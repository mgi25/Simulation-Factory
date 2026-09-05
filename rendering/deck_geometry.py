"""The Neon machine's deck geometry, in Python, so it can be tested.

`godot/scripts/neon_scene.gd` derives every stretch of drawn track from the
simulation's own walls: it samples a section every `DECK_STEP` course pixels,
asks what is clear between the walls at that height, and sweeps a solid
through the answer. Nothing describes the shape of the chute, the throat, the
bridge or the catch anywhere - the walls are the description.

That builder produced two defects during the V1 prototype, and both of them
put marbles over nothing, which is the one thing the whole presentation
mapping exists to make impossible:

* a wall was measured by its axis-aligned extent, which is the same at every
  height, so a channel that *leans* got a deck of one constant width. Six of
  sixteen racers finished the V1 race standing in the void beside the rails.

* where the number of channels changed, the closing sweep ended one sample
  before the opening sweep began - a full sample step with nothing swept
  between, and because every sweep is capped at both ends, that is an open
  slot right across the deck rather than a seam. The whole field was drawn
  crossing it inside the shipped video.

Both were found by porting the builder to Python and replaying against it,
and both were invisible to the pytest suite because nothing in it can reach
GDScript. This module is that port, kept rather than thrown away.

## What "kept" has to mean

A port is only worth having if it cannot drift from the thing it mirrors. Two
rules do that work here:

* **The constants live in one place and are checked.** Every number below
  mirrors a `const` in `neon_scene.gd`, and
  `tests/test_deck_geometry.py::test_the_scene_and_the_port_agree_on_every_shared_constant`
  parses the GDScript and asserts each one, so a value edited on one side and
  not the other fails the suite rather than the render.

* **The algorithm is transcribed, not re-derived.** Each function below is
  the same arithmetic in the same order as its GDScript twin, named the same
  way. Where the two differ - GDScript's `Vector2`/`Vector3` against tuples -
  the difference is spelled out in the function's own docstring.

It is a *reference implementation*, not a second renderer. Nothing in the
production pipeline imports it; the tests do, and so does anyone who has to
find out why a deck is the shape it is.
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

__all__ = [
    "DECK_MARGIN",
    "DECK_STEP",
    "EDGE_SMOOTHING",
    "MIN_SPAN",
    "Sample",
    "band",
    "clear_spans",
    "deck_ribbons",
    "inset",
    "piece_span",
    "section_bounds",
    "smooth",
    "widen",
]

# --- constants, mirrored from neon_scene.gd ---------------------------------

# Course pixels the deck reaches past the walls, so the rails have something
# to stand on and the racing surface still ends where the simulation says.
DECK_MARGIN = 32.0
# Course pixels between deck cross-sections.
DECK_STEP = 26.0
# Narrower than a racer is not a channel. Rejects the slivers a conservative
# wall measurement leaves either side of a joint.
MIN_SPAN = 60.0
# Samples either side of a cross-section that its edges are averaged over.
EDGE_SMOOTHING = 3
# Below this, a piece is a floor rather than the wall of a channel.
WALL_SIN_MIN = 0.25

# A cross-section: (left edge, right edge, course height), all in simulation
# pixels. The GDScript carries the same three numbers as a `Vector3` for the
# reason a dictionary per sample would be a few thousand allocations.
Sample = tuple[float, float, float]


# --- one wall, at one height ------------------------------------------------


def piece_span(spec: dict, y: float) -> tuple[float, float] | None:
    """What a piece blocks on the x axis at a course height, or `None`.

    A circle contributes its *chord* rather than its diameter: a peg caught
    at the very edge of a sample blocks almost nothing there.

    A box is measured by clipping its rotated outline against the horizontal
    line at `y`, which is exact. The first version of this took the box's
    axis-aligned extent instead, and that is wrong in one specific way: the
    extent is the same at every height, so a wall that leans claims the same
    slice of the x axis all the way down itself. A leaning wall is at a
    different x at every y and the deck under it has to be too.

    Returns `None` where GDScript returns `Vector2.ZERO`, because a real span
    could in principle be `(0, 0)` and a sentinel that can collide with an
    answer is a bug waiting for the course to move to the origin.
    """
    piece_y = float(spec.get("y", 0.0))
    if str(spec.get("type", "")) == "circle":
        radius = float(spec.get("radius", 0.0))
        if abs(y - piece_y) > radius:
            return None
        half = math.sqrt(max(1.0, radius * radius - (y - piece_y) ** 2))
        centre = float(spec.get("x", 0.0))
        return (centre - half, centre + half)

    half_w = float(spec.get("width", 0.0)) * 0.5
    half_h = float(spec.get("height", 0.0)) * 0.5
    angle = math.radians(float(spec.get("rotation_degrees", 0.0)))
    # A near-horizontal piece is a floor, not the wall of a channel. Skipping
    # them is what stops the finish apron's own floor being read as a wall
    # right across the section it is the floor of.
    if abs(math.sin(angle)) < WALL_SIN_MIN:
        return None

    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    piece_x = float(spec.get("x", 0.0))
    corners = [
        (
            piece_x + sx * half_w * cos_a - sy * half_h * sin_a,
            piece_y + sx * half_w * sin_a + sy * half_h * cos_a,
        )
        for sx, sy in ((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0))
    ]

    lowest = math.inf
    highest = -math.inf
    for index in range(4):
        here = corners[index]
        nxt = corners[(index + 1) % 4]
        if abs(here[1] - y) < 1.0e-6:
            lowest = min(lowest, here[0])
            highest = max(highest, here[0])
        if (here[1] - y) * (nxt[1] - y) >= 0.0 or here[1] == nxt[1]:
            continue
        t = (y - here[1]) / (nxt[1] - here[1])
        crossing = here[0] + t * (nxt[0] - here[0])
        lowest = min(lowest, crossing)
        highest = max(highest, crossing)
    if lowest > highest:
        return None
    return (lowest, highest)


def clear_spans(pieces: Iterable[dict], section: str, y: float) -> list[tuple[float, float]]:
    """Every gap in one section's walls at a course height, left to right.

    Only gaps walled on *both* sides count. Anything running off to a course
    edge is not a channel - it is the open air beside the machine, and the
    first version of this happily paved it: the chute came out ten units wide
    with the spouts drawn as scratches on it.
    """
    blocked: list[tuple[float, float]] = []
    for spec in pieces:
        if str(spec.get("section", "")) != section:
            continue
        if str(spec.get("role", "")) == "gate":
            continue
        span = piece_span(spec, y)
        if span is not None:
            blocked.append(span)
    blocked.sort(key=lambda span: span[0])

    spans: list[tuple[float, float]] = []
    if len(blocked) < 2:
        return spans
    cursor = blocked[0][1]
    for span in blocked[1:]:
        if span[0] - cursor > MIN_SPAN:
            spans.append((cursor, span[0]))
        cursor = max(cursor, span[1])
    return spans


def section_bounds(course: dict, section: str) -> tuple[float, float] | None:
    for entry in course.get("sections", []):
        if str(entry.get("name", "")) == section:
            return (float(entry.get("top", 0.0)), float(entry.get("bottom", 0.0)))
    return None


# --- the sweep --------------------------------------------------------------


def deck_ribbons(course: dict, section: str) -> list[list[Sample]]:
    """The channels through one section, as runs of cross-sections.

    Sampled top to bottom. While the number of gaps holds steady each sample
    is appended to the run it continues; when the count changes - four launch
    channels becoming two feed spouts - the open runs are closed and new ones
    begun *on the same plane*, so the two sweeps meet rather than leaving a
    step of deck unswept between them.

    Abutting is safe where overlapping would not be: the closing run's end
    cap and the opening run's start cap are coplanar with opposite normals,
    so whichever one faces the lens is the only one drawn.
    """
    bounds = section_bounds(course, section)
    if bounds is None:
        return []
    start, raw_finish = bounds
    finish = raw_finish - 2.0
    if finish <= start:
        return []
    steps = max(1, int((finish - start) / DECK_STEP))
    pieces = course.get("pieces", [])

    ribbons: list[list[Sample]] = []
    open_runs: list[list[Sample]] = []
    previous = start
    for step in range(steps + 1):
        y = start + step * (finish - start) / steps
        spans = clear_spans(pieces, section, y)
        if len(spans) != len(open_runs):
            seam = (previous + y) * 0.5
            seamed = seam > previous + 0.5
            for run in open_runs:
                if seamed and run:
                    last = run[-1]
                    run.append((last[0], last[1], seam))
                if len(run) >= 2:
                    ribbons.append(run)
            open_runs = [
                [(span[0], span[1], seam)] if seamed else [] for span in spans
            ]
        for index, span in enumerate(spans):
            open_runs[index].append((span[0], span[1], y))
        previous = y
    for run in open_runs:
        if len(run) >= 2:
            ribbons.append(run)

    # A wall's first and last boxes only just reach the planes their section
    # begins and ends at, so a sample there can fall on either side of one
    # depending on rounding - and the sweep deliberately stops two pixels
    # short of the bottom, because at the plane itself this section's walls
    # have ended and the next section's have begun, which reads as a change of
    # channel count and splits every run.
    #
    # So the first run is pulled back to the section top and the last is
    # carried on to the section bottom. What that closes is the seam between
    # two stretches of track: two course pixels of nothing is a fiftieth of a
    # world unit and invisible, but a racer standing over it is standing over
    # nothing, and that is the one thing this whole builder exists to prevent.
    #
    # Every run that reaches a plane is carried to it, not only the first and
    # the last in the list. The list is in the order runs *closed*, so on a
    # section that ends in two channels the last two entries both end at the
    # sweep's final plane and only one of them is the list's last.
    for run in ribbons:
        head = run[0]
        if head[2] <= start + DECK_STEP and head[2] > start + 1.0e-6:
            run.insert(0, (head[0], head[1], start))
        tail = run[-1]
        if tail[2] >= finish - 1.0e-6:
            run.append((tail[0], tail[1], raw_finish))

    return [smooth(run) for run in ribbons]


def smooth(samples: Sequence[Sample]) -> list[Sample]:
    """Round the scallop out of a swept edge.

    A wall is a chain of straight boxes that overlap at every joint, and
    where two overlap the clear width is decided by whichever of them claims
    more of the x axis - so a curved wall's inner face has a shallow corner
    at each joint rather than a continuous curve. Averaging over a window a
    little wider than one box removes them and leaves the curve itself, which
    is two orders of magnitude longer, untouched.
    """
    if len(samples) < 3:
        return list(samples)
    out: list[Sample] = []
    for index in range(len(samples)):
        left = 0.0
        right = 0.0
        count = 0
        for offset in range(-EDGE_SMOOTHING, EDGE_SMOOTHING + 1):
            at = min(max(index + offset, 0), len(samples) - 1)
            left += samples[at][0]
            right += samples[at][1]
            count += 1
        out.append((left / count, right / count, samples[index][2]))
    return out


# --- the shaping helpers ----------------------------------------------------


def widen(samples: Sequence[Sample], left: float, right: float) -> list[Sample]:
    """The same run of cross-sections with its edges moved, in course pixels."""
    return [(s[0] + left, s[1] + right, s[2]) for s in samples]


def inset(samples: Sequence[Sample], fraction: float) -> list[Sample]:
    """The middle share of a run, as a fraction of its own width."""
    out: list[Sample] = []
    for s in samples:
        centre = (s[0] + s[1]) * 0.5
        half = (s[1] - s[0]) * 0.5 * fraction
        out.append((centre - half, centre + half, s[2]))
    return out


def band(samples: Sequence[Sample], side: float, inner: float,
         outer: float) -> list[Sample]:
    """A narrow run along one edge of a deck, measured from that edge inwards.

    `side` is -1 for the left edge and +1 for the right. Both offsets are
    course pixels from the edge, positive inwards, which is what lets a rail
    and the strip let into its top be described the same way.
    """
    out: list[Sample] = []
    for s in samples:
        edge = s[0] if side < 0.0 else s[1]
        a = edge + side * -outer
        b = edge + side * -inner
        out.append((min(a, b), max(a, b), s[2]))
    return out


# --- reading a deck back ----------------------------------------------------


def covered(ribbons: Sequence[Sequence[Sample]], x: float, y: float,
            margin: float = DECK_MARGIN) -> bool:
    """Is `(x, y)` over drawn deck?

    The question the whole builder exists to answer yes to for every racer.
    A ribbon is a run of cross-sections and the deck between two of them is a
    quadrilateral, so the test is: find the pair of samples that straddle `y`,
    interpolate their edges, and ask whether `x` is inside - widened by the
    same margin the deck is drawn with.
    """
    for run in ribbons:
        if len(run) < 2:
            continue
        if not run[0][2] <= y <= run[-1][2]:
            continue
        for here, nxt in zip(run, run[1:]):
            if not here[2] <= y <= nxt[2]:
                continue
            span = nxt[2] - here[2]
            t = 0.0 if span <= 0.0 else (y - here[2]) / span
            left = here[0] + (nxt[0] - here[0]) * t - margin
            right = here[1] + (nxt[1] - here[1]) * t + margin
            if left <= x <= right:
                return True
    return False

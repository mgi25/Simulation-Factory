"""V23: the environment directions, the frames they are judged on, and how.

This is the Python half of the environment lab. The Godot half is
`godot/assets/marble_machine/course/course_env.gd`, which re-skins a finished
V22.1 scene as one named direction; this module says **which** directions there
are, **which frames** they are compared on, and **what is measured** on those
frames so that a choice between them is argued rather than asserted.

## The comparison is fair by construction

Every direction is photographed through the same solved V22.1 camera tracks, at
the same output seconds, from the same locked replay, with the same start
contract and the same `--finish-sign=double`. Nothing in the lab re-solves a
camera, re-seeds a scatter or re-runs a physics step: `tools/sloped_v23_env.py`
renders each direction with one extra flag and nothing else, so two frames that
differ differ only in the evening they were taken in.

## What is measured, and what a number here cannot see

Five measures per frame, chosen because each answers one line of the brief and
because each one caught something during the pass:

* **headroom** - the machine's own brightness minus the backdrop's. The V22.1
  frame has a warm sky brighter than the pearl track at the fork and at the
  finish, and a white machine on a lighter ground has no silhouette. Positive
  headroom is the single number the brief's "premium" and "readable" both
  depend on.
* **backdrop flatness** - whether the top quarter of the frame is a
  featureless wall. It is *not* a layering measure and the table does not
  pretend it is: three attempts at scoring layering from a rendered frame all
  failed, all of them by measuring brightness or contrast under another name,
  and `plateaus` records what was tried and why. Depth is judged on the sheets
  and the clips. What this number can say is "there is nothing back there",
  which one direction earns in eight frames out of eleven.
* **backdrop warmth** - the mean CIELAB b* of that same band. The brief spends
  its warm accents on the choice zone and the finish, and V22.1 spends most of
  them on the sky. A direction that has moved the warmth off the horizon shows
  a b* near zero or below there and a warm reading at the finish.
* **separation** - each marble against the course immediately behind it, in
  CIELAB, borrowed unchanged from the V21 contrast pass. This is the
  readability floor: an environment that is beautiful and costs the racers
  their contrast has failed the one rule the brief marks as a constraint.
* **clip** - the share of the frame flat at the top of the range. V21 exists
  because V20 clipped one pixel in eighteen, and a direction that raises
  exposure to look richer can put it straight back.

None of them can see composition, memorability or whether a world looks like a
toy. Those are what the sheets are for. The numbers are here to stop a frame
being called better when it is only brighter.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

# --- the directions ---------------------------------------------------------


@dataclass(frozen=True)
class Direction:
    """One environment direction, as the lab refers to it.

    `key` is the string passed to Godot as `--env=`; it must match a key of
    `course_env_profiles.PROFILES`, and `tests/test_sloped_v23_env.py` checks
    that the two lists have not drifted apart.
    """

    key: str
    title: str
    blurb: str


BASELINE = Direction(
    "",
    "V22.1 baseline",
    "the accepted production picture, rendered with no profile at all",
)

DIRECTIONS: tuple[Direction, ...] = (
    Direction(
        "aurora",
        "A - Aurora Valley",
        "cold alpine dusk; four steps of aerial perspective, mist in the "
        "gorge, and the only warm light in the world at the finish",
    ),
    Direction(
        "collector",
        "B - Collector Canyon",
        "a warm stylised canyon on a cool seamless backdrop; product-lit, "
        "thin haze, clean silhouettes, no environmental neon at all",
    ),
    Direction(
        "graphite",
        "C - Graphite Grid",
        "a near-black valley the machine is the only light in; graphic "
        "silhouettes and one restrained cyan accent in the far distance",
    ),
)

ALL: tuple[Direction, ...] = (BASELINE,) + DIRECTIONS


def direction(key: str) -> Direction:
    for entry in ALL:
        if entry.key == key:
            return entry
    raise KeyError(f"no V23 direction named {key!r}")


# --- the frames -------------------------------------------------------------


@dataclass(frozen=True)
class Moment:
    """One comparison frame: which track, which output second, and why.

    `track` is `"preview"` or `"race"` and decides which of the two solved
    V22.1 camera tracks - and therefore which replay - the frame is rendered
    from. `second` is an **output** second of that track, which is what the
    renderer's `--at=` takes.
    """

    key: str
    track: str
    second: float
    title: str
    why: str


# The eight the brief asks for, plus the three preview frames that are the only
# place the course is seen whole. The race seconds are inside the cut they name
# on the V22.1 track, which runs:
#
#     start 0.00-4.55   descent 4.55-7.52   obstacle 7.52-12.95
#     fork 12.95-14.58  branches 14.58-16.27  merge 16.27-16.75
#     final 16.75-22.32
#
# so each is a frame of the shot it is labelled with rather than a frame near
# one. The preview runs the course backwards from the finish to the start line,
# which is why `preview_arena` is the earliest of the three.
MOMENTS: tuple[Moment, ...] = (
    Moment("preview_arena", "preview", 0.300, "Preview - the finish arena",
           "the widest view of the mesa, and the frame the film opens on"),
    Moment("preview_mid", "preview", 1.500, "Preview - mid course",
           "the reverse dolly at its furthest out: whole-course scale"),
    Moment("preview_start", "preview", 2.900, "Preview - the start",
           "the handoff frame, where the world has to sell the drop below"),
    Moment("start_grid", "race", 0.600, "Start - the grid",
           "eight marbles held on the line, the tightest read in the film"),
    Moment("start_release", "race", 3.400, "Start - the release",
           "the trapdoor, with the whole start pod and its ground in shot"),
    Moment("descent", "race", 5.800, "The first descent",
           "the first shot with terrain above and gorge below at once"),
    Moment("obstacle", "race", 10.200, "The spinner corridor",
           "the longest cut, and the one with the most orange in it"),
    Moment("fork", "race", 13.600, "The fork",
           "the choice zone; the brief's orange energy belongs here"),
    Moment("branches", "race", 15.400, "The branches",
           "two routes over open air: the depth shot of the whole film"),
    Moment("merge", "race", 16.500, "The merge",
           "the routes rejoining, with the finish mesa already in frame"),
    Moment("finish", "race", 21.400, "The finish",
           "the gold payoff, parked up-course of a double-sided board"),
)

PREVIEW_MOMENTS = tuple(one for one in MOMENTS if one.track == "preview")
RACE_MOMENTS = tuple(one for one in MOMENTS if one.track == "race")


def moment(key: str) -> Moment:
    for entry in MOMENTS:
        if entry.key == key:
            return entry
    raise KeyError(f"no V23 moment named {key!r}")


def seconds_for(track: str) -> tuple[float, ...]:
    return tuple(one.second for one in MOMENTS if one.track == track)


# --- the proof clips --------------------------------------------------------


@dataclass(frozen=True)
class Clip:
    """A short continuous span, rendered per direction as a moving proof.

    A still cannot show whether a haze bank swims against the ranges behind it
    when the camera moves, and that is the one failure mode a layered backdrop
    has that a flat one does not. Two spans are enough to see it: the preview,
    which is the only shot that travels the whole course, and the fork-to-merge
    run, which is the one that crosses the gorge.
    """

    key: str
    track: str
    start: float
    end: float
    title: str


CLIPS: tuple[Clip, ...] = (
    Clip("preview", "preview", 0.000, 3.483,
         "the course preview, whole"),
    Clip("choice", "race", 12.950, 16.750,
         "fork to merge: the choice, both routes, and the gorge"),
)


# --- the measures -----------------------------------------------------------

# The top of the frame is where this course puts its backdrop. Every camera on
# it stands downhill of what it looks at and is aimed a few degrees below
# horizontal, so the machine occupies the middle and lower thirds and the band
# above is sky, haze and distant range. A quarter is the largest share that is
# backdrop in *every* one of the eleven moments - at a third the finish frame
# starts eating the FINISH gantry, which would read as a warm, high-contrast
# backdrop and flatter exactly the direction that changed least.
BACKDROP_BAND = 0.25

# The machine's own brightness, as a percentile rather than a maximum: a single
# specular pinpoint on a chrome bead is not the subject's value, and the 98th
# percentile of a 1080x1920 frame is still forty thousand pixels.
SUBJECT_PERCENTILE = 98.0

# V21's own clip thresholds, unchanged, so a V23 number is comparable with the
# table in `docs/sloped_race_v21_contrast.md`.
FLAT_WHITE = 250
NEAR_CLIP = 254


def to_lab(rgb: np.ndarray) -> np.ndarray:
    """sRGB 0-255 to CIELAB, D65, on an array whose last axis is the channel.

    `tools/sloped_contrast_measure._lab`, copied rather than imported because a
    tool is not a package and importing one from `sloped/` would invert the
    dependency the whole repository is arranged around.
    """
    srgb = rgb.astype(np.float64) / 255.0
    linear = np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)
    matrix = np.array([
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ])
    xyz = linear @ matrix.T
    white = np.array([0.95047, 1.0, 1.08883])
    ratio = xyz / white
    f = np.where(ratio > 0.008856, np.cbrt(ratio), 7.787 * ratio + 16.0 / 116.0)
    return np.stack([
        116.0 * f[..., 1] - 16.0,
        500.0 * (f[..., 0] - f[..., 1]),
        200.0 * (f[..., 1] - f[..., 2]),
    ], axis=-1)


def frame_measures(pixels: np.ndarray) -> dict[str, float]:
    """The five per-frame numbers. `pixels` is RGB, uint8, (height, width, 3).

    Read the class docstring for what each one is evidence for. Two notes on
    the arithmetic that matter when the table is read:

    * **headroom is a difference of two different statistics** - a high
      percentile for the subject and a mean for the backdrop - and that is
      deliberate. The subject is a small bright object in a large frame and its
      mean is dominated by whatever surrounds it; the backdrop is a large flat
      region and its percentile is dominated by whatever pokes into the band.
      Each statistic is the robust one for its own region.
    * **backdrop warmth is signed** and is a b* value, so it is directly
      comparable between directions: positive is yellow-orange, negative is
      blue. It is not a share of warm pixels, because a small very warm area
      and a large slightly warm one are different pictures and only the mean
      tells them apart.
    """
    if pixels.ndim != 3 or pixels.shape[2] != 3:
        raise ValueError("frame_measures wants an (h, w, 3) RGB array")
    lab = to_lab(pixels)
    lightness = lab[..., 0]
    band = max(1, int(round(pixels.shape[0] * BACKDROP_BAND)))
    backdrop = lab[:band]
    return {
        "subject": float(np.percentile(lightness, SUBJECT_PERCENTILE)),
        "backdrop": float(backdrop[..., 0].mean()),
        "headroom": float(
            np.percentile(lightness, SUBJECT_PERCENTILE) - backdrop[..., 0].mean()
        ),
        "spread": float(backdrop[..., 0].std()),
        "planes": plateaus(backdrop[..., 0]),
        "warmth": float(backdrop[..., 2].mean()),
        "mean": float(lightness.mean()),
        "flat_white": float((pixels >= FLAT_WHITE).all(axis=-1).mean() * 100.0),
        "near_clip": float((pixels >= NEAR_CLIP).any(axis=-1).mean() * 100.0),
    }


# A plane has to hold this share of the backdrop band to count as one. Below
# about a fortieth of the band a region is an edge, a lamp or a piece of the
# machine poking into the sky rather than a layer of the world.
PLANE_SHARE = 0.025

# Twenty-five bins over the band's own range, so a plane is a twenty-fifth of
# whatever contrast the picture actually has. See `plateaus` for why the range
# is the band's and not the L* scale's.
PLANE_BINS = 25

# Below this much lightness range the band has nothing in it to separate and
# normalising would be amplifying noise into planes. Three L* over a quarter of
# a 1080x1920 frame is a flat wall.
PLANE_FLOOR = 3.0


def plateaus(lightness: np.ndarray) -> int:
    """How many separable value plateaus the backdrop band holds - a
    **flatness** detector, and deliberately not a layering one.

    ## Three measures of "is there depth back there" were tried and all three
    ## failed, which is the most useful thing this lab learned about measuring

    The brief asks for foreground/midground/background layering, and the
    obvious move is to score it from a rendered frame. It does not work, and
    the three attempts fail in two distinct ways:

    * **Standard deviation of L\\* across the band.** Ranks the V22.1 baseline
      top: 16.4 against 14.1, 13.3 and 10.3 for the three directions that
      demonstrably added layers. A bright sky with one hard silhouette cut out
      of it occupies a huge absolute range; a dark world occupies a small one
      however many layers are inside it. It reads *how bright the backdrop is*.
    * **Plateau count in absolute L\\*.** Same ranking, 10.5 against 5.9, 5.9
      and 2.9, for the same reason: a dark world has few absolute bins to
      occupy.
    * **Step count in the row-mean profile** - the second difference of the
      band's per-row mean, which should spike at a layer boundary and stay flat
      through a gradient. Still ranks the baseline top (25.7 against 9.0, 11.5,
      9.0) and is dominated by whichever frames have machine in the band: the
      obstacle frame alone scores 194 steps, none of them sky.

    The common failure is that none of them can tell *where the backdrop ends*.
    Layering is an ordering of regions by depth, a single rendered frame does
    not carry depth, and every proxy tried here ended up measuring contrast or
    brightness under another name. **Depth in this lab is judged on the sheets
    and the clips, and no number in the table claims to see it.**

    What survives is worth keeping, and it is the normalised version because it
    answers a narrower question honestly: the band is scaled to its own
    2nd-to-98th percentile range and the plateaus counted inside that, with
    `PLANE_FLOOR` returning 1 when there is less than three L* of range to
    normalise. So a score of 1 means *this backdrop is a featureless wall*, and
    that is a real finding: Graphite Grid scores 1 in eight of the eleven
    moments, which is the measured form of "the machine is floating in a void".
    Anything above about 4 means only "not a wall" and should not be ranked.
    """
    low = float(np.percentile(lightness, 2.0))
    high = float(np.percentile(lightness, 98.0))
    if high - low < PLANE_FLOOR:
        return 1
    scaled = (lightness - low) / (high - low)
    counts, _ = np.histogram(scaled, bins=PLANE_BINS, range=(0.0, 1.0))
    share = counts.astype(np.float64) / max(float(lightness.size), 1.0)
    return int((share >= PLANE_SHARE).sum())


def separation(
    pixels: np.ndarray,
    places: Sequence[tuple[float, float, float]],
) -> list[tuple[float, float]]:
    """Per racer, `(dE, chroma-only dE)` against the course behind it.

    `tools/sloped_contrast_measure.separation`, with the same disc-against-
    annulus geometry and the same caveat: an occluded marble reports a false
    near-zero because its centre lands on whatever is in front of it. Report
    the median beside the mean and compare directions rather than absolutes.
    """
    values = pixels.astype(np.float64)
    height, width = values.shape[:2]
    ys, xs = np.mgrid[0:height, 0:width]
    out: list[tuple[float, float]] = []
    for x, y, radius in places:
        if radius < 2.0 or not (0 <= x < width and 0 <= y < height):
            continue
        far = (xs - x) ** 2 + (ys - y) ** 2
        ball = far <= (radius * 0.55) ** 2
        ring = (far >= (radius * 1.60) ** 2) & (far <= (radius * 2.60) ** 2)
        if int(ball.sum()) < 4 or int(ring.sum()) < 12:
            continue
        a = to_lab(values[ball].mean(axis=0))
        b = to_lab(values[ring].mean(axis=0))
        out.append((
            float(np.linalg.norm(a - b)),
            float(np.linalg.norm(a[1:] - b[1:])),
        ))
    return out


def median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return float(0.5 * (ordered[middle - 1] + ordered[middle]))


def places_at(
    replay: dict[str, Any],
    track: dict[str, Any],
    when: float,
    project,
    camera_at,
    width: int,
    height: int,
) -> list[tuple[float, float, float]]:
    """Every marble's `(x, y, radius)` on the delivered frame at a replay second.

    The projection is passed in rather than imported so this module does not
    depend on `sloped.presentation`, which carries the Short's clock and has no
    business being loaded to measure a lab still. `tools/sloped_v23_env.py`
    hands it `presentation.project` and `presentation._camera_at`, which is the
    same arithmetic the V21 contrast table was built with.
    """
    units = replay.get("units", {})
    scale = float(units.get("render_scale", 0.57))
    marble_radius = float(units.get("layout_marble_radius", 0.285))
    frame = min(replay["frames"], key=lambda one: abs(float(one["t"]) - when))
    camera, aim, fov = camera_at(track, when)
    half_up = math.tan(math.radians(fov) * 0.5)
    out: list[tuple[float, float, float]] = []
    for sample in frame["marbles"]:
        point = tuple(float(sample["p"][axis]) * scale for axis in range(3))
        placed = project(camera, aim, fov, point)
        if placed is None:
            continue
        x, y, depth = placed
        if not (0 <= x < width and 0 <= y < height):
            continue
        out.append((x, y, (marble_radius / depth) / half_up * (height * 0.5)))
    return out


def output_to_replay(track: dict[str, Any], output: float) -> float:
    """A camera track's own output clock to its replay clock.

    Slope one inside every window, exactly as `sloped_race_scene.replay_at`
    reads it, and held at the end of the last window rather than running off
    the replay. A track with no edit - the preview's - maps one to one.
    """
    edit = track.get("edit") or ()
    if not edit:
        return output
    for window in edit:
        low, high = window["out"]
        if output <= high or window is edit[-1]:
            span = window["replay"][1] - window["replay"][0]
            return window["replay"][0] + min(max(output - low, 0.0), span)
    return output

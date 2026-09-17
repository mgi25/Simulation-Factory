"""The V33 opening shot: one hook composition, and the move that hands off.

## What this replaces and what it must not touch

The delivered Race #2 camera track is four cuts - `release` 0.017-2.217,
`upper` 2.233-9.017, `middle`, `run_in`. This module rewrites **`release` and
nothing else**. The three later cuts are copied through byte for byte, and
`tools/race2_v33_bookends.py camera` asserts that by comparing their frame rows
with the source track's.

So the film's cut structure, its cut times, its lens speeds and its whole
middle are unchanged by construction rather than by care.

## The handoff

An opening shot that ends anywhere lands the viewer in a hard cut with a
different subject, a different scale and a different direction, which is the
one thing the brief says must not happen to somebody who has just chosen a
colour. So the last frame of the opening is **`upper`'s first pose, walked back
one frame along `upper`'s own opening velocity**. The result is that position,
aim and lens are continuous across the join to first order: the existing cut
at 2.233 s is still in the schedule and is still where the film's structure
says it is, but there is nothing there for an eye to catch on.

`handoff_error` reports the three residuals - position, aim and fov - so the
claim is a number rather than a description.

## Why the compositions are solved rather than authored

Eight racers at a 0.82 pitch are 6.31 layout units end to end, and a portrait
frame 1080 wide at a 32 degree vertical lens is 0.323 units of world per unit
of distance. Fitting the row across the frame therefore *caps* a racer at about
9% of frame width however the shot is dressed - and 9% is 97 px, which is not
much better than the 81 px the shipped opening has.

The lever is obliquity. Viewed at an azimuth `theta` off the course axis the
row's apparent width falls as `cos(theta)` while a racer's diameter does not,
so the camera can come closer. It costs depth spread: at 60 degrees the nearest
racer is 1.7x the diameter of the furthest, and past about 65 the near ones
start covering the far ones. `solve` walks the distance in against the frame
and `measure` reports what that bought, per composition, so the choice between
A, B and C is made on a table rather than on an opinion.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

__all__ = [
    "FRAME_WIDTH",
    "FRAME_HEIGHT",
    "Composition",
    "COMPOSITIONS",
    "screen",
    "basis",
    "solve",
    "measure",
    "opening_cut",
    "pack_centroid",
    "rewrite_track",
    "handoff_error",
]

FRAME_WIDTH = 1080
FRAME_HEIGHT = 1920

Vec3 = tuple[float, float, float]


def _unit(v: Sequence[float]) -> Vec3:
    span = math.sqrt(sum(float(c) * float(c) for c in v)) or 1.0
    return (float(v[0]) / span, float(v[1]) / span, float(v[2]) / span)


def basis(position: Sequence[float], aim: Sequence[float]):
    """The lens's forward, right and up, with the camera held level.

    Identical to `race2.rig._basis`, and `tests/test_race2_v33_bookends.py`
    asserts that on random inputs rather than by inspection: two projections
    that disagree by a sign produce a metric that is confidently wrong.
    """
    forward = _unit(tuple(aim[axis] - position[axis] for axis in range(3)))
    right = _unit((-forward[2], 0.0, forward[0]))
    up = (
        right[1] * forward[2] - right[2] * forward[1],
        right[2] * forward[0] - right[0] * forward[2],
        right[0] * forward[1] - right[1] * forward[0],
    )
    return forward, right, _unit(up)


def screen(points: Sequence[Sequence[float]], position: Sequence[float],
           aim: Sequence[float], fov: float) -> list[tuple[float, float, float]]:
    """`(x, y, depth)` per point: x and y in [-1, 1], depth in layout units.

    `race2.rig._screen` returns the first two and drops the third; the depth is
    what turns a projected centre into a diameter in pixels, which is the
    measurement Part G is written in.
    """
    forward, right, up = basis(position, aim)
    half_up = math.tan(math.radians(fov) * 0.5)
    half_right = half_up * (FRAME_WIDTH / FRAME_HEIGHT)
    out: list[tuple[float, float, float]] = []
    for point in points:
        offset = [point[axis] - position[axis] for axis in range(3)]
        depth = sum(offset[axis] * forward[axis] for axis in range(3))
        if depth <= 1.0e-3:
            out.append((9.0, 9.0, depth))
            continue
        out.append((
            sum(offset[axis] * right[axis] for axis in range(3)) / (depth * half_right),
            sum(offset[axis] * up[axis] for axis in range(3)) / (depth * half_up),
            depth,
        ))
    return out


def pixel_diameter(depth: float, fov: float, radius: float) -> float:
    """A sphere's diameter in pixels at `depth`, on the delivered frame.

    The small-angle form `2 r / (depth * 2 * half_right) * WIDTH` is not used:
    at the distances a hook shot works at, the angular diameter of a 0.57-unit
    ball is a few degrees and the error is under a tenth of a pixel, but the
    exact form costs one `asin` and cannot drift.
    """
    if depth <= radius:
        return float(FRAME_WIDTH)
    half_up = math.tan(math.radians(fov) * 0.5)
    half_right = half_up * (FRAME_WIDTH / FRAME_HEIGHT)
    angle = math.asin(min(1.0, radius / depth))
    return 2.0 * math.tan(angle) / half_right * 0.5 * FRAME_WIDTH


# --- compositions -----------------------------------------------------------


@dataclass(frozen=True)
class Composition:
    """One hook camera, as an angle rather than as a position.

    `azimuth` is measured in the start site's ground plane from the direction
    the race runs *towards*, turning toward `across`; so 0 is dead in front of
    the bay row looking back up the course, 90 is square on from the side, and
    past 90 the camera is behind the row. `elevation` is above that plane.

    The camera is placed by `solve`, which walks the distance in until the
    frame will not hold the row any tighter.
    """

    key: str
    title: str
    azimuth: float
    elevation: float
    fov: float
    fit: float = 0.92            # the row's share of the frame when solved
    aim_up: float = 0.36         # where in the stand the lens is pointed
    aim_along: float = -0.45
    note: str = ""


COMPOSITIONS: tuple[Composition, ...] = (
    Composition("A", "front three-quarter grid", azimuth=44.0, elevation=22.0,
                fov=20.0, aim_up=0.34, aim_along=-0.40,
                note="the largest racer the row will hold at full separation, "
                     "and the bay layout read straight off"),
    Composition("B", "low three-quarter, along the row", azimuth=78.0,
                elevation=14.0, fov=26.0, aim_up=0.40, aim_along=-0.30,
                note="down the row rather than across it: the biggest racers "
                     "in the set, bought with most of the separation"),
    Composition("C", "elevated three-quarter", azimuth=58.0, elevation=42.0,
                fov=18.0, aim_up=0.22, aim_along=-0.24,
                note="high enough to slant the row across the portrait frame, "
                     "which is where the extra size comes from, and to show "
                     "the gate and the band the field falls onto"),
)

# **A true rear hook is not available on this stand, and the number is 52.**
# The brief asks for a low rear three-quarter as composition B. A camera
# upstream of the bay row looks through the back board, which rises 1.74 above
# a deck the racers sit 0.35 above; clearing its top edge on the way to a racer
# needs an elevation of about 52 degrees, which is the map-like view the same
# brief rules out. The two wants - a board that fills the void behind the
# racers, and a lens behind them - are mutually exclusive, and the board is
# worth more. B is therefore taken round to 78 degrees, which is the lowest,
# most raking angle at which nothing on the stand is between the lens and a
# racer. `tools/race2_v33_bookends.py hooks` re-derives the blocking rather
# than trusting this paragraph.
REAR_HOOK_ELEVATION_DEG = 52.0


def _place(site, composition: Composition, distance: float) -> tuple[Vec3, Vec3]:
    azimuth = math.radians(composition.azimuth)
    elevation = math.radians(composition.elevation)
    aim = site.at(composition.aim_along, composition.aim_up, 0.0)
    along, up, across = site.axes()
    ground = (
        math.cos(azimuth) * along[0] + math.sin(azimuth) * across[0],
        math.cos(azimuth) * along[1] + math.sin(azimuth) * across[1],
        math.cos(azimuth) * along[2] + math.sin(azimuth) * across[2],
    )
    direction = (
        math.cos(elevation) * ground[0] + math.sin(elevation) * up[0],
        math.cos(elevation) * ground[1] + math.sin(elevation) * up[1],
        math.cos(elevation) * ground[2] + math.sin(elevation) * up[2],
    )
    position = (aim[0] + direction[0] * distance,
                aim[1] + direction[1] * distance,
                aim[2] + direction[2] * distance)
    return position, aim


def racer_points(site, bays: int, bay_pitch: float, rise: float) -> list[Vec3]:
    """The eight resting centres, in the site's own frame.

    Taken from the geometry rather than from the replay so a composition can be
    solved before a race is run - which is what makes this reusable for a
    course whose replay does not exist yet.
    """
    half = 0.5 * (bays - 1) * bay_pitch
    return [site.at(-0.65, rise, -half + index * bay_pitch)
            for index in range(bays)]


def solve(site, composition: Composition, points: Sequence[Sequence[float]],
          radius: float, lo: float = 3.0, hi: float = 60.0,
          steps: int = 60) -> float:
    """The closest distance at which the row still fits `composition.fit`.

    Bisected on the *projected* extent, never computed from a world width:
    the row is foreshortened by the azimuth and spread by the elevation, and
    the two do not compose into a closed form worth trusting. The extent
    measured is the racers' silhouettes, not their centres, so a ball is not
    allowed to hang half out of frame.
    """
    def extent(distance: float) -> float:
        position, aim = _place(site, composition, distance)
        projected = screen(points, position, aim, composition.fov)
        worst_x = 0.0
        worst_y = 0.0
        for x, y, depth in projected:
            diameter = pixel_diameter(depth, composition.fov, radius)
            pad_x = diameter / FRAME_WIDTH
            pad_y = diameter / FRAME_HEIGHT
            worst_x = max(worst_x, abs(x) + pad_x)
            worst_y = max(worst_y, abs(y) + pad_y)
        # The frame is portrait, so the binding constraint is normally x; both
        # are tested because a steep elevation can push the far end of the row
        # out of the top instead.
        return max(worst_x, worst_y)

    for _ in range(steps):
        middle = 0.5 * (lo + hi)
        if extent(middle) > composition.fit:
            lo = middle
        else:
            hi = middle
    return hi


def measure(site, composition: Composition, distance: float,
            points: Sequence[Sequence[float]], radius: float) -> dict[str, Any]:
    """Part G's opening numbers for one composition, at one instant."""
    position, aim = _place(site, composition, distance)
    projected = screen(points, position, aim, composition.fov)
    diameters = [pixel_diameter(depth, composition.fov, radius)
                 for _x, _y, depth in projected]
    ordered = sorted(diameters)
    middle = len(ordered) // 2
    median = (ordered[middle] if len(ordered) % 2
              else 0.5 * (ordered[middle - 1] + ordered[middle]))
    pixels = [(0.5 * (x + 1.0) * FRAME_WIDTH, 0.5 * (1.0 - y) * FRAME_HEIGHT)
              for x, y, _d in projected]
    gaps = []
    for index in range(1, len(pixels)):
        gaps.append(math.dist(pixels[index - 1], pixels[index]))
    inside = sum(1 for x, y, d in projected
                 if d > 0.0 and abs(x) <= 1.0 and abs(y) <= 1.0)
    area = sum(math.pi * (0.5 * d) ** 2 for d in diameters)
    return {
        "key": composition.key,
        "title": composition.title,
        "azimuth": composition.azimuth,
        "elevation": composition.elevation,
        "fov": composition.fov,
        "distance": round(distance, 4),
        "position": [round(c, 4) for c in position],
        "aim": [round(c, 4) for c in aim],
        "median_diameter_1080": round(median, 2),
        "median_diameter_270": round(median * 270.0 / FRAME_WIDTH, 2),
        "min_diameter_1080": round(min(diameters), 2),
        "max_diameter_1080": round(max(diameters), 2),
        "near_far_ratio": round(max(diameters) / max(1.0e-6, min(diameters)), 3),
        "racer_area_share": round(area / (FRAME_WIDTH * FRAME_HEIGHT), 5),
        "min_centre_gap_px": round(min(gaps), 2) if gaps else 0.0,
        "min_gap_in_diameters": round(min(gaps) / median, 3) if gaps else 0.0,
        "in_frame": inside,
        "note": composition.note,
    }


# --- the cut ----------------------------------------------------------------


def _row(time: float, position: Sequence[float], aim: Sequence[float],
         fov: float) -> list[float]:
    return [round(time, 6), round(position[0], 5), round(position[1], 5),
            round(position[2], 5), round(aim[0], 5), round(aim[1], 5),
            round(aim[2], 5), round(fov, 5)]


def _ease(phase: float, shape: float) -> float:
    """A smoothstep raised to `shape`, so the hold at the head is adjustable.

    `shape` above 1 keeps the camera near the hook composition for longer and
    spends the travel later; the brief's "do not introduce a long pre-race
    hold" is the reason it is not a hold - the lens is moving on frame 1, it is
    just moving slowly while the premise is being read.
    """
    smooth = phase * phase * (3.0 - 2.0 * phase)
    return smooth ** shape


def opening_cut(site, composition: Composition, distance: float,
                target: Sequence[Sequence[float]], fps: int = 60,
                first: float = 0.016667, last: float = 2.216667,
                shape: float = 0.9, subject=None,
                track_from: float = 0.20, track_to: float = 0.60,
                hand_from: float = 0.82,
                ) -> dict[str, Any]:
    """The replacement `release` cut: one move that follows the field out.

    `target` is `(position, aim, fov)` for the frame *after* this cut's last -
    `handoff_pose` derives it from the next cut - and the last row here is that
    pose walked back one frame along the next cut's own opening velocity.

    ## The aim tracks the pack, and that is not a refinement

    A straight interpolation from the hook pose to the handoff pose holds the
    empty stand while the field falls out of frame. Measured on the delivered
    replay, it leaves **no racer on screen at all between about 1.1 s and
    2.0 s** - nearly a second in which a viewer who has just picked a colour
    has nothing to follow, which is the one failure the brief names.

    So `subject(t)` - the pack's centroid on the film's own frames - is blended
    into the aim over `track_from`..`track_to`, and the handoff aim is blended
    back in over the eased progress. The camera therefore does what the shipped
    `release` shot does, which is follow, and still lands exactly where `upper`
    begins. With no `subject` the behaviour is the old straight interpolation,
    so the two can be compared.
    """
    start_position, start_aim = _place(site, composition, distance)
    end_position, end_aim, end_fov = target
    count = int(round((last - first) * fps)) + 1
    frames: list[list[float]] = []
    for index in range(count):
        when = first + index / float(fps)
        phase = index / float(max(1, count - 1))
        eased = _ease(phase, shape)
        position = [start_position[axis]
                    + (end_position[axis] - start_position[axis]) * eased
                    for axis in range(3)]
        aim = [start_aim[axis] + (end_aim[axis] - start_aim[axis]) * eased
               for axis in range(3)]
        if subject is not None:
            follow = subject(when)
            if follow is not None:
                weight = 0.0
                if when > track_from:
                    span = max(1.0e-6, track_to - track_from)
                    weight = min(1.0, (when - track_from) / span)
                    weight = weight * weight * (3.0 - 2.0 * weight)
                # **The handoff blend is late, and that is a measurement.**
                # Blending it over the shot's whole eased progress puts the aim
                # 70% of the way to `upper`'s first frame by 1.3 s, while the
                # pack is still accelerating away from it: the field's centroid
                # then runs out to x = +2.3 of a frame that ends at 1.0 and
                # comes back, and 55 frames have no racer in them at all.
                # Holding the pack until `hand_from` of the shot and spending
                # the rest on the handoff keeps the centroid inside the frame
                # throughout and still lands on the handoff exactly.
                held = [start_aim[axis] + (follow[axis] - start_aim[axis]) * weight
                        for axis in range(3)]
                hand = 0.0
                if phase > hand_from:
                    hand = min(1.0, (phase - hand_from)
                               / max(1.0e-6, 1.0 - hand_from))
                    hand = hand * hand * (3.0 - 2.0 * hand)
                aim = [held[axis] + (end_aim[axis] - held[axis]) * hand
                       for axis in range(3)]
        fov = composition.fov + (end_fov - composition.fov) * eased
        frames.append(_row(when, position, aim, fov))
    return {
        "name": "release",
        "mode": "hook_stand",
        "subject": "pack" if subject is not None else "",
        "note": f"V33 opening: {composition.title}, one move that follows the "
                f"field onto the upper shot's own first pose",
        "cut_on": "release",
        "side": 1.0,
        "from": round(first, 6),
        "to": round(last + 1.0 / fps, 6),
        "frames": frames,
    }


def pack_centroid(replay: dict[str, Any], scale: float, fps: int = 60):
    """A `subject(t)` that returns the field's centroid in layout units.

    Every marble, unweighted: the hook shot's job is the whole field rather
    than a leader, and a weighted centroid would start telling a story about
    who is winning 0.3 s into a race whose first mechanism is 1.2 s away.
    """
    frames = replay["frames"]

    def subject(when: float):
        index = min(len(frames) - 1, max(0, int(round(when * fps))))
        marbles = frames[index]["marbles"]
        if not marbles:
            return None
        total = [0.0, 0.0, 0.0]
        for marble in marbles:
            for axis in range(3):
                total[axis] += float(marble["p"][axis]) * scale
        return [value / len(marbles) for value in total]

    return subject


def handoff_pose(next_cut: dict[str, Any], fps: int = 60):
    """The pose one frame before the next cut starts, on its own velocity.

    Extrapolated backwards rather than copied: copying makes the two frames
    either side of the join identical, which is a duplicate frame in a film
    whose QC counts them.
    """
    rows = next_cut["frames"]
    if len(rows) < 2:
        raise ValueError("the next cut has no velocity to extrapolate")
    first, second = rows[0], rows[1]
    step = [float(first[index]) - float(second[index]) for index in range(1, 8)]
    position = tuple(float(first[index]) + step[index - 1] for index in range(1, 4))
    aim = tuple(float(first[index]) + step[index - 1] for index in range(4, 7))
    fov = float(first[7]) + step[6]
    return position, aim, fov


def handoff_error(cut: dict[str, Any], next_cut: dict[str, Any],
                  fps: int = 60) -> dict[str, float]:
    """Position, aim and lens residual across the join, and the step ratio."""
    last = cut["frames"][-1]
    first = next_cut["frames"][0]
    second = next_cut["frames"][1]
    position = math.dist(last[1:4], first[1:4])
    aim = math.dist(last[4:7], first[4:7])
    inner = math.dist(first[1:4], second[1:4])
    return {
        "position": round(position, 5),
        "aim": round(aim, 5),
        "fov": round(abs(float(last[7]) - float(first[7])), 5),
        "step_ratio": round(position / inner, 4) if inner > 1.0e-9 else 0.0,
        "next_step": round(inner, 5),
    }


def rewrite_track(track: dict[str, Any], cut: dict[str, Any],
                  name: str = "release") -> dict[str, Any]:
    """`track` with one cut replaced and every other cut copied through.

    A new dict rather than a mutation, and the untouched cuts are the *same
    objects* - so a caller comparing them with the source is comparing what was
    written, not a re-serialisation of it.
    """
    out = dict(track)
    cuts = []
    replaced = 0
    for entry in track["cuts"]:
        if entry["name"] == name:
            cuts.append(cut)
            replaced += 1
        else:
            cuts.append(entry)
    if replaced != 1:
        raise ValueError(f"expected one cut named {name}, found {replaced}")
    out["cuts"] = cuts
    return out

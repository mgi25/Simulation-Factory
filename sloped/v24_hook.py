"""V24: the first three seconds, treated as the product.

The first uploaded Short was watched to 89 per cent of its length by the 19.6
per cent of viewers who stayed. Nobody who stayed got bored; four viewers in
five left before the premise arrived. So this pass is not about the race. It is
about **what is on screen at output second zero and what moves next**, and it
touches nothing else.

## What the shipped opening spends its first four seconds on

    OUTPUT  0.000 - 3.500   a course preview: an aerial flight over an empty
                            hillside. No racer is on screen at all
    OUTPUT  3.500 - 4.200   the first race frame, frozen, under PICK ONE
    OUTPUT  4.200           the film starts moving

Measured on the frame the hold freezes - `v221.START`'s own first frame, replay
0.200 - the eight racers are 81.3 px across on a 1080x1920 delivery, they sit in
a band from y 1167 to y 1291 down the left of the frame, and their bounding box
is **3.5 per cent of the picture**. The other 96.5 per cent is machine housing
and mountain. A cold viewer's first sight of a racer is four and a fifth seconds
in, at three and a half per cent of the frame, not moving.

## What this module builds instead

One continuous camera move, live from the first frame, that opens tight on the
eight bays and pulls back onto the shipped start lens as the field pours:

    OUTPUT  0.000           eight racers, large, under PICK A COLOR
    OUTPUT  0.117           the release paddles swing
    OUTPUT  0.217           the field starts to roll
    OUTPUT  ~1.2            the lens arrives on `v221.START`'s own first pose
                            and the shipped start shot carries on from there

No frame of replay is added, removed, sped up or re-seeded. Seed 5432, the
physics, the finish order, the course, the obstacle, the chase lenses, the
finish and the environment are all exactly what `v221` ships; the hook consumes
replay 0.200 to its handoff and hands the rest of that window back to the start
plan with its `live_from` moved up. Runtime after the handoff is unchanged to
the microsecond.

## Marble size is a function of one number, and it is not the field of view

    distance = 0.5 * extent / tan(fov/2)          `cameras.build_track`
    px       = 2 * radius / depth / (2 tan(fov/2)) * height

At the aim plane `depth == distance`, the tangents cancel, and

    px = 2 * radius * height / extent = 1094.4 / extent

on a 1920-tall frame with `layout.MARBLE_RADIUS` of 0.285. The field of view
cancels out entirely: widening the lens and standing further back is the same
picture. **`extent` is the whole of the size control**, and the shipped start
lens runs it at 14 because 14 layout units is the mixing machine end to end.

The eight racers at replay 0.200 span **4.41 layout units**. Framing 14 to show
a 4.4-unit subject is what put the racers at 3.5 per cent of the frame, and it
is the one number this pass moves.

## Why the aim is the field and not the drum

`cameras` aims the start lens at `machine.modules["start"].origin`, and the
field sits 3.92 layout units from it - down the apron, outside the drum the aim
is on. That offset is what pushes the pack to y 1167-1291 and 0.34 off centre
on a frame whose centre is where a phone viewer's eye rests. Aiming at the
racers' own centroid puts them at the middle of the picture by construction, and
because the centroid *travels into the drum* over the same second and a half,
the aim converges on the shipped one with nothing to blend away: 3.92 units
apart at replay 0.200 and 0.78 apart at replay 1.400.

## The join is a Hermite with a matched end slope, not a smoothstep

A smoothstep arrives with zero velocity. The shipped start shot does not begin
at rest - its orbit and dolly legs are already ramping at the first frame - so a
hook that eases to a stop on that pose would stop and then be shoved. Every
scalar here lands on a cubic Hermite with `h(0)=0, h'(0)=0, h(1)=1, h'(1)=g`,
with `g` solved per parameter from the start shot's own first-frame rate:

    g = rate_start * duration / (land - open)

so the lens arrives moving at the speed the next shot is already moving at.
`join_report` measures what came out rather than trusting it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any, Sequence

from sloped import cameras, overlays, readability, terrain, v221, v221_shuffle
from sloped.presentation import project
from sloped.scale import SIM_TO_LAYOUT

__all__ = [
    "FPS",
    "HEIGHT",
    "HOOKS",
    "LIVE_FROM",
    "WIDTH",
    "Hook",
    "Reference",
    "background_report",
    "build_hook_track",
    "build_opening_track",
    "check_hook",
    "compose",
    "control_hook",
    "decompose",
    "disc_visibility",
    "field_centroid",
    "field_span",
    "first_frame_report",
    "hook_report",
    "join_report",
    "legibility_report",
    "motion_report",
    "pick_a_color",
    "px_at_extent",
    "start_plan_for",
    "start_reference",
    "text_box",
    "text_plate",
]

FPS = 60
WIDTH, HEIGHT = 1080, 1920

# The replay second production's start window opens on, and the one every hook
# here opens on unless it says otherwise. Not 0.0: the marbles fall 0.33 sim
# units into their bays over replay 0.000-0.050 as the solver settles them, and
# that drop is a spawn artefact rather than a beat of the machine.
LIVE_FROM = 0.2


def px_at_extent(extent: float, height: int = HEIGHT) -> float:
    """A racer's diameter in pixels at the aim plane, from the extent alone.

    See the module docstring: the field of view cancels. This is the sizing
    dial, and it is exact only at the aim plane - `first_frame_report` measures
    the real projection, which spreads either side of this by the depth of the
    row.
    """
    from sloped import layout

    return 2.0 * layout.MARBLE_RADIUS * height / max(extent, 1e-6)


# --- the start's own reference frame ---------------------------------------


@dataclass(frozen=True)
class Reference:
    """The basis `cameras` measures the start lens's bearing in.

    Built from `cameras`' own helpers rather than retyped, so a bearing written
    here means the same thing as a bearing written in `cameras.SECTIONS` - and
    so `decompose` can read the shipped start pose back out as a bearing and an
    elevation that this module can interpolate.
    """

    origin: tuple[float, float, float]      # the drum, `start.origin`
    forward: tuple[float, float, float]     # the course's own heading, flattened
    side: tuple[float, float, float]        # the perpendicular the bearing swings toward


def start_reference(replay: dict[str, Any], machine) -> Reference:
    """The drum, the course heading at the start, and the terrain's open side."""
    track = cameras.progress_track(replay, machine)
    middle = min(len(track["times"]) - 1, int(round(1.0 * FPS)))
    lead = sorted(track["marbles"], key=lambda m: -track["progress"][m][middle])[0]
    heading = cameras._heading_at(machine, track["places"][lead][middle])
    flat = (heading[0], 0.0, heading[2])
    length = math.hypot(flat[0], flat[2]) or 1.0
    flat = (flat[0] / length, 0.0, flat[2] / length)
    origin = tuple(float(v) for v in machine.modules["start"].origin)
    side = terrain.lower_side(origin, flat, terrain.terrain_config())
    return Reference(origin=origin, forward=flat, side=tuple(float(v) for v in side))


def compose(
    aim: Sequence[float], bearing: float, elevation: float, reach: float,
    reference: Reference,
) -> tuple[float, float, float]:
    """`cameras._place`, with the bearing resolved in `reference`'s basis."""
    angle = math.radians(bearing)
    spun = (
        reference.forward[0] * math.cos(angle) + reference.side[0] * math.sin(angle),
        0.0,
        reference.forward[2] * math.cos(angle) + reference.side[2] * math.sin(angle),
    )
    length = math.hypot(spun[0], spun[2]) or 1.0
    spun = (spun[0] / length, 0.0, spun[2] / length)
    return cameras._place(aim, spun, elevation, reach)


def decompose(
    position: Sequence[float], aim: Sequence[float], reference: Reference,
) -> tuple[float, float, float]:
    """`(bearing, elevation, reach)` of a pose, the exact inverse of `compose`.

    This is how the hook learns where it has to land: the shipped start track is
    solved by `cameras.build_track` with its own orbit and dolly legs, and rather
    than re-derive those legs - which would be the same arithmetic written twice,
    in two places that can drift - the landing pose is read off the solved track
    and turned back into the three numbers the hook interpolates.
    """
    offset = [position[axis] - aim[axis] for axis in range(3)]
    reach = math.sqrt(sum(value * value for value in offset))
    if reach < 1e-9:
        return (0.0, 0.0, 0.0)
    elevation = math.degrees(math.asin(max(-1.0, min(1.0, offset[1] / reach))))
    flat = math.hypot(offset[0], offset[2])
    if flat < 1e-9:
        return (0.0, elevation, reach)
    spun = (offset[0] / flat, 0.0, offset[2] / flat)
    along = spun[0] * reference.forward[0] + spun[2] * reference.forward[2]
    across = spun[0] * reference.side[0] + spun[2] * reference.side[2]
    return (math.degrees(math.atan2(across, along)) % 360.0, elevation, reach)


# --- where the racers are --------------------------------------------------


def field_centroid(replay: dict[str, Any], when: float) -> tuple[float, float, float]:
    """The eight racers' mean position at a replay second, in layout units."""
    frames = replay["frames"]
    index = min(range(len(frames)), key=lambda k: abs(float(frames[k]["t"]) - when))
    points = [marble["p"] for marble in frames[index]["marbles"]]
    return tuple(
        sum(point[axis] for point in points) / len(points) * SIM_TO_LAYOUT
        for axis in range(3)
    )


def field_span(replay: dict[str, Any], when: float) -> float:
    """The widest gap between two racers at a replay second, in layout units."""
    frames = replay["frames"]
    index = min(range(len(frames)), key=lambda k: abs(float(frames[k]["t"]) - when))
    points = [
        [value * SIM_TO_LAYOUT for value in marble["p"]]
        for marble in frames[index]["marbles"]
    ]
    return max(math.dist(a, b) for a in points for b in points)


# --- the hook ---------------------------------------------------------------


def _hermite(u: float, slope: float) -> float:
    """`h(0)=0, h'(0)=0, h(1)=1, h'(1)=slope`, on the unit interval."""
    return 3.0 * u * u - 2.0 * u ** 3 + slope * (u ** 3 - u * u)


# How large an arrival slope a parameter is allowed to be solved to. A cubic
# Hermite with h'(0)=0 stays monotone up to h'(1)=3; past that it overshoots and
# the lens arrives by coming back, which is a wobble at exactly the frame the
# join is on. Anything the solve wants above this is clamped and the residual
# shows up in `join_report` as a velocity step, where it can be seen.
MAX_SLOPE = 3.0


@dataclass(frozen=True)
class Hook:
    """One opening move: a lens at frame zero and a way of leaving it.

    Everything is in the units `cameras` uses. `bearing` and `elevation` are in
    `Reference`'s basis, so `bearing=230, elevation=30` is exactly where
    `v221.START` stands and a hook written with those and the shipped extent is
    a null change that renders the shipped opening.
    """

    name: str
    # The frame-zero lens.
    bearing: float
    elevation: float
    extent: float
    fov: float = 34.0
    # Where the lens aims at frame zero, as a fraction from the racers' own
    # centroid (0.0) to the drum the shipped lens aims at (1.0), plus a lift.
    #
    # **The lift is the composition dial, and it works the way a tripod does:**
    # raising the aim tips the lens up, and the subject falls down the frame.
    # It is how the pack is put under the text rather than through it.
    aim_bias: float = 0.0
    aim_rise: float = 0.0
    # Layout units along the lens's own right, added to the aim at frame zero
    # and eased to nothing by the landing. The rig translates with it - aim and
    # position together - so it is a lateral pan and not a swing, and it leaves
    # the landing pose exactly where it was.
    #
    # **It exists because `off_centre` cannot see a horizontal miss.**
    # `readability` measures the pack's distance from the middle in half *frame
    # heights*, which is right for a 1080x1920 delivery where the vertical is
    # the tight axis on a moving shot. On a first frame it is the wrong axis: a
    # pack 120 px left of centre is a fifth of the frame's width out of place
    # and scores 0.125, which passes every bar there is. See `off_centre_x`.
    aim_pan: float = 0.0
    # The replay second the hook opens on, and how long it runs for. `opens_at`
    # later than `LIVE_FROM` is the "machine already active" variant: the
    # release paddles first move at replay 0.3167, so a hook that opens at 0.35
    # has mechanism motion in its own first frame.
    opens_at: float = LIVE_FROM
    seconds: float = 1.2
    # How much of the move is held back before it begins, as an exponent on the
    # eased parameter. 1.0 moves from the first frame; 2.0 spends the first
    # third of the hook nearly still and then goes. The tight framing is the
    # thing being bought, so it is worth dwelling on.
    lead: float = 1.6
    # Whether the aim follows the racers frame by frame or holds the pose it
    # opened on. Following is what makes the shot read as watching them.
    follow: bool = True
    note: str = ""

    def frames(self, fps: int = FPS) -> int:
        return max(1, int(round(self.seconds * fps)))

    def hands_over(self, fps: int = FPS) -> float:
        """The replay second the shipped start shot takes back over on."""
        return round(self.opens_at + self.frames(fps) / float(fps), 6)


def start_plan_for(hook: Hook, plan=None, fps: int = FPS):
    """`v221.START`, opened where the hook hands over, and **otherwise identical**.

    The omission is still 116 frames of constant-rate rotor, the resume is still
    replay 4.000, the elevation is still 30 and the handoff to the chase is still
    `v221.START_HANDOFF`. What moves is the near edge of the first window - and
    the two legs that edge would otherwise have re-timed.

    ## Why the legs have to be written out rather than left to be recomputed

    `v221_shuffle.plan_legs` hands each window the share of the whole start's
    orbit and dolly that its own *length* earns, so that the rate never changes
    across the join. That is exactly right for a plan whose two windows are the
    whole shot. It is wrong here: moving `live_from` from 0.200 to 1.400 makes
    the first window a third of its length, and the solver then spends the same
    36 degrees of orbit over the shorter remainder - which speeds the rate up
    from 7.3 to 10.8 degrees a second and moves **every frame of the shipped
    start shot after the handoff**, including all 163 frames of the post-omission
    window. Measured: up to 4.05 layout units in the first window and 3.19 in
    the second, on a shot this pass is not supposed to be touching.

    So the legs are taken from the shipped plan and only the first one's *near
    end* is moved, to the value the shipped ramp already had at the handoff:

        orbit_low' = low + (high - low) * (handoff - 0.200) / (2.050 - 0.200)

    Both windows then trace exactly the poses `v221.START` traces, over exactly
    the replay frames it traces them on, and the hook's job is to arrive at the
    one it would have been at. `tests/test_sloped_v24_hook.py` pins that as an
    equality of frame rows rather than as a tolerance.
    """
    plan = plan if plan is not None else v221.START
    handoff = hook.hands_over(fps)
    orbit, dolly = v221_shuffle.plan_legs(plan)
    first_window = v221_shuffle.window_spans(plan)[0]
    if first_window <= 0.0:
        raise ValueError("the start plan's first window is empty")
    travelled = (handoff - plan.live_from) / first_window
    if not 0.0 <= travelled < 1.0:
        raise ValueError(
            f"the hook hands over at replay {handoff}, which is outside the start "
            f"plan's first window {plan.live_from}-{plan.live_from + first_window}")

    def resume(leg: tuple[float, float]) -> tuple[float, float]:
        low, high = leg
        return (round(low + (high - low) * travelled, 6), high)

    return replace(
        plan,
        name=f"{plan.name}_{hook.name}",
        live_from=handoff,
        orbit=(resume(orbit[0]), *orbit[1:]),
        dolly=(resume(dolly[0]), *dolly[1:]),
    )


def _landing(
    start_track: dict[str, Any], reference: Reference, fps: int = FPS,
) -> tuple[dict[str, float], dict[str, float]]:
    """The start shot's opening pose and its opening rate, per parameter.

    Rate is the first-to-second-frame difference times the frame rate, which is
    the shot's own velocity at the boundary in parameter space. Both come back
    keyed the same way so `_solve_slope` can pair them.
    """
    rows = start_track["cuts"][0]["frames"]
    first, second = rows[0], rows[min(1, len(rows) - 1)]

    def read(row: Sequence[float]) -> dict[str, float]:
        position, aim = row[1:4], row[4:7]
        bearing, elevation, reach = decompose(position, aim, reference)
        return {
            "bearing": bearing, "elevation": elevation, "reach": reach,
            "fov": float(row[7]),
            "aim_x": aim[0], "aim_y": aim[1], "aim_z": aim[2],
        }

    land = read(first)
    later = read(second)
    rate = {}
    for key, value in land.items():
        step = later[key] - value
        if key == "bearing":
            step = (step + 180.0) % 360.0 - 180.0
        rate[key] = step * fps
    return land, rate


def _solve_slope(open_value: float, land: float, rate: float, seconds: float) -> float:
    """The arrival slope that makes the hook's velocity the start's velocity."""
    travel = land - open_value
    if abs(travel) < 1e-9:
        return 0.0
    return max(0.0, min(MAX_SLOPE, rate * seconds / travel))


def build_hook_track(
    replay: dict[str, Any],
    machine,
    hook: Hook,
    plan=None,
    fps: int = FPS,
    start_track: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The hook's own frames as a `cameras`-schema track, nothing else in it.

    Solved against the *shifted* start plan, because the whole point of the move
    is where it ends: the last row is the shipped start shot's own first row, so
    the two can be concatenated with no join at all. See `build_opening_track`.

    **`start_track` is the shot the hook has to arrive on, when that is not a
    `StartPlan`.** `start_plan_for` can only express the two windows a
    `StartPlan` has, and V24's start has more than two - the timeline pass omits
    inside it - so integration solves that shot itself and hands it in here. The
    hook reads exactly two things from it, the opening pose and the opening rate,
    and neither depends on how many windows follow; passing None keeps the
    prototype's own behaviour and every number in `docs/sloped_race_v24_hook.md`.
    """
    reference = start_reference(replay, machine)
    if start_track is None:
        shifted = start_plan_for(hook, plan, fps)
        start_track = v221_shuffle.build_start_track(replay, machine, shifted, fps=fps)
    land, rate = _landing(start_track, reference, fps)

    centre = field_centroid(replay, hook.opens_at)
    aim0 = [
        centre[axis] + (reference.origin[axis] - centre[axis]) * hook.aim_bias
        for axis in range(3)
    ]
    aim0[1] += hook.aim_rise
    if hook.aim_pan:
        # The lens's own right at frame zero: the horizontal perpendicular to
        # the direction it is looking, which for a camera with no roll is the
        # screen's right. `presentation.project` writes this vector the same way
        # and documents why the sign matters.
        angle = math.radians(hook.bearing)
        spun = (
            reference.forward[0] * math.cos(angle) + reference.side[0] * math.sin(angle),
            reference.forward[2] * math.cos(angle) + reference.side[2] * math.sin(angle),
        )
        length = math.hypot(*spun) or 1.0
        spun = (spun[0] / length, spun[1] / length)
        # `spun` points from the aim to the camera, so the view direction is its
        # negative and the screen right is that turned a quarter turn.
        right = (spun[1], -spun[0])
        aim0[0] += right[0] * hook.aim_pan
        aim0[2] += right[1] * hook.aim_pan
    open_values = {
        "bearing": hook.bearing, "elevation": hook.elevation,
        "reach": 0.5 * hook.extent / max(math.tan(math.radians(hook.fov) * 0.5), 1e-6),
        "fov": hook.fov,
        "aim_x": aim0[0], "aim_y": aim0[1], "aim_z": aim0[2],
    }
    # The bearing is interpolated the short way round, so `b_gate`, which opens
    # at 300 and lands on the start lens's 194, turns 106 degrees rather than
    # 254 the other way.
    turn = (land["bearing"] - open_values["bearing"] + 180.0) % 360.0 - 180.0
    land_bearing = open_values["bearing"] + turn
    land = {**land, "bearing": land_bearing}

    slopes = {
        key: _solve_slope(open_values[key], land[key], rate[key], hook.seconds)
        for key in open_values
    }

    count = hook.frames(fps)
    rows: list[list[float]] = []
    for step in range(count + 1):          # + 1: the row shared with the start
        when = round(hook.opens_at + step / float(fps), 6)
        u = min(1.0, (step / float(count)) ** hook.lead)
        values = {
            key: open_values[key] + (land[key] - open_values[key]) * _hermite(u, slopes[key])
            for key in open_values
        }
        aim = [values["aim_x"], values["aim_y"], values["aim_z"]]
        if hook.follow and u < 1.0:
            # The racers' own travel, added to the eased aim and faded out as
            # the eased aim takes over. Added rather than blended so the hook's
            # landing point is untouched by it - the start shot aims at a fixed
            # drum and a hook that arrived somewhere else would be a jump.
            drift = field_centroid(replay, when)
            opened = field_centroid(replay, hook.opens_at)
            weight = 1.0 - _hermite(u, 0.0)
            for axis in range(3):
                aim[axis] += (drift[axis] - opened[axis]) * weight
        position = compose(aim, values["bearing"], values["elevation"],
                           values["reach"], reference)
        rows.append([
            when,
            *(round(position[axis], 4) for axis in range(3)),
            *(round(aim[axis], 4) for axis in range(3)),
            round(values["fov"], 3),
        ])

    # The aim is smoothed exactly as `cameras.build_track` smooths its own, so a
    # followed aim cannot carry the replay's own sampling jitter into the lens.
    # The first and last rows are pinned afterwards: the opening composition and
    # the landing pose are both the point, and a filter is allowed to touch
    # neither.
    aims = cameras._smooth([tuple(row[4:7]) for row in rows], cameras.SMOOTH_PASSES)
    for index, row in enumerate(rows):
        if index in (0, len(rows) - 1):
            continue
        u = min(1.0, (index / float(count)) ** hook.lead)
        values_bearing = open_values["bearing"] + (land["bearing"] - open_values["bearing"]) \
            * _hermite(u, slopes["bearing"])
        values_elev = open_values["elevation"] + (land["elevation"] - open_values["elevation"]) \
            * _hermite(u, slopes["elevation"])
        values_reach = open_values["reach"] + (land["reach"] - open_values["reach"]) \
            * _hermite(u, slopes["reach"])
        aim = aims[index]
        position = compose(aim, values_bearing, values_elev, values_reach, reference)
        row[1:4] = [round(position[axis], 4) for axis in range(3)]
        row[4:7] = [round(aim[axis], 4) for axis in range(3)]

    cut = {
        "name": "hook",
        "until": "launched",
        "fov": rows[0][7],
        "extent": hook.extent,
        "elevation": hook.elevation,
        "bearing": hook.bearing,
        "target": "pack",
        "band": 60.0,
        "node": "",
        "side": 0,
        "fixed_heading": True,
        "heading_run": "",
        "from": round(hook.opens_at, 6),
        # The cut's far bound is the *shared* row's time, not its own last
        # rendered frame's. `sloped_race_scene._place_from_track` picks the
        # first cut whose `to` is at or after the wanted second, and a boundary
        # frame that falls through to the next cut and clamps to its row zero
        # duplicates a frame - `course_preview.preview_track` documents the
        # three it duplicated before it was found. Sharing the row makes both
        # readings the same pose.
        "to": rows[-1][0],
        "distance": round(open_values["reach"], 4),
        "fastest_racer": 0.0,
        "subject": sorted(range(len(replay["frames"][0]["marbles"]))),
        "lift_deg": 0.0,
        "min_clearance": 0.0,
        "frames": rows,
    }
    span = round(count / float(fps), 6)
    return {
        "units": "layout",
        "fps": fps,
        "seed": replay["seed"],
        "edited": True,
        "duration": span,
        "replay_duration": float(replay["frames"][-1]["t"]),
        "omitted": 0.0,
        "last_crossing": 0.0,
        "edit": [{"cut": "hook", "out": [0.0, span],
                  "replay": [round(hook.opens_at, 6), rows[-1][0]]}],
        "cuts": [cut],
    }


def build_opening_track(
    replay: dict[str, Any],
    machine,
    hook: Hook,
    plan=None,
    fps: int = FPS,
) -> dict[str, Any]:
    """The hook and the shipped start windows as one track, one clock.

    The output clock is rebuilt from the concatenated windows, so the film's own
    second zero is the hook's first frame and every later boundary is where the
    shipped plan puts it. Replay time is omitted, never stretched: the 116-frame
    rotor omission is the plan's and is carried through untouched.
    """
    hook_track = build_hook_track(replay, machine, hook, plan, fps)
    shifted = start_plan_for(hook, plan, fps)
    start_track = v221_shuffle.build_start_track(replay, machine, shifted, fps=fps)

    cuts = [hook_track["cuts"][0], *start_track["cuts"]]
    segments: list[dict[str, Any]] = []
    cursor = 0.0
    windows = [(hook.opens_at, hook.hands_over(fps))]
    windows += [(entry["replay"][0], entry["replay"][1]) for entry in start_track["edit"]]
    for cut, (low, high) in zip(cuts, windows):
        span = round(high - low, 6)
        segments.append({"cut": cut["name"], "out": [round(cursor, 6),
                                                     round(cursor + span, 6)],
                         "replay": [round(low, 6), round(high, 6)]})
        cursor = round(cursor + span, 6)
    covered = windows[-1][1] - windows[0][0]
    return {
        "units": "layout",
        "fps": fps,
        "seed": replay["seed"],
        "edited": True,
        "duration": round(cursor, 6),
        "replay_duration": float(replay["frames"][-1]["t"]),
        "omitted": round(max(0.0, covered - cursor), 6),
        "last_crossing": start_track.get("last_crossing", 0.0),
        "edit": segments,
        "cuts": cuts,
    }


# --- what came out ----------------------------------------------------------


def first_frame_report(
    track: dict[str, Any], replay: dict[str, Any],
    width: int = WIDTH, height: int = HEIGHT,
) -> dict[str, Any]:
    """The composition of frame zero, in the numbers the brief asks for.

    `readability.cut_reads` does the projection, which is the same arithmetic
    `cameras.frame_report` and the shipped readability bar use, so a pixel here
    is a pixel in the delivered frame.
    """
    cut = track["cuts"][0]
    row = readability.cut_reads(cut, replay, width, height, stride=1)[0]
    diameters = sorted(row["diameters"])
    bbox = row["bbox"]
    report: dict[str, Any] = {
        "t": row["t"],
        "racers": row["in_frame"],
        "of": row["of"],
        "median_px": round(readability._median(diameters), 2) if diameters else 0.0,
        "min_px": round(min(diameters), 2) if diameters else 0.0,
        "max_px": round(max(diameters), 2) if diameters else 0.0,
        "occupancy": round(row["occupancy"], 4),
        "off_centre": round(row["off_centre"], 4),
        "centroid": [round(v, 1) for v in row["centroid"]] if row["centroid"] else None,
        "bbox": [round(v, 1) for v in bbox] if bbox else None,
        "positions": {int(k): [round(v[0], 1), round(v[1], 1), round(v[2], 2)]
                      for k, v in sorted(row["racers"].items())},
    }
    if bbox:
        report["bbox_px"] = [round(bbox[2] - bbox[0], 1), round(bbox[3] - bbox[1], 1)]
        # The share of the frame's own area the eight discs cover, which is the
        # honest reading of "how much of this picture is racers". The bounding
        # box is the reading of "how much of the picture are they spread over",
        # and the two say different things - a row of eight along a diagonal has
        # a large box and a small ink share.
        report["ink"] = round(
            sum(math.pi * (d * 0.5) ** 2 for d in diameters) / float(width * height), 5
        )
        # The largest empty margin: how much of the frame lies outside the pack's
        # own box, on the side it is furthest from. A composition with the field
        # jammed into one corner reads here and nowhere else.
        report["margins"] = {
            "left": round(bbox[0] / width, 3),
            "right": round((width - bbox[2]) / width, 3),
            "top": round(bbox[1] / height, 3),
            "bottom": round((height - bbox[3]) / height, 3),
        }
        # How separable the eight are: the least centre-to-centre gap between
        # any two, in units of a racer's own diameter. Under 1.0 they overlap.
        points = list(report["positions"].values())
        gaps = [
            math.hypot(a[0] - b[0], a[1] - b[1]) / max(a[2], b[2], 1e-6)
            for index, a in enumerate(points) for b in points[index + 1:]
        ]
        report["min_separation"] = round(min(gaps), 3) if gaps else 0.0
        # The horizontal miss on its own axis, in half frame *widths*, so that
        # 1.0 is the left or right edge. `off_centre` above is `readability`'s
        # and is measured in half heights for both axes, which on a 1080x1920
        # frame under-reports a sideways miss by 16/9.
        report["off_centre_x"] = round(
            abs(report["centroid"][0] - 0.5 * width) / (0.5 * width), 4)
        visible = disc_visibility(report)
        report["disc_visible"] = visible["racers"]
        report["worst_disc"] = visible["worst"]
    return report


# What counts as movement: pixels of screen travel **between two consecutive
# frames**, on the delivered 1080x1920 at 60 fps. Two pixels a frame is 120 px a
# second, a fifth of the frame width in five seconds - plainly moving.
#
# **It is a rate and not a total, and that is the whole of the instrument.** A
# racer sitting in a shut bay is not still: the contact solver relaxes it, and
# measured through the shipped start lens the worst-creeping of the eight
# travels about half a pixel a frame indefinitely. A *cumulative* gate of any
# size a release would pass is therefore reached by creep alone a fraction of a
# second later - at eight pixels, 0.27 s, which is inside the window this pass
# is measuring and would have reported the machine "moving" before a paddle had
# stirred. A rate gate separates them by an order of magnitude: creep runs at
# 0.5 px a frame, the release paddles at about 6.
MOTION_PX = 2.0


def _screen(camera, aim, fov, point, width=WIDTH, height=HEIGHT):
    placed = project(camera, aim, fov, point, width, height)
    return None if placed is None else (placed[0], placed[1])


def motion_report(
    replay: dict[str, Any], hook: Hook, track: dict[str, Any],
    fps: int = FPS, gate: float = MOTION_PX,
) -> dict[str, Any]:
    """When the first thing moves on screen, in **output** seconds from frame 0.

    Four events, measured in projected pixels rather than in world units,
    because the brief's question is about the picture:

        mechanism   the eight release paddles, seen through the frame-0 lens
        racers      the eight marbles, seen through the frame-0 lens
        camera      the lens itself, as the screen travel of a fixed world point
        first       the earliest of the three

    The subject measures hold the camera at its opening pose on purpose. A hook
    that pulls back moves every pixel in the frame from frame one, and a measure
    that let the camera in would report 0.017 s for every variant and answer
    nothing. Holding it isolates *what the machine is doing* - and the camera's
    own contribution is then reported beside it rather than mixed into it.
    """
    frames = replay["frames"]
    times = [float(frame["t"]) for frame in frames]
    opened = min(range(len(frames)), key=lambda k: abs(times[k] - hook.opens_at))

    # The frame-zero lens, read off the solved track rather than recomputed from
    # the hook, so the projection here is the projection the renderer used.
    row = track["cuts"][0]["frames"][0]
    camera, aim, fov = tuple(row[1:4]), tuple(row[4:7]), float(row[7])

    def paddles(index: int) -> list[tuple[float, float, float]]:
        acts = frames[index]["actuators"]
        return [
            tuple(value * SIM_TO_LAYOUT for value in acts[f"start.paddle{j}"]["p"])
            for j in range(8)
        ]

    def racers(index: int) -> list[tuple[float, float, float]]:
        return [
            tuple(value * SIM_TO_LAYOUT for value in marble["p"])
            for marble in frames[index]["marbles"]
        ]

    def travel(now, before) -> float:
        worst = 0.0
        for a, b in zip(now, before):
            here = _screen(camera, aim, fov, a)
            there = _screen(camera, aim, fov, b)
            if here is None or there is None:
                continue
            worst = max(worst, math.hypot(here[0] - there[0], here[1] - there[1]))
        return worst

    out: dict[str, Any] = {"opens_at": hook.opens_at, "gate_px": gate,
                           "mechanism": None, "racers": None, "camera": None}
    previous = (paddles(opened), racers(opened))
    for index in range(opened + 1, min(len(frames), opened + 3 * fps)):
        when = round(times[index] - hook.opens_at, 6)
        now = (paddles(index), racers(index))
        if out["mechanism"] is None and travel(now[0], previous[0]) > gate:
            out["mechanism"] = when
        if out["racers"] is None and travel(now[1], previous[1]) > gate:
            out["racers"] = when
        previous = now
        if out["mechanism"] is not None and out["racers"] is not None:
            break
    # The worst per-frame creep before anything opens, so the gate's own margin
    # is a measured number in the report rather than a claim in a comment.
    creep = 0.0
    before = racers(opened)
    for index in range(opened + 1, min(len(frames), opened + int(0.1 * fps))):
        now = racers(index)
        creep = max(creep, travel(now, before))
        before = now
    out["creep_px"] = round(creep, 3)

    # The lens's own first move, read off the solved rows: how far a point at
    # the aim plane travels across the frame between two consecutive frames.
    rows = track["cuts"][0]["frames"]
    anchor = tuple(rows[0][4:7])
    for index in range(1, len(rows)):
        here = _screen(tuple(rows[index][1:4]), tuple(rows[index][4:7]),
                       float(rows[index][7]), anchor)
        there = _screen(tuple(rows[index - 1][1:4]), tuple(rows[index - 1][4:7]),
                        float(rows[index - 1][7]), anchor)
        if here is None or there is None:
            continue
        if math.hypot(here[0] - there[0], here[1] - there[1]) > gate:
            out["camera"] = round(float(rows[index][0]) - hook.opens_at, 6)
            break

    found = [value for value in (out["mechanism"], out["racers"], out["camera"])
             if value is not None]
    out["first"] = min(found) if found else None
    out["subject_first"] = min(
        [value for value in (out["mechanism"], out["racers"]) if value is not None],
        default=None)
    return out


# --- is a racer actually on screen -------------------------------------------
#
# **The start module's backboard is drawn and not collided, and `sightlines` is
# therefore blind to exactly the surface that matters here.**
#
# `sightlines.course_solids` builds its triangles from `module.local_colliders()`,
# which is the right source everywhere else on this course: a channel's acrylic
# guard, the finish gantry and the piers are all collidable. The board the eight
# racers sit against is not - the marbles rest in cradles and never touch it -
# so a ray fired from the lens to a marble's centre passes straight through it.
# Measured at two framings whose renders show four and eight racers hidden
# behind that board respectively, `Bundle.first_hit` reports **every one of the
# sixteen clear**, centre and rim alike.
#
# So visibility at the start has to be read off the picture. The measure below
# is `tools/sloped_contrast_measure.separation`'s - a racer's disc against the
# annulus of course around it, in CIELAB - with one column added: the Lab hue
# angle of the disc against the hue angle of the colour that racer is supposed
# to be. The pair is what separates the two ways of being unreadable:
#
#     low dE, any hue      the racer is the same colour as what is behind it
#     any dE, wrong hue    the disc is not the racer at all - it is the board
#
# Hue is taken in Lab rather than in HSV because the warm key light moves a
# rendered candy red from HSV hue 356 to 36, which reads as a 40-degree miss;
# in Lab the same two are 34 and 39 degrees apart from the a* axis, five.

MIN_LEGIBLE_DE = 12.0           # a difference a phone at arm's length can hold
MAX_LEGIBLE_HUE = 30.0          # degrees of Lab hue from the racer's own colour


def _lab(rgb):
    """sRGB 0-255 to CIELAB D65. `tools/sloped_contrast_measure._lab`'s."""
    import numpy as np

    srgb = np.asarray(rgb, dtype=float) / 255.0
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


def _hue(lab) -> float:
    return math.degrees(math.atan2(float(lab[2]), float(lab[1]))) % 360.0


def legibility_report(image, frame_zero: dict[str, Any]) -> dict[str, Any]:
    """Per racer on a rendered frame: is its own colour actually in the picture.

    `image` is a PIL image of the frame `frame_zero` describes, at any scale -
    the projected places are rescaled to it, so the same call answers the
    question at 1080x1920 and at the 270x480 a phone feed shows.
    """
    import numpy as np

    pixels = np.asarray(image.convert("RGB")).astype(float)
    height, width = pixels.shape[:2]
    scale = height / float(HEIGHT)
    grid_y, grid_x = np.mgrid[0:height, 0:width]
    palette = _lab(np.array(overlays.MARBLE_HUES, dtype=float))

    rows: list[dict[str, Any]] = []
    # The keys come back from JSON as strings when a report has been round
    # tripped through `hooks_<seed>.json`, and as ints when it has not.
    for raw, place in sorted(frame_zero["positions"].items(), key=lambda kv: int(kv[0])):
        key = int(raw)
        x, y, diameter = (place[0] * scale, place[1] * scale, place[2] * scale)
        radius = diameter * 0.5
        if radius < 2.0:
            rows.append({"id": key, "de": None, "hue_error": None, "legible": False})
            continue
        far = (grid_x - x) ** 2 + (grid_y - y) ** 2
        ball = far <= (radius * 0.55) ** 2
        ring = (far >= (radius * 1.60) ** 2) & (far <= (radius * 2.60) ** 2)
        if int(ball.sum()) < 4 or int(ring.sum()) < 12:
            rows.append({"id": key, "de": None, "hue_error": None, "legible": False})
            continue
        # **The median of the disc, not its mean.** A lit ball carries a small
        # blown specular highlight, and averaging it in drags the disc's colour
        # toward white and rotates its Lab hue with it - measured, by up to 30
        # degrees on the cobalt racer, which is the whole of this bar. The
        # median ignores a highlight that is a minority of the disc and reports
        # the majority of it, which is also the right answer when the majority
        # is something standing in front.
        disc = _lab(np.median(pixels[ball], axis=0))
        around = _lab(np.median(pixels[ring], axis=0))
        de = float(np.linalg.norm(disc - around))
        want = _hue(palette[key])
        got = _hue(disc)
        error = min(abs(got - want), 360.0 - abs(got - want))
        rows.append({
            "id": key,
            "de": round(de, 1),
            "hue_error": round(error, 1),
            "legible": de >= MIN_LEGIBLE_DE and error <= MAX_LEGIBLE_HUE,
        })
    legible = [row for row in rows if row["legible"]]
    return {
        "legible": len(legible),
        "of": len(rows),
        "min_de": round(min((row["de"] for row in legible), default=0.0), 1),
        "racers": rows,
    }


def disc_visibility(
    frame_zero: dict[str, Any], samples: int = 28,
) -> dict[str, Any]:
    """How much of each racer's own disc no nearer racer is standing in front of.

    **This replaces centre-to-centre spacing as the test of "can a viewer tell
    the eight apart", and it had to.** Spacing in diameters is the natural
    measure for a row seen broadside, and it is what the first version of this
    module failed two framings on - 0.73 and 0.64 diameters against a bar of
    0.90. The renders of those two framings show eight separate balls sitting in
    eight separate bays, unmistakably. The measure was wrong, not the framings:
    a row seen down its own axis stacks in *depth*, the near racer is larger and
    in front, and two centres half a diameter apart are a row in perspective
    rather than two balls in a heap.

    So the question is asked directly. The eight discs are rasterised in depth
    order on a grid inside each disc; a sample belongs to a racer if no nearer
    racer's disc contains it. The result is the share of its own silhouette each
    racer actually owns - which is the thing a viewer picks a colour off.

    It sees racers only. What the *machine* puts in front of them is not in the
    geometry a collider knows about; `legibility_report` reads that off the
    render.
    """
    places = frame_zero.get("positions") or {}
    if not places:
        return {"worst": 0.0, "racers": {}}
    order = sorted(places.items(), key=lambda kv: kv[1][2])   # nearest first
    out: dict[int, float] = {}
    for index, (key, place) in enumerate(order):
        x, y, diameter = place
        radius = diameter * 0.5
        nearer = [order[other][1] for other in range(index)]
        seen = total = 0
        for row in range(samples):
            v = (row + 0.5) / samples * 2.0 - 1.0
            for column in range(samples):
                u = (column + 0.5) / samples * 2.0 - 1.0
                if u * u + v * v > 1.0:
                    continue
                total += 1
                px, py = x + u * radius, y + v * radius
                hidden = any(
                    math.hypot(px - other[0], py - other[1]) <= other[2] * 0.5
                    for other in nearer
                )
                if not hidden:
                    seen += 1
        out[int(key)] = round(seen / total, 3) if total else 0.0
    return {"worst": round(min(out.values()), 3), "racers": dict(sorted(out.items()))}


# How far a ray is followed before the frame is called sky, in layout units.
# The course is 90 units end to end and the massif behind the start stands about
# 40 above it, so 400 reaches past both with room and stops a ray that leaves the
# world from being marched forever.
SKY_REACH = 400.0

# How finely the frame is sampled when it is classified. 36 x 64 keeps the
# 1080x1920 aspect exactly and costs about 2300 rays, which is two seconds - a
# price worth paying once per variant and not once per frame.
BACKDROP_GRID = (36, 64)

# Where the ground stops being the machine's own hillside and starts being
# scenery, in layout units of ray. See the classifier in `background_report`.
NEAR_GROUND = 25.0


def background_report(
    track: dict[str, Any], replay: dict[str, Any], bundle, cfg: dict[str, Any],
    grid: tuple[int, int] = BACKDROP_GRID, reach: float = SKY_REACH,
) -> dict[str, Any]:
    """What frame zero is made of, as shares of its own area.

    Every sample is a ray from the lens through a cell of the frame, resolved
    against three things in the order they can occlude each other: the eight
    racers as spheres, the drawn course solids through `sightlines`, and the
    terrain by marching. What no ray reaches is sky.

    **This is the brief's "empty-background share" and it is not the same
    question as occupancy.** The shipped opening's racers cover 2.0 per cent of
    the frame by area either way; what tells the two openings apart is whether
    the other 98 per cent is the machine the race is about or a hillside the
    viewer has no reason to look at.
    """
    from sloped import layout

    row = track["cuts"][0]["frames"][0]
    camera, aim, fov = tuple(row[1:4]), tuple(row[4:7]), float(row[7])
    forward = [aim[axis] - camera[axis] for axis in range(3)]
    length = math.sqrt(sum(v * v for v in forward)) or 1.0
    forward = [v / length for v in forward]
    right = [-forward[2], 0.0, forward[0]]
    span = math.hypot(right[0], right[2]) or 1.0
    right = [right[0] / span, 0.0, right[2] / span]
    up = [
        right[1] * forward[2] - right[2] * forward[1],
        right[2] * forward[0] - right[0] * forward[2],
        right[0] * forward[1] - right[1] * forward[0],
    ]
    half_up = math.tan(math.radians(fov) * 0.5)
    half_right = half_up * WIDTH / float(HEIGHT)

    index = min(range(len(replay["frames"])),
                key=lambda k: abs(float(replay["frames"][k]["t"]) - float(row[0])))
    balls = [
        tuple(value * SIM_TO_LAYOUT for value in marble["p"])
        for marble in replay["frames"][index]["marbles"]
    ]
    radius = layout.MARBLE_RADIUS

    def ball_hit(direction) -> float | None:
        best = None
        for centre in balls:
            offset = [centre[axis] - camera[axis] for axis in range(3)]
            along = sum(offset[axis] * direction[axis] for axis in range(3))
            if along <= 0.0:
                continue
            gap2 = sum(offset[axis] ** 2 for axis in range(3)) - along * along
            if gap2 > radius * radius:
                continue
            distance = along - math.sqrt(max(0.0, radius * radius - gap2))
            best = distance if best is None else min(best, distance)
        return best

    def ground_hit(direction) -> float | None:
        # Marched rather than solved: `terrain.height` has five noise octaves and
        # a bench cut in it, exactly as `terrain.clearance` says.
        step = reach / 220.0
        travelled = step
        while travelled < reach:
            point = [camera[axis] + direction[axis] * travelled for axis in range(3)]
            if point[1] <= terrain.height(point[0], point[2], cfg):
                return travelled
            travelled += step
        return None

    columns, rows_n = grid
    tally: dict[str, int] = {}
    for cy in range(rows_n):
        v = ((cy + 0.5) / rows_n) * 2.0 - 1.0
        for cx in range(columns):
            u = ((cx + 0.5) / columns) * 2.0 - 1.0
            direction = [
                forward[axis] + right[axis] * (u * half_right) - up[axis] * (v * half_up)
                for axis in range(3)
            ]
            norm = math.sqrt(sum(value * value for value in direction)) or 1.0
            direction = [value / norm for value in direction]
            target = [camera[axis] + direction[axis] * reach for axis in range(3)]

            best, label = reach, "sky"
            ball = ball_hit(direction)
            if ball is not None and ball < best:
                best, label = ball, "racer"
            solid = bundle.first_hit(camera, target)
            if solid is not None and solid[0] < best:
                best, label = solid[0], solid[1]
            ground = ground_hit(direction)
            if ground is not None and ground < best:
                best, label = ground, "terrain"
            if label == "terrain":
                # **Near ground and far ground are not the same picture.**
                # The hill the machine stands on, a few units behind the bays,
                # is a backdrop: it is dark, it is in shade, and it is what
                # makes the mark readable. The massif across the valley is
                # scenery a viewer has no reason to read. The classifier cannot
                # tell them apart by label - both are `terrain.height` - so it
                # splits them on how far the ray went, and the boundary is the
                # machine's own size: 25 layout units is a little under twice
                # the 14 the module measures end to end.
                label = "terrain" if best <= NEAR_GROUND else "terrain_far"
            tally[label] = tally.get(label, 0) + 1

    total = float(columns * rows_n)
    shares = {key: round(value / total, 4) for key, value in sorted(tally.items())}
    machine_share = sum(
        value for key, value in shares.items()
        if key in ("start", "mixer", "shuffle", "launch", "launch:piers")
    )
    return {
        "grid": [columns, rows_n],
        "shares": shares,
        "racer": shares.get("racer", 0.0),
        "machine": round(machine_share, 4),
        # Everything the race is made of: the eight and the thing they are in.
        "subject": round(shares.get("racer", 0.0) + machine_share, 4),
        "terrain_near": shares.get("terrain", 0.0),
        "terrain_far": shares.get("terrain_far", 0.0),
        "sky": shares.get("sky", 0.0),
        # What the brief calls empty background: distant hillside and sky, the
        # two things a viewer deciding whether to stay has no reason to read.
        # Near ground is not in it - see the classifier above.
        "empty": round(shares.get("terrain_far", 0.0) + shares.get("sky", 0.0), 4),
    }


def join_report(track: dict[str, Any], fps: int = FPS) -> dict[str, Any]:
    """The step across the hook's last frame and the start shot's first.

    Reported against the largest step *inside* either shot, which is the only
    fair yardstick: a join that moves the lens less than the shots move it
    themselves is not a join a viewer can find.
    """
    hook_cut, start_cut = track["cuts"][0], track["cuts"][1]
    # The hook's last *rendered* row is the one before the shared row.
    last = hook_cut["frames"][-2] if len(hook_cut["frames"]) > 1 else hook_cut["frames"][-1]
    first = start_cut["frames"][0]

    def step(a: Sequence[float], b: Sequence[float], lo: int) -> float:
        return math.dist(a[lo:lo + 3], b[lo:lo + 3])

    inside = 0.0
    aim_inside = 0.0
    for cut in (hook_cut, start_cut):
        rows = cut["frames"]
        for index in range(1, len(rows) - 1):
            inside = max(inside, step(rows[index - 1], rows[index], 1))
            aim_inside = max(aim_inside, step(rows[index - 1], rows[index], 4))
    return {
        "lens_step": round(step(last, first, 1), 4),
        "aim_step": round(step(last, first, 4), 4),
        "fov_step": round(abs(first[7] - last[7]), 4),
        "largest_inside_lens": round(inside, 4),
        "largest_inside_aim": round(aim_inside, 4),
        "shared_row_matches": hook_cut["frames"][-1][1:] == first[1:],
    }


# --- the mark ---------------------------------------------------------------

# The hook's own text. The brief is explicit that it is not PICK ONE: a cold
# viewer has to be told that the coloured balls are the choices, and "one" does
# not say that where "a colour" does.
HOOK_TEXT = "PICK A COLOR"

# The size the line is set at, and why it is not `overlays.pick_one`'s 150.
#
# PICK A COLOR is twelve glyphs against PICK ONE's eight. At 150 with the same
# 0.09 tracking it measures 1413 px on a 1080 frame - a third wider than the
# picture. 96 brings it to 904 px, an eight per cent margin each side, which is
# the margin `overlays.pick_one` was sized to. At 96 the cap height is 69 px on
# a 1920 frame, which is 17 px at the 270x480 a phone feed scrubs at.
HOOK_SIZE = 96


def pick_a_color(
    text: str = HOOK_TEXT, size: int = HOOK_SIZE, baseline: int = 395,
) -> "Any":
    """The opening mark, at a baseline this pass chooses per composition.

    `overlays.pick_one` is the same drawing with two numbers frozen into it -
    a 150 pt setting and a 395 px baseline, both measured against V20's held
    opening frame, whose racers sat at y 831-887. This opening does not put them
    there, so the baseline is an argument rather than a constant, and
    `text_plate` is where it is argued: on the rendered frame, in twelve columns,
    against the picture the mark will actually sit on.

    Drawn through `overlays._shadowed` rather than reimplemented, so the face,
    the tracking, the warm white and the soft shadow are the film's and cannot
    drift from it.
    """
    return overlays._shadowed(text, size, baseline, tracking=0.09)


def text_box(text: str = HOOK_TEXT, size: int = HOOK_SIZE) -> tuple[float, float]:
    """The set line's width and cap height in pixels, measured not guessed."""
    from PIL import Image, ImageDraw

    font = overlays.load_font(size)
    draw = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    gap = size * 0.09
    widths = [draw.textlength(char, font=font) for char in text]
    box = draw.textbbox((0, 0), text, font=font, anchor="ls")
    return (sum(widths) + gap * (len(text) - 1), float(box[3] - box[1]))


# Candidate baselines for the mark, as fractions of the frame height. The mark
# goes wherever the picture has room for it, and "room" is measured on the
# rendered frame rather than assumed - see `text_plate`. Sampled every two per
# cent of the height rather than at a handful of places, because the plate that
# works can be a narrow band between the sign above and the racers below.
TEXT_BANDS = tuple(round(0.14 + 0.02 * step, 3) for step in range(37))

# How many columns the mark's own box is scored in.
#
# **A mean contrast cannot say which letters are readable.** The first version of
# this scored the plate on its mean colour and its luma spread, and rejected two
# framings of three for "crossing a seam" - which was true and useless, because
# it could not then say where the mark should go instead. Twelve columns is one
# per glyph of PICK A COLOR: the score is the *worst* column, so a baseline
# passes only if every part of the line has something to read against.
TEXT_COLUMNS = 12

# The frame a feed actually shows. 270x480 is a quarter of the delivery in each
# axis - what `tools/sloped_contrast_measure` uses, and roughly what a Short
# occupies on a handset before anyone taps it.
PHONE_WIDTH, PHONE_HEIGHT = 270, 480

# What the mark has to clear to be readable on a phone, measured column by
# column between the warm white it is set in and the picture under it.
#
# 3.0:1 is the WCAG large-text ratio, and PICK A COLOR at 96 pt on a 1920 frame
# is 18 px of cap height at 270x480, which is large text by any reading of that
# standard. The mark also carries a blurred black shadow, so the ratio is a
# floor on the *unaided* case rather than on the delivered one.
MIN_TEXT_CONTRAST = 3.0


def _luma(pixels):
    return (0.2126 * pixels[..., 0] + 0.7152 * pixels[..., 1]
            + 0.0722 * pixels[..., 2])


def _relative_luminance(rgb) -> float:
    channels = []
    for value in rgb:
        c = float(value) / 255.0
        channels.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def text_plate(
    image, frame_zero: dict[str, Any], size: int = HOOK_SIZE,
    bands: Sequence[float] = TEXT_BANDS, clearance: int = 70,
) -> dict[str, Any]:
    """Where PICK A COLOR goes on this frame, and what it will read against.

    Every candidate baseline is scored on the rendered picture: the mark's own
    box is cut out of the frame, its mean colour gives a contrast ratio against
    `overlays.WARM_WHITE`, and its luma spread says whether the plate is one
    tone or a seam between two. Candidates that would cross the racers are
    dropped before any of that - the one thing the mark may never do is cover
    the eight things it is pointing at.

    Returns the chosen baseline and the whole scored list, so a report can show
    what was rejected rather than only what won.
    """
    import numpy as np

    pixels = np.asarray(image.convert("RGB")).astype(float)
    height, width = pixels.shape[:2]
    scale = height / float(HEIGHT)
    line_width, cap = text_box(size=size)
    left = max(0, int(round((WIDTH - line_width) * 0.5 * scale)))
    right = min(width, int(round((WIDTH + line_width) * 0.5 * scale)))
    white = _relative_luminance(overlays.WARM_WHITE)

    bbox = frame_zero.get("bbox")
    scored: list[dict[str, Any]] = []
    for band in bands:
        baseline = int(round(band * HEIGHT))
        top, bottom = baseline - cap, float(baseline)
        if bbox is not None and not (bottom + clearance < bbox[1]
                                     or top - clearance > bbox[3]):
            continue
        y0 = max(0, int(round((top - 12) * scale)))
        y1 = min(height, int(round((bottom + 12) * scale)))
        if y1 - y0 < 4 or right - left < TEXT_COLUMNS:
            continue
        patch = pixels[y0:y1, left:right]
        if patch.size == 0:
            continue
        edges = [
            left + int(round((right - left) * column / TEXT_COLUMNS))
            for column in range(TEXT_COLUMNS + 1)
        ]
        ratios = []
        for column in range(TEXT_COLUMNS):
            cell = pixels[y0:y1, edges[column]:edges[column + 1]]
            if cell.size == 0:
                continue
            mean = tuple(float(cell[..., axis].mean()) for axis in range(3))
            plate = _relative_luminance(mean)
            ratios.append((max(white, plate) + 0.05) / (min(white, plate) + 0.05))
        if not ratios:
            continue
        luma = _luma(patch)
        scored.append({
            "baseline": baseline,
            "band": band,
            "worst_column": round(min(ratios), 2),
            "mean_contrast": round(sum(ratios) / len(ratios), 2),
            "variance": round(float(luma.std()), 1),
            "mean_luma": round(float(luma.mean()), 1),
        })
    if not scored:
        chosen = {"baseline": 395, "band": 0.206, "worst_column": 0.0,
                  "mean_contrast": 0.0, "variance": 0.0}
    else:
        # The worst column first, then the higher position - a mark near the top
        # of a portrait frame is read before the picture under it. Contrast is
        # banded at a tenth of a ratio so that two plates that are equally
        # readable are separated by where they sit rather than by noise.
        chosen = max(
            scored,
            key=lambda row: (round(min(row["worst_column"], 9.0), 1), -row["band"]),
        )
    return {
        "baseline": chosen["baseline"],
        "contrast": chosen.get("worst_column", 0.0),
        "mean_contrast": chosen.get("mean_contrast", 0.0),
        "variance": chosen.get("variance", 0.0),
        "size": size,
        "width_px": round(line_width, 1),
        "cap_px": round(cap, 1),
        "phone_cap_px": round(cap * PHONE_HEIGHT / HEIGHT, 1),
        "candidates": sorted(scored, key=lambda row: -row["worst_column"])[:8],
    }


# --- the bar ----------------------------------------------------------------
#
# What a hook has to clear to be a hook. Every one of these is the brief's own
# ask turned into a number a render can fail - and every one of them is set from
# a measurement rather than from taste.

# All eight, or the premise is not on screen.
MIN_RACERS = 8

# "Substantially larger than the old map-preview opening", in pixels of the
# delivered 1080x1920. The shipped opening's median racer is 81.3 px; 110 is
# a third again of that and corresponds to an extent of about 10.
MIN_HOOK_PX = 110.0

# How much of its own silhouette the least-visible racer must own, once the
# racers in front of it are accounted for. See `disc_visibility` for why this
# is the bar and centre-to-centre spacing is not.
#
# 0.55 is a little over half a ball. Below that a racer is a crescent behind its
# neighbour and its colour is a sliver; at 0.55 and up it is a ball in a row.
# Measured: the shipped opening and variant A lose nothing at all - 1.00, the
# row being broadside to both - while B keeps 0.86 and C, square to the row
# and therefore stacking it hardest, keeps 0.77.
MIN_VISIBLE_DISC = 0.55

# Centre-to-centre spacing is still reported, because it says something the
# visibility share does not - whether the row is being seen broadside or down
# its own axis - but it is a diagnostic and not a bar.
#
# **The ceiling on it is the machine's, not the camera's.** The eight bays are
# 4.41 layout units end to end, which is 0.63 between neighbours against a racer
# diameter of 0.57 - **1.105 diameters, centre to centre, in the geometry
# itself**. No lens can do better, and the shipped opening's 0.97 is already 88
# per cent of the way there. It also means the brief's "strong colour
# separation" cannot be bought with spacing: it has to come from size and from
# each racer's own colour being on screen, which is what `MIN_HOOK_PX` and
# `legibility_report` are for.

# How far the pack's centroid may sit from the middle of the frame, in half
# frame heights - `readability.MAX_OFF_CENTRE`'s unit. 0.22 is a third of the
# shipped bar, because a race shot has to keep a moving field somewhere in the
# picture and a *first frame* is composed. The shipped opening is 0.34.
MAX_OFF_CENTRE = 0.22

# The same question on the horizontal alone, in half frame widths, where 1.0 is
# the edge. 0.22 of the width is 119 px on this frame - a miss a viewer would
# have to be looking for. The shipped opening is 0.35 out sideways and scores
# only 0.20 of the combined measure above, which is why this one exists.
MAX_OFF_CENTRE_X = 0.22

# How much of the frame is racer, by area rather than by bounding box. The
# shipped opening is 2.01 per cent; 4.0 is double it.
MIN_INK = 0.040

# How much of the frame is distant hillside or sky - the part a viewer deciding
# whether to stay has no reason to read. Near ground is excluded: the massif a
# few units behind the bays is a backdrop and is what the mark is read against.
#
# The shipped opening's number is the starkest this pass found, and it is what
# "no giant empty scenery" was written about.
MAX_EMPTY = 0.45

# Seconds of output before something in the machine moves. The brief asks for
# 0.2-0.3 and the physics gives 0.117 for free once the held frame is gone.
MAX_FIRST_MOTION = 0.30

# How many racers have to show their own colour on the rendered frame. All of
# them: a racer hidden behind the backboard is not a choice a viewer can make.
MIN_LEGIBLE = 8


def check_hook(
    frame_zero: dict[str, Any], motion: dict[str, Any],
    join: dict[str, Any] | None = None,
    backdrop: dict[str, Any] | None = None,
    legibility: dict[str, Any] | None = None,
    text: dict[str, Any] | None = None,
) -> list[str]:
    """Everything this opening fails, as sentences. Empty is a pass."""
    problems: list[str] = []
    if frame_zero["racers"] < MIN_RACERS:
        problems.append(
            f"frame 0 holds {frame_zero['racers']} racers of {frame_zero['of']}, "
            f"not {MIN_RACERS}")
    if frame_zero["median_px"] < MIN_HOOK_PX:
        problems.append(
            f"frame 0 median racer is {frame_zero['median_px']:.1f} px, "
            f"under {MIN_HOOK_PX:.0f}")
    if frame_zero.get("worst_disc", 1.0) < MIN_VISIBLE_DISC:
        worst = min(frame_zero.get("disc_visible", {1: 1.0}).items(),
                    key=lambda kv: kv[1])
        problems.append(
            f"frame 0 leaves racer {worst[0]} with {worst[1] * 100:.0f}% of its own "
            f"disc behind a nearer racer, under {MIN_VISIBLE_DISC * 100:.0f}%")
    if frame_zero["off_centre"] > MAX_OFF_CENTRE:
        problems.append(
            f"frame 0 pack sits {frame_zero['off_centre']:.2f} off centre, "
            f"over {MAX_OFF_CENTRE}")
    if frame_zero.get("off_centre_x", 0.0) > MAX_OFF_CENTRE_X:
        problems.append(
            f"frame 0 pack sits {frame_zero['off_centre_x']:.2f} of a half-width "
            f"sideways of centre, over {MAX_OFF_CENTRE_X}")
    if frame_zero.get("ink", 0.0) < MIN_INK:
        problems.append(
            f"frame 0 is {frame_zero.get('ink', 0.0) * 100:.2f}% racer by area, "
            f"under {MIN_INK * 100:.1f}%")
    first = motion.get("subject_first")
    if first is None or first > MAX_FIRST_MOTION:
        shown = "never" if first is None else f"output {first:.3f} s"
        problems.append(
            f"nothing in the machine moves until {shown}, over {MAX_FIRST_MOTION:.2f}")
    if backdrop is not None and backdrop["empty"] > MAX_EMPTY:
        problems.append(
            f"frame 0 is {backdrop['empty'] * 100:.0f}% hillside and sky, "
            f"over {MAX_EMPTY * 100:.0f}%")
    if legibility is not None and legibility["legible"] < MIN_LEGIBLE:
        lost = [row["id"] for row in legibility["racers"] if not row["legible"]]
        problems.append(
            f"frame 0 shows {legibility['legible']} racers of {legibility['of']} "
            f"in their own colour; {lost} are behind something")
    if text is not None:
        if text["contrast"] < MIN_TEXT_CONTRAST:
            problems.append(
                f"the weakest twelfth of PICK A COLOR reads at {text['contrast']:.2f}:1 "
                f"against the frame, under {MIN_TEXT_CONTRAST}:1")
    if join is not None:
        if join["lens_step"] > max(join["largest_inside_lens"] * 1.5, 0.05):
            problems.append(
                f"the handoff moves the lens {join['lens_step']:.3f} units against "
                f"{join['largest_inside_lens']:.3f} inside the shots")
        if join["fov_step"] > 0.05:
            problems.append(f"the handoff steps the field of view {join['fov_step']:.2f} deg")
    return problems


def hook_report(
    replay: dict[str, Any], machine, hook: Hook, plan=None, fps: int = FPS,
    image=None,
) -> dict[str, Any]:
    """Solve one hook and measure everything about it in one call.

    `image` is the rendered first frame, when there is one. Without it the
    report carries the geometry - sizes, places, timings, the handoff - and not
    the two things only the picture can answer: whether each racer's own colour
    is on screen at all, and what the mark will read against.
    """
    track = build_opening_track(replay, machine, hook, plan, fps)
    frame_zero = first_frame_report(track, replay)
    motion = motion_report(replay, hook, track, fps)
    join = join_report(track, fps)
    report: dict[str, Any] = {
        "name": hook.name,
        "note": hook.note,
        "hook": {
            "bearing": hook.bearing, "elevation": hook.elevation,
            "extent": hook.extent, "fov": hook.fov,
            "aim_bias": hook.aim_bias, "aim_rise": hook.aim_rise,
            "aim_pan": hook.aim_pan,
            "opens_at": hook.opens_at, "seconds": hook.seconds,
            "lead": hook.lead, "follow": hook.follow,
            "hands_over": hook.hands_over(fps),
        },
        "predicted_px": round(px_at_extent(hook.extent), 1),
        "frame_zero": frame_zero,
        "motion": motion,
        "join": join,
        "duration": track["duration"],
        "track": track,
    }
    if image is not None:
        report["legibility"] = legibility_report(image, frame_zero)
        report["text"] = text_plate(image, frame_zero)
    report["problems"] = check_hook(
        frame_zero, motion, join, backdrop=report.get("backdrop"),
        legibility=report.get("legibility"), text=report.get("text"),
    )
    return report


# --- the variants -----------------------------------------------------------
#
# Three framings, the three the brief names, plus the shipped opening rebuilt as
# a hook so the comparison is like for like rather than against a different
# module's numbers.
#
# `bearing` is in `Reference`'s basis: 0 stands downstream of the aim looking
# back up the course at the field, 180 stands behind it looking the way the
# racers will go, and the shipped start lens is at 230 - behind and round to the
# open side of the hill.

def control_hook(
    replay: dict[str, Any], machine, plan=None, name: str = "v221",
    seconds: float = 1.2, fps: int = FPS,
) -> Hook:
    """The shipped opening as a hook: a still lens on the pose V22.1 opens on.

    Read off the solved start track rather than retyped, because the shipped
    opening pose is not the numbers in `cameras.SECTIONS`. The start lens is
    written `bearing=28, elevation=16, extent=14`; `v221.START` overrides the
    elevation to 30 and the bearing to `chase_camera.START_BEARING`, and then
    `cameras.build_track` adds the first orbit leg and the first dolly leg
    before it places anything. What actually comes out at replay 0.200 is
    **bearing 194.0, elevation 30.0, reach 25.186** - an effective extent of
    15.40, not 14.

    So the control is decomposed from the render rather than asserted, and it is
    an exact null: every one of its frames is the pose V22.1 opens on, it lands
    on that pose, and the comparison table's first row is therefore the picture
    the uploaded Short actually shipped.
    """
    reference = start_reference(replay, machine)
    plan = plan if plan is not None else v221.START
    track = v221_shuffle.build_start_track(replay, machine, plan, fps=fps)
    row = track["cuts"][0]["frames"][0]
    bearing, elevation, reach = decompose(row[1:4], row[4:7], reference)
    fov = float(row[7])
    extent = 2.0 * reach * math.tan(math.radians(fov) * 0.5)
    return Hook(
        name=name, bearing=round(bearing, 4), elevation=round(elevation, 4),
        extent=round(extent, 4), fov=fov, aim_bias=1.0, aim_rise=0.0,
        opens_at=LIVE_FROM, seconds=seconds, lead=1.0, follow=False,
        note="control - the pose V22.1's start shot opens on, held",
    )


HOOKS: dict[str, Hook] = {
    # **A - the elevated rear three-quarter: the shipped family, tightened.**
    #
    # Bearing 194 is where `v221.START`'s first frame already stands, so this
    # variant turns not at all: it is a pure pull-back and a re-aim, and its
    # handoff is the smallest of the three by construction. The extent comes in
    # from an effective 15.4 to 8.2 and the aim moves off the drum on to the
    # racers, which is the whole change.
    #
    # It is the weakest of the three, and the reason is in the render rather
    # than in any number: at this bearing the lens is on the *up-course* side of
    # the bay row, so the module's own backboard stands between it and the field
    # and crosses the eight discs. Legible at elevation 26 - all eight clear -
    # and progressively less so as the lens rises: seven of eight at 40 degrees
    # and one of eight at 54, where the board covers the row outright.
    #
    # **198 rather than the shipped 194, and the four degrees are gate posts.**
    # The release stanchions stand between this lens and the row, and which
    # racer one of them is across is a sharp function of the bearing. At 194
    # with the aim on the racers the turquoise racer is more than half behind
    # one; at 204 the yellow one is, and only at a quarter of the delivery size,
    # where its disc reads 131 degrees off its own hue against 29 at full
    # resolution - a defect a 1080x1920 measure passes by one degree. Swept over
    # four bearings and three elevations, scored at **both** sizes, 198 is the
    # only bearing that holds all eight colours at both, at every elevation from
    # 22 to 30. A four-degree turn on to the start lens is the smallest of the
    # three variants by an order of magnitude.
    "a_rear": Hook(
        name="a_rear", bearing=198.0, elevation=26.0, extent=8.2,
        aim_bias=0.12, aim_rise=0.45, aim_pan=-0.20,
        seconds=1.2, lead=1.5, follow=True,
        note="A - elevated rear three-quarter, the shipped bearing tightened"),
    # **B - the front three-quarter over the gate row. The recommendation.**
    #
    # Round to the open side of the bays, where four things happen at once that
    # no rear framing gets:
    #
    #   * the backboard is *behind* the racers, so all eight read as whole balls
    #     rather than as discs crossed by a navy bar;
    #   * the course's own START sign, which faces down-course, is in the frame.
    #     It is the cheapest possible statement of the premise and it is already
    #     built - no overlay says "this is a race" as fast as a sign that does;
    #   * the backdrop is the massif in its own shade rather than the sunset, so
    #     the frame is dark behind the mark and the empty share collapses;
    #   * the apron's ribs run from the bays down to the drum, which points at
    #     where the eight are about to go.
    #
    # It costs the largest turn of the three - 106 degrees of bearing on to the
    # start lens - which is why it is the longest at 1.4 s.
    "b_gate": Hook(
        name="b_gate", bearing=300.0, elevation=30.0, extent=7.2,
        aim_bias=0.12, aim_rise=0.45, aim_pan=-0.45,
        seconds=1.4, lead=1.5, follow=True,
        note="B - front three-quarter across the gate row, under the START sign"),
    # **C - the column: the bay row run straight up a portrait frame.**
    #
    # At bearing 270 the lens is square on to the row's own axis, so the eight
    # project as a single vertical file - 148 x 701 px at this extent against
    # A's 985 x 173. It is the only framing that spends the long axis of the
    # delivery on the subject, and the eight read as a stack a thumb scrolls
    # past rather than as a line across the middle.
    #
    # Its own cost is the opposite of A's: square on to the row, the lens needs
    # elevation to see past the nearest racer to the furthest, and 38 degrees is
    # where all eight come clear - 5 of 8 at 30 and 1 of 8 at 22.
    "c_column": Hook(
        name="c_column", bearing=270.0, elevation=38.0, extent=7.6,
        aim_bias=0.12, aim_rise=0.45, aim_pan=-0.40,
        seconds=1.3, lead=1.5, follow=True,
        note="C - square to the row, eight racers up the portrait frame"),
}

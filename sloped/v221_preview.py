"""V22.1: the course preview, paced by what is in front of the lens.

V22 shipped the preview as 120 frames - 2.000 s of output - and a human watching
it on a phone read *that there is a course* and not *what the course is*. The
concept was not the problem. The clock was: eight landmarks in two seconds is a
quarter of a second each, and a quarter of a second is under the time it takes a
viewer to find a thing in a frame, let alone recognise it.

This module lengthens the shot **and spends the extra time unevenly**, which is
the whole of the idea. Playing the same flight slower would give the fork and
the empty hillside above it the same extra screen time, and the hillside does
not need any.

## What is reused and what is new

Everything that makes the picture is `sloped.course_preview`, untouched: the
course line, the corridor, the lift solver that stands the lens off the terrain,
the aim envelope, the landmark segmentation, the track writer, `path_report` and
`check_preview`. This file changes exactly one function of that solver - the map
from frame number to station along the corridor - and it changes it by
substituting `course_preview._ease` for the duration of one solve. That is the
single line the pacing lives on (`course_preview.py:721`), so substituting it is
reuse rather than a fork: with a flat density this module reproduces V22's
frames to the last decimal, and `tests/test_sloped_v221_preview.py` asserts it.

## The pacing, as a density

The shot is a monotone flight from a station near the finish to a station behind
the start. Call the fraction of that travel `q`, so `q = 0` opens on the finish
arena and `q = 1` is behind the start machine. The design input is not a speed
but a **time density** `tau(q)`: how many seconds of screen a unit of travel is
worth. Its integral, normalised, is the map from output time to travel:

    u(q) = integral(0 -> q) tau / integral(0 -> 1) tau

and the solver wants the inverse, `q(u)`, which is `_Pace`.

`tau` is 1 over generic track and rises into a Gaussian bump at each landmark, so
a landmark's *share of the shot* is very nearly `weight * sigma * sqrt(2 pi) / Z`
with `Z` the whole integral. Two end terms slow the opening and the arrival on
top of that, which is the acceleration out of the finish and the deceleration
into the start the brief asks for. Nothing here stalls: `tau` is bounded, so the
flight always has speed, and a stall is what a paused flyover looks like.

## The trap: breathing is bought from the straights

Time in the shot is conserved. Raising `Z` from 1 to about 1.9 - which is what
the dwell below costs - makes the flight **1.9 times faster over the generic
track than a uniform flight of the same length**. So a breathing preview has to
be longer than a uniform one simply to hold the straights at the same rate, and
the low-priority parts of the course are the reason the brief's longer durations
win. `pace_report` reports the flat-track rate as `flat_units_per_frame` beside
V22's own peak so the trade is a number.

## Where the shot warps, the composition has to warp with it

`course_preview` authors the lead, the lift and the aim lift as ramps over `u`,
the clock. They are really statements about the *course*: "stand high over the
middle, where the branches are thirty-six units apart", "come back down to ten
over the start so the handoff is not a plan view". Under a uniform pace those
are the same statement. Under this one they are not, and the gap is largest
exactly where it matters most. A breathing flight spends its last tenth of a
second crawling the last few units into the start, so at `u = 0.9` it is already
95.4 per cent of the way down the corridor. Read on the clock the lift ramp is
still at 15.1 there; read on the *course* it is at 11.9, on its way to the
authored 10. Leaving the ramps on the clock would therefore hold the lens three
units higher over the start machine through the whole of the arrival - and the
tail knot of 10 exists precisely because 26 made the handoff a plan view.

So `warp()` resamples each ramp's knots onto the paced clock: the new knot `j` is
the old ramp read at `q(j / (M - 1))`. Catmull-Rom through 49 knots reproduces a
5-knot ramp to within `warp_error` in the report, which is checked. The endpoint
knots are fixed points of the warp (`q(0) = 0`, `q(1) = 1`), so `cam_from` and
`cam_to` - which are built from `lead[0]` and `lead[-1]` - do not move at all.

## The handoff, and the thing V22 got very nearly right

`course_preview._blend_end` eases the tail onto one fixed pose, and because the
weight is a smootherstep its velocity at the last frame is exactly zero. The
brief asks for near-zero residual motion, and that delivers it.

But the camera that takes over is *not* stationary. `cameras.V22_START_ORBIT`
is already moving about 0.17 layout units a frame at its own frame zero,
orbiting the machine. A preview that arrives at rest therefore hands over with a
velocity step of that size - small, but it is the one discontinuity left in a
film that was built to have none.

`Rail` closes it. Instead of a fixed target the tail is eased onto the race
camera's own track *continued backwards in time*: the orbit is read in
cylindrical coordinates about its fixed aim and reflected through frame zero, so
frame -1 of the preview is where the chase camera would have been one frame
before the film starts. The last frame is still the race camera's frame zero
exactly; what changes is that the frame before it is one race-camera step away
rather than zero. Both modes are built and measured - `land="still"` is V22's
behaviour, `land="rail"` is this - and the report carries the residual against
both readings so the choice is a number rather than an opinion.
"""

from __future__ import annotations

import contextlib
import math
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Mapping, Sequence

from sloped import course_preview as cp
from sloped import terrain

Vec3 = tuple[float, float, float]

__all__ = [
    "Breath",
    "CANDIDATES",
    "DWELL",
    "Pacing",
    "Rail",
    "build",
    "check_v221",
    "pace_report",
    "preview_spec",
    "preview_track",
    "solve_pace",
    "warp",
]


# --- what a landmark is worth --------------------------------------------


@dataclass(frozen=True)
class Breath:
    """One landmark's claim on the shot.

    `weight` is how many extra seconds-per-unit-travel the lens is worth at the
    centre of the landmark, in multiples of the generic-track rate, and `sigma`
    is the half-width of that claim in units of travel fraction. Their product
    is what actually buys screen time: the landmark's share of the shot is about
    `weight * sigma * 2.5066 / Z`.
    """

    weight: float
    sigma: float


# The brief's priorities, as numbers. High priority is the finish, the split
# (which is `branches` and `fork` together - they are 0.065 of the travel apart
# and read as one idea), the mechanical obstacle, and the start. Medium is the
# merge and the main downhill turns. Low is `mixer`, the only landmark the
# brief's list of seven does not name.
#
# The sigmas are all near 0.045 because a dwell narrower than that is a hitch
# rather than a breath: at 3.2 s, 0.045 of travel is about fourteen frames of
# slowed flight either side of the centre, which is a quarter of a second of
# settle - long enough to read as the camera taking an interest and short enough
# that it never stops.
#
# `finish` and `start` carry no bump: they sit at q = 0 and q = 1 where a
# Gaussian would be half wasted outside the shot, so their time is bought by the
# two end terms of `Pacing` instead, which is also the acceleration and the
# deceleration.
DWELL: Mapping[str, Breath] = {
    "merge": Breath(0.55, 0.042),
    "branches": Breath(1.00, 0.045),
    "fork": Breath(1.10, 0.045),
    "obstacle": Breath(1.40, 0.056),
    "turns": Breath(0.75, 0.042),
    # Almost nothing, and not because the mixer is uninteresting: it sits at
    # travel 0.85, inside the skirt of the arrival term below, and was being fed
    # twice. At weight 0.25 it came out the subject for 0.50 s against the fork's
    # 0.45, which is the low-priority landmark outranking a high-priority one.
    "mixer": Breath(0.10, 0.040),
}


@dataclass
class Pacing:
    """One authored pace. Everything the clock is, as numbers."""

    seconds: float = 3.2
    fps: int = 60
    dwell: Mapping[str, Breath] = field(default_factory=lambda: dict(DWELL))
    # The opening. `ease_in` is the extra density at the very first frame and
    # `ease_in_span` how much of the travel it decays over, so it costs about
    # `ease_in * ease_in_span / 2` of the integral. This is the smooth
    # acceleration out of the finish *and* the finish's own dwell, which are the
    # same move: the shot opens on the arena and leaves it.
    ease_in: float = 2.60
    ease_in_span: float = 0.20
    # The arrival. Larger and wider than the opening because it has two jobs -
    # the start machine is a high-priority landmark and the flight has to be
    # nearly stopped when the chase camera takes it over.
    ease_out: float = 3.80
    ease_out_span: float = 0.16
    # Quadrature resolution for the density integral and its inverse. 2048 over
    # a travel of 91.7 layout units is 0.045 units a sample, two orders finer
    # than a frame moves.
    samples: int = 2048
    # How many knots the warped ramps carry. See the module docstring.
    knots: int = 49
    name: str = "v221"

    def frames(self) -> int:
        return max(int(round(self.seconds * self.fps)), 2)


# The three candidates the brief asks for.
CANDIDATES: Mapping[str, float] = {
    "preview_28": 2.8,
    "preview_32": 3.2,
    "preview_35": 3.5,
}


# Where the aim starts, as an offset from the finish node, replacing V22's -6.
#
# This is the one number of the *composition* this pass moves, and it is moved
# because the pacing could not reach the finish without it. `_segments` gives the
# finish the frames whose aim is above the finish-merge midpoint at station
# 91.29, and V22 starts the aim at 95.70 - four and a half units of corridor, or
# a fifth of a second however slowly the lens is flown. Short of stalling the
# shot there is no pacing that makes the brief's highest-priority landmark the
# subject for long enough.
#
# V22 chose -6 to keep the gaze off the finish gantry, "whose sign is a solid
# 5.4 units across standing at the deck's up-course end". Measured against the
# drawn course with `sightlines.Bundle`, that fear does not bite at any overrun
# from -6 to 0: `centre_blocked_frames` is 0 throughout and the lens never comes
# within 12.2 units of any solid, against the 2.0 it needs. -2 is taken rather
# than 0 anyway, because `centre_blocked` shortens its ray by 3 units and so
# cannot see a solid sitting exactly *on* the aim; two units of standoff keeps
# the sign out of the middle of the frame on an argument the measurement does
# not have to make.
#
#     overrun   finish is the subject for   finish's height in frame   frame visible
#       -6.0                      0.233 s                      0.173         0.480
#       -4.0                      0.317 s                      0.182         0.476
#       -2.0                      0.383 s                      0.192         0.473
#        0.0                      0.450 s                      0.203         0.469
FINISH_OVERRUN = -2.0

# And the aim's own height over the corridor at the end of the shot, V22's
# `(2.5, 4.0, 2.5)` with the tail knot raised half a unit.
#
# This is a defect the pacing *found* rather than one it caused. Flying over the
# start module the sight line grazes it: at 3.2 s, frame 142's ray passes through
# the start solid 23.73 units along its 26.83, which is 3.10 units short of the
# aim and so 0.10 inside the 3.00 `CENTRE_SHORTEN` window `check_preview` looks
# in. V22 does not trip it because at 120 frames it has no frame there - the
# grazing sits between its frames. A paced shot spends nine frames where V22
# spent four, and finds it.
#
# It is one frame, and what is in the middle of that frame is the start machine
# the shot is flying towards rather than something in the way. It is still the
# thing the bar was written to catch, so it is cleared rather than argued with:
# raising the tail knot to 3.0 lifts the aim off the module and takes the count
# to zero at all three durations, for 0.003 degrees of extra gaze turn and no
# measurable change in what is in frame.
AIM_LIFT = (2.5, 4.0, 3.0)


def preview_spec(base: cp.Preview) -> cp.Preview:
    """The V22 preview spec as this pass takes it: two numbers moved. See above."""
    return replace(base, finish_overrun=FINISH_OVERRUN, aim_lift=AIM_LIFT)


def _smootherstep(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


# --- the clock ------------------------------------------------------------


class _Pace:
    """The map from output time to travel, and back.

    Built once from a density and then read per frame. `q_of_u` is the one the
    solver wants; `u_of_q` is kept because the landmark centres are found in
    travel and reported in time.
    """

    def __init__(self, density: Callable[[float], float], samples: int) -> None:
        self.samples = samples
        step = 1.0 / samples
        values = [density(index * step) for index in range(samples + 1)]
        if min(values) <= 0.0:
            raise ValueError("the pacing density has to stay positive")
        cumulative = [0.0]
        for index in range(samples):
            cumulative.append(
                cumulative[-1] + 0.5 * (values[index] + values[index + 1]) * step
            )
        total = cumulative[-1]
        self.integral = total
        self.density = values
        self.u_grid = [value / total for value in cumulative]

    def u_of_q(self, q: float) -> float:
        q = min(max(q, 0.0), 1.0)
        scaled = q * self.samples
        index = min(int(scaled), self.samples - 1)
        t = scaled - index
        return self.u_grid[index] + (self.u_grid[index + 1] - self.u_grid[index]) * t

    def q_of_u(self, u: float) -> float:
        """Invert by bisection on the cumulative grid, then interpolate.

        The grid is monotone because the density is positive, so the bisection is
        exact to the grid and the interpolation inside a cell is the same linear
        reading `u_of_q` makes. Round-tripping is checked in the tests.
        """
        u = min(max(u, 0.0), 1.0)
        low, high = 0, self.samples
        while high - low > 1:
            middle = (low + high) // 2
            if self.u_grid[middle] <= u:
                low = middle
            else:
                high = middle
        span = self.u_grid[high] - self.u_grid[low]
        t = 0.0 if span <= 0.0 else (u - self.u_grid[low]) / span
        return (low + t) / self.samples

    def rate(self, q: float) -> float:
        """`dq/du` at a travel fraction: how fast the flight is moving there."""
        scaled = min(max(q, 0.0), 1.0) * self.samples
        index = min(int(scaled), self.samples - 1)
        return self.integral / self.density[index]


def _density_of(
    pacing: Pacing, centres: Mapping[str, float]
) -> Callable[[float], float]:
    bumps = [
        (centres[name], breath.weight, breath.sigma)
        for name, breath in pacing.dwell.items()
        if name in centres
    ]

    def density(q: float) -> float:
        value = 1.0
        for centre, weight, sigma in bumps:
            value += weight * math.exp(-0.5 * ((q - centre) / sigma) ** 2)
        value += pacing.ease_in * (
            1.0 - _smootherstep(q / max(pacing.ease_in_span, 1e-6))
        )
        value += pacing.ease_out * (
            1.0 - _smootherstep((1.0 - q) / max(pacing.ease_out_span, 1e-6))
        )
        return value

    return density


# --- solving the pace -----------------------------------------------------


def _landmark_stations(spine: cp.Line) -> dict[str, float]:
    return {name: spine.station_of(point) for name, point in cp.LANDMARKS}


def _travel(spec: cp.Preview, spine: cp.Line) -> tuple[float, float]:
    """`(cam_from, cam_to)`, exactly as `course_preview.build_preview` builds it."""
    return (
        spine.length + spec.finish_overrun - spec.lead[0],
        spec.start_overrun - spec.lead[-1],
    )


def solve_pace(
    pacing: Pacing,
    spec: cp.Preview,
    spine: cp.Line,
    rounds: int = 4,
) -> dict[str, Any]:
    """Find where each landmark falls in travel, and the clock that follows.

    The circularity is real and small: a landmark's centre is the travel
    fraction at which the *aim* is on it, the aim leads the lens by a ramp read
    on the clock, and the clock is what the centres are being solved for. Four
    rounds of substitution settle it, and the last round's movement is reported
    as `centre_shift`.
    """
    stations = _landmark_stations(spine)
    cam_from, cam_to = _travel(spec, spine)
    span = cam_to - cam_from

    def centre_of(aim_station: float, pace: "_Pace | None") -> float:
        """Travel fraction at which the aim passes `aim_station`.

        Solved on a dense sweep of the clock rather than algebraically, because
        the lead is a spline and the clock is a numeric inverse.
        """
        best, best_gap = 0.0, float("inf")
        for index in range(801):
            u = index / 800.0
            q = pace.q_of_u(u) if pace is not None else u
            lead = cp._ramp(u, spec.lead)
            aim = cam_from + span * q + lead
            gap = abs(aim - aim_station)
            if gap < best_gap:
                best, best_gap = q, gap
        return best

    centres = {name: centre_of(stations[name], None) for name in pacing.dwell}
    shifts: list[float] = []
    pace = _Pace(_density_of(pacing, centres), pacing.samples)
    for _ in range(rounds):
        updated = {name: centre_of(stations[name], pace) for name in pacing.dwell}
        shifts.append(max(abs(updated[name] - centres[name]) for name in centres))
        centres = updated
        pace = _Pace(_density_of(pacing, centres), pacing.samples)

    # The two pinned landmarks are not solved: the aim starts short of the
    # finish node by `finish_overrun` and stops on the start node, so they are
    # the two ends of the travel by construction.
    every = dict(centres)
    every["finish"] = 0.0
    every["start"] = 1.0
    return {
        "pace": pace,
        "centres": every,
        "stations": stations,
        "centre_shift": shifts[-1] if shifts else 0.0,
        "integral": pace.integral,
        "cam_from": cam_from,
        "cam_to": cam_to,
    }


# --- warping the authored composition onto the paced clock ----------------


def _warp_knots(knots: Sequence[float], pace: _Pace, count: int) -> tuple[float, ...]:
    return tuple(
        cp._ramp(pace.q_of_u(index / (count - 1)), knots) for index in range(count)
    )


def warp(spec: cp.Preview, pacing: Pacing, pace: _Pace) -> cp.Preview:
    """`spec` with its ramps re-read against travel instead of against the clock.

    `seconds` and `fps` come from the pacing, everything else from the authored
    V22 spec. The endpoint knots are fixed points, so the flight still begins and
    ends at exactly the stations V22's did.
    """
    return replace(
        spec,
        seconds=pacing.seconds,
        fps=pacing.fps,
        lead=_warp_knots(spec.lead, pace, pacing.knots),
        lift=_warp_knots(spec.lift, pace, pacing.knots),
        aim_lift=_warp_knots(spec.aim_lift, pace, pacing.knots),
        name=pacing.name,
    )


def warp_error(spec: cp.Preview, warped: cp.Preview, pace: _Pace) -> dict[str, float]:
    """How far the resampled ramps sit from the profiles they stand in for."""
    out: dict[str, float] = {}
    for name in ("lead", "lift", "aim_lift"):
        original = getattr(spec, name)
        rebuilt = getattr(warped, name)
        worst = 0.0
        for index in range(1001):
            u = index / 1000.0
            worst = max(
                worst, abs(cp._ramp(u, rebuilt) - cp._ramp(pace.q_of_u(u), original))
            )
        out[name] = round(worst, 5)
    return out


# --- the handoff ----------------------------------------------------------


class Rail:
    """The race camera's own track, readable at negative frame offsets.

    Offset 0 is the race's first frame. Negative offsets are the orbit continued
    backwards: the pose is taken to cylindrical coordinates about the aim -
    radius, bearing and height - and reflected through frame zero, which is exact
    for a constant-rate orbit about a fixed point and is what the start shot is.
    A straight reflection of the Cartesian position would bend the continuation
    the wrong way round the machine.
    """

    def __init__(self, rows: Sequence[Sequence[float]]) -> None:
        if len(rows) < 2:
            raise ValueError("a rail needs at least two race frames")
        self.rows = [tuple(float(value) for value in row) for row in rows]

    @property
    def first(self) -> tuple[Vec3, Vec3]:
        row = self.rows[0]
        return (row[1:4], row[4:7])

    @property
    def fov(self) -> float:
        """The race camera's own field of view at its first frame."""
        return self.rows[0][7]

    def _cylindrical(self, index: int) -> tuple[float, float, float, Vec3]:
        row = self.rows[min(index, len(self.rows) - 1)]
        position, aim = row[1:4], row[4:7]
        dx, dz = position[0] - aim[0], position[2] - aim[2]
        return (math.hypot(dx, dz), math.atan2(dx, dz), position[1] - aim[1], aim)

    def pose(self, offset: int) -> tuple[Vec3, Vec3]:
        """`(position, aim)` `offset` frames from the race's first frame."""
        if offset >= 0:
            row = self.rows[min(offset, len(self.rows) - 1)]
            return (row[1:4], row[4:7])
        radius0, bearing0, height0, aim0 = self._cylindrical(0)
        radius, bearing, height, aim = self._cylindrical(-offset)
        turn = (bearing - bearing0 + math.pi) % (2.0 * math.pi) - math.pi
        back_bearing = bearing0 - turn
        back_radius = 2.0 * radius0 - radius
        back_height = 2.0 * height0 - height
        back_aim = tuple(2.0 * aim0[axis] - aim[axis] for axis in range(3))
        return (
            (
                back_aim[0] + back_radius * math.sin(back_bearing),
                back_aim[1] + back_height,
                back_aim[2] + back_radius * math.cos(back_bearing),
            ),
            back_aim,
        )

    def step(self) -> tuple[float, float]:
        """The race camera's own first positional step and gaze turn."""
        (p0, a0), (p1, a1) = self.pose(0), self.pose(1)
        return (math.dist(p0, p1), turn_between(p0, a0, p1, a1))


def turn_between(p0: Vec3, a0: Vec3, p1: Vec3, a1: Vec3) -> float:
    """Degrees between two gaze directions, each given as a lens and an aim."""
    first = cp._unit(tuple(a0[axis] - p0[axis] for axis in range(3)))
    second = cp._unit(tuple(a1[axis] - p1[axis] for axis in range(3)))
    dot = min(1.0, max(-1.0, sum(first[axis] * second[axis] for axis in range(3))))
    return math.degrees(math.acos(dot))


# How many frames before the race's first the rail is followed for.
#
# The trade is between a hitch and a tilt, and both ends of it are visible in the
# measurement. The static blend brings the flight nearly to rest at the last
# frame; the rail correction then has to bring it back up to the race camera's
# own 0.170 units a frame. Too short a horizon and those two happen one after the
# other, so the lens slows almost to a stop and then speeds up again into the
# handoff. Too long and the correction reaches back into frames where the blend
# is still moving the lens a long way, and it costs tilt. At 3.2 s:
#
#     horizon   slowest step in the tail   worst tilt in a frame
#          30                     0.021                   0.696
#          45                     0.039                   0.696
#          60                     0.064                   0.696
#          80                     0.098                   0.773
#         100                     0.124                   0.966
#
# Sixty is the last horizon that costs no tilt at all, and it leaves the slowest
# moment of the settle at 0.064 against the 0.170 it arrives on - a flight that
# eases and then firms up, not one that stops and restarts. Reported as
# `handoff.tail_dip`, because it is a residual and not a zero.
RAIL_HORIZON = 60


def _weight(u: float, window: float) -> float:
    """The static blend's own weight at a clock fraction. Zero before it opens."""
    window = max(window, 1e-6)
    if u < 1.0 - window:
        return 0.0
    return _smootherstep((u - (1.0 - window)) / window)


def _land(frames: list[dict[str, Any]], window: float, pose: tuple[Vec3, Vec3]) -> None:
    """Ease the tail of a solved flight onto one fixed pose.

    `course_preview._blend_end`, reimplemented here only so that `_rail_tail` can
    be layered on the same weight. Given the same window and pose it produces the
    same frames, which `tests/test_sloped_v221_preview.py` pins against the
    shipped function.
    """
    target_position, target_aim = pose
    for frame in frames:
        weight = _weight(frame["u"], window)
        if weight <= 0.0:
            continue
        frame["position"] = tuple(
            frame["position"][axis]
            + (float(target_position[axis]) - frame["position"][axis]) * weight
            for axis in range(3)
        )
        frame["aim"] = tuple(
            frame["aim"][axis] + (float(target_aim[axis]) - frame["aim"][axis]) * weight
            for axis in range(3)
        )


# How many frames the field of view takes to land, separately from the flight's
# own `RAIL_HORIZON`. A lens has no inertia, so this is not chosen for smoothness
# - it is chosen to stay inside the frames where the start machine is already the
# subject. Sixty frames at 2.8 s reaches back to 0.64 of the shot, narrows the
# frame while the *turns* are still the subject, and pushes them out of it
# entirely: `check_preview` reported "never in frame: turns". Forty stays inside
# the start and mixer segments at all three durations.
FOV_HORIZON = 40


def _fov_land(
    frames: list[dict[str, Any]],
    target: float,
    window: float,
    horizon: int = FOV_HORIZON,
) -> None:
    """Ease the preview's field of view onto the race camera's.

    **The handoff V22 measured as exact is not exact.** Its last preview row and
    the race's first row carry the same position and the same aim to four
    decimals - and 48 degrees against 34. The renderer takes the field of view
    from the row it is playing (`sloped_race_scene.gd:461`), so the film cuts
    from a 48-degree lens to a 34-degree one on a frame where nothing else
    changes, which is a zoom snap of 1.45x in the image. Nothing in the V22
    report looks at the eighth column, so nothing caught it.

    It is closed the same way the velocity is: over the last `horizon` frames,
    on the product of the rail fade and the landing weight, so the ramp starts
    with zero slope and lands exactly on the race's own number. What it buys
    besides continuity is a move - a wide lens that tightens onto the machine as
    the flight settles, which is what "arrive behind the racers" looks like.
    """
    last = len(frames) - 1
    for index, frame in enumerate(frames):
        offset = index - last
        if offset < -horizon:
            continue
        weight = _smootherstep(1.0 + offset / float(horizon)) * _weight(
            frame["u"], window
        )
        if weight <= 0.0:
            continue
        frame["fov"] = frame["fov"] + (target - frame["fov"]) * weight


def _rail_tail(
    frames: list[dict[str, Any]],
    rail: Rail,
    window: float,
    horizon: int = RAIL_HORIZON,
) -> None:
    """Bend the last `horizon` frames onto the race camera's backward continuation.

    Applied *after* `_land`, and as an offset from the pose `_land` arrived at,
    so the two never fight: the correction is

        (rail.pose(offset) - rail.pose(0)) * fade(offset) * land_weight(u)

    which is zero at the last frame - the pose the film hands over on does not
    move - and zero `horizon` frames earlier, both with zero slope, because
    `fade` is a smootherstep. What it is not zero at is the *velocity* of the
    last frame: `fade` is flat there, so the correction's rate is the rail's own
    rate, and the preview arrives travelling at exactly the speed the chase
    camera leaves at.

    The naive version of this - handing `_land` a moving target over its whole
    window - reads the rail hundreds of frames before the race starts, where the
    orbit's backward continuation is nonsense and the blend drags the middle of
    the shot toward it. Measured at 3.2 s that cost 1.30 degrees of tilt in a
    frame against the 1.00 allowed. Bounding it at `horizon` costs 0.00.
    """
    last = len(frames) - 1
    base_position, base_aim = rail.first
    for index, frame in enumerate(frames):
        offset = index - last
        if offset < -horizon:
            continue
        fade = _smootherstep(1.0 + offset / float(horizon))
        weight = fade * _weight(frame["u"], window)
        if weight <= 0.0:
            continue
        position, aim = rail.pose(offset)
        frame["position"] = tuple(
            frame["position"][axis] + (position[axis] - base_position[axis]) * weight
            for axis in range(3)
        )
        frame["aim"] = tuple(
            frame["aim"][axis] + (aim[axis] - base_aim[axis]) * weight
            for axis in range(3)
        )


# --- building -------------------------------------------------------------


@contextlib.contextmanager
def _paced(pace: _Pace):
    """Substitute the solver's one pacing function for the length of one solve.

    `course_preview.build_preview` reads `_ease` exactly once per frame, at
    `course_preview.py:721`, to turn the frame's clock fraction into its travel
    fraction. Replacing it is therefore the whole of the change, and everything
    downstream - the lift solve, the aim envelope, the segmentation, the report -
    runs on the paced flight without knowing it was paced.
    """
    original = cp._ease
    cp._ease = lambda u, strength: pace.q_of_u(u)
    try:
        yield
    finally:
        cp._ease = original


def build(
    pacing: Pacing,
    spec: cp.Preview,
    rail: Rail | None = None,
    land: str = "rail",
    end_blend: float | None = None,
    horizon: int = RAIL_HORIZON,
    line: cp.Line | None = None,
    spine: cp.Line | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Solve one paced preview.

    Returns `course_preview.build_preview`'s shape plus a `pace` entry carrying
    the clock, the landmark centres and what the warp cost.

    `land` is `"rail"` (the tail meets the race camera already moving at its own
    rate), `"still"` (V22's behaviour - the tail arrives at rest) or `"none"`
    (no handoff at all, for measuring what the blend costs).
    """
    line = line if line is not None else cp.course_line()
    spine = spine if spine is not None else cp.corridor(line)
    cfg = cfg if cfg is not None else terrain.terrain_config()

    solution = solve_pace(pacing, spec, spine)
    pace: _Pace = solution["pace"]
    warped = warp(spec, pacing, pace)
    # The handoff is applied here rather than by the solver, so that the target
    # may move; `end_pose` is cleared before the solve and restored into the
    # returned spec for the report.
    bare = replace(warped, end_pose=None)
    with _paced(pace):
        solved = cp.build_preview(bare, line=line, spine=spine, cfg=cfg)

    blend = warped.end_blend if end_blend is None else end_blend
    if land != "none":
        if rail is not None:
            pose = rail.first
        elif spec.end_pose is not None:
            pose = (tuple(spec.end_pose[0]), tuple(spec.end_pose[1]))
        else:
            raise ValueError("landing needs a rail or an end_pose")
        _land(solved["frames"], blend, pose)
        if land == "rail":
            if rail is None:
                raise ValueError('land="rail" needs a rail')
            _rail_tail(solved["frames"], rail, blend, horizon)
            _fov_land(solved["frames"], rail.fov, blend)

    solved["spec"] = replace(
        warped,
        end_pose=(rail.first if rail is not None else spec.end_pose),
        end_blend=blend,
    )
    solved["pace"] = {
        **{key: value for key, value in solution.items() if key != "pace"},
        "clock": pace,
        "land": land,
        "warp_error": warp_error(spec, warped, pace),
        "pacing": pacing,
    }
    return solved


def preview_track(solved: dict[str, Any], seed: int = 0) -> dict[str, Any]:
    """`course_preview.preview_track`, with the field of view read per frame.

    The shipped writer puts `spec.fov` in every row because V22's preview has one
    field of view all the way through. This one does not - see `_fov_land` - so
    the eighth column is rewritten from the solved frames, matched by time. The
    cuts, their bounds, the shared boundary rows and every other column are the
    shipped writer's, untouched.
    """
    track = cp.preview_track(solved, seed=seed)
    by_time = {round(frame["t"], 6): frame["fov"] for frame in solved["frames"]}
    for cut in track["cuts"]:
        for row in cut["frames"]:
            row[7] = round(by_time[round(row[0], 6)], 3)
        cut["fov"] = row[7]
    return track


# --- measuring ------------------------------------------------------------


# V22's own worst frame-to-frame station travel, computed from its shipped spec:
# 120 frames over the same 91.7 units of corridor, eased at 0.45, whose peak rate
# is 1.394 times the mean. The straights of a paced flight are compared against
# it, because a preview that crosses generic track faster than V22 ever crossed
# anything has spent its breathing badly.
V22_PEAK_STEP = 1.074

# What this pass will accept as a duration, replacing `course_preview`'s
# 1.5-2.2 s. The bounds are the brief's own 2.8 and 3.5 with a frame of slack.
DURATION_RANGE = (2.78, 3.52)

# The brief's three priority tiers, and the screen time each one buys.
#
# Screen time is measured on `course_preview._segments` - the frames whose *gaze*
# is on a thing - and not on `path_report`'s "is it anywhere in frame", which on
# a shot aimed down-course is generous to the point of meaninglessness: the
# finish node is inside the frustum for all 3.2 seconds of a 3.2-second shot.
#
# **`branches` and `fork` are one subject.** The brief's high-priority list says
# "split / two routes", which is one idea with two landmark points in it, and the
# two are 0.065 of the travel apart - closer than either is to anything else. The
# segmentation splits them because it tiles by nearest landmark; the floor does
# not, and reads their sum. Held apart, `branches` cannot pass: its segment is
# bounded by the midpoints to `merge` and to `fork` and is 6.9 units of corridor
# wide, the narrowest of the eight, so no pacing short of a stall gets it to a
# third of a second on its own.
#
# The numbers: 0.42 s for a high-priority subject is about the floor for finding
# and recognising an unfamiliar object on a phone; 0.30 for a medium one, which
# is enough to read a shape that has already been established. The low tier has
# no floor at all - `mixer` is the one landmark the brief's list of seven does
# not name, and the check below is that it does not *outrank* a high-priority
# one, which is the failure it actually had.
SUBJECT_TIERS: Mapping[str, tuple[float, tuple[str, ...]]] = {
    "finish": (0.42, ("finish",)),
    "split": (0.60, ("branches", "fork")),
    "obstacle": (0.42, ("obstacle",)),
    "start": (0.42, ("start",)),
    "merge": (0.30, ("merge",)),
    "turns": (0.30, ("turns",)),
}
LOW_PRIORITY = ("mixer",)

# How many frames at the end of the shot count as the approach to the handoff.
HANDOFF_FRAMES = 12


def subject_seconds(solved: dict[str, Any]) -> dict[str, float]:
    """Seconds each landmark is the thing the gaze is on.

    `course_preview._segments` tiles the shot by which landmark the aim is
    nearest, so this is the segmentation the contact sheet and the rendered cuts
    already use, read as a duration.
    """
    fps = solved["spec"].fps
    return {
        name: round((last - first + 1) / fps, 4)
        for name, first, last in cp._segments(solved)
    }


def handoff_report(solved: dict[str, Any], rail: Rail | None) -> dict[str, Any]:
    """What the last of the preview does, and how near the race camera it lands.

    Three separate questions, which V22's single "the poses match" hid:

    * **Pose.** How far the last preview frame is from the race camera's first,
      in position and in aim. Zero is the target and the blend delivers it.
    * **Residual motion.** How fast the lens is still travelling and turning as
      it arrives, over the last `HANDOFF_FRAMES`. The brief asks for near zero.
    * **Continuity.** The difference between the preview's last step and the race
      camera's first. This is the number a viewer can actually see, and it is
      *not* minimised by arriving at rest - the race camera is already moving.
    """
    frames = solved["frames"]
    tail = frames[-HANDOFF_FRAMES - 1:]
    steps = [
        math.dist(tail[index]["position"], tail[index - 1]["position"])
        for index in range(1, len(tail))
    ]
    turns = [
        turn_between(
            tail[index - 1]["position"], tail[index - 1]["aim"],
            tail[index]["position"], tail[index]["aim"],
        )
        for index in range(1, len(tail))
    ]
    # How slow the flight gets over the last second before it arrives. The
    # settle is not monotone - see `RAIL_HORIZON` - and this is the bottom of it.
    settle = [
        math.dist(frames[index]["position"], frames[index - 1]["position"])
        for index in range(max(len(frames) - 60, 1), len(frames))
    ]
    out: dict[str, Any] = {
        "tail_frames": HANDOFF_FRAMES,
        "tail_dip": round(min(settle), 5),
        "last_step": round(steps[-1], 5),
        "last_turn": round(turns[-1], 5),
        "mean_tail_step": round(sum(steps) / len(steps), 5),
        "max_tail_step": round(max(steps), 5),
        "max_tail_turn": round(max(turns), 5),
    }
    if rail is None:
        return out
    race_step, race_turn = rail.step()
    position, aim = rail.first
    out.update(
        {
            "race_first_step": round(race_step, 5),
            "race_first_turn": round(race_turn, 5),
            "pose_delta": round(math.dist(frames[-1]["position"], position), 6),
            "aim_delta": round(math.dist(frames[-1]["aim"], aim), 6),
            # Positive means the preview arrives faster than the race leaves.
            "velocity_residual": round(steps[-1] - race_step, 5),
            "turn_residual": round(turns[-1] - race_turn, 5),
            # The column V22 never looked at. See `_fov_land`.
            "race_fov": round(rail.fov, 3),
            "last_fov": round(frames[-1]["fov"], 3),
            "fov_delta": round(frames[-1]["fov"] - rail.fov, 4),
            "max_fov_step": round(
                max(
                    abs(frames[index]["fov"] - frames[index - 1]["fov"])
                    for index in range(1, len(frames))
                ),
                4,
            ),
        }
    )
    return out


def pace_report(
    solved: dict[str, Any],
    bundle: Any | None = None,
    rail: Rail | None = None,
    stride: int = 2,
) -> dict[str, Any]:
    """`course_preview.path_report` plus everything the pacing adds.

    The base report is not re-derived: every motion, visibility and clearance
    number in it is the shipped measurement, run over the paced frames.
    """
    report = cp.path_report(solved, bundle=bundle, stride=stride)
    pace = solved["pace"]
    clock: _Pace = pace["clock"]
    frames = solved["frames"]
    fps = solved["spec"].fps

    # The aim has to run monotonically down-course, or `_segments` tiles wrongly
    # and, worse, the gaze visibly backs up. Breathing is what puts this at risk:
    # the aim leads the lens by a ramp, and where the lens slows hard the ramp's
    # own rise can outrun it.
    aims = [frame["aim_station"] for frame in frames]
    rises = [aims[index] - aims[index - 1] for index in range(1, len(aims))]
    report["max_aim_rise"] = round(max(rises), 5)
    report["aim_monotone"] = bool(max(rises) <= 0.0)

    travel = abs(pace["cam_to"] - pace["cam_from"])
    report["travel"] = round(travel, 3)
    report["pace_integral"] = round(clock.integral, 4)
    # Station travelled in a frame where the density is flat, which is the
    # generic track. `rate` is dq/du and a frame is 1/(N-1) of u.
    report["flat_units_per_frame"] = round(
        travel * clock.integral / (len(frames) - 1), 4
    )
    report["v22_peak_step"] = V22_PEAK_STEP
    report["centres"] = {
        name: round(value, 4) for name, value in pace["centres"].items()
    }
    report["centre_seconds"] = {
        name: round(clock.u_of_q(value) * (len(frames) - 1) / fps, 3)
        for name, value in pace["centres"].items()
    }
    report["centre_shift"] = round(pace["centre_shift"], 6)
    report["warp_error"] = pace["warp_error"]
    report["land"] = pace["land"]
    report["subject_seconds"] = subject_seconds(solved)
    report["handoff"] = handoff_report(solved, rail)

    # Where the shot is slowest and fastest, as a ratio, so "it breathes" is a
    # number rather than a claim. One is a uniform flight.
    steps = [
        math.dist(frames[index]["position"], frames[index - 1]["position"])
        for index in range(1, len(frames))
    ]
    report["breath_ratio"] = round(max(steps) / max(min(steps), 1e-9), 2)
    # The motion itself, one number a frame, so a sheet can draw the pacing
    # rather than assert it.
    report["step_series"] = [round(value, 4) for value in steps]
    drops = [-rise for rise in rises]
    report["station_rate_ratio"] = round(max(drops) / max(min(drops), 1e-9), 2)
    return report


def check_v221(report: dict[str, Any]) -> list[str]:
    """What in `pace_report`'s numbers a viewer could see as a defect.

    `course_preview.check_preview`'s whole bar, minus its duration clause - which
    is V22's 1.5-2.2 s and is the thing this pass is deliberately outside - plus
    the four the pacing introduces.
    """
    problems = [
        problem
        for problem in cp.check_preview(report)
        if not problem.startswith("duration ")
    ]
    low, high = DURATION_RANGE
    if not low <= report["duration"] <= high:
        problems.append(
            f"duration {report['duration']:.2f} s is outside the breathing "
            f"pass's {low:.2f}-{high:.2f} s"
        )
    if not report["aim_monotone"]:
        problems.append(
            f"the gaze backs up the course by {report['max_aim_rise']:.3f} units "
            "in a frame: the lead outruns a slowed lens"
        )
    if report["flat_units_per_frame"] > V22_PEAK_STEP:
        problems.append(
            f"the flight crosses generic track at "
            f"{report['flat_units_per_frame']:.3f} units a frame, faster than "
            f"V22's worst moment ({V22_PEAK_STEP:.3f}): the breathing is being "
            "paid for out of the parts a viewer still has to track through"
        )
    subject = report["subject_seconds"]
    for label, (floor, parts) in SUBJECT_TIERS.items():
        seconds = sum(subject.get(part, 0.0) for part in parts)
        if seconds < floor:
            problems.append(
                f"the {label} is the subject for {seconds:.3f} s, under the "
                f"{floor:.2f} s it needs to be recognised"
            )
    leanest_high = min(
        sum(subject.get(part, 0.0) for part in parts)
        for floor, parts in SUBJECT_TIERS.values()
        if floor >= 0.42
    )
    for name in LOW_PRIORITY:
        if subject.get(name, 0.0) > leanest_high:
            problems.append(
                f"{name} is the subject for {subject[name]:.3f} s, longer than a "
                "high-priority landmark: the pacing is feeding empty track"
            )
    worst = max(report["warp_error"].values())
    if worst > 0.05:
        problems.append(
            f"a warped ramp sits {worst:.3f} layout units from the profile it "
            "stands in for: raise Pacing.knots"
        )
    return problems

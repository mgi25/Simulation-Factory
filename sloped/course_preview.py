"""The V22 opening: two seconds of course, travelled backwards, ending behind the racers.

The brief is a pre-race course preview of the kind a party game puts in front
of a round - the viewer is shown the map before anyone runs it - compressed to
what a vertical Short can carry. It begins at the finish arena, retreats up the
course past the landmarks the race will use, and settles above and behind the
start machine, pointing the way the marbles are about to go.

## The move, and why it is the only one that fits

The obvious way to travel a course backwards is to fly up it looking where you
are going. On this course that camera is unwatchable, and the reason is
arithmetic rather than taste. Layout B is a zig-zag: measured on the drawn
centreline the plan heading of its sections runs 68 degrees on the sprint, -19
between the branches, 41 on leg 3, -48 on leg 2, 48 on leg 1 and 63 on the
launch - about 350 degrees of accumulated yaw. A camera that takes its facing
from the course covers that in the two seconds the preview has, which is 175
degrees a second of rotation. Nothing survives that.

So the camera **faces down-course for the whole shot and travels up-course**: a
reverse dolly. Its motion is very nearly anti-parallel to its own gaze, so what
the frame does is open out rather than swing, and every degree of rotation in
the finished path comes from the curve of the flight line rather than from the
course's turns. Three things fall out of it for free:

* It begins looking **at** the finish arena rather than past it, because the
  arena is down-course of where the camera starts.
* Each landmark enters the frame from the bottom and recedes up it, which is
  the one direction a 1080x1920 frame has to spare. `sloped.cameras` found the
  same thing for the race: looking along the channel puts the ribbon receding
  up the frame.
* It arrives **behind the start** facing **down the launch** with no turn at
  the end at all. A camera that flew up the course looking forward would have
  to swing 180 degrees in the last half second to get there.

## The corridor

The flight line is not the course. It is the centreline convolved with a wide
Gaussian - wide enough that the zig-zag flattens into a single curve down the
fall line - with the two ends pinned back onto the start and finish nodes so
the shot still begins and ends over the right places. `CORRIDOR_SIGMA` is in
layout units and is the one number that trades the flight's smoothness against
how closely it hugs the track; `path_report` returns how far the corridor
strays from the ribbon so the trade can be seen rather than guessed.

The aim rides the same corridor, a `lead` ahead of the camera. Aiming at the
*course* instead was tried and is wrong twice: the aim darts into every hairpin,
and between the fork and the merge there are two ribbons and the aim would have
to pick one. On the corridor it passes between the lobes, which is what a shot
of a split has to look at.

The corridor cuts across ground the course goes around, so both the camera and
the aim are held above the higher of the corridor's own height and the terrain
under them. `sloped.terrain`'s lesson applies unchanged: an aim under the
mountain is not fixed by moving the camera.

## What is checked

`check_preview` is the whole of the quality bar and it is deliberately not the
race's. A race camera is judged on whether the field is legible; this one has
no field. It is judged on whether the move is watchable and whether the lens
stays out of the scenery:

* position step, and separately the **lateral** step - the part of the motion
  across the gaze rather than along it, which is the part that costs a viewer
  something
* the angular step of the look direction
* the sight line's clearance over the terrain, and the lens's distance from any
  drawn surface, through `sloped.sightlines`
* how much of the course is inside the frustum, and which landmarks are seen
* that the gaze never approaches vertical, because the renderer's `look_at`
  takes +Y as up and a shot looking straight down has no defined roll

Nothing here changes physics, the race, the seed or any production camera. The
preview is written as a camera track in the format `sloped_race_scene.gd`
already reads, so it renders through the shipped pipeline with no change to it.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from typing import Any, Sequence

from sloped import layout, terrain
from sloped.pathing import arc_lengths, resample
from sloped.track import TrackRun

__all__ = [
    "Vec3",
    "LANDMARKS",
    "CORRIDOR_SIGMA",
    "LINE_SAMPLES",
    "Preview",
    "PREVIEW",
    "Line",
    "course_line",
    "branch_midline",
    "corridor",
    "build_preview",
    "preview_track",
    "write_track",
    "frozen_replay",
    "path_report",
    "check_preview",
    "MAX_STEP",
    "MAX_ACROSS_STEP",
    "MAX_RISE_STEP",
    "MAX_TURN",
    "MAX_YAW",
    "MAX_PITCH",
    "SIGHT_MARGIN",
    "LENS_MARGIN",
    "MIN_GAZE_TO_VERTICAL",
    "DURATION_RANGE",
    "CENTRE_SHORTEN",
    "LANDMARK_SIZE",
]

Vec3 = tuple[float, float, float]


# --- what the preview has to show ----------------------------------------
#
# The brief names eight things the viewer should recognise. Each is a point in
# layout units and each names one segment of the finished track, so
# `--stills=fork` renders the frame whose aim is passing the fork. They are
# listed in **race** order; the preview visits them backwards.
#
# `turns` is leg 1's apex rather than leg 2's west hairpin: both are hairpins,
# leg 1's is the outer one and the one the zig-zag reads from, and leg 2's is
# four units from the obstacle node and would have given two landmarks in one
# frame.
LANDMARKS: tuple[tuple[str, Vec3], ...] = (
    ("start", layout.NODES["start"]),
    ("mixer", layout.NODES["mix"]),
    ("turns", (18.80, 24.00, -16.00)),
    ("obstacle", layout.NODES["obstacle"]),
    ("fork", layout.NODES["split"]),
    ("branches", (0.00, 8.00, 27.00)),
    ("merge", layout.NODES["merge"]),
    ("finish", layout.NODES["finish"]),
)

# How wide the smoothing kernel on the centreline is, in **layout units of arc**.
#
# The trade it makes is between how much the flight turns and how far it strays
# from the track, and the trade is very one-sided. Measured on this course, the
# corridor's total plan-heading swing and its mean distance from the nearest
# ribbon come out:
#
#     sigma   swing   mean stray   worst stray   length
#        26   73.4         3.85          9.59    106.7
#        32   52.5         4.07         10.10    104.0
#        40   35.3         4.31         10.52    102.5
#        50   22.6         4.61         10.98    101.7
#        64   12.2         4.94         11.50    101.3
#
# Fifty-odd degrees of swing buys three quarters of a layout unit of stray. At
# 26 the residual of leg 1 and leg 2's zig-zag survived the blur as a 73-degree
# S near the top of the course, and the shot spent it in half a second: measured
# frame by frame the gaze yawed 2.6 degrees a frame there, against a pitch that
# never moved more than 0.38. Fifty flattens that S to 23 degrees over the whole
# two seconds and the flight becomes one curve, which is what the brief means by
# purposeful rather than drone-like.
CORRIDOR_SIGMA = 50.0

# How many samples the course line carries. 480 over ~196 units is 0.41 units a
# sample, comfortably finer than the 1.88-unit channel, so the corridor is a
# curve rather than a chain of chords.
LINE_SAMPLES = 480


# --- quality bar ----------------------------------------------------------
#
# Not the race camera's numbers. `sloped.cameras.MAX_CAMERA_STEP` is 1.2 layout
# units a frame for a lens orbiting a subject at twenty-odd units, where the
# whole step is across the gaze. Here almost all of it is *along* the gaze - a
# dolly out, which reads as the frame opening rather than as the world sliding -
# so the total is allowed to be larger and the lateral part is held much tighter.
# The shipped V21 race track, measured over all 1145 of its frames, moves the
# lens at most 0.504 layout units in a frame and turns the gaze at most 0.132
# degrees. That is a camera whose subject moves and which therefore barely does;
# a preview has to cross 102 units of corridor in two seconds and cannot be held
# to it. What it can be held to is the *shape* of the motion, and for that the
# step is resolved into the frame's own axes:
#
# * `along` - toward or away from what is being looked at. A dolly. It reads as
#   the frame opening out and costs a viewer almost nothing, so it is not capped.
# * `rise` - up or down the frame. On a flyover this is the reveal itself: the
#   course sliding up the frame is the shot working.
# * `across` - left or right. This is the one that reads as the world sliding
#   sideways, and it is the one held tight.
#
# The angles are split the same way and for the same reason: a steady pitch with
# the yaw doing the work is a pan, and a pan is what makes a viewer ill.
MAX_STEP = 1.60                 # layout units per frame, total
MAX_ACROSS_STEP = 0.55          # layout units per frame, screen-horizontal
MAX_RISE_STEP = 1.30            # layout units per frame, screen-vertical
MAX_TURN = 1.20                 # degrees per frame of look direction
MAX_YAW = 1.00                  # degrees per frame, 60 a second
MAX_PITCH = 1.00                # degrees per frame
SIGHT_MARGIN = 0.60             # `sloped.cameras.SIGHT_MARGIN`, unchanged
LENS_MARGIN = 2.00              # `sloped.sightlines.LENS_CLEARANCE`, unchanged
# `look_at(aim, Vector3.UP)` is undefined when the gaze is vertical and jittery
# near it. Twenty degrees of margin is about twelve times the worst turn allowed.
MIN_GAZE_TO_VERTICAL = 20.0
# The brief: "approximately 1.5-2.2 seconds", and a preview is not a cinematic.
DURATION_RANGE = (1.5, 2.2)


# --- an arc-parameterised polyline ---------------------------------------


class Line:
    """A polyline addressed by arc length, which extrapolates past both ends.

    The extrapolation is the point of it. The camera ends behind the start and
    its aim may be asked for past the finish, and both of those are off the
    course; a line that clamped instead would park the lens on the last sample
    for the frames that matter most.
    """

    __slots__ = ("points", "arc")

    def __init__(self, points: Sequence[Sequence[float]]) -> None:
        self.points: list[Vec3] = [tuple(float(v) for v in point) for point in points]
        if len(self.points) < 2:
            raise ValueError("a line needs at least two points")
        self.arc: list[float] = arc_lengths(self.points)

    @property
    def length(self) -> float:
        return self.arc[-1]

    def _span(self, station: float) -> tuple[int, int, float]:
        if station <= 0.0:
            return 0, 1, station / max(self.arc[1], 1e-9)
        if station >= self.length:
            last = len(self.points) - 1
            span = max(self.arc[last] - self.arc[last - 1], 1e-9)
            return last - 1, last, 1.0 + (station - self.length) / span
        low, high = 0, len(self.arc) - 1
        while high - low > 1:
            middle = (low + high) // 2
            if self.arc[middle] <= station:
                low = middle
            else:
                high = middle
        span = max(self.arc[high] - self.arc[low], 1e-9)
        return low, high, (station - self.arc[low]) / span

    def at(self, station: float) -> Vec3:
        low, high, t = self._span(station)
        a, b = self.points[low], self.points[high]
        return tuple(a[axis] + (b[axis] - a[axis]) * t for axis in range(3))

    def tangent(self, station: float) -> Vec3:
        low, high, _ = self._span(station)
        a, b = self.points[low], self.points[high]
        delta = tuple(b[axis] - a[axis] for axis in range(3))
        size = math.sqrt(sum(value * value for value in delta)) or 1.0
        return tuple(value / size for value in delta)

    def station_of(self, point: Sequence[float]) -> float:
        """The arc length of the sample nearest `point`. How a landmark is placed."""
        best, at = math.inf, 0
        for index, sample in enumerate(self.points):
            gap = math.dist(sample, point)
            if gap < best:
                best, at = gap, index
        return self.arc[at]

    def nearest(self, point: Sequence[float]) -> float:
        """Distance from `point` to the nearest sample."""
        return min(math.dist(sample, point) for sample in self.points)


# --- the course, as one line ---------------------------------------------


def branch_midline(count: int = 118) -> list[Vec3]:
    """Blue and orange averaged, sample for sample, at equal arc length.

    Between the fork and the merge the course is two ribbons thirty-six layout
    units apart at their widest, and a single flight line has to run between
    them: a corridor down either lobe points the camera at that lobe with the
    other one out of frame, which is the fault `sloped.cameras._pack_aim`
    records for the race's own merge shot.
    """
    blue = resample(TrackRun("blue").path, count)
    orange = resample(TrackRun("orange").path, count)
    return [
        tuple((blue[index][axis] + orange[index][axis]) * 0.5 for axis in range(3))
        for index in range(count)
    ]


def course_line(samples: int = LINE_SAMPLES) -> Line:
    """The whole race from the start node to the finish node, as one polyline.

    The drawn runs, in flow order, with the two branch lobes replaced by their
    midline and the two authored nodes on the ends - the start module sits about
    four units back from the launch's first sample and the finish deck about
    five on from the sprint's last, and a preview that began and ended on the
    channel would begin and end just short of the two things it is there to show.
    """
    points: list[Vec3] = [tuple(float(v) for v in layout.NODES["start"])]
    for name in ("launch", "leg1", "leg2", "leg3"):
        points.extend(tuple(float(v) for v in point) for point in TrackRun(name).path)
    points.extend(branch_midline())
    points.extend(tuple(float(v) for v in point) for point in TrackRun("final").path)
    points.append(tuple(float(v) for v in layout.NODES["finish"]))
    # Consecutive runs share their join sample exactly, and a zero-length span
    # is a division by nothing for `arc_lengths`' users.
    trimmed: list[Vec3] = [points[0]]
    for point in points[1:]:
        if math.dist(point, trimmed[-1]) > 1e-6:
            trimmed.append(point)
    return Line(resample(trimmed, samples))


def _gaussian(values: Sequence[float], sigma_samples: float,
              radius: int | None = None) -> list[float]:
    """A Gaussian blur with the ends held, which is what `smooth_series` is not.

    `sloped.pathing.smooth_series` box-blurs three taps at a time; the width
    wanted here is about sixty samples, and sixty box passes over 480 points is
    both slow and a worse kernel than one convolution.

    `radius` truncates the kernel. Left alone it is three sigma, which is the
    whole of the Gaussian worth having; `_envelope` narrows it deliberately.
    """
    if sigma_samples <= 0.0:
        return list(values)
    if radius is None:
        radius = int(math.ceil(sigma_samples * 3.0))
    radius = max(1, radius)
    kernel = [
        math.exp(-0.5 * (offset / sigma_samples) ** 2)
        for offset in range(-radius, radius + 1)
    ]
    total = sum(kernel)
    kernel = [weight / total for weight in kernel]
    count = len(values)
    out: list[float] = []
    for index in range(count):
        acc = 0.0
        for step, weight in enumerate(kernel):
            at = min(max(index + step - radius, 0), count - 1)
            acc += values[at] * weight
        out.append(acc)
    return out


def _envelope(values: Sequence[float], dilate: int, sigma: float) -> list[float]:
    """A smooth series that is nowhere below `values`.

    Dilate, then blur. The dilation is what makes the blur safe: a maximum
    filter over a window `dilate` wide raises every sample to its neighbourhood's
    peak, and a kernel that reaches no further than that window cannot then pull
    the result back under the original. Blurring alone would sag at exactly the
    peak the requirement is at, which is the one place it may not.

    **The kernel is truncated at the dilation width, and that is what makes the
    guarantee a guarantee rather than a hope.** A Gaussian's natural reach is
    three sigma; with sigma 9 and a dilation of 16 it reaches 27 samples either
    side, so at the middle of a 33-sample plateau eleven of its taps are still
    outside and the output comes back under the requirement. Written this way
    the plateau is always at least as wide as the kernel, so its centre is the
    weighted mean of a constant and comes out exactly equal to it - whatever
    `dilate` and `sigma` are set to.
    """
    count = len(values)
    grown = [
        max(values[max(index - dilate, 0) : index + dilate + 1]) for index in range(count)
    ]
    return _gaussian(grown, sigma, radius=dilate)


def corridor(line: Line, sigma: float = CORRIDOR_SIGMA) -> Line:
    """`line` flattened into a flight corridor, with both ends pinned back on.

    Holding the end samples during the blur is not enough: a clamped kernel
    still drags the first and last points a long way toward the interior, and
    the two points this shot most has to be over are exactly those. So the
    residual at each end is spread back over the whole curve as a linear ramp,
    which restores both endpoints exactly and leaves the middle as smooth as the
    blur made it.
    """
    spacing = line.length / max(len(line.points) - 1, 1)
    sigma_samples = sigma / max(spacing, 1e-9)
    axes = [
        _gaussian([point[axis] for point in line.points], sigma_samples)
        for axis in range(3)
    ]
    count = len(line.points)
    head = tuple(line.points[0][axis] - axes[axis][0] for axis in range(3))
    tail = tuple(line.points[-1][axis] - axes[axis][-1] for axis in range(3))
    fixed: list[Vec3] = []
    for index in range(count):
        u = index / max(count - 1, 1)
        fixed.append(
            tuple(
                axes[axis][index] + head[axis] * (1.0 - u) + tail[axis] * u
                for axis in range(3)
            )
        )
    return Line(fixed)


# --- the shot -------------------------------------------------------------


def _ramp(u: float, knots: Sequence[float]) -> float:
    """A value from evenly spaced knots over u in [0, 1], splined not kinked.

    Catmull-Rom with the end knots duplicated, so the curve passes through every
    knot and has no corner at any of them - a corner in the lift profile is a
    corner in the flight path, and the report would show it as a step in `rise`.

    Any number of knots from one up. Three was enough for the lead and is not
    enough for the lift: the shot wants to be high over the middle of the course
    and low again behind the start, and three symmetric knots cannot say that.
    """
    values = [float(value) for value in knots]
    if len(values) == 1:
        return values[0]
    spans = len(values) - 1
    scaled = min(max(u, 0.0), 1.0) * spans
    index = min(int(scaled), spans - 1)
    t = scaled - index
    p0 = values[max(index - 1, 0)]
    p1 = values[index]
    p2 = values[index + 1]
    p3 = values[min(index + 2, spans)]
    return 0.5 * (
        2.0 * p1
        + (p2 - p0) * t
        + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t * t
        + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t * t * t
    )


def _ease(u: float, strength: float) -> float:
    """Normalised progress, eased at both ends without stalling the middle.

    A pure smootherstep peaks at 1.875 times the average rate, which on a shot
    this short is a lurch through the middle of the course. Blended with the
    straight line at `strength` it peaks at `1 + 0.875 * strength`, and the
    default of 0.55 comes out at 1.48 - enough of a settle at each end to read
    as a move that was started and stopped rather than cut into.
    """
    smooth = u * u * u * (u * (u * 6.0 - 15.0) + 10.0)
    return u + (smooth - u) * strength


@dataclass
class Preview:
    """One authored preview. Everything the shot is, as numbers.

    The distances are layout units and the angles degrees, which is what every
    other camera in this package speaks.
    """

    seconds: float = 2.0
    fps: int = 60
    # Vertical, because `course_scene.gd` keeps the frame's height. On a
    # 1080x1920 frame this is 27.9 degrees across, which is the narrow axis and
    # the reason a shot aimed along the course reads and one aimed across it
    # does not.
    fov: float = 48.0
    # Camera-to-aim distance along the corridor, as knots evenly spaced over the
    # shot. It grows through the middle because that is where the course is
    # widest - the two branch lobes are thirty-six layout units apart - and
    # closes again at the start, where the subject is one fourteen-unit machine.
    lead: tuple[float, ...] = (26.0, 32.0, 22.0)
    # How far the lens stands above the corridor, before `_solve_lift` raises it
    # over anything in the way. The two ends are equal by intent: the shot opens
    # on one arena and closes on one machine, and both want the same scale.
    #
    # **This is much lower than it first looks like it should be, and the reason
    # is that the course is already downhill.** The corridor falls 37.85 layout
    # units over 106.7 of arc, so a lens and an aim at the *same* height above it
    # are already looking down at 20.8 degrees. The extra depression a lift buys
    # is `atan((lift - aim_lift + 0.355 * lead) / (0.935 * lead))`, and at a lead
    # of 34 a lift of 30 puts the gaze 48 degrees down - which is a plan view,
    # and worse than that, it turns the flight into a lateral move: a camera
    # travelling horizontally under a gaze depressed 48 degrees spends 74 per
    # cent of every step across its own sight line instead of along it, and
    # across is the part that costs a viewer something. At 12 the gaze sits near
    # 32 degrees and the same flight is 53 per cent along.
    #
    # The back half is higher than the front, and that is a composition finding
    # rather than a geometric one. With the lift flat at 13 the last four
    # landmark frames came back with 35 to 48 per cent of a 1080x1920 frame as
    # unlit mountain above the course: the camera is high on the hillside by
    # then and a gaze depressed only 37 degrees still has the massif in the top
    # of the frame. Carrying the lift to 26 tips the gaze far enough down that
    # the course fills the frame instead, and it costs nothing measurable - the
    # extra motion lands in `rise`, which on a flyover is the reveal.
    #
    # **The middle wants height and the end does not, so this has five knots.**
    # With the lift flat at 13 the last four landmark frames came back with 35
    # to 48 per cent of a 1080x1920 frame as unlit mountain above the course:
    # the lens is high on the hillside by then and a gaze depressed only 37
    # degrees still has the massif in the top of the frame. Carrying it to 26
    # tips the gaze down until the course fills the frame instead. But holding
    # 26 to the end put the lens 31.5 units over the start node at 18 across -
    # a 60-degree look straight down onto the machine, which is not what
    # "behind the racers" means and not a pose any chase camera can take over
    # from. The tail comes back to 10, which lands the handoff 25.9 layout units
    # out at 38.8 degrees of elevation - about where the shipped race's own
    # `start` cut stands, at 25 - and the elevation of the handoff is then a
    # number this file chooses rather than one the middle of the shot leaves
    # behind.
    #
    # It cannot be a *low* angle whatever this says, because everywhere behind
    # the start is uphill: the crest over the start rises 5.5 units and the
    # western flank another 17, and the lens has to stand `GROUND_GAP` over
    # whichever of them it is on.
    lift: tuple[float, ...] = (14.0, 22.0, 27.0, 24.0, 10.0)
    # And how far above it the aim sits, so the gaze is not buried in the slope.
    aim_lift: tuple[float, ...] = (2.5, 4.0, 2.5)
    # A fixed lateral offset of the flight line, eased in and out over the shot,
    # in layout units. Positive is the corridor's own left. A pure axial dolly is
    # flat, and a few units of drift give the course some parallax without
    # turning the shot into an orbit.
    #
    # It is the single largest consumer of the sideways budget, and cheap to
    # read off. Measured over the whole flight, as the ratio of travel along the
    # gaze to travel across it, and the worst sideways step:
    #
    #     sway   along/across   worst across   ribbon in frame
    #      0.0          12.18          0.169            43.1%
    #      2.0           6.56          0.258            43.9%
    #      4.0           4.37          0.347            44.8%
    #      6.0           3.26          0.434            45.3%
    #
    # Six units buys two percentage points of visibility for three quarters of
    # the sideways budget, and the argument this shot rests on is that it is a
    # dolly. Three keeps the drift and keeps the argument.
    sway: float = 3.0
    # A firmer settle than the middle of the range, because the last thing this
    # shot does is hand over: at 0.65 the flight is down to a third of its mean
    # rate by the final frame, which reads as arriving rather than as being cut
    # away from.
    ease: float = 0.65
    # Where the shot has to end, as (position, aim) in layout units. `None` lets
    # the reverse dolly finish where it finishes, which is already behind and
    # above the start looking down the launch. Integration passes the V22 chase
    # camera's own first pose here; `path_report` says what the blend cost in
    # angle and step, and `check_preview` fails it if it cost too much.
    end_pose: tuple[Vec3, Vec3] | None = None
    # Reported, never enforced: the elevation in degrees the handoff comes out
    # at, above the horizontal through the aim. See `path_report`.
    # How long the blend onto `end_pose` takes, as a fraction of the shot.
    end_blend: float = 0.32
    # Where the aim starts, as an offset from the finish node along the
    # corridor. Negative holds it short of the deck, which puts the arena in the
    # upper third of the frame with the run-in below it - and keeps the gaze off
    # the finish gantry, whose sign is a solid 5.4 units across standing at the
    # deck's up-course end.
    finish_overrun: float = -6.0
    # And where the aim finishes, as a station on the corridor. Zero is the start
    # node itself; the aim stops on the start module rather than running behind it.
    start_overrun: float = 0.0
    name: str = "preview"

    def frames(self) -> int:
        return max(int(round(self.seconds * self.fps)), 2)


PREVIEW = Preview()


def _unit(vector: Sequence[float]) -> Vec3:
    size = math.sqrt(sum(float(v) * float(v) for v in vector)) or 1.0
    return tuple(float(v) / size for v in vector)


def _left_of(tangent: Sequence[float]) -> Vec3:
    """The horizontal perpendicular of a heading, taken once and never re-asked.

    `terrain.lower_side` would answer per frame and `sloped.cameras.Cut.side`
    records what that costs: where the two sides are within a metre of each
    other the verdict flips and the lens moves seven units in one frame. The
    corridor's sway has a sign written into it instead.
    """
    flat = _unit((tangent[0], 0.0, tangent[2]))
    return (flat[2], 0.0, -flat[0])


# How far either side of a frame a lift correction is carried before it is
# blurred, in frames, and how hard it is blurred afterwards. Wide enough that
# raising the lens over one ridge is a swell in the flight path rather than a
# bump in it.
LIFT_DILATE = 16
LIFT_SIGMA = 9.0
LIFT_ROUNDS = 8

# How far the lens has to stand over the ground under it, on top of whatever the
# sight line asks for. Roughly nine marble diameters: near enough to read as a
# camera on the mountain, far enough that no terrace lip scrapes the lens.
GROUND_GAP = 5.0

# The same pair for the aim's own height. Narrower, because the aim may follow
# the ground more closely than the lens may - it is a point to look at, not a
# place to stand - and a wide envelope there would lift the gaze off the track.
AIM_DILATE = 8
AIM_SIGMA = 5.0


def _solve_lift(rows: Sequence[dict[str, Any]], cfg: dict[str, Any]) -> list[float]:
    """The authored lift, raised wherever the ground gets too near the shot.

    Two requirements solved as one: the sight line has to clear the terrain by
    `SIGHT_MARGIN`, and the lens itself has to stand `GROUND_GAP` over the
    ground beneath it.

    **The ground is not allowed into the flight path directly.** The first solve
    of this module took the lens height as `max(corridor, ground) + lift`, which
    is right frame by frame and produces a path that wears the mountain's own
    shape: measured on the reference flight, the crest above the start moved the
    lens 3.7 layout units in one frame and put a 1.84-degree kink in the gaze,
    both over budget, and the dip on the far side of it cost 1.9 units of
    lateral travel a frame. So the corridor's own height is the base - it is
    smooth by construction - and the ground reaches the shot only through here.

    `sloped.cameras` raises the *elevation* two degrees at a time until the line
    is clear, one frame at a time and independently, which is right for a cut
    that holds one bearing and wrong for a continuous flight: the frames either
    side of a raised one are not raised and the path steps. So the requirement
    is measured per frame, then **dilated** over a window and blurred, and a
    correction becomes a swell that starts before the obstruction and ends after
    it. Blurring alone would dip back under the requirement at its own peak;
    dilating first is what leaves the blur headroom to spend.
    """
    lift = [float(row["lift"]) for row in rows]
    count = len(rows)
    for _ in range(LIFT_ROUNDS):
        deficit = [0.0] * count
        worst = 0.0
        for index, row in enumerate(rows):
            height = row["cam_base"] + lift[index]
            position = (row["cam_xz"][0], height, row["cam_xz"][1])
            short = GROUND_GAP - (height - row["ground"])
            gap = terrain.clearance(position, row["aim"], cfg, samples=40)
            if gap < SIGHT_MARGIN:
                # The sight line is a chord; raising the near end by d raises its
                # lowest point by something between 0 and d, so the shortfall is
                # asked for with headroom rather than solved for.
                short = max(short, (SIGHT_MARGIN - gap) * 1.6 + 0.2)
            if short > 0.0:
                deficit[index] = short
                worst = max(worst, short)
        if worst <= 0.0:
            break
        smoothed = _envelope(deficit, LIFT_DILATE, LIFT_SIGMA)
        lift = [lift[index] + smoothed[index] for index in range(count)]
    return lift


def _blend_end(frames: list[dict[str, Any]], spec: Preview) -> None:
    """Ease the tail of the solved flight onto an explicit final pose.

    The weight is a smootherstep over the last `end_blend` of the shot, so the
    blend's own velocity is zero where it starts - the solved path is not
    deflected at the join - and zero where it ends, which is what lets the race
    camera take over without a step.
    """
    target_position, target_aim = spec.end_pose
    window = max(spec.end_blend, 1e-6)
    for frame in frames:
        u = frame["u"]
        if u < 1.0 - window:
            continue
        t = (u - (1.0 - window)) / window
        weight = t * t * t * (t * (t * 6.0 - 15.0) + 10.0)
        frame["position"] = tuple(
            frame["position"][axis]
            + (float(target_position[axis]) - frame["position"][axis]) * weight
            for axis in range(3)
        )
        frame["aim"] = tuple(
            frame["aim"][axis] + (float(target_aim[axis]) - frame["aim"][axis]) * weight
            for axis in range(3)
        )


def build_preview(
    spec: Preview = PREVIEW,
    line: Line | None = None,
    spine: Line | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Solve the shot: a position, an aim and a field of view per frame.

    Returned in the shape the rest of this module and `path_report` want; call
    `preview_track` for the JSON `sloped_race_scene.gd` reads.
    """
    line = line if line is not None else course_line()
    spine = spine if spine is not None else corridor(line)
    cfg = cfg if cfg is not None else terrain.terrain_config()

    count = spec.frames()
    # **The camera's own station is what is eased, not the aim's.** The lead
    # varies through the shot, so driving the aim instead makes the camera's
    # speed the eased aim speed *minus* the lead's rate of change: on the first
    # solve, with the lead bulging 26 to 52 and back, that came out at 1.5
    # layout units a frame through the first half and 0.3 through the last,
    # which spent the final six-tenths of a two-second shot nearly stationary.
    cam_from = spine.length + spec.finish_overrun - spec.lead[0]
    cam_to = spec.start_overrun - spec.lead[-1]

    rows: list[dict[str, Any]] = []
    for index in range(count):
        u = index / (count - 1)
        cam_station = cam_from + (cam_to - cam_from) * _ease(u, spec.ease)
        aim_station = cam_station + _ramp(u, spec.lead)

        left = _left_of(spine.tangent(cam_station))
        # Eased in and out so the drift starts and ends on the corridor itself,
        # which is what keeps the two pinned ends over the two nodes.
        drift = spec.sway * math.sin(math.pi * u)

        foot = spine.at(cam_station)
        aim_foot = spine.at(aim_station)
        cam_xz = (foot[0] + left[0] * drift, foot[2] + left[2] * drift)
        aim_ground = terrain.height(aim_foot[0], aim_foot[2], cfg)

        rows.append(
            {
                "u": u,
                "t": index / spec.fps,
                "aim_station": aim_station,
                "cam_station": cam_station,
                "cam_xz": cam_xz,
                # The corridor's own height, which is smooth. The ground reaches
                # the flight only through `_solve_lift`. See there.
                "cam_base": foot[1],
                "ground": terrain.height(cam_xz[0], cam_xz[1], cfg),
                "lift": _ramp(u, spec.lift),
                "aim_xz": (aim_foot[0], aim_foot[2]),
                # Raw, and smoothed into an envelope below: the ground under the
                # aim has terraces in it, and taking the higher of it and the
                # corridor frame by frame steps. Measured on the first solve the
                # step was 2.0 layout units of aim height in one frame, which
                # pitched the gaze 2.12 degrees in that frame - the worst turn in
                # the shot, and a one-frame flick rather than a move.
                "aim_base": max(aim_foot[1], aim_ground),
                "aim_lift": _ramp(u, spec.aim_lift),
            }
        )

    aim_base = _envelope(
        [row["aim_base"] for row in rows], AIM_DILATE, AIM_SIGMA
    )
    for row, base in zip(rows, aim_base):
        row["aim"] = (row["aim_xz"][0], base + row["aim_lift"], row["aim_xz"][1])

    lift = _solve_lift(rows, cfg)
    frames: list[dict[str, Any]] = []
    for row, height in zip(rows, lift):
        frames.append(
            {
                "t": row["t"],
                "u": row["u"],
                "position": (row["cam_xz"][0], row["cam_base"] + height, row["cam_xz"][1]),
                "aim": row["aim"],
                "fov": spec.fov,
                "lift": height,
                "aim_station": row["aim_station"],
                "cam_station": row["cam_station"],
            }
        )

    if spec.end_pose is not None:
        _blend_end(frames, spec)
    return {
        "spec": spec,
        "line": line,
        "spine": spine,
        "cfg": cfg,
        "frames": frames,
        "duration": (count - 1) / spec.fps,
    }


# --- the track ------------------------------------------------------------


def _segments(solved: dict[str, Any]) -> list[tuple[str, int, int]]:
    """One named window per landmark, bounded by where the aim passes it.

    The aim runs monotonically from the finish to the start, so the landmarks
    tile the shot by construction and a still of `fork` is the frame whose gaze
    is on the fork rather than one taken near it. Names come out in the order
    the preview visits them, which is the reverse of the race's.
    """
    spine: Line = solved["spine"]
    frames = solved["frames"]
    stations = sorted(
        ((name, spine.station_of(point)) for name, point in LANDMARKS),
        key=lambda entry: entry[1],
        reverse=True,
    )
    # The boundary between two landmarks is the midpoint of their stations.
    bounds = [
        0.5 * (stations[index][1] + stations[index + 1][1])
        for index in range(len(stations) - 1)
    ]

    out: list[tuple[str, int, int]] = []
    first = 0
    for index, bound in enumerate(bounds):
        if first >= len(frames):
            break
        last = first - 1
        while last + 1 < len(frames) and frames[last + 1]["aim_station"] > bound:
            last += 1
        if last >= first:
            out.append((stations[index][0], first, last))
            first = last + 1
    if first < len(frames):
        out.append((stations[-1][0], first, len(frames) - 1))
    return out


def preview_track(solved: dict[str, Any], seed: int = 0) -> dict[str, Any]:
    """The solved flight in the camera-track format the renderer already reads.

    One cut per landmark, tiled and contiguous, because `sloped_race_render.gd`
    takes a still by cut name and a preview whose windows are named after what
    is in them is a contact sheet that builds itself.

    The edit map is the identity, so `sloped_race_scene.replay_at` is a no-op
    and the track's own times are output times.

    ## Consecutive cuts share their boundary frame, and they have to

    `sloped_race_scene._place_from_track` chooses the first cut whose `to` is at
    or after the wanted second, then indexes into that cut's rows from its own
    first row's time. Both of those are float comparisons against a number this
    file wrote with six decimal places, and the renderer's own clock is
    `index / fps` at full precision. At a boundary those disagree: frame 17 of a
    60 fps shot is 0.28333333, the cut's `to` was written as 0.283333, and
    0.28333333 > 0.283333 - so the frame fell through to the *next* cut, indexed
    at zero, and was drawn with the pose belonging to frame 18.

    That is not a rounding curiosity. Rendered, it duplicated three frames of
    the 120 - 17 and 18, 47 and 48, 83 and 84 - each preceded by a step of
    exactly twice the usual size, and it reproduced byte for byte across
    independent renders of different windows, which is what ruled out a GPU
    hiccup and pointed here. Measured in the image: the mean absolute
    inter-frame difference at those pairs was 0.013 against a shot mean of 17.9.

    So each cut carries **one row past its own last frame** - the first row of
    the cut after it - and its `to` is that row's time. Now both readings are
    right: dither that keeps the frame in this cut finds the row it added, and
    dither that pushes it into the next finds that cut's row zero, which is the
    same frame. The cost is one duplicated row per boundary, seven rows in the
    whole track.

    The production edit does not have this fault because its cut bounds are
    *station* times, which land between frames rather than on them. A track cut
    by frame index, as this one is, lands on them every time.
    """
    spec: Preview = solved["spec"]
    frames = solved["frames"]
    cuts: list[dict[str, Any]] = []
    segments: list[dict[str, Any]] = []
    for name, first, last in _segments(solved):
        shared = min(last + 1, len(frames) - 1)
        rows = [
            [
                round(frames[index]["t"], 6),
                *(round(frames[index]["position"][axis], 4) for axis in range(3)),
                *(round(frames[index]["aim"][axis], 4) for axis in range(3)),
                round(spec.fov, 3),
            ]
            for index in range(first, shared + 1)
        ]
        low = round(frames[first]["t"], 6)
        high = round(frames[shared]["t"], 6)
        cuts.append(
            {
                "name": name,
                "until": name,
                "fov": spec.fov,
                "target": "corridor",
                "from": low,
                "to": high,
                "frames": rows,
            }
        )
        segments.append({"cut": name, "out": [low, high], "replay": [low, high]})
    return {
        "units": "layout",
        "fps": spec.fps,
        "seed": seed,
        "edited": False,
        "preview": spec.name,
        "duration": round(solved["duration"], 6),
        "replay_duration": round(solved["duration"], 6),
        "omitted": 0.0,
        "last_crossing": 0.0,
        "edit": segments,
        "cuts": cuts,
    }


def write_track(track: dict[str, Any], path: str) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(track, handle, separators=(",", ":"))
        handle.write("\n")
    return path


def frozen_replay(replay: dict[str, Any], seconds: float, fps: int = 60) -> dict[str, Any]:
    """The race's own first frame, held for the length of the preview.

    The preview happens *before* the race, so nothing in the scene may move -
    and the scene it is rendered in reads its marbles and its machine parts from
    a replay. Repeating frame zero gives the renderer a legal replay in which
    the racers are loaded in the start drum and every actuator is at rest, with
    no change to the shipped renderer, the shipped scene or the race record
    itself. The digest fields are dropped rather than carried, because this is
    not a physical record and a file that claimed to be one would eventually be
    checked as one.
    """
    first = replay["frames"][0]
    count = max(int(round(seconds * fps)), 1) + 1
    return {
        "format": replay.get("format", "marble3d.replay"),
        "version": replay.get("version", 1),
        "mode": replay.get("mode", "marble3d"),
        "seed": replay.get("seed", 0),
        "physics_hz": replay.get("physics_hz", 0),
        "replay_fps": fps,
        "units": replay["units"],
        "marbles": replay["marbles"],
        "frames": [{**first, "t": round(index / fps, 6)} for index in range(count)],
        "events": [],
        "note": "frame zero of the race, held. Not a physical record: see "
        "sloped.course_preview.frozen_replay.",
    }


# --- what it came out as --------------------------------------------------


ASPECT = 1080.0 / 1920.0

# How far short of the aim the centre-of-frame ray is stopped, in layout units.
#
# The aim is a point *on* the corridor, which at the two ends is a point inside
# the thing being looked at: at the start the corridor's last sample is the start
# node, and the start module is built around it. A ray run all the way to it
# reports the module's own near wall as an obstruction - which it measured, at
# 30.3 units of a 32.3-unit ray, two frames before the end of the shot. What the
# test is for is something *between* the lens and its subject, so the last three
# units are the subject's own and are not counted.
CENTRE_SHORTEN = 3.0

# The feature size a landmark is judged at, in layout units. The start module is
# about fourteen units end to end and the finish arena about eight tall; six is
# a conservative stand-in for "one recognisable piece of course furniture", and
# `landmarks[...]["best_height"]` is the fraction of the frame's height it fills
# at its closest, which is what decides whether a viewer can name it.
LANDMARK_SIZE = 6.0


def _visible(
    position: Vec3, aim: Vec3, fov: float, point: Sequence[float], aspect: float
) -> bool:
    """Whether `point` is inside the frustum of a portrait frame.

    `fov` is vertical, because `course_scene.gd` builds its camera with
    `keep_aspect = KEEP_HEIGHT` and Godot's `fov` is then the vertical angle.
    The horizontal half-angle is derived from it and the aspect rather than
    assumed equal, which on a 1080x1920 frame is the difference between 25 and
    14.6 degrees.
    """
    forward = _unit(tuple(aim[axis] - position[axis] for axis in range(3)))
    # forward x (0, 1, 0), written out. Horizontal by construction, which is
    # what makes the frame's own up the renderer's `Vector3.UP`.
    right = _unit((-forward[2], 0.0, forward[0]))
    up = (
        right[1] * forward[2] - right[2] * forward[1],
        right[2] * forward[0] - right[0] * forward[2],
        right[0] * forward[1] - right[1] * forward[0],
    )
    delta = tuple(float(point[axis]) - position[axis] for axis in range(3))
    depth = sum(delta[axis] * forward[axis] for axis in range(3))
    if depth <= 0.15:
        return False
    half_v = math.tan(math.radians(fov) * 0.5)
    half_h = half_v * aspect
    across = sum(delta[axis] * right[axis] for axis in range(3))
    high = sum(delta[axis] * up[axis] for axis in range(3))
    return abs(high) <= half_v * depth and abs(across) <= half_h * depth


def path_report(
    solved: dict[str, Any],
    bundle: Any | None = None,
    stride: int = 2,
    aspect: float = ASPECT,
) -> dict[str, Any]:
    """Every number the brief asks to be measured, and the ones behind them.

    `bundle` is a `sloped.sightlines.Bundle` over the drawn course. Building one
    costs a few seconds, so it is passed in rather than made here; without one
    the lens-clearance and centre-blocked figures are omitted and the rest
    stands.
    """
    frames = solved["frames"]
    line: Line = solved["line"]
    spine: Line = solved["spine"]
    cfg = solved["cfg"]
    spec: Preview = solved["spec"]

    steps: list[float] = []
    across_steps: list[float] = []
    rise_steps: list[float] = []
    turns: list[float] = []
    yaws: list[float] = []
    pitches: list[float] = []
    aim_steps: list[float] = []
    gaze_to_vertical: list[float] = []
    previous: tuple[Vec3, float, float] | None = None
    for index, frame in enumerate(frames):
        forward = _unit(
            tuple(frame["aim"][axis] - frame["position"][axis] for axis in range(3))
        )
        right = _unit((-forward[2], 0.0, forward[0]))
        up = (
            right[1] * forward[2] - right[2] * forward[1],
            right[2] * forward[0] - right[0] * forward[2],
            right[0] * forward[1] - right[1] * forward[0],
        )
        yaw = math.degrees(math.atan2(forward[0], forward[2]))
        pitch = math.degrees(math.asin(max(-1.0, min(1.0, forward[1]))))
        gaze_to_vertical.append(math.degrees(math.acos(min(1.0, abs(forward[1])))))
        if index and previous is not None:
            before = frames[index - 1]
            delta = tuple(
                frame["position"][axis] - before["position"][axis] for axis in range(3)
            )
            steps.append(math.sqrt(sum(value * value for value in delta)))
            across_steps.append(abs(sum(delta[axis] * right[axis] for axis in range(3))))
            rise_steps.append(abs(sum(delta[axis] * up[axis] for axis in range(3))))
            aim_steps.append(math.dist(frame["aim"], before["aim"]))
            dot = min(
                1.0, max(-1.0, sum(forward[axis] * previous[0][axis] for axis in range(3)))
            )
            turns.append(math.degrees(math.acos(dot)))
            yaws.append(abs((yaw - previous[1] + 180.0) % 360.0 - 180.0))
            pitches.append(abs(pitch - previous[2]))
        previous = (forward, yaw, pitch)

    clearances = [
        terrain.clearance(frame["position"], frame["aim"], cfg, samples=40)
        for frame in frames[::stride]
    ]

    # Track visibility: how much of the drawn ribbon is inside the frame, using
    # the real course rather than the corridor, because what a viewer has to see
    # is the track and not the flight line.
    ribbon = line.points[::6]
    seen_fraction = [
        sum(
            1
            for point in ribbon
            if _visible(frame["position"], frame["aim"], frame["fov"], point, aspect)
        )
        / len(ribbon)
        for frame in frames[::stride]
    ]

    landmarks: dict[str, dict[str, Any]] = {}
    for name, point in LANDMARKS:
        window = [
            frame
            for frame in frames
            if _visible(frame["position"], frame["aim"], frame["fov"], point, aspect)
        ]
        entry: dict[str, Any] = {
            "seen": bool(window),
            "seconds": round(len(window) / spec.fps, 3) if window else 0.0,
            "from": round(window[0]["t"], 3) if window else None,
            "to": round(window[-1]["t"], 3) if window else None,
        }
        if window:
            closest = min(window, key=lambda frame: math.dist(frame["position"], point))
            reach = math.dist(closest["position"], point)
            entry["nearest"] = round(reach, 2)
            entry["nearest_at"] = round(closest["t"], 3)
            # What fraction of the frame's height a `LANDMARK_SIZE` feature at
            # that reach fills. `fov` is the vertical angle, so the frame's own
            # height at that distance is `2 * reach * tan(fov / 2)`.
            span = 2.0 * reach * math.tan(math.radians(closest["fov"]) * 0.5)
            entry["best_height"] = round(LANDMARK_SIZE / max(span, 1e-6), 4)
        landmarks[name] = entry

    strays = [
        line.nearest(spine.at(spine.length * step / 40.0)) for step in range(41)
    ]

    report: dict[str, Any] = {
        "name": spec.name,
        "duration": round(solved["duration"], 4),
        "frames": len(frames),
        "fps": spec.fps,
        "fov": spec.fov,
        "start_position": tuple(round(v, 3) for v in frames[0]["position"]),
        "start_aim": tuple(round(v, 3) for v in frames[0]["aim"]),
        "end_position": tuple(round(v, 3) for v in frames[-1]["position"]),
        "end_aim": tuple(round(v, 3) for v in frames[-1]["aim"]),
        # What the handoff pose *is*, in the terms `sloped.cameras.Cut` uses, so
        # the race camera that takes over can be compared with it directly
        # rather than by reading six coordinates. Reported, never enforced.
        "end_reach": round(math.dist(frames[-1]["position"], frames[-1]["aim"]), 3),
        "end_elevation": round(
            math.degrees(
                math.atan2(
                    frames[-1]["position"][1] - frames[-1]["aim"][1],
                    math.hypot(
                        frames[-1]["position"][0] - frames[-1]["aim"][0],
                        frames[-1]["position"][2] - frames[-1]["aim"][2],
                    ),
                )
            ),
            2,
        ),
        "max_step": round(max(steps), 4),
        "mean_step": round(sum(steps) / len(steps), 4),
        "max_across_step": round(max(across_steps), 4),
        "max_rise_step": round(max(rise_steps), 4),
        "max_aim_step": round(max(aim_steps), 4),
        "max_turn": round(max(turns), 4),
        "mean_turn": round(sum(turns) / len(turns), 4),
        "total_turn": round(sum(turns), 3),
        "max_yaw": round(max(yaws), 4),
        "max_pitch": round(max(pitches), 4),
        "total_yaw": round(sum(yaws), 3),
        "total_pitch": round(sum(pitches), 3),
        "min_sight_clearance": round(min(clearances), 3),
        "min_gaze_to_vertical": round(min(gaze_to_vertical), 2),
        "min_visible_fraction": round(min(seen_fraction), 4),
        "mean_visible_fraction": round(sum(seen_fraction) / len(seen_fraction), 4),
        "landmarks": landmarks,
        "landmarks_seen": sum(1 for entry in landmarks.values() if entry["seen"]),
        "corridor_length": round(spine.length, 3),
        "course_length": round(line.length, 3),
        "max_corridor_stray": round(max(strays), 3),
        "mean_corridor_stray": round(sum(strays) / len(strays), 3),
    }
    if bundle is not None:
        lens = [bundle.nearest(frame["position"]) for frame in frames[::stride]]
        worst = min(lens, key=lambda entry: entry[0])
        blocked = [
            frame["t"]
            for frame in frames[::stride]
            if bundle.first_hit(frame["position"], frame["aim"], shorten=CENTRE_SHORTEN)
            is not None
        ]
        report["min_lens_clearance"] = round(worst[0], 3)
        report["nearest_solid"] = worst[1]
        report["centre_blocked_frames"] = len(blocked)
        report["centre_blocked_first"] = round(blocked[0], 3) if blocked else None
    return report


def check_preview(report: dict[str, Any]) -> list[str]:
    """What in `path_report`'s numbers would be a defect a viewer could see."""
    problems: list[str] = []
    low, high = DURATION_RANGE
    if not low - 1e-6 <= report["duration"] <= high + 1e-6:
        problems.append(
            f"duration {report['duration']:.2f} s is outside the brief's "
            f"{low:.1f}-{high:.1f} s"
        )
    if report["max_step"] > MAX_STEP:
        problems.append(
            f"the lens moves {report['max_step']:.2f} layout units in a frame, over "
            f"the {MAX_STEP:.2f} a dolly may"
        )
    if report["max_across_step"] > MAX_ACROSS_STEP:
        problems.append(
            f"the lens moves {report['max_across_step']:.2f} units sideways across "
            f"the frame in a frame, over the {MAX_ACROSS_STEP:.2f} allowed"
        )
    if report["max_rise_step"] > MAX_RISE_STEP:
        problems.append(
            f"the lens moves {report['max_rise_step']:.2f} units up or down the frame "
            f"in a frame, over the {MAX_RISE_STEP:.2f} allowed"
        )
    if report["max_turn"] > MAX_TURN:
        problems.append(
            f"the gaze turns {report['max_turn']:.2f} degrees in a frame, over the "
            f"{MAX_TURN:.2f} allowed"
        )
    if report["max_yaw"] > MAX_YAW:
        problems.append(
            f"the gaze pans {report['max_yaw']:.2f} degrees in a frame, over the "
            f"{MAX_YAW:.2f} allowed"
        )
    if report["max_pitch"] > MAX_PITCH:
        problems.append(
            f"the gaze tilts {report['max_pitch']:.2f} degrees in a frame, over the "
            f"{MAX_PITCH:.2f} allowed"
        )
    if report["min_sight_clearance"] < SIGHT_MARGIN:
        problems.append(
            f"the ground crosses within {report['min_sight_clearance']:.2f} of the "
            f"sight line, inside the {SIGHT_MARGIN:.2f} it needs"
        )
    if report["min_gaze_to_vertical"] < MIN_GAZE_TO_VERTICAL:
        problems.append(
            f"the gaze comes within {report['min_gaze_to_vertical']:.1f} degrees of "
            f"vertical, where the renderer's up vector is undefined"
        )
    if "min_lens_clearance" in report and report["min_lens_clearance"] < LENS_MARGIN:
        problems.append(
            f"the lens passes {report['min_lens_clearance']:.2f} units from "
            f"{report['nearest_solid']}, inside the {LENS_MARGIN:.1f} it needs"
        )
    if report.get("centre_blocked_frames"):
        problems.append(
            f"the middle of the frame is blocked in {report['centre_blocked_frames']} "
            f"sampled frames, first at {report['centre_blocked_first']:.2f} s"
        )
    missing = sorted(
        name for name, entry in report["landmarks"].items() if not entry["seen"]
    )
    if missing:
        problems.append("never in frame: " + ", ".join(missing))
    return problems

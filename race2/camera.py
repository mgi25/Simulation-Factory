"""The Race #2 camera language: seven modes, and what each one is *for*.

Race #1's camera documents where the race is. Every cut is a fixed bearing and
elevation about a station on the course, and the shot is correct in the sense
that the racers are in it. What it does not do is tell the viewer what is about
to happen, and the brief's diagnosis is that this is most of why the middle of
the film does not hold: a shot that shows only the present has nothing to make
a viewer lean forward.

So the rule here is one line:

    SHOW THE RACERS, SHOW THE NEXT THREAT, SHOW THE CONSEQUENCE.

and the three parts of it are three different things the solver does.

## Show the racers: the frame is solved from the pack, not from the course

Every mode sizes its distance so the **leading group** spans a stated fraction
of the frame *width*. Not the course, not a station's extent - the racers. That
is the direct answer to the failure mode the brief names: a camera placed at a
fixed reach from a station frames whatever the station is, and when the field is
strung out over twenty units the racers in it are four pixels each.

The target band is 25-45% of useful frame width, and it is a target rather than
a law: `race2.framing.report` measures what was achieved and a shot that misses
it is a finding, not a crash. Cropping racers out to hit the number would be
worse than missing it.

## Show the next threat: the aim leads the pack

The aim is a blend of where the racers are and where the *next event* is:

    aim = (1 - look_ahead) * pack centroid + look_ahead * next event

with `look_ahead` around 0.3. At 0.0 the camera follows; at 1.0 it stares at an
empty mechanism. Around 0.3 the racers sit in the near two thirds of frame and
the thing they are about to hit sits in the far third, which is the composition
the brief's Part D describes. The exact number is per shot and tuned by looking,
which is what `tools/race2_camera.py --sheet` exists for.

## Show the consequence: a shot outlives its event

Every mode's window is authored to end *after* the event it covers, by at least
`CONSEQUENCE` seconds. Cutting on the impact is the reflex and it is wrong: the
viewer has seen the collision and not seen who won it.

## Anticipation is its own mode, not a parameter

`obstacle_anticipation` puts the camera *past* the mechanism looking back up the
course, so the mechanism is in the foreground and the field arrives into it. A
look-ahead blend cannot produce that shot - it can only lead the aim, and a led
aim still has the camera behind the pack with the mechanism edge-on.

## Determinism

A shot is authored - mode, window, bearing, elevation, look-ahead - and the
solver is a pure function of the shot and the replay. Nothing is chosen at
render time, nothing is random, and two runs of `build_track` on the same replay
produce byte-identical JSON. The event markers the windows are anchored to come
from the race's own stage times, so the schedule adapts to the seed without
anything about it being decided by a heuristic at run time.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from typing import Any, Sequence

from sloped.scale import SIM_TO_LAYOUT

from race2.course import Course

__all__ = [
    "MODES",
    "Shot",
    "Plan",
    "TrackState",
    "build_track",
    "write_track",
    "preferred_side",
    "CONSEQUENCE",
]

# The seven modes, and the one sentence each exists for.
MODES = {
    "hook_close": "eight racers filling the frame at rest, so the premise lands inside half a second",
    "pack_track": "the leading group in the near two thirds and the course direction in the far third",
    "obstacle_anticipation": "the mechanism in the foreground, the field arriving into it",
    "action": "close and low inside a compression, where the contact is",
    "route_choice": "both branches in frame at once, so a choice is legible as a choice",
    "final_sprint": "low and alongside, so the closing gap is the whole picture",
    "winner_payoff": "the winner across the line and far enough past it to be read",
}

# How long a shot must outlive the event it covers, in seconds. Half a second is
# about what it takes to see who came out of a collision in front.
CONSEQUENCE = 0.55

# Frame geometry. `fov` is the *vertical* half-angle doubled, which is what
# Godot's Camera3D takes, and the delivery frame is portrait - so the horizontal
# field is the narrow one and a shot sized on the vertical is 44% tighter
# horizontally than it looks in the number.
FRAME_WIDTH = 1080
FRAME_HEIGHT = 1920

# How far the lens may travel between two output frames, in layout units. Taken
# from Race #1's own limit and for its reason: a camera stands a reach from its
# aim, so a bearing that turns one degree moves a lens fifty units out by nearly
# a unit while the aim has not moved at all, and every camera fault V21 found
# was of that shape.
MAX_STEP = 1.2
SMOOTH_PASSES = 10

# How far the solver may lift a shot to see past the course, and in what steps.
#
# **A folded course occludes itself, and that is the price of folding it.**
# Race #1's legs are forty units apart and a camera behind the pack sees only
# the leg the pack is on. The switchyard's neighbouring legs are five to nine
# units away and often between the lens and the racers: the first render of
# seed 1 put the camera under the channel for four of seven shots, and in the
# start shot it was behind the trapdoor panel looking at its underside.
#
# So the elevation authored on a shot is a *floor*, not a value. The solver
# raises it in four-degree steps until the leading group is actually visible,
# and stops at 44 degrees because past that the shot stops being a
# three-quarter view and becomes the map the brief's Part F rules out. A shot
# that cannot see its racers at 44 degrees is reported by
# `race2.framing.report` rather than lifted further.
LIFT_STEP = 4.0
MAX_ELEVATION = 44.0
# A blocker sphere is skipped within this distance of the target, because the
# channel the pack is running in is legitimately between the lens and them.
NEAR_TARGET = 2.6

# The widest span the framing solve will pull back for, in layout units.
#
# **Without a cap, "keep the leading group at 34% of frame width" is a rule
# that makes the racers small.** A portrait frame's horizontal half-angle at a
# 38-degree vertical fov is 11 degrees, so filling 42% of the width with a
# 14-unit group puts the lens 86 layout units out - further than the course is
# long - and a 0.57-unit marble is 18 pixels in a 1080 frame, or four and a
# half on a phone. Measured on seed 1: the last four shots were all like that.
#
# 7.0 is twelve marble diameters. Past it the shot frames the leading three at
# a readable size and lets the tail leave frame, which is the right trade: a
# shot of three racers you can tell apart is a race, and a shot of eight dots
# is a diagram. `race2.framing.report` records how many were actually in
# frame, so what the cap costs is visible rather than assumed.
MAX_FRAMED_EXTENT = 7.0

# Which way the course key comes from, in plan, as a unit vector.
#
# Derived from the environment rather than chosen: `alpine_neon.json` - the
# profile every valley environment in this repository extends - rotates `Key`
# (cull mask 1, the one that lights the machine) by (-44, -34, 0) degrees. A
# Godot DirectionalLight3D shines along its local -Z, so under Godot's YXZ
# Euler order that light *travels* toward (0.402, -0.695, -0.596) and therefore
# *comes from* (-0.402, +0.695, +0.596). Normalised in plan that is
# (-0.56, 0, +0.83).
#
# **This is a camera decision, not an environment one.** Nothing in
# `assets/marble_machine/environment/` is touched; the solver simply prefers
# the side of the course the key is already on, so the racers are front-lit
# instead of silhouetted. The first render of the hook put the lens on the
# shadow side and eight glossy marbles came back as dark shapes.
KEY_FROM = (-0.56, 0.0, 0.83)

# The most of a mechanism's approach an anticipation shot will frame, in layout
# units. Nine is about fifteen marble diameters: enough run-up to read "they
# are about to hit that", short enough that the racers stay readable.
APPROACH_CAP = 9.0

# How much clear air the lens itself needs, in layout units, and the closest it
# may ever stand to its aim.
#
# **A clear sightline is not a clear shot.** The final-sprint cut on seed 140
# had all three leading racers visible and was still unusable: the lens sat
# twelve units out among the switchback legs, and the underside of the pan
# above filled the top half of the frame as an enormous pale shape with a
# five-pixel marble beyond it. The sightline test cannot see that, because
# nothing was between the lens and the racers - the problem was what was beside
# it.
#
# So the lift loop prefers positions with 2.4 units of clear air around the
# lens, and no shot stands closer than 7.0 units from its aim whatever the
# framing solve asks for. A folded course is the reason both numbers exist:
# Race #1's legs are forty units apart and neither would ever have bound.
LENS_CLEARANCE = 2.4
MIN_REACH = 7.0

# And the furthest the lens may ever stand from its aim, in layout units.
#
# **The extent cap was not enough, because a portrait frame is narrow.** At a
# 34-degree vertical field the horizontal half-angle is 9.8 degrees, so filling
# 38% of the width with a 7-unit group still puts the lens sixty layout units
# out - further than the course is wide - and on a folded course sixty units
# away means two other legs between the lens and the racers. Seed 140's sprint
# cut came back as the underside of `pan5` filling the top of frame with a
# five-pixel marble beyond it, twice, before this number existed.
#
# 26 is half the course's long dimension. At it a racer is about seventy pixels
# in a 1080 frame, and a group wider than the frame simply overflows - which
# `race2.framing.report` counts as racers out of frame, so the cost is visible.
MAX_REACH = 26.0

# How far above the channel's *own* plane the lens must sit, in degrees.
#
# **The sightline test cannot see the wall the racers are standing behind.** It
# skips blockers within `NEAR_TARGET` of the target, because the channel the
# pack is in is legitimately between the lens and them - and that skip is
# exactly what let seed 140's `last_impact` come back with five racers counted
# in frame and none of them visible, hidden behind their own guard rail with
# the camera nearly edge-on to the channel.
#
# Seeing a marble over its own near rail needs `atan(containment / half width)`
# of depression, measured in the channel's banked frame. `race2.track.WALL_CAP`
# holds the containment at 0.62 layout units whatever the width scale is, so
# the demand is 25 degrees in the narrowest corridor and 10 in a pan. 22 is the
# working number: above the pans' requirement everywhere and one lift step
# under the corridors', which the sightline test then supplies where it is
# actually needed rather than everywhere.
#
# It is measured against the run's *banked* up vector rather than against world
# vertical, which is the whole reason it works on a course whose turns roll to
# 28 degrees - a world-vertical rule would be wrong by the bank, and wrong in
# the direction that matters, because the camera prefers the outside of a turn
# where the rail is highest.
MIN_LOOKDOWN = 14.0
# And the most that will ever be demanded. Past 40 degrees a shot has stopped
# being a three-quarter view, and a channel that needs more than that is a
# channel to widen rather than a camera to lift - which is what
# `race2.track`'s wall cap is for.
MAX_LOOKDOWN = 40.0


def horizontal_half_angle(fov_deg: float) -> float:
    """The horizontal half-angle of a portrait frame at a vertical `fov`."""
    return math.atan(
        math.tan(math.radians(fov_deg) * 0.5) * (FRAME_WIDTH / FRAME_HEIGHT)
    )


@dataclass(frozen=True)
class Shot:
    """One cut: a mode, a window, and the handful of numbers that aim it."""

    name: str
    mode: str
    start: float
    end: float
    fov: float = 36.0
    elevation: float = 18.0
    # Degrees about the vertical from the course's own direction of travel.
    # Zero is directly behind the pack looking downhill; 180 is head-on. The
    # brief asks for a low or moderate three-quarter view, which is 30 to 55.
    bearing: float = 42.0
    look_ahead: float = 0.30
    # What fraction of the frame width the leading group should span.
    target_width: float = 0.34
    group: int = 4
    # A mechanism or stage this shot is about, for the anticipation modes and
    # for the camera event map.
    subject: str = ""
    # Extra reach, in layout units, added after the framing solve. Used where a
    # shot has to clear geometry rather than where it wants to be looser.
    lift: float = 0.0
    note: str = ""

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"shot {self.name!r}: unknown mode {self.mode!r}")
        if self.end <= self.start:
            raise ValueError(f"shot {self.name!r}: {self.start} to {self.end} is not a window")


@dataclass
class Plan:
    """A whole schedule, and the race it was solved against."""

    shots: list[Shot] = field(default_factory=list)
    fps: int = 60

    def duration(self) -> float:
        return max((shot.end for shot in self.shots), default=0.0)

    def check(self) -> list[str]:
        """Gaps and overlaps, as complaints rather than exceptions."""
        out: list[str] = []
        for a, b in zip(self.shots, self.shots[1:]):
            if b.start < a.end - 1e-6:
                out.append(f"{a.name} and {b.name} overlap by {a.end - b.start:.3f} s")
            elif b.start > a.end + 1e-6:
                out.append(f"{a.name} to {b.name} leaves {b.start - a.end:.3f} s uncovered")
        return out


class TrackState:
    """Where the race is at one replay frame, in layout units.

    Everything a mode can ask for is here and nothing else: the pack centroid,
    the leader, the extent of the leading group, the direction of travel and
    where the next event is. That list is the brief's Part I - useful reusable
    logic, and specifically not an autonomous cinematographer.
    """

    def __init__(self, replay: dict[str, Any], course: Course, outcome) -> None:
        self.course = course
        self.fps = float(replay.get("replay_fps", 60))
        self.frames = replay["frames"]
        self.times = [float(frame["t"]) for frame in self.frames]
        self.outcome = outcome
        self.ranks = {round(when, 4): order for when, order in outcome.rank_series}
        self._rank_times = sorted(self.ranks)
        # Station positions, in layout units, so a shot can name one as its
        # subject and the solver can find it.
        self.stations: dict[str, tuple[float, float, float]] = {}
        for module_id in course.stations:
            module = course.machine.modules.get(module_id)
            if module is None:
                continue
            bounds = module.bounds()
            self.stations[module_id] = tuple(
                0.5 * (bounds.lower[axis] + bounds.upper[axis]) * SIM_TO_LAYOUT
                for axis in range(3)
            )
        # Each stage's entry point on the course, for "where is the next event".
        self.stage_points: list[tuple[str, tuple[float, float, float]]] = []
        for stage in course.stages:
            run = course.runs[stage.runs[0]]
            self.stage_points.append((stage.name, tuple(run.path[0])))
        # And the line itself, so the sprint leads toward the thing the race is
        # about rather than toward the fallback "eight units further along the
        # heading" - which on seed 140 aimed the last shot at empty channel and
        # left the leaders behind the bottom of frame.
        self.stage_points.append(
            ("finish", tuple(v * SIM_TO_LAYOUT for v in course.finish_line.frame.position))
        )

        # The course as a chain of spheres, in layout units, for the sightline
        # test. Every sixth sample, at the channel's outer envelope: half the
        # clear width plus a guard. Coarse on purpose - this decides whether to
        # raise a camera, not whether a pixel is covered, and a per-triangle
        # test over 25 000 triangles at 1150 frames is not affordable.
        self.blockers: list[tuple[float, float, float, float]] = []
        for name, run in course.runs.items():
            for index in range(0, len(run.path), 6):
                point = run.path[index]
                half = 0.5 * run.clear_width * run.widths[index] / SIM_TO_LAYOUT
                self.blockers.append(
                    (point[0], point[1], point[2], half * SIM_TO_LAYOUT + 0.35)
                )
        # **The stations too, and the start shelf most of all.** A blocker set
        # made only of runs let the solver put the hook shot behind the start's
        # back wall and report every racer visible, because the wall was not in
        # the set. One sphere per module at its own bounds is coarse - a shelf
        # is not a ball - but it is the difference between a shot that is
        # obviously wrong and one that is lifted until it is not.
        for module in course.machine:
            if module.id in course.runs:
                continue
            bounds = module.bounds()
            centre = tuple(
                0.5 * (bounds.lower[axis] + bounds.upper[axis]) * SIM_TO_LAYOUT
                for axis in range(3)
            )
            radius = 0.5 * min(
                (bounds.upper[axis] - bounds.lower[axis]) * SIM_TO_LAYOUT
                for axis in range(3)
            )
            if radius > 0.3:
                self.blockers.append((centre[0], centre[1], centre[2], radius))

    # --- per frame -------------------------------------------------------

    def frame_at(self, seconds: float) -> int:
        return max(0, min(len(self.frames) - 1, int(round(seconds * self.fps))))

    def positions(self, index: int) -> dict[int, tuple[float, float, float]]:
        out: dict[int, tuple[float, float, float]] = {}
        for sample in self.frames[index]["marbles"]:
            point = sample["p"] if isinstance(sample, dict) else sample[1]
            marble = sample["id"] if isinstance(sample, dict) else sample[0]
            out[int(marble)] = tuple(float(v) * SIM_TO_LAYOUT for v in point)
        return out

    def order_at(self, seconds: float) -> tuple[int, ...]:
        """The rank order nearest this time, or the field order if unknown."""
        if not self._rank_times:
            return tuple(sorted(self.positions(self.frame_at(seconds))))
        key = min(self._rank_times, key=lambda t: abs(t - seconds))
        return self.ranks[key]

    def group(self, seconds: float, count: int) -> list[tuple[float, float, float]]:
        """The leading `count` racers' positions, leader first."""
        index = self.frame_at(seconds)
        places = self.positions(index)
        order = [m for m in self.order_at(seconds) if m in places]
        return [places[m] for m in order[:count]] or list(places.values())[:count]

    def centroid(self, seconds: float, count: int) -> tuple[float, float, float]:
        points = self.group(seconds, count)
        if not points:
            return (0.0, 0.0, 0.0)
        return tuple(sum(p[axis] for p in points) / len(points) for axis in range(3))

    def extent(self, seconds: float, count: int) -> float:
        """The greatest distance between two of the leading group."""
        points = self.group(seconds, count)
        if len(points) < 2:
            return 2.0 * 0.285
        return max(
            math.dist(a, b) for i, a in enumerate(points) for b in points[i + 1:]
        )

    def leader(self, seconds: float) -> tuple[float, float, float]:
        points = self.group(seconds, 1)
        return points[0] if points else (0.0, 0.0, 0.0)

    def heading(self, seconds: float) -> tuple[float, float, float]:
        """The direction of travel at the pack, from the course itself.

        Read off the nearest run rather than differenced from the marbles: a
        marble in a banked turn is moving across the channel as well as along
        it, and a bearing taken from its velocity swings with every bounce.
        """
        centre = self.centroid(seconds, 3)
        best = None
        for name, run in self.course.runs.items():
            for index in range(0, len(run.path), 4):
                point = run.path[index]
                distance = (point[0] - centre[0]) ** 2 + (point[2] - centre[2]) ** 2
                if best is None or distance < best[0]:
                    best = (distance, name, index)
        if best is None:
            return (1.0, 0.0, 0.0)
        _d, name, index = best
        run = self.course.runs[name]
        tangent = run.tangents[min(index, len(run.tangents) - 1)]
        span = math.hypot(tangent[0], tangent[2]) or 1.0
        return (tangent[0] / span, 0.0, tangent[2] / span)

    def local_up(self, seconds: float) -> tuple[float, float, float]:
        """The channel's own up vector at the pack - banked, not world vertical."""
        centre = self.centroid(seconds, 3)
        best = None
        for name, run in self.course.runs.items():
            for index in range(0, len(run.path), 4):
                point = run.path[index]
                distance = (point[0] - centre[0]) ** 2 + (point[2] - centre[2]) ** 2
                if best is None or distance < best[0]:
                    best = (distance, name, index)
        if best is None:
            return (0.0, 1.0, 0.0)
        _d, name, index = best
        run = self.course.runs[name]
        _lateral, up, _forward = run.frames[min(index, len(run.frames) - 1)]
        return tuple(float(v) for v in up)

    def required_lookdown(self, seconds: float) -> float:
        """How far above the channel's plane the lens must be, in degrees.

        `atan(containment / half width)` at the pack's own sample, which is the
        angle at which a sightline to a marble on the cradle just clears the
        near rail. Read from the run rather than fixed, because the switchyard
        varies both terms by a factor of two along its length: a pan with its
        guard boost wants 36 degrees and the head band wants 13, and a single
        constant would either hide the racers in one or fly the camera in the
        other.
        """
        centre = self.centroid(seconds, 3)
        best = None
        for name, run in self.course.runs.items():
            for index in range(0, len(run.path), 4):
                point = run.path[index]
                distance = (point[0] - centre[0]) ** 2 + (point[2] - centre[2]) ** 2
                if best is None or distance < best[0]:
                    best = (distance, name, index)
        if best is None:
            return MIN_LOOKDOWN
        _d, name, index = best
        run = self.course.runs[name]
        half = 0.5 * run.clear_width * run.widths[index]
        rail = run.containment_at(index)
        if half <= 1e-6:
            return MIN_LOOKDOWN
        return max(
            MIN_LOOKDOWN, min(MAX_LOOKDOWN, math.degrees(math.atan2(rail, half)))
        )

    def next_event(self, seconds: float, subject: str = "") -> tuple[float, float, float]:
        """Where the thing the pack is about to meet is.

        A named subject wins - a shot that says it is about the drum is about
        the drum. Otherwise it is the next stage entry ahead of the leader,
        which is a defensible default: a stage boundary is where the width
        changes, and a width change is the next thing that will do something.
        """
        if subject and subject in self.stations:
            return self.stations[subject]
        leader = self.leader(seconds)
        heading = self.heading(seconds)
        best = None
        for name, point in self.stage_points:
            ahead = sum((point[axis] - leader[axis]) * heading[axis] for axis in (0, 2))
            if ahead <= 0.0:
                continue
            if best is None or ahead < best[0]:
                best = (ahead, point)
        if best is not None:
            return best[1]
        # Past the last stage entry: aim along the heading instead of nowhere.
        return tuple(leader[axis] + heading[axis] * 8.0 for axis in range(3))


def _spin(direction: tuple[float, float, float], degrees: float) -> tuple[float, float, float]:
    angle = math.radians(degrees)
    cos, sin = math.cos(angle), math.sin(angle)
    return (
        direction[0] * cos - direction[2] * sin,
        0.0,
        direction[0] * sin + direction[2] * cos,
    )


def _behind(heading: tuple[float, float, float], degrees: float):
    """The lens bearing for a shot `degrees` off directly behind the pack.

    **The camera stands at `aim + bearing * reach`, so a bearing equal to the
    heading puts it downhill of the racers looking back at them.** That is a
    head-on shot, not a chase, and the first build had every tracking shot
    authored as if zero meant "behind". Negating the heading first makes the
    number mean what every shot's comment says it means: 0 is directly behind
    looking downhill, 40 is a three-quarter rear, 180 is head-on.
    """
    return _spin((-heading[0], 0.0, -heading[2]), degrees)


def _lens_clearance(state: "TrackState", camera) -> float:
    """Distance from the lens to the nearest piece of course, in layout units."""
    best = 1e9
    for cx, cy, cz, radius in state.blockers:
        gap = math.sqrt(
            (cx - camera[0]) ** 2 + (cy - camera[1]) ** 2 + (cz - camera[2]) ** 2
        ) - radius
        if gap < best:
            best = gap
    return best


def _blocked(state: "TrackState", camera, target) -> bool:
    """Does the course stand between the lens and this point?

    A point-to-segment test against the blocker spheres, skipping the ones
    within `NEAR_TARGET` of the target - the channel the racers are in is
    legitimately between the lens and them, and a test that counted it would
    lift every shot to the ceiling.
    """
    dx = target[0] - camera[0]
    dy = target[1] - camera[1]
    dz = target[2] - camera[2]
    length2 = dx * dx + dy * dy + dz * dz
    if length2 < 1e-9:
        return False
    for cx, cy, cz, radius in state.blockers:
        near = (cx - target[0]) ** 2 + (cy - target[1]) ** 2 + (cz - target[2]) ** 2
        if near < (radius + NEAR_TARGET) ** 2:
            continue
        t = ((cx - camera[0]) * dx + (cy - camera[1]) * dy + (cz - camera[2]) * dz) / length2
        if t <= 0.0 or t >= 1.0:
            continue
        px = camera[0] + dx * t
        py = camera[1] + dy * t
        pz = camera[2] + dz * t
        if (cx - px) ** 2 + (cy - py) ** 2 + (cz - pz) ** 2 < radius * radius:
            return True
    return False


def _reach_for(extent: float, fov: float, target_width: float) -> float:
    """How far back to stand so `extent` fills `target_width` of the frame.

    The extent is treated as horizontal, which is what a group of racers
    abreast is and is the conservative reading for a group strung out along the
    course - a line along the view direction subtends less, so solving it as if
    it were across the frame puts the camera no further away than it needs to
    be.
    """
    half = horizontal_half_angle(fov)
    wanted = max(target_width, 0.05)
    return min(
        MAX_REACH,
        max(MIN_REACH, (0.5 * max(extent, 0.6)) / max(math.tan(half) * wanted, 1e-6)),
    )


def _aim_and_bearing(state: TrackState, shot: Shot, seconds: float, side: float = 1.0):
    """(aim, horizontal bearing, base reach) for one instant of one shot.

    `side` is +1 or -1 and mirrors the bearing about the direction of
    travel. It is decided once per shot by `preferred_side` and held for
    the whole of it: a side chosen per frame would swap in the middle of a
    cut, which is a jump the viewer reads as a second camera.
    """
    heading = state.heading(seconds)
    centroid = state.centroid(seconds, shot.group)
    target = state.next_event(seconds, shot.subject)
    extent = min(state.extent(seconds, shot.group), MAX_FRAMED_EXTENT)

    if shot.mode == "hook_close":
        # **In front of the grid, looking back up at it.** A hook shot solved
        # from behind puts the lens on the wrong side of the start shelf's back
        # wall - which is what the first render did, and the whole frame was
        # the outside of a dark slab. Eight racers on a line are photographed
        # from in front, the way a starting grid always is, and the floor
        # opening under them is then the thing the frame is about.
        aim = centroid
        bearing = _spin(heading, side * shot.bearing)
        reach = _reach_for(extent + 1.1, shot.fov, shot.target_width)
    elif shot.mode == "obstacle_anticipation":
        # Stand *beyond* the mechanism, looking back up the course at it. The
        # aim is the mechanism pulled a little toward the field, so the
        # arriving pack is in frame rather than off the top of it.
        aim = tuple(target[axis] * 0.72 + centroid[axis] * 0.28 for axis in range(3))
        bearing = _behind(heading, side * (180.0 - shot.bearing))
        # **How much of the approach to fit, capped.** Fitting the whole
        # distance from the pack to the mechanism pulls the lens back by the
        # length of the approach, and on seed 140 the drum shot came back with
        # the racers at 14% of frame width and 29 pixels across - a correct
        # composition of the wrong subject. A third of the approach, and never
        # more than APPROACH_CAP of it, keeps the mechanism in the foreground
        # and the arriving field big enough to have colours.
        approach = min(math.dist(centroid, target) * 0.34, APPROACH_CAP)
        reach = _reach_for(max(extent, approach) + 2.0,
                           shot.fov, shot.target_width)
    elif shot.mode == "route_choice":
        aim = tuple(target[axis] * 0.55 + centroid[axis] * 0.45 for axis in range(3))
        bearing = _behind(heading, side * shot.bearing)
        reach = _reach_for(extent + 4.4, shot.fov, shot.target_width)
    elif shot.mode == "final_sprint":
        aim = tuple(
            centroid[axis] * (1.0 - shot.look_ahead) + target[axis] * shot.look_ahead
            for axis in range(3)
        )
        bearing = _behind(heading, side * shot.bearing)
        reach = _reach_for(extent + 0.9, shot.fov, shot.target_width)
    elif shot.mode == "winner_payoff":
        aim = state.leader(seconds)
        bearing = _behind(heading, side * (180.0 - shot.bearing))
        reach = _reach_for(2.4, shot.fov, shot.target_width)
    elif shot.mode == "action":
        aim = tuple(
            centroid[axis] * (1.0 - shot.look_ahead * 0.5)
            + target[axis] * shot.look_ahead * 0.5
            for axis in range(3)
        )
        bearing = _behind(heading, side * shot.bearing)
        reach = _reach_for(extent + 1.6, shot.fov, shot.target_width)
    else:  # pack_track
        aim = tuple(
            centroid[axis] * (1.0 - shot.look_ahead) + target[axis] * shot.look_ahead
            for axis in range(3)
        )
        bearing = _behind(heading, side * shot.bearing)
        reach = _reach_for(extent + 1.4, shot.fov, shot.target_width)
    return aim, bearing, reach + shot.lift


def _lens(aim, bearing, elevation_deg: float, reach: float):
    elevation = math.radians(elevation_deg)
    return (
        aim[0] + bearing[0] * math.cos(elevation) * reach,
        aim[1] + math.sin(elevation) * reach,
        aim[2] + bearing[2] * math.cos(elevation) * reach,
    )


def preferred_side(state: TrackState, shot: Shot) -> float:
    """Which way to mirror a shot's bearing, decided once at its midpoint.

    Of the two bearings the shot could take - one either side of the direction
    of travel - the one that puts the lens nearer the key's own side wins, so
    the racers are lit rather than silhouetted. Ties and near-ties keep +1, so
    the answer is stable under a hairpin where the heading swings.
    """
    middle = 0.5 * (shot.start + shot.end)
    scores = []
    for side in (1.0, -1.0):
        _aim, bearing, _reach = _aim_and_bearing(state, shot, middle, side)
        scores.append((bearing[0] * KEY_FROM[0] + bearing[2] * KEY_FROM[2], side))
    scores.sort(key=lambda pair: (-pair[0], -pair[1]))
    return scores[0][1]


def _solve_frame(state: TrackState, shot: Shot, seconds: float, side: float = 1.0) -> tuple:
    """(position, aim, fov) for one instant of one shot, in layout units.

    The authored elevation is a floor. The solver raises it in `LIFT_STEP`
    increments until the leading group is actually visible past the rest of the
    course, and settles for the elevation that sees the most of them if none
    sees all - which is the honest behaviour for a shot the geometry does not
    allow, and one `race2.framing.report` then flags rather than hides.
    """
    aim, bearing, reach = _aim_and_bearing(state, shot, seconds, side)
    racers = state.group(seconds, max(shot.group, 2))
    up = state.local_up(seconds)
    wanted = math.sin(math.radians(state.required_lookdown(seconds)))
    best_ok = None
    best_any = None
    elevation = shot.elevation
    while elevation <= MAX_ELEVATION + 1e-6:
        position = _lens(aim, bearing, elevation, reach)
        offset = [position[axis] - aim[axis] for axis in range(3)]
        span = math.sqrt(sum(v * v for v in offset)) or 1.0
        lookdown = sum(offset[axis] * up[axis] for axis in range(3)) / span
        seen = sum(1 for point in racers if not _blocked(state, position, point))
        ok = (
            lookdown >= wanted
            and _lens_clearance(state, position) >= LENS_CLEARANCE
        )
        if best_any is None or seen > best_any[0]:
            best_any = (seen, position, elevation)
        if ok and (best_ok is None or seen > best_ok[0]):
            best_ok = (seen, position, elevation)
            if seen == len(racers):
                break
        elevation += LIFT_STEP
    chosen = best_ok or best_any
    position = chosen[1] if chosen else _lens(aim, bearing, shot.elevation, reach)
    return position, aim, shot.fov


def _smooth(points: list[tuple[float, float, float]], passes: int) -> list[tuple[float, float, float]]:
    out = [tuple(p) for p in points]
    for _ in range(passes):
        if len(out) < 3:
            break
        out = (
            [out[0]]
            + [
                tuple(0.25 * a[i] + 0.5 * b[i] + 0.25 * c[i] for i in range(3))
                for a, b, c in zip(out, out[1:], out[2:])
            ]
            + [out[-1]]
        )
    return out


def _limit_step(points: list[tuple[float, float, float]], limit: float) -> list[tuple[float, float, float]]:
    """Clamp how far the lens travels between frames, keeping the first point."""
    if not points:
        return points
    out = [points[0]]
    for point in points[1:]:
        previous = out[-1]
        step = math.dist(previous, point)
        if step <= limit or step < 1e-9:
            out.append(point)
        else:
            scale = limit / step
            out.append(
                tuple(previous[axis] + (point[axis] - previous[axis]) * scale for axis in range(3))
            )
    return out


def build_track(plan: Plan, state: TrackState, course: Course) -> dict[str, Any]:
    """The camera track, in the JSON the Godot renderer already reads.

    Same shape as `sloped.cameras.write_track` writes: a list of cuts, each a
    name, a window and a row per output frame of
    `[t, px, py, pz, ax, ay, az, fov]` in layout units. Reusing the format is
    what lets the Race #2 scene inherit the loader, the frame-pair lookup and
    the cut-boundary correction Race #1 paid for.
    """
    cuts: list[dict[str, Any]] = []
    fps = plan.fps
    for shot in plan.shots:
        first = int(round(shot.start * fps))
        last = int(round(shot.end * fps))
        times = [index / fps for index in range(first, max(last, first + 1))]
        side = preferred_side(state, shot)
        solved = [_solve_frame(state, shot, when, side) for when in times]
        positions = _limit_step(_smooth([row[0] for row in solved], SMOOTH_PASSES), MAX_STEP)
        aims = _smooth([row[1] for row in solved], SMOOTH_PASSES)
        rows = [
            [
                round(when, 6),
                round(position[0], 5), round(position[1], 5), round(position[2], 5),
                round(aim[0], 5), round(aim[1], 5), round(aim[2], 5),
                round(shot.fov, 3),
            ]
            for when, position, aim in zip(times, positions, aims)
        ]
        cuts.append(
            {
                "name": shot.name,
                "mode": shot.mode,
                "subject": shot.subject,
                "note": shot.note,
                "side": side,
                "from": round(shot.start, 6),
                "to": round(shot.end, 6),
                "frames": rows,
            }
        )
    return {
        "fps": fps,
        "duration": round(plan.duration(), 6),
        "course": course.concept or course.title,
        "modes": {shot.name: shot.mode for shot in plan.shots},
        "cuts": cuts,
    }


def write_track(track: dict[str, Any], path: str) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(track, handle, separators=(",", ":"))
        handle.write("\n")
    return path

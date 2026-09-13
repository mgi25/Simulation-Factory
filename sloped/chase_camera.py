"""An elevated chase camera: one lens that rides the course behind the pack.

    python tools/sloped_chase_camera.py --seed 5432 --stage all

## The complaint this answers

V21 made every shot readable one shot at a time. Watched end to end the film
still reads as *fast*, and the reason is not the physics - nothing here changes
a marble's speed - but the grammar. `sloped.cameras` places a **blocking**
camera per section: a lens stands at a bearing off the course, the field runs
through its frame, and the edit cuts to the next stand. Measured on the
selected seed's V21 track, the lens teleports 39.7, 33.7, 44.5, 49.3 and 31.7
layout units at five of its ten boundaries, and at three of them the pack's
screen direction turns through eighty degrees or more (cos -0.16, -0.15, -0.28).
Every one of those is a reacquisition: the viewer finds the marbles, watches
them cross, loses them, finds them again somewhere else.

A chase camera has no boundaries to reacquire across. It stands behind and
above the pack, it travels with it, and the course arrives at the top of the
frame before the marbles reach it. The viewer's eye stays on the same objects
moving the same way for as long as the shot lasts.

## What is a chase camera, here

Three points on the racing line and nothing else:

    pack      =  course at (pack progress)
    position  =  pack - forward * trail  +  rise
    aim       =  course at (pack progress + look)

where `forward` is the course's own tangent at the pack. That is the whole of
the design and it buys four things that the bearing-and-extent lens had to be
argued into:

* **The camera follows the course direction** because it is on the course. No
  bearing is measured off a tangent, so `Cut.fixed_heading`'s 180-degree
  reversal at the junction - the fault that moved V19's merge lens 29.7 units
  in one frame - cannot arise.
* **It anticipates the turn** because the aim is `look` units downstream. On a
  bend the aim is already round it while the pack is still entering, so the
  camera yaws into the corner ahead of the field rather than after it.
* **There is no side to choose.** `terrain.lower_side` probes either side of
  the aim and takes the lower ground, and where the two are within a metre of
  each other that verdict flips mid-shot - the defect `Cut.side` exists to
  suppress. A chase camera is directly behind, so the perpendicular never
  enters the arithmetic and there is nothing to flip.
* **The cradle is open to the lens.** `sloped.cameras` found this the hard way:
  a racer sits 1.4 marble diameters below the top of its channel's outer
  acrylic guard, so a camera looking *across* a leg has that wall between it
  and the field at any elevation, and "looking along the channel, or down it
  from ahead, is the only bearing from which the cradle is open". Looking along
  the channel from behind is what a chase camera does for its whole length.

## The one thing that does not work, and why it is worth writing down

The obvious form of the same idea is to put the camera *on the racing line* a
fixed arc length back - `course at (pack - trail)` - which has the appeal of
keeping the lens over the course at all times and therefore never inside the
mountain. It was written that way first and it fails on this course, badly
enough that the first solve held **0.6 racers of 8** through the spinner
corridor with the pack's centroid projecting to x = 3338 of a 1080-wide frame.

The reason is that this is a switchback. Legs 1, 2 and 3 run back and forth
across the same hillside, so two points 44 layout units apart *along the arc*
can be twenty units apart across it with a hairpin in between, and the chord
between them - which is exactly the camera's view axis - cuts the corner and
leaves the pack out to one side. Measured at replay 11.92 s: the pack sits at
leg2 sample 69 of 118, `pack - trail` lands at leg2 sample 27 and `pack + look`
at leg3 sample 25, and the straight line joining those two passes nowhere near
the corner the field is turning.

Arc length is the right measure for *who* to follow and the wrong one for
*where to stand*. So the trail is a straight-line offset along the local
tangent, which is what a racing game does, and the look-ahead stays an arc
length because it is asking a question about the course rather than about the
camera.

## And the aim is a point *on* the course, not a point toward it

The second form that does not work is an aim interpolated between the pack and
a point downstream - `pack + (ahead point - pack) * fraction` - which reads as
the obvious way to trade look-ahead against keeping the field centred. It puts
the aim **under the mountain**.

A chord between two points of a concave-upward curve lies below the curve, and
the first descent is concave upward: it leaves the launch steeply and flattens
into leg 1. The racing line hugs a bench cut 2.8 layout units deep, so a point
two units below the line is two units inside the hillside - and `terrain`
agrees. Measured at replay 8.883 s, the aim sat at y 25.81 against a ground
height of 28.14, the sight line was buried for its last 4 per cent, and the
lift loop ran all the way to its 26-unit ceiling trying to see over a hill that
was not the obstruction. The shot came out at 52 degrees of elevation - a plan
view - for a fault that had nothing to do with where the camera was standing.

`cameras._on_course` already carries this argument for the pack aim: "the aim
is the course's own point at the pack's mean progress. It is on the racing line
by construction, at every field spread and every turn." The look-ahead point is
held to the same rule, and `look` is therefore an arc length rather than a
blend. One number, one meaning, and it cannot leave the course.

## The look-ahead is an angle budget, not a distance

And then the switchback takes *that* apart too, because on a course that
doubles back "fifteen units ahead" is around the corner and pointing the other
way. Measured through the spinner corridor with a flat 15-unit look-ahead: the
pack sat at leg2 sample 96 and the aim at leg3 sample 23, the view axis pointed
down a leg the field was not on, and the eight racers projected to x = 1500 to
1700 of a 1080-wide frame - **all eight outside it, for 1.3 seconds.**

So `look` is a *maximum* and the real constraint is angular: the aim may sit at
most `MAX_LOOK_YAW` degrees of yaw off the direction from the lens to the pack.
The solve walks the look-ahead down from `look` until it is inside that budget,
which on a straight leaves it untouched and into a hairpin pulls it in to
nothing - the camera stops looking round the corner exactly when looking round
the corner would mean looking away from the race.

That is also the honest form of the brief's "anticipate turns rather than react
late": the anticipation is worth six degrees of frame, and no more, because the
frame is 10.36 degrees wide either side of centre and the pack has to live in
the rest of it.

The chosen distance is smoothed over frames before the aim is rebuilt from it,
because a per-frame search is a per-frame decision and a decision can change
its mind - the same argument `Cut.side` carries in `sloped.cameras`.

## The trail breathes with the field

A constant trail frames a constant amount of course, and the field on this
course is not a constant size. Measured on the selected seed the pack spans 3.5
layout units in the spinner corridor and 31 across the two branch lobes, a
factor of nine; a trail that holds the branches holds a marble at 29 px through
the corridor, and a trail that holds the corridor loses five racers of eight at
the branches. Swept at the branches, `trail` 24 to 46 moves coverage 0.62 to
0.79 and racer scale 41.3 px to 28.6 - a straight trade, with **no value
anywhere on it that reaches the 48 px floor**, because two lobes 31 units apart
do not fit a phone frame at a readable size and no camera position changes that.

So the trail is `phase.trail` plus `phase.spread` of however far the subject set
is spread beyond `SPREAD_FREE`, and the rise scales with it so the elevation
angle - and therefore the framing - is the same shot at both ends. The camera
closes in when the field bunches and pulls out when it strings out, which is
what a human operator does and what the brief means by "do not attempt to keep
every marble huge if they are physically far apart".

The spread is measured as the furthest subject racer from the pack point, in
layout units, and smoothed over half a second before it is used: an unfiltered
spread is a step function every time the trimmed set changes membership.

## Why the pack is not the leader

Naively the camera follows the front marble. On this course that empties the
frame: measured on the selected seed, the field is strung out over 59 layout
units of arc at 18.0 s and 54 at 21.0 s, so a lens holding the leader at a
useful scale has most of the race behind it and out of shot.

So the subject is a **robust centre** of the field rather than its front, and
`TARGETS` offers five of them - the mean, the median, a trimmed mean that drops
detached outliers, the leader, and an adaptive blend that leans toward the
front when the field is tight and toward the median when it is not. Which one
ships is a measured question, not a taste one; `tools/sloped_chase_camera.py
--stage target` runs the same solve under each and prints the readability of
all five. See `docs/sloped_race_v22_chase_camera.md` for the table.

**The centre is taken per route and then averaged.** After the fork the field
is on two lobes whose arc parameterisations are different lengths - blue's lead
and run are 13.8 + 59.5 sim units against orange's 21.9 + 49.4 - so a single
scalar progress means two different places on the two routes. Each route's own
members give that route's own mean, each is projected onto its own run, and the
two points are averaged by member count. This is `cameras._pack_aim`'s argument
applied to the pack and look-ahead points alike.

It is also what makes the fork work without a special case. Upstream of the
divider both routes share every run, so `pack - trail` is the same point on
both and the camera is behind the decision; downstream `pack + look` has split,
so the aim is the midpoint of two diverging mouths - which is the divider. The
camera is behind the fork looking at the fork because that is where those two
expressions land, not because a node was typed in.

## The route weights are smoothed, and that is not cosmetic

Member counts are integers. A marble crossing from one lobe's share to the
other's steps the weights by 1/n, and a step in the weights is a step in both
solved points - at the fork the lobes are 31 layout units apart, so one marble
changing sides moves the camera about four units in a single frame. Smoothing
the *points* afterwards turns that step into a ramp and does not remove it.

So the **weights** are smoothed before they are used, over about a third of a
second, and the points that come out of them are continuous to begin with.

## Phases are set-points, not stands

`ChasePhase` carries a trail, a rise, a lead and a field of view, and the
solver interpolates between consecutive phases with a smoothstep over the
phase's own `ramp`. The chase is therefore solved as **one continuous path**
and sliced into cuts afterwards, purely so that the reports have somewhere to
hang per-section numbers. A boundary between two chase phases is not a cut: the
last row of one and the first row of the next are adjacent samples of the same
curve, and `readability.continuity_report` measures the lens travelling 0.1
layout units across them against V21's 30 to 50.

That is the "fewer camera phases" of the brief expressed as a number rather
than as a count of names.

## The bookends are V21's, and one of them is turned round

The start lens and the finish lens are lifted from
`sloped.cameras.EDITS["v212"]` and solved by `cameras.build_track` itself. The
start is a machine shot of a field that has not moved - there is no pack to
chase - and the finish is the strongest shot in the film, which the brief says
not to replace without measured evidence of an improvement. There is none, so
it is not replaced.

**The start's bearing is the exception, and it is a bearing and nothing else.**
V21 photographs the trapdoor from 28 degrees - from downstream, looking back up
at the field as it drops - and a chase camera looks the other way down the same
course. Joined, the two reverse the pack's screen direction at cosine
**-1.00**: the marbles travel down the frame and then up it, which is the one
discontinuity `readability.MAX_TURN` exists to forbid and the worst join in the
whole track.

Swung to 230 degrees - behind the machine and round from it, looking down the
course the field is about to run - the join comes to **+0.81**: the pack leaves
the start shot travelling the way it arrives in the chase, and the reversal is
gone rather than reduced.

**The first sweep of this picked the wrong bearing, and it picked it for
exactly the reason `sloped.cameras` already warns about.** Swept on the frustum
count, 200 degrees looked best - eight racers of eight in frame against 28's
6.4, coverage 1.000 against 0.795. Swept again with `readability.visibility_report`,
which walks the drawn course as solid geometry, 200 turns out to put **three**
of those eight on screen and hide five behind the machine's own housing. V21's
own findings file says it in as many words - "a frustum count is not
visibility" - and this module repeated the mistake on its first pass.

Measured on what a viewer can actually see, over the release window:

    bearing   px_median  coverage  in frame  visible  hidden  handover
        28         76.0     0.795       6.4     4.76    0.256    -1.00
       180         71.1     1.000       8.0     3.98    0.502    -0.16
       200         71.0     1.000       8.0     2.91    0.636    -0.07
       230         70.3     0.852       6.8     4.81    0.299    +0.81

230 is **level** with V21 on racers actually on screen - 4.81 against 4.76, and
at a coarser sampling stride the two swap places - and it ends the reversal.
The claim is only that the swing does not cost visibility while it buys a
handover of +0.81 against -1.00; 200, which the frustum count preferred, would
have cost 1.9 racers of the 4.8 that were on screen. Six pixels of median scale
is the whole price.

**Both** windows swing, not only the release. Left at 28 the opening shot and
the release disagree across the omission - the pack reverses at -0.55 there
instead - and swinging it costs nothing: the opening reads 78.0 px against
73.5, with 7.50 racers visible against 7.45.

## Where the ground comes in

A camera on the course centreline plus `rise` is above the channel by
construction, but the *sight line* from it to an aim `trail + lead` units
downstream can still be crossed by the mountain - a descent that falls away
under the lens, a hairpin whose inside flank stands between the two points. The
same treatment as `sloped.cameras`: raise until it clears.

The difference is that a chase camera cannot afford a per-frame answer. Lifting
one frame and not the next is a camera that bobs. So the lift is computed per
frame, run through a **forward-looking running maximum** - the camera is already
high by the time it needs to be, which is the same anticipation the lead point
gives the yaw - and then smoothed before it is added.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any, Sequence

from sloped import cameras, layout, terrain
from sloped.race import ROUTE_RUNS
from sloped.scale import SIM_TO_LAYOUT

__all__ = [
    "ChasePhase",
    "PHASES",
    "TARGETS",
    "build_chase",
    "chase_report",
    "check_chase",
    "course_at",
    "edit_plan",
    "pack_anchor",
    "route_offsets",
]


# --- constants --------------------------------------------------------------

# How far the sight line has to clear the ground, and how far the camera may be
# raised to get there. `SIGHT_MARGIN` is `sloped.cameras`' own - one marble
# diameter of daylight - and the ceiling is expressed in layout units of extra
# height rather than in degrees of elevation, because a chase camera has no
# fixed elevation to raise: its pitch falls out of `rise`, `trail` and `lead`.
SIGHT_MARGIN = 0.6
GROUND_MARGIN = 1.2
MAX_EXTRA_RISE = 26.0
RISE_STEP = 1.0

# How far ahead the lift looks, in frames. A quarter of a second: enough that
# the camera is over the lip before the lip is between it and the aim, short
# enough that it is not riding high through a shot that does not need it.
LIFT_LOOKAHEAD = 15

# Smoothing, in passes of a symmetric three-tap mean. `cameras.SMOOTH_PASSES`
# is 14, which is a standard deviation of about three frames - right for a
# centroid that only has to stop shivering inside a two-second stand. A chase
# camera is the *whole* of the movement a viewer sees for thirteen seconds, so
# it is filtered about four times as hard.
PATH_PASSES = 54
WEIGHT_PASSES = 30
LIFT_PASSES = 26

# What `chase_report` calls "the course ahead": how far downstream of the pack
# to sample the racing line when asking whether a viewer can see where the race
# is going, and how many samples to take along it.
AHEAD_SPAN = 46.0
AHEAD_SAMPLES = 24

# How fast the chase may turn and travel, per frame at the replay's 60 Hz.
#
# `MAX_YAW_RATE` caps the course tangent the camera hangs off; at the longest
# trail in `PHASES` it is worth 34 * sin(0.75 deg) = 0.45 layout units of lens
# movement a frame, which leaves room under `cameras.MAX_CAMERA_STEP` for the
# pack's own travel.
#
# `MAX_LENS_STEP` is the backstop on the lens, under the 1.2 the production
# checker allows inside a shot.
#
# **The aim's limit is not a constant, and finding that out took a second
# race.** `check_track` judges an aim against the fastest racer in its own cut -
# "an aim point that moves faster than the fastest racer is what snapping rather
# than following actually means" - so a fixed 0.55 passes on a quick race and
# fails on a slow one: on the twenty-six-second proof seed the fork's fastest
# racer covers 0.384 layout units a frame and the aim was moving 0.515. The
# chase aim moves for two reasons, the pack's own travel and the look-ahead
# lengthening or shortening into a bend, and only the first of those is the
# race. So the limit is the field's own speed, per frame, with the same
# `MARBLE_RADIUS` floor the checker uses and none of its 1.15 headroom - which
# leaves the headroom as margin rather than spending it.
MAX_YAW_RATE = 0.75
MAX_LENS_STEP = 0.85

# How far off the direction to the pack the aim may sit, in degrees of yaw.
#
# **This is the number that makes a look-ahead survive a switchback**, and it is
# read off the delivery frame rather than chosen. Godot keeps the vertical
# angle, so at fov 36 on 1080x1920 the horizontal half-angle is
# atan(tan(18 deg) * 1080/1920) = 10.36 degrees - the *narrow* axis of a
# portrait frame. Spend six of those ten on the look-ahead and four are left
# for the pack's own width, which is what a field spread over twenty layout
# units needs at a 30-unit trail.
MAX_LOOK_YAW = 6.0

# How the trail answers the field's own spread. `SPREAD_FREE` is the radius a
# phase's own `trail` already frames - about two thirds of the half-height a
# 36-degree lens covers at 26 units - and past it every extra unit of spread
# buys `SPREAD_GAIN` units of trail. 1.35 is a little under the 1/tan(18 deg)
# = 3.08 that would hold the extra spread exactly, because holding it exactly
# is what makes the racers dots; this holds most of it and lets the tail leave.
SPREAD_FREE = 9.0
SPREAD_GAIN = 1.35
MAX_SPREAD_TRAIL = 22.0

# How many steps the look-ahead is shortened in when the angle budget is spent.
LOOK_STEPS = 20

# The shortest a phase may be before it is absorbed into the one before it.
# `cameras.check_track` calls anything under a third of a second a glitch.
MIN_PHASE_SECONDS = 0.5

WIDTH = 1080
HEIGHT = 1920


# --- the course, as arc length ---------------------------------------------


def route_offsets(machine) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    """Arc offset of every run within every route the machine carries.

    The same table `cameras._route_offsets` builds and for the same reason: a
    course built without the fork has no orange lead, so orange is not on offer
    and must not be tabulated. Rebuilt here rather than imported because this
    module also needs the route totals to extrapolate past the end.
    """
    offsets: dict[str, dict[str, float]] = {}
    totals: dict[str, float] = {}
    for route, names in ROUTE_RUNS.items():
        if any(name not in machine.runs for name in names):
            continue
        total = 0.0
        table: dict[str, float] = {}
        for name in names:
            table[name] = total
            total += machine.runs[name].sim_arc[-1]
        offsets[route] = table
        totals[route] = total
    return offsets, totals


def course_at(
    machine, offsets, route: str, distance: float
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """The racing line at `distance` sim units along `route`: point and tangent.

    In layout units, with a marble's radius added to the height, so the point
    is where a racer's centre rides rather than where the channel floor is -
    the same convention as `cameras._on_course`, which this agrees with sample
    for sample inside the course and `tests/test_sloped_chase.py` pins.

    **Outside the course it extrapolates rather than clamping, and that is the
    point of writing it out.** A chase camera stands `trail` behind the pack,
    and at the gate the pack is barely onto `launch`, so the camera's own point
    is thirty layout units *before* the course begins. Clamped, it would sit on
    the first sample and stay there while the field pulled away, which is a
    static camera for the first second of the chase and a lens inside the start
    machine for the rest of it. Extrapolated along the first tangent it is
    behind the start looking down the course, which is the shot.

    The same applies at the far end, where `pack + lead` runs past the line.
    """
    names = [name for name in ROUTE_RUNS[route] if name in machine.runs]
    table = offsets[route]
    total = table[names[-1]] + machine.runs[names[-1]].sim_arc[-1]

    if distance < 0.0:
        run, at, overshoot = machine.runs[names[0]], 0, distance
    elif distance > total:
        run = machine.runs[names[-1]]
        at, overshoot = len(run.sim_path) - 1, distance - total
    else:
        chosen = names[0]
        for name in names:
            if distance >= table[name] - 1e-9:
                chosen = name
        run = machine.runs[chosen]
        at, overshoot = run.index_at_length(distance - table[chosen]), 0.0

    at = min(max(at, 0), len(run.sim_path) - 1)
    tangent = run.tangents[min(at, len(run.tangents) - 1)]
    point = run.sim_path[at]
    return (
        (
            (point[0] + tangent[0] * overshoot) * SIM_TO_LAYOUT,
            (point[1] + tangent[1] * overshoot) * SIM_TO_LAYOUT + layout.MARBLE_RADIUS,
            (point[2] + tangent[2] * overshoot) * SIM_TO_LAYOUT,
        ),
        (float(tangent[0]), float(tangent[1]), float(tangent[2])),
    )


# --- who the camera is of ---------------------------------------------------


# The targeting rules, as the brief names them. Each takes the live racers'
# progress and returns the subset the camera is of; the anchor is that subset's
# own per-route mean, computed downstream, so a rule only has to decide
# membership.
TARGETS = ("centroid", "median", "trimmed", "leader", "adaptive")

# How far from the median a racer may be, in layout units of arc, before
# `trimmed` stops counting it as part of the pack. 26 is a little over half the
# widest the field is ever spread; past that a marble is not in the same piece
# of the race as the middle of the field and framing it costs everyone else
# their scale.
TRIM_BAND = 26.0

# The most racers `trimmed` will drop. Two of eight: a rule that can drop four
# is a rule that can quietly become `leader` at the moment the field splits.
MAX_TRIMMED = 2

# `adaptive` leans toward the leader by this fraction of the gap when the field
# is tight, and toward the median as it spreads.
ADAPTIVE_LEAN = 0.45
ADAPTIVE_SPREAD = 30.0


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return 0.5 * (ordered[middle - 1] + ordered[middle])


def pack_anchor(
    values: dict[int, float], rule: str, band: float = TRIM_BAND
) -> list[int]:
    """Which racers the camera is of, under one targeting rule.

    `values` is progress in **layout** units of arc for the racers still in the
    race. The return is the subject set; an empty input returns an empty set
    and the caller holds its previous frame.
    """
    if not values:
        return []
    live = sorted(values, key=lambda marble: -values[marble])
    if rule == "leader":
        return live[:1]
    if rule == "centroid":
        return list(live)
    if rule == "median":
        return list(live)
    if rule == "trimmed":
        kept = list(live)
        for _ in range(MAX_TRIMMED):
            if len(kept) <= 2:
                break
            middle = _median([values[marble] for marble in kept])
            worst = max(kept, key=lambda marble: abs(values[marble] - middle))
            if abs(values[worst] - middle) <= band:
                break
            kept.remove(worst)
        return kept
    if rule == "adaptive":
        middle = _median([values[marble] for marble in live])
        front = values[live[0]]
        spread = max(front - middle, 0.0)
        lean = ADAPTIVE_LEAN * max(0.0, 1.0 - spread / ADAPTIVE_SPREAD)
        centre = middle + lean * (front - middle)
        kept = [marble for marble in live if abs(values[marble] - centre) <= band]
        return kept or live[:2]
    raise KeyError(f"no such targeting rule: {rule!r}")


def _anchor_of(rule: str, values: dict[int, float], chosen: Sequence[int]) -> float:
    """The scalar progress the subject set sits at, under one rule."""
    picked = [values[marble] for marble in chosen] or list(values.values())
    if rule == "median":
        return _median(picked)
    if rule == "leader":
        return max(picked)
    return sum(picked) / len(picked)


# --- phases -----------------------------------------------------------------


@dataclass
class ChasePhase:
    """One stretch of the chase and the set-points it holds.

    Every distance is in **layout units**, which is what the readability
    thresholds and the frame arithmetic are in; the solve converts to the sim
    units the course's arc tables are written in.
    """

    name: str
    until: str                  # the station in `cameras.STATIONS` that ends it
    trail: float                # straight-line offset back along the tangent
    rise: float                 # height above the racing line, at the position
    look: float                 # arc length ahead of the pack, for the aim
    spread: float = SPREAD_GAIN  # units of trail per unit of field spread
    fov: float = 36.0
    ramp: float = 0.9           # seconds over which its set-points blend in
    hold: float = 0.0           # extra seconds after the station is reached
    min_seconds: float = 0.8
    max_seconds: float = 0.0

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "until": self.until,
            "trail": self.trail,
            "rise": self.rise,
            "look": self.look,
            "spread": self.spread,
            "fov": self.fov,
            "ramp": self.ramp,
        }


# The four phases the brief asks for, and no more. Each is a set of numbers the
# solve ramps to; none of them is a place the camera stands.
#
# The set-points are explained in `docs/sloped_race_v22_chase_camera.md` and
# were swept rather than chosen. In outline:
#
# * `trail` decides scale, because a chase camera's subject distance is roughly
#   `hypot(trail, rise)` and a racer's diameter in the delivery frame is
#   `2 * 0.285 / depth / (2 * tan(fov/2)) * 1920` - about `1684 / depth` px at
#   fov 36. The 48 px floor is therefore a depth of 35 layout units, which is
#   where these sit when the field is tight.
# * `rise` decides how much of the course ahead is in frame and how much of the
#   channel wall is between the lens and the cradle.
# * `lead` decides where the pack sits vertically: the aim is the middle of the
#   frame, so a longer lead pushes the field down it.
PHASES: tuple[ChasePhase, ...] = (
    # The first descent and both turns. The field leaves the drum in a bunch
    # and is spread over 28 layout units by the bottom of leg 1, so this is
    # the phase with the most arc to hold and the longest trail.
    ChasePhase("descent", "leg2_start", trail=26.0, rise=13.0, look=16.0, spread=0.6, ramp=0.5),
    # The spinner corridor. The field arrives strung out and leaves it bunched -
    # measured on the selected seed the spread collapses from 28 layout units
    # at 11.0 s to 3.5 at 13.0 - so the camera closes in as the corridor does
    # the bunching, and the obstacle is in frame before the marbles reach it
    # because the aim is 15 units downstream of them.
    ChasePhase("obstacle", "sweep", trail=19.0, rise=11.0, look=15.0, spread=1.8, ramp=1.1),
    # The fork. Rises and widens, and stays behind the divider without being
    # told to: upstream of the fork both routes share their runs, so the
    # position is on the shared leg and only the aim has split.
    ChasePhase("fork", "branch_in", trail=28.0, rise=20.0, look=14.0, spread=0.2, ramp=1.2),
    # Both lobes, and the junction they come back together at. The widest and
    # highest of the four, because this is the stretch where the field is on
    # two lines 31 layout units apart and the brief is explicit that keeping
    # every marble large here is not the goal.
    ChasePhase("branches", "branch_out", trail=34.0, rise=26.0, look=18.0,
               spread=0.4, ramp=1.3),
    ChasePhase("merge", "", trail=26.0, rise=34.0, look=16.0, spread=0.45, ramp=1.2),
)


# --- the solve --------------------------------------------------------------


def _smooth(rows: list[tuple[float, ...]], passes: int) -> list[tuple[float, ...]]:
    current = [tuple(row) for row in rows]
    if len(current) < 3:
        return current
    width = len(current[0])
    for _ in range(passes):
        following = []
        for index in range(len(current)):
            a = current[max(index - 1, 0)]
            b = current[index]
            c = current[min(index + 1, len(current) - 1)]
            following.append(
                tuple((a[axis] + b[axis] + c[axis]) / 3.0 for axis in range(width))
            )
        current = following
    return current


def _smooth_scalars(values: list[float], passes: int) -> list[float]:
    return [row[0] for row in _smooth([(value,) for value in values], passes)]


def _slew(vectors: list[tuple[float, ...]], rate: float) -> list[tuple[float, float, float]]:
    """Unit-length course tangents, forbidden to turn faster than `rate` a frame.

    **The hairpins are why this exists.** Legs 1, 2 and 3 double back, so the
    course tangent at the pack swings through most of 180 degrees in the twenty
    frames the field takes to round an apex, and the camera hangs off that
    tangent at a 26-unit radius: 3.0 degrees a frame of yaw is 1.4 layout units
    a frame of lens, which `cameras.check_track` reports as a cut in the middle
    of a shot and a viewer sees as a whip.

    Smoothing cannot fix it. A symmetric mean spreads a fast turn over its own
    width and leaves the integral - the camera still gets all the way round,
    just less abruptly - and at 54 passes the descent still turned 3.00 degrees
    in a frame. A slew limit changes the answer rather than the schedule: the
    camera **lags** into the apex and catches up on the way out, which is what a
    chase camera does on a switchback and what a viewer reads as the camera
    leaning into the corner.

    Causal on purpose. A symmetric limiter would start turning before the course
    does, which is anticipation the course has not earned.
    """
    if not vectors:
        return []
    limit = math.radians(rate)

    def unit(vector):
        length = math.sqrt(sum(value * value for value in vector))
        if length < 1e-9:
            return None
        return tuple(value / length for value in vector)

    first = unit(vectors[0]) or (0.0, 0.0, 1.0)
    out = [first]
    for vector in vectors[1:]:
        target = unit(vector)
        if target is None:
            out.append(out[-1])
            continue
        previous = out[-1]
        cosine = min(max(sum(previous[a] * target[a] for a in range(3)), -1.0), 1.0)
        angle = math.acos(cosine)
        if angle <= limit or angle < 1e-9:
            out.append(target)
            continue
        # Spherical interpolation toward the target, stopped at the limit. The
        # degenerate case - an exact reversal, where the rotation plane is
        # undefined - takes the previous frame's answer and waits for the
        # tangent to leave the antipode, which it does within a frame.
        sine = math.sin(angle)
        if sine < 1e-9:
            out.append(previous)
            continue
        a = math.sin(angle - limit) / sine
        b = math.sin(limit) / sine
        stepped = tuple(previous[axis] * a + target[axis] * b for axis in range(3))
        out.append(unit(stepped) or previous)
    return out


def _follow(rows: list[tuple[float, ...]], limit) -> list[tuple[float, ...]]:
    """A path that never moves more than `limit` in one frame, and lags if it must.

    The backstop behind the slew limit, and the one check that cannot be argued
    with: `cameras.MAX_CAMERA_STEP` is 1.2 layout units and a chase has no cuts
    to hide a jump behind. Where the raw path is inside the limit this is the
    identity, so on the stretches of the chase that are not a turn it changes
    nothing at all.
    """
    if not rows:
        return []
    limits = limit if isinstance(limit, (list, tuple)) else [limit] * len(rows)
    out = [tuple(rows[0])]
    for step, row in enumerate(rows[1:], start=1):
        previous = out[-1]
        allowed = float(limits[min(step, len(limits) - 1)])
        delta = [row[axis] - previous[axis] for axis in range(len(row))]
        moved = math.sqrt(sum(value * value for value in delta))
        if moved <= allowed or moved < 1e-12:
            out.append(tuple(row))
            continue
        scale = allowed / moved
        out.append(tuple(previous[axis] + delta[axis] * scale for axis in range(len(row))))
    return out


def _ease(fraction: float) -> float:
    value = min(max(fraction, 0.0), 1.0)
    return value * value * (3.0 - 2.0 * value)


def _station_time(track: dict[str, Any], machine, station: str) -> float:
    """When the leader first reaches one station, from the replay's own progress.

    `cameras.STATIONS` is the shared table and this is the same walk over it
    that `cameras._station_time` does; it is written out here so that the chase
    does not import a private name to find its own boundaries.
    """
    offsets, _totals = route_offsets(machine)
    run_name, fraction = cameras.STATIONS[station]
    route = next(
        (name for name, table in offsets.items() if run_name in table),
        next(iter(offsets)),
    )
    if run_name not in offsets[route]:
        return track["times"][-1]
    target = offsets[route][run_name] + fraction * machine.runs[run_name].sim_arc[-1]
    for index, when in enumerate(track["times"]):
        if max(track["progress"][m][index] for m in track["marbles"]) >= target:
            return when
    return track["times"][-1]


def _crossings(replay: dict[str, Any]) -> dict[int, float]:
    out: dict[int, float] = {}
    for event in replay["events"]:
        if event["kind"] == "finish_line":
            marble = int(event["id"])
            out[marble] = min(out.get(marble, math.inf), float(event["t"]))
    return out


# Where the start windows stand, in degrees off the course's forward at the
# start node. See the module docstring: 28 is V21's and reverses the pack
# against the chase; 230 is behind the machine and round from it, which is the
# only bearing that both ends the reversal and puts more of the field on screen
# than V21 does.
START_BEARING = 230.0


def edit_plan(edit: "str | Sequence[tuple]") -> tuple[tuple, ...]:
    """An edit map, given either its name in `cameras.EDITS` or the plan itself.

    **A named plan is a plan that lives in `sloped.cameras`, and not every plan
    does.** V22.1's start windows are solved by `v221_shuffle.plan_windows` from
    a `StartPlan` - the legs are computed by `constant_rate_legs` rather than
    typed - so the plan exists only once something has built it, and putting a
    placeholder for it in `cameras.EDITS` would make the module that owns the
    lenses import the module that owns the prototypes. Accepting the plan
    directly costs one `isinstance` and keeps every existing caller, which
    passes a name, reading exactly as it did.
    """
    if isinstance(edit, str):
        return cameras.EDITS[edit]
    return tuple(tuple(entry) for entry in edit)


def _bookends(
    replay: dict[str, Any],
    machine,
    fps: int,
    edit: "str | Sequence[tuple]" = "v212",
    start_bearing: float = START_BEARING,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """V21's start and finish, solved by `sloped.cameras` itself.

    Lifted rather than reimplemented: these two shots are not chase shots and
    the brief keeps them. Taking them from `EDITS[edit]` means a change to
    either in production reaches this prototype without an edit here, and means
    the opening of a V22 proof is frame-for-frame the opening of the V21 film.
    """
    plan = edit_plan(edit)
    lenses = {cut.name: cut for cut in cameras.SECTIONS}
    # **A window the replay does not reach is dropped, not solved.** The edit's
    # times are the production seed's, and a shorter replay - a twelve-second
    # proof race, a run that was cut off - simply has no frames in the finish
    # window. `cameras.build_track` raises "the edit kept nothing" on that,
    # which is the right answer for a film and the wrong one for a solver that
    # should hand back whatever chase the replay can carry. Production replays
    # are always long enough, which is exactly why this needed a test.
    horizon = float(replay["frames"][-1]["t"]) if replay.get("frames") else 0.0
    def reachable(entry) -> bool:
        return float(entry[1]) < horizon - 1e-6
    opening = [list(entry) for entry in plan if entry[0] == "start" and reachable(entry)]
    closing = [entry for entry in plan if entry[0] == "finish" and reachable(entry)]
    if not opening and not closing:
        raise ValueError(f"the {edit!r} edit has no start or no finish window")
    if start_bearing is not None:
        for entry in opening:
            overrides = dict(entry[3]) if len(entry) > 3 else {}
            overrides["bearing"] = float(start_bearing)
            if len(entry) > 3:
                entry[3] = overrides
            else:
                entry.append(overrides)
    opening = [tuple(entry) for entry in opening]
    front = (
        cameras.build_track(
            replay, machine, sections=(lenses["start"],), fps=fps, edit=tuple(opening)
        )
        if opening
        else None
    )
    back = (
        cameras.build_track(
            replay, machine, sections=(lenses["finish"],), fps=fps, edit=tuple(closing)
        )
        if closing
        else None
    )
    return front, back


def build_chase(
    replay: dict[str, Any],
    machine,
    phases: Sequence[ChasePhase] = PHASES,
    fps: int = 60,
    rule: str = "adaptive",
    bookends: bool = True,
    edit: "str | Sequence[tuple]" = "v212",
    start_bearing: float = START_BEARING,
) -> dict[str, Any]:
    """A camera track in `sloped.cameras`' own schema, solved as one chase.

    The output is deliberately the same document `cameras.build_track` writes -
    `cuts`, each with `frames` of `[t, px, py, pz, ax, ay, az, fov]`, plus the
    edit map - so `sloped_race_scene.gd` renders it with no change,
    `cameras.check_track` and `cameras.frame_report` check it, and
    `sloped.readability` measures it. A new camera language should not need a
    new renderer to look at it.
    """
    if rule not in TARGETS:
        raise KeyError(f"no such targeting rule: {rule!r}")
    track = cameras.progress_track(replay, machine)
    offsets, _totals = route_offsets(machine)
    times = track["times"]
    frames = replay["frames"]
    crossed = _crossings(replay)
    horizon = times[-1]
    cfg = terrain.terrain_config(machine.runs)

    front = back = None
    chase_from, chase_to = 0.0, horizon
    if bookends:
        front, back = _bookends(replay, machine, fps, edit, start_bearing)
        if front is not None:
            chase_from = float(front["cuts"][-1]["to"])
        if back is not None:
            chase_to = float(back["cuts"][0]["from"])
    if chase_to - chase_from <= 1e-6:
        raise ValueError("the replay leaves no room for a chase")

    # The phase boundaries, from the leader's own station clock, clamped into
    # the chase's window. The same rule `cameras.build_track` uses: a race that
    # jams at the fork should not leave the fork on schedule.
    bounds: list[tuple[float, float]] = []
    start = chase_from
    for phase in phases:
        if phase.until:
            end = _station_time(track, machine, phase.until) + phase.hold
        else:
            end = chase_to
        end = max(end, start + phase.min_seconds)
        if phase.max_seconds > 0.0:
            end = min(end, start + phase.max_seconds)
        end = min(max(end, start), chase_to)
        bounds.append((start, end))
        start = end
    bounds[-1] = (bounds[-1][0], chase_to)

    # **A phase the replay left no room for is absorbed by its neighbour.**
    # Phases are set-points rather than stands, so dropping one means its
    # numbers are never reached - which is the right answer, and much better
    # than emitting a shot of a tenth of a second. `cameras.build_track` does
    # the same for a cut, and for the same reason: on a race whose stations
    # land differently the later boundaries pile up at the horizon.
    kept_phases: list[ChasePhase] = []
    kept_bounds: list[tuple[float, float]] = []
    for phase, (low, high) in zip(phases, bounds):
        if high - low < MIN_PHASE_SECONDS and kept_bounds:
            kept_bounds[-1] = (kept_bounds[-1][0], high)
            continue
        kept_phases.append(phase)
        kept_bounds.append((low, high))
    if not kept_phases:
        kept_phases, kept_bounds = [phases[0]], [(chase_from, chase_to)]
    kept_bounds[-1] = (kept_bounds[-1][0], chase_to)
    phases, bounds = tuple(kept_phases), kept_bounds

    indices = [i for i, when in enumerate(times) if chase_from <= when <= chase_to]
    if not indices:
        raise ValueError("the replay leaves no room for a chase")

    # Which phase each frame belongs to, and the eased blend into it. The blend
    # runs over `ramp` seconds ending at the boundary, so a phase's set-points
    # are reached *at* its own start rather than a ramp later.
    def settings(when: float) -> tuple[float, float, float, float, float]:
        chosen = len(phases) - 1
        for step, (low, high) in enumerate(bounds):
            if when <= high:
                chosen = step
                break
        phase = phases[chosen]
        values = (phase.trail, phase.rise, phase.look, phase.spread, phase.fov)
        if chosen == 0:
            return values
        ramp = max(phases[chosen].ramp, 1e-6)
        into = when - bounds[chosen][0]
        if into >= ramp:
            return values
        before = phases[chosen - 1]
        earlier = (before.trail, before.rise, before.look, before.spread, before.fov)
        blend = _ease(into / ramp)
        return tuple(
            earlier[axis] + (values[axis] - earlier[axis]) * blend for axis in range(5)
        )

    # --- the raw path -------------------------------------------------------
    #
    # Per frame: the live field, the subject set under the rule, that set's own
    # mean progress **per route**, and the two course points those give.
    per_route: list[dict[str, float]] = []
    weights: list[dict[str, float]] = []
    spreads: list[float] = []
    held: tuple[dict[str, float], dict[str, float]] | None = None
    for index in indices:
        when = times[index]
        values = {
            marble: track["progress"][marble][index] * SIM_TO_LAYOUT
            for marble in track["marbles"]
            if crossed.get(marble, math.inf) > when
        }
        chosen = pack_anchor(values, rule)
        if not chosen:
            # Everyone has crossed. Hold the last real answer rather than
            # inventing one, which is what the finish lens is there to cover.
            per_route.append(held[0] if held else {"blue": 0.0})
            weights.append(held[1] if held else {"blue": 1.0})
            spreads.append(spreads[-1] if spreads else 0.0)
            continue
        anchor = _anchor_of(rule, values, chosen)
        spreads.append(max(abs(values[marble] - anchor) for marble in chosen))
        grouped: dict[str, list[int]] = {}
        for marble in chosen:
            route = track["routes"].get(marble) or "blue"
            grouped.setdefault(route if route in offsets else "blue", []).append(marble)
        means = {
            route: _anchor_of(rule, values, members) for route, members in grouped.items()
        }
        share = {
            route: len(members) / len(chosen) for route, members in grouped.items()
        }
        # Where a route is unrepresented its mean is the overall anchor, so a
        # weight that fades in from zero fades in at the right place rather
        # than from wherever that route's last member was.
        for route in offsets:
            means.setdefault(route, anchor)
            share.setdefault(route, 0.0)
        per_route.append(means)
        weights.append(share)
        held = (means, share)

    routes = sorted(offsets)
    smoothed_weights = _smooth(
        [tuple(row.get(route, 0.0) for route in routes) for row in weights],
        WEIGHT_PASSES,
    )
    smoothed_means = _smooth(
        [tuple(row.get(route, 0.0) for route in routes) for row in per_route],
        PATH_PASSES // 3,
    )
    smoothed_spread = _smooth_scalars(spreads, PATH_PASSES)

    # The pack, the course direction at it and the point `lead` downstream, all
    # three averaged across the routes the subject set is on. The tangent is
    # accumulated and then renormalised, which is what makes a hairpin behave:
    # where a field straddles an apex the two contributions oppose and the sum
    # is short, so the trail shortens and the camera closes in through the turn
    # instead of whipping around it.
    anchors: list[tuple[float, float, float]] = []
    forwards: list[tuple[float, float, float]] = []
    centres: list[list[float]] = []
    shares: list[list[float]] = []
    settings_rows: list[tuple[float, float, float, float, float]] = []
    for step, index in enumerate(indices):
        values = settings(times[index])
        settings_rows.append(values)
        _trail, _rise, look, _spread, _fov = values
        share = smoothed_weights[step]
        means = smoothed_means[step]
        total = sum(share) or 1.0
        here = [0.0, 0.0, 0.0]
        forward = [0.0, 0.0, 0.0]
        for slot, route in enumerate(routes):
            weight = share[slot] / total
            if weight <= 1e-9:
                continue
            centre = means[slot] / SIM_TO_LAYOUT
            point, tangent = course_at(machine, offsets, route, centre)
            for axis in range(3):
                here[axis] += point[axis] * weight
                forward[axis] += tangent[axis] * weight
        anchors.append(tuple(here))
        forwards.append(tuple(forward))
        centres.append([means[slot] for slot in range(len(routes))])
        shares.append([share[slot] / total for slot in range(len(routes))])

    # Smoothed *before* they are used, not after. A camera placed from a jittery
    # tangent and then filtered is a filtered jitter; a camera placed from a
    # filtered tangent is steady to begin with, and the trail keeps its length.
    anchors = _smooth(anchors, PATH_PASSES)
    forwards = _slew(_smooth(forwards, PATH_PASSES), MAX_YAW_RATE)

    raw_positions: list[tuple[float, float, float]] = []
    fovs: list[float] = []
    for step in range(len(indices)):
        trail, rise, _look, spread, fov = settings_rows[step]
        # The trail the field's own spread asks for, and the rise scaled with
        # it so pulling back is the same shot from further away rather than a
        # flatter one. See `SPREAD_GAIN`.
        extra = min(
            MAX_SPREAD_TRAIL, spread * max(0.0, smoothed_spread[step] - SPREAD_FREE)
        )
        opened = (trail + extra) / max(trail, 1e-6)
        trail, rise = trail + extra, rise * opened
        here = anchors[step]
        forward = forwards[step]
        raw_positions.append(
            (
                here[0] - forward[0] * trail,
                here[1] - forward[1] * trail + rise,
                here[2] - forward[2] * trail,
            )
        )
        fovs.append(fov)

    positions = _smooth(_follow(raw_positions, MAX_LENS_STEP), PATH_PASSES // 3)
    fovs = _smooth_scalars(fovs, PATH_PASSES // 2)

    # --- the aim, on the course and inside the angle budget -----------------
    def look_point(step: int, along: float) -> tuple[float, float, float]:
        point = [0.0, 0.0, 0.0]
        for slot, route in enumerate(routes):
            weight = shares[step][slot]
            if weight <= 1e-9:
                continue
            centre = centres[step][slot] / SIM_TO_LAYOUT
            target, _tangent = course_at(
                machine, offsets, route, centre + along / SIM_TO_LAYOUT
            )
            for axis in range(3):
                point[axis] += target[axis] * weight
        return tuple(point)

    chosen_look: list[float] = []
    for step in range(len(indices)):
        _trail, _rise, look, _spread, _fov = settings_rows[step]
        lens = positions[step]
        here = anchors[step]
        to_pack = (here[0] - lens[0], here[2] - lens[2])
        pack_length = math.hypot(*to_pack) or 1.0
        picked = 0.0
        for notch in range(LOOK_STEPS, -1, -1):
            along = look * notch / LOOK_STEPS
            point = look_point(step, along)
            to_aim = (point[0] - lens[0], point[2] - lens[2])
            aim_length = math.hypot(*to_aim) or 1.0
            cosine = (to_pack[0] * to_aim[0] + to_pack[1] * to_aim[1]) / (
                pack_length * aim_length
            )
            yaw = math.degrees(math.acos(min(max(cosine, -1.0), 1.0)))
            if yaw <= MAX_LOOK_YAW:
                picked = along
                break
        chosen_look.append(picked)
    chosen_look = _smooth_scalars(chosen_look, PATH_PASSES)

    # The field's own speed, per frame, in layout units a frame: what the aim
    # is allowed to move. See `MAX_LENS_STEP` for why this is not a constant.
    pace: list[float] = []
    for index in indices:
        quickest = 0.0
        for sample in frames[index]["marbles"]:
            if sample.get("s") != "running":
                continue
            quickest = max(
                quickest,
                math.sqrt(sum(float(v) ** 2 for v in sample["v"])) * SIM_TO_LAYOUT,
            )
        pace.append(max(quickest / max(float(fps), 1.0), layout.MARBLE_RADIUS))
    aims = _smooth(
        _follow(
            [look_point(step, chosen_look[step]) for step in range(len(indices))],
            pace,
        ),
        PATH_PASSES // 3,
    )

    # --- the lift -----------------------------------------------------------
    lifts: list[float] = []
    for position, aim in zip(positions, aims):
        need = 0.0
        while need < MAX_EXTRA_RISE:
            lifted = (position[0], position[1] + need, position[2])
            ground = terrain.height(lifted[0], lifted[2], cfg)
            if (
                lifted[1] - ground >= GROUND_MARGIN
                and terrain.clearance(lifted, aim, cfg) >= SIGHT_MARGIN
            ):
                break
            need += RISE_STEP
        lifts.append(need)
    # Forward-looking running maximum, then smoothed: the camera is high before
    # the ground needs it to be, and it gets there on a curve.
    anticipated = [
        max(lifts[step : step + LIFT_LOOKAHEAD + 1]) for step in range(len(lifts))
    ]
    anticipated = _smooth_scalars(anticipated, LIFT_PASSES)
    positions = [
        (position[0], position[1] + lift, position[2])
        for position, lift in zip(positions, anticipated)
    ]

    clearances = [
        terrain.clearance(position, aim, cfg) for position, aim in zip(positions, aims)
    ]

    # --- slice into cuts ----------------------------------------------------
    rows = [
        [
            round(times[index], 6),
            round(positions[step][0], 4),
            round(positions[step][1], 4),
            round(positions[step][2], 4),
            round(aims[step][0], 4),
            round(aims[step][1], 4),
            round(aims[step][2], 4),
            round(fovs[step], 3),
        ]
        for step, index in enumerate(indices)
    ]

    cuts_out: list[dict[str, Any]] = []
    if front is not None:
        cuts_out.extend(front["cuts"])
    for phase, (low, high) in zip(phases, bounds):
        picked = [
            step for step, index in enumerate(indices) if low <= times[index] <= high
        ]
        if not picked:
            continue
        fastest = 0.0
        for step in picked:
            for sample in frames[indices[step]]["marbles"]:
                if sample.get("s") != "running":
                    continue
                fastest = max(
                    fastest,
                    math.sqrt(sum(float(v) ** 2 for v in sample["v"])) * SIM_TO_LAYOUT,
                )
        entries = [rows[step] for step in picked]
        elevations = [
            math.degrees(
                math.atan2(
                    positions[step][1] - aims[step][1],
                    max(
                        math.hypot(
                            positions[step][0] - aims[step][0],
                            positions[step][2] - aims[step][2],
                        ),
                        1e-6,
                    ),
                )
            )
            for step in picked
        ]
        cuts_out.append(
            {
                **phase.to_json(),
                "target": rule,
                "band": TRIM_BAND,
                "node": "",
                "side": 0,
                "fixed_heading": False,
                "heading_run": "",
                "from": round(low, 6),
                "to": round(high, 6),
                "chase": True,
                "extent": round(phase.trail, 3),
                "distance": round(
                    _median(
                        [
                            math.dist(positions[step], aims[step])
                            for step in picked
                        ]
                    ),
                    4,
                ),
                "elevation": round(_median(elevations), 3),
                "fastest_racer": round(fastest, 4),
                "subject": [],
                "lift_deg": round(max(anticipated[step] for step in picked), 3),
                "min_clearance": round(min(clearances[step] for step in picked), 3),
                "frames": entries,
            }
        )
    if back is not None:
        cuts_out.extend(back["cuts"])

    # The edit map. The chase is contiguous, so its windows tile; the bookends
    # bring V21's own omission with them and nothing here adds one.
    windows: list[tuple[str, float, float]] = []
    if front is not None:
        windows.extend(
            (segment["cut"], segment["replay"][0], segment["replay"][1])
            for segment in front["edit"]
        )
    windows.extend((phase.name, low, high) for phase, (low, high) in zip(phases, bounds))
    if back is not None:
        windows.extend(
            (segment["cut"], segment["replay"][0], segment["replay"][1])
            for segment in back["edit"]
        )
    segments: list[dict[str, Any]] = []
    cursor = 0.0
    for name, low, high in windows:
        span = high - low
        segments.append(
            {
                "cut": name,
                "out": [round(cursor, 6), round(cursor + span, 6)],
                "replay": [round(low, 6), round(high, 6)],
            }
        )
        cursor += span

    crossings = [float(t) for t in _crossings(replay).values()]
    return {
        "units": "layout",
        "fps": fps,
        "seed": replay["seed"],
        "edited": True,
        "chase": True,
        "rule": rule,
        "duration": round(cursor, 6),
        "replay_duration": horizon,
        "omitted": round(max(0.0, (windows[-1][2] - windows[0][1]) - cursor), 6),
        "last_crossing": round(max(crossings) if crossings else horizon, 6),
        "edit": segments,
        "cuts": cuts_out,
    }


# --- what a chase can be wrong about ---------------------------------------


# How far the view direction may turn between two frames, in degrees. A chase
# camera's whole claim is that the picture moves smoothly, and the aim being
# `lead` units downstream means the yaw is the *course's* curvature rather than
# the pack's wandering. 1.2 degrees a frame is 72 a second - a full quarter turn
# in a second and a quarter, which is a fast bend rather than a whip.
MAX_TURN_RATE = 1.2

# How far the lens may move between consecutive frames inside a phase, and
# across a phase boundary. `cameras.MAX_CAMERA_STEP` is 1.2 layout units and
# exists to catch a lens that jumps *within* a shot; a chase has no cuts to
# hide a jump behind, so the boundary is held to the same limit as the interior.
MAX_PHASE_STEP = 1.2


def check_chase(track: dict[str, Any], replay: dict[str, Any] | None = None) -> list[str]:
    """`cameras.check_track`'s findings, plus the two a chase can fail alone.

    Almost everything the production checker knows still applies - a lens that
    jumps, an aim that outruns the field, a sight line the mountain crosses -
    so it is run first and its findings are kept verbatim rather than
    reimplemented.

    **One of them is retired for chase cuts, and only one.** `MAX_AIM_DRIFT`
    forbids an aim more than six layout units from the nearest racer, on the
    argument that "an aim point that moves faster than the fastest racer in its
    own cut is what snapping rather than following actually means". That is a
    statement about a *blocking* camera, whose aim is the field. A chase
    camera's aim is deliberately `look` units downstream of the field - that is
    the whole of the brief's "upcoming course is visible before interaction" -
    so on this track the check fires exactly where the design is working.

    Retiring a check that fires is how a prototype flatters itself, so the
    property it was protecting is re-asserted rather than dropped: the aim must
    be no further from the pack than the look-ahead it was solved with, plus a
    marble, and the *field* must be in frame - which `readability.check_readability`
    measures directly and far better than a distance ever did.
    """
    problems = [
        finding
        for finding in cameras.check_track(track, replay)
        if not (
            "is not following the field" in finding
            and any(
                cut.get("chase") and finding.startswith(f"{cut['name']}:")
                for cut in track["cuts"]
            )
        )
    ]
    for cut in track["cuts"]:
        if not cut.get("chase"):
            continue
        budget = float(cut.get("look", 0.0)) + 2.0 * layout.MARBLE_RADIUS
        rows = cut.get("frames") or []
        if replay is None or not rows:
            continue
        times = [float(frame["t"]) for frame in replay["frames"]]
        scale = float(replay.get("units", {}).get("render_scale", SIM_TO_LAYOUT))
        worst, when = 0.0, 0.0
        for row in rows[::6]:
            index = min(range(len(times)), key=lambda k: abs(times[k] - row[0]))
            racers = [
                tuple(float(marble["p"][axis]) * scale for axis in range(3))
                for marble in replay["frames"][index]["marbles"]
            ]
            if not racers:
                continue
            gap = min(math.dist(row[4:7], racer) for racer in racers)
            if gap > worst:
                worst, when = gap, row[0]
        if worst > budget:
            problems.append(
                f"{cut['name']}: the aim is {worst:.1f} layout units from the nearest "
                f"racer at {when:.2f}s, past the {budget:.1f} its look-ahead allows"
            )
    chase = [cut for cut in track["cuts"] if cut.get("chase")]
    for cut in chase:
        rows = cut.get("frames") or []
        worst, when = 0.0, 0.0
        for a, b in zip(rows, rows[1:]):
            one = [a[axis + 4] - a[axis + 1] for axis in range(3)]
            two = [b[axis + 4] - b[axis + 1] for axis in range(3)]
            length = math.sqrt(sum(v * v for v in one)) * math.sqrt(
                sum(v * v for v in two)
            )
            if length < 1e-9:
                continue
            cosine = sum(one[axis] * two[axis] for axis in range(3)) / length
            angle = math.degrees(math.acos(min(max(cosine, -1.0), 1.0)))
            if angle > worst:
                worst, when = angle, b[0]
        if worst > MAX_TURN_RATE:
            problems.append(
                f"{cut['name']}: the view turns {worst:.2f} degrees in one frame at "
                f"{when:.2f}s, which is a whip rather than a chase"
            )
    # A boundary between two chase phases is not a cut and must not look like
    # one. Measured between the last row of one and the first of the next.
    for before, after in zip(track["cuts"], track["cuts"][1:]):
        if not (before.get("chase") and after.get("chase")):
            continue
        rows_before = before.get("frames") or []
        rows_after = after.get("frames") or []
        if not rows_before or not rows_after:
            continue
        moved = math.dist(rows_before[-1][1:4], rows_after[0][1:4])
        if moved > MAX_PHASE_STEP:
            problems.append(
                f"{before['name']} -> {after['name']}: the lens moves {moved:.3f} "
                f"layout units across a phase boundary, which is a cut nobody edited"
            )
    return problems


# --- what a chase is for ----------------------------------------------------


def chase_report(
    track: dict[str, Any],
    replay: dict[str, Any],
    machine,
    bundle=None,
    width: int = WIDTH,
    height: int = HEIGHT,
    stride: int = 6,
) -> list[dict[str, Any]]:
    """Per cut: the two things a chase claims that no existing report measures.

    **Track ahead.** The brief's first principle is that a viewer should see
    where the race is going before the racers get there. That is not racer
    scale and it is not coverage; it is whether the *course* downstream of the
    pack is in the picture. So the racing line is sampled from the pack forward
    for `AHEAD_SPAN` layout units, each sample is projected, and the report is
    the fraction of that span inside the frame and not behind the mountain -
    together with how far downstream the furthest visible sample is, which is
    the viewer's actual horizon in layout units.

    **How fast the picture turns.** A chase camera moves for its whole length,
    so "smooth" has to be a number. The view direction's frame-to-frame angle
    is that number; its median is what the shot feels like and its maximum is
    what a viewer notices.
    """
    from sloped import sightlines
    from sloped.presentation import project

    cfg = terrain.terrain_config(machine.runs)
    if bundle is None:
        bundle = sightlines.Bundle(
            sightlines.course_solids(machine, lambda x, z: terrain.height(x, z, cfg))
        )
    offsets, _totals = route_offsets(machine)
    progress = cameras.progress_track(replay, machine)
    times = progress["times"]
    crossed = _crossings(replay)

    report: list[dict[str, Any]] = []
    for cut in track["cuts"]:
        rows = cut.get("frames") or []
        if not rows:
            continue
        turns: list[float] = []
        for a, b in zip(rows, rows[1:]):
            one = [a[axis + 4] - a[axis + 1] for axis in range(3)]
            two = [b[axis + 4] - b[axis + 1] for axis in range(3)]
            length = math.sqrt(sum(v * v for v in one)) * math.sqrt(
                sum(v * v for v in two)
            )
            if length < 1e-9:
                continue
            cosine = sum(one[axis] * two[axis] for axis in range(3)) / length
            turns.append(math.degrees(math.acos(min(max(cosine, -1.0), 1.0))))
        speeds = [math.dist(a[1:4], b[1:4]) for a, b in zip(rows, rows[1:])]

        seen: list[float] = []
        horizons: list[float] = []
        for row in rows[::stride]:
            when = float(row[0])
            index = min(range(len(times)), key=lambda k: abs(times[k] - when))
            live = {
                marble: progress["progress"][marble][index]
                for marble in progress["marbles"]
                if crossed.get(marble, math.inf) > when
            }
            if not live:
                continue
            route_of = progress["routes"]
            front = max(live, key=lambda marble: live[marble])
            route = route_of.get(front) or "blue"
            if route not in offsets:
                route = next(iter(offsets))
            base = live[front]
            camera, aim, fov = tuple(row[1:4]), tuple(row[4:7]), float(row[7])
            clear = 0
            furthest = 0.0
            for sample in range(1, AHEAD_SAMPLES + 1):
                along = AHEAD_SPAN * sample / AHEAD_SAMPLES
                point, _tangent = course_at(
                    machine, offsets, route, base + along / SIM_TO_LAYOUT
                )
                placed = project(camera, aim, fov, point, width, height)
                if placed is None:
                    continue
                x, y, _depth = placed
                if not (0.0 <= x <= width and 0.0 <= y <= height):
                    continue
                if bundle.first_hit(camera, point, shorten=0.4) is not None:
                    continue
                clear += 1
                furthest = max(furthest, along)
            seen.append(clear / AHEAD_SAMPLES)
            horizons.append(furthest)

        report.append(
            {
                "cut": cut["name"],
                "chase": bool(cut.get("chase")),
                "turn_median": round(_median(turns), 4) if turns else 0.0,
                "turn_max": round(max(turns), 4) if turns else 0.0,
                "speed_median": round(_median(speeds), 4) if speeds else 0.0,
                "speed_max": round(max(speeds), 4) if speeds else 0.0,
                "ahead_share": round(_median(seen), 3) if seen else 0.0,
                "ahead_units": round(_median(horizons), 1) if horizons else 0.0,
            }
        )
    return report

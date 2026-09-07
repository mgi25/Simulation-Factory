"""The four joins the authored course does not contain, solved from its poses.

`docs/sloped_race_v1_junction_finding.md` is the argument for why these exist.
The short version: five of the seven runs join cleanly and two do not. The field
arrives at the split travelling west and orange's mouth faces east, 152.8
degrees away; blue and orange arrive at the merge head-on, 147 degrees apart,
with the sprint leaving between them. Both stations were composed as symmetric
Y-junctions and both are fed across the axis of their own symmetry.

Nothing here re-authors a run. Each join is a short piece of the *same*
channel - same cradle, same lip, same guard, same bank law - between two poses
that already exist, and each one's shape is solved from those poses rather than
drawn. The four:

    blue_lead      leg3's exit        ->  blue's second control      7.90 units
    orange_lead    leg3 at sample 82  ->  orange's third control    12.70 units
    the merge      an apron, not a channel: `sloped.stations.MergeCatch`

## Why the fork moves up-course, and why that is the small change

At the authored split the arrival heading is -84.4 degrees and any line into
orange's lobe has to end up heading east, about +65 to +79. A single arc
between two poses has its chord along the *average* of the two headings; here
the average is -9.5 degrees and the chord to orange's lobe points +65.4, a
75-degree mismatch, so no arc joins them and the arc-line family solves to a
radius of 0.024 layout units - a knife edge. The turn can only be made by a
visible loop.

Seventy per cent of the way along leg3, at sample 82, the field is heading
-1.05 degrees: straight downhill, because that is where the violet sweep's hook
crosses south. From there the two lobes open at -22 and +24 degrees of the
stem and the chord-to-bisector mismatch into orange's third control is **5
degrees**. So the fork is placed where the course already turns south, blue is
leg3's own hook tail unchanged, and orange is reached by one gentle arc.

That is worth stating as a race property and not only as a geometric one: the
fork is *lane-based*. leg3's tail curves left and orange's lead curves right
out of a common stem, so which route a marble takes is decided by which side of
a 3.3-diameter channel it is running on when it reaches the fork. Nothing
chooses for it.

The cost is that orange's first two authored controls are dropped - the
7-unit segment from the old promontory mouth east to (13.0, 9.2, 21.0) - and
that the split's portals and wedge belong 7.6 units up-course. The eastern lobe
itself, which is what the split still frame shows, is untouched.

## Why both branch mouths are dropped, and where the leads join instead

Blue's authored mouth cannot be joined either, for the same reason in
miniature. leg3's exit heading is -84.4, the mouth is 1.115 units away in the
direction -46.8, and the mouth itself faces -64.1: three directions, with the
chord 37.6 degrees off the two poses' bisector. Prepending leg3's exit as a
control and keeping the mouth does not fix it - the first Catmull-Rom span is
then 1.08 units against a 6.6-unit second span, the tangent magnitudes are
mismatched four to one, and the curve leaves the exit heading -125 before
swinging back. Measured: a 40-degree kink at the seam and a 0.41-unit radius.

So each branch is entered one control in, by a lead solved from the two poses:

    blue_lead    leg3's exit    -> blue's   (-0.80, 9.30, 21.40) at -71.6
    orange_lead  leg3 at 82     -> orange's (18.40, 8.20, 23.60) at +40.6

Blue drops one authored control and orange two. From those points on, both
lobes are the curve that was photographed - which is the whole eastern loop and
the whole western one, all of the silhouette either of them contributes.

## The tension is 1.00, and that is a measurement

`hermite`'s tension scales both end tangents by the chord. Scanned against the
worst turn radius the resulting path actually contains:

    tension   blue_lead r    orange_lead r
    0.30      0.68           1.07
    0.45      1.14           1.93
    0.62      1.85           3.44
    0.80      2.84           5.91
    1.00      4.26           10.38
    1.25      5.27           10.33

The requirement is 2.43 layout units - what a marble at the measured 43 wu/s
holds on a 34-degree bank - and 0.62, which is the value that makes a
90-degree join closest to a circular arc, does not meet it on either lead.
Longer tangents hold the departure heading further into the curve and put the
turning in the middle where there is room for it. 1.00 clears the requirement
by 1.8x on the tighter of the two and the length cost is 0.5%: 7.85 units at
0.62 against 7.89 at 1.00.

## Why the merge is an apron and not a channel

A 141-degree turn at the measured 41 wu/s needs 4.15 layout units of chord
along the merge's own bisector, and that bisector points away from the
sprint's line - so any curve that makes the turn ends up parallel to the sprint
and 7.7 units from it. Every family was tried and each one's number is in the
finding note: a single arc, arc-then-line, line-then-arc (which solves to a
radius of 0.024, a knife edge), a two-inlet cyclone (whose common tangent
circle needs a radius of 78), and a mirror pair of hooks into a collector on
the bisector (which come out at a 0.06-unit radius, a cusp). None closes.

So the merge is not a channel. `sloped.stations.MergeCatch` is a roofed funnel
apron around the sprint's first two units: blue arrives on its centreline
pointing down it and runs across, orange arrives ahead of it pointing back up
it and is returned by the apron's own fall after one wall. The asymmetry is
real, and it is measured against orange's correspondingly shorter route rather
than argued away.

## Radii, which are measured and not chosen

The banked lateral limit for this channel is

    a_lat / g = (tan(bank) + mu) / (1 - mu * tan(bank))

with mu = 0.50, the core's marble-on-track figure. At the branches' 32-degree
bank that is 1.635 g, and the arrival speeds are measured rather than assumed:
a marble released at the top of the launch reaches leg3's exit at 43 wu/s, and
both branches self-limit to 36 to 41 wu/s at the merge whatever they enter at -
30 in gives 38 to 39 out, 60 in gives 31 to 41 out, so the lobes are at their
terminal speed and the merge's design speed is 41.

    minimum radius = v^2 / (1.635 * 245.25)

which is 4.2 sim units at 41 wu/s and 2.4 layout units. Every arc below is
checked against it by `sloped.course`, and the check is on the *built* path's
own curvature rather than on the nominal radius, because a Catmull-Rom through
control points is not the arc that was solved for.
"""

from __future__ import annotations

import math
from typing import Sequence

from marble3d.units import GRAVITY

from sloped import layout
from sloped.pathing import build_path, flat_tangents
from sloped.scale import LAYOUT_TO_SIM

__all__ = [
    "FORK_SAMPLE",
    "FORK_WINDOW_BLUE",
    "FORK_GUARD_WINDOW",
    "LEAD_MOUTH_FLARE",
    "FORK_WINDOW_ORANGE",
    "blue_controls",
    "LEAD_TENSION",
    "MU_TRACK",
    "MERGE_DESIGN_SPEED",
    "min_radius_layout",
    "hermite",
    "pose_of",
    "grade_of",
    "path_span",
    "JOIN_SPECS",
    "join_paths",
    "orange_controls",
]

# `marble3d.config.MarbleConfig.surface_friction`. Imported as a number rather
# than from the config so that this module stays readable as geometry; the test
# asserts the two agree.
MU_TRACK = 0.50

# Measured, not assumed. See the module docstring.
MERGE_DESIGN_SPEED = 41.0
SPLIT_DESIGN_SPEED = 43.0

# Where leg3's hook crosses south. `sloped.course` asserts this is still the
# sample whose heading is nearest zero, so a change to the path law cannot move
# the fork silently.
FORK_SAMPLE = 82

# The fork's two wall windows, in samples past the fork, and the arithmetic
# that fixes them. Both were measured wrong twice before they were measured
# right, and the measurements are worth keeping.
#
# The two centrelines separate at 56 degrees, so their distance apart `s` grows
# 0, 0.13, 0.89, 1.94, 3.23 layout units at 0, 4, 8, 12 and 16 samples. Two
# 1.88-wide channels overlap while `s < 1.88` and have a gap between them after.
#
# **leg3's east guard.** It is blue's wall on the *outside* of blue's own turn -
# leg3's tail turns 38 degrees right in 2.3 units and throws its marbles east -
# so opening it at the nose loses them: 11 of 24 marbles left the course at
# leg3 samples 80 to 99 with it open there, and 1 of 24 with it shut. But it
# also stands between an orange-bound marble and orange's floor once orange's
# west edge has moved east of it, which happens at about `s = 1.88`, sample
# +11. And by sample +8 the ridge has grown to 0.94 of the channel's own 1.40
# of containment with its west flank inside leg3's channel, so from there the
# ridge *is* blue's east wall and the guard is redundant. So the guard is full
# at the nose, open from +7 to +12, and full again by +14. Both edges are set
# by which wall is the *outer* one at that sample, which is the only thing that
# decides whether opening it is safe:
#
#     step | leg3's east edge | orange's east edge | outer wall
#        0 |             1.61 |               1.44 | leg3's
#        6 |             1.63 |               2.51 | orange's
#       12 |             1.65 |               4.57 | orange's
#       14 |             1.65 |               5.81 | each its own
#
# At the nose leg3's guard is outside orange's, so opening it leaves a strip of
# floor with nothing on its edge and the field goes over it - 11 of 24 lost
# there, against 1 with it shut. From six samples on, orange's guard is the
# outer wall and leg3's is an obstruction between an orange-bound marble and
# orange's floor. By +14 the two channels have parted and each needs its own
# again.
#
# **orange's west wall.** Open from its first sample, because leg3's floor is
# west of it there and a wall in the middle of leg3's floor is a step a marble
# climbs; full by +14, where the two channels have parted.
FORK_GUARD_WINDOW = (-1, 0, 12, 14)

# Orange's mouth is at hero width, and the 1.28 flare it used to carry is gone.
#
# The flare existed to put orange's east guard outside leg3's from the nose,
# because with the mouth on leg3's *centreline* orange's own guard only passed
# leg3's about six samples in, leaving a strip of leg3's floor with nothing on
# its edge. `ORANGE_MOUTH_ACROSS` solves that better: the mouth is now a channel
# half-width east, so orange's east edge is at 3.30 against leg3's 1.61 from the
# first sample and orange's guard is the outer wall throughout the window.
#
# Keeping the flare on top of the moved mouth was actively harmful, and this is
# the measurement. A 1.28 flare makes orange's half 2.111 against leg3's 1.649,
# so orange's *west* lip sits at leg3-frame across -0.505 - past leg3's own
# centreline - and about 0.97 simulation units above leg3's floor, because the
# mouth is up a 26-degree bank. That is a lip a marble diameter up, overhanging
# the middle of leg3's channel, and a marble arriving at 43 wu/s hits it: 53 of
# 158 losses over 28 seeds were booked to leg3[80..99] and 26 more to
# orange_lead[0..19]. At hero width orange's west edge lands on leg3's
# centreline instead of past it, and nothing overhangs.
LEAD_MOUTH_FLARE = 1.0
FORK_WINDOW_ORANGE = 14
FORK_WINDOW_BLUE = 20          # how far the ridge runs

# Where orange's mouth sits across leg3's channel, in profile units, and why it
# is not on the centreline.
#
# The fork is 82 samples along leg3, in the middle of a hairpin that turns
# **left** and is therefore banked with its **east** side raised - 26 degrees of
# it, which `min_radius_layout` says is 1.7 degrees more than a marble at
# 43 wu/s needs to hold the 3.5-unit radius there, so it is a requirement.
# Orange's lobe is to the east. So orange is on the *outside* of a banked turn,
# and a branch mouth on leg3's centreline is a channel underneath leg3's floor
# that a marble would have to fall into: measured, with the mouth on the
# centreline no marble ever reached orange's floor at any entry speed or
# lateral position, and the ones thrown east by the hook went over leg3's
# opened lip into the void between the two channels at leg3[92..95].
#
# So the mouth is at the *top* of leg3's east bank, where the outward throw of
# the hook actually delivers a marble, and the fork sorts the field the way the
# geometry already wants to: a marble carrying enough speed rides up the bank
# and onto orange's floor, one that does not stays low and follows leg3 round
# to blue. Nothing chooses for it - the choice is momentum against a bank,
# which is section 8's requirement exactly.
#
# In profile units, so `CHANNEL_HALF` is the cradle's edge and 1.0 is the top of
# the rolled lip. `sloped.splitlab` scans it; see `docs/sloped_race_v11.md`.
ORANGE_MOUTH_ACROSS = 0.94

# How much of orange's lead holds leg3's own gradient before it starts to
# fall - the correction in `_held_heights`, whose docstring has the numbers.
#
# It is set from the geometry rather than chosen. The two channels stop
# overlapping when their centrelines are `HERO_CLEAR_WIDTH` apart, which the
# built lead reaches about 13 of its 44 samples in, and 13/44 is 0.30. A tenth
# is added so the changeover is past the parting rather than on it.
# `sloped.course.check` asserts the built geometry still parts inside the hold,
# so a change to the path law cannot leave this behind.
ORANGE_LEAD_HOLD = 0.40


def min_radius_layout(speed: float, bank_deg: float, mu: float = MU_TRACK) -> float:
    """The tightest arc a marble at `speed` holds on a channel banked so."""
    tangent = math.tan(math.radians(bank_deg))
    ratio = (tangent + mu) / max(1.0 - mu * tangent, 1e-6)
    return speed * speed / (ratio * GRAVITY) / LAYOUT_TO_SIM


def _norm2(x: float, z: float) -> tuple[float, float]:
    length = math.hypot(x, z)
    return (x / length, z / length) if length > 1e-12 else (0.0, 1.0)


def _held_heights(
    plan: Sequence[tuple[float, float]],
    y0: float,
    y1: float,
    start_grade: float,
    end_grade: float,
    hold: float,
) -> list[float]:
    """Heights along a plan curve that hold `start_grade` before falling away.

    A grade is height per unit of *horizontal* travel, so this works in the
    plan curve's own arc length rather than in the Hermite's parameter, where
    equal steps are not equal distances.

    Over the first `hold` of the horizontal length the channel falls at exactly
    `start_grade` - the gradient of the run it branches from - and the whole
    remaining drop is absorbed by a cubic Hermite over what is left, joined C1
    at the changeover and arriving at `end_grade`.

    ## Why a fork needs this, and why a plain cubic will not do

    A fork has to separate in **plan** before it separates in **elevation**,
    and V1's two branches did the opposite. Measured in leg3's own frame at the
    samples past the fork:

        samples past  lateral apart  vertical apart
                   4          0.349         -0.246
                   8          0.707         -0.551
                  12          1.109         -1.078

    The two channels need 1.88 of lateral separation before they stop
    overlapping, and by the time they have half of it orange's cradle is more
    than half a marble diameter *below* leg3's floor. That is not a fork; it is
    a trench under leg3's east half with no continuous surface into it. A
    marble steered east ran off leg3's opened guard, dropped in and stopped
    against orange's west wall from the inside - all seven controlled entries
    in `sloped.splitlab` died that way, at leg3[90..95].

    The cause is the gradients rather than the curve family: leg3's tail eases
    from -0.32 at the fork to -0.07 at its exit while orange's lead needs an
    average of -0.33, and a plain cubic between matched end gradients has
    steepened to -0.39 by a quarter of the way along. Holding leg3's own
    gradient over the overlap costs almost nothing - the drop moves back into a
    stretch already at -0.38 - and it is the only thing that changes: both
    endpoints, the plan curve, the macro route and the lobe are untouched.
    """
    span = [0.0]
    for index in range(1, len(plan)):
        span.append(
            span[-1]
            + math.hypot(
                plan[index][0] - plan[index - 1][0], plan[index][1] - plan[index - 1][1]
            )
        )
    total = span[-1]
    if total <= 1e-9:
        return [y0] * len(plan)
    held = max(0.0, min(0.95, hold)) * total
    y_held = y0 + start_grade * held
    tail = total - held
    out: list[float] = []
    for distance in span:
        if distance <= held or tail <= 1e-9:
            out.append(y0 + start_grade * distance)
            continue
        u = (distance - held) / tail
        u2, u3 = u * u, u * u * u
        out.append(
            (2 * u3 - 3 * u2 + 1) * y_held
            + (u3 - 2 * u2 + u) * (start_grade * tail)
            + (-2 * u3 + 3 * u2) * y1
            + (u3 - u2) * (end_grade * tail)
        )
    return out


def hermite(
    start: Sequence[float],
    start_heading_deg: float,
    end: Sequence[float],
    end_heading_deg: float,
    samples: int = 24,
    tension: float = 0.62,
    start_grade: float | None = None,
    end_grade: float | None = None,
    hold_grade: float = 0.0,
) -> list[tuple[float, float, float]]:
    """A cubic Hermite between two poses, in the horizontal plane, with height
    carried as a cubic of its own.

    Two poses and one curve family, so the shape is determined by the poses and
    a single tension rather than by a hand-placed control polygon. `tension`
    scales both tangent magnitudes by the chord length: 0.62 is the value that
    makes a 90-degree join come out closest to a circular arc, which is what
    the radius budget is quoted against.

    Height is a cubic Hermite of its own, with the two end *gradients* passed
    in as `start_grade` and `end_grade` in height per unit of horizontal
    travel. That is not decoration. A join whose height is eased with a
    smoothstep leaves both ends level in gradient, and at the fork leg3's tail
    dives at 0.30 while a levelled orange lead sits still: measured, the two
    channels came out 0.25 layout units apart in height while still
    overlapping laterally, which put a marble-deep pocket between orange's
    cradle and leg3's east wall. Six of eight marbles ended up in it.

    Matching the end gradients was necessary and not sufficient: a cubic
    between them still steepens in the middle, and at a fork the middle is
    where the two channels still share floor. `hold_grade` is the fraction of
    the join's horizontal length over which `start_grade` is held exactly
    before the drop is made up; `_held_heights` has the measurement.
    """
    sx, sy, sz = (float(v) for v in start)
    ex, ey, ez = (float(v) for v in end)
    chord = math.hypot(ex - sx, ez - sz)
    scale = tension * chord
    s_dir = _norm2(math.sin(math.radians(start_heading_deg)), math.cos(math.radians(start_heading_deg)))
    e_dir = _norm2(math.sin(math.radians(end_heading_deg)), math.cos(math.radians(end_heading_deg)))
    m0 = (s_dir[0] * scale, s_dir[1] * scale)
    m1 = (e_dir[0] * scale, e_dir[1] * scale)

    # Height tangents in the same parameter as the plan curve, so a gradient of
    # dy/ds becomes dy/dt by multiplying through the horizontal speed - which
    # for a Hermite is the tangent magnitude, `scale`.
    g0 = 0.0 if start_grade is None else start_grade * scale
    g1 = 0.0 if end_grade is None else end_grade * scale
    eased = start_grade is None and end_grade is None

    plan: list[tuple[float, float]] = []
    heights: list[float] = []
    for step in range(samples):
        t = step / (samples - 1)
        t2, t3 = t * t, t * t * t
        h00 = 2 * t3 - 3 * t2 + 1
        h10 = t3 - 2 * t2 + t
        h01 = -2 * t3 + 3 * t2
        h11 = t3 - t2
        plan.append(
            (
                h00 * sx + h10 * m0[0] + h01 * ex + h11 * m1[0],
                h00 * sz + h10 * m0[1] + h01 * ez + h11 * m1[1],
            )
        )
        if eased:
            heights.append(sy + (ey - sy) * (t * t * (3.0 - 2.0 * t)))
        else:
            heights.append(h00 * sy + h10 * g0 + h01 * ey + h11 * g1)

    if hold_grade > 0.0 and not eased:
        heights = _held_heights(
            plan,
            sy,
            ey,
            0.0 if start_grade is None else start_grade,
            0.0 if end_grade is None else end_grade,
            hold_grade,
        )
    return [(plan[i][0], heights[i], plan[i][1]) for i in range(samples)]


def path_span(path) -> float:
    """A polyline's length, for choosing how many samples to carry it at."""
    return sum(math.dist(path[i + 1], path[i]) for i in range(len(path) - 1))


def grade_of(path, index: int, span: int = 4) -> float:
    """A run's gradient at one sample, as height lost per unit travelled.

    Measured over `span` samples rather than one, because a single sample of a
    118-point path is 0.29 layout units and the height difference across it is
    within the rounding of the control points it came from.
    """
    a = min(max(index, 0), len(path) - 1)
    b = min(max(index + span, 0), len(path) - 1)
    if a == b:
        a, b = max(0, b - span), b
    run = math.hypot(path[b][0] - path[a][0], path[b][2] - path[a][2])
    if run < 1e-9:
        return 0.0
    return (path[b][1] - path[a][1]) / run


def pose_of(path, tangents, index: int) -> tuple[tuple[float, float, float], float]:
    """One end of a run, as (point, heading in degrees)."""
    at = min(max(index, 0), len(path) - 1)
    forward = tangents[at]
    return (tuple(path[at]), math.degrees(math.atan2(forward[0], forward[2])))


def orange_controls() -> tuple[tuple[float, float, float], ...]:
    """Orange's lobe, entered at its third authored control.

    The two dropped controls are (6.90, 10.40, 18.55) - the old promontory
    mouth - and (13.00, 9.20, 21.00). `orange_lead` arrives at the third,
    (18.40, 8.20, 23.60): stopping at the second gives a lead whose worst
    radius is 1.45 at any tension, because the 71 degrees of turn have only
    9.0 units to happen in, and 1.45 is well under the 2.43 the arrival speed
    needs.
    """
    return tuple(layout.run("orange")["controls"][2:])


# Measured; see the module docstring's tension table.
LEAD_TENSION = 1.00


def blue_controls() -> tuple[tuple[float, float, float], ...]:
    """Blue's lobe, entered at its second authored control.

    The dropped control is (5.20, 10.40, 18.55), the old promontory mouth.
    `blue_lead` arrives at (-0.80, 9.30, 21.40) instead, which is 7.90 units
    from leg3's exit rather than 1.115 - room enough for the 12.8 degrees of
    turn the join needs at a radius of 4.26 against the 2.43 required.
    """
    return tuple(layout.run("blue")["controls"][1:])


def _built(name: str):
    spec = layout.run(name)
    return build_path(spec["controls"], float(spec["bank_gain"]), float(spec["bank_max"]))


def _run_pose(name: str, which: str):
    path, _banks, tangents, _widths = _built(name)
    index = 0 if which == "entry" else len(path) - 1
    point, heading = pose_of(path, tangents, index)
    return point, heading, grade_of(path, index if which == "entry" else index - 4)


def _leg3_fork_pose():
    """leg3's pose at the fork, with the gradient of its tail over the overlap.

    The gradient is the *chord* over `FORK_WINDOW_ORANGE` samples rather than
    the local one over four, because it is what orange's lead has to hold to
    stay level with leg3 while the two still share floor, and leg3's tail is
    not a straight line there: it falls at -0.32 at the fork and eases to -0.25
    by fourteen samples on, with a chord of -0.282. Holding the local -0.321
    instead puts orange's floor 0.10 simulation units *under* leg3's in the
    middle of the window; holding the chord puts it 0.10 *over*, which is the
    safe side - a marble crossing east climbs a tenth of a diameter rather than
    dropping into a gap.
    """
    path, _banks, tangents, _widths = _built("leg3")
    point, heading = pose_of(path, tangents, FORK_SAMPLE)
    return point, heading, grade_of(path, FORK_SAMPLE, span=FORK_WINDOW_ORANGE)


def _leg3_lip(leg3, sample: int, across: float = ORANGE_MOUTH_ACROSS):
    """A point on leg3's east lip, in **layout** units.

    `surface_point` applies the profile scale and the per-sample width factor
    in the same order `ring_points` does, so this is a point the collider has a
    vertex at rather than one near it.
    """
    point = leg3.surface_point(sample, across)
    return tuple(value / LAYOUT_TO_SIM for value in point)


def fork_mouth(across: float = ORANGE_MOUTH_ACROSS):
    """Orange's mouth, and the gradient of the lip it has to stay level with.

    Two corrections over V1.2, and the second is the one that was missing.

    **The mouth is lifted by the channel's own floor offset.** V1.2 put
    orange's *centreline* on leg3's east lip, and a channel's running floor
    sits `FLOOR_Y` - 0.26 layout units, 0.456 simulation - below its
    centreline. So orange's floor started 0.456 under the lip a marble crosses
    from, which is a drop at the seam rather than a join. Measured at the fork
    sample itself: leg3's lip at world y 22.213, the nearest point of orange's
    floor at 21.751.

    **The gradient held over the overlap is the lip's, not the centreline's.**
    `_held_heights` keeps the lead level with whatever it is given for the
    first `ORANGE_LEAD_HOLD` of its length, and what it has to stay level with
    is the surface the marble is actually running on. leg3's east lip sits 0.59
    to 0.62 above its own centreline through the window - the bank times the
    half width - and that offset is not constant, because both the bank and the
    width change through the tail.

    Together these close a gap that ran 0.46 at the fork to 0.76 eight samples
    on, and that gap is why every marble crossing east ended up on orange's
    west lip three quarters of a diameter down instead of on its floor.
    """
    from sloped.track import TrackRun

    leg3 = TrackRun("leg3")
    lip = _leg3_lip(leg3, FORK_SAMPLE, across)
    # Lift by the floor offset, along the channel's own up axis, so it is the
    # lead's *floor* that lands on the lip rather than its centreline.
    _lateral, up, _forward = leg3.frames[FORK_SAMPLE]
    lift = -layout.FLOOR_Y * float(layout.run("leg3")["scale"])
    mouth = tuple(lip[axis] + up[axis] * lift for axis in range(3))

    # The lip's own chord grade across the window the two channels share.
    far = _leg3_lip(leg3, min(FORK_SAMPLE + FORK_WINDOW_ORANGE, len(leg3.path) - 1), across)
    run = math.hypot(far[0] - lip[0], far[2] - lip[2])
    grade = (far[1] - lip[1]) / run if run > 1e-9 else 0.0
    return mouth, leg3.heading_deg(FORK_SAMPLE), grade


def fork_bank_deg() -> float:
    """leg3's own roll at the fork, in degrees.

    Read off the built run rather than typed, so the lead follows leg3 if the
    path law or the bank law ever moves. This is 26.0 degrees on the shipped
    geometry - `bank_max` for leg3, because the fork sits in the middle of its
    hairpin - and `min_radius_layout` says a marble at 43 wu/s needs 24.3 of it
    to hold the 3.5-unit radius there, so it is a requirement and not a choice.
    """
    _path, banks, _tangents, _widths = _built("leg3")
    return math.degrees(banks[FORK_SAMPLE])


# --- the specs ------------------------------------------------------------
#
# `bank_gain` and `bank_max` per join are the neighbouring runs' own figures, so
# a join rolls into a turn the way the channel either side of it does. The two
# merge hooks share one pair of numbers because they have to be mirror images
# of each other and nothing else.

JOIN_SPECS: dict[str, dict] = {
    "blue_lead": {
        "name": "blue_lead",
        "role": "join",
        "scale": layout.HERO_SCALE,
        "bank_gain": 3.4,
        "bank_max": 30.0,
        "exit_flare": 0.0,
        "design_speed": SPLIT_DESIGN_SPEED,
    },
    "orange_lead": {
        "name": "orange_lead",
        "role": "join",
        "scale": layout.HERO_SCALE,
        # **The lead carries no bank of its own, and that is measured.** Its
        # worst turn radius is 10.5 layout units and `min_radius_layout(43, 0)`
        # is 8.6, so friction alone holds a marble on it at the arrival speed
        # with the channel dead level. So its whole roll budget can go on the
        # one thing it does need: matching leg3 at the seam.
        #
        # With a curvature-driven bank it could not. leg3's hairpin turns left
        # and the lead turns right, so their banks have opposite sign, and a
        # lead pinned to leg3's +26 at the nose has to reverse to its own -17.
        # Over six samples that is a 43-degree twist in 1.7 layout units; over
        # eighteen the reversal simply moves into the middle of the overlap,
        # where the roll mismatch against leg3 measured -1.27 simulation units
        # of step at leg3[89]. Either way it is the sign change that does the
        # damage, and with `bank_gain` at zero there is no sign change: the roll
        # decays monotonically from leg3's 26 degrees to level over the lead's
        # whole length, 2.3 degrees per layout unit.
        "bank_gain": 0.0,
        "bank_max": 30.0,
        "entry_flare": 0.0,
        "design_speed": SPLIT_DESIGN_SPEED,
        # Measured off leg3 rather than typed. The two directions at the seam
        # agree by construction, because the lead's start heading is leg3's own.
        "entry_bank_deg": fork_bank_deg(),
        "bank_ease_ends": 40,
    },
}


def join_paths() -> dict[str, list[tuple[float, float, float]]]:
    """Every join's path, solved from the runs' own end poses.

    Solved rather than stored, so that a change to the path law moves the joins
    with the runs instead of leaving them behind at coordinates that used to be
    right. `sloped.course` then checks each seam and each radius.
    """
    # Orange leaves from the top of leg3's east bank, not from its centreline;
    # `ORANGE_MOUTH_ACROSS` has the measurement.
    fork_point, fork_heading, fork_grade = fork_mouth()
    leg3_exit, leg3_heading, leg3_grade = _run_pose("leg3", "exit")
    blue_lobe = blue_controls()
    orange_lobe = orange_controls()
    def lobe_entry(controls):
        """The lobe's own first pose, taken from its *built* path.

        Not from the control polygon: the polygon's first segment and the
        spline's first tangent differ by three degrees on orange and eleven on
        blue, and a lead aimed at the polygon lands with that much kink.
        """
        path, _banks, tangents, _widths = build_path(
            controls, float(layout.run("orange")["bank_gain"]), 30.0
        )
        return (
            tuple(path[0]),
            math.degrees(math.atan2(tangents[0][0], tangents[0][2])),
            grade_of(path, 0),
        )

    blue_entry, blue_entry_heading, blue_grade = lobe_entry(blue_lobe)
    orange_entry, orange_entry_heading, orange_grade = lobe_entry(orange_lobe)

    # Both leads. The end heading is the lobe's own first tangent rather than a
    # chosen one, so each seam closes in direction as well as in position.
    return {
        "blue_lead": hermite(
            leg3_exit,
            leg3_heading,
            blue_entry,
            blue_entry_heading,
            samples=48,
            tension=LEAD_TENSION,
            start_grade=leg3_grade,
            end_grade=blue_grade,
        ),
        # Orange's lead holds leg3's gradient over the stretch where the two
        # channels still share floor, then makes up its drop; see
        # `ORANGE_LEAD_HOLD` and `_held_heights`.
        "orange_lead": hermite(
            fork_point,
            fork_heading,
            orange_entry,
            orange_entry_heading,
            samples=48,
            tension=LEAD_TENSION,
            start_grade=fork_grade,
            end_grade=orange_grade,
            hold_grade=ORANGE_LEAD_HOLD,
        ),
    }

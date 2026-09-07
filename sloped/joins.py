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
# at the nose, open from +8 to +18, and full again by +22 - by which point the
# ridge's west foot has swept out to leg3's own edge and handed the job back.
#
# **orange's west wall.** Open from its first sample, because leg3's floor is
# west of it there and a wall in the middle of leg3's floor is a step a marble
# climbs; full by +14, where the two channels have parted.
FORK_GUARD_WINDOW = (8, 12, 18, 22)
FORK_WINDOW_ORANGE = 14
FORK_WINDOW_BLUE = 20          # how far the ridge runs


def min_radius_layout(speed: float, bank_deg: float, mu: float = MU_TRACK) -> float:
    """The tightest arc a marble at `speed` holds on a channel banked so."""
    tangent = math.tan(math.radians(bank_deg))
    ratio = (tangent + mu) / max(1.0 - mu * tangent, 1e-6)
    return speed * speed / (ratio * GRAVITY) / LAYOUT_TO_SIM


def _norm2(x: float, z: float) -> tuple[float, float]:
    length = math.hypot(x, z)
    return (x / length, z / length) if length > 1e-12 else (0.0, 1.0)


def hermite(
    start: Sequence[float],
    start_heading_deg: float,
    end: Sequence[float],
    end_heading_deg: float,
    samples: int = 24,
    tension: float = 0.62,
    start_grade: float | None = None,
    end_grade: float | None = None,
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

    out: list[tuple[float, float, float]] = []
    for step in range(samples):
        t = step / (samples - 1)
        t2, t3 = t * t, t * t * t
        h00 = 2 * t3 - 3 * t2 + 1
        h10 = t3 - 2 * t2 + t
        h01 = -2 * t3 + 3 * t2
        h11 = t3 - t2
        x = h00 * sx + h10 * m0[0] + h01 * ex + h11 * m1[0]
        z = h00 * sz + h10 * m0[1] + h01 * ez + h11 * m1[1]
        if eased:
            y = sy + (ey - sy) * (t * t * (3.0 - 2.0 * t))
        else:
            y = h00 * sy + h10 * g0 + h01 * ey + h11 * g1
        out.append((x, y, z))
    return out


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
    path, _banks, tangents, _widths = _built("leg3")
    point, heading = pose_of(path, tangents, FORK_SAMPLE)
    return point, heading, grade_of(path, FORK_SAMPLE)


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
        "bank_gain": 3.4,
        "bank_max": 30.0,
        "entry_flare": 0.0,
        "design_speed": SPLIT_DESIGN_SPEED,
    },
}


def join_paths() -> dict[str, list[tuple[float, float, float]]]:
    """Every join's path, solved from the runs' own end poses.

    Solved rather than stored, so that a change to the path law moves the joins
    with the runs instead of leaving them behind at coordinates that used to be
    right. `sloped.course` then checks each seam and each radius.
    """
    fork_point, fork_heading, fork_grade = _leg3_fork_pose()
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
        "orange_lead": hermite(
            fork_point,
            fork_heading,
            orange_entry,
            orange_entry_heading,
            samples=48,
            tension=LEAD_TENSION,
            start_grade=fork_grade,
            end_grade=orange_grade,
        ),
    }

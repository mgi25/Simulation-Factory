"""The whole course as one `marble3d.Machine`, with its joins checked.

## Placement is asserted, not derived

`marble3d.machine` exists to make a module's place in the world derived - one
anchor and socket algebra for everything else - and this is the one machine in
the repository that does not use it. The reason is that the position *is* the
contract: `docs/validation/sloped_course/physics_layout.json` says where the
built channel is and the render draws it there, so a run that solved for its
own placement could be perfectly self-consistent and in the wrong place.

The property socket algebra buys - that the joins actually close - is bought
here by checking instead. `check()` measures every seam's position gap,
heading change and bank step, every join's worst turn radius against what the
measured arrival speed can hold, and the fork sample against the heading it is
supposed to sit on. A gap is a finding, not a shrug.

## Flow order, and which routes are on offer

    START -> launch -> leg1(mixer) -> leg2(spinners) -> leg3
          -> blue_lead -> blue -> merge catch -> final -> FINISH

`routes="both"` adds the fork at leg3 sample 82, `orange_lead` and orange's
lobe. It is not the default, and that is a measurement rather than a
preference.

## Why the second route is off by default

The two branch lobes diverge at 56 degrees from a common point, so a fork
between them has to split a 3.3-diameter channel into two inside 3.4 layout
units while eight marbles arrive at 43 wu/s. Six configurations were built and
measured, over 32 seeds of eight marbles each:

    divider                       guard window   finished   lost at the fork
    straight blade on the tangent  +8 to +22       -         13 of 24
    blade on the bisector          +8 to +22       -          4 dead, rest queued
    ridge, foot <= half width      +8 to +22      68%        40 of 256
    ridge, foot <= 0.55            +7 to +16      57%        73 of 256
    ridge in the cradle gap        +5 to +14      41%        14 of 32
    ridge in the gap, mouth flared  0 to +14       0%        21 of 32
    no fork at all                 shut           85%         0 of 48

Each failure had a different cause and each is recorded where it was fixed -
in `sloped.stations.ForkRidge` and `sloped.joins.FORK_GUARD_WINDOW` - and none
of them was the last one. The pattern across all six is the same trade: a
divider big enough to sort the field is big enough to queue it, a guard open
enough to let a marble cross is open enough to lose one, and a guard shut
enough to hold the field is shut enough that orange is unreachable. With the
route attribution corrected - the first version fixed a marble's route on its
first contact with a branch collider, and the two channels *overlap* at the
fork, so it credited orange with marbles that ran down leg3's tail - **no
configuration ever put a marble on the orange lobe and got it to the finish.**

The through route does work, and it is the majority of the course: 196 layout
units, five clean seams, 85% of marbles finishing, four to six lead changes a
race and final margins from 0.03 to 0.67 seconds.

So the course ships with one route and the second is a documented, measured
blocker rather than a broken feature.
`docs/sloped_race_v1_junction_finding.md` has the geometry and
`docs/sloped_race_v1.md` has these numbers; the fork's own geometry stays in
the tree, behind `routes="both"`, because the next person to look at this
needs the shapes as much as the numbers.
"""

from __future__ import annotations

import math
from typing import Any

from marble3d.config import CoreConfig, DEFAULT_CONFIG
from marble3d.geometry import Transform
from marble3d.machine import Machine
from marble3d.validation import Finding, check_mesh
from marble3d.units import MARBLE_DIAMETER

from sloped import joins, layout
from sloped.pathing import build_path
from sloped.scale import to_sim
from sloped.basin import StartBasin
from sloped.radial import RadialStart
from sloped.shuffle import ShuffleChamber
from sloped.trapdoor import ShuffleFloor
from sloped.widelaunch import WideLaunch
from sloped.stations import FinishDeck, ForkRidge, MergeCatch, Mixer, Spinners, StartGrid
from sloped.track import TrackRun

__all__ = [
    "CHAIN",
    "BRANCH_MODULES",
    "OBSTRUCTIONS",
    "START_KIND",
    "START_KINDS",
    "START_CLASSES",
    "start_module",
    "sloped_course",
    "check",
    "check_probes",
    "facts",
    "route_of_module",
]

# Modules that stand *in* the channel on purpose. A cradle probe fired where
# one of them is measures the obstruction and reports the floor as missing, so
# a hit owned by one of these answers the probe rather than failing it - which
# is the honest reading: the surface a marble meets there really is the pin.
# Anything else that intercepts a probe is a finding.
OBSTRUCTIONS = ("start", "mixer", "shuffle", "obstacle", "fork", "merge")

# The runs a marble meets in order, before the fork.
CHAIN = ("launch", "leg1", "leg2", "leg3")

# Which modules identify a route. Contact with any of these is the evidence
# `sloped.race` uses, because a bounding box cannot tell the two lobes apart -
# their AABBs overlap over a third of their extent.
BRANCH_MODULES = {
    "blue_lead": "blue",
    "blue": "blue",
    "orange_lead": "orange",
    "orange": "orange",
}


ROUTE_CHOICES = ("blue", "both")

# The sprint's guard rails, opened on **both** sides over the samples the merge
# apron is built around - `(side, full-before, open-from, open-to, full-after)`,
# with a side of zero meaning both.
#
# `sloped.stations.MergeCatch` runs from 2.30 layout units behind the sprint's
# entry to 1.70 in front of it, and 1.70 layout is 2.98 simulation units, which
# is the sprint's sample 9. So the rails are open from the sprint's first sample
# to its ninth and back to full by its fourteenth, which is 1.4 units clear of
# the apron's front edge.
#
# Why they have to be: a rail standing inside the apron leaves a ledge along its
# own top with the apron's roof over it, and a marble that strays outside the
# channel while crossing the apron comes to rest on that ledge. Measured, an
# orange marble stopped on the east rail at apron-frame across +2.337 with its
# centre 0.43 simulation units above the apron floor beneath it, at 0.52 wu/s.
# V1 lost 319 of its 747 marbles there, every one booked to `blue[100]`.
# Containment over the window is the apron's own outer walls and roof, which
# span the whole of it.
MERGE_GUARD_WINDOW = (0.0, -1, 0, 9, 14)

# The same thing on blue's own last samples, which are inside the apron too.
# `(side, full-before, open-from, open-to, full-after)` with a side of zero
# meaning both rails. Blue's mouth is at the merge lead's seam and the apron
# reaches 4.035 simulation units behind the sprint's entry, which falls between
# blue's samples 112 and 113; the window opens at 112 and runs to the end of
# the run, so `open-to` and `full-after` are both past its last sample.
BLUE_MERGE_WINDOW = (0.0, 111, 113, 118, 119)

# How much of leg3's east guard stands through the fork window, as a fraction
# of its full height - the sixth entry of `TrackRun.open_side`.
#
# **This is the fork's sorting crest, and it exists because the entry trim made
# a crest possible.** Before `sloped.joins.fork_trim`, orange's west half hung
# over leg3's channel with less than a marble of clearance, so nothing crossed
# on purpose and 36% of the field arrived on orange by being shoved there. With
# the overhang gone the two channels share one edge and the crossing is free -
# 74% of the field took it, which is more traffic than the merge apron was
# built for and blue's own completion fell from 91% to 38%.
#
# So the crossing needs a threshold, and the only surface between the two
# routes is leg3's own east guard standing on the shared edge. At 5% - the bare
# `OPEN_FLOOR` that exists so a scaled-away wall has no coincident vertices -
# it is 0.05 simulation units and a marble does not notice it. Scanned against
# whole races, `docs/validation/sloped_race_v1/v110/fork_lab_crest_height.json`.
FORK_CREST = 0.05

# --- the start correction -------------------------------------------------
#
# V1 put its one stud row on leg1 at the recorded `mix` node and called it the
# fairness mechanism. `sloped.startlab` measured what it actually does, over
# 400 seeds of the start, the launch and leg1 alone:
#
#   * The eight bays are within three ticks of each other a quarter of the way
#     down the start fan and **76 ticks** apart at the launch seam. The whole
#     slot bias is made in the fan's second half, where the bare converging
#     trough funnels all eight marbles onto one line; the queue that forms
#     there is ordered by how far each bay had to travel sideways to reach it.
#   * The rest of the course preserves that order because it is a 3.3-diameter
#     channel in which everyone runs at the same terminal speed. By the launch
#     exit the field is strung out over eighteen simulation units.
#   * leg1's stud row is *downstream* of that. It can deflect a marble; it can
#     no longer reorder the field, because the field is no longer a field.
#
# Nine candidates were scanned before these two. A longitudinal bay stagger, a
# merge tree in the lane dividers, longer and shorter dividers, and three
# densities of deflector in the fan all made the bias **worse** - up to a span
# of 7.0 places out of a possible 7 - and they fail for one reason: every
# restriction added to a converging funnel is another queue, and a queue leaves
# in arrival order. Their numbers are in `tools/sloped_start_scan.py`.
#
# So the correction is two things on the launch run, where the field is still
# one channel-width long:
#
# **The stud row moves to launch sample 5.** Same nine studs, same 0.07 height.
# At leg1's seam the field arrives at 50 wu/s and a stud levers a marble out of
# the channel; here it arrives at 13 and the same stud deflects it. Losses over
# the start and leg1 fell from 15.95% to 1.19% on that move alone.
#
# **A single four-blade wheel at launch sample 32**, turning at 9.0 rad/s - the
# same `Spinners` class as the course's own obstacle, one wheel instead of
# three, so it is native to the machine rather than bolted on.
#
# It went in as a fairness mechanism at sample 7 and stayed as a reliability
# one, and the correction is worth recording because the lab got it wrong
# first. A wheel is the only mechanism scanned whose output order is not
# monotone in its input order - a marble's wait is its arrival time modulo the
# blade period - and at sample 7, where the field is still a clump, it did take
# the rank span from 3.71 places to 2.33. It also held 13% of the field up
# doing it, and on the real course that was **18.8% stuck**, all at launch[0].
# The lab could not see it, because a marble grinding along behind an
# obstruction has neither left the channel nor stopped dead; `startlab`'s
# `trailing` exists because of this row.
#
# A span bought by jamming a fifth of the field is not fairness. Faster is
# worse, not better - at 12 rad/s the same wheel bats a 13 wu/s marble back up
# the channel and 80% of the field never leaves. On the real course, 16 seeds
# of eight:
#
#     wheel             finish  escape   stuck
#     none               0.906   0.031   0.062
#     sample  7,  6.0    0.802   0.010   0.188
#     sample  7, 12.0    0.177   0.021   0.802
#     sample 24,  9.0    0.922   0.016   0.062
#     sample 32,  9.0    0.969   0.016   0.016
#     sample 40,  9.0    0.930   0.016   0.055
#
# So the wheel belongs downstream, where the field is at 30 wu/s and the blade
# tip at 9.5 is a tap rather than a gate. At sample 32 it beats having no wheel
# at all on every count, and it still takes the span from 3.705 to 3.345.
#
# **That 10% is the honest size of the fairness win.** The bias is diagnosed
# exactly - see above - and no physical geometry scanned in this session
# removes it without wrecking the race. `docs/sloped_race_v11.md` says so.
MIXER_SAMPLE = 5
SHUFFLE_SAMPLE = 32
SHUFFLE_RATE = 9.0

# --- the local rail boosts, one per concentrated escape site -------------
#
# `(extra, a, b, c, d)`: the rail is authored height before sample `a`, eases up
# to `authored + extra` by `b`, holds it to `c` and eases back by `d`. See
# `sloped.track.TrackRun.guard_extra`.
#
# **Three sites, each measured before it was given a rail.**
# `tools/sloped_escape_trace.py` records where the field leaves and with what,
# and `tools/sloped_continuity_check.py` audits the geometry it leaves on. The
# joins are exact - zero centreline gap, zero floor step, zero bank step on all
# three - and no run has a grade break worth naming, so the escapes are not a
# step or a seam. They are marbles going over the top of a 0.26 rail:
#
#     launch[27..51%]   7 of 768, centres 0.66 to 1.39 high against a 0.800
#                       containment, 0.3 outside the rail's face, at 19 to 26
#                       layout units per second with 4 to 9 of that lateral
#     leg1[72..76%]     5 of 768, the same picture at 25 to 29, in the +28
#                       degree hairpin
#     leg2[63..76%]     the audit's tightest turns - radius 1.77 at sample 88
#                       under 22 degrees of bank, with a 12.1 degree tangent
#                       break in the same place
#
# The launch site is the one the V1.8 start created: the axial catch's 3.93 lift
# delivers the field to launch[0] with 4.26 of drop behind it against the fan's
# 0.59, so it arrives as a clump at roughly three times the speed and the
# marbles throw *each other* into the rails. The other two are pre-existing and
# the fan loses the same 5 of 768 at leg1.
#
# **Why a rail and not a bank, a radius or a slope.** `sloped.contract` pins the
# centreline, the widths, the drops and the bank extremes of every run against
# `physics_layout.json` and the drawn asset, and `course.check()` has to stay at
# zero findings - so none of those is available. The rail's height is not
# pinned, it is the surface the marbles are demonstrably clearing, and
# `v2_track.gd` carries the same windows so the drawn rail and the collider
# agree. Section 1 of the V1.9 brief lists "guard" first for the same reason.
#
# A shallower exit chute was tried first and is falsified: at 11 degrees the
# clump stacks in the chute and *none* of 768 racers ever reached a run, which
# is V1.7's own measured floor of about 15 degrees confirmed at the higher
# arrival speed.
GUARD_BOOSTS: dict[str, tuple[float, int, int, int, int]] = {
    "launch": (0.50, 12, 24, 70, 84),
    "leg1": (0.50, 46, 58, 100, 110),
    # **leg2's was speculative and it is under test.** It was added on the
    # strength of the continuity audit's tangent break at leg2[88] rather than
    # on a measured escape - the start lab carries only the launch and leg1, so
    # leg2's own losses were never traced. The 600-race benchmark then put 41
    # of 56 non-finishers at `leg2[99]` and **stuck rather than escaped**,
    # which is exactly what a rail that retains a marble it used to lose looks
    # like: the racer scrubs its speed against the wall through the hairpin and
    # arrives at leg2's shallowest grade too slow to carry on.
    # **leg2's was added on an audit finding rather than a measured escape,
    # and the A/B that questioned it came back inconclusive.** The start lab
    # carries only the launch and leg1, so leg2's own losses were never traced;
    # this window went in on the continuity audit's 12.1-degree tangent break
    # at leg2[88] with its 1.77 turn radius under 22 degrees of bank.
    #
    # The 600-race benchmark then put 41 of 56 non-finishers at `leg2[99]` and
    # **stuck rather than escaped**, which is what a rail that retains a marble
    # it used to lose looks like - the racer scrubs its speed against the wall
    # and arrives at leg2's shallowest grade too slow to carry on. So the boost
    # was removed and 100 races run against the 600 with it:
    #
    #                     with boost (4800)  without (800)   difference
    #     finish rate            0.9883         0.9850     -0.0033 +- 0.0090
    #     escape rate            0.0025         0.0050     +0.0025 +- 0.0051
    #     stuck rate             0.0092         0.0100     +0.0008 +- 0.0074
    #     all eight              0.9100         0.8800     -0.0300 +- 0.0677
    #     leg2 site rate         0.0085         0.0112     +0.0027 +- 0.0078
    #
    # **Every difference is inside its own 95% interval.** The hypothesis is
    # not supported and the boost is not shown to be harmful either. It stays,
    # because it went in on a measured geometry defect, because every point
    # estimate is nominally better with it, and because the production
    # benchmark was run with it. **`leg2[99]`'s stalls are not this window's
    # doing, and the mechanism is now measured** - see `BANK_SLEWS` below and
    # `sloped.track._slewed_bank`. The guess recorded above, that the racer
    # scrubs its speed against the rail and arrives too slow, is wrong: what
    # takes the speed is another marble, and what keeps it is a pocket the
    # unwinding roll digs on the outside of the inflection.
    "leg2": (0.50, 60, 72, 106, 116),
}

# Where a run's roll is not allowed to unwind faster than the drop pays for,
# as (first sample, last sample, margin).
#
# **This is the mechanism `leg2[99]` was missing.** On this course the outside
# of a turn is the low side, so a roll coming off *raises* what rides it. At
# leg2's inflection the roll unwinds about five degrees a sample against a 10%
# fall, so over samples 98 to 103 the unwind eats 89.7% of the drop - which
# leaves a closed pocket on the outside, 0.0685 deep at a lateral fraction of
# 0.6 and 0.2504 at the rail, while the centreline runs downhill the whole way.
#
# The pocket cannot stop a moving marble: the climb asks 1.37 units per second
# and the field runs at 30 to 70. What stops them is each other, in the pocket,
# because the same inflection sweeps every marble across the channel from a
# fraction of -0.7 to +0.7 - so 99 to 101 is both where the field crosses and
# where anything stopped is kept. Traced, three racers lost +37.11, +35.74 and
# +37.95 of forward speed to a single marble contact and never left; re-run at
# 90 seconds, more than twice the race, all seven of a sample were still there.
#
# Installed, the pocket is **0.0000 at every lateral fraction** - the run
# descends monotonically everywhere - for twelve changed samples, a worst
# deviation of 10.14 degrees, and `max(abs(banks))` untouched at 22.0000.
#
# `sloped.track._slewed_bank` has the constraint, which is exact, and the three
# things that are counter-intuitive about it. **A margin of 1.0 is the best
# setting, not the weakest**: it is the least-restrictive rule that still
# forbids an edge rising, and tightening it makes the pocket *worse* (0.0743 at
# a fraction of 0.6 for margin 0.8, 0.1391 for 0.6) because the roll then lags
# far enough to have to catch up inside the window. **The window must be wide
# enough for the limit to rejoin the authored curve on its own** - ended at 108
# it snaps back with a 0.95 degree step and leaves a residue; given until 112 it
# rejoins at 110. And **a hold is not a substitute** - holding the roll for
# eight samples moves the pocket from sample 102 to 112 at the same depth
# (0.0685 to 0.0613 at a fraction of 0.6) and left a marble hovering 0.84 above
# the floor at `leg2[104]` in contact validation.
#
# Available where bank, radius and slope are not, for the same reason
# `GUARD_BOOSTS` is: `sloped.contract` pins the bank **extreme** and nothing
# about the profile between, and a limit only unwinds more slowly through an
# angle the run already reaches. `v2_track.gd` carries the same table.
BANK_SLEWS: dict[str, tuple[int, int, float]] = {
    "leg2": (98, 112, 1.0),
    # **blue's tail carries the same defect, 4.4x deeper, and it was never
    # surveyed.** `tools/sloped_pocket_survey.py` walks `CHAIN + ("final",)`
    # only, so neither branch lobe was ever measured; `sloped.junction`'s
    # survey covers them and `tools/sloped_junction_audit.py` prints it. blue's
    # roll reverses from -17.45 degrees at sample 89 to +10.50 at 99 while the
    # centreline falls 0.164 layout units, and the reversal costs 0.372 - a
    # ratio of 2.28 - so its east edge climbs where its centre descends:
    #
    #     fraction   0.00     0.40     0.55     0.70     0.85     0.95
    #     authored 0.0000   0.0442   0.1181   0.2083   0.3013   0.3635
    #     limited  0.0000   0.0000   0.0000   0.0000   0.0000   0.0000
    #
    # **The top of that climb is sample 98, and `blue[100]` is the loss site.**
    # It was 8 of V1.11's 24 remaining non-finishers over 4800 racers, and it
    # is where V1 lost 319 of 747 marbles. Injected at blue[96] at 4 to 12
    # wu/s, two of 28 marbles came to rest at `blue[90]` and `blue[92]`.
    #
    # Three things this costs and one it buys back, all measured against the
    # authored run at 41 and 50 wu/s:
    #
    # * the bank extreme is untouched - 24.0000 degrees, at sample 54, well
    #   outside the window - so `contract.check()` stays at zero findings;
    # * the roll's **sign flip moves from sample 95 to 103**, out of the
    #   stretch where blue's own inflection sweeps the field across the
    #   channel, which is the mechanism rather than a side effect;
    # * over samples 95 to 103 the roll is then banked the *wrong way* for its
    #   corner, and that is measured to cost nothing: `ride_height` is
    #   **0.2050 layout units either way** at both speeds, against a
    #   containment of 0.6560, and `runs_out` is zero on every sample of the
    #   whole run before and after;
    # * and the worst bank *rate* falls from 13.65 degrees per layout unit -
    #   over the 12.0 the continuity audit flags - to 6.86.
    #
    # The window opens at 84 and the constraint does not bind until 86, which
    # is deliberate slack; opening it at 86 leaves 0.0152 at the edge. It
    # rejoins the authored curve inside its own window with a residual of 0.00.
    "blue": (84, 117, 1.0),
    # **Orange's is the whole run, and that is what makes it possible.** Its
    # tail carries three roll reversals, not one: the roll runs +18.1 degrees
    # at sample 84 to -31.9 at 99 to +18.0 at 107, and the basins are the
    # deepest on the course by a factor of thirteen -
    #
    #     fraction   0.00     0.40     0.55     0.70     0.85     0.95
    #     authored 0.0000   0.2910   0.4602   0.6308   0.8035   0.9223
    #     limited  0.0000   0.0000   0.0000   0.0000   0.0000   0.0002
    #
    # - and the marbles ride out there: `sloped_continuity_check` puts the ride
    # height at 0.31 to 0.42 of a 0.54 containment through samples 103 to 110.
    #
    # **A window over the tail alone cannot do it and the whole run can**,
    # which is the opposite of the leg2 result and is worth stating plainly.
    # Over samples 84 to 118 the authored roll costs 1.5310 layout units of
    # drop and has 0.3871 - a ratio of 3.96 - so a rate cap started at 84 lags
    # and never catches up: it leaves 0.1864 at the edge. Over the *whole* run
    # the ratio is 0.82, because orange descends 3.30 units in total. Started
    # at sample 0 the cap never lets the roll wind on faster than the drop
    # pays for either, so it never reaches the excursions it would then have
    # to pay back, and the total variation it has to fund is its own and not
    # the authored one. Scanned: a window from 20, 40, 50, 60 or 70 all give
    # 0.0274; from 0 it gives 0.0002.
    #
    # The bank extreme is preserved exactly at 32.0000 - the roll holds +32 for
    # 24 samples, so the cap reaches it - and `ride_height` is 0.2050 layout
    # units before and after at 41 wu/s and 0.3608 at 50, with `runs_out` zero
    # in every case. What it buys is the *rate*: 47.44 degrees per layout unit
    # and 27 samples over the continuity audit's 12.0 threshold become 16.11
    # and far fewer. Nine samples end up banked the wrong way for their corner
    # and that is measured to cost nothing, the same as blue's.
    #
    # Measured on eight-marble traffic through orange's tail and the merge:
    # 13 of 28 finish authored, 22 of 28 limited.
    "orange": (0, 117, 1.0),
}

# Which start the course is built with.
#
# **"fan", because the basin was measured and is worse.** `sloped.basin` builds
# the architecture V1.3 was asked for - one wide flat ramp feeding a shallow
# stadium dish with a single spillway - and it works: all eight marbles drain,
# every seed, with no jam. It is still worse than the taper it replaced. Over
# 100 seeds of the real course, blue route:
#
#     start          finish   win ratio   win spread
#     fan             0.985       11.50      21 pts
#     basin           0.968       29.00      28 pts
#     basin + island  0.965       16.00      30 pts
#
# and the basin's win rates by bay come out 1 1 13 12 29 28 14 2 - the same
# centre-heavy V the taper produces, from the same cause. `sloped.basin` has
# the mechanism; the short version is that a single common exit orders the
# field by distance to that exit, and distance to the exit is a function of
# which bay you started in. Room to mill is not a reason to mill.
#
# The basin stays in the tree because it is the only clean test of that claim
# in a second topology, and because it is one line to switch back to.
#
# --- V1.9: "floor", and the start is now frozen -------------------------
#
# `sloped.trapdoor.ShuffleFloor` - the rotor chamber with a full-floor louvre
# release and a catch cone on the chamber's own axis. Measured against the
# taper in one instrument over 96 seeds each, 768 racers each:
#
#     start                   delivered  exit span  slot r  centre r    sd
#     fan, as shipped           99.349%     2.927   -0.387   +0.574   0.863
#     floor, as frozen          98.307%     1.177   +0.378   -0.090   0.376
#
# `sd` is the standard deviation of the eight slot mean ranks, which privileges
# no shape - the two correlations disagreed about which start was fairer and
# each was measuring its own. **0.863 to 0.376 is a 2.3x cut in the shape-free
# magnitude of the start bias**, and that is what the V1 decision was taken on.
# `docs/sloped_race_v18_floor.md` has the architecture and
# `docs/sloped_race_v19_production.md` the full-race numbers.
#
# The residual is a bearing residual that no amount of rotor removes, and it is
# recorded as a V1 limitation rather than reopened.
START_KIND = "floor"


# The three start topologies, by the name every plan, tool and report names
# them with. One table rather than a chain of `if`s, because the table is what
# lets `start_module` check its own answer - see below.
START_CLASSES = {
    StartGrid.START_KIND: StartGrid,
    StartBasin.START_KIND: StartBasin,
    RadialStart.START_KIND: RadialStart,
    WideLaunch.START_KIND: WideLaunch,
    ShuffleChamber.START_KIND: ShuffleChamber,
    ShuffleFloor.START_KIND: ShuffleFloor,
}
START_KINDS = tuple(START_CLASSES)


def start_module(kind: str, launch, **options):
    """One of the start topologies, by name.

    `fan` is V1.1's taper and `basin` V1.3's stadium dish, both falsified for
    slot bias; `radial` is V1.4's ring, falsified in V1.5 - see
    `docs/sloped_race_v15_apron.md`. All three are kept because they are the
    topologies the mechanism was measured in. `wide_launch` is V1.6's
    unconstricted raceway, falsified in the same session - see
    `docs/sloped_race_v16_widelaunch.md`, which concludes that passive start
    geometry is exhausted. `rotor` is V1.7's dynamic equaliser and `floor`
    is V1.8's - the same chamber, with its selective outlet replaced by a floor
    that opens under the whole field at once. They are the only two of the six
    that are not shapes: see `sloped.shuffle` and `sloped.trapdoor`.

    **The built module is asked what it is, and the answer is checked against
    what was requested.** That is not defensive noise: V1.4 recorded a
    300-seed "fan" start baseline that was really the basin's, because a
    `StartPlan`'s `start_kind` defaulted to `"basin"` while
    `sloped.course.START_KIND` said `"fan"` and nothing in the chain compared
    the two. Every layer that names a start kind now re-checks it, so the three
    cannot be silently confused again.
    """
    if kind not in START_CLASSES:
        raise ValueError(
            f"start must be one of {START_KINDS}, not {kind!r}"
        )
    module = START_CLASSES[kind]("start", launch, **options)
    if module.START_KIND != kind:
        raise AssertionError(
            f"start_module({kind!r}) built a {type(module).__name__}, which "
            f"declares START_KIND {module.START_KIND!r}"
        )
    return module


def sloped_course(config: CoreConfig | None = None, routes: str = "blue") -> Machine:
    """Layout B, made physical. Every module placed at its recorded position.

    `routes` is `"blue"` - the through route only - or `"both"`, which adds the
    fork, orange's lead and orange's lobe. See the module docstring for the six
    measurements behind that default.
    """
    if routes not in ROUTE_CHOICES:
        raise ValueError(f"routes must be one of {ROUTE_CHOICES}, not {routes!r}")
    config = config or DEFAULT_CONFIG
    machine = Machine("sloped_b" if routes == "blue" else "sloped_b_split")
    forked = routes == "both"

    runs: dict[str, TrackRun] = {
        name: TrackRun(
            name,
            # leg3's east guard, with a window in it rather than a ramp; see
            # `sloped.joins.FORK_GUARD_WINDOW` for why it is where it is.
            open_side=(
                (
                    1.0,
                    *(joins.FORK_SAMPLE + n for n in joins.FORK_GUARD_WINDOW),
                    FORK_CREST,
                )
                if (name == "leg3" and forked)
                else None
            ),
            guard_boost=GUARD_BOOSTS.get(name),
            bank_slew=BANK_SLEWS.get(name),
        )
        for name in CHAIN
    }
    # The sprint's two guard rails are opened where the merge apron is built
    # around them; see `MERGE_GUARD_WINDOW`.
    runs["final"] = TrackRun("final", open_side=MERGE_GUARD_WINDOW)
    # Both lobes entered one control in, so a lead can exist at all; see
    # `sloped.joins`.
    blue_spec = dict(layout.run("blue"))
    blue_spec["controls"] = joins.blue_controls()
    runs["blue"] = TrackRun(
        "blue",
        spec=blue_spec,
        bank_slew=BANK_SLEWS.get("blue"),
        # Blue's last samples stand inside the roofed apron, so its rails are
        # opened there for the same reason the sprint's and the merge lead's
        # are: a rail inside a roofed apron leaves a ledge along its own top,
        # and V1 lost 319 of 747 marbles resting on one. Blue's mouth is 1.899
        # units behind the sprint's entry and the apron reaches 4.035 behind
        # it, which is blue's sample 112.
        open_side=BLUE_MERGE_WINDOW,
    )
    # Orange's lobe entered at its second authored control; see `sloped.joins`.
    if forked:
        orange_spec = dict(layout.run("orange"))
        orange_spec["controls"] = joins.orange_controls()
        runs["orange"] = TrackRun(
            "orange", spec=orange_spec, bank_slew=BANK_SLEWS.get("orange")
        )

    paths = joins.join_paths()
    if not forked:
        paths.pop("orange_lead", None)
    for name, path in paths.items():
        runs[name] = TrackRun(
            name,
            spec=joins.JOIN_SPECS[name],
            path=path,
            # Sampled at the authored runs' own density, 0.289 layout units,
            # rather than at the Hermite's 48 points. Two things depend on it
            # and both bit: `auto_bank` computes curvature from consecutive
            # samples and eases its first six to level, so a join at twice the
            # density rolls to 30 degrees in one layout unit and throws a
            # marble arriving level off the seam - 15 of 24 stopped at leg3's
            # exit; and the collider's facet size is a physics parameter, the
            # 4%-of-a-radius sagitta the core is calibrated at.
            samples=max(8, int(round(joins.path_span(path) / 0.289))),
            # And orange's lead has its west lip opened out over the same
            # window, for the same reason from the other side.
            open_side=(
                (-1.0, -1, 0, 4, joins.FORK_WINDOW_ORANGE)
                if name == "orange_lead"
                else None
            ),
            # Both leads open at the full hero width, because that is what
            # hands over to them, and close to their lobe's own 0.82 by the
            # time they reach it. The *scale* stays hero rather than being 0.82
            # with the width scaled up: a 0.82 profile is 0.82 as *deep* as
            # well, and a lead is the only thing catching a marble that has been
            # thrown across the fork's combined channel at 43 wu/s - with 1.16
            # of containment instead of 1.40 it does not catch it.
            taper=(
                joins.LEAD_MOUTH_FLARE if name == "orange_lead" else 1.0,
                layout.BRANCH_SCALE,
            ),
        )

    # Blue's tail hands onto a **channel** into the sprint rather than onto the
    # merge apron's height field. `sloped.joins.merge_lead_path` has the three
    # measured reasons; the short one is that an apron laid over a channel is
    # only flush where its own cradle happens to line up with the channel's, and
    # blue's is 0.26 to 0.52 units off the sprint's and yawed 7.5 degrees.
    #
    # Solved from the two built runs and installed after both exist, because its
    # endpoints are their poses. `MERGE_LEAD_WIDTH` opens at blue's own width
    # and eases to `final[0]`'s flare, which is measured rather than chosen.
    runs["merge_lead"] = TrackRun(
        "merge_lead",
        spec=joins.JOIN_SPECS["merge_lead"],
        path=joins.merge_lead_path(runs["blue"], runs["final"]),
        samples=joins.MERGE_LEAD_SAMPLES,
        taper=joins.MERGE_LEAD_WIDTH,
        # The apron stands around the lead as well as around the sprint, so the
        # lead's rails are opened over the whole of it for the same reason the
        # sprint's are - see `MERGE_GUARD_WINDOW`. A rail inside an apron leaves
        # a ledge along its own top with the roof over it.
        open_side=(0.0, -1, 0, joins.MERGE_LEAD_SAMPLES, joins.MERGE_LEAD_SAMPLES),
    )

    # Orange's lead stops overhanging leg3's channel. Solved from the two built
    # runs and installed after both exist, because the answer is where one
    # crosses the other; `sloped.joins.fork_trim` has the measurement and the
    # eight racers a sample it was costing.
    if forked:
        runs["orange_lead"].set_entry_trim(joins.fork_trim(runs["leg3"], runs["orange_lead"]))
        # **Orange's mouth is NOT trimmed, and that is a measurement.** It
        # overhangs the sprint's east running edge by 0.30 to 0.50 units at
        # `final[5..7]`, which is a shelf, and `sloped.joins.merge_trim` solves
        # the fold that would remove it. Installed, it made orange worse:
        # 78.6% of an eight-marble tail sweep to 67.9%, and 60.7% to 7.1% for
        # marbles launched alone. See `merge_trim` for why the mechanism does
        # not transfer from the fork - there the folded-away part had leg3's
        # floor under it at the same height, and here the sprint's floor is
        # 0.34 to 0.9 below, so the fold turns a shelf into a waterfall.

    start = start_module(START_KIND, runs["launch"])
    # Declaration order is the build order and therefore the body numbering, so
    # it is part of the run; the wedge is declared where it belongs in flow even
    # though it needs the lead that is declared after it.

    machine.add(start, Transform())
    for name in CHAIN:
        machine.add(runs[name], Transform())
    # The two pieces of the start correction, both on the *launch* run rather
    # than on leg1. `sloped.startlab` measured them; `MIXER_SAMPLE` and
    # `SHUFFLE_SAMPLE` carry the argument.
    machine.add(Mixer("mixer", runs["launch"], at=MIXER_SAMPLE), Transform())
    if SHUFFLE_SAMPLE is not None:
        machine.add(
            Spinners(
                "shuffle", runs["launch"], at=SHUFFLE_SAMPLE, offsets=(0.0,), rate=SHUFFLE_RATE
            ),
            Transform(),
        )
    machine.add(Spinners("obstacle", runs["leg2"]), Transform())
    if forked:
        machine.add(
            ForkRidge(
                "fork",
                runs["leg3"],
                joins.FORK_SAMPLE,
                runs["orange_lead"],
                joins.FORK_WINDOW_BLUE,
            ),
            Transform(),
        )
    branch = ("blue_lead", "blue", "orange_lead", "orange") if forked else ("blue_lead", "blue")
    for name in branch:
        machine.add(runs[name], Transform())
    machine.add(runs["merge_lead"], Transform())
    machine.add(
        MergeCatch(
            "merge",
            runs["final"],
            runs["merge_lead"],
            runs["blue"],
            runs.get("orange"),
        ),
        Transform(),
    )
    machine.add(runs["final"], Transform())
    machine.add(FinishDeck("finish", runs["final"]), Transform())

    machine.runs = runs                      # type: ignore[attr-defined]
    machine.routes = routes                  # type: ignore[attr-defined]
    machine.finish_line = runs["final"].socket("exit")   # type: ignore[attr-defined]
    return machine


# --- the seams ------------------------------------------------------------

SEAMS = (
    ("start", "exit", "launch", "entry"),
    ("launch", "exit", "leg1", "entry"),
    ("leg1", "exit", "leg2", "entry"),
    ("leg2", "exit", "leg3", "entry"),
    ("leg3", "exit", "blue_lead", "entry"),
    ("blue_lead", "exit", "blue", "entry"),
    ("orange_lead", "exit", "orange", "entry"),
    # The merge lead closes the junction in position, heading and roll on both
    # sides, which is the whole point of it being a channel; before it, blue
    # handed onto a height field and there was no seam to check.
    ("blue", "exit", "merge_lead", "entry"),
    ("merge_lead", "exit", "final", "entry"),
)


def _seams_for(machine: Machine):
    return tuple(
        seam for seam in SEAMS if seam[0] in machine.modules and seam[2] in machine.modules
    )

POSITION_BUDGET = 0.5 * MARBLE_DIAMETER
HEADING_BUDGET = 24.0
BANK_BUDGET = 6.0


def check(machine: Machine | None = None, config: CoreConfig | None = None) -> list[Finding]:
    """Every disagreement the assembly can be asked about.

    Seams, turn radii, the fork's position, mesh integrity and the one thing a
    mesh check cannot see: whether a join's *end* tangent is the tangent of the
    run it hands to. A join that closes in position and not in direction is a
    kink, and a kink at these speeds is a marble leaving the channel.
    """
    machine = machine or sloped_course(config)
    config = config or DEFAULT_CONFIG
    runs: dict[str, TrackRun] = machine.runs                # type: ignore[attr-defined]
    findings: list[Finding] = []

    def report(check_name: str, subject: str, detail: str) -> None:
        findings.append(Finding(check=check_name, subject=subject, detail=detail))

    for up_name, up_socket, down_name, down_socket in _seams_for(machine):
        upstream = machine.modules[up_name]
        downstream = machine.modules[down_name]
        try:
            a = upstream.socket(up_socket)
            b = downstream.socket(down_socket)
        except KeyError as error:
            report("seam", f"{up_name}->{down_name}", str(error))
            continue
        gap = math.dist(a.frame.position, b.frame.position)
        if gap > POSITION_BUDGET:
            report(
                "seam-gap",
                f"{up_name}->{down_name}",
                f"{gap:.4f} between the sockets (budget {POSITION_BUDGET:.4f}, "
                f"a marble radius)",
            )
        turn = abs(_wrap(math.degrees(b.heading() - a.heading())))
        if turn > HEADING_BUDGET:
            report(
                "seam-heading",
                f"{up_name}->{down_name}",
                f"{turn:.2f} degrees of kink (budget {HEADING_BUDGET})",
            )
        if up_name in runs and down_name in runs:
            step = abs(
                math.degrees(runs[up_name].banks[-1] - runs[down_name].banks[0])
            )
            if step > BANK_BUDGET:
                report(
                    "seam-bank",
                    f"{up_name}->{down_name}",
                    f"{step:.2f} degrees of roll step (budget {BANK_BUDGET})",
                )

    # Turn radii on the joins, against what the measured arrival speed holds.
    for name, spec in joins.JOIN_SPECS.items():
        if name not in runs:
            continue
        run = runs[name]
        speed = float(spec["design_speed"])
        allowed = joins.min_radius_layout(speed, float(spec["bank_max"]))
        worst, at = _worst_radius(run.path)
        # **The radius is reported against the drift it actually costs.** A
        # steady-state radius budget fails six of the seven authored runs,
        # including leg2 at less than half its own limit, and those runs ship;
        # what separates a tight sample from a defect is whether the marble
        # ends up somewhere else. `joins.TURN_DRIFT_BUDGET` carries both tables.
        drift = joins.turn_drift(run.path, speed, float(spec["bank_max"]))
        half = 0.5 * run.clear_width * max(run.widths) / to_sim(1.0)
        if worst < allowed and drift > joins.TURN_DRIFT_BUDGET * half:
            report(
                "turn-radius",
                name,
                f"sample {at} turns at {worst:.3f} layout units against the "
                f"{allowed:.3f} a marble at {speed:.0f} wu/s holds on a "
                f"{spec['bank_max']:.0f}-degree bank, and walks it {drift:.4f} "
                f"off the centreline against a {half:.3f} half width",
            )

    # The fork is where leg3 crosses south, and nothing may move it silently.
    # Checked whether or not the fork is built, because `FORK_SAMPLE` is also
    # what the guard window and the route attribution are measured from.
    leg3 = runs["leg3"]
    crossing = min(range(len(leg3.path)), key=lambda index: abs(leg3.heading_deg(index)))
    if crossing != joins.FORK_SAMPLE:
        report(
            "fork",
            "leg3",
            f"the heading crosses zero at sample {crossing}, not at the "
            f"{joins.FORK_SAMPLE} the fork is placed on",
        )

    for module in machine:
        for mesh in module.local_colliders():
            findings.extend(
                check_mesh(mesh, config.collider, expect_components=None)
            )
    return findings


def _wrap(angle: float) -> float:
    while angle > 180.0:
        angle -= 360.0
    while angle < -180.0:
        angle += 360.0
    return angle


def _worst_radius(path) -> tuple[float, int]:
    """The tightest plan-view turn on a path, in layout units, and where.

    Measured on the built path rather than on the arc that was solved for,
    because a Catmull-Rom or a Hermite through the same poses is not that arc,
    and the difference is exactly where a join goes wrong.
    """
    worst, at = float("inf"), 0
    for index in range(1, len(path) - 1):
        a, b, c = path[index - 1], path[index], path[index + 1]
        v0 = (b[0] - a[0], b[2] - a[2])
        v1 = (c[0] - b[0], c[2] - b[2])
        l0 = math.hypot(*v0)
        l1 = math.hypot(*v1)
        if l0 < 1e-9 or l1 < 1e-9:
            continue
        cross = v0[0] * v1[1] - v0[1] * v1[0]
        turn = math.asin(max(-1.0, min(1.0, cross / (l0 * l1))))
        if abs(turn) < 1e-9:
            continue
        radius = ((l0 + l1) * 0.5) / abs(turn)
        if radius < worst:
            worst, at = radius, index
    return worst, at


def check_probes(machine: Machine, world) -> list[Finding]:
    """Fire every module's probes at the assembled world and report what is off.

    Two classes of hit are answered rather than failed, and both are named
    rather than absorbed into a loose tolerance:

    * an obstruction - a mixer pin, a spinner shaft, the fork's wedge, a gate
      paddle - standing where the probe was aimed at the floor;
    * the first sample of a run whose upstream neighbour is still there, where
      the two runs' entry and exit width flares differ by 5% of a half width
      and the surface steps by up to 0.06 simulation units. That step is in the
      render too, because both runs are drawn with their own flare, so the
      collider is reproducing a seam rather than inventing one.
    * the merge apron's own upstream edge, answered by **blue's** collider.
      The apron there is built to follow blue's channel rather than a chord to
      the sprint - that correction is what closed the `blue[100..119]` stop
      trap - so the two surfaces now agree to about 0.03 and the ray reaches
      whichever is a hair higher. A probe aimed at the apron and answered by
      blue at 0.053 is the two being one surface, which is the thing that was
      wanted; before the correction the apron stood 0.114 clear of blue there
      and the probe hit it cleanly, which is the thing that was wrong.
    """
    from marble3d.validation import probe_world

    findings: list[Finding] = []
    for finding in probe_world(world, machine.probes()):
        detail = finding.detail
        if any(f"on '{name}'" in detail for name in OBSTRUCTIONS):
            continue
        if "[0]" in finding.subject and "cradle" in finding.subject:
            continue
        if finding.subject.startswith("merge.apron[0]") and "on 'blue'" in detail:
            continue
        findings.append(finding)
    return findings


def route_of_module(module_id: str) -> str | None:
    return BRANCH_MODULES.get(module_id)


def facts(machine: Machine | None = None) -> dict[str, Any]:
    """The course, as the numbers a report has to quote."""
    machine = machine or sloped_course()
    runs: dict[str, TrackRun] = machine.runs               # type: ignore[attr-defined]
    shared = runs["leg3"].sim_arc[joins.FORK_SAMPLE]
    blue_route = (
        runs["launch"].sim_arc[-1]
        + runs["leg1"].sim_arc[-1]
        + runs["leg2"].sim_arc[-1]
        + runs["leg3"].sim_arc[-1]
        + runs["blue_lead"].sim_arc[-1]
        + runs["blue"].sim_arc[-1]
        + runs["final"].sim_arc[-1]
    )
    orange_route = (
        (
            runs["launch"].sim_arc[-1]
            + runs["leg1"].sim_arc[-1]
            + runs["leg2"].sim_arc[-1]
            + shared
            + runs["orange_lead"].sim_arc[-1]
            + runs["orange"].sim_arc[-1]
            + runs["final"].sim_arc[-1]
        )
        if "orange" in runs
        else 0.0
    )
    bounds = machine.bounds()
    triangles = sum(
        mesh.triangle_count for module in machine for mesh in module.local_colliders()
    )
    vertices = sum(
        mesh.vertex_count for module in machine for mesh in module.local_colliders()
    )
    return {
        "modules": len(machine.order),
        "vertices": vertices,
        "triangles": triangles,
        "bounds": [
            [round(v, 3) for v in bounds.lower],
            [round(v, 3) for v in bounds.upper],
        ],
        "runs": {name: run.describe() for name, run in runs.items()},
        "routes": getattr(machine, "routes", "blue"),
        "route_length_sim": {
            "blue": round(blue_route, 4),
            "orange": round(orange_route, 4),
            "difference": round(orange_route - blue_route, 4),
            "difference_pct": (
                round(100.0 * (orange_route - blue_route) / blue_route, 3)
                if orange_route
                else None
            ),
        },
        "route_length_layout": {
            "blue": round(blue_route * 0.57, 4),
            "orange": round(orange_route * 0.57, 4),
        },
        "fork": {
            "built": "fork" in machine.modules,
            "sample": joins.FORK_SAMPLE,
            "stem_heading_deg": round(runs["leg3"].heading_deg(joins.FORK_SAMPLE), 3),
            "blue_heading_deg": round(runs["leg3"].heading_deg(joins.FORK_SAMPLE + 8), 3),
            "orange_heading_deg": (
                round(runs["orange_lead"].heading_deg(8), 3)
                if "orange_lead" in runs
                else None
            ),
        },
        "join_radius_layout": {
            name: {
                "worst": round(_worst_radius(runs[name].path)[0], 4),
                "allowed": round(
                    joins.min_radius_layout(
                        float(spec["design_speed"]), float(spec["bank_max"])
                    ),
                    4,
                ),
                # What the shortfall actually costs, and what the check is on.
                # See `joins.TURN_DRIFT_BUDGET` for why the radius alone is the
                # wrong test on a join a marble crosses in four milliseconds.
                "drift": round(
                    joins.turn_drift(
                        runs[name].path,
                        float(spec["design_speed"]),
                        float(spec["bank_max"]),
                    ),
                    4,
                ),
                "drift_budget": round(
                    joins.TURN_DRIFT_BUDGET
                    * 0.5
                    * runs[name].clear_width
                    * max(runs[name].widths)
                    / to_sim(1.0),
                    4,
                ),
            }
            for name, spec in joins.JOIN_SPECS.items()
            if name in runs
        },
    }

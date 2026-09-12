# V1.15 — the shoulder that closed onto a rising rail

Status: **`final[10]` is diagnosed, reproduced outside a race, and removed by
one constant.** `sloped.course.MERGE_GUARD_WINDOW` closes at the sprint's
sample 12 instead of its sample 9. Nothing else in the physics moves: the fork
pan, the fork crest, the guard windows, the merge apron's shape, blue's channel
and the frozen start are all untouched, and the route split does not shift.

Read [`sloped_race_v114_fork_pan.md`](sloped_race_v114_fork_pan.md) for the
baseline. `course.check()` and `contract.check()` report zero findings on both
route configurations before and after.

## The headline

Twenty four seeds, 3201-3224, 192 racers a row, everything but the window held.

    configuration     finish   all8    esc    stk | blue%  blue fin | orng%  orng fin
    9/14  (V1.14)      0.885   0.33  0.005  0.109 | 0.693     0.985 | 0.302     0.672
    12/14 (ships)      0.990   0.92  0.005  0.005 | 0.693     1.000 | 0.302     0.983

**The route share is identical to four decimals.** This buys survival without
moving the split, which is the thing every previous merge and fork change had
to trade against.

Held out, fifty fresh seeds the window was never chosen on, 3301-3350:

    metric              V1.14     V1.15
    per-racer finish    0.905     0.9825
    blue completion     0.987     0.9932
    orange completion   0.673     0.9519
    blue share          0.740     0.740
    escape              0.015     0.015
    stuck               0.080     0.005

    loss ledger   V1.14: final[10] 26  final[8] 3  final[7] 2  orange lobe 4
                         merge_lead[11] 1  orange_lead[12] 1  leg3[95] 1
                  V1.15: orange[36] 1  orange[23] 1  orange[26] 1  orange[2] 1
                         final[10] 1  orange_lead[12] 1  leg3[95] 1

**`final[10]` goes from 26 of 38 to 1 of 7**, and no site replaces it: the
seven remaining losses are seven different places, four of them inside orange's
own lobe.

## The mechanism: two closures on the same five samples

The apron's rim eases in to the channel's own edge between `TAPER_FROM` and
`FRONT`, which is `final[6.5]` to `final[14]`, so the shoulder converges into
the channel instead of ending in mid-air. `MERGE_GUARD_WINDOW` eased the
sprint's rails back up over `final[9]` to `final[14]`. Those two spans overlap
almost exactly, and the overlap is the defect. Measured off the built course,
in simulation units:

    final[]                      8      9     10     11     12     13     14
    clear shoulder (rim-rail) 1.976  1.639  1.219  0.778  0.381  0.090 -0.029
    rail top above the edge   0.422  0.422  0.524  0.767  1.058  1.301  1.404

A marble is 1.0 across. From `final[11]` the shoulder is **narrower than the
marble standing on it**, and by then the lip has climbed 0.40 out of the channel
edge. The rim wall sweeps across the marble's path at about 54 degrees to the
flow; the lip stops it going the other way; it wedges between them.

It is one pose, not a scatter. Every one of the 32 non-finishers that reached
the junction in the fifty held-out seeds came to rest on the **west** shoulder,
and 26 of them at exactly

    final[10.34]   across -2.208   rise +0.889
    touching `merge` (shoulder floor, rim wall) and `final` (the lip) at once

to three decimals across different seeds, different marbles and both routes.
V1.12's own rebuild notes record "six of six marbles at 30 to 36 wu/s came to
rest in it at the same point to two decimals - along +3.27, across -2.19", which
is the same corner measured before the shoulder had a name; the normalisation
fix that followed reduced a basin there and left this.

### What a failing racer actually does

`tools/sloped_final_trace.py`, seed 3304 marble 4, in the sprint's own
gravity-aligned frame. `along` is measured from `final[0]`'s centreline surface
point, `across` is horizontal and positive east.

    t 20.13  f[18.79]  across +6.73  rise +2.59  28 wu/s   in orange's channel
    t 20.53  f[ 3.48]  across +0.06  rise +0.48  25 wu/s   leaves orange's mouth
    t 20.63  f[ 2.66]  across -1.21  rise +0.69  11 wu/s   crossing the sprint
    t 20.73  f[ 2.96]  across -1.85  rise +0.93   4 wu/s   over the west lip
    t 20.93  f[ 6.71]  across -2.57  rise +0.92  11 wu/s   running down the shoulder
    t 21.13  f[10.47]  across -2.18  rise +0.96   1 wu/s   the rim wall
    t 21.33  f[10.34]  across -2.21  rise +0.89   0 wu/s   stopped, for 19 seconds

The asymmetry is the whole thing: **the lip is low enough at `final[3]` for an
11 wu/s marble to climb out of the channel and too high at `final[10]` for it to
climb back in**, because the lip is rising between the two. The marble is not
thrown out of the course; it steps over a threshold that then grows behind it.

## The rule, which is what ships rather than the number

Wherever the shoulder is still wide enough to hold a marble, the rail beside it
must still be open, so a marble the rim is squeezing has somewhere to go. The
shoulder is under a diameter from `final[11]`, so the rails may start rising at
12 and no earlier; and they must be full by 14, because that is where the
apron's own wall ends and `test_the_front_is_closed_and_the_rails_take_over`
already pins that handover to one station. **12 and 14 is the only pair that
satisfies both**, which is why this is a derivation rather than a scan.

`tests/test_sloped_open_side.py::test_the_sprints_window_stays_open_until_the_shoulder_has_closed`
states it that way - it walks the apron's own `rim` and the run's own
`wall_factor` and fails with the offending sample named - so it fails again if
either the taper or the window moves without the other.

## Two candidates that were measured and are not needed

    configuration                     finish   all8 | blue fin | orng fin
    window 12/14                       0.990   0.92 |    1.000 |    0.983
    window 12/15                       0.990   0.92 |    1.000 |    0.983
    taper_from 0.0 (window unchanged)  0.990   0.92 |    1.000 |    0.983

All three are the same fix seen from three sides - separate the two closures -
and they are indistinguishable over 192 racers. `12/14` ships because it is one
constant and it keeps the rails full at the apron's front edge exactly;
`12/15` puts the last 0.31 units of the handover outside the apron with the
rail at 75% of height, and `taper_from 0.0` narrows the shoulder orange crosses
from the sprint's entry onward, which is a change to the corridor rather than
to the corner.

## The instruments, and the one of mine that was wrong

Two new ones, both aimed at the merge the way `tools/sloped_fork_trace.py` is
aimed at the fork, and both reporting in the sprint's gravity-aligned frame
rather than in any run's banked profile units.

* **`tools/sloped_final_shoulder.py`** walks every surface under a grid of
  points as a **layer walk** rather than one ray, so the roof, the rim, the rail
  top, the shoulder floor and the cradle are reported separately. This is what
  found the shoulder at all.
* **`tools/sloped_final_trace.py`** records, for every racer at the junction,
  the pose, the velocity split three ways, every static collider in contact with
  it and the normal and depth of each, and a 30 Hz path. It is what turned "26
  losses near `final[10]`" into "one pose, at across -2.208, touching the lip and
  the rim at once".
* **`tools/sloped_final_lab.py`** launches single marbles onto the shoulder and
  asks only whether they passed `final[20]` or stopped. It reproduces the defect
  in seconds: **69 of 90 launches stopped at `final[10.34]`, across -2.208** -
  the pose from the races - and after the fix the same set clears 368 of 384.

**The lab's first sweep was worthless and said so by being too good.** It probed
for the floor with one downward ray, and inside a roofed apron the first thing a
downward ray meets is the **roof** - so it placed every marble a radius above the
station and reported 94 of 105 launches clearing while they rolled along the
roof and off its front edge. The fix is the same layer walk the shoulder audit
uses. That is the tenth session `instrument-bugs-hide-geometry-findings` applies
to, and the same shape as V1.14's "a support test placed a radius above the
surface is arithmetic, not geometry".

## What did not move

* `ForkPan`, `ForkPanEnd`, `FORK_CREST`, `FORK_WINDOW_PAN` and both guard
  windows: untouched, and the fork's own losses in the held-out fifty are the
  same two racers V1.14 recorded (`orange_lead[12]`, `leg3[95]`).
* `MergeCatch`'s shape: `BACK`, `FRONT`, `ACROSS`, `ROOF`, `FUNNEL`, `WALL_AT`,
  `RIM_MIN` and `TAPER_FROM` are all as V1.12 left them. `TAPER_TO` is **added**
  and defaults to `None`, which means `FRONT`, so the apron builds byte-identically
  unless it is set; it exists because the scan needed to price the other half of
  the overlap and because the constant is where the argument belongs.
* The frozen start, `BANK_SLEWS`, `GUARD_BOOSTS`, friction, timestep, gravity,
  mass and restitution.

## Known and carried

A second, older resting place on the west shoulder survives: at `along` -1.9,
across -2.1, where the shoulder's world height rises 0.028 between the apron's
back half and the sprint's entry. It is the **blue-to-lead seam** V1.12 measured
at 0.0571 and left, it holds a marble launched into it at rest or at 6 wu/s, and
in whole races it costs one racer in four hundred. It is recorded here rather
than fixed, because it is a different mechanism in a different place and section
8 of the brief asks for the smallest fix to the defect under investigation.

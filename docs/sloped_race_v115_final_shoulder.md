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
    rail top over the cradle  0.422  0.422  0.524  0.767  1.058  1.301  1.404

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

Three new ones, all aimed at the merge the way `tools/sloped_fork_trace.py` is
aimed at the fork, and all reporting in the sprint's gravity-aligned frame
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
  the pose from the races. On the wider set that ships as the regression - six
  stations, eight lateral offsets, four speeds and two approach angles, 384
  launches - the shipped window clears 368 against the old window's 208, and
  the 16 it does not clear are the older upstream basin below.

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

## The 200-seed gate: passed on fairness, short on reliability, and it names why

Seeds 4001-4200, 1600 racers, the shipped configuration.

    finish 0.983   all-eight 0.865   escape 0.015   stuck 0.003
    blue   share 0.751   completion 0.995   median 23.05 s
    orange share 0.249   completion 0.955   median 22.05 s

    loss sites  orange[20] 10   orange_lead[0] 6   final[0] 4
                leg3[80] 3   launch[20] 2   launch[40] 1   leg3[100] 1

Against section 12's targets: blue and orange completion are both met (0.995
and 0.955 against 0.95), per-racer finish is 0.983 against 0.99 and all-eight
0.865 against 0.90. **`final[10]` is gone** - `final[0]` is a bin of the
sprint's first twenty samples and holds four.

**Fairness is the best this course has recorded**, by a wide margin, and every
measure agrees rather than one carrying the verdict:

    metric                V1.11    V1.15     target
    win-rate ratio        6.618    1.579     <= 2.0-2.5   met
    podium ratio          1.957    1.444                  met
    slot mean-rank SD    0.2997   0.2182
    slot mean-rank span   0.854    0.583
    slot/rank Spearman  -0.0721  -0.0155
    early spread (9%)     2.078    1.535   diluting to 0.583 at the line

Entertainment over the same 200: 4.81 lead changes, 42.4 overtakes, winner lock
0.292, winner's worst rank 2.855, final margin 0.674 mean and 0.533 median.

### The new leading site is orange's own lobe, and it is not the merge

Sixteen of the twenty seven losses are `orange[20]` and `orange_lead[0]`, and
the failure is an **escape** rather than a jam - 0.015 against 0.003.
`tools/sloped_orange_trace.py` reports, per sample and over the whole field
rather than only over the losers, how high a marble rides as a fraction of the
run's own containment:

    orange[]    16    18    20    21    22    23    24    26    28    30    34
    highest   0.91  ....  1.22  1.23  1.91  1.95  1.89  1.54  1.23  1.09  1.00

**The field rides over the top of orange's rail for sixteen consecutive
samples.** Two facts explain it and both are geometry rather than traffic:

* orange's lobe is the **tightest corner on the course** - the turn radius
  falls to 2.74 simulation units at `orange[18]` against leg2's 1.77 at hero
  scale but under half the bank - and at 32 degrees of bank that corner is
  balanced at **20.5 wu/s**. The escapers' own speeds at their highest point
  are 19.3 to 21.7.
* orange carries the course's **smallest rail**. It is a branch, so its whole
  profile is at `layout.BRANCH_SCALE` 0.82 and its containment is 1.1509
  against the hero channel's 1.4035.

So the smallest rail on the course sits on its hardest corner. That is the
same shape as the three windows `GUARD_BOOSTS` already carries on the launch,
leg1 and leg2 - "marbles at 16 to 31 layout units per second going over the top
of the 0.26 rail" - and it is the same repair.

**This is not a regression of the shoulder fix.** V1.14's held-out fifty booked
four of 400 to the orange lobe, which is 1.0%; this run books sixteen of 1600,
which is 1.0%. It is unchanged and was simply behind a larger defect.

## orange's rail, and the plumbing bug the scan found first

`GUARD_BOOSTS` gains a fourth entry, `orange: (0.50, 4, 12, 38, 46)`, measured
over whole races at 32 seeds and 256 racers a row:

    boost                 finish   all8    esc | blue fin | orng fin
    none                   0.981   0.84  0.019 |    1.000 |    0.942
    +0.30 (4,12,38,46)     0.981   0.84  0.016 |    1.000 |    0.942
    +0.50 (4,12,38,46)     0.988   0.91  0.012 |    1.000 |    0.971
    +0.75 (4,12,38,46)     0.988   0.91  0.012 |    1.000 |    0.971
    +0.50 (14,18,36,42)    0.981   0.84  0.016 |    0.995 |    0.957

0.50 and 0.75 are indistinguishable, so the smaller ships, and it is the same
height as the other three windows - which is what a marble a diameter over the
rail needs rather than a coincidence. The **window has to start early**: closed
up to sample 14 it recovers a third of what the wide one does and costs blue a
racer, because the field is already over containment by `orange[16]` and the
lead hands over at 0. Route share is 0.270 in every row.

**The first version of this scan returned four byte-identical rows**, which is
`instrument-bugs-hide-geometry-findings` in its usual shape and this time the
bug was in the course rather than in the tool: `sloped_course` reads
`GUARD_BOOSTS` in the dict comprehension that builds the four `CHAIN` runs, and
the sprint, blue's lobe and orange's lobe are each constructed separately
afterwards. An entry in the table for any of those three **reached nothing at
all**. All three now pass it through, and the scan discriminates.

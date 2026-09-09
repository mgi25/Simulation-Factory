# V1.13 — the fork, and why the guard window cannot fix it

Status: **the brief's stop condition is reached.** The west-guard/opening family
is exhausted and orange completion tops out at 50.7% installed and 58.1% with
the one lead that is not installable, against a target of 95%. This report
names the exact remaining failure mechanism, per §19, and stops there. No seed
is selected, no determinism run has been made, `open_side` is not rendered and
no video exists.

Blue is untouched and re-verified: **99.58% per-racer, 96.67% all-eight** over
seeds 3001–3060, byte-identical to V1.12. The merge was not opened,
`merge_trim` was not rescanned, the start was not touched, and no global Bullet
setting was changed.

Read [`sloped_race_v112_merge.md`](sloped_race_v112_merge.md) for the baseline.
`course.check()` and `contract.check()` report zero findings on both route
configurations throughout.

## The mechanism, in one paragraph

leg3's tail is a 26-degree-banked hairpin that throws its field east at about
1.24 g, and the fork puts a hole in the outer wall exactly there. Orange's
floor is **0.975 simulation units above** leg3's and 1.5 to 2.7 east of it, so
the crossing is a climb over a saddle **1.48 units** above leg3's own resting
line, and the two cradles overlap for only **nine samples** — 4.3 units of
travel, 0.12 seconds at racing speed. Past the overlap the only thing between
the two channels is `ForkRidge`, and the ridge is not a divider a marble is
sorted by. It is a **conveyor**: a triangular sheet whose east edge, in leg3's
own frame, sweeps from across +5.45 at `leg3[96]` to +1.70 at `leg3[102]` and
then stops over open air. A marble that gets onto it rides it to the end and
falls into the gorge between the two diverging channels.

**Touching the ridge is 83 to 89 per cent fatal, and no knob changes that.**

## The measurement that settles it

`tools/sloped_fork_trace.py` now records, for every racer, the **last static
collider it touched** and its pose in the frame of the run it was nearest.
`last_touch` cannot answer this: it records the *run* a marble was nearest
whenever it touched anything, so a marble that climbs onto the ridge at
`leg3[89]` and rides it to `leg3[102]` is booked at 89 and the geometry that
lost it is thirteen samples downstream and unnamed.

Seeds 3201–3212 at `FORK_CREST` 0.12, on V1.12's geometry, 96 racers:

    last static contact of the 58 non-finishers
      fork (the ridge)     41        leg3           6
      final+merge           4        orange_lead    4
      merge                 1        orange         1

    and the same population cut the other way
                              racers   finished
      touched the ridge          36        4      0.111
      never touched it           60       34      0.567

On the configuration this session installs, seeds 3201–3224, 192 racers:

      touched the ridge          35        6      0.171
      never touched it          157       89      0.567

**The installed change works entirely by keeping marbles off the ridge** — 37.5%
of the field touched it before, 18.2% after — and not at all by making the
ridge survivable. The 0.567 for marbles that never touch it is identical in both
and is the rest of the ledger, below.

## Where the ridge's own defect is, measured three ways

### It starts at the parting and ends over a gorge

`ForkRidge` emits a station wherever leg3's east cradle edge and orange's west
cradle edge are more than a hairline apart. On the built runs that is leg3
samples **91 to 102**, and the class docstring's own table says 12 to 16 — it
was written before `ORANGE_MOUTH_ACROSS` moved the mouth a channel half-width
east and was never remeasured.

    step  leg3  o_lead    gap   crest   max flank   leg3 guard   orange guard
       8    90       8  -0.041      -           -        0.12         0.38
       9    91       9   0.282  0.2538       70.5        0.12         0.53
      13    95      13   1.752  1.4035       68.3        0.56         0.97
      14    96      14   2.185  1.4035       63.6        1.00         1.00
      20   102      20   4.210  1.4035       46.3        1.00         1.00

Two things fall out of that table and both were live in V1.12:

* over `leg3[96..102]` the ridge is a floor 2.2 to 4.2 units wide with a
  **full-height guard on each side of it and its downstream end in mid-air**.
  A marble on it cannot re-enter either channel and cannot stop.
* `MAX_FLANK` is documented as "1.8; 61 degrees". 1.8 is the crest height per
  unit of *half* gap, and the steepest slope of `h·sin²(πu)` with `h = 0.9·gap`
  is `atan(0.9π)` = **70.5 degrees**. The number in the docstring is
  `atan(1.8)`, which is the average from foot to crest, not the flank a marble
  meets. The ridge's steepest face is a wall, which is the first failure the
  class was written to avoid.

### It is an up-ramp in the direction of travel

The crest height is tied to a gap that grows fast, so at a fixed lateral
position the surface **climbs along the run**. Centre-envelope world height at
leg3-frame across +2.5:

    leg3[90] 21.286   [91] 21.290   [92] 21.674   [93] 22.084   [94] 22.263

which is a ramp of +26.9 to +42.2 degrees per sample across the whole band the
hairpin delivers marbles into.

`ForkRidge.RISE_SLEW` limits the crest's rise to its own feet's descent, the
same argument and the same invariant as `TrackRun._slewed_bank`. It flattens
the ramp exactly — to two thousandths of a unit a sample — and **it does not
move a single marble**: 0.344 finish to 0.328 over 8 seeds, and byte-identical
results once the guard windows are right, because then nothing reaches the
slewed stations. It is kept in the tree, uninstalled, with its measurement,
the way `merge_trim` is.

### Lengthening it moves the cliff, not the loss

`ridge_window` at 20, 30 and 40, everything else held:

    window   finish   blue fin   orange fin   loss sites
        20    0.500      0.381        0.727   leg3[90] 11, leg3[97] 5
        30    0.500      0.381        0.727   leg3[90] 4, leg3[103] 4, leg3[108] 2
        40    0.500      0.381        0.727   leg3[99] 4, leg3[112] 2, leg3[113] 2

Three identical headlines and three different histograms is the conveyor
finding stated as an experiment: the same marbles are lost, further down.

## The guard window: every setting, and the two that are falsified

One property changed at a time, `FORK_CREST` 0.12 throughout, 8 seeds a row
unless noted. `guard_window` is leg3's east guard in samples past the fork;
`lead_window` is orange's west guard in orange_lead's own samples — a constant
this session had to **create**, because the opening was spelled inline as
`(-1, 0, 4, FORK_WINDOW_ORANGE)` and that constant also sets the mouth's
gradient span and both route-attribution windows.

    guard   lead    mouth  finish  blue fin  orange fin
    12/14   4/14     0.94   0.344     0.314       0.379   V1.12, as shipped
    20/22  20/22     0.94   0.188     0.207       0.438   to the ridge's end, 12 seeds
     8/10   8/10     0.94   0.422     0.372       0.524   the parting
     8/10   8/10     0.65   0.500     0.381       0.727   best measured
     6/10   6/10     0.65   0.359     0.346       0.417   opening ends early
     9/11   9/11     0.65   0.375     0.372       0.381
    10/12  10/12     0.65   0.266     0.192       0.471
     8/14   8/14     0.65   0.219     0.157       0.462   long closing taper
     8/18   8/18     0.65   0.156     0.127       0.333

The 20/22 row is twelve seeds against a twelve-seed baseline of 0.396; every
other row is eight against 0.344. The 24-seed confirmations are in the section
above and below and are the numbers to quote.

**Running either window on to the ridge's last station is falsified**, and it is
the repair the trough finding suggests: 0.396 to 0.188 over 12 seeds. The
guards were not walling a corridor off — they were keeping the field out of a
trap. With them open the release sites simply move downstream and multiply:
`fork` holds the last contact of 61 of 78 non-finishers instead of 41 of 58.

**Lengthening the closing taper is falsified too**, and that kills the
hypothesis this session started from. The guard rising from 12% to full over
two samples is a 45-degree ramp for anything riding the lip, so a gentler close
looks obviously right; measured, it is much worse, because a gentle close means
a **long partial opening** and more of the field gets out into the gorge.

What survives is one sentence: **the opening should shut where the two cradles
stop overlapping.** That is step 8 to 10, two samples earlier than V1.12's, and
it is what ships here.

## What is installed, and what it buys

Seeds 3201–3224, `FORK_CREST` 0.12, 192 racers a row:

    configuration                    finish   all8   escape  stuck | blue%  fin  | orng%  fin
    V1.12  guard 12/14  lead 4/14     0.359   0.00    0.583  0.057 | 0.516 0.343 | 0.479 0.380
    V1.13  guard  8/10  lead 8/10     0.448   0.00    0.479  0.073 | 0.635 0.418 | 0.359 0.507

Orange's completion is up a third, blue's is up a fifth, and the course is
still not a race. `FORK_CREST` remains at its 0.05 default for the reason V1.10
and V1.12 left it there — `routes="blue"` is the default and does not build the
fork, so the constant reaches nothing that ships, and 0.05 is the value the
scans are indexed on. Anyone taking the forked course forward should start at
**0.12**, which is where the route share is balanced.

## The strongest lead this session found, and why it is not installed

`ORANGE_MOUTH_ACROSS` sets how far up leg3's east bank orange's mouth sits, and
therefore both numbers that decide whether the crossing survives:

    mouth   climb to orange's floor   cradles part at   finish   orange fin
     0.94            0.975 sim             step 9        0.448      0.507
     0.75            0.722                 step 10       0.203      0.273
     0.65            0.601                 step 10       0.495      0.581
     0.55            0.488                 step 11       0.312      0.636
     0.45            0.382                 step 11       0.328      0.591

0.65 is the best whole-race result this session measured. **It breaks three
pinned invariants and one of them is a real defect**: the mouth is no longer on
leg3's lip, its west half overhangs leg3's channel again, and
`test_the_orange_seam_has_no_cliff_through_the_crossing_window` measures the
seam dropping **0.641** against a threshold of 0.35 — two thirds of a diameter
of step in the surface the crossing runs over. Six tests fail on it. The gain
also shrinks from 0.727 to 0.581 between 8 seeds and 24, so the eight-seed
number was optimistic. Recorded, not installed.

## Four of my own instruments were wrong

`instrument-bugs-hide-geometry-findings` is now on its eighth session, and this
time one of them had been silently disabling a published knob for three
versions.

1. **`tools/sloped_fork_lab.py`'s `mouth_across` knob had never done
   anything.** `joins.fork_mouth` and `_leg3_lip` spelled the constant as a
   **default argument**, and Python binds a default once, when the `def` runs.
   So setting `joins.ORANGE_MOUTH_ACROSS` afterwards moved nothing, and every
   scan row that set it — listed as a knob since V1.10 — measured the shipped
   0.94. Both signatures read the module attribute at call time now, and
   `test_the_fork_mouth_reads_its_constant_at_call_time` is the regression.
2. **A ray straight down is not a support test.** A first version of the
   release instrument called a marble supported while the surface under its
   centre was within 0.62, and on a plane inclined at `t` the centre stands
   `r / cos t` above the point below it — so 0.62 is a 36-degree ceiling. It
   read a marble climbing leg3's lip, which reaches 70 degrees, as already
   falling, and booked **20 of 58** losses to `leg3[69..80]` where the marbles
   were still running. Contact, not a ray, and the site vanished.
3. **`sloped.splitlab`'s verdict cannot be used as an outcome.** `SplitEntry`'s
   `done()` is true once every marble is finished or has `lost_at` set, and
   `lost_at` is a *containment* reading: a marble flying over the ridge with
   the ridge 1.2 units under it is "over" leg3's channel, because leg3's
   containment is 0.98 and `VERTICAL_SLACK` is 1.0. The race therefore stopped
   at the apex of a jump the marble was going to land from, and 5 of 28 entries
   were booked as failures without the simulation being asked.
   `tools/sloped_fork_sweep.py` owns its verdict now.
4. **`rise` was 0.912 too low in two tools.** `tools/sloped_fork_section.py`
   and the new corridor tool both took the cradle bottom as
   `centre[1] - floor_offset`, and `floor_offset` is negative, so the reference
   was 0.456 the wrong way. `sloped_fork_trace` has always had it right; the
   three agree now.

A fifth is a reporting bug rather than an instrument: `ForkRidge.describe()`
computes each station's gap against `frames[self.index]` — the lateral axis at
the *fork*, not at the station — and re-labels the surviving stations by
`enumerate`. So it reports the ridge starting at step 0 with a gap of 0.630
when it starts at step 9 with a gap of 0.282. It is the same fixed-frame error
V1.12 recorded for the apron, one station along. Named here, not fixed, because
nothing reads it but a human.

## The full loss ledger, on the installed geometry

192 racers, 97 non-finishers, by what last held them up:

    47   the ridge                    thrown east, conveyed to the gorge
    21   the seam at orange_lead[7..10]   last contact leg3's floor (13) or
                                          orange's (8), at orange-frame across
                                          -1.4 to -1.9 - the western edge of
                                          the shared floor, where leg3's floor
                                          ends and the ridge has not begun
    21   final[8] and final[10]       the merge's known residual, all stuck
     5   leg3[99..104]
     3   the orange lobe

So **68 of 97 are the fork** and they are one mechanism seen twice: the marble
is between the two channels and there is no floor that returns it. The 21 at
`final[10]` are V1.12's recorded residual, unchanged and scaling with orange
traffic exactly as that report predicted.

## Blue: the regression, unchanged

Seeds 3001–3060, blue route, against V1.12's own run of the same seeds:

    metric                 V1.12      V1.13     target
    per-racer finish      99.58%     99.58%     >= 99%   met
    all-eight races        96.7%      96.7%     >= 90%   met
    stuck                  0.21%      0.21%     near 0
    escape                 0.21%      0.21%     near 0
    loss sites        blue[0], final[0]  same
    max travel per tick   0.40628    0.40628    budget 0.5

Every figure is identical, which is the right answer: `routes="blue"` does not
build the fork, so none of this session's constants reaches it.

## Fairness and entertainment

**There is no working two-route configuration to measure**, so §14's and §15's
question cannot be answered this session. The blue-route figures are the
regression and are unmoved:

    win-rate ratio 6.006      podium ratio 2.000       slot mean-rank SD 0.4286
    slot mean-rank span 1.383  slot/rank Spearman -0.0721   weak slot 2

    lead changes 4.483    overtakes 33.683    winner lock 0.2115
    final margin 0.5858 mean / 0.5500 median  winner's worst rank 2.017
    collisions 103.65     top speed 64.832

Sixty races is 7.5 expected wins a slot, so the SD and the span are noise at
this sample size; slot 2 is the frozen start's own residual and is the same
weak slot V1.11 and V1.12 both found.

## Tests

`tests/test_sloped_split.py` gains four, all pinning findings rather than
numbers: that `fork_mouth` reads its constant at call time; that both fork
guards shut at or before the sample the two cradles part, with the falsified
alternatives named in the docstring; that the ridge's last station stands over
a gap wider than a marble, so its end is a hole and not a seam; and that
`RISE_SLEW` is off and still flattens the ramp when switched on.

Full suite: **1631 passed, 2 skipped, 1 deselected**, the deselection being the
pre-existing `test_neon_proof` missing-artifact failure V1.12 also recorded.

## What the next session needs

1. **A fork pan, not a guard.** Every knob in the opening family is now
   measured and the ceiling is ~50% orange completion. What the geometry needs
   is a surface that floors the region between the two channels from the
   parting until **both** channels are walled *and* its own downstream edge is
   behind those walls — so that a marble out there is returned to a channel
   rather than carried to a cliff. That is a new station, not a parameter on
   `ForkRidge`, and it is the only thing in this report that could plausibly
   reach 95%.
2. **The 1.48-unit saddle is the real budget.** Orange's floor is 0.975 above
   leg3's and the crossing costs 1.48 units of climb over nine samples. Any
   design that does not shorten that climb or lengthen that window is working
   inside the same margin this session was. `ORANGE_MOUTH_ACROSS` shortens the
   climb and is blocked by the 0.641 seam cliff — a mouth that is *lower* and
   *does not overhang* would need orange's lead re-solved, not just moved.
3. **`final[10]`, still.** 21 of 192 on the forked course, all stuck, all on
   the merge shoulder at `along` +3.26. It is a tenth of the fork's loss and it
   is the only merge defect left.

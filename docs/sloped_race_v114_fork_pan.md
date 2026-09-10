# V1.14 — the fork pan, and what it turns the fork's loss into

Status: **the fork pan is built, installed and measured.** `ForkRidge` is out of
the contact corridor; `sloped.stations.ForkPan` plus its end wall replaces it.
The unsupported exit the whole brief was written against is gone. Firing a
downstream ray from a marble centre over every point of every station
(`tools/sloped_fork_pan_audit.py`), the count that leaves the station without
meeting anything is:

    station                   rings   rays   open    findings
    ridge, window 20             13    143     89   62%    12
    pan,   window 20             13    143      1  0.7%     1
    pan,   window 10 (ships)      3     33      0    0%     0

The middle row is the one that isolates the shape from the length: at the same
thirteen stations as the ridge, the pan's drain and its end wall take 89 open
paths to 1. The installed row then takes the length out too.

Blue-only is untouched and re-verified: no constant this session adds is read
outside the `routes == "both"` branch, and
`test_neither_fork_station_reaches_the_blue_only_course` pins that.

Read [`sloped_race_v113_fork.md`](sloped_race_v113_fork.md) for the baseline
this is measured against. `course.check()` and `contract.check()` report zero
findings on both route configurations throughout.

## The mechanism, in one paragraph

The wedge between the two channels is a **dead end**, and every version of this
junction has tried to make a marble survive being in it. It cannot drain into
orange, because orange's west guard is the only thing holding orange's own field
on a mouth banked 25 degrees toward it - open it and orange empties onto the pan
instead, and its share collapses from 0.312 to 0.031. It cannot drain back into
blue, because leg3's tail throws its field east at 1.24 g and a surface that
returned a marble west would have to be banked past `atan(1.24)` = 51 degrees,
which is a wall. So the requirement is not "floor the wedge" but **"nothing may
be in the wedge"** - a containment job, not a flooring one. Both branch guards
reach full height at step 10, so the station bridges the parting over two
stations, ends there, and puts a wall across its own end. The ridge ran to step
20 and was therefore a **twelve-station dead end**: at window 20 the escapes are
nearly gone and every one of them has become a stuck.

## The headline

Twenty four seeds, 3201-3224, 192 racers a row. The first row reproduces
V1.13's published figures exactly, which is what makes the rest an A/B rather
than a claim.

    configuration            finish   all8    esc    stk | blue%  blue fin | orng%  orng fin
    ridge, crest 0.12         0.448   0.00  0.479  0.073 | 0.635     0.418 | 0.359     0.507
    pan w10, crest 0.05       0.771   0.12  0.036  0.193 | 0.328     0.905 | 0.667     0.711
    pan w10, crest 0.12       0.885   0.33  0.005  0.109 | 0.693     0.985 | 0.302     0.672
    pan w11, crest 0.05       0.703   0.08  0.135  0.162 | 0.333     0.766 | 0.661     0.677

**Escape falls from 0.479 to 0.005** - a factor of ninety six - and that is the
brief's section 1 in one number. Blue's completion goes 0.418 to **0.985** and
orange's 0.507 to **0.672**.

And the loss ledger stops being about the fork. All 22 non-finishers of the
installed row, by the sample they were lost at:

    final[10]      15        merge_lead[11]    1
    final[8]        3        merge_lead[0]     1
    final[7]        1        launch[29]        1

**Not one of the 22 is at the fork.** `final[10]` is V1.12's recorded merge
residual and it is now 68% of the whole ledger.

## The contact trace says the same thing from the other side

Section 10's instrument, `tools/sloped_fork_trace.py`, on the installed
configuration over the same 24 seeds. The line that settles it is **`release
floor`** - the last static geometry that was actually holding each non-finisher
up, which is the reading V1.13 had to invent because `last_touch` books a
marble at the run it was *nearest* rather than at the geometry that lost it:

    by route      orange 58   blue 133   unrouted 1
    by outcome    blue/finished 131   orange/finished 39
                  orange/stuck   19   blue/stuck      2   unrouted/escaped 1

    loss sites    final[10] 15   final[8] 3   final[7] 1
                  merge_lead[11] 1   merge_lead[0] 1   launch[29] 1

    release floor final+merge 16   merge 4
                  blue+merge+merge_lead 1   launch 1

**Neither `fork` nor `fork_end` appears in that ledger at all.** V1.13's
equivalent line was "the last static collider 41 of 58 non-finishers touched was
the ridge", and touching it was 83 to 89 per cent fatal. The pan's end wall - the
backstop that exists precisely so a failure there would be visible and
diagnosable - catches nobody.

Blue finishes 131 of 133; orange 39 of 58, and every one of orange's 19 losses
is booked to the merge with `touched: leg3 -> orange_lead`, meaning they crossed
the fork cleanly and died downstream. The single escape in 192 racers releases
on `leg3[0]` with `launch` as its floor - the start, not the fork.

## Held out: fifty fresh seeds the configuration was never tuned on

Everything above is seeds 3201-3224, which is where the window and crest were
chosen. Seeds **3301-3350**, 400 racers, shipped configuration, nothing
overridden:

    finish 0.905   all-eight 0.40   escape 0.015   stuck 0.080
    blue   share 0.740   completion 0.987
    orange share 0.260   completion 0.673

    final[10]   26     orange lobe        4     orange_lead[12]  1
    final[8]     3     merge_lead[11]     1     leg3[95]         1
    final[7]     2

It is **better** than the seeds it was tuned on - 0.905 against 0.885, all-eight
0.40 against 0.33 - so the window and crest are not fitted to 3201-3224.

Of 38 non-finishers, **two are the fork**: one at `orange_lead[12]` and one at
`leg3[95]`. That is 0.5% of the field, so the fork's own completion is about
**99.5%** and section 11's local acceptance of 95% is met with room. Thirty two
are the merge, which is 8% of the field and 84% of the ledger.

## What the ridge was doing wrong, in three measurements

`tools/sloped_fork_corridor.py` reports the fork as the energy landscape a
marble **centre** rides, which is the reading that settles this. Every previous
account of the junction is written in each channel's own banked profile units,
and at a 26-degree bank that is a different shape from the one gravity sees.

### Orange's mouth is not a pocket

    leg3[87], centre height above leg3's cradle bottom, per across
      leg3's floor   -1.00   0.086
      climbing east  +0.75   0.954
      the saddle     +1.50   1.553      <- 1.467 of climb
      orange         +2.00   1.409      <- a shelf 0.144 deep
      east of it     +3.25   1.914

A marble with enough lateral speed to clear a 1.467-unit saddle crosses a
0.144-deep dimple and climbs the far side. So the crossing does not *end* in
orange; it ends oscillating about the seam, and then the channels part
underneath it. That is the 21 losses V1.13 booked to `orange_lead[7..10]`.

### From the ridge's plateau, blue is impossible and orange is nearly free

    leg3[92], the same reading once the ridge exists
      leg3's floor   -1.00   0.114
      leg3's guard   +1.50   1.924
      the plateau    +2.00   2.080     <- 1.97 above leg3, walled off from it
      orange's lip   +3.00   2.250     <- only 0.17 above the plateau
      orange's floor +6.00   0.710     <- and 1.54 below it

The ridge does neither. It holds the marble on the plateau until its own sheet
ends, which is the conveyor V1.13 named — and the reason no parameter on the
ridge repairs it. The ridge's defect is that **the plateau has no exit**, not
that it is the wrong height.

### The wedge is a fan, not a corridor

The two runs part at leg3[90..91] and are already **46 degrees apart** when they
do, because the 56-degree divergence happens inside the window where the cradles
still overlap. Past the parting, in leg3's own frame, the far foot runs
*backwards*:

    step   gap across leg3   the same foot, along leg3's tangent   headings apart
      10             0.619                                -0.975             58
      14             2.185                                -2.631             72
      20             4.210                                -5.832             87

A sheet spanning that is not a cross-section of anything.

## What the pan is

Three pieces, each from one of those readings.

* **A capped, rate-limited crest.** `SEPARATOR_CAP` 0.33 simulation units — a
  third of a marble — against the ridge's 1.4035, and `RISE_SLEW` installed
  rather than shelved, so no surface a marble runs on rises as it travels.
* **A crest pinned to the west foot** at `SEPARATOR_AT` rather than at the
  middle of the gap, so the divider stops migrating east across the corridor as
  the gap opens.
* **A drain east of the crest** — a straight fall to the east foot rather than a
  raised cosine, whose last third is the level shelf the station exists to
  remove.
* **`ForkPanEnd`**, a transverse wall across the last station, standing on its
  ring exactly. Its own module, so the loss ledger can say whether the backstop
  is where marbles die.

## The two things that turned out to matter, and they are not the shape

### The pan must be short, and 10 is the smallest window that works

Eight seeds a row, everything else held. The two crests are tabulated apart
because they are separate scans and only the windows they each cover were
actually run at that crest.

    crest 0.05   finish    esc    stk | blue%  blue fin | orng%  orng fin
        w10       0.812  0.031  0.156 | 0.391     0.880 | 0.609     0.769
        w11       0.703  0.156  0.141 | 0.375     0.750 | 0.625     0.675
        w12       0.609  0.219  0.172 | 0.359     0.609 | 0.625     0.625
        w14       0.625  0.172  0.203 | 0.359     0.565 | 0.641     0.658

    crest 0.12   finish    esc    stk | blue%  blue fin | orng%  orng fin
        w12       0.562  0.297  0.141 | 0.625     0.600 | 0.328     0.571
        w14       0.438  0.438  0.125 | 0.688     0.409 | 0.312     0.500
        w20       0.453  0.062  0.484 | 0.688     0.409 | 0.312     0.550

The trend is one mechanism read twice: **a longer pan is a bigger dead end.**
The clearest single row is `w20` at crest 0.12, where the escapes are nearly
gone (0.062 against the ridge's 0.516 on the same eight seeds) and **every one
of them has become a stuck** (0.484 against 0.062) — the pan holds the marble
up and then has nowhere to put it, so the failure changes character without
changing size. Shortening the pan is what removes the failure rather than
relocating it, and at 10 there is no dead end left to be in.

Window 9 is refused by the geometry rather than by taste: the audit finds **9 of
11** downstream rays leaving it unobstructed, because both guards are still only
at 0.53 there. At 10 they are both at 1.00, which is what §1's "its downstream
edge must lie behind established branch walls" actually requires.

### The pan cannot drain into orange, and that is falsified rather than assumed

The pan drains east, so opening orange's west guard over its length is the
obvious completion of it. Measured over 8 seeds at crest 0.12:

    lead window   finish   blue%  blue fin | orng%  orng fin
         8/10      0.453   0.688     0.409 | 0.312     0.550
        14/16      0.266   0.953     0.262 | 0.047     0.333
        18/20      0.297   0.969     0.306 | 0.031     0.000

Orange's share collapses from 0.312 to **0.031**. The mechanism is V1.13's own
guard finding seen from the other side: orange's west guard is not walling a
corridor off, it is the only thing holding orange's field on a mouth banked 25
degrees toward it. With it open, **orange empties onto the pan rather than the
pan filling orange.**

And the wedge cannot drain back into blue either: leg3's tail throws its field
east at 1.24 g, so a surface east of leg3's channel would have to be banked
steeper than `atan(1.24)` = **51 degrees** to return a marble west, which is a
wall and not a floor.

So the requirement is not "floor the wedge". It is **"nothing may be in the
wedge"**, and that is a containment job, which is why the answer is a two-station
bridge with a wall on it rather than a twelve-station sheet.

## Four of my own instruments were wrong

`instrument-bugs-hide-geometry-findings` is now on its ninth session.

1. **`tools/sloped_fork_sweep.py --pack 1` is blind to the fork.** At 30 to 42
   wu/s, 28 of 28 single marbles finish and **not one takes orange**; the five
   failures it reports at 50 wu/s are downstream overspeed losses, and the same
   16-of-21 comes back byte-identical across `max_flank` 1.8 and 0.4,
   `ridge_window` 20 and 12, and `ridge_slew` on and off — three geometry
   changes the tool cannot see. The fork's failure is traffic-driven. Packs and
   whole races only.
2. **A support test placed a radius above the surface is arithmetic, not
   geometry.** The first version of `tools/sloped_fork_pan_audit.py` reported
   every drop as exactly 0.500 and every station supported, because it probed
   from a marble centre placed a radius above a point that was already on the
   surface — it can only fail if a ring vertex is missing from the collider. The
   grid is the strip's interior and a fan outboard of each foot now.
3. **The audit labelled the ridge's rings 0..11 when the ridge builds steps
   9..20**, and then reported every ring standing ~5.0 units from "its" cradle
   edge — the distance between two stations eleven samples apart, not a seam. It
   also fired each downstream ray along the *wrong sample's* forward tangent,
   which understated the ridge's own defect: with the steps recovered from its
   emission rule the ridge's open-ray count is **89 of 143, not 60**, and its
   findings 12 rather than 34. Every ridge number in this report is the
   corrected one.
4. **`ForkPan`'s own docstring put its steepest flank at 40.8 degrees**, from the
   nominal `SEPARATOR_AT` of 0.60. At the two stations that ship, the offset is
   clamped to a third of the chord, and the real faces are **56.4 and 50.1**.
   The number is corrected in the class and the test measures the effective
   offset.

A fifth is inherited and now fixed: `ForkRidge.describe()` measures every gap on
the lateral axis at the *fork* rather than at the station and re-labels the
survivors by `enumerate`, so it reports the ridge starting at step 0 with a gap
of 0.630 when it starts at step 9 with 0.282. `ForkPan.describe()` reports
`first_step` and `last_step` from the real frames.

And one defect of my own making, caught by the scan dying rather than by
thinking: `ForkPan.rings()` inherited `ForkRidge`'s "fewer than two stations"
refusal, but the pan inserts a nose ring, so one station is a valid two-ring
strip. A window of 9 emits exactly one station, and the window scan crashed on
that row instead of measuring it.

## Blue: unmoved, and structurally so

No constant this session adds or changes is read outside `sloped.course`'s
`routes == "both"` branch, so the blue-only course that ships cannot see any of
it. `test_neither_fork_station_reaches_the_blue_only_course` asserts that for
both stations by building the course and checking `fork`, `fork_end` and
`orange_lead` are all absent, and `course.check()` and `contract.check()` report
zero findings on the blue-only build.

Measured anyway, because the structural argument is the kind that is true until
it is not. Seeds 3001-3060, 480 racers, against V1.13's own run of the same
seeds:

    metric                 V1.13      V1.14     target
    per-racer finish      99.58%     99.6%      >= 99%   met
    all-eight races        96.7%     96.7%      >= 90%   met
    stuck                  0.21%      0.2%      near 0
    escape                 0.21%      0.2%      near 0
    loss sites        blue[0], final[0]  same
    max travel per tick   0.40628    0.40628    budget 0.5
    win-rate ratio          6.006      6.006
    slot/rank Spearman    -0.0721    -0.0721
    weak slot                   2          2

Every figure is identical, including the fairness shapes and the travel budget,
which is the right answer rather than a lucky one.

## Tests

`tests/test_sloped_split.py` gains seven, all pinning findings rather than
numbers:

* that the pan's end wall stands on its last ring **exactly** - a wall an
  epsilon downstream of the ring is a slot a marble fits through;
* that every station's feet are the two runs' own cradle edges to the last
  decimal, since both come from `TrackRun.surface_point`, the expression the
  collider's vertices come from;
* that `RISE_SLEW` is installed and the crest's world height never rises along
  the run;
* that the crest stays under a marble diameter and its **effective** steepest
  face - measured on `crest_u * span`, not on the nominal `SEPARATOR_AT` -
  stays under the ridge's own 70.5 degrees;
* that the crest does not migrate east across the corridor as the gap opens;
* that opening orange's west guard over the pan is falsified, with the three
  measured rows in the docstring;
* and that neither fork station reaches the blue-only course.

The two tests that are *about the ridge* now ask for it explicitly through a
`_ridge_course()` helper, because the ridge is no longer what the default
builds. Both still pass unchanged, which is the point of keeping it.

Full suite: **1638 passed, 1 failed, 2 skipped**. The failure is
`tests/test_neon_proof.py::test_a_missing_godot_is_reported_rather_than_raised`,
which fails on a missing `output/neon_v11/neon_7.json` replay artifact before it
reaches its own assertion - the same pre-existing missing-artifact failure V1.12
and V1.13 both recorded, on a different branch's work and untouched by this
session.

## What the next session needs

1. **`final[10]`, and it is now the whole problem.** 26 of 38 losses on the
   held-out seeds and 15 of 22 on the tuning seeds - about two thirds of the
   ledger either way - all on the merge shoulder, and it is **orange's** merge:
   blue completes 0.987 and orange 0.673, so essentially the entire residual is
   orange arriving at the junction. V1.12 predicted this would scale with orange
   traffic and it has: orange's share is lower than V1.13's (0.26 against 0.36)
   but its completion is a third higher, so far more orange actually reaches the
   merge than ever has. Section 12 of the V1.14 brief is explicit that this is a
   separate local shoulder defect and that the two investigations must not be
   mixed, which is why this report stops here rather than opening it.
2. **The ring sampling.** `ForkPan.FLANK_POINTS` samples eleven points uniformly
   in `u`, and the crest sits at `u = 1/3`, so no vertex lands on it: the built
   polyline peaks at `u = 0.3` with 0.976 of the nominal crest. Every number
   above was measured on that sampling. A ring that puts `FLANK_POINTS` on the
   flank and `FLANK_POINTS` on the drain is what it should do, and it is a
   geometry change that has not been run.
3. **`MAX_FLANK_DEG` is off and unscanned.** The installed west flank is 50 to
   56 degrees, which is a face rather than a wall but is steeper than a marble
   runs on. The knob bounds it against the effective offset; nothing has asked
   whether a gentler one is better.
4. **The benchmark ladder stops at its first rung on purpose.** Section 13's
   50-seed rung is done and held out (above); 200 and 600 are gated on the
   result being production-capable, and 0.905 finish with 0.40 all-eight is not
   against section 14's 99% and 90%. The gap is not the fork, which loses 2 of
   400 - it is `final[10]`. Fixing the merge and then climbing the ladder costs
   one long run instead of two.
5. **Nothing downstream of the benchmark has been done**, per the brief's own
   ordering: no seed selection, no determinism run, no replay export,
   `open_side` is not rendered and no video exists.

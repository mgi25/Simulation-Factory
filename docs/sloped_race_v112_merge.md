# V1.12 — the merge rebuilt from the endpoint frames

Status: **the merge is rebuilt and blue is measurably better than V1.11 —
99.58% per-racer, 96.7% all-eight, and `blue[100]` gone from the loss sites
entirely. Orange is transformed from unusable to partly working, and it is not
production-viable: it is blocked at the *fork*, not at the merge.** This report
stops at that finding, per the brief's stop condition. No seed is selected, no
determinism run has been made, no video has been rendered.

Read [`sloped_race_v111_leg2.md`](sloped_race_v111_leg2.md) for the baseline and
[`sloped_race_v110_fork.md`](sloped_race_v110_fork.md) for the fork work this
inherits. `course.check()` and `contract.check()` report zero findings on both
route configurations throughout.

## The one instrument that made this session possible

`sloped.junction` fires a vertical ray at every point of a *running line* and
reports which module owns the surface it finds.
`tools/sloped_junction_audit.py` walks the blue tail, the orange tail, the apron
and the sprint's head at **five lateral fractions**, because V1.11's leg2
finding is that a downhill centreline is not evidence.

That found four defects in one pass, and **none of them was the merge apron's
design speed**, which is what the brief expected and what
`MergeCatch`'s own docstring had claimed for three versions:

| where | what | recorded as |
|---|---|---|
| `blue[91..98]` | the east edge climbs **0.3013** while the centre falls | `blue[100]`, 8 of V1.11's 24 |
| `blue[113]` | the apron's height field steps **+26.0%** up over blue's west edge | `final[0]` |
| apron front | no front wall and **no floor beyond it** | `final[9..11]`, V1.10's immovable site |
| `orange[87..112]` | three roll reversals, climbs to **0.9223** | orange unusable |

And a coverage correction to a published number:
`tools/sloped_pocket_survey.py` walks `CHAIN + ("final",)` and **one sign** of
each lateral fraction. So neither branch lobe was ever surveyed, and leg1's own
basin is **0.5719** on the negative side against the 0.0309 V1.11 quotes for
the positive one. leg1 is frozen and was not touched; the number is recorded
because the survey it came from is still the tool anyone will reach for.

## What was rebuilt

### Blue's half of the merge is a channel now

`docs/sloped_race_v1_junction_finding.md` proved no channel joins the two
branches, and that is still true of **orange**. It was never true of blue: blue
arrives 7.5 degrees off the sprint's own heading, 0.26 simulation units off its
centreline and 1.9 behind its entry. `sloped.joins.merge_lead_path` joins those
two poses with 1.16 layout units of the same moulding as the runs either side.

What has to be continuous is the **contact point**, not the centreline: the two
runs' profile scales differ, so the lead's centreline starts
`FLOOR_Y * (0.82 - 1.0)` = 0.0468 layout units up blue's own frame. Measured on
the built runs, blue's exit contact is at apron-frame `(-1.899, -0.257, -0.303)`
and the lead's entry at `(-1.896, -0.257, -0.302)`.

Its width opens at **1.00** and eases to `final[0]`'s own 1.140, and that is the
smallest width that is wide enough. What matters is the lead's surface height at
blue's cradle *edge*, and a scale-1.0 cradle is deeper than a scale-0.82 one:

    width factor   lead's height at blue's edge   against blue's 0.1729
      0.95                     0.18542            +0.0125 layout  an uphill lip
      1.00                     0.16666            -0.0062          0.011 below
      1.140                    0.12702            -0.0459          0.081 below

1.140 is safe in height and wrong in *width*: the lead is then 1.880 of half
width against blue's 1.474, and the 0.406 difference has no floor under it on
the upstream side of the seam. At 1.00 the unsupported strip is 0.175 and the
0.06 bump the walk read at `merge_lead[1..2]` goes.

### The apron is a shoulder outside the channel, not a pan across it

It used to be a `height_field` over a rectangle with the cradle formula laid
across it, so it owned the floor wherever it came out higher than the channel's.
Along blue's west running edge it did. **Two corrections had already been made
to that height field and both were to its gradient** — first the chord to the
sprint, then blue's own fall — and neither could fix what was wrong, because
three things were:

* the apron's cradle was centred on the **sprint's** centreline while blue's is
  0.26 to 0.52 off it and yawed 7.5 degrees, so the two valleys did not line up;
* its cradle-to-shoulder changeover was at `CHANNEL_HALF * scale`, 1.649 units,
  while the sprint's own cradle edge is at 1.880 — because `widths[0]` flares it
  to 1.140, and the apron did not read `widths` at all. The shoulder's rise
  therefore began **0.23 units inside the running surface**, standing 0.083
  above the channel's floor at a lateral fraction of 0.85;
* past blue's mouth it extrapolated blue's gradient as a straight line while
  blue's channel was still turning.

`sloped.solids.flank_field` lays the shoulder between the channel's own clear
edge — read off the run through `widths` — and a rim that eases in to the
channel by the front. The whole failure class goes with the rectangle.

### The front is closed, and that is what `final[9..11]` was

The apron's floor spanned `across` ±4.035 out to `along` +2.982 and then simply
**stopped**: four walls, no front wall, no floor beyond. Everything riding the
shoulder outside the channel ran off the lip, and +2.982 is the sprint's sample
9.15. That is the site V1.10 found losing 14 of 128 in **six of seven** fork
configurations and could not move with any fork knob — because it was not a
fork defect.

`FRONT` is now `final[14]`, where `MERGE_GUARD_WINDOW` puts the rails back to
full height, so the apron's wall and the rail hand over at one station rather
than five samples apart.

### Two roll limits, and orange's is the whole run

`BANK_SLEWS` gains `"blue": (84, 117, 1.0)` and `"orange": (0, 117, 1.0)`.

    run     fraction  0.00     0.40     0.55     0.70     0.85     0.95
    blue    authored 0.0000   0.0442   0.1181   0.2083   0.3013   0.3635
            limited  0.0000   0.0000   0.0000   0.0000   0.0000   0.0000
    orange  authored 0.0000   0.2910   0.4602   0.6308   0.8035   0.9223
            limited  0.0000   0.0000   0.0000   0.0000   0.0000   0.0002

The basin survey over the whole built course afterwards, for the record - the
three that remain are all on runs this brief froze:

    launch 0.0941   leg1 0.5719   leg2 0.0000   leg3 0.2586
    blue_lead 0.3834   blue 0.0000   orange_lead 0.0000   orange 0.0002
    merge_lead 0.0000   final 0.0068

`blue_lead`'s 0.3834 at sample 5 is the largest unaddressed one on either
route's own geometry and it is 11.59 wu/s of escape speed. It is a join this
session did not touch.

**Orange's window is the whole run, and that is the opposite of the leg2
result.** Over samples 84 to 118 the authored roll costs 1.5310 layout units of
drop and has 0.3871 — a ratio of **3.96** — so a rate cap started there lags and
never catches up: it leaves 0.1864 at the edge. Over the whole run the ratio is
**0.82**, because orange descends 3.30 units in total. Started at sample 0 the
cap never lets the roll wind *on* faster than the drop pays for either, so it
never reaches the excursions it would then have to pay back, and the total
variation it has to fund is its own rather than the authored one. Windows from
20, 40, 50, 60 and 70 all give 0.0274; from 0 it gives 0.0002.

Both preserve the bank extreme exactly — 24.0000 for blue at sample 54, 32.0000
for orange — so `contract.check()` stays at zero. Both leave nine or so samples
banked the **wrong way** for their corner, and that is measured to cost nothing:
`ride_height` is 0.2050 layout units before and after at 41 wu/s and 0.3608 at
50, against a containment of 0.6560, with `runs_out` zero on every sample of
either run at either speed. What they buy is the *rate*: blue's worst falls
13.65 degrees per layout unit to 6.86, orange's **47.44 to 16.11** against the
continuity audit's threshold of 12.0.

## Blue: the regression test, and it is better than V1.11

    metric                V1.9 (600)  V1.11 (600)  V1.12 (60)   brief target
    per-racer finish         98.83%      99.50%      99.58%      >= 99%   met
    all-eight races          91.0%       96.0%       96.7%       >= 90%   met
    stuck                     0.92%       0.15%       0.21%      near 0
    escape                    0.25%       0.35%       0.21%      near 0

Seeds 3001–3060, fresh, blue route. **`blue[100]` is gone from the loss sites
entirely**, and so is `final[0]` as a site of any size: of 480 racers, the two
non-finishers are one at `blue[0]` and one at `final[0]`.

Sixty seeds against V1.11's six hundred, so these are not equal-weight
comparisons and the finish rates are within each other's noise. What is not
noise is the *shape*: 15 of V1.11's 24 non-finishers were at `blue[100]` and
`final[0]` together, and here there is one of each in a fifth of the sample.

Targeted, which is the comparison the brief asks for in §4:

    blue[88..112] -> merge -> final, 5 entries x 7 offsets x 8 speeds
      merge rebuilt only        278 of 280  (two stopped at blue[90], blue[92])
      and blue's roll limited   280 of 280  at 4, 6, 8, 12, 20, 30, 40, 50 wu/s

The two that stopped were injected at `blue[96]` at 4 to 12 wu/s and pushed
*backwards* into blue's own basin, which is the defect the roll limit removes
and not the merge's.

And the junction audit reports **zero** climbs, holes, ledges and tight
clearances over `blue[86]` through `final[21]` on all five lateral lines:

    blue-only walk              holes   climbs   ledges   tight
      V1.11 geometry                0       18        1       1
      V1.12                         0        0        0       0

with the worst climb before being the +26.0% at `blue[113]`'s west edge, owned
by the apron.

On the **forked** course two climbs remain on the blue walk and three on the
orange one, and both are named rather than fixed:

    worst on the blue walk     +68.9% at final[5] E-edge, owner orange
    worst on the orange walk  +100.2% at orange[111] E-edge, owner merge

The first is orange's untrimmed mouth standing over the sprint's east running
edge, which is the shelf `merge_trim` was written for and is falsified against.
The second is the apron's shoulder still touching orange's channel at one
sample of one edge, after the rim learned to yield to orange over the rest of
it. Neither is chased further this session, because the forked course loses 177
of its 244 marbles at the fork and 66 at the merge: a single-sample edge defect
at the junction cannot move that headline.

## Orange: transformed, and blocked somewhere else

Orange's tail through the rebuilt merge, eight-marble traffic:

    entered at orange[88]           in traffic     launched alone
      V1.11 geometry                  0 of 28         0 of 28
      east wall yielding to orange    13 of 28        13 of 28
      and the roll limited            22 of 28        20 of 28

**But the full forked race is 49.2% finish and 1.7% all-eight, and its losses
are at the fork.** Seeds 3001–3060, `FORK_CREST` at its open 0.05:

    site               losses of 480
    orange_lead[0]         94
    final[0]               61
    leg3[80]               54
    orange[20]             11
    orange[0]               7
    orange_lead[20]         6
    merge_lead[0]           5
    leg3[100]               5

177 of the 244 are at the fork — `leg3[80]`, `orange_lead[0..20]`,
`orange[0..20]` — and 66 at the merge. Route usage is **81.2% orange, 18.8%
blue**, outside the brief's 25–75% band, and blue's own completion collapses to
34.4% because the 90 marbles that stay on it are the ones the fork has already
knocked about.

V1.10 measured 0.500 finish and 0.445 escape at this crest. This session
measures 0.492 and 0.371. **The merge rebuild has not moved the forked course's
headline, because the forked course's headline is set by the fork.** That is
consistent rather than disappointing: the merge sites that V1.10 could not move
with any fork knob are the ones that moved, and the fork sites are the ones the
brief froze this session out of.

## The crest scan, which settles where orange is blocked

`FORK_CREST` is the route dial V1.10 established. Scanned again on the rebuilt
merge, 24 seeds a row, seeds 3201-3224
(`docs/validation/sloped_race_v1/v112/fork_lab_crest_v112.json`):

    crest   finish   all8    esc    stk |  blue%  blue fin |  orng%  orng fin
     0.05    0.552   0.00  0.333  0.115 |  0.188     0.361 |  0.807     0.600
     0.09    0.365   0.00  0.500  0.135 |  0.286     0.309 |  0.708     0.390
     0.12    0.359   0.00  0.583  0.057 |  0.516     0.343 |  0.479     0.380
     0.15    0.417   0.00  0.573  0.010 |  0.766     0.483 |  0.229     0.204
     0.19    0.729   0.04  0.271  0.000 |  0.922     0.785 |  0.073     0.071

**Crest 0.12 balances the routes — 51.6% blue, 47.9% orange, inside the brief's
25-75% band — and the course finishes 35.9%.** So there is now a setting that
gives both routes real traffic, which V1.10 could not find; and it is still not
a race.

Where it loses them is the whole answer. At crest 0.12, of 123 non-finishers:

    leg3[92]  10    orange_lead[9]   8    leg3[91]  6    leg3[102]  4
    final[10] 10    orange_lead[8]   7    orange_lead[11] 5    leg3[89]  4
    leg3[93]   8    orange_lead[10]  7

**Nine of the top ten sites are the fork.** `leg3[88..103]` and
`orange_lead[8..17]` together are about half the field; `final[10]` is 10 of 123.

And `final[10]` is the merge's own residual, scaling with orange traffic exactly
as it should: 17 at crest 0.05 and 0.09, 10 at 0.12, and absent from the top ten
at 0.15 and 0.19. It is the shoulder at the apron's front, `along` +3.26,
where a marble that has crossed at 5 to 15 wu/s runs out of momentum. That is
the one merge defect this rebuild has left, and it is a tenth of what the fork
takes.

Against V1.10's own scan of the same dial, before any of this:

    crest        finish            escape           orange completion
     0.05    0.500 -> 0.552    0.445 -> 0.333     0.547 -> 0.600
    ~0.12    0.349 -> 0.359    0.620 -> 0.583     0.254 -> 0.380
    ~0.15    0.641 -> 0.417    0.339 -> 0.573     0.158 -> 0.204
    ~0.19    0.885 -> 0.729    0.099 -> 0.271     0.000 -> 0.071

Orange's completion is better at every comparable crest and by half again at
the balanced one. **The escape columns are not comparable across versions and
should not be read as one**: this session changed the containment verdict in two
directions at once - the apron exemption removes marbles that were being booked
as escapes while standing on the shoulder, and the third test adds marbles that
were falling through and being booked as nothing at all. The finish columns are
comparable, because a finish is a finish. The rows are also not the same crests
and not the same seeds; V1.10 used 16 seeds from 1 and this used 24 from 3201.

## Fairness and entertainment: unchanged, which is the right answer

The start was not touched and neither was the main course, so the interesting
result here is that nothing moved. Blue route, seeds 3001-3060, against V1.11's
six hundred:

    metric                    V1.9     V1.11    V1.12 (60)   target
    win-rate ratio            5.04     6.618      6.006
    podium ratio              2.09     1.957      2.000      <= 2.5   met
    slot mean-rank SD         0.354    0.2997     0.4286
    slot mean-rank span       1.161    0.854      1.383
    slot/rank Spearman          -      -0.0145   -0.0721

    slot   win%   podium%   finish%   mean finish rank
       0   11.67    33.33    100.0         4.700
       1   20.00    40.00    100.0         4.083
       2    3.33    23.33    100.0         5.417
       3   10.00    31.67     98.3         4.729
       4   13.33    45.00     98.3         4.034
       5    8.33    35.00    100.0         4.450
       6   16.67    46.67    100.0         4.200
       7   16.67    45.00    100.0         4.267

**Sixty races is 7.5 expected wins a slot, so the SD and the span are noise at
this sample size** and their apparent worsening against V1.11's 600 should not
be read as a change. The one thing that is robust is the same as V1.11's: slot
2 is the weak slot on both, and it is the frozen start's own residual.

    metric                V1.3    V1.11     V1.12 (60)
    lead changes           ~4     3.995      4.483
    overtakes             ~39    34.927     33.683
    winner lock          ~0.13   0.2127     0.2115
    final margin (mean)  ~0.43s  0.5293     0.5858
    final margin (median)   -    0.4667     0.5500
    mean collisions         -    101.6     103.65
    winner's worst rank     -    2.027      2.017
    top speed               -   65.437     64.832

Every one of those is within noise of V1.11. **The merge rebuild changed the
course's reliability and not its character**, which is what a junction repair
should do, and the ~0.21 winner lock the brief asked to watch is unmoved.

The forked course's own figures are recorded and are not a race: win ratio
11.976, mean final margin 1.0089 s, mean top speed **108.06** - which is 37% of
the field free-falling rather than anything on the track - and one eligible seed
out of sixty.

    route    entries   share   finish   escape   win     median time
    blue          90   0.188    0.344    0.656   0.067      22.47 s
    orange       390   0.812    0.526    0.305   0.136      21.97 s

Orange is **52.6%** against the brief's 95%, and blue is 34.4% against its own
99.6% when the fork is not built. Neither route works when both are on offer at
this crest, and the reason is upstream of everything this session rebuilt.

## Three of my own instruments were wrong, and one mechanism is falsified

Recorded because each one changed a conclusion, and because
`instrument-bugs-hide-geometry-findings` is now on its seventh session.

1. **`sloped.splitlab`'s verdict had two tests and needed three**, which is
   exactly the bug V1.10 fixed in `sloped.race` and left in place here. Of 28
   marbles on an orange tail sweep, eleven came to rest **9.3 units below** the
   apron and `verdict()` reported "running". `FLOOR_SLACK` is the third test.
2. **The merge's shoulder is floor, and both verdicts were calling it an
   escape.** Another eleven of the same 28 were booked as having left the course
   while standing on the shoulder — 0.50 above it, 2.4 to 3.7 across, touching
   `merge` and nothing else, at 5 to 15 wu/s, which is the station doing exactly
   what it is for. `MergeCatch.holds` answers it now and both `sloped.race` and
   `sloped.splitlab` excuse the run-relative tests where it is true. **Every
   forked measurement this project has published has this in it**, V1.10's
   escape rates included.
3. **I measured the shoulder in the apron's own frame and quoted the wrong
   magnitude.** The apron's forward axis descends at 13.7 degrees, so a
   frame-relative rise that grows downstream is not the same size as a world
   climb and can be the opposite sign. The reading that motivated normalising
   the funnel by a fixed span was 0.3857 in the apron's frame; **in world
   height the same surface climbs 0.2460**, and the fixed-span version climbs
   0.0571. So the repair is real and larger than a fifth of what I first
   claimed for it - the local-rim normalisation turned everything outside the
   rim into a plateau at full funnel height, and the plateau's inner edge moved
   inward as the rim narrowed. The number was wrong; the defect was not.
   `test_the_shoulder_descends_in_world_height_on_every_line` is checked to
   discriminate: 0.2460 before against a 0.10 threshold.

   Two smaller ones are recorded in `sloped.junction`: a ray fired at a run's
   first or last ring meets it in a single vertex, so a miss is now re-probed
   on a ring of half a radius before it is called a hole; and a walk that
   stepped backwards between two runs' contact points read the 0.009 it had
   already descended as a +24.7% climb.

And **`sloped.joins.merge_trim` is falsified.** Orange's mouth stands 0.30 to
0.50 units over the sprint's east running edge at `final[5..7]` and then stops —
a shelf a blue marble climbs at +68.9% and a cliff an orange marble drops off at
−151.6%, in three samples. `merge_trim` solves the fold that removes it, by
exactly the argument `fork_trim` is built on. Installed, it made orange **worse**:
22 of 28 to 19 in traffic, and 17 of 28 to **2** launched alone. The mechanism
does not transfer, and the reason is what is underneath: at the fork the folded
part has leg3's own bank there at the same height, and at the merge the sprint's
floor is 0.34 to 0.9 *below*, so the fold does not hand a marble over — it drops
it. Kept in the tree with the measurement, for the reason `sloped.basin` is kept.

## The travel-per-tick warning, explained

V1.11 flagged `max travel per tick` at 0.744 against a budget of 0.5 and asked
for it to be separated. Measured on seeds 3001–3060 of the current geometry:

    reading                        budget   V1.11 (600)   V1.12 (60)
    max travel per tick               0.5      0.744         0.40628
    max travel falling                  -          -         0.41028
    worst track penetration             -     -0.38005      -0.36017
    worst actuator overlap              -     -1.15252      -1.03766
    worst marble-on-marble              -     -0.23359      -0.22759

**It does not reproduce, and the arithmetic says why it never was about the
geometry.** `max_travel_per_tick` is `speed * dt` with `dt` = 1/240, so 0.40628
implies 97.5 wu/s and 0.744 implies **178.6**. The mean top speed over these
sixty races is 64.832 and the fastest *contained* reading
`marble3d.simulation`'s own docstring records is 63 to 67 wu/s — 0.288 of a
diameter. 178.6 wu/s needs a 65-unit fall, which is more than the course is
tall.

So the reading is set by a marble in free flight, and the split
`marble3d.simulation` already carries excludes only marbles outside the
machine's **bounding box** — a marble falling thirty units *through* the middle
of the course is still inside it. The statistic therefore scales with how many
marbles leave the channel and with how many races are run, not with the channel.
V1.11 had 24 non-finishers in 4800 racers; this has 2 in 480.

**Measured, not argued.** Twenty-four further seeds (3101-3124) with per-race
output, in which **every** race finished all eight and nothing left the channel:

    max travel per tick       0.27311 worst, 0.26697 mean   (budget 0.5)
    max travel falling        0.00000 in all 24 races
    top speed                 65.55 worst, 64.07 mean

0.27311 is 65.55 / 240 exactly, which is the field's own terminal speed on the
steepest section and the 0.288 `marble3d.simulation` records. So on a race where
nothing is lost the reading is 55% of budget with no spread to speak of, and the
0.40628 over sixty seeds is the two non-finishers in that sample. There is no
course location, no contact spike and no actuator interaction in it.

**The recommendation is a third bucket, not a timestep change.** `sloped.race`
knows which run each marble is located on and whether it is contained;
`marble3d.simulation` does not, and its existing split excludes only marbles
outside the bounding box. A `max_travel_contained` taken over marbles inside
their own channel would make the budget mean what it says without needing a
loss-free sample to read it on.

## The render gap is larger than V1.10 priced, and it is not only `open_side`

V1.10 recorded that `v2_track.gd` implements `guard_boost` and nothing for
`open_side`. Measured, the gap is bigger: `course_layout.gd` carries the **seven
authored runs and nothing else**, so

    undrawn physics geometry              layout units
      blue_lead                              7.88
      orange_lead                           12.46
      merge_lead                             1.16   (new this session)
      merge apron                    4.91 x 4.60, plus its roof and four walls

and the drawn lobes are built from their full control polygons while the
physical ones drop one control (blue) and two (orange). The good news is the
direction of the error: the **physical** curve is within 0.173 (blue) and 0.206
(orange) layout units of the drawn one everywhere it exists, so a marble never
appears outside the drawn channel on either lobe. The drawn mouth stubs are
6.73 and 12.75 units of channel the marbles never touch, and the leads and the
apron are geometry the marbles do touch and the render does not have.

On the shipped blue route that is 9.04 layout units of channel plus the apron —
4.6% of a 196-unit route — and V1.9 rendered and inspected a video over it. It
is recorded rather than fixed: the brief's §9 gates this work on orange becoming
production-viable, and orange has not.

## Tests

`tests/test_sloped_split.py` gains three tests that pin the rebuild's
properties rather than its numbers: that the shoulder's inner edge **is** the
channel's own clear edge at every station and its surface there is the channel's
surface, so a step across the seam is impossible rather than small; that the
shoulder reads the width flare the old apron ignored; and that the rim eases in
to the channel by the front while the sprint's rails are at full height from
that station on. The exemption `test_the_aprons_upstream_edge_is_answered_by_blue`
used to bound is gone — no merge probe needs one now, because the shoulder is
only ever outside the channel.

`tests/test_sloped_race.py`'s join-radius test now measures the drift a short
radius costs rather than the radius alone, with a second test pinning that the
merge lead's drift stays below the ones the contract-pinned runs already carry.
A bare radius comparison fails **six of the seven authored runs**, leg2 included
at less than half its own limit, and they ship:

    run           bank_max   worst r   required   drift   drift / half width
    merge_lead         0.0     2.686      7.814  0.0131                0.012
    blue_lead         30.0     4.383      2.837  0.0000                0.000
    orange_lead       30.0    13.089      2.837  0.0000                0.000
    launch            18.0     2.918      4.363  0.2036                0.190
    leg2              22.0     1.767      3.793  3.1671                2.955
    blue              24.0     1.618      3.534  5.8369                6.643

Full suite: **1587 passed, 2 skipped, 0 failed**, excluding the pre-existing
`test_neon_proof` missing-artifact failure. `tests/test_sloped_bank_slew.py`'s
`..._on_leg2_only` is renamed and strengthened: it skipped every name in
`BANK_SLEWS` and so kept passing when the table grew to three without checking
that any of them was installed - and blue and orange are built outside the
`CHAIN` comprehension that passes `bank_slew`, so either could have been named
in the table and never wired.

## What the next session needs, in the order the evidence puts it

1. **The fork, not the merge.** `orange_lead[0]` at 94 of 480 and `leg3[80]` at
   54 are where orange is lost now. V1.10's guards grid says orange's own west
   guard reaching full height sooner is the one knob that did real work
   (`orange_window` 14 to 10: escape 0.445 to 0.328) and that it "has not been
   exhausted". That is the next lever and this session did not touch it.
2. **`FORK_CREST` = 0.12 is the balanced setting**, 51.6/47.9, and it is left
   at 0.05 for the same reason V1.10 left it there: `routes="blue"` is the
   default and does not build the fork, so the constant reaches nothing that
   ships, and 0.05 is the value the scans are indexed on. Anyone taking the
   forked course forward should start from 0.12.
3. **`final[10]`, the last merge defect**, 10 of 123 at the balanced crest and
   17 of 192 at the open one - a marble that has crossed the shoulder at 5 to
   15 wu/s running out of momentum at `along` +3.26.
4. **The back wall's 0.33-unit margin**, which is the whole clearance the two
   pinned centrelines permit, and the proof of that is now in `MergeCatch`'s
   docstring: orange's line is
   `across = 1.381 + 0.884 * (along - 1.531)`, which passes through the sprint's
   entry point *on its centreline*, so no transverse wall with a channel-shaped
   opening can sort the two streams anywhere in front of the entry. `merge_lead[0]`
   is where the marbles that use that opening end up.

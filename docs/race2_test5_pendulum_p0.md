# Race #2 — Test #5 P0: Pendulum Cross

**Status:** P0 mechanism validation — physics only
**Branch:** `video-test5-prediction-gauntlet`
**Base:** `main@65df08a`
**Scope:** does one `PendulumCross` earn screen time in Test #5?
**Not in scope:** course composition, camera, lighting, environment art, audio,
captions, packaging, and the Memory Rocker — which gets an architecture note at
the end of this document and no code.

This is the P0 step `docs/race2_test5_prediction_gauntlet.md` §12 asks for:
*"build ugly/no-art deterministic prototypes … measure finish rate,
jams/escapes, mechanism events and order effects."*

---

## 1. Phase 1 — the implementation as it stood

The branch arrived with `PendulumCross`, six unit tests, and all six passing.

**All six passed while the arm was inside the floor.**

The module typed its arm as two constants stated before the run's profile
scale — `ARM_LENGTH = 2.30`, `PIVOT_RISE = 1.72` — and `RaceRun.scale` is 2.0,
so the built arm was 4.60 layout units long hanging from a pivot 3.44 above the
channel centreline. Surveyed against the cradle arc and the capped rail that
`race2.track` actually builds, on `cascade/corr1` sample 17 (half width 1.915,
cradle −0.520, rail top +0.580, all layout units relative to the centreline):

| arm angle | tip across | tip up | cradle under the tip | tip − cradle | wall gap |
|---|---|---|---|---|---|
| −45° | −3.253 | +0.187 | — | — | **−1.338** |
| −25° | −1.944 | −0.729 | — | — | **−0.029** |
| −20° | −1.573 | −0.883 | −0.240 | **−0.643** | +0.342 |
| 0° | 0.000 | −1.160 | −0.520 | **−0.640** | +1.915 |
| +25° | +1.944 | −0.729 | — | — | **−0.029** |
| +45° | +3.253 | +0.187 | — | — | **−1.338** |

Two defects, both of the kinds the brief listed:

1. **Floor penetration at every angle in the arc.** The tip sat 0.64 layout
   units — 1.12 marble diameters — below the cradle surface across the whole
   swing. A racer in that channel is not deflected by that pendulum; it is
   scooped through the floor.
2. **Rail penetration past ±25°.** Beyond that the tip was outside the guard
   rail while still *below* the rail's top, so the swept box passed through the
   wall. A blade that overhangs a wall pins a racer against it — the failure
   `race2.parts.Wheel`'s own docstring records as having left "seven of eight
   racers stuck at two wheels".

Neither is visible to Bullet: two non-dynamic bodies interpenetrate silently.
Neither is visible to a test that asserts the pose is a pure function of the
tick, which is what all six shipped tests did.

The root cause is the one `Wheel` already paid for and wrote down: **a station's
reach cannot be a typed constant when the channel's width varies along the
run.**

### The fix

`race2/test5_parts.py` now derives the whole geometry from the channel at the
station. Three inputs:

| input | meaning |
|---|---|
| `reach` | the furthest any part of the swept box goes across the channel, **as a fraction of the local half width** |
| `clearance` | how far the swept box passes above the cradle at its lowest, in layout units before the profile scale |
| `amplitude` | the swing angle |

and everything else follows:

```
arm length = (reach · half width − ½ depth · cos A) / sin A
pivot rise = the height that puts the whole swept box `clearance` above the
             cradle at its worst angle
```

The pivot rise is *solved*, not typed. The box translates with the pivot along
the run's up axis, so the worst clearance is affine in the rise with unit
slope: one survey of 121 angles × 8 box corners at a trial rise settles it
exactly, with no search and no tolerance. The survey projects the real pose —
`PendulumArm.pose_for_angle`, the same law `pose_at` uses — onto the run's own
lateral and up axes and compares against the cradle arc
`TrackRun.surface_point` is built from.

Three bounds are then checked and **refused** rather than clamped. Two were
written with the fix; the third was added after §4.8 measured it:

- `side_gap = half width − reach` must exceed a marble diameter, or the arm
  pins a racer against the rail. This is `Wheel`'s disruptor/gate line.
- the axle must clear the rail it hangs over, so
  `arm length ≥ rail top + axle radius + margin − cradle`.
- `centre_uncovered = L·sin(A) − depth/2` must be positive, or the swept box
  never uncovers the channel's centreline and a racer is held there for the
  whole race. See §4.8 — this is the one that made a *lower* reach the
  dangerous direction.

The second bound is the non-obvious one, and it **couples amplitude to
position**: for a fixed reach, a wide swing needs a short arm, and a short
enough arm puts the axle inside the channel. Measured feasibility, this lab's
`corr1`:

| station | local half width | amplitudes the channel accepts |
|---|---|---|
| 0.20 | 2.184 | 6°–46° (all tested) |
| 0.30 | 1.915 | 6°–34° |
| 0.40 | 1.623 | 6°–26° |
| 0.50 | 1.446 | 6°–20° |
| 0.62 | 1.439 | 6°–20° |
| 0.85 | 1.504 | 6°–22° |

and the buildable reach band at 14° and station 0.62 is only **0.52 to 0.60** —
bounded below by the axle and the centreline condition, above by the side gap.
Which configurations are unbuildable is a result, so `race2.test5_lab.sweep`
records each refusal with its reason instead of skipping it. Note that the
recorded evidence in §4.8 *includes* configurations the code now refuses: they
are what justified the guard.

After the fix, at every station tested: cradle clearance exactly +0.100 layout
units, side gap 0.63–1.30 (a marble is 0.57), axle above the rail.

A secondary defect was introduced by the fix and then removed:
`local_bounds` surveyed 968 points on every call, and `Machine.module_at` asks
every module for its bounds on every locate — 15 s of wall clock per 30-second
seed, five times the race itself. The swept volume cannot change once the arm
is built, so it is measured once. `local_actuators` is cached for the same
reason: `BuiltModule.apply_actuators` calls it at 240 Hz.

---

## 2. Phase 2 — the P0 lab course

`race2/test5_course.py`, registry `pendulum_p0` / `pendulum_p0_bare`. Its own
module and its own registry so it can never be mistaken for SWITCHYARD.

**Five runs, a bit-identical prefix of the production skeleton.**
`race2.concepts._skeleton_runs` cuts the eleven-run plan at ten fixed places
and cannot be asked for fewer, so the prefix is cut in the lab from the same
`SKELETON` tuple at the same `SKELETON_BREAKS` distances. Verified sample for
sample against `courses.build("switchyard")`: identical centrelines, identical
sample counts, identical arc lengths.

| run | skeleton | width | job |
|---|---|---|---|
| `head` | straight 14.0 × 4.2 | `W_BAND` | release, then destroy the bay order |
| `pan1` | hairpin r4.8 180° | → `W_PAN` | compress: the field arrives level |
| `corr1` | straight 17.0 × 4.2 | → `W_LANE` | **the pendulum, and nothing else** |
| `pan2` | hairpin r4.8 180° | → `W_PAN` | recompress: the comeback window |
| `sprint` | straight 16.0 × 4.0 | → `W_NECK` | a clean fall with nothing on it |

79.1 layout units of centreline, 16.8 of fall — 45% of SWITCHYARD's length.
Only the last name differs from production: what SWITCHYARD calls `corr2` is
this course's final sprint, because in five runs it is one.

Borrowed unchanged: `kit.serpentine`, `concepts._run`, `concepts._breaks_at`,
`concepts._attach_start`, `sloped.stations.Mixer` (the nine-stud fairness
field), `race2.parts.RunOut` (the deck V33.1 corrected), `race2.course.Course`.
Nothing in `race2/courses.py`, `race2/concepts.py`, `race2/race.py`,
`race2/bench.py` or `race2/events.py` was modified.

**Six racers, and the bay count is not the marble count.**
`MarbleSimulation` truncates the start's bays with `starts[:marble_count]`, so
an eight-bay shelf asked for six loads the six bays on *one side* of the band
and leaves two empty — a lateral bias present before the race starts. The lab
builds a **six**-bay `DropStart`, so the field is symmetric about the
centreline: bays at +2.05, +1.23, +0.41, −0.41, −1.23, −2.05.

**The control is part of the design.** `pendulum_p0_bare` is the identical
course with the module left out, and it is expressed as the same
`PendulumSetting` value with `armed=False` so it cannot drift from the
configuration it controls. Removing a module renumbers Bullet's bodies, so the
two runs of one seed are different simulations; no per-seed claim is made
across the pair, only distributions.

---

## 3. Phase 3 — how the pendulum is measured

`race2/test5_lab.py`. Four measurements, and the ordering matters: the first
comes from the production instrument, the last is the one that makes the others
mean anything.

### Reliability, from the existing instrument

Finish count, escapes, racers left in the machine, the event timeline and the
longest dead interval all come from `race2.race.run_race` and
`race2.events.extract` unchanged, and the slot correlation from
`race2.bench.spearman`. `race2.bench`'s own docstring warns that computing a
metric one way for concepts and another for the chosen course is "a comparison
of two instruments"; a P0 lab that reimplemented finish-rate arithmetic would
be exactly that.

### Contact, computed from the deterministic pose

`Race2._note_mechanism` records true Bullet contacts with a named station, but
only for the leading three racers and only once per 0.6 s, because it feeds an
event density. A P0 lab wants every racer.

It can have them without touching the simulation, and the reason it can **is
the actuator contract**: the arm's pose is a pure function of the tick, so the
exact pose the solver used at tick *n* is recomputable afterwards. Marble
positions are interpolated across each 60 Hz replay interval while arm poses
are evaluated exactly at every 240 Hz physics tick, and the distance from each
marble centre to the swept box gives, per racer: closest approach, whether it
counts as a touch, how long it spent that close, and when it first did.

This is a *proximity* measure and is reported as one. `TOUCH_SLACK` is 0.15 of
a marble radius — above the worst error interpolation can introduce (a racer at
35 sim units a second moves 0.145 per substep) and far under a radius, so a
racer that passed on the far side of the channel is never counted. A test
asserts the recomputed pose equals the pose the replay recorded, everywhere the
two overlap, so the method rests on a checked identity rather than an
assumption.

### Rank change, at three scopes and two readings

A struck racer loses its place *downstream* of the strike, so one window
cannot be right. Three are measured and each is labelled:

- **region** — 2.0 units before the arm to 6.0 after. The immediate deflection.
- **corridor** — 2.0 units before the arm to the end of `corr1`. **The headline
  number**, because `corr1` holds the arm and nothing else.
- **finish** — 2.0 units before the arm to the finishing order. Everything
  downstream including the recovery hairpin: an upper bound, not a measure.

And each window is read two ways, because the obvious reading is confounded:

- **Crossing order** (headline). Each racer's own interpolated crossing time of
  the window's two progress marks; who went in first against who came out
  first. A sector comparison, anchored to the course.
- **Sticky order** (secondary). The viewer-agreeing ordering
  (`race2.race.LEAD_MARGIN`) before and after. Honest but flattering: an arm
  that holds the sixth racer up for two seconds means the leaders are far past
  the window by the time it clears, so part of the "after" ordering is
  downstream racing rather than the arm.

The difference is not academic. Over 50 seeds the bare control reads **20%
reorder on the crossing measure and 80% on the sticky one** — the sticky
reading of an empty corridor is mostly artefact. Where the two disagree, the
crossing order is what the verdict uses.

### One field that is not connected

`RunStats.max_energy_rise` is **structurally zero for every Race #2 race**. It
is accumulated by `marble3d.simulation.run_simulation`, and `race2.race.run_race`
is a different driver; `_replay_of` copies `race.stats.to_json()`, so the field
travels in the replay summary but the number was never taken. It is not
reported here — a zero from an unconnected instrument reads exactly like a
pass. The invariant itself is checked directly instead, by stepping a race and
asserting the field's energy never rises once the start gate has stopped
moving, which matters because a kinematic arm is infinitely heavy to a marble
and could shove without limit.

What *is* carried per seed: `worst_actuator_overlap` (how deep the arm got into
a marble before the solver pushed it out) and `max_travel_per_tick` against
`travel_budget`.

---

## 4. Phase 4 — the benchmark

50 deterministic seeds per configuration (seeds 1–50), 20 s limit, six racers.
Every armed configuration is paired with a no-arm control over the same seeds,
built from the same `PendulumSetting` with `armed=False`. Evidence:
`docs/validation/race2/test5_p0/*.json`.

Reproduce a pass with, for example:

```
python -m race2.test5_lab --seeds 50 \
    --amplitude 8 --amplitude 12 --amplitude 16 --amplitude 20 \
    --rate 1.6 --rate 2.4 --rate 3.2 --rate 4.4
```

### Why each range, physically

**amplitude, 8°–20°.** Bounded above by the channel: at station 0.62 the axle
stops clearing the rail past 20°, measured. Bounded below by the gantry: at 8°
the arm is 3.5 layout units long and its axle sits 2.5 above the rail, taller
than the course is deep. Within the band, amplitude changes the *shape* of the
swept region rather than its width — the lateral reach is fixed by `reach`, so
what moves is how far the tip lifts at each extreme (0.03 layout units at 8°,
0.09 at 20°) and how long the silhouette is.

**rate, 1.6–4.4 rad/s** (period 3.93 s down to 1.43 s). The field crosses
`corr1` in about 0.97 s at corridor speed and arrives spread over roughly half
of that. A period much longer than the arrival spread makes the arm a static
obstacle offset to one side — everyone meets the same position, and the
mechanism degenerates into a lateral bias. A period much shorter makes it a
blur, where everyone meets the average and the outcome stops being readable.
The interesting regime is a period of about one to four times the arrival
spread, which is what this range brackets.

**phase, 0 to 2π in six steps.** The one parameter with no physical argument
for any particular value, which is exactly why it is swept: if the outcome
depends strongly on phase, the mechanism is locked to the *course* rather than
to arrival, and a fixed phase would then be an authored advantage.

**position, 0.20–0.75 of `corr1`.** The corridor is still funnelling down from
the pan until about 0.55 of its length, so the local half width falls from 2.18
to 1.44 over this range. Position therefore changes two things at once: how
strung out the field is when it arrives, and how wide a swing the channel will
accept. The last three settings of the pass pair a wide station with a wide
swing for that reason.

**reach, 0.40–0.60 of the local half width.** The safety lever, and the band is
narrow because both bounds are physical: below about 0.46 the arm is too short
for its axle to clear the rail, and above about 0.56 the clear channel beside
the arm falls under a marble diameter and the arm would pin a racer. The
refusals are reported rather than skipped.

**mixer span, 0.58–0.98.** Not a pendulum dial. It is swept because the lab
course turned out to carry a start bias of its own and the stud row was the
obvious suspect — see §4.4.

### 4.1 Baseline: the arm against its own control

Default configuration (14°, 3.0 rad/s, phase 0, station 0.62, reach 0.56)
against the identical course with the module removed, seeds 1–50.

| | armed | bare control |
|---|---|---|
| racers finishing | 99.0% | 98.7% |
| races with all six | **94.0%** | 92.0% |
| races with a racer left in the machine | 4.0% | 4.0% |
| racers escaping | 0.33% (1) | 0.67% (2) |
| racers lost inside the arm's region | 1 | 0 |
| corridor reorder (crossing) | **100%** | **20%** |
| corridor leader lost | **68%** | **0%** |
| corridor racers moved, mean of 6 | **4.68** | 0.50 |
| pairs swapped, mean | 4.74 | 0.26 |
| lead changes per race | 3.44 | 3.24 |
| mean comeback (winner's early deficit) | 1.46 | 0.76 |
| median race | 6.33 s | 4.97 s |
| worst dead interval | 1.80 s | 2.07 s |
| slot correlation | +0.097 | +0.044 |
| racers touching the arm, mean | 4.30 of 6 | — |
| deepest arm/marble overlap | −0.181 sim (0.36 radii) | −0.00001 |
| worst travel per tick | 0.419 of 0.500 budget | 0.303 |

**The reliability failures are the course's, not the arm's.** Seeds 17 and 46
lose one racer at `pan1` sample 45 on *both* courses — same seed, same racer,
same sample. The bare control additionally loses two racers over the rail in
the `sprint`. The arm's own contribution is one escape, discussed in §4.3.

### 4.2 Amplitude against rate: rate is the dial, amplitude is not

Sixteen configurations, seeds 1–50 each, station 0.62. Corridor crossing
reading; every row's reliability is identical at 94% all-six except where noted.

| rate (period) | reorder | leader lost | racers moved | comeback | median race |
|---|---|---|---|---|---|
| 1.6 (3.93 s) | 82–84% | 26–32% | 3.20–3.42 | 1.08–1.36 | 5.72–5.85 s |
| 2.4 (2.62 s) | 94–96% | 48–52% | 3.98–4.10 | 1.26–1.56 | 5.97–6.01 s |
| 3.2 (1.96 s) | 98–100% | **72–80%** | 4.62–4.88 | 1.58–1.98 | 6.16–6.22 s |
| 4.4 (1.43 s) | 86–90% | **20–22%** | 3.22–3.38 | 0.94–1.16 | 5.93–5.96 s |

Each band collapses four amplitudes (8°, 12°, 16°, 20°) whose spread inside the
band is smaller than the spread between bands. That is the finding:

**The effect peaks at a period of about twice the corridor transit and falls
away on both sides.** The field crosses `corr1` in about 0.97 s. At 1.96 s the
arm makes one full crossing of the lane while the field passes, so the leaders
meet it on one side and the tail on the other — maximum differential. At 3.93 s
it barely moves during the pass and degenerates towards a static obstacle
offset to one side. At 1.43 s it has returned to nearly the same place by the
time the tail arrives, so the differential collapses again. This is a
resonance, not a monotone dial, and it means **rate is not a free parameter**.

**Amplitude does almost nothing competitively**, and the geometry says why: for
a fixed reach the tip's lateral speed is `length × A × rate`, and length is
itself `≈ reach / sin A`, so the product is very nearly `reach × rate` at any
amplitude. Measured sweep speeds at rate 1.6 across 8°→20°: 0.753, 0.763,
0.776, 0.794 layout units a second — a 5% spread across a 2.5× change in arm
length (3.37 → 1.42). **Amplitude is a visual dial: choose it for the
silhouette, and choose the rate for the drama.** That is a useful separation for
P1 and it was not obvious before the grid.

### 4.3 The one arm-caused escape, diagnosed

Sixteen of seventeen armed configurations lose exactly one racer per 50 races to
an `outside` containment loss in `corr1`, a few samples downstream of the arm —
seed 37 at most rates, 44 at rate 1.6, 31 at rate 4.4. It is consistent enough
to be a mechanism rather than an accident, so it was traced frame by frame
(seed 37, default configuration).

**The arm never touches the racer that is lost.** Its closest approach to the
swept box over the whole pass is **+0.62 layout units** — more than a marble
diameter, and fifteen times the touch threshold. What happens instead:

```
t=2.683  m2 at 24.58 layout u/s, m3 at 24.95, m5 at 24.99   (arriving)
t=2.700  m2 at  5.14,             m3 at 11.20, m5 at 14.96   (the arm has braked them)
         m4 still at 27.21, 0.04 behind m3
t=2.708  collision {a: 3, b: 4, speed: 42.65 sim} = 24.3 layout u/s closing
t=2.717  m4's velocity jumps by +11.5 across and +18.8 up in one frame
t=2.733  m4 above the rail top; thereafter pure ballistic flight
t=2.817  m4 leaves the channel at across 3.07, height 2.88
```

So the arm is an infinitely heavy brake — a kinematic body, mass zero, which is
correct for a gate and total for a marble — and it takes three racers from 25
layout units a second to between 5 and 15 inside one 60 Hz frame. A fourth
racer arriving at 27 into the back of that is a 24 layout-unit-a-second
rear-end collision in a 2.9-unit-wide channel, and the marble goes up.

**Rail is the wrong fix, and the arithmetic says so.** The launched racer
reached +1.76 layout units above the centreline. Containing that needs a rail
at 1.76 against a 1.44 half width, which is `atan(1.76 / 1.44)` = **50.9° of
look-down** — exactly the map view `race2.track`'s `WALL_CAP` was introduced to
escape ("50 degrees of look-down over every corridor is the map view"). A
pan-sized guard boost (+0.56, rail at 1.14) reads 38.4° and would still not
contain it.

The levers that could work are therefore not containment but:

1. **a wider station**, so a braked racer can be passed instead of rear-ended;
2. **a less aggressive arm** — less depth or less reach, so fewer racers are
   caught square and the speed differential is smaller.

Both are measured in §4.5 and §4.6 rather than argued.

### 4.4 Fairness: the arm halves a bias it did not create

Mean finishing rank by starting bay, over 50 seeds. Bays run +2.05, +1.23,
+0.41, −0.41, −1.23, −2.05 across the band, symmetric about the centreline.

| configuration | bay 0 | 1 | 2 | 3 | 4 | 5 | spread |
|---|---|---|---|---|---|---|---|
| bare control | 2.94 | **5.04** | 2.28 | 2.63 | 4.08 | 3.74 | **2.76** |
| armed, default | 3.08 | 4.14 | 2.78 | 2.92 | 4.26 | 3.65 | 1.48 |
| armed, best (12°, 3.2) | 3.00 | 4.02 | 3.12 | 3.10 | 4.00 | 3.59 | **1.02** |

**The control has a severe mid-lane penalty.** Bay 1 averages 5.04 of 6 and
never wins a single race in 50; bays 2 and 3 win 35 of 50 between them. The
shape is a W — centre best, mid-lane worst, edges middling — which is why the
Spearman slot correlation reads only +0.044: it is looking for a monotone
trend and the bias is not monotone. **A slot correlation near zero is not
evidence of a fair start**, and that is worth recording because every
slot-fairness number in this package is a rank correlation.

The obvious suspect was the stud row: at six bays, the +/−1.23 bays sit 0.105
from a stud and the +/−2.05 bays thread between two studs 0.62 and 0.72 away,
against a marble-plus-pin contact distance of 0.360. **The scan falsifies it.**
Six stud spans, 50 seeds each, bare:

| stud span | bays meeting a stud head-on | all six | mean rank by bay | spread |
|---|---|---|---|---|
| 0.58 | 4 | 92% | 3.21, 4.96, 2.04, 2.62, 4.38, 3.55 | 2.92 |
| 0.66 | 6 | 100% | 3.60, 5.14, 1.96, 2.38, 4.34, 3.58 | 3.18 |
| 0.74 | 6 | 98% | 3.28, 5.08, 2.04, 2.56, 4.16, 3.80 | 3.04 |
| 0.82 | 2 | 86% | 3.04, 5.02, 2.04, 2.61, 4.12, 3.72 | 2.98 |
| 0.90 | 2 | 92% | 2.94, 5.04, 2.28, 2.63, 4.08, 3.74 | 2.76 |
| 0.98 | 2 | 92% | 3.00, 5.08, 2.19, 2.71, 4.16, 3.56 | 2.89 |

The head-on count swings from 2 to 6 and **the rank pattern does not move**:
bay 1 sits at 4.96–5.14 in every one of them. The bias is not the stud row, and
no stud span available fixes it. The lab therefore keeps SWITCHYARD's proven
0.90 rather than tuning a number on 50 seeds to flatter a result. (Span 0.66
gives 100% all-six over these 50 seeds, which is interesting and not adopted:
four failures against zero is not a distinguishable difference at this sample
size, and start geometry belongs to P1.)

Run armed as well as bare, the span turns out to trade reliability against
fairness in opposite directions — which is a second reason not to tune it here:

| stud span | all six (bare / armed) | escapes (bare / armed) | rank spread (bare / armed) |
|---|---|---|---|
| 0.66 | **100% / 100%** | **0 / 0** | 3.18 / 2.04 |
| 0.82 | 86% / 90% | 1.00% / 0.33% | 2.98 / 1.62 |
| 0.90 | 92% / 94% | 0.67% / 0.33% | **2.76 / 1.48** |

Span 0.66 is the only setting in this whole P0 that finishes all six racers in
every race, armed *and* bare — and it has the worst slot spread of the three.
0.90 has the best spread and loses a racer in one race in twelve. There is no
setting that is good at both, so the lab keeps the production number and hands
the trade-off to P1 with the measurement attached.

This is the constraint `docs/sloped_race_v1*.md` already established over five
falsified start topologies: *every passive start delivers its field into a
course that reads some geometric coordinate as a time advantage, and the
surviving coordinate is always a function of the starting bay.* The one thing
recorded as reducing it there was **building a second route**, because a branch
outcome is not a function of start bay.

**The pendulum does the same thing without a fork.** Arrival phase is not a
function of the starting bay either, and the arm roughly halves the spread
(2.76 → 1.48 at the default, → 1.02 at the strongest setting) while leaving the
rank correlation low. That is the strongest competitive argument in this
document, and it is an argument the mechanism was not designed to make.

### 4.5 The arm is a pack gate, not a disruptor — and that is the mechanism

`race2.parts.Wheel` established the test for whether an obstacle is safe: leave
more than a marble diameter of clear channel beside it and "nothing is ever
stopped — a marble is deflected, delayed or let through". `PendulumCross`
inherits that test and passes it: at the default configuration the side gap is
0.633 against a 0.570 marble, so `describe()["gate"]` is False.

**The test is a single-marble test, and a six-racer field does not arrive one
at a time.** Traced on seed 37, armed against bare, the slowest speed each
racer reached inside `corr1`:

| racer | armed | bare |
|---|---|---|
| m0 | 3.64 | 22.08 |
| m2 | **0.01** | 12.95 |
| m3 | **0.01** | 16.99 |
| m5 | 10.80 | 20.64 |

Two racers come to a **dead stop** against the arm and are released when it
swings away; the bare control never drops a racer below 12.95 layout units a
second anywhere in the corridor. A 0.633 gap fits one marble with 0.063 to
spare and cannot pass two abreast, so a pack meeting the arm queues.

**That queue is the mechanism.** It is what produces the reordering (4.68 of 6
racers change their crossing order, against 0.50 in the control), and it is
also what produces §4.3's 24 layout-unit-a-second rear-end. The two are the
same physics and cannot be separated by tuning the arm's motion; only by
changing how much room there is beside it.

Side gap in marble diameters, over the feasible grid — the axle-over-rail bound
refuses reach 0.40 anywhere past station 0.30:

| station | half width | reach 0.40 | 0.46 | 0.52 | 0.56 | 0.60 |
|---|---|---|---|---|---|---|
| 0.20 | 2.184 | **2.30** | **2.07** | 1.84 | 1.69 | 1.53 |
| 0.30 | 1.915 | **2.02** | 1.81 | 1.61 | 1.48 | 1.34 |
| 0.40 | 1.623 | refused | 1.54 | 1.37 | 1.25 | 1.14 |
| 0.50 | 1.446 | refused | 1.37 | 1.22 | 1.12 | 1.01 |
| 0.62 | 1.439 | refused | 1.36 | 1.21 | **1.11** | 1.01 |
| 0.75 | 1.487 | refused | 1.41 | 1.25 | 1.15 | 1.04 |

**Only the corridor's entry admits a pendulum with two marbles' width beside
it**, and only at low reach — because `corr1` has not yet funnelled down from
the pan there. Everywhere past station 0.40 the channel is too narrow for the
arm to be anything but a pack gate, at every reach the axle will allow. That is
a structural statement about a `W_LANE` corridor, not about this arm.

### 4.6 Phase is more of an authored lever than the race is

Six phases over a full cycle, station 0.62, seeds 1–50:

| phase | reorder | leader lost | racers moved | comeback | all six | lost at the arm |
|---|---|---|---|---|---|---|
| 0 | 100% | 68% | 4.68 | 1.46 | 94% | 1 |
| π/3 | 100% | 74% | 4.94 | 1.44 | 94% | 1 |
| 2π/3 | 90% | 56% | 4.20 | **2.02** | **96%** | **0** |
| π | 82% | 28% | 3.40 | 1.28 | 94% | 1 |
| 4π/3 | 90% | 36% | 3.54 | 1.32 | 92% | 2 |
| 5π/3 | 96% | 66% | 4.38 | 1.50 | 94% | 1 |

Leader-lost swings from 28% to 74%. Sampling error at n=50 is about ±7% at one
standard deviation, so that spread is real, and the reason is uncomfortable:

**the leading racer reaches the arm at 2.490 s ± 0.046 s, and those numbers are
identical for every phase and every seed.** The full seed-to-seed range is
2.395–2.611 s. Against a 2.09 s period that is **37° of the arm's cycle across
all fifty seeds**, while the phase steps tested are 60° apart. The authored
phase therefore moves the arm's position at the leader's arrival further than
the entire race does.

Two things follow, and they point in opposite directions.

*The within-field differential is genuine.* The bare control's field enters the
window at 2.490 s and has cleared it by 3.217 s — 0.73 s of natural spread,
which is **125° of cycle** between the first racer and the last. The tail
genuinely meets a different arm position from the leader, and that is the
reordering.

*The leader's own fate is substantially authored.* 37° of seed variation
against a 60° authored step means a viewer watching many races of *this course*
would find the leader's treatment largely repeatable. Nothing selects a racer —
`MarbleSimulation._spawn` shuffles which marble sits in which bay per seed, so
no colour is favoured — but the *severity* is a number a human chose.

This is a **course-composition constraint rather than a mechanism defect**, and
the cause is visible in the lab's own shortness: the approach here is release →
studs → one hairpin → corridor, 2.5 s of almost deterministic travel. Seed
divergence has not had time to grow. In an 18-second course with mechanisms
upstream, arrival times would be scattered far more widely. The rule to carry
into P1 is therefore measurable:

> **A mechanism's period must be comparable to the spread of arrival times it
> actually sees.** Measure that spread at the station before choosing the rate,
> and treat a mechanism whose period exceeds the spread as an authored
> obstacle, not a raced one.

### 4.7 Position: where the arm stands decides whether anyone is lost

Six stations along `corr1`, plus three pairing a wide station with a wide swing,
each against a control at the same station, seeds 1–50. The controls differ
because the measurement window runs from the arm to the corridor's end, so an
early station gives more corridor for the *control* to reorder in — which is
exactly why each armed row is read against its own.

| station | half width | side gap | reorder (armed / bare) | leader lost | racers moved (armed / bare) | all six | `corr1` losses |
|---|---|---|---|---|---|---|---|
| 0.20 | 2.184 | 0.961 | 100% / 88% | 72% / 22% | 4.64 / 2.64 | 94% | **0** |
| 0.30 | 1.915 | 0.843 | 100% / 74% | 62% / 16% | 4.58 / 2.06 | **96%** | **0** |
| 0.40 | 1.623 | 0.714 | 100% / 48% | 56% / 6% | 4.44 / 1.26 | **96%** | **0** |
| 0.50 | 1.446 | 0.636 | 98% / 36% | 56% / 2% | 4.40 / 0.82 | **96%** | **0** |
| 0.62 | 1.439 | 0.633 | 100% / 20% | 68% / 0% | 4.68 / 0.50 | 94% | 1 |
| 0.75 | 1.487 | 0.654 | 96% / 8% | 60% / 0% | 4.28 / 0.16 | 94% | 1 |
| 0.20 @ 34° | 2.184 | 0.961 | 100% / 88% | 74% / 22% | 4.74 / 2.64 | **96%** | **0** |
| 0.30 @ 26° | 1.915 | 0.843 | 100% / 74% | 64% / 16% | 4.72 / 2.06 | **96%** | **0** |
| 0.40 @ 24° | 1.623 | 0.714 | 100% / 48% | 60% / 6% | 4.42 / 1.26 | **96%** | **0** |

**The arm's absolute effect barely varies with station** — reorder 96–100%,
racers moved 4.28–4.74, leader lost 56–74% everywhere. What varies is the
control, and therefore the *differential*, which grows from +12 points of
reorder at station 0.20 to +88 at 0.75 simply because a shorter window has less
natural reordering in it. That is an argument for reading the differential at a
matched window and not for preferring a late station.

**What does depend on the station is the escape**, and the attribution is
clean. Counting every racer lost on `corr1` — the run the arm stands on, and
the only run in this course carrying a mechanism — across every pass:

| | `corr1` losses |
|---|---|
| 9 bare-control configurations × 50 seeds | **0 of 450 races** |
| stations 0.20–0.50, 7 configurations × 50 seeds | **0 of 350 races** |
| stations 0.62 and 0.75, 24 configurations × 50 seeds | **24 events, in 23 of the 24** |

The corridor without an arm never loses a racer. With an arm past mid-corridor
it loses one in essentially every configuration tested — fifteen amplitude/rate
combinations, five of six phases, both late stations — so this is a property of
the station, not a seed. If the rate upstream were the same 2% of races, seeing
zero in 350 races would have probability 8.7 × 10⁻⁴.

**Where the loss is recorded says why.** Every one is at progress 46.2–47.4,
against a `corr1` exit seam at 47.363. The launched racer of §4.3 does not
leave the channel where it is hit; it flies and comes down **past the corridor's
exit**. Stations at or before 0.50 leave enough corridor ahead for the arc to
land back inside it.

That has a consequence for how much this finding can be trusted: stations 0.50
and 0.62 are geometrically almost identical — side gaps 0.636 and 0.633, arm
lengths 1.98 and 1.97 — so **the safety margin here is positional, not
geometric.** The rule to carry forward is therefore "stand the arm far enough
from the next seam that a launched racer lands before it, and verify at the
chosen station", not "0.50 is a safe number".

### 4.8 Reach: a wider gap beside the arm is a *worse* arm

Reach was the safety lever, so this pass was expected to be dull. It is the
most surprising result in the P0 and it falsifies the reasoning of §4.5.

Two amplitudes × five reaches at station 0.62, seeds 1–50. Reach 0.40 at 14° is
refused by the axle bound.

| reach | side gap | side gap in marbles | all six | racers pinned in `corr1` | reorder | racers moved |
|---|---|---|---|---|---|---|
| 0.40 | **0.863** | 1.51 | **76.0%** | **10** | 98% | 4.48 |
| 0.46 | 0.777 | 1.36 | 86.0% | 4 | 98% | 4.50 |
| 0.52 | 0.691 | 1.21 | 92.0% | 1 | 98% | 4.46 |
| 0.56 | 0.633 | 1.11 | 94.0% | 0 | 100% | 4.58 |
| 0.60 | **0.576** | 1.01 | **94.0%** | **0** | 98% | 4.58 |

*(10° rows; the 14° rows run 88 / 90 / 94 / 94% with 3 / 2 / 0 / 0 pinned.)*

**The widest side gap is the worst configuration**, and the competitive effect
is flat across the whole range — reorder 98–100%, racers moved 4.46–4.68. So
reach buys nothing competitively and costs reliability in the direction nobody
would guess.

Every pinned racer is at `corr1` sample 34, two samples upstream of the arm.
Traced: the marble sits at `across` 0.000, resting on the cradle, with a **zero
gap to the swept box, at every angle from −9.9° to +10.0°, from 4 s to the 20 s
limit.** It is not delayed. It is held for the rest of the race.

**The condition is closed-form.** The swing moves the arm's *axis* through
±`L·sin(A)`, and the box carries `depth/2` either side of that axis. If

```
L · sin(A)  ≤  depth / 2
```

the box covers the channel's centreline at every angle in the arc — and the
cradle centres a marble on exactly that line. Define
`centre_uncovered = L·sin(A) − depth/2`. Over the nine buildable
configurations, 450 races, it orders the failures perfectly:

| `centre_uncovered` | −0.099 | −0.013 | −0.008 | +0.073 | +0.078 | +0.131 | +0.136 | +0.188 | +0.193 |
|---|---|---|---|---|---|---|---|---|---|
| racers pinned | 10 | 4 | 3 | 1 | 2 | 0 | 0 | 0 | 0 |

**Why reach walks into it.** Reach fixes the lateral excursion of the box's
*outer* edge, so lowering it shortens the arm; a shorter arm at the same
amplitude sweeps its axis a shorter distance while keeping its width, and the
inner edge stops crossing the centre. The gap you gain laterally you lose in the
one place it matters. The same move also lowers the axle — at reach 0.40 the
pivot sits at 1.006 against an axle floor of 0.980, 0.026 of margin.

`PendulumCross` now refuses a non-positive `centre_uncovered`, because that case
is provably a plug rather than an obstacle, and publishes the number because the
*margin* is what a tuner needs: about +0.13 — half a marble radius — is where
pinning stopped in this channel.

### 4.9 The acceptance gate

Written before any results were read, from §5 of
`docs/race2_test5_prediction_gauntlet.md`:

**Reliable** — all six racers finish in ≥ 96% of races; no racer lost on the
arm's own run; the arm's deepest overlap with a marble shallower than half a
marble radius (0.25 simulation units); worst dead interval ≤ 2.0 s.
**Competitive** — corridor crossing reorder ≥ 60% of races; leader lost in
25–75% (uncertain, but not a forced coin-toss); mean racers moved 1.5–4.5 of 6
(meaningful, not maximum chaos); mean comeback ≥ 0.5.

Two notes on applying it honestly.

*96% is the ceiling on this lab course, not a low bar.* Seeds 17 and 46 lose a
racer at `pan1` on the armed **and** bare courses, so 48 of 50 is the best any
configuration can score. "All six ≥ 96%" therefore reads as "the arm loses
nobody".

*One criterion was measured by a broken instrument and is re-measured here.*
`P0Seed.stuck_at_pendulum` counts a non-finisher whose progress falls inside the
measurement window, which catches the course's own `pan1` failures whenever the
window sits early in the corridor — station 0.30 reports "2 lost at the arm"
and has none. The attribution used below is the run the racer was lost on.
`corr1` carries the arm and nothing else, and the thirteen no-arm controls lose
nobody there in 650 races. The criterion is unchanged; only its measurement is.

*And one criterion cannot discriminate.* The no-arm controls' own worst dead
interval is 2.75 s, so a 2.0 s worst-case bound fails the empty course. It is
reported, not relaxed. The brief's actual threshold — "more than roughly 3 s of
low-information waiting" — is met by every passing configuration at 1.2 s mean
and 2.3 s worst.

**Five of forty-four armed configurations clear every criterion:**

| configuration | all six | `corr1` lost | reorder | leader lost | moved | comeback | slot spread | dead mean/worst |
|---|---|---|---|---|---|---|---|---|
| station 0.62, 14°, span 0.66 | **100%** | 0 | 94% | 60% | 4.02 | 1.26 | 2.04 | 1.21 / **1.92** |
| station 0.40, 24° | 96% | 0 | 100% | 60% | 4.42 | 1.52 | 1.34 | 1.25 / **1.93** |
| station 0.40, 14° | 96% | 0 | 100% | 56% | 4.44 | 1.48 | **1.20** | 1.22 / 2.33 |
| station 0.50, 14° | 96% | 0 | 98% | 56% | 4.40 | 1.56 | **1.16** | 1.22 / 2.20 |
| station 0.62, 14°, phase 2π/3 | 96% | 0 | 90% | 56% | 4.20 | **2.02** | 1.26 | 1.21 / 2.25 |

Of the thirty-nine that fail, **all but two fail on a single `corr1` loss at
station 0.62 or 0.75, or on the plug condition at low reach** — that is, on the
two defects §4.3 and §4.8 diagnosed, not on a spread of unrelated problems. The
remaining two fail on the competitive band: rate 4.4 punishes the leader in only
20–22% of races, and rate 3.2 at station 0.62 punishes it in 78–80% and moves
4.8 of 6, which is over the "not maximum chaos" line.

**The station-0.40 family is the robust one.** The span-0.66 row buys its 100%
by changing the lab's *start*, which §4.4 declined to adopt; the phase-2π/3 row
depends on a single authored phase, which §4.6 showed is the least trustworthy
parameter here. Station 0.40's zero-loss result rests on 350 in-sample races
across seven configurations, and is confirmed out of sample in §4.10.

### 4.10 Out-of-sample confirmation

The station was chosen on seeds 1–50, so a reliability number measured on those
seeds is not a reliability number. Confirmation ran on **seeds 201–400** — a
block never used to select anything — at station 0.40, reach 0.56, against a
control at the same station. 200 seeds, 1200 racers per configuration.

| | 14° @ 3.2 | 10° @ 3.2 | 14° @ 2.4 | **bare control** |
|---|---|---|---|---|
| racers finishing | 99.83% | 99.83% | 99.67% | 99.83% |
| races with all six | **99.0%** | **99.0%** | 98.0% | 99.0% |
| escapes | **0.00%** | **0.00%** | 0.25% | 0.00% |
| racers left in the machine | 0.17% | 0.17% | 0.08% | 0.17% |
| **`corr1` losses** | **0 of 200** | **0 of 200** | 1 of 200 | 0 of 200 |
| corridor reorder | **99.0%** | 98.0% | 98.0% | 54.5% |
| corridor leader lost | **49.5%** | 48.5% | 55.5% | 8.5% |
| racers moved, of 6 | 4.30 | 4.25 | 4.51 | 1.42 |
| lead changes | 3.54 | 3.52 | 3.52 | 3.36 |
| mean comeback | 1.27 | 1.20 | 1.55 | 0.69 |
| median race | 6.17 s | 6.15 s | 5.98 s | 4.97 s |
| dead interval, mean / worst | 1.26 / **2.60** s | 1.22 / 2.32 s | 1.23 / 2.13 s | 1.12 / **3.18** s |
| slot correlation | +0.077 | +0.075 | −0.019 | +0.044 |
| slot rank spread | **1.38** | 1.34 | 0.74 | **3.09** |
| deepest arm/marble overlap | −0.179 sim | −0.180 | −0.188 | −0.00001 |

Everything holds, and several things sharpen:

- **The arm costs nothing in reliability.** 99.0% all six, identical to the
  empty course, with zero escapes over 1200 racers and **zero losses on the
  arm's own run in 200 races.** The two losses it does have are at `pan1`
  sample 45 and `pan2` sample 45, and the control loses the same seed-353 racer
  at the same sample.
- **The leader is punished on a near coin-flip: 49.5%**, against 8.5% on the
  empty corridor. That is the middle of the 25–75% band the gate asked for, and
  it is the number that says the outcome is uncertain before contact.
- **Rate matters more than amplitude even here.** 14° and 10° at rate 3.2 are
  within noise of each other on every column; dropping to rate 2.4 costs the
  one `corr1` escape and two sprint escapes.
- **The arm's worst dead interval is shorter than the empty course's** — 2.60 s
  against 3.18 s. A mechanism that reorders the field also gives the event
  timeline something to record.
- **The start bias is more than halved**, 3.09 → 1.38 of mean finishing rank,
  and the centre slot's win share falls from 48% to 38%.

## 5. Verdict against the acceptance criteria

### Reliable — **PASS**

99.0% of races finish all six, identical to the same course with the arm
removed, over 200 out-of-sample seeds. Zero escapes in 1200 racers. Zero racers
lost on the arm's own run in 200 races, against a diagnosed 2%-of-races loss at
the two late stations. The arm's deepest penetration of a marble is 0.179
simulation units — 0.36 of a marble radius — and peak travel per tick is 0.26
of a 0.50 budget, so there is no geometry instability and no tunnelling risk.
The energy invariant is asserted directly by test rather than read off the
disconnected `max_energy_rise` field.

Two reliability defects were found and both are now guarded in code rather than
documented: the arm must uncover the channel centreline (§4.8) and its axle
must clear the rail it hangs over (§1).

### Competitive — **PASS**

99% of races reorder the field's crossing order through the corridor, against
54.5% with the arm removed; 4.30 of 6 racers change their crossing position,
against 1.42. The leader is punished in 49.5% of races against 8.5%. Mean
comeback 1.27 places against 0.69. It does not preserve arrival order and it is
not a forced coin-toss in either direction.

It also does something it was not designed for: **it more than halves the lab
course's fixed-slot advantage**, 3.09 → 1.38 of mean finishing rank. The
project's own start-fairness work recorded that the only thing which reduced
that bias was building a second route, because a branch outcome is not a
function of start bay. Arrival phase is not either, and the pendulum buys the
same effect without a fork — which the Braid concept measured as the most
expensive drama per unit of geometry available.

### Understandable — **PASS, structurally**

Assessed from geometry, not rendering, as the brief directs:

- **Visible.** The arm is 1.97–2.39 layout units long — 3.5 to 4.2 marble
  diameters — and **51% of it, plus its axle, sits above the rail top**. Any
  camera that can see into the channel at all (21.5° of look-down here) sees the
  mechanism without a shot change.
- **Predictable state.** One actuator, one silhouette, and at these amplitudes
  the tip's height varies by 0.06 layout units across the whole swing. The only
  state to read is *where across the lane it is*, which is the simplest possible
  readable state, and the arm sweeps 56% of the channel so the open side is
  always visible.
- **Uncertain before contact.** The period is 1.96 s and the field crosses the
  corridor in 0.97 s, so the leader and the tail meet the arm 125° of cycle
  apart, and the leader is punished on a 49.5% coin-flip.
- **Understandable after contact.** The arm is the only thing in the corridor
  and every rank change is a visible collision with it or with a racer it
  stopped.

One reservation, and it is §4.6's: at this course the leading racer arrives
within 37° of the same point in the cycle on every seed, so *how hard the
leader is treated* is more sensitive to the authored phase than to the race.
That is a placement problem, not a mechanism problem, and it comes with a
testable P1 rule.

### Recommendation — **KEEP for course composition**

Pendulum Cross earns its screen time, at a named configuration and with two
named constraints.

**The configuration to compose with:**

| | value | why |
|---|---|---|
| station | at or before mid-run | 0 losses in 550 races at 0.20–0.50; 24 losses at 0.62–0.75 |
| reach | 0.56 of local half width | 0.46 and below approach the plug condition; above, the side gap falls under a marble |
| amplitude | 10°–24°, chosen for the silhouette | competitively inert; sweep speed varies 5% across a 2.5× change in arm length |
| rate | ≈ 2× the corridor transit (3.2 rad/s here) | the effect is a resonance and peaks there |
| phase | disclosed, never tuned per seed | it is an authored lever at this course, not a raced one |

**The two constraints, both now enforced in code:**

1. `centre_uncovered = L·sin(A) − depth/2` must be positive, and about half a
   marble radius of margin is where pinning stopped.
2. The axle must clear the rail, which caps the amplitude the channel will
   accept and ties it to the station.

**And the one that is not code, for P1:** stand the arm far enough from the next
seam that a racer launched by the pack it stops lands before that seam. The arm
*is* a pack gate at every reach a `W_LANE` corridor allows (§4.5); the queue is
where the reordering comes from and cannot be tuned away, so the consequence
has to be given room instead.

### What could not be validated here

- **Visual readability** is assessed structurally only. No render was made; P0
  is physics and the brief excludes final art.
- **The 18-second course.** Everything here is one mechanism on a 79-unit,
  6-second lab. Event density, dead intervals and arrival-time spread will all
  change when three other mechanisms sit upstream, and §4.6's phase sensitivity
  is expected to fall specifically because of that.
- **The lab course's own start bias.** Bay 1 averages 4.17 of 6 armed and 5.12
  bare and wins 3% of races. The stud span does not explain or fix it (§4.4),
  and five passive start topologies are already recorded as falsified. Nothing
  here is evidence about a *fair* six-racer start; it is evidence that the
  pendulum reduces an unfair one.
- **Whether station 0.40 is inherently safe.** 0.50 and 0.62 differ by 0.003 in
  side gap and by one racer in 50. The safety margin is positional, so the
  chosen station must be re-verified in the composed course rather than assumed.

---

## 6. Memory Rocker — architecture note

**Nothing here is implemented.** The question is: what is the smallest clean
change that would let a passive hinged rocker exist, whose angle changes
because racers physically load it?

### What the current contract is, and why it cannot hold one

`marble3d/modules/base.py` is explicit. An `Actuator`'s pose is
`pose_at(tick, dt)` — a pure function of an integer, "not of elapsed
wall-clock, not of an accumulated phase, not of the previous pose" — and the
bodies are mass zero, moved by `move_kinematic` rewriting their transform
between steps. Three properties follow: exact resume from any tick, no
floating-point phase drift, and evaluation without a physics world at all, so a
renderer can draw the moving parts straight from the replay.

The cost is stated in the same docstring: "an actuator cannot react". A Memory
Rocker is the reaction case. It is not a hard case because the physics is hard;
it is a hard case because a rocker's angle *is* run history, and the contract's
value is that nothing's pose is.

The same docstring also already names the answer:

> When they are [wanted], they should arrive as a **second kind**, explicitly
> non-reactive-free, with its state written into the replay per frame rather
> than derived from the tick; they must not arrive as an exception to this one,
> because the moment one mechanism's pose depends on run history, resuming from
> a replay stops being exact for the whole machine.

This note's contribution is to confirm that against the alternatives and say
what the change actually costs.

### The three candidates

**(A) A real hinge: a dynamic body on a revolute joint.** Give the rocker mass,
a joint axis across the channel, angle limits, pivot friction and optionally a
return spring. Racers load it, it tilts, the tilt persists and the next racer
meets it. The "memory" is the solver's, not a model's.

**(B) A kinematic body driven by an authored torque law.** Keep mass zero, read
the contacts each tick, integrate a hand-written load/damping model, write the
pose. Cheaper — no new body kind, no constraint, and a racer still meets a
predictable infinitely-heavy surface.

**(C) Scripted tilt by time.** A `LinearGate`-shaped ramp on a schedule.

**(C) is excluded by the Test #5 contract** (§3: no hidden gates that choose
outcomes independently of physics). It is the thing the current branch
deliberately did *not* do, and that judgement was right.

**(B) should be rejected, and for a reason worth writing down.** It breaks the
pure-pose contract exactly the way the base docstring forbids, *and* it does
not actually buy physical causation. A marble cannot load an infinitely heavy
plank — mass zero means contact transfers no momentum to the body — so the
"load" the torque law integrates would be a number the module invented from
contact positions. That is scripted physics wearing a physics costume, and it
is harder to defend than (C) because it looks defensible.

**(A) is the answer.** It is the only option where the rocker's angle is caused
by the racers rather than computed about them.

### The smallest clean change for (A)

The important finding is how little of it is new, because **the replay format
already supports a non-derived pose.** `MarbleSimulation.sample()` writes
`Frame.actuators` as `{"module.name": (position, rotation)}` per frame. Today
those values are computed from `pose_at`; nothing downstream knows or cares.
A hinge writes the same key from a *measured* transform. No schema change, no
renderer change, no replay migration.

Five changes, in dependency order:

1. **`marble3d/world.py`** — `add_hinged_box(half_extents, pose, axis, mass,
   limits, friction, …, owner=…)`. A two-link `createMultiBody` (mass-zero base
   at the pivot, one revolute link carrying the plank) with
   `jointLowerLimit`/`jointUpperLimit`, `changeDynamics(jointDamping=…)`, and
   `setJointMotorControl2(VELOCITY_CONTROL, targetVelocity=0, force=friction)`
   for pivot friction. Register it in `world.bodies` with a new
   `kind="hinged"`, which is the one intrusive bit: `_read_contacts` splits the
   worst overlap three ways by what the marble was touching and needs a fourth
   branch, or hinge contacts will be silently scored as track penetration.
2. **`marble3d/modules/base.py`** — `class Hinge`, a **sibling of `Actuator`,
   not a subclass**. It declares the joint frame, limits, mass, friction and a
   `rest_pose()`; it has no `pose_at`. `BuiltModule` gains `hinge_bodies` and a
   `read_hinges(world)` that *samples* the joint instead of writing it. Keeping
   them siblings is what preserves
   `test_every_actuator_pose_is_a_pure_function_of_the_tick` as a true
   statement about actuators.
3. **`Machine.build`** — create hinge bodies after colliders in declaration
   order, because "a machine assembled in a different order is a different
   run".
4. **`marble3d/simulation.py`** — `sample()` records each hinge's measured pose
   into the existing `Frame.actuators` dict. `_actuation_finishes` should treat
   a hinge as never settling, since the energy check's premise ("after this the
   only inputs are gravity and contact") is still true for a passive hinge but
   its pose keeps changing.
5. **`tests/test_race2_physics.py`** — add the complementary assertion: nothing
   anywhere writes a hinge's pose. The existing source scan for
   `resetBasePositionAndOrientation` in `race2/race.py` already covers half of
   it.

### What it costs, stated plainly

- **Exact mid-run resume is lost** for any machine carrying a hinge, unless the
  resume state is extended with each hinge's angle and angular velocity. The
  practical cost today is zero — nothing in this repository resumes mid-run;
  `run_race` always starts at tick 0 — but the *property* goes, and that is the
  thing the current contract was built to protect.
- **Run-to-run determinism survives, and should be proved rather than
  assumed.** A hinge's state is solver state, and PyBullet with
  `deterministicOverlappingPairs` and a fixed body order reproduces a run from
  tick 0. The first hinge should land with a determinism probe comparing two
  full runs of one seed, not with an argument.
- **A renderer with no physics engine still works**, because it reads the
  recorded pose. This is the property (B) would also have kept and (A) keeps
  for free.
- **Tuning is a real cost.** Mass, limits, friction and any return spring are
  four coupled numbers, and a rocker that does not return is a rocker whose
  memory is permanent. Expect a P0 of its own.

### One thing P0 cannot tell you about the rocker

The evidence in this document is about **arrival phase** — a mechanism whose
state is a function of time only. The rocker's claim is the opposite: that one
racer's interaction changes the state the *next* racer meets. None of the
measurements here transfer. The rocker needs its own control, and its own
control is harder to build, because the obvious one — the same course with the
hinge locked — is a different mechanism rather than an absent one.

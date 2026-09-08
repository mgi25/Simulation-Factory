# V1.8: the full-floor release, and the catch that turned out to be the start

**Status: built, and it is the best start this project has measured. The exit
rank span is 1.208 places against the shipped taper's 2.927 and V1.7's 2.200,
the slot correlation is −0.074, and the release delivers 100% of the field. It
is not clean: a penalty of about one place remains on the two centre bays, and
the measurement says that residual is the chamber's rather than the release's.
Sections 16 to 21 - orange, the remaining traps, the fresh benchmark, the seed,
the replay and the render - are gated on the start passing and are untouched.**

The shipped course is unchanged: `sloped.course.START_KIND` is still `"fan"`,
and `sloped.course.check()` reports zero findings. `floor` is reachable as
`start_module("floor", launch)` and as `StartPlan(start_kind="floor")`, off by
default.

---

## 1. Pre-release mixing: what the chamber actually erases

Section 2 asked for the field to be measured *inside* the chamber at the tick
before the release opens, and not inferred from exit statistics.
`sloped/chamberstate.py` and `tools/sloped_chamber_state.py` do that; the table
is `docs/validation/sloped_race_v1/v18/prerelease_trade.txt`.

The instrument reproduced V1.7's fixed-phase defect independently before being
trusted with anything new. V1.7 traced four parking bearings 90 degrees apart
one marble at a time; over 1536 racers the `bay -> blade sector` coefficient is
**0.529 with a fixed phase and 0.026 with the seed-derived one**, a twentyfold
difference in the one statistic that can see it.

Two findings the exit statistics could not have separated.

**The cyclic order is completely destroyed, and that is not enough.** Over
10752 bay triples, the cyclic order retained is 0.002 - indistinguishable from
a random cyclic permutation. The rotor really does break the necklace. But
every bay still has its own preferred arc of the chamber, at a per-bay bearing
concentration of 0.62 against a 0.064 noise floor, with the eight means spread
over 230 degrees. The field *as a whole* concentrates at only 0.253 - less than
any single bay - which is the signature that separates a shared preference,
which is fair, from eight separate ones, which is the sectoring five earlier
topologies died of.

Both are true at once and consistently so: a concentration of 0.62 is a
circular standard deviation of about 56 degrees and the bay means are about 33
degrees apart, so neighbouring bays overlap enough for their pairwise order to
be a coin flip while each keeps a strong absolute preference.

**Mixing duration does nothing at all.** From 1.19 revolutions to 7.16:

| mix | turns | bay→(x,z) | conc |
|---|---|---|---|
| 1.50 | 1.19 | 0.354 | 0.622 |
| 3.00 | 2.39 | 0.380 | – |
| 4.50 | 3.58 | 0.370 | 0.624 |
| 9.00 | 7.16 | 0.409 | 0.598 |

Six times the mixing changes nothing. `bay -> x` and `bay -> z` swing sign
while the *magnitude* of the vector they are the components of holds at 0.35 to
0.41. That is a bulk rotation, not a residual order — the rotor carries the
pattern round and a longer run turns it further without shrinking it.

The mechanism: a racer's transport angle is `rate * (stop_time - its own
arrival time)`, and the eight bays arrive at systematically different times
because they have different distances to travel across the apron. The bay is
written into the final bearing as an arrival-time **difference**, and a longer
run adds the same constant to everyone and cancels none of it.

### Section 3's second branch, and the three changes it justified

A strong systematic bay-to-position relationship remained, so three small
changes were made, each after the measurement that asked for it rather than by
scanning:

| | | |
|---|---|---|
| `SETTLE_SECONDS` 0.55 → 1.20 | at V1.7's 0.55 half the field was still moving - bays 0 to 3 at 0.81 to 1.34 layout units per second against bays 4 to 7 at 0.24 to 0.37 - and that residual energy carried the bay | `bay -> speed` −0.357 → −0.040 |
| the rotor **holds still** until the field is in | if the differential is in the residence time, remove the differential | `bay -> (x,z)` 0.406 → 0.302 |
| `MIX_SECONDS` 1.50 → 3.00 | once the residual is entry *position* rather than entry *time*, mixing bites; 4.50 is no better | → 0.218 |

Together: `bay -> (x,z)` 0.406 → 0.218 and the per-bay bearing concentration
0.62 → 0.36, with the cyclic order still broken. **Halved, and not zero.**

---

## 2. The full-floor release

`sloped/trapdoor.py`. There is no outlet, no gradient and no sweep: the floor
the whole field is standing on stops being there.

```
eight bays abreast on a flat pan, one synchronised gate   <- unchanged, seen
  |  a short apron, which may taper
a circular chamber 5.40 across, its floor FLAT AND LEVEL
  |  four paddles, held still until the field is in, then 2.39 turns
  |  the rotor stops, the field settles, the paddles rise clear
SIX FLOOR SLATS ROTATE DOWN TOGETHER, on one global clock
  |  every racer loses support at the same tick, wherever it stands
a cone on the chamber's own axis, 5.80 across
  |  through a 1.90 throat directly under the chamber's centre
the exit chute onto the launch run
```

**Why a louvre and not a shutter.** Section 5 requires the timing to depend on
the tick and the configuration only; section 4 requires every marble to lose
support at essentially the same time *regardless of where it sits*. The second
is the harder one, and it is what rules out the obvious mechanisms: a panel that
slides out from under the field uncovers the floor progressively from one side,
so its *timing* is global while its *effect* is a position-dependent sweep -
which is the selection being removed. A rotating slat has no such direction.

Eighteen boxes share six hinges and exactly **one** `(release, duration, sweep)`
triple; nothing in `FloorPanel` reads a position, an id, a bay or a rank.

**Removing the outlet removed three things with it**, each a simplification. The
chamber floor is now flat and level, because the 7-degree cone existed only to
persuade the field toward a hole and V1.7 measured that a floor steep enough to
deliver packs the field against the closed outlet and recreates the taper's own
centre bias. The rotor's blade clearance is one number (0.030 everywhere)
instead of two (0.030 at the tip, 0.208 at the root). The free radial travel is
the whole disc - 4.24 marble diameters - instead of 2.07 either side of a ring.

### The five defects, and which instrument found each

**The seam is `pitch − thickness`, not `pitch`, and it peaks at 90 degrees.** A
slat rotated by an angle has a horizontal footprint of `(t/2)sin + (w/2)cos`
about a centre at `offset·cos`, so the clear gap is `pitch(1−cos) −
thickness·sin` to 90 degrees and `pitch(1+cos) − thickness·sin` past it: beyond
90 the slat folds back over its own hinge, the hinge edge becomes its
downstream extreme, and the seam closes again. Built at a 120-degree sweep on a
closed form with the fold's sign wrong, the final seam measured **0.299 against
a predicted 1.070**. `tools/sloped_floor_check.py` walks the real box corners
every degree, which is what caught it. That single term set the slat count:

| slats | pitch | seam | diameters | |
|---|---|---|---|---|
| 8 | 0.675 | 0.575 | 1.01 | a marble rubs both sides |
| 7 | 0.771 | 0.671 | 1.18 | inside the band it can be held in |
| **6** | **0.900** | **0.800** | **1.40** | passes freely |
| 5 | 1.080 | 0.980 | 1.72 | and 0.18 more well depth |

**The well has to clear a marble standing on the dish, not the dish.** The
first build set the catch 0.16 below the slats' deepest sweep and the geometry
check reported a healthy +0.159 - to the *surface*. A marble resting on it
stands 0.285 higher, which put it 0.023 into the hanging plate. Six of fifteen
stage-A traces landed cleanly and then rolled back and forth along a slat's
face for five seconds. The well now carries a whole marble diameter, and the
check asks the question that matters instead of the one it was given.

**A stopped paddle is the third wall of a pocket.** Two racers of 96 were held
dead still at radius 2.412 against a free radius of 2.415, between the chamber
wall, the top edge of a hanging slat - a 0.10-wide horizontal ledge at the
hinge line, 0.05 below where the floor was - and a stopped blade beside them.
It was not reproducible from rest: eighteen stage-A marbles at the exact radius
limit at every 20 degrees of bearing all delivered. Two of the three walls are
structural, because a hinge stays where it is and so a hinged trapdoor always
leaves a fin. The blade is not, and with a full-floor release it has no further
job, so `Rotor.lift_at` raises the paddle assembly 0.68 clear during the settle.
`ShuffleChamber` keeps `ROTOR_LIFT = 0.0`, because V1.7's outlet does need its
blades where they are.

**The slats reach a long way outside the chamber while they move, and it is
inherent to an edge hinge.** At 90 degrees a slat has collapsed onto its own
hinge line while keeping its full half length, and the outermost slat's hinge
sits at the chamber's very edge where the chord is zero - so its corners swing
to radius **3.4435** against a 2.70 wall and a 2.90 catch rim. Harmless, for
exactly one reason, which is what the check now asserts rather than argues: a
marble's centre cannot exceed `R_WALL − MARBLE_RADIUS` = 2.415, so there is a
whole marble diameter of daylight between the reach and anywhere a marble can
be, and a kinematic box and a static shell generate no contact between them.
It is not harmless for the *render*, where slat corners visibly sweep through
the catch's rim, and that is issue 4 below.

**And the trace tool's own verdicts were wrong twice**, both times in the
direction that flatters or libels the mechanism. It called a marble 34 units
down leg1 "left the machine" because it was below the catch's lip, and a marble
stopped on the catch "still in the chamber" because it was above the catch's
rim. A second attempt at a containment threshold fired on every delivered
racer. There is now no escape column in that tool at all: containment needs the
run's own frame at the marble's own sample, so `StartTrial._containment` is what
answers it, and the trace reports the three states it can honestly see. This is
the fourth session in a row in which an instrument had to be corrected before
the geometry - see the memory note `instrument-bugs-hide-geometry-findings`.

### Throughput

Section 11's order, and nothing was run at 500 seeds before it passed at 12.

| stage | | |
|---|---|---|
| geometry | no findings | 5025 disc points covered, no seam narrows at any angle |
| A one marble | **33 of 33** | from 33 chamber positions, 18 at the radius limit |
| B eight marbles | **16 of 16** | released within 0.17s of one another |
| C the real field | **128 of 128** | 100.00% |
| D 96 seeds | 768 racers | 0 stuck, 0 unreleased, 14 lost downstream |

**The release's own contribution to the loss column is zero.** All fourteen
losses are containment on the launch and leg1: `leg1[70..89%]` ×8, which is the
pre-existing trap V1.7 recorded and the shipped fan has too, and
`launch[30..49%]` ×5, which are new and which the lift is why - a steeper feed
puts the field onto the launch's banked plunge faster, the mechanism V1.7 had
already measured on its own chute grade.

`START_LIFT` is re-derived at **3.93**, against V1.7's 2.14 and the radial
start's 4.30. Neither figure was assumed, as section 9 asks.

---

## 3. Start fairness, and the finding the session turns on

96 seeds each, same chamber, same downstream, same instrument.

| catch | delivered | exit span | **slot r** | **centre r** | lift |
|---|---|---|---|---|---|
| fan, as shipped (V1.3) | 99.35% | 2.927 | −0.387 | +0.574 | – |
| rotor + central outlet (V1.7) | 88.93% | 2.200 | −0.206 | −0.182 | 2.14 |
| floor + stadium dish, rim notch | 98.96% | 2.479 | +0.264 | +0.886 | 2.81 |
| **floor + cone on the axis** | **98.18%** | **1.208** | **−0.074** | −0.928 | 3.93 |

The release was built over the basin's stadium dish, which
`docs/sloped_race_v13_basin.md` measured as draining all eight marbles every
seed with no jam. It delivered, and it produced a centre-versus-rank
correlation of **+0.886** - worse than the taper it was meant to beat. That is
the session's main finding, and it generalises:

> A catch with one exit orders the field by path length to that exit. So a
> position-independent release does not remove the selection - it **moves** it
> to the catch, and the statistic that then decides the race is "how far from
> the exit was this marble when the floor went". The catch's exit therefore has
> to sit wherever the mixing has actually equalised the field.

The pre-release table says where that is. With the paddles stopped,
`bay -> radius` is −0.065 and `|bay−3.5| -> radius` is −0.202, while the
bearing still carries the bay at a concentration of 0.358 against a 0.090 noise
floor. Distance to a point **on the chamber's axis** is the radius. Distance to
a notch on the rim is a function of radius *and* bearing, so it reads back the
one thing the chamber did not erase - amplified, because the notch sat 2.75
downstream of a chamber only 2.70 across, making the dominant term the bay's
residual z.

That is also, in hindsight, why V1.7's central outlet was the fairest catch
this tree has built. **Its problem was throughput and never fairness.**

Moving the exit onto the axis took the exit rank span from 2.479 to **1.208
places** - under half the shipped fan's 2.927 and well under V1.7's 2.200, the
best figure this project has measured - and the slot correlation from +0.264 to
**−0.074**, which is indistinguishable from none.

### What remains, and why the two numbers do not contradict each other

The centre correlation is −0.928 and the span is 1.208 places. A correlation
measures shape; a span measures size. Grouped by distance from the middle of
the pan:

| \|bay − 3.5\| | mean exit rank | |
|---|---|---|
| 0.5 | 5.172 | bays 3 and 4 |
| 1.5 | 4.589 | |
| 2.5 | 4.130 | |
| 3.5 | 4.110 | bays 0 and 7 |

**Six of the eight bays sit within 0.5 places of each other.** What is left is
a penalty of about one place on the two centre bays, and its seed is visible in
the chamber at the same sign: `|bay−3.5| -> drain distance` is −0.202 there.
Bays 3 and 4 are the only ones with no lateral distance to travel across the
apron, so they enter first and fastest, cross the chamber, come to rest
furthest from its axis - and an axial catch reads exactly that.

So the residual is the chamber's, not the release's and not the catch's
position. The full-area release is **not** falsified: it is confirmed as a
working mechanism and falsified only as a sufficient cure for start bias.

---

## 4. The replay carries the mechanism (section 10)

`MarbleSimulation.sample` already writes every actuator's composed world pose
per frame, keyed `module.actuator`, so nothing new was needed to export a
physical trapdoor - which is the whole point of `Actuator.pose_at` being a pure
function of the tick. Measured on a real run:

    actuator keys per frame   34      18 panels, 4 rotor blades, 8 bay paddles
    t = 5.19s  rotor0 y = +73.2898    before the lift
    t = 5.70s  rotor0 y = +74.4828    after it: +1.193 sim = 0.680 layout, exact
    t = 6.09s  panel0_0 quat 0.208    the floor still shut
    t = 6.20s  panel0_0 quat 0.374    mid sweep
    t = 6.33s  panel0_0 quat 0.692    ninety degrees, and it stays there

`FloorPanel.to_json` also writes the hinge, the axis, the two perpendiculars,
the offset, the sweep, the release time and the duration into the module
configuration, and `Rotor.to_json` writes its start, stop, spin-down and lift.
So a renderer can either read the per-frame poses or re-evaluate the closed
form, and **Godot does not simulate the trapdoor** - it displays transforms.

---

## 5. What was not reached, and why

Sections 16 to 21 are explicitly gated on the start passing, and the brief's
section 14 asks for throughput *and* for the original bay not to strongly
predict post-start order. The throughput is met on the release's own account
and the slot correlation is gone, but a clean one-place centre penalty is not
"no longer predicts". So the orange lead, the `leg1[80..99%]` and
`leg2[80..99%]` traps, the 600-race benchmark, the seed selection, the
determinism repeats, the authoritative replay and `real_race_v17.mp4` are
untouched, and V1.3's numbers remain the current baseline.

The two things a next session would do first, in this order:

1. **Install `floor` in the complete course and run fresh full-race statistics.**
   The 1.208-place span is an early-checkpoint proxy and the brief's target is a
   full-race win ratio. The proxy has improved 2.4× over the shipped fan; whether
   that clears 2.5 on win rate is a measurement nobody has taken.
2. **Attack the one-place centre penalty at its measured cause**, which is that
   bays 3 and 4 have no lateral distance to travel and so enter first. The three
   knobs section 3 allows are exhausted; the untested one is the rotor rate, and
   with a trapdoor a *fast* rotor is newly harmless - it centrifuges the field to
   a common radius, which is exactly the coordinate an axial catch reads. V1.7
   could not use that because centrifuging starved its outlet.

---

## 6. Tests

`tests/test_sloped_chamberstate.py` (19) pins each pre-release statistic against
a hand-constructed field whose answer is arithmetic, including the fact that
Mardia's coefficient tops out near 0.81 rather than 1.0 when the bays wrap a
full circle - so the measured 0.22 to 0.53 are fractions of 0.81.

`tests/test_sloped_trapdoor.py` (28) pins the release where the geometry check
found the defects: one release triple across eighteen boxes, a pose that is a
pure function of the tick and clamped at both ends, an angle that never jumps,
the seam's peak at 90 degrees and its monotonicity measured on real box
corners, full coverage of the disc, the well against a marble *standing on* the
catch, the throat on the axis and its height equal at every bearing, the
paddles clear before the floor opens, and the chute grade the lift is sized
from being the grade the chute gets.

`tools/sloped_floor_check.py` is the gate before any of it: coverage, the seams
degree by degree, panel-to-wall, a marble against the wall through the whole
sweep, the slats against a marble on the catch, the catch against the chamber's
footprint, the fall and its impact speed, and that the panels share one clock.

The full suite is 1540 passed, 1 failed, 1 skipped. The failure is
`test_neon_proof.py::test_a_missing_godot_is_reported_rather_than_raised`, which
predates this session and is unrelated - confirmed by stashing.

---

## 7. Remaining issues

1. **A one-place penalty on bays 3 and 4**, with the other six inside 0.5
   places. Measured to a cause - they are the only bays with no lateral travel
   across the apron - and the untested lever is the rotor rate, which a
   trapdoor makes newly usable.
2. **The lift costs five launch escapes.** 3.93 against V1.7's 2.14 feeds the
   banked plunge faster; `launch[30..49%]` ×5 of 768 are new. The mechanism is
   V1.7's own measured chute-grade trade and the repair is local.
3. **`leg1[70..89%]` still loses eight racers in 768**, in every configuration
   measured here, in V1.6 and V1.7, and in the shipped taper. It is the
   pre-existing trap section 18 owns and nothing in this session touched it.

And one that is not a physics issue but will be visible the moment anything is
rendered: **the slats sweep 0.54 outside the catch's rim** on their way to 90
degrees, so the mechanism needs a shroud rather than a geometry change. The
reach is measured, bounded and asserted; the render is gated behind the start
passing in any case.

# The mixing basin, built and falsified

Section 25 asks that if the shared basin is falsified by careful measurement,
the mechanism of failure be reported rather than dozens of variations scanned.
It was, and this is it.

The basin is **built, working and in the tree**. All eight marbles drain, every
seed, with no jam. It is switched off because it is measurably worse than the
taper it was meant to replace.

---

## 1. What was built

Exactly the architecture the brief specified:

    8 BAYS on a flat shelf     unchanged, and unchanged to look at
      |  one wide flat ramp     same drop, same angle, same distance for all
      v
    BASIN                       a shallow stadium dish, 5.5 x 3.5 layout units
      |  one notch in the rim   the whole field converges on one exit
      v
    CHUTE                       to the launch entry

`START_LIFT` raises the start deck 1.90 layout units - the local macro-layout
adjustment the brief allows - because V1.2's start had 0.63 units of drop
between the gate and the launch and a basin with nothing to spend is a basin
the field settles in.

Two fairness properties were built in deliberately, and both are real:

* **The feed is congruent.** One flat ramp, so every marble reaches the basin
  with the same speed and heading, differing only in where along the basin's
  edge it arrives. No bay's position buys it speed or distance.
* **The shelf's pan is flat.** The taper's trough is a dish, `-0.30 + 0.16 u^2`,
  so its outer bays rest 0.10 layout units *higher* than its inner ones and
  start with more potential energy. That was a systematic per-bay difference
  sitting underneath three sessions of measurement, and the basin does not have
  it.

---

## 2. What it cost to get it working

Seven distinct geometry defects, each found by tracing marbles rather than by
reading the code, and each worth recording because the next person building a
station out of strips will hit them:

| defect | symptom |
|---|---|
| shelf at 0.9 degrees | nothing rolled off it; all eight sat past the lifted gate |
| feeder mouths 0.098 above the shelf floor | a step marbles crawling at 1 wu/s stopped against |
| feeder cradle radius 0.225 < marble radius 0.285 | marbles wedged between its walls, four fifths along |
| ramp wider than the basin | outer marbles arrived beside it and fell past its walls |
| rim wall built across the ramp's mouth | the field ran down and hit it; all eight, every trial |
| dish level at the drain | eight marbles built a static arch over the hole and stopped |
| chute walls 0.4 above the dish floor | a wall across the basin; three marbles piled behind it |

The under-dish drain was abandoned for a notch in the downstream rim after the
fourth of these: a central hole needs a throat, a tunnel and a roof, and each
was a defect in turn. A spillway is the same idea with none of that.

---

## 3. Why it is switched off

100 seeds of the real course, blue route, every other correction identical:

| start | finish | win ratio | win spread |
|---|---|---|---|
| **taper (shipped)** | **0.985** | **11.50** | 21.0 points |
| basin | 0.968 | 29.00 | 28.0 points |
| basin + central island | 0.965 | 16.00 | 30.0 points |

Win rate by bay:

    taper           2.0   5.0  23.0  19.0  16.0  12.0  14.0   9.0
    basin           1.0   1.0  13.0  12.0  29.0  28.0  14.0   2.0
    basin + island  3.0   8.0  23.0   2.0   2.0  32.0  23.0   7.0

The basin's row is the same shape as the taper's: a centre-heavy V, outer bays
last. The island does not flatten it - it *relabels* it, moving the advantage
from bays 4 and 5 to bays 5 and 6 while leaving the spread where it was.

---

## 4. The mechanism

**A single common exit orders the field by distance to that exit, and distance
to the exit is a function of which bay a marble started in.**

That is the same sentence as V1.2's finding about the taper, and the basin is
what proves it is about the *exit* rather than about the taper. The basin gives
the field everything the brief asked for - room for all eight abreast, physical
collisions, a wide shallow floor, no immediate single-file funnel - and none of
it matters, because the ordering is not created inside the basin. It is created
at the notch, where eight marbles that entered spread across 5.5 units have to
leave through one 1.9-unit gap, and the ones that entered nearest the gap reach
it first.

Room to mill is not a reason to mill. A marble crossing a dish toward an exit
travels in a straight line; it mills only if something makes it, and the things
that make it - an island, bumpers, a deeper bowl - either perturb which bays
win without narrowing the spread, or cost reliability.

**What would actually break it** is paths of equal length from every bay to the
exit, which means the bays arranged symmetrically *about* the exit rather than
on a line beside it - eight feeds around a ring, draining at its centre. That
is not a local adjustment to the start: it is a different start, and the eight
racers would no longer be side by side, which section 3 requires them to be.

Twenty-four geometries have now been measured across three sessions - staggers,
fin schedules, merge trees, deflector rows, wheel positions and rates, wide
trays, bumper sets, launch openings, and now a basin, a basin with an island
and a basin with a bigger island. The finding has not changed and is not, on
this evidence, a matter of not having found the right shape yet.

---

## 5. What is kept

`sloped.basin` stays in the tree and `sloped.course.START_KIND` switches to it
in one line. It is the only clean test of the claim above in a second topology,
and if the start presentation is ever allowed to change, the basin is most of
the work already done - it needs a feed arranged around it rather than beside
it.

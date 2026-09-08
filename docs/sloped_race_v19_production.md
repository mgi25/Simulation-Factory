# V1.9: the physics lock — the frozen start, the rails, and what orange costs

**Status: the V1 start is frozen and installed, the start-lift escapes are
fixed, and orange is falsified as a V1 route for a reason that is not the one
the brief expected. Numbers below are measured on the shipped configuration.**

`sloped.course.START_KIND` is now `"floor"`. `course.check()` and
`contract.check()` both report zero findings.

---

## 1. The frozen start, installed

`sloped.trapdoor.ShuffleFloor` — the rotor chamber with a full-floor louvre
release and a catch cone on the chamber's own axis, at 13 rad/s with the rotor
held for entry, 3.00 of mixing and a 1.20 settle. The architecture and the two
findings behind it are `docs/sloped_race_v18_floor.md`; nothing in this session
changed the mixer or the release.

Against the taper it replaces, in one instrument over 96 seeds each:

| start | delivered | exit span | slot r | centre r | **slot-mean sd** |
|---|---|---|---|---|---|
| fan, as shipped | 99.349% | 2.927 | −0.387 | +0.574 | **0.863** |
| floor, as frozen | 98.307% | 1.177 | +0.378 | −0.090 | **0.376** |

The decision was taken on the last column, and the reason it is the last column
rather than either correlation is that **the two correlations disagreed about
which start was fairer and each was measuring its own shape** — a centre bias
at 5 rad/s, a west-to-east one at 13, with the same span either way. The
standard deviation of the eight slot means privileges no shape.

---

## 2. The start-lift escapes, and leg1's trap with them (sections 1 and 4)

One correction does both, and it is the first thing on the brief's own list.
`docs/validation/sloped_race_v1/v19/guard_boosts.txt` has the whole table.

**What the escapes are.** All twelve were 31 to 46 per cent of a half width
outside the channel with their centres near the 0.800 containment, at 18 to 29
layout units per second with 3 to 9 of that lateral — and **every vertical
speed was negative**. They had gone over the top of the rail and were falling
outside it. The worst height any racer reached was 1.510, nearly double the
rail.

The instrument's first verdict labels said the opposite. They read "over the
guard" only when the *vertical* test fired, and the vertical slack is a whole
marble diameter, so eleven of twelve were labelled "outside the wall" while
their centres were above the rail and 0.3 outside its face.

**What it is not.** `tools/sloped_continuity_check.py` audits the chain for
every defect section 4 names and rules three out: each join has a zero
centreline gap, a zero floor step and a zero bank step, and no run has a grade
break over 8 degrees anywhere. What it finds is a 12.1-degree tangent break at
leg2[88] with a 1.77 turn radius under 22 degrees of bank, and 6.6 at leg1[92].

Its own first speed model was wrong and had to be replaced: it took
`tan(bank + wall)` with the sum clamped at 89 degrees, so a positive bank put
the argument at the clamp, `tan(89)` made almost any turn look able to hold
anything, and leg1 reported zero tight samples while marbles were demonstrably
leaving it. It also added the bank to the wall without checking which way the
corner turned. Rewritten to walk the channel's own profile outward with the
bank's sign taken from the turn, it says the channel holds 27 units/s **in
equilibrium** everywhere — so the escapes are dynamic, marbles climbing past
equilibrium on lateral velocity they got from each other in a clump.

**The lever that is falsified.** The launch site is the one the frozen start
created: its axial catch delivers the field to launch[0] with 4.26 of drop
behind it against the fan's 0.59, so it arrives as a clump at about three times
the speed, and the fan loses **zero** racers there. So less arrival energy was
tried first — a shallower exit chute and catch cone, which also lowers the
lift — and it fails totally:

| chute | cone | lift | field falls | delivered | escapes |
|---|---|---|---|---|---|
| 17 | 14 | 3.929 | 4.259 | 99.87% | 12 |
| 11 | 9 | 3.224 | 3.554 | **0.00%** | 0 — 768 stopped in the chute |
| 8 | 6 | 2.865 | 3.195 | **0.00%** | 0 — 768 stopped in the chute |

Below about 15 degrees the clump stacks in the chute and none of 768 racers
ever reaches a run. That is V1.7's own measured floor, confirmed at the higher
arrival speed rather than assumed to have moved. **The lift is what the
architecture costs.**

**The correction.** The centreline, the widths, the drops and the bank extremes
are all pinned by `sloped.contract` against the drawn asset, so none is
available. The rail's height is not pinned, and it is the surface the marbles
are demonstrably clearing. `TrackRun.guard_boost` is a smoothstepped window
raising only the points above the lip's crown — the lip and the cradle, which
are the running surface, are left exactly as drawn:

| configuration | escapes | rate | launch | leg1 |
|---|---|---|---|---|
| authored 0.26 rail | 12 | 1.562% | 7 | 5 |
| +0.34, narrower windows | 6 | 0.781% | 4 | 2 |
| **+0.50, shipped windows** | **1** | **0.130%** | 1 | **0** |

The containment check had to move with the collider: `run.containment` is a
scalar and the boost is per sample, so a check reading the scalar would book a
contained marble as an escape and the histogram would say the repair had done
nothing. Both `sloped.race` and `sloped.startlab` read `containment_at` now.

**And the render carries the same rails.** `v2_track.gd` grows an additive
`guard_boost` option and `course_machine.gd` passes the same three windows.
Additive so every existing build still gets the authored rail and the earlier
labs' committed frames still reproduce. `tests/test_sloped_guards.py` parses the
GDScript constant and compares it to `sloped.course.GUARD_BOOSTS` number for
number, because the alternative is a third file neither tree can import.

---

## 3. Orange (sections 2 and 3)

**The transition the brief asked for is already built, and it measures exact.**
`sloped.joins.fork_mouth` reads leg3's east lip through `surface_point` — the
same expression `ring_points` uses, so it is a point the collider has a vertex
at rather than one near it — lifts it by the channel's own `FLOOR_Y` so the
lead's *floor* lands on the lip rather than its centreline, holds the lip's own
chord grade over the shared window, and takes leg3's roll from the built run:

| lead sample | lead floor | leg3 east lip | floor step | lateral gap |
|---|---|---|---|---|
| 0 | 12.6562 | 12.6612 | **−0.0050** | **0.0160** |
| 4 | 12.3694 | 12.3967 | −0.0273 | 0.2371 |
| 8 | 12.0787 | 12.1472 | −0.0685 | 0.7687 |

Five thousandths of a floor step against a marble 0.570 across. And the lead's
own geometry is sound: worst turn radius 14.1, a marble at 30 units/s rides to
0.250 against a 0.800 rail, and its `bank_gain = 0.0` is a prior measured
decision — reversing leg3's +26 to the lead's own −17 is what the sign change
damages.

So finishing it changes nothing, because **the blocker is sorting**. Isolated,
4 speeds by 7 lateral offsets, every marble goes blue:

```
sorted to: {'blue': 28, 'orange': 0}, unrouted 0
orange: no entries - the fork never sorted a marble onto it
```

Launched as a field, 1 of 28 sorts orange and leaves at `orange_lead[15]` while
6 stop in leg3's hairpin from congestion. The ~35.8% orange usage the full race
shows is traffic pushing marbles east, not the fork sorting them — and 47.1% of
them finish, which is the brief's own figure reproduced.

What decides it is the ridge's crest line, and moving marbles relative to it
means changing the divider or the guard window: the full-split redesign section
2 excludes, and which the course's own history already records six failed
configurations of, with the conclusion "no configuration ever put a marble on
the orange lobe and got it to the finish."

**Orange stays off. `routes="blue"` remains the default and the shipped
course is the through route.** `docs/validation/sloped_race_v1/v19/orange_sorting.txt`
has the whole measurement, including two instrument errors of mine that each
produced a confident wrong mechanism first — an unwindowed nearest-sample
search across leg3's hairpin, and a bare `MarbleSimulation`, which does not
apply the injector's velocity, so a trial measured a marble dropped from rest.

---

## 4. Racer identity is not tied to a bay (section 7)

Already in place and now pinned. `marble3d.seeds.make_order_rng` permutes which
marble id stands in which physical slot, per seed, at spawn.
`tests/test_sloped_identity.py` asserts the four properties the brief asks for:
deterministic from the seed and a permutation rather than a sample; over 800
seeds every marble stands in every bay within 40% of an even share; fixed
before the first tick so it cannot read anything about the race; and
recoverable from the replay alone through `MarbleInfo.start_index`, which is
also what makes the per-bay characterisation a fact about geometry.

The consequence matters more than the mechanism: the frozen start still leaves
about 1.2 places between the eight bays, and bay 3 being a tenth of a place
quicker is a curiosity where red winning a third of every race for a year is a
broken product.

One real property found while pinning it: `_spawn` truncates the slot list to
the marble count *before* shuffling, so a three-marble debug run is a
permutation of 0..2 and not the first three of the eight-marble one.

---

## 5. Instruments added

| tool | what it answers |
|---|---|
| `tools/sloped_escape_trace.py` | how a racer left the start lab — over a rail, through a gap, or already outside — with the reach, the height against that sample's own containment, and the lateral and vertical speed |
| `tools/sloped_continuity_check.py` | the local defects section 4 names, per sample: turn radius and the height a marble rides to, tangent breaks, bank rate, grade breaks, and the floor step at every join |
| `tools/sloped_race_escapes.py` | the same as the first, on the whole route rather than the launch and leg1 |

All three are gates before a simulation rather than reports after one, and each
was wrong at least once before it was right — recorded in the files that carry
them, and the fourth session running in which an instrument had to be corrected
before the geometry could be judged.

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

---

## 6. The production benchmark (section 5)

**600 fresh races, 4,800 racers, the shipped blue route with the frozen start.**
`docs/validation/sloped_race_v1/v19/production_blue_600.json`.

| | measured | target |
|---|---|---|
| per-racer finish | **98.83%** | ≥99% — 0.17 points short |
| all-eight races | **91.0%** | ≥90% — met |
| escapes | **0.25%** | near zero — met |
| stuck | 0.92% | near zero — the dominant remaining loss |

Every non-finisher, by site: **`leg2[99]` ×41 stuck**, `final[8..14]` ×8
escaped, `blue[9..12]` ×2 escaped, `blue[112]` ×2 stuck, `leg2[108]` ×1,
`leg1` ×1. So 41 of 56 are one sample of one run, and they **stall** rather
than leave. The loss-site histogram buckets by decile and had been reporting
that as `leg2[80]`, which is why it took an A/B to find.

---

## 7. Start fairness on full races (section 6)

Per physical bay, 600 starts each. This is a characterisation, not an
optimisation loop.

| bay | win % | podium % | finish % | rank @9% | @half | @¾ | final rank |
|---|---|---|---|---|---|---|---|
| 0 | 18.00 | 43.17 | 98.50 | 3.918 | 4.132 | 4.237 | 4.164 |
| 1 | **21.83** | **49.00** | 98.50 | 3.527 | 3.817 | 3.953 | **3.931** |
| 2 | 6.17 | 29.17 | 99.17 | 5.425 | 4.895 | 4.877 | 4.834 |
| 3 | 10.50 | 36.00 | 98.83 | 4.892 | 4.615 | 4.643 | 4.616 |
| 4 | 13.00 | 39.67 | 99.17 | 4.423 | 4.450 | 4.407 | 4.371 |
| 5 | **4.33** | **23.50** | 98.33 | 5.622 | 5.247 | 5.160 | **5.092** |
| 6 | 12.17 | 37.33 | 98.83 | 4.502 | 4.550 | 4.507 | 4.462 |
| 7 | 14.00 | 42.17 | 99.33 | 3.692 | 4.295 | 4.217 | 4.205 |

| statistic | value | |
|---|---|---|
| **win-rate ratio** | **5.04** | against the ≤2.5 target — **missed** |
| podium-rate ratio | 2.09 | inside 2.5 |
| slot-mean rank SD | **0.354** | against the isolated start's 0.376 |
| slot-mean rank span | 1.161 | against the isolated start's 1.177 |
| slot/rank correlation | +0.267 | |
| centre bias | −0.535 | |
| Spearman(slot, finish rate) | +0.041 | |
| win-rate spread | 17.5 points | 4.33% to 21.83% |

**The one thing section 6 asked to be checked is answered: the full-race result
is not dramatically worse than the isolated-start result. It is marginally
better** — SD 0.354 against 0.376, span 1.161 against 1.177. The start's bias
is transmitted, not amplified. The per-checkpoint columns show it *decaying*:
the span is 2.095 places at the 9% mark and 1.161 at the finish, so the course
dilutes what the start hands it.

**The win ratio misses its target and is reported as a miss.** It is also the
wrong single number, which is why all four statistics are above rather than
one: a win is a tail event, and a 1.16-place shift in mean rank barely moves
the middle of the distribution while moving P(rank 1) a great deal. The podium
ratio over the same races is 2.09 and inside target. Slot 1 is 6.9 sigma above
the expected 12.5% win rate and slot 5 is 6.1 sigma below, so the effect is
real and not sampling noise — it is the same ~1.2-place residual V1.8 measured,
seen through a tail.

---

## 8. Routes (sections 2 and 3)

The shipped course is the through route, so the production benchmark is 100%
blue at 98.8% completion. Orange's numbers come from the 12-race both-routes
probe and the isolated split sweep, and the mechanism is in section 3 above:

| | usage | completion |
|---|---|---|
| blue, 600 races | 100% | 98.83% |
| blue, both-routes probe | 64.2% | 90.2% |
| orange, both-routes probe | 35.8% | **47.1%** |
| orange, isolated sweep | **0 of 28** | — |

Orange misses the ≥95% target and is a V1 limitation. Turning both routes on
also costs the whole course: finish 74%, escape 23%, all-eight 8%.

---

## 9. Entertainment (section 9)

600 races.

| | mean | median |
|---|---|---|
| lead changes | 4.19 | |
| overtakes | 35.41 | |
| winner lock fraction | 0.226 | 0.236 |
| winner's worst rank | 1.878 | |
| final margin | 0.567 s | 0.517 s |
| collisions per race | 104.6 | |
| top speed | 64.6 | |

Not measured over the 600: **competitive pack size and top-3 turnover.**
Turnover is computed per race inside the seed scorer — it is 1.0 for every
shortlisted seed — but is not aggregated across the benchmark, and pack size
has no instrument at all. Both are gaps rather than results.

---

## 10. The selected seed (section 10)

**Seed 182**, from 546 eligible races.

| | |
|---|---|
| all eight finish | yes, 0 escaped, 0 jammed |
| lead changes | 10 |
| overtakes | 41 |
| final margin | 0.4667 s |
| winner lock | 0.4825 — the winner settles only at halfway |
| winner's worst rank | 5 — a real comeback |
| top-3 turnover term | 1.0 |
| winner | marble 4 from **slot 1**, 20.217 s |
| contact validation | **no findings** |

**It was picked over the top-scoring seed on physics cleanliness rather than on
score.** Seed 130 scored higher (3.513 against 3.371) and had the closer finish
(0.25 s), but its contact validation reported four floating findings with a
worst resting gap of **0.3799** — a marble visibly hovering above the track.
Seed 27 was worse again at 0.7414. Seed 182 has zero findings and a worst gap
of 0.0280. For the video that *is* the physics lock, a clean contact validation
outranks a tenth of a point of entertainment score.

That comparison also settled a question about my own work: the floating is
**seed-dependent, not an artifact of the raised rails**.

What was traded away, stated plainly: 130's winner came from slot 5, the
weakest bay by win rate, where 182's comes from slot 1, the strongest. A single
race cannot show a win-rate distribution, so "no visually obvious start-slot
domination" is weakly served either way — but 182 is the less flattering pick
on that axis and it was still the right one.

---

## 11. Determinism (section 11)

Seed 182's race was re-run through the integration pipeline and its state and
event digests match the benchmark's exactly, so the authoritative replay is the
race that was measured.

Seed 130, 20 runs in one process, 20 in fresh processes, and the two sets
against each other — **identical on every compared key**:

```
state      27a6b6b1c2b0cd21d796afe9883122d1a75bf6a4bcf099d9ba9c67e684d553e1
events     f428ca8bfaf287b8a16ad26dcc32ab2bff6d46ec6bf796ec115021840bdf8d88
actuators  0c5d4b64fdb6be9105eeacf9f9648dbf417951c3b3cbaca8f51452afb33bf2a5
order      [1, 5, 3, 4, 6, 7, 2, 0]
```

with the finish times, the route and the start slot of every racer compared too.

**The check had a hole and it is now closed.** `Replay.digest()` hashes marble
position, orientation, velocity and spin — and nothing else — so the machine's
own moving parts were not covered, and a replay whose marbles agreed while a
gate, a paddle or a floor slat had moved differently would have compared as
identical. Harmless when the only actuators were eight start gates on a fixed
clock; not harmless now that the start carries a seed-derived rotor phase and
eighteen sweeping slats. `Replay.actuator_digest()` covers them, keyed by name
and sorted, and it was verified to discriminate rather than assumed to: two
replays with identical marbles and one panel moved differently agree on
`digest` and differ on the new one.

Cross-machine determinism is **not tested** — one machine was available. The
environment block in the JSON is what a second machine's report would be
diffed against.

---

## 12. The video (section 12)

`output/sloped_race_v1/real_race_final_physics.mp4`

| | |
|---|---|
| resolution | 1080 × 1920 |
| frame rate | 60/1 |
| codec | h264, yuv420p |
| audio streams | **0** |
| frames | 1515 |
| duration | 25.25 s |
| size | 32.3 MiB |

Rendered from the authoritative replay through Godot, which plays it back and
simulates nothing. Eleven camera cuts covering the visible start, the descent,
the long track, the hairpin, the obstacle, the split, the branch, the merge and
the finish.

**The framing is weak on at least two cuts and that is not fixed here.** The
camera solver reports one finding — "merge: the aim is 7.7 layout units from
the nearest racer, so it is not following the field" — and the rendered frame
confirms it: at t=20 s the frame is track structure and support columns with
the marbles at the edges. Section 21 says only minor adjustments and explicitly
defers the cinematic camera director, so this is reported rather than chased.
The video's job here is to be the physics lock.

---

## 13. Tests

The full suite is **1,579 passed, 1 failed, 1 skipped**. The failure is
`test_neon_proof.py::test_a_missing_godot_is_reported_rather_than_raised`,
which needs a gitignored render output, predates this session and is unrelated.

Three tests failed on the first full run *because the ship decision moved*, and
all three were right to. `tests/test_sloped_shuffle.py`,
`tests/test_sloped_widelaunch.py` and `tests/test_sloped_trapdoor.py` each
asserted `START_KIND == "fan"`, written when the file in question was adding a
*candidate* topology and the point was that adding one must not silently change
what races. Freezing `floor` in by instruction is exactly the change they exist
to notice.

They now state the invariant rather than spell a literal that goes stale the
next time the decision moves: the rotor chamber and the wide launch each assert
that the shipped kind is *not* the kind under test, and the floor start's own
file is the single place that pins what does ship - the name, the registered
class, and the class the course actually builds, because V1.4 lost a 300-seed
baseline to a start whose name and geometry disagreed. A second test pins the
four numbers the frozen configuration was chosen on (13 rad/s, held for entry,
3.00 mixing, 1.20 settle), because the choice rests on a measurement and a
silent drift in any of them would invalidate it without failing anything else.

New this session: `tests/test_sloped_guards.py` (9) for the rail-boost window,
including parsing the GDScript constant to check the render carries the same
table, and `tests/test_sloped_identity.py` (9) for the racer/slot decoupling.

---

## 14. Known V1 limitations

1. **Orange is not a viable route.** 47.1% completion in traffic and 0 of 28
   in isolation. The transition is exact and the lead's geometry is sound; the
   blocker is that nothing sorts a marble east of the fork's ridge, which needs
   the divider or the guard window and is excluded from this session. Seven
   configurations have now failed on it.
2. **`leg2[99]` stalls 41 racers in 4,800** — 0.85%, and three quarters of all
   non-finishers. It has no mechanism yet: the rail boost there was the
   candidate cause and a 100-race A/B put every difference inside its own 95%
   interval, so the boost is neither the cause nor shown to be harmless.
   Per-racer finish is 98.83% against a 99% target because of it.
3. **About 1.2 places of start bias remain**, showing as a 5.04 win-rate ratio
   against a ≤2.5 target. The underlying residual is unchanged from the frozen
   start's own measurement and is *diluted* rather than amplified by the
   course; it is a bearing residual that no amount of rotor removes, and it is
   deferred to V2 by instruction.

Three smaller things, recorded rather than fixed:

* `max_travel_per_tick` reached **0.53335** against the config's 0.5 travel
  budget, and `worst_penetration` **−1.0396** simulation units over 600 races.
  Both are single-worst-case figures across 4,800 racers and neither produced a
  containment failure, but both exceed the thresholds `marble3d.config` sets
  for itself and neither has been traced to a site.
* `course_machine.gd` builds run nodes with `name.capitalize()` — which turns
  `orange_lead` into `Orange Lead` — and looks them up with `to_lower()`, so
  the two `*_lead` runs fall back to the wrong spec and their support columns
  are misplaced. **Pre-existing**, verified against `HEAD~6`, and left alone
  because it is the drawn course's geometry.
* Competitive pack size and top-3 turnover are not aggregated over the
  benchmark. See section 9.

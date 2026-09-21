# Category 3, Test #1 — HIT EVERY TILE TO ESCAPE — Phase 1: core physics prototype

**Status:** Phase 1 complete. Prototype only; not a production candidate, not merged.
**Branch:** `category3-tile-escape-v1`
**Base:** `main` at `65df08a` (`project-factory-pre-media-loop-final-v1`)
**Worktree:** `projects/wt-category3-tile-escape`
**Date:** 2026-09-21

---

## 1. The question Phase 1 was asked

> Does a ball bouncing inside a segmented arena create a readable and technically
> reliable "activate every tile" simulation?

**Answer: yes on readability, yes on reliability, no on pacing as configured.**

- The arena reads as the progress bar. A dark tile and a lit tile are
  unmistakable at 1080x1920, and the number of remaining dark tiles is
  countable at a glance without a UI bar.
- The physics is exact rather than merely stable. There is no fixed step, so
  tunnelling is not possible; measured wall excursion is `1.8e-15` world units,
  which is floating-point noise, and energy drift is `0.0` in the zero-gravity
  configuration.
- Completion is reliable: 299 of 300 seeds finish in the recommended
  configuration.
- Completion is **too slow and too variable**: median 33 s but p90 58 s and a
  worst case of 482 s in the best configuration measured. That is the Phase 2
  pacing problem the brief anticipated, and it is stated here as a measurement
  rather than patched with trajectory assistance.

One genuine pathology was found, and it is a geometry problem rather than a
solver problem. See section 7.

---

## 2. Repository and isolation

| | |
|---|---|
| Baseline branch | `main` |
| Baseline SHA | `65df08a3e22d692d2783ab6004ce6f3d4046f54e` |
| New branch | `category3-tile-escape-v1` |
| Worktree | `C:/Users/mgial/OneDrive/Documents/projects/wt-category3-tile-escape` |

Nothing else was touched. Category 1 (`engine/`, `entities/`, `modes/`,
`powers/`), Category 2 (`race/`, `race2/`, `sloped/`, `marble3d/`, `godot/`),
Company OS (`company/`, `ai_platform/`, `intelligence/`, `knowledge/`) and Ball
Race Test Video 5 are untouched, and two tests assert the boundary rather than
asserting it in prose:

- `test_category_three_imports_no_other_category_and_no_company_os` walks every
  `satisfying/*.py` with `ast` and allows only the standard library, Pillow and
  `satisfying` itself.
- `test_no_other_category_imports_category_three` walks every `.py` under the
  sixteen other subsystem roots and asserts none of them imports `satisfying`.
  (By import, not by substring: "satisfying" is also an ordinary English word
  and several race modules use it in prose.)

### 2.1 Why the driver is not in `tools/`

Every other simulation here puts its CLI in `tools/`, and this one would too
except that `tools/` is a declared production root. Three Company OS tests —
the `test_this_branch_changed_no_race_fight_or_v30_code` guards in
`tests/test_company_os_research.py`, `..._batches.py` and `..._ingestion.py` —
refuse **any** file added under a production root that is not on their
two-entry additive allowlist (`tools/youtube_fetch/`,
`tools/engineering_runner/`). Landing a driver in `tools/` would turn three
green Company OS tests red on this branch, and widening the allowlist means
editing Company OS tests from a Category 3 branch, which this workstream is not
allowed to do.

So the driver is `satisfying/tile_escape_cli.py`, run as
`python -m satisfying.tile_escape_cli`. **This is a deliberate deviation from
repository convention and a decision to hand back:** if the owners of those
guards add a Category 3 entry to `_ADDITIVE_PRODUCTION_PATHS`, the module moves
to `tools/tile_escape_run.py` unchanged.

---

## 3. Architecture

### Files created

| File | Lines | What it is |
|---|---|---|
| `satisfying/__init__.py` | 36 | Category 3 package root; states the isolation rule |
| `satisfying/seeds.py` | 67 | Two salted `random.Random` streams, per `marble3d.seeds` convention |
| `satisfying/tile_arena.py` | 244 | The polygon, its sides, its tiles. Geometry only |
| `satisfying/tile_escape.py` | 634 | Ball, collisions, activation ledger, instruments |
| `satisfying/tile_render.py` | 226 | 9:16 stills via Pillow |
| `satisfying/tile_escape_cli.py` | 219 | The run/report/capture driver |
| `tests/test_tile_escape.py` | 553 | 39 tests |
| `docs/category3_tile_escape_phase1.md` | — | this report |
| `docs/validation/category3_tile_escape/` | — | evidence: 4 JSON, 2 text, 8 PNG |

### Files modified

**None.** Every path is new. That is what keeps the branch trivially reversible
and what lets the isolation tests be as blunt as they are.

### What was deliberately not built

No `UniversalSatisfyingSimulationEngine`, no shared "satisfying simulation"
framework, no reusable tile abstraction, no audio, no note system, no
particles, no materials, no lighting, no climax animation, no second ball, no
anti-stagnation assistance, no Godot scene. There is one prototype; it got what
it needs and nothing more.

### What was reused

`marble3d.seeds`'s *convention* (one salt per concern, derive a `Random` per
stream) and `tools/marble3d_run.py`'s `--digest-only` cross-process determinism
pattern. Neither is imported — copying a convention is the point, and a
Category 3 module that imports a Category 2 module to draw a random number is
exactly the coupling the brief forbids. Pillow and `pytest` are existing
dependencies; nothing new was added to `requirements.txt`.

---

## 4. Implementation

### 4.1 Arena

A regular 16-gon, circumradius 10 world units, apothem 9.8079, oriented so that
side 0 is a flat floor and side 8 a flat ceiling. Each side carries 3 equal
tiles, so 48 tiles, each 1.3006 wu long against a ball 0.9 wu wide — a hit is
unambiguous to the eye and to the code.

Tiles are numbered `side * 3 + slot` counter-clockwise from the floor, with ids
`tile_00` … `tile_47`. Identity comes from the geometry at build time and never
from the order anything was hit in, which is why building the arena twice gives
tile-for-tile identical results.

### 4.2 Ball physics — exact, not stepped

The arena is convex, so the region the ball's **centre** may occupy is exactly
the same polygon inset by the ball radius: the intersection of 16 half-planes
`dot(p, u_k) <= apothem - r`. Inside that region the ball flies a parabola, and
the time at which a parabola crosses a line is a quadratic. So the solver has
no time step at all: per flight it solves 16 quadratics, takes the earliest
positive root, advances exactly to it, reflects, and repeats.

The consequences are properties of the method rather than claims about tuning:

| Property | Why | Measured |
|---|---|---|
| No tunnelling | The solver finds the first crossing of the first wall; there is no interval in which the ball is on the wrong side | `max_wall_excursion` = 1.8e-15 wu (g=0), 1.6e-14 wu (g=12), over 300 seeds |
| No jitter | No penetration to resolve, no contact to hold, nothing to oscillate about | `min_flight_seconds` = 0.0666 s worst case |
| No energy drift | Elastic reflection preserves normal speed exactly; gravity is conservative | 0.0 relative (g=0); 4.3e-9 relative (g=12), which is the inward skin nudge accumulating, not the solver |
| No runaway, no stall | Same conservation | speed stays in 13.35–25.05 wu/s at the default config |
| Correct tile every time | The contact point is on the wall line by construction and is projected onto the side | asserted for all 48 tiles at three points each, and at both shared vertices |

Containment is checked twice. `max_wall_excursion` is computed inside the
solver as the exact maximum of each wall's quadratic over each flight — a
statement about the whole trajectory, not about sampled instants — and the test
suite adds an independent 600 Hz sampled witness, because an analytic bound
computed by the code it vouches for deserves a second opinion.

The cost of the method: a non-convex arena, a moving wall or a second ball each
need more than this. Phase 1 has none of them. Phase 2's second ball is the
moment to re-open the choice, and not before.

### 4.3 Activation

On the first valid collision a tile moves `inactive → active`, permanently.
`is_new` on the collision record is `True` exactly once per tile, and
`activated_after` carries the running count, so a duplicate hit provably cannot
move progress: `test_a_duplicate_hit_does_not_move_progress` walks every
collision and asserts the count is unchanged for every repeat. With 214
collisions and 48 activations on the default seed there are 166 duplicates to
test against.

### 4.4 Determinism

`satisfying.seeds` derives two streams from the run seed with their own salts —
position and heading, separate so that changing the release area cannot shift
the launch angle. A seed varies the release point (uniform by area over a disc
of 0.2 x circumradius) and the heading. Nothing else: speed, gravity, arena and
ball size come from the config, because a prototype comparing seeds must not
also be comparing energies.

Checked three ways: same seed thrice in one process, same seed in a fresh
interpreter through `--digest-only`, and four different seeds giving four
different digests. The digest is a SHA-256 over the raw IEEE-754 bytes of every
collision, taken before any rounding, so two runs that agree to six decimals at
collision one and are elsewhere entirely by collision two thousand compare as
different rather than as equal.

### 4.5 Completion

Completion is `activated == total`. The run stops on the collision that
activates the last tile, records `completion_time`, and reports
`stop_reason = "complete"`. `test_completion_happens_only_when_every_tile_is_activated`
asserts that the final collision is the activating one, that the count one
collision earlier was `total - 1`, and that nothing is left unhit.

One config trap is worth naming because it makes the mechanic silently
impossible: with elastic walls the specific energy is fixed at release, so
`0.5*speed^2` must exceed `gravity*(apothem - r)` or the upper tiles can never
be touched. `reachability_margin()` reports that ratio (1.78 at the defaults)
and the CLI prints it before running. A starved config is covered by a test
that asserts the top three sides are never hit.

---

## 5. Test results

`python -m pytest tests/test_tile_escape.py` — **39 passed in 3.3 s.**

The brief's eight required checks, each as a named test:

| Required | Test |
|---|---|
| expected tile count | `test_the_arena_generates_the_expected_tile_count`, plus a parametrised 16x3 / 12x4 / 8x1 / 20x2 |
| unique stable identity | `test_every_tile_has_a_unique_identity`, `test_tile_identity_is_stable_across_builds` |
| first hit activates | `test_the_first_hit_on_a_tile_activates_it` |
| duplicate does not progress | `test_a_duplicate_hit_does_not_move_progress`, `test_a_tile_is_activated_exactly_once_however_often_it_is_hit` |
| progress cannot exceed total | `test_progress_never_exceeds_the_total_tile_count` |
| complete only after all tiles | `test_completion_happens_only_when_every_tile_is_activated`, `test_a_run_stopped_early_is_not_complete` |
| deterministic initialisation | `test_the_same_seed_gives_the_same_release`, `..._in_one_process`, `..._in_a_fresh_interpreter` |
| ball remains bounded | `test_the_ball_stays_inside_the_arena_for_the_whole_run` (analytic + 600 Hz sampled) |

Beyond the list: correct tile attribution for all 48 tiles and at shared
vertices, tiles tiling each side end to end with no gap or overlap, reflection
preserving speed and reversing the wall normal, energy conserved collision by
collision, zero gravity as a valid configuration, an unreachable-ceiling config
never completing, a lit frame being measurably brighter than a dark one inside
the arena, the 9:16 frame ratio, the parallel-wall geometry finding of section
7, and the two isolation tests of section 2.

### Regression tests on the rest of the repository

This branch adds files and modifies none, so the risk of damage is structural
rather than behavioural: the question is whether any guard objects to new paths.

| Suite | Result |
|---|---|
| `tests/test_tile_escape.py` | 39 passed |
| `tests/test_company_os_research.py` | 81 passed |
| `tests/test_company_os_research_batches.py` | 118 passed |
| `tests/test_company_os_research_ingestion.py` | 122 passed |
| `tests/test_company_integration_gate.py` | 88 passed |
| `tests/test_race2_v30_stage.py` | 29 passed, **1 failed**, 1 skipped |
| `tests/test_race2_v31_readability.py` | 6 passed, 27 skipped |
| `tests/test_sloped_v26_integration.py` | 29 passed, 14 skipped |
| `tests/test_marble3d_determinism.py` | 7 passed |
| `tests/test_arena_layout.py` (Category 1) | 29 passed |

Post-commit re-run of the four guard suites that could see new paths in a
`git diff`: `test_company_os_research.py` 81 passed,
`test_company_os_research_batches.py` 118 passed,
`test_company_os_research_ingestion.py` 122 passed,
`test_race2_v30_stage.py` 29 passed / 1 failed / 1 skipped — identical to the
pre-commit run. The re-run matters: `git diff` cannot see untracked files, so a
suite run taken before committing would have under-counted any guard this
branch actually broke.

The single `test_race2_v30_stage` failure is
`test_this_branch_changes_no_physics_camera_or_course_module`, one of the
repository's 18 known pre-existing failures. It diffs two-dot against
`origin/v29-switchyard-contained-integration`, a frozen base, so every pass
that landed afterwards shows up as a stray file; its assertion message lists
`.gitignore` and `ai_platform/**`, and no `satisfying/**` or
`docs/validation/category3_tile_escape/**` path appears in it. It fails
identically with this branch's files untracked and with them committed.

The four Company OS and integration-gate suites were chosen specifically
because they are the ones that could have objected to new paths, and they pass.
That is the evidence for "existing categories remain untouched"; the full
5700-test suite was not run, because nothing in this branch can reach it and
the brief asks not to run large unrelated workloads without a reason.

---

## 6. Simulation evidence

Reproduce with `python -m satisfying.tile_escape_cli`; the exact invocations are
at the top of each evidence file.

### 6.1 The specified configuration — 16 sides, gravity 12, speed 20

`docs/validation/category3_tile_escape/phase1_gravity_runs.json`,
`phase1_gravity_log.txt`

| seed | completed | finish | collisions | duplicates | coll/s | longest dead | dead collisions | 2-tile run | grazing | max hits on one tile |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | yes | 122.0 s | 159 | 111 | 1.30 | 38.8 s | 47 | 3 | 1 | 10 |
| 2 | yes | 223.0 s | 290 | 242 | 1.30 | 67.7 s | 101 | 3 | 0 | 13 |
| 3 | yes | 358.2 s | 486 | 438 | 1.36 | 111.3 s | 149 | 9 | 2 | 19 |
| 4 | yes | 319.8 s | 456 | 408 | 1.43 | 181.2 s | 258 | 4 | 0 | 21 |
| 5 | yes | 162.1 s | 217 | 169 | 1.34 | 52.5 s | 70 | 3 | 0 | 12 |
| 6 | yes | 144.6 s | 184 | 136 | 1.27 | 48.3 s | 61 | 3 | 1 | 9 |
| 7 | yes | 173.2 s | 214 | 166 | 1.24 | 37.4 s | 45 | 6 | 0 | 13 |
| 8 | yes | 141.8 s | 183 | 135 | 1.29 | 42.0 s | 51 | 3 | 0 | 11 |

Over 300 seeds: **286/300 complete** within 1200 s; finish p10 128 s, median
189 s, p90 343 s, max 892 s; worst no-progress interval 1187 s.

Seed 7's activation intervals show the shape: the first ten new tiles arrive
0.43–1.02 s apart, the last six at 8.9, 25.8, 9.3, 37.4, 28.3 and 1.8 s. That
is the coupon-collector curve, and it is the right dramatic shape —
simple → active → escalating → last-tile tension — running roughly twenty
times too slowly.

### 6.2 The same arena with no gravity — 16 sides, gravity 0, speed 20

`phase1_zero_gravity_runs.json`

8/8 complete; finish 54.6–110.1 s, median 88.8 s; worst dead period 28.1 s;
duplicates 12–95 against 111–438 with gravity; max hits on one tile 2–6 against
9–21; grazing collisions 0; energy drift exactly 0.

**Gravity is the pacing problem, not the arena.** With gravity the bottom three
sides take 1.87x the hits of the top three, and the last tile to light lands in
the upper half of the arena in 55 of 100 runs: the ball spends its time where
the potential is low and starves the ceiling. With no gravity that ratio is
1.00 — the wall-hit distribution is uniform — and the coupon-collector tail
shortens accordingly.

### 6.3 Pacing levers, measured (12 seeds each, 900 s budget)

| variant | median finish | min | max | coll/s | worst dead | completed |
|---|---|---|---|---|---|---|
| g=12 speed=20 R=10 **(the specified config)** | 173.2 s | 101.8 | 390.3 | 1.30 | 272.7 s | 12/12 |
| g=0 speed=20 R=10 | 88.8 s | 54.6 | 110.1 | 1.36 | 28.1 s | 12/12 |
| g=0 speed=40 R=10 | 44.4 s | 27.3 | 55.0 | 2.71 | 14.0 s | 12/12 |
| g=0 speed=60 R=10 | **29.6 s** | 18.2 | 36.7 | 4.07 | 9.4 s | 12/12 |
| g=0 speed=20 R=5 | 42.9 s | 27.7 | 91.2 | 2.83 | 21.2 s | 12/12 |
| g=0 speed=60 R=10 ball=0.9 | 28.6 s | 18.5 | 60.8 | 4.24 | 14.1 s | 12/12 |
| g=4 speed=30 R=10 | 99.9 s | 75.9 | 149.5 | 1.95 | 872.0 s | 10/12 |
| g=0 speed=60, 16x4 = 64 tiles | 40.3 s | 19.4 | 45.8 | 4.11 | 13.2 s | 12/12 |
| g=0 speed=60, 16x2 = 32 tiles | 17.3 s | 12.4 | 25.2 | 4.02 | 6.9 s | 12/12 |

Completion time is very nearly inversely proportional to speed, which is what
an exact billiard should do: the number of collisions needed is geometry, and
the clock is collisions divided by rate. So **speed is the pacing dial and it
is linear**, with no reduction in reliability at 3x. A little gravity is the
worst of both worlds: `g=4 speed=30` still starves the ceiling (872 s dead
period, 2 of 12 never finishing) while giving up the uniformity.

### 6.4 The recommended configuration — 17 sides, gravity 0, speed 60

`phase1_candidate_runs.json`, and the 300-seed sweep in
`phase1_geometry_sweep.txt`

| arena | completed | finish median | p90 | max | worst dead | longest 2-tile run | longest 4-tile run |
|---|---|---|---|---|---|---|---|
| 16 x 3 = 48 tiles | 299/300 | 33.1 s | 58.5 s | 482.4 s | 828.5 s | **34** | **66** |
| 17 x 3 = 51 tiles | 299/300 | 47.1 s | 77.6 s | 743.7 s | 973.7 s | **3** | **7** |
| 15 x 3 = 45 tiles | 294/300 | 66.7 s | 193.1 s | 984.9 s | 1191.1 s | 3 | 54 |

---

## 7. The one real pathology: parallel walls

A regular polygon with an **even** number of sides has parallel opposite sides,
and two parallel walls admit an exactly periodic orbit — a ball travelling
perpendicular between them bounces off the same two tiles for ever. At 16 sides
this orbit is not theoretical. Seed 134 at `g=0 speed=60`:

```
46.531 tile_25 new=True  flight=0.3119 graze=1.000
46.843 tile_01 new=True  flight=0.3119 graze=1.000
47.155 tile_25 new=False flight=0.3119 graze=1.000
47.467 tile_01 new=False flight=0.3119 graze=1.000
...   34 collisions, 10.6 seconds, identical flight time, head-on every time
57.136 tile_24 new=True  flight=0.3119 graze=1.000
```

`tile_01` is on the floor, `tile_25` on the ceiling opposite it. The flight
time is identical to four decimal places and the impacts are exactly head-on
(`graze_ratio` 1.000), which is the signature of a fixed point rather than of
bad luck. **It escapes only because the inward skin nudge accumulates rounding
error until the contact point walks onto a neighbouring tile.** Escaping by
floating-point drift is not escaping — a different `skin`, a different
platform, or a `float64` that happened to round the other way could leave the
ball there for the rest of the run.

17 sides has no parallel pair and therefore no such orbit. Over the same 300
seeds the longest two-tile stretch falls from 34 collisions to 3, which is the
minimum a ball can produce legitimately (A, B, A). This is a **geometry fix,
not trajectory assistance**, which is why it is preferred to any nudge: it
removes the orbit from the system rather than pushing the ball out of it.

Both facts are now regression-protected:
`test_an_even_sided_arena_has_parallel_opposite_walls_and_an_odd_one_has_none`
and
`test_the_sixteen_sided_arena_admits_a_two_tile_bounce_loop_and_seventeen_does_not`.

15 sides is also odd and also kills the two-tile orbit, but it has a bad
four-tile orbit (54 consecutive collisions) and completes much worse. 17 is the
recommendation, not "any odd number".

---

## 8. Visual findings

Captures in `docs/validation/category3_tile_escape/`, 1080x1920:
`seed0007_{a_start,b_mid,c_late,d_complete}.png` for the specified config and
`candidate17_seed0007_*.png` for the recommendation.

**Inactive versus active is not a marginal call.** Inactive walls are
`(46,52,68)`, luma 52; active walls are `(255,176,66)`, luma ~193, with a
wider low-alpha pass under them. Counting pixels brighter than luma 120 inside
the arena, an empty arena gives ~400 (the ball and its halo) and a full one
~18,000 — a factor of 45. The test asserts it rather than the eye.

**Progress is obvious without a progress bar.** At 24/48 the lit and dark
tiles interleave around the ring and the fraction reads immediately. At 45/48
the three remaining dark tiles are individually countable. The
simple → escalating → last-tile-tension arc the production design wants is
already legible from the arena alone; the `24 / 48` caption is development
instrumentation and the film will not need it.

**48 tiles is the right density, and so is 51.** Each tile is clearly longer
than the ball is wide (1.30 wu against 0.90) and distinct at phone scale. At
16x4 = 64 the tiles begin to read as texture rather than as countable units and
completion time rises by a third for no dramatic gain. At 16x2 = 32 the arena
finishes in 17 s, which is too fast to build tension. **Keep the target
density; do not raise it.**

**The ball is readable, with one caveat.** At 1080 wide the ball is 21 px
across and its blue-grey halo is 100 px, which is what carries it — against a
fully lit ring the white disc alone would be marginal. At speed 60 the trail
renders as discrete dots rather than a streak, because the prototype trail
samples 34 points over 0.45 s and at 60 wu/s those points are 19 px apart. That
is a renderer sampling limit, not a physics finding, and it is a warning for
Phase 2: at 60 wu/s and 60 fps the ball travels 24 px per frame, so a film at
that speed needs motion blur or a shorter, denser trail or it will strobe.

**The 9:16 frame suits a round arena.** The arena fills 88% of the width and
about half the height, leaving a band top and bottom. That is not waste: it is
where the hook and the counter go, and it is why this shape works vertically at
all.

**The hook line is in and cost nothing** — `HIT EVERY TILE TO ESCAPE` at the
top of every frame, via Pillow's default font. No typography work was done and
none should be until Phase 2 picks a look.

---

## 9. Problems discovered

1. **Parallel-wall two-point orbit (16 sides).** Section 7. Real, reproducible,
   escapes only by rounding error. **Fix: 17 sides.** Highest priority.
2. **Four-tile orbits (16 sides: 66 consecutive collisions).** Same cause, one
   symmetry up. Also gone at 17 sides (7 collisions).
3. **Gravity starves the ceiling.** 1.87x hit asymmetry between the bottom and
   top three sides; the last tile lands in the upper half in 55% of runs.
   **Fix: gravity 0.** This is the single largest pacing win and it costs
   nothing.
4. **Heavy completion tail.** Even in the best configuration the p90 is 1.8x the
   median and the max is 15x it. The last two or three tiles are the whole
   problem: a 300-seed sweep shows dead periods up to 973 s. Phase 2 has to
   address this, and doing it with a *visible* mechanic — a hint, a widening
   target, a second ball released at a progress threshold — will read better
   than an invisible trajectory nudge, which is also the honest option for a
   channel whose premise is that you are watching physics.
5. **Collision rate is low at the specified speed.** 1.3/s. Satisfying-video
   pacing wants 4/s or more; speed 60 gives 4.07/s with no loss of reliability.
6. **One seed in 300 does not complete** within 1200 s in every configuration
   tried. Not a bug — it is the tail of item 4 — but the production pipeline
   needs a seed-acceptance pass, exactly as the races do.
7. **Grazing hits exist but are negligible.** 21 collisions across 300
   zero-gravity seeds have a normal speed under 5% of the speed. They activate
   a tile correctly; they just barely register on screen. Not worth acting on.
8. **The renderer's trail strobes at high speed.** Section 8. Renderer only.
9. **The `tools/` convention could not be followed.** Section 2.1. An
   architectural decision to hand back, not a defect in this work.
10. **Performance is a non-issue.** 300 full runs in 0.43 s. The prototype is
    roughly 10,000x faster than real time, so a Phase 2 seed search over
    thousands of candidates costs seconds.

---

## 10. Recommendation for Phase 2

Not implemented here. In priority order:

1. **Change the arena to 17 sides x 3 = 51 tiles.** Removes the periodic-orbit
   class outright. Geometry, not assistance.
2. **Set gravity to 0.** The mechanic is a billiard, not a bouncy ball. Uniform
   wall coverage, no starved ceiling, exact energy conservation, and it removes
   the reachability trap of section 4.5 entirely.
3. **Raise speed to ~60 wu/s** for a ~30–45 s median. The relationship is
   linear and reliability does not degrade, so this is a dial and not a
   redesign. Re-check readability at 60 fps first: see the strobing caveat.
4. **Then, and only then, attack the last-tile tail.** The heavy tail is what
   remains once 1–3 are done, and it is where a visible escalation mechanic
   belongs — a second ball at 80% progress, or the remaining dark tiles
   growing, or a visible tightening. Design it as something the viewer can see,
   because the premise of the format is that nothing is faked. Budget for a
   seed-acceptance pass either way.
5. **Build the Godot scene for the film.** `satisfying/tile_render.py` is a
   measuring instrument and should not grow into a renderer. The simulation is
   event-driven and exact, so it exports cleanly: a list of flights and a list
   of timestamped tile activations is everything a renderer or an audio pass
   needs, and the musical-note system the concept wants maps directly onto the
   collision list.
6. **Revisit the solver only when a second ball lands.** Ball-ball collision is
   the first thing the convex-half-plane method does not cover for free.

Phase 1 stops here.

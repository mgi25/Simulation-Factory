# Category 3, Test #1 — HIT EVERY TILE TO ESCAPE — Phase 2: pacing + seed evaluator

**Status:** Phase 2 complete. Not merged. No assistance mechanics added.
**Branch:** `category3-tile-escape-v2`
**Base:** `category3-tile-escape-v1` at `7b7f0f8`
**Worktree:** `projects/wt-category3-tile-escape`
**Date:** 2026-09-21

---

## 1. The question Phase 2 was asked

> Before introducing extra balls, trajectory assistance, moving targets or other
> pacing mechanics, determine whether natural deterministic physics + seed
> selection already solves the production problem.

**Answer: NATURAL PHYSICS SUFFICIENT.** Section 10 has the evidence and the
numbers behind it. In one line: at 17 × 3 tiles, gravity 0 and ~85 wu/s, half of
all seeds land in the 25–40 s envelope, 11.5% pass every one of twelve
independent quality conditions, and a 50,000-seed search costs 4.5 minutes of
CPU — so the supply of good runs is 5,757 per 50,000 seeds and the cost of
finding them is negligible.

Three findings changed how the rest of the work was done, and they are the
reason this report is shorter on speculation than Phase 1's:

1. **With gravity 0, speed is a change of clock and nothing else.** The tile
   sequence at 30 wu/s and at 150 wu/s is bit-identical, and completion times
   differ by exactly the speed ratio (worst relative error `7.5e-15` over 720
   run pairs). Speed cannot fix a badly-shaped run or break a well-shaped one.
   Section 4.
2. **Arena scale is the same dial as speed.** Only `speed / circumradius` is
   physical. Halving both reproduces a run exactly. So the brief's "same arena
   scale unless evidence supports a small adjustment" needs no decision: there
   is nothing there to adjust independently. Section 4.2.
3. **The heavy tail is the coupon-collector structure of the mechanic, not a
   defect of this arena.** "Hit every one of N surfaces" makes the last few
   surfaces take tens of times longer than the first few, in any geometry.
   Measured against a simulated iid baseline (section 7.3), the billiard is 18%
   *better* than random sampling at the median and 3.3x *worse* at p99 - and the
   excess over random lives entirely in the tail that seed selection discards.
   This bounds what Phase 3 could hope to achieve by tuning geometry.

---

## 2. Repository, isolation and version control

| | |
|---|---|
| Starting SHA | `7b7f0f819501fdc436dfbf0d868ac4a108aaae87` (Phase 1) |
| Starting branch | `category3-tile-escape-v1` |
| New branch | `category3-tile-escape-v2` |
| Worktree | `C:/Users/mgial/OneDrive/Documents/projects/wt-category3-tile-escape` |
| Merged | No. Nothing merged, no history rewritten. |

Category 1 (`engine/`, `entities/`, `modes/`, `powers/`), Category 2 (`race/`,
`race2/`, `sloped/`, `marble3d/`), Company OS (`company/`, `ai_platform/`,
`intelligence/`) and Ball Race Test Video 5 are untouched. Only three files were
added under `satisfying/`, one test file under `tests/`, and documentation and
evidence under `docs/`.

Phase 1's two machine-checked boundary tests still pass unchanged, and so do the
three Company OS `test_this_branch_changed_no_race_fight_or_v30_code` branch
guards — nothing was added under a declared production root. The Phase 2 driver
sits beside its code in `satisfying/` for the same reason Phase 1's does, which
is recorded in section 2.1 of the Phase 1 report; that decision is unchanged and
is still one to hand back to whoever owns those guards.

---

## 3. Part 1 — validating 17 × 3 = 51

`docs/validation/category3_tile_escape/phase2_population_50k_speed60.json`

**50,000 deterministic seeds** (0–49,999), the locked base configuration: 17
sides, 3 tiles per side, 51 tiles, gravity 0, speed 60 wu/s, circumradius 10,
ball radius 0.45, restitution 1. Runs stop at 8,000 collisions rather than at a
wall-clock limit, because a *time* cap censors the population differently at
every speed while a collision cap censors it identically. 265 s of CPU for the
whole sweep.

The brief asked for at least 10,000 seeds. 50,000 were run because the cost is
5.3 ms per seed and the tail statistics are the ones that matter. The
10,000-seed population the brief specified is reported separately in
`phase2_population_10k_speed60.json`; it agrees with the 50,000-seed one to
within **2.2% on every percentile up to p95** (0.5% at the median) and diverges
by 4.1% at p99, which is the expected behaviour of a heavy tail sampled five
times less often and is the reason the larger sweep was run.

### 3.1 Completion

| | |
|---|---|
| Completed | **49,899 / 50,000 = 99.80%** |
| Incomplete | 101 (0.20%), every one of them by hitting the 8,000-collision cap |

### 3.2 Completion-time distribution (seconds, speed 60)

| min | p10 | p25 | p50 | p75 | p90 | p95 | p99 | max |
|---|---|---|---|---|---|---|---|---|
| 14.42 | 30.72 | 37.95 | **47.26** | 60.06 | 78.90 | 105.53 | 361.07 | 2396.70 |

**The locked starting speed of 60 wu/s is too slow for 51 tiles.** Phase 1's
"~60 wu/s reaches Shorts territory" was measured at 48 tiles in a 16-gon
(median 33.1 s). Three more tiles and one more wall push the median to 47.3 s,
which is outside the 25–40 s envelope. This is a consequence of the geometry
change Phase 1 recommended, not a contradiction of it. Section 5 fixes it.

### 3.3 Collisions

| | min | p10 | p25 | p50 | p75 | p90 | p95 | p99 | max |
|---|---|---|---|---|---|---|---|---|---|
| collisions | 51 | 116 | 144 | **181** | 231 | 306 | 412 | 1410 | 7923 |
| collisions/s | 3.21 | 3.38 | 3.49 | **3.75** | 4.11 | 4.39 | 4.63 | 5.22 | 6.86 |

Mean collisions 232.8. Duplicate share (repeat hits as a fraction of all
contacts) has median 0.718 — roughly seven contacts in ten land on a tile that
is already lit. Most hits on any single tile: median 7, p99 64, max 421.

### 3.4 Milestone timings (seconds, speed 60, completing runs)

| milestone | tile | p10 | p25 | p50 | p75 | p90 | p95 |
|---|---|---|---|---|---|---|---|
| first activation | 1 | 0.13 | 0.14 | **0.16** | 0.17 | 0.18 | 0.18 |
| 25% | 13 | 3.20 | 3.57 | **3.79** | 3.93 | 4.22 | 4.38 |
| 50% | 26 | 7.46 | 8.08 | **8.86** | 9.65 | 10.60 | 11.40 |
| 75% | 39 | 13.61 | 15.54 | **17.59** | 20.04 | 23.72 | 28.48 |
| 90% | 46 | 20.00 | 23.16 | **26.87** | 31.78 | 39.14 | 50.45 |
| 95% = 49/51 | 49 | 24.55 | 29.30 | **34.90** | 42.31 | 53.26 | 69.78 |
| 50/51 | 50 | 27.25 | 33.12 | **40.12** | 49.59 | 64.61 | 86.73 |
| 51/51 | 51 | 30.72 | 37.95 | **47.26** | 60.06 | 78.90 | 105.53 |

**At 51 tiles the "95%" milestone and the "49 of 51" milestone are the same
tile.** `ceil(0.95 × 51) = 49`. They coincide for every tile count from 40 to
59, so the two clocks are one clock here; a test pins this so no future report
compares a value with itself and calls it a finding.

### 3.5 Stagnation

| metric (seconds) | p10 | p25 | p50 | p75 | p90 | p95 | max |
|---|---|---|---|---|---|---|---|
| longest gap, anywhere | 3.61 | 5.68 | **9.57** | 16.16 | 27.06 | 38.99 | 2381 |
| longest gap **before the final three tiles** | 2.11 | 3.01 | **4.52** | 7.06 | 11.77 | 18.09 | 2381 |
| median interval between activations | 0.30 | 0.31 | **0.31** | 0.32 | 0.40 | 0.52 | 4.84 |
| gaps of 3 s or more, per run | 1 | 2 | **3** | 4 | 6 | 7 | 27 |

**Where the longest gap sits is the finding, not how long it is.** The fraction
of tiles already lit when the longest gap begins has median **0.96** and p25
0.92: in a typical run the longest dead period is the hunt for one of the last
two tiles, not a hole in the middle. That is why the evaluator reports two gap
numbers and why acceptance uses the second one.

### 3.6 Tail

| clock (seconds) | p10 | p25 | p50 | p75 | p90 | p95 |
|---|---|---|---|---|---|---|
| 90% → complete | 7.28 | 11.97 | **19.17** | 29.95 | 44.75 | 60.84 |
| 95% → complete | 2.41 | 5.17 | **10.43** | 19.26 | 31.93 | 44.30 |
| 49/51 → complete | 2.41 | 5.17 | **10.43** | 19.26 | 31.93 | 44.30 |
| 50/51 → complete (final tile) | 0.59 | 1.64 | **4.71** | 10.98 | 20.66 | 29.28 |
| final three tiles | 4.09 | 7.65 | **13.88** | 23.46 | 36.91 | 50.93 |
| tail share from 90% | 0.22 | 0.31 | **0.41** | 0.51 | 0.60 | 0.65 |

At the median, **41% of the runtime is spent on the last 10% of the tiles**, and
the final tile alone takes 14.3× an ordinary activation interval. That is the
shape the brief calls tension when it is bounded and boredom when it is not:
p10 is 0.59 s (over before it registers) and p95 is 29.28 s (a wait). Both ends
are real populations, which is exactly what makes selection worth doing.

---

## 4. The finding that reorganised the analysis: speed is only a clock

`docs/validation/category3_tile_escape/phase2_speed_invariance.json`

With `gravity = 0` a flight is a straight line, so the release point and heading
fix the entire sequence of walls the ball will ever touch. Speed sets only how
fast that fixed sequence is traversed.

### 4.1 The measurement

Measured over **60 seeds × 12 speeds (30 to 150 wu/s) = 720 run pairs**:

| | |
|---|---|
| Identical tile sequences, contact for contact | **720 / 720** |
| Worst relative error on the predicted time ratio | **7.494e-15** |

So `completion_time(speed) = completion_time(60) × 60 / speed`, exactly, to the
last bit a double can hold. Three consequences:

- Every seed's **shape** — collision count, tile order, stagnation measured in
  collisions, every periodic pattern — is a property of the seed alone. Speed
  moves all of a run's clocks by one factor.
- Speed therefore **cannot repair a badly shaped run**, and choosing it is
  purely a matter of placing the whole distribution against the runtime
  envelope and the readability band.
- A single sweep gives the exact curve for every speed. Section 5 nonetheless
  reports a real simulation at each swept speed, because a claim this load-
  bearing deserves to be demonstrated rather than extrapolated.

A test pins the claim, and a companion test pins that it **stops** holding once
gravity is switched on — otherwise a future change could leave the check passing
while measuring nothing.

### 4.2 Arena scale is the same dial

A run's clock is (collisions × mean chord) / speed, and scaling the arena scales
the mean chord. Only `speed / circumradius` is physical. Halving the
circumradius, the ball radius and the speed together reproduces a run **exactly**
— same tile sequence, same completion time to `1e-9` relative — which is
measured in `task_invariance` and pinned by
`test_arena_scale_and_speed_are_one_dial_and_not_two`.

The brief allowed a small arena-scale adjustment if evidence supported one.
**No such adjustment is possible as an independent lever**; it would be the
speed change of section 5 expressed in different units. The arena stays at
circumradius 10.

---

## 5. Part 2 — the speed sweep

`phase2_speed_sweep_suggested.json` (50–70) and `phase2_speed_sweep_widened.json`
(75–120). **10,000 seeds simulated independently at every speed**, not rescaled.

| speed | p50 | p90 | coll/s | in 25–40 s | in 28–38 s | accepted | final tile p50 | body gap p50 |
|---|---|---|---|---|---|---|---|---|
| 50 | 57.0 | 96.2 | 3.13 | 13.2% | 9.2% | 4.55% | 5.81 | 5.45 |
| 55 | 51.8 | 87.5 | 3.44 | 19.9% | 13.4% | 7.31% | 5.28 | 4.96 |
| 60 | 47.5 | 80.2 | 3.75 | 26.6% | 18.6% | 9.32% | 4.84 | 4.54 |
| 65 | 43.8 | 74.0 | 4.07 | 33.5% | 24.1% | 11.24% | 4.47 | 4.19 |
| 70 | 40.7 | 68.7 | 4.38 | 40.3% | 28.9% | 12.45% | 4.15 | 3.89 |
| **75** | 38.0 | 64.1 | 4.69 | 45.5% | 32.2% | **12.71%** | 3.87 | 3.63 |
| **80** | 35.6 | 60.1 | 5.01 | 48.9% | 34.5% | 12.01% | 3.63 | 3.41 |
| **85** | **33.5** | 56.6 | 5.32 | 50.0% | **34.7%** | 11.12% | 3.42 | 3.21 |
| **90** | 31.7 | 53.5 | 5.63 | **50.2%** | 34.0% | 10.11% | 3.23 | 3.03 |
| 95 | 30.0 | 50.6 | 5.95 | 49.3% | 32.4% | 8.81% | 3.06 | 2.87 |
| 100 | 28.5 | 48.1 | 6.26 | 47.4% | 30.4% | 7.17% | 2.90 | 2.73 |
| 110 | 25.9 | 43.7 | 6.88 | 41.0% | 25.3% | 4.73% | 2.64 | 2.48 |
| 120 | 23.7 | 40.1 | 7.51 | 33.8% | 20.3% | 2.75% | 2.42 | 2.27 |

### 5.1 Why the sweep was widened

The brief said not to widen without justification. The suggested 50–70 band is
**monotone in every column and has not turned over at its top end**: acceptance
climbs 4.55% → 12.45% from end to end and the median is still 40.7 s at 70 wu/s,
at the very edge of the envelope. A sweep whose best point is its boundary has
not found an optimum, so it was extended to 120 wu/s, where all three quality
columns have clearly peaked and fallen.

### 5.2 The optimum is a crossing, not a maximum

The three columns peak in different places, and the reason is a real trade:

- **In-envelope fraction** peaks at **90** (50.2%), because raising speed pulls
  the long half of the distribution down into 25–40 s.
- **Acceptance** peaks lower, at **75** (12.71%), because acceptance also
  requires the ending to be *visible*: `final_tile ≥ 1.5 s`. Speed compresses
  the tail along with everything else, so past ~85 wu/s the runs entering the
  envelope from above are offset by runs whose ending has flattened into
  nothing. At 120 wu/s the median final tile is 2.42 s and acceptance has
  collapsed to 2.75%.

**Recommended operating region: 75–90 wu/s. Recommended point: 85 wu/s.**

| why 85 | |
|---|---|
| Median completion | 33.5 s — the middle of the brief's stated "low/mid 30-second" target |
| In the core 28–38 s window | 34.7%, the maximum over the whole sweep |
| In 25–40 s | 50.0%, within 0.2 pp of the maximum |
| Acceptance | 11.12% — 5,560 usable seeds per 50,000 |
| Collision rate | 5.32/s = one impact every 11.3 frames at 60 fps |
| Median final tile | 3.42 s, still 15.6× the 0.219 s ordinary activation interval at this speed |

75 wu/s is the right choice instead if yield per seed searched matters more than
landing in the middle of the target: it buys 1.6 pp of acceptance at the cost of
a 38.0 s median, which is the top edge of the envelope rather than its middle.
80 is between the two and loses nothing much either way. Below 70 and above 100
are both clearly worse on every column.

### 5.3 Rendering concerns, kept separate

Nothing above is a rendering measurement, and none of the recommendation rests
on one. Two things a Phase 3 renderer will have to check, flagged rather than
assumed:

- At 85 wu/s the ball crosses the arena in roughly 0.24 s — about 14 frames at
  60 fps. Phase 1 already found the instrument renderer's trail strobes at 60
  wu/s; at 85 it will strobe harder. This is a shutter/trail problem, not a
  simulation problem.
- 5.32 impacts per second is 11 frames apart. That is separable, but it is the
  density a procedural audio pass has to sit on top of — roughly 16th notes at
  120 BPM. If audio wants fewer events, the lever is speed, and the cost in
  runtime is exactly linear.

---

## 6. Part 3 — the evaluator

### Files created

| file | lines | what it is |
|---|---|---|
| `satisfying/tile_evaluator.py` | 788 | One run in, named metrics out. Milestones, stagnation, tail clocks, collision quality, periodic-pattern detection, acceptance rule, candidate score. |
| `satisfying/tile_sweep.py` | 488 | Population layer: batch sweep, nearest-rank distributions, the population report, the activation-curve percentiles, the shortlist, the speed-invariance measurement. |
| `satisfying/tile_sweep_cli.py` | 495 | The driver: `population`, `speed`, `invariance`, `candidates`, `curves`, `inspect`. |
| `tests/test_tile_escape_phase2.py` | 824 | 53 test functions, 58 test items. |
| `docs/category3_tile_escape_phase2.md` | this | |

No generic evaluation framework, no plugin registry, no metric protocol: a
`TileEscapeRun` goes in and a `RunEvaluation` of named floats comes out. A
general evaluator would have to guess what "the tail" means, and the whole point
here is that the tail means something exact — the clock from the 49th tile to
the 51st.

### Files modified

None. Phase 1's `tile_arena.py`, `tile_escape.py`, `tile_render.py`, `seeds.py`,
`tile_escape_cli.py` and `tests/test_tile_escape.py` are untouched, and all 39
Phase 1 tests pass unchanged.

### 6.1 Metrics, and exactly how each is computed

Everything is derived from the event stream — `run.collisions` and
`run.first_hit_time`. Nothing re-simulates, samples the trajectory or looks at a
pixel, so an evaluation is as deterministic as the run it describes.

**Completion.** `completed`, `activated_tiles`, `completion_seconds`,
`stop_reason`.

**Opening.**
- `first_collision_seconds` = time of contact 1.
- `first_activation_seconds` = time of the first new tile. Identical to the
  above in any real run, because every tile starts dark; a test asserts it.
- `activations_in_opening` = new tiles with `t ≤ 2.0 s`.
- `early_activation_rate` = that count / 2.0.

**Progression.** `milestone_index(spec, total)`: a fraction rounds **up**
(`ceil(0.25 × 51) = 13`); a non-positive integer counts back from the end
(`0 → 51`, `-1 → 50`, `-2 → 49`). `milestones[name]` is the time of that
activation, or `None` if it never happened — never 0.0, because "at the start"
and "never" must not collapse.

**Stagnation.** The gap list is one entry per activation (from the previous
activation, or from `t = 0` for the first) plus the tail from the last
activation to the end of the run.
- `longest_gap_seconds` / `_start_seconds` / `_after_tiles` = the largest, and
  where it sits.
- `longest_gap_progress` = tiles lit when it began, over 51.
- `longest_body_gap_seconds` = the largest gap that **begins while more than
  three tiles are still dark**. This is the number that separates a mid-run hole
  from an ending.
- `long_gap_count` = gaps ≥ 3.0 s.
- `median_activation_interval` = median over the activation gaps only.

**Tail.** Four independent clocks, each `completion − milestone`:
`tail_from_90_seconds`, `tail_from_95_seconds`, `tail_from_third_last_seconds`
(49/51), `tail_from_second_last_seconds` (50/51, = `final_tile_seconds`). Plus
`final_three_seconds` = `completion − t(48th)`, `tail_share_from_90` =
`tail_from_90 / completion`, and `final_tile_over_median_interval`, which is how
many ordinary tiles the last one is worth.

**Collision quality.** `collisions`, `new_hits`, `duplicate_hits`,
`collisions_per_second`, `duplicate_share`, `max_hits_on_one_tile`,
`untouched_tiles`, and — split into three equal-count blocks of the collision
stream — `duplicate_share_thirds` (always defined) and
`duplicates_per_new_thirds` (`None` when a block has no new tile, rather than a
division by zero dressed up as infinity).

### 6.2 Periodic-pattern detection

`longest_periodic_run(values, times, max_period=8, min_period=1, min_repeats=2)`
finds the longest stretch in which every entry equals the one `p` places back,
scanning every period from `min_period` to `max_period`. Ties go to the
**smaller** period: a true A-B-A-B also satisfies period 4 with two fewer
matching positions and therefore the same stretch length, and reporting it as a
four-cycle would misname the pathology.

Four detectors run on every evaluation:

| field | what it catches |
|---|---|
| `longest_alternation` | A-B-A-B specifically (period 2 only) |
| `longest_tile_cycle` | any repeating tile cycle up to period 8 |
| `longest_side_cycle` | the same over **wall** indices — a ball retracing a wall sequence while drifting across the tiles of each wall, which a tile-level check cannot see |
| `longest_two_tile_run` / `longest_four_tile_run` | sliding windows confined to ≤ 2 and ≤ 4 distinct tiles, reported **with the position** they started at |

Period 1 is in range even though two consecutive contacts with the same tile are
impossible here: if it ever fires, the skin nudge has failed, and that is worth
catching rather than assuming away.

### 6.3 Acceptance: twelve separable conditions, not a score

`AcceptanceRule` is a dataclass of named thresholds; `verdict()` applies all
twelve and returns **every** failure, not the first. A seed that misses one
threshold by a tenth of a second is a different object from one that misses
five, and a first-failure-wins check makes them look the same.

The right-hand column is the **measured rejection rate of that condition alone**
over the 50,000-seed sweep at 85 wu/s — exact, not an estimated percentile, and
reproducible from `phase2_population_50k_speed85.json`.

| condition | threshold | rejects | what it is for |
|---|---|---|---|
| `completes` | all 51 tiles | 0.20% | — |
| `duration_at_least_min` | ≥ 25 s | 18.96% | the brief's envelope |
| `duration_at_most_max` | ≤ 40 s | 30.36% | the brief's envelope |
| `opens_immediately` | first contact ≤ 1.0 s | **0.00%** | viewer retention; inert here |
| `opening_is_busy` | ≥ 3 activations in 2 s | **0.00%** | viewer retention; inert here |
| `no_mid_run_dead_zone` | body gap ≤ 4.0 s | 35.63% | the brief's "no large dead zone" |
| `last_tile_has_tension` | final tile ≥ 1.5 s | 30.31% | below this the ending is over before it registers |
| `last_tile_is_not_a_wait` | final tile ≤ 9.0 s | 21.03% | above this it is a wait, not a hunt |
| `final_three_are_a_hunt` | final three ≤ 14.0 s | 32.59% | the ending as a whole, not just its last beat |
| `tail_is_proportionate` | tail share from 90% ≤ 0.40 | **52.74%** | the ending may not be most of the video |
| `no_two_tile_loop` | ≤ 4 collisions on ≤ 2 tiles | **0.00%** | Phase 1's pathology; inert at 17 sides, fires at 16 |
| `no_long_cycle` | longest tile cycle ≤ 12 collisions | 0.51% | the residual 17-sided pathology of section 7.2 |

The binding condition at 85 wu/s is `tail_is_proportionate`, which rejects more
than half the population on its own and is **dimensionless** — it is the one
condition speed cannot move. `last_tile_has_tension` is the condition that makes
acceptance peak at a lower speed than envelope coverage does (section 5.2): it
rejects 30.31% at 85 wu/s and more at every speed above it.

**Three of the twelve never fire at 17 × 3 with gravity 0, and that is itself a
result.** Over 49,899 completing seeds, the first contact was always between
0.123 s and 0.192 s, every run lit at least 3 tiles in its first 2 s, and the
longest two-tile run was never more than 3. `opens_immediately`,
`opening_is_busy` and `no_two_tile_loop` are therefore inert in this
configuration. They are kept — each fires on a configuration that is one
parameter away, and `no_two_tile_loop` fires immediately at 16 sides, which a
test asserts — but the honest statement is that **the opening of this simulation
is never the problem**. Raising the thresholds to manufacture a failure rate
would be tuning the instrument to look busy.

### 6.4 The score, and why it comes second

`candidate_score` returns a `ScoreBreakdown`: a total in [0, 1] **and** the five
components and five weights it is the sum of. It only ever ranks runs that
`verdict` has already accepted; nothing is accepted because of a score. A test
asserts the total is reproducible from the reported components.

| component | formula | weight |
|---|---|---|
| `runtime` | tent(completion, ideal 32 s, tolerance 9 s) | 0.35 |
| `tail_tension` | tent(final tile, ideal 4 s, tolerance 5 s) | 0.30 |
| `no_stagnation` | 1 − body_gap / 4.0, floored at 0 | 0.25 |
| `opening` | min(1, activations in 2 s / 6) | 0.05 |
| `event_density` | tent(collisions/s, ideal 6.0, tolerance 3.0) | 0.05 |

`tent(v, i, t) = max(0, 1 − |v − i| / t)`: 1.0 at the ideal, falling linearly to
0 at ±tolerance.

The weights follow the **measured variance** of each component, not a prior
opinion. Runtime, tension and stagnation are where seeds actually differ and
carry 0.90 between them. Opening and density carry 0.05 each because they barely
vary (section 6.3): weighting a near-constant heavily adds the same number to
every score and ranks nothing. The constants are chosen so the score never
disagrees with the rule at a boundary — `runtime` reaches zero at 23 s and 41 s,
just outside the 25–40 s window, and `tail_tension` reaches zero at 9 s, exactly
`max_final_tile`.

---

## 7. Periodic-orbit findings

### 7.1 The 16-sided pathology is gone, and it was worse than Phase 1 knew

**Same 10,000 seeds (0-9,999), same speed, same gravity, one wall apart:**

| | 16 x 3 = 48 tiles | 17 x 3 = 51 tiles |
|---|---|---|
| longest two-tile run, **max** | **4,214 collisions** | **3** |
| longest two-tile run, p99 | 36 | 3 |
| longest two-tile run, p90 | 4 | 3 |
| longest A-B-A-B alternation, max | **4,214** | **0** |
| longest four-tile run, max | **6,096** | 142 |
| seeds with **any** tile cycle (period <= 8) | 1,626 = **16.26%** | 67 = **0.67%** |
| seeds with **any** wall-sequence cycle | 3,979 = **39.79%** | 67 = **0.67%** |
| cycle periods present | 2, 4, 6, 8 | 4, 8 only |

The 17-sided column is confirmed at five times the sample size by the
50,000-seed sweep: two-tile max still 3, alternation still 0, any-cycle rate
0.65%.

Three things in that table are worth saying out loud.

**Phase 1 understated the 16-sided problem by two orders of magnitude.** Seed
134's 34-collision trap sat around the 99th percentile, not at the worst case.
The worst case in 10,000 seeds is seed 6518: **4,214 consecutive collisions**
alternating between `tile_03` and `tile_29` - sides 1 and 9, an exactly parallel
pair - beginning at t = 587 s. Every one of the ten worst two-tile traps is a
parallel-wall pair, sides differing by exactly 8.

**A-B-A-B does not occur at all at 17 sides.** Not "rarely": the longest
alternation over 50,000 seeds is **0**, and the longest two-tile run is 3, which
is the minimum a ball can produce legitimately (A, B, A). The geometry fix
removed the orbit from the system rather than making it unlikely. Period 2 is
absent from the 17-sided cycle histogram entirely.

**The wall-groove mode disappears too, and this is the reason both detectors
exist.** At 16 sides, 603 of 1,500 spot-checked seeds have a repeating *wall*
sequence with no repeating *tile* sequence - a ball bouncing between parallel
walls while drifting sideways across their tiles, which looks stuck on screen
and is invisible to a tile-level check. At 17 sides that count is **zero**: the
side detector never once exceeds the tile detector. The 16-sided disagreement
(39.79% against 16.26%) is also the evidence that the two detectors are not the
same code path wearing two names.

### 7.2 A new, much rarer pathology at 17 sides

17 sides is not perfectly clean. **323 seeds in 50,000 (0.65%)** contain a
repeating cycle, at **period 4 (113 seeds) or period 8 (210 seeds)** — never
period 2. The worst is 682 collisions, and the worst four-tile confinement is
174 consecutive collisions. `no_long_cycle` rejects 256 of the 50,000 (0.51%).

This is the residual of the same mechanism one symmetry further out, and it is
handled the way Phase 1 handled the rest: **detected, measured, and rejected by
the acceptance rule** rather than patched in the physics. At 0.65% it costs
nothing in yield.

### 7.3 Why the tail exists at all, and what that bounds

`phase2_coupon_collector_baseline.json`

"Hit every one of N surfaces" is a coupon-collector process, and coupon
collectors have heavy tails by construction. The right comparison is not the
textbook mean but the whole distribution, so the iid baseline was **simulated at
the same sample size**: 50,000 trials of drawing uniformly from 51 tiles until
all are collected, against the 50,000-seed billiard sweep.

| collisions / draws to light all 51 | billiard (17 x 3) | iid random draws | ratio |
|---|---|---|---|
| p10 | 116 | 162 | 0.72 |
| p25 | 144 | 186 | 0.77 |
| **p50** | **181** | **220** | **0.82** |
| p75 | 231 | 263 | 0.88 |
| p90 | 306 | 314 | 0.97 |
| **mean** | **232.8** | **230.7** | **1.01** |
| p99 | 1,410 | 430 | **3.28** |
| max | 7,923 | 709 | **11.17** |

(The simulated iid mean of 230.7 matches the analytic `51 x H(51) = 230.5`, so
the baseline is sound.)

**The billiard is 18% better than random in the body and 3.3x worse in the
tail, and the two cancel almost exactly in the mean.** That is the correlation
in a billiard trajectory showing up twice with opposite signs: usually a ball
crossing the arena sweeps new walls more systematically than a die does, and
occasionally it falls into a near-periodic path and revisits the same handful of
tiles for hundreds of collisions. A die cannot get stuck; a ball can.

Two implications, and they point the same way:

- **The deceleration toward the last tiles is structural.** It is the
  coupon-collector shape, present in any geometry, and no polygon, tile count or
  speed removes it. Section 8.1's curve is what that shape looks like.
- **The part that is *worse* than random is exactly the part selection removes.**
  The excess over iid lives entirely above p90; below it the billiard wins. So
  seed selection is not papering over a defect - it is discarding the
  correlation-induced tail and keeping a body that is already better than
  chance. That is the strongest single argument behind the decision gate.

---

## 8. Activation-curve findings

`phase2_activation_percentiles_speed85.csv` (and the same at speed 60), one row
per activation number: `activated, runs, p10, p25, p50, p75, p90`. 10,000 seeds.
The shortlisted seeds' own curves are in `phase2_shortlist_curves_speed85.csv` as
`seed, seconds, activated`, which is a step function and should be drawn as one.

### 8.1 The typical shape, at 85 wu/s

Median seconds per new tile, by band:

| tiles | median gap | what the viewer sees |
|---|---|---|
| 1–5 | 0.19 s | immediate, continuous activity |
| 6–17 | 0.22 s | steady — the arena is filling visibly |
| 18–30 | 0.32 s | first perceptible slowing |
| 31–43 | 0.60 s | dark tiles becoming scarce |
| 44–48 | 1.37 s | hunting |
| 49 | 2.24 s | |
| 50 | 3.73 s | |
| **51** | **5.11 s** | the last tile |

**This is healthy deceleration, not stagnation.** The curve is monotone and
smooth: every band is slower than the one before, the ratio between consecutive
bands is between 1.1 and 2.3, and there is no discontinuity anywhere. The last
tile takes 26× the opening pace, reached gradually over 51 steps rather than in
a cliff. That is the retention shape the brief described, and the median seed
already has it.

### 8.2 All the variation is created in the second half

| tile | p10 | p50 | p90 | p90 / p10 |
|---|---|---|---|---|
| 1 | 0.09 | 0.11 | 0.13 | 1.35 |
| 13 (25%) | 2.25 | 2.67 | 2.98 | 1.32 |
| 26 (50%) | 5.27 | 6.25 | 7.49 | 1.42 |
| 39 (75%) | 9.62 | 12.43 | 16.85 | 1.75 |
| 46 (90%) | 14.14 | 19.00 | 27.77 | 1.96 |
| 49 (95%) | 17.46 | 24.68 | 37.79 | 2.16 |
| 51 | 21.86 | 33.52 | 56.60 | 2.59 |

Up to the halfway mark, every seed runs essentially the same video: the spread
between the 10th and 90th percentile is under 1.5×, and half the arena is lit
between 5.3 s and 7.5 s in 80% of runs. The spread then doubles over the second
half.

**Seed selection is therefore not a choice about the whole run. It is a choice
about the last twenty tiles.** Nothing a seed can do makes the opening better —
it is already as good as it gets in every seed — and nothing makes the middle
worse. This also explains why three of the twelve acceptance conditions never
fire.

---

## 9. Part 4 — the candidate shortlist

`phase2_shortlist_speed85.json` (full precision, every metric, every verdict) and
`phase2_shortlist_curves_speed85.csv` (1,040 rows: `seed, seconds, activated`).

**50,000 seeds searched at 85 wu/s in 271 s. 5,757 accepted (11.51%).** The 20
below are the highest-scoring; the score only ranks, and all 5,757 passed all
twelve conditions.

| seed | score | total | 25% | 50% | 75% | 90% | 49/51 | 50/51 | last 3 | last 1 | worst body gap (at tile) | coll | dup | dup share E/M/L | 2-tile |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 3530 | 0.859 | 32.1 | 3.1 | 6.9 | 14.6 | 21.4 | 26.4 | 28.3 | 8.3 | 3.8 | 1.70 @ 45 | 158 | 107 | 0.40/0.72/0.91 | 2 |
| 2281 | 0.856 | 31.8 | 2.7 | 6.3 | 14.2 | 19.9 | 21.7 | 28.0 | 10.6 | 3.7 | 1.60 @ 42 | 151 | 100 | 0.32/0.74/0.92 | 2 |
| 12183 | 0.854 | 31.2 | 2.7 | 8.3 | 15.6 | 22.6 | 25.6 | 27.6 | 6.5 | 3.5 | 1.09 @ 41 | 153 | 102 | 0.41/0.73/0.86 | 3 |
| 37169 | 0.853 | 32.2 | 2.0 | 6.0 | 13.0 | 19.4 | 26.1 | 28.1 | 10.4 | 4.1 | 2.16 @ 47 | 194 | 143 | 0.47/0.80/0.94 | 3 |
| 8949 | 0.851 | 31.5 | 1.6 | 5.9 | 13.4 | 19.5 | 25.4 | 27.3 | 10.3 | 4.2 | 1.90 @ 37 | 189 | 138 | 0.44/0.81/0.94 | 3 |
| 14694 | 0.849 | 31.7 | 1.7 | 5.5 | 13.0 | 19.8 | 23.7 | 27.7 | 10.1 | 4.0 | 2.19 @ 45 | 192 | 141 | 0.44/0.83/0.94 | 3 |
| 15517 | 0.848 | 31.7 | 1.7 | 5.5 | 13.0 | 19.8 | 23.7 | 27.7 | 10.1 | 4.0 | 2.19 @ 45 | 192 | 141 | 0.44/0.83/0.94 | 3 |
| 13968 | 0.844 | 31.6 | 2.6 | 6.2 | 12.4 | 19.6 | 23.5 | 27.3 | 9.6 | 4.3 | 1.84 @ 41 | 177 | 126 | 0.39/0.85/0.90 | 2 |
| 8108 | 0.843 | 31.6 | 3.2 | 8.1 | 14.4 | 19.0 | 24.3 | 28.3 | 11.4 | 3.4 | 1.50 @ 39 | 167 | 116 | 0.47/0.66/0.95 | 3 |
| 30725 | 0.839 | 31.5 | 1.6 | 5.4 | 12.9 | 20.8 | 24.8 | 27.5 | 8.0 | 4.0 | 2.19 @ 44 | 191 | 140 | 0.44/0.83/0.92 | 3 |
| 17276 | 0.838 | 31.9 | 2.7 | 6.9 | 13.6 | 22.7 | 24.6 | 28.0 | 8.4 | 3.9 | 2.13 @ 45 | 154 | 103 | 0.31/0.80/0.88 | 2 |
| 37393 | 0.838 | 32.1 | 2.7 | 7.0 | 14.1 | 19.4 | 23.0 | 28.4 | 10.3 | 3.7 | 2.18 @ 41 | 186 | 135 | 0.45/0.77/0.95 | 2 |
| 9521 | 0.837 | 32.3 | 2.7 | 5.5 | 15.1 | 20.5 | 27.1 | 28.4 | 10.0 | 3.8 | 2.04 @ 32 | 163 | 112 | 0.39/0.74/0.93 | 2 |
| 35688 | 0.835 | 31.9 | 2.9 | 8.0 | 17.0 | 23.6 | 26.6 | 29.0 | 6.0 | 3.0 | 1.28 @ 47 | 150 | 99 | 0.38/0.76/0.84 | 2 |
| 2427 | 0.835 | 30.8 | 2.5 | 5.2 | 13.5 | 19.0 | 24.2 | 27.0 | 9.3 | 3.8 | 1.68 @ 46 | 184 | 133 | 0.41/0.82/0.94 | 2 |
| 36557 | 0.834 | 31.3 | 3.0 | 6.6 | 12.7 | 21.3 | 25.9 | 27.0 | 7.1 | 4.3 | 1.69 @ 46 | 155 | 104 | 0.31/0.81/0.88 | 3 |
| 33377 | 0.832 | 32.3 | 2.7 | 7.3 | 14.0 | 23.1 | 25.0 | 28.4 | 8.4 | 3.9 | 2.13 @ 45 | 156 | 105 | 0.35/0.79/0.88 | 2 |
| 15088 | 0.831 | 30.7 | 2.5 | 6.1 | 13.7 | 21.3 | 24.6 | 26.5 | 7.3 | 4.1 | 1.73 @ 45 | 185 | 134 | 0.41/0.81/0.95 | 2 |
| 5672 | 0.831 | 32.2 | 3.1 | 8.2 | 17.2 | 23.8 | 26.8 | 29.2 | 6.0 | 3.0 | 1.28 @ 47 | 151 | 100 | 0.38/0.76/0.84 | 2 |
| 26267 | 0.831 | 30.3 | 2.6 | 7.1 | 13.8 | 19.6 | 22.2 | 26.3 | 8.7 | 4.0 | 1.30 @ 31 | 145 | 94 | 0.29/0.73/0.92 | 3 |

All twenty light their first tile at 0.1 s and all twenty activate all 51.
Ranges across the shortlist: **total 30.3–32.3 s**, final tile **3.0–4.3 s**,
final three **6.0–11.4 s**, worst mid-run gap **1.09–2.19 s**, collisions
**145–194**.

Two rows to read carefully. Seeds **14694 and 15517** print identically at one
decimal place; they are genuinely different runs with different release states
and different digests (31.6897 s against 31.6801 s), and the JSON carries full
precision. The same applies to 35688 and 5672. The table is rounded for reading;
nothing is deduplicated.

### 9.1 Why they passed, and what the score is made of

The top seed, **3530**, scores 0.859:

| component | value | score | weight | contribution |
|---|---|---|---|---|
| runtime | 32.1 s | 0.984 | 0.35 | 0.344 |
| tail_tension | final tile 3.8 s | 0.964 | 0.30 | 0.289 |
| no_stagnation | body gap 1.70 s | 0.574 | 0.25 | 0.144 |
| opening | 8 tiles in 2 s | 1.000 | 0.05 | 0.050 |
| event_density | 4.9 collisions/s | 0.639 | 0.05 | 0.032 |
| | | | | **0.859** |

In prose: it runs 32.1 s, half a second off the ideal; it opens instantly, lights
a quarter of the arena in 3.1 s and half of it in 6.9 s; it never goes more than
1.70 s without a new tile until 45 tiles are lit; the last three tiles take 8.3 s
and the last one alone 3.8 s, which is 17× an ordinary activation; and it does
all of that in 158 collisions with no two-tile loop longer than the legitimate
minimum of 2.

### 9.2 Which condition each candidate is closest to failing

"It passed all twelve" is true of 5,757 seeds and therefore says nothing about
any one of them. The useful per-seed answer is the **margin on its tightest
condition**:

| seed | tightest condition | its value | limit | margin |
|---|---|---|---|---|
| 3530 | `no_mid_run_dead_zone` | 1.70 s | ≤ 4.0 | **2.30 s** |
| 2281 | `last_tile_has_tension` | 3.74 s | ≥ 1.5 | 2.24 s |
| 12183 | `last_tile_has_tension` | 3.55 s | ≥ 1.5 | 2.05 s |
| 37169 | `tail_is_proportionate` | 0.3982 | ≤ 0.40 | **0.18 pp** |
| 8949 | `tail_is_proportionate` | 0.3824 | ≤ 0.40 | 1.76 pp |
| 14694 | `no_mid_run_dead_zone` | 2.19 s | ≤ 4.0 | 1.81 s |
| 15517 | `no_mid_run_dead_zone` | 2.19 s | ≤ 4.0 | 1.81 s |
| 13968 | `tail_is_proportionate` | 0.3811 | ≤ 0.40 | 1.89 pp |
| 8108 | `tail_is_proportionate` | 0.3992 | ≤ 0.40 | **0.08 pp** |
| 30725 | `no_mid_run_dead_zone` | 2.19 s | ≤ 4.0 | 1.81 s |
| 17276 | `no_mid_run_dead_zone` | 2.13 s | ≤ 4.0 | 1.87 s |
| 37393 | `tail_is_proportionate` | 0.3954 | ≤ 0.40 | 0.46 pp |
| 9521 | `no_mid_run_dead_zone` | 2.04 s | ≤ 4.0 | 1.96 s |
| 35688 | `last_tile_has_tension` | 2.99 s | ≥ 1.5 | 1.49 s |
| 2427 | `tail_is_proportionate` | 0.3832 | ≤ 0.40 | 1.68 pp |
| 36557 | `no_mid_run_dead_zone` | 1.69 s | ≤ 4.0 | 2.31 s |
| 33377 | `no_mid_run_dead_zone` | 2.13 s | ≤ 4.0 | 1.87 s |
| 15088 | `no_mid_run_dead_zone` | 1.73 s | ≤ 4.0 | 2.27 s |
| 5672 | `last_tile_has_tension` | 2.99 s | ≥ 1.5 | 1.49 s |
| 26267 | `last_tile_has_tension` | 4.04 s | ≥ 1.5 | 2.54 s |

**Five of the top twenty sit within 2 percentage points of the tail-share
ceiling, and two within half a point.** That is not an accident: the score
rewards a long final tile (`tail_tension` peaks at 4 s) while the rule caps how
much of the run the ending may occupy, so the highest-scoring seeds are pushed
up against `tail_is_proportionate` by construction. The rule bounds and the
score optimises inside the bound; at the very top of the ranking they meet.

The practical consequence for whoever picks the production seed: **seeds 8108
and 37169 would flip to rejected if the tail-share threshold moved by a
fifth of a point.** If robustness to a threshold revision matters more than the
third decimal of the score, **3530 is the better pick** — it is the top-scoring
seed *and* its tightest margin is 2.30 s on a condition nothing else is pressing.

### 9.3 The texture is the same across the shortlist

The duplicate-share thirds are the most telling column. Every shortlisted seed
runs roughly **0.40 / 0.78 / 0.91**: in its first third, six contacts in ten
light something new; by its last third, nine in ten are repeat hits on a nearly
full arena. That progression *is* the retention shape, measured on the collision
stream rather than inferred from the clock, and it is remarkably consistent
across seeds that differ by 50 collisions in total length.

No final production seed is picked here, as the brief instructed.

---

## 10. Decision gate

# NATURAL PHYSICS SUFFICIENT

Recommend staying with pure physics plus seed selection. Do not add assistance
mechanics. The evidence:

**1. Good runs are abundant, not rare.** At 17 × 3, gravity 0, 85 wu/s:

| standard | share of seeds | per 50,000 |
|---|---|---|
| lands in 25–40 s | 50.8% | 25,400 |
| lands in 28–38 s | 35.1% | 17,570 |
| lands in 30–36 s | 21.8% | 10,910 |
| passes all twelve conditions | 11.5% | 5,757 |

The first three rows are measured over the 20,000-seed sensitivity sweep and the
last over the 50,000-seed candidate search; the 20,000-seed sweep puts full
acceptance at 11.41%, so the two agree to within a tenth of a point.

**2. The conclusion is not an artefact of where the lines were drawn.**
`phase2_threshold_sensitivity.json`, 20,000 seeds scored against five rules:

| rule | accepted | per 50,000 |
|---|---|---|
| very loose (20–50 s, gap ≤ 8 s, final tile 0.8–16 s, tail ≤ 0.60) | 58.05% | 29,022 |
| loose (22–45 s, gap ≤ 6 s, final tile 1.0–12 s, tail ≤ 0.50) | 37.95% | 18,975 |
| **default** (25–40 s, gap ≤ 4 s, final tile 1.5–9 s, tail ≤ 0.40) | **11.41%** | **5,705** |
| strict (28–38 s, gap ≤ 3 s, final tile 2–7 s, tail ≤ 0.33) | 1.48% | 738 |
| very strict (30–36 s, gap ≤ 2.5 s, final tile 2.5–6 s, tail ≤ 0.28) | 0.12% | 58 |

Even the *very strict* rule — a 30–36 s run that never stalls for 2.5 s, ends on
a final tile between 2.5 s and 6 s, and spends under 28% of its length on the
last 10% of tiles — still yields 58 seeds per 50,000. That is roughly one in
860, and a 50,000-seed sweep takes four and a half minutes.

**3. Searching is effectively free.** 5.4 ms per seed. Finding a hundred
candidates at the *strict* standard costs about six minutes of one CPU core.
There is no economic argument for assistance.

**4. The runs are good in shape, not merely in length.** The median seed already
has the retention curve the brief asked for (section 8.1): immediate activity,
steady visible progress, smooth monotone deceleration, and a last tile worth 26×
the opening pace — with no discontinuity anywhere across the 51 steps.

**5. The one real pathology is gone.** Zero A-B-A-B patterns in 50,000 seeds
against a 4,214-collision worst case at 16 sides; the residual period-4 and
period-8 cycles affect 0.65% of seeds and are already rejected by an existing
condition.

### 10.1 What is genuinely not solved, stated plainly

- **The population tail is heavy and always will be.** p99 completion is 254.9 s
  and the worst seed in 50,000 takes 1,691.8 s. This is coupon-collector
  structure (section 7.3), not a fixable defect. It does not matter because the
  pipeline selects seeds; it would matter enormously if anything ever filmed an
  *unselected* seed. **Category 3 needs a seed-acceptance gate in the production
  pipeline, exactly as the races do.** That is the one hard requirement this
  phase hands forward.
- **0.20% of seeds never complete** within 8,000 collisions. Rejected by
  `completes`; worth knowing the population is not 100%.
- **The ending is where all the variance lives** (section 8.2). Selection buys
  the last twenty tiles and nothing else. If a future brief wants the *middle*
  changed, selection cannot do it.
- **Nothing here is a rendering result.** Readability at 85 wu/s, trail strobing,
  and whether a 3.4 s final-tile hunt reads as tension on a phone screen are all
  unverified. Phase 1 already found the instrument renderer strobes at 60 wu/s.

---

## 11. Failure population

`phase2_population_50k_speed60.json`, `failures` block. Two populations, and they
are not the same problem.

### 11.1 Runs that never finish — 101 in 50,000 (0.20%)

Every one stopped at the 8,000-collision cap. None faulted, none lost energy,
none left the arena. Tiles still dark at the cap: median 5, p90 21, max 40.

**The missing tiles are spread uniformly over all 17 sides** — between 44 and 60
missing tiles per side across the 101 runs. That is direct confirmation that
gravity 0 removes Phase 1's directional bias: under gravity 12 the bottom three
sides took 1.87× the hits of the top three and the last tile landed in the upper
half in 55% of runs. There is now no preferred region, so an incomplete run is
unlucky rather than starved.

### 11.2 Runs that finish badly — the real failure mode

At speed 60, over 50,000 seeds:

| what is wrong | share |
|---|---|
| too slow, over 40 s | 69.4% |
| too slow, over 60 s | 25.0% |
| mid-run dead zone over 4 s | 57.5% |
| mid-run dead zone over 8 s | 20.2% |
| final tile over 10 s (a wait) | 27.6% |
| final tile under 1 s (no ending at all) | 17.2% |
| two-tile loop over 6 collisions | **0.0%** |
| too fast, under 25 s | 3.4% |

The "too slow" rows are what the speed change of section 5 fixes wholesale. The
rest is what selection is for. Note that **17.2% of runs have no ending at all** —
the 51st tile arrives within a second of the 50th — a failure mode a naive
"shortest run wins" search would actively select for. That is why
`last_tile_has_tension` exists as a condition rather than as a preference.

## 12. Tests

`tests/test_tile_escape_phase2.py` — **58 tests**, all passing in 15 s
including a cross-process subprocess check. Phase 1's `tests/test_tile_escape.py`
— **39 tests** — is **unmodified** and still passes.

### 12.1 The focused tests the brief asked for

| area asked for | tests | what they actually pin |
|---|---|---|
| 51-tile generation | 4 | 17 × 3 = 51, unique ids, three tiles on every side exactly once, every tile wider than the ball, and that the locked base config *is* gravity 0 / speed 60 / restitution 1 / circumradius 10 |
| deterministic evaluator output | 4 | same seed range twice, order independence (forward vs reversed batch vs each seed alone), shortlist determinism, a fresh-interpreter run agreeing with this one |
| milestone extraction | 5 | fractions round up; a missed milestone is `None` and not 0.0; milestones are non-decreasing; the 95% / 49-of-51 coincidence at 51 tiles and its absence at 100 |
| stagnation measurement | 5 | the longest gap is found *and located*; the first gap runs from t=0, not from the first event; an incomplete run's dead tail counts; a gap inside the final three tiles is the ending and not a body gap |
| tail timing | 4 | all four clocks against a hand-built stream with known answers; the tail share; the final tile against an ordinary one; the four clocks' ordering on real runs |
| repeating-pattern detection | 7 | A-B-A-B found and named period 2; longer cycles found; ties prefer the smaller period; a pattern that repeats only once is ignored; Phase 1's seed 134 loop is caught at 16 sides and absent at 17 |
| candidate acceptance/rejection | 7 | a control stream passes all twelve; **each condition has a case that fails it alone**; every failure is reported, not just the first; the rule is data and a different rule gives a different answer; the score shows its working and ranks but never accepts |
| batch reproducibility | 5 | as above, plus that every shortlisted seed re-simulates to exactly its recorded evaluation |

### 12.2 Three tests worth calling out

**The evaluator is tested against hand-built event streams, not only against
simulation output.** `_fake_run` constructs a run whose activation times are
exactly what the test asked for, so "the longest gap is 9.5 s and it begins at
10.0 s with 20 tiles lit" is checked against a stream where that is true by
construction, rather than against whatever the physics happened to do.

**Every acceptance condition has a test that makes it fail.** A threshold that
can never fire is decoration. Six conditions are broken one at a time by a
targeted mutation of a passing stream; the remaining six are covered by the
incomplete-run, 16-sided-loop and all-conditions-listed tests.

**Speed invariance is pinned in both directions.**
`test_zero_gravity_makes_speed_a_pure_rescaling_of_the_clock` asserts it holds
at gravity 0, and `test_the_same_claim_does_not_hold_once_gravity_is_switched_on`
asserts it **fails** at gravity 12 — otherwise a future change could leave the
first test passing while it measured nothing.

### 12.3 No Phase 1 test was changed

The brief allowed updating a Phase 1 test if a deliberate specification change
required it. **None did.** Phase 1's isolation test allows only
`{__future__, argparse, dataclasses, hashlib, json, math, os, PIL, random,
struct, sys, time, typing, satisfying}`, and the three new modules were written
to stay inside that set — the nearest-rank `percentile` helper is hand-written
rather than taken from `statistics`, and the CSV writers use plain `open`
instead of `csv`, for exactly this reason. No Phase 1 test was touched.

### 12.4 Regression tests

| suite | result |
|---|---|
| `tests/test_tile_escape.py` (Phase 1, 39 tests) | **pass**, file unmodified |
| `tests/test_tile_escape_phase2.py` (Phase 2, 58 tests) | **pass** |
| `test_this_branch_changed_no_race_fight_or_v30_code` x 3, plus their three `test_the_branch_guard_still_refuses_...` partners | **pass** (6 tests) |

The branch guards are the ones that matter most here, because they are the
tests Phase 1 had to work around: they diff `origin/main...HEAD` and reject any
file added under a declared production root. They pass because nothing was added
under one.

### 12.5 Why no existing behaviour can have changed

`git status` on this branch lists **19 untracked files and zero modified files**.
Every path is new: three modules under `satisfying/`, one test file under
`tests/`, one report and fifteen evidence files under `docs/`. No existing
module, test, fixture or configuration file was edited, renamed or deleted, and
nothing under `satisfying/` is imported by anything outside it - Phase 1's
`test_no_other_category_imports_category_three` walks sixteen subsystem roots
and asserts exactly that, and it still passes.

So no pre-existing test can have changed behaviour through this branch: there is
no edited code for it to observe. **No unrelated test guard was modified,
skipped or xfailed to make anything pass.**

The repository's full suite carries a set of failures that predate this branch
and belong to other workstreams; it is slow enough that a full before-and-after
comparison was not run for this phase, and the argument above is the stronger
one in any case - a diff of pure additions cannot regress a test that does not
import them.

## 13. Evidence

All under `docs/validation/category3_tile_escape/`. Raw, machine-readable, and
regenerable from the commands in each file's originating task.

| file | what it holds |
|---|---|
| `phase2_population_50k_speed60.json` | Part 1: the 50,000-seed validation at the locked base speed |
| `phase2_population_10k_speed60.json` | the 10,000-seed population the brief specified |
| `phase2_population_50k_speed85.json` | the same at the recommended speed |
| `phase2_population_10k_sides16.json` | the 16-sided control for the periodic-orbit comparison |
| `phase2_speed_sweep_suggested.json` | Part 2: 50, 55, 60, 65, 70 wu/s × 10,000 seeds each |
| `phase2_speed_sweep_widened.json` | Part 2 widened: 75–120 wu/s × 10,000 seeds each |
| `phase2_speed_invariance.json` | 720 run pairs proving speed is a change of clock, plus the arena-scale check |
| `phase2_activation_percentiles_speed60.csv` / `.json` | activation curve, one row per tile, population percentiles |
| `phase2_activation_percentiles_speed85.csv` / `.json` | the same at the recommended speed |
| `phase2_shortlist_speed85.json` | the 20 candidates, every metric, every verdict, full precision |
| `phase2_shortlist_curves_speed85.csv` | the candidates' own activation curves, 1,040 rows |
| `phase2_threshold_sensitivity.json` | the decision gate's robustness check across five acceptance rules |
| `phase2_coupon_collector_baseline.json` | the simulated iid baseline section 7.3 compares the billiard against |

Reproducing any of it:

```
python -m satisfying.tile_sweep_cli population  --count 50000 --speed 60
python -m satisfying.tile_sweep_cli speed       --count 10000 --speeds 50 55 60 65 70
python -m satisfying.tile_sweep_cli invariance  --count 60 --speeds 30 40 50 55 60 65 70 80 90 100 120 150
python -m satisfying.tile_sweep_cli candidates  --count 50000 --speed 85 --top 20
python -m satisfying.tile_sweep_cli curves      --count 10000 --speed 85
python -m satisfying.tile_sweep_cli inspect     --seed 3530 --speed 85 --log
```

---

## 14. Recommendation for Phase 3

Not implemented here, as instructed. In priority order:

1. **Set the production speed to 85 wu/s** (region 75–90). This is a one-line
   config change and it is the whole of the pacing fix. Keep the arena at
   circumradius 10 — section 4.2 shows scale is not an independent lever.
2. **Build the seed-acceptance gate into the pipeline.** This is the one hard
   requirement Phase 2 hands forward. The population tail is structural, so
   nothing may ever film an unselected seed. `satisfying.tile_sweep.shortlist`
   plus an `AcceptanceRule` is the gate; it needs a home in the production
   workflow and a recorded rule version alongside each rendered seed, exactly as
   the races record theirs.
3. **Do not add assistance mechanics.** No steering, no magnetism, no moving
   targets, no extra balls, no relocation. The supply of naturally good runs is
   5,757 per 50,000 at the default standard and 738 per 50,000 at a much stricter
   one; the honest option is also the cheap one, and the premise of the format is
   that nothing is faked.
4. **Verify readability at 85 wu/s before anything else is built.** This is the
   only unvalidated assumption left in the recommendation. The ball crosses the
   arena in ~0.24 s and impacts land 11 frames apart at 60 fps. Phase 1 found the
   instrument renderer's trail strobes at 60 wu/s; at 85 it will strobe harder.
   If 85 proves unreadable, the sweep table in section 5 says exactly what each
   slower speed costs, and the answer is a few percentage points of yield rather
   than a redesign.
5. **Build the Godot scene, and export from the event stream.** Phase 1's advice
   stands and Phase 2 strengthens it: a run is a list of flights and a list of
   timestamped activations, and `activation_curve` already emits the progress
   data a renderer or an audio pass needs. `satisfying/tile_render.py` remains a
   measuring instrument and should not grow into a renderer.
6. **Map the musical-note system onto the collision list.** At 85 wu/s a run is
   ~5.3 events per second — about 16th notes at 120 BPM — and the
   duplicate-share thirds (0.40 / 0.78 / 0.91) give a natural three-movement
   structure: new notes early, mostly repeats late.

### 14.1 If a future brief overrules the decision gate

Phase 2 did not need escalation mechanics and does not design them. If a later
brief wants one anyway, the measurements above say where it would have to act and
what it would have to beat:

- The only thing worth escalating is **the last twenty tiles**, because that is
  where all the variance is (section 8.2). An escalation that fires before 60%
  progress would be changing a part of the run that is already identical in every
  seed.
- A second ball is a **second coupon sampler**, which would roughly halve the
  expected tail — that is the size of the prize, and it is bounded by section
  7.3's arithmetic rather than by taste.
- Any such mechanic must be **visible and rule-like** — released at a stated
  progress threshold, not eased in — because the format's premise is that the
  viewer is watching physics. An invisible nudge would be indistinguishable from
  the drift that made Phase 1 reject "escaping by rounding error".

Phase 2 stops here.

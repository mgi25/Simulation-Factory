# Category 3, Test #2 redesign — MULTIPLYING SHELL ESCAPE, Phase 1

**Decision: MULTIPLYING MECHANIC PASSED — READY FOR NEW VISUAL/AUDIO PROOFS**

One ball starts inside five nested rotating segmented shells. Every time a ball
gets through a shell it has not been through before, it becomes two. The child
is a real simulation object with its own trajectory, its own damage
contribution and its own right to reproduce, so growth is recursive and the
second half of a run is busier than the first half *because of what happened in
the first half*.

That last sentence is the whole point of the redesign, and it is the one thing
this phase had to prove rather than assert. It is measured on 20,000 seeds:
the meaningful-event count in the last third of a run exceeds the first third's
in **99.35%** of runs, with a median ratio of **2.67**.

---

## A. Git and base

| | |
|---|---|
| Base branch | `category3-shell-escape-v1` |
| Base SHA | `42cdbb34588f052be45377d7c20c89d8100fcf99` |
| New branch | `category3-multiplying-shell-v1` |
| Worktree | `projects/wt-category3-multiplying-shell` (isolated, created for this phase) |
| Merged to main | no |
| History rewritten | no |

`category3-shell-production-v4` — the rejected V4 production master at
`afd503b` — was not branched from, checked out, or touched. Nothing in
`satisfying/shell_*.py`, `satisfying/tile_*.py`, `company/`, `race*/`,
`marble3d/` or `sloped/` was modified. The redesign is additive: five new
modules and one new test file.

The one coupling worth naming: the new simulation **imports the single-ball
contact solver** (`_ShellState`, `_nearest_live`, `_contact_in_interval`,
`_band_intervals`, `_boundary_crossing`, `_is_post_contact`, `_near_miss`) from
`satisfying.shell_escape` rather than copying it. Those are the pieces whose
correctness argument took the whole of the single-ball phase to establish — the
curvature bound, the two-nearest-panel rule for corners, the two-point
verification of a Newton step — and a second copy would be a second thing to
keep right. `shell_escape` itself is unchanged, so schema
`category3-test2-shell-escape/1.0.0` and the branch that pins it are unaffected;
`test_the_borrowed_solver_primitives_still_exist` pins the six signatures so a
future rename in `shell_escape` fails loudly here rather than silently.

### Files added

```
satisfying/multishell_seeds.py       independent seed streams
satisfying/multishell.py             config, schema V2, the multi-ball simulation
satisfying/multishell_evaluator.py   metrics, thresholds, flags, batch summaries
satisfying/multishell_playback.py    the canonical playback document
satisfying/multishell_cli.py         batch / sweep / shortlist / document / verify
tests/test_multiplying_shell.py      66 tests
docs/category3_multiplying_shell_phase1.md
docs/validation/category3_multiplying_shell/*.json
```

---

## B. New architecture

The single-ball simulation was one loop over one ball. With a population that
shape is wrong, and wrong in a way that is invisible until it corrupts a run: a
panel that breaks at t = 11.2 must be broken for every ball that reaches it
after 11.2 and intact for every ball that reached it before, and a per-ball
loop run to completion one ball at a time gets that wrong in both directions.

So the redesign is an **event scheduler over a shared arena**:

- Every ball carries its own cached next event — a panel contact, a region
  crossing, an escape, or the horizon — computed by `_resolve_next_event`,
  which is the single-ball loop's top half lifted out unchanged.
- The globally earliest event is processed. Ties go to the lower ball id,
  because that is the only thing that makes a tie deterministic.
- **When a panel breaks, every ball's cached event is discarded and recomputed.**

That invalidation rule is sound for two reasons, both of which matter. Events
are processed in non-decreasing time order, so at a break every other ball's
stored state is at or before the break and its cached event is at or after it —
recomputing from where the ball stands is therefore valid. And removing
material can only move a contact later, never earlier, so the recomputation can
only ever find the same answer or a later one. It is also cheap, because breaks
are rare (a median of 12 per run).

Without it a ball would rebound off a panel that no longer exists — a ghost
wall, and one that `anomalous_crossings` would never see, because no region
boundary is involved. `test_no_ball_ever_bounces_off_a_hole` is the check that
would catch it: over 120 seeds and 5,000-plus collisions, no collision event
ever names a slot that started open or has already broken.

### Cost

Measured back to back in one process, 200 seeds each:

| | single ball, 6 shells | multiplying, 5 shells |
|---|---|---|
| mean wall time per run | 11.3 ms | 19.1 ms (p50 16.8, p95 40.8) |
| mean collisions per run | 62 | 114 |
| simulate **and** evaluate, 12 workers | — | 128 seeds/s |
| 20,000-seed validation batch | — | 2.6 min |

1.7× the cost for a population of ten balls, because the expensive part is the
contact search and each ball only pays for its own. Two and a half minutes for a
full 20,000-seed batch is what let the parameter search below be eleven separate
controlled sweeps rather than one blind multidimensional grid.

---

## C. Reproduction model

**The rule.** A ball that crosses a shell outward, for the first time for that
ball at that shell, continues unchanged and a child appears beside it.

**The anti-farming rule.** Each ball carries a bitmask of the shells it has
already been paid for. A child born outside shell *k* starts with bits 0…*k*
set. Falling back inward through a hole is still allowed — it is the drama the
concept asks for, and forbidding it would be steering — but coming back out
through a shell already credited produces nothing. A ball can therefore produce
at most `shell_count` children in a whole run, one per shell.

The bitmask is one line, so the tests do not check it against itself. They check
the **event stream**:

- No `(parent, shell)` pair appears twice, over the 120-seed test population and
  over all 20,000 batch seeds. `reproduction_violations = 0` in both.
- The situation the rule exists for is asserted to actually occur:
  `test_repeated_crossings_do_not_farm_children` fails if no ball in the whole
  population ever re-crossed a credited shell, so a green suite cannot mean
  "the rule was never exercised".

**Credited on the crossing, not on the birth.** A spawn refused by the
population cap still spends the ball's claim on that shell. Nothing ever removes
a ball from the population, so there is no later moment at which the refusal
could be revisited, and pretending otherwise would leave a claim permanently
open.

**Child spawn physics.** The parent's trajectory is untouched. The child is born
`spawn_lead_ball_radii × ball_radius` (1.04 units) ahead of the parent along its
own heading, with the parent's speed and the parent's heading turned by
`spawn_turn = 0.16 rad`.

The turn's sign is `+` on even-numbered spawns and `−` on odd ones. This is:

- **deterministic** — no RNG stream exists for reproduction at all;
- **symmetric** — exactly balanced within every run (asserted: the counts differ
  by at most one), so the split cannot bias which way children go;
- **independent of the geometry** — it reads nothing about where the openings
  are, so it cannot aim a child at one;
- **not outcome steering** — a seeded random split would be strictly worse,
  because it would put a random number between the physics and the outcome and
  make "the child got lucky" a thing the seed decided rather than a thing the
  geometry decided.

**No child inside solid geometry.** If the nominal birth point is inside
material the lead is halved, repeatedly, and the last rung is a lead of zero —
the parent's own position, which is provably clear because the parent is a
non-penetrating ball standing there. The lead used and the clearance achieved
are both written into the spawn event, so this is measured and not promised.
Over 20,000 seeds the **minimum spawn clearance was 8.93 × 10⁻⁷**, positive,
and the ladder is exercised: both the full lead and shorter rungs occur.

**Population safety limit.** `max_population = 32`. Over 20,000 seeds it was
**never reached** — `spawns_suppressed = 0` on every run, and the largest
population observed was in the 20–24 bucket (10 runs). The cap is a guard, not
the mechanic, which is what the brief asked for. A test drives it deliberately
(`max_population = 3`) to prove the limit holds and that the suppression is
counted rather than hidden.

---

## D. Lineage model

Every ball carries a stable deterministic identity, in both the records and the
event stream:

| field | meaning |
|---|---|
| `ball_id` | dense integer from 0, in creation order |
| `parent_id` | `None` for the founder |
| `generation` | parent's generation + 1 |
| `birth_time` | the crossing that created it |
| `birth_shell` | the shell the parent had just crossed |
| `lineage` | the whole ancestral chain, root first |
| `credited_at_birth` | shells 0…`birth_shell`, the pre-charged ledger |
| `credited` | shells credited by the end of the run |
| `visited` | the regions the ball actually stood in |
| `children` | the ids it produced |

`visited` is not decoration. It is what makes the difficulty curve honest: a
child born outside shell 3 has never been inside regions 0–2, and counting it
among the balls that "reached" shell 0 and failed to cross it makes every inner
shell look harder than it is. `max_region` cannot answer this. Measured with
`max_region` the pass-rate curve comes out inverted; measured with `visited` it
comes out monotonic. That difference is the single largest measurement trap this
phase found.

A whole run reads like this (seed 7, `describe --seed 7`):

```
ball 0  gen 0  born  0.000  -        children [1, 3]  visited [0,1,2]
ball 1  gen 1  born  0.541  shell 0  children [2, 7]  visited [0,1,2,3]
ball 2  gen 2  born  0.900  shell 1  children []      visited [0,1,2]
ball 3  gen 1  born  1.013  shell 1  children [4, 6]  visited [1,2,3,4]
ball 4  gen 2  born  5.123  shell 2  children [5]     visited [0,1,2,3,4]
ball 5  gen 3  born  9.996  shell 3  children []      visited [3,4]
ball 6  gen 2  born 10.091  shell 3  children []      visited [2,3,4]
ball 7  gen 2  born 18.515  shell 2  children [8]     visited [3,4]
ball 8  gen 3  born 21.041  shell 3  children [9]     visited [4,5]  ESCAPED
ball 9  gen 4  born 21.628  shell 4  children []      visited [5]
```

Four things in that table are the redesign working. Ball 4, born outside shell
2, later falls all the way back to region 0 and climbs out again — the `visited`
list says so and the anti-farming rule paid it nothing for the repeat. Ball 7 is
born at 18.5 s, two thirds of the way in, and is the parent of the ball that
gets out; the run's outcome is decided by a ball that did not exist for most of
it. Ball 8 escapes at 21.717 s with lineage `[0, 1, 7, 8]` — a great-grandchild.
And ball 9 is born at 21.628 s *outside the outermost shell*, in the region a
ball reaches only after clearing shell 4: it exists for 89 milliseconds and
never crosses anything, which is the case that broke the escape event's route
attribution until it was fixed (§N).

Median generations reached over 20,000 seeds: **4** (p95 = 5, the maximum
possible with five shells). The escaping ball is a descendant, not the founder,
in the large majority of successful runs — median escape generation **2**.

---

## E. Progressive difficulty

Two dimensions, both physical and both legible on screen: **the holes get
smaller** and **the panels get stronger**. Nothing is hidden in a probability.

| shell | radius | panels | openings × slots | open fraction | gap ÷ ball diameter | break threshold |
|---|---|---|---|---|---|---|
| 0 |  6.0 | 12 | 3 × 2 | 0.500 |  7.12 | 1.6 |
| 1 | 10.6 | 16 | 3 × 2 | 0.375 |  9.77 | 2.4 |
| 2 | 15.2 | 20 | 2 × 2 | 0.200 | 11.37 | 3.6 |
| 3 | 19.8 | 26 | 2 × 2 | 0.154 | 11.47 | 5.2 |
| 4 | 24.4 | 32 | 2 × 1 | 0.062 |  5.60 | 7.2 |

`difficulty_profile()` computes the table and checks its own monotonicity, so a
config whose middle shell is easier than the one inside it says so immediately
rather than three hours later in a batch.

**Rotation is deliberately not used to make one shell harder than another.**
`omega_falloff = 1` gives every shell the same 3.72 units/s surface speed — the
table above is flat in that column — so no shell is made difficult by spinning
faster than its neighbours. That keeps the outer shells from reading as a blur,
and it means the difficulty a viewer can see is the whole of the difficulty
there is.

The *global* rate is a different question, and the sweep corrects an earlier
reading of it. During exploration, on a smaller arena with wider openings, a
3.4× change in `omega_base` moved nothing measurable, and the working conclusion
was "rotation is not a dial at all". On the locked arena that is false:
`phase1_sweep_omega.json` takes `omega_base` from 0.20 to 0.90 and the escape
rate goes 51.4% → 65.9%, the median duration 18.3 → 15.5 s, and the outermost
shell's pass rate 0.134 → 0.170.

The reason is the hole size. When an opening is wide, a ball arriving anywhere
near it gets through whatever the shell is doing; when the outermost shell is
6.2% open, *when* the hole is in front of you starts to matter, and the shell's
rate sets that. So rotation's influence is conditional on the opening geometry,
and the exploratory conclusion was arena-specific rather than general. It is
recorded here because the same trap is waiting for anyone who re-tunes the
openings and assumes the rotation finding still holds.

`omega_base = 0.62` is kept because it is a legibility choice — fast enough to
read as motion, slow enough not to strobe — and the difficulty is carried by the
two dials a viewer can actually see.

### Measured, over 20,000 seeds

| shell | balls that stood in it | balls that got out | **pass rate** | blocked contacts | region ball-seconds | damage absorbed | panels broken |
|---|---|---|---|---|---|---|---|
| 0 | 4.19 | 4.00 | **95.4%** |  6.2 | 14.9 |  9.3 | 3.92 |
| 1 | 5.63 | 5.06 | **89.3%** | 13.0 | 25.5 | 18.3 | 4.56 |
| 2 | 6.96 | 4.87 | **67.5%** | 21.5 | 29.8 | 26.1 | 2.79 |
| 3 | 7.70 | 3.36 | **42.4%** | 21.0 | 25.0 | 22.3 | 0.91 |
| 4 | 5.29 | 0.69 | **15.6%** | 15.0 | 14.2 | 11.7 | 0.21 |

The pass rate falls monotonically outward, by a factor of six from the innermost
shell to the outermost. The config claims the shells get harder; the balls
agree.

A single run cannot say this — with four to seven balls reaching a shell, one
run's pass rate is a handful of Bernoulli trials and comes out non-monotonic
44% of the time. That is why `difficulty_inverted` is **not** a per-run flag:
flagging it would reject most of a healthy population for a property no single
run can carry. `summarise` reports `pass_rate_monotonic` over the batch instead,
which is the level the question lives at.

---

## F. New damage and break physics

The single-ball model added `(v_n / v_ref) ** 1.5` per contact and broke at a
fixed 1.6. Two things were wrong with it: the exponent was a fitted number with
no physical reading, and there was no floor, so a panel could be broken by an
accumulation of grazes a viewer would not believe had done anything.

### The model

```
f      = normal impact speed / damage_reference_speed
added  = ((f - floor) / (1 - floor)) ** 2      for f > floor, else 0
floor  = 0.08
```

At exponent 2 this is the **kinetic energy carried in the contact normal**,
scaled so a head-on hit at the reference speed is exactly `1.0` damage — a
statement with a physical reading, and one a test asserts arithmetically. Below
the chip floor a contact adds *nothing*: a graze is not "a little damage", which
is both what stone does and what a viewer expects. The shell's own threshold
then says how many reference hits that shell is worth, from 1.6 (two solid hits)
to 7.2 (seven).

### How much of this is a behaviour change: almost none, and that is worth saying

Both changes were swept rather than assumed, and the sweeps are deflating.
`phase1_sweep_damage_exponent.json` takes the exponent over 1.0 / 1.5 / 2.0 /
3.0: the escape rate moves between 61.9% and 65.0%, the median duration between
16.9 and 17.2 s, the median break count from 15 to 11. `phase1_sweep_damage_floor.json`
takes the floor over 0.0 / 0.04 / 0.08 / 0.16 and moves the median break count
from 13 to 12 and nothing else meaningfully. Over the 20,000-seed batch only
**0.18%** of damage events fall below the chip floor at all.

So the redesigned damage model is a **legibility and interpretation**
improvement, not a behavioural one. The exponent now means something (energy),
the unit now means something (one head-on reference hit), and the floor now
guarantees that a hit a viewer would call a graze does nothing — but at this
operating point grazes are rare, so the floor rarely fires. Claiming the new
model "fixed" the outcome would be false; what it fixed is that the numbers can
now be read, and that a configuration where grazes *did* become common would not
silently start breaking walls with them.

### Damage states

Five states at deterministic fractions of the shell's own threshold:

| state | ledger ÷ threshold |
|---|---|
| `healthy` | < 0.25 |
| `damaged` | ≥ 0.25 |
| `critical` | ≥ 0.55 |
| `fractured` | ≥ 0.80 |
| `broken` | ≥ 1.00 |

Every transition is its own `damage_state` event carrying the previous and the
new state, because the visual branch needs to know when to start drawing cracks
and the audio branch needs to know when to change a panel's voice. Transitions
only ever go forward, and every one of the four non-healthy states is reached in
the test population.

### Shared damage, which is the emergent behaviour

Contributions from different balls accumulate on one ledger, and the break event
records how many distinct balls paid for it. Over 20,000 seeds, **19,861 runs
(99.3%) contain at least one panel broken by more than one ball**, median 11
such breaks per run. An earlier ball softening a panel a later ball walks
through is not a hoped-for side effect; it is what almost every run does.

A break happens exactly once, the hole persists, nothing repairs, and a test
asserts that balls other than the breaker go through it —
`test_a_ball_can_use_a_hole_another_ball_made`.

### Route split

| | count | share |
|---|---|---|
| shell crossings through an original opening | 514,582 | 71.4% |
| shell crossings through a broken panel | 206,245 | 28.6% |
| **final escapes** through an opening | 9,723 | 77.4% |
| **final escapes** through a break | 2,835 | 22.6% |

Both routes are live at every shell and at the climax. Median 12 panels broken
per run, out of 86 solid panels in the arena — visible damage, not demolition.

---

## G. Physics-model comparison

Four collision models, 300–1,200 shared seeds each, on the locked arena.

| model | escape | dur p50 | speed drift p50 / p95 / max | repeat contacts | collision cap hits | anomalies | max penetration | impact sd | ms/run |
|---|---|---|---|---|---|---|---|---|---|
| **constant (production)** | 64.1% | 17.1 | 0 / 0 / 0 | **0** | 0 | 0 | 1.0e-11 | 1.91 | 61 |
| bounded 0.80–1.25 | 69.5% | 16.0 | **25.0 / 25.0 / 25.0** | 4 | 0 | 0 | 1.0e-11 | 2.26 | 55 |
| bounded 0.65–1.50 | 80.8% | 15.1 | **50.0 / 50.0 / 50.0** | 4 | 0 | 0 | 1.0e-11 | 2.72 | 54 |
| free (unbounded) | 86.3% | 12.7 | **+109 / +220 / +276%** | 0 | 0 | 0 | 1.0e-11 | 3.55 | 34 |
| no panel transfer | 46.7% | 15.6 | 0 / 0 / 0 | **1,709,078** | **79** | 0 | 1.0e-11 | 2.15 | **1,407** |

**The free model confirms the Fermi runaway at a larger scale than the
single-ball phase saw it.** Median speed drift +109%, 95th percentile +220%,
worst +276%. The run's clock becomes a thing the seed decides. Not usable.

**"No panel transfer" reproduces the chatter failure, far worse with a
population.** 1.7 million repeat contacts across 300 seeds, 79 runs exhausting
the collision budget, and a 23× slowdown. A ball arriving near-tangentially at a
post rebounds slower than the post sweeps in and is caught. Not usable.

**The bounded model was the interesting candidate and it lost on its own
evidence.** The idea was that a band would let impacts genuinely vary, which
would give the redesigned damage model more to say. What actually happens is
that the drift is *exactly* the band ceiling in every single run — p50 = p95 =
max = 25.0% — because the underlying process has a positive bias, so the ball
runs its whole life pinned at the top of the band. A band does not buy a
distribution of energies; it buys a 25% faster clock. The extra impact spread
(sd 1.91 → 2.26) is bought by letting the Fermi bias win, which shows up
directly as escape rate 64% → 70% and duration 17.1 → 16.0 s. It also
reintroduces repeat contacts the constant model has none of.

**So the constant-speed constraint stays**, and the instrument that says how
hard it is working is now reported two ways rather than one. Per contact, the
median run renormalises by **7.75%** (p95 10.3%) — the model is nearly
energy-conserving to begin with. The per-run *worst* correction is 67% at the
median, which is what a single number would have reported and would have been
badly misleading; both are in `summarise`.

### Ball-ball collisions — Option A, and the reason is not "simpler"

Exact equal-mass elastic contact between balls is implemented and can be turned
on (`ball_ball_collisions = True`). It is off in production, on four measured
grounds, against the 300-seed constant-speed reference (escape 69.3%, dur p50
16.1, breaks 11.9, penetration 1.0e-11, 35 ms/run):

| | constant | constant + ball-ball |
|---|---|---|
| ball-ball contacts | 0 | **78,933** (263 per run) |
| repeat contacts | 0 | **31,212** |
| max penetration | 1.0e-11 | **5.75e-08** (5,000×) |
| panels broken per run | 11.9 | **6.3** |
| escape rate | 69.3% | 79.0% |
| ms per run | 35 | 236 (6.7×) |

1. **It is not occasional drama, it is a gas.** 263 ball-ball contacts per run
   against 116 wall contacts. The balls spend more time hitting each other than
   hitting the arena.
2. **It halves the mechanic the redesign is about.** Breaks fall from 11.9 to
   6.3 per run, because balls deflect each other away from the walls before they
   can land a solid hit.
3. **It is incompatible with the constant-speed model, specifically.** The
   elastic exchange separates the pair; renormalising each ball's speed
   afterwards, independently, does not preserve that separation, so the pair
   re-contacts — 31,212 repeat contacts and a penetration five thousand times
   the constraint-free figure. Under the bounded model, where the clamp usually
   does not fire, the same run produces 13. This is a real interaction between
   two choices, not a tuning problem, and
   `test_the_constant_speed_constraint_and_ball_ball_contact_are_incompatible`
   pins it so it cannot be quietly re-enabled.
4. **It makes the outcome less uncertain** (69.3% → 79.0%) and costs 6.7× the
   runtime.

More physical complexity was not better here, and the numbers say why.

---

## H. Event schema V2

`category3-test2-multiplying-shell/2.0.0`. A new schema, not a mutation:
`satisfying.shell_escape.SCHEMA_VERSION` still reads
`category3-test2-shell-escape/1.0.0` and a test asserts it.

Eleven kinds. Every ball-scoped event leads with `ball_id` — asserted, so a
consumer can key on the first field without a lookup table.

| kind | fields after `kind` and `t` |
|---|---|
| `ball_spawn` | `ball_id, parent_id, generation, birth_shell, region, position, velocity, speed, turn, lead, clearance, spawn_index, population, lineage` |
| `collision` | `ball_id, shell_id, panel_id, region, position, contact_point, contact_angle, normal, velocity_in, velocity_out, impact_speed, speed, incidence, feature, grazing, radial_outward, panel_local_offset` |
| `ball_collision` | `ball_id, other_id, position, other_position, normal, velocity_in, velocity_out, other_velocity_in, other_velocity_out, impact_speed` |
| `near_miss` | `ball_id, shell_id, panel_id, opening_id, region, ball_position, ball_angle, opening_centre_angle, opening_half_width, angular_separation, arc_separation, arc_separation_ball_radii, relative_angular_speed, time_separation, signed_lead, criterion` |
| `damage` | `ball_id, shell_id, panel_id, contribution, cumulative, threshold, fraction, state, impact_speed, contributors` |
| `damage_state` | `ball_id, shell_id, panel_id, previous_state, new_state, cumulative, threshold, fraction` |
| `panel_break` | `ball_id, shell_id, panel_id, position, break_angle, cumulative, threshold, hits, contributors` |
| `shell_exit` | `ball_id, shell_id, panel_id, route, opening_id, from_region, to_region, position, crossing_angle, local_offset, dwell_seconds, first_for_ball, reproduced` |
| `shell_entry` | `ball_id, shell_id, panel_id, route, opening_id, from_region, to_region, position, crossing_angle, local_offset, dwell_seconds` |
| `escape` | `ball_id, shell_id, route, position, generation, parent_id, birth_time, birth_shell, lineage, collisions, breaks, population` |
| `failure` | `reason, horizon, active_balls, total_balls, frontier_region, frontier_balls, balls_by_region, collisions, breaks` |

`validate_events` checks every run field by field — no missing key, no extra
key, no renamed key — so schema drift is a test failure rather than a renderer
that silently draws nothing.

**Cause before effect.** A `ball_spawn` is emitted *after* the `shell_exit` that
caused it, at the same timestamp, and the exit carries `first_for_ball` and
`reproduced` so a consumer can tell a productive crossing from a barren one
without looking ahead.

### The playback document

`satisfying/multishell_playback.py` writes the canonical document the visual and
audio branches will consume, and nothing else. The inherited rule is unchanged:
*a consumer may read a trajectory and may not compute one.* With a population
the reason is stronger than before — a break caused by ball 7 at t = 11.2
changes what ball 3 does at t = 11.4, so a consumer that re-simulates gets not
just a different trajectory but a different cast.

The document adds `balls` (the lineage table), per-ball `flights` keyed by ball
id, `panel_states` (every panel's whole damage history, so a renderer draws the
right crack state at any `t` without replaying the damage stream) and
`population_samples`. `verify_document` re-simulates the seed and compares
digests, event counts, ball counts, flight counts and a whole-document hash.

---

## I. Batch statistics — 20,000 seeds

`docs/validation/category3_multiplying_shell/phase1_population_20k.json` — the
summary, the config and its digest, and the measured difficulty profile. The
20,000 per-seed records are **not** committed: they are 71 MB, and a repository
is not where that belongs. They are regenerated in 2.6 minutes with

```
python -m satisfying.multishell_cli batch --count 20000 --keep-records --out <scratch>.json
```

and the run is deterministic, so the regenerated records carry the same digests
as the ones the shortlist below was drawn from. `--keep-records` is off by
default for exactly this reason.

### Outcome

| | |
|---|---|
| seeds | 20,000 |
| escaped | 62.79% |
| timed out | 37.21% |
| hit the collision cap | 0 |
| usable (no flags at all) | 27.49% |
| escaped **and** 18–26 s | 26.52% (5,303 runs) |
| escaped **and** 20–24 s | 13.47% (2,694 runs) |

The outcome is genuinely uncertain. Roughly three runs in eight fail, and they
fail by running out of time with balls still working on an outer shell, not by
stalling: the collision cap was never reached and the longest gap between
meaningful events has a 95th percentile of **1.10 seconds**.

### Duration

| p5 | p25 | p50 | p75 | p95 |
|---|---|---|---|---|
| 5.9 s | 11.8 s | 16.6 s | 21.1 s | 24.9 s |

| 0–6 | 6–10 | 10–14 | 14–18 | 18–20 | 20–22 | 22–24 | 24–26 |
|---|---|---|---|---|---|---|---|
| 656 | 1,479 | 2,379 | 2,741 | 1,434 | 1,357 | 1,337 | 1,175 |

The median escape lands at 16.6 s, below the 20–24 s target, and the
distribution is broad — which is what an escape time set by a genuinely
uncertain search *is*. Two things make that acceptable rather than a miss.
First, 2,694 seeds escape inside 20–24 s and 5,303 inside 18–26 s, so the
shortlist is selecting from thousands, not scraping a tail. Second, and more
important, **the 20–24 s runs are not atypical runs that happened to be slow** —
their population, escalation, break count and route mix all sit on the
population's own medians (§J). Selecting for runtime is not selecting for
anything else.

The horizon is 26 s, so a timeout is itself a 26-second video in the brief's
broad band.

### Population

| | p5 | p25 | p50 | p75 | p95 |
|---|---|---|---|---|---|
| balls created | 7 | 9 | 10 | 12 | 14 |

| 4–7 | 7–10 | 10–13 | 13–16 | 16–20 | 20–24 | ≥24 |
|---|---|---|---|---|---|---|
| 847 | 6,515 | 8,979 | 3,274 | 373 | 10 | 0 |

Generations reached: p50 = 4, p95 = 5 (the maximum with five shells). Spawns:
p50 = 9. Spawns by shell: **1.00 / 1.98 / 3.07 / 2.65 / 0.69** — shell 0 always
produces exactly one child (the founder's first crossing), shell 2 is the most
productive, and shell 4 hardly ever pays out.

### Instruments — all clean

| | |
|---|---|
| max penetration, worst of 20,000 | 1.0014 × 10⁻¹¹ |
| min spawn clearance, worst of 20,000 | 8.93 × 10⁻⁷ (positive) |
| anomalous crossings | 0 |
| contact searches exhausted | 0 |
| reproduction violations | 0 |
| population cap reached | 0 runs |
| speed min / max across the batch | 10.000 / 10.000 |
| speed correction, mean per contact | 7.94% |

---

## J. Population and escalation curves

Mean ball count at ten points across the run, whole population and the 18–26 s
in-band subset:

| fraction of run | 0 | .1 | .2 | .3 | .4 | .5 | .6 | .7 | .8 | .9 | 1.0 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| all seeds | 1.00 | 2.03 | 2.96 | 3.84 | 4.68 | 5.51 | 6.31 | 7.13 | 7.99 | 8.86 | 10.38 |
| 18–26 s escapes | 1.00 | 2.21 | 3.20 | 4.05 | 4.97 | 5.82 | 6.64 | 7.48 | 8.37 | 9.34 | 11.35 |

Against the brief's target progression:

| stage | brief | measured (in-band) |
|---|---|---|
| start | 1 | 1 |
| early | ~2–4 | 2.2–3.2 |
| middle | ~4–8 | 5.0–6.6 |
| late | ~8–16 | 8.4–9.3 |
| climax | ~10–24 | 11.4 mean, p95 14, max 20–24 |

Growth is steady rather than explosive — roughly one ball per tenth of the run —
and nothing is capped.

**Every one of the 20,000 seeds reproduces at least once.** When it happens is a
distribution, not a constant:

| first split | p5 | p25 | p50 | p75 | p95 |
|---|---|---|---|---|---|
| seconds | 0.44 | 0.59 | **1.45** | 2.63 | 6.76 |

The median run announces the mechanic inside a second and a half, which is what
the hook needs. The tail does not: a twentieth of runs are still a single ball
at seven seconds, a third of the way through the video, with nothing on screen
that says what this is. That is a real failure mode for a Short and it was not
on the brief's list, so `slow_first_spawn` was added to the evaluator at 4.0 s.
It fires on **15.7%** of all seeds and **15.9%** of in-band ones, and every
shortlist candidate is under it.

### The escalation metric

"Meaningful events" are collisions, spawns, breaks, damage-state transitions,
near misses and shell crossings — everything a viewer or listener registers.
Raw `damage` events are deliberately excluded: they fire on every contact and
would make the metric a synonym for the collision count.

| late ÷ early ratio | p5 | p25 | p50 | p75 | p95 |
|---|---|---|---|---|---|
| meaningful events | 1.33 | 1.93 | **2.67** | 4.00 | 8.04 |
| collisions | 1.23 | 2.03 | 3.00 | 4.64 | 9.25 |
| population | 1.33 | 1.75 | 2.20 | 3.00 | 5.00 |

**99.35% of runs have more meaningful events in their last third than their
first.** No term was added to make this come out; it is a count of the stream
divided into thirds. The mechanism is visible in the components — the population
ratio alone is 2.20, and the collision ratio tracks it, which is exactly the
brief's "more balls → more collisions → more musical events".

---

## K. Audio-density proxy

This is the one place where the redesign has a real cost, and it should be
stated plainly rather than buried.

| | p5 | p25 | p50 | p75 | p95 |
|---|---|---|---|---|---|
| collisions/s, whole run (sustained) | 3.11 | 4.58 | **5.88** | 7.37 | **9.92** |
| collisions/s, peak 2 s window (burst) | 6.5 | 10.0 | **12.5** | 15.0 | **19.0** |
| meaningful events/s, whole run | 8.65 | 11.66 | 14.27 | 17.31 | 22.78 |

The brief's caution region is *sustained* 8–10 collisions/s. Measured against
the sustained figure — the whole-run mean — the median run sits at 5.9/s and
only the top 5% touch the caution region at 9.9/s. Measured against a two-second
burst, the median is 12.5/s and the 95th percentile 19/s.

Both numbers are true and they mean different things. A multiplying-ball concept
produces a collision rate proportional to the population by construction, so the
late-run bursts are not a tuning accident; they are the escalation the concept
is selling, heard as density. The evaluator therefore draws two separate lines —
`max_collision_rate = 9.0` on the sustained mean, `max_peak_collision_rate =
16.0` on the two-second burst — and the batch reports both distributions rather
than one verdict. `frantic_peak` is the most common flag on in-band runs (23.5%
of them), so a quarter of otherwise-good runtime candidates are excluded on
burst density alone, and the shortlist below is drawn from the rest.

The arena scale is what bought this. Collisions per second per ball is
`speed ÷ mean free path`, so widening the shells from 3.6 to 4.6 apart and
slowing the ball from 15 to 10 units/s took the sustained median from 11.9/s to
5.9/s and the two-second peak from 30.5/s to 12.5/s, at no cost to escalation.
That trade is the single most useful thing the parameter search found.

### What is left after a selection rule

The finding for the audio branch is that it must **select, not sonify
everything** — and the selection has to cut the *structural* stream as well as
the percussive one, which is the part that is easy to get wrong. Measured over
800 clean in-band seeds:

| layer | mean p50 | mean p95 | 2 s peak p50 | 2 s peak p95 |
|---|---|---|---|---|
| every collision | 5.87 | 8.10 | 12.50 | 16.00 |
| collisions on the ball's own frontier shell | 3.80 | 5.10 | 8.00 | 9.50 |
| …and impact ≥ 0.35 × speed | **3.68** | **4.92** | **7.50** | **9.50** |
| all damage-state changes | 3.25 | 4.39 | — | — |
| outward crossings (incl. the escape) | 1.73 | 2.75 | — | — |
| inward crossings | 1.63 | 2.81 | — | — |
| spawns | 0.44 | 0.59 | — | — |
| panel breaks | 0.62 | 0.90 | — | — |
| transitions to `fractured` | 0.46 | 0.76 | — | — |
| structural = spawns + breaks + `fractured` + outward crossings | 3.25 | 4.67 | 7.50 | 10.50 |
| percussive + structural together | 6.92 | 9.30 | 13.50 | 17.50 |

Two things fall out of this.

**Frontier hard hits are a usable percussive layer as they stand.** Keeping only
the collisions where a ball is hitting the shell it is currently trying to get
through, above a third of its speed, takes 5.87/s down to **3.68/s sustained and
7.5/s at the two-second peak** — inside the brief's caution region with room
over. It also throws away almost nothing dramatic: a ball hitting the shell
*behind* it is a backboard bounce, not an attempt.

**Sonifying "every meaningful event" would be worse than sonifying every
collision.** All damage-state changes alone run at 3.25/s and inward crossings
at 1.63/s; adding those to the percussive layer takes the combined stream to
6.92/s and a 17.5/s peak. The structural layer has to be cut to the events that
carry the story — spawns, breaks, the step to `fractured`, and outward progress
— which lands it at 3.25/s.

The combined voice stream escalates on its own: late-third over first-third
**2.59** median, above 1.0 in **100%** of the 800 runs, with mean event counts
per third of 28.6 / 50.9 / 74.3. The soundtrack does not have to build the
crescendo; it has to avoid flattening it.

---

## L. Failure modes

Every named failure mode from the brief, with the line it is drawn at and how
often it fired across 20,000 seeds.

| brief's failure mode | flag | line | fired |
|---|---|---|---|
| — (did not escape) | `failed` | — | 37.21% |
| instant escape, no suspense | `instant_escape` | < 12 s | 16.19% |
| excessive sonic/event density (burst) | `frantic_peak` | > 16 collisions/s in 2 s | 17.56% |
| excessive sonic/event density (sustained) | `frantic_mean` | > 9 collisions/s | 9.30% |
| too weak: population stays 1–3 | `population_weak` | < 5 total or < 4 at 2/3 | 5.58% |
| too explosive: 20+ almost immediately | `population_explosive` | > 8 at 1/4 of the run | 1.65% |
| first reproduction not quick | `slow_first_spawn` | first split after 4 s | 15.69% |
| all balls follow near-identical paths | `few_distinct_panels` | < 14 distinct panels | 3.35% |
| — | `clone_trajectories` | radius spread < 0.10 | 0.78% |
| late no richer than early | `no_escalation` | ratio < 1.15 | 2.01% |
| one mechanic irrelevant | `no_breaks` | 0 breaks | 0.48% |
| too sparse | `sparse` | < 1.5 collisions/s | 0.10% |
| orbit traps | `repetitive_orbit` | cycle run > 10, period ≤ 6 | 0.04% |
| long stalls | `dead_stretch` | > 4 s with no meaningful event | **0** |
| outer shell trivial | `outer_shell_trivial` | pass rate > 85% with ≥ 3 balls | **0** |
| runaway population | `population_capped` | any suppressed spawn | **0** |
| multiplication stalls at one shell | `too_few_generations` | < 2 generations | **0** |
| no opening route | `no_opening_progress` | < 2 opening crossings | **0** |
| farming | `spawn_farming` | any duplicate `(ball, shell)` | **0** |
| solver fault | `instrument_fault` | penetration, anomaly, exhaustion, bad spawn | **0** |

Two configuration-level questions cannot be answered by a single run and are
reported over the batch instead:

- **outer shell impossible** — 93.06% of runs get a ball into region 4 and
  63.04% get one out of it. Neither impossible nor trivial.
- **difficulty inverted** — `pass_rate_monotonic` is true over the batch. The
  per-run figure is 55.6%, which is what four-to-seven Bernoulli trials per
  shell looks like, and is why it is not a per-run flag.

Also measured and not flagged: **trajectory spread** (the coefficient of
variation of the population's radii, sampled ten times per run) has p5 = 0.197
and p50 = 0.322, so a clone swarm is not what these runs are; and **regressions**
— balls falling back inward through a hole — happen routinely, which is the
drama the concept asked for and which the anti-farming rule has to survive.

---

## M. Parameter search and candidate shortlist

### The search

Interpretable ranges were established one axis at a time before any joint
search, as the brief asked. Eleven controlled sweeps of 800 shared seeds each
are in `docs/validation/category3_multiplying_shell/phase1_sweep_*.json`:
`speed`, `spawn_turn`, `omega_base`, `shell_spacing`, `damage_floor_fraction`,
`damage_exponent`, `break_thresholds`, `opening_slots`, `openings_per_shell`,
`panel_counts`, `max_population`.

What the search actually found, in order of how useful it was:

1. **Arena scale is the density dial, and it is the reason this phase has a
   usable soundtrack.** `phase1_sweep_spacing.json`: shell spacing 3.6 → 5.1
   takes the sustained collision rate from 7.09/s to 5.27/s and the two-second
   peak from 15.5/s to 11.0/s, with escalation essentially unchanged
   (2.97 → 2.64). Combined with dropping the ball from 15 to 10 units/s, moving
   off the exploratory arena took the sustained median from **11.9/s to
   5.88/s**. Collisions per second per ball is `speed ÷ mean free path`, so
   widening the regions is the one lever that reduces density without reducing
   anything else.
2. **Break thresholds set the route mix, not the difficulty.**
   `phase1_sweep_break_thresholds.json`, from ×1 to ×5 of the exploratory base:
   the escape rate falls 84.6% → 50.0% and the median break count 18 → 2, but
   the striking move is the *escape route*, from **48.0% through an opening to
   97.0%**. Too tough and the break route stops existing; too soft and the
   arena is demolished. The chosen ×2 sits at 80.6% opening in the sweep and
   77.4% over the full batch, which keeps both routes live.
3. **Escape rate and duration trade off directly against each other**, because
   both are set by the outermost shell. `phase1_sweep_speed.json` is the
   cleanest view: speed 8 → 14 takes the escape rate 38.4% → 96.5% and the
   median duration 18.9 → 10.7 s, monotonically, with the 20–24 s yield peaking
   at 10.0. There is no setting that lengthens runs without costing successes.
4. **Population responds to the middle shells, not the outer ones.**
   `phase1_sweep_opening_slots.json`: widening shell 3 from one slot to two
   takes the final population 9.71 → 10.30, the escape rate 57.4% → 65.0% and
   shell 3's own pass rate 0.310 → 0.427, at a cost of 0.8 s of median duration.
   Widening the outermost shell instead (`[2,2,2,2,2]`) barely moves the
   population at all (10.00) and shortens the median run by 1.6 s, because an
   easier last shell ends the run sooner rather than filling it.
5. **The damage model's parameters are nearly inert** (§F). Worth knowing
   before anyone spends a day tuning them.
6. **The population cap is genuinely a guard.**
   `phase1_sweep_max_population.json`: caps of 32 and 64 produce byte-identical
   summaries, so 32 is never reached. A cap of 16 is *almost* identical — one
   run in 800 reaches 17 balls, and the mean final population differs by 0.012 —
   so even 16 is nearly inert. A cap of **8** is not: the escape rate falls to
   54.7%, the mean final population to 7.85, and the usable rate from 29.1% to
   **3.3%**. That is what a cap looks like once it has stopped being a guard and
   become the mechanic, and having it in the sweep is what makes "the cap is
   inert at 32" a measurement rather than an assertion.
7. **Rotation's influence is conditional on the opening geometry** (§E), which
   corrected an exploratory conclusion rather than confirming it.

### The operating configuration

```
shell_count         5
inner_radius        6.0          shell_spacing     4.6
panel_counts        (12, 16, 20, 26, 32)
openings_per_shell  (3, 3, 2, 2, 2)
opening_slots       (2, 2, 2, 2, 1)
panel_thickness     0.30
omega_base          0.62         omega_falloff     1.0     omega_jitter  0.22
ball_radius         0.40         speed             10.0
speed_model         constant     panel_momentum_transfer  1.0
ball_ball_collisions  False
reproduction        True         max_population    32
spawn_lead_ball_radii 2.6        spawn_turn        0.16
damage_reference_speed 10.0      damage_exponent   2.0     damage_floor_fraction  0.08
break_thresholds    (1.6, 2.4, 3.6, 5.2, 7.2)
damage_state_fractions (0.25, 0.55, 0.80)
horizon             26.0
```

### Shortlist

`docs/validation/category3_multiplying_shell/phase1_shortlist.json`. Eighteen
seeds, every one of them flag-free, drawn by bucket rather than by rank - a
ranked list would hand the next branches eighteen versions of whatever the
ranking favours. The buckets are the axes the brief named: runtime band, how
big the population got, whether the final escape came through an opening or
through a panel the balls had broken, and whether the escaping ball was the
original or a descendant. Two thirds of the list is filled from the 20-24 s
band before the wider 18-20 and 24-26 runs get a turn, because the brief asks
for that band and the band is not an equal dimension with the other three.
| seed | duration | first split | balls | gens | escape gen | escape route | coll/s | peak 2 s | breaks | shared | opening | break | escalation | near misses |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 13009 | 18.18 s | 3.32 s | 14 | 4 | 2 | opening | 7.59 | 14.0 | 13 | 12 | 37 | 8 | 7.36 | 4 |
| 16458 | 18.43 s | 1.75 s | 10 | 3 | 0 | break | 4.61 | 15.0 | 11 | 9 | 20 | 3 | 4.37 | 10 |
| 16067 | 18.56 s | 3.52 s | 9 | 4 | 2 | break | 5.82 | 15.5 | 10 | 10 | 20 | 4 | 7.22 | 7 |
| 368 | 19.46 s | 0.47 s | 12 | 5 | 2 | break | 5.34 | 13.5 | 14 | 13 | 28 | 7 | 6.07 | 5 |
| 17758 | 19.98 s | 3.57 s | 12 | 5 | 0 | opening | 6.46 | 15.5 | 10 | 9 | 23 | 9 | 4.79 | 7 |
| 949 | 20.16 s | 2.31 s | 8 | 5 | 3 | opening | 5.90 | 12.0 | 13 | 13 | 18 | 4 | 6.27 | 2 |
| 9091 | 20.81 s | 3.42 s | 13 | 6 | 5 | opening | 5.05 | 12.0 | 8 | 8 | 19 | 4 | 6.83 | 12 |
| 19998 | 21.59 s | 3.57 s | 15 | 5 | 0 | opening | 8.61 | 16.0 | 18 | 18 | 33 | 15 | 5.34 | 9 |
| 12004 | 21.71 s | 2.40 s | 15 | 5 | 2 | opening | 6.17 | 15.5 | 9 | 9 | 29 | 12 | 8.42 | 6 |
| 547 | 21.73 s | 2.25 s | 11 | 4 | 0 | opening | 5.25 | 10.0 | 14 | 13 | 31 | 3 | 6.76 | 12 |
| 11319 | 21.80 s | 1.47 s | 14 | 5 | 0 | break | 6.84 | 15.0 | 18 | 17 | 30 | 23 | 3.89 | 15 |
| 10038 | 22.35 s | 3.43 s | 12 | 4 | 1 | break | 6.22 | 16.0 | 14 | 14 | 21 | 11 | 5.24 | 4 |
| 3622 | 22.82 s | 0.45 s | 11 | 5 | 3 | break | 5.26 | 14.0 | 13 | 11 | 31 | 5 | 5.50 | 12 |
| 12818 | 22.84 s | 0.50 s | 15 | 5 | 0 | opening | 8.27 | 16.0 | 19 | 18 | 28 | 16 | 4.22 | 11 |
| 7183 | 23.21 s | 0.62 s | 13 | 5 | 3 | break | 6.68 | 15.0 | 16 | 15 | 21 | 20 | 4.78 | 8 |
| 17693 | 23.50 s | 3.55 s | 10 | 4 | 0 | break | 5.06 | 14.0 | 13 | 11 | 38 | 8 | 4.21 | 6 |
| 6625 | 23.87 s | 3.62 s | 13 | 5 | 0 | break | 7.08 | 14.5 | 17 | 17 | 37 | 15 | 3.11 | 16 |
| 3909 | 24.13 s | 1.53 s | 13 | 4 | 0 | break | 6.96 | 16.0 | 14 | 13 | 28 | 10 | 2.77 | 9 |

Coverage against everything the brief asked the shortlist to span:

| axis | spread |
|---|---|
| runtime | **12 of 18** inside 20-24 s, all 18 inside 18-26 s, from 18.18 to 24.13 s |
| moderate vs stronger escalation | 2.77 to 8.42, with candidates at every point between |
| population | 8 to 15 balls |
| opening-dominant routes | 17693 (38 opening crossings to 8 breaks), 13009 (37 / 8), 547 (31 / 3) |
| break-heavy routes | 7183 (21 / 20), 11319 (30 / 23), 12818 (28 / 16) |
| final escape route | 8 through an opening, 10 through a break |
| escaping ball | 9 founders, 9 descendants, to the fifth generation (9091) |
| lineage depth | 3 to 6 generations |
| first split | 0.45 to 3.62 s, all inside the 4 s line |
| near misses | 2 to 16 |
| burst density | 10.0 to 16.0 collisions/s at the two-second peak |

**No production seed is selected.** That is the next phase's decision, and
the list is deliberately not ranked.

Three are written out in full as canonical playback documents, chosen to span
the axes rather than to be the best three:

| seed | why | state digest |
|---|---|---|
| 12818 | 22.84 s, the biggest population in the list at 15 balls, 19 breaks, founder escapes through an opening, first split at 0.50 s | `5c96f6d7a185b523` |
| 7183 | 23.21 s, the most evenly mixed routes in the list (21 opening crossings to 20 breaks), a third-generation descendant escapes through a broken panel | `0915c69d8d9ca2c5` |
| 9091 | 20.81 s, the deepest lineage at six generations with a *fifth*-generation ball escaping, and the joint-lowest burst density at 12.0/s | `31e35cf2f5646bdb` |
---

## N. Tests and regressions

**New:** `tests/test_multiplying_shell.py`, 66 tests, 30 s.

Covering, in the brief's order: deterministic multi-ball simulation; stable
lineage ids; one child maximum per ball per shell; no repeated-crossing spawn
farming; child spawn outside solid geometry; deterministic spawn velocity;
increasing difficulty config; impact-based damage; deterministic damage-state
transitions; shared damage accumulation; break once; broken panel remains
passable; outer-layer success and failure; the population safety limit;
evaluator population metrics; event-density metrics; schema and digest
stability; no dependency on Godot, audio or rendering.

Four are worth naming because they check something a weaker test would miss:

- `test_repeated_crossings_do_not_farm_children` fails if the population never
  exercised the rule, so a green suite cannot mean "never tested".
- `test_no_ball_ever_bounces_off_a_hole` catches the ghost-wall failure that
  cache invalidation prevents and that `anomalous_crossings` cannot see.
- `test_a_break_by_one_ball_changes_what_another_ball_does` fails if breaks
  never happen with another ball in flight, which is the only case invalidation
  exists for.
- `test_the_constant_speed_constraint_and_ball_ball_contact_are_incompatible`
  records §G's finding as an executable fact rather than a paragraph.
- `test_every_escape_names_the_route_it_came_out_through` catches a real defect
  found late: a ball born *outside* the outermost shell reaches the escape
  radius without ever making a crossing of its own, so the run's headline event
  reported no route at all. That was 11.5% of successful runs. The fix is that a
  child inherits its parent's route, which is the hole it also came out of.
- `test_the_evaluator_reports_when_the_first_split_happens` exists because the
  number it reports contradicted an exploratory claim (§J): the median first
  split is 1.45 s, not the 0.9 s carried over from a different arena.

**Category 3 regressions:** `test_shell_escape.py`, `test_tile_escape.py`,
`test_tile_escape_phase2..6.py` plus the new file — **445 passed, 1 skipped, 0
failed** in 6 min 47 s. Test #1 and the single-ball Test #2 are green and
untouched.

The whole-repository suite was not run: per the brief, that is for final
production, and nothing outside `satisfying/multishell*` and
`tests/test_multiplying_shell.py` was changed.

---

## O. Decision

**MULTIPLYING MECHANIC PASSED — READY FOR NEW VISUAL/AUDIO PROOFS**

Against each pass condition:

| condition | evidence |
|---|---|
| reproduction works naturally | every one of 20,000 seeds reproduces; 9 spawns median, first split at a median of 1.45 s, spawns at all five shells |
| every ball can create descendants | median 4 generations, p95 = 5 (the maximum); escaping ball is a descendant at median generation 2 |
| no spawn farming exists | 0 violations in 20,000 seeds, checked on the event stream; re-crossings demonstrably occur and pay nothing |
| difficulty increases outward | pass rates 95.4 / 89.3 / 67.5 / 42.4 / 15.6%, monotonic, a factor of six |
| population escalates without exploding | 1 → 2.2 → 5.8 → 9.3 → 11.4; cap never touched; `population_explosive` 1.65% |
| break physics improved and stable | energy-based with a chip floor, five states, per-shell thresholds; 99.3% of runs contain a break paid for by more than one ball; 0 solver faults |
| success and failure remain genuine | 62.8% escape, 37.2% timeout, 0 collision caps |
| later stages meaningfully richer | late/early meaningful ratio p50 = 2.67, above 1.0 in 99.35% of runs |
| future audio density manageable | sustained median 5.9 collisions/s, inside the brief's caution region; burst density is a real constraint, quantified, and a frontier-hard-hit selection lands the percussive layer at 3.68/s sustained and 7.5/s peak |
| natural candidates near the target runtime | 2,694 seeds escape in 20–24 s; in-band runs sit on the population's medians for every other metric |

One condition is met with a qualification rather than cleanly: the **median
escape time is 16.6 s, not 20–24 s**. The band is reached by selection from a
large population rather than by the distribution being centred on it. That is
disclosed rather than tuned away, because the two available ways to move the
median — making the outermost shell harder, or lengthening the horizon — cost
either the escape rate or the target runtime, and because the in-band runs were
checked and are not a biased subpopulation.

---

## P. Recommendations for parallel visual and audio development

Not implemented. Listed for the branches that come next, with the number from
this phase that each one rests on.

### Visual

1. **Tint by lineage, not by index.** The document carries `lineage`,
   `generation` and `parent_id` on every ball. Descent is the story the mechanic
   is telling and it is currently invisible: a viewer sees a ball appear and has
   no way to know whose it was. Generation depth tops out at 5, so a five-step
   ramp covers every run.
2. **The hook is the first split, and it lands at a median of 1.45 s.** Whatever
   the split looks like has to read in well under a second, because it is over
   before a viewer has decided whether to keep watching. This is the single
   highest-leverage shot in the video and it is not the escape. Note the tail:
   the 95th percentile is 6.76 s, so the shortlist filters on it
   (`slow_first_spawn`) and a production seed should be chosen with the first
   split in mind as well as the last one.
3. **Read panel state from `panel_states`, never by accumulating damage.** Four
   visible states precede a break — `healthy`, `damaged`, `critical`,
   `fractured` — and the table gives the state at any `t` directly. A renderer
   that re-derives it from the `damage` stream is computing physics, which the
   playback contract forbids for good reason.
4. **The outermost shell is the frame, and it is radius 24.4 with 32 panels.**
   Test #1's Phase 6 found that a centred 0.86-wide arena hides content under
   the Shorts action rail; the same check has to be run here, and with 32 panels
   the outer shell's features are small, so a safe-area pass is not optional.
5. **Balls will strobe.** Test #1's Phase 3 found that a single ball at 30 fps
   needed a temporal trail to stop strobing. Ten balls at speed 10 make that
   worse, not better, and a trail also happens to encode which ball is which.
6. **Population is the escalation, so it has to be legible.** The count goes
   1 → 11 over the run. Whether that reads without a counter on screen is a
   question for a visual proof, not an assumption.
7. **A break is worth a camera beat.** Median 12 per run, 99.3% of runs contain
   one paid for by more than one ball. The "two balls wore this panel down and
   a third walked through" moment is the emergent behaviour the redesign exists
   for, and the event stream already identifies it (`contributors > 1`).

### Audio

1. **Do not sonify every collision.** The measured rates are in §K. A selection
   rule is not a compromise; at these densities it is the only way the stream
   becomes music rather than gravel.
2. **Lineage is a voice.** `generation` and `lineage` give a ready mapping —
   a child as a transposition or a timbral variant of its parent — so the
   family tree is audible as well as visible, and a listener can hear that the
   thing that got out was a descendant.
3. **The four damage states are a four-step gesture.** `healthy → damaged →
   critical → fractured → broken` is a built-in crescendo per panel, with the
   break as its resolution. A panel that is one hit from going can say so.
4. **The escape is a single event at the very end**, and the density curve rises
   into it on its own (late/early 2.67). The soundtrack does not need to
   manufacture a climax; it needs to not flatten the one the physics produces.
5. **Near misses are the tension markers** and they are already classified by
   `criterion` — `arc` (a miss of aim) or `time` (a miss of timing) — which are
   different feelings and could be different sounds.
6. **Watch the burst, not the mean.** A run averaging six collisions a second
   with nineteen in one of them is not a six-a-second soundtrack, and the
   bursts are concentrated in the last third by construction.

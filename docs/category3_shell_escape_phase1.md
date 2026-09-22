# Category 3, Test #2 — MUSICAL SHELL ESCAPE, Phase 1

**CAN THE BALL ESCAPE?**

One ball starts inside six nested rotating segmented shells. It gets out two
ways and only two ways: through a moving **opening**, or through a panel it has
hit hard enough and often enough to **break**. Or it does not get out, and the
run ends at the horizon.

Phase 1 asks one question — *can rotating openings plus destructible panels
naturally generate repeated prediction opportunities, shell progression and
genuine success/failure inside a Shorts-friendly runtime* — and builds only
enough to answer it.

**Decision: CORE MECHANIC PASSED — READY FOR PARALLEL VISUAL/AUDIO
DEVELOPMENT.**

---

## 1. What was built

| File | What it is |
| --- | --- |
| `satisfying/shell_seeds.py` | Four independent seeded streams: release point, heading, per-shell phase, per-shell rate jitter. Distinct salts from Test #1. |
| `satisfying/shell_arena.py` | The shells. Regular polygons, panels as capsules, openings as runs of missing slots, stable `shell_id` / `panel_id` / `opening_id`. Geometry only. |
| `satisfying/shell_escape.py` | The simulation: ball, contact solver, damage, breaking, region crossings, event stream, digest. |
| `satisfying/shell_reference.py` | A deliberately stupid sampling solver, used only to check the clever one. Test scaffolding. |
| `satisfying/shell_playback.py` | The canonical playback/event document that Phase 2A and Phase 2B consume. |
| `satisfying/shell_evaluator.py` | Per-run metrics and named flags; population summaries. No score, anywhere. |
| `satisfying/shell_escape_cli.py` | `batch`, `sweep`, `shortlist`, `document`, `verify`, `describe`. |
| `tests/test_shell_escape.py` | 48 tests. |

Reused from Test #1: the *patterns*, not the code — one salt per concern, a
canonical document a renderer may read and may not recompute, a fast batch
evaluator, a package-local CLI, prose docstrings that say why. Nothing here
imports `satisfying.tile_*` or `satisfying.seeds`, and
`test_test_two_does_not_import_test_one` holds that. The only edit to an
existing file is two stdlib names (`concurrent`, `statistics`) added to Test
#1's package-wide import allowlist, which is the growth that guard's own
comment provides for.

---

## 2. The simulation

**Shells are rotating polygons, not rings — and that is a dynamical choice.**
Reflection off a circle has a radial normal, and a radial normal leaves
`L = p × v` exactly conserved: every bounce then has the same incidence angle,
contact angles advance by a fixed increment, and the ball traces one rosette
for the whole run. That is the "long repetitive orbit" the brief asks us to
detect, except it would be the only orbit rather than a rare pathology. A flat
panel's normal is not radial and a *rotating* polygon's normals are
time-dependent, so the system is non-integrable. It also happens to be the
segmented, mechanical look the brief asked for.

| Default | Value |
| --- | --- |
| Shells | 6, radii 5.0 → 23.0, spacing 3.6 |
| Panels per shell | 16, 17, 18, 19, 20, 21 (inner → outer) |
| Openings per shell | 2, 3, 3, 4, 4, 5 — one slot each |
| Panel thickness / ball radius | 0.30 / 0.40 |
| Rotation | `ω_k = 0.62 · (5.0 / R_k) · (1 ± 0.22)`, sign alternating by index |
| Ball | speed 17.0, gravity 0, restitution 1 |
| Damage | `(v_normal / 17)^1.5` per hit, break at 2.6 → **1.6** |
| Horizon | 26.0 s |

`ω_k ∝ 1/R_k` gives every shell the same *surface* speed (3.1 units/s against a
ball at 17), which is what stops the outer shells reading as a blur. The
seeded jitter means no two shells share a rate and their openings never lock
into a repeating alignment pattern.

**Opening fit is geometry, not a tunable.** A ball passes only if it fits
between the flanking posts, and `ShellArena.fit_report()` reports the ratio per
shell — 2.06 at the innermost shell, 8.19 at the outermost. A config whose
innermost opening were narrower than the ball would make that route impossible
and this says so as a number.

### 2.1 The contact solver, and the two bugs it had

Between collisions the ball is a point on a straight line, so entering and
leaving any circle is an exact quadratic root, and each shell publishes a
contact band outside which it cannot be touched at all. Inside the bracket the
geometry is a rotating capsule and the contact time is not a polynomial root.
It is found by marching on the signed clearance with steps each of which is
*proved* free of a contact — by the near panels' curvature bound, by the
Lipschitz distance to everything else, or by the two-point rule (two positive
clearances `d1`, `d2` leave no room for a root when `(t2−t1)·S ≤ d1+d2`).

Two defects were found during Phase 1, both by the run-level instruments and
neither by any test that only checked that a ball bounced:

1. **A Newton step past the end of the interval was treated as proof the
   interval was clear.** On a near-tangential graze the derivative passes
   through almost zero, the step lands seconds away, and the solver reported
   "no contact" — walking the ball straight through a panel. `max_penetration`
   read 0.55 (the full contact radius) and `anomalous_crossings` counted the
   ball crossing shells where panels were still standing. Fixed by clipping
   every step to the interval and evaluating there.
2. **A ball clipping a vertex touches both panels that meet there.** Bounding
   only the nearest one and leaving the other to the Lipschitz rule gives a
   safe step of nearly zero: one search spent 2001 evaluations inside a
   two-millisecond window and gave up. Fixed by giving the two nearest panels
   each their own curvature bound.

`satisfying/shell_reference.py` exists because of these. It answers the same
question by sampling every live panel a few thousand times along the flight —
a hundred times slower, with no geometric insight in it, so agreement is
evidence rather than a tautology. `test_solver_agrees_with_the_brute_force_reference`
runs it against every contact search of six seeds: **980 searches, zero
disagreements**, and the windowed nearest-panel search never differs from the
all-panel one. The same check was run over wider samples during development -
3439 searches across twelve seeds at one point in the parameter search - and
never disagreed after the two fixes above.

### 2.2 Collision response, and why it looks the way it does

The reflection is specular about the contact normal **in the panel's own
frame**, and the ball's speed is renormalised to the config speed after every
contact. Both are config flags. Both are there because the two obvious models
each fail, and both failures were measured over 1500 seeds:

| Model | Result |
| --- | --- |
| Ignore the panel's motion (`panel_momentum_transfer = 0`) | Speed exactly constant — and nothing can push the ball out of a wall sweeping into it. A near-tangential arrival at a post is caught and **chatters**: same contact, same instant. **14.4% of runs**; the worst spent its whole collision budget in one spot. |
| Take the panel's motion, restitution 1 (`constant_speed = False`) | Contacts separate correctly and every shell becomes a Fermi accelerator. Speed drift **p50 +34%, p95 +119%, max +225%**. That is the runaway the brief forbids. |
| Both (the default) | Chatter gone (0.1% of runs show >3 immediate repeats, one pathological orbit in 20 000). Speed drift `4.2e-16`. |

So the *direction* of every bounce comes entirely from the physical reflection
off a moving wall — nothing about it is tuned and it cannot bias which way the
ball goes — and the magnitude is held at the config's speed, which makes speed
the run's clock and nothing else. How much work the constraint does is
reported, not assumed:

| Contact type | Share | Median correction | Max |
| --- | --- | --- | --- |
| Flat face | 86% | 2.3% | 7.7% |
| Post (panel end) | 14% | 17.1% | 43.4% |

A post is a point at radius `R` moving at `ωR = 3.1`; that is the strongest
kick a rotating edge can physically give, and it is the moment the constraint
is doing real work. `max_speed_correction` carries it per run.

### 2.3 What is *not* in the response

`test_the_ball_is_never_steered_towards_an_opening` reads the source of
`simulate` and asserts that the collision-response block never touches
`opening_of_slot`, `passable_runs` or `open_slots`. The response is a function
of the contact normal and the panel's velocity and nothing else.
`test_the_near_miss_threshold_does_not_change_the_trajectory` runs the same
seed with the reporting thresholds at 50× and asserts every collision time and
position is identical.

---

## 3. The event schema — frozen at `category3-test2-shell-escape/1.0.0`

Eight kinds. `test_the_event_schema_is_frozen` asserts every field name of
every kind, in order, so a rename is a test failure rather than a merge
conflict discovered at integration.

| Kind | Fields (beyond `kind`, `t`) |
| --- | --- |
| `collision` | `shell_id`, `panel_id`, `region`, `position`, `contact_point`, `contact_angle`, `normal`, `velocity_in`, `velocity_out`, `impact_speed`, `speed`, `incidence`, `feature` (`face`/`post`), `grazing`, `radial_outward`, `panel_local_offset` |
| `near_miss` | `shell_id`, `panel_id`, `opening_id`, `region`, `ball_position`, `ball_angle`, `opening_centre_angle`, `opening_half_width`, `angular_separation`, `arc_separation`, `arc_separation_ball_radii`, `relative_angular_speed`, `time_separation`, `signed_lead`, `criterion` |
| `damage` | `shell_id`, `panel_id`, `added`, `cumulative`, `threshold`, `impact_speed` |
| `panel_break` | `shell_id`, `panel_id`, `position`, `break_angle`, `cumulative`, `hits` |
| `shell_exit` | `shell_id`, `panel_id`, `method` (`opening`/`break`), `opening_id`, `from_region`, `to_region`, `position`, `crossing_angle`, `local_offset`, `dwell_seconds` |
| `shell_entry` | same fields — the ball falling back inward |
| `escape` | `shell_id`, `method`, `position`, `collisions`, `breaks` |
| `failure` | `reason`, `region`, `collisions`, `breaks` |

**The playback document** (`category3-test2-shell-escape-playback/1.0.0`) adds
`flights` (the trajectory, as straight-line arcs — a renderer evaluates
`p + v·dt`, closed form, so frame rate cannot move the ball), `shells`,
`panel_states` (which panel broke when — the whole draw rule), `summary` and
`digest`. `verify_document` re-simulates the seed and compares field by field.
Three canonical documents are committed under
`docs/validation/category3_shell_escape/`.

**Escape is two beats, deliberately.** `shell_exit` fires when the ball's
centre crosses the outermost mid-surface; `escape` fires when it clears
`outer_radius + rho`, because until then it can still clip a post and be thrown
back in.

---

## 4. The near-miss model

A collision with a solid panel of shell `k` is a **near miss** when the ball
was on its way out of its own frontier shell (`shell_id == region` and radial
velocity outward), and the angular gap `g` from the contact angle to the
nearest passable arc satisfies **either**:

- **arc** — `g · R / ball_radius ≤ near_miss_arc_ball_radii` (default **2.5**):
  a small difference in *aim* would have passed; or
- **time** — `g / |ω_shell − ω_ball| ≤ near_miss_seconds` (default **0.15 s**):
  a small difference in *timing* would have.

Passable arcs are openings *and* broken panels alike — to the ball they are the
same hole — and each is first shrunk by the angle the ball subtends at that
radius, because a hole the ball does not fit through was never a chance it
missed. Every event carries `g`, the arc gap in world units, the gap in ball
radii, the relative angular rate, the time separation, the signed lead
(positive: the hole is still coming; negative: it has just gone past) and
which criterion fired.

Both thresholds are config and changing them changes nothing about the
trajectory. Setting both to zero leaves **zero** near misses; setting both to
50 raises the count. Ordinary distant impacts are not counted: at the defaults
a near miss is a miss by under one ball diameter of arc, or under a sixth of a
second of shell rotation.

---

## 5. Batch results — 20 000 seeds

`python -m satisfying.shell_escape_cli batch --seeds 20000`, 341 seeds/s on 12
cores, 59 s. Config digest `7da0cbc80d595826`.

| | |
| --- | --- |
| Escape rate | **39.1%** (7813) |
| Timeout rate | **60.9%** (12 187) |
| In 18–26 s | **3807** |
| In 20–24 s | **1895** |
| Clean (no flags at all) | 2091 |
| Duration p5 / p25 / p50 / p75 / p95 | 7.9 / 13.4 / 17.8 / 21.8 / 25.1 s |

Duration histogram is close to flat across the whole band — 825 runs under 10 s,
then 605 / 799 / 865 / 912 / 992 / 977 / 918 / 920 in 2-second buckets up to 26.

| Metric | p5 | p50 | p95 |
| --- | --- | --- | --- |
| Collisions | 30 | 63 | 79 |
| Collisions per second | 2.12 | **2.69** | 3.29 |
| Near misses | 3 | **11** | 19 |
| Panel breaks | 4 | **14** | 21 |
| Regressions (falls back inward) | 1 | **9** | 17 |

- **Near misses:** only **76 runs in 20 000** had none.
- **Breaks:** only **96 runs in 20 000** had none.
- **Collision rate:** never once above the 8/s "visually impossible" line and
  never below the 1.2/s "empty screen" line — 0 `frantic`, 0 `sparse`.
- **Pathological orbits:** **1 in 20 000**.
- **Stagnation:** longest gap with no meaningful event — p50 2.56 s, p95 4.43 s,
  p99 5.64 s. Middle-third stagnation p50 1.50 s, p95 3.23 s.
- **Instruments: 0 runs with penetration, 0 with anomalous crossings, 0 with
  solver failures.** Worst penetration `1.0e-11` (the clearance tolerance),
  worst speed drift `4.2e-16`.

### Outcome balance

| | |
| --- | --- |
| Progression steps via opening | 68 738 (**74.9%**) |
| Progression steps via break | 23 059 (**25.1%**) |
| Escapes that used at least one break | **6091 of 7813 — 78%** |
| Escapes that used at least one opening | 7813 of 7813 — 100% |
| Escapes that used both | 6091 — 78% |

**A finding worth keeping:** measured on *every* outward crossing, breaking
looks dominant 4:1 in almost every configuration. Measured on **progression**
crossings — the ones that took the ball somewhere it had not been — the same
population is three-quarters openings. The difference is yo-yoing: a ball that
crosses one broken panel eleven times records eleven break exits and zero
progress. Reporting only the first number invents a balance problem that was
never there, which is why the evaluator reports both and the brief's balance
question is answered with the second.

---

## 6. Parameter sweep — the operating region

3000 seeds per point, one axis at a time. Raw JSON in
`docs/validation/category3_shell_escape/phase1_sweep_*.json`.

**Speed** (13 → 21, `damage_reference_speed` held at 17): escape 18.7% → 50.2%,
median 19.6 → 16.8 s, rate 2.27 → 3.08/s. Broad and flat — everything from 14
to 19 is usable, which is a healthy region rather than a knife edge. Note the
confound: with the damage reference held fixed, faster balls also break panels
faster, and the opening share drifts 82% → 75% because of that and not because
of the speed.

**Openings per shell**: the strongest lever by far.

| Profile | Escape | Median | Opening share of progression |
| --- | --- | --- | --- |
| 1,1,1,1,1,1 | 3.7% | 20.9 s | 47.5% |
| 2,2,2,2,2,2 | 15.9% | 19.6 s | 64.0% |
| **2,3,3,4,4,5** | **38.5%** | **17.7 s** | **75.6%** |
| 3,3,3,3,3,3 | 29.9% | 17.5 s | 75.1% |
| 4,4,4,4,4,4 | 42.7% | 16.7 s | 80.5% |

**Break threshold**: 0.8 → 62.7% escape and openings down to 56% of
progression; 3.5 → 28.1% and openings up to 91.8%; disabled entirely → 26.8%
escape and openings 100%. So **breaking is worth about 12 points of escape
rate**, and the threshold is the dial that decides how much of the progression
each mechanic owns. 1.6 sits at 75/25.

**Rotation** (`omega_base` 0 → 1.6): escape 34.5% → 51.5%, median near-miss
count unchanged at 11. **Rotation is not what makes escape possible** — with
the shells frozen the ball still gets out of 34.5% of runs, because the chaos
comes from the polygon geometry, not the motion. What rotation buys is the
*timing* character of the near misses and the "wait for the gap" reading, which
is a Phase 2 concern and not a feasibility one.

**Panel count** (10–15 → 20–25): escape 60.7% → 28.9%, median 14.9 → 19.2 s,
near misses 7 → 14. More panels means narrower openings, more posts to clip and
more near misses, at the cost of escape rate. 16–21 is the balance point.

**Shell spacing** (2.4 → 5.2): escape 43.8% → 26.4%, rate 3.40 → 2.08/s, near
misses 16 → 8. Spacing is the collision-rate dial: it sets how much radial room
the ball has in an annulus and therefore how often it hits something.

**Rejected:**
- *Circular shells.* `L` conserved, one rosette for the whole run. Rejected on
  the geometry, before any seed was run.
- *Zero panel momentum transfer.* 14.4% chatter.
- *Full transfer with no speed constraint.* +34% median speed drift.
- *Tight spacing (2.05) with 12–17 panels.* The annulus had under one ball
  diameter of clear radial room; the ball rattled at 10–15 collisions/s and
  the run was a blur.
- *Flat single openings (1,1,1,1,1,1).* 3.7% escape — the population has almost
  no successes in it.

---

## 7. Retention-oriented findings

**Near misses.** Median 11 per run, roughly one every two seconds, and 99.6% of
runs have at least one. They are physically real: a near miss is usually a
**post contact**, the ball clipping the edge of the panel beside the hole
(14% of all collisions are post contacts). That gives Phase 2A and 2B a
distinct event to dress, not a label over an ordinary bounce.

**Progression is a near-symmetric random walk, and that is the structure of the
whole piece.** The ball can fall back inward through any hole it has already
made or found, and it does: **median 9 regressions per run** against 6 forward
steps. That is why six shells take twenty seconds rather than six, and it is
where the tension lives — "it was nearly out and it fell back" is the shape
this concept produces on its own, without anything being arranged.

**Escalation is real but it is not in the event rate.** Across the population,
per third:

| | 1st | 2nd | 3rd |
| --- | --- | --- | --- |
| Collisions | 20.3 | 20.7 | 19.0 |
| Near misses | 4.12 | 3.97 | 2.99 |
| Breaks | 3.85 | 5.11 | 4.71 |
| Progress steps | 1.54 | 1.36 | **1.69** |

Collisions are flat (they cannot rise much at constant speed) and near misses
*decline*. What rises is **progress** — and for the shortlisted candidates the
final third carries nearly twice the progress of the middle third. The run gets
faster, not busier. The late-run difference the brief asks for is there in
three things, and none of them is event density:

1. **Progress accelerates.** The ball clears its last shells in a rush.
2. **The arena is visibly wrecked.** Cumulative breaks by the end of each third
   run roughly 4 / 9 / 14 — by the final third a third of the panels the ball
   has met are gone.
3. **The ball is somewhere else.** It has moved from a disc of radius 4.8 to an
   annulus at radius 23; the scale of the picture changes completely.

**This is the single most important note for Phase 2A and 2B.** If the visual
and audio branches try to build the climax out of rising event density, they
will be fighting the simulation. The climax is built out of accumulating
damage, increasing radius, and the shrinking number of shells left.

**Dead air is not a problem.** The 99th percentile gap with no meaningful event
is 5.6 s over the whole population, and 135 runs in 20 000 are flagged
`dead_stretch`.

---

## 8. Bad runs — named, counted, never scored

`usable` is exactly "no flags". There is no aggregate score anywhere in the
evaluator, because a score would say seed 4471 rates 0.82 and destroy the only
information a shortlist needs: *which* thing is wrong.

| Flag | Count in 20 000 | What it catches |
| --- | --- | --- |
| `failed` | 12 187 | did not escape |
| `one_shell_hog` | 11 143 | one region takes over 40% of the run |
| `instant_escape` | 2678 | out in under 15 s, no suspense |
| `too_few_near_misses` | 2695 | under 6 near misses |
| `no_opening_progress` | 344 | every step was a break; openings irrelevant |
| `photo_finish` | 226 | escaped within 0.5 s of the horizon |
| `dead_stretch` | 135 | over 6 s with nothing meaningful |
| `dead_middle` | 102 | over 5 s of the middle third with nothing |
| `no_breaks` | 96 | nothing broke; the damage system is decoration |
| `few_distinct_panels` | 78 | under 12 distinct panels touched |
| `repetitive_orbit` | 1 | a short cycle repeated over 10 times |
| `frantic` / `sparse` | 0 / 0 | collision rate outside 1.2–8.0/s |
| `instrument_fault` | **0** | penetration, drift, anomaly or solver failure |

`one_shell_hog` is set at **0.40**, and it has to be that tight. The first
shortlist, built at 0.5, produced a candidate that spent 91% of its run inside
the two innermost shells and cleared the outer four in under two seconds. The
threshold was set from the population — in-band escapes give their biggest
region a median 0.387 of the runtime, p75 0.467 — so 0.40 cuts just above the
middle and still leaves about 1600 clean in-band seeds in 20 000.

**The shortlist ranking needed the same correction and needed it twice.**
Ranking on near misses alone picks inner-shell hogs, because a ball rattling in
the core collects near misses faster than one making progress. Ranking on the
share of the run spent *outside* the core picks the mirror image — runs that
blast out of the middle in four seconds and grind in one outer annulus — and
being continuous it never ties, so it becomes the only sort key and the
near-miss counts collapse with it. The term that works is a **count**: how many
regions got at least 8% of the runtime. It ties constantly, which is the point.

---

## 9. Candidate shortlist — 16 seeds

From 20 000 seeds, config digest `7da0cbc80d595826`. Every candidate is
flag-free, gives all six regions at least 8% of its runtime, and has a biggest
region under 0.40. Full records in
`docs/validation/category3_shell_escape/phase1_shortlist.json`.

| Seed | Band | Duration | Collisions | Near misses | Breaks | Open/Break progression | Final | Biggest region | Digest |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 17534 | 20–22 | 21.13 | 71 | 14 | 13 | 4/2 | break | 0.33 | `3979f57089f0` |
| 3654 | 20–22 | 21.21 | 62 | 13 | 9 | 5/1 | opening | 0.26 | `2cbd8b869452` |
| 6903 | 20–22 | 21.39 | 60 | 12 | 10 | 5/1 | break | 0.23 | `593fcd93a816` |
| 18645 | 20–22 | 21.72 | 69 | 12 | 14 | 4/2 | opening | 0.25 | `a11089d17210` |
| 9589 | 22–24 | 22.94 | 66 | 15 | 17 | 3/3 | opening | 0.36 | `0978e0644f27` |
| 16513 | 22–24 | 23.80 | 58 | 14 | 14 | 4/2 | opening | 0.38 | `d1173bb5a3bc` |
| 8952 | 22–24 | 23.83 | 66 | 13 | 11 | 5/1 | break | 0.29 | `74779d1c9d5d` |
| 11929 | 22–24 | 22.11 | 76 | 12 | 14 | **2/4** | break | 0.26 | `4c0434a8d497` |
| 7699 | 24–26 | 25.47 | 82 | 14 | 18 | 4/2 | opening | 0.30 | `42361f2a8f7a` |
| 13761 | 24–26 | 24.60 | 75 | 14 | 8 | 5/1 | opening | 0.27 | `c269aba18952` |
| 18920 | 24–26 | 25.16 | 65 | 13 | 12 | 5/1 | opening | 0.28 | `ab880e692000` |
| 15804 | 24–26 | 24.24 | 72 | 13 | 13 | 5/1 | opening | 0.26 | `fca7c7a5115f` |
| 1511 | 18–20 | 18.71 | 58 | 11 | 9 | 3/3 | break | 0.37 | `641d48c58af4` |
| 11141 | 18–20 | 19.23 | 58 | 9 | 9 | 3/3 | break | 0.31 | `34120d169540` |
| 2023 | 18–20 | 18.99 | 53 | 9 | 8 | 4/2 | opening | 0.35 | `cbec4ecf046d` |
| 19607 | 18–20 | 18.68 | 52 | 9 | 8 | 5/1 | break | 0.34 | `9002c702b82f` |

Variety, as the brief asked for it: four in 20–22 s, four in 22–24 s, four in
24–26 s, four in 18–20 s; progression mixes from 5/1 to **2/4**; six resolve
the outer shell by breaking it and ten by finding its opening.

Three are committed as full playback documents: **9589** (a 3/3 route mix,
15 near misses, 17 breaks), **11929** (break-dominant, 2/4, resolves by
breaking), **7699** (the longest, 25.47 s, 18 breaks).

No production seed is selected. That is deliberate — the visual and audio
branches need several to choose from.

---

## 10. Tests and regression

`tests/test_shell_escape.py`, **48 tests, all passing**, covering every item the
brief listed plus the things that turned out to matter:

deterministic shell construction · deterministic rotation · opening geometry
and fit · seam-wrapping openings · rotation present in the state not just the
picture · seed-stream independence · **solver vs brute-force reference** ·
zero penetration over 200 seeds · zero anomalous crossings and solver failures
over 200 seeds · speed exactly constant · the speed constraint reported and
non-steering · the chatter that zero transfer causes · reflection about the
contact normal · **no steering towards openings, checked in the source** ·
damage accumulation and impact-strength dependence · break exactly once ·
no damage after a break · broken panel becomes passable · breaking can be
disabled · region changes only by one and only through a hole · escape only
after clearing the outermost shell · both escape routes · timeout failure ·
falling back inward · success and failure both occur · near-miss geometry,
thresholds and non-interference · **the frozen schema, field by field** ·
event ordering and one terminal event · flights are the trajectory · document
reproduction and JSON round trip · digest sensitivity · consumer replay of
position, region and panel state · evaluator totals reconcile · progression
separated from yo-yoing · flags name specific complaints · stagnation metrics
differ · cycle detection · summaries carry no score · batch records rebuild the
summary · shortlist spread · no Godot/audio/rendering import · no Test #1
import.

Regressions: `tests/test_tile_escape.py` and `tests/test_tile_escape_phase2.py`
— **98 passed**. No existing guard weakened; the only change is two stdlib
names added to an allowlist whose own comment provides for exactly that.

---

## 11. Decision

**CORE MECHANIC PASSED — READY FOR PARALLEL VISUAL/AUDIO DEVELOPMENT.**

Against the brief's Phase 1 criteria:

| Criterion | Evidence |
| --- | --- |
| Genuine success and failure both occur | 39.1% / 60.9% over 20 000 seeds |
| Successful runs exist naturally in 18–26 s | 3807 in band, 1895 in 20–24 s |
| Near misses often enough for repeated prediction | median 11/run; 76 runs in 20 000 have none |
| Multiple shells change the situation over time | every shortlist candidate gives all six regions ≥8% of its runtime |
| Both opening and break progression matter | 74.9% / 25.1% of progression; 78% of escapes used both; disabling breaking costs 12 points of escape rate |
| Pathological repetition uncommon | 1 in 20 000 |
| No hidden steering necessary | asserted in the source and by threshold-invariance |
| Event stream complete for visual and audio | schema frozen, three documents committed, replay helpers tested |
| Fast enough for batch search | 341 seeds/s on 12 cores; 20 000 seeds in 59 s |

---

## 12. Recommendations for Phase 2A / 2B (not implemented)

**For both branches.**
- Treat `category3-test2-shell-escape/1.0.0` as read-only. A renderer or
  synthesiser that recomputes a trajectory will diverge — the dynamics are
  chaotic on purpose.
- Build the climax out of **accumulating damage, growing radius and the
  shrinking number of shells left**, not out of rising event density. §7 has
  the measurements: collisions are flat and near misses decline.
- Use several shortlist candidates in parallel. The 2/4 route mix (11929) and
  the 5/1 mixes look like different videos.

**Phase 2A (visual).**
- `feature` distinguishes a flat hit from a clipped post. The post clips *are*
  the near misses; they deserve their own treatment.
- `panel_states` is the whole draw rule: a panel exists if it started closed
  and has not broken by `t`. Cumulative damage is available per contact if a
  cracking progression is wanted.
- The action rail: Test #1's Phase 6 found a centred 0.86-wide arena hides
  9 tiles under the Shorts rail. This arena is a disc of radius 23 and the
  outer shell is where the climax happens — the safe-area question needs
  answering before composition, not after.
- Six shells at radii 5 → 23 in a 9:16 frame means the innermost shell is a
  small fraction of the picture. Whether the camera stays wide or follows the
  ball outward is a real decision and it changes what the early run reads as.

**Phase 2B (audio).**
- `impact_speed` and `incidence` give a natural dynamic per hit; `feature`
  gives two timbres; `shell_id` gives six registers.
- Median 2.7 collisions/s is a musical tempo, not a rattle — around 160 BPM in
  quarter notes. The event stream is sparse enough to score rather than to
  sonify.
- `near_miss` carries `signed_lead`: positive means the hole was still coming,
  negative means it had just gone past. That is a tension cue with a direction,
  and it is already in the stream.
- `panel_break` is the only event that permanently changes the arena. It is the
  obvious carrier of harmonic movement across the run.

**Do not start either branch from this document alone** — read
`satisfying/shell_escape.py`'s module docstring first. The contact model and
its two named constraints are the part that would be easy to re-derive wrongly.

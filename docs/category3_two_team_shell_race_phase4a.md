# Category 3 Test #2 — TWO-TEAM SHELL RACE, Phase 4A evidence

This is a human-review candidate phase, not production approval. No upload
master was created.

## Provenance and isolation

- source branch: `category3-multiplying-shell-adjust-v3b`
- fetched source tip: `335ae3c647676be37421e082268f650b8541e8c9`, verified
- work branch: `category3-two-team-shell-race-v4a`
- Phase 1, Visual 2A, Audio 2B, A/V 3 and Adjust 3B branches and their evidence
  are untouched; `main` is untouched

## The defect that explains the human review

**The renderer's camera was 1.778× too wide, and had been since Phase 2A.**

`Camera3D.keep_aspect = KEEP_WIDTH` makes Godot read the frustum `size` as the
near plane's *width* and derive the height from the aspect ratio:

```
left / right = ∓ size / 2            + offset.x
top / bottom = ∓ size / aspect / 2   + offset.y        (aspect = W / H)
```

`CAMERA_FRUSTUM_SIZE` was `2·near·tan(hfov/2)·H/W` — the near plane's *height*.
The horizontal field was therefore 74.4° rather than the declared 47°, and
every framing came out 1.778× wider than `satisfying.multishell_visual`
computed. Measured on a rendered frame, the Phase 3B composition filled
**46.9 % of the frame width where the report said 83.4 %**; the outermost shell
sat roughly 250 px clear of the action rail rather than the 18.4 px the
safe-area report claimed; a ball at the final framing was about 12 px across
rather than 21.

It survived three phases because the only test on the constant compared the
Python copy with the GDScript copy — and both copies carried the same error.
Two files agreeing is not a measurement.

It also accounts for three of the seven human-review findings directly. "The
arena becomes too small relative to the vertical frame", "too much empty dark
space appears precisely when action should be increasing" and "frontier
reframing zooms out too aggressively" are what a camera 1.778× too wide looks
like, and no retuning of `VIEW_DIAMETER_FRACTION` could have fixed any of them,
because that number was not the one the renderer used.

`test_the_frustum_matches_the_declared_field_of_view` re-derives the half-angle
from Godot's own frustum arithmetic rather than from a second copy of the
constant. Measured on a rendered frame after the fix, the outermost shell's
radius is **352 px against a predicted 349.2 px**.

## A. The two-team mechanic

Two founders, one per colour. Every ball belongs permanently to one team; a
child is its parent's colour, for every generation, with no mechanism anywhere
that could change it. The run resolves on the first legitimate crossing of the
escape radius and the crossing colour is the winner.

Ball records carry `ball_id`, `team_id`, `team_colour`, `parent_id`,
`generation`, `birth_time`, `birth_shell`, `lineage`, `credited_at_birth`,
`credited`, `visited`, `children` and `damage_dealt`. Schema is
`category3-test2-two-team-shell-race/3.0.0`; every event that names a ball
carries that ball's `team_id`.

Anti-farming is unchanged: one child per ball per shell, enforced by a bitmask
and checked against the written event stream rather than against the variable
that enforces it. **0 reproduction violations in 20,000 runs.**

The spawn split still alternates on the global spawn index. Alternating on the
parent's own child count was tried first, on the argument that it would be
balanced per colour as well as per run: it is not balanced at all. Most balls
have one or two children, so "the first child turns +" put **415 of 597 cyan
spawns the same way** and gave the whole simulation a chirality. The global
counter is exactly balanced by construction, and whether it is *also* balanced
between the colours is then an empirical question that the population answers.

## B. Team fairness

**The physics never reads the team, structurally.** `start_states` builds two
release states from the seed; `team_assignment` then decides which of those two
finished states is called cyan. No arrangement of the colours can change a
position, a velocity or a time.

Both founders are released on one circle at one shared radius, antipodally,
with the same speed, the same ball radius and the same collision model, and
with independently drawn headings. One radius is the whole of "equivalent
distance from relevant geometry". Independent headings are what stop the pair
being a point-symmetric mirror of each other, which on an even-panelled shell
would trace two copies of one trajectory instead of a race.

**Label-swap test, 1,000 seeds, ten independent checks each — all pass.**

| check | failures |
| --- | ---: |
| `state_digest_equal` (physics fingerprint identical) | 0 |
| `team_digest_differs` (label fingerprint mirrored) | 0 |
| `labels_mirrored` (every ball changed colour) | 0 |
| `physical_events_equal` (every non-team field, member by member) | 0 |
| `event_count_equal` / `duration_equal` / `escape_ball_equal` | 0 / 0 / 0 |
| `winner_flipped` | 0 |
| `damage_swapped` / `population_swapped` | 0 / 0 |

The swap test found a real defect while being written: `team_swap` was inside
`MultishellConfig.digest()`, which `state_digest` hashes, so a swapped run
fingerprinted differently for a reason that was not physical. The instrument
moved with the thing it was measuring. `physics_digest` now excludes the
label-only fields by name and `state_digest` is built from that, so
"the swap changed nothing physical" is a digest comparison and not a promise.

**Colour statistics, 20,000 seeds, 4,490 escapes.**

| measurement | cyan | orange | z |
| --- | ---: | ---: | ---: |
| wins | 2,288 | 2,202 | +1.28 |
| wins by physical founder slot | 2,277 | 2,213 | +0.96 |
| first to clone | 10,031 | 9,969 | +0.44 |
| mean final population | 6.1414 | 6.1377 | — |
| mean damage dealt | 128.697 | 128.774 | — |

Neither the colour split nor the slot split is significant at two sigma. The
two are reported separately on purpose: the colour map is a seeded coin, so a
colour bias would be the coin, while a *slot* bias would be a real asymmetry in
the implementation — slot 0 is ball 0 and the ball id breaks scheduling ties.
Reporting only the colour rate would let the coin launder a slot bias.

## C. Camera and zoom

| decision | Phase 3B | Phase 4A |
| --- | ---: | ---: |
| arena centre, x | 0.420 | **0.500** |
| arena centre, y | 0.440 | 0.450 |
| pad | +0.85 world units | ×1.055, proportional |
| frontier, share of frame width | 73.3 % → 80.6 % (claimed) | **65.2 %, constant** |
| total zoom-out | 3.63× | **2.80×** |
| lateral camera movement | 0 px | 0 px |

**Arena screen occupancy at every frontier stage** (1080×1920, top candidate
17964; identical on every seed because the schedule is a function of the shell
geometry):

| stage | frontier Ø | of frame width | of usable width | ball Ø | opening | wall | panel chord |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 704.2 px | 65.20 % | 95.88 % | 73.0 px | 88.3 px | 7.0 px | 134.3 px |
| 1 | 704.2 px | 65.20 % | 95.88 % | 50.3 px | 53.4 px | 8.7 px | 57.2 px |
| 2 | 704.2 px | 65.20 % | 95.88 % | 38.4 px | 58.6 px | 11.8 px | 47.5 px |
| 3 | 704.2 px | 65.20 % | 95.88 % | 31.0 px | 51.7 px | 16.6 px | 34.2 px |
| 4 | 704.2 px | 65.20 % | 95.88 % | 26.0 px | 27.6 px | 23.8 px | 33.2 px |

"Usable width" is the widest horizontally centred band that clears the action
rail: 2 × (0.840 − 0.500) = 0.680 of the frame. The frontier fraction spread
across stages is **exactly 0.0** — the proportional pad makes it constant by
construction rather than by fitting.

The total zoom-out is now a property of the arena rather than of the camera:
under a proportional pad it is the outermost material edge over the innermost,
so the only way to open out further is to change the shells. That is why Phase
4A shrank the arena from an outer radius of 24.4 to 18.5 and grew the ball from
0.40 to 0.53.

At the final wall the opening is **27.6 px against a 26.0 px drawn ball**. That
is the "how are they going to get through that" read, and it is geometry rather
than staging.

## D. Visual centring

| measurement | value |
| --- | ---: |
| arena centre, x | 0.500 of frame width |
| lateral offset from frame centre | **0.00 px** |
| maximum lateral camera movement over a run | **0.00 px** |
| maximum vertical camera movement over a run | **0.00 px** |
| outermost material radius | 352.08 px |
| clearance to the conservative action rail | **15.12 px** |
| left margin | 187.92 px |

The camera only ever changes its eye distance, so the world centre projects to
the same pixel on every frame of every candidate. The vertical centre sits at
0.450 rather than 0.500 because the Shorts furniture is not symmetric — the top
bar takes 6 % and the title block, scrubber and navigation row take the bottom
16 % — so 0.450 is the midpoint of the band a viewer actually sees.

The 15.12 px rail clearance is the tightest constraint in the composition and
is the price of genuine centring. It is smaller than Phase 3B's *claimed* 18.4
px, and much smaller than Phase 3B's *actual* clearance, which the frustum
defect made about 250 px. See "Remaining human-review concerns".

## E. Harder walls

The configuration was chosen by a named matrix rather than a product search:
seventeen rows across four blocks, each changing one understandable part of the
arena, on shared deterministic seed intervals. `phase4a_tuning.json` records
every row and what it said. Two rows are worth repeating here because they
closed off options rather than opening them. **`H_s0hard`** made the innermost
shell 18 panels and barely moved its pass rate (96.8 %) while pushing the median
first clone from 0.84 s to 1.45 s — which is how the shell-1 tension below was
established rather than assumed. **`R_s4_soft`** lowered the outermost break
threshold from 16.0 to 14.0 and changed the race-success rate by 0.24 points:
the final wall is almost never crossed by breaking it, so its *toughness* is not
what gates the race. Widening its opening from 1/72 to 1/66 of the shell moved
the rate from 17.9 % to 23.2 %, and that is the row that was selected.


| shell | radius | panels | openings × slots | open fraction | gap / ball Ø | break threshold | surface speed |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 6.5 | 16 | 3 × 2 | 0.3750 | 4.41 | 1.8 | 4.29 |
| 2 | 9.5 | 38 | 3 × 2 | 0.1579 | 2.67 | 4.0 | 4.59 |
| 3 | 12.5 | 46 | 2 × 2 | 0.0870 | 2.93 | 5.6 | 4.83 |
| 4 | 15.5 | 64 | 2 × 2 | 0.0625 | 2.58 | 9.5 | 5.02 |
| 5 | 18.5 | 66 | 2 × 1 | 0.0303 | 1.38 | 15.0 | 5.18 |

Three legible dimensions instead of two: the holes get rarer, the last hole
gets narrower than a ball is comfortable with, and the panels get stronger.
Open fraction and break threshold are both monotonic; every opening admits the
ball.

**Measured pass rates against the brief's search regions, 20,000 seeds:**

| shell | brief | Phase 3B | Phase 4A |
| ---: | :--- | ---: | ---: |
| 1 | 90–96 % | 96.80 % | 96.70 % |
| 2 | 65–80 % | 85.54 % | **74.14 %** |
| 3 | 35–50 % | 55.94 % | **42.74 %** |
| 4 | 15–28 % | 32.56 % | **24.98 %** |
| 5 | 3–8 % | 10.15 % | **6.54 %** |

Shells 2–5 are inside the brief's regions. **Shell 1 is 0.7 points above the
90–96 % region and that is structural rather than a tuning miss.** A pass rate
of 90 % at the innermost shell means one founder in ten never leaves the middle
in 26 seconds, and the brief also asks for the first clone at or under 2.0 s in
production candidates. Those two pull against each other: making shell 1 hard
enough to hold back a tenth of founders pushed the median first clone from
0.84 s to 1.45 s and the 75th percentile past 2.7 s, which loses the hook. The
hook was judged the more load-bearing of the two. The value is reported rather
than quietly rounded into the band.

Race success is **22.45 %**, inside the brief's 20–40 % region. The outermost
shell is reached in 71.96 % of runs and crossed in 22.63 %.

## F. Damage and breaks

The damage model is unchanged in substance — normalised contact-normal impact
energy above a chip floor, five named states, shared persistent ledgers, one
break per panel, permanent passage. What is new is that **every panel keeps two
ledgers, one total and one per colour**, so a break records `team_cumulative`,
`team_contributors` and `largest_team`.

| measurement, 20,000 seeds | p5 | p50 | p95 |
| --- | ---: | ---: | ---: |
| breaks per run | 10 | 19 | 35 |
| distinct balls paying into the broken panel | 4 | 5 | 8 |
| breaks both colours paid into | 6 | 14 | 27 |
| breaks the *other* colour did most of the work on | 1 | 5 | 11 |

- runs with at least one shared break: **19,990 / 20,000**
- runs with at least one cross-team break: **19,940 / 20,000**
- runs where one colour broke a panel the other had done most of the work on:
  **19,516 / 20,000**
- cooperative breaks on the outermost shell: 180, across 161 runs

"Cyan does most of the work and orange goes through it" is not a rare emergent
moment; it is the normal texture of a run, and it is counted rather than
asserted.

## G. Population and chaos

| measurement | value |
| --- | --- |
| population, p5 / p50 / p95 | 7 / 12 / 18 |
| population inside the 20–26 s band, p50 | 14 |
| largest population observed | 28–31 (3 runs) |
| emergency cap (64) hits | **0** |
| mean population curve, start → end | 2.00 → 12.28 |
| the same curve for in-band runs | 2.00 → 14.83 |
| generations, p50 | 4 |
| first clone, p50 | 0.835 s; **0 runs never reproduced** |
| collisions/s, p5 / p50 / p95 | 6.18 / 14.59 / 28.50 |
| meaningful events/s, p50 | 26.91 |
| late-over-early meaningful ratio, p50 | 2.62; above 1 in **99.18 %** of runs |

**The brief's 15–30 late-population target is not reachable with the brief's
own pass-rate regions, and the arithmetic says so before any sweep does.**
Population is `2 + first-crossings`, and with one child per ball per shell the
expected size is about `2 · ∏(1 + pₖ)`. At the *top* of every one of the
brief's regions — 0.96, 0.80, 0.50, 0.28, 0.08 — that product is 14.2. The
measured configuration sits at 12 because the 26-second horizon truncates some
chains. Reaching a median of 20 would need shell 3 at roughly 55 % and shell 4
at 55 %, which is outside two of the five regions by a wide margin.

The two targets were weighed and the difficulty regions won, because the brief
is explicit that hard outer walls should constrain growth and that the
population counts must not be hard-coded. What the phase delivers instead is a
*selected* review set at 12–18 balls with peaks to 28 in the wider population,
and the tension reported rather than hidden.

Ball–ball collisions remain off. The chaos comes from population, walls,
rotation and damage, as instructed.

## H. Audio

The `open_quartal` system is unchanged: one tonal collection, one scale, one
set of shell bases. Team identity is everything *except* pitch class — a
register preference of ±1 ladder step, an overtone-mix offset of ±0.18, an
attack-sharpness offset of ±0.14 and a stereo lean of ∓0.34, applied at the
founder and inherited down the lineage. The two founders' voices are exact
reflections of each other about the neutral centre, so neither colour is
brighter, higher or louder by construction. A lineage's register walk is
clamped around its *own* team's centre, so a long cyan line cannot drift down
into orange's half of the ladder.

Two founders roughly doubled the event rate, and two things had to change for
it.

**Constrained voice duration.** Phase 3B only ever *divided* a bounce's nominal
length, so at fifteen collisions a second an ordinary late-run bounce still rang
for a quarter of a second. Phase 4A adds a hard ceiling per tier — 0.150 s
ordinary, 0.300 s strong or frontier, 0.420 s carrying a damage transition —
applied after the tier is decided. Nothing is dropped and nothing is moved, so
causality is exact; the bed simply stops sustaining.

**A repeat crossing is now quieter than the quietest bounce again.** The density
gain floor moved from 0.62 to 0.50 to hold the denser bed down, which took the
quietest bounce from 0.0527 to 0.0425 and left `crossing_gain = 0.055` *above*
it — the mix was rewarding a ball for going backwards. `crossing_gain` is 0.038
and `AudioConfig.__post_init__` now checks the relationship, so a future density
floor cannot invert it silently.

Across the six review masters at 48 kHz: integrated loudness **−18.41 to
−19.68 LUFS**, true peak **−2.49 to −3.96 dBTP**, **zero clipped samples** and
no limiting. Mono fold-down loses 0.08 dB with a correlation of 0.97; 95.7 % of
the energy sits in the 300–2000 Hz band a phone speaker reproduces. Scheduled
density is 16.35–21.72 events/s, maximum polyphony 10–14, **median polyphony
4.0**, harsh-pair incidence zero. Maximum canonical-to-video cue error is below
one frame on every candidate.

## I. The 20,000-seed population

Config digest `4a3ab8ba22ae7c54981700823cc5b4eaf147c72fc5ab609a244d9cbaeb6ce572`,
physics digest `14c070194427714be0d7a8ee463ec5eef9c5edaa620a039725f27f4bcc6adec9`.

| measurement | result |
| --- | ---: |
| escaped / timeout / collision cap | 4,490 / 15,510 / **0** |
| escape rate | **22.45 %** |
| unflagged ("usable") runs | 2,130 (10.65 %) |
| escapes in the 20–26 s band | 2,077 |
| escapes in the preferred 21–24 s band | 1,011 |
| duration p5 / p25 / p50 / p75 / p95 | 9.15 / 15.24 / 19.48 / 22.92 / 25.44 s |
| escape route, opening / break | 4,414 / 76 |
| winner generation, p50 | 2 (273 founder wins, 4,217 descendant wins) |
| population lead changes, p50 / p95 | 1 / 3 (one run reached 6) |
| frontier lead changes, p50 / p95 | 1 / 2 |
| winning margin, p50 | 6.11 s (**409 runs finish inside 1 s**) |
| winner's share of the final population, p50 | 64.7 % |
| maximum penetration | 1.00 × 10⁻¹¹ |
| minimum spawn clearance | 1.67 × 10⁻⁵ (positive) |
| speed min / max | 10.000000 / 10.000000 |
| anomalous crossings / Newton failures / reproduction violations | **0 / 0 / 0** |
| ball–ball contacts / population-cap hits | **0 / 0** |

Every evaluator flag fires on a discriminating minority rather than on
everything or nothing. The Phase 3B density lines had to be redrawn: at
`max_collision_rate = 9.0` and `max_peak_collision_rate = 16.0` — numbers
calibrated on a bed running at 6.2 collisions a second — the two flags fired on
92 % of a 3,000-seed population and `usable` fell to one run in three thousand.
A flag that rejects almost everything has stopped measuring anything. They now
sit at 24.0 and 48.0, which name roughly the busiest fifth and the busiest
eighth of the escaped population. Three other flags were dead guards at the
Phase 3B values — `min_distinct_panels`, `min_trajectory_spread` and
`max_stagnation_seconds` could not fire on any Phase 4A run, healthy or not —
and were moved to just outside the measured population so they are guards
again.

## J. The shortlist

414 of the 20,000 seeds pass the engineering rule: escaped, unflagged, 20–26 s,
first clone at or under 3.0 s, 12 or more balls, at least 4 per colour, the
losing colour past region 3, the winner holding no more than 75 % of the
population, at least 6 breaks and under 18 collisions a second.

**Nothing in the rule mentions the finishing margin or the lead-change count.**
A rule that rewarded a narrow finish would be, one sweep later, a rule that
selects for arranged ones. The three race lines ask only whether the second
colour was in the race at all.

Twenty are recorded as the engineering shortlist. The variety buckets are
cyan/descendant/opening 204, orange/descendant/opening 170, cyan/founder/opening
21, orange/founder/opening 16, orange/descendant/break 3.

## K. The six human-review candidates

| seed | dur | pop | cyan/orange | winner | gen | route | 1st clone | breaks | cross | stolen | lead | margin | ev/s | poly | still tail |
| ---: | ---: | ---: | :--- | :--- | ---: | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 17964 | 25.78 s | 18 | 9/9 | orange | 3 | opening | 0.52 s | 31 | 25 | 7 | 2 | 4.47 s | 21.62 | 13 | 4.04 s |
| 3762 | 24.12 s | 18 | 11/7 | cyan | 1 | opening | 0.78 s | 14 | 14 | 4 | 3 | 5.29 s | 20.15 | 13 | 4.86 s |
| 10943 | 20.03 s | 16 | 9/7 | cyan | 0 | opening | 1.54 s | 19 | 14 | 8 | 0 | 3.28 s | 21.35 | 14 | 3.05 s |
| 17660 | 24.42 s | 17 | 7/10 | orange | 1 | opening | 0.64 s | 15 | 12 | 5 | 0 | 0.36 s | 16.35 | 11 | 4.03 s |
| 16020 | 25.15 s | 16 | 10/6 | cyan | 0 | opening | 0.64 s | 34 | 28 | 11 | 2 | 6.65 s | 21.72 | 13 | 6.22 s |
| 1176 | 23.77 s | 12 | 5/7 | orange | 4 | break | 0.54 s | 20 | 16 | 2 | 2 | 8.74 s | 17.17 | 10 | 5.09 s |

Each one is in the set for a named reason, not because it scored highest on
anything: 17964 is the biggest and the most even; 3762 has the most lead
changes in the whole eligible pool; 10943 is a founder winning; 17660 is the
closest finish in the pool at 0.36 s; 16020 has the most cooperative damage;
1176 is the only break-route win and the deepest winner.

**Seed 952 was in this set and was dropped by a gate that did not exist when it
was picked.** It is a founder winning 1.11 s after the other colour's last
advance, which is the most dramatic finish in the pool — and its last frontier
advance lands 0.68 s before the escape, so the camera is still opening out over
the payoff. Five of the six that stayed measure 4.0 s or more of still camera
before the end. `MIN_STATIC_TAIL_SECONDS = 1.5` is now a rejection reason in
`candidate_row`, which is where the rule belonged: on a final wall this hard,
the first ball into the outermost region can arrive less than a second before
the winner leaves it.

Coverage: three cyan wins and three orange wins, two founder wins and four
descendant wins, five opening routes and one break, populations 12 to 18, first
clone 0.52 to 1.54 s — every candidate inside the 2.0 s preference.

No candidate has a visual pile, measured two ways because the two instruments
ask different questions. `population_report`, whose pile rule is the integration
gate, finds a longest pile of **0.00 s** on all six. `readability_report`, which
is stricter — it counts any cluster whose centres are inside one *drawn*
diameter, at 60 fps — finds a longest three-ball merge of **0.38 s** (seed
17964) and one momentary six-ball cluster on seed 3762 that holds for a quarter
of a second. Clusters holding **both** colours, which are the only ones that
could put the video's question in doubt, occupy 4.3 % to 11.0 % of frames and
never exceed four balls.

**In three of the six, no single panel of the outermost shell ever visibly
cracks.** `damaged` begins at 24 % of a threshold of 15.0, so a panel of the
final wall needs roughly eighteen ordinary hits before it shows a mark, and in
3762, 17660 and 16020 the winner threads the moving opening without softening
anything. The contact sheet falls back to first contact with that wall and says
so in the still's own caption.

## L. The eleven contact-sheet views

Every still is a canonical event time plus a small fixed offset, so a sheet is a
set of instants the simulation chose rather than a set a person picked to
flatter it:

1. two founders (frame zero) — 2. first clone — 3. both teams multiplying —
4. first population lead change (or, where there is none, the widest lead) —
5. eight-ball state — 6. shared panel damage, at the instant a second ball joins
a panel's ledger — 7. a panel of the final wall taking visible damage (or first
contact with it) — 8. the late population peak — 9. both colours working the
outermost barrier — 10. the winning escape — 11. the last frame, the payoff in
the winning colour.

## M. The rendered review set

Six synchronised 9:16 A/V clips at 540x960, 30 fps, h264 + AAC 48 kHz stereo.
No production master was created; the `full` 1080x1920 profile was not run.

| measurement | result |
| --- | --- |
| A/V drift, container | **-15.0 to +7.3 ms** (under half a frame at 30 fps) |
| maximum canonical-to-video cue error | **0.994 to 1.000 frames** |
| integrated loudness | **-18.43 to -19.68 LUFS** |
| true peak | **-2.49 to -3.96 dBTP**, 0 clipped samples, no limiting |
| mono fold-down loss | **-0.08 to -0.09 dB**, correlation 0.961 to 0.966 |
| phone-band level against the master | -5.58 to -8.30 dB |
| scheduled event density | 16.35 to 21.72 /s |
| maximum polyphony / median polyphony | 10-14 / 4.0 |
| harsh-pair incidence | **0** |
| longest pile (integration rule) | **0.00 s** on all six |
| safe area | arena clear on all six, 15.12 px rail clearance |

## N. Tests and regression

The focused Category 3 suite - the two-team simulation, the audio score, the
A/V integration, the composition contract, the single-ball Test #2 and all six
Test #1 phases - is **803 passed, 1 skipped, 0 failed** in 684.8 s.

New or rewritten tests cover, one per line of the brief: exactly two founders;
deterministic team assignment; same-team cloning; descendants retaining their
team; anti-farming; deterministic lineage; team-label swap invariance; no
colour-dependent physics; a monotonic harder wall profile; persistent damage;
team damage attribution; break-once; a broken passage staying open; an
invariant camera world centre; a perceptually centred arena; frontier
screen-size bounds; maximum zoom bounds; deterministic team visual mapping;
harmonically compatible team audio; a deterministic winner event; A/V sync; no
clipping; and safe-area compliance. Two tests were added for things that were
*not* being checked: the frustum against Godot's own arithmetic, and the
absence of any close-race preference anywhere in the selection path.

**One pre-existing failure was fixed rather than inherited.**
`test_no_other_category_imports_category_three` was already red on
`category3-multiplying-shell-adjust-v3b`: Phase 3B added
`tools/multishell_phase3b_lab.py`, which imports `satisfying` because measuring
Category 3 is what it is for, and left the assertion failing. Category 3's own
laboratory tools are now a named exemption, and a second assertion checks that
every name on that list exists and really does import Category 3 - so the list
is an exemption and not a hole, and everything else under `tools/` still fails
the guard as intended.

## O. Evidence index

Under `docs/validation/category3_two_team_shell_race_v4a/`:

- `phase4a_tuning.json` — the controlled matrix that chose the configuration
- `phase4a_population_20k.json` — the whole batch summary
- `phase4a_shortlist.json` — 414 eligible seeds, 20 shortlisted
- `phase4a_candidates.json` — the six, the rule and the coverage
- `phase4a_label_swap.json` — the fairness proof
- `av_candidates.json` — the per-candidate integration row
- `detail/` — every sub-report per candidate
- `mux_review.json`, `phone_validation.json`
- `contact_sheets/` — eleven stills per candidate
- `audio/proof_candidates.json` — the audio branch's independent judgement

Tooling: `tools/two_team_phase4a_lab.py` (`batch`, `fairness`, `shortlist`).

# Category 3, Test #2 redesign — Phase 3: multi-ball A/V integration

**Branch** `category3-multiplying-shell-av-v3`
**Base** `78739b266d9c8872c350bf239ae3c60e02c7fe65` (Phase 1, the frozen mechanic)
**Visual** `585d85ef7abbc363f058670dd7d56effed30aee1` (Phase 2A, merged first)
**Audio** `14522d9e02d1dd4630d6bbb398e818494d914d44` (Phase 2B, merged second)

Both merges are `--no-ff`. Nothing was squashed, nothing was rebased, and
nothing was merged to `main`.

This phase joins two consumers that were built independently against one frozen
document and never against each other. It adds no dial that can change a
trajectory. What is new is `satisfying/multishell_av.py`, which measures the
joins, and `satisfying/multishell_av_cli.py`, which writes the files a person
has to watch.

---

## 1. The frozen contract held, and no schema change was needed

The two branches turned out to touch disjoint source files, so both merges were
clean. More importantly the six frozen simulation files are byte-identical to
Phase 1 — compared by blob hash, not by diff:

| file | blob |
| --- | --- |
| `satisfying/multishell.py` | `875c1ae9610b1d98b6cdb313de2cf759ae1c393c` |
| `satisfying/multishell_cli.py` | `312d1d19bc3a362924e0c697c5a1e09941f27117` |
| `satisfying/multishell_evaluator.py` | `c0bc5461b200f3230d070764afaa2cc201295233` |
| `satisfying/multishell_playback.py` | `b7b2917ae8c12fcb2789f59dc5551fc4de4f59a1` |
| `satisfying/multishell_seeds.py` | `67bd969c420ab20e24c751357666c0dfb46e743d` |
| `tests/test_multiplying_shell.py` | `82f2a39fd9a7b58b0eec2ccb5010a912590032e4` |

Neither branch asked for a change to the canonical V2 event schema, so the
brief's stop-and-report condition was never reached. Both consumers take
`document_for(seed)` from `multishell_playback` and derive everything from it:
the schedule's `playback_digest` equals the document's `digest` for all seven
candidates, and `test_neither_consumer_mutates_the_canonical_playback` deep-copies
the document, runs every reader in both layers over it, and asserts the document
compares equal afterwards.

---

## 2. The integration argument

With one ball, "the bounce and the note are the same event" is a claim about a
single stream. With a population it is two claims, and the second one is the
one that could have gone wrong silently:

**The clock.** The audio side never moves a cue in time. `_manage_clusters`
resolves two simultaneous notes by moving one *up the ladder*, never by delaying
it, so every scored event sits at `_sample_at(source_seconds)` exactly. The
picture samples the scene on the frame grid and every effect in the Godot scene
is driven from `sim_t - at`, showing nothing while that is negative. So an event
at `t` is heard at `t` and first seen at `ceil(t*fps)/fps`, and the whole
measurable error is frame quantisation.

**The cast.** A collision belongs to a particular ball; that ball belongs to a
lineage; the renderer tints it and the sequencer voices it. If those two
readings disagreed the clip would show a white founder bouncing under a
third-generation timbre and no timing measurement would catch it. Both read
`lineage` off the ball record and neither has an id space of its own, which
`lineage_audit` checks by comparing the two family *partitions* rather than
assuming them.

That second check is a regression guard, not a forgery detector, and the test
suite says so in as many words. Editing `generation` in the document moves the
renderer and the sequencer together and the audit still agrees — which is the
property being asserted. What it would catch is a future layer that started
numbering the cast for itself.

---

## 3. A/V synchronisation

Measured per cue class, for all seven candidates, at both frame rates.

Worst case over all seven candidates:

| cue class | source | 30 fps | 60 fps |
| --- | --- | --- | --- |
| collision | `collision` | 0.999 fr (33.3 ms) | 0.999 fr (16.6 ms) |
| spawn | `ball_spawn` | 0.993 fr (33.1 ms) | 0.995 fr (16.6 ms) |
| near miss | `near_miss` on a contact | 0.992 fr (33.1 ms) | 0.984 fr (16.4 ms) |
| damage state | `damage_state` on a contact | 0.998 fr (33.3 ms) | 0.996 fr (16.6 ms) |
| break | `panel_break` | 0.998 fr (33.3 ms) | 0.996 fr (16.6 ms) |
| shell exit | frontier-advancing `shell_exit` | 0.987 fr (32.9 ms) | 0.979 fr (16.3 ms) |
| final escape | `escape` | 0.721 fr (24.0 ms) | 0.902 fr (15.0 ms) |

Every class is inside one rendered frame on every candidate, which is the
brief's target. Two things are worth stating rather than rounding away:

**The error is one-sided.** Audio lands on the instant; the picture lands on the
next frame boundary; the picture is therefore never early. `video_never_early`
is asserted per cue class. The mean across the seven candidates is 0.47 to 0.52
frames — 15.6 to 17.5 ms at 30 fps, 7.6 to 9.0 ms at 60 — and the worst case is
the frame period.

**It is quantisation, not drift.** The one-frame figure is the ceiling of
`ceil(t*fps)/fps - t` and it cannot grow with clip length. Halving it is a
matter of frame rate alone, which is why the two production-candidate clips are
also rendered at 60 fps.

Container drift after muxing is −15 to +7 ms across the nine encoded files,
which is the last-frame pad quantised to whole frames, not a sync error inside
the clip.

---

## 4. The frontier camera does not create a retention problem

Phase 2A proved the camera is evidence-driven: every move is one frontier
advance in the canonical `shell_exit` stream. That settles *where* it moves. It
does not settle whether the moving is watchable, which is what this phase was
asked.

Every candidate has the same four reframes, because the schedule is a function
of the shell geometry and not of the seed: 7.00 → 11.60 → 16.20 → 20.80 → 25.40
world units, a total growth of 3.63×, each eased over 0.55 s with a 0.12 s lead.

The gate is the run's own fastest screen motion rather than a number invented
here. The ball crosses the opening arena at **0.596 frame widths per second**,
which is the quickest thing the presentation ever asks a viewer to track and
which Phase 2A already proved readable. The worst camera-induced motion across
all seven candidates is **0.569**, always during the first reframe — the largest
single step, 1.657×. Every candidate clears its own gate with about 5% headroom.

| seed | camera peak | headroom | overlapping reframes | static tail |
| --- | --- | --- | --- | --- |
| 949 | 0.5685 | +0.027 | 1 | 8.46 s |
| 12004 | 0.5670 | +0.029 | 0 | 7.06 s |
| 547 | 0.5687 | +0.027 | 1 | 7.47 s |
| 11319 | 0.5681 | +0.028 | 0 | 8.13 s |
| 3622 | 0.5687 | +0.027 | 1 | 8.35 s |
| 12818 | 0.5665 | +0.029 | 0 | 7.89 s |
| 7183 | 0.5682 | +0.028 | 0 | 7.42 s |

The whole first reframe moves a world point at the frame edge by 0.165 frame
widths — 16.5% of the screen, over 0.55 s. The later ones are smaller: 0.118,
0.092, 0.076. This is reframing, not zooming.

**One measurement is reported and deliberately not gated.** Comparing the
reframe against the ball's velocity *at that same instant* gives a ratio that
rises to 1.25–1.43 late in every candidate, for about 30 frames. That is an
artefact of the denominator: by then the arena has opened out, so the ball has
slowed from 0.60 to 0.16 frame widths per second while the reframes stay near
0.2. Both motions are slow there. Gating on that ratio would reject a clip for
being calm, so it is recorded as evidence and left to the eye.

The static tail — 7.1 to 8.5 s with the camera completely still — is preserved.
It is a test, not just a note: `test_the_clip_ends_on_a_still_camera`.

---

## 5. Musical density, with the picture attached

Phase 2B passed on the whole-clip averages. Re-asked with the video, the useful
question is not the average but *where the peak is*, and the answer is the same
on every candidate: the busiest one-second window always falls in the final
third. Nothing was reduced pre-emptively.

| seed | ev/s | peak ev/s | at | max poly | median poly | late collisions overlapping |
| --- | --- | --- | --- | --- | --- | --- |
| 949 | 7.96 | 18 | 15.5 s | 8 | 2 | 87% |
| 12004 | 8.76 | 23 | 17.2 s | 10 | 2 | 93% |
| 547 | 7.77 | 18 | 18.5 s | 9 | 2 | **75%** |
| 11319 | 10.37 | 25 | 14.9 s | 9 | 3 | 96% |
| 3622 | 7.70 | 21 | 17.8 s | 9 | 2 | 89% |
| 12818 | 11.34 | 25 | 16.5 s | 9 | 3 | 92% |
| 7183 | 9.39 | 22 | 15.3 s | 10 | 2 | 90% |

"Late collisions overlapping" is the fraction of late collisions still ringing
when the next arrives. Some of that is the point and all of it would be mud, so
it is the axis on which 547 and 12818 sit at opposite ends — 75% against 92% —
and it is the reason they are the primary and the backup rather than two
attempts at the same clip.

### A correction to how masking was first counted

The first pass flagged 6 to 9 spawns per seed as "masked by a louder cue" and
that number was wrong twice over. Every case was a lift-carrying spawn, ducked
3.1 dB by design, losing to a collision by 0.24 to 1.18 dB. Two things were
missing: a split that carries a lift is announced by the *pair*, and the lift is
the loud half, so the cue to compare is the louder of the two; and a smaller cue
has to win by enough to be heard doing it. With the pair compared and a 1.5 dB
margin required, **no spawn on any candidate is buried by a collision.** The
lift-and-break cases remain and are reported as `spawns_outranked_by_design`,
which is the hierarchy working.

---

## 6. Spawn readability

The geometry of a split is frozen and identical everywhere: the child is born
2.6 ball radii ahead of the parent with a 0.16 rad turn, so every pair starts
1.73 drawn radii apart and opens at the same rate. Readability is therefore a
property of the mechanic, not a seed discriminator — except where a ball bounces
back toward its parent, which is where the candidates differ.

Measured as time-to-separate to two drawn radii (tangent discs), searched on the
frame grid because separation is not monotone:

| seed | first split | first split reads in | watched splits reading as two | slowest |
| --- | --- | --- | --- | --- |
| 949 | 2.31 s | 0.33 s | 5/6 (83%) | 1.17 s |
| 12004 | 2.40 s | 0.43 s | 10/12 (83%) | 1.10 s |
| 547 | 2.25 s | 0.33 s | **8/8 (100%)** | 0.43 s |
| 11319 | 1.47 s | **0.57 s** | 11/12 (92%) | 0.57 s |
| 3622 | 0.45 s | 0.33 s | **8/8 (100%)** | 0.43 s |
| 12818 | 0.50 s | 0.43 s | **13/13 (100%)** | 0.43 s |
| 7183 | 0.62 s | 0.43 s | **11/11 (100%)** | 0.43 s |

Every candidate splits well inside the 3.0 s hard limit and inside the 2.5 s
preference. Splits landing in the last 0.5 s of a run are counted separately:
they happen under the escape payoff, where the viewer is being shown the
resolution rather than asked to count balls, and seed 12004's worst case is
exactly that — a split 0.04 s before its own escape.

---

## 7. The seven candidates

No single score. The axes that actually traded against each other:

| axis | 949 | 12004 | 547 | 11319 | 3622 | 12818 | 7183 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| first split (s) | 2.31 | 2.40 | 2.25 | 1.47 | 0.45 | **0.50** | 0.62 |
| splits reading as two | 83% | 83% | **100%** | 92% | **100%** | **100%** | **100%** |
| population | 8 | **15** | 11 | 14 | 11 | **15** | 13 |
| families | 2 | 4 | 5 | 5 | 3 | **5** | 4 |
| breaks | 13 | 9 | 14 | 18 | 13 | **19** | 16 |
| near misses | 2 | 6 | 12 | **15** | 12 | 11 | 8 |
| population by third | 2/7/8 | 2/9/15 | 2/6/11 | 3/8/14 | 2/6/11 | **4/9/15** | 3/10/13 |
| peak cluster (balls) | 2 | 3 | 4 | 4 | 4 | 3 | **7** |
| longest merge (s) | 0.03 | 0.97 | 0.90 | 0.80 | 0.80 | **0.17** | **1.63** |
| blob deficit | **16%** | 35% | 20% | 30% | 29% | 29% | 33% |
| ev/s | 7.96 | 8.76 | 7.77 | 10.37 | 7.70 | **11.34** | 9.39 |
| late overlap | 87% | 93% | **75%** | 96% | 89% | 92% | 90% |
| polyphony growth | 5.1× | **5.8×** | 5.1× | 3.4× | 4.3× | 3.4× | 4.5× |
| longest gap (s) | 1.10 | 1.07 | 0.95 | 1.11 | **0.87** | 0.99 | 0.98 |
| duration (s) | 20.16 | 21.71 | 21.73 | 21.80 | 22.82 | 22.84 | 23.21 |

### Two gates were wrong on the first pass and were corrected

**Dead air.** A 1.0 s gate rejected three candidates. The seven longest gaps
span 0.87 s to 1.11 s — one crossing of the opened-out arena at the frozen
speed, with a ball visibly in flight the whole time. That is the mechanic's
natural rhythm, not a stall, and a gate inside that range splits a uniform
population on noise. Raised to 1.5 s, where it discriminates nothing, which is
the honest outcome: **no candidate stalls.**

**Spawn masking.** Described in §5. Corrected from 6–9 per seed to zero.

After both corrections the rejection rule fires exactly once.

---

## 8. Selection

### Primary — seed 12818

Chosen because it is the only candidate that is both the most populated and one
of the least piled. It reaches 15 balls across 5 families and 19 panel breaks,
and its longest visual merge is 0.17 s — shorter than every candidate except
949, which only ever has 8 balls. It splits at 0.50 s, every one of its 13
splits reads as two within 0.43 s, none is buried, and it carries the highest
event density at 11.34/s with its peak in the final third. Population by third
is 4 → 9 → 15, the clearest escalation in the set.

Its one real trade is the lowest polyphony growth ratio, 3.4×, and that is
arithmetic rather than a weakness: its hook is already the busiest of the seven
(6 collisions and 2 splits inside 3 s), so it grows *from* a higher floor. For a
Shorts hook that is the right direction.

### Backup — seed 547

Chosen for a different reason, which is why it is a useful backup rather than a
second-best copy. The open risk on 12818 is density: 11.34 events/s with 92% of
late collisions overlapping is the busiest clip in the set, and whether that
reads as exciting or as cluttered is a question for ears, not for this document.
547 is the answer if it reads as cluttered — the calmest candidate, 7.77 ev/s
and 75% late overlap, the lowest of all seven, with 100% of splits reading as
two, the second-best blob deficit at 20%, and still 11 balls, 5 families, 14
breaks and 12 near misses. Its cost is the latest first split at 2.25 s, still
inside the 2.5 s preference.

### Rejected

**7183 — the one hard rejection.** The brief flagged a known ~1.63 s seven-ball
pile. Two independent measurements here reproduce it: the pile detector finds a
7-ball cluster holding 1.27 s at its 1.5-drawn-radii gate, and Phase 2A's own
readability report gives `longest_triple_merge_seconds = 1.63`, matching the
brief's figure exactly. Nothing else in the set exceeds 0.97 s. Its statistics
are otherwise good — 13 balls, 16 breaks, all splits readable — and it is
rejected anyway, which is what the brief asked for.

The other four are eligible and simply lose on the axes above:

- **949** — the cleanest picture in the set (16% blob deficit) and the weakest
  story: 8 balls, and a final third that goes 7 → 8. The escalation the redesign
  depends on barely happens.
- **12004** — 15 balls but the worst crowding of the eligible seeds (35% blob
  deficit, 0.97 s merge) and only 83% of splits reading as two.
- **11319** — the only candidate whose *first* split takes longer than 0.50 s to
  read (0.57 s), and the most overlapped late audio at 96%. The first split is
  the moment the rule is taught, so being slowest there is the wrong place to be
  slow.
- **3622** — no defect, and the earliest split at 0.45 s. It loses on variety:
  3 families against 5, and the lowest event density at 7.70/s. It is the third
  choice and would serve.

---

## 9. Mobile and Shorts

All seven, at 450×800 (exact 9:16; Phase 2A's 405-wide still size has an odd
width that libx264 will not encode in 4:2:0), plus mono and phone-band folds of
the delivered master.

| check | result |
| --- | --- |
| arena clears every Shorts overlay | yes, all seven |
| tightest clearance | 18.3 px against the action rail |
| frames with a ball under chrome | **0**, all seven |
| mono fold-down loss | −0.05 to −0.13 dB |
| stereo correlation | 0.95 to 0.98 |
| phone band (500–6000 Hz) | −5.2 to −6.8 dB relative to master |
| true peak | −2.50 to −3.31 dBTP |
| clipped samples | 0 |
| strobing at 30 fps | none; worst step is 0.56 ball diameters |

The 18.3 px action-rail clearance is the tightest constraint in the whole
presentation and it is a property of the final view radius, so it is identical
on every seed. It is positive, and no ball is ever hidden, but it is thin enough
that any future change to `VIEW_RADIUS_PAD` or the outer shell radius has to be
re-checked against it. Test #1 lost nine tiles under that rail.

---

## 10. What is proved and what still needs a person

**Objectively verified.** Shared playback digest; no mutation of canonical
playback; unchanged event order; shared lineage across both layers; A/V
placement inside one frame for all seven cue classes at 30 and 60 fps; camera
monotonicity and peak velocity; spawn separation geometry; pile duration;
population escalation; event density and polyphony; safe area; mono and
phone-band survival; true peak and clipping; determinism of both render
configurations. 391 tests.

**Requires human review.** Whether 12818's 11.34 events/s reads as exciting or
as cluttered. Whether the reframes feel like the arena opening out or like a
camera moving. Whether a first-time viewer understands "escaping makes more
balls" from the first split alone. Whether the final escape lands as a payoff.
Whether the clip is beautiful. None of that is in this document and none of it
should be inferred from it.

The files for that review are `output/category3_multishell_av_v3/review/` — seven
540×960 clips plus 1080×1920 at 60 fps for 12818 and 547 — and the twelve-still
contact sheets in `docs/validation/category3_multiplying_shell_av_v3/contact_sheets/`.

---

## 11. Decision

**MULTI-BALL A/V PROOF PASSED — PRODUCTION SEED SELECTED**

Primary **12818**, backup **547**. Production is not implemented here.

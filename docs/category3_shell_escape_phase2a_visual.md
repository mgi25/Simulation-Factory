# Category 3, Test #2 — MUSICAL SHELL ESCAPE, Phase 2A visual proof

## Decision

Yes. Without narration, the frame reads as one bright ball trapped inside six
moving barriers; the cyan post pairs expose the moving holes; clipped-post
contacts read as a sharper local flash; amber/red panels show real accumulated
damage; missing panels remain missing; increasing radius and the shrinking set
of barriers communicate progress; and the final ball position plus `ESCAPED`
confirmation makes the release unambiguous.

This is a visual proof, not an upload master. It contains no production audio,
does not pick the production seed, and does not modify Phase 1 physics,
evaluation, schemas, or seed generation.

## Frozen boundary

- Parent: `category3-shell-escape-v1` at
  `42cdbb34588f052be45377d7c20c89d8100fcf99`.
- Event schema: `category3-test2-shell-escape/1.0.0`.
- Playback schema: `category3-test2-shell-escape-playback/1.0.0`.
- Config digest: `7da0cbc80d5958260b65417c1ac94fac2285471aaf8adc4f093b27e3445afb3e`.
- Godot reads `flights`, `shells`, `panel_states`, and `events`. It has no
  physics bodies, collision solver, response law, random source, or seed path.
- Every frame is addressed by `frame_index / fps`. Ball position is evaluated
  from the document's current flight. Shell angle is the document's
  `theta0 + omega * t`. A panel exists exactly when it was not an original
  opening and its canonical break time has not arrived.
- The 120 ms release continues the already-recorded final flight only after the
  terminal escape. It then holds for 630 ms and stops. No pre-escape position,
  velocity, event, or time is changed.

The recorded Godot audit for seed 9589 agrees on the source digest, schemas,
all 187 event identities and order, the complete panel-state ledger, and every
sampled flight position. Worst Godot/Python float delta is
`7.80e-7` world units. The same audit passes at 30 and 60 fps.

## Composition and safe area

The conservative Test #1 Shorts model (`3776358f1bf13326`) was applied before
polish. A centered 86%-wide arena was rejected. The accepted fixed composition
is 72% of frame width, centered at `(0.410 W, 0.500 H)`.

At 1080 × 1920:

| Measurement | Result |
| --- | ---: |
| Arena / outer-shell diameter | 777.6 px (72.0% width) |
| Arena box | x 54.0–831.6, y 571.2–1348.8 px |
| Outer shell to nearest Shorts region | 75.6 px |
| Hook to nearest Shorts region | 34.6 px |
| Opening-marker minimum clearance, seven candidates | 75.9 px |
| Ball frames under a conservative region | 0 |
| Worst final-escape clearance | 77.2 px (seed 18920) |
| Conservative gate | PASS, all seven candidates |

The safe-area overlay set is in
`output/category3_shell_visual_v2a/safe_area/`. It contains all seven required
moments for seed 9589 with Test #1's conservative control rectangles composited
over the actual Godot frame.

## Readability and continuity

| Measurement | 30 fps | 60 fps |
| --- | ---: | ---: |
| World scale | 16.904 px/wu | 16.904 px/wu |
| Drawn ball diameter | 25.695 px | 25.695 px |
| Frame-to-frame travel | 9.579 px | 4.790 px |
| Travel in drawn ball diameters | 0.373 | 0.186 |
| 80 ms trail length | 22.990 px | 22.990 px |
| Consecutive coverage | PASS | PASS |

The physical collision diameter remains 13.523 px; only the luminous disc is
drawn at 1.9× around the canonical center. The inner shell is 169.0 px across,
the outer shell 777.6 px. The smallest canonical opening is 27.9 px and the
outer openings are 110.8 px. Panel strokes vary from 6 to 11 px, with
shell-specific value and hue, structural posts, different panel counts, and
visible opening-end markers. The six layers therefore do not collapse into
six identical thin rings at phone size.

The 80 ms trail is intentionally shorter than Test #1's explored setting. At
this test's lower apparent speed, the drawn ball already overlaps its previous
30 fps position. The trail adds direction without turning into a fake arc.

## Canonical visual language

- `healthy`: shell-specific cool metal.
- `damaged`: amber, beginning at 35% of the canonical break threshold.
- `heavily_damaged`: orange-red with three small stress marks, beginning at
  72% of the canonical threshold.
- `broken`: the panel is absent forever, leaving short hot remnants at its two
  canonical endpoints.
- `near_miss`: a 130 ms post flash and four-pixel-scale spark, emitted only
  while a canonical `near_miss` event is active. A normal face hit cannot
  trigger it.
- `panel_break`: one restrained 180 ms local ring at the canonical break
  position. The persistent missing passage, not particles, carries escalation.
- passed shells are lowered in value. The current and outer shells remain
  bright, so outward progress is visible without a shell counter.

## Representative cast

These seven are from the existing Phase 1 shortlist. No new search was run.

| Seed | Duration | Final | Near misses | Breaks | First-time open/break route | Visual reading |
| ---: | ---: | --- | ---: | ---: | ---: | --- |
| 17534 | 21.13 s | break | 14 | 13 | 4/2 | Short, tense, damage-rich; middle progress arrives late. |
| 3654 | 21.21 s | opening | 13 | 9 | 5/1 | Clean opening-led read; least structural escalation. |
| 6903 | 21.39 s | break | 12 | 10 | 5/1 | Long outer-shell tension and clear break resolution. |
| 9589 | 22.94 s | opening | 15 | 17 | 3/3 | Strongest balanced visual baseline; most near misses. |
| 11929 | 22.11 s | break | 12 | 14 | 2/4 | Best contrasting break-heavy route; dense but readable. |
| 7699 | 25.47 s | opening | 14 | 18 | 4/2 | Most accumulated damage; strongest long-form option. |
| 18920 | 25.16 s | opening | 13 | 12 | 5/1 | Clean route, but latest outer sequence and least safe-area margin. |

The visual branch does **not** select a winner. Seeds 9589, 11929, and 7699
are the strongest deliberately different candidates to hand to Phase 2B.
Seed 9589 is the visual baseline, 11929 tests whether a break-dominant score is
more satisfying, and 7699 tests whether the longer damage accumulation earns
its extra runtime.

## Outputs

For every representative seed, Godot produced these seven 1080 × 1920 stills
and matching 360 × 640 phone versions:

1. `a_opening`
2. `b_first_shell`
3. `c_near_miss`
4. `d_panel_break`
5. `e_middle_progress`
6. `f_outer_sequence`
7. `g_final_escape`

They are under
`output/category3_shell_visual_v2a/seed<seed>/stills/` (98 evidence images).

Silent H.264/YUV420 previews, not masters:

- `output/category3_shell_visual_v2a/previews/seed9589_visual_preview_540x960_30fps.mp4`
- `output/category3_shell_visual_v2a/previews/seed11929_visual_preview_540x960_30fps.mp4`
- `output/category3_shell_visual_v2a/previews/seed7699_visual_preview_540x960_30fps.mp4`

The machine-readable evidence is in
`docs/validation/category3_shell_visual_v2a/`: candidate metrics, 30/60 fps
playback audits, and the preview manifest. Four additional Phase 1 playback
documents were generated for seeds 17534, 3654, 6903, and 18920 using the
already-frozen Phase 1 producer.

## Focused proof and regression

`tests/test_shell_visual.py` covers:

- exact frozen schema and config digest;
- Godot consumer architecture and absence of physics or audio;
- deterministic render constants and config fingerprint;
- canonical panel/opening geometry;
- canonical panel-state-to-visual-state mapping;
- near-miss feedback exclusivity;
- unchanged event ordering;
- all critical safe-area targets on all seven candidates;
- all seven evidence moments;
- requested duration, route, near-miss, and progression spread;
- the recorded Godot playback audit.

Focused result after the import-boundary correction: **63 passed**. The clean
full Category 3 rerun is **393 passed, 1 skipped** in 317.48 seconds. The skip
is inherited from Test #1. No existing guard was changed or weakened.

## Problems and A/V recommendation

- At phone scale, the near-miss spark is deliberately brief. Audio should
  reinforce the canonical `feature=post` distinction; visuals should not be
  made larger unless the combined preview still loses it.
- The shortest candidates have less time for broken geometry to accumulate;
  the longest candidates ask more of pacing. That is now an A/V comparison,
  not a reason to alter the simulation.
- Seed 18920 passes the conservative safe-area gate but has the cast's smallest
  final-release margin (77.2 px). Do not expand the post-escape flight during
  audio integration.
- Phase 2B should use these exact playback documents and align cues to the
  canonical event times. It should compare 9589, 11929, and 7699 before any
  final seed decision. Keep the visual render config digest
  `77335e59def5e7f7` fixed during that comparison.

VISUAL PROOF PASSED

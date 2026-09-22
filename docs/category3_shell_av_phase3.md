# Category 3, Test #2 — MUSICAL SHELL ESCAPE, Phase 3 A/V integration

## Decision

Seed **9589** is the primary production seed. Seed **11929** is the backup.

The combined result reads as the ball playing one changing six-register
instrument, not a physics clip with unrelated beeps. Collision attacks attach
to bounces, post contacts are sharper without becoming separate fake impacts,
near-miss ornaments reinforce the visible "almost," break chords coincide with
new permanent passages, first-time outward exits lift the register, and the
outer-shell escape resolves both picture and score. No integration defect
required a visual, audio, or timing change.

This phase makes previews, not an upload master.

## Git integration and frozen boundary

- Base: `42cdbb34588f052be45377d7c20c89d8100fcf99`.
- Visual input: `8dc61c27d9f9c2a8e848239771a33adf4d1a7b35`.
- Audio input: `0c8ce1f8132b3ec6188dd53ec931af4717f5c9f9`.
- Merge order: visual, then audio; two ordinary merge commits, no squash or
  rebase; no conflicts. Visual merge `db5dd21`, audio merge `5adbf1a`.
- Phase 3 integration commit: `8dc12cc`, on branch `category3-shell-av-v3`.
  Nothing is merged to `main`.
- Event schema: `category3-test2-shell-escape/1.0.0`.
- Frozen config digest: `7da0cbc80d595826…`.
- Visual config digest: `77335e59def5e7f7`.
- Audio config: `refined_hybrid`, fingerprint `eaedaafdb37866f1`.
- Integrated config digest: `063a4fa0c0f1d819`.

`shell_escape.py`, `shell_arena.py`, physics, damage, seed generation,
near-miss semantics, evaluation, and the canonical schemas are unchanged.
Phase 3 copies the already-recorded Phase 1 JSON; it never calls the simulator.
Godot and the score builder receive that same file.

## Exact preview configuration

| Property | Review set | Full-quality top two |
| --- | ---: | ---: |
| Frame | 540 × 960 | 1080 × 1920 |
| Frame rate | 30 fps | 60 fps |
| Camera | fixed, arena 72% frame width at `(0.410 W, 0.500 H)` | same |
| Hook | `CAN THE BALL ESCAPE?` | same |
| Visual release / hold | 120 ms / 630 ms | same |
| Visual codec | H.264, CRF 20, slow, YUV420p | H.264, CRF 17, slow, YUV420p |
| Audio | `refined_hybrid`, 48 kHz stereo | same |
| Preview audio codec | AAC 192 kb/s | same |
| Dynamics | static gain only; no compressor or limiter | same |
| End | final frame cloned only to the score end | same |

The PCM score ends with 150 ms exact digital silence. Decoding the final 100 ms
of every AAC review preview measures at ffmpeg's digital-floor reading of
-91.0 dB. All preview streams are 48 kHz stereo and match their source score
duration to the millisecond reported by ffprobe.

## Synchronisation

The visual consumer preserves every canonical event identity and order. Audio
cues retain the canonical event instant on the 48 kHz sample grid (worst error
under half a sample). A frame cannot show a between-frame event until its next
sampled scene time, so the measured integration error is the distance from
that sample-accurate cue to the first frame at or after it.

| Seed | Review max | Review frames | Full max | Full frames |
| ---: | ---: | ---: | ---: | ---: |
| 9589 | 33.208 ms | 0.996250 | 16.542 ms | 0.992500 |
| 11929 | 33.125 ms | 0.993750 | 16.458 ms | 0.987500 |
| 3654 | 32.708 ms | 0.981250 | — | — |
| 7699 | 32.896 ms | 0.986875 | — | — |

Every collision, post contact, near miss, panel break, first-time shell exit,
and final escape is below the hard one-frame limit at every rendered quality.
No cue offset was introduced: canonical timestamps remain the sole clock.

## Four-candidate integrated observations

### Seed 9589 — primary

The first collision arrives at 0.209 s and the first shell exit at 1.739 s, so
the premise rewards attention immediately even though the first near miss is
later at 5.245 s. The middle is the cast's strongest: 10 near misses, 10
breaks, and 6 shell exits keep prediction, geometry, and timbre changing.
First-time progress then arrives at 10.524, 11.432, 13.241, 16.616, and 22.849
seconds, preventing the latter half from becoming a repeated loop.

Musically it has the best balance of pace and space: 2.958 collisions/s, a
0.277 s median collision gap, 6.03 LU loudness range, only a two-note maximum
identical run, and 4.992 s of deliberate overlap. Its 17 break blooms feel
consequential without the density becoming relentless. The 6.233 s final-shell
sequence keeps the outcome uncertain, then the opening escape reads cleanly
and resolves to D major. Review duration is 23.761 s.

### Seed 11929 — backup

This has the strongest first second: the first contact at 0.298 s is already a
near miss, followed by an exit at 1.653 s and a break at 2.140 s. Its unusual
2-opening/4-break route makes the arena visibly and audibly destructive, and
the final visible panel break plus chord bloom is the clearest single combined
payoff in the cast.

The tradeoff is density. At 3.474 collisions/s, a 0.194 s median gap, and only
3.86 LU of range, it feels busier and less phrased than 9589. It reaches region
5 at 12.775 s and then spends 9.288 s resolving the outer shell. Late damage
and four near misses keep that stretch alive, but it is less compact. Review
duration is 22.935 s.

### Seed 3654 — rejected control

The start is clean and quick (collision 0.199 s, exit 1.511 s, break 2.041 s),
and it has the clearest, least-overlapped score. It is also the least changed:
only 9 panels break, and approximately 12.04 s pass between first-time region
3 and region 4 progress. The video remains readable and musical, but the
middle recreates Test #1's primary weakness: completion becomes plausible
without enough visible outward evolution. Review duration is 22.025 s.

### Seed 7699 — rejected control

The first collision is the fastest at 0.189 s and the first near miss arrives
at 1.034 s. Its 18 breaks produce the richest accumulated-damage picture, and
the 4/2 route stays locally unpredictable. It does not earn the added length:
first-time regions 2→3 are separated by about 9.01 s, and region 5→escape by
10.77 s. The score is rich but carries the most overlap (5.386 s), the cast's
longest collision gap (1.006 s), and the highest safe peak (-3.08 dBTP).
Review duration is 26.293 s.

## Candidate comparison

Every column below is measured from the same canonical playback the video and
the score were built from, so the four candidates are compared on one ruler.
"Longest frontier wait" is the largest gap between consecutive first-time
region advances - the clock on which a shell-escape video stops feeling like it
is going anywhere.

| Seed | Duration | Collisions | Near misses | Breaks | Route | Median gap | Identical run | Longest frontier wait | Density | LRA | True peak |
| ---: | ---: | ---: | ---: | ---: | :---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **9589** | 22.941 s | 66 | 15 | 17 | 3 open / 3 break | 0.277 s | 2 | **8.786 s** (r1→r2) | 2.958 Hz | 6.03 LU | -4.53 dBTP |
| **11929** | 22.115 s | 76 | 12 | 14 | 2 open / 4 break | 0.194 s | 3 | 9.288 s (r5→r6) | 3.474 Hz | 3.86 LU | -5.26 dBTP |
| 3654 | 21.206 s | 62 | 13 | 9 | 5 open / 1 break | 0.309 s | 3 | 12.038 s (r3→r4) | 2.978 Hz | 5.99 LU | -4.80 dBTP |
| 7699 | 25.473 s | 82 | 14 | 18 | 4 open / 2 break | 0.236 s | 2 | 10.770 s (r5→r6) | 3.237 Hz | 6.09 LU | -3.08 dBTP |

The decisive column is the last frontier one. 9589 has the shortest worst wait
in the cast, and it is the only candidate whose longest stall sits early, while
the opening is still establishing the premise and while 15 collisions, 2 breaks
and 2 outward exits are still arriving. Both rejected controls put their worst
wait *after* the audience already understands the premise: 3654 stalls 12.038 s
in the middle, and 7699 stalls 10.770 s in the last region, where a stall is
most expensive. 11929's 9.288 s wait is also late, which is the single reason
it is backup rather than primary.

That ordering is not a scoring formula. It is the one comparison where the four
candidates genuinely separate: near-miss counts (12-15), break counts (9-18),
true peak (-5.26 to -3.08 dBTP) and mono behaviour are close enough across the
cast that none of them would decide the question on its own.

## Conservative Shorts and listening checks

The existing analytic gate still reports 777.6 px arena diameter, 25.7 px
drawn ball, 110.8 px outer opening, 75.6 px outer-shell safe clearance, and
zero hidden-ball frames at full resolution. Five decoded frames per candidate
(opening, 25%, 50%, 75%, payoff) were inspected under the conservative Shorts
overlay. Moving openings, the outer shell, ball, local event feedback, and
release remain unobstructed; the locked hook remains above the title block.

All four WAVs were checked in stereo, mono, and a 300–3500 Hz phone-like fold.
Mono loss is only 0.07–0.10 dB with correlation 0.959–0.976. The phone-filtered
signal keeps 94.84–97.17% of its energy from 300–2000 Hz. No source clips, no
limiter is used, and true peak ranges from -5.26 to -3.08 dBTP.

## Artifacts and validation

- Four review MP4s, 540x960 at 30 fps, in
  `output/category3_shell_av_v3/previews/review/`: `seed_9589_av_review.mp4`,
  `seed_11929_av_review.mp4`, `seed_3654_av_review.mp4`,
  `seed_7699_av_review.mp4`.
- The two full-quality MP4s, 1080x1920 at 60 fps, in
  `output/category3_shell_av_v3/previews/full/`: `seed_9589_av_full.mp4`
  (1425 frames, 23.761 s) and `seed_11929_av_full.mp4` (1376 frames,
  22.935 s). Both are complete; each muxed frame count exceeds its rendered
  count by the final frame cloned to the score end.
- Reproducible playback, score, WAV, measurement, audit, frame, listening,
  and ffprobe artifacts: `output/category3_shell_av_v3/`.
- Tracked identities, deterministic scores, measurements, sync audits,
  delivery probes, experience metrics, and the explicit decision:
  `docs/validation/category3_shell_av_v3/`.

## Tests and regression

The whole Category 3 set - Test #1's six tile-escape phases, Test #2's Phase 1
shell escape, Phase 2A visual, Phase 2B audio, and this phase - runs green:

| Set | Passed | Failed | Skipped |
| --- | ---: | ---: | ---: |
| Category 3, all ten files | 423 | 0 | 1 |

The single skip is pre-existing and environmental: `test_tile_escape_phase3.py`
skips its evidence check because `output/` is gitignored and the Phase 3 CLI has
not been run in this tree. It skips identically at the Phase 1 base.

Integrating Phase 3 broke exactly one test, and it was a real failure rather
than a stale one: `test_category_three_imports_no_other_category_and_no_company_os`
rejected `shell_av_cli.py` for importing `pathlib`. That guard holds a
*workstream* boundary - no race, no duel, no Company OS - and its own comment
records the rule that "the list grows when Category 3 needs another stdlib
module and never when it needs another workstream". `pathlib` is stdlib, and
the A/V driver needs it to join the Phase 1 playback, Godot's frame directory,
the score WAV and the muxed preview into one tree of derived paths. The
allowlist was therefore grown by that one name, with the reason recorded beside
the four earlier growths. The guard was not weakened: it still rejects every
non-stdlib import, every other workstream, and everything in `audio/` outside
the three leaf modules.

High-signal regressions, chosen because Phase 3 adds two modules to
`satisfying/` and could only be seen by something that counts or walks
repository files:

| Set | Passed | Failed | Skipped |
| --- | ---: | ---: | ---: |
| Repo map, exploration report and telemetry, capsules, integration gate, runtime | 238 | 0 | 0 |
| Directory-walking guards outside Company OS | 221 | 5 | 8 |

All five failures are pre-existing and were confirmed by running them at the
Phase 1 base `42cdbb3`, where they fail identically:

- Four in `test_sloped_v251_world.py`, all from the missing gitignored artifact
  `output/sloped_race_v1/cameras_v221_5432.json`, which no Category 3 phase
  produces.
- `test_race2_v33_bookends.py::test_the_branch_adds_bookends_and_touches_nothing_else`,
  a stale branch-scope guard that already lists 734 lines of unrelated Company
  OS, intelligence and race files at the base commit.

No full-repository suite was run. Phase 3 touches one tracked file outside its
own new files - the allowlist above - so the expensive sweep belongs to the
production phase.

## Frozen-contract audit

Re-verified on the final tree rather than assumed:

- `shell_escape.py`, `shell_arena.py` and `shell_playback.py` are byte-identical
  to `42cdbb3`; the blob hashes match exactly.
- All seven Phase 1 playbacks still carry schema
  `category3-test2-shell-escape/1.0.0` and config digest `7da0cbc80d595826…`.
- The four candidate playbacks re-validate, their event times are monotonic,
  and their recomputed order digests equal the ones recorded in the sync
  audits.
- The candidate playbacks for 9589, 11929 and 7699 are unchanged since the
  base. `phase1_playback_seed3654.json` is an addition that arrived with the
  Phase 2A visual merge, not an edit.
- Per seed, `playback_digest`, `visual_playback_digest` and
  `score_playback_digest` are the same string: picture and score read one
  document.
- Neither `shell_av.py` nor `shell_av_cli.py` mentions `shell_escape`,
  `shell_arena` or `simulate(`. There is no second physics implementation.

## Phase 4 recommendation

Phase 4 should be final polish, production master and QC. It is not started
here and nothing in this phase anticipates it.

The specific things it inherits:

- Seed 9589 as the master, 11929 held as the backup cut.
- Previews, not an upload master: this phase renders at CRF 20/17 with static
  gain, no compressor and no limiter. Mastering decisions are Phase 4's.
- The one open listening question. The scores were measured, folded to mono and
  filtered to a phone band, and they pass every analytic check - but as in Test
  #1 Phase 5, nobody has actually listened to them yet.
- The full-repository suite, deliberately deferred above.
- The two stale guards named above, which will still fail in Phase 4 and are
  still not Category 3's to fix.

A/V PROOF PASSED — PRODUCTION SEED SELECTED

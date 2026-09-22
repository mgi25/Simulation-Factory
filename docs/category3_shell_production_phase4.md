# Category 3, Test #2 — MUSICAL SHELL ESCAPE, Phase 4: production master

## Decision

**PRODUCTION MASTER APPROVED.**

Seed 9589 is delivered. The master is
`output/category3_shell_production_v4/master/category3_test2_seed9589_delivery.mp4`
- 1080x1920, 60 fps, 23.761 s, 6.1 MB, H.264 CRF 17 with 192 kb/s AAC and
faststart. Nothing about the picture or the score was changed to get it there:
Phase 4 built the delivery path, ran the quality checks, and found nothing that
needed fixing.

The strongest single piece of evidence that this is the approved film and not a
new one is that the production audio rebuilt from the frozen playback carries
byte-identical digests to Phase 3's - score `69f30e04729bde82`, PCM
`8d654315842280ca`. The picture rebuilt to the same 1422 frames and the same
16.542 ms worst-case placement. Phase 4 delivered the thing Phase 3 approved.

The one thing this phase still cannot certify is in Part 1 below: the score has
been measured, not listened to.

## 1. Git

| | |
| --- | --- |
| starting branch | `category3-shell-av-v3` |
| starting SHA | `b39204a4acc648161821835da42a481a4a11a647` |
| this branch | `category3-shell-production-v4` |
| worktree | `../Simulation Factory-category3-shell-av-v3` |
| Godot | 4.7.2 stable, the portable build in the Phase 2A worktree |
| ffmpeg | 8.1.1 full build |

The branch is a continuation, not a rewrite: no history was rewritten, nothing
was force-pushed, nothing was merged to `main`, and no unrelated branch was
merged in.

## 2. The frozen contract, re-verified rather than assumed

| | |
| --- | --- |
| schema | `category3-test2-shell-escape/1.0.0` |
| simulation config digest | `7da0cbc80d595826…` |
| playback digest, seed 9589 | `0978e0644f27a7f8…` |
| event order digest | `3e67d1331c322f71…` |
| visual config digest | `77335e59def5e7f7` |
| audio config | `refined_hybrid`, fingerprint `eaedaafdb37866f1` |
| score fingerprint | `69f30e04729bde82…` |
| PCM digest | `8d654315842280ca…` |
| production fingerprint | `ae538ed8df0944d3` |
| production identity digest | `dc84bcd7f5351e75` |

`shell_escape.py`, `shell_arena.py` and `shell_playback.py` are untouched.
Phase 4 never calls the simulator: `prepare` copies the already-recorded Phase 1
playback, verifies it against `shell_playback.verify_document`, and hands that
one file to both Godot and the score builder. A test asserts this over the
parsed import graph of both new modules rather than over their text, because
both legitimately mention the *directory* the recorded playback is read from.

## 3. Part 2 — final visual polish

**No visual change was made, and none was needed.**

The presentation passed visual proof in Phase 3, and it was re-inspected here
rather than taken on trust. Frames were decoded and looked at directly at the
opening, the first near miss, the first mid-route break, the escape, and the
end:

- **Hook** - `CAN THE BALL ESCAPE?` is legible at full size from frame 0 and
  sits clear of the title block by 34.6 px.
- **Ball readability** - the ball is a bright warm disc against a dark field
  with a local glow; its minimum clearance from any Shorts control across the
  whole clip is 132.8 px and it is never hidden.
- **Shell contrast** - the six shells read as six, warm pink outermost through
  cyan innermost, so "how many are left" is answerable at a glance.
- **Opening visibility** - moving openings stay visible; the tightest opening
  clearance is 78.9 px.
- **Post-contact flash and near-miss ornament** - local, restrained and
  attached to the ball. At the first near miss the panel the ball *almost*
  passed lights amber immediately beside it; it does not wash the frame.
- **Progressive damage** - the teal→yellow→orange→red damage ramp plus the
  permanently missing panels make the middle visibly a different arena from the
  opening, which is the exact weakness Test #1 had.
- **Outer-shell tension and final escape** - at the escape the ball is on the
  outer boundary and by the final frame it is unmistakably outside every ring,
  with the hook replaced by `ESCAPED`.

Nothing was added. No camera movement, no scenery, no extra particles, no
counter, no screen shake, no new shell effect.

## 4. Part 3 — the final escape is the simulation's

The escape is the canonical event at 22.849 s and nothing stages it. There is
no unlock sequence, no scripted opening, no assisted crossing. The ball reaches
region 6 through an opening, the picture shows it crossing, and the score
resolves to D major on that same instant - 8.875 ms from the cue to the first
frame that can show it, 0.53 of one 60 fps frame.

The tail is short and deliberate. The rendered picture stops changing 24 frames
before the end (0.40 s) and the mux clones the final frame for 3 more (0.05 s)
to meet the score, so the film holds the `ESCAPED` card for about 0.45 s while
the last chord decays into exact digital silence. `freezedetect` finds that one
hold and nothing else; `blackdetect` finds nothing at all. The video does not
continue aimlessly after the escape.

## 5. Part 4 — the final audio master

**No mastering change was made.** The delivered audio is the Phase 3
refined-hybrid mix, rebuilt from the same document to the same PCM digest.

`master_gain_db` is 0.0 and there is no limiter and no compressor. That is a
decision, not an omission, and the production config refuses to be constructed
with a non-zero gain so that changing it has to be deliberate:

- The score already sits at **-4.54 dBTP**, which is 3.5 dB below the
  repository's established **-1.0 dBTP** delivery ceiling
  (`tile_phase6_cli.DELIVERY_TRUE_PEAK_DBTP`, reused here rather than
  reinvented).
- There are **zero clipped samples**.
- Adding gain to approach the ceiling would buy loudness nobody asked for and
  spend the 6.02 LU of range the six-register design exists to produce.

So the ceiling is enforced as a gate on the *decoded delivery file* - which is
how Test #1 enforces it - rather than as a target to normalise toward.

Measured on the decoded delivered MP4, not on the source WAV:

| | |
| --- | ---: |
| integrated loudness | -21.17 LUFS |
| loudness range | 6.02 LU (source: 6.027 LU) |
| sample peak | -4.544 dBFS |
| true peak | -4.54 dBTP |
| clipped samples | 0 |
| maximum polyphony | 4 |
| final 50 ms peak | -240.0 dBFS |
| mono fold loss | -0.10 dB, correlation 0.9654 |
| phone band, 300-2000 Hz | 95.35% of energy |

The AAC encode cost 0.007 LU of range and no peak headroom, so the hierarchy
that survives to the listener is the one that was approved. Nothing was
normalised per event and nothing was flattened.

## 6. Part 1 — the human-audition assumption, stated plainly

Every audio number above is a measurement. None of them is evidence that the
result is *pleasant*. The soundtrack was not redesigned on speculation and no
taste-driven change was made, exactly as the brief requires - but the honest
position is unchanged from Phase 3 and from Test #1's Phase 5: **nobody has
listened to this yet.** If a concrete audible defect is reported by a human,
that is a real finding and this master should be revisited. Absent one, the
approved system stands.

## 7. Part 5 — A/V synchronisation on the delivered master

Re-measured against the delivered 60 fps grid, not carried over from Phase 3:

| cue class | n | worst error | frames |
| --- | ---: | ---: | ---: |
| collision | 66 | 16.542 ms | 0.9925 |
| post contact | 10 | 16.188 ms | 0.9713 |
| near miss | 15 | 13.521 ms | 0.8112 |
| panel break | 17 | 16.542 ms | 0.9925 |
| shell exit | 6 | 11.396 ms | 0.6837 |
| final escape | 1 | 8.875 ms | 0.5325 |

Worst case overall **16.542 ms = 0.9925 of one rendered frame**, identical to
Phase 3's full-quality figure. Container and audio lengths differ by 4.3 ms,
about a quarter of a frame. Picture and score share one playback digest.

## 8. Part 6 — delivery frame rate

60 fps, as Phase 3's proof recommended and measured. The shells rotate
continuously and the ball never stops, so every frame is a different picture,
and the production config refuses any rate other than the one the visual layer
actually renders at. No downgrade to 30 was considered, because there is no
evidence it would be free and the 60 fps timing was already proven.

## 9. Part 7 — conservative Shorts safe area

Measured across the whole clip at the delivered rate, against all five expected
controls (`action_rail`, `title_block`, `progress_bar`, `nav_bar`, `top_bar`):

| | |
| --- | ---: |
| arena occupancy | 72.00% of frame width (777.6 px diameter) |
| outer-shell clearance | 75.6 px |
| hook clearance | 34.6 px |
| tightest opening clearance | 78.9 px |
| ball frames swept | 1385 |
| **ball hidden frames** | **0** |
| minimum ball clearance | 132.8 px |
| final escape clearance | 414.7 px |
| gate | **PASS** |

The sweep is taken at 60 fps rather than the config default of 30, because a
report at the wrong rate would be checking a picture the upload does not
contain. The late section is included: the escape itself has the largest
clearance of any moment in the film, 414.7 px.

## 10. Part 8 — phone and mono

The mono fold loses 0.10 dB at correlation 0.9654, so nothing important lives
only in the stereo difference. The phone-band filter keeps 95.35% of the
remaining energy in 300-2000 Hz and 96.41% above 300 Hz, with 0.0% below
120 Hz - so no cue depends on bass a phone speaker cannot produce. Collision
attacks and break blooms are the loudest events in the band a phone reproduces
best.

## 11. Part 9 — production encode

Two files, both encoded from the same 1422 PNG frames and the same 24-bit PCM.
**Neither is made from the other**, so neither carries the other's generation
loss, and the delivery file is not a transcode of any preview.

| | delivery | archive |
| --- | --- | --- |
| path | `master/category3_test2_seed9589_delivery.mp4` | `master/category3_test2_seed9589_archive.mkv` |
| video | H.264 CRF 17, preset slow | H.264 CRF 12, preset slow |
| audio | AAC 192 kb/s, 48 kHz stereo | `pcm_s24le` |
| colour | bt709 / iec61966-2-1 / bt709 | same |
| faststart | yes (`moov` before `mdat`, verified) | n/a |
| size | 6.1 MB (6 414 322 bytes) | 17.2 MB |

The transfer characteristic is recorded as `iec61966-2-1` rather than bt709 for
the reason Test #1 established: Godot writes sRGB PNGs and ffmpeg propagates
the input's transfer, so the stream tag comes back sRGB whatever is requested.
Recording bt709 would describe a file that does not exist.

## 12. Part 10 — QC on the encoded file

Run against the delivered MP4 itself, not the source frames.

- **Start** - frame 0 is fully composed: hook, six shells and ball, 98.3% of
  pixels non-black. There is no blank opening frame. The first collision is at
  0.209 s and the first outward shell exit at 1.739 s, so the premise pays off
  almost immediately.
- **Early** - openings read clearly, bounces and their sounds coincide inside
  one frame, and the first near-miss prediction arrives at 5.245 s.
- **Middle** - the arena visibly becomes a different arena: 10 near misses, 10
  breaks and 6 shell exits between 5.7 s and 14.9 s, with the register lifting
  as the ball moves outward.
- **Late** - fewer shells remain and it is obvious; the longest wait between
  first-time region advances is 8.786 s and it falls early, not here.
- **Escape** - unmistakable; the ball clears every ring and the hook becomes
  `ESCAPED`.
- **End** - `blackdetect` finds no black frames anywhere. `freezedetect` finds
  exactly one hold, the designed 0.45 s `ESCAPED` card, and the audio ends at
  -240 dBFS: clean decay, no dead tail, no accidental frozen sequence.

## 13. Part 11 — reproducibility

`docs/validation/category3_shell_production_v4/production_identity.json`
records the source branch and SHA, the seed, the simulation schema and config
digest, the playback digest, the visual config digest, the audio config and
fingerprint, the hook, the frame, the rate and every encoder parameter, layered
so that a mismatch says *which* layer moved.

Hashes, recorded in `delivery_verification.json`:

| artefact | sha256 |
| --- | --- |
| canonical playback | `99d9989a65427a27…` |
| master WAV (24-bit PCM) | `10849b1eb5f1d548…` |
| delivery MP4 | `15255300bb5c7f06…` |
| archive MKV | `1895cd9e90a52de6…` |

The playback and the PCM are exactly reproducible and their digests are what a
rebuild must match. The encoded files are deliberately *not* claimed to be
bit-reproducible, because x264 differs between builds; what is checked instead
is the decoded result - frame count, resolution, rate, duration, peak, clipping
and synchronisation - which is the same claim Test #1 makes.

## 14. Parts 12 and 13 — tests and regression

Phase 4 adds `tests/test_shell_production.py`: 28 focused contracts covering
the locked seed, the frozen simulation digest, visual and audio config
determinism, identity layering and determinism, delivery resolution, rate,
duration and codec, A/V sync per cue class, clipping and headroom, preserved
dynamic range, ending silence, safe-area compliance and the production identity
digest. The tests that need the delivered MP4 skip in a clone, because
`output/` is gitignored; the tests that decide *what would be delivered* need
nothing but the repository and never skip.

Every existing Category 3 test is preserved and unchanged.

### Category 3

| set | passed | failed | skipped |
| --- | ---: | ---: | ---: |
| Category 3, all eleven files | 451 | 0 | 1 |

The one skip is the pre-existing, environmental one: `test_tile_escape_phase3`
needs evidence under the gitignored `output/`. It skipped identically before
Phase 4.

### The full repository suite

Phase 3 deferred this to the production phase. It was run here, on the final
tree:

| | passed | failed | skipped | time |
| --- | ---: | ---: | ---: | ---: |
| whole repository | 6176 | 18 | 441 | 25:17 |

**All 18 failures are pre-existing, and none was introduced by Phase 4.** That
was checked rather than assumed: a detached worktree was created at the Phase 4
baseline `b39204a`, the eighteen node IDs were run there, and the same eighteen
failed - same tests, same count, same reasons. The worktree was then removed.

| failing node | pre-existing cause |
| --- | --- |
| `test_neon_proof::test_a_missing_godot_is_reported_rather_than_raised` | environment: Godot is not on `PATH` |
| `test_race2_v30_stage`, `test_race2_v301_stage` `::test_this_branch_changes_no_physics_camera_or_course_module` | stale branch-scope guard |
| `test_race2_v311_track::test_the_branch_changes_only_render_and_measurement`, `::test_no_locked_package_moved[race2/]` | stale branch-scope guard |
| `test_race2_v321_geometry::test_the_branch_changes_only_render_and_measurement` | stale branch-scope guard |
| `test_race2_v32_final::test_the_branch_adds_only_presentation`, `::test_no_locked_file_moved[×5]` | stale branch-scope guard |
| `test_race2_v33_bookends::test_the_branch_adds_bookends_and_touches_nothing_else` | stale branch-scope guard |
| `test_sloped_v251_world` [×4], `test_sloped_v252_world::test_the_geometric_parallax_field_is_identical_to_v251s` | missing gitignored `output/sloped_race_v1/cameras_v221_5432.json` |

The branch-scope guards belong to finished race workstreams and compare the
working tree against their own recorded file lists; they have been failing on
every branch since those workstreams closed. No unrelated race or Company OS
guard was weakened to make anything green, and no gitignored artefact was
manufactured to satisfy the sloped tests.


## 15. Phase 4 did not touch anything else

The diff is confined to Category 3 Test #2: two new modules in `satisfying/`,
one new test file, this document and its evidence directory. Nothing under
Company OS, Category 1, Ball Race or Test Video 5 was modified, and no
unrelated branch was merged.

## 16. What is delivered

Upload this file:

```
output/category3_shell_production_v4/master/category3_test2_seed9589_delivery.mp4
```

Seed 11929 remains the recorded backup. It is reproducible on demand -
`shell_production_cli prepare|render|audit|master|verify --seed 11929` builds it
with every other dial identical - and it was deliberately not rendered, because
the primary passed QC and a second master nobody needs is a second master
somebody can upload by mistake.

PRODUCTION MASTER APPROVED

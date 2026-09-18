# Race #2 — SWITCHYARD V33.1, the uploaded Test #4 master

The accepted, uploaded cut of Test #4. This file exists so the exact shipped
state stays identifiable after branches move. It records *what* shipped; the
reasoning and the measurements live in the documents linked at the bottom and
are not repeated here.

**This release is frozen.** Picture, audio, physics, seed, camera, track,
environment, bookends and runtime are final. Any future change is a new
release, not an edit to this one.

## The commit

| | |
|---|---|
| release | Race #2 — SWITCHYARD, V33.1, **Test #4** |
| git SHA | `5414a76d278aa792489f21cbacc8c2126a02d74e` |
| tag | `race2-v33.1-test4-uploaded` |
| branch | `v331-runout-fix` (from `v33-mobile-race-bookends` at `749d355`) |
| commit date | 2026-09-18 |
| date frozen | 2026-09-18 |
| upload status | uploaded to YouTube as Test #4, accepted |

The tag points at the uploaded *code*. Any later commit on this branch —
including this manifest — is after the fact, and the tag does not move.

Rebuild command: `python tools/race2_v331_runout.py all --hook=C --text=your`

## The film

| | |
|---|---|
| course | SWITCHYARD, hero seed **8** |
| winner | **m7, PINK** (`#F0559B`), crossing at 15.8167 s, by 0.0667 s |
| finish order | **`[7, 2, 1, 5, 3, 0, 6, 4]`** |
| resolution | 1080 x 1920 |
| frame rate | 60 fps |
| frames | 1150, frame 0 to 1149, contiguous, 0 omissions |
| runtime | **19.1667 s** |
| audio | AAC-LC, 48 kHz stereo |
| file size | 16,990,573 bytes |

Finish times, in order: 15.816667, 15.883333, 16.133333, 16.583333, 17.200000,
17.716667, 17.816667, 18.750000. All eight racers finish; none is retired.

## The layers

| layer | version |
|---|---|
| physics / course | SWITCHYARD (V28) |
| camera | V31 RB readability, V28.1 chase |
| environment | `contained_bay_v301` (V30.1) |
| track | V31.1 Variant B, V32.1 geometry correction |
| presentation / payoff | V32, card `PINK WINS / 5TH -> 1ST` |
| audio | V32.2, **Mix B**, stream-copied |
| opening / hook | V33, composition **C**, `PICK YOUR COLOR` |
| start stand | V33 bookends |
| finish bookend | V33 bookends, **run-out corrected in V33.1** |

## What V33.1 changed, and only that

One geometry defect in `race2.parts.RunOut`: the deck's frame was built from a
compass heading read with the engine's forward formula, which turned it exactly
90° from the direction of travel at every heading. Test #4's winner missed the
deck, left the machine at 15.9292 s and hung frozen in mid-air for the last 192
frames.

V33.1 lays the run-out along the track and sizes it to the shot. Everything
before the finish line is bit-identical to V33: the start, the hook, the gate,
the middle, the camera track, the event timing and the audio stream all match
the accepted V33 build. Full account in `docs/race2_v331_runout_fix.md`.

## Identity of the delivered file

`race2_switchyard_v331_your.mp4`

    file SHA-256            b03ff50a2d4a45104d02616c2a2684262737ee93dcd6f02c389dc2b2c6843c89
    video stream MD5        85543d6a0e968578fbbb077f8eab66f4
    audio stream MD5        9404b38016c75c4c16869f5f2c6c87ae
    AAC elementary SHA-256  9db89f3a919446215cc9e0afd5122b1acc8d4f3351a5f5c7c2afb9e870f832dd

The AAC elementary digest is shared with the V32.2 shipped master: the mux is
`-c:a copy`, so no encoder has touched the sound since Test #3. It is checked on
the elementary stream rather than the container, because two MP4s built at
different times differ in their headers whatever the audio is doing.

The delivered files are kept in `exports/`, which is deliberately outside git
(see `.gitignore`). **The repository does not contain the film.** The uploaded
master is held in two places:

* `exports/race2_v331_runout/race2_switchyard_v331_your.mp4` — the build
  location, inside the `wt-v331-runout` worktree.
* `exports/race2_v331_test4/race2_switchyard_v331_your.mp4` — in the primary
  working tree, which survives any worktree being removed. `CHECKSUMS.txt`
  beside it repeats the digests above.

## Reproducing it

The race is independent of the render:

```python
from race2.courses import switchyard
from race2.race import run_race
outcome, _ = run_race(switchyard(), seed=8)
```

From a clean checkout of this commit that reproduces the shipped result exactly
— winner m7 at 15.816667, the finish order above, 0 escaped, 0 stuck, all eight
`finished`.

## Where the evidence is

| pass | document | validation |
|---|---|---|
| V28–V32.2 lineage | `docs/releases/race2_v322_uploaded.md` | |
| V33 mobile bookends | `docs/race2_v33_mobile_bookends.md` | `docs/validation/race2/v33_bookends/` |
| **V33.1 run-out fix** | `docs/race2_v331_runout_fix.md` | `docs/validation/race2/v331_runout/` |

## Known, accepted at ship time

Recorded so they are not rediscovered as surprises. None were considered
blocking, and none are fixed here.

1. **No one has watched the cut end to end at phone size.** The finish is
   reviewed at 270x480 (V33.1 §9); the rest is measured, not viewed.
2. **The film is proven on seed 8 only**, as every Race #2 release has been.
3. **Three branch-scope guards from earlier briefs fail on this commit**
   (`test_race2_v32_final.py::test_no_locked_file_moved` for `race2/parts.py`,
   `race2/kit.py` and `race2/race.py`, plus V33's
   `test_the_branch_adds_bookends_and_touches_nothing_else`). They assert that
   files V33.1's brief *required* changing were not changed. They are stale
   guards, not defects, and must not be "fixed" by editing accepted production
   code (V33.1 §10).

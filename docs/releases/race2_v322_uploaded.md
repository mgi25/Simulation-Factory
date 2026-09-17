# Race #2 — SWITCHYARD V32.2, the uploaded YouTube master

The accepted, uploaded cut of Race #2. This file exists so the exact shipped
state stays identifiable after branches move. It records *what* shipped; the
reasoning and the measurements live in the V28–V32.2 documents linked at the
bottom, and are not repeated here.

**This release is frozen.** Picture, audio, physics, seed, camera, track,
environment and runtime are final. Any future change is a new release, not an
edit to this one.

## The commit

| | |
|---|---|
| release | Race #2 — SWITCHYARD, V32.2 |
| git SHA | `9d48221a5004c73dfb757d7bde1d268e072ab052` |
| tag | `race2-v32.2-uploaded` |
| branch | `v322-asmr-audio-final` |
| commit date | 2026-09-17 |
| date frozen | 2026-09-17 |
| upload status | uploaded to YouTube, accepted |

Rebuild command: `python tools/race2_v322_audio.py all --winner=B`

## The film

| | |
|---|---|
| course | SWITCHYARD, hero seed **8** |
| winner | **m7, PINK** (`#F0559B`), crossing at 15.8167 s, by 0.0667 s |
| resolution | 1080 x 1920 |
| frame rate | 60 fps |
| frames | 1150, frame 0 to 1149, contiguous, 0 omissions |
| runtime | **19.1667 s** |
| video | H.264 High, CRF 17, preset slow, yuv420p, `+faststart` |
| audio | AAC-LC 256 kbit/s, 48 kHz stereo |
| file size | 14,683,041 bytes |

## The layers

| layer | version |
|---|---|
| physics / course | SWITCHYARD (V28) |
| camera | V31 RB readability, V28.1 chase |
| environment | `contained_bay_v301` (V30.1) |
| track | V31.1 Variant B, V32.1 geometry correction |
| presentation / payoff | V32 |
| audio | V32.2, **Mix B** |

## Audio

| | |
|---|---|
| integrated loudness | **−14.58 LUFS** |
| true peak | **−1.27 dBTP** |
| loudness range | 3.33 LU |
| mono fold-down | −14.60 LUFS (−0.02 dB) |

Music is original and race-derived; nothing third-party is in the chain. See
`docs/validation/race2/v322_audio/music_license.txt`.

## Identity of the delivered file

`race2_switchyard_final_audio.mp4`, byte-identical to Mix B
(`race2_switchyard_b.mp4`).

    file MD5                a18d356ed38f6946f4823c997878585a
    video stream MD5        49515b72fc1799ca611ce8d55490736e
    decoded frames SHA-256  d7c3c48d1292dfa1a16766f3f90e53540119d5c44d661ce7e0c64e45331e2db0

The V32.2 mux is `ffmpeg -c:v copy`, so the picture is the V32.1 film's bytes
unmodified — the video stream MD5 above is shared by the V32.1 source and by
all three V32.2 mixes. Only the audio differs between them.

The delivered files are kept in `exports/`, which is deliberately outside git
(see `.gitignore`). **The repository does not contain the film.**

## Reproducing it

The picture and the mix rebuild from this commit with the command above.
The race itself is independent of the render:

```python
from race2.courses import switchyard
from race2.race import run_race
outcome, _ = run_race(switchyard(), seed=8)
```

reproduces the shipped finish order exactly:

    1. m7  15.816667      5. m3  17.200000
    2. m2  15.883333      6. m0  17.716667
    3. m1  16.133333      7. m6  17.816667
    4. m5  16.583333      8. m4  18.750000

## Where the evidence is

| pass | document | validation |
|---|---|---|
| V28 drama camera | `docs/race2_drama_camera.md` | `docs/validation/race2/` |
| V28.1 cinematography | `docs/race2_v281_racing_cinematography.md` | |
| V29 contained | `docs/race2_v29_switchyard_contained.md` | `.../v29_contained/` |
| V30 stage | `docs/race2_v30_contained_stage.md` | `.../v30_stage/` |
| V30.1 stage art | `docs/race2_v301_premium_stage.md` | `.../v301_stage/` |
| V31 readability | `docs/race2_v31_readability.md` | |
| V31.1 track | `docs/race2_v311_track_visibility.md` | `.../v311_track/` |
| V32 production | `docs/race2_v32_production.md` | `.../v32_final/` |
| V32.1 geometry | `docs/race2_v321_track_geometry.md` | `.../v321_track_geometry/` |
| **V32.2 audio** | `docs/race2_v322_audio.md` | `.../v322_audio/` |

## Known, accepted at ship time

Recorded so they are not rediscovered as surprises. None were considered
blocking, and none are fixed here.

1. **No one has listened to the mix end to end.** Every audio claim in V32.2 is
   a measurement, not a perceptual judgement (V32.2 §16.1).
2. **The `6TH -> 1ST` card overstates the comeback.** m7 is sixth for 13 frames
   (0.217 s). The duration-weighted low is fifth. V32 §3 documents this in full.
3. **The mix is proven on seed 8 only.** Its thresholds were chosen against this
   replay's residual distribution (V32.2 §16.7).

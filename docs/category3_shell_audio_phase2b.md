# Category 3, Test #2 — Musical Shell Escape, audio Phase 2B

**Decision: AUDIO PROOF PASSED — recommend the refined hybrid for later A/V integration.**

This phase builds the differentiator promised by Test #2: the collision stream
is the music. There is no background track, sustained bed, sampled material,
recognisable melody, or artificial increase in event rate. Every musical
change comes from canonical physical state.

The work branches from `category3-shell-escape-v1` at
`42cdbb34588f052be45377d7c20c89d8100fcf99`. It accepts only event schema
`category3-test2-shell-escape/1.0.0` and config digest
`7da0cbc80d595826…`. No simulation, geometry, seed, damage, near-miss,
evaluator, or playback-schema code changed.

## Architecture

The separation is explicit:

```text
frozen canonical playback JSON
        ↓
satisfying.shell_score
deterministic musical schedule JSON
        ↓
satisfying.shell_audio
deterministic oscillator synthesis → stereo PCM WAV + measurements
```

`shell_score` imports neither simulation nor synthesis. `shell_audio` receives
only an immutable schedule and cannot reach physics. The same playback digest
and audio-config fingerprint produce the same schedule fingerprint and PCM
digest. Event instants are rounded once to 48 kHz and remain within half a
sample of canonical time.

## Physical-to-musical mapping

| Canonical fact | Musical meaning |
| --- | --- |
| `shell_id` | Six increasingly bright, related registers: A3, C#4, E4, A4, C#5, E5 bases |
| collision `position.y / radius` | One of five ordered scale degrees inside that register |
| collision `position.x / radius` | Conservative constant-power pan, maximum ±0.30 |
| `impact_speed` + `incidence` | Note gain, upper-partial strength, and transient energy |
| `feature=post` | Shorter, sharper pitched fourth-partial transient |
| canonical near miss + `signed_lead` | Brief 9:8 upward or 8:9 downward unresolved neighbour |
| panel damage fraction | Gradually added, slightly stretched upper partial and longer resonance |
| `panel_break` | Major-triad harmonic bloom, stronger than every normal collision |
| first `shell_exit` into each new outer region | Compact fifth lift; break exits add a subtle third partial |
| `escape` | D-major resolution with a 660 ms decay and at least 150 ms exact silence |

The pitch vocabulary is D-major pentatonic expressed from A — A, B, D, E,
F# — rather than Test #1's A-minor mapping. It contains no semitone or tritone
inside the palette, stays consonant in arbitrary physics-generated order, and
places all fundamentals between 220 and 1109 Hz. Generated upper partials
carry the lower notes on small speakers.

Every collision remains audible. The brief near-miss ornament is inside its
collision voice instead of creating a second fake impact. Damage is a spectral
state, not a crack sample. Regressions do not replay progression lifts: only
the first canonical crossing into each of the six new outer regions does.

## Bounded variant comparison

Seeds 11929 and 9589 compared exactly three coherent designs.

| Variant | Character | Polyphony | Overlap, two seeds | LUFS, two seeds | Decision |
| --- | --- | ---: | ---: | ---: | --- |
| `clean_percussive` | 115 ms notes, strongest attack, least ring | 3 | 3.27 / 3.30 s | -22.13 / -22.22 | Clear but too pointillist for the central musical claim |
| `resonant_musical` | 245 ms notes, richest ring and damage colour | 4 | 7.68 / 7.35 s | -20.94 / -21.26 | Musical but carries unnecessary overlap at this density |
| `refined_hybrid` | 165 ms notes, clean attack plus restrained resonance | 4 | 4.96 / 4.99 s | -20.98 / -21.17 | **Selected** |

The hybrid retains the clean design's separation while allowing pitch,
damage, break chords, and outward progression to connect collisions into one
piece. It needs no masking bed.

## Eight-candidate evaluation

These are eight of the existing sixteen Phase 1 shortlisted seeds. No new
search was run.

| Seed | Physics duration | Hits / near / breaks | Progress opening/break | Final | LUFS | dBTP | Mono loss |
| ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| 19607 | 18.68 s | 52 / 9 / 8 | 5 / 1 | break | -22.00 | -4.48 | -0.08 dB |
| 1511 | 18.71 s | 58 / 11 / 9 | 3 / 3 | break | -21.67 | -5.04 | -0.07 dB |
| 17534 | 21.13 s | 71 / 14 / 13 | 4 / 2 | break | -21.45 | -5.51 | -0.09 dB |
| 3654 | 21.21 s | 62 / 13 / 9 | 5 / 1 | opening | -22.26 | -4.80 | -0.09 dB |
| 11929 | 22.11 s | 76 / 12 / 14 | 2 / 4 | break | -20.98 | -5.26 | -0.07 dB |
| 9589 | 22.94 s | 66 / 15 / 17 | 3 / 3 | opening | -21.17 | -4.53 | -0.10 dB |
| 16513 | 23.80 s | 58 / 14 / 14 | 4 / 2 | opening | -21.56 | -5.09 | -0.09 dB |
| 8952 | 23.83 s | 66 / 13 / 11 | 5 / 1 | break | -21.93 | -4.68 | -0.11 dB |

Across the hybrid set:

- collision density is 2.46–3.47 Hz; audio adds no events to inflate it;
- maximum scheduled polyphony is 4;
- time with at least two scheduled voices is 2.82–4.99 seconds;
- integrated loudness is -22.26 to -20.98 LUFS and RMS is -25.17 to -23.99 dBFS;
- sample/true peak is -5.51 to -4.48 dBFS/dBTP, with zero clipped samples and no limiter;
- mono fold loss is 0.07–0.11 dB, with correlation 0.958–0.975;
- a phone-like high-pass retains 93.18% or more of its energy in 300–2000 Hz;
- timing error is at most 0.500 sample (10.42 μs);
- every preview ends in exact digital silence.

The useful handoff set is deliberately plural: seed 11929 tests dense,
break-led outward progress and a break finale; seed 9589 tests the highest
near-miss/break count with balanced progression and an opening finale; seed
3654 is the lighter opening-led counterexample. The visual integration pass
should compare those three before choosing a production seed.

## Outputs

Local reproducible output is under `output/category3_shell_audio_v2b/`:

- `playback/`: eight verified canonical documents;
- `scores/`: twelve deterministic score documents;
- `wav/`: twelve 24-bit, 48 kHz stereo WAV previews (74.8 MB);
- `measurements/`: twelve JSON reports;
- `candidate_comparison.json`: the seed and variant comparison.

The compact scores, measurements, and comparison are also committed under
`docs/validation/category3_shell_audio_v2b/`. WAVs remain in the repository's
ignored `output/` workspace and reproduce with:

```powershell
python -m satisfying.shell_audio_cli build
```

## Validation

`tests/test_shell_audio.py` adds focused coverage for the frozen schema/config,
layer isolation, deterministic scoring and synthesis, register and position
mapping, impact dynamics, near-miss direction, damage progression, break
hierarchy, genuine outward transitions, escape resolution, headroom, true
peak, clipping, phone-band survival, mono compatibility, document
non-mutation, exact timing, and distinct variants.

Validation result:

```text
pytest -q tests/test_shell_escape.py tests/test_shell_audio.py \
  tests/test_tile_escape.py tests/test_tile_escape_phase2.py \
  tests/test_tile_escape_phase3.py tests/test_tile_escape_phase4.py \
  tests/test_tile_escape_phase5.py tests/test_tile_escape_phase6.py

397 passed, 1 skipped
```

Integration recommendation: carry `refined_hybrid` and seeds 11929, 9589,
and 3654 into the later A/V comparison. Keep canonical times as the source of
truth; if a visual pass adds holds or retiming, add an explicit render-time
mapping above this score rather than changing physics events. Do not begin A/V
integration or select a final production seed in this branch.

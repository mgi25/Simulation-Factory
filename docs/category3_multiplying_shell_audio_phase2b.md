# Category 3, Test #2 redesign — multi-ball musical audio, Phase 2B

**Decision: MULTI-BALL AUDIO PROOF PASSED — the `open_quartal` system, across
seven proof candidates.**

The redesigned mechanic turns one ball into as many as fifteen, so the piece
has to grow from a single sparse voice into controlled polyphony without ever
becoming a wash. It does, and the growth is the balls' doing: over the seven
candidates the late third carries 1.38 to 1.88 more simultaneous voices than
the early third, six to thirteen more distinct balls, and *more* of its energy
standing on palette pitches than the sparse opening did — 92.7% to 94.1%
against a white-noise control of 17.5% on the same measurement.

There is no background track, no sampled material, no recognisable melody and
no loop. Nothing in the audio layer can reach the physics, and nothing in the
audio layer moves an event in time.

The work branches from `category3-multiplying-shell-v1` at
`78739b266d9c8872c350bf239ae3c60e02c7fe65`. It accepts only event schema
`category3-test2-multiplying-shell/2.0.0` and config digest
`dcf3c2bf05879e08…`. No simulation, schema, evaluator, playback or seed code
changed; the branch is four new files.

## Architecture

```text
frozen canonical V2 playback JSON
        ↓
satisfying.multishell_score      — deterministic musical schedule JSON
        ↓
satisfying.multishell_audio      — oscillator synthesis → stereo PCM + measurements
        ↓
satisfying.multishell_audio_cli  — candidates, variants, build, verify, timeline
```

`multishell_score` imports six standard-library modules and nothing else —
asserted by walking its import graph, not by the docstring. `multishell_audio`
receives an immutable schedule and reaches only `audio/wav_io`,
`audio/loudness` and numpy. A full render leaves the canonical document
byte-identical.

## The mistake that decided the harmonic system

The obvious way to give five shells five registers is to transpose one
collection by a fifth per shell. It does not work, and it fails silently.
A major pentatonic on A is `{A B C# E F#}`; the same collection on E is
`{E F# G# B C#}`; their union contains both A and G#, a semitone apart. Two
balls in adjacent shells could then sound a minor second, and no amount of
per-event policing would get it back — the pitch set itself would be wrong.

So shells are not transposed. The collection is built once into a **ladder** —
`root · 2^((scale[i mod 5] + 12·(i div 5))/12)`, fifteen positions spanning
220–1480 Hz — and a shell is a *window of that ladder*, not a transposition of
the scale. The union of everything any shell can play is then the collection
itself, and a test proves it for every pair of positions in every palette:

| system | collection | shell windows | union, as pitch classes |
| --- | --- | --- | --- |
| `bright_pentatonic` | 0 2 4 7 9 (major pentatonic) | ladder 0, 2, 4, 6, 8 | exactly the collection |
| `open_quartal` | 0 2 5 7 10 (suspended pentatonic) | ladder 0, 2, 4, 6, 8 | exactly the collection |
| `deep_minor` | 0 3 5 7 10 (minor pentatonic) | ladder 0, 2, 4, 6, 8 | exactly the collection |

Every pair inside any of the three is 2, 3, 4, 5, 7, 8, 9 or 10 semitones
apart modulo an octave — never 1, 6 or 11. Consonance is therefore structural,
not enforced: across all seven candidates and all three systems, **zero** of
the 46 to 101 simultaneous pairs per run form a semitone, a tritone or a major
seventh. The measurement exists so that a future palette that breaks the
guarantee fails a test instead of a listening session three phases later.

## Physical → musical mapping

| Canonical fact | Musical decision |
| --- | --- |
| `collision.position.y / shell.radius` | one of five equal-width degrees inside the shell's window |
| `collision.position.x / shell.radius` | amplitude-only pan, maximum ±0.30 |
| `shell_id` | which ladder window, plus a sub-octave that grows outward and a longer ring |
| `impact_speed` | note gain, transient energy and note length |
| `incidence` | articulation: head-on is short and struck, glancing is long and brushed |
| `feature == "post"` | a sharper, higher, faster-decaying transient |
| ball lineage | overtone tint, attack edge, pan bias, register preference, ±7 cents |
| panel damage entering the contact | longer ring and a progressively stretched second partial |
| `damage_state` transition | a 55 ms fifth above, inside that contact's own voice |
| `near_miss` + `signed_lead` | a neighbour degree that never returns, inside the voice |
| `panel_break` | a four-note palette chord with an octave-below floor, 470 ms |
| `ball_spawn` | the parent's note, then the child's own note a mirrored fifth away, on the other side of the stereo field |
| the run's first arrival in a region | an ascending arpeggio of the palette chord |
| a repeat outward crossing | a quiet passage marker, below the quietest bounce |
| `escape` | the collection's tonic chord over two octaves, with the bed cleared around it |

Two mapping choices are corrections of the single-ball version rather than
copies of it. Degrees are **equal-width bands** of the contact height, not a
rounded position: rounding gives the two outer degrees half the width of the
three inner ones, which with fifteen balls is a measurable pull towards the
middle of every register. And the panel's timbre reports its state **entering**
the contact, `(cumulative − contribution) / threshold`, not the state it is
left in — a cracked panel rings differently when it is struck, which is a
different claim from the hit having cracked it.

## Lineage is a walk, not a draw

A ball's voice is its parent's voice plus one bounded deterministic step on
each axis; the founder sits at the neutral centre of every axis, so the family
has a middle rather than an arbitrary corner. Siblings are measurably nearer
each other than second-generation cousins are, and the whole thing is a
function of `(parent_id, ball_id)` alone — reversing the ball list produces
identical voices. Register walks in whole ladder steps rather than in cents,
because two voices a scale degree apart are two voices and two voices six
cents apart are one blurred one.

## Density: nothing is dropped

Phase 1 measured about 5.9 sustained collisions a second with peaks near 14.
Every one of them sounds. The answer to density is shorter and quieter, never
silent:

- a backward 600 ms window counts the recent contacts and scales the voice
  length by `1/(1 + 0.125·(n−1))`, floored at 0.45, and the level by half that
  — backward-looking on purpose, because a symmetric window would let a note
  that has not happened yet shorten one that already has;
- a pitch that repeats inside 140 ms moves one ladder step and drops 1.9 dB,
  which is what stops a ball trapped between two panels machine-gunning one
  note. Longest same-pitch run over the whole proof set: **3**;
- inside a 30 ms cluster, a unison is pushed up a step and two adjacent
  degrees in the bottom octave are separated by an octave. Register
  management, not timestamp quantisation: nothing is moved in time, and the
  distinct inter-collision gaps are 95%+ distinct, which is what a piece with
  no grid looks like.

The check that matters is that no bounce is buried. Across all seven
candidates, **zero** collisions raise the mix by less than 3 dB across their
own onset; the median rise is 10.7–12.9 dB and the worst single contact in the
whole set is +4.0 dB.

## Hierarchy: two buses and a duck

Collisions and passage markers sum into a **bed**; spawns, breaks, lifts and
the escape sum into a **marked bus** that nothing can duck. The bed is
multiplied by a duck envelope built from the marked events — 2.0 dB for a
spawn, 2.6 for a lift, 3.0 for a break, 9.0 for the escape, each with an 80 ms
lead-in, a 90 ms hold and a 220 ms release. The lead is the only forward-looking
thing in the layer and it is a gain ramp on a bus, never an event moving; a
test bounds it.

Measured on seed 12818, medians of each event's own contribution:

| event | median peak | count |
| --- | ---: | ---: |
| repeat crossing | −22.66 dBFS | 30 |
| ordinary bounce | −16.65 | 129 |
| strong / frontier bounce | −15.27 | 60 |
| spawn under a lift | −14.33 | 5 |
| spawn | −11.23 | 9 |
| progression lift | −9.43 | 5 |
| panel break | −8.19 | 19 |
| **escape** | **−5.43** | 1 |

Ducking stays under 0.92 onsets a second and touches 24–35% of the timeline at
2–3 dB, which is a wash rather than a pump. The marked bus sits 0.6–1.6 dB
*under* the bed in RMS: the important events are louder per event and far
rarer, which is what a hierarchy should look like.

## The structural fact this phase found

**Every progression lift lands on the same sample as a spawn, by construction.**
A ball's first crossing of a shell is what makes it reproduce; when nobody has
been out there before, that same crossing is the run's arrival in a new region.
So all five lifts in every candidate share an instant with a spawn, and five of
the seven to fourteen spawns per run are lift-carrying.

It has two consequences and both are handled rather than tolerated.

In the mix, the pair would sum into the loudest thing before the escape, so a
lift-carrying spawn is held 3.1 dB down and the lift carries the moment.

In the measurement, it made the first hierarchy reading come out backwards. The
per-kind table was originally taken over a 55 ms window of the bus, and on a
run with twelve spawns and five lifts the *median* spawn window is a lift
window — so a spawn appeared louder than the panel break it is supposed to sit
under, on three of the six variant renders. The fix is two tables: the
hierarchy is judged on each event's own contribution, and the in-mix window
reading is reported beside it with a count of how many windows had to be
discarded because something more important was sounding across them.

The lift that fires 67–113 ms before the escape is the same fact once more —
the last frontier advance is the escaping ball leaving the outermost shell —
and it is left alone, because an ascending arpeggio immediately before the
resolution is the upbeat and not a competitor.

## Variant comparison

Three systems, two reference seeds, decided before the proof set was built.
12818 is the densest run in the set and 7183 is the mid-density break/descendant
counterexample.

| system | voice median | overlap ratio | mean polyphony | late−early polyphony | palette share, late | median onset rise | verdict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `bright_pentatonic` | 0.145 / 0.148 s | 1.96 / 1.69 | 2.44 / 2.30 | +1.11 / +0.93 | 91.1 / 91.4% | 12.1 / 11.7 dB | the middle case on every axis |
| `deep_minor` | 0.108 / 0.112 s | 1.61 / 1.39 | 2.15 / 2.00 | +0.86 / +0.68 | 89.5 / 88.9% | 13.4 / 13.5 dB | cleanest separation, weakest crescendo |
| `open_quartal` | 0.202 / 0.207 s | 2.48 / 2.14 | 2.90 / 2.70 | **+1.55 / +1.38** | **93.2 / 94.1%** | 11.4 / 11.4 dB | **selected** |

All three pass the hierarchy, the consonance constraint and the no-clipping
check, and all three bury nothing — no collision under a 3 dB onset rise in any
of the six renders.

`open_quartal` is selected because it wins on the axis the redesign exists to
produce. It grows from the sparse opening to the crowded close by half a voice
more than the next system, and it does so while *raising* the share of energy
standing on palette pitches rather than lowering it. The reason is the
collection: two stacked fourths (0–5–10) interfere less than a stacked third
does, so more voices fit before they start to beat. It costs 1.5–2.0 dB of
median onset rise against `deep_minor`, which the masking measurement says is
affordable — the worst contact in either reference render still lifts the mix
by 4.0 dB.

`deep_minor`'s 108 ms voices are the most legible per event and the least
musical in aggregate; it reads as a percussion part rather than as a piece
growing. That is the correct choice for a different brief.

## The seven proof candidates

Derived from Phase 1's eighteen shortlisted seeds by the brief's rules alone.
No new seed search was run. The visual branch had not pushed a manifest when
this was written, so the rules were reproduced here and the reason every
rejected seed lost is recorded in `proof_candidates.json` for the later
intersection.

Rules: duration 20–24 s; first split ≤2.5 s preferred and >3.0 s rejected;
population 8–15; escape required; ordered by duration; both routes and both
founder and descendant finals required in the result.

| seed | duration | first split | population | route | final | collisions | spawns | breaks |
| ---: | ---: | ---: | ---: | --- | --- | ---: | ---: | ---: |
| 949 | 20.16 s | 2.31 s | 8 | opening | descendant (g3) | 119 | 7 | 13 |
| 12004 | 21.71 s | 2.40 s | 15 | opening | descendant (g2) | 134 | 14 | 9 |
| 547 | 21.73 s | 2.25 s | 11 | opening | founder | 114 | 10 | 14 |
| 11319 | 21.80 s | 1.47 s | 14 | break | founder | 149 | 13 | 18 |
| 3622 | 22.82 s | 0.45 s | 11 | break | descendant (g3) | 120 | 10 | 13 |
| 12818 | 22.84 s | 0.50 s | 15 | opening | founder | 189 | 14 | 19 |
| 7183 | 23.21 s | 0.62 s | 13 | break | descendant (g3) | 155 | 12 | 16 |

Eleven of the eighteen were rejected: six for a duration outside the band
(13009, 16458, 16067, 368, 17758, 3909) and five for a first split over 3 s
alone (9091, 19998, 10038, 17693, 6625); three of those six failed both rules.
Every survivor passed on every rule, and none needed the 2.5–3.0 s band
opened.

## Measured, across the seven

| reading | range |
| --- | --- |
| integrated loudness | −19.98 to −18.83 LUFS |
| loudness range | 4.65 to 8.55 LU |
| true peak | −3.31 to −2.50 dBTP, **0 clipped samples**, no limiter |
| collision density | 5.27 to 8.31 Hz; total event density 7.70 to 11.34 Hz |
| maximum polyphony | 8 to 10 voices; median 2 to 3; mean 2.45 to 2.90 |
| collision voice length | median 0.202 to 0.244 s; overlap ratio 1.85 to 2.48 |
| longest same-pitch run | 2 to 3 |
| harsh simultaneous intervals | **0**, out of 506 simultaneous pairs |
| onset rise | median 10.67 to 12.87 dB; 10th percentile 7.71 to 8.81 dB; **0 contacts under 3 dB** |
| duck | 24.3% to 34.5% of the timeline, 0.52 to 0.92 onsets/s, 9 dB maximum |
| bed level after the escape | −14.5 to −24.3 dB against the second before it |
| mono fold | −0.05 to −0.13 dB, correlation 0.958 or better, no band hole |
| phone high-pass | −5.23 to −6.81 dB against the master; 92.9% or more of what survives is in 300–2000 Hz |
| timing error | at most 0.500 sample (10.4 µs); every cue within half a sample |
| ending | exact digital silence for the last 150 ms of every preview |

### Escalation, on seed 12818

| third | events/s | mean voices | balls | distinct pitches | mean ladder | centroid | palette share | short-term |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| early | 4.20 | 1.87 | 4 | 11 | 4.37 | 554 Hz | 92.3% | −21.11 LUFS |
| middle | 12.84 | 3.00 | 10 | 12 | 5.72 | 557 Hz | 92.5% | −18.88 |
| late | 13.92 | 3.42 | 15 | 15 | 6.88 | 657 Hz | 93.2% | −17.93 |

Every axis of richness rises monotonically and loudness rises by 3.2 LU — it
climbs, it does not run away, and a test bounds it under 6 LU. The register
climbs with it, because the outer shells are higher windows of the ladder and
the late run is where the balls are.

**The noise guard needed a different instrument.** Spectral flatness is the
textbook measurement and it is useless here: a sum of pure partials has
near-zero energy in most bins, the geometric mean underflows, and every third
reads 0.00001 whether one ball is playing or fifteen are. What the question
actually needs is how much of the energy is still standing *on notes the
palette can play* — within 35 cents of any ladder position or its sub-octave
and first three harmonics. That reads 92.7–94.1% on these renders and 17.5% on
white noise at the same RMS, and it goes **up** from early to late on all seven
candidates, which is the evidence that the late third is denser without being
muddier.

## The climax

The canonical run stops at the first escape, so nothing new is struck after
it; the "many balls still active" the brief describes is a visual-branch fact,
not an audio one. What the escape duck actually clears is the decaying tail of
everything still ringing, and it clears a lot: the bed's own level in the
second after the escape is 14.5 to 24.3 dB below its level in the second
before. The suppression starts 80 ms ahead of the resolution and nothing is
muted earlier than that. The escape is the loudest single moment of every
render and sits 2.76 to 2.99 dB above the panel break, the next loudest kind.

## Outputs

Committed, under `docs/validation/category3_multiplying_shell_audio_v2b/`:

- `proof_candidates.json` — the derivation, the survivors and every rejection;
- `variant_comparison.json` — three systems, two reference seeds;
- `proof_set.json` — the seven headline rows and their spans;
- `scores/` — eleven deterministic score documents: seven for the selected
  system, and two each for the two it was compared against;
- `measurements/` — eleven measurement reports, one per score;
- `timelines/` — seven diagnostic PNGs: envelope, duck, polyphony curve, event
  lanes and the pitch scatter, one picture per candidate.

Local, in the ignored `output/category3_multiplying_shell_audio_v2b/`:
seven verified playback documents, eleven 24-bit 48 kHz stereo WAVs (75 MB),
and, where FFmpeg is present, a still-image diagnostic mux per seed. The
expensive half of a real mux needs the visual branch's frames and this branch
does not integrate visuals, so the still is what a reviewer gets to listen to.

Reproduce with:

```powershell
python -m satisfying.multishell_audio_cli candidates
python -m satisfying.multishell_audio_cli variants
python -m satisfying.multishell_audio_cli build
python -m satisfying.multishell_audio_cli verify
python -m satisfying.multishell_audio_cli timeline --mux
```

`verify` re-derives every seed from scratch and compares playback digests,
score fingerprints, the whole score document and the PCM digest: 7/7 reproduce
exactly.

## Validation

`tests/test_multiplying_shell_audio.py` adds 60 tests: the frozen V2 schema
field by field, the locked config digest, layer isolation by import graph,
palette consonance over every ladder pair, the ladder-versus-transposition
distinction, equal-width degrees, shell registers, lineage inheritance and
sibling distance, one voice per canonical collision, half-sample timing, the
absence of a grid, density shortening without silencing, cluster and repeat
management, pre-contact damage state, five damage colours, break and escape
chords in the palette, spawn intervals and stereo mirroring, lift counting,
the lift/spawn sum, duck bounds and causality, clipping, ending silence, mono,
phone, masking, escalation, three-way determinism, WAV round-trip and the
candidate rules.

```text
pytest -q tests/test_multiplying_shell.py tests/test_multiplying_shell_audio.py \
  tests/test_shell_escape.py tests/test_tile_escape.py \
  tests/test_tile_escape_phase2.py tests/test_tile_escape_phase3.py \
  tests/test_tile_escape_phase4.py tests/test_tile_escape_phase5.py \
  tests/test_tile_escape_phase6.py

505 passed, 1 skipped
```

Phase 1's 445 tests are unchanged and the single-ball Test #2 and Test #1 are
untouched.

## Handoff

Carry `open_quartal` and the seven candidates into the A/V comparison. Seeds
12818 and 12004 are the two fifteen-ball runs and the strongest test of dense
polyphony; 11319 is the busiest per second (10.37 events/s) and the one with
the deepest ducking; 949 is the lightest counterexample at eight balls, and it
has the largest early-to-late polyphony gain of the set. Both routes and both
kinds of final escape are represented.

Reconcile this candidate list against the visual branch's by intersection —
both were derived from the same eighteen Phase 1 seeds with the same rules,
and `proof_candidates.json` records the reason each of the eleven rejections
lost so the comparison is mechanical.

Keep canonical times as the source of truth. If the visual pass adds a hold, a
retime or a bookend, put an explicit render-time mapping *above* this score
rather than changing an event; the whole layer is built on the promise that a
sound happens when the ball hit the wall. Do not select a production seed, and
do not integrate visuals, in this branch.

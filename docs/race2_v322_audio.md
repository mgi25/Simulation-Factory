# Race #2, V32.2 — the audio pass

**Branch** `v322-asmr-audio-final`, from `v321-track-geometry-readability-final`
(`bc59457`). The picture is V32.1's and is not touched. Only audio changed, and
the proof of that is structural rather than promised — see §2.

    python tools/race2_v322_audio.py all --winner=B

---

## 1. Current audio diagnosis

The V32 mix is six layers. Rebuilt in isolation at their designed levels and
measured, they are:

| stem | RMS dBFS | peak dBFS | active | within 10 dB of its own median | share >2 kHz |
|---|---|---|---|---|---|
| ambience | −40.00 | −26.66 | 100.0% | 100.0% | 0.0% |
| **rolling bed** | **−30.00** | −14.73 | **99.5%** | **96.3%** | **42.2%** |
| **rattle grain** | **−36.00** | −21.45 | **100.0%** | **99.0%** | **86.3%** |
| music | −28.00 | −9.15 | 92.2% | 79.6% | 0.0% |
| impacts (239) | −39.52 | −16.40 | 84.3% | 75.4% | 0.8% |
| crossings (8) | −35.73 | −8.16 | 10.5% | 5.8% | 0.2% |

The rolling bed is the loudest *broadband* voice in the film and the rattle grain
is the flattest signal in it: the grain is above threshold in 100% of 100 ms
windows and within 10 dB of its own median in 99% of them. Only the music bed is
louder in RMS terms, and it is both quieter above 800 Hz (nothing at all) and
considerably less flat (79.6%).

Measured on the delivered Short:

| band | share of total power | span across the film (0.25 s windows) | windows within 6 dB of median | windows 12 dB down |
|---|---|---|---|---|
| 800–2000 Hz | 11.4% | 10.6 dB | 88% | 0.0% |
| 2000–5000 Hz | 10.3% | 7.4 dB | 99% | 0.0% |
| 5000–10000 Hz | 6.6% | **4.2 dB** | **100%** | **0.0%** |

**24.2% of the mix's power is above 2 kHz and essentially all of it is those two
layers.** The impacts and crossings put 84–92% of their energy in 300–800 Hz and
the music bed has none at all above 800 Hz. So everything the ear registers as
"air" or "texture" in the V32 Short is the rolling pair — and it never stops. The
5–10 kHz band moves 4.2 dB from the first frame to the last.

`docs/validation/race2/v322_audio/spectrogram_CONTROL.png` shows it directly: the
upper two-thirds of the frame is an unbroken speckled wash from 0 to 19.17 s with
no gap anywhere in it.

### Loudness of the CONTROL

−14.18 LUFS integrated, −1.93 dBTP, **LRA 3.57 LU**, full-band 0.5 s span
10.1 dB. Those last two are the dynamics half of the same complaint.

## 2. Source of the continuous grain

`audio/marble.py:build_race_audio`, the block that builds `grain`:

```python
grain = Noise(stable_seed("rattle", seed_base)).fill(length)
high_pass(grain, 1700.0, ...)        # 1.7 kHz
low_pass(grain, 8200.0, ...)         # to 8.2 kHz
...
grain[index] *= (interpolated contact_energy) ** 1.2
_to_rms(grain, LEVEL_ROLL - 6.0)     # −36 dBFS RMS, all 1150 frames
```

It is nominally contact-driven. It is not, and the arithmetic says why.

**`presentation.contact_energy` is a constant in disguise.** Its per-second mean
across the whole race is:

    0.415 0.365 0.355 0.508 0.518 0.513 0.455 0.486 0.447 0.432
    0.491 0.490 0.470 0.452 0.431 0.409 0.386 0.407 0.485 0.439

It never leaves 0.355–0.518. Raised to the 1.2 in the code, that is a total
travel of **3.3 dB over nineteen seconds**. A gain that moves 3.3 dB is a fader
position, not a modulation.

**Worse, it is anti-correlated with the rolling bed.** Pearson r between the
bed's drive and the grain's control is **−0.233**. The bed is loudest at 15–17 s
(drive 0.61) where the grain is quietest (0.386); the grain is loudest at 3–5 s
(0.518) where the bed is quietest (0.20). The two layers fill each other's gaps,
so the *sum* is flatter than either one alone. That is why the Short has a
texture rather than a dynamic.

### The lesson

A continuous layer with a nominal control signal is not automatically dynamic.
The control has to be measured. The whole defect here is three decibels of range
on a signal everyone assumed was tracking the race.

## 3. ASMR design

New module `audio/asmr.py`. `audio/marble.py` is untouched, so every edition up
to and including V32.1 still rebuilds byte for byte, and the CONTROL in this
comparison is the mix that actually shipped (asserted by SHA-256 at build time
and by `tests/test_race2_v322_audio.py::test_control_reproduces_the_shipped_master`).

The hierarchy is the brief's:

1. **physical ASMR** — rolling, rail ticks, marble-to-marble clicks, track contacts
2. **mechanism impacts** — five machines, five identities
3. **music** — under all of it
4. **room tone** — −44/−45 dBFS RMS, low-passed at 300 Hz, inaudible as a layer

Everything is placed on a recorded event. The replay was already carrying two
event streams the V32 mix never used:

* **116 `collision` records** — real marble-on-marble contacts with a closing
  speed (2.1 to 42.4 wu/s) and a world position;
* **32 `mechanism_hit` records** across five machines — `studs`(1), `drum`(14),
  `sweep`(5), `pair`(9), `last`(3).

### Telemetry

`asmr.telemetry` reads the replay and the camera track onto the film's own 1150
frame grid and produces, per frame: frame-weighted pack speed, top speed, camera
proximity, on-screen count and screen pan.

`pack_speed` is deliberately *not* `presentation.rolling`'s mean over all running
marbles. Each marble is weighted by how large it is in the frame, so a straggler
forty units behind and a finished marble circling the run-out stop making the bed
louder for nothing. The difference is the whole dynamic: the frame-weighted speed
runs **7.1 wu/s at 3–4 s against 30.0 at 15–16 s**, where the unweighted mean
barely moves.

## 4. Rolling logic

`asmr.rolling_layer`. Three changes from V32's bed, each aimed at one fault.

**Pitched, not broadband.** Noise through two modulated state-variable
band-passes rather than a low-passed hiss: a fundamental that rides 250–770 Hz
with the pack speed, and a formant at 3.15× it (790–2430 Hz). A band-pass means
level and brightness are separate controls, which is what let the old bed be loud
and dull at once. The layer measures 51% of its power in 300–800 Hz, 22% in
800–2000 and **2.1% above 5 kHz**.

The first version centred it at 170–560 Hz. Two things were wrong with that: a
20 mm sphere on a hard channel does not ring at 170 Hz, and it piled the layer
into the same 120–300 Hz band as the music's bass, the drum and the arrivals —
53.6% of the whole mix's power in one band.

**Gated.** A half-cosine knee under the drive signal: below `roll_gate` the
output is zero, not quiet. On this film that is 5.2% of the running time in Mix A
and the layer spends 32.6% of it more than 20 dB under its own 95th percentile.
Amplitude span p20→p95 is **33.1 dB** (A) and 26.1 dB (B).

**Camera-aware.** `proximity_depth` (0.80 in A, 0.70 in B) hands most of the
layer's level to how large the nearest racer actually is in the frame. Proximity
on this film has a per-frame p5-p95 of 0.58-0.91 and a standard deviation of
0.107; its per-second means run 0.574 to 0.932. So the sound pulls back when the
lens does.

The layer is levelled by **RMS**, not peak. Peak-levelling a gated signal was a
real error made during this pass: the gate gives the layer a ~21 dB crest, so a
peak budget of −19.5 dBFS put its *average* at −40 dBFS and the rolling layer —
the subject of the whole exercise — was inaudible under the contacts. RMS
normalisation changes only where the layer sits; every ratio inside it, and so
all the contrast the gate bought, is untouched.

## 5. Collision logic

### Rail ticks — what replaces the grain

The information the grain carried is real: the field *is* rattling. It is not
deleted, it is re-voiced as **discrete events**. `presentation.residuals` between
9.0 and 11.0 wu/s (the latter is `presentation.impacts`'s own floor, so the two
bands meet without a gap) fire a 5–9 ms band-limited tick, 2.2–6.5 kHz, one per
marble per 85 ms, at most three anywhere in 75 ms. 211 of them.

**The first attempt at this was the same bug in a new costume.** At a floor of
5.6 wu/s with a 52 ms debounce it produced 466 ticks whose per-second count ran
19, 28, 25, 21, 25, 27, 29, 26, 30 … all the way to the finish — a new continuous
texture, which is exactly what Part A forbids. The reason is arithmetic: eight
marbles debounced at 52 ms can supply 154 ticks a second and the raw signal had
2032 candidates, so the *ration* was the binding constraint in every second of
the film, and **a density set by a cap is by definition a constant.** The physics
was never allowed to decide.

Raising the floor to 9.0 makes the floor the binding constraint. The candidate
count per second then runs 19, 64, 72, 18, 10, 17, 29 … — a sevenfold swing that
is the race's own, with the 3–5 s stretch genuinely sparse. Pinned by
`test_the_tick_density_is_set_by_the_physics_not_by_the_cap`.

### Marble on marble — 77 clicks

From the replay's own `collision` records, which the V32 mix never read. Closing
speed ≥ 3.4 wu/s, one per pair per 75 ms, at most two anywhere in 45 ms.

`marble_click` is modelled on what two acrylic spheres actually do: there is no
cavity behind the contact, so the partials are high (1650–2270 Hz), *inharmonic*
(1 : 1.593 : 2.136 — a sphere's first two modes are not an octave apart, and
using an octave makes it a bell instead of a bead) and dead inside 40 ms. Harder
contacts get brighter and **shorter**, not longer.

### Marble on track — 239 contacts

`presentation.impacts` unchanged as the event source, re-voiced. The click's
pass-band starts at 1.2 kHz and stops at 7 kHz rather than running to 11 kHz, and
the ring partial moved from 2.71× to 2.44× and came down 6 dB — because a cue
that restates 2–5 kHz two hundred and thirty-nine times in nineteen seconds is
the fatigue problem however transient each one is.

### The machine-gun guard, and a bug in it

`_ration` claimed "at most N cues in any window". It did not do that. Counting
only the cues *already kept* inside a candidate's window leaves the invariant
open from the other side: a cue admitted later, whose own neighbourhood was under
the cap when it was considered, can push an earlier cue's neighbourhood over it.
On this race that produced runs of four ticks inside a 75 ms window under a cap
of three. The check is now made on the trial list, and
`test_the_machine_gun_guards_actually_ration` verifies the invariant over every
window in the result rather than over each kept cue's own neighbourhood — which
is the check that let the first implementation through.

## 6. Mechanism sound identities

Five machines, and they are given different *behaviour in time* rather than
different EQ of one knock. Each owns a section of the race, so no two overlap.

| machine | when | hits | the sound |
|---|---|---|---|
| `studs` | 0.93 s | 1 | four small taps 17 ms apart, each quieter — a stud field |
| `drum` | 2.23–4.70 s | 14→8 | soft, cushioned knock inside a shell that rings on after it (196 / 311 / 742 Hz) |
| `sweep` | 6.28–7.60 s | 5→3 | a 130 ms band-passed move that opens and closes, *then* the arrival knock |
| `pair` | 9.02–10.95 s | 9→6 | two knocks 26 ms apart — under ~30 ms the ear fuses them into one "clack" |
| `last` | 12.68–13.47 s | 3 | the only one with weight: a short 132→104 Hz component, high-passed at 55 Hz so it lands rather than booms |

Hits are debounced 120 ms per module, so 32 recorded hits become 21 cues; what is
dropped is a second strike inside an eighth of a second, which a listener hears
as one event.

`test_the_five_machine_voices_are_actually_different` measures it: every pair of
the five differs by more than 15% in spectral centroid or 40% in duration.

The course is a switchyard, so its five `line_choice` records get a very quiet
sprung metallic tick — the points changing. Real event, small sound.

## 7. Music source and originality

**Original, procedurally generated, owned outright by this project.** No sample,
no loop, no library, no music service, no YouTube Audio Library asset, nothing
third-party anywhere in the chain. Every sample is computed at render time by
`audio/asmr.py:music_score` from `audio/synthesis.py` oscillators and filters.
Full record: `docs/validation/race2/v322_audio/music_license.txt`.

## 8. Musical structure

**The race chooses the tempo.** The winner crosses at replay 15.81667 s, and

    bpm = 9 bars × 4 beats × 60 / 15.81667 = 136.565

puts that crossing exactly on the downbeat of bar 9 — and lands in the kinetic,
playful range the brief asks for, so nothing had to be compromised to get the
alignment. The consequence is that the sections fall where the brief wanted them
without anything being laid over the film:

| bars | seconds | brief asks for | what happens |
|---|---|---|---|
| 0 | 0.00–1.76 | 0–2 s: immediate hook | eighth-note pulse, bass, no figure yet |
| 1–3 | 1.76–7.03 | 2–7 s: stable drive | the three-note figure enters |
| 4–6 | 7.03–12.30 | 7–12 s: more tension | syncopated counter-line, bass on every beat |
| 7 | 12.30–14.06 | 12–14.5 s: build | sixteenths, figure doubled an octave up |
| 8 | 14.06–15.82 | 14.5→finish: strongest | bass on every eighth |
| 9 | 15.82 | the crossing | the tonic triad, struck once, ringing out |
| 9–10.9 | 15.82–19.17 | payoff tail | one bass note a bar, decaying |

A minor, i–VI–III–VII, roots 220.00 / 174.61 / 261.63 / 196.00 Hz.

**The build is density, not level.** Bar energy peaks at 0.94, not 1.0, and the
sub-octave reinforcement is halved from bar 7. With the sub at full level through
the build, the bar-7 downbeat at 12.30 s was the loudest fifty milliseconds in
Mix B's film — ahead of the winner's crossing three and a half seconds later,
which is exactly the defect `tools/sloped_short_qc.py` has been checking for
since V19. A sprint that gets heavier is also simply wrong: what makes a final
section feel faster is density and brightness and the low end getting out of the
way.

The five musical parts are each nudged 0–7.3 ms off the beat (`_LAYER_OFFSETS`).
Inaudible as timing; it stops five voices struck on one sample from summing into
the tallest peak in the film.

## 9. Mix A — ASMR forward

The physical layer is the subject. Music 4.1 dB lower than B, a deeper rolling
gate, more tick and contact detail, no master compression.

    roll −26.5 RMS   tick −20.75   click −14.0   contact −28.0 … −14.5
    mechanism −13.5  finish −14.5  winner −8.5   music −32.0 RMS   room −44.0
    roll_gate 0.20   proximity_depth 0.80   duck 2.0 dB   space 5.0 dB

Buses: physical −29.84 dBFS RMS, rolling −27.36, music −33.14.

## 10. Mix B — balanced engagement

The same physical layer, held down about a decibel, under a music bed that is
genuinely present. Deeper event ducking (7 dB) so the transients still come
forward, and a stronger musical sprint.

    roll −29.5 RMS   tick −22.5    click −15.5  contact −29.5 … −15.5
    mechanism −13.0  finish −13.5  winner −9.6  music −27.0 RMS   room −45.0
    roll_gate 0.17   proximity_depth 0.70   duck 7.0 dB   space 4.0 dB

Buses: physical −30.30 dBFS RMS, rolling −30.30, music −29.06.

**An earlier pair of profiles differed by 2 dB of music and were not two
directions at all** — less than the step between two faders. The shipped pair is
4.1 dB apart in music bus RMS and 3.0 dB in rolling, and
`test_the_two_directions_are_actually_two_directions` holds it there.

### Ducking (Part K) and space (Part G)

79 duck events — every mechanism hit, every arrival, every contact above half
strength — pull the music down by `duck_db` with an 8 ms attack and a ~0.3 s
recovery, taking the *minimum* of the dips rather than the sum, so two events
40 ms apart duck once rather than twice as far.

Three `space` events (the three `last` hits, 12.68 / 13.13 / 13.47 s) open a
wider dip **before** the event — 0.20 s of lead, 0.16 s attack — and pull the
rolling layer down as well as the music. The crossing gets its own, deeper and
longer version: the arrival runs 0.70 s and the music's resolution chord lands on
the same downbeat by design, so a 0.42 s recovery had the bed climbing back up
underneath the chime. Measured in the film: the mix falls to −26.7 dB at 15.6 s
and lifts to −17.4 dB on the crossing, **9.3 dB of space in front of the
winner**.

## 11. Loudness

| | CONTROL (V32) | Mix A | Mix B |
|---|---|---|---|
| integrated | −14.18 LUFS | −14.73 LUFS | **−14.58 LUFS** |
| true peak | −1.93 dBTP | −1.17 dBTP | **−1.27 dBTP** |
| sample peak | −2.06 dBFS | −1.30 dBFS | −1.30 dBFS |
| LRA | 3.57 LU | **6.04 LU** | 3.33 LU |
| full-band 0.5 s span | 10.1 dB | **21.2 dB** | 20.2 dB |
| master bus compression | 2.2:1, ~2–3 dB | **none** | **none** |
| limiter, worst / mean | — | −2.75 / −0.041 dB | −2.87 / −0.018 dB |
| limiter active | — | 4.0% of samples | 2.8% |

Loudness is reached with **one static gain over the whole timeline**, measured by
`audio/loudness.py` (a BS.1770-4 implementation checked against ffmpeg's
`ebur128` to 0.3 LU and against the EBU Tech 3341 calibration case at three
levels). A static gain cannot change LRA, crest factor or the relationship
between any two moments. Nothing normalises and nothing squashes.

The target is −14.5 LUFS rather than −14.0, and the half decibel is bought rather
than given away: at −14.0 the static trim is 0.5 dB larger, which pushed the
winner's arrival far enough over the ceiling that the limiter took 3.7 dB out of
the loudest moment in the film. The brief asks for "approximately −14 LUFS" and
says not to chase an exact figure at the expense of dynamics.

**Compression is on the music bus, not the master.** A bed built from struck
oscillators arrives with a ~19 dB crest, and at Mix B's level it — not any
physical event — set the peak of the whole film. A master compressor brought in
to catch it took 2.3 dB off every marble in the race. Compressing the bed alone
fixes the peak where it is made and the physical bus never sees a detector.

## 12. Fatigue analysis

| | CONTROL | Mix A | Mix B |
|---|---|---|---|
| power above 2 kHz | **24.2%** | 16.8% | 9.9% |
| power above 5 kHz | **14.0%** | 1.4% | 1.0% |
| 2–5 kHz within 6 dB of median | **99%** | 47% | 57% |
| 2–5 kHz span | 7.4 dB | **27.6 dB** | 22.7 dB |
| 2–5 kHz windows 12 dB down | **0%** | 37% | 30% |
| 5–10 kHz within 6 dB of median | **100%** | **46%** | 58% |
| 5–10 kHz span | **4.2 dB** | **28.4 dB** | 25.5 dB |
| 5–10 kHz windows 12 dB down | **0%** | 46% | 46% |
| 5–10 kHz duty cycle (20 ms) | **99.7%** | 60.9% | 65.1% |

Band shares of total power:

| | 20–120 | 120–300 | 300–800 | 800–2k | 2–5k | 5–10k | >10k |
|---|---|---|---|---|---|---|---|
| CONTROL | 9.6 | 23.2 | 31.5 | 11.4 | 10.3 | 6.6 | 5.8 |
| Mix A | 1.9 | 13.8 | 50.9 | 16.6 | 15.3 | 1.2 | 0.2 |
| Mix B | 4.3 | 26.9 | 44.9 | 14.0 | 9.0 | 0.8 | 0.2 |

`spectrogram_stack.png` is the same thing to look at: CONTROL's upper two-thirds
is an unbroken wash; A and B are dark up there with discrete vertical strikes and
visible gaps, widest across the slow stretch at 3–5 s.

### Low frequency (Part M)

1.9% / 4.3% under 120 Hz against V32's 9.6% — restrained, and supplied by the
music, which is what the brief asks. The music bus is 8.5% (A) and 9.4% (B)
under 120 Hz against the physical bus's 2.1%, asserted by
`test_the_low_end_is_restrained_and_belongs_to_the_music`. The `last` mechanism's
low component is high-passed at 55 Hz by the voice itself, so it cannot boom.

An intermediate version of the music sat an octave lower (roots A2 down) and
measured 60.5% of its own power below 120 Hz, dragging the finished mix to 48%
there — five times V32's figure. Moving the roots up an octave put the bass note
in 175–262 Hz, where a laptop can reproduce it and a phone can imply it.

## 13. Phone, small-speaker and mono review

Mono fold-down, measured:

| | mono loss | L/R correlation | worst band shift |
|---|---|---|---|
| CONTROL | −0.01 dB | 0.996 | <0.5 pt |
| Mix A | −0.03 dB | 0.986 | <2 pt |
| Mix B | −0.03 dB | 0.988 | <2 pt |

Everything is amplitude panning at `MAX_PAN` 0.42 or less, so nothing cancels.

Through a simulated small speaker (mono, two-pole high-pass at 500 Hz):

| | RMS drop vs full range | 5–10 kHz share | >10 kHz share | 5–10 kHz within 6 dB | loudest moment |
|---|---|---|---|---|---|
| CONTROL | −4.7 dB | **16.5%** | **14.6%** | **100%** | 15.80 s ✓ |
| Mix A | −5.4 dB | 2.7% | 0.0% | 46% | **1.10 s ✗** |
| Mix B | −5.5 dB | 2.3% | 0.5% | 58% | 15.85 s ✓ |

Two findings worth keeping.

**V32's grain is *worse* on a phone.** The filter removes the low end that was
partly masking it, and the continuous 5–10 kHz layer goes from 6.6% of the full-
range mix to 16.5% of what a phone speaker actually reproduces — still 100% flat.
The mix is at its most fatiguing exactly where most of this Short will be
watched.

**Mix A's loudest phone moment is its opening, not its finish.** The finish's
weight is in a 344/516 Hz deck resonance that a phone speaker cannot reproduce,
while the opening second is full of 2–5 kHz contacts and clicks that it
reproduces well. Mix B's arrival survives the filter because its chime (784,
1176, 1568, 2352 Hz) carries proportionally more of the cue. This was found by
measurement, and it is the single most decisive difference between the two mixes
for a Shorts audience.

## 14. The winner

**Mix B — balanced engagement.**

> **This choice was made on measurements and on the spectrograms, not by
> listening.** I cannot hear the files. The numbers below are real and the
> instruments are checked against ffmpeg and against synthetic signals, but every
> question in Part R that is genuinely about perception — "does rolling feel
> tactile", "do collisions feel satisfying" — is answered here by proxy and needs
> a human ear before upload. `compare_full_CONTROL_B.mp4` and
> `compare_full_A_B.mp4` exist for that. If a listener prefers A, switching is
> one command: `python tools/race2_v322_audio.py winner --winner=A`.

Why B, on the evidence available:

1. **It is the one that works on a phone.** Its loudest moment survives the
   small-speaker filter and lands on the winner's crossing; A's lands on its own
   opening second. For a vertical Short that is the deciding fact.
2. **It is further from the complaint.** 9.9% of power above 2 kHz against A's
   16.8% and V32's 24.2%. Both mixes fixed the *continuity*; B also has less of
   the energy there in absolute terms, which is the safer side to err on for a
   brief whose word was "irritating".
3. **It has the music the brief asked for.** Music bus 4.1 dB above A's, a clear
   rhythmic pulse from frame 0, and a sprint that lifts 1.5 dB over the middle
   section before the crossing ducks it.
4. It meets every delivery number with the master bus uncompressed and the
   limiter touching 2.8% of samples.

What B gives up, stated plainly: **LRA 3.33 LU against A's 6.04**, which is no
better than V32's 3.57. B does not improve the *loudness-range* half of the
dynamics complaint — it improves the spectral half (0.5 s span 20.2 dB vs 10.1)
and spends the rest on music. And three of its 21 mechanism cues sit 0.3–3.9 dB
under the music bed in the machines' own band.

Mix A is the better mix by every fatigue and dynamics measure and is kept as a
full deliverable, not a draft.

## 15. Answers to the Part R review questions

Measured where measurable, marked where not.

1. **Irritating continuous noise?** No, on the instruments: 5–10 kHz flat-within-
   6 dB falls from 100% to 58% (B) and its span from 4.2 to 25.5 dB. *Perceptual
   confirmation outstanding.*
2. **Does rolling feel tactile?** Not measurable. It is pitched rather than
   broadband, gated to silence 2.2% of the time, and spans 26 dB.
3. **Do collisions feel satisfying?** Not measurable. 77 marble-to-marble clicks
   now exist that did not before, with inharmonic partials and speed-mapped
   level.
4. **Distinct mechanisms?** Yes — every pair of the five differs by >15% in
   spectral centroid or >40% in duration, and each owns its own stretch of race.
5. **Does the audio change with the picture?** Yes. Rolling follows frame-
   weighted pack speed (per-second mean 7.1 → 30.0 wu/s) and camera proximity
   (per-second mean 0.574 → 0.932).
6. **Useful quiet moments?** Yes. 46% of 0.25 s windows are 12 dB under the
   5–10 kHz p95, against 0% in V32; 6.3% of the film's 0.1 s windows are 15 dB
   under its own full-band p95, against 0.0% in V32.
7. **Does music add momentum?** Not measurable. It is present from frame 0 at
   136.6 BPM and builds through four sections.
8. **Does music overpower the race?** No finish, in either mix. 3 of 21
   mechanism cues in B sit under the bed in-band (§14).
9. **Does the final sprint build?** Yes: +1.5 dB of music from the middle section
   into bar 8, with sixteenths and a doubled octave.
10. **Satisfying finish?** The crossing is the loudest 50 ms in both mixes, and
    stands 9.4 dB (B) over the music bed. *Perceptual confirmation outstanding.*
11. **Would repeated viewing annoy?** The duty cycle is the proxy: 100% → 65%.
    *Genuinely needs repeat listening.*
12. **Does it work on a phone?** B: yes, measured (§13). A: its finish does not
    survive the filter as well.

## 16. Remaining weaknesses

1. **Nobody has listened to it.** Every perceptual claim above is a proxy.
2. **Mix B's LRA is 3.33 LU**, no better than V32's 3.57. The spectral fix is
   large; the loudness-range fix is A's, and B trades it for music.
3. **Three of B's 21 mechanism cues** (drum #6 and #8 of 14, the ninth `pair`
   hit) sit 0.3–3.9 dB under the music in 300–4000 Hz. No machine loses its
   identity — every first and strongest hit is clear — but a repeat late in a run
   can be covered.
4. **11 of 32 mechanism hits are debounced away** by the 120 ms per-module gap.
   Deliberate, but it means a fast double-strike reads as one.
5. **The rolling layer's gate is shallow in B** (2.2% true silence against A's
   5.2%). B leans on level rather than on silence for its contrast.
6. **`phone_filter` is crude** — a two-pole high-pass at 500 Hz and a fold-down.
   It is a way of listening to what survives a speaker, not a model of one, and
   the "loudest phone moment" finding rests on it.
7. **The mix is only proven on seed 8.** The thresholds (`TICK_FLOOR` 9.0,
   `CLICK_FLOOR` 3.4) were chosen against this replay's own residual
   distribution; another course or seed would need them re-checked.
8. **Mix A's 16.8% above 2 kHz** is closer to V32's 24.2% than to B's 9.9%. It is
   discrete rather than continuous, but it is not a small amount of high
   frequency.

## 17. Should audio development stop?

**Yes, subject to one human listening pass.**

Against the brief's stop condition, for Mix B:

| | |
|---|---|
| no irritating constant grain | ✅ measured — 100% → 58% flat, 4.2 → 25.5 dB span |
| satisfying tactile marble audio | ⏳ built and measured; needs an ear |
| distinct mechanism sounds | ✅ five machines, measurably different |
| useful quiet contrast | ✅ 46% of windows 12 dB down, from 0% |
| engaging music | ✅ original, 136.6 BPM, four sections, race-derived tempo |
| strong final sprint | ✅ +1.5 dB and doubled density into bar 8 |
| satisfying finish | ✅ loudest 50 ms of the film, 9.4 dB over the bed |
| no copyright uncertainty | ✅ nothing third-party exists in the chain |
| phone-friendly mix | ✅ mono loss −0.02 dB; finish survives the filter |
| locked visuals | ✅ identical video stream MD5 and decoded-frame hash |

There is no further audio work this brief describes. If the listening pass
prefers A, that is a one-command switch, not a V32.3.

---

## Appendix — the visual lock

`mux` takes the shipping V32.1 film and runs `ffmpeg -c:v copy`. No decoder and
no encoder touches the picture, so the bytes that arrive are the bytes that left.
Verified two ways across all three films and the source:

    video stream MD5        49515b72fc1799ca611ce8d55490736e   (all four)
    decoded frames SHA-256  d7c3c48d1292dfa1…                  (all four)
    frames                  1150                               (all four)

And at the branch level: the only tracked file this branch modifies is
`pytest.ini` (two lines registering a test marker). `audio/asmr.py`,
`audio/loudness.py`, `tools/race2_v322_audio.py` and the test file are new. No
physics, course, track, camera, environment, lighting, presentation or render
module is touched, and `tests/test_race2_v322_audio.py::test_nothing_in_this_pass_imports_a_renderer`
asserts that `audio/asmr.py` cannot even reach one.

## Appendix — files

    exports/race2_v322_audio/
      race2_switchyard_final_audio.mp4              the upload candidate (Mix B)
      race2_switchyard_final_audio_phone_270x480.mp4
      race2_switchyard_control.mp4                  V32 audio, for comparison
      race2_switchyard_a.mp4                        Mix A
      race2_switchyard_b.mp4                        Mix B
      race2_switchyard_{control,a,b}_phone_270x480.mp4
      race2_switchyard_{control,a,b}_smallspeaker.wav
      compare_{full,sprint,start}_CONTROL_A.mp4     sequential listening pairs
      compare_{full,sprint,start}_CONTROL_B.mp4
      compare_{full,sprint,start}_A_B.mp4

    docs/validation/race2/v322_audio/
      diagnosis.json          the V32 stem analysis and the two control signals
      masters.json            every number each mix reports about itself
      audio_report.json       loudness, fatigue, mono, and the event timeline
      visual_lock.json        Part P evidence
      qc.json                 56 acceptance checks
      music_license.txt       licensing and provenance
      spectrogram_{CONTROL,A,B}.png, spectrogram_stack.png

# Category 3, Test #1 — HIT EVERY TILE TO ESCAPE — Phase 5: procedural audio and sound identity

**Decision: AUDIO PROOF PASSED.**

The soundtrack is written by the run. Every sound in the finished video is a
collision, an activation, or one of the three instants Phase 4 named, and there
is no bed, no loop and no music underneath them. `satisfying/tile_score.py`
turns the canonical playback document into a schedule of events on the
**render** clock; `satisfying/tile_audio.py` turns that schedule into samples
out of `audio/synthesis.py`'s oscillators and its seeded noise source. Neither
module can reach the physics, and a test reads their sources to say so.

Three things came out of this phase that were not in the brief's hypothesis,
and all three were found by measuring rather than by listening.

**A hierarchy that is correct on the master can be wrong on a phone.** The
first build of the detonation measured **+6.2 dB** over an ordinary activation
on the master and **+0.4 dB RMS** through `audio/loudness.py`'s phone-speaker
approximation. It was voiced the obvious way — the key at the bottom, the
tile's own note on top — which put almost all of its energy under 500 Hz, where
a phone speaker does not go. The same fault, in different clothes, was in the
unlock (a rising glide given a *decaying* envelope, so its energy sat at the
bottom of the rise) and in the arena as a whole (a 7.5 dB loudness gradient
from the bottom of the ring to the top, invisible on headphones). The fix is
one idea applied three times: **put the weight where a small speaker can
reproduce it**, and measure there as well as on the master.

**Peak-normalising a chord dilutes it, and phase dispersion does not fix
that.** A cue is normalised to unit peak before its gain is applied, which is
what makes the hierarchy exact. For the detonation's eleven voices, all
starting in phase, that divisor is about four — every voice comes out at a
quarter of the level it was written at. Spreading the starting phases was the
obvious repair and it is not one: measured across all eleven pitches of the
vocabulary it changed the chord's normalised energy by between **+2.6 dB and
−1.5 dB** depending only on how that frequency set happened to sum, and it
cancelled two voices that shared a pitch by **18.3 dB**. It was removed. The
detonation carries instead by being voiced an octave up over a fixed bright
rack.

**The release has to be as long as the video has room for.** Built at a fixed
1.56 s against endings that have between 1.17 s and 1.53 s left in them, the
escape pad ran past the last frame and was cut off by the end of the buffer on
every seed — seed 37169's final sample measured **−26.9 dBFS**. A Short that
ends in a splice is not an ending. The release now takes its length from the
timeline, and the last 0.20 s of every video is exact digital silence.

---

## 1. Base / Git

| | |
|---|---|
| starting SHA | `6cca4281bed78779e15031125f91b5266b8eef8d` (Phase 4) |
| branch | `category3-tile-escape-v5`, created from `6cca428` |
| worktree | `../wt-category3-tile-escape` |
| merged | **no**, as instructed |
| history rewritten | **no** |
| stale branch guards | untouched |
| files added | `satisfying/tile_score.py`, `satisfying/tile_audio.py`, `satisfying/tile_phase5_cli.py`, `tests/test_tile_escape_phase5.py`, this file |
| files modified | **`tests/test_tile_escape.py`** — Phase 1's workstream boundary guard, widened and then strengthened; section 2.1 is the whole story |
| other workstreams | untouched — nothing under `race/`, `race2/`, `sloped/`, `company/`, `audio/`, `godot/` or `tools/` was changed |

The resulting commit and the remote SHA are in section 12.

---

## 2. Architecture

Three layers, and the separation is the point: the canonical events, the audio
schedule, and the samples.

| file | what it is | what it may not do |
|---|---|---|
| `satisfying/tile_playback.py` + `tile_completion.py` | Phase 3 and Phase 4, unchanged | — |
| `satisfying/tile_score.py` | the score: pitch mapping, event schedule, density damping, determinism | imports no synthesiser, holds no buffer |
| `satisfying/tile_audio.py` | the sound: cues, the mix, the master, every measurement | imports no simulator, takes no seed |
| `satisfying/tile_phase5_cli.py` | the driver — `export`, `score`, `render`, `sync`, `climax`, `mux`, `verify`, `compare` | |
| `tests/test_tile_escape_phase5.py` | 74 tests | launches neither Godot nor ffmpeg |
| `tests/test_tile_escape.py` | **modified** — Phase 1's boundary guard, widened and strengthened | see section 2.1 |

Nothing in `satisfying/tile_escape.py`, `tile_arena.py`, `tile_evaluator.py`,
`tile_pacing.py`, `tile_completion.py` or `tile_playback.py` changed, and
neither did either GDScript. The physics, the acceptance rule, the ending and
the renderer are Phases 1–4's exactly, which is what makes "the audio changed
nothing" checkable rather than claimed.

### 2.1 The one existing test this phase changed, and why

Phase 5 modified `tests/test_tile_escape.py`. That is the only file outside
Phase 5's own that it touched, and it is worth the paragraphs because the
change is to a *guard*.

`test_category_three_imports_no_other_category_and_no_company_os` is Phase 1's
workstream boundary: it walks every file in `satisfying/` and asserts each
import root is on an allowlist of the standard library, Pillow and `satisfying`
itself. Its own comment says the list "grows when Category 3 needs another
stdlib module and **never** when it needs another package".

Phase 5 needs another package. Oscillators, envelopes, a seeded noise source, a
24-bit WAV writer and an EBU loudness meter all already exist in `audio/`, and
writing a second copy of them inside `satisfying/` would mean two true-peak
meters in one repository that can drift apart. So the guard was widened.

**And the widening immediately caught a real fault, which is why the guard was
right and the first draft was wrong.** Phase 5's first version imported
`audio/soundtrack.py` for three generic things — a limiter, an equal-power pan
law and two ceiling constants. `audio/soundtrack.py` opens with
`from audio import cues`: the battle cue library. Importing it would have
pulled another workstream's sound design into Category 3's import graph to get
at sixty lines of mastering. The guard failed, and the fix was not to allow it
— it was to **drop the dependency**. `satisfying/tile_audio.py` now carries its
own master stage, and the rendered PCM is byte-identical before and after the
change, so nothing about the sound rests on this.

What the guard says now is narrower in the way that matters and wider only
where it had to be:

* the stdlib list gains `array`, `collections` and `numpy` — a cue is an
  `array("d")`, the limiter's sliding minimum is a `deque`, and numpy is
  already a declared dependency of this repository;
* `audio/` is allowed, but **only** `synthesis`, `wav_io` and `loudness`, by
  module and not by package root, so `from audio import cues` fails as loudly
  as `import race2` would;
* and a new test, `test_category_three_uses_only_the_leaf_audio_modules`,
  asserts that those three modules themselves import nothing but the standard
  library and numpy. That is what makes the widening a boundary rather than a
  hole: if any of the three ever grows a dependency on the rest of `audio/`,
  it fails there before the allowlist starts quietly permitting it.

Phase 1's guard went from "no packages" to "these three leaf modules, proven
to be leaves". It is a stricter statement about a larger surface, and it is
the reason this dependency is defensible rather than merely convenient.

**The event path.** `simulate` → `playback_document` → `attach_completion` →
`tile_score.schedule` → `tile_audio.render` → `write_wav` → ffmpeg. Every arrow
is one way. `schedule` does not mutate the document it reads — a test compares
the JSON before and after — and `render` never sees a seed.

**The synthesis path.** Every sample comes from `audio/synthesis.py`:
`tone`, `envelope`, `noise_burst`, `low_pass`, `high_pass`, and `Noise`, a
SplitMix64 stream seeded by `stable_seed` from the note's own frequency.
Nothing is sampled, downloaded, licensed or borrowed. Phase 5 adds two
primitives that package did not have and this one needed — `_moving_low_pass`,
a filter whose cutoff glides (a filter *opening* is what an opening sounds
like, and a static one cannot say it), and `_swell`, the reverse of an impact
envelope — and they live in `tile_audio.py` rather than in `audio/` because
this is a Category 3 system, not a project-wide music engine.

The master chain is **one static gain and a look-ahead limiter**, both in
`satisfying/tile_audio.py` for the reason in section 2.1. There is no
compressor, and a test asserts on the source that there is not: a compressor
pulls the loudest moments down toward the quietest, and the distance between
the detonation and a duplicate is the whole design.

---

## 3. The clock is render time, never simulation time

The ending holds the simulation clock still for **0.92 s** — 0.14 s of
hit-stop, 0.48 s of confirmation, 0.30 s of the gate retracting — and then
plays the escape at 0.45×. A cue written against simulation time would stall
with it, and the detonation, the unlock and the release would all arrive at the
same instant.

So the score reads `completion["timeline"]` and takes the four beats **by state
name**:

| beat | segment | seed 3530 |
|---|---|---|
| final hit | `final_hit`.render_start | 32.1431 s |
| confirmation | `confirming`.render_start | 32.2831 s |
| unlock | `unlocking`.render_start | 32.7631 s |
| release | `escaping`.render_start | 33.0631 s |
| settled | `settled`.render_start | 34.0546 s |

Nothing here is re-derived from the timing preset, so a re-timed ending carries
the sound with it. Two things are consequences rather than copies: the gate's
rise is exactly as long as the `unlocking` segment, so it tops out as the
opening completes; and the release is exactly as long as the video has left
after it, less the closing silence.

Below the completion the `locked` segment is the identity map, so a collision's
simulation time *is* its render time. That is asserted, not assumed —
`schedule` refuses a timeline whose first segment has a rate other than 1.0.

### Events land on the frame the picture lands on

A tile struck at 21.4711 s is first drawn on frame `ceil(21.4711 × 30) = 645`,
shown at 21.5 s. Two placements were possible:

* at the canonical instant — the audio then **leads** the picture by up to one
  frame period, a mean of 16.7 ms at 30 fps;
* at the frame instant — the audio is simultaneous with the frame the viewer
  actually sees.

The second is used. Audio arriving before its picture is the direction the ear
detects soonest, and a video is a sequence of frames, so "the frame on which
the tile lights" is the honest definition of when the tile lights. The rule is
`tile_playback.activation_frames`' rule — Phase 3's, written for the Godot
audit before any of this existed — applied to every contact rather than only to
activations, and a test compares the two computations.

---

## 4. The musical system

### The vocabulary

**Minor pentatonic on A, two octaves: 220 to 880 Hz, eleven notes.** The scale
is chosen for one property and not for a mood: the ball decides the order, so
consonance cannot be arranged, it has to belong to the set. A minor pentatonic
has no semitone and no tritone anywhere in it, in any inversion, so every pair
and every stack of the eleven pitches is consonant. A major scale is not — its
fourth against its seventh is a tritone, and at five contacts a second that
pair would arrive many times a run. A test checks all fifty-five intervals.

| index | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Hz | 220.0 | 261.6 | 293.7 | 329.6 | 392.0 | 440.0 | 523.3 | 587.3 | 659.3 | 784.0 | 880.0 |
| tiles | 7 | 6 | 4 | 4 | 2 | 4 | 4 | 4 | 4 | 4 | 8 |

### Tile → pitch: height

**A tile's pitch is its height in the arena.** Up is high. The mapping is a
function of the arena's geometry and of nothing else, so `tile_17` is the same
note in every run of every seed whatever order the ball finds the tiles in — a
test compares the whole table across two seeds with different collision orders.

It gives the ring a shape nobody has to be taught:

| side | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pitch indices | 0,0,0 | 0,0,1 | 1,1,2 | 2,3,3 | 4,5,5 | 6,6,7 | 7,8,8 | 9,9,10 | 10,10,10 | 10,10,10 | 10,9,9 | 8,8,7 | 7,6,6 | 5,5,4 | 3,3,2 | 2,1,1 | 1,0,0 |

Adjacent walls are adjacent notes — no two neighbouring tiles are more than one
step apart, including across the wrap from tile 50 to tile 0, which is exactly
where an index-based mapping breaks. The two flanks mirror each other, the ball
working round the bottom of the arena is audibly in the bass, and fifty-one
tiles share eleven notes so that the arena sounds like one instrument rather
than like fifty-one.

**Stereo is the other axis.** A tile is panned by the x of its midpoint, up to
0.45 of the field, using `audio/soundtrack.py`'s equal-power law. The
*midpoint*, not the contact point: a tile's sound is its identity, so the same
wall has to arrive from the same place every time it is struck.

### Duplicate against activation

The same fundamental, opened out. That is the whole idea, and it is what makes
progress audible without anyone explaining it — the arena does not change what
it says, only how much of it it says.

| | duplicate | activation | final |
|---|---|---|---|
| fundamental | the tile's | the tile's | the tile's, plus the key |
| octave partial | 0.17 | 0.42 | 1.00 (the loudest voice) |
| twelfth | — | 0.135 → 0.46 | 0.52 |
| bright tick | 1.4–5.2 kHz, 20 ms | 2.0–7.2 kHz, 26 ms | a 1.4–9 kHz bloom, 400 ms |
| roll-off | low-passed at 1.7 kHz | — | — |
| decay | 0.042 s | 0.215 s | 0.62 s |
| length | 0.11 s | 0.62 s | 1.70 s |
| peak gain | 0.098 | 0.300 → 0.385 | 0.760 |

A duplicate is short, dark and quiet — 110 ms, rolled off above 1.7 kHz — with
one very quiet band-limited tick on it so that a contact is still a contact on
a phone speaker. It keeps the run alive without implying progress: it does not
move its tile on screen either, which is Phase 4's half of the same contract.

### The small-speaker tilt

Rendered flat, the arena has a loudness gradient that exists **only on a
phone**: the low tiles measured 7.5 dB quieter than the high ones through
`loudness.phone_filter` while sitting inside 1.4 dB of each other on the
master. The bottom third of the ring would have sounded like it mattered less,
on the speaker most of the audience is using.

The correction is a spectral tilt rather than a gain: the lower a note is, the
more of its energy its upper partials carry. That is what a struck bar actually
does — a low one is far richer in overtones than a high one — so it costs
nothing in plausibility, and every note's fundamental, and therefore its
identity, stays exactly where it was. Full strength at 220 Hz, nothing from
660 Hz up. It narrowed the gradient to 6.2 dB on its own; the rest came from
layering the bright tick **after** the tonal body is normalised rather than
before, which is section 5's finding.

---

## 5. Progression

Subtle, and driven entirely by the activation's own `count` field — canonical
data from the document's ledger, not a clock and not a curve.

| dial | at 1 of 51 | at 50 of 51 |
|---|---|---|
| twelfth partial | 0.135 | 0.460 |
| fourth partial | 0.000 | 0.160 |
| upper-partial decays | ×1.00 | ×1.60 |
| peak gain | 0.300 | 0.385 |
| a fifth above the fundamental | — | fades in over the last fifth of the run |

The duplicate is deliberately left **fixed** while the activation opens up, so
what grows over the run is the *gap* between them.

Measured on the finished cue: spectral centroid rises monotonically from
**2398 Hz to 2582 Hz**, and total energy by **+0.5 dB** once peak
normalisation has taken its share back. Eight per cent of brightness and half
a decibel of weight across thirty-two seconds is about as restrained as a
progression can be and still be measurable, which is what the brief asked for —
and whether it is *perceptible* is one of the questions section 18 hands to a
listener.

**It was backwards twice before it was right**, and both times every gain in
the configuration moved in the correct direction while the rendered cue got
*darker*:

* **the decay growth was applied to the fundamental too.** The fundamental
  carries most of the energy, so ringing it longer simply adds bass. Growth now
  applies to the upper partials only.
* **the bright tick was layered on before the cue was normalised.** The tick is
  the highest-frequency thing in an activation; added first, its share of the
  finished cue is decided by whatever the partials underneath it happen to sum
  to, so as the progression added partials the tick quietly got quieter —
  centroid 2379 Hz at 1 of 51 against 2166 Hz at 50 of 51. Transients are now
  layered after normalisation, at a fixed share, and normalised again.

The second of those is a general rule this phase learned the hard way and it is
written down at the top of the cue section: **normalise, then layer, then
normalise again.**

### No milestone audio

There is none at 25%, 50% or 75%, and none was built and rejected — the brief's
instruction not to add them merely because the numbers exist was taken at face
value. The arena communicates progress visually and the activation stream
communicates it audibly; a gong at 26 of 51 would be scoring, not sound. **The
fifty-first tile is the only milestone**, and it is the one the brief makes
mandatory.

---

## 6. The five strengths

| event | what it is | peak gain | length | > 500 Hz |
|---|---|---|---|---|
| `duplicate` | the tile's note, muted and short, with a tick | 0.098 | 0.11 s | 4.9% |
| `activation` | the same note, opened out | 0.300 → 0.385 | 0.62 s | 47.5% |
| `final` | the same note again, as a chord over the key | 0.760 | 1.70 s | 47.9% |
| `unlock` | that note sweeping up, and a gate opening | 0.360 | 0.62 s | 47.5% |
| `escape` | the root triad, swelling and decaying to nothing | 0.440 | from the timeline | 23.5% |
| `confirm` | the `drone` hold only: a low sustain under the pause | 0.075 | 0.95 s | — |

The gains **are** the hierarchy: a cue is peak-normalised to 1.0 before its gain
is applied, so an event's peak in the mix is its gain whatever the partials
inside it summed to, and nothing downstream normalises an event on its own. An
inverted configuration raises `ScoreError` at construction.

### The detonation

The fifty-first tile keeps its identity — its fundamental is in the chord and
its octave is the loudest voice in the piece — and the root and fifth of the
scale arrive under it, so the ending states the same chord whichever tile
happens to be last and the unlock and the release that follow are answering a
question it asked. On seed 3530 the last tile is at the bottom of the ring and
its note happens to *be* the root; on a seed whose last tile is at the top it
is a tenth above, and the resolution is identical either way. A test renders
the cue for all eleven pitches and looks for the root's fourth octave in each.

It is voiced an **octave up** with a fixed bright rack at 880, 1320, 1760 and
2640 Hz — all octaves and fifths of the root, so all consonant with every note
in the vocabulary — and a noise bloom at 78% of the chord's peak. That is the
correction for the phone defect, and it is also simply what Phase 4's white
detonation looks like: a full spectrum.

### The unlock

Three layers, and the middle one is why it does not sound like another note:

* a glide from the tile that was just struck up to the top of the register,
  with a fifth and an octave gliding in parallel;
* a noise swell whose low-pass cutoff opens from 500 Hz to 8 kHz over the cue —
  a filter opening;
* one 20 ms low knock at the head of it, for the flare.

The glide **swells** rather than decays, and its rise is exactly as long as the
`unlocking` segment, so it tops out as the gate finishes retracting and the
ball is let go. Written the ordinary way — a struck envelope on a rising sweep
— only 8.9% of its energy was above 500 Hz and the arena changed state in
silence on a phone.

### The release

The one cue in the piece that is not an impact: the root triad with a 50 ms
attack, an air layer at 900–6500 Hz that follows the ball out, and a pan at
half depth toward the frame edge the ball actually exits through. It arrives by
growing rather than by being struck, which is what makes it read as a
resolution rather than as one more collision, and it decays into **exact
digital silence** with 0.20 s of video still to run.

---

## 7. Density

The run produces 4.8 to 6.1 contacts a second. Two dampers, both computed in
the score so they are in the machine-readable schedule and a test can read
them:

| damper | rule | does it fire? |
|---|---|---|
| re-strike | a tile struck again inside 0.32 s is damped toward 0.46 | **no** |
| density duck | a duplicate arriving in a crowd is pulled down, floor 0.55 | **yes** |

**The re-strike damper is inert at this configuration, and this report says so
rather than presenting it as work being done.** At gravity 0 on a
seventeen-gon at 85 wu/s the ball does not come back to a tile it has just
left: over the five rendered seeds the shortest interval between two contacts
on one tile is **0.44 s**. It is kept for the same reason Phase 4 kept its two
almost-inert pacing guards — "no fast re-strikes" is a property of *this*
arena, speed and gravity, and a change to any of the three could produce one —
and it is tested on a synthetic contact rather than left unexercised.


---

## 8. The confirmation hold

The brief asks one question here — does contrast before the unlock make the
payoff stronger? — and it is answered with a curve rather than an adjective.
`tile_audio.confirmation_profile` walks the 0.92 s pause in 60 ms bins and
reports the level of each, so the three treatments can be put side by side.

Seed 3530, RMS per bin, dBFS. The detonation is at the left; the gate flares at
bin 11.

| | detonation | ← the confirmation → | the unlock |
|---|---|---|---|
| **A `resonant`** | −13.3 | −12.4 −14.2 −15.8 −17.0 −18.2 −19.4 −20.6 −21.9 −22.8 −23.3 | −23.5 −21.4 −19.4 −17.0 −15.8 |
| **B `breath`** | −14.1 | −15.9 −21.2 −26.1 −30.0 −34.5 −38.5 −42.5 −46.5 −50.0 | −33.4 −28.7 −22.9 −19.8 −17.5 −15.9 |
| **C `drone`** | −13.6 | −13.7 −16.9 −19.7 −21.5 −23.2 −25.1 −25.9 −27.1 −27.8 | −27.4 −25.7 −21.8 −20.4 −17.3 −15.9 |

| | quietest bin | at the unlock | **contrast** |
|---|---|---|---|
| A `resonant` — the final hit rings through | −23.3 dBFS | −15.8 dBFS | **+7.5 dB** |
| B `breath` — decay, then near-silence | −50.0 dBFS | −15.9 dBFS | **+34.1 dB** |
| C `drone` — a restrained low sustain | −27.8 dBFS | −15.9 dBFS | **+11.9 dB** |

The three are well separated, which is what makes the comparison worth
anything, and every other dial is identical — a test compares the three
configurations field by field and asserts that `confirmation` is the only one
that differs.

**What the numbers say.**

* **B empties the pause.** −50 dBFS is below the noise floor of any room or
  phone a Short is watched on, so for about 0.18 s there is nothing there at
  all. That is the brief's own warning — "total silence may also feel like an
  audio failure" — arriving as a measurement rather than as a worry.
* **A never gets out of the way.** The detonation's tail falls only 10 dB
  across the whole pause, and the unlock has to rise out of it into 7.5 dB of
  room.
* **C is the middle, and it is a deliberate middle.** The low sustain puts a
  floor at −27.8 dBFS — quiet enough that the pause reads as a pause, present
  enough that the audio has not failed — and leaves the unlock 11.9 dB to
  arrive out of.

**The recommendation is C, `drone`, and it is a recommendation rather than a
finding.** The measurements rank the three on contrast and on how much room the
unlock is given; they cannot say which of 7.5, 11.9 and 34.1 dB a viewer
prefers. That needs ears, and section 11 says plainly that nobody has listened
to these files yet. `v2_refined` stays the default in the code because it is
the configuration every other measurement in this report was taken on;
switching it is one line in `DEFAULT_CONFIG` once someone has heard all three.

---

## 9. Preview variants, seed 3530

Four renders, and the controlled part is that **all four carry the same
picture**. `mux` copies the video stream out of Phase 4's
`climax_seed3530.mp4` with `-c:v copy`, and the four previews hash identically:

```
MD5=f1bee6b7f30366d83ee94c1acae9ac0a  climax_seed3530.mp4  (Phase 4, silent)
MD5=f1bee6b7f30366d83ee94c1acae9ac0a  preview_seed3530_v1_basic.mp4
MD5=f1bee6b7f30366d83ee94c1acae9ac0a  preview_seed3530_v2_refined.mp4
MD5=f1bee6b7f30366d83ee94c1acae9ac0a  preview_seed3530_v2_hold_breath.mp4
MD5=f1bee6b7f30366d83ee94c1acae9ac0a  preview_seed3530_v3_hold_drone.mp4
```

Not one pixel differs between the four, or between them and the silent clip
Phase 4 judged. The only variable is the sound.

| | **V1 `v1_basic`** | **V2 `v2_refined`** | V2 + hold B | **V3 `v3_hold_drone`** |
|---|---|---|---|---|
| pitch mapping | `tile % 11`, spatially meaningless | by height in the arena | by height | by height |
| stereo | mono | by tile x, ±0.45 | ±0.45 | ±0.45 |
| progression | none | brightness, weight, late fifth | same | same |
| confirmation hold | B `breath` | A `resonant` | B `breath` | C `drone` |
| sample peak dBFS | −1.83 | −1.39 | −1.83 | −1.83 |
| true peak dBTP | −1.69 | −1.34 | −1.66 | −1.49 |
| integrated LUFS | −18.34 | −18.59 | −18.99 | −18.87 |
| LRA LU | 8.69 | 8.15 | 7.83 | 8.00 |
| new over duplicate | +11.3 dB | **+12.5 dB** | +12.5 | +12.5 |
| final over new | +7.4 dB | +6.3 dB | +6.3 | +6.3 |
| phone new over duplicate | +13.3 dB | **+15.0 dB** | +15.0 | +15.0 |
| phone final over new, RMS | +6.4 dB | +6.8 dB | +6.0 | **+7.0 dB** |
| channel correlation | 1.000 (mono) | 0.915 | 0.908 | 0.910 |
| pause contrast | +33.6 dB | +7.5 dB | +34.1 dB | +11.9 dB |
| clipped samples | 0 | 0 | 0 | 0 |

**V1 against V2 is a fair comparison and the numbers say so**: the two sit
within 0.3 LUFS and 0.6 LU of each other, so what separates them is structure
and not level. V1's `tile % 11` mapping is exactly as deterministic and exactly
as stable per tile; what it is not is *spatial*, and a test pins the
difference — under the shipped mapping no two neighbouring tiles are more than
one step of the vocabulary apart, and under V1's some are seven. V1 is also
mono by construction, so the arena has no width in it.

The measurable case for V2 over V1 is narrower than the design case: +1.2 dB of
separation between a new hit and a duplicate, and +1.7 dB of it on a phone. The
rest of what V2 buys — that the ring has a shape, that the ball's position is
in the stereo field, that the run opens up as it fills — does not reduce to a
decibel, and that part needs ears.

---

## 10. Seed 3530, end to end

`preview_seed3530_v2_refined.mp4` — 1,038 frames, 34.600 s, 1080×1920, 30 fps,
H.264 copied from Phase 4, AAC 192 kbps.

**The shape of the run.** 158 contacts: 50 activations, one final, 107
duplicates, at 4.93 events a second. The median gap between two events is
0.200 s and the longest is 0.600 s, so there is never a hole. The last 3.83 s
before the detonation is the final hunt — **eighteen duplicates and no
activation at all** — and this is where the design does the most work without
having been asked to: the duplicate's gain is fixed for the whole run while the
activation's has been climbing, so the final hunt arrives as a sudden drop in
reward. The arena keeps talking and stops saying anything, which is exactly
what 50 of 51 means.

**The tail of the event stream**, as the score writes it:

```
 31.6000s f 948  duplicate   tile 46   261.6 Hz  gain 0.088  pan -0.301
 31.8000s f 954  duplicate   tile 30   880.0 Hz  gain 0.088  pan -0.188
 31.9667s f 959  duplicate   tile 17   587.3 Hz  gain 0.088  pan +0.414
 32.1667s f 965  final       tile 50   220.0 Hz  gain 0.760  pan -0.109
 32.7667s f 983  unlock      tile 50   220.0 Hz  gain 0.360  pan +0.000
 33.0667s f 992  escape            --  220.0 Hz  gain 0.440  pan +0.001
```

Seed 3530's last tile is at the bottom of the ring, so its note **is** the
root, and the ending resolves on the pitch it detonated on. The escape's pan is
+0.001 because the ball leaves through the top of the frame almost dead
centre — the pan is taken from the exit position, so it reports the diagonal
escape this seed was chosen for.

**The detonation lands out of silence.** The contact before it is 0.20 s
earlier and a duplicate's cue is 0.11 s long, so there are 90 ms of digital
silence immediately before the fifty-first tile. That is luck of this seed's
final gap rather than design, and it is recorded because it is part of why this
particular ending reads.

**Audio-visual correspondence, beat by beat:**

| what the viewer sees (Phase 4) | frame | what they hear |
|---|---|---|
| a duplicate: brightness only, no motion | its own | the tile's note, 110 ms, dark, −21 dB |
| a tile lights: brightness plus a 0.30 wu recoil | its own | the same note opened out, 620 ms, −9 dB |
| the 51st tile: white, +11.0 emission, a shock ring | 965 | the same note as a chord over the key, 1.70 s, −2.4 dB |
| the confirmation wave crosses the ring | 969–983 | the detonation ringing down 10 dB |
| the gate flares cyan and retracts | 983 | a rise from that note to the top of the register, and a filter opening |
| the ball is released | 992 | the root triad, swelling |
| the open arena, held | 1022 | decay |
| the last frame | 1037 | exact digital silence, for 0.21 s |

**Measured, for this file:** sample peak −1.39 dBFS, true peak −1.34 dBTP, zero
clipped samples, the limiter never engaged, −18.59 LUFS integrated with 8.2 LU
of range, at most four voices sounding at once, 20.9% of the timeline below
−60 dBFS with the longest quiet stretch 0.21 s (the closing silence), 0.49% of
the energy above 4 kHz, and 0.19 dB of level lost folding to mono at a channel
correlation of 0.915.

---

## 11. What has *not* been verified

Stated plainly, because the decision depends on it.

**Nobody has listened to any of these files.** Every claim in this report is a
measurement, a spectral reading, a waveform inspection or an argument from the
design. Three of the brief's eight gate criteria — that an arbitrary collision
order is *pleasant*, that the payoff is *coherent*, that the pause *feels*
intentional — are judgements an ear makes, and the instruments here can only
bound them:

* *pleasant under arbitrary order* is bounded by the scale. All fifty-five
  intervals between the eleven pitches are checked and none is a semitone or a
  tritone in any inversion, so no pair the ball can produce is dissonant. That
  is a proof about the note set, not a verdict about the result.
* *a coherent payoff* is bounded by levels and timing: the three beats land on
  their exact frames, each clears an ordinary activation on the master and on a
  phone, and the ending resolves on the key.
* *the pause feels intentional* is bounded by section 8's three curves, which
  say how much contrast each treatment provides and not which one is wanted.

The four seed-3530 previews exist precisely so that one listening pass settles
all three at once, and that pass is the first item in section 16.

---

## 12. Secondary-seed validation

Four more pacing-gate-valid seeds, all taken from the Phase 2 shortlist and the
Phase 4 cast rather than from a new search, chosen to vary what the audio
actually depends on: contact density, run length, and where the last tile is.

| seed | why it is here | run | contacts | /s | final tile | its pitch |
|---|---|---|---|---|---|---|
| **3530** | the brief's reference | 32.14 s | 158 | 4.93 | 50, at the bottom | 220.0 Hz — the root |
| **26267** | the fastest and sparsest valid run | 30.30 s | 145 | 4.80 | 39 | 440.0 Hz |
| **37169** | **the densest** valid run; a 4.42 s approach | 32.16 s | 194 | 6.06 | 22, high in the ring | 784.0 Hz |
| **6132** | the **slowest** valid run; a 4.02 s final hunt | 33.11 s | 179 | 5.42 | 47 | 261.6 Hz |
| **7541** | the longest approach and final hunt pair, 4.13 s and 3.90 s | 31.20 s | 155 | 4.99 | 5 | 261.6 Hz |

The final-tile pitch spread — 220 to 784 Hz — is what this selection is for.
It is the evidence that the detonation states the same chord whichever tile
happens to be last, rather than only working on the seed it was tuned on.

| seed | peak dBFS | true peak | LUFS | LRA | voices | new>dup | final>new | phone final>new RMS | >4 kHz |
|---|---|---|---|---|---|---|---|---|---|
| 3530 | −1.39 | −1.34 | −18.59 | 8.2 | 4 | +12.46 | +6.28 | +6.75 | 0.48% |
| 26267 | −1.83 | −1.59 | −18.87 | 7.6 | 4 | +12.41 | +6.33 | +6.24 | 0.26% |
| 37169 | −1.95 | −1.90 | −18.55 | 9.9 | **6** | +12.57 | +6.05 | +6.97 | 0.48% |
| 6132 | −1.83 | −1.30 | −18.44 | 9.8 | 5 | +12.45 | +6.29 | +5.83 | 0.40% |
| 7541 | −1.83 | −1.30 | −18.16 | 11.0 | 4 | +12.56 | +6.18 | +6.26 | 0.49% |

The hierarchy holds to within half a decibel across all five: new over
duplicate spans 12.41 to 12.57 dB, and final over new 6.05 to 6.33 dB. Nothing
clips anywhere and the limiter engages on nothing. Loudness spans 0.7 LUFS,
which is exactly the variation a fixed master gain is meant to leave in — a
busier seed is louder, and it stays louder.

**Where the density does show up** is polyphony. Seed 37169 at 6.06 contacts a
second reaches six simultaneous voices against four on the two sparsest seeds,
and it is the only seed where the 30 fps frame grid ever puts two contacts on
one frame — three times out of 196 events, the worst pair 26.4 ms apart. That
is a real cost of placing audio on frames, and it is a cost the *picture*
already pays: those two contacts are drawn on the same frame too, so the sound
still matches what is on screen exactly. Over all five seeds it is 3 events in
841, or 0.36%.

---

## 13. Measurements

Every number below is in `output/category3_v5/audio/seed_*_*.measure.json`.

### Levels and clipping

| | requirement | seed 3530 | worst of five |
|---|---|---|---|
| sample peak | ≤ −1.3 dBFS (`audio.soundtrack.PEAK_CEILING_DBFS`) | −1.39 | −1.39 |
| true peak, master | ≤ −1.0 dBTP | −1.34 | −1.30 |
| true peak, **encoded AAC** | ≤ −1.0 dBTP | −1.41 | −1.41 (of all eight) |
| clipped samples, above 1.0 | 0 | 0 | 0 |
| samples above the ceiling | 0 | 0 | 0 |
| limiter gain reduction | — | 0.00 dB | 0.00 dB |

The repository already has an audio standard and Phase 5 adopts its numbers
rather than inventing new ones: the PCM master sits at −1.3 dBFS, which is the
delivery figure of −1.0 dBTP less the 0.3 dB `audio/soundtrack.py` measured as
the reserve for AAC's inter-sample overshoot at 192 kbps. **`verify` does not trust that reserve** — it decodes the finished
MP4 and measures what came out. Across the eight previews the encoded true peak
ranges −1.41 to −1.83 dBTP, so the reserve was not merely adequate, it was
never called on.

The master gain is a single static 0.55 dB, chosen so that the loudest raw mix
of the five seeds (0.7999) lands just under the ceiling. **The limiter did not
act on anything rendered in this phase**, which is what makes "an event's peak
in the mix is its configured gain" true rather than nearly true.

### Density and polyphony

| | 3530 | across five seeds |
|---|---|---|
| events | 160 | 147 – 196 |
| events per second | 4.93 | 4.80 – 6.06 |
| max simultaneous voices, above −50 dBFS | 4 | 4 – 6 |
| max scheduled envelope overlap | 4 | 4 – 6 |
| shortest gap between events | 0.133 s | 0.000 – 0.133 s |
| median gap | 0.200 s | 0.167 – 0.200 s |
| longest gap | 0.600 s | 0.600 – 0.633 s |
| below −60 dBFS | 20.9% | 19 – 23% |
| longest silence | 0.214 s | 0.214 s, every seed — the closing silence |
| energy above 4 kHz | 0.49% | 0.26 – 0.51% |

### Masking — does an event clear what is already sounding?

The reading that matters most for the brief's second criterion, and the one a
level table cannot give. `emergence` is the energy in a 55 ms window at the
cue's own peak, over the same-length window immediately before the event
started.

Seed 3530, `v2_refined`:

| | n | median | p05 | min | under 3 dB |
|---|---|---|---|---|---|
| duplicate | 107 | +15.4 dB | −1.6 | −3.9 | **35** |
| activation | 50 | +9.2 dB | +5.1 | **+3.7** | **0** |
| the detonation | 1 | out of silence (+68 dB against the −80 dBFS floor) | | | 0 |
| the unlock | 1 | +11.7 dB | | | 0 |
| the release | 1 | +4.6 dB | | | 0 |

**Every one of the fifty activations clears the bed under it**, the weakest by
3.7 dB. A third of the duplicates do not, and that is correct: a duplicate is
supposed to sit inside the texture, not step out of it.

Across all five seeds the picture holds except at the top of the density range:

| seed | /s | median | p05 | under 3 dB, master | under 3 dB, phone |
|---|---|---|---|---|---|
| 3530 | 4.93 | +9.2 dB | +5.1 | 0 of 50 | 5 of 50 |
| 26267 | 4.80 | +9.9 dB | +4.9 | 0 of 50 | 10 of 50 |
| **37169** | **6.06** | +8.5 dB | **+1.2** | **9 of 50** | 11 of 50 |
| 6132 | 5.42 | +8.4 dB | +3.9 | 1 of 50 | 8 of 50 |
| 7541 | 4.99 | +8.1 dB | +4.5 | 1 of 50 | 8 of 50 |

**This is the one measurement in the phase that is not comfortable, and it is
reported rather than smoothed.** On the densest pacing-valid seed nearly one
activation in five does not clearly separate from the duplicates around it, and
through a phone speaker eight to eleven of fifty do so on every seed. The
median is healthy everywhere — +8.1 to +9.9 dB on the master — so this is a
tail, not a norm, and nothing about it clips, masks the climax or moves the
hierarchy. It is a refinement for Phase 6 (section 16), not a defect that
changes this phase's decision: the obvious fix is a very short duck of the
duplicate bed around an activation, which is a change to the score and costs
nothing structural.

### Synchronisation

| | |
|---|---|
| events checked | 160 on seed 3530; 841 across five seeds |
| frame mismatches | **0** |
| agreement with `tile_playback.activation_frames` | **exact**, all five seeds |
| placement error | **0.0 s — exactly zero** |
| mean frame lead | 16.2 ms |
| max frame lead | 32.8 ms |

The placement error is not "small", it is zero: at 48 kHz and 30 fps a frame is
exactly 1,600 samples, so every cue lands on an integer sample and there is
nothing to round. It is the same arithmetic `audio/soundtrack.py` relies on at
48000/60, holding at 48000/30.

The frame lead is the distance from an event's canonical instant to the frame
that first shows it. It is a property of sampling a continuous run at 30 fps and
it exists with or without audio; the sound is placed on the frame, so the
viewer sees and hears the same thing at the same moment and the A/V discrepancy
is the zero above. The brief's budget is approximately one frame; this is four
orders of magnitude inside it.

### Phone playback

Measured through `audio/loudness.py`'s `phone_filter` — a mono fold and a
second-order high-pass at 500 Hz. It is not a model of a speaker; it is a way of
asking what survives one.

| | master | phone |
|---|---|---|
| integrated | −18.59 LUFS | −23.07 LUFS |
| new over duplicate, peak | +12.5 dB | +15.0 dB |
| final over new, RMS | +4.9 dB | +6.8 dB |
| the unlock, over an ordinary activation | +3.7 dB | +3.8 dB |
| the escape, over an ordinary activation | +3.8 dB | +3.8 dB |

Everything that carries meaning is **louder relative to the bed on a phone than
on the master**, because the corrections in sections 4 and 6 moved the weight of
every important cue above 500 Hz and left the duplicate — the one event that is
supposed to recede — below it. Folding to mono costs 0.19 dB at a channel
correlation of 0.915, with no frequency band losing more than a tenth of a
decibel, which is what amplitude panning and nothing else in the signal path
should give.

---

## 14. Outputs

All under the un-gitted `output/category3_v5/`.

### Preview MP4s

1080×1920, 30 fps, H.264 CRF 17, **AAC 192 kbps stereo at 48 kHz**.

| file | what it is | video source |
|---|---|---|
| `preview_seed3530_v1_basic.mp4` | V1 — the event hierarchy alone | copied from Phase 4 |
| `preview_seed3530_v2_refined.mp4` | **V2 — the recommendation** | copied from Phase 4 |
| `preview_seed3530_v2_hold_breath.mp4` | V2 with confirmation hold B | copied from Phase 4 |
| `preview_seed3530_v3_hold_drone.mp4` | V3 — V2 with confirmation hold C | copied from Phase 4 |
| `preview_seed26267_v2_refined.mp4` | secondary — fastest, sparsest | encoded from frames |
| `preview_seed37169_v2_refined.mp4` | secondary — densest | encoded from frames |
| `preview_seed6132_v2_refined.mp4` | secondary — slowest | encoded from frames |
| `preview_seed7541_v2_refined.mp4` | secondary — longest approach | encoded from frames |

The four seed-3530 files carry a video stream that is **bit-identical** to
Phase 4's `climax_seed3530.mp4` — section 9 has the hashes — so the variant
comparison has exactly one variable in it. The four secondary seeds were
rendered fresh in Godot for this phase at the locked Phase 3 presentation and
the `standard` climax timing.

These are previews. **No upload master was made**, as instructed.

### Audio and evidence

| path | what |
|---|---|
| `audio/seed_*_*.wav` | the PCM masters, 24-bit stereo at 48 kHz |
| `audio/seed_*_*.measure.json` | every measurement in section 13, per render |
| `audio/seed_*_*.decoded.wav` | the AAC audio decoded back out of each preview, for the encoded true-peak check |
| `score/seed_*_*.json` | **the machine-readable audio schedule** — every event with its kind, render instant, frame, gain, pan, pitch and the damping applied to it |
| `sync/seed_*_*.json` | the A/V synchronisation report, per seed |
| `playback/seed_*_standard.json` | Phase 4 playback documents with completion blocks, re-exported here |
| `climax30_standard/seed_*/` | the frame sequences for the four secondary seeds |
| `compare_seed*.json` | the tabulated comparisons |

### Reproducing

```
$env:GODOT_BIN = "...\Godot_v4.7.2-stable_win64_console.exe"
python -m satisfying.tile_phase5_cli export  --seeds 3530 26267 37169 6132 7541
python -m satisfying.tile_phase5_cli score   --seeds 3530 --config v2_refined
python -m satisfying.tile_phase5_cli render  --seeds 3530 --config v2_refined
python -m satisfying.tile_phase5_cli sync    --seeds 3530 --config v2_refined
python -m satisfying.tile_phase5_cli climax  --seeds 26267 37169 6132 7541 --fps 30
python -m satisfying.tile_phase5_cli mux     --seeds 3530 --config v2_refined \
    --video output/category3_v4/climax_seed3530.mp4
python -m satisfying.tile_phase5_cli mux     --seeds 26267 37169 6132 7541 --config v2_refined
python -m satisfying.tile_phase5_cli verify  --seeds 3530 --config v2_refined
python -m satisfying.tile_phase5_cli compare --seeds 3530
```

Rendering a master is about 30 seconds of pure Python for a 35-second piece;
the Godot climax renders are Phase 4's 124 ms a frame, and Phase 3's and Phase
4's warning still applies — **do not run the suite and a Godot render at the
same time**.

---

## 15. Determinism

Stated against a pair — a seed and an `AudioConfig` — and checked at three
levels by `tile_phase5_cli verify`, on every one of the eight renders:

| | how it is checked | result |
|---|---|---|
| the run | the document is re-simulated and compared digest, activation order, activation times, completion and contact count | **OK**, 8 of 8 |
| the schedule | built twice and compared as sorted JSON, then fingerprinted | **OK**, 8 of 8 |
| the waveform | rendered twice and the 24-bit PCM compared by SHA-256 | **OK**, 8 of 8 |
| the encoded file | the MP4's audio decoded back and measured | **OK**, 8 of 8, −1.41 to −1.83 dBTP |

Everything that could move a sample is a field on `AudioConfig` — including
`fps`, because the frame grid decides where cues land, and `sample_rate`,
because it decides how they are quantised — and `AudioConfig.fingerprint()` is
a digest over all of them. Noise is `audio/synthesis.py`'s SplitMix64 seeded
from `stable_seed` on the note's own frequency, never from a clock, a process
hash or an event index, so the same tile's tick is the same bytes in every run.

The eight PCM digests are all different, which is the other half of the claim:
two configurations that should sound different do.

```
c99dac11adfdd848  3530 v1_basic          cd814ad2f6531bae  26267 v2_refined
8861c478eb78453e  3530 v2_refined        a1f6ea9bbd206aab  37169 v2_refined
2af7b8eb13874f91  3530 v2_hold_breath    38c83908a469189c  6132  v2_refined
665ce1cdfedf37ae  3530 v3_hold_drone     0b2851e0b0ad7c8c  7541  v2_refined
```

**The audio cannot touch the run.** Three tests carry this:

* `schedule` and `render` do not mutate the document — the JSON is compared
  before and after;
* the document still passes `tile_playback.verify_document` after the audio has
  read it;
* `tile_score` imports no simulator and `tile_audio` imports no seed, asserted
  by reading the two module sources. That last one is the mechanical reason
  rather than the careful one.

---

## 16. Tests and regression

`tests/test_tile_escape_phase5.py` — **74 tests**, covering every item the
brief listed:

| the brief's requirement | tests |
|---|---|
| deterministic tile→pitch mapping | stable across two seeds with different collision orders, across repeat calls, and spatially coherent around the whole ring including the wrap |
| deterministic audio-event schedule | built twice and JSON-compared; built from two fresh simulations; four configurations give four distinct fingerprints |
| duplicate/new event hierarchy | asserted on the configured gains, on the rendered cues in isolation (peak, total energy, duration), on the finished master, and through `phone_filter`; an inverted configuration raises at construction |
| final tile event fires exactly once | one `final`, fifty `activation`, on the last contact, at the completion instant |
| completion audio uses the presentation timeline | every beat compared against `completion["timeline"]` by state name; the unlock and escape offsets compared against the timing preset |
| the 0.92 s pause does not collapse audio timing | the three held segments share one simulation instant and carry cues at three distinct render instants on three distinct frames |
| unlock at the correct completion offset | `gate_open_at_seconds` after the final hit, on its own frame |
| escape at the correct completion offset | `release_at_seconds` after the final hit, on its own frame |
| audio never mutates canonical data | the document is byte-compared before and after; it still verifies afterwards; the run is identical whether or not audio was built; the import graph is read from the source |
| output length matches the video timeline | `round(duration × fps) + 1` frames, asserted against Phase 4's actual 1,038 for seed 3530, and the buffer length asserted against it |
| no waveform clipping | zero clipped samples and nothing over the ceiling on every configuration of two seeds, plus a check that the master is not silent |
| stable export/digest | PCM digests equal across two renders, different across four configurations, and the configuration fingerprint moves with any of six dials |

Plus regressions for the six defects this phase produced — the detonation's
phone level, the gate's envelope, the truncated release, the backwards
progression, the window that measured the start of a swell, and the phase
dispersion that was measured and removed.

### Full-suite comparison

Both measured with `python -m pytest -q` on the committed tree.

| | failures | passed | skipped |
|---|---|---|---|
| `85c4e89` (Phase 4, as that report recorded it) | **18** | 5,937 | 440 |
| `e434fe5` (this branch, committed) | **18** | 6,012 | 440 |

**The two failure sets are byte-identical** — diffed, not eyeballed — so Phase 5
adds no failure and fixes none. The deltas account for themselves exactly:

```
5,937  Phase 4 passes
  +74  Phase 5 tests
   +1  test_category_three_uses_only_the_leaf_audio_modules, the new half of
       the boundary guard in section 2.1
-----
6,012
```

17 min 53 s, against Phase 4's 16 min 02 s.

**And a nineteenth failure was found and fixed on the way**, which is the part
worth recording. The first full run came back **19 failed / 6,010 passed**, and
the extra one was
`tests/test_tile_escape.py::test_category_three_imports_no_other_category_and_no_company_os`
— Phase 1's boundary guard, catching Phase 5's own import of
`audio/soundtrack.py`. Section 2.1 is what happened next. Per
[[suite-has-14-known-failures]] a failure above the base is real until proven
otherwise; this one was real, and the fix was to remove the dependency rather
than to widen the guard around it.


The eighteen are the fingerprint Phases 2, 3 and 4 all recorded: twelve stale
cross-workstream branch guards that diff `origin/main...HEAD` and reject
anything outside their own allowlist, and six open files under the un-gitted
`output/`. Neither group indicates a regression, and per Phase 4's note the
comparison that matters is against the base, not against any absolute number.

---

## 17. Decision

**AUDIO PROOF PASSED.**

Against the brief's eight criteria:

| criterion | evidence | verdict |
|---|---|---|
| collisions sound causally connected to visuals | every one of 841 contacts across five seeds has a cue on the exact frame that first draws it; 0 frame mismatches; 0.0 s placement error; the frame rule independently agrees with `tile_playback.activation_frames` | **measured, passes** |
| new activations are more rewarding than duplicates | +12.4 to +12.6 dB peak and +13.5 dB RMS on the master, +14.4 to +15.0 dB on a phone, +16 dB of cue energy, 5.6× the duration, a pitched body against a dark tick — and on four of five seeds at most one activation in fifty fails to clear 3 dB above the bed under it | **measured, passes, with the density caveat in section 13** |
| arbitrary collision order remains pleasant | all 55 intervals of the 11-note vocabulary are checked: no semitone, no tritone, in any inversion, so no pair the ball can produce is dissonant | **bounded, not heard** |
| audio density remains controlled | at most 4–6 simultaneous voices at 4.8–6.1 contacts a second; no clipping anywhere; the limiter never engaged; 19–23% of the timeline below −60 dBFS | **measured, passes** |
| final hit / unlock / escape form a coherent payoff | the three land on their exact frames; each clears an ordinary activation on the master and on a phone; the detonation states the key whichever tile is last, the unlock rises from that tile to the top of the register, the release resolves on the root triad and decays to exact silence | **measured for level and timing; coherence argued** |
| the confirmation pause feels intentional | the three treatments give 7.5, 11.9 and 34.1 dB of contrast and are cleanly separated; `drone` is recommended | **bounded, not heard** |
| synchronisation is correct | zero, exactly — 48000/30 is 1,600 samples, so no cue needs rounding | **measured, passes** |
| phone playback remains clear | everything that carries meaning is *louder* relative to the bed through `phone_filter` than on the master; the duplicate is the only thing that recedes | **measured, passes** |

**Five of the eight are settled by measurement. Three of them — pleasantness,
coherence and how the pause feels — are bounded by measurement and settled by
an ear, and no ear has heard these files.** Section 11 says so at length. The
decision is PASSED because no criterion failed, no defect is left open, and
every defect this phase found was fixed and given a regression; it is not a
claim that the soundtrack has been listened to and approved.

The one uncomfortable measurement — that on the densest pacing-valid seed nine
activations in fifty do not clearly separate from the bed — is in section 13,
is not hidden behind an average, and is the second item in section 18. It does
not change this decision: the median is healthy on every seed, nothing clips,
and the climax is untouched by it.

---

## 18. Recommendation for Phase 6

Not implemented here, as instructed.

1. **Listen to the four seed-3530 previews, in one sitting, in this order:**
   `v1_basic`, `v2_refined`, `v2_hold_breath`, `v3_hold_drone`. They share a
   bit-identical picture, so the comparison is exact. Three of the eight gate
   criteria and the choice of confirmation hold all resolve in that one pass,
   and nothing else in Phase 6 should start before it. If `drone` wins, the
   change is one line in `DEFAULT_CONFIG`.

2. **Duck the duplicate bed around an activation.** This is the one
   uncomfortable measurement in the phase: on the densest pacing-valid seed
   nine activations in fifty do not clear 3 dB above what is already sounding,
   and through a phone speaker eight to eleven of fifty do so on every seed.
   A very short duck — a few tens of milliseconds of the duplicates around each
   activation — is a change to `tile_score` alone, costs nothing structural,
   and would move the p05 rather than the median, which is exactly where the
   problem is. Measure it with `masking_report`, which already exists.

3. **Decide whether the activation progression is worth its complexity.** It
   is measurable — the spectral centroid rises monotonically from 2398 to
   2582 Hz and the energy by half a decibel — and it took two rounds of
   corrections to get the sign right. A listener should say whether 8% of
   brightness over thirty-two seconds is perceptible at all. If it is not, the
   three dials that drive it should come out rather than be kept for the
   diagram.

4. **The visual and the audio hierarchies are now separately tunable and should
   be checked together.** Phase 4 set brightness, brightness-plus-motion and a
   white detonation; Phase 5 set −21, −9 and −2 dBFS. Nothing forces them to
   stay in step, and a test asserts each side alone. A Phase 6 change to either
   should re-check the other.

5. **One thing that is *not* worth doing**: a wider musical vocabulary. Eleven
   notes over fifty-one tiles is what makes the arena sound like one
   instrument, and the mapping test — no two neighbouring tiles more than one
   step apart — is only satisfiable because the vocabulary is small relative to
   the ring. Adding notes would break that property before it added anything.

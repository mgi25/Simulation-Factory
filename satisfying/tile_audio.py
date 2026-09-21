"""The sound: one schedule to one stereo master, and the numbers to judge it.

The third of three layers. `tile_playback` and `tile_completion` publish what
happened; `tile_score` decides what is heard and when; this module is the only
one that produces samples, and it consumes a schedule and an arena and nothing
else. It cannot reach the physics, it cannot reach a seed and it never
re-simulates anything - which is the mechanical reason the soundtrack cannot
alter the run underneath it.

## Everything here is original

Every sample comes out of `audio.synthesis`: oscillators, envelopes, one-pole
filters and a SplitMix64 noise source seeded from stable facts. No samples, no
loops, no packs, no libraries, nothing licensed. The primitives are the
project's own, already used by the race soundtracks, and Phase 5 adds cues
rather than a second synthesiser.

## What a cue is, and why it is normalised before it is placed

A cue is a mono buffer, peak-normalised to 1.0 and then multiplied by the
event's gain. That order is the hierarchy: an event's peak in the mix *is* its
gain, whatever the partials inside it happened to sum to, so a duplicate at
0.098 and an activation at 0.300 are 9.7 dB apart by construction and stay that
way. Nothing downstream normalises an event on its own. The master is a single
static gain and a look-ahead limiter behind it - no compressor - because a
compressor would pull the detonation down toward the duplicates and the
hierarchy is the whole design.

## The five strengths, as sound

| event        | the idea                                                     |
|--------------|--------------------------------------------------------------|
| `duplicate`  | the tile's own note, muted and short, with a quiet tick on it |
| `activation` | the same note, opened out: octave, twelfth, longer tail       |
| `final`      | the same note again, as a chord over the key's root           |
| `unlock`     | that note sweeping up to the top of the register, and a gate  |
| `escape`     | the root triad, swelling and decaying into silence            |

A duplicate and an activation on the same tile are the *same fundamental*: same
wall, same note, different emphasis. That is what makes progress audible without
having to be taught - the arena does not change what it says, only how much of
it it says.

## Phone speakers

A phone reproduces almost nothing below about 500 Hz, so nothing load-bearing
lives there. The lowest note in the vocabulary is 220 Hz and every cue that uses
it carries its octave and twelfth, and every impact carries a short band-limited
tick between 1.4 and 7 kHz. `measure` reports what survives `phone_filter`, and
the activation-over-duplicate ratio is measured there as well as on the master.
"""

from __future__ import annotations

import math
import os
from array import array
from collections import deque
from dataclasses import dataclass
from typing import Any, Sequence

from audio.synthesis import (
    CHANNELS,
    DEFAULT_RELEASE,
    db_to_gain as _db_to_gain,
    SAMPLE_RATE,
    add_into,
    db_to_gain,
    envelope,
    gain_to_db,
    high_pass,
    low_pass,
    noise_burst,
    normalise_peak,
    peak,
    rms,
    scale,
    seconds_to_samples,
    silence,
    stable_seed,
    tone,
)
from audio.wav_io import DEFAULT_BIT_DEPTH, sha256_hex, pcm_bytes, write_wav
from satisfying.tile_score import (
    AudioConfig,
    AudioEvent,
    AudioSchedule,
    DEFAULT_CONFIG,
    ScoreError,
    schedule as build_schedule,
)

__all__ = [
    "AUDIO_RENDER_VERSION",
    "PEAK_CEILING",
    "PEAK_CEILING_DBFS",
    "DELIVERY_PEAK_DBFS",
    "master",
    "pan_gains",
    "AudioError",
    "RenderedAudio",
    "cue_for",
    "cue_profile",
    "confirmation_profile",
    "masking_report",
    "tilt_for",
    "render",
    "render_document",
    "write_master",
    "measure",
]

# Changes when the same schedule would produce different samples.
AUDIO_RENDER_VERSION = 1

# What counts as a voice still sounding, for the polyphony reading: 50 dB below
# the loudest thing in the piece. Below that a cue is not masking anything and
# not adding to the density the brief is asking about.
VOICE_FLOOR_DB = -50.0
# What counts as silence, for the silence reading.
SILENCE_FLOOR_DB = -60.0
# The window a per-event level is measured in. Long enough to contain an
# attack and the first part of a decay, short enough that the next event at
# four to six a second is usually not in it.
EVENT_WINDOW_SECONDS = 0.055


# --------------------------------------------------------------------------
# The master stage, and why it is here rather than imported
# --------------------------------------------------------------------------
#
# `audio/soundtrack.py` has a `master`, a `pan_gains` and these two constants
# already, and Phase 5's first draft imported them. It does not any more, and
# the reason is a Phase 1 guard rather than a preference:
# `test_category_three_imports_no_other_category_and_no_company_os` holds the
# workstream boundary, and `audio/soundtrack.py` opens with `from audio import
# cues` - the battle cue library. Importing three generic functions out of it
# would have dragged another workstream's sound design into Category 3's
# import graph to get them.
#
# So the three leaf modules Category 3 does use - `audio/synthesis.py`,
# `audio/wav_io.py` and `audio/loudness.py` - import nothing but the standard
# library and numpy, which the guard now asserts transitively, and the sixty
# lines below are the price of that. They are a deliberate second copy of a
# known algorithm, not a second design: the limiter's construction is the same
# one `audio/soundtrack.master` proves, and the numbers are the repository's.

# What the finished MP4 must not exceed, as a true peak, and what the PCM
# master is therefore allowed to reach. The 0.3 dB between them is the
# reserve `audio/soundtrack.py` measured for AAC's inter-sample overshoot at
# 192 kbps; `tile_phase5_cli verify` decodes the encoded file and checks it
# rather than trusting it.
DELIVERY_PEAK_DBFS = -1.0
CODEC_OVERSHOOT_DB = 0.3
PEAK_CEILING_DBFS = DELIVERY_PEAK_DBFS - CODEC_OVERSHOOT_DB
PEAK_CEILING = _db_to_gain(PEAK_CEILING_DBFS)
# Look-ahead and release of the safety limiter, as one radius.
LIMITER_RADIUS_SECONDS = 0.024


def pan_gains(pan: float) -> tuple[float, float]:
    """Channel gains for a pan position in [-1, 1].

    The usual equal-power law - cosine and sine of a quarter turn -
    renormalised so the nearer channel always gets the cue's full designed
    level. Cue levels here are budgeted as peaks, and dividing by the larger
    gain is what keeps that budget true.
    """
    pan = max(-1.0, min(1.0, pan))
    angle = (pan + 1.0) * math.pi / 4.0
    left = math.cos(angle)
    right = math.sin(angle)
    largest = max(left, right)
    if largest <= 0.0:
        return 1.0, 1.0
    return left / largest, right / largest


@dataclass(frozen=True)
class MasterReport:
    """What the master stage found, and what it had to do about it."""

    peak_before: float
    peak_after: float
    limiter_gain: float
    limited: bool
    makeup_gain: float = 1.0


def _sliding_min(values: array, radius: int) -> array:
    """Minimum of every window [i - radius, i + radius], clipped at the ends."""
    length = len(values)
    out = silence(length)
    window: deque[int] = deque()
    filled = 0
    for index in range(length):
        while filled <= min(length - 1, index + radius):
            while window and values[window[-1]] >= values[filled]:
                window.pop()
            window.append(filled)
            filled += 1
        while window[0] < index - radius:
            window.popleft()
        out[index] = values[window[0]]
    return out


def _boxcar(values: array, radius: int) -> array:
    """Mean of every window [i - radius, i + radius], clipped at the ends."""
    length = len(values)
    out = silence(length)
    prefix = [0.0] * (length + 1)
    for index in range(length):
        prefix[index + 1] = prefix[index] + values[index]
    for index in range(length):
        start = max(0, index - radius)
        end = min(length, index + radius + 1)
        out[index] = (prefix[end] - prefix[start]) / (end - start)
    return out


def master(left: array,
           right: array,
           *,
           ceiling: float = PEAK_CEILING,
           radius_seconds: float = LIMITER_RADIUS_SECONDS,
           sample_rate: int = SAMPLE_RATE,
           makeup_db: float = 0.0) -> MasterReport:
    """One static gain, then a look-ahead limiter, then an exact clamp.

    There is no compressor, and that is the design: a compressor pulls the
    loudest moments down toward the quietest, and the distance between the
    detonation and a duplicate is the whole of Phase 5's hierarchy. A static
    gain cannot change any relationship in the mix at all.

    The limiter is a safety net that, on everything this phase rendered, did
    nothing - the static gain is chosen so the loudest raw mix of the five
    seeds lands under the ceiling. It is kept because a future seed could be
    louder, and its gain envelope is built in two passes: a sliding minimum of
    the gain each sample needs, then a moving average of that over the same
    radius. The order is the proof - every minimum inside the averaging window
    already accounts for the loudest sample at its centre, so the average can
    never exceed what that sample needs, and no sample can slip through above
    the ceiling.

    Both stages are applied identically to the two channels, so nothing here
    moves the stereo image.
    """
    peak_before = max(peak(left), peak(right))
    if peak_before <= 0.0:
        return MasterReport(peak_before, peak_before, 1.0, False)

    applied = 1.0
    if makeup_db:
        applied = _db_to_gain(makeup_db)
        scale(left, applied)
        scale(right, applied)

    limiter_gain = 1.0
    limited = False
    current = max(peak(left), peak(right))
    if current > ceiling:
        limited = True
        length = len(left)
        needed = silence(length)
        for index in range(length):
            loudest = max(abs(left[index]), abs(right[index]))
            needed[index] = 1.0 if loudest <= ceiling else ceiling / loudest

        radius = max(1, seconds_to_samples(radius_seconds, sample_rate))
        envelope_gain = _boxcar(_sliding_min(needed, radius), radius)
        for index in range(length):
            gain = envelope_gain[index]
            left[index] *= gain
            right[index] *= gain
            if gain < limiter_gain:
                limiter_gain = gain

    # The proof above holds in real arithmetic; in float the two passes can
    # leave a couple of parts in a million million above the ceiling. That is
    # 230 dB down and quantises to the same integer either way, but "no sample
    # is above the ceiling" is worth being true rather than nearly true. It is
    # a rounding backstop, not a stage: if it ever had real work to do, the
    # limiter above it would be broken.
    for index in range(len(left)):
        value = left[index]
        if value > ceiling:
            left[index] = ceiling
        elif value < -ceiling:
            left[index] = -ceiling
        value = right[index]
        if value > ceiling:
            right[index] = ceiling
        elif value < -ceiling:
            right[index] = -ceiling

    return MasterReport(
        peak_before=peak_before,
        peak_after=max(peak(left), peak(right)),
        limiter_gain=limiter_gain,
        limited=limited,
        makeup_gain=applied,
    )


class AudioError(RuntimeError):
    """A schedule that cannot be rendered."""


# --------------------------------------------------------------------------
# Small primitives this phase needed and `audio.synthesis` did not have
# --------------------------------------------------------------------------


def _moving_low_pass(buffer: array,
                     start_hz: float,
                     end_hz: float,
                     *,
                     sample_rate: int = SAMPLE_RATE,
                     stages: int = 2) -> array:
    """A one-pole low-pass whose cutoff glides from `start_hz` to `end_hz`.

    `audio.synthesis.low_pass` has a fixed cutoff, which is right for an impact
    and wrong for the unlock: a filter *opening* is what "a thing is opening"
    sounds like, and a static filter cannot say it. The interpolation is
    geometric, because cutoff is heard logarithmically.
    """
    length = len(buffer)
    if length == 0:
        return buffer
    start = max(1e-6, start_hz)
    end = max(1e-6, end_hz)
    ratio = (end / start) ** (1.0 / max(1, length - 1))
    for _ in range(max(1, stages)):
        cutoff = start
        state = 0.0
        for index in range(length):
            alpha = 1.0 - math.exp(-2.0 * math.pi * cutoff / sample_rate)
            if alpha > 1.0:
                alpha = 1.0
            state += alpha * (buffer[index] - state)
            buffer[index] = state
            cutoff *= ratio
    return buffer


def _swell(length: int, *, attack: float, hold: float, sample_rate: int) -> array:
    """A slow rise, a short plateau, then a linear fall to exactly zero.

    The reverse of an impact envelope, and what the gate and the escape need:
    both are things that arrive rather than things that strike.
    """
    out = silence(length)
    if length == 0:
        return out
    rise = min(length, max(1, seconds_to_samples(attack, sample_rate)))
    flat = min(length - rise, max(0, seconds_to_samples(hold, sample_rate)))
    fall = length - rise - flat
    for index in range(length):
        if index < rise:
            out[index] = (index + 1) / rise
        elif index < rise + flat:
            out[index] = 1.0
        else:
            out[index] = max(0.0, (length - index) / max(1, fall))
    return out


def _partials(length: int,
              parts: Sequence[tuple[float, float, float]],
              *,
              attack: float,
              sample_rate: int,
              release: float = DEFAULT_RELEASE) -> array:
    """Sum of `(freq, gain, decay)` sines into one buffer, all in phase.

    In phase, and that is a decision with a measurement behind it rather than
    the default nobody thought about.

    A cue is peak-normalised before its gain is applied, so the divisor is the
    peak of the sum. Every partial here starts at phase zero, so at the onset
    they are all rising together and that peak is very nearly the *sum* of
    their gains: the detonation's eleven voices are divided by about 3.9, and
    each one comes out at a quarter of the level it was written at. That
    dilution is real, and it is what made the first build of the final hit
    measure **+0.4 dB RMS** over an ordinary activation through
    `loudness.phone_filter`.

    Spreading the starting phases was tried as the fix, and it is not one.
    Measured over all eleven pitches of the vocabulary, dispersing the same
    chord by the golden angle changed its normalised energy by between
    **+2.6 dB and -1.5 dB** depending on nothing more than how that particular
    set of frequencies happened to sum - a mean of about +0.2 dB, which is to
    say a coin flip. It also introduced a real defect on the way: two voices
    at the same frequency, which this chord has whenever the root's fourth
    octave meets the tile's own fundamental, are the same note and must
    reinforce; given different phases they cancelled, and a final tile at the
    top of the arena lost its 880 Hz voice by **18.3 dB**.

    So the dilution is paid rather than dodged, and the detonation is made to
    carry through a phone by being voiced an octave up with a fixed bright
    rack and a much larger noise bloom - see `_final_cue`. The transient stays
    a transient, which is the other thing dispersion would have cost.
    """
    out = silence(length)
    for freq, gain, decay in parts:
        if gain <= 0.0 or freq <= 0.0:
            continue
        add_into(out, tone(length, freq=freq, attack=attack, decay=decay,
                           release=release, sample_rate=sample_rate), 0, gain)
    return out


def tilt_for(freq: float, config: AudioConfig, depth: float | None = None) -> float:
    """How much extra upper-partial weight a note of this pitch gets.

    1.0 at the bottom of the register and 0.0 from `tilt_hz` up, multiplied by
    the depth. See `AudioConfig.tilt_hz` for why this exists: without it the
    arena has a 7.5 dB loudness gradient that appears only on a phone speaker.
    A function of the note and of nothing else, so it cannot break a tile's
    identity - the same tile gets the same tilt in every run.
    """
    if depth is None:
        depth = config.tilt_depth
    unit = max(0.0, (config.tilt_hz - freq) / config.tilt_hz)
    return unit * depth


# A transient layer - a tick, a bloom - is added to a cue *after* its tonal
# body has been normalised, never before. Added first, its share of the finished
# cue depends on whatever the partials underneath it happened to sum to, so a
# layer that is meant to be a fixed proportion of the sound quietly becomes a
# variable one. That is not hypothetical: the activation's bright tick is the
# single highest-frequency thing in the cue, and adding it before normalisation
# made a *late* activation - which has more partials in it - measurably
# **darker** than an early one, spectral centroid 2374 Hz at 1 of 51 against
# 1970 Hz at 50 of 51, while every gain in the progression moved the right way.
# Normalise, then layer, then normalise again.
_TICK_SHARE_ACTIVATION = 0.34
_TICK_SHARE_DUPLICATE = 0.52
_BLOOM_SHARE_FINAL = 0.78
_SUB_SHARE_FINAL = 0.20


def _duplicate_cue(freq: float, config: AudioConfig) -> array:
    """A tile that was already lit, struck again.

    Weakest of the five: the tile's fundamental with a little of its octave,
    rolled off above 1.7 kHz so it sits under everything, plus one very quiet
    band-limited tick so the contact is still a contact on a phone speaker.
    Short - 110 ms - which is what keeps a hundred and seven of them from
    turning into a wash.
    """
    rate = config.sample_rate
    length = seconds_to_samples(config.duplicate_seconds, rate)
    tilt = tilt_for(freq, config, config.tilt_depth_duplicate)
    body = _partials(
        length,
        ((freq, 1.0, config.duplicate_decay),
         (freq * 2.0, 0.17 + 0.50 * tilt, config.duplicate_decay * 0.55),
         (freq * 3.0, 0.22 * tilt, config.duplicate_decay * 0.40)),
        attack=0.0009,
        sample_rate=rate,
    )
    low_pass(body, config.duplicate_lowpass_hz, sample_rate=rate, stages=2)
    tick = noise_burst(
        seconds_to_samples(0.020, rate),
        seed=stable_seed("category3", "duplicate", round(freq, 4)),
        attack=0.0004,
        decay=0.0055,
        highpass=1400.0,
        lowpass=5200.0,
        sample_rate=rate,
    )
    normalise_peak(body, 1.0)
    add_into(body, tick, 0, _TICK_SHARE_DUPLICATE)
    normalise_peak(body, 1.0)
    return body


def _activation_cue(freq: float,
                    bright: float,
                    fourth: float,
                    upper: float,
                    fifth: float,
                    config: AudioConfig) -> array:
    """A tile lighting: the same note, opened out.

    Against the duplicate: the octave comes up from 0.17 to 0.42, the twelfth
    arrives at `bright`, the tail is five times longer, and the tick is higher
    and harder. The fundamental is the same frequency, which is the point -
    the viewer hears the same wall answer more fully, not a different wall.

    The partials decay at different rates, shortest on top. A stack that all
    decayed together would read as an organ; this reads as something struck.
    """
    rate = config.sample_rate
    length = seconds_to_samples(config.activation_seconds, rate)
    tilt = tilt_for(freq, config)
    decay = config.activation_decay
    parts = [
        (freq, 1.0, decay),
        (freq * 2.0, 0.42 + 0.34 * tilt, decay * 0.62 * upper),
        (freq * 3.0, bright * (1.0 + 1.15 * tilt), decay * 0.40 * upper),
        (freq * 4.0, 0.26 * tilt + fourth, decay * 0.30 * upper),
        (freq * 6.0, 0.13 * tilt, decay * 0.20 * upper),
    ]
    if fifth > 0.0:
        parts.append((freq * 1.5, fifth, decay * 0.75))
    body = _partials(length, tuple(parts), attack=0.0013, sample_rate=rate)
    tick = noise_burst(
        seconds_to_samples(0.026, rate),
        seed=stable_seed("category3", "activation", round(freq, 4)),
        attack=0.0004,
        decay=0.0075,
        highpass=2000.0,
        lowpass=7200.0,
        sample_rate=rate,
    )
    normalise_peak(body, 1.0)
    add_into(body, tick, 0, _TICK_SHARE_ACTIVATION)
    normalise_peak(body, 1.0)
    return body


def _final_cue(freq: float, config: AudioConfig) -> array:
    """The fifty-first tile: the same note again, voiced upward, over the key.

    Three things at once, and the order they are listed in is the order they
    were arrived at.

    **The tile keeps its identity.** Its fundamental is in the chord and its
    octave is the loudest voice in the piece, so the fifty-first tile still
    sounds like *that wall* - the same thing a duplicate and an activation on
    it would have said.

    **The key arrives under it.** The root and its fifth are there whatever
    the tile is, so the detonation states the same chord on every seed and the
    unlock and the escape that follow are answering a question it asked. On
    seed 3530 the last tile is at the bottom of the ring and its note happens
    to *be* the root; on a seed whose last tile is at the top it is a tenth
    above, and the ending resolves identically either way.

    **And it is voiced an octave up, with a bright rack above it.** That is
    the correction for the worst measurement of this phase. Voiced the obvious
    way - root and fifth at the bottom, the tile's fundamental on top - the
    detonation put nearly all of its energy below 500 Hz, and through
    `loudness.phone_filter` it measured **+3.0 dB peak and +0.4 dB RMS** above
    an ordinary activation instead of the six or more it has to have. A phone
    simply did not hear that the run had ended. The chord is now centred an
    octave higher and carries a fixed rack on the root's upper octaves - 880,
    1320, 1760 and 2640 Hz, every one of them consonant with every note in the
    vocabulary because they are octaves and fifths of the root - so the
    detonation's weight is where a small speaker can reproduce it, whichever
    tile happens to be last. Phase 4 made the same beat white rather than
    amber: a full spectrum is what a detonation looks like and it turns out to
    be what one sounds like too.

    Its length and decay are the confirmation-hold treatment: `resonant` rings
    for 1.70 s and covers the whole pause, `breath` is out in 0.70 s and leaves
    the pause nearly empty, `drone` sits between them with a sustain under it.
    """
    rate = config.sample_rate
    length = seconds_to_samples(config.final_length_seconds, rate)
    decay = config.final_decay
    root = config.root_hz
    tilt = tilt_for(freq, config)
    body = _partials(
        length,
        (
            # The key. Felt more than heard on a phone, and that is its job.
            (root, 0.34, decay),
            (root * 1.5, 0.30, decay * 0.90),
            # The fixed bright rack: two, two-and-a-fifth, three and
            # three-and-a-fifth octaves above the root.
            (root * 4.0, 0.78, decay * 0.72),
            (root * 6.0, 0.60, decay * 0.52),
            (root * 8.0, 0.46, decay * 0.38),
            (root * 12.0, 0.28, decay * 0.24),
            # The tile itself, voiced up: the octave is the loudest voice.
            (freq, 0.60, decay),
            (freq * 2.0, 1.00, decay * 0.78),
            (freq * 3.0, 0.52 + 0.20 * tilt, decay * 0.48),
            (freq * 4.0, 0.34 + 0.22 * tilt, decay * 0.30),
            (freq * 6.0, 0.18 + 0.16 * tilt, decay * 0.18),
        ),
        attack=0.0016,
        sample_rate=rate,
    )
    # Weight on headphones, nothing on a phone, and it is gone in a tenth of a
    # second either way - the detonation should land in the chest and not stay
    # there.
    normalise_peak(body, 1.0)
    add_into(body, tone(seconds_to_samples(0.30, rate), freq=root * 0.5,
                        attack=0.002, decay=0.085, sample_rate=rate), 0,
             _SUB_SHARE_FINAL)
    bloom = noise_burst(
        seconds_to_samples(0.40, rate),
        seed=stable_seed("category3", "final", round(freq, 4)),
        attack=0.0006,
        decay=0.090,
        highpass=1400.0,
        lowpass=9000.0,
        sample_rate=rate,
    )
    add_into(body, bloom, 0, _BLOOM_SHARE_FINAL)
    normalise_peak(body, 1.0)
    return body


def _confirm_cue(config: AudioConfig) -> array:
    """The `drone` hold: a low root-and-fifth sustain under the 0.92 s pause.

    Restrained to the point of being barely there - a twelfth of an activation
    - because its job is to say the audio has not failed, not to fill the
    silence the unlock has to arrive out of.
    """
    rate = config.sample_rate
    length = seconds_to_samples(0.950, rate)
    body = _partials(
        length,
        ((config.root_hz, 1.0, 3.2), (config.root_hz * 1.5, 0.55, 3.2)),
        attack=0.090,
        sample_rate=rate,
    )
    shape = _swell(length, attack=0.110, hold=0.560, sample_rate=rate)
    for index in range(length):
        body[index] *= shape[index]
    normalise_peak(body, 1.0)
    return body


def _unlock_cue(freq: float, gate_seconds: float, config: AudioConfig) -> array:
    """The arena changing state: a rise, and something opening.

    Three layers, and the middle one is the reason this does not sound like
    another note:

    * a glide from the tile that was just struck up to the top of the
      register, with a fifth gliding in parallel - the tonal rise;
    * a noise swell whose low-pass cutoff opens from 400 Hz to 7 kHz over the
      length of the cue - a filter opening, which is what an opening sounds
      like and what a static filter cannot say;
    * one short low knock at the head of it, for the flare - the restrained
      mechanical layer, and it is two hundredths of a second long.

    The rise is exactly as long as the `unlocking` segment - the time Phase 4
    gives the gate to flare and retract, read from the document rather than
    fixed here - so it tops out as the opening completes and the ball is let
    go. A re-timed ending carries the sound of the gate with it.

    The glide **swells** rather than decays, and that is a correction rather
    than a preference. Written the ordinary way - a struck envelope on a
    rising sweep - almost all of the cue's energy sat at the bottom of the
    glide, which on seed 3530 is 220 Hz. Measured, only 8.9% of it was above
    500 Hz and the gate opening came out 7 dB *below* an ordinary activation
    through `loudness.phone_filter`: on a phone the arena changed state in
    silence. A rise that gets louder as it rises is also simply the right
    shape for the beat - the gate flares, then retracts - so the fix costs
    nothing.
    """
    rate = config.sample_rate
    length = seconds_to_samples(config.unlock_seconds, rate)
    top = config.root_hz * 2.0 ** config.octaves
    body = silence(length)
    shape = _swell(length, attack=gate_seconds, hold=0.070, sample_rate=rate)
    for gain, start, end, attack in ((1.00, freq, top, 0.010),
                                     (0.46, freq * 1.5, top * 1.5, 0.014),
                                     (0.26, freq * 2.0, top * 2.0, 0.018)):
        voice = tone(length, freq=start, freq_end=end, attack=attack,
                     decay=6.0, sample_rate=rate)
        for index in range(length):
            voice[index] *= shape[index]
        add_into(body, voice, 0, gain)

    swell_n = seconds_to_samples(0.460, rate)
    air = noise_burst(swell_n, seed=stable_seed("category3", "unlock", "gate"),
                      attack=0.001, decay=8.0, sample_rate=rate)
    _moving_low_pass(air, 500.0, 8000.0, sample_rate=rate, stages=2)
    high_pass(air, 420.0, sample_rate=rate, stages=1)
    air_shape = _swell(swell_n, attack=0.280, hold=0.060, sample_rate=rate)
    for index in range(swell_n):
        air[index] *= air_shape[index]
    normalise_peak(air, 1.0)
    add_into(body, air, 0, 0.62)

    knock = _partials(seconds_to_samples(0.11, rate),
                      ((150.0, 1.0, 0.020), (300.0, 0.35, 0.014),
                       (1850.0, 0.30, 0.007)),
                      attack=0.0008, sample_rate=rate)
    add_into(body, knock, 0, 0.30)
    normalise_peak(body, 1.0)
    return body


def _escape_cue(seconds: float, config: AudioConfig) -> array:
    """The release: the root triad, swelling and then gone.

    The one cue in the piece that is not an impact. Everything before it
    arrives by being struck; this arrives by growing, which is what makes it
    read as a resolution rather than as one more collision.

    Its length is `seconds` - whatever is left of the video after the release,
    less the silence the ending finishes in - and not a constant. Built at a
    fixed 1.56 s it overran the last frame on every seed and was cut off by
    the end of the buffer rather than ending: seed 37169's final sample
    measured **-26.9 dBFS**, a splice at the end of a Short. The escape
    segment's own render length is `exit_seconds / escape_rate`, which is
    0.99 s on seed 3530 and 0.62 s on 37169, so there is no constant that fits
    every seed and the number has to come from the timeline.

    The release ramp is 0.22 s, long enough that whatever level the decay has
    reached when the pad's time is up is faded rather than truncated, and the
    decays are short enough that it is already 20 dB down by then.
    """
    rate = config.sample_rate
    length = seconds_to_samples(seconds, rate)
    root = config.root_hz
    body = _partials(
        length,
        (
            (root, 0.72, 0.500),
            (root * 1.5, 0.56, 0.440),
            (root * 2.0, 1.00, 0.420),
            (root * 3.0, 0.62, 0.340),
            (root * 4.0, 0.52, 0.290),
            (root * 6.0, 0.34, 0.220),
            (root * 8.0, 0.22, 0.170),
            (root * 12.0, 0.11, 0.120),
        ),
        attack=0.050,
        release=0.220,
        sample_rate=rate,
    )
    air_n = min(length, seconds_to_samples(0.900, rate))
    air = noise_burst(air_n, seed=stable_seed("category3", "escape", "air"),
                      attack=0.001, decay=9.0, sample_rate=rate)
    high_pass(air, 900.0, sample_rate=rate, stages=2)
    low_pass(air, 6500.0, sample_rate=rate, stages=1)
    shape = _swell(air_n, attack=0.130, hold=0.040, sample_rate=rate)
    for index in range(air_n):
        air[index] *= shape[index]
    normalise_peak(air, 1.0)
    add_into(body, air, 0, 0.34)
    normalise_peak(body, 1.0)
    return body


def cue_for(event: AudioEvent, config: AudioConfig) -> array:
    """The mono, peak-normalised buffer for one event.

    Pure in its arguments, which is what lets the renderer cache it: two
    duplicates on the same tile are the same buffer, and so are two
    activations that happen to land on the same progress.
    """
    if event.kind == "duplicate":
        return _duplicate_cue(float(event.freq), config)
    if event.kind == "activation":
        if config.progression:
            unit = event.progress
            bright = config.bright_low + (config.bright_high - config.bright_low) * unit
            fourth = config.fourth_growth * unit
            upper = 1.0 + config.upper_decay_growth * unit
            fifth = 0.0
            if unit >= config.late_fifth_from:
                span = max(1e-9, 1.0 - config.late_fifth_from)
                fifth = config.late_fifth_gain * (unit - config.late_fifth_from) / span
        else:
            bright, fourth, upper, fifth = config.bright_low, 0.0, 1.0, 0.0
        return _activation_cue(float(event.freq), bright, fourth, upper,
                               fifth, config)
    if event.kind == "final":
        return _final_cue(float(event.freq), config)
    if event.kind == "confirm":
        return _confirm_cue(config)
    if event.kind == "unlock":
        return _unlock_cue(float(event.freq),
                           float(event.duration_seconds or 0.300), config)
    if event.kind == "escape":
        return _escape_cue(float(event.duration_seconds
                                 or config.escape_seconds), config)
    raise AudioError(f"no cue for event kind {event.kind!r}")


def _cache_key(event: AudioEvent, config: AudioConfig) -> tuple:
    if event.kind == "activation":
        return ("activation", round(float(event.freq), 6),
                round(event.progress, 9) if config.progression else 0.0)
    if event.kind == "unlock":
        return ("unlock", round(float(event.freq), 6),
                round(float(event.duration_seconds or 0.300), 6))
    if event.kind in ("duplicate", "final"):
        return (event.kind, round(float(event.freq), 6))
    if event.kind == "escape":
        return ("escape", round(float(event.duration_seconds or 0.0), 6))
    return (event.kind,)


# --------------------------------------------------------------------------
# The render
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RenderedAudio:
    """One finished stereo master and everything measured about it."""

    schedule: AudioSchedule
    left: array
    right: array
    master_gain: float
    limiter_gain: float
    limited: bool
    voices: dict[str, Any]

    @property
    def sample_rate(self) -> int:
        return self.schedule.config.sample_rate

    def pcm(self, bit_depth: int = DEFAULT_BIT_DEPTH) -> bytes:
        return pcm_bytes(self.left, self.right, bit_depth)

    def digest(self, bit_depth: int = DEFAULT_BIT_DEPTH) -> str:
        """SHA-256 over the PCM that would be written. Determinism, in one line."""
        return sha256_hex(self.pcm(bit_depth))


def render(plan: AudioSchedule) -> RenderedAudio:
    """The schedule, as samples.

    Mix, then one static gain, then the look-ahead limiter above. No
    compressor and no per-event normalisation after placement: both would move
    events relative to each other, and the relationship between them is the
    design.
    """
    config = plan.config
    rate = config.sample_rate
    length = plan.total_samples
    left = silence(length)
    right = silence(length)

    cache: dict[tuple, array] = {}
    spans: list[tuple[float, float, str]] = []
    floor = db_to_gain(VOICE_FLOOR_DB)

    for event in plan.events:
        key = _cache_key(event, config)
        cue = cache.get(key)
        if cue is None:
            cue = cue_for(event, config)
            cache[key] = cue
        offset = int(round(event.at_seconds * rate))
        left_gain, right_gain = pan_gains(event.pan)
        add_into(left, cue, offset, event.gain * left_gain)
        add_into(right, cue, offset, event.gain * right_gain)

        # How long this voice is actually audible, from the rendered cue rather
        # than from the envelope the schedule assumed. The two differ: a cue's
        # buffer is as long as its longest partial needs, and the partial that
        # sets the length is usually 40 dB down well before the buffer ends.
        loudest = event.gain * max(left_gain, right_gain)
        audible = 0
        for index in range(len(cue) - 1, -1, -1):
            if abs(cue[index]) * loudest > floor:
                audible = index + 1
                break
        if audible:
            spans.append((event.at_seconds,
                          event.at_seconds + audible / rate,
                          event.kind))

    report = master(left, right, ceiling=PEAK_CEILING,
                    makeup_db=config.master_gain_db, sample_rate=rate)

    return RenderedAudio(
        schedule=plan,
        left=left,
        right=right,
        master_gain=report.makeup_gain,
        limiter_gain=report.limiter_gain,
        limited=report.limited,
        voices=_polyphony(spans),
    )


def _polyphony(spans: Sequence[tuple[float, float, str]]) -> dict[str, Any]:
    """Largest number of voices audible at once, and when.

    A sweep over starts and ends. "Audible" is 50 dB below the loudest event in
    the piece, measured on the rendered cue at the gain it was placed with, so
    a duplicate's contribution counts for the 60 ms it can be heard for and not
    for the 110 ms its buffer occupies.
    """
    if not spans:
        return {"max_voices": 0, "at_seconds": 0.0, "kinds": []}
    edges: list[tuple[float, int, str]] = []
    for start, stop, kind in spans:
        edges.append((start, 1, kind))
        edges.append((stop, -1, kind))
    edges.sort(key=lambda item: (item[0], item[1]))
    live = 0
    best, best_at = 0, 0.0
    active: list[str] = []
    best_kinds: list[str] = []
    for when, delta, kind in edges:
        if delta > 0:
            live += 1
            active.append(kind)
        else:
            live -= 1
            if kind in active:
                active.remove(kind)
        if live > best:
            best, best_at, best_kinds = live, when, sorted(active)
    return {
        "max_voices": best,
        "at_seconds": round(best_at, 4),
        "kinds": best_kinds,
    }


def render_document(document: dict[str, Any],
                    config: AudioConfig = DEFAULT_CONFIG) -> RenderedAudio:
    return render(build_schedule(document, config))


def write_master(rendered: RenderedAudio,
                 path: str,
                 bit_depth: int = DEFAULT_BIT_DEPTH) -> str:
    return write_wav(path, rendered.left, rendered.right,
                     sample_rate=rendered.sample_rate, bit_depth=bit_depth)


# --------------------------------------------------------------------------
# Measurement
# --------------------------------------------------------------------------


def _window_peak(left: array, right: array, start: int, stop: int) -> float:
    highest = 0.0
    stop = min(stop, len(left))
    for index in range(max(0, start), stop):
        magnitude = abs(left[index])
        if magnitude > highest:
            highest = magnitude
        magnitude = abs(right[index])
        if magnitude > highest:
            highest = magnitude
    return highest


def _window_rms(left: array, right: array, start: int, stop: int) -> float:
    """Energy in the window, as a level.

    Reported beside the peak because for this material they answer different
    questions and the peak alone is misleading. An event's peak in the mix is
    its designed gain by construction - a cue is peak-normalised before the
    gain is applied - so the peak reading mostly confirms the arithmetic. What
    an ear weighs over fifty-five milliseconds is closer to the energy, and a
    long dense chord and a short bright tick with the same peak are nothing
    like each other. The detonation's phone defect was visible in both, which
    is why it was believed.
    """
    total = 0.0
    stop = min(stop, len(left))
    start = max(0, start)
    count = max(1, stop - start)
    for index in range(start, stop):
        total += left[index] * left[index] + right[index] * right[index]
    return math.sqrt(total / (2 * count))


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = fraction * (len(ordered) - 1)
    low = int(math.floor(position))
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def _hierarchy(rendered: RenderedAudio,
               left: Sequence[float] | None = None,
               right: Sequence[float] | None = None) -> dict[str, Any]:
    """What each kind of event actually reaches in the finished master.

    Measured, not asserted: the local peak in a 55 ms window from each event's
    own placement, grouped by kind. It is the honest version of "an activation
    is more rewarding than a duplicate" - the designed gains say one thing, and
    two events landing on the same frame or a limiter engaging could say
    another.
    """
    config = rendered.schedule.config
    buffer_left = rendered.left if left is None else left
    buffer_right = rendered.right if right is None else right
    window = seconds_to_samples(EVENT_WINDOW_SECONDS, config.sample_rate)
    peaks: dict[str, list[float]] = {}
    energies: dict[str, list[float]] = {}
    offsets: dict[tuple, int] = {}
    for event in rendered.schedule.events:
        # The window runs from where this cue's own peak falls, not from where
        # it was placed. Four of the six kinds are struck and peak in their
        # first four milliseconds, so for them the two are the same thing. The
        # unlock is not: it swells and peaks 327 ms in, and measured from its
        # placement it read 22 dB down - a reading of the silence at the start
        # of a rise rather than of the rise. The escape swells too, at 93 ms.
        key = _cache_key(event, config)
        head = offsets.get(key)
        if head is None:
            cue = cue_for(event, config)
            head = max(range(len(cue)), key=lambda i: abs(cue[i])) if cue else 0
            offsets[key] = head
        start = int(round(event.at_seconds * config.sample_rate)) + head
        peaks.setdefault(event.kind, []).append(
            _window_peak(buffer_left, buffer_right, start, start + window))
        energies.setdefault(event.kind, []).append(
            _window_rms(buffer_left, buffer_right, start, start + window))

    out: dict[str, Any] = {}
    for kind, values in peaks.items():
        energy = energies[kind]
        out[kind] = {
            "count": len(values),
            "median_dbfs": round(gain_to_db(_percentile(values, 0.5)), 2),
            "p05_dbfs": round(gain_to_db(_percentile(values, 0.05)), 2),
            "p95_dbfs": round(gain_to_db(_percentile(values, 0.95)), 2),
            "max_dbfs": round(gain_to_db(max(values)), 2),
            "median_rms_dbfs": round(gain_to_db(_percentile(energy, 0.5)), 2),
            "p05_rms_dbfs": round(gain_to_db(_percentile(energy, 0.05)), 2),
            "p95_rms_dbfs": round(gain_to_db(_percentile(energy, 0.95)), 2),
        }
    return out


def _silence_runs(left: array, right: array, rate: int) -> dict[str, Any]:
    floor = db_to_gain(SILENCE_FLOOR_DB)
    longest, run, longest_at = 0, 0, 0
    quiet = 0
    for index in range(len(left)):
        if abs(left[index]) < floor and abs(right[index]) < floor:
            run += 1
            quiet += 1
            if run > longest:
                longest, longest_at = run, index - run + 1
        else:
            run = 0
    return {
        "longest_silence_seconds": round(longest / rate, 4),
        "longest_silence_at_seconds": round(longest_at / rate, 4),
        "silent_fraction": round(quiet / max(1, len(left)), 5),
    }


def cue_profile(rendered: RenderedAudio) -> dict[str, Any]:
    """Each kind of event measured on its own cue, away from the mix.

    The in-mix window reading in `_hierarchy` answers "what happened"; this
    answers "what was designed", and the two are needed together. A window
    reading is contaminated by whatever else is sounding and truncated at
    55 ms, which flatters a short bright event and undersells a 1.7-second
    chord. Here each kind is measured on the actual buffer it was placed with,
    at the gain it was placed at, over its whole length:

    * `peak_dbfs` - the event's own peak, which by construction is its gain;
    * `energy_dbfs` - `10 log10` of its total squared sum, so a long event
      counts for being long. This is the reading that says an activation is a
      bigger thing than a duplicate rather than just a louder one;
    * `above_500hz_pct` - the share of that energy a phone speaker can
      reproduce. It is why the detonation is voiced an octave up.
    """
    import numpy as np

    config = rendered.schedule.config
    rate = config.sample_rate
    seen: dict[str, dict[tuple, float]] = {}
    lengths: dict[str, list[float]] = {}
    for event in rendered.schedule.events:
        key = _cache_key(event, config)
        seen.setdefault(event.kind, {})
        if key in seen[event.kind]:
            continue
        seen[event.kind][key] = event.gain

    out: dict[str, Any] = {}
    for kind, keyed in seen.items():
        energies, peaks, shares = [], [], []
        for event in rendered.schedule.events:
            if event.kind != kind:
                continue
            key = _cache_key(event, config)
            if keyed.pop(key, None) is None:
                continue
            samples = np.asarray(cue_for(event, config)) * event.gain
            power = float(np.sum(samples * samples))
            energies.append(power)
            peaks.append(float(np.max(np.abs(samples))))
            spectrum = np.abs(np.fft.rfft(samples)) ** 2
            freqs = np.fft.rfftfreq(samples.size, 1.0 / rate)
            total = float(spectrum.sum()) or 1.0
            shares.append(100.0 * float(spectrum[freqs >= 500.0].sum()) / total)
            lengths.setdefault(kind, []).append(samples.size / rate)
        out[kind] = {
            "distinct_cues": len(energies),
            "seconds": round(_percentile(lengths[kind], 0.5), 4),
            "peak_dbfs": round(gain_to_db(_percentile(peaks, 0.5)), 2),
            "energy_dbfs": round(
                10.0 * math.log10(max(_percentile(energies, 0.5), 1e-18)), 2),
            "above_500hz_pct": round(_percentile(shares, 0.5), 2),
        }
    return out


# The quietest bed an emergence is measured against. Without a floor, an event
# that lands in a silent gap divides by the arithmetic zero of an empty buffer
# and reports something like +228 dB, which is not a number anyone can read and
# not one that can be averaged with the others. -80 dBFS is well below anything
# audible in this material, so clamping there says "it arrived out of silence"
# and keeps the column summable.
MASKING_BED_FLOOR_DBFS = -80.0


def masking_report(rendered: "RenderedAudio",
                   left: Sequence[float] | None = None,
                   right: Sequence[float] | None = None) -> dict[str, Any]:
    """How far each event rises above whatever was already sounding.

    A hierarchy measured against silence is not the question. At five contacts
    a second an activation usually lands on the tail of the two before it, so
    what decides whether the viewer hears progress is not the activation's
    absolute level but how far it *emerges* from the bed underneath it.

    `emergence` is the energy in a window at the event's own peak over the
    energy in the same-length window immediately before the event started, in
    decibels. Two details, both of which were wrong first:

    * the window runs from the **cue's peak**, not from its placement, for the
      same reason `_hierarchy`'s does - measured at its placement the unlock
      emerged by -0.44 dB, which is a reading of the silence at the head of a
      swell rather than of the swell;
    * the bed is clamped at `MASKING_BED_FLOOR_DBFS`, because an event landing
      in a genuinely empty stretch otherwise divides by nothing.

    A duplicate is allowed to emerge by very little - that is what "low
    sensory weight" means, and a third of them do not clear 3 dB. An
    activation is not: `masked_count` counts the ones that emerge by less than
    3 dB, which is about where an event stops being separate and becomes a
    swell in the one before it.
    """
    config = rendered.schedule.config
    rate = config.sample_rate
    buffer_left = rendered.left if left is None else left
    buffer_right = rendered.right if right is None else right
    window = seconds_to_samples(EVENT_WINDOW_SECONDS, rate)
    floor = db_to_gain(MASKING_BED_FLOOR_DBFS)

    offsets: dict[tuple, int] = {}
    by_kind: dict[str, list[float]] = {}
    silent: dict[str, int] = {}
    for event in rendered.schedule.events:
        placed = int(round(event.at_seconds * rate))
        if placed < window:
            continue
        key = _cache_key(event, config)
        head = offsets.get(key)
        if head is None:
            cue = cue_for(event, config)
            head = max(range(len(cue)), key=lambda i: abs(cue[i])) if cue else 0
            offsets[key] = head
        bed = _window_rms(buffer_left, buffer_right, placed - window, placed)
        here = _window_rms(buffer_left, buffer_right,
                           placed + head, placed + head + window)
        if here <= 0.0:
            continue
        if bed < floor:
            silent[event.kind] = silent.get(event.kind, 0) + 1
        by_kind.setdefault(event.kind, []).append(
            gain_to_db(here) - gain_to_db(max(bed, floor)))

    out: dict[str, Any] = {
        "threshold_db": 3.0,
        "bed_floor_dbfs": MASKING_BED_FLOOR_DBFS,
    }
    for kind, values in by_kind.items():
        out[kind] = {
            "count": len(values),
            "median_emergence_db": round(_percentile(values, 0.5), 2),
            "p05_emergence_db": round(_percentile(values, 0.05), 2),
            "min_emergence_db": round(min(values), 2),
            "masked_count": sum(1 for value in values if value < 3.0),
            "arrived_in_silence": silent.get(kind, 0),
        }
    return out


def confirmation_profile(rendered: "RenderedAudio") -> dict[str, Any]:
    """What the 0.92 s pause actually sounds like, bin by bin.

    The brief asks whether contrast before the unlock makes the payoff
    stronger, and that is not a question a peak reading answers. This walks
    the paused section - from the detonation to the release - in 60 ms bins
    and reports the level of each, so the three confirmation-hold treatments
    can be compared as curves rather than as adjectives.

    Three summary numbers come out of it:

    * `floor_dbfs` - the quietest bin between the wave leaving and the gate
      flaring. This is the silence, if there is any.
    * `at_unlock_dbfs` - the level in the bin the gate's flare lands in.
    * `contrast_db` - the difference. It is the size of the reduction the
      unlock arrives out of, and it is the whole of what distinguishes the
      three treatments: `resonant` rings through the pause and has almost
      none, `breath` empties the pause out and has the most, `drone` puts a
      floor under it deliberately.
    """
    plan = rendered.schedule
    if not plan.completed:
        return {}
    config = plan.config
    rate = config.sample_rate
    start = plan.beats["final_hit"]
    wave = plan.beats["confirming"]
    gate = plan.beats["unlocking"]
    release = plan.beats["escaping"]

    step = 0.060
    bins: list[dict[str, Any]] = []
    when = start
    while when < release - 1e-9:
        head = int(round(when * rate))
        tail = int(round(min(when + step, release) * rate))
        bins.append({
            "at_seconds": round(when - start, 4),
            "state": ("final_hit" if when < wave
                      else "confirming" if when < gate else "unlocking"),
            "rms_dbfs": round(gain_to_db(
                _window_rms(rendered.left, rendered.right, head, tail)), 2),
            "peak_dbfs": round(gain_to_db(
                _window_peak(rendered.left, rendered.right, head, tail)), 2),
        })
        when += step

    quiet = [entry for entry in bins if entry["state"] == "confirming"]
    flare = [entry for entry in bins if entry["state"] == "unlocking"]
    floor = min((entry["rms_dbfs"] for entry in quiet), default=0.0)
    at_unlock = max((entry["rms_dbfs"] for entry in flare), default=0.0)
    return {
        "hold": config.confirmation,
        "pause_seconds": round(release - start, 4),
        "bin_seconds": step,
        "floor_dbfs": floor,
        "floor_at_seconds": min(
            (entry["at_seconds"] for entry in quiet
             if entry["rms_dbfs"] == floor), default=0.0),
        "at_detonation_dbfs": bins[0]["rms_dbfs"] if bins else 0.0,
        "at_unlock_dbfs": at_unlock,
        "contrast_db": round(at_unlock - floor, 2),
        "decay_across_pause_db": round(
            floor - (bins[0]["rms_dbfs"] if bins else 0.0), 2),
        "bins": bins,
    }


def measure(rendered: RenderedAudio,
            *,
            phone: bool = True,
            document: dict[str, Any] | None = None) -> dict[str, Any]:
    """Every number the decision gate needs, from the finished master.

    Uses `audio.loudness` - the project's existing meter - for true peak,
    integrated loudness, mono compatibility and the phone-speaker
    approximation, so Phase 5 is judged by the same instrument the race
    soundtracks were.
    """
    import numpy as np

    from audio import loudness

    config = rendered.schedule.config
    rate = config.sample_rate
    stereo = loudness.as_stereo(rendered.left, rendered.right)
    meter = loudness.measure(stereo, rate)

    clipped = int(np.count_nonzero(np.abs(stereo) > 1.0))
    at_ceiling = int(np.count_nonzero(np.abs(stereo) > PEAK_CEILING + 1e-12))

    out: dict[str, Any] = {
        "render_version": AUDIO_RENDER_VERSION,
        "seed": rendered.schedule.seed,
        "config": config.name,
        "config_fingerprint": config.fingerprint(),
        "schedule_fingerprint": rendered.schedule.fingerprint()[:16],
        "sample_rate": rate,
        "samples": len(rendered.left),
        "seconds": round(len(rendered.left) / rate, 6),
        "frames": rendered.schedule.frames,
        "fps": config.fps,
        "master_gain_db": round(gain_to_db(rendered.master_gain), 3),
        "limiter_engaged": rendered.limited,
        "limiter_min_gain_db": round(gain_to_db(rendered.limiter_gain), 3),
        "peak": {
            "sample_peak_dbfs": meter.sample_peak_dbfs,
            "true_peak_dbtp": meter.true_peak_dbtp,
            "ceiling_dbfs": round(PEAK_CEILING_DBFS, 2),
            "clipped_samples": clipped,
            "samples_over_ceiling": at_ceiling,
        },
        "loudness": {
            "integrated_lufs": meter.integrated_lufs,
            "lra_lu": meter.lra_lu,
            "rms_dbfs": round(
                gain_to_db(math.sqrt(
                    (rms(rendered.left) ** 2 + rms(rendered.right) ** 2) / 2.0)), 2),
        },
        "density": dict(rendered.schedule.metrics),
        "voices": dict(rendered.voices),
        "hierarchy_dbfs": _hierarchy(rendered),
        "cues": cue_profile(rendered),
        "mono": loudness.mono_compatibility(stereo, rate),
        "fatigue": {
            "energy_above_4k_pct": loudness.energy_above(stereo, 4000.0, rate),
            "energy_above_8k_pct": loudness.energy_above(stereo, 8000.0, rate),
        },
    }
    out.update(_silence_runs(rendered.left, rendered.right, rate))

    if phone:
        small = loudness.phone_filter(stereo, rate)
        pair = np.repeat(small, 2, axis=1)
        phone_left = array("d", pair[:, 0].tolist())
        phone_right = array("d", pair[:, 1].tolist())
        out["phone"] = {
            "corner_hz": 500.0,
            "integrated_lufs": round(loudness.integrated(pair, rate), 2),
            "level_loss_db": round(
                loudness.integrated(pair, rate) - meter.integrated_lufs, 2),
            "hierarchy_dbfs": _hierarchy(rendered, phone_left, phone_right),
            "masking": masking_report(rendered, phone_left, phone_right),
        }

    out["hierarchy_gaps_db"] = _hierarchy_gaps(out)
    out["confirmation"] = confirmation_profile(rendered)
    out["masking"] = masking_report(rendered)
    if document is not None:
        out["sync"] = sync_report(rendered.schedule, document)
    return out


def _hierarchy_gaps(report: dict[str, Any]) -> dict[str, Any]:
    """The three differences the decision gate is actually about."""

    def gap(where: dict[str, Any], low: str, high: str, key: str) -> float | None:
        if low not in where or high not in where:
            return None
        return round(where[high][key] - where[low][key], 2)

    out: dict[str, Any] = {}
    for label, where in (("", report["hierarchy_dbfs"]),
                         ("phone_", report.get("phone", {}).get(
                             "hierarchy_dbfs"))):
        if where is None:
            continue
        out[f"{label}activation_over_duplicate_db"] = gap(
            where, "duplicate", "activation", "median_dbfs")
        out[f"{label}final_over_activation_db"] = gap(
            where, "activation", "final", "median_dbfs")
        out[f"{label}activation_over_duplicate_rms_db"] = gap(
            where, "duplicate", "activation", "median_rms_dbfs")
        out[f"{label}final_over_activation_rms_db"] = gap(
            where, "activation", "final", "median_rms_dbfs")
    return out


def sync_report(plan: AudioSchedule, document: dict[str, Any]) -> dict[str, Any]:
    """Where every cue lands against the frame that shows what caused it.

    Three separate things, and conflating them is how an A/V sync claim goes
    wrong:

    * **frame agreement.** Every tile event's frame is recomputed here from the
      document, and every activation's frame is checked a third way against
      `tile_playback.activation_frames` - Phase 3's own function, written
      before any of this existed. A disagreement anywhere is a real fault.
    * **placement error.** A cue is placed at `round(at_seconds * 48000)`, so
      it is at most half a sample - 10.4 microseconds - from the frame instant
      it belongs to. This is the A/V discrepancy, and it is four thousand times
      inside the brief's one-frame budget.
    * **frame lead.** How far the frame instant is after the canonical instant.
      This is a property of sampling a continuous run at 30 fps and it exists
      with or without audio: the picture of a contact at 21.4711 s is shown at
      21.5 s. The audio is placed on the picture, so the viewer sees and hears
      the same thing at the same moment; the number is reported because it is
      the size of the decision, not because it is an error.
    """
    from satisfying import tile_playback
    from satisfying.tile_score import frame_for

    config = plan.config
    leads: list[float] = []
    placement: list[float] = []
    mismatched: list[dict[str, Any]] = []
    for event in plan.events:
        expected = frame_for(event.render_seconds, config.fps)
        if expected != event.frame:
            mismatched.append({"kind": event.kind, "frame": event.frame,
                               "expected": expected})
        leads.append(event.at_seconds - event.render_seconds)
        sample = int(round(event.at_seconds * config.sample_rate))
        placement.append(sample / config.sample_rate - event.at_seconds)

    activation_frames = tile_playback.activation_frames(document, config.fps)
    scheduled = [event.frame for event in plan.events
                 if event.kind in ("activation", "final")]
    beats: dict[str, Any] = {}
    for name, when in plan.beats.items():
        beats[name] = {
            "render_seconds": round(when, 6),
            "frame": frame_for(when, config.fps),
        }
    for event in plan.events:
        if event.kind in ("final", "unlock", "escape", "confirm"):
            beats[f"cue_{event.kind}"] = {
                "render_seconds": round(event.render_seconds, 6),
                "frame": event.frame,
                "at_seconds": round(event.at_seconds, 6),
            }
    return {
        "fps": config.fps,
        "frame_seconds": round(1.0 / config.fps, 6),
        "events": len(plan.events),
        "frame_mismatches": mismatched,
        "activation_frames_agree": activation_frames == scheduled,
        "max_placement_error_seconds": round(max(abs(v) for v in placement), 9)
        if placement else 0.0,
        "max_placement_error_frames": round(
            max(abs(v) for v in placement) * config.fps, 9) if placement else 0.0,
        "mean_frame_lead_seconds": round(sum(leads) / len(leads), 6)
        if leads else 0.0,
        "max_frame_lead_seconds": round(max(leads), 6) if leads else 0.0,
        "beats": beats,
    }

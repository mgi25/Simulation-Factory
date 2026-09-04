"""What each battle event sounds like.

One function per identity, every one of them built out of `audio.synthesis`
primitives. This is the presentation layer, and unlike the interestingness
scorer it is *supposed* to tell powers apart: a viewer should hear an Orbit
bead strike and a Pulse bolt strike as different things. Nothing here is read
back by the simulation, so a sound can never change what happens in a battle.

Every cue is peak-normalised and then scaled to a designed level in dBFS, so
the number in the table below is what the cue actually peaks at whatever the
layers inside it happened to add up to. Levels are deliberately conservative:
they are added into a shared mix, and the master stage should have nothing to
do on a normal battle.

Two rules the levels encode:

* an activation is never louder than a major hit, because a power firing is
  an announcement and a big hit is the payoff;
* an elimination is the loudest single thing in a Short, but it is mostly low
  frequency, so it lands as weight rather than as volume.
"""

from __future__ import annotations

import math
from array import array
from dataclasses import dataclass

from audio.synthesis import (
    SAMPLE_RATE,
    Noise,
    db_to_gain,
    layer,
    low_pass,
    noise_burst,
    normalise_peak,
    rms,
    scale,
    seconds_to_samples,
    silence,
    stable_seed,
    tone,
)

# Hit subtypes, as the battle mode records them. `impact` is a fighter ramming
# a fighter; the rest are the `kind` of the dynamic entity that landed.
HIT_IMPACT = "impact"
HIT_PROJECTILE = "projectile"
HIT_ECHO = "echo"
HIT_ORBIT = "orbit"

# Power names, as `power_activate` records them.
POWER_RUSH = "rush"
POWER_TITAN = "titan"
POWER_PULSE = "pulse"
POWER_ECHO = "echo"
POWER_ORBIT = "orbit"

# The damage window magnitude is mapped across. Real replays put most hits
# between about 6 and 38 HP with occasional Titan-assisted rams near 50, so
# the window is set to spend its range where the hits actually are and clamp
# outside it rather than let one freak number own the loudest sound.
HIT_MAGNITUDE_QUIET = 4.0
HIT_MAGNITUDE_LOUD = 42.0
# A hit that recorded no magnitude at all still has to sound like something.
HIT_MAGNITUDE_DEFAULT = 0.35

# Designed peak level per cue, in dBFS. Hits carry two numbers: the quiet end
# of the damage window and the loud end.
LEVEL_HIT = {
    HIT_IMPACT: (-12.0, -3.6),
    HIT_PROJECTILE: (-11.0, -4.5),
    HIT_ECHO: (-13.5, -6.5),
    HIT_ORBIT: (-12.5, -5.8),
}
LEVEL_ACTIVATE = {
    POWER_RUSH: -10.0,
    POWER_TITAN: -8.5,
    POWER_PULSE: -9.8,
    POWER_ECHO: -11.5,
    POWER_ORBIT: -10.5,
}
# The elimination's level is set by a headroom budget rather than by taste.
# Every production replay ends with a lethal hit and an elimination recorded
# on the *same* tick, so the loudest moment of almost every Short is those
# two cues stacked on top of the ambient bed. The bed peaks near -24 dBFS,
# which leaves the cues about -0.6 dB of the -1 dBFS ceiling to share; this
# is the level at which the worst of those stacks - a heavy Orbit strike, the
# brightest of the four - still fits underneath without the limiter having to
# do anything.
LEVEL_ELIMINATION = -2.9

# How far one event's sound may drift from another of the same kind. Repeats
# are what makes an arcade mix tiring, and a power can activate six times in
# one Short; Orbit's rising cue is pure tone with no noise in it at all, so
# without this every Orbit activation in a battle would be the identical
# buffer. Both numbers are deliberately small - a third of a semitone and
# under a decibel - so this reads as variety rather than as a different
# sound, and both come from the event's own seed, so it stays deterministic.
VOICE_PITCH_SPREAD = 0.02
VOICE_LEVEL_TRIM_DB = 0.9

# The ambient bed's target level, as RMS rather than peak: it is a continuous
# sound and its peak says almost nothing about how present it feels.
AMBIENCE_RMS_DBFS = -33.0
AMBIENCE_FADE_IN = 0.5
AMBIENCE_FADE_OUT = 0.4

# The bed: three low partials at deliberately awkward ratios (1 : 1.513 :
# 2.333) so it reads as a hum rather than as a chord, each breathing on its
# own very slow LFO. No beat, no melody, nothing that repeats inside a Short.
AMBIENCE_PARTIALS = ((52.0, 1.00, 0.083), (78.7, 0.62, 0.061), (121.3, 0.34, 0.047))
AMBIENCE_LFO_DEPTH = 0.35
# A few cents of detune between channels, and independent noise per channel.
# Both widen the bed without the phase cancellation a delay would cause, so
# it survives being folded to mono on a phone speaker.
AMBIENCE_DETUNE = 0.0009
# The air layer is weighed against the partials by RMS, and it is the only
# part of the bed a small speaker can reproduce: the three partials are all
# under 130 Hz, and a phone rolls off long before that. Measured, the bed put
# 0.7% of its energy above 400 Hz, which meant the gaps between events were
# silent on the device most Shorts are watched on - the one thing the bed is
# there to prevent. Raised and opened up until that passband holds a faint
# room tone, and no further: it is still far below any event, still has no
# pitch of its own and still nothing that repeats.
AMBIENCE_AIR_LEVEL = 0.26
AMBIENCE_AIR_CUTOFF = 1300.0
# How many samples an ambience LFO is held for, and how far below the output
# rate its noise layer is generated. Both are shortcuts taken only because the
# bed is slow and band-limited; see `ambience` and `_air_layer`.
AMBIENCE_LFO_BLOCK = 128
AMBIENCE_AIR_DECIMATION = 8


@dataclass(frozen=True)
class Cue:
    """One rendered sound, at its designed level, ready to be placed.

    `name` is what the mix metadata counts, and is also how a listening audit
    says which identity it is hearing.
    """

    name: str
    buffer: array
    level_dbfs: float

    @property
    def length(self) -> int:
        return len(self.buffer)


def magnitude_factor(magnitude: float | None) -> float:
    """Where a hit sits in the damage window, as 0.0 (light) to 1.0 (heavy).

    Clamped at both ends. Everything magnitude influences - gain, decay and
    low-end weight - is driven from this one number, so there is a single
    place a damage value can affect a sound and it cannot escape [0, 1].
    """
    if magnitude is None:
        return HIT_MAGNITUDE_DEFAULT
    span = HIT_MAGNITUDE_LOUD - HIT_MAGNITUDE_QUIET
    return min(1.0, max(0.0, (float(magnitude) - HIT_MAGNITUDE_QUIET) / span))


def _finish(
    name: str, parts: list[tuple[int, array, float]], length: int, level: float
) -> Cue:
    """Layer, peak-normalise, then scale to `level` dBFS."""
    buffer = layer(length, parts)
    normalise_peak(buffer, 1.0)
    scale(buffer, db_to_gain(level))
    return Cue(name=name, buffer=buffer, level_dbfs=level)


def _level(bounds: tuple[float, float], factor: float) -> float:
    quiet, loud = bounds
    return quiet + (loud - quiet) * factor


def voice(seed: int) -> tuple[float, float]:
    """A pitch multiplier and a level trim for one event, from its own seed.

    Two draws from the same generator, so one seed decides both and neither
    can be predicted from the other. Applied to the tonal layers of a cue
    only: the noise inside a cue is already unique to the event, and moving
    a filter cutoff would change the sound's character rather than vary it.

    The level only ever goes down. A cue's designed level is part of a
    headroom budget - a heavy lethal hit, its elimination and the bed all
    land on one sample - and a variation that could add half a decibel would
    be a variation that could spend budget the mix does not have.
    """
    generator = Noise(stable_seed(seed, "voice"))
    return (
        1.0 + VOICE_PITCH_SPREAD * generator.sample(),
        0.5 * VOICE_LEVEL_TRIM_DB * (generator.sample() - 1.0),
    )


# --- hits -------------------------------------------------------------------


def impact_cue(magnitude: float | None, seed: int, sample_rate: int = SAMPLE_RATE) -> Cue:
    """Fighter into fighter: a low body and its fifth, a click, a noise crack.

    Heavier hits are longer, lower and carry more sub, which is the whole of
    what magnitude does here - the shape stays the same so ten rams in a row
    still sound like the same event.

    The mid click is louder than a mix on headphones would want it. It is the
    only part of this cue a phone speaker can reproduce - almost nothing below
    400 Hz survives one - and a ram is the most frequent hit in the game, so
    it is the layer that decides whether impacts are heard at all.
    """
    factor = magnitude_factor(magnitude)
    pitch, trim = voice(seed)
    length = seconds_to_samples(0.080 + 0.100 * factor, sample_rate)
    body_decay = 0.028 + 0.020 * factor
    body_freq = (124.0 - 22.0 * factor) * pitch

    parts = [
        (
            0,
            tone(
                length,
                freq=body_freq,
                freq_end=body_freq * 0.55,
                attack=0.0012,
                decay=body_decay,
                sample_rate=sample_rate,
            ),
            1.0,
        ),
        (
            0,
            tone(
                length,
                freq=body_freq * 0.62,
                freq_end=body_freq * 0.50,
                attack=0.0025,
                decay=body_decay * 1.5,
                sample_rate=sample_rate,
            ),
            0.16 + 0.40 * factor,
        ),
        (
            0,
            tone(
                min(length, seconds_to_samples(0.060, sample_rate)),
                freq=470.0 * pitch,
                freq_end=270.0 * pitch,
                attack=0.0008,
                decay=0.016,
                sample_rate=sample_rate,
            ),
            1.05,
        ),
        # The body's fifth. Same reason as Titan's harmonics: the thud's own
        # fundamental is under 110 Hz and a small speaker never gets it.
        (
            0,
            tone(
                min(length, seconds_to_samples(0.070, sample_rate)),
                freq=body_freq * 5.0,
                freq_end=body_freq * 2.75,
                attack=0.0012,
                decay=body_decay * 0.7,
                sample_rate=sample_rate,
            ),
            0.30,
        ),
        (
            0,
            noise_burst(
                min(length, seconds_to_samples(0.030, sample_rate)),
                seed=seed,
                decay=0.007,
                highpass=700.0,
                lowpass=3800.0,
                sample_rate=sample_rate,
            ),
            0.52,
        ),
    ]
    return _finish(
        f"hit/{HIT_IMPACT}", parts, length, _level(LEVEL_HIT[HIT_IMPACT], factor) + trim
    )


def projectile_cue(
    magnitude: float | None, seed: int, sample_rate: int = SAMPLE_RATE
) -> Cue:
    """Pulse bolt strike: a falling chirp with an electrical edge on it.

    The chirp and its 1.5x partner fall together, which is what makes it read
    as synthetic energy rather than as a tuned note, and the short high burst
    is the crack of arrival. Generated, not a laser sample.
    """
    factor = magnitude_factor(magnitude)
    pitch, trim = voice(seed)
    length = seconds_to_samples(0.110 + 0.060 * factor, sample_rate)

    parts = [
        (
            0,
            tone(
                length,
                freq=1650.0 * pitch,
                freq_end=360.0 * pitch,
                attack=0.0006,
                decay=0.040,
                sample_rate=sample_rate,
            ),
            1.0,
        ),
        (
            0,
            tone(
                length,
                freq=2475.0 * pitch,
                freq_end=540.0 * pitch,
                attack=0.0008,
                decay=0.022,
                sample_rate=sample_rate,
            ),
            0.30,
        ),
        (
            0,
            noise_burst(
                min(length, seconds_to_samples(0.020, sample_rate)),
                seed=seed,
                decay=0.0055,
                highpass=2600.0,
                sample_rate=sample_rate,
            ),
            0.55,
        ),
        (
            0,
            tone(
                min(length, seconds_to_samples(0.055, sample_rate)),
                freq=155.0 * pitch,
                freq_end=82.0 * pitch,
                attack=0.0015,
                decay=0.022,
                sample_rate=sample_rate,
            ),
            0.50 + 0.45 * factor,
        ),
    ]
    return _finish(
        f"hit/{HIT_PROJECTILE}",
        parts,
        length,
        _level(LEVEL_HIT[HIT_PROJECTILE], factor) + trim,
    )


def echo_hit_cue(
    magnitude: float | None, seed: int, sample_rate: int = SAMPLE_RATE
) -> Cue:
    """Echo clone strike: lighter, hollow, slightly haunted.

    Two tones a hair apart beat against each other at about seven times a
    second, which is the shimmer; the near-third-harmonic above them with no
    second harmonic underneath is what makes it hollow. Softer attack than
    every other hit, so a clone never lands like a ram.
    """
    factor = magnitude_factor(magnitude)
    pitch, trim = voice(seed)
    length = seconds_to_samples(0.160 + 0.080 * factor, sample_rate)
    base = 604.0 * pitch

    parts = [
        (
            0,
            tone(
                length,
                freq=base,
                attack=0.005,
                decay=0.075,
                sample_rate=sample_rate,
            ),
            1.0,
        ),
        (
            0,
            tone(
                length,
                freq=base * 1.012,
                attack=0.006,
                decay=0.070,
                sample_rate=sample_rate,
            ),
            0.72,
        ),
        (
            0,
            tone(
                length,
                freq=base * 2.98,
                attack=0.006,
                decay=0.045,
                sample_rate=sample_rate,
            ),
            0.22,
        ),
        (
            0,
            noise_burst(
                min(length, seconds_to_samples(0.014, sample_rate)),
                seed=seed,
                decay=0.0045,
                highpass=5200.0,
                sample_rate=sample_rate,
            ),
            0.16,
        ),
        (
            0,
            tone(
                min(length, seconds_to_samples(0.050, sample_rate)),
                freq=150.0 * pitch,
                freq_end=112.0 * pitch,
                attack=0.003,
                decay=0.020,
                sample_rate=sample_rate,
            ),
            0.22 + 0.20 * factor,
        ),
    ]
    return _finish(
        f"hit/{HIT_ECHO}", parts, length, _level(LEVEL_HIT[HIT_ECHO], factor) + trim
    )


def orbit_hit_cue(
    magnitude: float | None, seed: int, sample_rate: int = SAMPLE_RATE
) -> Cue:
    """Orbit bead strike: a small metallic ping with just enough body.

    The two partners above the ping sit at 1.71x and 2.76x - bell ratios, not
    harmonics - which is where the metal comes from. Short, bright and easy to
    hear four of in a row without it turning into noise.
    """
    factor = magnitude_factor(magnitude)
    pitch, trim = voice(seed)
    length = seconds_to_samples(0.130 + 0.070 * factor, sample_rate)
    base = 1284.0 * pitch

    parts = [
        (
            0,
            tone(
                length,
                freq=base,
                attack=0.0012,
                decay=0.058,
                sample_rate=sample_rate,
            ),
            1.0,
        ),
        (
            0,
            tone(
                length,
                freq=base * 1.71,
                attack=0.0012,
                decay=0.040,
                sample_rate=sample_rate,
            ),
            0.34,
        ),
        (
            0,
            tone(
                length,
                freq=base * 2.76,
                attack=0.0012,
                decay=0.026,
                sample_rate=sample_rate,
            ),
            0.22,
        ),
        (
            0,
            noise_burst(
                min(length, seconds_to_samples(0.008, sample_rate)),
                seed=seed,
                decay=0.0025,
                highpass=4000.0,
                sample_rate=sample_rate,
            ),
            0.20,
        ),
        (
            0,
            tone(
                min(length, seconds_to_samples(0.050, sample_rate)),
                freq=246.0 * pitch,
                freq_end=178.0 * pitch,
                attack=0.002,
                decay=0.020,
                sample_rate=sample_rate,
            ),
            0.30 + 0.25 * factor,
        ),
    ]
    return _finish(
        f"hit/{HIT_ORBIT}", parts, length, _level(LEVEL_HIT[HIT_ORBIT], factor) + trim
    )


HIT_CUES = {
    HIT_IMPACT: impact_cue,
    HIT_PROJECTILE: projectile_cue,
    HIT_ECHO: echo_hit_cue,
    HIT_ORBIT: orbit_hit_cue,
}


def hit_cue(
    subtype: str | None,
    magnitude: float | None,
    seed: int,
    sample_rate: int = SAMPLE_RATE,
) -> Cue:
    """The cue for a hit, falling back to the impact identity.

    An unknown subtype is a new entity kind that arrived without a sound
    designed for it. Falling back keeps the Short complete and audibly wrong
    in one place rather than silently missing a hit.
    """
    builder = HIT_CUES.get(subtype or "", impact_cue)
    return builder(magnitude, seed, sample_rate)


# --- power activations ------------------------------------------------------


def rush_cue(seed: int, sample_rate: int = SAMPLE_RATE) -> Cue:
    """Rush: a rising swell that gets out of the way fast.

    The long attack on every layer is the whole trick - the envelope swells
    into the sound instead of hitting it, which is what a burst of speed
    feels like.
    """
    pitch, trim = voice(seed)
    length = seconds_to_samples(0.190, sample_rate)
    parts = [
        (
            0,
            tone(
                length,
                freq=250.0 * pitch,
                freq_end=980.0 * pitch,
                attack=0.055,
                decay=0.055,
                sample_rate=sample_rate,
            ),
            1.0,
        ),
        (
            0,
            tone(
                length,
                freq=500.0 * pitch,
                freq_end=1960.0 * pitch,
                attack=0.060,
                decay=0.040,
                sample_rate=sample_rate,
            ),
            0.22,
        ),
        (
            0,
            noise_burst(
                length,
                seed=seed,
                attack=0.070,
                decay=0.045,
                highpass=900.0,
                lowpass=6500.0,
                sample_rate=sample_rate,
            ),
            0.55,
        ),
    ]
    return _finish(
        f"activate/{POWER_RUSH}", parts, length, LEVEL_ACTIVATE[POWER_RUSH] + trim
    )


def titan_cue(seed: int, sample_rate: int = SAMPLE_RATE) -> Cue:
    """Titan: mass arriving. A short thud, then everything falls.

    Both tonal layers sweep downward over a quarter of a second, which is the
    pitch cue for something getting bigger and heavier.

    Measured as two bare sine sweeps, this cue put a thousandth of its
    energy above 400 Hz, which made a Titan firing silent on a phone. The
    layers above are the third and fifth harmonics of the main sweep: a
    speaker that cannot reproduce 54 Hz still conveys the pitch if they are
    there, and they cost nothing in identity because they move with it.
    """
    pitch, trim = voice(seed)
    length = seconds_to_samples(0.260, sample_rate)
    parts = [
        (
            0,
            noise_burst(
                min(length, seconds_to_samples(0.030, sample_rate)),
                seed=seed,
                decay=0.014,
                lowpass=2600.0,
                sample_rate=sample_rate,
            ),
            0.60,
        ),
        (
            0,
            tone(
                length,
                freq=186.0 * pitch,
                freq_end=54.0 * pitch,
                attack=0.004,
                decay=0.095,
                sample_rate=sample_rate,
            ),
            1.0,
        ),
        (
            0,
            tone(
                length,
                freq=93.0 * pitch,
                freq_end=41.0 * pitch,
                attack=0.006,
                decay=0.130,
                sample_rate=sample_rate,
            ),
            0.62,
        ),
        # The third and fifth of the main sweep. They follow it exactly, so
        # the pitch and the movement are unchanged - what they add is the
        # only part of this cue a phone can reproduce.
        (
            0,
            tone(
                length,
                freq=558.0 * pitch,
                freq_end=162.0 * pitch,
                attack=0.003,
                decay=0.075,
                sample_rate=sample_rate,
            ),
            0.34,
        ),
        (
            0,
            tone(
                length,
                freq=930.0 * pitch,
                freq_end=270.0 * pitch,
                attack=0.003,
                decay=0.055,
                sample_rate=sample_rate,
            ),
            0.19,
        ),
    ]
    return _finish(
        f"activate/{POWER_TITAN}", parts, length, LEVEL_ACTIVATE[POWER_TITAN] + trim
    )


def pulse_cue(seed: int, sample_rate: int = SAMPLE_RATE) -> Cue:
    """Pulse: the launch. A rising zap, deliberately the inverse of the hit.

    The bolt's strike falls and its launch rises, so a viewer hears the shot
    leave and hears it land without the two being the same sound twice.
    """
    pitch, trim = voice(seed)
    length = seconds_to_samples(0.160, sample_rate)
    parts = [
        (
            0,
            tone(
                length,
                freq=370.0 * pitch,
                freq_end=1780.0 * pitch,
                attack=0.003,
                decay=0.045,
                sample_rate=sample_rate,
            ),
            1.0,
        ),
        (
            0,
            tone(
                length,
                freq=555.0 * pitch,
                freq_end=2670.0 * pitch,
                attack=0.004,
                decay=0.030,
                sample_rate=sample_rate,
            ),
            0.26,
        ),
        (
            0,
            noise_burst(
                min(length, seconds_to_samples(0.024, sample_rate)),
                seed=seed,
                decay=0.007,
                highpass=3000.0,
                sample_rate=sample_rate,
            ),
            0.42,
        ),
        (
            0,
            tone(
                min(length, seconds_to_samples(0.055, sample_rate)),
                freq=205.0 * pitch,
                freq_end=140.0 * pitch,
                attack=0.002,
                decay=0.020,
                sample_rate=sample_rate,
            ),
            0.34,
        ),
    ]
    return _finish(
        f"activate/{POWER_PULSE}", parts, length, LEVEL_ACTIVATE[POWER_PULSE] + trim
    )


def echo_activate_cue(seed: int, sample_rate: int = SAMPLE_RATE) -> Cue:
    """Echo: two airy pulses, the second a quieter copy of the first.

    Saying the same thing twice is the point. The repeat is detuned very
    slightly rather than being identical, so it sounds like a reflection
    instead of a buffer played again.
    """
    pitch, trim = voice(seed)
    length = seconds_to_samples(0.220, sample_rate)
    gap = seconds_to_samples(0.086, sample_rate)
    chime = seconds_to_samples(0.120, sample_rate)
    air = seconds_to_samples(0.030, sample_rate)

    parts = []
    for index, (offset, gain, detune) in enumerate(((0, 1.0, 1.0), (gap, 0.58, 1.014))):
        parts.append(
            (
                offset,
                tone(
                    chime,
                    freq=880.0 * detune * pitch,
                    attack=0.008,
                    decay=0.048,
                    sample_rate=sample_rate,
                ),
                gain,
            )
        )
        parts.append(
            (
                offset,
                tone(
                    chime,
                    freq=1320.0 * detune * pitch,
                    attack=0.009,
                    decay=0.034,
                    sample_rate=sample_rate,
                ),
                gain * 0.34,
            )
        )
        parts.append(
            (
                offset,
                noise_burst(
                    air,
                    seed=stable_seed(seed, "echo-air", index),
                    attack=0.004,
                    decay=0.010,
                    highpass=4200.0,
                    sample_rate=sample_rate,
                ),
                gain * 0.16,
            )
        )
    return _finish(
        f"activate/{POWER_ECHO}", parts, length, LEVEL_ACTIVATE[POWER_ECHO] + trim
    )


def orbit_activate_cue(seed: int, sample_rate: int = SAMPLE_RATE) -> Cue:
    """Orbit: three small energy tones climbing as the beads spin up.

    Evenly spaced in frequency rather than in pitch, so it climbs without
    landing on a chord, and each tone carries the same inharmonic partner the
    bead strike does - the activation and the hit belong to each other.
    """
    pitch, trim = voice(seed)
    length = seconds_to_samples(0.290, sample_rate)
    step = seconds_to_samples(0.062, sample_rate)
    body = seconds_to_samples(0.110, sample_rate)

    parts = [
        (
            0,
            tone(
                seconds_to_samples(0.060, sample_rate),
                freq=210.0 * pitch,
                freq_end=170.0 * pitch,
                attack=0.003,
                decay=0.022,
                sample_rate=sample_rate,
            ),
            0.22,
        )
    ]
    for index, (base, gain) in enumerate(((720.0, 1.0), (960.0, 0.88), (1200.0, 0.80))):
        offset = index * step
        freq = base * pitch
        parts.append(
            (
                offset,
                tone(
                    body, freq=freq, attack=0.0025, decay=0.040, sample_rate=sample_rate
                ),
                gain,
            )
        )
        parts.append(
            (
                offset,
                tone(
                    body,
                    freq=freq * 2.41,
                    attack=0.0025,
                    decay=0.020,
                    sample_rate=sample_rate,
                ),
                gain * 0.14,
            )
        )
    return _finish(
        f"activate/{POWER_ORBIT}", parts, length, LEVEL_ACTIVATE[POWER_ORBIT] + trim
    )


ACTIVATION_CUES = {
    POWER_RUSH: rush_cue,
    POWER_TITAN: titan_cue,
    POWER_PULSE: pulse_cue,
    POWER_ECHO: echo_activate_cue,
    POWER_ORBIT: orbit_activate_cue,
}


def activation_cue(
    power: str | None, seed: int, sample_rate: int = SAMPLE_RATE
) -> Cue | None:
    """The cue for a power firing, or None if that power has no sound yet.

    None rather than a fallback: an unknown power is a gameplay addition, and
    a missing announcement is a smaller lie than announcing it as Rush.
    """
    builder = ACTIVATION_CUES.get(power or "")
    return None if builder is None else builder(seed, sample_rate)


# --- elimination ------------------------------------------------------------

# The boom starts this far into the cue. The cue itself still begins exactly
# on the event's tick - the bright transient is at offset zero - but the
# weight arrives just after, which leaves room for the lethal hit's own
# transient instead of stacking two peaks on one sample.
ELIMINATION_BOOM_OFFSET = 0.030


def elimination_cue(seed: int, sample_rate: int = SAMPLE_RATE) -> Cue:
    """The strongest single sound in a Short: a boom under a finishing tone.

    Final without being loud. Most of the level is below 120 Hz, where peak
    amplitude buys weight rather than volume, and the bright tone on top is
    what makes it read as an ending rather than as one more big hit.
    """
    pitch, trim = voice(seed)
    length = seconds_to_samples(0.480, sample_rate)
    boom_at = seconds_to_samples(ELIMINATION_BOOM_OFFSET, sample_rate)

    parts = [
        (
            0,
            tone(
                seconds_to_samples(0.200, sample_rate),
                freq=1560.0 * pitch,
                freq_end=1160.0 * pitch,
                attack=0.0025,
                decay=0.085,
                sample_rate=sample_rate,
            ),
            0.52,
        ),
        (
            0,
            tone(
                seconds_to_samples(0.160, sample_rate),
                freq=2340.0 * pitch,
                freq_end=1740.0 * pitch,
                attack=0.0025,
                decay=0.048,
                sample_rate=sample_rate,
            ),
            0.16,
        ),
        (
            0,
            noise_burst(
                seconds_to_samples(0.030, sample_rate),
                seed=stable_seed(seed, "elimination-crack"),
                decay=0.008,
                highpass=1800.0,
                lowpass=9000.0,
                sample_rate=sample_rate,
            ),
            0.35,
        ),
        (
            boom_at,
            tone(
                length - boom_at,
                freq=128.0 * pitch,
                freq_end=42.0 * pitch,
                attack=0.004,
                decay=0.155,
                sample_rate=sample_rate,
            ),
            1.0,
        ),
        (
            boom_at,
            tone(
                length - boom_at,
                freq=64.0 * pitch,
                freq_end=34.0 * pitch,
                attack=0.008,
                decay=0.210,
                sample_rate=sample_rate,
            ),
            0.70,
        ),
        (
            0,
            noise_burst(
                seconds_to_samples(0.300, sample_rate),
                seed=stable_seed(seed, "elimination-air"),
                attack=0.030,
                decay=0.100,
                highpass=300.0,
                lowpass=5200.0,
                sample_rate=sample_rate,
            ),
            0.20,
        ),
    ]
    return _finish("elimination", parts, length, LEVEL_ELIMINATION + trim)


# --- ambience ---------------------------------------------------------------


def ambience(
    length: int,
    *,
    seed: int,
    sample_rate: int = SAMPLE_RATE,
    target_dbfs: float = AMBIENCE_RMS_DBFS,
    fade_in: float = AMBIENCE_FADE_IN,
    fade_out: float = AMBIENCE_FADE_OUT,
) -> tuple[array, array]:
    """The arena's room tone: a quiet hum that runs the whole length.

    It exists so the gaps between events are not digital silence. There is no
    beat and no melody in it by construction - three partials at inharmonic
    ratios, each on its own very slow amplitude LFO, with a whisper of
    low-passed noise for air. It is calibrated by RMS rather than trimmed by
    ear, so a longer battle is exactly as present as a shorter one.

    Returns the two channels. The fade-out is measured back from `length`, so
    a Short's ambience always ends on the last sample of the post-roll.
    """
    left = silence(length)
    right = silence(length)
    if length == 0:
        return left, right

    two_pi = 2.0 * math.pi
    sin = math.sin
    for index, (channel, detune, lfo_phase) in enumerate(
        ((left, 1.0 - AMBIENCE_DETUNE, 0.0), (right, 1.0 + AMBIENCE_DETUNE, two_pi / 3.0))
    ):
        # All three partials in one pass. Their LFOs are held for a block at a
        # time: at a twelfth of a hertz the level moves by well under a
        # millionth across 128 samples, which is far below what 24-bit PCM can
        # even represent, and it takes two thirds of the sine calls out of the
        # longest loop in the package.
        angles = [0.0, 0.0, 0.0]
        steps = [two_pi * freq * detune / sample_rate for freq, _, _ in AMBIENCE_PARTIALS]
        lfo_angles = [lfo_phase, lfo_phase, lfo_phase]
        lfo_steps = [two_pi * lfo_hz / sample_rate for _, _, lfo_hz in AMBIENCE_PARTIALS]
        weights = [weight for _, weight, _ in AMBIENCE_PARTIALS]
        depths = [1.0, 1.0, 1.0]

        for position in range(length):
            if position % AMBIENCE_LFO_BLOCK == 0:
                for partial in range(3):
                    depths[partial] = weights[partial] * (
                        1.0 - AMBIENCE_LFO_DEPTH * (0.5 - 0.5 * sin(lfo_angles[partial]))
                    )
                    lfo_angles[partial] += lfo_steps[partial] * AMBIENCE_LFO_BLOCK
            channel[position] = (
                depths[0] * sin(angles[0])
                + depths[1] * sin(angles[1])
                + depths[2] * sin(angles[2])
            )
            angles[0] += steps[0]
            angles[1] += steps[1]
            angles[2] += steps[2]

        air = _air_layer(
            length,
            stable_seed(seed, "ambience-air", index),
            sample_rate,
            AMBIENCE_AIR_CUTOFF,
        )
        # Three one-pole stages take a lot of level out of white noise, so the
        # air layer is matched to the partials by RMS before it is weighed in.
        air_rms = rms(air)
        if air_rms > 0.0:
            scale(air, AMBIENCE_AIR_LEVEL * rms(channel) / air_rms)
            for position in range(length):
                channel[position] += air[position]

    gain = db_to_gain(target_dbfs) / max(1e-12, 0.5 * (rms(left) + rms(right)))
    scale(left, gain)
    scale(right, gain)

    _fade(left, right, length, fade_in, fade_out, sample_rate)
    return left, right


def _air_layer(
    length: int,
    seed: int,
    sample_rate: int,
    cutoff: float,
    decimation: int = AMBIENCE_AIR_DECIMATION,
) -> array:
    """Low-passed noise for the bed, generated below the output rate.

    The air is band-limited to well under a kilohertz, so there is nothing
    above 3 kHz for a full-rate generator to contribute. Producing it at an
    eighth of the rate and interpolating back up is the same sound for an
    eighth of the work, and just as deterministic - the PRNG is still seeded
    from the replay and still draws the same numbers in the same order.
    """
    if length == 0:
        return silence(0)
    coarse_rate = max(1, sample_rate // decimation)
    coarse = Noise(seed).fill(length // decimation + 2)
    low_pass(coarse, cutoff, sample_rate=coarse_rate, stages=2)

    out = silence(length)
    for index in range(length):
        position = index / decimation
        base = int(position)
        fraction = position - base
        out[index] = coarse[base] * (1.0 - fraction) + coarse[base + 1] * fraction
    return out


def _fade(
    left: array,
    right: array,
    length: int,
    fade_in: float,
    fade_out: float,
    sample_rate: int,
) -> None:
    """Linear fades at both ends, sized from the exact sample count."""
    rise = min(length, max(0, seconds_to_samples(fade_in, sample_rate)))
    fall = min(length, max(0, seconds_to_samples(fade_out, sample_rate)))
    for index in range(rise):
        factor = (index + 1) / rise
        left[index] *= factor
        right[index] *= factor
    for offset in range(fall):
        index = length - 1 - offset
        factor = (offset + 1) / fall
        left[index] *= factor
        right[index] *= factor

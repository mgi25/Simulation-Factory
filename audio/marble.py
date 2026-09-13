"""What a marble machine sounds like, built from the replay it is made of.

`audio.cues` is the battle format's voice. This is the sloped race's, and it
shares only `audio.synthesis` - oscillators, envelopes, filters and a seeded
noise source - so every sample here is still arithmetic in this repository and
the finished Short carries nobody's rights but ours.

## The design, in one paragraph

A 20 mm acrylic marble in a pearl channel is a *small, bright, short* sound: a
click of contact, a body resonance a few hundred hertz up, and a ring above that
which dies in a twentieth of a second. It is never a gunshot and never a boing.
So every impact here is three layers on that model, the module it happened in
chooses the body frequency, and the strength of the contact chooses the level
and how much click there is relative to body. The continuous layer underneath is
the field *rolling*, which is filtered noise whose brightness and level follow
the speed the physics actually recorded - so the machine gets louder because the
marbles got faster, not because a fader moved.

## Everything is placed by what happened, not by the clock

`sloped.presentation` converts replay seconds to finished-film seconds through
the edit and the held opening frame, and it measures an impact as the velocity
change **gravity cannot explain**. Both matter here. Without the first, three and
a half seconds of omitted mixing would still make noise; without the second, nine
tenths of the "impacts" would be marbles falling, because free fall changes a
60 Hz frame's velocity by 4.0875 wu/s and that is the ninetieth percentile of
the raw signal.

## Music

A short instrumental bed, also synthesised here: a pulse, a bass note per bar
and a three-note figure, on a minor progression that adds a layer roughly every
four bars and resolves on the last. It is mixed a long way under the machine -
the brief is explicit that it must not hide the marbles - and it is built from
the same oscillators, so it is as original as the rest.
"""

from __future__ import annotations

import math
from array import array
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from audio.synthesis import (
    Noise,
    SAMPLE_RATE,
    add_into,
    db_to_gain,
    envelope,
    high_pass,
    low_pass,
    noise_burst,
    peak,
    rms,
    scale,
    seconds_to_samples,
    silence,
    stable_seed,
    tone,
)

__all__ = [
    "BODY_HZ",
    "CUES",
    "Cues",
    "RaceMix",
    "build_race_audio",
    "impact_cue",
    "lift_cue",
    "mechanism_bed",
    "release_cue",
    "whoosh_cue",
    "split_cue",
    "crossing_cue",
]


@dataclass(frozen=True)
class Cues:
    """Which of the non-diegetic cues an edition uses.

    **This exists because V22.1 had to stop making one sound, and hard-muting a
    timestamp would have broken every older edition's rebuild.** The two flags
    are policies rather than switches for one film:

    `omission` marks time the edit skipped, with `whoosh_cue`. V19 through V22
    want it: their omission is placed across the rotor's spin-down, so the
    picture changes in a way that needs explaining and a cue says "that was
    deliberate". V22.1 does not: its omission is four whole rotor revolutions
    inside the constant-rate spin, and the blades, the hub and the field are all
    continuous across it to a hundredth of a degree. The whole claim is that the
    viewer does not notice, and a whoosh over an invisible join does not explain
    an edit - it announces one that was not otherwise there.

    `mechanism` is the mixer's own machinery: a drone that follows the recorded
    rotor rate, so the spin-down is *heard* as the rotor slowing, and a cue on
    the blades lifting out of the drum. Only V22.1 keeps enough of that on
    screen to be worth sounding - see `sloped.v221.START` - and an edition that
    shows 0.267 s of it would be scoring a shot it does not have.
    """

    omission: bool = True
    mechanism: bool = False


# The default is every edition before V22.1, unchanged.
CUES: dict[str, Cues] = {
    "default": Cues(),
    "v221": Cues(omission=False, mechanism=True),
}


# --- levels ----------------------------------------------------------------
#
# Peak dBFS per voice, budgeted so that the loudest ordinary contact sits a good
# 8 dB under the winner's crossing and the music never competes. These are
# designed levels: the master stage lifts the whole timeline once at the end and
# never trims a voice that has already been placed.

# **These are relative to the winner's crossing, and the whole budget is then
# dropped by `HEADROOM` so the limiter has almost nothing to do.**
#
# The first version of this mix set the winner at -2.5 dBFS, which is a sensible
# level for the loudest thing in a film until you add a bed and two hundred
# contacts underneath it. The sum arrived at +0.98 dBFS, the limiter pulled 2.3
# dB out of it, and every accent in the finish came out at exactly -1.31 dBFS:
# the winner, second place, and the fourth-fifth dead heat all identical,
# because a limiter working that hard is a machine for removing the difference
# between loud things. The brief asks for the opposite in as many words -
# "finish payoff clearly stronger than ordinary contacts".
#
# So the budget is quiet enough that nothing needs catching, and `master` is
# asked to `trim`: one gain over the whole timeline that puts the peak exactly
# on the ceiling and leaves every relationship below it untouched.
HEADROOM = -9.0

LEVEL_CROSS_WINNER = HEADROOM + 0.0
LEVEL_CROSS_PHOTO = HEADROOM - 3.0      # fourth and fifth, 0.017 s apart
LEVEL_CROSS_OTHER = HEADROOM - 6.5
LEVEL_TRAPDOOR = HEADROOM - 4.0
LEVEL_GATE = HEADROOM - 7.0
LEVEL_WHOOSH = HEADROOM - 10.0
# The mixer's machinery.
#
# **-26 rather than the -19 this started at, and the seven decibels are the
# finish.** The drone is a *continuous* voice, and the one stretch it is loudest
# over - the rotor at full rate, replay 1.6 to 4.6 - is also where the field is
# pouring down the apron and throwing its hardest contacts. Summed, the two put
# the loudest moment of the whole film at output 5.76 s, which is the mixer:
# `tools/sloped_short_qc.py` checks that the winner's crossing is the loudest
# moment and it correctly failed. At -26 the crossing is the peak again and the
# mechanism is still plainly the subject where it should be - measured against
# the same mix with `mechanism=False`, it adds 8.5 dB under the mix, 2.3 dB
# through the spin-down, and 0.0 dB once the rotor has stopped, which is the
# shape the machine actually has.
LEVEL_MECHANISM = HEADROOM - 26.0
LEVEL_LIFT = HEADROOM - 9.0
LEVEL_SPLIT = HEADROOM - 11.0
LEVEL_IMPACT_LOUD = HEADROOM - 12.0
LEVEL_IMPACT_QUIET = HEADROOM - 28.0
LEVEL_ROLL = HEADROOM - 21.0
LEVEL_MUSIC = HEADROOM - 19.0
LEVEL_AMBIENCE = HEADROOM - 31.0

# How hard the rolling bed follows speed.
#
# **The physics and the film disagree here, and the film has to win a little.**
# The fastest the field ever moves is the long descent at 5 to 8 seconds, so a
# bed that tracks speed faithfully is loudest in the middle of the race and has
# spent the headroom by the time anyone reaches the line - measured, the descent
# sat at -13 dBFS and the winner's crossing at -13.3, which is the opposite of
# what a finish should do. An exponent under one keeps the bed's *shape* - it
# still rises and falls with the race - while compressing how far it travels, so
# the discrete accents at the line have somewhere to land.
ROLL_RESPONSE = 0.85

# A contact this weak is texture and one this strong is the hardest hit in the
# race; everything between maps onto the level range above.
IMPACT_SOFT = 6.0
IMPACT_HARD = 42.0

# The mixer's own two numbers. `ShuffleFloor` carries four paddles on one hub,
# so the chop a viewer hears is four a revolution; `MOTOR_HZ` is where the drive
# sits at full rate, low enough to read as a machine under load and high enough
# to survive a phone speaker's roll-off.
BLADES = 4
MOTOR_HZ = 112.0

# How far a sound may be pushed off centre by where it is on screen. Restrained
# on purpose: a phone speaker is mono and a wide mix collapses to nothing.
MAX_PAN = 0.55

# The body resonance of each part of the machine, in hertz. A marble in the
# start drum is inside a 2.7-unit acrylic wall and rings higher and longer than
# one in an open channel; the finish deck is a big flat plate and rings lower.
BODY_HZ = {
    "start": 720.0,
    "mixer": 660.0,
    "shuffle": 690.0,
    "launch": 480.0,
    "leg1": 430.0,
    "leg2": 430.0,
    "leg3": 430.0,
    "obstacle": 250.0,
    "blue_lead": 470.0,
    "orange_lead": 470.0,
    "blue": 450.0,
    "orange": 450.0,
    "merge_lead": 400.0,
    "merge": 360.0,
    "final": 410.0,
    "finish": 300.0,
}
BODY_DEFAULT = 450.0


# --- voices ----------------------------------------------------------------


def impact_cue(
    magnitude: float,
    body_hz: float,
    seed: int,
    *,
    sample_rate: int = SAMPLE_RATE,
) -> array:
    """One contact: a click, a body resonance and a ring above it.

    `magnitude` is the wu/s of velocity gravity did not account for. It moves
    three things at once, which is what makes a hard contact sound hard rather
    than merely loud: the click gets brighter and louder relative to the body,
    the body is pitched slightly up by the extra stiffness of a fast contact,
    and the whole thing lasts longer.
    """
    force = min(1.0, max(0.0, (magnitude - IMPACT_SOFT) / (IMPACT_HARD - IMPACT_SOFT)))
    length = seconds_to_samples(0.045 + 0.075 * force, sample_rate)
    out = silence(length)

    click = noise_burst(
        min(length, seconds_to_samples(0.010 + 0.006 * force, sample_rate)),
        seed=seed,
        attack=0.0004,
        decay=0.0025 + 0.0020 * force,
        highpass=1500.0 + 2200.0 * force,
        lowpass=11000.0,
        stages=2,
        sample_rate=sample_rate,
    )
    add_into(out, click, 0, 0.42 + 0.40 * force)

    pitch = body_hz * (1.0 + 0.16 * force)
    body = tone(
        length,
        freq=pitch,
        freq_end=pitch * 0.955,
        attack=0.0007,
        decay=0.018 + 0.030 * force,
        sample_rate=sample_rate,
    )
    add_into(out, body, 0, 0.66)

    ring = tone(
        length,
        freq=pitch * 2.71,
        freq_end=pitch * 2.66,
        attack=0.0006,
        decay=0.012 + 0.022 * force,
        sample_rate=sample_rate,
    )
    add_into(out, ring, 0, 0.20 + 0.16 * force)

    largest = peak(out)
    if largest > 0.0:
        scale(out, 1.0 / largest)
    return out


def release_cue(
    seed: int,
    *,
    weight: float = 1.0,
    sample_rate: int = SAMPLE_RATE,
) -> array:
    """A mechanism letting go: latch, slide, and the air under what falls.

    `weight` separates the two releases this race has. At 0.45 it is the start
    gates opening under a settled field; at 1.0 it is the trapdoor, eighteen
    slats dropping at once with eight marbles on them.
    """
    length = seconds_to_samples(0.34 + 0.30 * weight, sample_rate)
    out = silence(length)

    latch = noise_burst(
        seconds_to_samples(0.022, sample_rate),
        seed=seed,
        attack=0.0003,
        decay=0.004,
        highpass=900.0,
        lowpass=7000.0,
        sample_rate=sample_rate,
    )
    add_into(out, latch, 0, 0.55)

    # The mechanism's own body: a low thunk that sags as the weight comes off.
    thunk = tone(
        seconds_to_samples(0.20 + 0.18 * weight, sample_rate),
        freq=132.0 - 34.0 * weight,
        freq_end=74.0 - 20.0 * weight,
        attack=0.0016,
        decay=0.055 + 0.050 * weight,
        sample_rate=sample_rate,
    )
    add_into(out, thunk, seconds_to_samples(0.004, sample_rate), 0.78 * (0.6 + 0.4 * weight))

    # The slide: filtered noise opening and closing as the slats travel.
    slide = noise_burst(
        seconds_to_samples(0.16 + 0.14 * weight, sample_rate),
        seed=seed ^ 0x5A17,
        attack=0.012,
        decay=0.070,
        highpass=240.0,
        lowpass=2600.0 + 900.0 * weight,
        sample_rate=sample_rate,
    )
    add_into(out, slide, seconds_to_samples(0.010, sample_rate), 0.34)

    largest = peak(out)
    if largest > 0.0:
        scale(out, 1.0 / largest)
    return out


def whoosh_cue(
    seed: int,
    *,
    seconds: float = 0.30,
    sample_rate: int = SAMPLE_RATE,
) -> array:
    """Air moving past: band-passed noise swept up and away.

    The film's one intentional time jump is marked with this and nothing else.
    A cut that needs a graphic to be understood is a cut in the wrong place; a
    cut that is *heard* to be deliberate needs about a quarter of a second of
    moving air.
    """
    length = seconds_to_samples(seconds, sample_rate)
    noise = Noise(seed).fill(length)
    # A sweeping one-pole low-pass: the cutoff climbs, so the noise opens out
    # and then the envelope takes it away.
    state = 0.0
    for index in range(length):
        position = index / max(1, length - 1)
        cutoff = 320.0 * math.exp(math.log(5200.0 / 320.0) * position)
        alpha = 1.0 - math.exp(-2.0 * math.pi * cutoff / sample_rate)
        state += alpha * (noise[index] - state)
        noise[index] = state
    high_pass(noise, 260.0, sample_rate=sample_rate, stages=2)
    shape = envelope(length, attack=0.070, decay=0.085, sample_rate=sample_rate)
    for index in range(length):
        noise[index] *= shape[index]
    largest = peak(noise)
    if largest > 0.0:
        scale(noise, 1.0 / largest)
    return noise


def crossing_cue(
    seed: int,
    *,
    winner: bool = False,
    sample_rate: int = SAMPLE_RATE,
) -> array:
    """A racer crossing the line: the contact, plus a note that says it counted.

    The winner's is a fifth higher, twice as long and has a second voice under
    it. Everyone else's is the same shape kept small, so a photo finish reads as
    two of the same sound a seventeenth of a second apart rather than as one
    event with an echo.
    """
    length = seconds_to_samples(0.62 if winner else 0.26, sample_rate)
    out = silence(length)

    strike = noise_burst(
        seconds_to_samples(0.014, sample_rate),
        seed=seed,
        attack=0.0004,
        decay=0.0035,
        highpass=2400.0,
        lowpass=12000.0,
        sample_rate=sample_rate,
    )
    add_into(out, strike, 0, 0.5)

    root = 784.0 if winner else 523.25
    add_into(
        out,
        tone(length, freq=root, attack=0.0015, decay=0.115 if winner else 0.055,
             sample_rate=sample_rate),
        0,
        0.62,
    )
    add_into(
        out,
        tone(length, freq=root * 1.5, attack=0.0018, decay=0.095 if winner else 0.042,
             sample_rate=sample_rate),
        seconds_to_samples(0.004, sample_rate),
        0.34,
    )
    if winner:
        # An octave below, arriving a beat later: the part that reads as a result.
        add_into(
            out,
            tone(length, freq=root * 0.5, attack=0.004, decay=0.170,
                 sample_rate=sample_rate),
            seconds_to_samples(0.028, sample_rate),
            0.52,
        )
    largest = peak(out)
    if largest > 0.0:
        scale(out, 1.0 / largest)
    return out


def split_cue(seed: int, *, sample_rate: int = SAMPLE_RATE) -> array:
    """The field committing to a route: a soft swell that opens outward.

    **The same sound for both branches, at the same level.** The brief is
    explicit that neither route may be made to sound like the scripted winner,
    and the cheapest way to guarantee that is to have only one cue and place it
    twice - once when the first marble commits to orange, once when the first
    commits to blue - panned to where each of them is on screen and nothing
    else. There is no arrangement of two identical sounds that favours one.

    It is a swell rather than a chime: a bell at the fork would read as a prize.
    """
    length = seconds_to_samples(0.44, sample_rate)
    out = silence(length)
    for freq, gain, delay in ((294.0, 0.60, 0.0), (440.0, 0.44, 0.012), (588.0, 0.22, 0.026)):
        add_into(
            out,
            tone(length, freq=freq, attack=0.055, decay=0.130, sample_rate=sample_rate),
            seconds_to_samples(delay, sample_rate),
            gain,
        )
    air = noise_burst(
        length,
        seed=seed,
        attack=0.045,
        decay=0.105,
        highpass=1100.0,
        lowpass=6400.0,
        sample_rate=sample_rate,
    )
    add_into(out, air, 0, 0.20)
    largest = peak(out)
    if largest > 0.0:
        scale(out, 1.0 / largest)
    return out


def rolling_bed(
    speeds: Sequence[tuple[float, float, float]],
    length: int,
    seed: int,
    *,
    sample_rate: int = SAMPLE_RATE,
) -> array:
    """The field rolling: noise whose brightness and level follow real speed.

    `speeds` is `(output second, mean speed, fastest speed)` per output frame
    from `presentation.rolling`. Between frames the control values are linearly
    interpolated, so the bed moves at the rate the race does and there are no
    steps in it.

    The cutoff is tied to the *mean* and the level to a blend of mean and
    fastest, which is what makes a field that has strung out sound busier than
    one marble going the same speed.
    """
    out = Noise(seed).fill(length)
    if not speeds:
        return silence(length)

    ordered = sorted(speeds)
    times = [row[0] for row in ordered]
    fastest_speed = max(max(row[1], row[2]) for row in ordered) or 1.0

    state = 0.0
    cursor = 0
    for index in range(length):
        when = index / sample_rate
        while cursor + 1 < len(times) and times[cursor + 1] <= when:
            cursor += 1
        low = ordered[cursor]
        high = ordered[min(cursor + 1, len(ordered) - 1)]
        span = max(1e-6, high[0] - low[0])
        blend = min(1.0, max(0.0, (when - low[0]) / span))
        mean = low[1] + (high[1] - low[1]) * blend
        top = low[2] + (high[2] - low[2]) * blend

        drive = min(1.0, (0.55 * mean + 0.45 * top) / fastest_speed)
        cutoff = 260.0 + 2400.0 * min(1.0, mean / fastest_speed) ** 0.7
        alpha = 1.0 - math.exp(-2.0 * math.pi * cutoff / sample_rate)
        state += alpha * (out[index] - state)
        out[index] = state * (drive ** ROLL_RESPONSE)

    high_pass(out, 150.0, sample_rate=sample_rate, stages=1)
    largest = peak(out)
    if largest > 0.0:
        scale(out, 1.0 / largest)
    return out


# --- music ------------------------------------------------------------------

# A minor and its relative: i - VI - III - VII, the plainest four-bar loop that
# rises without going anywhere, which is what a twenty-second race needs. Roots
# in hertz, A2 up.
PROGRESSION = (110.00, 87.31, 130.81, 98.00)
BEATS_PER_MINUTE = 126.0


def music_bed(
    length: int,
    seed: int,
    *,
    build_from: float,
    sample_rate: int = SAMPLE_RATE,
) -> array:
    """A short instrumental bed that adds a layer every four bars and resolves.

    `build_from` is the output second the last section starts, which is where
    the figure doubles up and the bass goes to every beat. Everything is one
    oscillator per note; there is no sample and no loop in it.
    """
    out = silence(length)
    beat = 60.0 / BEATS_PER_MINUTE
    beats = int(length / sample_rate / beat) + 1

    for index in range(beats):
        when = index * beat
        at = seconds_to_samples(when, sample_rate)
        if at >= length:
            break
        bar = index // 4
        root = PROGRESSION[bar % len(PROGRESSION)]
        late = when >= build_from
        intensity = min(1.0, 0.30 + 0.16 * bar) * (1.25 if late else 1.0)

        # Bass: the root on the downbeat, and on every beat once it builds.
        if index % 4 == 0 or late:
            add_into(
                out,
                tone(
                    seconds_to_samples(beat * 0.92, sample_rate),
                    freq=root,
                    attack=0.006,
                    decay=0.16,
                    sample_rate=sample_rate,
                ),
                at,
                0.50 * intensity,
            )
        # Pulse: a soft filtered tick on every beat, the thing that carries time.
        tick = noise_burst(
            seconds_to_samples(0.055, sample_rate),
            seed=seed ^ (index * 2654435761),
            attack=0.0008,
            decay=0.016,
            highpass=3200.0,
            lowpass=9000.0,
            sample_rate=sample_rate,
        )
        add_into(out, tick, at, 0.20 * intensity)

        # The figure: root, fifth, octave, an eighth apart, from the second bar.
        if bar >= 1:
            for step, ratio in enumerate((2.0, 3.0, 4.0)):
                offset = at + seconds_to_samples(beat * 0.5 * step, sample_rate)
                if offset >= length:
                    break
                add_into(
                    out,
                    tone(
                        seconds_to_samples(beat * 0.45, sample_rate),
                        freq=root * ratio,
                        attack=0.004,
                        decay=0.085,
                        sample_rate=sample_rate,
                    ),
                    offset,
                    (0.16 + 0.05 * bar) * (1.4 if late else 1.0),
                )

    low_pass(out, 7600.0, sample_rate=sample_rate, stages=1)
    # Resolve rather than stop: the last half second falls away under itself.
    tail = seconds_to_samples(0.55, sample_rate)
    for index in range(max(0, length - tail), length):
        position = (length - index) / tail
        out[index] *= position * position
    largest = peak(out)
    if largest > 0.0:
        scale(out, 1.0 / largest)
    return out


def ambience_bed(length: int, seed: int, *, sample_rate: int = SAMPLE_RATE) -> array:
    """Room tone: the space the machine is standing in, and nothing else."""
    out = Noise(seed).fill(length)
    low_pass(out, 420.0, sample_rate=sample_rate, stages=3)
    high_pass(out, 60.0, sample_rate=sample_rate, stages=1)
    largest = peak(out)
    if largest > 0.0:
        scale(out, 1.0 / largest)
    return out


# --- the mix ----------------------------------------------------------------


@dataclass
class RaceMix:
    """The finished stereo pair and what went into it."""

    left: array
    right: array
    sample_rate: int
    placed: dict[str, int]
    peak_before: float
    peak_after: float
    limited: bool
    gain_reduction_db: float = 0.0

    @property
    def seconds(self) -> float:
        return len(self.left) / float(self.sample_rate)


def _place(
    left: array,
    right: array,
    cue: array,
    at_seconds: float,
    level_db: float,
    pan: float,
    sample_rate: int,
) -> None:
    from audio.soundtrack import pan_gains

    gain = db_to_gain(level_db)
    left_gain, right_gain = pan_gains(pan)
    offset = int(round(at_seconds * sample_rate))
    add_into(left, cue, offset, gain * left_gain)
    add_into(right, cue, offset, gain * right_gain)


def _to_rms(buffer: array, target_db: float) -> array:
    """Scale a bed so its RMS is `target_db`. Beds are levelled by average."""
    current = rms(buffer)
    if current > 0.0:
        scale(buffer, db_to_gain(target_db) / current)
    return buffer


def tension_cue(
    seconds: float, seed: int, *, sample_rate: int = SAMPLE_RATE
) -> array:
    """The quiet the machine holds before it lets go.

    A low pair of detuned tones that creep up in level and stop dead at the
    release. The brief asks for "quiet mechanical tension" at the start and this
    is the whole of it: nothing rises in pitch, because a riser is a trailer
    cliche and this is a machine standing still.
    """
    length = seconds_to_samples(seconds, sample_rate)
    out = silence(length)
    for freq, gain in ((58.0, 1.0), (58.0 * 1.007, 0.8), (116.0, 0.35)):
        add_into(
            out,
            tone(length, freq=freq, attack=0.25, decay=90.0, sample_rate=sample_rate),
            0,
            gain,
        )
    hiss = Noise(seed ^ 0x7E7).fill(length)
    low_pass(hiss, 900.0, sample_rate=sample_rate, stages=2)
    high_pass(hiss, 180.0, sample_rate=sample_rate, stages=1)
    add_into(out, hiss, 0, 0.16)
    # Swell into the release rather than sit flat.
    for index in range(length):
        position = index / max(1, length - 1)
        out[index] *= 0.35 + 0.65 * position * position
    largest = peak(out)
    if largest > 0.0:
        scale(out, 1.0 / largest)
    return out


def mechanism_bed(
    motion: Sequence[tuple[float, float, float]],
    length: int,
    seed: int,
    *,
    sample_rate: int = SAMPLE_RATE,
) -> array:
    """The mixer, heard. Level and pitch follow the **recorded** rotor rate.

    `motion` is `presentation.actuator_motion`'s series - output second, radians
    a second, units risen - so nothing here decides when the machine slows down.
    The rotor holds 13.0 rad/s from replay 1.600 to 4.600 and is at 0.036 by
    5.000, and a bed keyed to that is a spin-down a viewer hears without anyone
    placing one.

    Two voices, both of them things a drum mixer actually makes:

    * the motor, a pair of detuned tones whose frequency rises with the rate, so
      slowing is a pitch fall as well as a level fall. Half-speed is a fifth
      down, which is what a motor under load does;
    * the blades in the air, low-passed noise gated by the same envelope, with
      the cutoff opening as the rate rises.

    Over it both are amplitude-modulated at the **blade-pass frequency** - four
    paddles at 13.0 rad/s is 8.28 Hz - which is the chop you hear standing next
    to one and is why this reads as a mixer rather than as a synthesiser pad.
    """
    out = silence(length)
    if not motion:
        return out
    peak_rate = max(row[1] for row in motion)
    if peak_rate <= 1e-6:
        return out

    # The envelope, one value a sample, read off the series by interpolation.
    # Rate over its own peak, so the bed is normalised to this machine.
    rows = sorted(motion)
    times = [row[0] for row in rows]
    gain = silence(length)
    cursor = 0
    for index in range(length):
        when = index / sample_rate
        while cursor + 1 < len(times) and times[cursor + 1] <= when:
            cursor += 1
        low = rows[cursor]
        high = rows[min(cursor + 1, len(rows) - 1)]
        span = max(1e-6, high[0] - low[0])
        blend = min(1.0, max(0.0, (when - low[0]) / span))
        gain[index] = (low[1] + (high[1] - low[1]) * blend) / peak_rate

    noise = Noise(seed).fill(length)
    low_pass(noise, 1400.0, sample_rate=sample_rate, stages=2)
    high_pass(noise, 120.0, sample_rate=sample_rate, stages=1)

    # The motor and the chop, integrated rather than evaluated, so a changing
    # rate does not step the phase. `MOTOR_HZ` at full rate; the blade pass is
    # the rate itself times the paddle count over 2*pi.
    motor_phase = 0.0
    chop_phase = 0.0
    for index in range(length):
        level = gain[index]
        if level <= 1e-4:
            out[index] = 0.0
            continue
        motor = MOTOR_HZ * (0.45 + 0.55 * level)
        motor_phase += 2.0 * math.pi * motor / sample_rate
        chop_phase += 2.0 * math.pi * (BLADES * peak_rate * level / (2.0 * math.pi)) / sample_rate
        body = (math.sin(motor_phase)
                + 0.62 * math.sin(motor_phase * 1.502 + 0.7)
                + 0.28 * math.sin(motor_phase * 2.0))
        chop = 0.62 + 0.38 * math.sin(chop_phase)
        out[index] = (body * 0.55 + noise[index] * 0.9) * chop * level * level
    largest = peak(out)
    if largest > 0.0:
        scale(out, 1.0 / largest)
    return out


def lift_cue(
    seconds: float,
    seed: int,
    *,
    sample_rate: int = SAMPLE_RATE,
) -> array:
    """The paddle assembly withdrawing from the drum, over its recorded travel.

    A screw actuator lifting a heavy thing: a low tone that climbs a minor third
    as it takes the load, band-limited noise for the thread, and a settle at the
    top. `seconds` is the replay's own 5.200-5.900, so this is as long as the
    move is and stops when the blades stop.
    """
    length = seconds_to_samples(max(seconds, 0.05), sample_rate)
    out = silence(length)
    phase = 0.0
    for index in range(length):
        position = index / max(1, length - 1)
        freq = 96.0 * (1.0 + 0.19 * position)
        phase += 2.0 * math.pi * freq / sample_rate
        out[index] = math.sin(phase) + 0.4 * math.sin(phase * 2.0)
    grind = Noise(seed).fill(length)
    band_pass = grind
    high_pass(band_pass, 900.0, sample_rate=sample_rate, stages=1)
    low_pass(band_pass, 3400.0, sample_rate=sample_rate, stages=2)
    add_into(out, band_pass, 0, 0.5)
    # In quickly, out over the last fifth: the move ends by arriving, not by
    # fading. The tail is the mechanism settling onto its stops.
    for index in range(length):
        position = index / max(1, length - 1)
        shape = min(1.0, position / 0.08) * (1.0 if position < 0.80 else
                                             max(0.0, (1.0 - position) / 0.20))
        out[index] *= shape
    largest = peak(out)
    if largest > 0.0:
        scale(out, 1.0 / largest)
    return out


def build_race_audio(
    replay: dict[str, Any],
    track: dict[str, Any],
    clock,
    *,
    music: bool = True,
    cues: Cues = CUES["default"],
    sample_rate: int = SAMPLE_RATE,
) -> RaceMix:
    """The whole soundtrack, placed on the finished film's clock.

    Everything is derived: the two releases from the actuator transforms, the
    impacts from the velocity residual, the bed from recorded speed, and the
    whooshes from the edit map's own omissions. Nothing is placed by hand except
    the levels.
    """
    from sloped import presentation as pres
    from audio.soundtrack import compress, master

    length = seconds_to_samples(clock.duration, sample_rate)
    left = silence(length)
    right = silence(length)
    placed: dict[str, int] = {}
    seed_base = int(replay.get("seed", 0))

    def bump(name: str, count: int = 1) -> None:
        placed[name] = placed.get(name, 0) + count

    # --- beds ---------------------------------------------------------------

    ambience = ambience_bed(length, stable_seed("ambience", seed_base))
    _to_rms(ambience, LEVEL_AMBIENCE)
    add_into(left, ambience, 0, 1.0)
    add_into(right, ambience, 0, 0.94)      # a hair of width, not a wide image
    bump("ambience")

    speeds = pres.rolling(replay, clock)
    rattle = dict(pres.contact_energy(replay, clock))
    bed = rolling_bed(speeds, length, stable_seed("rolling", seed_base))
    _to_rms(bed, LEVEL_ROLL)
    # The rattle rides on top of the bed: the same noise, brighter, keyed to how
    # much small contact the frame actually had.
    grain = Noise(stable_seed("rattle", seed_base)).fill(length)
    high_pass(grain, 1700.0, sample_rate=sample_rate, stages=2)
    low_pass(grain, 8200.0, sample_rate=sample_rate, stages=1)
    control = sorted(rattle.items())
    if control:
        cursor = 0
        times = [row[0] for row in control]
        for index in range(length):
            when = index / sample_rate
            while cursor + 1 < len(times) and times[cursor + 1] <= when:
                cursor += 1
            low = control[cursor]
            high = control[min(cursor + 1, len(control) - 1)]
            span = max(1e-6, high[0] - low[0])
            blend = min(1.0, max(0.0, (when - low[0]) / span))
            grain[index] *= (low[1] + (high[1] - low[1]) * blend) ** 1.2
    _to_rms(grain, LEVEL_ROLL - 6.0)
    for index in range(length):
        value = bed[index] + grain[index]
        left[index] += value
        right[index] += value * 0.97
    bump("rolling")

    # --- the two releases, from the actuators that made them ----------------

    gate = pres.actuator_move(replay, clock, "start.paddle")
    if gate is not None:
        _place(left, right, release_cue(stable_seed("gate", seed_base), weight=0.45),
               gate, LEVEL_GATE, -0.10, sample_rate)
        bump("gate")
        # The tension runs up to the gate and stops there.
        tension = tension_cue(max(0.2, gate), stable_seed("tension", seed_base))
        _to_rms(tension, LEVEL_ROLL - 3.0)
        add_into(left, tension, 0, 1.0)
        add_into(right, tension, 0, 1.0)
        bump("tension")

    trapdoor = pres.actuator_move(replay, clock, "start.panel")
    if trapdoor is not None:
        _place(left, right, release_cue(stable_seed("trapdoor", seed_base), weight=1.0),
               trapdoor, LEVEL_TRAPDOOR, 0.0, sample_rate)
        bump("trapdoor")

    # --- the mixer, for editions that keep it on screen ---------------------
    #
    # **There are effectively no contact events during the settled period, and
    # this does not invent any.** The field stops being hit at replay 2.012 and
    # the floor does not open until 6.100 - `join_report`'s
    # `last_collision_to_gate` is 4.09 s - so what fills those four seconds is
    # the machine, or nothing. Both voices below are the recorded rotor
    # transforms read back: the drone is its rate, the lift is its height.
    if cues.mechanism:
        motion = pres.actuator_motion(replay, clock, "start.rotor")
        if motion:
            # Only as long as the machinery is doing something, plus a second of
            # room. Synthesising a silent bed over the whole film is a minute of
            # arithmetic to add zero.
            active = [row[0] for row in motion if row[1] > 0.2 or row[2] > 1e-3]
            span = min(length, seconds_to_samples(
                (max(active) if active else 0.0) + 1.0, sample_rate))
            bed = mechanism_bed(
                motion, span, stable_seed("mechanism", seed_base),
                sample_rate=sample_rate,
            )
            _to_rms(bed, LEVEL_MECHANISM)
            add_into(left, bed, 0, 1.0)
            add_into(right, bed, 0, 0.96)
            bump("mechanism")

            rising = [row for row in motion if row[2] > 1e-3]
            if rising:
                settled = [row[0] for row in rising
                           if row[2] >= rising[-1][2] - 1e-3]
                start_at = rising[0][0]
                _place(
                    left, right,
                    lift_cue(max(0.15, min(settled) - start_at),
                             stable_seed("lift", seed_base)),
                    start_at, LEVEL_LIFT, 0.0, sample_rate,
                )
                bump("lift")

    # --- the edit's own omissions -------------------------------------------
    #
    # A whoosh marks *omitted time*, not a change of lens. This film omits time
    # twice - 3.40 s of mixing and 0.85 s before the fork - and the first is the
    # one the brief asks to make legible, because the lens is the same on both
    # sides of it and without a cue it reads as a glitch. Ordinary camera cuts
    # get nothing: there is nothing to explain.
    for at, omitted in pres.omissions(clock) if cues.omission else ():
        weight = min(1.0, omitted / 3.4)
        _place(
            left,
            right,
            whoosh_cue(stable_seed("whoosh", seed_base, round(at, 3)),
                       seconds=0.22 + 0.14 * weight),
            at - 0.10,
            LEVEL_WHOOSH - 7.0 * (1.0 - weight),
            0.0,
            sample_rate,
        )
        bump("whoosh")

    # --- contacts -----------------------------------------------------------

    hits = pres.impacts(replay, clock)
    pans = pres.screen_pan(replay, track, hits, max_pan=MAX_PAN)
    for event, pan in zip(hits, pans):
        force = min(1.0, max(0.0, (event.magnitude - IMPACT_SOFT) / (IMPACT_HARD - IMPACT_SOFT)))
        level = LEVEL_IMPACT_QUIET + (LEVEL_IMPACT_LOUD - LEVEL_IMPACT_QUIET) * force
        cue = impact_cue(
            event.magnitude,
            BODY_HZ.get(event.module, BODY_DEFAULT),
            stable_seed("impact", seed_base, event.marble, round(event.replay, 4)),
        )
        _place(left, right, cue, event.at, level, pan, sample_rate)
    bump("impact", len(hits))

    # --- the fork -----------------------------------------------------------

    first_commit: dict[str, tuple[float, int]] = {}
    for event in replay.get("events", ()):
        if event["kind"] != "route":
            continue
        route = str(event["route"])
        when = float(event["t"])
        if route not in first_commit or when < first_commit[route][0]:
            first_commit[route] = (when, int(event["id"]))
    for route, (when, marble) in sorted(first_commit.items()):
        output = clock.at(when)
        if output is None:
            continue
        sample = pres.screen_track(replay, track, clock, marble, (output - 0.02, output + 0.02))
        pan = 0.0
        if sample:
            pan = max(-1.0, min(1.0, (sample[0][1] / 1080.0) * 2.0 - 1.0)) * MAX_PAN
        _place(
            left,
            right,
            split_cue(stable_seed("split", seed_base)),
            output,
            LEVEL_SPLIT,
            pan,
            sample_rate,
        )
        bump("split")

    # --- the line -----------------------------------------------------------

    crossings = sorted(
        (float(event["t"]), int(event["id"]), int(event["order"]))
        for event in replay.get("events", ())
        if event["kind"] == "finish_line"
    )
    photo = _photo_finishes(crossings)
    for when, marble, order in crossings:
        output = clock.at(when)
        if output is None:
            continue
        winner = order == 1
        level = LEVEL_CROSS_WINNER if winner else (
            LEVEL_CROSS_PHOTO if order in photo else LEVEL_CROSS_OTHER
        )
        _place(
            left,
            right,
            crossing_cue(stable_seed("cross", seed_base, marble), winner=winner),
            output,
            level,
            0.0,
            sample_rate,
        )
        bump("crossing")

    # --- music --------------------------------------------------------------

    if music:
        bed_music = music_bed(
            length,
            stable_seed("music", seed_base),
            build_from=max(0.0, clock.duration - 4.0),
        )
        _to_rms(bed_music, LEVEL_MUSIC)
        add_into(left, bed_music, 0, 1.0)
        add_into(right, bed_music, 0, 1.0)
        bump("music")

    # Bus compression, then one trim to the ceiling.
    #
    # The budget above deliberately leaves the mix quiet - it arrives at about
    # -5 dBFS peak and -21 dBFS RMS, which is a crest factor of twenty. Left
    # alone it would be a correctly balanced Short that plays far quieter than
    # everything around it. `compress` is the package's own answer to that and
    # the right one: a soft knee at 2.2:1 with look-ahead pulls a few decibels
    # off the transients that set the peak, and the trim afterwards spends
    # exactly that on everything else. What it must NOT do is what the limiter
    # was doing - see the note on `HEADROOM` - so the result is measured, not
    # assumed: `tests/test_sloped_short.py` pins the winner's crossing as the
    # loudest moment in the film with the second and the dead heat below it.
    squash = compress(left, right)
    report = master(left, right, trim=True)
    return RaceMix(
        left=left,
        right=right,
        sample_rate=sample_rate,
        placed=placed,
        peak_before=report.peak_before,
        peak_after=report.peak_after,
        limited=report.limited,
        gain_reduction_db=squash.max_reduction_db,
    )


def _photo_finishes(
    crossings: Sequence[tuple[float, int, int]], gap: float = 0.20
) -> set[int]:
    """Which finishing positions were close enough to need their own accent.

    On the selected seed fourth and fifth are 0.017 s apart, which is one output
    frame. Two cues that close read as one unless both are lifted, so they are.
    """
    close: set[int] = set()
    for index in range(1, len(crossings)):
        if crossings[index][0] - crossings[index - 1][0] <= gap:
            close.add(crossings[index][2])
            close.add(crossings[index - 1][2])
    close.discard(1)
    return close

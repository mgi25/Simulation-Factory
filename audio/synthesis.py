"""The primitives every sound in this project is built from.

Nothing here knows what a battle is. It is oscillators, envelopes, filters
and a seeded noise source - the smallest set of parts that can express the
cues in `audio.cues`, and deliberately no more than that. There is no graph,
no plugin interface and no realtime anything: a cue is a list of floats, and
a soundtrack is those lists added into a longer one.

Two properties matter more than features:

* Originality. Every sample comes out of the arithmetic below. Nothing is
  sampled, downloaded or licensed, so a rendered video carries no third
  party's rights with it.
* Determinism. No global RNG, no clocks. Noise comes from `Noise`, whose
  seed is derived from stable facts about the event that asked for it, so
  the same replay produces the same bytes every time.
"""

from __future__ import annotations

import math
from array import array

# Production audio format. 48 kHz is chosen for the arithmetic it makes
# exact: at 60 output frames per second it is 800 samples per frame, and at
# the 120 Hz physics rate it is 400 samples per tick, both with no
# remainder. Every timing decision in this package is integer arithmetic.
SAMPLE_RATE = 48000
CHANNELS = 2

_TWO_PI = 2.0 * math.pi
_MASK64 = (1 << 64) - 1

# FNV-1a 64, used to turn event facts into a PRNG seed. Python's own hash()
# is salted per process and would make noise differ between runs.
_FNV_OFFSET = 0xCBF29CE484222325
_FNV_PRIME = 0x100000001B3

# SplitMix64 constants.
_GAMMA = 0x9E3779B97F4A7C15
_MIX_A = 0xBF58476D1CE4E5B9
_MIX_B = 0x94D049BB133111EB

# Every enveloped sound ends with a short linear ramp to exactly zero. An
# exponential decay never actually reaches silence, and a buffer that stops
# at 0.002 instead of 0.0 is a click.
DEFAULT_RELEASE = 0.004


def seconds_to_samples(seconds: float, sample_rate: int = SAMPLE_RATE) -> int:
    """A duration in samples, rounded once, here."""
    return int(round(seconds * sample_rate))


def silence(length: int) -> array:
    """`length` samples of nothing, allocated in one go."""
    if length < 0:
        raise ValueError(f"buffer length cannot be negative: {length}")
    return array("d", bytes(8 * length))


def db_to_gain(db: float) -> float:
    return 10.0 ** (db / 20.0)


def gain_to_db(gain: float) -> float:
    """Decibels for a linear gain. Silence reads as -inf rather than raising."""
    return -math.inf if gain <= 0.0 else 20.0 * math.log10(gain)


# --- determinism ------------------------------------------------------------


def stable_seed(*parts: object) -> int:
    """A 64-bit seed from any mix of numbers and strings, stable across runs.

    Parts are separated rather than concatenated, so ("a", "bc") and
    ("ab", "c") do not collide - which matters when the parts are a subtype
    name and a pair of fighter ids.
    """
    digest = _FNV_OFFSET
    for part in parts:
        for byte in str(part).encode("utf-8"):
            digest = ((digest ^ byte) * _FNV_PRIME) & _MASK64
        digest = ((digest ^ 0x1F) * _FNV_PRIME) & _MASK64
    return digest


class Noise:
    """SplitMix64 as a white-noise source.

    Small, fast, and - unlike random.random() - carries its whole state in
    one integer, so a cue's noise is a pure function of the seed it was
    handed and nothing else in the process can perturb it.
    """

    __slots__ = ("_state",)

    def __init__(self, seed: int) -> None:
        self._state = seed & _MASK64

    def next_u64(self) -> int:
        self._state = (self._state + _GAMMA) & _MASK64
        value = self._state
        value = ((value ^ (value >> 30)) * _MIX_A) & _MASK64
        value = ((value ^ (value >> 27)) * _MIX_B) & _MASK64
        return value ^ (value >> 31)

    def sample(self) -> float:
        """One white sample in [-1, 1)."""
        return (self.next_u64() >> 11) * (2.0 / (1 << 53)) - 1.0

    def fill(self, length: int) -> array:
        out = silence(length)
        for index in range(length):
            out[index] = self.sample()
        return out


# --- envelopes and oscillators ---------------------------------------------


def envelope(
    length: int,
    *,
    attack: float,
    decay: float,
    release: float = DEFAULT_RELEASE,
    sample_rate: int = SAMPLE_RATE,
) -> array:
    """Linear attack, exponential decay, linear release to exactly zero.

    `decay` is a time constant, not a duration: the level falls to 1/e of
    its peak after `decay` seconds and keeps falling. `length` decides when
    the sound stops, and the release ramp makes it stop silently.
    """
    out = silence(length)
    if length == 0:
        return out

    attack_n = min(length, max(1, seconds_to_samples(attack, sample_rate)))
    release_n = min(length, max(1, seconds_to_samples(release, sample_rate)))
    release_from = length - release_n
    step = math.exp(-1.0 / max(1e-9, decay * sample_rate))

    level = 1.0
    for index in range(length):
        value = level
        if index < attack_n:
            value *= (index + 1) / attack_n
        if index >= release_from:
            value *= (length - index) / release_n
        out[index] = value
        level *= step
    return out


def tone(
    length: int,
    *,
    freq: float,
    freq_end: float | None = None,
    attack: float = 0.002,
    decay: float = 0.05,
    release: float = DEFAULT_RELEASE,
    phase: float = 0.0,
    sample_rate: int = SAMPLE_RATE,
) -> array:
    """One enveloped sine, optionally sweeping from `freq` to `freq_end`.

    Sweeps are geometric - the frequency is multiplied by a constant each
    sample - which is both how pitch is heard and one multiplication per
    sample rather than a pow().
    """
    out = envelope(
        length, attack=attack, decay=decay, release=release, sample_rate=sample_rate
    )
    if length == 0:
        return out

    ratio = 1.0
    if freq_end is not None and length > 1 and freq > 0.0 and freq_end > 0.0:
        ratio = (freq_end / freq) ** (1.0 / (length - 1))

    angle = phase
    step = _TWO_PI * freq / sample_rate
    sin = math.sin
    for index in range(length):
        out[index] *= sin(angle)
        angle += step
        step *= ratio
    return out


def noise_burst(
    length: int,
    *,
    seed: int,
    attack: float = 0.0005,
    decay: float = 0.01,
    release: float = DEFAULT_RELEASE,
    highpass: float | None = None,
    lowpass: float | None = None,
    stages: int = 2,
    sample_rate: int = SAMPLE_RATE,
) -> array:
    """Enveloped white noise, optionally band-limited.

    Filtering happens before the envelope: a one-pole filter has memory, and
    running it over an already-decayed signal smears the transient that makes
    a burst read as an impact rather than as a hiss.
    """
    out = Noise(seed).fill(length)
    if highpass is not None:
        high_pass(out, highpass, sample_rate=sample_rate, stages=stages)
    if lowpass is not None:
        low_pass(out, lowpass, sample_rate=sample_rate, stages=stages)

    shape = envelope(
        length, attack=attack, decay=decay, release=release, sample_rate=sample_rate
    )
    for index in range(length):
        out[index] *= shape[index]
    return out


# --- filters ----------------------------------------------------------------


def low_pass(
    buffer: array,
    cutoff: float,
    *,
    sample_rate: int = SAMPLE_RATE,
    stages: int = 1,
) -> array:
    """One-pole low-pass, in place, `stages` times for a steeper slope."""
    alpha = 1.0 - math.exp(-_TWO_PI * max(1e-6, cutoff) / sample_rate)
    alpha = min(1.0, max(0.0, alpha))
    for _ in range(max(1, stages)):
        state = 0.0
        for index in range(len(buffer)):
            state += alpha * (buffer[index] - state)
            buffer[index] = state
    return buffer


def high_pass(
    buffer: array,
    cutoff: float,
    *,
    sample_rate: int = SAMPLE_RATE,
    stages: int = 1,
) -> array:
    """One-pole high-pass, in place, `stages` times for a steeper slope."""
    rc = 1.0 / (_TWO_PI * max(1e-6, cutoff))
    alpha = rc / (rc + 1.0 / sample_rate)
    for _ in range(max(1, stages)):
        previous_in = 0.0
        state = 0.0
        for index in range(len(buffer)):
            sample = buffer[index]
            state = alpha * (state + sample - previous_in)
            previous_in = sample
            buffer[index] = state
    return buffer


# --- combining --------------------------------------------------------------


def add_into(
    destination: array, source: array, offset: int = 0, gain: float = 1.0
) -> int:
    """Add `source` into `destination` at `offset`, clipped to what fits.

    Returns how many samples were actually written. A cue whose tail runs
    past the end of the soundtrack is truncated rather than refused: the
    soundtrack has an exact intended length and nothing may extend it.
    """
    if gain == 0.0:
        return 0
    start = max(0, offset)
    end = min(len(destination), offset + len(source))
    if end <= start:
        return 0
    read = start - offset
    for index in range(start, end):
        destination[index] += source[read] * gain
        read += 1
    return end - start


def layer(length: int, parts: list[tuple[int, array, float]]) -> array:
    """A cue assembled from (offset, buffer, gain) layers."""
    out = silence(length)
    for offset, buffer, gain in parts:
        add_into(out, buffer, offset, gain)
    return out


def scale(buffer: array, gain: float) -> array:
    if gain != 1.0:
        for index in range(len(buffer)):
            buffer[index] *= gain
    return buffer


def peak(buffer: array) -> float:
    """Largest absolute sample, or 0.0 for an empty buffer."""
    largest = 0.0
    for value in buffer:
        magnitude = -value if value < 0.0 else value
        if magnitude > largest:
            largest = magnitude
    return largest


def rms(buffer: array) -> float:
    if not buffer:
        return 0.0
    total = 0.0
    for value in buffer:
        total += value * value
    return math.sqrt(total / len(buffer))


def normalise_peak(buffer: array, target: float = 1.0) -> float:
    """Scale a buffer so its loudest sample is `target`. Returns the gain used.

    Applied to a cue *before* it is placed, never to the finished mix: a cue
    has a designed level, and normalising it here is how that level means the
    same thing whichever layers happened to add up inside it.
    """
    current = peak(buffer)
    if current <= 0.0:
        return 1.0
    gain = target / current
    scale(buffer, gain)
    return gain

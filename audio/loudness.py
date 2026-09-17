"""Loudness, true peak and fatigue analysis, measured rather than assumed.

Everything in this module is ITU-R BS.1770-4 / EBU R128 arithmetic done here,
in numpy, against the PCM the mix stage produced. It exists because V32.2 is an
audio pass whose whole claim is "the continuous texture is gone", and a claim
like that has to be a number before it can be a decision.

Three groups of measurement:

* **loudness** - K-weighted, gated integrated loudness (`integrated`), the
  short-term series it is built from, and the loudness range (`lra`) that says
  how much contrast the film actually has. A mix with LRA 4 LU is a flat mix
  whatever its spectrum looks like.
* **true peak** - `true_peak`, at 4x oversampling, because the sample peak of a
  44/48 kHz file is not the peak a converter reconstructs and the delivery
  ceiling is written against the latter.
* **texture** - `band_profile`, `band_series` and `continuity`. These are the
  fatigue instruments. `continuity` is the one this pass was built around: it
  reports what fraction of the film a band sits within a few decibels of its own
  median, which is the difference between "a texture that responds" and "a
  texture that is always on".

The implementation is checked against ffmpeg's `ebur128` filter in
`tests/test_race2_v322_audio.py`; the tolerance there is 0.3 LU, which is about
what two conforming meters disagree by.
"""

from __future__ import annotations

import math
import wave
from array import array
from dataclasses import dataclass, field
from typing import Iterable, Sequence

import numpy as np

# --- K-weighting, BS.1770-4 Tables 1 and 2 at 48 kHz -------------------------
#
# Stage 1 is the head-shelf that stands in for the acoustic effect of a head in
# a sound field; stage 2 is the RLB high-pass. Both are biquads and both are
# specified at 48 kHz, which is the only rate this project masters at, so they
# are written down rather than designed at run time.
_SHELF_B = (1.53512485958697, -2.69169618940638, 1.19839281085285)
_SHELF_A = (1.0, -1.69065929318241, 0.73248077421585)
_RLB_B = (1.0, -2.0, 1.0)
_RLB_A = (1.0, -1.99004745483398, 0.99007225036621)

#: The offset in `L = -0.691 + 10 log10 sum(G * z)`.
_LOUDNESS_OFFSET = -0.691
#: BS.1770 channel weights for a stereo pair.
_CHANNEL_GAIN = (1.0, 1.0)

#: Gating, R128 s2.
ABSOLUTE_GATE_LUFS = -70.0
RELATIVE_GATE_LU = -10.0
BLOCK_SECONDS = 0.400
BLOCK_STEP_SECONDS = 0.100

#: LRA, EBU Tech 3342.
LRA_BLOCK_SECONDS = 3.0
LRA_STEP_SECONDS = 1.0
LRA_RELATIVE_GATE_LU = -20.0
LRA_LOW_PERCENTILE = 10.0
LRA_HIGH_PERCENTILE = 95.0

#: True-peak oversampling factor. BS.1770-4 asks for at least 4x at 48 kHz.
TRUE_PEAK_OVERSAMPLE = 4

#: The bands the fatigue report is written in. The two the brief names - 2-5 kHz
#: and 5-10 kHz - are bands of their own so they can be quoted directly.
BANDS: tuple[tuple[float, float], ...] = (
    (20.0, 120.0),
    (120.0, 300.0),
    (300.0, 800.0),
    (800.0, 2000.0),
    (2000.0, 5000.0),
    (5000.0, 10000.0),
    (10000.0, 20000.0),
)


def band_label(low: float, high: float) -> str:
    return f"{int(low)}-{int(high)}"


# --- reading -----------------------------------------------------------------


def read_pcm(path: str) -> tuple[np.ndarray, int]:
    """A WAV file as `(samples[n, channels] in [-1, 1), sample rate)`.

    Handles the 24-bit files `audio.wav_io` writes and the 16-bit ones ffmpeg
    hands back, which is every format this project puts on disk.
    """
    with wave.open(path, "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        raw = handle.readframes(handle.getnframes())
    if width == 3:
        packed = np.frombuffer(raw, dtype=np.uint8).reshape(-1, channels, 3)
        value = (packed[:, :, 0].astype(np.int32)
                 | (packed[:, :, 1].astype(np.int32) << 8)
                 | (packed[:, :, 2].astype(np.int32) << 16))
        value = np.where(value & 0x800000, value - 0x1000000, value)
        data = value.astype(np.float64) / float(1 << 23)
    elif width == 2:
        data = (np.frombuffer(raw, dtype="<i2").reshape(-1, channels)
                .astype(np.float64) / float(1 << 15))
    elif width == 4:
        data = (np.frombuffer(raw, dtype="<i4").reshape(-1, channels)
                .astype(np.float64) / float(1 << 31))
    else:
        raise ValueError(f"unsupported sample width {width} in {path}")
    return np.ascontiguousarray(data), rate


def as_stereo(left: array | Sequence[float], right: array | Sequence[float]) -> np.ndarray:
    """Two mono buffers as one `[n, 2]` block, without going through a file."""
    a = np.asarray(left, dtype=np.float64)
    b = np.asarray(right, dtype=np.float64)
    if len(a) != len(b):
        raise ValueError(f"channel lengths differ: {len(a)} vs {len(b)}")
    return np.stack((a, b), axis=1)


# --- loudness ----------------------------------------------------------------


def _biquad(signal: np.ndarray, b: Sequence[float], a: Sequence[float]) -> np.ndarray:
    """One direct-form-I biquad down a column.

    Written as an explicit recursion rather than `lfilter` so the module needs
    numpy and nothing else - scipy is not in `requirements.txt` and this pass is
    not the place to add a dependency for six lines of arithmetic.
    """
    out = np.empty_like(signal)
    x1 = x2 = y1 = y2 = 0.0
    b0, b1, b2 = b
    _, a1, a2 = a
    for index in range(signal.shape[0]):
        x0 = signal[index]
        y0 = b0 * x0 + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        out[index] = y0
        x2, x1 = x1, x0
        y2, y1 = y1, y0
    return out


def k_weight(samples: np.ndarray, sample_rate: int = 48000) -> np.ndarray:
    """BS.1770 K-weighting, channel by channel."""
    if sample_rate != 48000:
        raise ValueError(
            f"the K-weighting coefficients here are the 48 kHz ones; got {sample_rate}")
    out = np.empty_like(samples)
    for channel in range(samples.shape[1]):
        stage = _biquad(samples[:, channel], _SHELF_B, _SHELF_A)
        out[:, channel] = _biquad(stage, _RLB_B, _RLB_A)
    return out


def _block_loudness(
    weighted: np.ndarray, sample_rate: int, block_seconds: float, step_seconds: float
) -> np.ndarray:
    """Loudness of every overlapping block, in LUFS, ungated."""
    block = int(round(block_seconds * sample_rate))
    step = int(round(step_seconds * sample_rate))
    if weighted.shape[0] < block:
        return np.array([])
    starts = range(0, weighted.shape[0] - block + 1, step)
    power = np.empty(len(starts))
    for index, start in enumerate(starts):
        segment = weighted[start:start + block]
        mean_square = np.mean(segment * segment, axis=0)
        power[index] = float(np.dot(_CHANNEL_GAIN[:len(mean_square)], mean_square))
    with np.errstate(divide="ignore"):
        return _LOUDNESS_OFFSET + 10.0 * np.log10(np.maximum(power, 1e-30))


def _gated_mean(blocks: np.ndarray, relative_gate_lu: float) -> float:
    """The two-stage gate: absolute, then relative to what survived it."""
    keep = blocks[blocks > ABSOLUTE_GATE_LUFS]
    if keep.size == 0:
        return float("-inf")
    first = _LOUDNESS_OFFSET + 10.0 * np.log10(
        np.mean(np.power(10.0, (keep - _LOUDNESS_OFFSET) / 10.0)))
    keep = keep[keep > first + relative_gate_lu]
    if keep.size == 0:
        return float("-inf")
    return float(_LOUDNESS_OFFSET + 10.0 * np.log10(
        np.mean(np.power(10.0, (keep - _LOUDNESS_OFFSET) / 10.0))))


@dataclass(frozen=True)
class Loudness:
    """What a meter says about one finished mix."""

    integrated_lufs: float
    lra_lu: float
    lra_low_lufs: float
    lra_high_lufs: float
    true_peak_dbtp: float
    sample_peak_dbfs: float
    short_term: tuple[float, ...] = field(default=(), repr=False)
    momentary: tuple[float, ...] = field(default=(), repr=False)

    def as_dict(self) -> dict[str, float]:
        return {
            "integrated_lufs": round(self.integrated_lufs, 2),
            "lra_lu": round(self.lra_lu, 2),
            "lra_low_lufs": round(self.lra_low_lufs, 2),
            "lra_high_lufs": round(self.lra_high_lufs, 2),
            "true_peak_dbtp": round(self.true_peak_dbtp, 2),
            "sample_peak_dbfs": round(self.sample_peak_dbfs, 2),
        }


def integrated(samples: np.ndarray, sample_rate: int = 48000) -> float:
    """Gated integrated loudness in LUFS."""
    weighted = k_weight(samples, sample_rate)
    blocks = _block_loudness(weighted, sample_rate, BLOCK_SECONDS, BLOCK_STEP_SECONDS)
    return _gated_mean(blocks, RELATIVE_GATE_LU)


def lra(samples: np.ndarray, sample_rate: int = 48000) -> tuple[float, float, float]:
    """`(LRA, low, high)` in LU/LUFS, EBU Tech 3342."""
    weighted = k_weight(samples, sample_rate)
    blocks = _block_loudness(weighted, sample_rate, LRA_BLOCK_SECONDS, LRA_STEP_SECONDS)
    keep = blocks[blocks > ABSOLUTE_GATE_LUFS]
    if keep.size == 0:
        return 0.0, float("-inf"), float("-inf")
    mean = _LOUDNESS_OFFSET + 10.0 * np.log10(
        np.mean(np.power(10.0, (keep - _LOUDNESS_OFFSET) / 10.0)))
    keep = keep[keep > mean + LRA_RELATIVE_GATE_LU]
    if keep.size == 0:
        return 0.0, float("-inf"), float("-inf")
    low = float(np.percentile(keep, LRA_LOW_PERCENTILE))
    high = float(np.percentile(keep, LRA_HIGH_PERCENTILE))
    return high - low, low, high


def true_peak(samples: np.ndarray, oversample: int = TRUE_PEAK_OVERSAMPLE) -> float:
    """Peak in dBTP, by band-limited interpolation onto a 4x grid.

    The resampling is done with a real FFT over the whole buffer, which is the
    exact band-limited interpolation the standard's filter approximates. A Short
    is twenty seconds, so doing it in one pass costs nothing and avoids the
    block-edge error a short FIR would introduce.
    """
    highest = 0.0
    for channel in range(samples.shape[1]):
        column = samples[:, channel]
        if column.size == 0:
            continue
        spectrum = np.fft.rfft(column)
        padded = np.zeros(column.size * oversample // 2 + 1, dtype=complex)
        padded[:spectrum.size] = spectrum
        lifted = np.fft.irfft(padded, n=column.size * oversample) * oversample
        highest = max(highest, float(np.max(np.abs(lifted))))
    return 20.0 * math.log10(max(highest, 1e-12))


def measure(samples: np.ndarray, sample_rate: int = 48000) -> Loudness:
    """Every delivery number for one mix, in one pass over the K-weighted signal."""
    weighted = k_weight(samples, sample_rate)
    momentary = _block_loudness(weighted, sample_rate, BLOCK_SECONDS, BLOCK_STEP_SECONDS)
    short = _block_loudness(weighted, sample_rate, LRA_BLOCK_SECONDS, LRA_STEP_SECONDS)

    keep = short[short > ABSOLUTE_GATE_LUFS]
    if keep.size:
        mean = _LOUDNESS_OFFSET + 10.0 * np.log10(
            np.mean(np.power(10.0, (keep - _LOUDNESS_OFFSET) / 10.0)))
        gated = keep[keep > mean + LRA_RELATIVE_GATE_LU]
    else:
        gated = keep
    if gated.size:
        low = float(np.percentile(gated, LRA_LOW_PERCENTILE))
        high = float(np.percentile(gated, LRA_HIGH_PERCENTILE))
    else:
        low = high = float("-inf")

    return Loudness(
        integrated_lufs=_gated_mean(momentary, RELATIVE_GATE_LU),
        lra_lu=(high - low) if gated.size else 0.0,
        lra_low_lufs=low,
        lra_high_lufs=high,
        true_peak_dbtp=true_peak(samples),
        sample_peak_dbfs=20.0 * math.log10(max(float(np.max(np.abs(samples))), 1e-12)),
        short_term=tuple(round(float(v), 3) for v in short),
        momentary=tuple(round(float(v), 3) for v in momentary),
    )


def gain_for_target(samples: np.ndarray, target_lufs: float,
                    sample_rate: int = 48000) -> float:
    """The single linear gain that puts `samples` on `target_lufs`.

    One number over the whole timeline. A static gain cannot change LRA, the
    crest factor or the relationship between any two moments, which is the whole
    reason loudness is hit this way here and not with a normaliser.
    """
    current = integrated(samples, sample_rate)
    if not math.isfinite(current):
        return 1.0
    return float(10.0 ** ((target_lufs - current) / 20.0))


# --- texture -----------------------------------------------------------------


def _welch(signal: np.ndarray, sample_rate: int, size: int = 1 << 16) -> tuple[np.ndarray, np.ndarray]:
    size = min(size, 1 << int(math.floor(math.log2(max(signal.size, 2)))))
    window = np.hanning(size)
    total = np.zeros(size // 2 + 1)
    count = 0
    for start in range(0, max(1, signal.size - size + 1), size // 2):
        segment = signal[start:start + size]
        if segment.size < size:
            break
        total += np.abs(np.fft.rfft(segment * window)) ** 2
        count += 1
    if count:
        total /= count
    return np.fft.rfftfreq(size, 1.0 / sample_rate), total


def band_profile(samples: np.ndarray, sample_rate: int = 48000) -> dict[str, float]:
    """Each band's share of total power, as a percentage, over the whole film."""
    mono = samples.mean(axis=1)
    freqs, power = _welch(mono, sample_rate)
    total = float(power.sum()) or 1.0
    return {
        band_label(low, high): round(
            100.0 * float(power[(freqs >= low) & (freqs < high)].sum()) / total, 3)
        for low, high in BANDS
    }


def band_series(
    samples: np.ndarray,
    low: float,
    high: float,
    sample_rate: int = 48000,
    window_seconds: float = 0.25,
) -> np.ndarray:
    """One band's level in dB, window by window, down the whole film.

    The instrument the diagnosis is written with. A band that is a *texture*
    produces a flat series; a band that carries *events* produces a spiky one,
    and the difference is visible in the numbers before anyone listens.
    """
    mono = samples.mean(axis=1)
    size = int(round(window_seconds * sample_rate))
    if size < 16 or mono.size < size:
        return np.array([])
    window = np.hanning(size)
    freqs = np.fft.rfftfreq(size, 1.0 / sample_rate)
    mask = (freqs >= low) & (freqs < high)
    count = mono.size // size
    out = np.empty(count)
    for index in range(count):
        segment = mono[index * size:(index + 1) * size] * window
        spectrum = np.fft.rfft(segment)
        energy = float(np.sum(np.abs(spectrum[mask]) ** 2)) / (size * size)
        out[index] = 10.0 * math.log10(max(energy, 1e-30))
    return out


@dataclass(frozen=True)
class Continuity:
    """How always-on one band is.

    `within_db` is the fraction of windows whose level is within `tolerance` of
    the band's own median. A broadband bed that never stops scores near 1.0; a
    band carrying discrete events scores low, because most windows sit well
    under the median and a few sit well over it.

    `span_db` is p95 minus p5 of the same series - how far the band actually
    travels - and `quiet_fraction` is how much of the film the band spends more
    than `quiet_db` under its own 95th percentile, which is the direct measure
    of whether the mix has any spaces in it.
    """

    band: str
    within_db: float
    span_db: float
    quiet_fraction: float
    median_db: float
    tolerance_db: float
    quiet_db: float

    def as_dict(self) -> dict[str, float | str]:
        return {
            "band": self.band,
            "within_db": round(self.within_db, 4),
            "span_db": round(self.span_db, 2),
            "quiet_fraction": round(self.quiet_fraction, 4),
            "median_db": round(self.median_db, 2),
            "tolerance_db": self.tolerance_db,
            "quiet_db": self.quiet_db,
        }


def continuity(
    samples: np.ndarray,
    low: float,
    high: float,
    sample_rate: int = 48000,
    window_seconds: float = 0.25,
    tolerance_db: float = 6.0,
    quiet_db: float = 12.0,
) -> Continuity:
    """The fatigue instrument, for one band."""
    series = band_series(samples, low, high, sample_rate, window_seconds)
    if series.size == 0:
        return Continuity(band_label(low, high), 0.0, 0.0, 0.0, float("-inf"),
                          tolerance_db, quiet_db)
    median = float(np.median(series))
    top = float(np.percentile(series, 95.0))
    bottom = float(np.percentile(series, 5.0))
    return Continuity(
        band=band_label(low, high),
        within_db=float(np.mean(np.abs(series - median) <= tolerance_db)),
        span_db=top - bottom,
        quiet_fraction=float(np.mean(series < top - quiet_db)),
        median_db=median,
        tolerance_db=tolerance_db,
        quiet_db=quiet_db,
    )


def fatigue_report(samples: np.ndarray, sample_rate: int = 48000) -> dict[str, object]:
    """Every band's continuity, plus the two the brief singles out."""
    rows = [continuity(samples, low, high, sample_rate).as_dict() for low, high in BANDS]
    return {
        "band_profile": band_profile(samples, sample_rate),
        "continuity": rows,
        "fatigue_bands": {
            "2000-5000": next(r for r in rows if r["band"] == "2000-5000"),
            "5000-10000": next(r for r in rows if r["band"] == "5000-10000"),
        },
    }


# --- mono --------------------------------------------------------------------


def mono_fold(samples: np.ndarray) -> np.ndarray:
    """The sum a phone speaker makes, as one column."""
    return samples.mean(axis=1, keepdims=True)


def mono_compatibility(samples: np.ndarray, sample_rate: int = 48000) -> dict[str, float]:
    """What folding to mono costs, in decibels, band by band and overall.

    A mix that loses more than a decibel or two anywhere has something out of
    phase in it. Anything here that is panned is panned by amplitude only, so
    the expected answer is a small, even loss and no band-specific hole.
    """
    folded = mono_fold(samples)
    stereo_rms = float(np.sqrt(np.mean(samples ** 2)))
    mono_rms = float(np.sqrt(np.mean(folded ** 2)))
    out = {
        "stereo_rms_dbfs": round(20.0 * math.log10(max(stereo_rms, 1e-12)), 2),
        "mono_rms_dbfs": round(20.0 * math.log10(max(mono_rms, 1e-12)), 2),
        "mono_loss_db": round(20.0 * math.log10(max(mono_rms, 1e-12) / max(stereo_rms, 1e-12)), 2),
        "correlation": round(float(np.corrcoef(samples[:, 0], samples[:, 1])[0, 1]), 4),
        "mono_integrated_lufs": round(
            integrated(np.repeat(folded, 2, axis=1), sample_rate), 2),
    }
    stereo_bands = band_profile(samples, sample_rate)
    mono_bands = band_profile(np.repeat(folded, 2, axis=1), sample_rate)
    out["band_shift"] = {
        key: round(mono_bands[key] - stereo_bands[key], 3) for key in stereo_bands
    }
    return out


# --- small-speaker simulation ------------------------------------------------


def phone_filter(samples: np.ndarray, sample_rate: int = 48000,
                 low_corner: float = 500.0) -> np.ndarray:
    """A phone speaker, roughly: mono, and nothing useful under ~500 Hz.

    Crude on purpose - a second-order high-pass and a fold-down. It is not a
    model of a speaker, it is a way of listening to what survives one, and the
    only question asked of it is whether the marbles and the rhythm are still
    there when the bass is not.
    """
    folded = mono_fold(samples)
    alpha = math.exp(-2.0 * math.pi * low_corner / sample_rate)
    out = folded.copy()
    for _ in range(2):
        column = out[:, 0]
        filtered = np.empty_like(column)
        previous_in = 0.0
        previous_out = 0.0
        for index in range(column.size):
            value = column[index]
            previous_out = alpha * (previous_out + value - previous_in)
            previous_in = value
            filtered[index] = previous_out
        out[:, 0] = filtered
    return out


def energy_above(samples: np.ndarray, hz: float, sample_rate: int = 48000) -> float:
    """Share of total power above `hz`, as a percentage. The fatigue headline."""
    mono = samples.mean(axis=1)
    freqs, power = _welch(mono, sample_rate)
    total = float(power.sum()) or 1.0
    return round(100.0 * float(power[freqs >= hz].sum()) / total, 3)


def duty_cycle(samples: np.ndarray, low: float, high: float,
               sample_rate: int = 48000, window_seconds: float = 0.02,
               threshold_db: float = -15.0) -> float:
    """Fraction of short windows in which a band is within `threshold_db` of its own p95.

    The difference between a hiss and a stream of ticks, stated as one number: a
    continuous noise bed is above its own p95 minus 15 dB essentially always; the
    same energy delivered as discrete transients is not.
    """
    series = band_series(samples, low, high, sample_rate, window_seconds)
    if series.size == 0:
        return 0.0
    top = float(np.percentile(series, 95.0))
    return float(np.mean(series > top + threshold_db))

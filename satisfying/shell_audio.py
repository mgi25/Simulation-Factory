"""Sample synthesis and objective measurement for the shell musical score.

All sounds are generated here from oscillators and deterministic arithmetic.
There are no samples and no background-music layer.  The score module owns
meaning and timing; this module only turns that immutable schedule into PCM.
"""

from __future__ import annotations

import hashlib
import math
from array import array
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from audio import loudness
from audio.wav_io import DEFAULT_BIT_DEPTH, pcm_bytes, write_wav
from satisfying.shell_score import AudioConfig, AudioEvent, AudioSchedule


RENDER_VERSION = "category3-test2-shell-audio-render/1.0.0"


def _db(gain: float) -> float:
    return 20.0 * math.log10(max(gain, 1e-12))


def pan_gains(pan: float) -> tuple[float, float]:
    """Constant-power placement with no inter-channel phase differences."""
    angle = (max(-1.0, min(1.0, pan)) + 1.0) * math.pi / 4.0
    return math.cos(angle), math.sin(angle)


def _envelope(length: int, rate: int, attack: float, decay: float) -> np.ndarray:
    if length <= 0:
        return np.zeros(0, dtype=np.float64)
    times = np.arange(length, dtype=np.float64) / rate
    shape = np.exp(-times / max(decay, 1e-6))
    attack_n = max(1, min(length, int(round(attack * rate))))
    shape[:attack_n] *= np.linspace(0.0, 1.0, attack_n, endpoint=True)
    release_n = max(2, min(length, int(round(0.006 * rate))))
    shape[-release_n:] *= np.linspace(1.0, 0.0, release_n, endpoint=True)
    shape[-1] = 0.0
    return shape


def _normalise(cue: np.ndarray) -> np.ndarray:
    peak = float(np.max(np.abs(cue))) if cue.size else 0.0
    if peak > 0.0:
        cue /= peak
    return cue


def _collision_cue(event: AudioEvent, config: AudioConfig) -> np.ndarray:
    rate = config.sample_rate
    length = int(round(config.collision_seconds * rate))
    t = np.arange(length, dtype=np.float64) / rate
    outer = event.shell_id / 5.0
    damage = event.damage
    decay = config.collision_decay * (1.0 + 0.28 * damage + 0.10 * outer)
    shape = _envelope(length, rate, 0.0012, decay)
    freq = event.frequency_hz

    # One mallet instrument, voiced more brightly as the ball moves outward.
    second = config.resonance * (0.34 + 0.22 * outer)
    third = config.brightness * (0.10 + 0.14 * event.impact + 0.16 * outer)
    cue = (
        np.sin(2.0 * math.pi * freq * t)
        + second * np.sin(2.0 * math.pi * 2.0 * freq * t + 0.31)
        + third * np.sin(2.0 * math.pi * 3.0 * freq * t + 0.67)
    ) * shape

    # Weakening is spectral and cumulative, never a canned crack.  A slightly
    # stretched second partial creates a controlled beating only near failure.
    if damage > 0.0:
        rough = np.sin(2.0 * math.pi * freq * (2.0 + 0.010 * damage) * t + 1.1)
        cue += rough * shape * config.damage_colour * damage * 0.25

    # Impact and post geometry control the clean transient.  It is a pitched
    # high partial, not broadband noise, so dense passages do not turn to hiss.
    transient_decay = 0.008 if event.feature == "post" else 0.013
    transient_shape = _envelope(length, rate, 0.00035, transient_decay)
    transient_gain = config.transient * (0.35 + 0.65 * event.impact)
    if event.feature == "post":
        transient_gain *= 1.28
    cue += transient_gain * np.sin(2.0 * math.pi * 4.0 * freq * t + 0.2) * transient_shape

    # A real canonical near miss gets one short unresolved neighbour.  Sign is
    # direction: the gap still coming rises; the gap just passed falls.
    if event.near_miss and event.near_miss_direction:
        start = int(round(0.021 * rate))
        ornament_n = min(length - start, int(round(0.068 * rate)))
        if ornament_n > 1:
            ot = np.arange(ornament_n, dtype=np.float64) / rate
            ratio = 9.0 / 8.0 if event.near_miss_direction > 0 else 8.0 / 9.0
            ornament = np.sin(2.0 * math.pi * freq * ratio * ot + 0.45)
            ornament *= _envelope(ornament_n, rate, 0.0008, 0.025)
            cue[start:start + ornament_n] += ornament * config.near_miss_colour

    return _normalise(cue)


def _break_cue(event: AudioEvent, config: AudioConfig) -> np.ndarray:
    rate = config.sample_rate
    length = int(round(config.break_seconds * rate))
    t = np.arange(length, dtype=np.float64) / rate
    shape = _envelope(length, rate, 0.0025, 0.150 + 0.025 * event.progress)
    freq = event.frequency_hz
    cue = (
        np.sin(2.0 * math.pi * freq * t)
        + 0.72 * np.sin(2.0 * math.pi * freq * 1.25 * t + 0.22)
        + 0.62 * np.sin(2.0 * math.pi * freq * 1.5 * t + 0.54)
        + 0.24 * np.sin(2.0 * math.pi * freq * 2.0 * t + 0.80)
    ) * shape
    return _normalise(cue)


def _transition_cue(event: AudioEvent, config: AudioConfig) -> np.ndarray:
    rate = config.sample_rate
    length = int(round(config.transition_seconds * rate))
    t = np.arange(length, dtype=np.float64) / rate
    unit = np.linspace(0.0, 1.0, length, endpoint=True)
    ratio = np.power(1.5, unit)
    phase = 2.0 * math.pi * np.cumsum(event.frequency_hz * ratio) / rate
    shape = _envelope(length, rate, 0.003, 0.115)
    cue = np.sin(phase) + 0.38 * np.sin(2.0 * phase + 0.4)
    if event.method == "break":
        cue += 0.17 * np.sin(3.0 * phase + 0.8)
    cue *= shape
    return _normalise(cue)


def _escape_cue(event: AudioEvent, config: AudioConfig) -> np.ndarray:
    rate = config.sample_rate
    length = int(round(config.escape_seconds * rate))
    t = np.arange(length, dtype=np.float64) / rate
    shape = _envelope(length, rate, 0.009, 0.245)
    root = event.frequency_hz
    # D-major resolution: root, major third, fifth and octave.  Its longer,
    # gentler envelope is the release; gain remains below a brute-force hit.
    cue = (
        np.sin(2.0 * math.pi * root * t)
        + 0.68 * np.sin(2.0 * math.pi * root * 1.25 * t + 0.16)
        + 0.78 * np.sin(2.0 * math.pi * root * 1.5 * t + 0.38)
        + 0.34 * np.sin(2.0 * math.pi * root * 2.0 * t + 0.62)
    ) * shape
    return _normalise(cue)


def cue_for(event: AudioEvent, config: AudioConfig) -> np.ndarray:
    if event.kind == "collision":
        return _collision_cue(event, config)
    if event.kind == "break":
        return _break_cue(event, config)
    if event.kind == "transition":
        return _transition_cue(event, config)
    if event.kind == "escape":
        return _escape_cue(event, config)
    raise ValueError(f"unknown shell audio event {event.kind!r}")


@dataclass(frozen=True)
class RenderedAudio:
    schedule: AudioSchedule
    samples: np.ndarray
    static_gain: float

    @property
    def sample_rate(self) -> int:
        return self.schedule.config.sample_rate

    @property
    def left(self) -> array:
        return array("d", self.samples[:, 0])

    @property
    def right(self) -> array:
        return array("d", self.samples[:, 1])

    def pcm(self, bit_depth: int = DEFAULT_BIT_DEPTH) -> bytes:
        return pcm_bytes(self.left, self.right, bit_depth)

    def digest(self, bit_depth: int = DEFAULT_BIT_DEPTH) -> str:
        return hashlib.sha256(self.pcm(bit_depth)).hexdigest()


def render(plan: AudioSchedule) -> RenderedAudio:
    """Render a schedule with one static gain and no dynamics processor."""
    samples = np.zeros((plan.total_samples, 2), dtype=np.float64)
    for event in plan.events:
        cue = cue_for(event, plan.config)
        start = event.sample_offset
        stop = min(plan.total_samples, start + cue.size)
        if stop <= start:
            continue
        left, right = pan_gains(event.pan)
        audible = cue[:stop - start] * event.gain
        samples[start:stop, 0] += audible * left
        samples[start:stop, 1] += audible * right

    raw_peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    ceiling = 10.0 ** (plan.config.peak_ceiling_dbfs / 20.0)
    static_gain = plan.config.master_gain
    if raw_peak * static_gain > ceiling:
        static_gain = ceiling / raw_peak
    samples *= static_gain
    return RenderedAudio(plan, samples, static_gain)


def write_master(rendered: RenderedAudio, path: str,
                 bit_depth: int = DEFAULT_BIT_DEPTH) -> str:
    return write_wav(path, rendered.left, rendered.right,
                     sample_rate=rendered.sample_rate, bit_depth=bit_depth)


def _event_peaks(rendered: RenderedAudio, window_seconds: float = 0.055) -> dict[str, Any]:
    size = int(round(window_seconds * rendered.sample_rate))
    grouped: dict[str, list[float]] = {}
    for event in rendered.schedule.events:
        start = event.sample_offset
        stop = min(rendered.samples.shape[0], start + size)
        peak = float(np.max(np.abs(rendered.samples[start:stop]))) if stop > start else 0.0
        grouped.setdefault(event.kind, []).append(peak)
    return {
        kind: {
            "count": len(values),
            "median_peak_dbfs": round(_db(float(np.median(values))), 2),
            "max_peak_dbfs": round(_db(max(values)), 2),
        }
        for kind, values in sorted(grouped.items())
    }


def sync_report(plan: AudioSchedule) -> dict[str, Any]:
    errors = [abs(event.sample_offset / plan.config.sample_rate - event.source_seconds)
              for event in plan.events]
    return {
        "events": len(plan.events),
        "max_placement_error_seconds": max(errors, default=0.0),
        "max_placement_error_samples": max(errors, default=0.0) * plan.config.sample_rate,
        "within_half_sample": all(error <= 0.5 / plan.config.sample_rate + 1e-12
                                  for error in errors),
    }


def measure(rendered: RenderedAudio) -> dict[str, Any]:
    samples = rendered.samples
    rate = rendered.sample_rate
    meter = loudness.measure(samples, rate)
    mono = loudness.mono_compatibility(samples, rate)
    phone = loudness.phone_filter(samples, rate)
    phone_stereo = np.repeat(phone, 2, axis=1)
    phone_rms = float(np.sqrt(np.mean(phone * phone)))
    stereo_rms = float(np.sqrt(np.mean(samples * samples)))
    clipped = int(np.count_nonzero(np.abs(samples) >= 1.0))
    final_silence = int(round(rendered.schedule.config.end_silence_seconds * rate))
    silence_peak = float(np.max(np.abs(samples[-final_silence:]))) if final_silence else 0.0
    return {
        "render_version": RENDER_VERSION,
        "seed": rendered.schedule.seed,
        "playback_digest": rendered.schedule.playback_digest,
        "score_fingerprint": rendered.schedule.fingerprint(),
        "config_fingerprint": rendered.schedule.config.fingerprint(),
        "pcm_digest": rendered.digest(),
        "duration_seconds": round(samples.shape[0] / rate, 6),
        "sample_rate": rate,
        "channels": 2,
        "peak": {
            "sample_peak_dbfs": meter.as_dict()["sample_peak_dbfs"],
            "true_peak_dbtp": meter.as_dict()["true_peak_dbtp"],
            "clipped_samples": clipped,
            "static_gain": round(rendered.static_gain, 8),
            "limiter_used": False,
        },
        "loudness": meter.as_dict(),
        "rms_dbfs": round(_db(stereo_rms), 2),
        "event_density_hz": rendered.schedule.metrics["collision_density_hz"],
        "maximum_polyphony": rendered.schedule.metrics["max_scheduled_polyphony"],
        "note_overlap_seconds": rendered.schedule.metrics["estimated_overlap_seconds"],
        "phone": {
            "rms_dbfs": round(_db(phone_rms), 2),
            "relative_to_master_db": round(_db(phone_rms / max(stereo_rms, 1e-12)), 2),
            "band_energy_percent": loudness.band_profile(phone_stereo, rate),
        },
        "mono": mono,
        "spectrum_percent": loudness.band_profile(samples, rate),
        "event_hierarchy": _event_peaks(rendered),
        "synchronization": sync_report(rendered.schedule),
        "ending_silence_peak": silence_peak,
    }

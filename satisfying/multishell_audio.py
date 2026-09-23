"""Sample synthesis and objective measurement for the multiplying-shell score.

Every sound here is generated from oscillators and deterministic arithmetic.
There are no samples, no loops and no background-music layer: the only thing
that plays is what the balls did. The score module owns meaning and timing;
this module only turns an immutable schedule into PCM, and then measures what
it turned it into.

## Two buses, and why

The render sums into a **bed** - collisions and passage markers, the tiers the
brief calls a normal bounce, a strong hit, and a marked contact - and a
**marked bus** carrying spawns, breaks, progression lifts and the escape. The
bed is multiplied by a duck envelope built from the marked events; the marked
bus never ducks. That is the whole implementation of "dense collision beds
must duck or shorten locally for important events": the important events are
on a bus that cannot be ducked by anything, and the crowd steps aside for them
by a measured two to nine decibels.

Splitting the buses is also what makes the hierarchy measurable rather than
asserted. `measure` reports the bed and the marked bus separately, and the
per-kind peak table underneath it is the evidence that a spawn is louder than
the bounce it came from and quieter than the break that follows it.

## The one thing that looks forward

`duck_lead_seconds` opens the duck 80 ms before the event it is for. That is
a gain ramp on a bus, not an event moving in time: every cue still starts on
`round(t * 48000)` and `sync_report` proves it. The alternative - a duck that
begins exactly on the downbeat of the thing it is making room for - arrives
too late to make the room.
"""

from __future__ import annotations

import hashlib
import math
from array import array
from dataclasses import dataclass
from typing import Any

import numpy as np

from audio import loudness
from audio.wav_io import DEFAULT_BIT_DEPTH, pcm_bytes, write_wav
from satisfying.multishell_score import (
    LADDER_TOP,
    AudioConfig,
    AudioEvent,
    AudioSchedule,
    TonalSystem,
)

__all__ = [
    "RENDER_VERSION",
    "RenderedAudio",
    "AudioRenderError",
    "pan_gains",
    "cue_for",
    "duck_envelope",
    "render",
    "write_master",
    "measure",
    "sync_report",
    "richness_report",
    "masking_report",
]

#: Changes when the same schedule would produce different samples.
RENDER_VERSION = "category3-test2-multiplying-shell-audio-render/1.0.0"

#: The tier at and above which an event is on the marked bus and never ducks.
MARKED_TIER = 4

#: The window a per-event level is measured in: long enough to hold an attack
#: and the start of a decay, short enough that the next contact usually is not
#: in it at six a second.
EVENT_WINDOW_SECONDS = 0.055

#: The band the spectral readings are taken over. Below it is the room the
#: escape's sub-octave sits in; above it is nothing this palette generates, and
#: including either would move a ratio around without saying anything musical.
SPECTRAL_LOW_HZ = 100.0
SPECTRAL_HIGH_HZ = 12_000.0

#: How far either side of a palette partial still counts as that partial. A
#: note with an 80 ms decay is about 4 Hz wide at its base, and 35 cents is
#: 9 Hz at 440, so the window holds the skirt without reaching the next
#: degree - the closest pair in any of the three collections is two
#: semitones, 200 cents, apart.
TONAL_WINDOW_CENTS = 35.0
#: The partials the palette actually generates: the sub-octave that gives
#: outer shells their weight, the fundamental, and the three above it.
TONAL_HARMONICS: tuple[float, ...] = (0.5, 1.0, 2.0, 3.0, 4.0)


class AudioRenderError(RuntimeError):
    """The schedule cannot be turned into samples."""


def _db(gain: float) -> float:
    return 20.0 * math.log10(max(gain, 1e-12))


def pan_gains(pan: float) -> tuple[float, float]:
    """Equal-power placement, renormalised so a gain means a peak.

    Amplitude only, so everything folds to mono cleanly and
    `mono_compatibility` is asked to prove it rather than trusted to be true.
    The renormalisation - dividing by the larger of the two gains - is what
    makes the scheduled gain the level the event actually reaches: without it
    a centre-panned cue arrives 3 dB under a hard-panned one of the same
    written level, and the event hierarchy the brief specifies turns into a
    hierarchy of where the ball happened to be standing.
    """
    angle = (max(-1.0, min(1.0, pan)) + 1.0) * math.pi / 4.0
    left = math.cos(angle)
    right = math.sin(angle)
    largest = max(left, right)
    if largest <= 0.0:
        return 1.0, 1.0
    return left / largest, right / largest


def _envelope(length: int, rate: int, attack: float, decay: float) -> np.ndarray:
    """One attack-decay shape that always ends at exact zero."""
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
        cue = cue / peak
    return cue


def _detuned(frequency: float, event: AudioEvent, config: AudioConfig) -> float:
    """A lineage's few cents of width, applied once at the fundamental."""
    return frequency * 2.0 ** (event.detune * config.detune_cents / 1200.0)


# --------------------------------------------------------------------------
# Cues
# --------------------------------------------------------------------------


def _collision_cue(event: AudioEvent, config: AudioConfig, system: TonalSystem) -> np.ndarray:
    """One struck panel, voiced by who hit it, how hard, and what state it was in."""
    rate = config.sample_rate
    length = max(2, int(round(event.seconds * rate)))
    t = np.arange(length, dtype=np.float64) / rate
    freq = _detuned(event.frequency_hz, event, config)
    outer = event.progress
    damage = event.damage_before

    # Articulation. A head-on contact is struck and short; a glancing one is
    # brushed and rings. A lineage's `edge` moves the attack by a factor of
    # about two either way, which is audible as family character and never as
    # a different instrument.
    attack = 0.0011 * (1.9 - 1.1 * event.incidence) * (1.45 - 0.9 * event.edge)
    decay = config.collision_decay * (1.0 + config.damage_ring * damage
                                      + config.shell_ring * outer)
    shape = _envelope(length, rate, attack, decay)

    # The mallet itself. `tint` is the lineage axis: 0 is the rounder relative,
    # 1 the brighter one, and the founder sits at 0.5.
    tint = event.tint
    second = config.resonance * (0.30 + 0.30 * tint + 0.20 * outer)
    third = config.brightness * (0.08 + 0.16 * event.impact + 0.18 * outer) * (0.6 + 0.8 * tint)
    cue = (
        np.sin(2.0 * math.pi * freq * t)
        + second * np.sin(2.0 * math.pi * 2.0 * freq * t + 0.31)
        + third * np.sin(2.0 * math.pi * 3.0 * freq * t + 0.67)
    )

    # Outer shells are heavier, not merely higher: a sub-octave under the
    # fundamental gives the later registers a body their pitch alone does not
    # have, which is how difficulty reads as substance instead of as volume.
    if outer > 0.0:
        weight = config.shell_weight * outer
        cue += weight * np.sin(2.0 * math.pi * 0.5 * freq * t + 0.11)

    cue *= shape

    # Damage is spectral and cumulative. A slightly stretched second partial
    # beats against the true one, faintly at "damaged" and plainly by
    # "fractured", and no sample is involved at any point.
    if damage > 0.0:
        stretched = np.sin(2.0 * math.pi * freq * (2.0 + 0.012 * damage) * t + 1.1)
        cue += stretched * shape * config.damage_colour * damage * 0.28

    # The transient is a pitched high partial rather than broadband noise, so a
    # dense passage stays a passage and does not turn to hiss.
    transient_decay = 0.008 if event.feature == "post" else 0.013
    transient = _envelope(length, rate, 0.00035, transient_decay)
    transient_gain = config.transient * (0.35 + 0.65 * event.impact) * (0.7 + 0.6 * event.edge)
    if event.feature == "post":
        transient_gain *= 1.28
    cue += transient_gain * np.sin(2.0 * math.pi * 4.0 * freq * t + 0.2) * transient

    # A damage-state transition is an event the viewer can see - the panel
    # changes - so it is marked inside the voice that caused it: one short
    # partial a fifth above, brighter the closer the panel is to failing.
    if event.state_step:
        step = event.state_step / (len(system.scale) - 1)
        start = int(round(0.010 * rate))
        span = min(length - start, int(round(0.055 * rate)))
        if span > 1:
            ot = np.arange(span, dtype=np.float64) / rate
            colour = np.sin(2.0 * math.pi * freq * 1.5 * ot + 0.9)
            colour *= _envelope(span, rate, 0.0006, 0.016)
            cue[start:start + span] += colour * config.state_colour * step

    # A canonical near miss is the gap the ball did not take. It gets one
    # neighbour degree that never returns to the note it left, which is what an
    # unresolved ornament is; sign is direction, from `signed_lead`.
    if event.near_miss and event.near_miss_direction:
        neighbour = min(LADDER_TOP, max(0, event.ladder_index + event.near_miss_direction))
        ratio = system.frequency(neighbour) / max(event.frequency_hz, 1e-9)
        start = int(round(0.022 * rate))
        span = min(length - start, int(round(0.075 * rate)))
        if span > 1:
            ot = np.arange(span, dtype=np.float64) / rate
            ornament = np.sin(2.0 * math.pi * freq * ratio * ot + 0.45)
            ornament *= _envelope(span, rate, 0.0009, 0.030)
            cue[start:start + span] += ornament * config.near_miss_colour

    return _normalise(cue)


def _crossing_cue(event: AudioEvent, config: AudioConfig, system: TonalSystem) -> np.ndarray:
    """A ball going back out through a shell it has already been through.

    Under the bed by design: it is the least important thing that happens, and
    there are twice as many of them as there are spawns.
    """
    rate = config.sample_rate
    length = max(2, int(round(event.seconds * rate)))
    t = np.arange(length, dtype=np.float64) / rate
    freq = _detuned(event.frequency_hz, event, config)
    shape = _envelope(length, rate, 0.012, 0.045)
    cue = (np.sin(2.0 * math.pi * freq * t)
           + 0.22 * np.sin(2.0 * math.pi * 2.0 * freq * t + 0.4)) * shape
    return _normalise(cue)


def _spawn_cue(event: AudioEvent, config: AudioConfig, system: TonalSystem) -> np.ndarray:
    """One became two: the parent's note, then the child's, opening outward.

    Two notes and nothing else. The interval is mirrored - a fifth up from a
    low parent, a fifth down from a high one - so the gesture always widens,
    and the pair is laid out across the stereo field in opposite directions so
    a listener hears the split as well as the fifth.
    """
    rate = config.sample_rate
    length = max(2, int(round(event.seconds * rate)))
    split = max(1, int(round(config.spawn_split_seconds * rate)))
    parent_hz = _detuned(event.frequency_hz, event, config)
    child_hz = event.secondary_hz

    left = np.zeros(length, dtype=np.float64)
    right = np.zeros(length, dtype=np.float64)

    head = length
    ht = np.arange(head, dtype=np.float64) / rate
    parent_shape = _envelope(head, rate, 0.0016, 0.070)
    parent = (np.sin(2.0 * math.pi * parent_hz * ht)
              + (0.34 + 0.24 * event.tint) * np.sin(2.0 * math.pi * 2.0 * parent_hz * ht + 0.2)
              ) * parent_shape
    pl, pr = pan_gains(event.pan)
    left[:head] += parent * pl
    right[:head] += parent * pr

    tail = length - split
    if tail > 1:
        ct = np.arange(tail, dtype=np.float64) / rate
        child_shape = _envelope(tail, rate, 0.0014, 0.105)
        child = (np.sin(2.0 * math.pi * child_hz * ct)
                 + (0.34 + 0.24 * event.secondary_tint)
                 * np.sin(2.0 * math.pi * 2.0 * child_hz * ct + 0.2)
                 + 0.14 * np.sin(2.0 * math.pi * 3.0 * child_hz * ct + 0.6)
                 ) * child_shape
        cl, cr = pan_gains(event.secondary_pan)
        left[split:] += child * cl * 1.05
        right[split:] += child * cr * 1.05

    stereo = np.stack([left, right], axis=1)
    peak = float(np.max(np.abs(stereo))) if stereo.size else 0.0
    return stereo / peak if peak > 0.0 else stereo


def _break_cue(event: AudioEvent, config: AudioConfig, system: TonalSystem) -> np.ndarray:
    """A panel giving way: the palette's chord, struck together and gone.

    Short on purpose. A break opens a passage, and the next thing worth hearing
    is a ball using it, so the bloom has to finish before that happens.
    """
    rate = config.sample_rate
    length = max(2, int(round(event.seconds * rate)))
    t = np.arange(length, dtype=np.float64) / rate
    shape = _envelope(length, rate, 0.0022, 0.135 + 0.040 * event.progress)
    cue = np.zeros(length, dtype=np.float64)
    weights = (1.0, 0.74, 0.62, 0.30)
    for weight, index in zip(weights, event.chord):
        cue += weight * np.sin(2.0 * math.pi * system.frequency(index) * t
                               + 0.22 * index)
    # One octave below the struck note, briefly, so the payoff has a floor.
    cue += 0.30 * np.sin(2.0 * math.pi * 0.5 * event.frequency_hz * t + 0.5) * np.exp(-t / 0.055)
    return _normalise(cue * shape)


def _lift_cue(event: AudioEvent, config: AudioConfig, system: TonalSystem) -> np.ndarray:
    """The run reaching a region for the first time.

    An ascending arpeggio rather than a struck chord, which is what keeps it
    distinguishable from a break at the same tier: a break lands, a lift
    climbs.
    """
    rate = config.sample_rate
    length = max(2, int(round(event.seconds * rate)))
    cue = np.zeros(length, dtype=np.float64)
    steps = list(event.chord)
    stagger = max(1, int(round(0.042 * rate)))
    for order, index in enumerate(steps):
        start = order * stagger
        span = length - start
        if span <= 1:
            break
        ot = np.arange(span, dtype=np.float64) / rate
        voice = _envelope(span, rate, 0.006, 0.150 + 0.030 * order)
        frequency = system.frequency(index)
        cue[start:] += (np.sin(2.0 * math.pi * frequency * ot)
                        + 0.30 * np.sin(2.0 * math.pi * 2.0 * frequency * ot + 0.3)
                        ) * voice * (1.0 - 0.10 * order)
    return _normalise(cue)


def _escape_cue(event: AudioEvent, config: AudioConfig, system: TonalSystem) -> np.ndarray:
    """The resolution: the collection's tonic chord, two octaves wide.

    The root is doubled an octave below the ladder's bottom for weight, which
    is the only note in the piece under 220 Hz and the reason the ending has a
    floor a phone will not reproduce and a pair of headphones will.
    """
    rate = config.sample_rate
    length = max(2, int(round(event.seconds * rate)))
    t = np.arange(length, dtype=np.float64) / rate
    cue = np.zeros(length, dtype=np.float64)
    weights = (0.42, 1.0, 0.70, 0.82, 0.46, 0.26)
    for order, (weight, index) in enumerate(zip(weights, event.chord)):
        frequency = system.frequency(index)
        voice = _envelope(length, rate, 0.010 + 0.004 * order, 0.320 + 0.050 * order)
        cue += weight * np.sin(2.0 * math.pi * frequency * t + 0.17 * order) * voice
    return _normalise(cue)


def cue_for(event: AudioEvent, config: AudioConfig,
            system: TonalSystem | None = None) -> np.ndarray:
    """The samples for one scheduled event, mono unless the cue is inherently stereo."""
    system = system if system is not None else config.tonal
    if event.kind == "collision":
        return _collision_cue(event, config, system)
    if event.kind == "crossing":
        return _crossing_cue(event, config, system)
    if event.kind == "spawn":
        return _spawn_cue(event, config, system)
    if event.kind == "break":
        return _break_cue(event, config, system)
    if event.kind == "lift":
        return _lift_cue(event, config, system)
    if event.kind == "escape":
        return _escape_cue(event, config, system)
    raise AudioRenderError(f"unknown scheduled event {event.kind!r}")


# --------------------------------------------------------------------------
# Ducking
# --------------------------------------------------------------------------


def duck_envelope(plan: AudioSchedule) -> np.ndarray:
    """The gain the collision bed is allowed, sample by sample.

    Every marked event opens a dip: a linear 100 ms lead in, a hold for as long
    as the event needs the room, then a raised-cosine release. Dips combine by
    taking the deepest, and the whole envelope is floored so that no stack of
    events can mute the arena.
    """
    config = plan.config
    rate = config.sample_rate
    length = plan.total_samples
    envelope = np.ones(length, dtype=np.float64)
    floor = 10.0 ** (-config.duck_floor_db / 20.0)
    lead = max(1, int(round(config.duck_lead_seconds * rate)))

    depths = {
        "spawn": config.duck_spawn_db,
        "break": config.duck_break_db,
        "lift": config.duck_lift_db,
        "escape": config.duck_escape_db,
    }
    for event in plan.events:
        depth_db = depths.get(event.kind)
        if depth_db is None:
            continue
        if event.kind == "escape":
            hold = int(round(config.duck_escape_hold * rate))
            release = int(round(config.duck_escape_release * rate))
        else:
            hold = int(round(config.duck_marked_hold * rate))
            release = int(round(config.duck_marked_release * rate))
        depth = 10.0 ** (-depth_db / 20.0)
        start = max(0, event.sample_offset - lead)
        peak = min(length, event.sample_offset + hold)
        stop = min(length, peak + release)
        if start >= length:
            continue
        shape = np.ones(stop - start, dtype=np.float64)
        ramp_n = min(lead, stop - start)
        if ramp_n > 0:
            shape[:ramp_n] = np.linspace(1.0, depth, ramp_n, endpoint=True)
        hold_n = max(0, peak - start - ramp_n)
        if hold_n > 0:
            shape[ramp_n:ramp_n + hold_n] = depth
        rest = (stop - start) - ramp_n - hold_n
        if rest > 0:
            curve = 0.5 * (1.0 - np.cos(np.linspace(0.0, math.pi, rest, endpoint=True)))
            shape[ramp_n + hold_n:] = depth + (1.0 - depth) * curve
        envelope[start:stop] = np.minimum(envelope[start:stop], shape)
    return np.maximum(envelope, floor)


# --------------------------------------------------------------------------
# Render
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RenderedAudio:
    schedule: AudioSchedule
    samples: np.ndarray
    bed: np.ndarray
    marked: np.ndarray
    duck: np.ndarray
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
    """Two buses, one duck, one static gain, and no dynamics processor."""
    config = plan.config
    system = config.tonal
    total = plan.total_samples
    bed = np.zeros((total, 2), dtype=np.float64)
    marked = np.zeros((total, 2), dtype=np.float64)

    for event in plan.events:
        cue = cue_for(event, config, system)
        start = event.sample_offset
        stop = min(total, start + cue.shape[0])
        if stop <= start:
            continue
        span = stop - start
        bus = marked if event.tier >= MARKED_TIER else bed
        if cue.ndim == 2:
            bus[start:stop] += cue[:span] * event.gain
        else:
            left, right = pan_gains(event.pan)
            audible = cue[:span] * event.gain
            bus[start:stop, 0] += audible * left
            bus[start:stop, 1] += audible * right

    duck = duck_envelope(plan)
    samples = bed * duck[:, None] + marked

    raw_peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    ceiling = 10.0 ** (config.peak_ceiling_dbfs / 20.0)
    static_gain = config.master_gain
    if raw_peak * static_gain > ceiling:
        static_gain = ceiling / raw_peak
    samples = samples * static_gain
    return RenderedAudio(
        schedule=plan,
        samples=samples,
        bed=bed * duck[:, None] * static_gain,
        marked=marked * static_gain,
        duck=duck,
        static_gain=static_gain,
    )


def write_master(rendered: RenderedAudio, path: str,
                 bit_depth: int = DEFAULT_BIT_DEPTH) -> str:
    return write_wav(path, rendered.left, rendered.right,
                     sample_rate=rendered.sample_rate, bit_depth=bit_depth)


# --------------------------------------------------------------------------
# Measurement
# --------------------------------------------------------------------------


def sync_report(plan: AudioSchedule) -> dict[str, Any]:
    """How far any cue sits from the instant the physics says it happened."""
    rate = plan.config.sample_rate
    errors = [abs(event.sample_offset / rate - event.source_seconds) for event in plan.events]
    worst = max(errors, default=0.0)
    return {
        "events": len(plan.events),
        "max_placement_error_seconds": worst,
        "max_placement_error_samples": worst * rate,
        "within_half_sample": all(error <= 0.5 / rate + 1e-12 for error in errors),
    }


def _kind_of(event: AudioEvent) -> str:
    """The row an event belongs in.

    A spawn that carries a progression lift is its own row rather than part of
    the spawn row. It has to be: the lift is on top of it, so its own level is
    pulled down to keep the pair from summing past the break tier, and on a run
    with seven spawns of which five are lifts the median "spawn" would
    otherwise be the attenuated one and the hierarchy would read backwards.
    """
    if event.kind == "collision":
        return "collision_strong" if event.strong else "collision"
    if event.kind == "spawn" and event.with_lift:
        return "spawn_with_lift"
    return event.kind


def _summarise(grouped: dict[str, list[float]], extra: dict[str, int]) -> dict[str, Any]:
    return {
        key: {
            "count": len(values),
            "shadowed": extra.get(key, 0),
            "median_peak_dbfs": round(_db(float(np.median(values))), 2),
            "max_peak_dbfs": round(_db(max(values)), 2),
        }
        for key, values in sorted(grouped.items())
        if values
    }


def _event_peaks(rendered: RenderedAudio) -> dict[str, Any]:
    """What each kind of event is worth on its own, as the hierarchy check.

    Every cue is peak-normalised before its gain is applied, so an event's own
    contribution to the master is exactly `gain x pan x static_gain`, and this
    table is that number per kind. It is the design hierarchy - the brief's
    ordering, measured on what the score decided rather than on what happened
    to be decaying at the same moment - and it is the one `hierarchy_ok` reads.
    """
    static = rendered.static_gain
    grouped: dict[str, list[float]] = {}
    for event in rendered.schedule.events:
        left, right = pan_gains(event.pan)
        reach = max(left, right)
        grouped.setdefault(_kind_of(event), []).append(event.gain * reach * static)
    return _summarise(grouped, {})


def _event_peaks_in_mix(rendered: RenderedAudio) -> dict[str, Any]:
    """What a listener actually meets at each event, and how often that is asked.

    An event is left out when anything more important is sounding across its
    window, and the count of those is reported next to the survivors. Without
    that exclusion the table lies in one specific, repeatable way: every
    progression lift shares its sample with the spawn that caused it, so on a
    run with twelve spawns and five lifts the *median* spawn window is a lift
    window, and a spawn appears to be louder than the panel break it sits
    under. Even with it, the marked bus is busy enough that a kind can run out
    of clean windows, which is why `count` is printed beside every median.
    """
    rate = rendered.sample_rate
    size = int(round(EVENT_WINDOW_SECONDS * rate))
    events = rendered.schedule.events
    spans = [(event.sample_offset,
              event.sample_offset + int(round(event.seconds * rate)),
              event.tier) for event in events]
    grouped: dict[str, list[float]] = {}
    shadowed: dict[str, int] = {}
    for index, event in enumerate(events):
        start = event.sample_offset
        stop = min(rendered.samples.shape[0], start + size)
        key = _kind_of(event)
        eclipsed = False
        for other_start, other_stop, other_tier in spans[max(0, index - 64):index + 64]:
            if other_tier <= event.tier:
                continue
            if other_start < start + size and other_stop > start:
                eclipsed = True
                break
        if eclipsed:
            shadowed[key] = shadowed.get(key, 0) + 1
            continue
        bus = rendered.marked if event.tier >= MARKED_TIER else rendered.bed
        peak = float(np.max(np.abs(bus[start:stop]))) if stop > start else 0.0
        grouped.setdefault(key, []).append(peak)
    return _summarise(grouped, shadowed)


def _spectrum(mono: np.ndarray, rate: int) -> tuple[np.ndarray, np.ndarray]:
    if mono.size < 16:
        return np.zeros(0), np.zeros(0)
    window = np.hanning(mono.size)
    spectrum = np.fft.rfft(mono * window)
    power = (spectrum.real ** 2 + spectrum.imag ** 2)
    freqs = np.fft.rfftfreq(mono.size, 1.0 / rate)
    keep = (freqs >= SPECTRAL_LOW_HZ) & (freqs <= SPECTRAL_HIGH_HZ)
    return freqs[keep], power[keep]


def _palette_mask(freqs: np.ndarray, system: TonalSystem) -> np.ndarray:
    """Which spectrum bins belong to a note the palette is able to play."""
    mask = np.zeros(freqs.size, dtype=bool)
    ratio = 2.0 ** (TONAL_WINDOW_CENTS / 1200.0)
    for index in range(LADDER_TOP + 1):
        base = system.frequency(index)
        for harmonic in TONAL_HARMONICS:
            centre = base * harmonic
            if centre < SPECTRAL_LOW_HZ or centre > SPECTRAL_HIGH_HZ:
                continue
            mask |= (freqs >= centre / ratio) & (freqs <= centre * ratio)
    return mask


def _spectral_shape(mono: np.ndarray, rate: int, system: TonalSystem) -> dict[str, float]:
    """Centroid, palette share and crest over one span - the "is it noise" reading.

    Spectral flatness is the textbook instrument here and it is useless on this
    material: a sum of pure partials has near-zero energy in most bins, so the
    geometric mean underflows and every third reads 0.00001 whether one ball is
    playing or fifteen are. What the question actually needs is how much of the
    energy is still standing *on notes the palette can play*, which does
    separate a dense chord from a wash - about 90% on these renders against
    17.5% for white noise at the same RMS.
    """
    freqs, power = _spectrum(mono, rate)
    total = float(power.sum())
    if total <= 0.0 or freqs.size == 0:
        return {"centroid_hz": 0.0, "tonal_percent": 0.0, "crest_db": 0.0,
                "above_2k_percent": 0.0, "rms_dbfs": -120.0}
    centroid = float((freqs * power).sum() / total)
    tonal = float(power[_palette_mask(freqs, system)].sum()) / total
    crest = 10.0 * math.log10(float(power.max()) / max(float(power.mean()), 1e-30))
    above = float(power[freqs >= 2000.0].sum()) / total
    return {
        "centroid_hz": round(centroid, 2),
        "tonal_percent": round(100.0 * tonal, 3),
        "crest_db": round(crest, 2),
        "above_2k_percent": round(100.0 * above, 3),
        "rms_dbfs": round(_db(float(np.sqrt(np.mean(mono * mono)))), 2),
    }


def richness_report(rendered: RenderedAudio) -> dict[str, Any]:
    """Early, middle and late, measured on the rendered signal and on the score.

    The verdict this exists for is the brief's: late richer than early, without
    becoming noise. Richness is read on five axes - how many voices sound at
    once, how many events arrive, how many balls are playing, how high the
    spectrum sits and how much of the pitch compass is in use - and the noise
    guard is the share of energy still standing on palette pitches.
    """
    rate = rendered.sample_rate
    samples = rendered.samples
    total = samples.shape[0]
    mono = samples.mean(axis=1)
    bounds = (total // 3, 2 * total // 3)
    spans = {
        "early": mono[:bounds[0]],
        "middle": mono[bounds[0]:bounds[1]],
        "late": mono[bounds[1]:],
    }
    scored = {row["third"]: row
              for row in rendered.schedule.metrics["progression"]["thirds"]}
    out: dict[str, Any] = {"thirds": []}
    for name in ("early", "middle", "late"):
        span = spans[name]
        stereo = np.stack([span, span], axis=1)
        shape = _spectral_shape(span, rate, rendered.schedule.config.tonal)
        row = dict(scored[name])
        row.update(shape)
        row["short_term_lufs"] = round(loudness.integrated(stereo, rate), 2)
        row["peak_dbfs"] = round(_db(float(np.max(np.abs(span)))) if span.size else -120.0, 2)
        out["thirds"].append(row)

    early, middle, late = out["thirds"]
    out["verdict"] = {
        "late_polyphony_over_early": round(
            late["mean_polyphony"] - early["mean_polyphony"], 4),
        "late_density_over_early": round(
            late["events_per_second"] - early["events_per_second"], 4),
        "late_centroid_over_early_hz": round(late["centroid_hz"] - early["centroid_hz"], 2),
        "late_pitches_over_early": late["distinct_pitches"] - early["distinct_pitches"],
        "late_balls_over_early": late["distinct_balls"] - early["distinct_balls"],
        "late_lufs_over_early": round(late["short_term_lufs"] - early["short_term_lufs"], 2),
        "tonal_percent_early": early["tonal_percent"],
        "tonal_percent_late": late["tonal_percent"],
        "tonal_percent_change": round(late["tonal_percent"] - early["tonal_percent"], 3),
        "crest_db_late": late["crest_db"],
        "richer_late": (
            late["mean_polyphony"] > early["mean_polyphony"]
            and late["events_per_second"] > early["events_per_second"]
            and late["distinct_balls"] > early["distinct_balls"]
        ),
        # Not noise: most of the late energy is still standing on notes the
        # palette can play, and the late third has not given up more than
        # five points of that share against the sparse opening.
        "not_noise": (
            late["tonal_percent"] >= 80.0
            and late["tonal_percent"] >= early["tonal_percent"] - 5.0
        ),
        "middle_peak_density": middle["events_per_second"] > late["events_per_second"],
    }
    return out


def masking_report(rendered: RenderedAudio,
                   window_seconds: float = 0.025) -> dict[str, Any]:
    """How far the mix rises across each contact - the "can it still be heard" reading.

    A voice that is long enough to make the arena musical is also long enough
    to bury the next bounce underneath its own decay, and that trade is the one
    real risk in a piece with fifteen players. The measurement is the level
    step across an onset: the peak of the 25 ms after a contact against the RMS
    of the 25 ms before it. A contact that does not lift the mix at all is a
    bounce the viewer sees and does not hear, which is the failure this phase
    is not allowed to ship.
    """
    rate = rendered.sample_rate
    size = max(1, int(round(window_seconds * rate)))
    envelope = np.abs(rendered.samples).max(axis=1)
    total = envelope.size
    rises: list[float] = []
    for event in rendered.schedule.events:
        if event.kind != "collision":
            continue
        start = event.sample_offset
        prior = envelope[max(0, start - size):start]
        following = envelope[start:min(total, start + size)]
        if following.size == 0:
            continue
        floor = float(np.sqrt(np.mean(prior * prior))) if prior.size else 0.0
        rises.append(_db(float(following.max())) - _db(max(floor, 1e-9)))
    if not rises:
        return {"collisions": 0}
    values = np.array(rises, dtype=np.float64)
    return {
        "collisions": int(values.size),
        "median_onset_rise_db": round(float(np.median(values)), 2),
        "p10_onset_rise_db": round(float(np.percentile(values, 10)), 2),
        "min_onset_rise_db": round(float(values.min()), 2),
        "below_3db": int(np.count_nonzero(values < 3.0)),
        "below_3db_fraction": round(float(np.count_nonzero(values < 3.0)) / values.size, 4),
        "below_6db": int(np.count_nonzero(values < 6.0)),
        "below_6db_fraction": round(float(np.count_nonzero(values < 6.0)) / values.size, 4),
    }


def _duck_report(rendered: RenderedAudio) -> dict[str, Any]:
    """How much the bed stepped aside, how often, and what the escape got for it.

    `escape_space_db` is the one number the climax test turns on: the bed's own
    level in the second after the escape against its level in the second
    before. The canonical run stops at the first escape, so nothing new is
    struck after it - what the duck actually clears is the decaying tail of
    everything that was still ringing, which is what leaves the resolution
    alone in the room.
    """
    duck = rendered.duck
    rate = rendered.sample_rate
    below = duck < 10.0 ** (-1.0 / 20.0)
    transitions = int(np.count_nonzero(np.diff(below.astype(np.int8)) == 1))
    span = duck.size / rate
    escape_at = int(round(rendered.schedule.escape_seconds * rate))
    window = int(round(1.0 * rate))
    bed = np.abs(rendered.bed).max(axis=1)
    prior = bed[max(0, escape_at - window):escape_at]
    after = bed[escape_at:min(bed.size, escape_at + window)]
    prior_rms = float(np.sqrt(np.mean(prior * prior))) if prior.size else 0.0
    after_rms = float(np.sqrt(np.mean(after * after))) if after.size else 0.0
    return {
        "escape_space_db": round(_db(after_rms) - _db(max(prior_rms, 1e-12)), 2),
        "bed_before_escape_dbfs": round(_db(prior_rms), 2),
        "bed_after_escape_dbfs": round(_db(after_rms), 2),
        "max_duck_db": round(-_db(float(duck.min())), 2) if duck.size else 0.0,
        "median_duck_db": round(-_db(float(np.median(duck))), 3) if duck.size else 0.0,
        "seconds_below_minus_1db": round(float(np.count_nonzero(below)) / rate, 3),
        "fraction_below_minus_1db": round(float(np.count_nonzero(below)) / max(duck.size, 1), 4),
        "duck_onsets": transitions,
        "duck_onsets_per_second": round(transitions / span, 3) if span else 0.0,
    }


def _rendered_polyphony(rendered: RenderedAudio, floor_db: float = -50.0) -> dict[str, Any]:
    """Voices actually sounding, read off the schedule against the rendered floor.

    The schedule's own polyphony counts a voice for its whole designed length.
    This one drops a voice once the mix it sits in has fallen 50 dB below the
    loudest moment of the piece, which is the honest number for "how many
    things can be heard at once".
    """
    rate = rendered.sample_rate
    samples = rendered.samples
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    threshold = peak * 10.0 ** (floor_db / 20.0)
    envelope = np.abs(samples).max(axis=1)
    audible = envelope > threshold
    live = np.zeros(samples.shape[0], dtype=np.int32)
    for event in rendered.schedule.events:
        start = event.sample_offset
        stop = min(samples.shape[0], start + int(round(event.seconds * rate)))
        if stop > start:
            live[start:stop] += 1
    counted = live[audible]
    if counted.size == 0:
        return {"max": 0, "median": 0.0, "mean": 0.0, "p95": 0.0}
    return {
        "max": int(counted.max()),
        "median": float(np.median(counted)),
        "mean": round(float(counted.mean()), 4),
        "p95": float(np.percentile(counted, 95)),
    }


def measure(rendered: RenderedAudio) -> dict[str, Any]:
    """Every delivery number the phase is judged on, in one pass."""
    plan = rendered.schedule
    samples = rendered.samples
    rate = rendered.sample_rate
    meter = loudness.measure(samples, rate)
    mono = loudness.mono_compatibility(samples, rate)
    phone = loudness.phone_filter(samples, rate)
    phone_stereo = np.repeat(phone, 2, axis=1)
    phone_rms = float(np.sqrt(np.mean(phone * phone)))
    stereo_rms = float(np.sqrt(np.mean(samples * samples)))
    bed_rms = float(np.sqrt(np.mean(rendered.bed * rendered.bed)))
    marked_rms = float(np.sqrt(np.mean(rendered.marked * rendered.marked)))
    clipped = int(np.count_nonzero(np.abs(samples) >= 1.0))
    silence_n = int(round(plan.config.end_silence_seconds * rate))
    silence_peak = float(np.max(np.abs(samples[-silence_n:]))) if silence_n else 0.0
    metrics = plan.metrics
    return {
        "render_version": RENDER_VERSION,
        "seed": plan.seed,
        "config_name": plan.config.name,
        "tonal_system": plan.config.system,
        "playback_digest": plan.playback_digest,
        "score_fingerprint": plan.fingerprint(),
        "config_fingerprint": plan.config.fingerprint(),
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
        "buses": {
            "bed_rms_dbfs": round(_db(bed_rms), 2),
            "marked_rms_dbfs": round(_db(marked_rms), 2),
            "marked_over_bed_db": round(_db(marked_rms / max(bed_rms, 1e-12)), 2),
        },
        "density": {
            "collision_density_hz": metrics["collision_density_hz"],
            "event_density_hz": metrics["event_density_hz"],
            "median_collision_gap_seconds": metrics["median_collision_gap_seconds"],
            "minimum_collision_gap_seconds": metrics["minimum_collision_gap_seconds"],
            "simultaneous_within_cluster": metrics["simultaneous_within_cluster"],
        },
        "polyphony": {
            "scheduled_max": metrics["max_scheduled_polyphony"],
            "scheduled_median": metrics["median_scheduled_polyphony"],
            "scheduled_mean": metrics["mean_scheduled_polyphony"],
            "audible": _rendered_polyphony(rendered),
        },
        "voices": {
            "total_voice_seconds": metrics["voice_seconds_total"],
            "collision_median_seconds": metrics["collision_voice_seconds_median"],
            "collision_min_seconds": metrics["collision_voice_seconds_min"],
            "collision_max_seconds": metrics["collision_voice_seconds_max"],
            "overlap_ratio": round(
                metrics["voice_seconds_total"] / max(metrics["total_seconds"], 1e-9), 4),
            "distinct_balls": metrics["distinct_balls"],
            "generations": metrics["generations"],
        },
        "repetition": {
            "longest_same_pitch_run": metrics["longest_same_pitch_run"],
            "runs_of_three_or_more": metrics["runs_of_three_or_more"],
            "repeat_nudged": metrics["repeat_nudged"],
            "cluster_nudged": metrics["cluster_nudged"],
        },
        "consonance": metrics["consonance"],
        "duck": _duck_report(rendered),
        "masking": masking_report(rendered),
        "phone": {
            "rms_dbfs": round(_db(phone_rms), 2),
            "relative_to_master_db": round(_db(phone_rms / max(stereo_rms, 1e-12)), 2),
            "band_energy_percent": loudness.band_profile(phone_stereo, rate),
        },
        "mono": mono,
        "spectrum_percent": loudness.band_profile(samples, rate),
        "event_hierarchy": _event_peaks(rendered),
        "event_hierarchy_in_mix": _event_peaks_in_mix(rendered),
        "richness": richness_report(rendered),
        "synchronization": sync_report(plan),
        "ending_silence_peak": silence_peak,
        "by_kind": metrics["by_kind"],
        "by_tier": metrics["by_tier"],
    }

"""One replay to one stereo PCM master, on an exact integer timeline.

The whole point of this module is that nothing in it measures time. The
production format is 48 kHz against 60 output frames and 120 physics ticks a
second, which makes both conversions exact integers:

    48000 / 60  = 800 samples per output frame
    48000 / 120 = 400 samples per physics tick

So an event recorded on tick N is placed at sample N * 400, and a render of
N frames is exactly N * 800 samples per channel. No wall clock, no sleep, no
accumulating float duration, and nothing that could drift over a 25-second
Short. The soundtrack's length is asserted rather than measured.

The input is the exported replay and the frame count the render plan decided
on - never a fresh simulation. A replay is frozen by definition, and audio
that came from re-running a seed could disagree with the pixels beside it.
"""

from __future__ import annotations

import math
from array import array
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from audio import cues
from audio.synthesis import (
    CHANNELS,
    SAMPLE_RATE,
    add_into,
    db_to_gain,
    gain_to_db,
    peak,
    rms,
    scale,
    seconds_to_samples,
    silence,
    stable_seed,
)
from audio.wav_io import DEFAULT_BIT_DEPTH

# The soundtrack format's own version, separate from the replay format (v6),
# the batch manifest (v1) and the render manifest (v1). It changes when the
# same replay would produce different audio.
SOUNDTRACK_VERSION = 1

# The production rates. Both are validated against the replay rather than
# trusted, because the exactness above is the only reason this module can use
# integer arithmetic at all.
VIDEO_FPS = 60
PHYSICS_HZ = 120
SAMPLES_PER_FRAME = SAMPLE_RATE // VIDEO_FPS
SAMPLES_PER_TICK = SAMPLE_RATE // PHYSICS_HZ

# Event types, as the battle mode records them.
EVENT_POWER_ACTIVATE = "power_activate"
EVENT_HIT = "hit"
EVENT_ELIMINATION = "elimination"

# Master ceiling. Left a decibel below full scale so that a lossy encode,
# which does not preserve sample peaks, still has somewhere to put its
# overshoot.
PEAK_CEILING_DBFS = -1.0
PEAK_CEILING = db_to_gain(PEAK_CEILING_DBFS)
# Look-ahead and release of the safety limiter, as one number: the gain
# envelope is a sliding minimum over this radius followed by a moving average
# over the same radius, which is what makes it provably unable to leave a
# sample above the ceiling. See `master`.
LIMITER_RADIUS_SECONDS = 0.024
# How far the master stage may lift a mix that came out under the ceiling.
# Cue levels already land a normal battle within a decibel or two of it, so
# this only ever spends the last of the headroom - which is worth doing
# because five Shorts watched one after another should peak at the same
# place. Capped so that a soundtrack with almost nothing in it, such as an
# audit of the ambient bed on its own, cannot be inflated to look loud.
MASTER_MAKEUP_MAX_DB = 3.0

# How far a cue is allowed to be pushed off centre. Restrained on purpose:
# the arena is 960 logical pixels wide on a phone screen held at arm's
# length, so a hard pan would be wider than the picture it belongs to.
MAX_PAN = 0.6


class SoundtrackError(ValueError):
    """The replay cannot be turned into a production soundtrack."""


# --- the exact timeline -----------------------------------------------------


def samples_per_frame(sample_rate: int = SAMPLE_RATE, fps: int = VIDEO_FPS) -> int:
    """Samples in one output frame. Refuses a rate that does not divide."""
    if fps <= 0:
        raise SoundtrackError(f"frame rate must be positive: {fps}")
    if sample_rate % fps:
        raise SoundtrackError(
            f"{sample_rate} Hz does not divide into {fps} frames per second;"
            " this soundtrack only addresses whole samples"
        )
    return sample_rate // fps


def samples_per_tick(sample_rate: int = SAMPLE_RATE, physics_hz: int = PHYSICS_HZ) -> int:
    """Samples in one physics tick. Refuses a rate that does not divide."""
    if physics_hz <= 0:
        raise SoundtrackError(f"physics rate must be positive: {physics_hz}")
    if sample_rate % physics_hz:
        raise SoundtrackError(
            f"{sample_rate} Hz does not divide into {physics_hz} ticks per second;"
            " this soundtrack only addresses whole samples"
        )
    return sample_rate // physics_hz


def frame_to_sample(
    index: int, sample_rate: int = SAMPLE_RATE, fps: int = VIDEO_FPS
) -> int:
    """The first sample of output frame `index`."""
    if index < 0:
        raise SoundtrackError(f"frame index cannot be negative: {index}")
    return index * samples_per_frame(sample_rate, fps)


def tick_to_sample(
    tick: int, sample_rate: int = SAMPLE_RATE, physics_hz: int = PHYSICS_HZ
) -> int:
    """The sample a physics tick lands on. The timing authority, in one line."""
    if tick < 0:
        raise SoundtrackError(f"tick cannot be negative: {tick}")
    return tick * samples_per_tick(sample_rate, physics_hz)


def total_samples(
    frame_count: int, sample_rate: int = SAMPLE_RATE, fps: int = VIDEO_FPS
) -> int:
    """Exactly how long a soundtrack for `frame_count` frames is."""
    if frame_count < 0:
        raise SoundtrackError(f"frame count cannot be negative: {frame_count}")
    return frame_count * samples_per_frame(sample_rate, fps)


@dataclass(frozen=True)
class SoundtrackPlan:
    """The soundtrack a replay and a frame count produce, before any audio."""

    seed: int
    replay_version: int
    frame_count: int
    gameplay_frames: int
    post_roll_frames: int
    fps: int
    physics_hz: int
    sample_rate: int
    channels: int
    bit_depth: int
    arena_left: float
    arena_right: float

    @property
    def samples_per_frame(self) -> int:
        return samples_per_frame(self.sample_rate, self.fps)

    @property
    def samples_per_tick(self) -> int:
        return samples_per_tick(self.sample_rate, self.physics_hz)

    @property
    def total_samples(self) -> int:
        return total_samples(self.frame_count, self.sample_rate, self.fps)

    @property
    def duration(self) -> float:
        return self.total_samples / self.sample_rate


def plan_soundtrack(
    replay: dict[str, Any],
    frame_count: int,
    *,
    fps: int = VIDEO_FPS,
    sample_rate: int = SAMPLE_RATE,
    bit_depth: int = DEFAULT_BIT_DEPTH,
) -> SoundtrackPlan:
    """Turn a loaded replay plus a render's frame count into a soundtrack plan.

    `frame_count` comes from the render that already exists - gameplay frames
    plus post-roll - so the audio is exactly as long as the pictures it will
    be muxed with, rather than as long as the battle was.
    """
    frames = replay.get("frames") or []
    if not frames:
        raise SoundtrackError("replay has no frames")

    replay_fps = int(replay.get("fps", fps))
    if replay_fps != fps:
        raise SoundtrackError(
            f"replay was sampled at {replay_fps} fps but the soundtrack wants {fps}"
        )
    if frame_count < len(frames):
        raise SoundtrackError(
            f"render has {frame_count} frames, fewer than the replay's {len(frames)}"
        )

    arena = replay.get("arena") or {}
    canvas = replay.get("canvas") or {}
    left = float(arena.get("left", 0.0))
    right = float(arena.get("right", canvas.get("width", 1080)))

    return SoundtrackPlan(
        seed=int(replay.get("seed", 0)),
        replay_version=int(replay.get("version", 0)),
        frame_count=frame_count,
        gameplay_frames=len(frames),
        post_roll_frames=frame_count - len(frames),
        fps=fps,
        physics_hz=int(replay.get("physics_hz", PHYSICS_HZ)),
        sample_rate=sample_rate,
        channels=CHANNELS,
        bit_depth=bit_depth,
        arena_left=left,
        arena_right=right,
    )


# --- stereo placement -------------------------------------------------------


def pan_for_x(
    x: float, arena_left: float, arena_right: float, max_pan: float = MAX_PAN
) -> float:
    """Where in the stereo field something at arena position `x` belongs.

    Centre of the arena is dead centre; the walls are `max_pan` out. Clamped,
    so an event recorded slightly outside the bounds - a contact point on the
    far side of a wall - cannot pan further than the wall itself.
    """
    half = 0.5 * (arena_right - arena_left)
    if half <= 0.0:
        return 0.0
    offset = (x - (arena_left + half)) / half
    return max(-1.0, min(1.0, offset)) * max_pan


def pan_gains(pan: float) -> tuple[float, float]:
    """Channel gains for a pan position in [-1, 1].

    The shape is the usual equal-power law - cosine and sine of a quarter
    turn - renormalised so the nearer channel always gets the cue's full
    designed level. Cue levels in `audio.cues` are budgeted as peaks, and
    dividing by the larger gain is what keeps that budget true; across the
    restrained range panning actually uses, the total power this gives up
    is a little over a decibel.
    """
    pan = max(-1.0, min(1.0, pan))
    angle = (pan + 1.0) * math.pi / 4.0
    left = math.cos(angle)
    right = math.sin(angle)
    largest = max(left, right)
    if largest <= 0.0:
        return 1.0, 1.0
    return left / largest, right / largest


# --- mastering --------------------------------------------------------------


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


def master(
    left: array,
    right: array,
    *,
    ceiling: float = PEAK_CEILING,
    radius_seconds: float = LIMITER_RADIUS_SECONDS,
    sample_rate: int = SAMPLE_RATE,
    makeup: bool = False,
) -> MasterReport:
    """Bring the finished mix under the ceiling, in place, without clipping.

    The mix is mastered once, globally, after everything is in it - never by
    trimming individual effects that have already been placed, which would
    change the balance the cue levels were designed to give.

    Below the ceiling nothing happens at all, which is the normal case: cue
    levels are budgeted so a real battle never needs this. When something
    does need holding back, the gain envelope is built in two passes - a
    sliding minimum of the gain each sample needs, then a moving average of
    that over the same radius. The order matters: every minimum inside the
    averaging window already accounts for the loudest sample at the centre,
    so the average can never exceed what that sample needs. That is a proof
    rather than a tuning, and it is why nothing can slip through.

    Both channels get the same envelope, so the stereo image does not move
    when the limiter engages.

    `makeup` then spends whatever headroom is left over, up to
    `MASTER_MAKEUP_MAX_DB`, as one linear gain over the whole timeline. It is
    off by default: the ambient bed is calibrated by RMS and an audit of it
    alone must hear the level it will really have, not a version lifted to
    the ceiling to fill a Short that has no events in it.
    """
    peak_before = max(peak(left), peak(right))
    if peak_before <= 0.0:
        return MasterReport(peak_before, peak_before, 1.0, False)
    if peak_before <= ceiling:
        return MasterReport(
            peak_before,
            _makeup(left, right, peak_before, ceiling) if makeup else peak_before,
            1.0,
            False,
            makeup_gain=(
                min(ceiling / peak_before, db_to_gain(MASTER_MAKEUP_MAX_DB))
                if makeup
                else 1.0
            ),
        )

    length = len(left)
    needed = silence(length)
    for index in range(length):
        loudest = max(abs(left[index]), abs(right[index]))
        needed[index] = 1.0 if loudest <= ceiling else ceiling / loudest

    radius = max(1, seconds_to_samples(radius_seconds, sample_rate))
    envelope = _boxcar(_sliding_min(needed, radius), radius)

    smallest = 1.0
    for index in range(length):
        gain = envelope[index]
        left[index] *= gain
        right[index] *= gain
        if gain < smallest:
            smallest = gain

    limited_peak = max(peak(left), peak(right))
    gain = 1.0
    if makeup:
        gain = min(ceiling / limited_peak, db_to_gain(MASTER_MAKEUP_MAX_DB))
        _makeup(left, right, limited_peak, ceiling)
    return MasterReport(
        peak_before,
        max(peak(left), peak(right)),
        smallest,
        True,
        makeup_gain=gain,
    )


def _makeup(left: array, right: array, current: float, ceiling: float) -> float:
    """Lift both channels toward the ceiling, by the same bounded gain."""
    gain = min(ceiling / current, db_to_gain(MASTER_MAKEUP_MAX_DB))
    scale(left, gain)
    scale(right, gain)
    return current * gain


# --- building one soundtrack ------------------------------------------------


@dataclass(frozen=True)
class ScheduledCue:
    """One cue, and exactly where it was placed."""

    tick: int
    sample: int
    name: str
    pan: float
    level_dbfs: float
    length: int


@dataclass(frozen=True)
class Soundtrack:
    """A finished stereo master, and everything worth reporting about it."""

    plan: SoundtrackPlan
    left: array
    right: array
    schedule: tuple[ScheduledCue, ...] = ()
    events_total: int = 0
    events_unvoiced: int = 0
    events_past_end: int = 0
    peak_before_master: float = 0.0
    peak: float = 0.0
    level_rms: float = 0.0
    limiter_gain: float = 1.0
    limited: bool = False
    makeup_gain: float = 1.0
    has_ambience: bool = True
    cue_counts: dict[str, int] = field(default_factory=dict)

    @property
    def sample_count(self) -> int:
        return len(self.left)


def cue_seed(replay_seed: int, event: dict[str, Any]) -> int:
    """The PRNG seed one event's noise is drawn from.

    Every part of it is a stable property of the replay: the seed that
    produced the battle, the tick the moment happened on, what kind of moment
    it was and who was involved. Two identical hits at different moments
    therefore get different noise, and the same hit gets the same noise on
    every run and every machine.
    """
    return stable_seed(
        replay_seed,
        event.get("tick"),
        event.get("type"),
        event.get("subtype"),
        event.get("source_id"),
        event.get("target_id"),
    )


def cue_for_event(
    event: dict[str, Any], replay_seed: int, sample_rate: int
) -> cues.Cue | None:
    """The sound one event makes, or None if it is not a moment with a sound."""
    seed = cue_seed(replay_seed, event)
    kind = event.get("type")
    if kind == EVENT_HIT:
        return cues.hit_cue(event.get("subtype"), event.get("magnitude"), seed, sample_rate)
    if kind == EVENT_POWER_ACTIVATE:
        return cues.activation_cue(event.get("subtype"), seed, sample_rate)
    if kind == EVENT_ELIMINATION:
        return cues.elimination_cue(seed, sample_rate)
    return None


def build_soundtrack(
    replay: dict[str, Any],
    plan: SoundtrackPlan,
    *,
    include_ambience: bool = True,
    include_events: bool = True,
) -> Soundtrack:
    """Render the whole soundtrack for one replay.

    `include_ambience` and `include_events` exist so a check can isolate one
    of the two - proving a cue starts on exactly the sample it should is much
    easier against silence than against a bed that is never silent - and so a
    listening audit can hear either half on its own. Production uses both.
    """
    length = plan.total_samples
    if include_ambience:
        left, right = cues.ambience(
            length,
            seed=stable_seed(plan.seed, "ambience", SOUNDTRACK_VERSION),
            sample_rate=plan.sample_rate,
        )
    else:
        left, right = silence(length), silence(length)

    events = replay.get("events") or []
    schedule: list[ScheduledCue] = []
    counts: dict[str, int] = {}
    unvoiced = 0
    past_end = 0

    if include_events:
        for event in events:
            sample = tick_to_sample(
                int(event.get("tick", 0)), plan.sample_rate, plan.physics_hz
            )
            if sample >= length:
                # A moment recorded after the last frame the render contains.
                # It cannot be heard, so it is counted rather than clamped
                # onto the final sample where it would arrive at the wrong time.
                past_end += 1
                continue
            cue = cue_for_event(event, plan.seed, plan.sample_rate)
            if cue is None:
                unvoiced += 1
                continue

            pan = pan_for_x(
                float(event.get("x", 0.0)), plan.arena_left, plan.arena_right
            )
            gain_left, gain_right = pan_gains(pan)
            add_into(left, cue.buffer, sample, gain_left)
            add_into(right, cue.buffer, sample, gain_right)

            schedule.append(
                ScheduledCue(
                    tick=int(event.get("tick", 0)),
                    sample=sample,
                    name=cue.name,
                    pan=pan,
                    level_dbfs=cue.level_dbfs,
                    length=cue.length,
                )
            )
            counts[cue.name] = counts.get(cue.name, 0) + 1

    report = master(
        left, right, sample_rate=plan.sample_rate, makeup=bool(schedule)
    )

    if len(left) != length or len(right) != length:
        raise SoundtrackError(
            f"soundtrack is {len(left)} and {len(right)} samples,"
            f" expected exactly {length}"
        )

    return Soundtrack(
        plan=plan,
        left=left,
        right=right,
        schedule=tuple(schedule),
        events_total=len(events),
        events_unvoiced=unvoiced,
        events_past_end=past_end,
        peak_before_master=report.peak_before,
        peak=report.peak_after,
        level_rms=0.5 * (rms(left) + rms(right)),
        limiter_gain=report.limiter_gain,
        limited=report.limited,
        makeup_gain=report.makeup_gain,
        has_ambience=include_ambience,
        cue_counts=counts,
    )


# --- the deterministic sidecar ---------------------------------------------


def audio_metadata(
    soundtrack: Soundtrack,
    *,
    replay_name: str,
    replay_path: str,
    replay_sha256: str,
    pcm_sha256: str,
) -> dict[str, Any]:
    """The sidecar written beside a finished WAV.

    Everything in here is derived from the replay, the plan and the samples.
    No timestamps, no hardware, no absolute paths, no run ids - build the same
    soundtrack twice and the two files are byte for byte the same. How long
    synthesis took is console output, not metadata.
    """
    plan = soundtrack.plan
    return {
        "audio_version": SOUNDTRACK_VERSION,
        "replay": {
            "name": replay_name,
            "path": replay_path,
            "version": plan.replay_version,
            "seed": plan.seed,
            "sha256": replay_sha256,
        },
        "audio": {
            "sample_rate": plan.sample_rate,
            "channels": plan.channels,
            "bit_depth": plan.bit_depth,
            "samples": soundtrack.sample_count,
            "duration": round(soundtrack.sample_count / plan.sample_rate, 6),
            "samples_per_frame": plan.samples_per_frame,
            "samples_per_tick": plan.samples_per_tick,
            "pcm_sha256": pcm_sha256,
        },
        "timeline": {
            "fps": plan.fps,
            "physics_hz": plan.physics_hz,
            "frame_count": plan.frame_count,
            "gameplay_frames": plan.gameplay_frames,
            "post_roll_frames": plan.post_roll_frames,
        },
        "events": {
            "total": soundtrack.events_total,
            "scheduled": len(soundtrack.schedule),
            "unvoiced": soundtrack.events_unvoiced,
            "past_end": soundtrack.events_past_end,
            "by_cue": dict(sorted(soundtrack.cue_counts.items())),
        },
        "levels": {
            "ambience": soundtrack.has_ambience,
            "ceiling_dbfs": round(PEAK_CEILING_DBFS, 3),
            "peak": round(soundtrack.peak, 6),
            "peak_dbfs": round(gain_to_db(soundtrack.peak), 3),
            "rms_dbfs": round(gain_to_db(soundtrack.level_rms), 3),
            "limited": soundtrack.limited,
            "limiter_gain": round(soundtrack.limiter_gain, 6),
            "makeup_gain": round(soundtrack.makeup_gain, 6),
        },
    }


__all__ = [
    "EVENT_ELIMINATION",
    "EVENT_HIT",
    "EVENT_POWER_ACTIVATE",
    "LIMITER_RADIUS_SECONDS",
    "MASTER_MAKEUP_MAX_DB",
    "MAX_PAN",
    "PEAK_CEILING",
    "PEAK_CEILING_DBFS",
    "PHYSICS_HZ",
    "SAMPLES_PER_FRAME",
    "SAMPLES_PER_TICK",
    "SOUNDTRACK_VERSION",
    "VIDEO_FPS",
    "MasterReport",
    "ScheduledCue",
    "Soundtrack",
    "SoundtrackError",
    "SoundtrackPlan",
    "audio_metadata",
    "build_soundtrack",
    "cue_for_event",
    "cue_seed",
    "frame_to_sample",
    "master",
    "pan_for_x",
    "pan_gains",
    "plan_soundtrack",
    "samples_per_frame",
    "samples_per_tick",
    "tick_to_sample",
    "total_samples",
]

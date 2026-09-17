"""Tactile race audio: what the machine sounds like from close up.

`audio.marble` is the sloped race's voice and it still is - nothing in this
module touches it, so every edition up to and including V32.1 rebuilds byte for
byte. This is a *second* voice for the same replays, written for one complaint:
the V32 mix has a continuous broadband texture running under all 1150 frames,
and over nineteen seconds that becomes the thing you hear rather than the thing
you watch.

## What was actually wrong, measured

Two layers in `audio.marble.build_race_audio` are always on:

* the **rolling bed** - noise through a speed-tracking one-pole low-pass,
  levelled to -30 dBFS RMS, which is the loudest continuous voice in the film;
* the **rattle grain** - noise band-limited to 1.7-8.2 kHz, levelled to
  -36 dBFS RMS and multiplied by `presentation.contact_energy ** 1.2`.

The grain is the fatiguing one and the reason is arithmetic, not taste. Its
control signal's per-second mean never leaves 0.355-0.518 across the whole race:
a total travel of 3.3 dB. It is nominally contact-driven and effectively a
constant. Worse, it is *anti-correlated* with the rolling bed's own drive
(r = -0.23): the grain is loudest at 3-5 s where the field is slowest and
quietest at 15-17 s where it is fastest, so the two layers fill each other's
gaps and the sum is flatter than either. Measured on the delivered Short, the
5-10 kHz band moves 4.7 dB from end to end and the 2-5 kHz band 8.2 dB, and
22.6% of the mix's total power lives above 2 kHz - essentially all of it those
two layers, because the impacts and crossings put 84-92% of their energy in
300-800 Hz and the music bed has none at all above 800 Hz.

So: everything above 2 kHz in the V32 Short is the rolling pair, and it never
stops. That is the sound the brief is describing.

## What replaces it

The information the grain was carrying is real - the field *is* rattling - so it
is not deleted, it is **re-voiced as discrete events**. The same residual stream
that drove the noise gain now fires `rail_tick`s: 5-9 ms band-limited transients,
thresholded, debounced per marble and rationed per window. A hundred ticks a
second of noise becomes forty ticks a second of *tick*, and the difference is
duty cycle - which `audio.loudness.duty_cycle` reports, and which is the number
this whole pass turns on.

The rolling layer stays, because a marble machine without rolling is a slideshow
of clicks, but it is rebuilt three ways:

* **pitched, not broadband.** Two modulated state-variable band-passes instead of
  a low-passed hiss, so it reads as a marble in a channel rather than as noise.
  Almost nothing of it survives above 4 kHz;
* **gated.** A soft knee under the drive signal, so slow and distant stretches go
  to real silence rather than to a quiet hiss;
* **camera-aware.** Level and brightness follow how large the nearest racers
  actually are in the frame, so when the lens pulls back the sound pulls back.

Everything else is new voice work on events the V32 mix never used at all: the
replay's own 116 marble-to-marble `collision` records, and its 32
`mechanism_hit`s across the five machines this course has.

## Nothing here invents an event

Every cue is placed on a recorded thing - a collision, a mechanism hit, a
residual above a floor, a line choice, a crossing. The only free parameters are
levels, and the only thing the camera is allowed to do is change how loud a real
event is, never whether it happened.
"""

from __future__ import annotations

import math
from array import array
from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Sequence

import numpy as np

from audio.synthesis import (
    Noise,
    SAMPLE_RATE,
    add_into,
    db_to_gain,
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
    "ASMR_VERSION",
    "MixProfile",
    "PROFILES",
    "RaceMix",
    "Telemetry",
    "build_asmr_audio",
    "telemetry",
]

#: Changes when the same replay and profile would produce different audio.
ASMR_VERSION = 1

VIDEO_FPS = 60
SAMPLES_PER_FRAME = SAMPLE_RATE // VIDEO_FPS

#: Delivery ceilings, carried over from `audio.marble` for the same reason: AAC
#: does not return the waveform it was given, so the PCM master reserves a little
#: under the figure the MP4 has to meet.
DELIVERY_PEAK_DBTP = -1.0
CODEC_OVERSHOOT_DB = 0.3
MASTER_CEILING_DBFS = DELIVERY_PEAK_DBTP - CODEC_OVERSHOOT_DB
LIMITER_RADIUS_SECONDS = 0.024

#: How far a cue may be pushed off centre. Restrained, and checked by
#: `audio.loudness.mono_compatibility`: everything here is amplitude panning, so
#: a fold-down loses level evenly and never cancels.
MAX_PAN = 0.42


# --- profiles ---------------------------------------------------------------


@dataclass(frozen=True)
class MixProfile:
    """One audio direction, as the numbers that make it.

    Two exist. They share every voice, every event list and every placement -
    what differs is the balance between the physical layer and the music, and how
    much dynamic range the master is allowed to spend.
    """

    name: str
    title: str
    #: **Two kinds of number live here and mixing them up costs a mix.** The three
    #: continuous layers - `roll`, `room` and `music` - are levelled by *RMS*,
    #: because what a bed contributes is its average and its peak is an accident
    #: of what happened to line up. Every discrete cue below them is levelled by
    #: *peak*, because what a transient contributes is its height.
    #:
    #: The first version of this table treated `music` as a peak budget and then
    #: divided by the score's RMS, which is an RMS target wearing a peak's label.
    #: At -18 it put the music bus at -19.6 dBFS RMS and **+1.9 dBFS peak**, and
    #: the bus compressor then pulled 8.4 dB out of the whole film to hide it.
    #: Both kinds are now named in the comments beside them.
    roll: float                    # RMS dBFS
    tick: float                    # peak dBFS at full strength
    click: float                   # peak dBFS at full strength
    contact: float                 # peak dBFS at zero strength
    contact_loud: float            # peak dBFS at full strength
    mechanism: float               # peak dBFS, before MECHANISM_TRIM
    finish: float                  # peak dBFS
    finish_winner: float           # peak dBFS
    points: float                  # peak dBFS
    music: float                   # RMS dBFS
    room: float                    # RMS dBFS
    #: The gate under the rolling layer: drive below `roll_gate` is silence,
    #: and the knee reaches full level at `roll_knee`.
    roll_gate: float = 0.16
    roll_knee: float = 0.52
    roll_response: float = 1.9
    #: How much of the rolling level the camera owns, 0 = none, 1 = all.
    proximity_depth: float = 0.75
    #: Music ducking at physical events: depth in dB and recovery in seconds.
    duck_db: float = 3.0
    duck_release: float = 0.26
    #: The space opened *before* the biggest events - Part G.
    space_db: float = 4.0
    space_lead: float = 0.20
    #: **Compression is on the music bus, not the master.** A music bed built
    #: from struck oscillators arrives with a crest factor around 19 dB, which is
    #: fine for a bed and ruinous for a master: at Mix B's level it, and not any
    #: physical event, set the peak of the whole film, and a master compressor
    #: brought in to catch it took 2.3 dB off every marble in the race to do it.
    #: Compressing the bed alone fixes the peak where it is made and leaves Part
    #: T's transients literally untouched - the physical bus never sees a
    #: detector.
    #: The threshold is relative to the score, which `music_score` normalises to
    #: a peak of 1.0 - so -9 dB means "the top nine decibels", not "the body".
    #: Set at -19 to begin with, which is under the score's own RMS and had the
    #: compressor pulling 7.6 dB continuously: a bed flattened rather than a peak
    #: caught, and Mix B's loudness range fell to 2.6 LU because of it.
    music_compress_threshold: float = -9.0
    music_compress_ratio: float = 3.0
    #: Master bus compression. A ratio of 1.0 disables the stage entirely, and
    #: both shipped profiles disable it.
    compress_threshold: float = -12.0
    compress_ratio: float = 1.0
    #: Delivery target. -14.5 rather than -14.0, and the half decibel is bought
    #: rather than given away: at -14.0 the static trim is 0.5 dB larger, which
    #: pushed the winner's arrival far enough over the ceiling that the limiter
    #: took 3.7 dB out of the loudest moment in the film. The brief asks for
    #: "approximately -14 LUFS" and says in as many words not to chase an exact
    #: figure at the expense of dynamics; this is that trade, made explicitly.
    target_lufs: float = -14.5

    @property
    def compressed(self) -> bool:
        return self.compress_ratio > 1.0001

    @property
    def music_compressed(self) -> bool:
        return self.music_compress_ratio > 1.0001


#: **Mix A - ASMR forward.** The physical layer is the subject: the music sits
#: 7 dB lower than in B, the rolling gate is deeper so the quiet stretches are
#: quieter, and the bus compressor is off entirely. This is the mix to judge the
#: marbles by.
MIX_A = MixProfile(
    name="A",
    title="ASMR forward",
    roll=-26.5,
    tick=-20.75,
    click=-14.0,
    contact=-28.0,
    contact_loud=-14.5,
    mechanism=-13.5,
    finish=-14.5,
    finish_winner=-8.5,
    points=-27.0,
    music=-32.0,
    room=-44.0,
    roll_gate=0.20,
    roll_knee=0.56,
    roll_response=2.1,
    proximity_depth=0.80,
    duck_db=2.0,
    duck_release=0.22,
    space_db=5.0,
    music_compress_threshold=-10.0,
    music_compress_ratio=2.2,
    compress_ratio=1.0,
    target_lufs=-14.5,
)

#: **Mix B - balanced engagement.** The same physical layer, still clearly on
#: top of the music, but the music is present enough to carry a Short: 7 dB up,
#: a stronger final-sprint build, deeper event ducking so the transients still
#: come forward, and a gentle 1.8:1 bus compressor to hold the whole thing
#: together without flattening it.
MIX_B = MixProfile(
    name="B",
    title="balanced engagement",
    roll=-29.5,
    tick=-22.5,
    click=-15.5,
    contact=-29.5,
    contact_loud=-15.5,
    mechanism=-13.0,
    finish=-13.5,
    finish_winner=-9.6,
    points=-28.5,
    music=-27.0,
    room=-45.0,
    roll_gate=0.17,
    roll_knee=0.52,
    roll_response=1.8,
    proximity_depth=0.70,
    duck_db=7.0,
    duck_release=0.30,
    space_db=4.0,
    music_compress_threshold=-9.0,
    music_compress_ratio=3.0,
    compress_ratio=1.0,
    target_lufs=-14.5,
)

PROFILES: dict[str, MixProfile] = {"A": MIX_A, "B": MIX_B}


# --- telemetry ---------------------------------------------------------------


@dataclass(frozen=True)
class Telemetry:
    """Per output frame, everything the mix is allowed to modulate with.

    One row per rendered frame, so a control signal read off this is on the same
    grid as the pictures and cannot drift against them.

    `pack_speed` is deliberately not the whole field's mean. A marble that has
    already finished and is rolling round the run-out is not what the camera is
    looking at, and neither is one forty units behind; both are in
    `presentation.rolling`'s mean and both make the bed louder for nothing. Here
    each running marble is weighted by how large it is in the frame, so the bed
    follows the racers the shot is actually about.
    """

    seconds: tuple[float, ...]
    pack_speed: tuple[float, ...]      # wu/s, frame-weighted
    top_speed: tuple[float, ...]       # wu/s, fastest running marble
    proximity: tuple[float, ...]       # 0..1, apparent size of the nearest racer
    on_screen: tuple[int, ...]         # running marbles inside the frustum
    pan: tuple[float, ...]             # -1..1, where the pack sits on the frame
    running: tuple[int, ...]

    def __len__(self) -> int:
        return len(self.seconds)

    def as_dict(self) -> dict[str, Any]:
        return {
            "frames": len(self.seconds),
            "pack_speed": {
                "min": round(min(self.pack_speed), 4),
                "max": round(max(self.pack_speed), 4),
                "mean": round(sum(self.pack_speed) / len(self.pack_speed), 4),
            },
            "proximity": {
                "min": round(min(self.proximity), 4),
                "max": round(max(self.proximity), 4),
                "mean": round(sum(self.proximity) / len(self.proximity), 4),
            },
            "on_screen": {
                "min": min(self.on_screen),
                "max": max(self.on_screen),
                "mean": round(sum(self.on_screen) / len(self.on_screen), 3),
            },
        }


def _camera_series(track: dict[str, Any], clock, frames: int
                   ) -> list[tuple[tuple[float, float, float],
                                   tuple[float, float, float], float]]:
    """The camera pose at every output frame, picked the way the renderer picks it."""
    from sloped.presentation import _camera_at

    out = []
    for index in range(frames):
        when = clock.replay_at(index / float(clock.fps)) if hasattr(clock, "replay_at") \
            else index / float(clock.fps)
        out.append(_camera_at(track, when))
    return out


def telemetry(replay: dict[str, Any], track: dict[str, Any], clock) -> Telemetry:
    """Read the replay and the camera track onto the film's own frame grid.

    The camera is where the proximity comes from, and proximity is measured the
    way a lens measures it: a marble's apparent radius is its world radius over
    its distance from the camera, divided by the tangent of the half field of
    view. That is the fraction of the frame height it covers, which is the same
    thing an audience means by "close".
    """
    from sloped.presentation import WIDTH, HEIGHT, project

    scale_to_render = float(replay.get("units", {}).get("render_scale", 0.57))
    radius = float(replay.get("units", {}).get("layout_marble_radius", 0.285))
    frames = int(clock.frames)

    rows: dict[int, list[tuple[float, tuple[float, float, float]]]] = {}
    order: list[tuple[int, list]] = []
    per_frame: list[list[tuple[float, tuple[float, float, float]]]] = [[] for _ in range(frames)]
    for frame in replay["frames"]:
        output = clock.at(float(frame["t"]))
        if output is None:
            continue
        index = int(round(output * clock.fps))
        if not 0 <= index < frames:
            continue
        for sample in frame["marbles"]:
            if sample.get("s") != "running":
                continue
            speed = math.sqrt(sum(float(v) ** 2 for v in sample["v"]))
            point = tuple(float(v) * scale_to_render for v in sample["p"])
            per_frame[index].append((speed, point))

    cameras = _camera_series(track, clock, frames)

    seconds: list[float] = []
    pack: list[float] = []
    top: list[float] = []
    near: list[float] = []
    seen: list[int] = []
    pans: list[float] = []
    running: list[int] = []
    half = math.tan(math.radians(cameras[0][2] * 0.5)) if cameras else 1.0

    for index in range(frames):
        camera, aim, fov = cameras[index]
        half = math.tan(math.radians(fov * 0.5)) or 1e-6
        marbles = per_frame[index]
        seconds.append(index / float(clock.fps))
        running.append(len(marbles))
        if not marbles:
            pack.append(0.0)
            top.append(0.0)
            near.append(0.0)
            seen.append(0)
            pans.append(0.0)
            continue

        weights: list[float] = []
        sizes: list[float] = []
        onscreen = 0
        offsets: list[tuple[float, float]] = []
        for speed, point in marbles:
            distance = math.dist(camera, point) or 1e-6
            # Fraction of the frame height the marble covers.
            size = (radius / distance) / half
            sizes.append(size)
            placed = project(camera, aim, fov, point)
            if placed is not None and 0.0 <= placed[0] <= WIDTH and 0.0 <= placed[1] <= HEIGHT:
                onscreen += 1
                offsets.append(((placed[0] / WIDTH) * 2.0 - 1.0, size))
            # A marble on screen counts fully; one out of frame counts a quarter,
            # because it is still in the room and still making noise.
            weights.append(size * (1.0 if placed is not None else 0.25))

        total = sum(weights) or 1e-9
        pack.append(sum(w * s for w, (s, _) in zip(weights, marbles)) / total)
        top.append(max(speed for speed, _ in marbles))
        near.append(max(sizes))
        seen.append(onscreen)
        if offsets:
            weight = sum(size for _, size in offsets) or 1e-9
            pans.append(sum(x * size for x, size in offsets) / weight)
        else:
            pans.append(0.0)

    # Proximity is normalised against this film's own largest apparent marble, so
    # it is "close for this shot" rather than an absolute distance that would
    # mean something different on every course.
    largest = max(near) or 1.0
    return Telemetry(
        seconds=tuple(seconds),
        pack_speed=tuple(pack),
        top_speed=tuple(top),
        proximity=tuple(min(1.0, value / largest) for value in near),
        on_screen=tuple(seen),
        pan=tuple(max(-1.0, min(1.0, value)) for value in pans),
        running=tuple(running),
    )


# --- events ------------------------------------------------------------------


@dataclass(frozen=True)
class Cue:
    """One thing that happened, once, at one output second."""

    kind: str
    at: float
    strength: float          # 0..1
    pan: float = 0.0
    detail: dict[str, Any] = field(default_factory=dict)


def _ration(cues: Sequence[Cue], *, per_second_cap: int, window: float,
            key=lambda cue: cue.at) -> list[Cue]:
    """At most `per_second_cap` cues in any span of `window` seconds, strongest kept.

    The machine-gun guard. It is a cap on *simultaneity*, not on the event list:
    what it drops is the fourth-loudest of four things that happened inside forty
    milliseconds, which a listener would not have resolved as four things anyway.

    **The obvious implementation does not keep this promise.** Counting only the
    cues already kept within a candidate's own window leaves the invariant open
    to being broken from the other side: a cue admitted later, whose own
    neighbourhood was under the cap when it was considered, can push an earlier
    cue's neighbourhood over it. On this race that produced runs of four ticks
    inside a 75 ms window under a cap of three. So the check here is on the
    *trial* list: a candidate is admitted only if no window of `window` seconds
    containing it would then hold more than the cap.
    """
    from bisect import bisect_left, bisect_right, insort

    kept: list[Cue] = []
    times: list[float] = []
    for cue in sorted(cues, key=lambda c: (-c.strength, key(c))):
        when = key(cue)
        index = bisect_left(times, when)
        trial = times[:index] + [when] + times[index:]
        low = bisect_left(trial, when - window)
        high = bisect_right(trial, when + window) - 1
        crowded = False
        for start in range(low, index + 1):
            end = start
            while end + 1 <= high and trial[end + 1] - trial[start] < window:
                end += 1
            if end - start + 1 > per_second_cap:
                crowded = True
                break
        if crowded:
            continue
        kept.append(cue)
        insort(times, when)
    return sorted(kept, key=key)


def _debounce(cues: Sequence[Cue], *, gap: float, group=lambda cue: 0) -> list[Cue]:
    """One cue per group per `gap` seconds, keeping the strongest in each run."""
    best: dict[Any, Cue] = {}
    out: list[Cue] = []
    for cue in sorted(cues, key=lambda c: c.at):
        key = group(cue)
        previous = best.get(key)
        if previous is not None and cue.at - previous.at < gap:
            if cue.strength > previous.strength:
                out[out.index(previous)] = cue
                best[key] = cue
            continue
        out.append(cue)
        best[key] = cue
    return sorted(out, key=lambda c: c.at)


def _pan_at(telemetry_rows: Telemetry, at: float, depth: float = MAX_PAN) -> float:
    fps = len(telemetry_rows) / (telemetry_rows.seconds[-1] + 1e-9) if len(telemetry_rows) > 1 else 60.0
    index = int(round(at * VIDEO_FPS))
    index = min(max(index, 0), len(telemetry_rows) - 1)
    return telemetry_rows.pan[index] * depth


#: The floor a marble-to-marble collision has to clear to be worth a click, in
#: wu/s of closing speed. The replay records 116 collisions between 2.1 and 42.4;
#: this keeps the top ~70% and drops the taps a listener would not separate from
#: the rolling layer anyway.
CLICK_FLOOR = 3.4
CLICK_CEILING = 34.0
CLICK_GAP = 0.075
CLICK_WINDOW = 0.045
CLICK_POLYPHONY = 2

#: Rail ticks, and the numbers here were chosen twice.
#:
#: The first attempt put the floor at 5.6 wu/s - just over the residual median -
#: with one tick per marble per 52 ms and two anywhere per 40 ms. It produced 466
#: ticks whose per-second count ran 19, 28, 25, 21, 25, 27, 29, 26, 30, ... all
#: the way to the finish: **a new continuous texture**, which is the one thing
#: Part A forbids. The reason is worth writing down. Eight marbles debounced at
#: 52 ms can supply 154 ticks a second and the raw residual had 2032 candidates
#: over that floor, so the *ration* was the binding constraint in every second of
#: the film - and a density set by a cap is by definition a constant. The physics
#: was never allowed to decide.
#:
#: So the floor is made the binding constraint instead. At 9.0 wu/s - between the
#: 90th and 95th percentile of the residual, and just under
#: `presentation.impacts`'s floor of 11.0 so the two bands meet without a gap -
#: the candidate count per second runs 19, 64, 72, 18, 10, 17, 29, ... : a
#: sevenfold swing that is the race's own, with the slow stretch at 3-5 s
#: genuinely sparse. The ration is then set loose enough to catch only true
#: simultaneity.
TICK_FLOOR = 9.0
TICK_CEILING = 11.0
TICK_GAP = 0.085
TICK_WINDOW = 0.075
TICK_POLYPHONY = 3

#: Track contacts. `presentation.impacts` already rations these; the floor here
#: is its floor.
CONTACT_SOFT = 11.0
CONTACT_HARD = 42.0


def marble_clicks(replay: dict[str, Any], clock, rows: Telemetry) -> list[Cue]:
    """Marble on marble, from the replay's own `collision` records.

    **The V32 mix never used these.** They are the one contact type a marble
    machine has that nothing else sounds like - two hard spheres, very short, very
    bright, no body behind them - and the replay has been recording them with a
    closing speed and a world position the whole time.
    """
    out: list[Cue] = []
    for event in replay.get("events", ()):
        if event.get("kind") != "collision":
            continue
        speed = float(event.get("speed", 0.0))
        if speed < CLICK_FLOOR:
            continue
        when = clock.at(float(event["t"]))
        if when is None:
            continue
        strength = min(1.0, (speed - CLICK_FLOOR) / (CLICK_CEILING - CLICK_FLOOR))
        out.append(Cue(
            kind="click",
            at=when,
            strength=strength,
            pan=_pan_at(rows, when),
            detail={"a": int(event.get("a", -1)), "b": int(event.get("b", -1)),
                    "speed": round(speed, 4), "replay": float(event["t"])},
        ))
    out = _debounce(out, gap=CLICK_GAP,
                    group=lambda cue: tuple(sorted((cue.detail["a"], cue.detail["b"]))))
    return _ration(out, per_second_cap=CLICK_POLYPHONY, window=CLICK_WINDOW)


def rail_ticks(replay: dict[str, Any], clock, rows: Telemetry) -> list[Cue]:
    """The rattle, as events.

    This is the layer that replaces the grain. `presentation.residuals` is the
    raw per-frame contact impulse; `presentation.impacts` takes the top one per
    cent of it and the old mix smeared the rest into a noise gain. Here the band
    between `TICK_FLOOR` and the impact floor becomes small discrete ticks, one
    per marble per 52 ms at most and two anywhere per 40 ms, which is a texture
    made of transients instead of a transient-free texture.
    """
    from sloped import presentation as pres

    out: list[Cue] = []
    for event in pres.residuals(replay, clock):
        if not TICK_FLOOR <= event.magnitude < TICK_CEILING:
            continue
        strength = (event.magnitude - TICK_FLOOR) / (TICK_CEILING - TICK_FLOOR)
        out.append(Cue(
            kind="tick",
            at=event.at,
            strength=min(1.0, max(0.0, strength)),
            pan=_pan_at(rows, event.at, MAX_PAN * 0.8),
            detail={"marble": event.marble, "module": event.module,
                    "magnitude": round(event.magnitude, 4)},
        ))
    out = _debounce(out, gap=TICK_GAP, group=lambda cue: cue.detail["marble"])
    return _ration(out, per_second_cap=TICK_POLYPHONY, window=TICK_WINDOW)


def track_contacts(replay: dict[str, Any], track: dict[str, Any], clock) -> list[Cue]:
    """Marble on track: `presentation.impacts`, re-voiced rather than re-derived."""
    from sloped import presentation as pres

    hits = pres.impacts(replay, clock)
    pans = pres.screen_pan(replay, track, hits, max_pan=MAX_PAN)
    out: list[Cue] = []
    for event, pan in zip(hits, pans):
        strength = min(1.0, max(0.0, (event.magnitude - CONTACT_SOFT)
                                / (CONTACT_HARD - CONTACT_SOFT)))
        out.append(Cue(
            kind="contact",
            at=event.at,
            strength=strength,
            pan=pan,
            detail={"marble": event.marble, "module": event.module,
                    "magnitude": round(event.magnitude, 4)},
        ))
    return out


#: The five machines this course has, and the window each one owns. Taken from
#: the replay rather than written down: `drum` is 2.23-4.70, `sweep` 6.28-7.60,
#: `pair` 9.02-10.95 and `last` 12.68-13.47, so each mechanism is also a *section*
#: of the race and can be given an identity without any two of them overlapping.
MECHANISM_GAP = {"studs": 0.12, "drum": 0.16, "sweep": 0.18, "pair": 0.14, "last": 0.20}


def mechanism_hits(replay: dict[str, Any], track: dict[str, Any], clock,
                   rows: Telemetry) -> list[Cue]:
    """Every `mechanism_hit`, grouped by the machine that made it."""
    out: list[Cue] = []
    for event in replay.get("events", ()):
        if event.get("kind") != "mechanism_hit":
            continue
        when = clock.at(float(event["t"]))
        if when is None:
            continue
        module = str(event.get("module") or "")
        out.append(Cue(
            kind="mechanism",
            at=when,
            strength=1.0,
            pan=_pan_at(rows, when, MAX_PAN * 0.7),
            detail={"module": module, "marble": int(event.get("id", -1)),
                    "rank": event.get("rank"), "replay": float(event["t"])},
        ))
    return _debounce(
        out,
        gap=0.12,
        group=lambda cue: cue.detail["module"],
    )


def points_switches(replay: dict[str, Any], clock, rows: Telemetry) -> list[Cue]:
    """The `line_choice` records: this course is a switchyard, and those are its points.

    Very quiet - a single small metallic tick. It is included because the event is
    real and it lands on the five moments the field picks a line, which is
    information; it is quiet because nothing on screen is *made* of it.
    """
    out: list[Cue] = []
    for event in replay.get("events", ()):
        if event.get("kind") != "line_choice":
            continue
        when = clock.at(float(event["t"]))
        if when is None:
            continue
        spread = float(event.get("spread", 0.0))
        out.append(Cue(
            kind="points",
            at=when,
            strength=min(1.0, spread / 0.6),
            pan=_pan_at(rows, when, MAX_PAN * 0.5),
            detail={"pan": event.get("pan"), "spread": spread},
        ))
    return out


def crossings(replay: dict[str, Any], clock) -> list[Cue]:
    """The eight arrivals, the winner's marked as such."""
    rows = sorted(
        (float(e["t"]), int(e["id"]), int(e["order"]))
        for e in replay.get("events", ()) if e["kind"] == "finish_line"
    )
    out: list[Cue] = []
    for when, marble, order in rows:
        at = clock.at(when)
        if at is None:
            continue
        out.append(Cue(
            kind="finish",
            at=at,
            strength=1.0 if order == 1 else 0.55,
            pan=0.0,
            detail={"marble": marble, "order": order, "replay": when},
        ))
    return out


# --- voices ------------------------------------------------------------------


def rail_tick(strength: float, seed: int, *, sample_rate: int = SAMPLE_RATE) -> array:
    """A marble ticking over a rail joint: 5-9 ms, bright, and gone.

    Deliberately band-limited at the top. The complaint this pass exists to fix
    is high-frequency fatigue, and a tick whose energy runs to 12 kHz is a tick
    that stings on a phone. The pass-band here tops out at 6.5 kHz and the body
    under it is a single short partial, which is enough to read as *small and
    hard* without any of the sizzle.
    """
    force = min(1.0, max(0.0, strength))
    length = seconds_to_samples(0.005 + 0.004 * force, sample_rate)
    out = noise_burst(
        length,
        seed=seed,
        attack=0.00025,
        decay=0.0011 + 0.0010 * force,
        highpass=2200.0 + 900.0 * force,
        lowpass=6500.0,
        stages=2,
        sample_rate=sample_rate,
    )
    body = tone(
        length,
        freq=2400.0 + 700.0 * force,
        freq_end=2100.0 + 600.0 * force,
        attack=0.0003,
        decay=0.0026,
        sample_rate=sample_rate,
    )
    add_into(out, body, 0, 0.35)
    largest = peak(out)
    if largest > 0.0:
        scale(out, 1.0 / largest)
    return out


def marble_click(strength: float, seed: int, *, sample_rate: int = SAMPLE_RATE) -> array:
    """Two acrylic spheres meeting: a very short, glassy, two-partial click.

    What separates this from a track contact is that there is no cavity behind
    it. A marble hitting a channel excites the channel; a marble hitting a marble
    excites only the two marbles, which are small, stiff and heavily damped - so
    the partials are high, inharmonic and dead inside forty milliseconds. Harder
    contacts get brighter and *shorter*, not longer.
    """
    force = min(1.0, max(0.0, strength))
    length = seconds_to_samples(0.020 + 0.026 * (1.0 - force * 0.45), sample_rate)
    out = silence(length)

    transient = noise_burst(
        min(length, seconds_to_samples(0.0045, sample_rate)),
        seed=seed,
        attack=0.00018,
        decay=0.00075 + 0.00060 * force,
        highpass=2600.0 + 1800.0 * force,
        lowpass=9000.0,
        stages=2,
        sample_rate=sample_rate,
    )
    add_into(out, transient, 0, 0.30 + 0.26 * force)

    # Two partials at an inharmonic ratio: a sphere's first two modes are not an
    # octave apart, and using one makes it sound like a bell instead of a bead.
    first = 1650.0 + 620.0 * force
    for index, (ratio, gain, decay) in enumerate((
            (1.0, 0.72, 0.0085 + 0.0055 * (1.0 - force)),
            (1.593, 0.34, 0.0052 + 0.0032 * (1.0 - force)),
            (2.136, 0.13, 0.0030))):
        add_into(out, tone(
            length,
            freq=first * ratio,
            freq_end=first * ratio * 0.985,
            attack=0.00025,
            decay=decay,
            sample_rate=sample_rate,
        ), 0, gain)

    high_pass(out, 700.0, sample_rate=sample_rate, stages=1)
    largest = peak(out)
    if largest > 0.0:
        scale(out, 1.0 / largest)
    return out


#: The body resonance of each part of this course, in hertz. A switchyard's
#: corridors are long open channels and its pans are wide shallow plates, so the
#: pans ring lower and longer than the corridors do.
BODY_HZ: dict[str, float] = {
    "start": 640.0,
    "head": 520.0,
    "pan1": 372.0,
    "pan2": 362.0,
    "pan3": 352.0,
    "pan4": 344.0,
    "pan5": 336.0,
    "corr1": 452.0,
    "corr2": 442.0,
    "corr3": 434.0,
    "corr4": 426.0,
    "sprint": 408.0,
    "runout": 296.0,
}
BODY_DEFAULT = 430.0


def track_contact(strength: float, body_hz: float, seed: int, *,
                  sample_rate: int = SAMPLE_RATE) -> array:
    """A marble landing on the track: a small click over a channel resonance.

    The shape `audio.marble.impact_cue` established is right and is kept - click,
    body, ring, all three moving with force. Two things change, and both of them
    are the fatigue brief:

    * the click's pass-band starts at 1.2 kHz and stops at 7 kHz rather than
      running to 11 kHz, and its share of the cue is smaller at every force;
    * the ring partial sits at 2.44x rather than 2.71x and 6 dB lower, which
      keeps the 2-5 kHz band from being restated two hundred and thirty-nine
      times in nineteen seconds.

    What is left is more body and less spit, which is also simply closer to what
    a 20 mm acrylic marble in a pearl channel sounds like.
    """
    force = min(1.0, max(0.0, strength))
    length = seconds_to_samples(0.050 + 0.080 * force, sample_rate)
    out = silence(length)

    click = noise_burst(
        min(length, seconds_to_samples(0.008 + 0.005 * force, sample_rate)),
        seed=seed,
        attack=0.00035,
        decay=0.0020 + 0.0018 * force,
        highpass=1200.0 + 1500.0 * force,
        lowpass=7000.0,
        stages=2,
        sample_rate=sample_rate,
    )
    add_into(out, click, 0, 0.30 + 0.34 * force)

    pitch = body_hz * (1.0 + 0.14 * force)
    add_into(out, tone(
        length, freq=pitch, freq_end=pitch * 0.951,
        attack=0.0008, decay=0.022 + 0.034 * force, sample_rate=sample_rate,
    ), 0, 0.66)
    add_into(out, tone(
        length, freq=pitch * 2.44, freq_end=pitch * 2.39,
        attack=0.0007, decay=0.011 + 0.018 * force, sample_rate=sample_rate,
    ), 0, 0.15 + 0.13 * force)

    largest = peak(out)
    if largest > 0.0:
        scale(out, 1.0 / largest)
    return out


def points_tick(strength: float, seed: int, *, sample_rate: int = SAMPLE_RATE) -> array:
    """The points changing: one small sprung metallic tick, and a tiny tail."""
    force = min(1.0, max(0.0, strength))
    length = seconds_to_samples(0.038, sample_rate)
    out = noise_burst(
        seconds_to_samples(0.0035, sample_rate),
        seed=seed, attack=0.0002, decay=0.0010,
        highpass=3000.0, lowpass=8000.0, stages=2, sample_rate=sample_rate,
    )
    out.extend([0.0] * max(0, length - len(out)))
    for ratio, gain, decay in ((1.0, 0.55, 0.006), (2.77, 0.22, 0.0035)):
        add_into(out, tone(length, freq=1980.0 * ratio, attack=0.0003,
                           decay=decay, sample_rate=sample_rate), 0, gain * (0.7 + 0.3 * force))
    largest = peak(out)
    if largest > 0.0:
        scale(out, 1.0 / largest)
    return out


# --- the five machines -------------------------------------------------------
#
# Each of these is a different *mechanism*, not a different EQ of the same knock.
# The brief asks for distinct identities and the way to get them is to make the
# machines behave differently in time: the studs are a run of taps, the drum is a
# padded knock with a shell behind it, the sweep is a move and then an arrival,
# the pair is two knocks so close they read as one object, and the last wheel is
# the only one with any weight under it.


def studs_voice(seed: int, *, sample_rate: int = SAMPLE_RATE) -> array:
    """A stud field: four small taps 17 ms apart, each a little quieter."""
    length = seconds_to_samples(0.11, sample_rate)
    out = silence(length)
    for index in range(4):
        tap = noise_burst(
            seconds_to_samples(0.007, sample_rate),
            seed=seed ^ (index * 0x9E37), attack=0.0002, decay=0.0016,
            highpass=1500.0, lowpass=6200.0, stages=2, sample_rate=sample_rate,
        )
        add_into(tap, tone(seconds_to_samples(0.020, sample_rate), freq=880.0 - 44.0 * index,
                           attack=0.0004, decay=0.007, sample_rate=sample_rate), 0, 0.6)
        add_into(out, tap, seconds_to_samples(0.017 * index, sample_rate),
                 0.95 ** (index * 2.2))
    largest = peak(out)
    if largest > 0.0:
        scale(out, 1.0 / largest)
    return out


def drum_voice(seed: int, *, sample_rate: int = SAMPLE_RATE) -> array:
    """The drum: a padded knock inside a shell that keeps ringing after it.

    Soft attack on purpose - a marble hitting a rotating drum wall is cushioned
    by the wall's give - and a long, low, quiet shell mode behind it, which is
    what makes a drum read as a hollow object rather than as a block of wood.
    """
    length = seconds_to_samples(0.30, sample_rate)
    out = silence(length)
    knock = noise_burst(
        seconds_to_samples(0.012, sample_rate), seed=seed,
        attack=0.0011, decay=0.0042, highpass=420.0, lowpass=3200.0,
        stages=2, sample_rate=sample_rate,
    )
    add_into(out, knock, 0, 0.44)
    add_into(out, tone(seconds_to_samples(0.16, sample_rate), freq=196.0, freq_end=182.0,
                       attack=0.0022, decay=0.042, sample_rate=sample_rate), 0, 0.80)
    add_into(out, tone(length, freq=311.0, freq_end=305.0,
                       attack=0.0035, decay=0.085, sample_rate=sample_rate),
             seconds_to_samples(0.004, sample_rate), 0.30)
    add_into(out, tone(length, freq=742.0, attack=0.004, decay=0.055,
                       sample_rate=sample_rate), seconds_to_samples(0.006, sample_rate), 0.11)
    high_pass(out, 70.0, sample_rate=sample_rate, stages=1)
    largest = peak(out)
    if largest > 0.0:
        scale(out, 1.0 / largest)
    return out


def sweep_voice(seed: int, *, sample_rate: int = SAMPLE_RATE) -> array:
    """The sweep: a short servo move that opens, closes and then arrives.

    The move comes *first* and the contact lands at the end of it, which is the
    only one of the five machines where the sound has an order to it. The whoosh
    is band-passed noise whose centre frequency rises and falls over 130 ms - a
    thing travelling past - and the arrival is a damped knock on its last frame.
    """
    lead = seconds_to_samples(0.130, sample_rate)
    length = lead + seconds_to_samples(0.20, sample_rate)
    out = silence(length)

    air = Noise(seed).fill(lead)
    state_low = 0.0
    state_band = 0.0
    for index in range(lead):
        position = index / max(1, lead - 1)
        centre = 520.0 + 2400.0 * math.sin(math.pi * position)
        f = 2.0 * math.sin(math.pi * centre / sample_rate)
        high = air[index] - state_low - 0.9 * state_band
        state_band += f * high
        state_low += f * state_band
        shape = math.sin(math.pi * position) ** 1.6
        air[index] = state_band * shape
    add_into(out, air, 0, 0.55)

    knock = noise_burst(
        seconds_to_samples(0.010, sample_rate), seed=seed ^ 0x51CE,
        attack=0.0003, decay=0.0026, highpass=900.0, lowpass=5600.0,
        stages=2, sample_rate=sample_rate,
    )
    add_into(out, knock, lead, 0.70)
    add_into(out, tone(seconds_to_samples(0.13, sample_rate), freq=430.0, freq_end=402.0,
                       attack=0.0009, decay=0.030, sample_rate=sample_rate), lead, 0.62)
    largest = peak(out)
    if largest > 0.0:
        scale(out, 1.0 / largest)
    return out


def pair_voice(seed: int, *, sample_rate: int = SAMPLE_RATE) -> array:
    """The pair: two knocks 26 ms apart, which the ear hears as one clack.

    The interval is the identity. Anything under about 30 ms fuses into a single
    percussive object with a characteristic "ck" on the front of it, and that is
    exactly what a two-armed mechanism striking twice sounds like.
    """
    length = seconds_to_samples(0.20, sample_rate)
    out = silence(length)
    for index, (offset, gain) in enumerate(((0.0, 1.0), (0.026, 0.72))):
        at = seconds_to_samples(offset, sample_rate)
        knock = noise_burst(
            seconds_to_samples(0.008, sample_rate), seed=seed ^ (index * 0x2F1B),
            attack=0.00025, decay=0.0022, highpass=1100.0, lowpass=6000.0,
            stages=2, sample_rate=sample_rate,
        )
        add_into(out, knock, at, 0.52 * gain)
        add_into(out, tone(seconds_to_samples(0.09, sample_rate), freq=596.0 - 30.0 * index,
                           freq_end=572.0 - 30.0 * index, attack=0.0006, decay=0.016,
                           sample_rate=sample_rate), at, 0.74 * gain)
        add_into(out, tone(seconds_to_samples(0.05, sample_rate), freq=1455.0,
                           attack=0.0005, decay=0.008, sample_rate=sample_rate), at, 0.16 * gain)
    largest = peak(out)
    if largest > 0.0:
        scale(out, 1.0 / largest)
    return out


def last_voice(seed: int, *, sample_rate: int = SAMPLE_RATE) -> array:
    """The last wheel: the only mechanism with weight under it.

    It gets a low component because it is the final obstacle before the sprint
    and the film's shape wants a punctuation there - but the component is short
    and high-passed at 55 Hz, so it lands rather than booms. Part M is the
    constraint here and it is enforced by the filter, not by taste.
    """
    length = seconds_to_samples(0.38, sample_rate)
    out = silence(length)
    knock = noise_burst(
        seconds_to_samples(0.014, sample_rate), seed=seed,
        attack=0.0004, decay=0.0038, highpass=700.0, lowpass=5200.0,
        stages=2, sample_rate=sample_rate,
    )
    add_into(out, knock, 0, 0.56)
    add_into(out, tone(seconds_to_samples(0.10, sample_rate), freq=132.0, freq_end=104.0,
                       attack=0.0016, decay=0.026, sample_rate=sample_rate), 0, 0.62)
    add_into(out, tone(seconds_to_samples(0.20, sample_rate), freq=286.0, freq_end=272.0,
                       attack=0.0012, decay=0.052, sample_rate=sample_rate), 0, 0.72)
    add_into(out, tone(length, freq=688.0, attack=0.0022, decay=0.080,
                       sample_rate=sample_rate), seconds_to_samples(0.005, sample_rate), 0.18)
    high_pass(out, 55.0, sample_rate=sample_rate, stages=2)
    largest = peak(out)
    if largest > 0.0:
        scale(out, 1.0 / largest)
    return out


MECHANISM_VOICES = {
    "studs": studs_voice,
    "drum": drum_voice,
    "sweep": sweep_voice,
    "pair": pair_voice,
    "last": last_voice,
}
#: Per-machine trim in dB, relative to the profile's mechanism level. The last
#: wheel is the punctuation and the studs are a detail; both are placed here
#: rather than inside the voices so the identities stay comparable.
MECHANISM_TRIM = {"studs": -7.0, "drum": -1.5, "sweep": -1.0, "pair": -1.5, "last": 2.0}


def arrival_cue(winner: bool, seed: int, *, sample_rate: int = SAMPLE_RATE) -> array:
    """Crossing the line: a marble arriving on a deck, and for the winner, a chime.

    Ordinary arrivals are the deck being struck, which is the same physical event
    as any other track contact but on a bigger, lower plate. The winner gets one
    extra thing - a clean two-partial chime a fifth apart, rising - and that is
    the only non-diegetic sound in the whole mix. It is here because a Short has
    to say *this one won* inside a second, and every other lever available (the
    ring, the card) is visual and already spent.
    """
    length = seconds_to_samples(0.70 if winner else 0.26, sample_rate)
    out = silence(length)

    # **A low crest, deliberately.** The cue is peak-budgeted, so how much of the
    # finish a listener actually gets is its energy *under* that peak, not the
    # peak. A hard spike and a long quiet tail is the worst shape available: it
    # spends the whole budget on one sample, and it was why brightening the chime
    # for phone reach made the film's loudest fifty milliseconds move off the
    # crossing and onto the opening. A softer strike over a fuller, longer deck
    # resonance puts more sound under the same ceiling, which is both a stronger
    # finish and less for the limiter to do.
    strike = noise_burst(
        seconds_to_samples(0.014, sample_rate), seed=seed,
        attack=0.0009, decay=0.0042, highpass=800.0, lowpass=6400.0,
        stages=2, sample_rate=sample_rate,
    )
    add_into(out, strike, 0, 0.38 if winner else 0.34)
    add_into(out, tone(seconds_to_samples(0.28, sample_rate), freq=344.0, freq_end=326.0,
                       attack=0.0016, decay=0.068 if winner else 0.044,
                       sample_rate=sample_rate),
             0, 0.72 if winner else 0.60)
    if winner:
        # The deck's own second mode, which is what makes a big plate read as a
        # plate rather than as a drum.
        add_into(out, tone(seconds_to_samples(0.24, sample_rate), freq=516.0,
                           freq_end=502.0, attack=0.0018, decay=0.055,
                           sample_rate=sample_rate), 0, 0.40)
    # The deck's second mode. Without it an arrival is one low tone and disappears
    # on a phone, which is where most of this Short will be watched.
    add_into(out, tone(seconds_to_samples(0.11, sample_rate), freq=1032.0, freq_end=1004.0,
                       attack=0.0007, decay=0.019, sample_rate=sample_rate),
             0, 0.26 if winner else 0.44)
    if not winner:
        add_into(out, tone(seconds_to_samples(0.07, sample_rate), freq=1548.0,
                           attack=0.0006, decay=0.012, sample_rate=sample_rate),
                 0, 0.18)

    if winner:
        # **Weighted for a phone.** A phone speaker has nothing useful under
        # about 500 Hz, and the first version of this cue put its weight in the
        # 344 Hz deck strike: filtered, the loudest moment of the Short stopped
        # being the finish and became the opening second, where the contacts and
        # clicks live in the 2-5 kHz the speaker is best at. The chime carries
        # the arrival instead - four partials from 784 Hz up, all of them inside
        # what a phone reproduces - and the deck is what you feel on headphones.
        for index, (ratio, gain, delay) in enumerate((
                (1.0, 0.82, 0.010), (1.5, 0.70, 0.030), (2.0, 0.50, 0.050),
                (3.0, 0.24, 0.068))):
            add_into(out, tone(
                seconds_to_samples(0.60 - 0.07 * index, sample_rate),
                freq=784.0 * ratio, attack=0.0035, decay=0.150 - 0.012 * index,
                sample_rate=sample_rate,
            ), seconds_to_samples(delay, sample_rate), gain)
    largest = peak(out)
    if largest > 0.0:
        scale(out, 1.0 / largest)
    return out


# --- the rolling layer -------------------------------------------------------


def _ramp(control: Sequence[float], length: int, fps: int = VIDEO_FPS) -> np.ndarray:
    """One control value per frame, interpolated to one per sample."""
    values = np.asarray(control, dtype=np.float64)
    if values.size == 0:
        return np.zeros(length)
    grid = np.arange(length, dtype=np.float64) / (SAMPLE_RATE / float(fps))
    return np.interp(grid, np.arange(values.size, dtype=np.float64), values)


def _gate(drive: np.ndarray, floor: float, knee: float) -> np.ndarray:
    """A soft knee: silence under `floor`, full above `knee`, smooth between.

    The half-cosine in the middle is there so the bed does not chatter when the
    drive hovers on the threshold, which it does every time the field bunches up
    behind a mechanism.
    """
    span = max(1e-6, knee - floor)
    position = np.clip((drive - floor) / span, 0.0, 1.0)
    return 0.5 - 0.5 * np.cos(math.pi * position)


def rolling_layer(
    rows: Telemetry,
    length: int,
    seed: int,
    profile: MixProfile,
    *,
    sample_rate: int = SAMPLE_RATE,
) -> tuple[array, dict[str, float]]:
    """Marbles rolling in a channel: two modulated resonances, gated.

    Not a low-passed hiss. Noise is driven through two state-variable band-passes
    whose centre frequencies ride the pack's speed - a fundamental that runs
    170-560 Hz and a second formant a little over three times it - so the layer is
    *pitched*, rises and falls with the race, and puts almost nothing above
    4 kHz. A band-pass also means the level and the brightness are not the same
    control, which is what let the old bed be loud and dull at the same time.

    The gate is the other half. `profile.roll_gate` is a real floor: below it the
    output is zero, not quiet, and on this film that is 14.6% of the running time.
    """
    drive_raw = np.clip(np.asarray(rows.pack_speed, dtype=np.float64), 0.0, None)
    top = float(np.percentile(drive_raw, 97.0)) or 1.0
    drive_frames = np.clip(drive_raw / top, 0.0, 1.2)
    near_frames = np.asarray(rows.proximity, dtype=np.float64)

    drive = _ramp(drive_frames, length)
    near = _ramp(near_frames, length)

    gate = _gate(drive, profile.roll_gate, profile.roll_knee)
    body = np.power(np.clip(drive, 0.0, 1.0), profile.roll_response)
    proximity = (1.0 - profile.proximity_depth) + profile.proximity_depth * np.power(near, 0.85)
    amplitude = gate * body * proximity

    # Centre frequencies. The fundamental is what a marble rolling in a 20 mm
    # channel excites; the formant is the channel's own second mode.
    #
    # 250-770 Hz rather than the 170-560 this started at, and the reason is both
    # physical and a mix problem. A 20 mm sphere on a hard channel does not ring
    # at 170 Hz - nothing that small does - and at 170 Hz the layer piled into the
    # same 120-300 Hz band as the music's bass, the drum and the arrivals, which
    # measured 53.6% of the whole mix's power in one band. Moving it up puts the
    # rolling layer in its own register and the second formant into 790-2430 Hz,
    # where a phone speaker can actually reproduce it.
    first = 250.0 + 520.0 * np.clip(drive, 0.0, 1.0)
    second = first * 3.15
    resonance = 0.34 - 0.10 * np.clip(drive, 0.0, 1.0)      # 1/Q, so higher drive = tighter

    noise = Noise(seed).fill(length)
    source = np.asarray(noise, dtype=np.float64)

    out = np.empty(length, dtype=np.float64)
    low_a = band_a = low_b = band_b = 0.0
    two_over_sr = math.pi / sample_rate
    sin = math.sin
    for index in range(length):
        value = source[index]
        q = resonance[index]

        f = 2.0 * sin(two_over_sr * first[index])
        high = value - low_a - q * band_a
        band_a += f * high
        low_a += f * band_a

        g = 2.0 * sin(two_over_sr * second[index])
        high_b = value - low_b - (q + 0.22) * band_b
        band_b += g * high_b
        low_b += g * band_b

        out[index] = (band_a + 0.52 * band_b) * amplitude[index]

    # A last low-pass so nothing the resonators let through sits in the fatigue
    # band, and a high-pass so the layer stays out of the music's register.
    buffer = array("d", out)
    low_pass(buffer, 5600.0, sample_rate=sample_rate, stages=2)
    high_pass(buffer, 150.0, sample_rate=sample_rate, stages=1)
    largest = peak(buffer)
    if largest > 0.0:
        scale(buffer, 1.0 / largest)

    silent = float(np.mean(gate <= 1e-9))
    # The span is quoted between the 20th and the 95th percentile rather than the
    # 5th and the 95th: with a real gate the bottom of the distribution is zero,
    # and the logarithm of zero is not a measurement of anything.
    low = float(np.percentile(amplitude, 20.0))
    high = float(np.percentile(amplitude, 95.0))
    return buffer, {
        "gate_silent_fraction": round(silent, 4),
        "drive_p5": round(float(np.percentile(drive_frames, 5.0)), 4),
        "drive_p95": round(float(np.percentile(drive_frames, 95.0)), 4),
        "amplitude_p20": round(low, 6),
        "amplitude_p95": round(high, 6),
        "amplitude_span_db": (
            round(20.0 * math.log10(max(high, 1e-9) / low), 2) if low > 1e-9 else None),
        "below_20db_fraction": round(float(np.mean(amplitude < high * 0.1)), 4),
    }


def room_tone(length: int, seed: int, *, sample_rate: int = SAMPLE_RATE) -> array:
    """The hall, and nothing else: dark, quiet, and under everything.

    `contained_bay_v301` is an enclosed room, so a little of it should be
    audible. Low-passed at 300 Hz and three poles down, so it contributes no
    energy at all to the bands this pass is trying to empty.
    """
    out = Noise(seed).fill(length)
    low_pass(out, 300.0, sample_rate=sample_rate, stages=3)
    high_pass(out, 55.0, sample_rate=sample_rate, stages=1)
    largest = peak(out)
    if largest > 0.0:
        scale(out, 1.0 / largest)
    return out


# --- music -------------------------------------------------------------------
#
# Original, written here, in arithmetic, from the same oscillators as everything
# else. There is no sample, no loop, no library and no third-party asset in it -
# see `docs/validation/race2/v322_audio/music_license.txt`.

#: A minor, natural: i - VI - III - VII with a suspended turn in the build. Roots
#: in hertz from A2, which puts the bass where a phone speaker can still imply it
#: and a laptop can actually play it.
#:
#: The roots are A3 down, not A2. The first version used A2 and measured 60.5% of
#: the music's own power below 120 Hz, which dragged the finished mix to 48%
#: there - five times the V32 figure and squarely against Part M. An octave up
#: puts the bass note in 175-262 Hz, where a laptop can reproduce it and a phone
#: can at least imply it, and leaves the sub-120 region to a single quiet
#: reinforcement on the downbeat.
CHORDS: tuple[tuple[float, tuple[float, ...]], ...] = (
    (220.00, (1.0, 1.2, 1.5)),        # Am
    (174.61, (1.0, 1.25, 1.5)),       # F
    (261.63, (1.0, 1.25, 1.5)),       # C
    (196.00, (1.0, 1.25, 1.5)),       # G
)
BEATS_PER_BAR = 4
BARS_TO_FINISH = 9


def music_tempo(crossing_seconds: float, bars: int = BARS_TO_FINISH) -> float:
    """The BPM that puts the winner's crossing on a downbeat.

    **The race picks the tempo.** The winner crosses at 15.8167 s, and nine bars
    of four beats inside that is 136.57 BPM - which is squarely in the kinetic,
    playful range the brief asks for, so nothing has to be compromised to get the
    alignment. The consequence is worth stating: the musical sections then fall
    at bar 0 (hook), 1-3 (drive), 4-6 (tension), 7-8 (build and sprint) and 9
    (the crossing, on a downbeat, resolving) - which is the brief's own energy
    shape, arrived at from the replay rather than laid over it.
    """
    return bars * BEATS_PER_BAR * 60.0 / max(crossing_seconds, 1e-6)


@dataclass(frozen=True)
class MusicPlan:
    bpm: float
    beat: float
    bar: float
    bars: int
    crossing_bar: int
    crossing: float

    def as_dict(self) -> dict[str, float]:
        return {
            "bpm": round(self.bpm, 3),
            "beat_seconds": round(self.beat, 5),
            "bar_seconds": round(self.bar, 5),
            "bars": self.bars,
            "crossing_bar": self.crossing_bar,
            "crossing_seconds": round(self.crossing, 5),
        }


def music_plan(duration: float, crossing: float) -> MusicPlan:
    bpm = music_tempo(crossing)
    beat = 60.0 / bpm
    bar = beat * BEATS_PER_BAR
    return MusicPlan(bpm=bpm, beat=beat, bar=bar,
                     bars=int(math.ceil(duration / bar)),
                     crossing_bar=BARS_TO_FINISH, crossing=crossing)


#: How far each musical part sits off the beat, in seconds. Five parts struck on
#: the same sample sum coherently; spread over eight milliseconds they do not,
#: and eight milliseconds is a tenth of the gap between two sixteenths at this
#: tempo - a player's own timing error, not a musical one.
_LAYER_OFFSETS = {"hat": 0.0, "figure": 0.0011, "bass": 0.0026,
                  "sub": 0.0052, "body": 0.0073}


def _pluck(length: int, freq: float, *, decay: float, bright: float,
           sample_rate: int = SAMPLE_RATE) -> array:
    """One plucked note: three partials, the upper two shorter than the first."""
    out = silence(length)
    for ratio, gain, scale_decay in ((1.0, 1.0, 1.0), (2.0, 0.30 * bright, 0.55),
                                     (3.0, 0.12 * bright, 0.34)):
        add_into(out, tone(length, freq=freq * ratio, attack=0.0025,
                           decay=decay * scale_decay, sample_rate=sample_rate), 0, gain)
    return out


def music_score(
    length: int,
    seed: int,
    plan: MusicPlan,
    *,
    sprint_from: float,
    sample_rate: int = SAMPLE_RATE,
) -> array:
    """The bed, written against the race's own sections.

    Five parts, each entering where the race gives it a reason to:

    * **pulse** - a soft closed hat on every eighth from bar 0. The thing that
      makes the first second feel like it is already moving;
    * **bass** - the chord root, on the downbeat from bar 0, on every beat from
      bar 4, on every eighth through the sprint;
    * **figure** - a three-note rising motif from bar 1, doubled an octave up
      from bar 7;
    * **counter** - a syncopated off-beat answer from bar 4, which is where the
      race's middle section needs something to happen;
    * **resolution** - on the crossing downbeat, the tonic triad, struck once and
      allowed to ring out under the payoff.

    Nothing after the crossing is busy. The last three and a third seconds are the
    chord decaying and one closing bass note, because the payoff card is on screen
    and the film has stopped being a race.
    """
    out = silence(length)
    beat = plan.beat
    total_beats = int(length / sample_rate / beat) + 2

    for index in range(total_beats):
        when = index * beat
        at = seconds_to_samples(when, sample_rate)
        if at >= length:
            break
        bar = index // BEATS_PER_BAR
        beat_in_bar = index % BEATS_PER_BAR
        root, _voicing = CHORDS[bar % len(CHORDS)]
        after_line = when >= plan.crossing - 1e-6
        sprint = sprint_from <= when < plan.crossing
        build = 12.0 <= when < sprint_from

        # Energy by section. Flat inside a section and stepped between them, so
        # the arc is legible rather than a slow ramp nobody notices.
        if bar == 0:
            energy = 0.52
        elif bar <= 3:
            energy = 0.70
        elif bar <= 6:
            energy = 0.84
        elif bar == 7:
            energy = 0.90
        elif bar == 8:
            energy = 0.94
        else:
            energy = 0.34
        if after_line:
            energy = 0.28

        # --- pulse: eighths, and sixteenths once it builds -------------------
        divisions = 2 if not (build or sprint) else 4
        if after_line:
            divisions = 1
        for step in range(divisions):
            offset = at + seconds_to_samples(beat * step / divisions, sample_rate)
            if offset >= length:
                break
            accent = 1.0 if step == 0 else (0.52 if divisions == 2 else 0.40)
            # Every part is nudged a few milliseconds off the grid - see
            # `_LAYER_OFFSETS`. Inaudible as timing, and it stops the downbeat
            # from being the tallest sample in the film.
            offset += seconds_to_samples(_LAYER_OFFSETS["hat"], sample_rate)
            hat = noise_burst(
                seconds_to_samples(0.026, sample_rate),
                seed=seed ^ ((index * 977 + step * 131) & 0x7FFFFFFF),
                attack=0.0004, decay=0.0075,
                highpass=4200.0, lowpass=8600.0, stages=2, sample_rate=sample_rate,
            )
            add_into(out, hat, offset, 0.30 * accent * energy)

        # --- bass -------------------------------------------------------------
        bass_here = (beat_in_bar == 0) or (bar >= 4 and not after_line) or sprint
        if after_line and beat_in_bar != 0:
            bass_here = False
        if bass_here:
            eighths = 2 if sprint else 1
            for step in range(eighths):
                offset = (at + seconds_to_samples(beat * step / eighths, sample_rate)
                          + seconds_to_samples(_LAYER_OFFSETS["bass"], sample_rate))
                if offset >= length:
                    break
                add_into(out, tone(
                    seconds_to_samples(beat * 0.86, sample_rate),
                    freq=root, freq_end=root * 0.998,
                    attack=0.005, decay=0.115 + 0.05 * (1 - step),
                    sample_rate=sample_rate,
                ), offset, 0.34 * energy * (1.0 if step == 0 else 0.62))
                add_into(out, tone(
                    seconds_to_samples(beat * 0.5, sample_rate), freq=root * 2.0,
                    attack=0.004, decay=0.055, sample_rate=sample_rate,
                ), offset, 0.12 * energy)
                # The only thing under 120 Hz in the whole bed, and only on a
                # downbeat: an octave below the root, short, so the beat has a
                # floor without the mix having a mud problem.
                if beat_in_bar == 0 and step == 0 and not after_line:
                    add_into(out, tone(
                        seconds_to_samples(beat * 0.55, sample_rate),
                        freq=root * 0.5, attack=0.007, decay=0.070,
                        sample_rate=sample_rate,
                    ), offset + seconds_to_samples(
                        _LAYER_OFFSETS["sub"] - _LAYER_OFFSETS["bass"], sample_rate),
                       0.78 * energy * (0.5 if bar >= 7 else 1.0))

        if (beat_in_bar == 2 and bar >= 4 and not after_line
                and beat_in_bar == 2):
            add_into(out, tone(
                seconds_to_samples(beat * 0.45, sample_rate),
                freq=root * 0.5, attack=0.007, decay=0.050,
                sample_rate=sample_rate,
            ), at + seconds_to_samples(_LAYER_OFFSETS["sub"], sample_rate),
               0.34 * energy * (0.5 if bar >= 7 else 1.0))

        # --- body: the chord itself, once a bar, filling 300-800 Hz -----------
        if beat_in_bar == 0 and bar >= 1 and not after_line:
            for ratio, gain in ((1.2, 0.10), (1.5, 0.11), (2.0, 0.07)):
                add_into(out, _pluck(
                    seconds_to_samples(beat * 1.9, sample_rate),
                    freq=root * ratio, decay=0.30, bright=0.30,
                    sample_rate=sample_rate,
                ), at + seconds_to_samples(_LAYER_OFFSETS["body"], sample_rate),
                   gain * energy)

        # --- figure -----------------------------------------------------------
        if 1 <= bar <= 8 and not after_line:
            octaves = (2.0,) if bar < 7 else (2.0, 4.0)
            for step, ratio in enumerate((1.0, 1.5, 2.0)):
                offset = (at + seconds_to_samples(beat * 0.5 * step, sample_rate)
                          + seconds_to_samples(_LAYER_OFFSETS["figure"], sample_rate))
                if offset >= length:
                    break
                for octave in octaves:
                    add_into(out, _pluck(
                        seconds_to_samples(beat * 0.46, sample_rate),
                        freq=root * ratio * octave, decay=0.070,
                        bright=0.8 if octave == 2.0 else 0.45,
                        sample_rate=sample_rate,
                    ), offset, (0.200 if octave == 2.0 else 0.105) * energy)

        # --- counter ----------------------------------------------------------
        if 4 <= bar <= 8 and beat_in_bar in (1, 3) and not after_line:
            offset = at + seconds_to_samples(beat * 0.5, sample_rate)
            if offset < length:
                add_into(out, _pluck(
                    seconds_to_samples(beat * 0.38, sample_rate),
                    freq=root * 3.0, decay=0.048, bright=0.6, sample_rate=sample_rate,
                ), offset, 0.120 * energy)

    # --- the resolution, on the crossing downbeat ----------------------------
    at = seconds_to_samples(plan.crossing, sample_rate)
    if at < length:
        root = CHORDS[0][0]
        # Staggered attacks, not a stack. Five partials struck on the same sample
        # sum to a single spike three times the height of any of them, which is a
        # peak the whole film then has to be mastered around; spreading them over
        # twelve milliseconds is inaudible as timing and halves the crest.
        for index, (ratio, gain, decay) in enumerate((
                (1.0, 0.34, 0.55), (2.0, 0.26, 0.48), (3.0, 0.17, 0.38),
                (4.0, 0.11, 0.30), (6.0, 0.06, 0.24))):
            add_into(out, tone(
                min(length - at, seconds_to_samples(2.6, sample_rate)),
                freq=root * ratio, attack=0.006 + 0.0022 * index,
                decay=decay, sample_rate=sample_rate,
            ), at + seconds_to_samples(0.003 * index, sample_rate), gain)
        add_into(out, noise_burst(
            seconds_to_samples(0.05, sample_rate), seed=seed ^ 0x5E11,
            attack=0.0008, decay=0.013, highpass=3200.0, lowpass=8000.0,
            stages=2, sample_rate=sample_rate,
        ), at, 0.14)

    low_pass(out, 11000.0, sample_rate=sample_rate, stages=1)
    # Part M, enforced rather than trusted: two poles at 62 Hz mean the music
    # supplies the mix's stable low end without anything running under the note.
    high_pass(out, 62.0, sample_rate=sample_rate, stages=2)

    # Ring off rather than stop.
    tail = seconds_to_samples(0.60, sample_rate)
    for index in range(max(0, length - tail), length):
        position = (length - index) / tail
        out[index] *= position * position
    largest = peak(out)
    if largest > 0.0:
        scale(out, 1.0 / largest)
    return out


# --- ducking and space -------------------------------------------------------


def _duck_envelope(length: int, events: Sequence[tuple[float, float]],
                   depth_db: float, release: float, lead: float = 0.0,
                   attack: float = 0.008, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """A sidechain envelope: 1.0 everywhere, dipping to `depth_db` at each event.

    Built by taking the minimum of a dip per event rather than by summing them,
    so two events 40 ms apart duck once rather than twice as far. `lead` opens the
    dip *before* the event, which is Part G: the space in front of a transient is
    what makes it land.
    """
    out = np.ones(length)
    if depth_db <= 0.0 or not events:
        return out
    for when, weight in events:
        floor = 10.0 ** (-(depth_db * min(1.0, max(0.0, weight))) / 20.0)
        start = int((when - lead - attack) * sample_rate)
        bottom = int((when - lead) * sample_rate)
        end = int((when + release) * sample_rate)
        start = max(0, start)
        bottom = max(start + 1, min(length, bottom))
        end = max(bottom + 1, min(length, end))
        if start >= length:
            continue
        down = np.linspace(1.0, floor, bottom - start)
        out[start:bottom] = np.minimum(out[start:bottom], down)
        up = floor + (1.0 - floor) * (np.linspace(0.0, 1.0, end - bottom) ** 1.7)
        out[bottom:end] = np.minimum(out[bottom:end], up)
    return out


# --- master ------------------------------------------------------------------


def _limiter(left: np.ndarray, right: np.ndarray, ceiling: float,
             radius_seconds: float = LIMITER_RADIUS_SECONDS,
             sample_rate: int = SAMPLE_RATE) -> tuple[np.ndarray, np.ndarray, float]:
    """A look-ahead limiter that provably cannot leave a sample over the ceiling.

    The same two-pass construction `audio.soundtrack.master` uses, in numpy: the
    gain each sample would need, then a sliding *minimum* of that over the
    look-ahead radius - so the gain is already down before the peak arrives - then
    a moving average over the same radius, which smooths it without ever raising
    it above the sliding minimum. Since the average of a window is at most the
    window's maximum and the sliding minimum is by construction below every
    required gain in the window, the result is still under the ceiling everywhere.
    """
    magnitude = np.maximum(np.abs(left), np.abs(right))
    needed = np.where(magnitude > ceiling, ceiling / np.maximum(magnitude, 1e-12), 1.0)
    radius = max(1, int(radius_seconds * sample_rate))
    window = 2 * radius + 1

    padded = np.concatenate((np.ones(radius), needed, np.ones(radius)))
    # Sliding minimum, O(n) via a strided reduction on a windowed view.
    view = np.lib.stride_tricks.sliding_window_view(padded, window)
    floor = view.min(axis=1)

    kernel = np.ones(window) / window
    smoothed = np.convolve(np.concatenate((np.ones(radius), floor, np.ones(radius))),
                           kernel, mode="valid")
    gain = np.minimum(smoothed, floor)
    worst = 20.0 * math.log10(max(float(gain.min()), 1e-12))
    mean = 20.0 * math.log10(max(float(gain.mean()), 1e-12))
    return left * gain, right * gain, (worst, mean, float(np.mean(gain < 0.9999)))


#: -70 dBFS, as a linear amplitude. See `prominence`.
_BED_FLOOR = 10.0 ** (-70.0 / 20.0)


def _window_rms(signal: np.ndarray, at: float, seconds: float,
                sample_rate: int = SAMPLE_RATE) -> float:
    start = max(0, int(at * sample_rate))
    end = min(signal.shape[0], start + int(seconds * sample_rate))
    if end <= start:
        return 0.0
    return float(np.sqrt(np.mean(signal[start:end] ** 2)))


#: The band the race's own voices live in. The machines ring between 130 and
#: 750 Hz, track contacts between 300 and 1100, marble clicks and rail ticks
#: between 1600 and 6500; 300-4000 Hz covers the part of all of them that a
#: listener uses to separate one from another.
PROMINENCE_BAND = (300.0, 4000.0)


def _band_window_rms(signal: np.ndarray, at: float, seconds: float,
                     low: float, high: float,
                     sample_rate: int = SAMPLE_RATE) -> float:
    start = max(0, int(at * sample_rate))
    end = min(signal.shape[0], start + int(seconds * sample_rate))
    if end - start < 32:
        return 0.0
    segment = signal[start:end]
    spectrum = np.fft.rfft(segment * np.hanning(segment.size))
    freqs = np.fft.rfftfreq(segment.size, 1.0 / sample_rate)
    mask = (freqs >= low) & (freqs < high)
    return float(np.sqrt(np.sum(np.abs(spectrum[mask]) ** 2))) / segment.size


def prominence(
    physical: np.ndarray,
    music: np.ndarray,
    events: Sequence[Cue],
    *,
    seconds: float = 0.08,
    band: tuple[float, float] = PROMINENCE_BAND,
    sample_rate: int = SAMPLE_RATE,
) -> dict[str, float]:
    """How far the race stands above the music, in dB, at the events that matter.

    The direct answer to the brief's eighth review question. For each event the
    physical buses and the music bus are measured over the same 80 ms window and
    subtracted: positive means the marble is in front, negative means the music
    has covered it. A median is not enough here - one buried mechanism is a
    defect - so the minimum is reported too.

    **The comparison is band-limited, and that is not a detail.** Masking is
    frequency-specific: a knock at 400 Hz is not hidden by a bass note at 110 Hz
    however much broadband energy the bass has. Measured full-band, this
    instrument reported three of Mix B's mechanisms "buried" that share almost no
    spectrum with the part of the bed that was supposedly burying them. Restricted
    to `PROMINENCE_BAND`, it compares the two signals where they actually compete.
    """
    if not events:
        return {"count": 0}
    values = []
    low, high = band
    for cue in events:
        loud = _band_window_rms(physical, cue.at, seconds, low, high, sample_rate)
        bed = _band_window_rms(music, cue.at, seconds, low, high, sample_rate)
        # The bed is clamped at -70 dBFS. A music bed made of struck notes is
        # genuinely, exactly silent between them, and the first version of this
        # instrument divided by that: it reported +215 dB of prominence for an
        # event that happened to land in a gap, which is not a measurement of
        # anything. -70 dBFS is far under audibility in a -14 LUFS mix, so
        # clamping there changes no real comparison and removes the infinity.
        values.append(20.0 * math.log10(max(loud, 1e-12) / max(bed, _BED_FLOOR)))
    array_values = np.asarray(values)
    return {
        "count": len(values),
        "min_db": round(float(array_values.min()), 2),
        "median_db": round(float(np.median(array_values)), 2),
        "max_db": round(float(array_values.max()), 2),
        "below_zero": int((array_values < 0.0).sum()),
    }


def loudest_moment(left: np.ndarray, right: np.ndarray,
                   window: float = 0.05,
                   sample_rate: int = SAMPLE_RATE) -> tuple[float, float]:
    """`(second, dBFS)` of the loudest short window in the film.

    `tools/sloped_short_qc.py` has asserted since V19 that this lands on the
    winner's crossing, and the assertion has caught a real defect before - V22.1's
    mechanism drone summing with the apron contacts to make the mixer, not the
    finish, the peak of the film. It is checked here for the same reason.
    """
    mono = (left + right) * 0.5
    size = max(1, int(window * sample_rate))
    count = mono.shape[0] // size
    trimmed = mono[:count * size].reshape(count, size)
    energy = np.sqrt(np.mean(trimmed * trimmed, axis=1))
    best = int(np.argmax(energy))
    return best * window, 20.0 * math.log10(max(float(energy[best]), 1e-12))


@dataclass
class RaceMix:
    """The finished stereo pair, what went into it and what it measures."""

    left: array
    right: array
    sample_rate: int
    profile: str
    placed: dict[str, int]
    report: dict[str, Any]

    @property
    def seconds(self) -> float:
        return len(self.left) / float(self.sample_rate)


def build_asmr_audio(
    replay: dict[str, Any],
    track: dict[str, Any],
    clock,
    profile: MixProfile | str = "B",
    *,
    sample_rate: int = SAMPLE_RATE,
    music: bool = True,
) -> RaceMix:
    """The whole V32.2 soundtrack, on the finished film's own integer timeline.

    The order matters and is the order the design is in:

    1. the physical layer - room, rolling, ticks, clicks, contacts, mechanisms,
       the points, the eight arrivals - each placed on a recorded event;
    2. a music bus, built separately so it can be ducked without touching
       anything physical;
    3. the ducks: one from every mechanism hit and every arrival, plus a wider
       *space* opened in front of the two biggest moments;
    4. optional gentle bus compression, per profile;
    5. one static gain onto the loudness target, then the limiter.

    Step 5 is the important one for Part T. Loudness is reached with a *single*
    number over the whole timeline, measured by `audio.loudness`, which cannot
    change LRA, crest factor or the relation between any two moments. Nothing in
    this chain normalises, and nothing squashes.
    """
    from audio import loudness as meter

    if isinstance(profile, str):
        profile = PROFILES[profile]

    length = seconds_to_samples(clock.duration, sample_rate)
    if length != int(clock.frames) * SAMPLES_PER_FRAME:
        raise ValueError(
            f"{length} samples is not {clock.frames} frames x {SAMPLES_PER_FRAME}")

    seed_base = int(replay.get("seed", 0))
    rows = telemetry(replay, track, clock)

    physical_left = np.zeros(length)
    physical_right = np.zeros(length)
    placed: dict[str, int] = {}

    def bump(name: str, count: int = 1) -> None:
        placed[name] = placed.get(name, 0) + count

    def place(cue: array, at: float, level_db: float, pan: float) -> None:
        from audio.soundtrack import pan_gains

        gain = db_to_gain(level_db)
        left_gain, right_gain = pan_gains(pan)
        offset = int(round(at * sample_rate))
        data = np.asarray(cue, dtype=np.float64)
        start = max(0, offset)
        head = start - offset
        end = min(length, offset + len(data))
        if end <= start:
            return
        chunk = data[head:head + (end - start)]
        physical_left[start:end] += chunk * (gain * left_gain)
        physical_right[start:end] += chunk * (gain * right_gain)

    # --- 1. the physical layer ----------------------------------------------

    room = room_tone(length, stable_seed("v322-room", seed_base))
    room_gain = db_to_gain(profile.room) / max(rms(room), 1e-9)
    room_data = np.asarray(room, dtype=np.float64)
    physical_left += room_data * room_gain
    physical_right += room_data * (room_gain * 0.93)
    bump("room")

    roll, roll_report = rolling_layer(
        rows, length, stable_seed("v322-roll", seed_base), profile,
        sample_rate=sample_rate)
    roll_data = np.asarray(roll, dtype=np.float64)
    # By RMS, like the other two beds. Peak-levelling this one was a mistake worth
    # recording: the gate gives the layer a crest factor around 21 dB, so a peak
    # budget of -19.5 put its *average* at -40 dBFS and the rolling layer - the
    # thing this whole pass is about - was inaudible under the contacts.
    # Normalising by RMS changes only where the layer sits; every ratio inside it,
    # and so all the contrast the gate bought, is untouched.
    roll_gain = db_to_gain(profile.roll) / max(float(np.sqrt(np.mean(roll_data ** 2))), 1e-9)
    roll_bus_left = roll_data * roll_gain
    roll_bus_right = roll_data * (roll_gain * 0.965)
    bump("rolling")

    ticks = rail_ticks(replay, clock, rows)
    for cue in ticks:
        place(rail_tick(cue.strength, stable_seed("v322-tick", seed_base,
                                                  cue.detail["marble"], round(cue.at, 4))),
              cue.at, profile.tick + 9.0 * (cue.strength - 1.0), cue.pan)
    bump("tick", len(ticks))

    clicks = marble_clicks(replay, clock, rows)
    for cue in clicks:
        place(marble_click(cue.strength, stable_seed("v322-click", seed_base,
                                                     cue.detail["a"], cue.detail["b"],
                                                     round(cue.detail["replay"], 4))),
              cue.at, profile.click + 15.0 * (cue.strength - 1.0), cue.pan)
    bump("click", len(clicks))

    contacts = track_contacts(replay, track, clock)
    for cue in contacts:
        level = profile.contact + (profile.contact_loud - profile.contact) * cue.strength
        place(track_contact(cue.strength,
                            BODY_HZ.get(cue.detail["module"], BODY_DEFAULT),
                            stable_seed("v322-contact", seed_base, cue.detail["marble"],
                                        round(cue.at, 4))),
              cue.at, level, cue.pan)
    bump("contact", len(contacts))

    machines = mechanism_hits(replay, track, clock, rows)
    for cue in machines:
        module = cue.detail["module"]
        voice = MECHANISM_VOICES.get(module)
        if voice is None:
            continue
        place(voice(stable_seed("v322-mech", seed_base, module, round(cue.at, 4))),
              cue.at, profile.mechanism + MECHANISM_TRIM.get(module, 0.0), cue.pan)
        bump(f"mechanism:{module}")

    switches = points_switches(replay, clock, rows)
    for cue in switches:
        place(points_tick(cue.strength,
                          stable_seed("v322-points", seed_base, round(cue.at, 4))),
              cue.at, profile.points, cue.pan)
    bump("points", len(switches))

    arrivals = crossings(replay, clock)
    for cue in arrivals:
        winner = cue.detail["order"] == 1
        place(arrival_cue(winner, stable_seed("v322-finish", seed_base,
                                              cue.detail["marble"])),
              cue.at, profile.finish_winner if winner else profile.finish, 0.0)
    bump("finish", len(arrivals))

    # --- 2. the music bus ----------------------------------------------------

    winner_cue = next((c for c in arrivals if c.detail["order"] == 1), None)
    crossing = winner_cue.at if winner_cue else clock.duration * 0.82
    plan = music_plan(clock.duration, crossing)
    sprint_from = min(machines[-1].at, crossing - 0.5) if machines else crossing - 3.0

    music_left = np.zeros(length)
    music_right = np.zeros(length)
    if music:
        score = music_score(length, stable_seed("v322-music", seed_base), plan,
                            sprint_from=sprint_from, sample_rate=sample_rate)
        if profile.music_compressed:
            from audio.soundtrack import compress

            mirror = array("d", score)
            squash = compress(score, mirror,
                              threshold_dbfs=profile.music_compress_threshold,
                              ratio=profile.music_compress_ratio,
                              sample_rate=sample_rate)
            report_music_reduction = round(squash.max_reduction_db, 3)
        else:
            report_music_reduction = 0.0
        gain = db_to_gain(profile.music) / max(rms(score), 1e-9)
        data = np.asarray(score, dtype=np.float64) * gain
        music_left += data
        music_right += data
        bump("music")
    else:
        report_music_reduction = 0.0

    # --- 3. ducking, and the space in front of the big moments ---------------

    duck_events = [(cue.at, 0.55 + 0.45 * MECHANISM_TRIM.get(cue.detail["module"], 0.0) / 2.0)
                   for cue in machines]
    duck_events += [(cue.at, 1.0 if cue.detail["order"] == 1 else 0.45) for cue in arrivals]
    duck_events += [(cue.at, 0.35 + 0.45 * cue.strength) for cue in contacts
                    if cue.strength >= 0.55]
    duck = _duck_envelope(length, duck_events, profile.duck_db, profile.duck_release,
                          sample_rate=sample_rate)
    music_left *= duck
    music_right *= duck

    # Part G: a wider dip, opened *before* the event, on the two moments the film
    # is built around - the last wheel and the winner crossing the line. It pulls
    # the rolling layer down as well as the music, which is the only way to put
    # actual space around a transient rather than just more level on it.
    space_events = [(cue.at, 1.0) for cue in machines if cue.detail["module"] == "last"]
    space = _duck_envelope(length, space_events, profile.space_db, 0.42,
                           lead=profile.space_lead, attack=0.16,
                           sample_rate=sample_rate)
    # The crossing gets its own, longer, dip. The winner's arrival runs 0.70 s
    # and the music's resolution chord lands on the same downbeat by design, so
    # a 0.42 s recovery had the bed climbing back up underneath the chime: in
    # Mix B the two summed to +2.18 dBFS and the limiter took 3.5 dB out of the
    # loudest moment in the film to catch it. Holding the music down until the
    # chime has decayed is the same few decibels, spent by the mix rather than
    # by a detector, and the transient stays intact - which is the whole of Part
    # T. It is also better ducking: a bed that dips and stays down for the
    # duration of what it is making room for is what "recovers smoothly" means.
    if winner_cue is not None:
        arrival = _duck_envelope(
            length, [(winner_cue.at, 1.0)], profile.space_db + 2.5, 0.95,
            lead=profile.space_lead, attack=0.16, sample_rate=sample_rate)
        space = np.minimum(space, arrival)
    roll_bus_left *= space
    roll_bus_right *= space
    music_left *= space
    music_right *= space

    left = physical_left + roll_bus_left + music_left
    right = physical_right + roll_bus_right + music_right

    buses = {
        "physical": (physical_left, physical_right),
        "rolling": (roll_bus_left, roll_bus_right),
        "music": (music_left, music_right),
    }
    bus_report = {}
    for label, (bus_left, bus_right) in buses.items():
        stacked = np.stack((bus_left, bus_right), axis=1)
        bus_rms = float(np.sqrt(np.mean(stacked ** 2)))
        bus_report[label] = {
            "rms_dbfs": round(20.0 * math.log10(max(bus_rms, 1e-12)), 2),
            "peak_dbfs": round(
                20.0 * math.log10(max(float(np.max(np.abs(stacked))), 1e-12)), 2),
            "bands": meter.band_profile(stacked, sample_rate),
        }

    report: dict[str, Any] = {
        "version": ASMR_VERSION,
        "profile": profile.name,
        "profile_title": profile.title,
        "telemetry": rows.as_dict(),
        "buses": bus_report,
        "rolling": roll_report,
        "music": plan.as_dict(),
        "music_sprint_from": round(sprint_from, 4),
        "music_compressor_reduction_db": report_music_reduction,
        "events": {
            "ticks": len(ticks),
            "clicks": len(clicks),
            "contacts": len(contacts),
            "mechanisms": len(machines),
            "points": len(switches),
            "finishes": len(arrivals),
        },
        "duck_events": len(duck_events),
        "space_events": [round(when, 4) for when, _ in space_events],
        "peak_before_master_dbfs": round(
            20.0 * math.log10(max(float(np.max(np.abs(np.stack((left, right))))), 1e-12)), 3),
    }

    # --- 4. optional bus compression ----------------------------------------

    if profile.compressed:
        from audio.soundtrack import compress

        buffer_left = array("d", left)
        buffer_right = array("d", right)
        squash = compress(buffer_left, buffer_right,
                          threshold_dbfs=profile.compress_threshold,
                          ratio=profile.compress_ratio,
                          sample_rate=sample_rate)
        left = np.asarray(buffer_left, dtype=np.float64)
        right = np.asarray(buffer_right, dtype=np.float64)
        report["compressor_reduction_db"] = round(squash.max_reduction_db, 3)
    else:
        report["compressor_reduction_db"] = 0.0

    # --- 5. one gain onto the target, then the limiter -----------------------

    stereo = np.stack((left, right), axis=1)
    before = meter.integrated(stereo, sample_rate)
    trim = meter.gain_for_target(stereo, profile.target_lufs, sample_rate)
    left = left * trim
    right = right * trim
    report["loudness_before_trim_lufs"] = round(before, 3)
    report["trim_db"] = round(20.0 * math.log10(max(trim, 1e-12)), 3)

    ceiling = db_to_gain(MASTER_CEILING_DBFS)
    left, right, (worst, mean, active) = _limiter(
        left, right, ceiling, sample_rate=sample_rate)
    report["limiter_worst_db"] = round(worst, 3)
    report["limiter_mean_db"] = round(mean, 4)
    report["limiter_active_fraction"] = round(active, 5)
    report["limiter_engaged"] = bool(worst < -0.001)

    final = np.stack((left, right), axis=1)
    report["loudness"] = meter.measure(final, sample_rate).as_dict()

    # --- what the mix does at the moments the film is made of ---------------
    race_bus = (physical_left + roll_bus_left + physical_right + roll_bus_right) * 0.5
    music_bus = (music_left + music_right) * 0.5
    report["prominence"] = {
        "mechanisms": prominence(race_bus, music_bus, machines, sample_rate=sample_rate),
        "finishes": prominence(race_bus, music_bus, arrivals, sample_rate=sample_rate),
        "loud_contacts": prominence(
            race_bus, music_bus,
            [cue for cue in contacts if cue.strength >= 0.5], sample_rate=sample_rate),
        "band": list(PROMINENCE_BAND),
    }
    when, level = loudest_moment(left, right, sample_rate=sample_rate)
    report["loudest_moment"] = {
        "second": round(when, 3),
        "dbfs": round(level, 2),
        "winner_crossing": round(crossing, 3),
        "on_the_crossing": bool(abs(when - crossing) <= 0.30),
    }
    # Part J: the music's own energy, second by second, so "does it build" is a
    # series rather than an opinion.
    music_seconds = []
    for index in range(int(clock.duration)):
        music_seconds.append(round(
            20.0 * math.log10(max(_window_rms(music_bus, float(index), 1.0,
                                              sample_rate), 1e-12)), 2))
    report["music_per_second_dbfs"] = music_seconds
    race_seconds = []
    for index in range(int(clock.duration)):
        race_seconds.append(round(
            20.0 * math.log10(max(_window_rms(race_bus, float(index), 1.0,
                                              sample_rate), 1e-12)), 2))
    report["race_per_second_dbfs"] = race_seconds

    return RaceMix(
        left=array("d", left),
        right=array("d", right),
        sample_rate=sample_rate,
        profile=profile.name,
        placed=placed,
        report=report,
    )

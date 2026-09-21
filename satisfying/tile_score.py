"""The score: canonical events turned into a deterministic audio schedule.

This module is the middle of three layers and it makes no sound. It reads a
playback document - the frozen record `satisfying.tile_playback` publishes and
`satisfying.tile_completion` attaches an ending to - and writes down *what is
heard, when, at what pitch and how loudly*. `satisfying.tile_audio` turns that
into samples. Nothing here imports a synthesiser and nothing here can reach the
physics, which is the mechanical reason the soundtrack cannot influence the run
it is describing.

## The clock is render time, never simulation time

The ending holds the simulation clock still for 0.92 s - 0.14 s of hit-stop,
0.48 s of confirmation, 0.30 s of the gate opening - and then plays the escape
at 0.45x. A cue placed at a simulation instant would stall with the clock and
arrive under the wrong picture. So every event in this module carries a
**render** time, and the four climax instants are read out of
`completion["timeline"]` by state name rather than re-derived from the timing
preset. If Phase 4 re-times the ending, the score follows without being edited.

Below the completion the `locked` segment is the identity map, so a collision's
simulation time *is* its render time. That is asserted rather than assumed:
`schedule` checks the locked segment's rate is 1.0 and starts at zero.

## Events land on the frame the picture lands on

A tile struck at 21.4711 s is first drawn on frame `ceil(21.4711 * 30) = 645`,
which is shown at 21.5 s. Two placements were possible and the difference
matters:

* at the canonical instant 21.4711 - the audio then **leads** the picture by up
  to one frame period, a mean of 16.7 ms at 30 fps;
* at the frame instant 21.5 - the audio is simultaneous with the frame the
  viewer actually sees.

The second is used. Audio arriving before its picture is the direction the ear
detects soonest - about 22 ms against about 45 ms the other way - and a video is
a sequence of frames, so "the frame on which the tile lights" is the honest
definition of when the tile lights. The cost is that the rhythm is quantised to
33 ms, which at four to six contacts a second is below the grid the ear groups
on. The frame rule is `tile_playback.activation_frames`' rule, applied to every
contact rather than only to activations.

## The five strengths

| kind         | what it is                                     |
|--------------|------------------------------------------------|
| `duplicate`  | a contact on a tile that is already lit         |
| `activation` | a tile lights; 1 to 50 of 51                    |
| `final`      | the fifty-first tile                            |
| `unlock`     | the gate flares and retracts                    |
| `escape`     | the ball is released                            |

`confirm` is a sixth, optional kind: it exists only for the confirmation-hold
treatments that put something under the 0.92 s pause, and `breath` has none.

The hierarchy is carried as a gain per event and nothing downstream is allowed
to normalise an event on its own, because the gains *are* the hierarchy. Phase
4's visual hierarchy - brightness only, brightness plus motion, a white
detonation - is the contract this mirrors.

## Tile identity, not collision order

A tile's pitch is a function of where it is in the arena and of nothing else:
the same arena gives `tile_17` the same fundamental in every seed, on every run,
whichever order the ball happens to find the tiles in. See `pitch_index_for`.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field, replace
from typing import Any, Sequence

__all__ = [
    "SCORE_FORMAT",
    "ScoreError",
    "AudioConfig",
    "CONFIGS",
    "DEFAULT_CONFIG",
    "named_config",
    "AudioEvent",
    "AudioSchedule",
    "MINOR_PENTATONIC",
    "EVENT_KINDS",
    "CLIMAX_BEATS",
    "frame_for",
    "pitch_table",
    "pitch_index_for",
    "frequency_for",
    "pan_for",
    "schedule",
    "schedule_document",
]

# Bumped when the meaning of a field changes, never when one is added. A
# renderer or a test that reads a schedule checks it.
SCORE_FORMAT = 1

# Minor pentatonic, in semitones above the root. Chosen for the property the
# brief asks for and nothing else: the ball decides the order, so any two notes
# that can land together have to be consonant together. A minor pentatonic has
# no semitone and no tritone anywhere in it, in any inversion, so every pair and
# every stack of the eleven pitches below is consonant. A major scale is not -
# its fourth against its seventh is a tritone, and at five contacts a second
# that pair arrives many times a run.
MINOR_PENTATONIC: tuple[int, ...] = (0, 3, 5, 7, 10)

EVENT_KINDS: tuple[str, ...] = (
    "duplicate",
    "activation",
    "final",
    "confirm",
    "unlock",
    "escape",
)

# The climax states a beat is taken from, in order. These are `state` values in
# `completion["timeline"]`; the score never computes them from a timing preset.
CLIMAX_BEATS: tuple[str, ...] = (
    "final_hit",
    "confirming",
    "unlocking",
    "escaping",
    "settled",
)


class ScoreError(RuntimeError):
    """A document or a configuration that cannot carry a schedule."""


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AudioConfig:
    """Every dial the schedule depends on, and therefore the audio identity.

    Determinism in Phase 5 is stated against this object: the same seed and the
    same `AudioConfig` give the same schedule, byte for byte, and the same
    rendered waveform. So everything that could change a sample is a field here
    - including `fps`, because the frame grid decides where events land, and
    `sample_rate`, because it decides how they are quantised.
    """

    name: str = "v2_refined"

    # --- the timeline -----------------------------------------------------
    fps: float = 30.0
    sample_rate: int = 48000

    # --- the pitch system -------------------------------------------------
    # A3. Low enough that the arena has a floor, high enough that the second
    # partial of the lowest note is 440 Hz and survives a phone speaker.
    root_hz: float = 220.0
    scale: tuple[int, ...] = MINOR_PENTATONIC
    octaves: int = 2

    # --- the mapping ------------------------------------------------------
    # True: pitch rises with the tile's height in the arena, so neighbouring
    # walls are neighbouring notes and the two sides of the ring mirror each
    # other. False: `tile.index % pitches`, which is stable per tile and
    # spatially meaningless - the V1 control.
    spatial_pitch: bool = True
    # How far a tile is placed off centre, by the x of its midpoint. 0 is mono
    # placement. Capped well below hard: the arena is 86% of a phone frame.
    pan_depth: float = 0.45

    # --- the hierarchy, as peak gains -------------------------------------
    # These numbers are the hierarchy. Cues are peak-normalised to 1.0 before
    # the gain is applied, so an event's peak in the mix is its gain, and no
    # stage after this one is allowed to touch an event on its own.
    duplicate_gain: float = 0.098
    activation_gain: float = 0.300
    final_gain: float = 0.760
    unlock_gain: float = 0.360
    escape_gain: float = 0.440
    confirm_gain: float = 0.075

    # --- envelopes --------------------------------------------------------
    duplicate_decay: float = 0.042
    duplicate_seconds: float = 0.110
    duplicate_lowpass_hz: float = 1700.0
    activation_decay: float = 0.215
    activation_seconds: float = 0.620
    unlock_seconds: float = 0.620
    # A ceiling, not a length. The release's real length is whatever is left
    # of the video after it, less `end_silence_seconds` - see the escape event
    # in `schedule`. Rendered at a fixed 1.56 s the pad ran past the last
    # frame on all five seeds and was cut off by the buffer instead of ending:
    # seed 37169's final sample measured -26.9 dBFS, which is a splice, not an
    # ending.
    escape_seconds: float = 1.560
    # Deliberate silence at the end of the video. The brief's ending is dense
    # activity, then the detonation, then a controlled reduction; this is the
    # reduction, and it is a schedule decision rather than something the decay
    # happens to leave behind.
    end_silence_seconds: float = 0.200

    # --- the small-speaker tilt -------------------------------------------
    # A phone reproduces almost nothing below about 500 Hz, and the pitch
    # mapping puts the bottom of the arena at 220. Rendered flat, the low
    # tiles measured 7.5 dB quieter than the high ones through
    # `loudness.phone_filter` while sitting inside 1.4 dB of each other on the
    # master - a loudness gradient that exists only on the speaker most of the
    # audience is using, and that would make the bottom third of the arena
    # sound like it mattered less.
    #
    # The correction is a spectral tilt, not a gain: the lower a note is, the
    # more of its energy is carried by its upper partials. That is what a real
    # struck bar does - a low one is far richer in overtones than a high one -
    # so it costs nothing in plausibility, and it leaves every note's
    # fundamental and therefore its identity exactly where it was.
    #
    # `tilt = (tilt_hz - freq) / tilt_hz`, clamped at zero: full strength at
    # the bottom of the register, nothing at 660 Hz and above.
    tilt_hz: float = 660.0
    tilt_depth: float = 1.35
    # Duplicates are rolled off at 1.7 kHz by design, so they get a share of
    # the tilt rather than all of it - enough to stay present on a phone,
    # never enough to start competing with an activation.
    tilt_depth_duplicate: float = 0.55

    # --- progression ------------------------------------------------------
    # Driven by the activation's own `count` field, which is canonical data.
    # Off in V1. The duplicate is deliberately left fixed while the activation
    # brightens, so what grows is the *gap* between them.
    progression: bool = True
    # Third-partial gain at 0 of 51 and at 51 of 51.
    bright_low: float = 0.135
    bright_high: float = 0.460
    # A fourth partial that is not there at all early and arrives by the end.
    fourth_growth: float = 0.160
    # The **upper** partials' decays lengthen by this ratio, end to end. The
    # fundamental's does not, and that is the correction rather than a taste:
    # lengthening every partial together made a late activation measurably
    # *darker* - spectral centroid 2379 Hz at 1 of 51 against 2166 Hz at 50 of
    # 51 over its first 80 ms - because the fundamental carries most of the
    # energy and ringing it for longer simply adds bass. The brief asks for a
    # brightness increase, and the first build delivered the opposite while
    # every gain in it moved the right way.
    upper_decay_growth: float = 0.600
    # Gain grows by this much, end to end. Small: the hierarchy must not drift.
    gain_growth: float = 0.085
    # A fifth above the fundamental, faded in over the last fifth of the run.
    # The "harmonic layer becoming available near completion" the brief lists,
    # and it is a real second note rather than another overtone.
    late_fifth_from: float = 0.80
    late_fifth_gain: float = 0.130

    # --- density ----------------------------------------------------------
    # Two deterministic dampers, both computed here so they are in the
    # machine-readable schedule and a test can read them.
    #
    # A tile struck again while it is still ringing does not add a whole new
    # event's worth of energy - the bar is already moving. Physical, and it is
    # also what stops a two-tile rally sounding like a machine gun.
    restrike_seconds: float = 0.320
    restrike_floor: float = 0.46
    # And a global duck on duplicates only, by how many events are already
    # inside the window behind this one. Activations are never ducked: they are
    # the progress signal and the one thing that must not be buried.
    duck_window_seconds: float = 0.300
    duck_per_event: float = 0.115
    duck_floor: float = 0.55

    # --- the confirmation hold --------------------------------------------
    # "resonant": the final hit rings through the whole 0.92 s pause.
    # "breath":   the final hit decays out, leaving near-silence before the
    #             unlock.
    # "drone":    a restrained low sustain under the pause.
    confirmation: str = "resonant"
    final_decay_resonant: float = 0.620
    final_decay_breath: float = 0.145
    final_decay_drone: float = 0.300
    final_seconds_resonant: float = 1.700
    final_seconds_breath: float = 0.700
    final_seconds_drone: float = 0.950

    # --- the master -------------------------------------------------------
    # One fixed static gain for every seed and every variant, so two files can
    # be compared by ear, and a look-ahead limiter behind it that should never
    # have anything to do. A static gain cannot change the hierarchy; that is
    # the whole reason the chain has no compressor in it.
    #
    # 0.55 dB and not the 1.20 that was measured first. At 1.20 the loudest
    # seed of the five - 7541, where the gate's rise and the release happen to
    # come into phase - asked the limiter for 0.37 dB, and 6132 and 26267 for
    # a little less. That is a harmless amount of limiting in a harmless place
    # (after every activation, under the escape) but it is worth 0.5 LUFS to
    # be able to say the limiter did not act on anything rendered. The worst
    # raw peak over the five rendered seeds is 0.7999, which the ceiling
    # allows 0.639 dB of; this is 0.55. It stays in the chain as the
    # guarantee, not as a stage.
    master_gain_db: float = 0.55

    CONFIRMATIONS = ("resonant", "breath", "drone")

    def __post_init__(self) -> None:
        if self.fps <= 0.0:
            raise ScoreError("fps must be positive")
        if self.sample_rate <= 0:
            raise ScoreError("sample_rate must be positive")
        if self.root_hz <= 0.0:
            raise ScoreError("the root must be a positive frequency")
        if not self.scale or self.scale[0] != 0:
            raise ScoreError("the scale must start on its root")
        if list(self.scale) != sorted(set(self.scale)):
            raise ScoreError("the scale must be strictly ascending")
        if self.octaves < 1:
            raise ScoreError("the register must span at least one octave")
        if self.confirmation not in self.CONFIRMATIONS:
            raise ScoreError(
                f"unknown confirmation hold {self.confirmation!r}; "
                f"known: {list(self.CONFIRMATIONS)}"
            )
        # The hierarchy is a contract, not a preference. Phase 4 asserts the
        # same ordering on the visual response; a configuration that inverts it
        # is a bug in the configuration and is refused here rather than
        # rendered and listened to.
        order = (
            ("duplicate", self.duplicate_gain),
            ("activation", self.activation_gain),
            ("final", self.final_gain),
        )
        for (low_name, low), (high_name, high) in zip(order, order[1:]):
            if not low < high:
                raise ScoreError(
                    f"the hierarchy is inverted: {low_name} {low} is not below "
                    f"{high_name} {high}"
                )
        if not self.confirm_gain < self.activation_gain:
            raise ScoreError(
                "the confirmation sustain must sit below an activation"
            )
        if self.end_silence_seconds < 0.0:
            raise ScoreError("the end silence cannot be negative")
        if self.tilt_hz <= 0.0 or self.tilt_depth < 0.0:
            raise ScoreError("the small-speaker tilt must be a positive corner")
        if not 0.0 <= self.pan_depth <= 1.0:
            raise ScoreError("pan_depth must be in [0, 1]")
        if not 0.0 < self.restrike_floor <= 1.0:
            raise ScoreError("restrike_floor must be in (0, 1]")
        if not 0.0 < self.duck_floor <= 1.0:
            raise ScoreError("duck_floor must be in (0, 1]")

    @property
    def pitches(self) -> int:
        """How many distinct fundamentals the arena's vocabulary has."""
        return len(self.scale) * self.octaves + 1

    @property
    def final_decay(self) -> float:
        return {
            "resonant": self.final_decay_resonant,
            "breath": self.final_decay_breath,
            "drone": self.final_decay_drone,
        }[self.confirmation]

    @property
    def final_length_seconds(self) -> float:
        return {
            "resonant": self.final_seconds_resonant,
            "breath": self.final_seconds_breath,
            "drone": self.final_seconds_drone,
        }[self.confirmation]

    @property
    def has_confirm_layer(self) -> bool:
        return self.confirmation == "drone"

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in self.__dict__.items():
            out[key] = list(value) if isinstance(value, tuple) else value
        return out

    def fingerprint(self) -> str:
        """A short stable digest of every dial. Two schedules that share it
        were built by the same audio configuration."""
        blob = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


# The three previews the brief asks for, plus the fourth that completes the
# confirmation-hold comparison. They differ in as few dials as possible: V2 and
# V3 differ *only* in `confirmation`, and `v2_hold_breath` differs from V2 only
# in the same field, so the hold comparison is a controlled one.
CONFIGS: dict[str, AudioConfig] = {
    # V1. The event hierarchy on its own: five strengths, a stable per-tile
    # pitch that carries no spatial meaning, mono placement, no progression,
    # and the plainest hold. It is the control, and it is meant to sound
    # worse than V2 in a specific way rather than to sound bad.
    "v1_basic": AudioConfig(
        name="v1_basic",
        spatial_pitch=False,
        pan_depth=0.0,
        progression=False,
        confirmation="breath",
    ),
    # V2. The recommendation: spatial pitch, stereo placement by tile, the
    # progression, and the final hit ringing through the pause.
    "v2_refined": AudioConfig(name="v2_refined"),
    # V2 with hold B, for the comparison only.
    "v2_hold_breath": AudioConfig(name="v2_hold_breath", confirmation="breath"),
    # V3. V2 with hold C.
    "v3_hold_drone": AudioConfig(name="v3_hold_drone", confirmation="drone"),
}
DEFAULT_CONFIG = CONFIGS["v2_refined"]


def named_config(name: str, **overrides: Any) -> AudioConfig:
    if name not in CONFIGS:
        raise ScoreError(f"unknown audio config {name!r}; known: {sorted(CONFIGS)}")
    base = CONFIGS[name]
    return replace(base, **overrides) if overrides else base


# --------------------------------------------------------------------------
# The frame grid
# --------------------------------------------------------------------------


def frame_for(t: float, fps: float) -> int:
    """The first rendered frame that shows an event at time `t`.

    `tile_playback.activation_frames`' rule, for any contact rather than only
    for activations: frame `i` shows the world at `i / fps`, so an event at `t`
    is visible from `ceil(t * fps)`, with a guard for the float that sits a few
    ulp under an integer.
    """
    exact = t * fps
    if abs(exact - round(exact)) < 1.0e-9:
        return int(round(exact))
    return int(math.ceil(exact))


# --------------------------------------------------------------------------
# The musical mapping
# --------------------------------------------------------------------------


def pitch_table(config: AudioConfig = DEFAULT_CONFIG) -> tuple[float, ...]:
    """The vocabulary: every fundamental the arena can produce, ascending.

    Eleven notes for the shipped configuration - two octaves of a five-note
    scale plus the octave that closes it - over 220 to 880 Hz. Small on
    purpose. Fifty-one unrelated pitches would be fifty-one things to learn;
    eleven spread around the ring is a vocabulary, and four tiles sharing a
    note is what makes the arena sound like one instrument.
    """
    out = []
    for index in range(config.pitches):
        step = config.scale[index % len(config.scale)]
        octave = index // len(config.scale)
        out.append(config.root_hz * 2.0 ** ((step + 12 * octave) / 12.0))
    return tuple(out)


def _midpoints(arena: dict[str, Any]) -> list[tuple[float, float]]:
    return [(float(t["midpoint"][0]), float(t["midpoint"][1]))
            for t in arena["tiles"]]


def pitch_index_for(arena: dict[str, Any],
                    tile: int,
                    config: AudioConfig = DEFAULT_CONFIG) -> int:
    """Which note tile `tile` speaks with. A function of the arena, not the run.

    **Spatial mapping** (shipped): the tile's height in the arena, normalised
    over every tile's midpoint and quantised onto the vocabulary. Up is high.
    That gives the ring a shape a viewer never has to be taught - neighbouring
    walls are neighbouring notes, the left and right flanks mirror each other,
    and the ball working its way round the bottom of the arena is audibly in
    the bass. On the shipped 17-gon it distributes 51 tiles over 11 notes with
    two to eight tiles each and no note unused.

    **Index mapping** (V1 control): `tile % pitches`. Just as stable and just
    as deterministic, and deliberately without any of the above - the top of
    the arena and the bottom share notes at random, and the ring has a seam
    where the wrap lands.
    """
    total = len(arena["tiles"])
    if not 0 <= tile < total:
        raise ScoreError(f"tile {tile} is outside an arena of {total}")
    if not config.spatial_pitch:
        return tile % config.pitches
    points = _midpoints(arena)
    lowest = min(y for _, y in points)
    highest = max(y for _, y in points)
    span = highest - lowest
    if span <= 0.0:
        return 0
    unit = (points[tile][1] - lowest) / span
    return int(round(unit * (config.pitches - 1)))


def frequency_for(arena: dict[str, Any],
                  tile: int,
                  config: AudioConfig = DEFAULT_CONFIG) -> float:
    return pitch_table(config)[pitch_index_for(arena, tile, config)]


def pan_for(arena: dict[str, Any],
            tile: int,
            config: AudioConfig = DEFAULT_CONFIG) -> float:
    """Where the tile sits in the stereo field, by the x of its midpoint.

    The midpoint and not the contact point, because a tile's sound is its
    identity: the same wall has to arrive from the same place every time it is
    struck, or the arena stops being a fixed object.
    """
    if config.pan_depth <= 0.0:
        return 0.0
    points = _midpoints(arena)
    widest = max(abs(x) for x, _ in points) or 1.0
    return max(-1.0, min(1.0, points[tile][0] / widest)) * config.pan_depth


# --------------------------------------------------------------------------
# Events
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AudioEvent:
    """One sounding thing, placed on the render clock and on the frame grid."""

    kind: str
    # Where the picture puts it: the canonical render instant.
    render_seconds: float
    # The frame that first shows it, and that frame's own instant - which is
    # where the sound is actually placed. See the module docstring.
    frame: int
    at_seconds: float
    gain: float
    pan: float
    # Tile events only.
    tile: int | None = None
    side: int | None = None
    slot: int | None = None
    pitch_index: int | None = None
    freq: float | None = None
    # `count / total` at this instant, from the document's own ledger.
    progress: float = 0.0
    # What the two dampers did, kept so a schedule explains its own levels.
    restrike_scale: float = 1.0
    duck_scale: float = 1.0
    # Seconds since this tile was last struck, or None for a first contact.
    since_tile_seconds: float | None = None
    # How long the state this event belongs to lasts, in render seconds. Only
    # the climax events carry it, and only the unlock uses it: the gate's rise
    # is as long as the gate takes to retract, so a re-timed ending re-times
    # the sound of it without either side being edited.
    duration_seconds: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "render_seconds": self.render_seconds,
            "frame": self.frame,
            "at_seconds": self.at_seconds,
            "gain": self.gain,
            "pan": self.pan,
            "tile": self.tile,
            "side": self.side,
            "slot": self.slot,
            "pitch_index": self.pitch_index,
            "freq": self.freq,
            "progress": self.progress,
            "restrike_scale": self.restrike_scale,
            "duck_scale": self.duck_scale,
            "since_tile_seconds": self.since_tile_seconds,
            "duration_seconds": self.duration_seconds,
        }


@dataclass(frozen=True)
class AudioSchedule:
    """Everything `tile_audio` needs, and nothing it could use to re-simulate."""

    seed: int
    digest: str
    config: AudioConfig
    events: tuple[AudioEvent, ...]
    beats: dict[str, float]
    total_render_seconds: float
    frames: int
    total_seconds: float
    total_samples: int
    completed: bool
    metrics: dict[str, Any] = field(default_factory=dict)

    def of_kind(self, kind: str) -> tuple[AudioEvent, ...]:
        return tuple(event for event in self.events if event.kind == kind)

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": SCORE_FORMAT,
            "kind": "category3_tile_escape_score",
            "seed": self.seed,
            "playback_digest": self.digest,
            "config": self.config.as_dict(),
            "config_fingerprint": self.config.fingerprint(),
            "completed": self.completed,
            "beats": dict(self.beats),
            "total_render_seconds": self.total_render_seconds,
            "frames": self.frames,
            "total_seconds": self.total_seconds,
            "total_samples": self.total_samples,
            "metrics": self.metrics,
            "events": [event.as_dict() for event in self.events],
        }

    def fingerprint(self) -> str:
        """A digest over the schedule alone. Determinism, in one line."""
        blob = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _beats(document: dict[str, Any]) -> dict[str, float]:
    """The climax instants, read out of the timeline by state name.

    Not derived from the timing preset, and not recomputed: Phase 4 owns those
    offsets and the score's job is to land on them.
    """
    completion = document.get("completion")
    if not completion:
        return {}
    by_state = {segment["state"]: segment for segment in completion["timeline"]}
    missing = [name for name in CLIMAX_BEATS if name not in by_state]
    if missing:
        raise ScoreError(
            f"the completion block has no {missing} segment; this score cannot "
            "place the ending without the timeline that defines it"
        )
    return {name: float(by_state[name]["render_start"]) for name in CLIMAX_BEATS}


def _check_locked(document: dict[str, Any]) -> None:
    """The one assumption the collision placement rests on."""
    completion = document.get("completion")
    if not completion:
        return
    locked = completion["timeline"][0]
    if locked["state"] != "locked":
        raise ScoreError("the timeline does not begin in the locked state")
    if locked["sim_rate"] != 1.0 or locked["sim_start"] != 0.0:
        raise ScoreError(
            "the locked segment is not the identity map, so a collision's "
            "simulation time is not its render time and this score would be "
            "placed against the wrong picture"
        )


def schedule(document: dict[str, Any],
             config: AudioConfig = DEFAULT_CONFIG) -> AudioSchedule:
    """The whole soundtrack as data, on the render clock.

    Reads `collisions`, `activations`, `arena` and `completion` and writes
    nothing back: `document` is not mutated and could be a read-only mapping.
    """
    if document.get("kind") != "category3_tile_escape_playback":
        raise ScoreError("not a tile-escape playback document")
    _check_locked(document)
    arena = document["arena"]
    total_tiles = int(document["total_tiles"])
    beats = _beats(document)
    completed = bool(document.get("completed")) and bool(beats)

    freqs = [frequency_for(arena, index, config) for index in range(total_tiles)]
    pitch_indices = [pitch_index_for(arena, index, config)
                     for index in range(total_tiles)]
    pans = [pan_for(arena, index, config) for index in range(total_tiles)]

    events: list[AudioEvent] = []
    last_struck: dict[int, float] = {}
    recent: list[float] = []          # render times, for the density duck
    final_render: float | None = None

    for hit in document["collisions"]:
        t = float(hit["t"])
        tile = int(hit["tile"])
        is_new = bool(hit["new"])
        count = int(hit["count"])
        is_final = is_new and count >= total_tiles

        # The density duck: how many contacts are already inside the window
        # behind this one. Computed on the canonical times, so it does not move
        # when the frame grid does.
        while recent and t - recent[0] > config.duck_window_seconds:
            recent.pop(0)
        crowd = len(recent)
        recent.append(t)

        since = None if tile not in last_struck else t - last_struck[tile]
        last_struck[tile] = t

        restrike = 1.0
        duck = 1.0
        if is_final:
            kind = "final"
            gain = config.final_gain
        elif is_new:
            kind = "activation"
            progress_here = (count - 1) / max(1, total_tiles - 1)
            gain = config.activation_gain
            if config.progression:
                gain += config.gain_growth * progress_here
        else:
            kind = "duplicate"
            gain = config.duplicate_gain
            if since is not None and since < config.restrike_seconds:
                # Linear from the floor at zero separation to 1.0 at the
                # window's edge. Linear rather than exponential because what is
                # being modelled is "how much of the last one is still in the
                # air", and the envelope it is standing in for is already
                # exponential.
                restrike = config.restrike_floor + (
                    (1.0 - config.restrike_floor) * (since / config.restrike_seconds)
                )
            duck = max(config.duck_floor,
                       1.0 / (1.0 + config.duck_per_event * crowd))
            gain *= restrike * duck

        frame = frame_for(t, config.fps)
        events.append(AudioEvent(
            kind=kind,
            render_seconds=t,
            frame=frame,
            at_seconds=frame / config.fps,
            gain=gain,
            pan=pans[tile],
            tile=tile,
            side=int(hit["side"]),
            slot=int(hit["slot"]),
            pitch_index=pitch_indices[tile],
            freq=freqs[tile],
            progress=count / total_tiles,
            restrike_scale=restrike,
            duck_scale=duck,
            since_tile_seconds=since,
        ))
        if is_final:
            final_render = t

    if completed:
        # The final hit is already in the list, from the collision that caused
        # it. That it lands on the `final_hit` segment's own render start is a
        # property of Phase 4's timeline, and it is checked rather than assumed
        # - if it ever stopped being true, the detonation would be scheduled
        # against a picture that had already moved on.
        if final_render is None:
            raise ScoreError(
                f"seed {document['seed']}: the document says the run completed "
                "but no collision activated the last tile"
            )
        if abs(final_render - beats["final_hit"]) > 1.0e-9:
            raise ScoreError(
                f"the last activation is at {final_render} but the ending's "
                f"final_hit segment starts at {beats['final_hit']}"
            )
        final_tile = int(document["completion"]["final_tile"])

        if config.has_confirm_layer:
            frame = frame_for(beats["confirming"], config.fps)
            events.append(AudioEvent(
                kind="confirm",
                render_seconds=beats["confirming"],
                frame=frame,
                at_seconds=frame / config.fps,
                gain=config.confirm_gain,
                pan=0.0,
                pitch_index=0,
                freq=config.root_hz,
                progress=1.0,
            ))

        # The unlock rises from the tile that was just struck to the top of the
        # register: the gate opening is caused by that tile, and the sweep is
        # the causal line drawn between them. Its rise is exactly as long as
        # the `unlocking` segment - the time the gate section takes to flare
        # and retract - so the rise tops out as the opening completes, and a
        # re-timed ending carries the sound with it.
        gate_seconds = beats["escaping"] - beats["unlocking"]
        frame = frame_for(beats["unlocking"], config.fps)
        events.append(AudioEvent(
            kind="unlock",
            render_seconds=beats["unlocking"],
            frame=frame,
            at_seconds=frame / config.fps,
            gain=config.unlock_gain,
            pan=0.0,
            tile=final_tile,
            pitch_index=pitch_indices[final_tile],
            freq=freqs[final_tile],
            progress=1.0,
            duration_seconds=gate_seconds,
        ))

        # The release follows the ball out. Half depth, because the pad is the
        # piece's resolution and a resolution that arrives from one side is a
        # sound effect; a quarter of the field is enough to say which way the
        # ball went without moving the chord off centre.
        route = document["completion"]["route"]
        exit_x = float(route["exit_position"][0])
        half_width = float(route["frame_half_width_wu"]) or 1.0
        escape_pan = (max(-1.0, min(1.0, exit_x / half_width))
                      * config.pan_depth * 0.5)
        frame = frame_for(beats["escaping"], config.fps)
        escape_at = frame / config.fps
        events.append(AudioEvent(
            kind="escape",
            render_seconds=beats["escaping"],
            frame=frame,
            at_seconds=escape_at,
            gain=config.escape_gain,
            pan=escape_pan,
            pitch_index=0,
            freq=config.root_hz,
            progress=1.0,
            # Filled in below, once the video's length is known.
            duration_seconds=None,
        ))

    events.sort(key=lambda event: (event.at_seconds, EVENT_KINDS.index(event.kind)))

    if completed:
        total_render = float(document["completion"]["total_render_seconds"])
    else:
        total_render = float(document["end_seconds"])
    # The video is frames 0..round(duration * fps) inclusive - the range
    # `tile_escape_render.gd` writes - so it is that many plus one frames long
    # and the soundtrack is exactly as long as the video it sits under.
    frames = int(round(total_render * config.fps)) + 1
    total_seconds = frames / config.fps
    total_samples = int(round(total_seconds * config.sample_rate))

    if completed:
        # The release lasts exactly as long as there is video left for it,
        # less the silence the ending is supposed to finish in. It cannot be a
        # constant: the escape segment's own length is `exit_seconds /
        # escape_rate` and that varies by seed - 0.99 s on 3530 and 0.62 s on
        # 37169 - so a fixed pad overruns the last frame on some seeds and not
        # on others.
        for index, event in enumerate(events):
            if event.kind != "escape":
                continue
            room = total_seconds - event.at_seconds - config.end_silence_seconds
            events[index] = replace(
                event,
                duration_seconds=max(0.10, min(config.escape_seconds, room)),
            )

    return AudioSchedule(
        seed=int(document["seed"]),
        digest=str(document["digest"]),
        config=config,
        events=tuple(events),
        beats=beats,
        total_render_seconds=total_render,
        frames=frames,
        total_seconds=total_seconds,
        total_samples=total_samples,
        completed=completed,
        metrics=schedule_metrics(tuple(events), total_seconds, config),
    )


def schedule_metrics(events: Sequence[AudioEvent],
                     total_seconds: float,
                     config: AudioConfig) -> dict[str, Any]:
    """Density readings taken on the schedule, before a sample exists.

    Overlap here is a statement about envelopes, not about the mix: an event is
    counted as sounding for as long as its own cue lasts, so `max_overlap` is
    the largest number of cues that are simultaneously non-zero. The mix's own
    measured polyphony is in `tile_audio`, and the two are different questions -
    this one is what the score asked for, that one is what the waveform did.
    """
    lengths = {
        "duplicate": config.duplicate_seconds,
        "activation": config.activation_seconds,
        "final": config.final_length_seconds,
        "confirm": 0.95,
        "unlock": config.unlock_seconds,
        "escape": config.escape_seconds,
    }
    counts: dict[str, int] = {kind: 0 for kind in EVENT_KINDS}
    for event in events:
        counts[event.kind] += 1

    spans = sorted(
        (event.at_seconds,
         event.at_seconds + (event.duration_seconds
                             if event.kind == "escape" and event.duration_seconds
                             else lengths[event.kind]))
        for event in events)
    max_overlap, overlap_at = 0, 0.0
    ends: list[float] = []
    for start, stop in spans:
        ends = [end for end in ends if end > start]
        ends.append(stop)
        if len(ends) > max_overlap:
            max_overlap, overlap_at = len(ends), start

    gaps = [b.at_seconds - a.at_seconds for a, b in zip(events, events[1:])]
    body = [event for event in events
            if event.kind in ("duplicate", "activation", "final")]
    body_span = (body[-1].at_seconds - body[0].at_seconds) if len(body) > 1 else 0.0
    return {
        "events": len(events),
        "by_kind": counts,
        "events_per_second": round(len(body) / body_span, 4) if body_span else 0.0,
        "max_scheduled_overlap": max_overlap,
        "max_overlap_at_seconds": round(overlap_at, 4),
        "min_gap_seconds": round(min(gaps), 6) if gaps else 0.0,
        "median_gap_seconds": round(sorted(gaps)[len(gaps) // 2], 6) if gaps else 0.0,
        "longest_silence_seconds": round(max(gaps), 6) if gaps else 0.0,
        "total_seconds": round(total_seconds, 6),
    }


def schedule_document(document: dict[str, Any],
                      config: AudioConfig = DEFAULT_CONFIG) -> dict[str, Any]:
    """`schedule`, as the JSON sidecar the CLI writes."""
    return schedule(document, config).as_dict()

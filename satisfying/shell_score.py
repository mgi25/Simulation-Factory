"""Deterministic musical scoring for Category 3 Test #2.

This is the middle layer between the frozen shell-escape playback document
and sample synthesis.  It reads canonical events and emits musical decisions;
it imports neither the simulator nor the synthesiser.  That boundary is the
guarantee that audio can describe physics but can never influence it.

The arena is one related instrument.  Its six shells use increasingly bright
registers in a D/A pentatonic family, while collision height selects a degree
inside the shell's register.  Physical state supplies expression: impact and
incidence drive dynamics, posts sharpen the attack, a real near miss adds a
brief unresolved neighbour, accumulated panel damage opens the spectrum,
breaks bloom into a chord, first-time outward crossings lift the harmony, and
the final escape resolves to D.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Mapping, Sequence


SCORE_VERSION = "category3-test2-shell-audio-score/1.0.0"
PLAYBACK_VERSION = "category3-test2-shell-escape-playback/1.0.0"
SCHEMA_VERSION = "category3-test2-shell-escape/1.0.0"
CONFIG_DIGEST = "7da0cbc80d5958260b65417c1ac94fac2285471aaf8adc4f093b27e3445afb3e"

# D major pentatonic, expressed from A: A, B, D, E, F#.  Unlike Test #1's
# A-minor system it has a bright major colour, while still avoiding semitones
# and tritones under arbitrary ordering.
PENTATONIC: tuple[int, ...] = (0, 2, 5, 7, 9)
SHELL_TRANSPOSITIONS: tuple[int, ...] = (0, 4, 7, 12, 16, 19)
EVENT_KINDS: tuple[str, ...] = ("collision", "break", "transition", "escape")


class ScoreError(ValueError):
    """The canonical document or audio configuration cannot be scored."""


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return min(high, max(low, value))


@dataclass(frozen=True)
class AudioConfig:
    """Every score and synthesis dial that identifies a waveform."""

    name: str = "refined_hybrid"
    sample_rate: int = 48_000
    root_hz: float = 220.0
    scale: tuple[int, ...] = PENTATONIC
    shell_transpositions: tuple[int, ...] = SHELL_TRANSPOSITIONS
    pan_depth: float = 0.30

    collision_gain_low: float = 0.105
    collision_gain_high: float = 0.205
    collision_seconds: float = 0.165
    collision_decay: float = 0.082
    resonance: float = 0.34
    transient: float = 0.17
    brightness: float = 0.52
    damage_colour: float = 0.30
    near_miss_colour: float = 0.22

    break_gain: float = 0.305
    break_seconds: float = 0.390
    transition_gain: float = 0.235
    transition_seconds: float = 0.285
    escape_gain: float = 0.390
    escape_seconds: float = 0.660
    tail_seconds: float = 0.820
    end_silence_seconds: float = 0.150

    # A single static output gain.  No compressor, limiter, or adaptive stage.
    master_gain: float = 1.35
    peak_ceiling_dbfs: float = -2.5

    def __post_init__(self) -> None:
        if self.sample_rate != 48_000:
            raise ScoreError("shell audio is mastered at 48 kHz")
        if len(self.scale) < 4 or len(self.shell_transpositions) != 6:
            raise ScoreError("the tonal system needs five-ish degrees and six shell registers")
        if not 0.0 <= self.pan_depth <= 0.6:
            raise ScoreError("pan depth must preserve a strong mono centre")
        if self.end_silence_seconds >= self.tail_seconds:
            raise ScoreError("the ending needs sound before its final silence")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def fingerprint(self) -> str:
        payload = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


CONFIGS: dict[str, AudioConfig] = {
    "clean_percussive": AudioConfig(
        name="clean_percussive",
        collision_seconds=0.115,
        collision_decay=0.052,
        resonance=0.16,
        transient=0.23,
        brightness=0.42,
        damage_colour=0.18,
        near_miss_colour=0.18,
        break_seconds=0.310,
        transition_seconds=0.235,
    ),
    "resonant_musical": AudioConfig(
        name="resonant_musical",
        collision_gain_low=0.095,
        collision_gain_high=0.185,
        collision_seconds=0.245,
        collision_decay=0.125,
        resonance=0.58,
        transient=0.12,
        brightness=0.57,
        damage_colour=0.38,
        near_miss_colour=0.25,
        break_seconds=0.470,
        transition_seconds=0.350,
    ),
    "refined_hybrid": AudioConfig(),
}
DEFAULT_CONFIG = CONFIGS["refined_hybrid"]


def named_config(name: str, **overrides: Any) -> AudioConfig:
    if name not in CONFIGS:
        raise ScoreError(f"unknown audio config {name!r}; known: {sorted(CONFIGS)}")
    return replace(CONFIGS[name], **overrides) if overrides else CONFIGS[name]


@dataclass(frozen=True)
class AudioEvent:
    kind: str
    source_seconds: float
    sample_offset: int
    gain: float
    pan: float
    frequency_hz: float
    shell_id: int
    panel_id: int | None = None
    pitch_degree: int = 0
    impact: float = 0.0
    incidence: float = 0.0
    feature: str | None = None
    near_miss: bool = False
    near_miss_direction: int = 0
    damage: float = 0.0
    method: str | None = None
    progress: float = 0.0

    @property
    def at_seconds(self) -> float:
        return self.sample_offset / 48_000.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AudioSchedule:
    seed: int
    playback_digest: str
    config: AudioConfig
    events: tuple[AudioEvent, ...]
    total_seconds: float
    total_samples: int
    metrics: dict[str, Any] = field(default_factory=dict)

    def of_kind(self, kind: str) -> tuple[AudioEvent, ...]:
        return tuple(event for event in self.events if event.kind == kind)

    def as_dict(self) -> dict[str, Any]:
        return {
            "score_version": SCORE_VERSION,
            "kind": "category3_shell_escape_audio_score",
            "seed": self.seed,
            "playback_digest": self.playback_digest,
            "config": self.config.as_dict(),
            "config_fingerprint": self.config.fingerprint(),
            "total_seconds": self.total_seconds,
            "total_samples": self.total_samples,
            "metrics": self.metrics,
            "events": [event.as_dict() for event in self.events],
        }

    def fingerprint(self) -> str:
        payload = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_document(document: Mapping[str, Any]) -> None:
    if document.get("document_version") != PLAYBACK_VERSION:
        raise ScoreError("not the frozen Test #2 playback document")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ScoreError("the Test #2 event schema is not the frozen 1.0.0 schema")
    if document.get("config_digest") != CONFIG_DIGEST:
        raise ScoreError("the playback was not made with frozen config 7da0cbc80d595826")
    if not isinstance(document.get("events"), list) or not document.get("shells"):
        raise ScoreError("the playback document has no canonical events or shells")


def pitch_degree_for(position: Sequence[float], radius: float, scale_size: int = 5) -> int:
    """Map collision height to a stable low-to-high pentatonic degree."""
    if radius <= 0.0 or scale_size < 2:
        raise ScoreError("pitch mapping needs a positive radius and at least two degrees")
    vertical = _clamp(float(position[1]) / radius, -1.0, 1.0)
    return int(round((vertical + 1.0) * 0.5 * (scale_size - 1)))


def frequency_for(shell_id: int, degree: int, config: AudioConfig = DEFAULT_CONFIG) -> float:
    if not 0 <= shell_id < len(config.shell_transpositions):
        raise ScoreError(f"shell_id {shell_id} is outside the six-shell instrument")
    if not 0 <= degree < len(config.scale):
        raise ScoreError(f"pitch degree {degree} is outside the palette")
    semitones = config.shell_transpositions[shell_id] + config.scale[degree]
    return config.root_hz * 2.0 ** (semitones / 12.0)


def _pan(position: Sequence[float], radius: float, config: AudioConfig) -> float:
    return _clamp(float(position[0]) / max(radius, 1e-9), -1.0, 1.0) * config.pan_depth


def _sample_at(seconds: float, sample_rate: int) -> int:
    return int(round(seconds * sample_rate))


def _index_by_collision(events: Sequence[Mapping[str, Any]], kind: str) -> dict[tuple[float, int, int], Mapping[str, Any]]:
    indexed: dict[tuple[float, int, int], Mapping[str, Any]] = {}
    for event in events:
        if event.get("kind") == kind:
            indexed[(float(event["t"]), int(event["shell_id"]), int(event["panel_id"]))] = event
    return indexed


def schedule(document: Mapping[str, Any], config: AudioConfig = DEFAULT_CONFIG) -> AudioSchedule:
    """Translate canonical events into a deterministic musical schedule."""
    _validate_document(document)
    canonical = document["events"]
    shells = {int(shell["shell_id"]): shell for shell in document["shells"]}
    damage_at = _index_by_collision(canonical, "damage")
    near_at = _index_by_collision(canonical, "near_miss")
    break_at = _index_by_collision(canonical, "panel_break")

    events: list[AudioEvent] = []
    last_panel_hit: dict[tuple[int, int], float] = {}
    max_region = 0

    for source in canonical:
        kind = str(source["kind"])
        t = float(source["t"])
        if kind == "collision":
            shell_id = int(source["shell_id"])
            panel_id = int(source["panel_id"])
            shell = shells[shell_id]
            position = source["position"]
            degree = pitch_degree_for(position, float(shell["radius"]), len(config.scale))
            frequency = frequency_for(shell_id, degree, config)
            impact = _clamp(float(source["impact_speed"]) / 20.0)
            incidence = _clamp(float(source["incidence"]) / 1.15)
            gain = config.collision_gain_low + (
                config.collision_gain_high - config.collision_gain_low
            ) * (0.62 * math.sqrt(impact) + 0.38 * incidence)

            panel_key = (shell_id, panel_id)
            previous = last_panel_hit.get(panel_key)
            if previous is not None and t - previous < 0.11:
                gain *= 0.78 + 2.0 * max(0.0, t - previous)
            last_panel_hit[panel_key] = t

            lookup = (t, shell_id, panel_id)
            damage_event = damage_at.get(lookup)
            near_event = near_at.get(lookup)
            damage = 0.0
            if damage_event:
                damage = _clamp(
                    float(damage_event["cumulative"]) / float(damage_event["threshold"])
                )
            direction = 0
            if near_event:
                lead = float(near_event["signed_lead"])
                direction = 1 if lead > 0.0 else -1 if lead < 0.0 else 0

            events.append(AudioEvent(
                kind="collision",
                source_seconds=t,
                sample_offset=_sample_at(t, config.sample_rate),
                gain=gain,
                pan=_pan(position, float(shell["radius"]), config),
                frequency_hz=frequency,
                shell_id=shell_id,
                panel_id=panel_id,
                pitch_degree=degree,
                impact=impact,
                incidence=incidence,
                feature=str(source["feature"]),
                near_miss=near_event is not None,
                near_miss_direction=direction,
                damage=damage,
                progress=shell_id / 5.0,
            ))

            if lookup in break_at:
                events.append(AudioEvent(
                    kind="break",
                    source_seconds=t,
                    sample_offset=_sample_at(t, config.sample_rate),
                    gain=config.break_gain * (0.92 + 0.08 * shell_id / 5.0),
                    pan=_pan(position, float(shell["radius"]), config) * 0.55,
                    frequency_hz=frequency,
                    shell_id=shell_id,
                    panel_id=panel_id,
                    pitch_degree=degree,
                    impact=impact,
                    incidence=incidence,
                    feature=str(source["feature"]),
                    damage=1.0,
                    progress=shell_id / 5.0,
                ))

        elif kind == "shell_exit":
            to_region = int(source["to_region"])
            if to_region > max_region:
                max_region = to_region
                shell_id = int(source["shell_id"])
                shell = shells[shell_id]
                position = source["position"]
                degree = min(len(config.scale) - 1, 1 + shell_id * 3 // 5)
                events.append(AudioEvent(
                    kind="transition",
                    source_seconds=t,
                    sample_offset=_sample_at(t, config.sample_rate),
                    gain=config.transition_gain * (0.90 + 0.10 * to_region / 6.0),
                    pan=_pan(position, float(shell["radius"]), config) * 0.45,
                    frequency_hz=frequency_for(shell_id, degree, config),
                    shell_id=shell_id,
                    panel_id=int(source["panel_id"]),
                    pitch_degree=degree,
                    method=str(source["method"]),
                    progress=to_region / 6.0,
                ))

        elif kind == "escape":
            shell_id = int(source["shell_id"])
            shell = shells[shell_id]
            position = source["position"]
            events.append(AudioEvent(
                kind="escape",
                source_seconds=t,
                sample_offset=_sample_at(t, config.sample_rate),
                gain=config.escape_gain,
                pan=_pan(position, float(shell["radius"]), config) * 0.25,
                # Resolve to D5: the tonal centre of the chosen D-major family.
                frequency_hz=config.root_hz * 2.0 ** (5.0 / 12.0 + 1.0),
                shell_id=shell_id,
                method=str(source["method"]),
                progress=1.0,
            ))

    priority = {kind: index for index, kind in enumerate(EVENT_KINDS)}
    events.sort(key=lambda event: (event.sample_offset, priority[event.kind]))
    if not events or not any(event.kind == "escape" for event in events):
        raise ScoreError("audio previews require a successful canonical escape run")

    final_source = max(float(document["summary"]["duration"]), events[-1].source_seconds)
    total_samples = _sample_at(final_source + config.tail_seconds, config.sample_rate)
    total_seconds = total_samples / config.sample_rate
    metrics = schedule_metrics(events, total_seconds, config)
    return AudioSchedule(
        seed=int(document["seed"]),
        playback_digest=str(document["digest"]),
        config=config,
        events=tuple(events),
        total_seconds=total_seconds,
        total_samples=total_samples,
        metrics=metrics,
    )


def schedule_metrics(events: Sequence[AudioEvent], total_seconds: float,
                     config: AudioConfig) -> dict[str, Any]:
    lengths = {
        "collision": config.collision_seconds,
        "break": config.break_seconds,
        "transition": config.transition_seconds,
        "escape": config.escape_seconds,
    }
    counts = {kind: sum(event.kind == kind for event in events) for kind in EVENT_KINDS}
    collision_times = [event.source_seconds for event in events if event.kind == "collision"]
    edges: list[tuple[float, int]] = []
    for event in events:
        edges.append((event.source_seconds, 1))
        edges.append((event.source_seconds + lengths[event.kind], -1))
    edges.sort(key=lambda edge: (edge[0], edge[1]))  # ends before starts
    live = 0
    max_overlap = 0
    overlap_at = 0.0
    overlap_seconds = 0.0
    previous = edges[0][0] if edges else 0.0
    index = 0
    while index < len(edges):
        at = edges[index][0]
        if live >= 2:
            overlap_seconds += at - previous
        while index < len(edges) and edges[index][0] == at:
            live += edges[index][1]
            index += 1
        if live > max_overlap:
            max_overlap, overlap_at = live, at
        previous = at
    gaps = [b - a for a, b in zip(collision_times, collision_times[1:])]
    return {
        "events": len(events),
        "by_kind": counts,
        "collision_density_hz": round(len(collision_times) / max(collision_times[-1], 1e-9), 4),
        "near_miss_collisions": sum(event.near_miss for event in events),
        "max_scheduled_polyphony": max_overlap,
        "max_polyphony_at_seconds": round(overlap_at, 6),
        "estimated_overlap_seconds": round(overlap_seconds, 6),
        "median_collision_gap_seconds": round(sorted(gaps)[len(gaps) // 2], 6) if gaps else 0.0,
        "minimum_collision_gap_seconds": round(min(gaps), 6) if gaps else 0.0,
        "total_seconds": round(total_seconds, 6),
    }


def score_document(document: Mapping[str, Any],
                   config: AudioConfig = DEFAULT_CONFIG) -> dict[str, Any]:
    return schedule(document, config).as_dict()

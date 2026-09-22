"""Deterministic audiovisual integration for Category 3 Test #2.

This module joins the already-proven Phase 2A visual consumer and Phase 2B
musical consumer.  It does not simulate.  Both sides receive the same frozen
playback document, and the audit below measures the only unavoidable timing
difference: an event can occur between two rendered video frames while audio
is placed on the 48 kHz sample grid.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from satisfying import shell_score, shell_visual


INTEGRATION_VERSION = "category3-test2-shell-av-integration/1.0.0"
BASE_SHA = "42cdbb34588f052be45377d7c20c89d8100fcf99"
VISUAL_SHA = "8dc61c27d9f9c2a8e848239771a33adf4d1a7b35"
AUDIO_SHA = "0c8ce1f8132b3ec6188dd53ec931af4717f5c9f9"
CANDIDATE_SEEDS: tuple[int, ...] = (9589, 11929, 3654, 7699)
PRIMARY_REFERENCE_SEED = 9589


class AVIntegrationError(ValueError):
    """The two playback consumers cannot be proven to share one timeline."""


@dataclass(frozen=True)
class AVConfig:
    """Every integration dial that can change a preview or its identity."""

    hook: str = "CAN THE BALL ESCAPE?"
    audio: str = "refined_hybrid"
    review_width: int = 540
    review_height: int = 960
    review_fps: int = 30
    full_width: int = 1080
    full_height: int = 1920
    full_fps: int = 60
    video_codec: str = "libx264"
    review_crf: int = 20
    full_crf: int = 17
    preset: str = "slow"
    pixel_format: str = "yuv420p"
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"
    audio_sample_rate: int = 48_000
    final_frame_padding: str = "clone_to_audio_end"

    def __post_init__(self) -> None:
        if self.audio != "refined_hybrid":
            raise AVIntegrationError("Phase 3 is locked to refined_hybrid")
        if self.hook != "CAN THE BALL ESCAPE?":
            raise AVIntegrationError("Phase 3 must preserve the selected hook")
        for width, height, fps in (
            (self.review_width, self.review_height, self.review_fps),
            (self.full_width, self.full_height, self.full_fps),
        ):
            if width <= 0 or height <= width or fps <= 0:
                raise AVIntegrationError("preview profiles must be positive 9:16 video")
        if self.audio_sample_rate != 48_000:
            raise AVIntegrationError("the selected score is mastered at 48 kHz")

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def fingerprint(self) -> str:
        blob = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


CONFIG = AVConfig()


def event_order_digest(document: Mapping[str, Any]) -> str:
    """Digest the complete canonical event sequence without rewriting it."""
    blob = json.dumps(document["events"], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def validate_shared_document(document: Mapping[str, Any]) -> None:
    """Apply both completed branches' frozen input contracts."""
    shell_visual.validate_document(dict(document))
    # Scheduling is validation by the audio branch and remains pure.
    shell_score.schedule(document, shell_score.named_config(CONFIG.audio))


def identity(document: Mapping[str, Any], config: AVConfig = CONFIG) -> dict[str, Any]:
    validate_shared_document(document)
    audio_config = shell_score.named_config(config.audio)
    return {
        "format": INTEGRATION_VERSION,
        "base_sha": BASE_SHA,
        "visual_sha": VISUAL_SHA,
        "audio_sha": AUDIO_SHA,
        "seed": int(document["seed"]),
        "schema_version": str(document["schema_version"]),
        "frozen_config_digest": str(document["config_digest"]),
        "playback_digest": str(document["digest"]),
        "event_order_digest": event_order_digest(document),
        "visual_config_digest": shell_visual.render_config_digest(),
        "audio_config": config.audio,
        "audio_config_fingerprint": audio_config.fingerprint(),
        "integration_config": config.as_dict(),
        "integration_config_digest": config.fingerprint(),
    }


def _canonical_index(document: Mapping[str, Any]) -> dict[int, int]:
    return {id(event): index for index, event in enumerate(document["events"])}


def _event_key(event: Mapping[str, Any]) -> tuple[float, int, int]:
    return (
        float(event["t"]),
        int(event.get("shell_id", -1)),
        int(event.get("panel_id", -1)),
    )


def _first_outward_exits(document: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    result: list[Mapping[str, Any]] = []
    frontier = 0
    for event in document["events"]:
        if event["kind"] == "shell_exit" and int(event["to_region"]) > frontier:
            frontier = int(event["to_region"])
            result.append(event)
    return result


def _visual_time(seconds: float, fps: int) -> float:
    # The first output frame whose sampled scene time has reached the event.
    return math.ceil(seconds * fps - 1.0e-12) / fps


def _timing_group(times: Sequence[tuple[float, float]], fps: int) -> dict[str, Any]:
    errors = [abs(visual - audio) for visual, audio in times]
    maximum = max(errors, default=0.0)
    return {
        "count": len(times),
        "max_error_seconds": maximum,
        "max_error_frames": maximum * fps,
        "mean_error_seconds": sum(errors) / len(errors) if errors else 0.0,
        "within_one_frame": maximum <= 1.0 / fps + 1.0e-12,
    }


def sync_audit(
    document: Mapping[str, Any],
    visual_audit: Mapping[str, Any],
    fps: int,
    config: AVConfig = CONFIG,
) -> dict[str, Any]:
    """Prove shared identity, ordering, and A/V placement for every cue class."""
    validate_shared_document(document)
    plan = shell_score.schedule(document, shell_score.named_config(config.audio))
    canonical = document["events"]
    if int(visual_audit.get("seed", -1)) != int(document["seed"]):
        raise AVIntegrationError("visual audit seed differs from playback")

    visual_times = [float(value) for value in visual_audit.get("event_times", [])]
    visual_kinds = [str(value) for value in visual_audit.get("event_kinds", [])]
    source_times = [float(event["t"]) for event in canonical]
    source_kinds = [str(event["kind"]) for event in canonical]
    visual_time_error = max(
        (abs(actual - expected) for actual, expected in zip(visual_times, source_times)),
        default=0.0,
    )
    # Godot parses the same JSON doubles but its JSON writer may print a few
    # final decimal places differently.  Identity and ordinal position are
    # exact; the numeric round-trip is held to the Phase 2A 20 microsecond gate.
    visual_order_exact = (
        len(visual_times) == len(source_times)
        and visual_kinds == source_kinds
        and visual_time_error < 2.0e-5
    )

    collisions = [event for event in canonical if event["kind"] == "collision"]
    collision_by_key = {_event_key(event): event for event in collisions}
    near_by_key = {
        _event_key(event): event for event in canonical if event["kind"] == "near_miss"
    }
    break_by_key = {
        _event_key(event): event for event in canonical if event["kind"] == "panel_break"
    }
    outward = _first_outward_exits(document)
    outward_by_key = {_event_key(event): event for event in outward}
    escapes = [event for event in canonical if event["kind"] == "escape"]

    groups: dict[str, list[tuple[float, float]]] = {
        "collision": [],
        "post": [],
        "near_miss": [],
        "break": [],
        "shell_exit": [],
        "escape": [],
    }
    source_indices: list[int] = []
    canonical_indices = _canonical_index(document)
    mapping_ok = True
    for event in plan.events:
        panel_id = -1 if event.panel_id is None else int(event.panel_id)
        key = (float(event.source_seconds), int(event.shell_id), panel_id)
        source: Mapping[str, Any] | None = None
        group = event.kind
        if event.kind == "collision":
            source = collision_by_key.get(key)
            if source is not None:
                groups["collision"].append(
                    (_visual_time(float(source["t"]), fps), event.at_seconds)
                )
                if event.feature == "post":
                    groups["post"].append(
                        (_visual_time(float(source["t"]), fps), event.at_seconds)
                    )
                if event.near_miss:
                    mapping_ok = mapping_ok and key in near_by_key
                    groups["near_miss"].append(
                        (_visual_time(float(source["t"]), fps), event.at_seconds)
                    )
        elif event.kind == "break":
            source = break_by_key.get(key)
            if source is not None:
                groups["break"].append(
                    (_visual_time(float(source["t"]), fps), event.at_seconds)
                )
        elif event.kind == "transition":
            source = outward_by_key.get(key)
            if source is not None:
                groups["shell_exit"].append(
                    (_visual_time(float(source["t"]), fps), event.at_seconds)
                )
        elif event.kind == "escape":
            source = escapes[0] if escapes else None
            if source is not None:
                groups["escape"].append(
                    (_visual_time(float(source["t"]), fps), event.at_seconds)
                )
        mapping_ok = mapping_ok and source is not None
        if source is not None:
            source_indices.append(canonical_indices[id(source)])

    counts_ok = (
        len(groups["collision"]) == len(collisions)
        and len(groups["near_miss"]) == len(near_by_key)
        and len(groups["break"]) == len(break_by_key)
        and len(groups["shell_exit"]) == len(outward)
        and len(groups["escape"]) == 1
    )
    timing = {name: _timing_group(values, fps) for name, values in groups.items()}
    maximum = max((row["max_error_seconds"] for row in timing.values()), default=0.0)
    result = {
        "format": INTEGRATION_VERSION,
        "seed": int(document["seed"]),
        "fps": fps,
        "frame_seconds": 1.0 / fps,
        "playback_digest": str(document["digest"]),
        "visual_playback_digest": str(visual_audit.get("digest", "")),
        "score_playback_digest": plan.playback_digest,
        "event_order_digest": event_order_digest(document),
        "visual_event_order_exact": visual_order_exact,
        "visual_max_event_time_error_seconds": visual_time_error,
        "audio_source_order_shared": source_indices == sorted(source_indices),
        "mapping_complete": mapping_ok and counts_ok,
        "timing": timing,
        "maximum_sync_error_seconds": maximum,
        "maximum_sync_error_frames": maximum * fps,
        "within_one_rendered_frame": maximum <= 1.0 / fps + 1.0e-12,
        "score_fingerprint": plan.fingerprint(),
        "visual_config_digest": shell_visual.render_config_digest(),
        "integration_config_digest": config.fingerprint(),
    }
    result["pass"] = all((
        result["playback_digest"] == result["visual_playback_digest"],
        result["playback_digest"] == result["score_playback_digest"],
        result["visual_event_order_exact"],
        result["audio_source_order_shared"],
        result["mapping_complete"],
        result["within_one_rendered_frame"],
        all(row["within_one_frame"] for row in timing.values()),
    ))
    return result


def experience_metrics(document: Mapping[str, Any]) -> dict[str, Any]:
    """High-signal pacing facts used alongside watching and listening."""
    validate_shared_document(document)
    plan = shell_score.schedule(document, shell_score.named_config(CONFIG.audio))
    duration = float(document["summary"]["duration"])
    boundaries = (
        ("opening", 0.0, duration * 0.25),
        ("middle", duration * 0.25, duration * 0.65),
        ("late", duration * 0.65, duration),
    )
    segments: dict[str, Any] = {}
    for name, start, end in boundaries:
        events = [event for event in document["events"]
                  if start <= float(event["t"]) < end]
        segments[name] = {
            "start": round(start, 6),
            "end": round(end, 6),
            "collisions": sum(event["kind"] == "collision" for event in events),
            "near_misses": sum(event["kind"] == "near_miss" for event in events),
            "damage_events": sum(event["kind"] == "damage" for event in events),
            "panel_breaks": sum(event["kind"] == "panel_break" for event in events),
            "shell_exits": sum(event["kind"] == "shell_exit" for event in events),
        }
    collision_audio = list(plan.of_kind("collision"))
    pitch_pairs = list(zip(collision_audio, collision_audio[1:]))
    immediate_repeats = sum(
        a.shell_id == b.shell_id and a.pitch_degree == b.pitch_degree
        for a, b in pitch_pairs
    )
    run = longest_run = 0
    previous: tuple[int, int] | None = None
    for event in collision_audio:
        note = (event.shell_id, event.pitch_degree)
        run = run + 1 if note == previous else 1
        longest_run = max(longest_run, run)
        previous = note
    collision_times = [float(event["t"]) for event in document["events"]
                       if event["kind"] == "collision"]
    gaps = [b - a for a, b in zip(collision_times, collision_times[1:])]
    first = lambda kind: next(
        (float(event["t"]) for event in document["events"] if event["kind"] == kind),
        None,
    )
    return {
        "seed": int(document["seed"]),
        "duration_seconds": duration,
        "first_collision_seconds": first("collision"),
        "first_near_miss_seconds": first("near_miss"),
        "first_break_seconds": first("panel_break"),
        "first_shell_exit_seconds": first("shell_exit"),
        "segments": segments,
        "longest_collision_gap_seconds": max(gaps, default=0.0),
        "median_collision_gap_seconds": plan.metrics["median_collision_gap_seconds"],
        "immediate_note_repeat_fraction": (
            immediate_repeats / len(pitch_pairs) if pitch_pairs else 0.0
        ),
        "longest_identical_note_run": longest_run,
        "progression": [
            {
                "t": float(event["t"]),
                "shell_id": int(event["shell_id"]),
                "to_region": int(event["to_region"]),
                "method": str(event["method"]),
            }
            for event in _first_outward_exits(document)
        ],
    }

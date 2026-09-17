"""Append-only storage for raw and normalized YouTube evidence."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_platform.serde import dumps, fingerprint, to_jsonable
from company.runtime.state_paths import append_json_bytes, sorted_records

from .models import RetrievedEvidence


@dataclass(frozen=True)
class YouTubeEvidencePointer:
    record_ref: str
    fingerprint: str
    kind: str


class YouTubeEvidenceStore:
    """Preserves provider response and normalized evidence as separate fields."""

    def __init__(self, state_dir: str | Path) -> None:
        self.state_dir = Path(state_dir).expanduser().resolve()
        self.root = self.state_dir / "youtube" / "evidence"

    def append(self, evidence: RetrievedEvidence) -> YouTubeEvidencePointer:
        normalized = to_jsonable(evidence.normalized)
        envelope: dict[str, Any] = {
            "schema_version": 1,
            "kind": evidence.kind,
            "source": _source(evidence),
            "retrieved_at": evidence.retrieved_at.isoformat(),
            "date_range": _date_range(evidence),
            "identity": _identity(evidence),
            "normalized": normalized,
            "raw": evidence.raw,
            "api_calls": to_jsonable(evidence.api_calls),
        }
        envelope["evidence_id"] = "youtube-" + fingerprint(envelope)
        path = append_json_bytes(self.root, dumps(envelope).encode("utf-8"))
        return YouTubeEvidencePointer(
            path.relative_to(self.state_dir).as_posix(),
            fingerprint(envelope),
            evidence.kind,
        )

    def records(self) -> tuple[dict[str, Any], ...]:
        import json

        return tuple(
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted_records(self.root)
        )


def _source(evidence: RetrievedEvidence) -> str:
    value = evidence.normalized
    if isinstance(value, tuple):
        return value[0].source if value else "youtube_data_api_v3.videos.list"
    return value.source


def _date_range(evidence: RetrievedEvidence) -> dict[str, str] | None:
    value = evidence.normalized
    if hasattr(value, "start_date") and hasattr(value, "end_date"):
        return {
            "start": value.start_date.isoformat(),
            "end": value.end_date.isoformat(),
        }
    return None


def _identity(evidence: RetrievedEvidence) -> dict[str, object]:
    value = evidence.normalized
    if evidence.kind == "channel":
        return {"channel_id": value.channel_id}
    if evidence.kind == "videos":
        return {
            "channel_id": value[0].channel_id if value else None,
            "video_ids": [video.video_id for video in value],
        }
    return {"channel_id": value.channel_id, "video_id": value.video_id}


__all__ = ["YouTubeEvidencePointer", "YouTubeEvidenceStore"]

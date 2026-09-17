"""Normalized, immutable YouTube evidence records."""

from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
from typing import Any

from ai_platform.serde import to_jsonable

from .errors import EvidenceError
from .transport import ApiCallTrace


def _instant(value: str | dt.datetime) -> dt.datetime:
    if isinstance(value, str):
        value = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, dt.datetime) or value.tzinfo is None:
        raise EvidenceError("YouTube evidence timestamps must carry a timezone")
    return value.astimezone(dt.timezone.utc)


@dataclass(frozen=True)
class ChannelEvidence:
    channel_id: str
    channel_title: str
    subscriber_count: int | None
    video_count: int | None
    view_count: int | None
    uploads_playlist_id: str
    retrieved_at: dt.datetime
    subscriber_count_unavailable_reason: str = ""
    source: str = "youtube_data_api_v3.channels.list"

    def __post_init__(self) -> None:
        object.__setattr__(self, "retrieved_at", _instant(self.retrieved_at))

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class VideoEvidence:
    video_id: str
    channel_id: str
    title: str
    published_at: dt.datetime
    duration: str | None
    duration_seconds: int | None
    privacy_status: str | None
    upload_status: str | None
    retrieved_at: dt.datetime
    source: str = "youtube_data_api_v3.videos.list"

    def __post_init__(self) -> None:
        object.__setattr__(self, "published_at", _instant(self.published_at))
        object.__setattr__(self, "retrieved_at", _instant(self.retrieved_at))

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class MetricReading:
    name: str
    source_metric: str
    unit: str
    value: float | int | None
    available: bool
    unavailable_reason: str = ""

    def __post_init__(self) -> None:
        if self.available and self.value is None:
            raise EvidenceError(f"{self.name}: an available metric needs a value")
        if not self.available and self.value is not None:
            raise EvidenceError(f"{self.name}: an unavailable metric cannot carry a value")
        if not self.available and not self.unavailable_reason:
            raise EvidenceError(f"{self.name}: unavailability needs a reason")

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class AnalyticsEvidence:
    channel_id: str
    start_date: dt.date
    end_date: dt.date
    video_id: str | None
    metrics: tuple[MetricReading, ...]
    retrieved_at: dt.datetime
    source: str = "youtube_analytics_api_v2.reports.query"

    def __post_init__(self) -> None:
        object.__setattr__(self, "retrieved_at", _instant(self.retrieved_at))
        if self.start_date > self.end_date:
            raise EvidenceError("analytics start_date must not be after end_date")
        names = [metric.name for metric in self.metrics]
        if len(names) != len(set(names)):
            raise EvidenceError("analytics metrics must be unique")

    def metric(self, name: str) -> MetricReading:
        for metric in self.metrics:
            if metric.name == name:
                return metric
        raise KeyError(name)

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class RetrievedEvidence:
    kind: str
    normalized: ChannelEvidence | tuple[VideoEvidence, ...] | AnalyticsEvidence
    raw: dict[str, Any]
    retrieved_at: dt.datetime
    api_calls: tuple[ApiCallTrace, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "retrieved_at", _instant(self.retrieved_at))

    def to_dict(self, *, include_raw: bool = False) -> dict[str, Any]:
        result = {
            "kind": self.kind,
            "normalized": to_jsonable(self.normalized),
            "retrieved_at": self.retrieved_at.isoformat(),
            "api_calls": to_jsonable(self.api_calls),
            "raw_preserved": True,
        }
        if include_raw:
            result["raw"] = self.raw
        return result


__all__ = [
    "AnalyticsEvidence",
    "ChannelEvidence",
    "MetricReading",
    "RetrievedEvidence",
    "VideoEvidence",
]

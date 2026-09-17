"""Bridge authenticated API evidence into Company OS analytics observations."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib

from company.analytics import (
    AnalyzedDeliverable,
    AnalyticsStore,
    DataScope,
    DataSource,
    DeliverableKind,
    MetricObservation,
    Provenance,
    observe,
)
from company.analytics.errors import LedgerViolation
from knowledge.company_os.records import Evidence

from .errors import EvidenceError
from .models import AnalyticsEvidence, MetricReading, VideoEvidence


@dataclass(frozen=True)
class AnalyticsCommit:
    deliverable_id: str
    observation_ids: tuple[str, ...]
    unavailable_metrics: tuple[str, ...]
    evidence_ref: str


def build_deliverable(
    video: VideoEvidence,
    *,
    deliverable_id: str,
    kind: DeliverableKind,
    format_id: str,
) -> AnalyzedDeliverable:
    return AnalyzedDeliverable(
        deliverable_id=deliverable_id,
        kind=kind,
        format_id=format_id,
        title=video.title,
        published_at=video.published_at,
        production_refs=(f"youtube:video:{video.video_id}",),
        notes="Identity supplied by the YouTube Data API; format classification supplied by the operator.",
    )


def analytics_observations(
    report: AnalyticsEvidence,
    video: VideoEvidence,
    deliverable: AnalyzedDeliverable,
    *,
    evidence_ref: str,
) -> tuple[MetricObservation, ...]:
    if report.video_id != video.video_id:
        raise EvidenceError("per-video analytics and video identity do not match")
    provenance = Provenance(
        source=DataSource.OWN_ANALYTICS_API,
        retrieved_by="YouTube Analytics API v2 reports.query",
        evidence=(
            Evidence(
                kind="external",
                ref=evidence_ref,
                note="append-only raw and normalized YouTube API evidence",
            ),
        ),
    )
    scope = DataScope(
        population=(
            f"YouTube activity for video {video.video_id} from "
            f"{report.start_date.isoformat()} through {report.end_date.isoformat()}"
        ),
        limitations=(
            "YouTube Analytics data can be delayed or revised after retrieval.",
        ),
    )
    observations: list[MetricObservation] = []
    for reading in report.metrics:
        mapped = _analytics_metric(reading)
        if mapped is None:
            continue
        metric_name, value, note = mapped
        identity = (
            f"{evidence_ref}|{deliverable.deliverable_id}|{metric_name}|"
            f"{report.start_date.isoformat()}|{report.end_date.isoformat()}"
        )
        observation_id = "ytapi-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
        denominator = (
            float(video.duration_seconds)
            if metric_name == "average_percentage_viewed" and video.duration_seconds is not None
            else None
        )
        observations.append(
            observe(
                observation_id,
                deliverable,
                metric_name,
                value,
                report.retrieved_at,
                provenance,
                scope,
                denominator_value=denominator,
                note=note,
            )
        )
    return tuple(observations)


def commit_analytics(
    store: AnalyticsStore,
    report: AnalyticsEvidence,
    video: VideoEvidence,
    deliverable: AnalyzedDeliverable,
    *,
    evidence_ref: str,
) -> AnalyticsCommit:
    if deliverable.deliverable_id in store.ids("deliverable"):
        existing = store.get("deliverable", deliverable.deliverable_id)
        if existing.to_dict() != deliverable.to_dict():
            raise LedgerViolation(
                f"deliverable {deliverable.deliverable_id!r} already exists with different content"
            )
    else:
        store.put(deliverable)
    observations = analytics_observations(
        report, video, deliverable, evidence_ref=evidence_ref
    )
    store.put_all(observations)
    unavailable = tuple(metric.name for metric in report.metrics if not metric.available)
    return AnalyticsCommit(
        deliverable.deliverable_id,
        tuple(observation.observation_id for observation in observations),
        unavailable,
        evidence_ref,
    )


def _analytics_metric(reading: MetricReading) -> tuple[str, float, str] | None:
    if not reading.available or reading.value is None:
        return None
    value = float(reading.value)
    if reading.name == "estimated_minutes_watched":
        return (
            "watch_time_hours",
            value / 60.0,
            "Converted from YouTube API estimatedMinutesWatched by dividing by 60.",
        )
    mapping = {
        "views": "views",
        "average_view_duration_seconds": "average_view_duration_seconds",
        "average_view_percentage": "average_percentage_viewed",
        "subscribers_gained": "subscribers_gained",
        "subscribers_lost": "subscribers_lost",
        "likes": "likes",
        "comments": "comments",
        "shares": "shares",
    }
    metric = mapping.get(reading.name)
    return (metric, value, f"YouTube API metric {reading.source_metric}.") if metric else None


__all__ = [
    "AnalyticsCommit",
    "analytics_observations",
    "build_deliverable",
    "commit_analytics",
]

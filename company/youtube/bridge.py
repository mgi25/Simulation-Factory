"""An artifact reading becomes an observation, or it becomes nothing.

## Identity is what was measured, and nothing else

The id of an observation built here is a digest of eight facts: the API, the
channel, the video, the deliverable, the registry metric, the two ends of the
window, and the measurement tag. That list is the whole design, and it is
defined by what is *not* on it. The artifact's path is not on it, nor the
evidence record's sequence number, nor `fetched_at`, nor the artifact digest,
nor - most importantly - the value.

Each omission closes a specific failure. A path or a filename on the id means
the same pull imported from two directories becomes two readings of one window.
`fetched_at` on the id means every re-pull is a new reading, and a store that
was supposed to hold one number per window per metric holds a growing pile of
identical ones. The artifact digest on the id means a fetcher upgrade silently
duplicates history. And the *value* on the id is the worst of the four: it makes
a revised number a new record rather than a contradiction, so 100 views and 118
views for the same week sit side by side and every later average is wrong.

With the value off the id, a revision collides with what is stored, and
`ingest.py` refuses it as a conflict. That is the intended behaviour, not a
limitation: analytics history is append-only, and a correction supersedes a
record rather than editing it.

## `observed_at` is when the window closed, not when we looked

`MetricObservation` needs an instant, and a window is not one. The only instant
a bounded reading actually supports is the moment it became complete: midnight
UTC at the start of the day after `end_date`. Using the fetch instant instead
would mean two pulls of the same finished week were two observations taken at
two different times, which is exactly the duplication the id is designed to
prevent - and it would also be untrue, because nothing about the reading
happened when the request was made.

## The breakdown is what keeps an API reading off a Studio reading

A Studio videos export is a cumulative total as it stood when the export was
taken. An Analytics API pull is a measurement of a bounded window. They can name
the same video and the same metric, and they are not the same measurement: one
is views since publication, the other views during a fortnight. Every
observation built here carries `breakdown={"measurement": "interval"}`, which
puts it in a different `MetricObservation.key` from the cumulative reading, so
the two can sit in one store without ever being compared, averaged or reported
as a contradiction.

## Money is not here, and cannot be

There is no monetary metric in the artifact vocabulary and no mapping for one.
Section 17 of the analytics brief, implemented by having nowhere to put the
number: finance owns money, and an analytics ingester that produced a revenue
figure would be a second answer to a question that already has an owner.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Mapping

from ai_platform.serde import fingerprint
from company.analytics import (
    AnalyzedDeliverable,
    ApiArtifactSource,
    DataScope,
    DataSource,
    DateRange,
    DeliverableKind,
    MetricObservation,
    MetricRegistry,
    Provenance,
    TemporalSemantics,
    artifact_evidence,
    observe,
    source_id_for,
)

from .artifact import artifact_digest
from .errors import ArtifactRejected
from .models import (
    ANALYTICS_SOURCE,
    AnalyticsEvidence,
    MetricReading,
    VideoEvidence,
    YouTubeArtifact,
)

# Named rather than left blank, for the reason `studio_ingest.DEFAULT_POPULATION`
# gives: `DataScope` exists to stop two readings of different populations being
# averaged, and an empty population defeats it.
POPULATION_TEMPLATE = (
    "every viewer the channel's own Analytics API counted for {subject} "
    "between {start} and {end}"
)

# The caveat every platform reading carries. Analytics figures are revised after
# the fact, and a reading that does not say so reads as final.
REVISION_LIMITATION = (
    "YouTube Analytics data can be delayed or revised after retrieval."
)

# Which pull produced the number. Deliberately a constant and not the artifact's
# own producer version: it is written into every observation, and a value that
# changes when the fetcher is upgraded would make a re-pull of an unchanged
# window a different record. Which pull it was is answered by the digest in the
# evidence reference.
RETRIEVED_BY = "YouTube Analytics API v2 reports.query, fetched by tools.youtube_fetch"


@dataclass(frozen=True)
class MetricMapping:
    """One artifact metric name, and the registry metric it is a reading of.

    `factor` is a unit conversion and nothing else. The one non-trivial case is
    `estimatedMinutesWatched`, which the registry holds as hours, and it is
    converted here rather than at the API so that the artifact keeps the units
    the platform actually reported.
    """

    artifact_name: str
    metric: str
    factor: float = 1.0
    conversion: str = ""


# The complete vocabulary. A metric the artifact names that is not in this table
# produces no observation and a diagnostic saying the name was not recognised -
# never a guess at which registry metric was meant.
METRIC_VOCABULARY: dict[str, MetricMapping] = {
    mapping.artifact_name: mapping
    for mapping in (
        MetricMapping("views", "views"),
        MetricMapping(
            "estimated_minutes_watched",
            "watch_time_hours",
            factor=1.0 / 60.0,
            conversion="converted from estimatedMinutesWatched by dividing by 60",
        ),
        MetricMapping("average_view_duration_seconds", "average_view_duration_seconds"),
        MetricMapping("average_view_percentage", "average_percentage_viewed"),
        MetricMapping("subscribers_gained", "subscribers_gained"),
        MetricMapping("subscribers_lost", "subscribers_lost"),
        MetricMapping("likes", "likes"),
        MetricMapping("comments", "comments"),
        MetricMapping("shares", "shares"),
    )
}


def build_deliverable(
    video: VideoEvidence,
    *,
    deliverable_id: str,
    kind: DeliverableKind,
    format_id: str,
    version: str = "",
) -> AnalyzedDeliverable:
    """The analytics handle for one video, from the platform's own identity.

    Kind and format are the operator's declaration, never inferred: which
    family a video belongs to is a fact about how it was made, and reading it
    off a title would be a guess wearing the authority of a record.
    """
    return AnalyzedDeliverable(
        deliverable_id=deliverable_id,
        kind=kind,
        format_id=format_id,
        version=version,
        title=video.title,
        published_at=video.published_at,
        production_refs=(video.production_ref,),
        notes=(
            "Identity supplied by the YouTube Data API; format classification "
            "supplied by the operator."
        ),
    )


def build_source(artifact: YouTubeArtifact, *, note: str = "") -> ApiArtifactSource:
    """The source record for one artifact, derived entirely from what it measured.

    Every field is a function of the semantic payload, so two artifacts holding
    the same numbers build the same record byte for byte and the second import
    writes nothing. That is why the fetch instant, the producer version and the
    file's path appear nowhere on it.
    """
    if not artifact.analytics:
        raise ArtifactRejected(
            "artifact: there is no analytics row set to ingest, so there is no window "
            "for a source record to name. Inspect the artifact instead, or re-run the "
            "fetch with a date range"
        )
    digest = artifact_digest(artifact)
    return ApiArtifactSource(
        source_id=source_id_for(digest),
        digest=digest,
        api=ANALYTICS_SOURCE,
        channel_ref=artifact.channel_ref,
        semantics=TemporalSemantics.INTERVAL,
        reported_range=reported_range(artifact),
        provenance=Provenance(
            source=DataSource.OWN_ANALYTICS_API,
            retrieved_by=RETRIEVED_BY,
            evidence=(artifact_evidence(digest),),
        ),
        granted_scopes=artifact.granted_scopes,
        complete=artifact.complete,
        excludes=artifact_excludes(artifact),
        note=note,
    )


def reported_range(artifact: YouTubeArtifact) -> DateRange:
    """The widest window any reading in the artifact covers.

    A pull can ask for several videos over one window, and could in principle
    ask for two windows in one file. The source record names the span the file
    as a whole describes; each observation records its own window in its
    identity, so nothing is compared across windows because of this.
    """
    return DateRange(
        min(report.start_date for report in artifact.analytics),
        max(report.end_date for report in artifact.analytics),
    )


def artifact_excludes(artifact: YouTubeArtifact) -> tuple[str, ...]:
    """Everything this pull is known not to have got, by name.

    Requirement 6 in one function. A retrieval that came back short names the
    exact ids it is missing, not a count, and an analytics row set that knows it
    is partial contributes its own sentences. The result reaches `DataScope`,
    which refuses `complete=False` with nothing to show for it.
    """
    out: list[str] = []
    shortfall = artifact.video_retrieval.shortfall_sentence
    if shortfall:
        out.append(shortfall)
    out.extend(artifact.video_retrieval.notes)
    for report in artifact.analytics:
        out.extend(f"{report.subject_ref}: {text}" for text in report.excludes)
    seen: list[str] = []
    for item in out:
        if item not in seen:
            seen.append(item)
    return tuple(seen)


def build_scope(artifact: YouTubeArtifact, report: AnalyticsEvidence) -> DataScope:
    """What one row set covers, and what the pull it arrived in did not get.

    The incompleteness of the *pull* lands on every reading taken from it, which
    is deliberate. A reading that looks whole, sitting in a store beside a gap
    nobody recorded, is how a partial import becomes a fact.
    """
    excludes = artifact_excludes(artifact)
    return DataScope(
        population=POPULATION_TEMPLATE.format(
            subject=report.subject_ref,
            start=report.start_date.isoformat(),
            end=report.end_date.isoformat(),
        ),
        complete=not excludes,
        excludes=excludes,
        limitations=(REVISION_LIMITATION,),
    )


def window_close(end_date: dt.date) -> dt.datetime:
    """The instant a window's measurement is complete: midnight UTC after its last day.

    The same reasoning as `studio_ingest._coverage`, with UTC instead of a
    channel reporting offset, because the Analytics API is asked for days in UTC
    and answers in them.
    """
    return dt.datetime.combine(
        end_date + dt.timedelta(days=1), dt.time(0, 0), tzinfo=dt.timezone.utc
    )


def observation_identity(
    *,
    report: AnalyticsEvidence,
    deliverable_id: str,
    metric: str,
    api: str = ANALYTICS_SOURCE,
) -> dict[str, Any]:
    """The semantic facts an observation id is a digest of. See the module docstring."""
    return {
        "api": api,
        "channel_id": report.channel_id,
        "video_id": report.video_id,
        "deliverable_id": deliverable_id,
        "metric": metric,
        "start_date": report.start_date.isoformat(),
        "end_date": report.end_date.isoformat(),
        "measurement": TemporalSemantics.INTERVAL.measurement_tag,
    }


def observation_id_for(identity: Mapping[str, Any]) -> str:
    """`ya-` and sixteen hex characters of the identity's canonical form."""
    return f"ya-{fingerprint(dict(identity))}"


def resolve_metric(reading: MetricReading) -> MetricMapping | None:
    """The registry metric this reading is of, or None if the name is unknown."""
    return METRIC_VOCABULARY.get(reading.name)


def build_observation(
    *,
    source: ApiArtifactSource,
    report: AnalyticsEvidence,
    reading: MetricReading,
    mapping: MetricMapping,
    deliverable: AnalyzedDeliverable,
    video: VideoEvidence | None,
    scope: DataScope,
    registry: MetricRegistry | None = None,
) -> MetricObservation:
    """One reading, as a record that says what it is and where it came from.

    Raises `AnalyticsError` when the reading cannot honestly become an
    observation - a value the metric definition refuses, a window that closes
    before the deliverable was published. The caller turns that into a
    diagnostic naming the metric, and the import continues without it.
    """
    if not reading.available or reading.value is None:  # pragma: no cover - guarded
        raise ArtifactRejected(
            f"metric {reading.name!r}: an unavailable reading has no value to record, "
            "and zero is not a reading"
        )
    identity = observation_identity(
        report=report, deliverable_id=deliverable.deliverable_id, metric=mapping.metric
    )
    note = f"YouTube API metric {reading.source_metric}, {source.coverage_sentence}"
    if mapping.conversion:
        note = f"{note}; {mapping.conversion}"
    return observe(
        observation_id_for(identity),
        deliverable,
        mapping.metric,
        float(reading.value) * mapping.factor,
        window_close(report.end_date),
        source.observation_provenance(),
        scope,
        denominator_value=_denominator(mapping, video),
        breakdown={"measurement": TemporalSemantics.INTERVAL.measurement_tag},
        note=note,
        registry=registry,
    )


def _denominator(mapping: MetricMapping, video: VideoEvidence | None) -> float | None:
    """The denominator of a rate, where the artifact happens to carry it.

    Only `average_percentage_viewed` has one this artifact can supply - the
    video's own length. It is optional rather than required because a missing
    duration costs the comparison (`comparison.py` marks the rate pair not
    comparable) rather than the reading.
    """
    if mapping.metric != "average_percentage_viewed":
        return None
    if video is None or video.duration_seconds is None:
        return None
    return float(video.duration_seconds)


__all__ = [
    "METRIC_VOCABULARY",
    "POPULATION_TEMPLATE",
    "RETRIEVED_BY",
    "REVISION_LIMITATION",
    "MetricMapping",
    "artifact_excludes",
    "build_deliverable",
    "build_observation",
    "build_scope",
    "build_source",
    "observation_id_for",
    "observation_identity",
    "reported_range",
    "resolve_metric",
    "window_close",
]

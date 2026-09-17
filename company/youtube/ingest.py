"""Artifact to auditable observation, or to a diagnostic saying why not.

## The two halves, and why they are two

`ingest_artifact` reads an artifact and returns everything it would record. It
touches no store, so a dry run is the real import with the last step left off -
not a second code path that approximates it and drifts. `commit_ingestion` takes
that result, checks it against what is already recorded, and appends. The shape
is `studio_ingest.py`'s on purpose: the same two verbs, the same three commit
outcomes, the same diagnostic vocabulary, so a reader who knows one import knows
both.

The interesting failures are all visible before anything is written - a metric
the API did not report, a video the artifact has no identity for, a number that
contradicts one already in the ledger - and a caller who reads the result before
committing is doing the review the whole layer exists to make possible.

## Nothing is imported quietly, including what is not imported

The result reports readings read and readings accepted, and then reports every
reason the difference exists: each unavailable metric with the API's own reason,
each metric name the vocabulary does not recognise, each video with no
assignment, each channel-wide row set that has no deliverable to attach to.
"Import successful" is not a sentence this layer can say.

An unavailable metric is a note rather than an error, because it is the expected
case rather than a defect: the Analytics API returns no row for a metric it has
nothing to say about, and the honest record of that is the absence of an
observation plus a named reason. It is never a zero, and there is nowhere in
this module where it could become one.

## Idempotence, and the difference between a replay and a disagreement

Everything a committed record contains is a function of what the pull measured,
so re-importing the same artifact - or a second artifact file holding the same
numbers, written at a different moment to a different path - produces the same
ids with the same content, and the store's append-only guard makes that a no-op.
Replay is safe by construction rather than by a flag.

A pull that claims a *different* value for the same video, metric and window is
not a replay. It lands on the same observation id with different content, so
`commit_ingestion` refuses it as a conflict naming both readings, and with
`allow_conflicts=False` - the default - nothing at all is written, not even the
source record. Half an import is harder to reason about than none, and a second
contradictory row would quietly break every later average.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from company.analytics import (
    AnalyticsError,
    AnalyticsStore,
    AnalyzedDeliverable,
    ApiArtifactSource,
    DeliverableKind,
    IngestionIssue,
    IngestionIssueKind,
    IssueSeverity,
    LedgerViolation,
    MetricObservation,
    MetricRegistry,
)

from .artifact import artifact_digest
from .bridge import (
    artifact_excludes,
    build_deliverable,
    build_observation,
    build_scope,
    build_source,
    resolve_metric,
)
from .errors import ArtifactRejected
from .models import YouTubeArtifact

# How many diagnostics a rendered summary prints before it stops listing them.
# The same budget `studio_ingest.py` uses, for the same reason: a summary that
# prints four hundred lines is a summary nobody reads.
MAX_LISTED_ISSUES = 20


@dataclass(frozen=True)
class DeliverableAssignment:
    """The operator's declaration of what one video is, in analytics terms.

    Three things the platform cannot tell us: which deliverable id this video
    is, what kind of thing it is, and which format family it belongs to. All
    three are supplied by whoever made it. Nothing here is inferred from a title
    or a duration, because a family read off a title is a guess carrying the
    authority of a record.
    """

    deliverable_id: str
    kind: DeliverableKind
    format_id: str
    version: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.kind, DeliverableKind):
            raise ArtifactRejected(
                f"assignment for {self.deliverable_id!r}: kind must be a "
                f"DeliverableKind, got {self.kind!r}. Known: "
                + ", ".join(sorted(k.value for k in DeliverableKind))
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "deliverable_id": self.deliverable_id,
            "kind": self.kind.value,
            "format_id": self.format_id,
            "version": self.version,
        }


@dataclass(frozen=True)
class UnavailableReading:
    """One metric the API did not report, with the reason it gave."""

    subject_ref: str
    metric: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject_ref": self.subject_ref,
            "metric": self.metric,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ApiIngestionResult:
    """Everything one artifact produced, and everything it did not."""

    source: ApiArtifactSource
    deliverables: tuple[AnalyzedDeliverable, ...]
    observations: tuple[MetricObservation, ...]
    readings_read: int
    readings_accepted: int
    issues: tuple[IngestionIssue, ...] = ()
    unavailable: tuple[UnavailableReading, ...] = ()
    unknown_metrics: tuple[str, ...] = ()
    unassigned_videos: tuple[str, ...] = ()

    @property
    def readings_rejected(self) -> int:
        return self.readings_read - self.readings_accepted

    @property
    def errors(self) -> tuple[IngestionIssue, ...]:
        return tuple(i for i in self.issues if i.severity is IssueSeverity.ERROR)

    @property
    def warnings(self) -> tuple[IngestionIssue, ...]:
        return tuple(i for i in self.issues if i.severity is IssueSeverity.WARNING)

    @property
    def notes(self) -> tuple[IngestionIssue, ...]:
        return tuple(i for i in self.issues if i.severity is IssueSeverity.NOTE)

    def issues_of(self, kind: IngestionIssueKind) -> tuple[IngestionIssue, ...]:
        return tuple(i for i in self.issues if i.kind is kind)

    @property
    def deliverable_ids(self) -> tuple[str, ...]:
        return tuple(sorted({o.deliverable_id for o in self.observations}))

    def render(self) -> str:
        """A summary in counts and references. Deliberately quotes no reading."""
        lines = [
            f"youtube api artifact {self.source.source_id}",
            f"  digest      sha256:{self.source.short_digest}",
            f"  channel     {self.source.channel_ref}",
            f"  covers      {self.source.coverage_sentence}",
            f"  grant       {', '.join(self.source.granted_scopes)}",
            f"  readings    {self.readings_read} read, "
            f"{self.readings_accepted} accepted",
            f"  observations {len(self.observations)} for "
            f"{len(self.deliverable_ids)} deliverable(s)",
        ]
        if not self.source.complete:
            lines.append("  incomplete pull:")
            for text in self.source.excludes:
                lines.append(f"    {text}")
        if self.unavailable:
            lines.append(f"  unavailable  {len(self.unavailable)} metric(s)")
            for reading in self.unavailable[:MAX_LISTED_ISSUES]:
                lines.append(
                    f"    {reading.subject_ref} {reading.metric}: {reading.reason}"
                )
        if self.unknown_metrics:
            lines.append(f"  unmapped metrics  {', '.join(self.unknown_metrics)}")
        if self.unassigned_videos:
            lines.append(f"  unassigned videos {', '.join(self.unassigned_videos)}")
        counts = {
            severity.value: len([i for i in self.issues if i.severity is severity])
            for severity in IssueSeverity
        }
        lines.append(
            f"  diagnostics {counts['error']} error(s), {counts['warning']} "
            f"warning(s), {counts['note']} note(s)"
        )
        listed = [i for i in self.issues if i.severity is not IssueSeverity.NOTE]
        for issue in listed[:MAX_LISTED_ISSUES]:
            lines.append(f"    {issue}")
        if len(listed) > MAX_LISTED_ISSUES:
            lines.append(f"    ... {len(listed) - MAX_LISTED_ISSUES} more")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.to_dict(),
            "deliverable_ids": [d.deliverable_id for d in self.deliverables],
            "observation_ids": [o.observation_id for o in self.observations],
            "readings_read": self.readings_read,
            "readings_accepted": self.readings_accepted,
            "issues": [i.to_dict() for i in self.issues],
            "unavailable": [u.to_dict() for u in self.unavailable],
            "unknown_metrics": list(self.unknown_metrics),
            "unassigned_videos": list(self.unassigned_videos),
        }


@dataclass(frozen=True)
class ApiCommitOutcome:
    """What a commit actually did to the store."""

    written: tuple[str, ...] = ()
    already_present: tuple[str, ...] = ()
    conflicts: tuple[IngestionIssue, ...] = ()
    source_recorded: bool = False
    deliverables_written: tuple[str, ...] = ()

    @property
    def wrote_nothing(self) -> bool:
        return (
            not self.written
            and not self.source_recorded
            and not self.deliverables_written
        )

    def render(self) -> str:
        lines = [
            f"{len(self.written)} observation(s) written, "
            f"{len(self.already_present)} already present, "
            f"{len(self.conflicts)} conflict(s)"
        ]
        if self.deliverables_written:
            lines.append(f"  deliverables {', '.join(self.deliverables_written)}")
        for conflict in self.conflicts[:MAX_LISTED_ISSUES]:
            lines.append(f"  {conflict}")
        return "\n".join(lines)


@dataclass(frozen=True)
class ArtifactDescription:
    """What `inspect` can say about an artifact without importing it.

    Names, counts, windows and availability. No value of any metric: private
    channel analytics printed on a terminal is private channel analytics in a
    scrollback buffer, and the question inspect answers is what importing this
    file would do, not what the numbers are.
    """

    digest: str
    producer: str
    producer_version: str
    fetched_at: str
    channel_ref: str
    channel_title: str
    granted_scopes: tuple[str, ...]
    video_count: int
    windows: tuple[str, ...]
    subjects: tuple[str, ...]
    metric_names: tuple[str, ...]
    unavailable: tuple[UnavailableReading, ...]
    unknown_metrics: tuple[str, ...]
    complete: bool
    excludes: tuple[str, ...]
    api_call_count: int
    holds_raw: bool

    def render(self) -> str:
        lines = [
            f"youtube api artifact sha256:{self.digest[:12]}",
            f"  producer    {self.producer} {self.producer_version}",
            f"  fetched at  {self.fetched_at}",
            f"  channel     {self.channel_ref} ({self.channel_title})",
            f"  grant       {', '.join(self.granted_scopes)}",
            f"  videos      {self.video_count}",
            f"  windows     {', '.join(self.windows) or 'none'}",
            f"  subjects    {', '.join(self.subjects) or 'none'}",
            f"  metrics     {', '.join(self.metric_names) or 'none'}",
            f"  api calls   {self.api_call_count}",
            f"  raw kept    {'yes' if self.holds_raw else 'no'}",
            f"  complete    {'yes' if self.complete else 'no'}",
        ]
        for text in self.excludes:
            lines.append(f"    {text}")
        if self.unknown_metrics:
            lines.append(
                "  metric names this ingester does not recognise: "
                + ", ".join(self.unknown_metrics)
            )
        for reading in self.unavailable[:MAX_LISTED_ISSUES]:
            lines.append(
                f"  unavailable {reading.subject_ref} {reading.metric}: "
                f"{reading.reason}"
            )
        lines.append(
            "\nNo reading is printed here. Import it to see the numbers in the store."
        )
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "digest": self.digest,
            "producer": self.producer,
            "producer_version": self.producer_version,
            "fetched_at": self.fetched_at,
            "channel_ref": self.channel_ref,
            "channel_title": self.channel_title,
            "granted_scopes": list(self.granted_scopes),
            "video_count": self.video_count,
            "windows": list(self.windows),
            "subjects": list(self.subjects),
            "metric_names": list(self.metric_names),
            "unavailable": [u.to_dict() for u in self.unavailable],
            "unknown_metrics": list(self.unknown_metrics),
            "complete": self.complete,
            "excludes": list(self.excludes),
            "api_call_count": self.api_call_count,
            "holds_raw": self.holds_raw,
        }


def describe_artifact(artifact: YouTubeArtifact) -> ArtifactDescription:
    """Everything an operator needs to decide whether to import this file."""
    unavailable = tuple(
        UnavailableReading(
            report.subject_ref, reading.name, reading.unavailable_reason
        )
        for report in artifact.analytics
        for reading in report.unavailable
    )
    names: list[str] = []
    unknown: list[str] = []
    for report in artifact.analytics:
        for reading in report.metrics:
            if reading.name not in names:
                names.append(reading.name)
            if resolve_metric(reading) is None and reading.name not in unknown:
                unknown.append(reading.name)
    return ArtifactDescription(
        digest=artifact_digest(artifact),
        producer=artifact.producer,
        producer_version=artifact.producer_version,
        fetched_at=artifact.fetched_at.isoformat(),
        channel_ref=artifact.channel_ref,
        channel_title=artifact.channel.channel_title,
        granted_scopes=artifact.granted_scopes,
        video_count=len(artifact.videos),
        windows=tuple(
            dict.fromkeys(
                f"{report.start_date.isoformat()}..{report.end_date.isoformat()}"
                for report in artifact.analytics
            )
        ),
        subjects=tuple(dict.fromkeys(r.subject_ref for r in artifact.analytics)),
        metric_names=tuple(names),
        unavailable=unavailable,
        unknown_metrics=tuple(unknown),
        complete=artifact.complete,
        excludes=artifact_excludes(artifact),
        api_call_count=len(artifact.api_calls),
        holds_raw=artifact.raw is not None,
    )


def ingest_artifact(
    artifact: YouTubeArtifact,
    *,
    assignments: Mapping[str, DeliverableAssignment],
    registry: MetricRegistry | None = None,
    note: str = "",
) -> ApiIngestionResult:
    """Everything this artifact would record, computed without touching a store."""
    source = build_source(artifact, note=note)
    issues: list[IngestionIssue] = []
    unavailable: list[UnavailableReading] = []
    unknown_metrics: list[str] = []
    unassigned: list[str] = []
    deliverables: dict[str, AnalyzedDeliverable] = {}
    observations: list[MetricObservation] = []
    readings_read = 0
    readings_accepted = 0

    for report in artifact.analytics:
        readings_read += len(report.metrics)
        if report.video_id is None:
            issues.append(
                IngestionIssue(
                    IngestionIssueKind.MISSING_VIDEO_ID,
                    "a channel-wide row set names no video, and an observation is "
                    "recorded against a deliverable. A channel total is a reading "
                    "about the channel, which this ledger has no subject for",
                    video_id="",
                )
            )
            continue
        video = artifact.video(report.video_id)
        if video is None:
            issues.append(
                IngestionIssue(
                    IngestionIssueKind.MISSING_VIDEO_ID,
                    "the artifact carries analytics for this video and no identity "
                    "for it, so there is no publication date to place the reading "
                    "against. Re-run the fetch; videos.list did not return it",
                    video_id=report.video_id,
                )
            )
            continue
        assignment = assignments.get(report.video_id)
        if assignment is None:
            if report.video_id not in unassigned:
                unassigned.append(report.video_id)
            issues.append(
                IngestionIssue(
                    IngestionIssueKind.UNRESOLVED_DELIVERABLE,
                    "no assignment says which deliverable this video is, or what "
                    "kind and format it belongs to. Nothing here is inferred from "
                    "the title sitting next to it",
                    video_id=report.video_id,
                )
            )
            continue

        deliverable = build_deliverable(
            video,
            deliverable_id=assignment.deliverable_id,
            kind=assignment.kind,
            format_id=assignment.format_id,
            version=assignment.version,
        )
        deliverables.setdefault(deliverable.deliverable_id, deliverable)
        scope = build_scope(artifact, report)

        for reading in report.metrics:
            if not reading.available:
                unavailable.append(
                    UnavailableReading(
                        report.subject_ref, reading.name, reading.unavailable_reason
                    )
                )
                issues.append(
                    IngestionIssue(
                        IngestionIssueKind.BLANK_VALUE,
                        f"the API reported no value: {reading.unavailable_reason}. "
                        "Recorded as missing rather than as zero",
                        column=reading.name,
                        video_id=report.video_id,
                    )
                )
                continue
            mapping = resolve_metric(reading)
            if mapping is None:
                if reading.name not in unknown_metrics:
                    unknown_metrics.append(reading.name)
                issues.append(
                    IngestionIssue(
                        IngestionIssueKind.UNKNOWN_COLUMN,
                        "this ingester has no registry metric for that name, and "
                        "guessing which one was meant is how a fraction becomes a "
                        "percentage. Add it to the vocabulary deliberately",
                        column=reading.name,
                        video_id=report.video_id,
                    )
                )
                continue
            try:
                observations.append(
                    build_observation(
                        source=source,
                        report=report,
                        reading=reading,
                        mapping=mapping,
                        deliverable=deliverable,
                        video=video,
                        scope=scope,
                        registry=registry,
                    )
                )
            except AnalyticsError as exc:
                issues.append(
                    IngestionIssue(
                        IngestionIssueKind.OBSERVATION_REFUSED,
                        str(exc),
                        column=reading.name,
                        video_id=report.video_id,
                    )
                )
                continue
            readings_accepted += 1

    return ApiIngestionResult(
        source=source,
        deliverables=tuple(deliverables.values()),
        observations=tuple(observations),
        readings_read=readings_read,
        readings_accepted=readings_accepted,
        issues=tuple(issues),
        unavailable=tuple(unavailable),
        unknown_metrics=tuple(unknown_metrics),
        unassigned_videos=tuple(unassigned),
    )


def commit_ingestion(
    result: ApiIngestionResult,
    store: AnalyticsStore,
    *,
    allow_conflicts: bool = False,
) -> ApiCommitOutcome:
    """Append what this import produced, refusing anything that contradicts the store.

    Three outcomes per observation, exactly as the Studio import has them. An id
    not present is written. An id present with identical content is a replay of
    the same pull and is left alone. An id present with different content, or a
    reading of the same metric of the same deliverable at the same instant with
    a different value, is a conflict - and by default a conflict writes nothing
    at all, not even the source record.
    """
    if not isinstance(store, AnalyticsStore):
        raise AnalyticsError(f"expected an AnalyticsStore, got {type(store).__name__}")
    existing = {o.observation_id: o for o in store.list("observation")}
    by_snapshot: dict[str, list[MetricObservation]] = {}
    for observation in existing.values():
        by_snapshot.setdefault(observation.snapshot_key, []).append(observation)

    to_write: list[MetricObservation] = []
    already: list[str] = []
    conflicts: list[IngestionIssue] = []
    for observation in result.observations:
        prior = existing.get(observation.observation_id)
        if prior is not None:
            if prior.to_dict() == observation.to_dict():
                already.append(observation.observation_id)
            else:
                conflicts.append(
                    IngestionIssue(
                        IngestionIssueKind.VALUE_CONFLICT,
                        f"observation {observation.observation_id} is already recorded "
                        f"with different content ({prior.value} against "
                        f"{observation.value}). Analytics history is append-only, so "
                        "the earlier reading stands and this one was not written",
                        column=observation.metric.name,
                    )
                )
            continue
        disagreeing = [
            other
            for other in by_snapshot.get(observation.snapshot_key, ())
            if other.value != observation.value
        ]
        if disagreeing:
            conflicts.append(
                IngestionIssue(
                    IngestionIssueKind.VALUE_CONFLICT,
                    f"{observation.snapshot_key} is already recorded as "
                    f"{disagreeing[0].value} by {disagreeing[0].observation_id}, and "
                    f"this pull says {observation.value}. One of the two is wrong; a "
                    "correction supersedes an earlier record rather than sitting "
                    "beside it",
                    column=observation.metric.name,
                )
            )
            continue
        to_write.append(observation)

    new_deliverables = _deliverable_plan(result.deliverables, store, conflicts)
    conflicts.extend(_source_conflicts(result.source, store))
    if conflicts and not allow_conflicts:
        raise LedgerViolation(
            f"{len(conflicts)} conflict(s) between this pull and what is already "
            "recorded; nothing was written:\n  "
            + "\n  ".join(str(conflict) for conflict in conflicts)
        )

    store.put_all(new_deliverables)
    recorded = _record_source(result.source, store)
    store.put_all(to_write)
    return ApiCommitOutcome(
        written=tuple(o.observation_id for o in to_write),
        already_present=tuple(already),
        conflicts=tuple(conflicts),
        source_recorded=recorded,
        deliverables_written=tuple(d.deliverable_id for d in new_deliverables),
    )


def load_assignments(data: Any) -> dict[str, DeliverableAssignment]:
    """Read the operator's video-to-deliverable declarations from a mapping.

    The shape a JSON file on disk has: video id to an object naming the
    deliverable, its kind and its format. Refused rather than guessed at when a
    field is missing, because a default kind here would classify somebody's
    video for them.
    """
    if not isinstance(data, Mapping):
        raise ArtifactRejected(
            f"assignments: expected an object keyed by video id, got {data!r}"
        )
    out: dict[str, DeliverableAssignment] = {}
    for video_id, item in data.items():
        if not isinstance(item, Mapping):
            raise ArtifactRejected(
                f"assignments[{video_id!r}]: expected an object naming the "
                "deliverable, its kind and its format"
            )
        missing = [
            key for key in ("deliverable_id", "kind", "format_id") if key not in item
        ]
        if missing:
            raise ArtifactRejected(
                f"assignments[{video_id!r}]: missing " + ", ".join(missing)
            )
        try:
            kind = DeliverableKind(item["kind"])
        except ValueError as exc:
            raise ArtifactRejected(
                f"assignments[{video_id!r}]: {exc}. Known kinds: "
                + ", ".join(sorted(k.value for k in DeliverableKind))
            ) from None
        out[video_id] = DeliverableAssignment(
            deliverable_id=item["deliverable_id"],
            kind=kind,
            format_id=item["format_id"],
            version=item.get("version", ""),
        )
    return out


# -- internals -------------------------------------------------------------


def _deliverable_plan(
    deliverables: Iterable[AnalyzedDeliverable],
    store: AnalyticsStore,
    conflicts: list[IngestionIssue],
) -> tuple[AnalyzedDeliverable, ...]:
    """The deliverables this import would create, and the ones it disagrees with.

    A deliverable already recorded with different content is a conflict rather
    than an update: the title or the publication date this artifact carries
    contradicts what the store believes, and quietly replacing either would
    rewrite what every earlier observation was about.
    """
    stored = set(store.ids("deliverable"))
    out: list[AnalyzedDeliverable] = []
    for deliverable in deliverables:
        if deliverable.deliverable_id not in stored:
            out.append(deliverable)
            continue
        prior = store.get("deliverable", deliverable.deliverable_id)
        if prior.to_dict() == deliverable.to_dict():
            continue
        changed = sorted(
            key
            for key in set(prior.to_dict()) | set(deliverable.to_dict())
            if prior.to_dict().get(key) != deliverable.to_dict().get(key)
        )
        conflicts.append(
            IngestionIssue(
                IngestionIssueKind.VALUE_CONFLICT,
                f"deliverable {deliverable.deliverable_id!r} is already recorded "
                f"describing something different ({', '.join(changed)} differ). The "
                "stored record stands; correct it deliberately rather than as a side "
                "effect of an import",
            )
        )
    return tuple(out)


def _stored_source(
    source: ApiArtifactSource, store: AnalyticsStore
) -> ApiArtifactSource | None:
    if source.source_id not in store.ids("api_source"):
        return None
    return store.get("api_source", source.source_id)


def _source_conflicts(
    source: ApiArtifactSource, store: AnalyticsStore
) -> list[IngestionIssue]:
    """Refuse a source id already used for a different pull.

    Everything has to match, with no field excused. There is no `imported_at`
    here to forgive, which is the point of building the record out of the
    semantic payload: a second pull that measured the same thing is identical,
    and a record that differs under an id derived from the digest means two
    different measurements collided in sixteen hex characters.
    """
    prior = _stored_source(source, store)
    if prior is None or prior.to_dict() == source.to_dict():
        return []
    before, after = prior.to_dict(), source.to_dict()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    return [
        IngestionIssue(
            IngestionIssueKind.VALUE_CONFLICT,
            f"source {source.source_id!r} is already recorded describing a different "
            f"pull ({', '.join(changed)} differ). Two pulls under one id make every "
            "observation off them untraceable",
        )
    ]


def _record_source(source: ApiArtifactSource, store: AnalyticsStore) -> bool:
    """Write the source unless the same pull is already recorded under its id."""
    if _stored_source(source, store) is not None:
        return False
    store.put(source)
    return True


__all__ = [
    "MAX_LISTED_ISSUES",
    "ApiCommitOutcome",
    "ApiIngestionResult",
    "ArtifactDescription",
    "DeliverableAssignment",
    "UnavailableReading",
    "commit_ingestion",
    "describe_artifact",
    "ingest_artifact",
    "load_assignments",
]

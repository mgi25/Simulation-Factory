"""CSV row to auditable observation, or to a diagnostic saying why not.

## The two halves, and why they are two

`ingest_studio_export` reads a file and returns everything it would record. It
touches no store, so a dry run is the real import with the last step left off -
not a second code path that approximates it and drifts. `commit_ingestion` takes
that result, checks it against what is already recorded, and appends.

Section 21 and 22 of the brief ask for both modes; the reason to build them this
way round is that the interesting failures - an unreadable cell, an unmapped
video, a number that contradicts one we already have - are all visible before
anything is written, and a caller who reads the result before committing is
doing the review the whole layer exists to make possible.

## Nothing is imported quietly, including what is not imported

`StudioIngestionResult` reports rows read and rows accepted, and then it reports
every reason the difference exists: each blank cell, each unreadable number,
each unknown column, each video with no mapping, each monetary column that went
to finance instead. "Import successful" is not a thing this layer can say. A
caller that only ever reads `observations` still sees the count it produced
against the count of rows, and the gap is the prompt to look.

Diagnostics name a cell, not a row. Section 16 and section 25 want the same
thing for different reasons - precision and privacy - and they agree: a
reference to file, row, column and reason is enough to find the defect, and a
copy of the row is private analytics sitting in a log.

## Money leaves at the door

A Studio export carries estimated revenue, RPM and CPM. This ingester records
none of them, creates no finance record of any kind, and reports the columns as
needing finance ingestion (`monetary_columns`). Finance owns money; an analytics
ingester that produced a revenue figure would be a second answer to a question
that already has an owner, and the second answer is always the one somebody
quotes. Section 17, implemented by having nowhere to put the number: a monetary
column carries no metric in the schema, so no observation can be built from it.

## Idempotence, and the difference between a replay and a disagreement

An observation id is a digest of the things that identify the reading: the
file's own SHA-256, the row, the column, the metric, the deliverable and what
the reading covers. Re-importing the same bytes therefore produces the same ids
with the same content, and the store's append-only guard makes that a no-op -
replay is safe by construction rather than by a flag.

A *different* file claiming a different value for the same video, metric and
window is not a replay. It gets a different id, so nothing is overwritten, and
`commit_ingestion` refuses it as a conflict naming both readings. That is the
contradictory-snapshot rule from `integrity.py`, applied at the moment the
second reading arrives instead of at the next integrity run.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from ai_platform.serde import fingerprint

from .common import DataScope, Provenance, assert_prose, assert_record_id
from .deliverable import AnalyzedDeliverable
from .errors import AnalyticsError, LedgerViolation, StudioExportRejected, StudioValueError
from .metrics import MetricRegistry
from .observations import MetricObservation, observe
from .store import AnalyticsStore
from .studio_mapping import VideoIdentityMapping, is_video_id
from .studio_schema import (
    AGGREGATE_ROW_LABELS,
    ColumnMapping,
    StudioExportSchema,
    TemporalSemantics,
    recognise_schema,
)
from .studio_source import (
    ExportRow,
    StudioExportSource,
    build_source,
    read_export,
)
from .studio_values import (
    DOT_DECIMAL,
    NumberFormat,
    is_blank,
    parse_cell,
    parse_iso_day,
    quote_cell,
)
from .windows import DateRange

# The population an imported reading covers unless the caller says otherwise.
# Named rather than left blank, because `DataScope` exists to stop two readings
# of different populations being averaged, and "" would defeat it.
DEFAULT_POPULATION = "all viewers counted by the channel's own YouTube Studio export"

# How many diagnostics a rendered summary prints before it stops listing them.
MAX_LISTED_ISSUES = 20


class IssueSeverity(Enum):
    """How much a diagnostic costs. Notes are expected; errors lost a reading."""

    NOTE = "note"
    WARNING = "warning"
    ERROR = "error"


class IngestionIssueKind(Enum):
    """Every way a cell, a row or a column can fail to become an observation."""

    MALFORMED_ROW = "malformed_row"
    AGGREGATE_ROW = "aggregate_row"
    MISSING_VIDEO_ID = "missing_video_id"
    UNRESOLVED_DELIVERABLE = "unresolved_deliverable"
    MISSING_DELIVERABLE_RECORD = "missing_deliverable_record"
    DUPLICATE_ROW = "duplicate_row"
    UNREADABLE_DATE = "unreadable_date"
    DATE_OUTSIDE_RANGE = "date_outside_range"
    READING_BEFORE_PUBLICATION = "reading_before_publication"
    BLANK_VALUE = "blank_value"
    UNPARSEABLE_VALUE = "unparseable_value"
    AMBIGUOUS_NUMBER = "ambiguous_number"
    UNKNOWN_COLUMN = "unknown_column"
    UNMAPPED_COLUMN = "unmapped_column"
    MONETARY_COLUMN = "monetary_column"
    OBSERVATION_REFUSED = "observation_refused"
    VALUE_CONFLICT = "value_conflict"

    @property
    def severity(self) -> IssueSeverity:
        if self in _NOTES:
            return IssueSeverity.NOTE
        if self in _WARNINGS:
            return IssueSeverity.WARNING
        return IssueSeverity.ERROR


_NOTES = frozenset(
    {
        IngestionIssueKind.AGGREGATE_ROW,
        IngestionIssueKind.BLANK_VALUE,
        IngestionIssueKind.UNMAPPED_COLUMN,
    }
)

_WARNINGS = frozenset(
    {
        IngestionIssueKind.UNKNOWN_COLUMN,
        IngestionIssueKind.MONETARY_COLUMN,
    }
)


@dataclass(frozen=True)
class IngestionIssue:
    """One precise reason something did not become an observation.

    `raw_value` is set only where seeing the text is the point - a number that
    would not parse - and is truncated. A blank cell has nothing to quote, and a
    monetary column's figure is deliberately not quoted at all.
    """

    kind: IngestionIssueKind
    reason: str
    row_number: int | None = None
    column: str = ""
    raw_value: str = ""
    video_id: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.kind, IngestionIssueKind):
            raise AnalyticsError(
                f"issue kind must be an IngestionIssueKind, got {self.kind!r}"
            )
        object.__setattr__(self, "reason", assert_prose(self.reason, "issue reason"))
        if self.row_number is not None and (
            isinstance(self.row_number, bool) or not isinstance(self.row_number, int)
        ):
            raise AnalyticsError(f"row_number must be a line number, got {self.row_number!r}")
        object.__setattr__(self, "raw_value", quote_cell(self.raw_value) if self.raw_value else "")

    @property
    def severity(self) -> IssueSeverity:
        return self.kind.severity

    @property
    def where(self) -> str:
        parts = []
        if self.row_number is not None:
            parts.append(f"row {self.row_number}")
        if self.column:
            parts.append(f"column {self.column!r}")
        if self.video_id:
            parts.append(f"video {self.video_id}")
        return ", ".join(parts) or "the file"

    def __str__(self) -> str:
        value = f" (cell {self.raw_value!r})" if self.raw_value else ""
        return f"[{self.severity.value}] {self.kind.value} at {self.where}{value}: {self.reason}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "severity": self.severity.value,
            "reason": self.reason,
            "row_number": self.row_number,
            "column": self.column,
            "raw_value": self.raw_value,
            "video_id": self.video_id,
        }


@dataclass(frozen=True)
class UnresolvedVideo:
    """A video in the export with no entry in the mapping.

    `title_hint` is for the person writing the mapping line and for nothing
    else. It is not an identity, it is never matched on, and it is named so that
    a future reader who reaches for it is told what it is before they use it.
    """

    video_id: str
    row_numbers: tuple[int, ...]
    title_hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "video_id": self.video_id,
            "row_numbers": list(self.row_numbers),
            "title_hint": self.title_hint,
        }


@dataclass(frozen=True)
class StudioIngestionResult:
    """Everything one export produced, and everything it did not."""

    source: StudioExportSource
    schema: StudioExportSchema
    observations: tuple[MetricObservation, ...]
    rows_read: int
    rows_accepted: int
    issues: tuple[IngestionIssue, ...] = ()
    unresolved_videos: tuple[UnresolvedVideo, ...] = ()
    unknown_columns: tuple[str, ...] = ()
    unmapped_columns: tuple[str, ...] = ()
    monetary_columns: tuple[str, ...] = ()

    @property
    def rows_rejected(self) -> int:
        return self.rows_read - self.rows_accepted

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
            f"studio export {self.source.source_id} ({self.schema.schema_id})",
            f"  file        {self.source.source_ref}",
            f"  digest      sha256:{self.source.short_digest}",
            f"  channel     {self.source.channel_ref}",
            f"  covers      {self.source.coverage_sentence}",
            f"  numbers     {self.source.number_format_name}",
            f"  rows        {self.rows_read} read, {self.rows_accepted} accepted",
            f"  observations {len(self.observations)} for "
            f"{len(self.deliverable_ids)} deliverable(s)",
        ]
        if self.unknown_columns:
            lines.append(f"  unknown columns   {', '.join(self.unknown_columns)}")
        if self.unmapped_columns:
            lines.append(f"  unmapped columns  {', '.join(self.unmapped_columns)}")
        if self.monetary_columns:
            lines.append(
                f"  finance-routed    {', '.join(self.monetary_columns)} "
                "(no analytics observation; company/finance owns money)"
            )
        if self.unresolved_videos:
            lines.append(f"  unmapped videos   {len(self.unresolved_videos)}")
            for unresolved in self.unresolved_videos[:MAX_LISTED_ISSUES]:
                rows = ", ".join(str(n) for n in unresolved.row_numbers)
                lines.append(f"    {unresolved.video_id}  rows {rows}")
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
            "schema_id": self.schema.schema_id,
            "rows_read": self.rows_read,
            "rows_accepted": self.rows_accepted,
            "observation_ids": [o.observation_id for o in self.observations],
            "issues": [i.to_dict() for i in self.issues],
            "unresolved_videos": [u.to_dict() for u in self.unresolved_videos],
            "unknown_columns": list(self.unknown_columns),
            "unmapped_columns": list(self.unmapped_columns),
            "monetary_columns": list(self.monetary_columns),
        }


@dataclass(frozen=True)
class CommitOutcome:
    """What a commit actually did to the store."""

    written: tuple[str, ...] = ()
    already_present: tuple[str, ...] = ()
    conflicts: tuple[IngestionIssue, ...] = ()
    source_recorded: bool = False

    @property
    def wrote_nothing(self) -> bool:
        return not self.written and not self.source_recorded

    def render(self) -> str:
        lines = [
            f"{len(self.written)} observation(s) written, "
            f"{len(self.already_present)} already present, "
            f"{len(self.conflicts)} conflict(s)"
        ]
        for conflict in self.conflicts[:MAX_LISTED_ISSUES]:
            lines.append(f"  {conflict}")
        return "\n".join(lines)


@dataclass(frozen=True)
class ExportDescription:
    """What `studio-inspect` can say about a file without importing it."""

    source_ref: str
    digest: str
    schema: StudioExportSchema
    header: tuple[str, ...]
    row_count: int
    unknown_columns: tuple[str, ...]
    mapped_columns: tuple[tuple[str, str], ...]
    unmapped_columns: tuple[tuple[str, str], ...]
    monetary_columns: tuple[str, ...]
    required_declarations: tuple[str, ...]

    def render(self) -> str:
        lines = [
            f"{self.source_ref}",
            f"  digest      sha256:{self.digest[:12]}",
            f"  schema      {self.schema.schema_id} - {self.schema.report_name}",
            f"  rows        {self.row_count} data row(s), "
            f"{len(self.header)} column(s)",
            f"  identity    video id in {self.schema.video_id_header!r}"
            + (
                f", day in {self.schema.date_header!r}"
                if self.schema.date_header
                else ""
            ),
            "  temporal    "
            + (
                self.schema.fixed_semantics.value
                if self.schema.fixed_semantics
                else "declared by the caller; this report emits the same columns for "
                "a lifetime total and for a chosen date range"
            ),
            f"  mapped      {len(self.mapped_columns)} column(s)",
        ]
        for header, metric in self.mapped_columns:
            lines.append(f"    {header}  ->  {metric}")
        if self.unmapped_columns:
            lines.append(f"  unmapped    {len(self.unmapped_columns)} column(s)")
            for header, reason in self.unmapped_columns:
                lines.append(f"    {header}: {reason}")
        if self.monetary_columns:
            lines.append(
                "  finance     " + ", ".join(self.monetary_columns)
            )
            lines.append(
                "    monetary columns need finance ingestion; analytics records none "
                "of them"
            )
        if self.unknown_columns:
            lines.append(f"  unknown     {', '.join(self.unknown_columns)}")
            lines.append(
                "    no mapping decision exists for these; they are reported, never "
                "guessed at"
            )
        lines.append("  to import, declare:")
        for declaration in self.required_declarations:
            lines.append(f"    {declaration}")
        return "\n".join(lines)


def describe_export(
    path: str | Path, schemas: Iterable[StudioExportSchema] | None = None
) -> ExportDescription:
    """Read a file and say what it is. Writes nothing and needs no provenance."""
    export = read_export(path)
    schema = recognise_schema(export.header, schemas)
    mapped = tuple(
        (column.header, column.metric)
        for column in schema.columns
        if column.is_mapped and column.header in export.header
    )
    unmapped = tuple(
        (column.header, column.unmapped_reason)
        for column in schema.columns
        if not column.is_mapped
        and not column.monetary
        and column.header in export.header
    )
    monetary = tuple(
        column.header
        for column in schema.columns
        if column.monetary and column.header in export.header
    )
    declarations = [
        "a provenance whose source is own_studio_export, with evidence",
        "the channel this export belongs to (channel_ref)",
        "a video id to deliverable id mapping file",
        "when the export was taken (exported_at)",
        "the export's number format, if it is not dot_decimal",
    ]
    if schema.fixed_semantics is None:
        declarations.append(
            "what the file covers: cumulative_to_instant, or interval with a date range"
        )
    if schema.requires_reporting_timezone:
        declarations.append(
            "the channel's reporting timezone offset, which is where its days begin"
        )
    return ExportDescription(
        source_ref=str(path),
        digest=export.digest,
        schema=schema,
        header=export.header,
        row_count=len(export.rows),
        unknown_columns=schema.unknown_headers(export.header),
        mapped_columns=mapped,
        unmapped_columns=unmapped,
        monetary_columns=monetary,
        required_declarations=tuple(declarations),
    )


def ingest_studio_export(
    path: str | Path,
    *,
    source_id: str,
    provenance: Provenance,
    channel_ref: str,
    mapping: VideoIdentityMapping,
    exported_at: Any,
    imported_at: Any,
    deliverables: Iterable[AnalyzedDeliverable] = (),
    semantics: TemporalSemantics | None = None,
    reported_range: DateRange | None = None,
    reporting_offset_minutes: int | None = None,
    number_format: NumberFormat = DOT_DECIMAL,
    scope: DataScope | None = None,
    registry: MetricRegistry | None = None,
    schemas: Iterable[StudioExportSchema] | None = None,
    source_ref: str | None = None,
    note: str = "",
) -> StudioIngestionResult:
    """Read one Studio export into observations, reporting everything it did not.

    Writes nothing. The result is the whole of what a commit would record, so a
    dry run is this call and a real import is this call plus `commit_ingestion`.
    """
    assert_record_id(source_id, "source_id")
    if not isinstance(mapping, VideoIdentityMapping):
        raise AnalyticsError(
            "a video identity mapping is required. A row is resolved to a "
            "deliverable by an explicit entry or not at all - there is no inference "
            "from titles, publication dates or ordering"
        )
    export = read_export(path)
    schema = recognise_schema(export.header, schemas)
    source = build_source(
        source_id=source_id,
        source_ref=source_ref if source_ref is not None else str(path),
        export=export,
        schema=schema,
        provenance=provenance,
        channel_ref=channel_ref,
        number_format=number_format,
        exported_at=exported_at,
        imported_at=imported_at,
        semantics=semantics,
        reported_range=reported_range,
        reporting_offset_minutes=reporting_offset_minutes,
        note=note,
    )
    if mapping.channel_ref != source.channel_ref:
        raise StudioExportRejected(
            f"the mapping describes {mapping.channel_ref!r} and this export is from "
            f"{source.channel_ref!r}. One mapping across two channels is how a video "
            "id from one becomes a deliverable of the other"
        )

    reading_scope = scope if scope is not None else DataScope(population=DEFAULT_POPULATION)
    known = {d.deliverable_id: d for d in deliverables}
    issues: list[IngestionIssue] = []
    observations: list[MetricObservation] = []
    unresolved: dict[str, list[int]] = defaultdict(list)
    unresolved_titles: dict[str, str] = {}
    seen_rows: dict[tuple[str, str], int] = {}
    rows_accepted = 0

    unknown_columns = schema.unknown_headers(export.header)
    for header in unknown_columns:
        issues.append(
            IngestionIssue(
                IngestionIssueKind.UNKNOWN_COLUMN,
                "no mapping decision exists for this column, so nothing was read from "
                "it. Headers are matched exactly and never approximately; add it to "
                "company/analytics/studio_schema.py with a metric or with a reason",
                column=header,
            )
        )
    unmapped_columns = tuple(h for h in schema.unmapped_columns if h in export.header)
    for column in schema.columns:
        if column.header not in export.header:
            continue
        if column.monetary:
            issues.append(
                IngestionIssue(
                    IngestionIssueKind.MONETARY_COLUMN,
                    "a monetary column: it needs finance ingestion, and analytics "
                    "records no money. No value from it was read, quoted or stored",
                    column=column.header,
                )
            )
        elif not column.is_mapped:
            issues.append(
                IngestionIssue(
                    IngestionIssueKind.UNMAPPED_COLUMN,
                    column.unmapped_reason,
                    column=column.header,
                )
            )
    monetary_columns = tuple(h for h in schema.monetary_columns if h in export.header)

    for row in export.rows:
        if not row.cells:
            issues.append(
                IngestionIssue(
                    IngestionIssueKind.MALFORMED_ROW,
                    f"this row does not have {len(export.header)} cells, so its values "
                    "cannot be attached to columns without guessing which is which",
                    row_number=row.row_number,
                )
            )
            continue

        video_id = _video_id(row, schema, issues)
        if not video_id:
            continue

        deliverable_id = mapping.deliverable_for(video_id)
        if not deliverable_id:
            unresolved[video_id].append(row.row_number)
            unresolved_titles.setdefault(video_id, _title_hint(row, schema))
            issues.append(
                IngestionIssue(
                    IngestionIssueKind.UNRESOLVED_DELIVERABLE,
                    "this video has no entry in the mapping, so nothing was recorded "
                    "for it. Add the video id to the mapping file; nothing here "
                    "invents a deliverable from a title or a date",
                    row_number=row.row_number,
                    video_id=video_id,
                )
            )
            continue

        deliverable = known.get(deliverable_id)
        if deliverable is None:
            issues.append(
                IngestionIssue(
                    IngestionIssueKind.MISSING_DELIVERABLE_RECORD,
                    f"the mapping resolves this video to {deliverable_id!r}, but no "
                    "AnalyzedDeliverable for it was supplied, so a reading's age "
                    "since publication could not be derived",
                    row_number=row.row_number,
                    video_id=video_id,
                )
            )
            continue

        coverage = _coverage(row, schema, source, issues)
        if coverage is None:
            continue

        identity = (video_id, coverage.key)
        earlier = seen_rows.get(identity)
        if earlier is not None:
            issues.append(
                IngestionIssue(
                    IngestionIssueKind.DUPLICATE_ROW,
                    f"this video already appeared at row {earlier} covering the same "
                    "window; two rows for one measurement are a defect in the export, "
                    "and choosing one of them would be a guess",
                    row_number=row.row_number,
                    video_id=video_id,
                )
            )
            continue
        seen_rows[identity] = row.row_number

        produced = _row_observations(
            row=row,
            schema=schema,
            source=source,
            coverage=coverage,
            deliverable=deliverable,
            video_id=video_id,
            number_format=number_format,
            scope=reading_scope,
            registry=registry,
            issues=issues,
        )
        observations.extend(produced)
        if produced:
            rows_accepted += 1

    return StudioIngestionResult(
        source=source,
        schema=schema,
        observations=tuple(observations),
        rows_read=len(export.rows),
        rows_accepted=rows_accepted,
        issues=tuple(issues),
        unresolved_videos=tuple(
            UnresolvedVideo(
                video_id=video,
                row_numbers=tuple(rows),
                title_hint=unresolved_titles.get(video, ""),
            )
            for video, rows in sorted(unresolved.items())
        ),
        unknown_columns=unknown_columns,
        unmapped_columns=unmapped_columns,
        monetary_columns=monetary_columns,
    )


def commit_ingestion(
    result: StudioIngestionResult,
    store: AnalyticsStore,
    *,
    allow_conflicts: bool = False,
) -> CommitOutcome:
    """Append what this import produced, refusing anything that contradicts the store.

    Three outcomes per observation. An id not present is written. An id present
    with identical content is a replay of the same export and is left alone. An
    id present with different content, or a reading of the same metric of the
    same deliverable at the same instant with a different value, is a conflict -
    and by default a conflict writes nothing at all, because half an import is
    harder to reason about than none.
    """
    if not isinstance(store, AnalyticsStore):
        raise AnalyticsError(f"expected an AnalyticsStore, got {type(store).__name__}")
    existing = {o.observation_id: o for o in store.list("observation")}
    by_snapshot: dict[str, list[MetricObservation]] = defaultdict(list)
    for observation in existing.values():
        by_snapshot[observation.snapshot_key].append(observation)

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
                        f"with a different content ({prior.value} against "
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
                    f"this export says {observation.value}. One of the two is wrong; "
                    "a correction supersedes an earlier record rather than sitting "
                    "beside it",
                    column=observation.metric.name,
                )
            )
            continue
        to_write.append(observation)

    conflicts.extend(_source_conflicts(result.source, store))
    if conflicts and not allow_conflicts:
        raise LedgerViolation(
            f"{len(conflicts)} conflict(s) between this export and what is already "
            "recorded; nothing was written:\n  "
            + "\n  ".join(str(conflict) for conflict in conflicts)
        )
    recorded = _record_source(result.source, store)
    store.put_all(to_write)
    return CommitOutcome(
        written=tuple(o.observation_id for o in to_write),
        already_present=tuple(already),
        conflicts=tuple(conflicts),
        source_recorded=recorded,
    )


def _stored_source(
    source: StudioExportSource, store: AnalyticsStore
) -> StudioExportSource | None:
    if source.source_id not in store.ids("studio_source"):
        return None
    return store.get("studio_source", source.source_id)


def _source_conflicts(
    source: StudioExportSource, store: AnalyticsStore
) -> list[IngestionIssue]:
    """Refuse a source id already used for a different file or declaration.

    Everything except `imported_at` has to match, because a second import of the
    same bytes is the same export arriving again and genuinely does happen at a
    later moment. A different digest under the same id is a different file
    wearing a name that is already taken.
    """
    prior = _stored_source(source, store)
    if prior is None:
        return []
    before, after = prior.to_dict(), source.to_dict()
    before.pop("imported_at"), after.pop("imported_at")
    if before == after:
        return []
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    return [
        IngestionIssue(
            IngestionIssueKind.VALUE_CONFLICT,
            f"source {source.source_id!r} is already recorded describing a different "
            f"export ({', '.join(changed)} differ). Give this import its own source "
            "id; two files under one id make every observation off them untraceable",
        )
    ]


def _record_source(source: StudioExportSource, store: AnalyticsStore) -> bool:
    """Write the source unless the same export is already recorded under its id.

    On a replay the earlier record stands, `imported_at` and all. The first time
    the file entered the store is a fact about the store, and overwriting it
    with the latest replay would erase the only record of when we first had
    these numbers.
    """
    if _stored_source(source, store) is not None:
        return False
    store.put(source)
    return True


# -- internals -------------------------------------------------------------


@dataclass(frozen=True)
class _Coverage:
    """What one row measures, and the instant its measurement is complete."""

    observed_at: dt.datetime
    key: str
    sentence: str
    semantics: TemporalSemantics

    @property
    def breakdown(self) -> dict[str, str]:
        tag = self.semantics.measurement_tag
        return {"measurement": tag} if tag else {}


def _video_id(
    row: ExportRow, schema: StudioExportSchema, issues: list[IngestionIssue]
) -> str:
    """The row's stable video id, or "" with the reason recorded."""
    raw = row.value(schema.video_id_header).strip()
    if not raw:
        issues.append(
            IngestionIssue(
                IngestionIssueKind.MISSING_VIDEO_ID,
                "the identity column is empty. A title is never used as identity, so "
                "there is nothing here to attach a reading to",
                row_number=row.row_number,
                column=schema.video_id_header,
            )
        )
        return ""
    if raw.lower() in AGGREGATE_ROW_LABELS:
        issues.append(
            IngestionIssue(
                IngestionIssueKind.AGGREGATE_ROW,
                "an aggregate row across the whole report, not a video. Recording it "
                "would invent a deliverable that is the sum of the others",
                row_number=row.row_number,
                column=schema.video_id_header,
            )
        )
        return ""
    if not is_video_id(raw):
        issues.append(
            IngestionIssue(
                IngestionIssueKind.MISSING_VIDEO_ID,
                "the identity column does not hold a YouTube video id. Whatever else "
                "is in it - a title, a handle, a label - is not an identity, because "
                "it can be changed without the video changing",
                row_number=row.row_number,
                column=schema.video_id_header,
                raw_value=raw,
            )
        )
        return ""
    return raw


def _title_hint(row: ExportRow, schema: StudioExportSchema) -> str:
    if not schema.title_header:
        return ""
    return quote_cell(row.value(schema.title_header))


def _coverage(
    row: ExportRow,
    schema: StudioExportSchema,
    source: StudioExportSource,
    issues: list[IngestionIssue],
) -> _Coverage | None:
    """What this row covers: the export's declaration, or the row's own day."""
    if not schema.date_header:
        return _Coverage(
            observed_at=source.exported_at,
            key=source.coverage_key,
            sentence=source.coverage_sentence,
            semantics=source.semantics,
        )
    raw = row.value(schema.date_header)
    try:
        year, month, day = parse_iso_day(raw)
        when = dt.date(year, month, day)
    except (StudioValueError, ValueError) as exc:
        issues.append(
            IngestionIssue(
                IngestionIssueKind.UNREADABLE_DATE,
                str(exc),
                row_number=row.row_number,
                column=schema.date_header,
                raw_value=raw,
            )
        )
        return None
    covered = source.reported_range
    if covered is not None and not covered.contains(when):
        issues.append(
            IngestionIssue(
                IngestionIssueKind.DATE_OUTSIDE_RANGE,
                f"{when.isoformat()} is outside the {covered} the export was declared "
                "to cover, so either the declaration or the file is wrong",
                row_number=row.row_number,
                column=schema.date_header,
            )
        )
        return None
    zone = source.reporting_timezone
    if zone is None:  # pragma: no cover - build_source refuses this combination
        issues.append(
            IngestionIssue(
                IngestionIssueKind.UNREADABLE_DATE,
                "a per-day row needs the channel's reporting timezone to know when "
                "its day ended",
                row_number=row.row_number,
                column=schema.date_header,
            )
        )
        return None
    # The instant the day's measurement is complete: midnight at the start of the
    # next day, in the timezone the channel reports in. An instant is required by
    # MetricObservation, and this is the only one the row actually supports - the
    # range it covers stays on the record in `sentence` and in the breakdown.
    closed_at = dt.datetime.combine(
        when + dt.timedelta(days=1), dt.time(0, 0), tzinfo=zone
    )
    span = DateRange(when, when)
    return _Coverage(
        observed_at=closed_at,
        key=f"interval@{span}",
        sentence=(
            f"measured during {when.isoformat()} and nothing outside it; the day "
            f"closed at {closed_at.isoformat()} in the channel's reporting timezone"
        ),
        semantics=TemporalSemantics.INTERVAL,
    )


def _row_observations(
    *,
    row: ExportRow,
    schema: StudioExportSchema,
    source: StudioExportSource,
    coverage: _Coverage,
    deliverable: AnalyzedDeliverable,
    video_id: str,
    number_format: NumberFormat,
    scope: DataScope,
    registry: MetricRegistry | None,
    issues: list[IngestionIssue],
) -> list[MetricObservation]:
    out: list[MetricObservation] = []
    for column in schema.mapped_columns:
        if not row.has(column.header):
            continue
        raw = row.value(column.header)
        if is_blank(raw):
            issues.append(
                IngestionIssue(
                    IngestionIssueKind.BLANK_VALUE,
                    "the cell is empty, so this metric was not measured for this row. "
                    "It is recorded as missing rather than as zero, which is a "
                    "different fact",
                    row_number=row.row_number,
                    column=column.header,
                    video_id=video_id,
                )
            )
            continue
        try:
            value = parse_cell(raw, column.value_format, number_format)
        except StudioValueError as exc:
            issues.append(
                IngestionIssue(
                    IngestionIssueKind.AMBIGUOUS_NUMBER
                    if exc.ambiguous
                    else IngestionIssueKind.UNPARSEABLE_VALUE,
                    str(exc),
                    row_number=row.row_number,
                    column=column.header,
                    raw_value=raw,
                    video_id=video_id,
                )
            )
            continue
        denominator = _denominator(row, schema, column, number_format, issues, video_id)
        identity = {
            "source_digest": source.digest,
            "row": row.row_number,
            "column": column.header,
            "metric": column.metric,
            "deliverable": deliverable.deliverable_id,
            "video": video_id,
            "coverage": coverage.key,
        }
        try:
            out.append(
                observe(
                    f"ys-{source.short_digest}-{fingerprint(identity)}",
                    deliverable,
                    column.metric,
                    value,
                    coverage.observed_at,
                    source.observation_provenance(row.row_number, column.header),
                    scope,
                    denominator_value=denominator,
                    breakdown=coverage.breakdown,
                    note=(
                        f"youtube studio export {source.source_id}, row "
                        f"{row.row_number}, column {column.header!r}; video "
                        f"{video_id}; {coverage.sentence}"
                    ),
                    registry=registry,
                )
            )
        except AnalyticsError as exc:
            kind = (
                IngestionIssueKind.READING_BEFORE_PUBLICATION
                if "before publication" in str(exc)
                else IngestionIssueKind.OBSERVATION_REFUSED
            )
            issues.append(
                IngestionIssue(
                    kind,
                    str(exc),
                    row_number=row.row_number,
                    column=column.header,
                    video_id=video_id,
                )
            )
    return out


def _denominator(
    row: ExportRow,
    schema: StudioExportSchema,
    column: ColumnMapping,
    number_format: NumberFormat,
    issues: list[IngestionIssue],
    video_id: str,
) -> float | None:
    """The base of a rate, read from its own column and in its own shape.

    None when the column is absent, blank or unreadable. The observation is
    still recorded - losing a rate we did measure to save its denominator would
    be the worse trade - and it carries the caveat that `comparison.py` turns
    into a refusal to compare.
    """
    if not column.denominator_header:
        return None
    base = schema.mapping_for(column.denominator_header)
    if base is None or not row.has(column.denominator_header):  # pragma: no cover
        return None
    raw = row.value(column.denominator_header)
    if is_blank(raw):
        return None
    try:
        return parse_cell(raw, base.value_format, number_format)
    except StudioValueError as exc:
        issues.append(
            IngestionIssue(
                IngestionIssueKind.UNPARSEABLE_VALUE,
                f"this column is the denominator of {column.metric!r} and could not "
                f"be read, so the rate was recorded without it: {exc}",
                row_number=row.row_number,
                column=column.denominator_header,
                raw_value=raw,
                video_id=video_id,
            )
        )
        return None

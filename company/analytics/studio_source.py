"""The file an import came from, named precisely enough to go and check it.

## An imported number is not true because it came from a CSV

A row in a spreadsheet has the same authority as a number somebody typed, and
slightly more dangerous manners, because it looks retrieved. So every
observation this package imports is traceable to a `StudioExportSource`: which
file, which bytes of that file, which report shape, what the file covers, which
number convention read it, when it was exported and when it was imported. A
reader who doubts a figure can re-export, re-digest, and see whether they are
looking at the same file.

`digest` is the whole of that guarantee. It is SHA-256 over the exact bytes, so
a re-export with one corrected cell is a different source with different
observation ids, and the two readings sit side by side as a disagreement rather
than one overwriting the other.

## Own channel, asserted deliberately, or no import

Section 2 of the brief and section 19 of the analytics brief draw the same line
from opposite sides: private metrics - click-through rate, retention, watch time
- exist in this package *only* because the file is an authenticated export of a
channel we own. So `StudioExportSource` refuses any provenance whose source is
not `OWN_STUDIO_EXPORT`, and requires `channel_ref` to name which channel of
ours it is.

That is not a formality, it is the reason there is no competitor path. A
scraped table with these exact columns cannot be given a source record, so it
cannot reach the ingester, so it cannot become an observation. The refusal is
structural rather than a check somebody has to remember to call.

## What the file cannot tell you, the caller must declare

A Studio videos table emits the same columns for a lifetime total and for a
total over a chosen date range. Nothing in the bytes distinguishes them, and
guessing would turn "views during one week" into "views since publication". So
`semantics` is declared here, and `CUMULATIVE_TO_INSTANT` is refused a date
range while `INTERVAL` requires one. A per-day report declares its own semantics
and instead needs `reporting_offset_minutes`, because the day a Studio row names
is a day in the channel's reporting timezone and a day boundary assumed to be
UTC moves readings between days.

## The record holds pointers, never contents

Section 19: no raw export is copied into the repository. This record carries a
path, a digest and the original header row - enough to identify the file and to
see which columns it had - and no cell of data. Runtime state lives wherever the
caller's `state_dir` is.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from knowledge.company_os.records import Evidence

from .common import (
    DataSource,
    Provenance,
    assert_instant,
    assert_prose,
    assert_record_id,
    assert_ref,
)
from .errors import AnalyticsError, ProvenanceViolation, StudioExportRejected
from .studio_schema import StudioExportSchema, TemporalSemantics, assert_header
from .studio_values import NumberFormat, quote_cell
from .windows import DateRange

# Bumped when a change here would read the same bytes differently. Recorded on
# every source so a later reader can tell which parser produced a figure.
STUDIO_PARSER_VERSION = "studio-csv/1"

# The widest real timezone offset, in minutes either side of UTC.
MAX_OFFSET_MINUTES = 14 * 60

MINUTES_PER_HOUR = 60


@dataclass(frozen=True)
class ExportRow:
    """One data row, with the row number it occupies in the file it came from."""

    row_number: int
    cells: tuple[tuple[str, str], ...]

    def value(self, header: str) -> str:
        for name, text in self.cells:
            if name == header:
                return text
        return ""

    def has(self, header: str) -> bool:
        return any(name == header for name, _ in self.cells)


@dataclass(frozen=True)
class StudioExportFile:
    """A parsed export: its header exactly as written, its rows, and its digest."""

    header: tuple[str, ...]
    rows: tuple[ExportRow, ...]
    digest: str
    byte_count: int


def digest_bytes(data: bytes) -> str:
    """SHA-256 of the exact bytes, lowercase hex. The file's identity."""
    return hashlib.sha256(data).hexdigest()


def read_export(path: str | Path) -> StudioExportFile:
    """Read a Studio CSV without touching it, preserving rows and header names.

    UTF-8 with or without a byte-order mark. Anything else is refused by name
    rather than decoded with replacement characters, because a mangled header is
    a column that silently stops matching.
    """
    source = Path(path)
    try:
        data = source.read_bytes()
    except OSError as exc:
        raise StudioExportRejected(f"cannot read {source}: {exc}") from exc
    if not data.strip():
        raise StudioExportRejected(f"{source} is empty; there is no header to read")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise StudioExportRejected(
            f"{source} is not UTF-8 text ({exc.reason} at byte {exc.start}). Studio "
            "exports UTF-8; re-export rather than transcoding, so that the digest "
            "describes the file the platform produced"
        ) from exc

    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        raw_header = next(reader)
    except StopIteration:  # pragma: no cover - the emptiness check catches this
        raise StudioExportRejected(f"{source} has no header row") from None
    header = tuple(assert_header(name, "csv header") for name in raw_header)
    duplicates = sorted({name for name in header if header.count(name) > 1})
    if duplicates:
        raise StudioExportRejected(
            f"{source} repeats the column(s) {', '.join(duplicates)}. A repeated "
            "header makes every cell in it ambiguous, and picking one occurrence "
            "would be a guess about which the export meant"
        )

    rows: list[ExportRow] = []
    for raw in reader:
        if not raw or all(not cell.strip() for cell in raw):
            continue
        # A row whose width disagrees with the header keeps its line number and
        # loses its cells: pairing them off would attach values to the wrong
        # columns. `studio_ingest.py` reports it as a malformed row rather than
        # the file silently dropping it.
        cells = tuple(zip(header, raw)) if len(raw) == len(header) else ()
        rows.append(ExportRow(row_number=reader.line_num, cells=cells))
    return StudioExportFile(
        header=header,
        rows=tuple(rows),
        digest=digest_bytes(data),
        byte_count=len(data),
    )


@dataclass(frozen=True)
class StudioExportSource:
    """One export file, identified well enough to re-check every figure it gave.

    Immutable, like everything else this package stores. A second import of the
    same bytes rebuilds an identical record; a different file is a different
    digest and therefore a different source.
    """

    source_id: str
    source_ref: str
    digest: str
    schema_id: str
    channel_ref: str
    semantics: TemporalSemantics
    provenance: Provenance
    header: tuple[str, ...]
    number_format_name: str
    exported_at: dt.datetime
    imported_at: dt.datetime
    reported_range: DateRange | None = None
    reporting_offset_minutes: int | None = None
    parser_version: str = STUDIO_PARSER_VERSION
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "source_id", assert_record_id(self.source_id, "source_id")
        )
        object.__setattr__(self, "source_ref", assert_ref(self.source_ref, "source_ref"))
        object.__setattr__(self, "digest", _digest(self.digest))
        object.__setattr__(self, "schema_id", assert_prose(self.schema_id, "schema_id"))
        object.__setattr__(
            self, "channel_ref", assert_ref(self.channel_ref, "channel_ref")
        )
        object.__setattr__(
            self, "exported_at", assert_instant(self.exported_at, "exported_at")
        )
        object.__setattr__(
            self, "imported_at", assert_instant(self.imported_at, "imported_at")
        )
        object.__setattr__(
            self,
            "number_format_name",
            assert_prose(self.number_format_name, "number_format_name"),
        )
        object.__setattr__(
            self,
            "header",
            tuple(assert_header(name, "source header") for name in self.header),
        )
        if not self.header:
            raise AnalyticsError(
                f"source {self.source_id}: the export's header row is recorded so a "
                "later reader can see which columns the file had"
            )
        if self.note:
            object.__setattr__(self, "note", assert_prose(self.note, "source note"))
        object.__setattr__(
            self, "parser_version", assert_prose(self.parser_version, "parser_version")
        )

        if not isinstance(self.provenance, Provenance):
            raise AnalyticsError(
                f"source {self.source_id}: provenance must be a Provenance record"
            )
        self._assert_first_party()

        if not isinstance(self.semantics, TemporalSemantics):
            raise AnalyticsError(
                f"source {self.source_id}: semantics must be a TemporalSemantics, got "
                f"{self.semantics!r}"
            )
        if self.semantics is TemporalSemantics.INTERVAL:
            if not isinstance(self.reported_range, DateRange):
                raise StudioExportRejected(
                    f"source {self.source_id}: an interval export must say which days "
                    "it covers. A measurement of a bounded stretch of time with no "
                    "stated bounds is not a measurement of anything"
                )
        elif self.reported_range is not None:
            raise StudioExportRejected(
                f"source {self.source_id}: a cumulative export totals everything up "
                f"to {self.exported_at.isoformat()}, so a date range would describe "
                "a window the numbers do not respect. Declare INTERVAL semantics if "
                "the export was taken over a chosen range"
            )
        if self.reporting_offset_minutes is not None:
            offset = self.reporting_offset_minutes
            if isinstance(offset, bool) or not isinstance(offset, int):
                raise AnalyticsError(
                    f"source {self.source_id}: reporting_offset_minutes must be whole "
                    f"minutes, got {offset!r}"
                )
            if abs(offset) > MAX_OFFSET_MINUTES:
                raise AnalyticsError(
                    f"source {self.source_id}: {offset} minutes is not a timezone "
                    "offset any channel reports in"
                )

    def _assert_first_party(self) -> None:
        """One deliberate assertion of ownership, or no import.

        `effective_source` is not consulted: a manual entry transcribed from a
        Studio export is a person retyping numbers, and this parser reads a file.
        Only a record that says the bytes came off our own Studio export is
        accepted, so there is no spelling of provenance under which somebody
        else's table becomes admissible.
        """
        if self.provenance.source is not DataSource.OWN_STUDIO_EXPORT:
            raise ProvenanceViolation(
                f"source {self.source_id}: this ingester reads authenticated exports "
                f"of our own channel, and {self.provenance.source.value!r} is not "
                f"one. Only {DataSource.OWN_STUDIO_EXPORT.value!r} may be ingested "
                "here. A competitor table, a scraped page, a public view-count "
                "dataset or a third-party revenue estimate has the same columns and "
                "none of the authority: its numbers belong in research, as public "
                "figures, with no private metric among them"
            )

    @property
    def short_digest(self) -> str:
        """Twelve hex characters: enough to name the file in an id or a note."""
        return self.digest[:12]

    @property
    def reporting_timezone(self) -> dt.timezone | None:
        if self.reporting_offset_minutes is None:
            return None
        return dt.timezone(dt.timedelta(minutes=self.reporting_offset_minutes))

    @property
    def coverage_key(self) -> str:
        """What this export measures, as one string an observation id can hash."""
        if self.semantics is TemporalSemantics.CUMULATIVE_TO_INSTANT:
            return f"cumulative@{self.exported_at.isoformat()}"
        return f"interval@{self.reported_range}"

    @property
    def coverage_sentence(self) -> str:
        """The same thing in words, for the note on each observation."""
        if self.semantics is TemporalSemantics.CUMULATIVE_TO_INSTANT:
            return (
                "cumulative total since publication, as it stood when the export was "
                f"taken at {self.exported_at.isoformat()}"
            )
        assert self.reported_range is not None
        return (
            f"measured over {self.reported_range} "
            f"({self.reported_range.days} day(s)) and nothing outside it"
        )

    def evidence(self) -> Evidence:
        """The pointer every observation off this file carries."""
        return Evidence(
            kind="document",
            ref=self.source_ref,
            note=f"sha256:{self.short_digest} read by {self.parser_version}",
        )

    def row_evidence(self, row_number: int, column: str) -> Evidence:
        """The pointer to one cell. A reference, never the cell's contents."""
        return Evidence(
            kind="document",
            ref=self.source_ref,
            note=(
                f"sha256:{self.short_digest} row {row_number} column "
                f"{quote_cell(column)!r}"
            ),
        )

    def observation_provenance(self, row_number: int, column: str) -> Provenance:
        """The caller's provenance with this cell's pointer added to its evidence."""
        return Provenance(
            source=self.provenance.source,
            retrieved_by=self.provenance.retrieved_by,
            evidence=self.provenance.evidence + (self.row_evidence(row_number, column),),
            note=self.provenance.note,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_ref": self.source_ref,
            "digest": self.digest,
            "schema_id": self.schema_id,
            "channel_ref": self.channel_ref,
            "semantics": self.semantics.value,
            "provenance": self.provenance.to_dict(),
            "header": list(self.header),
            "number_format_name": self.number_format_name,
            "exported_at": self.exported_at.isoformat(),
            "imported_at": self.imported_at.isoformat(),
            "reported_range": (
                self.reported_range.to_dict() if self.reported_range else None
            ),
            "reporting_offset_minutes": self.reporting_offset_minutes,
            "parser_version": self.parser_version,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: Any) -> StudioExportSource:
        if not isinstance(data, dict):
            raise AnalyticsError(f"expected a studio source object, got {data!r}")
        try:
            covered = data.get("reported_range")
            return cls(
                source_id=data["source_id"],
                source_ref=data["source_ref"],
                digest=data["digest"],
                schema_id=data["schema_id"],
                channel_ref=data["channel_ref"],
                semantics=TemporalSemantics(data["semantics"]),
                provenance=Provenance.from_dict(data["provenance"]),
                header=tuple(data["header"]),
                number_format_name=data["number_format_name"],
                exported_at=data["exported_at"],
                imported_at=data["imported_at"],
                reported_range=DateRange.from_dict(covered) if covered else None,
                reporting_offset_minutes=data.get("reporting_offset_minutes"),
                parser_version=data.get("parser_version", STUDIO_PARSER_VERSION),
                note=data.get("note", ""),
            )
        except KeyError as exc:
            raise AnalyticsError(f"studio source: missing {exc.args[0]!r}") from None
        except ValueError as exc:
            raise AnalyticsError(f"studio source: {exc}") from None


def build_source(
    *,
    source_id: str,
    source_ref: str,
    export: StudioExportFile,
    schema: StudioExportSchema,
    provenance: Provenance,
    channel_ref: str,
    number_format: NumberFormat,
    exported_at: Any,
    imported_at: Any,
    semantics: TemporalSemantics | None = None,
    reported_range: DateRange | None = None,
    reporting_offset_minutes: int | None = None,
    note: str = "",
) -> StudioExportSource:
    """Assemble the source record, resolving the semantics the schema fixes.

    A per-day report fixes its own semantics and needs a reporting timezone; a
    videos table leaves the semantics to the caller and refuses to default,
    because the wrong default here turns a week's views into a lifetime.
    """
    if schema.fixed_semantics is not None:
        if semantics is not None and semantics is not schema.fixed_semantics:
            raise StudioExportRejected(
                f"{schema.schema_id} rows measure a bounded day, so their semantics "
                f"are {schema.fixed_semantics.value!r} and not {semantics.value!r}"
            )
        resolved = schema.fixed_semantics
    elif semantics is None:
        raise StudioExportRejected(
            f"{schema.schema_id} emits the same columns for a lifetime total and for "
            "a total over a chosen date range, so the file cannot say which this is. "
            "Declare cumulative_to_instant, or declare interval with the date range "
            "the export was taken over"
        )
    else:
        resolved = semantics
    if schema.requires_reporting_timezone and reporting_offset_minutes is None:
        raise StudioExportRejected(
            f"{schema.schema_id} names a calendar day per row, and a day begins and "
            "ends in the channel's reporting timezone. Declare that offset: a day "
            "boundary assumed to be UTC moves readings between days"
        )
    return StudioExportSource(
        source_id=source_id,
        source_ref=source_ref,
        digest=export.digest,
        schema_id=schema.schema_id,
        channel_ref=channel_ref,
        semantics=resolved,
        provenance=provenance,
        header=export.header,
        number_format_name=number_format.name,
        exported_at=exported_at,
        imported_at=imported_at,
        reported_range=reported_range,
        reporting_offset_minutes=reporting_offset_minutes,
        note=note,
    )


def offset_minutes(text: str) -> int:
    """`+02:00`, `-05:30` or `Z` as whole minutes. One spelling, no guessing."""
    body = text.strip()
    if body in ("Z", "z"):
        return 0
    sign = 1
    if body.startswith("-"):
        sign, body = -1, body[1:]
    elif body.startswith("+"):
        body = body[1:]
    else:
        raise AnalyticsError(
            f"{text!r} is not a timezone offset; write it as +HH:MM, -HH:MM or Z"
        )
    parts = body.split(":")
    if len(parts) != 2 or not all(p.isdigit() for p in parts) or len(parts[0]) != 2:
        raise AnalyticsError(
            f"{text!r} is not a timezone offset; write it as +HH:MM, -HH:MM or Z"
        )
    hours, minutes = int(parts[0]), int(parts[1])
    if minutes > 59:
        raise AnalyticsError(f"{text!r} has {minutes} minutes in its offset")
    return sign * (hours * MINUTES_PER_HOUR + minutes)


def _digest(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise AnalyticsError(
            f"digest: {value!r} is not a lowercase SHA-256 hex digest. The digest is "
            "what makes a re-export a different source rather than an overwrite"
        )
    return value

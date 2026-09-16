"""The validators and the provenance vocabulary every analytics record shares.

## Why `observed_at` is an instant and not a day

Everywhere else in Company OS a date is enough: a cost was incurred on a day, a
role was reviewed in a quarter. Analytics is the one subsystem where it is not.
Section 4 of the brief asks for a video at one hour, twenty-four hours, seven
days and thirty days, and three of those four fall on the same calendar date.
Storing a day would silently collapse them into one reading that appears to
have changed, which is exactly the overwrite this layer exists to prevent.

So `assert_instant` requires a timezone-aware datetime and normalises it to
UTC. Naive datetimes are refused rather than assumed local, because "17:00" is
four different instants depending on who typed it, and an analytics record that
guesses has invented a measurement time.

## Why provenance is an enum and not a string

Section 19 draws one hard line: our own authenticated analytics may carry
private numbers, and nothing else may. A free-text `source` field cannot hold
that line - "studio", "Studio export" and "yt studio" are three sources to any
check and one source to a reader. `DataSource` is closed, every member declares
whether it is authenticated first-party access, and `metrics.py` uses that
single boolean to decide whether a private metric is admissible.

`MANUAL_ENTRY` is the member that would break it, so it does not stand alone: a
manual entry names the underlying source it was transcribed from, and inherits
that source's authority rather than granting itself any.

## Why completeness is a field and not an absence

A metric that was not measured is missing. A metric that was measured over part
of the population is *partial*, and the difference matters more than it looks:
partial data averaged with complete data produces a number with no population.
`DataScope` carries what the reading covers and what it excludes, so a later
comparison can refuse two readings that do not describe the same thing.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from ai_platform.references import assert_reference, assert_text
from ai_platform.serde import as_date, to_jsonable
from knowledge.company_os.records import Evidence

from .errors import AnalyticsError, EvidenceRequired, ProvenanceViolation

# A record id is also a filename, so it takes the shape the knowledge store and
# the finance store already accept.
RECORD_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,79}")

# A deliverable id names something we published or rendered: `race-short-014`,
# `v30.1`, `switchyard-v2`. Wider than an identifier, narrower than free text.
DELIVERABLE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,79}")

# A tag: a metric name, a feature value, a format family. Lowercase and
# underscore-joined, so `Hook Style` and `hook style` cannot become two groups.
TAG = re.compile(r"[a-z][a-z0-9_]{0,63}")

MAX_PROSE_CHARS = 2000


class DataSource(Enum):
    """Where a number came from, and therefore what it is allowed to be.

    The order is deliberate: the three authenticated members first, then the
    two that describe somebody else's property, then the one that has to borrow
    its authority from another member.
    """

    OWN_STUDIO_EXPORT = "own_studio_export"
    OWN_ANALYTICS_API = "own_analytics_api"
    OWN_PRODUCTION_MEASUREMENT = "own_production_measurement"
    PLATFORM_PUBLIC = "platform_public"
    RESEARCH_REFERENCE = "research_reference"
    MANUAL_ENTRY = "manual_entry"

    @property
    def is_first_party(self) -> bool:
        """Is this authenticated access to something we own?

        The one question that decides whether a private metric may be stored.
        `MANUAL_ENTRY` answers False on its own and is resolved by
        `Provenance.effective_source`, which makes a transcription inherit the
        authority of what it transcribed rather than assert any of its own.
        """
        return self in _FIRST_PARTY


_FIRST_PARTY = frozenset(
    {
        DataSource.OWN_STUDIO_EXPORT,
        DataSource.OWN_ANALYTICS_API,
        DataSource.OWN_PRODUCTION_MEASUREMENT,
    }
)

# Sources that describe somebody else's video. A metric from one of these is
# public by definition, because nothing else about a stranger's video is
# readable. Kept as its own set rather than as `not is_first_party`, so that a
# new member has to be classified deliberately instead of defaulting.
_EXTERNAL = frozenset({DataSource.PLATFORM_PUBLIC, DataSource.RESEARCH_REFERENCE})


@dataclass(frozen=True)
class Provenance:
    """How a number was obtained, in enough detail to go and get it again.

    `retrieved_by` names the export, endpoint or tool - not a person, because
    the question a later reader asks is "which pull produced this", and the
    answer has to survive the person leaving.
    """

    source: DataSource
    retrieved_by: str
    evidence: tuple[Evidence, ...] = ()
    transcribed_from: DataSource | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.source, DataSource):
            raise AnalyticsError(
                f"provenance source must be a DataSource, got {self.source!r}. Known: "
                + ", ".join(sorted(item.value for item in DataSource))
            )
        object.__setattr__(
            self, "retrieved_by", assert_prose(self.retrieved_by, "retrieved_by")
        )
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))
        if self.note:
            assert_prose(self.note, "provenance note")
        if self.source is DataSource.MANUAL_ENTRY:
            if not isinstance(self.transcribed_from, DataSource):
                raise ProvenanceViolation(
                    "a manual entry must name the source it was transcribed from; a "
                    "number typed in by hand has exactly the authority of the export "
                    "it came off, and none of its own"
                )
            if self.transcribed_from is DataSource.MANUAL_ENTRY:
                raise ProvenanceViolation(
                    "a manual entry cannot be transcribed from a manual entry - the "
                    "chain has to end at something that was actually read"
                )
        elif self.transcribed_from is not None:
            raise ProvenanceViolation(
                "transcribed_from is only meaningful for a manual entry; "
                f"{self.source.value!r} names where the number was read directly"
            )
        assert_evidence_backed(
            self.evidence,
            "provenance evidence",
            "a measurement nobody can trace to an export, a page or a render is a "
            "number somebody remembered",
        )

    @property
    def effective_source(self) -> DataSource:
        """The source whose authority actually applies."""
        return self.transcribed_from or self.source

    @property
    def is_first_party(self) -> bool:
        return self.effective_source.is_first_party

    @property
    def is_external_subject(self) -> bool:
        """Does this describe somebody else's property rather than ours?"""
        return self.effective_source in _EXTERNAL

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.value,
            "retrieved_by": self.retrieved_by,
            "evidence": [to_jsonable(item) for item in self.evidence],
            "transcribed_from": (
                self.transcribed_from.value if self.transcribed_from else None
            ),
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: Any, field_name: str = "provenance") -> Provenance:
        if not isinstance(data, dict):
            raise AnalyticsError(
                f"{field_name}: expected a provenance object, got {data!r}"
            )
        try:
            transcribed = data.get("transcribed_from")
            return cls(
                source=DataSource(data["source"]),
                retrieved_by=data["retrieved_by"],
                evidence=evidence_tuple(data.get("evidence")),
                transcribed_from=DataSource(transcribed) if transcribed else None,
                note=data.get("note", ""),
            )
        except KeyError as exc:
            raise AnalyticsError(f"{field_name}: missing {exc.args[0]!r}") from None
        except ValueError as exc:
            raise AnalyticsError(f"{field_name}: {exc}") from None


@dataclass(frozen=True)
class DataScope:
    """What one reading covers, and what it is known not to cover.

    `complete` is the caller's assertion that the reading is the whole
    population it names. When it is False, `excludes` has to say what is out,
    because "partial" with no description is the same as unknown wearing a
    number.
    """

    population: str
    complete: bool = True
    excludes: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "population", assert_prose(self.population, "scope population")
        )
        object.__setattr__(self, "excludes", text_tuple(self.excludes, "scope excludes"))
        object.__setattr__(
            self, "limitations", text_tuple(self.limitations, "scope limitations")
        )
        if not isinstance(self.complete, bool):
            raise AnalyticsError(
                f"scope completeness must be a bool, got {self.complete!r}"
            )
        if not self.complete and not self.excludes:
            raise AnalyticsError(
                "an incomplete reading must say what it excludes; 'partial' with no "
                "description is an unknown with a number attached to it"
            )

    @property
    def caveats(self) -> tuple[str, ...]:
        """Every sentence a record built on this reading has to carry."""
        out = list(self.limitations)
        if not self.complete:
            out.append(
                f"incomplete reading of {self.population}; excludes "
                + "; ".join(self.excludes)
            )
        return tuple(out)

    def to_dict(self) -> dict[str, Any]:
        return {
            "population": self.population,
            "complete": self.complete,
            "excludes": list(self.excludes),
            "limitations": list(self.limitations),
        }

    @classmethod
    def from_dict(cls, data: Any, field_name: str = "scope") -> DataScope:
        if not isinstance(data, dict):
            raise AnalyticsError(f"{field_name}: expected a scope object, got {data!r}")
        try:
            return cls(
                population=data["population"],
                complete=bool(data.get("complete", True)),
                excludes=tuple(data.get("excludes") or ()),
                limitations=tuple(data.get("limitations") or ()),
            )
        except KeyError as exc:
            raise AnalyticsError(f"{field_name}: missing {exc.args[0]!r}") from None


# -- validators ------------------------------------------------------------


def assert_record_id(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not RECORD_ID.fullmatch(value):
        raise AnalyticsError(
            f"{field_name}: {value!r} must be lowercase [a-z0-9._-], start alphanumeric "
            "and be at most 80 characters - record ids are also filenames"
        )
    return value


def assert_deliverable_id(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not DELIVERABLE_ID.fullmatch(value):
        raise AnalyticsError(
            f"{field_name}: {value!r} must be lowercase [a-z0-9._-] and start "
            "alphanumeric - a deliverable id is matched exactly, so a typo has to "
            "look like a new deliverable rather than merge into an existing one"
        )
    return value


def assert_tag(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not TAG.fullmatch(value):
        raise AnalyticsError(
            f"{field_name}: {value!r} must be lowercase [a-z0-9_] and start with a "
            "letter - tags are grouping keys, and a capitalised variant would become "
            "a second group nobody intended"
        )
    return value


def assert_prose(value: Any, field_name: str) -> str:
    try:
        assert_text(value, field_name)
    except ValueError as exc:
        raise AnalyticsError(str(exc)) from exc
    if len(value) > MAX_PROSE_CHARS:
        raise AnalyticsError(
            f"{field_name}: {len(value)} characters exceeds the "
            f"{MAX_PROSE_CHARS}-character budget. Put the detail in a document and "
            "reference it as evidence."
        )
    return value


def assert_ref(value: Any, field_name: str) -> str:
    try:
        return assert_reference(value, field_name)
    except ValueError as exc:
        raise AnalyticsError(str(exc)) from exc


def optional_ref(value: Any, field_name: str) -> str:
    if value in (None, ""):
        return ""
    return assert_ref(value, field_name)


def assert_day(value: Any, field_name: str) -> dt.date:
    try:
        return as_date(value, field_name)
    except (TypeError, ValueError) as exc:
        raise AnalyticsError(f"{field_name}: {exc}") from exc


def optional_day(value: Any, field_name: str) -> dt.date | None:
    return None if value is None else assert_day(value, field_name)


def assert_instant(value: Any, field_name: str) -> dt.datetime:
    """A timezone-aware moment, normalised to UTC.

    A naive datetime is refused rather than assumed. The refusal names the fix,
    because the common case is a caller who has a local timestamp and simply
    has not said which offset it carries.
    """
    if isinstance(value, str):
        text = value.strip()
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        try:
            value = dt.datetime.fromisoformat(text)
        except ValueError as exc:
            raise AnalyticsError(
                f"{field_name}: {value!r} is not an ISO 8601 timestamp: {exc}"
            ) from exc
    if not isinstance(value, dt.datetime):
        raise AnalyticsError(
            f"{field_name}: expected a datetime, got {type(value).__name__}. An "
            "observation is taken at an instant; a date would collapse the one-hour "
            "and twenty-four-hour readings of the same video into one"
        )
    if value.tzinfo is None or value.utcoffset() is None:
        raise AnalyticsError(
            f"{field_name}: {value.isoformat()} has no timezone. Attach one - "
            "datetime.timezone.utc if the reading is already UTC - because the same "
            "wall clock is a different instant in every office that reports it"
        )
    return value.astimezone(dt.timezone.utc)


def optional_instant(value: Any, field_name: str) -> dt.datetime | None:
    return None if value is None else assert_instant(value, field_name)


def text_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        raise AnalyticsError(
            f"{field_name}: expected a sequence of statements, got the string {value!r}"
        )
    return tuple(assert_prose(item, field_name) for item in value)


def tag_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        raise AnalyticsError(
            f"{field_name}: expected a sequence of tags, got the string {value!r}"
        )
    return tuple(assert_tag(item, field_name) for item in value)


def ref_tuple(
    value: Any, field_name: str, *, validator: Callable[[Any, str], str] = assert_ref
) -> tuple[str, ...]:
    """Normalise a sequence of references, rejecting a bare string outright.

    A bare string is rejected rather than wrapped, because `evidence_refs="x.md"`
    would otherwise silently become four one-character references.
    """
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        raise AnalyticsError(
            f"{field_name}: expected a sequence of references, got the string {value!r}"
        )
    if not isinstance(value, Iterable):
        raise AnalyticsError(
            f"{field_name}: expected a sequence of references, got {value!r}"
        )
    return tuple(validator(item, field_name) for item in value)


def evidence_tuple(value: Any) -> tuple[Evidence, ...]:
    if not value:
        return ()
    if isinstance(value, (str, bytes, Evidence)):
        raise AnalyticsError("evidence must be a sequence of Evidence records")
    out: list[Evidence] = []
    for item in value:
        if isinstance(item, Evidence):
            out.append(item)
        elif isinstance(item, dict):
            try:
                out.append(Evidence.from_dict(item))
            except (KeyError, ValueError) as exc:
                raise AnalyticsError(f"malformed evidence: {exc}") from exc
        else:
            raise AnalyticsError(
                f"evidence must be Evidence records, got {type(item).__name__}"
            )
    return tuple(out)


def assert_evidence_backed(
    evidence: tuple[Evidence, ...], field_name: str, why: str
) -> None:
    """Refuse a claim that points at nothing checkable."""
    if not evidence:
        raise EvidenceRequired(
            f"{field_name}: at least one piece of evidence is required - {why}"
        )


def record_to_dict(record: Any) -> dict[str, Any]:
    """Canonical JSON form for an analytics record.

    Walks the record's own fields so that the datetimes analytics uses encode as
    ISO 8601 with their offset. `ai_platform.serde.to_jsonable` handles
    everything else and refuses what it does not know, which is what keeps a
    stray object out of a stored record.
    """
    from dataclasses import fields as dataclass_fields

    return {f.name: _encode(getattr(record, f.name)) for f in dataclass_fields(record)}


def _encode(value: Any) -> Any:
    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, Evidence):
        return to_jsonable(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict) and not isinstance(value, type):
        return to_dict()
    if isinstance(value, (list, tuple)):
        return [_encode(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _encode(v) for k, v in sorted(value.items())}
    return to_jsonable(value)

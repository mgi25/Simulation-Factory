"""The validators every finance record shares, defined once.

Constitution rule 15 stores a canonical fact once, and that applies to the code
that checks one. Ten record types below need the same handful of things: an id
that is also a filename, a date that is really a date, prose that is not empty,
and evidence that is really evidence.

## The two validators worth reading

`assert_evidence_backed` is the one that carries section 3 of the brief: no
monetary record without evidence. A cost with no receipt is a number somebody
remembered, and the whole point of this layer is that a second person can go and
check every figure it reports. Enforced at construction, not on request - a
validator that runs later is a validator that does not run.

`assert_human` is the one that carries section 27. Finance records that a spend
was proposed and what the evidence was; a human decides. So a decision has to
name a person, and the names a machine would sign with are refused by a list.

## Why there is a separate subject reference

A cost belongs to something - a task, a video, a format, an experiment, a
reusable tool, the company. Storing that as free text would mean `race-shorts`,
`Race Shorts` and `race_shorts` are three formats in any summary that groups by
it. `SubjectRef` makes the kind explicit and the id a validated identifier, so
grouping is exact and a typo is a new subject a reader can see rather than a
silent split in the totals.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
import re
from typing import Any, Callable

from ai_platform.references import assert_reference, assert_text
from ai_platform.serde import as_date, to_jsonable
from knowledge.company_os.records import Evidence

from .errors import EvidenceRequired, FinanceError

# A record id is also a filename, so it takes the shape the knowledge store
# already accepts: lowercase, dots and dashes, alphanumeric start.
RECORD_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,79}")

# A subject id names something the company works on. Wider than the workforce
# identifier because a video id is legitimately `race-short-014`, not
# `race_short_014`, and forcing snake_case here would mean rewriting every
# reference on the way in.
SUBJECT_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,79}")

MAX_PROSE_CHARS = 2000

# Names a machine signs with. Same intent as
# `company.org_intelligence.common.AUTOMATIC_MARKERS`, restated here rather than
# imported so that `company/finance` depends on no other Company OS subsystem
# and the capsule edge from organizational intelligence to finance stays acyclic.
AUTOMATIC_MARKERS = frozenset(
    {
        "auto",
        "automatic",
        "automated",
        "automation",
        "company_os",
        "company os",
        "finance",
        "finance_os",
        "self",
        "system",
        "this subsystem",
    }
)


class SubjectKind(Enum):
    """What a cost, a revenue line or a budget is about.

    Deliberately closed, and deliberately without a COMPETITOR member: section 4
    says competitor data must never become our revenue, and the cheapest way to
    guarantee that is for our records to have no way to name one.
    """

    COMPANY = "company"
    DEPARTMENT = "department"
    PROJECT = "project"
    FORMAT = "format"
    VIDEO = "video"
    TASK = "task"
    EXPERIMENT = "experiment"
    TOOL = "tool"
    ASSET = "asset"
    SERVICE = "service"


@dataclass(frozen=True)
class SubjectRef:
    """What a record is about: a kind from a closed set, and a validated id."""

    kind: SubjectKind
    id: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, SubjectKind):
            raise FinanceError(
                f"subject kind must be a SubjectKind, got {self.kind!r}. Known: "
                + ", ".join(sorted(item.value for item in SubjectKind))
            )
        if not isinstance(self.id, str) or not SUBJECT_ID.fullmatch(self.id):
            raise FinanceError(
                f"subject id {self.id!r} must be lowercase [a-z0-9._-], start "
                "alphanumeric and be at most 80 characters"
            )

    @property
    def key(self) -> str:
        """The grouping key. Two subjects group together only if both parts match."""
        return f"{self.kind.value}:{self.id}"

    def __str__(self) -> str:
        return self.key

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind.value, "id": self.id}

    @classmethod
    def from_dict(cls, data: Any, field: str = "subject") -> SubjectRef:
        if not isinstance(data, dict):
            raise FinanceError(f"{field}: expected a subject object, got {data!r}")
        try:
            return cls(kind=SubjectKind(data["kind"]), id=data["id"])
        except KeyError as exc:
            raise FinanceError(f"{field}: missing {exc.args[0]!r}") from None
        except ValueError as exc:
            raise FinanceError(f"{field}: {exc}") from None


def record_to_dict(record: Any) -> dict[str, Any]:
    """Canonical JSON form for a finance record, with amounts as text.

    `ai_platform.serde.to_jsonable` handles dataclasses, enums, dates and
    containers, and deliberately refuses anything else - including `Decimal`,
    because there is no one right way to encode one. For money there is: the
    digits as a string, so a JSON number never becomes a float on the way back
    in. This walks the record's own fields, encodes `Money` and `Decimal` that
    way, and hands everything else to `to_jsonable` unchanged.

    Defined once here rather than in each record class, for the reason
    constitution rule 15 gives: eleven copies of this loop is eleven places for
    a float to sneak back into a stored amount.
    """
    from dataclasses import fields as dataclass_fields

    return {
        field.name: _encode_value(getattr(record, field.name))
        for field in dataclass_fields(record)
    }


def _encode_value(value: Any) -> Any:
    from decimal import Decimal

    from .money import Money

    if isinstance(value, Money):
        return value.to_dict()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (list, tuple)):
        return [_encode_value(item) for item in value]
    return to_jsonable(value)


def assert_record_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not RECORD_ID.fullmatch(value):
        raise FinanceError(
            f"{field}: {value!r} must be lowercase [a-z0-9._-], start alphanumeric and "
            "be at most 80 characters - record ids are also filenames"
        )
    return value


def assert_prose(value: Any, field: str) -> str:
    """Non-empty prose with a ceiling. A record field is a statement, not a report."""
    try:
        assert_text(value, field)
    except ValueError as exc:
        raise FinanceError(str(exc)) from exc
    if len(value) > MAX_PROSE_CHARS:
        raise FinanceError(
            f"{field}: {len(value)} characters exceeds the {MAX_PROSE_CHARS}-character "
            "budget. Put the detail in a document and reference it as evidence."
        )
    return value


def assert_ref(value: Any, field: str) -> str:
    try:
        return assert_reference(value, field)
    except ValueError as exc:
        raise FinanceError(str(exc)) from exc


def optional_ref(value: Any, field: str) -> str:
    if value in (None, ""):
        return ""
    return assert_ref(value, field)


def assert_day(value: Any, field: str) -> dt.date:
    try:
        return as_date(value, field)
    except (TypeError, ValueError) as exc:
        raise FinanceError(f"{field}: {exc}") from exc


def optional_day(value: Any, field: str) -> dt.date | None:
    return None if value is None else assert_day(value, field)


def assert_human(value: Any, field: str) -> str:
    """Refuse a decision or an approval that names no person.

    Section 27: finance does not approve itself. A spend decision signed
    `system` is a spend nobody agreed to, and the list above is what that looks
    like when it is written down.
    """
    try:
        text = assert_text(value, field)
    except ValueError as exc:
        raise FinanceError(str(exc)) from exc
    if text.strip().lower() in AUTOMATIC_MARKERS:
        raise FinanceError(
            f"{field}: {text!r} is not a person. Finance records the proposal and the "
            "evidence; approving a spend is a named human act"
        )
    return text


def text_tuple(value: Any, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        raise FinanceError(f"{field}: expected a sequence of statements, got a string")
    return tuple(assert_prose(item, field) for item in value)


def ref_tuple(
    value: Any, field: str, *, validator: Callable[[Any, str], str] = assert_ref
) -> tuple[str, ...]:
    """Normalise a sequence of references, rejecting a bare string outright.

    A bare string is rejected rather than wrapped, because `evidence_refs="x.md"`
    would otherwise silently become four one-character references.
    """
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        raise FinanceError(
            f"{field}: expected a sequence of references, got the string {value!r}"
        )
    if not isinstance(value, Iterable):
        raise FinanceError(f"{field}: expected a sequence of references, got {value!r}")
    return tuple(validator(item, field) for item in value)


def evidence_tuple(value: Any) -> tuple[Evidence, ...]:
    if not value:
        return ()
    if isinstance(value, (str, bytes, Evidence)):
        raise FinanceError("evidence must be a sequence of Evidence records")
    out: list[Evidence] = []
    for item in value:
        if isinstance(item, Evidence):
            out.append(item)
        elif isinstance(item, dict):
            try:
                out.append(Evidence.from_dict(item))
            except (KeyError, ValueError) as exc:
                raise FinanceError(f"malformed evidence: {exc}") from exc
        else:
            raise FinanceError(
                f"evidence must be Evidence records, got {type(item).__name__}"
            )
    return tuple(out)


def assert_evidence_backed(evidence: tuple[Evidence, ...], field: str, why: str) -> None:
    """Refuse a monetary claim that points at nothing checkable."""
    if not evidence:
        raise EvidenceRequired(f"{field}: at least one piece of evidence is required - {why}")


def evidence_kinds(evidence: Iterable[Evidence]) -> frozenset[str]:
    return frozenset(item.kind for item in evidence)

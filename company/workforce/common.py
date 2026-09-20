"""The validators every workforce record shares, defined once.

Ten record types in this package all need the same four things: an identifier
that is also a filename, a date that is really a date, prose that is not empty,
and a tuple of `Evidence` that is really evidence. Constitution rule 15 stores a
canonical fact once; the same applies to the code that checks one.

`assert_evidence_backed` is the one worth reading. Section 4 of the workforce
brief says a gap does not exist because someone thinks a job title sounds
useful, and section 8 says do not fabricate scores. Both reduce to the same
mechanic: the record class refuses to be constructed without a pointer to
something a second person could go and check. A validator that runs later, on
request, is a validator that does not run.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable
from typing import Any, Callable

from ai_platform.references import assert_reference, assert_text
from ai_platform.serde import as_date
from knowledge.company_os.records import Evidence

from .errors import WorkforceError

# An employee id, a capability id, a department: the snake_case identifier the
# org registry already validates. Kept identical to
# `company.validation.bootstrap._IDENTIFIER` on purpose - two vocabularies for
# the same names would be the duplication rule 15 forbids.
IDENTIFIER = re.compile(r"[a-z][a-z0-9_]*")

# A record id is also a filename, so it accepts the wider set the knowledge
# store accepts: lowercase, dots and dashes, alphanumeric start.
RECORD_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,79}")

MAX_PROSE_CHARS = 2000


def assert_identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise WorkforceError(
            f"{field}: {value!r} must be a lowercase snake_case identifier, the same "
            "shape org_registry.yaml uses for employees and capabilities"
        )
    return value


def assert_record_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not RECORD_ID.fullmatch(value):
        raise WorkforceError(
            f"{field}: {value!r} must be lowercase [a-z0-9._-], start alphanumeric and "
            "be at most 80 characters - record ids are also filenames"
        )
    return value


def assert_prose(value: Any, field: str) -> str:
    """Non-empty prose with a ceiling. A record field is a statement, not a report."""
    try:
        assert_text(value, field)
    except ValueError as exc:
        raise WorkforceError(str(exc)) from exc
    if len(value) > MAX_PROSE_CHARS:
        raise WorkforceError(
            f"{field}: {len(value)} characters exceeds the {MAX_PROSE_CHARS}-character "
            "budget. Put the detail in a document and reference it as evidence."
        )
    return value


def assert_ref(value: Any, field: str) -> str:
    try:
        return assert_reference(value, field)
    except ValueError as exc:
        raise WorkforceError(str(exc)) from exc


def optional_ref(value: Any, field: str) -> str:
    if value in (None, ""):
        return ""
    return assert_ref(value, field)


def assert_day(value: Any, field: str) -> dt.date:
    try:
        return as_date(value, field)
    except (TypeError, ValueError) as exc:
        raise WorkforceError(f"{field}: {exc}") from exc


def id_tuple(
    value: Any,
    field: str,
    *,
    validator: Callable[[Any, str], str] = assert_identifier,
    unique: bool = True,
    sort: bool = False,
) -> tuple[str, ...]:
    """Normalise a sequence of identifiers, rejecting a bare string outright.

    A bare string is rejected rather than wrapped: `capabilities="framing"`
    would otherwise silently become eight one-character capabilities.
    """
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        raise WorkforceError(f"{field}: expected a sequence of ids, got the string {value!r}")
    if not isinstance(value, Iterable):
        raise WorkforceError(f"{field}: expected a sequence of ids, got {value!r}")
    items = tuple(validator(item, field) for item in value)
    if unique and len(set(items)) != len(items):
        duplicates = sorted({item for item in items if items.count(item) > 1})
        raise WorkforceError(f"{field}: duplicate entries: {', '.join(duplicates)}")
    return tuple(sorted(items)) if sort else items


def text_tuple(value: Any, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        raise WorkforceError(f"{field}: expected a sequence of statements, got a string")
    return tuple(assert_prose(item, field) for item in value)


def evidence_tuple(value: Any) -> tuple[Evidence, ...]:
    if not value:
        return ()
    if isinstance(value, (str, bytes, Evidence)):
        raise WorkforceError("evidence must be a sequence of Evidence records")
    out: list[Evidence] = []
    for item in value:
        if isinstance(item, Evidence):
            out.append(item)
        elif isinstance(item, dict):
            try:
                out.append(Evidence.from_dict(item))
            except (KeyError, ValueError) as exc:
                raise WorkforceError(f"malformed evidence: {exc}") from exc
        else:
            raise WorkforceError(f"evidence must be Evidence records, got {type(item).__name__}")
    return tuple(out)


def assert_evidence_backed(evidence: tuple[Evidence, ...], field: str, why: str) -> None:
    """Refuse a claim that points at nothing checkable."""
    if not evidence:
        raise WorkforceError(f"{field}: at least one piece of evidence is required - {why}")


def evidence_kinds(evidence: Iterable[Evidence]) -> frozenset[str]:
    return frozenset(item.kind for item in evidence)

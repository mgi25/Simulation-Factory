"""Field guards shared by every delegation record, written down once.

The same shapes appear across this package — a seat id, a record id, a date
supplied by the caller, a bounded tuple of prose — so they live here rather
than being re-derived per module.

## `assert_named_person`

`company/engineering/common.py` and `company/org_intelligence/common.py` each
carry a copy of this guard, and each explains that importing the other would
add a subsystem edge to carry one function. This is the third copy, for the
same reason and against the same vocabulary. It matters here more than in
either of those: the one lie a delegation subsystem could tell is writing a
CEO approval in the CEO's absence, and the guard fails on the single field such
a record must fill in.

The marker set is imported from `company.engineering.common` deliberately —
this package already depends on nothing in `company/engineering`, so the list
is duplicated here in full rather than importing it. If one list grows, all
three should; the integration gate probes two of them and this package's own
tests probe the third.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from ai_platform.references import ReferenceViolation, assert_reference
from ai_platform.serde import as_date

from .errors import DelegationError


RECORD_ID = re.compile(r"[a-z0-9][a-z0-9._-]{2,63}")
"""A record identifier: lowercase, pointer-shaped, long enough to be readable."""

SEAT_ID = re.compile(r"[a-z][a-z0-9_]{1,47}")
"""A seat name: lowercase with underscores, the same shape as an employee id."""

# Kept in step with company/engineering/common.AUTOMATIC_MARKERS and
# company/org_intelligence/common.AUTOMATIC_MARKERS.
AUTOMATIC_MARKERS = frozenset(
    {
        "agent",
        "ai",
        "automated",
        "automatic",
        "bot",
        "claude",
        "claude_code",
        "codex",
        "company",
        "company_os",
        "company os",
        "delegation",
        "delegation_policy",
        "engineering",
        "engineering_execution",
        "executive",
        "gpt",
        "llm",
        "model",
        "self",
        "system",
        "the system",
        "this subsystem",
    }
)


def assert_record_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not RECORD_ID.fullmatch(value):
        raise DelegationError(
            f"{field}: {value!r} must be a lowercase identifier of 3-64 characters "
            "using letters, digits, dot, underscore or hyphen"
        )
    return value


def assert_seat_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SEAT_ID.fullmatch(value):
        raise DelegationError(
            f"{field}: {value!r} must be a lowercase seat name of 2-48 characters "
            "using letters, digits and underscore"
        )
    return value


def assert_prose(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DelegationError(f"{field} must be non-empty text")
    return value.strip()


def assert_ref(value: Any, field: str) -> str:
    try:
        return assert_reference(value, field).strip()
    except ReferenceViolation as exc:  # one error type at this boundary
        raise DelegationError(str(exc)) from exc


def text_tuple(values: Any, field: str, *, limit: int = 32) -> tuple[str, ...]:
    """A tuple of non-empty text, order preserved, length bounded."""
    if values is None:
        return ()
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
        raise DelegationError(f"{field} must be a list of strings")
    if len(values) > limit:
        raise DelegationError(
            f"{field}: {len(values)} items exceeds the {limit} a record may carry"
        )
    return tuple(
        assert_prose(item, f"{field}[{index}]") for index, item in enumerate(values)
    )


def ref_tuple(values: Any, field: str, *, limit: int = 32) -> tuple[str, ...]:
    """A tuple of pointers, de-duplicated and sorted so two equal sets hash alike."""
    if values is None:
        return ()
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
        raise DelegationError(f"{field} must be a list of references")
    if len(values) > limit:
        raise DelegationError(
            f"{field}: {len(values)} items exceeds the {limit} a record may carry"
        )
    refs = {assert_ref(item, f"{field}[{index}]") for index, item in enumerate(values)}
    return tuple(sorted(refs))


def name_tuple(values: Any, field: str, *, limit: int = 32) -> tuple[str, ...]:
    """A sorted, de-duplicated tuple of lowercase names."""
    if values is None:
        return ()
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
        raise DelegationError(f"{field} must be a list of names")
    if len(values) > limit:
        raise DelegationError(
            f"{field}: {len(values)} items exceeds the {limit} a record may carry"
        )
    names = set()
    for index, item in enumerate(values):
        text = assert_prose(item, f"{field}[{index}]")
        if text != text.lower():
            raise DelegationError(f"{field}[{index}]: {text!r} must be lowercase")
        names.add(text)
    return tuple(sorted(names))


def seat_tuple(values: Any, field: str, *, limit: int = 32) -> tuple[str, ...]:
    """Seat ids **in the order given**, validated and refused if one repeats.

    Deliberately distinct from `name_tuple`, which sorts. An escalation chain is
    a sequence: sorting it alphabetically puts `ceo` first and makes "the last
    seat considered" mean nothing — and that is the field `record_decision`
    reads to attribute a rejected request to the seat it finally reached.
    """
    if values is None:
        return ()
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
        raise DelegationError(f"{field} must be a list of seat ids")
    if len(values) > limit:
        raise DelegationError(
            f"{field}: {len(values)} items exceeds the {limit} a record may carry"
        )
    seen: list[str] = []
    for index, item in enumerate(values):
        seat = assert_seat_id(item, f"{field}[{index}]")
        if seat in seen:
            raise DelegationError(
                f"{field}: {seat!r} appears twice. A chain that revisits a seat is a "
                "circular escalation, not a longer one."
            )
        seen.append(seat)
    return tuple(seen)


def assert_day(value: Any, field: str) -> dt.date:
    """A calendar day, supplied rather than read from a clock.

    Every record here takes its date from its caller, for the reason
    `company/engineering/common.py` gives: a record that stamped itself would
    make two runs over the same evidence produce two different fingerprints,
    and the fingerprints are what prove a policy did not change underneath a
    decision.
    """
    try:
        return as_date(value, field)
    except (TypeError, ValueError) as exc:
        raise DelegationError(f"{field}: {value!r} is not an ISO-8601 date") from exc


def assert_named_person(value: Any, field: str) -> str:
    """Refuse an approval that names no person."""
    text = assert_prose(value, field)
    if text.strip().lower() in AUTOMATIC_MARKERS:
        raise DelegationError(
            f"{field}: {text!r} is not a person. A delegation record may say which "
            "seat would decide; a CEO approval is a named human act."
        )
    return text


def positive_int(value: Any, field: str, *, minimum: int = 1, maximum: int = 64) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        raise DelegationError(
            f"{field} must be an integer between {minimum} and {maximum}"
        )
    return value


__all__ = [
    "AUTOMATIC_MARKERS",
    "RECORD_ID",
    "SEAT_ID",
    "assert_day",
    "assert_named_person",
    "assert_prose",
    "assert_record_id",
    "assert_ref",
    "assert_seat_id",
    "name_tuple",
    "positive_int",
    "ref_tuple",
    "seat_tuple",
    "text_tuple",
]

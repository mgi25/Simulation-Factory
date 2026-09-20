"""Shared field guards for the engineering records, written down once.

Every record in this package is a frozen dataclass validated in
`__post_init__`, and they all need the same handful of checks. They live here
so that "a work order id" and "a review id" cannot drift into two different
ideas of what an identifier is.

## `assert_named_person`

A CEO decision has to name a person. The guard mirrors
`company/org_intelligence/common.assert_human`, which the integration gate
probes for the same purpose in that subsystem, and it is a second
implementation on purpose: importing it would add a
`company/engineering -> company/org_intelligence` subsystem edge to carry one
function, and this package already refuses one such edge (see
`company/engineering/README.md`). The marker set is deliberately the same
vocabulary; if either list grows, both should.

It is not a proof of humanity — nothing here can be. It refuses the one lie
this package would tell if it ever wrote its own approval.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from ai_platform.references import ReferenceViolation, assert_reference
from ai_platform.serde import as_date

from .errors import EngineeringError


RECORD_ID = re.compile(r"[a-z0-9][a-z0-9._-]{2,63}")
"""A record identifier: lowercase, pointer-shaped, long enough to be readable."""

# The vocabulary a record uses when it is about to claim a machine decided
# something. Kept in step with company/org_intelligence/common.AUTOMATIC_MARKERS.
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
        "engineering",
        "engineering_execution",
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
        raise EngineeringError(
            f"{field}: {value!r} must be a lowercase identifier of 3-64 characters "
            "using letters, digits, dot, underscore or hyphen"
        )
    return value


def assert_prose(value: Any, field: str) -> str:
    """Non-empty text. May wrap; an objective is allowed to be a paragraph."""
    if not isinstance(value, str) or not value.strip():
        raise EngineeringError(f"{field} must be non-empty text")
    return value.strip()


def assert_ref(value: Any, field: str) -> str:
    """A single-line pointer, held to the platform's reference budget."""
    try:
        return assert_reference(value, field).strip()
    except ReferenceViolation as exc:  # one error type at this boundary
        raise EngineeringError(str(exc)) from exc


def text_tuple(values: Any, field: str, *, limit: int = 64) -> tuple[str, ...]:
    """A tuple of non-empty text, order preserved, length bounded."""
    if values is None:
        return ()
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
        raise EngineeringError(f"{field} must be a list of strings")
    if len(values) > limit:
        raise EngineeringError(
            f"{field}: {len(values)} items exceeds the {limit} a record may carry"
        )
    return tuple(assert_prose(item, f"{field}[{index}]") for index, item in enumerate(values))


def ref_tuple(values: Any, field: str, *, limit: int = 64) -> tuple[str, ...]:
    """A tuple of pointers, de-duplicated and sorted so two equal sets hash alike."""
    if values is None:
        return ()
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
        raise EngineeringError(f"{field} must be a list of references")
    if len(values) > limit:
        raise EngineeringError(
            f"{field}: {len(values)} items exceeds the {limit} a record may carry"
        )
    refs = {assert_ref(item, f"{field}[{index}]") for index, item in enumerate(values)}
    return tuple(sorted(refs))


def assert_day(value: Any, field: str) -> dt.date:
    """A calendar day, supplied rather than read from a clock.

    Every record in this package takes its date from its caller. A record that
    stamped itself would make two runs over the same evidence produce two
    different fingerprints, and the fingerprints are what prove a work order
    did not change.
    """
    try:
        return as_date(value, field)
    except (TypeError, ValueError) as exc:
        raise EngineeringError(f"{field}: {value!r} is not an ISO-8601 date") from exc


def assert_named_person(value: Any, field: str) -> str:
    """Refuse a decision or an approval that names no person."""
    text = assert_prose(value, field)
    if text.strip().lower() in AUTOMATIC_MARKERS:
        raise EngineeringError(
            f"{field}: {text!r} is not a person. Company OS prepares, verifies and "
            "reports engineering work; approving it is a named human act."
        )
    return text


def positive_int(value: Any, field: str, *, minimum: int = 1, maximum: int = 16) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        raise EngineeringError(
            f"{field} must be an integer between {minimum} and {maximum}"
        )
    return value


__all__ = [
    "AUTOMATIC_MARKERS",
    "RECORD_ID",
    "assert_day",
    "assert_named_person",
    "assert_prose",
    "assert_record_id",
    "assert_ref",
    "positive_int",
    "ref_tuple",
    "text_tuple",
]

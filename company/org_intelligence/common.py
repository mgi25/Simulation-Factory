"""The validators, borrowed rather than rewritten, and the words this package
refuses to accept from a machine.

## Why this module is thin on purpose

`company/workforce/common.py` already decides what an identifier is, what a
record id is, how long a prose field may be, and what counts as evidence. Those
are the same answers here - an employee id is an employee id - and constitution
rule 15 stores a canonical fact once. So this module re-exports that logic and
does exactly one thing of its own: it converts `WorkforceError` into
`OrgIntelligenceError` at the boundary, so a caller catching one package's
errors does not silently catch the other's.

## The automatic markers

`assert_human` is the mechanic behind "this subsystem must not approve itself".
A decision carries the name of whoever made it; if that name is `automatic`,
`system`, `org_intelligence` or any of the rest, the record refuses to exist.
It is a deliberately small list of the words a program would reach for when
writing its own approval, and it fails on the field that a real approval has to
fill in anyway.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from collections.abc import Iterable
from typing import Any, Callable, TypeVar

from company.workforce.common import (
    MAX_PROSE_CHARS,
    assert_day as _assert_day,
    assert_evidence_backed as _assert_evidence_backed,
    assert_identifier as _assert_identifier,
    assert_prose as _assert_prose,
    assert_record_id as _assert_record_id,
    assert_ref as _assert_ref,
    evidence_tuple as _evidence_tuple,
    id_tuple as _id_tuple,
    optional_ref as _optional_ref,
    text_tuple as _text_tuple,
)
from company.workforce.errors import WorkforceError
from knowledge.company_os.records import Evidence

from .errors import AdvisoryViolation, OrgIntelligenceError

T = TypeVar("T")

__all__ = [
    "MAX_PROSE_CHARS",
    "assert_day",
    "assert_evidence_backed",
    "assert_human",
    "assert_identifier",
    "assert_prose",
    "assert_record_id",
    "assert_ref",
    "enum_value",
    "evidence_tuple",
    "id_tuple",
    "nonempty_text_tuple",
    "optional_ref",
    "positive_int",
    "ratio",
    "rendered_configuration",
    "text_tuple",
]


def _rewrap(call: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    try:
        return call(*args, **kwargs)
    except WorkforceError as exc:
        raise OrgIntelligenceError(str(exc)) from exc


def assert_identifier(value: Any, field: str) -> str:
    return _rewrap(_assert_identifier, value, field)


def assert_record_id(value: Any, field: str) -> str:
    return _rewrap(_assert_record_id, value, field)


def assert_prose(value: Any, field: str) -> str:
    return _rewrap(_assert_prose, value, field)


def assert_ref(value: Any, field: str) -> str:
    return _rewrap(_assert_ref, value, field)


def optional_ref(value: Any, field: str) -> str:
    return _rewrap(_optional_ref, value, field)


def assert_day(value: Any, field: str) -> dt.date:
    return _rewrap(_assert_day, value, field)


def id_tuple(value: Any, field: str, **kwargs: Any) -> tuple[str, ...]:
    return _rewrap(_id_tuple, value, field, **kwargs)


def text_tuple(value: Any, field: str) -> tuple[str, ...]:
    return _rewrap(_text_tuple, value, field)


def evidence_tuple(value: Any) -> tuple[Evidence, ...]:
    return _rewrap(_evidence_tuple, value)


def assert_evidence_backed(evidence: tuple[Evidence, ...], field: str, why: str) -> None:
    _rewrap(_assert_evidence_backed, evidence, field, why)


def nonempty_text_tuple(value: Any, field: str, why: str) -> tuple[str, ...]:
    """A list of statements that must contain at least one statement."""
    items = text_tuple(value, field)
    if not items:
        raise OrgIntelligenceError(f"{field}: at least one entry is required - {why}")
    return items


# The names a program reaches for when it signs its own approval. A human
# decision has to name somebody, and none of these is somebody.
AUTOMATIC_MARKERS = frozenset(
    {
        "auto",
        "automatic",
        "automated",
        "automation",
        "company_os",
        "company os",
        "org_intelligence",
        "organizational_intelligence",
        "organizational intelligence",
        "self",
        "system",
        "this subsystem",
    }
)


def assert_human(value: Any, field: str) -> str:
    """Refuse a decision, an approval or an implementer that names no person.

    Not a proof of humanity - nothing here can be. It is a refusal of the
    specific lie this subsystem would tell if it ever wrote its own approval,
    and it fails on the one field such a record has to fill in.
    """
    text = assert_prose(value, field)
    if text.strip().lower() in AUTOMATIC_MARKERS:
        raise AdvisoryViolation(
            f"{field}: {text!r} is not a person. Organizational Intelligence observes, "
            "reasons and recommends; approving, deciding and implementing are named "
            "human acts recorded elsewhere"
        )
    return text


def positive_int(value: Any, field: str, *, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise OrgIntelligenceError(f"{field} must be an integer of at least {minimum}")
    return value


def ratio(numerator: float | None, denominator: float | None) -> float | None:
    """`numerator / denominator`, or `None` when nobody can divide them.

    `None` rather than `0.0`, everywhere, for the reason `ai_platform/usage.py`
    gives: an unmeasured rate is not a good rate.
    """
    if numerator is None or not denominator:
        return None
    return numerator / denominator


def enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def rendered_configuration(*policies: Any) -> tuple[tuple[str, str], ...]:
    """Every threshold a review actually used, as sorted `(name, value)` pairs.

    A review that says "three occurrences was the bar" and a policy object that
    says four is a review nobody can reproduce. Rendering the dataclass rather
    than restating it by hand means the record cannot disagree with the run.
    """
    out: list[tuple[str, str]] = []
    for policy in policies:
        if not dataclasses.is_dataclass(policy) or isinstance(policy, type):
            raise OrgIntelligenceError(
                "configuration is rendered from policy dataclasses, "
                f"got {type(policy).__name__}"
            )
        prefix = type(policy).__name__
        for field in dataclasses.fields(policy):
            raw = getattr(policy, field.name)
            if isinstance(raw, Iterable) and not isinstance(raw, (str, bytes)):
                text = ",".join(str(enum_value(item)) for item in raw)
            else:
                text = str(enum_value(raw))
            out.append((f"{prefix}.{field.name}", text))
    return tuple(sorted(out))

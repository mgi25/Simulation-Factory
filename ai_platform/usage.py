"""What a task actually cost, recorded so that it still works without token counts.

`docs/company_os_v1_bootstrap.md` sets the objective: *do not optimize for
fewest tokens in isolation; optimize total resources per accepted result*. That
sentence contains the design constraint for this module, and it is not the
obvious one.

## The constraint: the denominator is the reliable half

Token counts are a courtesy. A provider may expose them, may expose them only
for some calls, may change their units, or may be a local tool that has none.
Accepted deliverables, retries, passes, rejections and tool calls are things
*we* observe, in our own process, every time.

So the primary metric is defined over the half we always have. Every
provider-supplied field - `input_units`, `output_units`, `tool_calls`,
`duration_s` - is `None` when not supplied, and `None` propagates: a summary
over records that lack unit accounting reports `units_per_accepted=None` and
still reports `passes_per_accepted`, which is a real efficiency number. A
platform whose only metric needs token counts stops measuring the moment the
provider changes; this one degrades to a coarser unit and keeps going.

They are `units`, not `tokens`, for the same reason the resource classes carry
no model names: a token is one provider's quantisation of one provider's text.
`UsageUnit` records which quantisation a number is in, and a summary that mixes
two of them refuses to add them up rather than producing a plausible lie.

## Rejections are a cost, not an absence

A rejected result consumed everything an accepted one would have. It stays in
the ledger with its reason, and it lands in the denominator of
`resources_per_accepted` - which is what makes the metric tell the truth about
a cheap class that keeps failing.

## Nested agents

`subagents_used` exists and its only legal value under a bootstrap policy is
zero. A field that can only be zero looks redundant until the day a record
arrives with a one in it; then it is the audit trail.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any

from ai_platform.policy import (
    BOOTSTRAP_POLICY,
    ExecutionPolicy,
    SubagentPolicyViolation,
)
from ai_platform.references import assert_reference
from ai_platform.resource_classes import ReasoningClass
from ai_platform.serde import fingerprint as _fingerprint
from ai_platform.serde import to_jsonable


class Outcome(Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ABANDONED = (
        "abandoned"  # stopped before a result existed: escalated, superseded, cancelled
    )


class UsageUnit(Enum):
    """Which quantisation an input/output count is expressed in."""

    UNKNOWN = "unknown"  # the provider exposed nothing
    TOKEN = "token"
    CHARACTER = "character"
    WORD = "word"


class UsageRecordError(ValueError):
    """A usage record that cannot be believed."""


@dataclass(frozen=True)
class ResourceUsageRecord:
    """One attempt at one task: what it was given, what it cost, how it ended."""

    task_id: str
    reasoning_class: ReasoningClass
    outcome: Outcome

    # What it was given. Keys from `ContextManifest.keys()`.
    context_sources: tuple[str, ...] = ()
    context_refs_used: tuple[str, ...] = ()
    context_fingerprint: str = ""
    explicit_context_sources: tuple[str, ...] = ()
    automatic_context_sources: tuple[str, ...] = ()
    context_cache_key: str = ""

    # What we observe ourselves. Always present.
    passes: int = 1
    retries: int = 0
    cache_hits: int = 0
    retrieval_hits: int = 0
    subagents_used: int = 0

    # What the provider may or may not expose. None means "not supplied".
    tool_calls: int | None = None
    input_units: int | None = None
    output_units: int | None = None
    usage_unit: UsageUnit = UsageUnit.UNKNOWN
    duration_s: float | None = None

    rejection_reason: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        assert_reference(self.task_id, "task_id")
        if not isinstance(self.reasoning_class, ReasoningClass):
            raise UsageRecordError(
                f"{self.task_id}: reasoning_class must be a ReasoningClass value"
            )
        if not isinstance(self.outcome, Outcome):
            raise UsageRecordError(f"{self.task_id}: outcome must be an Outcome value")
        if not isinstance(self.usage_unit, UsageUnit):
            raise UsageRecordError(
                f"{self.task_id}: usage_unit must be a UsageUnit value"
            )
        for name in (
            "context_sources",
            "context_refs_used",
            "explicit_context_sources",
            "automatic_context_sources",
        ):
            if not isinstance(getattr(self, name), tuple):
                raise UsageRecordError(f"{self.task_id}: {name} must be a tuple")
        for name in (
            "context_fingerprint",
            "context_cache_key",
            "rejection_reason",
            "notes",
        ):
            if not isinstance(getattr(self, name), str):
                raise UsageRecordError(f"{self.task_id}: {name} must be a string")

        if self.outcome is Outcome.REJECTED and not self.rejection_reason.strip():
            raise UsageRecordError(
                f"{self.task_id}: a rejected result must carry a rejection_reason - "
                "an unexplained rejection cannot improve the next pass"
            )
        if self.outcome is not Outcome.REJECTED and self.rejection_reason.strip():
            raise UsageRecordError(
                f"{self.task_id}: rejection_reason is set on a {self.outcome.value} result"
            )

        counters = (
            ("passes", self.passes),
            ("retries", self.retries),
            ("cache_hits", self.cache_hits),
            ("retrieval_hits", self.retrieval_hits),
            ("subagents_used", self.subagents_used),
        )
        for name, value in counters:
            if isinstance(value, bool) or not isinstance(value, int):
                raise UsageRecordError(f"{self.task_id}: {name} must be an integer")
            if value < 0:
                raise UsageRecordError(f"{self.task_id}: {name} must not be negative")
        if self.passes < 1:
            raise UsageRecordError(
                f"{self.task_id}: a record describes at least one pass"
            )

        optional = (
            ("tool_calls", self.tool_calls),
            ("input_units", self.input_units),
            ("output_units", self.output_units),
        )
        for name, value in optional:
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int)
            ):
                raise UsageRecordError(
                    f"{self.task_id}: {name} must be an integer or None"
                )
            if value is not None and value < 0:
                raise UsageRecordError(f"{self.task_id}: {name} must not be negative")
        if self.duration_s is not None:
            if isinstance(self.duration_s, bool) or not isinstance(
                self.duration_s, (int, float)
            ):
                raise UsageRecordError(
                    f"{self.task_id}: duration_s must be a number or None"
                )
            if not math.isfinite(self.duration_s) or self.duration_s < 0:
                raise UsageRecordError(
                    f"{self.task_id}: duration_s must be finite and not negative"
                )
            object.__setattr__(self, "duration_s", float(self.duration_s))

        for name, values in (
            ("context_sources", self.context_sources),
            ("context_refs_used", self.context_refs_used),
            ("explicit_context_sources", self.explicit_context_sources),
            ("automatic_context_sources", self.automatic_context_sources),
        ):
            if any(not isinstance(value, str) or not value for value in values):
                raise UsageRecordError(
                    f"{self.task_id}: {name} must contain non-empty strings"
                )

        supplied_units = self.input_units is not None or self.output_units is not None
        if supplied_units and self.usage_unit is UsageUnit.UNKNOWN:
            raise UsageRecordError(
                f"{self.task_id}: unit counts were supplied without a usage_unit; "
                "a bare number is not a measurement"
            )

        unknown = set(self.context_refs_used) - set(self.context_sources)
        if unknown:
            raise UsageRecordError(
                f"{self.task_id}: used context not present in the manifest: "
                + ", ".join(sorted(unknown))
            )

        explicit = set(self.explicit_context_sources)
        automatic = set(self.automatic_context_sources)
        overlap = explicit & automatic
        if overlap:
            raise UsageRecordError(
                f"{self.task_id}: context cannot be both explicit and automatic: "
                + ", ".join(sorted(overlap))
            )
        if (explicit or automatic) and explicit | automatic != set(
            self.context_sources
        ):
            raise UsageRecordError(
                f"{self.task_id}: explicit and automatic context must account for "
                "every supplied context source"
            )

        if self.subagents_used:
            raise SubagentPolicyViolation(
                f"{self.task_id}: {self.subagents_used} nested agent(s) recorded; "
                "constitution rule 2 forbids them in Bootstrap Mode"
            )

    @property
    def has_unit_accounting(self) -> bool:
        return self.usage_unit is not UsageUnit.UNKNOWN and (
            self.input_units is not None or self.output_units is not None
        )

    @property
    def total_units(self) -> int | None:
        if not self.has_unit_accounting:
            return None
        return (self.input_units or 0) + (self.output_units or 0)

    @property
    def unused_context(self) -> tuple[str, ...]:
        used = set(self.context_refs_used)
        return tuple(key for key in self.context_sources if key not in used)

    def check_policy(self, policy: ExecutionPolicy = BOOTSTRAP_POLICY) -> None:
        policy.assert_no_subagents(self.subagents_used)

    def to_dict(self) -> dict[str, Any]:
        """Return the canonical JSON-ready shape used by the file store."""
        return to_jsonable(self)

    def fingerprint(self) -> str:
        """Stable identity for compact handoff references and integrity checks."""
        return _fingerprint(self)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> ResourceUsageRecord:
        """Decode one persisted record without permissive reflective coercion."""
        known = {item.name for item in cls.__dataclass_fields__.values()}
        unknown = sorted(set(data) - known)
        if unknown:
            raise UsageRecordError(
                "unknown resource usage field(s): " + ", ".join(unknown)
            )

        task_id = _required_string(data, "task_id")
        reasoning_class = _enum_value(
            ReasoningClass, data.get("reasoning_class"), "reasoning_class"
        )
        outcome = _enum_value(Outcome, data.get("outcome"), "outcome")
        usage_unit = _enum_value(
            UsageUnit, data.get("usage_unit", UsageUnit.UNKNOWN.value), "usage_unit"
        )

        tuple_fields = {
            name: _string_tuple(data.get(name, ()), name)
            for name in (
                "context_sources",
                "context_refs_used",
                "explicit_context_sources",
                "automatic_context_sources",
            )
        }
        integer_fields = {
            name: _integer(data.get(name, default), name)
            for name, default in (
                ("passes", 1),
                ("retries", 0),
                ("cache_hits", 0),
                ("retrieval_hits", 0),
                ("subagents_used", 0),
            )
        }
        optional_integer_fields = {
            name: _optional_integer(data.get(name), name)
            for name in ("tool_calls", "input_units", "output_units")
        }
        duration = data.get("duration_s")
        if duration is not None and (
            isinstance(duration, bool) or not isinstance(duration, (int, float))
        ):
            raise UsageRecordError("duration_s must be a number or null")

        string_fields = {
            name: _string(data.get(name, ""), name)
            for name in (
                "context_fingerprint",
                "context_cache_key",
                "rejection_reason",
                "notes",
            )
        }
        return cls(
            task_id=task_id,
            reasoning_class=reasoning_class,
            outcome=outcome,
            usage_unit=usage_unit,
            duration_s=float(duration) if duration is not None else None,
            **tuple_fields,
            **integer_fields,
            **optional_integer_fields,
            **string_fields,
        )


@dataclass(frozen=True)
class ResourceSummary:
    """The ledger's answer to 'what did an accepted deliverable cost?'.

    `units_per_accepted` is `None` whenever the underlying records cannot
    support it - no unit accounting, or two incompatible units mixed.
    `passes_per_accepted` is never `None`, because passes are always counted.
    """

    records: int
    accepted: int
    rejected: int
    abandoned: int
    passes: int
    retries: int
    cache_hits: int
    retrieval_hits: int
    unused_context_refs: int
    unit: UsageUnit
    units: int | None
    tool_calls: int | None
    duration_s: float | None
    passes_per_accepted: float | None
    units_per_accepted: float | None
    first_pass_success_rate: float | None
    rejected_passes: int


@dataclass
class UsageLedger:
    """An ordered, append-only collection of usage records for one scope."""

    records: list[ResourceUsageRecord] = field(default_factory=list)

    def add(self, record: ResourceUsageRecord) -> ResourceUsageRecord:
        record.check_policy()
        self.records.append(record)
        return record

    def with_outcome(self, outcome: Outcome) -> tuple[ResourceUsageRecord, ...]:
        return tuple(r for r in self.records if r.outcome is outcome)

    def cache_hit_rate(self) -> float | None:
        """Hits per pass. `None` when there is nothing to divide."""
        passes = sum(r.passes for r in self.records)
        if not passes:
            return None
        hits = sum(r.cache_hits + r.retrieval_hits for r in self.records)
        return hits / passes

    def summarise(self) -> ResourceSummary:
        records = self.records
        accepted = self.with_outcome(Outcome.ACCEPTED)
        rejected = self.with_outcome(Outcome.REJECTED)
        abandoned = self.with_outcome(Outcome.ABANDONED)

        passes = sum(r.passes for r in records)
        retries = sum(r.retries for r in records)

        # Units are only summable when every record reports the same unit.
        units_seen = {r.usage_unit for r in records if r.has_unit_accounting}
        if (
            len(units_seen) == 1
            and all(r.has_unit_accounting for r in records)
            and records
        ):
            unit = units_seen.pop()
            units: int | None = sum(r.total_units or 0 for r in records)
        else:
            unit = UsageUnit.UNKNOWN
            units = None

        tool_calls = (
            sum(r.tool_calls or 0 for r in records)
            if records and all(r.tool_calls is not None for r in records)
            else None
        )
        duration = (
            sum(r.duration_s or 0.0 for r in records)
            if records and all(r.duration_s is not None for r in records)
            else None
        )

        n_accepted = len(accepted)
        first_pass = (
            sum(1 for r in accepted if r.retries == 0 and r.passes == 1) / n_accepted
            if n_accepted
            else None
        )

        return ResourceSummary(
            records=len(records),
            accepted=n_accepted,
            rejected=len(rejected),
            abandoned=len(abandoned),
            passes=passes,
            retries=retries,
            cache_hits=sum(r.cache_hits for r in records),
            retrieval_hits=sum(r.retrieval_hits for r in records),
            unused_context_refs=sum(len(r.unused_context) for r in records),
            unit=unit,
            units=units,
            tool_calls=tool_calls,
            duration_s=duration,
            # Every pass in the scope is charged to the accepted deliverables,
            # rejections included - that is the cost of getting to acceptance.
            passes_per_accepted=(passes / n_accepted) if n_accepted else None,
            units_per_accepted=(
                (units / n_accepted) if (units is not None and n_accepted) else None
            ),
            first_pass_success_rate=first_pass,
            rejected_passes=sum(r.passes for r in rejected),
        )


def _required_string(data: Mapping[str, Any], field_name: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise UsageRecordError(f"{field_name} must be a non-empty string")
    return value


def _string(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise UsageRecordError(f"{field_name} must be a string")
    return value


def _string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise UsageRecordError(f"{field_name} must be a list of strings")
    if any(not isinstance(item, str) for item in value):
        raise UsageRecordError(f"{field_name} must be a list of strings")
    return tuple(value)


def _integer(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise UsageRecordError(f"{field_name} must be an integer")
    return value


def _optional_integer(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    return _integer(value, field_name)


def _enum_value(enum_type: type[Enum], value: Any, field_name: str) -> Any:
    if not isinstance(value, str):
        raise UsageRecordError(f"{field_name} must be a string")
    try:
        return enum_type(value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in enum_type)
        raise UsageRecordError(f"{field_name} must be one of: {allowed}") from exc

"""How an employee performs, per capability - and never as one number.

## There is no global employee score, and its absence is enforced

Section 13 of the workforce brief: *do not create one global "good employee
score"*. The reason is concrete rather than philosophical. A role can be strong
at `software_architecture` and weak at `visual_direction`; a single number for
that employee is either an average nobody can act on or a verdict that follows
them into work they are actually good at.

So the unit of performance here is `(employee_id, capability_id)`, and the
absence is checked: `tests/test_company_workforce.py` scans every dataclass in
this package for a field named like a score, rating or overall grade and fails
if one appears. A rule that lives only in a docstring is a rule that comes back.

## It works with no token counts

Every counter here - attempted, accepted, rejected, first pass, regressions,
escalations - is something *we* observe. None of them needs a provider to
expose a token count. `ai_platform/usage.py` makes the same argument at length;
the consequence for this module is that `CapabilityPerformance` is complete and
useful with `usage_record_refs` empty, and `resource_summary()` returns `None`
rather than zero when there is nothing to summarise.

## Usage records are referenced, not copied

`PerformanceObservation.usage_record_ref` is a pointer into the usage store.
`resource_summary()` takes a resolver function, so this module never reads the
filesystem and the counts have exactly one home (constitution rule 15).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ai_platform.serde import to_jsonable
from ai_platform.usage import ResourceSummary, ResourceUsageRecord, UsageLedger

from .common import (
    assert_day,
    assert_identifier,
    assert_prose,
    assert_ref,
    optional_ref,
)
from .errors import WorkforceError


class TaskOutcome(Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ABANDONED = "abandoned"


@dataclass(frozen=True)
class PerformanceObservation:
    """One employee, one capability, one task, what happened.

    Scoped to a capability on purpose: an observation that only knows which
    employee it belongs to cannot support a task-specific answer later, and no
    amount of aggregation puts the scope back.
    """

    employee_id: str
    capability_id: str
    task_ref: str
    outcome: TaskOutcome
    on: dt.date
    first_pass: bool = True
    caused_regression: bool = False
    escalated: bool = False
    recommendation_accepted: bool | None = None
    false_alarm: bool = False
    usage_record_ref: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        assert_identifier(self.employee_id, "employee_id")
        assert_identifier(self.capability_id, "capability_id")
        assert_ref(self.task_ref, "task_ref")
        if not isinstance(self.outcome, TaskOutcome):
            raise WorkforceError("outcome must be a TaskOutcome")
        object.__setattr__(self, "on", assert_day(self.on, "observation date"))
        for name in ("first_pass", "caused_regression", "escalated", "false_alarm"):
            if not isinstance(getattr(self, name), bool):
                raise WorkforceError(f"observation {name} must be a bool")
        if self.recommendation_accepted is not None and not isinstance(
            self.recommendation_accepted, bool
        ):
            raise WorkforceError("recommendation_accepted must be a bool or None")
        object.__setattr__(
            self, "usage_record_ref", optional_ref(self.usage_record_ref, "usage_record_ref")
        )
        if not isinstance(self.note, str):
            raise WorkforceError("observation note must be a string")
        if self.outcome is TaskOutcome.REJECTED and not self.note.strip():
            raise WorkforceError(
                f"{self.employee_id}/{self.capability_id}: a rejected task needs a note. "
                "A rejection with no reason cannot improve the next attempt"
            )
        if self.false_alarm and self.recommendation_accepted is not False:
            raise WorkforceError(
                "a false alarm is a recommendation that was not accepted; set "
                "recommendation_accepted=False alongside it"
            )

    @property
    def scope(self) -> tuple[str, str]:
        return (self.employee_id, self.capability_id)

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PerformanceObservation:
        return cls(
            employee_id=data["employee_id"],
            capability_id=data["capability_id"],
            task_ref=data["task_ref"],
            outcome=TaskOutcome(data["outcome"]),
            on=assert_day(data["on"], "on"),
            first_pass=data.get("first_pass", True),
            caused_regression=data.get("caused_regression", False),
            escalated=data.get("escalated", False),
            recommendation_accepted=data.get("recommendation_accepted"),
            false_alarm=data.get("false_alarm", False),
            usage_record_ref=data.get("usage_record_ref", ""),
            note=data.get("note", ""),
        )


@dataclass(frozen=True)
class CapabilityPerformance:
    """The summary for one (employee, capability) pair. Rates, never a grade."""

    employee_id: str
    capability_id: str
    attempted: int = 0
    accepted: int = 0
    rejected: int = 0
    abandoned: int = 0
    first_pass_successes: int = 0
    regressions_caused: int = 0
    accepted_recommendations: int = 0
    false_alarms: int = 0
    escalations: int = 0
    usage_record_refs: tuple[str, ...] = ()

    @property
    def first_pass_success_rate(self) -> float | None:
        return None if not self.accepted else self.first_pass_successes / self.accepted

    @property
    def acceptance_rate(self) -> float | None:
        return None if not self.attempted else self.accepted / self.attempted

    @property
    def rejection_rate(self) -> float | None:
        return None if not self.attempted else self.rejected / self.attempted

    @property
    def escalation_rate(self) -> float | None:
        return None if not self.attempted else self.escalations / self.attempted

    @property
    def false_alarm_rate(self) -> float | None:
        recommendations = self.accepted_recommendations + self.false_alarms
        return None if not recommendations else self.false_alarms / recommendations

    def to_dict(self) -> dict[str, Any]:
        base = to_jsonable(self)
        base.update(
            first_pass_success_rate=self.first_pass_success_rate,
            acceptance_rate=self.acceptance_rate,
            rejection_rate=self.rejection_rate,
            escalation_rate=self.escalation_rate,
            false_alarm_rate=self.false_alarm_rate,
        )
        return base


@dataclass(frozen=True)
class EmployeePerformance:
    """Every capability an employee has been observed on. Not a ranking.

    This class exists so a caller can ask "what has this employee done" without
    the package ever answering "how good is this employee". `capabilities` is
    sorted by capability id, not by any measure of quality, because sorting by
    quality is the first step to collapsing it into a score.
    """

    employee_id: str
    capabilities: tuple[CapabilityPerformance, ...] = ()

    def get(self, capability_id: str) -> CapabilityPerformance:
        for entry in self.capabilities:
            if entry.capability_id == capability_id:
                return entry
        raise WorkforceError(
            f"{self.employee_id} has no recorded performance for {capability_id!r}"
        )

    @property
    def capability_ids(self) -> tuple[str, ...]:
        return tuple(entry.capability_id for entry in self.capabilities)

    @property
    def attempted(self) -> int:
        """Total tasks attempted. A count, not a quality measure."""
        return sum(entry.attempted for entry in self.capabilities)

    @property
    def accepted(self) -> int:
        return sum(entry.accepted for entry in self.capabilities)

    @property
    def unique_capabilities_used(self) -> int:
        return len([entry for entry in self.capabilities if entry.attempted])

    def to_dict(self) -> dict[str, Any]:
        return {
            "employee_id": self.employee_id,
            "capabilities": [entry.to_dict() for entry in self.capabilities],
            "attempted": self.attempted,
            "accepted": self.accepted,
            "unique_capabilities_used": self.unique_capabilities_used,
        }


def summarise_observations(
    observations: Iterable[PerformanceObservation],
) -> tuple[CapabilityPerformance, ...]:
    """Fold observations into one summary per (employee, capability), sorted."""
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for observation in observations:
        bucket = buckets.setdefault(
            observation.scope,
            {
                "attempted": 0,
                "accepted": 0,
                "rejected": 0,
                "abandoned": 0,
                "first_pass_successes": 0,
                "regressions_caused": 0,
                "accepted_recommendations": 0,
                "false_alarms": 0,
                "escalations": 0,
                "refs": [],
            },
        )
        bucket["attempted"] += 1
        if observation.outcome is TaskOutcome.ACCEPTED:
            bucket["accepted"] += 1
            if observation.first_pass:
                bucket["first_pass_successes"] += 1
        elif observation.outcome is TaskOutcome.REJECTED:
            bucket["rejected"] += 1
        else:
            bucket["abandoned"] += 1
        if observation.caused_regression:
            bucket["regressions_caused"] += 1
        if observation.escalated:
            bucket["escalations"] += 1
        if observation.recommendation_accepted is True:
            bucket["accepted_recommendations"] += 1
        if observation.false_alarm:
            bucket["false_alarms"] += 1
        if observation.usage_record_ref:
            bucket["refs"].append(observation.usage_record_ref)
    return tuple(
        CapabilityPerformance(
            employee_id=employee_id,
            capability_id=capability_id,
            attempted=bucket["attempted"],
            accepted=bucket["accepted"],
            rejected=bucket["rejected"],
            abandoned=bucket["abandoned"],
            first_pass_successes=bucket["first_pass_successes"],
            regressions_caused=bucket["regressions_caused"],
            accepted_recommendations=bucket["accepted_recommendations"],
            false_alarms=bucket["false_alarms"],
            escalations=bucket["escalations"],
            usage_record_refs=tuple(sorted(set(bucket["refs"]))),
        )
        for (employee_id, capability_id), bucket in sorted(buckets.items())
    )


def employee_performance(
    employee_id: str, observations: Iterable[PerformanceObservation]
) -> EmployeePerformance:
    assert_identifier(employee_id, "employee_id")
    mine = [item for item in observations if item.employee_id == employee_id]
    return EmployeePerformance(
        employee_id=employee_id,
        capabilities=summarise_observations(mine),
    )


def resource_summary(
    performance: CapabilityPerformance,
    resolve: Callable[[str], ResourceUsageRecord | None],
) -> ResourceSummary | None:
    """Cost per accepted deliverable, via the usage store, or `None`.

    Returns `None` when no usage record is linked or none resolves - which is
    the normal case for work measured only by our own counters, and is not a
    failure. `ResourceSummary.passes_per_accepted` is populated even when the
    provider exposed no units at all; `units_per_accepted` is `None` then, and
    the caller that needed it learns so honestly.
    """
    if not performance.usage_record_refs:
        return None
    ledger = UsageLedger()
    for ref in performance.usage_record_refs:
        record = resolve(ref)
        if record is not None:
            ledger.add(record)
    if not ledger.records:
        return None
    return ledger.summarise()

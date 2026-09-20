"""Organizational debt: what the org chart is quietly costing.

Deliberately light. Section 14 of the workforce brief asks for a record type and
explicitly does not ask for the Organizational Intelligence department, so this
is one dataclass, one enum, and two detectors that can be computed from data we
already have. Everything else is a record someone writes by hand.

The two detectors are the ones that need no judgement:

`duplicated_roles` - two employees with identical capability sets. That is a
fact about `org_registry.yaml`, not an opinion, and it is the input to a merge
proposal rather than the proposal itself.

`unused_capabilities` - a capability defined in `capability_registry.json` that
no employee provides. Note the direction: this is debt in the *capability model*,
not in the workforce. A capability nobody has may be a gap worth filling or a
definition worth deleting, and the record says which one a human decided.

What is not here, on purpose: bloated-contract detection by line count (a
contract is long or short for reasons a counter cannot see), approval-bottleneck
detection from timestamps (we have no approval timestamps yet), and anything
that scores a department.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ai_platform.serde import to_jsonable
from knowledge.company_os.records import Evidence

from .capabilities import CapabilityRegistry
from .common import (
    assert_day,
    assert_prose,
    assert_record_id,
    assert_ref,
    evidence_tuple,
)
from .errors import WorkforceError


class DebtKind(Enum):
    DUPLICATED_ROLE = "duplicated_role"
    UNNECESSARY_MANAGEMENT_LAYER = "unnecessary_management_layer"
    STALE_EMPLOYEE_DEFINITION = "stale_employee_definition"
    BLOATED_CONTRACT = "bloated_contract"
    UNUSED_CAPABILITY = "unused_capability"
    APPROVAL_BOTTLENECK = "approval_bottleneck"


class DebtSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DebtStatus(Enum):
    OPEN = "open"
    ACCEPTED = "accepted"
    RESOLVED = "resolved"
    WITHDRAWN = "withdrawn"


@dataclass(frozen=True)
class OrganizationalDebt:
    """One noted cost of the current organization, with a pointer to it."""

    debt_id: str
    kind: DebtKind
    subject_ref: str
    detail: str
    observed_on: dt.date
    severity: DebtSeverity = DebtSeverity.LOW
    status: DebtStatus = DebtStatus.OPEN
    evidence: tuple[Evidence, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        assert_record_id(self.debt_id, "debt_id")
        if not isinstance(self.kind, DebtKind):
            raise WorkforceError("debt kind must be a DebtKind")
        assert_ref(self.subject_ref, "debt subject_ref")
        assert_prose(self.detail, f"debt {self.debt_id} detail")
        object.__setattr__(self, "observed_on", assert_day(self.observed_on, "observed_on"))
        if not isinstance(self.severity, DebtSeverity):
            raise WorkforceError("debt severity must be a DebtSeverity")
        if not isinstance(self.status, DebtStatus):
            raise WorkforceError("debt status must be a DebtStatus")
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))
        if not isinstance(self.notes, str):
            raise WorkforceError("debt notes must be a string")

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrganizationalDebt:
        return cls(
            debt_id=data["debt_id"],
            kind=DebtKind(data["kind"]),
            subject_ref=data["subject_ref"],
            detail=data["detail"],
            observed_on=assert_day(data["observed_on"], "observed_on"),
            severity=DebtSeverity(data.get("severity", DebtSeverity.LOW.value)),
            status=DebtStatus(data.get("status", DebtStatus.OPEN.value)),
            evidence=evidence_tuple(data.get("evidence")),
            notes=data.get("notes", ""),
        )


def duplicated_roles(registry: CapabilityRegistry) -> tuple[tuple[str, ...], ...]:
    """Groups of employees whose capability sets are identical.

    Identical, not overlapping. Overlap is normal and healthy; two roles that
    declare exactly the same capabilities are two names for one job, and that
    is the only version of this a computation can assert without judgement.
    """
    groups: dict[tuple[str, ...], list[str]] = {}
    for employee_id in registry.employee_ids:
        key = registry.employee_capabilities(employee_id)
        if not key:
            continue
        groups.setdefault(key, []).append(employee_id)
    return tuple(
        tuple(sorted(members)) for _key, members in sorted(groups.items()) if len(members) > 1
    )


def detect_debt(
    registry: CapabilityRegistry, *, observed_on: dt.date, prefix: str = "debt"
) -> tuple[OrganizationalDebt, ...]:
    """The debt records that follow from the registries alone.

    Every record is `OPEN` and `LOW`: a detector found a shape, not a problem.
    Raising the severity is what a person does after looking.
    """
    found: list[OrganizationalDebt] = []
    for index, members in enumerate(duplicated_roles(registry)):
        found.append(
            OrganizationalDebt(
                debt_id=f"{prefix}-duplicated-role-{index + 1}",
                kind=DebtKind.DUPLICATED_ROLE,
                subject_ref=",".join(members),
                detail=(
                    "these employees declare identical capability sets: " + ", ".join(members)
                ),
                observed_on=observed_on,
            )
        )
    for capability_id in registry.unused_capabilities():
        found.append(
            OrganizationalDebt(
                debt_id=f"{prefix}-unused-capability-{capability_id.replace('_', '-')}",
                kind=DebtKind.UNUSED_CAPABILITY,
                subject_ref=capability_id,
                detail=(
                    f"{capability_id} is defined in the capability registry and no employee "
                    "provides it. Either it is a gap worth filling or a definition worth "
                    "deleting; the record does not decide which"
                ),
                observed_on=observed_on,
            )
        )
    return tuple(found)

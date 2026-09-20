"""The row that answers: why did the company choose this work?

`ExecutiveDecisionRecord` records that a seat approved an action. It cannot
record a selection, because until now selection was not an act the model had a
name for - the first live-delegation pilot stopped on exactly that. This record
is its counterpart for the rung above: not "may this proceed" but "of the work
we knew about, this is the piece we chose, and here is who chose it and what
they rejected".

## Why the rejected candidates are on the record

`candidate_ids_considered` holds everything the eligibility pass returned, not
just the winner. A selection that lists one candidate and picks it is not a
choice; it is the only option, and the record should make that visible rather
than dress it up. When a later reader asks whether the company chose well, the
set it chose *from* is most of the answer.

## Why the objective's intent digest is copied in

`objectives.Objective.intent()` fingerprints the fields that constitute what the
CEO asked for. Copying the digest here means a planning decision taken against
one objective cannot be quietly re-attributed to an edited one:
`objectives.assert_within_intent` already refuses a child derived from an intent
the parent no longer has, and this record extends that property to the choice
itself. Editing an objective is a new objective, and a selection made under the
old one says so.

## What this record is not

It is not an authorization. `decision` says a selection was made, escalated, or
found nothing; whether the *work* may then proceed is
`authority.evaluate`'s answer about `SELECT_WORK` and, later, about
`APPROVE_WORK_ORDER`. Keeping the two apart is what lets a manager legitimately
select work that the company then declines to fund.
"""

from __future__ import annotations

from collections.abc import Mapping
import datetime as dt
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ai_platform.resource_classes import Risk
from ai_platform.serde import fingerprint as _fingerprint
from company.finance.money import Money

from .common import (
    assert_day,
    assert_named_person,
    assert_prose,
    assert_record_id,
    assert_seat_id,
    name_tuple,
    ref_tuple,
    text_tuple,
)
from .errors import DelegationError
from .policy import parse_risk

PLANNING_RECORD_VERSION = 1


class PlanningOutcome(str, Enum):
    """The three ways a planning pass can end. There is no "maybe"."""

    SELECTED = "selected"
    NO_ELIGIBLE_WORK_CANDIDATE = "no_eligible_work_candidate"
    ESCALATED = "escalated"


def parse_outcome(value: Any, field: str = "decision") -> PlanningOutcome:
    if isinstance(value, PlanningOutcome):
        return value
    if not isinstance(value, str):
        raise DelegationError(f"{field} must be a planning outcome name, got {value!r}")
    try:
        return PlanningOutcome(value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in PlanningOutcome)
        raise DelegationError(f"{field} must be one of: {allowed}") from exc


@dataclass(frozen=True)
class PlanningDecisionRecord:
    """One executive/management selection, as it will be stored and audited."""

    planning_decision_id: str
    recorded_on: dt.date
    objective_id: str
    objective_intent_digest: str
    department: str
    executive_seat: str
    executive_employee: str
    manager_seat: str
    manager_employee: str
    decision: PlanningOutcome
    selection_reason: str
    policy_version: str
    policy_fingerprint: str
    candidate_ids_considered: tuple[str, ...] = ()
    candidate_ids_rejected: tuple[str, ...] = ()
    selected_candidate_id: str = ""
    capsule_id: str = ""
    risk: Risk | None = None
    estimated_cost: Money | None = None
    expected_value: str = ""
    acceptance_criteria: tuple[str, ...] = ()
    objective_alignment: str = ""
    evidence_refs_used: tuple[str, ...] = ()
    escalation_required: bool = False
    escalation_reason: str = ""
    version: int = PLANNING_RECORD_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "planning_decision_id",
            assert_record_id(self.planning_decision_id, "planning_decision_id"),
        )
        object.__setattr__(
            self, "recorded_on", assert_day(self.recorded_on, "recorded_on")
        )
        object.__setattr__(
            self, "objective_id", assert_record_id(self.objective_id, "objective_id")
        )
        object.__setattr__(
            self,
            "objective_intent_digest",
            assert_prose(self.objective_intent_digest, "objective_intent_digest"),
        )
        object.__setattr__(
            self, "department", assert_prose(self.department, "department").lower()
        )
        object.__setattr__(
            self, "executive_seat", assert_seat_id(self.executive_seat, "executive_seat")
        )
        object.__setattr__(
            self, "manager_seat", assert_seat_id(self.manager_seat, "manager_seat")
        )
        for field in ("executive_employee", "manager_employee"):
            object.__setattr__(
                self, field, assert_named_person(getattr(self, field), field)
            )
        object.__setattr__(self, "decision", parse_outcome(self.decision, "decision"))
        object.__setattr__(
            self, "selection_reason", assert_prose(self.selection_reason, "selection_reason")
        )
        for field in ("policy_version", "policy_fingerprint"):
            object.__setattr__(
                self, field, assert_prose(getattr(self, field), field)
            )
        object.__setattr__(
            self,
            "candidate_ids_considered",
            name_tuple(self.candidate_ids_considered, "candidate_ids_considered", limit=64),
        )
        object.__setattr__(
            self,
            "candidate_ids_rejected",
            name_tuple(self.candidate_ids_rejected, "candidate_ids_rejected", limit=64),
        )
        object.__setattr__(
            self,
            "acceptance_criteria",
            text_tuple(self.acceptance_criteria, "acceptance_criteria", limit=16),
        )
        object.__setattr__(
            self,
            "evidence_refs_used",
            ref_tuple(self.evidence_refs_used, "evidence_refs_used"),
        )
        for field in (
            "selected_candidate_id",
            "capsule_id",
            "expected_value",
            "objective_alignment",
            "escalation_reason",
        ):
            value = getattr(self, field)
            if not isinstance(value, str):
                raise DelegationError(f"{field} must be text")
            object.__setattr__(self, field, value.strip())
        if self.risk is not None:
            object.__setattr__(self, "risk", parse_risk(self.risk, "risk"))
        if self.estimated_cost is not None and not isinstance(self.estimated_cost, Money):
            raise DelegationError("estimated_cost must be Money or None")
        if not isinstance(self.escalation_required, bool):
            raise DelegationError("escalation_required must be a bool")

        # --- the three refusals --------------------------------------------
        if self.decision is PlanningOutcome.SELECTED:
            if not self.selected_candidate_id:
                raise DelegationError(
                    f"{self.planning_decision_id}: a SELECTED planning decision names "
                    "no candidate. A selection that does not say what was selected is "
                    "the defect this record exists to prevent."
                )
            if self.selected_candidate_id not in self.candidate_ids_considered:
                raise DelegationError(
                    f"{self.planning_decision_id}: selected candidate "
                    f"{self.selected_candidate_id} is not among the candidates "
                    "considered. A choice made outside the set that was evaluated is "
                    "not a choice the eligibility pass authorized."
                )
            if not self.acceptance_criteria:
                raise DelegationError(
                    f"{self.planning_decision_id}: a SELECTED planning decision "
                    "carries no acceptance criteria, so the work order derived from "
                    "it could not be reviewed."
                )
        if self.decision is PlanningOutcome.ESCALATED and not self.escalation_reason:
            raise DelegationError(
                f"{self.planning_decision_id}: an ESCALATED decision must say what "
                "exceeded the envelope, because the CEO is being asked to act on it."
            )
        if (
            self.decision is PlanningOutcome.NO_ELIGIBLE_WORK_CANDIDATE
            and self.selected_candidate_id
        ):
            raise DelegationError(
                f"{self.planning_decision_id}: no eligible candidate, yet one is "
                "named as selected."
            )
        if self.executive_employee == self.manager_employee and (
            self.executive_seat != self.manager_seat
        ):
            raise DelegationError(
                f"{self.planning_decision_id}: {self.executive_employee} is recorded "
                "in both the executive and the manager seat. One employee holding "
                "both ends of a planning decision is not two layers of review."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "planning_decision_id": self.planning_decision_id,
            "recorded_on": self.recorded_on.isoformat(),
            "objective_id": self.objective_id,
            "objective_intent_digest": self.objective_intent_digest,
            "department": self.department,
            "executive_seat": self.executive_seat,
            "executive_employee": self.executive_employee,
            "manager_seat": self.manager_seat,
            "manager_employee": self.manager_employee,
            "decision": self.decision.value,
            "selection_reason": self.selection_reason,
            "policy_version": self.policy_version,
            "policy_fingerprint": self.policy_fingerprint,
            "candidate_ids_considered": list(self.candidate_ids_considered),
            "candidate_ids_rejected": list(self.candidate_ids_rejected),
            "selected_candidate_id": self.selected_candidate_id,
            "capsule_id": self.capsule_id,
            "risk": self.risk.value if self.risk else "",
            "estimated_cost": (
                self.estimated_cost.to_dict() if self.estimated_cost else None
            ),
            "expected_value": self.expected_value,
            "acceptance_criteria": list(self.acceptance_criteria),
            "objective_alignment": self.objective_alignment,
            "evidence_refs_used": list(self.evidence_refs_used),
            "escalation_required": self.escalation_required,
            "escalation_reason": self.escalation_reason,
            "version": self.version,
        }

    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())


def planning_record_from(values: Any) -> PlanningDecisionRecord:
    """Decode one planning decision, for the store to read its own history."""
    if not isinstance(values, Mapping):
        raise DelegationError("a planning decision must be a mapping")
    cost_raw = values.get("estimated_cost")
    cost = (
        Money.from_dict(dict(cost_raw), "estimated_cost")
        if isinstance(cost_raw, Mapping)
        else None
    )
    risk_raw = values.get("risk") or ""
    return PlanningDecisionRecord(
        planning_decision_id=str(values.get("planning_decision_id", "")),
        recorded_on=assert_day(values.get("recorded_on"), "recorded_on"),
        objective_id=str(values.get("objective_id", "")),
        objective_intent_digest=str(values.get("objective_intent_digest", "")),
        department=str(values.get("department", "")),
        executive_seat=str(values.get("executive_seat", "")),
        executive_employee=str(values.get("executive_employee", "")),
        manager_seat=str(values.get("manager_seat", "")),
        manager_employee=str(values.get("manager_employee", "")),
        decision=values.get("decision", ""),
        selection_reason=str(values.get("selection_reason", "")),
        policy_version=str(values.get("policy_version", "")),
        policy_fingerprint=str(values.get("policy_fingerprint", "")),
        candidate_ids_considered=tuple(values.get("candidate_ids_considered", ())),
        candidate_ids_rejected=tuple(values.get("candidate_ids_rejected", ())),
        selected_candidate_id=str(values.get("selected_candidate_id", "") or ""),
        capsule_id=str(values.get("capsule_id", "") or ""),
        risk=parse_risk(risk_raw, "risk") if risk_raw else None,
        estimated_cost=cost,
        expected_value=str(values.get("expected_value", "") or ""),
        acceptance_criteria=tuple(values.get("acceptance_criteria", ())),
        objective_alignment=str(values.get("objective_alignment", "") or ""),
        evidence_refs_used=tuple(values.get("evidence_refs_used", ())),
        escalation_required=bool(values.get("escalation_required", False)),
        escalation_reason=str(values.get("escalation_reason", "") or ""),
        version=int(values.get("version", PLANNING_RECORD_VERSION)),
    )


__all__ = [
    "PLANNING_RECORD_VERSION",
    "PlanningDecisionRecord",
    "PlanningOutcome",
    "parse_outcome",
    "planning_record_from",
]

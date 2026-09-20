"""The row that lets a CEO reconstruct why something happened without them.

## The test this record has to pass

A CEO reads this six months later and asks one question: *why did this proceed
without me?* The record is adequate only if the answer is complete without
opening the code, the policy file or the git history. That means it has to
carry, at minimum:

- what was decided, and by which **seat**
- which **employee** sat in that seat, and which employees implemented and
  reviewed the work — because the separation-of-duties rules are about people,
  not positions, and a record naming only seats cannot show that the reviewer
  and the approver were different humans
- the **authority** it was taken under, down to the envelope the CEO signed
- every seat the request **passed through** and why it did not stop there
- the fact that the CEO was **not** required, as a recorded conclusion rather
  than an absence

`ExecutiveDecisionRecord` carries most of that already. What it cannot carry is
the last one honestly: it hard-refuses `shadow=False`, by design, so that no
shadow-phase record can ever be mistaken for a live one. This record is the
other half of that pair.

## Why this is a second class and not a flag on the first

The obvious change is to relax `ExecutiveDecisionRecord.shadow` to accept
`False`. That single edit would make every historical shadow record's guarantee
retroactively weaker: the property "nothing in this store ever claimed
authority" would become "nothing in this store claimed authority unless it
did". Two classes, two stores, one `mode` field each, and the old guarantee
survives untouched.

## Why the employee fields are separate from the seat fields

`approving_seat` is `engineering_manager`. `approving_employee` is
`engineering_delivery_manager`. They differ, they can be re-pointed at each
other by an org-registry edit, and the audit question — "was the approver a
different person from the reviewer?" — is only answerable from the second. A
record that collapsed them would make a genuine conflict of interest invisible
the moment somebody changed who sits in a seat.
"""

from __future__ import annotations

from collections.abc import Mapping
import datetime as dt
from dataclasses import dataclass
from typing import Any

from ai_platform.resource_classes import Risk
from ai_platform.serde import fingerprint as _fingerprint
from company.finance.money import Money

from .actions import ActionType, parse_action
from .authority import Decision
from .common import (
    assert_day,
    assert_prose,
    assert_record_id,
    assert_seat_id,
    ref_tuple,
    text_tuple,
)
from .errors import DelegationError, PilotBoundaryViolation
from .org import CEO_SEAT, Hierarchy
from .pilot import (
    PILOT_SEATS,
    LivePilotDecision,
    PilotActivation,
    PilotMode,
    PilotRequest,
)
from .policy import DelegationPolicy, parse_risk


LIVE_RECORD_VERSION = 1


@dataclass(frozen=True)
class LivePilotDecisionRecord:
    """One live delegated decision, as it will be stored and audited."""

    # --- identity ---------------------------------------------------------
    decision_id: str
    recorded_on: dt.date
    objective_id: str
    work_order_id: str
    department: str

    # --- the people -------------------------------------------------------
    requesting_seat: str
    requesting_employee: str
    approving_seat: str
    approving_employee: str
    reviewer: str

    # --- the decision -----------------------------------------------------
    action: ActionType
    risk: Risk
    decision: Decision
    reason: str
    authority_source: str
    ceo_required: bool

    # --- the limits it was taken against ----------------------------------
    mode: PilotMode
    policy_version: str
    policy_fingerprint: str
    envelope_id: str
    envelope_fingerprint: str
    activation_id: str

    # --- the chain --------------------------------------------------------
    escalation_chain: tuple[str, ...] = ()
    escalation_target: str = ""

    # --- money ------------------------------------------------------------
    budget_used: Money | None = None
    budget_limit: Money | None = None
    budget_scope: str = ""

    # --- the rest ---------------------------------------------------------
    implementer: str = ""
    integration_branch: str = ""
    gates_checked: int = 0
    gates_failed: tuple[str, ...] = ()
    exception_classes: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    request_fingerprint: str = ""
    authorizes_action: bool = False
    version: int = LIVE_RECORD_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "decision_id", assert_record_id(self.decision_id, "live.decision_id")
        )
        object.__setattr__(
            self, "recorded_on", assert_day(self.recorded_on, "live.recorded_on")
        )
        for name in ("objective_id", "work_order_id", "envelope_id", "activation_id"):
            value = getattr(self, name)
            if value:
                object.__setattr__(self, name, assert_record_id(value, f"live.{name}"))
        object.__setattr__(
            self, "department", assert_prose(self.department, "live.department").lower()
        )
        for name in ("requesting_seat", "approving_seat"):
            object.__setattr__(
                self, name, assert_seat_id(getattr(self, name), f"live.{name}")
            )
        for name in ("requesting_employee", "approving_employee", "reviewer", "implementer"):
            value = getattr(self, name)
            if value:
                object.__setattr__(
                    self, name, assert_seat_id(value, f"live.{name}")
                )
        object.__setattr__(self, "action", parse_action(self.action, "live.action"))
        object.__setattr__(self, "risk", parse_risk(self.risk, "live.risk"))
        if not isinstance(self.decision, Decision):
            raise DelegationError("live.decision must be a Decision value")
        if not isinstance(self.mode, PilotMode):
            raise DelegationError("live.mode must be a PilotMode value")
        object.__setattr__(self, "reason", assert_prose(self.reason, "live.reason"))
        object.__setattr__(
            self,
            "authority_source",
            assert_prose(self.authority_source, "live.authority_source"),
        )
        for flag in ("ceo_required", "authorizes_action"):
            if not isinstance(getattr(self, flag), bool):
                raise DelegationError(f"live.{flag} must be a boolean")
        object.__setattr__(
            self,
            "escalation_chain",
            text_tuple(self.escalation_chain, "live.escalation_chain", limit=32),
        )
        object.__setattr__(
            self,
            "gates_failed",
            text_tuple(self.gates_failed, "live.gates_failed", limit=32),
        )
        object.__setattr__(
            self,
            "exception_classes",
            text_tuple(self.exception_classes, "live.exception_classes", limit=16),
        )
        object.__setattr__(
            self, "evidence_refs", ref_tuple(self.evidence_refs, "live.evidence_refs")
        )
        for name in ("budget_used", "budget_limit"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, Money):
                raise DelegationError(f"live.{name} must be Money or None")
        if isinstance(self.gates_checked, bool) or not isinstance(self.gates_checked, int):
            raise DelegationError("live.gates_checked must be an integer")
        if self.gates_checked < 0:
            raise DelegationError("live.gates_checked is not negative")
        if self.version != LIVE_RECORD_VERSION:
            raise DelegationError(f"live.version must be {LIVE_RECORD_VERSION}")

        # --- the invariants -------------------------------------------------

        if self.authorizes_action:
            if self.mode is not PilotMode.LIVE_PILOT:
                raise PilotBoundaryViolation(
                    "a record in shadow mode cannot claim to have authorized an "
                    "action; that is what shadow means"
                )
            if self.decision is not Decision.APPROVED:
                raise PilotBoundaryViolation(
                    f"a {self.decision.value!r} record cannot authorize an action"
                )
            if self.ceo_required:
                raise PilotBoundaryViolation(
                    "a record that required the CEO cannot also record that the "
                    "action was authorized without them"
                )
            if self.approving_seat == CEO_SEAT:
                raise PilotBoundaryViolation(
                    "this package never writes a CEO approval; a CEO decision is a "
                    "named human act recorded by company/engineering/decision.py"
                )
            if self.approving_seat not in PILOT_SEATS:
                raise PilotBoundaryViolation(
                    f"seat {self.approving_seat!r} holds no live authority in this pilot"
                )
            if self.action not in PILOT_SEATS[self.approving_seat]:
                raise PilotBoundaryViolation(
                    f"seat {self.approving_seat!r} may not live-approve "
                    f"{self.action.value!r}"
                )
            if self.gates_failed:
                raise PilotBoundaryViolation(
                    "a live approval requires every gate to hold; these did not: "
                    + ", ".join(self.gates_failed)
                )
            if not self.envelope_id or not self.activation_id:
                raise PilotBoundaryViolation(
                    "a live approval must name the envelope and activation it was "
                    "taken under; an approval with no envelope is not delegated, it "
                    "is unbounded"
                )
            # The audit question this record exists to answer.
            if self.approving_employee and self.reviewer:
                if self.approving_employee == self.reviewer:
                    raise PilotBoundaryViolation(
                        f"{self.approving_employee} both reviewed and approved this "
                        "work; the reviewer and the approver are two people"
                    )
            if self.approving_employee and self.implementer:
                if self.approving_employee == self.implementer:
                    raise PilotBoundaryViolation(
                        f"{self.approving_employee} both implemented and approved this "
                        "work; no seat may approve its own implementation"
                    )
        if self.ceo_required and self.decision is Decision.APPROVED:
            raise PilotBoundaryViolation(
                "a record cannot be both approved below the CEO and marked as "
                "requiring the CEO"
            )

    @property
    def handled_internally(self) -> bool:
        return not self.ceo_required and self.decision is not Decision.ESCALATE

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "recorded_on": self.recorded_on.isoformat(),
            "objective_id": self.objective_id,
            "work_order_id": self.work_order_id,
            "department": self.department,
            "requesting_seat": self.requesting_seat,
            "requesting_employee": self.requesting_employee,
            "approving_seat": self.approving_seat,
            "approving_employee": self.approving_employee,
            "reviewer": self.reviewer,
            "implementer": self.implementer,
            "action": self.action.value,
            "risk": self.risk.value,
            "decision": self.decision.value,
            "reason": self.reason,
            "authority_source": self.authority_source,
            "ceo_required": self.ceo_required,
            "mode": self.mode.value,
            "policy_version": self.policy_version,
            "policy_fingerprint": self.policy_fingerprint,
            "envelope_id": self.envelope_id,
            "envelope_fingerprint": self.envelope_fingerprint,
            "activation_id": self.activation_id,
            "escalation_chain": list(self.escalation_chain),
            "escalation_target": self.escalation_target,
            "budget_used": self.budget_used.to_dict() if self.budget_used else None,
            "budget_limit": self.budget_limit.to_dict() if self.budget_limit else None,
            "budget_scope": self.budget_scope,
            "integration_branch": self.integration_branch,
            "gates_checked": self.gates_checked,
            "gates_failed": list(self.gates_failed),
            "exception_classes": list(self.exception_classes),
            "evidence_refs": list(self.evidence_refs),
            "request_fingerprint": self.request_fingerprint,
            "authorizes_action": self.authorizes_action,
            "version": self.version,
        }

    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())

    def explain(self) -> str:
        """Why this proceeded without the CEO, in prose, for the brief."""
        if self.ceo_required:
            head = f"{self.action.value} REQUIRED the CEO"
        elif self.authorizes_action:
            head = (
                f"{self.action.value} was approved by {self.approving_employee or self.approving_seat} "
                f"({self.approving_seat}) without the CEO"
            )
        else:
            head = f"{self.action.value} was calculated but authorized nothing"
        lines = [
            head,
            f"  authority   {self.authority_source}",
            f"  envelope    {self.envelope_id or '(none)'} "
            f"[{self.envelope_fingerprint[:16] or 'n/a'}]",
            f"  risk        {self.risk.value}",
            f"  reviewer    {self.reviewer or '(none recorded)'}",
            f"  implementer {self.implementer or '(none recorded)'}",
            f"  gates       {self.gates_checked} checked, "
            f"{len(self.gates_failed)} failed",
            f"  reason      {self.reason}",
        ]
        if self.escalation_chain:
            lines.append("  chain       " + " -> ".join(self.escalation_chain))
        return "\n".join(lines)


def _employee_of(hierarchy: Hierarchy | None, seat: str) -> str:
    """The employee sitting in a seat today, or "" when nobody does."""
    if hierarchy is None or not seat:
        return ""
    try:
        found = hierarchy.seat(seat)
    except Exception:  # noqa: BLE001
        # A seat the hierarchy does not know is not an error here: the record
        # is evidence, and "we could not name the employee" is a truthful thing
        # for it to say. The authority check that mattered already ran.
        return ""
    return str(getattr(found, "employee", "") or "")


def record_live_decision(
    live: LivePilotDecision,
    pilot_request: PilotRequest,
    *,
    decision_id: str,
    recorded_on: dt.date,
    policy: DelegationPolicy,
    activation: PilotActivation | None = None,
    hierarchy: Hierarchy | None = None,
    budget_used: Money | None = None,
    exception_classes: tuple[str, ...] = (),
    evidence_refs: tuple[str, ...] = (),
) -> LivePilotDecisionRecord:
    """Turn one live decision into the row that will be stored.

    Pure: it reads the decision, the request and the policy and writes nothing.
    Persisting the result is the caller's business, exactly as it is for
    `ExecutiveDecisionRecord`.
    """
    if not isinstance(live, LivePilotDecision):
        raise DelegationError("record_live_decision expects a LivePilotDecision")
    if not isinstance(pilot_request, PilotRequest):
        raise DelegationError("record_live_decision expects a PilotRequest")

    request = pilot_request.request
    envelope = activation.envelope if activation else None
    chain = tuple(
        f"{step.seat}:{step.insufficiency.value}"
        for step in live.shadow_decision.chain
    )
    return LivePilotDecisionRecord(
        decision_id=decision_id,
        recorded_on=recorded_on,
        objective_id=request.objective_id,
        work_order_id=request.work_order_id,
        department=request.department,
        requesting_seat=request.requesting_seat,
        requesting_employee=_employee_of(hierarchy, request.requesting_seat),
        approving_seat=live.actor,
        approving_employee=_employee_of(hierarchy, live.actor),
        reviewer=request.reviewer,
        implementer=request.implementer,
        action=live.action,
        risk=live.risk,
        decision=live.decision,
        reason=live.reason,
        authority_source=live.authority_source,
        ceo_required=live.ceo_required,
        mode=live.mode,
        policy_version=policy.version,
        policy_fingerprint=policy.fingerprint(),
        envelope_id=envelope.envelope_id if envelope else "",
        envelope_fingerprint=envelope.fingerprint() if envelope else "",
        activation_id=activation.activation_id if activation else "",
        escalation_chain=chain,
        escalation_target=live.escalation_target,
        budget_used=budget_used if budget_used is not None else request.amount,
        budget_limit=envelope.budget if envelope else None,
        budget_scope=request.budget_scope,
        integration_branch=live.integration_branch,
        gates_checked=len(live.gates),
        gates_failed=tuple(item.gate_id.value for item in live.failed_gates),
        exception_classes=exception_classes,
        evidence_refs=evidence_refs or request.evidence_refs,
        request_fingerprint=request.fingerprint(),
        authorizes_action=live.authorizes_action,
    )


__all__ = [
    "LIVE_RECORD_VERSION",
    "LivePilotDecisionRecord",
    "record_live_decision",
]

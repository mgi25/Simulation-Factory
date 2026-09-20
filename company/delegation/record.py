"""The executive decision record: one row, fully attributable, never an action.

Every field exists so that a reader six months later can answer "who decided
this, under what authority, and what would have happened if they had not". A
record that cannot answer all three is not evidence, it is a log line.

## Why `shadow` is a field and not a deployment detail

`shadow=True` is written into the record itself, so a record produced in this
phase can never be mistaken for one produced after activation — not by a later
reader, not by a report, and not by a migration that copies a directory. It
refuses to be `False`, exactly as `authorizes_action` does, and the two together
are what make a stored delegation history safe to keep.

## Why the record carries the policy fingerprint and not the policy

A decision means nothing without the limits it was taken against, and limits
change. Storing the whole policy in every record would make the store large and
the diffs unreadable; storing nothing would make an old decision unauditable.
The fingerprint is the middle: `DelegationPolicy.fingerprint()` over the
hierarchy, the grants, the ladder and the reserved set, so an audit can say
"these four decisions were taken under a policy that no longer exists" without
guessing.

## Why `ceo_required` and `decision` are both recorded

They are not redundant. `decision` is what the model concluded; `ceo_required`
is whether it needed a human. `ESCALATE` with `ceo_required=False` is a real
and useful state — the action went up one level and a manager took it — and
collapsing the two would lose exactly the number this phase is trying to
produce: how much stayed below the CEO.
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
from .authority import AuthorityDecision, AuthorityRequest, Decision
from .common import (
    assert_day,
    assert_prose,
    assert_record_id,
    assert_seat_id,
    ref_tuple,
)
from .exceptions import ExceptionReport
from .errors import AuthorityViolation, DelegationError, ShadowModeViolation
from .org import CEO_SEAT
from .policy import parse_risk


RECORD_VERSION = 1


@dataclass(frozen=True)
class ExecutiveDecisionRecord:
    """One delegation decision, as it will be stored and audited."""

    decision_id: str
    recorded_on: dt.date
    objective_id: str
    work_order_id: str
    department: str
    requesting_role: str
    approving_role: str
    authority_source: str
    action: ActionType
    risk: Risk
    decision: Decision
    reason: str
    escalation_target: str
    ceo_required: bool
    policy_version: str
    policy_fingerprint: str
    request_fingerprint: str
    budget_used: Money | None = None
    budget_limit: Money | None = None
    budget_scope: str = ""
    exception_classes: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    shadow: bool = True
    authorizes_action: bool = False
    version: int = RECORD_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "decision_id", assert_record_id(self.decision_id, "record.decision_id")
        )
        object.__setattr__(
            self, "recorded_on", assert_day(self.recorded_on, "record.recorded_on")
        )
        for name in ("objective_id", "work_order_id"):
            value = getattr(self, name)
            if value:
                object.__setattr__(self, name, assert_record_id(value, f"record.{name}"))
        object.__setattr__(
            self, "department", assert_prose(self.department, "record.department").lower()
        )
        object.__setattr__(
            self,
            "requesting_role",
            assert_seat_id(self.requesting_role, "record.requesting_role"),
        )
        object.__setattr__(
            self,
            "approving_role",
            assert_seat_id(self.approving_role, "record.approving_role"),
        )
        object.__setattr__(
            self,
            "authority_source",
            assert_prose(self.authority_source, "record.authority_source"),
        )
        object.__setattr__(self, "action", parse_action(self.action, "record.action"))
        object.__setattr__(self, "risk", parse_risk(self.risk, "record.risk"))
        if not isinstance(self.decision, Decision):
            raise DelegationError("record.decision must be a Decision value")
        object.__setattr__(self, "reason", assert_prose(self.reason, "record.reason"))
        if self.escalation_target:
            object.__setattr__(
                self,
                "escalation_target",
                assert_seat_id(self.escalation_target, "record.escalation_target"),
            )
        if not isinstance(self.ceo_required, bool):
            raise DelegationError("record.ceo_required must be a boolean")
        object.__setattr__(
            self,
            "policy_version",
            assert_prose(self.policy_version, "record.policy_version"),
        )
        for name in ("policy_fingerprint", "request_fingerprint"):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) != 16:
                raise DelegationError(
                    f"record.{name} must be a 16-character digest; a decision without "
                    "the fingerprint of what it decided against cannot be audited"
                )
        for name in ("budget_used", "budget_limit"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, Money):
                raise DelegationError(f"record.{name} must be Money or None")
        if self.budget_scope:
            object.__setattr__(
                self,
                "budget_scope",
                assert_record_id(self.budget_scope, "record.budget_scope"),
            )
        object.__setattr__(
            self,
            "exception_classes",
            tuple(sorted({str(item) for item in (self.exception_classes or ())})),
        )
        object.__setattr__(
            self, "evidence_refs", ref_tuple(self.evidence_refs, "record.evidence_refs")
        )
        if self.requesting_role == self.approving_role:
            raise AuthorityViolation(
                f"{self.requesting_role} appears as both the requesting and the "
                "approving role. A seat does not approve its own request; that is "
                "the condition this record exists to make visible."
            )
        if self.decision is Decision.APPROVED:
            if self.ceo_required:
                raise AuthorityViolation(
                    "a delegated approval that requires the CEO is an escalation"
                )
            if self.approving_role == CEO_SEAT:
                raise AuthorityViolation(
                    "this record never carries a CEO approval. The CEO decision on "
                    "engineering work is company/engineering/decision.py, which names "
                    "a human and is written by one."
                )
        if self.shadow is not True:
            raise ShadowModeViolation(
                "record.shadow must be true. Every record this version writes was "
                "produced while the canonical CEO stop semantics were in force, and "
                "a record that claimed otherwise would misdescribe its own history."
            )
        if self.authorizes_action is not False:
            raise AuthorityViolation(
                "a decision record never authorizes the action it describes. It says "
                "which seat would have been competent; performing the action is a "
                "separate act outside this subsystem."
            )
        if self.version != RECORD_VERSION:
            raise DelegationError(f"record.version must be {RECORD_VERSION}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "recorded_on": self.recorded_on.isoformat(),
            "objective_id": self.objective_id,
            "work_order_id": self.work_order_id,
            "department": self.department,
            "requesting_role": self.requesting_role,
            "approving_role": self.approving_role,
            "authority_source": self.authority_source,
            "action": self.action.value,
            "risk": self.risk.value,
            "decision": self.decision.value,
            "reason": self.reason,
            "escalation_target": self.escalation_target,
            "ceo_required": self.ceo_required,
            "policy_version": self.policy_version,
            "policy_fingerprint": self.policy_fingerprint,
            "request_fingerprint": self.request_fingerprint,
            "budget_used": self.budget_used.to_dict() if self.budget_used else None,
            "budget_limit": self.budget_limit.to_dict() if self.budget_limit else None,
            "budget_scope": self.budget_scope,
            "exception_classes": list(self.exception_classes),
            "evidence_refs": list(self.evidence_refs),
            "shadow": True,
            "authorizes_action": False,
            "version": self.version,
        }

    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ExecutiveDecisionRecord":
        if not isinstance(data, Mapping):
            raise DelegationError("a decision record must be a mapping")
        unknown = sorted(set(data) - set(cls.__dataclass_fields__))
        if unknown:
            raise DelegationError(
                "decision record has unknown field(s): "
                + ", ".join(unknown)
                + ". A record outside the schema is refused rather than ignored."
            )
        verdict = data.get("decision")
        if not isinstance(verdict, str):
            raise DelegationError("record.decision must be a string")
        try:
            parsed = Decision(verdict)
        except ValueError as exc:
            allowed = ", ".join(item.value for item in Decision)
            raise DelegationError(f"record.decision must be one of: {allowed}") from exc
        return cls(
            decision_id=str(data.get("decision_id", "")),
            recorded_on=assert_day(data.get("recorded_on"), "record.recorded_on"),
            objective_id=str(data.get("objective_id", "") or ""),
            work_order_id=str(data.get("work_order_id", "") or ""),
            department=str(data.get("department", "")),
            requesting_role=str(data.get("requesting_role", "")),
            approving_role=str(data.get("approving_role", "")),
            authority_source=str(data.get("authority_source", "")),
            action=parse_action(data.get("action"), "record.action"),
            risk=parse_risk(data.get("risk"), "record.risk"),
            decision=parsed,
            reason=str(data.get("reason", "")),
            escalation_target=str(data.get("escalation_target", "") or ""),
            ceo_required=bool(data.get("ceo_required", False)),
            policy_version=str(data.get("policy_version", "")),
            policy_fingerprint=str(data.get("policy_fingerprint", "")),
            request_fingerprint=str(data.get("request_fingerprint", "")),
            budget_used=(
                Money.from_dict(dict(data["budget_used"]), "record.budget_used")
                if data.get("budget_used")
                else None
            ),
            budget_limit=(
                Money.from_dict(dict(data["budget_limit"]), "record.budget_limit")
                if data.get("budget_limit")
                else None
            ),
            budget_scope=str(data.get("budget_scope", "") or ""),
            exception_classes=tuple(data.get("exception_classes", ())),
            evidence_refs=tuple(data.get("evidence_refs", ())),
            shadow=bool(data.get("shadow", True)),
            authorizes_action=bool(data.get("authorizes_action", False)),
            version=int(data.get("version", RECORD_VERSION)),
        )


def record_decision(
    request: AuthorityRequest,
    decision: AuthorityDecision,
    *,
    decision_id: str,
    recorded_on: dt.date,
    policy_version: str,
    exceptions: ExceptionReport | None = None,
    evidence_refs: tuple[str, ...] = (),
) -> ExecutiveDecisionRecord:
    """Turn one evaluated request into the row that will be stored.

    The escalation target is read off the decision rather than recomputed: the
    chain the evaluation actually walked is the auditable fact, and a second
    derivation could disagree with it after a policy change.
    """
    if request.request_id != decision.request_id:
        raise DelegationError(
            f"the decision is for {decision.request_id} and the request is "
            f"{request.request_id}"
        )
    target = ""
    if decision.escalation_required:
        target = decision.actor
    approving = decision.actor
    if approving == request.requesting_seat:
        # Only possible for a REJECTED answer, where the requesting seat is
        # recorded as the actor because that is where the refusal was raised.
        # The record attributes it to the seat the chain finally reached, so no
        # record ever shows a seat deciding its own request — and the
        # escalation target moves with it, because "escalated to the seat that
        # raised it" is not a destination.
        #
        # `considered` is ordered, nearest seat first and the CEO last
        # (`company/delegation/common.seat_tuple` refuses to sort it), so the
        # last entry is the seat the request reached.
        superiors = [
            seat for seat in decision.considered if seat != request.requesting_seat
        ]
        approving = superiors[-1] if superiors else CEO_SEAT
        target = approving
    return ExecutiveDecisionRecord(
        decision_id=decision_id,
        recorded_on=recorded_on,
        objective_id=request.objective_id,
        work_order_id=request.work_order_id,
        department=request.department,
        requesting_role=request.requesting_seat,
        approving_role=approving,
        authority_source=decision.authority_source,
        action=decision.action,
        risk=decision.risk,
        decision=decision.decision,
        reason=decision.reason,
        escalation_target=target,
        ceo_required=decision.ceo_required,
        policy_version=policy_version,
        policy_fingerprint=decision.policy_fingerprint,
        request_fingerprint=request.fingerprint(),
        budget_used=decision.budget.consumed if decision.budget else None,
        budget_limit=decision.budget.ceiling if decision.budget else None,
        budget_scope=(decision.budget.scope_id if decision.budget else ""),
        exception_classes=tuple(
            item.value for item in (exceptions.classes if exceptions else ())
        ),
        evidence_refs=tuple(evidence_refs) + tuple(request.evidence_refs),
    )


__all__ = [
    "RECORD_VERSION",
    "ExecutiveDecisionRecord",
    "record_decision",
]

"""The decision: one request, one deterministic answer, and the chain that got there.

```
ACTION -> authority check -> lowest sufficient seat -> APPROVE / REJECT / ESCALATE
```

`evaluate` walks the escalation chain from the requesting seat upward and stops
at the **first** seat that could decide. It never jumps to the CEO because the
CEO is certain to be able to decide — that is the behaviour this whole phase
exists to replace. If no seat in the chain suffices, the answer is ESCALATE with
`ceo_required=True`, and every seat it passed is recorded with the reason it was
insufficient.

## The order of the checks, and why it is this order

1. **Reserved.** A reserved action is CEO-reserved whatever the risk or the
   amount, so it is answered before anything else is measured. Measuring first
   would produce a record saying a department lead was within budget for
   publishing a video, which is true and grotesque.
2. **Scope.** Does any grant in the chain cover this action type at all, for
   this department? An action outside every grant is REJECTED at the seat that
   was asked and escalates from there — it is not an approval and not an error.
3. **Self-approval.** A seat never decides a request it originated. This is
   checked before the ceilings so that a seat cannot approve its own request by
   keeping it small.
4. **Standing.** Can the seat decide anything today — is it filled, active, and
   held at an autonomy level this action needs? A dormant seat fails here.
5. **Risk**, then **budget**. The two ceilings, cheapest first.

A seat that fails 2, 4, 5 or 6 does not reject: it passes the request up. Only
a seat that could have decided and found the action outside its *scope of
competence* produces REJECTED, and only when no superior covers it either.

## Why the decision cannot authorize anything

`AuthorityDecision.authorizes_action` is `False` and refuses to be anything
else, exactly as `company.engineering.decision.CEODecision.authorizes_merge`
does. Recording that the engineering manager *would* have been authorized is
testimony about a policy. Acting on it is a separate act, and in this phase
nothing performs it: the canonical CEO decision record is still the only thing
that closes a job, and this package contains no code that could move one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ai_platform.resource_classes import Risk
from ai_platform.serde import fingerprint as _fingerprint
from company.finance.money import Money

from .actions import RESERVED_AS, RESERVED_HERE_REASON, ActionType, parse_action
from .budget import BudgetFinding
from .common import (
    assert_prose,
    assert_record_id,
    assert_seat_id,
    ref_tuple,
    seat_tuple,
    text_tuple,
)
from .errors import AuthorityViolation, DelegationError
from .org import CEO_SEAT, SeatAvailability
from .policy import DelegationPolicy, parse_risk, risk_rank


class Decision(str, Enum):
    """The three answers. There is no fourth, and no "probably"."""

    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATE = "escalate"


class Insufficiency(str, Enum):
    """Why one seat could not decide. Recorded per seat, in chain order."""

    NO_GRANT = "no_grant"
    OUT_OF_SCOPE = "out_of_scope"
    WRONG_DEPARTMENT = "wrong_department"
    SELF_APPROVAL = "self_approval"
    IMPLEMENTER_IS_APPROVER = "implementer_is_approver"
    REVIEWER_IS_APPROVER = "reviewer_is_approver"
    WOULD_OVERRIDE_INDEPENDENT_CONTROL = "would_override_independent_control"
    SEAT_VACANT = "seat_vacant"
    SEAT_DORMANT = "seat_dormant"
    SEAT_RESTRICTED = "seat_restricted"
    AUTONOMY_TOO_LOW = "autonomy_too_low"
    RISK_ABOVE_CEILING = "risk_above_ceiling"
    BUDGET_ABOVE_CEILING = "budget_above_ceiling"
    BUDGET_UNKNOWN = "budget_unknown"
    RESERVED_ACTION = "reserved_action"


@dataclass(frozen=True)
class ChainStep:
    """One seat the request passed through, and why it did not stop there."""

    seat: str
    insufficiency: Insufficiency
    detail: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "seat", assert_seat_id(self.seat, "chain.seat"))
        if not isinstance(self.insufficiency, Insufficiency):
            raise DelegationError("chain.insufficiency must be an Insufficiency value")
        object.__setattr__(self, "detail", assert_prose(self.detail, "chain.detail"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "seat": self.seat,
            "insufficiency": self.insufficiency.value,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class AuthorityRequest:
    """One thing somebody wants to do, described so a policy can answer it."""

    request_id: str
    action: ActionType
    requesting_seat: str
    department: str
    risk: Risk
    objective_id: str = ""
    work_order_id: str = ""
    budget_scope: str = ""
    amount: Money | None = None
    summary: str = ""
    reversible: bool = True
    evidence_refs: tuple[str, ...] = ()
    write_scope: tuple[str, ...] = ()
    # Separation of duties. These name *employees*, not seats, because the
    # implementer and the reviewer are routed per work order by capability and
    # are not positions on the chart. A seat is disqualified when the employee
    # sitting in it is the one whose work is being judged, or the one who
    # already judged it.
    implementer: str = ""
    reviewer: str = ""
    # True when the action would set aside a failing deterministic QA run or a
    # reviewer verdict. No delegated seat may do this at any risk or amount.
    overrides_independent_control: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "request_id", assert_record_id(self.request_id, "request_id")
        )
        object.__setattr__(self, "action", parse_action(self.action, "request.action"))
        object.__setattr__(
            self,
            "requesting_seat",
            assert_seat_id(self.requesting_seat, "request.requesting_seat"),
        )
        if self.requesting_seat == CEO_SEAT:
            raise AuthorityViolation(
                "the CEO does not file a request with the delegation model; the CEO "
                "sets the objective the model runs under"
            )
        object.__setattr__(
            self, "department", assert_prose(self.department, "request.department").lower()
        )
        object.__setattr__(self, "risk", parse_risk(self.risk, "request.risk"))
        for name in ("objective_id", "work_order_id"):
            value = getattr(self, name)
            if value:
                object.__setattr__(self, name, assert_record_id(value, f"request.{name}"))
        if self.budget_scope:
            object.__setattr__(
                self,
                "budget_scope",
                assert_record_id(self.budget_scope, "request.budget_scope"),
            )
        if self.amount is not None and not isinstance(self.amount, Money):
            raise DelegationError("request.amount must be Money or None")
        if self.amount is not None and self.amount.is_negative:
            raise DelegationError("request.amount is not negative")
        object.__setattr__(
            self,
            "summary",
            assert_prose(self.summary, "request.summary") if self.summary else "",
        )
        if not isinstance(self.reversible, bool):
            raise DelegationError("request.reversible must be a boolean")
        object.__setattr__(
            self, "evidence_refs", ref_tuple(self.evidence_refs, "request.evidence_refs")
        )
        object.__setattr__(
            self, "write_scope", text_tuple(self.write_scope, "request.write_scope")
        )
        for name in ("implementer", "reviewer"):
            value = getattr(self, name)
            if value:
                object.__setattr__(
                    self, name, assert_seat_id(value, f"request.{name}")
                )
        if not isinstance(self.overrides_independent_control, bool):
            raise DelegationError(
                "request.overrides_independent_control must be a boolean"
            )

    @property
    def spends_money(self) -> bool:
        return self.amount is not None and not self.amount.is_zero

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "action": self.action.value,
            "requesting_seat": self.requesting_seat,
            "department": self.department,
            "risk": self.risk.value,
            "objective_id": self.objective_id,
            "work_order_id": self.work_order_id,
            "budget_scope": self.budget_scope,
            "amount": self.amount.to_dict() if self.amount else None,
            "summary": self.summary,
            "reversible": self.reversible,
            "evidence_refs": list(self.evidence_refs),
            "write_scope": list(self.write_scope),
            "implementer": self.implementer,
            "reviewer": self.reviewer,
            "overrides_independent_control": self.overrides_independent_control,
        }

    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())


@dataclass(frozen=True)
class AuthorityDecision:
    """Who would decide this, on what authority, and whether the CEO is needed."""

    request_id: str
    decision: Decision
    actor: str
    authority_source: str
    action: ActionType
    risk: Risk
    escalation_required: bool
    ceo_required: bool
    reason: str
    chain: tuple[ChainStep, ...] = ()
    considered: tuple[str, ...] = ()
    budget: BudgetFinding | None = None
    policy_fingerprint: str = ""
    reserved_as: str = ""
    authorizes_action: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "request_id", assert_record_id(self.request_id, "decision.request_id")
        )
        if not isinstance(self.decision, Decision):
            raise DelegationError("decision.decision must be a Decision value")
        object.__setattr__(self, "actor", assert_seat_id(self.actor, "decision.actor"))
        object.__setattr__(
            self,
            "authority_source",
            assert_prose(self.authority_source, "decision.authority_source"),
        )
        object.__setattr__(self, "action", parse_action(self.action, "decision.action"))
        object.__setattr__(self, "risk", parse_risk(self.risk, "decision.risk"))
        for flag in ("escalation_required", "ceo_required"):
            if not isinstance(getattr(self, flag), bool):
                raise DelegationError(f"decision.{flag} must be a boolean")
        object.__setattr__(self, "reason", assert_prose(self.reason, "decision.reason"))
        if not isinstance(self.chain, tuple) or any(
            not isinstance(item, ChainStep) for item in self.chain
        ):
            raise DelegationError("decision.chain must be a tuple of ChainStep")
        object.__setattr__(
            self, "considered", seat_tuple(self.considered, "decision.considered")
        )
        if self.decision is Decision.APPROVED and self.ceo_required:
            raise AuthorityViolation(
                "a decision cannot both be approved by a delegated seat and require "
                "the CEO; the CEO answer is ESCALATE"
            )
        if self.decision is Decision.APPROVED and self.actor == CEO_SEAT:
            raise AuthorityViolation(
                "this model never writes a CEO approval. Reaching the CEO seat is "
                "ESCALATE; the approval itself is a named human act recorded by "
                "company/engineering/decision.py."
            )
        if self.ceo_required and not self.escalation_required:
            raise DelegationError(
                "a decision that requires the CEO is by definition an escalation"
            )
        if self.authorizes_action is not False:
            raise AuthorityViolation(
                "an authority decision never carries authority to act. It records "
                "which seat would be competent under the policy; performing the "
                "action is a separate act this package cannot perform."
            )

    @property
    def handled_internally(self) -> bool:
        """Decided below the CEO. The number the executive brief counts."""
        return not self.ceo_required and self.decision is not Decision.ESCALATE

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "decision": self.decision.value,
            "actor": self.actor,
            "authority_source": self.authority_source,
            "action": self.action.value,
            "risk": self.risk.value,
            "escalation_required": self.escalation_required,
            "ceo_required": self.ceo_required,
            "reason": self.reason,
            "chain": [step.to_dict() for step in self.chain],
            "considered": list(self.considered),
            "budget": self.budget.to_dict() if self.budget else None,
            "policy_fingerprint": self.policy_fingerprint,
            "reserved_as": self.reserved_as,
            "authorizes_action": False,
        }

    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())


def _reserved_reason(action: ActionType) -> str:
    named = RESERVED_AS.get(action)
    if named:
        return (
            f"{action.value} is reserved to the CEO as {named!r} in "
            "company/permissions.yaml"
        )
    return (
        f"{action.value} is reserved by the delegation model itself: "
        + RESERVED_HERE_REASON.get(action, "it would let the model widen its own limits")
    )


def evaluate(
    request: AuthorityRequest,
    policy: DelegationPolicy,
    *,
    consumed: Mapping[str, Money] | None = None,
) -> AuthorityDecision:
    """Answer one request against one policy. Pure, and the same every time."""
    if not isinstance(request, AuthorityRequest):
        raise DelegationError("evaluate takes an AuthorityRequest")
    if not isinstance(policy, DelegationPolicy):
        raise DelegationError("evaluate takes a DelegationPolicy")

    fingerprint = policy.fingerprint()
    # The line chain, with any functional seats for this action spliced in
    # below the CEO. For money that is the CFO, which no reporting line
    # passes through.
    chain_ids = policy.effective_chain(request.requesting_seat, request.action)

    # 1. Reserved beats everything, and is answered before anything is measured.
    if policy.is_reserved(request.action):
        return AuthorityDecision(
            request_id=request.request_id,
            decision=Decision.ESCALATE,
            actor=CEO_SEAT,
            authority_source=policy.version,
            action=request.action,
            risk=request.risk,
            escalation_required=True,
            ceo_required=True,
            reason=_reserved_reason(request.action),
            chain=(
                ChainStep(
                    seat=request.requesting_seat,
                    insufficiency=Insufficiency.RESERVED_ACTION,
                    detail=_reserved_reason(request.action),
                ),
            ),
            considered=chain_ids,
            policy_fingerprint=fingerprint,
            reserved_as=RESERVED_AS.get(request.action, ""),
        )

    steps: list[ChainStep] = []
    covered_anywhere = False

    for seat_id in chain_ids:
        if seat_id == CEO_SEAT:
            break
        grant = policy.grant(seat_id)
        if grant is None:
            steps.append(
                ChainStep(
                    seat=seat_id,
                    insufficiency=Insufficiency.NO_GRANT,
                    detail=f"{seat_id} holds no delegated grant under {policy.version}",
                )
            )
            continue
        if not grant.covers(request.action):
            steps.append(
                ChainStep(
                    seat=seat_id,
                    insufficiency=Insufficiency.OUT_OF_SCOPE,
                    detail=(
                        f"{seat_id} may not approve {request.action.value}; its grant "
                        f"covers {len(grant.action_types)} other action type(s)"
                    ),
                )
            )
            continue
        covered_anywhere = True

        seat = policy.hierarchy.seat(seat_id)
        if seat.departments and request.department not in seat.departments:
            steps.append(
                ChainStep(
                    seat=seat_id,
                    insufficiency=Insufficiency.WRONG_DEPARTMENT,
                    detail=(
                        f"{seat_id} covers {', '.join(seat.departments)} and the "
                        f"request is from {request.department}"
                    ),
                )
            )
            continue
        if seat_id == request.requesting_seat:
            steps.append(
                ChainStep(
                    seat=seat_id,
                    insufficiency=Insufficiency.SELF_APPROVAL,
                    detail=(
                        f"{seat_id} raised this request and does not decide it. A seat "
                        "that signs its own work is not a control."
                    ),
                )
            )
            continue

        # Separation of duties, checked against the *employee* in the seat.
        # Before the ceilings, for the same reason self-approval is: a
        # disqualified approver cannot become qualified by the request being
        # small. No delegated seat may set aside an independent control, so
        # that condition disqualifies every seat below the CEO rather than
        # being passed up one level at a time.
        if request.overrides_independent_control:
            steps.append(
                ChainStep(
                    seat=seat_id,
                    insufficiency=Insufficiency.WOULD_OVERRIDE_INDEPENDENT_CONTROL,
                    detail=(
                        f"{seat_id} would be setting aside a failing deterministic "
                        "check or a reviewer verdict. Management decides what to do "
                        "about a finding; it does not decide that the finding is "
                        "wrong."
                    ),
                )
            )
            continue

        seat_employee = policy.hierarchy.seat(seat_id).employee
        if seat_employee and seat_employee == request.implementer:
            steps.append(
                ChainStep(
                    seat=seat_id,
                    insufficiency=Insufficiency.IMPLEMENTER_IS_APPROVER,
                    detail=(
                        f"{seat_id} is filled by {seat_employee}, who implemented the "
                        "work under decision"
                    ),
                )
            )
            continue
        if seat_employee and seat_employee == request.reviewer:
            steps.append(
                ChainStep(
                    seat=seat_id,
                    insufficiency=Insufficiency.REVIEWER_IS_APPROVER,
                    detail=(
                        f"{seat_id} is filled by {seat_employee}, who reviewed the "
                        "work under decision. Independent review and managerial "
                        "approval are two controls, and one employee performing both "
                        "is one control."
                    ),
                )
            )
            continue

        standing = policy.hierarchy.standing(seat_id)
        if not standing.can_decide:
            mapping = {
                SeatAvailability.VACANT: Insufficiency.SEAT_VACANT,
                SeatAvailability.DORMANT: Insufficiency.SEAT_DORMANT,
                SeatAvailability.RESTRICTED: Insufficiency.SEAT_RESTRICTED,
                SeatAvailability.EXTERNAL_HUMAN: Insufficiency.NO_GRANT,
            }
            steps.append(
                ChainStep(
                    seat=seat_id,
                    insufficiency=mapping[standing.availability],
                    detail=standing.detail,
                )
            )
            continue
        needed = policy.required_autonomy(request.action)
        if standing.authority_cap < needed:
            steps.append(
                ChainStep(
                    seat=seat_id,
                    insufficiency=Insufficiency.AUTONOMY_TOO_LOW,
                    detail=(
                        f"{request.action.value} needs autonomy {needed} and "
                        f"{seat_id} is capped at {standing.authority_cap}"
                    ),
                )
            )
            continue
        if risk_rank(request.risk) > risk_rank(grant.max_risk):
            steps.append(
                ChainStep(
                    seat=seat_id,
                    insufficiency=Insufficiency.RISK_ABOVE_CEILING,
                    detail=(
                        f"{seat_id} may approve up to {grant.max_risk.value} risk and "
                        f"this is {request.risk.value}"
                    ),
                )
            )
            continue

        budget: BudgetFinding | None = None
        if request.spends_money:
            if request.amount is not None and request.amount > grant.per_decision_ceiling:
                steps.append(
                    ChainStep(
                        seat=seat_id,
                        insufficiency=Insufficiency.BUDGET_ABOVE_CEILING,
                        detail=(
                            f"{request.amount} is above the {grant.per_decision_ceiling} "
                            f"a single {seat_id} decision may approve"
                        ),
                    )
                )
                continue
            scope = request.budget_scope or grant.budget_scope
            budget = policy.ladder.check(scope, request.amount, consumed)
            if not budget.known:
                steps.append(
                    ChainStep(
                        seat=seat_id,
                        insufficiency=Insufficiency.BUDGET_UNKNOWN,
                        detail=budget.reason,
                    )
                )
                continue
            if not budget.within:
                steps.append(
                    ChainStep(
                        seat=seat_id,
                        insufficiency=Insufficiency.BUDGET_ABOVE_CEILING,
                        detail=budget.reason,
                    )
                )
                continue

        reason = (
            f"{seat_id} is the lowest seat with authority over "
            f"{request.action.value} at {request.risk.value} risk"
        )
        if budget is not None:
            reason = f"{reason}; {budget.reason}"
        return AuthorityDecision(
            request_id=request.request_id,
            decision=Decision.APPROVED,
            actor=seat_id,
            authority_source=policy.version,
            action=request.action,
            risk=request.risk,
            escalation_required=False,
            ceo_required=False,
            reason=reason,
            chain=tuple(steps),
            considered=chain_ids,
            budget=budget,
            policy_fingerprint=fingerprint,
        )

    # Nothing below the CEO could decide it.
    if not covered_anywhere:
        detail = (
            f"no seat between {request.requesting_seat} and the CEO holds "
            f"{request.action.value} in its grant"
        )
        return AuthorityDecision(
            request_id=request.request_id,
            decision=Decision.REJECTED,
            actor=request.requesting_seat,
            authority_source=policy.version,
            action=request.action,
            risk=request.risk,
            escalation_required=True,
            ceo_required=True,
            reason=(
                detail
                + ". The action is outside the delegated model entirely, so it is "
                "refused here and carried to the CEO as an unclassified request "
                "rather than approved by the nearest seat that happened to be free."
            ),
            chain=tuple(steps),
            considered=chain_ids,
            policy_fingerprint=fingerprint,
        )

    blocking = steps[-1] if steps else None
    if blocking is None:
        reason = f"every seat from {request.requesting_seat} to the CEO was insufficient"
    else:
        reason = f"the chain stopped at {blocking.seat}: {blocking.detail}"
        # The self-approval skip is the headline whenever it happened, because
        # "the COO does not hold this action" reads as a policy gap when the
        # real cause is that the only seat that does raised the request itself.
        self_skip = next(
            (
                step
                for step in steps
                if step.insufficiency is Insufficiency.SELF_APPROVAL
            ),
            None,
        )
        if self_skip is not None and self_skip is not blocking:
            reason = (
                f"{self_skip.seat} holds this action and raised the request, so it "
                f"does not decide it; {reason}"
            )
    return AuthorityDecision(
        request_id=request.request_id,
        decision=Decision.ESCALATE,
        actor=CEO_SEAT,
        authority_source=policy.version,
        action=request.action,
        risk=request.risk,
        escalation_required=True,
        ceo_required=True,
        reason=reason,
        chain=tuple(steps),
        considered=chain_ids,
        policy_fingerprint=fingerprint,
    )


def evaluate_all(
    requests: Sequence[AuthorityRequest],
    policy: DelegationPolicy,
    *,
    consumed: Mapping[str, Money] | None = None,
) -> tuple[AuthorityDecision, ...]:
    """Answer a batch in order. No request sees another one's answer."""
    return tuple(evaluate(item, policy, consumed=consumed) for item in requests)


__all__ = [
    "AuthorityDecision",
    "AuthorityRequest",
    "ChainStep",
    "Decision",
    "Insufficiency",
    "evaluate",
    "evaluate_all",
]

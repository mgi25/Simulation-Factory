"""What the CEO is told about, and the far longer list of what they are not.

Management by exception is usually described as a filter on outputs. It is more
useful as a **closed set of named conditions**, because the question that
actually matters is not "was this interesting" but "is there a rule under which
this had to be raised". So `ExceptionClass` is an enum, `classify` returns the
members that fired, and routine success returns an empty tuple.

## Why routine success is not an exception

It is worth saying out loud, because the failure mode of every reporting system
is that it starts reporting everything. `test_routine_success_raises_no_exception`
is the test that keeps this honest: a LOW-risk approved change, inside budget,
inside the envelope, with a passing review, produces `()`. If that test ever
needs updating to accommodate a new class, the new class is wrong.

## Why some classes come from the decision and some from the context

`AUTHORITY_EXCEEDED`, `BUDGET_CEILING_EXCEEDED`, `RISK_CEILING_EXCEEDED`,
`RESERVED_ACTION` and `UNCLASSIFIED_HIGH_RISK` are readable from the decision
alone — they are the reasons the chain failed to stop somewhere. The rest are
not: nothing in an authority decision knows that this is the third failed
attempt, or that a reviewer and a manager disagree. Those arrive in
`ExceptionContext`, which the caller fills from the engineering job, the
review and the gate verdict it already has.

The split is deliberate. A classifier that went looking for its own evidence
would be a second control plane with its own opinion about what happened.

## `VACANT_AUTHORITY` is our own finding

It is not in the brief. It exists because the canonical registry fills three of
the eleven employee rows with an `active` employee and the master plan describes
seats — a CFO, an engineering manager — that no row fills at all. A request
that escalates only because the seat that should have taken it does not exist is
a different management problem from one that escalates because it was genuinely
too big, and merging the two would hide the org gap behind a budget number.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ai_platform.resource_classes import Risk

from .actions import RESERVED_AS, ActionType
from .authority import AuthorityDecision, Decision, Insufficiency
from .common import assert_prose, text_tuple
from .errors import DelegationError


class ExceptionClass(str, Enum):
    """Every condition under which the CEO hears about something."""

    AUTHORITY_EXCEEDED = "authority_exceeded"
    BUDGET_CEILING_EXCEEDED = "budget_ceiling_exceeded"
    RISK_CEILING_EXCEEDED = "risk_ceiling_exceeded"
    RESERVED_ACTION = "reserved_action"
    POLICY_CONFLICT = "policy_conflict"
    STRATEGIC_CONFLICT = "strategic_conflict"
    REPEATED_EXECUTION_FAILURE = "repeated_execution_failure"
    UNRESOLVED_DISPUTE = "unresolved_dispute"
    SECURITY_OR_GOVERNANCE_EVENT = "security_or_governance_event"
    MAJOR_ARCHITECTURE_DECISION = "major_architecture_decision"
    UNCLASSIFIED_HIGH_RISK = "unclassified_high_risk"
    ENVELOPE_BREACH = "envelope_breach"
    VACANT_AUTHORITY = "vacant_authority"


# How loudly each class asks for attention. Used only for ordering a report;
# nothing here changes whether an exception is raised.
SEVERITY: dict[ExceptionClass, int] = {
    ExceptionClass.SECURITY_OR_GOVERNANCE_EVENT: 0,
    ExceptionClass.RESERVED_ACTION: 1,
    ExceptionClass.MAJOR_ARCHITECTURE_DECISION: 2,
    ExceptionClass.POLICY_CONFLICT: 3,
    ExceptionClass.STRATEGIC_CONFLICT: 4,
    ExceptionClass.AUTHORITY_EXCEEDED: 5,
    ExceptionClass.BUDGET_CEILING_EXCEEDED: 6,
    ExceptionClass.RISK_CEILING_EXCEEDED: 7,
    ExceptionClass.ENVELOPE_BREACH: 8,
    ExceptionClass.UNRESOLVED_DISPUTE: 9,
    ExceptionClass.REPEATED_EXECUTION_FAILURE: 10,
    ExceptionClass.UNCLASSIFIED_HIGH_RISK: 11,
    ExceptionClass.VACANT_AUTHORITY: 12,
}

# The actions whose approval is a major architecture decision in its own right,
# whatever the recorded risk. Architecture is the one dimension where a small
# diff and a large consequence routinely coincide.
ARCHITECTURE_ACTIONS: frozenset[ActionType] = frozenset(
    {
        ActionType.APPROVE_ARCHITECTURE_REDESIGN,
        ActionType.CHANGE_PRIMARY_ENGINE,
        ActionType.APPROVE_NEW_DEPENDENCY,
    }
)

GOVERNANCE_ACTIONS: frozenset[ActionType] = frozenset(
    {
        ActionType.AMEND_CONSTITUTION,
        ActionType.CHANGE_GOVERNANCE_POLICY,
        ActionType.CHANGE_DELEGATION_POLICY,
        ActionType.CHANGE_NO_SUBAGENTS_POLICY,
        ActionType.EXPAND_AUTHORITY,
        ActionType.APPROVE_SECURITY_EXCEPTION,
    }
)


@dataclass(frozen=True)
class ExceptionContext:
    """What the caller knows that an authority decision cannot.

    Every field defaults to the quiet value, so a caller with nothing to add
    passes nothing and gets exactly the exceptions the decision itself implies.
    """

    failed_attempts: int = 0
    attempt_ceiling: int = 0
    reviewer_disputed: bool = False
    dispute_detail: str = ""
    envelope_violations: tuple[str, ...] = ()
    policy_conflicts: tuple[str, ...] = ()
    strategic_conflicts: tuple[str, ...] = ()
    security_events: tuple[str, ...] = ()
    protected_surface_changed: bool = False

    def __post_init__(self) -> None:
        for name in ("failed_attempts", "attempt_ceiling"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise DelegationError(f"context.{name} must be a non-negative integer")
        for name in (
            "envelope_violations",
            "policy_conflicts",
            "strategic_conflicts",
            "security_events",
        ):
            object.__setattr__(
                self, name, text_tuple(getattr(self, name), f"context.{name}")
            )
        for name in ("reviewer_disputed", "protected_surface_changed"):
            if not isinstance(getattr(self, name), bool):
                raise DelegationError(f"context.{name} must be a boolean")
        if self.dispute_detail:
            object.__setattr__(
                self,
                "dispute_detail",
                assert_prose(self.dispute_detail, "context.dispute_detail"),
            )
        if self.reviewer_disputed and not self.dispute_detail:
            raise DelegationError(
                "a dispute with no detail cannot be settled by whoever it reaches; "
                "say what the reviewer and the manager disagree about"
            )

    @property
    def attempts_exhausted(self) -> bool:
        return bool(self.attempt_ceiling) and self.failed_attempts >= self.attempt_ceiling


@dataclass(frozen=True)
class ManagementException:
    """One reason this reached the CEO, with the evidence for it."""

    exception_class: ExceptionClass
    detail: str
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.exception_class, ExceptionClass):
            raise DelegationError("exception_class must be an ExceptionClass value")
        object.__setattr__(self, "detail", assert_prose(self.detail, "exception.detail"))
        object.__setattr__(
            self, "evidence_refs", text_tuple(self.evidence_refs, "exception.evidence_refs")
        )

    @property
    def severity(self) -> int:
        return SEVERITY[self.exception_class]

    def to_dict(self) -> dict[str, Any]:
        return {
            "exception_class": self.exception_class.value,
            "detail": self.detail,
            "evidence_refs": list(self.evidence_refs),
            "severity": self.severity,
        }


@dataclass(frozen=True)
class ExceptionReport:
    """Every exception one decision raised, worst first. Empty is the good case."""

    request_id: str
    exceptions: tuple[ManagementException, ...] = field(default_factory=tuple)

    @property
    def ceo_required(self) -> bool:
        return bool(self.exceptions)

    @property
    def classes(self) -> tuple[ExceptionClass, ...]:
        return tuple(item.exception_class for item in self.exceptions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "ceo_required": self.ceo_required,
            "exceptions": [item.to_dict() for item in self.exceptions],
        }


_INSUFFICIENCY_CLASS: dict[Insufficiency, ExceptionClass] = {
    Insufficiency.RISK_ABOVE_CEILING: ExceptionClass.RISK_CEILING_EXCEEDED,
    Insufficiency.BUDGET_ABOVE_CEILING: ExceptionClass.BUDGET_CEILING_EXCEEDED,
    Insufficiency.BUDGET_UNKNOWN: ExceptionClass.BUDGET_CEILING_EXCEEDED,
    Insufficiency.RESERVED_ACTION: ExceptionClass.RESERVED_ACTION,
    Insufficiency.SEAT_VACANT: ExceptionClass.VACANT_AUTHORITY,
    Insufficiency.SEAT_DORMANT: ExceptionClass.VACANT_AUTHORITY,
    Insufficiency.SEAT_RESTRICTED: ExceptionClass.VACANT_AUTHORITY,
    Insufficiency.AUTONOMY_TOO_LOW: ExceptionClass.AUTHORITY_EXCEEDED,
    Insufficiency.OUT_OF_SCOPE: ExceptionClass.AUTHORITY_EXCEEDED,
    Insufficiency.WRONG_DEPARTMENT: ExceptionClass.AUTHORITY_EXCEEDED,
}


def classify(
    decision: AuthorityDecision,
    context: ExceptionContext | None = None,
    *,
    evidence_refs: Sequence[str] = (),
) -> ExceptionReport:
    """Every exception class this decision and its context raise, worst first."""
    if not isinstance(decision, AuthorityDecision):
        raise DelegationError("classify takes an AuthorityDecision")
    ctx = context or ExceptionContext()
    if not isinstance(ctx, ExceptionContext):
        raise DelegationError("classify takes an ExceptionContext or None")
    refs = tuple(evidence_refs)
    found: list[ManagementException] = []

    def add(kind: ExceptionClass, detail: str, own: Sequence[str] = ()) -> None:
        found.append(
            ManagementException(
                exception_class=kind,
                detail=detail,
                evidence_refs=tuple(own) + refs,
            )
        )

    # -- from the decision itself -----------------------------------------
    if decision.action in GOVERNANCE_ACTIONS:
        add(
            ExceptionClass.SECURITY_OR_GOVERNANCE_EVENT,
            f"{decision.action.value} touches the governance surface every other "
            "limit is measured against",
        )
    if decision.reserved_as or decision.action in RESERVED_AS:
        add(
            ExceptionClass.RESERVED_ACTION,
            decision.reason,
            ("company/permissions.yaml",),
        )
    elif decision.action in GOVERNANCE_ACTIONS and decision.ceo_required:
        add(ExceptionClass.RESERVED_ACTION, decision.reason)
    if decision.action in ARCHITECTURE_ACTIONS:
        add(
            ExceptionClass.MAJOR_ARCHITECTURE_DECISION,
            f"{decision.action.value} is an architecture decision whatever its diff",
        )
    if decision.action is ActionType.UNCLASSIFIED:
        add(
            ExceptionClass.UNCLASSIFIED_HIGH_RISK,
            "the action carries no classification, so its risk is unmeasured rather "
            "than low",
        )
    elif decision.risk in (Risk.HIGH, Risk.CRITICAL) and decision.ceo_required:
        add(
            ExceptionClass.RISK_CEILING_EXCEEDED,
            f"{decision.risk.value} risk exceeded every delegated ceiling in the chain",
        )

    if decision.escalation_required and decision.chain:
        blocking = decision.chain[-1]
        mapped = _INSUFFICIENCY_CLASS.get(blocking.insufficiency)
        if mapped is not None:
            add(mapped, f"{blocking.seat}: {blocking.detail}")
    if decision.decision is Decision.REJECTED:
        add(
            ExceptionClass.AUTHORITY_EXCEEDED,
            decision.reason,
        )
    if decision.budget is not None and not decision.budget.within:
        add(ExceptionClass.BUDGET_CEILING_EXCEEDED, decision.budget.reason)

    # -- from the context the caller supplied -----------------------------
    if ctx.attempts_exhausted:
        add(
            ExceptionClass.REPEATED_EXECUTION_FAILURE,
            f"{ctx.failed_attempts} of {ctx.attempt_ceiling} developer attempts are "
            "spent; a further correction needs a new work order",
        )
    if ctx.reviewer_disputed:
        add(ExceptionClass.UNRESOLVED_DISPUTE, ctx.dispute_detail)
    for item in ctx.envelope_violations:
        add(ExceptionClass.ENVELOPE_BREACH, item)
    for item in ctx.policy_conflicts:
        add(ExceptionClass.POLICY_CONFLICT, item)
    for item in ctx.strategic_conflicts:
        add(ExceptionClass.STRATEGIC_CONFLICT, item)
    for item in ctx.security_events:
        add(ExceptionClass.SECURITY_OR_GOVERNANCE_EVENT, item)
    if ctx.protected_surface_changed:
        add(
            ExceptionClass.SECURITY_OR_GOVERNANCE_EVENT,
            "the protected governance surface changed while the work was in flight",
        )

    # De-duplicate by (class, detail) and order worst first, then alphabetically
    # so two runs over the same inputs produce the same report.
    unique: dict[tuple[str, str], ManagementException] = {}
    for item in found:
        unique.setdefault((item.exception_class.value, item.detail), item)
    ordered = tuple(
        sorted(
            unique.values(),
            key=lambda item: (item.severity, item.exception_class.value, item.detail),
        )
    )
    return ExceptionReport(request_id=decision.request_id, exceptions=ordered)


__all__ = [
    "ARCHITECTURE_ACTIONS",
    "GOVERNANCE_ACTIONS",
    "SEVERITY",
    "ExceptionClass",
    "ExceptionContext",
    "ExceptionReport",
    "ManagementException",
    "classify",
]

"""What the CEO should see instead of approvals: counts, and why.

The previous phase produced one brief per objective. This produces the number
that decides whether delegation is working at all — **how much stayed below the
CEO** — and, for the part that did not, the named reason.

## Three counts that are not the same count

`ceo_decisions_required` — the model could find no seat below the CEO. The CEO
has to *decide*.

`ceo_notifications` — a seat below the CEO decided it, and something about it
still raises a management exception. The CEO has to *know*, and nothing waits
on them. A repeatedly-failing work order that a manager is still authorized to
correct is the example: the correction proceeds, and the CEO hears that it is
the third one.

`ceo_attention` — the union. This is the number to watch over time, because a
delegation model can flatter itself by moving work from the first bucket into
the second.

Keeping them apart is the whole point. Collapsing them would let "CEO
escalations: 0" be true while the CEO is reading forty notifications.

## Why the reasons are counted per class and not summarised

`reasons` is a count per `ExceptionClass`, in severity order. A CEO looking at
"CEO escalations: 6" needs to know whether that is six budget breaches or six
separation-of-duty failures, because those are different companies. A single
number with a prose summary would be the version of this that nobody can act
on.

## Why this module computes nothing about quality

It counts decisions and exceptions. It does not score the company, rank
departments, or emit a health number — `company/dashboard/integrity.py` refuses
the same class of field by name (`FORBIDDEN_AGGREGATE_FIELDS`), for the reason
that an aggregate verdict is the fastest way to stop reading the evidence.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from company.finance.money import Money, total

from .authority import AuthorityDecision, Decision
from .exceptions import SEVERITY, ExceptionClass, ExceptionReport
from .errors import DelegationError


@dataclass(frozen=True)
class DecisionOutcome:
    """One decision paired with the exceptions it raised."""

    decision: AuthorityDecision
    exceptions: ExceptionReport

    def __post_init__(self) -> None:
        if not isinstance(self.decision, AuthorityDecision):
            raise DelegationError("outcome.decision must be an AuthorityDecision")
        if not isinstance(self.exceptions, ExceptionReport):
            raise DelegationError("outcome.exceptions must be an ExceptionReport")
        if self.decision.request_id != self.exceptions.request_id:
            raise DelegationError(
                f"the decision is for {self.decision.request_id} and the exception "
                f"report is for {self.exceptions.request_id}"
            )

    @property
    def resolved_internally(self) -> bool:
        """Decided below the CEO, whatever the CEO was later told about it."""
        return not self.decision.ceo_required

    @property
    def notifies_ceo(self) -> bool:
        """Resolved below the CEO, and still something the CEO should know."""
        return self.resolved_internally and bool(self.exceptions.exceptions)


@dataclass(frozen=True)
class ManagementMetrics:
    """The management-by-exception picture over one set of decisions."""

    total_decisions: int
    resolved_internally: int
    ceo_decisions_required: int
    ceo_notifications: int
    approved: int
    rejected: int
    escalated: int
    by_seat: tuple[tuple[str, int], ...]
    reasons: tuple[tuple[str, int], ...]
    spend: Money | None = None
    budget: Money | None = None

    @property
    def ceo_attention(self) -> int:
        return self.ceo_decisions_required + self.ceo_notifications

    @property
    def internal_share(self) -> str:
        """Resolved-below-CEO as `n/total`. Not a percentage, and not a score."""
        return f"{self.resolved_internally}/{self.total_decisions}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_decisions": self.total_decisions,
            "resolved_internally": self.resolved_internally,
            "ceo_decisions_required": self.ceo_decisions_required,
            "ceo_notifications": self.ceo_notifications,
            "ceo_attention": self.ceo_attention,
            "approved": self.approved,
            "rejected": self.rejected,
            "escalated": self.escalated,
            "by_seat": [list(item) for item in self.by_seat],
            "reasons": [list(item) for item in self.reasons],
            "spend": self.spend.to_dict() if self.spend else None,
            "budget": self.budget.to_dict() if self.budget else None,
        }

    def render(self) -> str:
        lines = [
            "MANAGEMENT BY EXCEPTION",
            f"  total decisions          {self.total_decisions}",
            f"  resolved internally      {self.internal_share}",
            f"  CEO decisions required   {self.ceo_decisions_required}",
            f"  CEO notifications        {self.ceo_notifications}",
            f"  CEO attention (total)    {self.ceo_attention}",
            "",
            f"  approved {self.approved}   rejected {self.rejected}   "
            f"escalated {self.escalated}",
        ]
        if self.by_seat:
            lines += ["", "APPROVING SEATS"]
            lines += [f"  {seat:<24} {count}" for seat, count in self.by_seat]
        lines += ["", "ESCALATION REASONS"]
        if not self.reasons:
            lines.append("  none")
        else:
            lines += [f"  {name:<30} {count}" for name, count in self.reasons]
        if self.spend is not None or self.budget is not None:
            spent = str(self.spend) if self.spend is not None else "unknown"
            against = f" / {self.budget}" if self.budget is not None else ""
            lines += ["", "RESOURCE SPEND", f"  {spent}{against}"]
        return "\n".join(lines)


def measure(
    outcomes: Sequence[DecisionOutcome],
    *,
    spend: Money | None = None,
    budget: Money | None = None,
) -> ManagementMetrics:
    """Count one set of decisions. Pure, and the same every time."""
    items = list(outcomes)
    for item in items:
        if not isinstance(item, DecisionOutcome):
            raise DelegationError("measure takes DecisionOutcome values")

    seats: dict[str, int] = {}
    reasons: dict[ExceptionClass, int] = {}
    for item in items:
        if item.decision.decision is Decision.APPROVED:
            seats[item.decision.actor] = seats.get(item.decision.actor, 0) + 1
        for kind in item.exceptions.classes:
            reasons[kind] = reasons.get(kind, 0) + 1

    return ManagementMetrics(
        total_decisions=len(items),
        resolved_internally=sum(1 for item in items if item.resolved_internally),
        ceo_decisions_required=sum(
            1 for item in items if item.decision.ceo_required
        ),
        ceo_notifications=sum(1 for item in items if item.notifies_ceo),
        approved=sum(
            1 for item in items if item.decision.decision is Decision.APPROVED
        ),
        rejected=sum(
            1 for item in items if item.decision.decision is Decision.REJECTED
        ),
        escalated=sum(
            1 for item in items if item.decision.decision is Decision.ESCALATE
        ),
        by_seat=tuple(sorted(seats.items(), key=lambda kv: (-kv[1], kv[0]))),
        reasons=tuple(
            (kind.value, count)
            for kind, count in sorted(
                reasons.items(), key=lambda kv: (SEVERITY[kv[0]], kv[0].value)
            )
        ),
        spend=spend,
        budget=budget,
    )


def spend_of(outcomes: Sequence[DecisionOutcome], currency: str) -> Money | None:
    """Total of every amount the decisions carried, or None if any is missing.

    An unmeasured cost makes the total unknown rather than smaller — the rule
    `company/finance/economics.py` applies to a margin, applied to a portfolio.
    """
    amounts = []
    for item in outcomes:
        found = item.decision.budget
        if found is None or found.requested is None:
            continue
        amounts.append(found.requested)
    if not amounts:
        return None
    return total(amounts, currency)


@dataclass(frozen=True)
class ManagementReport:
    """One programme, as the CEO should receive it: outcomes, then exceptions."""

    programme: str
    metrics: ManagementMetrics
    outcomes: tuple[str, ...] = ()
    next_action: str = ""
    control_metrics: ManagementMetrics | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "programme": self.programme,
            "metrics": self.metrics.to_dict(),
            "outcomes": list(self.outcomes),
            "next_action": self.next_action,
            "control_metrics": (
                self.control_metrics.to_dict() if self.control_metrics else None
            ),
        }

    def render(self) -> str:
        lines = ["OBJECTIVE / PROGRAM", f"  {self.programme}", ""]
        lines.append(self.metrics.render())
        if self.outcomes:
            lines += ["", "OUTCOMES"]
            lines += [f"  - {item}" for item in self.outcomes]
        if self.next_action:
            lines += ["", "NEXT ACTION", f"  {self.next_action}"]
        if self.control_metrics is not None:
            lines += [
                "",
                "CONTROL PROBES (counterfactual, never run)",
                f"  {self.control_metrics.total_decisions} probes, "
                f"{self.control_metrics.ceo_decisions_required} correctly required "
                "the CEO",
                "  Reported so that a clean programme cannot be mistaken for a model",
                "  that approves everything.",
            ]
        return "\n".join(lines)


__all__ = [
    "DecisionOutcome",
    "ManagementMetrics",
    "ManagementReport",
    "measure",
    "spend_of",
]

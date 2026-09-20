"""The one page the CEO reads when a bounded objective ends.

In shadow mode the CEO saw every decision, so a report was a summary of things
they already knew. In bounded routine engineering they saw none of them, so
this page is the *only* account of what happened and has to stand on its own.

Three rules follow from that:

1. **It always exists.** Every terminal state produces one, including the
   uninteresting ones. An objective that quietly found nothing to do still owes
   the CEO a page saying so.
2. **It says what it cost.** Planning, developer, review and correction, each
   separately, against the authorized budget. A run whose cost is unreported is
   a run the company cannot budget from.
3. **`CEO ACTION REQUIRED` is computed, not written.** It comes from the
   objective's terminal state and the exception classes that fired, so a report
   cannot claim nothing is needed while an exception is outstanding.

The last one is the one that matters. A report where the author chooses the
headline is a report that will eventually be optimistic.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
import datetime as dt
from typing import Any

from company.finance.money import Money

from .common import assert_prose, assert_record_id, text_tuple
from .errors import DelegationError
from .exceptions import ExceptionClass
from .objective_lifecycle import (
    TERMINAL,
    TERMINAL_WITHOUT_CEO,
    ObjectiveHistory,
    ObjectiveState,
)


REPORT_VERSION = "objective_report_v1"

#: What the CEO is told to do, per terminal state, when no exception fired.
_ACTION_BY_STATE: dict[ObjectiveState, str] = {
    ObjectiveState.COMPLETED: "NONE",
    ObjectiveState.NO_EXECUTABLE_WORK: (
        "NONE. The company found nothing it could start. Read the follow-up "
        "candidates when convenient; nothing is waiting on you."
    ),
    ObjectiveState.EXPIRED: (
        "NONE unless you want this objective continued, which needs a new "
        "contract."
    ),
    ObjectiveState.BLOCKED: "Decide whether to unblock this objective or close it.",
    ObjectiveState.ESCALATED: "A decision is required before this can continue.",
    ObjectiveState.FAILED: (
        "Decide whether to retry this objective, change it, or close it."
    ),
}


@dataclass(frozen=True)
class CostBreakdown:
    """Where the money went. Every field is a real recorded session cost."""

    currency: str = "USD"
    planning: Money | None = None
    developer: Money | None = None
    review: Money | None = None
    correction: Money | None = None

    def _parts(self) -> tuple[tuple[str, Money | None], ...]:
        return (
            ("planning", self.planning),
            ("developer", self.developer),
            ("review", self.review),
            ("correction", self.correction),
        )

    def total(self) -> Money:
        total = Money("0", self.currency)
        for _, amount in self._parts():
            if amount is not None:
                total = total + amount
        return total

    def remaining(self, budget: Money) -> Money:
        return budget - self.total()

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"currency": self.currency}
        for name, amount in self._parts():
            out[name] = amount.to_dict() if amount is not None else None
        out["total"] = self.total().to_dict()
        return out


@dataclass(frozen=True)
class ManagementDecision:
    """One decision taken below the CEO, and who took it."""

    action: str
    decided_by_seat: str
    decision: str
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "decided_by_seat": self.decided_by_seat,
            "decision": self.decision,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class ObjectiveOutcomeReport:
    """One objective, finished, as the CEO sees it."""

    objective_id: str
    objective: str
    contract_id: str
    history: ObjectiveHistory
    budget: Money
    costs: CostBreakdown
    started_on: dt.date
    finished_on: dt.date
    success_criteria: tuple[str, ...] = ()
    criteria_met: tuple[str, ...] = ()
    work_selected: str = ""
    selection_reason: str = ""
    work_completed: str = ""
    internal_integration: str = ""
    management_decisions: tuple[ManagementDecision, ...] = ()
    exceptions: tuple[ExceptionClass, ...] = ()
    follow_up_candidates: tuple[str, ...] = ()
    notes: str = ""
    version: str = REPORT_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "objective_id", assert_record_id(self.objective_id, "objective_id")
        )
        object.__setattr__(
            self, "contract_id", assert_record_id(self.contract_id, "contract_id")
        )
        object.__setattr__(self, "objective", assert_prose(self.objective, "objective"))
        if not isinstance(self.history, ObjectiveHistory):
            raise DelegationError("report.history must be an ObjectiveHistory")
        if self.history.objective_id != self.objective_id:
            raise DelegationError(
                f"the history is for {self.history.objective_id} and the report is "
                f"for {self.objective_id}"
            )
        if self.history.state not in TERMINAL:
            raise DelegationError(
                f"{self.objective_id} is {self.history.state.value} and has not "
                "finished. A report is what an objective produces when it ends; "
                "there is no interim edition."
            )
        if not isinstance(self.budget, Money):
            raise DelegationError("report.budget must be Money")
        if not isinstance(self.costs, CostBreakdown):
            raise DelegationError("report.costs must be a CostBreakdown")
        for name in ("success_criteria", "criteria_met", "follow_up_candidates"):
            object.__setattr__(
                self, name, text_tuple(getattr(self, name), name, limit=32)
            )
        object.__setattr__(
            self,
            "exceptions",
            tuple(
                sorted(
                    {
                        item
                        if isinstance(item, ExceptionClass)
                        else ExceptionClass(str(item))
                        for item in self.exceptions
                    },
                    key=lambda item: item.value,
                )
            ),
        )

    # --- the computed headline ---------------------------------------------

    @property
    def outcome(self) -> ObjectiveState:
        return self.history.state

    @property
    def over_budget(self) -> bool:
        return self.costs.total() > self.budget

    def ceo_action_required(self) -> str:
        """Derived from the terminal state and the exceptions, never written."""
        if self.exceptions:
            named = ", ".join(item.value for item in self.exceptions)
            return f"Yes - {len(self.exceptions)} exception(s) fired: {named}."
        if self.over_budget:
            return (
                "Yes - the objective spent more than its authorized budget "
                f"({self.costs.total().amount} of {self.budget.amount})."
            )
        if self.outcome in TERMINAL_WITHOUT_CEO:
            return _ACTION_BY_STATE.get(self.outcome, "NONE")
        return _ACTION_BY_STATE.get(
            self.outcome, "A decision is required before this can continue."
        )

    def interrupted_the_ceo(self) -> bool:
        """Whether a person had to be pulled in before the objective ended."""
        return bool(self.exceptions) or self.history.needed_the_ceo()

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective_id": self.objective_id,
            "objective": self.objective,
            "contract_id": self.contract_id,
            "outcome": self.outcome.value,
            "success_criteria": list(self.success_criteria),
            "criteria_met": list(self.criteria_met),
            "work_selected": self.work_selected,
            "selection_reason": self.selection_reason,
            "work_completed": self.work_completed,
            "internal_integration": self.internal_integration,
            "management_decisions": [
                item.to_dict() for item in self.management_decisions
            ],
            "exceptions": [item.value for item in self.exceptions],
            "costs": self.costs.to_dict(),
            "budget": self.budget.to_dict(),
            "remaining": self.costs.remaining(self.budget).to_dict(),
            "over_budget": self.over_budget,
            "started_on": self.started_on.isoformat(),
            "finished_on": self.finished_on.isoformat(),
            "elapsed_days": (self.finished_on - self.started_on).days,
            "follow_up_candidates": list(self.follow_up_candidates),
            "ceo_action_required": self.ceo_action_required(),
            "interrupted_the_ceo": self.interrupted_the_ceo(),
            "history": self.history.to_dict(),
            "notes": self.notes,
            "version": self.version,
        }

    def render(self) -> str:
        """The page itself, in the shape the CEO asked for."""
        costs = self.costs
        lines = [
            f"OBJECTIVE            {self.objective}",
            f"OUTCOME              {self.outcome.value}",
            "",
            "SUCCESS METRICS",
        ]
        if self.success_criteria:
            met = set(self.criteria_met)
            for item in self.success_criteria:
                lines.append(f"  [{'x' if item in met else ' '}] {item}")
        else:
            lines.append("  none stated")
        lines += [
            "",
            f"WORK SELECTED        {self.work_selected or '-'}",
            f"WHY                  {self.selection_reason or '-'}",
            f"WORK COMPLETED       {self.work_completed or '-'}",
            f"INTERNAL INTEGRATION {self.internal_integration or 'none'}",
            "",
            "MANAGEMENT DECISIONS",
        ]
        if self.management_decisions:
            for item in self.management_decisions:
                lines.append(
                    f"  {item.action:<28} {item.decision:<10} by {item.decided_by_seat}"
                )
        else:
            lines.append("  none")
        lines += ["", "EXCEPTIONS"]
        if self.exceptions:
            for item in self.exceptions:
                lines.append(f"  {item.value}")
        else:
            lines.append("  none")
        lines += ["", "MODEL COST"]
        for name, amount in costs._parts():
            shown = f"{amount.amount} {amount.currency}" if amount else "0"
            lines.append(f"  {name:<12} {shown}")
        total = costs.total()
        lines.append(
            f"  {'total':<12} {total.amount} of {self.budget.amount} "
            f"{self.budget.currency}"
        )
        lines += [
            "",
            f"TIME                 {self.started_on.isoformat()} to "
            f"{self.finished_on.isoformat()} "
            f"({(self.finished_on - self.started_on).days} day(s))",
            "",
            "FOLLOW-UP CANDIDATES",
        ]
        if self.follow_up_candidates:
            for item in self.follow_up_candidates:
                lines.append(f"  {item}")
        else:
            lines.append("  none")
        lines += ["", f"CEO ACTION REQUIRED  {self.ceo_action_required()}"]
        return "\n".join(lines)


def build_report(
    *,
    objective_id: str,
    objective: str,
    contract_id: str,
    history: ObjectiveHistory,
    budget: Money,
    costs: CostBreakdown,
    started_on: dt.date,
    finished_on: dt.date,
    exceptions: Sequence[ExceptionClass] = (),
    **kwargs: Any,
) -> ObjectiveOutcomeReport:
    """Assemble the report. A thin helper, kept so callers read as prose."""
    return ObjectiveOutcomeReport(
        objective_id=objective_id,
        objective=objective,
        contract_id=contract_id,
        history=history,
        budget=budget,
        costs=costs,
        started_on=started_on,
        finished_on=finished_on,
        exceptions=tuple(exceptions),
        **kwargs,
    )


__all__ = [
    "REPORT_VERSION",
    "CostBreakdown",
    "ManagementDecision",
    "ObjectiveOutcomeReport",
    "build_report",
]

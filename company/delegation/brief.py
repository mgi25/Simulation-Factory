"""The CEO view: outcomes and exceptions, with the approvals left out.

The brief the CEO should get is a result, a cost, a count of what was handled
without them, and a list of what was not. This module builds exactly that from
records that already exist, and deliberately builds nothing else.

## Why this is not a dashboard

`company/dashboard/` already renders the executive view, and the integration
gate has a required condition — `executive.dashboard_cannot_approve` — asserting
that the view is a view. Rebuilding that here would create a second executive
surface with its own idea of what the company is doing, and the first thing
such a pair does is disagree.

So `ExecutiveBrief` is a model, not a renderer of record. It carries the fields
the phase brief asks for, converts to a mapping, and renders plain text for a
terminal. Wiring it into `company/dashboard/` is an integration step for a
later phase, when delegated approvals are real and the counts mean something
operational rather than advisory.

## Why `decisions_handled_internally` excludes escalations that stopped early

An action that went from a developer to an engineering manager and stopped
there was handled internally: the CEO never saw it, which is the point. An
action that reached the CEO seat was not, even though every seat below behaved
correctly. The count is of decisions that stayed below the CEO, and
`AuthorityDecision.handled_internally` is where that definition lives so the
brief and the tests cannot drift apart about it.

## Why the cost line can say "unknown"

`company/finance` refuses to report an unmeasured cost as zero, and the
integration gate probes that by name. A brief that printed `$0.00 / $50` for a
period with no recorded usage would be the same lie in a friendlier font, so
`spend` is `Money | None` and renders as `unknown` when nothing was recorded.
"""

from __future__ import annotations

from collections.abc import Sequence
import datetime as dt
from dataclasses import dataclass
from typing import Any

from company.finance.money import Money, total

from .authority import AuthorityDecision
from .common import assert_prose, assert_record_id, text_tuple
from .exceptions import ExceptionReport, ManagementException
from .errors import DelegationError
from .objectives import Objective, PlanningEnvelope
from .record import ExecutiveDecisionRecord


@dataclass(frozen=True)
class ExecutiveBrief:
    """One objective, as the CEO should receive it."""

    objective_id: str
    objective: str
    status: str
    work_completed: tuple[str, ...] = ()
    best_result: str = ""
    spend: Money | None = None
    budget: Money | None = None
    decisions_handled_internally: int = 0
    ceo_escalations: tuple[ManagementException, ...] = ()
    next_action: str = ""
    as_of: dt.date | None = None
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "objective_id", assert_record_id(self.objective_id, "brief.objective_id")
        )
        object.__setattr__(
            self, "objective", assert_prose(self.objective, "brief.objective")
        )
        object.__setattr__(self, "status", assert_prose(self.status, "brief.status"))
        object.__setattr__(
            self, "work_completed", text_tuple(self.work_completed, "brief.work_completed")
        )
        if self.best_result:
            object.__setattr__(
                self, "best_result", assert_prose(self.best_result, "brief.best_result")
            )
        for name in ("spend", "budget"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, Money):
                raise DelegationError(f"brief.{name} must be Money or None")
        if (
            isinstance(self.decisions_handled_internally, bool)
            or not isinstance(self.decisions_handled_internally, int)
            or self.decisions_handled_internally < 0
        ):
            raise DelegationError(
                "brief.decisions_handled_internally must be a non-negative integer"
            )
        if not isinstance(self.ceo_escalations, tuple):
            raise DelegationError("brief.ceo_escalations must be a tuple")
        for item in self.ceo_escalations:
            if not isinstance(item, ManagementException):
                raise DelegationError(
                    "every escalation must be a ManagementException"
                )
        if self.next_action:
            object.__setattr__(
                self, "next_action", assert_prose(self.next_action, "brief.next_action")
            )
        object.__setattr__(
            self, "evidence_refs", text_tuple(self.evidence_refs, "brief.evidence_refs")
        )

    @property
    def spend_line(self) -> str:
        """The cost line, with `unknown` rather than a zero nobody measured."""
        if self.spend is None:
            budget = f" / {self.budget}" if self.budget else ""
            return f"unknown{budget}"
        if self.budget is None:
            return f"{self.spend} / no recorded budget"
        return f"{self.spend} / {self.budget}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective_id": self.objective_id,
            "objective": self.objective,
            "status": self.status,
            "work_completed": list(self.work_completed),
            "best_result": self.best_result,
            "spend": self.spend.to_dict() if self.spend else None,
            "budget": self.budget.to_dict() if self.budget else None,
            "spend_line": self.spend_line,
            "decisions_handled_internally": self.decisions_handled_internally,
            "ceo_escalations": [item.to_dict() for item in self.ceo_escalations],
            "next_action": self.next_action,
            "as_of": self.as_of.isoformat() if self.as_of else None,
            "evidence_refs": list(self.evidence_refs),
        }

    def render(self) -> str:
        """Plain text, in the shape the phase brief asks for."""
        lines = [
            "OBJECTIVE",
            f"  {self.objective}",
            "",
            "STATUS",
            f"  {self.status}",
        ]
        if self.work_completed:
            lines += ["", "WORK COMPLETED"]
            lines += [f"  - {item}" for item in self.work_completed]
        if self.best_result:
            lines += ["", "BEST RESULT", f"  {self.best_result}"]
        lines += ["", "AI COST", f"  {self.spend_line}"]
        lines += [
            "",
            "EXECUTIVE DECISIONS",
            f"  {self.decisions_handled_internally} handled internally",
            "",
            "CEO ESCALATIONS",
        ]
        if not self.ceo_escalations:
            lines.append("  0")
        else:
            lines += [
                f"  - [{item.exception_class.value}] {item.detail}"
                for item in self.ceo_escalations
            ]
        if self.next_action:
            lines += ["", "NEXT ACTION", f"  {self.next_action}"]
        return "\n".join(lines)


def build_brief(
    objective: Objective,
    *,
    status: str,
    decisions: Sequence[AuthorityDecision] = (),
    reports: Sequence[ExceptionReport] = (),
    work_completed: Sequence[str] = (),
    best_result: str = "",
    spend: Money | None = None,
    envelope: PlanningEnvelope | None = None,
    next_action: str = "",
    as_of: dt.date | None = None,
    evidence_refs: Sequence[str] = (),
) -> ExecutiveBrief:
    """Assemble the brief from decisions and exception reports already produced.

    Nothing is fetched here. The caller supplies what it already has, which
    keeps the brief a pure function of its inputs and stops it from becoming a
    second place that knows how to read the company.
    """
    if not isinstance(objective, Objective):
        raise DelegationError("build_brief takes an Objective")
    internal = sum(1 for item in decisions if item.handled_internally)
    escalations: list[ManagementException] = []
    for report in reports:
        if not isinstance(report, ExceptionReport):
            raise DelegationError("every report must be an ExceptionReport")
        escalations.extend(report.exceptions)
    escalations.sort(key=lambda item: (item.severity, item.exception_class.value))
    budget = envelope.budget if envelope is not None else (
        objective.envelope.budget if objective.envelope else None
    )
    return ExecutiveBrief(
        objective_id=objective.objective_id,
        objective=objective.title,
        status=status,
        work_completed=tuple(work_completed),
        best_result=best_result,
        spend=spend,
        budget=budget,
        decisions_handled_internally=internal,
        ceo_escalations=tuple(escalations),
        next_action=next_action,
        as_of=as_of,
        evidence_refs=tuple(evidence_refs),
    )


def brief_from_records(
    objective: Objective,
    records: Sequence[ExecutiveDecisionRecord],
    *,
    status: str,
    spend: Money | None = None,
    next_action: str = "",
    as_of: dt.date | None = None,
) -> ExecutiveBrief:
    """The same brief, rebuilt from a stored history rather than a live run."""
    internal = sum(1 for item in records if not item.ceo_required)
    escalations = tuple(
        ManagementException(
            exception_class_from(name),
            detail=f"{item.decision_id}: {item.reason}",
            evidence_refs=item.evidence_refs,
        )
        for item in records
        for name in item.exception_classes
    )
    budget = objective.envelope.budget if objective.envelope else None
    return ExecutiveBrief(
        objective_id=objective.objective_id,
        objective=objective.title,
        status=status,
        work_completed=(),
        spend=spend,
        budget=budget,
        decisions_handled_internally=internal,
        ceo_escalations=escalations,
        next_action=next_action,
        as_of=as_of,
    )


def exception_class_from(name: str):
    """Decode a stored exception-class name, refusing one that is not a class."""
    from .exceptions import ExceptionClass

    try:
        return ExceptionClass(name)
    except ValueError as exc:
        raise DelegationError(
            f"{name!r} is not a management exception class; a stored record naming "
            "one this code does not implement is refused rather than shown as text"
        ) from exc


def portfolio_spend(briefs: Sequence[ExecutiveBrief], currency: str) -> Money | None:
    """Total spend across briefs, or None if any of them never measured it.

    Summing a known number with an unknown one produces an unknown total, not a
    smaller known one. The same rule `company/finance` applies to a margin.
    """
    amounts = [item.spend for item in briefs]
    if any(value is None for value in amounts):
        return None
    return total([value for value in amounts if value is not None], currency)


__all__ = [
    "ExecutiveBrief",
    "brief_from_records",
    "build_brief",
    "exception_class_from",
    "portfolio_spend",
]

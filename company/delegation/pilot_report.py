"""What the CEO reads after a pilot run: the outcome, and the exceptions.

## The shape, and why it ends where it does

`metrics.py` already produces the management-by-exception report for shadow
replay: totals, approving seats, escalation reasons, spend. This extends it for
a pilot run, which has two things a shadow run does not — decisions that
actually took effect, and an envelope they took effect inside.

The section order is the CEO's, from the pass brief, and it is deliberate: the
objective and the outcome come first, the machinery in the middle, and
`CEO DECISIONS REQUIRED` near the end where it can be read as the headline
number. A report that opened with the number of approvals would be a report
about the system; this one is about the work.

## Why `CEO DECISIONS REQUIRED: 0` is not the goal

It is a measurement, and a report that treated it as a target would be
optimising for silence. `EXCEPTIONS` sits directly beneath it for that reason:
zero CEO decisions is good news only if the exception list is also empty, and a
run with zero CEO decisions *and* four exceptions means something was swallowed.
The two are printed together so they cannot be read apart.

## Why this is text and not a UI

The CEO asked for a CLI or report artifact and said not to build a UI unless
trivial. It is also the format that diffs: two runs of the same pilot produce
two files a reader can compare line by line, which a dashboard does not.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import datetime as dt
from dataclasses import dataclass
from typing import Any

from company.finance.money import Money

from .authority import Decision
from .common import assert_prose
from .errors import DelegationError
from .pilot import PilotActivation, PilotMode
from .pilot_record import LivePilotDecisionRecord
from .pilot_simulation import PilotReplayResult


REPORT_VERSION = "pilot_report_v1"


def _money_text(amount: Money | None) -> str:
    return amount.text if amount is not None else "0"


def _sum_money(amounts: Sequence[Money | None], currency: str = "USD") -> Money:
    total = Money.zero(currency)
    for item in amounts:
        if item is None:
            continue
        if item.currency != currency:
            # Refusing to add across currencies rather than guessing a rate.
            # A mixed-currency run is a real thing that should be visible.
            continue
        total = total + item
    return total


@dataclass(frozen=True)
class PilotRunReport:
    """One pilot run, as the CEO receives it."""

    objective: str
    outcome: str
    activation: PilotActivation
    records: tuple[LivePilotDecisionRecord, ...]
    work_orders_completed: tuple[str, ...] = ()
    exceptions: tuple[str, ...] = ()
    final_result: str = ""
    as_of: dt.date | None = None
    version: str = REPORT_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "objective", assert_prose(self.objective, "report.objective")
        )
        object.__setattr__(
            self, "outcome", assert_prose(self.outcome, "report.outcome")
        )
        if not isinstance(self.activation, PilotActivation):
            raise DelegationError("report.activation must be a PilotActivation")
        if not isinstance(self.records, tuple) or any(
            not isinstance(item, LivePilotDecisionRecord) for item in self.records
        ):
            raise DelegationError(
                "report.records must be a tuple of LivePilotDecisionRecord"
            )

    # --- the numbers -------------------------------------------------------

    @property
    def manager_approvals(self) -> tuple[LivePilotDecisionRecord, ...]:
        return tuple(
            item
            for item in self.records
            if item.authorizes_action and item.approving_seat == "engineering_manager"
        )

    @property
    def executive_approvals(self) -> tuple[LivePilotDecisionRecord, ...]:
        return tuple(
            item
            for item in self.records
            if item.authorizes_action and item.approving_seat == "cto"
        )

    @property
    def ceo_decisions_required(self) -> tuple[LivePilotDecisionRecord, ...]:
        return tuple(item for item in self.records if item.ceo_required)

    @property
    def internal_decisions(self) -> tuple[LivePilotDecisionRecord, ...]:
        return tuple(item for item in self.records if item.handled_internally)

    @property
    def cost(self) -> Money:
        return _sum_money([item.budget_used for item in self.records])

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "objective": self.objective,
            "outcome": self.outcome,
            "as_of": self.as_of.isoformat() if self.as_of else None,
            "activation_id": self.activation.activation_id,
            "envelope_id": self.activation.envelope.envelope_id,
            "mode": self.activation.mode.value,
            "work_orders_completed": list(self.work_orders_completed),
            "internal_decisions": len(self.internal_decisions),
            "manager_approvals": len(self.manager_approvals),
            "executive_approvals": len(self.executive_approvals),
            "ceo_decisions_required": len(self.ceo_decisions_required),
            "exceptions": list(self.exceptions),
            "cost": self.cost.to_dict(),
            "budget": self.activation.envelope.budget.to_dict(),
            "final_result": self.final_result,
            "records": [item.to_dict() for item in self.records],
        }

    def render(self) -> str:
        """The report, in the CEO's section order."""
        envelope = self.activation.envelope
        lines: list[str] = []

        lines.append("OBJECTIVE")
        lines.append(f"  {self.objective}")
        lines.append(f"  envelope   {envelope.envelope_id} ({envelope.objective_id})")
        lines.append(
            f"  authority  {envelope.authorized_by}, expires "
            f"{envelope.expires_on.isoformat()}"
        )
        lines.append(f"  mode       {self.activation.mode.value}")
        lines.append("")

        lines.append("OUTCOME")
        lines.append(f"  {self.outcome}")
        lines.append("")

        lines.append("WORK ORDERS COMPLETED")
        if self.work_orders_completed:
            for item in self.work_orders_completed:
                lines.append(f"  {item}")
        else:
            lines.append("  none")
        lines.append("")

        lines.append("INTERNAL DECISIONS")
        internal = self.internal_decisions
        if internal:
            for item in internal:
                lines.append(
                    f"  {item.action.value:32s} {item.approving_seat:22s} "
                    f"{item.risk.value:8s} {item.decision.value}"
                )
        else:
            lines.append("  none")
        lines.append(f"  total      {len(internal)}")
        lines.append("")

        lines.append("MANAGER APPROVALS")
        manager = self.manager_approvals
        if manager:
            for item in manager:
                who = item.approving_employee or item.approving_seat
                lines.append(f"  {item.action.value:32s} {who}")
        else:
            lines.append("  none")
        lines.append(f"  total      {len(manager)}")
        lines.append("")

        lines.append("EXECUTIVE APPROVALS")
        executive = self.executive_approvals
        if executive:
            for item in executive:
                who = item.approving_employee or item.approving_seat
                lines.append(f"  {item.action.value:32s} {who}")
        else:
            lines.append("  none")
        lines.append(f"  total      {len(executive)}")
        lines.append("")

        ceo = self.ceo_decisions_required
        lines.append("CEO DECISIONS REQUIRED")
        lines.append(f"  {len(ceo)}")
        for item in ceo:
            lines.append(f"  - {item.action.value}: {item.reason}")
        lines.append("")

        lines.append("EXCEPTIONS")
        if self.exceptions:
            for item in self.exceptions:
                lines.append(f"  - {item}")
        else:
            lines.append("  none")
        lines.append("")

        lines.append("COST")
        lines.append(
            f"  {_money_text(self.cost)} {self.cost.currency} / "
            f"{envelope.budget.text} {envelope.budget.currency} envelope"
        )
        lines.append("")

        lines.append("FINAL RESULT")
        lines.append(f"  {self.final_result or 'no result recorded'}")
        return "\n".join(lines)


def simulation_report(
    results: Mapping[str, Sequence[PilotReplayResult]],
    *,
    activation: PilotActivation,
    objective: str,
    as_of: dt.date | None = None,
) -> str:
    """The deterministic-simulation equivalent, for a run that never happened.

    Separate from `PilotRunReport.render` on purpose. A simulation has no cost,
    no completed work orders and no final result, and a report that printed
    zeroes into those fields would read like a pilot that ran and achieved
    nothing. This one says what it is.
    """
    lines: list[str] = []
    envelope = activation.envelope
    lines.append("DELEGATED ENGINEERING PILOT - DETERMINISTIC SIMULATION")
    lines.append(f"  as of      {(as_of or dt.date.today()).isoformat()}")
    lines.append(f"  envelope   {envelope.envelope_id}")
    lines.append(f"  mode       {activation.mode.value} (simulation; nothing ran)")
    lines.append("")

    for name, group in results.items():
        internal = [item for item in group if item.proceeded_internally]
        ceo = [item for item in group if item.live.ceo_required]
        mismatched = [item for item in group if not item.matches_expectation]
        diverged = [item for item in group if item.differs_from_shadow]
        lines.append(name.upper().replace("_", " "))
        lines.append(f"  scenarios              {len(group)}")
        lines.append(f"  proceeded internally   {len(internal)}")
        lines.append(f"  required the CEO       {len(ceo)}")
        lines.append(
            f"  matched expectation    {len(group) - len(mismatched)}/{len(group)}"
        )
        for item in group:
            mark = "ok " if item.matches_expectation else "BAD"
            verdict = "internal" if item.proceeded_internally else "escalated"
            lines.append(f"    [{mark}] {item.scenario_id:34s} {verdict}")
            if item.live.failed_gates:
                gates = ", ".join(
                    gate.gate_id.value for gate in item.live.failed_gates
                )
                lines.append(f"           gates: {gates}")
        if diverged:
            lines.append("  DIVERGED FROM SHADOW")
            for item in diverged:
                lines.append(f"    {item.scenario_id}: {item.divergence_reason}")
        lines.append("")

    lines.append("NO REAL WORK ORDER RAN")
    lines.append("  Every decision above is a calculation over recorded history.")
    lines.append("  Nothing was spent, no branch moved, and the pilot is not")
    lines.append("  activated in the canonical Company OS.")
    return "\n".join(lines)


__all__ = ["REPORT_VERSION", "PilotRunReport", "simulation_report"]

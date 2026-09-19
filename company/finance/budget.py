"""An authorization boundary, and what is actually left of it.

## A budget is evidence, not a wallet

Nothing in this package spends a budget. A `BudgetLine` records that somebody
with authority authorised an amount for a scope over a period, and
`consumption()` reports how much of it recorded costs have used. That is the
whole contract: budget is an authorization and evidence boundary (section 14),
and treating it as a balance a process draws down is how automated spending
starts.

Revising a budget is therefore not an edit. A new line supersedes the old one
and both stay in the ledger, because "the budget was raised in March" is a fact
somebody will need and an in-place edit destroys it.

## Unknown consumption is a state, not a zero

Section 15 is the reason `ConsumptionState` has an UNKNOWN member and
`BudgetConsumption.actual` is `Money | None`. A budget whose costs have not been
recorded yet has *unknown* consumption. Reporting it as zero would say the
budget is untouched, which is the most reassuring possible way to be wrong.

So: no recorded costs and no assertion that none exist means UNKNOWN. A caller
that genuinely knows the costs are complete says so with
`consumption(..., costs_are_complete=True)`, and only then can a zero mean zero.

## Scope is checked, not assumed

A budget for `format:race_shorts` consuming a cost charged to
`project:website` is a category error that produces a plausible number. Every
cost offered to `consumption()` is checked against the line's scope, and a
mismatch is reported rather than counted.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, ClassVar, Iterable

from knowledge.company_os.records import Evidence

from .common import (
    SubjectRef,
    assert_day,
    assert_evidence_backed,
    assert_human,
    assert_prose,
    assert_record_id,
    evidence_tuple,
    record_to_dict,
)
from .costs import CostCategory, CostRecord
from .errors import FinanceError
from .money import Money
from .period import FinancialPeriod


class LimitKind(Enum):
    """What happens at the line. Recorded here; enforced by a human."""

    HARD = "hard"  # going over is a breach somebody has to answer for
    SOFT = "soft"  # going over is a signal, not a violation


class ConsumptionState(Enum):
    """Where a budget stands. UNKNOWN is a real answer, and the default one."""

    UNKNOWN = "unknown"
    UNDER = "under"
    AT = "at"
    OVER = "over"


@dataclass(frozen=True)
class BudgetLine:
    """One authorised amount, for one scope, over one period."""

    kind: ClassVar[str] = "budget"

    budget_id: str
    period: FinancialPeriod
    scope: SubjectRef
    amount: Money
    owner: str
    evidence: tuple[Evidence, ...]
    recorded_by: str
    recorded_on: dt.date
    category: CostCategory | None = None
    limit_kind: LimitKind = LimitKind.SOFT
    approval_ref: str = ""
    supersedes: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        assert_record_id(self.budget_id, "budget_id")
        if not isinstance(self.period, FinancialPeriod):
            raise FinanceError(
                f"budget {self.budget_id!r}: period must be a FinancialPeriod"
            )
        if not isinstance(self.scope, SubjectRef):
            raise FinanceError(f"budget {self.budget_id!r}: scope must be a SubjectRef")
        if not isinstance(self.amount, Money):
            raise FinanceError(f"budget {self.budget_id!r}: amount must be Money")
        if self.amount.is_negative:
            raise FinanceError(
                f"budget {self.budget_id!r}: a budget is not negative ({self.amount})"
            )
        self.period.assert_currency_matches(
            self.amount, f"budget {self.budget_id!r} amount"
        )
        if self.category is not None and not isinstance(self.category, CostCategory):
            raise FinanceError(
                f"budget {self.budget_id!r}: category must be a CostCategory or None "
                "for a line covering every category"
            )
        if not isinstance(self.limit_kind, LimitKind):
            raise FinanceError(f"budget {self.budget_id!r}: limit_kind must be a LimitKind")
        assert_human(self.owner, f"budget {self.budget_id!r} owner")
        assert_prose(self.recorded_by, f"budget {self.budget_id!r} recorded_by")
        object.__setattr__(self, "recorded_on", assert_day(self.recorded_on, "recorded_on"))
        if self.supersedes:
            assert_record_id(self.supersedes, f"budget {self.budget_id!r} supersedes")
        for name in ("approval_ref", "notes"):
            if not isinstance(getattr(self, name), str):
                raise FinanceError(f"budget {self.budget_id!r}: {name} must be a string")
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))
        assert_evidence_backed(
            self.evidence,
            f"budget {self.budget_id!r} evidence",
            "a budget is an authorization, and an authorization nobody can point at is "
            "a number somebody assumed (brief section 14)",
        )

    @property
    def currency(self) -> str:
        return self.amount.currency

    def covers(self, cost: CostRecord) -> bool:
        """True when this cost falls inside the line's scope, category and period."""
        if cost.subject.key != self.scope.key:
            return False
        if self.category is not None and cost.category is not self.category:
            return False
        return self.period.contains(cost.incurred_on)

    def to_dict(self) -> dict[str, Any]:
        return record_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BudgetLine:
        category = data.get("category")
        return cls(
            budget_id=data["budget_id"],
            period=FinancialPeriod.from_dict(data["period"]),
            scope=SubjectRef.from_dict(data["scope"]),
            amount=Money.from_dict(data["amount"], "budget amount"),
            owner=data["owner"],
            evidence=evidence_tuple(data.get("evidence")),
            recorded_by=data["recorded_by"],
            recorded_on=assert_day(data["recorded_on"], "recorded_on"),
            category=CostCategory(category) if category else None,
            limit_kind=LimitKind(data.get("limit_kind", "soft")),
            approval_ref=data.get("approval_ref", ""),
            supersedes=data.get("supersedes", ""),
            notes=data.get("notes", ""),
        )


@dataclass(frozen=True)
class BudgetConsumption:
    """How much of one budget recorded costs have used, or that nobody knows."""

    budget: BudgetLine
    actual: Money | None
    remaining: Money | None
    fraction_consumed: Decimal | None
    state: ConsumptionState
    counted_costs: int
    out_of_scope: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()

    @property
    def is_known(self) -> bool:
        return self.state is not ConsumptionState.UNKNOWN

    @property
    def is_over(self) -> bool:
        """True only when consumption is known and over. Unknown is not under."""
        return self.state is ConsumptionState.OVER

    def to_dict(self) -> dict[str, Any]:
        return {
            "budget_id": self.budget.budget_id,
            "actual": self.actual.to_dict() if self.actual else None,
            "remaining": self.remaining.to_dict() if self.remaining else None,
            "fraction_consumed": (
                format(self.fraction_consumed, "f")
                if self.fraction_consumed is not None
                else None
            ),
            "state": self.state.value,
            "counted_costs": self.counted_costs,
            "out_of_scope": list(self.out_of_scope),
            "missing": list(self.missing),
        }


def consumption(
    budget: BudgetLine,
    costs: Iterable[CostRecord],
    *,
    costs_are_complete: bool = False,
) -> BudgetConsumption:
    """What recorded costs have used of one budget.

    `costs_are_complete` is the caller asserting that every cost against this
    scope and period has been recorded. Without it, an empty or partial cost set
    yields `UNKNOWN` rather than a reassuring zero - section 15's whole point.

    A cost in another currency is refused rather than converted, and a cost
    outside the scope is listed in `out_of_scope` rather than counted.
    """
    counted: list[CostRecord] = []
    out_of_scope: list[str] = []
    for cost in costs:
        if not isinstance(cost, CostRecord):
            raise FinanceError(
                f"budget {budget.budget_id!r}: consumption takes CostRecords, got "
                f"{type(cost).__name__}"
            )
        if cost.currency != budget.currency:
            raise FinanceError(
                f"budget {budget.budget_id!r} is in {budget.currency} and cost "
                f"{cost.cost_id!r} is in {cost.currency}. Nothing here converts a "
                "currency; budget the second one separately"
            )
        if budget.covers(cost):
            counted.append(cost)
        else:
            out_of_scope.append(
                f"{cost.cost_id}: {cost.subject.key} / {cost.category.value} / "
                f"{cost.incurred_on.isoformat()} is outside "
                f"{budget.scope.key} / "
                f"{budget.category.value if budget.category else 'any category'} / "
                f"{budget.period.period_id}"
            )
    missing: list[str] = []
    if not costs_are_complete:
        missing.append(
            f"nobody has asserted that every cost against {budget.scope.key} in period "
            f"{budget.period.period_id} is recorded, so consumption is unknown rather "
            "than the total of what happens to be stored"
        )
        return BudgetConsumption(
            budget=budget,
            actual=None,
            remaining=None,
            fraction_consumed=None,
            state=ConsumptionState.UNKNOWN,
            counted_costs=len(counted),
            out_of_scope=tuple(sorted(out_of_scope)),
            missing=tuple(missing),
        )
    actual = Money.zero(budget.currency)
    for cost in counted:
        actual = actual + cost.amount
    remaining = budget.amount - actual
    if budget.amount.is_zero:
        fraction = None
        missing.append(
            f"budget {budget.budget_id!r} authorises zero, so a consumed fraction has no "
            "denominator"
        )
        state = ConsumptionState.OVER if actual.amount > 0 else ConsumptionState.AT
    else:
        fraction = actual.ratio_to(budget.amount)
        if actual > budget.amount:
            state = ConsumptionState.OVER
        elif actual == budget.amount:
            state = ConsumptionState.AT
        else:
            state = ConsumptionState.UNDER
    return BudgetConsumption(
        budget=budget,
        actual=actual,
        remaining=remaining,
        fraction_consumed=fraction,
        state=state,
        counted_costs=len(counted),
        out_of_scope=tuple(sorted(out_of_scope)),
        missing=tuple(missing),
    )

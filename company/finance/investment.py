"""What a reusable thing cost, how often it was reused, and what that saved.

## The distinction this module exists to keep

A camera system that costs three days to build and saves two hours per video is
the central economic bet of a simulation factory. It is also the easiest place
in the company to write down a number nobody measured: "saves two hours" is a
belief until somebody times it.

So `ReuseEvent.cost_avoided` is `Money | None`, and the `None` is load-bearing.
An event with no measured saving is still a reuse - it happened, it counts
toward `reuse_count` - but it contributes nothing to `measured_cost_avoided`.
Section 10: do not invent cost saved.

## MEASURED and HYPOTHETICAL are different answers, never averaged

`BreakEvenAnalysis` takes measured savings and assumed savings as separate
arguments and never mixes them. If measured savings exist, the result is
MEASURED and any assumption supplied is listed as *not used*. If only
assumptions exist, the result is HYPOTHETICAL and says so in its own `basis`
field, so a break-even quoted from it carries the label with it.

The alternative - blending an observed hour with an assumed one - produces a
payback period that is partly real and entirely unlabelled, which is worse than
either input alone.

## Events accrue; the investment record does not change

A reuse is appended as its own record. The `ReusableInvestment` is written once
and never rewritten, so what the investment cost on the day it was made is still
readable after fifty reuses.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, replace
from decimal import Decimal
from enum import Enum
from typing import Any, ClassVar, Iterable

from knowledge.company_os.records import Evidence

from .common import (
    SubjectRef,
    assert_day,
    assert_evidence_backed,
    assert_prose,
    assert_record_id,
    assert_ref,
    evidence_tuple,
    record_to_dict,
    text_tuple,
)
from .errors import FinanceError
from .money import Money
from .period import FinancialPeriod


class InvestmentStatus(Enum):
    ACTIVE = "active"
    RETIRED = "retired"
    SUPERSEDED = "superseded"


class Basis(Enum):
    """Whether a conclusion rests on something observed or something assumed."""

    MEASURED = "measured"
    HYPOTHETICAL = "hypothetical"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ReusableInvestment:
    """Something built once to make later work cheaper, and what it cost."""

    kind: ClassVar[str] = "reusable_investment"

    investment_id: str
    subject: SubjectRef
    cost: Money
    created_on: dt.date
    purpose: str
    evidence: tuple[Evidence, ...]
    recorded_by: str
    recorded_on: dt.date
    status: InvestmentStatus = InvestmentStatus.ACTIVE
    cost_record_ids: tuple[str, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        assert_record_id(self.investment_id, "investment_id")
        if not isinstance(self.subject, SubjectRef):
            raise FinanceError(
                f"investment {self.investment_id!r}: subject must be a SubjectRef naming "
                "the tool, asset or module built"
            )
        if not isinstance(self.cost, Money):
            raise FinanceError(f"investment {self.investment_id!r}: cost must be Money")
        if self.cost.is_negative:
            raise FinanceError(
                f"investment {self.investment_id!r}: cost is not negative ({self.cost})"
            )
        if not isinstance(self.status, InvestmentStatus):
            raise FinanceError(
                f"investment {self.investment_id!r}: status must be an InvestmentStatus"
            )
        object.__setattr__(self, "created_on", assert_day(self.created_on, "created_on"))
        object.__setattr__(self, "recorded_on", assert_day(self.recorded_on, "recorded_on"))
        assert_prose(self.purpose, f"investment {self.investment_id!r} purpose")
        assert_prose(self.recorded_by, f"investment {self.investment_id!r} recorded_by")
        object.__setattr__(
            self,
            "cost_record_ids",
            tuple(
                assert_record_id(item, f"investment {self.investment_id!r} cost_record_ids")
                for item in self.cost_record_ids or ()
            ),
        )
        if not isinstance(self.notes, str):
            raise FinanceError(f"investment {self.investment_id!r}: notes must be a string")
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))
        assert_evidence_backed(
            self.evidence,
            f"investment {self.investment_id!r} evidence",
            "the build cost has to point at the cost records or the commit that produced it",
        )

    @property
    def currency(self) -> str:
        return self.cost.currency

    def to_dict(self) -> dict[str, Any]:
        return record_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReusableInvestment:
        return cls(
            investment_id=data["investment_id"],
            subject=SubjectRef.from_dict(data["subject"]),
            cost=Money.from_dict(data["cost"], "investment cost"),
            created_on=assert_day(data["created_on"], "created_on"),
            purpose=data["purpose"],
            evidence=evidence_tuple(data.get("evidence")),
            recorded_by=data["recorded_by"],
            recorded_on=assert_day(data["recorded_on"], "recorded_on"),
            status=InvestmentStatus(data.get("status", "active")),
            cost_record_ids=tuple(data.get("cost_record_ids", ())),
            notes=data.get("notes", ""),
        )


@dataclass(frozen=True)
class ReuseEvent:
    """One time the investment was used again. The saving may be unmeasured.

    `cost_avoided=None` is the normal case and not a defect. It means the reuse
    happened and nobody timed what it saved, which is exactly what the record
    should say.
    """

    kind: ClassVar[str] = "reuse_event"

    event_id: str
    investment_id: str
    occurred_on: dt.date
    used_by: SubjectRef
    recorded_by: str
    recorded_on: dt.date
    cost_avoided: Money | None = None
    measurement_ref: str = ""
    evidence: tuple[Evidence, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        assert_record_id(self.event_id, "event_id")
        assert_record_id(self.investment_id, "investment_id")
        if not isinstance(self.used_by, SubjectRef):
            raise FinanceError(f"reuse event {self.event_id!r}: used_by must be a SubjectRef")
        object.__setattr__(self, "occurred_on", assert_day(self.occurred_on, "occurred_on"))
        object.__setattr__(self, "recorded_on", assert_day(self.recorded_on, "recorded_on"))
        assert_prose(self.recorded_by, f"reuse event {self.event_id!r} recorded_by")
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))
        if self.cost_avoided is not None:
            if not isinstance(self.cost_avoided, Money):
                raise FinanceError(
                    f"reuse event {self.event_id!r}: cost_avoided must be Money or None"
                )
            if self.cost_avoided.is_negative:
                raise FinanceError(
                    f"reuse event {self.event_id!r}: cost_avoided is not negative"
                )
            if not self.measurement_ref.strip():
                raise FinanceError(
                    f"reuse event {self.event_id!r}: a measured saving needs a "
                    "measurement_ref pointing at how it was measured. An unmeasured reuse "
                    "leaves cost_avoided as None (brief section 10)"
                )
            assert_evidence_backed(
                self.evidence,
                f"reuse event {self.event_id!r} evidence",
                "a claimed saving needs evidence; an unmeasured reuse leaves cost_avoided "
                "as None instead",
            )
        if self.measurement_ref:
            assert_ref(self.measurement_ref, f"reuse event {self.event_id!r} measurement_ref")
        if not isinstance(self.notes, str):
            raise FinanceError(f"reuse event {self.event_id!r}: notes must be a string")

    @property
    def is_measured(self) -> bool:
        return self.cost_avoided is not None

    def to_dict(self) -> dict[str, Any]:
        return record_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReuseEvent:
        avoided = data.get("cost_avoided")
        return cls(
            event_id=data["event_id"],
            investment_id=data["investment_id"],
            occurred_on=assert_day(data["occurred_on"], "occurred_on"),
            used_by=SubjectRef.from_dict(data["used_by"]),
            recorded_by=data["recorded_by"],
            recorded_on=assert_day(data["recorded_on"], "recorded_on"),
            cost_avoided=Money.from_dict(avoided, "cost_avoided") if avoided else None,
            measurement_ref=data.get("measurement_ref", ""),
            evidence=evidence_tuple(data.get("evidence")),
            notes=data.get("notes", ""),
        )


@dataclass(frozen=True)
class InvestmentEconomics:
    """An investment's position: what it cost, what it saved, what is unmeasured."""

    investment: ReusableInvestment
    reuse_count: int
    measured_reuse_count: int
    measured_cost_avoided: Money
    maintenance_cost: Money
    net_position: Money
    broke_even: bool
    basis: Basis
    missing: tuple[str, ...]

    @property
    def currency(self) -> str:
        return self.investment.currency

    @property
    def unmeasured_reuse_count(self) -> int:
        return self.reuse_count - self.measured_reuse_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "investment_id": self.investment.investment_id,
            "reuse_count": self.reuse_count,
            "measured_reuse_count": self.measured_reuse_count,
            "unmeasured_reuse_count": self.unmeasured_reuse_count,
            "measured_cost_avoided": self.measured_cost_avoided.to_dict(),
            "maintenance_cost": self.maintenance_cost.to_dict(),
            "net_position": self.net_position.to_dict(),
            "broke_even": self.broke_even,
            "basis": self.basis.value,
            "missing": list(self.missing),
        }


def investment_economics(
    investment: ReusableInvestment,
    events: Iterable[ReuseEvent] = (),
    *,
    maintenance_cost: Money | None = None,
) -> InvestmentEconomics:
    """Net position from recorded values only. Nothing here estimates a saving."""
    own = [event for event in events if event.investment_id == investment.investment_id]
    measured = [event for event in own if event.is_measured]
    avoided = Money.zero(investment.currency)
    for event in measured:
        if event.cost_avoided is None:  # pragma: no cover - guarded by is_measured
            continue
        if event.cost_avoided.currency != investment.currency:
            raise FinanceError(
                f"reuse event {event.event_id!r} saves {event.cost_avoided.currency} "
                f"against an investment in {investment.currency}; nothing here converts"
            )
        avoided = avoided + event.cost_avoided
    maintenance = maintenance_cost or Money.zero(investment.currency)
    if maintenance.currency != investment.currency:
        raise FinanceError(
            f"investment {investment.investment_id!r}: maintenance in "
            f"{maintenance.currency} against a cost in {investment.currency}"
        )
    spent = investment.cost + maintenance
    net = avoided - spent
    missing: list[str] = []
    unmeasured = len(own) - len(measured)
    if unmeasured:
        missing.append(
            f"{unmeasured} of {len(own)} reuse(s) recorded no measured cost avoided, so "
            "the saving is a floor rather than a total"
        )
    if maintenance_cost is None:
        missing.append(
            f"no maintenance cost supplied for {investment.investment_id!r}; the net "
            "position assumes zero upkeep, which is an assumption not a measurement"
        )
    basis = Basis.MEASURED if measured else Basis.UNKNOWN
    if not own:
        missing.append(
            f"investment {investment.investment_id!r} has no recorded reuse; its value is "
            "unmeasured, not zero"
        )
    return InvestmentEconomics(
        investment=investment,
        reuse_count=len(own),
        measured_reuse_count=len(measured),
        measured_cost_avoided=avoided,
        maintenance_cost=maintenance,
        net_position=net,
        broke_even=bool(measured) and avoided >= spent,
        basis=basis,
        missing=tuple(missing),
    )


@dataclass(frozen=True)
class BreakEvenResult:
    """When an investment pays back, and whether that is observed or assumed."""

    label: str
    basis: Basis
    upfront_cost: Money
    recurring_cost: Money
    saving_per_period: Money | None
    net_per_period: Money | None
    periods_to_break_even: Decimal | None
    net_over_horizon: Money | None
    horizon_periods: int | None
    assumptions: tuple[str, ...]
    unused_inputs: tuple[str, ...]
    caveats: tuple[str, ...]

    @property
    def is_hypothetical(self) -> bool:
        return self.basis is Basis.HYPOTHETICAL

    def statement(self) -> str:
        """One sentence that carries its own basis, so a quote cannot drop it."""
        if self.periods_to_break_even is None:
            return (
                f"{self.label}: break-even cannot be computed ({self.basis.value}); "
                + "; ".join(self.caveats or ("no saving supplied",))
            )
        label = "HYPOTHETICAL" if self.is_hypothetical else "MEASURED"
        return (
            f"{self.label}: {label} break-even after "
            f"{format(self.periods_to_break_even, 'f')} period(s), on "
            f"{self.saving_per_period} saved per period against {self.upfront_cost} "
            f"upfront and {self.recurring_cost} recurring"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "basis": self.basis.value,
            "upfront_cost": self.upfront_cost.to_dict(),
            "recurring_cost": self.recurring_cost.to_dict(),
            "saving_per_period": (
                self.saving_per_period.to_dict() if self.saving_per_period else None
            ),
            "net_per_period": self.net_per_period.to_dict() if self.net_per_period else None,
            "periods_to_break_even": (
                format(self.periods_to_break_even, "f")
                if self.periods_to_break_even is not None
                else None
            ),
            "net_over_horizon": (
                self.net_over_horizon.to_dict() if self.net_over_horizon else None
            ),
            "horizon_periods": self.horizon_periods,
            "assumptions": list(self.assumptions),
            "unused_inputs": list(self.unused_inputs),
            "caveats": list(self.caveats),
            "statement": self.statement(),
        }


def break_even(
    label: str,
    *,
    upfront_cost: Money,
    recurring_cost: Money | None = None,
    measured_saving_per_period: Money | None = None,
    assumed_saving_per_period: Money | None = None,
    assumptions: Iterable[str] = (),
    horizon_periods: int | None = None,
) -> BreakEvenResult:
    """Periods to payback, labelled by whether the saving was observed or assumed.

    Measured wins when both are supplied, and the assumed figure is reported in
    `unused_inputs` rather than blended in. An assumed saving with no stated
    assumption is refused: section 11 requires a hypothesis to be supplied by an
    analyst, and an unattributed one is indistinguishable from a fact.
    """
    assert_prose(label, "break-even label")
    if not isinstance(upfront_cost, Money):
        raise FinanceError("break_even: upfront_cost must be Money")
    currency = upfront_cost.currency
    recurring = recurring_cost or Money.zero(currency)
    if recurring.currency != currency:
        raise FinanceError(
            f"break_even {label!r}: recurring cost in {recurring.currency} against "
            f"upfront in {currency}; nothing here converts a currency"
        )
    stated = text_tuple(tuple(assumptions), "break-even assumption")
    caveats: list[str] = []
    unused: list[str] = []

    for name, value in (
        ("measured_saving_per_period", measured_saving_per_period),
        ("assumed_saving_per_period", assumed_saving_per_period),
    ):
        if value is not None:
            if not isinstance(value, Money):
                raise FinanceError(f"break_even {label!r}: {name} must be Money or None")
            if value.currency != currency:
                raise FinanceError(
                    f"break_even {label!r}: {name} in {value.currency} against upfront in "
                    f"{currency}"
                )

    if assumed_saving_per_period is not None and not stated:
        raise FinanceError(
            f"break_even {label!r}: an assumed saving needs a stated assumption naming "
            "who supplied it and on what grounds. An unattributed hypothesis reads as a "
            "measurement (brief section 11)"
        )

    if measured_saving_per_period is not None:
        basis = Basis.MEASURED
        saving: Money | None = measured_saving_per_period
        if assumed_saving_per_period is not None:
            unused.append(
                f"assumed saving {assumed_saving_per_period} per period was supplied and "
                "not used; the measured figure takes precedence and the two are never "
                "blended"
            )
    elif assumed_saving_per_period is not None:
        basis = Basis.HYPOTHETICAL
        saving = assumed_saving_per_period
        caveats.append(
            "break-even rests on an assumed saving, not an observed one. Every figure "
            "below is hypothetical until the saving is measured"
        )
    else:
        basis = Basis.UNKNOWN
        saving = None
        caveats.append(
            "no saving supplied, measured or assumed, so there is nothing to pay the "
            "cost back"
        )

    if horizon_periods is not None and (
        isinstance(horizon_periods, bool)
        or not isinstance(horizon_periods, int)
        or horizon_periods < 1
    ):
        raise FinanceError(f"break_even {label!r}: horizon_periods must be a positive int")

    net_per_period = (saving - recurring) if saving is not None else None
    periods: Decimal | None = None
    if net_per_period is not None:
        if net_per_period.amount <= 0:
            caveats.append(
                f"net saving per period is {net_per_period}; at this rate the upfront "
                f"{upfront_cost} is never recovered"
            )
        elif upfront_cost.is_zero:
            periods = Decimal(0)
        else:
            periods = upfront_cost.amount / net_per_period.amount
    net_over_horizon: Money | None = None
    if horizon_periods is not None and net_per_period is not None:
        net_over_horizon = (net_per_period * horizon_periods) - upfront_cost
    elif horizon_periods is None and saving is not None:
        caveats.append(
            "no evaluation horizon supplied, so only the payback period is reported"
        )
    return BreakEvenResult(
        label=label,
        basis=basis,
        upfront_cost=upfront_cost,
        recurring_cost=recurring,
        saving_per_period=saving,
        net_per_period=net_per_period,
        periods_to_break_even=periods,
        net_over_horizon=net_over_horizon,
        horizon_periods=horizon_periods,
        assumptions=stated,
        unused_inputs=tuple(unused),
        caveats=tuple(caveats),
    )


def break_even_from_investment(
    economics: InvestmentEconomics,
    period: FinancialPeriod,
    *,
    horizon_periods: int | None = None,
) -> BreakEvenResult:
    """Break-even for a real investment, from its measured reuse savings only.

    The per-period saving is the measured total divided by the number of
    measured reuses, so an investment with no measured saving produces an
    UNKNOWN result rather than a hopeful one.
    """
    saving = (
        economics.measured_cost_avoided.divided_by(economics.measured_reuse_count)
        if economics.measured_reuse_count
        else None
    )
    result = break_even(
        f"{economics.investment.investment_id} over {period.label}",
        upfront_cost=economics.investment.cost,
        recurring_cost=economics.maintenance_cost,
        measured_saving_per_period=saving,
        horizon_periods=horizon_periods,
    )
    if economics.missing:
        return replace(
            result, caveats=tuple(dict.fromkeys(result.caveats + economics.missing))
        )
    return result

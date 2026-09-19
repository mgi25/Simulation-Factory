"""Cost, revenue and contribution for one thing - and what is missing from each.

## Every summary carries its own gaps

The type that does the work is not `DeliverableEconomics.total_cost`, it is
`DeliverableEconomics.missing`. A summary computed over records that happen to
exist is a summary of what somebody remembered to record, and the difference
between that and the truth is invisible unless the summary states it.

So every figure below has one of three states: a number, `None` with a reason in
`missing`, or a number plus a caveat saying it is a floor. There is no fourth
state where a gap becomes a zero.

## Margin is suppressed, not estimated

`gross_margin` is `None` unless revenue is known, non-zero, and no cost input is
missing. That is section 8's "never report margin when required inputs are
missing", and it is the one rule here that a reader is most likely to want to
break: a margin over partial costs looks fine and is flattering by exactly the
amount that was not recorded.

## Failures count

Section 18: a rejected attempt and an abandoned prototype cost real money, and
deleting them from the totals turns cost-per-accepted-deliverable into
cost-per-deliverable-that-worked, which is a different and much smaller number.
`accepted`, `rejected` and `abandoned` are counted separately and all three cost
buckets are summed into the total.

## Sample size travels with every format figure

Section 9: do not rank formats from one video's outcome. `FormatEconomics`
carries `videos_produced`, and `compare_formats` refuses to order two formats
when either is below the minimum the caller states. Nothing here produces a
ranking from an unqualified average.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Mapping

from .common import SubjectRef
from .costs import Attribution, CostAdjustment, CostRecord
from .errors import FinanceError
from .money import Money
from .period import FinancialPeriod
from .revenue import RevenueRecord, basis_mix


class DeliverableOutcome(Enum):
    """How an attempt ended. All three cost money; only one shipped."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ABANDONED = "abandoned"


@dataclass(frozen=True)
class OutcomeCounts:
    """How many attempts ended each way, supplied by whoever knows.

    Not derived from the cost records: a cost does not know whether the video it
    paid for shipped. A caller that has not counted leaves this `None` and every
    per-deliverable figure comes back unknown, which is correct.
    """

    accepted: int = 0
    rejected: int = 0
    abandoned: int = 0

    def __post_init__(self) -> None:
        for name in ("accepted", "rejected", "abandoned"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise FinanceError(
                    f"outcome count {name} must be a non-negative whole number, got "
                    f"{value!r}"
                )

    @property
    def attempted(self) -> int:
        return self.accepted + self.rejected + self.abandoned

    def to_dict(self) -> dict[str, int]:
        return {
            "accepted": self.accepted,
            "rejected": self.rejected,
            "abandoned": self.abandoned,
            "attempted": self.attempted,
        }


@dataclass(frozen=True)
class DeliverableEconomics:
    """What one subject cost, earned and contributed, with its gaps named."""

    subject: SubjectRef
    period: FinancialPeriod
    direct_cost: Money
    allocated_cost: Money
    unallocated_cost: Money
    adjustments: Money
    total_cost: Money
    gross_revenue: Money
    net_contribution: Money | None
    gross_margin: Decimal | None
    outcomes: OutcomeCounts | None
    cost_records: int
    revenue_records: int
    revenue_basis: tuple[str, ...]
    missing: tuple[str, ...]
    caveats: tuple[str, ...]

    @property
    def currency(self) -> str:
        return self.period.currency

    @property
    def cost_per_accepted_deliverable(self) -> Money | None:
        """Total cost divided by accepted deliverables, or None.

        Includes rejected and abandoned attempts in the numerator on purpose -
        that is what makes it the cost of *getting* an accepted deliverable
        rather than the cost of the one that worked.
        """
        if self.outcomes is None or self.outcomes.accepted == 0:
            return None
        if self.missing:
            return None
        return self.total_cost.divided_by(self.outcomes.accepted)

    @property
    def revenue_per_accepted_deliverable(self) -> Money | None:
        if self.outcomes is None or self.outcomes.accepted == 0:
            return None
        if self.revenue_records == 0:
            return None
        return self.gross_revenue.divided_by(self.outcomes.accepted)

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject.to_dict(),
            "period": self.period.to_dict(),
            "direct_cost": self.direct_cost.to_dict(),
            "allocated_cost": self.allocated_cost.to_dict(),
            "unallocated_cost": self.unallocated_cost.to_dict(),
            "adjustments": self.adjustments.to_dict(),
            "total_cost": self.total_cost.to_dict(),
            "gross_revenue": self.gross_revenue.to_dict(),
            "net_contribution": (
                self.net_contribution.to_dict() if self.net_contribution else None
            ),
            "gross_margin": (
                format(self.gross_margin, "f") if self.gross_margin is not None else None
            ),
            "outcomes": self.outcomes.to_dict() if self.outcomes else None,
            "cost_records": self.cost_records,
            "revenue_records": self.revenue_records,
            "revenue_basis": list(self.revenue_basis),
            "missing": list(self.missing),
            "caveats": list(self.caveats),
        }


def deliverable_economics(
    subject: SubjectRef,
    period: FinancialPeriod,
    *,
    costs: Iterable[CostRecord] = (),
    revenue: Iterable[RevenueRecord] = (),
    adjustments: Iterable[CostAdjustment] = (),
    outcomes: OutcomeCounts | None = None,
    unpriced_resources: Iterable[str] = (),
    costs_are_complete: bool = False,
    revenue_is_complete: bool = False,
) -> DeliverableEconomics:
    """Sum one subject's records over one period, and name what is not there.

    Records outside the subject or the period are ignored rather than counted;
    records in another currency are refused rather than converted. The two
    `*_are_complete` flags are the caller asserting that nothing is missing, and
    without them margin and net contribution stay `None` - a contribution over
    an unknown fraction of the costs is not a contribution.
    """
    zero = period.zero()
    direct = zero
    allocated = zero
    unallocated_total = zero
    cost_ids: set[str] = set()
    counted_costs = 0
    for cost in costs:
        if not isinstance(cost, CostRecord):
            raise FinanceError(f"expected CostRecord, got {type(cost).__name__}")
        if cost.subject.key != subject.key or not period.contains(cost.incurred_on):
            continue
        period.assert_currency_matches(cost.amount, f"cost {cost.cost_id!r}")
        cost_ids.add(cost.cost_id)
        counted_costs += 1
        if cost.attribution is Attribution.DIRECT:
            direct = direct + cost.amount
        elif cost.attribution is Attribution.ALLOCATED:
            allocated = allocated + cost.amount
        else:
            unallocated_total = unallocated_total + cost.amount

    adjustment_total = zero
    for adjustment in adjustments:
        if not isinstance(adjustment, CostAdjustment):
            raise FinanceError(
                f"expected CostAdjustment, got {type(adjustment).__name__}"
            )
        if adjustment.cost_id not in cost_ids:
            continue
        period.assert_currency_matches(
            adjustment.amount, f"adjustment {adjustment.adjustment_id!r}"
        )
        adjustment_total = adjustment_total + adjustment.signed_amount

    revenue_records = [
        record
        for record in revenue
        if isinstance(record, RevenueRecord)
        and record.subject.key == subject.key
        and period.contains(record.received_on)
    ]
    gross_revenue = zero
    for record in revenue_records:
        period.assert_currency_matches(record.amount, f"revenue {record.revenue_id!r}")
        gross_revenue = gross_revenue + record.amount

    total_cost = direct + allocated + unallocated_total + adjustment_total

    missing: list[str] = []
    caveats: list[str] = []
    for reason in unpriced_resources:
        missing.append(str(reason))
    if not costs_are_complete:
        missing.append(
            f"nobody has asserted that every cost for {subject.key} in period "
            f"{period.period_id} is recorded; the total is a floor over "
            f"{counted_costs} record(s)"
        )
    if not revenue_is_complete:
        missing.append(
            f"nobody has asserted that every revenue line for {subject.key} in period "
            f"{period.period_id} is recorded"
        )
    if not revenue_records:
        missing.append(
            f"no revenue recorded for {subject.key} in period {period.period_id}"
        )
    if not unallocated_total.is_zero:
        caveats.append(
            f"{unallocated_total} of shared cost is recorded against this subject but "
            "unallocated; it is included in the total and attributed to no rule"
        )
    basis = basis_mix(revenue_records)
    if len(basis) > 1:
        caveats.append(
            "revenue mixes " + " and ".join(basis) + " figures; the sum is ambiguous"
        )
    if "unknown" in basis:
        caveats.append(
            "at least one revenue line does not say whether it is gross or net"
        )

    inputs_known = not missing
    net_contribution = gross_revenue - total_cost if inputs_known else None
    if not inputs_known:
        margin = None
    elif gross_revenue.is_zero:
        margin = None
        missing.append(
            "gross revenue is zero, so a margin has no denominator - the contribution "
            "is the negative of the cost"
        )
    else:
        margin = (gross_revenue - total_cost).ratio_to(gross_revenue)

    return DeliverableEconomics(
        subject=subject,
        period=period,
        direct_cost=direct,
        allocated_cost=allocated,
        unallocated_cost=unallocated_total,
        adjustments=adjustment_total,
        total_cost=total_cost,
        gross_revenue=gross_revenue,
        net_contribution=net_contribution,
        gross_margin=margin,
        outcomes=outcomes,
        cost_records=counted_costs,
        revenue_records=len(revenue_records),
        revenue_basis=basis,
        missing=tuple(missing),
        caveats=tuple(caveats),
    )


@dataclass(frozen=True)
class FormatEconomics:
    """One format family's economics, with the sample size attached to it.

    `videos_produced` is not decoration. Every average below is an average over
    that many videos, and `compare_formats` refuses to order two formats when
    either sample is too small to mean anything.
    """

    format_id: str
    period: FinancialPeriod
    videos_produced: int
    total_cost: Money
    total_revenue: Money
    reusable_investment_cost: Money
    experiment_cost: Money
    failed_prototype_cost: Money
    reuse_count: int
    amortized_reusable_cost: Money | None
    contribution: Money | None
    missing: tuple[str, ...]
    caveats: tuple[str, ...]

    @property
    def currency(self) -> str:
        return self.period.currency

    @property
    def sample_size(self) -> int:
        """The number every average here rests on."""
        return self.videos_produced

    @property
    def average_cost_per_video(self) -> Money | None:
        if self.videos_produced == 0 or self.missing:
            return None
        return self.total_cost.divided_by(self.videos_produced)

    @property
    def average_revenue_per_video(self) -> Money | None:
        if self.videos_produced == 0:
            return None
        return self.total_revenue.divided_by(self.videos_produced)

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_id": self.format_id,
            "period": self.period.to_dict(),
            "videos_produced": self.videos_produced,
            "sample_size": self.sample_size,
            "total_cost": self.total_cost.to_dict(),
            "total_revenue": self.total_revenue.to_dict(),
            "reusable_investment_cost": self.reusable_investment_cost.to_dict(),
            "experiment_cost": self.experiment_cost.to_dict(),
            "failed_prototype_cost": self.failed_prototype_cost.to_dict(),
            "reuse_count": self.reuse_count,
            "amortized_reusable_cost": (
                self.amortized_reusable_cost.to_dict()
                if self.amortized_reusable_cost
                else None
            ),
            "contribution": self.contribution.to_dict() if self.contribution else None,
            "missing": list(self.missing),
            "caveats": list(self.caveats),
        }


def format_economics(
    format_id: str,
    period: FinancialPeriod,
    *,
    video_summaries: Iterable[DeliverableEconomics] = (),
    reusable_investment_cost: Money | None = None,
    experiment_cost: Money | None = None,
    failed_prototype_cost: Money | None = None,
    reuse_count: int = 0,
    amortize_over: int | None = None,
) -> FormatEconomics:
    """Roll per-video summaries up to a format, carrying every gap upward.

    `amortize_over` is the explicit configuration section 10 requires: a
    reusable tool's cost is spread over a number of uses somebody chose and
    recorded. With no such number the amortized figure is `None`, because
    "spread it over how many" is not a question this code may answer.
    """
    zero = period.zero()
    summaries = tuple(video_summaries)
    total_cost = zero
    total_revenue = zero
    missing: list[str] = []
    caveats: list[str] = []
    for summary in summaries:
        if summary.period.period_id != period.period_id:
            raise FinanceError(
                f"format {format_id!r}: summary for {summary.subject.key} covers period "
                f"{summary.period.period_id}, not {period.period_id}. Periods are not "
                "merged silently"
            )
        period.assert_currency_matches(summary.total_cost, "video total cost")
        total_cost = total_cost + summary.total_cost
        total_revenue = total_revenue + summary.gross_revenue
        missing.extend(summary.missing)
    for name, value in (
        ("reusable_investment_cost", reusable_investment_cost),
        ("experiment_cost", experiment_cost),
        ("failed_prototype_cost", failed_prototype_cost),
    ):
        if value is not None:
            period.assert_currency_matches(value, f"format {format_id!r} {name}")
    investment = reusable_investment_cost or zero
    experiments = experiment_cost or zero
    failures = failed_prototype_cost or zero
    total_cost = total_cost + investment + experiments + failures

    if isinstance(reuse_count, bool) or not isinstance(reuse_count, int) or reuse_count < 0:
        raise FinanceError(
            f"format {format_id!r}: reuse_count must be a non-negative whole number"
        )
    amortized: Money | None = None
    if amortize_over is not None:
        if isinstance(amortize_over, bool) or not isinstance(amortize_over, int) or amortize_over <= 0:
            raise FinanceError(
                f"format {format_id!r}: amortize_over must be a positive whole number of "
                "uses, explicitly configured"
            )
        amortized = investment.divided_by(amortize_over)
        caveats.append(
            f"reusable cost is amortized over {amortize_over} use(s) by explicit "
            "configuration, not by an estimate"
        )
    elif not investment.is_zero:
        caveats.append(
            "reusable investment is charged in full to this period; no amortization "
            "horizon was configured"
        )

    if len(summaries) == 0:
        missing.append(f"no per-video summaries supplied for format {format_id!r}")
    if len(summaries) == 1:
        caveats.append(
            "one video. Nothing here supports a judgement about the format - only about "
            "this video (brief section 9)"
        )
    contribution = (total_revenue - total_cost) if not missing else None
    return FormatEconomics(
        format_id=format_id,
        period=period,
        videos_produced=len(summaries),
        total_cost=total_cost,
        total_revenue=total_revenue,
        reusable_investment_cost=investment,
        experiment_cost=experiments,
        failed_prototype_cost=failures,
        reuse_count=reuse_count,
        amortized_reusable_cost=amortized,
        contribution=contribution,
        missing=tuple(dict.fromkeys(missing)),
        caveats=tuple(dict.fromkeys(caveats)),
    )


@dataclass(frozen=True)
class FormatComparison:
    """Two formats side by side, or a statement of why they cannot be compared."""

    left: FormatEconomics
    right: FormatEconomics
    minimum_sample: int
    comparable: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "left": self.left.format_id,
            "right": self.right.format_id,
            "minimum_sample": self.minimum_sample,
            "comparable": self.comparable,
            "reasons": list(self.reasons),
        }


def compare_formats(
    left: FormatEconomics, right: FormatEconomics, *, minimum_sample: int
) -> FormatComparison:
    """Report whether two formats can be compared at all, and why not if not.

    Deliberately returns no ranking and no winner. Section 9 forbids ranking
    formats from one video's outcome, and a function that returns "left" would
    be used for exactly that. What a caller gets is both summaries, the sample
    sizes, and the reasons a comparison would be unsound.
    """
    if isinstance(minimum_sample, bool) or not isinstance(minimum_sample, int) or minimum_sample < 1:
        raise FinanceError("minimum_sample must be a positive whole number")
    reasons: list[str] = []
    if left.period.period_id != right.period.period_id:
        reasons.append(
            f"different periods: {left.period.period_id} and {right.period.period_id}"
        )
    if left.currency != right.currency:
        reasons.append(
            f"different currencies: {left.currency} and {right.currency}; nothing here "
            "converts one"
        )
    for summary in (left, right):
        if summary.sample_size < minimum_sample:
            reasons.append(
                f"{summary.format_id}: {summary.sample_size} video(s), below the "
                f"{minimum_sample} this comparison requires"
            )
        if summary.missing:
            reasons.append(
                f"{summary.format_id}: {len(summary.missing)} missing financial "
                "measurement(s)"
            )
    return FormatComparison(
        left=left,
        right=right,
        minimum_sample=minimum_sample,
        comparable=not reasons,
        reasons=tuple(reasons),
    )


@dataclass(frozen=True)
class ProfitabilitySummary:
    """Known revenue, known cost and observed contribution - never a verdict.

    There is no `is_profitable` and no profit score. Section 22 says an
    incomplete picture may not be labelled profitable, and section 23 forbids
    reducing the company to one number. What this offers instead is
    `statement()`, which says what was observed and over what.
    """

    label: str
    period: FinancialPeriod
    known_revenue: Money
    known_cost: Money
    observed_contribution: Money
    sample_size: int
    cost_records: int
    revenue_records: int
    missing: tuple[str, ...]
    caveats: tuple[str, ...]

    @property
    def currency(self) -> str:
        return self.period.currency

    @property
    def is_complete(self) -> bool:
        return not self.missing

    def statement(self) -> str:
        """One sentence a human can quote without over-claiming."""
        qualifier = (
            "over complete records"
            if self.is_complete
            else f"over known records, with {len(self.missing)} measurement(s) missing"
        )
        return (
            f"{self.label}: observed contribution {self.observed_contribution} "
            f"{qualifier} for {self.period.label} "
            f"({self.revenue_records} revenue record(s), {self.cost_records} cost "
            f"record(s), sample size {self.sample_size})"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "period": self.period.to_dict(),
            "known_revenue": self.known_revenue.to_dict(),
            "known_cost": self.known_cost.to_dict(),
            "observed_contribution": self.observed_contribution.to_dict(),
            "sample_size": self.sample_size,
            "cost_records": self.cost_records,
            "revenue_records": self.revenue_records,
            "missing": list(self.missing),
            "caveats": list(self.caveats),
            "statement": self.statement(),
        }


def profitability(
    label: str,
    period: FinancialPeriod,
    summaries: Iterable[DeliverableEconomics],
    *,
    extra_missing: Iterable[str] = (),
) -> ProfitabilitySummary:
    """Roll deliverable summaries into one qualified profitability statement."""
    items = tuple(summaries)
    zero = period.zero()
    revenue = zero
    cost = zero
    missing: list[str] = [str(item) for item in extra_missing]
    caveats: list[str] = []
    cost_records = 0
    revenue_records = 0
    for item in items:
        if item.period.period_id != period.period_id:
            raise FinanceError(
                f"profitability {label!r}: {item.subject.key} covers period "
                f"{item.period.period_id}, not {period.period_id}"
            )
        period.assert_currency_matches(item.total_cost, "summary total cost")
        revenue = revenue + item.gross_revenue
        cost = cost + item.total_cost
        cost_records += item.cost_records
        revenue_records += item.revenue_records
        missing.extend(item.missing)
        caveats.extend(item.caveats)
    if not items:
        missing.append(f"no deliverable summaries supplied for {label!r}")
    return ProfitabilitySummary(
        label=label,
        period=period,
        known_revenue=revenue,
        known_cost=cost,
        observed_contribution=revenue - cost,
        sample_size=len(items),
        cost_records=cost_records,
        revenue_records=revenue_records,
        missing=tuple(dict.fromkeys(missing)),
        caveats=tuple(dict.fromkeys(caveats)),
    )


def ai_cost_efficiency(
    period: FinancialPeriod,
    priced_by_outcome: Mapping[str, Money | None],
    counts: OutcomeCounts,
) -> dict[str, Any]:
    """AI cost per attempt, per accepted and per rejected task.

    `priced_by_outcome` maps an outcome name to what that outcome's AI usage was
    priced at, or `None` where no rate covered it. A `None` anywhere makes the
    corresponding per-unit figure `None` too: section 19's "do not infer money
    from token counts without a RateCard", carried through the arithmetic rather
    than restated in a docstring.
    """
    result: dict[str, Any] = {"period": period.period_id, "currency": period.currency}
    total: Money | None = period.zero()
    for name in ("accepted", "rejected", "abandoned"):
        amount = priced_by_outcome.get(name)
        result[f"{name}_cost"] = amount
        if amount is None:
            total = None
        elif total is not None:
            total = total + period.assert_currency_matches(amount, f"{name} AI cost")
    result["total_cost"] = total
    result["attempted"] = counts.attempted
    result["cost_per_attempt"] = (
        total.divided_by(counts.attempted)
        if total is not None and counts.attempted
        else None
    )
    result["cost_per_accepted_task"] = (
        total.divided_by(counts.accepted) if total is not None and counts.accepted else None
    )
    rejected_cost = priced_by_outcome.get("rejected")
    result["cost_per_rejected_task"] = (
        rejected_cost.divided_by(counts.rejected)
        if rejected_cost is not None and counts.rejected
        else None
    )
    result["unknown"] = tuple(
        sorted(name for name in ("accepted", "rejected", "abandoned")
               if priced_by_outcome.get(name) is None)
    )
    return result


def research_cost_efficiency(
    period: FinancialPeriod,
    cost: Money | None,
    *,
    unique_candidates: int | None = None,
    screened_in: int | None = None,
    promoted_sources: int | None = None,
    dossiers: int | None = None,
) -> dict[str, Any]:
    """Research cost per candidate, per screened-in candidate, per promoted source.

    The counts come from the research subsystem's own measurements - a
    `BatchReport`'s progress figures - and are passed in rather than recomputed.
    A `None` count, or a `None` cost, yields a `None` ratio: there is no
    denominator this function will supply itself.
    """
    if cost is not None:
        period.assert_currency_matches(cost, "research cost")

    def per(count: int | None) -> Money | None:
        if cost is None or count is None or count <= 0:
            return None
        return cost.divided_by(count)

    return {
        "period": period.period_id,
        "currency": period.currency,
        "cost": cost,
        "cost_per_unique_candidate": per(unique_candidates),
        "cost_per_screened_in_candidate": per(screened_in),
        "cost_per_promoted_source": per(promoted_sources),
        "cost_per_opportunity_dossier": per(dossiers),
        "unknown": tuple(
            sorted(
                name
                for name, value in (
                    ("cost", cost),
                    ("unique_candidates", unique_candidates),
                    ("screened_in", screened_in),
                    ("promoted_sources", promoted_sources),
                    ("dossiers", dossiers),
                )
                if value is None
            )
        ),
    }

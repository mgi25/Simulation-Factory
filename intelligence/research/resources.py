"""What a search cost, recorded so the number still works when nobody counted tokens.

`ai_platform/usage.py` answers "what did an accepted deliverable cost?" for a
task attempt, and the shape of that answer is reused here almost exactly:
provider-supplied fields are `None` when not supplied, `None` propagates, and
the metrics defined over the half we always observe keep working when the half
we sometimes observe is absent.

What is *not* reused is the record. A `ResourceUsageRecord` requires a
`task_id`, a `ReasoningClass` and an `Outcome`, because it describes one attempt
at one task by one model. A research batch is not a task attempt: most of its
cost is a person with a browser reading forty video pages, there is no reasoning
class for that, and forcing one would either be a lie or a `NOT_APPLICABLE`
value on every record. So this is a sibling record with the same discipline, not
a subclass, and `UsageUnit` is imported rather than redefined (rule 15) because
which quantisation a unit count is in is one question with one answer.

## A total is None unless every record supplied the field

The strict rule, and it is the one that does not lie. Five records of which four
recorded review minutes sum to a number that is not the review minutes of the
batch; reported as a total, it understates the cost and it does so silently.
`summarise_cost` returns `None` for that field and names it in `missing`, with
how many records were short.

## Only a ratio whose two halves both exist

`cost_efficiency` computes cost-per-useful-outcome, which is the objective this
whole phase is named for. It refuses two divisions: one where the cost was never
measured, and one where the denominator is zero. A batch that promoted nothing
has no cost-per-promoted-source - it has a cost and a reason to worry, and
writing 0 or infinity in that cell would communicate neither.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar, Iterable, Mapping

from ai_platform.serde import as_date
from ai_platform.usage import UsageUnit
from intelligence.research.common import assert_research_id, assert_text
from intelligence.research.errors import ResearchError
from intelligence.research.funnel import CostTier

RESOURCE_MEASURES: tuple[str, ...] = (
    "manual_minutes",
    "reasoning_units",
    "tool_calls",
    "search_calls",
    "candidates_processed",
    "reference_analyses",
)
"""Everything a resource record may measure. Each one is optional on its own,
and a record measuring none of them is refused."""

COST_MEASURES: tuple[str, ...] = (
    "manual_minutes",
    "reasoning_units",
    "tool_calls",
    "search_calls",
)
"""The subset that is a *spend* rather than a count of work done. Only these
appear as the numerator of an efficiency ratio."""


@dataclass(frozen=True)
class ResearchResourceRecord:
    """One piece of research spend, charged to one batch at one funnel tier.

    `tier` rather than a free-text activity, so spend lands on the same six
    tiers `funnel.py` already defines and a reader can see where the money went:
    a batch spending four hours at tier 2 and twenty minutes at tier 3 has a
    screening problem, and a batch with the reverse has a queue nobody filtered.

    Every measurement is optional and missing stays missing. What is not
    optional is measuring *something*: a record with six `None`s is an assertion
    that work happened, and the ledger already has the batch history for that.
    """

    kind: ClassVar[str] = "research_resource"

    id: str
    batch_id: str
    recorded_on: dt.date
    recorded_by: str
    tier: CostTier
    manual_minutes: int | None = None
    reasoning_units: int | None = None
    usage_unit: UsageUnit = UsageUnit.UNKNOWN
    tool_calls: int | None = None
    search_calls: int | None = None
    candidates_processed: int | None = None
    reference_analyses: int | None = None
    note: str = ""

    def __post_init__(self) -> None:
        assert_research_id(self.id, "research resource record")
        assert_research_id(self.batch_id, "research batch")
        assert_text(self.recorded_by, "recorded_by (who is accounting for this)")
        if not isinstance(self.recorded_on, dt.date):
            raise ResearchError("a resource record must record the day it covers")
        if not isinstance(self.tier, CostTier):
            raise ResearchError(
                f"resource record {self.id!r}: tier must be a CostTier, so spend lands "
                "on the funnel the rest of this package already describes"
            )
        if not isinstance(self.usage_unit, UsageUnit):
            raise ResearchError(
                f"resource record {self.id!r}: usage_unit must be a UsageUnit"
            )
        for name in RESOURCE_MEASURES:
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int):
                raise ResearchError(
                    f"resource record {self.id!r}: {name} must be a whole number or "
                    f"None, got {value!r}"
                )
            if value < 0:
                raise ResearchError(
                    f"resource record {self.id!r}: {name} cannot be negative, got {value}"
                )
        if not self.measured:
            raise ResearchError(
                f"resource record {self.id!r} measures nothing. Leave the fields you did "
                f"not measure as None, but record at least one of {', '.join(RESOURCE_MEASURES)} "
                "- a record with no measurement says only that work happened, which the "
                "batch history already says."
            )
        if self.reasoning_units is not None and self.usage_unit is UsageUnit.UNKNOWN:
            raise ResearchError(
                f"resource record {self.id!r} counts {self.reasoning_units} reasoning "
                "units in an unknown unit. A count nobody can name the quantisation of "
                "cannot be added to another one - set usage_unit, or leave the count out."
            )

    @property
    def measured(self) -> tuple[str, ...]:
        return tuple(name for name in RESOURCE_MEASURES if getattr(self, name) is not None)

    @property
    def unmeasured(self) -> tuple[str, ...]:
        return tuple(name for name in RESOURCE_MEASURES if getattr(self, name) is None)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResearchResourceRecord:
        return cls(
            id=data["id"],
            batch_id=data["batch_id"],
            recorded_on=as_date(data["recorded_on"], "recorded_on"),
            recorded_by=data["recorded_by"],
            tier=CostTier(data["tier"]),
            manual_minutes=data.get("manual_minutes"),
            reasoning_units=data.get("reasoning_units"),
            usage_unit=UsageUnit(data.get("usage_unit", "unknown")),
            tool_calls=data.get("tool_calls"),
            search_calls=data.get("search_calls"),
            candidates_processed=data.get("candidates_processed"),
            reference_analyses=data.get("reference_analyses"),
            note=data.get("note", ""),
        )


@dataclass(frozen=True)
class TierCost:
    """What one funnel tier consumed. Same None rule, applied per tier."""

    tier: CostTier
    records: int
    manual_minutes: int | None
    reasoning_units: int | None
    tool_calls: int | None
    search_calls: int | None


@dataclass(frozen=True)
class ResearchCost:
    """Everything one batch spent, with the fields nobody measured named.

    `missing` is the field that keeps the rest honest. A batch report showing
    `manual_minutes: None` and nothing else has told the reader that the number
    is absent; one that also says *how many records were short* has told them
    whether it is a gap or an oversight.
    """

    records: int
    manual_minutes: int | None = None
    reasoning_units: int | None = None
    usage_unit: UsageUnit = UsageUnit.UNKNOWN
    tool_calls: int | None = None
    search_calls: int | None = None
    candidates_processed: int | None = None
    reference_analyses: int | None = None
    by_tier: tuple[TierCost, ...] = ()
    missing: tuple[str, ...] = ()

    @property
    def measured(self) -> tuple[str, ...]:
        return tuple(name for name in RESOURCE_MEASURES if getattr(self, name) is not None)

    def measure(self, name: str) -> int | None:
        if name not in RESOURCE_MEASURES:
            raise ResearchError(
                f"unknown research measure {name!r}; this cost holds {', '.join(RESOURCE_MEASURES)}"
            )
        return getattr(self, name)


def summarise_cost(records: Iterable[ResearchResourceRecord]) -> ResearchCost:
    """Add up what every record supplied, and refuse to add up what they did not.

    Pure. A field is summed only when *every* record in the batch supplied it;
    otherwise the total is `None` and `missing` says how many were short. The
    reasoning-unit total additionally requires every record to be in one unit,
    the same refusal `ai_platform.usage.UsageLedger.summarise` makes: two
    quantisations added together produce a plausible number that is not a
    measurement of anything.
    """
    items = tuple(records)
    totals: dict[str, int | None] = {}
    missing: list[str] = []
    if not items:
        # One line rather than six. "Nobody wrote a resource record" is a single
        # fact about the batch, and repeating it per field buries the five other
        # absences the report is trying to show.
        totals = {name: None for name in RESOURCE_MEASURES}
        missing.append(
            "no resource record was written for this batch, so nothing it cost is known"
        )
    for name in RESOURCE_MEASURES if items else ():
        values = [getattr(record, name) for record in items]
        absent = sum(1 for value in values if value is None)
        if absent:
            totals[name] = None
            missing.append(
                f"{name}: {absent} of {len(items)} resource record(s) did not measure it"
            )
        else:
            totals[name] = sum(values)

    units_seen = sorted(
        {record.usage_unit.value for record in items if record.reasoning_units is not None}
    )
    if len(units_seen) > 1:
        # Two quantisations in one batch: the sum would be arithmetic over
        # incomparable numbers, so there is no total to report.
        totals["reasoning_units"] = None
        unit = UsageUnit.UNKNOWN
        missing.append(
            f"reasoning_units: the batch mixes usage units ({', '.join(units_seen)}), "
            "and two quantisations cannot be added"
        )
    elif units_seen:
        unit = UsageUnit(units_seen[0])
    else:
        unit = UsageUnit.UNKNOWN

    by_tier: list[TierCost] = []
    for tier in CostTier:
        tier_records = [record for record in items if record.tier is tier]
        if not tier_records:
            continue
        tier_totals: dict[str, int | None] = {}
        for name in COST_MEASURES:
            values = [getattr(record, name) for record in tier_records]
            tier_totals[name] = (
                None if any(value is None for value in values) else sum(values)
            )
        by_tier.append(
            TierCost(
                tier=tier,
                records=len(tier_records),
                manual_minutes=tier_totals["manual_minutes"],
                reasoning_units=tier_totals["reasoning_units"],
                tool_calls=tier_totals["tool_calls"],
                search_calls=tier_totals["search_calls"],
            )
        )

    return ResearchCost(
        records=len(items),
        manual_minutes=totals["manual_minutes"],
        reasoning_units=totals["reasoning_units"],
        usage_unit=unit,
        tool_calls=totals["tool_calls"],
        search_calls=totals["search_calls"],
        candidates_processed=totals["candidates_processed"],
        reference_analyses=totals["reference_analyses"],
        by_tier=tuple(by_tier),
        missing=tuple(missing),
    )


class Denominator(Enum):
    """The four "useful outcome" counts research cost is divided by.

    Ordered by how much each one costs to produce, which is also the order in
    which the ratios get interesting: cost per unique candidate says whether
    discovery is efficient, and cost per opportunity says whether the whole
    funnel is.
    """

    UNIQUE_CANDIDATE = "unique_candidate"
    SCREENED_IN_CANDIDATE = "screened_in_candidate"
    PROMOTED_SOURCE = "promoted_source"
    OPPORTUNITY = "opportunity"


@dataclass(frozen=True)
class CostRatio:
    """One cost per one useful outcome, or the reason there is no such number."""

    cost: str
    per: str
    value: float | None = None
    unavailable: str = ""

    @property
    def is_available(self) -> bool:
        return self.value is not None

    @property
    def label(self) -> str:
        return f"{self.cost}_per_{self.per}"


@dataclass(frozen=True)
class CostEfficiency:
    """Every cost-per-outcome ratio the measurements supported, and the rest named.

    This is the phase objective - minimum research cost per useful opportunity -
    as a table. It is deliberately not a single score: a batch can be cheap per
    candidate and ruinous per opportunity, and collapsing the two would hide the
    only comparison that changes what a research lead does next.
    """

    ratios: tuple[CostRatio, ...] = ()

    @property
    def computed(self) -> tuple[CostRatio, ...]:
        return tuple(r for r in self.ratios if r.is_available)

    @property
    def unavailable(self) -> tuple[str, ...]:
        return tuple(f"{r.label}: {r.unavailable}" for r in self.ratios if not r.is_available)

    def ratio(self, cost: str, per: str) -> CostRatio | None:
        for item in self.ratios:
            if item.cost == cost and item.per == per:
                return item
        return None


def cost_efficiency(
    cost: ResearchCost, denominators: Mapping[str, int]
) -> CostEfficiency:
    """Divide each measured cost by each useful-outcome count. Pure.

    Two refusals, and both produce a named absence rather than a number:

    - the cost was never measured, so there is no numerator;
    - the denominator is zero, so there is no ratio - a batch that promoted
      nothing does not have an infinite cost per promoted source, it has a cost
      and a question.

    `denominators` is supplied rather than derived, because the counts come from
    the candidate records and this module deliberately does not read them.
    """
    unknown = sorted(set(denominators) - {d.value for d in Denominator})
    if unknown:
        raise ResearchError(
            f"unknown cost denominator(s) {', '.join(unknown)}; research cost is "
            f"divided by {', '.join(d.value for d in Denominator)}"
        )
    out: list[CostRatio] = []
    for measure in COST_MEASURES:
        total = cost.measure(measure)
        for denominator in Denominator:
            count = denominators.get(denominator.value)
            if total is None:
                reason = f"no {measure} was recorded for this batch"
            elif count is None:
                reason = f"the {denominator.value} count was not supplied"
            elif count <= 0:
                reason = f"this batch produced no {denominator.value} to divide by"
            else:
                out.append(
                    CostRatio(
                        cost=measure,
                        per=denominator.value,
                        value=round(total / count, 6),
                    )
                )
                continue
            out.append(CostRatio(cost=measure, per=denominator.value, unavailable=reason))
    return CostEfficiency(ratios=tuple(out))

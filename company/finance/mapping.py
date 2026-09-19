"""Measured usage times a supplied price, and nothing when there is no price.

## This module does not measure anything

`ai_platform.usage.ResourceUsageRecord` already counts tokens, tool calls,
retries and duration. `intelligence.research.resources.ResearchResourceRecord`
already counts manual minutes, reasoning units and search calls. Constitution
rule 15 stores a canonical fact once, so nothing here recounts either of them:
a `ResourceCostMapping` is a *reference* to a measurement somebody else took,
plus the unit it should be priced in.

## Both record types are read duck-typed, never imported

`company/finance` imports nothing from `intelligence/` and nothing from the rest
of Company OS beyond `ai_platform` and `knowledge`, for the reason
`company/org_intelligence/research_evidence.py` gives: the boundary stays
one-way, so the measuring subsystems can move or be replaced without this
package noticing, and a caller holding a summary rather than a whole record can
still use it.

Every attribute read is named in the function that reads it, so an upstream
rename raises on the next run rather than quietly producing `None`.

## The whole point: missing price means unknown, not zero

`PricedUsage.amount` is `Money | None`. When the rate card has no rate for that
provider, unit and day, the amount is `None` and `unpriced_reason` says exactly
what is missing. Every summary downstream propagates that as a named gap.

The alternative - defaulting to zero - produces a cost report where an unpriced
provider looks free, which is the most expensive kind of wrong number a company
can have.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, ClassVar, Iterable


from .common import (
    SubjectRef,
    assert_day,
    assert_prose,
    assert_record_id,
    assert_ref,
    record_to_dict,
)
from .costs import CostCategory
from .errors import FinanceError
from .money import Money, as_decimal
from .rates import UNIT_EQUIVALENCE, CostRate, RateCard, RateUnit, UnpricedReason


class MeasureSource(Enum):
    """Which subsystem took the measurement this mapping prices."""

    USAGE_RECORD = "usage_record"  # ai_platform.usage.ResourceUsageRecord
    RESEARCH_RESOURCE = "research_resource"  # intelligence.research ResearchResourceRecord
    MANUAL = "manual"  # a human recorded the quantity directly
    OTHER = "other"


@dataclass(frozen=True)
class ResourceCostMapping:
    """A measured quantity, the unit it prices in, and what took the measurement.

    Deliberately not a cost. It becomes one only if `price()` finds a rate, and
    the two-step shape is what keeps "we used 240,000 tokens" and "that was
    0.72 EUR" as separate, separately-checkable claims.
    """

    kind: ClassVar[str] = "resource_cost_mapping"

    mapping_id: str
    resource_ref: str
    measure: str
    quantity: Decimal
    unit: RateUnit
    provider: str
    category: CostCategory
    subject: SubjectRef
    measured_on: dt.date
    measure_source: MeasureSource = MeasureSource.MANUAL
    notes: str = ""

    def __post_init__(self) -> None:
        assert_record_id(self.mapping_id, "mapping_id")
        assert_ref(self.resource_ref, f"mapping {self.mapping_id!r} resource_ref")
        assert_prose(self.measure, f"mapping {self.mapping_id!r} measure")
        assert_ref(self.provider, f"mapping {self.mapping_id!r} provider")
        if not isinstance(self.unit, RateUnit):
            raise FinanceError(f"mapping {self.mapping_id!r}: unit must be a RateUnit")
        if not isinstance(self.category, CostCategory):
            raise FinanceError(
                f"mapping {self.mapping_id!r}: category must be a CostCategory"
            )
        if not isinstance(self.subject, SubjectRef):
            raise FinanceError(f"mapping {self.mapping_id!r}: subject must be a SubjectRef")
        if not isinstance(self.measure_source, MeasureSource):
            raise FinanceError(
                f"mapping {self.mapping_id!r}: measure_source must be a MeasureSource"
            )
        object.__setattr__(self, "measured_on", assert_day(self.measured_on, "measured_on"))
        object.__setattr__(
            self, "quantity", as_decimal(self.quantity, f"mapping {self.mapping_id!r} quantity")
        )
        if self.quantity < 0:
            raise FinanceError(
                f"mapping {self.mapping_id!r}: a measured quantity is not negative, got "
                f"{self.quantity}"
            )
        if not isinstance(self.notes, str):
            raise FinanceError(f"mapping {self.mapping_id!r}: notes must be a string")

    # -- pricing -----------------------------------------------------------

    def price(self, card: RateCard, *, on: Any = None) -> PricedUsage:
        """Apply the rate effective on `on`, or report that there is none.

        `on` defaults to the day the measurement was taken, which is the day the
        price should be the one in force - pricing March's tokens at April's
        rate is the restatement `rates.py` exists to prevent.
        """
        day = assert_day(on, "on") if on is not None else self.measured_on
        rate = self._find(card, day)
        if rate is None:
            return PricedUsage(
                mapping=self,
                amount=None,
                rate_id="",
                priced_on=day,
                unpriced_reason=UnpricedReason(
                    provider=self.provider,
                    unit=self.unit,
                    on=day,
                    detail=(
                        "supply a CostRate for this provider and unit covering this date; "
                        "an unpriced quantity stays unknown and is never counted as zero"
                    ),
                ),
            )
        quantity = self.quantity
        if rate.unit is not self.unit:
            quantity = quantity / Decimal(UNIT_EQUIVALENCE[(self.unit, rate.unit)])
        return PricedUsage(
            mapping=self,
            amount=rate.price(quantity, on=day),
            rate_id=rate.rate_id,
            priced_on=day,
            unpriced_reason=None,
        )

    def _find(self, card: RateCard, day: dt.date) -> CostRate | None:
        """The rate for this exact unit, or one quoted at an equivalent scale."""
        direct = card.rate_for(self.provider, self.unit, on=day, category=self.category)
        if direct is not None:
            return direct
        for (small, large), _factor in UNIT_EQUIVALENCE.items():
            if small is self.unit:
                scaled = card.rate_for(
                    self.provider, large, on=day, category=self.category
                )
                if scaled is not None:
                    return scaled
        return None

    def to_dict(self) -> dict[str, Any]:
        return record_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResourceCostMapping:
        return cls(
            mapping_id=data["mapping_id"],
            resource_ref=data["resource_ref"],
            measure=data["measure"],
            quantity=data["quantity"],
            unit=RateUnit(data["unit"]),
            provider=data["provider"],
            category=CostCategory(data["category"]),
            subject=SubjectRef.from_dict(data["subject"]),
            measured_on=assert_day(data["measured_on"], "measured_on"),
            measure_source=MeasureSource(data.get("measure_source", "manual")),
            notes=data.get("notes", ""),
        )


@dataclass(frozen=True)
class PricedUsage:
    """A mapping after pricing: an amount, or a named reason there is none."""

    mapping: ResourceCostMapping
    amount: Money | None
    rate_id: str
    priced_on: dt.date
    unpriced_reason: UnpricedReason | None

    def __post_init__(self) -> None:
        if (self.amount is None) == (self.unpriced_reason is None):
            raise FinanceError(
                "a priced usage has exactly one of an amount and an unpriced reason; "
                "anything else is an unknown pretending to be a number, or the reverse"
            )

    @property
    def is_priced(self) -> bool:
        return self.amount is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "mapping_id": self.mapping.mapping_id,
            "amount": self.amount.to_dict() if self.amount else None,
            "rate_id": self.rate_id,
            "priced_on": self.priced_on.isoformat(),
            "unpriced_reason": str(self.unpriced_reason) if self.unpriced_reason else "",
        }


@dataclass(frozen=True)
class PricedUsageSet:
    """Many priced mappings, with the unpriced ones kept visible.

    `total` is the sum of what *could* be priced, and `unpriced` is everything
    that could not. A caller that reads only `total` gets an understatement, so
    `is_complete` exists and every summary in this package checks it.
    """

    priced: tuple[PricedUsage, ...]
    currency: str

    @property
    def total(self) -> Money:
        """Sum of the priced amounts. Zero when nothing priced - see `is_complete`."""
        running = Money.zero(self.currency)
        for item in self.priced:
            if item.amount is not None:
                running = running + item.amount
        return running

    @property
    def unpriced(self) -> tuple[PricedUsage, ...]:
        return tuple(item for item in self.priced if not item.is_priced)

    @property
    def is_complete(self) -> bool:
        """True when every mapping found a rate. False makes `total` a floor."""
        return not self.unpriced

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(
            sorted(str(item.unpriced_reason) for item in self.unpriced if item.unpriced_reason)
        )


def price_all(
    mappings: Iterable[ResourceCostMapping], card: RateCard, *, currency: str, on: Any = None
) -> PricedUsageSet:
    """Price a set of mappings, keeping the unpriced ones in the result."""
    priced = tuple(mapping.price(card, on=on) for mapping in mappings)
    for item in priced:
        if item.amount is not None and item.amount.currency != currency:
            raise FinanceError(
                f"mapping {item.mapping.mapping_id!r} priced in {item.amount.currency}, "
                f"but this set reports {currency}. Nothing here converts a currency"
            )
    return PricedUsageSet(priced=priced, currency=currency)


# -- reading the measuring subsystems, without importing them ---------------

# Attributes read off a ResourceUsageRecord. Named here so a rename upstream
# fails loudly on the next run instead of silently yielding an empty mapping set.
USAGE_ATTRIBUTES: tuple[str, ...] = (
    "task_id",
    "input_units",
    "output_units",
    "usage_unit",
    "tool_calls",
    "duration_s",
    "outcome",
    "reasoning_class",
)

# The same, for a ResearchResourceRecord.
RESEARCH_ATTRIBUTES: tuple[str, ...] = (
    "id",
    "batch_id",
    "tier",
    "manual_minutes",
    "reasoning_units",
    "usage_unit",
    "tool_calls",
    "search_calls",
    "recorded_on",
)

# The usage_unit values that are really a token count. Anything else - a
# character or word count, or the provider exposing nothing - cannot be priced
# per token, and produces no mapping rather than a converted guess.
_TOKEN_UNITS = frozenset({"token"})


def _unit_value(usage_unit: Any) -> str:
    return getattr(usage_unit, "value", usage_unit)


def mappings_from_usage(
    record: Any,
    *,
    subject: SubjectRef,
    provider: str,
    measured_on: Any,
    id_prefix: str,
    include_time: bool = False,
) -> tuple[ResourceCostMapping, ...]:
    """Mappings for whatever a `ResourceUsageRecord` actually measured.

    Reads `task_id`, `input_units`, `output_units`, `usage_unit`, `tool_calls`
    and `duration_s`. A measure the provider did not expose is `None` upstream
    and produces no mapping here: an absent token count becomes an absent cost,
    not a zero one.

    Token mappings are produced only when `usage_unit` is TOKEN. A character
    count priced per token would be a unit conversion nobody supplied.
    """
    try:
        task_id = record.task_id
        input_units = record.input_units
        output_units = record.output_units
        usage_unit = record.usage_unit
        tool_calls = record.tool_calls
        duration_s = record.duration_s
    except AttributeError as exc:
        raise FinanceError(
            f"a usage record must expose {', '.join(USAGE_ATTRIBUTES)}; this one is "
            f"missing {exc}"
        ) from exc
    day = assert_day(measured_on, "measured_on")
    out: list[ResourceCostMapping] = []
    is_tokens = _unit_value(usage_unit) in _TOKEN_UNITS
    if is_tokens:
        for measure, value in (("input_units", input_units), ("output_units", output_units)):
            if value is None:
                continue
            out.append(
                ResourceCostMapping(
                    mapping_id=f"{id_prefix}.{measure}",
                    resource_ref=task_id,
                    measure=f"{measure} reported by the provider for task {task_id}",
                    quantity=value,
                    unit=RateUnit.TOKEN,
                    provider=provider,
                    category=CostCategory.AI_REASONING,
                    subject=subject,
                    measured_on=day,
                    measure_source=MeasureSource.USAGE_RECORD,
                )
            )
    if tool_calls is not None:
        out.append(
            ResourceCostMapping(
                mapping_id=f"{id_prefix}.tool_calls",
                resource_ref=task_id,
                measure=f"tool calls observed for task {task_id}",
                quantity=tool_calls,
                unit=RateUnit.REQUEST,
                provider=provider,
                category=CostCategory.API,
                subject=subject,
                measured_on=day,
                measure_source=MeasureSource.USAGE_RECORD,
            )
        )
    if include_time and duration_s is not None:
        out.append(
            ResourceCostMapping(
                mapping_id=f"{id_prefix}.compute_seconds",
                resource_ref=task_id,
                measure=f"wall-clock seconds observed for task {task_id}",
                quantity=Decimal(str(duration_s)),
                unit=RateUnit.COMPUTE_SECOND,
                provider=provider,
                category=CostCategory.COMPUTE,
                subject=subject,
                measured_on=day,
                measure_source=MeasureSource.USAGE_RECORD,
            )
        )
    return tuple(out)


def mappings_from_research_resource(
    record: Any,
    *,
    subject: SubjectRef,
    provider: str,
    id_prefix: str,
    labour_provider: str = "",
) -> tuple[ResourceCostMapping, ...]:
    """Mappings for what a `ResearchResourceRecord` measured.

    Reads `id`, `batch_id`, `manual_minutes`, `reasoning_units`, `usage_unit`,
    `tool_calls`, `search_calls` and `recorded_on`. Research already decided what
    a tier means and what was spent at it; this turns those counts into priceable
    quantities and nothing more.

    `labour_provider` is separate because manual minutes are priced from an
    internal labour rate, not from the AI provider's price list, and defaulting
    one to the other would put a token price on a person's time.
    """
    try:
        record_id = record.id
        batch_id = record.batch_id
        manual_minutes = record.manual_minutes
        reasoning_units = record.reasoning_units
        usage_unit = record.usage_unit
        tool_calls = record.tool_calls
        search_calls = record.search_calls
        recorded_on = record.recorded_on
    except AttributeError as exc:
        raise FinanceError(
            f"a research resource record must expose {', '.join(RESEARCH_ATTRIBUTES)}; "
            f"this one is missing {exc}"
        ) from exc
    day = assert_day(recorded_on, "recorded_on")
    out: list[ResourceCostMapping] = []
    if reasoning_units is not None and _unit_value(usage_unit) in _TOKEN_UNITS:
        out.append(
            ResourceCostMapping(
                mapping_id=f"{id_prefix}.reasoning_units",
                resource_ref=record_id,
                measure=f"reasoning units recorded against research batch {batch_id}",
                quantity=reasoning_units,
                unit=RateUnit.TOKEN,
                provider=provider,
                category=CostCategory.AI_REASONING,
                subject=subject,
                measured_on=day,
                measure_source=MeasureSource.RESEARCH_RESOURCE,
            )
        )
    for measure, value in (("tool_calls", tool_calls), ("search_calls", search_calls)):
        if value is None:
            continue
        out.append(
            ResourceCostMapping(
                mapping_id=f"{id_prefix}.{measure}",
                resource_ref=record_id,
                measure=f"{measure} recorded against research batch {batch_id}",
                quantity=value,
                unit=RateUnit.REQUEST,
                provider=provider,
                category=CostCategory.RESEARCH,
                subject=subject,
                measured_on=day,
                measure_source=MeasureSource.RESEARCH_RESOURCE,
            )
        )
    if manual_minutes is not None:
        if not labour_provider:
            raise FinanceError(
                f"research record {record_id!r} measured {manual_minutes} manual minutes. "
                "Pass labour_provider to price them from an internal labour rate - a "
                "person's time is not billed at the AI provider's price"
            )
        out.append(
            ResourceCostMapping(
                mapping_id=f"{id_prefix}.manual_minutes",
                resource_ref=record_id,
                measure=f"manual minutes recorded against research batch {batch_id}",
                quantity=manual_minutes,
                unit=RateUnit.MINUTE,
                provider=labour_provider,
                category=CostCategory.EMPLOYEE_TIME,
                subject=subject,
                measured_on=day,
                measure_source=MeasureSource.RESEARCH_RESOURCE,
            )
        )
    return tuple(out)

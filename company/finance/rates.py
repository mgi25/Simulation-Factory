"""Prices, as dated data rather than constants in code.

## No provider price is hardcoded, anywhere

Section 5 is blunt about it and the reason is arithmetic: a token price written
into a module is a price that was true on the day somebody typed it, and every
historical cost recomputed after it changes is silently restated. So there is no
price table in this package. A `CostRate` is a record a human supplies with a
source, and a cost computed without one is unknown rather than estimated.

## Rates are versioned by time, and history is never overwritten

A rate carries `effective_from` and an optional `effective_to`. Superseding a
price does not edit the old record - `supersede()` returns *two* records, the
old one closed on a date and the new one opened the day after, so a cost from
March is still priced with March's rate after April's arrives.

`RateCard.rate_for` refuses to guess: asked for a price on a day no rate covers,
it returns `None` and `unpriced_reason` says which provider, which unit and
which day. That `None` is what propagates into `mapping.py`, and it is why an AI
cost with no pricing comes out as unknown instead of zero.

## Overlaps are an integrity failure, not a resolution rule

Two rates for the same provider and unit covering the same day is not a
tie-break problem to solve with "latest wins" - it is two people having recorded
two different prices, and picking one hides that. `RateCard.overlaps()` reports
it and `integrity.py` fails on it.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any, ClassVar, Iterable

from knowledge.company_os.records import Evidence

from .common import (
    assert_day,
    assert_evidence_backed,
    assert_prose,
    assert_record_id,
    assert_ref,
    evidence_tuple,
    optional_day,
    record_to_dict,
)
from .costs import CostCategory
from .errors import FinanceError
from .money import Money


class RateUnit(Enum):
    """What one unit of the priced thing is. Section 6's list, one value each."""

    TOKEN = "token"
    MILLION_TOKENS = "million_tokens"
    REQUEST = "request"
    MINUTE = "minute"
    HOUR = "hour"
    COMPUTE_SECOND = "compute_second"
    RENDER_MINUTE = "render_minute"
    GB_MONTH = "gb_month"
    FIXED_SUBSCRIPTION_PERIOD = "fixed_subscription_period"


# Units that measure the same physical thing at two scales, so a quantity
# measured in one can be priced by a rate quoted in the other. The factor is how
# many of the key unit make one of the value unit. Deliberately tiny: these two
# pairs are real conversions between units of count and time, not currency
# conversion, which this package refuses to do at all.
UNIT_EQUIVALENCE: dict[tuple[RateUnit, RateUnit], str] = {
    (RateUnit.TOKEN, RateUnit.MILLION_TOKENS): "1000000",
    (RateUnit.MINUTE, RateUnit.HOUR): "60",
}


@dataclass(frozen=True)
class CostRate:
    """One price, for one unit, from one provider, over one date range."""

    kind: ClassVar[str] = "rate"

    rate_id: str
    provider: str
    category: CostCategory
    unit: RateUnit
    amount: Money
    effective_from: dt.date
    source: str
    evidence: tuple[Evidence, ...]
    recorded_by: str
    recorded_on: dt.date
    effective_to: dt.date | None = None
    supersedes: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        assert_record_id(self.rate_id, "rate_id")
        assert_ref(self.provider, f"rate {self.rate_id!r} provider")
        assert_ref(self.source, f"rate {self.rate_id!r} source")
        assert_prose(self.recorded_by, f"rate {self.rate_id!r} recorded_by")
        if not isinstance(self.category, CostCategory):
            raise FinanceError(f"rate {self.rate_id!r}: category must be a CostCategory")
        if not isinstance(self.unit, RateUnit):
            raise FinanceError(
                f"rate {self.rate_id!r}: unit must be a RateUnit, got {self.unit!r}"
            )
        if not isinstance(self.amount, Money):
            raise FinanceError(f"rate {self.rate_id!r}: amount must be Money")
        if self.amount.is_negative:
            raise FinanceError(
                f"rate {self.rate_id!r}: a price is not negative ({self.amount})"
            )
        object.__setattr__(
            self, "effective_from", assert_day(self.effective_from, "effective_from")
        )
        object.__setattr__(
            self, "effective_to", optional_day(self.effective_to, "effective_to")
        )
        object.__setattr__(self, "recorded_on", assert_day(self.recorded_on, "recorded_on"))
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise FinanceError(
                f"rate {self.rate_id!r}: effective_to {self.effective_to.isoformat()} is "
                f"before effective_from {self.effective_from.isoformat()}"
            )
        if self.supersedes:
            assert_record_id(self.supersedes, f"rate {self.rate_id!r} supersedes")
        if not isinstance(self.notes, str):
            raise FinanceError(f"rate {self.rate_id!r}: notes must be a string")
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))
        assert_evidence_backed(
            self.evidence,
            f"rate {self.rate_id!r} evidence",
            "a price with no source is a price somebody recalled, and every cost "
            "computed from it inherits the recollection",
        )

    # -- reading -----------------------------------------------------------

    @property
    def currency(self) -> str:
        return self.amount.currency

    @property
    def key(self) -> tuple[str, str, str]:
        """What makes two rates the same price line: provider, category, unit."""
        return (self.provider, self.category.value, self.unit.value)

    def covers(self, day: Any) -> bool:
        value = assert_day(day, "day")
        if value < self.effective_from:
            return False
        return self.effective_to is None or value <= self.effective_to

    def overlaps(self, other: CostRate) -> bool:
        if self.key != other.key:
            return False
        left_end = self.effective_to or dt.date.max
        right_end = other.effective_to or dt.date.max
        return self.effective_from <= right_end and other.effective_from <= left_end

    def price(self, quantity: Any, *, on: Any) -> Money:
        """Cost of `quantity` units at this rate, refusing a day it does not cover.

        Section 26 lists "rate used outside its effective dates" as an integrity
        failure. It is enforced here too, because the call that would produce a
        wrong number is this one.
        """
        day = assert_day(on, "on")
        if not self.covers(day):
            raise FinanceError(
                f"rate {self.rate_id!r} covers "
                f"{self.effective_from.isoformat()} to "
                f"{(self.effective_to.isoformat() if self.effective_to else 'open')}, "
                f"not {day.isoformat()}. Pricing outside a rate's dates restates history"
            )
        return self.amount * quantity

    def to_dict(self) -> dict[str, Any]:
        return record_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CostRate:
        return cls(
            rate_id=data["rate_id"],
            provider=data["provider"],
            category=CostCategory(data["category"]),
            unit=RateUnit(data["unit"]),
            amount=Money.from_dict(data["amount"], "rate amount"),
            effective_from=assert_day(data["effective_from"], "effective_from"),
            source=data["source"],
            evidence=evidence_tuple(data.get("evidence")),
            recorded_by=data["recorded_by"],
            recorded_on=assert_day(data["recorded_on"], "recorded_on"),
            effective_to=optional_day(data.get("effective_to"), "effective_to"),
            supersedes=data.get("supersedes", ""),
            notes=data.get("notes", ""),
        )


def supersede(
    old: CostRate, new: CostRate, *, last_day: Any
) -> tuple[CostRate, CostRate]:
    """Close `old` on `last_day` and open `new` the day after, as two records.

    Returns both, and the caller stores both. Nothing is edited in place: the
    closed rate is a new value with `effective_to` set, and the old object the
    caller passed in is unchanged, so a price that was true in March stays
    readable in April.
    """
    if old.key != new.key:
        raise FinanceError(
            f"rate {new.rate_id!r} prices {new.key} and cannot supersede {old.key}"
        )
    day = assert_day(last_day, "last_day")
    if day < old.effective_from:
        raise FinanceError(
            f"rate {old.rate_id!r} cannot end {day.isoformat()}, before it began "
            f"{old.effective_from.isoformat()}"
        )
    closed = replace(old, effective_to=day)
    opened = replace(
        new, effective_from=day + dt.timedelta(days=1), supersedes=old.rate_id
    )
    return closed, opened


@dataclass(frozen=True)
class UnpricedReason:
    """Why a quantity has no monetary cost. Never a zero pretending to be one."""

    provider: str
    unit: RateUnit
    on: dt.date
    detail: str

    def __str__(self) -> str:
        return (
            f"no rate for {self.provider} per {self.unit.value} effective "
            f"{self.on.isoformat()}: {self.detail}"
        )


class RateCard:
    """Every rate the company has recorded, queried by provider, unit and date."""

    def __init__(self, rates: Iterable[CostRate] = ()) -> None:
        self._rates: tuple[CostRate, ...] = tuple(
            sorted(rates, key=lambda rate: (rate.key, rate.effective_from, rate.rate_id))
        )
        seen: set[str] = set()
        for rate in self._rates:
            if rate.rate_id in seen:
                raise FinanceError(f"duplicate rate id {rate.rate_id!r} in one rate card")
            seen.add(rate.rate_id)

    def __len__(self) -> int:
        return len(self._rates)

    def __iter__(self):
        return iter(self._rates)

    @property
    def rates(self) -> tuple[CostRate, ...]:
        """Every rate, in a stable order. History included, never pruned."""
        return self._rates

    def with_rate(self, rate: CostRate) -> RateCard:
        """A new card carrying one more rate. The card itself is immutable."""
        return RateCard(self._rates + (rate,))

    def get(self, rate_id: str) -> CostRate | None:
        for rate in self._rates:
            if rate.rate_id == rate_id:
                return rate
        return None

    def history(self, provider: str, unit: RateUnit, category: CostCategory) -> tuple[CostRate, ...]:
        """Every rate ever recorded for one price line, oldest first."""
        key = (provider, category.value, unit.value)
        return tuple(rate for rate in self._rates if rate.key == key)

    def rate_for(
        self,
        provider: str,
        unit: RateUnit,
        *,
        on: Any,
        category: CostCategory | None = None,
    ) -> CostRate | None:
        """The rate effective on `on`, or None. Never the nearest, never the latest."""
        day = assert_day(on, "on")
        matches = [
            rate
            for rate in self._rates
            if rate.provider == provider
            and rate.unit is unit
            and (category is None or rate.category is category)
            and rate.covers(day)
        ]
        if not matches:
            return None
        if len(matches) > 1:
            raise FinanceError(
                f"{len(matches)} rates cover {provider} per {unit.value} on "
                f"{day.isoformat()}: "
                + ", ".join(sorted(rate.rate_id for rate in matches))
                + ". Two recorded prices for one day is a correction somebody owes, not "
                "a tie this code may break"
            )
        return matches[0]

    def overlaps(self) -> tuple[str, ...]:
        """Pairs of rates that price the same thing on the same day, sorted."""
        problems: list[str] = []
        for index, left in enumerate(self._rates):
            for right in self._rates[index + 1 :]:
                if left.overlaps(right):
                    problems.append(
                        f"rates {left.rate_id!r} and {right.rate_id!r} both price "
                        f"{left.provider} per {left.unit.value} over overlapping dates"
                    )
        return tuple(sorted(problems))

    def currencies(self) -> tuple[str, ...]:
        return tuple(sorted({rate.currency for rate in self._rates}))


def load_rate_card(path: str | Path) -> RateCard:
    """Read a rate card from a JSON file somebody wrote by hand.

    The file is a list of rate objects, or an object with a `rates` key holding
    one. Every field `CostRate` requires is required here too - id, provider,
    category, unit, amount, currency, effective dates, source and evidence -
    because a loader that filled in a default would be a price this package
    invented.

    There is no fetch, no URL and no provider client, and there is not going to
    be: a price that arrives over the network is a price nobody reviewed, and
    section 5 of the brief exists to keep pricing something a human recorded.
    """
    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except OSError as exc:
        raise FinanceError(f"cannot read rate card {source}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise FinanceError(f"{source}: rate card is not valid JSON: {exc}") from exc
    if isinstance(data, dict):
        data = data.get("rates", data)
    if not isinstance(data, list):
        raise FinanceError(
            f"{source}: a rate card is a list of rate objects, or an object with a "
            "'rates' key holding one"
        )
    rates: list[CostRate] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise FinanceError(f"{source}: rate {index} is not an object")
        try:
            rates.append(CostRate.from_dict(item))
        except (KeyError, TypeError, ValueError) as exc:
            raise FinanceError(f"{source}: rate {index} does not decode: {exc}") from exc
    return RateCard(rates)

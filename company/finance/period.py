"""The accounting window, and the rule that two windows are never silently one.

A cost in March and a revenue line in September are both real and comparing
them is a choice. This module exists so that the choice is visible in the type
rather than lost inside a sum: every summary in this package carries the
`FinancialPeriod` it covers, and asking a summary a question about a record
outside that period gets a refusal rather than a number.

## Inclusive on both ends

`start` and `end` are both inclusive, because a monthly period is January 1st
to January 31st in every document a human will compare this against. An
exclusive end would make the boundary correct and every off-by-one argument
about it permanent.

## The reporting currency belongs to the period, not the report

A period declares the currency its totals are expressed in. That is what turns
"do not silently convert" from a convention into a check: a cost in USD landing
in a EUR period is a mismatch the period notices, and the only two honest
answers - keep them apart, or convert with a dated rate observation - are both
the caller's to make.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, ClassVar


from .common import assert_day, assert_prose, assert_record_id, record_to_dict
from .errors import FinanceError
from .money import Money, assert_currency


@dataclass(frozen=True)
class FinancialPeriod:
    """One accounting window: when it starts, when it ends, what it reports in."""

    kind: ClassVar[str] = "period"

    period_id: str
    label: str
    start: dt.date
    end: dt.date
    currency: str
    notes: str = ""

    def __post_init__(self) -> None:
        assert_record_id(self.period_id, "period_id")
        assert_prose(self.label, "period label")
        object.__setattr__(self, "start", assert_day(self.start, "period start"))
        object.__setattr__(self, "end", assert_day(self.end, "period end"))
        object.__setattr__(self, "currency", assert_currency(self.currency))
        if self.end < self.start:
            raise FinanceError(
                f"period {self.period_id!r}: end {self.end.isoformat()} is before start "
                f"{self.start.isoformat()}; a window that runs backwards has no contents"
            )
        if not isinstance(self.notes, str):
            raise FinanceError(f"period {self.period_id!r}: notes must be a string")

    # -- reading -----------------------------------------------------------

    @property
    def days(self) -> int:
        """Length in days, both ends inclusive."""
        return (self.end - self.start).days + 1

    def contains(self, day: Any) -> bool:
        return self.start <= assert_day(day, "day") <= self.end

    def overlaps(self, other: FinancialPeriod) -> bool:
        return self.start <= other.end and other.start <= self.end

    def zero(self) -> Money:
        """The zero of this period's reporting currency."""
        return Money.zero(self.currency)

    def assert_currency_matches(self, amount: Money, what: str) -> Money:
        """Refuse an amount in a currency this period does not report in."""
        if not isinstance(amount, Money):
            raise FinanceError(f"{what}: expected Money, got {type(amount).__name__}")
        if amount.currency != self.currency:
            raise FinanceError(
                f"{what}: {amount.currency} does not match the reporting currency "
                f"{self.currency} of period {self.period_id!r}. Nothing here converts "
                "a currency on its own"
            )
        return amount

    def assert_contains(self, day: Any, what: str) -> dt.date:
        value = assert_day(day, what)
        if not self.contains(value):
            raise FinanceError(
                f"{what}: {value.isoformat()} falls outside period {self.period_id!r} "
                f"({self.start.isoformat()} to {self.end.isoformat()})"
            )
        return value

    def __str__(self) -> str:
        return (
            f"{self.label} ({self.start.isoformat()} to {self.end.isoformat()}, "
            f"{self.currency})"
        )

    # -- serialization -----------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return record_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FinancialPeriod:
        return cls(
            period_id=data["period_id"],
            label=data["label"],
            start=assert_day(data["start"], "period start"),
            end=assert_day(data["end"], "period end"),
            currency=data["currency"],
            notes=data.get("notes", ""),
        )


def same_period(left: FinancialPeriod, right: FinancialPeriod) -> bool:
    """True when two periods are the same window in the same currency."""
    return (
        left.start == right.start
        and left.end == right.end
        and left.currency == right.currency
    )


def assert_comparable(
    left: FinancialPeriod, right: FinancialPeriod, what: str
) -> None:
    """Refuse a comparison across two different windows.

    Section 2, as a call a reader can find: expenses and revenue from different
    periods are not compared without that being visible. Here it is visible as
    an exception naming both windows.
    """
    if not same_period(left, right):
        raise FinanceError(
            f"{what}: {left} and {right} are different accounting windows. Compare them "
            "deliberately, with both periods named in the output"
        )

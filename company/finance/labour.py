"""What an hour of somebody's time costs, when somebody has said so.

## No rate is ever inferred from a role

Section 21 says it twice over: do not assign salaries or rates to employees by
guessing. There is no table here mapping a role to a number, and no default. A
`LabourRate` exists because a human supplied it with evidence and a date range,
or it does not exist and the labour cost of that person's time is unknown.

## Cost and performance never meet

The workforce package measures how well somebody does something. This module
records what an hour costs. They are deliberately in different packages with no
reference between them, because the record that joins them is the one that turns
into a value ranking, and section 21 forbids exactly that: "employee performance
and cost remain separate. No value score."

So `LabourRate` has a subject and an amount and nothing about output. A caller
wanting cost per accepted deliverable gets it from `economics.py`, over records,
for a *deliverable* - never for a person.

## A rate is a `CostRate`, deliberately

An internal hourly rate is a price per unit of a thing, versioned by date, with
a source. That is what `rates.CostRate` already is, so this module builds one
rather than defining a parallel type with the same fields and a different name.
What it adds is the subject - which person or role the rate is for - and the
refusal to invent one.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, ClassVar

from knowledge.company_os.records import Evidence

from .common import (
    SubjectRef,
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
from .rates import CostRate, RateUnit

# The units an hour of work can be priced in. A labour rate quoted per token
# would be a category error, and this is where it is refused.
LABOUR_UNITS = frozenset({RateUnit.MINUTE, RateUnit.HOUR})


@dataclass(frozen=True)
class LabourRate:
    """An internal cost of time for one person or role, over one date range."""

    kind: ClassVar[str] = "labour_rate"

    rate_id: str
    subject: SubjectRef
    amount: Money
    unit: RateUnit
    effective_from: dt.date
    source: str
    evidence: tuple[Evidence, ...]
    recorded_by: str
    recorded_on: dt.date
    effective_to: dt.date | None = None
    is_contractor: bool = False
    notes: str = ""

    def __post_init__(self) -> None:
        assert_record_id(self.rate_id, "rate_id")
        if not isinstance(self.subject, SubjectRef):
            raise FinanceError(
                f"labour rate {self.rate_id!r}: subject must be a SubjectRef naming the "
                "person or role this rate is for"
            )
        if not isinstance(self.unit, RateUnit) or self.unit not in LABOUR_UNITS:
            raise FinanceError(
                f"labour rate {self.rate_id!r}: unit must be MINUTE or HOUR, got "
                f"{self.unit!r}. Time is priced per unit of time"
            )
        if not isinstance(self.amount, Money):
            raise FinanceError(f"labour rate {self.rate_id!r}: amount must be Money")
        if self.amount.is_negative:
            raise FinanceError(
                f"labour rate {self.rate_id!r}: a labour rate is not negative"
            )
        if not isinstance(self.is_contractor, bool):
            raise FinanceError(
                f"labour rate {self.rate_id!r}: is_contractor must be a boolean"
            )
        assert_ref(self.source, f"labour rate {self.rate_id!r} source")
        assert_prose(self.recorded_by, f"labour rate {self.rate_id!r} recorded_by")
        object.__setattr__(
            self, "effective_from", assert_day(self.effective_from, "effective_from")
        )
        object.__setattr__(
            self, "effective_to", optional_day(self.effective_to, "effective_to")
        )
        object.__setattr__(self, "recorded_on", assert_day(self.recorded_on, "recorded_on"))
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise FinanceError(
                f"labour rate {self.rate_id!r}: effective_to is before effective_from"
            )
        if not isinstance(self.notes, str):
            raise FinanceError(f"labour rate {self.rate_id!r}: notes must be a string")
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))
        assert_evidence_backed(
            self.evidence,
            f"labour rate {self.rate_id!r} evidence",
            "an internal rate with no source is a salary somebody guessed, and section 21 "
            "forbids guessing one",
        )

    @property
    def currency(self) -> str:
        return self.amount.currency

    def as_cost_rate(self) -> CostRate:
        """The same rate in the form `mapping.py` prices against.

        The provider is the subject key, so a labour mapping and a labour rate
        meet on `person:mira` rather than on a name typed twice.
        """
        return CostRate(
            rate_id=self.rate_id,
            provider=self.subject.key,
            category=CostCategory.CONTRACTOR if self.is_contractor else CostCategory.EMPLOYEE_TIME,
            unit=self.unit,
            amount=self.amount,
            effective_from=self.effective_from,
            source=self.source,
            evidence=self.evidence,
            recorded_by=self.recorded_by,
            recorded_on=self.recorded_on,
            effective_to=self.effective_to,
            notes=self.notes,
        )

    def to_dict(self) -> dict[str, Any]:
        return record_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LabourRate:
        return cls(
            rate_id=data["rate_id"],
            subject=SubjectRef.from_dict(data["subject"]),
            amount=Money.from_dict(data["amount"], "labour rate amount"),
            unit=RateUnit(data["unit"]),
            effective_from=assert_day(data["effective_from"], "effective_from"),
            source=data["source"],
            evidence=evidence_tuple(data.get("evidence")),
            recorded_by=data["recorded_by"],
            recorded_on=assert_day(data["recorded_on"], "recorded_on"),
            effective_to=optional_day(data.get("effective_to"), "effective_to"),
            is_contractor=bool(data.get("is_contractor", False)),
            notes=data.get("notes", ""),
        )

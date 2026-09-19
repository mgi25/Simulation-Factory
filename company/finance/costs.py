"""What something cost, what it was for, and who can check the number.

## Every cost carries a receipt

`evidence` is not optional and not defaulted to empty. Section 3 of the brief
says a monetary cost without evidence is not a cost record, and the constructor
is where that is cheapest to enforce: a number with no source cannot be created,
so it cannot be stored, so no summary can ever quietly include one.

## Three orthogonal classifications, not one taxonomy

A cost is simultaneously recurring or one-time, fixed or variable, and direct or
allocated. Collapsing those into a single enum would produce fourteen members
and a reader who has to memorise which combination each one means. Three small
enums answer three different questions:

    Recurrence   does it come back next month? - the subscription question
    Variability  does it scale with output? - the marginal-cost question
    Attribution  is it this subject's cost, or a share of something bigger?

## Allocated means the method is on the record

`Attribution.ALLOCATED` requires `allocation_method` and `allocation_basis`, and
`Attribution.DIRECT` refuses both. That is section 7's "do not silently
distribute shared costs" as a construction rule: a share that exists without
naming how it was computed is a number nobody can reproduce.

`UNALLOCATED` is a first-class third state, not a missing value. A 20 EUR
subscription that four projects use and nobody has apportioned is *known* and
*unassigned*, and pretending it is 5 EUR each would be an invention. Summaries
count it separately and say so.

## Corrections are records, never edits

A cost that was wrong is not repaired in place - section 16. `CostAdjustment` is
the one type in this package that carries a signed amount, because a refund and
a surcharge are genuinely opposite directions and modelling a refund as a
negative `CostRecord` would put a minus sign into the ledger that every total
would have to remember to handle. Adjustments net against their target in
`economics.py`, and the original record stays exactly as it was recorded.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
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
    optional_ref,
    record_to_dict,
)
from .errors import FinanceError
from .money import Money


class CostCategory(Enum):
    """Where the money went. Section 3's list, one value each."""

    AI_REASONING = "ai_reasoning"
    API = "api"
    SOFTWARE_SERVICE = "software_service"
    COMPUTE = "compute"
    RENDER = "render"
    STORAGE = "storage"
    CONTRACTOR = "contractor"
    EMPLOYEE_TIME = "employee_time"
    RESEARCH = "research"
    PRODUCTION = "production"
    DISTRIBUTION = "distribution"
    ASSET = "asset"
    ONE_TIME_TOOLING = "one_time_tooling"
    REUSABLE_INFRASTRUCTURE = "reusable_infrastructure"
    OTHER = "other"


class Recurrence(Enum):
    ONE_TIME = "one_time"
    RECURRING = "recurring"


class Variability(Enum):
    FIXED = "fixed"
    VARIABLE = "variable"
    UNKNOWN = "unknown"


class Attribution(Enum):
    """Whose cost this is.

    UNALLOCATED is not a missing value. It is the honest state of a shared cost
    nobody has apportioned yet, and it is reported rather than distributed.
    """

    DIRECT = "direct"
    ALLOCATED = "allocated"
    UNALLOCATED = "unallocated"


class AllocationMethod(Enum):
    """How a share was computed. Required exactly when a cost is allocated."""

    NONE = "none"
    EQUAL = "equal"
    USAGE_BASED = "usage_based"
    MANUAL = "manual"


class AdjustmentKind(Enum):
    """The two directions a correction can run."""

    CREDIT = "credit"  # money back, or a cost that was overstated
    SURCHARGE = "surcharge"  # an additional charge against the same subject


# Categories whose spend is paid to an outside provider. Used by `proposals.py`
# to decide whether a spend proposal is the kind of thing permissions.yaml
# reserves, and by `integrity.py` to notice a recurring paid line that was
# recorded without one.
PAID_EXTERNAL_CATEGORIES = frozenset(
    {
        CostCategory.API,
        CostCategory.SOFTWARE_SERVICE,
        CostCategory.COMPUTE,
        CostCategory.STORAGE,
        CostCategory.RENDER,
        CostCategory.AI_REASONING,
        CostCategory.CONTRACTOR,
    }
)


@dataclass(frozen=True)
class CostRecord:
    """One cost, charged to one subject, with the evidence that proves it."""

    kind: ClassVar[str] = "cost"

    cost_id: str
    incurred_on: dt.date
    amount: Money
    category: CostCategory
    subject: SubjectRef
    source: str
    evidence: tuple[Evidence, ...]
    recorded_by: str
    recorded_on: dt.date
    recurrence: Recurrence = Recurrence.ONE_TIME
    recurrence_period: str = ""
    variability: Variability = Variability.UNKNOWN
    attribution: Attribution = Attribution.DIRECT
    allocation_method: AllocationMethod = AllocationMethod.NONE
    allocation_basis: str = ""
    parent_cost_id: str = ""
    resource_ref: str = ""
    supersedes: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        assert_record_id(self.cost_id, "cost_id")
        object.__setattr__(self, "incurred_on", assert_day(self.incurred_on, "incurred_on"))
        object.__setattr__(self, "recorded_on", assert_day(self.recorded_on, "recorded_on"))
        for name, enum_type in (
            ("category", CostCategory),
            ("recurrence", Recurrence),
            ("variability", Variability),
            ("attribution", Attribution),
            ("allocation_method", AllocationMethod),
        ):
            value = getattr(self, name)
            if not isinstance(value, enum_type):
                raise FinanceError(
                    f"cost {self.cost_id!r}: {name} must be a {enum_type.__name__}, "
                    f"got {value!r}"
                )
        if not isinstance(self.amount, Money):
            raise FinanceError(
                f"cost {self.cost_id!r}: amount must be Money, got "
                f"{type(self.amount).__name__}"
            )
        if self.amount.is_negative:
            raise FinanceError(
                f"cost {self.cost_id!r}: a cost is not negative ({self.amount}). A refund "
                "or an overstatement is a CostAdjustment against this record, which keeps "
                "the original number in the ledger"
            )
        if not isinstance(self.subject, SubjectRef):
            raise FinanceError(
                f"cost {self.cost_id!r}: subject must be a SubjectRef naming what this "
                "cost is for"
            )
        assert_ref(self.source, f"cost {self.cost_id!r} source")
        assert_prose(self.recorded_by, f"cost {self.cost_id!r} recorded_by")
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))
        assert_evidence_backed(
            self.evidence,
            f"cost {self.cost_id!r} evidence",
            "a monetary cost that points at nothing checkable is a number somebody "
            "remembered (brief section 3)",
        )
        for name in ("parent_cost_id", "supersedes"):
            value = getattr(self, name)
            if value:
                assert_record_id(value, f"cost {self.cost_id!r} {name}")
        object.__setattr__(
            self, "resource_ref", optional_ref(self.resource_ref, "resource_ref")
        )
        for name in ("recurrence_period", "allocation_basis", "notes"):
            if not isinstance(getattr(self, name), str):
                raise FinanceError(f"cost {self.cost_id!r}: {name} must be a string")
        self._check_recurrence()
        self._check_allocation()

    def _check_recurrence(self) -> None:
        if self.recurrence is Recurrence.RECURRING and not self.recurrence_period.strip():
            raise FinanceError(
                f"cost {self.cost_id!r}: a recurring cost must name its period - "
                "'monthly', 'annual', 'per_render' - or nobody can tell what recurs"
            )
        if self.recurrence is Recurrence.ONE_TIME and self.recurrence_period.strip():
            raise FinanceError(
                f"cost {self.cost_id!r}: a one-time cost has no recurrence period"
            )

    def _check_allocation(self) -> None:
        allocated = self.attribution is Attribution.ALLOCATED
        if allocated:
            if self.allocation_method is AllocationMethod.NONE:
                raise FinanceError(
                    f"cost {self.cost_id!r}: an allocated cost must name the rule that "
                    "produced the share. A share nobody can reproduce is not evidence "
                    "(brief section 7)"
                )
            if not self.allocation_basis.strip():
                raise FinanceError(
                    f"cost {self.cost_id!r}: an allocated cost must state the basis the "
                    "share was computed on"
                )
            if not self.parent_cost_id:
                raise FinanceError(
                    f"cost {self.cost_id!r}: an allocated cost must reference the shared "
                    "cost it is a share of"
                )
        else:
            if self.allocation_method is not AllocationMethod.NONE:
                raise FinanceError(
                    f"cost {self.cost_id!r}: allocation_method is for allocated costs; "
                    f"this one is {self.attribution.value}"
                )
            if self.allocation_basis.strip():
                raise FinanceError(
                    f"cost {self.cost_id!r}: allocation_basis is for allocated costs; "
                    f"this one is {self.attribution.value}"
                )

    # -- reading -----------------------------------------------------------

    @property
    def currency(self) -> str:
        return self.amount.currency

    @property
    def is_paid_external(self) -> bool:
        """True when this is money leaving the company to an outside provider."""
        return self.category in PAID_EXTERNAL_CATEGORIES

    def to_dict(self) -> dict[str, Any]:
        return record_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CostRecord:
        return cls(
            cost_id=data["cost_id"],
            incurred_on=assert_day(data["incurred_on"], "incurred_on"),
            amount=Money.from_dict(data["amount"], "cost amount"),
            category=CostCategory(data["category"]),
            subject=SubjectRef.from_dict(data["subject"]),
            source=data["source"],
            evidence=evidence_tuple(data.get("evidence")),
            recorded_by=data["recorded_by"],
            recorded_on=assert_day(data["recorded_on"], "recorded_on"),
            recurrence=Recurrence(data.get("recurrence", "one_time")),
            recurrence_period=data.get("recurrence_period", ""),
            variability=Variability(data.get("variability", "unknown")),
            attribution=Attribution(data.get("attribution", "direct")),
            allocation_method=AllocationMethod(data.get("allocation_method", "none")),
            allocation_basis=data.get("allocation_basis", ""),
            parent_cost_id=data.get("parent_cost_id", ""),
            resource_ref=data.get("resource_ref", ""),
            supersedes=data.get("supersedes", ""),
            notes=data.get("notes", ""),
        )


@dataclass(frozen=True)
class CostAdjustment:
    """A correction against a recorded cost. The one signed amount in the package.

    The target record is never touched. A credit of 12 EUR against a 50 EUR
    invoice leaves the 50 in the ledger and adds a second record saying 12 came
    back, which is what makes the history readable a year later.
    """

    kind: ClassVar[str] = "cost_adjustment"

    adjustment_id: str
    cost_id: str
    adjusted_on: dt.date
    amount: Money
    adjustment_kind: AdjustmentKind
    reason: str
    evidence: tuple[Evidence, ...]
    recorded_by: str
    recorded_on: dt.date
    notes: str = ""

    def __post_init__(self) -> None:
        assert_record_id(self.adjustment_id, "adjustment_id")
        assert_record_id(self.cost_id, "cost_id")
        object.__setattr__(self, "adjusted_on", assert_day(self.adjusted_on, "adjusted_on"))
        object.__setattr__(self, "recorded_on", assert_day(self.recorded_on, "recorded_on"))
        if not isinstance(self.adjustment_kind, AdjustmentKind):
            raise FinanceError(
                f"adjustment {self.adjustment_id!r}: adjustment_kind must be an "
                "AdjustmentKind"
            )
        if not isinstance(self.amount, Money):
            raise FinanceError(
                f"adjustment {self.adjustment_id!r}: amount must be Money"
            )
        if self.amount.is_negative or self.amount.is_zero:
            raise FinanceError(
                f"adjustment {self.adjustment_id!r}: state the magnitude as a positive "
                "amount and the direction as the kind. A negative credit is two minus "
                "signs and one of them will be lost"
            )
        assert_prose(self.reason, f"adjustment {self.adjustment_id!r} reason")
        assert_prose(self.recorded_by, f"adjustment {self.adjustment_id!r} recorded_by")
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))
        assert_evidence_backed(
            self.evidence,
            f"adjustment {self.adjustment_id!r} evidence",
            "a correction with no source is an opinion about a number that had one",
        )
        if not isinstance(self.notes, str):
            raise FinanceError(f"adjustment {self.adjustment_id!r}: notes must be a string")

    @property
    def signed_amount(self) -> Money:
        """The effect on the total: negative for a credit, positive for a surcharge."""
        return -self.amount if self.adjustment_kind is AdjustmentKind.CREDIT else self.amount

    @property
    def currency(self) -> str:
        return self.amount.currency

    def to_dict(self) -> dict[str, Any]:
        return record_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CostAdjustment:
        return cls(
            adjustment_id=data["adjustment_id"],
            cost_id=data["cost_id"],
            adjusted_on=assert_day(data["adjusted_on"], "adjusted_on"),
            amount=Money.from_dict(data["amount"], "adjustment amount"),
            adjustment_kind=AdjustmentKind(data["adjustment_kind"]),
            reason=data["reason"],
            evidence=evidence_tuple(data.get("evidence")),
            recorded_by=data["recorded_by"],
            recorded_on=assert_day(data["recorded_on"], "recorded_on"),
            notes=data.get("notes", ""),
        )


@dataclass(frozen=True)
class AllocationShare:
    """One subject's claim on a shared cost, and the weight behind it."""

    subject: SubjectRef
    weight: Any = 1
    basis: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.subject, SubjectRef):
            raise FinanceError("an allocation share must name a SubjectRef")
        if not isinstance(self.basis, str):
            raise FinanceError("allocation share basis must be a string")


def allocate(
    cost: CostRecord,
    shares: Iterable[AllocationShare],
    method: AllocationMethod,
    *,
    basis: str,
    id_prefix: str = "",
    quantum: Any = None,
) -> tuple[CostRecord, ...]:
    """Split one shared cost into per-subject allocated costs that sum to it exactly.

    Returns allocated children, each naming the method, the basis and the parent.
    The parent is not modified and not deleted; a caller that stores both has the
    shared cost and its distribution, which is what makes the split auditable.

    `AllocationMethod.NONE` is refused here rather than handled: a caller with no
    rule wants `unallocated()`, and leaving the cost unallocated is the honest
    outcome section 7 asks for.
    """
    if not isinstance(method, AllocationMethod) or method is AllocationMethod.NONE:
        raise FinanceError(
            "allocate() needs a real method - EQUAL, USAGE_BASED or MANUAL. With no rule, "
            "leave the cost unallocated rather than inventing a distribution"
        )
    parts = tuple(shares)
    if not parts:
        raise FinanceError(
            f"cost {cost.cost_id!r}: no shares supplied. A shared cost with no known "
            "consumers stays unallocated"
        )
    if not basis.strip():
        raise FinanceError(
            f"cost {cost.cost_id!r}: allocation needs a stated basis - what the weights "
            "actually measure"
        )
    if cost.attribution is Attribution.ALLOCATED:
        raise FinanceError(
            f"cost {cost.cost_id!r} is already an allocated share; allocate the parent"
        )
    seen: set[str] = set()
    for share in parts:
        if share.subject.key in seen:
            raise FinanceError(
                f"cost {cost.cost_id!r}: {share.subject.key} appears twice in one "
                "allocation; combine the weights instead"
            )
        seen.add(share.subject.key)
    weights = [1 if method is AllocationMethod.EQUAL else share.weight for share in parts]
    split_kwargs = {} if quantum is None else {"quantum": quantum}
    amounts = cost.amount.split(weights, **split_kwargs)
    prefix = id_prefix or f"{cost.cost_id}.alloc"
    return tuple(
        CostRecord(
            cost_id=f"{prefix}.{index + 1:02d}",
            incurred_on=cost.incurred_on,
            amount=amount,
            category=cost.category,
            subject=share.subject,
            source=cost.source,
            evidence=cost.evidence,
            recorded_by=cost.recorded_by,
            recorded_on=cost.recorded_on,
            recurrence=cost.recurrence,
            recurrence_period=cost.recurrence_period,
            variability=cost.variability,
            attribution=Attribution.ALLOCATED,
            allocation_method=method,
            allocation_basis=share.basis or basis,
            parent_cost_id=cost.cost_id,
            resource_ref=cost.resource_ref,
            notes=cost.notes,
        )
        for index, (share, amount) in enumerate(zip(parts, amounts))
    )


def unallocated(cost: CostRecord, why: str) -> CostRecord:
    """Mark a shared cost as known but unassigned, with the reason recorded.

    The alternative - distributing it anyway - is the thing section 7 forbids.
    This keeps the number in every company-level total while keeping it out of
    every per-project total, which is exactly what is true about it.
    """
    from dataclasses import replace

    if not why.strip():
        raise FinanceError(
            f"cost {cost.cost_id!r}: say why it is unallocated, so the gap is a known "
            "gap rather than an oversight"
        )
    note = f"unallocated: {why}" if not cost.notes else f"{cost.notes} | unallocated: {why}"
    return replace(
        cost,
        attribution=Attribution.UNALLOCATED,
        allocation_method=AllocationMethod.NONE,
        allocation_basis="",
        notes=note,
    )

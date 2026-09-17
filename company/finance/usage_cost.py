"""The bridge from a measured attempt to a recorded cost, and the gap when there is none.

`ai_platform/usage.py` counts what an attempt consumed. `rates.py` holds the
prices somebody supplied. `costs.py` holds money. Nothing joined them, so the
question the bootstrap brief actually asks - *what did an accepted deliverable
cost?* - had no operational answer even though both halves were being recorded.

This module is that join, and it is deliberately thin.

## Usage is not money, and this is where that is enforced

A token count is one provider's quantisation of one provider's text. A tool call
is an event. A second of wall clock is a second. None of them is a currency
amount, and the only thing that turns one into money is a `CostRate` a human
recorded with a source and an effective date. So `UsageCostAttribution.amount`
is `Money | None`, and the `None` carries an `UnpricedReason` rather than a zero.

There is no price table here, no provider constant and no default rate. A run
over real usage with an empty rate card prices nothing and says so, which is the
correct answer rather than a failure.

## What the usage record cannot know

`ResourceUsageRecord` carries no provider, no executor and no date. That is not
an oversight upstream: a usage record describes *work*, and who ran it and what
they charge are facts about the arrangement, not about the attempt. So pricing
needs a `UsageObservation` to supply them, and a caller who does not know the
provider cannot accidentally get a price.

The attempt number is likewise not on the record. It is the sequence number the
append-only store gave the file, which is why it arrives as a parameter rather
than as an attribute.

## Identity: three digests, and what each one protects

A cost id reads `uca.<lineage>.<measure>.<pricing>`.

    lineage   the usage record and its digest, the provider, the subject, the day
    measure   which quantity of that record is being charged
    pricing   the rate that was applied, and the evidence behind it

Replaying an attribution reproduces all three, so the store sees byte-identical
content and does nothing. Changing the rate changes only the third, so the new
record is *distinct* and the old one survives - and because the first two still
match, `commit_attribution_costs` can see that the second record restates the
first and refuse to write it unless a caller says so. That is the whole
no-silent-restatement guarantee, and it is why the measure is in the id rather
than only in the notes.

## Descriptive, not causal

The expansion, reasoning-class and executor views exist because those are the
dimensions the company wants to look at. They report sample counts, known cost
and how much was unpriced. They do not attribute causation: nothing here
isolates the effect of an expansion, so no figure supports "expansion cost us X",
and there is no ranking and no cheapest-executor conclusion for the same reason.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, ClassVar, Iterable

from ai_platform.serde import fingerprint as _fingerprint
from knowledge.company_os.records import Evidence

from .common import (
    SubjectRef,
    assert_day,
    assert_evidence_backed,
    assert_record_id,
    assert_ref,
    evidence_tuple,
    record_to_dict,
)
from .costs import Attribution, CostCategory, CostRecord, Recurrence, Variability
from .errors import FinanceError
from .mapping import PricedUsage, ResourceCostMapping, mappings_from_usage
from .money import Money
from .rates import RateCard, RateUnit, UnpricedReason

# Outcome values, restated rather than imported. `mapping.py` gives the reason:
# `company/finance` reads the measuring subsystems duck-typed so the boundary
# stays one-way, and three string constants are a cheaper coupling than an
# import of `ai_platform.usage.Outcome`.
ACCEPTED = "accepted"
REJECTED = "rejected"
ABANDONED = "abandoned"
OUTCOMES = (ACCEPTED, REJECTED, ABANDONED)

# Attributes read off a `ResourceUsageRecord` beyond the ones `mapping.py`
# already names in `USAGE_ATTRIBUTES`. Listed here for the same reason: a rename
# upstream fails on the next run instead of silently producing an empty view.
OBSERVED_ATTRIBUTES: tuple[str, ...] = (
    "passes",
    "retries",
    "expansion_count",
    "required_expansion_count",
    "expansion_chars",
)

ID_PREFIX = "uca"

# The statement every descriptive view carries. Section 8 of the brief: this is
# accounting, not analysis, and the difference belongs where a reader of the
# number will see it rather than in a docstring they will not.
DESCRIPTIVE_ONLY = (
    "Expansion, reasoning-class and executor views are descriptive: they report "
    "what each group cost, not what any of it caused. Nothing here isolates an "
    "effect, so no figure supports 'expansion cost X' or 'this executor is cheaper'."
)

RETRY_SEMANTICS = (
    "A retry is counted on the attempt that made it, and that attempt's measured "
    "units already cover every pass it took. Retry-bearing cost is therefore the "
    "cost of attempts that retried, not a separable charge for the retries."
)

UNPRICED_IS_NOT_FREE = (
    "An unpriced quantity is unknown, never zero. Any total over a run that is "
    "not complete is a floor."
)


class CostableMeasure(Enum):
    """The quantities a `ResourceUsageRecord` actually exposes, one value each.

    Deliberately not a wish list. `input_units` and `output_units` exist and are
    `None` when the provider exposed nothing; `tool_calls` and `duration_s` the
    same. There is no cached-token member because there is no such field to read,
    and inventing one would produce a mapping over a number nobody measured.
    """

    INPUT_UNITS = "input_units"
    OUTPUT_UNITS = "output_units"
    TOOL_CALLS = "tool_calls"
    COMPUTE_SECONDS = "compute_seconds"


class CostCompleteness(Enum):
    """How much of what was measured actually carries a price."""

    COMPLETE = "complete"  # every costable quantity found a rate
    PARTIAL = "partial"  # some priced, some not - every total is a floor
    UNPRICED = "unpriced"  # quantities existed, no rate covered any of them
    INSUFFICIENT_QUANTITY = "insufficient_quantity"  # nothing costable was measured


class ConflictKind(Enum):
    """Why a quantity was refused a price rather than simply missing one."""

    OVERLAPPING_RATES = "overlapping_rates"
    UNIT_MISMATCH = "unit_mismatch"


class AttributionScope(Enum):
    """Which attempts the numerator of a per-deliverable figure includes."""

    ALL_ATTEMPTS = "all_attempts"  # what it cost to *reach* acceptance
    ACCEPTED_ONLY = "accepted_only"  # what the accepted attempts alone cost


# Which rate unit and cost category each measure prices in. This mirrors what
# `mapping.py` builds; the tests assert the table against real mappings so the
# two cannot drift apart unnoticed.
MEASURE_UNITS: dict[CostableMeasure, tuple[RateUnit, CostCategory]] = {
    CostableMeasure.INPUT_UNITS: (RateUnit.TOKEN, CostCategory.AI_REASONING),
    CostableMeasure.OUTPUT_UNITS: (RateUnit.TOKEN, CostCategory.AI_REASONING),
    CostableMeasure.TOOL_CALLS: (RateUnit.REQUEST, CostCategory.API),
    CostableMeasure.COMPUTE_SECONDS: (RateUnit.COMPUTE_SECOND, CostCategory.COMPUTE),
}


def _enum_text(value: Any) -> str:
    """The string form of an enum member or a plain string. Duck-typed on purpose."""
    return str(getattr(value, "value", value))


def _add(totals: dict[str, Money], amount: Money | None) -> None:
    """Accumulate into a per-currency bucket. Nothing is ever converted."""
    if amount is None:
        return
    running = totals.get(amount.currency)
    totals[amount.currency] = amount if running is None else running + amount


def _totals(attributions: Iterable[UsageCostAttribution]) -> dict[str, Money]:
    """Known cost by currency, in currency order. Multi-currency stays separate."""
    out: dict[str, Money] = {}
    for item in attributions:
        _add(out, item.amount)
    return {code: out[code] for code in sorted(out)}


def _money_text(totals: dict[str, Money]) -> dict[str, str]:
    return {code: amount.text for code, amount in totals.items()}


# --------------------------------------------------------------------------
# One usage record, seen from the finance side
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class UsageObservation:
    """One usage record, plus the facts the record itself cannot carry.

    The record knows what an attempt consumed. It does not know who ran it, what
    they charge, which day the arrangement priced, or what the cost is for. Those
    four arrive here from a caller who knows them, and without them there is no
    attribution rather than a guessed one.
    """

    kind: ClassVar[str] = "usage_observation"

    usage_ref: str
    task_id: str
    provider: str
    subject: SubjectRef
    measured_on: dt.date
    evidence: tuple[Evidence, ...]
    usage_fingerprint: str = ""
    attempt: int | None = None
    executor: str = ""
    reasoning_class: str = ""
    outcome: str = ""
    passes: int = 1
    retries: int = 0
    expansion_count: int = 0
    required_expansion_count: int = 0
    expansion_chars: int = 0
    mappings: tuple[ResourceCostMapping, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        assert_ref(self.usage_ref, "observation usage_ref")
        assert_ref(self.task_id, "observation task_id")
        assert_ref(self.provider, "observation provider")
        if not isinstance(self.subject, SubjectRef):
            raise FinanceError(
                f"observation {self.usage_ref!r}: subject must be a SubjectRef naming "
                "what this usage is charged to"
            )
        object.__setattr__(
            self, "measured_on", assert_day(self.measured_on, "measured_on")
        )
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))
        assert_evidence_backed(
            self.evidence,
            f"observation {self.usage_ref!r} evidence",
            "an attribution that points at no checkable measurement is a cost "
            "somebody asserted, and every total it enters inherits the assertion",
        )
        if self.outcome and self.outcome not in OUTCOMES:
            raise FinanceError(
                f"observation {self.usage_ref!r}: outcome {self.outcome!r} must be one "
                "of: " + ", ".join(OUTCOMES)
            )
        for name in (
            "passes",
            "retries",
            "expansion_count",
            "required_expansion_count",
            "expansion_chars",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise FinanceError(
                    f"observation {self.usage_ref!r}: {name} must be a non-negative "
                    f"whole number, got {value!r}"
                )
        if self.attempt is not None and (
            isinstance(self.attempt, bool)
            or not isinstance(self.attempt, int)
            or self.attempt < 1
        ):
            raise FinanceError(
                f"observation {self.usage_ref!r}: attempt must be a positive integer, "
                "or None when the history did not number it"
            )
        for name in ("usage_fingerprint", "executor", "reasoning_class", "notes"):
            if not isinstance(getattr(self, name), str):
                raise FinanceError(
                    f"observation {self.usage_ref!r}: {name} must be a string"
                )
        if not isinstance(self.mappings, tuple):
            raise FinanceError(
                f"observation {self.usage_ref!r}: mappings must be a tuple"
            )

    @property
    def lineage(self) -> str:
        """The digest of everything that fixes *what* is being charged.

        The usage record and its digest, the provider, the subject and the day.
        Not the rate: a re-priced attribution keeps this digest, which is exactly
        what lets a restatement be recognised as one rather than as a new cost.
        """
        return _fingerprint(
            {
                "usage_ref": self.usage_ref,
                "usage_fingerprint": self.usage_fingerprint,
                "task_id": self.task_id,
                "provider": self.provider,
                "subject": self.subject.key,
                "measured_on": self.measured_on.isoformat(),
            }
        )

    @property
    def id_prefix(self) -> str:
        return f"{ID_PREFIX}.{self.lineage}"

    @property
    def has_costable_quantity(self) -> bool:
        return bool(self.mappings)

    @property
    def required_expansion(self) -> bool:
        """True when the initial context was not sufficient for this attempt."""
        return self.required_expansion_count > 0

    def to_dict(self) -> dict[str, Any]:
        data = record_to_dict(self)
        data["lineage"] = self.lineage
        return data


def observe_usage(
    record: Any,
    *,
    usage_ref: str,
    provider: str,
    subject: SubjectRef,
    measured_on: Any,
    evidence: Iterable[Evidence],
    attempt: int | None = None,
    executor: Any = "",
    include_duration: bool = False,
    usage_fingerprint: str | None = None,
    notes: str = "",
) -> UsageObservation:
    """Read one `ResourceUsageRecord` into an observation, without importing it.

    `include_duration` is off by default and is a statement about the
    arrangement rather than about the record: wall-clock seconds are billable
    when somebody rents compute by the second and are not when a session is
    covered by a subscription. Turning it on without a rate produces an unpriced
    line, which is the honest outcome either way.

    `usage_fingerprint` defaults to the record's own digest when it exposes one.
    Passing the store pointer's fingerprint instead is equivalent, and is what
    the CLI does - that is the value the store has already verified.
    """
    try:
        observed = {name: getattr(record, name) for name in OBSERVED_ATTRIBUTES}
    except AttributeError as exc:
        raise FinanceError(
            f"a usage record must expose {', '.join(OBSERVED_ATTRIBUTES)}; this one is "
            f"missing {exc}"
        ) from exc
    if usage_fingerprint is None:
        digest = getattr(record, "fingerprint", None)
        usage_fingerprint = digest() if callable(digest) else ""
    day = assert_day(measured_on, "measured_on")
    identity = UsageObservation(
        usage_ref=usage_ref,
        task_id=getattr(record, "task_id", ""),
        provider=provider,
        subject=subject,
        measured_on=day,
        evidence=tuple(evidence),
        usage_fingerprint=usage_fingerprint,
        attempt=attempt,
        executor=_enum_text(executor) if executor else "",
        reasoning_class=_enum_text(getattr(record, "reasoning_class", "")),
        outcome=_enum_text(getattr(record, "outcome", "")),
        notes=notes,
        **observed,
    )
    # The mapping ids embed the lineage, so the identity has to exist before the
    # quantities do. Everything else is carried straight through.
    mappings = mappings_from_usage(
        record,
        subject=subject,
        provider=provider,
        measured_on=day,
        id_prefix=identity.id_prefix,
        include_time=include_duration,
    )
    return UsageObservation(
        usage_ref=identity.usage_ref,
        task_id=identity.task_id,
        provider=identity.provider,
        subject=identity.subject,
        measured_on=identity.measured_on,
        evidence=identity.evidence,
        usage_fingerprint=identity.usage_fingerprint,
        attempt=identity.attempt,
        executor=identity.executor,
        reasoning_class=identity.reasoning_class,
        outcome=identity.outcome,
        passes=identity.passes,
        retries=identity.retries,
        expansion_count=identity.expansion_count,
        required_expansion_count=identity.required_expansion_count,
        expansion_chars=identity.expansion_chars,
        mappings=mappings,
        notes=identity.notes,
    )


# --------------------------------------------------------------------------
# One priced line
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AttributionConflict:
    """A quantity that could have been priced wrongly, and was refused instead.

    Two rates covering one day is a correction somebody owes, not a tie to break.
    A rate quoted in an incompatible unit is a different measurement, not a
    conversion. Both leave the quantity unpriced and both are reported, because
    an unexplained gap and a refused price are different problems with different
    owners.
    """

    kind: ClassVar[str] = "attribution_conflict"

    conflict: ConflictKind
    usage_ref: str
    measure: CostableMeasure
    provider: str
    on: dt.date
    detail: str

    def __str__(self) -> str:
        return (
            f"{self.conflict.value}: {self.provider} {self.measure.value} for "
            f"{self.usage_ref} on {self.on.isoformat()}: {self.detail}"
        )

    def to_dict(self) -> dict[str, Any]:
        return record_to_dict(self)


@dataclass(frozen=True)
class UsageCostAttribution:
    """One measured quantity, the rate applied to it, and the money that resulted.

    Evidence and bridge, never the financial source of truth: committing a run
    turns each priced attribution into a `CostRecord`, and that record is what
    every total in this package reads.
    """

    kind: ClassVar[str] = "usage_cost_attribution"

    attribution_id: str
    usage_ref: str
    task_id: str
    measure: CostableMeasure
    quantity: Decimal
    unit: RateUnit
    category: CostCategory
    provider: str
    subject: SubjectRef
    measured_on: dt.date
    evidence: tuple[Evidence, ...]
    amount: Money | None = None
    rate_id: str = ""
    unpriced_reason: UnpricedReason | None = None
    conflict: AttributionConflict | None = None
    attempt: int | None = None
    executor: str = ""
    reasoning_class: str = ""
    outcome: str = ""

    def __post_init__(self) -> None:
        assert_record_id(self.attribution_id, "attribution_id")
        if (self.amount is None) == (self.unpriced_reason is None):
            raise FinanceError(
                f"attribution {self.attribution_id!r}: exactly one of an amount and an "
                "unpriced reason. Anything else is an unknown pretending to be a "
                "number, or the reverse"
            )
        if self.amount is not None and not self.rate_id:
            raise FinanceError(
                f"attribution {self.attribution_id!r}: a priced amount names the rate "
                "that produced it, or nobody can recompute the number"
            )
        if self.amount is not None and self.amount.is_negative:
            raise FinanceError(
                f"attribution {self.attribution_id!r}: a usage cost is not negative"
            )

    @property
    def is_priced(self) -> bool:
        return self.amount is not None

    @property
    def currency(self) -> str | None:
        return self.amount.currency if self.amount is not None else None

    @property
    def lineage_id(self) -> str:
        """`uca.<lineage>.<measure>` - the charge line, without the pricing.

        Two attributions that share this price the same quantity of the same
        usage record for the same subject. If they differ beyond it, the second
        restates the first rather than adding to it.
        """
        return self.attribution_id.rsplit(".", 1)[0]

    def to_dict(self) -> dict[str, Any]:
        data = record_to_dict(self)
        data["unpriced_reason"] = (
            str(self.unpriced_reason) if self.unpriced_reason else ""
        )
        data["conflict"] = str(self.conflict) if self.conflict else ""
        data["lineage_id"] = self.lineage_id
        return data


def _measure_of(mapping: ResourceCostMapping) -> CostableMeasure:
    """Recover which measure a mapping prices, from the suffix of its id."""
    suffix = mapping.mapping_id.rsplit(".", 1)[-1]
    try:
        return CostableMeasure(suffix)
    except ValueError as exc:
        raise FinanceError(
            f"mapping {mapping.mapping_id!r} does not name a costable measure; known "
            "measures: " + ", ".join(item.value for item in CostableMeasure)
        ) from exc


def _pricing_digest(
    observation: UsageObservation, priced: PricedUsage | None, rate_id: str
) -> str:
    """Everything that fixes *what was charged* for one line, and nothing else."""
    return _fingerprint(
        {
            "rate_id": rate_id,
            "priced_on": priced.priced_on.isoformat() if priced is not None else "",
            "amount": (
                priced.amount.to_dict()
                if priced is not None and priced.amount is not None
                else None
            ),
            "evidence": [
                {"kind": item.kind, "ref": item.ref, "note": item.note}
                for item in observation.evidence
            ],
        }
    )


def _other_units(card: RateCard, mapping: ResourceCostMapping, day: dt.date) -> tuple[str, ...]:
    """Units this card prices the provider and category in, other than the one asked.

    Reported rather than converted: a rate per render minute does not price a
    token count, and whoever recorded one of them meant the other.
    """
    return tuple(
        sorted(
            {
                rate.unit.value
                for rate in card
                if rate.provider == mapping.provider
                and rate.category is mapping.category
                and rate.covers(day)
            }
        )
    )


def _attribute_one(
    observation: UsageObservation, mapping: ResourceCostMapping, card: RateCard
) -> UsageCostAttribution:
    """Price one mapping, turning every way it can fail into a named state."""
    measure = _measure_of(mapping)
    day = mapping.measured_on
    conflict: AttributionConflict | None = None
    priced: PricedUsage | None = None
    try:
        priced = mapping.price(card)
    except FinanceError as exc:
        # `RateCard.rate_for` refuses to break a tie between two rates that both
        # cover the day. That refusal is the finding, so it becomes a conflict
        # here rather than ending the run.
        conflict = AttributionConflict(
            conflict=ConflictKind.OVERLAPPING_RATES,
            usage_ref=observation.usage_ref,
            measure=measure,
            provider=mapping.provider,
            on=day,
            detail=str(exc),
        )
    if priced is not None and not priced.is_priced:
        others = _other_units(card, mapping, day)
        if others:
            conflict = AttributionConflict(
                conflict=ConflictKind.UNIT_MISMATCH,
                usage_ref=observation.usage_ref,
                measure=measure,
                provider=mapping.provider,
                on=day,
                detail=(
                    f"this quantity is measured in {mapping.unit.value}; the card "
                    f"prices {mapping.provider} {mapping.category.value} in "
                    + ", ".join(others)
                    + ". Nothing here converts between units that measure different "
                    "things"
                ),
            )
    amount = priced.amount if priced is not None else None
    rate_id = priced.rate_id if priced is not None else ""
    reason = priced.unpriced_reason if priced is not None else None
    if amount is None and reason is None:
        reason = UnpricedReason(
            provider=mapping.provider,
            unit=mapping.unit,
            on=day,
            detail=conflict.detail if conflict is not None else "no rate was resolved",
        )
    return UsageCostAttribution(
        attribution_id=(
            f"{mapping.mapping_id}.{_pricing_digest(observation, priced, rate_id)}"
        ),
        usage_ref=observation.usage_ref,
        task_id=observation.task_id,
        measure=measure,
        quantity=mapping.quantity,
        unit=mapping.unit,
        category=mapping.category,
        provider=mapping.provider,
        subject=mapping.subject,
        measured_on=day,
        evidence=observation.evidence,
        amount=amount,
        rate_id=rate_id,
        unpriced_reason=reason,
        conflict=conflict,
        attempt=observation.attempt,
        executor=observation.executor,
        reasoning_class=observation.reasoning_class,
        outcome=observation.outcome,
    )


# --------------------------------------------------------------------------
# Descriptive views
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class GroupCost:
    """What one group of attempts cost, with its gaps kept in view.

    `known_cost` is a floor whenever `unpriced` is non-zero, which is why the
    two travel together and why nothing here divides one by a sample size.
    """

    key: str
    samples: int
    accepted: int
    rejected: int
    abandoned: int
    known_cost: dict[str, Money]
    unpriced: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "samples": self.samples,
            "accepted": self.accepted,
            "rejected": self.rejected,
            "abandoned": self.abandoned,
            "known_cost": _money_text(self.known_cost),
            "unpriced": self.unpriced,
        }


@dataclass(frozen=True)
class ExpansionCostView:
    """What attempts that expanded their context cost. Descriptive only.

    An attempt that needed more context and an attempt that did not are not a
    controlled comparison: they are different tasks, given different material, by
    different classes. So this reports the two groups and states that it is not
    a finding about expansion.
    """

    attempts_with_expansion: int
    attempts_requiring_expansion: int
    expansion_chars: int
    accepted_with_expansion: int
    rejected_with_expansion: int
    known_cost_with_expansion: dict[str, Money]
    known_cost_without_expansion: dict[str, Money]
    unpriced_with_expansion: int
    caveat: str = DESCRIPTIVE_ONLY

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempts_with_expansion": self.attempts_with_expansion,
            "attempts_requiring_expansion": self.attempts_requiring_expansion,
            "expansion_chars": self.expansion_chars,
            "accepted_with_expansion": self.accepted_with_expansion,
            "rejected_with_expansion": self.rejected_with_expansion,
            "known_cost_with_expansion": _money_text(self.known_cost_with_expansion),
            "known_cost_without_expansion": _money_text(
                self.known_cost_without_expansion
            ),
            "unpriced_with_expansion": self.unpriced_with_expansion,
            "caveat": self.caveat,
        }


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class UsageCostAttributionRun:
    """Every attribution over one set of observations, with what is missing named.

    A run is a reading, not a record: it is recomputed from the usage store and
    the rate card whenever somebody asks. What it produces that *is* a record is
    the `CostRecord` set `commit_attribution_costs` writes.
    """

    kind: ClassVar[str] = "usage_cost_attribution_run"

    run_id: str
    as_of: dt.date
    observations: tuple[UsageObservation, ...]
    attributions: tuple[UsageCostAttribution, ...]
    conflicts: tuple[AttributionConflict, ...]
    skipped: tuple[str, ...]
    evidence: tuple[Evidence, ...]
    caveats: tuple[str, ...] = (UNPRICED_IS_NOT_FREE, RETRY_SEMANTICS, DESCRIPTIVE_ONLY)

    # -- what was looked at ------------------------------------------------

    @property
    def usage_refs_inspected(self) -> tuple[str, ...]:
        return tuple(observation.usage_ref for observation in self.observations)

    @property
    def priced(self) -> tuple[UsageCostAttribution, ...]:
        return tuple(item for item in self.attributions if item.is_priced)

    @property
    def unpriced(self) -> tuple[UsageCostAttribution, ...]:
        return tuple(item for item in self.attributions if not item.is_priced)

    @property
    def known_cost(self) -> dict[str, Money]:
        """Known cost by currency. Two currencies stay two numbers, always."""
        return _totals(self.attributions)

    @property
    def currencies(self) -> tuple[str, ...]:
        return tuple(sorted(self.known_cost))

    @property
    def completeness(self) -> CostCompleteness:
        if not self.attributions:
            return CostCompleteness.INSUFFICIENT_QUANTITY
        if not self.unpriced:
            return CostCompleteness.COMPLETE
        if not self.priced:
            return CostCompleteness.UNPRICED
        return CostCompleteness.PARTIAL

    @property
    def missing_pricing(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                str(item.unpriced_reason)
                for item in self.unpriced
                if item.unpriced_reason is not None
            )
        )

    @property
    def missing_quantity(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                f"{ref}: the usage record exposed no costable quantity, so there is "
                "nothing to price"
                for ref in self.skipped
            )
        )

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                set(self.missing_pricing)
                | set(self.missing_quantity)
                | {str(item) for item in self.conflicts}
            )
        )

    # -- outcome accounting ------------------------------------------------

    def with_outcome(self, outcome: str) -> tuple[UsageCostAttribution, ...]:
        return tuple(item for item in self.attributions if item.outcome == outcome)

    @property
    def accepted_cost(self) -> dict[str, Money]:
        return _totals(self.with_outcome(ACCEPTED))

    @property
    def rejected_cost(self) -> dict[str, Money]:
        """Rejected work is a cost, not an absence. It is never discarded here."""
        return _totals(self.with_outcome(REJECTED))

    @property
    def abandoned_cost(self) -> dict[str, Money]:
        return _totals(self.with_outcome(ABANDONED))

    @property
    def retry_bearing_cost(self) -> dict[str, Money]:
        """Cost of attempts that retried. See `RETRY_SEMANTICS` for what that is not."""
        refs = {
            observation.usage_ref
            for observation in self.observations
            if observation.retries > 0
        }
        return _totals(item for item in self.attributions if item.usage_ref in refs)

    @property
    def retry_bearing_attempts(self) -> int:
        return sum(1 for item in self.observations if item.retries > 0)

    @property
    def rework_cost(self) -> dict[str, Money]:
        """What the unsuccessful attempts on eventually-accepted tasks cost.

        This is the part of a cost-per-accepted figure that a naive reading
        drops: the tries it took to get there. Reported separately so that the
        figure can be read either way.
        """
        accepted_tasks = self.accepted_tasks
        return _totals(
            item
            for item in self.attributions
            if item.task_id in accepted_tasks and item.outcome != ACCEPTED
        )

    @property
    def accepted_tasks(self) -> frozenset[str]:
        """Tasks with at least one accepted attempt. The deliverables that landed."""
        return frozenset(
            observation.task_id
            for observation in self.observations
            if observation.outcome == ACCEPTED
        )

    @property
    def outcomes_known(self) -> bool:
        """False when any observation left its outcome unstated."""
        return bool(self.observations) and all(
            observation.outcome in OUTCOMES for observation in self.observations
        )

    # -- descriptive views -------------------------------------------------

    def _group(self, key: str, refs: set[str]) -> GroupCost:
        members = tuple(
            observation
            for observation in self.observations
            if observation.usage_ref in refs
        )
        lines = tuple(item for item in self.attributions if item.usage_ref in refs)
        return GroupCost(
            key=key,
            samples=len(members),
            accepted=sum(1 for item in members if item.outcome == ACCEPTED),
            rejected=sum(1 for item in members if item.outcome == REJECTED),
            abandoned=sum(1 for item in members if item.outcome == ABANDONED),
            known_cost=_totals(lines),
            unpriced=sum(1 for item in lines if not item.is_priced),
        )

    def _grouped(self, attribute: str) -> tuple[GroupCost, ...]:
        keys: dict[str, set[str]] = {}
        for observation in self.observations:
            key = getattr(observation, attribute) or "unstated"
            keys.setdefault(key, set()).add(observation.usage_ref)
        return tuple(self._group(key, refs) for key, refs in sorted(keys.items()))

    @property
    def by_reasoning_class(self) -> tuple[GroupCost, ...]:
        """Cost by resource class. Sorted by class, never by cost: see `DESCRIPTIVE_ONLY`."""
        return self._grouped("reasoning_class")

    @property
    def by_executor(self) -> tuple[GroupCost, ...]:
        """Cost by executor. No ranking, and no arithmetic branches on the key."""
        return self._grouped("executor")

    @property
    def expansion_view(self) -> ExpansionCostView:
        expanded = {
            observation.usage_ref
            for observation in self.observations
            if observation.expansion_count > 0
        }
        expanded_lines = tuple(
            item for item in self.attributions if item.usage_ref in expanded
        )
        plain_lines = tuple(
            item for item in self.attributions if item.usage_ref not in expanded
        )
        members = tuple(
            observation
            for observation in self.observations
            if observation.usage_ref in expanded
        )
        return ExpansionCostView(
            attempts_with_expansion=len(members),
            attempts_requiring_expansion=sum(
                1 for item in members if item.required_expansion
            ),
            expansion_chars=sum(item.expansion_chars for item in members),
            accepted_with_expansion=sum(
                1 for item in members if item.outcome == ACCEPTED
            ),
            rejected_with_expansion=sum(
                1 for item in members if item.outcome == REJECTED
            ),
            known_cost_with_expansion=_totals(expanded_lines),
            known_cost_without_expansion=_totals(plain_lines),
            unpriced_with_expansion=sum(
                1 for item in expanded_lines if not item.is_priced
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "as_of": self.as_of.isoformat(),
            "usage_refs_inspected": list(self.usage_refs_inspected),
            "attributions": [item.to_dict() for item in self.attributions],
            "conflicts": [str(item) for item in self.conflicts],
            "skipped": list(self.skipped),
            "known_cost": _money_text(self.known_cost),
            "completeness": self.completeness.value,
            "missing_pricing": list(self.missing_pricing),
            "missing_quantity": list(self.missing_quantity),
            "evidence": [
                {"kind": item.kind, "ref": item.ref, "note": item.note}
                for item in self.evidence
            ],
            "caveats": list(self.caveats),
        }


def attribute_usage_costs(
    observations: Iterable[UsageObservation],
    card: RateCard,
    *,
    as_of: Any,
    evidence: Iterable[Evidence] = (),
) -> UsageCostAttributionRun:
    """Price every costable quantity in `observations`, keeping every gap visible.

    Deterministic in both directions: the attributions come out in the order the
    observations went in, and `run_id` is a digest of the inputs, so the same
    usage priced with the same card on the same day is the same run.
    """
    if not isinstance(card, RateCard):
        raise FinanceError(
            "attribute_usage_costs needs a RateCard. Pricing is supplied data, and an "
            "implicit default rate card is how a provider price becomes a constant"
        )
    day = assert_day(as_of, "as_of")
    ordered = tuple(observations)
    attributions: list[UsageCostAttribution] = []
    conflicts: list[AttributionConflict] = []
    skipped: list[str] = []
    for observation in ordered:
        if not observation.has_costable_quantity:
            skipped.append(observation.usage_ref)
            continue
        for mapping in observation.mappings:
            attribution = _attribute_one(observation, mapping, card)
            attributions.append(attribution)
            if attribution.conflict is not None:
                conflicts.append(attribution.conflict)
    collected = evidence_tuple(tuple(evidence)) if evidence else ()
    seen: dict[tuple[str, str, str], Evidence] = {
        (item.kind, item.ref, item.note): item for item in collected
    }
    for observation in ordered:
        for item in observation.evidence:
            seen.setdefault((item.kind, item.ref, item.note), item)
    return UsageCostAttributionRun(
        run_id=_fingerprint(
            {
                "as_of": day.isoformat(),
                "observations": [
                    {"lineage": item.lineage, "usage_ref": item.usage_ref}
                    for item in ordered
                ],
                "rates": sorted(rate.rate_id for rate in card),
            }
        ),
        as_of=day,
        observations=ordered,
        attributions=tuple(attributions),
        conflicts=tuple(conflicts),
        skipped=tuple(skipped),
        evidence=tuple(seen[key] for key in sorted(seen)),
    )


# --------------------------------------------------------------------------
# Cost per accepted deliverable
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CostPerAccepted:
    """The figure, or the named reasons there is not one.

    `amount` is `None` whenever the cost is incomplete, the count is unknown, or
    the run spans more than one currency. Dividing a partial cost by a count
    produces a number that looks like a unit cost and understates it by exactly
    the part nobody priced, which is the most confidently wrong figure this
    module could emit.
    """

    amount: Money | None
    scope: AttributionScope
    accepted_deliverables: int | None
    numerator: dict[str, Money]
    completeness: CostCompleteness
    missing: tuple[str, ...]

    @property
    def is_known(self) -> bool:
        return self.amount is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "amount": self.amount.to_dict() if self.amount is not None else None,
            "scope": self.scope.value,
            "accepted_deliverables": self.accepted_deliverables,
            "numerator": _money_text(self.numerator),
            "completeness": self.completeness.value,
            "missing": list(self.missing),
        }


def cost_per_accepted_deliverable(
    run: UsageCostAttributionRun,
    *,
    scope: AttributionScope = AttributionScope.ALL_ATTEMPTS,
    accepted_deliverables: int | None = None,
) -> CostPerAccepted:
    """Cost per accepted deliverable, or unknown with the reasons it is unknown.

    `ALL_ATTEMPTS` is the default because the question is what an accepted
    deliverable *cost*, and the rejected attempts on the way to it were paid for.
    `ACCEPTED_ONLY` is available and has to be asked for, so that a figure which
    excludes rework is never produced by accident.

    `accepted_deliverables` defaults to the number of distinct tasks with an
    accepted attempt. A caller who ships one video from three accepted tasks
    supplies the count instead.
    """
    if not isinstance(scope, AttributionScope):
        raise FinanceError("scope must be an AttributionScope value")
    lines = (
        run.attributions
        if scope is AttributionScope.ALL_ATTEMPTS
        else run.with_outcome(ACCEPTED)
    )
    numerator = _totals(lines)
    missing: list[str] = []
    completeness = run.completeness
    if completeness is not CostCompleteness.COMPLETE:
        missing.append(
            f"cost is {completeness.value}: "
            + (
                "; ".join(run.missing[:4])
                if run.missing
                else "no costable quantity was measured"
            )
        )
    count = accepted_deliverables
    if count is None:
        if not run.outcomes_known:
            missing.append(
                "at least one observation states no outcome, so the accepted count "
                "cannot be derived; supply accepted_deliverables"
            )
        else:
            count = len(run.accepted_tasks)
    elif isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise FinanceError(
            f"accepted_deliverables must be a non-negative whole number, got {count!r}"
        )
    if count == 0:
        missing.append("no accepted deliverable in scope, so there is nothing to divide by")
    if len(numerator) > 1:
        missing.append(
            "costs are recorded in "
            + ", ".join(sorted(numerator))
            + "; nothing here converts a currency, so there is no single figure"
        )
    if not numerator:
        missing.append("no cost was priced, so there is no numerator")
    amount = (
        next(iter(numerator.values())).divided_by(count)
        if not missing and count
        else None
    )
    return CostPerAccepted(
        amount=amount,
        scope=scope,
        accepted_deliverables=count,
        numerator=numerator,
        completeness=completeness,
        missing=tuple(missing),
    )


# --------------------------------------------------------------------------
# Committing: attributions become canonical CostRecords
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Restatement:
    """A committed cost this run would price differently. Never applied silently."""

    lineage_id: str
    existing_cost_id: str
    incoming_cost_id: str
    detail: str

    def __str__(self) -> str:
        return (
            f"{self.lineage_id} is already recorded as {self.existing_cost_id}; this "
            f"run would record {self.incoming_cost_id}. {self.detail}"
        )


@dataclass(frozen=True)
class AttributionCommit:
    """What a commit wrote, or - under `dry_run` - what it would have written."""

    run_id: str
    dry_run: bool
    costs: tuple[CostRecord, ...]
    mappings: tuple[ResourceCostMapping, ...]
    unchanged: tuple[str, ...]
    restatements: tuple[Restatement, ...]

    @property
    def written(self) -> int:
        return 0 if self.dry_run else len(self.costs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "dry_run": self.dry_run,
            "costs": [record.cost_id for record in self.costs],
            "mappings": [record.mapping_id for record in self.mappings],
            "unchanged": list(self.unchanged),
            "restatements": [str(item) for item in self.restatements],
            "written": self.written,
        }


def _cost_from(
    attribution: UsageCostAttribution,
    *,
    recorded_by: str,
    recorded_on: dt.date,
    supersedes: str = "",
) -> CostRecord:
    """The canonical record for one priced attribution.

    `VARIABLE` is not a judgement call here: a measured quantity of tokens, calls
    or seconds is by definition the part of the bill that moves with output.
    `DIRECT` likewise - this cost was measured against this subject, so no share
    of anything was computed and `costs.py` would refuse an allocation method.
    """
    if attribution.amount is None:  # pragma: no cover - guarded by the caller
        raise FinanceError(
            f"attribution {attribution.attribution_id!r} has no amount; an unpriced "
            "quantity does not become a cost record"
        )
    return CostRecord(
        cost_id=attribution.attribution_id,
        incurred_on=attribution.measured_on,
        amount=attribution.amount,
        category=attribution.category,
        subject=attribution.subject,
        source=attribution.usage_ref,
        evidence=attribution.evidence,
        recorded_by=recorded_by,
        recorded_on=recorded_on,
        recurrence=Recurrence.ONE_TIME,
        variability=Variability.VARIABLE,
        attribution=Attribution.DIRECT,
        resource_ref=attribution.usage_ref,
        supersedes=supersedes,
        notes=(
            f"{attribution.quantity} {attribution.unit.value} "
            f"({attribution.measure.value}) measured for task "
            f"{attribution.task_id}"
            + (f" attempt {attribution.attempt}" if attribution.attempt else "")
            + f", priced at rate {attribution.rate_id} from provider "
            f"{attribution.provider}"
            + (f", executor {attribution.executor}" if attribution.executor else "")
            + (f", outcome {attribution.outcome}" if attribution.outcome else "")
        ),
    )


def commit_attribution_costs(
    run: UsageCostAttributionRun,
    store: Any,
    *,
    recorded_by: str,
    recorded_on: Any,
    dry_run: bool = False,
    allow_restatement: bool = False,
) -> AttributionCommit:
    """Turn every priced attribution into a `CostRecord`, writing nothing on a dry run.

    Replay is free: an unchanged attribution produces byte-identical content and
    `FinanceStore.put` treats that as a no-op, so running this twice over the
    same usage and the same card records one cost.

    A *changed* price is the case worth being careful about. The lineage half of
    the id still matches, so an already-recorded cost for the same quantity is
    found, and by default the incoming record is refused and reported as a
    `Restatement`. Passing `allow_restatement` writes it with `supersedes` set,
    which is `costs.py`'s own correction mechanism - the old number stays in the
    ledger either way.

    The store is taken duck-typed (`list`, `put`) so a dry run needs no store at
    all and a caller can pass any append-only sink with those two methods.
    """
    day = assert_day(recorded_on, "recorded_on")
    if not isinstance(recorded_by, str) or not recorded_by.strip():
        raise FinanceError("recorded_by must name whoever ran the attribution")
    existing: dict[str, str] = {}
    if store is not None:
        for record in store.list("cost"):
            cost_id = record.cost_id
            if cost_id.startswith(f"{ID_PREFIX}.") and cost_id.count(".") >= 3:
                existing[cost_id.rsplit(".", 1)[0]] = cost_id
    costs: list[CostRecord] = []
    mappings: list[ResourceCostMapping] = []
    unchanged: list[str] = []
    restatements: list[Restatement] = []
    by_ref = {
        observation.usage_ref: observation for observation in run.observations
    }
    for attribution in run.priced:
        recorded = existing.get(attribution.lineage_id)
        if recorded == attribution.attribution_id:
            unchanged.append(attribution.attribution_id)
            continue
        supersedes = ""
        if recorded is not None:
            restatement = Restatement(
                lineage_id=attribution.lineage_id,
                existing_cost_id=recorded,
                incoming_cost_id=attribution.attribution_id,
                detail=(
                    "The rate, the date or the evidence changed. Financial history is "
                    "append-only: pass allow_restatement to record a superseding cost, "
                    "which keeps the original number in the ledger"
                ),
            )
            restatements.append(restatement)
            if not allow_restatement:
                continue
            supersedes = recorded
        costs.append(
            _cost_from(
                attribution,
                recorded_by=recorded_by,
                recorded_on=day,
                supersedes=supersedes,
            )
        )
        observation = by_ref.get(attribution.usage_ref)
        if observation is not None:
            mappings.extend(
                mapping
                for mapping in observation.mappings
                if mapping.mapping_id == attribution.lineage_id
            )
    if not dry_run and store is not None:
        # Mappings first: the measured quantity is the evidence the cost cites,
        # and a half-written pair is more readable in that order.
        store.put_all(mappings)
        store.put_all(costs)
    return AttributionCommit(
        run_id=run.run_id,
        dry_run=dry_run,
        costs=tuple(costs),
        mappings=tuple(mappings),
        unchanged=tuple(unchanged),
        restatements=tuple(restatements),
    )


# --------------------------------------------------------------------------
# The dogfood report
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DogfoodReport:
    """The compact answer to section 18, and nothing that resembles a score.

    Every field is a count, a per-currency amount or a named gap. There is no
    efficiency number, because one figure over these dimensions would be
    optimised in place of the objective it approximates - constitution rule 3.
    """

    run_id: str
    as_of: dt.date
    usage_records_inspected: int
    attributions: int
    priced: int
    unpriced: int
    skipped: int
    conflicts: int
    known_cost: dict[str, Money]
    accepted_cost: dict[str, Money]
    rejected_cost: dict[str, Money]
    abandoned_cost: dict[str, Money]
    retry_bearing_cost: dict[str, Money]
    retry_bearing_attempts: int
    rework_cost: dict[str, Money]
    accepted_deliverables: int | None
    cost_per_accepted: CostPerAccepted
    completeness: CostCompleteness
    missing: tuple[str, ...]
    by_reasoning_class: tuple[GroupCost, ...]
    by_executor: tuple[GroupCost, ...]
    expansion: ExpansionCostView
    caveats: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "as_of": self.as_of.isoformat(),
            "usage_records_inspected": self.usage_records_inspected,
            "attributions": self.attributions,
            "priced": self.priced,
            "unpriced": self.unpriced,
            "skipped": self.skipped,
            "conflicts": self.conflicts,
            "known_cost": _money_text(self.known_cost),
            "accepted_cost": _money_text(self.accepted_cost),
            "rejected_cost": _money_text(self.rejected_cost),
            "abandoned_cost": _money_text(self.abandoned_cost),
            "retry_bearing_cost": _money_text(self.retry_bearing_cost),
            "retry_bearing_attempts": self.retry_bearing_attempts,
            "rework_cost": _money_text(self.rework_cost),
            "accepted_deliverables": self.accepted_deliverables,
            "cost_per_accepted": self.cost_per_accepted.to_dict(),
            "completeness": self.completeness.value,
            "missing": list(self.missing),
            "by_reasoning_class": [item.to_dict() for item in self.by_reasoning_class],
            "by_executor": [item.to_dict() for item in self.by_executor],
            "expansion": self.expansion.to_dict(),
            "caveats": list(self.caveats),
        }


def dogfood_report(
    run: UsageCostAttributionRun,
    *,
    scope: AttributionScope = AttributionScope.ALL_ATTEMPTS,
    accepted_deliverables: int | None = None,
) -> DogfoodReport:
    """How many records, how many priced, what is known, and what is missing."""
    per_accepted = cost_per_accepted_deliverable(
        run, scope=scope, accepted_deliverables=accepted_deliverables
    )
    return DogfoodReport(
        run_id=run.run_id,
        as_of=run.as_of,
        usage_records_inspected=len(run.observations),
        attributions=len(run.attributions),
        priced=len(run.priced),
        unpriced=len(run.unpriced),
        skipped=len(run.skipped),
        conflicts=len(run.conflicts),
        known_cost=run.known_cost,
        accepted_cost=run.accepted_cost,
        rejected_cost=run.rejected_cost,
        abandoned_cost=run.abandoned_cost,
        retry_bearing_cost=run.retry_bearing_cost,
        retry_bearing_attempts=run.retry_bearing_attempts,
        rework_cost=run.rework_cost,
        accepted_deliverables=per_accepted.accepted_deliverables,
        cost_per_accepted=per_accepted,
        completeness=run.completeness,
        missing=run.missing,
        by_reasoning_class=run.by_reasoning_class,
        by_executor=run.by_executor,
        expansion=run.expansion_view,
        caveats=run.caveats,
    )

"""What the work cost, read from records the caller supplies.

## It takes records, it does not fetch them

`company/runtime/usage_store.py` owns where usage records live and
`ai_platform/usage.py` owns what they mean. This module imports neither store
and reads no filesystem: `ResourceEvidence.from_records` takes an iterable and
`from_summary` takes an already-computed `ResourceSummary`. That keeps the
subsystem testable with a list of objects, keeps it out of the runtime
workstream's way, and makes the one thing it does - notice patterns across
attempts - separable from where the attempts were stored.

## It works with no token counts

This is the constraint `ai_platform/usage.py` was built around and it survives
the trip. `passes_per_accepted` comes from counters we observe ourselves and is
always available; `units_per_accepted` is `None` whenever the provider exposed
nothing or two incompatible units were mixed, and a `None` here becomes an entry
in `missing_measurements` rather than a zero. A signal set computed over records
with no unit accounting at all is complete and useful, and it says which numbers
it never had.

## Rejections are in the denominator

Also inherited: a rejected attempt consumed what an accepted one would have. So
`resources_per_accepted` counts every pass and divides by the accepted ones,
which is what makes the metric tell the truth about a cheap approach that keeps
failing.

## Context expansion

`context_expansions` is an optional caller-supplied count and defaults to
`None`. The runtime capability that would produce it is another workstream's;
until a caller passes one, the pressure signal is computed from unused context
references instead, and the expansion count stays honestly missing.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from ai_platform.serde import to_jsonable
from ai_platform.usage import (
    Outcome,
    ResourceSummary,
    ResourceUsageRecord,
    UsageLedger,
)
from knowledge.company_os.records import Evidence

from .common import positive_int, ratio
from .errors import OrgIntelligenceError
from .signals import (
    Direction,
    Measurement,
    OrganizationalSignal,
    SignalType,
    SubjectKind,
)
from .window import ReviewWindow


@dataclass(frozen=True)
class ResourcePolicy:
    """The efficiency thresholds, stated so a review can record what it used."""

    passes_per_accepted_threshold: float = 3.0
    first_pass_rate_threshold: float = 0.5
    rejection_rate_threshold: float = 0.5
    retries_per_record_threshold: float = 1.0
    unused_context_share_threshold: float = 0.5
    context_expansions_threshold: float = 2.0
    minimum_records: int = 3

    def __post_init__(self) -> None:
        for name in (
            "passes_per_accepted_threshold",
            "first_pass_rate_threshold",
            "rejection_rate_threshold",
            "retries_per_record_threshold",
            "unused_context_share_threshold",
            "context_expansions_threshold",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise OrgIntelligenceError(f"{name} must be a positive number")
        positive_int(self.minimum_records, "minimum_records")


DEFAULT_RESOURCE_POLICY = ResourcePolicy()


@dataclass(frozen=True)
class ResourceEvidence:
    """One scope's attempts, folded to the numbers an organization can act on.

    `scope` is whatever the caller grouped by - a workflow, a role, a task
    class. This module never decides the grouping, because the grouping is the
    question being asked and inventing one would answer a different question.
    """

    scope: str
    records: int
    accepted: int
    rejected: int
    abandoned: int
    passes: int
    retries: int
    unused_context_refs: int
    context_refs_supplied: int | None = None
    tool_calls: int | None = None
    duration_s: float | None = None
    passes_per_accepted: float | None = None
    units_per_accepted: float | None = None
    first_pass_success_rate: float | None = None
    context_expansions: int | None = None
    subagents_used: int = 0

    @classmethod
    def from_records(
        cls,
        scope: str,
        records: Iterable[ResourceUsageRecord],
        *,
        context_expansions: int | None = None,
    ) -> ResourceEvidence:
        """Fold usage records through the ledger that already knows how.

        `UsageLedger.summarise` is the one implementation of these sums
        (constitution rule 15); this adds only the two counts the summary does
        not carry - how many context references were supplied, and how many
        subagents were used, which under a bootstrap policy must be zero.
        """
        items = tuple(records)
        ledger = UsageLedger()
        for record in items:
            if not isinstance(record, ResourceUsageRecord):
                raise OrgIntelligenceError(
                    "from_records takes ai_platform ResourceUsageRecord objects"
                )
            ledger.add(record)
        supplied = sum(len(record.context_sources) for record in items) if items else None
        return cls.from_summary(
            scope,
            ledger.summarise(),
            context_refs_supplied=supplied,
            context_expansions=context_expansions,
            subagents_used=sum(record.subagents_used for record in items),
        )

    @classmethod
    def from_summary(
        cls,
        scope: str,
        summary: ResourceSummary,
        *,
        context_refs_supplied: int | None = None,
        context_expansions: int | None = None,
        subagents_used: int = 0,
    ) -> ResourceEvidence:
        if not isinstance(summary, ResourceSummary):
            raise OrgIntelligenceError("from_summary takes an ai_platform ResourceSummary")
        return cls(
            scope=scope,
            records=summary.records,
            accepted=summary.accepted,
            rejected=summary.rejected,
            abandoned=summary.abandoned,
            passes=summary.passes,
            retries=summary.retries,
            unused_context_refs=summary.unused_context_refs,
            context_refs_supplied=context_refs_supplied,
            tool_calls=summary.tool_calls,
            duration_s=summary.duration_s,
            passes_per_accepted=summary.passes_per_accepted,
            units_per_accepted=summary.units_per_accepted,
            first_pass_success_rate=summary.first_pass_success_rate,
            context_expansions=context_expansions,
            subagents_used=subagents_used,
        )

    # -- derived rates, each `None` rather than zero when undivisible --------

    @property
    def rejection_rate(self) -> float | None:
        return ratio(self.rejected, self.records)

    @property
    def acceptance_rate(self) -> float | None:
        return ratio(self.accepted, self.records)

    @property
    def retries_per_record(self) -> float | None:
        return ratio(self.retries, self.records)

    @property
    def unused_context_share(self) -> float | None:
        return ratio(self.unused_context_refs, self.context_refs_supplied)

    @property
    def missing_measurements(self) -> tuple[str, ...]:
        """Everything nobody could measure, named. Deliberately not a footnote."""
        out: list[str] = []
        if self.units_per_accepted is None:
            out.append(
                "units per accepted deliverable: the provider exposed no unit accounting, "
                "or two incompatible units were mixed"
            )
        if self.tool_calls is None:
            out.append("tool calls: not every record reported one")
        if self.duration_s is None:
            out.append("duration: not every record reported one")
        if self.context_refs_supplied is None:
            out.append("context references supplied: no record carried a context manifest")
        if self.context_expansions is None:
            out.append(
                "context expansions: no caller supplied a count; the runtime capability "
                "that would produce it is not consumed here"
            )
        if self.first_pass_success_rate is None:
            out.append("first-pass success rate: nothing was accepted, so there is no rate")
        return tuple(out)

    def to_dict(self) -> dict[str, Any]:
        base = to_jsonable(self)
        base.update(
            rejection_rate=self.rejection_rate,
            acceptance_rate=self.acceptance_rate,
            retries_per_record=self.retries_per_record,
            unused_context_share=self.unused_context_share,
            missing_measurements=list(self.missing_measurements),
        )
        return base


def resource_signals(
    evidence: ResourceEvidence,
    *,
    window: ReviewWindow,
    policy: ResourcePolicy = DEFAULT_RESOURCE_POLICY,
    evidence_refs: Iterable[Evidence] = (),
    prefix: str = "sig-res",
) -> tuple[OrganizationalSignal, ...]:
    """Every efficiency signal the supplied records support, in a stable order.

    A signal is emitted only where a measurement exists and crosses its own
    declared threshold. Where the number is missing, nothing is emitted and the
    absence is carried on the evidence object - an unmeasured cost is not a low
    one, and a signal saying so would be inventing the number the brief forbids.
    """
    if not isinstance(evidence, ResourceEvidence):
        raise OrgIntelligenceError("resource_signals takes a ResourceEvidence")
    pointers = tuple(evidence_refs) or (
        Evidence(
            kind="measurement",
            ref=f"ai_platform/usage.py#{evidence.scope}",
            note=f"{evidence.records} usage record(s) summarised by the caller",
        ),
    )
    stem = f"{prefix}-{evidence.scope.replace('_', '-').replace('/', '-')}"
    absences = evidence.missing_measurements
    out: list[OrganizationalSignal] = []

    for value, signal_type, threshold, direction, unit, detail in (
        (
            evidence.passes_per_accepted,
            SignalType.HIGH_RESOURCE_PER_ACCEPTANCE,
            policy.passes_per_accepted_threshold,
            Direction.HIGHER_IS_WORSE,
            "passes_per_accepted",
            "passes per accepted deliverable",
        ),
        (
            evidence.first_pass_success_rate,
            SignalType.POOR_FIRST_PASS_RATE,
            policy.first_pass_rate_threshold,
            Direction.LOWER_IS_WORSE,
            "rate",
            "accepted on the first pass",
        ),
        (
            evidence.rejection_rate,
            SignalType.HIGH_REJECTION_RATE,
            policy.rejection_rate_threshold,
            Direction.HIGHER_IS_WORSE,
            "rate",
            "attempts rejected",
        ),
        (
            evidence.retries_per_record,
            SignalType.REPEATED_RETRY_PATTERN,
            policy.retries_per_record_threshold,
            Direction.HIGHER_IS_WORSE,
            "retries_per_record",
            "retries per attempt",
        ),
        (
            evidence.unused_context_share,
            SignalType.CONTEXT_EXPANSION_PRESSURE,
            policy.unused_context_share_threshold,
            Direction.HIGHER_IS_WORSE,
            "rate",
            "supplied context references never used",
        ),
    ):
        measurement = Measurement(
            value=value,
            unit=unit if value is not None else "",
            threshold=threshold,
            direction=direction,
            sample_size=evidence.records,
            minimum_sample=policy.minimum_records,
        )
        if measurement.breaches_threshold is not True:
            continue
        out.append(
            OrganizationalSignal(
                signal_id=f"{stem}-{signal_type.value.replace('_', '-')}",
                type=signal_type,
                subject=evidence.scope,
                subject_kind=SubjectKind.WORKFLOW,
                window=window,
                detail=(
                    f"{evidence.scope}: {value:.3g} {detail} over {evidence.records} "
                    f"record(s), against a {threshold:.3g} threshold"
                ),
                measurement=measurement,
                evidence=pointers,
                missing_measurements=absences,
                source_refs=("ai_platform/usage.py",),
            )
        )

    if (
        evidence.context_expansions is not None
        and evidence.context_expansions > policy.context_expansions_threshold
    ):
        out.append(
            OrganizationalSignal(
                signal_id=f"{stem}-context-expansion-count",
                type=SignalType.CONTEXT_EXPANSION_PRESSURE,
                subject=evidence.scope,
                subject_kind=SubjectKind.WORKFLOW,
                window=window,
                detail=(
                    f"{evidence.scope}: {evidence.context_expansions} context expansion(s) "
                    f"over {evidence.records} record(s), against a "
                    f"{policy.context_expansions_threshold:.3g} threshold"
                ),
                measurement=Measurement(
                    value=float(evidence.context_expansions),
                    unit="expansions",
                    threshold=float(policy.context_expansions_threshold),
                    direction=Direction.HIGHER_IS_WORSE,
                    sample_size=evidence.records,
                    minimum_sample=policy.minimum_records,
                ),
                evidence=pointers,
                source_refs=("ai_platform/usage.py",),
            )
        )
    return tuple(out)


def attempt_pattern(records: Iterable[ResourceUsageRecord]) -> dict[str, int]:
    """Accepted, rejected and abandoned counts. The denominators, plainly.

    Here so a caller can see the pattern without building a `ResourceEvidence`,
    and so a test can check that rejected attempts are counted rather than
    filtered out of the picture.
    """
    items = tuple(records)
    return {
        "records": len(items),
        "accepted": sum(1 for item in items if item.outcome is Outcome.ACCEPTED),
        "rejected": sum(1 for item in items if item.outcome is Outcome.REJECTED),
        "abandoned": sum(1 for item in items if item.outcome is Outcome.ABANDONED),
        "retries": sum(item.retries for item in items),
        "passes": sum(item.passes for item in items),
    }

"""Workforce records, read as organizational signals. Nothing is recomputed.

## Two layers, one fact

`company/workforce/coverage.py` answers *who can do this work*. It already knows
that `mobile_readability` has exactly one organizational provider, and it says
so in `CapabilityCoverage.is_single_point_of_failure`. This module does not work
that out again; it reads the answer and says what it means for the company: a
critical single point of failure exists, over this window, with this evidence.

The brief is explicit that those are different layers, and the code keeps them
apart by construction - there is no capability graph here, no provider
derivation, no hiring decision table, and no second organizational-debt ledger.
Every function below takes records the workforce layer produced and returns
signals. If a number is wrong, there is exactly one place it was computed.

## The inversion that had to be carried across

`company/workforce/necessity.py` refuses to recommend archiving a role while a
uniqueness signal is present, because archiving the sole provider of a core
capability is the confidently-wrong answer that does damage. The same trap is
here in a different shape: a capability covered only by a dormant employee looks
identical to an uncovered one if you count active providers alone.
`signals_from_coverage` emits `DORMANT_CAPABILITY`, never a gap, and
`recommendations.py` maps that to `activate_dormant_employee` - so the cheap
answer cannot turn into a hire by passing through this layer.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from company.workforce.coverage import CapabilityCoverage, CoverageReport
from company.workforce.debt import DebtKind, OrganizationalDebt
from company.workforce.gaps import CapabilityGap, NeedFrequency
from company.workforce.necessity import NecessitySignal, RoleNecessityReview
from company.workforce.performance import CapabilityPerformance
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
class WorkforcePolicy:
    """Thresholds for reading workforce records. Opinions, held in one place.

    These deliberately mirror `company/workforce/necessity.NecessityPolicy`
    rather than inventing a second scale: a rejection rate is high at the same
    place in both layers, or the company is telling itself two stories.
    """

    rejection_rate_threshold: float = 0.5
    escalation_rate_threshold: float = 0.5
    first_pass_rate_threshold: float = 0.5
    minimum_observations: int = 3
    recurring_gap_occurrences: int = 3

    def __post_init__(self) -> None:
        for name in (
            "rejection_rate_threshold",
            "escalation_rate_threshold",
            "first_pass_rate_threshold",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= 1:
                raise OrgIntelligenceError(f"{name} must be a rate in (0, 1]")
        positive_int(self.minimum_observations, "minimum_observations")
        positive_int(self.recurring_gap_occurrences, "recurring_gap_occurrences", minimum=2)


DEFAULT_WORKFORCE_POLICY = WorkforcePolicy()


def _slug(value: str) -> str:
    return value.replace("_", "-").replace("/", "-")


def signals_from_coverage(
    report: CoverageReport,
    *,
    window: ReviewWindow,
    evidence: Iterable[Evidence],
    prefix: str = "sig-cov",
) -> tuple[OrganizationalSignal, ...]:
    """Read a `CoverageReport` for risk. The counting was done by coverage.py.

    Two signal types come out, and keeping them apart is the whole point:
    `CRITICAL_SINGLE_POINT_FAILURE` for a capability with exactly one
    organizational provider, and `DORMANT_CAPABILITY` for one the company holds
    but is not running. The second is not a gap and must never become a hire.
    """
    if not isinstance(report, CoverageReport):
        raise OrgIntelligenceError("signals_from_coverage takes a workforce CoverageReport")
    supporting = tuple(evidence)
    if not supporting:
        raise OrgIntelligenceError(
            "coverage signals need a pointer to the coverage run that produced them"
        )
    out: list[OrganizationalSignal] = []
    for coverage in report.coverages:
        out.extend(_coverage_signals(coverage, window, supporting, prefix))
    return tuple(out)


def _coverage_signals(
    coverage: CapabilityCoverage,
    window: ReviewWindow,
    evidence: tuple[Evidence, ...],
    prefix: str,
) -> tuple[OrganizationalSignal, ...]:
    out: list[OrganizationalSignal] = []
    providers = coverage.organizational_providers
    if coverage.is_single_point_of_failure:
        out.append(
            OrganizationalSignal(
                signal_id=f"{prefix}-spof-{_slug(coverage.capability_id)}",
                type=SignalType.CRITICAL_SINGLE_POINT_FAILURE,
                subject=coverage.capability_id,
                subject_kind=SubjectKind.CAPABILITY,
                window=window,
                detail=(
                    f"{coverage.capability_id} ({coverage.criticality.value}) has one "
                    f"organizational provider: {providers[0]}"
                ),
                measurement=Measurement(
                    value=1.0,
                    unit="organizational_providers",
                    threshold=2.0,
                    direction=Direction.LOWER_IS_WORSE,
                ),
                evidence=evidence,
                caveats=(
                    "a single provider is a structural risk, not an incident; nothing "
                    "here says the provider is unavailable or overloaded",
                ),
                source_refs=("company/workforce/coverage.py",),
            )
        )
    if not coverage.covered_actively and coverage.dormant_providers:
        out.append(
            OrganizationalSignal(
                signal_id=f"{prefix}-dormant-{_slug(coverage.capability_id)}",
                type=SignalType.DORMANT_CAPABILITY,
                subject=coverage.capability_id,
                subject_kind=SubjectKind.CAPABILITY,
                window=window,
                detail=(
                    f"{coverage.capability_id} is held by "
                    + ", ".join(coverage.dormant_providers)
                    + " and nobody is running it. The company has this capability"
                ),
                measurement=Measurement(
                    value=float(len(coverage.dormant_providers)),
                    unit="dormant_providers",
                ),
                evidence=evidence,
                caveats=(
                    "constitution rule 18: a defined employee is not a running employee. "
                    "This is an activation question, never a hiring one",
                ),
                source_refs=("company/workforce/coverage.py",),
            )
        )
    return tuple(out)


def signals_from_gaps(
    gaps: Iterable[CapabilityGap],
    *,
    window: ReviewWindow,
    policy: WorkforcePolicy = DEFAULT_WORKFORCE_POLICY,
    prefix: str = "sig-gap",
) -> tuple[OrganizationalSignal, ...]:
    """One signal per recurring capability gap, counted by the gap record itself.

    Frequency is not inferred here for the same reason `gaps.py` refuses to
    infer it: the code will not decide that a need recurs. The occurrence count
    and its window come off `FrequencyEvidence`, which already refused to exist
    without them.
    """
    out: list[OrganizationalSignal] = []
    for gap in gaps:
        if not isinstance(gap, CapabilityGap):
            raise OrgIntelligenceError("signals_from_gaps takes workforce CapabilityGap records")
        frequency = gap.frequency
        recurring = frequency.frequency is NeedFrequency.RECURRING
        out.append(
            OrganizationalSignal(
                signal_id=f"{prefix}-{_slug(gap.gap_id)}",
                type=SignalType.CAPABILITY_GAP_FREQUENCY,
                subject=gap.gap_id,
                subject_kind=SubjectKind.CAPABILITY,
                window=window,
                detail=(
                    f"{gap.gap_id} is a {frequency.frequency.value} need for "
                    + ", ".join(gap.missing or gap.covered_dormant)
                    + f", observed {frequency.observed_occurrences} time(s)"
                    + (f" in {frequency.window_days} day(s)" if frequency.window_days else "")
                ),
                measurement=Measurement(
                    value=float(frequency.observed_occurrences),
                    unit="observed_occurrences",
                    threshold=float(policy.recurring_gap_occurrences),
                    direction=Direction.HIGHER_IS_WORSE,
                ),
                evidence=gap.evidence + frequency.evidence,
                caveats=(
                    ()
                    if recurring
                    else (
                        f"the gap record classifies this as {frequency.frequency.value}; a "
                        "count above the threshold does not reclassify it here",
                    )
                ),
                source_refs=("company/workforce/gaps.py",),
            )
        )
    return tuple(out)


def signals_from_performance(
    performances: Iterable[CapabilityPerformance],
    *,
    window: ReviewWindow,
    policy: WorkforcePolicy = DEFAULT_WORKFORCE_POLICY,
    prefix: str = "sig-perf",
) -> tuple[OrganizationalSignal, ...]:
    """Rejection, escalation and first-pass rates, scoped as the workforce scopes them.

    Per `(employee, capability)`, never per employee: `performance.py` explains
    at length why a single number for a person erases the information a staffing
    decision needs, and aggregating here would put it back.

    Small samples are emitted rather than suppressed, carrying the caveat the
    measurement generates. A rate over two tasks is a real observation and a
    weak one, and dropping it loses the observation.
    """
    out: list[OrganizationalSignal] = []
    for item in performances:
        if not isinstance(item, CapabilityPerformance):
            raise OrgIntelligenceError(
                "signals_from_performance takes workforce CapabilityPerformance records"
            )
        scope = f"{item.employee_id}/{item.capability_id}"
        stem = f"{prefix}-{_slug(item.employee_id)}-{_slug(item.capability_id)}"
        evidence = (
            Evidence(
                kind="observation",
                ref=f"company/workforce/performance.py#{scope}",
                note=f"{item.attempted} attempt(s) summarised by the workforce layer",
            ),
        )
        for rate, signal_type, threshold, direction, label in (
            (
                item.rejection_rate,
                SignalType.HIGH_REJECTION_RATE,
                policy.rejection_rate_threshold,
                Direction.HIGHER_IS_WORSE,
                "rejected",
            ),
            (
                item.escalation_rate,
                SignalType.HIGH_ESCALATION_RATE,
                policy.escalation_rate_threshold,
                Direction.HIGHER_IS_WORSE,
                "escalated",
            ),
            (
                item.first_pass_success_rate,
                SignalType.POOR_FIRST_PASS_RATE,
                policy.first_pass_rate_threshold,
                Direction.LOWER_IS_WORSE,
                "accepted first pass",
            ),
        ):
            measurement = Measurement(
                value=rate,
                unit="rate" if rate is not None else "",
                threshold=threshold,
                direction=direction,
                sample_size=item.attempted,
                minimum_sample=policy.minimum_observations,
            )
            if measurement.breaches_threshold is not True:
                continue
            out.append(
                OrganizationalSignal(
                    signal_id=f"{stem}-{signal_type.value.replace('_', '-')}",
                    type=signal_type,
                    subject=scope,
                    subject_kind=SubjectKind.EMPLOYEE,
                    window=window,
                    detail=(
                        f"{scope}: {rate:.0%} {label} over {item.attempted} attempt(s), "
                        f"against a {threshold:.0%} threshold"
                    ),
                    measurement=measurement,
                    evidence=evidence,
                    source_refs=("company/workforce/performance.py",),
                )
            )
    return tuple(out)


def signals_from_necessity(
    reviews: Iterable[RoleNecessityReview],
    *,
    window: ReviewWindow,
    prefix: str = "sig-nec",
) -> tuple[OrganizationalSignal, ...]:
    """Role overlap and idle roles, read off necessity reviews the HR layer ran.

    Only the two redundancy signals cross over. The protective ones
    (`unique_capability_coverage`, `critical_single_point_of_failure`) already
    reach this package through `signals_from_coverage`, and importing them twice
    would let one finding count the same fact as two.
    """
    out: list[OrganizationalSignal] = []
    for review in reviews:
        if not isinstance(review, RoleNecessityReview):
            raise OrgIntelligenceError(
                "signals_from_necessity takes workforce RoleNecessityReview records"
            )
        review_window = ReviewWindow(start=review.window_start, end=review.window_end)
        evidence = (
            Evidence(
                kind="document",
                ref=f"company/workforce/necessity.py#{review.employee_id}",
                note=f"necessity review over {review_window}",
            ),
        )
        signals = {finding.signal: finding for finding in review.findings}
        overlap = signals.get(NecessitySignal.DUPLICATE_CAPABILITY_COVERAGE)
        protective = review.protective_signals
        if overlap is not None:
            out.append(
                OrganizationalSignal(
                    signal_id=f"{prefix}-overlap-{_slug(review.employee_id)}",
                    type=SignalType.ROLE_OVERLAP,
                    subject=review.employee_id,
                    subject_kind=SubjectKind.EMPLOYEE,
                    window=window,
                    detail=overlap.detail,
                    measurement=Measurement(),
                    evidence=evidence,
                    missing_measurements=(
                        "overlap is a set relation, not a quantity; no cost of the "
                        "duplication was measured",
                    ),
                    caveats=(
                        ("this role is also a protective signal: " + ", ".join(protective),)
                        if protective
                        else ()
                    ),
                    source_refs=("company/workforce/necessity.py",),
                )
            )
        if NecessitySignal.NO_TASKS_IN_WINDOW in signals:
            out.append(
                OrganizationalSignal(
                    signal_id=f"{prefix}-unused-{_slug(review.employee_id)}",
                    type=SignalType.ROLE_UNUSED,
                    subject=review.employee_id,
                    subject_kind=SubjectKind.EMPLOYEE,
                    window=review_window,
                    detail=signals[NecessitySignal.NO_TASKS_IN_WINDOW].detail,
                    measurement=Measurement(value=0.0, unit="tasks_routed"),
                    evidence=evidence,
                    caveats=(
                        "a dormant employee costs nothing to keep (constitution rule 18); "
                        "no tasks routed is a question, not a verdict",
                    ),
                    source_refs=("company/workforce/necessity.py",),
                )
            )
    return tuple(out)


# Workforce debt kinds, mapped onto the signal vocabulary. The workforce layer
# owns the ledger (section 13 of the brief: do not build a second one); this is
# a reading of it, and a kind with no mapping is skipped rather than guessed.
DEBT_SIGNAL_TYPES: dict[DebtKind, SignalType] = {
    DebtKind.DUPLICATED_ROLE: SignalType.ROLE_OVERLAP,
    DebtKind.UNNECESSARY_MANAGEMENT_LAYER: SignalType.DUPLICATED_MANAGEMENT_LAYER,
    DebtKind.STALE_EMPLOYEE_DEFINITION: SignalType.STALE_CONTRACT,
    DebtKind.BLOATED_CONTRACT: SignalType.CONTRACT_BLOAT,
    DebtKind.UNUSED_CAPABILITY: SignalType.UNUSED_CAPABILITY,
    DebtKind.APPROVAL_BOTTLENECK: SignalType.APPROVAL_BOTTLENECK,
}


def signals_from_debt(
    debts: Iterable[OrganizationalDebt],
    *,
    window: ReviewWindow,
    prefix: str = "sig-debt",
) -> tuple[OrganizationalSignal, ...]:
    """Read existing `OrganizationalDebt` records. No second ledger is created."""
    out: list[OrganizationalSignal] = []
    for debt in debts:
        if not isinstance(debt, OrganizationalDebt):
            raise OrgIntelligenceError(
                "signals_from_debt takes workforce OrganizationalDebt records"
            )
        signal_type = DEBT_SIGNAL_TYPES.get(debt.kind)
        if signal_type is None:
            continue
        out.append(
            OrganizationalSignal(
                signal_id=f"{prefix}-{_slug(debt.debt_id)}",
                type=signal_type,
                subject=debt.subject_ref,
                subject_kind=SubjectKind.ORGANIZATION,
                window=window,
                detail=debt.detail,
                evidence=debt.evidence
                or (
                    Evidence(
                        kind="document",
                        ref=f"company/workforce/debt.py#{debt.debt_id}",
                        note=f"{debt.kind.value}, recorded {debt.observed_on.isoformat()}",
                    ),
                ),
                missing_measurements=(
                    f"{debt.kind.value} is recorded as a shape, not a cost; its severity "
                    f"is {debt.severity.value}, asserted by whoever filed it",
                ),
                source_refs=("company/workforce/debt.py",),
            )
        )
    return tuple(out)


def gap_recurrence(gaps: Iterable[CapabilityGap]) -> tuple[tuple[str, int], ...]:
    """(capability, times it was missing) across the supplied gaps, sorted.

    A count over records somebody else produced, not a new judgement about
    whether a need recurs - each gap already carries its own frequency claim and
    the counting that had to back it.
    """
    counts: dict[str, int] = {}
    for gap in gaps:
        for capability_id in gap.missing:
            counts[capability_id] = counts.get(capability_id, 0) + 1
    return tuple(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def acceptance_ratio(performances: Iterable[CapabilityPerformance]) -> float | None:
    """Accepted over attempted across the supplied scopes, or `None`.

    Not a score for anyone: the scope is whatever the caller passed, and the
    return is `None` rather than zero when nothing was attempted.
    """
    items = tuple(performances)
    return ratio(
        sum(item.accepted for item in items), sum(item.attempted for item in items)
    )

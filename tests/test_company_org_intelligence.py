"""Tests for Company OS Organizational Intelligence.

The suite is organised by the question each group answers, because the
interesting failures here are organizational rather than numerical: not "is this
float right" but "can this subsystem approve its own recommendation".

Seven groups are guard tests rather than behaviour tests - they assert the
*absence* of something:

    test_no_global_company_score_field_exists
    test_the_package_contains_no_writer_for_a_canonical_contract
    test_running_the_analysis_does_not_touch_a_company_contract
    test_org_intelligence_imports_no_production_module
    test_no_dependency_is_added
    test_no_recommendation_applies_itself
    test_the_no_subagent_policy_is_where_it_was

Each encodes a rule that would otherwise live only in a docstring, and a rule
that lives only in a docstring comes back.
"""

from __future__ import annotations

import ast
import dataclasses
import datetime as dt
import json
from pathlib import Path

import pytest

from ai_platform.resource_classes import ReasoningClass
from ai_platform.serde import dumps
from ai_platform.usage import Outcome, ResourceUsageRecord, UsageUnit
from company.org_intelligence import (
    AUTOMATIC_MARKERS,
    CANONICAL_CONTRACTS,
    CAUSALITY_CAVEAT,
    CONSTITUTIONAL_POLICIES,
    SINGLE_BATCH_LIMITATION,
    SINGLE_OBSERVATION_CAVEAT,
    AdvisoryViolation,
    ApprovalAuthority,
    ChangeExperiment,
    ChangeOutcome,
    Decision,
    DimensionValue,
    Direction,
    EvidenceStrength,
    FindingCategory,
    ManagementGraph,
    ManagementPolicy,
    Measurement,
    MetricComparison,
    OrganizationChangeProposal,
    OrganizationChangeReview,
    OrganizationalFinding,
    OrganizationalRecommendation,
    OrganizationalReview,
    OrganizationalSignal,
    OrgIntelligenceError,
    OrgIntelligenceStore,
    OrgIntelligenceStoreError,
    PriorityWeights,
    RecommendationState,
    RecommendationType,
    RepeatedWork,
    ResearchEvidence,
    ResourceEvidence,
    ReviewScope,
    ReviewWindow,
    Reversibility,
    RiskLevel,
    SignalType,
    SubjectKind,
    SuccessMetric,
    WORKFORCE_EQUIVALENT,
    attempt_pattern,
    automation_candidate,
    build_finding,
    ceo_reserved_actions,
    check_integrity,
    gap_recurrence,
    management_signals,
    prioritise,
    rank,
    record_decision,
    rendered_configuration,
    research_signals,
    resource_signals,
    significant,
    signals_from_coverage,
    signals_from_debt,
    signals_from_gaps,
    signals_from_necessity,
    signals_from_performance,
    unreserved_actions,
)
from company.runtime.config import load_company_config
from company.workforce import (
    Capability,
    CapabilityGraph,
    CapabilityRegistry,
    Criticality,
    FrequencyEvidence,
    GapTrigger,
    NeedFrequency,
    PerformanceObservation,
    TaskOutcome,
    TriggerKind,
    Urgency,
    assess_coverage,
    detect_debt,
    gap_from_coverage,
    review_role,
    summarise_observations,
)
from company.workforce.proposals import Recommendation as WorkforceRecommendation

# Governed, but not part of the control plane. Restated here rather than
# imported so this required suite keeps its own import surface; every copy is
# pinned against `company.dashboard.builder.EXTERNAL_CAPSULES` in
# `tests/test_company_external_engineering_runner.py`.
EXTERNAL_CAPSULES = {
    "company-external-engineering-runner",
    "company-youtube-fetch-client",
}
from knowledge.company_os.capsules import CapsuleIndex
from knowledge.company_os.capsules.budget import DEFAULT_BUDGET
from knowledge.company_os.capsules.index import SEED_ROOT
from knowledge.company_os.records import Evidence

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "company" / "org_intelligence"
TODAY = dt.date(2026, 9, 16)
WINDOW = ReviewWindow(start=dt.date(2026, 8, 18), end=TODAY, label="the last 30 days")


# -- fixtures and builders -------------------------------------------------


@pytest.fixture(scope="module")
def config():
    return load_company_config()


@pytest.fixture(scope="module")
def registry(config):
    return CapabilityRegistry.load(config.org_registry)


def an_evidence(kind: str = "observation", ref: str = "tests/test_company_org_intelligence.py"):
    return Evidence(kind=kind, ref=ref, note="")


def a_registry(employees: dict, capabilities=None, criticality=Criticality.IMPORTANT):
    caps = capabilities or ("alpha", "beta", "gamma")
    graph = CapabilityGraph(
        capabilities=tuple(
            Capability(
                capability_id=name,
                name=name.title(),
                description=f"The {name} capability.",
                domain="engineering",
                criticality=criticality,
            )
            for name in caps
        )
    )
    return CapabilityRegistry(graph, {"employees": employees})


def a_signal(**overrides) -> OrganizationalSignal:
    data = dict(
        signal_id="sig-001",
        type=SignalType.ROLE_OVERLAP,
        subject="studio_coo",
        subject_kind=SubjectKind.EMPLOYEE,
        window=WINDOW,
        detail="Two roles declare the same capability set.",
        evidence=(an_evidence(),),
        missing_measurements=("the cost of the duplication was not measured",),
    )
    data.update(overrides)
    return OrganizationalSignal(**data)


def a_finding(**overrides) -> OrganizationalFinding:
    data = dict(
        finding_id="find-001",
        category=FindingCategory.REDUNDANCY,
        subjects=("studio_coo",),
        statement="Two roles cover the same ground over this window.",
        window=WINDOW,
        signal_ids=("sig-001",),
        evidence=(an_evidence(),),
        what_would_change_it=("one of the two roles taking work the other cannot",),
    )
    data.update(overrides)
    return OrganizationalFinding(**data)


def a_recommendation(**overrides) -> OrganizationalRecommendation:
    data = dict(
        recommendation_id="rec-001",
        type=RecommendationType.INVESTIGATE,
        finding_ids=("find-001",),
        rationale="The overlap is real and its cost is unmeasured.",
        expected_benefit="A measured cost, or a reason to stop looking.",
        expected_cost="One reviewer, one afternoon.",
        risk=RiskLevel.LOW,
        reversibility=Reversibility.REVERSIBLE,
        follow_up_measurement="tasks routed to each role over the next 30 days",
        evidence=(an_evidence(),),
        kill_conditions=("the two roles diverge on their own before the window closes",),
    )
    data.update(overrides)
    return OrganizationalRecommendation(**data)


def a_metric(**overrides) -> SuccessMetric:
    data = dict(
        metric_id="m-cycle-time",
        description="Median approval hops for a class-A task.",
        baseline=Measurement(
            value=3.0, unit="hops", threshold=2.0, direction=Direction.HIGHER_IS_WORSE
        ),
        target_direction=Direction.HIGHER_IS_WORSE,
        target_value=2.0,
    )
    data.update(overrides)
    return SuccessMetric(**data)


def a_change_proposal(**overrides) -> OrganizationChangeProposal:
    data = dict(
        proposal_id="chg-001",
        recommendation_ids=("rec-001",),
        what_changes="Remove the second review for low-risk class-A tasks.",
        what_does_not_change=(
            "Class-B and class-C review, production write gates, and every CEO-reserved "
            "decision stay exactly as they are."
        ),
        expected_benefit="One fewer approval hop on the highest-volume task class.",
        expected_implementation_cost="One edit to the routing table and a note to two roles.",
        reversibility=Reversibility.REVERSIBLE,
        rollback="Restore the second review; the routing table is one file under version control.",
        observation_window=ReviewWindow(start=TODAY, end=TODAY + dt.timedelta(days=29)),
        success_metrics=(a_metric(),),
        kill_conditions=("any class-A defect reaching production during the window",),
        reconsider_if=("class-A volume falls below ten tasks in a month",),
        evidence=(an_evidence(),),
    )
    data.update(overrides)
    return OrganizationChangeProposal(**data)


def an_experiment(**overrides) -> ChangeExperiment:
    data = dict(
        experiment_id="exp-001",
        change_proposal_id="chg-001",
        hypothesis="Removing the second review cuts median hops without raising defects.",
        changed_variable="the second review step for low-risk class-A tasks",
        baseline_window=ReviewWindow(start=dt.date(2026, 8, 18), end=TODAY),
        observation_window=ReviewWindow(start=TODAY, end=TODAY + dt.timedelta(days=29)),
        rollback_condition="any class-A defect reaching production",
        locked_variables=("the task classifier", "the two roles doing the work"),
        baseline_metrics=(a_metric(),),
        baseline_evidence=(an_evidence("measurement", "company/state/usage/class-a.json"),),
        success_metrics=(a_metric(),),
    )
    data.update(overrides)
    return ChangeExperiment(**data)


def usage(task_id: str, outcome: Outcome, **overrides) -> ResourceUsageRecord:
    data = dict(
        task_id=task_id,
        reasoning_class=ReasoningClass.C,
        outcome=outcome,
        passes=1,
    )
    data.update(overrides)
    if outcome is Outcome.REJECTED and "rejection_reason" not in data:
        data["rejection_reason"] = "QC found a readability defect."
    return ResourceUsageRecord(**data)


# --------------------------------------------------------------------------
# The review: an explicit window, a recorded configuration
# --------------------------------------------------------------------------


def a_review(**overrides) -> OrganizationalReview:
    data = dict(
        review_id="orv-2026-09",
        objective="Find where the current organization costs more than it returns.",
        window=WINDOW,
        created=TODAY,
        reviewer="studio_coo",
        evidence=(an_evidence("document", "company/org_registry.yaml"),),
        configuration=rendered_configuration(ManagementPolicy()),
    )
    data.update(overrides)
    return OrganizationalReview(**data)


def test_a_review_states_its_window_and_records_what_it_measured_against():
    review = a_review()
    assert review.window.days == 30
    assert review.configuration_map["ManagementPolicy.max_span_of_control"] == "6"
    assert review.window.limitation in review.limitations


def test_a_review_window_that_ends_before_it_starts_is_impossible():
    with pytest.raises(OrgIntelligenceError, match="impossible review window"):
        ReviewWindow(start=TODAY, end=TODAY - dt.timedelta(days=1))


def test_a_review_cannot_predate_its_own_window():
    with pytest.raises(OrgIntelligenceError, match="before its own window opens"):
        a_review(created=dt.date(2026, 1, 1))


def test_a_review_with_no_evidence_is_refused():
    with pytest.raises(OrgIntelligenceError, match="at least one piece of evidence"):
        a_review(evidence=())


def test_exclusions_and_missing_configuration_become_visible_limitations():
    review = a_review(
        scope=ReviewScope(departments=("engineering",), exclusions=("the data department",)),
        configuration=(),
    )
    assert not review.scope.is_whole_company
    assert any("excluded from this review" in item for item in review.limitations)
    assert any("no thresholds were recorded" in item for item in review.limitations)


def test_two_windows_of_very_different_length_are_not_comparable():
    short = ReviewWindow(start=TODAY, end=TODAY + dt.timedelta(days=2))
    assert not WINDOW.comparable_to(short)
    assert "not equivalent measurements" in WINDOW.mismatch_caveat(short)
    assert WINDOW.mismatch_caveat(WINDOW) == ""


# --------------------------------------------------------------------------
# Signals: a missing measurement stays missing
# --------------------------------------------------------------------------


def test_a_signal_with_no_measurement_stays_unmeasured_rather_than_zero():
    signal = a_signal()
    assert signal.measured is False
    assert signal.measurement.value is None
    assert signal.to_dict()["measurement"]["value"] is None
    assert signal.breaches_threshold is None
    assert signal.missing_measurements


def test_a_signal_with_neither_a_value_nor_a_named_absence_is_refused():
    with pytest.raises(OrgIntelligenceError, match="nothing was named as missing"):
        a_signal(missing_measurements=())


def test_a_signal_without_evidence_is_refused():
    with pytest.raises(OrgIntelligenceError, match="at least one piece of evidence"):
        a_signal(evidence=())


def test_a_measured_value_needs_a_unit():
    with pytest.raises(OrgIntelligenceError, match="needs a unit"):
        Measurement(value=0.7)


def test_a_threshold_without_a_direction_cannot_be_read():
    with pytest.raises(OrgIntelligenceError, match="which side is worse"):
        Measurement(value=1.0, unit="rate", threshold=0.5)


def test_a_small_sample_keeps_its_caveat_on_the_signal():
    signal = a_signal(
        measurement=Measurement(
            value=0.8,
            unit="rate",
            threshold=0.5,
            direction=Direction.HIGHER_IS_WORSE,
            sample_size=2,
            minimum_sample=3,
        ),
        missing_measurements=(),
    )
    assert signal.measurement.small_sample is True
    assert any("sample of 2" in caveat for caveat in signal.caveats)
    assert signal.breaches_threshold is True


def test_a_sample_nobody_counted_is_not_reported_as_small():
    measurement = Measurement(value=0.8, unit="rate", minimum_sample=3)
    assert measurement.small_sample is None
    assert measurement.caveat == ""


# --------------------------------------------------------------------------
# Findings: evidence, counterevidence, limitations
# --------------------------------------------------------------------------


def test_a_finding_without_evidence_is_refused():
    with pytest.raises(OrgIntelligenceError, match="no finding with zero evidence"):
        a_finding(evidence=())


def test_a_finding_without_a_supporting_signal_is_refused():
    with pytest.raises(OrgIntelligenceError, match="combines one or more signals"):
        a_finding(signal_ids=())


def test_a_finding_must_say_what_would_change_it():
    with pytest.raises(OrgIntelligenceError, match="what_would_change_it"):
        a_finding(what_would_change_it=())


def test_a_finding_retains_counterevidence_and_gains_a_limitation_for_it():
    finding = a_finding(
        counterevidence=(an_evidence("measurement", "company/state/usage/overlap.json"),)
    )
    assert finding.has_counterevidence
    assert len(finding.counterevidence) == 1
    assert any("counterevidence was recorded" in item for item in finding.limitations)
    assert finding.window.limitation in finding.limitations


def test_build_finding_carries_signal_caveats_and_absences_into_limitations():
    small = a_signal(
        signal_id="sig-small",
        measurement=Measurement(
            value=0.9,
            unit="rate",
            threshold=0.5,
            direction=Direction.HIGHER_IS_WORSE,
            sample_size=2,
            minimum_sample=3,
        ),
        missing_measurements=("nobody recorded how long each attempt took",),
    )
    finding = build_finding(
        "find-small",
        FindingCategory.RESOURCE_INEFFICIENCY,
        statement="Most attempts in this scope were rejected.",
        signals=(small,),
        what_would_change_it=("a larger sample at the same rate",),
    )
    assert any("sample of 2" in item for item in finding.limitations)
    assert any("nobody recorded how long" in item for item in finding.limitations)
    assert finding.strength is EvidenceStrength.MODERATE


def test_a_finding_built_from_two_breaching_signals_is_stronger_than_one():
    def breaching(signal_id):
        return a_signal(
            signal_id=signal_id,
            measurement=Measurement(
                value=0.9,
                unit="rate",
                threshold=0.5,
                direction=Direction.HIGHER_IS_WORSE,
                sample_size=30,
                minimum_sample=3,
            ),
            missing_measurements=(),
        )

    strong = build_finding(
        "find-strong",
        FindingCategory.WORKFLOW_INEFFICIENCY,
        statement="Two independent measures cross their thresholds.",
        signals=(breaching("sig-a"), breaching("sig-b")),
        what_would_change_it=("either measure falling back under its threshold",),
    )
    assert strong.strength is EvidenceStrength.STRONG
    weak = build_finding(
        "find-weak",
        FindingCategory.WORKFLOW_INEFFICIENCY,
        statement="One measure crosses its threshold.",
        signals=(breaching("sig-a"),),
        what_would_change_it=("the measure falling back under its threshold",),
    )
    assert weak.strength is EvidenceStrength.MODERATE


def test_counterevidence_caps_the_strength_of_an_otherwise_strong_finding():
    def breaching(signal_id):
        return a_signal(
            signal_id=signal_id,
            measurement=Measurement(
                value=0.9,
                unit="rate",
                threshold=0.5,
                direction=Direction.HIGHER_IS_WORSE,
                sample_size=30,
                minimum_sample=3,
            ),
            missing_measurements=(),
        )

    finding = build_finding(
        "find-contested",
        FindingCategory.WORKFLOW_INEFFICIENCY,
        statement="Two measures cross, and one observation points the other way.",
        signals=(breaching("sig-a"), breaching("sig-b")),
        counterevidence=(an_evidence("measurement", "company/state/usage/contra.json"),),
        what_would_change_it=("the counterevidence being explained",),
    )
    assert finding.strength is EvidenceStrength.MODERATE


def test_a_finding_widens_its_window_to_cover_every_signal_it_used():
    early = a_signal(
        signal_id="sig-early",
        window=ReviewWindow(start=dt.date(2026, 7, 1), end=dt.date(2026, 7, 31)),
    )
    late = a_signal(signal_id="sig-late", window=WINDOW)
    finding = build_finding(
        "find-wide",
        FindingCategory.STRUCTURAL_FACT,
        statement="Observed across two periods.",
        signals=(early, late),
        what_would_change_it=("a period with neither observation",),
    )
    assert finding.window.start == dt.date(2026, 7, 1)
    assert finding.window.end == TODAY


# --------------------------------------------------------------------------
# Section 4: there is no company score
# --------------------------------------------------------------------------


def test_no_global_company_score_field_exists():
    """Section 4, enforced rather than described.

    Scans every dataclass in the package for a field whose name reads like an
    aggregate quality verdict. A company is multi-objective, and one number for
    it erases exactly the information a reorganization decision needs.
    """
    import company.org_intelligence as package

    banned = ("score", "rating", "grade", "reputation", "overall", "health", "verdict")
    offenders = []
    for name in dir(package):
        obj = getattr(package, name)
        if not dataclasses.is_dataclass(obj) or not isinstance(obj, type):
            continue
        for field in dataclasses.fields(obj):
            if any(word in field.name.lower() for word in banned):
                offenders.append(f"{name}.{field.name}")
    assert offenders == []


def test_no_module_defines_a_company_level_aggregate():
    forbidden = (
        "company_health_score",
        "organization_score",
        "employee_score",
        "manager_score",
        "department_score",
    )
    for path in sorted(PACKAGE_ROOT.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        for name in forbidden:
            assert name not in source, f"{path.name} mentions {name}"


# --------------------------------------------------------------------------
# Workforce evidence: consumed, never recomputed
# --------------------------------------------------------------------------


def test_a_known_single_point_of_failure_becomes_a_finding():
    registry_obj = a_registry(
        {
            "only_one": {"state": "active", "capabilities": ["alpha"], "manager": "ceo"},
            "someone_else": {"state": "active", "capabilities": ["beta"], "manager": "ceo"},
        }
    )
    report = assess_coverage(("alpha",), registry_obj)
    assert report.single_points_of_failure == ("alpha",)

    signals = signals_from_coverage(
        report, window=WINDOW, evidence=(an_evidence("document", "company/org_registry.yaml"),)
    )
    spof = [s for s in signals if s.type is SignalType.CRITICAL_SINGLE_POINT_FAILURE]
    assert len(spof) == 1
    assert spof[0].subject == "alpha"
    assert spof[0].breaches_threshold is True

    finding = build_finding(
        "find-spof",
        FindingCategory.CAPABILITY_RISK,
        statement="alpha has one organizational provider; losing them removes it.",
        signals=tuple(spof),
        what_would_change_it=("a second employee declaring alpha",),
    )
    assert finding.category is FindingCategory.CAPABILITY_RISK
    assert finding.subjects == ("alpha",)


def test_a_dormant_capability_does_not_become_a_hire_recommendation():
    """Constitution rule 18, carried across the layer boundary."""
    registry_obj = a_registry(
        {
            "sleeper": {"state": "dormant", "capabilities": ["alpha"], "manager": "ceo"},
            "awake": {"state": "active", "capabilities": ["beta"], "manager": "ceo"},
        }
    )
    report = assess_coverage(("alpha",), registry_obj)
    signals = signals_from_coverage(
        report, window=WINDOW, evidence=(an_evidence("document", "company/org_registry.yaml"),)
    )
    kinds = {signal.type for signal in signals}
    assert SignalType.DORMANT_CAPABILITY in kinds
    assert SignalType.CAPABILITY_GAP_FREQUENCY not in kinds

    dormant = [s for s in signals if s.type is SignalType.DORMANT_CAPABILITY][0]
    finding = build_finding(
        "find-dormant",
        FindingCategory.WORKFORCE_GAP,
        statement="alpha is held by a dormant employee and nobody is running it.",
        signals=(dormant,),
        what_would_change_it=("the dormant employee being activated",),
    )
    recommendation = a_recommendation(
        recommendation_id="rec-activate",
        type=RecommendationType.ACTIVATE_DORMANT_EMPLOYEE,
        finding_ids=(finding.finding_id,),
        subjects=("sleeper",),
        workforce_record_refs=("company/workforce/coverage.py#alpha",),
        rationale="The company already holds alpha; it is not running it.",
    )
    assert recommendation.type is not RecommendationType.CREATE_CANDIDATE_ROLE
    assert recommendation.workforce_equivalent is (
        WorkforceRecommendation.ACTIVATE_DORMANT_EMPLOYEE
    )


def test_repeated_gap_evidence_can_generate_a_workforce_recommendation():
    registry_obj = a_registry(
        {"awake": {"state": "active", "capabilities": ["beta"], "manager": "ceo"}}
    )
    report = assess_coverage(("alpha",), registry_obj)
    gap = gap_from_coverage(
        "gap-alpha-001",
        report,
        trigger=GapTrigger(
            kind=TriggerKind.TASK,
            ref="task/alpha-001",
            summary="Nobody could take the alpha work.",
        ),
        frequency=FrequencyEvidence(
            frequency=NeedFrequency.RECURRING,
            observed_occurrences=4,
            window_days=60,
            evidence=(an_evidence("escalation", "company/state/escalations/001.json"),),
        ),
        urgency=Urgency.HIGH,
        business_impact="Four pieces of work waited on a capability nobody has.",
        observed_on=TODAY,
        evidence=(an_evidence("escalation", "company/state/escalations/001.json"),),
    )
    assert gap_recurrence((gap,)) == (("alpha", 1),)

    signals = signals_from_gaps((gap,), window=WINDOW)
    assert len(signals) == 1
    assert signals[0].measurement.value == 4.0
    assert signals[0].breaches_threshold is True

    finding = build_finding(
        "find-alpha-gap",
        FindingCategory.WORKFORCE_GAP,
        statement="alpha has been missing four times in sixty days.",
        signals=signals,
        what_would_change_it=("sixty days with no alpha request",),
    )
    recommendation = a_recommendation(
        recommendation_id="rec-alpha-role",
        type=RecommendationType.CREATE_CANDIDATE_ROLE,
        finding_ids=(finding.finding_id,),
        subjects=("alpha",),
        workforce_record_refs=(f"company/workforce/gaps.py#{gap.gap_id}",),
        rationale="A recurring gap with nobody adjacent.",
    )
    assert recommendation.workforce_equivalent is WorkforceRecommendation.CREATE_CANDIDATE_ROLE


def test_a_workforce_shaped_recommendation_must_point_at_the_record_it_consumes():
    with pytest.raises(OrgIntelligenceError, match="already means something in company/workforce"):
        a_recommendation(
            recommendation_id="rec-no-ref",
            type=RecommendationType.ACTIVATE_DORMANT_EMPLOYEE,
            subjects=("sleeper",),
        )


def test_every_shared_recommendation_name_maps_to_the_workforce_meaning():
    """Section 5: reuse the existing meaning rather than inventing a rival one."""
    workforce_names = {item.value for item in WorkforceRecommendation}
    for org_type in RecommendationType:
        if org_type.value not in workforce_names:
            continue
        assert org_type in WORKFORCE_EQUIVALENT, org_type
        assert WORKFORCE_EQUIVALENT[org_type].value == org_type.value


def test_performance_signals_stay_scoped_to_employee_and_capability():
    observations = tuple(
        PerformanceObservation(
            employee_id="chief_architect",
            capability_id="software_architecture",
            task_ref=f"task/{index}",
            outcome=TaskOutcome.REJECTED,
            on=TODAY,
            note="Rejected in review.",
        )
        for index in range(4)
    )
    performances = summarise_observations(observations)
    signals = signals_from_performance(performances, window=WINDOW)
    rejection = [s for s in signals if s.type is SignalType.HIGH_REJECTION_RATE]
    assert len(rejection) == 1
    assert rejection[0].subject == "chief_architect/software_architecture"
    assert rejection[0].measurement.value == 1.0
    assert rejection[0].measurement.sample_size == 4


def test_a_small_performance_sample_is_reported_with_its_caveat():
    observations = (
        PerformanceObservation(
            employee_id="chief_architect",
            capability_id="software_architecture",
            task_ref="task/1",
            outcome=TaskOutcome.REJECTED,
            on=TODAY,
            note="Rejected in review.",
        ),
    )
    signals = signals_from_performance(summarise_observations(observations), window=WINDOW)
    assert len(signals) == 1
    assert any("sample of 1" in caveat for caveat in signals[0].caveats)


def test_necessity_reviews_become_overlap_and_unused_signals(registry):
    review = review_role(
        "hr_org_intelligence_lead",
        registry,
        (),
        window_start=WINDOW.start,
        window_end=WINDOW.end,
    )
    signals = signals_from_necessity((review,), window=WINDOW)
    kinds = {signal.type for signal in signals}
    assert SignalType.ROLE_UNUSED in kinds
    unused = [s for s in signals if s.type is SignalType.ROLE_UNUSED][0]
    assert unused.measurement.value == 0.0
    assert any("a question, not a verdict" in caveat for caveat in unused.caveats)


def test_the_existing_debt_ledger_is_read_rather_than_rebuilt(registry):
    debts = detect_debt(registry, observed_on=TODAY)
    assert debts, "the shipped registry should yield at least one debt record"
    signals = signals_from_debt(debts, window=WINDOW)
    assert len(signals) == len(debts)
    assert all(signal.source_refs == ("company/workforce/debt.py",) for signal in signals)
    assert all(signal.missing_measurements for signal in signals)


def test_a_protective_necessity_signal_is_carried_as_a_caveat_on_the_overlap():
    registry_obj = a_registry(
        {
            "twin_one": {"state": "active", "capabilities": ["alpha", "beta"], "manager": "ceo"},
            "twin_two": {"state": "active", "capabilities": ["alpha", "gamma"], "manager": "ceo"},
        }
    )
    review = review_role(
        "twin_one", registry_obj, (), window_start=WINDOW.start, window_end=WINDOW.end
    )
    assert review.protective_signals
    signals = signals_from_necessity((review,), window=WINDOW)
    overlap = [s for s in signals if s.type is SignalType.ROLE_OVERLAP]
    assert overlap
    assert any("protective signal" in caveat for caveat in overlap[0].caveats)


# --------------------------------------------------------------------------
# Resource efficiency: no token counts required
# --------------------------------------------------------------------------


def test_resource_records_are_usable_with_no_token_counts():
    records = (
        usage("task/a", Outcome.ACCEPTED, passes=3),
        usage("task/b", Outcome.REJECTED, passes=4),
        usage("task/c", Outcome.REJECTED, passes=5),
    )
    evidence = ResourceEvidence.from_records("class_a_workflow", records)
    assert evidence.units_per_accepted is None
    assert evidence.passes_per_accepted == 12.0
    assert any("units per accepted" in item for item in evidence.missing_measurements)
    assert any("tool calls" in item for item in evidence.missing_measurements)

    signals = resource_signals(evidence, window=WINDOW)
    kinds = {signal.type for signal in signals}
    assert SignalType.HIGH_RESOURCE_PER_ACCEPTANCE in kinds
    assert SignalType.HIGH_REJECTION_RATE in kinds
    assert all(signal.missing_measurements for signal in signals)


def test_accepted_and_rejected_attempt_patterns_are_measurable():
    records = (
        usage("task/a", Outcome.ACCEPTED),
        usage("task/b", Outcome.REJECTED, retries=2),
        usage("task/c", Outcome.ABANDONED),
    )
    pattern = attempt_pattern(records)
    assert pattern == {
        "records": 3,
        "accepted": 1,
        "rejected": 1,
        "abandoned": 1,
        "retries": 2,
        "passes": 3,
    }
    evidence = ResourceEvidence.from_records("mixed", records)
    assert evidence.rejection_rate == pytest.approx(1 / 3)
    assert evidence.acceptance_rate == pytest.approx(1 / 3)


def test_unused_context_references_drive_the_expansion_pressure_signal():
    records = tuple(
        usage(
            f"task/{index}",
            Outcome.ACCEPTED,
            context_sources=("a", "b", "c", "d"),
            context_refs_used=("a",),
        )
        for index in range(4)
    )
    evidence = ResourceEvidence.from_records("context_heavy", records)
    assert evidence.context_refs_supplied == 16
    assert evidence.unused_context_share == pytest.approx(0.75)
    signals = resource_signals(evidence, window=WINDOW)
    assert any(s.type is SignalType.CONTEXT_EXPANSION_PRESSURE for s in signals)


def test_a_context_expansion_count_nobody_supplied_stays_missing():
    evidence = ResourceEvidence.from_records(
        "unknown_expansion", (usage("task/a", Outcome.ACCEPTED),)
    )
    assert evidence.context_expansions is None
    assert any("context expansions" in item for item in evidence.missing_measurements)


def test_a_provider_that_does_expose_units_is_carried_through():
    records = tuple(
        usage(
            f"task/{index}",
            Outcome.ACCEPTED,
            input_units=100,
            output_units=50,
            usage_unit=UsageUnit.TOKEN,
            tool_calls=2,
            duration_s=1.5,
        )
        for index in range(3)
    )
    evidence = ResourceEvidence.from_records("measured", records)
    assert evidence.units_per_accepted == pytest.approx(150.0)
    assert evidence.tool_calls == 6
    assert not any("units per accepted" in item for item in evidence.missing_measurements)


# --------------------------------------------------------------------------
# Research efficiency: duplication, and the caveat that must survive
# --------------------------------------------------------------------------


class _Progress:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def a_batch_report_shape(**overrides):
    """A stand-in with the attribute shape `from_batch_report` documents."""
    data = dict(
        batch_id="rb-marble-sweep",
        progress=_Progress(
            observations=11, unique_candidates=5, unscreened=3, promoted_sources=1
        ),
        duplication=_Progress(duplicate_rate=6 / 11),
        creators=_Progress(
            top_creator="chan-alpha", top_creator_share=0.75, unknown_creator_candidates=1
        ),
        screening=_Progress(assessed=2),
        missing_measurements=("nobody recorded manual minutes for round 2",),
    )
    data.update(overrides)
    return _Progress(**data)


def test_a_research_duplication_signal_comes_off_a_supplied_batch_report():
    evidence = ResearchEvidence.from_batch_report(a_batch_report_shape())
    assert evidence.duplicate_rate == pytest.approx(6 / 11)
    assert evidence.promotion_yield == pytest.approx(0.2)

    signals = research_signals(evidence, window=WINDOW)
    duplication = [s for s in signals if s.type is SignalType.RESEARCH_QUERY_DUPLICATION]
    assert len(duplication) == 1
    assert duplication[0].subject == "rb-marble-sweep"
    assert duplication[0].subject_kind is SubjectKind.RESEARCH_BATCH


def test_a_small_research_sample_keeps_both_caveats():
    signals = research_signals(
        ResearchEvidence.from_batch_report(a_batch_report_shape()), window=WINDOW
    )
    assert signals
    for signal in signals:
        assert SINGLE_BATCH_LIMITATION in signal.caveats
        assert any("sample of 5" in caveat for caveat in signal.caveats)


def test_a_research_finding_never_takes_a_content_format_as_its_subject():
    signals = research_signals(
        ResearchEvidence.from_batch_report(a_batch_report_shape()), window=WINDOW
    )
    finding = build_finding(
        "find-research",
        FindingCategory.RESOURCE_INEFFICIENCY,
        statement="This search re-read more pages than it found.",
        signals=signals,
        what_would_change_it=("a second batch with a different query family",),
    )
    assert finding.subjects == ("rb-marble-sweep",)
    assert SINGLE_BATCH_LIMITATION in finding.limitations


def test_a_report_missing_an_attribute_fails_loudly():
    with pytest.raises(OrgIntelligenceError, match="missing attribute"):
        ResearchEvidence.from_batch_report(_Progress(batch_id="rb-x"))


def test_the_real_batch_report_satisfies_the_documented_shape():
    """The adapter is duck-typed; this checks it against the real thing."""
    from intelligence.research import (
        BatchBudget,
        BatchStatus,
        CandidateOutcome,
        CandidateState,
        DiscoveryRound,
        StopCondition,
        StopReason,
        advance_batch,
        build_batch_report,
        open_batch,
        record_round,
    )

    batch = open_batch(
        id="rb-org-intel",
        objective="A batch built only to check the report shape.",
        created=TODAY,
        owner="research_opportunity_lead",
        query_ids=("dq-marble-race",),
        budget=BatchBudget(
            max_queries=2,
            max_candidate_observations=40,
            max_unique_candidates=20,
            max_promoted_candidates=4,
            max_reference_cases=3,
            max_human_review_minutes=180,
        ),
        stop_conditions=(StopCondition(reason=StopReason.MAX_UNIQUE_CANDIDATES, threshold=20),),
    )
    batch = advance_batch(
        batch,
        BatchStatus.COLLECTING,
        on=TODAY,
        by="research_opportunity_lead",
        reason="Budget agreed; collection may start.",
    )
    for _ in range(2):
        batch = record_round(
            batch,
            DiscoveryRound(
                query_id="dq-marble-race", ran_on=TODAY, observed=("c1", "c2", "c3")
            ),
            by="research_opportunity_lead",
        )
    outcomes = (
        CandidateOutcome(
            candidate_id="c1",
            state=CandidateState.DISCOVERED,
            reached=(CandidateState.DISCOVERED,),
            creator_id="chan-alpha",
        ),
    )
    report = build_batch_report(batch, outcomes, (), (), as_of=TODAY)

    evidence = ResearchEvidence.from_batch_report(report)
    assert evidence.batch_id == "rb-org-intel"
    assert evidence.observations == 6
    assert evidence.unique_candidates == 3
    assert evidence.duplicate_rate == pytest.approx(0.5)


# --------------------------------------------------------------------------
# Management graph
# --------------------------------------------------------------------------


def test_management_depth_is_measured_deterministically(config):
    graph = ManagementGraph.from_org_registry(config.org_registry)
    assert graph.depth_of("studio_coo") == 1
    assert graph.depth_of("chief_architect") == 2
    # The engineers sit one rung lower than they used to: the CEO-authorized
    # Engineering Manager was inserted between them and the Chief Architect so
    # that managerial approval stops being the same employee as independent
    # review. Four is the configured ceiling, not over it.
    assert graph.depth_of("engineering_delivery_manager") == 3
    assert graph.depth_of("simulation_physics_engineer") == 4
    assert graph.excessive_depth(ManagementPolicy(max_depth=4)) == ()
    assert graph.cycles() == ()
    assert graph.orphans() == ()
    assert graph.invalid_references() == ()
    # The CFO reports to the CEO rather than the COO, which is where the master
    # plan puts it and what keeps this span at its threshold rather than over it.
    assert dict(graph.span_of_control())["studio_coo"] == 6


def test_a_manager_cycle_is_detected_and_depth_becomes_unmeasurable():
    registry = {
        "employees": {
            "a_role": {"manager": "b_role", "department": "engineering", "capabilities": []},
            "b_role": {"manager": "a_role", "department": "engineering", "capabilities": []},
            "c_role": {"manager": "a_role", "department": "engineering", "capabilities": []},
        }
    }
    graph = ManagementGraph.from_org_registry(registry)
    assert graph.cycles() == (("a_role", "b_role"),)
    assert graph.depth_of("a_role") is None
    assert graph.depth_of("c_role") is None

    signals = management_signals(graph, window=WINDOW)
    cycle = [s for s in signals if s.type is SignalType.MANAGEMENT_CYCLE]
    assert len(cycle) == 1
    assert "a_role -> b_role -> a_role" in cycle[0].detail
    assert check_integrity(org_registry=registry)[0].startswith("manager cycle")


def test_an_invalid_management_reference_is_reported_not_guessed():
    registry = {
        "employees": {
            "a_role": {"manager": "nobody_here", "department": "engineering", "capabilities": []}
        }
    }
    graph = ManagementGraph.from_org_registry(registry)
    assert graph.invalid_references() == (("a_role", "nobody_here"),)
    signals = management_signals(graph, window=WINDOW)
    assert signals[0].type is SignalType.INVALID_MANAGEMENT_REFERENCE
    assert signals[0].measurement.value is None
    assert signals[0].missing_measurements


def test_span_of_control_is_an_explicit_threshold_not_a_hidden_judgement(config):
    graph = ManagementGraph.from_org_registry(config.org_registry)
    assert graph.oversized_spans(ManagementPolicy(max_span_of_control=6)) == ()
    tight = graph.oversized_spans(ManagementPolicy(max_span_of_control=3))
    assert ("studio_coo", 6) in tight
    signals = management_signals(
        graph, window=WINDOW, policy=ManagementPolicy(max_span_of_control=3)
    )
    span = [s for s in signals if s.type is SignalType.MANAGEMENT_SPAN][0]
    assert span.measurement.threshold == 3.0
    assert any("configured threshold, not a measured cost" in c for c in span.caveats)


def test_a_pass_through_layer_is_reported_as_a_shape_not_a_verdict(config):
    graph = ManagementGraph.from_org_registry(config.org_registry)
    assert ("creative_format_director", "visual_cinematography_director") in (
        graph.pass_through_managers()
    )
    signals = management_signals(graph, window=WINDOW)
    layer = [s for s in signals if s.type is SignalType.DUPLICATED_MANAGEMENT_LAYER][0]
    assert "bad" not in layer.detail
    assert any("a shape, not a cost" in caveat for caveat in layer.caveats)


def test_a_manager_in_a_management_department_with_no_reports_is_visible():
    registry = {
        "employees": {
            "lonely_exec": {"manager": "ceo", "department": "executive", "capabilities": []}
        }
    }
    graph = ManagementGraph.from_org_registry(registry)
    assert graph.managers_without_reports() == ("lonely_exec",)
    assert graph.managers_without_reports(
        ManagementPolicy(management_departments=("people",))
    ) == ()


def test_an_orphan_role_is_detected():
    registry = {
        "employees": {"a_role": {"manager": "", "department": "engineering", "capabilities": []}}
    }
    graph = ManagementGraph.from_org_registry(registry)
    assert graph.orphans() == ("a_role",)
    assert management_signals(graph, window=WINDOW)[0].type is SignalType.ORPHAN_ROLE


# --------------------------------------------------------------------------
# Recommendations: advisory, always
# --------------------------------------------------------------------------


def test_a_recommendation_needs_a_finding_underneath_it():
    with pytest.raises(OrgIntelligenceError, match="name the finding it answers"):
        a_recommendation(finding_ids=())


def test_a_recommendation_needs_kill_conditions_unless_it_recommends_nothing():
    with pytest.raises(OrgIntelligenceError, match="kill_conditions"):
        a_recommendation(kill_conditions=())
    nothing = a_recommendation(
        recommendation_id="rec-nothing",
        type=RecommendationType.NO_ACTION,
        kill_conditions=(),
    )
    assert nothing.kill_conditions == ()
    assert nothing.is_action is False


def test_no_recommendation_applies_itself():
    """There is no apply, and nothing in the package mutates the company."""
    import company.org_intelligence as package

    for name in dir(package):
        obj = getattr(package, name)
        if isinstance(obj, type):
            forbidden = {"apply", "execute", "implement", "commit", "enact", "perform"}
            assert not (forbidden & set(dir(obj))), f"{name} exposes an apply-like method"
    assert not hasattr(package, "apply")
    assert not hasattr(package, "implement")


def test_a_recommendation_cannot_arrive_approved_with_nobody_s_name_on_it():
    with pytest.raises(AdvisoryViolation, match="does not approve its own recommendations"):
        a_recommendation(state=RecommendationState.APPROVED)


@pytest.mark.parametrize("marker", sorted(AUTOMATIC_MARKERS))
def test_a_machine_cannot_sign_a_decision(marker):
    with pytest.raises(AdvisoryViolation, match="is not a person"):
        Decision(
            state=RecommendationState.APPROVED,
            by=marker,
            on=TODAY,
            reason="It looked fine.",
        )


def test_recording_a_human_decision_changes_state_and_nothing_else():
    proposed = a_recommendation()
    decided = record_decision(
        proposed,
        state=RecommendationState.APPROVED,
        by="the CEO",
        on=TODAY,
        reason="Worth one afternoon of measurement.",
    )
    assert decided.state is RecommendationState.APPROVED
    assert decided.decision.by == "the CEO"
    assert dataclasses.replace(decided, state=proposed.state, decision=None) == proposed


def test_a_decided_recommendation_is_not_reversed_in_place():
    decided = record_decision(
        a_recommendation(),
        state=RecommendationState.APPROVED,
        by="the CEO",
        on=TODAY,
        reason="Approved.",
    )
    with pytest.raises(OrgIntelligenceError, match="record a new recommendation"):
        record_decision(
            decided,
            state=RecommendationState.REJECTED,
            by="the CEO",
            on=TODAY,
            reason="Changed my mind.",
        )


def test_a_proposed_recommendation_carries_no_decision():
    with pytest.raises(OrgIntelligenceError, match="proposed recommendation carries no decision"):
        a_recommendation(
            decision=Decision(
                state=RecommendationState.APPROVED, by="the CEO", on=TODAY, reason="ok"
            )
        )


# --------------------------------------------------------------------------
# CEO-reserved actions and the no-subagent policy
# --------------------------------------------------------------------------


def test_a_ceo_reserved_action_requires_the_ceo_approval_flag(config):
    reserved = ceo_reserved_actions(
        RecommendationType.ARCHIVE_ROLE,
        subject_departments=("executive",),
        permissions=config.permissions,
    )
    assert reserved == ("hire_or_remove_executive_role",)
    with pytest.raises(AdvisoryViolation, match="does not require CEO approval"):
        a_recommendation(
            recommendation_id="rec-exec",
            type=RecommendationType.ARCHIVE_ROLE,
            subjects=("studio_coo",),
            workforce_record_refs=("company/workforce/necessity.py#studio_coo",),
            reserved_actions=reserved,
            requires_ceo_approval=False,
        )
    allowed = a_recommendation(
        recommendation_id="rec-exec",
        type=RecommendationType.ARCHIVE_ROLE,
        subjects=("studio_coo",),
        workforce_record_refs=("company/workforce/necessity.py#studio_coo",),
        reserved_actions=reserved,
        requires_ceo_approval=True,
    )
    assert allowed.requires_ceo_approval


def test_reservation_is_read_from_permissions_and_fails_closed():
    assert ceo_reserved_actions(
        RecommendationType.ARCHIVE_ROLE, subject_departments=("executive",), permissions=None
    ) == ("hire_or_remove_executive_role",)
    assert (
        ceo_reserved_actions(
            RecommendationType.ARCHIVE_ROLE,
            subject_departments=("executive",),
            permissions={"ceo_reserved": []},
        )
        == ()
    )
    assert (
        ceo_reserved_actions(
            RecommendationType.ARCHIVE_ROLE,
            subject_departments=("engineering",),
            permissions=None,
        )
        == ()
    )


def test_the_shipped_permissions_still_reserve_every_action_this_package_maps(config):
    """The rename detector, run against the real file."""
    assert unreserved_actions(config.permissions) == ()
    assert check_integrity(permissions=config.permissions) == ()


def test_a_no_subagent_change_cannot_be_an_ordinary_optimisation():
    with pytest.raises(AdvisoryViolation, match="constitutional, not efficiency dials"):
        a_recommendation(
            recommendation_id="rec-subagents",
            type=RecommendationType.SIMPLIFY_WORKFLOW,
            subjects=("class_a_review",),
            touches_policies=("no_subagents",),
            requires_ceo_approval=True,
        )


def test_a_no_subagent_change_without_the_ceo_flag_is_refused():
    with pytest.raises(AdvisoryViolation, match="requires CEO approval"):
        a_recommendation(
            recommendation_id="rec-subagents",
            type=RecommendationType.INVESTIGATE,
            touches_policies=("no_subagents",),
            requires_ceo_approval=False,
        )


def test_a_no_subagent_change_proposal_is_representable_when_ceo_reserved():
    proposal = a_change_proposal(
        proposal_id="chg-subagents",
        touches_policies=("no_subagents",),
        requires_ceo_approval=True,
        required_approval=ApprovalAuthority.CEO,
        reserved_actions=("change_no_subagents_policy",),
    )
    assert proposal.requires_ceo_approval
    assert proposal.required_approval is ApprovalAuthority.CEO


def test_an_unknown_policy_id_cannot_slip_past_a_gate():
    with pytest.raises(OrgIntelligenceError, match="is not a known policy id"):
        a_recommendation(touches_policies=("no_subagent",), requires_ceo_approval=True)


def test_the_no_subagent_policy_is_where_it_was(config):
    """Rule 2 is read, never edited."""
    assert config.org_registry["global_constraints"]["no_subagents"] is True
    assert config.permissions["bootstrap_defaults"]["no_subagents"] is True
    assert "change_no_subagents_policy" in config.permissions["ceo_reserved"]
    assert "no_subagents" in CONSTITUTIONAL_POLICIES


# --------------------------------------------------------------------------
# Change proposals, experiments and post-change review
# --------------------------------------------------------------------------


def test_a_significant_recommendation_produces_a_change_proposal():
    ordinary = a_recommendation(recommendation_id="rec-small")
    weighty = a_recommendation(
        recommendation_id="rec-big",
        reversibility=Reversibility.REVERSIBLE_WITH_COST,
    )
    assert significant((ordinary, weighty)) == (weighty,)
    proposal = a_change_proposal(recommendation_ids=("rec-big",))
    assert proposal.recommendation_ids == ("rec-big",)
    assert proposal.state is RecommendationState.PROPOSED


def test_a_change_proposal_must_say_what_does_not_change_and_how_to_undo_it():
    for field in ("what_does_not_change", "rollback"):
        with pytest.raises(OrgIntelligenceError, match=field):
            a_change_proposal(**{field: ""})
    for field, match in (
        ("success_metrics", "how anyone would know this worked"),
        ("kill_conditions", "kill_conditions"),
        ("reconsider_if", "reconsider_if"),
    ):
        with pytest.raises(OrgIntelligenceError, match=match):
            a_change_proposal(**{field: ()})


def test_a_change_proposal_touching_a_canonical_contract_is_ceo_reserved():
    with pytest.raises(AdvisoryViolation, match="canonical contracts"):
        a_change_proposal(
            proposal_id="chg-registry",
            implementation_paths=("company/org_registry.yaml",),
        )
    allowed = a_change_proposal(
        proposal_id="chg-registry",
        implementation_paths=("company/org_registry.yaml",),
        requires_ceo_approval=True,
        required_approval=ApprovalAuthority.CEO,
    )
    assert allowed.touches_canonical_contract


def test_a_change_proposal_cannot_name_a_machine_as_its_implementer():
    with pytest.raises(AdvisoryViolation, match="is not a person"):
        a_change_proposal(implemented_by="automatic")


def test_a_change_experiment_carries_a_baseline_locked_variables_and_a_kill_condition():
    experiment = an_experiment()
    assert experiment.locked_variables
    assert experiment.rollback_condition
    assert any(metric.has_baseline for metric in experiment.baseline_metrics)
    assert CAUSALITY_CAVEAT in experiment.limitations
    assert experiment.windows_comparable


def test_an_experiment_with_no_locked_variables_is_refused():
    with pytest.raises(OrgIntelligenceError, match="name what was held still"):
        an_experiment(locked_variables=())


def test_an_experiment_with_no_measured_baseline_is_refused():
    with pytest.raises(OrgIntelligenceError, match="no baseline metric carries a measured value"):
        an_experiment(
            baseline_metrics=(
                a_metric(baseline=Measurement(), target_value=None),
            )
        )


def test_mismatched_baseline_and_observation_windows_become_a_limitation():
    experiment = an_experiment(
        observation_window=ReviewWindow(start=TODAY, end=TODAY + dt.timedelta(days=2))
    )
    assert not experiment.windows_comparable
    assert any("window lengths differ" in item for item in experiment.limitations)


def test_a_post_change_review_never_claims_causality():
    review = OrganizationChangeReview(
        review_id="chr-001",
        experiment_id="exp-001",
        observed_window=ReviewWindow(start=TODAY, end=TODAY + dt.timedelta(days=29)),
        outcome=ChangeOutcome.KEEP,
        summary="Median hops fell from three to two and no class-A defect shipped.",
        comparisons=(
            MetricComparison(
                metric_id="m-cycle-time",
                expected=Measurement(
                    value=3.0, unit="hops", threshold=2.0, direction=Direction.HIGHER_IS_WORSE
                ),
                actual=Measurement(
                    value=2.0, unit="hops", threshold=2.0, direction=Direction.HIGHER_IS_WORSE
                ),
            ),
        ),
        evidence=(an_evidence("measurement", "company/state/usage/class-a-after.json"),),
        observation_count=1,
    )
    assert review.claims_causality is False
    assert CAUSALITY_CAVEAT in review.caveat
    assert SINGLE_OBSERVATION_CAVEAT in review.limitations
    assert review.improved == ("m-cycle-time",)
    assert review.worsened == ()


def test_the_causality_caveat_cannot_be_removed():
    with pytest.raises(AdvisoryViolation, match="may be extended but not removed"):
        OrganizationChangeReview(
            review_id="chr-002",
            experiment_id="exp-001",
            observed_window=WINDOW,
            outcome=ChangeOutcome.KEEP,
            summary="It worked.",
            evidence=(an_evidence(),),
            caveat="",
        )


def test_an_unmeasured_comparison_is_reported_as_unmeasured():
    comparison = MetricComparison(
        metric_id="m-cycle-time",
        expected=Measurement(value=3.0, unit="hops"),
        actual=Measurement(),
    )
    assert comparison.delta is None
    assert comparison.moved is None


def test_nothing_in_this_package_rolls_a_change_back():
    import company.org_intelligence.change as change

    source = Path(change.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }
    assert not {"rollback", "revert", "apply", "execute"} & names


# --------------------------------------------------------------------------
# Automation candidates
# --------------------------------------------------------------------------


def a_repeated_work(**overrides) -> RepeatedWork:
    data = dict(
        action_id="regenerate-qc-manifest",
        instances=("task/qc-101", "task/qc-118", "task/qc-133"),
        deterministic_rationale=(
            "The same inputs produce the same manifest, and a test checks the output."
        ),
        window=WINDOW,
        evidence=(an_evidence("observation", "company/state/tasks/qc-101.json"),),
    )
    data.update(overrides)
    return RepeatedWork(**data)


def test_an_automation_candidate_requires_repeated_evidence():
    with pytest.raises(OrgIntelligenceError, match="below the 3 this claim declares"):
        a_repeated_work(instances=("task/qc-101",))
    with pytest.raises(OrgIntelligenceError, match="appears twice"):
        a_repeated_work(instances=("task/qc-101", "task/qc-101", "task/qc-118"))


def test_the_repetition_floor_cannot_be_lowered_below_two():
    with pytest.raises(OrgIntelligenceError, match="minimum_instances"):
        a_repeated_work(minimum_instances=1)


def test_an_automation_candidate_finding_carries_the_determinism_caveat():
    finding = automation_candidate("find-auto", a_repeated_work())
    assert finding.category is FindingCategory.AUTOMATION_CANDIDATE
    assert finding.subjects == ("regenerate-qc-manifest",)
    assert any("asserted by whoever filed this" in item for item in finding.limitations)
    assert any("unquantified" in item for item in finding.limitations)


def test_repeated_work_needs_evidence_not_only_references():
    with pytest.raises(OrgIntelligenceError, match="at least one piece of evidence"):
        a_repeated_work(evidence=())


# --------------------------------------------------------------------------
# Priority: deterministic, and the weights are on the record
# --------------------------------------------------------------------------


def test_priority_weights_must_be_supplied_and_are_stored_on_the_result():
    with pytest.raises(OrgIntelligenceError, match="at least one weight"):
        PriorityWeights({})
    weights = PriorityWeights({"urgency": 2.0, "expected_impact": 1.0})
    priority = prioritise(
        "rec-001",
        (DimensionValue("urgency", 3.0), DimensionValue("expected_impact", 2.0)),
        weights,
    )
    assert priority.total == pytest.approx(8.0)
    assert priority.is_complete
    assert priority.to_dict()["weights"] == {"urgency": 2.0, "expected_impact": 1.0}


def test_a_missing_priority_dimension_stays_visible():
    weights = PriorityWeights({"urgency": 2.0, "implementation_cost": 1.0})
    priority = prioritise("rec-002", (DimensionValue("urgency", 3.0),), weights)
    assert priority.total == pytest.approx(6.0)
    assert priority.missing_dimensions == ("implementation_cost",)
    assert not priority.is_complete


def test_ranking_is_deterministic_and_puts_complete_priorities_first():
    weights = PriorityWeights({"urgency": 1.0, "expected_impact": 1.0})
    complete = prioritise(
        "rec-b",
        (DimensionValue("urgency", 2.0), DimensionValue("expected_impact", 2.0)),
        weights,
    )
    partial = prioritise("rec-a", (DimensionValue("urgency", 4.0),), weights)
    assert [item.recommendation_id for item in rank((partial, complete))] == ["rec-b", "rec-a"]
    assert rank((partial, complete)) == rank((complete, partial))


def test_an_unknown_priority_dimension_is_refused():
    with pytest.raises(OrgIntelligenceError, match="not a priority dimension"):
        PriorityWeights({"vibes": 1.0})
    with pytest.raises(OrgIntelligenceError, match="not a priority dimension"):
        DimensionValue("vibes", 1.0)


# --------------------------------------------------------------------------
# Store: deterministic, and no silent overwrite
# --------------------------------------------------------------------------


def a_change_review(**overrides) -> OrganizationChangeReview:
    data = dict(
        review_id="chr-001",
        experiment_id="exp-001",
        observed_window=ReviewWindow(start=TODAY, end=TODAY + dt.timedelta(days=29)),
        outcome=ChangeOutcome.KEEP,
        summary="Median hops fell from three to two and no class-A defect shipped.",
        comparisons=(
            MetricComparison(
                metric_id="m-cycle-time",
                expected=Measurement(
                    value=3.0, unit="hops", threshold=2.0, direction=Direction.HIGHER_IS_WORSE
                ),
                actual=Measurement(
                    value=2.0, unit="hops", threshold=2.0, direction=Direction.HIGHER_IS_WORSE
                ),
            ),
        ),
        evidence=(an_evidence("measurement", "company/state/usage/class-a-after.json"),),
        observation_count=4,
        reviewed_by="the COO",
    )
    data.update(overrides)
    return OrganizationChangeReview(**data)


def test_records_round_trip_through_the_store_as_identical_bytes(tmp_path):
    store = OrgIntelligenceStore(tmp_path)
    records = (
        a_review(),
        a_signal(),
        a_finding(),
        a_recommendation(),
        a_change_proposal(),
        an_experiment(),
        a_change_review(),
    )
    for record in records:
        store.put(record)
    assert store.get("review", "orv-2026-09") == a_review()
    assert store.get("signal", "sig-001") == a_signal()
    assert store.get("finding", "find-001") == a_finding()
    assert store.get("recommendation", "rec-001") == a_recommendation()
    assert store.get("change_proposal", "chg-001") == a_change_proposal()
    assert store.get("experiment", "exp-001") == an_experiment()
    assert store.get("change_review", "chr-001") == a_change_review()
    assert store.ids("signal") == ("sig-001",)


def test_two_equal_records_produce_identical_bytes():
    assert dumps(a_finding().to_dict()) == dumps(a_finding().to_dict())
    assert dumps(a_signal().to_dict()) == dumps(a_signal().to_dict())


def test_the_store_refuses_a_silent_overwrite(tmp_path):
    store = OrgIntelligenceStore(tmp_path)
    path = store.put(a_finding())
    assert store.put(a_finding()) == path  # identical bytes: a no-op

    changed = a_finding(statement="A different claim under the same id.")
    with pytest.raises(OrgIntelligenceStoreError, match="already holds a different finding"):
        store.put(changed)
    store.put(changed, replace=True)
    assert store.get("finding", "find-001").statement.startswith("A different claim")


def test_appended_observations_never_reopen_an_existing_record(tmp_path):
    store = OrgIntelligenceStore(tmp_path)
    first = store.append_observation({"note": "one"})
    second = store.append_observation({"note": "one"})
    assert first != second
    assert [item["note"] for item in store.observations()] == ["one", "one"]


def test_the_store_needs_an_explicit_directory():
    with pytest.raises(OrgIntelligenceStoreError, match="explicit non-empty path"):
        OrgIntelligenceStore("   ")


def test_a_malformed_record_on_disk_is_reported_with_its_path(tmp_path):
    store = OrgIntelligenceStore(tmp_path)
    store.put(a_finding())
    path = tmp_path / "findings" / "find-001.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["evidence"] = []
    path.write_text(dumps(data), encoding="utf-8")
    with pytest.raises(OrgIntelligenceStoreError, match="does not decode"):
        store.get("finding", "find-001")


# --------------------------------------------------------------------------
# Integrity
# --------------------------------------------------------------------------


def test_a_recommendation_referencing_a_missing_finding_is_reported():
    issues = check_integrity(
        findings=(a_finding(),),
        recommendations=(a_recommendation(finding_ids=("find-missing",)),),
    )
    assert any("find-missing" in issue for issue in issues)


def test_a_change_proposal_referencing_a_missing_recommendation_is_reported():
    issues = check_integrity(
        recommendations=(a_recommendation(),),
        change_proposals=(a_change_proposal(recommendation_ids=("rec-missing",)),),
    )
    assert any("rec-missing" in issue for issue in issues)


def test_an_unknown_employee_is_rejected(config):
    signal = a_signal(signal_id="sig-ghost", subject="nobody_here")
    issues = check_integrity(org_registry=config.org_registry, signals=(signal,))
    assert any("unknown employee 'nobody_here'" in issue for issue in issues)

    known = a_signal(signal_id="sig-known", subject="studio_coo")
    assert check_integrity(org_registry=config.org_registry, signals=(known,)) == ()


def test_an_unknown_capability_subject_is_rejected(config, registry):
    signal = a_signal(
        signal_id="sig-cap",
        subject="not_a_capability",
        subject_kind=SubjectKind.CAPABILITY,
    )
    issues = check_integrity(
        org_registry=config.org_registry,
        capability_ids=registry.graph.ids(),
        signals=(signal,),
    )
    assert any("unknown capability" in issue for issue in issues)


def test_duplicate_record_ids_are_reported():
    issues = check_integrity(findings=(a_finding(), a_finding(statement="Another claim.")))
    assert any("duplicate record id 'find-001'" in issue for issue in issues)


def test_a_finding_outside_its_review_window_is_reported():
    review = a_review()
    stray = a_finding(
        review_id=review.review_id,
        window=ReviewWindow(start=dt.date(2025, 1, 1), end=dt.date(2025, 1, 31)),
    )
    issues = check_integrity(reviews=(review,), findings=(stray,))
    assert any("lies outside its review's window" in issue for issue in issues)


def test_an_integrity_pass_over_a_consistent_set_is_clean(config, registry):
    review = a_review()
    signal = a_signal(signal_id="sig-001", subject="studio_coo")
    finding = a_finding(review_id=review.review_id, signal_ids=("sig-001",))
    recommendation = a_recommendation(finding_ids=(finding.finding_id,), subjects=("studio_coo",))
    proposal = a_change_proposal(
        recommendation_ids=(recommendation.recommendation_id,),
        affected_subjects=("studio_coo",),
    )
    experiment = an_experiment(change_proposal_id=proposal.proposal_id)
    assert (
        check_integrity(
            org_registry=config.org_registry,
            permissions=config.permissions,
            capability_ids=registry.graph.ids(),
            reviews=(review,),
            signals=(signal,),
            findings=(finding,),
            recommendations=(recommendation,),
            change_proposals=(proposal,),
            experiments=(experiment,),
        )
        == ()
    )


# --------------------------------------------------------------------------
# Guards: the package cannot change the company
# --------------------------------------------------------------------------


def test_the_package_contains_no_writer_for_a_canonical_contract():
    """Section 21, enforced rather than described."""
    reserved = ("org_registry", "permissions.yaml", "agent_contract.schema", "constitution")
    writers = ("write_text", "write_bytes", "open", "write_json", "mkdir", "unlink")
    for path in sorted(PACKAGE_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            rendered = ast.dump(node)
            if any(name in rendered for name in reserved) and any(
                writer in rendered for writer in writers
            ):
                pytest.fail(f"{path.name} appears to write a company contract file")


def test_running_the_analysis_does_not_touch_a_company_contract(tmp_path, config, registry):
    """The behavioural half of the same rule: the files do not change."""
    before = {
        name: (REPO_ROOT / name).read_bytes() for name in CANONICAL_CONTRACTS
    }
    graph = ManagementGraph.from_org_registry(config.org_registry)
    signals = management_signals(graph, window=WINDOW)
    finding = build_finding(
        "find-live",
        FindingCategory.STRUCTURAL_FACT,
        statement="One management layer has a single direct report.",
        signals=signals,
        what_would_change_it=("a second report arriving under that layer",),
    )
    recommendation = a_recommendation(
        recommendation_id="rec-live", finding_ids=(finding.finding_id,)
    )
    store = OrgIntelligenceStore(tmp_path)
    for record in signals + (finding, recommendation):
        store.put(record)
    check_integrity(
        org_registry=config.org_registry,
        permissions=config.permissions,
        capability_ids=registry.graph.ids(),
        signals=signals,
        findings=(finding,),
        recommendations=(recommendation,),
    )
    after = {name: (REPO_ROOT / name).read_bytes() for name in CANONICAL_CONTRACTS}
    assert before == after


def test_org_intelligence_imports_no_production_module():
    production = {
        "race",
        "sloped",
        "marble3d",
        "rendering",
        "replay",
        "godot",
        "entities",
        "powers",
        "modes",
        "engine",
        "audio",
        "evaluation",
        "production",
        "intelligence",
    }
    for path in sorted(PACKAGE_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            roots: list[str] = []
            if isinstance(node, ast.Import):
                roots = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots = [node.module.split(".")[0]]
            assert not (set(roots) & production), f"{path.name} imports {roots}"


def test_no_dependency_is_added():
    """Standard library, plus what the control plane already imports."""
    internal = {"ai_platform", "company", "knowledge"}
    stdlib = set(__import__("sys").stdlib_module_names)
    for path in sorted(PACKAGE_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module.split(".")[0]]
            for name in names:
                assert name in stdlib | internal, (
                    f"{path.name} imports {name}, which is a new dependency"
                )
    requirements = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert sorted(requirements.split()) == sorted(
        "pymunk>=7.0 pygame>=2.6 pytest>=8.0 pybullet>=3.2.7 pillow>=11.0 numpy>=2.1".split()
    )


def test_no_production_file_is_touched_by_this_workstream():
    """The package owns one directory, one seed, one test file and nothing else."""
    owned = {
        REPO_ROOT / "company" / "org_intelligence",
        REPO_ROOT / "tests" / "test_company_org_intelligence.py",
        SEED_ROOT / "company-organizational-intelligence.json",
    }
    assert all(path.exists() for path in owned)
    for forbidden in ("race", "sloped", "marble3d", "rendering", "godot"):
        assert not (PACKAGE_ROOT / forbidden).exists()


# --------------------------------------------------------------------------
# The capsule
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def seeds():
    return CapsuleIndex.load(SEED_ROOT)


def test_the_organizational_intelligence_capsule_fits_its_budget(seeds):
    capsule = seeds.get("company-organizational-intelligence")
    assert capsule.size_chars() <= DEFAULT_BUDGET.max_capsule_chars
    assert capsule.size_chars() <= 4000
    assert capsule.owns_paths == ("company/org_intelligence",)
    assert capsule.tests == ("tests/test_company_org_intelligence.py",)


def test_the_capsule_states_the_advisory_and_ceo_boundaries(seeds):
    capsule = seeds.get("company-organizational-intelligence")
    joined = " ".join(capsule.invariants).lower()
    assert "advisory only" in joined
    assert "never approves itself" in joined
    assert "no_subagents" in joined
    assert "score exists" in joined
    for path in CANONICAL_CONTRACTS:
        assert path in capsule.must_not_modify or path.endswith("agent_contract.schema.yaml")


def test_the_control_plane_stays_within_its_dependency_cap(seeds):
    control_plane = seeds.get("company-os-control-plane")
    assert len(control_plane.dependencies) <= 8
    assert "company-organizational-intelligence" in control_plane.dependencies
    assert len(control_plane.dependencies) == len(set(control_plane.dependencies))


def test_the_dependency_closure_still_covers_every_company_os_capsule(seeds):
    # The external engineering runner is governed by a capsule but is not a
    # member of the control plane: it owns a path under a production root, so
    # an edge reaching it would declare the control plane rests on production.
    # `company.dashboard.builder.EXTERNAL_CAPSULES` is where that is stated.
    assert seeds.dependency_closure("company-os-control-plane") == tuple(
        sorted(set(seeds.ids()) - {"company-os-control-plane"} - EXTERNAL_CAPSULES)
    )

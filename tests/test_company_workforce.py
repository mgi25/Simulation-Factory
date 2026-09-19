"""Tests for the Company OS workforce/HR foundation.

The suite is organised by the question each group answers, because the
interesting failures here are organizational rather than numerical: not "is this
float right" but "can a candidate reach production authority without an
evaluation".

Four groups are guard tests rather than behaviour tests - they assert the
*absence* of something:

    test_no_global_reputation_score_field_exists
    test_workforce_never_writes_a_company_contract_file
    test_workforce_imports_no_production_module
    test_no_new_dependency_is_introduced

Each of those encodes a rule that would otherwise live only in a docstring, and
a rule that lives only in a docstring comes back.
"""

from __future__ import annotations

import ast
import dataclasses
import datetime as dt
import json
from pathlib import Path

import pytest

from ai_platform.serde import dumps
from ai_platform.usage import Outcome, ResourceUsageRecord, UsageUnit
from ai_platform.resource_classes import ReasoningClass
from company.runtime.config import load_company_config
from company.validation.bootstrap import validate_agent_contract, validate_bootstrap
from company.workforce import (
    ApprovalState,
    AuthorityViolation,
    Capability,
    CapabilityGap,
    CapabilityGraph,
    CapabilityRegistry,
    CapabilityRelation,
    CandidateEvaluation,
    ComparisonDimension,
    ComparisonVerdict,
    CoverageLevel,
    CoverageStatus,
    Criticality,
    DebtKind,
    EmploymentRecord,
    EmploymentState,
    EvaluationCase,
    EvaluationCaseKind,
    EvaluationOutcome,
    EvaluationResult,
    FrequencyEvidence,
    GapTrigger,
    LifecycleViolation,
    NecessitySignal,
    NeedFrequency,
    PerformanceObservation,
    Recommendation,
    RelationKind,
    ResourceBudget,
    RoleSpecification,
    ShadowAssignment,
    ShadowComparison,
    TaskOutcome,
    TriggerKind,
    Urgency,
    WorkforceError,
    WorkforceProposal,
    WorkforceStore,
    advance,
    assert_authority,
    assert_integrity,
    assert_may_not_write_production,
    assess_coverage,
    check_integrity,
    default_case_set,
    detect_debt,
    employee_performance,
    gap_from_coverage,
    graph_to_dict,
    load_capability_graph,
    organization_single_points_of_failure,
    propose_for_gap,
    rank_options,
    resource_summary,
    review_role,
    review_to_proposal,
    shadow_scope_violations,
    summarise_observations,
)
from company.workforce.capabilities import DEFAULT_REGISTRY_PATH
from company.workforce.store import WorkforceStoreError
from knowledge.company_os.records import Evidence

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "company" / "workforce"
TODAY = dt.date(2026, 9, 16)


# -- fixtures --------------------------------------------------------------


@pytest.fixture(scope="module")
def config():
    return load_company_config()


@pytest.fixture(scope="module")
def registry(config):
    return CapabilityRegistry.load(config.org_registry)


def a_registry(employees: dict[str, dict], capabilities=None, relations=()):
    """A small registry with an explicit workforce, for the focused cases."""
    caps = capabilities or ("alpha", "beta", "gamma")
    graph = CapabilityGraph(
        capabilities=tuple(
            Capability(
                capability_id=name,
                name=name.title(),
                description=f"The {name} capability.",
                domain="engineering",
                criticality=Criticality.IMPORTANT,
            )
            for name in caps
        ),
        relations=tuple(relations),
    )
    return CapabilityRegistry(graph, {"employees": employees})


def an_evidence(kind: str = "observation", ref: str = "tests/test_company_workforce.py"):
    return Evidence(kind=kind, ref=ref, note="")


def a_trigger():
    return GapTrigger(
        kind=TriggerKind.TASK,
        ref="task/render-audio-bed-001",
        summary="The audio bed for the V30 cut could not be routed to any employee.",
    )


def a_gap(registry_obj, required, *, frequency: FrequencyEvidence, gap_id="gap-001"):
    report = assess_coverage(required, registry_obj)
    return gap_from_coverage(
        gap_id,
        report,
        trigger=a_trigger(),
        frequency=frequency,
        urgency=Urgency.MEDIUM,
        business_impact="The cut ships without an audio bed, which loses the payoff beat.",
        observed_on=TODAY,
        evidence=(an_evidence("escalation", "company/state/escalations/001.json"),),
    )


def one_off():
    return FrequencyEvidence(
        frequency=NeedFrequency.ONE_OFF,
        observed_occurrences=1,
        window_days=1,
        evidence=(an_evidence(),),
    )


def recurring():
    return FrequencyEvidence(
        frequency=NeedFrequency.RECURRING,
        observed_occurrences=4,
        window_days=60,
        evidence=(
            an_evidence("escalation", "company/state/escalations/001.json"),
            an_evidence("escalation", "company/state/escalations/014.json"),
        ),
    )


def a_role(**overrides) -> RoleSpecification:
    defaults = dict(
        role_id="audio_design_lead",
        mission="Own the audio bed, its mix, and its relationship to the cut.",
        department="production",
        manager="studio_coo",
        required_capabilities=("qc",),
        inputs=("A locked cut and its shot list",),
        outputs=("A mixed audio bed and a QC note",),
        may_read=("sloped/**", "docs/**"),
        quality_gates=("loudness within the delivery spec",),
        success_metrics=("first_pass_success",),
        proposed_on=TODAY,
    )
    defaults.update(overrides)
    return RoleSpecification(**defaults)


def an_evaluation(**overrides) -> CandidateEvaluation:
    defaults = dict(
        evaluation_id="eval-001",
        candidate_id="audio_design_lead",
        role_specification_id="audio_design_lead",
        cases=default_case_set("audio_design_lead"),
        opened_on=TODAY,
    )
    defaults.update(overrides)
    return CandidateEvaluation(**defaults)


def passed_evaluation() -> CandidateEvaluation:
    evaluation = an_evaluation()
    outcomes = tuple(
        EvaluationOutcome(
            test_id=case.test_id,
            result=EvaluationResult.PASS,
            evaluator="chief_architect",
            on=TODAY,
            observed_evidence=(an_evidence("test", f"tests/eval/{case.test_id}.json"),),
        )
        for case in evaluation.cases
    )
    return dataclasses.replace(evaluation, outcomes=outcomes)


def a_shadow(**overrides) -> ShadowAssignment:
    defaults = dict(
        assignment_id="shadow-001",
        candidate_id="audio_design_lead",
        baseline_employee_id="production_qc_lead",
        task_ref="task/render-audio-bed-001",
        capabilities=("qc",),
        may_read=("sloped/**",),
        objective="Produce an audio bed for the same cut the incumbent is working on.",
        assigned_on=TODAY,
    )
    defaults.update(overrides)
    return ShadowAssignment(**defaults)


def a_comparison(**overrides) -> ShadowComparison:
    defaults = dict(
        comparison_id="cmp-001",
        assignment_id="shadow-001",
        candidate_result_ref="exports/shadow/001/candidate.wav",
        baseline_result_ref="exports/shadow/001/baseline.wav",
        verdict=ComparisonVerdict.EQUIVALENT,
        evaluator="production_qc_lead",
        on=TODAY,
        dimensions=(
            ComparisonDimension(
                name="loudness",
                candidate="-14.1 LUFS",
                baseline="-14.0 LUFS",
                verdict=ComparisonVerdict.EQUIVALENT,
            ),
        ),
    )
    defaults.update(overrides)
    return ShadowComparison(**defaults)


# -- 1. capability registry ------------------------------------------------


def test_the_shipped_capability_registry_loads_and_is_deterministic():
    graph = load_capability_graph()
    again = load_capability_graph()
    assert graph.ids() == again.ids()
    assert graph_to_dict(graph) == graph_to_dict(again)
    assert dumps(graph_to_dict(graph)) == DEFAULT_REGISTRY_PATH.read_text(encoding="utf-8")


def test_every_org_registry_capability_is_defined(registry):
    assert registry.unregistered_employee_capabilities() == ()


def test_a_capability_record_carries_no_provider_list():
    """Providers are derived. A stored `provided_by` would go stale in a week."""
    fields = {field.name for field in dataclasses.fields(Capability)}
    assert "provided_by" not in fields
    assert "employees" not in fields


def test_duplicate_capability_ids_are_refused():
    twice = Capability(
        capability_id="alpha",
        name="Alpha",
        description="The alpha capability.",
        domain="engineering",
    )
    with pytest.raises(WorkforceError, match="duplicate capability id"):
        CapabilityGraph(capabilities=(twice, twice))


def test_providers_are_derived_from_the_org_registry(registry):
    resolved = registry.providers("software_architecture")
    assert resolved.active_providers == ("chief_architect",)
    assert resolved.dormant_providers == ()
    assert resolved.provided_by == ("chief_architect",)


# -- 2. capability graph ---------------------------------------------------


def test_the_brief_decompositions_are_explicit_data(registry):
    assert set(registry.graph.descendants("cinematography")) >= {
        "framing",
        "camera_continuity",
        "occlusion_analysis",
        "mobile_readability",
    }
    assert set(registry.graph.descendants("research_intelligence")) == {
        "source_analysis",
        "reference_analysis",
        "opportunity_analysis",
    }


def test_a_cycle_in_an_acyclic_relation_kind_is_refused():
    capabilities = tuple(
        Capability(
            capability_id=name,
            name=name,
            description=f"{name}.",
            domain="engineering",
        )
        for name in ("a", "b", "c")
    )
    relations = (
        CapabilityRelation(kind=RelationKind.COMPRISES, source="a", target="b"),
        CapabilityRelation(kind=RelationKind.COMPRISES, source="b", target="c"),
        CapabilityRelation(kind=RelationKind.COMPRISES, source="c", target="a"),
    )
    with pytest.raises(WorkforceError, match="cycle detected"):
        CapabilityGraph(capabilities=capabilities, relations=relations)


def test_a_symmetric_relation_is_not_treated_as_a_cycle():
    """`related_to` is symmetric, so every edge is a two-cycle. Checking it would be noise."""
    capabilities = tuple(
        Capability(capability_id=n, name=n, description=f"{n}.", domain="engineering")
        for n in ("a", "b")
    )
    graph = CapabilityGraph(
        capabilities=capabilities,
        relations=(CapabilityRelation(kind=RelationKind.RELATED_TO, source="a", target="b"),),
    )
    assert graph.cycles() == ()
    assert graph.descendants("a", RelationKind.RELATED_TO) == ("b",)
    assert graph.descendants("b", RelationKind.RELATED_TO) == ("a",)


def test_a_relation_to_an_unknown_capability_is_refused():
    capability = Capability(
        capability_id="a", name="a", description="a.", domain="engineering"
    )
    with pytest.raises(WorkforceError, match="unknown capability"):
        CapabilityGraph(
            capabilities=(capability,),
            relations=(
                CapabilityRelation(kind=RelationKind.REQUIRES, source="a", target="nope"),
            ),
        )


# -- 3. coverage -----------------------------------------------------------


def test_coverage_separates_active_capacity_from_organizational_capability():
    registry_obj = a_registry(
        {
            "runner": {"state": "active", "capabilities": ["alpha"], "manager": "ceo"},
            "sleeper": {"state": "dormant", "capabilities": ["beta"], "manager": "ceo"},
        }
    )
    report = assess_coverage(("alpha", "beta", "gamma"), registry_obj)
    assert report.fully_covered == ("alpha",)
    assert report.partially_covered == ("beta",)
    assert report.uncovered == ("gamma",)
    assert report.status is CoverageStatus.PARTIAL
    assert report.get("beta").level is CoverageLevel.DORMANT_ONLY
    assert report.active_employees == ("runner",)
    assert report.dormant_employees == ("sleeper",)


def test_a_restricted_employee_is_neither_active_nor_organizational_coverage():
    """A candidate under evaluation is not the answer to the gap they were hired for."""
    registry_obj = a_registry(
        {"hopeful": {"state": "candidate", "capabilities": ["alpha"], "manager": "ceo"}}
    )
    coverage = assess_coverage(("alpha",), registry_obj).get("alpha")
    assert coverage.level is CoverageLevel.UNCOVERED
    assert coverage.restricted_providers == ("hopeful",)
    assert coverage.organizational_providers == ()


def test_a_missing_capability_is_detected():
    registry_obj = a_registry(
        {"runner": {"state": "active", "capabilities": ["alpha"], "manager": "ceo"}}
    )
    report = assess_coverage(("alpha", "gamma"), registry_obj)
    assert report.uncovered == ("gamma",)
    assert report.status is CoverageStatus.PARTIAL


def test_a_single_point_of_failure_is_detected():
    registry_obj = a_registry(
        {
            "only_one": {"state": "active", "capabilities": ["alpha"], "manager": "ceo"},
            "one_of_two": {"state": "active", "capabilities": ["beta"], "manager": "ceo"},
            "two_of_two": {"state": "dormant", "capabilities": ["beta"], "manager": "ceo"},
        }
    )
    report = assess_coverage(("alpha", "beta"), registry_obj)
    assert report.single_points_of_failure == ("alpha",)


def test_organization_wide_single_points_of_failure_are_ordered_by_criticality(registry):
    found = organization_single_points_of_failure(registry)
    criticalities = [coverage.criticality for coverage in found]
    assert criticalities == sorted(
        criticalities, key=lambda c: [Criticality.CORE, Criticality.IMPORTANT].index(c)
    )
    assert all(len(coverage.organizational_providers) == 1 for coverage in found)


def test_expanding_a_requirement_is_opt_in(registry):
    narrow = assess_coverage(("cinematography",), registry)
    wide = assess_coverage(("cinematography",), registry, expand=True)
    assert narrow.required == ("cinematography",)
    assert set(wide.required) > set(narrow.required)
    assert "occlusion_analysis" in wide.uncovered


def test_requiring_an_unregistered_capability_is_refused(registry):
    with pytest.raises(WorkforceError, match="unknown capabilities"):
        assess_coverage(("sound_desgin",), registry)


# -- 4. the gap record -----------------------------------------------------


def test_a_gap_without_evidence_is_refused():
    registry_obj = a_registry({})
    report = assess_coverage(("alpha",), registry_obj)
    with pytest.raises(WorkforceError, match="evidence is required"):
        gap_from_coverage(
            "gap-x",
            report,
            trigger=a_trigger(),
            frequency=one_off(),
            urgency=Urgency.LOW,
            business_impact="It would be nice to have a sound designer.",
            observed_on=TODAY,
        )


def test_full_active_coverage_cannot_become_a_gap():
    registry_obj = a_registry(
        {"runner": {"state": "active", "capabilities": ["alpha"], "manager": "ceo"}}
    )
    report = assess_coverage(("alpha",), registry_obj)
    with pytest.raises(WorkforceError, match="there is no gap"):
        gap_from_coverage(
            "gap-x",
            report,
            trigger=a_trigger(),
            frequency=one_off(),
            urgency=Urgency.LOW,
            business_impact="x",
            observed_on=TODAY,
            evidence=(an_evidence(),),
        )


def test_the_code_will_not_decide_that_a_need_recurs():
    with pytest.raises(WorkforceError, match="will not decide that a need recurs"):
        FrequencyEvidence(
            frequency=NeedFrequency.RECURRING,
            observed_occurrences=1,
            window_days=30,
            evidence=(an_evidence(),),
        )


def test_a_recurring_claim_needs_pointers_not_a_remembered_count():
    with pytest.raises(WorkforceError, match="evidence is required"):
        FrequencyEvidence(
            frequency=NeedFrequency.RECURRING, observed_occurrences=5, window_days=60
        )


def test_a_gap_records_its_coverage_split_from_the_report():
    registry_obj = a_registry(
        {
            "runner": {"state": "active", "capabilities": ["alpha"], "manager": "ceo"},
            "sleeper": {"state": "dormant", "capabilities": ["beta"], "manager": "ceo"},
        }
    )
    gap = a_gap(registry_obj, ("alpha", "beta", "gamma"), frequency=one_off())
    assert gap.covered_actively == ("alpha",)
    assert gap.covered_dormant == ("beta",)
    assert gap.missing == ("gamma",)
    assert not gap.is_activation_only


# -- 5. prove need before hiring -------------------------------------------


def test_existing_coverage_prevents_an_unnecessary_hire_proposal():
    """No gap record can be built at all, so no proposal exists to be made."""
    registry_obj = a_registry(
        {
            "runner": {
                "state": "active",
                "capabilities": ["alpha", "beta"],
                "manager": "ceo",
            }
        }
    )
    report = assess_coverage(("alpha", "beta"), registry_obj)
    assert report.status is CoverageStatus.FULL
    assert report.employees_covering_all() == ("runner",)
    with pytest.raises(WorkforceError, match="there is no gap"):
        gap_from_coverage(
            "gap-x",
            report,
            trigger=a_trigger(),
            frequency=recurring(),
            urgency=Urgency.HIGH,
            business_impact="x",
            observed_on=TODAY,
            evidence=(an_evidence(),),
        )


def test_a_dormant_provider_produces_activation_not_a_hire():
    registry_obj = a_registry(
        {"sleeper": {"state": "dormant", "capabilities": ["alpha"], "manager": "ceo"}}
    )
    gap = a_gap(registry_obj, ("alpha",), frequency=recurring())
    assert gap.is_activation_only
    proposal = propose_for_gap(
        gap,
        registry_obj,
        proposal_id="prop-001",
        proposed_on=TODAY,
        report=assess_coverage(("alpha",), registry_obj),
    )
    assert proposal.recommendation is Recommendation.ACTIVATE_DORMANT_EMPLOYEE
    assert proposal.subject_employee_ids == ("sleeper",)


def test_a_one_off_need_recommends_a_temporary_specialist():
    registry_obj = a_registry({})
    gap = a_gap(registry_obj, ("alpha",), frequency=one_off())
    proposal = propose_for_gap(
        gap, registry_obj, proposal_id="prop-002", proposed_on=TODAY
    )
    assert proposal.recommendation is Recommendation.TEMPORARY_SPECIALIST
    assert proposal.gap_id == "gap-001"


def test_a_recurring_gap_with_nobody_adjacent_produces_a_candidate_role():
    registry_obj = a_registry({})
    gap = a_gap(registry_obj, ("alpha",), frequency=recurring())
    proposal = propose_for_gap(
        gap,
        registry_obj,
        proposal_id="prop-003",
        proposed_on=TODAY,
        role_specification_id="audio_design_lead",
    )
    assert proposal.recommendation is Recommendation.CREATE_CANDIDATE_ROLE
    assert proposal.role_specification_id == "audio_design_lead"


def test_overlapping_coverage_prefers_retraining_over_a_hire():
    """An employee one explicit relation hop away is cheaper than a permanent role."""
    registry_obj = a_registry(
        {"runner": {"state": "active", "capabilities": ["beta"], "manager": "ceo"}},
        relations=(
            CapabilityRelation(kind=RelationKind.RELATED_TO, source="alpha", target="beta"),
        ),
    )
    gap = a_gap(registry_obj, ("alpha",), frequency=recurring())
    proposal = propose_for_gap(
        gap, registry_obj, proposal_id="prop-004", proposed_on=TODAY
    )
    assert proposal.recommendation is Recommendation.RETRAIN_EMPLOYEE
    assert proposal.subject_employee_ids == ("runner",)


def test_every_option_is_reported_whether_or_not_it_was_chosen():
    registry_obj = a_registry({})
    gap = a_gap(registry_obj, ("alpha",), frequency=one_off())
    options = rank_options(gap, registry_obj)
    assert {option.recommendation for option in options} == {
        Recommendation.NO_ACTION,
        Recommendation.USE_EXISTING_EMPLOYEE,
        Recommendation.ACTIVATE_DORMANT_EMPLOYEE,
        Recommendation.RETRAIN_EMPLOYEE,
        Recommendation.TEMPORARY_SPECIALIST,
        Recommendation.CREATE_CANDIDATE_ROLE,
    }
    assert options[0].viable
    assert all(option.reason for option in options)


def test_the_ranking_is_deterministic():
    registry_obj = a_registry({})
    gap = a_gap(registry_obj, ("alpha",), frequency=recurring())
    first = rank_options(gap, registry_obj)
    second = rank_options(gap, registry_obj)
    assert [o.recommendation for o in first] == [o.recommendation for o in second]


# -- 6. proposals do not act -----------------------------------------------


def test_a_proposal_is_born_proposed_and_has_no_apply():
    registry_obj = a_registry({})
    gap = a_gap(registry_obj, ("alpha",), frequency=one_off())
    proposal = propose_for_gap(
        gap, registry_obj, proposal_id="prop-005", proposed_on=TODAY
    )
    assert proposal.approval is ApprovalState.PROPOSED
    assert not hasattr(proposal, "apply")
    assert not hasattr(proposal, "execute")


def test_new_capacity_must_name_the_gap_it_answers():
    with pytest.raises(WorkforceError, match="prove need before building"):
        WorkforceProposal(
            proposal_id="prop-x",
            recommendation=Recommendation.TEMPORARY_SPECIALIST,
            rationale="We want one.",
            proposed_on=TODAY,
        )


def test_a_permanent_role_proposal_must_carry_a_specification():
    with pytest.raises(WorkforceError, match="A department and a title are not a role"):
        WorkforceProposal(
            proposal_id="prop-x",
            recommendation=Recommendation.CREATE_CANDIDATE_ROLE,
            rationale="We want one.",
            proposed_on=TODAY,
            gap_id="gap-001",
        )


def test_an_executive_hire_is_flagged_for_the_ceo(config):
    from company.workforce import requires_ceo_approval

    assert requires_ceo_approval(
        Recommendation.CREATE_CANDIDATE_ROLE,
        department="executive",
        permissions=config.permissions,
    )
    assert not requires_ceo_approval(
        Recommendation.CREATE_CANDIDATE_ROLE,
        department="production",
        permissions=config.permissions,
    )
    # Fails closed with no permission file to read.
    assert requires_ceo_approval(Recommendation.ARCHIVE_ROLE, department="executive")


# -- 7. role specification -------------------------------------------------


def test_a_proposed_role_keeps_no_subagents_true():
    assert a_role().no_subagents is True
    with pytest.raises(WorkforceError, match="must be exactly True"):
        a_role(no_subagents=False)


def test_a_candidate_role_cannot_receive_production_authority():
    with pytest.raises(AuthorityViolation, match="production authority"):
        a_role(proposed_may_write=("approved_code_write",))


def test_a_restricted_role_contract_emits_no_write_scope(config):
    role = a_role(state="candidate", proposed_may_write=("audio/**",))
    contract = role.to_contract(permissions=config.permissions)
    assert contract["may_write"] == []
    assert contract["autonomy_level"] == 0
    assert contract["production_authority"] is False
    assert contract["no_subagents"] is True


def test_a_proposed_role_contract_satisfies_the_canonical_agent_schema(config):
    validate_agent_contract(a_role().to_contract(permissions=config.permissions), config)


def test_approving_a_role_changes_only_the_approval_field():
    from company.workforce import approve_role_specification

    role = a_role()
    approved = approve_role_specification(
        role, by="ceo", on=TODAY, reason="The gap is proven and the budget exists."
    )
    assert approved.approval is ApprovalState.APPROVED
    assert dataclasses.replace(approved, approval=ApprovalState.PROPOSED) == role


def test_a_role_with_no_capabilities_is_a_title():
    with pytest.raises(WorkforceError, match="a role with no capabilities is a title"):
        a_role(required_capabilities=())


def test_a_resource_budget_is_a_class_not_a_token_count():
    fields = {field.name for field in dataclasses.fields(ResourceBudget)}
    assert "tokens" not in fields and "max_tokens" not in fields
    assert ResourceBudget().budget_class == "small"


# -- 8. candidate evaluation -----------------------------------------------


def test_the_compliance_cases_cannot_be_dropped():
    cases = tuple(
        case
        for case in default_case_set("x")
        if case.kind is not EvaluationCaseKind.NO_SUBAGENT_COMPLIANCE
    )
    with pytest.raises(WorkforceError, match="missing mandatory case"):
        an_evaluation(cases=cases)


def test_a_pass_needs_observed_evidence():
    with pytest.raises(WorkforceError, match="a score someone made up"):
        EvaluationOutcome(
            test_id="x-permission-compliance",
            result=EvaluationResult.PASS,
            evaluator="chief_architect",
            on=TODAY,
        )


def test_a_missing_outcome_is_a_fail_not_a_skip():
    evaluation = an_evaluation()
    assert not evaluation.passed
    assert len(evaluation.pending) == len(evaluation.cases)


def test_a_passed_evaluation_reports_pass_and_can_be_evidence():
    evaluation = passed_evaluation()
    assert evaluation.passed
    assert evaluation.as_evidence().kind == "candidate_evaluation"


def test_evaluation_results_stay_capability_scoped():
    case = EvaluationCase(
        test_id="x-architecture",
        kind=EvaluationCaseKind.ARCHITECTURE_COMPREHENSION,
        objective="State the boundary.",
        expected_evidence=("a boundary summary",),
        capability_id="software_architecture",
    )
    evaluation = an_evaluation(cases=default_case_set("x") + (case,))
    assert "software_architecture" in evaluation.results_by_capability()


def test_an_outcome_for_an_undeclared_case_is_refused():
    with pytest.raises(WorkforceError, match="undeclared case"):
        an_evaluation(
            outcomes=(
                EvaluationOutcome(
                    test_id="not-a-case",
                    result=EvaluationResult.FAIL,
                    evaluator="x",
                    on=TODAY,
                    note="n/a",
                ),
            )
        )


def test_evaluation_evidence_survives_a_round_trip(tmp_path):
    store = WorkforceStore(tmp_path)
    store.put(passed_evaluation())
    loaded = store.get("evaluation", "eval-001")
    assert loaded.passed
    assert loaded == passed_evaluation()
    assert loaded.outcomes[0].observed_evidence[0].ref.startswith("tests/eval/")


# -- 9. shadow mode --------------------------------------------------------


def test_a_shadow_cannot_hold_a_write_scope():
    with pytest.raises(AuthorityViolation, match="may_write must be empty"):
        a_shadow(may_write=("audio/**",))


def test_a_shadow_cannot_hold_production_write():
    with pytest.raises(AuthorityViolation, match="production_write must be False"):
        a_shadow(production_write=True)


def test_a_shadow_that_attempted_a_write_is_reported():
    violations = shadow_scope_violations(a_shadow(), ("sloped/cameras.py", "production_write"))
    assert len(violations) == 3
    assert any("production authority" in item for item in violations)


def test_a_shadow_autonomy_level_is_capped_by_permissions(config):
    with pytest.raises(AuthorityViolation, match="may not hold autonomy level"):
        a_shadow(autonomy_level=3).check_authority(config.permissions)
    a_shadow(autonomy_level=1).check_authority(config.permissions)


def test_a_shadow_carries_a_session_packet_slot_that_is_not_wired():
    """The field exists so the boundary can meet SessionPacket later; nothing imports it."""
    assignment = a_shadow(session_packet_ref="packets/shadow-001.json")
    assert assignment.session_packet_ref == "packets/shadow-001.json"
    tree = ast.parse((PACKAGE_ROOT / "shadow.py").read_text(encoding="utf-8"))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "company.runtime.packets" not in imported


def test_a_verdict_without_dimensions_is_a_preference():
    with pytest.raises(WorkforceError, match="needs at least one named dimension"):
        a_comparison(verdict=ComparisonVerdict.CANDIDATE_BETTER, dimensions=())


# -- 10. probation lifecycle -----------------------------------------------


def test_candidate_cannot_jump_straight_to_active():
    record = EmploymentRecord(employee_id="audio_design_lead")
    with pytest.raises(LifecycleViolation, match="cannot go from 'candidate' to 'active'"):
        advance(
            record,
            EmploymentState.ACTIVE,
            on=TODAY,
            by="ceo",
            reason="They seem good.",
            evidence=(an_evidence("candidate_evaluation", "eval-001"),),
        )


def test_each_gate_requires_its_own_evidence():
    record = EmploymentRecord(employee_id="audio_design_lead")
    with pytest.raises(LifecycleViolation, match="role_approval"):
        advance(record, EmploymentState.SHADOW, on=TODAY, by="ceo", reason="Start shadowing.")


def test_the_full_candidate_to_active_walk_needs_every_gate():
    record = EmploymentRecord(employee_id="audio_design_lead")
    record = advance(
        record,
        EmploymentState.SHADOW,
        on=TODAY,
        by="studio_coo",
        reason="The role specification was approved.",
        evidence=(an_evidence("role_approval", "role/audio_design_lead"),),
    )
    record = advance(
        record,
        EmploymentState.PROBATION,
        on=TODAY,
        by="chief_architect",
        reason="Every required evaluation case passed.",
        evidence=(passed_evaluation().as_evidence(),),
    )
    with pytest.raises(LifecycleViolation, match="probation_review"):
        advance(
            record,
            EmploymentState.ACTIVE,
            on=TODAY,
            by="ceo",
            reason="Good enough.",
            evidence=(a_comparison().as_evidence(),),
        )
    record = advance(
        record,
        EmploymentState.ACTIVE,
        on=TODAY,
        by="ceo",
        reason="Probation complete and the comparison held.",
        evidence=(
            a_comparison().as_evidence(),
            an_evidence("probation_review", "docs/probation/audio_design_lead.md"),
        ),
    )
    assert record.state is EmploymentState.ACTIVE
    assert len(record.history) == 3


def test_a_rejected_candidate_is_terminal_and_is_not_an_org_registry_state():
    record = advance(
        EmploymentRecord(employee_id="audio_design_lead"),
        EmploymentState.REJECTED,
        on=TODAY,
        by="chief_architect",
        reason="The seeded-bug case failed twice.",
    )
    assert record.state.is_terminal
    assert record.state.registry_state is None
    with pytest.raises(LifecycleViolation, match="terminal"):
        advance(record, EmploymentState.SHADOW, on=TODAY, by="x", reason="Try again.")


def test_archived_does_not_silently_return_to_active():
    from company.workforce import ALLOWED_TRANSITIONS

    assert ALLOWED_TRANSITIONS[EmploymentState.ARCHIVED] == frozenset(
        {EmploymentState.DORMANT}
    )


def test_archived_returns_only_through_a_recorded_reactivation_decision():
    record = EmploymentRecord(
        employee_id="research_opportunity_lead", state=EmploymentState.ARCHIVED
    )
    with pytest.raises(LifecycleViolation, match="cannot go from 'archived' to 'active'"):
        advance(record, EmploymentState.ACTIVE, on=TODAY, by="ceo", reason="We need them.")
    with pytest.raises(LifecycleViolation, match="reactivation_decision"):
        advance(record, EmploymentState.DORMANT, on=TODAY, by="ceo", reason="We need them.")
    woken = advance(
        record,
        EmploymentState.DORMANT,
        on=TODAY,
        by="ceo",
        reason="The trend research gap reopened.",
        evidence=(an_evidence("reactivation_decision", "docs/decisions/reactivate-rol.md"),),
    )
    assert woken.state is EmploymentState.DORMANT


def test_a_discontinuous_history_is_refused():
    step = dataclasses.replace  # readability
    record = advance(
        EmploymentRecord(employee_id="x"),
        EmploymentState.REJECTED,
        on=TODAY,
        by="y",
        reason="No.",
    )
    with pytest.raises(LifecycleViolation, match="ended at"):
        step(record, state=EmploymentState.ACTIVE)


def test_a_candidate_cannot_hold_authority(config):
    assert_authority(EmploymentState.CANDIDATE, 0, config.permissions)
    with pytest.raises(AuthorityViolation, match="may not hold autonomy level 1"):
        assert_authority(EmploymentState.CANDIDATE, 1, config.permissions)


def test_restricted_states_may_not_request_production_actions():
    for state in (
        EmploymentState.CANDIDATE,
        EmploymentState.SHADOW,
        EmploymentState.PROBATION,
    ):
        with pytest.raises(AuthorityViolation, match="production authority"):
            assert_may_not_write_production(state, ("approved_code_write",))
    assert_may_not_write_production(EmploymentState.ACTIVE, ("approved_code_write",))


# -- 11. performance evidence ----------------------------------------------


def an_observation(**overrides) -> PerformanceObservation:
    defaults = dict(
        employee_id="chief_architect",
        capability_id="software_architecture",
        task_ref="task/001",
        outcome=TaskOutcome.ACCEPTED,
        on=TODAY,
    )
    defaults.update(overrides)
    return PerformanceObservation(**defaults)


def test_performance_works_with_no_token_counts():
    summaries = summarise_observations(
        (
            an_observation(task_ref="task/001"),
            an_observation(task_ref="task/002", first_pass=False),
            an_observation(
                task_ref="task/003", outcome=TaskOutcome.REJECTED, note="Broke the merge apron."
            ),
        )
    )
    assert len(summaries) == 1
    entry = summaries[0]
    assert entry.attempted == 3
    assert entry.accepted == 2
    assert entry.first_pass_success_rate == 0.5
    assert entry.rejection_rate == pytest.approx(1 / 3)
    assert entry.usage_record_refs == ()


def test_performance_stays_capability_scoped():
    performance = employee_performance(
        "chief_architect",
        (
            an_observation(capability_id="software_architecture"),
            an_observation(
                capability_id="dependency_governance",
                outcome=TaskOutcome.REJECTED,
                note="Added a dependency without the security review.",
            ),
        ),
    )
    assert performance.capability_ids == ("dependency_governance", "software_architecture")
    assert performance.get("software_architecture").acceptance_rate == 1.0
    assert performance.get("dependency_governance").acceptance_rate == 0.0


def test_no_global_reputation_score_field_exists():
    """Section 13, enforced rather than described.

    Scans every dataclass in the package for a field whose name reads like an
    aggregate quality verdict. A single number for an employee erases exactly
    the information a staffing decision needs.
    """
    import company.workforce as package

    banned = ("score", "rating", "grade", "reputation", "overall")
    offenders = []
    for name in dir(package):
        obj = getattr(package, name)
        if not dataclasses.is_dataclass(obj) or not isinstance(obj, type):
            continue
        for field in dataclasses.fields(obj):
            if any(word in field.name.lower() for word in banned):
                offenders.append(f"{name}.{field.name}")
    assert offenders == []


def test_usage_records_are_linked_by_reference_not_copied():
    fields = {
        field.name for field in dataclasses.fields(PerformanceObservation)
    }
    assert "usage_record_ref" in fields
    assert "input_units" not in fields and "output_units" not in fields

    observations = (
        an_observation(task_ref="task/001", usage_record_ref="resource_usage/task-001/000001.json"),
    )
    entry = summarise_observations(observations)[0]
    record = ResourceUsageRecord(
        task_id="task/001",
        reasoning_class=ReasoningClass.B,
        outcome=Outcome.ACCEPTED,
    )
    summary = resource_summary(entry, lambda ref: record)
    assert summary is not None
    assert summary.passes_per_accepted == 1.0
    assert summary.units_per_accepted is None
    assert summary.unit is UsageUnit.UNKNOWN


def test_resource_summary_is_none_when_nothing_is_linked():
    entry = summarise_observations((an_observation(),))[0]
    assert resource_summary(entry, lambda ref: None) is None


# -- 12. role necessity ----------------------------------------------------


def test_role_necessity_never_archives_and_always_needs_a_human():
    registry_obj = a_registry(
        {
            "one": {"state": "active", "capabilities": ["alpha"], "manager": "ceo"},
            "two": {"state": "active", "capabilities": ["alpha"], "manager": "ceo"},
        }
    )
    review = review_role(
        "two",
        registry_obj,
        (),
        window_start=dt.date(2026, 7, 1),
        window_end=TODAY,
    )
    assert review.requires_human_decision is True
    assert review.recommendation is not Recommendation.ARCHIVE_ROLE
    assert NecessitySignal.DUPLICATE_CAPABILITY_COVERAGE.value in review.signals
    assert NecessitySignal.NO_TASKS_IN_WINDOW.value in review.signals


def test_a_sole_provider_is_protected_from_an_archive_recommendation():
    registry_obj = a_registry(
        {"only": {"state": "active", "capabilities": ["alpha"], "manager": "ceo"}}
    )
    review = review_role(
        "only", registry_obj, (), window_start=dt.date(2026, 7, 1), window_end=TODAY
    )
    assert review.protective_signals
    assert review.recommendation is Recommendation.NO_ACTION


def test_a_review_cannot_be_built_that_archives_a_sole_provider():
    from company.workforce.necessity import Direction, NecessityFinding, RoleNecessityReview

    with pytest.raises(WorkforceError, match="not a redundancy finding"):
        RoleNecessityReview(
            employee_id="only",
            window_start=dt.date(2026, 7, 1),
            window_end=TODAY,
            findings=(
                NecessityFinding(
                    signal=NecessitySignal.UNIQUE_CAPABILITY_COVERAGE,
                    direction=Direction.PROTECT,
                    detail="sole provider of alpha",
                ),
            ),
            recommendation=Recommendation.ARCHIVE_ROLE,
        )


def test_high_rejection_and_escalation_rates_are_reported_not_acted_on():
    registry_obj = a_registry(
        {
            "one": {"state": "active", "capabilities": ["alpha"], "manager": "ceo"},
            "two": {"state": "active", "capabilities": ["alpha"], "manager": "ceo"},
        }
    )
    observations = [
        PerformanceObservation(
            employee_id="two",
            capability_id="alpha",
            task_ref=f"task/{index}",
            outcome=TaskOutcome.REJECTED,
            on=TODAY,
            escalated=True,
            note="Wrong module boundary.",
        )
        for index in range(4)
    ]
    review = review_role(
        "two",
        registry_obj,
        summarise_observations(observations),
        window_start=dt.date(2026, 7, 1),
        window_end=TODAY,
    )
    assert NecessitySignal.HIGH_REJECTION_RATE.value in review.signals
    assert NecessitySignal.REPEATED_ESCALATION.value in review.signals
    assert review.recommendation is Recommendation.MERGE_ROLES
    proposal = review_to_proposal(
        review, proposal_id="prop-006", proposed_on=TODAY, merge_with=("one",)
    )
    assert proposal.approval is ApprovalState.PROPOSED
    assert proposal.subject_employee_ids == ("one", "two")


def test_an_unmeasured_resource_cost_produces_no_finding():
    registry_obj = a_registry(
        {"only": {"state": "active", "capabilities": ["alpha"], "manager": "ceo"}}
    )
    review = review_role(
        "only",
        registry_obj,
        (),
        window_start=dt.date(2026, 7, 1),
        window_end=TODAY,
        resource_cost_per_accepted=None,
    )
    assert NecessitySignal.HIGH_RESOURCE_COST.value not in review.signals


# -- 14. organizational debt -----------------------------------------------


def test_identical_capability_sets_are_reported_as_duplicated_roles():
    registry_obj = a_registry(
        {
            "one": {"state": "active", "capabilities": ["alpha"], "manager": "ceo"},
            "two": {"state": "active", "capabilities": ["alpha"], "manager": "ceo"},
        }
    )
    found = detect_debt(registry_obj, observed_on=TODAY)
    kinds = {record.kind for record in found}
    assert DebtKind.DUPLICATED_ROLE in kinds
    assert DebtKind.UNUSED_CAPABILITY in kinds
    assert all(record.status.value == "open" for record in found)


# -- 15. store -------------------------------------------------------------


def test_the_store_needs_an_explicit_root():
    with pytest.raises(WorkforceStoreError, match="explicit non-empty path"):
        WorkforceStore("   ")


def test_serialization_is_deterministic_and_round_trips(tmp_path):
    registry_obj = a_registry({})
    gap = a_gap(registry_obj, ("alpha",), frequency=one_off())
    store = WorkforceStore(tmp_path)
    first = store.put(gap).read_bytes()
    second = store.put(gap).read_bytes()
    assert first == second
    assert store.get("gap", "gap-001") == gap
    assert store.ids("gap") == ("gap-001",)
    assert json.loads(first.decode("utf-8"))["frequency"]["frequency"] == "one_off"


def test_observations_append_and_never_overwrite(tmp_path):
    store = WorkforceStore(tmp_path)
    first = store.append_observation(an_observation(task_ref="task/001"))
    second = store.append_observation(an_observation(task_ref="task/002"))
    assert first != second
    loaded = store.observations("chief_architect", "software_architecture")
    assert [item.task_ref for item in loaded] == ["task/001", "task/002"]


def test_an_unknown_record_kind_is_refused(tmp_path):
    store = WorkforceStore(tmp_path)
    with pytest.raises(WorkforceStoreError, match="unknown record kind"):
        store.get("employee", "x")
    with pytest.raises(WorkforceStoreError, match="not a storable workforce record"):
        store.put(an_observation())


def test_a_corrupt_record_names_its_file(tmp_path):
    store = WorkforceStore(tmp_path)
    path = tmp_path / "gaps" / "broken.json"
    path.parent.mkdir(parents=True)
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(WorkforceStoreError, match="does not decode"):
        store.get("gap", "broken")


# -- 16. integrity ---------------------------------------------------------


def test_the_shipped_organization_is_clean(registry, config):
    assert check_integrity(registry, permissions=config.permissions) == ()
    assert_integrity(registry, permissions=config.permissions)


def test_an_employee_referencing_an_unknown_capability_is_detected():
    registry_obj = a_registry(
        {"one": {"state": "active", "capabilities": ["nope"], "manager": "ceo"}}
    )
    issues = check_integrity(registry_obj)
    assert any("is not defined in the capability registry" in issue for issue in issues)


def test_a_role_with_an_invalid_manager_is_detected():
    registry_obj = a_registry(
        {"one": {"state": "active", "capabilities": ["alpha"], "manager": "ceo"}}
    )
    role = a_role(manager="nobody", required_capabilities=("alpha",))
    issues = check_integrity(registry_obj, role_specifications=(role,))
    assert any("is neither an employee" in issue for issue in issues)


def test_a_proposed_manager_cycle_is_detected():
    registry_obj = a_registry(
        {"one": {"state": "active", "capabilities": ["alpha"], "manager": "ceo"}}
    )
    left = a_role(role_id="left", manager="right", required_capabilities=("alpha",))
    right = a_role(role_id="right", manager="left", required_capabilities=("alpha",))
    issues = check_integrity(registry_obj, role_specifications=(left, right))
    assert any("proposed manager cycle detected" in issue for issue in issues)


def test_an_unknown_employee_in_an_evaluation_is_detected():
    registry_obj = a_registry(
        {"one": {"state": "active", "capabilities": ["alpha"], "manager": "ceo"}}
    )
    issues = check_integrity(registry_obj, evaluations=(an_evaluation(),))
    assert any("unknown employee" in issue for issue in issues)


def test_an_unknown_capability_in_a_shadow_assignment_is_detected():
    registry_obj = a_registry(
        {
            "audio_design_lead": {
                "state": "candidate",
                "capabilities": ["alpha"],
                "manager": "ceo",
            },
            "production_qc_lead": {
                "state": "active",
                "capabilities": ["alpha"],
                "manager": "ceo",
            },
        }
    )
    issues = check_integrity(registry_obj, shadow_assignments=(a_shadow(),))
    assert any("unknown capability 'qc'" in issue for issue in issues)


def test_a_core_capability_with_no_provider_is_an_integrity_failure():
    graph = CapabilityGraph(
        capabilities=(
            Capability(
                capability_id="alpha",
                name="Alpha",
                description="A core capability nobody has.",
                domain="engineering",
                criticality=Criticality.CORE,
            ),
        )
    )
    issues = check_integrity(CapabilityRegistry(graph, {"employees": {}}))
    assert any("is core and has no provider" in issue for issue in issues)


def test_an_invalid_lifecycle_jump_in_stored_history_is_detected():
    """A record that arrived from an older file, not through `advance`."""
    from company.workforce.employment import EmploymentTransition, history_violations

    record = EmploymentRecord(
        employee_id="x",
        state=EmploymentState.ACTIVE,
        history=(
            EmploymentTransition(
                from_state=EmploymentState.CANDIDATE,
                to_state=EmploymentState.ACTIVE,
                on=TODAY,
                by="someone",
                reason="Straight in.",
            ),
        ),
    )
    issues = history_violations(record)
    assert any("invalid lifecycle jump candidate -> active" in issue for issue in issues)
    assert any(
        "invalid lifecycle jump" in issue
        for issue in check_integrity(a_registry({}), employment_records=(record,))
    )


def test_a_role_violating_the_no_subagent_policy_is_detected():
    role = a_role()
    object.__setattr__(role, "no_subagents", False)
    issues = check_integrity(a_registry({}), role_specifications=(role,))
    assert any("constitution rule 2" in issue for issue in issues)


def test_a_shadow_with_a_write_scope_is_detected():
    assignment = a_shadow()
    object.__setattr__(assignment, "may_write", ("audio/**",))
    issues = check_integrity(a_registry({}), shadow_assignments=(assignment,))
    assert any("holds a write scope" in issue for issue in issues)


# -- 17 & 20. invariants preserved -----------------------------------------


def test_the_bootstrap_configuration_still_validates(config):
    validate_bootstrap(config)


def test_the_no_subagent_rule_is_untouched(config):
    assert config.org_registry["global_constraints"]["no_subagents"] is True
    assert config.org_registry["global_constraints"]["nested_agent_spawning"] is False
    assert config.permissions["bootstrap_defaults"]["no_subagents"] is True
    assert "change_no_subagents_policy" in config.permissions["ceo_reserved"]


def test_workforce_never_writes_a_company_contract_file():
    """No module here opens org_registry.yaml, permissions.yaml, or a schema for write."""
    reserved = ("org_registry", "permissions.yaml", "agent_contract.schema", "constitution")
    writers = ("write_text", "open(", "write_json", "dumps(")
    for path in sorted(PACKAGE_ROOT.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            rendered = ast.dump(node)
            if any(name in rendered for name in reserved) and any(
                writer.rstrip("(") in rendered for writer in writers
            ):
                pytest.fail(f"{path.name} appears to write a company contract file")


def test_workforce_imports_no_production_module():
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
            assert not (set(roots) & production), f"{path.name} imports production code"


def test_no_dependency_is_added():
    """Standard library, plus what the control plane already imports."""
    allowed_third_party = {"pytest"}
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
                assert name in stdlib | internal | allowed_third_party, (
                    f"{path.name} imports {name}, which is a new dependency"
                )
    requirements = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert sorted(requirements.split()) == sorted(
        "pymunk>=7.0 pygame>=2.6 pytest>=8.0 pybullet>=3.2.7 pillow>=11.0 numpy>=2.1".split()
    )


def test_the_worked_example_holds_end_to_end(tmp_path, registry, config):
    """One gap, one proposal, one role, one evaluation, one lifecycle walk.

    The integration case: every record the brief asks for, produced in order,
    stored, reloaded, and checked for integrity as a set.
    """
    report = assess_coverage(("mobile_readability", "qc"), registry)
    gap = gap_from_coverage(
        "gap-mobile-readability-001",
        report,
        trigger=a_trigger(),
        frequency=recurring(),
        urgency=Urgency.HIGH,
        business_impact="Three cuts shipped without a phone-size readability pass.",
        observed_on=TODAY,
        evidence=(an_evidence("document", "docs/sloped_race_v21_contrast.md"),),
    )
    proposal = propose_for_gap(
        gap,
        registry,
        proposal_id="prop-mobile-readability-001",
        proposed_on=TODAY,
        report=report,
        permissions=config.permissions,
        department="production",
    )
    role = a_role(required_capabilities=("mobile_readability", "qc"), gap_id=gap.gap_id)
    evaluation = passed_evaluation()
    employment = EmploymentRecord(
        employee_id=role.role_id, role_specification_id=role.role_id
    )

    store = WorkforceStore(tmp_path)
    for record in (gap, proposal, role, evaluation, employment):
        store.put(record)
    assert store.get("proposal", proposal.proposal_id) == proposal
    assert store.get("role", role.role_id).no_subagents is True

    issues = check_integrity(
        registry,
        permissions=config.permissions,
        role_specifications=(role,),
        evaluations=(evaluation,),
        employment_records=(employment,),
    )
    assert issues == ()

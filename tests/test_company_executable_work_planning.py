"""Executable work, not merely eligible work, and the discovery it unlocks.

The final end-to-end delegation pilot ended at NO_EXECUTABLE_WORK_CANDIDATE
having spent nothing, which was the right answer arrived at by the wrong route.
Deterministic eligibility left one candidate, planning committed to the
one-candidate rung, and normal intake then refused the work order that
candidate derives - `reserved-screening-negation-blindness` is a defect in
credential screening, its title contains the word `credential`, and
`screen_credentials()` fires on it. The defect blocked the authorization of its
own fix.

Bounded discovery existed for exactly that situation and could not be reached,
because the condition guarding it read `eligible == 0` rather than
`executable == 0`.

So: a candidate is EXECUTABLE when it passes deterministic eligibility, derives
a bounded work order, and normal intake authorizes that order. Planning counts
those. Nothing about eligibility or intake was weakened to make this work, and
the two candidates that could not pass before still cannot.

Sections
    1. viability, on its own
    2. the rungs, counted in executable candidates
    3. the two candidates that must stay refused
    4. discovery becomes reachable
    5. intake cannot be routed around
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from ai_platform.resource_classes import Risk
from company.delegation.candidates import (
    CandidateRegister,
    CandidateSource,
    CandidateStatus,
    WorkCandidate,
    load_seed_register,
)
from company.delegation.discovery import (
    DiscoveryEnvelope,
    EvidenceSurface,
    gate_advisory_proposals,
    run_discovery,
)
from company.delegation.objectives import Objective, ObjectiveLevel, PlanningEnvelope
from company.delegation.planning_record import PlanningOutcome
from company.delegation.planning_run import plan_objective
from company.delegation.viability import (
    INTAKE,
    ViabilityVerdict,
    assess_viability,
    executable_ids,
)
from company.delegation.errors import DelegationError
from company.finance.money import Money
from company.runtime.config import load_company_config
from knowledge.company_os.capsules import CapsuleIndex

DAY = dt.date(2026, 9, 20)
REPO_ROOT = Path(__file__).resolve().parents[1]
OBJECTIVE_ID = "obj-executable-work-test"

CREDENTIAL_CANDIDATE = "reserved-screening-negation-blindness"
TOOLS_CANDIDATE = "runner-blocked-attempt-repo-dir"


@pytest.fixture(scope="module")
def config():
    return load_company_config(None)


@pytest.fixture(scope="module")
def capsule_ids():
    return CapsuleIndex.load().ids()


def _envelope(risk_ceiling=Risk.MEDIUM):
    return PlanningEnvelope(
        objective_id=OBJECTIVE_ID,
        budget=Money("6.00", "USD"),
        budget_scope="engineering-operations",
        risk_ceiling=risk_ceiling,
        deadline=dt.date(2026, 12, 31),
        allowed_departments=("engineering",),
        success_metrics=("one useful improvement",),
    )


def _objective(envelope):
    return Objective(
        objective_id=OBJECTIVE_ID,
        title=(
            "Improve the reliability, maintainability, or operating efficiency of "
            "the Company OS by completing ONE useful engineering improvement."
        ),
        owner_seat="ceo",
        set_by="MGI",
        set_on=DAY,
        level=ObjectiveLevel.CEO_OBJECTIVE,
        envelope=envelope,
    )


def _check(config, envelope):
    def viability_check(candidate):
        return assess_viability(
            candidate,
            envelope,
            permissions=config.permissions,
            repo_root=REPO_ROOT,
            proposed_by_seat="engineering_manager",
            proposed_on=DAY,
            planning_decision_id="plan-" + OBJECTIVE_ID,
            requested_by="engineering_delivery_manager",
        )

    return viability_check


def _run(register, config, capsule_ids, **kw):
    envelope = kw.pop("envelope", None) or _envelope()
    return plan_objective(
        register,
        _objective(envelope),
        envelope,
        planning_run_id=kw.pop("planning_run_id", "run-executable-test"),
        executive_seat="cto",
        executive_employee="chief_architect",
        manager_seat="engineering_manager",
        manager_employee="engineering_delivery_manager",
        policy_version="delegation_policy_v1",
        policy_fingerprint="f",
        authority_source="CEO objective envelope",
        recorded_on=DAY,
        capsule_ids=capsule_ids,
        viability_check=_check(config, envelope),
        **kw,
    )


def _candidate(candidate_id, **kw):
    """A candidate whose derived work order intake authorizes."""
    base = dict(
        candidate_id=candidate_id,
        title="Narrow the retry backoff helper",
        description="The helper retries on a status it should not.",
        capsule_id="company-engineering-execution",
        department="engineering",
        source_type=CandidateSource.KNOWN_DEFECT,
        source_ref="docs/company_os_review_separation.md",
        problem_statement=(
            "The retry helper in company/engineering/intake.py retries on a "
            "status that is not transient, so a permanent refusal is retried."
        ),
        expected_value="Fewer wasted attempts on permanent refusals.",
        risk=Risk.LOW,
        created_at=DAY,
        evidence_refs=("docs/company_os_review_separation.md",),
        acceptance_criteria=(
            "The helper does not retry on a permanent refusal.",
            "The helper still retries on a transient one.",
            "tests/test_company_engineering_execution.py passes.",
        ),
        allowed_write_scope=(
            "company/engineering/intake.py",
            "tests/test_company_engineering_execution.py",
        ),
        estimated_resource_profile="consumer",
        goal_tags=("maintenance", "engineering"),
        status=CandidateStatus.OPEN,
    )
    base.update(kw)
    return WorkCandidate(**base)


# --- 1. viability, on its own ----------------------------------------------


def test_a_clean_candidate_is_executable(config):
    verdict = _check(config, _envelope())(_candidate("clean-retry-helper"))
    assert verdict.executable is True, verdict.reason
    assert verdict.intake_outcome == "authorized"
    assert verdict.blocked_at == ""


def test_the_credential_candidate_is_not_executable(config):
    """The candidate that ended the previous pilot, unchanged and still refused."""
    candidate = load_seed_register().candidate(CREDENTIAL_CANDIDATE)
    # It is COMPLETED/OPEN-agnostic here: viability asks a different question.
    verdict = _check(config, _envelope())(candidate)
    assert verdict.executable is False
    assert verdict.blocked_at == INTAKE
    assert verdict.intake_outcome == "decision_required"
    assert "credential" in verdict.reason


def test_a_refusal_must_carry_a_reason():
    with pytest.raises(DelegationError, match="must say why"):
        ViabilityVerdict(candidate_id="x", executable=False)


def test_an_executable_verdict_is_not_also_blocked():
    with pytest.raises(DelegationError, match="not blocked"):
        ViabilityVerdict(candidate_id="x", executable=True, blocked_at=INTAKE)


# --- 2. the rungs, counted in executable candidates -------------------------


def test_one_eligible_and_executable_selects_without_discovery(config, capsule_ids):
    register = CandidateRegister(candidates=(_candidate("clean-retry-helper"),))
    run = _run(register, config, capsule_ids)
    assert run.outcome is PlanningOutcome.SELECTED
    assert run.record.selected_candidate_id == "clean-retry-helper"
    assert run.record.viability_assessed is True
    assert run.record.executable_candidate_ids == ("clean-retry-helper",)
    assert run.record.model_used is False
    assert run.record.discovery_requested is False


def test_one_eligible_but_not_executable_does_not_select(config, capsule_ids):
    """The exact shape that ended the previous pilot."""
    candidate = load_seed_register().candidate(CREDENTIAL_CANDIDATE)
    register = CandidateRegister(candidates=(candidate,))
    run = _run(register, config, capsule_ids)
    assert run.outcome is PlanningOutcome.NO_ELIGIBLE_WORK_CANDIDATE
    assert run.record.selected_candidate_id == ""
    assert run.record.eligible_candidate_ids == (CREDENTIAL_CANDIDATE,)
    assert run.record.executable_candidate_ids == ()
    assert run.record.not_executable
    assert "credential" in run.record.not_executable[0]
    # The reason must not claim nothing was eligible, because something was.
    assert "passed eligibility and none can be worked on" in (
        run.record.decision_reason
    )


def test_several_eligible_with_one_executable_needs_no_model(config, capsule_ids):
    blocked = load_seed_register().candidate(CREDENTIAL_CANDIDATE)
    register = CandidateRegister(
        candidates=(blocked, _candidate("clean-retry-helper"))
    )
    run = _run(register, config, capsule_ids)
    assert run.outcome is PlanningOutcome.SELECTED
    assert run.record.selected_candidate_id == "clean-retry-helper"
    assert len(run.record.eligible_candidate_ids) == 2
    assert run.record.executable_candidate_ids == ("clean-retry-helper",)
    # Two eligible would have asked an executive. One executable is arithmetic.
    assert run.record.model_used is False


def test_several_eligible_and_none_executable_stops(config, capsule_ids):
    blocked = load_seed_register().candidate(CREDENTIAL_CANDIDATE)
    second = _candidate(
        "another-credential-shaped-one",
        title="Rotate the stored credential for the analytics reader",
    )
    register = CandidateRegister(candidates=(blocked, second))
    run = _run(register, config, capsule_ids)
    assert run.outcome is PlanningOutcome.NO_ELIGIBLE_WORK_CANDIDATE
    assert len(run.record.eligible_candidate_ids) == 2
    assert run.record.executable_candidate_ids == ()
    assert len(run.record.not_executable) == 2


def test_two_executable_candidates_still_ask_the_executive(config, capsule_ids):
    """Viability narrows the set; it does not decide between what survives."""
    register = CandidateRegister(
        candidates=(
            _candidate("clean-retry-helper"),
            _candidate("clean-retry-helper-two", title="Narrow the backoff ceiling"),
        )
    )
    run = _run(register, config, capsule_ids)
    assert run.outcome is PlanningOutcome.ESCALATED
    assert len(run.record.executable_candidate_ids) == 2
    assert run.record.model_used is False


# --- 3. the two candidates that must stay refused ---------------------------


def test_the_credential_candidate_is_still_refused_by_intake(config):
    """Not reworded, not excepted, not screened more loosely."""
    candidate = load_seed_register().candidate(CREDENTIAL_CANDIDATE)
    verdict = _check(config, _envelope())(candidate)
    assert verdict.executable is False
    assert verdict.intake_outcome == "decision_required"


def test_the_tools_candidate_still_fails_capsule_ownership(config, capsule_ids):
    """`tools/` was not given a capsule to make this eligible."""
    from company.delegation.planning import eligible_candidates

    register = load_seed_register()
    envelope = _envelope()
    results = eligible_candidates(
        register, _objective(envelope), envelope, capsule_ids=capsule_ids
    )
    tools = next(r for r in results if r.candidate_id == TOOLS_CANDIDATE)
    assert tools.eligible is False
    assert any(check.value == "capsule_owned" for check in tools.failed)


# --- 4. discovery becomes reachable -----------------------------------------


def _discovery_envelope(**kw):
    base = dict(
        envelope_id="disc-executable-test",
        objective_id=OBJECTIVE_ID,
        department="engineering",
        allowed_capsules=("company-knowledge-capsules",),
        allowed_surfaces=(EvidenceSurface.VALIDATION_REPORT.value,),
        risk_ceiling=Risk.MEDIUM,
        budget=Money("6.00", "USD"),
        expires_on=dt.date(2026, 12, 31),
        authorized_by="chief_architect",
        authority_source="discover_work grant under the objective envelope",
        max_candidates=3,
    )
    base.update(kw)
    return DiscoveryEnvelope(**base)


def _gate_report(check_id="architecture.subsystem_ownership_bounded", **kw):
    check = {
        "check_id": check_id,
        "status": "fail",
        "detail": "7 module(s) no capsule claims",
        "evidence": ["company/workforce/__init__.py", "company/workforce/common.py"],
    }
    check.update(kw)
    return {"required_check_ids": [], "sections": [{"checks": [check]}]}


def test_the_gate_reader_proposes_from_a_failing_advisory():
    proposals = gate_advisory_proposals(
        _discovery_envelope(),
        _gate_report(),
        today=DAY,
        report_ref="docs/company_os_review_separation.md",
    )
    assert len(proposals) == 1
    candidate, surface = proposals[0]
    assert surface is EvidenceSurface.VALIDATION_REPORT
    assert candidate.risk is Risk.LOW
    assert candidate.allowed_write_scope == ("knowledge/company_os/capsules/seeds",)


def test_the_gate_reader_refuses_to_route_a_required_check():
    """A failing required check is a blocker, not a backlog item."""
    report = _gate_report()
    report["required_check_ids"] = ["architecture.subsystem_ownership_bounded"]
    assert gate_advisory_proposals(
        _discovery_envelope(), report, today=DAY, report_ref="docs/x.md"
    ) == ()


def test_the_gate_reader_proposes_nothing_without_evidence():
    assert gate_advisory_proposals(
        _discovery_envelope(),
        _gate_report(evidence=[]),
        today=DAY,
        report_ref="docs/x.md",
    ) == ()


def test_the_gate_reader_ignores_a_finding_it_cannot_scope():
    assert gate_advisory_proposals(
        _discovery_envelope(),
        _gate_report(check_id="health.something_unmapped"),
        today=DAY,
        report_ref="docs/x.md",
    ) == ()


def test_the_gate_reader_respects_the_surface_it_was_not_given():
    envelope = _discovery_envelope(
        allowed_surfaces=(EvidenceSurface.CAPSULE_METADATA.value,)
    )
    assert gate_advisory_proposals(
        envelope, _gate_report(), today=DAY, report_ref="docs/x.md"
    ) == ()


def test_discovery_that_finds_nothing_still_stops(config, capsule_ids):
    candidate = load_seed_register().candidate(CREDENTIAL_CANDIDATE)
    register = CandidateRegister(candidates=(candidate,))
    envelope = _discovery_envelope()
    empty = run_discovery(
        (), envelope, register=register, capsule_paths={}, today=DAY, repo_root=REPO_ROOT
    )
    run = _run(
        register,
        config,
        capsule_ids,
        discovery=empty,
        discovery_envelope=envelope,
    )
    assert run.outcome is PlanningOutcome.NO_ELIGIBLE_WORK_CANDIDATE
    assert run.record.discovery_requested is True
    assert run.record.discovered_candidate_ids == ()


# --- 5. intake cannot be routed around --------------------------------------


def test_a_discovered_candidate_intake_refuses_stays_unusable(config, capsule_ids):
    """Discovery does not get to hand a developer work intake would refuse."""
    discovered = _candidate(
        "discovered-credential-shaped",
        title="Rotate the stored credential for the analytics reader",
    )
    register = CandidateRegister(candidates=(discovered,))
    run = _run(register, config, capsule_ids)
    assert run.outcome is PlanningOutcome.NO_ELIGIBLE_WORK_CANDIDATE
    assert run.record.executable_candidate_ids == ()
    assert "credential" in " ".join(run.record.not_executable)


def test_a_run_cannot_select_a_candidate_viability_refused():
    """The record itself refuses the combination, not only the code path."""
    from company.delegation.planning_run import PlanningRunRecord

    with pytest.raises(DelegationError, match="execution viability"):
        PlanningRunRecord(
            planning_run_id="run-bad",
            objective_id=OBJECTIVE_ID,
            objective_intent_digest="d",
            recorded_on=DAY,
            department="engineering",
            executive_seat="cto",
            executive_employee="chief_architect",
            manager_seat="engineering_manager",
            manager_employee="engineering_delivery_manager",
            outcome=PlanningOutcome.SELECTED,
            decision_reason="r",
            authority_source="a",
            policy_version="v",
            policy_fingerprint="f",
            eligible_candidate_ids=("a", "b"),
            viability_assessed=True,
            executable_candidate_ids=("b",),
            selected_candidate_id="a",
        )


def test_viability_results_require_the_assessed_flag():
    from company.delegation.planning_run import PlanningRunRecord

    with pytest.raises(DelegationError, match="viability_assessed is false"):
        PlanningRunRecord(
            planning_run_id="run-bad-2",
            objective_id=OBJECTIVE_ID,
            objective_intent_digest="d",
            recorded_on=DAY,
            department="engineering",
            executive_seat="cto",
            executive_employee="chief_architect",
            manager_seat="engineering_manager",
            manager_employee="engineering_delivery_manager",
            outcome=PlanningOutcome.NO_ELIGIBLE_WORK_CANDIDATE,
            decision_reason="r",
            authority_source="a",
            policy_version="v",
            policy_fingerprint="f",
            executable_candidate_ids=("a",),
        )


def test_viability_cannot_widen_eligibility():
    from company.delegation.planning_run import PlanningRunRecord

    with pytest.raises(DelegationError, match="cannot add to it"):
        PlanningRunRecord(
            planning_run_id="run-bad-3",
            objective_id=OBJECTIVE_ID,
            objective_intent_digest="d",
            recorded_on=DAY,
            department="engineering",
            executive_seat="cto",
            executive_employee="chief_architect",
            manager_seat="engineering_manager",
            manager_employee="engineering_delivery_manager",
            outcome=PlanningOutcome.NO_ELIGIBLE_WORK_CANDIDATE,
            decision_reason="r",
            authority_source="a",
            policy_version="v",
            policy_fingerprint="f",
            eligible_candidate_ids=("a",),
            viability_assessed=True,
            executable_candidate_ids=("z",),
        )


def test_a_run_without_a_viability_check_says_so(config, capsule_ids):
    """The older behaviour is still reachable and is labelled, not disguised."""
    register = CandidateRegister(candidates=(_candidate("clean-retry-helper"),))
    envelope = _envelope()
    run = plan_objective(
        register,
        _objective(envelope),
        envelope,
        planning_run_id="run-unassessed",
        executive_seat="cto",
        executive_employee="chief_architect",
        manager_seat="engineering_manager",
        manager_employee="engineering_delivery_manager",
        policy_version="delegation_policy_v1",
        policy_fingerprint="f",
        authority_source="CEO objective envelope",
        recorded_on=DAY,
        capsule_ids=capsule_ids,
    )
    assert run.record.viability_assessed is False
    assert run.record.executable_candidate_ids == ()


def test_executable_ids_reads_only_executable_verdicts():
    verdicts = (
        ViabilityVerdict(candidate_id="a", executable=True),
        ViabilityVerdict(
            candidate_id="b", executable=False, blocked_at=INTAKE, reason="no"
        ),
    )
    assert executable_ids(verdicts) == ("a",)

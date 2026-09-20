"""Executive planning, prioritization and bounded work discovery.

Sections
    1. the discovery envelope, and what it refuses
    2. evidence surfaces: the closed set, and the one that is absent
    3. proposal validation, one test per gate
    4. discovery runs, ceilings and in-run duplicates
    5. the bounded reader
    6. the planning brief, and what the planner is never given
    7. the executive choice contract and its seven refusals
    8. the deterministic-first ordering
    9. the audit record and its telemetry
   10. authority: who may select, who may discover, who may do neither
   11. the two replays
   12. what this branch still cannot do
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from ai_platform.resource_classes import ReasoningClass, Risk
from company.delegation.actions import ActionType
from company.delegation.candidates import (
    CandidateRegister,
    CandidateStatus,
    WorkCandidate,
    load_seed_register,
)
from company.delegation.discovery import (
    ACTIVE_STATUSES,
    MAX_DISCOVERY_CANDIDATES,
    PROPOSAL_CHECKS,
    SURFACE_SOURCES,
    DiscoveryEnvelope,
    EvidenceSurface,
    ProposalCheck,
    capsule_revalidation_proposals,
    parse_surface,
    run_discovery,
    validate_proposal,
)
from company.delegation.errors import AuthorityViolation, DelegationError
from company.delegation.executive import (
    EXECUTIVE_CHOICE_CONTRACT,
    MAX_BRIEF_CANDIDATES,
    MAX_PLANNING_SESSIONS,
    PLANNING_REASONING_CLASS,
    Confidence,
    ExecutiveChoice,
    ExecutiveDecision,
    PlannerOutputError,
    PlanningSessionCost,
    assert_choice_within,
    parse_choice,
    planning_brief,
    should_ask_executive,
)
from company.delegation.objectives import Objective, ObjectiveLevel, PlanningEnvelope
from company.delegation.org import SeatKind
from company.delegation.planning_record import PlanningOutcome
from company.delegation.planning_run import (
    PlanningRunRecord,
    ceo_planning_report,
    plan_objective,
)
from company.delegation.policy import load_delegation_policy
from company.finance.money import Money
from company.runtime.config import load_company_config
from knowledge.company_os.capsules import CapsuleIndex

DAY = dt.date(2026, 9, 20)
REPO_ROOT = Path(__file__).resolve().parents[1]
OWNED = ("company-engineering-execution", "company-executive-delegation", "ai-platform")


def _usd(amount: str) -> Money:
    return Money.from_dict({"amount": amount, "currency": "USD"})


@pytest.fixture(scope="module")
def policy():
    config = load_company_config(None)
    return load_delegation_policy(
        org_registry=config.org_registry, permissions=config.permissions
    )


@pytest.fixture(scope="module")
def index():
    return CapsuleIndex.load()


@pytest.fixture(scope="module")
def capsule_paths(index):
    return {cid: index.get(cid).owns_paths for cid in index.ids()}


def _envelope(objective_id="obj-demo", *, risk_ceiling="low", budget="6.00",
              departments=("engineering",), forbidden=()):
    return PlanningEnvelope(
        objective_id=objective_id,
        budget=_usd(budget),
        budget_scope="engineering-operations",
        risk_ceiling=risk_ceiling,
        allowed_departments=departments,
        forbidden_actions=forbidden,
        success_metrics=("fewer false escalations",),
    )


def _objective(objective_id="obj-demo", *, title="Reduce false escalations in intake.",
               envelope=None):
    return Objective(
        objective_id=objective_id,
        level=ObjectiveLevel.CEO_OBJECTIVE,
        title=title,
        owner_seat="ceo",
        set_by="MGI",
        set_on=DAY,
        department="engineering",
        envelope=envelope if envelope is not None else _envelope(objective_id),
    )


def _discovery_envelope(**overrides):
    base = dict(
        envelope_id="disc-demo",
        objective_id="obj-demo",
        department="engineering",
        allowed_capsules=("company-engineering-execution",),
        allowed_surfaces=(EvidenceSurface.CAPSULE_METADATA,),
        risk_ceiling="low",
        budget=_usd("1.00"),
        expires_on=dt.date(2026, 9, 27),
        authorized_by="chief_architect",
        authority_source="cto discover_work grant under the objective envelope",
        max_candidates=3,
    )
    base.update(overrides)
    return DiscoveryEnvelope(**base)


def _candidate(**overrides):
    base = dict(
        candidate_id="cand-demo",
        title="Teach the parser to accept a trailing comma",
        description="A small, bounded parser change.",
        capsule_id="company-engineering-execution",
        department="engineering",
        source_type="maintenance_gap",
        source_ref="knowledge/company_os/capsules/seeds/company-engineering-execution.json",
        problem_statement=(
            "parse_action() in company/delegation/actions.py rejects a trailing "
            "comma in the action list."
        ),
        expected_value="One fewer malformed-input refusal on valid input.",
        risk="low",
        created_at=DAY,
        evidence_refs=(
            "knowledge/company_os/capsules/seeds/company-engineering-execution.json",
        ),
        acceptance_criteria=(
            "parse_action() accepts a trailing comma and still refuses an unknown "
            "action name.",
        ),
        allowed_write_scope=("company/engineering",),
    )
    base.update(overrides)
    return WorkCandidate(**base)


# --- 1. the discovery envelope ---------------------------------------------


def test_a_discovery_envelope_carries_every_bound_the_objective_named():
    envelope = _discovery_envelope()
    assert envelope.allowed_capsules
    assert envelope.allowed_surfaces
    assert envelope.expires_on
    assert envelope.authorized_by
    assert envelope.authority_source
    assert envelope.max_candidates == 3
    assert envelope.fingerprint()


def test_an_envelope_allowing_no_capsule_is_refused():
    """An empty allow-list is not a small scope; it is an unstated one."""
    with pytest.raises(DelegationError, match="authorizes discovery over nothing"):
        _discovery_envelope(allowed_capsules=())


def test_an_envelope_allowing_no_surface_is_refused():
    with pytest.raises(DelegationError, match="repository exploration"):
        _discovery_envelope(allowed_surfaces=())


def test_an_envelope_may_not_exceed_the_hard_candidate_ceiling():
    with pytest.raises(DelegationError, match="stopped choosing and started listing"):
        _discovery_envelope(max_candidates=MAX_DISCOVERY_CANDIDATES + 1)
    with pytest.raises(DelegationError):
        _discovery_envelope(max_candidates=0)


def test_an_envelope_requires_an_expiry_and_knows_when_it_passed():
    envelope = _discovery_envelope()
    assert envelope.expired_on(dt.date(2026, 9, 27)) is False
    assert envelope.expired_on(dt.date(2026, 9, 28)) is True


def test_an_envelope_signed_by_nobody_is_refused():
    with pytest.raises(DelegationError):
        _discovery_envelope(authorized_by="automatic")


# --- 2. evidence surfaces --------------------------------------------------


def test_there_is_no_surface_for_the_repository_at_large():
    """The absence is the point, so it is asserted rather than assumed."""
    names = {item.value for item in EvidenceSurface}
    for forbidden in (
        "repository",
        "repository_prose",
        "source_code",
        "todo_comments",
        "whole_repo",
        "codebase",
    ):
        assert forbidden not in names
    with pytest.raises(DelegationError, match="not a surface discovery may read"):
        parse_surface("repository_prose")


def test_every_surface_declares_which_provenance_it_can_produce():
    for surface in EvidenceSurface:
        assert SURFACE_SOURCES.get(surface), surface


# --- 3. proposal validation ------------------------------------------------


def _validate(candidate, envelope=None, *, register=None, surface=EvidenceSurface.CAPSULE_METADATA,
              today=DAY, reserved=(), paths=None, repo_root=REPO_ROOT):
    return validate_proposal(
        candidate,
        envelope or _discovery_envelope(),
        surface=surface,
        register=register if register is not None else CandidateRegister(()),
        capsule_paths=paths if paths is not None else {
            "company-engineering-execution": ("company/engineering",)
        },
        today=today,
        reserved_actions=reserved,
        repo_root=repo_root,
    )


def test_a_clean_proposal_passes_all_thirteen_gates():
    verdict = _validate(_candidate())
    assert verdict.accepted is True
    assert set(verdict.passed) == set(PROPOSAL_CHECKS)


def test_an_expired_envelope_rejects_every_proposal():
    verdict = _validate(_candidate(), today=dt.date(2026, 10, 1))
    assert ProposalCheck.ENVELOPE_LIVE in verdict.failed
    assert "ran out" in " ".join(verdict.reasons)


def test_evidence_that_does_not_exist_on_disk_is_rejected():
    verdict = _validate(
        _candidate(evidence_refs=("docs/a_file_that_does_not_exist.md",))
    )
    assert ProposalCheck.EVIDENCE_EXISTS in verdict.failed


def test_a_surface_the_envelope_did_not_allow_is_rejected():
    verdict = _validate(_candidate(), surface=EvidenceSurface.REVIEWER_ADVISORY)
    assert ProposalCheck.SURFACE_ALLOWED in verdict.failed


def test_a_provenance_the_surface_cannot_produce_is_rejected():
    """capsule_metadata cannot yield a reviewer advisory, whatever it claims."""
    verdict = _validate(_candidate(source_type="reviewer_advisory"))
    assert ProposalCheck.SURFACE_ALLOWED in verdict.failed


def test_a_capsule_outside_the_envelope_is_rejected():
    verdict = _validate(_candidate(capsule_id="ai-platform"))
    assert ProposalCheck.CAPSULE_RESOLVES in verdict.failed


def test_a_department_mismatch_is_rejected():
    verdict = _validate(_candidate(department="ai_platform"))
    assert ProposalCheck.DEPARTMENT_MATCHES in verdict.failed


def test_a_write_scope_outside_the_owning_capsule_is_rejected():
    verdict = _validate(_candidate(allowed_write_scope=("company/permissions.yaml",)))
    assert ProposalCheck.WRITE_SCOPE_BOUNDED in verdict.failed


def test_an_empty_write_scope_is_rejected():
    verdict = _validate(_candidate(allowed_write_scope=()))
    assert ProposalCheck.WRITE_SCOPE_BOUNDED in verdict.failed


def test_risk_above_the_discovery_ceiling_is_rejected():
    verdict = _validate(_candidate(risk="high"))
    assert ProposalCheck.RISK_CLASSIFIED in verdict.failed


def test_a_reserved_action_is_rejected():
    verdict = _validate(
        _candidate(required_actions=(ActionType.AMEND_CONSTITUTION,)),
        reserved=(ActionType.AMEND_CONSTITUTION,),
    )
    assert ProposalCheck.ACTIONS_PERMITTED in verdict.failed


def test_a_forbidden_action_is_rejected():
    verdict = _validate(
        _candidate(required_actions=(ActionType.APPROVE_DEPLOYMENT,)),
        envelope=_discovery_envelope(forbidden_actions=(ActionType.APPROVE_DEPLOYMENT,)),
    )
    assert ProposalCheck.ACTIONS_PERMITTED in verdict.failed


def test_a_dependency_the_register_does_not_hold_is_rejected():
    verdict = _validate(_candidate(dependencies=("cand-ghost",)))
    assert ProposalCheck.DEPENDENCIES_REPRESENTED in verdict.failed


def test_a_proposal_duplicating_active_work_is_rejected():
    existing = _candidate(candidate_id="cand-existing")
    verdict = _validate(
        _candidate(candidate_id="cand-new"),
        register=CandidateRegister((existing,)),
    )
    assert ProposalCheck.NOT_DUPLICATE in verdict.failed
    assert "cand-existing" in " ".join(verdict.reasons)


def test_a_completed_candidate_does_not_block_a_new_proposal():
    """The world moved on. DEFERRED means not now, not never, so it also frees."""
    done = _candidate(candidate_id="cand-done", status=CandidateStatus.COMPLETED)
    assert _validate(
        _candidate(candidate_id="cand-new"), register=CandidateRegister((done,))
    ).accepted
    assert CandidateStatus.COMPLETED not in ACTIVE_STATUSES
    assert CandidateStatus.DEFERRED not in ACTIVE_STATUSES
    assert CandidateStatus.OPEN in ACTIVE_STATUSES


def test_a_proposal_reusing_an_existing_id_is_rejected():
    existing = _candidate(allowed_write_scope=("company/runtime",))
    verdict = _validate(_candidate(), register=CandidateRegister((existing,)))
    assert ProposalCheck.NOT_DUPLICATE in verdict.failed


# --- 4. discovery runs -----------------------------------------------------


def test_a_run_that_exceeds_its_own_ceiling_is_refused_whole(capsule_paths):
    envelope = _discovery_envelope(max_candidates=1)
    proposals = [
        (_candidate(candidate_id="cand-a"), EvidenceSurface.CAPSULE_METADATA),
        (_candidate(candidate_id="cand-b"), EvidenceSurface.CAPSULE_METADATA),
    ]
    with pytest.raises(AuthorityViolation, match="whole run is refused"):
        run_discovery(
            proposals,
            envelope,
            register=CandidateRegister(()),
            capsule_paths=capsule_paths,
            today=DAY,
            repo_root=REPO_ROOT,
        )


def test_two_proposals_in_one_run_cannot_both_claim_the_same_work(capsule_paths):
    proposals = [
        (_candidate(candidate_id="cand-a"), EvidenceSurface.CAPSULE_METADATA),
        (_candidate(candidate_id="cand-b"), EvidenceSurface.CAPSULE_METADATA),
    ]
    result = run_discovery(
        proposals,
        _discovery_envelope(),
        register=CandidateRegister(()),
        capsule_paths={"company-engineering-execution": ("company/engineering",)},
        today=DAY,
        repo_root=REPO_ROOT,
    )
    assert result.accepted_ids() == ("cand-a",)
    assert result.rejected_ids() == ("cand-b",)


def test_a_run_reports_what_it_read_and_what_it_refused():
    result = run_discovery(
        [(_candidate(risk="high"), EvidenceSurface.CAPSULE_METADATA)],
        _discovery_envelope(),
        register=CandidateRegister(()),
        capsule_paths={"company-engineering-execution": ("company/engineering",)},
        today=DAY,
        repo_root=REPO_ROOT,
    )
    assert result.found_anything is False
    assert result.surfaces_read == (EvidenceSurface.CAPSULE_METADATA,)
    assert result.rejected_ids() == ("cand-demo",)


# --- 5. the bounded reader -------------------------------------------------


def test_the_reader_proposes_nothing_when_no_allowed_capsule_is_stale(index):
    assert capsule_revalidation_proposals(_discovery_envelope(), index, today=DAY) == ()


def test_the_reader_proposes_a_revalidation_once_a_capsule_goes_stale(index):
    envelope = _discovery_envelope(
        allowed_capsules=("company-engineering-execution", "company-executive-delegation")
    )
    proposals = capsule_revalidation_proposals(envelope, index, today=dt.date(2028, 1, 1))
    assert proposals
    candidate, surface = proposals[0]
    assert surface is EvidenceSurface.CAPSULE_METADATA
    assert candidate.risk is Risk.LOW
    assert candidate.candidate_id.startswith("revalidate-")
    assert candidate.evidence_refs
    assert candidate.falsifiable_criteria()


def test_the_reader_reads_nothing_when_its_surface_is_not_allowed(index):
    envelope = _discovery_envelope(allowed_surfaces=(EvidenceSurface.REVIEWER_ADVISORY,))
    assert capsule_revalidation_proposals(envelope, index, today=dt.date(2028, 1, 1)) == ()


def test_the_reader_respects_the_candidate_ceiling(index):
    envelope = _discovery_envelope(
        allowed_capsules=("company-engineering-execution", "company-executive-delegation"),
        max_candidates=1,
    )
    assert len(capsule_revalidation_proposals(envelope, index, today=dt.date(2028, 1, 1))) == 1


# --- 6. the planning brief -------------------------------------------------


def test_the_brief_carries_summaries_and_never_a_file():
    objective, envelope = _objective(), _envelope()
    brief = planning_brief(objective, envelope, [_candidate()])
    payload = brief.to_dict()
    assert payload["objective_title"] == objective.title
    assert payload["candidates"][0]["candidate_id"] == "cand-demo"
    assert brief.within_budget()
    # Nothing in the brief is a body of code, only pointers a human may follow.
    text = brief.to_json()
    assert "def " not in text
    assert "import " not in text
    for key in ("repo_root", "file_contents", "source", "diff"):
        assert f'"{key}":' not in text or key == "source"


def test_a_brief_with_no_candidates_is_refused():
    with pytest.raises(DelegationError, match="nothing to decide"):
        planning_brief(_objective(), _envelope(), [])


def test_a_brief_may_not_exceed_the_candidate_ceiling():
    many = [_candidate(candidate_id=f"cand-{n:02d}") for n in range(MAX_BRIEF_CANDIDATES + 1)]
    with pytest.raises(DelegationError, match="at most"):
        planning_brief(_objective(), _envelope(), many)


# --- 7. the choice contract and its refusals -------------------------------


def _choice(**overrides):
    base = dict(
        decision="select",
        selected_candidate_id="cand-demo",
        reason="it is the smaller change and unblocks the other",
        objective_alignment="reduces false escalations directly",
        expected_value_reasoning="one fewer wrong escalation per routine request",
        risk_reasoning="two functions, no downstream dependency",
        resource_reasoning="consumer profile, inside the envelope",
        confidence="high",
    )
    base.update(overrides)
    return ExecutiveChoice(**base)


def test_the_contract_states_its_inputs_outputs_and_refusals():
    joined = " ".join(EXECUTIVE_CHOICE_CONTRACT)
    for phrase in ("input:", "output:", "refusal:", "authority: none", "budget:"):
        assert phrase in joined


def test_a_well_formed_answer_parses():
    raw = json.dumps(_choice().to_dict())
    choice = parse_choice(raw)
    assert choice.decision is ExecutiveDecision.SELECT
    assert choice.confidence is Confidence.HIGH


def test_a_fenced_answer_is_read_rather_than_refused():
    """Unwrapping a code fence is reading. Everything below is repairing."""
    raw = "```json\n" + json.dumps(_choice().to_dict()) + "\n```"
    assert parse_choice(raw).selected_candidate_id == "cand-demo"


def test_malformed_output_is_a_refusal_and_not_a_retry():
    for raw in ("not json at all", "", "{", "[1, 2, 3]", '{"decision": "maybe"}'):
        with pytest.raises(PlannerOutputError):
            parse_choice(raw)


def test_a_select_naming_no_candidate_is_refused():
    with pytest.raises(DelegationError, match="not a selection"):
        _choice(selected_candidate_id="")


def test_a_non_select_naming_a_candidate_is_refused():
    with pytest.raises(DelegationError, match="Only a selection selects"):
        _choice(decision="defer")


def test_the_planner_may_not_choose_a_candidate_it_was_not_shown():
    brief = planning_brief(_objective(), _envelope(), [_candidate()])
    with pytest.raises(AuthorityViolation, match="not among the eligible candidates"):
        assert_choice_within(
            _choice(selected_candidate_id="cand-invented"),
            brief,
            objective=_objective(),
            envelope=_envelope(),
        )


def test_the_planner_may_not_answer_about_a_different_objective():
    brief = planning_brief(_objective("obj-one"), _envelope("obj-one"), [_candidate()])
    with pytest.raises(AuthorityViolation, match="the brief was written for"):
        assert_choice_within(
            _choice(),
            brief,
            objective=_objective("obj-two"),
            envelope=_envelope("obj-two"),
        )


def test_the_planner_may_not_widen_the_risk_ceiling():
    brief = planning_brief(_objective(), _envelope(), [_candidate()])
    with pytest.raises(AuthorityViolation, match="may not widen the ceiling"):
        assert_choice_within(
            _choice(),
            brief,
            objective=_objective(),
            envelope=_envelope(risk_ceiling="low"),
            claimed_risk="high",
        )


def test_the_planner_may_not_widen_the_budget():
    brief = planning_brief(_objective(), _envelope(), [_candidate()])
    with pytest.raises(AuthorityViolation, match="against an envelope budget"):
        assert_choice_within(
            _choice(),
            brief,
            objective=_objective(),
            envelope=_envelope(budget="6.00"),
            claimed_spend=_usd("99.00"),
        )


def test_the_planner_may_not_claim_a_reserved_action():
    brief = planning_brief(_objective(), _envelope(), [_candidate()])
    with pytest.raises(AuthorityViolation, match="Authority is granted, never"):
        assert_choice_within(
            _choice(),
            brief,
            objective=_objective(),
            envelope=_envelope(),
            claimed_actions=(ActionType.AMEND_CONSTITUTION,),
            reserved_actions=(ActionType.AMEND_CONSTITUTION,),
        )


def test_the_planner_may_not_request_discovery_that_was_not_offered():
    brief = planning_brief(_objective(), _envelope(), [_candidate()], discovery_available=False)
    with pytest.raises(AuthorityViolation, match="not requested into existence"):
        assert_choice_within(
            _choice(decision="discover", selected_candidate_id=""),
            brief,
            objective=_objective(),
            envelope=_envelope(),
        )


# --- 8. deterministic first ------------------------------------------------


def test_a_model_is_asked_only_when_there_is_a_real_comparison():
    assert should_ask_executive(0) is False
    assert should_ask_executive(1) is False
    assert should_ask_executive(2) is True
    assert should_ask_executive(5) is True


def test_one_eligible_candidate_is_selected_without_any_model(index):
    register = CandidateRegister((_candidate(),))

    def explode(brief, instructions):  # pragma: no cover - must never run
        raise AssertionError("a model was called to confirm the only possible answer")

    run = plan_objective(
        register,
        _objective(),
        _envelope(),
        planning_run_id="run-one",
        executive_seat="cto",
        executive_employee="chief_architect",
        manager_seat="engineering_manager",
        manager_employee="engineering_delivery_manager",
        policy_version="v1",
        policy_fingerprint="f",
        authority_source="objective envelope",
        recorded_on=DAY,
        capsule_ids=OWNED,
        planner=explode,
    )
    assert run.outcome is PlanningOutcome.SELECTED
    assert run.record.model_used is False
    assert run.record.session is None
    assert run.record.planning_cost is None
    assert "arithmetic" in run.record.selection_reason


def test_zero_eligible_candidates_needs_no_model_either():
    run = plan_objective(
        CandidateRegister((_candidate(risk="critical"),)),
        _objective(),
        _envelope(),
        planning_run_id="run-zero",
        executive_seat="cto",
        executive_employee="chief_architect",
        manager_seat="engineering_manager",
        manager_employee="engineering_delivery_manager",
        policy_version="v1",
        policy_fingerprint="f",
        authority_source="objective envelope",
        recorded_on=DAY,
        capsule_ids=OWNED,
    )
    assert run.outcome is PlanningOutcome.NO_ELIGIBLE_WORK_CANDIDATE
    assert run.record.model_used is False
    assert run.record.selected_candidate_id == ""


def _two_eligible():
    return CandidateRegister(
        (
            _candidate(candidate_id="cand-a", allowed_write_scope=("company/engineering",)),
            _candidate(
                candidate_id="cand-b",
                allowed_write_scope=("company/delegation",),
                capsule_id="company-executive-delegation",
            ),
        )
    )


def _run_two(planner=None, session=None, **kw):
    return plan_objective(
        _two_eligible(),
        _objective(),
        _envelope(),
        planning_run_id="run-two",
        executive_seat="cto",
        executive_employee="chief_architect",
        manager_seat="engineering_manager",
        manager_employee="engineering_delivery_manager",
        policy_version="v1",
        policy_fingerprint="f",
        authority_source="objective envelope",
        recorded_on=DAY,
        capsule_ids=OWNED,
        planner=planner,
        session=session,
        **kw,
    )


def test_several_eligible_candidates_reach_the_executive_planner():
    answer = json.dumps(_choice(selected_candidate_id="cand-b").to_dict())
    cost = PlanningSessionCost(session_id="sess-demo", cost=_usd("0.03"))
    run = _run_two(planner=lambda brief, instructions: answer, session=cost)
    assert run.outcome is PlanningOutcome.SELECTED
    assert run.record.selected_candidate_id == "cand-b"
    assert run.record.model_used is True
    assert run.record.choice.confidence is Confidence.HIGH


def test_several_eligible_and_no_planner_escalates_rather_than_guessing():
    run = _run_two(planner=None)
    assert run.outcome is PlanningOutcome.ESCALATED
    assert run.record.model_used is False
    assert "nothing authorized to make it" in run.record.decision_reason


def test_an_out_of_contract_answer_escalates_and_is_not_repaired():
    answer = json.dumps(_choice(selected_candidate_id="cand-invented").to_dict())
    cost = PlanningSessionCost(session_id="sess-bad", cost=_usd("0.03"))
    run = _run_two(planner=lambda brief, instructions: answer, session=cost)
    assert run.outcome is PlanningOutcome.ESCALATED
    assert run.record.selected_candidate_id == ""
    assert "not among the eligible candidates" in run.record.refusal
    # The cost of the refused session is still recorded. A refusal is not free.
    assert run.record.planning_cost == _usd("0.03")


def test_malformed_planner_output_escalates():
    cost = PlanningSessionCost(session_id="sess-garbage", cost=_usd("0.01"))
    run = _run_two(planner=lambda brief, instructions: "I think option two", session=cost)
    assert run.outcome is PlanningOutcome.ESCALATED
    assert run.record.refusal


def test_a_planner_that_defers_does_not_select():
    answer = json.dumps(
        _choice(decision="defer", selected_candidate_id="", reason="neither is urgent").to_dict()
    )
    cost = PlanningSessionCost(session_id="sess-defer", cost=_usd("0.01"))
    run = _run_two(planner=lambda brief, instructions: answer, session=cost)
    assert run.outcome is PlanningOutcome.NO_ELIGIBLE_WORK_CANDIDATE
    assert run.record.selected_candidate_id == ""


# --- 9. the audit record ---------------------------------------------------


def test_the_record_answers_the_four_questions_the_ceo_asks():
    answer = json.dumps(_choice(selected_candidate_id="cand-a").to_dict())
    cost = PlanningSessionCost(
        session_id="sess-audit",
        model="claude-haiku-4-5-20251001",
        provider="anthropic",
        input_tokens=9,
        output_tokens=2612,
        cost=_usd("0.028659"),
        duration_s=25.4,
        turns=1,
    )
    run = _run_two(planner=lambda brief, instructions: answer, session=cost)
    record = run.record
    assert record.selected_candidate_id == "cand-a"          # what
    assert record.selection_reason                            # why
    assert record.eligible_candidate_ids                      # what else
    assert record.planning_cost == _usd("0.028659")           # what it cost
    assert record.session.model == "claude-haiku-4-5-20251001"
    assert record.session.turns == 1
    assert record.fingerprint()
    assert record.authority_source
    assert record.policy_version


def test_a_run_that_used_a_model_must_record_the_session():
    with pytest.raises(DelegationError, match="records no session"):
        PlanningRunRecord(
            planning_run_id="run-bad",
            objective_id="obj-demo",
            objective_intent_digest="d",
            recorded_on=DAY,
            department="engineering",
            executive_seat="cto",
            executive_employee="chief_architect",
            manager_seat="engineering_manager",
            manager_employee="engineering_delivery_manager",
            outcome=PlanningOutcome.ESCALATED,
            decision_reason="because",
            authority_source="envelope",
            policy_version="v1",
            policy_fingerprint="f",
            model_used=True,
        )


def test_a_selection_outside_the_eligible_set_cannot_be_recorded():
    with pytest.raises(DelegationError, match="not among the eligible candidates"):
        PlanningRunRecord(
            planning_run_id="run-bad2",
            objective_id="obj-demo",
            objective_intent_digest="d",
            recorded_on=DAY,
            department="engineering",
            executive_seat="cto",
            executive_employee="chief_architect",
            manager_seat="engineering_manager",
            manager_employee="engineering_delivery_manager",
            outcome=PlanningOutcome.SELECTED,
            selected_candidate_id="cand-ghost",
            eligible_candidate_ids=("cand-a",),
            decision_reason="because",
            authority_source="envelope",
            policy_version="v1",
            policy_fingerprint="f",
        )


def test_one_employee_cannot_hold_both_planning_seats():
    with pytest.raises(DelegationError, match="both the executive and the manager"):
        PlanningRunRecord(
            planning_run_id="run-bad3",
            objective_id="obj-demo",
            objective_intent_digest="d",
            recorded_on=DAY,
            department="engineering",
            executive_seat="cto",
            executive_employee="same_person",
            manager_seat="engineering_manager",
            manager_employee="same_person",
            outcome=PlanningOutcome.NO_ELIGIBLE_WORK_CANDIDATE,
            decision_reason="nothing eligible",
            authority_source="envelope",
            policy_version="v1",
            policy_fingerprint="f",
        )


def test_unreported_telemetry_stays_none_rather_than_becoming_zero():
    """Recording an unreported number as zero is how planning looks free."""
    cost = PlanningSessionCost(session_id="sess-quiet")
    assert cost.input_tokens is None
    assert cost.cost is None
    assert cost.reasoning_class is PLANNING_REASONING_CLASS
    assert cost.to_dict()["input_tokens"] is None


def test_the_ceo_report_answers_without_register_internals():
    answer = json.dumps(_choice(selected_candidate_id="cand-a").to_dict())
    cost = PlanningSessionCost(session_id="sess-report", cost=_usd("0.03"))
    run = _run_two(planner=lambda brief, instructions: answer, session=cost)
    page = ceo_planning_report(run, _two_eligible())
    for heading in (
        "OBJECTIVE", "PLANNING STATUS", "ELIGIBLE WORK FOUND", "SELECTED WORK",
        "WHY SELECTED", "DISCOVERY USED", "EXECUTIVE", "MANAGER",
        "EXPECTED VALUE", "RISK", "PLANNING COST", "READY FOR EXECUTION",
        "CEO DECISION NEEDED",
    ):
        assert heading in page
    assert "candidate_id" not in page


# --- 10. authority ---------------------------------------------------------


def test_discover_work_is_a_real_delegatable_action(policy):
    assert ActionType.DISCOVER_WORK in ActionType
    assert policy.is_reserved(ActionType.DISCOVER_WORK) is False


def test_discovery_is_held_by_the_cto_and_the_research_lead_only(policy):
    holders = sorted(
        standing.seat.seat_id
        for standing in policy.hierarchy.standings()
        if (grant := policy.grant(standing.seat.seat_id))
        and ActionType.DISCOVER_WORK in grant.action_types
    )
    assert holders == ["cto", "research_lead"]


def test_the_manager_who_selects_work_does_not_also_invent_it(policy):
    """Separation: the seat that chooses from the list does not write the list."""
    grant = policy.grant("engineering_manager")
    assert ActionType.SELECT_WORK in grant.action_types
    assert ActionType.DISCOVER_WORK not in grant.action_types


def test_no_worker_may_select_or_discover_strategic_work(policy):
    for standing in policy.hierarchy.standings():
        if standing.seat.kind is SeatKind.WORKER:
            assert policy.grant(standing.seat.seat_id) is None


def test_a_worker_asking_to_discover_is_decided_by_management(policy):
    from company.delegation.authority import AuthorityRequest, Decision, evaluate

    decision = evaluate(
        AuthorityRequest(
            request_id="req-worker-discover",
            action=ActionType.DISCOVER_WORK,
            requesting_seat="software_implementation_engineer",
            department="engineering",
            risk=Risk.LOW,
            objective_id="obj-demo",
            summary="look for new work",
        ),
        policy,
    )
    # The worker never decides it. The chain walks past them to a seat that holds it.
    assert decision.actor != "software_implementation_engineer"
    if decision.decision is Decision.APPROVED:
        assert decision.actor in {"cto", "engineering_manager", "coo"}


# --- 11. the replays -------------------------------------------------------


def test_the_low_objective_replay_finds_nothing_and_invents_nothing(index, capsule_paths):
    """The failed pilot's exact objective, planned rather than executed."""
    from company.delegation.discovery import capsule_revalidation_proposals

    pilot = (
        "Improve the reliability or maintainability of the Company OS engineering "
        "system by completing ONE genuinely useful, already-existing LOW-risk "
        "engineering improvement."
    )
    envelope = _envelope("obj-first-live-delegation-2026-09-20")
    objective = _objective(
        "obj-first-live-delegation-2026-09-20", title=pilot, envelope=envelope
    )
    discovery_envelope = _discovery_envelope(
        envelope_id="disc-low-replay",
        objective_id=objective.objective_id,
        allowed_capsules=("company-engineering-execution", "company-executive-delegation"),
    )
    proposals = capsule_revalidation_proposals(discovery_envelope, index, today=DAY)
    result = run_discovery(
        proposals,
        discovery_envelope,
        register=load_seed_register(),
        capsule_paths=capsule_paths,
        today=DAY,
        repo_root=REPO_ROOT,
    )
    run = plan_objective(
        load_seed_register(),
        objective,
        envelope,
        planning_run_id="run-low-replay",
        executive_seat="cto",
        executive_employee="chief_architect",
        manager_seat="engineering_manager",
        manager_employee="engineering_delivery_manager",
        policy_version="v1",
        policy_fingerprint="f",
        authority_source="CEO objective envelope",
        recorded_on=DAY,
        capsule_ids=index.ids(),
        discovery=result,
        discovery_envelope=discovery_envelope,
    )
    assert run.outcome is PlanningOutcome.NO_ELIGIBLE_WORK_CANDIDATE
    assert run.record.discovery_requested is True
    assert run.record.model_used is False
    assert run.record.selected_candidate_id == ""


def _register_with_classifier_candidate_open():
    """The seeded register with `auth-migration-classifier-ambiguity` reopened.

    That candidate is COMPLETED in the register today: its fix came out of the
    historical end-to-end pilot and was canonicalized by CEO exception. The
    test below is about the *mechanism* - a MEDIUM ceiling reaching medium-risk
    work, and a planner choosing between two eligible candidates - not about
    which items the company's backlog happens to hold this week. Pinning it to
    the live seed file made it fail the moment the company finished a piece of
    work, which is the one thing a working company is supposed to do. So it
    builds the register it needs.

    Appending is the supported idiom: the register is an append-only history
    and the latest version of an id wins, so this is a reopened candidate
    rather than an edited one.
    """
    seeded = load_seed_register()
    reopened = seeded.candidate("auth-migration-classifier-ambiguity").with_status(
        CandidateStatus.OPEN
    )
    return CandidateRegister(candidates=(*seeded.candidates, reopened))


def test_the_medium_replay_selects_through_the_executive_without_a_human(index):
    """Two eligible candidates, chosen by the planner, not by a preference."""
    envelope = _envelope("obj-intake-classifier", risk_ceiling="medium")
    objective = _objective("obj-intake-classifier", envelope=envelope)
    register = _register_with_classifier_candidate_open()
    answer = json.dumps(
        _choice(selected_candidate_id="reserved-screening-negation-blindness").to_dict()
    )
    cost = PlanningSessionCost(session_id="sess-medium", cost=_usd("0.028659"), turns=1)
    run = plan_objective(
        register,
        objective,
        envelope,
        planning_run_id="run-medium",
        executive_seat="cto",
        executive_employee="chief_architect",
        manager_seat="engineering_manager",
        manager_employee="engineering_delivery_manager",
        policy_version="v1",
        policy_fingerprint="f",
        authority_source="CEO objective envelope",
        recorded_on=DAY,
        capsule_ids=index.ids(),
        planner=lambda brief, instructions: answer,
        session=cost,
    )
    assert run.outcome is PlanningOutcome.SELECTED
    assert len(run.record.eligible_candidate_ids) == 2
    assert run.record.selected_candidate_id == "reserved-screening-negation-blindness"
    assert run.record.model_used is True
    assert run.record.planning_cost == _usd("0.028659")


def test_the_real_session_answer_is_accepted_by_the_deterministic_contract():
    """The answer the one real provider session returned, replayed offline.

    Kept as a fixture so the contract stays pinned against a real model's
    output without spending anything to run these tests.
    """
    evidence = (
        REPO_ROOT
        / "docs/evidence/company_os_executive_planning/planner_session_raw.json"
    )
    if not evidence.exists():  # pragma: no cover - evidence bundle not checked out
        pytest.skip("session evidence not present")
    raw = json.loads(evidence.read_text(encoding="utf-8"))
    choice = parse_choice(raw["result"])
    assert choice.decision is ExecutiveDecision.SELECT
    assert choice.selected_candidate_id == "reserved-screening-negation-blindness"
    assert choice.reason and choice.risk_reasoning and choice.resource_reasoning
    assert raw["total_cost_usd"] < 1.50


# --- 12. what this branch still cannot do ----------------------------------


def test_planning_spawns_nothing_and_holds_no_live_delegation():
    """The planner is a seam, not a process. Company OS still cannot spawn one."""
    import company.delegation.discovery as discovery
    import company.delegation.executive as executive
    import company.delegation.planning_run as planning_run

    for module in (discovery, executive, planning_run):
        source = Path(module.__file__).read_text(encoding="utf-8")
        for forbidden in ("subprocess", "os.system", "os.popen", "multiprocessing"):
            assert forbidden not in source, f"{module.__name__} names {forbidden}"


def test_planning_never_depends_on_live_pilot_machinery():
    """The invariant that survives composition.

    An earlier version of this test asserted that *no* `pilot_*.py` existed
    beside the planning modules. That was true of the branch it was written on
    and is the wrong thing to assert: the end-to-end pilot composes planning
    with the live-delegation runtime on purpose, and the check failed for the
    one composition it was meant to make safe.

    What actually matters does not depend on which branch this runs on: the
    planning layer must never *reach for* pilot code. Canonical can then carry
    planning without carrying activation, which is exactly how the curated
    canonical integration was possible.
    """
    delegation = Path(__file__).resolve().parents[1] / "company" / "delegation"
    planning_modules = (
        "candidates.py",
        "planning.py",
        "planning_record.py",
        "planning_run.py",
        "discovery.py",
        "executive.py",
        "objectives.py",
    )
    for name in planning_modules:
        path = delegation / name
        if not path.exists():  # pragma: no cover - module set differs per branch
            continue
        source = path.read_text(encoding="utf-8")
        for forbidden in (
            "from .pilot",
            "import pilot",
            "PilotActivation",
            "evaluate_live",
            "PilotBoundaryViolation",
        ):
            assert forbidden not in source, f"{name} reaches for {forbidden}"


def test_where_the_live_pilot_exists_it_is_inert_without_an_activation():
    """Importing the pilot changes nothing; only an activation does.

    Skipped on a branch that carries no pilot, which is the canonical case.
    """
    delegation = Path(__file__).resolve().parents[1] / "company" / "delegation"
    if not (delegation / "pilot.py").exists():
        pytest.skip("this branch carries no live-pilot runtime")
    from company.delegation.pilot import PilotMode, evaluate_live

    import inspect

    signature = inspect.signature(evaluate_live)
    activation = signature.parameters.get("activation")
    assert activation is not None
    assert activation.default is None, (
        "evaluate_live must default to no activation, so importing the pilot "
        "authorizes nothing"
    )
    assert PilotMode.SHADOW.value == "shadow"


def test_the_delegation_policy_is_still_shadow():
    policy_text = (
        Path(__file__).resolve().parents[1] / "company" / "delegation_policy.yaml"
    ).read_text(encoding="utf-8")
    assert "mode: shadow" in policy_text


def test_one_session_is_the_ceiling_and_it_is_written_down():
    assert MAX_PLANNING_SESSIONS == 1
    assert PLANNING_REASONING_CLASS is ReasoningClass.C

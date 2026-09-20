"""Objective-to-work planning: the rung the first live-delegation pilot found empty.

Sections
    1. the falsifiable-criteria vocabulary, pinned in both directions
    2. the work candidate model and its refusals
    3. the register, and the capsule-owned backlog view
    4. deterministic eligibility, one section per constraint
    5. selection, and who is allowed to make it
    6. the planning decision record
    7. work-order generation, and the refusal to widen
    8. intake: PLANNING_REQUIRED rather than a vague work order
    9. the deterministic controls are not vacancies
   10. the failed live-pilot objective, replayed end to end
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from ai_platform.resource_classes import Risk
from company.delegation.actions import ActionType
from company.delegation.candidates import (
    CandidateRegister,
    CandidateStatus,
    WorkCandidate,
    load_seed_register,
    propose_candidate,
)
from company.delegation.errors import AuthorityViolation, DelegationError
from company.delegation.objectives import Objective, ObjectiveLevel, PlanningEnvelope
from company.delegation.org import SeatKind
from company.delegation.planning import (
    ELIGIBILITY_CHECKS,
    EligibilityCheck,
    assess_candidate,
    eligible_candidates,
    only_eligible,
    propose_work_order,
    select_work,
)
from company.delegation.planning_record import PlanningDecisionRecord, PlanningOutcome
from company.delegation.policy import load_delegation_policy
from company.delegation.store import DelegationStore
from company.engineering.criteria import (
    assess_specificity,
    is_falsifiable_criterion,
)
from company.engineering.intake import CEORequest, IntakeOutcome, assess_request
from company.finance.money import Money
from company.runtime.config import load_company_config

DAY = dt.date(2026, 9, 20)
REPO_ROOT = Path(__file__).resolve().parents[1]


# --- fixtures --------------------------------------------------------------


def _candidate(**overrides) -> WorkCandidate:
    base = dict(
        candidate_id="cand-demo",
        title="Teach the parser to accept a trailing comma",
        description="A small, bounded parser change.",
        capsule_id="company-engineering-execution",
        department="engineering",
        source_type="known_defect",
        source_ref="docs/company_os_canonical_integration_record.md",
        problem_statement=(
            "parse_action() in company/delegation/actions.py rejects a trailing "
            "comma in the action list."
        ),
        expected_value="One fewer malformed-input refusal on valid input.",
        risk="low",
        created_at=DAY,
        evidence_refs=("docs/company_os_canonical_integration_record.md",),
        acceptance_criteria=(
            "parse_action() accepts a trailing comma and still refuses an unknown "
            "action name.",
        ),
        allowed_write_scope=("company/delegation/actions.py",),
    )
    base.update(overrides)
    return WorkCandidate(**base)


def _usd(amount: str) -> Money:
    return Money.from_dict({"amount": amount, "currency": "USD"})


def _objective(
    objective_id: str = "obj-demo",
    *,
    title: str = "Reduce false escalations in engineering intake.",
    envelope: PlanningEnvelope | None = None,
) -> Objective:
    """A CEO objective always carries its envelope; the constructor insists."""
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


def _envelope(
    objective_id: str = "obj-demo",
    *,
    risk_ceiling: str = "low",
    departments: tuple[str, ...] = ("engineering",),
    budget: str = "6.00",
    forbidden: tuple[ActionType, ...] = (),
) -> PlanningEnvelope:
    return PlanningEnvelope(
        objective_id=objective_id,
        budget=_usd(budget),
        budget_scope="engineering-operations",
        risk_ceiling=risk_ceiling,
        allowed_departments=departments,
        forbidden_actions=forbidden,
    )


OWNED = ("company-engineering-execution", "company-executive-delegation", "ai-platform")


def _assess(candidate: WorkCandidate, envelope: PlanningEnvelope | None = None, **kw):
    return assess_candidate(
        candidate,
        _objective(),
        envelope or _envelope(),
        capsule_ids=kw.pop("capsule_ids", OWNED),
        **kw,
    )


@pytest.fixture(scope="module")
def policy():
    config = load_company_config(None)
    return load_delegation_policy(
        org_registry=config.org_registry, permissions=config.permissions
    )


# --- 1. the falsifiable-criteria vocabulary --------------------------------
#
# Both directions are pinned. The accept list is every objective the existing
# engineering suites already submit; if a vocabulary change refuses one of
# those, it has broken work the company has been doing for months. The refuse
# list is the examples the pilot report names. A change that breaks either
# direction should fail here and be argued about, not discovered in production.

ALREADY_ACCEPTED = (
    "Add a field to the engineering result record.",
    "Give me a way to check whether the protected governance files have changed "
    "since an engineering work order was authorized.",
    "Improve the flavour text of the trophy presentation.",
    "Migrate the database schema to an incompatible layout.",
    "Migrate the persisted storage format.",
    "Please handle the deploy problem in the loop.",
    "Publish the engineering result to the channel once it is done.",
    "Rewrite the governance approval boundary so a protected policy file cannot "
    "be changed without a separate reviewer.",
    "Rotate the engineering oauth client secret and store the refresh token.",
    "Show governance activity on the CEO page.",
)

MUST_REFUSE = (
    "The stated objective is implemented.",
    "Improve engineering reliability.",
    "Make the system better.",
    "Identify and implement whatever is missing.",
    "Improve the reliability or maintainability of the Company OS engineering "
    "system by completing ONE genuinely useful, already-existing LOW-risk "
    "engineering improvement.",
)


@pytest.mark.parametrize("objective", ALREADY_ACCEPTED)
def test_every_objective_the_suites_already_submit_stays_specific(objective):
    assert assess_specificity(objective).specific is True


@pytest.mark.parametrize("objective", MUST_REFUSE)
def test_the_pilot_refusal_examples_are_not_specific(objective):
    verdict = assess_specificity(objective)
    assert verdict.specific is False
    assert verdict.reason


def test_explicit_acceptance_criteria_rescue_a_broad_objective():
    """Management that has done the specifying is not blocked by the title."""
    verdict = assess_specificity(
        "Improve engineering reliability.",
        acceptance_criteria=(
            "screen_reserved() returns no DecisionRequired for a negated trigger "
            "term and still returns one when the term is asserted.",
        ),
    )
    assert verdict.specific is True
    assert verdict.satisfied_by == "acceptance_criteria"


def test_a_selected_candidate_rescues_a_broad_objective():
    verdict = assess_specificity("Make the system better.", candidate_id="cand-demo")
    assert verdict.specific is True
    assert verdict.satisfied_by == "candidate"


def test_a_short_label_is_not_a_falsifiable_criterion():
    assert is_falsifiable_criterion("Done.") is False
    assert is_falsifiable_criterion("The stated objective is implemented.") is False
    assert (
        is_falsifiable_criterion(
            "parse_action() accepts a trailing comma and refuses an unknown name."
        )
        is True
    )


# --- 2. the candidate model ------------------------------------------------


def test_a_candidate_is_created_with_its_evidence_and_is_open_by_default():
    candidate = _candidate()
    assert candidate.status is CandidateStatus.OPEN
    assert candidate.selectable is True
    assert candidate.evidence_refs
    assert candidate.fingerprint()


def test_a_candidate_with_no_evidence_is_refused_at_construction():
    with pytest.raises(DelegationError, match="evidence_refs is empty"):
        _candidate(evidence_refs=())


def test_a_candidate_whose_problem_statement_names_no_subject_is_refused():
    with pytest.raises(DelegationError, match="names no subject"):
        _candidate(problem_statement="Things could be better.")


def test_a_blocked_candidate_must_name_its_blocker():
    with pytest.raises(DelegationError, match="names no blocker"):
        _candidate(status=CandidateStatus.BLOCKED)
    blocked = _candidate(
        status=CandidateStatus.BLOCKED,
        blocked_by=("a CEO policy decision nobody has taken",),
    )
    assert blocked.selectable is False


def test_an_open_candidate_may_not_also_carry_blockers():
    with pytest.raises(DelegationError, match="OPEN and also names blockers"):
        _candidate(status=CandidateStatus.OPEN, blocked_by=("waiting on a decision",))


def test_a_superseded_candidate_must_name_its_successor():
    with pytest.raises(DelegationError, match="names no successor"):
        _candidate(status=CandidateStatus.SUPERSEDED)


def test_an_unrecognised_source_is_refused_rather_than_accepted_as_a_wish():
    with pytest.raises(DelegationError, match="not a recognised evidence source"):
        _candidate(source_type="somebody_thought_of_it")


def test_a_candidate_declaring_nothing_still_needs_the_routine_action_pair():
    assert _candidate().required_action_set() == (
        ActionType.APPROVE_WORK_ORDER,
        ActionType.APPROVE_CODE_CHANGE,
    )


def test_status_change_is_a_new_record_and_never_an_edit():
    candidate = _candidate()
    moved = candidate.with_status(CandidateStatus.SELECTED)
    assert candidate.status is CandidateStatus.OPEN
    assert moved.status is CandidateStatus.SELECTED
    assert moved.fingerprint() != candidate.fingerprint()


# --- 3. the register and the backlog view ----------------------------------


def test_the_register_keeps_the_latest_version_of_each_candidate():
    candidate = _candidate()
    register = CandidateRegister(
        (candidate, candidate.with_status(CandidateStatus.COMPLETED))
    )
    assert len(register) == 1
    assert register.candidate("cand-demo").status is CandidateStatus.COMPLETED


def test_open_filtering_excludes_every_non_open_status():
    rows = [
        _candidate(candidate_id="cand-open"),
        _candidate(candidate_id="cand-selected", status=CandidateStatus.SELECTED),
        _candidate(candidate_id="cand-deferred", status=CandidateStatus.DEFERRED),
        _candidate(
            candidate_id="cand-blocked",
            status=CandidateStatus.BLOCKED,
            blocked_by=("a design decision",),
        ),
        _candidate(candidate_id="cand-done", status=CandidateStatus.COMPLETED),
    ]
    register = CandidateRegister(tuple(rows))
    assert [item.candidate_id for item in register.open_candidates()] == ["cand-open"]


def test_a_capsule_can_be_asked_what_open_work_it_owns():
    register = CandidateRegister(
        (
            _candidate(candidate_id="cand-eng"),
            _candidate(candidate_id="cand-other", capsule_id="ai-platform"),
        )
    )
    owned = register.open_for_capsule("company-engineering-execution")
    assert [item.candidate_id for item in owned] == ["cand-eng"]
    assert register.capsule_ids() == ("ai-platform", "company-engineering-execution")


def test_the_register_reports_a_dependency_it_does_not_hold():
    register = CandidateRegister((_candidate(dependencies=("cand-missing",)),))
    assert any("cand-missing" in item for item in register.violations())


def test_the_store_round_trips_a_candidate_and_its_status_history(tmp_path):
    store = DelegationStore(tmp_path)
    candidate = _candidate()
    store.append_candidate(candidate)
    store.append_candidate(candidate.with_status(CandidateStatus.SELECTED))
    assert len(store.candidate_versions("cand-demo")) == 2
    assert store.candidate_ids() == ("cand-demo",)
    assert store.register().candidate("cand-demo").status is CandidateStatus.SELECTED


# --- the discovery boundary ------------------------------------------------


def test_discovery_may_propose_work_and_may_not_select_it():
    proposed = propose_candidate(
        candidate_id="cand-proposed",
        title="A discovered item",
        description="d",
        capsule_id="company-engineering-execution",
        department="engineering",
        source_type="maintenance_gap",
        source_ref="docs/company_os_objective_planning.md",
        problem_statement=(
            "load_seed_register() in company/delegation/candidates.py reads one "
            "file and no other source."
        ),
        expected_value="v",
        risk="low",
        created_at=DAY,
        evidence_refs=("docs/company_os_objective_planning.md",),
        proposed_by="research_lead",
    )
    assert proposed.status is CandidateStatus.OPEN
    assert "research_lead" in proposed.notes
    with pytest.raises(DelegationError, match="may not arrive SELECTED"):
        propose_candidate(
            candidate_id="cand-presel",
            title="t",
            description="d",
            capsule_id="company-engineering-execution",
            department="engineering",
            source_type="maintenance_gap",
            source_ref="docs/x.md",
            problem_statement=(
                "parse_action() in company/delegation/actions.py rejects a "
                "trailing comma."
            ),
            expected_value="v",
            risk="low",
            created_at=DAY,
            evidence_refs=("docs/x.md",),
            proposed_by="research_lead",
            status=CandidateStatus.SELECTED,
        )


# --- 4. deterministic eligibility ------------------------------------------


def test_eligible_candidates_measures_everything_and_filters_nothing():
    """The rejected ones are part of the answer, so nothing is dropped."""
    register = CandidateRegister(
        (
            _candidate(candidate_id="cand-ok"),
            _candidate(candidate_id="cand-risky", risk="high"),
        )
    )
    results = eligible_candidates(
        register, _objective(), _envelope(), capsule_ids=OWNED
    )
    assert [item.candidate_id for item in results] == ["cand-ok", "cand-risky"]
    assert only_eligible(results) == ("cand-ok",)


def test_a_clean_candidate_passes_every_one_of_the_ten_checks():
    verdict = _assess(_candidate())
    assert verdict.eligible is True
    assert set(verdict.passed) == set(ELIGIBILITY_CHECKS)
    assert verdict.failed == ()


def test_a_department_outside_the_envelope_is_rejected():
    verdict = _assess(_candidate(department="ai_platform", capsule_id="ai-platform"))
    assert EligibilityCheck.DEPARTMENT_PERMITTED in verdict.failed


def test_a_capsule_no_index_confirms_is_rejected():
    verdict = _assess(_candidate(capsule_id="tools-engineering-runner"))
    assert EligibilityCheck.CAPSULE_OWNED in verdict.failed


def test_capsule_ownership_fails_closed_when_no_capsules_are_supplied():
    """Ownership that cannot be confirmed is not ownership."""
    verdict = _assess(_candidate(), capsule_ids=())
    assert EligibilityCheck.CAPSULE_OWNED in verdict.failed


def test_a_blocked_candidate_is_rejected_and_the_reason_names_the_blocker():
    verdict = _assess(
        _candidate(
            status=CandidateStatus.BLOCKED,
            blocked_by=("a CEO policy decision nobody has taken",),
        )
    )
    assert EligibilityCheck.STATUS_OPEN in verdict.failed
    assert any("CEO policy decision" in item for item in verdict.reasons)


def test_a_deferred_candidate_is_rejected_on_status():
    verdict = _assess(_candidate(status=CandidateStatus.DEFERRED))
    assert EligibilityCheck.STATUS_OPEN in verdict.failed


def test_risk_above_the_envelope_ceiling_is_rejected():
    verdict = _assess(_candidate(risk="medium"))
    assert EligibilityCheck.RISK_WITHIN_CEILING in verdict.failed
    assert _assess(_candidate(risk="medium"), _envelope(risk_ceiling="medium")).eligible


def test_an_estimate_above_the_envelope_budget_is_rejected():
    verdict = _assess(_candidate(estimated_cost=_usd("9.00")))
    assert EligibilityCheck.COST_WITHIN_BUDGET in verdict.failed
    assert _assess(_candidate(estimated_cost=_usd("3.00"))).eligible


def test_a_cost_in_another_currency_is_rejected_rather_than_converted():
    verdict = _assess(_candidate(estimated_cost=Money.from_dict({"amount": "1.00", "currency": "EUR"})))
    assert EligibilityCheck.COST_WITHIN_BUDGET in verdict.failed


def test_a_forbidden_action_is_rejected():
    verdict = _assess(
        _candidate(required_actions=(ActionType.APPROVE_DEPLOYMENT,)),
        _envelope(forbidden=(ActionType.APPROVE_DEPLOYMENT,)),
    )
    assert EligibilityCheck.NO_FORBIDDEN_ACTION in verdict.failed


def test_a_ceo_reserved_action_is_rejected_even_when_the_envelope_is_silent():
    verdict = _assess(
        _candidate(required_actions=(ActionType.AMEND_CONSTITUTION,)),
        reserved_actions=(ActionType.AMEND_CONSTITUTION,),
    )
    assert EligibilityCheck.NO_FORBIDDEN_ACTION in verdict.failed


def test_an_incomplete_dependency_is_rejected():
    dependency = _candidate(candidate_id="cand-first")
    dependent = _candidate(candidate_id="cand-second", dependencies=("cand-first",))
    register = CandidateRegister((dependency, dependent))
    verdict = assess_candidate(
        dependent, _objective(), _envelope(), capsule_ids=OWNED, register=register
    )
    assert EligibilityCheck.DEPENDENCIES_SATISFIED in verdict.failed

    done = CandidateRegister(
        (dependency.with_status(CandidateStatus.COMPLETED), dependent)
    )
    assert assess_candidate(
        dependent, _objective(), _envelope(), capsule_ids=OWNED, register=done
    ).eligible


def test_a_candidate_with_no_falsifiable_criterion_is_rejected():
    verdict = _assess(_candidate(acceptance_criteria=("Done.",)))
    assert EligibilityCheck.CRITERIA_FALSIFIABLE in verdict.failed


def test_goal_overlap_only_compares_declared_categories():
    """No declared categories on one side means nothing to compare, not a guess."""
    tagged = _candidate(goal_tags=("intake", "classifier"))
    assert _assess(tagged).eligible is True  # objective declares none
    mismatch = assess_candidate(
        tagged,
        _objective(),
        _envelope(),
        capsule_ids=OWNED,
        objective_goal_tags=("rendering",),
    )
    assert EligibilityCheck.GOAL_OVERLAP in mismatch.failed
    match = assess_candidate(
        tagged,
        _objective(),
        _envelope(),
        capsule_ids=OWNED,
        objective_goal_tags=("intake",),
    )
    assert match.eligible is True


# --- 5. selection, and who may make it -------------------------------------


def _select(register: CandidateRegister, envelope=None, **kw):
    return select_work(
        register,
        _objective(),
        envelope or _envelope(),
        planning_decision_id=kw.pop("planning_decision_id", "plan-demo"),
        executive_seat="cto",
        executive_employee="chief_architect",
        manager_seat="engineering_manager",
        manager_employee="engineering_delivery_manager",
        policy_version="delegation_policy_v1",
        policy_fingerprint="abc123",
        recorded_on=DAY,
        capsule_ids=OWNED,
        **kw,
    )


def test_one_eligible_candidate_is_selected_and_the_record_says_why():
    result = _select(CandidateRegister((_candidate(),)))
    assert result.outcome is PlanningOutcome.SELECTED
    assert result.record.selected_candidate_id == "cand-demo"
    assert result.record.acceptance_criteria
    assert result.record.objective_alignment
    assert "only candidate" in result.record.selection_reason


def test_no_eligible_candidate_returns_the_outcome_and_invents_nothing():
    register = CandidateRegister((_candidate(risk="critical"),))
    result = _select(register)
    assert result.outcome is PlanningOutcome.NO_ELIGIBLE_WORK_CANDIDATE
    assert result.record.selected_candidate_id == ""
    assert result.proposal is None
    assert "risk_within_ceiling" in result.record.selection_reason


def test_an_empty_register_is_no_eligible_candidate_rather_than_an_error():
    result = _select(CandidateRegister(()))
    assert result.outcome is PlanningOutcome.NO_ELIGIBLE_WORK_CANDIDATE


def test_several_eligible_candidates_escalate_rather_than_being_guessed_between():
    register = CandidateRegister(
        (_candidate(candidate_id="cand-a"), _candidate(candidate_id="cand-b"))
    )
    result = _select(register)
    assert result.outcome is PlanningOutcome.ESCALATED
    assert result.record.escalation_required is True
    assert result.record.escalation_reason


def test_a_named_preference_resolves_the_choice():
    register = CandidateRegister(
        (_candidate(candidate_id="cand-a"), _candidate(candidate_id="cand-b"))
    )
    result = _select(register, prefer_candidate_id="cand-b")
    assert result.outcome is PlanningOutcome.SELECTED
    assert result.record.selected_candidate_id == "cand-b"
    assert "cand-a" in result.record.candidate_ids_rejected


def test_a_preference_cannot_override_a_failed_constraint():
    register = CandidateRegister(
        (_candidate(candidate_id="cand-a"), _candidate(candidate_id="cand-b", risk="high"))
    )
    result = _select(register, prefer_candidate_id="cand-b")
    assert result.outcome is PlanningOutcome.ESCALATED
    assert "not eligible" in result.record.selection_reason


def test_only_a_ceo_objective_may_be_planned():
    lower = Objective(
        objective_id="obj-program",
        level=ObjectiveLevel.PROGRAM,
        title="A program.",
        owner_seat="cto",
        set_by="MGI",
        set_on=DAY,
        parent_id="obj-demo",
        parent_intent="x",
        department="engineering",
    )
    with pytest.raises(DelegationError, match="plans a ceo_objective"):
        select_work(
            CandidateRegister((_candidate(),)),
            lower,
            _envelope("obj-program"),
            planning_decision_id="plan-x",
            executive_seat="cto",
            executive_employee="chief_architect",
            manager_seat="engineering_manager",
            manager_employee="engineering_delivery_manager",
            policy_version="v",
            policy_fingerprint="f",
            recorded_on=DAY,
            capsule_ids=OWNED,
        )


def test_an_envelope_for_another_objective_is_refused():
    with pytest.raises(DelegationError, match="the envelope is for"):
        _select(CandidateRegister((_candidate(),)), _envelope("obj-other"))


# --- select_work authority -------------------------------------------------


def test_select_work_is_a_real_action_with_an_autonomy_rung(policy):
    assert ActionType.SELECT_WORK in ActionType
    assert policy.is_reserved(ActionType.SELECT_WORK) is False


def test_management_seats_hold_select_work_and_workers_do_not(policy):
    for seat in ("engineering_manager", "cto", "coo"):
        grant = policy.grant(seat)
        assert grant is not None
        assert ActionType.SELECT_WORK in grant.action_types, seat
    for seat in (
        "software_implementation_engineer",
        "simulation_physics_engineer",
        "visual_direction",
    ):
        assert policy.grant(seat) is None, seat


def test_no_worker_seat_holds_any_grant_at_all(policy):
    """The structural form of "workers execute, managers select"."""
    for standing in policy.hierarchy.standings():
        if standing.seat.kind is SeatKind.WORKER:
            assert policy.grant(standing.seat.seat_id) is None


def test_a_worker_raising_a_selection_is_decided_by_management(policy):
    from company.delegation.authority import AuthorityRequest, Decision, evaluate

    decision = evaluate(
        AuthorityRequest(
            request_id="req-worker-select",
            action=ActionType.SELECT_WORK,
            requesting_seat="software_implementation_engineer",
            department="engineering",
            risk=Risk.LOW,
            objective_id="obj-demo",
            summary="pick the next piece of work",
        ),
        policy,
    )
    assert decision.decision is Decision.APPROVED
    # The worker asked; the manager decided. The worker is never the actor.
    assert decision.actor == "engineering_manager"


def test_a_manager_does_not_decide_its_own_selection(policy):
    from company.delegation.authority import AuthorityRequest, evaluate

    decision = evaluate(
        AuthorityRequest(
            request_id="req-manager-select",
            action=ActionType.SELECT_WORK,
            requesting_seat="engineering_manager",
            department="engineering",
            risk=Risk.LOW,
            objective_id="obj-demo",
            summary="pick the next piece of work",
        ),
        policy,
    )
    assert decision.actor == "cto"


# --- 6. the planning decision record ---------------------------------------


def test_the_record_carries_the_objective_intent_digest():
    objective = _objective()
    result = _select(CandidateRegister((_candidate(),)))
    assert result.record.objective_intent_digest == objective.intent()


def test_editing_the_objective_breaks_the_recorded_intent_link():
    """An edited objective is a new objective, and the old record says so."""
    before = _select(CandidateRegister((_candidate(),))).record
    edited = _objective(title="Something else entirely.")
    assert before.objective_intent_digest != edited.intent()


def test_a_selected_record_naming_no_candidate_is_refused():
    with pytest.raises(DelegationError, match="names no candidate"):
        PlanningDecisionRecord(
            planning_decision_id="plan-bad",
            recorded_on=DAY,
            objective_id="obj-demo",
            objective_intent_digest="d",
            department="engineering",
            executive_seat="cto",
            executive_employee="chief_architect",
            manager_seat="engineering_manager",
            manager_employee="engineering_delivery_manager",
            decision=PlanningOutcome.SELECTED,
            selection_reason="because",
            policy_version="v",
            policy_fingerprint="f",
        )


def test_a_selection_outside_the_considered_set_is_refused():
    with pytest.raises(DelegationError, match="not among the candidates considered"):
        PlanningDecisionRecord(
            planning_decision_id="plan-bad2",
            recorded_on=DAY,
            objective_id="obj-demo",
            objective_intent_digest="d",
            department="engineering",
            executive_seat="cto",
            executive_employee="chief_architect",
            manager_seat="engineering_manager",
            manager_employee="engineering_delivery_manager",
            decision=PlanningOutcome.SELECTED,
            selected_candidate_id="cand-ghost",
            candidate_ids_considered=("cand-demo",),
            acceptance_criteria=("something checkable about parse_action().",),
            selection_reason="because",
            policy_version="v",
            policy_fingerprint="f",
        )


def test_one_employee_may_not_hold_both_ends_of_a_planning_decision():
    with pytest.raises(DelegationError, match="both the executive and the manager"):
        PlanningDecisionRecord(
            planning_decision_id="plan-bad3",
            recorded_on=DAY,
            objective_id="obj-demo",
            objective_intent_digest="d",
            department="engineering",
            executive_seat="cto",
            executive_employee="same_person",
            manager_seat="engineering_manager",
            manager_employee="same_person",
            decision=PlanningOutcome.NO_ELIGIBLE_WORK_CANDIDATE,
            selection_reason="nothing eligible",
            policy_version="v",
            policy_fingerprint="f",
        )


def test_the_planning_decision_round_trips_through_the_store(tmp_path):
    store = DelegationStore(tmp_path)
    record = _select(CandidateRegister((_candidate(),))).record
    store.append_planning_decision(record)
    loaded = store.planning_decisions("obj-demo")
    assert len(loaded) == 1
    assert loaded[0].fingerprint() == record.fingerprint()


# --- 7. work-order generation ----------------------------------------------


def _proposal(candidate=None, envelope=None, **kw):
    return propose_work_order(
        candidate or _candidate(),
        envelope or _envelope(),
        proposal_id=kw.pop("proposal_id", "wo-demo"),
        proposed_by_seat="engineering_manager",
        proposed_on=DAY,
        planning_decision_id="plan-demo",
        **kw,
    )


def test_a_proposal_inherits_the_candidate_scope_criteria_and_evidence():
    proposal = _proposal()
    assert proposal.candidate_id == "cand-demo"
    assert proposal.scope_ceiling == ("company/delegation/actions.py",)
    assert proposal.acceptance_criteria
    assert proposal.evidence_refs
    assert proposal.risk is Risk.LOW


def test_management_may_narrow_the_scope():
    candidate = _candidate(
        allowed_write_scope=("company/delegation/actions.py", "company/delegation/org.py")
    )
    proposal = _proposal(candidate, narrow_scope=("company/delegation/actions.py",))
    assert proposal.scope_ceiling == ("company/delegation/actions.py",)


def test_management_may_not_widen_the_scope():
    with pytest.raises(AuthorityViolation, match="may narrow .* not widen"):
        _proposal(narrow_scope=("company/permissions.yaml",))


def test_management_may_not_invent_new_acceptance_criteria():
    with pytest.raises(AuthorityViolation, match="adds acceptance criteria"):
        _proposal(narrow_criteria=("Something nobody reviewed.",))


def test_a_proposal_may_be_more_cautious_than_its_candidate_and_never_less():
    medium = _candidate(risk="medium")
    envelope = _envelope(risk_ceiling="medium")
    assert _proposal(medium, envelope, narrow_risk="low").risk is Risk.LOW
    with pytest.raises(AuthorityViolation, match="more cautious"):
        _proposal(_candidate(risk="low"), envelope, narrow_risk="medium")


def test_a_proposal_may_not_exceed_the_envelope_budget():
    with pytest.raises(AuthorityViolation, match="not inside the envelope"):
        _proposal(budget=_usd("99.00"))


def test_a_proposal_carries_the_checkout_it_was_planned_against():
    """Found by running the chain, not by reading it.

    The first end-to-end pilot's work order passed intake and then failed at
    the runner with "base commit is not in this repository". A proposal named
    its scope, risk, budget and acceptance criteria and never said which
    checkout any of that applied to, which is a late and confusing place to
    learn that planning had not decided.
    """
    proposal = _proposal(
        authorized_branch="eng-demo-work", base_commit="a" * 40
    )
    assert proposal.authorized_branch == "eng-demo-work"
    assert proposal.base_commit == "a" * 40
    payload = proposal.to_request_dict(requested_by="engineering_delivery_manager")
    assert payload["authorized_branch"] == "eng-demo-work"
    assert payload["base_commit"] == "a" * 40
    assert proposal.to_dict()["base_commit"] == "a" * 40


def test_a_proposal_without_a_checkout_still_builds_and_says_nothing():
    """Empty rather than invented. The caller supplies the checkout or intake
    falls back to its own default branch name, and neither is this module's
    business to guess."""
    payload = _proposal().to_request_dict(requested_by="engineering_delivery_manager")
    assert payload["authorized_branch"] == ""
    assert payload["base_commit"] == ""


def test_the_proposal_becomes_a_request_that_carries_its_provenance():
    payload = _proposal().to_request_dict(requested_by="engineering_delivery_manager")
    assert payload["candidate_id"] == "cand-demo"
    assert payload["planning_decision_id"] == "plan-demo"
    assert payload["acceptance_criteria"]


# --- 8. intake: PLANNING_REQUIRED ------------------------------------------


def _intake(objective: str, **kw):
    config = load_company_config(None)
    request = CEORequest(
        request_id=kw.pop("request_id", "req-planning-guard"),
        objective=objective,
        requested_by="MGI",
        requested_on=DAY,
        risk=Risk.LOW,
        **kw,
    )
    return assess_request(
        request, config.permissions, repo_root=REPO_ROOT, authorized_on=DAY
    )


def test_a_broad_objective_is_planning_required_and_opens_no_work_order():
    assessment = _intake(MUST_REFUSE[-1])
    assert assessment.outcome is IntakeOutcome.PLANNING_REQUIRED
    assert assessment.work_order is None
    assert "objective, not a work order" in assessment.decisions[0].reason


def test_a_vague_criterion_does_not_rescue_a_broad_objective():
    assessment = _intake(
        "Improve engineering reliability.", acceptance_criteria=("It is better.",)
    )
    assert assessment.outcome is IntakeOutcome.PLANNING_REQUIRED


def test_an_objective_no_capsule_owns_is_still_the_ceo_s_decision():
    """Two things are wrong and the more severe one names the outcome.

    "Make the system better" has no subject *and* no capsule owns it. The
    scope failure is the CEO's to resolve, so the outcome stays
    DECISION_REQUIRED - but the planning reason is still recorded beside it,
    because both are true and the reader needs both.
    """
    assessment = _intake("Make the system better.")
    assert assessment.outcome is IntakeOutcome.DECISION_REQUIRED
    reasons = " ".join(item.reason for item in assessment.decisions)
    assert "no capsule owns the subject" in reasons
    assert "objective, not a work order" in reasons


def test_specific_criteria_make_a_broad_objective_authorizable():
    assessment = _intake(
        "Improve engineering reliability.",
        acceptance_criteria=(
            "screen_reserved() in company/engineering/intake.py returns no "
            "DecisionRequired for a negated trigger term.",
        ),
    )
    assert assessment.outcome is IntakeOutcome.AUTHORIZED


def test_a_request_tied_to_a_candidate_passes_the_guard():
    assessment = _intake(
        "Improve engineering reliability.", candidate_id="cand-demo"
    )
    assert assessment.outcome is IntakeOutcome.AUTHORIZED


@pytest.mark.parametrize("objective", ALREADY_ACCEPTED[:3])
def test_the_guard_does_not_change_the_answer_for_ordinary_objectives(objective):
    assert _intake(objective).outcome is not IntakeOutcome.PLANNING_REQUIRED


def test_a_reserved_action_still_outranks_a_planning_gap():
    """The CEO hears about a reserved action even when planning is also missing."""
    assessment = _intake(
        "Make the system better by amending the constitution and whatever is missing."
    )
    assert assessment.outcome is IntakeOutcome.DECISION_REQUIRED


def test_planning_required_opens_no_job(tmp_path):
    from company.engineering.errors import EngineeringError
    from company.engineering.orchestrator import open_job
    from company.engineering.store import EngineeringStore

    assessment = _intake(MUST_REFUSE[1])
    with pytest.raises(EngineeringError, match="planning_required"):
        open_job(EngineeringStore(tmp_path), assessment, on=DAY)


# --- 9. the deterministic controls are not vacancies -----------------------


def test_the_two_independent_controls_are_deterministic_not_posts(policy):
    """`deterministic_qa` and `integration_gate` are code, not people.

    Nothing waits for them to be filled: they hold no grant, they sit at rank 0
    beside workers, and no escalation path stops at them. What this pins is that
    their emptiness is never reported as a hiring gap.
    """
    controls = [
        standing
        for standing in policy.hierarchy.standings()
        if standing.seat.is_deterministic_control
    ]
    assert sorted(item.seat.seat_id for item in controls) == [
        "deterministic_qa",
        "integration_gate",
    ]
    for standing in controls:
        assert standing.seat.kind is SeatKind.INDEPENDENT_CONTROL
        assert policy.grant(standing.seat.seat_id) is None
        assert standing.authority_cap == 0
        assert "deterministic control, not a post" in standing.detail
        assert "hire_or_remove_executive_role" not in standing.detail


def test_planning_does_not_wait_for_a_control_seat_to_be_filled():
    """The whole planning pass runs to a selection with both controls empty."""
    result = _select(CandidateRegister((_candidate(),)))
    assert result.outcome is PlanningOutcome.SELECTED


# --- 10. the failed live-pilot objective, replayed -------------------------

PILOT_OBJECTIVE = MUST_REFUSE[-1]


def test_the_seeded_register_loads_and_every_seed_is_evidence_backed():
    register = load_seed_register()
    assert len(register) >= 5
    assert register.violations() == ()
    for candidate in register.candidates:
        assert candidate.evidence_refs
        assert candidate.source_ref.startswith("docs/")


def test_the_seeded_register_classifies_honestly_rather_than_optimistically():
    """Blocked work is blocked. A register of all-open candidates is a wish list."""
    register = load_seed_register()
    statuses = {item.status for item in register.candidates}
    assert CandidateStatus.BLOCKED in statuses
    for candidate in register.by_status(CandidateStatus.BLOCKED):
        assert candidate.blocked_by


def test_the_pilot_objective_is_refused_as_executable_work():
    """The exact input that produced `authorized` before now produces a refusal."""
    assessment = _intake(PILOT_OBJECTIVE, request_id="req-pilot-replay")
    assert assessment.outcome is IntakeOutcome.PLANNING_REQUIRED


def test_the_pilot_objective_plans_to_no_eligible_candidate_under_its_low_ceiling():
    """The honest answer, and the one the register's real contents produce.

    Two candidates are real LOW-risk-adjacent engineering and sit at MEDIUM;
    one is LOW risk and owned by no capsule. Under a LOW ceiling the company
    has nothing it may routinely do, and says so instead of inventing work.
    """
    register = load_seed_register()
    envelope = _envelope("obj-first-live-delegation-2026-09-20")
    objective = _objective(
        "obj-first-live-delegation-2026-09-20",
        title=PILOT_OBJECTIVE,
        envelope=envelope,
    )
    result = select_work(
        register,
        objective,
        envelope,
        planning_decision_id="plan-pilot-replay",
        executive_seat="cto",
        executive_employee="chief_architect",
        manager_seat="engineering_manager",
        manager_employee="engineering_delivery_manager",
        policy_version="delegation_policy_v1",
        policy_fingerprint="f",
        recorded_on=DAY,
        capsule_ids=OWNED,
    )
    assert result.outcome is PlanningOutcome.NO_ELIGIBLE_WORK_CANDIDATE
    assert len(result.record.candidate_ids_considered) == len(register)
    assert result.proposal is None


def test_raising_the_ceiling_reaches_real_work_and_produces_an_authorized_order():
    """The positive path, end to end, on the real seeded register.

    objective -> eligibility -> selection -> proposal -> deterministic intake.
    Nothing here executes the work; the last step is an authorization.
    """
    register = load_seed_register()
    envelope = _envelope("obj-intake-classifier", risk_ceiling="medium")
    objective = _objective("obj-intake-classifier", envelope=envelope)
    result = select_work(
        register,
        objective,
        envelope,
        planning_decision_id="plan-intake-classifier",
        executive_seat="cto",
        executive_employee="chief_architect",
        manager_seat="engineering_manager",
        manager_employee="engineering_delivery_manager",
        policy_version="delegation_policy_v1",
        policy_fingerprint="f",
        recorded_on=DAY,
        capsule_ids=OWNED,
        prefer_candidate_id="auth-migration-classifier-ambiguity",
    )
    assert result.outcome is PlanningOutcome.SELECTED

    candidate = register.candidate(result.record.selected_candidate_id)
    proposal = propose_work_order(
        candidate,
        envelope,
        proposal_id="wo-auth-migration-classifier",
        proposed_by_seat="engineering_manager",
        proposed_on=DAY,
        planning_decision_id=result.record.planning_decision_id,
    )
    payload = proposal.to_request_dict(requested_by="engineering_delivery_manager")
    config = load_company_config(None)
    assessment = assess_request(
        CEORequest.from_mapping(payload),
        config.permissions,
        repo_root=REPO_ROOT,
        authorized_on=DAY,
    )
    assert assessment.outcome is IntakeOutcome.AUTHORIZED
    assert assessment.work_order is not None
    assert set(assessment.work_order.authorized_paths) <= set(
        candidate.allowed_write_scope
    ) | {"tests/test_company_engineering_execution.py"}

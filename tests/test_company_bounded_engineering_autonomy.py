"""Bounded routine engineering as a real operating mode, and what it refuses.

The successful discovery pilot proved the chain works once. Making it the
normal way the company runs an engineering objective changes the question from
"did it work" to "what can it never do", because nobody will be watching the
next one.

So this file is mostly refusals. The routine cases are here to show the mode is
useful; the exception cases are the reason it is safe to leave on.

Sections
    1. the operating modes, and why there is no third
    2. the CEO objective contract
    3. delegated authority inside a live contract
    4. the objective lifecycle
    5. internal integration and the promotion boundary
    6. the CEO report, and the headline it computes
    7. the exception matrix - every one of these must fail closed
    8. the carried-forward limitations, asserted rather than assumed
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from ai_platform.resource_classes import Risk
from company.delegation.actions import ActionType
from company.delegation.authority import AuthorityRequest
from company.delegation.candidates import load_seed_register
from company.delegation.errors import DelegationError
from company.delegation.exceptions import ExceptionClass
from company.delegation.objective_lifecycle import (
    TERMINAL,
    TERMINAL_WITHOUT_CEO,
    ObjectiveHistory,
    ObjectiveState,
    may_move,
)
from company.delegation.objective_report import (
    CostBreakdown,
    ManagementDecision,
    build_report,
)
from company.delegation.objectives import PlanningEnvelope
from company.delegation.operating_mode import (
    BOUNDED_ENGINEERING_ACTIONS,
    BOUNDED_ENGINEERING_MAX_RISK,
    CONTRACT_FORBIDDEN,
    CTO_ROUTINE_ACTIONS,
    MANAGER_ROUTINE_ACTIONS,
    ObjectiveContract,
    OperatingMode,
    may_activate,
)
from company.delegation.pilot import (
    PilotActivation,
    PilotEnvelope,
    PilotRequest,
    evaluate_live,
)
from company.delegation.pilot_correction import CorrectionLedger, authorize_correction
from company.delegation.pilot_integration import PROTECTED_REFS
from company.delegation.policy import load_delegation_policy
from company.delegation.promotion import (
    INTERNAL_ENGINEERING_TARGET,
    INTERNAL_ENGINEERING_TARGET_SPEC,
    NEVER_ADVANCED,
    Destination,
    classify_destination,
    may_integrate,
    promotion_readiness,
)
from company.delegation.viability import assess_viability
from company.finance.money import Money
from company.runtime.config import load_company_config

DAY = dt.date(2026, 9, 20)
REPO_ROOT = Path(__file__).resolve().parents[1]
OBJ = "obj-bounded-engineering-test"

DEV_SEAT = "software_implementation_engineer"
REV_SEAT = "engineering_reviewer"
MGR = "engineering_manager"
DEV_EMP = "software_implementation_engineer"
REV_EMP = "software_review_engineer"
ARCHITECT = "chief_architect"


@pytest.fixture(scope="module")
def config():
    return load_company_config(None)


@pytest.fixture(scope="module")
def policy(config):
    return load_delegation_policy(
        org_registry=config.org_registry, permissions=config.permissions
    )


def _contract(**kw):
    base = dict(
        contract_id="con-bounded-test",
        objective_id=OBJ,
        objective="Improve Company OS reliability within the authorized budget.",
        mode=OperatingMode.BOUNDED_ROUTINE_ENGINEERING,
        department="engineering",
        budget=Money("6.00", "USD"),
        budget_scope="engineering-operations",
        risk_ceiling=Risk.MEDIUM,
        expires_on=dt.date(2026, 12, 31),
        authorized_by="MGI (CEO)",
        success_criteria=("one useful improvement", "zero new test regressions"),
        allowed_actions=tuple(sorted(CTO_ROUTINE_ACTIONS, key=lambda a: a.value)),
        max_corrections_per_work_order=1,
    )
    base.update(kw)
    return ObjectiveContract(**base)


@pytest.fixture
def contract():
    return _contract()


@pytest.fixture
def activation(contract):
    """The live activation a bounded contract produces, aimed at the real target."""
    plan = PlanningEnvelope(
        objective_id=OBJ,
        budget=contract.budget,
        budget_scope=contract.budget_scope,
        risk_ceiling=contract.risk_ceiling,
        deadline=contract.expires_on,
        allowed_departments=("engineering",),
        success_metrics=contract.success_criteria,
    )
    envelope = PilotEnvelope(
        envelope_id="env-bounded-test",
        objective=contract.objective,
        plan=plan,
        allowed_actions=contract.allowed_actions,
        integration_target=INTERNAL_ENGINEERING_TARGET_SPEC,
        expires_on=contract.expires_on,
        authorized_by=contract.authorized_by,
        max_corrections_per_work_order=contract.max_corrections_per_work_order,
    )
    return PilotActivation(
        activation_id="act-bounded-test",
        envelope=envelope,
        activated_by=contract.authorized_by,
        activated_on=DAY,
        acknowledged_live=True,
        policy_version="delegation_policy_v1",
    )


def _live(policy, activation, action, seat, risk, **kw):
    request = AuthorityRequest(
        request_id=("req-" + action.value.replace("_", "-"))[:64],
        action=action,
        requesting_seat=seat,
        department=kw.pop("department", "engineering"),
        risk=risk,
        objective_id=OBJ,
        work_order_id="wo-bounded-test",
        summary="a bounded routine engineering decision",
        implementer=kw.pop("implementer", DEV_EMP),
        reviewer=kw.pop("reviewer", REV_EMP),
        overrides_independent_control=kw.pop("ovr", False),
    )
    kw.setdefault("review_passed", True)
    kw.setdefault("qa_passed", True)
    return evaluate_live(
        PilotRequest(request=request, as_of=DAY, **kw),
        policy,
        activation=activation,
        as_of=DAY,
    )


# --- 1. the operating modes -------------------------------------------------


def test_there_are_exactly_two_operating_modes():
    assert {item.value for item in OperatingMode} == {
        "shadow",
        "bounded_routine_engineering",
    }


def test_the_canonical_policy_file_is_still_shadow():
    """The mode lives in a contract, never in the policy file."""
    text = (REPO_ROOT / "company" / "delegation_policy.yaml").read_text(
        encoding="utf-8"
    )
    assert "\nmode: shadow\n" in text


def test_a_shadow_contract_may_not_activate(contract):
    shadow = _contract(mode=OperatingMode.SHADOW, allowed_actions=())
    verdict = may_activate(shadow, as_of=DAY)
    assert verdict.may_activate is False


def test_activation_is_refused_unless_the_mode_is_enabled(contract):
    """The default argument is shadow-only, so forgetting it enables nothing."""
    assert may_activate(contract, as_of=DAY).may_activate is False
    enabled = may_activate(
        contract,
        as_of=DAY,
        enabled_modes=(OperatingMode.BOUNDED_ROUTINE_ENGINEERING,),
    )
    assert enabled.may_activate is True


def test_an_expired_contract_may_not_activate(contract):
    verdict = may_activate(
        contract,
        as_of=dt.date(2027, 1, 1),
        enabled_modes=(OperatingMode.BOUNDED_ROUTINE_ENGINEERING,),
    )
    assert verdict.may_activate is False
    assert "expired" in verdict.reason


# --- 2. the CEO objective contract ------------------------------------------


def test_a_live_contract_states_how_success_is_judged():
    with pytest.raises(DelegationError, match="success criteria"):
        _contract(success_criteria=())


def test_a_contract_cannot_be_signed_by_the_system():
    with pytest.raises(DelegationError, match="name a person"):
        _contract(authorized_by="company_os")


@pytest.mark.parametrize(
    "action", sorted(CONTRACT_FORBIDDEN, key=lambda item: item.value)
)
def test_no_contract_may_allow_a_forbidden_action(action):
    with pytest.raises(DelegationError, match="no objective contract may allow"):
        _contract(allowed_actions=(action,))


def test_a_contract_above_medium_risk_is_not_routine():
    with pytest.raises(DelegationError, match="stops at medium risk"):
        _contract(risk_ceiling=Risk.HIGH)


def test_a_contract_outside_engineering_is_refused():
    with pytest.raises(DelegationError, match="bounded routine engineering covers"):
        _contract(department="production")


def test_a_contract_cannot_both_allow_and_forbid_an_action():
    with pytest.raises(DelegationError, match="both allowed and forbidden"):
        _contract(
            allowed_actions=(ActionType.APPROVE_CODE_CHANGE,),
            forbidden_actions=(ActionType.APPROVE_CODE_CHANGE,),
        )


def test_a_contract_may_not_name_an_action_outside_bounded_engineering():
    with pytest.raises(DelegationError, match="does not cover"):
        _contract(
            allowed_actions=(
                ActionType.APPROVE_CODE_CHANGE,
                ActionType.APPROVE_RESEARCH_PROGRAM,
            )
        )


def test_the_correction_ceiling_is_bounded():
    with pytest.raises(DelegationError, match="0..4"):
        _contract(max_corrections_per_work_order=9)


# --- 3. delegated authority inside a live contract --------------------------


@pytest.mark.parametrize(
    "action,seat",
    [
        (ActionType.APPROVE_CODE_CHANGE, DEV_SEAT),
        (ActionType.APPROVE_TEST_PROGRESSION, DEV_SEAT),
        (ActionType.APPROVE_REVIEW_OUTCOME, REV_SEAT),
        (ActionType.REQUEST_BOUNDED_CORRECTION, REV_SEAT),
    ],
)
def test_routine_management_decisions_stop_at_the_manager(
    policy, activation, action, seat
):
    decision = _live(policy, activation, action, seat, Risk.LOW)
    assert decision.actor == MGR, decision.reason
    assert decision.authorizes_action is True
    assert decision.ceo_required is False


def test_integration_stops_at_the_cto(policy, activation):
    decision = _live(
        policy,
        activation,
        ActionType.APPROVE_INTEGRATION_MERGE,
        MGR,
        Risk.MEDIUM,
        integration_branch=INTERNAL_ENGINEERING_TARGET,
    )
    assert decision.actor == "cto"
    assert decision.authorizes_action is True
    assert decision.ceo_required is False


def test_the_reviewer_manages_nothing(policy, activation):
    """The reviewer seat holds no grant; it attests and nothing else."""
    grant = policy.grant(REV_SEAT)
    assert grant is None


def test_the_manager_may_not_integrate_on_its_own_authority():
    assert ActionType.APPROVE_INTEGRATION_MERGE not in MANAGER_ROUTINE_ACTIONS
    assert ActionType.APPROVE_INTEGRATION_MERGE in CTO_ROUTINE_ACTIONS


def test_the_bounded_action_set_excludes_everything_forbidden():
    assert not (BOUNDED_ENGINEERING_ACTIONS & CONTRACT_FORBIDDEN)


# --- 4. the objective lifecycle ---------------------------------------------


def test_the_happy_path_is_legal_end_to_end():
    history = ObjectiveHistory(objective_id=OBJ)
    for state in (
        ObjectiveState.AUTHORIZED,
        ObjectiveState.PLANNING,
        ObjectiveState.EXECUTING,
        ObjectiveState.REVIEWING,
        ObjectiveState.VALIDATING,
        ObjectiveState.INTERNALLY_INTEGRATED,
        ObjectiveState.COMPLETED,
    ):
        history = history.with_transition(
            state, at=DAY, actor_seat=MGR, reason="the run advanced"
        )
    assert history.state is ObjectiveState.COMPLETED
    assert history.is_terminal() is True
    assert history.needed_the_ceo() is False


def test_a_review_may_send_work_back_once_for_correction():
    history = ObjectiveHistory(objective_id=OBJ)
    for state in (
        ObjectiveState.AUTHORIZED,
        ObjectiveState.PLANNING,
        ObjectiveState.EXECUTING,
        ObjectiveState.REVIEWING,
        ObjectiveState.EXECUTING,
    ):
        history = history.with_transition(state, at=DAY, actor_seat=MGR, reason="correction")
    assert history.state is ObjectiveState.EXECUTING


def test_no_executable_work_is_reachable_only_from_planning():
    assert may_move(ObjectiveState.PLANNING, ObjectiveState.NO_EXECUTABLE_WORK)
    for state in (
        ObjectiveState.EXECUTING,
        ObjectiveState.REVIEWING,
        ObjectiveState.VALIDATING,
    ):
        assert not may_move(state, ObjectiveState.NO_EXECUTABLE_WORK)


def test_no_executable_work_does_not_need_the_ceo():
    """The whole point: a quiet nothing-to-do is a report, not an interruption."""
    assert ObjectiveState.NO_EXECUTABLE_WORK in TERMINAL
    assert ObjectiveState.NO_EXECUTABLE_WORK in TERMINAL_WITHOUT_CEO


def test_escalated_does_need_the_ceo():
    assert ObjectiveState.ESCALATED in TERMINAL
    assert ObjectiveState.ESCALATED not in TERMINAL_WITHOUT_CEO


def test_a_terminal_objective_cannot_move_again():
    history = ObjectiveHistory(objective_id=OBJ).with_transition(
        ObjectiveState.AUTHORIZED, at=DAY, actor_seat="ceo", reason="signed"
    )
    history = history.with_transition(
        ObjectiveState.FAILED, at=DAY, actor_seat=MGR, reason="stopped"
    )
    with pytest.raises(DelegationError, match="not a legal move"):
        history.with_transition(
            ObjectiveState.PLANNING, at=DAY, actor_seat=MGR, reason="again"
        )


def test_a_history_cannot_skip_a_state():
    history = ObjectiveHistory(objective_id=OBJ)
    with pytest.raises(DelegationError, match="not a legal move"):
        history.with_transition(
            ObjectiveState.EXECUTING, at=DAY, actor_seat=MGR, reason="jump"
        )


# --- 5. internal integration and the promotion boundary ---------------------


def test_the_internal_target_is_the_only_permitted_destination():
    assert may_integrate(INTERNAL_ENGINEERING_TARGET).permitted is True


@pytest.mark.parametrize("branch", sorted(PROTECTED_REFS))
def test_no_protected_ref_is_ever_a_permitted_destination(branch):
    verdict = may_integrate(branch)
    assert verdict.permitted is False
    assert verdict.ceo_required is True


def test_canonical_is_classified_as_promotion_not_integration():
    verdict = may_integrate("company-os-v1-bootstrap")
    assert verdict.destination is Destination.CANONICAL
    assert verdict.permitted is False
    assert "promotion, not routine engineering" in verdict.reason


def test_an_unknown_destination_fails_closed():
    assert classify_destination("some-branch") is Destination.UNKNOWN
    assert may_integrate("some-branch").permitted is False


def test_never_advanced_is_a_superset_of_protected_refs():
    assert PROTECTED_REFS <= NEVER_ADVANCED


def test_promotion_readiness_authorizes_nothing():
    ready = promotion_readiness(
        (OBJ,), internally_integrated=True, gate_ready=True, blockers=()
    )
    assert ready.ready is True
    assert "is not a promotion" in ready.reason
    assert any("CEO decision" in item for item in ready.requires)


def test_promotion_is_not_ready_with_blockers():
    ready = promotion_readiness(
        (OBJ,), internally_integrated=True, gate_ready=False, blockers=("x",)
    )
    assert ready.ready is False


# --- 6. the CEO report ------------------------------------------------------


def _finished(state):
    history = ObjectiveHistory(objective_id=OBJ).with_transition(
        ObjectiveState.AUTHORIZED, at=DAY, actor_seat="ceo", reason="signed"
    )
    history = history.with_transition(
        ObjectiveState.PLANNING, at=DAY, actor_seat=MGR, reason="planning"
    )
    if state is ObjectiveState.NO_EXECUTABLE_WORK:
        return history.with_transition(state, at=DAY, actor_seat=MGR, reason="nothing")
    for nxt in (
        ObjectiveState.EXECUTING,
        ObjectiveState.REVIEWING,
        ObjectiveState.VALIDATING,
        ObjectiveState.INTERNALLY_INTEGRATED,
        ObjectiveState.COMPLETED,
    ):
        history = history.with_transition(nxt, at=DAY, actor_seat=MGR, reason="advanced")
    return history


def _report(history, **kw):
    base = dict(
        objective_id=OBJ,
        objective="Improve Company OS reliability",
        contract_id="con-bounded-test",
        history=history,
        budget=Money("6.00", "USD"),
        costs=CostBreakdown(
            developer=Money("2.63", "USD"), review=Money("0.64", "USD")
        ),
        started_on=DAY,
        finished_on=DAY,
        success_criteria=("one useful improvement",),
    )
    base.update(kw)
    return build_report(**base)


def test_a_routine_success_asks_the_ceo_for_nothing():
    report = _report(_finished(ObjectiveState.COMPLETED))
    assert report.ceo_action_required() == "NONE"
    assert report.interrupted_the_ceo() is False


def test_no_executable_work_asks_the_ceo_for_nothing():
    report = _report(_finished(ObjectiveState.NO_EXECUTABLE_WORK))
    assert report.ceo_action_required().startswith("NONE")
    assert report.interrupted_the_ceo() is False


def test_an_exception_forces_the_headline_whatever_the_state():
    report = _report(
        _finished(ObjectiveState.COMPLETED),
        exceptions=(ExceptionClass.RESERVED_ACTION,),
    )
    assert report.ceo_action_required().startswith("Yes")
    assert report.interrupted_the_ceo() is True


def test_overspend_forces_the_headline():
    report = _report(
        _finished(ObjectiveState.COMPLETED),
        costs=CostBreakdown(developer=Money("9.00", "USD")),
    )
    assert report.over_budget is True
    assert "more than its authorized budget" in report.ceo_action_required()


def test_a_report_cannot_be_written_for_a_running_objective():
    history = ObjectiveHistory(objective_id=OBJ).with_transition(
        ObjectiveState.AUTHORIZED, at=DAY, actor_seat="ceo", reason="signed"
    )
    with pytest.raises(DelegationError, match="has not finished"):
        _report(history)


def test_the_rendered_page_names_every_required_section():
    report = _report(
        _finished(ObjectiveState.COMPLETED),
        work_selected="Declare capsule ownership",
        management_decisions=(
            ManagementDecision(
                action="approve_code_change",
                decided_by_seat=MGR,
                decision="approved",
            ),
        ),
        follow_up_candidates=("capsule-ownership-semantic-review",),
    )
    page = report.render()
    for heading in (
        "OBJECTIVE",
        "OUTCOME",
        "SUCCESS METRICS",
        "WORK SELECTED",
        "WHY",
        "WORK COMPLETED",
        "INTERNAL INTEGRATION",
        "MANAGEMENT DECISIONS",
        "EXCEPTIONS",
        "MODEL COST",
        "TIME",
        "FOLLOW-UP CANDIDATES",
        "CEO ACTION REQUIRED",
    ):
        assert heading in page, heading


# --- 7. the exception matrix ------------------------------------------------


def test_qa_failure_blocks_test_progression(policy, activation):
    decision = _live(
        policy,
        activation,
        ActionType.APPROVE_TEST_PROGRESSION,
        DEV_SEAT,
        Risk.LOW,
        qa_passed=False,
    )
    assert decision.authorizes_action is False


def test_an_override_of_an_independent_control_is_refused(policy, activation):
    decision = _live(
        policy,
        activation,
        ActionType.APPROVE_REVIEW_OUTCOME,
        REV_SEAT,
        Risk.LOW,
        qa_passed=False,
        ovr=True,
    )
    assert decision.authorizes_action is False
    assert decision.ceo_required is True


@pytest.mark.parametrize("branch", sorted(PROTECTED_REFS))
def test_a_protected_ref_is_refused_live(policy, activation, branch):
    decision = _live(
        policy,
        activation,
        ActionType.APPROVE_INTEGRATION_MERGE,
        MGR,
        Risk.MEDIUM,
        integration_branch=branch,
    )
    assert decision.authorizes_action is False


def test_high_risk_is_above_the_envelope(policy, activation):
    decision = _live(
        policy, activation, ActionType.APPROVE_CODE_CHANGE, DEV_SEAT, Risk.HIGH
    )
    assert decision.authorizes_action is False


def test_public_deployment_is_refused(policy, activation):
    decision = _live(
        policy, activation, ActionType.APPROVE_DEPLOYMENT, MGR, Risk.MEDIUM
    )
    assert decision.authorizes_action is False
    assert decision.ceo_required is True


def test_publishing_is_refused(policy, activation):
    decision = _live(
        policy, activation, ActionType.APPROVE_PRODUCTION_RENDER, MGR, Risk.MEDIUM
    )
    assert decision.authorizes_action is False
    assert decision.ceo_required is True


def test_authority_modification_is_refused(policy, activation):
    decision = _live(
        policy, activation, ActionType.CHANGE_DELEGATION_POLICY, MGR, Risk.MEDIUM
    )
    assert decision.authorizes_action is False
    assert decision.ceo_required is True


def test_organization_modification_is_refused(policy, activation):
    decision = _live(
        policy, activation, ActionType.APPROVE_WORKFORCE_STATE_CHANGE, MGR, Risk.MEDIUM
    )
    assert decision.authorizes_action is False
    assert decision.ceo_required is True


def test_spend_outside_the_envelope_is_refused(policy, activation):
    decision = _live(
        policy, activation, ActionType.APPROVE_OPERATING_SPEND, MGR, Risk.MEDIUM
    )
    assert decision.authorizes_action is False


def test_the_first_correction_is_routine_and_the_second_is_not(activation):
    first = authorize_correction(
        "wo-bounded-test",
        activation=activation,
        authorizing_seat=MGR,
        reviewer_said_changes_required=True,
        ledger=CorrectionLedger.empty(),
    )
    assert first.permitted is True and first.ceo_required is False
    second = authorize_correction(
        "wo-bounded-test",
        activation=activation,
        authorizing_seat=MGR,
        reviewer_said_changes_required=True,
        ledger=CorrectionLedger(counts={"wo-bounded-test": 1}),
    )
    assert second.permitted is False and second.ceo_required is True


def test_an_expired_objective_authorizes_nothing(policy, activation):
    decision = evaluate_live(
        PilotRequest(
            request=AuthorityRequest(
                request_id="req-expired",
                action=ActionType.APPROVE_CODE_CHANGE,
                requesting_seat=DEV_SEAT,
                department="engineering",
                risk=Risk.LOW,
                objective_id=OBJ,
                work_order_id="wo-bounded-test",
                summary="after expiry",
                implementer=DEV_EMP,
                reviewer=REV_EMP,
            ),
            review_passed=True,
            qa_passed=True,
            as_of=dt.date(2027, 6, 1),
        ),
        policy,
        activation=activation,
        as_of=dt.date(2027, 6, 1),
    )
    assert decision.authorizes_action is False


def test_architecture_review_still_puts_the_cto_in_self_conflict(policy, activation):
    """The case the whole review-separation pass exists to preserve."""
    decision = _live(
        policy,
        activation,
        ActionType.APPROVE_INTEGRATION_MERGE,
        MGR,
        Risk.MEDIUM,
        integration_branch=INTERNAL_ENGINEERING_TARGET,
        reviewer=ARCHITECT,
    )
    assert decision.authorizes_action is False
    assert decision.ceo_required is True


def test_without_an_activation_nothing_is_authorized(policy):
    decision = evaluate_live(
        PilotRequest(
            request=AuthorityRequest(
                request_id="req-no-activation",
                action=ActionType.APPROVE_CODE_CHANGE,
                requesting_seat=DEV_SEAT,
                department="engineering",
                risk=Risk.LOW,
                summary="shadow default",
                implementer=DEV_EMP,
                reviewer=REV_EMP,
            ),
            review_passed=True,
            qa_passed=True,
            as_of=DAY,
        ),
        policy,
        as_of=DAY,
    )
    assert decision.authorizes_action is False


# --- 8. the carried-forward limitations -------------------------------------


def test_credential_screening_still_refuses_its_own_candidate(config):
    """FAIL_SAFE, and not weakened to make routine autonomy convenient."""
    envelope = PlanningEnvelope(
        objective_id=OBJ,
        budget=Money("6.00", "USD"),
        budget_scope="engineering-operations",
        risk_ceiling=Risk.MEDIUM,
        deadline=dt.date(2026, 12, 31),
        allowed_departments=("engineering",),
    )
    candidate = load_seed_register().candidate(
        "reserved-screening-negation-blindness"
    )
    verdict = assess_viability(
        candidate,
        envelope,
        permissions=config.permissions,
        repo_root=REPO_ROOT,
        proposed_by_seat=MGR,
        proposed_on=DAY,
        planning_decision_id="plan-" + OBJ,
        requested_by="engineering_delivery_manager",
    )
    assert verdict.executable is False
    assert "credential" in verdict.reason


def test_the_tools_candidate_still_has_no_capsule():
    """OPERATIONAL_LIMITATION: `tools/` was not given an owner to unblock work."""
    candidate = load_seed_register().candidate("runner-blocked-attempt-repo-dir")
    assert candidate is not None
    assert candidate.capsule_id not in {"", None}


def test_the_reviewer_follow_up_is_recorded_as_a_candidate():
    candidate = load_seed_register().candidate("capsule-ownership-semantic-review")
    assert candidate is not None
    assert candidate.risk is Risk.LOW
    assert "intelligence/__init__.py" in candidate.problem_statement


def test_the_deployment_gap_is_still_granted_to_nobody(policy):
    for seat_id in ("engineering_manager", "cto", "coo", "cfo"):
        grant = policy.grant(seat_id)
        if grant is None:
            continue
        assert ActionType.APPROVE_DEPLOYMENT not in grant.action_types


# --- the runner CLI shape, from Phase 10 ------------------------------------


def test_run_one_accepts_either_spelling_of_the_work_order_id():
    import argparse

    from tools.engineering_runner.__main__ import resolve_work_order_id

    positional = argparse.Namespace(work_order_id="wo-a", work_order_id_flag="")
    flagged = argparse.Namespace(work_order_id="", work_order_id_flag="wo-a")
    assert resolve_work_order_id(positional) == "wo-a"
    assert resolve_work_order_id(flagged) == "wo-a"


def test_run_one_names_both_spellings_when_the_id_is_missing():
    import argparse

    from tools.engineering_runner.errors import RunnerError
    from tools.engineering_runner.__main__ import resolve_work_order_id

    with pytest.raises(RunnerError) as excinfo:
        resolve_work_order_id(
            argparse.Namespace(work_order_id="", work_order_id_flag="")
        )
    message = str(excinfo.value)
    assert "run-one WO_ID" in message
    assert "--work-order-id" in message


def test_run_one_refuses_two_different_ids():
    import argparse

    from tools.engineering_runner.errors import RunnerError
    from tools.engineering_runner.__main__ import resolve_work_order_id

    with pytest.raises(RunnerError, match="two different work order ids"):
        resolve_work_order_id(
            argparse.Namespace(work_order_id="wo-a", work_order_id_flag="wo-b")
        )

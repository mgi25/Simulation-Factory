"""Executive delegation and management by exception, in shadow.

The suite is organised by the thing being protected rather than by module, so
a reader looking for "can a seat widen its own authority" finds one section
rather than three files.

Sections:

1.  the closed action set and the reserved list read from permissions.yaml
2.  seats, standing, and the registry the hierarchy is bound to
3.  the budget ladder
4.  policy construction: the four structural refusals
5.  delegated approval inside the ceilings
6.  rejection outside scope
7.  escalation to the lowest sufficient seat
8.  eventual CEO escalation
9.  the four authority-integrity invariants
10. the objective ladder and the planning envelope
11. management by exception
12. the decision record and the append-only store
13. the CEO brief
14. shadow mode, and the canonical CEO gate that is still the only gate
15. the historical replay
16. the package holds none of the capabilities the gate forbids
"""

from __future__ import annotations

import ast
import datetime as dt
from decimal import Decimal
import json
from pathlib import Path

import pytest

from ai_platform.resource_classes import Risk
from company.delegation.actions import (
    RESERVED_AS,
    RESERVED_HERE,
    ActionType,
    parse_action,
    reservation_drift,
    reserved_action_types,
)
from company.delegation.authority import (
    AuthorityDecision,
    AuthorityRequest,
    Decision,
    Insufficiency,
    evaluate,
    evaluate_all,
)
from company.delegation.brief import build_brief, portfolio_spend
from company.delegation.budget import (
    BudgetLadder,
    BudgetLevel,
    BudgetScope,
    money_from_text,
)
from company.delegation.errors import (
    AuthorityViolation,
    DelegationError,
    ShadowModeViolation,
)
from company.delegation.exceptions import (
    ExceptionClass,
    ExceptionContext,
    classify,
)
from company.delegation.objectives import (
    ExecutivePlan,
    Objective,
    ObjectiveLevel,
    ObjectiveTree,
    PlanningEnvelope,
    assert_within_intent,
    decompose,
    envelope_violations,
)
from company.delegation.org import (
    CEO_SEAT,
    Hierarchy,
    Seat,
    SeatAvailability,
    SeatKind,
)
from company.delegation.policy import (
    POLICY_VERSION,
    DelegatedAuthority,
    DelegationMode,
    DelegationPolicy,
    load_delegation_policy,
)
from company.delegation.record import ExecutiveDecisionRecord, record_decision
from company.delegation.scenarios import REPORTED_TOTALS, SCENARIOS, replay, summarise
from company.delegation.shadow import assert_shadow_mode, verify_shadow_mode
from company.delegation.store import DelegationStore, DelegationStoreError
from company.finance.money import Money
from company.runtime.config import load_company_config


PACKAGE = Path(__file__).resolve().parents[1] / "company" / "delegation"
POLICY_FILE = Path(__file__).resolve().parents[1] / "company" / "delegation_policy.yaml"
DAY = dt.date(2026, 9, 20)


# --- fixtures --------------------------------------------------------------


@pytest.fixture(scope="module")
def config():
    return load_company_config()


@pytest.fixture(scope="module")
def policy(config) -> DelegationPolicy:
    return load_delegation_policy(
        org_registry=config.org_registry,
        permissions=config.permissions,
        policy_path=POLICY_FILE,
    )


def usd(text: str) -> Money:
    return Money(text, "USD")


def _registry(**employees):
    return {"employees": employees}


def _permissions(**overrides):
    base = {
        "autonomy_levels": {0: {}, 1: {}, 2: {}, 3: {}, 4: {}, 5: {}},
        "bootstrap_defaults": {
            "candidate_level": 0,
            "shadow_level": 1,
            "probation_max_level": 2,
        },
        "ceo_reserved": sorted(set(RESERVED_AS.values())),
    }
    base.update(overrides)
    return base


def _toy_hierarchy(registry=None, permissions=None) -> Hierarchy:
    """CEO -> exec -> manager -> worker, with the manager filled and active."""
    return Hierarchy(
        seats=(
            Seat(seat_id=CEO_SEAT, kind=SeatKind.CEO, title="CEO", reports_to=""),
            Seat(
                seat_id="exec",
                kind=SeatKind.EXECUTIVE,
                title="Executive",
                reports_to=CEO_SEAT,
                employee="an_executive",
                departments=("engineering",),
            ),
            Seat(
                seat_id="manager",
                kind=SeatKind.DEPARTMENT_MANAGEMENT,
                title="Manager",
                reports_to="exec",
                employee="a_manager",
                departments=("engineering",),
            ),
            Seat(
                seat_id="worker",
                kind=SeatKind.WORKER,
                title="Worker",
                reports_to="manager",
                employee="a_worker",
                departments=("engineering",),
            ),
        ),
        org_registry=registry
        or _registry(
            an_executive={"state": "active", "department": "engineering", "manager": "ceo"},
            a_manager={"state": "active", "department": "engineering", "manager": "an_executive"},
            a_worker={"state": "active", "department": "engineering", "manager": "a_manager"},
        ),
        permissions=permissions or _permissions(),
    )


def _toy_ladder() -> BudgetLadder:
    return BudgetLadder(
        (
            BudgetScope(
                scope_id="company-budget",
                level=BudgetLevel.COMPANY,
                ceiling=usd("50.00"),
            ),
            BudgetScope(
                scope_id="dept-budget",
                level=BudgetLevel.DEPARTMENT,
                parent_id="company-budget",
                ceiling=usd("30.00"),
            ),
            BudgetScope(
                scope_id="prog-budget",
                level=BudgetLevel.PROGRAM,
                parent_id="dept-budget",
                ceiling=usd("10.00"),
            ),
        )
    )


_AUTONOMY = {
    "approve_code_change": 3,
    "approve_test_progression": 2,
    "approve_operating_spend": 4,
    "approve_integration_merge": 4,
    "request_bounded_correction": 2,
    "stop_work_on_invalid_premise": 1,
    "approve_deployment": 4,
}


def _toy_policy(hierarchy=None, grants=None, **kwargs) -> DelegationPolicy:
    hierarchy = hierarchy or _toy_hierarchy()
    if grants is None:
        grants = (
            DelegatedAuthority(
                seat="manager",
                action_types=frozenset(
                    {
                        ActionType.APPROVE_CODE_CHANGE,
                        ActionType.APPROVE_TEST_PROGRESSION,
                        ActionType.REQUEST_BOUNDED_CORRECTION,
                    }
                ),
                max_risk=Risk.LOW,
                per_decision_ceiling=usd("5.00"),
                budget_scope="prog-budget",
            ),
            DelegatedAuthority(
                seat="exec",
                action_types=frozenset(
                    {
                        ActionType.APPROVE_CODE_CHANGE,
                        ActionType.APPROVE_INTEGRATION_MERGE,
                        ActionType.APPROVE_OPERATING_SPEND,
                    }
                ),
                max_risk=Risk.MEDIUM,
                per_decision_ceiling=usd("25.00"),
                budget_scope="dept-budget",
            ),
        )
    return DelegationPolicy(
        hierarchy=hierarchy,
        grants=grants,
        ladder=kwargs.pop("ladder", _toy_ladder()),
        action_autonomy=kwargs.pop("action_autonomy", dict(_AUTONOMY)),
        **kwargs,
    )


def _request(**overrides) -> AuthorityRequest:
    fields = {
        "request_id": "req-under-test",
        "action": ActionType.APPROVE_CODE_CHANGE,
        "requesting_seat": "worker",
        "department": "engineering",
        "risk": Risk.LOW,
    }
    fields.update(overrides)
    return AuthorityRequest(**fields)


# --- 1. the closed action set and the reserved list ------------------------


def test_an_unknown_action_name_is_refused_rather_than_guessed():
    with pytest.raises(DelegationError) as exc:
        parse_action("approve_whatever_this_is")
    assert "unclassified" in str(exc.value)


def test_unclassified_is_always_reserved_however_permissions_reads():
    assert ActionType.UNCLASSIFIED in reserved_action_types({"ceo_reserved": []})
    assert ActionType.UNCLASSIFIED in RESERVED_HERE


def test_the_reserved_set_is_read_from_permissions_and_not_restated(config):
    reserved = reserved_action_types(config.permissions)
    assert ActionType.PUBLISH_PUBLIC_VIDEO in reserved
    assert ActionType.AMEND_CONSTITUTION in reserved
    # And it follows the file: drop one entry, lose one reserved action.
    without_publish = dict(config.permissions)
    without_publish["ceo_reserved"] = [
        name for name in config.permissions["ceo_reserved"] if name != "publish_public_video"
    ]
    assert ActionType.PUBLISH_PUBLIC_VIDEO not in reserved_action_types(without_publish)


def test_reservation_drift_reports_a_release_and_tolerates_growth(config):
    assert reservation_drift(config.permissions).ok
    shrunk = dict(config.permissions)
    shrunk["ceo_reserved"] = ["amend_constitution"]
    drift = reservation_drift(shrunk)
    assert not drift.ok
    assert any("publish_public_video" in item for item in drift.released)
    grown = dict(config.permissions)
    grown["ceo_reserved"] = [*config.permissions["ceo_reserved"], "some_new_reservation"]
    assert reservation_drift(grown).ok


def test_every_self_reserved_action_carries_a_reason():
    from company.delegation.actions import RESERVED_HERE_REASON

    assert set(RESERVED_HERE) == set(RESERVED_HERE_REASON)


# --- 2. seats, standing, and the registry ---------------------------------


def test_the_ceo_seat_is_never_filled_from_the_registry():
    with pytest.raises(AuthorityViolation):
        Seat(seat_id=CEO_SEAT, kind=SeatKind.CEO, title="CEO", reports_to="", employee="someone")


def test_a_hierarchy_without_a_ceo_seat_is_refused():
    with pytest.raises(DelegationError) as exc:
        Hierarchy(
            seats=(
                Seat(
                    seat_id="lonely",
                    kind=SeatKind.EXECUTIVE,
                    title="Lonely",
                    reports_to="lonely",
                ),
            ),
            org_registry=_registry(),
            permissions=_permissions(),
        )
    assert "reports to itself" in str(exc.value) or "ceo" in str(exc.value)


def test_an_escalation_that_goes_downward_is_refused():
    with pytest.raises(AuthorityViolation) as exc:
        Hierarchy(
            seats=(
                Seat(seat_id=CEO_SEAT, kind=SeatKind.CEO, title="CEO", reports_to=""),
                Seat(
                    seat_id="worker_seat",
                    kind=SeatKind.WORKER,
                    title="W",
                    reports_to=CEO_SEAT,
                ),
                Seat(
                    seat_id="boss_seat",
                    kind=SeatKind.EXECUTIVE,
                    title="B",
                    reports_to="worker_seat",
                ),
            ),
            org_registry=_registry(),
            permissions=_permissions(),
        )
    assert "not an escalation" in str(exc.value)


def test_a_circular_chain_is_refused_at_construction():
    with pytest.raises(AuthorityViolation) as exc:
        Hierarchy(
            seats=(
                Seat(seat_id=CEO_SEAT, kind=SeatKind.CEO, title="CEO", reports_to=""),
                Seat(
                    seat_id="one_seat",
                    kind=SeatKind.EXECUTIVE,
                    title="1",
                    reports_to="two_seat",
                ),
                Seat(
                    seat_id="two_seat",
                    kind=SeatKind.EXECUTIVE,
                    title="2",
                    reports_to="one_seat",
                ),
            ),
            org_registry=_registry(),
            permissions=_permissions(),
        )
    assert "loops" in str(exc.value)


def test_a_dormant_employee_cannot_decide_anything():
    hierarchy = _toy_hierarchy(
        registry=_registry(
            an_executive={"state": "active", "department": "engineering", "manager": "ceo"},
            a_manager={"state": "dormant", "department": "engineering", "manager": "an_executive"},
            a_worker={"state": "active", "department": "engineering", "manager": "a_manager"},
        )
    )
    standing = hierarchy.standing("manager")
    assert standing.availability is SeatAvailability.DORMANT
    assert not standing.can_decide
    assert "rule 18" in standing.detail


def test_a_restricted_state_is_capped_below_approval():
    hierarchy = _toy_hierarchy(
        registry=_registry(
            an_executive={"state": "active", "department": "engineering", "manager": "ceo"},
            a_manager={"state": "shadow", "department": "engineering", "manager": "an_executive"},
            a_worker={"state": "active", "department": "engineering", "manager": "a_manager"},
        )
    )
    standing = hierarchy.standing("manager")
    assert standing.availability is SeatAvailability.RESTRICTED
    assert standing.authority_cap == 1  # permissions.yaml shadow_level


def test_a_seat_claiming_an_employee_the_registry_lacks_is_an_impersonation():
    hierarchy = _toy_hierarchy(
        registry=_registry(
            an_executive={"state": "active", "department": "engineering", "manager": "ceo"},
            a_worker={"state": "active", "department": "engineering", "manager": "a_manager"},
        )
    )
    with pytest.raises(AuthorityViolation) as exc:
        hierarchy.standing("manager")
    assert "impersonation" in str(exc.value)


def test_one_employee_holding_two_seats_is_reported():
    hierarchy = Hierarchy(
        seats=(
            Seat(seat_id=CEO_SEAT, kind=SeatKind.CEO, title="CEO", reports_to=""),
            Seat(
                seat_id="exec",
                kind=SeatKind.EXECUTIVE,
                title="E",
                reports_to=CEO_SEAT,
                employee="busy_person",
            ),
            Seat(
                seat_id="manager",
                kind=SeatKind.DEPARTMENT_MANAGEMENT,
                title="M",
                reports_to="exec",
                employee="busy_person",
            ),
        ),
        org_registry=_registry(
            busy_person={"state": "active", "department": "engineering", "manager": "ceo"}
        ),
        permissions=_permissions(),
    )
    problems = hierarchy.registry_conflicts()
    assert any("own escalation" in item for item in problems)


def test_the_canonical_chart_reports_exactly_the_inserted_manager_layer(policy):
    conflicts = policy.hierarchy.registry_conflicts()
    assert len(conflicts) == 2
    assert all("engineering_manager" in item for item in conflicts)
    assert all("no employee fills" in item for item in conflicts)


def test_the_canonical_policy_seats_every_registry_employee(policy, config):
    seated = {
        seat.employee for seat in policy.hierarchy.seats if seat.employee
    }
    assert seated == set(config.org_registry["employees"])


# --- 3. the budget ladder --------------------------------------------------


def test_a_child_budget_may_not_exceed_its_parent():
    with pytest.raises(DelegationError) as exc:
        BudgetLadder(
            (
                BudgetScope("root-budget", BudgetLevel.COMPANY, usd("10.00")),
                BudgetScope("child-budget", BudgetLevel.DEPARTMENT, usd("20.00"), "root-budget"),
            )
        )
    assert "exceeds its parent" in str(exc.value)


def test_siblings_may_not_sum_past_their_parent():
    with pytest.raises(DelegationError) as exc:
        BudgetLadder(
            (
                BudgetScope("root-budget", BudgetLevel.COMPANY, usd("10.00")),
                BudgetScope("one-budget", BudgetLevel.DEPARTMENT, usd("6.00"), "root-budget"),
                BudgetScope("two-budget", BudgetLevel.DEPARTMENT, usd("6.00"), "root-budget"),
            )
        )
    assert "four ways to spend one budget" in str(exc.value)


def test_a_rung_may_not_skip_a_level():
    with pytest.raises(DelegationError) as exc:
        BudgetLadder(
            (
                BudgetScope("root-budget", BudgetLevel.COMPANY, usd("10.00")),
                BudgetScope("wo-budget", BudgetLevel.WORK_ORDER, usd("1.00"), "root-budget"),
            )
        )
    assert "hangs from a" in str(exc.value)


def test_an_unknown_scope_is_unknown_and_not_unlimited():
    finding = _toy_ladder().check("no-such-budget", usd("1.00"))
    assert not finding.known
    assert not finding.within
    assert "not an unlimited one" in finding.reason


def test_the_tightest_binding_rung_is_the_one_reported():
    ladder = _toy_ladder()
    finding = ladder.check(
        "prog-budget",
        usd("1.00"),
        {"dept-budget": usd("29.50")},
    )
    assert finding.known and not finding.within
    assert finding.scope_id == "dept-budget"


def test_consumption_is_subtracted_before_the_ceiling_is_compared():
    ladder = _toy_ladder()
    inside = ladder.check("prog-budget", usd("2.00"), {"prog-budget": usd("7.00")})
    assert inside.within
    outside = ladder.check("prog-budget", usd("4.00"), {"prog-budget": usd("7.00")})
    assert not outside.within


def test_a_policy_amount_must_be_written_as_text():
    with pytest.raises(DelegationError) as exc:
        money_from_text(25.0, "USD", "ceiling")
    assert "not a float" in str(exc.value)
    assert money_from_text("25.00", "USD", "ceiling").amount == Decimal("25.00")


# --- 4. policy construction: the four structural refusals -----------------


def test_a_policy_cannot_grant_a_reserved_action():
    grant = DelegatedAuthority(
        seat="manager",
        action_types=frozenset({ActionType.PUBLISH_PUBLIC_VIDEO}),
        max_risk=Risk.LOW,
        per_decision_ceiling=usd("1.00"),
        budget_scope="prog-budget",
    )
    with pytest.raises(AuthorityViolation) as exc:
        _toy_policy(grants=(grant,))
    assert "not delegable" in str(exc.value)


def test_the_ceo_seat_receives_no_grant():
    grant = DelegatedAuthority(
        seat=CEO_SEAT,
        action_types=frozenset({ActionType.APPROVE_CODE_CHANGE}),
        max_risk=Risk.LOW,
        per_decision_ceiling=usd("1.00"),
        budget_scope="prog-budget",
    )
    with pytest.raises(AuthorityViolation) as exc:
        _toy_policy(grants=(grant,))
    assert "escalation terminates" in str(exc.value)


def test_a_subordinate_may_not_out_rank_its_manager_on_risk():
    grants = (
        DelegatedAuthority(
            seat="manager",
            action_types=frozenset({ActionType.APPROVE_CODE_CHANGE}),
            max_risk=Risk.HIGH,
            per_decision_ceiling=usd("1.00"),
            budget_scope="prog-budget",
        ),
        DelegatedAuthority(
            seat="exec",
            action_types=frozenset({ActionType.APPROVE_CODE_CHANGE}),
            max_risk=Risk.LOW,
            per_decision_ceiling=usd("5.00"),
            budget_scope="dept-budget",
        ),
    )
    with pytest.raises(AuthorityViolation) as exc:
        _toy_policy(grants=grants)
    assert "Escalation would be a demotion" in str(exc.value)


def test_a_subordinate_may_not_out_rank_its_manager_on_budget():
    grants = (
        DelegatedAuthority(
            seat="manager",
            action_types=frozenset({ActionType.APPROVE_CODE_CHANGE}),
            max_risk=Risk.LOW,
            per_decision_ceiling=usd("30.00"),
            budget_scope="prog-budget",
        ),
        DelegatedAuthority(
            seat="exec",
            action_types=frozenset({ActionType.APPROVE_CODE_CHANGE}),
            max_risk=Risk.LOW,
            per_decision_ceiling=usd("5.00"),
            budget_scope="dept-budget",
        ),
    )
    with pytest.raises(AuthorityViolation) as exc:
        _toy_policy(grants=grants)
    assert "subordinate ceiling above its" in str(exc.value)


def test_a_granted_action_needs_a_declared_autonomy_level():
    with pytest.raises(DelegationError) as exc:
        _toy_policy(action_autonomy={"approve_operating_spend": 4})
    assert "no declared autonomy level" in str(exc.value)


def test_a_grant_against_an_unknown_budget_scope_is_refused():
    grant = DelegatedAuthority(
        seat="manager",
        action_types=frozenset({ActionType.APPROVE_CODE_CHANGE}),
        max_risk=Risk.LOW,
        per_decision_ceiling=usd("1.00"),
        budget_scope="no-such-budget",
    )
    with pytest.raises(DelegationError) as exc:
        _toy_policy(grants=(grant,))
    assert "the ladder does not carry" in str(exc.value)


def test_the_canonical_policy_declares_version_one_and_shadow_mode(policy):
    assert policy.version == POLICY_VERSION
    assert policy.mode is DelegationMode.SHADOW
    assert len(policy.fingerprint()) == 16


# --- 5. delegated approval inside the ceilings ----------------------------


def test_a_routine_low_risk_change_is_approved_by_the_manager():
    decision = evaluate(_request(), _toy_policy())
    assert decision.decision is Decision.APPROVED
    assert decision.actor == "manager"
    assert not decision.ceo_required
    assert not decision.escalation_required
    assert decision.handled_internally


def test_a_spend_inside_every_rung_is_approved_with_the_budget_recorded():
    decision = evaluate(
        _request(amount=usd("3.00"), budget_scope="prog-budget"), _toy_policy()
    )
    assert decision.decision is Decision.APPROVED
    assert decision.actor == "manager"
    assert decision.budget is not None and decision.budget.within


def test_two_runs_over_the_same_inputs_produce_the_same_answer():
    policy = _toy_policy()
    first = evaluate(_request(), policy)
    second = evaluate(_request(), policy)
    assert first.fingerprint() == second.fingerprint()


def test_a_batch_answers_each_request_independently():
    policy = _toy_policy()
    answers = evaluate_all(
        (
            _request(request_id="req-one"),
            _request(request_id="req-two", risk=Risk.CRITICAL),
        ),
        policy,
    )
    assert answers[0].decision is Decision.APPROVED
    assert answers[1].ceo_required


# --- 6. rejection outside scope -------------------------------------------


def test_an_action_no_seat_holds_is_rejected_and_carried_to_the_ceo():
    decision = evaluate(_request(action=ActionType.APPROVE_DEPLOYMENT), _toy_policy())
    assert decision.decision is Decision.REJECTED
    assert decision.ceo_required
    assert "outside the delegated model entirely" in decision.reason


def test_a_request_from_another_department_does_not_reach_this_manager():
    hierarchy = _toy_hierarchy()
    decision = evaluate(
        _request(department="creative", requesting_seat="worker"),
        _toy_policy(hierarchy=hierarchy),
    )
    assert decision.ceo_required
    assert any(
        step.insufficiency is Insufficiency.WRONG_DEPARTMENT for step in decision.chain
    )


def test_the_deployment_gap_is_visible_in_the_canonical_policy(policy):
    """The known deployment-policy blocker, asserted rather than assumed."""
    granted = {
        action
        for grant in policy.grants
        for action in grant.action_types
    }
    assert ActionType.APPROVE_DEPLOYMENT not in granted
    assert ActionType.APPROVE_DEPLOYMENT not in policy.reserved
    decision = evaluate(
        _request(
            requesting_seat="software_implementation_engineer",
            action=ActionType.APPROVE_DEPLOYMENT,
        ),
        policy,
    )
    assert decision.decision is Decision.REJECTED and decision.ceo_required


# --- 7. escalation to the lowest sufficient seat --------------------------


def test_a_medium_risk_change_passes_the_manager_and_stops_at_the_executive():
    decision = evaluate(_request(risk=Risk.MEDIUM), _toy_policy())
    assert decision.decision is Decision.APPROVED
    assert decision.actor == "exec"
    assert not decision.ceo_required
    assert decision.chain[-1].insufficiency is Insufficiency.RISK_ABOVE_CEILING


def test_escalation_never_jumps_straight_to_the_ceo():
    decision = evaluate(_request(amount=usd("9.00"), budget_scope="prog-budget"), _toy_policy())
    assert decision.actor == "exec"
    assert CEO_SEAT not in {step.seat for step in decision.chain}


def test_a_vacant_seat_is_passed_over_and_named_in_the_chain(policy):
    decision = evaluate(
        _request(requesting_seat="software_implementation_engineer"), policy
    )
    assert decision.decision is Decision.APPROVED
    assert decision.actor == "cto"
    vacant = [
        step for step in decision.chain
        if step.insufficiency is Insufficiency.SEAT_VACANT
    ]
    assert [step.seat for step in vacant] == ["engineering_manager"]


def test_a_dormant_seat_is_passed_over_and_named_in_the_chain():
    hierarchy = _toy_hierarchy(
        registry=_registry(
            an_executive={"state": "active", "department": "engineering", "manager": "ceo"},
            a_manager={"state": "dormant", "department": "engineering", "manager": "an_executive"},
            a_worker={"state": "active", "department": "engineering", "manager": "a_manager"},
        )
    )
    decision = evaluate(_request(), _toy_policy(hierarchy=hierarchy))
    assert decision.decision is Decision.APPROVED
    assert decision.actor == "exec"
    assert decision.chain[-1].insufficiency is Insufficiency.SEAT_DORMANT


# --- 8. eventual CEO escalation -------------------------------------------


def test_a_reserved_action_reaches_the_ceo_before_anything_is_measured():
    decision = evaluate(
        _request(
            action=ActionType.PUBLISH_PUBLIC_VIDEO,
            amount=usd("0.01"),
            budget_scope="prog-budget",
        ),
        _toy_policy(),
    )
    assert decision.decision is Decision.ESCALATE
    assert decision.actor == CEO_SEAT and decision.ceo_required
    assert decision.budget is None  # nothing was measured
    assert decision.reserved_as == "publish_public_video"


def test_a_critical_risk_change_exhausts_every_ceiling_and_reaches_the_ceo():
    decision = evaluate(_request(risk=Risk.CRITICAL), _toy_policy())
    assert decision.decision is Decision.ESCALATE
    assert decision.ceo_required
    assert decision.chain[-1].insufficiency is Insufficiency.RISK_ABOVE_CEILING


def test_a_spend_above_every_ceiling_reaches_the_ceo():
    decision = evaluate(
        _request(
            action=ActionType.APPROVE_OPERATING_SPEND,
            risk=Risk.LOW,
            amount=usd("40.00"),
            budget_scope="dept-budget",
        ),
        _toy_policy(),
    )
    assert decision.ceo_required
    assert decision.chain[-1].insufficiency is Insufficiency.BUDGET_ABOVE_CEILING


def test_a_spend_against_an_unrecorded_budget_escalates_rather_than_approving():
    decision = evaluate(
        _request(
            action=ActionType.APPROVE_OPERATING_SPEND,
            amount=usd("1.00"),
            budget_scope="ghost-budget",
        ),
        _toy_policy(),
    )
    assert decision.ceo_required
    assert decision.chain[-1].insufficiency is Insufficiency.BUDGET_UNKNOWN


def test_expanding_authority_and_changing_the_policy_are_always_ceo_reserved():
    policy = _toy_policy()
    for action in (
        ActionType.EXPAND_AUTHORITY,
        ActionType.CHANGE_DELEGATION_POLICY,
        ActionType.CHANGE_GOVERNANCE_POLICY,
        ActionType.UNCLASSIFIED,
    ):
        decision = evaluate(_request(action=action), policy)
        assert decision.ceo_required, action


# --- 9. the four authority-integrity invariants ---------------------------


def test_a_seat_never_decides_its_own_request():
    decision = evaluate(_request(requesting_seat="manager"), _toy_policy())
    assert decision.actor != "manager"
    assert any(
        step.insufficiency is Insufficiency.SELF_APPROVAL for step in decision.chain
    )


def test_self_approval_is_checked_before_the_ceilings():
    """A seat cannot approve its own request by keeping it small."""
    decision = evaluate(
        _request(requesting_seat="manager", amount=usd("0.01"), budget_scope="prog-budget"),
        _toy_policy(),
    )
    assert decision.actor == "exec"
    self_step = next(
        step for step in decision.chain
        if step.insufficiency is Insufficiency.SELF_APPROVAL
    )
    assert self_step.seat == "manager"


def test_a_request_from_the_ceo_seat_is_refused():
    with pytest.raises(AuthorityViolation) as exc:
        _request(requesting_seat=CEO_SEAT)
    assert "sets the objective" in str(exc.value)


def test_a_decision_cannot_be_both_approved_and_ceo_required():
    with pytest.raises(AuthorityViolation):
        AuthorityDecision(
            request_id="req-under-test",
            decision=Decision.APPROVED,
            actor="manager",
            authority_source=POLICY_VERSION,
            action=ActionType.APPROVE_CODE_CHANGE,
            risk=Risk.LOW,
            escalation_required=False,
            ceo_required=True,
            reason="impossible",
        )


def test_the_model_never_writes_a_ceo_approval():
    with pytest.raises(AuthorityViolation) as exc:
        AuthorityDecision(
            request_id="req-under-test",
            decision=Decision.APPROVED,
            actor=CEO_SEAT,
            authority_source=POLICY_VERSION,
            action=ActionType.APPROVE_CODE_CHANGE,
            risk=Risk.LOW,
            escalation_required=False,
            ceo_required=False,
            reason="impossible",
        )
    assert "named human act" in str(exc.value)


def test_a_decision_never_carries_authority_to_act():
    with pytest.raises(AuthorityViolation) as exc:
        AuthorityDecision(
            request_id="req-under-test",
            decision=Decision.APPROVED,
            actor="manager",
            authority_source=POLICY_VERSION,
            action=ActionType.APPROVE_CODE_CHANGE,
            risk=Risk.LOW,
            escalation_required=False,
            ceo_required=False,
            reason="a decision",
            authorizes_action=True,
        )
    assert "never carries authority to act" in str(exc.value)


# --- 10. the objective ladder and the planning envelope -------------------


def _envelope(objective_id="obj-grow-shorts", **overrides) -> PlanningEnvelope:
    fields = {
        "objective_id": objective_id,
        "budget": usd("50.00"),
        "budget_scope": "company-budget",
        "risk_ceiling": Risk.MEDIUM,
        "deadline": dt.date(2026, 12, 31),
        "allowed_departments": ("engineering", "creative"),
        "forbidden_actions": (ActionType.PUBLISH_PUBLIC_VIDEO,),
        "success_metrics": ("100k monthly Shorts views",),
    }
    fields.update(overrides)
    return PlanningEnvelope(**fields)


def _root(objective_id="obj-grow-shorts") -> Objective:
    return Objective(
        objective_id=objective_id,
        level=ObjectiveLevel.CEO_OBJECTIVE,
        title="Grow Simulation Factory monthly Shorts views to 100k",
        owner_seat="coo",
        set_by="the CEO",
        set_on=DAY,
        success_metrics=("100k monthly Shorts views",),
        envelope=_envelope(objective_id),
    )


def test_a_ceo_objective_must_carry_an_envelope():
    with pytest.raises(DelegationError) as exc:
        Objective(
            objective_id="obj-no-envelope",
            level=ObjectiveLevel.CEO_OBJECTIVE,
            title="Do something",
            owner_seat="coo",
            set_by="the CEO",
            set_on=DAY,
        )
    assert "plans against no limit" in str(exc.value)


def test_decompose_produces_the_next_rung_and_stamps_the_parent_intent():
    root = _root()
    program = decompose(
        root,
        objective_id="prog-shorts-hooks",
        title="Test opening-hook variants",
        owner_seat="content_strategy_lead",
        set_by="coo",
        set_on=DAY,
        department="creative",
    )
    assert program.level is ObjectiveLevel.PROGRAM
    assert program.parent_intent == root.intent()
    assert_within_intent(program, root)


def test_a_level_cannot_be_skipped():
    root = _root()
    orphan = Objective(
        objective_id="wo-straight-off-the-top",
        level=ObjectiveLevel.WORK_ORDER,
        title="A work order with no program",
        owner_seat="cto",
        set_by="cto",
        set_on=DAY,
        parent_id=root.objective_id,
        parent_intent=root.intent(),
    )
    problems = ObjectiveTree((root, orphan)).lineage_violations()
    assert any("hangs from a" in item for item in problems)


def test_editing_a_ceo_objective_orphans_every_child_derived_from_it():
    root = _root()
    program = decompose(
        root,
        objective_id="prog-shorts-hooks",
        title="Test opening-hook variants",
        owner_seat="content_strategy_lead",
        set_by="coo",
        set_on=DAY,
    )
    edited = Objective(
        objective_id=root.objective_id,
        level=ObjectiveLevel.CEO_OBJECTIVE,
        title="Grow Simulation Factory monthly Shorts views to 500k",
        owner_seat="coo",
        set_by="the CEO",
        set_on=DAY,
        success_metrics=("500k monthly Shorts views",),
        envelope=_envelope(),
    )
    problems = ObjectiveTree((edited, program)).lineage_violations()
    assert any("a new objective, not an edit" in item for item in problems)
    with pytest.raises(AuthorityViolation):
        assert_within_intent(program, edited)


def test_bookkeeping_changes_do_not_move_the_intent_digest():
    root = _root()
    same_intent = Objective(
        objective_id=root.objective_id,
        level=ObjectiveLevel.CEO_OBJECTIVE,
        title=root.title,
        owner_seat="cto",  # a different owner
        set_by="the CEO",
        set_on=dt.date(2026, 10, 1),  # a different day
        success_metrics=root.success_metrics,
        evidence_refs=("docs/company_os_executive_delegation.md",),
        envelope=_envelope(),
    )
    assert same_intent.intent() == root.intent()


def test_every_objective_traces_back_to_a_ceo_objective():
    root = _root()
    program = decompose(
        root,
        objective_id="prog-shorts-hooks",
        title="Test opening-hook variants",
        owner_seat="content_strategy_lead",
        set_by="coo",
        set_on=DAY,
    )
    tree = ObjectiveTree((root, program))
    assert tree.lineage_violations() == ()
    assert tree.root_of("prog-shorts-hooks") is root
    assert tree.envelope_for("prog-shorts-hooks") is root.envelope


def test_an_orphan_program_is_reported():
    program = Objective(
        objective_id="prog-orphan",
        level=ObjectiveLevel.PROGRAM,
        title="A program with no objective",
        owner_seat="coo",
        set_by="coo",
        set_on=DAY,
        parent_id="obj-that-does-not-exist",
        parent_intent="0" * 16,
    )
    problems = ObjectiveTree((program,)).lineage_violations()
    assert any("traces back to no CEO objective" in item for item in problems)


def _plan(envelope: PlanningEnvelope, **overrides) -> ExecutivePlan:
    fields = {
        "plan_id": "plan-under-test",
        "objective_id": envelope.objective_id,
        "planned_by": "coo",
        "planned_on": DAY,
        "envelope_fingerprint": envelope.fingerprint(),
        "departments": ("engineering",),
        "actions": (ActionType.APPROVE_CODE_CHANGE,),
        "estimated_spend": usd("20.00"),
        "max_risk": Risk.LOW,
        "completion_by": dt.date(2026, 11, 30),
    }
    fields.update(overrides)
    return ExecutivePlan(**fields)


def test_a_plan_inside_the_envelope_has_no_violations():
    envelope = _envelope()
    assert envelope_violations(_plan(envelope), envelope) == ()


def test_a_plan_that_overspends_the_envelope_is_a_violation():
    envelope = _envelope()
    problems = envelope_violations(_plan(envelope, estimated_spend=usd("80.00")), envelope)
    assert any("against an envelope budget" in item for item in problems)


def test_a_plan_using_a_forbidden_action_or_department_is_a_violation():
    envelope = _envelope()
    problems = envelope_violations(
        _plan(
            envelope,
            departments=("finance",),
            actions=(ActionType.PUBLISH_PUBLIC_VIDEO,),
        ),
        envelope,
    )
    assert any("does not allow" in item for item in problems)
    assert any("forbids" in item for item in problems)


def test_a_plan_written_against_an_older_envelope_is_a_violation():
    envelope = _envelope()
    plan = _plan(envelope)
    widened = _envelope(budget=usd("500.00"))
    problems = envelope_violations(plan, widened)
    assert any("replan against the current envelope" in item for item in problems)


def test_an_envelope_that_names_no_department_is_refused():
    with pytest.raises(DelegationError) as exc:
        _envelope(allowed_departments=())
    assert "not an envelope" in str(exc.value)


# --- 11. management by exception ------------------------------------------


def test_routine_success_raises_no_exception():
    """The test that keeps the exception set honest. It must never need a change."""
    decision = evaluate(_request(amount=usd("1.00"), budget_scope="prog-budget"), _toy_policy())
    report = classify(decision, ExceptionContext(failed_attempts=0, attempt_ceiling=1))
    assert decision.decision is Decision.APPROVED
    assert report.exceptions == ()
    assert not report.ceo_required


def test_a_reserved_action_raises_the_reserved_class():
    decision = evaluate(_request(action=ActionType.PUBLISH_PUBLIC_VIDEO), _toy_policy())
    assert ExceptionClass.RESERVED_ACTION in classify(decision).classes


def test_a_budget_breach_and_a_risk_breach_each_raise_their_own_class():
    budget = classify(
        evaluate(
            _request(
                action=ActionType.APPROVE_OPERATING_SPEND,
                amount=usd("40.00"),
                budget_scope="dept-budget",
            ),
            _toy_policy(),
        )
    )
    assert ExceptionClass.BUDGET_CEILING_EXCEEDED in budget.classes
    risk = classify(evaluate(_request(risk=Risk.CRITICAL), _toy_policy()))
    assert ExceptionClass.RISK_CEILING_EXCEEDED in risk.classes


def test_exhausted_attempts_raise_repeated_execution_failure():
    decision = evaluate(_request(), _toy_policy())
    report = classify(decision, ExceptionContext(failed_attempts=1, attempt_ceiling=1))
    assert ExceptionClass.REPEATED_EXECUTION_FAILURE in report.classes


def test_an_unresolved_dispute_needs_its_detail():
    with pytest.raises(DelegationError):
        ExceptionContext(reviewer_disputed=True)
    ctx = ExceptionContext(
        reviewer_disputed=True,
        dispute_detail="the reviewer says the round trip crashes and the manager disagrees",
    )
    report = classify(evaluate(_request(), _toy_policy()), ctx)
    assert ExceptionClass.UNRESOLVED_DISPUTE in report.classes


def test_an_envelope_breach_and_a_governance_event_each_raise_their_class():
    ctx = ExceptionContext(
        envelope_violations=("the plan estimates 80 USD against an envelope of 50 USD",),
        security_events=("a credential-shaped string reached a briefing",),
        protected_surface_changed=True,
    )
    report = classify(evaluate(_request(), _toy_policy()), ctx)
    assert ExceptionClass.ENVELOPE_BREACH in report.classes
    assert ExceptionClass.SECURITY_OR_GOVERNANCE_EVENT in report.classes


def test_an_architecture_action_is_an_exception_whatever_its_risk():
    decision = evaluate(
        _request(action=ActionType.APPROVE_NEW_DEPENDENCY, risk=Risk.LOW), _toy_policy()
    )
    assert ExceptionClass.MAJOR_ARCHITECTURE_DECISION in classify(decision).classes


def test_a_vacancy_is_reported_as_its_own_class_and_not_as_a_budget_problem():
    hierarchy = Hierarchy(
        seats=(
            Seat(seat_id=CEO_SEAT, kind=SeatKind.CEO, title="CEO", reports_to=""),
            Seat(
                seat_id="exec",
                kind=SeatKind.EXECUTIVE,
                title="E",
                reports_to=CEO_SEAT,
                employee="",
                departments=("engineering",),
            ),
            Seat(
                seat_id="manager",
                kind=SeatKind.DEPARTMENT_MANAGEMENT,
                title="M",
                reports_to="exec",
                employee="",
                departments=("engineering",),
            ),
            Seat(
                seat_id="worker",
                kind=SeatKind.WORKER,
                title="W",
                reports_to="manager",
                employee="a_worker",
                departments=("engineering",),
            ),
        ),
        org_registry=_registry(
            a_worker={"state": "active", "department": "engineering", "manager": "a_manager"}
        ),
        permissions=_permissions(),
    )
    decision = evaluate(_request(), _toy_policy(hierarchy=hierarchy))
    assert decision.ceo_required
    assert ExceptionClass.VACANT_AUTHORITY in classify(decision).classes


def test_exceptions_are_ordered_worst_first_and_deduplicated():
    ctx = ExceptionContext(
        security_events=("one event", "one event"),
        envelope_violations=("one breach",),
    )
    report = classify(evaluate(_request(risk=Risk.CRITICAL), _toy_policy()), ctx)
    severities = [item.severity for item in report.exceptions]
    assert severities == sorted(severities)
    details = [(item.exception_class, item.detail) for item in report.exceptions]
    assert len(details) == len(set(details))


# --- 12. the decision record and the append-only store --------------------


def _record(**overrides) -> ExecutiveDecisionRecord:
    policy = _toy_policy()
    request = _request(objective_id="obj-grow-shorts", work_order_id="wo-something")
    decision = evaluate(request, policy)
    return record_decision(
        request,
        decision,
        decision_id=overrides.pop("decision_id", "dec-under-test"),
        recorded_on=DAY,
        policy_version=policy.version,
        exceptions=classify(decision),
        **overrides,
    )


def test_a_record_carries_the_policy_fingerprint_it_was_decided_against():
    record = _record()
    assert record.policy_fingerprint == _toy_policy().fingerprint()
    assert record.approving_role == "manager"
    assert record.requesting_role == "worker"


def test_a_record_cannot_claim_authority_or_leave_shadow():
    record = _record()
    fields = record.to_dict()
    assert fields["shadow"] is True and fields["authorizes_action"] is False
    with pytest.raises(AuthorityViolation):
        ExecutiveDecisionRecord.from_mapping({**fields, "authorizes_action": True})
    with pytest.raises(ShadowModeViolation):
        ExecutiveDecisionRecord.from_mapping({**fields, "shadow": False})


def test_a_record_cannot_show_a_seat_approving_its_own_request():
    fields = _record().to_dict()
    with pytest.raises(AuthorityViolation) as exc:
        ExecutiveDecisionRecord.from_mapping({**fields, "approving_role": "worker"})
    assert "does not approve its own request" in str(exc.value)


def test_a_rejected_request_is_never_attributed_to_the_seat_that_raised_it():
    policy = _toy_policy()
    request = _request(action=ActionType.APPROVE_DEPLOYMENT)
    decision = evaluate(request, policy)
    record = record_decision(
        request,
        decision,
        decision_id="dec-rejected",
        recorded_on=DAY,
        policy_version=policy.version,
    )
    assert decision.decision is Decision.REJECTED
    assert record.approving_role != record.requesting_role
    # It is attributed to the seat the chain finally reached, which is the CEO
    # for an action no seat holds — not to whichever seat sorts last.
    assert record.approving_role == CEO_SEAT
    assert record.escalation_target == CEO_SEAT


def test_the_considered_chain_keeps_its_order():
    """`considered` is a sequence, not a set.

    Sorting it would put `ceo` first and make "the last seat considered" mean
    the alphabetically last one, which is what `record_decision` reads to
    attribute a rejected request.
    """
    decision = evaluate(_request(), _toy_policy())
    assert decision.considered == ("worker", "manager", "exec", CEO_SEAT)
    assert decision.considered[-1] == CEO_SEAT
    with pytest.raises(DelegationError):
        AuthorityDecision(
            request_id="req-under-test",
            decision=Decision.ESCALATE,
            actor=CEO_SEAT,
            authority_source=POLICY_VERSION,
            action=ActionType.APPROVE_CODE_CHANGE,
            risk=Risk.LOW,
            escalation_required=True,
            ceo_required=True,
            reason="a chain that revisits a seat",
            considered=("worker", "manager", "worker"),
        )


def test_a_record_with_an_unknown_field_is_refused():
    with pytest.raises(DelegationError) as exc:
        ExecutiveDecisionRecord.from_mapping({**_record().to_dict(), "sneaky": 1})
    assert "unknown field" in str(exc.value)


def test_a_record_round_trips_through_its_own_mapping():
    record = _record()
    assert ExecutiveDecisionRecord.from_mapping(record.to_dict()) == record


def test_the_store_appends_and_never_replaces(tmp_path):
    store = DelegationStore(tmp_path)
    first = store.append_decision(_record(decision_id="dec-one"))
    second = store.append_decision(_record(decision_id="dec-two"))
    assert first.sequence == 1 and second.sequence == 2
    stored = store.decisions("obj-grow-shorts")
    assert [item.decision_id for item in stored] == ["dec-one", "dec-two"]


def test_a_decision_with_no_objective_lands_where_it_can_be_seen(tmp_path):
    policy = _toy_policy()
    request = _request()  # no objective_id
    decision = evaluate(request, policy)
    record = record_decision(
        request,
        decision,
        decision_id="dec-loose",
        recorded_on=DAY,
        policy_version=policy.version,
    )
    store = DelegationStore(tmp_path)
    pointer = store.append_decision(record)
    assert "unattributed" in pointer.record_ref
    assert store.objective_ids() == ("unattributed",)


def test_the_store_reports_a_contradiction_rather_than_repairing_it(tmp_path):
    store = DelegationStore(tmp_path)
    store.append_decision(_record(decision_id="dec-one"))
    # Write a contradicting record straight into the directory, the way a
    # foreign tool or an older version would.
    directory = tmp_path / "delegation" / "decisions"
    group = next(directory.iterdir())
    fields = _record(decision_id="dec-one").to_dict()
    fields["reason"] = "a different reason under the same id"
    (group / "000002.json").write_text(json.dumps(fields), encoding="utf-8")
    problems = store.integrity()
    assert any("appears twice with different contents" in item for item in problems)


def test_the_store_refuses_a_malformed_record(tmp_path):
    store = DelegationStore(tmp_path)
    store.append_decision(_record())
    group = next((tmp_path / "delegation" / "decisions").iterdir())
    (group / "000002.json").write_text("[]", encoding="utf-8")
    with pytest.raises(DelegationStoreError):
        store.decisions("obj-grow-shorts")


def test_the_store_needs_an_explicit_state_directory():
    with pytest.raises(DelegationStoreError):
        DelegationStore("   ")


def test_an_objective_and_a_plan_round_trip_through_the_store(tmp_path):
    store = DelegationStore(tmp_path)
    root = _root()
    program = decompose(
        root,
        objective_id="prog-shorts-hooks",
        title="Test opening-hook variants",
        owner_seat="content_strategy_lead",
        set_by="coo",
        set_on=DAY,
    )
    store.append_objective(root)
    store.append_objective(program)
    stored = store.objectives(root.objective_id)
    assert {item.objective_id for item in stored} == {
        root.objective_id,
        program.objective_id,
    }
    assert ObjectiveTree(stored).lineage_violations() == ()

    plan = _plan(_envelope())
    store.append_plan(plan)
    back = store.plans(plan.objective_id)
    assert len(back) == 1
    # The cost survives the round trip: a plan that forgot what it estimated
    # could not be checked against its envelope on the way back in.
    assert back[0].estimated_spend == plan.estimated_spend
    assert back[0].fingerprint() == plan.fingerprint()


# --- 13. the CEO brief ----------------------------------------------------


def test_the_brief_counts_what_stayed_below_the_ceo():
    policy = _toy_policy()
    decisions = [
        evaluate(_request(request_id="req-one"), policy),
        evaluate(_request(request_id="req-two", risk=Risk.MEDIUM), policy),
        evaluate(_request(request_id="req-three", risk=Risk.CRITICAL), policy),
    ]
    reports = [classify(item) for item in decisions]
    brief = build_brief(
        _root(),
        status="On track",
        decisions=decisions,
        reports=reports,
        work_completed=("12 experiments", "7 videos"),
        best_result="Opening-hook variant B, +8.2% retention",
        spend=usd("18.42"),
        next_action="Continue the winning format for two weeks",
        as_of=DAY,
    )
    assert brief.decisions_handled_internally == 2
    assert brief.ceo_escalations
    text = brief.render()
    assert "OBJECTIVE" in text and "CEO ESCALATIONS" in text
    # Money normalises its own text; the line is "<spend> / <budget>".
    assert brief.spend_line == f"{usd('18.42')} / {usd('50.00')}"
    assert brief.spend_line in text


def test_a_brief_with_nothing_measured_says_unknown_and_not_zero():
    brief = build_brief(_root(), status="Just started", spend=None)
    assert "unknown" in brief.spend_line
    assert "0.00" not in brief.spend_line


def test_a_portfolio_total_containing_an_unknown_is_unknown():
    known = build_brief(_root("obj-one"), status="On track", spend=usd("5.00"))
    unknown = build_brief(_root("obj-two"), status="On track", spend=None)
    assert portfolio_spend((known, known), "USD") == usd("10.00")
    assert portfolio_spend((known, unknown), "USD") is None


def test_a_clean_objective_renders_zero_escalations():
    brief = build_brief(_root(), status="On track", spend=usd("1.00"))
    assert "CEO ESCALATIONS\n  0" in brief.render()


# --- 14. shadow mode, and the canonical CEO gate --------------------------


def test_shadow_mode_is_enforced_against_the_canonical_modules():
    report = verify_shadow_mode()
    assert report.enforced, report.render()
    assert len(report.checks) == 5
    assert assert_shadow_mode().enforced


def test_the_canonical_ceo_decision_still_names_a_human():
    from company.engineering.common import assert_named_person
    from company.engineering.errors import EngineeringError

    with pytest.raises(EngineeringError):
        assert_named_person("company_os", "decided_by")
    assert assert_named_person("the CEO", "decided_by") == "the CEO"


def test_the_canonical_ceo_approval_still_carries_no_merge_authority():
    from company.engineering.decision import CEODecision, CEOVerdict
    from company.engineering.errors import EngineeringError
    from company.engineering.lifecycle import JobState

    approved = CEODecision(
        decision_id="dec-shadow-check",
        work_order_id="wo-shadow-check",
        work_order_fingerprint="0" * 16,
        verdict=CEOVerdict.APPROVE,
        decided_by="the CEO",
        decided_on=DAY,
        rationale="a test that constructs a decision and stores nothing",
        reviewed_state=JobState.READY_FOR_APPROVAL,
    )
    assert approved.authorizes_merge is False
    with pytest.raises(EngineeringError):
        CEODecision(
            decision_id="dec-shadow-check",
            work_order_id="wo-shadow-check",
            work_order_fingerprint="0" * 16,
            verdict=CEOVerdict.APPROVE,
            decided_by="the CEO",
            decided_on=DAY,
            rationale="a test",
            reviewed_state=JobState.READY_FOR_APPROVAL,
            authorizes_merge=True,
        )


def test_a_policy_cannot_be_constructed_in_enforcing_mode():
    with pytest.raises(ShadowModeViolation) as exc:
        _toy_policy(mode=DelegationMode.ENFORCING)
    assert "CEO-reserved" in str(exc.value)


def test_the_shipped_policy_file_declares_shadow_mode():
    text = POLICY_FILE.read_text(encoding="utf-8")
    assert "mode: shadow" in text
    assert "mode: enforcing" not in text


def test_no_delegation_decision_can_move_an_engineering_job():
    """Shadow mode does not authorize a merge, a deploy or a state change."""
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(PACKAGE.glob("*.py"))
    )
    for forbidden in ("git merge", "git push", "git checkout", "advance(", "apply_to("):
        assert forbidden not in source, forbidden


# --- 15. the historical replay --------------------------------------------


def test_the_replay_agrees_with_the_expected_direction_on_every_scenario(policy):
    results = replay(policy)
    summary = summarise(results)
    assert summary["scenarios"] == 5
    assert summary["disagreements"] == [], summary["disagreements"]


def test_routine_successful_work_does_not_need_the_ceo(policy):
    by_id = {item.scenario.scenario_id: item for item in replay(policy)}
    for scenario_id in ("dogfood-2", "burnin-correction", "burnin-job-b"):
        item = by_id[scenario_id]
        assert item.decision.decision is Decision.APPROVED, scenario_id
        assert not item.decision.ceo_required, scenario_id
        assert item.exceptions.exceptions == (), scenario_id


def test_the_reviewer_finding_escalates_because_one_employee_holds_both_seats(policy):
    """Job A: the architect reviewed it and is the only seat that could approve it."""
    item = next(x for x in replay(policy) if x.scenario.scenario_id == "burnin-job-a")
    assert item.decision.ceo_required
    assert any(
        step.insufficiency is Insufficiency.SELF_APPROVAL for step in item.decision.chain
    )
    assert ExceptionClass.REPEATED_EXECUTION_FAILURE in item.exceptions.classes


def test_stopping_work_on_an_invalid_premise_never_reaches_the_ceo(policy):
    item = next(x for x in replay(policy) if x.scenario.scenario_id == "burnin-job-c")
    assert item.decision.decision is Decision.APPROVED
    assert not item.decision.ceo_required
    assert item.scenario.actual_ceo_involved is False


def test_the_transcribed_costs_match_the_totals_the_reports_state():
    by_id = {item.scenario_id: item for item in SCENARIOS}
    for scenario_id, reported in REPORTED_TOTALS.items():
        amount = by_id[scenario_id].request.amount
        assert amount is not None, scenario_id
        assert amount.amount == Decimal(reported), scenario_id


def test_the_replay_reads_no_state_directory_and_writes_nothing(tmp_path, policy):
    before = sorted(tmp_path.rglob("*"))
    replay(policy)
    assert sorted(tmp_path.rglob("*")) == before


def test_every_scenario_names_the_report_it_was_transcribed_from():
    for scenario in SCENARIOS:
        assert scenario.evidence, scenario.scenario_id
        assert all(item.startswith("docs/") for item in scenario.evidence)


# --- 16. the package holds none of the capabilities the gate forbids ------


def _package_trees():
    for path in sorted(PACKAGE.glob("*.py")):
        yield path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_no_publishing_or_process_capability_is_introduced():
    forbidden_modules = {
        "subprocess", "multiprocessing", "pty", "socket", "http", "urllib",
        "requests", "httpx", "ftplib", "smtplib", "asyncio", "ssl",
    }
    forbidden_calls = {
        "system", "popen", "fork", "forkpty", "execv", "execve", "execl",
        "spawnv", "spawnl", "posix_spawn",
    }
    for path, tree in _package_trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden_modules, (
                        f"{path.name}:{node.lineno} imports {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden_modules, (
                    f"{path.name}:{node.lineno} imports from {node.module}"
                )
            elif isinstance(node, ast.Call):
                name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
                assert name not in forbidden_calls, f"{path.name}:{node.lineno} calls {name}"


def test_no_credential_is_read_by_this_package():
    for path, tree in _package_trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in ("environ", "getenv"):
                raise AssertionError(f"{path.name}:{node.lineno} reads the environment")
            if isinstance(node, ast.Call):
                name = getattr(node.func, "attr", None)
                assert name not in ("getenv", "expandvars"), f"{path.name}:{node.lineno}"


def test_the_package_deletes_nothing():
    forbidden = {"removedirs", "rmdir", "rmtree", "unlink", "truncate"}
    for path, tree in _package_trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
                assert name not in forbidden, f"{path.name}:{node.lineno} calls {name}"


def test_the_package_names_no_production_path():
    production = ("sloped/", "race/", "godot/", "rendering/", "tools/", "exports/")
    for path, tree in _package_trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for root in production:
                    assert not node.value.startswith(root), (
                        f"{path.name}:{node.lineno} names {node.value!r}"
                    )


def test_the_package_does_not_import_production():
    production_roots = {
        "sloped", "race", "godot", "rendering", "marble3d", "entities", "engine",
        "production", "replay", "powers", "modes", "audio", "evaluation", "tools",
    }
    for path, tree in _package_trees():
        for node in ast.walk(tree):
            root = ""
            if isinstance(node, ast.Import):
                root = node.names[0].name.split(".")[0]
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".")[0]
            assert root not in production_roots, f"{path.name}:{node.lineno}"

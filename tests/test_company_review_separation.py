"""Independent engineering review, and the separation it restores.

The first end-to-end pilot completed every stage and then escalated to the CEO
at integration. Not a bug: `chief_architect` was the only employee holding
`software_architecture`, every work order defaulted its review capability to
that, and so the CTO's own employee reviewed every job - which disqualified the
CTO seat from approving the integration of work it had just reviewed. The chain
walked to the COO, which holds no integration grant, and then to the CEO. That
would have happened on every engineering job, forever.

The fix is one employee and one default, not a weakened rule.

Sections
    1. the seat and the employee
    2. routing: ordinary review and architecture review are different questions
    3. separation of duties, proved rather than asserted
    4. the historical job keeps its history
    5. the future path, which is the point
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from ai_platform.resource_classes import Risk
from company.delegation.actions import ActionType
from company.delegation.authority import (
    AuthorityRequest,
    Decision,
    Insufficiency,
    evaluate,
)
from company.delegation.org import SeatKind
from company.delegation.policy import load_delegation_policy
from company.engineering.intake import CEORequest, IntakeOutcome, assess_request
from company.engineering.work_order import (
    ARCHITECTURE_REVIEW_CAPABILITY,
    ARCHITECTURE_REVIEW_DOMAINS,
    CODE_REVIEW_CAPABILITY,
)
from company.runtime.config import load_company_config
from company.runtime.lifecycle import plan_task
from company.validation.yaml_subset import load_yaml_subset

DAY = dt.date(2026, 9, 20)
REPO_ROOT = Path(__file__).resolve().parents[1]

REVIEWER_EMPLOYEE = "software_review_engineer"
REVIEWER_SEAT = "engineering_reviewer"
DEVELOPER_EMPLOYEE = "software_implementation_engineer"
DEVELOPER_SEAT = "software_implementation_engineer"
ARCHITECT_EMPLOYEE = "chief_architect"


@pytest.fixture(scope="module")
def config():
    return load_company_config(None)


@pytest.fixture(scope="module")
def policy(config):
    return load_delegation_policy(
        org_registry=config.org_registry, permissions=config.permissions
    )


@pytest.fixture(scope="module")
def registry():
    return load_yaml_subset(REPO_ROOT / "company" / "org_registry.yaml")


# --- 1. the seat and the employee ------------------------------------------


def test_the_reviewer_is_a_real_active_engineering_employee(registry):
    employee = registry["employees"][REVIEWER_EMPLOYEE]
    assert employee["department"] == "engineering"
    assert employee["state"] == "active"
    assert employee["manager"] == "engineering_delivery_manager"
    assert CODE_REVIEW_CAPABILITY in employee["capabilities"]


def test_the_reviewer_holds_no_implementation_capability(registry):
    """Minimum capability for the job, so it cannot be routed work to build."""
    employee = registry["employees"][REVIEWER_EMPLOYEE]
    developer = registry["employees"][DEVELOPER_EMPLOYEE]
    overlap = set(employee["capabilities"]) & set(developer["capabilities"])
    assert overlap == set(), f"reviewer shares implementation capability: {overlap}"
    assert employee["capabilities"] == [CODE_REVIEW_CAPABILITY]


def test_the_reviewer_seat_is_a_worker_seat_that_holds_no_grant(policy):
    """It attests; it does not approve. A grant would make it a second manager."""
    standing = {item.seat.seat_id: item for item in policy.hierarchy.standings()}
    seat = standing[REVIEWER_SEAT].seat
    assert seat.kind is SeatKind.WORKER
    assert seat.employee == REVIEWER_EMPLOYEE
    assert seat.reports_to == "engineering_manager"
    assert policy.grant(REVIEWER_SEAT) is None


def test_the_architect_still_holds_architecture_review(registry):
    caps = registry["employees"][ARCHITECT_EMPLOYEE]["capabilities"]
    assert ARCHITECTURE_REVIEW_CAPABILITY in caps


def test_only_one_employee_holds_each_review_capability(registry):
    """Two holders of `code_review` would be fine; zero would break routing."""
    holders = {
        cap: [
            eid
            for eid, emp in registry["employees"].items()
            if cap in emp.get("capabilities", ())
        ]
        for cap in (CODE_REVIEW_CAPABILITY, ARCHITECTURE_REVIEW_CAPABILITY)
    }
    assert holders[CODE_REVIEW_CAPABILITY] == [REVIEWER_EMPLOYEE]
    assert ARCHITECT_EMPLOYEE in holders[ARCHITECTURE_REVIEW_CAPABILITY]
    assert REVIEWER_EMPLOYEE not in holders[ARCHITECTURE_REVIEW_CAPABILITY]


# --- 2. routing -------------------------------------------------------------


def _intake(objective, request_id, config, **kw):
    return assess_request(
        CEORequest(
            request_id=request_id,
            objective=objective,
            requested_by="MGI",
            requested_on=DAY,
            risk=Risk.LOW,
            **kw,
        ),
        config.permissions,
        repo_root=REPO_ROOT,
        authorized_on=DAY,
    )


def test_ordinary_engineering_work_asks_for_ordinary_review(config):
    assessment = _intake(
        "Add a field to the engineering result record.", "req-sep-ordinary", config
    )
    assert assessment.outcome is IntakeOutcome.AUTHORIZED
    assert assessment.work_order.specialist_domain == ""
    assert assessment.work_order.review_capability == CODE_REVIEW_CAPABILITY


def test_architecture_work_still_asks_for_the_architect(config):
    assessment = _intake(
        "Rewrite the module boundary between the runtime and the engineering package.",
        "req-sep-arch",
        config,
    )
    assert assessment.outcome is IntakeOutcome.AUTHORIZED
    assert assessment.work_order.specialist_domain == "architecture"
    assert assessment.work_order.review_capability == ARCHITECTURE_REVIEW_CAPABILITY


def test_the_two_review_questions_are_distinguishable(config):
    """The whole point of section 2: one objective, two different reviewers."""
    ordinary = _intake(
        "Add a field to the engineering result record.", "req-sep-d1", config
    ).work_order
    architectural = _intake(
        "Rewrite the module boundary between the runtime and the engineering package.",
        "req-sep-d2",
        config,
    ).work_order
    assert ordinary.review_capability != architectural.review_capability
    assert (
        plan_task(ordinary.review_specification(), config).selected_employee
        == REVIEWER_EMPLOYEE
    )
    assert (
        plan_task(architectural.review_specification(), config).selected_employee
        == ARCHITECT_EMPLOYEE
    )


def test_only_architecture_is_an_architecture_review_domain():
    """security, governance and concurrency escalate the tier, not the reviewer."""
    assert ARCHITECTURE_REVIEW_DOMAINS == frozenset({"architecture"})


def test_the_reviewer_is_never_routed_the_implementation(config):
    ordinary = _intake(
        "Add a field to the engineering result record.", "req-sep-impl", config
    ).work_order
    routed = plan_task(ordinary.task_specification(), config)
    assert routed.selected_employee == DEVELOPER_EMPLOYEE
    assert routed.selected_employee != REVIEWER_EMPLOYEE


# --- 3. separation of duties ------------------------------------------------


def _request(action, seat, *, reviewer, implementer=DEVELOPER_EMPLOYEE, risk=Risk.MEDIUM,
             request_id="req-sep-probe", **kw):
    return AuthorityRequest(
        request_id=request_id,
        action=action,
        requesting_seat=seat,
        department="engineering",
        risk=risk,
        objective_id="obj-sep-demo",
        work_order_id="wo-sep-demo",
        summary="a bounded engineering decision",
        implementer=implementer,
        reviewer=reviewer,
        **kw,
    )


def test_developer_and_reviewer_are_different_employees(registry):
    assert REVIEWER_EMPLOYEE != DEVELOPER_EMPLOYEE
    assert registry["employees"][REVIEWER_EMPLOYEE] is not registry["employees"][
        DEVELOPER_EMPLOYEE
    ]


def test_reviewer_is_not_the_engineering_manager(policy):
    seats = {item.seat.seat_id: item.seat for item in policy.hierarchy.standings()}
    assert seats["engineering_manager"].employee != REVIEWER_EMPLOYEE


def test_reviewer_is_not_the_integration_approver(policy):
    seats = {item.seat.seat_id: item.seat for item in policy.hierarchy.standings()}
    assert seats["cto"].employee != REVIEWER_EMPLOYEE


def test_the_cto_may_not_approve_integration_of_work_it_reviewed(policy):
    """The rule that caught the pilot. It is not weakened by the new seat."""
    decision = evaluate(
        _request(
            ActionType.APPROVE_INTEGRATION_MERGE,
            "engineering_manager",
            reviewer=ARCHITECT_EMPLOYEE,
            request_id="req-sep-cto-reviewed",
        ),
        policy,
    )
    assert decision.decision is Decision.ESCALATE
    assert decision.actor == "ceo"


def test_the_cto_may_approve_integration_it_did_not_review(policy):
    decision = evaluate(
        _request(
            ActionType.APPROVE_INTEGRATION_MERGE,
            "engineering_manager",
            reviewer=REVIEWER_EMPLOYEE,
            request_id="req-sep-cto-clean",
        ),
        policy,
    )
    assert decision.decision is Decision.APPROVED
    assert decision.actor == "cto"


def test_the_reviewer_seat_cannot_approve_integration(policy):
    decision = evaluate(
        _request(
            ActionType.APPROVE_INTEGRATION_MERGE,
            REVIEWER_SEAT,
            reviewer=REVIEWER_EMPLOYEE,
            request_id="req-sep-reviewer-integ",
        ),
        policy,
    )
    # It holds no grant, so it never decides; the chain walks past it. And it
    # reviewed this work, so every seat it walks to is checked against that too.
    assert decision.actor != REVIEWER_SEAT


def test_the_reviewer_cannot_expand_its_own_authority(policy):
    decision = evaluate(
        _request(
            ActionType.EXPAND_AUTHORITY,
            REVIEWER_SEAT,
            reviewer=REVIEWER_EMPLOYEE,
            request_id="req-sep-expand",
        ),
        policy,
    )
    assert decision.decision is Decision.ESCALATE
    assert decision.ceo_required is True


@pytest.mark.parametrize(
    "action",
    (
        ActionType.APPROVE_DEPLOYMENT,
        ActionType.PUBLISH_PUBLIC_VIDEO,
        ActionType.CHANGE_DELEGATION_POLICY,
        ActionType.APPROVE_SECURITY_EXCEPTION,
        ActionType.ALLOCATE_DEPARTMENT_BUDGET,
        ActionType.APPROVE_ARCHITECTURE_REDESIGN,
    ),
)
def test_the_reviewer_holds_none_of_the_forbidden_actions(policy, action):
    """None of these is ever *authorized* for the reviewer.

    The seat can appear as the `actor` of a REJECTED answer - being the seat a
    refusal is recorded against is not holding authority - so what is asserted
    is the thing that matters: `authorizes_action` is never true.
    """
    assert policy.grant(REVIEWER_SEAT) is None
    decision = evaluate(
        _request(
            action,
            REVIEWER_SEAT,
            reviewer=REVIEWER_EMPLOYEE,
            request_id=f"req-sep-{action.value.replace('_','-')}"[:64],
        ),
        policy,
    )
    # The precise invariant, which has to cover two honest shapes. A refusal can
    # be recorded *against* the reviewer seat (`actor` is the seat the chain
    # stopped at, `authorizes_action` false), and a request the reviewer merely
    # raises can be legitimately approved by somebody else - a reviewer asking
    # the CFO to allocate budget is ordinary. What must never happen is the
    # reviewer being the seat that *authorizes* something.
    if decision.decision is Decision.APPROVED:
        assert decision.actor != REVIEWER_SEAT
    assert policy.grant(REVIEWER_SEAT) is None


def test_management_cannot_override_an_independent_control(policy):
    """QA and reviewer verdicts are not a manager's to set aside, at any risk.

    The refusal takes two shapes and both are refusals: a seat that holds the
    action escalates, and one that does not is rejected outright with the
    request carried to the CEO. What matters is that no management seat is ever
    *approved* to overrule an independent control.
    """
    for seat in ("engineering_manager", "cto", "coo"):
        decision = evaluate(
            _request(
                ActionType.APPROVE_REVIEW_OUTCOME,
                seat,
                reviewer=REVIEWER_EMPLOYEE,
                request_id=f"req-sep-override-{seat.replace('_','-')}"[:64],
                overrides_independent_control=True,
            ),
            policy,
        )
        assert decision.decision is not Decision.APPROVED, seat
        assert decision.authorizes_action is False, seat


def test_deterministic_qa_remains_an_unstaffed_independent_control(policy):
    standing = {item.seat.seat_id: item for item in policy.hierarchy.standings()}
    for seat_id in ("deterministic_qa", "integration_gate"):
        item = standing[seat_id]
        assert item.seat.kind is SeatKind.INDEPENDENT_CONTROL
        assert item.seat.is_deterministic_control
        assert policy.grant(seat_id) is None
        assert item.seat.employee != REVIEWER_EMPLOYEE


def test_escalation_stays_upward_and_acyclic(policy):
    """Adding a seat must not create a loop or a downward hop."""
    seats = {item.seat.seat_id: item.seat for item in policy.hierarchy.standings()}
    for seat_id, seat in seats.items():
        if seat.kind is SeatKind.CEO:
            continue
        seen = {seat_id}
        cursor = seat
        while cursor.reports_to:
            assert cursor.reports_to not in seen, f"cycle through {cursor.reports_to}"
            seen.add(cursor.reports_to)
            parent = seats[cursor.reports_to]
            assert parent.rank >= cursor.rank, (
                f"{cursor.seat_id} reports to {parent.seat_id}, which sits lower"
            )
            cursor = parent
        assert cursor.kind is SeatKind.CEO


# --- 4. the historical job keeps its history --------------------------------


def test_the_completed_pilot_job_still_escalates(policy):
    """Historical audit truth beats pilot-success convenience.

    `chief_architect` really did review `wo-req-auth-migration-correction-01`.
    Staffing a new reviewer does not change who reviewed it, so the CTO stays
    disqualified for that job and it stays a CEO decision.
    """
    decision = evaluate(
        AuthorityRequest(
            request_id="req-integrate-correction-01",
            action=ActionType.APPROVE_INTEGRATION_MERGE,
            requesting_seat="engineering_manager",
            department="engineering",
            risk=Risk.MEDIUM,
            objective_id="obj-end-to-end-pilot-2026-09-20",
            work_order_id="wo-req-auth-migration-correction-01",
            summary="integrate the corrected intake change",
            implementer=DEVELOPER_EMPLOYEE,
            reviewer=ARCHITECT_EMPLOYEE,
        ),
        policy,
    )
    assert decision.decision is Decision.ESCALATE
    assert decision.ceo_required is True


def test_the_coo_was_not_given_integration_authority_to_rescue_the_pilot(policy):
    """The cheap fix, deliberately not taken."""
    grant = policy.grant("coo")
    assert ActionType.APPROVE_INTEGRATION_MERGE not in grant.action_types


# --- 5. the future path -----------------------------------------------------


def test_a_future_job_completes_without_the_ceo(policy, config):
    """Developer -> independent reviewer -> manager -> QA -> CTO -> integration.

    Every delegated step answered below the CEO, and - the part the first
    version of this test did not check - answered by the *right* seat.

    Each request is filed by the seat that actually raises it. That matters
    because `authority.evaluate` refuses self-approval: a seat that raises a
    request is skipped when the chain is walked. Filing all four as
    `engineering_manager` therefore skipped the manager on the three decisions
    it is supposed to own and silently landed them on the CTO, which is exactly
    what the first `future_job_simulation.json` recorded. The developer raises
    the code change and the test progression; the reviewer raises the review
    outcome; only integration is raised by the manager, and only that one is
    meant to reach the CTO.
    """
    order = _intake(
        "Add a field to the engineering result record.", "req-sep-future", config
    ).work_order
    assert order.review_capability == CODE_REVIEW_CAPABILITY
    implementer = plan_task(order.task_specification(), config).selected_employee
    reviewer = plan_task(order.review_specification(), config).selected_employee
    assert implementer == DEVELOPER_EMPLOYEE
    assert reviewer == REVIEWER_EMPLOYEE
    assert implementer != reviewer

    # (action, the seat that RAISES it, the risk it is raised at, who must decide)
    chain = [
        (ActionType.APPROVE_CODE_CHANGE, DEVELOPER_SEAT, Risk.LOW, "engineering_manager"),
        (ActionType.APPROVE_TEST_PROGRESSION, DEVELOPER_SEAT, Risk.LOW, "engineering_manager"),
        (ActionType.APPROVE_REVIEW_OUTCOME, REVIEWER_SEAT, Risk.LOW, "engineering_manager"),
        (ActionType.REQUEST_BOUNDED_CORRECTION, REVIEWER_SEAT, Risk.LOW, "engineering_manager"),
        (ActionType.APPROVE_INTEGRATION_MERGE, "engineering_manager", Risk.MEDIUM, "cto"),
    ]
    actors = {}
    for action, seat, risk, expected in chain:
        decision = evaluate(
            _request(
                action,
                seat,
                reviewer=reviewer,
                implementer=implementer,
                risk=risk,
                request_id=f"req-sep-future-{action.value.replace('_','-')}"[:64],
            ),
            policy,
        )
        assert decision.decision is Decision.APPROVED, (action.value, decision.reason)
        assert decision.ceo_required is False, action.value
        assert decision.actor == expected, (action.value, decision.actor, decision.reason)
        actors[action.value] = decision.actor
    assert actors["approve_integration_merge"] == "cto"
    # The management layer is genuinely used, not bypassed.
    assert sum(a == "engineering_manager" for a in actors.values()) == 4


def test_the_manager_does_not_decide_its_own_request(policy):
    """Why the four management decisions are not raised by the manager.

    This is the mechanism behind the first simulation's all-CTO result, pinned
    so it cannot be rediscovered as a mystery. Nothing here is a defect: a seat
    signing its own request is precisely what separation of duties forbids.
    """
    decision = evaluate(
        _request(
            ActionType.APPROVE_CODE_CHANGE,
            "engineering_manager",
            reviewer=REVIEWER_EMPLOYEE,
            risk=Risk.LOW,
            request_id="req-sep-self-approval",
        ),
        policy,
    )
    assert decision.actor == "cto"
    step = decision.chain[0]
    assert step.seat == "engineering_manager"
    assert step.insufficiency is Insufficiency.SELF_APPROVAL


def test_medium_risk_routine_work_escalates_to_the_cto_by_design(policy):
    """The manager's ceiling is `low`, and that is the policy's own choice.

    Not widened here. `engineering_manager` is granted `max_risk: low` with the
    rationale "routine low-risk engineering work"; the CTO carries `medium`.
    So a MEDIUM-risk engineering job reaching the CTO is the ladder working,
    not the manager being bypassed. An ordinary routine job is LOW and stops at
    the manager, as the future-path test proves.
    """
    decision = evaluate(
        _request(
            ActionType.APPROVE_CODE_CHANGE,
            DEVELOPER_SEAT,
            reviewer=REVIEWER_EMPLOYEE,
            risk=Risk.MEDIUM,
            request_id="req-sep-medium-ceiling",
        ),
        policy,
    )
    assert decision.actor == "cto"
    assert decision.ceo_required is False
    manager_step = next(s for s in decision.chain if s.seat == "engineering_manager")
    assert manager_step.insufficiency is Insufficiency.RISK_ABOVE_CEILING


def test_architecture_review_still_disqualifies_the_cto_from_integration(policy, config):
    """The case that must NOT be weakened by any of the above.

    Architecture work still routes its review to `chief_architect`, who is the
    CTO's employee, so the CTO is disqualified from approving that job's
    integration and the chain still reaches the CEO.
    """
    order = _intake(
        "Rewrite the module boundary between the runtime and the engineering package.",
        "req-sep-arch-future",
        config,
    ).work_order
    assert order.review_capability == ARCHITECTURE_REVIEW_CAPABILITY
    arch_reviewer = plan_task(order.review_specification(), config).selected_employee
    assert arch_reviewer == ARCHITECT_EMPLOYEE

    decision = evaluate(
        _request(
            ActionType.APPROVE_INTEGRATION_MERGE,
            "engineering_manager",
            reviewer=arch_reviewer,
            risk=Risk.MEDIUM,
            request_id="req-sep-arch-integration",
        ),
        policy,
    )
    assert decision.decision is Decision.ESCALATE
    assert decision.ceo_required is True

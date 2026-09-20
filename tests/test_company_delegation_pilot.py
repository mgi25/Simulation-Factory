"""The bounded live-delegation pilot: what it permits, and what it must refuse.

The sections follow the risk, not the module layout. Sections 1-3 establish
that nothing is live by default; 4 holds the floor rule, which is the single
property that separates a pilot from a bypass; 5-9 test each gate; 10-12 cover
the record, the correction loop and the report; 13 replays history; 14 asserts
against the package source that this code cannot merge, deploy or publish.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from ai_platform.resource_classes import Risk
from company.delegation.actions import RESERVED_HERE, ActionType, reserved_action_types
from company.delegation.authority import AuthorityRequest, Decision, evaluate
from company.delegation.errors import (
    DelegationError,
    PilotBoundaryViolation,
)
from company.delegation.objectives import PlanningEnvelope
from company.delegation.policy import DelegationMode, load_delegation_policy
from company.delegation.pilot import (
    CTO_LIVE_ACTIONS,
    ENGINEERING_MANAGER_LIVE_ACTIONS,
    PILOT_FORBIDDEN_ACTIONS,
    PILOT_RISK_CEILING,
    PILOT_SEATS,
    LivePilotDecision,
    PilotActivation,
    PilotGateId,
    PilotMode,
    PilotRequest,
    evaluate_live,
)
from company.delegation.pilot_correction import (
    CorrectionLedger,
    authorize_correction,
    correction_ceiling,
)
from company.delegation.pilot_envelope import PilotEnvelope
from company.delegation.pilot_integration import (
    PILOT_TARGET,
    PROTECTED_REFS,
    IntegrationTarget,
    TargetKind,
)
from company.delegation.pilot_record import (
    LivePilotDecisionRecord,
    record_live_decision,
)
from company.delegation.pilot_report import PilotRunReport, simulation_report
from company.delegation.pilot_simulation import (
    ENGINEERING_ACTIVATION,
    ENGINEERING_ENVELOPE,
    ENGINEERING_OBJECTIVE,
    EXPIRED_ACTIVATION,
    PILOT_DAY,
    PILOT_PROBES,
    replay_live,
    replay_probes,
    replay_shadow_default,
    run_full_simulation,
)
from company.delegation.shadow import verify_shadow_mode
from company.efficiency.profile import PROFILES, ResourceProfileName
from company.finance.money import Money
from company.runtime.config import load_company_config
from company.delegation.scenarios import CONTROL_SCENARIOS, SCENARIOS


DAY = PILOT_DAY
USD = "USD"


def _usd(text: str) -> Money:
    return Money(text, USD)


@pytest.fixture(scope="module")
def policy():
    config = load_company_config()
    return load_delegation_policy(
        org_registry=config.org_registry, permissions=config.permissions
    )


@pytest.fixture
def envelope() -> PilotEnvelope:
    plan = PlanningEnvelope(
        objective_id=ENGINEERING_OBJECTIVE,
        budget=_usd("18.00"),
        budget_scope="engineering-operations",
        risk_ceiling=Risk.LOW,
        deadline=dt.date(2026, 12, 31),
        allowed_departments=("engineering",),
        success_metrics=("suite green",),
    )
    return PilotEnvelope(
        envelope_id="test-envelope-engineering",
        objective="Routine engineering delivery",
        plan=plan,
        allowed_actions=tuple(
            sorted(
                ENGINEERING_MANAGER_LIVE_ACTIONS | CTO_LIVE_ACTIONS,
                key=lambda item: item.value,
            )
        ),
        integration_target=PILOT_TARGET,
        expires_on=dt.date(2026, 12, 31),
        authorized_by="MGI (CEO)",
        max_corrections_per_work_order=1,
    )


@pytest.fixture
def activation(envelope: PilotEnvelope) -> PilotActivation:
    return PilotActivation(
        activation_id="test-activation-engineering",
        envelope=envelope,
        activated_by="MGI (CEO)",
        activated_on=DAY,
        acknowledged_live=True,
        policy_version="delegation_policy_v1",
    )


def _request(
    request_id: str = "test-req-code-change",
    action: ActionType = ActionType.APPROVE_CODE_CHANGE,
    *,
    seat: str = "software_implementation_engineer",
    risk: Risk = Risk.LOW,
    department: str = "engineering",
    objective_id: str = ENGINEERING_OBJECTIVE,
    work_order_id: str = "wo-test-change",
    amount: Money | None = None,
    implementer: str = "software_implementation_engineer",
    reviewer: str = "chief_architect",
    overrides: bool = False,
) -> AuthorityRequest:
    return AuthorityRequest(
        request_id=request_id,
        action=action,
        requesting_seat=seat,
        department=department,
        risk=risk,
        objective_id=objective_id,
        work_order_id=work_order_id,
        budget_scope="engineering-operations",
        amount=amount if amount is not None else _usd("2.00"),
        summary="A routine low-risk engineering change",
        implementer=implementer,
        reviewer=reviewer,
        overrides_independent_control=overrides,
    )


def _pilot(request: AuthorityRequest, **kwargs) -> PilotRequest:
    kwargs.setdefault("review_passed", True)
    kwargs.setdefault("qa_passed", True)
    kwargs.setdefault("as_of", DAY)
    return PilotRequest(request=request, **kwargs)


# ---------------------------------------------------------------- 1. default


class TestShadowRemainsTheDefault:
    """Nothing is live because the code exists. Phase 2."""

    def test_the_canonical_policy_is_still_in_shadow_mode(self, policy):
        assert policy.mode is DelegationMode.SHADOW

    def test_the_canonical_policy_still_refuses_to_leave_shadow(self, policy):
        report = verify_shadow_mode()
        assert report.enforced, report.render()

    def test_evaluate_live_without_an_activation_authorizes_nothing(self, policy):
        live = evaluate_live(_pilot(_request()), policy)
        assert live.mode is PilotMode.SHADOW
        assert live.authorizes_action is False

    def test_the_unactivated_answer_is_the_shadow_answer(self, policy):
        request = _request()
        shadow = evaluate(request, policy)
        live = evaluate_live(_pilot(request), policy)
        assert live.decision is shadow.decision
        assert live.actor == shadow.actor
        assert live.ceo_required == shadow.ceo_required

    def test_every_historical_scenario_authorizes_nothing_without_activation(
        self, policy
    ):
        results = replay_shadow_default(policy, SCENARIOS)
        assert results
        assert all(item.live.authorizes_action is False for item in results)
        assert all(item.live.mode is PilotMode.SHADOW for item in results)

    def test_the_only_gate_reported_without_activation_is_not_activated(self, policy):
        live = evaluate_live(_pilot(_request()), policy)
        assert [item.gate_id for item in live.gates] == [PilotGateId.NOT_ACTIVATED]


# ------------------------------------------------------------- 2. the opt-in


class TestExplicitOptInIsRequired:
    """An activation cannot happen by default, by accident, or by itself."""

    def test_an_activation_without_acknowledgement_is_refused(self, envelope):
        with pytest.raises(PilotBoundaryViolation, match="acknowledged_live"):
            PilotActivation(
                activation_id="test-act-unacknowledged",
                envelope=envelope,
                activated_by="MGI (CEO)",
                activated_on=DAY,
            )

    def test_acknowledgement_defaults_to_false(self, envelope):
        # The default matters more than the check: a default of True would make
        # live authority the thing you get by forgetting an argument.
        field = PilotActivation.__dataclass_fields__["acknowledged_live"]
        assert field.default is False

    @pytest.mark.parametrize(
        "signer", ["company_os", "company-os", "system", "automatic", "Company OS"]
    )
    def test_the_subsystem_cannot_activate_itself(self, envelope, signer):
        with pytest.raises(PilotBoundaryViolation, match="activated_by"):
            PilotActivation(
                activation_id="test-act-self",
                envelope=envelope,
                activated_by=signer,
                activated_on=DAY,
                acknowledged_live=True,
            )

    def test_an_activation_cannot_predate_nothing_and_postdate_its_expiry(
        self, envelope
    ):
        with pytest.raises(PilotBoundaryViolation, match="retroactively"):
            PilotActivation(
                activation_id="test-act-late",
                envelope=envelope,
                activated_by="MGI (CEO)",
                activated_on=dt.date(2027, 6, 1),
                acknowledged_live=True,
            )

    def test_a_shadow_mode_activation_is_a_contradiction(self, envelope):
        with pytest.raises(DelegationError, match="live-pilot mode"):
            PilotActivation(
                activation_id="test-act-shadow",
                envelope=envelope,
                activated_by="MGI (CEO)",
                activated_on=DAY,
                acknowledged_live=True,
                mode=PilotMode.SHADOW,
            )

    def test_an_activation_makes_a_low_risk_change_live(self, policy, activation):
        live = evaluate_live(_pilot(_request()), policy, activation=activation)
        assert live.mode is PilotMode.LIVE_PILOT
        assert live.decision is Decision.APPROVED
        assert live.authorizes_action is True


# ------------------------------------------------------- 3. the envelope model


class TestCEOObjectiveEnvelope:
    """Phase 9: the smallest thing the CEO signs."""

    def test_an_envelope_with_no_allowed_actions_is_refused(self):
        plan = PlanningEnvelope(
            objective_id=ENGINEERING_OBJECTIVE,
            budget=_usd("10.00"),
            budget_scope="engineering-operations",
            risk_ceiling=Risk.LOW,
            allowed_departments=("engineering",),
        )
        with pytest.raises(PilotBoundaryViolation, match="no allowed action"):
            PilotEnvelope(
                envelope_id="test-envelope-empty",
                objective="Nothing at all",
                plan=plan,
                allowed_actions=(),
                integration_target=PILOT_TARGET,
                expires_on=dt.date(2026, 12, 31),
                authorized_by="MGI (CEO)",
            )

    @pytest.mark.parametrize("action", sorted(RESERVED_HERE, key=lambda a: a.value))
    def test_an_envelope_cannot_allow_a_self_reserved_action(self, action):
        plan = PlanningEnvelope(
            objective_id=ENGINEERING_OBJECTIVE,
            budget=_usd("10.00"),
            budget_scope="engineering-operations",
            risk_ceiling=Risk.LOW,
            allowed_departments=("engineering",),
        )
        with pytest.raises(PilotBoundaryViolation, match="self-reserved"):
            PilotEnvelope(
                envelope_id="test-envelope-reserved",
                objective="Widening itself",
                plan=plan,
                allowed_actions=(action,),
                integration_target=PILOT_TARGET,
                expires_on=dt.date(2026, 12, 31),
                authorized_by="MGI (CEO)",
            )

    def test_an_envelope_cannot_be_signed_by_the_system(self, envelope):
        plan = envelope.plan
        with pytest.raises(PilotBoundaryViolation, match="authorized_by"):
            PilotEnvelope(
                envelope_id="test-envelope-unsigned",
                objective="Signed by nobody",
                plan=plan,
                allowed_actions=(ActionType.APPROVE_CODE_CHANGE,),
                integration_target=PILOT_TARGET,
                expires_on=dt.date(2026, 12, 31),
                authorized_by="company_os",
            )

    def test_an_envelope_cannot_both_allow_and_forbid_an_action(self):
        plan = PlanningEnvelope(
            objective_id=ENGINEERING_OBJECTIVE,
            budget=_usd("10.00"),
            budget_scope="engineering-operations",
            risk_ceiling=Risk.LOW,
            allowed_departments=("engineering",),
            forbidden_actions=(ActionType.APPROVE_CODE_CHANGE,),
        )
        with pytest.raises(DelegationError, match="allows and forbids"):
            PilotEnvelope(
                envelope_id="test-envelope-contradictory",
                objective="Both at once",
                plan=plan,
                allowed_actions=(ActionType.APPROVE_CODE_CHANGE,),
                integration_target=PILOT_TARGET,
                expires_on=dt.date(2026, 12, 31),
                authorized_by="MGI (CEO)",
            )

    def test_authority_cannot_outlive_the_objective(self):
        plan = PlanningEnvelope(
            objective_id=ENGINEERING_OBJECTIVE,
            budget=_usd("10.00"),
            budget_scope="engineering-operations",
            risk_ceiling=Risk.LOW,
            deadline=dt.date(2026, 10, 1),
            allowed_departments=("engineering",),
        )
        with pytest.raises(DelegationError, match="outlive"):
            PilotEnvelope(
                envelope_id="test-envelope-outlives",
                objective="Authority past the deadline",
                plan=plan,
                allowed_actions=(ActionType.APPROVE_CODE_CHANGE,),
                integration_target=PILOT_TARGET,
                expires_on=dt.date(2026, 12, 31),
                authorized_by="MGI (CEO)",
            )

    def test_the_envelope_carries_every_field_the_ceo_asked_for(self, envelope):
        # Phase 9's list, checked as a list so a future edit that drops one
        # fails here rather than in a report six months later.
        assert envelope.objective
        assert envelope.success_criteria is not None
        assert envelope.budget.text
        assert envelope.risk_ceiling
        assert envelope.plan.allowed_departments
        assert envelope.allowed_actions
        assert envelope.expires_on
        assert envelope.integration_target

    def test_the_canonical_reserved_set_is_checked_at_activation(
        self, policy, activation
    ):
        reserved = reserved_action_types(policy.hierarchy.permissions)
        assert reserved
        # Nothing the pilot allows may be in it.
        assert not activation.envelope.reserved_overlap(reserved)


# ---------------------------------------------------------- 4. the floor rule


class TestThePilotOnlyNarrows:
    """The single property that separates a pilot from a bypass."""

    @pytest.mark.parametrize(
        "scenario", CONTROL_SCENARIOS, ids=lambda s: s.scenario_id
    )
    def test_a_shadow_escalation_is_never_turned_into_a_live_approval(
        self, policy, activation, scenario
    ):
        shadow = evaluate(scenario.request, policy)
        live = evaluate_live(
            _pilot(scenario.request, review_passed=None, qa_passed=None),
            policy,
            activation=activation,
        )
        if shadow.ceo_required or shadow.decision is not Decision.APPROVED:
            assert live.authorizes_action is False
            assert live.ceo_required is True

    @pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.scenario_id)
    def test_live_never_lowers_ceo_required_below_shadow(
        self, policy, activation, scenario
    ):
        shadow = evaluate(scenario.request, policy)
        live = evaluate_live(
            _pilot(scenario.request, review_passed=True, qa_passed=True),
            policy,
            activation=activation,
        )
        if shadow.ceo_required:
            assert live.ceo_required is True

    def test_live_never_moves_the_approving_seat(self, policy, activation):
        request = _request()
        shadow = evaluate(request, policy)
        live = evaluate_live(_pilot(request), policy, activation=activation)
        if live.authorizes_action:
            assert live.actor == shadow.actor

    def test_a_decision_object_refuses_to_authorize_past_a_failed_gate(
        self, policy, activation
    ):
        request = _request()
        shadow = evaluate(request, policy)
        from company.delegation.pilot import PilotGate

        with pytest.raises(PilotBoundaryViolation, match="every pilot gate"):
            LivePilotDecision(
                request_id=request.request_id,
                mode=PilotMode.LIVE_PILOT,
                decision=Decision.APPROVED,
                actor="engineering_manager",
                authority_source="hand-built",
                action=request.action,
                risk=request.risk,
                ceo_required=False,
                reason="a hand-built approval over a failed gate",
                shadow_decision=shadow,
                gates=(
                    PilotGate(
                        gate_id=PilotGateId.QA_NOT_PASSED,
                        held=False,
                        detail="QA failed",
                    ),
                ),
                authorizes_action=True,
            )

    def test_a_decision_object_refuses_to_authorize_what_shadow_escalated(
        self, policy, activation
    ):
        escalating = CONTROL_SCENARIOS[-1].request
        shadow = evaluate(escalating, policy)
        assert shadow.decision is not Decision.APPROVED or shadow.ceo_required
        with pytest.raises(PilotBoundaryViolation, match="narrow the shadow answer"):
            LivePilotDecision(
                request_id=escalating.request_id,
                mode=PilotMode.LIVE_PILOT,
                decision=Decision.APPROVED,
                actor="engineering_manager",
                authority_source="hand-built",
                action=ActionType.APPROVE_CODE_CHANGE,
                risk=Risk.LOW,
                ceo_required=False,
                reason="a hand-built approval over a shadow escalation",
                shadow_decision=shadow,
                gates=(),
                authorizes_action=True,
            )

    def test_a_shadow_mode_decision_cannot_authorize(self, policy):
        request = _request()
        shadow = evaluate(request, policy)
        with pytest.raises(PilotBoundaryViolation, match="shadow"):
            LivePilotDecision(
                request_id=request.request_id,
                mode=PilotMode.SHADOW,
                decision=Decision.APPROVED,
                actor="engineering_manager",
                authority_source="hand-built",
                action=request.action,
                risk=request.risk,
                ceo_required=False,
                reason="a shadow decision claiming authority",
                shadow_decision=shadow,
                authorizes_action=True,
            )


# ------------------------------------------------------ 5. seats and actions


class TestEngineeringManagerAuthority:
    """Phase 4: what the manager may and may not live-approve."""

    def test_the_manager_may_live_approve_a_low_risk_change(self, policy, activation):
        live = evaluate_live(_pilot(_request()), policy, activation=activation)
        assert live.actor == "engineering_manager"
        assert live.authorizes_action is True
        assert live.ceo_required is False

    @pytest.mark.parametrize(
        "action",
        sorted(ENGINEERING_MANAGER_LIVE_ACTIONS, key=lambda item: item.value),
        ids=lambda a: a.value,
    )
    def test_every_action_in_the_managers_set_is_granted_by_the_policy(
        self, policy, action
    ):
        # The pilot must be a subset of the policy, never a superset. A pilot
        # action the policy does not grant would escalate every time, which
        # looks like a broken pilot rather than a narrow one.
        grant = policy.grant("engineering_manager")
        assert grant is not None
        assert action in grant.action_types, action.value

    def test_the_manager_ceiling_is_low_risk(self):
        assert PILOT_RISK_CEILING["engineering_manager"] is Risk.LOW

    def test_the_manager_cannot_live_approve_medium_risk(self, policy, activation):
        live = evaluate_live(
            _pilot(_request(risk=Risk.MEDIUM)), policy, activation=activation
        )
        assert live.authorizes_action is False
        assert live.ceo_required is True

    def test_the_manager_cannot_approve_their_own_implementation(
        self, policy, activation
    ):
        live = evaluate_live(
            _pilot(
                _request(
                    implementer="engineering_delivery_manager",
                    reviewer="chief_architect",
                )
            ),
            policy,
            activation=activation,
        )
        assert live.authorizes_action is False

    def test_the_manager_cannot_override_a_reviewer_verdict(self, policy, activation):
        live = evaluate_live(
            _pilot(_request(overrides=True), review_passed=False, qa_passed=False),
            policy,
            activation=activation,
        )
        assert live.authorizes_action is False
        assert live.ceo_required is True

    def test_the_manager_may_accept_a_changes_required_verdict(
        self, policy, activation
    ):
        # The case the historical replay corrected. A reviewer-found defect is
        # ordinary engineering; sending it to the CEO defeats Phase 8.
        live = evaluate_live(
            _pilot(
                _request(action=ActionType.APPROVE_REVIEW_OUTCOME),
                review_passed=False,
                qa_passed=None,
            ),
            policy,
            activation=activation,
        )
        assert live.authorizes_action is True
        assert live.ceo_required is False

    def test_the_manager_cannot_approve_an_outcome_with_no_review(
        self, policy, activation
    ):
        live = evaluate_live(
            _pilot(
                _request(action=ActionType.APPROVE_REVIEW_OUTCOME),
                review_passed=None,
                qa_passed=None,
            ),
            policy,
            activation=activation,
        )
        assert live.authorizes_action is False
        assert PilotGateId.REVIEW_NOT_INDEPENDENT in {
            item.gate_id for item in live.failed_gates
        }

    def test_the_manager_holds_no_integration_authority(self):
        assert (
            ActionType.APPROVE_INTEGRATION_MERGE
            not in PILOT_SEATS["engineering_manager"]
        )


class TestCTOAuthority:
    """Phase 4: the CTO's bounded internal integration authority."""

    def test_the_cto_may_live_approve_internal_integration(self, policy, activation):
        live = evaluate_live(
            _pilot(
                _request(
                    request_id="test-req-integrate",
                    action=ActionType.APPROVE_INTEGRATION_MERGE,
                    reviewer="ai_efficiency_platform_engineer",
                ),
                integration_branch=PILOT_TARGET.branch,
            ),
            policy,
            activation=activation,
        )
        assert live.actor == "cto"
        assert live.authorizes_action is True
        assert live.ceo_required is False

    def test_the_cto_medium_ceiling_comes_from_the_policy_grant(self, policy):
        assert PILOT_RISK_CEILING["cto"] is Risk.MEDIUM
        grant = policy.grant("cto")
        assert grant is not None
        assert grant.max_risk is Risk.MEDIUM

    def test_the_cto_cannot_integrate_work_they_reviewed(self, policy, activation):
        live = evaluate_live(
            _pilot(
                _request(
                    request_id="test-req-cto-reviewed",
                    action=ActionType.APPROVE_INTEGRATION_MERGE,
                    reviewer="chief_architect",
                ),
                integration_branch=PILOT_TARGET.branch,
            ),
            policy,
            activation=activation,
        )
        assert live.authorizes_action is False

    @pytest.mark.parametrize(
        "action",
        sorted(CTO_LIVE_ACTIONS, key=lambda item: item.value),
        ids=lambda a: a.value,
    )
    def test_every_action_in_the_ctos_set_is_granted_by_the_policy(
        self, policy, action
    ):
        grant = policy.grant("cto")
        assert grant is not None
        assert action in grant.action_types, action.value


class TestNobodyElseHoldsLiveAuthority:
    def test_only_two_seats_are_in_the_pilot(self):
        assert set(PILOT_SEATS) == {"engineering_manager", "cto"}

    def test_the_ceo_seat_is_not_a_pilot_seat(self):
        assert "ceo" not in PILOT_SEATS

    @pytest.mark.parametrize("seat", ["coo", "cfo", "ai_platform_lead", "people_lead"])
    def test_other_seats_hold_no_live_authority(self, seat):
        assert seat not in PILOT_SEATS

    def test_a_decision_naming_a_non_pilot_seat_cannot_authorize(self, policy):
        request = _request()
        shadow = evaluate(request, policy)
        with pytest.raises(PilotBoundaryViolation, match="no live authority"):
            LivePilotDecision(
                request_id=request.request_id,
                mode=PilotMode.LIVE_PILOT,
                decision=Decision.APPROVED,
                actor="coo",
                authority_source="hand-built",
                action=request.action,
                risk=request.risk,
                ceo_required=False,
                reason="the COO claiming live authority",
                shadow_decision=shadow,
                authorizes_action=True,
            )


# -------------------------------------------------- 6. reserved and escalation


class TestReservedAndUnknownActionsEscalate:
    """Phase 6 and the unknown-action case."""

    @pytest.mark.parametrize(
        "action",
        [
            ActionType.APPROVE_DEPLOYMENT,
            ActionType.PUBLISH_PUBLIC_VIDEO,
            ActionType.APPROVE_CANONICAL_MERGE,
            ActionType.APPROVE_STAGING_RELEASE,
            ActionType.APPROVE_ARCHITECTURE_REDESIGN,
            ActionType.APPROVE_SECURITY_EXCEPTION,
            ActionType.CHANGE_GOVERNANCE_POLICY,
            ActionType.EXPAND_AUTHORITY,
            ActionType.CHANGE_DELEGATION_POLICY,
            ActionType.HIRE_OR_REMOVE_EXECUTIVE_ROLE,
            ActionType.UNCLASSIFIED,
        ],
        ids=lambda a: a.value,
    )
    def test_the_pilot_forbids_it(self, action):
        assert action in PILOT_FORBIDDEN_ACTIONS

    @pytest.mark.parametrize(
        "action",
        [
            ActionType.APPROVE_DEPLOYMENT,
            ActionType.PUBLISH_PUBLIC_VIDEO,
            ActionType.EXPAND_AUTHORITY,
            ActionType.UNCLASSIFIED,
        ],
        ids=lambda a: a.value,
    )
    def test_no_pilot_seat_holds_it(self, action):
        for seat, actions in PILOT_SEATS.items():
            assert action not in actions, f"{seat} holds {action.value}"

    @pytest.mark.parametrize(
        "action",
        [
            ActionType.APPROVE_DEPLOYMENT,
            ActionType.PUBLISH_PUBLIC_VIDEO,
            ActionType.EXPAND_AUTHORITY,
            ActionType.CHANGE_GOVERNANCE_POLICY,
            ActionType.UNCLASSIFIED,
        ],
        ids=lambda a: a.value,
    )
    def test_requesting_it_reaches_the_ceo(self, policy, activation, action):
        live = evaluate_live(
            _pilot(
                _request(request_id="test-req-reserved", action=action),
                review_passed=None,
                qa_passed=None,
            ),
            policy,
            activation=activation,
        )
        assert live.authorizes_action is False
        assert live.ceo_required is True

    def test_an_activation_allowing_a_forbidden_action_is_refused(self, policy):
        # `approve_staging_release` is executive rather than CEO-reserved, so
        # the envelope itself accepts it; the activation check is what catches
        # it. This is the seam those two layers exist to cover.
        plan = PlanningEnvelope(
            objective_id=ENGINEERING_OBJECTIVE,
            budget=_usd("10.00"),
            budget_scope="engineering-operations",
            risk_ceiling=Risk.LOW,
            allowed_departments=("engineering",),
        )
        envelope = PilotEnvelope(
            envelope_id="test-envelope-staging",
            objective="A release, dressed as an integration",
            plan=plan,
            allowed_actions=(ActionType.APPROVE_STAGING_RELEASE,),
            integration_target=PILOT_TARGET,
            expires_on=dt.date(2026, 12, 31),
            authorized_by="MGI (CEO)",
        )
        act = PilotActivation(
            activation_id="test-act-staging",
            envelope=envelope,
            activated_by="MGI (CEO)",
            activated_on=DAY,
            acknowledged_live=True,
        )
        with pytest.raises(PilotBoundaryViolation, match="outside this pilot"):
            act.check_against(policy)

    def test_public_deployment_is_never_authorized(self, policy, activation):
        for action in (ActionType.APPROVE_DEPLOYMENT, ActionType.PUBLISH_PUBLIC_VIDEO):
            live = evaluate_live(
                _pilot(
                    _request(request_id="test-req-public", action=action),
                    review_passed=None,
                    qa_passed=None,
                ),
                policy,
                activation=activation,
            )
            assert live.authorizes_action is False, action.value


# ------------------------------------------------------ 7. integration target


class TestIntegrationTarget:
    """Phase 5: work is accepted internally, and main never moves."""

    def test_the_pilot_target_is_an_internal_branch(self):
        assert PILOT_TARGET.kind is TargetKind.INTERNAL_BRANCH
        assert PILOT_TARGET.reversible is True

    def test_the_pilot_target_is_not_main_or_canonical(self):
        assert PILOT_TARGET.branch not in PROTECTED_REFS

    @pytest.mark.parametrize("ref", sorted(PROTECTED_REFS))
    def test_a_target_naming_a_protected_ref_is_refused(self, ref):
        with pytest.raises(PilotBoundaryViolation, match="protected ref"):
            IntegrationTarget(
                target_id="test-target-protected",
                kind=TargetKind.INTERNAL_BRANCH,
                branch=ref,
                rationale="trying to name a protected ref",
            )

    def test_main_and_canonical_are_both_protected(self):
        assert "main" in PROTECTED_REFS
        assert "company-os-v1-bootstrap" in PROTECTED_REFS

    def test_an_unclassified_target_fails_closed(self):
        with pytest.raises(PilotBoundaryViolation, match="unknown"):
            IntegrationTarget(
                target_id="test-target-unknown",
                kind=TargetKind.UNKNOWN,
                branch="some-branch",
                rationale="an unclassified target",
            )

    def test_an_irreversible_target_is_refused(self):
        with pytest.raises(PilotBoundaryViolation, match="irreversible"):
            IntegrationTarget(
                target_id="test-target-irreversible",
                kind=TargetKind.INTERNAL_BRANCH,
                branch="some-branch",
                rationale="a release pretending to be an integration",
                reversible=False,
            )

    def test_a_target_cannot_shrink_the_protected_set(self):
        target = IntegrationTarget(
            target_id="test-target-narrow",
            kind=TargetKind.INTERNAL_BRANCH,
            branch="some-internal-branch",
            rationale="declares only one extra protection",
            protects=("release",),
        )
        assert PROTECTED_REFS.issubset(set(target.protects))

    @pytest.mark.parametrize("ref", sorted(PROTECTED_REFS))
    def test_integration_onto_a_protected_ref_reaches_the_ceo(
        self, policy, activation, ref
    ):
        live = evaluate_live(
            _pilot(
                _request(
                    request_id="test-req-protected-merge",
                    action=ActionType.APPROVE_INTEGRATION_MERGE,
                    reviewer="ai_efficiency_platform_engineer",
                ),
                integration_branch=ref,
            ),
            policy,
            activation=activation,
        )
        assert live.authorizes_action is False
        assert live.ceo_required is True
        assert PilotGateId.PROTECTED_REF in {
            item.gate_id for item in live.failed_gates
        }

    def test_integration_onto_an_unrelated_branch_reaches_the_ceo(
        self, policy, activation
    ):
        live = evaluate_live(
            _pilot(
                _request(
                    request_id="test-req-other-merge",
                    action=ActionType.APPROVE_INTEGRATION_MERGE,
                    reviewer="ai_efficiency_platform_engineer",
                ),
                integration_branch="somebody-elses-branch",
            ),
            policy,
            activation=activation,
        )
        assert live.authorizes_action is False
        assert live.ceo_required is True

    def test_a_live_decision_object_refuses_a_protected_branch(self, policy):
        request = _request(action=ActionType.APPROVE_INTEGRATION_MERGE)
        shadow = evaluate(request, policy)
        if shadow.decision is Decision.APPROVED and not shadow.ceo_required:
            with pytest.raises(PilotBoundaryViolation, match="protected ref"):
                LivePilotDecision(
                    request_id=request.request_id,
                    mode=PilotMode.LIVE_PILOT,
                    decision=Decision.APPROVED,
                    actor=shadow.actor,
                    authority_source="hand-built",
                    action=request.action,
                    risk=request.risk,
                    ceo_required=False,
                    reason="a hand-built approval naming main",
                    shadow_decision=shadow,
                    integration_branch="main",
                    authorizes_action=True,
                )


# --------------------------------------------------- 8. budget, risk, expiry


class TestEnvelopeEnforcement:
    def test_spend_above_the_envelope_reaches_the_ceo(self, policy, activation):
        live = evaluate_live(
            _pilot(_request(request_id="test-req-big-spend", amount=_usd("500.00"))),
            policy,
            activation=activation,
        )
        assert live.authorizes_action is False
        assert live.ceo_required is True

    def test_risk_above_the_envelope_reaches_the_ceo(self, policy, activation):
        live = evaluate_live(
            _pilot(_request(request_id="test-req-high-risk", risk=Risk.HIGH)),
            policy,
            activation=activation,
        )
        assert live.authorizes_action is False
        assert live.ceo_required is True

    def test_a_department_outside_the_envelope_reaches_the_ceo(
        self, policy, activation
    ):
        live = evaluate_live(
            _pilot(
                _request(
                    request_id="test-req-other-dept",
                    department="production",
                    seat="production_lead",
                )
            ),
            policy,
            activation=activation,
        )
        assert live.authorizes_action is False
        assert live.ceo_required is True

    def test_an_objective_the_envelope_was_not_signed_for_reaches_the_ceo(
        self, policy, activation
    ):
        live = evaluate_live(
            _pilot(
                _request(
                    request_id="test-req-other-objective",
                    objective_id="obj-some-other-programme",
                )
            ),
            policy,
            activation=activation,
        )
        assert live.authorizes_action is False
        assert live.ceo_required is True
        assert PilotGateId.OBJECTIVE_MISMATCH in {
            item.gate_id for item in live.failed_gates
        }

    def test_an_expired_envelope_escalates_rather_than_approving(self, policy):
        live = evaluate_live(
            _pilot(_request(request_id="test-req-expired")),
            policy,
            activation=EXPIRED_ACTIVATION,
            as_of=DAY,
        )
        assert live.authorizes_action is False
        assert live.ceo_required is True
        assert PilotGateId.ENVELOPE_EXPIRED in {
            item.gate_id for item in live.failed_gates
        }

    def test_a_currency_mismatch_fails_closed(self, envelope):
        assert envelope.permits_amount(Money("1.00", "EUR")) is False

    def test_a_mismatched_currency_is_refused_rather_than_converted(
        self, policy, activation
    ):
        # The canonical budget ladder raises instead of picking a rate, so a
        # mixed-currency request never reaches a decision at all. That is a
        # stronger answer than escalating, and this test records which of the
        # two actually happens so a future change to either is visible here.
        from company.finance.errors import CurrencyMismatch

        with pytest.raises(CurrencyMismatch):
            evaluate_live(
                _pilot(
                    _request(request_id="test-req-eur", amount=Money("1.00", "EUR"))
                ),
                policy,
                activation=activation,
            )


class TestQACannotBeOverridden:
    def test_progression_past_a_failed_qa_run_reaches_the_ceo(
        self, policy, activation
    ):
        live = evaluate_live(
            _pilot(
                _request(
                    request_id="test-req-qa-fail",
                    action=ActionType.APPROVE_TEST_PROGRESSION,
                ),
                review_passed=True,
                qa_passed=False,
            ),
            policy,
            activation=activation,
        )
        assert live.authorizes_action is False
        assert live.ceo_required is True
        assert PilotGateId.QA_NOT_PASSED in {
            item.gate_id for item in live.failed_gates
        }

    def test_progression_to_qa_is_routine(self, policy, activation):
        live = evaluate_live(
            _pilot(
                _request(
                    request_id="test-req-qa-ok",
                    action=ActionType.APPROVE_TEST_PROGRESSION,
                ),
                review_passed=True,
                qa_passed=True,
            ),
            policy,
            activation=activation,
        )
        assert live.authorizes_action is True

    def test_an_explicit_override_reaches_the_ceo(self, policy, activation):
        live = evaluate_live(
            _pilot(
                _request(request_id="test-req-override", overrides=True),
                review_passed=False,
                qa_passed=False,
            ),
            policy,
            activation=activation,
        )
        assert live.authorizes_action is False
        assert live.ceo_required is True

    def test_a_reviewer_who_implemented_is_not_independent(self, policy, activation):
        live = evaluate_live(
            _pilot(
                _request(
                    request_id="test-req-same-person",
                    implementer="software_implementation_engineer",
                    reviewer="software_implementation_engineer",
                )
            ),
            policy,
            activation=activation,
        )
        assert live.authorizes_action is False


# ------------------------------------------------- 9. the correction loop


class TestBoundedCorrection:
    """Phase 8: one correction is ordinary; the second is the CEO's call."""

    def test_the_consumer_ceiling_is_one(self, activation):
        consumer = PROFILES[ResourceProfileName.CONSUMER]
        assert correction_ceiling(activation, consumer) == 1

    def test_the_envelope_cannot_raise_the_profile_ceiling(self, envelope):
        generous = PilotEnvelope(
            envelope_id="test-envelope-generous",
            objective="Asking for more corrections than the subscription funds",
            plan=envelope.plan,
            allowed_actions=envelope.allowed_actions,
            integration_target=PILOT_TARGET,
            expires_on=envelope.expires_on,
            authorized_by="MGI (CEO)",
            max_corrections_per_work_order=8,
        )
        act = PilotActivation(
            activation_id="test-act-generous",
            envelope=generous,
            activated_by="MGI (CEO)",
            activated_on=DAY,
            acknowledged_live=True,
        )
        consumer = PROFILES[ResourceProfileName.CONSUMER]
        assert correction_ceiling(act, consumer) == consumer.reviewer_passes

    def test_the_profile_cannot_raise_the_envelope_ceiling(self, activation):
        expanded = PROFILES[ResourceProfileName.EXPANDED]
        assert expanded.reviewer_passes > 1
        assert correction_ceiling(activation, expanded) == 1

    def test_the_manager_may_authorize_one_correction(self, activation):
        verdict = authorize_correction(
            "wo-test-correction",
            activation=activation,
            authorizing_seat="engineering_manager",
            reviewer_said_changes_required=True,
        )
        assert verdict.permitted is True
        assert verdict.ceo_required is False
        assert verdict.authorizing_seat == "engineering_manager"

    def test_the_second_correction_reaches_the_ceo(self, activation):
        first = authorize_correction(
            "wo-test-correction",
            activation=activation,
            authorizing_seat="engineering_manager",
            reviewer_said_changes_required=True,
        )
        second = authorize_correction(
            "wo-test-correction",
            activation=activation,
            authorizing_seat="engineering_manager",
            reviewer_said_changes_required=True,
            ledger=first.ledger,
        )
        assert second.permitted is False
        assert second.ceo_required is True

    def test_a_correction_needs_a_reviewer_verdict(self, activation):
        verdict = authorize_correction(
            "wo-test-correction",
            activation=activation,
            authorizing_seat="engineering_manager",
            reviewer_said_changes_required=False,
        )
        assert verdict.permitted is False

    @pytest.mark.parametrize("seat", ["coo", "cfo", "people_lead", "ceo"])
    def test_only_pilot_management_seats_may_authorize_one(self, activation, seat):
        verdict = authorize_correction(
            "wo-test-correction",
            activation=activation,
            authorizing_seat=seat,
            reviewer_said_changes_required=True,
        )
        assert verdict.permitted is False
        assert verdict.ceo_required is True

    def test_a_refused_correction_does_not_increment_the_ledger(self, activation):
        ledger = CorrectionLedger.empty()
        verdict = authorize_correction(
            "wo-test-correction",
            activation=activation,
            authorizing_seat="coo",
            reviewer_said_changes_required=True,
            ledger=ledger,
        )
        assert verdict.ledger.used("wo-test-correction") == 0

    def test_the_ledger_is_immutable(self):
        first = CorrectionLedger.empty()
        second = first.with_correction("wo-test-correction")
        assert first.used("wo-test-correction") == 0
        assert second.used("wo-test-correction") == 1

    def test_a_request_over_the_ceiling_reaches_the_ceo(self, policy, activation):
        live = evaluate_live(
            _pilot(
                _request(
                    request_id="test-req-third-correction",
                    action=ActionType.REQUEST_BOUNDED_CORRECTION,
                ),
                corrections_used=3,
                review_passed=False,
            ),
            policy,
            activation=activation,
        )
        assert live.authorizes_action is False
        assert live.ceo_required is True
        assert PilotGateId.CORRECTION_CEILING in {
            item.gate_id for item in live.failed_gates
        }

    def test_the_full_correction_loop_needs_no_ceo(self, policy, activation):
        """Phase 8 end to end: defect, correction, re-review, QA, approval."""
        # 1. The reviewer asks for changes. The manager accepts that outcome.
        accepted = evaluate_live(
            _pilot(
                _request(
                    request_id="test-loop-review",
                    action=ActionType.APPROVE_REVIEW_OUTCOME,
                ),
                review_passed=False,
                qa_passed=None,
            ),
            policy,
            activation=activation,
        )
        assert accepted.authorizes_action is True

        # 2. The manager authorizes one bounded correction.
        verdict = authorize_correction(
            "wo-test-loop",
            activation=activation,
            authorizing_seat="engineering_manager",
            reviewer_said_changes_required=True,
        )
        assert verdict.permitted is True

        # 3. The corrected work is reviewed again and approved.
        corrected = evaluate_live(
            _pilot(
                _request(request_id="test-loop-corrected"),
                review_passed=True,
                qa_passed=True,
                corrections_used=1,
            ),
            policy,
            activation=activation,
        )
        assert corrected.authorizes_action is True

        # 4. Progression to deterministic QA.
        progressed = evaluate_live(
            _pilot(
                _request(
                    request_id="test-loop-qa",
                    action=ActionType.APPROVE_TEST_PROGRESSION,
                ),
                review_passed=True,
                qa_passed=True,
                corrections_used=1,
            ),
            policy,
            activation=activation,
        )
        assert progressed.authorizes_action is True

        for step in (accepted, corrected, progressed):
            assert step.ceo_required is False


# ------------------------------------------------------- 10. the audit record


class TestLiveDecisionRecord:
    """Phase 7: the row a CEO reconstructs the decision from."""

    def test_a_live_approval_produces_a_complete_record(self, policy, activation):
        request = _request()
        live = evaluate_live(_pilot(request), policy, activation=activation)
        record = record_live_decision(
            live,
            _pilot(request),
            decision_id="test-decision-0001",
            recorded_on=DAY,
            policy=policy,
            activation=activation,
            hierarchy=policy.hierarchy,
        )
        assert record.mode is PilotMode.LIVE_PILOT
        assert record.authorizes_action is True
        assert record.ceo_required is False
        assert record.approving_seat == "engineering_manager"
        assert record.approving_employee == "engineering_delivery_manager"
        assert record.requesting_employee
        assert record.reviewer == "chief_architect"
        assert record.implementer == "software_implementation_engineer"
        assert record.envelope_id == activation.envelope.envelope_id
        assert record.envelope_fingerprint
        assert record.activation_id == activation.activation_id
        assert record.policy_fingerprint
        assert record.policy_version
        assert record.request_fingerprint
        assert record.gates_checked > 0
        assert record.gates_failed == ()

    def test_every_field_the_ceo_asked_for_is_present(self, policy, activation):
        request = _request()
        live = evaluate_live(_pilot(request), policy, activation=activation)
        payload = record_live_decision(
            live,
            _pilot(request),
            decision_id="test-decision-0002",
            recorded_on=DAY,
            policy=policy,
            activation=activation,
            hierarchy=policy.hierarchy,
        ).to_dict()
        for field in (
            "decision_id",
            "objective_id",
            "work_order_id",
            "requesting_employee",
            "reviewer",
            "approving_employee",
            "approving_seat",
            "authority_source",
            "risk",
            "budget_used",
            "action",
            "decision",
            "reason",
            "escalation_chain",
            "ceo_required",
            "policy_version",
            "mode",
        ):
            assert field in payload, field
        assert payload["mode"] == "live_pilot"

    def test_the_record_explains_why_the_ceo_was_not_needed(self, policy, activation):
        request = _request()
        live = evaluate_live(_pilot(request), policy, activation=activation)
        record = record_live_decision(
            live,
            _pilot(request),
            decision_id="test-decision-0003",
            recorded_on=DAY,
            policy=policy,
            activation=activation,
            hierarchy=policy.hierarchy,
        )
        text = record.explain()
        assert "without the CEO" in text
        assert activation.envelope.envelope_id in text

    def test_an_escalated_record_carries_the_chain(self, policy, activation):
        request = _request(request_id="test-req-chain", risk=Risk.HIGH)
        live = evaluate_live(_pilot(request), policy, activation=activation)
        record = record_live_decision(
            live,
            _pilot(request),
            decision_id="test-decision-0004",
            recorded_on=DAY,
            policy=policy,
            activation=activation,
            hierarchy=policy.hierarchy,
        )
        assert record.ceo_required is True
        assert record.authorizes_action is False
        assert record.escalation_chain

    def test_a_record_cannot_claim_authority_in_shadow_mode(self, policy):
        with pytest.raises(PilotBoundaryViolation, match="shadow"):
            LivePilotDecisionRecord(
                decision_id="test-decision-shadow",
                recorded_on=DAY,
                objective_id=ENGINEERING_OBJECTIVE,
                work_order_id="wo-test-change",
                department="engineering",
                requesting_seat="software_implementation_engineer",
                requesting_employee="software_implementation_engineer",
                approving_seat="engineering_manager",
                approving_employee="engineering_delivery_manager",
                reviewer="chief_architect",
                action=ActionType.APPROVE_CODE_CHANGE,
                risk=Risk.LOW,
                decision=Decision.APPROVED,
                reason="a shadow record claiming authority",
                authority_source="hand-built",
                ceo_required=False,
                mode=PilotMode.SHADOW,
                policy_version="delegation_policy_v1",
                policy_fingerprint="x" * 16,
                envelope_id="test-envelope-engineering",
                envelope_fingerprint="y" * 16,
                activation_id="test-activation-engineering",
                authorizes_action=True,
            )

    def test_a_record_refuses_the_reviewer_as_the_approver(self):
        with pytest.raises(PilotBoundaryViolation, match="reviewed and approved"):
            LivePilotDecisionRecord(
                decision_id="test-decision-conflict",
                recorded_on=DAY,
                objective_id=ENGINEERING_OBJECTIVE,
                work_order_id="wo-test-change",
                department="engineering",
                requesting_seat="software_implementation_engineer",
                requesting_employee="software_implementation_engineer",
                approving_seat="engineering_manager",
                approving_employee="chief_architect",
                reviewer="chief_architect",
                action=ActionType.APPROVE_CODE_CHANGE,
                risk=Risk.LOW,
                decision=Decision.APPROVED,
                reason="the reviewer approving their own review",
                authority_source="hand-built",
                ceo_required=False,
                mode=PilotMode.LIVE_PILOT,
                policy_version="delegation_policy_v1",
                policy_fingerprint="x" * 16,
                envelope_id="test-envelope-engineering",
                envelope_fingerprint="y" * 16,
                activation_id="test-activation-engineering",
                authorizes_action=True,
            )

    def test_a_record_refuses_the_implementer_as_the_approver(self):
        with pytest.raises(PilotBoundaryViolation, match="implemented and approved"):
            LivePilotDecisionRecord(
                decision_id="test-decision-selfimpl",
                recorded_on=DAY,
                objective_id=ENGINEERING_OBJECTIVE,
                work_order_id="wo-test-change",
                department="engineering",
                requesting_seat="software_implementation_engineer",
                requesting_employee="software_implementation_engineer",
                approving_seat="engineering_manager",
                approving_employee="software_implementation_engineer",
                reviewer="chief_architect",
                implementer="software_implementation_engineer",
                action=ActionType.APPROVE_CODE_CHANGE,
                risk=Risk.LOW,
                decision=Decision.APPROVED,
                reason="the implementer approving their own work",
                authority_source="hand-built",
                ceo_required=False,
                mode=PilotMode.LIVE_PILOT,
                policy_version="delegation_policy_v1",
                policy_fingerprint="x" * 16,
                envelope_id="test-envelope-engineering",
                envelope_fingerprint="y" * 16,
                activation_id="test-activation-engineering",
                authorizes_action=True,
            )

    def test_a_live_approval_must_name_its_envelope(self):
        with pytest.raises(PilotBoundaryViolation, match="envelope"):
            LivePilotDecisionRecord(
                decision_id="test-decision-noenvelope",
                recorded_on=DAY,
                objective_id=ENGINEERING_OBJECTIVE,
                work_order_id="wo-test-change",
                department="engineering",
                requesting_seat="software_implementation_engineer",
                requesting_employee="software_implementation_engineer",
                approving_seat="engineering_manager",
                approving_employee="engineering_delivery_manager",
                reviewer="chief_architect",
                action=ActionType.APPROVE_CODE_CHANGE,
                risk=Risk.LOW,
                decision=Decision.APPROVED,
                reason="an approval with no envelope",
                authority_source="hand-built",
                ceo_required=False,
                mode=PilotMode.LIVE_PILOT,
                policy_version="delegation_policy_v1",
                policy_fingerprint="x" * 16,
                envelope_id="",
                envelope_fingerprint="",
                activation_id="",
                authorizes_action=True,
            )

    def test_the_shadow_record_class_still_refuses_to_leave_shadow(self):
        # The guarantee the second class exists to preserve.
        from company.delegation.record import ExecutiveDecisionRecord

        field = ExecutiveDecisionRecord.__dataclass_fields__["shadow"]
        assert field.default is True


# ---------------------------------------------------------- 11. the CEO report


class TestCEOReport:
    def test_the_report_has_every_section_the_ceo_asked_for(
        self, policy, activation
    ):
        request = _request()
        live = evaluate_live(_pilot(request), policy, activation=activation)
        record = record_live_decision(
            live,
            _pilot(request),
            decision_id="test-decision-report",
            recorded_on=DAY,
            policy=policy,
            activation=activation,
            hierarchy=policy.hierarchy,
        )
        text = PilotRunReport(
            objective="Routine engineering delivery",
            outcome="One low-risk change approved internally",
            activation=activation,
            records=(record,),
            work_orders_completed=("wo-test-change",),
            final_result="accepted onto the pilot integration branch",
            as_of=DAY,
        ).render()
        for heading in (
            "OBJECTIVE",
            "OUTCOME",
            "WORK ORDERS COMPLETED",
            "INTERNAL DECISIONS",
            "MANAGER APPROVALS",
            "EXECUTIVE APPROVALS",
            "CEO DECISIONS REQUIRED",
            "EXCEPTIONS",
            "COST",
            "FINAL RESULT",
        ):
            assert heading in text, heading

    def test_a_clean_run_reports_zero_ceo_decisions(self, policy, activation):
        request = _request()
        live = evaluate_live(_pilot(request), policy, activation=activation)
        record = record_live_decision(
            live,
            _pilot(request),
            decision_id="test-decision-clean",
            recorded_on=DAY,
            policy=policy,
            activation=activation,
            hierarchy=policy.hierarchy,
        )
        report = PilotRunReport(
            objective="Routine engineering delivery",
            outcome="clean",
            activation=activation,
            records=(record,),
        )
        assert len(report.ceo_decisions_required) == 0
        assert len(report.manager_approvals) == 1
        assert "CEO DECISIONS REQUIRED\n  0" in report.render()

    def test_the_simulation_report_says_nothing_ran(self, policy):
        text = simulation_report(
            {"historical": replay_live(policy, SCENARIOS)},
            activation=ENGINEERING_ACTIVATION,
            objective="pilot",
            as_of=DAY,
        )
        assert "NO REAL WORK ORDER RAN" in text
        assert "not" in text


# -------------------------------------------------------- 12. the replay


class TestHistoricalSimulation:
    """Phase 11: recorded history, through live semantics."""

    def test_every_historical_scenario_matches_its_pilot_expectation(self, policy):
        for item in replay_live(policy, SCENARIOS):
            assert item.matches_expectation, (
                f"{item.scenario_id}: ceo_required={item.live.ceo_required}, "
                f"expected={item.effective_expectation}"
            )

    def test_every_control_scenario_still_reaches_the_ceo(self, policy):
        results = replay_live(policy, CONTROL_SCENARIOS)
        assert len(results) == 5
        for item in results:
            assert item.live.ceo_required is True, item.scenario_id
            assert item.live.authorizes_action is False, item.scenario_id

    def test_every_pilot_probe_matches_its_expectation(self, policy):
        results = replay_probes(policy)
        assert len(results) == len(PILOT_PROBES)
        for item in results:
            assert item.matches_expectation, item.scenario_id

    def test_four_of_five_routine_historical_decisions_stay_internal(self, policy):
        results = replay_live(policy, SCENARIOS)
        internal = [item for item in results if item.proceeded_internally]
        assert len(internal) == 4

    def test_the_one_divergence_is_reported_with_a_reason(self, policy):
        results = replay_live(policy, SCENARIOS)
        diverged = [item for item in results if item.differs_from_shadow]
        assert len(diverged) == 1
        assert diverged[0].scenario_id == "burnin-job-c"
        assert diverged[0].divergence_reason

    def test_the_internal_integration_probe_succeeds(self, policy):
        results = {item.scenario_id: item for item in replay_probes(policy)}
        internal = results["pilot-probe-integrate-internal"]
        assert internal.proceeded_internally is True
        assert internal.live.actor == "cto"

    def test_the_main_branch_probe_fails_only_on_the_branch(self, policy):
        results = {item.scenario_id: item for item in replay_probes(policy)}
        main = results["pilot-probe-integrate-main"]
        assert main.live.ceo_required is True
        assert [item.gate_id for item in main.live.failed_gates] == [
            PilotGateId.PROTECTED_REF
        ]

    def test_the_full_simulation_is_deterministic(self, policy):
        first = run_full_simulation(policy)
        second = run_full_simulation(policy)
        assert first == second

    def test_the_full_simulation_has_no_mismatches(self, policy):
        summary = run_full_simulation(policy)
        assert summary["historical"]["mismatched"] == []
        assert summary["controls"]["mismatched"] == []
        assert summary["pilot_probes"]["mismatched"] == []
        assert summary["shadow_default"]["authorized_any"] is False


# ------------------------------------------------- 13. what the code cannot do


class TestThePilotCannotAct:
    """Asserted against the package source, not against a fixture."""

    PILOT_SOURCES = (
        "pilot.py",
        "pilot_envelope.py",
        "pilot_integration.py",
        "pilot_record.py",
        "pilot_correction.py",
        "pilot_report.py",
        "pilot_simulation.py",
    )

    def _sources(self) -> dict[str, str]:
        base = Path(__file__).resolve().parents[1] / "company" / "delegation"
        return {
            name: (base / name).read_text(encoding="utf-8")
            for name in self.PILOT_SOURCES
        }

    def test_every_pilot_source_exists(self):
        for name, text in self._sources().items():
            assert text, name

    # Checked as *code*, not as text. An earlier version of this test matched
    # bare substrings and failed on the word "socket" inside a docstring that
    # promised the module opens none - which is the wrong way round: prose
    # describing the guarantee should not trip the guarantee. So the scan walks
    # the parsed AST and looks at imports and calls.

    def _trees(self):
        import ast

        base = Path(__file__).resolve().parents[1] / "company" / "delegation"
        for name in self.PILOT_SOURCES:
            yield name, ast.parse((base / name).read_text(encoding="utf-8"))

    FORBIDDEN_MODULES = frozenset(
        {
            "subprocess",
            "socket",
            "urllib",
            "urllib.request",
            "requests",
            "httpx",
            "http",
            "http.client",
            "shutil",
            "os",
            "sys",
            "multiprocessing",
            "threading",
            "asyncio",
        }
    )

    def test_the_pilot_imports_nothing_that_reaches_outside_the_process(self):
        import ast

        for name, tree in self._trees():
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        root = alias.name.split(".")[0]
                        assert root not in self.FORBIDDEN_MODULES, (
                            f"{name} imports {alias.name}"
                        )
                elif isinstance(node, ast.ImportFrom) and node.module:
                    root = node.module.split(".")[0]
                    assert root not in self.FORBIDDEN_MODULES, (
                        f"{name} imports from {node.module}"
                    )

    FORBIDDEN_CALLS = frozenset(
        {"open", "exec", "eval", "compile", "__import__", "input"}
    )

    def test_the_pilot_makes_no_io_or_dynamic_calls(self):
        import ast

        for name, tree in self._trees():
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if isinstance(func, ast.Name):
                    assert func.id not in self.FORBIDDEN_CALLS, (
                        f"{name} calls {func.id}()"
                    )
                elif isinstance(func, ast.Attribute):
                    assert func.attr not in {
                        "write_text",
                        "write_bytes",
                        "unlink",
                        "rmtree",
                        "mkdir",
                        "system",
                        "popen",
                        "run",
                        "check_output",
                        "getenv",
                    }, f"{name} calls .{func.attr}()"

    def test_the_pilot_does_not_drive_git(self):
        # No string literal anywhere in the pilot invokes git. Checked over
        # literals rather than the whole file so that a docstring saying "this
        # cannot run git" does not fail its own promise.
        import ast

        for name, tree in self._trees():
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    literal = node.value.strip().lower()
                    assert not literal.startswith("git "), f"{name}: {literal[:40]!r}"

    def test_main_is_protected_in_source_not_configuration(self):
        text = (
            Path(__file__).resolve().parents[1]
            / "company"
            / "delegation"
            / "pilot_integration.py"
        ).read_text(encoding="utf-8")
        # The protected set is a module constant. If it ever becomes a YAML
        # read, this test fails and the reviewer has to think about why.
        assert "PROTECTED_REFS: frozenset[str] = frozenset(" in text
        assert "load_yaml" not in text

    def test_the_pilot_branch_is_not_main(self):
        assert PILOT_TARGET.branch != "main"
        assert "main" in PILOT_TARGET.protects

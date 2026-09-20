"""Activation: the twenty things that must be true before this mode is on.

The previous pass built bounded routine engineering and proved it works. This
one is about turning it on, which is a different question: not "does the chain
run" but "can this be left enabled without anyone watching it".

The single most important property is the one that is easiest to lose by
accident:

    **Forgetting something must enable nothing.**

`may_activate` defaults `enabled_modes` to shadow only. The CLI requires an
explicit flag. `evaluate_live` requires an activation object passed by hand.
There is no configuration file, no environment variable and no global switch,
because each of those is a thing that can be left in the wrong state.

Sections
    1. the default, and the four ways authority ends
    2. contracts that must be refused before they exist
    3. the ordinary chain, with the CEO absent
    4. the refusals, every one failing closed
    5. the CEO entrypoint
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from ai_platform.resource_classes import Risk
from company.delegation.actions import ActionType
from company.delegation.authority import AuthorityRequest
from company.delegation.errors import DelegationError
from company.delegation.objective_lifecycle import TERMINAL, ObjectiveState
from company.delegation.objectives import PlanningEnvelope
from company.delegation.operating_mode import (
    REQUIRED_CONTRACT_FIELDS,
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
)
from company.finance.money import Money
from company.runtime.config import load_company_config

DAY = dt.date(2026, 9, 20)
REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_FILE = (
    REPO_ROOT
    / "docs"
    / "evidence"
    / "company_os_bounded_engineering_activation"
    / "example_objective_contract.json"
)

OBJ = "obj-engineering-reliability-2026-09-20"
DEV_SEAT = "software_implementation_engineer"
REV_SEAT = "engineering_reviewer"
MGR = "engineering_manager"
DEV_EMP = "software_implementation_engineer"
REV_EMP = "software_review_engineer"
ARCHITECT = "chief_architect"

BOUNDED = (OperatingMode.SHADOW, OperatingMode.BOUNDED_ROUTINE_ENGINEERING)


@pytest.fixture(scope="module")
def config():
    return load_company_config(None)


@pytest.fixture(scope="module")
def policy(config):
    return load_delegation_policy(
        org_registry=config.org_registry, permissions=config.permissions
    )


@pytest.fixture(scope="module")
def raw_contract():
    return json.loads(CONTRACT_FILE.read_text(encoding="utf-8"))


@pytest.fixture
def contract(raw_contract):
    return ObjectiveContract.from_mapping(raw_contract)


@pytest.fixture
def activation(contract):
    plan = PlanningEnvelope(
        objective_id=contract.objective_id,
        budget=contract.budget,
        budget_scope=contract.budget_scope,
        risk_ceiling=contract.risk_ceiling,
        deadline=contract.expires_on,
        allowed_departments=("engineering",),
        success_metrics=contract.success_criteria,
    )
    envelope = PilotEnvelope(
        envelope_id="env-activation",
        objective=contract.objective,
        plan=plan,
        allowed_actions=contract.allowed_actions,
        integration_target=INTERNAL_ENGINEERING_TARGET_SPEC,
        expires_on=contract.expires_on,
        authorized_by=contract.authorized_by,
        max_corrections_per_work_order=contract.max_corrections_per_work_order,
    )
    return PilotActivation(
        activation_id="act-activation",
        envelope=envelope,
        activated_by=contract.authorized_by,
        activated_on=DAY,
        acknowledged_live=True,
        policy_version="delegation_policy_v1",
    )


def _live(policy, activation, action, seat, risk, **kw):
    request = AuthorityRequest(
        request_id=("req-act-" + action.value.replace("_", "-"))[:64],
        action=action,
        requesting_seat=seat,
        department=kw.pop("department", "engineering"),
        risk=risk,
        objective_id=OBJ,
        work_order_id="wo-activation",
        summary="an activation matrix probe",
        implementer=kw.pop("implementer", DEV_EMP),
        reviewer=kw.pop("reviewer", REV_EMP),
        overrides_independent_control=kw.pop("ovr", False),
    )
    kw.setdefault("review_passed", True)
    kw.setdefault("qa_passed", True)
    as_of = kw.pop("as_of", DAY)
    return evaluate_live(
        PilotRequest(request=request, as_of=as_of, **kw),
        policy,
        activation=activation,
        as_of=as_of,
    )


# --- 1. the default, and the four ways authority ends -----------------------


def test_01_absent_contract_means_no_live_authority(policy):
    """Nothing passed, nothing authorized. The whole design rests on this."""
    decision = evaluate_live(
        PilotRequest(
            request=AuthorityRequest(
                request_id="req-act-absent",
                action=ActionType.APPROVE_CODE_CHANGE,
                requesting_seat=DEV_SEAT,
                department="engineering",
                risk=Risk.LOW,
                summary="no contract exists",
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


def test_02_a_shadow_contract_means_no_live_authority(raw_contract):
    shadow = dict(raw_contract)
    shadow["mode"] = "shadow"
    shadow["allowed_actions"] = ["approve_code_change"]
    # A shadow contract may not name allowed actions at all.
    with pytest.raises(DelegationError, match="shadow contract authorizes nothing"):
        ObjectiveContract.from_mapping(shadow)


def test_03_a_valid_bounded_contract_means_live_authority(contract):
    verdict = may_activate(contract, as_of=DAY, enabled_modes=BOUNDED)
    assert verdict.may_activate is True


def test_03b_the_default_enabled_modes_authorize_nothing(contract):
    """Forgetting the argument is the failure mode this guards."""
    assert may_activate(contract, as_of=DAY).may_activate is False


def test_04_an_expired_contract_has_no_authority(contract):
    verdict = may_activate(
        contract, as_of=dt.date(2027, 6, 1), enabled_modes=BOUNDED
    )
    assert verdict.may_activate is False
    assert "expired" in verdict.reason


@pytest.mark.parametrize("state", sorted(TERMINAL, key=lambda item: item.value))
def test_05_a_terminal_objective_has_no_authority(contract, state):
    verdict = may_activate(
        contract, as_of=DAY, enabled_modes=BOUNDED, objective_state=state
    )
    assert verdict.may_activate is False
    assert "finished" in verdict.reason


def test_05b_a_revoked_contract_has_no_authority(contract):
    verdict = may_activate(
        contract, as_of=DAY, enabled_modes=BOUNDED, revoked=True
    )
    assert verdict.may_activate is False
    assert "revoked" in verdict.reason


def test_05c_no_residual_authority_survives_a_finished_objective(contract):
    """Completed, expired and revoked all reach the same answer: no."""
    for kwargs in (
        {"objective_state": ObjectiveState.COMPLETED},
        {"revoked": True},
    ):
        assert (
            may_activate(contract, as_of=DAY, enabled_modes=BOUNDED, **kwargs).may_activate
            is False
        )
    assert (
        may_activate(
            contract, as_of=dt.date(2027, 6, 1), enabled_modes=BOUNDED
        ).may_activate
        is False
    )


# --- 2. contracts refused before they exist ---------------------------------


@pytest.mark.parametrize("field", REQUIRED_CONTRACT_FIELDS)
def test_06_a_missing_required_field_is_refused(raw_contract, field):
    broken = {k: v for k, v in raw_contract.items() if k != field}
    with pytest.raises(DelegationError, match="incomplete and is refused"):
        ObjectiveContract.from_mapping(broken)


def test_06b_an_unknown_field_is_refused(raw_contract):
    extra = dict(raw_contract)
    extra["also_allow"] = ["approve_deployment"]
    with pytest.raises(DelegationError, match="does not understand"):
        ObjectiveContract.from_mapping(extra)


def test_06c_a_non_mapping_is_refused():
    with pytest.raises(DelegationError, match="is a mapping"):
        ObjectiveContract.from_mapping("a contract, honestly")


def test_07_the_wrong_department_is_refused(raw_contract):
    wrong = dict(raw_contract)
    wrong["department"] = "production"
    with pytest.raises(DelegationError, match="bounded routine engineering covers"):
        ObjectiveContract.from_mapping(wrong)


def test_08_excessive_risk_is_refused(raw_contract):
    risky = dict(raw_contract)
    risky["risk_ceiling"] = "high"
    with pytest.raises(DelegationError, match="stops at medium risk"):
        ObjectiveContract.from_mapping(risky)


def test_09_an_excessive_budget_is_bounded_by_the_envelope(policy, activation):
    """The contract carries a budget; spend beyond the envelope is refused live."""
    decision = _live(
        policy,
        activation,
        ActionType.APPROVE_OPERATING_SPEND,
        MGR,
        Risk.MEDIUM,
    )
    assert decision.authorizes_action is False


@pytest.mark.parametrize(
    "action",
    [
        ActionType.CHANGE_DELEGATION_POLICY,
        ActionType.CHANGE_BUDGET_POLICY,
        ActionType.APPROVE_WORKFORCE_STATE_CHANGE,
        ActionType.APPROVE_CANONICAL_MERGE,
        ActionType.APPROVE_DEPLOYMENT,
        ActionType.APPROVE_STAGING_RELEASE,
        ActionType.APPROVE_PRODUCTION_RENDER,
    ],
)
def test_10_a_contract_naming_a_reserved_or_forbidden_action_is_refused(
    raw_contract, action
):
    bad = dict(raw_contract)
    bad["allowed_actions"] = list(raw_contract["allowed_actions"]) + [action.value]
    with pytest.raises(DelegationError, match="no objective contract may allow"):
        ObjectiveContract.from_mapping(bad)


# --- 3. the ordinary chain, CEO absent --------------------------------------


def test_15_the_ordinary_chain_completes_without_the_ceo(policy, activation):
    """developer -> reviewer -> manager -> QA -> CTO -> internal integration."""
    chain = [
        (ActionType.APPROVE_CODE_CHANGE, DEV_SEAT, Risk.LOW, MGR, {}),
        (ActionType.APPROVE_TEST_PROGRESSION, DEV_SEAT, Risk.LOW, MGR, {}),
        (ActionType.APPROVE_REVIEW_OUTCOME, REV_SEAT, Risk.LOW, MGR, {}),
        (
            ActionType.APPROVE_INTEGRATION_MERGE,
            MGR,
            Risk.MEDIUM,
            "cto",
            {"integration_branch": INTERNAL_ENGINEERING_TARGET},
        ),
    ]
    actors = []
    for action, seat, risk, expected, extra in chain:
        decision = _live(policy, activation, action, seat, risk, **extra)
        assert decision.authorizes_action is True, (action.value, decision.reason)
        assert decision.ceo_required is False, action.value
        assert decision.actor == expected, (action.value, decision.actor)
        actors.append(decision.actor)
    assert actors.count(MGR) == 3
    assert actors[-1] == "cto"


def test_15b_the_reviewer_authorizes_nothing(policy):
    assert policy.grant(REV_SEAT) is None


def test_16_one_bounded_correction_stays_internal(activation):
    verdict = authorize_correction(
        "wo-activation",
        activation=activation,
        authorizing_seat=MGR,
        reviewer_said_changes_required=True,
        ledger=CorrectionLedger.empty(),
    )
    assert verdict.permitted is True
    assert verdict.ceo_required is False


def test_17_the_second_correction_stops(activation):
    verdict = authorize_correction(
        "wo-activation",
        activation=activation,
        authorizing_seat=MGR,
        reviewer_said_changes_required=True,
        ledger=CorrectionLedger(counts={"wo-activation": 1}),
    )
    assert verdict.permitted is False
    assert verdict.ceo_required is True


# --- 4. the refusals --------------------------------------------------------


def test_18_qa_failure_stops_progression(policy, activation):
    decision = _live(
        policy,
        activation,
        ActionType.APPROVE_TEST_PROGRESSION,
        DEV_SEAT,
        Risk.LOW,
        qa_passed=False,
    )
    assert decision.authorizes_action is False


def test_18b_an_independent_control_cannot_be_overridden(policy, activation):
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
def test_13_canonical_and_main_promotion_is_refused(policy, activation, branch):
    decision = _live(
        policy,
        activation,
        ActionType.APPROVE_INTEGRATION_MERGE,
        MGR,
        Risk.MEDIUM,
        integration_branch=branch,
    )
    assert decision.authorizes_action is False


@pytest.mark.parametrize(
    "action",
    [
        ActionType.APPROVE_DEPLOYMENT,
        ActionType.APPROVE_STAGING_RELEASE,
        ActionType.APPROVE_PRODUCTION_RENDER,
    ],
)
def test_11_12_deployment_and_publishing_are_refused(policy, activation, action):
    decision = _live(policy, activation, action, MGR, Risk.MEDIUM)
    assert decision.authorizes_action is False
    assert decision.ceo_required is True


@pytest.mark.parametrize(
    "action",
    [
        ActionType.CHANGE_DELEGATION_POLICY,
        ActionType.CHANGE_BUDGET_POLICY,
        ActionType.APPROVE_WORKFORCE_STATE_CHANGE,
    ],
)
def test_14_authority_and_organization_changes_are_refused(policy, activation, action):
    decision = _live(policy, activation, action, MGR, Risk.MEDIUM)
    assert decision.authorizes_action is False
    assert decision.ceo_required is True


def test_19_architecture_review_still_escalates(policy, activation):
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


def test_20_no_executable_work_is_a_clean_terminal_result():
    """It ends the objective and asks the CEO for nothing."""
    from company.delegation.objective_lifecycle import (
        TERMINAL_WITHOUT_CEO,
        ObjectiveHistory,
    )
    from company.delegation.objective_report import CostBreakdown, build_report

    history = ObjectiveHistory(objective_id=OBJ)
    for state, seat in (
        (ObjectiveState.AUTHORIZED, "ceo"),
        (ObjectiveState.PLANNING, MGR),
        (ObjectiveState.NO_EXECUTABLE_WORK, MGR),
    ):
        history = history.with_transition(
            state, at=DAY, actor_seat=seat, reason="the run advanced"
        )
    assert history.state in TERMINAL_WITHOUT_CEO
    report = build_report(
        objective_id=OBJ,
        objective="Improve Company OS reliability",
        contract_id="con-engineering-reliability-2026-09-20",
        history=history,
        budget=Money("6.00", "USD"),
        costs=CostBreakdown(),
        started_on=DAY,
        finished_on=DAY,
        success_criteria=("one improvement",),
    )
    assert report.ceo_action_required().startswith("NONE")
    assert report.interrupted_the_ceo() is False


def test_the_live_risk_ceiling_still_binds(policy, activation):
    decision = _live(
        policy, activation, ActionType.APPROVE_CODE_CHANGE, DEV_SEAT, Risk.HIGH
    )
    assert decision.authorizes_action is False


def test_authority_disappears_the_day_after_expiry(policy, activation):
    decision = _live(
        policy,
        activation,
        ActionType.APPROVE_CODE_CHANGE,
        DEV_SEAT,
        Risk.LOW,
        as_of=dt.date(2027, 1, 1),
    )
    assert decision.authorizes_action is False


# --- 5. the CEO entrypoint --------------------------------------------------


def test_the_shipped_example_contract_is_valid_and_bounded(contract):
    assert contract.mode is OperatingMode.BOUNDED_ROUTINE_ENGINEERING
    assert contract.department == "engineering"
    assert contract.risk_ceiling is Risk.MEDIUM
    assert contract.max_corrections_per_work_order == 1
    assert contract.success_criteria


def test_the_entrypoint_default_is_shadow(tmp_path, raw_contract):
    from company.delegation.__main__ import main

    path = tmp_path / "contract.json"
    path.write_text(json.dumps(raw_contract), encoding="utf-8")
    code = main(
        [
            "objective-contract",
            "--contract-file",
            str(path),
            "--as-of",
            "2026-09-20",
        ]
    )
    assert code != 0, "the default must not report live authority"


def test_the_entrypoint_reports_live_only_when_explicitly_enabled(
    tmp_path, raw_contract
):
    from company.delegation.__main__ import main

    path = tmp_path / "contract.json"
    path.write_text(json.dumps(raw_contract), encoding="utf-8")
    code = main(
        [
            "objective-contract",
            "--contract-file",
            str(path),
            "--as-of",
            "2026-09-20",
            "--enable-bounded-engineering",
        ]
    )
    assert code == 0


def test_the_entrypoint_refuses_an_incomplete_contract(tmp_path, raw_contract):
    from company.delegation.__main__ import main

    broken = {k: v for k, v in raw_contract.items() if k != "risk_ceiling"}
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(broken), encoding="utf-8")
    # `main` turns a DelegationError into a refusal exit code and a message on
    # stderr rather than a traceback, which is what a CLI should do. What
    # matters is that it does not report live authority.
    code = main(
        [
            "objective-contract",
            "--contract-file",
            str(path),
            "--as-of",
            "2026-09-20",
            "--enable-bounded-engineering",
        ]
    )
    assert code != 0
    # And the underlying refusal is the incompleteness one, not something else.
    with pytest.raises(DelegationError, match="incomplete and is refused"):
        ObjectiveContract.from_mapping(broken)


def test_the_canonical_policy_file_never_leaves_shadow():
    text = (REPO_ROOT / "company" / "delegation_policy.yaml").read_text(
        encoding="utf-8"
    )
    assert "\nmode: shadow\n" in text
    assert "enforcing" not in text.split("# --- the hierarchy")[0]


def test_no_module_hardcodes_the_bounded_mode_as_enabled():
    """There is no global switch, and this asserts nobody quietly adds one.

    The risk is a literal `enabled_modes=(..., BOUNDED_ROUTINE_ENGINEERING)`
    somewhere in the runtime, which would turn the mode on for every caller.
    Passing a variable derived from an explicit CLI flag is the supported shape
    and is not an offender - `__main__.py` does exactly that.
    """
    offenders = []
    for path in (REPO_ROOT / "company").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if "enabled_modes=" in stripped and "BOUNDED_ROUTINE_ENGINEERING" in stripped:
                offenders.append(f"{path.name}: {stripped}")
    assert offenders == [], offenders


def test_the_cli_only_enables_the_mode_behind_an_explicit_flag():
    """The one place the mode can be enabled, and what it is conditioned on."""
    source = (
        REPO_ROOT / "company" / "delegation" / "__main__.py"
    ).read_text(encoding="utf-8")
    assert "args.enable_bounded_engineering" in source
    index = source.index("enabled_modes=enabled")
    preamble = source[:index]
    # The variable passed in is chosen by the flag, and shadow is the else.
    assert "if args.enable_bounded_engineering" in preamble
    assert "else (OperatingMode.SHADOW,)" in preamble

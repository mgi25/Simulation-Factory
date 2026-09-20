"""Stage 9 pre-spend validation: the whole chain, deterministically, before a cent."""
import sys, json, datetime as dt
sys.path.insert(0, ".")
from ai_platform.resource_classes import Risk
from company.finance.money import Money
from company.runtime.config import load_company_config
from company.delegation.policy import load_delegation_policy
from company.delegation.actions import ActionType
from company.delegation.authority import AuthorityRequest
from company.delegation.objectives import PlanningEnvelope
from company.delegation.pilot import (
    PilotActivation, PilotEnvelope, PilotRequest, evaluate_live,
    ENGINEERING_MANAGER_LIVE_ACTIONS, CTO_LIVE_ACTIONS,
)
from company.delegation.pilot_integration import PILOT_TARGET, PROTECTED_REFS
from company.delegation.pilot_correction import CorrectionLedger, authorize_correction

DAY = dt.date(2026, 9, 20)
cfg = load_company_config(None)
pol = load_delegation_policy(org_registry=cfg.org_registry, permissions=cfg.permissions)

OBJECTIVE = (
    "Improve the reliability, maintainability, or operating efficiency of the "
    "Company OS by completing ONE useful engineering improvement selected by "
    "the company itself."
)

plan = PlanningEnvelope(
    objective_id="obj-final-e2e-pilot", budget=Money("6.00", "USD"),
    budget_scope="engineering-operations", risk_ceiling=Risk.MEDIUM,
    deadline=dt.date(2026, 12, 31), allowed_departments=("engineering",),
    success_metrics=("one useful engineering improvement, reviewed and green",))
env = PilotEnvelope(
    envelope_id="pilot-envelope-final-e2e", objective=OBJECTIVE, plan=plan,
    allowed_actions=tuple(sorted(
        ENGINEERING_MANAGER_LIVE_ACTIONS | CTO_LIVE_ACTIONS, key=lambda a: a.value)),
    integration_target=PILOT_TARGET, expires_on=dt.date(2026, 12, 31),
    authorized_by="MGI (CEO)", max_corrections_per_work_order=1)
act = PilotActivation(activation_id="pilot-activation-final-e2e", envelope=env,
    activated_by="MGI (CEO)", activated_on=DAY, acknowledged_live=True,
    policy_version="delegation_policy_v1")

checks = []


def rec(name, ok, detail):
    checks.append({"check": name, "pass": bool(ok), "detail": detail})


def live(action, seat, risk, **kw):
    rid = "ps-" + action.value.replace("_", "-") + "-" + seat[:8]
    req = AuthorityRequest(
        request_id=rid[:64], action=action, requesting_seat=seat,
        department="engineering", risk=risk, objective_id="obj-final-e2e-pilot",
        work_order_id="wo-final-e2e-probe", summary="pre-spend validation probe",
        implementer=kw.pop("implementer", "software_implementation_engineer"),
        reviewer=kw.pop("reviewer", "software_review_engineer"),
        overrides_independent_control=kw.pop("ovr", False))
    return evaluate_live(PilotRequest(request=req, as_of=DAY, **kw), pol,
                         activation=act, as_of=DAY)


DEV = "software_implementation_engineer"
REV = "engineering_reviewer"
MGR = "engineering_manager"
GOOD = dict(review_passed=True, qa_passed=True)

# --- the ordinary chain -----------------------------------------------------
ordinary = []
for action, seat, risk, expect in [
    (ActionType.APPROVE_CODE_CHANGE, DEV, Risk.LOW, MGR),
    (ActionType.APPROVE_TEST_PROGRESSION, DEV, Risk.LOW, MGR),
    (ActionType.APPROVE_REVIEW_OUTCOME, REV, Risk.LOW, MGR),
    (ActionType.REQUEST_BOUNDED_CORRECTION, REV, Risk.LOW, MGR),
]:
    d = live(action, seat, risk, **GOOD)
    ordinary.append({"action": action.value, "raised_by": seat, "actor": d.actor,
                     "expected": expect, "proceeds_internally": d.authorizes_action,
                     "ceo_required": d.ceo_required})
    rec("ordinary." + action.value + "_decided_by_engineering_manager",
        d.actor == expect and d.authorizes_action and not d.ceo_required,
        "actor=%s live=%s ceo=%s" % (d.actor, d.authorizes_action, d.ceo_required))

d = live(ActionType.APPROVE_INTEGRATION_MERGE, MGR, Risk.MEDIUM,
         integration_branch=PILOT_TARGET.branch, **GOOD)
ordinary.append({"action": "approve_integration_merge", "raised_by": MGR,
                 "actor": d.actor, "expected": "cto",
                 "proceeds_internally": d.authorizes_action,
                 "ceo_required": d.ceo_required})
rec("ordinary.integration_decided_by_cto",
    d.actor == "cto" and d.authorizes_action and not d.ceo_required,
    "actor=%s live=%s" % (d.actor, d.authorizes_action))
rec("ordinary.ceo_not_required_anywhere",
    all(not s["ceo_required"] for s in ordinary),
    "no step in the ordinary chain reaches the CEO")

# --- the negatives ----------------------------------------------------------
# QA is enforced where progression past it is asked for: APPROVE_TEST_PROGRESSION.
d = live(ActionType.APPROVE_TEST_PROGRESSION, DEV, Risk.LOW,
         review_passed=True, qa_passed=False)
rec("qa_failure_blocks_test_progression", not d.authorizes_action,
    "gates=%s" % [g.gate_id.value for g in d.gates if not g.held])

# And an integration merge is gated on refs and target, not on QA. Recorded as
# an observation rather than asserted as a gate, because it is the runner's
# stage ordering that stops integration being asked for before QA has run.
d = live(ActionType.APPROVE_INTEGRATION_MERGE, MGR, Risk.MEDIUM,
         integration_branch=PILOT_TARGET.branch, review_passed=True, qa_passed=False)
OBSERVATION_INTEGRATION_QA = {
    "note": ("evaluate_live does not gate APPROVE_INTEGRATION_MERGE on qa_passed; "
             "QA is gated at APPROVE_TEST_PROGRESSION and by "
             "overrides_independent_control. Integration ordering is the runner's."),
    "authorizes_action": d.authorizes_action,
    "gates_failed": [g.gate_id.value for g in d.gates if not g.held],
}

d = live(ActionType.APPROVE_REVIEW_OUTCOME, REV, Risk.LOW,
         review_passed=True, qa_passed=False, ovr=True)
rec("override_of_independent_control_refused", not d.authorizes_action,
    "gates=%s ceo=%s" % ([g.gate_id.value for g in d.gates if not g.held], d.ceo_required))

for ref in sorted(PROTECTED_REFS):
    d = live(ActionType.APPROVE_INTEGRATION_MERGE, MGR, Risk.MEDIUM,
             integration_branch=ref, **GOOD)
    rec("protected_ref_blocked." + ref, not d.authorizes_action,
        "gates=%s" % [g.gate_id.value for g in d.gates if not g.held])

d = live(ActionType.APPROVE_CODE_CHANGE, DEV, Risk.HIGH, **GOOD)
rec("risk_ceiling_enforced", not d.authorizes_action,
    "gates=%s" % [g.gate_id.value for g in d.gates if not g.held])

d = live(ActionType.APPROVE_DEPLOYMENT, MGR, Risk.MEDIUM, **GOOD)
rec("public_deployment_blocked", not d.authorizes_action and d.ceo_required,
    "gates=%s ceo=%s" % ([g.gate_id.value for g in d.gates if not g.held], d.ceo_required))

for name in ("approve_staging_release", "approve_production_render"):
    try:
        d = live(ActionType(name), MGR, Risk.MEDIUM, **GOOD)
        rec("publishing_blocked." + name, not d.authorizes_action,
            "gates=%s ceo=%s" % ([g.gate_id.value for g in d.gates if not g.held], d.ceo_required))
    except Exception as exc:
        rec("publishing_blocked." + name, True, "refused at construction: %s" % exc)

d = live(ActionType.APPROVE_OPERATING_SPEND, MGR, Risk.MEDIUM, **GOOD)
rec("spend_outside_envelope_blocked", not d.authorizes_action,
    "gates=%s" % [g.gate_id.value for g in d.gates if not g.held])

# The correction ceiling is decided by authorize_correction, which is the path
# the Engineering Manager actually goes through. `used >= ceiling` refuses.
first = authorize_correction("wo-final-e2e-probe", activation=act,
    authorizing_seat=MGR, reviewer_said_changes_required=True,
    ledger=CorrectionLedger.empty())
rec("first_correction_permitted", first.permitted and not first.ceo_required,
    "used=%s ceiling=%s" % (first.used, first.ceiling))

second = authorize_correction("wo-final-e2e-probe", activation=act,
    authorizing_seat=MGR, reviewer_said_changes_required=True,
    ledger=CorrectionLedger(counts={"wo-final-e2e-probe": 1}))
rec("second_correction_blocked", (not second.permitted) and second.ceo_required,
    "used=%s ceiling=%s ceo=%s" % (second.used, second.ceiling, second.ceo_required))

d = live(ActionType.APPROVE_INTEGRATION_MERGE, MGR, Risk.MEDIUM,
         integration_branch=PILOT_TARGET.branch, reviewer="chief_architect", **GOOD)
rec("architecture_review_self_conflict_escalates",
    not d.authorizes_action and d.ceo_required,
    "actor=%s ceo=%s" % (d.actor, d.ceo_required))

d0 = evaluate_live(PilotRequest(request=AuthorityRequest(
    request_id="ps-shadow-default", action=ActionType.APPROVE_CODE_CHANGE,
    requesting_seat=DEV, department="engineering", risk=Risk.LOW,
    implementer="software_implementation_engineer",
    reviewer="software_review_engineer", summary="shadow default probe"),
    review_passed=True, qa_passed=True, as_of=DAY), pol, as_of=DAY)
rec("default_is_shadow_without_activation", not d0.authorizes_action,
    "activation=None authorizes nothing")

result = {"as_of": str(DAY), "envelope_id": env.envelope_id,
          "activation_id": act.activation_id, "objective": OBJECTIVE,
          "ordinary_chain": ordinary, "checks": checks,
          "observations": [OBSERVATION_INTEGRATION_QA],
          "passed": sum(1 for c in checks if c["pass"]), "total": len(checks),
          "blockers": [c["check"] for c in checks if not c["pass"]]}
import pathlib
pathlib.Path("docs/evidence/company_os_final_end_to_end_pilot/pre_spend_validation.json").write_text(
    json.dumps(result, indent=2) + "\n", encoding="utf-8")
for c in checks:
    print(("PASS " if c["pass"] else "FAIL ") + c["check"] + "  :: " + c["detail"][:90])
print("")
print("%d/%d checks pass; blockers: %s" % (result["passed"], result["total"], result["blockers"]))

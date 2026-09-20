"""The historical scenarios, replayed under live-pilot semantics, before anything runs.

## Why replay and not a fresh test case

A test case proves the code does what its author expected. A replay proves the
code does what *actually happened* — and the value of this company's history is
that it contains real defects, a real correction, a real stopped job and real
money. `scenarios.py` already carries ten of them: five historical jobs and
five counterfactual control probes, each with the recorded outcome and whether
the CEO was actually involved.

Shadow replay asked one question of each: *would the model have needed the
CEO?* Live replay asks a harder one: *would the work have proceeded?* Those
differ, because a live decision has to pass gates a shadow calculation never
saw — an objective envelope, an expiry, an integration target, a correction
ceiling.

## The two envelopes, and why there are two

Nine of the ten scenarios sit under `obj-engineering-operability`. Job C sits
under `obj-finance-usage-accuracy`, because it was a finance-accuracy job that
stopped at pre-flight.

An envelope is scoped to one objective — that is Phase 9's whole point, and
`PilotGateId.OBJECTIVE_MISMATCH` enforces it. So a pilot spanning both
objectives needs the CEO to sign both, and the simulation does exactly that
rather than quietly widening one envelope to cover work it was not signed for.
This is worth stating plainly because the alternative is the failure mode the
envelope exists to prevent: one signature acquiring scope over the next
programme of work.

## The five probes that are new here

`CONTROL_SCENARIOS` predates the pilot, so it has no case for a gate the pilot
invented. Five are added below, and each one is a thing a manager might
plausibly try on an ordinary day:

- **QA failed and progression was requested anyway.** The nearest existing
  probe overrides a control *explicitly*; this one just asks to carry on.
- **Integration onto `main`.** The action is routine and the seat holds it. The
  branch is the whole objection.
- **Integration onto the pilot branch.** Identical to the last one but for the
  branch, and the only probe here that is meant to *succeed*. Without it, the
  `main` probe proves that something refused rather than that the branch was
  what refused - a pilot that blocked every integration would pass it for
  entirely the wrong reason.
- **An expired envelope.** The authority ran out while the work was legitimate.
- **A second bounded correction.** The first was ordinary; the second is spend.

## Where live semantics part company with shadow, and why that is right

One historical scenario changes answer. Job C is a
`stop_work_on_invalid_premise` **requested by the CTO**, so the CTO is
disqualified as the approver of their own request and the chain lands on the
**COO** - who holds the action in the canonical policy and holds no live
authority in this pilot, because Phase 4 named two seats and the COO is not one
of them.

So Job C escalates under live semantics where it resolved internally under
shadow. That is the pilot being narrow, not the pilot being wrong: widening it
to cover the COO would grant live authority the CEO did not delegate. The
number to read is therefore 4 of 5 routine historical decisions internal, with
the fifth escalating for a stated structural reason, and it is reported that
way rather than being smoothed over by adding a seat.

## What this module does not do

It does not run a work order, spend anything, or touch a branch. Every
`LivePilotDecision` it produces is a calculation over a recorded past, and the
pilot is not activated in canonical by any of it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import datetime as dt
from dataclasses import dataclass
from typing import Any

from ai_platform.resource_classes import Risk
from company.finance.money import Money

from .actions import ActionType
from .authority import AuthorityRequest, Decision
from .common import assert_prose, assert_record_id
from .errors import DelegationError
from .objectives import PlanningEnvelope
from .pilot import (
    CTO_LIVE_ACTIONS,
    ENGINEERING_MANAGER_LIVE_ACTIONS,
    LivePilotDecision,
    PilotActivation,
    PilotMode,
    PilotRequest,
    evaluate_live,
)
from .pilot_envelope import PilotEnvelope
from .pilot_integration import PILOT_TARGET
from .policy import DelegationPolicy
from .scenarios import CONTROL_SCENARIOS, SCENARIOS, Scenario


USD = "USD"

# The day the pilot was designed. Every envelope and decision in this replay is
# dated from it, so the result is deterministic and does not change tomorrow.
PILOT_DAY = dt.date(2026, 9, 20)
PILOT_EXPIRY = dt.date(2026, 12, 31)

# The CEO signs an envelope per objective. Both are engineering work; the
# second exists because Job C was filed under the finance-accuracy objective.
ENGINEERING_OBJECTIVE = "obj-engineering-operability"
FINANCE_OBJECTIVE = "obj-finance-usage-accuracy"


def _usd(text: str) -> Money:
    return Money(text, USD)


def _envelope(
    envelope_id: str,
    objective_id: str,
    objective: str,
    budget: str,
    budget_scope: str,
    *,
    allowed: frozenset[ActionType] = ENGINEERING_MANAGER_LIVE_ACTIONS,
    expires_on: dt.date = PILOT_EXPIRY,
) -> PilotEnvelope:
    plan = PlanningEnvelope(
        objective_id=objective_id,
        budget=_usd(budget),
        budget_scope=budget_scope,
        risk_ceiling=Risk.LOW,
        deadline=PILOT_EXPIRY,
        allowed_departments=("engineering",),
        success_metrics=(
            "every work order independently reviewed",
            "deterministic QA green",
            "no new regressions in the full suite",
        ),
    )
    return PilotEnvelope(
        envelope_id=envelope_id,
        objective=objective,
        plan=plan,
        allowed_actions=tuple(sorted(allowed, key=lambda item: item.value)),
        integration_target=PILOT_TARGET,
        expires_on=expires_on,
        authorized_by="MGI (CEO)",
        max_corrections_per_work_order=1,
        success_criteria=(
            "routine engineering progression needs no CEO decision",
            "every exception still reaches the CEO",
        ),
    )


def _activation(
    activation_id: str, envelope: PilotEnvelope, *, activated_on: dt.date = PILOT_DAY
) -> PilotActivation:
    return PilotActivation(
        activation_id=activation_id,
        envelope=envelope,
        activated_by="MGI (CEO)",
        activated_on=activated_on,
        acknowledged_live=True,
        policy_version="delegation_policy_v1",
        notes="bounded live-delegation pilot; routine low-risk engineering only",
    )


# The engineering envelope. Budget is the engineering-operations figure the
# management-staffing report already measured against (18 USD), which is what
# makes the 200 USD control probe land outside it.
ENGINEERING_ENVELOPE = _envelope(
    envelope_id="pilot-envelope-engineering",
    objective_id=ENGINEERING_OBJECTIVE,
    objective="Keep engineering operable: routine low-risk delivery and corrections",
    budget="18.00",
    budget_scope="engineering-operations",
    allowed=frozenset(ENGINEERING_MANAGER_LIVE_ACTIONS | CTO_LIVE_ACTIONS),
)

# The finance-accuracy envelope. Narrower on purpose: the only thing this pilot
# needed to do under it was stop work on a false premise.
FINANCE_ENVELOPE = _envelope(
    envelope_id="pilot-envelope-finance-accuracy",
    objective_id=FINANCE_OBJECTIVE,
    objective="Usage-to-cost accuracy: routine low-risk verification work",
    budget="6.00",
    budget_scope="engineering-operations",
    allowed=frozenset(
        {
            ActionType.STOP_WORK_ON_INVALID_PREMISE,
            ActionType.APPROVE_WORK_ORDER,
            ActionType.APPROVE_CODE_CHANGE,
            ActionType.APPROVE_REVIEW_OUTCOME,
            ActionType.APPROVE_TEST_PROGRESSION,
        }
    ),
)

ENGINEERING_ACTIVATION = _activation("pilot-act-engineering", ENGINEERING_ENVELOPE)
FINANCE_ACTIVATION = _activation("pilot-act-finance-accuracy", FINANCE_ENVELOPE)

# An envelope that has already expired as of PILOT_DAY, for the probe. Signed
# and activated inside its own validity, then read a day too late.
EXPIRED_ENVELOPE = _envelope(
    envelope_id="pilot-envelope-expired",
    objective_id=ENGINEERING_OBJECTIVE,
    objective="An engineering envelope whose authority has run out",
    budget="18.00",
    budget_scope="engineering-operations",
    allowed=frozenset(ENGINEERING_MANAGER_LIVE_ACTIONS),
    expires_on=dt.date(2026, 8, 31),
)
EXPIRED_ACTIVATION = _activation(
    "pilot-act-expired", EXPIRED_ENVELOPE, activated_on=dt.date(2026, 8, 1)
)

# Which activation covers which objective. A request whose objective is in
# neither is outside the pilot, which is the correct answer rather than a gap.
ACTIVATIONS: Mapping[str, PilotActivation] = {
    ENGINEERING_OBJECTIVE: ENGINEERING_ACTIVATION,
    FINANCE_OBJECTIVE: FINANCE_ACTIVATION,
}


# --- per-scenario facts the shadow model never needed ---------------------
#
# Shadow never let anything proceed, so it never had to know whether the review
# had actually passed. Live does. These are read off the recorded history in
# `docs/company_os_management_staffing.md` and the burn-in evidence bundle.
@dataclass(frozen=True)
class ScenarioFacts:
    """The review, QA and branch state of one recorded scenario."""

    review_passed: bool | None = None
    qa_passed: bool | None = None
    integration_branch: str = ""
    corrections_used: int = 0
    note: str = ""


# Where the pilot's correct answer differs from the shadow expectation recorded
# in `scenarios.py`, and why. Anything not named here is expected to answer the
# same way it did in shadow.
PILOT_EXPECTATION: Mapping[str, tuple[bool, str]] = {
    "burnin-job-c": (
        True,
        "the CTO filed this request, so the CTO cannot approve it and the chain "
        "lands on the COO, who holds no live authority in this pilot. Phase 4 "
        "delegated two seats and the COO is not one of them, so the correct "
        "pilot answer is to escalate.",
    ),
}


SCENARIO_FACTS: Mapping[str, ScenarioFacts] = {
    # A clean job: reviewed, QA green, approved.
    "dogfood-2": ScenarioFacts(
        review_passed=True,
        qa_passed=True,
        note="the reviewer accepted it and the suite was green",
    ),
    # Job A as originally filed: the reviewer asked for changes. The decision
    # being replayed is `approve_review_outcome`, and the outcome under review
    # is a changes_required verdict.
    "burnin-job-a": ScenarioFacts(
        review_passed=False,
        qa_passed=None,
        note="the reviewer said changes_required; this is the failed original",
    ),
    # The correction: reviewed again, clean.
    "burnin-correction": ScenarioFacts(
        review_passed=True,
        qa_passed=True,
        corrections_used=1,
        note="the second bounded work order, independently reviewed and green",
    ),
    "burnin-job-b": ScenarioFacts(
        review_passed=True,
        qa_passed=True,
        note="clean, progressed to deterministic QA",
    ),
    # Job C never reached a review: it stopped at pre-flight.
    "burnin-job-c": ScenarioFacts(
        review_passed=None,
        qa_passed=None,
        note="stopped at pre-flight on a premise that turned out to be false",
    ),
    "control-reviewer-as-approver": ScenarioFacts(
        review_passed=True, note="the probe is who approves, not whether it passed"
    ),
    "control-override-independent-control": ScenarioFacts(
        review_passed=False, qa_passed=False, note="the probe overrides a failing control"
    ),
    "control-unknown-deployment": ScenarioFacts(note="an unclassified deployment"),
    "control-spend-above-cfo": ScenarioFacts(note="200 USD against an 18 USD envelope"),
    "control-expand-authority": ScenarioFacts(note="a seat asking to widen itself"),
}


# --- the four probes the pilot invented -----------------------------------


def _probe_request(
    request_id: str,
    action: ActionType,
    *,
    seat: str = "software_implementation_engineer",
    risk: Risk = Risk.LOW,
    objective_id: str = ENGINEERING_OBJECTIVE,
    work_order_id: str = "",
    amount: Money | None = None,
    implementer: str = "software_implementation_engineer",
    reviewer: str = "chief_architect",
    summary: str = "",
) -> AuthorityRequest:
    return AuthorityRequest(
        request_id=request_id,
        action=action,
        requesting_seat=seat,
        department="engineering",
        risk=risk,
        objective_id=objective_id,
        work_order_id=work_order_id,
        budget_scope="engineering-operations",
        amount=amount,
        summary=summary,
        implementer=implementer,
        reviewer=reviewer,
    )


@dataclass(frozen=True)
class PilotProbe:
    """One counterfactual a live pilot makes possible and must refuse."""

    probe_id: str
    label: str
    pilot_request: PilotRequest
    activation: PilotActivation
    expected_ceo_required: bool
    expectation: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "probe_id", assert_record_id(self.probe_id, "probe.probe_id")
        )
        object.__setattr__(self, "label", assert_prose(self.label, "probe.label"))
        if not isinstance(self.pilot_request, PilotRequest):
            raise DelegationError("probe.pilot_request must be a PilotRequest")
        if not isinstance(self.activation, PilotActivation):
            raise DelegationError("probe.activation must be a PilotActivation")

    def to_dict(self) -> dict[str, Any]:
        return {
            "probe_id": self.probe_id,
            "label": self.label,
            "request": self.pilot_request.to_dict(),
            "activation_id": self.activation.activation_id,
            "expected_ceo_required": self.expected_ceo_required,
            "expectation": self.expectation,
        }


PILOT_PROBES: tuple[PilotProbe, ...] = (
    PilotProbe(
        probe_id="pilot-probe-qa-failed",
        label="QA failed and progression was requested anyway",
        pilot_request=PilotRequest(
            request=_probe_request(
                "pilot-probe-qa-failed-req",
                ActionType.APPROVE_TEST_PROGRESSION,
                work_order_id="wo-probe-qa-failed",
                summary="Continue past a deterministic QA run that failed",
            ),
            review_passed=True,
            qa_passed=False,
            as_of=PILOT_DAY,
        ),
        activation=ENGINEERING_ACTIVATION,
        expected_ceo_required=True,
        expectation=(
            "deterministic QA is not a judgement a manager may continue past; the "
            "action and the seat are both routine and the failing run is the objection"
        ),
    ),
    PilotProbe(
        probe_id="pilot-probe-integrate-main",
        label="A routine integration, aimed at main",
        pilot_request=PilotRequest(
            request=_probe_request(
                "pilot-probe-integrate-main-req",
                ActionType.APPROVE_INTEGRATION_MERGE,
                work_order_id="wo-probe-integrate-main",
                # The reviewer is the AI platform lead rather than the CTO, so
                # that the CTO is not disqualified as the reviewer of the work
                # they are being asked to integrate. The point of this probe is
                # the branch, so every other objection is cleared out of the way.
                reviewer="ai_efficiency_platform_engineer",
                summary="Integrate reviewed work onto main",
            ),
            review_passed=True,
            qa_passed=True,
            integration_branch="main",
            as_of=PILOT_DAY,
        ),
        activation=ENGINEERING_ACTIVATION,
        expected_ceo_required=True,
        expectation=(
            "the CTO holds approve_integration_merge and the work is reviewed and "
            "green; main is a protected ref and no envelope, grant or seat can "
            "name it, so the branch is the only objection left"
        ),
    ),
    PilotProbe(
        probe_id="pilot-probe-integrate-internal",
        label="The same integration, aimed at the pilot branch",
        pilot_request=PilotRequest(
            request=_probe_request(
                "pilot-probe-integrate-internal-req",
                ActionType.APPROVE_INTEGRATION_MERGE,
                work_order_id="wo-probe-integrate-internal",
                reviewer="ai_efficiency_platform_engineer",
                summary="Integrate reviewed work onto the pilot integration branch",
            ),
            review_passed=True,
            qa_passed=True,
            integration_branch=PILOT_TARGET.branch,
            as_of=PILOT_DAY,
        ),
        activation=ENGINEERING_ACTIVATION,
        expected_ceo_required=False,
        # The one probe here that is meant to SUCCEED. Without it the branch
        # guard above proves only that something refused, not that the branch is
        # what it refused: a pilot that blocks every integration would pass the
        # main probe for the wrong reason.
        expectation=(
            "identical to the main probe except for the branch; this is Phase 5's "
            "claim that work can be internally accepted without the CEO"
        ),
    ),
    PilotProbe(
        probe_id="pilot-probe-expired-envelope",
        label="Legitimate routine work under an envelope that has expired",
        pilot_request=PilotRequest(
            request=_probe_request(
                "pilot-probe-expired-req",
                ActionType.APPROVE_CODE_CHANGE,
                work_order_id="wo-probe-expired",
                amount=_usd("1.50"),
                summary="An ordinary low-risk change, after the authority ran out",
            ),
            review_passed=True,
            qa_passed=True,
            as_of=PILOT_DAY,
        ),
        activation=EXPIRED_ACTIVATION,
        expected_ceo_required=True,
        expectation=(
            "nothing is wrong with the work; the authority to approve it without "
            "the CEO expired on 2026-08-31"
        ),
    ),
    PilotProbe(
        probe_id="pilot-probe-second-correction",
        label="A second bounded correction on one work order",
        pilot_request=PilotRequest(
            request=_probe_request(
                "pilot-probe-second-correction-req",
                ActionType.REQUEST_BOUNDED_CORRECTION,
                work_order_id="wo-probe-second-correction",
                amount=_usd("1.20"),
                summary="Authorize a further correction after the first was spent",
            ),
            review_passed=False,
            qa_passed=None,
            corrections_used=2,
            as_of=PILOT_DAY,
        ),
        activation=ENGINEERING_ACTIVATION,
        expected_ceo_required=True,
        expectation=(
            "one bounded correction is ordinary engineering; the second is "
            "exceptional spend on a consumer subscription and is the CEO's call"
        ),
    ),
)


# --- the replay -----------------------------------------------------------


@dataclass(frozen=True)
class PilotReplayResult:
    """What live-pilot semantics said about one recorded scenario."""

    scenario_id: str
    label: str
    live: LivePilotDecision
    expected_ceo_required: bool
    actual_ceo_involved: bool | None = None
    historical: bool = True
    note: str = ""
    # Set only where the pilot's correct answer differs from the shadow
    # expectation, with the reason. `matches_expectation` measures against this
    # when it is present, and `differs_from_shadow` stays True so the difference
    # is reported rather than hidden behind a passing number.
    pilot_expected_ceo_required: bool | None = None
    divergence_reason: str = ""

    @property
    def proceeded_internally(self) -> bool:
        return self.live.authorizes_action and not self.live.ceo_required

    @property
    def effective_expectation(self) -> bool:
        if self.pilot_expected_ceo_required is None:
            return self.expected_ceo_required
        return self.pilot_expected_ceo_required

    @property
    def differs_from_shadow(self) -> bool:
        return self.live.ceo_required != self.expected_ceo_required

    @property
    def matches_expectation(self) -> bool:
        return self.live.ceo_required == self.effective_expectation

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "label": self.label,
            "mode": self.live.mode.value,
            "decision": self.live.decision.value,
            "actor": self.live.actor,
            "authorizes_action": self.live.authorizes_action,
            "ceo_required": self.live.ceo_required,
            "expected_ceo_required": self.expected_ceo_required,
            "pilot_expected_ceo_required": self.pilot_expected_ceo_required,
            "matches_expectation": self.matches_expectation,
            "differs_from_shadow": self.differs_from_shadow,
            "divergence_reason": self.divergence_reason,
            "proceeded_internally": self.proceeded_internally,
            "actual_ceo_involved": self.actual_ceo_involved,
            "historical": self.historical,
            "reason": self.live.reason,
            "failed_gates": [item.gate_id.value for item in self.live.failed_gates],
            "gates_checked": len(self.live.gates),
            "note": self.note,
        }


def _pilot_request_for(scenario: Scenario) -> PilotRequest:
    facts = SCENARIO_FACTS.get(scenario.scenario_id, ScenarioFacts())
    return PilotRequest(
        request=scenario.request,
        integration_branch=facts.integration_branch,
        review_passed=facts.review_passed,
        qa_passed=facts.qa_passed,
        corrections_used=facts.corrections_used,
        as_of=PILOT_DAY,
    )


def _activation_for(scenario: Scenario) -> PilotActivation | None:
    return ACTIVATIONS.get(scenario.request.objective_id)


def replay_live(
    policy: DelegationPolicy,
    scenarios: Sequence[Scenario] = SCENARIOS,
    *,
    as_of: dt.date = PILOT_DAY,
) -> tuple[PilotReplayResult, ...]:
    """Every scenario, through live-pilot semantics, in order."""
    results: list[PilotReplayResult] = []
    for scenario in scenarios:
        pilot_request = _pilot_request_for(scenario)
        activation = _activation_for(scenario)
        live = evaluate_live(
            pilot_request,
            policy,
            activation=activation,
            as_of=as_of,
        )
        facts = SCENARIO_FACTS.get(scenario.scenario_id, ScenarioFacts())
        override = PILOT_EXPECTATION.get(scenario.scenario_id)
        results.append(
            PilotReplayResult(
                scenario_id=scenario.scenario_id,
                label=scenario.label,
                live=live,
                expected_ceo_required=scenario.expected_ceo_required,
                actual_ceo_involved=scenario.actual_ceo_involved,
                historical=scenario.historical,
                note=facts.note,
                pilot_expected_ceo_required=override[0] if override else None,
                divergence_reason=override[1] if override else "",
            )
        )
    return tuple(results)


def replay_probes(
    policy: DelegationPolicy,
    probes: Sequence[PilotProbe] = PILOT_PROBES,
    *,
    as_of: dt.date = PILOT_DAY,
) -> tuple[PilotReplayResult, ...]:
    """The pilot's own counterfactuals, which must all reach the CEO."""
    results: list[PilotReplayResult] = []
    for probe in probes:
        live = evaluate_live(
            probe.pilot_request,
            policy,
            activation=probe.activation,
            as_of=as_of,
        )
        results.append(
            PilotReplayResult(
                scenario_id=probe.probe_id,
                label=probe.label,
                live=live,
                expected_ceo_required=probe.expected_ceo_required,
                actual_ceo_involved=None,
                historical=False,
                note=probe.expectation,
            )
        )
    return tuple(results)


def replay_shadow_default(
    policy: DelegationPolicy,
    scenarios: Sequence[Scenario] = SCENARIOS,
) -> tuple[PilotReplayResult, ...]:
    """The same scenarios with no activation, proving the default is shadow.

    Every result here must have `authorizes_action=False`. It is the same code
    path the pilot uses, called the way canonical calls it.
    """
    results: list[PilotReplayResult] = []
    for scenario in scenarios:
        live = evaluate_live(_pilot_request_for(scenario), policy, activation=None)
        results.append(
            PilotReplayResult(
                scenario_id=scenario.scenario_id,
                label=scenario.label,
                live=live,
                expected_ceo_required=scenario.expected_ceo_required,
                actual_ceo_involved=scenario.actual_ceo_involved,
                historical=scenario.historical,
                note="no activation supplied: shadow",
            )
        )
    return tuple(results)


def summarise_live(results: Sequence[PilotReplayResult]) -> dict[str, Any]:
    """The numbers a stop condition quotes."""
    internal = [item for item in results if item.proceeded_internally]
    ceo = [item for item in results if item.live.ceo_required]
    mismatched = [item for item in results if not item.matches_expectation]
    authorized = [item for item in results if item.live.authorizes_action]
    diverged = [item for item in results if item.differs_from_shadow]
    return {
        "total": len(results),
        "proceeded_internally": len(internal),
        "ceo_required": len(ceo),
        "matches_expectation": len(results) - len(mismatched),
        "mismatched": [item.scenario_id for item in mismatched],
        "diverged_from_shadow": [
            {"scenario_id": item.scenario_id, "reason": item.divergence_reason}
            for item in diverged
        ],
        "authorized_actions": [item.scenario_id for item in authorized],
        "internal": [item.scenario_id for item in internal],
        "escalated": [item.scenario_id for item in ceo],
        "results": [item.to_dict() for item in results],
    }


def run_full_simulation(policy: DelegationPolicy) -> dict[str, Any]:
    """Every replay this phase claims, in one deterministic answer."""
    historical = replay_live(policy, SCENARIOS)
    controls = replay_live(policy, CONTROL_SCENARIOS)
    probes = replay_probes(policy)
    shadow = replay_shadow_default(policy, SCENARIOS)
    return {
        "as_of": PILOT_DAY.isoformat(),
        "envelopes": {
            ENGINEERING_OBJECTIVE: ENGINEERING_ENVELOPE.to_dict(),
            FINANCE_OBJECTIVE: FINANCE_ENVELOPE.to_dict(),
        },
        "historical": summarise_live(historical),
        "controls": summarise_live(controls),
        "pilot_probes": summarise_live(probes),
        "shadow_default": {
            "total": len(shadow),
            "authorized_any": any(item.live.authorizes_action for item in shadow),
            "all_shadow_mode": all(
                item.live.mode is PilotMode.SHADOW for item in shadow
            ),
        },
    }


__all__ = [
    "ACTIVATIONS",
    "ENGINEERING_ACTIVATION",
    "ENGINEERING_ENVELOPE",
    "ENGINEERING_OBJECTIVE",
    "EXPIRED_ACTIVATION",
    "FINANCE_ACTIVATION",
    "FINANCE_ENVELOPE",
    "FINANCE_OBJECTIVE",
    "PILOT_DAY",
    "PILOT_EXPECTATION",
    "PILOT_PROBES",
    "PilotProbe",
    "PilotReplayResult",
    "ScenarioFacts",
    "SCENARIO_FACTS",
    "replay_live",
    "replay_probes",
    "replay_shadow_default",
    "run_full_simulation",
    "summarise_live",
]

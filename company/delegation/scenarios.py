"""Five real jobs Company OS already ran, replayed against the delegation model.

This is the validation step for the whole phase. The model is new, so nothing
can be inferred from it running; what can be inferred is whether it reaches the
same conclusions as five decisions the company already took and documented.

## What is replayed, and what is emphatically not

Replayed: the authority calculation. Given what each job actually was — its
department, its action, its recorded risk, its real provider-reported cost —
which seat would have owned it, could that seat have approved it, and would the
CEO have been needed.

Not replayed: anything that spends money or changes history. No model session
runs, no receipt is re-validated, no stored record in any state directory is
read or written, and no historical document is edited. Every scenario below is
a frozen declaration transcribed from the reports named in its `evidence`
field, and `python -m company.delegation replay` is a pure function of this
module plus the policy file.

## Why the scenarios are transcribed rather than read from a store

The five jobs ran on four different branches, and their state directories are
either outside this repository or absent from this one. Reading them would make
this module depend on which worktree it is executed from — the replay would
pass on one machine and be UNAVAILABLE on another, which is the least useful
possible property for a validation step.

So the facts are written down here with the report and line each came from, the
transcription is small enough to check by eye, and `tests/` asserts the
transcribed costs against the totals those reports state. A number here that
drifts from its source is a test failure, not a silent wrong answer.

## The expected direction

| Scenario | Expected |
|---|---|
| Dogfood #2, clean run | handled below the CEO |
| Job A, reviewer found a real defect | the correction path is a manager decision |
| the correction job | handled below the CEO |
| Job B, trivial and clean | handled below the CEO |
| Job C, invalid premise at pre-flight | stopped by the department, no CEO |

`replay` reports where the model agrees and where it does not. A disagreement
is a finding about the policy, not an error — and the ones this phase found are
written up in `docs/company_os_executive_delegation.md`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ai_platform.resource_classes import Risk
from company.finance.money import Money

from .actions import ActionType
from .authority import AuthorityDecision, AuthorityRequest, Decision, evaluate
from .exceptions import ExceptionContext, ExceptionReport, classify
from .policy import DelegationPolicy


USD = "USD"


@dataclass(frozen=True)
class Scenario:
    """One historical job, and what actually happened to it."""

    scenario_id: str
    label: str
    request: AuthorityRequest
    context: ExceptionContext
    actual_outcome: str
    actual_ceo_involved: bool
    expected_ceo_required: bool
    expectation: str
    evidence: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "label": self.label,
            "request": self.request.to_dict(),
            "actual_outcome": self.actual_outcome,
            "actual_ceo_involved": self.actual_ceo_involved,
            "expected_ceo_required": self.expected_ceo_required,
            "expectation": self.expectation,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class ReplayResult:
    """What the model said about one scenario, and whether that matches."""

    scenario: Scenario
    decision: AuthorityDecision
    exceptions: ExceptionReport

    @property
    def owning_seat(self) -> str:
        return self.decision.actor

    @property
    def matches_expectation(self) -> bool:
        return self.decision.ceo_required == self.scenario.expected_ceo_required

    @property
    def matches_history(self) -> bool:
        """Whether the model needs the CEO exactly where history did."""
        return self.decision.ceo_required == self.scenario.actual_ceo_involved

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario.scenario_id,
            "label": self.scenario.label,
            "owning_seat": self.owning_seat,
            "decision": self.decision.decision.value,
            "ceo_required": self.decision.ceo_required,
            "expected_ceo_required": self.scenario.expected_ceo_required,
            "actual_ceo_involved": self.scenario.actual_ceo_involved,
            "matches_expectation": self.matches_expectation,
            "matches_history": self.matches_history,
            "reason": self.decision.reason,
            "exception_classes": [item.value for item in self.exceptions.classes],
            "chain": [step.to_dict() for step in self.decision.chain],
            "evidence": list(self.scenario.evidence),
        }


def _usd(text: str) -> Money:
    return Money(text, USD)


# --- the five scenarios ----------------------------------------------------
#
# Every figure below is transcribed from the report named in `evidence`.


DOGFOOD_2 = Scenario(
    scenario_id="dogfood-2",
    label="Dogfood #2: developer_attempts_remaining on the CEO result page",
    request=AuthorityRequest(
        request_id="replay-dogfood-2",
        action=ActionType.APPROVE_CODE_CHANGE,
        requesting_seat="software_implementation_engineer",
        department="engineering",
        risk=Risk.LOW,
        objective_id="obj-engineering-operability",
        work_order_id="wo-req-ceo-page-attempts-remaining",
        budget_scope="engineering-operations",
        amount=_usd("2.157688"),
        summary=(
            "Add attempts-remaining to EngineeringResult and show it on the CEO page; "
            "reviewer PASS, gate READY, ready_for_approval"
        ),
        evidence_refs=("docs/company_os_second_real_dogfood.md",),
    ),
    context=ExceptionContext(failed_attempts=0, attempt_ceiling=1),
    actual_outcome="ready_for_approval, reviewer PASS, gate READY, no CEO decision recorded",
    actual_ceo_involved=True,
    expected_ceo_required=False,
    expectation=(
        "a clean low-risk engineering change inside budget should be owned by the "
        "engineering management layer, not the CEO"
    ),
    evidence=("docs/company_os_second_real_dogfood.md",),
)


JOB_A_ORIGINAL = Scenario(
    scenario_id="burnin-job-a",
    label="Job A: legacy attempts-remaining default, reviewer found a real defect",
    request=AuthorityRequest(
        request_id="replay-burnin-job-a",
        action=ActionType.APPROVE_REVIEW_OUTCOME,
        requesting_seat="cto",
        department="engineering",
        risk=Risk.LOW,
        objective_id="obj-engineering-operability",
        work_order_id="wo-req-legacy-attempts-remaining-default",
        budget_scope="engineering-operations",
        amount=_usd("1.0636907499999999"),
        summary=(
            "Reviewer verdict changes_required on a real round-trip TypeError the "
            "deterministic suite did not cover; the single authorized attempt is spent"
        ),
        evidence_refs=("docs/company_os_supervised_burnin.md",),
    ),
    context=ExceptionContext(
        failed_attempts=1,
        attempt_ceiling=1,
        reviewer_disputed=False,
    ),
    actual_outcome=(
        "decision_required: the one authorized developer attempt is spent and review "
        "still requires changes"
    ),
    actual_ceo_involved=True,
    expected_ceo_required=True,
    expectation=(
        "the reviewer finding itself is a manager decision, but a work order whose "
        "attempt ceiling is spent needs a new authorization, which is a level up"
    ),
    evidence=("docs/company_os_supervised_burnin.md",),
)


JOB_A_CORRECTION = Scenario(
    scenario_id="burnin-correction",
    label="Correction job: null-safe attempts-remaining, clean run",
    request=AuthorityRequest(
        request_id="replay-burnin-correction",
        action=ActionType.APPROVE_CODE_CHANGE,
        requesting_seat="software_implementation_engineer",
        department="engineering",
        risk=Risk.LOW,
        objective_id="obj-engineering-operability",
        work_order_id="wo-req-attempts-remaining-null-safe",
        budget_scope="engineering-operations",
        amount=_usd("1.1758087499999998"),
        summary=(
            "Reviewer PASS, gate READY, ready_for_approval; one developer attempt, "
            "one reviewer pass, zero retries"
        ),
        evidence_refs=("docs/company_os_supervised_burnin_correction.md",),
    ),
    context=ExceptionContext(failed_attempts=0, attempt_ceiling=1),
    actual_outcome="ready_for_approval, awaiting the CEO decision gate",
    actual_ceo_involved=True,
    expected_ceo_required=False,
    expectation=(
        "a bounded correction that passed review and the gate is the routine case "
        "delegation exists for"
    ),
    evidence=("docs/company_os_supervised_burnin_correction.md",),
)


JOB_B = Scenario(
    scenario_id="burnin-job-b",
    label="Job B: test section-header renumbering, four lines, reviewer PASS",
    request=AuthorityRequest(
        request_id="replay-burnin-job-b",
        action=ActionType.APPROVE_TEST_PROGRESSION,
        requesting_seat="software_implementation_engineer",
        department="engineering",
        risk=Risk.LOW,
        objective_id="obj-engineering-operability",
        work_order_id="wo-req-test-section-header-renumber",
        budget_scope="engineering-operations",
        amount=_usd("0.5538657499999999"),
        summary=(
            "Four lines changed in one test file, 140 passed unchanged, reviewer PASS "
            "with no findings, gate READY 11/11"
        ),
        evidence_refs=("docs/company_os_supervised_burnin_b_and_c.md",),
    ),
    context=ExceptionContext(failed_attempts=0, attempt_ceiling=1),
    actual_outcome="ready_for_approval, gate READY, no CEO decision recorded",
    actual_ceo_involved=True,
    expected_ceo_required=False,
    expectation=(
        "the most routine change the company has ever run; if this needs the CEO, "
        "nothing is delegable"
    ),
    evidence=("docs/company_os_supervised_burnin_b_and_c.md",),
)


JOB_C = Scenario(
    scenario_id="burnin-job-c",
    label="Job C: stopped at the schema pre-flight, never submitted",
    request=AuthorityRequest(
        request_id="replay-burnin-job-c",
        action=ActionType.STOP_WORK_ON_INVALID_PREMISE,
        requesting_seat="cto",
        department="engineering",
        risk=Risk.LOW,
        objective_id="obj-finance-usage-accuracy",
        summary=(
            "The brief assumed a stable per-event identifier in ResourceUsageRecord; "
            "no such field exists, so no request was submitted and no session ran"
        ),
        evidence_refs=(
            "docs/evidence/company_os_supervised_burnin/job_c/SCHEMA_PREFLIGHT_STOP.md",
        ),
    ),
    context=ExceptionContext(),
    actual_outcome="stopped before intake; nothing was spent and no work order exists",
    actual_ceo_involved=False,
    expected_ceo_required=False,
    expectation=(
        "stopping work on a premise that turned out to be false is exactly what a "
        "department should be able to do without asking"
    ),
    evidence=(
        "docs/evidence/company_os_supervised_burnin/job_c/SCHEMA_PREFLIGHT_STOP.md",
    ),
)


SCENARIOS: tuple[Scenario, ...] = (
    DOGFOOD_2,
    JOB_A_ORIGINAL,
    JOB_A_CORRECTION,
    JOB_B,
    JOB_C,
)

# The real provider-reported totals the transcriptions above must match, as the
# reports state them. Asserted by the tests so a transcription cannot drift.
REPORTED_TOTALS: dict[str, str] = {
    "dogfood-2": "2.157688",
    "burnin-job-a": "1.0636907499999999",
    "burnin-correction": "1.1758087499999998",
    "burnin-job-b": "0.5538657499999999",
}


def replay(
    policy: DelegationPolicy,
    *,
    scenarios: Sequence[Scenario] = SCENARIOS,
    consumed: dict[str, Money] | None = None,
) -> tuple[ReplayResult, ...]:
    """Run every scenario through the model. Pure, and spends nothing."""
    out: list[ReplayResult] = []
    for scenario in scenarios:
        decision = evaluate(scenario.request, policy, consumed=consumed)
        report = classify(
            decision, scenario.context, evidence_refs=scenario.evidence
        )
        out.append(
            ReplayResult(scenario=scenario, decision=decision, exceptions=report)
        )
    return tuple(out)


def summarise(results: Sequence[ReplayResult]) -> dict[str, Any]:
    """The counts a stop condition quotes, plus the disagreements by name."""
    total_count = len(results)
    matched = [item for item in results if item.matches_expectation]
    ceo_needed = [item for item in results if item.decision.ceo_required]
    approved = [
        item for item in results if item.decision.decision is Decision.APPROVED
    ]
    return {
        "scenarios": total_count,
        "matching_expectation": len(matched),
        "disagreements": [
            {
                "scenario_id": item.scenario.scenario_id,
                "expected_ceo_required": item.scenario.expected_ceo_required,
                "model_ceo_required": item.decision.ceo_required,
                "owning_seat": item.owning_seat,
                "reason": item.decision.reason,
            }
            for item in results
            if not item.matches_expectation
        ],
        "ceo_required": [item.scenario.scenario_id for item in ceo_needed],
        "approved_below_ceo": [item.scenario.scenario_id for item in approved],
        "results": [item.to_dict() for item in results],
    }


__all__ = [
    "REPORTED_TOTALS",
    "SCENARIOS",
    "ReplayResult",
    "Scenario",
    "replay",
    "summarise",
]

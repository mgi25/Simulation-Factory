"""From a CEO objective to one bounded work order, by decision rather than guess.

This is the rung the first live-delegation pilot found empty. The pilot handed
Company OS an objective - "complete one genuinely useful LOW-risk engineering
improvement" - and intake authorized it, copied it verbatim into a work order,
derived the criterion *"The stated objective is implemented: <the objective>"*,
and told the developer to work out what the contract was. The company had not
planned; it had deferred planning to whoever was cheapest.

```
CEO objective + planning envelope
    -> eligible_candidates()     ten deterministic constraints, no judgement
    -> select_work()             one manager, one executive, one record
    -> propose_work_order()      narrowed, never widened
    -> company.engineering.intake deterministic intake, as before
```

## Why eligibility is deterministic and selection is not

Eligibility asks *may this candidate be chosen* - a question about departments,
capsules, risk, money, dependencies and evidence, every one of which is a
comparison. Ten comparisons, in `ELIGIBILITY_CHECKS`, each with a name that
appears in the record. No embedding, no similarity score, no model call, and
none is needed: a constraint that cannot be computed is a constraint nobody can
appeal.

Selection asks *which of the eligible ones should we do*, which is a judgement.
Today `select_work` takes the deterministic default - the single eligible
candidate, or the caller's explicit choice among several - and refuses to
invent a preference it cannot justify. `EXECUTIVE_CHOICE_CONTRACT` describes
what a model-assisted planner would have to supply to make that judgement
instead. No paid executive session runs here.

## Why an empty result is a real answer

`NO_ELIGIBLE_WORK_CANDIDATE` is an outcome, not a failure. The whole defect
this module exists to fix was a system that produced *something* for every
objective, because producing nothing felt like breakage. A company with no
eligible low-risk work should say so and let the CEO decide whether to fund
discovery, widen the envelope, or wait. What it must never do is manufacture a
vague work order so the pipeline has something to carry.

## Narrowing, and why widening is refused rather than warned

`propose_work_order` takes the candidate's declared scope, risk and criteria and
lets management make them smaller. Every attempt to make one larger raises,
because the envelope and the candidate are the two records a reviewer will
check the finished work against, and a work order that quietly exceeded both is
not reviewable against anything.
"""

from __future__ import annotations

from collections.abc import Sequence
import datetime as dt
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ai_platform.resource_classes import Risk
from company.engineering.criteria import is_falsifiable_criterion
from company.finance.money import Money

from .actions import ActionType
from .candidates import CandidateRegister, CandidateStatus, WorkCandidate
from .common import assert_prose, assert_record_id
from .errors import AuthorityViolation, DelegationError
from .objectives import Objective, ObjectiveLevel, PlanningEnvelope
from .planning_record import PlanningDecisionRecord, PlanningOutcome
from .policy import risk_rank


class EligibilityCheck(str, Enum):
    """The ten constraints, named so a rejection can cite one."""

    DEPARTMENT_PERMITTED = "department_permitted"
    CAPSULE_OWNED = "capsule_owned"
    STATUS_OPEN = "status_open"
    RISK_WITHIN_CEILING = "risk_within_ceiling"
    COST_WITHIN_BUDGET = "cost_within_budget"
    NO_FORBIDDEN_ACTION = "no_forbidden_action"
    DEPENDENCIES_SATISFIED = "dependencies_satisfied"
    CRITERIA_FALSIFIABLE = "criteria_falsifiable"
    EVIDENCE_PRESENT = "evidence_present"
    GOAL_OVERLAP = "goal_overlap"


ELIGIBILITY_CHECKS: tuple[EligibilityCheck, ...] = tuple(EligibilityCheck)

EXECUTIVE_CHOICE_CONTRACT: tuple[str, ...] = (
    "input: the eligible candidates, each with problem_statement, expected_value, "
    "risk, estimated_cost and evidence_refs",
    "input: the CEO objective title, success metrics and the planning envelope",
    "output: exactly one candidate_id drawn from the eligible set, never a new one",
    "output: a selection_reason naming what the rejected candidates lacked",
    "refusal: a choice outside the eligible set is discarded, not honoured",
    "refusal: the planner may not alter risk, scope, budget or acceptance criteria",
    "budget: the planning session counts against the objective envelope like any "
    "other model process",
)
"""What a model-assisted planner would have to honour. Nothing calls this yet."""


@dataclass(frozen=True)
class CandidateEligibility:
    """One candidate measured against one envelope, check by check."""

    candidate_id: str
    eligible: bool
    passed: tuple[EligibilityCheck, ...]
    failed: tuple[EligibilityCheck, ...]
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "eligible": self.eligible,
            "passed": [item.value for item in self.passed],
            "failed": [item.value for item in self.failed],
            "reasons": list(self.reasons),
        }


def assess_candidate(
    candidate: WorkCandidate,
    objective: Objective,
    envelope: PlanningEnvelope,
    *,
    capsule_ids: Sequence[str],
    register: CandidateRegister | None = None,
    reserved_actions: Sequence[ActionType] = (),
    objective_goal_tags: Sequence[str] = (),
) -> CandidateEligibility:
    """Run the ten checks. Every failure names the check and says why.

    `capsule_ids` is the set of capsules the caller confirmed exist and belong
    to the allowed departments. An empty set fails every candidate rather than
    passing them: ownership that cannot be confirmed is not ownership, and the
    register is the wrong place to learn which capsules the company has.
    """
    if not isinstance(candidate, WorkCandidate):
        raise DelegationError("assess_candidate takes a WorkCandidate")
    if not isinstance(objective, Objective):
        raise DelegationError("assess_candidate takes an Objective")
    if not isinstance(envelope, PlanningEnvelope):
        raise DelegationError("assess_candidate takes a PlanningEnvelope")

    owned = {str(item).strip() for item in (capsule_ids or ()) if str(item).strip()}
    reserved = set(reserved_actions or ())
    forbidden = set(envelope.forbidden_actions)
    passed: list[EligibilityCheck] = []
    failed: list[EligibilityCheck] = []
    reasons: list[str] = []

    def record(check: EligibilityCheck, ok: bool, why: str) -> None:
        if ok:
            passed.append(check)
        else:
            failed.append(check)
            reasons.append(f"{check.value}: {why}")

    allowed_departments = set(envelope.allowed_departments)
    record(
        EligibilityCheck.DEPARTMENT_PERMITTED,
        candidate.department in allowed_departments,
        f"{candidate.department} is not among the envelope's departments "
        f"({', '.join(sorted(allowed_departments)) or 'none declared'})",
    )
    record(
        EligibilityCheck.CAPSULE_OWNED,
        candidate.capsule_id in owned,
        f"no confirmed capsule owns {candidate.capsule_id}; work whose owner the "
        "company cannot name has no declared scope, tests or invariants to be "
        "reviewed against",
    )
    record(
        EligibilityCheck.STATUS_OPEN,
        candidate.status is CandidateStatus.OPEN,
        f"status is {candidate.status.value}"
        + (
            f" ({'; '.join(candidate.blocked_by)})"
            if candidate.blocked_by
            else ""
        ),
    )
    record(
        EligibilityCheck.RISK_WITHIN_CEILING,
        risk_rank(candidate.risk) <= risk_rank(envelope.risk_ceiling),
        f"{candidate.risk.value} risk exceeds the envelope ceiling of "
        f"{envelope.risk_ceiling.value}",
    )
    if candidate.estimated_cost is None:
        record(
            EligibilityCheck.COST_WITHIN_BUDGET,
            True,
            "",
        )
    elif candidate.estimated_cost.currency != envelope.budget.currency:
        record(
            EligibilityCheck.COST_WITHIN_BUDGET,
            False,
            f"costed in {candidate.estimated_cost.currency} against an envelope "
            f"budget in {envelope.budget.currency}",
        )
    else:
        record(
            EligibilityCheck.COST_WITHIN_BUDGET,
            candidate.estimated_cost <= envelope.budget,
            f"estimated {candidate.estimated_cost} against an envelope budget of "
            f"{envelope.budget}",
        )
    needed = set(candidate.required_action_set())
    blocked_actions = sorted(
        item.value for item in needed & (forbidden | reserved)
    )
    record(
        EligibilityCheck.NO_FORBIDDEN_ACTION,
        not blocked_actions,
        "the work needs action(s) the envelope forbids or the CEO reserves: "
        + ", ".join(blocked_actions),
    )
    if candidate.dependencies:
        unmet: list[str] = []
        for dependency in candidate.dependencies:
            other = register.candidate(dependency) if register else None
            if other is None or other.status is not CandidateStatus.COMPLETED:
                unmet.append(dependency)
        record(
            EligibilityCheck.DEPENDENCIES_SATISFIED,
            not unmet,
            "depends on work that is not complete: " + ", ".join(unmet),
        )
    else:
        record(EligibilityCheck.DEPENDENCIES_SATISFIED, True, "")
    usable = candidate.falsifiable_criteria()
    record(
        EligibilityCheck.CRITERIA_FALSIFIABLE,
        bool(usable),
        "no acceptance criterion names a subject a reviewer could check, so the "
        "finished work could not be judged",
    )
    record(
        EligibilityCheck.EVIDENCE_PRESENT,
        bool(candidate.evidence_refs),
        "no evidence refs",
    )
    # Only *declared* categories are compared. An earlier draft tokenized the
    # objective's prose title and matched words against the candidate's tags,
    # which turned a constraint into a keyword filter and rejected real work for
    # not repeating the CEO's adjectives. If one side declares no categories the
    # check has nothing to compare, and it says so rather than inventing an
    # affinity out of a sentence.
    declared = {str(tag).strip().lower() for tag in (objective_goal_tags or ())}
    if candidate.goal_tags and declared:
        overlap = {tag for tag in candidate.goal_tags if tag in declared}
        record(
            EligibilityCheck.GOAL_OVERLAP,
            bool(overlap),
            f"declared goal tags ({', '.join(candidate.goal_tags)}) share nothing "
            f"with the objective's declared categories ({', '.join(sorted(declared))})",
        )
    else:
        record(EligibilityCheck.GOAL_OVERLAP, True, "")

    return CandidateEligibility(
        candidate_id=candidate.candidate_id,
        eligible=not failed,
        passed=tuple(passed),
        failed=tuple(failed),
        reasons=tuple(reasons),
    )


def eligible_candidates(
    register: CandidateRegister,
    objective: Objective,
    envelope: PlanningEnvelope,
    *,
    capsule_ids: Sequence[str],
    reserved_actions: Sequence[ActionType] = (),
    objective_goal_tags: Sequence[str] = (),
) -> tuple[CandidateEligibility, ...]:
    """Every candidate measured, in register order. Nothing is filtered away.

    The rejected ones are part of the answer: a planning decision that cannot
    say what it turned down has not shown its work.
    """
    if not isinstance(register, CandidateRegister):
        raise DelegationError("eligible_candidates takes a CandidateRegister")
    return tuple(
        assess_candidate(
            candidate,
            objective,
            envelope,
            capsule_ids=capsule_ids,
            register=register,
            reserved_actions=reserved_actions,
            objective_goal_tags=objective_goal_tags,
        )
        for candidate in register.candidates
    )


def only_eligible(
    results: Sequence[CandidateEligibility],
) -> tuple[str, ...]:
    """The candidate ids that passed every check."""
    return tuple(item.candidate_id for item in results if item.eligible)


@dataclass(frozen=True)
class WorkOrderProposal:
    """A bounded work order, derived from one candidate and one envelope.

    Not a work order yet - `company.engineering.intake` still has to authorize
    it, and still may refuse. What this guarantees is that intake will not be
    handed an objective nobody planned.
    """

    proposal_id: str
    objective_id: str
    candidate_id: str
    capsule_id: str
    department: str
    objective: str
    acceptance_criteria: tuple[str, ...]
    scope_ceiling: tuple[str, ...]
    risk: Risk
    resource_profile: str
    budget: Money
    evidence_refs: tuple[str, ...]
    proposed_by_seat: str
    proposed_on: dt.date
    planning_decision_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "proposal_id", assert_record_id(self.proposal_id, "proposal_id")
        )
        object.__setattr__(
            self, "objective", assert_prose(self.objective, "proposal.objective")
        )
        if not self.acceptance_criteria:
            raise DelegationError("a work order proposal needs acceptance criteria")

    def to_request_dict(self, *, requested_by: str) -> dict[str, Any]:
        """The payload `company.engineering.intake` reads, ready to submit."""
        return {
            "request_id": self.proposal_id,
            "objective": self.objective,
            "requested_by": requested_by,
            "requested_on": self.proposed_on.isoformat(),
            "capsule_hints": [self.capsule_id],
            "scope_ceiling": list(self.scope_ceiling),
            "acceptance_criteria": list(self.acceptance_criteria),
            "risk": self.risk.value,
            "reversible": True,
            "resource_profile": self.resource_profile,
            "candidate_id": self.candidate_id,
            "planning_decision_id": self.planning_decision_id,
            "notes": (
                f"derived from candidate {self.candidate_id} by planning decision "
                f"{self.planning_decision_id}"
            ),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "objective_id": self.objective_id,
            "candidate_id": self.candidate_id,
            "capsule_id": self.capsule_id,
            "department": self.department,
            "objective": self.objective,
            "acceptance_criteria": list(self.acceptance_criteria),
            "scope_ceiling": list(self.scope_ceiling),
            "risk": self.risk.value,
            "resource_profile": self.resource_profile,
            "budget": self.budget.to_dict(),
            "evidence_refs": list(self.evidence_refs),
            "proposed_by_seat": self.proposed_by_seat,
            "proposed_on": self.proposed_on.isoformat(),
            "planning_decision_id": self.planning_decision_id,
        }


def propose_work_order(
    candidate: WorkCandidate,
    envelope: PlanningEnvelope,
    *,
    proposal_id: str,
    proposed_by_seat: str,
    proposed_on: dt.date,
    planning_decision_id: str,
    narrow_scope: Sequence[str] = (),
    narrow_criteria: Sequence[str] = (),
    narrow_risk: Any = None,
    budget: Money | None = None,
) -> WorkOrderProposal:
    """Turn a selected candidate into a bounded work order proposal.

    Management may narrow. Every widening raises `AuthorityViolation`, because
    the candidate and the envelope are what the finished work will be reviewed
    against, and a work order larger than both is reviewable against nothing.
    """
    if not isinstance(candidate, WorkCandidate):
        raise DelegationError("propose_work_order takes a WorkCandidate")
    if not isinstance(envelope, PlanningEnvelope):
        raise DelegationError("propose_work_order takes a PlanningEnvelope")

    scope = tuple(narrow_scope) or candidate.allowed_write_scope
    if narrow_scope:
        outside = sorted(set(scope) - set(candidate.allowed_write_scope))
        if outside:
            raise AuthorityViolation(
                f"{proposal_id}: the proposal writes to {', '.join(outside)}, which "
                f"candidate {candidate.candidate_id} does not allow. Management may "
                "narrow a candidate's scope and may not widen it."
            )
    criteria = tuple(narrow_criteria) or candidate.falsifiable_criteria()
    if narrow_criteria:
        extra = sorted(set(criteria) - set(candidate.acceptance_criteria))
        if extra:
            raise AuthorityViolation(
                f"{proposal_id}: the proposal adds acceptance criteria the candidate "
                f"does not carry ({'; '.join(extra)}). Narrowing means dropping "
                "criteria, not writing new ones after the evidence was reviewed."
            )
    unusable = [item for item in criteria if not is_falsifiable_criterion(item)]
    if unusable or not criteria:
        raise DelegationError(
            f"{proposal_id}: a work order proposal needs at least one falsifiable "
            "acceptance criterion and every criterion must be one; "
            f"{len(unusable)} were not"
        )
    risk = candidate.risk
    if narrow_risk is not None:
        from .policy import parse_risk

        wanted = parse_risk(narrow_risk, "narrow_risk")
        if risk_rank(wanted) > risk_rank(candidate.risk):
            raise AuthorityViolation(
                f"{proposal_id}: the proposal claims {wanted.value} risk against a "
                f"candidate assessed at {candidate.risk.value}. A work order may be "
                "more cautious than its candidate and never less."
            )
        risk = wanted
    if risk_rank(risk) > risk_rank(envelope.risk_ceiling):
        raise AuthorityViolation(
            f"{proposal_id}: {risk.value} risk exceeds the envelope ceiling "
            f"{envelope.risk_ceiling.value}"
        )
    money = budget or envelope.budget
    if money.currency != envelope.budget.currency or money > envelope.budget:
        raise AuthorityViolation(
            f"{proposal_id}: a budget of {money} is not inside the envelope's "
            f"{envelope.budget}"
        )
    return WorkOrderProposal(
        proposal_id=proposal_id,
        objective_id=envelope.objective_id,
        candidate_id=candidate.candidate_id,
        capsule_id=candidate.capsule_id,
        department=candidate.department,
        objective=candidate.title
        if is_falsifiable_criterion(candidate.title)
        else candidate.problem_statement,
        acceptance_criteria=criteria,
        scope_ceiling=scope,
        risk=risk,
        resource_profile=candidate.estimated_resource_profile,
        budget=money,
        evidence_refs=candidate.evidence_refs,
        proposed_by_seat=proposed_by_seat,
        proposed_on=proposed_on,
        planning_decision_id=planning_decision_id,
    )


@dataclass(frozen=True)
class PlanningResult:
    """Everything one planning pass produced, decision first."""

    record: PlanningDecisionRecord
    eligibility: tuple[CandidateEligibility, ...]
    proposal: WorkOrderProposal | None = None

    @property
    def outcome(self) -> PlanningOutcome:
        return self.record.decision

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.record.to_dict(),
            "eligibility": [item.to_dict() for item in self.eligibility],
            "proposal": self.proposal.to_dict() if self.proposal else None,
        }


def select_work(
    register: CandidateRegister,
    objective: Objective,
    envelope: PlanningEnvelope,
    *,
    planning_decision_id: str,
    executive_seat: str,
    executive_employee: str,
    manager_seat: str,
    manager_employee: str,
    policy_version: str,
    policy_fingerprint: str,
    recorded_on: dt.date,
    capsule_ids: Sequence[str],
    reserved_actions: Sequence[ActionType] = (),
    objective_goal_tags: Sequence[str] = (),
    prefer_candidate_id: str = "",
) -> PlanningResult:
    """One planning pass: measure everything, choose one, and record why.

    The choice itself is deliberately unclever. With one eligible candidate it
    is that one. With several, the caller must name which - and if it does not,
    this escalates rather than picking, because preferring one piece of work
    over another on no stated grounds is a judgement the company has not
    delegated to anything yet.
    """
    if not isinstance(objective, Objective):
        raise DelegationError("select_work takes an Objective")
    if objective.level is not ObjectiveLevel.CEO_OBJECTIVE:
        raise DelegationError(
            f"select_work plans a ceo_objective; {objective.objective_id} is a "
            f"{objective.level.value}. Lower rungs are decomposed, not planned."
        )
    if envelope.objective_id != objective.objective_id:
        raise DelegationError(
            f"the envelope is for {envelope.objective_id} and the objective is "
            f"{objective.objective_id}"
        )

    results = eligible_candidates(
        register,
        objective,
        envelope,
        capsule_ids=capsule_ids,
        reserved_actions=reserved_actions,
        objective_goal_tags=objective_goal_tags,
    )
    considered = tuple(item.candidate_id for item in results)
    winners = only_eligible(results)
    # Everything that was looked at and not chosen, whether it failed a check or
    # simply lost. A record that only listed the ineligible ones would hide the
    # most interesting rejections: the candidates that were eligible and passed
    # over.
    ineligible = tuple(item for item in considered if item not in set(winners))
    common = {
        "planning_decision_id": planning_decision_id,
        "recorded_on": recorded_on,
        "objective_id": objective.objective_id,
        "objective_intent_digest": objective.intent(),
        "department": (envelope.allowed_departments or ("engineering",))[0],
        "executive_seat": executive_seat,
        "executive_employee": executive_employee,
        "manager_seat": manager_seat,
        "manager_employee": manager_employee,
        "policy_version": policy_version,
        "policy_fingerprint": policy_fingerprint,
        "candidate_ids_considered": considered,
    }

    if not winners:
        summary = "; ".join(
            f"{item.candidate_id} failed {', '.join(c.value for c in item.failed)}"
            for item in results
        )
        return PlanningResult(
            record=PlanningDecisionRecord(
                decision=PlanningOutcome.NO_ELIGIBLE_WORK_CANDIDATE,
                selection_reason=(
                    "no candidate in the register passes every constraint of this "
                    "objective's envelope. "
                    + (summary or "the register holds no candidates at all")
                    + ". Creating work anyway would mean inventing a task the "
                    "evidence does not support, which is the failure this "
                    "capability exists to prevent."
                ),
                candidate_ids_rejected=ineligible,
                **common,
            ),
            eligibility=results,
        )

    if len(winners) > 1 and not prefer_candidate_id:
        return PlanningResult(
            record=PlanningDecisionRecord(
                decision=PlanningOutcome.ESCALATED,
                selection_reason=(
                    f"{len(winners)} candidates are equally eligible "
                    f"({', '.join(winners)}) and no preference was supplied"
                ),
                escalation_required=True,
                escalation_reason=(
                    "choosing between eligible candidates is a judgement, and this "
                    "company has delegated eligibility but not preference. A named "
                    "planner must supply the choice, or the envelope must narrow "
                    "until one candidate remains."
                ),
                candidate_ids_rejected=ineligible,
                **common,
            ),
            eligibility=results,
        )

    chosen_id = prefer_candidate_id or winners[0]
    if chosen_id not in winners:
        return PlanningResult(
            record=PlanningDecisionRecord(
                decision=PlanningOutcome.ESCALATED,
                selection_reason=(
                    f"the preferred candidate {chosen_id} is not eligible"
                ),
                escalation_required=True,
                escalation_reason=(
                    f"{chosen_id} failed the deterministic eligibility pass, and a "
                    "preference does not override a constraint. Either the "
                    "constraint is wrong, which is a CEO decision, or the candidate "
                    "is not ready."
                ),
                candidate_ids_rejected=ineligible,
                **common,
            ),
            eligibility=results,
        )

    candidate = register.candidate(chosen_id)
    assert candidate is not None  # winners came from the register
    rejected = tuple(item for item in considered if item != chosen_id)
    alignment = (
        f"advances {objective.objective_id} ({objective.title}) by closing a "
        f"{candidate.source_type.value} recorded in {candidate.source_ref}"
    )
    record = PlanningDecisionRecord(
        decision=PlanningOutcome.SELECTED,
        selected_candidate_id=chosen_id,
        capsule_id=candidate.capsule_id,
        risk=candidate.risk,
        estimated_cost=candidate.estimated_cost,
        expected_value=candidate.expected_value,
        acceptance_criteria=candidate.falsifiable_criteria(),
        objective_alignment=alignment,
        evidence_refs_used=candidate.evidence_refs,
        selection_reason=(
            f"{chosen_id} is "
            + (
                "the only candidate that passes every constraint"
                if len(winners) == 1
                else f"the planner's choice among {len(winners)} eligible candidates"
            )
            + f"; {len(rejected)} other candidate(s) were not chosen"
        ),
        candidate_ids_rejected=rejected,
        **common,
    )
    return PlanningResult(record=record, eligibility=results)


__all__ = [
    "ELIGIBILITY_CHECKS",
    "EXECUTIVE_CHOICE_CONTRACT",
    "CandidateEligibility",
    "EligibilityCheck",
    "PlanningResult",
    "WorkOrderProposal",
    "assess_candidate",
    "eligible_candidates",
    "only_eligible",
    "propose_work_order",
    "select_work",
]

"""One planning run, end to end, and the record that says what it cost.

`planning.select_work` answers a narrow question well: given a register and an
envelope, which candidates are eligible, and is there exactly one? It escalates
whenever there are several, because choosing between them is a judgement it has
no way to make. That escalation was correct and it was also a dead end: a
company whose planner stops whenever it has options has not delegated planning.

This module closes the loop. It owns the ordering, the audit record, and the
page the CEO reads.

```
eligible_candidates()          deterministic, always first
  0 eligible  -> discovery, if an envelope authorizes it, else NO_ELIGIBLE
  1 eligible  -> select it. No model. The answer is arithmetic.
  2+ eligible -> ONE bounded executive session, then the deterministic refusals
```

## Why the ordering is the design and not an optimisation

Every rung costs more than the one above it, and the expensive rung is entered
on purpose or not at all. `executive.should_ask_executive` is a function rather
than an `if` buried in a branch so that "did this run need a model" is a
question with a testable answer. The company runs on one consumer subscription;
a planner session spent confirming the only possible answer is the clearest
waste available to it, and it is also the easiest to write by accident.

## Why the record holds the options that were not taken

`PlanningRunRecord` keeps the eligible set, the rejected set with the named
check each one failed, the decision, the reasoning, whether discovery ran, what
it proposed, what was refused and why, and what the session cost. The CEO asked
four questions of this system - what did management choose, why, what else was
available, and what did planning cost - and a record that cannot answer the
third and fourth is a receipt rather than an account.

## Why a refused planner answer becomes an escalation and not a retry

If the session returns something out of contract - an ineligible id, a widened
risk, malformed output - the run ends `ESCALATED` with the refusal recorded.
It does not ask again, and it does not repair the answer into an authorized
one. Both of those turn a control into a formality: the first by paying twice
for the same judgement, the second by keeping a conclusion whose argument was
discarded.
"""

from __future__ import annotations

from collections.abc import Sequence
import datetime as dt
from dataclasses import dataclass
from typing import Any

from ai_platform.resource_classes import Risk
from ai_platform.serde import fingerprint as _fingerprint
from company.finance.money import Money

from .actions import ActionType
from .candidates import CandidateRegister, WorkCandidate
from .common import (
    assert_day,
    assert_named_person,
    assert_prose,
    assert_record_id,
    assert_seat_id,
    name_tuple,
    ref_tuple,
    text_tuple,
)
from .discovery import DiscoveryEnvelope, DiscoveryResult
from .errors import AuthorityViolation, DelegationError
from .executive import (
    ExecutiveChoice,
    ExecutiveDecision,
    ExecutivePlanner,
    PlannerOutputError,
    PlanningBrief,
    PlanningSessionCost,
    assert_choice_within,
    parse_choice,
    planning_brief,
    should_ask_executive,
)
from .objectives import Objective, ObjectiveLevel, PlanningEnvelope
from .planning import CandidateEligibility, eligible_candidates, only_eligible
from .planning_record import PlanningDecisionRecord, PlanningOutcome

PLANNING_RUN_VERSION = 1


@dataclass(frozen=True)
class PlanningRunRecord:
    """The immutable account of one planning run. Never edited, only appended."""

    planning_run_id: str
    objective_id: str
    objective_intent_digest: str
    recorded_on: dt.date
    department: str
    executive_seat: str
    executive_employee: str
    manager_seat: str
    manager_employee: str
    outcome: PlanningOutcome
    decision_reason: str
    authority_source: str
    policy_version: str
    policy_fingerprint: str
    eligible_candidate_ids: tuple[str, ...] = ()
    rejected_candidates: tuple[str, ...] = ()
    selected_candidate_id: str = ""
    selection_reason: str = ""
    model_used: bool = False
    session: PlanningSessionCost | None = None
    choice: ExecutiveChoice | None = None
    refusal: str = ""
    discovery_requested: bool = False
    discovery_envelope_id: str = ""
    discovery_surfaces: tuple[str, ...] = ()
    discovered_candidate_ids: tuple[str, ...] = ()
    discovery_rejected: tuple[str, ...] = ()
    risk: Risk | None = None
    budget: Money | None = None
    planning_cost: Money | None = None
    version: int = PLANNING_RUN_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "planning_run_id",
            assert_record_id(self.planning_run_id, "planning_run_id"),
        )
        object.__setattr__(
            self, "objective_id", assert_record_id(self.objective_id, "objective_id")
        )
        object.__setattr__(
            self,
            "objective_intent_digest",
            assert_prose(self.objective_intent_digest, "objective_intent_digest"),
        )
        object.__setattr__(
            self, "recorded_on", assert_day(self.recorded_on, "recorded_on")
        )
        object.__setattr__(
            self, "department", assert_prose(self.department, "department").lower()
        )
        for field in ("executive_seat", "manager_seat"):
            object.__setattr__(self, field, assert_seat_id(getattr(self, field), field))
        for field in ("executive_employee", "manager_employee"):
            object.__setattr__(
                self, field, assert_named_person(getattr(self, field), field)
            )
        if not isinstance(self.outcome, PlanningOutcome):
            raise DelegationError("outcome must be a PlanningOutcome")
        for field in ("decision_reason", "authority_source", "policy_version",
                      "policy_fingerprint"):
            object.__setattr__(
                self, field, assert_prose(getattr(self, field), field)
            )
        object.__setattr__(
            self,
            "eligible_candidate_ids",
            name_tuple(self.eligible_candidate_ids, "eligible_candidate_ids", limit=64),
        )
        object.__setattr__(
            self,
            "rejected_candidates",
            text_tuple(self.rejected_candidates, "rejected_candidates", limit=64),
        )
        object.__setattr__(
            self,
            "discovered_candidate_ids",
            name_tuple(
                self.discovered_candidate_ids, "discovered_candidate_ids", limit=16
            ),
        )
        object.__setattr__(
            self,
            "discovery_rejected",
            text_tuple(self.discovery_rejected, "discovery_rejected", limit=32),
        )
        object.__setattr__(
            self,
            "discovery_surfaces",
            name_tuple(self.discovery_surfaces, "discovery_surfaces", limit=16),
        )
        for field in ("selected_candidate_id", "selection_reason", "refusal",
                      "discovery_envelope_id"):
            value = getattr(self, field)
            if not isinstance(value, str):
                raise DelegationError(f"{field} must be text")
            object.__setattr__(self, field, value.strip())
        for field in ("model_used", "discovery_requested"):
            if not isinstance(getattr(self, field), bool):
                raise DelegationError(f"{field} must be a bool")

        # --- the four refusals ---------------------------------------------
        if self.outcome is PlanningOutcome.SELECTED:
            if not self.selected_candidate_id:
                raise DelegationError(
                    f"{self.planning_run_id}: a SELECTED run names no candidate"
                )
            if self.selected_candidate_id not in self.eligible_candidate_ids:
                raise DelegationError(
                    f"{self.planning_run_id}: {self.selected_candidate_id} was not "
                    "among the eligible candidates. A selection outside the set the "
                    "deterministic pass produced is not a selection this company "
                    "authorized."
                )
        if self.model_used and self.session is None:
            raise DelegationError(
                f"{self.planning_run_id}: a run that used a model records no "
                "session. Planning whose cost is unrecorded is planning the "
                "company cannot budget for."
            )
        if self.session is not None and not self.model_used:
            raise DelegationError(
                f"{self.planning_run_id}: a session is recorded but model_used is "
                "false"
            )
        if self.executive_employee == self.manager_employee and (
            self.executive_seat != self.manager_seat
        ):
            raise DelegationError(
                f"{self.planning_run_id}: {self.executive_employee} is recorded in "
                "both the executive and the manager seat"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "planning_run_id": self.planning_run_id,
            "objective_id": self.objective_id,
            "objective_intent_digest": self.objective_intent_digest,
            "recorded_on": self.recorded_on.isoformat(),
            "department": self.department,
            "executive_seat": self.executive_seat,
            "executive_employee": self.executive_employee,
            "manager_seat": self.manager_seat,
            "manager_employee": self.manager_employee,
            "outcome": self.outcome.value,
            "decision_reason": self.decision_reason,
            "authority_source": self.authority_source,
            "policy_version": self.policy_version,
            "policy_fingerprint": self.policy_fingerprint,
            "eligible_candidate_ids": list(self.eligible_candidate_ids),
            "rejected_candidates": list(self.rejected_candidates),
            "selected_candidate_id": self.selected_candidate_id,
            "selection_reason": self.selection_reason,
            "model_used": self.model_used,
            "session": self.session.to_dict() if self.session else None,
            "choice": self.choice.to_dict() if self.choice else None,
            "refusal": self.refusal,
            "discovery_requested": self.discovery_requested,
            "discovery_envelope_id": self.discovery_envelope_id,
            "discovery_surfaces": list(self.discovery_surfaces),
            "discovered_candidate_ids": list(self.discovered_candidate_ids),
            "discovery_rejected": list(self.discovery_rejected),
            "risk": self.risk.value if self.risk else "",
            "budget": self.budget.to_dict() if self.budget else None,
            "planning_cost": self.planning_cost.to_dict() if self.planning_cost else None,
            "version": self.version,
        }

    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())


@dataclass(frozen=True)
class PlanningRun:
    """The record, plus the working detail a caller may want."""

    record: PlanningRunRecord
    eligibility: tuple[CandidateEligibility, ...] = ()
    brief: PlanningBrief | None = None
    discovery: DiscoveryResult | None = None
    decision: PlanningDecisionRecord | None = None

    @property
    def outcome(self) -> PlanningOutcome:
        return self.record.outcome

    def to_dict(self) -> dict[str, Any]:
        return {
            "run": self.record.to_dict(),
            "eligibility": [item.to_dict() for item in self.eligibility],
            "brief": self.brief.to_dict() if self.brief else None,
            "discovery": self.discovery.to_dict() if self.discovery else None,
            "decision": self.decision.to_dict() if self.decision else None,
        }


def _rejection_lines(results: Sequence[CandidateEligibility]) -> tuple[str, ...]:
    return tuple(
        f"{item.candidate_id}: " + ", ".join(check.value for check in item.failed)
        for item in results
        if not item.eligible
    )


def plan_objective(
    register: CandidateRegister,
    objective: Objective,
    envelope: PlanningEnvelope,
    *,
    planning_run_id: str,
    executive_seat: str,
    executive_employee: str,
    manager_seat: str,
    manager_employee: str,
    policy_version: str,
    policy_fingerprint: str,
    authority_source: str,
    recorded_on: dt.date,
    capsule_ids: Sequence[str],
    reserved_actions: Sequence[ActionType] = (),
    objective_goal_tags: Sequence[str] = (),
    planner: ExecutivePlanner | None = None,
    session: PlanningSessionCost | None = None,
    discovery: DiscoveryResult | None = None,
    discovery_envelope: DiscoveryEnvelope | None = None,
) -> PlanningRun:
    """One planning run, deterministic first and a model only when it must be.

    `discovery` is a result the caller already obtained under
    `discovery_envelope`; this function does not read evidence itself, for the
    same reason `run_discovery` does not - reading is the bounded part, and it
    belongs to whoever holds the envelope.
    """
    if not isinstance(objective, Objective):
        raise DelegationError("plan_objective takes an Objective")
    if objective.level is not ObjectiveLevel.CEO_OBJECTIVE:
        raise DelegationError(
            f"plan_objective plans a ceo_objective; {objective.objective_id} is a "
            f"{objective.level.value}"
        )
    if envelope.objective_id != objective.objective_id:
        raise DelegationError(
            f"the envelope is for {envelope.objective_id} and the objective is "
            f"{objective.objective_id}"
        )

    working = register
    discovered_ids: tuple[str, ...] = ()
    discovery_rejected: tuple[str, ...] = ()
    surfaces: tuple[str, ...] = ()
    if discovery is not None:
        if discovery_envelope is None:
            raise DelegationError(
                "a discovery result was supplied with no envelope; the envelope is "
                "the authority the result was produced under"
            )
        if discovery_envelope.objective_id != objective.objective_id:
            raise AuthorityViolation(
                f"the discovery envelope is for {discovery_envelope.objective_id} "
                f"and the objective is {objective.objective_id}"
            )
        working = CandidateRegister(register.candidates + discovery.accepted)
        discovered_ids = discovery.accepted_ids()
        discovery_rejected = tuple(
            f"{item.candidate_id}: " + ", ".join(c.value for c in item.failed)
            for item in discovery.verdicts
            if not item.accepted
        )
        surfaces = tuple(item.value for item in discovery.surfaces_read)

    results = eligible_candidates(
        working,
        objective,
        envelope,
        capsule_ids=capsule_ids,
        reserved_actions=reserved_actions,
        objective_goal_tags=objective_goal_tags,
    )
    winners = only_eligible(results)
    common: dict[str, Any] = {
        "planning_run_id": planning_run_id,
        "objective_id": objective.objective_id,
        "objective_intent_digest": objective.intent(),
        "recorded_on": recorded_on,
        "department": (envelope.allowed_departments or ("engineering",))[0],
        "executive_seat": executive_seat,
        "executive_employee": executive_employee,
        "manager_seat": manager_seat,
        "manager_employee": manager_employee,
        "authority_source": authority_source,
        "policy_version": policy_version,
        "policy_fingerprint": policy_fingerprint,
        "eligible_candidate_ids": winners,
        "rejected_candidates": _rejection_lines(results),
        "budget": envelope.budget,
        "discovery_requested": discovery is not None,
        "discovery_envelope_id": (
            discovery_envelope.envelope_id if discovery_envelope else ""
        ),
        "discovery_surfaces": surfaces,
        "discovered_candidate_ids": discovered_ids,
        "discovery_rejected": discovery_rejected,
    }

    # --- rung 1: nothing eligible -----------------------------------------
    if not winners:
        detail = "; ".join(_rejection_lines(results)) or "the register is empty"
        note = (
            "discovery ran and produced nothing that passed validation"
            if discovery is not None and not discovery.found_anything
            else "no discovery envelope authorized a search for new work"
            if discovery is None
            else "discovery produced candidates, and none of them is eligible"
        )
        return PlanningRun(
            record=PlanningRunRecord(
                outcome=PlanningOutcome.NO_ELIGIBLE_WORK_CANDIDATE,
                decision_reason=(
                    f"no candidate passes every constraint of this envelope ({detail}). "
                    f"{note}. Creating work anyway would mean inventing a task the "
                    "evidence does not support."
                ),
                model_used=False,
                **common,
            ),
            eligibility=results,
            discovery=discovery,
        )

    # --- rung 2: exactly one eligible, decided without a model -------------
    if not should_ask_executive(len(winners)):
        chosen = working.candidate(winners[0])
        assert chosen is not None
        return PlanningRun(
            record=PlanningRunRecord(
                outcome=PlanningOutcome.SELECTED,
                selected_candidate_id=chosen.candidate_id,
                selection_reason=(
                    f"{chosen.candidate_id} is the only candidate that passes every "
                    "constraint, so the choice is arithmetic and no planning session "
                    "was opened"
                ),
                decision_reason=(
                    "one eligible candidate: selected deterministically, at no "
                    "model cost"
                ),
                risk=chosen.risk,
                model_used=False,
                **common,
            ),
            eligibility=results,
        )

    # --- rung 3: two or more, one bounded executive session ----------------
    eligible_records = tuple(working.candidate(item) for item in winners)
    brief = planning_brief(
        objective,
        envelope,
        [item for item in eligible_records if item is not None],
        discovery_available=False,
    )
    if planner is None:
        return PlanningRun(
            record=PlanningRunRecord(
                outcome=PlanningOutcome.ESCALATED,
                decision_reason=(
                    f"{len(winners)} candidates are equally eligible "
                    f"({', '.join(winners)}) and no executive planner was supplied. "
                    "Choosing between eligible options is a judgement; this run had "
                    "nothing authorized to make it."
                ),
                model_used=False,
                **common,
            ),
            eligibility=results,
            brief=brief,
        )
    if not brief.within_budget():
        return PlanningRun(
            record=PlanningRunRecord(
                outcome=PlanningOutcome.ESCALATED,
                decision_reason=(
                    "the planning brief exceeds the bounded-context ceiling, so the "
                    "session would not be the bounded thing it is authorized to be"
                ),
                model_used=False,
                **common,
            ),
            eligibility=results,
            brief=brief,
        )

    from .executive import PLANNER_INSTRUCTIONS

    try:
        raw = planner(brief, PLANNER_INSTRUCTIONS)
        choice = parse_choice(raw)
        assert_choice_within(
            choice,
            brief,
            objective=objective,
            envelope=envelope,
            reserved_actions=reserved_actions,
        )
    except (PlannerOutputError, AuthorityViolation) as exc:
        return PlanningRun(
            record=PlanningRunRecord(
                outcome=PlanningOutcome.ESCALATED,
                decision_reason=(
                    "the executive planning session returned an answer this company "
                    "cannot accept, and a refused answer is not retried or repaired"
                ),
                refusal=str(exc),
                model_used=True,
                session=session,
                planning_cost=session.cost if session else None,
                **common,
            ),
            eligibility=results,
            brief=brief,
        )

    if choice.decision is not ExecutiveDecision.SELECT:
        return PlanningRun(
            record=PlanningRunRecord(
                outcome=(
                    PlanningOutcome.ESCALATED
                    if choice.decision is ExecutiveDecision.ESCALATE
                    else PlanningOutcome.NO_ELIGIBLE_WORK_CANDIDATE
                ),
                decision_reason=(
                    f"the executive planner answered {choice.decision.value}: "
                    f"{choice.reason}"
                ),
                choice=choice,
                model_used=True,
                session=session,
                planning_cost=session.cost if session else None,
                **common,
            ),
            eligibility=results,
            brief=brief,
        )

    chosen = working.candidate(choice.selected_candidate_id)
    assert chosen is not None  # assert_choice_within proved it is in the brief
    return PlanningRun(
        record=PlanningRunRecord(
            outcome=PlanningOutcome.SELECTED,
            selected_candidate_id=chosen.candidate_id,
            selection_reason=choice.reason,
            decision_reason=(
                f"{len(winners)} candidates were eligible; one bounded executive "
                f"session chose {chosen.candidate_id} with {choice.confidence.value} "
                "confidence"
            ),
            choice=choice,
            risk=chosen.risk,
            model_used=True,
            session=session,
            planning_cost=session.cost if session else None,
            **common,
        ),
        eligibility=results,
        brief=brief,
    )


def ceo_planning_report(run: PlanningRun, register: CandidateRegister) -> str:
    """The page the CEO reads. Not the register, and not the run's internals."""
    record = run.record
    chosen = (
        register.candidate(record.selected_candidate_id)
        if record.selected_candidate_id
        else None
    )
    ready = record.outcome is PlanningOutcome.SELECTED
    needs_ceo = record.outcome is PlanningOutcome.ESCALATED
    lines = [
        f"OBJECTIVE            {record.objective_id}",
        f"PLANNING STATUS      {record.outcome.value}",
        f"ELIGIBLE WORK FOUND  {len(record.eligible_candidate_ids)}",
        f"CANDIDATES CONSIDERED"
        f"{' ':<1}{len(record.eligible_candidate_ids) + len(record.rejected_candidates)}"
        f" ({len(record.rejected_candidates)} rejected)",
        f"SELECTED WORK        {chosen.title if chosen else '-'}",
        f"WHY SELECTED         {record.selection_reason or record.decision_reason}",
        f"DISCOVERY USED       {'yes' if record.discovery_requested else 'no'}"
        + (
            f" ({len(record.discovered_candidate_ids)} proposed, "
            f"{len(record.discovery_rejected)} rejected)"
            if record.discovery_requested
            else ""
        ),
        f"EXECUTIVE            {record.executive_seat} ({record.executive_employee})",
        f"MANAGER              {record.manager_seat} ({record.manager_employee})",
        f"EXPECTED VALUE       {chosen.expected_value if chosen else '-'}",
        f"RISK                 {record.risk.value if record.risk else '-'}",
        f"PLANNING COST        "
        + (
            f"{record.planning_cost}"
            if record.planning_cost
            else ("model used, cost unreported" if record.model_used else "0 (no model)")
        ),
        f"READY FOR EXECUTION  {'yes' if ready else 'no'}",
        f"CEO DECISION NEEDED  {'yes' if needs_ceo else 'no'}",
    ]
    if record.refusal:
        lines.append(f"REFUSED              {record.refusal}")
    return "\n".join(lines)


__all__ = [
    "PLANNING_RUN_VERSION",
    "PlanningRun",
    "PlanningRunRecord",
    "ceo_planning_report",
    "plan_objective",
]

"""The executive planner: choosing between eligible candidates, and nothing else.

Deterministic eligibility answers *may this candidate be chosen*. It cannot
answer *which of these three should we do first*, because that is a judgement
about value, risk and timing, and a comparison that could be computed would
have been a constraint. So this module is where a model is allowed to help -
and it is built on the assumption that the model is fallible and the policy is
not.

```
eligible candidates
  -> planning_brief()      bounded: titles, value, risk, criteria, evidence refs
  -> one executive session (or none - see below)
  -> parse_choice()        structured output, or a refusal
  -> assert_choice_within() seven refusals, checked against the policy
  -> ExecutiveChoice
```

## Why the planner gets a brief and not the repository

`PlanningBrief` is a closed set of fields, assembled from records the company
already holds. The planner never receives source files, never receives the
capsule bodies, and never receives a path it could ask to have read. It gets
what a manager would get in a one-page summary: what the objective is, what
each option is for, what each would cost and risk, and where the evidence sits
if a human wants to check.

That is not only a cost decision, though it is also that. A planner holding the
repository can justify anything, and a selection justified by something the
record does not contain cannot be audited afterwards.

## Why deterministic comes first, always

`should_ask_executive` exists so that the expensive path is entered on purpose.
With zero eligible candidates there is nothing to choose between and the answer
is discovery or nothing. With exactly one, **the choice is arithmetic** and
calling a model to confirm the only possible answer is pure waste - the company
runs on one consumer subscription, and a planner session spent restating a
foregone conclusion is a session not spent on a real comparison.

Only two or more eligible candidates reach a session.

## Why the model proposes and the policy decides

Everything the planner returns is a *claim*. `assert_choice_within` checks each
claim against the records the planner was given:

- a candidate id outside the eligible set
- an objective id that is not the objective it was asked about
- a risk above the envelope ceiling
- a spend above the envelope budget
- an action the envelope forbids or the CEO reserves
- a decision name outside the closed set
- output that does not parse

Each is a refusal, and **none of them is repaired**. A planner that chose an
ineligible candidate is not quietly re-pointed at an eligible one, because the
reasoning that produced the answer was reasoning about something else. The run
ends as `ESCALATED` and a person reads it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import datetime as dt
from dataclasses import dataclass
from enum import Enum
import json
from typing import Any, Protocol

from ai_platform.resource_classes import ReasoningClass, Risk
from ai_platform.serde import fingerprint as _fingerprint
from company.finance.money import Money

from .actions import ActionType, parse_action
from .candidates import WorkCandidate
from .common import assert_prose, assert_record_id, text_tuple
from .errors import AuthorityViolation, DelegationError
from .objectives import Objective, PlanningEnvelope
from .policy import parse_risk, risk_rank

PLANNING_REASONING_CLASS = ReasoningClass.C
"""Small reasoning. Comparing a handful of summarised options is not research.

Deliberately not D or E. The specialist tiers exist for work whose difficulty
is in the subject matter; this planner's difficulty is in the trade-off, and
the trade-off is presented to it already summarised. A company that reaches for
its most expensive tier to rank three bullet points will reach for it for
everything.
"""

MAX_PLANNING_SESSIONS = 1
"""One bounded session per planning run. Not a default - a ceiling.

No planner swarm, no second opinion, no critic. A second session would double
the bill to arbitrate a disagreement nobody has evidence is happening, and the
deterministic refusals below already catch the failures a critic would look
for.
"""

MAX_BRIEF_CANDIDATES = 8
MAX_BRIEF_CHARS = 8000
"""Ceilings on the brief itself, so "bounded context" is a number and not a hope."""


class ExecutiveDecision(str, Enum):
    """The four things an executive planner may conclude. Closed."""

    SELECT = "select"
    DEFER = "defer"
    DISCOVER = "discover"
    ESCALATE = "escalate"


def parse_decision(value: Any, field: str = "decision") -> ExecutiveDecision:
    if isinstance(value, ExecutiveDecision):
        return value
    if not isinstance(value, str):
        raise DelegationError(f"{field} must be a decision name, got {value!r}")
    try:
        return ExecutiveDecision(value.strip().lower())
    except ValueError as exc:
        allowed = ", ".join(item.value for item in ExecutiveDecision)
        raise DelegationError(f"{field} must be one of: {allowed}") from exc


class Confidence(str, Enum):
    """How sure the planner is. Three values, because five would be invented."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


def parse_confidence(value: Any, field: str = "confidence") -> Confidence:
    if isinstance(value, Confidence):
        return value
    if not isinstance(value, str) or not value.strip():
        return Confidence.LOW
    try:
        return Confidence(value.strip().lower())
    except ValueError as exc:
        raise DelegationError(
            f"{field} must be low, medium or high, got {value!r}"
        ) from exc


@dataclass(frozen=True)
class CandidateBrief:
    """One option, as the planner sees it. Everything here is already recorded."""

    candidate_id: str
    title: str
    expected_value: str
    problem_statement: str
    risk: str
    estimated_resource_profile: str
    estimated_cost: str
    capsule_id: str
    dependencies: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    source: str

    @classmethod
    def of(cls, candidate: WorkCandidate) -> "CandidateBrief":
        return cls(
            candidate_id=candidate.candidate_id,
            title=candidate.title,
            expected_value=candidate.expected_value,
            problem_statement=candidate.problem_statement,
            risk=candidate.risk.value,
            estimated_resource_profile=candidate.estimated_resource_profile,
            estimated_cost=(
                str(candidate.estimated_cost) if candidate.estimated_cost else "unstated"
            ),
            capsule_id=candidate.capsule_id,
            dependencies=candidate.dependencies,
            acceptance_criteria=candidate.falsifiable_criteria(),
            evidence_refs=candidate.evidence_refs,
            source=candidate.source_type.value,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "title": self.title,
            "expected_value": self.expected_value,
            "problem_statement": self.problem_statement,
            "risk": self.risk,
            "estimated_resource_profile": self.estimated_resource_profile,
            "estimated_cost": self.estimated_cost,
            "capsule_id": self.capsule_id,
            "dependencies": list(self.dependencies),
            "acceptance_criteria": list(self.acceptance_criteria),
            "evidence_refs": list(self.evidence_refs),
            "source": self.source,
        }


@dataclass(frozen=True)
class PlanningBrief:
    """Everything one executive planning session is given. Nothing else exists."""

    objective_id: str
    objective_title: str
    success_metrics: tuple[str, ...]
    department: str
    risk_ceiling: str
    budget: str
    forbidden_actions: tuple[str, ...]
    candidates: tuple[CandidateBrief, ...]
    discovery_available: bool = False

    def __post_init__(self) -> None:
        if not self.candidates:
            raise DelegationError(
                "a planning brief with no candidates has nothing to decide; the "
                "caller should take the discovery path instead of opening a session"
            )
        if len(self.candidates) > MAX_BRIEF_CANDIDATES:
            raise DelegationError(
                f"a brief carries at most {MAX_BRIEF_CANDIDATES} candidates, got "
                f"{len(self.candidates)}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective_id": self.objective_id,
            "objective_title": self.objective_title,
            "success_metrics": list(self.success_metrics),
            "department": self.department,
            "risk_ceiling": self.risk_ceiling,
            "budget": self.budget,
            "forbidden_actions": list(self.forbidden_actions),
            "discovery_available": self.discovery_available,
            "candidates": [item.to_dict() for item in self.candidates],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    def within_budget(self) -> bool:
        return len(self.to_json()) <= MAX_BRIEF_CHARS

    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())


def planning_brief(
    objective: Objective,
    envelope: PlanningEnvelope,
    eligible: Sequence[WorkCandidate],
    *,
    discovery_available: bool = False,
) -> PlanningBrief:
    """Assemble the bounded brief. Every field comes from a record, not a file."""
    return PlanningBrief(
        objective_id=objective.objective_id,
        objective_title=objective.title,
        success_metrics=tuple(envelope.success_metrics),
        department=(envelope.allowed_departments or ("engineering",))[0],
        risk_ceiling=envelope.risk_ceiling.value,
        budget=str(envelope.budget),
        forbidden_actions=tuple(item.value for item in envelope.forbidden_actions),
        candidates=tuple(CandidateBrief.of(item) for item in eligible),
        discovery_available=discovery_available,
    )


EXECUTIVE_CHOICE_CONTRACT: tuple[str, ...] = (
    "input: a PlanningBrief and nothing else - no repository, no source files, "
    "no capsule bodies, no path the planner may ask to have read",
    "input: each candidate summarised as candidate_id, title, problem_statement, "
    "expected_value, risk, estimated_resource_profile, estimated_cost, capsule_id, "
    "dependencies, acceptance_criteria and evidence_refs",
    "output: one JSON object, no prose around it",
    "output: decision is exactly one of select, defer, discover, escalate",
    "output: on select, selected_candidate_id is one of the candidate_ids given",
    "output: reason, objective_alignment, expected_value_reasoning, risk_reasoning "
    "and resource_reasoning are each a sentence a person can disagree with",
    "output: confidence is low, medium or high",
    "refusal: a candidate id outside the eligible set ends the run as ESCALATED "
    "and is never re-pointed at an eligible one",
    "refusal: the planner may not alter the objective, the risk ceiling, the "
    "budget, the scope or the acceptance criteria",
    "refusal: the planner may not name an action the envelope forbids or the CEO "
    "reserves",
    "refusal: output that does not parse is a refusal, not a prompt to retry",
    "authority: none. The strongest thing this session produces is a recorded "
    "recommendation that deterministic policy then accepts or rejects",
    "budget: one session per planning run, counted against the objective envelope "
    "like any other model process",
)
"""The whole contract, in the form a reader can check an implementation against."""

PLANNER_INSTRUCTIONS = """\
You are the executive planner for a small software company.

You are given a CEO objective and several candidate pieces of work that have
ALREADY passed every deterministic eligibility check: department, capsule
ownership, risk ceiling, budget, dependencies, evidence and falsifiable
acceptance criteria. You do not need to re-check any of that, and you cannot
see anything beyond this brief.

Your only job is to decide which ONE of these candidates the company should do
first, or that it should do none of them.

Reply with a single JSON object and no other text:

{
  "decision": "select" | "defer" | "discover" | "escalate",
  "selected_candidate_id": "<one of the candidate_id values, or empty>",
  "reason": "<why this one, and what the others lacked>",
  "objective_alignment": "<how it advances the stated objective>",
  "expected_value_reasoning": "<what the company gets>",
  "risk_reasoning": "<what could go wrong and why that is acceptable>",
  "resource_reasoning": "<why the cost is proportionate>",
  "confidence": "low" | "medium" | "high"
}

Rules:
- selected_candidate_id MUST be one of the candidate_id values given, exactly.
- Use "select" when one candidate is clearly the best next step.
- Use "defer" when all of them are real but none should be done now; say why.
- Use "discover" only if discovery_available is true and none of these
  candidates advances the objective.
- Use "escalate" when the choice genuinely needs the CEO.
- Do not propose new work. Do not write code. Do not change the objective, the
  risk ceiling, the budget or any acceptance criteria.
"""


@dataclass(frozen=True)
class ExecutiveChoice:
    """One executive planning judgement, parsed and checked."""

    decision: ExecutiveDecision
    reason: str
    selected_candidate_id: str = ""
    objective_alignment: str = ""
    expected_value_reasoning: str = ""
    risk_reasoning: str = ""
    resource_reasoning: str = ""
    confidence: Confidence = Confidence.LOW

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "decision", parse_decision(self.decision, "decision")
        )
        object.__setattr__(self, "reason", assert_prose(self.reason, "reason"))
        object.__setattr__(
            self, "confidence", parse_confidence(self.confidence, "confidence")
        )
        for field in (
            "selected_candidate_id",
            "objective_alignment",
            "expected_value_reasoning",
            "risk_reasoning",
            "resource_reasoning",
        ):
            value = getattr(self, field)
            if not isinstance(value, str):
                raise DelegationError(f"{field} must be text")
            object.__setattr__(self, field, value.strip())
        if self.decision is ExecutiveDecision.SELECT and not self.selected_candidate_id:
            raise DelegationError(
                "a SELECT choice names no candidate, which is not a selection"
            )
        if self.decision is not ExecutiveDecision.SELECT and self.selected_candidate_id:
            raise DelegationError(
                f"a {self.decision.value.upper()} choice names a candidate. Only a "
                "selection selects."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "selected_candidate_id": self.selected_candidate_id,
            "reason": self.reason,
            "objective_alignment": self.objective_alignment,
            "expected_value_reasoning": self.expected_value_reasoning,
            "risk_reasoning": self.risk_reasoning,
            "resource_reasoning": self.resource_reasoning,
            "confidence": self.confidence.value,
        }

    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())


class PlannerOutputError(DelegationError):
    """The planner said something this company cannot read or cannot allow.

    A distinct type because the handling is distinct: a malformed or
    out-of-contract answer is not retried and not repaired. It escalates.
    """


def parse_choice(raw: Any) -> ExecutiveChoice:
    """Read one planner answer. Anything unreadable is a refusal, not a retry."""
    if isinstance(raw, ExecutiveChoice):
        return raw
    data: Any = raw
    if isinstance(raw, (str, bytes)):
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        text = text.strip()
        # A model that wrapped its JSON in a fence is answering in the right
        # shape with the wrong packaging; unwrapping that is reading, not
        # repairing. Anything else is refused below.
        if text.startswith("```"):
            lines = [line for line in text.splitlines() if not line.startswith("```")]
            text = "\n".join(lines).strip()
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise PlannerOutputError(
                "the planner returned no JSON object. Output that does not parse "
                "is a refusal, not a prompt to ask again."
            )
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise PlannerOutputError(f"the planner returned unreadable JSON: {exc}") from exc
    if not isinstance(data, Mapping):
        raise PlannerOutputError("a planner answer must be a JSON object")
    try:
        return ExecutiveChoice(
            decision=data.get("decision", ""),
            reason=str(data.get("reason", "") or ""),
            selected_candidate_id=str(data.get("selected_candidate_id", "") or ""),
            objective_alignment=str(data.get("objective_alignment", "") or ""),
            expected_value_reasoning=str(data.get("expected_value_reasoning", "") or ""),
            risk_reasoning=str(data.get("risk_reasoning", "") or ""),
            resource_reasoning=str(data.get("resource_reasoning", "") or ""),
            confidence=data.get("confidence", "low"),
        )
    except DelegationError as exc:
        raise PlannerOutputError(f"the planner answer is out of contract: {exc}") from exc


def assert_choice_within(
    choice: ExecutiveChoice,
    brief: PlanningBrief,
    *,
    objective: Objective,
    envelope: PlanningEnvelope,
    claimed_risk: Any = None,
    claimed_spend: Money | None = None,
    claimed_actions: Sequence[Any] = (),
    reserved_actions: Sequence[ActionType] = (),
) -> None:
    """The seven refusals. None of them is repaired into something authorized."""
    if not isinstance(choice, ExecutiveChoice):
        raise PlannerOutputError("assert_choice_within takes an ExecutiveChoice")
    if brief.objective_id != objective.objective_id:
        raise AuthorityViolation(
            f"the brief was written for {brief.objective_id} and the objective is "
            f"{objective.objective_id}"
        )
    known = {item.candidate_id for item in brief.candidates}
    if choice.decision is ExecutiveDecision.SELECT:
        if choice.selected_candidate_id not in known:
            raise AuthorityViolation(
                f"the planner selected {choice.selected_candidate_id!r}, which was "
                f"not among the eligible candidates it was given "
                f"({', '.join(sorted(known))}). The run ends here: an answer about "
                "a candidate the planner could not see is reasoning about "
                "something else, and pointing it at an eligible one would keep the "
                "conclusion while discarding the argument."
            )
    if choice.decision is ExecutiveDecision.DISCOVER and not brief.discovery_available:
        raise AuthorityViolation(
            "the planner asked for discovery, which this run did not offer. "
            "Discovery is authorized by an envelope, not requested into existence."
        )
    if claimed_risk is not None:
        wanted = parse_risk(claimed_risk, "claimed_risk")
        if risk_rank(wanted) > risk_rank(envelope.risk_ceiling):
            raise AuthorityViolation(
                f"the planner's answer carries {wanted.value} risk against an "
                f"envelope ceiling of {envelope.risk_ceiling.value}. A planner may "
                "not widen the ceiling it was given."
            )
    if claimed_spend is not None:
        if not isinstance(claimed_spend, Money):
            raise PlannerOutputError("claimed_spend must be Money or None")
        if (
            claimed_spend.currency != envelope.budget.currency
            or claimed_spend > envelope.budget
        ):
            raise AuthorityViolation(
                f"the planner's answer costs {claimed_spend} against an envelope "
                f"budget of {envelope.budget}"
            )
    wanted_actions = {parse_action(item, "claimed_actions") for item in (claimed_actions or ())}
    blocked = sorted(
        item.value
        for item in wanted_actions & (set(envelope.forbidden_actions) | set(reserved_actions))
    )
    if blocked:
        raise AuthorityViolation(
            "the planner's answer requires action(s) the envelope forbids or the "
            f"CEO reserves: {', '.join(blocked)}. Authority is granted, never "
            "claimed by the thing that wants it."
        )


class ExecutivePlanner(Protocol):
    """Anything that can answer one bounded planning brief.

    Deliberately this small. A planner is a function from a brief to text; how
    that text is produced - a provider session, a fixture, a person pasting an
    answer - is not this module's business, and keeping it out is what lets the
    contract be tested without spending anything.
    """

    def __call__(self, brief: PlanningBrief, instructions: str) -> str: ...


@dataclass(frozen=True)
class PlanningSessionCost:
    """What one executive planning session actually cost.

    Fields are `None` rather than 0 when the provider did not report them, for
    the reason `ai_platform.usage` gives: an unreported number is not zero, and
    recording it as zero is how a company convinces itself planning is free.
    """

    session_id: str
    model: str = ""
    provider: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_creation_tokens: int | None = None
    cache_read_tokens: int | None = None
    cost: Money | None = None
    duration_s: float | None = None
    turns: int | None = None
    tool_calls: int | None = None
    reasoning_class: ReasoningClass = PLANNING_REASONING_CLASS

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "model": self.model,
            "provider": self.provider,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cost": self.cost.to_dict() if self.cost else None,
            "duration_s": self.duration_s,
            "turns": self.turns,
            "tool_calls": self.tool_calls,
            "reasoning_class": self.reasoning_class.value,
        }


def should_ask_executive(eligible_count: int) -> bool:
    """Whether this run needs a model at all.

    Zero has nothing to compare. One is arithmetic. The company runs on a
    single consumer subscription, and a session spent confirming the only
    possible answer is the clearest waste available to it.
    """
    if isinstance(eligible_count, bool) or not isinstance(eligible_count, int):
        raise DelegationError("should_ask_executive takes an integer count")
    return eligible_count >= 2


__all__ = [
    "EXECUTIVE_CHOICE_CONTRACT",
    "MAX_BRIEF_CANDIDATES",
    "MAX_BRIEF_CHARS",
    "MAX_PLANNING_SESSIONS",
    "PLANNER_INSTRUCTIONS",
    "PLANNING_REASONING_CLASS",
    "CandidateBrief",
    "Confidence",
    "ExecutiveChoice",
    "ExecutiveDecision",
    "ExecutivePlanner",
    "PlannerOutputError",
    "PlanningBrief",
    "PlanningSessionCost",
    "assert_choice_within",
    "parse_choice",
    "parse_confidence",
    "parse_decision",
    "planning_brief",
    "should_ask_executive",
]

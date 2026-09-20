"""The objective ladder, and the envelope an executive may plan freely inside.

```
CEO objective -> program -> department goal -> work order -> task
```

Every item below the root names its parent, and a parent is always exactly one
rung up. A tree that skips a rung is refused, because a work order hanging
straight off a CEO objective has no department that owns it and no program it
belongs to, which is how a company loses track of why it is doing something.

## Why a CEO objective carries an intent fingerprint

The thing being protected is not the text of the objective. It is the promise
that decomposition does not quietly change what the CEO asked for. So a CEO
objective computes a digest over the fields that constitute its intent — the
title, the success metrics, the deadline, the budget, the risk ceiling, the
departments it may use and the actions it forbids — and every child records the
digest of the parent it was derived from.

`lineage_violations` recomputes the parent digest and compares. If the CEO
objective has been edited since the program was written, the program is now
derived from something that no longer exists and says so. **Editing a CEO
objective is not an amendment; it is a new objective.** That is the whole
mechanism against uncontrolled goal mutation, and it is one comparison.

## Why the envelope is separate from the objective

An objective is what to achieve. An envelope is what an executive may spend,
risk, use and do while achieving it. They are separate records because the
envelope is the thing a plan is checked against, and checking a plan against a
paragraph of intent is not a deterministic operation.

`envelope_violations` answers one question: does this plan stay inside? A plan
that cannot reach the objective inside the envelope produces violations, and
the correct response to violations is to escalate — never to widen the envelope,
which is why `PlanningEnvelope` has no method that returns a bigger one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import datetime as dt
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ai_platform.resource_classes import Risk
from ai_platform.serde import fingerprint as _fingerprint
from company.finance.money import Money

from .actions import ActionType, parse_action
from .common import (
    assert_day,
    assert_prose,
    assert_record_id,
    assert_seat_id,
    name_tuple,
    ref_tuple,
    text_tuple,
)
from .errors import AuthorityViolation, DelegationError
from .policy import parse_risk, risk_rank


class ObjectiveLevel(str, Enum):
    """The five rungs, broadest first."""

    CEO_OBJECTIVE = "ceo_objective"
    PROGRAM = "program"
    DEPARTMENT_GOAL = "department_goal"
    WORK_ORDER = "work_order"
    TASK = "task"


LEVEL_ORDER: tuple[ObjectiveLevel, ...] = (
    ObjectiveLevel.CEO_OBJECTIVE,
    ObjectiveLevel.PROGRAM,
    ObjectiveLevel.DEPARTMENT_GOAL,
    ObjectiveLevel.WORK_ORDER,
    ObjectiveLevel.TASK,
)


def parse_level(value: Any, field: str = "level") -> ObjectiveLevel:
    if isinstance(value, ObjectiveLevel):
        return value
    if not isinstance(value, str):
        raise DelegationError(f"{field} must be an objective level name, got {value!r}")
    try:
        return ObjectiveLevel(value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in LEVEL_ORDER)
        raise DelegationError(f"{field} must be one of: {allowed}") from exc


@dataclass(frozen=True)
class PlanningEnvelope:
    """What an executive may spend, risk, use and do for one objective.

    Everything here is a ceiling or a closed list. There is deliberately no
    field that says how to achieve the objective: inside the envelope the
    executive plans freely, and that freedom is the point of delegating at all.
    """

    objective_id: str
    budget: Money
    budget_scope: str
    risk_ceiling: Risk
    deadline: dt.date | None = None
    allowed_departments: tuple[str, ...] = ()
    forbidden_actions: tuple[ActionType, ...] = ()
    success_metrics: tuple[str, ...] = ()
    reporting_cadence: str = "on_exception"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "objective_id",
            assert_record_id(self.objective_id, "envelope.objective_id"),
        )
        if not isinstance(self.budget, Money):
            raise DelegationError("envelope.budget must be Money")
        if self.budget.is_negative:
            raise DelegationError("envelope.budget is not negative")
        object.__setattr__(
            self,
            "budget_scope",
            assert_record_id(self.budget_scope, "envelope.budget_scope"),
        )
        object.__setattr__(
            self, "risk_ceiling", parse_risk(self.risk_ceiling, "envelope.risk_ceiling")
        )
        if self.deadline is not None:
            object.__setattr__(
                self, "deadline", assert_day(self.deadline, "envelope.deadline")
            )
        object.__setattr__(
            self,
            "allowed_departments",
            name_tuple(self.allowed_departments, "envelope.allowed_departments"),
        )
        if not self.allowed_departments:
            raise DelegationError(
                "envelope.allowed_departments is empty. An envelope that names no "
                "department permits every department, which is not an envelope."
            )
        forbidden = tuple(
            parse_action(item, "envelope.forbidden_actions")
            for item in (self.forbidden_actions or ())
        )
        object.__setattr__(
            self,
            "forbidden_actions",
            tuple(sorted(set(forbidden), key=lambda item: item.value)),
        )
        object.__setattr__(
            self,
            "success_metrics",
            text_tuple(self.success_metrics, "envelope.success_metrics", limit=12),
        )
        object.__setattr__(
            self,
            "reporting_cadence",
            assert_prose(self.reporting_cadence, "envelope.reporting_cadence"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective_id": self.objective_id,
            "budget": self.budget.to_dict(),
            "budget_scope": self.budget_scope,
            "risk_ceiling": self.risk_ceiling.value,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "allowed_departments": list(self.allowed_departments),
            "forbidden_actions": [item.value for item in self.forbidden_actions],
            "success_metrics": list(self.success_metrics),
            "reporting_cadence": self.reporting_cadence,
        }

    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())


@dataclass(frozen=True)
class Objective:
    """One rung of the ladder, tied to the rung above it by a digest."""

    objective_id: str
    level: ObjectiveLevel
    title: str
    owner_seat: str
    set_by: str
    set_on: dt.date
    parent_id: str = ""
    parent_intent: str = ""  # the parent fingerprint this was derived from
    department: str = ""
    success_metrics: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    envelope: PlanningEnvelope | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "objective_id", assert_record_id(self.objective_id, "objective_id")
        )
        object.__setattr__(self, "level", parse_level(self.level, "objective.level"))
        object.__setattr__(self, "title", assert_prose(self.title, "objective.title"))
        object.__setattr__(
            self, "owner_seat", assert_seat_id(self.owner_seat, "objective.owner_seat")
        )
        object.__setattr__(
            self, "set_by", assert_prose(self.set_by, "objective.set_by")
        )
        object.__setattr__(self, "set_on", assert_day(self.set_on, "objective.set_on"))
        if self.level is ObjectiveLevel.CEO_OBJECTIVE:
            if self.parent_id or self.parent_intent:
                raise DelegationError(
                    "a CEO objective is the root and is derived from nothing"
                )
            if self.envelope is None:
                raise DelegationError(
                    "a CEO objective carries the planning envelope. Without one, "
                    "every executive below it plans against no limit."
                )
        else:
            object.__setattr__(
                self, "parent_id", assert_record_id(self.parent_id, "objective.parent_id")
            )
            if self.parent_id == self.objective_id:
                raise DelegationError(f"objective {self.objective_id} is its own parent")
            if not self.parent_intent:
                raise DelegationError(
                    f"objective {self.objective_id} records no parent intent digest. "
                    "Without it, an edit to the objective above would go unnoticed."
                )
            object.__setattr__(
                self,
                "parent_intent",
                assert_prose(self.parent_intent, "objective.parent_intent"),
            )
        if self.department:
            object.__setattr__(
                self,
                "department",
                assert_prose(self.department, "objective.department").lower(),
            )
        object.__setattr__(
            self,
            "success_metrics",
            text_tuple(self.success_metrics, "objective.success_metrics", limit=12),
        )
        object.__setattr__(
            self,
            "evidence_refs",
            ref_tuple(self.evidence_refs, "objective.evidence_refs"),
        )
        if self.envelope is not None:
            if not isinstance(self.envelope, PlanningEnvelope):
                raise DelegationError("objective.envelope must be a PlanningEnvelope")
            if self.envelope.objective_id != self.objective_id:
                raise DelegationError(
                    f"objective {self.objective_id} carries an envelope for "
                    f"{self.envelope.objective_id}"
                )

    def intent(self) -> str:
        """The digest a child records. Covers intent, never bookkeeping.

        `set_on`, `evidence_refs` and the owning seat are excluded on purpose:
        correcting a date or adding a reference is not a change of intent, and a
        digest that moved when they did would cry wolf until nobody looked.
        """
        return _fingerprint(
            {
                "objective_id": self.objective_id,
                "level": self.level.value,
                "title": self.title,
                "success_metrics": list(self.success_metrics),
                "envelope": self.envelope.to_dict() if self.envelope else None,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective_id": self.objective_id,
            "level": self.level.value,
            "title": self.title,
            "owner_seat": self.owner_seat,
            "set_by": self.set_by,
            "set_on": self.set_on.isoformat(),
            "parent_id": self.parent_id,
            "parent_intent": self.parent_intent,
            "department": self.department,
            "success_metrics": list(self.success_metrics),
            "evidence_refs": list(self.evidence_refs),
            "envelope": self.envelope.to_dict() if self.envelope else None,
        }

    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())


@dataclass(frozen=True)
class ObjectiveTree:
    """A set of objectives, and the lineage checks over them."""

    objectives: tuple[Objective, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.objectives, tuple) or not self.objectives:
            raise DelegationError("an objective tree needs at least one objective")
        by_id: dict[str, Objective] = {}
        for item in self.objectives:
            if not isinstance(item, Objective):
                raise DelegationError("every entry must be an Objective")
            if item.objective_id in by_id:
                raise DelegationError(f"objective {item.objective_id} appears twice")
            by_id[item.objective_id] = item
        object.__setattr__(self, "_by_id", by_id)

    @property
    def _index(self) -> dict[str, Objective]:
        return getattr(self, "_by_id")

    def objective(self, objective_id: str) -> Objective | None:
        return self._index.get(objective_id)

    def roots(self) -> tuple[Objective, ...]:
        return tuple(
            item
            for item in self.objectives
            if item.level is ObjectiveLevel.CEO_OBJECTIVE
        )

    def children(self, objective_id: str) -> tuple[Objective, ...]:
        return tuple(
            sorted(
                (item for item in self.objectives if item.parent_id == objective_id),
                key=lambda item: item.objective_id,
            )
        )

    def lineage(self, objective_id: str) -> tuple[Objective, ...]:
        """This objective and every one above it, narrowest first."""
        out: list[Objective] = []
        seen: set[str] = set()
        current = self._index.get(objective_id)
        while current is not None:
            if current.objective_id in seen:
                raise DelegationError(
                    f"objective lineage loops at {current.objective_id}"
                )
            seen.add(current.objective_id)
            out.append(current)
            current = self._index.get(current.parent_id) if current.parent_id else None
        return tuple(out)

    def root_of(self, objective_id: str) -> Objective | None:
        chain = self.lineage(objective_id)
        if not chain:
            return None
        top = chain[-1]
        return top if top.level is ObjectiveLevel.CEO_OBJECTIVE else None

    def envelope_for(self, objective_id: str) -> PlanningEnvelope | None:
        """The envelope in force here: the nearest one at or above this rung."""
        for item in self.lineage(objective_id):
            if item.envelope is not None:
                return item.envelope
        return None

    def lineage_violations(self) -> tuple[str, ...]:
        """Every broken link: a missing parent, a skipped rung, a changed intent."""
        problems: list[str] = []
        for item in sorted(self.objectives, key=lambda o: o.objective_id):
            if item.level is ObjectiveLevel.CEO_OBJECTIVE:
                continue
            parent = self._index.get(item.parent_id)
            if parent is None:
                problems.append(
                    f"{item.objective_id} names parent {item.parent_id!r}, which the "
                    "tree does not carry; it traces back to no CEO objective"
                )
                continue
            expected_level = LEVEL_ORDER[LEVEL_ORDER.index(item.level) - 1]
            if parent.level is not expected_level:
                problems.append(
                    f"{item.objective_id} is a {item.level.value} whose parent "
                    f"{parent.objective_id} is a {parent.level.value}; a "
                    f"{item.level.value} hangs from a {expected_level.value}"
                )
            if parent.intent() != item.parent_intent:
                problems.append(
                    f"{item.objective_id} was derived from {parent.objective_id} at "
                    f"intent {item.parent_intent}, and that objective now reads "
                    f"{parent.intent()}. The objective above it changed after it was "
                    "decomposed; a changed CEO intent is a new objective, not an edit."
                )
        for item in sorted(self.objectives, key=lambda o: o.objective_id):
            try:
                root = self.root_of(item.objective_id)
            except DelegationError as exc:
                problems.append(str(exc))
                continue
            if root is None:
                problems.append(
                    f"{item.objective_id} does not trace back to a CEO objective"
                )
        return tuple(dict.fromkeys(problems))

    def to_dict(self) -> dict[str, Any]:
        return {"objectives": [item.to_dict() for item in self.objectives]}


@dataclass(frozen=True)
class ExecutivePlan:
    """What an executive intends to do for one objective, in checkable terms."""

    plan_id: str
    objective_id: str
    planned_by: str
    planned_on: dt.date
    envelope_fingerprint: str
    departments: tuple[str, ...] = ()
    actions: tuple[ActionType, ...] = ()
    estimated_spend: Money | None = None
    max_risk: Risk = Risk.LOW
    completion_by: dt.date | None = None
    steps: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "plan_id", assert_record_id(self.plan_id, "plan_id"))
        object.__setattr__(
            self, "objective_id", assert_record_id(self.objective_id, "plan.objective_id")
        )
        object.__setattr__(
            self, "planned_by", assert_seat_id(self.planned_by, "plan.planned_by")
        )
        object.__setattr__(
            self, "planned_on", assert_day(self.planned_on, "plan.planned_on")
        )
        object.__setattr__(
            self,
            "envelope_fingerprint",
            assert_prose(self.envelope_fingerprint, "plan.envelope_fingerprint"),
        )
        object.__setattr__(
            self, "departments", name_tuple(self.departments, "plan.departments")
        )
        object.__setattr__(
            self,
            "actions",
            tuple(
                sorted(
                    {parse_action(item, "plan.actions") for item in (self.actions or ())},
                    key=lambda item: item.value,
                )
            ),
        )
        if self.estimated_spend is not None and not isinstance(
            self.estimated_spend, Money
        ):
            raise DelegationError("plan.estimated_spend must be Money or None")
        object.__setattr__(self, "max_risk", parse_risk(self.max_risk, "plan.max_risk"))
        if self.completion_by is not None:
            object.__setattr__(
                self, "completion_by", assert_day(self.completion_by, "plan.completion_by")
            )
        object.__setattr__(self, "steps", text_tuple(self.steps, "plan.steps", limit=24))

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "objective_id": self.objective_id,
            "planned_by": self.planned_by,
            "planned_on": self.planned_on.isoformat(),
            "envelope_fingerprint": self.envelope_fingerprint,
            "departments": list(self.departments),
            "actions": [item.value for item in self.actions],
            "estimated_spend": (
                self.estimated_spend.to_dict() if self.estimated_spend else None
            ),
            "max_risk": self.max_risk.value,
            "completion_by": (
                self.completion_by.isoformat() if self.completion_by else None
            ),
            "steps": list(self.steps),
        }

    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())


def envelope_violations(
    plan: ExecutivePlan, envelope: PlanningEnvelope
) -> tuple[str, ...]:
    """Every way this plan leaves the envelope. Empty means it stays inside.

    A non-empty result is an escalation, not a licence to widen the envelope.
    The distinction is the reason this returns strings and not a new envelope.
    """
    if not isinstance(plan, ExecutivePlan):
        raise DelegationError("envelope_violations takes an ExecutivePlan")
    if not isinstance(envelope, PlanningEnvelope):
        raise DelegationError("envelope_violations takes a PlanningEnvelope")
    problems: list[str] = []
    if plan.objective_id != envelope.objective_id:
        problems.append(
            f"the plan is for {plan.objective_id} and the envelope is for "
            f"{envelope.objective_id}"
        )
    if plan.envelope_fingerprint != envelope.fingerprint():
        problems.append(
            f"the plan was written against envelope {plan.envelope_fingerprint} and "
            f"the envelope now reads {envelope.fingerprint()}; replan against the "
            "current envelope rather than assuming the old limits"
        )
    outside = sorted(set(plan.departments) - set(envelope.allowed_departments))
    if outside:
        problems.append(
            "the plan uses department(s) the envelope does not allow: "
            + ", ".join(outside)
        )
    forbidden = sorted(
        item.value for item in plan.actions if item in set(envelope.forbidden_actions)
    )
    if forbidden:
        problems.append(
            "the plan requires action(s) the envelope forbids: " + ", ".join(forbidden)
        )
    if risk_rank(plan.max_risk) > risk_rank(envelope.risk_ceiling):
        problems.append(
            f"the plan carries {plan.max_risk.value} risk and the envelope ceiling is "
            f"{envelope.risk_ceiling.value}"
        )
    if plan.estimated_spend is not None:
        if plan.estimated_spend.currency != envelope.budget.currency:
            problems.append(
                f"the plan is costed in {plan.estimated_spend.currency} and the "
                f"envelope budget is {envelope.budget.currency}"
            )
        elif plan.estimated_spend > envelope.budget:
            problems.append(
                f"the plan estimates {plan.estimated_spend} against an envelope budget "
                f"of {envelope.budget}"
            )
    if (
        envelope.deadline is not None
        and plan.completion_by is not None
        and plan.completion_by > envelope.deadline
    ):
        problems.append(
            f"the plan completes on {plan.completion_by.isoformat()} and the envelope "
            f"deadline is {envelope.deadline.isoformat()}"
        )
    return tuple(problems)


def decompose(
    parent: Objective,
    *,
    objective_id: str,
    title: str,
    owner_seat: str,
    set_by: str,
    set_on: dt.date,
    department: str = "",
    success_metrics: Sequence[str] = (),
    evidence_refs: Sequence[str] = (),
) -> Objective:
    """Derive the next rung down, stamped with the parent's current intent.

    There is no `level` parameter: the level is the one rung below the parent,
    and letting a caller choose it is how a work order ends up hanging off a CEO
    objective with no department in between.
    """
    if not isinstance(parent, Objective):
        raise DelegationError("decompose takes an Objective as the parent")
    index = LEVEL_ORDER.index(parent.level)
    if index + 1 >= len(LEVEL_ORDER):
        raise DelegationError(
            f"a {parent.level.value} is the last rung and decomposes into nothing"
        )
    return Objective(
        objective_id=objective_id,
        level=LEVEL_ORDER[index + 1],
        title=title,
        owner_seat=owner_seat,
        set_by=set_by,
        set_on=set_on,
        parent_id=parent.objective_id,
        parent_intent=parent.intent(),
        department=department or parent.department,
        success_metrics=tuple(success_metrics),
        evidence_refs=tuple(evidence_refs),
    )


def assert_within_intent(child: Objective, parent: Objective) -> None:
    """Refuse a child derived from an intent the parent no longer has."""
    if child.parent_id != parent.objective_id:
        raise DelegationError(
            f"{child.objective_id} names parent {child.parent_id}, not "
            f"{parent.objective_id}"
        )
    if child.parent_intent != parent.intent():
        raise AuthorityViolation(
            f"{child.objective_id} was derived from {parent.objective_id} at intent "
            f"{child.parent_intent}, which now reads {parent.intent()}. An executive "
            "may decompose a CEO objective; it may not restate one."
        )


def objectives_from(values: Any) -> ObjectiveTree:
    """Build a tree from decoded mappings, for a stored or fixture tree."""
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
        raise DelegationError("objectives must be a list of mappings")
    built: list[Objective] = []
    for item in values:
        if not isinstance(item, Mapping):
            raise DelegationError("each objective must be a mapping")
        envelope_raw = item.get("envelope")
        envelope = None
        if isinstance(envelope_raw, Mapping):
            envelope = PlanningEnvelope(
                objective_id=str(envelope_raw.get("objective_id", "")),
                budget=Money.from_dict(dict(envelope_raw.get("budget", {})), "budget"),
                budget_scope=str(envelope_raw.get("budget_scope", "")),
                risk_ceiling=parse_risk(envelope_raw.get("risk_ceiling")),
                deadline=(
                    dt.date.fromisoformat(str(envelope_raw["deadline"]))
                    if envelope_raw.get("deadline")
                    else None
                ),
                allowed_departments=tuple(envelope_raw.get("allowed_departments", ())),
                forbidden_actions=tuple(
                    parse_action(name) for name in envelope_raw.get("forbidden_actions", ())
                ),
                success_metrics=tuple(envelope_raw.get("success_metrics", ())),
                reporting_cadence=str(
                    envelope_raw.get("reporting_cadence", "on_exception")
                ),
            )
        built.append(
            Objective(
                objective_id=str(item.get("objective_id", "")),
                level=parse_level(item.get("level")),
                title=str(item.get("title", "")),
                owner_seat=str(item.get("owner_seat", "")),
                set_by=str(item.get("set_by", "")),
                set_on=assert_day(item.get("set_on"), "objective.set_on"),
                parent_id=str(item.get("parent_id", "") or ""),
                parent_intent=str(item.get("parent_intent", "") or ""),
                department=str(item.get("department", "") or ""),
                success_metrics=tuple(item.get("success_metrics", ())),
                evidence_refs=tuple(item.get("evidence_refs", ())),
                envelope=envelope,
            )
        )
    return ObjectiveTree(tuple(built))


__all__ = [
    "LEVEL_ORDER",
    "ExecutivePlan",
    "Objective",
    "ObjectiveLevel",
    "ObjectiveTree",
    "PlanningEnvelope",
    "assert_within_intent",
    "decompose",
    "envelope_violations",
    "objectives_from",
    "parse_level",
]

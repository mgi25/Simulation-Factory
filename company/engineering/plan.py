"""The implementation plan: a proposal about *how*, bounded by the work order.

A plan is the one record in this package that is allowed to be wrong. It says
which stages the work will move through and which paths each stage expects to
touch, and a developer that finds a better route may take it.

What it may never do is widen the ceiling. `assert_within` checks every path a
step claims against the work order's authorized paths, its forbidden paths and
its protected surface, and raises `AuthorityEscalation` on the first step that
reaches outside. So a plan is a proposal about method and never a grant of
authority — which is the distinction section 4 of the engineering brief asks
for, made into a call that raises.

## Why the default plan is deterministic

`derive_plan` produces the same seven stages for every work order: inspect,
locate the contract, implement, test, run the affected suites, run the
governance gate, prepare review evidence. They are not a guess about the work
— they are the company's own completion protocol
(`company.runtime.packets.COMPLETION_PROTOCOL`) plus the two stages this
package adds, expressed as an ordered list a reader can check off.

A model could produce a better-informed plan, and if one does it is decoded
through `ImplementationPlan.from_mapping` and held to exactly the same
`assert_within`. The deterministic default exists so that the loop has a plan
even when nothing has reasoned yet (constitution rule 4: deterministic code
first).
"""

from __future__ import annotations

from collections.abc import Mapping
import datetime as dt
from dataclasses import dataclass
from typing import Any

from ai_platform.serde import fingerprint as _fingerprint
from ai_platform.serde import to_jsonable
from company.runtime.path_scope import normalise_path

from .common import assert_day, assert_prose, assert_record_id, text_tuple
from .errors import AuthorityEscalation, EngineeringError
from .work_order import EngineeringWorkOrder


PLAN_VERSION = 1


@dataclass(frozen=True)
class PlanStep:
    """One stage of the work, and the paths it expects to touch."""

    step_id: str
    action: str
    touches: tuple[str, ...] = ()
    writes: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "step_id", assert_record_id(self.step_id, "step.step_id"))
        object.__setattr__(self, "action", assert_prose(self.action, "step.action"))
        if not isinstance(self.touches, (list, tuple)) or isinstance(self.touches, str):
            raise EngineeringError("step.touches must be a list of paths")
        object.__setattr__(
            self,
            "touches",
            tuple(
                sorted(
                    {
                        normalise_path(item, f"step[{self.step_id}].touches")
                        for item in self.touches
                    }
                )
            ),
        )
        if not isinstance(self.writes, bool):
            raise EngineeringError("step.writes must be a boolean")

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class ImplementationPlan:
    """An ordered proposal for satisfying one work order."""

    work_order_id: str
    work_order_fingerprint: str
    steps: tuple[PlanStep, ...]
    proposed_by: str
    proposed_on: dt.date
    notes: tuple[str, ...] = ()
    version: int = PLAN_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "work_order_id", assert_record_id(self.work_order_id, "plan.work_order_id")
        )
        if not isinstance(self.work_order_fingerprint, str) or len(
            self.work_order_fingerprint
        ) != 16:
            raise EngineeringError(
                "plan.work_order_fingerprint must be a 16-character digest"
            )
        if not isinstance(self.steps, tuple) or any(
            not isinstance(step, PlanStep) for step in self.steps
        ):
            raise EngineeringError("plan.steps must be a tuple of PlanStep values")
        if not self.steps:
            raise EngineeringError("plan.steps is empty: a plan with no stage is not a plan")
        ids = [step.step_id for step in self.steps]
        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        if duplicates:
            raise EngineeringError("plan repeats a step id: " + ", ".join(duplicates))
        object.__setattr__(
            self, "proposed_by", assert_prose(self.proposed_by, "plan.proposed_by")
        )
        object.__setattr__(
            self, "proposed_on", assert_day(self.proposed_on, "plan.proposed_on")
        )
        object.__setattr__(self, "notes", text_tuple(self.notes, "plan.notes", limit=16))
        if self.version != PLAN_VERSION:
            raise EngineeringError(f"plan.version must be {PLAN_VERSION}")

    @property
    def writing_paths(self) -> tuple[str, ...]:
        return tuple(
            sorted({path for step in self.steps if step.writes for path in step.touches})
        )

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    def fingerprint(self) -> str:
        return _fingerprint(self)

    def assert_within(self, order: EngineeringWorkOrder) -> "ImplementationPlan":
        """Refuse a plan that reaches beyond the work order it claims to serve.

        Three refusals, and the order matters: the plan must belong to this
        work order, the work order must be the authorized one, and no writing
        step may name a path the work order did not grant. A read-only step may
        name any path — inspecting the repository is not an authority.
        """
        if self.work_order_id != order.work_order_id:
            raise AuthorityEscalation(
                f"plan names work order {self.work_order_id!r}, not {order.work_order_id!r}"
            )
        order.assert_unchanged(self.work_order_fingerprint, "implementation plan")
        scope = order.path_scope()
        issues: list[str] = []
        for step in self.steps:
            if not step.writes:
                continue
            verdict = scope.verdict(step.touches)
            issues.extend(
                f"step {step.step_id}: {failure}" for failure in verdict.failures()
            )
        if issues:
            raise AuthorityEscalation(
                "the plan proposes writing outside the work order's authorized scope: "
                + "; ".join(sorted(issues))
                + ". A plan chooses how the objective is met; it does not choose what "
                "is authorized."
            )
        return self

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ImplementationPlan":
        if not isinstance(data, Mapping):
            raise EngineeringError("a plan must be a mapping")
        unknown = sorted(set(data) - set(cls.__dataclass_fields__))
        if unknown:
            raise EngineeringError("plan has unknown field(s): " + ", ".join(unknown))
        raw_steps = data.get("steps", ())
        if isinstance(raw_steps, (str, bytes)) or not isinstance(raw_steps, (list, tuple)):
            raise EngineeringError("plan.steps must be a list")
        steps = []
        for index, item in enumerate(raw_steps):
            if not isinstance(item, Mapping):
                raise EngineeringError(f"plan.steps[{index}] must be a mapping")
            extra = sorted(set(item) - {"step_id", "action", "touches", "writes"})
            if extra:
                raise EngineeringError(
                    f"plan.steps[{index}] has unknown field(s): " + ", ".join(extra)
                )
            touches = item.get("touches", ())
            if isinstance(touches, (str, bytes)) or not isinstance(touches, (list, tuple)):
                raise EngineeringError(f"plan.steps[{index}].touches must be a list")
            steps.append(
                PlanStep(
                    step_id=str(item.get("step_id", "")),
                    action=str(item.get("action", "")),
                    touches=tuple(str(path) for path in touches),
                    writes=bool(item.get("writes", False)),
                )
            )
        notes = data.get("notes", ())
        if isinstance(notes, (str, bytes)) or not isinstance(notes, (list, tuple)):
            raise EngineeringError("plan.notes must be a list")
        version = data.get("version", PLAN_VERSION)
        if isinstance(version, bool) or not isinstance(version, int):
            raise EngineeringError("plan.version must be an integer")
        return cls(
            work_order_id=str(data.get("work_order_id", "")),
            work_order_fingerprint=str(data.get("work_order_fingerprint", "")),
            steps=tuple(steps),
            proposed_by=str(data.get("proposed_by", "")),
            proposed_on=assert_day(data.get("proposed_on"), "plan.proposed_on"),
            notes=tuple(str(note) for note in notes),
            version=version,
        )


def derive_plan(
    order: EngineeringWorkOrder,
    *,
    proposed_by: str = "company-os intake",
    proposed_on: dt.date | None = None,
) -> ImplementationPlan:
    """The deterministic seven-stage plan, bounded by this work order's scope."""
    authorized = order.authorized_paths
    tests = ", ".join(order.required_tests) or "the suites the change affects"
    steps = (
        PlanStep(
            step_id="inspect",
            action=(
                "Read the authorized paths and the capsule contract they belong to "
                "before changing anything: " + ", ".join(authorized)
            ),
            touches=authorized,
        ),
        PlanStep(
            step_id="locate-contract",
            action=(
                "Identify the smallest contract that the objective is missing, and "
                "state it before implementing it"
            ),
            touches=authorized,
        ),
        PlanStep(
            step_id="implement",
            action="Implement the smallest compatible change inside the authorized paths",
            touches=authorized,
            writes=True,
        ),
        PlanStep(
            step_id="test",
            action="Write focused tests for the new behaviour and for each acceptance criterion",
            touches=authorized,
            writes=True,
        ),
        PlanStep(
            step_id="run-suites",
            action=f"Run the affected suites and report every result: {tests}",
            touches=order.required_tests,
        ),
        PlanStep(
            step_id="gate-evidence",
            action=(
                "Run the existing integration gate over the checkout and keep its "
                "report as evidence; do not modify the gate"
            ),
        ),
        PlanStep(
            step_id="review-evidence",
            action=(
                "Return a receipt naming the changed paths, the commit, the pushed "
                "branch and one evidence reference per acceptance criterion"
            ),
        ),
    )
    plan = ImplementationPlan(
        work_order_id=order.work_order_id,
        work_order_fingerprint=order.fingerprint(),
        steps=steps,
        proposed_by=proposed_by,
        proposed_on=proposed_on or order.authorized_on,
        notes=(
            "Derived deterministically from the work order; a developer may take a "
            "better route inside the same authorized scope.",
        ),
    )
    return plan.assert_within(order)


__all__ = [
    "PLAN_VERSION",
    "ImplementationPlan",
    "PlanStep",
    "derive_plan",
]

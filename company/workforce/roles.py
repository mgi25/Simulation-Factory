"""A proposed role: a complete contract that has not been hired.

## This module cannot hire anyone

`org_registry.yaml` is the workforce source of truth and nothing here writes to
it. A `RoleSpecification` is a *proposal*: it carries `approval` and starts at
`PROPOSED`, and the only thing approval changes is the field. Turning an
approved specification into an employee is an edit to a shared root contract,
which `company/WORKSTREAMS.md` reserves for the integration branch and
`permissions.yaml` gates behind `hire_or_remove_executive_role` for executives.

The check is mechanical rather than cultural: this package imports no writer for
`company/*.yaml`, and `tests/test_company_workforce.py` asserts that the source
of the package contains no write to one.

## Three fields that are not decoration

`no_subagents` is typed `bool` but accepts exactly `True`. Constitution rule 2
forbids nested agents in Bootstrap Mode, and amending it needs CEO approval; a
role specification that could be drafted with `no_subagents=False` would be a
way to route around that with a data file.

`proposed_may_write` is named for what it is. A candidate role holds autonomy
level 0 and no production authority (`permissions.yaml` bootstrap defaults), so
the paths a role would eventually write are a *request*, not a grant, and the
name keeps a reader from mistaking the list for permission. `to_contract()`
therefore emits `may_write: []` while the role is in a restricted state.

`resource_budget` is a budget class plus prose, not a token number. `ai_platform
/usage.py` explains why the platform does not require token counts: a provider
may not expose them. A role whose budget could only be written as a token count
would be a role we could not staff on a provider that counts characters.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any

from ai_platform.serde import to_jsonable
from company.validation.bootstrap import BOOTSTRAP_DEPARTMENTS

from .common import (
    assert_day,
    assert_identifier,
    assert_prose,
    assert_record_id,
    id_tuple,
    optional_ref,
    text_tuple,
)
from .errors import AuthorityViolation, WorkforceError

# Autonomy tokens from permissions.yaml that mean production authority. A
# proposed role may not request one while it is in a restricted state.
PRODUCTION_ACTIONS = frozenset(
    {
        "approved_code_write",
        "approved_operational_actions",
        "approved_org_or_architecture_change",
        "production_write",
    }
)

RESTRICTED_STATES = frozenset({"candidate", "shadow", "probation"})

BUDGET_CLASSES = ("small", "medium", "large")


class ApprovalState(Enum):
    """Where a proposal is, never what it may do."""

    PROPOSED = "proposed"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


@dataclass(frozen=True)
class ResourceBudget:
    """What a role is expected to cost, in units that survive a provider change."""

    budget_class: str = "small"
    max_passes_per_task: int = 2
    notes: str = ""

    def __post_init__(self) -> None:
        if self.budget_class not in BUDGET_CLASSES:
            raise WorkforceError(
                f"budget_class must be one of {', '.join(BUDGET_CLASSES)}, "
                f"got {self.budget_class!r}"
            )
        if (
            isinstance(self.max_passes_per_task, bool)
            or not isinstance(self.max_passes_per_task, int)
            or self.max_passes_per_task < 1
        ):
            raise WorkforceError("max_passes_per_task must be an integer of at least 1")
        if not isinstance(self.notes, str):
            raise WorkforceError("resource budget notes must be a string")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResourceBudget:
        return cls(
            budget_class=data.get("budget_class", "small"),
            max_passes_per_task=data.get("max_passes_per_task", 2),
            notes=data.get("notes", ""),
        )


@dataclass(frozen=True)
class RoleSpecification:
    """Everything `agent_contract.schema.yaml` requires, in proposal form."""

    role_id: str
    mission: str
    department: str
    manager: str
    required_capabilities: tuple[str, ...]
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    may_read: tuple[str, ...]
    proposed_may_write: tuple[str, ...] = ()
    may_not_modify: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    quality_gates: tuple[str, ...] = ()
    evidence_requirements: tuple[str, ...] = ()
    escalation_conditions: tuple[str, ...] = ()
    success_metrics: tuple[str, ...] = (
        "correctness",
        "first_pass_success",
        "regressions_caused",
        "accepted_recommendations",
        "resource_per_accepted_deliverable",
    )
    resource_budget: ResourceBudget = ResourceBudget()
    state: str = "candidate"
    approval: ApprovalState = ApprovalState.PROPOSED
    gap_id: str = ""
    proposed_on: dt.date | None = None
    no_subagents: bool = True

    def __post_init__(self) -> None:
        assert_identifier(self.role_id, "role_id")
        assert_prose(self.mission, f"role {self.role_id} mission")
        if self.department not in BOOTSTRAP_DEPARTMENTS:
            raise WorkforceError(
                f"role {self.role_id}: {self.department!r} is not a Bootstrap v1 department "
                f"({', '.join(sorted(BOOTSTRAP_DEPARTMENTS))})"
            )
        if self.manager != "ceo":
            assert_identifier(self.manager, f"role {self.role_id} manager")
        for name in ("required_capabilities", "tools"):
            object.__setattr__(
                self, name, id_tuple(getattr(self, name), f"role {self.role_id} {name}", sort=True)
            )
        if not self.required_capabilities:
            raise WorkforceError(f"role {self.role_id}: a role with no capabilities is a title")
        for name in (
            "inputs",
            "outputs",
            "may_read",
            "proposed_may_write",
            "may_not_modify",
            "quality_gates",
            "evidence_requirements",
            "escalation_conditions",
            "success_metrics",
        ):
            object.__setattr__(
                self, name, text_tuple(getattr(self, name), f"role {self.role_id} {name}")
            )
        for name in ("inputs", "outputs", "may_read", "quality_gates", "success_metrics"):
            if not getattr(self, name):
                raise WorkforceError(
                    f"role {self.role_id}: {name} must not be empty - "
                    "agent_contract.schema.yaml requires it of every employee"
                )
        if not isinstance(self.resource_budget, ResourceBudget):
            raise WorkforceError(f"role {self.role_id}: resource_budget must be a ResourceBudget")
        if not isinstance(self.approval, ApprovalState):
            raise WorkforceError(f"role {self.role_id}: approval must be an ApprovalState")
        if self.state not in RESTRICTED_STATES | {"active", "dormant", "archived"}:
            raise WorkforceError(f"role {self.role_id}: {self.state!r} is not an employment state")
        object.__setattr__(self, "gap_id", optional_ref(self.gap_id, "role gap_id"))
        if self.proposed_on is not None:
            object.__setattr__(
                self, "proposed_on", assert_day(self.proposed_on, "role proposed_on")
            )

        if self.no_subagents is not True:
            raise WorkforceError(
                f"role {self.role_id}: no_subagents must be exactly True. Constitution "
                "rule 2 forbids nested agents in Bootstrap Mode, and amending it needs "
                "CEO approval - not a field on a role proposal"
            )
        self._assert_no_production_authority()

    def _assert_no_production_authority(self) -> None:
        if self.state not in RESTRICTED_STATES:
            return
        requested = PRODUCTION_ACTIONS.intersection(self.proposed_may_write)
        requested |= PRODUCTION_ACTIONS.intersection(self.tools)
        if requested:
            raise AuthorityViolation(
                f"role {self.role_id}: a {self.state} role requests production authority "
                f"({', '.join(sorted(requested))}). Constitution rule 11 - sandbox before "
                "production - makes that an evaluation outcome, not a proposal field"
            )

    # -- reading ----------------------------------------------------------

    @property
    def is_restricted(self) -> bool:
        return self.state in RESTRICTED_STATES

    @property
    def grants_production_write(self) -> bool:
        """Always False while restricted. Kept as a property so callers can assert it."""
        return not self.is_restricted and bool(self.proposed_may_write)

    def to_contract(self, *, permissions: dict[str, Any] | None = None) -> dict[str, Any]:
        """The `agent_contract.schema.yaml` shape, with authority failed closed.

        `may_write` is emitted empty for a restricted role no matter what the
        proposal requested, and `autonomy_level` comes from the permissions
        bootstrap defaults rather than from this record. A specification cannot
        talk itself into authority by filling in its own fields.
        """
        level = _restricted_level(self.state, permissions)
        contract: dict[str, Any] = {
            "employee_id": self.role_id,
            "mission": self.mission,
            "department": self.department,
            "manager": self.manager,
            "state": self.state,
            "capabilities": list(self.required_capabilities),
            "tools": list(self.tools),
            "input_contract": list(self.inputs),
            "output_contract": list(self.outputs),
            "may_read": list(self.may_read),
            "may_write": [] if self.is_restricted else list(self.proposed_may_write),
            "may_not_modify": list(self.may_not_modify),
            "decisions_allowed": [],
            "quality_gates": list(self.quality_gates),
            "token_policy": {
                "minimum_relevant_context": True,
                "deterministic_first": True,
                "retrieval_before_reasoning": True,
                "prefer_single_pass": True,
                "budget_class": self.resource_budget.budget_class,
            },
            "required_tests": list(self.evidence_requirements),
            "escalation_conditions": list(self.escalation_conditions),
            "success_metrics": list(self.success_metrics),
            "no_subagents": True,
        }
        if level is not None:
            contract["autonomy_level"] = level
            contract["production_authority"] = False
        return contract

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RoleSpecification:
        return cls(
            role_id=data["role_id"],
            mission=data["mission"],
            department=data["department"],
            manager=data["manager"],
            required_capabilities=tuple(data["required_capabilities"]),
            inputs=tuple(data["inputs"]),
            outputs=tuple(data["outputs"]),
            may_read=tuple(data["may_read"]),
            proposed_may_write=tuple(data.get("proposed_may_write", ())),
            may_not_modify=tuple(data.get("may_not_modify", ())),
            tools=tuple(data.get("tools", ())),
            quality_gates=tuple(data["quality_gates"]),
            evidence_requirements=tuple(data.get("evidence_requirements", ())),
            escalation_conditions=tuple(data.get("escalation_conditions", ())),
            success_metrics=tuple(data["success_metrics"]),
            resource_budget=ResourceBudget.from_dict(data.get("resource_budget", {})),
            state=data.get("state", "candidate"),
            approval=ApprovalState(data.get("approval", ApprovalState.PROPOSED.value)),
            gap_id=data.get("gap_id", ""),
            proposed_on=data.get("proposed_on"),
            no_subagents=data.get("no_subagents", True),
        )


def approve_role_specification(
    specification: RoleSpecification, *, by: str, on: dt.date, reason: str
) -> RoleSpecification:
    """Mark a specification approved. Approval is a record, not an action.

    What this does *not* do is add the role to `org_registry.yaml`, grant it
    authority, or change its state. Approval means a human said the proposal is
    worth running an evaluation on; every later step has its own gate.
    """
    assert_prose(by, "approver")
    assert_prose(reason, "approval reason")
    assert_day(on, "approval date")
    if specification.approval is ApprovalState.APPROVED:
        return specification
    if specification.approval in (ApprovalState.REJECTED, ApprovalState.WITHDRAWN):
        raise WorkforceError(
            f"role {specification.role_id}: a {specification.approval.value} proposal is "
            "closed. Draft a new specification citing this one"
        )
    return replace(specification, approval=ApprovalState.APPROVED)


def _restricted_level(state: str, permissions: dict[str, Any] | None) -> int | None:
    if permissions is None or state not in RESTRICTED_STATES:
        return None
    defaults = permissions.get("bootstrap_defaults", {})
    field = {
        "candidate": "candidate_level",
        "shadow": "shadow_level",
        "probation": "probation_max_level",
    }[state]
    value = defaults.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise WorkforceError(
            f"permissions.bootstrap_defaults.{field} is not an integer; a role cannot be "
            "given an authority level the permission file does not define"
        )
    return value

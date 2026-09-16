"""The employment lifecycle, and the evidence each step of it costs.

    candidate -> shadow -> probation -> active -> dormant -> archived
    candidate | shadow | probation -> rejected
    archived -> dormant, and only on a recorded reactivation decision

## Why `rejected` is not in org_registry.yaml

`org_registry.yaml` declares six employment states and `rejected` is not among
them, which looks like an omission until you notice what it would mean: a
rejected candidate is not an employee in a terminal state, it is someone who
never became an employee. The registry holds the workforce; this module holds
the *process*, and the process has one state more than the workforce does.
`EmploymentState.REJECTED.registry_state` is `None` and `integrity.py` checks
that every other state does map onto a declared one, so the two vocabularies
cannot silently drift apart.

Adding `rejected` to the registry would also fail `validate_bootstrap`, which
accepts exactly the six. Changing a shared root contract is reserved to the
integration branch (`company/WORKSTREAMS.md`), and no gap here justifies it.

## Gates are per edge, not per destination

`candidate -> shadow` and `archived -> dormant` both end somewhere non-terminal
and have nothing else in common. So `_GATES` is keyed by the whole edge, and
each entry names the evidence kinds the transition needs. The three that matter:

    candidate -> shadow     an approved role specification
    shadow -> probation     a passed candidate evaluation
    probation -> active     a shadow comparison *and* a probation review

which is the mechanical form of "no production authority without evaluation"
(`permissions.yaml`, `production_write_requires`). `candidate -> active` is not
an edge at all, so the jump cannot be made by supplying more evidence - it can
only be made by walking through shadow and probation.

## Authority fails closed

`assert_authority` refuses a level above the cap for a restricted state, and
`assert_may_not_write_production` refuses production write for candidate,
shadow and probation regardless of what any other record says. Both read their
caps from `permissions.yaml` rather than from constants here, so tightening the
permission file tightens this module.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any

from ai_platform.serde import to_jsonable
from knowledge.company_os.records import Evidence

from .common import (
    assert_day,
    assert_identifier,
    assert_prose,
    evidence_kinds,
    evidence_tuple,
)
from .errors import AuthorityViolation, LifecycleViolation, WorkforceError

PRODUCTION_WRITE_ACTIONS = frozenset(
    {
        "approved_code_write",
        "approved_operational_actions",
        "approved_org_or_architecture_change",
        "production_write",
    }
)


class EmploymentState(Enum):
    CANDIDATE = "candidate"
    SHADOW = "shadow"
    PROBATION = "probation"
    ACTIVE = "active"
    DORMANT = "dormant"
    ARCHIVED = "archived"
    REJECTED = "rejected"

    @property
    def registry_state(self) -> str | None:
        """The `org_registry.yaml` employment state, or `None` for `REJECTED`."""
        return None if self is EmploymentState.REJECTED else self.value

    @property
    def is_restricted(self) -> bool:
        return self in _RESTRICTED

    @property
    def is_terminal(self) -> bool:
        return not ALLOWED_TRANSITIONS[self]

    @property
    def is_running(self) -> bool:
        """Does this state consume routine reasoning? Constitution rule 18."""
        return self in (EmploymentState.ACTIVE, EmploymentState.SHADOW, EmploymentState.PROBATION)


_RESTRICTED = frozenset(
    {EmploymentState.CANDIDATE, EmploymentState.SHADOW, EmploymentState.PROBATION}
)

ALLOWED_TRANSITIONS: dict[EmploymentState, frozenset[EmploymentState]] = {
    EmploymentState.CANDIDATE: frozenset({EmploymentState.SHADOW, EmploymentState.REJECTED}),
    EmploymentState.SHADOW: frozenset({EmploymentState.PROBATION, EmploymentState.REJECTED}),
    EmploymentState.PROBATION: frozenset({EmploymentState.ACTIVE, EmploymentState.REJECTED}),
    EmploymentState.ACTIVE: frozenset({EmploymentState.DORMANT, EmploymentState.ARCHIVED}),
    EmploymentState.DORMANT: frozenset({EmploymentState.ACTIVE, EmploymentState.ARCHIVED}),
    # An archived role comes back dormant, never straight to active: waking it
    # up is one decision and putting it to work is another.
    EmploymentState.ARCHIVED: frozenset({EmploymentState.DORMANT}),
    EmploymentState.REJECTED: frozenset(),
}

# Edge -> (required evidence kinds, why).
_GATES: dict[tuple[EmploymentState, EmploymentState], tuple[frozenset[str], str]] = {
    (EmploymentState.CANDIDATE, EmploymentState.SHADOW): (
        frozenset({"role_approval"}),
        "shadowing consumes a real reviewer's attention; the role has to be approved first",
    ),
    (EmploymentState.SHADOW, EmploymentState.PROBATION): (
        frozenset({"candidate_evaluation"}),
        "permissions.yaml requires evaluation_pass before anything approaching authority",
    ),
    (EmploymentState.PROBATION, EmploymentState.ACTIVE): (
        frozenset({"shadow_comparison", "probation_review"}),
        "going active is the step that can end in production authority; it needs both the "
        "comparison against the incumbent and a human review of the probation period",
    ),
    (EmploymentState.DORMANT, EmploymentState.ACTIVE): (
        frozenset({"activation_decision"}),
        "constitution rule 18 - waking an employee up starts consuming routine reasoning",
    ),
    (EmploymentState.ARCHIVED, EmploymentState.DORMANT): (
        frozenset({"reactivation_decision"}),
        "an archived role was retired for a reason; reversing that is a recorded decision",
    ),
}


@dataclass(frozen=True)
class EmploymentTransition:
    """One signed step. Who, when, why, and what backs it."""

    from_state: EmploymentState
    to_state: EmploymentState
    on: dt.date
    by: str
    reason: str
    evidence: tuple[Evidence, ...] = ()

    def __post_init__(self) -> None:
        for name in ("from_state", "to_state"):
            if not isinstance(getattr(self, name), EmploymentState):
                raise WorkforceError(f"transition {name} must be an EmploymentState")
        object.__setattr__(self, "on", assert_day(self.on, "transition date"))
        assert_prose(self.by, "transition by")
        assert_prose(self.reason, "transition reason")
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))
        if self.from_state is self.to_state:
            raise LifecycleViolation(
                f"{self.from_state.value} -> itself is not a transition"
            )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EmploymentTransition:
        return cls(
            from_state=EmploymentState(data["from_state"]),
            to_state=EmploymentState(data["to_state"]),
            on=assert_day(data["on"], "on"),
            by=data["by"],
            reason=data["reason"],
            evidence=evidence_tuple(data.get("evidence")),
        )


@dataclass(frozen=True)
class EmploymentRecord:
    """One person's position in the process, plus how they got there."""

    employee_id: str
    state: EmploymentState = EmploymentState.CANDIDATE
    role_specification_id: str = ""
    history: tuple[EmploymentTransition, ...] = ()

    def __post_init__(self) -> None:
        assert_identifier(self.employee_id, "employee_id")
        if not isinstance(self.state, EmploymentState):
            raise WorkforceError("employment state must be an EmploymentState")
        if not isinstance(self.role_specification_id, str):
            raise WorkforceError("role_specification_id must be a string")
        if not isinstance(self.history, tuple) or any(
            not isinstance(item, EmploymentTransition) for item in self.history
        ):
            raise WorkforceError("history must be a tuple of EmploymentTransition")
        for earlier, later in zip(self.history, self.history[1:]):
            if earlier.to_state is not later.from_state:
                raise LifecycleViolation(
                    f"{self.employee_id}: history jumps from {earlier.to_state.value!r} to "
                    f"{later.from_state.value!r} with no transition between them"
                )
        if self.history and self.history[-1].to_state is not self.state:
            raise LifecycleViolation(
                f"{self.employee_id}: state is {self.state.value!r} but the last transition "
                f"ended at {self.history[-1].to_state.value!r}"
            )

    @property
    def registry_state(self) -> str | None:
        return self.state.registry_state

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EmploymentRecord:
        return cls(
            employee_id=data["employee_id"],
            state=EmploymentState(data.get("state", EmploymentState.CANDIDATE.value)),
            role_specification_id=data.get("role_specification_id", ""),
            history=tuple(
                EmploymentTransition.from_dict(item) for item in data.get("history", ())
            ),
        )


def can_transition(current: EmploymentState, target: EmploymentState) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


def assert_transition(current: EmploymentState, target: EmploymentState) -> None:
    if can_transition(current, target):
        return
    allowed = sorted(state.value for state in ALLOWED_TRANSITIONS[current])
    if not allowed:
        raise LifecycleViolation(
            f"{current.value!r} is terminal; there is nothing after it to transition to"
        )
    raise LifecycleViolation(
        f"cannot go from {current.value!r} to {target.value!r}; allowed from here: "
        + ", ".join(allowed)
    )


def required_evidence_kinds(
    current: EmploymentState, target: EmploymentState
) -> frozenset[str]:
    kinds, _why = _GATES.get((current, target), (frozenset(), ""))
    return kinds


def advance(
    record: EmploymentRecord,
    to_state: EmploymentState,
    *,
    on: dt.date,
    by: str,
    reason: str,
    evidence: tuple[Evidence, ...] = (),
) -> EmploymentRecord:
    """Move one employee one step, appending a signed transition.

    The history is appended to and never rewritten, so a rejected candidate's
    two transitions stay readable a year later.
    """
    assert_transition(record.state, to_state)
    supplied = evidence_tuple(evidence)
    needed, why = _GATES.get((record.state, to_state), (frozenset(), ""))
    missing = needed - evidence_kinds(supplied)
    if missing:
        raise LifecycleViolation(
            f"{record.employee_id}: {record.state.value} -> {to_state.value} needs evidence "
            f"of kind {', '.join(sorted(missing))} and none was supplied. {why}"
        )
    step = EmploymentTransition(
        from_state=record.state,
        to_state=to_state,
        on=on,
        by=by,
        reason=reason,
        evidence=supplied,
    )
    return replace(record, state=to_state, history=(*record.history, step))


# -- authority ------------------------------------------------------------


def state_authority_cap(state: EmploymentState, permissions: dict[str, Any]) -> int:
    """The highest autonomy level this state may hold, read from permissions.yaml.

    Unknown states and a malformed permission file both fail closed at 0, which
    is `observe`: the failure mode of a missing number is no authority, not
    unchecked authority.
    """
    defaults = permissions.get("bootstrap_defaults", {}) if isinstance(permissions, dict) else {}
    field = {
        EmploymentState.CANDIDATE: "candidate_level",
        EmploymentState.SHADOW: "shadow_level",
        EmploymentState.PROBATION: "probation_max_level",
    }.get(state)
    if field is None:
        if state is EmploymentState.ACTIVE:
            return max(
                (int(key) for key in permissions.get("autonomy_levels", {}) if str(key).isdigit()),
                default=0,
            )
        return 0
    value = defaults.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value


def assert_authority(
    state: EmploymentState, autonomy_level: int, permissions: dict[str, Any]
) -> None:
    if isinstance(autonomy_level, bool) or not isinstance(autonomy_level, int):
        raise AuthorityViolation("autonomy_level must be an integer")
    cap = state_authority_cap(state, permissions)
    if autonomy_level > cap:
        raise AuthorityViolation(
            f"a {state.value} employee may not hold autonomy level {autonomy_level}; "
            f"permissions.yaml caps it at {cap}"
        )


def assert_may_not_write_production(
    state: EmploymentState, requested: tuple[str, ...] | frozenset[str]
) -> None:
    """Refuse production authority for any restricted state.

    Checked against the request rather than against a granted permission,
    because the only safe moment to refuse is before the grant exists.
    """
    if not state.is_restricted:
        return
    forbidden = PRODUCTION_WRITE_ACTIONS.intersection(requested)
    if forbidden:
        raise AuthorityViolation(
            f"a {state.value} employee may not hold production authority: "
            + ", ".join(sorted(forbidden))
            + ". Constitution rule 11 - sandbox before production"
        )


def history_violations(record: EmploymentRecord) -> tuple[str, ...]:
    """Every illegal edge in a stored history, for the integrity pass.

    `EmploymentRecord` refuses to be constructed with a discontinuous history,
    but a record decoded from an older file or written by another tool can
    still contain an edge that is now illegal. This reports rather than raises,
    so one integrity run names every problem at once.
    """
    out: list[str] = []
    for step in record.history:
        if not can_transition(step.from_state, step.to_state):
            out.append(
                f"{record.employee_id}: invalid lifecycle jump "
                f"{step.from_state.value} -> {step.to_state.value} on {step.on.isoformat()}"
            )
            continue
        needed = required_evidence_kinds(step.from_state, step.to_state)
        missing = needed - evidence_kinds(step.evidence)
        if missing:
            out.append(
                f"{record.employee_id}: {step.from_state.value} -> {step.to_state.value} on "
                f"{step.on.isoformat()} is missing evidence: {', '.join(sorted(missing))}"
            )
    return tuple(out)

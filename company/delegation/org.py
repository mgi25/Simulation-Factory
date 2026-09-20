"""Seats, who fills them, and which of them can decide anything today.

A **seat** is a position in the management hierarchy: `cto`, `engineering_manager`,
`cfo`. An **employee** is a row in `company/org_registry.yaml`. The two are not
the same thing, and keeping them apart is what makes this module worth having.

## Why a seat is not an employee

The master development plan draws an executive office with a COO, a CTO and a
CFO, and a management layer with an engineering manager, a research lead and an
analytics lead. The canonical registry contains eleven employees, of whom
`studio_coo`, `chief_architect` and `ai_efficiency_platform_engineer` are
`active` and the rest are `dormant`. There is no CFO and no engineering
manager.

Creating either of them is `hire_or_remove_executive_role`, which
`company/permissions.yaml` reserves to the CEO. **So this subsystem cannot
hire.** A seat the plan describes but the registry does not fill is declared
here and reported `VACANT`, and every request that would land on it escalates
past it. The alternative — writing a CFO into `org_registry.yaml` — would have
this package perform a CEO-reserved action in order to model the rule that it
may not.

The consequence is visible rather than hidden: with the registry as it stands,
most delegation paths collapse onto `studio_coo` and `chief_architect`, and the
shadow evaluation says so in as many words.

## Why a dormant employee cannot approve

Constitution rule 18: a defined employee is not a running employee, and a
dormant role consumes no routine reasoning. A dormant seat that could approve
would be a role the company is not paying attention to, signing decisions. So
availability is read from the registry state, and only `active` can decide.

The restricted states go through the canonical ladder rather than a second
opinion about them: `company.workforce.employment.state_authority_cap` reads the
caps out of `permissions.yaml`, and a seat needs a cap at least as high as the
level the policy attaches to the action. A `shadow` employee is capped at 1
(recommend), so it can propose and never approve — which is what shadow means.

## Why `reports_to` is declared and then reconciled

A vacant seat has no registry row, so its manager edge has to be declared. A
filled seat has both, and they can disagree. `registry_conflicts` reports the
disagreement instead of picking a winner, because a silent pick is how a
delegation policy would quietly re-parent the org chart.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from company.workforce.employment import EmploymentState, state_authority_cap

from .common import assert_prose, assert_seat_id, name_tuple
from .errors import AuthorityViolation, DelegationError


CEO_SEAT = "ceo"
"""The external root. Not an employee, and never filled from the registry."""

MAX_CHAIN_DEPTH = 8
"""A chain longer than this is a policy defect, not a deep company."""


class SeatKind(str, Enum):
    """Which layer of the hierarchy a seat belongs to."""

    CEO = "ceo"
    EXECUTIVE = "executive"
    DEPARTMENT_MANAGEMENT = "department_management"
    WORKER = "worker"
    INDEPENDENT_CONTROL = "independent_control"


# The layers, outermost first. A seat may only escalate to a seat at the same
# rank or higher, which is the structural form of "no subordinate override".
LAYER_RANK: dict[SeatKind, int] = {
    SeatKind.WORKER: 0,
    SeatKind.INDEPENDENT_CONTROL: 0,
    SeatKind.DEPARTMENT_MANAGEMENT: 1,
    SeatKind.EXECUTIVE: 2,
    SeatKind.CEO: 3,
}


class SeatAvailability(str, Enum):
    """Whether the seat can decide anything, and if not, why not."""

    EXTERNAL_HUMAN = "external_human"  # the CEO: available, and always an escalation
    ACTIVE = "active"
    RESTRICTED = "restricted"  # candidate, shadow or probation: capped below approval
    DORMANT = "dormant"  # defined, not running (constitution rule 18)
    VACANT = "vacant"  # the plan describes it; the registry does not fill it

    @property
    def can_decide(self) -> bool:
        return self is SeatAvailability.ACTIVE


@dataclass(frozen=True)
class Seat:
    """One position: where it sits, who fills it, and what it covers."""

    seat_id: str
    kind: SeatKind
    title: str
    reports_to: str
    employee: str = ""  # an org_registry employee id, or empty for a vacant seat
    departments: tuple[str, ...] = ()  # the authority domains this seat covers

    def __post_init__(self) -> None:
        object.__setattr__(self, "seat_id", assert_seat_id(self.seat_id, "seat_id"))
        if not isinstance(self.kind, SeatKind):
            raise DelegationError(f"seat {self.seat_id}: kind must be a SeatKind")
        object.__setattr__(self, "title", assert_prose(self.title, "seat.title"))
        if self.kind is SeatKind.CEO:
            if self.seat_id != CEO_SEAT:
                raise DelegationError(
                    f"seat {self.seat_id}: only {CEO_SEAT!r} may be the CEO seat"
                )
            if self.reports_to:
                raise DelegationError("the CEO seat reports to nobody in this model")
            if self.employee:
                raise AuthorityViolation(
                    "the CEO seat is not filled from org_registry.yaml. The human CEO "
                    "is not an employee of the company they own, and a registry row "
                    "claiming to be the CEO would be a seat this subsystem could sign."
                )
        else:
            object.__setattr__(
                self, "reports_to", assert_seat_id(self.reports_to, "seat.reports_to")
            )
            if self.reports_to == self.seat_id:
                raise DelegationError(f"seat {self.seat_id} reports to itself")
        if self.employee:
            object.__setattr__(
                self, "employee", assert_seat_id(self.employee, "seat.employee")
            )
        object.__setattr__(
            self, "departments", name_tuple(self.departments, "seat.departments")
        )

    @property
    def is_vacant(self) -> bool:
        return self.kind is not SeatKind.CEO and not self.employee

    @property
    def is_deterministic_control(self) -> bool:
        """True for a seat that is a mechanism rather than a person.

        `deterministic_qa` and `integration_gate` are `independent_control`
        seats that no employee fills and no employee ever should. Deterministic
        QA is `company/engineering/review.py` computing a verdict; the
        integration gate is that gate's own CLI producing a report. Both are
        code, both already run, and staffing either would replace a
        reproducible check with somebody's opinion.

        They appear as seats so the chart can show that an independent control
        exists and so `LAYER_RANK` can refuse to let a manager overrule one.
        They hold no grant, sit at rank 0, and are never a stop on an
        escalation path, so their emptiness delays nothing. Calling that
        emptiness a *vacancy* is the only thing here that was ever misleading:
        a vacancy is a seat waiting for a hire, and these are not.
        """
        return self.kind is SeatKind.INDEPENDENT_CONTROL and not self.employee

    @property
    def rank(self) -> int:
        return LAYER_RANK[self.kind]

    def to_dict(self) -> dict[str, Any]:
        return {
            "seat_id": self.seat_id,
            "kind": self.kind.value,
            "title": self.title,
            "reports_to": self.reports_to,
            "employee": self.employee,
            "departments": list(self.departments),
        }


@dataclass(frozen=True)
class SeatStanding:
    """What a seat can do right now, and the evidence for the answer."""

    seat: Seat
    availability: SeatAvailability
    employment_state: str
    authority_cap: int
    detail: str

    @property
    def can_decide(self) -> bool:
        return self.availability.can_decide

    def to_dict(self) -> dict[str, Any]:
        return {
            "seat_id": self.seat.seat_id,
            "availability": self.availability.value,
            "employment_state": self.employment_state,
            "authority_cap": self.authority_cap,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class Hierarchy:
    """The declared seats, bound to one org registry and one permissions file."""

    seats: tuple[Seat, ...]
    org_registry: Mapping[str, Any]
    permissions: Mapping[str, Any]
    registry_ref: str = "company/org_registry.yaml"

    def __post_init__(self) -> None:
        if not isinstance(self.seats, tuple) or not self.seats:
            raise DelegationError("a hierarchy needs at least the CEO seat")
        by_id: dict[str, Seat] = {}
        for seat in self.seats:
            if not isinstance(seat, Seat):
                raise DelegationError("every entry in seats must be a Seat")
            if seat.seat_id in by_id:
                raise DelegationError(f"seat {seat.seat_id} is declared twice")
            by_id[seat.seat_id] = seat
        if CEO_SEAT not in by_id:
            raise DelegationError(
                f"a hierarchy must declare the {CEO_SEAT!r} seat: it is the only "
                "termination an escalation chain has"
            )
        for seat in self.seats:
            if seat.kind is SeatKind.CEO:
                continue
            if seat.reports_to not in by_id:
                raise DelegationError(
                    f"seat {seat.seat_id} reports to {seat.reports_to!r}, which is "
                    "not a declared seat"
                )
            manager = by_id[seat.reports_to]
            if manager.rank < seat.rank:
                raise AuthorityViolation(
                    f"seat {seat.seat_id} ({seat.kind.value}) reports to "
                    f"{manager.seat_id} ({manager.kind.value}), which sits at a lower "
                    "layer. An escalation that goes downward is not an escalation."
                )
        # Every chain must reach the CEO seat without repeating a seat.
        for seat in self.seats:
            self._walk(seat.seat_id, by_id)
        if not isinstance(self.org_registry, Mapping):
            raise DelegationError("org_registry must be a mapping")
        if not isinstance(self.permissions, Mapping):
            raise DelegationError("permissions must be a mapping")
        object.__setattr__(self, "_by_id", by_id)

    # -- lookup ------------------------------------------------------------

    @property
    def _index(self) -> dict[str, Seat]:
        return getattr(self, "_by_id")

    def seat(self, seat_id: str) -> Seat:
        try:
            return self._index[seat_id]
        except KeyError:
            raise DelegationError(
                f"{seat_id!r} is not a declared seat. A request naming a seat the "
                "policy does not declare is refused rather than routed to a guess."
            ) from None

    def has_seat(self, seat_id: str) -> bool:
        return seat_id in self._index

    def seat_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._index))

    # -- chains ------------------------------------------------------------

    @staticmethod
    def _walk(seat_id: str, by_id: Mapping[str, Seat]) -> tuple[str, ...]:
        """The chain from `seat_id` up to and including the CEO seat."""
        chain: list[str] = []
        seen: set[str] = set()
        current = seat_id
        while True:
            if current in seen:
                raise AuthorityViolation(
                    "the escalation chain loops at "
                    f"{current!r}: {' -> '.join((*chain, current))}. A circular "
                    "escalation has no CEO at the end of it, which means an action "
                    "could travel forever without ever reaching a decision."
                )
            seen.add(current)
            chain.append(current)
            seat = by_id[current]
            if seat.kind is SeatKind.CEO:
                return tuple(chain)
            if len(chain) > MAX_CHAIN_DEPTH:
                raise AuthorityViolation(
                    f"the chain from {seat_id!r} is deeper than {MAX_CHAIN_DEPTH} "
                    "seats without reaching the CEO"
                )
            current = seat.reports_to

    def chain(self, seat_id: str) -> tuple[str, ...]:
        """Every seat from this one to the CEO, this one first."""
        self.seat(seat_id)
        return self._walk(seat_id, self._index)

    def superiors(self, seat_id: str) -> tuple[str, ...]:
        """The chain above this seat, nearest manager first, CEO last."""
        return self.chain(seat_id)[1:]

    def direct_reports(self, seat_id: str) -> tuple[str, ...]:
        return tuple(
            sorted(
                seat.seat_id
                for seat in self.seats
                if seat.kind is not SeatKind.CEO and seat.reports_to == seat_id
            )
        )

    # -- standing ----------------------------------------------------------

    def _employees(self) -> Mapping[str, Any]:
        employees = self.org_registry.get("employees")
        if not isinstance(employees, Mapping):
            raise DelegationError(
                "org_registry must carry an 'employees' mapping; without it no seat "
                "can be told apart from a vacant one"
            )
        return employees

    def standing(self, seat_id: str) -> SeatStanding:
        """Whether this seat can decide anything, with the reason recorded."""
        seat = self.seat(seat_id)
        if seat.kind is SeatKind.CEO:
            return SeatStanding(
                seat=seat,
                availability=SeatAvailability.EXTERNAL_HUMAN,
                employment_state="",
                authority_cap=0,
                detail=(
                    "the CEO is a human outside the registry; reaching this seat is "
                    "an escalation, never a delegated approval"
                ),
            )
        if seat.is_deterministic_control:
            # Empty by design, and never to be filled. Same authority as any
            # unfilled seat - none - and a different reason, so that a reader
            # of the chart does not go looking for somebody to hire.
            return SeatStanding(
                seat=seat,
                availability=SeatAvailability.VACANT,
                employment_state="",
                authority_cap=0,
                detail=(
                    f"{seat.seat_id} is a deterministic control, not a post: it is "
                    "computed by code that already runs, holds no grant, and is "
                    "never a stop on an escalation path. Nothing waits for it to "
                    "be filled, and filling it would replace a reproducible check "
                    "with an opinion."
                ),
            )
        if seat.is_vacant:
            return SeatStanding(
                seat=seat,
                availability=SeatAvailability.VACANT,
                employment_state="",
                authority_cap=0,
                detail=(
                    f"no employee fills {seat.seat_id}; creating one is "
                    "hire_or_remove_executive_role, which is CEO-reserved"
                ),
            )
        employees = self._employees()
        row = employees.get(seat.employee)
        if not isinstance(row, Mapping):
            raise AuthorityViolation(
                f"seat {seat.seat_id} claims employee {seat.employee!r}, which is not "
                f"in {self.registry_ref}. A seat filled by a name the registry does "
                "not carry is an impersonation, not a vacancy."
            )
        raw_state = str(row.get("state", "")).strip().lower()
        try:
            state = EmploymentState(raw_state)
        except ValueError:
            return SeatStanding(
                seat=seat,
                availability=SeatAvailability.VACANT,
                employment_state=raw_state,
                authority_cap=0,
                detail=(
                    f"{seat.employee} has employment state {raw_state!r}, which is not "
                    "a registry state; an unreadable state holds no authority"
                ),
            )
        cap = state_authority_cap(state, dict(self.permissions))
        if state is EmploymentState.ACTIVE:
            availability = SeatAvailability.ACTIVE
            detail = f"{seat.employee} is active, authority capped at {cap}"
        elif state in (EmploymentState.DORMANT, EmploymentState.ARCHIVED):
            availability = SeatAvailability.DORMANT
            detail = (
                f"{seat.employee} is {state.value}: defined but not running "
                "(constitution rule 18), so it decides nothing"
            )
        else:
            availability = SeatAvailability.RESTRICTED
            detail = (
                f"{seat.employee} is {state.value}, which permissions.yaml caps at "
                f"autonomy {cap}"
            )
        return SeatStanding(
            seat=seat,
            availability=availability,
            employment_state=state.value,
            authority_cap=cap,
            detail=detail,
        )

    def standings(self) -> tuple[SeatStanding, ...]:
        return tuple(self.standing(seat_id) for seat_id in self.seat_ids())

    # -- reconciliation ----------------------------------------------------

    def registry_conflicts(self) -> tuple[str, ...]:
        """Where the declared chart and the registry disagree, both directions.

        Reported, never resolved. A delegation policy that silently re-parented
        the org chart would be changing the organization, which is a corporate
        action and not a configuration detail.
        """
        employees = self._employees()
        problems: list[str] = []
        claimed: dict[str, str] = {}
        for seat in self.seats:
            if not seat.employee:
                continue
            if seat.employee in claimed:
                problems.append(
                    f"{seat.employee} fills both {claimed[seat.employee]} and "
                    f"{seat.seat_id}; one employee holding two seats can approve its "
                    "own escalation"
                )
                continue
            claimed[seat.employee] = seat.seat_id
        for seat in self.seats:
            if seat.kind is SeatKind.CEO or not seat.employee:
                continue
            row = employees.get(seat.employee)
            if not isinstance(row, Mapping):
                problems.append(
                    f"{seat.seat_id} claims {seat.employee}, absent from "
                    f"{self.registry_ref}"
                )
                continue
            registry_manager = str(row.get("manager", "")).strip()
            declared = self.seat(seat.reports_to)
            if declared.kind is SeatKind.CEO:
                expected = CEO_SEAT
            elif declared.employee:
                expected = declared.employee
            else:
                # An inserted management layer the registry does not staff. This
                # is the master-plan/registry discrepancy, and it is reported in
                # its own words rather than as a mismatched employee name.
                problems.append(
                    f"{seat.seat_id} reports to {seat.reports_to}, which no employee "
                    f"fills; in {self.registry_ref} its employee {seat.employee} "
                    f"reports to {registry_manager or 'nobody'}"
                )
                continue
            if registry_manager and registry_manager != expected:
                problems.append(
                    f"{seat.seat_id} reports to {seat.reports_to} "
                    f"({expected}) in the delegation policy and to "
                    f"{registry_manager} in {self.registry_ref}"
                )
            department = str(row.get("department", "")).strip()
            if department and seat.departments and department not in seat.departments:
                problems.append(
                    f"{seat.seat_id} covers {', '.join(seat.departments)} and its "
                    f"employee {seat.employee} sits in department {department!r}"
                )
        unseated = sorted(set(employees) - set(claimed))
        for employee in unseated:
            problems.append(f"{employee} is in the registry and fills no declared seat")
        return tuple(problems)

    def to_dict(self) -> dict[str, Any]:
        return {
            "registry_ref": self.registry_ref,
            "seats": [seat.to_dict() for seat in self.seats],
        }


__all__ = [
    "CEO_SEAT",
    "LAYER_RANK",
    "MAX_CHAIN_DEPTH",
    "Hierarchy",
    "Seat",
    "SeatAvailability",
    "SeatKind",
    "SeatStanding",
]

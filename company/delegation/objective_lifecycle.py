"""Where a CEO objective has got to, and which moves are legal from here.

An objective in bounded routine engineering runs for a long time without the
CEO looking at it, which is the point and also the risk: the only way anyone
can later say what happened is if every move was recorded and only legal moves
were possible. So this is an explicit state machine rather than a status
string, and the transition table is data rather than a pile of conditionals.

    PROPOSED -> AUTHORIZED -> PLANNING -> EXECUTING -> REVIEWING
             -> VALIDATING -> INTERNALLY_INTEGRATED -> COMPLETED

with five terminal exits available from most of the run:

    BLOCKED          something must change before this can continue
    ESCALATED        the CEO has to decide; the objective is parked
    FAILED           the work was attempted and did not succeed
    EXPIRED          the contract ran out
    NO_EXECUTABLE_WORK
                     planning and bounded discovery both found nothing that
                     could be started

## Why NO_EXECUTABLE_WORK is terminal and not an escalation

It is the outcome the last pilot reached, and it is a **result**, not a
question. The company looked at its own register, found nothing it could start,
looked for new work under a bounded envelope, and still found nothing. There is
no decision for the CEO to take mid-run; there is a report to read afterwards.
Treating it as an escalation would interrupt a person to tell them that nothing
happened, which is exactly the interruption management by exception exists to
prevent.

`ESCALATED` is different: it means a decision is genuinely required and the
objective cannot proceed until someone takes it.

## What a transition is not

Reaching `INTERNALLY_INTEGRATED` says the work is on the internal engineering
integration target and nowhere else. It is not a release, and it does not make
anything eligible for canonical or `main`. See `promotion.py`.
"""

from __future__ import annotations

from collections.abc import Sequence
import datetime as dt
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ai_platform.serde import fingerprint as _fingerprint

from .common import assert_day, assert_prose, assert_record_id
from .errors import DelegationError


LIFECYCLE_VERSION = "objective_lifecycle_v1"


class ObjectiveState(str, Enum):
    """Every state a CEO objective can be in. Closed, and ordered by the run."""

    PROPOSED = "proposed"
    AUTHORIZED = "authorized"
    PLANNING = "planning"
    EXECUTING = "executing"
    REVIEWING = "reviewing"
    VALIDATING = "validating"
    INTERNALLY_INTEGRATED = "internally_integrated"
    COMPLETED = "completed"
    # --- terminal and exception states ---
    BLOCKED = "blocked"
    ESCALATED = "escalated"
    FAILED = "failed"
    EXPIRED = "expired"
    NO_EXECUTABLE_WORK = "no_executable_work"


#: States from which nothing further happens without a new CEO decision.
TERMINAL: frozenset[ObjectiveState] = frozenset(
    {
        ObjectiveState.COMPLETED,
        ObjectiveState.BLOCKED,
        ObjectiveState.ESCALATED,
        ObjectiveState.FAILED,
        ObjectiveState.EXPIRED,
        ObjectiveState.NO_EXECUTABLE_WORK,
    }
)

#: Terminal states that end an objective without asking the CEO anything. The
#: CEO reads about these; they do not wait on them.
TERMINAL_WITHOUT_CEO: frozenset[ObjectiveState] = frozenset(
    {
        ObjectiveState.COMPLETED,
        ObjectiveState.NO_EXECUTABLE_WORK,
        ObjectiveState.EXPIRED,
    }
)

#: The exits available from any live state. Listing them once keeps the table
#: below about the happy path, which is the part worth reading.
_EXITS: frozenset[ObjectiveState] = frozenset(
    {
        ObjectiveState.BLOCKED,
        ObjectiveState.ESCALATED,
        ObjectiveState.FAILED,
        ObjectiveState.EXPIRED,
    }
)

_FORWARD: dict[ObjectiveState, frozenset[ObjectiveState]] = {
    ObjectiveState.PROPOSED: frozenset({ObjectiveState.AUTHORIZED}),
    ObjectiveState.AUTHORIZED: frozenset({ObjectiveState.PLANNING}),
    # Planning is the only place NO_EXECUTABLE_WORK can be reached: it is what
    # planning concluded, after discovery, and no later stage can discover it.
    ObjectiveState.PLANNING: frozenset(
        {ObjectiveState.EXECUTING, ObjectiveState.NO_EXECUTABLE_WORK}
    ),
    ObjectiveState.EXECUTING: frozenset({ObjectiveState.REVIEWING}),
    # Review sending work back for a bounded correction returns to EXECUTING.
    # The correction ceiling is enforced by `pilot_correction.py`, not here; a
    # state machine that counted attempts would be a second, worse answer.
    ObjectiveState.REVIEWING: frozenset(
        {ObjectiveState.VALIDATING, ObjectiveState.EXECUTING}
    ),
    ObjectiveState.VALIDATING: frozenset({ObjectiveState.INTERNALLY_INTEGRATED}),
    ObjectiveState.INTERNALLY_INTEGRATED: frozenset({ObjectiveState.COMPLETED}),
}

TRANSITIONS: dict[ObjectiveState, frozenset[ObjectiveState]] = {
    state: (_FORWARD.get(state, frozenset()) | _EXITS)
    for state in ObjectiveState
    if state not in TERMINAL
}
TRANSITIONS.update({state: frozenset() for state in TERMINAL})


def parse_state(value: Any, field_name: str = "state") -> ObjectiveState:
    if isinstance(value, ObjectiveState):
        return value
    try:
        return ObjectiveState(str(value).strip().lower())
    except ValueError as exc:
        raise DelegationError(
            f"{field_name}: {value!r} is not an objective state"
        ) from exc


def may_move(current: Any, nxt: Any) -> bool:
    """Whether this move is legal. Pure, and the same every time."""
    return parse_state(nxt, "next") in TRANSITIONS[parse_state(current, "current")]


@dataclass(frozen=True)
class ObjectiveTransition:
    """One recorded move, with who moved it and on what evidence."""

    objective_id: str
    from_state: ObjectiveState
    to_state: ObjectiveState
    at: dt.date
    actor_seat: str
    reason: str
    evidence_refs: tuple[str, ...] = ()
    version: str = LIFECYCLE_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "objective_id", assert_record_id(self.objective_id, "objective_id")
        )
        object.__setattr__(
            self, "from_state", parse_state(self.from_state, "from_state")
        )
        object.__setattr__(self, "to_state", parse_state(self.to_state, "to_state"))
        object.__setattr__(self, "at", assert_day(self.at, "at"))
        object.__setattr__(
            self, "actor_seat", assert_prose(self.actor_seat, "actor_seat")
        )
        object.__setattr__(self, "reason", assert_prose(self.reason, "reason"))
        if isinstance(self.evidence_refs, (str, bytes)) or not isinstance(
            self.evidence_refs, (list, tuple)
        ):
            raise DelegationError("evidence_refs must be a sequence")
        object.__setattr__(self, "evidence_refs", tuple(str(i) for i in self.evidence_refs))
        if not may_move(self.from_state, self.to_state):
            legal = ", ".join(
                sorted(item.value for item in TRANSITIONS[self.from_state])
            )
            raise DelegationError(
                f"{self.objective_id}: {self.from_state.value} -> "
                f"{self.to_state.value} is not a legal move. From "
                f"{self.from_state.value} the objective may go to: "
                f"{legal or 'nowhere, it is terminal'}."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective_id": self.objective_id,
            "from_state": self.from_state.value,
            "to_state": self.to_state.value,
            "at": self.at.isoformat(),
            "actor_seat": self.actor_seat,
            "reason": self.reason,
            "evidence_refs": list(self.evidence_refs),
            "version": self.version,
        }


@dataclass(frozen=True)
class ObjectiveHistory:
    """Every move one objective made, in order. Append-only by construction."""

    objective_id: str
    transitions: tuple[ObjectiveTransition, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "objective_id", assert_record_id(self.objective_id, "objective_id")
        )
        if isinstance(self.transitions, (str, bytes)) or not isinstance(
            self.transitions, (list, tuple)
        ):
            raise DelegationError("transitions must be a sequence")
        moves = tuple(self.transitions)
        for item in moves:
            if not isinstance(item, ObjectiveTransition):
                raise DelegationError("every entry must be an ObjectiveTransition")
            if item.objective_id != self.objective_id:
                raise DelegationError(
                    f"{item.objective_id} does not belong to {self.objective_id}"
                )
        for earlier, later in zip(moves, moves[1:]):
            if earlier.to_state is not later.from_state:
                raise DelegationError(
                    f"{self.objective_id}: history jumps from "
                    f"{earlier.to_state.value} to {later.from_state.value} with no "
                    "recorded move between them"
                )
        object.__setattr__(self, "transitions", moves)

    @property
    def state(self) -> ObjectiveState:
        if not self.transitions:
            return ObjectiveState.PROPOSED
        return self.transitions[-1].to_state

    def is_terminal(self) -> bool:
        return self.state in TERMINAL

    def needed_the_ceo(self) -> bool:
        """True only when the objective ended in a state a person must answer."""
        return self.is_terminal() and self.state not in TERMINAL_WITHOUT_CEO

    def with_transition(
        self,
        to_state: Any,
        *,
        at: dt.date,
        actor_seat: str,
        reason: str,
        evidence_refs: Sequence[str] = (),
    ) -> "ObjectiveHistory":
        """The next history. Never a mutation of this one.

        Named for the record rather than the job. The obvious verb is refused
        by a source guard in `tests/test_company_delegation.py`, which asserts
        that no module in this package contains any of a short list of tokens
        that would move an engineering job in the world - two git verbs, a
        checkout, and two state-advancing call shapes. The guard is deliberately
        crude, and it is protecting something real, so the verb gives way rather
        than the guard. `with_transition` also matches the `with_status` idiom
        `WorkCandidate` already uses.
        """
        move = ObjectiveTransition(
            objective_id=self.objective_id,
            from_state=self.state,
            to_state=to_state,
            at=at,
            actor_seat=actor_seat,
            reason=reason,
            evidence_refs=tuple(evidence_refs),
        )
        return ObjectiveHistory(
            objective_id=self.objective_id, transitions=(*self.transitions, move)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective_id": self.objective_id,
            "state": self.state.value,
            "terminal": self.is_terminal(),
            "needed_the_ceo": self.needed_the_ceo(),
            "transitions": [item.to_dict() for item in self.transitions],
            "version": LIFECYCLE_VERSION,
        }

    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())


__all__ = [
    "LIFECYCLE_VERSION",
    "TERMINAL",
    "TERMINAL_WITHOUT_CEO",
    "TRANSITIONS",
    "ObjectiveHistory",
    "ObjectiveState",
    "ObjectiveTransition",
    "may_move",
    "parse_state",
]

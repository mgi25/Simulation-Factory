"""The engineering job's state machine, and the two places it refuses to move.

    requested -> planning -> developing -> testing -> reviewing -> gate
              -> ready_for_approval -> closed

with `decision_required`, `blocked` and `failed` reachable from the stages that
can produce them. Every state the engineering brief names is here and none of
them is decoration: `ALLOWED_TRANSITIONS` is the whole authority on what may
follow what, and `advance` raises rather than recording an illegal move.

## The two refusals

**There is no approved state, and no merged state.** `closed` is the terminal
state, it is reached only by recording a `CEODecision`, and closing performs
nothing: no merge, no deploy, no publish. `ready_for_approval` means the work is
ready to be *looked at*. `tests/test_company_engineering_execution.py` asserts
that no state in this enum means approved and that no transition performs an
integration.

**A correction loop is bounded.** `planning -> developing` is legal only while
`corrections_remaining` is positive; the work order's `max_developer_attempts`
sets the bound, `refusal` says why a move would be rejected before anything is
written, and `exhausted` is what a caller checks before asking. When it runs
out the only moves left are `failed` and `decision_required`, which is how an
unbounded retry loop is prevented — by making it unrepresentable rather than by
hoping nobody writes one.

## Why a job is a snapshot and not a mutable object

Each `EngineeringJob` is frozen and carries its whole `transitions` history.
`advance` returns a *new* job, which the store appends beside the old one. So
the state of a job is the last record in an append-only directory, the history
is readable two ways that cannot disagree, and no code path exists that edits a
recorded state. It is the same discipline `ExecutionStore` applies to packets
and receipts, for the same reason.
"""

from __future__ import annotations

from collections.abc import Mapping
import datetime as dt
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Optional

from ai_platform.serde import fingerprint as _fingerprint
from ai_platform.serde import to_jsonable

from .common import assert_day, assert_prose, assert_record_id, ref_tuple, text_tuple
from .errors import EngineeringError
from .work_order import DEFAULT_MAX_DEVELOPER_ATTEMPTS, EngineeringWorkOrder


JOB_VERSION = 1


class JobState(str, Enum):
    """Where one engineering job is. Exactly the states the CEO surface shows."""

    REQUESTED = "requested"
    PLANNING = "planning"
    DEVELOPING = "developing"
    TESTING = "testing"
    REVIEWING = "reviewing"
    GATE = "gate"
    READY_FOR_APPROVAL = "ready_for_approval"
    DECISION_REQUIRED = "decision_required"
    BLOCKED = "blocked"
    FAILED = "failed"
    CLOSED = "closed"


# The stages an ordinary job walks through, in order. Used for rendering and to
# assert that the machine has no shortcut past review or the gate.
MAIN_SEQUENCE: tuple[JobState, ...] = (
    JobState.REQUESTED,
    JobState.PLANNING,
    JobState.DEVELOPING,
    JobState.TESTING,
    JobState.REVIEWING,
    JobState.GATE,
    JobState.READY_FOR_APPROVAL,
)

# A job in one of these is waiting on the CEO, not on the company.
CEO_STATES: frozenset[JobState] = frozenset(
    {JobState.READY_FOR_APPROVAL, JobState.DECISION_REQUIRED, JobState.BLOCKED}
)

TERMINAL_STATES: frozenset[JobState] = frozenset({JobState.CLOSED, JobState.FAILED})

# `developing` is reachable only from `planning`, and only
# `prepare_developer_session` performs that move. Everything that sends work
# back - a review, the gate, a CEO asking for changes - returns the job to
# `planning` instead.
#
# That is not cosmetic. `developing` is the one state that consumes a developer
# attempt, so it has to mean exactly "a packet was issued". When two different
# things could enter it, a review sending work back spent an attempt that
# issued no packet, and the retry bound stopped counting the thing it bounds.
ALLOWED_TRANSITIONS: dict[JobState, frozenset[JobState]] = {
    JobState.REQUESTED: frozenset(
        {JobState.PLANNING, JobState.DECISION_REQUIRED, JobState.FAILED}
    ),
    JobState.PLANNING: frozenset(
        {JobState.DEVELOPING, JobState.DECISION_REQUIRED, JobState.BLOCKED, JobState.FAILED}
    ),
    JobState.DEVELOPING: frozenset(
        {JobState.TESTING, JobState.DECISION_REQUIRED, JobState.BLOCKED, JobState.FAILED}
    ),
    JobState.TESTING: frozenset(
        {
            JobState.REVIEWING,
            JobState.PLANNING,
            JobState.DECISION_REQUIRED,
            JobState.BLOCKED,
            JobState.FAILED,
        }
    ),
    JobState.REVIEWING: frozenset(
        {
            JobState.GATE,
            JobState.PLANNING,
            JobState.DECISION_REQUIRED,
            JobState.BLOCKED,
            JobState.FAILED,
        }
    ),
    JobState.GATE: frozenset(
        {
            JobState.READY_FOR_APPROVAL,
            JobState.PLANNING,
            JobState.BLOCKED,
            JobState.DECISION_REQUIRED,
            JobState.FAILED,
        }
    ),
    # A ready job waits. It may be closed by a CEO decision, sent back for
    # changes, or blocked by something discovered afterwards. It may not
    # advance itself to anything.
    JobState.READY_FOR_APPROVAL: frozenset(
        {JobState.CLOSED, JobState.PLANNING, JobState.BLOCKED, JobState.DECISION_REQUIRED}
    ),
    JobState.DECISION_REQUIRED: frozenset(
        {JobState.PLANNING, JobState.CLOSED, JobState.FAILED}
    ),
    JobState.BLOCKED: frozenset(
        {JobState.PLANNING, JobState.DECISION_REQUIRED, JobState.CLOSED, JobState.FAILED}
    ),
    JobState.FAILED: frozenset(),
    JobState.CLOSED: frozenset(),
}

# The one transition that consumes a developer attempt from the work order's
# ceiling, because it is the one that means a packet went out.
_CONSUMES_ATTEMPT: frozenset[JobState] = frozenset({JobState.DEVELOPING})


@dataclass(frozen=True)
class JobTransition:
    """One recorded move, with the day, the reason and who caused it."""

    from_state: JobState
    to_state: JobState
    on: dt.date
    reason: str
    actor: str = "company-os"
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("from_state", "to_state"):
            if not isinstance(getattr(self, name), JobState):
                raise EngineeringError(f"transition.{name} must be a JobState value")
        object.__setattr__(self, "on", assert_day(self.on, "transition.on"))
        object.__setattr__(self, "reason", assert_prose(self.reason, "transition.reason"))
        object.__setattr__(self, "actor", assert_prose(self.actor, "transition.actor"))
        object.__setattr__(
            self,
            "evidence_refs",
            ref_tuple(self.evidence_refs, "transition.evidence_refs", limit=16),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class StageTiming:
    """How long a job spent in one state, measured from its own transitions.

    A job that revisits a state (e.g. planning -> developing -> planning) gets
    one ``StageTiming`` per visit, in transition order. ``exited_on`` is
    ``None`` for the state the job is currently in, and ``days`` is zero for
    that open interval.
    """

    state: JobState
    entered_on: dt.date
    exited_on: Optional[dt.date]
    days: int

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class EngineeringJob:
    """One engineering job's state, its attempt counters and its whole history."""

    work_order_id: str
    work_order_fingerprint: str
    state: JobState
    opened_on: dt.date
    developer_attempts: int = 0
    reviews_completed: int = 0
    max_developer_attempts: int = DEFAULT_MAX_DEVELOPER_ATTEMPTS
    transitions: tuple[JobTransition, ...] = ()
    pending_decisions: tuple[str, ...] = ()
    version: int = JOB_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "work_order_id", assert_record_id(self.work_order_id, "job.work_order_id")
        )
        if not isinstance(self.work_order_fingerprint, str) or len(
            self.work_order_fingerprint
        ) != 16:
            raise EngineeringError("job.work_order_fingerprint must be a 16-character digest")
        if not isinstance(self.state, JobState):
            raise EngineeringError("job.state must be a JobState value")
        object.__setattr__(self, "opened_on", assert_day(self.opened_on, "job.opened_on"))
        for name in ("developer_attempts", "reviews_completed", "max_developer_attempts"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise EngineeringError(f"job.{name} must be a non-negative integer")
        if self.max_developer_attempts < 1:
            raise EngineeringError("job.max_developer_attempts must be at least 1")
        if self.developer_attempts > self.max_developer_attempts:
            raise EngineeringError(
                f"job {self.work_order_id}: {self.developer_attempts} developer "
                f"attempts exceeds the authorized ceiling of "
                f"{self.max_developer_attempts}. The ceiling is the work order's; a "
                "job does not raise its own."
            )
        if not isinstance(self.transitions, tuple) or any(
            not isinstance(item, JobTransition) for item in self.transitions
        ):
            raise EngineeringError("job.transitions must hold JobTransition values")
        if len(self.transitions) > 64:
            raise EngineeringError(
                f"job {self.work_order_id} has {len(self.transitions)} transitions. A "
                "job that has moved 64 times is a job nobody is deciding."
            )
        expected = self.state
        for index, transition in enumerate(reversed(self.transitions)):
            if index == 0 and transition.to_state is not expected:
                raise EngineeringError(
                    f"job.state {self.state.value!r} does not match its last recorded "
                    f"transition, which ended in {transition.to_state.value!r}"
                )
        object.__setattr__(
            self,
            "pending_decisions",
            text_tuple(self.pending_decisions, "job.pending_decisions", limit=16),
        )
        if self.version != JOB_VERSION:
            raise EngineeringError(f"job.version must be {JOB_VERSION}")

    # --- derived -----------------------------------------------------------

    @property
    def corrections_remaining(self) -> int:
        return max(0, self.max_developer_attempts - self.developer_attempts)

    @property
    def exhausted(self) -> bool:
        return self.corrections_remaining == 0

    @property
    def terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    @property
    def awaits_ceo(self) -> bool:
        return self.state in CEO_STATES

    @property
    def approved(self) -> bool:
        """Always False. There is no state in this machine that means approved.

        Kept as an explicit property because the question gets asked, and the
        honest answer needs to be reachable rather than inferred from an
        absence. A CEO decision is a separate record; see `decision.py`.
        """
        return False

    def stage_timings(self) -> tuple[StageTiming, ...]:
        """Duration of each stage visit, derived from the job's own transitions.

        Returns one ``StageTiming`` per contiguous stay in a state. The
        current (last) state has ``exited_on=None`` and ``days=0`` because it
        has no closing transition yet.
        """
        if not self.transitions:
            return ()
        spans: list[StageTiming] = []
        for index, transition in enumerate(self.transitions):
            entered = transition.on
            # Find the exit: the next transition leaves this state.
            if index + 1 < len(self.transitions):
                exited = self.transitions[index + 1].on
                days = (exited - entered).days
                spans.append(
                    StageTiming(
                        state=transition.to_state,
                        entered_on=entered,
                        exited_on=exited,
                        days=days,
                    )
                )
            else:
                # Current state, still open.
                spans.append(
                    StageTiming(
                        state=transition.to_state,
                        entered_on=entered,
                        exited_on=None,
                        days=0,
                    )
                )
        return tuple(spans)

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    def fingerprint(self) -> str:
        return _fingerprint(self)

    # --- movement ----------------------------------------------------------

    def refusal(self, to_state: JobState) -> str:
        """Why this move would be refused, or an empty string.

        Public and separate from `advance` so a caller can check legality
        *before* doing irreversible work. `prepare_developer_session` uses it
        for exactly that reason: it persists a packet and an authority
        snapshot, and a stage that is going to be refused must write neither.
        """
        if not isinstance(to_state, JobState):
            return "a transition target must be a JobState value"
        allowed = ALLOWED_TRANSITIONS[self.state]
        if to_state not in allowed:
            names = ", ".join(sorted(item.value for item in allowed)) or "nothing"
            return (
                f"job {self.work_order_id}: {self.state.value} -> {to_state.value} is "
                f"not an allowed transition; from {self.state.value} it may move to: "
                f"{names}"
            )
        if to_state in _CONSUMES_ATTEMPT and self.exhausted:
            return (
                f"job {self.work_order_id} has used all "
                f"{self.max_developer_attempts} authorized developer attempt(s). A "
                "further correction needs a new work order, which is a CEO decision."
            )
        return ""

    def can_advance(self, to_state: JobState) -> bool:
        return not self.refusal(to_state)

    def advance(
        self,
        to_state: JobState,
        *,
        on: dt.date,
        reason: str,
        actor: str = "company-os",
        evidence_refs: tuple[str, ...] = (),
    ) -> "EngineeringJob":
        """Return the next job snapshot, or raise if the move is not allowed."""
        refusal = self.refusal(to_state)
        if refusal:
            raise EngineeringError(refusal)
        consumes = to_state in _CONSUMES_ATTEMPT
        transition = JobTransition(
            from_state=self.state,
            to_state=to_state,
            on=assert_day(on, "transition.on"),
            reason=reason,
            actor=actor,
            evidence_refs=evidence_refs,
        )
        return replace(
            self,
            state=to_state,
            developer_attempts=self.developer_attempts + (1 if consumes else 0),
            # Leaving `reviewing` by any door means one review completed.
            reviews_completed=self.reviews_completed
            + (1 if self.state is JobState.REVIEWING else 0),
            transitions=self.transitions + (transition,),
            pending_decisions=(
                self.pending_decisions
                if to_state in (JobState.DECISION_REQUIRED, JobState.BLOCKED)
                else ()
            ),
        )

    def requiring_decision(
        self,
        reasons: tuple[str, ...],
        *,
        on: dt.date,
        actor: str = "company-os",
        evidence_refs: tuple[str, ...] = (),
    ) -> "EngineeringJob":
        """Stop with DECISION REQUIRED, carrying the reasons the CEO must settle."""
        if not reasons:
            raise EngineeringError(
                "a decision-required stop must name at least one reason; an "
                "unexplained stop cannot be decided"
            )
        moved = self.advance(
            JobState.DECISION_REQUIRED,
            on=on,
            reason="; ".join(reasons),
            actor=actor,
            evidence_refs=evidence_refs,
        )
        return replace(moved, pending_decisions=text_tuple(reasons, "reasons", limit=16))

    @classmethod
    def open(
        cls, order: EngineeringWorkOrder, *, on: dt.date | None = None
    ) -> "EngineeringJob":
        """The first snapshot of a job: requested, nothing attempted."""
        day = assert_day(on or order.authorized_on, "job.opened_on")
        return cls(
            work_order_id=order.work_order_id,
            work_order_fingerprint=order.fingerprint(),
            state=JobState.REQUESTED,
            opened_on=day,
            max_developer_attempts=order.max_developer_attempts,
            transitions=(
                JobTransition(
                    from_state=JobState.REQUESTED,
                    to_state=JobState.REQUESTED,
                    on=day,
                    reason=(
                        f"work order {order.work_order_id} authorized by "
                        f"{order.requested_by}"
                    ),
                ),
            ),
        )

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "EngineeringJob":
        if not isinstance(data, Mapping):
            raise EngineeringError("a job must be a mapping")
        unknown = sorted(set(data) - set(cls.__dataclass_fields__))
        if unknown:
            raise EngineeringError("job has unknown field(s): " + ", ".join(unknown))
        raw = data.get("transitions", ())
        if isinstance(raw, (str, bytes)) or not isinstance(raw, (list, tuple)):
            raise EngineeringError("job.transitions must be a list")
        transitions = []
        for index, item in enumerate(raw):
            if not isinstance(item, Mapping):
                raise EngineeringError(f"job.transitions[{index}] must be a mapping")
            extra = sorted(
                set(item)
                - {"from_state", "to_state", "on", "reason", "actor", "evidence_refs"}
            )
            if extra:
                raise EngineeringError(
                    f"job.transitions[{index}] has unknown field(s): " + ", ".join(extra)
                )
            refs = item.get("evidence_refs", ())
            if isinstance(refs, (str, bytes)) or not isinstance(refs, (list, tuple)):
                raise EngineeringError(
                    f"job.transitions[{index}].evidence_refs must be a list"
                )
            transitions.append(
                JobTransition(
                    from_state=_state(item.get("from_state"), "from_state"),
                    to_state=_state(item.get("to_state"), "to_state"),
                    on=assert_day(item.get("on"), "transition.on"),
                    reason=str(item.get("reason", "")),
                    actor=str(item.get("actor", "company-os")),
                    evidence_refs=tuple(str(ref) for ref in refs),
                )
            )
        pending = data.get("pending_decisions", ())
        if isinstance(pending, (str, bytes)) or not isinstance(pending, (list, tuple)):
            raise EngineeringError("job.pending_decisions must be a list")
        return cls(
            work_order_id=str(data.get("work_order_id", "")),
            work_order_fingerprint=str(data.get("work_order_fingerprint", "")),
            state=_state(data.get("state"), "state"),
            opened_on=assert_day(data.get("opened_on"), "job.opened_on"),
            developer_attempts=_int(data.get("developer_attempts", 0), "developer_attempts"),
            reviews_completed=_int(data.get("reviews_completed", 0), "reviews_completed"),
            max_developer_attempts=_int(
                data.get("max_developer_attempts", DEFAULT_MAX_DEVELOPER_ATTEMPTS),
                "max_developer_attempts",
            ),
            transitions=tuple(transitions),
            pending_decisions=tuple(str(item) for item in pending),
            version=_int(data.get("version", JOB_VERSION), "version"),
        )


def _state(value: Any, field_name: str) -> JobState:
    if not isinstance(value, str):
        raise EngineeringError(f"job.{field_name} must be a string")
    try:
        return JobState(value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in JobState)
        raise EngineeringError(f"job.{field_name} must be one of: {allowed}") from exc


def _int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EngineeringError(f"job.{field_name} must be an integer")
    return value


__all__ = [
    "ALLOWED_TRANSITIONS",
    "CEO_STATES",
    "JOB_VERSION",
    "MAIN_SEQUENCE",
    "TERMINAL_STATES",
    "EngineeringJob",
    "JobState",
    "JobTransition",
    "StageTiming",
]

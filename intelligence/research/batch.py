"""One search, its budget, and the conditions it agreed to stop on - written first.

A discovery query can return four results or four hundred, and the cost of the
four hundred is not in holding them. It is in the afternoon of analyst time
each one can ask for. `funnel.py` names the tiers; this module decides how many
candidates are allowed to reach the expensive ones, and it decides it **before**
collection starts rather than after somebody notices the queue is long.

    ResearchBatch    one search: its queries, its rounds, its status, its log
    BatchBudget      the ceilings, as whole numbers a comparison can fail on
    StopCondition    the rule we agreed to stop on, declared in advance
    SaturationRule   N rounds under X new information, both configurable
    DiscoveryRound   one query, one day, the candidate ids it put in front of us

## The batch does not execute anything

Nothing here runs a query, screens a candidate or writes a reference case. This
module is the record; `batch_control.py` holds the four functions that change
one, and each of those records that something *happened* rather than making it
happen. The batch manager is an accountant, not a scheduler - the same line
`funnel.py` draws between describing a tier and running one.

## Stop conditions are declared before collection, or they are excuses

A batch requires at least one `StopCondition` at construction. A stop rule
chosen after the numbers are visible is not a stop rule: it is a description of
where somebody happened to stop, and it cannot fail. "Stop when three
consecutive rounds contribute under 20% new candidates", written on the day the
batch is planned, is a commitment; the same sentence written on the day round
four comes in is a summary.

## A hard limit stops, or a person raises it with their name on it

The ceilings are declared here; enforcing them is `batch_control.py`, which
holds the four state changes and refuses each one against a measurement. The
split is the usual one in this package: this module is what a batch *is*, and
nothing in it changes anything.

## History is append-only and small

`BatchEvent` is a flat tuple on the record: kind, day, person, detail, and the
two statuses when the event was a status change. That is the whole of the event
sourcing, deliberately - the status-change events replay to the current status
and construction refuses a record where they do not, which is the same
guarantee `DiscoveryCandidate.history` and `ResearchSource.history` already
give, in the same shape, for the same reason.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar, Iterable

from ai_platform.serde import as_date, as_opt_date, as_tuple
from intelligence.research.common import (
    assert_nonempty,
    assert_research_id,
    assert_text,
)
from intelligence.research.discovery import assert_line
from intelligence.research.errors import ResearchError


class BatchStatus(Enum):
    """Where a batch is, in the seven words a research lead would use.

    `STOPPED` is not a failure and not the end: it is the state a batch reaches
    when a declared condition fired or a ceiling was hit, and it exists so that
    continuing has to be somebody's decision rather than the default.
    """

    PLANNED = "planned"
    COLLECTING = "collecting"
    SCREENING = "screening"
    ANALYSIS_READY = "analysis_ready"
    COMPLETE = "complete"
    STOPPED = "stopped"
    ARCHIVED = "archived"


BATCH_TRANSITIONS: dict[BatchStatus, frozenset[BatchStatus]] = {
    BatchStatus.PLANNED: frozenset(
        {BatchStatus.COLLECTING, BatchStatus.STOPPED, BatchStatus.ARCHIVED}
    ),
    BatchStatus.COLLECTING: frozenset(
        {BatchStatus.SCREENING, BatchStatus.STOPPED, BatchStatus.ARCHIVED}
    ),
    BatchStatus.SCREENING: frozenset(
        {BatchStatus.ANALYSIS_READY, BatchStatus.STOPPED, BatchStatus.ARCHIVED}
    ),
    BatchStatus.ANALYSIS_READY: frozenset(
        {BatchStatus.COMPLETE, BatchStatus.STOPPED, BatchStatus.ARCHIVED}
    ),
    BatchStatus.COMPLETE: frozenset({BatchStatus.ARCHIVED}),
    BatchStatus.STOPPED: frozenset(
        {BatchStatus.COLLECTING, BatchStatus.SCREENING, BatchStatus.ARCHIVED}
    ),
    BatchStatus.ARCHIVED: frozenset(),
}
"""`STOPPED` has two ways back, and `advance_batch` gates both on an escalation
recorded *after* the stop. Without that gate a stop is a suggestion."""

TERMINAL_BATCH_STATUSES: frozenset[BatchStatus] = frozenset(
    status for status, onward in BATCH_TRANSITIONS.items() if not onward
)

FORWARD_STATUSES: frozenset[BatchStatus] = frozenset(
    {
        BatchStatus.COLLECTING,
        BatchStatus.SCREENING,
        BatchStatus.ANALYSIS_READY,
        BatchStatus.COMPLETE,
    }
)
"""Statuses that mean work continues. A breached hard limit refuses all four."""


class BatchEventKind(Enum):
    CREATED = "created"
    ROUND_RECORDED = "round_recorded"
    STATUS_CHANGED = "status_changed"
    STOP_TRIGGERED = "stop_triggered"
    ESCALATED = "escalated"
    NOTE = "note"


@dataclass(frozen=True)
class BatchEvent:
    """One line of the batch's history. Appended, never rewritten.

    Enough to reconstruct what we knew, when, and why we stopped, and no more
    than that: there is no event bus, no projection and no replay engine here.
    A tuple of these on the record *is* the audit trail.
    """

    kind: BatchEventKind
    on: dt.date
    by: str
    detail: str
    from_status: BatchStatus | None = None
    to_status: BatchStatus | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, BatchEventKind):
            raise ResearchError(
                f"batch event kind must be a BatchEventKind, got {self.kind!r}"
            )
        if not isinstance(self.on, dt.date):
            raise ResearchError("a batch event must record the day it happened")
        assert_text(self.by, "batch event by (who did this)")
        assert_text(self.detail, "batch event detail (what happened, in one sentence)")
        if self.kind is BatchEventKind.STATUS_CHANGED:
            if self.from_status is None or self.to_status is None:
                raise ResearchError(
                    "a status_changed event must record both statuses, or the history "
                    "cannot be replayed into the status the record claims"
                )
            if self.from_status is self.to_status:
                raise ResearchError(
                    f"status change from {self.from_status.value!r} to itself is not a change"
                )
        elif self.from_status is not None or self.to_status is not None:
            raise ResearchError(
                f"a {self.kind.value!r} event carries no status change; leave both unset"
            )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BatchEvent:
        return cls(
            kind=BatchEventKind(data["kind"]),
            on=as_date(data["on"], "on"),
            by=data["by"],
            detail=data["detail"],
            from_status=(
                None
                if data.get("from_status") is None
                else BatchStatus(data["from_status"])
            ),
            to_status=(
                None if data.get("to_status") is None else BatchStatus(data["to_status"])
            ),
        )


@dataclass(frozen=True)
class DiscoveryRound:
    """One query, run on one day, and the candidate ids it put in front of us.

    The unit of discovery cost. A round is what saturation is measured over,
    because "are we still learning?" is a question about consecutive attempts
    and not about the total pile - a batch with 300 candidates and a flat last
    five rounds and a batch with 300 candidates still climbing are the same pile
    and different decisions.

    `observed` holds every candidate the round put in front of a researcher,
    including the ones we already held. That is the point: a round whose twenty
    results are twenty candidates we already have cost the same as one that
    found twenty new ones, and only the observation log can tell them apart.
    """

    query_id: str
    ran_on: dt.date
    observed: tuple[str, ...] = ()
    note: str = ""

    def __post_init__(self) -> None:
        assert_research_id(self.query_id, "discovery query")
        if not isinstance(self.ran_on, dt.date):
            raise ResearchError("a discovery round must record the day it ran")
        observed = as_tuple(self.observed)
        for value in observed:
            assert_research_id(value, "observed candidate")
        if len(set(observed)) != len(observed):
            repeated = sorted({v for v in observed if observed.count(v) > 1})
            raise ResearchError(
                f"round {self.query_id!r} on {self.ran_on} observes "
                f"{', '.join(repeated)} twice. One round seeing one video once is one "
                "observation; a repeat inside a single round is a capture error, and "
                "counting it would inflate both the duplicate rate and the measured "
                "cost per unique candidate."
            )
        object.__setattr__(self, "observed", observed)

    @property
    def observations(self) -> int:
        return len(self.observed)

    @property
    def is_empty(self) -> bool:
        """A round that returned nothing. It still cost a query, and it is the
        one round a candidate's own provenance can never show."""
        return not self.observed

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscoveryRound:
        return cls(
            query_id=data["query_id"],
            ran_on=as_date(data["ran_on"], "ran_on"),
            observed=as_tuple(data.get("observed")),
            note=data.get("note", ""),
        )


@dataclass(frozen=True)
class CandidateTarget:
    """How many candidates this batch is trying to end up with.

    A range rather than a number, because the honest answer to "how many marble
    videos should we look at" is an interval. It is a plan, not a limit - the
    limit is `BatchBudget` - and the two are checked against each other so a
    batch cannot aim past its own ceiling.
    """

    minimum: int
    maximum: int

    def __post_init__(self) -> None:
        for name in ("minimum", "maximum"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ResearchError(
                    f"candidate target {name} must be a whole number of at least 1, "
                    f"got {value!r}"
                )
        if self.minimum > self.maximum:
            raise ResearchError(
                f"candidate target {self.minimum}-{self.maximum} is empty; the minimum "
                "cannot exceed the maximum"
            )

    def contains(self, count: int) -> bool:
        return self.minimum <= count <= self.maximum

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CandidateTarget:
        return cls(minimum=data["minimum"], maximum=data["maximum"])


COLLECTION_LIMITS: tuple[str, ...] = (
    "max_queries",
    "max_candidate_observations",
    "max_unique_candidates",
)
ANALYSIS_LIMITS: tuple[str, ...] = (
    "max_promoted_candidates",
    "max_reference_cases",
)
OPTIONAL_LIMITS: tuple[str, ...] = (
    "max_human_review_minutes",
    "max_reasoning_units",
    "max_tool_calls",
)
HARD_LIMITS: tuple[str, ...] = COLLECTION_LIMITS + ANALYSIS_LIMITS + OPTIONAL_LIMITS


@dataclass(frozen=True)
class BatchBudget:
    """What this search may spend, as whole numbers, every one of them optional.

    Three groups, and the split is the design:

    - **collection limits** are consumed by rounds and checked on every one.
      They are things we count ourselves, every time, with no provider involved:
      how many queries ran, how many results they showed us, how many distinct
      videos came out.
    - **analysis limits** are consumed by promotion and reference analysis - the
      tiers that cost an afternoon. These are the numbers this whole layer
      exists to hold down.
    - **optional limits** are review minutes, reasoning units and tool calls.
      Optional because a batch run by a person with a browser has no reasoning
      units and is not thereby unbudgeted. `ai_platform/usage.py` makes the same
      call for the same reason: a system whose only budget needs provider
      telemetry stops budgeting the day the provider changes.

    A budget with no limit at all is refused. "As many as it takes" is the thing
    this record exists to stop somebody writing down.
    """

    max_queries: int | None = None
    max_candidate_observations: int | None = None
    max_unique_candidates: int | None = None
    max_promoted_candidates: int | None = None
    max_reference_cases: int | None = None
    max_human_review_minutes: int | None = None
    max_reasoning_units: int | None = None
    max_tool_calls: int | None = None
    deadline: dt.date | None = None
    note: str = ""

    def __post_init__(self) -> None:
        for name in HARD_LIMITS:
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ResearchError(
                    f"budget {name} must be a whole number of at least 1, or None when "
                    f"this batch sets no such limit; got {value!r}. A limit of 0 is not "
                    "a budget, it is a batch that may not start."
                )
        if self.deadline is not None and not isinstance(self.deadline, dt.date):
            raise ResearchError("budget deadline must be a date, or None")
        if not self.limits and self.deadline is None:
            raise ResearchError(
                "a budget with no limit and no deadline is not a budget. Set at least "
                "one ceiling - max_unique_candidates and max_promoted_candidates are "
                "the two that actually bound research cost."
            )
        if (
            self.max_unique_candidates is not None
            and self.max_candidate_observations is not None
            and self.max_unique_candidates > self.max_candidate_observations
        ):
            raise ResearchError(
                f"budget allows {self.max_unique_candidates} unique candidates out of "
                f"{self.max_candidate_observations} observations. Every unique candidate "
                "is an observation, so the unique ceiling could never be the binding one."
            )
        if (
            self.max_promoted_candidates is not None
            and self.max_unique_candidates is not None
            and self.max_promoted_candidates > self.max_unique_candidates
        ):
            raise ResearchError(
                f"budget promotes up to {self.max_promoted_candidates} candidates out of "
                f"at most {self.max_unique_candidates}. Only a candidate can be promoted."
            )

    @property
    def limits(self) -> tuple[tuple[str, int], ...]:
        """The ceilings that were actually set, in declaration order."""
        return tuple(
            (name, getattr(self, name))
            for name in HARD_LIMITS
            if getattr(self, name) is not None
        )

    def limit(self, name: str) -> int | None:
        if name not in HARD_LIMITS:
            raise ResearchError(
                f"unknown budget limit {name!r}; this budget bounds "
                f"{', '.join(HARD_LIMITS)}"
            )
        return getattr(self, name)

    def is_expired(self, on: dt.date) -> bool:
        return self.deadline is not None and on > self.deadline

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BatchBudget:
        return cls(
            max_queries=data.get("max_queries"),
            max_candidate_observations=data.get("max_candidate_observations"),
            max_unique_candidates=data.get("max_unique_candidates"),
            max_promoted_candidates=data.get("max_promoted_candidates"),
            max_reference_cases=data.get("max_reference_cases"),
            max_human_review_minutes=data.get("max_human_review_minutes"),
            max_reasoning_units=data.get("max_reasoning_units"),
            max_tool_calls=data.get("max_tool_calls"),
            deadline=as_opt_date(data.get("deadline"), "deadline"),
            note=data.get("note", ""),
        )


class SaturationMetric(Enum):
    """Which kind of new information a saturation rule watches for.

    Three, because they saturate at different times and the difference is
    informative. New candidates dry up first; new creators next; new mechanics
    last, and a batch still finding new mechanics is worth running even when
    every video is from a channel we already know.
    """

    NEW_UNIQUE_CANDIDATES = "new_unique_candidates"
    NEW_CREATORS = "new_creators"
    NEW_TAGS = "new_tags"


@dataclass(frozen=True)
class SaturationRule:
    """Stop when the last N rounds each contributed under X new information.

    Both numbers are configuration, both are required, and neither has a default
    that would let somebody skip thinking about it. There is no "saturation
    score": one number would hide which of the three metrics flattened and how
    many rounds it took, and those are the two things a research lead acts on.

    `rounds` is also the honesty floor. Fewer than N rounds is not "not
    saturated" - it is `INSUFFICIENT_EVIDENCE`, a third answer, because a batch
    that has run two rounds has no evidence about what a third would find.
    """

    rounds: int
    new_rate_below: float
    metric: SaturationMetric = SaturationMetric.NEW_UNIQUE_CANDIDATES
    note: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.rounds, bool) or not isinstance(self.rounds, int):
            raise ResearchError(
                f"saturation rounds must be a whole number, got {self.rounds!r}"
            )
        if self.rounds < 2:
            raise ResearchError(
                f"saturation over {self.rounds} round(s) is not a trend. Two consecutive "
                "rounds is the fewest that can show a direction."
            )
        if isinstance(self.new_rate_below, bool) or not isinstance(
            self.new_rate_below, (int, float)
        ):
            raise ResearchError(
                f"saturation new_rate_below must be a number, got {self.new_rate_below!r}"
            )
        object.__setattr__(self, "new_rate_below", float(self.new_rate_below))
        if not 0.0 < self.new_rate_below <= 1.0:
            raise ResearchError(
                f"saturation new_rate_below {self.new_rate_below} must be a fraction "
                "above 0 and at most 1. A threshold of 0 can never fire, and one above "
                "1 fires on the first round."
            )
        if not isinstance(self.metric, SaturationMetric):
            raise ResearchError("saturation metric must be a SaturationMetric")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SaturationRule:
        return cls(
            rounds=data["rounds"],
            new_rate_below=data["new_rate_below"],
            metric=SaturationMetric(data.get("metric", "new_unique_candidates")),
            note=data.get("note", ""),
        )


class StopReason(Enum):
    MAX_UNIQUE_CANDIDATES = "max_unique_candidates"
    MAX_OBSERVATIONS = "max_observations"
    MAX_QUERIES = "max_queries"
    BUDGET_EXHAUSTED = "budget_exhausted"
    SATURATION = "saturation"
    DEADLINE = "deadline"


class StopAction(Enum):
    """What reaching a condition means. Neither value continues the batch.

    `STOP` moves the batch to `STOPPED`. `REVIEW` means a person must look
    before it goes on - the weaker of the two, and still not "carry on", because
    a condition that fires and changes nothing is a comment.
    """

    STOP = "stop"
    REVIEW = "review"


COUNT_REASONS: frozenset[StopReason] = frozenset(
    {
        StopReason.MAX_UNIQUE_CANDIDATES,
        StopReason.MAX_OBSERVATIONS,
        StopReason.MAX_QUERIES,
    }
)

PROGRESS_FIELD: dict[StopReason, str] = {
    StopReason.MAX_UNIQUE_CANDIDATES: "unique_candidates",
    StopReason.MAX_OBSERVATIONS: "observations",
    StopReason.MAX_QUERIES: "queries",
}
"""Which `BatchProgress` number each counting condition is read against. One
mapping, so a condition and its measurement cannot drift apart."""


@dataclass(frozen=True)
class StopCondition:
    """One rule this batch agreed to stop on, written before collection began.

    Every reason carries exactly the parameter it needs and refuses the others,
    so a condition cannot be half-specified: a count condition without a
    threshold would never fire, a saturation condition without a rule would have
    nothing to test, and a deadline condition without a date is a wish.
    """

    reason: StopReason
    action: StopAction = StopAction.STOP
    threshold: int | None = None
    deadline: dt.date | None = None
    saturation: SaturationRule | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.reason, StopReason):
            raise ResearchError("stop condition reason must be a StopReason")
        if not isinstance(self.action, StopAction):
            raise ResearchError("stop condition action must be a StopAction")
        if self.note:
            assert_line(self.note, "stop condition note")

        if self.reason in COUNT_REASONS:
            if self.threshold is None:
                raise ResearchError(
                    f"stop condition {self.reason.value!r} needs a threshold; without "
                    "one there is no number for the batch to reach"
                )
            if (
                isinstance(self.threshold, bool)
                or not isinstance(self.threshold, int)
                or self.threshold < 1
            ):
                raise ResearchError(
                    f"stop condition {self.reason.value!r}: threshold must be a whole "
                    f"number of at least 1, got {self.threshold!r}"
                )
        elif self.threshold is not None:
            raise ResearchError(
                f"stop condition {self.reason.value!r} counts nothing, so a threshold of "
                f"{self.threshold!r} would be ignored"
            )

        if self.reason is StopReason.DEADLINE:
            if not isinstance(self.deadline, dt.date):
                raise ResearchError("a deadline stop condition must name the date")
        elif self.deadline is not None:
            raise ResearchError(
                f"stop condition {self.reason.value!r} is not time-based; put the date "
                "on a deadline condition, or on the budget"
            )

        if self.reason is StopReason.SATURATION:
            if not isinstance(self.saturation, SaturationRule):
                raise ResearchError(
                    "a saturation stop condition must carry a SaturationRule - the N "
                    "rounds and the X rate are the condition, and they are configuration"
                )
        elif self.saturation is not None:
            raise ResearchError(
                f"stop condition {self.reason.value!r} carries a saturation rule it "
                "would never evaluate"
            )

    @property
    def key(self) -> str:
        """Two conditions with the same key are one condition written twice."""
        parts = [self.reason.value]
        if self.threshold is not None:
            parts.append(str(self.threshold))
        if self.deadline is not None:
            parts.append(self.deadline.isoformat())
        if self.saturation is not None:
            parts.append(f"{self.saturation.metric.value}:{self.saturation.rounds}")
        return "|".join(parts)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StopCondition:
        return cls(
            reason=StopReason(data["reason"]),
            action=StopAction(data.get("action", "stop")),
            threshold=data.get("threshold"),
            deadline=as_opt_date(data.get("deadline"), "deadline"),
            saturation=(
                None
                if data.get("saturation") is None
                else SaturationRule.from_dict(data["saturation"])
            ),
            note=data.get("note", ""),
        )


@dataclass(frozen=True)
class ResearchBatch:
    """One search: what it is for, what it may spend, and everything it did.

    The candidate ids are a *property*, not a field. A stored list beside the
    round log is a second answer to "what did this batch find", and the two
    diverge the first time somebody edits one of them. Derived from the rounds,
    in first-seen order, there is one answer and it carries the order discovery
    actually happened in - which is the order saturation is read off.
    """

    kind: ClassVar[str] = "research_batch"

    id: str
    objective: str
    created: dt.date
    owner: str
    query_ids: tuple[str, ...]
    budget: BatchBudget
    stop_conditions: tuple[StopCondition, ...]
    target: CandidateTarget | None = None
    rounds: tuple[DiscoveryRound, ...] = ()
    status: BatchStatus = BatchStatus.PLANNED
    history: tuple[BatchEvent, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        assert_research_id(self.id, "research batch")
        assert_text(self.objective, "batch objective (what this search is for)")
        assert_text(self.owner, "batch owner (the researcher accountable for it)")
        if not isinstance(self.created, dt.date):
            raise ResearchError("a research batch must record the day it was planned")

        query_ids = as_tuple(self.query_ids)
        for value in query_ids:
            assert_research_id(value, "discovery query")
        if len(set(query_ids)) != len(query_ids):
            raise ResearchError(f"batch {self.id!r}: the same query is declared twice")
        assert_nonempty(
            query_ids,
            "query_ids",
            "a batch with no declared query is a batch whose results belong to nothing",
        )
        object.__setattr__(self, "query_ids", query_ids)

        if not isinstance(self.budget, BatchBudget):
            raise ResearchError(
                f"batch {self.id!r}: budget must be a BatchBudget. An unbudgeted search "
                "is the thing this record exists to make impossible."
            )
        conditions = tuple(self.stop_conditions)
        for condition in conditions:
            if not isinstance(condition, StopCondition):
                raise ResearchError(f"batch {self.id!r}: not a StopCondition")
        assert_nonempty(
            conditions,
            "stop_conditions",
            "declare when to stop before collecting, or the stopping point is wherever "
            "somebody happened to get tired",
        )
        keys = [c.key for c in conditions]
        if len(set(keys)) != len(keys):
            raise ResearchError(
                f"batch {self.id!r}: the same stop condition is declared twice; one of "
                "the two would fire and the other would be noise"
            )
        object.__setattr__(self, "stop_conditions", conditions)

        if self.target is not None:
            if not isinstance(self.target, CandidateTarget):
                raise ResearchError(
                    f"batch {self.id!r}: target must be a CandidateTarget"
                )
            ceiling = self.budget.max_unique_candidates
            if ceiling is not None and self.target.maximum > ceiling:
                raise ResearchError(
                    f"batch {self.id!r} targets up to {self.target.maximum} candidates "
                    f"but its budget stops at {ceiling}. The plan cannot exceed the "
                    "ceiling - raise the budget, or aim at what it allows."
                )

        rounds = tuple(self.rounds)
        for entry in rounds:
            if not isinstance(entry, DiscoveryRound):
                raise ResearchError(f"batch {self.id!r}: not a DiscoveryRound")
            if entry.query_id not in query_ids:
                raise ResearchError(
                    f"batch {self.id!r}: a round names query {entry.query_id!r}, which "
                    "the batch does not declare. A candidate discovered by an undeclared "
                    "query belongs to no batch, and its cost is charged to nobody."
                )
        for earlier, later in zip(rounds, rounds[1:]):
            if later.ran_on < earlier.ran_on:
                raise ResearchError(
                    f"batch {self.id!r}: a round on {later.ran_on} is recorded after one "
                    f"on {earlier.ran_on}. Rounds are the order collection happened in, "
                    "and saturation is read off that order."
                )
        object.__setattr__(self, "rounds", rounds)

        history = tuple(self.history)
        for event in history:
            if not isinstance(event, BatchEvent):
                raise ResearchError(f"batch {self.id!r}: not a BatchEvent")
        for earlier, later in zip(history, history[1:]):
            if later.on < earlier.on:
                raise ResearchError(
                    f"batch {self.id!r}: an event dated {later.on} follows one dated "
                    f"{earlier.on}. History is append-only, and in order."
                )
        object.__setattr__(self, "history", history)

        expected = BatchStatus.PLANNED
        for event in history:
            if event.kind is not BatchEventKind.STATUS_CHANGED:
                continue
            if event.from_status is not expected:
                raise ResearchError(
                    f"batch {self.id!r}: history moves from {expected.value!r} to an "
                    f"event that starts at {event.from_status.value!r}"
                )
            expected = event.to_status
        if expected is not self.status:
            raise ResearchError(
                f"batch {self.id!r}: history replays to {expected.value!r} but the record "
                f"says {self.status.value!r}. Use advance_batch, so every status change "
                "carries the person and the reason."
            )

    # -- derived views ----------------------------------------------------

    @property
    def candidate_ids(self) -> tuple[str, ...]:
        """Every distinct candidate this batch observed, in first-seen order."""
        out: list[str] = []
        seen: set[str] = set()
        for entry in self.rounds:
            for candidate_id in entry.observed:
                if candidate_id not in seen:
                    seen.add(candidate_id)
                    out.append(candidate_id)
        return tuple(out)

    @property
    def observations(self) -> int:
        """Every time a round put a candidate in front of us, duplicates counted."""
        return sum(entry.observations for entry in self.rounds)

    @property
    def ran_query_ids(self) -> tuple[str, ...]:
        """Declared queries that actually ran a round. A plan is not a spend."""
        out: list[str] = []
        for entry in self.rounds:
            if entry.query_id not in out:
                out.append(entry.query_id)
        return tuple(out)

    @property
    def unrun_query_ids(self) -> tuple[str, ...]:
        ran = set(self.ran_query_ids)
        return tuple(q for q in self.query_ids if q not in ran)

    @property
    def empty_rounds(self) -> tuple[int, ...]:
        """Indices of rounds that returned nothing - a real cost, and the one
        kind of round a candidate's own provenance can never reveal."""
        return tuple(i for i, entry in enumerate(self.rounds) if entry.is_empty)

    @property
    def is_open(self) -> bool:
        return self.status not in (
            BatchStatus.COMPLETE,
            BatchStatus.STOPPED,
            BatchStatus.ARCHIVED,
        )

    @property
    def saturation_rules(self) -> tuple[SaturationRule, ...]:
        return tuple(c.saturation for c in self.stop_conditions if c.saturation is not None)

    @property
    def escalated_since_stop(self) -> bool:
        """Has somebody authorised continuing, since the batch last stopped?

        Read off the history: yes only when an `ESCALATED` event appears after
        the most recent change *into* `STOPPED`. A batch escalated in March and
        stopped again in April has not been escalated since.
        """
        stopped_at = -1
        escalated_at = -1
        for index, event in enumerate(self.history):
            if (
                event.kind is BatchEventKind.STATUS_CHANGED
                and event.to_status is BatchStatus.STOPPED
            ):
                stopped_at = index
            elif event.kind is BatchEventKind.ESCALATED:
                escalated_at = index
        return escalated_at > stopped_at

    def rounds_for(self, query_id: str) -> tuple[DiscoveryRound, ...]:
        return tuple(entry for entry in self.rounds if entry.query_id == query_id)

    def events_of(self, kind: BatchEventKind) -> tuple[BatchEvent, ...]:
        return tuple(event for event in self.history if event.kind is kind)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResearchBatch:
        return cls(
            id=data["id"],
            objective=data["objective"],
            created=as_date(data["created"], "created"),
            owner=data["owner"],
            query_ids=as_tuple(data.get("query_ids")),
            budget=BatchBudget.from_dict(data["budget"]),
            stop_conditions=tuple(
                StopCondition.from_dict(c) for c in data.get("stop_conditions", ())
            ),
            target=(
                None
                if data.get("target") is None
                else CandidateTarget.from_dict(data["target"])
            ),
            rounds=tuple(DiscoveryRound.from_dict(r) for r in data.get("rounds", ())),
            status=BatchStatus(data.get("status", "planned")),
            history=tuple(BatchEvent.from_dict(h) for h in data.get("history", ())),
            notes=data.get("notes", ""),
        )


def open_batch(
    *,
    id: str,
    objective: str,
    created: dt.date,
    owner: str,
    query_ids: Iterable[str],
    budget: BatchBudget,
    stop_conditions: Iterable[StopCondition],
    target: CandidateTarget | None = None,
    notes: str = "",
) -> ResearchBatch:
    """Plan a batch, with the `CREATED` event already in its history.

    A convenience, and a small guarantee: a batch built this way always has a
    first event, so "when did this search start, and who started it" is answered
    from the history rather than from the `created` field alone.
    """
    return ResearchBatch(
        id=id,
        objective=objective,
        created=created,
        owner=owner,
        query_ids=tuple(query_ids),
        budget=budget,
        stop_conditions=tuple(stop_conditions),
        target=target,
        rounds=(),
        status=BatchStatus.PLANNED,
        history=(
            BatchEvent(
                kind=BatchEventKind.CREATED,
                on=created,
                by=owner,
                detail=objective,
            ),
        ),
        notes=notes,
    )


def can_advance(current: BatchStatus, target: BatchStatus) -> bool:
    return target in BATCH_TRANSITIONS[current]


def assert_batch_transition(current: BatchStatus, target: BatchStatus) -> None:
    if can_advance(current, target):
        return
    allowed = sorted(s.value for s in BATCH_TRANSITIONS[current])
    if not allowed:
        raise ResearchError(f"{current.value!r} is terminal; a batch leaves it nowhere")
    raise ResearchError(
        f"cannot move a batch from {current.value!r} to {target.value!r}; "
        f"allowed from here: {', '.join(allowed)}"
    )

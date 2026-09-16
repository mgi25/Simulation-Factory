"""Consumption, stop evaluation, and the four places a measurement gates a change.

`batch.py` is what a batch is. This is what a batch does, and every function
here is either a measurement of what has been spent or a state change that
refuses itself against one.

    budget_lines            each ceiling, what went against it, whether that is over
    evaluate_stop_conditions  the declared conditions, checked, never acted on
    record_round            one round, appended, or refused whole
    advance_batch           one signed status change, gated on evidence
    stop_batch              the condition that fired, then the decision
    escalate_batch          authorising more, at the cost of a name

## Two refusals, deliberately not the same rule

**A fired stop condition blocks collecting, and only collecting.** Reaching
`max_unique_candidates` is the ceiling *working*: the right next move is to
screen what the batch found. So a fired condition blocks `record_round` and the
way back into `COLLECTING`, and leaves every other forward move alone.

**An exceeded ceiling blocks everything forward.** Consumption past a limit is
spend nobody authorised, and continuing to spend it anywhere is the thing
section 2 of the brief asks this layer not to do silently. `record_round`
cannot produce that state - it refuses the round first - so in practice it
arises from the analysis-side counts, which is exactly where the check earns its
place.

Either is cleared by `escalate_batch`, which requires an authoriser, a reason,
and - when it supplies a budget at all - a budget that actually allows more.
The authorisation lands in the append-only history and stays there.

## A round is refused whole, never trimmed

`record_round` rejects a round that would cross a collection ceiling rather than
taking the part that fits. Half an observation log is a research record that has
quietly lost evidence, and every rate computed from it - the duplicate rate, the
unique contribution per query, the saturation curve - would be wrong in a
direction nobody could see.

## Nothing here schedules anything

`evaluate_stop_conditions` reports; `stop_batch` is what acts on it, and it
takes a person's name and a reason. There is no loop anywhere in this module
that moves a batch on because a number said so - the gap between a signal and a
decision is where a person decides whether the next tier is worth paying for,
which is the line `funnel.py` draws for the same reason.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from intelligence.research.batch import (
    COUNT_REASONS,
    FORWARD_STATUSES,
    HARD_LIMITS,
    PROGRESS_FIELD,
    BatchBudget,
    BatchEvent,
    BatchEventKind,
    BatchStatus,
    DiscoveryRound,
    ResearchBatch,
    SaturationRule,
    StopAction,
    StopCondition,
    StopReason,
    assert_batch_transition,
)
from intelligence.research.common import assert_text
from intelligence.research.errors import ResearchError


# --------------------------------------------------------------------------
# What has been consumed, and what that means
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class BatchProgress:
    """Everything a budget or a stop condition is read against, in one object.

    The collection half is derivable from the batch alone and is always present.
    The screening and analysis half comes from the candidate records, and the
    three cost fields come from the resource ledger; both are `None` or zero
    when nobody supplied them, and `batch_metrics.batch_progress` is the one
    place that fills them in.
    """

    queries: int = 0
    rounds: int = 0
    observations: int = 0
    unique_candidates: int = 0
    screened: int = 0
    screened_in: int = 0
    screened_out: int = 0
    unscreened: int = 0
    archived: int = 0
    promoted_sources: int = 0
    reference_cases: int = 0
    opportunities: int = 0
    human_review_minutes: int | None = None
    reasoning_units: int | None = None
    tool_calls: int | None = None


LIMIT_FIELD: dict[str, str] = {
    "max_queries": "queries",
    "max_candidate_observations": "observations",
    "max_unique_candidates": "unique_candidates",
    "max_promoted_candidates": "promoted_sources",
    "max_reference_cases": "reference_cases",
    "max_human_review_minutes": "human_review_minutes",
    "max_reasoning_units": "reasoning_units",
    "max_tool_calls": "tool_calls",
}
"""Which progress number each ceiling is compared against. One mapping, so a
budget and its measurement cannot be wired up two different ways."""


@dataclass(frozen=True)
class BudgetLine:
    """One ceiling, what has been spent against it, and whether that is over.

    `reached` and `exceeded` are different facts with different consequences.
    Reaching `max_unique_candidates` is the batch working: collection stops and
    screening starts. *Exceeding* any ceiling is spend nobody authorised, and
    `advance_batch` refuses to carry the batch anywhere until somebody raises
    the limit with their name on it.
    """

    limit_name: str
    limit: int
    consumed: int | None = None
    remaining: int | None = None
    fraction: float | None = None
    reached: bool = False
    exceeded: bool = False
    unavailable: str = ""


def budget_lines(budget: BatchBudget, progress: BatchProgress) -> tuple[BudgetLine, ...]:
    """One line per ceiling the budget actually set. Pure.

    A ceiling whose consumption was never measured - review minutes on a batch
    where nobody kept a timesheet - reports `consumed=None` and says why, rather
    than reporting zero. Zero spend and unmeasured spend look identical in a
    table and mean opposite things.
    """
    out: list[BudgetLine] = []
    for name, limit in budget.limits:
        consumed = getattr(progress, LIMIT_FIELD[name])
        if consumed is None:
            out.append(
                BudgetLine(
                    limit_name=name,
                    limit=limit,
                    unavailable=(
                        f"{LIMIT_FIELD[name]} was not measured for this batch, so "
                        "consumption against this ceiling is unknown"
                    ),
                )
            )
            continue
        out.append(
            BudgetLine(
                limit_name=name,
                limit=limit,
                consumed=consumed,
                remaining=limit - consumed,
                fraction=round(consumed / limit, 6),
                reached=consumed >= limit,
                exceeded=consumed > limit,
            )
        )
    return tuple(out)


def exceeded_limits(budget: BatchBudget, progress: BatchProgress) -> tuple[str, ...]:
    """The ceilings that have been spent past, in budget order."""
    return tuple(line.limit_name for line in budget_lines(budget, progress) if line.exceeded)


class SaturationState(Enum):
    """Three answers, because "we do not know yet" is one of them.

    Collapsing `INSUFFICIENT_EVIDENCE` into `NOT_SATURATED` would be the usual
    lie: a batch that has run two rounds against a three-round rule has produced
    no evidence about saturation at all, and reporting "not saturated" invites
    somebody to keep spending on the strength of a measurement nobody made.
    """

    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NOT_SATURATED = "not_saturated"
    SATURATED = "saturated"


@dataclass(frozen=True)
class SaturationSignal:
    """A saturation rule, evaluated, with its components left in view.

    There is no score. `rates` is the last N round rates in order, `threshold`
    is the number they were compared against, and `undetermined_rounds` names
    the rounds whose rate could not be computed at all - a round that observed
    nothing, or one where nothing carried the field the metric counts. A reader
    can therefore see *why* the answer is what it is, and disagree with it.
    """

    rule: SaturationRule
    state: SaturationState
    rounds_considered: int
    rounds_required: int
    threshold: float
    rates: tuple[float | None, ...] = ()
    undetermined_rounds: tuple[int, ...] = ()
    detail: str = ""

    @property
    def is_saturated(self) -> bool:
        return self.state is SaturationState.SATURATED


@dataclass(frozen=True)
class StopSignal:
    """One declared condition, evaluated against what the batch has done."""

    condition: StopCondition
    triggered: bool
    observed: int | None = None
    threshold: int | None = None
    detail: str = ""

    @property
    def reason(self) -> StopReason:
        return self.condition.reason

    @property
    def action(self) -> StopAction:
        return self.condition.action

    @property
    def halts(self) -> bool:
        """True when this signal has fired *and* its action is to stop."""
        return self.triggered and self.condition.action is StopAction.STOP


def collection_progress(batch: ResearchBatch) -> BatchProgress:
    """The half of progress the batch record knows on its own. Pure."""
    return BatchProgress(
        queries=len(batch.ran_query_ids),
        rounds=len(batch.rounds),
        observations=batch.observations,
        unique_candidates=len(batch.candidate_ids),
    )


def evaluate_stop_conditions(
    batch: ResearchBatch,
    progress: BatchProgress | None = None,
    *,
    on: dt.date,
    saturation: tuple[SaturationSignal, ...] = (),
) -> tuple[StopSignal, ...]:
    """Evaluate every declared condition. Pure, and in declaration order.

    `progress` defaults to what the batch knows about itself, which is enough
    for all three counting conditions - they count queries, observations and
    unique candidates, and those are properties of the round log. The saturation
    signals are supplied because computing them needs the candidate records, and
    this module deliberately does not read them.
    """
    measured = progress if progress is not None else collection_progress(batch)
    by_rule = {signal.rule: signal for signal in saturation}
    out: list[StopSignal] = []

    for condition in batch.stop_conditions:
        if condition.reason in COUNT_REASONS:
            observed = getattr(measured, PROGRESS_FIELD[condition.reason])
            triggered = observed >= condition.threshold
            out.append(
                StopSignal(
                    condition=condition,
                    triggered=triggered,
                    observed=observed,
                    threshold=condition.threshold,
                    detail=(
                        f"{observed} of {condition.threshold} "
                        f"{PROGRESS_FIELD[condition.reason]}"
                    ),
                )
            )
        elif condition.reason is StopReason.DEADLINE:
            triggered = on >= condition.deadline
            out.append(
                StopSignal(
                    condition=condition,
                    triggered=triggered,
                    detail=(
                        f"deadline {condition.deadline} "
                        f"{'reached' if triggered else 'not yet reached'} on {on}"
                    ),
                )
            )
        elif condition.reason is StopReason.BUDGET_EXHAUSTED:
            lines = budget_lines(batch.budget, measured)
            spent = tuple(line.limit_name for line in lines if line.reached)
            unknown = tuple(line.limit_name for line in lines if line.unavailable)
            detail = (
                f"ceilings reached: {', '.join(spent)}"
                if spent
                else "no ceiling reached"
            )
            if unknown:
                detail += f"; not measured: {', '.join(unknown)}"
            out.append(
                StopSignal(condition=condition, triggered=bool(spent), detail=detail)
            )
        else:
            signal = by_rule.get(condition.saturation)
            if signal is None:
                out.append(
                    StopSignal(
                        condition=condition,
                        triggered=False,
                        detail=(
                            "saturation was not evaluated; the candidate records needed "
                            "to compute the rate were not supplied"
                        ),
                    )
                )
                continue
            out.append(
                StopSignal(
                    condition=condition,
                    triggered=signal.is_saturated,
                    detail=signal.detail,
                )
            )
    return tuple(out)


def triggered_stops(signals: Iterable[StopSignal]) -> tuple[StopSignal, ...]:
    return tuple(signal for signal in signals if signal.triggered)


# --------------------------------------------------------------------------
# The four state changes, each gated on a measurement
# --------------------------------------------------------------------------


def _last_event_date(batch: ResearchBatch) -> dt.date:
    return batch.history[-1].on if batch.history else batch.created


def _assert_not_before(batch: ResearchBatch, on: dt.date, what: str) -> None:
    last = _last_event_date(batch)
    if on < last:
        raise ResearchError(
            f"batch {batch.id!r}: {what} is dated {on}, before the last event on {last}. "
            "The history is append-only, so it cannot gain an earlier entry."
        )


def record_round(
    batch: ResearchBatch,
    round: DiscoveryRound,
    *,
    by: str,
    detail: str = "",
    saturation: tuple[SaturationSignal, ...] = (),
) -> ResearchBatch:
    """Record that a query ran and what it put in front of us. Appends only.

    Four refusals, and each one is a place a batch would otherwise overspend
    without anybody deciding to:

    - the batch is not `COLLECTING`, so collection started without a signed
      decision that it should;
    - the round names a query the batch never declared, which would charge its
      cost to nobody;
    - the round would carry the batch past a hard collection ceiling. The whole
      round is refused rather than trimmed to fit: half an observation log is a
      research record that has quietly lost evidence, and the duplicate rate
      computed from it would be wrong in a direction nobody could see;
    - a declared stop condition has already fired.

    Both of the last two name `escalate_batch` in the message, because
    continuing is a legitimate decision - it is just not a free one.
    """
    if batch.status is not BatchStatus.COLLECTING:
        raise ResearchError(
            f"batch {batch.id!r} is {batch.status.value!r}, so it is not collecting. "
            "Advance it to 'collecting' first - starting to spend is a decision, and it "
            "belongs in the history with a person against it."
        )
    if round.query_id not in batch.query_ids:
        raise ResearchError(
            f"batch {batch.id!r} does not declare query {round.query_id!r}. A round from "
            "an undeclared query produces candidates that belong to no batch, and a cost "
            "charged to nobody."
        )
    _assert_not_before(batch, round.ran_on, "the round")

    budget = batch.budget
    if budget.is_expired(round.ran_on):
        raise ResearchError(
            f"batch {batch.id!r}: the round ran on {round.ran_on}, past the budget "
            f"deadline of {budget.deadline}. Stop the batch, or escalate it with a new "
            "deadline and an authoriser."
        )

    queries = len(set(batch.ran_query_ids) | {round.query_id})
    observations = batch.observations + round.observations
    unique = len(set(batch.candidate_ids) | set(round.observed))
    for name, would_be in (
        ("max_queries", queries),
        ("max_candidate_observations", observations),
        ("max_unique_candidates", unique),
    ):
        limit = budget.limit(name)
        if limit is not None and would_be > limit:
            raise ResearchError(
                f"batch {batch.id!r}: this round would take {LIMIT_FIELD[name]} to "
                f"{would_be}, past the budget's {name} of {limit}. The round is refused "
                "whole rather than trimmed, because a truncated observation log loses "
                "evidence silently. Stop the batch, or raise the ceiling with "
                "escalate_batch and an authoriser."
            )

    fired = [
        signal
        for signal in triggered_stops(
            evaluate_stop_conditions(batch, on=round.ran_on, saturation=saturation)
        )
        if signal.halts
    ]
    if fired and not batch.escalated_since_stop:
        named = ", ".join(f"{s.reason.value} ({s.detail})" for s in fired)
        raise ResearchError(
            f"batch {batch.id!r} has reached a stop condition it declared before "
            f"collecting: {named}. Stop the batch, or escalate it with an authoriser - "
            "a condition that fires and changes nothing was not a condition."
        )

    return ResearchBatch(
        id=batch.id,
        objective=batch.objective,
        created=batch.created,
        owner=batch.owner,
        query_ids=batch.query_ids,
        budget=batch.budget,
        stop_conditions=batch.stop_conditions,
        target=batch.target,
        rounds=(*batch.rounds, round),
        status=batch.status,
        history=(
            *batch.history,
            BatchEvent(
                kind=BatchEventKind.ROUND_RECORDED,
                on=round.ran_on,
                by=by,
                detail=(
                    detail
                    or f"{round.query_id}: {round.observations} observation(s)"
                ),
            ),
        ),
        notes=batch.notes,
    )


def _assert_advance_evidence(
    batch: ResearchBatch, to: BatchStatus, progress: BatchProgress | None
) -> None:
    if to is BatchStatus.SCREENING and not batch.rounds:
        raise ResearchError(
            f"batch {batch.id!r} has recorded no discovery round, so there is nothing to "
            "screen. A batch does not reach 'screening' by declaration."
        )
    if to is BatchStatus.ANALYSIS_READY:
        if progress is None:
            raise ResearchError(
                f"batch {batch.id!r}: moving to 'analysis_ready' needs the candidate "
                "outcomes - the claim is that something was screened in, and that is a "
                "fact about the candidate records, not about the batch."
            )
        if progress.screened_in < 1:
            raise ResearchError(
                f"batch {batch.id!r} has no screened-in candidate, so nothing is ready "
                "for analysis. Screen something in, or stop the batch and record that "
                "the search found nothing worth an afternoon - that is a result."
            )
    if to is BatchStatus.COMPLETE:
        if progress is None:
            raise ResearchError(
                f"batch {batch.id!r}: completing needs the candidate outcomes, so the "
                "claim that every candidate was decided can be checked"
            )
        if progress.unscreened:
            raise ResearchError(
                f"batch {batch.id!r} still has {progress.unscreened} candidate(s) nobody "
                "decided about. Complete means every candidate has a screening decision; "
                "if they are not worth deciding, screen them out with a reason."
            )


def advance_batch(
    batch: ResearchBatch,
    to: BatchStatus,
    *,
    on: dt.date,
    by: str,
    reason: str,
    progress: BatchProgress | None = None,
    signals: tuple[StopSignal, ...] = (),
) -> ResearchBatch:
    """Move a batch, with the person, the day and the reason in the history.

    Two refusals beyond the transition table, and they are deliberately not the
    same rule:

    - **a fired stop condition blocks collecting**, and only collecting. A batch
      that has reached its candidate ceiling should go on to screening - that is
      the ceiling working - so the condition blocks the way back into
      `COLLECTING` and `record_round`, and nothing else.
    - **an exceeded ceiling blocks everything forward.** Consumption past a
      limit is spend nobody authorised, and continuing to spend it anywhere is
      the thing section 2 of the brief asks this layer not to do silently.

    Either is cleared by `escalate_batch`, which costs an authoriser's name.
    """
    assert_batch_transition(batch.status, to)
    _assert_not_before(batch, on, "the status change")
    _assert_advance_evidence(batch, to, progress)

    escalated = batch.escalated_since_stop
    if batch.status is BatchStatus.STOPPED and to in FORWARD_STATUSES and not escalated:
        raise ResearchError(
            f"batch {batch.id!r} is stopped. Restarting it needs an escalation recorded "
            "after the stop - who authorised continuing, and why. Use escalate_batch."
        )

    measured = progress if progress is not None else collection_progress(batch)
    if to in FORWARD_STATUSES and not escalated:
        over = exceeded_limits(batch.budget, measured)
        if over:
            raise ResearchError(
                f"batch {batch.id!r} has spent past {', '.join(over)}. That is research "
                "nobody authorised; the batch may only stop or be archived until "
                "escalate_batch raises the ceiling with an authoriser against it."
            )
        if to is BatchStatus.COLLECTING:
            fired = [s for s in signals if s.halts]
            if not signals:
                fired = [
                    s
                    for s in triggered_stops(
                        evaluate_stop_conditions(batch, measured, on=on)
                    )
                    if s.halts
                ]
            if fired:
                named = ", ".join(f"{s.reason.value} ({s.detail})" for s in fired)
                raise ResearchError(
                    f"batch {batch.id!r} cannot return to collecting: {named}. Escalate "
                    "it, or leave collection where the declared condition stopped it."
                )

    return ResearchBatch(
        id=batch.id,
        objective=batch.objective,
        created=batch.created,
        owner=batch.owner,
        query_ids=batch.query_ids,
        budget=batch.budget,
        stop_conditions=batch.stop_conditions,
        target=batch.target,
        rounds=batch.rounds,
        status=to,
        history=(
            *batch.history,
            BatchEvent(
                kind=BatchEventKind.STATUS_CHANGED,
                on=on,
                by=by,
                detail=reason,
                from_status=batch.status,
                to_status=to,
            ),
        ),
        notes=batch.notes,
    )


def stop_batch(
    batch: ResearchBatch,
    *,
    on: dt.date,
    by: str,
    reason: str,
    signals: tuple[StopSignal, ...] = (),
) -> ResearchBatch:
    """Stop a batch, recording which declared condition fired before the status.

    Two events, in that order, and the order is the point: the history says what
    was true and *then* what was decided, so a reader six weeks later can see
    whether the stop followed the rule the batch wrote down or somebody's
    Friday afternoon.
    """
    fired = triggered_stops(signals)
    detail = (
        "; ".join(f"{s.reason.value}: {s.detail}" for s in fired)
        if fired
        else f"stopped without a declared condition firing: {reason}"
    )
    stamped = ResearchBatch(
        id=batch.id,
        objective=batch.objective,
        created=batch.created,
        owner=batch.owner,
        query_ids=batch.query_ids,
        budget=batch.budget,
        stop_conditions=batch.stop_conditions,
        target=batch.target,
        rounds=batch.rounds,
        status=batch.status,
        history=(
            *batch.history,
            BatchEvent(
                kind=BatchEventKind.STOP_TRIGGERED, on=on, by=by, detail=detail
            ),
        ),
        notes=batch.notes,
    )
    return advance_batch(stamped, BatchStatus.STOPPED, on=on, by=by, reason=reason)


def _is_raised(before: int | None, after: int | None) -> bool:
    """Is `after` a more permissive ceiling than `before`? Removing one counts."""
    if before is None:
        return False  # there was no ceiling; nothing to raise
    return after is None or after > before


def _is_later(before: dt.date | None, after: dt.date | None) -> bool:
    if before is None:
        return False
    return after is None or after > before


def escalate_batch(
    batch: ResearchBatch,
    *,
    on: dt.date,
    by: str,
    reason: str,
    authorised_by: str,
    budget: BatchBudget | None = None,
) -> ResearchBatch:
    """Authorise continuing past a stop or a ceiling. Costs a name, every time.

    An escalation that raises no ceiling and extends no deadline is refused when
    a budget is supplied: "we agreed to continue" and "we agreed to spend more"
    are different decisions, and a budget object that changes nothing is the
    second one written as if it were the first. Escalating without a budget at
    all is legitimate - that is the saturation case, where the rule fired, a
    person disagreed, and the ceilings were never the problem.

    The status is untouched. An escalation clears the *block*; moving the batch
    is still `advance_batch`, with its own reason.
    """
    assert_text(authorised_by, "escalation authorised_by (who is accountable for this)")
    assert_text(reason, "escalation reason")
    _assert_not_before(batch, on, "the escalation")
    if batch.status is BatchStatus.ARCHIVED:
        raise ResearchError(
            f"batch {batch.id!r} is archived, and an archived record does not grow a "
            "history. Open a new batch that cites this one."
        )

    if budget is not None:
        if not isinstance(budget, BatchBudget):
            raise ResearchError("an escalation budget must be a BatchBudget")
        raised = [
            name for name in HARD_LIMITS if _is_raised(batch.budget.limit(name), budget.limit(name))
        ]
        extended = _is_later(batch.budget.deadline, budget.deadline)
        if not raised and not extended:
            raise ResearchError(
                f"batch {batch.id!r}: this escalation supplies a budget that raises no "
                "ceiling and extends no deadline. Escalate without a budget to authorise "
                "continuing, or supply one that actually allows more."
            )

    return ResearchBatch(
        id=batch.id,
        objective=batch.objective,
        created=batch.created,
        owner=batch.owner,
        query_ids=batch.query_ids,
        budget=budget if budget is not None else batch.budget,
        stop_conditions=batch.stop_conditions,
        target=batch.target,
        rounds=batch.rounds,
        status=batch.status,
        history=(
            *batch.history,
            BatchEvent(
                kind=BatchEventKind.ESCALATED,
                on=on,
                by=by,
                detail=f"{reason} (authorised by {authorised_by})",
            ),
        ),
        notes=batch.notes,
    )


def note_batch(
    batch: ResearchBatch, *, on: dt.date, by: str, detail: str
) -> ResearchBatch:
    """Append an observation to the history without changing anything else."""
    _assert_not_before(batch, on, "the note")
    return ResearchBatch(
        id=batch.id,
        objective=batch.objective,
        created=batch.created,
        owner=batch.owner,
        query_ids=batch.query_ids,
        budget=batch.budget,
        stop_conditions=batch.stop_conditions,
        target=batch.target,
        rounds=batch.rounds,
        status=batch.status,
        history=(
            *batch.history,
            BatchEvent(kind=BatchEventKind.NOTE, on=on, by=by, detail=detail),
        ),
        notes=batch.notes,
    )

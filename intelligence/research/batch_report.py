"""One batch, as the twenty numbers a research lead needs and nothing else.

The point of a report is to be cheaper than the thing it describes. A research
manager who has to read ninety candidate records to answer "did that search work"
has not been given a report, they have been given the batch again. So this is a
table: counts, rates, the ceilings and what was spent against them, and - the
part that is not a number - a list of everything nobody measured.

    build_batch_report(batch, outcomes, assessments, resources, as_of=...)

is a pure function of records that already exist. It runs no query, screens
nothing, promotes nothing and decides nothing; the stop signals it carries are
evaluated, not acted on, because acting on them is `stop_batch` and that takes a
person's name.

## Missing measurements are a section, not a footnote

`missing_measurements` collects every absence the other sections found: cost
fields nobody recorded, candidates with no creator, candidates nobody tagged,
candidates nobody screened, rounds whose rate could not be computed, ceilings
whose consumption was never measured. It is deliberately the longest section on
a young batch and it should shrink as the batch matures - a report where it is
empty and the batch is two rounds old is a report that has guessed at something.

## The report is deterministic

Same records in, same bytes out. Every ordering in every section is either a
declaration order or a total order with an id tiebreak, so a report committed on
Monday and regenerated on Friday from unchanged records is a zero-line diff -
which is what makes it safe to check one in beside the batch.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Iterable

from intelligence.research.batch import (
    BatchStatus,
    CandidateTarget,
    ResearchBatch,
)
from intelligence.research.batch_control import (
    BatchProgress,
    BudgetLine,
    SaturationSignal,
    SaturationState,
    StopSignal,
    budget_lines,
    evaluate_stop_conditions,
)
from intelligence.research.batch_metrics import (
    CandidateOutcome,
    CreatorConcentration,
    DuplicationMetrics,
    QueryPerformance,
    RoundProgress,
    TagCoverage,
    TierCount,
    batch_progress,
    by_candidate,
    creator_concentration,
    cost_denominators,
    duplication_metrics,
    funnel_counts,
    query_performance,
    round_progress,
    saturation_signals,
    tag_coverage,
)
from intelligence.research.errors import ResearchError
from intelligence.research.resources import (
    CostEfficiency,
    ResearchCost,
    ResearchResourceRecord,
    cost_efficiency,
    summarise_cost,
)
from intelligence.research.screening_queue import (
    QUEUE_CAVEAT,
    QueueEntry,
    ScreeningAssessment,
    ScreeningCoverage,
    screening_coverage,
    screening_queue,
)

REPORT_CAVEAT = (
    "Counts and rates over the records this batch holds. Screening signals are "
    "researcher judgement, not evidence; a rate computed over a round nobody "
    "supplied candidate records for is absent rather than zero. Read "
    "missing_measurements before reading anything else."
)


@dataclass(frozen=True)
class BatchReport:
    """Everything measurable about one batch, in one frozen object.

    Assembled from the seven metric functions, the screening queue and the
    resource ledger. Nothing here is computed twice and nothing is computed a
    second way: the report is an arrangement of those results, so a number in
    the report and the same number from the function that produced it cannot
    disagree.
    """

    batch_id: str
    objective: str
    owner: str
    status: BatchStatus
    as_of: dt.date
    progress: BatchProgress
    queries: tuple[QueryPerformance, ...]
    duplication: DuplicationMetrics
    creators: CreatorConcentration
    tags: TagCoverage
    rounds: tuple[RoundProgress, ...]
    saturation: tuple[SaturationSignal, ...]
    funnel: tuple[TierCount, ...]
    screening: ScreeningCoverage
    queue: tuple[QueueEntry, ...]
    cost: ResearchCost
    efficiency: CostEfficiency
    budget: tuple[BudgetLine, ...]
    stop_signals: tuple[StopSignal, ...]
    missing_measurements: tuple[str, ...] = ()
    target: CandidateTarget | None = None
    unmatched_candidates: tuple[str, ...] = ()
    caveat: str = REPORT_CAVEAT
    queue_caveat: str = QUEUE_CAVEAT

    @property
    def triggered(self) -> tuple[StopSignal, ...]:
        return tuple(signal for signal in self.stop_signals if signal.triggered)

    @property
    def halting(self) -> tuple[StopSignal, ...]:
        """Triggered conditions whose declared action is to stop."""
        return tuple(signal for signal in self.stop_signals if signal.halts)

    @property
    def exceeded(self) -> tuple[BudgetLine, ...]:
        return tuple(line for line in self.budget if line.exceeded)

    @property
    def on_target(self) -> bool | None:
        """Is the unique-candidate count inside the declared range? None if no range."""
        if self.target is None:
            return None
        return self.target.contains(self.progress.unique_candidates)

    def lines(self) -> tuple[str, ...]:
        """The report as short lines, for a terminal and for a review comment."""
        out: list[str] = [
            f"batch {self.batch_id}  {self.status.value}  as of {self.as_of}",
            f"  objective       {self.objective}",
            f"  owner           {self.owner}",
        ]
        if self.target is not None:
            fit = "inside" if self.on_target else "outside"
            out.append(
                f"  target          {self.target.minimum}-{self.target.maximum} "
                f"candidates ({fit} the range)"
            )
        progress = self.progress
        out += [
            "",
            f"  queries run     {progress.queries} of {len(self.queries)} declared",
            f"  rounds          {progress.rounds}",
            f"  observations    {progress.observations}",
            f"  unique          {progress.unique_candidates}",
            f"  duplicate rate  {_fmt(self.duplication.duplicate_rate)}"
            f"  ({self.duplication.duplicate_observations} repeat observation(s))",
            f"  screened        in {progress.screened_in}, out {progress.screened_out}, "
            f"undecided {progress.unscreened}",
            f"  promoted        {progress.promoted_sources} source(s), "
            f"{progress.reference_cases} reference case(s), "
            f"{progress.opportunities} opportunity(ies)",
        ]

        out += ["", "  query                        obs  uniq  only-here  in  promoted"]
        for query in self.queries:
            out.append(
                f"  {query.query_id:<28} {query.observations:>4} {query.candidates:>5} "
                f"{query.unique_contribution:>10} {query.screened_in:>3} "
                f"{query.promoted_sources:>9}"
            )

        creators = self.creators
        out += [
            "",
            f"  creators        {creators.unique_creators} known, "
            f"{creators.unknown_creator_candidates} candidate(s) with no creator recorded",
            f"  top creator     {creators.top_creator or '(none recorded)'} "
            f"{creators.top_creator_candidates} candidate(s), share "
            f"{_fmt(creators.top_creator_share)} of known",
            f"  tags            {self.tags.unique_tags} distinct, "
            f"{self.tags.untagged_candidates} candidate(s) untagged",
        ]

        if self.rounds:
            out += ["", "  round  query                        obs  new  rate"]
            for entry in self.rounds:
                out.append(
                    f"  {entry.index:>5}  {entry.query_id:<28} {entry.observations:>4} "
                    f"{entry.new_unique_candidates:>4}  {_fmt(entry.new_unique_rate)}"
                )
        for signal in self.saturation:
            out.append(
                f"  saturation      {signal.rule.metric.value}: {signal.state.value} "
                f"({signal.detail})"
            )

        out += ["", "  tier                          entered  exited  stopped"]
        for tier in self.funnel:
            out.append(
                f"  {tier.tier.value:<28} {tier.entered:>8} {tier.exited:>7} "
                f"{tier.stopped:>8}"
            )

        screening = self.screening
        out += [
            "",
            f"  screening       {screening.assessed} of {screening.candidates} assessed "
            f"({screening.fully_scored} fully, {screening.partially_scored} partly, "
            f"{screening.unscored} unscored)",
        ]

        out += ["", "  budget"]
        for line in self.budget:
            if line.unavailable:
                out.append(f"    {line.limit_name:<28} limit {line.limit}  {line.unavailable}")
            else:
                flag = " EXCEEDED" if line.exceeded else (" reached" if line.reached else "")
                out.append(
                    f"    {line.limit_name:<28} {line.consumed}/{line.limit} "
                    f"({_fmt(line.fraction)}){flag}"
                )

        out += ["", "  stop conditions"]
        for signal in self.stop_signals:
            mark = "FIRED" if signal.triggered else "     "
            out.append(
                f"    {mark} {signal.reason.value:<24} [{signal.action.value}] {signal.detail}"
            )

        computed = self.efficiency.computed
        out += ["", "  cost per useful outcome"]
        if computed:
            for ratio in computed:
                out.append(f"    {ratio.label:<44} {ratio.value}")
        else:
            out.append("    (none computable - see missing_measurements)")

        out += ["", "  missing measurements"]
        if self.missing_measurements:
            for item in self.missing_measurements:
                out.append(f"    {item}")
        else:
            out.append("    (none)")

        out += ["", f"  {self.caveat}"]
        return tuple(out)


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def build_batch_report(
    batch: ResearchBatch,
    outcomes: Iterable[CandidateOutcome] = (),
    assessments: Iterable[ScreeningAssessment] = (),
    resources: Iterable[ResearchResourceRecord] = (),
    *,
    as_of: dt.date,
) -> BatchReport:
    """Measure one batch. Pure, deterministic, and it changes nothing.

    `outcomes`, `assessments` and `resources` are supplied rather than loaded,
    so the whole report is testable without a directory and so this module reads
    no files. `ResearchStore.batch_report` is the convenience that assembles all
    three from the store.

    Resource records belonging to another batch are refused rather than ignored:
    a cost silently charged to the wrong search is the one accounting error this
    layer could not detect later.
    """
    known = by_candidate(outcomes)
    items = tuple(known.values())
    cards = tuple(assessments)
    ledger = tuple(resources)

    for record in ledger:
        if record.batch_id != batch.id:
            raise ResearchError(
                f"resource record {record.id!r} is charged to batch "
                f"{record.batch_id!r}, not to {batch.id!r}"
            )
    for card in cards:
        if card.batch_id != batch.id:
            raise ResearchError(
                f"screening assessment {card.id!r} belongs to batch {card.batch_id!r}, "
                f"not to {batch.id!r}"
            )

    cost = summarise_cost(ledger)
    progress = batch_progress(batch, items, cost)
    rounds = round_progress(batch, items)
    signals = saturation_signals(batch, rounds)
    lines = budget_lines(batch.budget, progress)
    stops = evaluate_stop_conditions(batch, progress, on=as_of, saturation=signals)

    pairs = tuple((outcome.candidate_id, outcome.state) for outcome in items)
    duplication = duplication_metrics(batch)
    creators = creator_concentration(batch, items)
    tags = tag_coverage(batch, items)
    coverage = screening_coverage(pairs, cards)
    unmatched = tuple(c for c in batch.candidate_ids if c not in known)

    return BatchReport(
        batch_id=batch.id,
        objective=batch.objective,
        owner=batch.owner,
        status=batch.status,
        as_of=as_of,
        progress=progress,
        queries=query_performance(batch, items),
        duplication=duplication,
        creators=creators,
        tags=tags,
        rounds=rounds,
        saturation=signals,
        funnel=funnel_counts(batch, items),
        screening=coverage,
        queue=screening_queue(pairs, cards),
        cost=cost,
        efficiency=cost_efficiency(cost, cost_denominators(progress)),
        budget=lines,
        stop_signals=stops,
        missing_measurements=_missing(
            batch, cost, rounds, signals, lines, creators, tags, coverage, unmatched
        ),
        target=batch.target,
        unmatched_candidates=unmatched,
    )


def _missing(
    batch: ResearchBatch,
    cost: ResearchCost,
    rounds: tuple[RoundProgress, ...],
    saturation: tuple[SaturationSignal, ...],
    budget: tuple[BudgetLine, ...],
    creators: CreatorConcentration,
    tags: TagCoverage,
    screening: ScreeningCoverage,
    unmatched: tuple[str, ...],
) -> tuple[str, ...]:
    """Every absence the other sections found, in one list, in a fixed order.

    Fixed order rather than sorted, because the order is the order a reader
    should worry in: candidates we have no record of at all, then the fields
    nobody filled in, then the rates that could not be computed, then the
    ceilings nobody is measuring against.
    """
    out: list[str] = []
    if unmatched:
        out.append(
            f"{len(unmatched)} observed candidate(s) have no candidate record supplied, "
            "so every screening, creator and tag count below excludes them"
        )
    if batch.unrun_query_ids:
        out.append(
            f"declared but never run: {', '.join(batch.unrun_query_ids)} - budgeted for "
            "and unspent, or work nobody did"
        )
    if batch.empty_rounds:
        out.append(
            f"round(s) {', '.join(str(i) for i in batch.empty_rounds)} observed nothing; "
            "they cost a query and leave no trace in candidate provenance"
        )
    if creators.unknown_creator_candidates:
        out.append(
            f"{creators.unknown_creator_candidates} candidate(s) have no creator "
            "recorded, so concentration is measured over "
            f"{creators.known_creator_candidates}"
        )
    if tags.untagged_candidates:
        out.append(
            f"{tags.untagged_candidates} candidate(s) carry no tag, so the "
            f"{tags.unique_tags} mechanic(s) below were observed in "
            f"{tags.tagged_candidates} candidate(s)"
        )
    if screening.unassessed:
        out.append(
            f"{screening.unassessed} candidate(s) have no screening assessment, so the "
            "queue orders a subset of the batch"
        )
    for entry in rounds:
        for problem in entry.unavailable:
            out.append(f"round {entry.index}: {problem}")
    for signal in saturation:
        if signal.state is SaturationState.INSUFFICIENT_EVIDENCE:
            out.append(f"saturation ({signal.rule.metric.value}): {signal.detail}")
    out.extend(cost.missing)
    for line in budget:
        if line.unavailable:
            out.append(f"budget {line.limit_name}: {line.unavailable}")
    return tuple(out)


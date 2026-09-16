"""Everything a batch can be measured on, computed and never estimated.

Seven questions a research lead has to answer about a finished search, and the
seven functions here are those questions, one each:

    batch_progress        how far did it get, against what it was allowed?
    query_performance     which query earned its place?
    duplication_metrics   how much of this did we already have?
    creator_concentration whose channel is this batch actually about?
    tag_coverage          which mechanics did we see, and how many stayed blank?
    round_progress        was each round still teaching us anything?
    funnel_counts         how many entered each tier, and how many went on?

Every one is a pure function of records that already exist, every one is
deterministic to the last digit, and none of them reads a title, a view count or
a thumbnail. The arithmetic is the cheap half of research management and it is
the half that should never be a judgement call.

## Unknown is not zero, and a rate over nothing does not exist

The refusal that shapes this module. A round that observed nothing has no new-
candidate rate - not 0.0, which would read as "we learned nothing" when the
truth is "we looked at nothing". A batch where nobody recorded a creator has no
top-creator share. A batch with no tagged candidates has no mechanic coverage.
Each of those is a `None` with a sentence beside it in `unavailable`, and the
saturation signal that would have been computed from them reports
`INSUFFICIENT_EVIDENCE` instead of a number.

## Concentration and coverage are measured over what is known

`top_creator_share` divides by the candidates whose creator we actually
recorded, not by all of them, and reports the unknown count beside it. Dividing
by all of them makes concentration look lower every time the metadata gets
worse, which is the wrong direction for a warning signal to move in.

## Tags are read, never inferred

`tag_coverage` counts `DiscoveryCandidate.tags` - slugs a researcher or an
ingestion payload supplied. There is no tokenizer here, no keyword list and no
title parsing. A candidate nobody tagged is counted as untagged, which is a
number the batch report prints; guessing "marble" from a title would turn that
number into a zero and the guess into a mechanic finding.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Iterable, Mapping

from intelligence.research.batch import (
    ResearchBatch,
    SaturationMetric,
    SaturationRule,
)
from intelligence.research.batch_control import (
    BatchProgress,
    SaturationSignal,
    SaturationState,
)
from intelligence.research.discovery import CandidateState, DiscoveryCandidate
from intelligence.research.errors import ResearchError
from intelligence.research.funnel import TIERS, CostTier
from intelligence.research.lifecycle import ResearchStage
from intelligence.research.resources import ResearchCost
from intelligence.research.sources import ResearchSource

UNSCREENED_STATES: frozenset[CandidateState] = frozenset(
    {CandidateState.DISCOVERED, CandidateState.QUEUED}
)
SCREENED_IN_STATES: frozenset[CandidateState] = frozenset(
    {CandidateState.SCREENED_IN, CandidateState.PROMOTED_TO_SOURCE}
)


def _round6(value: float) -> float:
    """Six decimals, so two machines agree on the text of the same rate."""
    return round(value, 6)


@dataclass(frozen=True)
class CandidateOutcome:
    """What became of one candidate, joined from the two records that know.

    The candidate says how far it got through screening; the source it was
    promoted to says what analysis it bought. Neither knows the other half, and
    every metric in this module needs both, so the join happens once, here, in a
    record small enough to build by hand in a test.

    `creator_key` prefers the platform's channel id over the display name,
    because two channels share a display name more often than a research lead
    expects and the concentration metric is the one place that matters.
    """

    candidate_id: str
    state: CandidateState
    reached: tuple[CandidateState, ...] = ()
    creator: str = ""
    creator_id: str = ""
    tags: tuple[str, ...] = ()
    query_ids: tuple[str, ...] = ()
    promoted_source_id: str = ""
    source_stage: ResearchStage | None = None
    reference_case_ids: tuple[str, ...] = ()
    opportunity_ids: tuple[str, ...] = ()

    @property
    def creator_key(self) -> str:
        """The channel this candidate belongs to, or "" when nobody recorded it."""
        return self.creator_id or self.creator

    @property
    def has_known_creator(self) -> bool:
        return bool(self.creator_key)

    @property
    def is_screened_in(self) -> bool:
        return self.state in SCREENED_IN_STATES

    @property
    def is_unscreened(self) -> bool:
        return self.state in UNSCREENED_STATES

    @property
    def is_promoted(self) -> bool:
        return bool(self.promoted_source_id)


def outcome_of(
    candidate: DiscoveryCandidate, source: ResearchSource | None = None
) -> CandidateOutcome:
    """Project a candidate, and the source it became, onto what the metrics need.

    `reached` replays the candidate's own screening history rather than reading
    its current state, because an archived candidate's state says `archived` and
    loses the fact that somebody screened it in first. The funnel counts are
    read off `reached` for exactly that reason.
    """
    seen = {step.to_state for step in candidate.history} | {
        candidate.state,
        CandidateState.DISCOVERED,
    }
    return CandidateOutcome(
        candidate_id=candidate.id,
        state=candidate.state,
        reached=tuple(state for state in CandidateState if state in seen),
        creator=candidate.creator,
        creator_id=candidate.creator_id,
        tags=candidate.tags,
        query_ids=candidate.query_ids,
        promoted_source_id=candidate.promoted_source_id,
        source_stage=None if source is None else source.stage,
        reference_case_ids=() if source is None else source.reference_case_ids,
        opportunity_ids=() if source is None else source.opportunity_ids,
    )


def by_candidate(
    outcomes: Iterable[CandidateOutcome],
) -> dict[str, CandidateOutcome]:
    out: dict[str, CandidateOutcome] = {}
    for outcome in outcomes:
        if outcome.candidate_id in out:
            raise ResearchError(
                f"two outcomes were supplied for candidate {outcome.candidate_id!r}; "
                "one candidate has one outcome, and a second would silently win"
            )
        out[outcome.candidate_id] = outcome
    return out


# --------------------------------------------------------------------------
# Progress
# --------------------------------------------------------------------------


def batch_progress(
    batch: ResearchBatch,
    outcomes: Iterable[CandidateOutcome] = (),
    cost: ResearchCost | None = None,
) -> BatchProgress:
    """Everything a budget or a stop condition is read against. Pure.

    The collection half comes from the round log and is always exact. The
    screening half comes from the outcomes supplied and is zero when none were -
    which is why `advance_batch` refuses to reach `analysis_ready` on a progress
    object nobody passed outcomes to, rather than believing the zeros.
    """
    known = by_candidate(outcomes)
    items = tuple(known.values())
    references: set[str] = set()
    opportunities: set[str] = set()
    for outcome in items:
        references.update(outcome.reference_case_ids)
        opportunities.update(outcome.opportunity_ids)
    screened_in = sum(1 for o in items if o.is_screened_in)
    screened_out = sum(1 for o in items if o.state is CandidateState.SCREENED_OUT)
    return BatchProgress(
        queries=len(batch.ran_query_ids),
        rounds=len(batch.rounds),
        observations=batch.observations,
        unique_candidates=len(batch.candidate_ids),
        screened=screened_in + screened_out,
        screened_in=screened_in,
        screened_out=screened_out,
        unscreened=sum(1 for o in items if o.is_unscreened),
        archived=sum(1 for o in items if o.state is CandidateState.ARCHIVED),
        promoted_sources=sum(1 for o in items if o.is_promoted),
        reference_cases=len(references),
        opportunities=len(opportunities),
        human_review_minutes=None if cost is None else cost.manual_minutes,
        reasoning_units=None if cost is None else cost.reasoning_units,
        tool_calls=None if cost is None else cost.tool_calls,
    )


# --------------------------------------------------------------------------
# Query performance
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class QueryPerformance:
    """What one query produced, and how much of it nothing else would have.

    `unique_contribution` is the number the brief asks for and the one that
    changes behaviour: two queries that each find twenty videos, fifteen of them
    shared, are not two queries worth running. It is counted over the batch, so
    it is a statement about this search and not about the query in general - a
    query with zero unique contribution here may be the only one that finds
    anything in a different batch.

    `unmatched_candidates` is how many of its observations had no candidate
    record supplied. Every screening and analysis count below is drawn from
    those records, so a non-zero value here is the coverage caveat for all of
    them.
    """

    query_id: str
    rounds: int = 0
    observations: int = 0
    candidates: int = 0
    repeat_observations: int = 0
    first_found: int = 0
    shared: int = 0
    unique_contribution: int = 0
    screened_in: int = 0
    screened_out: int = 0
    unscreened: int = 0
    promoted_sources: int = 0
    reference_cases: int = 0
    opportunities: int = 0
    unmatched_candidates: int = 0

    @property
    def ran(self) -> bool:
        return self.rounds > 0

    @property
    def unique_share(self) -> float | None:
        """Of what this query found, how much nothing else did. None if it found
        nothing - a query with no results has no composition."""
        if not self.candidates:
            return None
        return _round6(self.unique_contribution / self.candidates)


def query_performance(
    batch: ResearchBatch, outcomes: Iterable[CandidateOutcome] = ()
) -> tuple[QueryPerformance, ...]:
    """One row per declared query, in declaration order, zeros included. Pure.

    A declared query that never ran keeps its row with `rounds=0`. That row is
    the cheapest finding in the whole report: a query somebody wrote, budgeted
    for and never ran is either a plan that changed or work nobody did, and
    dropping it from the table hides both.
    """
    known = by_candidate(outcomes)
    seen_by: dict[str, list[str]] = {}
    first_round_of: dict[str, str] = {}
    for entry in batch.rounds:
        for candidate_id in entry.observed:
            seen_by.setdefault(candidate_id, [])
            if entry.query_id not in seen_by[candidate_id]:
                seen_by[candidate_id].append(entry.query_id)
            first_round_of.setdefault(candidate_id, entry.query_id)

    out: list[QueryPerformance] = []
    for query_id in batch.query_ids:
        rounds = batch.rounds_for(query_id)
        observations = sum(entry.observations for entry in rounds)
        candidates: list[str] = []
        for entry in rounds:
            for candidate_id in entry.observed:
                if candidate_id not in candidates:
                    candidates.append(candidate_id)
        unique = [c for c in candidates if seen_by[c] == [query_id]]
        matched = [known[c] for c in candidates if c in known]
        references: set[str] = set()
        opportunities: set[str] = set()
        for outcome in matched:
            references.update(outcome.reference_case_ids)
            opportunities.update(outcome.opportunity_ids)
        out.append(
            QueryPerformance(
                query_id=query_id,
                rounds=len(rounds),
                observations=observations,
                candidates=len(candidates),
                repeat_observations=observations - len(candidates),
                first_found=sum(
                    1 for c in candidates if first_round_of.get(c) == query_id
                ),
                shared=len(candidates) - len(unique),
                unique_contribution=len(unique),
                screened_in=sum(1 for o in matched if o.is_screened_in),
                screened_out=sum(
                    1 for o in matched if o.state is CandidateState.SCREENED_OUT
                ),
                unscreened=sum(1 for o in matched if o.is_unscreened),
                promoted_sources=sum(1 for o in matched if o.is_promoted),
                reference_cases=len(references),
                opportunities=len(opportunities),
                unmatched_candidates=len(candidates) - len(matched),
            )
        )
    return tuple(out)


# --------------------------------------------------------------------------
# Duplication and overlap
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class QueryOverlap:
    """How much two queries in this batch found the same things."""

    query_a: str
    query_b: str
    shared: int
    union: int
    jaccard: float | None = None


@dataclass(frozen=True)
class DuplicationMetrics:
    """How much of this search we already had before it ran.

    `duplicate_rate` is over *observations*, not candidates: the cost of a
    duplicate is the second time somebody looked at it, and that cost is an
    observation. A batch with 100 observations and 40 candidates spent 60
    observations re-reading pages it had already read.
    """

    observations: int
    unique_candidates: int
    duplicate_observations: int
    duplicate_rate: float | None = None
    seen_once: int = 0
    seen_more_than_once: int = 0
    multi_query_candidates: int = 0
    max_sightings: int = 0
    overlaps: tuple[QueryOverlap, ...] = ()


def duplication_metrics(batch: ResearchBatch) -> DuplicationMetrics:
    """Count re-sightings and pairwise query overlap. Pure, from the round log.

    Read off the rounds rather than off candidate provenance, because provenance
    is keyed by `(query, day)` and collapses a query run twice in one day into
    one entry. The round log keeps both, and both were paid for.
    """
    sightings: dict[str, int] = {}
    queries_of: dict[str, list[str]] = {}
    for entry in batch.rounds:
        for candidate_id in entry.observed:
            sightings[candidate_id] = sightings.get(candidate_id, 0) + 1
            bucket = queries_of.setdefault(candidate_id, [])
            if entry.query_id not in bucket:
                bucket.append(entry.query_id)

    observations = batch.observations
    unique = len(sightings)
    ran = batch.ran_query_ids
    found_by: dict[str, set[str]] = {q: set() for q in ran}
    for candidate_id, query_ids in queries_of.items():
        for query_id in query_ids:
            found_by[query_id].add(candidate_id)

    overlaps: list[QueryOverlap] = []
    for index, query_a in enumerate(ran):
        for query_b in ran[index + 1 :]:
            a, b = found_by[query_a], found_by[query_b]
            shared = len(a & b)
            union = len(a | b)
            overlaps.append(
                QueryOverlap(
                    query_a=query_a,
                    query_b=query_b,
                    shared=shared,
                    union=union,
                    jaccard=None if not union else _round6(shared / union),
                )
            )

    return DuplicationMetrics(
        observations=observations,
        unique_candidates=unique,
        duplicate_observations=observations - unique,
        duplicate_rate=(
            None if not observations else _round6((observations - unique) / observations)
        ),
        seen_once=sum(1 for count in sightings.values() if count == 1),
        seen_more_than_once=sum(1 for count in sightings.values() if count > 1),
        multi_query_candidates=sum(1 for ids in queries_of.values() if len(ids) > 1),
        max_sightings=max(sightings.values()) if sightings else 0,
        overlaps=tuple(overlaps),
    )


# --------------------------------------------------------------------------
# Creator concentration
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CreatorConcentration:
    """Whose channel this batch is actually about.

    Surfaced, never acted on. Thirty candidates from one creator may be a biased
    search or may be the honest shape of a niche one channel invented, and the
    difference is not in any of these numbers. What the numbers do is make the
    question unavoidable.

    `top_creator_share` divides by `known_creators_candidates`, not by all of
    them. Dividing by all would make concentration fall every time the metadata
    got worse, which is the wrong direction for a warning to move in;
    `unknown_creator_candidates` is printed beside it so the coverage is visible.
    """

    candidates: int
    known_creator_candidates: int
    unknown_creator_candidates: int
    unique_creators: int
    counts: tuple[tuple[str, int], ...] = ()
    top_creator: str = ""
    top_creator_candidates: int = 0
    top_creator_share: float | None = None
    creator_coverage: float | None = None


def creator_concentration(
    batch: ResearchBatch, outcomes: Iterable[CandidateOutcome] = ()
) -> CreatorConcentration:
    """Count candidates per channel over the batch's candidates. Pure.

    A candidate with no outcome record counts as unknown-creator rather than
    being dropped, because a batch whose metadata never arrived is concentrated
    in a way nobody can see, and a smaller denominator would hide it.
    """
    known = by_candidate(outcomes)
    counts: dict[str, int] = {}
    unknown = 0
    for candidate_id in batch.candidate_ids:
        outcome = known.get(candidate_id)
        key = outcome.creator_key if outcome is not None else ""
        if not key:
            unknown += 1
            continue
        counts[key] = counts.get(key, 0) + 1

    total = len(batch.candidate_ids)
    known_count = total - unknown
    ordered = tuple(sorted(counts.items(), key=lambda item: (-item[1], item[0])))
    top_creator, top_count = ordered[0] if ordered else ("", 0)
    return CreatorConcentration(
        candidates=total,
        known_creator_candidates=known_count,
        unknown_creator_candidates=unknown,
        unique_creators=len(counts),
        counts=ordered,
        top_creator=top_creator,
        top_creator_candidates=top_count,
        top_creator_share=None if not known_count else _round6(top_count / known_count),
        creator_coverage=None if not total else _round6(known_count / total),
    )


# --------------------------------------------------------------------------
# Tag / mechanic coverage
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class TagCoverage:
    """Which mechanics this batch actually observed, from explicit tags only.

    `untagged_candidates` is the number that keeps the rest honest. A batch
    reporting four mechanics over ninety candidates, eighty of which nobody
    tagged, has observed four mechanics in ten videos - and the ten is the
    number that says whether the four mean anything.
    """

    candidates: int
    tagged_candidates: int
    untagged_candidates: int
    unique_tags: int
    counts: tuple[tuple[str, int], ...] = ()
    first_seen_round: tuple[tuple[str, int], ...] = ()
    new_tags_per_round: tuple[int, ...] = ()
    tag_coverage: float | None = None


def tag_coverage(
    batch: ResearchBatch, outcomes: Iterable[CandidateOutcome] = ()
) -> TagCoverage:
    """Count explicit candidate tags, and when each was first observed. Pure.

    No inference of any kind. A tag is a slug on a `DiscoveryCandidate`, put
    there by a researcher or by a validated ingestion payload; a title is never
    read, because a mechanic guessed from a title is a finding the batch did not
    make.
    """
    known = by_candidate(outcomes)
    counts: dict[str, int] = {}
    tagged = 0
    for candidate_id in batch.candidate_ids:
        outcome = known.get(candidate_id)
        tags = outcome.tags if outcome is not None else ()
        if tags:
            tagged += 1
        for tag in tags:
            counts[tag] = counts.get(tag, 0) + 1

    first_seen: dict[str, int] = {}
    per_round: list[int] = []
    for index, entry in enumerate(batch.rounds):
        new_here = 0
        for candidate_id in entry.observed:
            outcome = known.get(candidate_id)
            for tag in outcome.tags if outcome is not None else ():
                if tag not in first_seen:
                    first_seen[tag] = index
                    new_here += 1
        per_round.append(new_here)

    total = len(batch.candidate_ids)
    return TagCoverage(
        candidates=total,
        tagged_candidates=tagged,
        untagged_candidates=total - tagged,
        unique_tags=len(counts),
        counts=tuple(sorted(counts.items(), key=lambda item: (-item[1], item[0]))),
        first_seen_round=tuple(sorted(first_seen.items(), key=lambda i: (i[1], i[0]))),
        new_tags_per_round=tuple(per_round),
        tag_coverage=None if not total else _round6(tagged / total),
    )


# --------------------------------------------------------------------------
# Round by round, and saturation
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RoundProgress:
    """One round, and how much of it was information we did not already have.

    Three rates, three different denominators, and the denominators are the
    honest part:

    - `new_unique_rate` is over the round's observations. A round that observed
      nothing has no rate at all.
    - `new_creator_rate` is over the observations whose candidate named a
      creator. A round of twenty videos with no channel recorded has no creator
      rate - reporting 0.0 would say "no new channels", which is not what was
      measured.
    - `new_tag_rate` is over the observations that carried at least one tag,
      for the same reason.

    `unavailable` names each rate that could not be computed, with the input
    that was missing, the same way `sources.derive` does for public metrics.
    """

    index: int
    query_id: str
    ran_on: dt.date
    observations: int = 0
    new_unique_candidates: int = 0
    new_unique_rate: float | None = None
    creator_observations: int = 0
    new_creators: int = 0
    new_creator_rate: float | None = None
    tagged_observations: int = 0
    new_tags: int = 0
    new_tag_rate: float | None = None
    cumulative_unique: int = 0
    cumulative_creators: int = 0
    cumulative_tags: int = 0
    unmatched_observations: int = 0
    unavailable: tuple[str, ...] = ()

    def rate(self, metric: SaturationMetric) -> float | None:
        if metric is SaturationMetric.NEW_UNIQUE_CANDIDATES:
            return self.new_unique_rate
        if metric is SaturationMetric.NEW_CREATORS:
            return self.new_creator_rate
        return self.new_tag_rate


def round_progress(
    batch: ResearchBatch, outcomes: Iterable[CandidateOutcome] = ()
) -> tuple[RoundProgress, ...]:
    """Replay the rounds in order and measure what each one added. Pure.

    Order is the record's order, which construction already holds to be
    chronological. Replaying rather than recomputing from provenance is what
    makes "new" mean new *at that point*, which is the only sense in which a
    saturation curve means anything.
    """
    known = by_candidate(outcomes)
    seen_candidates: set[str] = set()
    seen_creators: set[str] = set()
    seen_tags: set[str] = set()
    out: list[RoundProgress] = []

    for index, entry in enumerate(batch.rounds):
        missing: list[str] = []
        unmatched = 0
        new_candidates = 0
        creator_observations = 0
        tagged_observations = 0
        new_creators: set[str] = set()
        new_tags: set[str] = set()

        for candidate_id in entry.observed:
            if candidate_id not in seen_candidates:
                new_candidates += 1
            outcome = known.get(candidate_id)
            if outcome is None:
                unmatched += 1
                continue
            if outcome.has_known_creator:
                creator_observations += 1
                if outcome.creator_key not in seen_creators:
                    new_creators.add(outcome.creator_key)
            if outcome.tags:
                tagged_observations += 1
                for tag in outcome.tags:
                    if tag not in seen_tags:
                        new_tags.add(tag)

        observations = entry.observations
        new_unique_rate: float | None = None
        if not observations:
            missing.append("new_unique_rate: the round observed nothing")
        else:
            new_unique_rate = _round6(new_candidates / observations)

        new_creator_rate: float | None = None
        if not creator_observations:
            missing.append(
                "new_creator_rate: no observation in this round named a creator"
            )
        else:
            new_creator_rate = _round6(len(new_creators) / creator_observations)

        new_tag_rate: float | None = None
        if not tagged_observations:
            missing.append("new_tag_rate: no observation in this round carried a tag")
        else:
            new_tag_rate = _round6(len(new_tags) / tagged_observations)

        if unmatched:
            missing.append(
                f"{unmatched} observation(s) have no candidate record, so their creator "
                "and tags were counted as unknown"
            )

        seen_candidates.update(entry.observed)
        seen_creators.update(new_creators)
        seen_tags.update(new_tags)

        out.append(
            RoundProgress(
                index=index,
                query_id=entry.query_id,
                ran_on=entry.ran_on,
                observations=observations,
                new_unique_candidates=new_candidates,
                new_unique_rate=new_unique_rate,
                creator_observations=creator_observations,
                new_creators=len(new_creators),
                new_creator_rate=new_creator_rate,
                tagged_observations=tagged_observations,
                new_tags=len(new_tags),
                new_tag_rate=new_tag_rate,
                cumulative_unique=len(seen_candidates),
                cumulative_creators=len(seen_creators),
                cumulative_tags=len(seen_tags),
                unmatched_observations=unmatched,
                unavailable=tuple(missing),
            )
        )
    return tuple(out)


def saturation_signal(
    rule: SaturationRule, rounds: Iterable[RoundProgress]
) -> SaturationSignal:
    """Evaluate one saturation rule over the round history. Pure.

    Three ways to answer, and the third is the one that keeps the other two
    usable:

    - fewer rounds than the rule requires - `INSUFFICIENT_EVIDENCE`. A batch
      that ran two rounds against a three-round rule has measured nothing about
      what a third would find.
    - a round in the window whose rate could not be computed -
      `INSUFFICIENT_EVIDENCE`, naming it. A rule about new creators cannot be
      evaluated across a round where nobody recorded a creator, and treating the
      missing rate as zero would read as total saturation.
    - otherwise, saturated when every rate in the window is below the threshold.
    """
    history = tuple(rounds)
    window = history[-rule.rounds :] if len(history) >= rule.rounds else history
    rates = tuple(entry.rate(rule.metric) for entry in window)

    if len(history) < rule.rounds:
        return SaturationSignal(
            rule=rule,
            state=SaturationState.INSUFFICIENT_EVIDENCE,
            rounds_considered=len(history),
            rounds_required=rule.rounds,
            threshold=rule.new_rate_below,
            rates=rates,
            detail=(
                f"{len(history)} of {rule.rounds} round(s) recorded; not enough evidence "
                f"yet to say whether {rule.metric.value} has flattened"
            ),
        )

    undetermined = tuple(
        entry.index for entry, rate in zip(window, rates) if rate is None
    )
    if undetermined:
        return SaturationSignal(
            rule=rule,
            state=SaturationState.INSUFFICIENT_EVIDENCE,
            rounds_considered=len(window),
            rounds_required=rule.rounds,
            threshold=rule.new_rate_below,
            rates=rates,
            undetermined_rounds=undetermined,
            detail=(
                f"round(s) {', '.join(str(i) for i in undetermined)} have no "
                f"{rule.metric.value} rate, so the window cannot be judged"
            ),
        )

    below = sum(1 for rate in rates if rate < rule.new_rate_below)
    saturated = below == len(rates)
    return SaturationSignal(
        rule=rule,
        state=SaturationState.SATURATED if saturated else SaturationState.NOT_SATURATED,
        rounds_considered=len(window),
        rounds_required=rule.rounds,
        threshold=rule.new_rate_below,
        rates=rates,
        detail=(
            f"{below} of the last {len(rates)} round(s) below "
            f"{rule.new_rate_below} {rule.metric.value}"
        ),
    )


def saturation_signals(
    batch: ResearchBatch, rounds: Iterable[RoundProgress]
) -> tuple[SaturationSignal, ...]:
    """One signal per saturation rule the batch declared, in declaration order."""
    history = tuple(rounds)
    return tuple(saturation_signal(rule, history) for rule in batch.saturation_rules)


# --------------------------------------------------------------------------
# The funnel
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class TierCount:
    """How many things entered one cost tier, and how many bought the next one.

    `stopped` is the number this whole layer exists to make large at the cheap
    tiers and small at the expensive ones. A funnel where tier 2 stops four of
    ninety is a queue nobody filtered, and the cost of that shows up two tiers
    later as afternoons.
    """

    tier: CostTier
    entered: int
    exited: int

    @property
    def stopped(self) -> int:
        return self.entered - self.exited

    @property
    def pass_rate(self) -> float | None:
        if not self.entered:
            return None
        return _round6(self.exited / self.entered)


def funnel_counts(
    batch: ResearchBatch, outcomes: Iterable[CandidateOutcome] = ()
) -> tuple[TierCount, ...]:
    """Counts entering and leaving each of the six tiers. Pure.

    Entry to a tier is derived from what a candidate *reached*, not from where
    it is now, so an archived candidate that was screened in still counts as
    having bought tier 2. `exited` is by definition `entered` at the next tier,
    which is what makes the six rows add up instead of being six independent
    counts that can disagree.
    """
    known = by_candidate(outcomes)
    items = tuple(known[c] for c in batch.candidate_ids if c in known)

    reached_screening = sum(
        1
        for o in items
        if any(
            state in o.reached
            for state in (
                CandidateState.QUEUED,
                CandidateState.SCREENED_IN,
                CandidateState.SCREENED_OUT,
                CandidateState.PROMOTED_TO_SOURCE,
            )
        )
    )
    promoted = sum(1 for o in items if o.is_promoted)
    with_reference = sum(1 for o in items if o.reference_case_ids)
    with_opportunity = sum(1 for o in items if o.opportunity_ids)
    recommended = sum(
        1 for o in items if o.source_stage is ResearchStage.PROTOTYPE_RECOMMENDED
    )

    entered: dict[CostTier, int] = {
        CostTier.IDENTITY: batch.observations,
        CostTier.PUBLIC_METADATA: len(batch.candidate_ids),
        CostTier.SCREENING: reached_screening,
        CostTier.REFERENCE_ANALYSIS: promoted,
        CostTier.OPPORTUNITY_DOSSIER: with_reference,
        CostTier.PROTOTYPE_RECOMMENDATION: with_opportunity,
    }
    exited: dict[CostTier, int] = {
        CostTier.IDENTITY: len(batch.candidate_ids),
        CostTier.PUBLIC_METADATA: reached_screening,
        CostTier.SCREENING: promoted,
        CostTier.REFERENCE_ANALYSIS: with_reference,
        CostTier.OPPORTUNITY_DOSSIER: with_opportunity,
        CostTier.PROTOTYPE_RECOMMENDATION: recommended,
    }
    return tuple(
        TierCount(tier=spec.tier, entered=entered[spec.tier], exited=exited[spec.tier])
        for spec in TIERS
    )


def cost_denominators(progress: BatchProgress) -> Mapping[str, int]:
    """The four useful-outcome counts research cost is divided by."""
    return {
        "unique_candidate": progress.unique_candidates,
        "screened_in_candidate": progress.screened_in,
        "promoted_source": progress.promoted_sources,
        "opportunity": progress.opportunities,
    }



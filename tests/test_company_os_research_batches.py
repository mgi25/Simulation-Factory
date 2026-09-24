"""Focused tests for the Company OS research batch layer.

Phase 4 made one video one candidate. This layer is what happens when there are
three hundred of them, and nearly every invariant worth a test is a refusal or
an absence:

- a batch declares its budget and its stop conditions before it collects;
- a round that would break a ceiling is refused whole, never trimmed to fit;
- a stop condition that fires stops collecting, and only an escalation with an
  authoriser's name against it starts again;
- a duplicate is counted where it cost something - at the observation;
- a candidate with no creator recorded stays unknown, and concentration is
  measured over what is known;
- a mechanic is a tag somebody typed, never a word in a title;
- saturation over too few rounds is "not enough evidence", never "not yet";
- a screening judgement carries a reviewer, a reason and evidence, and an
  unscored candidate keeps its place in the queue;
- a cost ratio exists only when both halves of it were measured.

Plus the branch guards: no new dependency, no network, no model, no production
import in either direction, and rule 2 exactly where it was.
"""

from __future__ import annotations

import ast
import dataclasses
import datetime as dt
import subprocess
from pathlib import Path

import pytest

from ai_platform import ExecutionPolicy, SubagentPolicyViolation
from ai_platform.serde import dumps
from ai_platform.usage import UsageUnit
from company.validation.errors import ValidationError
from company.validation.no_subagents import enforce_no_subagents
from intelligence.research import (
    HARD_LIMITS,
    SCREENING_SIGNALS,
    BatchBudget,
    BatchEventKind,
    BatchStatus,
    CandidateOutcome,
    CandidateState,
    CandidateTarget,
    CaptureMethod,
    ConfidenceLevel,
    CostTier,
    DimensionScore,
    DiscoveryCandidate,
    DiscoveryProvenance,
    DiscoveryQuery,
    DiscoveryRound,
    Evidence,
    QueueStatus,
    ResearchBatch,
    ResearchConfidence,
    ResearchError,
    ResearchResourceRecord,
    ResearchStore,
    RightsStatus,
    SaturationMetric,
    SaturationRule,
    SaturationState,
    ScreeningAssessment,
    ScreeningRecommendation,
    SourceQuality,
    SourceType,
    StopAction,
    StopCondition,
    StopReason,
    advance_batch,
    batch_progress,
    build_batch_report,
    candidate_id_for,
    canonicalize,
    cost_denominators,
    cost_efficiency,
    creator_concentration,
    duplication_metrics,
    escalate_batch,
    evaluate_stop_conditions,
    funnel_counts,
    note_batch,
    open_batch,
    outcome_of,
    query_performance,
    queue_candidate,
    record_round,
    round_progress,
    saturation_signal,
    screen_candidate,
    screening_coverage,
    screening_queue,
    stop_batch,
    summarise_cost,
    tag_coverage,
)
from knowledge.company_os import Freshness
from knowledge.company_os.capsules import CapsuleIndex
from knowledge.company_os.capsules.budget import DEFAULT_BUDGET

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE = REPO_ROOT / "intelligence"
SEED_ROOT = REPO_ROOT / "knowledge" / "company_os" / "capsules" / "seeds"

TODAY = dt.date(2026, 9, 16)
RACE = "dq-marble-race"
MACHINE = "dq-satisfying-machine"


def day(offset: int = 0) -> dt.date:
    return TODAY + dt.timedelta(days=offset)


# --------------------------------------------------------------------------
# Builders
# --------------------------------------------------------------------------


def an_evidence(ref: str = "docs/validation/discovery/2026-09-16-marble.md") -> Evidence:
    return Evidence(kind="observation", ref=ref, note="read off the public page")


def a_budget(**overrides) -> BatchBudget:
    data = dict(
        max_queries=3,
        max_candidate_observations=40,
        max_unique_candidates=20,
        max_promoted_candidates=4,
        max_reference_cases=3,
        max_human_review_minutes=180,
    )
    data.update(overrides)
    return BatchBudget(**data)


def a_saturation_condition(**overrides) -> StopCondition:
    rule = dict(rounds=3, new_rate_below=0.25, metric=SaturationMetric.NEW_UNIQUE_CANDIDATES)
    rule.update(overrides.pop("rule", {}))
    data = dict(
        reason=StopReason.SATURATION,
        action=StopAction.STOP,
        saturation=SaturationRule(**rule),
    )
    data.update(overrides)
    return StopCondition(**data)


def a_batch(**overrides) -> ResearchBatch:
    data = dict(
        id="rb-marble-sweep",
        objective="Find marble-run formats whose loop renews without narration.",
        created=TODAY,
        owner="research_opportunity_lead",
        query_ids=(RACE, MACHINE),
        budget=a_budget(),
        stop_conditions=(
            StopCondition(reason=StopReason.MAX_UNIQUE_CANDIDATES, threshold=20),
            a_saturation_condition(),
        ),
        target=CandidateTarget(minimum=8, maximum=20),
    )
    data.update(overrides)
    return open_batch(**data)


def collecting(batch: ResearchBatch | None = None) -> ResearchBatch:
    return advance_batch(
        batch or a_batch(),
        BatchStatus.COLLECTING,
        on=TODAY,
        by="research_opportunity_lead",
        reason="Budget and stop conditions agreed; collection may start.",
    )


def an_outcome(candidate_id: str, **overrides) -> CandidateOutcome:
    """A candidate outcome built by hand - the metrics take a projection, so
    most of these tests need no store and no candidate records at all."""
    state = overrides.pop("state", CandidateState.QUEUED)
    reached = {CandidateState.DISCOVERED, state}
    if state in (CandidateState.SCREENED_IN, CandidateState.PROMOTED_TO_SOURCE):
        reached |= {CandidateState.QUEUED, CandidateState.SCREENED_IN}
    if state is CandidateState.SCREENED_OUT:
        reached |= {CandidateState.QUEUED}
    data = dict(
        candidate_id=candidate_id,
        state=state,
        reached=tuple(s for s in CandidateState if s in reached),
        creator_id="chan-alpha",
        tags=("race",),
    )
    data.update(overrides)
    return CandidateOutcome(**data)


def an_assessment(candidate_id: str, **overrides) -> ScreeningAssessment:
    signals = overrides.pop("signals", SCREENING_SIGNALS)
    score = overrides.pop("score", 4)
    data = dict(
        id=f"sa-{candidate_id}",
        batch_id="rb-marble-sweep",
        candidate_id=candidate_id,
        reviewer="research_screener",
        reviewed_on=TODAY,
        reason="The loop renews at every junction without narration.",
        evidence=(an_evidence(),),
        scores=tuple(
            DimensionScore(dimension=name, score=score, reason="watched the first minute")
            for name in signals
        ),
        recommendation=ScreeningRecommendation.SCREEN_IN,
    )
    data.update(overrides)
    return ScreeningAssessment(**data)


def a_resource(**overrides) -> ResearchResourceRecord:
    data = dict(
        id="rr-discovery",
        batch_id="rb-marble-sweep",
        recorded_on=TODAY,
        recorded_by="research_opportunity_lead",
        tier=CostTier.PUBLIC_METADATA,
        manual_minutes=60,
    )
    data.update(overrides)
    return ResearchResourceRecord(**data)


def rounds(batch: ResearchBatch, *specs) -> ResearchBatch:
    """Record a sequence of `(query_id, offset, ids...)` rounds."""
    for query_id, offset, *observed in specs:
        batch = record_round(
            batch,
            DiscoveryRound(query_id=query_id, ran_on=day(offset), observed=tuple(observed)),
            by="research_opportunity_lead",
        )
    return batch


# --------------------------------------------------------------------------
# The batch record
# --------------------------------------------------------------------------


def test_a_planned_batch_carries_its_budget_its_conditions_and_its_first_event():
    batch = a_batch()
    assert batch.status is BatchStatus.PLANNED
    assert batch.query_ids == (RACE, MACHINE)
    assert batch.candidate_ids == ()
    assert batch.observations == 0
    assert [event.kind for event in batch.history] == [BatchEventKind.CREATED]


def test_a_batch_with_no_stop_condition_is_refused_before_it_can_collect():
    with pytest.raises(ResearchError, match="declare when to stop before collecting"):
        a_batch(stop_conditions=())


def test_a_batch_with_no_declared_query_is_refused():
    with pytest.raises(ResearchError, match="belong to nothing"):
        a_batch(query_ids=())


def test_the_same_stop_condition_twice_is_refused_rather_than_silently_deduplicated():
    condition = StopCondition(reason=StopReason.MAX_OBSERVATIONS, threshold=40)
    with pytest.raises(ResearchError, match="declared twice"):
        a_batch(stop_conditions=(condition, condition))


def test_candidate_ids_are_derived_from_the_round_log_and_never_stored_beside_it():
    fields = {f.name for f in dataclasses.fields(ResearchBatch)}
    assert "candidate_ids" not in fields
    batch = rounds(collecting(), (RACE, 0, "c1", "c2"), (MACHINE, 1, "c2", "c3"))
    assert batch.candidate_ids == ("c1", "c2", "c3")
    assert batch.observations == 4


def test_a_round_that_observes_one_candidate_twice_is_a_capture_error():
    with pytest.raises(ResearchError, match="observes c1 twice"):
        DiscoveryRound(query_id=RACE, ran_on=TODAY, observed=("c1", "c2", "c1"))


def test_rounds_are_kept_in_the_order_collection_happened():
    with pytest.raises(ResearchError, match="Rounds are the order collection happened"):
        ResearchBatch(
            id="rb-x",
            objective="o",
            created=TODAY,
            owner="me",
            query_ids=(RACE,),
            budget=a_budget(),
            stop_conditions=(StopCondition(reason=StopReason.MAX_OBSERVATIONS, threshold=5),),
            rounds=(
                DiscoveryRound(query_id=RACE, ran_on=day(3)),
                DiscoveryRound(query_id=RACE, ran_on=day(1)),
            ),
        )


def test_a_status_that_the_history_does_not_replay_to_is_refused():
    batch = collecting()
    with pytest.raises(ResearchError, match="history replays to"):
        dataclasses.replace(batch, status=BatchStatus.COMPLETE)


def test_the_history_is_append_only_and_a_note_adds_without_changing_anything():
    batch = collecting()
    noted = note_batch(batch, on=day(1), by="lead", detail="Second query is slow to return.")
    assert noted.history[: len(batch.history)] == batch.history
    assert noted.history[-1].kind is BatchEventKind.NOTE
    assert noted.status is batch.status and noted.rounds == batch.rounds


def test_an_event_dated_before_the_last_one_cannot_be_appended():
    batch = rounds(collecting(), (RACE, 3, "c1"))
    with pytest.raises(ResearchError, match="before the last event"):
        note_batch(batch, on=day(1), by="lead", detail="late arrival")


# --------------------------------------------------------------------------
# The budget
# --------------------------------------------------------------------------


def test_a_budget_with_no_ceiling_and_no_deadline_is_not_a_budget():
    with pytest.raises(ResearchError, match="not a budget"):
        BatchBudget()


def test_a_ceiling_of_zero_is_refused_as_a_batch_that_may_not_start():
    with pytest.raises(ResearchError, match="may not start"):
        BatchBudget(max_unique_candidates=0)


def test_a_budget_cannot_allow_more_unique_candidates_than_observations():
    with pytest.raises(ResearchError, match="never be the binding one"):
        BatchBudget(max_candidate_observations=10, max_unique_candidates=20)


def test_a_budget_cannot_promote_more_candidates_than_it_may_find():
    with pytest.raises(ResearchError, match="Only a candidate can be promoted"):
        BatchBudget(max_unique_candidates=5, max_promoted_candidates=9)


def test_a_target_range_may_not_exceed_the_ceiling_it_is_planned_under():
    with pytest.raises(ResearchError, match="The plan cannot exceed the ceiling"):
        a_batch(
            budget=a_budget(max_unique_candidates=10),
            target=CandidateTarget(minimum=5, maximum=30),
        )


def test_an_empty_target_range_is_refused():
    with pytest.raises(ResearchError, match="minimum cannot exceed the maximum"):
        CandidateTarget(minimum=9, maximum=4)


def test_the_query_budget_refuses_a_round_from_one_query_too_many():
    batch = a_batch(budget=a_budget(max_queries=1), query_ids=(RACE, MACHINE))
    batch = rounds(collecting(batch), (RACE, 0, "c1"))
    with pytest.raises(ResearchError, match="past the budget's max_queries of 1"):
        record_round(
            batch, DiscoveryRound(query_id=MACHINE, ran_on=day(1), observed=("c2",)), by="lead"
        )


def test_the_candidate_ceiling_refuses_the_whole_round_rather_than_trimming_it():
    batch = a_batch(
        budget=a_budget(
            max_unique_candidates=3,
            max_candidate_observations=40,
            max_promoted_candidates=2,
        ),
        target=None,
    )
    batch = rounds(collecting(batch), (RACE, 0, "c1", "c2"))
    with pytest.raises(ResearchError, match="refused whole rather than trimmed"):
        record_round(
            batch,
            DiscoveryRound(query_id=RACE, ran_on=day(1), observed=("c3", "c4")),
            by="lead",
        )
    # Nothing was written: the batch the caller still holds is untouched.
    assert batch.candidate_ids == ("c1", "c2")


def test_the_observation_ceiling_is_counted_over_duplicates_too():
    batch = a_batch(
        budget=a_budget(
            max_candidate_observations=3,
            max_unique_candidates=3,
            max_promoted_candidates=2,
        ),
        target=None,
    )
    batch = rounds(collecting(batch), (RACE, 0, "c1", "c2"))
    with pytest.raises(ResearchError, match="max_candidate_observations"):
        record_round(
            batch,
            DiscoveryRound(query_id=MACHINE, ran_on=day(1), observed=("c1", "c2")),
            by="lead",
        )


def test_a_round_after_the_deadline_is_refused():
    batch = a_batch(budget=a_budget(deadline=day(1)))
    batch = collecting(batch)
    with pytest.raises(ResearchError, match="past the budget deadline"):
        record_round(
            batch, DiscoveryRound(query_id=RACE, ran_on=day(2), observed=("c1",)), by="lead"
        )


def test_a_round_cannot_be_recorded_against_a_batch_nobody_started():
    with pytest.raises(ResearchError, match="is not collecting"):
        record_round(
            a_batch(), DiscoveryRound(query_id=RACE, ran_on=TODAY, observed=("c1",)), by="lead"
        )


def test_a_round_from_an_undeclared_query_is_refused():
    with pytest.raises(ResearchError, match="does not declare query"):
        record_round(
            collecting(),
            DiscoveryRound(query_id="dq-unrelated", ran_on=TODAY, observed=("c1",)),
            by="lead",
        )


# --------------------------------------------------------------------------
# Stop conditions and escalation
# --------------------------------------------------------------------------


def test_a_counting_stop_condition_without_a_threshold_would_never_fire():
    with pytest.raises(ResearchError, match="needs a threshold"):
        StopCondition(reason=StopReason.MAX_OBSERVATIONS)


def test_a_saturation_condition_without_a_rule_has_nothing_to_test():
    with pytest.raises(ResearchError, match="must carry a SaturationRule"):
        StopCondition(reason=StopReason.SATURATION)


def test_a_deadline_condition_without_a_date_is_a_wish():
    with pytest.raises(ResearchError, match="must name the date"):
        StopCondition(reason=StopReason.DEADLINE)


def test_a_fired_condition_stops_the_next_round_and_names_both_remedies():
    batch = a_batch(
        stop_conditions=(StopCondition(reason=StopReason.MAX_UNIQUE_CANDIDATES, threshold=2),),
        target=None,
    )
    batch = rounds(collecting(batch), (RACE, 0, "c1", "c2"))
    with pytest.raises(ResearchError, match="escalate it with an authoriser"):
        record_round(
            batch, DiscoveryRound(query_id=RACE, ran_on=day(1), observed=("c3",)), by="lead"
        )


def test_a_fired_condition_stops_collecting_and_does_not_block_screening():
    """Reaching the candidate ceiling is the ceiling working, and the next thing
    a batch should do is screen what it found."""
    batch = a_batch(
        stop_conditions=(StopCondition(reason=StopReason.MAX_UNIQUE_CANDIDATES, threshold=2),),
        target=None,
    )
    batch = rounds(collecting(batch), (RACE, 0, "c1", "c2"))
    moved = advance_batch(
        batch,
        BatchStatus.SCREENING,
        on=day(1),
        by="lead",
        reason="Ceiling reached; screen what we have.",
    )
    assert moved.status is BatchStatus.SCREENING


def test_a_stop_records_which_condition_fired_before_it_records_the_decision():
    batch = a_batch(
        stop_conditions=(StopCondition(reason=StopReason.MAX_UNIQUE_CANDIDATES, threshold=2),),
        target=None,
    )
    batch = rounds(collecting(batch), (RACE, 0, "c1", "c2"))
    signals = evaluate_stop_conditions(batch, on=day(1))
    stopped = stop_batch(
        batch, on=day(1), by="lead", reason="Declared ceiling reached.", signals=signals
    )
    assert stopped.status is BatchStatus.STOPPED
    kinds = [event.kind for event in stopped.history[-2:]]
    assert kinds == [BatchEventKind.STOP_TRIGGERED, BatchEventKind.STATUS_CHANGED]
    assert "max_unique_candidates" in stopped.history[-2].detail


def test_a_stopped_batch_needs_an_escalation_before_it_collects_again():
    batch = rounds(collecting(), (RACE, 0, "c1"))
    batch = stop_batch(batch, on=day(1), by="lead", reason="Paused for review.")
    with pytest.raises(ResearchError, match="needs an escalation recorded after the stop"):
        advance_batch(batch, BatchStatus.COLLECTING, on=day(2), by="lead", reason="carry on")

    escalated = escalate_batch(
        batch,
        on=day(2),
        by="lead",
        reason="The niche is wider than the first query showed.",
        authorised_by="ceo",
    )
    resumed = advance_batch(
        escalated, BatchStatus.COLLECTING, on=day(2), by="lead", reason="Authorised."
    )
    assert resumed.status is BatchStatus.COLLECTING
    assert "authorised by ceo" in escalated.history[-1].detail


def test_an_escalation_that_raises_nothing_is_refused_when_it_supplies_a_budget():
    batch = collecting()
    with pytest.raises(ResearchError, match="raises no ceiling and extends no deadline"):
        escalate_batch(
            batch,
            on=day(1),
            by="lead",
            reason="more please",
            authorised_by="ceo",
            budget=a_budget(),
        )


def test_an_escalation_may_raise_a_ceiling_and_the_new_one_takes_effect():
    batch = a_batch(
        budget=a_budget(max_unique_candidates=2, max_promoted_candidates=1), target=None
    )
    batch = rounds(collecting(batch), (RACE, 0, "c1", "c2"))
    escalated = escalate_batch(
        batch,
        on=day(1),
        by="lead",
        reason="Two more queries are worth running.",
        authorised_by="ceo",
        budget=a_budget(max_unique_candidates=6, max_promoted_candidates=1),
    )
    grown = record_round(
        escalated,
        DiscoveryRound(query_id=RACE, ran_on=day(1), observed=("c3",)),
        by="lead",
    )
    assert grown.candidate_ids == ("c1", "c2", "c3")


def test_an_archived_batch_does_not_grow_a_history():
    archived = advance_batch(
        a_batch(), BatchStatus.ARCHIVED, on=day(1), by="lead", reason="Superseded."
    )
    with pytest.raises(ResearchError, match="does not grow a history"):
        escalate_batch(
            archived, on=day(2), by="lead", reason="one more look", authorised_by="ceo"
        )
    with pytest.raises(ResearchError, match="terminal"):
        advance_batch(archived, BatchStatus.COLLECTING, on=day(2), by="lead", reason="x")


def test_an_exceeded_ceiling_blocks_every_forward_move_until_somebody_raises_it():
    batch = a_batch(budget=a_budget(max_promoted_candidates=1), target=None)
    batch = rounds(collecting(batch), (RACE, 0, "c1", "c2"))
    outcomes = (
        an_outcome("c1", state=CandidateState.PROMOTED_TO_SOURCE, promoted_source_id="yt-1"),
        an_outcome("c2", state=CandidateState.PROMOTED_TO_SOURCE, promoted_source_id="yt-2"),
    )
    progress = batch_progress(batch, outcomes)
    assert progress.promoted_sources == 2
    with pytest.raises(ResearchError, match="spent past max_promoted_candidates"):
        advance_batch(
            batch,
            BatchStatus.SCREENING,
            on=day(1),
            by="lead",
            reason="on we go",
            progress=progress,
        )
    # Stopping is always available.
    assert stop_batch(batch, on=day(1), by="lead", reason="Over budget.").status is (
        BatchStatus.STOPPED
    )


def test_a_batch_does_not_reach_screening_by_declaration():
    with pytest.raises(ResearchError, match="recorded no discovery round"):
        advance_batch(collecting(), BatchStatus.SCREENING, on=TODAY, by="lead", reason="x")


def test_analysis_ready_needs_the_candidate_outcomes_and_a_screened_in_candidate():
    batch = rounds(collecting(), (RACE, 0, "c1"))
    batch = advance_batch(
        batch, BatchStatus.SCREENING, on=day(1), by="lead", reason="Screening starts."
    )
    with pytest.raises(ResearchError, match="needs the candidate outcomes"):
        advance_batch(batch, BatchStatus.ANALYSIS_READY, on=day(2), by="lead", reason="ready")
    with pytest.raises(ResearchError, match="no screened-in candidate"):
        advance_batch(
            batch,
            BatchStatus.ANALYSIS_READY,
            on=day(2),
            by="lead",
            reason="ready",
            progress=batch_progress(batch, (an_outcome("c1", state=CandidateState.SCREENED_OUT),)),
        )
    ready = advance_batch(
        batch,
        BatchStatus.ANALYSIS_READY,
        on=day(2),
        by="lead",
        reason="One case is worth an afternoon.",
        progress=batch_progress(batch, (an_outcome("c1", state=CandidateState.SCREENED_IN),)),
    )
    assert ready.status is BatchStatus.ANALYSIS_READY


def test_completing_requires_every_candidate_to_have_been_decided():
    batch = rounds(collecting(), (RACE, 0, "c1", "c2"))
    batch = advance_batch(batch, BatchStatus.SCREENING, on=day(1), by="lead", reason="screen")
    undecided = (
        an_outcome("c1", state=CandidateState.SCREENED_IN),
        an_outcome("c2", state=CandidateState.QUEUED),
    )
    batch = advance_batch(
        batch,
        BatchStatus.ANALYSIS_READY,
        on=day(2),
        by="lead",
        reason="one is ready",
        progress=batch_progress(batch, undecided),
    )
    with pytest.raises(ResearchError, match="candidate.s. nobody decided about"):
        advance_batch(
            batch,
            BatchStatus.COMPLETE,
            on=day(3),
            by="lead",
            reason="done",
            progress=batch_progress(batch, undecided),
        )


def test_stop_conditions_survive_a_round_trip_through_json():
    batch = rounds(collecting(), (RACE, 0, "c1"))
    restored = ResearchBatch.from_dict(__import__("json").loads(dumps(batch)))
    assert restored == batch
    assert restored.stop_conditions == batch.stop_conditions
    assert restored.saturation_rules == batch.saturation_rules
    assert dumps(restored) == dumps(batch)


# --------------------------------------------------------------------------
# Duplication, overlap and query performance
# --------------------------------------------------------------------------


def test_a_duplicate_is_counted_where_it_cost_something_at_the_observation():
    batch = rounds(
        collecting(),
        (RACE, 0, "c1", "c2", "c3"),
        (MACHINE, 1, "c2", "c3", "c4"),
    )
    metrics = duplication_metrics(batch)
    assert metrics.observations == 6
    assert metrics.unique_candidates == 4
    assert metrics.duplicate_observations == 2
    assert metrics.duplicate_rate == pytest.approx(2 / 6)
    assert metrics.multi_query_candidates == 2
    assert metrics.max_sightings == 2


def test_the_duplicate_rate_is_absent_rather_than_zero_when_nothing_was_observed():
    assert duplication_metrics(collecting()).duplicate_rate is None


def test_one_candidate_found_by_two_queries_is_one_candidate_and_two_observations():
    batch = rounds(collecting(), (RACE, 0, "c1"), (MACHINE, 1, "c1"))
    assert batch.candidate_ids == ("c1",)
    assert batch.observations == 2
    metrics = duplication_metrics(batch)
    assert metrics.multi_query_candidates == 1
    overlap = metrics.overlaps[0]
    assert (overlap.query_a, overlap.query_b) == (RACE, MACHINE)
    assert overlap.shared == 1 and overlap.jaccard == pytest.approx(1.0)


def test_the_brief_s_worked_example_gives_query_b_a_unique_contribution_of_five():
    a_only = [f"a{i}" for i in range(5)]
    shared = [f"s{i}" for i in range(15)]
    b_only = [f"b{i}" for i in range(5)]
    batch = a_batch(
        budget=a_budget(max_candidate_observations=80, max_unique_candidates=40),
        stop_conditions=(
            StopCondition(reason=StopReason.MAX_UNIQUE_CANDIDATES, threshold=40),
        ),
    )
    batch = rounds(
        collecting(batch),
        (RACE, 0, *a_only, *shared),
        (MACHINE, 1, *shared, *b_only),
    )
    race, machine = query_performance(batch, ())
    assert race.candidates == 20 and machine.candidates == 20
    assert race.shared == 15 and machine.shared == 15
    assert race.unique_contribution == 5
    assert machine.unique_contribution == 5
    assert machine.first_found == 5  # the fifteen shared were first seen by RACE
    assert machine.unique_share == pytest.approx(0.25)


def test_a_declared_query_that_never_ran_keeps_its_row_with_zeros():
    batch = rounds(collecting(), (RACE, 0, "c1"))
    race, machine = query_performance(batch, ())
    assert race.ran is True
    assert machine.ran is False and machine.observations == 0
    assert machine.unique_share is None
    assert batch.unrun_query_ids == (MACHINE,)


def test_query_performance_reports_how_many_of_its_candidates_had_no_record():
    batch = rounds(collecting(), (RACE, 0, "c1", "c2"))
    race, _ = query_performance(batch, (an_outcome("c1"),))
    assert race.candidates == 2
    assert race.unmatched_candidates == 1


def test_two_outcomes_for_one_candidate_are_refused_rather_than_one_winning():
    batch = rounds(collecting(), (RACE, 0, "c1"))
    with pytest.raises(ResearchError, match="two outcomes were supplied"):
        batch_progress(batch, (an_outcome("c1"), an_outcome("c1")))


# --------------------------------------------------------------------------
# Creator concentration
# --------------------------------------------------------------------------


def test_creator_concentration_is_surfaced_and_nothing_is_rejected_for_it():
    batch = rounds(collecting(), (RACE, 0, "c1", "c2", "c3", "c4"))
    outcomes = tuple(
        an_outcome(cid, creator_id=creator)
        for cid, creator in (
            ("c1", "chan-alpha"),
            ("c2", "chan-alpha"),
            ("c3", "chan-alpha"),
            ("c4", "chan-beta"),
        )
    )
    creators = creator_concentration(batch, outcomes)
    assert creators.unique_creators == 2
    assert creators.top_creator == "chan-alpha"
    assert creators.top_creator_candidates == 3
    assert creators.top_creator_share == pytest.approx(0.75)
    assert creators.counts == (("chan-alpha", 3), ("chan-beta", 1))


def test_an_unknown_creator_stays_unknown_and_is_left_out_of_the_share():
    batch = rounds(collecting(), (RACE, 0, "c1", "c2", "c3"))
    outcomes = (
        an_outcome("c1", creator_id="chan-alpha"),
        an_outcome("c2", creator_id="", creator=""),
        an_outcome("c3", creator_id="", creator=""),
    )
    creators = creator_concentration(batch, outcomes)
    assert creators.unknown_creator_candidates == 2
    assert creators.known_creator_candidates == 1
    assert creators.top_creator_share == pytest.approx(1.0)
    assert creators.creator_coverage == pytest.approx(1 / 3)


def test_a_candidate_with_no_record_at_all_counts_as_unknown_creator():
    batch = rounds(collecting(), (RACE, 0, "c1", "c2"))
    creators = creator_concentration(batch, (an_outcome("c1"),))
    assert creators.candidates == 2 and creators.unknown_creator_candidates == 1


def test_a_channel_id_wins_over_a_display_name_two_channels_could_share():
    outcome = an_outcome("c1", creator="Marble Time", creator_id="uc-123")
    assert outcome.creator_key == "uc-123"
    assert an_outcome("c2", creator="Marble Time", creator_id="").creator_key == "Marble Time"


def test_creator_share_is_absent_when_nobody_recorded_a_creator_at_all():
    batch = rounds(collecting(), (RACE, 0, "c1"))
    creators = creator_concentration(batch, (an_outcome("c1", creator_id="", creator=""),))
    assert creators.top_creator == "" and creators.top_creator_share is None


# --------------------------------------------------------------------------
# Tags
# --------------------------------------------------------------------------


def test_only_explicit_tags_are_counted_and_a_title_is_never_read():
    batch = rounds(collecting(), (RACE, 0, "c1", "c2"))
    outcomes = (
        an_outcome("c1", tags=("elimination", "race")),
        an_outcome("c2", tags=()),
    )
    coverage = tag_coverage(batch, outcomes)
    assert coverage.unique_tags == 2
    assert coverage.tagged_candidates == 1
    assert coverage.untagged_candidates == 1
    assert coverage.counts == (("elimination", 1), ("race", 1))
    assert coverage.tag_coverage == pytest.approx(0.5)


def test_a_new_tag_is_attributed_to_the_round_that_first_observed_it():
    batch = rounds(collecting(), (RACE, 0, "c1"), (MACHINE, 1, "c2"), (RACE, 2, "c3"))
    outcomes = (
        an_outcome("c1", tags=("race",)),
        an_outcome("c2", tags=("race", "elimination")),
        an_outcome("c3", tags=("race",)),
    )
    coverage = tag_coverage(batch, outcomes)
    assert coverage.new_tags_per_round == (1, 1, 0)
    assert dict(coverage.first_seen_round) == {"race": 0, "elimination": 1}


def test_the_metrics_module_never_reads_a_candidate_title():
    """Section 7: explicit signals only. The guard reads the syntax tree rather
    than the prose, because a tokenizer added later would pass every count-based
    test above and would mention none of the words a text search looks for."""
    tree = ast.parse(
        (PACKAGE / "research" / "batch_metrics.py").read_text(encoding="utf-8")
    )
    attributes = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert "title" not in attributes
    assert "signals" not in attributes  # free-text signals are not a tag vocabulary
    assert not attributes & {"split", "lower", "upper", "find", "startswith"}


# --------------------------------------------------------------------------
# Saturation
# --------------------------------------------------------------------------


def test_saturation_over_too_few_rounds_is_not_enough_evidence_not_not_yet():
    batch = rounds(collecting(), (RACE, 0, "c1"), (MACHINE, 1, "c2"))
    rule = SaturationRule(rounds=3, new_rate_below=0.25)
    signal = saturation_signal(rule, round_progress(batch, ()))
    assert signal.state is SaturationState.INSUFFICIENT_EVIDENCE
    assert signal.rounds_considered == 2 and signal.rounds_required == 3
    assert "not enough evidence yet" in signal.detail


def test_saturation_fires_only_when_every_round_in_the_window_is_below_the_rate():
    batch = rounds(
        collecting(),
        (RACE, 0, "c1", "c2", "c3", "c4"),
        (MACHINE, 1, "c1", "c2", "c3", "c5"),
        (RACE, 2, "c1", "c2", "c3", "c4"),
        (MACHINE, 3, "c1", "c2", "c3", "c5"),
    )
    history = round_progress(batch, ())
    assert [entry.new_unique_rate for entry in history] == [1.0, 0.25, 0.0, 0.0]

    strict = saturation_signal(SaturationRule(rounds=3, new_rate_below=0.25), history)
    assert strict.state is SaturationState.NOT_SATURATED  # round 1 is 0.25, not below it
    assert strict.rates == (0.25, 0.0, 0.0)

    window = saturation_signal(SaturationRule(rounds=2, new_rate_below=0.25), history)
    assert window.state is SaturationState.SATURATED
    assert window.rates == (0.0, 0.0)


def test_a_saturation_verdict_is_the_same_object_twice_and_carries_no_score():
    batch = rounds(collecting(), (RACE, 0, "c1", "c2"), (MACHINE, 1, "c1"), (RACE, 2, "c2"))
    rule = SaturationRule(rounds=2, new_rate_below=0.5)
    history = round_progress(batch, ())
    first = saturation_signal(rule, history)
    assert first == saturation_signal(rule, history)
    assert not hasattr(first, "score")
    assert first.threshold == 0.5


def test_a_round_that_observed_nothing_has_no_rate_and_blocks_a_verdict():
    batch = rounds(collecting(), (RACE, 0, "c1", "c2"), (MACHINE, 1), (RACE, 2, "c3"))
    history = round_progress(batch, ())
    assert history[1].new_unique_rate is None
    assert "the round observed nothing" in history[1].unavailable[0]

    signal = saturation_signal(SaturationRule(rounds=3, new_rate_below=0.9), history)
    assert signal.state is SaturationState.INSUFFICIENT_EVIDENCE
    assert signal.undetermined_rounds == (1,)


def test_a_creator_rate_is_absent_when_no_observation_named_a_creator():
    batch = rounds(collecting(), (RACE, 0, "c1", "c2"), (MACHINE, 1, "c3"))
    outcomes = (
        an_outcome("c1", creator_id="", creator=""),
        an_outcome("c2", creator_id="", creator=""),
        an_outcome("c3", creator_id="chan-alpha"),
    )
    history = round_progress(batch, outcomes)
    assert history[0].new_creator_rate is None
    assert history[1].new_creator_rate == pytest.approx(1.0)
    signal = saturation_signal(
        SaturationRule(rounds=2, new_rate_below=0.5, metric=SaturationMetric.NEW_CREATORS),
        history,
    )
    assert signal.state is SaturationState.INSUFFICIENT_EVIDENCE


def test_a_tag_rate_is_measured_over_the_observations_that_carried_a_tag():
    batch = rounds(collecting(), (RACE, 0, "c1", "c2"))
    outcomes = (an_outcome("c1", tags=("race",)), an_outcome("c2", tags=()))
    entry = round_progress(batch, outcomes)[0]
    assert entry.tagged_observations == 1
    assert entry.new_tag_rate == pytest.approx(1.0)
    assert entry.observations == 2


def test_a_saturation_rule_over_one_round_is_not_a_trend():
    with pytest.raises(ResearchError, match="is not a trend"):
        SaturationRule(rounds=1, new_rate_below=0.2)


def test_a_saturation_threshold_of_zero_could_never_fire():
    with pytest.raises(ResearchError, match="must be a fraction"):
        SaturationRule(rounds=3, new_rate_below=0.0)


def test_an_unevaluated_saturation_condition_reports_that_rather_than_false():
    batch = rounds(collecting(), (RACE, 0, "c1"))
    signals = evaluate_stop_conditions(batch, on=day(1))
    saturation = [s for s in signals if s.reason is StopReason.SATURATION][0]
    assert saturation.triggered is False
    assert "saturation was not evaluated" in saturation.detail


# --------------------------------------------------------------------------
# Screening queue
# --------------------------------------------------------------------------


def test_a_screening_judgement_without_evidence_or_a_reason_is_refused():
    with pytest.raises(ResearchError, match="evidence"):
        an_assessment("c1", evidence=())
    with pytest.raises(Exception, match="reason"):
        an_assessment("c1", reason="")


def test_a_screening_assessment_is_not_a_screening_decision():
    """The recommendation is what a reviewer thinks; `screen_candidate` is what
    the queue does, and it still takes its own person, date and reason."""
    assessment = an_assessment("c1")
    assert assessment.recommendation is ScreeningRecommendation.SCREEN_IN
    fields = {f.name for f in dataclasses.fields(ScreeningAssessment)}
    assert "state" not in fields and "to_state" not in fields
    text = (PACKAGE / "research" / "screening_queue.py").read_text(encoding="utf-8")
    assert "screen_candidate(" not in text  # it is named in prose, never called


def test_a_signal_outside_the_declared_vocabulary_cannot_be_compared_so_is_refused():
    with pytest.raises(ResearchError, match="not a screening signal"):
        an_assessment(
            "c1", scores=(DimensionScore(dimension="vibes", score=5, reason="felt right"),)
        )


def test_a_score_above_the_scale_is_refused():
    with pytest.raises(ResearchError, match="scale that stops at 5"):
        an_assessment(
            "c1", scores=(DimensionScore(dimension="relevance", score=9, reason="a lot"),)
        )


def test_an_unscored_candidate_keeps_its_place_at_the_bottom_of_the_queue():
    pairs = (("c1", CandidateState.QUEUED), ("c2", CandidateState.QUEUED))
    queue = screening_queue(pairs, (an_assessment("c1"),))
    assert [entry.candidate_id for entry in queue] == ["c1", "c2"]
    assert queue[1].status is QueueStatus.UNSCORED
    assert queue[1].assessed is False
    assert queue[1].missing_signals == SCREENING_SIGNALS


def test_a_partially_scored_candidate_never_sorts_above_a_fully_scored_one():
    pairs = (("c-high-partial", CandidateState.QUEUED), ("c-low-full", CandidateState.QUEUED))
    queue = screening_queue(
        pairs,
        (
            an_assessment(
                "c-high-partial", id="sa-partial", signals=("relevance",), score=5
            ),
            an_assessment("c-low-full", id="sa-full", score=2),
        ),
    )
    assert [entry.candidate_id for entry in queue] == ["c-low-full", "c-high-partial"]
    assert queue[0].status is QueueStatus.SCORED
    assert queue[1].status is QueueStatus.PARTIALLY_SCORED
    assert queue[1].coverage == pytest.approx(0.2)


def test_the_queue_orders_on_the_mean_not_the_total_so_more_boxes_is_not_better():
    four_fours = an_assessment("c-four", id="sa-four", signals=SCREENING_SIGNALS[:4], score=4)
    three_fives = an_assessment("c-five", id="sa-five", signals=SCREENING_SIGNALS[:3], score=5)
    assert four_fours.signal_total == 16 and three_fives.signal_total == 15
    queue = screening_queue(
        (("c-four", CandidateState.QUEUED), ("c-five", CandidateState.QUEUED)),
        (four_fours, three_fives),
    )
    assert [entry.candidate_id for entry in queue] == ["c-five", "c-four"]


def test_two_identical_candidates_come_back_in_id_order_every_time():
    pairs = tuple((f"c{i}", CandidateState.QUEUED) for i in range(5))
    cards = tuple(an_assessment(f"c{i}", score=3) for i in range(5))
    once = screening_queue(pairs, cards)
    twice = screening_queue(tuple(reversed(pairs)), tuple(reversed(cards)))
    assert [e.candidate_id for e in once] == [e.candidate_id for e in twice]
    assert [e.candidate_id for e in once] == ["c0", "c1", "c2", "c3", "c4"]


def test_a_candidate_reviewed_twice_keeps_both_records_and_the_queue_reads_the_later():
    early = an_assessment("c1", id="sa-early", reviewed_on=TODAY, score=1)
    late = an_assessment("c1", id="sa-late", reviewed_on=day(3), score=5)
    queue = screening_queue((("c1", CandidateState.QUEUED),), (early, late))
    assert queue[0].assessment_id == "sa-late"
    assert queue[0].signal_mean == pytest.approx(5.0)


def test_the_queue_holds_candidates_whose_decision_is_still_ahead_of_them():
    pairs = (
        ("c-open", CandidateState.QUEUED),
        ("c-out", CandidateState.SCREENED_OUT),
        ("c-promoted", CandidateState.PROMOTED_TO_SOURCE),
    )
    queue = screening_queue(pairs, ())
    assert [entry.candidate_id for entry in queue] == ["c-open"]


def test_incomplete_screening_coverage_is_visible_over_the_whole_batch():
    pairs = tuple((f"c{i}", CandidateState.QUEUED) for i in range(4))
    coverage = screening_coverage(
        pairs,
        (
            an_assessment("c0"),
            an_assessment("c1", id="sa-partial", signals=("relevance", "channel_fit")),
        ),
    )
    assert coverage.candidates == 4
    assert coverage.assessed == 2 and coverage.unassessed == 2
    assert coverage.fully_scored == 1 and coverage.partially_scored == 1
    assert coverage.assessed_fraction == pytest.approx(0.5)
    assert coverage.mean_coverage == pytest.approx((1.0 + 0.4) / 2)
    assert dict(coverage.signal_coverage)["relevance"] == 2
    assert dict(coverage.signal_coverage)["novelty_potential"] == 1
    assert coverage.reviewers == ("research_screener",)


# --------------------------------------------------------------------------
# The funnel
# --------------------------------------------------------------------------


def test_funnel_counts_enter_and_exit_each_tier_and_the_exits_chain():
    batch = rounds(collecting(), (RACE, 0, "c1", "c2", "c3"), (MACHINE, 1, "c1", "c4"))
    outcomes = (
        an_outcome(
            "c1",
            state=CandidateState.PROMOTED_TO_SOURCE,
            promoted_source_id="yt-1",
            reference_case_ids=("rc-1",),
            opportunity_ids=("op-1",),
        ),
        an_outcome("c2", state=CandidateState.SCREENED_OUT),
        an_outcome("c3", state=CandidateState.QUEUED),
        an_outcome("c4", state=CandidateState.DISCOVERED),
    )
    counts = {tier.tier: tier for tier in funnel_counts(batch, outcomes)}
    identity = counts[CostTier.IDENTITY]
    assert (identity.entered, identity.exited) == (5, 4)
    assert identity.stopped == 1  # one observation deduplicated away
    assert counts[CostTier.PUBLIC_METADATA].entered == 4
    assert counts[CostTier.SCREENING].entered == 3  # c4 never left DISCOVERED
    assert counts[CostTier.SCREENING].exited == 1
    assert counts[CostTier.REFERENCE_ANALYSIS].entered == 1
    assert counts[CostTier.OPPORTUNITY_DOSSIER].entered == 1
    assert counts[CostTier.PROTOTYPE_RECOMMENDATION].exited == 0
    for spec, tier in zip(funnel_counts(batch, outcomes), funnel_counts(batch, outcomes)[1:]):
        assert spec.exited == tier.entered


def test_an_archived_candidate_still_counts_as_having_bought_the_tier_it_reached():
    batch = rounds(collecting(), (RACE, 0, "c1"))
    archived = an_outcome(
        "c1",
        state=CandidateState.ARCHIVED,
        reached=(
            CandidateState.DISCOVERED,
            CandidateState.QUEUED,
            CandidateState.SCREENED_IN,
            CandidateState.ARCHIVED,
        ),
    )
    counts = {tier.tier: tier for tier in funnel_counts(batch, (archived,))}
    assert counts[CostTier.SCREENING].entered == 1
    assert batch_progress(batch, (archived,)).archived == 1


def test_outcome_of_replays_the_screening_history_rather_than_reading_the_state():
    """An archived candidate's state says `archived` and loses the fact that
    somebody screened it in; `reached` is what the funnel counts are read off."""
    candidate = a_candidate_record(0, queries=(RACE,))
    candidate = queue_candidate(candidate, on=TODAY, by="lead", reason="Adjacent format.")
    candidate = screen_candidate(
        candidate, CandidateState.SCREENED_IN, on=TODAY, by="lead", reason="Worth it."
    )
    candidate = screen_candidate(
        candidate,
        CandidateState.ARCHIVED,
        on=day(1),
        by="lead",
        reason="Superseded by a better example from the same channel.",
    )
    outcome = outcome_of(candidate)
    assert outcome.state is CandidateState.ARCHIVED
    assert CandidateState.SCREENED_IN in outcome.reached
    assert CandidateState.DISCOVERED in outcome.reached
    assert outcome.creator_key == "uc-marble-time"
    assert outcome.tags == ("race",)
    assert outcome.is_promoted is False
    assert outcome.reference_case_ids == ()


def test_a_funnel_pass_rate_over_an_empty_tier_is_absent():
    counts = {tier.tier: tier for tier in funnel_counts(collecting(), ())}
    assert counts[CostTier.REFERENCE_ANALYSIS].pass_rate is None


# --------------------------------------------------------------------------
# Cost accounting
# --------------------------------------------------------------------------


def test_a_resource_record_that_measures_nothing_is_refused():
    with pytest.raises(ResearchError, match="measures nothing"):
        a_resource(manual_minutes=None)


def test_a_reasoning_unit_count_in_an_unnamed_quantisation_is_refused():
    with pytest.raises(ResearchError, match="unknown unit"):
        a_resource(reasoning_units=1200)


def test_a_cost_total_is_absent_unless_every_record_supplied_the_field():
    cost = summarise_cost(
        (
            a_resource(id="rr-1", manual_minutes=60, tool_calls=4),
            a_resource(id="rr-2", manual_minutes=30),
        )
    )
    assert cost.manual_minutes == 90
    assert cost.tool_calls is None
    assert any("tool_calls: 1 of 2" in item for item in cost.missing)


def test_two_quantisations_of_reasoning_units_are_not_added_together():
    cost = summarise_cost(
        (
            a_resource(id="rr-1", reasoning_units=1000, usage_unit=UsageUnit.TOKEN),
            a_resource(id="rr-2", reasoning_units=4000, usage_unit=UsageUnit.CHARACTER),
        )
    )
    assert cost.reasoning_units is None
    assert cost.usage_unit is UsageUnit.UNKNOWN
    assert any("mixes usage units" in item for item in cost.missing)


def test_cost_metrics_are_missing_when_nobody_measured_the_cost():
    cost = summarise_cost(())
    efficiency = cost_efficiency(cost, {"unique_candidate": 20})
    assert efficiency.computed == ()
    assert any(
        "manual_minutes_per_unique_candidate: no manual_minutes was recorded" in item
        for item in efficiency.unavailable
    )


def test_a_batch_with_no_resource_record_says_so_once_and_not_six_times():
    cost = summarise_cost(())
    assert cost.records == 0
    assert cost.measured == ()
    assert cost.missing == (
        "no resource record was written for this batch, so nothing it cost is known",
    )


def test_cost_metrics_are_correct_when_both_halves_were_supplied():
    cost = summarise_cost((a_resource(manual_minutes=90),))
    efficiency = cost_efficiency(
        cost, {"unique_candidate": 30, "screened_in_candidate": 6, "promoted_source": 3}
    )
    assert efficiency.ratio("manual_minutes", "unique_candidate").value == pytest.approx(3.0)
    assert efficiency.ratio("manual_minutes", "screened_in_candidate").value == pytest.approx(15.0)
    assert efficiency.ratio("manual_minutes", "promoted_source").value == pytest.approx(30.0)


def test_a_ratio_over_zero_useful_outcomes_is_a_sentence_not_an_infinity():
    cost = summarise_cost((a_resource(manual_minutes=90),))
    efficiency = cost_efficiency(cost, {"unique_candidate": 10, "opportunity": 0})
    ratio = efficiency.ratio("manual_minutes", "opportunity")
    assert ratio.value is None
    assert "produced no opportunity to divide by" in ratio.unavailable


def test_cost_is_split_by_the_funnel_tier_that_consumed_it():
    cost = summarise_cost(
        (
            a_resource(id="rr-1", tier=CostTier.PUBLIC_METADATA, manual_minutes=40),
            a_resource(id="rr-2", tier=CostTier.SCREENING, manual_minutes=200),
            a_resource(id="rr-3", tier=CostTier.SCREENING, manual_minutes=100),
        )
    )
    by_tier = {entry.tier: entry for entry in cost.by_tier}
    assert by_tier[CostTier.SCREENING].manual_minutes == 300
    assert by_tier[CostTier.SCREENING].records == 2
    assert by_tier[CostTier.PUBLIC_METADATA].manual_minutes == 40


def test_the_cost_denominators_come_from_progress_and_nowhere_else():
    batch = rounds(collecting(), (RACE, 0, "c1", "c2"))
    progress = batch_progress(
        batch,
        (
            an_outcome("c1", state=CandidateState.PROMOTED_TO_SOURCE, promoted_source_id="yt-1"),
            an_outcome("c2", state=CandidateState.SCREENED_OUT),
        ),
    )
    assert cost_denominators(progress) == {
        "unique_candidate": 2,
        "screened_in_candidate": 1,
        "promoted_source": 1,
        "opportunity": 0,
    }


def test_an_unknown_cost_denominator_is_refused_rather_than_ignored():
    with pytest.raises(ResearchError, match="unknown cost denominator"):
        cost_efficiency(summarise_cost(()), {"views": 1000})


# --------------------------------------------------------------------------
# The report
# --------------------------------------------------------------------------


def a_reported_batch():
    batch = rounds(
        collecting(),
        (RACE, 0, "c1", "c2", "c3", "c4"),
        (MACHINE, 1, "c3", "c4", "c5"),
        (RACE, 2, "c1", "c2", "c3", "c4"),
    )
    outcomes = (
        an_outcome(
            "c1",
            state=CandidateState.PROMOTED_TO_SOURCE,
            promoted_source_id="yt-1",
            reference_case_ids=("rc-1",),
            opportunity_ids=("op-1",),
        ),
        an_outcome("c2", state=CandidateState.SCREENED_IN),
        an_outcome("c3", state=CandidateState.SCREENED_OUT, creator_id="chan-beta"),
        an_outcome("c4", state=CandidateState.QUEUED, creator_id="", tags=()),
        an_outcome("c5", state=CandidateState.DISCOVERED, tags=("elimination",)),
    )
    assessments = (an_assessment("c2"), an_assessment("c4", id="sa-c4", signals=("relevance",)))
    resources = (
        a_resource(id="rr-1", tier=CostTier.PUBLIC_METADATA, manual_minutes=45, search_calls=3),
        a_resource(id="rr-2", tier=CostTier.SCREENING, manual_minutes=30, search_calls=0),
    )
    return batch, outcomes, assessments, resources


def test_the_batch_report_is_the_same_bytes_twice():
    batch, outcomes, assessments, resources = a_reported_batch()
    first = build_batch_report(batch, outcomes, assessments, resources, as_of=day(2))
    second = build_batch_report(batch, outcomes, assessments, resources, as_of=day(2))
    assert first == second
    assert dumps(first) == dumps(second)
    assert first.lines() == second.lines()


def test_the_report_carries_the_numbers_a_research_lead_asked_for():
    batch, outcomes, assessments, resources = a_reported_batch()
    report = build_batch_report(batch, outcomes, assessments, resources, as_of=day(2))
    assert report.progress.observations == 11
    assert report.progress.unique_candidates == 5
    assert report.duplication.duplicate_rate == pytest.approx(6 / 11)
    assert report.creators.unknown_creator_candidates == 1
    assert report.tags.untagged_candidates == 1
    assert report.screening.unassessed == 3
    assert report.progress.promoted_sources == 1
    assert report.cost.manual_minutes == 75
    assert report.efficiency.ratio("manual_minutes", "unique_candidate").value == pytest.approx(15.0)
    assert [q.query_id for q in report.queries] == [RACE, MACHINE]
    assert report.on_target is False  # five candidates against a target of eight


def test_the_report_names_every_measurement_nobody_made():
    batch, outcomes, assessments, resources = a_reported_batch()
    report = build_batch_report(batch, outcomes, assessments, resources, as_of=day(2))
    joined = " | ".join(report.missing_measurements)
    assert "no creator recorded" in joined
    assert "carry no tag" in joined
    assert "no screening assessment" in joined
    assert "candidates_processed" in joined
    assert report.caveat and report.queue_caveat


def test_the_report_reports_a_candidate_it_has_no_record_for():
    batch = rounds(collecting(), (RACE, 0, "c1", "c2"))
    report = build_batch_report(batch, (an_outcome("c1"),), as_of=day(1))
    assert report.unmatched_candidates == ("c2",)
    assert "no candidate record supplied" in report.missing_measurements[0]


def test_the_report_refuses_a_cost_charged_to_another_batch():
    batch, outcomes, _, _ = a_reported_batch()
    with pytest.raises(ResearchError, match="charged to batch"):
        build_batch_report(
            batch, outcomes, (), (a_resource(batch_id="rb-other"),), as_of=day(2)
        )


def test_the_report_refuses_an_assessment_from_another_batch():
    batch, outcomes, _, _ = a_reported_batch()
    with pytest.raises(ResearchError, match="belongs to batch"):
        build_batch_report(
            batch, outcomes, (an_assessment("c1", batch_id="rb-other"),), (), as_of=day(2)
        )


def test_the_report_evaluates_stop_conditions_and_acts_on_none_of_them():
    batch = a_batch(
        stop_conditions=(StopCondition(reason=StopReason.MAX_OBSERVATIONS, threshold=2),),
        target=None,
    )
    batch = rounds(collecting(batch), (RACE, 0, "c1", "c2"))
    report = build_batch_report(batch, (), (), (), as_of=day(1))
    assert [signal.reason for signal in report.halting] == [StopReason.MAX_OBSERVATIONS]
    assert report.status is BatchStatus.COLLECTING  # the report changed nothing


def test_a_deadline_condition_fires_on_the_day_it_names():
    batch = a_batch(
        stop_conditions=(StopCondition(reason=StopReason.DEADLINE, deadline=day(5)),),
    )
    before = evaluate_stop_conditions(batch, on=day(4))
    after = evaluate_stop_conditions(batch, on=day(5))
    assert before[0].triggered is False
    assert after[0].triggered is True


# --------------------------------------------------------------------------
# The store
# --------------------------------------------------------------------------


def a_query_record(query_id: str) -> DiscoveryQuery:
    return DiscoveryQuery(
        id=query_id,
        platform="youtube",
        objective="Find marble-run formats whose loop renews without narration.",
        terms=("marble race",),
        created=TODAY,
        author="research_opportunity_lead",
    )


def a_candidate_record(index: int, *, queries: tuple[str, ...], **overrides) -> DiscoveryCandidate:
    canonical = canonicalize(f"https://youtu.be/vid{index:08d}")
    data = dict(
        id=candidate_id_for(canonical.identity),
        platform=canonical.platform,
        original_url=canonical.original,
        canonical_url=canonical.url,
        external_id=canonical.external_id,
        discovered_on=TODAY,
        discovered_by="research_opportunity_lead",
        capture_method=CaptureMethod.MANUAL_BROWSER,
        evidence=an_evidence(),
        provenance=tuple(
            DiscoveryProvenance(query_id=q, discovered_on=TODAY) for q in queries
        ),
        title=f"A marble race, number {index}",
        creator="Marble Time",
        creator_id="uc-marble-time",
        tags=("race",),
    )
    data.update(overrides)
    return DiscoveryCandidate(**data)


def a_populated_store(tmp_path, *, count: int = 3):
    store = ResearchStore(tmp_path)
    store.add(a_query_record(RACE))
    store.add(a_query_record(MACHINE))
    ids = []
    for index in range(count):
        candidate = a_candidate_record(index, queries=(RACE,))
        store.ingest(candidate)
        ids.append(candidate.id)
    batch = rounds(collecting(), (RACE, 0, *ids))
    store.add(batch)
    return store, batch, tuple(ids)


def test_a_batch_round_trips_through_the_store_and_is_never_silently_overwritten(tmp_path):
    store, batch, _ = a_populated_store(tmp_path)
    assert store.get(ResearchBatch.kind, batch.id) == batch
    with pytest.raises(ResearchError, match="already exists"):
        store.add(batch)
    updated = note_batch(batch, on=day(1), by="lead", detail="Second query still to run.")
    store.add(updated, overwrite=True)
    assert len(store.get(ResearchBatch.kind, batch.id).history) == len(batch.history) + 1


def test_a_clean_store_reports_no_integrity_issue(tmp_path):
    store, _, _ = a_populated_store(tmp_path)
    assert store.integrity() == ()


def test_integrity_detects_a_batch_naming_a_query_that_does_not_exist(tmp_path):
    store, batch, ids = a_populated_store(tmp_path)
    store.path_for(DiscoveryQuery.kind, MACHINE).unlink()
    problems = [i.problem for i in store.integrity() if i.record_id == batch.id]
    assert any("declares unknown discovery query" in p for p in problems)


def test_integrity_detects_a_batch_round_observing_a_candidate_nobody_holds(tmp_path):
    store, batch, ids = a_populated_store(tmp_path)
    dangling = rounds(batch, (RACE, 1, "cand-youtube-deadbeef"))
    store.add(dangling, overwrite=True)
    problems = [i.problem for i in store.integrity() if i.record_id == batch.id]
    assert any("observed unknown candidate" in p for p in problems)


def test_integrity_detects_a_candidate_charged_to_a_query_its_provenance_never_names(tmp_path):
    """The one a record cannot notice about itself: the round log and the
    candidate's provenance are two accounts of the same event."""
    store, batch, ids = a_populated_store(tmp_path)
    mischarged = rounds(batch, (MACHINE, 1, ids[0]))
    store.add(mischarged, overwrite=True)
    problems = [i.problem for i in store.integrity() if i.record_id == batch.id]
    assert any("not in that candidate's provenance" in p for p in problems)


def test_integrity_detects_a_screening_record_for_a_candidate_nobody_holds(tmp_path):
    store, batch, _ = a_populated_store(tmp_path)
    store.add(an_assessment("cand-youtube-nothing", batch_id=batch.id))
    problems = [i.problem for i in store.integrity() if i.kind == "screening_assessment"]
    assert any("unknown discovery candidate" in p for p in problems)
    assert any("never observed" in p for p in problems)


def test_integrity_detects_a_resource_record_charged_to_no_batch(tmp_path):
    store, _, _ = a_populated_store(tmp_path)
    store.add(a_resource(batch_id="rb-does-not-exist"))
    problems = [i.problem for i in store.integrity() if i.kind == "research_resource"]
    assert any("not a research batch" in p for p in problems)


def test_integrity_detects_a_promotion_count_the_store_does_not_support(tmp_path):
    store, batch, ids = a_populated_store(tmp_path)
    candidate = store.get(DiscoveryCandidate.kind, ids[0])
    candidate = queue_candidate(candidate, on=TODAY, by="lead", reason="Adjacent format.")
    candidate = screen_candidate(
        candidate,
        CandidateState.SCREENED_IN,
        on=TODAY,
        by="lead",
        reason="The loop renews without narration.",
    )
    candidate = screen_candidate(
        candidate,
        CandidateState.PROMOTED_TO_SOURCE,
        on=TODAY,
        by="lead",
        reason="Worth an afternoon.",
        promoted_source_id="yt-marble-one",
    )
    store.add(candidate, overwrite=True)
    problems = [i.problem for i in store.integrity() if i.record_id == batch.id]
    assert any("say they were promoted, but 0 source" in p for p in problems)


def a_confidence() -> ResearchConfidence:
    return ResearchConfidence(
        level=ConfidenceLevel.WEAK,
        basis="One public page, read once, with the counts it showed that day.",
        freshness=Freshness.TIME_SENSITIVE,
        observed_on=TODAY,
        would_change_if=("The channel stops publishing this format for two months.",),
        source_quality=SourceQuality.PLATFORM_PUBLIC,
    )


def promote_through_the_store(store, candidate_id: str, source_id: str):
    candidate = store.get(DiscoveryCandidate.kind, candidate_id)
    candidate = queue_candidate(candidate, on=TODAY, by="lead", reason="Adjacent format.")
    candidate = screen_candidate(
        candidate,
        CandidateState.SCREENED_IN,
        on=TODAY,
        by="lead",
        reason="The loop renews at every junction.",
    )
    store.add(candidate, overwrite=True)
    return store.promote(
        candidate_id,
        source_id=source_id,
        source_type=SourceType.COMPETITOR_VIDEO,
        rights=RightsStatus.LINK_ONLY,
        confidence=a_confidence(),
        promoted_by="lead",
        on=TODAY,
        reason="Worth a reference case.",
    )


def test_integrity_detects_a_limit_spent_past_without_a_stop_or_an_escalation(tmp_path):
    store = ResearchStore(tmp_path)
    store.add(a_query_record(RACE))
    store.add(a_query_record(MACHINE))
    ids = []
    for index in range(2):
        candidate = a_candidate_record(index, queries=(RACE,))
        store.ingest(candidate)
        ids.append(candidate.id)
    batch = a_batch(budget=a_budget(max_promoted_candidates=1), target=None)
    store.add(rounds(collecting(batch), (RACE, 0, *ids)))
    for index, candidate_id in enumerate(ids):
        promote_through_the_store(store, candidate_id, f"yt-marble-{index}")

    assert store.batch_progress(batch.id).promoted_sources == 2
    problems = [i.problem for i in store.integrity() if i.record_id == batch.id]
    assert any("spent past max_promoted_candidates" in p for p in problems)

    escalated = store.escalate_batch(
        batch.id,
        on=day(1),
        by="lead",
        reason="Both are worth an afternoon; the ceiling was set too low.",
        authorised_by="ceo",
        budget=a_budget(max_promoted_candidates=4),
    )
    assert escalated.budget.max_promoted_candidates == 4
    assert not [
        i for i in store.integrity() if "spent past" in i.problem
    ]


def test_the_store_assembles_the_report_and_the_queue(tmp_path):
    store, batch, ids = a_populated_store(tmp_path)
    store.add(an_assessment(ids[0], batch_id=batch.id, id="sa-first"))
    report = store.batch_report(batch.id, as_of=day(1))
    assert report.batch_id == batch.id
    assert report.progress.unique_candidates == len(ids)
    assert report.unmatched_candidates == ()
    queue = store.batch_queue(batch.id)
    assert [entry.candidate_id for entry in queue][0] == ids[0]
    assert store.batch_stop_signals(batch.id, on=day(1))


def test_the_store_records_a_round_and_advances_with_the_evidence_it_assembles(tmp_path):
    store, batch, ids = a_populated_store(tmp_path)
    extra = a_candidate_record(9, queries=(MACHINE,))
    store.ingest(extra)
    grown = store.record_round(
        batch.id,
        DiscoveryRound(query_id=MACHINE, ran_on=day(1), observed=(extra.id,)),
        by="lead",
    )
    assert len(grown.candidate_ids) == len(ids) + 1
    moved = store.advance_batch(
        batch.id, BatchStatus.SCREENING, on=day(2), by="lead", reason="Enough to screen."
    )
    assert moved.status is BatchStatus.SCREENING
    assert store.get(ResearchBatch.kind, batch.id).status is BatchStatus.SCREENING


def test_the_store_stops_a_batch_with_the_condition_that_fired(tmp_path):
    store = ResearchStore(tmp_path)
    store.add(a_query_record(RACE))
    store.add(a_query_record(MACHINE))
    candidate = a_candidate_record(0, queries=(RACE,))
    store.ingest(candidate)
    batch = a_batch(
        stop_conditions=(StopCondition(reason=StopReason.MAX_UNIQUE_CANDIDATES, threshold=1),),
        target=None,
    )
    store.add(rounds(collecting(batch), (RACE, 0, candidate.id)))
    stopped = store.stop_batch(batch.id, on=day(1), by="lead", reason="Ceiling reached.")
    assert stopped.status is BatchStatus.STOPPED
    assert "max_unique_candidates" in stopped.history[-2].detail


# --------------------------------------------------------------------------
# The research capsule
# --------------------------------------------------------------------------


def test_the_research_capsule_stays_within_budget_with_the_batch_layer_in_it():
    index = CapsuleIndex.load(SEED_ROOT)
    capsule = index.get("company-research-intelligence")
    assert capsule.size_chars() <= DEFAULT_BUDGET.max_capsule_chars
    # The capsule also claims the package-level namespace init; see
    # tests/test_company_os_capsules.py for the canonical ownership assertion.
    assert capsule.owns_paths == ("intelligence/__init__.py", "intelligence/research")
    assert "tests/test_company_os_research_batches.py" in capsule.tests


def test_the_research_capsule_states_the_batch_invariant_and_stays_consistent():
    index = CapsuleIndex.load(SEED_ROOT)
    capsule = index.get("company-research-intelligence")
    text = " ".join(capsule.invariants).lower()
    assert "network" in text
    assert "escalat" in text or "ceiling" in text
    assert index.integrity(repo_root=REPO_ROOT) == ()
    assert not capsule.is_stale(TODAY)


def test_one_research_capsule_still_covers_the_package():
    index = CapsuleIndex.load(SEED_ROOT)
    owners = [c.id for c in index.all() if "intelligence/research" in c.owns_paths]
    assert owners == ["company-research-intelligence"]


# --------------------------------------------------------------------------
# Guards
# --------------------------------------------------------------------------


_ALLOWED_IMPORTS = frozenset(
    {
        "__future__",
        "ai_platform",
        "argparse",
        "dataclasses",
        "datetime",
        "enum",
        "intelligence",
        "json",
        "knowledge",
        "pathlib",
        "re",
        "sys",
        "typing",
    }
)

_PRODUCTION_DIRS = (
    "audio",
    "engine",
    "entities",
    "evaluation",
    "marble3d",
    "modes",
    "powers",
    "production",
    "race",
    "rendering",
    "replay",
    "sloped",
    "tools",
)

# `_PRODUCTION_DIRS` names roots, not owners: every race, fight and V30 module
# lives under one of them, but a root may also hold a package that has nothing
# to do with any of them. A path listed below is separately owned and purely
# additive, so a *new* file under it changes no race/fight/V30 code. Modifying
# or deleting anything under a production root - this path included - stays a
# violation, and so does adding a file anywhere else under one.
_ADDITIVE_PRODUCTION_PATHS = ("tools/youtube_fetch/", "tools/engineering_runner/")


def _production_changes(name_status):
    """The (status, path) pairs of a --name-status diff that touch race, fight
    or V30 code: anything modified or deleted under a production root, plus any
    file added under one outside the additive paths above.

    A rename reports two paths - the source went away, the destination is new -
    and a copy leaves its source untouched.
    """
    roots = tuple(f"{d}/" for d in _PRODUCTION_DIRS)
    offending = []
    for line in name_status.splitlines():
        if not line.strip():
            continue
        fields = line.split("\t")
        code = fields[0][:1]
        if code == "R" and len(fields) == 3:
            changes = [("D", fields[1]), ("A", fields[2])]
        elif code == "C" and len(fields) == 3:
            changes = [("A", fields[2])]
        else:
            changes = [(code, fields[1])]
        for status, path in changes:
            if not path.startswith(roots):
                continue
            if status == "A" and path.startswith(_ADDITIVE_PRODUCTION_PATHS):
                continue
            offending.append((status, path))
    return offending


def test_the_batch_layer_added_no_dependency_and_no_production_import():
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                roots = [(node.module or "").split(".")[0]]
            else:
                continue
            for root in roots:
                assert root in _ALLOWED_IMPORTS, f"{path.name} imports {root!r}"


def test_no_production_module_imports_the_research_layer():
    for directory in _PRODUCTION_DIRS:
        base = REPO_ROOT / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            assert "intelligence.research" not in text, path
            assert "from intelligence" not in text, path


def test_this_branch_changed_no_race_fight_or_v30_code():
    diff = subprocess.run(
        ["git", "diff", "--name-status", "origin/main...HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if diff.returncode != 0:
        pytest.skip("no origin/main to compare against")
    assert _production_changes(diff.stdout) == []


def test_the_branch_guard_still_refuses_race_fight_and_v30_changes():
    """A new separately owned package under a production root is additive; the
    guard still refuses every other change under one, including a rename away
    and a path that merely starts like the additive one."""
    tab = "\t"
    for line in (
        "M" + tab + "tools/race2_render.py",
        "D" + tab + "tools/sloped_short.py",
        "M" + tab + "sloped/cameras.py",
        "A" + tab + "tools/race3_render.py",
        "A" + tab + "sloped/newthing.py",
        "A" + tab + "tools/youtube_fetch_evil.py",
        "M" + tab + "tools/youtube_fetch/api.py",
        "R100" + tab + "tools/race2_render.py" + tab + "tools/race2_moved.py",
    ):
        assert _production_changes(line), line
    for line in (
        "A" + tab + "tools/youtube_fetch/api.py",
        "A" + tab + "company/youtube/ingest.py",
        "M" + tab + ".gitignore",
    ):
        assert _production_changes(line) == [], line


def test_the_no_subagent_rule_is_exactly_where_it_was():
    """This branch added a batch-management layer; it did not touch rule 2."""
    with pytest.raises(SubagentPolicyViolation):
        ExecutionPolicy(no_subagents=False)
    with pytest.raises(SubagentPolicyViolation):
        ExecutionPolicy(nested_agent_spawning=True)
    with pytest.raises(ValidationError):
        enforce_no_subagents({"no_subagents": False})
    assert ExecutionPolicy().no_subagents is True


def test_nothing_in_the_package_reaches_the_network_or_a_model():
    banned = (
        "urllib",
        "requests",
        "httpx",
        "http.client",
        "socket",
        "selenium",
        "playwright",
        "yt_dlp",
        "youtube",
        "openai",
        "anthropic",
        "webbrowser",
        "subprocess",
        "numpy",
        "sklearn",
        "torch",
    )
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                assert not name.startswith(banned), f"{path.name} imports {name!r}"


def test_no_scheduler_or_autonomous_vocabulary_entered_the_package():
    """The batch layer records cost and workflow; it runs neither."""
    banned = ("def crawl", "def schedule_", "asyncio", "threading", "def auto_screen")
    for path in sorted(PACKAGE.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for phrase in banned:
            assert phrase not in text, f"{path.name} mentions {phrase!r}"


def test_every_budget_ceiling_is_wired_to_exactly_one_progress_number():
    from intelligence.research.batch_control import LIMIT_FIELD, BatchProgress

    assert set(LIMIT_FIELD) == set(HARD_LIMITS)
    fields = {f.name for f in dataclasses.fields(BatchProgress)}
    assert set(LIMIT_FIELD.values()) <= fields

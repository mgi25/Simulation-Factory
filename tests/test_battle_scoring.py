"""Phase 5B1 tests: battle metrics, the interestingness score and ranking."""

from __future__ import annotations

import dataclasses
import math

import pytest

from engine.arena_layout import LAYOUT_CLASSIC, LAYOUT_PROCEDURAL
from engine.simulation import Simulation
from evaluation.battle_metrics import (
    CLOSE_HEALTH_GAP,
    LEAD_THRESHOLD,
    BattleMetrics,
    _Collector,
    collect_metrics,
    evaluate_seed,
)
from evaluation.battle_score import (
    ACTION_WEIGHT,
    ARENA_WEIGHT,
    EXTREME_SPEED_FLOOR,
    HIT_COUNT_CAP,
    LEAD_CHANGE_CAP,
    PACING_WEIGHT,
    PAYOFF_WEIGHT,
    SHORT_BATTLE_SECONDS,
    SUSPENSE_WEIGHT,
    VARIETY_WEIGHT,
    score_battle,
)
from modes.power_battle import PowerBattleMode
from powers import POWER_NAMES
from tools.candidate_search import Candidate, evaluate, search

SEED = 12345


def metrics(**overrides) -> BattleMetrics:
    """A plain, unremarkable battle, with whatever a test wants changed."""
    base = dict(
        seed=1,
        arena_mode=LAYOUT_PROCEDURAL,
        layout_id="procedural-1",
        powers=("rush", "titan"),
        obstacles=2,
        kinetic_obstacles=1,
        winner_id=0,
        is_draw=False,
        is_timeout=False,
        duration=17.0,
        damaging_hits=7,
        hits_by_subtype=(("impact", 7),),
        power_activations=5,
        activating_fighters=2,
        damaging_fighters=2,
        first_hit_time=2.0,
        longest_idle_gap=5.0,
        lead_changes=1,
        close_fraction=0.5,
        winner_comeback=10.0,
        final_health_gap=30.0,
        winner_health=30.0,
        max_fighter_speed=1800.0,
        obstacle_contacts=25,
        distinct_obstacles_contacted=2,
        kinetic_obstacle_contacts=8,
    )
    return BattleMetrics(**{**base, **overrides})


def feed(collector: _Collector, series) -> _Collector:
    """Drive a collector with a scripted series of (RED HP, BLUE HP)."""
    for first, second in series:
        collector.observe_health(first, second)
    return collector


# --- metrics: the per-tick health tracking ----------------------------------


def test_a_lead_only_changes_when_it_really_changes() -> None:
    # RED ahead throughout, by a shrinking then growing margin.
    steady = feed(_Collector(), [(100, 90), (100, 95), (100, 80)])
    assert steady.lead_changes == 0

    # RED ahead, then BLUE ahead: one change, not two.
    once = feed(_Collector(), [(100, 80), (100, 100), (80, 100)])
    assert once.lead_changes == 1

    # Back and forth twice.
    twice = feed(_Collector(), [(100, 80), (80, 100), (100, 80)])
    assert twice.lead_changes == 2


def test_taking_the_first_lead_is_not_a_lead_change() -> None:
    opening = feed(_Collector(), [(100, 100), (100, 100), (100, 70)])
    assert opening.lead_changes == 0
    assert opening.lead_state == 1


def test_drifting_through_equality_and_back_is_not_a_change() -> None:
    """The dead band is held, so noise around a tie cannot manufacture flips."""
    wobble = [(100, 90)] + [(100, 100 - offset) for offset in (1, 0, 1, 0, 1, 0)] * 3
    assert feed(_Collector(), wobble).lead_changes == 0


def test_tiny_health_differences_never_count_as_a_lead() -> None:
    noise = feed(_Collector(), [(100, 100 - LEAD_THRESHOLD)] * 20)
    assert noise.lead_changes == 0
    assert noise.lead_state == 0


def test_close_fraction_counts_the_ticks_spent_close() -> None:
    collector = feed(
        _Collector(),
        [(100, 100)] * 3 + [(100, 100 - CLOSE_HEALTH_GAP - 1)] * 1,
    )
    assert collector.ticks == 4
    assert collector.close_ticks == 3
    # Exactly at the threshold still counts as close.
    assert feed(_Collector(), [(100, 100 - CLOSE_HEALTH_GAP)]).close_ticks == 1


def test_comeback_records_the_worst_deficit_each_side_faced() -> None:
    collector = feed(_Collector(), [(100, 100), (30, 100), (60, 100), (100, 55)])
    assert collector.max_deficit[0] == pytest.approx(70.0)
    assert collector.max_deficit[1] == pytest.approx(45.0)


# --- metrics: from a real battle --------------------------------------------


def test_metrics_are_deterministic_for_a_seed() -> None:
    for seed in (0, SEED, 4643):
        assert evaluate_seed(seed, LAYOUT_PROCEDURAL) == evaluate_seed(
            seed, LAYOUT_PROCEDURAL
        )


def test_metrics_describe_the_battle_that_ran() -> None:
    sim = Simulation(SEED, arena_mode=LAYOUT_PROCEDURAL)
    mode = PowerBattleMode(sim)
    found = collect_metrics(sim, mode)

    assert found.seed == SEED
    assert found.arena_mode == LAYOUT_PROCEDURAL
    assert found.layout_id == sim.layout.layout_id
    assert found.powers == mode.matchup
    assert found.obstacles == len(sim.layout)
    assert found.kinetic_obstacles == len(sim.layout.kinetic)
    assert found.winner_id == (None if mode.winner is None else mode.winner.ball_id)
    assert found.duration == pytest.approx(mode.duration)
    assert found.final_health_gap == pytest.approx(
        abs(sim.balls[0].health - sim.balls[1].health)
    )
    assert mode.finished


def test_hit_counts_match_the_event_stream() -> None:
    sim = Simulation(SEED, arena_mode=LAYOUT_PROCEDURAL)
    mode = PowerBattleMode(sim)
    found = collect_metrics(sim, mode)

    hits = [event for event in mode.events if event.type == "hit"]
    assert found.damaging_hits == len(hits)
    assert sum(count for _, count in found.hits_by_subtype) == len(hits)
    assert found.hit_subtypes == len({event.subtype for event in hits})
    # Sorted, so two runs of the same battle compare equal.
    assert list(found.hits_by_subtype) == sorted(found.hits_by_subtype)
    assert found.power_activations == sum(
        1 for event in mode.events if event.type == "power_activate"
    )


def test_first_hit_and_idle_gap_bracket_the_action() -> None:
    found = evaluate_seed(SEED, LAYOUT_PROCEDURAL)
    assert found.first_hit_time is not None
    assert 0.0 <= found.first_hit_time <= found.duration
    # The longest quiet stretch cannot exceed the battle, and must be at
    # least as long as the wait for the first hit.
    assert found.first_hit_time <= found.longest_idle_gap <= found.duration


def test_a_battle_with_no_hits_reports_no_first_hit() -> None:
    found = metrics(damaging_hits=0, hits_by_subtype=(), first_hit_time=None)
    assert found.hit_subtypes == 0
    assert found.hit_rate == 0.0
    assert score_battle(found).total >= 0.0


def test_obstacle_contacts_are_counted_and_bounded_by_the_layout() -> None:
    for seed in range(12):
        found = evaluate_seed(seed, LAYOUT_PROCEDURAL)
        assert found.obstacle_contacts >= 0
        assert found.distinct_obstacles_contacted <= found.obstacles
        assert found.kinetic_obstacle_contacts <= found.obstacle_contacts


def test_a_classic_arena_reports_no_obstacle_engagement() -> None:
    found = evaluate_seed(SEED, LAYOUT_CLASSIC)
    assert found.arena_mode == LAYOUT_CLASSIC
    assert found.obstacles == 0
    assert found.obstacle_contacts == 0
    assert found.distinct_obstacles_contacted == 0


def test_max_speed_is_recorded_and_positive() -> None:
    found = evaluate_seed(SEED, LAYOUT_PROCEDURAL)
    assert math.isfinite(found.max_fighter_speed)
    assert found.max_fighter_speed > 0.0


# --- scoring: bounds, purity, no favourites ---------------------------------


def test_a_score_is_always_between_zero_and_one_hundred() -> None:
    extremes = [
        metrics(),
        metrics(duration=0.5, damaging_hits=0, hits_by_subtype=(), first_hit_time=None,
                longest_idle_gap=0.5, power_activations=0, activating_fighters=0,
                damaging_fighters=0, close_fraction=0.0, winner_comeback=0.0,
                final_health_gap=100.0, max_fighter_speed=20_000.0,
                obstacle_contacts=0, distinct_obstacles_contacted=0,
                kinetic_obstacle_contacts=0, is_timeout=True),
        metrics(duration=18.0, damaging_hits=400, hits_by_subtype=(("a", 100), ("b", 300)),
                lead_changes=500, close_fraction=1.0, winner_comeback=1000.0,
                final_health_gap=0.0, power_activations=99, obstacle_contacts=9999,
                distinct_obstacles_contacted=9, kinetic_obstacle_contacts=9999),
    ]
    for case in extremes:
        assert 0.0 <= score_battle(case).total <= 100.0

    for seed in range(40):
        found = evaluate_seed(seed, LAYOUT_PROCEDURAL)
        assert 0.0 <= score_battle(found).total <= 100.0


def test_scoring_is_pure() -> None:
    case = metrics()
    assert score_battle(case) == score_battle(case)
    assert [score_battle(case).total for _ in range(5)].count(
        score_battle(case).total
    ) == 5


def test_the_breakdown_adds_up() -> None:
    result = score_battle(metrics())
    assert result.total == pytest.approx(result.subtotal - result.penalty)
    assert result.penalty == pytest.approx(sum(v for _, v in result.penalties))
    assert result.explain(metrics())


def test_no_power_is_worth_points_by_name() -> None:
    """Renaming the powers in a battle must not move its score at all."""
    base = metrics()
    for first in POWER_NAMES:
        for second in POWER_NAMES:
            renamed = dataclasses.replace(base, powers=(first, second))
            assert score_battle(renamed).total == score_battle(base).total


def test_relabelling_hit_mechanisms_changes_nothing() -> None:
    """Only how *many* mechanisms there were can matter, never which."""
    impact = metrics(hits_by_subtype=(("impact", 4), ("echo", 3)), damaging_hits=7)
    renamed = metrics(hits_by_subtype=(("orbit", 4), ("projectile", 3)), damaging_hits=7)
    assert score_battle(impact).total == score_battle(renamed).total


# --- scoring: counts saturate -----------------------------------------------


def test_lead_changes_saturate() -> None:
    at_cap = score_battle(metrics(lead_changes=LEAD_CHANGE_CAP)).suspense
    far_past = score_battle(metrics(lead_changes=LEAD_CHANGE_CAP * 50)).suspense
    assert far_past == pytest.approx(at_cap)


def test_hit_volume_saturates() -> None:
    """Both of these land often enough; the busier one gains nothing for it.

    Durations are chosen so each battle's hit *rate* stays inside the band
    the density term likes, which isolates the volume cap from it.
    """
    at_cap = score_battle(metrics(damaging_hits=HIT_COUNT_CAP, duration=17.0)).action
    busier = score_battle(metrics(damaging_hits=20, duration=17.0)).action
    assert busier == pytest.approx(at_cap)


def test_an_absurd_hit_rate_is_not_rewarded_as_action() -> None:
    """Saturating counts is not the same as rewarding maximum chaos."""
    brisk = score_battle(metrics(damaging_hits=14, duration=17.0)).action
    frantic = score_battle(metrics(damaging_hits=600, duration=17.0)).action
    assert frantic < brisk


def test_more_of_a_good_thing_never_scores_worse() -> None:
    quiet = metrics(lead_changes=0, close_fraction=0.1, winner_comeback=0.0)
    lively = metrics(lead_changes=3, close_fraction=0.8, winner_comeback=35.0)
    assert score_battle(lively).suspense > score_battle(quiet).suspense


# --- scoring: penalties -----------------------------------------------------


def test_a_timeout_is_penalised_and_loses_its_payoff() -> None:
    ended = metrics(is_timeout=False)
    timed_out = metrics(is_timeout=True)
    assert "timeout" in dict(score_battle(timed_out).penalties)
    assert score_battle(timed_out).payoff < score_battle(ended).payoff
    assert score_battle(timed_out).total < score_battle(ended).total


def test_a_very_short_battle_is_penalised() -> None:
    brief = metrics(duration=2.0)
    named = dict(score_battle(brief).penalties)
    assert "too short" in named
    assert 0.0 < named["too short"] <= 10.0
    assert "too short" not in dict(score_battle(metrics(duration=SHORT_BATTLE_SECONDS)).penalties)


def test_a_long_idle_stretch_is_penalised_but_bounded() -> None:
    dull = dict(score_battle(metrics(longest_idle_gap=30.0)).penalties)
    milder = dict(score_battle(metrics(longest_idle_gap=11.0)).penalties)
    assert dull["idle stretch"] > milder["idle stretch"]
    assert dull["idle stretch"] <= 6.0


def test_an_almost_inert_battle_is_penalised() -> None:
    assert "almost no action" in dict(
        score_battle(metrics(damaging_hits=1)).penalties
    )
    assert "almost no action" not in dict(score_battle(metrics()).penalties)


def test_extreme_speed_is_penalised_without_any_gameplay_cap() -> None:
    """The tail gets marked down as a candidate; the game is left alone."""
    normal = metrics(max_fighter_speed=1800.0)
    wild = metrics(max_fighter_speed=EXTREME_SPEED_FLOOR + 4000.0)
    assert "extreme speed" not in dict(score_battle(normal).penalties)
    named = dict(score_battle(wild).penalties)
    assert 0.0 < named["extreme speed"] <= 6.0
    assert score_battle(wild).total < score_battle(normal).total


def test_penalties_stay_bounded_even_all_at_once() -> None:
    worst = metrics(
        is_timeout=True, duration=0.1, longest_idle_gap=99.0, damaging_hits=0,
        hits_by_subtype=(), first_hit_time=None, max_fighter_speed=99_999.0,
    )
    assert score_battle(worst).penalty < 40.0
    assert score_battle(worst).total >= 0.0


# --- scoring: the orderings that matter -------------------------------------


def test_a_dramatic_elimination_beats_an_inactive_timeout() -> None:
    dramatic = metrics(
        duration=18.0, is_timeout=False, lead_changes=4, close_fraction=0.85,
        winner_comeback=40.0, final_health_gap=6.0, winner_health=6.0,
        damaging_hits=11, hits_by_subtype=(("impact", 6), ("echo", 5)),
        first_hit_time=1.2, longest_idle_gap=3.0,
    )
    inert = metrics(
        duration=35.0, is_timeout=True, lead_changes=0, close_fraction=0.05,
        winner_comeback=0.0, final_health_gap=70.0, winner_health=90.0,
        damaging_hits=2, hits_by_subtype=(("impact", 2),),
        first_hit_time=14.0, longest_idle_gap=20.0,
    )
    assert score_battle(dramatic).total > score_battle(inert).total + 40.0


def test_a_back_and_forth_battle_beats_a_two_second_stomp() -> None:
    back_and_forth = metrics(
        duration=18.0, lead_changes=4, close_fraction=0.8, winner_comeback=35.0,
        damaging_hits=10, final_health_gap=10.0, winner_health=10.0,
    )
    stomp = metrics(
        duration=2.0, lead_changes=0, close_fraction=0.1, winner_comeback=0.0,
        damaging_hits=3, final_health_gap=100.0, winner_health=100.0,
        first_hit_time=0.4, longest_idle_gap=1.0,
    )
    assert score_battle(back_and_forth).total > score_battle(stomp).total


def test_a_close_finish_pays_off_better_than_a_walkover() -> None:
    photo_finish = metrics(final_health_gap=3.0, winner_health=3.0)
    walkover = metrics(final_health_gap=98.0, winner_health=98.0)
    assert score_battle(photo_finish).payoff > score_battle(walkover).payoff


def test_pacing_prefers_a_shorts_length_battle() -> None:
    lengths = {d: score_battle(metrics(duration=d)).pacing for d in (2, 8, 17, 28, 35)}
    assert lengths[17] == PACING_WEIGHT
    assert lengths[8] < lengths[17]
    assert lengths[28] < lengths[17]
    assert lengths[2] == 0.0
    assert lengths[35] == 0.0


# --- scoring: arena engagement is fair to every layout ----------------------


def test_an_empty_arena_is_scored_neutrally_not_punished() -> None:
    empty = metrics(obstacles=0, kinetic_obstacles=0, obstacle_contacts=0,
                    distinct_obstacles_contacted=0, kinetic_obstacle_contacts=0)
    ignored = metrics(obstacles=3, kinetic_obstacles=1, obstacle_contacts=0,
                      distinct_obstacles_contacted=0, kinetic_obstacle_contacts=0)
    assert 0.0 < score_battle(empty).arena < ARENA_WEIGHT
    # An arena with obstacles that went untouched does worse than one that
    # never had any to touch.
    assert score_battle(ignored).arena < score_battle(empty).arena


def test_a_still_layout_can_still_score_full_arena_marks() -> None:
    """A layout with nothing kinetic is judged on what it actually offered."""
    still = metrics(obstacles=3, kinetic_obstacles=0, obstacle_contacts=200,
                    distinct_obstacles_contacted=3, kinetic_obstacle_contacts=0)
    assert score_battle(still).arena == pytest.approx(ARENA_WEIGHT)


def test_engaging_with_the_arena_scores_better_than_ignoring_it() -> None:
    engaged = metrics(obstacle_contacts=40, distinct_obstacles_contacted=2,
                      kinetic_obstacle_contacts=18)
    aloof = metrics(obstacle_contacts=2, distinct_obstacles_contacted=1,
                    kinetic_obstacle_contacts=0)
    assert score_battle(engaged).arena > score_battle(aloof).arena


def test_every_dimension_stays_inside_its_weight() -> None:
    caps = {
        "pacing": PACING_WEIGHT, "suspense": SUSPENSE_WEIGHT, "action": ACTION_WEIGHT,
        "variety": VARIETY_WEIGHT, "arena": ARENA_WEIGHT, "payoff": PAYOFF_WEIGHT,
    }
    for seed in range(30):
        result = score_battle(evaluate_seed(seed, LAYOUT_PROCEDURAL))
        for name, cap in caps.items():
            assert 0.0 <= getattr(result, name) <= cap


# --- ranking ----------------------------------------------------------------


def test_ranking_is_the_same_however_many_workers_run_it() -> None:
    jobs = [(seed, LAYOUT_PROCEDURAL) for seed in range(24)]
    single = search(jobs, workers=1)
    parallel = search(jobs, workers=4)
    assert [c.metrics.seed for c in single] == [c.metrics.seed for c in parallel]
    assert [c.score.total for c in single] == [c.score.total for c in parallel]


def test_ranking_is_best_first_with_a_stable_tie_break() -> None:
    ranked = search([(seed, LAYOUT_PROCEDURAL) for seed in range(24)], workers=1)
    totals = [c.score.total for c in ranked]
    assert totals == sorted(totals, reverse=True)

    tied = sorted(
        [
            Candidate(metrics(seed=7), score_battle(metrics(seed=7))),
            Candidate(metrics(seed=3), score_battle(metrics(seed=3))),
            Candidate(metrics(seed=5), score_battle(metrics(seed=5))),
        ],
        key=lambda candidate: candidate.rank_key,
    )
    # Identical scores, so the seed decides - ascending, and never by chance.
    assert [c.metrics.seed for c in tied] == [3, 5, 7]


def test_evaluating_one_job_matches_evaluating_the_seed() -> None:
    candidate = evaluate((SEED, LAYOUT_PROCEDURAL))
    assert candidate.metrics == evaluate_seed(SEED, LAYOUT_PROCEDURAL)
    assert candidate.score == score_battle(candidate.metrics)

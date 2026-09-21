"""Category 3 Phase 2: the evaluator, the seed search, and the claims they rest on.

Phase 1's tests pin the physics. These pin the *judgement* - the layer that
decides a run is worth filming - and one physical claim Phase 2 leans on so
heavily that it has to be regression-protected: with `gravity = 0`, speed is a
change of clock and nothing else.

Three things are worth a note on method.

**The evaluator is tested against hand-built event streams, not only against
runs.** A metric that is only ever checked on real simulation output is checked
against whatever the simulation happens to do, which is exactly the population
whose properties are in question. `_fake_run` builds a run with a chosen
activation pattern, so "the longest gap is 9 s and it starts at 12 s" is
asserted against a stream where that is true by construction.

**Speed invariance is tested by comparing whole collision sequences**, not
summary statistics. Two runs can agree on completion time and disagree about
every tile in between.

**The acceptance rule is tested in both directions.** A rule that only ever
gets shown runs it accepts is not a rule. Each condition has a case that fails
it alone, so a future threshold change cannot silently stop a condition from
being able to fire.

No new third-party dependency, and the file runs in a few seconds: the
simulations here are short and the fake streams cost nothing.
"""

from __future__ import annotations

import math
import os
import subprocess
import sys

import pytest

from satisfying.tile_arena import polygon_arena
from satisfying.tile_escape import (
    Collision,
    Flight,
    TileEscapeConfig,
    TileEscapeRun,
    simulate,
)
from satisfying.tile_evaluator import (
    DEFAULT_RULE,
    MILESTONES,
    AcceptanceRule,
    activation_curve,
    candidate_score,
    evaluate,
    longest_confined_window,
    longest_periodic_run,
    milestone_index,
    percentile,
    verdict,
)
from satisfying.tile_sweep import (
    PHASE2_ARENA,
    PHASE2_CONFIG,
    activation_curve_percentiles,
    distribution,
    population_report,
    rescale_to_speed,
    shortlist,
    sweep,
    verify_speed_invariance,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The locked Phase 2 base configuration, as the brief states it.
PHASE2_SIDES = 17
PHASE2_TILES_PER_SIDE = 3
PHASE2_TOTAL_TILES = 51


# --------------------------------------------------------------------------
# The locked Phase 2 geometry: 17 x 3 = 51.
# --------------------------------------------------------------------------


def test_the_phase_two_arena_has_fifty_one_independently_activatable_tiles() -> None:
    arena = PHASE2_ARENA
    assert arena.sides == PHASE2_SIDES
    assert arena.tiles_per_side == PHASE2_TILES_PER_SIDE
    assert arena.total_tiles == PHASE2_TOTAL_TILES
    assert len({tile.tile_id for tile in arena.tiles}) == PHASE2_TOTAL_TILES
    assert len({tile.index for tile in arena.tiles}) == PHASE2_TOTAL_TILES
    # Three tiles on every side, and every side represented exactly once.
    per_side: dict[int, int] = {}
    for tile in arena.tiles:
        per_side[tile.side] = per_side.get(tile.side, 0) + 1
    assert set(per_side) == set(range(PHASE2_SIDES))
    assert set(per_side.values()) == {PHASE2_TILES_PER_SIDE}


def test_every_one_of_the_fifty_one_tiles_is_wider_than_the_ball() -> None:
    """51 tiles is only readable if a tile is still bigger than what hits it."""
    arena = PHASE2_ARENA
    assert arena.tile_length > 2.0 * PHASE2_CONFIG.ball_radius
    assert all(
        tile.length == pytest.approx(arena.tile_length, rel=1e-12) for tile in arena.tiles
    )


def test_the_phase_two_base_configuration_is_the_one_the_brief_locked() -> None:
    assert PHASE2_CONFIG.gravity == 0.0
    assert PHASE2_CONFIG.speed == 60.0
    assert PHASE2_CONFIG.restitution == 1.0
    assert PHASE2_ARENA.circumradius == 10.0


def test_a_completing_run_activates_every_one_of_the_fifty_one_tiles() -> None:
    run = simulate(7, PHASE2_CONFIG, PHASE2_ARENA)
    assert run.completed
    assert run.activated_tiles == PHASE2_TOTAL_TILES
    assert len(run.first_hit_time) == PHASE2_TOTAL_TILES
    assert run.unhit_tiles() == ()


# --------------------------------------------------------------------------
# A hand-built event stream, so the metrics are checked against known answers.
# --------------------------------------------------------------------------


def _fake_run(
    activation_times: list[float],
    duplicates_after: dict[int, int] | None = None,
    end_time: float | None = None,
    total_tiles: int = 51,
    seed: int = 0,
) -> TileEscapeRun:
    """A run whose event stream is exactly what the caller asked for.

    `activation_times[i]` is when tile i lit. `duplicates_after[i]` inserts that
    many repeat hits just after activation i, spaced a hundredth of a second
    apart, so duplicate-share and gap metrics can be given a known answer. The
    geometry is real - a 17-gon - but no physics ran: these are the events an
    evaluator sees, and the evaluator is the thing under test.
    """
    arena = polygon_arena(sides=17, tiles_per_side=3)
    assert total_tiles <= arena.total_tiles
    duplicates_after = duplicates_after or {}

    collisions: list[Collision] = []
    first_hit: dict[str, float] = {}
    hits: dict[str, int] = {tile.tile_id: 0 for tile in arena.tiles}

    def add(tile_index: int, when: float, is_new: bool) -> None:
        tile = arena.tiles[tile_index]
        if is_new:
            first_hit[tile.tile_id] = when
        hits[tile.tile_id] += 1
        collisions.append(
            Collision(
                time=when,
                tile_index=tile.index,
                tile_id=tile.tile_id,
                side=tile.side,
                slot=tile.slot,
                is_new=is_new,
                activated_after=len(first_hit),
                contact=tile.midpoint,
                incoming_speed=60.0,
                normal_speed=30.0,
                flight_seconds=0.1,
            )
        )

    for index, when in enumerate(activation_times):
        add(index, when, True)
        for repeat in range(duplicates_after.get(index, 0)):
            add(index, when + 0.01 * (repeat + 1), False)

    collisions.sort(key=lambda c: c.time)
    finish = activation_times[-1] if len(first_hit) == total_tiles else None
    return TileEscapeRun(
        seed=seed,
        config=PHASE2_CONFIG,
        arena=arena,
        flights=(Flight(0.0, (0.0, 0.0), (60.0, 0.0)),),
        collisions=tuple(collisions),
        first_hit_time=first_hit,
        hits_by_tile=hits,
        end_time=end_time if end_time is not None else collisions[-1].time,
        completed=finish is not None,
        completion_time=finish,
        stop_reason="complete" if finish is not None else "duration",
        metrics={},
    )


def _even_activations(count: int, step: float, start: float = 0.5) -> list[float]:
    return [start + step * i for i in range(count)]


# --------------------------------------------------------------------------
# Milestone extraction.
# --------------------------------------------------------------------------


def test_a_milestone_is_a_tile_number_and_a_fraction_rounds_up() -> None:
    assert milestone_index(0.25, 51) == 13  # ceil(12.75)
    assert milestone_index(0.50, 51) == 26  # ceil(25.5)
    assert milestone_index(0.75, 51) == 39  # ceil(38.25)
    assert milestone_index(0.90, 51) == 46  # ceil(45.9)
    assert milestone_index(0.95, 51) == 49  # ceil(48.45)
    assert milestone_index(-2, 51) == 49
    assert milestone_index(-1, 51) == 50
    assert milestone_index(0, 51) == 51
    assert milestone_index(1, 51) == 1


def test_at_fifty_one_tiles_ninety_five_percent_and_forty_nine_are_the_same_milestone() -> None:
    """A real coincidence of this tile count, pinned so a report cannot misread it.

    `ceil(0.95 * 51) == 49`, so the "95%" clock and the "49 of 51" clock are the
    same number at 51 tiles. Anything comparing the two is comparing a value
    with itself. They coincide for every tile count from 40 to 59 and part
    company outside that band, which is what the second assertion shows.
    """
    assert milestone_index(0.95, 51) == milestone_index(-2, 51) == 49
    assert milestone_index(0.95, 100) == 95 != milestone_index(-2, 100) == 98
    evaluation = evaluate(_fake_run(_even_activations(51, 1.0)))
    assert evaluation.milestones["p95"] == evaluation.milestones["n_minus_2"]
    assert evaluation.tail_from_95_seconds == evaluation.tail_from_third_last_seconds


def test_milestones_are_extracted_at_the_times_the_stream_says() -> None:
    times = _even_activations(51, 1.0, start=1.0)  # tile n lights at t = n seconds
    evaluation = evaluate(_fake_run(times))
    assert evaluation.milestones["first"] == pytest.approx(1.0)
    assert evaluation.milestones["p25"] == pytest.approx(13.0)
    assert evaluation.milestones["p50"] == pytest.approx(26.0)
    assert evaluation.milestones["p75"] == pytest.approx(39.0)
    assert evaluation.milestones["p90"] == pytest.approx(46.0)
    assert evaluation.milestones["p95"] == pytest.approx(49.0)
    assert evaluation.milestones["n_minus_1"] == pytest.approx(50.0)
    assert evaluation.milestones["complete"] == pytest.approx(51.0)
    assert list(evaluation.milestones) == [name for name, _ in MILESTONES]


def test_a_milestone_not_reached_is_none_rather_than_zero() -> None:
    """The difference between "at 0 s" and "never" has to survive the report."""
    evaluation = evaluate(_fake_run(_even_activations(20, 1.0), end_time=60.0))
    assert evaluation.milestones["p25"] is not None
    assert evaluation.milestones["p50"] is None
    assert evaluation.milestones["complete"] is None
    assert evaluation.tail_from_90_seconds is None
    assert evaluation.final_tile_seconds is None
    assert not evaluation.completed


def test_milestones_are_non_decreasing() -> None:
    evaluation = evaluate(simulate(7, PHASE2_CONFIG, PHASE2_ARENA))
    reached = [v for v in evaluation.milestones.values() if v is not None]
    assert reached == sorted(reached)


# --------------------------------------------------------------------------
# Stagnation measurement.
# --------------------------------------------------------------------------


def test_the_longest_gap_is_found_and_located() -> None:
    times = _even_activations(51, 0.5, start=0.5)
    # Push everything from the 21st tile on nine seconds later: one 9.5 s gap
    # that begins at the 20th activation, which is at t = 10.0.
    times = [t if i < 20 else t + 9.0 for i, t in enumerate(times)]
    evaluation = evaluate(_fake_run(times))
    assert evaluation.longest_gap_seconds == pytest.approx(9.5)
    assert evaluation.longest_gap_start_seconds == pytest.approx(10.0)
    assert evaluation.longest_gap_after_tiles == 20
    assert evaluation.longest_gap_progress == pytest.approx(20 / 51)


def test_the_first_gap_is_measured_from_zero_and_not_from_the_first_event() -> None:
    """A run that does nothing for six seconds has a six-second gap, not none."""
    evaluation = evaluate(_fake_run([6.0] + _even_activations(50, 0.5, start=6.5)))
    assert evaluation.longest_gap_seconds == pytest.approx(6.0)
    assert evaluation.longest_gap_start_seconds == pytest.approx(0.0)
    assert evaluation.longest_gap_after_tiles == 0


def test_an_incomplete_runs_dead_tail_counts_as_a_gap() -> None:
    evaluation = evaluate(_fake_run(_even_activations(30, 0.5, start=0.5), end_time=100.0))
    # Last activation at 15.0, run ends at 100.0.
    assert evaluation.longest_gap_seconds == pytest.approx(85.0)
    assert evaluation.longest_gap_after_tiles == 30


def test_a_gap_inside_the_final_three_tiles_is_the_ending_and_not_a_body_gap() -> None:
    """The distinction the whole tail analysis rests on.

    `longest_gap_seconds` cannot tell a twelve-second hunt for the last tile
    from a twelve-second hole at the halfway mark. `longest_body_gap_seconds`
    can, because it only looks at gaps that begin while more than three tiles
    are still dark.
    """
    times = _even_activations(51, 0.4, start=0.4)
    times[50] += 12.0  # a twelve-second wait for the very last tile
    evaluation = evaluate(_fake_run(times))
    assert evaluation.longest_gap_seconds == pytest.approx(12.4)
    assert evaluation.longest_gap_after_tiles == 50
    assert evaluation.longest_body_gap_seconds == pytest.approx(0.4)
    assert evaluation.final_tile_seconds == pytest.approx(12.4)

    # The same twelve seconds in the middle is a body gap and must be caught.
    middle = _even_activations(51, 0.4, start=0.4)
    middle = [t if i < 25 else t + 12.0 for i, t in enumerate(middle)]
    mid_evaluation = evaluate(_fake_run(middle))
    assert mid_evaluation.longest_body_gap_seconds == pytest.approx(12.4)
    assert mid_evaluation.longest_body_gap_after_tiles == 25


def test_long_gaps_are_counted_against_the_stated_threshold() -> None:
    times = _even_activations(51, 0.2, start=0.2)
    for boundary in (10, 20, 30):
        times = [t if i < boundary else t + 5.0 for i, t in enumerate(times)]
    evaluation = evaluate(_fake_run(times), long_gap_seconds=3.0)
    assert evaluation.long_gap_count == 3
    assert evaluation.long_gap_threshold_seconds == 3.0
    assert evaluate(_fake_run(times), long_gap_seconds=6.0).long_gap_count == 0


# --------------------------------------------------------------------------
# Tail timing.
# --------------------------------------------------------------------------


def test_the_four_tail_clocks_measure_what_they_are_named_after() -> None:
    times = _even_activations(51, 1.0, start=1.0)
    evaluation = evaluate(_fake_run(times))
    assert evaluation.completion_seconds == pytest.approx(51.0)
    assert evaluation.tail_from_90_seconds == pytest.approx(51.0 - 46.0)
    assert evaluation.tail_from_95_seconds == pytest.approx(51.0 - 49.0)
    assert evaluation.tail_from_third_last_seconds == pytest.approx(51.0 - 49.0)
    assert evaluation.tail_from_second_last_seconds == pytest.approx(51.0 - 50.0)
    assert evaluation.final_tile_seconds == pytest.approx(1.0)
    # The final three are tiles 49, 50 and 51, so the clock starts at tile 48.
    assert evaluation.final_three_seconds == pytest.approx(51.0 - 48.0)


def test_the_tail_share_is_the_fraction_of_the_run_spent_on_the_last_ten_percent() -> None:
    times = _even_activations(46, 0.2, start=0.2)  # 46 tiles in 9.2 s
    times += [9.2 + 2.0 * (i + 1) for i in range(5)]  # the last five take 10 s
    evaluation = evaluate(_fake_run(times))
    assert evaluation.completion_seconds == pytest.approx(19.2)
    assert evaluation.tail_from_90_seconds == pytest.approx(10.0)
    assert evaluation.tail_share_from_90 == pytest.approx(10.0 / 19.2)


def test_the_final_tile_is_compared_against_an_ordinary_one() -> None:
    """"The ending takes longer than a normal tile" needs a normal tile to mean."""
    times = _even_activations(50, 0.5, start=0.5)
    times.append(times[-1] + 7.5)
    evaluation = evaluate(_fake_run(times))
    assert evaluation.median_activation_interval == pytest.approx(0.5)
    assert evaluation.final_tile_seconds == pytest.approx(7.5)
    assert evaluation.final_tile_over_median_interval == pytest.approx(15.0)


def test_tail_clocks_are_ordered_by_construction() -> None:
    """From 90% >= from 95% >= from n-1: each window contains the next."""
    for seed in (1, 7, 12, 19, 23):
        evaluation = evaluate(simulate(seed, PHASE2_CONFIG, PHASE2_ARENA))
        if not evaluation.completed:
            continue
        assert evaluation.tail_from_90_seconds >= evaluation.tail_from_95_seconds
        assert evaluation.tail_from_95_seconds >= evaluation.tail_from_second_last_seconds
        assert evaluation.final_three_seconds >= evaluation.tail_from_95_seconds
        assert evaluation.tail_from_second_last_seconds >= 0.0


# --------------------------------------------------------------------------
# Opening and collision quality.
# --------------------------------------------------------------------------


def test_the_opening_counts_only_what_happened_inside_the_window() -> None:
    times = [0.3, 0.8, 1.4, 1.9, 2.5] + _even_activations(46, 0.5, start=3.0)
    evaluation = evaluate(_fake_run(times), opening_window_seconds=2.0)
    assert evaluation.first_collision_seconds == pytest.approx(0.3)
    assert evaluation.first_activation_seconds == pytest.approx(0.3)
    assert evaluation.activations_in_opening == 4
    assert evaluation.early_activation_rate == pytest.approx(2.0)


def test_the_first_collision_of_a_real_run_is_always_the_first_activation() -> None:
    """Every tile starts dark, so contact number one cannot be a duplicate."""
    for seed in (1, 7, 12, 19):
        run = simulate(seed, PHASE2_CONFIG, PHASE2_ARENA)
        evaluation = evaluate(run)
        assert run.collisions[0].is_new
        assert evaluation.first_collision_seconds == evaluation.first_activation_seconds


def test_duplicate_share_is_reported_across_the_run_and_not_only_in_total() -> None:
    """A run can be 60% duplicates overall and 98% duplicates in its last third."""
    times = _even_activations(51, 0.5, start=0.5)
    # 40 repeat hits piled onto the 50th activation: the last third of the
    # collision stream is almost entirely duplicates.
    evaluation = evaluate(_fake_run(times, duplicates_after={49: 40}))
    assert evaluation.new_hits == 51
    assert evaluation.duplicate_hits == 40
    assert evaluation.collisions == 91
    # Thirds are cut by collision count, not by clock: 91 collisions split at
    # 30 and 60, so the pile-up straddles the second and third blocks.
    early, middle, late = evaluation.duplicate_share_thirds
    assert early == 0.0
    assert 0.0 < middle < late
    assert late > 0.9
    assert evaluation.duplicates_per_new_thirds[0] == 0.0
    assert evaluation.duplicates_per_new_thirds[2] > 10.0


def test_a_third_with_no_new_tile_reports_none_rather_than_a_division() -> None:
    times = _even_activations(51, 0.5, start=0.5)
    evaluation = evaluate(_fake_run(times, duplicates_after={50: 200}))
    assert evaluation.duplicates_per_new_thirds[2] is None
    assert evaluation.duplicate_share_thirds[2] == pytest.approx(1.0)


# --------------------------------------------------------------------------
# Repeating-pattern detection.
# --------------------------------------------------------------------------


def test_the_detector_finds_an_a_b_a_b_pattern_and_names_its_period() -> None:
    found = longest_periodic_run([9, 8, 7, 1, 2, 1, 2, 1, 2, 5, 6])
    assert found.period == 2
    assert found.length == 6
    assert found.repeats == 3
    assert found.start_index == 3
    assert found.members == (1, 2)


def test_the_detector_finds_a_longer_cycle_and_prefers_the_smaller_period() -> None:
    """A-B-A-B also satisfies period 4; reporting it as a four-cycle misnames it."""
    four = longest_periodic_run([1, 2, 3, 4] * 3)
    assert four.period == 4 and four.length == 12 and four.repeats == 3
    two = longest_periodic_run([1, 2] * 6)
    assert two.period == 2 and two.length == 12


def test_the_detector_ignores_a_pattern_that_does_not_repeat_twice() -> None:
    assert not longest_periodic_run([1, 2, 1]).found
    assert not longest_periodic_run([1, 2, 3, 4, 5, 6, 7]).found
    assert longest_periodic_run([1, 2, 1, 2]).found


def test_the_detector_can_be_restricted_to_one_period() -> None:
    sequence = [1, 2, 3, 4] * 3
    assert longest_periodic_run(sequence).period == 4
    assert not longest_periodic_run(sequence, max_period=2, min_period=2).found


def test_a_confined_window_reports_where_it_started_and_what_was_in_it() -> None:
    times = [float(i) for i in range(11)]
    window = longest_confined_window([9, 8, 7, 1, 2, 1, 2, 1, 2, 5, 6], 2, times)
    assert window.length == 6
    assert window.start_index == 3
    assert window.start_seconds == pytest.approx(3.0)
    assert window.members == (1, 2)


def test_the_sixteen_sided_loop_is_caught_by_the_phase_two_detector() -> None:
    """Phase 1's pathology, seen through Phase 2's instrument.

    Seed 134 in a 16-gon spends dozens of consecutive collisions alternating
    between one floor tile and the ceiling tile opposite. The evaluator must
    report that as a period-2 pattern with two members - if a future change
    stops it firing here, it will not fire on a real regression either.
    """
    fast = TileEscapeConfig(gravity=0.0, speed=60.0, duration=1200.0)
    sixteen = evaluate(simulate(134, fast, polygon_arena(sides=16)))
    assert sixteen.longest_alternation.period == 2
    assert sixteen.longest_alternation.length >= 20
    assert len(sixteen.longest_alternation.members) == 2
    assert sixteen.longest_two_tile_run.length >= 20
    assert sixteen.longest_two_tile_run.start_seconds > 0.0


def test_seventeen_sides_does_not_produce_that_loop() -> None:
    fast = TileEscapeConfig(gravity=0.0, speed=60.0, duration=1200.0)
    seventeen = evaluate(simulate(134, fast, polygon_arena(sides=17)))
    assert seventeen.longest_two_tile_run.length <= 5
    assert not seventeen.longest_alternation.found


# --------------------------------------------------------------------------
# Candidate acceptance and rejection.
# --------------------------------------------------------------------------


def _accepted_stream() -> TileEscapeRun:
    """An event stream built to pass every condition, as the control case."""
    times = _even_activations(48, 0.55, start=0.35)  # 48 tiles by ~26.2 s
    times += [times[-1] + 2.0, times[-1] + 5.0, times[-1] + 9.0]
    return _fake_run(times)


def test_the_control_stream_is_accepted() -> None:
    evaluation = evaluate(_accepted_stream())
    outcome = verdict(evaluation)
    assert outcome.accepted, outcome.failures
    assert outcome.failures == ()
    assert 25.0 <= evaluation.completion_seconds <= 40.0


@pytest.mark.parametrize(
    "condition, mutate",
    [
        (
            "duration_at_most_max",
            lambda t: [x * 2.0 for x in t],
        ),
        (
            "duration_at_least_min",
            lambda t: [x * 0.3 for x in t],
        ),
        (
            "opens_immediately",
            lambda t: [x + 3.0 for x in t],
        ),
        (
            "no_mid_run_dead_zone",
            lambda t: [x if i < 20 else x + 6.0 for i, x in enumerate(t)],
        ),
        (
            "last_tile_is_not_a_wait",
            lambda t: t[:-1] + [t[-1] + 12.0],
        ),
        (
            "last_tile_has_tension",
            lambda t: t[:-1] + [t[-2] + 0.2],
        ),
    ],
)
def test_each_acceptance_condition_can_fail_on_its_own(condition, mutate) -> None:
    """Every threshold must be reachable, or it is decoration.

    The mutation is chosen to break one condition; others may break with it
    (stretching a run to fail on duration also moves its tail), so the assertion
    is that the named condition is among the failures, not that it is alone.
    """
    base = _even_activations(48, 0.55, start=0.35)
    base += [base[-1] + 2.0, base[-1] + 5.0, base[-1] + 9.0]
    evaluation = evaluate(_fake_run(mutate(base)))
    outcome = verdict(evaluation)
    assert not outcome.accepted
    assert condition in outcome.failures, outcome.failures


def test_an_incomplete_run_is_rejected_and_says_so_first() -> None:
    evaluation = evaluate(_fake_run(_even_activations(30, 0.5, start=0.5), end_time=60.0))
    outcome = verdict(evaluation)
    assert not outcome.accepted
    assert "completes" in outcome.failures


def test_a_two_tile_loop_is_rejected_however_good_the_rest_of_the_run_is() -> None:
    fast = TileEscapeConfig(gravity=0.0, speed=60.0, duration=1200.0)
    sixteen = evaluate(simulate(134, fast, polygon_arena(sides=16)))
    assert "no_two_tile_loop" in verdict(sixteen).failures


def test_the_verdict_lists_every_failing_condition_and_not_just_the_first() -> None:
    """A seed that misses one threshold is not the same object as one that misses five."""
    evaluation = evaluate(_fake_run(_even_activations(51, 4.0, start=4.0)))
    outcome = verdict(evaluation)
    assert len(outcome.failures) >= 3
    assert set(outcome.failures).isdisjoint(outcome.passes)
    assert len(outcome.failures) + len(outcome.passes) == 12


def test_the_rule_is_data_and_a_different_rule_gives_a_different_answer() -> None:
    evaluation = evaluate(_fake_run(_even_activations(51, 1.0, start=1.0)))
    assert "duration_at_most_max" in verdict(evaluation, AcceptanceRule()).failures
    generous = AcceptanceRule(max_duration=90.0, max_final_three=20.0, max_body_gap=9.0)
    assert "duration_at_most_max" not in verdict(evaluation, generous).failures


def test_the_score_shows_its_components_and_they_are_the_weighted_total() -> None:
    """No opaque number: the total has to be reproducible from what is reported."""
    evaluation = evaluate(_accepted_stream())
    score = candidate_score(evaluation)
    assert set(score.components) == set(score.weights)
    assert sum(score.weights.values()) == pytest.approx(1.0)
    assert all(0.0 <= v <= 1.0 for v in score.components.values())
    recomputed = sum(score.components[k] * score.weights[k] for k in score.weights)
    assert score.total == pytest.approx(recomputed)
    assert 0.0 <= score.total <= 1.0


def test_the_score_ranks_but_does_not_accept() -> None:
    """A high-scoring run that fails a condition is still rejected."""
    times = _even_activations(48, 0.55, start=0.35)
    times += [times[-1] + 2.0, times[-1] + 5.0, times[-1] + 9.0]
    times = [t if i < 20 else t + 6.0 for i, t in enumerate(times)]
    evaluation = evaluate(_fake_run(times))
    assert candidate_score(evaluation).total > 0.3
    assert not verdict(evaluation).accepted


# --------------------------------------------------------------------------
# The activation curve.
# --------------------------------------------------------------------------


def test_the_activation_curve_starts_at_the_origin_and_steps_once_per_tile() -> None:
    run = simulate(7, PHASE2_CONFIG, PHASE2_ARENA)
    curve = activation_curve(run)
    assert curve[0] == (0.0, 0)
    counts = [count for _, count in curve]
    assert counts == sorted(counts)
    assert counts[-1] == run.activated_tiles
    # One point per activation, plus the origin.
    assert len(curve) == run.activated_tiles + 1
    times = [t for t, _ in curve]
    assert times == sorted(times)


def test_an_incomplete_runs_curve_carries_its_dead_tail() -> None:
    run = simulate(7, TileEscapeConfig(**{**PHASE2_CONFIG.as_dict(), "duration": 12.0}), PHASE2_ARENA)
    curve = activation_curve(run)
    assert not run.completed
    assert curve[-1][0] == pytest.approx(run.end_time)
    assert curve[-1][1] == curve[-2][1], "the tail must not look like an activation"


def test_curve_percentiles_count_each_activation_number_once_per_run() -> None:
    """The flat tail point must not be counted as an extra arrival at that count."""
    curves = [
        ((0.0, 0), (1.0, 1), (2.0, 2), (9.0, 2)),
        ((0.0, 0), (3.0, 1), (4.0, 2)),
    ]
    rows = activation_curve_percentiles(curves)
    assert [r["activated"] for r in rows] == [1, 2]
    assert all(r["runs"] == 2 for r in rows)
    assert rows[1]["p50"] == pytest.approx(2.0)


def test_the_curve_agrees_with_the_milestones_it_is_supposed_to_explain() -> None:
    run = simulate(7, PHASE2_CONFIG, PHASE2_ARENA)
    curve = activation_curve(run)
    evaluation = evaluate(run)
    by_count = {count: moment for moment, count in curve}
    for name, spec in MILESTONES:
        index = milestone_index(spec, run.total_tiles)
        if evaluation.milestones[name] is not None:
            assert by_count[index] == pytest.approx(evaluation.milestones[name])


# --------------------------------------------------------------------------
# Speed is a change of clock: the claim the whole speed analysis rests on.
# --------------------------------------------------------------------------


def test_zero_gravity_makes_speed_a_pure_rescaling_of_the_clock() -> None:
    result = verify_speed_invariance(
        list(range(12)), [30.0, 50.0, 70.0, 120.0], 60.0, PHASE2_ARENA, PHASE2_CONFIG
    )
    assert result["invariant"]
    assert result["worst_relative_time_error"] < 1.0e-12
    assert all(row["same_tile_sequence"] for row in result["rows"])


def test_the_same_claim_does_not_hold_once_gravity_is_switched_on() -> None:
    """The invariance is a property of gravity 0, not of the solver.

    Worth pinning: if this ever starts passing under gravity, the check above
    has stopped measuring anything.
    """
    heavy = TileEscapeConfig(**{**PHASE2_CONFIG.as_dict(), "gravity": 12.0, "duration": 400.0})
    result = verify_speed_invariance(
        list(range(4)), [30.0, 120.0], 60.0, PHASE2_ARENA, heavy
    )
    assert not result["invariant"]


def test_a_rescaled_clock_matches_a_rerun_at_that_speed() -> None:
    for seed in (1, 7, 19):
        reference = simulate(seed, PHASE2_CONFIG, PHASE2_ARENA)
        for speed in (45.0, 90.0):
            actual = simulate(
                seed,
                TileEscapeConfig(**{**PHASE2_CONFIG.as_dict(), "speed": speed}),
                PHASE2_ARENA,
            )
            predicted = rescale_to_speed(reference.completion_time, 60.0, speed)
            assert actual.completion_time == pytest.approx(predicted, rel=1e-9)


def test_arena_scale_and_speed_are_one_dial_and_not_two() -> None:
    """Halving the arena and the speed together must reproduce the run exactly.

    Only `speed / circumradius` is physical, so a Phase 2 that tuned both would
    be turning one knob twice and reporting it as two findings.
    """
    half_arena = polygon_arena(sides=17, tiles_per_side=3, circumradius=5.0)
    half_config = TileEscapeConfig(
        **{**PHASE2_CONFIG.as_dict(), "speed": 30.0, "ball_radius": 0.225}
    )
    for seed in (1, 7, 19):
        base = simulate(seed, PHASE2_CONFIG, PHASE2_ARENA)
        small = simulate(seed, half_config, half_arena)
        assert [c.tile_index for c in small.collisions] == [
            c.tile_index for c in base.collisions
        ]
        assert small.completion_time == pytest.approx(base.completion_time, rel=1e-9)


# --------------------------------------------------------------------------
# Batch reproducibility.
# --------------------------------------------------------------------------


def test_the_same_seed_range_evaluates_identically_twice() -> None:
    first = [e.as_dict() for e in sweep(range(40), PHASE2_CONFIG, PHASE2_ARENA)]
    second = [e.as_dict() for e in sweep(range(40), PHASE2_CONFIG, PHASE2_ARENA)]
    assert first == second


def test_a_seeds_evaluation_does_not_depend_on_the_batch_it_was_run_in() -> None:
    """Order independence: no state may leak from one seed's run into the next."""
    forward = {e.seed: e.as_dict() for e in sweep(range(30), PHASE2_CONFIG, PHASE2_ARENA)}
    backward = {
        e.seed: e.as_dict() for e in sweep(range(29, -1, -1), PHASE2_CONFIG, PHASE2_ARENA)
    }
    alone = {
        seed: evaluate(simulate(seed, PHASE2_CONFIG, PHASE2_ARENA)).as_dict()
        for seed in (0, 13, 29)
    }
    assert forward == backward
    for seed, expected in alone.items():
        assert forward[seed] == expected


def test_the_shortlist_is_a_deterministic_function_of_the_population() -> None:
    evaluations = sweep(range(600), PHASE2_CONFIG, PHASE2_ARENA)
    first = [c.seed for c in shortlist(evaluations, DEFAULT_RULE, 10)]
    second = [c.seed for c in shortlist(list(reversed(evaluations)), DEFAULT_RULE, 10)]
    assert first == second
    assert len(first) == len(set(first))
    scores = [c.score.total for c in shortlist(evaluations, DEFAULT_RULE, 10)]
    assert scores == sorted(scores, reverse=True)


def test_every_shortlisted_seed_passes_every_condition() -> None:
    evaluations = sweep(range(600), PHASE2_CONFIG, PHASE2_ARENA)
    for candidate in shortlist(evaluations, DEFAULT_RULE, 10):
        assert candidate.verdict.accepted
        assert candidate.verdict.failures == ()
        reproduced = evaluate(simulate(candidate.seed, PHASE2_CONFIG, PHASE2_ARENA))
        assert reproduced.as_dict() == candidate.evaluation.as_dict()


def test_a_batch_run_in_a_fresh_interpreter_agrees_with_this_one() -> None:
    """Cross-process, for the same reason Phase 1 checks determinism that way."""
    seed = 7
    expected = evaluate(simulate(seed, PHASE2_CONFIG, PHASE2_ARENA))
    result = subprocess.run(
        [sys.executable, "-m", "satisfying.tile_sweep_cli", "inspect", "--seed", str(seed)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=180,
        env={**os.environ, "PYTHONPATH": REPO_ROOT, "PYTHONHASHSEED": "1"},
    )
    assert result.returncode == 0, result.stderr
    assert f'"completion_seconds": {expected.completion_seconds:.3f}' in result.stdout
    assert f'"collisions": {expected.collisions}' in result.stdout


# --------------------------------------------------------------------------
# The aggregation layer.
# --------------------------------------------------------------------------


def test_percentiles_are_nearest_rank_and_therefore_real_values() -> None:
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    assert percentile(values, 0.50) == 5.0
    assert percentile(values, 0.90) == 9.0
    assert percentile(values, 1.0) == 10.0
    assert percentile(values, 0.0) == 1.0
    assert math.isnan(percentile([], 0.5))
    stats = distribution(values)
    assert stats["p50"] == 5.0 and stats["max"] == 10.0 and stats["count"] == 10
    assert all(stats[key] in values for key in ("min", "p10", "p50", "p90", "max"))


def test_the_population_report_covers_every_group_the_brief_asks_for() -> None:
    report = population_report(sweep(range(120), PHASE2_CONFIG, PHASE2_ARENA))
    for section in (
        "completion",
        "opening",
        "milestones",
        "stagnation",
        "tail",
        "periodic",
        "acceptance",
        "failures",
    ):
        assert section in report, section
    assert report["arena"]["total_tiles"] == PHASE2_TOTAL_TILES
    assert set(report["milestones"]) == {name for name, _ in MILESTONES}
    assert 0.0 <= report["completion"]["completion_rate"] <= 1.0
    assert report["failures"]["seeds"] == 120


def test_the_failure_census_separates_never_finishing_from_finishing_badly() -> None:
    report = population_report(sweep(range(400), PHASE2_CONFIG, PHASE2_ARENA))
    census = report["failures"]
    assert census["incomplete"]["count"] + report["completion"]["completed"] == 400
    assert "too_slow_over_40s" in census["completed_but_unusable"]
    assert "mid_run_dead_zone_over_4s" in census["completed_but_unusable"]
    # A slow finisher is not an incomplete run, and must not be counted as one.
    slow = census["completed_but_unusable"]["too_slow_over_40s"]["count"]
    assert slow <= report["completion"]["completed"]

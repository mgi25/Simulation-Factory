"""Race V0.1 tests: the countdown, ranking, finishing and recovery.

Recovery is the part worth testing hardest, and it cannot be tested on the
prototype course - the whole point of that course is that racers almost
never get stuck on it. So the stuck and out-of-bounds paths are driven on
purpose-built dead-end geometry, where a racer is guaranteed to stop.
"""

from __future__ import annotations

import pytest

from race.config import (
    COUNTDOWN_SECONDS,
    COUNTDOWN_TICKS,
    MAX_RECOVERIES_PER_RACER,
    PHYSICS_HZ,
    RACE_TIMEOUT_SECONDS,
    RECOVERY_PENALTY_SECONDS,
)
from race.course import TRACK, RaceCourse
from race.courses.builder import CourseBuilder
from race.events import (
    EVENT_CHECKPOINT,
    EVENT_COMPLETE,
    EVENT_COUNTDOWN,
    EVENT_FINISH,
    EVENT_RECOVERY,
    EVENT_RETIRED,
    EVENT_START,
    EVENT_WINNER,
    REASON_OUT_OF_BOUNDS,
    REASON_STUCK,
)
from race.manager import RaceManager, RaceState
from race.progress import count_inversions, ranking, update_progress
from race.racer import Racer
from race.simulation import RaceSimulation

STUCK_COURSE_FLOOR = 1000.0


def dead_end_course() -> RaceCourse:
    """A floor with the finish far below it. A racer here can never progress.

    Exactly what a stuck racer looks like from the manager's point of view:
    resting, making no progress, and not finished.
    """
    builder = CourseBuilder("dead-end", 1000.0, 0.0)
    builder.begin_section("run", 0.0)
    builder.ramp((0.0, STUCK_COURSE_FLOOR), (1000.0, STUCK_COURSE_FLOOR), 40.0, TRACK)
    builder.checkpoint("start", 900.0, (500.0, 905.0))
    builder.checkpoint("finish", 5000.0, (500.0, 5010.0))
    for index in range(2):
        builder.spawn(300.0 + index * 400.0, 700.0)
    return builder.finish(6000.0)


def slide_course() -> RaceCourse:
    """A clean run from the grid to a finish, with nothing in the way."""
    builder = CourseBuilder("slide", 1000.0, 0.0)
    builder.begin_section("run", 0.0)
    builder.ramp((0.0, 3000.0), (1000.0, 3000.0), 40.0, TRACK)
    builder.checkpoint("start", 300.0, (500.0, 320.0))
    builder.checkpoint("middle", 1500.0, (500.0, 1520.0))
    builder.checkpoint("finish", 2800.0, (500.0, 2820.0))
    for index in range(3):
        builder.spawn(250.0 + index * 250.0, 150.0)
    return builder.finish(3200.0)


def manager_for(course: RaceCourse, seed: int = 1, racers: int = 2) -> RaceManager:
    return RaceManager(RaceSimulation(seed, course=course, racer_count=racers))


def step_seconds(manager: RaceManager, seconds: float) -> None:
    for _ in range(int(seconds * PHYSICS_HZ)):
        if not manager.step():
            break


def events_of(manager: RaceManager, event_type: str) -> list:
    return [event for event in manager.events if event.type == event_type]


# --- the countdown ----------------------------------------------------------


def test_a_race_starts_in_the_countdown_with_the_gate_shut() -> None:
    manager = RaceManager(RaceSimulation(1))
    assert manager.state is RaceState.COUNTDOWN
    assert not manager.started
    assert not manager.sim.gates_open
    assert manager.race_time == pytest.approx(-COUNTDOWN_SECONDS)


def test_the_countdown_announces_every_second_once() -> None:
    manager = RaceManager(RaceSimulation(1))
    step_seconds(manager, COUNTDOWN_SECONDS + 0.5)
    counted = [event.detail for event in events_of(manager, EVENT_COUNTDOWN)]
    assert counted == ["3", "2", "1"]
    assert len(events_of(manager, EVENT_START)) == 1


def test_the_gate_opens_exactly_when_the_countdown_ends() -> None:
    manager = RaceManager(RaceSimulation(1))
    step_seconds(manager, COUNTDOWN_SECONDS - 0.05)
    assert not manager.sim.gates_open
    assert manager.state is RaceState.COUNTDOWN
    step_seconds(manager, 0.1)
    assert manager.sim.gates_open
    assert manager.state is RaceState.RUNNING
    assert manager.started


def test_the_race_clock_starts_at_zero_on_the_gate() -> None:
    manager = RaceManager(RaceSimulation(1))
    step_seconds(manager, COUNTDOWN_SECONDS)
    assert manager.sim.ticks == COUNTDOWN_TICKS
    assert manager.race_time == pytest.approx(0.0)


def test_the_countdown_number_counts_down_and_then_stops() -> None:
    manager = RaceManager(RaceSimulation(1))
    assert manager.countdown_number == 3
    step_seconds(manager, 1.0)
    assert manager.countdown_number == 2
    step_seconds(manager, 2.0)
    assert manager.countdown_number == 0


def test_nothing_is_tracked_before_the_gate_opens() -> None:
    """A racer resting on the gate is not stuck, and has not overtaken anyone."""
    manager = RaceManager(RaceSimulation(1))
    step_seconds(manager, COUNTDOWN_SECONDS - 0.1)
    assert manager.recoveries == 0
    assert manager.overtakes == 0
    assert manager.leader_changes == 0
    assert all(racer.stuck_ticks == 0 for racer in manager.sim.racers)


# --- finishing --------------------------------------------------------------


def test_a_racer_finishes_once_with_a_time_and_a_position() -> None:
    manager = manager_for(slide_course(), racers=3)
    manager.run()
    assert manager.winner is not None
    assert manager.racers_finished == 3
    finishes = events_of(manager, EVENT_FINISH)
    assert len(finishes) == 3
    assert [event.detail for event in finishes] == ["1", "2", "3"]
    for racer in manager.finish_order:
        assert racer.finished
        assert racer.finish_time is not None and racer.finish_time > 0.0
        assert racer.finish_tick is not None


def test_the_winner_is_announced_once_and_is_the_first_finisher() -> None:
    manager = manager_for(slide_course(), racers=3)
    manager.run()
    winners = events_of(manager, EVENT_WINNER)
    assert len(winners) == 1
    assert winners[0].racer_id == manager.winner.racer_id
    assert manager.winner is manager.finish_order[0]
    assert manager.winner_time == pytest.approx(manager.winner.finish_time)


def test_finish_order_is_by_crossing_time() -> None:
    manager = manager_for(slide_course(), racers=3)
    manager.run()
    times = [racer.finish_time for racer in manager.finish_order]
    assert times == sorted(times)


def test_crossing_the_line_again_does_not_finish_a_racer_twice() -> None:
    """A finisher rolling back over the plane must not re-register."""
    manager = manager_for(slide_course(), racers=1)
    manager.run()
    racer = manager.finish_order[0]
    first_tick = racer.finish_tick
    # Put it back above the line and drive it across again.
    racer.teleport((500.0, manager.course.finish_y - 200.0))
    update_progress(manager.course, racer)
    racer.teleport((500.0, manager.course.finish_y + 50.0))
    manager._update_positions()
    assert manager.racers_finished == 1
    assert racer.finish_tick == first_tick
    assert len(events_of(manager, EVENT_FINISH)) == 1


def test_the_winner_does_not_stop_the_race_immediately() -> None:
    """The pack behind still has to get its finish order recorded."""
    manager = manager_for(slide_course(), racers=3)
    while manager.winner is None and manager.step():
        pass
    assert manager.state is RaceState.FINISHING
    assert not manager.complete
    assert any(racer.racing for racer in manager.sim.racers)


def test_checkpoint_crossings_are_recorded_in_order() -> None:
    manager = manager_for(slide_course(), racers=1)
    manager.run()
    crossed = [event.value for event in events_of(manager, EVENT_CHECKPOINT)]
    assert crossed == [0.0, 1.0], "start and middle; the finish is its own event"


def test_a_race_completes_and_says_why() -> None:
    manager = manager_for(slide_course(), racers=2)
    manager.run()
    assert manager.complete
    assert manager.duration is not None and manager.duration > 0.0
    completions = events_of(manager, EVENT_COMPLETE)
    assert len(completions) == 1
    assert completions[0].detail == "finished"
    assert not manager.timed_out


def test_a_race_nobody_can_finish_ends_without_a_winner() -> None:
    """A dead end runs out of racers before it runs out of clock.

    Recovery retries a stuck racer a few times and then retires it, so this
    race ends because nobody is left in it - not on the timeout. Both are
    reported as failures by the telemetry; they are different failures.
    """
    manager = manager_for(dead_end_course(), racers=1)
    manager.run()
    assert manager.complete
    assert manager.winner is None
    assert manager.retirements == 1
    assert not manager.timed_out
    assert events_of(manager, EVENT_COMPLETE)[0].detail == "finished"


def test_a_race_that_will_not_end_is_cut_off_by_the_timeout() -> None:
    """The last resort, so a batch run can never hang on one bad seed.

    Driven by moving the clock rather than by simulating seventy seconds of
    a race going nowhere: the branch under test is the time limit itself.
    """
    manager = manager_for(slide_course(), racers=1)
    step_seconds(manager, COUNTDOWN_SECONDS + 0.5)
    manager.sim.ticks = (
        COUNTDOWN_TICKS + int(RACE_TIMEOUT_SECONDS * PHYSICS_HZ) - 1
    )
    manager.step()
    assert manager.complete
    assert manager.timed_out
    assert manager.race_time >= RACE_TIMEOUT_SECONDS
    assert events_of(manager, EVENT_COMPLETE)[0].detail == "timeout"


def test_stepping_a_complete_race_does_nothing() -> None:
    manager = manager_for(slide_course(), racers=1)
    manager.run()
    ticks, events = manager.sim.ticks, len(manager.events)
    assert manager.step() is False
    assert manager.sim.ticks == ticks
    assert len(manager.events) == events


# --- ranking ----------------------------------------------------------------


def test_ranking_puts_finishers_first_in_crossing_order() -> None:
    early = Racer(0, (0.0, 0.0))
    late = Racer(1, (0.0, 0.0))
    running = Racer(2, (0.0, 0.0))
    early.finished, early.finish_tick = True, 100
    late.finished, late.finish_tick = True, 200
    running.progress = 99.0
    order = ranking([running, late, early])
    assert [racer.racer_id for racer in order] == [0, 1, 2]


def test_ranking_orders_the_unfinished_by_course_progress() -> None:
    ahead = Racer(0, (0.0, 0.0))
    behind = Racer(1, (0.0, 0.0))
    ahead.progress, behind.progress = 4.5, 2.0
    assert [r.racer_id for r in ranking([behind, ahead])] == [0, 1]


def test_a_retired_racer_ranks_last_however_far_it_got() -> None:
    retired = Racer(0, (0.0, 0.0))
    running = Racer(1, (0.0, 0.0))
    retired.retired, retired.progress = True, 9.0
    running.progress = 0.1
    assert [r.racer_id for r in ranking([retired, running])] == [1, 0]


def test_ranking_breaks_ties_by_racer_id_not_by_list_order() -> None:
    first = Racer(0, (0.0, 0.0))
    second = Racer(1, (0.0, 0.0))
    first.progress = second.progress = 3.0
    assert [r.racer_id for r in ranking([second, first])] == [0, 1]
    assert [r.racer_id for r in ranking([first, second])] == [0, 1]


def test_ranks_are_written_onto_the_racers() -> None:
    manager = manager_for(slide_course(), racers=3)
    step_seconds(manager, COUNTDOWN_SECONDS + 1.0)
    assert sorted(racer.rank for racer in manager.sim.racers) == [1, 2, 3]
    assert manager.ranked[0].rank == 1


def test_progress_credit_is_kept_when_a_racer_is_knocked_backwards() -> None:
    """A checkpoint reached stays reached; live progress can still fall."""
    course = slide_course()
    racer = Racer(0, (500.0, 1600.0))
    assert update_progress(course, racer) == [0, 1]
    assert racer.checkpoint == 1
    forward = racer.progress

    racer.teleport((500.0, 400.0))
    assert update_progress(course, racer) == []
    assert racer.checkpoint == 1, "credit for a plane already passed is kept"
    assert racer.progress < forward, "but losing ground has to cost something"


def test_count_inversions_counts_each_swapped_pair_once() -> None:
    assert count_inversions([1, 2, 3], [1, 2, 3]) == 0
    assert count_inversions([1, 2, 3], [2, 1, 3]) == 1
    # One racer passing three others is three overtakes, not one.
    assert count_inversions([1, 2, 3, 4], [4, 1, 2, 3]) == 3
    assert count_inversions([1, 2, 3], [3, 2, 1]) == 3


def test_count_inversions_ignores_racers_that_left_the_ranking() -> None:
    assert count_inversions([1, 2, 3], [3, 1]) == 1


def test_lead_changes_are_counted_while_the_race_is_undecided() -> None:
    manager = manager_for(slide_course(), racers=3)
    manager.run()
    assert manager.leader_id is not None
    # Never negative, and never counted before there is a leader to change.
    assert manager.leader_changes >= 0
    assert manager.overtakes >= 0


# --- stuck recovery ---------------------------------------------------------


def test_a_stuck_racer_is_recovered_to_its_last_checkpoint() -> None:
    manager = manager_for(dead_end_course(), racers=1)
    racer = manager.sim.racers[0]
    while manager.recoveries == 0 and manager.step():
        pass
    assert manager.recoveries == 1
    assert racer.recoveries == 1
    respawn = manager.course.checkpoint(0).respawn
    # It was put back at the respawn point and left there at rest.
    assert racer.position.x == pytest.approx(respawn[0])
    assert racer.position.y == pytest.approx(respawn[1])


def test_a_recovery_is_never_silent() -> None:
    """Moving a racer by hand always leaves a record."""
    manager = manager_for(dead_end_course(), racers=1)
    while manager.recoveries == 0 and manager.step():
        pass
    recoveries = events_of(manager, EVENT_RECOVERY)
    assert len(recoveries) == 1
    assert recoveries[0].detail == REASON_STUCK
    assert recoveries[0].racer_id == 0
    assert recoveries[0].value == 0.0, "it went back to checkpoint 0"


def test_a_recovery_costs_a_time_penalty() -> None:
    manager = manager_for(dead_end_course(), racers=1)
    racer = manager.sim.racers[0]
    while manager.recoveries == 0 and manager.step():
        pass
    assert racer.time_penalty == pytest.approx(RECOVERY_PENALTY_SECONDS)


def test_a_racer_in_a_queue_is_not_treated_as_stuck() -> None:
    """Slow and going nowhere for a moment is what a queue looks like."""
    manager = manager_for(dead_end_course(), racers=1)
    step_seconds(manager, COUNTDOWN_SECONDS + 2.0)
    assert manager.recoveries == 0, "two seconds of stillness is not stuck yet"
    assert manager.sim.racers[0].stuck_ticks > 0, "but it is being watched"


def test_a_racer_that_keeps_moving_is_never_recovered() -> None:
    manager = manager_for(slide_course(), racers=3)
    manager.run()
    assert manager.recoveries == 0
    assert all(racer.recoveries == 0 for racer in manager.sim.racers)


def test_recovery_gives_up_after_a_few_attempts_and_retires_the_racer() -> None:
    manager = manager_for(dead_end_course(), racers=1)
    racer = manager.sim.racers[0]
    manager.run()
    assert racer.recoveries == MAX_RECOVERIES_PER_RACER
    assert racer.retired
    assert not racer.racing
    assert manager.retirements == 1
    retired = events_of(manager, EVENT_RETIRED)
    assert len(retired) == 1
    assert retired[0].racer_id == 0


def test_a_retired_racer_leaves_the_world_so_it_cannot_obstruct() -> None:
    manager = manager_for(dead_end_course(), racers=2)
    manager.run()
    for racer in manager.sim.racers:
        if racer.retired:
            assert racer.space is None
            assert racer.shape not in manager.sim.space.shapes


def test_a_race_ends_once_every_racer_is_out_of_it() -> None:
    """Two racers on a dead end: both retire, and the race stops."""
    manager = manager_for(dead_end_course(), racers=2)
    manager.run()
    assert manager.complete
    assert all(not racer.racing for racer in manager.sim.racers)


# --- out-of-bounds recovery -------------------------------------------------


def test_a_racer_that_leaves_the_course_is_recovered_at_once() -> None:
    """No waiting period: off the course is not a state to sit in."""
    manager = manager_for(slide_course(), racers=1)
    step_seconds(manager, COUNTDOWN_SECONDS + 0.2)
    racer = manager.sim.racers[0]
    racer.teleport((-4000.0, -4000.0))
    manager.step()
    assert manager.recoveries == 1
    assert not manager.course.out_of_bounds(racer.position.x, racer.position.y)
    assert events_of(manager, EVENT_RECOVERY)[0].detail == REASON_OUT_OF_BOUNDS


def test_a_racer_whose_position_stops_being_a_number_is_recovered() -> None:
    manager = manager_for(slide_course(), racers=1)
    step_seconds(manager, COUNTDOWN_SECONDS + 0.2)
    racer = manager.sim.racers[0]
    racer.body.position = (float("nan"), float("nan"))
    manager.step()
    assert manager.recoveries == 1
    assert racer.is_finite()
    assert manager.sim.is_state_valid()


def test_recovery_puts_a_racer_back_no_further_on_than_it_had_reached() -> None:
    manager = manager_for(slide_course(), racers=1)
    racer = manager.sim.racers[0]
    # Let it pass the middle checkpoint, then throw it off the course.
    while racer.checkpoint < 1 and manager.step():
        pass
    assert racer.checkpoint == 1
    racer.teleport((5000.0, 500.0))
    manager.step()
    expected = manager.course.checkpoint(1).respawn
    assert racer.position.y == pytest.approx(expected[1])
    assert manager.course.progress_at(racer.position.y) < 2.0


# --- the whole race ---------------------------------------------------------


def test_the_prototype_course_produces_a_complete_race() -> None:
    manager = RaceManager(RaceSimulation(4242))
    manager.run()
    assert manager.complete
    assert not manager.timed_out
    assert manager.winner is not None
    assert manager.racers_finished >= 5
    assert 10.0 < manager.winner_time < 30.0


def test_the_same_seed_gives_the_same_result() -> None:
    def result(seed: int) -> tuple:
        manager = RaceManager(RaceSimulation(seed))
        manager.run()
        return (
            manager.winner.name,
            round(manager.winner_time, 6),
            tuple(racer.name for racer in manager.finish_order),
            manager.leader_changes,
            manager.overtakes,
        )

    assert result(4242) == result(4242)


def test_different_seeds_give_different_races() -> None:
    results = set()
    for seed in range(30, 40):
        manager = RaceManager(RaceSimulation(seed))
        manager.run()
        results.add((manager.winner.name, round(manager.winner_time, 3)))
    assert len(results) >= 8, "ten seeds should not collapse onto one outcome"


def test_positions_change_during_a_race() -> None:
    """A race where nobody ever passes anybody is not a race."""
    changed = 0
    for seed in range(50, 60):
        manager = RaceManager(RaceSimulation(seed))
        manager.run()
        if manager.overtakes > 0:
            changed += 1
    assert changed == 10

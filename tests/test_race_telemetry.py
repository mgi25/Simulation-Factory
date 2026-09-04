"""Race V0.1 tests: telemetry, the summary block and the camera.

The telemetry tests care about honesty more than formatting: a race that
timed out, produced no winner or lost racers has to say so, because the
whole point of collecting this is to find out how often that happens.
"""

from __future__ import annotations

import pytest

from engine.arena import CANVAS_HEIGHT
from race.camera import FOCUS_GROUP, LEAD_FRACTION, RaceCamera
from race.config import RACER_COUNT
from race.manager import RaceManager
from race.racer import Racer
from race.simulation import RaceSimulation
from race.telemetry import format_finish_order, format_summary, race_summary
from tests.test_race_manager import (
    dead_end_course,
    manager_for,
    slide_course,
    step_seconds,
)


@pytest.fixture(scope="module")
def finished_race() -> RaceManager:
    manager = RaceManager(RaceSimulation(4242))
    manager.run()
    return manager


# --- the summary ------------------------------------------------------------


def test_summary_reports_every_field_the_brief_asks_for(
    finished_race: RaceManager,
) -> None:
    summary = race_summary(finished_race)
    for field in (
        "seed",
        "race_duration",
        "winner",
        "finish_order",
        "finish_times",
        "leader_changes",
        "racers_finished",
        "racers_stuck",
        "overtakes",
        "large_collisions",
    ):
        assert field in summary, field
    assert summary["seed"] == 4242
    assert summary["course"] == "prototype"
    assert summary["racer_count"] == RACER_COUNT


def test_summary_is_plain_json_compatible_data(finished_race: RaceManager) -> None:
    """It gets written to disk by the batch tool, so no objects allowed."""
    import json

    encoded = json.dumps(race_summary(finished_race))
    assert json.loads(encoded)["seed"] == 4242


def test_summary_finish_order_and_times_line_up(finished_race: RaceManager) -> None:
    summary = race_summary(finished_race)
    assert len(summary["finish_order"]) == summary["racers_finished"]
    assert len(summary["finish_times"]) == summary["racers_finished"]
    assert summary["finish_times"] == sorted(summary["finish_times"])
    assert summary["winner"] == summary["finish_order"][0]
    assert summary["winner_time"] == pytest.approx(summary["finish_times"][0])


def test_summary_names_the_racers_that_did_not_finish(
    finished_race: RaceManager,
) -> None:
    summary = race_summary(finished_race)
    assert len(summary["unfinished"]) == RACER_COUNT - summary["racers_finished"]
    assert not set(summary["unfinished"]) & set(summary["finish_order"])


def test_a_completed_race_says_it_completed(finished_race: RaceManager) -> None:
    summary = race_summary(finished_race)
    assert summary["completed"]
    assert not summary["timed_out"]
    assert summary["state"] == "complete"


def test_official_times_carry_recovery_penalties_without_reordering() -> None:
    """The order on screen is crossing order; the penalty is recorded beside it."""
    manager = manager_for(slide_course(), racers=2)
    manager.run()
    winner = manager.finish_order[0]
    winner.time_penalty = 5.0
    summary = race_summary(manager)
    assert summary["finish_order"][0] == winner.name
    assert summary["official_times"][0] == pytest.approx(
        summary["finish_times"][0] + 5.0
    )


def test_a_failed_race_is_reported_as_failed() -> None:
    manager = manager_for(dead_end_course(), racers=1)
    manager.run()
    summary = race_summary(manager)
    assert summary["winner"] is None
    assert summary["winner_time"] is None
    assert summary["racers_finished"] == 0
    assert summary["racers_retired"] == 1
    assert summary["finish_spread"] is None


def test_summary_works_on_a_race_still_in_its_countdown() -> None:
    """Telemetry must never be the thing that crashes a run."""
    manager = RaceManager(RaceSimulation(1))
    step_seconds(manager, 1.0)
    summary = race_summary(manager)
    assert summary["state"] == "countdown"
    assert summary["race_duration"] is None
    assert summary["winner"] is None
    assert not summary["completed"]


def test_finish_spread_measures_first_to_last(finished_race: RaceManager) -> None:
    summary = race_summary(finished_race)
    if summary["racers_finished"] >= 2:
        assert summary["finish_spread"] == pytest.approx(
            summary["finish_times"][-1] - summary["finish_times"][0]
        )


def test_recoveries_are_counted_per_racer_and_in_total() -> None:
    manager = manager_for(dead_end_course(), racers=1)
    manager.run()
    summary = race_summary(manager)
    assert summary["racers_stuck"] == 1
    assert summary["recoveries"] == manager.recoveries > 1


# --- formatting -------------------------------------------------------------


def test_summary_block_has_the_shape_the_brief_specified(
    finished_race: RaceManager,
) -> None:
    text = format_summary(finished_race)
    assert text.startswith("=== RACE COMPLETE ===")
    for label in ("Seed:", "Winner:", "Time:", "Leader Changes:", "Finished:", "Stuck:"):
        assert label in text
    assert str(finished_race.sim.seed) in text
    assert finished_race.winner.name in text


def test_a_timed_out_race_is_headed_differently() -> None:
    manager = manager_for(slide_course(), racers=1)
    manager.timed_out = True
    assert format_summary(manager).startswith("=== RACE TIMED OUT ===")


def test_finish_order_block_numbers_finishers_and_marks_the_rest(
    finished_race: RaceManager,
) -> None:
    text = format_finish_order(finished_race)
    lines = text.splitlines()
    assert lines[0].strip().startswith("1.")
    assert finished_race.winner.name in lines[0]
    summary = race_summary(finished_race)
    for name in summary["unfinished"]:
        assert name in text
    assert text.count("DNF") + text.count("RETIRED") == len(summary["unfinished"])


def test_the_summary_shows_a_recovery_penalty_when_there_was_one() -> None:
    manager = manager_for(slide_course(), racers=1)
    manager.run()
    manager.finish_order[0].time_penalty = 1.5
    assert "recovery" in format_finish_order(manager)


# --- the camera -------------------------------------------------------------


def camera_for(seed: int = 1) -> tuple[RaceCamera, RaceManager]:
    manager = RaceManager(RaceSimulation(seed))
    camera = RaceCamera(manager.course, CANVAS_HEIGHT)
    return camera, manager


def test_the_camera_starts_inside_the_course() -> None:
    camera, _ = camera_for()
    assert camera.top >= camera.course.top
    assert camera.bottom <= camera.course.bottom + 1.0


def test_the_camera_never_leaves_the_course() -> None:
    camera, manager = camera_for(4242)
    while manager.step():
        camera.update(manager.sim.racers, 1.0 / 60.0)
        assert camera.top >= camera.course.top - 1e-6
        assert camera.top <= camera.course.top + camera.travel + 1e-6


def test_the_camera_only_ever_moves_down_the_course() -> None:
    """A race runs downhill; a camera that jerked back would be unwatchable."""
    camera, manager = camera_for(4242)
    previous = camera.top
    while manager.step():
        camera.update(manager.sim.racers, 1.0 / 60.0)
        assert camera.top >= previous - 1e-6
        previous = camera.top


def test_the_camera_follows_the_field_down_the_course() -> None:
    camera, manager = camera_for(4242)
    start = camera.top
    manager.run()
    camera.snap_to(manager.sim.racers)
    assert camera.top > start + CANVAS_HEIGHT


def test_the_camera_frames_the_leading_group_not_the_leader() -> None:
    """Framing on first place alone puts the racer being passed off screen."""
    camera, manager = camera_for()
    racers = []
    for index in range(4):
        racer = Racer(index, (500.0, 1000.0 + index * 400.0))
        racer.rank = index + 1
        racers.append(racer)
    focus = camera.focus(racers)
    leaders = racers[:FOCUS_GROUP]
    assert focus == pytest.approx(
        sum(r.position.y for r in leaders) / len(leaders)
    )
    assert focus != racers[0].position.y


def test_the_camera_ignores_a_retired_racer() -> None:
    camera, _ = camera_for()
    alive = Racer(0, (500.0, 2000.0))
    alive.rank = 1
    gone = Racer(1, (500.0, 5000.0))
    gone.rank = 2
    gone.retired = True
    assert camera.focus([alive, gone]) == pytest.approx(2000.0)


def test_the_camera_keeps_the_focus_above_centre() -> None:
    """More course ahead than behind: a viewer wants to see what is coming."""
    assert 0.0 < LEAD_FRACTION < 0.5


def test_the_camera_eases_rather_than_snapping() -> None:
    camera, manager = camera_for()
    camera.snap_to(manager.sim.racers)
    for racer in manager.sim.racers:
        racer.teleport((500.0, 4000.0))
        racer.rank = 1
    before = camera.top
    camera.update(manager.sim.racers, 1.0 / 60.0)
    eased = camera.top
    assert eased > before, "it moved"
    camera.snap_to(manager.sim.racers)
    assert camera.top > eased, "but nowhere near as far as a snap"


def test_visible_answers_whether_something_is_in_frame() -> None:
    camera, _ = camera_for()
    assert camera.visible(camera.top + 10.0)
    assert not camera.visible(camera.bottom + 500.0)
    assert camera.visible(camera.bottom + 500.0, margin=600.0)


def test_a_camera_taller_than_its_course_cannot_travel() -> None:
    camera, manager = camera_for()
    tall = RaceCamera(manager.course, manager.course.height * 2.0)
    assert tall.travel == 0.0
    tall.update(manager.sim.racers, 1.0)
    assert tall.top == pytest.approx(manager.course.top)


def test_the_frame_is_the_portrait_canvas_the_content_is_cut_for() -> None:
    from engine.arena import CANVAS_WIDTH

    camera, manager = camera_for()
    assert camera.viewport_width == pytest.approx(CANVAS_WIDTH)
    assert camera.viewport_height == pytest.approx(CANVAS_HEIGHT)
    assert CANVAS_WIDTH / CANVAS_HEIGHT == pytest.approx(9 / 16)

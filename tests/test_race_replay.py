"""V0.2 tests: deterministic race replay export.

The counterpart of `test_replay.py`, which asks the same questions of a duel.
What a replay has to be is the same in both modes: complete enough that a
renderer needs nothing else, faithful enough that it describes the run that
actually happened, and identical every time the same seed is exported.
"""

from __future__ import annotations

import json
import math

import pytest

from engine.arena import CANVAS_HEIGHT, CANVAS_WIDTH
from race.camera import RaceCamera
from race.config import PHYSICS_DT, PHYSICS_HZ, RACE_TIMEOUT_SECONDS
from race.courses import DEFAULT_COURSE, SPLIT_COURSE_ID
from race.events import EVENT_TYPES
from race.manager import RaceManager
from race.simulation import RaceSimulation
from replay.race_exporter import (
    MODE_RACE,
    RACE_REPLAY_VERSION,
    REPLAY_FPS,
    TICKS_PER_FRAME,
    record_race,
    write_replay,
)

SEED = 1000
SPLIT_SEED = 1007


@pytest.fixture(scope="module")
def replay() -> dict:
    return record_race(SEED)


@pytest.fixture(scope="module")
def split_replay() -> dict:
    return record_race(SPLIT_SEED, course_name=SPLIT_COURSE_ID)


# --- schema ---------------------------------------------------------------


def test_metadata_describes_the_simulation(replay: dict) -> None:
    assert replay["version"] == RACE_REPLAY_VERSION == 1
    assert replay["mode"] == MODE_RACE == "race"
    assert replay["seed"] == SEED
    assert replay["fps"] == REPLAY_FPS == 60
    assert replay["physics_hz"] == PHYSICS_HZ
    assert replay["ticks_per_frame"] == TICKS_PER_FRAME == 2
    assert replay["limit_seconds"] == RACE_TIMEOUT_SECONDS
    assert replay["canvas"] == {"width": CANVAS_WIDTH, "height": CANVAS_HEIGHT}
    assert replay["course_id"] == DEFAULT_COURSE


def test_the_mode_is_what_tells_the_two_replay_kinds_apart() -> None:
    """A race says so; a battle is what a replay with no mode is.

    The whole compatibility story rests on this. Every replay exported before
    race mode existed has no `mode` field and never will, so a reader that
    defaults to battle plays all of them, and only a file that explicitly
    claims to be a race is treated as one.
    """
    from replay.exporter import record_battle

    battle = record_battle(12345)
    assert "mode" not in battle
    assert battle.get("mode", "battle") == "battle"
    assert record_race(SEED)["mode"] == "race"


def test_the_replay_is_plain_json(replay: dict) -> None:
    """No Python objects, no timestamps, no paths, no non-finite numbers.

    `allow_nan=False` is the load-bearing part: a NaN would serialise as the
    bare token `NaN`, which is not JSON at all and which Godot's parser
    rejects, so a single non-finite coordinate would produce a file that
    looked written and could not be played.
    """
    text = json.dumps(replay, allow_nan=False, sort_keys=True)
    assert json.loads(text) == replay


def test_racer_metadata_is_complete(replay: dict) -> None:
    sim = RaceSimulation(SEED)
    assert len(replay["racers"]) == len(sim.racers)
    for meta, racer in zip(replay["racers"], sim.racers):
        assert meta["id"] == racer.racer_id
        assert meta["name"] == racer.name
        assert meta["color"] == list(racer.color)
        assert meta["radius"] == pytest.approx(racer.radius, abs=1e-3)
        assert meta["spawn_slot"] == racer.spawn_slot
        assert meta["contestant_type"] == "ball"


# --- frames ---------------------------------------------------------------


def test_frames_are_sampled_every_two_physics_ticks(replay: dict) -> None:
    frames = replay["frames"]
    assert frames[0]["tick"] == 0
    assert frames[-1]["tick"] == replay["result"]["finished_tick"]

    steps = {frames[i + 1]["tick"] - frames[i]["tick"] for i in range(len(frames) - 1)}
    # The last step can be short: the race ends on whichever tick it ends on,
    # not on a multiple of the sampling rate.
    assert steps <= {1, TICKS_PER_FRAME}
    assert len(frames) == pytest.approx(
        frames[-1]["tick"] / TICKS_PER_FRAME + 1, abs=1
    )


def test_every_frame_holds_valid_racer_state(replay: dict) -> None:
    course = replay["course"]
    margin = course["out_of_bounds_margin"]
    for frame in replay["frames"]:
        assert isinstance(frame["tick"], int)
        assert len(frame["racers"]) == len(replay["racers"])
        for racer in frame["racers"]:
            for key in ("x", "y", "vx", "vy", "speed", "rotation_degrees"):
                assert math.isfinite(racer[key]), key
            assert 0.0 <= racer["rotation_degrees"] < 360.0
            assert 1 <= racer["rank"] <= len(replay["racers"])
            assert isinstance(racer["finished"], bool)
            assert isinstance(racer["retired"], bool)
            assert racer["recoveries"] >= 0
            assert -margin <= racer["x"] <= course["width"] + margin
            assert course["top"] - margin <= racer["y"] <= course["bottom"] + margin


def test_speed_agrees_with_the_velocity_beside_it(replay: dict) -> None:
    """The convenience field is the vector, not an independent number."""
    for frame in replay["frames"][::37]:
        for racer in frame["racers"]:
            assert racer["speed"] == pytest.approx(
                math.hypot(racer["vx"], racer["vy"]), abs=2e-3
            )


def test_moving_obstacles_are_exported_per_frame(replay: dict) -> None:
    """Every spinner, every frame, with the transform it actually had.

    A renderer must never have to integrate an angular speed to find out
    where an arm is, so the test that matters is that the exported angle is
    the *simulated* one rather than one the spec would predict.
    """
    spinners = replay["course"]["spinners"]
    assert spinners, "the prototype course has spinners"

    for frame in replay["frames"]:
        assert len(frame["spinners"]) == len(spinners)
        for state in frame["spinners"]:
            assert 0.0 <= state["rotation_degrees"] < 360.0
            assert math.isfinite(state["x"]) and math.isfinite(state["y"])

    sim = RaceSimulation(SEED)
    manager = RaceManager(sim)
    for _ in range(200):
        manager.step()
    exported = {
        state["id"]: state
        for state in replay["frames"][100]["spinners"]
    }
    for runtime in sim.track.spinners:
        state = exported[runtime.spinner_id]
        assert state["x"] == pytest.approx(runtime.body.position.x, abs=1e-3)
        assert state["y"] == pytest.approx(runtime.body.position.y, abs=1e-3)
        assert state["rotation_degrees"] == pytest.approx(
            runtime.rotation_degrees % 360.0, abs=1e-2
        )


def test_the_gate_state_is_recorded_rather_than_timed(replay: dict) -> None:
    """A renderer is told the gate is gone; it does not count down to it."""
    opened = [frame["gates_open"] for frame in replay["frames"]]
    assert opened[0] is False
    assert opened[-1] is True
    # Once, and never back again.
    assert opened == sorted(opened)


def test_the_camera_track_matches_a_live_preview(replay: dict) -> None:
    """The recorded camera is the one the preview would have shown.

    Not an approximation of it: the exporter advances the same camera by the
    same fixed step as the interactive loop, so the two agree exactly. This
    is what lets the Godot renderer read the track instead of reimplementing
    the follow logic and hoping the two stay in step.
    """
    sim = RaceSimulation(SEED)
    manager = RaceManager(sim)
    camera = RaceCamera(sim.course, CANVAS_HEIGHT)
    camera.snap_to(sim.racers)

    track = [round(camera.y, 3)]
    while not manager.complete:
        for _ in range(TICKS_PER_FRAME):
            if not manager.step():
                break
        camera.update(sim.racers, TICKS_PER_FRAME * PHYSICS_DT)
        track.append(round(camera.y, 3))

    assert [frame["camera_y"] for frame in replay["frames"]] == track


def test_the_camera_never_runs_back_up_the_course(replay: dict) -> None:
    track = [frame["camera_y"] for frame in replay["frames"]]
    assert track == sorted(track)
    assert replay["camera"]["viewport_height"] == CANVAS_HEIGHT


# --- course geometry ------------------------------------------------------


def test_the_course_is_exported_in_full(replay: dict) -> None:
    """Enough to rebuild the course without importing a course builder."""
    course = replay["course"]
    built = RaceSimulation(SEED).course

    assert course["id"] == built.course_id
    assert course["width"] == pytest.approx(built.width)
    assert course["top"] == pytest.approx(built.top)
    assert course["bottom"] == pytest.approx(built.bottom)
    assert len(course["pieces"]) == len(built.pieces)
    assert len(course["spinners"]) == len(built.spinners)
    assert len(course["checkpoints"]) == len(built.checkpoints)
    assert len(course["spawns"]) == len(built.spawns)
    assert len(course["sections"]) == len(built.sections)
    assert course["finish"]["index"] == built.finish_index
    assert course["max_progress"] == pytest.approx(built.max_progress)

    roles = {piece["role"] for piece in course["pieces"]}
    assert {"wall", "ramp", "peg", "gate"} <= roles
    for piece in course["pieces"]:
        assert piece["type"] in ("box", "circle")
        assert piece["material"] in ("track", "slick", "bouncy")
        for key in ("x", "y", "radius", "width", "height", "rotation_degrees"):
            assert math.isfinite(piece[key]), key


def test_exported_geometry_matches_the_course_it_came_from(replay: dict) -> None:
    built = RaceSimulation(SEED).course
    for exported, piece in zip(replay["course"]["pieces"], built.pieces):
        assert exported["id"] == piece.piece_id
        assert exported["role"] == piece.role
        assert exported["material"] == piece.material.name
        assert exported["x"] == pytest.approx(piece.spec.x, abs=1e-3)
        assert exported["y"] == pytest.approx(piece.spec.y, abs=1e-3)
        assert exported["width"] == pytest.approx(piece.spec.width, abs=1e-3)
        assert exported["height"] == pytest.approx(piece.spec.height, abs=1e-3)
        assert exported["rotation_degrees"] == pytest.approx(
            piece.spec.rotation_degrees, abs=1e-3
        )

    for exported, spec in zip(replay["course"]["spinners"], built.spinners):
        assert exported["id"] == spec.spinner_id
        assert exported["arm_count"] == spec.arm_count
        assert exported["arm_length"] == pytest.approx(spec.arm_length, abs=1e-3)
        assert exported["hub_radius"] == pytest.approx(spec.hub_radius, abs=1e-3)
        assert exported["angular_speed"] == pytest.approx(spec.angular_speed, abs=1e-3)


def test_the_progress_graph_is_exported(replay: dict, split_replay: dict) -> None:
    """A linear course lists one route; a split course lists one per path."""
    assert replay["course"]["branches"] == []
    assert [route["branch"] for route in replay["course"]["routes"]] == [""]

    course = split_replay["course"]
    assert course["branches"] == ["left", "right"]
    routes = {route["branch"]: route["checkpoints"] for route in course["routes"]}
    assert set(routes) == {"left", "right"}

    nodes = {node["index"]: node for node in course["checkpoints"]}
    for branch, indices in routes.items():
        values = [nodes[index]["progress"] for index in indices]
        assert values == sorted(values)
        assert len(set(values)) == len(values)
        # A route is main-line nodes plus its own; never another branch's.
        assert all(nodes[index]["branch"] in ("", branch) for index in indices)
        assert nodes[indices[-1]]["index"] == course["finish"]["index"]

    for node in course["checkpoints"]:
        if node["branch"]:
            assert node["x_min"] is not None or node["x_max"] is not None


# --- events ---------------------------------------------------------------


def test_events_are_preserved_in_order(replay: dict) -> None:
    events = replay["events"]
    assert events
    assert [event["tick"] for event in events] == sorted(
        event["tick"] for event in events
    )
    for event in events:
        assert event["type"] in EVENT_TYPES
        assert set(event) == {
            "tick",
            "race_time",
            "type",
            "racer_id",
            "x",
            "y",
            "value",
            "detail",
        }


def test_the_events_a_race_has_to_report_are_all_there(replay: dict) -> None:
    kinds = {event["type"] for event in replay["events"]}
    assert {
        "countdown",
        "start",
        "checkpoint",
        "finish",
        "winner",
        "complete",
    } <= kinds


def test_events_match_the_race_that_produced_them(replay: dict) -> None:
    sim = RaceSimulation(SEED)
    manager = RaceManager(sim)
    manager.run()

    assert len(replay["events"]) == len(manager.events)
    for exported, event in zip(replay["events"], manager.events):
        assert exported["tick"] == event.tick
        assert exported["type"] == event.type
        assert exported["racer_id"] == event.racer_id
        assert exported["detail"] == event.detail


# --- the result -----------------------------------------------------------


def test_result_matches_the_race_manager(replay: dict) -> None:
    sim = RaceSimulation(SEED)
    manager = RaceManager(sim)
    manager.run()

    result = replay["result"]
    assert result["winner_id"] == (
        None if manager.winner is None else manager.winner.racer_id
    )
    assert result["finished_tick"] == manager.completed_tick
    assert result["duration"] == pytest.approx(manager.duration, abs=1e-3)
    assert result["timed_out"] == manager.timed_out
    assert result["state"] == manager.state.value
    assert result["racers_finished"] == manager.racers_finished
    assert result["leader_changes"] == manager.leader_changes
    assert result["recoveries"] == manager.recoveries
    assert result["retirements"] == manager.retirements

    assert [entry["racer_id"] for entry in result["finish_order"]] == [
        racer.racer_id for racer in manager.finish_order
    ]
    for entry, racer in zip(result["finish_order"], manager.finish_order):
        assert entry["name"] == racer.name
        assert entry["finish_time"] == pytest.approx(racer.finish_time, abs=1e-3)
        assert entry["official_time"] == pytest.approx(racer.official_time, abs=1e-3)


def test_the_final_frame_shows_the_finished_race(replay: dict) -> None:
    final = replay["frames"][-1]
    result = replay["result"]
    assert final["tick"] == result["finished_tick"]

    finished = [racer for racer in final["racers"] if racer["finished"]]
    assert len(finished) == result["racers_finished"]
    if result["winner_id"] is not None:
        winner = next(
            racer for racer in final["racers"] if racer["id"] == result["winner_id"]
        )
        assert winner["finished"] is True
        assert winner["rank"] == 1


def test_finish_order_ranks_match_the_frames(replay: dict) -> None:
    """Rank in the last frame is crossing order, which is what a viewer saw."""
    final = {racer["id"]: racer for racer in replay["frames"][-1]["racers"]}
    for entry in replay["result"]["finish_order"]:
        assert final[entry["racer_id"]]["rank"] == entry["position"]


# --- determinism ----------------------------------------------------------


def test_export_is_deterministic() -> None:
    first = record_race(SEED)
    second = record_race(SEED)
    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_export_is_deterministic_on_a_branching_course() -> None:
    first = record_race(SPLIT_SEED, course_name=SPLIT_COURSE_ID)
    second = record_race(SPLIT_SEED, course_name=SPLIT_COURSE_ID)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_different_seeds_give_different_races() -> None:
    """The determinism check is worthless if every seed exports the same file."""
    first = record_race(SEED)
    second = record_race(SEED + 1)
    assert first["frames"] != second["frames"]


def test_the_replay_is_the_race_the_manager_ran(replay: dict) -> None:
    """Frame by frame, the same positions the live simulation produced.

    The check that makes every other one worth having: an exported replay
    that had drifted from the race it claims to record would still be
    deterministic, still be valid JSON and still render.
    """
    sim = RaceSimulation(SEED)
    manager = RaceManager(sim)

    for index, frame in enumerate(replay["frames"]):
        assert frame["tick"] == sim.ticks
        for exported, racer in zip(frame["racers"], sim.racers):
            assert exported["id"] == racer.racer_id
            assert exported["x"] == pytest.approx(racer.position.x, abs=1e-3)
            assert exported["y"] == pytest.approx(racer.position.y, abs=1e-3)
            assert exported["rank"] == racer.rank
            assert exported["checkpoint"] == racer.checkpoint
            assert exported["branch"] == racer.branch
            assert exported["finished"] is racer.finished
            assert exported["retired"] is racer.retired
        if index == len(replay["frames"]) - 1:
            break
        for _ in range(TICKS_PER_FRAME):
            if not manager.step():
                break


def test_write_replay_roundtrips_as_json(tmp_path, replay: dict) -> None:
    path = tmp_path / "nested" / f"race_{SEED}.json"
    written = write_replay(replay, str(path))

    assert path.exists()
    with open(written, encoding="utf-8") as handle:
        assert json.load(handle) == replay


def test_a_pinned_course_overrides_the_name() -> None:
    """The escape hatch a test uses to record exact geometry."""
    from race.courses import build_course

    course = build_course(SPLIT_COURSE_ID, SPLIT_SEED)
    replay = record_race(SPLIT_SEED, course=course)
    assert replay["course_id"] == SPLIT_COURSE_ID
    assert replay["course"]["branches"] == ["left", "right"]


def test_a_smaller_field_exports_fewer_racers() -> None:
    replay = record_race(SEED, racer_count=4)
    assert len(replay["racers"]) == 4
    assert all(len(frame["racers"]) == 4 for frame in replay["frames"])

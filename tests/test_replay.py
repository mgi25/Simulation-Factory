"""Phase 2.5 tests: deterministic replay export."""

from __future__ import annotations

import json
import math

import pytest

from engine.arena import CANVAS_HEIGHT, CANVAS_WIDTH
from engine.simulation import PHYSICS_HZ, Simulation
from modes.power_battle import BATTLE_DURATION_SECONDS, PowerBattleMode
from replay.exporter import (
    REPLAY_FPS,
    REPLAY_VERSION,
    TICKS_PER_FRAME,
    record_battle,
    write_replay,
)

SEED = 12345


@pytest.fixture(scope="module")
def replay() -> dict:
    return record_battle(SEED)


def test_metadata_describes_the_simulation(replay: dict) -> None:
    assert replay["version"] == REPLAY_VERSION == 3
    assert replay["seed"] == SEED
    assert replay["fps"] == REPLAY_FPS == 60
    assert replay["physics_hz"] == PHYSICS_HZ
    assert replay["ticks_per_frame"] == TICKS_PER_FRAME == 2
    assert replay["limit_seconds"] == BATTLE_DURATION_SECONDS
    assert replay["canvas"] == {"width": CANVAS_WIDTH, "height": CANVAS_HEIGHT}

    sim = Simulation(SEED)
    assert replay["arena"] == {
        "left": sim.arena.left,
        "top": sim.arena.top,
        "right": sim.arena.right,
        "bottom": sim.arena.bottom,
    }

    assert len(replay["fighters"]) == len(sim.balls)
    for meta, ball in zip(replay["fighters"], sim.balls):
        assert meta["id"] == ball.ball_id
        assert meta["name"] == ball.name
        assert meta["color"] == list(ball.color)
        assert meta["radius"] == pytest.approx(ball.base_radius, abs=1e-3)
        assert meta["max_health"] == ball.max_health


def test_frames_are_sampled_every_two_physics_ticks(replay: dict) -> None:
    frames = replay["frames"]
    finished_tick = replay["result"]["finished_tick"]

    assert frames[0]["tick"] == 0
    assert frames[-1]["tick"] == finished_tick

    expected = finished_tick / TICKS_PER_FRAME + 1
    assert abs(len(frames) - expected) <= 1

    steps = {frames[i + 1]["tick"] - frames[i]["tick"] for i in range(len(frames) - 1)}
    assert steps <= {1, TICKS_PER_FRAME}


def test_export_is_deterministic() -> None:
    first = record_battle(SEED)
    second = record_battle(SEED)
    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_result_matches_the_battle_mode(replay: dict) -> None:
    sim = Simulation(SEED)
    mode = PowerBattleMode(sim)
    while mode.step():
        pass

    result = replay["result"]
    expected_winner = None if mode.winner is None else mode.winner.ball_id
    assert result["winner_id"] == expected_winner
    assert result["is_draw"] == mode.is_draw
    assert result["finished_tick"] == mode.finished_tick
    assert result["duration"] == pytest.approx(mode.duration, abs=1e-3)

    for exported, ball in zip(replay["frames"][-1]["fighters"], sim.balls):
        assert exported["health"] == pytest.approx(ball.health, abs=1e-3)
        assert exported["alive"] is ball.alive


def test_every_frame_holds_valid_state(replay: dict) -> None:
    arena = replay["arena"]
    max_health = replay["fighters"][0]["max_health"]

    for frame in replay["frames"]:
        assert isinstance(frame["tick"], int)
        assert len(frame["fighters"]) == len(replay["fighters"])
        for fighter in frame["fighters"]:
            assert math.isfinite(fighter["x"])
            assert math.isfinite(fighter["y"])
            assert math.isfinite(fighter["health"])
            assert 0.0 <= fighter["health"] <= max_health
            assert isinstance(fighter["alive"], bool)
            assert arena["left"] <= fighter["x"] <= arena["right"]
            assert arena["top"] <= fighter["y"] <= arena["bottom"]


def test_final_frame_holds_the_completed_battle(replay: dict) -> None:
    final = replay["frames"][-1]
    result = replay["result"]
    assert final["tick"] == result["finished_tick"]

    by_id = {fighter["id"]: fighter for fighter in final["fighters"]}
    if result["winner_id"] is None:
        assert result["is_draw"]
    else:
        winner = by_id.pop(result["winner_id"])
        loser = next(iter(by_id.values()))
        assert winner["alive"] is True
        assert winner["health"] > 0.0
        assert winner["health"] > loser["health"]


def test_write_replay_roundtrips_as_json(tmp_path, replay: dict) -> None:
    path = tmp_path / "nested" / f"replay_{SEED}.json"
    written = write_replay(replay, str(path))

    assert path.exists()
    with open(written, encoding="utf-8") as handle:
        assert json.load(handle) == replay

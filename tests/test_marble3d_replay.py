"""The marble3d replay format: sufficient on its own, and not the race schema.

Section 19 asks for an experimental production-style 3D replay that does not
touch the existing schema, and section 26 asks that once a seed is selected the
replay is the authority and the renderer never re-simulates. Both of those are
properties of a *file*, so they are testable without a physics engine, and most
of these tests are.
"""

from __future__ import annotations

import json
import math

import pytest

from marble3d.replay import (
    MARBLE3D_FORMAT,
    MARBLE3D_VERSION,
    STATE_FINISHED,
    Event,
    Frame,
    MarbleInfo,
    MarbleSample,
    Replay,
    read_replay,
    write_replay,
)


def sample(marble_id: int = 0, offset: float = 0.0) -> MarbleSample:
    return MarbleSample(
        marble_id=marble_id,
        position=(1.0 + offset, 2.5, -3.25),
        orientation=(0.0, 0.0, 0.0, 1.0),
        velocity=(4.0, -5.0, 6.0),
        spin=(0.5, -0.25, 0.125),
        module="bowl",
        state="running",
    )


def tiny_replay() -> Replay:
    return Replay(
        seed=7,
        physics_hz=240,
        replay_fps=60,
        units={"length": "world unit (wu)"},
        config={"gravity": 245.25},
        machine={"name": "test", "modules": [], "connections": []},
        marbles=[MarbleInfo(0, 0.5, 1.0, 0), MarbleInfo(1, 0.5, 1.0, 1)],
        frames=[
            Frame(0.0, (sample(0), sample(1, 2.0)), {"start.gate": ((0.0, 1.0, 0.0), (0, 0, 0, 1))}),
            Frame(1 / 60, (sample(0, 0.1), sample(1, 2.1)), {}),
        ],
        events=[Event(0.5, "collision", {"a": 0, "b": 1, "speed": 3.0})],
        summary={"finished": 2},
    )


def test_a_replay_round_trips_through_a_file(tmp_path) -> None:
    original = tiny_replay()
    path = write_replay(original, str(tmp_path / "run.json"))
    restored = read_replay(path)
    assert restored.seed == original.seed
    assert restored.physics_hz == original.physics_hz
    assert len(restored.frames) == len(original.frames)
    assert restored.frames[0].marbles[1].position == pytest.approx(
        original.frames[0].marbles[1].position
    )
    assert restored.frames[0].actuators["start.gate"][0] == pytest.approx((0.0, 1.0, 0.0))
    assert restored.events[0].kind == "collision"
    assert restored.events[0].data["a"] == 0


def test_the_same_replay_writes_the_same_bytes(tmp_path) -> None:
    """No timestamps, no paths, no dict ordering: a run is its own record."""
    first = write_replay(tiny_replay(), str(tmp_path / "a.json"))
    second = write_replay(tiny_replay(), str(tmp_path / "b.json"))
    assert open(first, "rb").read() == open(second, "rb").read()


def test_the_digest_sees_a_difference_the_stored_decimals_cannot() -> None:
    """Why determinism is judged on the digest and not on the file.

    Storage rounds to six decimals. A physics engine can diverge in the
    sixteenth decimal on tick one and still agree to six places two hundred
    ticks later while being on a completely different trajectory by tick two
    thousand. The digest is taken from the raw IEEE-754 bytes, before rounding,
    so it cannot be fooled that way.
    """
    left = tiny_replay()
    right = tiny_replay()
    nudged = list(right.frames[0].marbles)
    nudged[0] = MarbleSample(
        marble_id=0,
        position=(nudged[0].position[0] + 1e-12, *nudged[0].position[1:]),
        orientation=nudged[0].orientation,
        velocity=nudged[0].velocity,
        spin=nudged[0].spin,
        module=nudged[0].module,
        state=nudged[0].state,
    )
    right.frames[0] = Frame(right.frames[0].time, tuple(nudged), right.frames[0].actuators)

    assert left.digest() != right.digest()
    payload_left = json.dumps(left.to_json()["frames"])
    payload_right = json.dumps(right.to_json()["frames"])
    assert payload_left == payload_right, "the stored decimals cannot see this and the digest can"


def test_the_digest_ignores_labels_that_are_derived_from_the_numbers() -> None:
    left = tiny_replay()
    right = tiny_replay()
    relabelled = list(right.frames[0].marbles)
    relabelled[0] = MarbleSample(
        marble_id=0,
        position=relabelled[0].position,
        orientation=relabelled[0].orientation,
        velocity=relabelled[0].velocity,
        spin=relabelled[0].spin,
        module="curve",
        state=STATE_FINISHED,
    )
    right.frames[0] = Frame(right.frames[0].time, tuple(relabelled), right.frames[0].actuators)
    assert left.digest() == right.digest()


def test_the_event_stream_has_a_digest_of_its_own() -> None:
    """Two runs can agree on every pose and disagree about event order."""
    left = tiny_replay()
    right = tiny_replay()
    right.events = list(reversed(right.events)) + [Event(0.6, "finish", {"id": 1})]
    assert left.digest() == right.digest()
    assert left.event_digest() != right.event_digest()


def test_the_format_refuses_a_file_that_is_not_one_of_its_own(tmp_path) -> None:
    path = tmp_path / "race.json"
    path.write_text(json.dumps({"version": 3, "mode": "race", "frames": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="not a marble3d replay"):
        read_replay(str(path))


def test_the_format_refuses_a_version_it_does_not_know(tmp_path) -> None:
    payload = tiny_replay().to_json()
    payload["version"] = MARBLE3D_VERSION + 1
    path = tmp_path / "future.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="marble3d replay version"):
        read_replay(str(path))


def test_the_race_replay_schema_is_untouched() -> None:
    """Section 19: this is a separate format, not a widened old one."""
    import replay as race_replay

    assert MARBLE3D_FORMAT == "marble3d"
    assert not hasattr(race_replay, "MARBLE3D_FORMAT")
    # And the marble format identifies itself in a field the race schema has
    # no notion of, so a reader can tell which kind of file it has in one line.
    assert tiny_replay().to_json()["format"] == MARBLE3D_FORMAT


# --- what a renderer needs, present in the file --------------------------


@pytest.mark.parametrize("field", ["position", "orientation", "velocity", "spin"])
def test_every_frame_carries_the_full_state_of_every_marble(field: str) -> None:
    payload = tiny_replay().to_json()
    key = {"position": "p", "orientation": "q", "velocity": "v", "spin": "w"}[field]
    for frame in payload["frames"]:
        assert len(frame["marbles"]) == 2
        for marble in frame["marbles"]:
            assert len(marble[key]) == (4 if field == "orientation" else 3)


def test_a_replay_is_sufficient_for_a_renderer_without_a_simulator() -> None:
    """Section 26, as a list of the things that have to be in the file.

    A renderer that has to recompute any of these is a renderer that needs the
    physics engine, and the whole point of writing the file is that it does not.
    """
    payload = tiny_replay().to_json()
    for key in ("units", "config", "machine", "marbles", "frames", "events", "summary"):
        assert key in payload, key
    assert payload["frames"][0]["actuators"], "moving parts have to be in the file too"
    assert payload["marbles"][0]["radius"] > 0.0


@pytest.mark.parametrize("seed", [7])
def test_a_real_run_writes_and_reads_back_identically(tmp_path, seed: int) -> None:
    pytest.importorskip("pybullet")
    from marble3d.machines import start_bowl_curve
    from marble3d.simulation import simulate

    replay = simulate(seed=seed, machine=start_bowl_curve(), marble_count=3)
    path = write_replay(replay, str(tmp_path / "real.json"))
    restored = read_replay(path)
    assert restored.summary["stored_digest"] == replay.digest()
    assert restored.summary["stored_event_digest"] == replay.event_digest()
    assert len(restored.frames) == len(replay.frames)
    assert restored.machine["name"] == "start_bowl_curve"
    assert restored.environment["python"]
    # The stored decimals are close enough that a renderer sees the same run.
    for stored, live in zip(restored.frames[-1].marbles, replay.frames[-1].marbles):
        assert math.dist(stored.position, live.position) < 1e-5

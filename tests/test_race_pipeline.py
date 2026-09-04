"""V0.2 tests: the production pipeline handling both modes.

The pipeline was written for battles and now carries races as well. Almost
every test here is really the same question asked twice: does this stage do
the right thing with a race, *and* does it still do exactly what it always
did with a battle. The second half is the one that matters most - a race is
new and can be fixed, while a regression in fight mode would be a regression
in work that is already finished.

The rule the whole thing rests on is the same everywhere: a replay with no
`mode` field is a battle. Every replay exported before race mode existed has
no such field, so every one of them still plays.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from rendering import encode
from rendering.render_plan import (
    MODE_BATTLE,
    MODE_RACE,
    RENDER_FORMAT_VERSION,
    RenderPlanError,
    metadata,
    plan_render,
)
from replay.exporter import REPLAY_VERSION, record_battle
from replay.race_exporter import RACE_REPLAY_VERSION, record_race

RACE_SEED = 1000
BATTLE_SEED = 12345


@pytest.fixture(scope="module")
def race() -> dict:
    return record_race(RACE_SEED)


@pytest.fixture(scope="module")
def battle() -> dict:
    return record_battle(BATTLE_SEED)


# --- planning a render ----------------------------------------------------


def test_a_race_replay_plans_a_render(race: dict) -> None:
    plan = plan_render(race, "output/race.json", ".")
    assert plan.mode == MODE_RACE
    assert plan.seed == RACE_SEED
    assert plan.replay_version == RACE_REPLAY_VERSION
    assert plan.gameplay_frames == len(race["frames"])
    assert plan.frame_count == plan.gameplay_frames + plan.post_roll_frames
    assert plan.width == 1080 and plan.height == 1920 and plan.fps == 60


def test_a_battle_replay_still_plans_the_render_it_always_did(battle: dict) -> None:
    plan = plan_render(battle, "output/replay.json", ".")
    assert plan.mode == MODE_BATTLE
    assert plan.seed == BATTLE_SEED
    assert plan.replay_version == REPLAY_VERSION
    assert plan.gameplay_frames == len(battle["frames"])


def test_the_two_modes_plan_identically_apart_from_the_mode(
    race: dict, battle: dict
) -> None:
    """A render is a count of images at a resolution, whatever it shows."""
    race_plan = plan_render(race, "r.json", ".")
    battle_plan = plan_render(battle, "b.json", ".")
    for field in ("width", "height", "fps", "physics_hz", "post_roll_frames"):
        assert getattr(race_plan, field) == getattr(battle_plan, field), field


def test_the_sidecar_records_the_mode(race: dict, battle: dict) -> None:
    race_data = metadata(plan_render(race, "r.json", "."), "a" * 64)
    battle_data = metadata(plan_render(battle, "b.json", "."), "b" * 64)
    assert race_data["replay"]["mode"] == "race"
    assert battle_data["replay"]["mode"] == "battle"
    # Adding the field did not change what a sidecar is.
    assert race_data["render_version"] == battle_data["render_version"]
    assert race_data["render_version"] == RENDER_FORMAT_VERSION == 1
    assert set(race_data) == set(battle_data)


def test_a_replay_with_no_frames_is_refused_in_either_mode(race: dict) -> None:
    with pytest.raises(RenderPlanError, match="no frames"):
        plan_render({"mode": "race", "frames": []}, "r.json", ".")


def test_a_replay_sampled_at_another_rate_is_refused(race: dict) -> None:
    wrong = dict(race, fps=30)
    with pytest.raises(RenderPlanError, match="resampling"):
        plan_render(wrong, "r.json", ".")


# --- the renderer's front door --------------------------------------------


def write(tmp_path, name: str, replay: dict) -> str:
    path = tmp_path / name
    path.write_text(json.dumps(replay), encoding="utf-8")
    return str(path)


def test_render_replay_accepts_both_modes(tmp_path, race: dict, battle: dict) -> None:
    from tools import render_replay

    assert render_replay.load_replay(write(tmp_path, "race.json", race))["mode"] == "race"
    loaded = render_replay.load_replay(write(tmp_path, "battle.json", battle))
    assert loaded.get("mode", MODE_BATTLE) == MODE_BATTLE


def test_each_mode_is_checked_against_its_own_schema_version(
    tmp_path, race: dict, battle: dict
) -> None:
    """The two counters are independent, and neither accepts the other's.

    A race replay is at v1 and a battle at v6. Checking a race against the
    battle counter would reject every race ever exported; checking a battle
    against the race counter would accept nothing at all.
    """
    from tools import render_replay

    assert render_replay.REPLAY_VERSIONS == {
        MODE_BATTLE: REPLAY_VERSION,
        MODE_RACE: RACE_REPLAY_VERSION,
    }

    stale_race = dict(race, version=RACE_REPLAY_VERSION + 1)
    with pytest.raises(render_replay.RenderError, match="race replay version"):
        render_replay.load_replay(write(tmp_path, "stale_race.json", stale_race))

    stale_battle = dict(battle, version=REPLAY_VERSION - 1)
    with pytest.raises(render_replay.RenderError, match="battle replay version"):
        render_replay.load_replay(write(tmp_path, "stale.json", stale_battle))


def test_an_unknown_mode_is_refused(tmp_path, race: dict) -> None:
    from tools import render_replay

    with pytest.raises(render_replay.RenderError, match="unknown replay mode"):
        render_replay.load_replay(
            write(tmp_path, "odd.json", dict(race, mode="survival"))
        )


def test_the_render_scene_is_the_same_one_for_both_modes() -> None:
    """The renderer hands Godot a replay path and a frame count, nothing else.

    Which is the whole reason race mode needed no new production tool: the
    thing that knows a race from a battle is the viewer, and it works that
    out from the file it is handed rather than from how it was invoked.
    """
    from tools import render_replay

    assert render_replay.RENDER_SCENE == "res://scenes/OfflineRender.tscn"
    source = open("tools/render_replay.py", encoding="utf-8").read()
    command = source[source.index("def run_godot("):source.index("def verify_sequence(")]
    assert "mode" not in command


# --- encoding -------------------------------------------------------------


def test_a_silent_encode_command_has_no_audio_input() -> None:
    silent = encode.encode_command(
        "ffmpeg", frames="f/%06d.png", audio=None, output="o.mp4", frame_count=10
    )
    assert silent.count("-i") == 1
    assert "-c:a" not in silent
    assert "1:a:0" not in silent
    assert "0:v:0" in silent
    # Everything that makes a production file a production file is untouched.
    for flag in ("-bitexact", "-fps_mode", "cfr", "-pix_fmt", "-map_metadata"):
        assert flag in silent


def test_the_soundtracked_command_is_exactly_what_it_was() -> None:
    with_audio = encode.encode_command(
        "ffmpeg", frames="f/%06d.png", audio="a.wav", output="o.mp4", frame_count=10
    )
    assert with_audio.count("-i") == 2
    assert with_audio[with_audio.index("-i") + 1] == "f/%06d.png"
    assert "1:a:0" in with_audio
    assert with_audio[with_audio.index("-c:a") + 1] == encode.AUDIO_CODEC


def test_probe_problems_invert_the_audio_clause() -> None:
    from rendering.encode import Probe, VideoStream

    video = VideoStream(
        codec="h264",
        profile="High",
        width=1080,
        height=1920,
        pix_fmt="yuv420p",
        frame_rate="60/1",
        avg_frame_rate="60/1",
        field_order="progressive",
        frames=600,
        duration=10.0,
    )
    silent = Probe(
        format_name="mov,mp4,m4a", duration=10.0, size=1, video=video, audio=None
    )
    assert encode.probe_problems(silent, frame_count=600, expect_audio=False) == []
    assert "no audio stream" in " ".join(
        encode.probe_problems(silent, frame_count=600)
    )


# --- end to end, if the tools are installed -------------------------------


def ffmpeg_available() -> bool:
    try:
        encode.find_ffmpeg()
        encode.find_ffprobe()
    except encode.EncodeError:
        return False
    return True


@pytest.mark.skipif(not ffmpeg_available(), reason="FFmpeg is not installed")
def test_a_silent_encode_produces_a_playable_video_only_mp4(tmp_path) -> None:
    """The last link of the race pipeline, actually run.

    Six frames rather than a whole race: what is being checked is that the
    command produces a valid video-only MP4 that ffprobe accepts as the
    production format, not that a race looks right - which is what the render
    verification does.
    """
    from rendering.render_plan import frame_filename

    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    ffmpeg = encode.find_ffmpeg()
    for index in range(6):
        subprocess.run(
            [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi",
                "-i", f"color=c=0x{index * 40:02x}2040:s=1080x1920:d=1",
                "-frames:v", "1",
                str(frames_dir / frame_filename(index)),
            ],
            check=True,
        )

    output = str(tmp_path / "short.mp4")
    command = encode.encode_command(
        ffmpeg,
        frames=encode.frames_pattern(str(frames_dir)),
        audio=None,
        output=output,
        frame_count=6,
    )
    assert subprocess.run(command, check=False).returncode == 0

    probe = subprocess.run(
        encode.probe_command(encode.find_ffprobe(), output),
        check=True,
        capture_output=True,
    )
    result = encode.parse_probe(probe.stdout.decode())
    assert result.audio is None
    assert result.video is not None
    assert (result.video.width, result.video.height) == (1080, 1920)
    assert encode.probe_problems(result, frame_count=6, expect_audio=False) == []

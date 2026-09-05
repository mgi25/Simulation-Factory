"""Phase 6A tests: planning and verifying a deterministic production render.

What is testable in Python is the *plan*: how many frames a replay produces,
what they are called, where they go, what the metadata beside them says and
how an incomplete sequence is caught. The pixels themselves are Godot's job
and are checked by rendering, not by pytest.
"""

from __future__ import annotations

import json
import os
import struct
import zlib

import pytest

from rendering import png_frames
from rendering.render_plan import (
    FRAME_DIGITS,
    POST_ROLL_SECONDS,
    RENDER_FORMAT_VERSION,
    RENDER_FPS,
    RENDER_HEIGHT,
    RENDER_WIDTH,
    RenderPlanError,
    frame_filename,
    frame_index,
    metadata,
    output_dir_name,
    plan_render,
    post_roll_frames,
    relative_replay_path,
    sequence_problems,
)
from replay.exporter import REPLAY_VERSION, record_battle, write_replay

SEED = 21465
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def make_replay(frames: int = 100, physics_hz: int = 120, fps: int = RENDER_FPS) -> dict:
    """A replay with only the fields a render plan reads."""
    ticks_per_frame = physics_hz // fps
    return {
        "version": REPLAY_VERSION,
        "seed": SEED,
        "fps": fps,
        "physics_hz": physics_hz,
        "ticks_per_frame": ticks_per_frame,
        "frames": [{"tick": index * ticks_per_frame} for index in range(frames)],
        "result": {
            "winner_id": 0,
            "is_draw": False,
            "finished_tick": (frames - 1) * ticks_per_frame,
            "duration": (frames - 1) * ticks_per_frame / physics_hz,
        },
    }


def plan_for(replay: dict, path: str = "output/replay_21465.json", **kwargs):
    return plan_render(replay, os.path.join(ROOT, path), ROOT, **kwargs)


# --- the production timeline ---------------------------------------------


def test_post_roll_is_one_deterministic_constant() -> None:
    assert POST_ROLL_SECONDS == 1.8
    assert post_roll_frames() == 108
    assert post_roll_frames(RENDER_FPS, POST_ROLL_SECONDS) == 108
    # Long enough for the result panel's 0.55s delay plus 0.45s fade, and
    # then a readable hold on top of that.
    assert POST_ROLL_SECONDS - (0.55 + 0.45) == pytest.approx(0.8)


def test_frame_count_is_gameplay_plus_post_roll() -> None:
    plan = plan_for(make_replay(frames=861))
    assert plan.gameplay_frames == 861
    assert plan.post_roll_frames == 108
    assert plan.frame_count == 969
    assert plan.total_seconds == pytest.approx(969 / 60)


def test_frame_zero_is_replay_time_zero() -> None:
    plan = plan_for(make_replay(frames=10))
    assert plan.frame_seconds(0) == 0.0
    assert plan.frame_seconds(1) == pytest.approx(1 / 60)
    assert plan.frame_seconds(60) == pytest.approx(1.0)


def test_the_final_gameplay_frame_is_rendered_before_the_tail() -> None:
    """The last replay frame is an output frame, not the boundary of one."""
    plan = plan_for(make_replay(frames=400))
    last_gameplay = plan.gameplay_frames - 1
    assert plan.frame_seconds(last_gameplay) == pytest.approx(plan.gameplay_seconds)
    assert plan.frame_count > last_gameplay
    assert plan.last_frame_seconds == pytest.approx(
        plan.gameplay_seconds + POST_ROLL_SECONDS
    )


def test_a_longer_post_roll_only_adds_frames_at_the_end() -> None:
    short = plan_for(make_replay(frames=200), tail_seconds=1.0)
    long = plan_for(make_replay(frames=200), tail_seconds=2.0)
    assert short.gameplay_frames == long.gameplay_frames
    assert long.frame_count - short.frame_count == 60


def test_a_real_replay_plans_the_frames_it_recorded() -> None:
    replay = record_battle(SEED)
    plan = plan_for(replay)
    assert plan.replay_version == REPLAY_VERSION
    assert plan.gameplay_frames == len(replay["frames"])
    assert plan.frame_count == len(replay["frames"]) + 108
    assert plan.finished_tick == replay["result"]["finished_tick"]
    assert plan.gameplay_seconds == pytest.approx(
        replay["frames"][-1]["tick"] / replay["physics_hz"]
    )


def test_a_replay_with_no_frames_is_refused() -> None:
    replay = make_replay()
    replay["frames"] = []
    with pytest.raises(RenderPlanError):
        plan_for(replay)


def test_a_replay_sampled_at_another_rate_is_refused() -> None:
    """Resampling would break the frame-index clock, so it is not attempted."""
    with pytest.raises(RenderPlanError):
        plan_for(make_replay(frames=50, physics_hz=90, fps=30))


# --- naming ---------------------------------------------------------------


def test_frame_filenames_are_zero_padded_and_contiguous() -> None:
    assert frame_filename(0) == "frame_000000.png"
    assert frame_filename(1) == "frame_000001.png"
    assert frame_filename(1426) == "frame_001426.png"
    assert frame_filename(999999) == "frame_999999.png"
    assert len(frame_filename(0)) == len("frame_") + FRAME_DIGITS + len(".png")


def test_frame_filenames_sort_in_playback_order() -> None:
    names = [frame_filename(index) for index in (0, 9, 10, 99, 100, 1000)]
    assert names == sorted(names)


def test_a_negative_frame_index_is_refused() -> None:
    with pytest.raises(RenderPlanError):
        frame_filename(-1)


def test_only_exact_frame_names_are_recognised() -> None:
    assert frame_index("frame_000042.png") == 42
    for name in ("frame_42.png", "frame_000042.jpg", "metadata.json", "frame_.png"):
        assert frame_index(name) is None


def test_output_directory_is_named_from_the_replay() -> None:
    assert output_dir_name(11266) == "render_seed_11266"
    assert output_dir_name(SEED) == output_dir_name(SEED)


def test_the_frame_list_is_the_whole_sequence_once_each() -> None:
    plan = plan_for(make_replay(frames=30))
    names = plan.frame_names()
    assert len(names) == plan.frame_count == len(set(names))
    assert names[0] == "frame_000000.png"
    assert names[-1] == frame_filename(plan.frame_count - 1)


# --- paths ----------------------------------------------------------------


def test_replay_paths_are_recorded_relative_to_the_project() -> None:
    path = os.path.join(ROOT, "output", "batch_x", "replays", "001_seed_5.json")
    assert relative_replay_path(path, ROOT) == "output/batch_x/replays/001_seed_5.json"


def test_a_replay_outside_the_project_is_recorded_by_name_alone() -> None:
    outside = os.path.join(os.path.dirname(ROOT), "elsewhere", "replay_5.json")
    assert relative_replay_path(outside, ROOT) == "replay_5.json"
    assert ".." not in relative_replay_path(outside, ROOT)


# --- metadata -------------------------------------------------------------


def test_metadata_describes_the_render() -> None:
    plan = plan_for(make_replay(frames=861))
    data = metadata(plan, "a" * 64)
    assert data["render_version"] == RENDER_FORMAT_VERSION == 1
    assert data["replay"] == {
        "name": "replay_21465.json",
        "path": "output/replay_21465.json",
        # A replay with no `mode` is a battle, so a sidecar for one says so
        # explicitly even though the replay it describes never did.
        "mode": "battle",
        "version": REPLAY_VERSION,
        "seed": SEED,
        "sha256": "a" * 64,
    }
    assert data["video"] == {
        "width": RENDER_WIDTH,
        "height": RENDER_HEIGHT,
        "fps": RENDER_FPS,
        "frame_count": 969,
        # A battle has one camera and always has. It is named rather than
        # left out so a sidecar reads the same way whatever it describes.
        "camera": "battle",
    }
    assert data["timeline"]["post_roll_seconds"] == POST_ROLL_SECONDS
    assert data["timeline"]["gameplay_frames"] == 861
    assert data["timeline"]["finished_tick"] == 1720
    assert data["frames"]["first"] == "frame_000000.png"
    assert data["frames"]["last"] == "frame_000968.png"
    assert data["frames"]["first_seconds"] == 0.0


def test_metadata_is_byte_identical_across_runs() -> None:
    plan = plan_for(make_replay(frames=120))
    first = json.dumps(metadata(plan, "b" * 64), indent=2, sort_keys=True)
    second = json.dumps(metadata(plan, "b" * 64), indent=2, sort_keys=True)
    assert first == second


def test_metadata_holds_no_machine_paths_or_timestamps() -> None:
    """Nothing in the sidecar may vary with where or when it was written."""
    plan = plan_for(make_replay(frames=120))
    data = metadata(plan, "c" * 64)

    text = json.dumps(data).replace("\\", "/")
    assert ROOT.replace(os.sep, "/") not in text
    for key in _keys(data):
        assert not any(
            word in key for word in ("timestamp", "created", "_at", "machine", "host")
        ), key
    for value in _strings(data):
        # No drive letter, no leading slash, no parent-directory escape: a
        # path here has to mean the same thing on another machine.
        assert ":" not in value and not value.startswith("/") and ".." not in value


def _keys(node, found=None) -> list[str]:
    found = [] if found is None else found
    if isinstance(node, dict):
        for key, value in node.items():
            found.append(key)
            _keys(value, found)
    return found


def _strings(node, found=None) -> list[str]:
    found = [] if found is None else found
    if isinstance(node, dict):
        for value in node.values():
            _strings(value, found)
    elif isinstance(node, str):
        found.append(node)
    return found


# --- verifying what came back --------------------------------------------


def test_a_complete_sequence_has_no_problems() -> None:
    assert sequence_problems([frame_filename(i) for i in range(5)], 5) == []


def test_a_missing_frame_is_reported() -> None:
    names = [frame_filename(i) for i in range(5) if i != 3]
    problems = sequence_problems(names, 5)
    assert len(problems) == 1
    assert "frame_000003.png" in problems[0]


def test_a_truncated_render_is_reported() -> None:
    problems = sequence_problems([frame_filename(i) for i in range(400)], 969)
    assert problems and "569 missing frames" in problems[0]


def test_frames_past_the_end_are_reported() -> None:
    """Stale frames from a longer earlier render must not pass as this one."""
    names = [frame_filename(i) for i in range(12)]
    problems = sequence_problems(names, 10)
    assert any("past the end" in problem for problem in problems)


def test_files_that_are_not_frames_are_reported() -> None:
    names = [frame_filename(i) for i in range(3)] + ["frame_3.png", "notes.txt"]
    problems = sequence_problems(names, 3)
    assert any("unrecognised" in problem for problem in problems)


def test_an_empty_directory_is_reported() -> None:
    assert sequence_problems([], 969) != []


# --- reading frames back --------------------------------------------------


def write_png(path: str, width: int, height: int, fill: bytes = b"\x20\x30\x40") -> str:
    """A minimal, valid, non-interlaced 8-bit RGB PNG."""
    raw = b"".join(b"\x00" + fill * width for _ in range(height))
    chunks = [
        (b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)),
        (b"IDAT", zlib.compress(raw)),
        (b"IEND", b""),
    ]
    body = b"".join(
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload))
        for kind, payload in chunks
    )
    with open(path, "wb") as handle:
        handle.write(png_frames.PNG_SIGNATURE + body)
    return path


def test_frame_resolution_is_read_from_the_file(tmp_path) -> None:
    path = write_png(str(tmp_path / "frame_000000.png"), RENDER_WIDTH, RENDER_HEIGHT)
    header = png_frames.read_header(path)
    assert (header.width, header.height) == (1080, 1920)
    assert header.bit_depth == 8
    assert header.channels == "RGB"


def test_a_wrongly_sized_frame_is_visible_in_its_header(tmp_path) -> None:
    header = png_frames.read_header(write_png(str(tmp_path / "small.png"), 540, 960))
    assert (header.width, header.height) != (RENDER_WIDTH, RENDER_HEIGHT)


def test_a_file_that_is_not_a_png_is_refused(tmp_path) -> None:
    path = tmp_path / "frame_000000.png"
    path.write_bytes(b"not a png at all, not even close")
    with pytest.raises(png_frames.PngError):
        png_frames.read_header(str(path))


def test_a_flat_frame_reads_as_blank(tmp_path) -> None:
    black = png_frames.sample(write_png(str(tmp_path / "b.png"), 8, 8, b"\x00\x00\x00"))
    assert black.is_black and black.is_blank

    flat = png_frames.sample(write_png(str(tmp_path / "f.png"), 8, 8, b"\x11\x11\x11"))
    assert not flat.is_black and flat.is_blank


def test_two_different_pictures_have_different_pixel_digests(tmp_path) -> None:
    left = write_png(str(tmp_path / "l.png"), 8, 8, b"\x10\x20\x30")
    right = write_png(str(tmp_path / "r.png"), 8, 8, b"\x10\x20\x31")
    assert png_frames.pixel_digest(left) != png_frames.pixel_digest(right)
    assert png_frames.pixel_digest(left) == png_frames.pixel_digest(left)


# --- the source replay ----------------------------------------------------


def test_planning_never_mutates_the_replay_it_read() -> None:
    """The renderer is a reader. It must not edit the battle it is showing."""
    replay = make_replay(frames=40)
    before = json.dumps(replay, sort_keys=True)
    plan_for(replay)
    assert json.dumps(replay, sort_keys=True) == before


def test_metadata_agrees_with_the_sequence_it_describes() -> None:
    plan = plan_for(make_replay(frames=77))
    data = metadata(plan, "d" * 64)
    names = plan.frame_names()
    assert data["video"]["frame_count"] == len(names)
    assert data["frames"]["first"] == names[0]
    assert data["frames"]["last"] == names[-1]


def test_planning_a_render_does_not_touch_the_replay(tmp_path) -> None:
    path = write_replay(record_battle(SEED), str(tmp_path / "replay.json"))
    before = png_frames.file_digest(path)

    with open(path, "r", encoding="utf-8") as handle:
        replay = json.load(handle)
    plan = plan_render(replay, path, ROOT)
    metadata(plan, before)

    assert png_frames.file_digest(path) == before

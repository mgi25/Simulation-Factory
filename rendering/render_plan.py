"""What a production render *is*, decided before a single pixel is drawn.

The renderer in Godot draws frames; this module decides which frames exist.
Everything here is a pure function of the replay: how many images the finished
Short contains, what each one is called, where the sequence lives and what the
metadata beside it says. No clocks, no wall time, no machine paths - two runs
of the same replay plan the same render, on any machine.

The production timeline is the battle plus a fixed post-roll. The post-roll is
presentation only: it exists because the result panel takes a moment to arrive
and then needs a moment to be read, and it never touches the simulation, the
replay or the recorded result.
"""

from __future__ import annotations

import os
import posixpath
from dataclasses import dataclass
from typing import Any

# The render manifest's own schema version. Nothing to do with the replay
# format (v6) or the batch manifest (v1): those describe a battle and a
# decision about many battles, this describes one sequence of images.
RENDER_FORMAT_VERSION = 1

# True production resolution. Portrait 9:16 at 1:1 pixel aspect, and the
# resolution the frames are actually rendered at - never a smaller render
# scaled up.
RENDER_WIDTH = 1080
RENDER_HEIGHT = 1920
RENDER_FPS = 60

# Presentation tail after the final gameplay frame. The result panel waits
# 0.55s and fades in over 0.45s, so a full second passes before it is legible
# at all; the rest is the hold that stops the Short cutting the moment "RED
# WINS" appears. One constant, chosen once, so every render of every replay
# ends the same way.
POST_ROLL_SECONDS = 1.8

FRAMES_SUBDIR = "frames"
METADATA_NAME = "metadata.json"
FRAME_PREFIX = "frame_"
FRAME_DIGITS = 6
FRAME_SUFFIX = ".png"


class RenderPlanError(ValueError):
    """The replay cannot be turned into a production render."""


def frame_filename(index: int) -> str:
    """`frame_000000.png`. Zero-padded, never a timestamp or an id."""
    if index < 0:
        raise RenderPlanError(f"frame index cannot be negative: {index}")
    return f"{FRAME_PREFIX}{index:0{FRAME_DIGITS}d}{FRAME_SUFFIX}"


def frame_index(name: str) -> int | None:
    """The index a frame filename encodes, or None if it is not one.

    Strict on purpose: only exactly the names `frame_filename` produces are
    accepted, so a stray `frame_1.png` left behind by something else is
    reported as an unexpected file rather than silently counted.
    """
    if not name.startswith(FRAME_PREFIX) or not name.endswith(FRAME_SUFFIX):
        return None
    digits = name[len(FRAME_PREFIX) : -len(FRAME_SUFFIX)]
    if len(digits) != FRAME_DIGITS or not digits.isdigit():
        return None
    return int(digits)


def post_roll_frames(fps: int = RENDER_FPS, seconds: float = POST_ROLL_SECONDS) -> int:
    """Post-roll length in frames. Rounded once, here, and nowhere else."""
    return int(round(seconds * fps))


def output_dir_name(seed: int) -> str:
    """The directory one replay renders into, named from the replay itself."""
    return f"render_seed_{seed}"


def relative_replay_path(path: str, root: str) -> str:
    """`path` as a repo-relative POSIX path, or just its filename.

    Metadata has to be reproducible on another machine, so an absolute path
    is never written. A replay from outside the project is recorded by name
    alone rather than by a `../../..` chain that would only make sense here.
    """
    try:
        relative = os.path.relpath(os.path.abspath(path), os.path.abspath(root))
    except ValueError:
        # Different drive on Windows: no relative path exists at all.
        return os.path.basename(path)
    relative = relative.replace(os.sep, "/")
    if relative.startswith("../") or relative == "..":
        return posixpath.basename(relative)
    return relative


@dataclass(frozen=True)
class RenderPlan:
    """Exactly which images a replay produces, and what they show."""

    seed: int
    replay_version: int
    replay_name: str
    replay_path: str
    width: int
    height: int
    fps: int
    physics_hz: int
    gameplay_frames: int
    post_roll_frames: int
    finished_tick: int | None
    battle_duration: float
    gameplay_seconds: float
    post_roll_seconds: float

    @property
    def frame_count(self) -> int:
        """Every gameplay frame, then every post-roll frame. No overlap.

        Frame 0 is replay time zero, so the gameplay frames run 0 to
        `gameplay_frames - 1` and the post-roll continues straight on from
        there - the final gameplay state is rendered before the tail starts,
        never skipped by a loop that stops at the last replay frame.
        """
        return self.gameplay_frames + self.post_roll_frames

    @property
    def total_seconds(self) -> float:
        return self.frame_count / self.fps

    @property
    def last_frame_seconds(self) -> float:
        return (self.frame_count - 1) / self.fps

    def frame_names(self) -> list[str]:
        return [frame_filename(index) for index in range(self.frame_count)]

    def frame_seconds(self, index: int) -> float:
        """Replay time frame `index` shows. The output clock, in one line."""
        return index / self.fps


def plan_render(
    replay: dict[str, Any],
    replay_path: str,
    root: str,
    width: int = RENDER_WIDTH,
    height: int = RENDER_HEIGHT,
    fps: int = RENDER_FPS,
    tail_seconds: float = POST_ROLL_SECONDS,
) -> RenderPlan:
    """Turn one loaded replay into the render it produces.

    The replay is read, never written, and never re-simulated: the frame count
    comes from the frames the exporter recorded, not from running the seed
    again.
    """
    frames = replay.get("frames") or []
    if not frames:
        raise RenderPlanError(f"replay has no frames: {replay_path}")

    replay_fps = int(replay.get("fps", fps))
    if replay_fps != fps:
        raise RenderPlanError(
            f"replay was sampled at {replay_fps} fps but the render wants {fps};"
            " resampling is not something this renderer does"
        )

    physics_hz = int(replay.get("physics_hz", 120))
    last_tick = int(frames[-1].get("tick", 0))
    result = replay.get("result") or {}
    finished = result.get("finished_tick")

    return RenderPlan(
        seed=int(replay.get("seed", 0)),
        replay_version=int(replay.get("version", 0)),
        replay_name=os.path.basename(replay_path),
        replay_path=relative_replay_path(replay_path, root),
        width=width,
        height=height,
        fps=fps,
        physics_hz=physics_hz,
        gameplay_frames=len(frames),
        post_roll_frames=post_roll_frames(fps, tail_seconds),
        finished_tick=None if finished is None else int(finished),
        battle_duration=float(result.get("duration", 0.0) or 0.0),
        # What is actually rendered, which is the last *sampled* moment of the
        # battle. Normally the same instant as `finished_tick`, and taken from
        # the frames rather than the result so it stays true if a battle ever
        # ends between two samples.
        gameplay_seconds=last_tick / max(1, physics_hz),
        post_roll_seconds=tail_seconds,
    )


def metadata(plan: RenderPlan, replay_sha256: str) -> dict[str, Any]:
    """The deterministic sidecar written beside a finished sequence.

    Everything in here is derived from the replay and the plan. No timestamps,
    no absolute paths, no hardware, no run ids - render the same replay twice
    and the two files are byte for byte the same. Wall-clock cost and GPU name
    are console output, not metadata.
    """
    return {
        "render_version": RENDER_FORMAT_VERSION,
        "replay": {
            "name": plan.replay_name,
            "path": plan.replay_path,
            "version": plan.replay_version,
            "seed": plan.seed,
            "sha256": replay_sha256,
        },
        "video": {
            "width": plan.width,
            "height": plan.height,
            "fps": plan.fps,
            "frame_count": plan.frame_count,
        },
        "timeline": {
            "physics_hz": plan.physics_hz,
            "finished_tick": plan.finished_tick,
            "battle_duration": round(plan.battle_duration, 3),
            "gameplay_frames": plan.gameplay_frames,
            "gameplay_seconds": round(plan.gameplay_seconds, 3),
            "post_roll_frames": plan.post_roll_frames,
            "post_roll_seconds": round(plan.post_roll_seconds, 3),
            "total_seconds": round(plan.total_seconds, 3),
        },
        "frames": {
            "directory": FRAMES_SUBDIR,
            "pattern": f"{FRAME_PREFIX}%0{FRAME_DIGITS}d{FRAME_SUFFIX}",
            "first": frame_filename(0),
            "last": frame_filename(plan.frame_count - 1),
            "first_seconds": 0.0,
            "last_seconds": round(plan.last_frame_seconds, 4),
        },
    }


def sequence_problems(names: list[str], expected_count: int) -> list[str]:
    """What is wrong with a rendered sequence, in plain words.

    An incomplete render must never pass quietly, so this reports missing
    numbers, extra files and anything that is not a frame at all. Duplicates
    cannot exist - one index is one filename - but a gap or a stray file can,
    and both mean the render is not what was planned.
    """
    problems: list[str] = []
    indices: set[int] = set()
    strays: list[str] = []

    for name in sorted(names):
        index = frame_index(name)
        if index is None:
            strays.append(name)
        else:
            indices.add(index)

    expected = set(range(expected_count))
    missing = sorted(expected - indices)
    extra = sorted(indices - expected)

    if missing:
        problems.append(
            f"{len(missing)} missing frames, first {frame_filename(missing[0])}"
        )
    if extra:
        problems.append(
            f"{len(extra)} frames past the end, first {frame_filename(extra[0])}"
        )
    if strays:
        problems.append(f"{len(strays)} unrecognised files, first {strays[0]}")
    return problems

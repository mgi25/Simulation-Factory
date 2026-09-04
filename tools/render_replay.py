"""Render a replay to a deterministic 1080x1920 PNG sequence.

The production renderer's front door. It plans the render, drives Godot in
offline mode, checks that what came back is what was planned, and writes the
metadata that describes the sequence.

Typical use::

    python tools/render_replay.py output/batch_audit10/replays/003_seed_21465.json
    python tools/render_replay.py replay.json --output output/render_test
    python tools/render_replay.py --manifest output/batch_audit10/manifest.json --limit 3

Godot is handed the *exported replay* and nothing else. It never re-runs a
seed: the point of a replay is that the selected battle is frozen, so the
images come from the file that was selected, not from a simulation that would
have to agree with it.

Finding Godot, in order: `--godot`, then `$GODOT_BIN`, then the PATH. No
machine-specific path is committed anywhere in this project.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rendering import png_frames  # noqa: E402
from rendering.render_plan import (  # noqa: E402
    FRAMES_SUBDIR,
    METADATA_NAME,
    POST_ROLL_SECONDS,
    RENDER_FPS,
    RENDER_HEIGHT,
    RENDER_WIDTH,
    RenderPlan,
    RenderPlanError,
    frame_filename,
    metadata,
    output_dir_name,
    plan_render,
    sequence_problems,
)
from replay.exporter import REPLAY_VERSION  # noqa: E402

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GODOT_PROJECT = os.path.join(PROJECT_ROOT, "godot")
RENDER_SCENE = "res://scenes/OfflineRender.tscn"
DEFAULT_OUTPUT_ROOT = "output"

GODOT_ENV_VARS = ("GODOT_BIN", "GODOT4_BIN")
GODOT_ON_PATH = ("godot", "godot4", "Godot_v4.7.2-stable_win64.exe")

# Bytes per mebibyte, for the storage report.
MIB = 1024 * 1024


class RenderError(RuntimeError):
    """The render did not produce the sequence that was planned."""


# --- locating Godot -------------------------------------------------------


def find_godot(explicit: str | None) -> str:
    if explicit:
        if os.path.isfile(explicit):
            return explicit
        found = shutil.which(explicit)
        if found:
            return found
        raise RenderError(f"--godot does not name an executable: {explicit}")

    for variable in GODOT_ENV_VARS:
        value = os.environ.get(variable)
        if value and os.path.isfile(value):
            return value

    for name in GODOT_ON_PATH:
        found = shutil.which(name)
        if found:
            return found

    raise RenderError(
        "cannot find Godot 4. Pass --godot PATH, set "
        f"{' or '.join('$' + name for name in GODOT_ENV_VARS)}, or put it on PATH."
    )


# --- one render -----------------------------------------------------------


def load_replay(path: str) -> dict:
    if not os.path.isfile(path):
        raise RenderError(f"no replay at {path}")
    with open(path, "r", encoding="utf-8") as handle:
        replay = json.load(handle)
    version = int(replay.get("version", 0))
    if version != REPLAY_VERSION:
        raise RenderError(
            f"{path}: replay version {version}, this renderer plays v{REPLAY_VERSION}"
        )
    return replay


def prepare_frames_dir(render_dir: str) -> str:
    """An empty frames directory, so a shorter render cannot inherit a tail.

    Only the frames this renderer writes are removed. Anything else in the
    directory is left where it is rather than deleted on the user's behalf.
    """
    frames_dir = os.path.join(render_dir, FRAMES_SUBDIR)
    os.makedirs(frames_dir, exist_ok=True)
    for name in os.listdir(frames_dir):
        if name.startswith("frame_") and name.endswith(".png"):
            os.remove(os.path.join(frames_dir, name))
    return frames_dir


def run_godot(godot: str, replay_path: str, frames_dir: str, plan: RenderPlan) -> None:
    command = [
        godot,
        "--path",
        GODOT_PROJECT,
        RENDER_SCENE,
        "--",
        f"--replay={os.path.abspath(replay_path)}",
        f"--out-dir={os.path.abspath(frames_dir)}",
        f"--frames={plan.frame_count}",
        f"--fps={plan.fps}",
        f"--width={plan.width}",
        f"--height={plan.height}",
    ]
    completed = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
    if completed.returncode != 0:
        raise RenderError(
            f"Godot exited {completed.returncode}; the render is incomplete"
        )


def verify_sequence(frames_dir: str, plan: RenderPlan) -> list[str]:
    """Every planned frame, exactly once, at exactly the right size.

    Headers only: the whole sequence is checked, which two million pixels a
    frame would make far too slow, and the dimensions are the thing that has
    to be true of every single image.
    """
    names = os.listdir(frames_dir)
    problems = sequence_problems(names, plan.frame_count)
    if problems:
        return problems

    for index in range(plan.frame_count):
        path = os.path.join(frames_dir, frame_filename(index))
        header = png_frames.read_header(path)
        if header.width != plan.width or header.height != plan.height:
            problems.append(
                f"{frame_filename(index)} is {header.width}x{header.height},"
                f" expected {plan.width}x{plan.height}"
            )
            break
        if header.color_type not in (
            png_frames.COLOR_TYPE_RGB,
            png_frames.COLOR_TYPE_RGBA,
        ):
            problems.append(
                f"{frame_filename(index)} is {header.channels}, expected RGB or RGBA"
            )
            break
    return problems


def verify_content(frames_dir: str, plan: RenderPlan) -> list[str]:
    """A handful of frames decoded, to prove the sequence is a battle.

    Not image quality - just that something was drawn, that the battle moved
    and that the ending is not the middle. Four frames is enough to catch a
    renderer that wrote two thousand copies of one picture.
    """
    checkpoints = {
        "frame 0": 0,
        "mid-battle": plan.gameplay_frames // 2,
        "final gameplay": plan.gameplay_frames - 1,
        "final hold": plan.frame_count - 1,
    }
    problems: list[str] = []
    samples = {}
    for label, index in checkpoints.items():
        path = os.path.join(frames_dir, frame_filename(index))
        frame = png_frames.sample(path)
        samples[label] = frame
        if frame.is_black:
            problems.append(f"{label} ({frame_filename(index)}) is completely black")
        elif frame.is_blank:
            problems.append(f"{label} ({frame_filename(index)}) is a flat colour")

    if samples["frame 0"].digest == samples["mid-battle"].digest:
        problems.append("frame 0 and the mid-battle frame are the same image")
    if samples["final hold"].digest == samples["mid-battle"].digest:
        problems.append("the final hold and the mid-battle frame are the same image")
    return problems


def write_metadata(render_dir: str, plan: RenderPlan, replay_sha256: str) -> str:
    path = os.path.join(render_dir, METADATA_NAME)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(metadata(plan, replay_sha256), handle, indent=2, sort_keys=True)
        handle.write("\n")
    return path


def frames_bytes(frames_dir: str, plan: RenderPlan) -> int:
    return sum(
        os.path.getsize(os.path.join(frames_dir, frame_filename(index)))
        for index in range(plan.frame_count)
    )


def render(
    godot: str,
    replay_path: str,
    render_dir: str,
    fps: int,
    width: int,
    height: int,
    tail_seconds: float,
) -> RenderPlan:
    """Plan one render, produce it, and refuse to accept anything less.

    Nothing is reported as finished until the sequence has been counted, its
    frames measured, a few of them decoded and the source replay confirmed
    untouched. A render that falls short raises rather than writing metadata
    describing images that are not there.
    """
    replay = load_replay(replay_path)
    plan = plan_render(
        replay,
        replay_path,
        PROJECT_ROOT,
        width=width,
        height=height,
        fps=fps,
        tail_seconds=tail_seconds,
    )
    # Hashed before and after: rendering reads the replay and must never touch
    # it, and the only way to say that with confidence is to check.
    replay_sha256 = png_frames.file_digest(replay_path)

    print(
        f"\n=== seed {plan.seed}  {plan.replay_path} ===\n"
        f"    {plan.width}x{plan.height} @ {plan.fps}fps  "
        f"{plan.gameplay_frames} gameplay + {plan.post_roll_frames} post-roll "
        f"= {plan.frame_count} frames ({plan.total_seconds:.2f}s)"
    )

    frames_dir = prepare_frames_dir(render_dir)
    started = time.perf_counter()
    run_godot(godot, replay_path, frames_dir, plan)
    elapsed = time.perf_counter() - started

    problems = verify_sequence(frames_dir, plan) or verify_content(frames_dir, plan)
    if problems:
        raise RenderError("; ".join(problems))

    if png_frames.file_digest(replay_path) != replay_sha256:
        raise RenderError(f"the source replay changed during rendering: {replay_path}")

    metadata_path = write_metadata(render_dir, plan, replay_sha256)
    total = frames_bytes(frames_dir, plan)
    print(
        f"    rendered in {elapsed:.1f}s"
        f"  ({plan.frame_count / max(elapsed, 1e-6):.1f} frames/sec,"
        f" {1000.0 * elapsed / plan.frame_count:.1f} ms/frame)\n"
        f"    {total / MIB:.1f} MiB of PNG"
        f"  ({total / plan.frame_count / 1024:.0f} KiB/frame)\n"
        f"    {os.path.relpath(metadata_path, PROJECT_ROOT)}"
    )
    return plan


# --- batches --------------------------------------------------------------


def manifest_jobs(
    manifest_path: str, output_root: str, limit: int | None
) -> list[tuple[str, str]]:
    """Replay path and render directory for each item of a batch manifest.

    One directory per item, named from its index *and* its seed, so two items
    can never write into the same place - not even the day a batch selects
    one seed twice.
    """
    with open(manifest_path, "r", encoding="utf-8") as handle:
        manifest = json.load(handle)

    batch_dir = os.path.dirname(os.path.abspath(manifest_path))
    batch_id = str(manifest.get("batch_id", "batch"))
    items = manifest.get("items", [])
    if limit is not None:
        items = items[:limit]

    jobs = []
    for item in items:
        relative = item.get("replay_path")
        if not relative:
            raise RenderError(
                f"{manifest_path}: item {item.get('index')} has no replay_path."
                " Rebuild the batch with --export-replays."
            )
        jobs.append(
            (
                os.path.join(batch_dir, relative),
                os.path.join(
                    output_root,
                    f"render_{batch_id}",
                    f"{int(item['index']):03d}_seed_{int(item['seed'])}",
                ),
            )
        )
    return jobs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="render a replay to a deterministic 1080x1920 PNG sequence"
    )
    parser.add_argument("replay", nargs="?", default=None, help="replay JSON to render")
    parser.add_argument("--manifest", default=None, help="render a batch manifest")
    parser.add_argument("--limit", type=int, default=None, help="first N manifest items")
    parser.add_argument("--output", default=None, help="directory for a single render")
    parser.add_argument("--output-root", default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--godot", default=None, help="path to the Godot 4 executable")
    parser.add_argument("--fps", type=int, default=RENDER_FPS)
    parser.add_argument("--width", type=int, default=RENDER_WIDTH)
    parser.add_argument("--height", type=int, default=RENDER_HEIGHT)
    parser.add_argument(
        "--post-roll",
        type=float,
        default=POST_ROLL_SECONDS,
        help="presentation tail after the final gameplay frame, in seconds",
    )
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="finish the remaining items after one fails, then still exit non-zero",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if bool(args.replay) == bool(args.manifest):
        print("give exactly one of: a replay path, or --manifest PATH", file=sys.stderr)
        return 2

    try:
        godot = find_godot(args.godot)
        if args.manifest:
            jobs = manifest_jobs(args.manifest, args.output_root, args.limit)
        else:
            replay = load_replay(args.replay)
            directory = args.output or os.path.join(
                args.output_root, output_dir_name(int(replay.get("seed", 0)))
            )
            jobs = [(args.replay, directory)]
    except (RenderError, OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if not jobs:
        print("error: nothing to render", file=sys.stderr)
        return 2

    print(f"godot: {godot}")
    failures: list[str] = []
    for replay_path, render_dir in jobs:
        try:
            render(
                godot,
                replay_path,
                render_dir,
                args.fps,
                args.width,
                args.height,
                args.post_roll,
            )
        except (RenderError, RenderPlanError, png_frames.PngError) as error:
            print(f"    FAILED: {error}", file=sys.stderr)
            failures.append(f"{os.path.basename(replay_path)}: {error}")
            if not args.keep_going:
                break

    if failures:
        print(f"\n{len(failures)} of {len(jobs)} renders failed:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1

    print(f"\n{len(jobs)} render(s) complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

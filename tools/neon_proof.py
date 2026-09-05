"""Produce the Neon Marble Machine visual proof: replay, stills, video.

The prototype's front door, and the only thing that knows the whole shape of
the deliverable. Everything it does is a step of the pipeline the project
already has - Python simulates, the exporter freezes the run, Godot draws it,
FFmpeg encodes it - with the V1 scene selected by one flag:

    python tools/neon_proof.py --seed 7 --all

Steps, and each one can be asked for on its own:

    --replay     simulate the neon course and export a race replay
    --cameras    the same four moments at 42, 48, 52 and 56 degrees
    --frames     the full 1080x1920 sequence at the chosen elevation
    --sections   the five section stills, pulled out of that sequence
    --video      the 5-8 second proof, cut from that sequence
    --countries  one still with five stylised country marbles

Nothing here re-simulates between steps. The replay is written once and every
later step reads it, so the camera comparison, the section stills and the
video are all the same race at the same instants - which is the only way a
comparison is about what it claims to be about.

The video window is computed from the replay rather than chosen: it opens a
fixed lead-in before the tick the gate is recorded open and runs for the
brief's length. Two runs of the same seed cut the same seven seconds.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from race.courses.neon import NEON_COURSE_ID, NEON_RACER_COUNT  # noqa: E402
from rendering import encode  # noqa: E402
from rendering.render_plan import (  # noqa: E402
    FRAMES_SUBDIR,
    RENDER_FPS,
    RENDER_HEIGHT,
    RENDER_WIDTH,
    frame_filename,
)
from tools.race_moments import THUMB_SCALE, write_thumb  # noqa: E402
from tools.render_replay import (  # noqa: E402
    GODOT_PROJECT,
    PROJECT_ROOT,
    RENDER_SCENE,
    RenderError,
    find_godot,
)

DEFAULT_SEED = 7
DEFAULT_ROOT = os.path.join("output", "neon_v1")
DEFAULT_STILLS = os.path.join("docs", "validation", "neon_v1")

# The four elevations the brief asks to be compared, and the one this
# prototype ships on. `SELECTED_ELEVATION` is what `--frames` and `--video`
# shoot with unless `--elevation` says otherwise; it must match the scene's
# own `CAM_ELEVATION`, and `tests/test_neon_proof.py` checks that it does.
CAMERA_ANGLES = (42.0, 48.0, 52.0, 56.0)
SELECTED_ELEVATION = 52.0

# The proof, in seconds. Opens on the platform, holds through the release,
# the bowl and the bridge.
VIDEO_LEAD_IN = 1.2
VIDEO_SECONDS = 7.0

# The moments the camera comparison is judged on, as seconds from the tick
# the gate opens. Negative is before the release.
CAMERA_MOMENTS = (-0.6, 1.4, 2.2, 3.6)

# The five section stills the brief asks for, as (name, seconds after the
# gate opens). Chosen from the reference replay's own timings and stated here
# rather than searched for, so the same five moments come out of any render
# of it.
SECTION_MOMENTS = (
    ("start_platform", -0.6),
    ("entering_bowl", 1.3),
    ("inside_bowl", 2.0),
    ("bowl_exit", 2.8),
    ("s_curve_bridge", 4.3),
)

# The country comparison: the same instant with plain marbles and with
# stylised ones, so the two stills differ in exactly one thing.
COUNTRY_MOMENT = -0.6


class ProofError(RuntimeError):
    """A step of the proof could not be completed."""


# --- replay -----------------------------------------------------------------


def export_replay(path: str, seed: int, racers: int) -> dict:
    from replay.race_exporter import record_race, write_replay

    replay = record_race(seed, course_name=NEON_COURSE_ID, racer_count=racers)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    write_replay(replay, path)
    result = replay["result"]
    print(
        f"    seed {seed}  {len(replay['racers'])} racers"
        f"  {len(replay['frames'])} frames"
        f" ({len(replay['frames']) / replay['fps']:.2f}s)\n"
        f"    winner {result['winner_name']} at {result['winner_time']:.2f}s,"
        f" {result['racers_finished']}/{len(replay['racers'])} home\n"
        f"    wrote {path} ({os.path.getsize(path) / 1024 / 1024:.1f} MiB)"
    )
    return replay


def load_replay(path: str) -> dict:
    if not os.path.isfile(path):
        raise ProofError(f"no replay at {path}; run with --replay first")
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def gate_frame(replay: dict) -> int:
    """The output frame the starting gate is first recorded open on.

    Every moment in this file is measured from here rather than from frame
    zero, because frame zero is three seconds of countdown that no part of
    the proof is about.
    """
    for index, frame in enumerate(replay.get("frames", [])):
        if frame.get("gates_open"):
            return index
    raise ProofError("the replay never opens its gate")


def moment_frame(replay: dict, seconds: float) -> int:
    """An output frame index, given seconds either side of the release."""
    last = max(0, len(replay.get("frames", [])) - 1)
    return max(0, min(last, gate_frame(replay) + int(round(seconds * RENDER_FPS))))


# --- rendering --------------------------------------------------------------


def godot_command(
    godot: str,
    replay_path: str,
    out_dir: str,
    total: int,
    elevation: float,
    stills: tuple[int, ...] = (),
    countries: bool = False,
) -> list[str]:
    """One Godot invocation, as an argument list.

    `--race-style=neon` is the whole difference from `render_replay.py`: the
    same scene tree, the same offline renderer and the same clock, with the
    prototype's scene in place of the production one.
    """
    command = [
        godot,
        "--path",
        GODOT_PROJECT,
        RENDER_SCENE,
        "--",
        f"--replay={os.path.abspath(replay_path)}",
        f"--out-dir={os.path.abspath(out_dir)}",
        f"--frames={total}",
        f"--fps={RENDER_FPS}",
        f"--width={RENDER_WIDTH}",
        f"--height={RENDER_HEIGHT}",
        "--race-camera=production",
        "--race-style=neon",
        f"--race-elevation={elevation:g}",
    ]
    if stills:
        command.append(f"--stills={','.join(str(index) for index in stills)}")
    if countries:
        command.append("--neon-countries=1")
    return command


def run_godot(command: list[str], label: str) -> None:
    completed = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
    if completed.returncode != 0:
        raise ProofError(f"Godot exited {completed.returncode} while rendering {label}")


def render_cameras(
    godot: str, replay: dict, replay_path: str, out_root: str, angles: tuple[float, ...]
) -> dict[float, list[str]]:
    """The same moments at each elevation, one directory per angle."""
    total = len(replay["frames"])
    frames = tuple(moment_frame(replay, at) for at in CAMERA_MOMENTS)
    written: dict[float, list[str]] = {}
    for angle in angles:
        out_dir = os.path.join(out_root, f"e{angle:g}")
        os.makedirs(out_dir, exist_ok=True)
        print(f"    {angle:g} degrees -> {out_dir}")
        run_godot(
            godot_command(godot, replay_path, out_dir, total, angle, frames),
            f"{angle:g} degrees",
        )
        written[angle] = [
            os.path.join(out_dir, f"still_{index:06d}.png") for index in frames
        ]
    return written


def render_frames(
    godot: str, replay: dict, replay_path: str, render_dir: str, elevation: float
) -> str:
    """The whole sequence, at the elevation the prototype ships on."""
    frames_dir = os.path.join(render_dir, FRAMES_SUBDIR)
    os.makedirs(frames_dir, exist_ok=True)
    for name in os.listdir(frames_dir):
        if name.startswith("frame_") and name.endswith(".png"):
            os.remove(os.path.join(frames_dir, name))

    total = len(replay["frames"])
    print(f"    {total} frames at {elevation:g} degrees -> {frames_dir}")
    run_godot(
        godot_command(godot, replay_path, frames_dir, total, elevation),
        "the full sequence",
    )
    missing = [
        index
        for index in range(total)
        if not os.path.isfile(os.path.join(frames_dir, frame_filename(index)))
    ]
    if missing:
        raise ProofError(
            f"{len(missing)} frames missing, first {frame_filename(missing[0])}"
        )
    return frames_dir


def render_countries(
    godot: str, replay: dict, replay_path: str, out_dir: str, elevation: float
) -> list[str]:
    """One instant, twice: plain marbles and stylised country ones.

    Both stills come out of the same replay at the same frame through the same
    scene, so the only thing that differs between them is the racer material -
    which is the only thing the experiment is asking about.
    """
    total = len(replay["frames"])
    index = moment_frame(replay, COUNTRY_MOMENT)
    written = []
    for label, countries in (("plain", False), ("countries", True)):
        target = os.path.join(out_dir, label)
        os.makedirs(target, exist_ok=True)
        run_godot(
            godot_command(
                godot, replay_path, target, total, elevation, (index,), countries
            ),
            f"the {label} marbles",
        )
        written.append(os.path.join(target, f"still_{index:06d}.png"))
    return written


# --- stills and video -------------------------------------------------------


def save_stills(sources: list[str], targets: list[str], scale: float) -> list[str]:
    """Put the stills where they are reviewed from, at review size.

    Half size by default, and `tools/race_moments.py`'s own resampler is used
    rather than a second one, for the reason that file gives: these are judged
    by eye, and a point-sampled downscale of a 1080p frame turns every thin
    lit edge on the machine into a dashed line.

    Half size is also what keeps them committable. Full-size PNGs of a machine
    this pale come out near a megabyte each, and twenty-three of them is
    eighteen megabytes of repository for pictures nobody measures - the
    measuring is done on the sequence under `output/`, which is not committed.
    `--still-scale 1` writes them full size if that is ever wanted.
    """
    written = []
    for source, target in zip(sources, targets):
        if not os.path.isfile(source):
            raise ProofError(f"expected a still at {source}")
        os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
        if scale >= 1.0:
            shutil.copyfile(source, target)
        else:
            write_thumb(source, target, scale)
        written.append(target)
    return written


def extract_sections(
    replay: dict, frames_dir: str, out_dir: str, scale: float
) -> list[str]:
    """The five named moments, copied out of the finished sequence."""
    sources = []
    targets = []
    for name, at in SECTION_MOMENTS:
        index = moment_frame(replay, at)
        sources.append(os.path.join(frames_dir, frame_filename(index)))
        targets.append(os.path.join(out_dir, f"{name}.png"))
        print(f"    {name:<16} frame {index:>5}  ({at:+.1f}s from the release)")
    return save_stills(sources, targets, scale)


def video_window(replay: dict) -> tuple[int, int]:
    """Which frames the proof video is cut from. First frame, and how many."""
    start = max(0, gate_frame(replay) - int(round(VIDEO_LEAD_IN * RENDER_FPS)))
    count = int(round(VIDEO_SECONDS * RENDER_FPS))
    available = len(replay.get("frames", [])) - start
    return start, max(1, min(count, available))


def encode_video(replay: dict, frames_dir: str, output: str) -> str:
    try:
        ffmpeg = encode.find_ffmpeg(None)
    except encode.EncodeError as error:
        raise ProofError(str(error)) from None
    start, count = video_window(replay)
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    command = encode.encode_command(
        ffmpeg,
        frames=encode.frames_pattern(frames_dir),
        audio=None,
        output=output,
        frame_count=count,
        start_number=start,
    )
    print(
        f"    frames {start}..{start + count - 1}"
        f"  ({count / RENDER_FPS:.2f}s at {RENDER_FPS}fps)"
    )
    completed = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
    if completed.returncode != 0:
        raise ProofError(f"ffmpeg exited {completed.returncode}")
    size = os.path.getsize(output)
    print(f"    wrote {output} ({size / 1024 / 1024:.1f} MiB)")
    return output


# --- the run ----------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="produce the Neon Marble Machine visual proof"
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--racers", type=int, default=NEON_RACER_COUNT)
    parser.add_argument("--root", default=DEFAULT_ROOT, help="working output root")
    parser.add_argument("--stills", default=DEFAULT_STILLS, help="where stills land")
    parser.add_argument("--godot", default=None)
    parser.add_argument(
        "--elevation",
        type=float,
        default=SELECTED_ELEVATION,
        help="camera elevation for the sequence and the video",
    )
    parser.add_argument(
        "--angles",
        default=",".join(f"{angle:g}" for angle in CAMERA_ANGLES),
        help="comma-separated elevations for the camera comparison",
    )
    parser.add_argument(
        "--still-scale",
        type=float,
        default=THUMB_SCALE,
        help="size the committed stills are written at, relative to 1080x1920",
    )
    parser.add_argument("--all", action="store_true", help="every step, in order")
    parser.add_argument("--replay", action="store_true")
    parser.add_argument("--cameras", action="store_true")
    parser.add_argument("--frames", action="store_true")
    parser.add_argument("--sections", action="store_true")
    parser.add_argument("--video", action="store_true")
    parser.add_argument("--countries", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    steps = {
        "replay": args.replay or args.all,
        "cameras": args.cameras or args.all,
        "frames": args.frames or args.all,
        "sections": args.sections or args.all,
        "video": args.video or args.all,
        "countries": args.countries or args.all,
    }
    if not any(steps.values()):
        print("nothing to do; pass --all or one of the step flags", file=sys.stderr)
        return 2

    replay_path = os.path.join(args.root, f"neon_{args.seed}.json")
    render_dir = os.path.join(args.root, f"render_e{args.elevation:g}")
    frames_dir = os.path.join(render_dir, FRAMES_SUBDIR)

    try:
        if steps["replay"]:
            print("=== replay ===")
            export_replay(replay_path, args.seed, args.racers)
        replay = load_replay(replay_path)

        godot = None
        if steps["cameras"] or steps["frames"] or steps["countries"]:
            godot = find_godot(args.godot)
            print(f"godot: {godot}")

        if steps["cameras"]:
            print("=== camera comparison ===")
            angles = tuple(
                float(value) for value in args.angles.split(",") if value.strip()
            )
            written = render_cameras(
                godot, replay, replay_path, os.path.join(args.root, "camera"), angles
            )
            for angle, paths in written.items():
                targets = [
                    os.path.join(
                        args.stills, "camera", f"e{angle:g}", os.path.basename(path)
                    )
                    for path in paths
                ]
                save_stills(paths, targets, args.still_scale)
            print(f"    {sum(len(v) for v in written.values())} stills")

        if steps["frames"]:
            print("=== sequence ===")
            render_frames(godot, replay, replay_path, render_dir, args.elevation)

        if steps["sections"]:
            print("=== section stills ===")
            extract_sections(
                replay,
                frames_dir,
                os.path.join(args.stills, "sections"),
                args.still_scale,
            )

        if steps["video"]:
            print("=== video ===")
            encode_video(
                replay, frames_dir, os.path.join(args.root, "neon_machine_proof.mp4")
            )

        if steps["countries"]:
            print("=== country comparison ===")
            written = render_countries(
                godot,
                replay,
                replay_path,
                os.path.join(args.root, "countries"),
                args.elevation,
            )
            save_stills(
                written,
                [
                    os.path.join(args.stills, "countries", "plain_marbles.png"),
                    os.path.join(args.stills, "countries", "country_marbles.png"),
                ],
                args.still_scale,
            )
            print("    2 stills")
    # `RenderError` is in here because `find_godot` is borrowed from
    # `render_replay.py` and raises its error, not this file's. It is a
    # sibling of `ProofError` rather than an ancestor, so leaving it out meant
    # a mistyped `--godot` came back as a traceback instead of one line
    # saying which executable was not found.
    except (
        ProofError,
        RenderError,
        encode.EncodeError,
        OSError,
        ValueError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print("\nproof complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

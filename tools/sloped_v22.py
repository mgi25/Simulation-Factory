"""Solve and render V22: the course preview, the chase camera and the new pacing.

    python tools/sloped_v22.py --stage all --godot PATH

Stages, in the order the dependency runs:

    solve    the race camera track, then the preview that hands off to it
    freeze   the held first race frame, so the preview scene has a legal pose
    race     Godot renders the race master, 1221 frames of replay 0.200-24.467
    preview  Godot renders the preview master, 120 frames of its own flight
    check    what the two tracks are wrong about, if anything
    all      all five

What comes out is two silent renders under `output/sloped_race_v1/v22/`. The
film is assembled from them by `tools/sloped_short.py --edition v22`, which is
where the hold, the overlays and the soundtrack live.

**Nothing here touches the physics.** The replay is read, never written; the
course is rebuilt from the same contract the race ran on so the camera solve has
geometry to aim at, and nothing it produces goes back into a simulation.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from typing import Any, Sequence

sys.path.insert(0, os.getcwd())

from sloped import cameras, chase_camera, course_preview, v22
from sloped.course import sloped_course

PROJECT_ROOT = os.getcwd()
GODOT_PROJECT = os.path.join(PROJECT_ROOT, "godot")
RENDER_SCENE = "res://scenes/SlopedRaceRender.tscn"

OUT_DIR = os.path.join("output", "sloped_race_v1")
WORK_DIR = os.path.join(OUT_DIR, "v22")

RACE_TRACK = os.path.join(OUT_DIR, "cameras_v22_{seed}.json")
PREVIEW_TRACK = os.path.join(OUT_DIR, "preview_v22_{seed}.json")
FROZEN_REPLAY = os.path.join(WORK_DIR, "frozen_{seed}.json")
RACE_MASTER = os.path.join(WORK_DIR, "race_master.mp4")
PREVIEW_MASTER = os.path.join(WORK_DIR, "preview_master.mp4")

WIDTH, HEIGHT, FPS = 1080, 1920, 60
VIDEO_CRF = 16
VIDEO_PRESET = "slow"


class V22Error(RuntimeError):
    pass


def _replay_path(seed: int) -> str:
    return os.path.join(OUT_DIR, f"race_{seed}.json")


def _start_contract(seed: int) -> str:
    return os.path.join(OUT_DIR, f"start_contract_{seed}.json")


def _load_replay(seed: int) -> dict[str, Any]:
    path = _replay_path(seed)
    if not os.path.isfile(path):
        raise V22Error(
            f"the locked replay is missing: {path}\n"
            "  it is generated output and not in the branch; copy it from a tree "
            "that has it, or rebuild it with tools/sloped_integrate.py race."
        )
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


# --- solving ----------------------------------------------------------------


def stage_solve(seed: int) -> dict[str, Any]:
    replay = _load_replay(seed)
    machine = sloped_course(routes="both")

    race = v22.build_race_track(replay, machine, fps=FPS)
    cameras.write_track(race, RACE_TRACK.format(seed=seed))
    print(f"race: {len(race['cuts'])} cuts over {race['duration']:.6f} s, "
          f"omitting {race['omitted']:.6f} s -> {RACE_TRACK.format(seed=seed)}")
    rows = {row["cut"]: row for row in cameras.frame_report(race, replay)}
    for segment in race["edit"]:
        row = rows.get(segment["cut"], {})
        print(f"    {segment['cut']:9s} out {segment['out'][0]:8.4f}-{segment['out'][1]:8.4f}"
              f"  replay {segment['replay'][0]:9.4f}-{segment['replay'][1]:9.4f}"
              f"  racers {row.get('in_frame', '-')}/{row.get('of', '-')}"
              f"  nearest {row.get('nearest_px', 0.0):.0f} px")

    track, report = v22.build_preview_track(race, machine, seed)
    course_preview.write_track(track, PREVIEW_TRACK.format(seed=seed))
    frames = v22.preview_frames(track)
    print(f"preview: {frames} frames, {report['duration']:.4f} s of frame centres, "
          f"{v22.preview_prefix(track):.4f} s of screen "
          f"-> {PREVIEW_TRACK.format(seed=seed)}")
    print(f"    handoff   {report['end_reach']:.2f} layout units out at "
          f"{report['end_elevation']:.2f} degrees")
    print(f"    step      max {report['max_step']:.3f}  across {report['max_across_step']:.3f}"
          f"  turn {report['max_turn']:.3f}  pan {report['max_yaw']:.3f}"
          f"  tilt {report['max_pitch']:.3f}")
    print(f"    visible   {100.0 * report['mean_visible_fraction']:.1f}% of the ribbon, "
          f"{report['landmarks_seen']}/{len(report['landmarks'])} landmarks")
    for problem in report["problems"]:
        print(f"    PROBLEM: {problem}")
    if not report["problems"]:
        print("    no problems found")
    _assert_handoff(race, track)
    return {"race": race, "preview": track, "report": report}


def _assert_handoff(race: dict[str, Any], preview: dict[str, Any]) -> None:
    """The preview's last frame and the race's first must be the same pose.

    This is the whole claim of the opening - that there is no cut between the
    preview and the race - so it is checked rather than assumed.
    """
    last = preview["cuts"][-1]["frames"][-1]
    first = race["cuts"][0]["frames"][0]
    worst = max(abs(float(last[i]) - float(first[i])) for i in range(1, 7))
    if worst > 5e-4:
        raise V22Error(
            f"the preview does not arrive on the race camera: {worst:.6f} layout "
            "units apart at the handoff"
        )
    print(f"    handoff exact to {worst:.6f} layout units")


def stage_freeze(seed: int) -> str:
    replay = _load_replay(seed)
    track_path = PREVIEW_TRACK.format(seed=seed)
    if not os.path.isfile(track_path):
        raise V22Error(f"solve first: {track_path} is missing")
    with open(track_path, "r", encoding="utf-8") as handle:
        seconds = float(json.load(handle)["duration"])
    frozen = course_preview.frozen_replay(replay, seconds, FPS)
    os.makedirs(WORK_DIR, exist_ok=True)
    path = FROZEN_REPLAY.format(seed=seed)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(frozen, handle, separators=(",", ":"))
        handle.write("\n")
    print(f"frozen replay: {len(frozen['frames'])} identical frames -> {path}"
          f"  ({os.path.getsize(path) / 1024:.0f} KiB)")
    return path


# --- rendering --------------------------------------------------------------


def find_godot(explicit: str | None) -> str:
    if explicit:
        if os.path.isfile(explicit):
            return explicit
        found = shutil.which(explicit)
        if found:
            return found
        raise V22Error(f"--godot does not name an executable: {explicit}")
    for variable in ("GODOT_BIN", "GODOT4_BIN"):
        value = os.environ.get(variable)
        if value and os.path.isfile(value):
            return value
    for name in ("godot", "godot4"):
        found = shutil.which(name)
        if found:
            return found
    raise V22Error(
        "cannot find Godot 4. Pass --godot PATH, set $GODOT_BIN, or put it on PATH."
    )


def run_godot(godot: str, extra: Sequence[str], label: str) -> float:
    started = time.perf_counter()
    completed = subprocess.run(
        [godot, "--path", GODOT_PROJECT, RENDER_SCENE, "--", *extra],
        cwd=PROJECT_ROOT, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
    )
    elapsed = time.perf_counter() - started
    errors = "\n".join((completed.stderr or "").splitlines()[-30:])
    if completed.returncode != 0:
        raise V22Error(f"{label}: Godot exited {completed.returncode}\n{errors}")
    for line in (completed.stderr or "").splitlines():
        if "SCRIPT ERROR" in line or "Parse Error" in line:
            raise V22Error(f"{label}: Godot reported an error: {line.strip()}")
    if errors.strip():
        print(f"  godot stderr tail:\n{errors}")
    return elapsed


def _render(godot: str, seed: int, replay_path: str, track_path: str,
            frames_dir: str, video: str, label: str) -> dict[str, Any]:
    if os.path.isdir(frames_dir):
        shutil.rmtree(frames_dir)
    os.makedirs(frames_dir, exist_ok=True)
    with open(track_path, "r", encoding="utf-8") as handle:
        end = float(json.load(handle)["duration"])
    flags = [
        f"--out-dir={os.path.abspath(frames_dir)}",
        f"--replay={os.path.abspath(replay_path)}",
        f"--cameras={os.path.abspath(track_path)}",
        "--clip=1", f"--end={end:.6f}", f"--fps={FPS}",
        f"--width={WIDTH}", f"--height={HEIGHT}",
        "--layout=b", "--detail=hero", "--routes=both",
    ]
    contract = _start_contract(seed)
    if os.path.isfile(contract):
        flags.append(f"--start-contract={os.path.abspath(contract)}")
    elapsed = run_godot(godot, flags, label)
    names = sorted(f for f in os.listdir(frames_dir) if f.endswith(".png"))
    if not names:
        raise V22Error(f"{label}: no frames were written")
    print(f"{label}: {len(names)} frames in {elapsed:.1f} s "
          f"({elapsed / len(names) * 1000:.0f} ms/frame)")
    _encode(frames_dir, names, video)
    return {"frames": len(names), "video": video}


def _encode(frames_dir: str, names: Sequence[str], video: str) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise V22Error("ffmpeg is not on PATH; the frames are rendered but not encoded")
    first = int(names[0].split("_")[1].split(".")[0])
    os.makedirs(os.path.dirname(os.path.abspath(video)), exist_ok=True)
    done = subprocess.run(
        [ffmpeg, "-y", "-framerate", str(FPS), "-start_number", str(first),
         "-i", os.path.join(frames_dir, "frame_%06d.png"),
         "-frames:v", str(len(names)), "-an",
         "-c:v", "libx264", "-preset", VIDEO_PRESET, "-crf", str(VIDEO_CRF),
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", video],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if done.returncode != 0:
        tail = "\n".join((done.stderr or "").splitlines()[-15:])
        raise V22Error(f"ffmpeg exited {done.returncode}\n{tail}")
    print(f"video: {video}  {os.path.getsize(video) / (1024 * 1024):.1f} MiB")


def stage_race(godot: str, seed: int) -> dict[str, Any]:
    return _render(godot, seed, _replay_path(seed), RACE_TRACK.format(seed=seed),
                   os.path.join(WORK_DIR, "race_frames"), RACE_MASTER, "race")


def stage_preview(godot: str, seed: int) -> dict[str, Any]:
    frozen = FROZEN_REPLAY.format(seed=seed)
    if not os.path.isfile(frozen):
        stage_freeze(seed)
    return _render(godot, seed, frozen, PREVIEW_TRACK.format(seed=seed),
                   os.path.join(WORK_DIR, "preview_frames"), PREVIEW_MASTER, "preview")


def stage_check(seed: int) -> list[str]:
    replay = _load_replay(seed)
    with open(RACE_TRACK.format(seed=seed), "r", encoding="utf-8") as handle:
        race = json.load(handle)
    problems = chase_camera.check_chase(race, replay)
    print(f"check: {len(problems)} findings on the race track")
    for problem in problems:
        print(f"    - {problem}")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=5432)
    parser.add_argument("--godot", default=None)
    parser.add_argument("--stage", default="all",
                        choices=("solve", "freeze", "race", "preview", "check", "all"))
    args = parser.parse_args(argv)

    stages = (("solve", "freeze", "race", "preview", "check")
              if args.stage == "all" else (args.stage,))
    godot = None
    for stage in stages:
        print(f"--- {stage} ---")
        if stage == "solve":
            stage_solve(args.seed)
        elif stage == "freeze":
            stage_freeze(args.seed)
        elif stage in ("race", "preview"):
            godot = godot or find_godot(args.godot)
            (stage_race if stage == "race" else stage_preview)(godot, args.seed)
        elif stage == "check":
            stage_check(args.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

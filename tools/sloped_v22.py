"""Solve and render V22 or V22.1: the preview, the chase camera and the pacing.

    python tools/sloped_v22.py --stage all --godot PATH
    python tools/sloped_v22.py --edition v221 --stage all --godot PATH

**Two editions, one pipeline.** The stages below are about Godot, ffmpeg and
where files go, and none of that changed between V22 and V22.1; what changed is
which module solves the two tracks. So the edition is a lookup - see `EDITIONS` -
and `--edition v22` still writes byte for byte what it wrote before.

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

from sloped import (cameras, chase_camera, course_preview, v22, v221,
                    v221_finish, v23)
from sloped.course import sloped_course

PROJECT_ROOT = os.getcwd()
GODOT_PROJECT = os.path.join(PROJECT_ROOT, "godot")
RENDER_SCENE = "res://scenes/SlopedRaceRender.tscn"

OUT_DIR = os.path.join("output", "sloped_race_v1")

# One entry per edition. `module` supplies `build_race_track`,
# `build_preview_track` and `assert_handoff`; `check` is what the solved race
# track is held to.
#
# **V22.1's checker is not V22's, and the difference is one retired finding.**
# `chase_camera.check_chase` allows a chase cut's aim to lead the pack by its
# own look-ahead, and V22.1's `final` cut is aimed at the finish *line* rather
# than at the pack - which is the whole of candidate A. `v221_finish.
# check_finish` is `check_chase` with that one clause exempted for cuts whose
# target is a node, and nothing else changed. See its docstring.
EDITIONS: dict[str, dict[str, Any]] = {
    "v22": {
        "module": v22,
        "work": "v22",
        "scene": (),
        "race_track": os.path.join(OUT_DIR, "cameras_v22_{seed}.json"),
        "preview_track": os.path.join(OUT_DIR, "preview_v22_{seed}.json"),
        "check": chase_camera.check_chase,
    },
    "v221": {
        "module": v221,
        "work": "v221",
        # **The one render flag this pass adds, and it draws nothing new.**
        # V22.1's finish parks up-course of the line, which is the one place on
        # the course from which the FINISH board is unreadable: its face and its
        # letters are on the down-course side. `--finish-sign=double` copies
        # them onto the back. No collider, no timing and no physics is touched,
        # and every other edition renders with the flag absent. See
        # `sloped_race_scene._face_finish_sign_both_ways`.
        "scene": ("--finish-sign=double",),
        "race_track": os.path.join(OUT_DIR, "cameras_v221_{seed}.json"),
        "preview_track": os.path.join(OUT_DIR, "preview_v221_{seed}.json"),
        "check": v221_finish.check_finish,
    },
    # **V23 is V22.1's film in a different world.** It shares V22.1's module,
    # its checker and - deliberately - its two *solved track files*, not copies
    # of them. A repaint that re-solved its cameras would be asserting that the
    # solve is deterministic rather than relying on the same numbers; pointing
    # both editions at `cameras_v221_{seed}.json` makes the camera track
    # identical by construction, and there is no drift left for a test to have
    # to catch. `--stage solve` is therefore not part of a V23 build.
    #
    # What differs is three render flags, and they are in `sloped/v23.py`.
    "v23": {
        "module": v221,
        "work": "v23",
        "scene": v23.SCENE_FLAGS,
        "race_track": os.path.join(OUT_DIR, "cameras_v221_{seed}.json"),
        "preview_track": os.path.join(OUT_DIR, "preview_v221_{seed}.json"),
        "check": v221_finish.check_finish,
    },
}
DEFAULT_EDITION = "v22"


def work_dir(edition: str) -> str:
    return os.path.join(OUT_DIR, EDITIONS[edition]["work"])


def race_track_path(edition: str, seed: int) -> str:
    return EDITIONS[edition]["race_track"].format(seed=seed)


def preview_track_path(edition: str, seed: int) -> str:
    return EDITIONS[edition]["preview_track"].format(seed=seed)


def frozen_path(edition: str, seed: int) -> str:
    return os.path.join(work_dir(edition), f"frozen_{seed}.json")


def race_master(edition: str) -> str:
    return os.path.join(work_dir(edition), "race_master.mp4")


def preview_master(edition: str) -> str:
    return os.path.join(work_dir(edition), "preview_master.mp4")

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


def stage_solve(seed: int, edition: str = DEFAULT_EDITION) -> dict[str, Any]:
    module = EDITIONS[edition]["module"]
    track_path = race_track_path(edition, seed)
    replay = _load_replay(seed)
    machine = sloped_course(routes="both")

    race = module.build_race_track(replay, machine, fps=FPS)
    cameras.write_track(race, track_path)
    print(f"race: {len(race['cuts'])} cuts over {race['duration']:.6f} s, "
          f"omitting {race['omitted']:.6f} s -> {track_path}")
    rows = {row["cut"]: row for row in cameras.frame_report(race, replay)}
    for segment in race["edit"]:
        row = rows.get(segment["cut"], {})
        print(f"    {segment['cut']:9s} out {segment['out'][0]:8.4f}-{segment['out'][1]:8.4f}"
              f"  replay {segment['replay'][0]:9.4f}-{segment['replay'][1]:9.4f}"
              f"  racers {row.get('in_frame', '-')}/{row.get('of', '-')}"
              f"  nearest {row.get('nearest_px', 0.0):.0f} px")

    track, report = module.build_preview_track(race, machine, seed)
    course_preview.write_track(track, preview_track_path(edition, seed))
    frames = module.preview_frames(track)
    print(f"preview: {frames} frames, {report['duration']:.4f} s of frame centres, "
          f"{module.preview_prefix(track):.4f} s of screen "
          f"-> {preview_track_path(edition, seed)}")
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
    try:
        deltas = module.assert_handoff(race, track)
    except ValueError as error:
        raise V22Error(str(error)) from None
    print("    handoff exact to "
          + "  ".join(f"{name} {value:.6f}" for name, value in deltas.items()))
    return {"race": race, "preview": track, "report": report}


def stage_freeze(seed: int, edition: str = DEFAULT_EDITION) -> str:
    replay = _load_replay(seed)
    track_path = preview_track_path(edition, seed)
    if not os.path.isfile(track_path):
        raise V22Error(f"solve first: {track_path} is missing")
    with open(track_path, "r", encoding="utf-8") as handle:
        seconds = float(json.load(handle)["duration"])
    frozen = course_preview.frozen_replay(replay, seconds, FPS)
    os.makedirs(work_dir(edition), exist_ok=True)
    path = frozen_path(edition, seed)
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
            frames_dir: str, video: str, label: str,
            scene_flags: Sequence[str] = ()) -> dict[str, Any]:
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
        *scene_flags,
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


def stage_race(godot: str, seed: int, edition: str = DEFAULT_EDITION) -> dict[str, Any]:
    return _render(godot, seed, _replay_path(seed), race_track_path(edition, seed),
                   os.path.join(work_dir(edition), "race_frames"),
                   race_master(edition), "race",
                   EDITIONS[edition].get("scene", ()))


def stage_preview(godot: str, seed: int,
                  edition: str = DEFAULT_EDITION) -> dict[str, Any]:
    frozen = frozen_path(edition, seed)
    if not os.path.isfile(frozen):
        stage_freeze(seed, edition)
    return _render(godot, seed, frozen, preview_track_path(edition, seed),
                   os.path.join(work_dir(edition), "preview_frames"),
                   preview_master(edition), "preview",
                   EDITIONS[edition].get("scene", ()))


def stage_check(seed: int, edition: str = DEFAULT_EDITION) -> list[str]:
    replay = _load_replay(seed)
    with open(race_track_path(edition, seed), "r", encoding="utf-8") as handle:
        race = json.load(handle)
    problems = EDITIONS[edition]["check"](race, replay)
    print(f"check: {len(problems)} findings on the race track")
    for problem in problems:
        print(f"    - {problem}")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=5432)
    parser.add_argument("--godot", default=None)
    parser.add_argument("--edition", default=DEFAULT_EDITION, choices=sorted(EDITIONS))
    parser.add_argument("--stage", default="all",
                        choices=("solve", "freeze", "race", "preview", "check", "all"))
    args = parser.parse_args(argv)

    stages = (("solve", "freeze", "race", "preview", "check")
              if args.stage == "all" else (args.stage,))
    godot = None
    for stage in stages:
        print(f"--- {stage} ({args.edition}) ---")
        if stage == "solve":
            stage_solve(args.seed, args.edition)
        elif stage == "freeze":
            stage_freeze(args.seed, args.edition)
        elif stage in ("race", "preview"):
            godot = godot or find_godot(args.godot)
            (stage_race if stage == "race" else stage_preview)(
                godot, args.seed, args.edition)
        elif stage == "check":
            stage_check(args.seed, args.edition)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

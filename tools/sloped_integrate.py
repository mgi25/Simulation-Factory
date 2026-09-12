"""One seed, end to end: race, replay, cameras, validation, stills, clip.

    python tools/sloped_integrate.py --seed 16 --stage all

Stages, each of which can be run on its own so a camera tweak does not cost a
re-simulation:

    race       run the seed, write the authoritative replay
    cameras    solve the shot list from that replay, write the camera track
    check      contact-validate the replay against the course it will be drawn on
    stills     one Godot frame per cut, into docs/validation/sloped_race_v1/
    clip       every frame of the race, then ffmpeg into one mp4
    all        all five, in that order

## What is authoritative

The replay. Nothing downstream re-simulates: `sloped_race_scene.gd` reads
transforms and Godot never calls `stepSimulation`. The replay is written in
simulation units and carries `units.render_scale`, which is the one conversion
in the pipeline and is applied on one node.

The camera track is *derived* and can be rebuilt at any time from the replay
alone, which is why it is a separate file rather than a section of the replay:
a camera is a presentation decision and a replay is a physical record, and
mixing them would make a re-cut look like a re-run.

## Finding Godot

`--godot`, then `$GODOT_BIN` or `$GODOT4_BIN`, then the PATH. It is not on the
PATH on the machine this was built on and the console build is the one to use,
because GDScript pushes parse and runtime errors to stderr *without* failing
the process - so a zero exit is not on its own evidence that the scene built.
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

from marble3d.config import DEFAULT_CONFIG
from marble3d.replay import read_replay, write_replay
from sloped import cameras as cameras_module
from sloped.contact import check_replay
from sloped.course import check as check_course, sloped_course
from sloped.race import run_race

PROJECT_ROOT = os.getcwd()
GODOT_PROJECT = os.path.join(PROJECT_ROOT, "godot")
RENDER_SCENE = "res://scenes/SlopedRaceRender.tscn"

OUT_DIR = os.path.join("output", "sloped_race_v1")
STILLS_DIR = os.path.join("docs", "validation", "sloped_race_v1")
FRAMES_DIR = os.path.join(OUT_DIR, "frames")
# The default name, kept so an existing invocation reproduces V1.3's clip.
# `--video` overrides it: the V1.9 physics lock writes
# `real_race_final_physics.mp4`, and a render that silently overwrote a
# previous version's deliverable would be the wrong kind of convenience.
VIDEO_PATH = os.path.join(OUT_DIR, "real_race_v13.mp4")

WIDTH = 1080
HEIGHT = 1920
FPS = 60
VIDEO_CRF = 16
VIDEO_PRESET = "slow"

GODOT_ENV_VARS = ("GODOT_BIN", "GODOT4_BIN")
GODOT_ON_PATH = ("godot", "godot4")

# Which cuts become the committed stills. Section 43 names seven moments; the
# cut list has ten, so `hairpin` and `straight` fold into `first_turn` and
# `long_track` and the establishing frame is not a validation still.
STILL_NAMES = {
    "start": "start",
    "descent": "first_descent",
    "hairpin": "first_turn",
    "straight": "long_track",
    "obstacle": "obstacle",
    "split": "split",
    "branch": "final_sprint",
    "merge": "merge",
    "finish": "finish",
}


class IntegrationError(RuntimeError):
    pass


def find_godot(explicit: str | None) -> str:
    if explicit:
        if os.path.isfile(explicit):
            return explicit
        found = shutil.which(explicit)
        if found:
            return found
        raise IntegrationError(f"--godot does not name an executable: {explicit}")
    for variable in GODOT_ENV_VARS:
        value = os.environ.get(variable)
        if value and os.path.isfile(value):
            return value
    for name in GODOT_ON_PATH:
        found = shutil.which(name)
        if found:
            return found
    raise IntegrationError(
        "cannot find Godot 4. Pass --godot PATH, set "
        f"{' or '.join('$' + n for n in GODOT_ENV_VARS)}, or put it on PATH."
    )


def paths_for(seed: int) -> dict[str, str]:
    return {
        "replay": os.path.join(OUT_DIR, f"race_{seed}.json"),
        "cameras": os.path.join(OUT_DIR, f"cameras_{seed}.json"),
        "contact": os.path.join(OUT_DIR, f"contact_{seed}.json"),
        # The start module's own geometry, so the renderer draws the start the
        # physics runs rather than the one the layout table draws. See
        # `tools/sloped_start_contract.py`.
        "start": os.path.join(OUT_DIR, f"start_contract_{seed}.json"),
    }


# --- stages ---------------------------------------------------------------


def stage_race(
    seed: int, marbles: int, duration: float, out: str, routes: str = "blue"
) -> dict[str, Any]:
    machine = sloped_course(routes=routes)
    findings = check_course(machine)
    if findings:
        raise IntegrationError(
            "the course does not check out; refusing to render it\n  "
            + "\n  ".join(str(f) for f in findings)
        )
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    started = time.perf_counter()
    outcome, replay = run_race(
        seed=seed, machine=machine, marble_count=marbles, duration=duration, with_replay=True
    )
    if replay is None:
        raise IntegrationError("the race produced no replay")
    write_replay(replay, out)
    print(
        f"race seed {seed}: {outcome.seconds:.3f} s, {outcome.finished}/{marbles} finished, "
        f"{outcome.escaped} escaped, {outcome.stuck} jammed, {len(replay.frames)} frames "
        f"in {time.perf_counter() - started:.1f} s wall"
    )
    print(f"  digest {replay.digest()}  events {replay.event_digest()}")
    print(f"  routes {outcome.route_counts}  lead changes {outcome.lead_changes}")
    for racer in sorted(outcome.racers, key=lambda r: r.finish_order or 99):
        print(
            f"    {racer.finish_order or '-':>2} marble {racer.marble_id} slot {racer.start_slot} "
            f"{racer.route or '-':7s} {racer.state:9s} "
            f"{'' if racer.finish_time is None else format(racer.finish_time, '.3f') + ' s'}"
        )
    print(f"  wrote {out}")
    return {"outcome": outcome.to_json(), "replay": out}


def stage_start_contract(out: str, routes: str = "both") -> dict[str, Any]:
    """The start module's geometry, read off the built module and written out.

    Its own stage rather than a line inside `race`, because the render stages
    need it and a camera tweak should not have to re-simulate to get it.
    """
    from tools.sloped_start_contract import contract as build_contract

    data = build_contract(routes)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=1, sort_keys=True)
        handle.write("\n")
    print(
        f"start: {data['kind']} lift {data['lift']} above {data['node']}, "
        f"{data['bays']} bays at {data['bay_pitch']} layout, "
        f"{len(data['parts'])} kinematic parts"
    )
    print(f"  wrote {out}")
    return data


def stage_cameras(replay_path: str, out: str, routes: str = "blue") -> dict[str, Any]:
    with open(replay_path, "r", encoding="utf-8") as handle:
        replay = json.load(handle)
    machine = sloped_course(routes=routes)
    track = cameras_module.build_track(replay, machine, fps=FPS)
    problems = cameras_module.check_track(track, replay)
    cameras_module.write_track(track, out)
    print(f"cameras: {len(track['cuts'])} cuts over {track['duration']:.2f} s -> {out}")
    rows = {row["cut"]: row for row in cameras_module.frame_report(track, replay)}
    for cut in track["cuts"]:
        row = rows.get(cut["name"], {})
        print(
            f"    {cut['name']:11s} {cut['from']:6.2f}-{cut['to']:6.2f}s  "
            f"target {cut['target']:6s} fov {cut['fov']:.0f} dist {cut['distance']:.1f}"
            f"  lift {cut.get('lift_deg', 0.0):.0f} deg"
            f"  racers {row.get('in_frame', '-')}/{row.get('of', '-')}"
            f"  nearest {row.get('nearest_px', 0.0):.0f} px"
        )
    if problems:
        print("  camera findings:")
        for problem in problems:
            print(f"    - {problem}")
    return {"cameras": out, "problems": problems}


def stage_check(
    replay_path: str, out: str, stride: int, routes: str = "blue"
) -> dict[str, Any]:
    with open(replay_path, "r", encoding="utf-8") as handle:
        replay = json.load(handle)
    machine = sloped_course(routes=routes)
    report = check_replay(replay, machine, stride=stride)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(report.to_json(), handle, indent=1, sort_keys=True)
        handle.write("\n")
    print(
        f"contact: {report.frames} frames, {report.channel_samples} channel samples "
        f"({report.off_channel_samples} on stations), "
        f"worst penetration {report.worst_penetration:.4f}, "
        f"worst resting gap {report.worst_float:.4f}"
    )
    if report.findings:
        print(f"  {len(report.findings)} findings: {report.by_kind()}")
        for finding in report.findings[:8]:
            print(
                f"    - {finding.kind} marble {finding.marble} at {finding.time:.2f}s "
                f"on {finding.run}[{finding.sample}] by {finding.value:.4f}"
            )
    else:
        print("  no findings")
    print(f"  wrote {out}")
    return report.to_json()


def godot_command(godot: str, extra: Sequence[str]) -> list[str]:
    """The invocation `tools/course_lab.py` already proves works, and no more.

    No `--rendering-driver`, no `--headless`: the layout proof's frames were
    taken with the defaults and the point of extending its scene is that the
    course in frame is the course it photographed.
    """
    return [godot, "--path", GODOT_PROJECT, RENDER_SCENE, "--", *extra]


def run_godot(godot: str, extra: Sequence[str], label: str) -> float:
    started = time.perf_counter()
    completed = subprocess.run(
        godot_command(godot, extra),
        cwd=PROJECT_ROOT,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    elapsed = time.perf_counter() - started
    errors = "\n".join((completed.stderr or "").splitlines()[-30:])
    if completed.returncode != 0:
        raise IntegrationError(
            f"{label}: Godot exited {completed.returncode}\n--- stderr ---\n{errors}"
        )
    for line in (completed.stderr or "").splitlines():
        if "SCRIPT ERROR" in line or "Parse Error" in line:
            raise IntegrationError(f"{label}: Godot reported an error: {line.strip()}")
    if errors.strip():
        print(f"  godot stderr tail:\n{errors}")
    return elapsed


def start_flag(seed: int | None = None) -> list[str]:
    """`--start-contract=` when the file exists, and nothing when it does not.

    Absent, `course_machine` builds the V1 fan pod on the authored node, which
    is what every earlier lab frame has and what keeps them reproducing.
    """
    path = _START_CONTRACT[0]
    if not path or not os.path.isfile(path):
        return []
    return [f"--start-contract={os.path.abspath(path)}"]


_START_CONTRACT = [""]


def stage_stills(godot: str, replay_path: str, cameras_path: str) -> dict[str, Any]:
    with open(cameras_path, "r", encoding="utf-8") as handle:
        track = json.load(handle)
    names = [cut["name"] for cut in track["cuts"] if cut["name"] in STILL_NAMES]
    scratch = os.path.join(OUT_DIR, "stills")
    os.makedirs(scratch, exist_ok=True)
    elapsed = run_godot(
        godot,
        [
            f"--out-dir={os.path.abspath(scratch)}",
            f"--replay={os.path.abspath(replay_path)}",
            f"--cameras={os.path.abspath(cameras_path)}",
            f"--stills={','.join(names)}",
            *start_flag(),
            f"--width={WIDTH}",
            f"--height={HEIGHT}",
            "--layout=b",
            "--detail=hero",
        ],
        "stills",
    )
    os.makedirs(STILLS_DIR, exist_ok=True)
    written = []
    for name in names:
        source = os.path.join(scratch, f"{name}.png")
        if not os.path.isfile(source):
            raise IntegrationError(f"stills: Godot did not write {source}")
        target = os.path.join(STILLS_DIR, f"{STILL_NAMES[name]}.png")
        shutil.copyfile(source, target)
        written.append(target)
    print(f"stills: {len(written)} frames in {elapsed:.1f} s")
    for path in written:
        print(f"    {path}  {os.path.getsize(path) / 1024:.0f} KiB")
    return {"stills": written}


def stage_clip(godot: str, replay_path: str, cameras_path: str, fps: int,
               video_path: str = "") -> dict[str, Any]:
    if os.path.isdir(FRAMES_DIR):
        shutil.rmtree(FRAMES_DIR)
    os.makedirs(FRAMES_DIR, exist_ok=True)

    # The clip is as long as the *race*, which is the camera track's span: from
    # the gate to the last crossing plus the finish cut's hold. The renderer on
    # its own would use the replay's duration, and the replay is as long as the
    # simulation window it was asked for - 30 s for the production seed, whose
    # last marble crosses at 18.85. Rendering to 30 spends nine and a half
    # seconds on a parked field under a camera that has run out of cuts, at
    # 371 ms a frame.
    #
    # This is not section 40's forbidden shortening. Nothing is sped up, no
    # frame between the gate and the last crossing is dropped, and gravity is
    # untouched: what is cut is the simulation continuing after the race is
    # over.
    with open(cameras_path, "r", encoding="utf-8") as handle:
        track = json.load(handle)
    end = float(track["duration"])

    elapsed = run_godot(
        godot,
        [
            f"--out-dir={os.path.abspath(FRAMES_DIR)}",
            *start_flag(),
            f"--replay={os.path.abspath(replay_path)}",
            f"--cameras={os.path.abspath(cameras_path)}",
            "--clip=1",
            f"--end={end:.6f}",
            f"--fps={fps}",
            f"--width={WIDTH}",
            f"--height={HEIGHT}",
            "--layout=b",
            "--detail=hero",
        ],
        "clip",
    )
    frames = sorted(f for f in os.listdir(FRAMES_DIR) if f.endswith(".png"))
    if not frames:
        raise IntegrationError("clip: no frames were written")
    print(f"clip: {len(frames)} frames in {elapsed:.1f} s ({elapsed / len(frames) * 1000:.0f} ms/frame)")

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise IntegrationError("ffmpeg is not on PATH; the frames are rendered but not encoded")
    first = int(frames[0].split("_")[1].split(".")[0])
    video = video_path or VIDEO_PATH
    os.makedirs(os.path.dirname(os.path.abspath(video)), exist_ok=True)
    command = [
        ffmpeg, "-y",
        "-framerate", str(fps),
        "-start_number", str(first),
        "-i", os.path.join(FRAMES_DIR, "frame_%06d.png"),
        "-frames:v", str(len(frames)),
        "-an",
        "-c:v", "libx264",
        "-preset", VIDEO_PRESET,
        "-crf", str(VIDEO_CRF),
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        video,
    ]
    completed = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if completed.returncode != 0:
        tail = "\n".join((completed.stderr or "").splitlines()[-15:])
        raise IntegrationError(f"ffmpeg exited {completed.returncode}\n{tail}")
    size = os.path.getsize(video) / (1024 * 1024)
    print(
        f"video: {video}  {size:.1f} MiB  {len(frames)} frames at {fps} fps "
        f"= {len(frames) / fps:.2f} s"
    )
    return {"video": video, "frames": len(frames), "seconds": len(frames) / fps}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--marbles", type=int, default=8)
    parser.add_argument("--duration", type=float, default=DEFAULT_CONFIG.duration_limit)
    parser.add_argument(
        "--stage",
        default="all",
        choices=("race", "start", "cameras", "check", "stills", "clip", "all",
                 "render"),
    )
    parser.add_argument("--fps", type=int, default=FPS)
    parser.add_argument("--stride", type=int, default=1)
    parser.add_argument("--godot", default="")
    parser.add_argument(
        "--video", default="",
        help="where to write the clip; defaults to VIDEO_PATH",
    )
    # **The race, the cameras and the contact check must all build the same
    # course**, and until V1.15 all three built `routes="blue"` regardless -
    # which was right while the through route was the only one that worked and
    # is wrong now that orange ships. A replay of a two-route race validated
    # against a blue-only machine reports every orange marble as off the
    # course, and a camera solved on one cannot find the branch at all.
    parser.add_argument(
        "--routes", default="both", choices=("blue", "both"),
        help="which routes the course offers; \"both\" builds the fork",
    )
    args = parser.parse_args(argv)

    paths = paths_for(args.seed)
    stages = (
        ("race", "start", "cameras", "check", "stills", "clip")
        if args.stage == "all"
        else ("start", "stills", "clip")
        if args.stage == "render"
        else (args.stage,)
    )
    godot = ""
    if any(stage in ("stills", "clip") for stage in stages):
        godot = find_godot(args.godot or None)
        print(f"godot: {godot}")

    _START_CONTRACT[0] = paths["start"]
    for stage in stages:
        print(f"--- {stage} ---")
        if stage == "start":
            stage_start_contract(paths["start"], args.routes)
        elif stage == "race":
            stage_race(
                args.seed, args.marbles, args.duration, paths["replay"], args.routes
            )
        elif stage == "cameras":
            stage_cameras(paths["replay"], paths["cameras"], args.routes)
        elif stage == "check":
            stage_check(paths["replay"], paths["contact"], args.stride, args.routes)
        elif stage == "stills":
            stage_stills(godot, paths["replay"], paths["cameras"])
        elif stage == "clip":
            stage_clip(godot, paths["replay"], paths["cameras"], args.fps,
                       args.video)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

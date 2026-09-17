"""Drive Godot over a Race #2 race: stills, phone sheets, clips, video.

Usage:

    python tools/race2_render.py sheet  --seed=1        # one frame per cut
    python tools/race2_render.py phone  --seed=1        # the same at 270x480
    python tools/race2_render.py clip   --seed=1        # every frame
    python tools/race2_render.py video  --seed=1        # clip, then encode

Finding Godot, in order: `--godot`, then `$GODOT_BIN` or `$GODOT4_BIN`, then
the PATH. The same order `tools/course_lab.py` uses, because a lab that found
Godot differently from the labs beside it would be a second thing to get wrong
on a new machine.

Everything this renders comes out of `tools/race2_camera.py`: a replay, a
geometry export and a camera track, all three named after the course and the
seed. This tool does not simulate - if the three files are missing it says so
rather than quietly racing a different seed.
"""

from __future__ import annotations

import argparse
import glob
import os
import shutil
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

GODOT_PROJECT = os.path.join(REPO, "godot")
RENDER_SCENE = "res://scenes/Race2Render.tscn"
GODOT_ENV_VARS = ("GODOT_BIN", "GODOT4_BIN")
GODOT_ON_PATH = ("godot", "godot4", "Godot_v4.7.2-stable_win64.exe")

DELIVERY = (1080, 1920)
PHONE = (270, 480)


class RenderError(RuntimeError):
    pass


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


def run_godot(command: list[str], label: str) -> str:
    started = time.time()
    result = subprocess.run(command, cwd=REPO, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    elapsed = time.time() - started
    if result.returncode != 0:
        tail = "\n".join((result.stdout or "").splitlines()[-40:])
        errors = "\n".join((result.stderr or "").splitlines()[-40:])
        raise RenderError(
            f"{label}: Godot exited {result.returncode}\n--- stdout ---\n{tail}"
            f"\n--- stderr ---\n{errors}"
        )
    # GDScript pushes parse and runtime errors to stderr without failing the
    # process, so a zero exit is not on its own proof the scene was built.
    for line in (result.stderr or "").splitlines():
        if "SCRIPT ERROR" in line or "Parse Error" in line:
            raise RenderError(f"{label}: {line.strip()}")
    # **`stage:` is here because its absence hid a shipped defect.**
    # `race2_scene._build_stage` prints a per-section census of what the stage
    # actually built, and `environment_stage` prints a line for every pad, bay
    # or wall segment its clearance guards *refused*. Neither was surfaced, so
    # a profile could author twelve floor inlays and two bays, have eight
    # inlays and one bay silently rejected, and render with no sign of it -
    # which is exactly what the V30 profile does, and what V30.1 found only by
    # reimplementing the guards in Python. One census line per render is a
    # cheap way for the next pass not to need that.
    for line in (result.stdout or "").splitlines():
        stripped = line.strip()
        if stripped.startswith(("race2:", "cameras:", "scene:", "rendered",
                                "adapter:", "stage:", "environment_stage:")):
            print(f"    {stripped}")
    print(f"  {label}: {elapsed:.1f}s")
    return result.stdout or ""


def inputs_for(out: str, course: str, seed: int) -> tuple[str, str, str]:
    stem = os.path.join(out, f"race2_{course}_{seed}")
    paths = (f"{stem}.geometry.json", f"{stem}.replay.json", f"{stem}.cameras.json")
    missing = [p for p in paths if not os.path.isfile(p)]
    if missing:
        raise RenderError(
            "missing "
            + ", ".join(os.path.basename(p) for p in missing)
            + f"\n  run: python tools/race2_camera.py --course={course} --seed={seed}"
        )
    return paths


def base_command(godot: str, out_dir: str, course: str, seed: int, out: str,
                 size: tuple[int, int], environment: str, racers: str,
                 show: str, track: str = "", track_probe: str = "",
                 faces: str = "") -> list[str]:
    geometry, replay, cameras = inputs_for(out, course, seed)
    command = [
        godot, "--path", GODOT_PROJECT, RENDER_SCENE, "--",
        f"--out-dir={os.path.abspath(out_dir)}",
        f"--geometry={os.path.abspath(geometry)}",
        f"--replay={os.path.abspath(replay)}",
        f"--cameras={os.path.abspath(cameras)}",
        f"--width={size[0]}", f"--height={size[1]}",
        f"--racers={racers}", f"--show={show}",
    ]
    if environment:
        command.append(f"--environment={environment}")
    # Both absent by default, and both absent is the V31 render. A flag that is
    # only appended when it is asked for is a flag that cannot change a command
    # line somebody already reproduced.
    if track:
        command.append(f"--track={track}")
    if track_probe:
        command.append(f"--track-probe={track_probe}")
    # Absent by default, and absent is V32's render. `--faces=both` draws the
    # channel strip double-sided, which is V32.1's whole geometric fix; see
    # `race2_track_surface.faces` for the measurement behind it.
    if faces:
        command.append(f"--faces={faces}")
    return command


def cut_names(out: str, course: str, seed: int) -> list[str]:
    import json

    _geometry, _replay, cameras = inputs_for(out, course, seed)
    with open(cameras, encoding="utf-8") as handle:
        track = json.load(handle)
    return [str(cut["name"]) for cut in track.get("cuts", [])]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("sheet", "phone", "clip", "video", "still"))
    parser.add_argument("--course", default="switchyard")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", default="output/race2")
    parser.add_argument("--frames", default="output/race2/frames")
    parser.add_argument("--godot", default="")
    parser.add_argument("--environment", default="")
    parser.add_argument("--racers", default="meridian")
    parser.add_argument("--show", default="all")
    parser.add_argument("--track", default="",
                        help="channel surface: v31 (default), A, B, C, mask")
    parser.add_argument("--track-probe", dest="track_probe", default="",
                        help="one material field at a time, e.g. roughness=0.5")
    parser.add_argument("--faces", default="",
                        help="channel strip: front (V32) or both (V32.1)")
    parser.add_argument("--fps", type=int, default=60)
    parser.add_argument("--start", type=float, default=0.0)
    parser.add_argument("--end", type=float, default=-1.0)
    parser.add_argument("--at", default="")
    parser.add_argument("--video", default="")
    args = parser.parse_args()

    godot = find_godot(args.godot or None)
    tag = f"{args.course}_{args.seed}"
    size = PHONE if args.mode == "phone" else DELIVERY

    if args.mode in ("sheet", "phone"):
        out_dir = os.path.join(args.frames, f"{args.mode}_{tag}")
        os.makedirs(out_dir, exist_ok=True)
        names = cut_names(args.out, args.course, args.seed)
        command = base_command(godot, out_dir, args.course, args.seed, args.out,
                               size, args.environment, args.racers, args.show,
                               args.track, args.track_probe, args.faces)
        command.append(f"--stills={','.join(names)}")
        run_godot(command, f"{args.mode} {tag}")
        print(f"  {len(names)} frames in {out_dir}")
        return 0

    if args.mode == "still":
        if not args.at:
            raise RenderError("--at=SECONDS[,SECONDS...] is required for still")
        out_dir = os.path.join(args.frames, f"still_{tag}")
        os.makedirs(out_dir, exist_ok=True)
        command = base_command(godot, out_dir, args.course, args.seed, args.out,
                               size, args.environment, args.racers, args.show,
                               args.track, args.track_probe, args.faces)
        command.append(f"--at={args.at}")
        run_godot(command, f"still {tag}")
        return 0

    out_dir = os.path.join(args.frames, f"clip_{tag}")
    os.makedirs(out_dir, exist_ok=True)
    for stale in glob.glob(os.path.join(out_dir, "frame_*.png")):
        os.remove(stale)
    command = base_command(godot, out_dir, args.course, args.seed, args.out,
                           size, args.environment, args.racers, args.show,
                           args.track, args.track_probe, args.faces)
    command += ["--clip=1", f"--fps={args.fps}", f"--start={args.start}"]
    if args.end > 0:
        command.append(f"--end={args.end}")
    run_godot(command, f"clip {tag}")
    frames = sorted(glob.glob(os.path.join(out_dir, "frame_*.png")))
    print(f"  {len(frames)} frames in {out_dir}")

    if args.mode == "video":
        target = args.video or os.path.join("exports", "race2_drama_camera",
                                            f"race2_{tag}.mp4")
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            print("  ffmpeg not on PATH; frames written, no video encoded")
            return 0
        first = int(os.path.basename(frames[0])[6:12]) if frames else 0
        encode = [
            ffmpeg, "-y", "-framerate", str(args.fps),
            "-start_number", str(first),
            "-i", os.path.join(out_dir, "frame_%06d.png"),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "17",
            "-preset", "slow", "-movflags", "+faststart", target,
        ]
        result = subprocess.run(encode, capture_output=True, text=True,
                                encoding="utf-8", errors="replace")
        if result.returncode != 0:
            raise RenderError("ffmpeg failed:\n" + (result.stderr or "")[-2000:])
        print(f"  wrote {target} ({os.path.getsize(target) / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RenderError as error:
        print(f"race2 render: {error}", file=sys.stderr)
        raise SystemExit(1)

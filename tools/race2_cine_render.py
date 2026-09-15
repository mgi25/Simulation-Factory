"""Render the V28 control and the three candidate cameras, and compare them.

Usage:

    python tools/race2_cine_render.py clips        # all four, full length
    python tools/race2_cine_render.py phone        # 270x480 versions
    python tools/race2_cine_render.py sections     # the five named sections
    python tools/race2_cine_render.py compare      # side-by-side and 4-up
    python tools/race2_cine_render.py all

Everything comes out of `output/race2/v281_camera/<CAM>/`, which
`tools/race2_cine.py` stages, and lands in `exports/race2_v281_cinematography/`.

The control is rendered by exactly the same path as the candidates, from V28's
own camera track copied unchanged. That is the point: a comparison in which the
control went through a different renderer measures the renderer.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

CAMERAS = ("V28", "A", "B", "C")
OUT = "output/race2/v281_camera"
FRAMES = "output/race2/v281_camera/frames"
EXPORT = "exports/race2_v281_cinematography"

# The five sections the brief asks for, as (name, start, end) in seconds. The
# bounds are the hero race's own beats, rounded to the nearest tenth, so the
# same window is cut from every candidate whatever its shot boundaries are.
SECTIONS = (
    ("1_opening", 0.0, 3.0),
    ("2_first_mechanism", 1.8, 5.2),
    ("3_switchbacks", 5.2, 10.0),
    ("4_late_race", 9.6, 13.6),
    ("5_final_sprint", 12.6, 19.15),
)


def ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found is None:
        raise SystemExit("ffmpeg is not on PATH")
    return found


def run(command: list[str], label: str) -> None:
    result = subprocess.run(command, cwd=REPO, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise SystemExit(f"{label} failed:\n{(result.stderr or result.stdout)[-2500:]}")
    print(f"  {label}")


def encode(folder: str, target: str, fps: int = 60, crf: int = 17) -> str:
    frames = sorted(glob.glob(os.path.join(folder, "frame_*.png")))
    if not frames:
        raise SystemExit(f"no frames in {folder}")
    first = int(os.path.basename(frames[0])[6:12])
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    run([
        ffmpeg(), "-y", "-framerate", str(fps), "-start_number", str(first),
        "-i", os.path.join(folder, "frame_%06d.png"),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", str(crf),
        "-preset", "slow", "-movflags", "+faststart", target,
    ], f"{os.path.basename(target)} ({len(frames)} frames)")
    return target


def film_end(camera: str, args) -> float:
    """How long this candidate's film is, from its own camera track.

    **Not the replay's duration.** The clip renderer walks the replay, which on
    the hero seed runs 36 seconds - the marbles keep rolling on the run-out long
    after the film is over - so a clip rendered without an end is 2155 frames of
    which 1005 are of a settled field. The film ends where the camera track
    does, and the track knows.
    """
    path = os.path.join(OUT, camera, f"race2_{args.course}_{args.seed}.cameras.json")
    with open(path, encoding="utf-8") as handle:
        return float(json.load(handle)["duration"])


def render_clips(args) -> None:
    for camera in args.cameras:
        folder = os.path.join(FRAMES, f"delivery_{camera}")
        os.makedirs(folder, exist_ok=True)
        run([
            sys.executable, "tools/race2_render.py", "clip",
            f"--seed={args.seed}", f"--course={args.course}",
            f"--out={OUT}/{camera}", f"--frames={folder}",
            f"--end={film_end(camera, args):.4f}",
        ], f"render {camera}")
        encode(os.path.join(folder, f"clip_{args.course}_{args.seed}"),
               os.path.join(EXPORT, f"race2_v281_{camera}.mp4"))


def phone_versions(args) -> None:
    """270x480 versions, scaled from the delivered file.

    Scaled rather than re-rendered on purpose: what a viewer sees on a phone is
    the delivered file resampled, so a phone proof that was rendered natively at
    270x480 would be a kinder picture than the one being shipped.
    """
    for camera in args.cameras:
        source = os.path.join(EXPORT, f"race2_v281_{camera}.mp4")
        if not os.path.isfile(source):
            print(f"  (skipping {camera}: no delivery clip yet)")
            continue
        run([ffmpeg(), "-y", "-i", source, "-vf", "scale=270:480:flags=lanczos",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
             "-preset", "slow", "-movflags", "+faststart",
             os.path.join(EXPORT, "phone", f"race2_v281_{camera}_phone.mp4")],
            f"phone {camera}")


def sections(args) -> None:
    for camera in args.cameras:
        source = os.path.join(EXPORT, f"race2_v281_{camera}.mp4")
        if not os.path.isfile(source):
            continue
        for name, start, end in SECTIONS:
            run([ffmpeg(), "-y", "-ss", f"{start}", "-to", f"{end}", "-i", source,
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
                 "-preset", "medium", "-movflags", "+faststart",
                 os.path.join(EXPORT, "sections", f"{camera}_{name}.mp4")],
                f"section {camera} {name}")


def side_by_side(args) -> None:
    control = os.path.join(EXPORT, "race2_v281_V28.mp4")
    for camera in [c for c in args.cameras if c != "V28"]:
        candidate = os.path.join(EXPORT, f"race2_v281_{camera}.mp4")
        if not (os.path.isfile(control) and os.path.isfile(candidate)):
            continue
        run([ffmpeg(), "-y", "-i", control, "-i", candidate,
             "-filter_complex",
             "[0:v]scale=540:960[l];[1:v]scale=540:960[r];[l][r]hstack=inputs=2",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
             "-preset", "medium", "-movflags", "+faststart",
             os.path.join(EXPORT, "compare", f"V28_vs_{camera}.mp4")],
            f"side by side V28 | {camera}")


def four_up(args) -> None:
    files = [os.path.join(EXPORT, f"race2_v281_{c}.mp4") for c in CAMERAS]
    if not all(os.path.isfile(f) for f in files):
        print("  (skipping 4-up: not every candidate is rendered)")
        return
    for name, start, end in SECTIONS:
        inputs: list[str] = []
        for path in files:
            inputs += ["-ss", f"{start}", "-to", f"{end}", "-i", path]
        run([ffmpeg(), "-y", *inputs, "-filter_complex",
             "[0:v]scale=360:640[a];[1:v]scale=360:640[b];"
             "[2:v]scale=360:640[c];[3:v]scale=360:640[d];"
             "[a][b][c][d]hstack=inputs=4",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
             "-preset", "medium", "-movflags", "+faststart",
             os.path.join(EXPORT, "compare", f"fourup_{name}.mp4")],
            f"4-up {name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("clips", "phone", "sections", "compare", "all"))
    parser.add_argument("--course", default="switchyard")
    parser.add_argument("--seed", type=int, default=8)
    parser.add_argument("--cameras", default=",".join(CAMERAS))
    args = parser.parse_args()
    args.cameras = [c for c in args.cameras.split(",") if c]
    for folder in ("compare", "sections", "phone"):
        os.makedirs(os.path.join(EXPORT, folder), exist_ok=True)

    if args.mode in ("clips", "all"):
        render_clips(args)
    if args.mode in ("phone", "all"):
        phone_versions(args)
    if args.mode in ("sections", "all"):
        sections(args)
    if args.mode in ("compare", "all"):
        side_by_side(args)
        four_up(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

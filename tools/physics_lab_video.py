"""Turn lab runs into the three videos section 21 of the brief asks for.

    surface25d_bowl.mp4     approach A
    rigid3d_bowl.mp4        approach B
    bowl_comparison.mp4     the two side by side, on one clock

Same camera, same framing, same marble colours, same clock. Both halves of the
comparison are advanced by output frame index, so they always show the same
instant and the shorter run holds its last frame rather than looping - an empty
bowl beside a full one being exactly the difference the video exists to show.

FFmpeg is found the way `rendering/encode.py` finds it: `--ffmpeg`, then
`$FFMPEG_BIN`, then the PATH. Nothing machine-specific is committed.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from physics_lab.analysis.render import Camera, render_pair, render_run  # noqa: E402
from physics_lab.common.labreplay import read_run  # noqa: E402

FPS = 60
DEFAULT_ROOT = os.path.join("output", "physics_lab", "video")


def find_ffmpeg(explicit: str | None) -> str:
    for candidate in (explicit, os.environ.get("FFMPEG_BIN"), "ffmpeg"):
        if not candidate:
            continue
        if os.path.isfile(candidate):
            return candidate
        found = shutil.which(candidate)
        if found:
            return found
    raise SystemExit("cannot find ffmpeg; pass --ffmpeg PATH or set $FFMPEG_BIN")


def encode(ffmpeg: str, frames_dir: str, out_path: str, fps: int = FPS) -> str:
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    subprocess.run(
        [
            ffmpeg, "-y", "-loglevel", "error",
            "-framerate", str(fps),
            "-i", os.path.join(frames_dir, "frame_%05d.png"),
            "-c:v", "libx264", "-preset", "slow", "-crf", "18",
            "-pix_fmt", "yuv420p",
            # Both dimensions to an even number; the side-by-side is 1920x960
            # and a single panel 960x960, but this keeps a resized run valid.
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            out_path,
        ],
        check=True,
    )
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--surface25d", default=os.path.join("output", "physics_lab", "surface25d_cal", "surface25d_seed7.json"))
    parser.add_argument("--rigid3d", default=os.path.join("output", "physics_lab", "rigid3d_cal", "rigid3d_seed7.json"))
    parser.add_argument("--output", default=DEFAULT_ROOT)
    parser.add_argument("--ffmpeg", default="")
    parser.add_argument("--elevation", type=float, default=34.0)
    parser.add_argument("--only", choices=("a", "b", "pair", "all"), default="all")
    args = parser.parse_args(argv)

    ffmpeg = find_ffmpeg(args.ffmpeg or None)
    camera = Camera(elevation_degrees=args.elevation)
    os.makedirs(args.output, exist_ok=True)

    written = []
    if args.only in ("a", "all"):
        run = read_run(args.surface25d)
        frames = os.path.join(args.output, "frames_surface25d")
        count = render_run(run, frames, camera, "Python 2.5D surface physics")
        written.append(encode(ffmpeg, frames, os.path.join(args.output, "surface25d_bowl.mp4")))
        print(f"surface25d: {count} frames -> {written[-1]}")

    if args.only in ("b", "all"):
        run = read_run(args.rigid3d)
        frames = os.path.join(args.output, "frames_rigid3d")
        count = render_run(run, frames, camera, "True 3D rigid bodies (PyBullet)")
        written.append(encode(ffmpeg, frames, os.path.join(args.output, "rigid3d_bowl.mp4")))
        print(f"rigid3d: {count} frames -> {written[-1]}")

    if args.only in ("pair", "all"):
        frames = os.path.join(args.output, "frames_comparison")
        count = render_pair(
            read_run(args.surface25d),
            read_run(args.rigid3d),
            frames,
            "Python 2.5D surface physics",
            "True 3D rigid bodies (PyBullet)",
            camera,
        )
        written.append(encode(ffmpeg, frames, os.path.join(args.output, "bowl_comparison.mp4")))
        print(f"comparison: {count} frames -> {written[-1]}")

    for path in written:
        print(f"  {path}  {os.path.getsize(path) / 1024:.0f} KiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

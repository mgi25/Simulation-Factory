"""Render the same moments of one race at several camera elevations.

The V0.3 production camera sat at 74 degrees because a course six times
longer than it is wide only gets its height back by looking down the length
of it. The argument was sound and the picture was still a plan view. This
tool exists so the replacement is chosen by looking rather than by arguing:

    python tools/race_camera_test.py output/race_v04/machine_1000_r16.json \\
        --angles 45,50,55,60,74 --at 3,8,14,19,24 --out docs/validation/race_v04/camera

Every angle renders the *same* replay at the *same* instants through the
*same* scene, so the only difference between two frames with the same name is
the lens. Each angle gets its own directory of `still_<frame>.png`, and a
contact strip per moment is written alongside so the five can be compared
without opening ten files.

Nothing here changes the simulation, and the elevation is passed to Godot at
render time rather than edited into the scene - see `_elevation_argument` in
`race_scene.gd` for why that matters.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.render_replay import find_godot, GODOT_PROJECT, PROJECT_ROOT, RENDER_SCENE  # noqa: E402

DEFAULT_ANGLES = (45.0, 50.0, 55.0, 60.0, 74.0)
DEFAULT_SECONDS = (3.0, 8.0, 14.0, 19.0, 24.0)
RENDER_FPS = 60


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sweep the production camera angle")
    parser.add_argument("replay", help="race replay JSON to shoot")
    parser.add_argument(
        "--angles", default=",".join(f"{a:g}" for a in DEFAULT_ANGLES),
        help="comma-separated elevations in degrees",
    )
    parser.add_argument(
        "--at", default=",".join(f"{s:g}" for s in DEFAULT_SECONDS),
        help="comma-separated moments, in seconds from the first frame",
    )
    parser.add_argument("--out", default="output/race_camera_test")
    parser.add_argument("--godot", default=None)
    parser.add_argument("--width", type=int, default=1080)
    parser.add_argument("--height", type=int, default=1920)
    return parser.parse_args()


def frame_indices(replay_path: str, seconds: list[float]) -> list[int]:
    """Turn wall-clock moments into output frame indices, clamped to the race."""
    with open(replay_path, encoding="utf-8") as handle:
        replay = json.load(handle)
    if replay.get("mode") != "race":
        raise SystemExit("camera tests are for race replays")
    last = max(0, len(replay.get("frames", [])) - 1)
    return sorted({min(last, max(0, int(round(s * RENDER_FPS)))) for s in seconds})


def render_angle(
    godot: str, replay_path: str, out_dir: str, frames: list[int],
    total: int, angle: float, width: int, height: int,
) -> None:
    os.makedirs(out_dir, exist_ok=True)
    command = [
        godot,
        "--path", GODOT_PROJECT, RENDER_SCENE, "--",
        f"--replay={os.path.abspath(replay_path)}",
        f"--out-dir={os.path.abspath(out_dir)}",
        f"--frames={total}",
        f"--fps={RENDER_FPS}",
        f"--width={width}",
        f"--height={height}",
        "--race-camera=production",
        f"--race-elevation={angle:g}",
        f"--stills={','.join(str(index) for index in frames)}",
    ]
    completed = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
    if completed.returncode != 0:
        raise SystemExit(f"Godot exited {completed.returncode} at {angle:g} degrees")


def main() -> None:
    args = parse_args()
    godot = find_godot(args.godot)
    angles = [float(v) for v in args.angles.split(",") if v.strip()]
    seconds = [float(v) for v in args.at.split(",") if v.strip()]

    with open(args.replay, encoding="utf-8") as handle:
        total = len(json.load(handle).get("frames", []))
    frames = frame_indices(args.replay, seconds)

    print(f"godot: {godot}")
    print(f"replay: {args.replay}  ({total} frames)")
    print(f"moments: {frames}")
    for angle in angles:
        out_dir = os.path.join(args.out, f"e{angle:g}")
        print(f"  {angle:g} degrees -> {out_dir}")
        render_angle(
            godot, args.replay, out_dir, frames, total, angle, args.width, args.height
        )

    print()
    print("compare with:")
    for index in frames:
        names = "  ".join(
            os.path.join(args.out, f"e{angle:g}", f"still_{index:06d}.png")
            for angle in angles
        )
        print(f"  frame {index}: {names}")


if __name__ == "__main__":
    main()

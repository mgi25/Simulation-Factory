"""Photograph the world kit on its own, before it is wired into the course.

    python tools/sloped_v251_kit.py --godot PATH
    python tools/sloped_v251_kit.py --rows cliff,needle --count 4 --elevation 9
    python tools/sloped_v251_kit.py --flora

The kit is the part of V25.1 a world render is the *slowest* way to judge: a
boulder at thirty units is forty pixels tall, and a change to its plan that is
obvious on a turntable is invisible in a race frame. So the forms are
photographed here first - lit by the world rig, at the value the world paints
them, against the world's own sky - and only wired into the course once they
read.

Two corrections in this pass were found here and nowhere else:

* the first ledge implementation stepped the radius **uniformly**, and the
  sheet showed a stack of cylinders - a wedding cake, which is exactly the
  repeated prism the brief bans. Ledges own an arc now.
* the hero tree was the *widest* plant as well as the tallest, and the sheet
  called it a parasol. A hero tree is taller than its neighbours, not fatter.

Low `--elevation` is for silhouettes against the sky, which is what a viewer
reads at phone size; the default 36 degrees is roughly a race camera's.

Nothing here is a deliverable and no profile names it. It renders
`res://scenes/WorldKitProbe.tscn`, which builds nothing but the kit.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from tools import sloped_v25_world as lab  # noqa: E402

SCENE = "res://scenes/WorldKitProbe.tscn"
OUT_DIR = os.path.join("output", "sloped_race_v1", "v251_world", "kit")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot")
    parser.add_argument("--out", help="where to write the PNG")
    parser.add_argument("--rows", default="",
                        help="comma-separated kit names, one row each")
    parser.add_argument("--count", type=int, default=4,
                        help="how many of each, at different seeds")
    parser.add_argument("--pitch", type=float, default=12.0)
    parser.add_argument("--elevation", type=float, default=36.0,
                        help="camera elevation in degrees; 9 for silhouettes")
    parser.add_argument("--flora", action="store_true",
                        help="draw the vegetation kit instead of the rock kit")
    args = parser.parse_args(argv)

    godot = lab.find_godot(args.godot)
    os.makedirs(OUT_DIR, exist_ok=True)
    name = "flora" if args.flora else "rock"
    if args.rows:
        name += "_" + args.rows.replace(",", "-")
    out = args.out or os.path.join(OUT_DIR, f"{name}.png")

    extra = [
        f"--out={os.path.abspath(out)}",
        f"--count={args.count}",
        f"--pitch={args.pitch}",
        f"--elevation={args.elevation}",
    ]
    if args.rows:
        extra.append(f"--rows={args.rows}")
    if args.flora:
        extra.append("--flora=1")

    completed = subprocess.run(
        [godot, "--path", os.path.join(PROJECT_ROOT, "godot"), SCENE, "--",
         *extra],
        cwd=PROJECT_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace")
    for line in (completed.stderr or "").splitlines():
        if "SCRIPT ERROR" in line or "Parse Error" in line:
            print(line.strip(), file=sys.stderr)
            return 1
    if completed.returncode != 0:
        print(f"Godot exited {completed.returncode}", file=sys.stderr)
        return 1
    if not os.path.isfile(out):
        print(f"no image was written to {out}", file=sys.stderr)
        return 1
    print("wrote", os.path.relpath(out, PROJECT_ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

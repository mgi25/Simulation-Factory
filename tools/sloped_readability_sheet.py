"""The same eleven moments through two edits, side by side.

    python tools/sloped_readability_sheet.py --seed 5432 --against v19

Solves both camera tracks from the one committed replay, renders each at the
same **output** seconds - so the two columns are the same instant of the same
race through two lenses - and tiles them into one contact sheet per moment,
before above after, with the measured racer scale printed on each.

This is the only part of the V21 pass that opens Godot, and it renders nothing
the film needs: the deliverable is the clip, and this is the evidence for it.
`--at` takes output seconds and `sloped_race_scene.replay_at` maps them, so a
frame here is the frame the video has at that second rather than a picture near
it.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from typing import Any, Sequence

sys.path.insert(0, os.getcwd())

from sloped import cameras as cameras_module
from sloped import readability
from sloped.course import sloped_course

OUT_DIR = os.path.join("output", "sloped_race_v1")
SHEET_DIR = os.path.join("docs", "validation", "sloped_race_v1", "v21_2_camera")
GODOT_PROJECT = os.path.join(os.getcwd(), "godot")
RENDER_SCENE = "res://scenes/SlopedRaceRender.tscn"

# The moments, in output seconds, and what each is evidence for. Every one of
# them is a fact about the edit rather than a taste: the two commitments come
# from the replay's own route events through the edit map, the convergence from
# the three marbles that pass the junction within 0.03 s of each other, and the
# crossing from the first `finish_line` event.
MOMENTS = (
    (0.60, "the grid"),
    (3.40, "the trapdoor"),
    (4.50, "the first descent"),
    (5.60, "leg 1's apex"),
    (6.70, "the hairpin"),
    (7.90, "the long straight"),
    (9.60, "the spinner corridor"),
    (11.30, "the fork, approaching"),
    (11.85, "orange commits"),
    (12.90, "the routes diverging"),
    (13.90, "both lobes"),
    (14.93, "three arrive at the junction"),
    (17.10, "the winner crosses"),
)


def solve(replay, machine, edit: str):
    plan = cameras_module.EDITS[edit] if edit else None
    return cameras_module.build_track(replay, machine, fps=60, edit=plan)


def render(godot: str, replay_path: str, track_path: str, out_dir: str,
           moments: Sequence[float], start_contract: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    extra = [
        f"--out-dir={os.path.abspath(out_dir)}",
        f"--replay={os.path.abspath(replay_path)}",
        f"--cameras={os.path.abspath(track_path)}",
        "--at=" + ",".join(f"{when:.3f}" for when in moments),
        "--width=1080",
        "--height=1920",
        "--layout=b",
        "--detail=hero",
    ]
    if os.path.isfile(start_contract):
        extra.insert(3, f"--start-contract={os.path.abspath(start_contract)}")
    done = subprocess.run(
        [godot, "--path", GODOT_PROJECT, RENDER_SCENE, "--", *extra],
        cwd=os.getcwd(), stderr=subprocess.PIPE, text=True, encoding="utf-8",
        errors="replace",
    )
    if done.returncode != 0:
        raise SystemExit(
            f"godot exited {done.returncode}\n" + "\n".join(
                (done.stderr or "").splitlines()[-20:])
        )


def scale_at(track, replay, when: float) -> tuple[int, float]:
    """How many racers are in frame at one output second, and the median size.

    The output second is mapped through the edit the way the renderer maps it,
    so the number belongs to the frame beside it.
    """
    replay_second = when
    for segment in track["edit"]:
        low, high = segment["out"]
        if when <= high:
            replay_second = segment["replay"][0] + min(
                max(when - low, 0.0), segment["replay"][1] - segment["replay"][0]
            )
            break
    for cut in track["cuts"]:
        if replay_second <= cut["to"] + 1e-9:
            row = min(cut["frames"], key=lambda entry: abs(entry[0] - replay_second))
            read = readability.cut_reads({"frames": [row]}, replay)[0]
            return read["in_frame"], readability._median(read["diameters"])
    return 0, 0.0


def tile(before_dir: str, after_dir: str, moments, sheet: str,
         labels: dict[float, tuple[str, str]], titles: tuple[str, str]) -> str:
    from PIL import Image, ImageDraw

    thumb = 300
    gap = 12
    band = 46
    columns = len(moments)
    width = columns * thumb + (columns + 1) * gap
    height = 2 * (thumb * 16 // 9) + 3 * gap + 2 * band + 34
    sheet_image = Image.new("RGB", (width, height), (18, 18, 22))
    draw = ImageDraw.Draw(sheet_image)
    tall = thumb * 16 // 9
    for index, (when, _why) in enumerate(moments):
        x = gap + index * (thumb + gap)
        for row, (directory, title) in enumerate(((before_dir, titles[0]),
                                                  (after_dir, titles[1]))):
            path = os.path.join(directory, f"at_{when:07.3f}.png")
            y = 34 + gap + row * (tall + band + gap)
            if os.path.isfile(path):
                with Image.open(path) as frame:
                    sheet_image.paste(frame.resize((thumb, tall)), (x, y))
            note = labels.get((when, title), ("", ""))[0]
            draw.text((x + 4, y + tall + 6), f"{title}  {when:5.2f}s", fill=(210, 210, 220))
            draw.text((x + 4, y + tall + 22), note, fill=(150, 200, 255))
        draw.text((x + 4, 10), _why[:44], fill=(235, 225, 190))
    os.makedirs(os.path.dirname(sheet) or ".", exist_ok=True)
    sheet_image.save(sheet)
    return sheet


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=5432)
    parser.add_argument("--edit", default="v212")
    parser.add_argument("--against", default="v19")
    parser.add_argument("--routes", default="both", choices=("blue", "both"))
    parser.add_argument("--godot", default="")
    parser.add_argument("--skip-render", action="store_true")
    args = parser.parse_args(argv)

    replay_path = os.path.join(OUT_DIR, f"race_{args.seed}.json")
    with open(replay_path, "r", encoding="utf-8") as handle:
        replay = json.load(handle)
    machine = sloped_course(routes=args.routes)

    tracks = {}
    for name in (args.against, args.edit):
        track = solve(replay, machine, name)
        path = os.path.join(OUT_DIR, f"cameras_{args.seed}_{name}.json")
        cameras_module.write_track(track, path)
        tracks[name] = (track, path)

    godot = args.godot or os.environ.get("GODOT_BIN") or os.environ.get("GODOT4_BIN") or ""
    moments = [when for when, _why in MOMENTS]
    directories = {}
    for name, (_track, path) in tracks.items():
        directory = os.path.join(OUT_DIR, "sheet", name)
        directories[name] = directory
        if not args.skip_render:
            if not godot:
                raise SystemExit("pass --godot or set $GODOT_BIN")
            render(godot, replay_path, path, directory, moments,
                   os.path.join(OUT_DIR, f"start_contract_{args.seed}.json"))
            print(f"rendered {len(moments)} frames of {name} into {directory}")

    labels: dict[tuple[float, str], tuple[str, str]] = {}
    print(f"{'out':>6s} {'moment':28s} {args.against:>16s} {args.edit:>16s}")
    for when, why in MOMENTS:
        line = f"{when:6.2f} {why:28s}"
        for name in (args.against, args.edit):
            count, size = scale_at(tracks[name][0], replay, when)
            labels[(when, name)] = (f"{count} racers, {size:.0f} px", "")
            line += f" {count} in frame {size:6.1f} px"
        print(line)

    sheet = os.path.join(SHEET_DIR, f"readability_sheet_{args.edit}.png")
    tile(directories[args.against], directories[args.edit], MOMENTS, sheet,
         labels, (args.against, args.edit))
    print(f"wrote {sheet}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""V21 beside V22, at the same moment of the race, and the same sheet on a phone.

    python tools/sloped_v22_sheet.py --stage all

**The two films do not share a clock, so "the same moment" is not the same
second.** V21 is 18.450 s with one pacing; V22 is 23.050 s with a course preview
in front of it, a longer start and a longer finish. A pair of frames grabbed at
the same output second would be comparing the obstacle with the fork.

So every pair here is named by a **replay** instant - a thing the physics did -
and each film's own clock says where that instant landed in it. Moments V21 does
not contain at all (the preview, and the two restored stretches) are shown as
V22 alone, with what V21 was showing instead beside them.

Stages:

    pairs   one PNG per moment, V21 left and V22 right, labelled
    sheet   all the moments on one contact sheet
    phone   the V22 column again at 270x480, which is the review that decides
    all     all three
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from typing import Any, Sequence

sys.path.insert(0, os.getcwd())

from PIL import Image, ImageDraw

from sloped import presentation, v22

OUT_DIR = os.path.join("output", "sloped_race_v1")
DOCS_DIR = os.path.join("docs", "validation", "sloped_race_v1", "v22_final")
SCRATCH = os.path.join(OUT_DIR, "v22", "sheet")

V21_FILM = os.path.join(OUT_DIR, "real_race_v21.mp4")
V22_FILM = os.path.join(OUT_DIR, "real_race_v22.mp4")

FPS = 60
PHONE = (270, 480)

# Each moment is a replay second, except the preview, which is not in the replay
# at all and is named by its own output second in V22.
MOMENTS: tuple[tuple[str, str, float], ...] = (
    ("opening", "output", 0.30),
    ("preview_mid", "output", 1.00),
    ("preview_arrive", "output", 1.95),
    ("pick_one", "output", None),          # filled in: the hold, in each film
    ("gates", "replay", 0.90),
    ("shuffle", "replay", 1.60),
    ("settled", "replay", 6.20),
    ("trapdoor", "replay", 7.10),
    ("first_descent", "replay", 8.60),
    ("obstacle_approach", "replay", 12.60),
    ("obstacle_interaction", "replay", 14.30),
    ("obstacle_escape", "replay", 15.00),
    ("fork", "replay", 15.90),
    ("branches", "replay", 17.60),
    ("merge", "replay", 19.40),
    ("final_chase", "replay", 20.40),
    ("winner", "replay", 20.95),
    ("last_crossing", "replay", 24.42),
)


def _ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found is None:
        raise SystemExit("ffmpeg is not on PATH")
    return found


def _clocks() -> tuple[presentation.Clock, presentation.Clock]:
    replay = os.path.join(OUT_DIR, "race_5432.json")
    _r, _t, v21 = presentation.load(
        replay, os.path.join(OUT_DIR, "cameras_5432.json"), 1150
    )
    v21, _keep = presentation.omit_frames(v21, ((49, 133),))
    preview = json.load(
        open(os.path.join(OUT_DIR, "preview_v22_5432.json"), encoding="utf-8")
    )
    _r, _t, v22_clock = presentation.load(
        replay, os.path.join(OUT_DIR, "cameras_v22_5432.json"), 1221,
        prefix=v22.preview_prefix(preview),
    )
    return v21, v22_clock


def _grab(film: str, second: float, out: str) -> bool:
    """One frame, by frame number rather than by seek, so it is exact."""
    frame = int(round(second * FPS))
    subprocess.run(
        [_ffmpeg(), "-v", "error", "-y", "-i", film,
         "-vf", f"select='eq(n\\,{frame})'", "-vsync", "0", "-frames:v", "1", out],
        capture_output=True, text=True,
    )
    return os.path.isfile(out)


def _label(image: Image.Image, text: str, sub: str = "") -> Image.Image:
    band = 74 if sub else 46
    out = Image.new("RGB", (image.width, image.height + band), (17, 17, 19))
    out.paste(image, (0, band))
    draw = ImageDraw.Draw(out)
    draw.text((14, 10), text, fill=(240, 240, 236))
    if sub:
        draw.text((14, 40), sub, fill=(150, 150, 156))
    return out


def _moments() -> list[tuple[str, str, float]]:
    filled = []
    for name, kind, value in MOMENTS:
        if name == "pick_one":
            continue
        filled.append((name, kind, value))
    return filled


def stage_pairs() -> list[str]:
    os.makedirs(SCRATCH, exist_ok=True)
    os.makedirs(DOCS_DIR, exist_ok=True)
    v21_clock, v22_clock = _clocks()
    written: list[str] = []
    for name, kind, value in _moments():
        if kind == "output":
            v22_at: float | None = value
            # What V21 was showing at the same point of its own run-in: it has
            # no preview, so this is its held opening.
            v21_at: float | None = min(value, v21_clock.hold - 0.05)
        else:
            v21_at = v21_clock.at(value)
            v22_at = v22_clock.at(value)
        panels = []
        for tag, film, when in (("V21", V21_FILM, v21_at), ("V22", V22_FILM, v22_at)):
            path = os.path.join(SCRATCH, f"{name}_{tag}.png")
            if when is None or not _grab(film, when, path):
                blank = Image.new("RGB", (1080, 1920), (26, 26, 30))
                draw = ImageDraw.Draw(blank)
                draw.text((40, 900), f"{tag}: not in this film", fill=(200, 120, 120))
                panels.append(_label(blank, f"{tag}  -", "this moment was cut"))
                continue
            sub = (f"output {when:.3f} s"
                   + ("" if kind == "output" else f"   replay {value:.3f} s"))
            panels.append(_label(Image.open(path).convert("RGB"), f"{tag}  {name}", sub))
        height = max(panel.height for panel in panels)
        pair = Image.new("RGB", (sum(p.width for p in panels) + 12, height), (17, 17, 19))
        x = 0
        for panel in panels:
            pair.paste(panel, (x, 0))
            x += panel.width + 12
        out = os.path.join(DOCS_DIR, f"pair_{name}.png")
        pair.resize((pair.width // 2, pair.height // 2), Image.LANCZOS).save(out)
        written.append(out)
        print(f"pair: {name:22s} V21 {'-' if v21_at is None else f'{v21_at:6.3f}'}"
              f"   V22 {'-' if v22_at is None else f'{v22_at:6.3f}'}")
    return written


def stage_sheet(columns: int = 6, cell: int = 250) -> str:
    """Every moment, V22 only, as one strip - the film at a glance."""
    os.makedirs(SCRATCH, exist_ok=True)
    _v21, v22_clock = _clocks()
    tiles: list[Image.Image] = []
    for name, kind, value in _moments():
        when = value if kind == "output" else v22_clock.at(value)
        path = os.path.join(SCRATCH, f"sheet_{name}.png")
        if when is None or not _grab(V22_FILM, when, path):
            continue
        image = Image.open(path).convert("RGB")
        image = image.resize((cell, int(cell * image.height / image.width)), Image.LANCZOS)
        tiles.append(_label(image, name, f"{when:.2f} s"))
    if not tiles:
        raise SystemExit("no frames could be grabbed")
    rows = (len(tiles) + columns - 1) // columns
    width = max(t.width for t in tiles)
    height = max(t.height for t in tiles)
    sheet = Image.new("RGB", (columns * (width + 8), rows * (height + 8)), (17, 17, 19))
    for index, tile in enumerate(tiles):
        sheet.paste(tile, ((index % columns) * (width + 8), (index // columns) * (height + 8)))
    out = os.path.join(DOCS_DIR, "sheet.png")
    sheet.save(out)
    print(f"sheet: {len(tiles)} moments -> {out}")
    return out


def stage_phone(columns: int = 6) -> str:
    """The same moments at 270x480, which is the size the review is done at."""
    os.makedirs(SCRATCH, exist_ok=True)
    _v21, v22_clock = _clocks()
    tiles: list[Image.Image] = []
    for name, kind, value in _moments():
        when = value if kind == "output" else v22_clock.at(value)
        path = os.path.join(SCRATCH, f"phone_{name}.png")
        if when is None or not _grab(V22_FILM, when, path):
            continue
        image = Image.open(path).convert("RGB").resize(PHONE, Image.LANCZOS)
        tiles.append(_label(image, name, f"{when:.2f} s"))
    rows = (len(tiles) + columns - 1) // columns
    width = max(t.width for t in tiles)
    height = max(t.height for t in tiles)
    sheet = Image.new("RGB", (columns * (width + 8), rows * (height + 8)), (17, 17, 19))
    for index, tile in enumerate(tiles):
        sheet.paste(tile, ((index % columns) * (width + 8), (index // columns) * (height + 8)))
    out = os.path.join(DOCS_DIR, "phone.png")
    sheet.save(out)
    print(f"phone: {len(tiles)} moments at {PHONE[0]}x{PHONE[1]} -> {out}")
    return out


def stage_timeline() -> str:
    """V21 and V22 as two bars: what each keeps, and where each skips."""
    v21_clock, v22_clock = _clocks()
    width, height = 1700, 420
    pad, bar = 70, 62
    image = Image.new("RGB", (width, height), (17, 17, 19))
    draw = ImageDraw.Draw(image)
    span = max(v21_clock.duration, v22_clock.duration)
    scale = (width - 2 * pad) / span

    palette = {
        "preview": (92, 132, 196), "hold": (78, 78, 86),
        "start": (206, 158, 74), "descent": (108, 168, 120),
        "long": (108, 168, 120), "hairpin": (108, 168, 120),
        "straight": (150, 132, 196), "obstacle": (190, 108, 108),
        "split": (196, 148, 92), "fork": (196, 148, 92),
        "branch": (120, 160, 190), "branches": (120, 160, 190),
        "merge": (150, 120, 190), "finish": (206, 206, 120),
    }

    def row(y: int, title: str, clock, names: Sequence[str], preview: bool) -> None:
        draw.text((pad, y - 26), title, fill=(240, 240, 236))
        x = pad
        if preview:
            wide = clock.prefix * scale
            draw.rectangle([x, y, x + wide, y + bar], fill=palette["preview"])
            draw.text((x + 6, y + 20), "preview", fill=(16, 16, 20))
            x += wide
        wide = clock.hold * scale
        draw.rectangle([x, y, x + wide, y + bar], fill=palette["hold"])
        x += wide
        previous_replay = None
        for index, (out_from, out_to, replay_from, replay_to) in enumerate(clock.segments):
            left = pad + (clock.origin + out_from) * scale
            right = pad + (clock.origin + out_to) * scale
            name = names[index]
            draw.rectangle([left, y, right, y + bar], fill=palette.get(name, (120, 120, 128)))
            if right - left > 46:
                draw.text((left + 5, y + 20), name[:9], fill=(16, 16, 20))
            if previous_replay is not None and replay_from - previous_replay > 1e-6:
                draw.line([left, y - 10, left, y + bar + 10], fill=(232, 92, 92), width=3)
                draw.text((left + 5, y + bar + 12),
                          f"omit {replay_from - previous_replay:.2f}s", fill=(232, 92, 92))
            previous_replay = replay_to

    v21_names = [row["cut"] for row in json.load(
        open(os.path.join(OUT_DIR, "cameras_5432.json"), encoding="utf-8"))["edit"]]
    v22_names = [row["cut"] for row in json.load(
        open(os.path.join(OUT_DIR, "cameras_v22_5432.json"), encoding="utf-8"))["edit"]]
    row(96, f"V21   {v21_clock.duration:.3f} s, {v21_clock.frames} frames, "
            f"{len(presentation.omissions(v21_clock))} omissions", v21_clock, v21_names, False)
    row(266, f"V22   {v22_clock.duration:.3f} s, {v22_clock.frames} frames, "
             f"{len(presentation.omissions(v22_clock))} omission", v22_clock, v22_names, True)
    for second in range(0, int(span) + 1, 2):
        x = pad + second * scale
        draw.line([x, height - 44, x, height - 34], fill=(110, 110, 118))
        draw.text((x - 6, height - 30), f"{second}s", fill=(150, 150, 156))
    out = os.path.join(DOCS_DIR, "timeline.png")
    image.save(out)
    print(f"timeline: -> {out}")
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stage", default="all",
                        choices=("pairs", "sheet", "phone", "timeline", "all"))
    args = parser.parse_args(argv)
    stages = (("pairs", "sheet", "phone", "timeline")
              if args.stage == "all" else (args.stage,))
    for stage in stages:
        print(f"--- {stage} ---")
        {"pairs": stage_pairs, "sheet": stage_sheet,
         "phone": stage_phone, "timeline": stage_timeline}[stage]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

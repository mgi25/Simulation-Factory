"""V22 beside V22.1, at the same moment of the race, plus a timeline of both.

    python tools/sloped_v221_sheet.py --stage all

**The two films do not share a clock, so "the same moment" is not the same
second.** V22.1 puts 1.500 s more preview in front of everything and 1.983 s
more live mixing inside the start, so by the trapdoor the two films are 3.483 s
apart. A pair of frames grabbed at the same output second would be comparing the
fork with the branches.

So every pair below is named by a **replay** instant - a thing the physics did -
and each film's own clock says where that instant landed in it. The three
moments that are not in the replay at all - the preview, and the frame the
omission joins to - are named by an output second in each film instead, because
"the frame after the cut" is an editing fact rather than a physical one.

Stages:

    pairs     one PNG per moment, V22 left and V22.1 right, labelled
    sheet     the V22.1 column on one contact sheet - the film at a glance
    phone     the same column at 270x480, which is the review that decides
    timeline  the two edits drawn against each other, preview to finish
    all       all four
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

from sloped import presentation, v22, v221

OUT_DIR = os.path.join("output", "sloped_race_v1")
DOCS_DIR = os.path.join("docs", "validation", "sloped_race_v1", "v221_final")
SCRATCH = os.path.join(OUT_DIR, "v221", "sheet")

V22_FILM = os.path.join(OUT_DIR, "real_race_v22.mp4")
V221_FILM = os.path.join(OUT_DIR, "real_race_v221.mp4")

FPS = 60
PHONE = (270, 480)

# The eleven the brief asks for, plus the two that show what the start now holds.
#
# `omit_before` and `omit_after` are the two frames either side of each film's
# own omission - the whole question of part B, and the one comparison that has
# to be taken on the output clock, because a replay second on the far side of a
# cut is not the second on the near side of it.
MOMENTS: tuple[tuple[str, str, Any], ...] = (
    ("map_preview", "output", 0.60),
    ("preview_mid", "output", 1.60),
    ("preview_arrive", "output", "arrive"),
    ("pick_one", "output", "hold"),
    ("first_shuffle", "replay", 1.60),
    ("omit_before", "output", "omit_before"),
    ("omit_after", "output", "omit_after"),
    ("spin_down", "replay", 4.75),
    ("blade_lift", "replay", 5.55),
    ("stillness", "replay", 6.00),
    ("trapdoor", "replay", 6.20),
    ("first_chase", "replay", 8.60),
    ("obstacle", "replay", 14.30),
    ("fork", "replay", 15.90),
    ("merge", "replay", 19.40),
    ("final_approach", "replay", 20.40),
    ("winner", "replay", 20.95),
    ("remaining", "replay", 23.50),
    ("last_crossing", "replay", 24.42),
)


def _ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found is None:
        raise SystemExit("ffmpeg is not on PATH")
    return found


def _clock(edition: str) -> presentation.Clock:
    """Each film's own map, built the way `sloped_short` builds it."""
    replay = os.path.join(OUT_DIR, "race_5432.json")
    tag = "v22" if edition == "v22" else "v221"
    track = os.path.join(OUT_DIR, f"cameras_{tag}_5432.json")
    preview = json.load(
        open(os.path.join(OUT_DIR, f"preview_{tag}_5432.json"), encoding="utf-8")
    )
    with open(track, encoding="utf-8") as handle:
        duration = float(json.load(handle)["duration"])
    frames = int(round(duration * FPS)) + 1
    _r, _t, clock = presentation.load(
        replay, track, frames, prefix=v22.preview_prefix(preview)
    )
    return clock


def _omission(clock: presentation.Clock) -> float | None:
    found = presentation.omissions(clock)
    return found[0][0] if found else None


def _resolve(clock: presentation.Clock, kind: str, value: Any) -> float | None:
    """This film's output second for one moment, or None if it has none."""
    if kind == "replay":
        return clock.at(float(value))
    if value == "hold":
        return clock.prefix + 0.35
    if value == "arrive":
        # The last frame of the preview: the handoff, whatever it costs.
        return clock.prefix - 1.0 / FPS
    if value in ("omit_before", "omit_after"):
        at = _omission(clock)
        if at is None:
            return None
        return at - 1.0 / FPS if value == "omit_before" else at
    return float(value)


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


def stage_pairs() -> list[str]:
    os.makedirs(SCRATCH, exist_ok=True)
    os.makedirs(DOCS_DIR, exist_ok=True)
    clocks = {"V22": _clock("v22"), "V22.1": _clock("v221")}
    films = {"V22": V22_FILM, "V22.1": V221_FILM}
    written: list[str] = []
    for name, kind, value in MOMENTS:
        panels = []
        at: dict[str, float | None] = {}
        for tag in ("V22", "V22.1"):
            when = _resolve(clocks[tag], kind, value)
            at[tag] = when
            path = os.path.join(SCRATCH, f"{name}_{tag}.png")
            if when is None or not _grab(films[tag], when, path):
                blank = Image.new("RGB", (1080, 1920), (26, 26, 30))
                draw = ImageDraw.Draw(blank)
                draw.text((40, 900), f"{tag}: not in this film", fill=(200, 120, 120))
                panels.append(_label(blank, f"{tag}  -", "this moment was cut"))
                continue
            sub = f"output {when:.3f} s"
            if kind == "replay":
                sub += f"   replay {float(value):.3f} s"
            panels.append(_label(Image.open(path).convert("RGB"),
                                 f"{tag}  {name}", sub))
        height = max(panel.height for panel in panels)
        pair = Image.new("RGB", (sum(p.width for p in panels) + 12, height),
                         (17, 17, 19))
        x = 0
        for panel in panels:
            pair.paste(panel, (x, 0))
            x += panel.width + 12
        out = os.path.join(DOCS_DIR, f"pair_{name}.png")
        pair.resize((pair.width // 2, pair.height // 2), Image.LANCZOS).save(out)
        written.append(out)
        def show(tag: str) -> str:
            when = at[tag]
            return "-" if when is None else f"{when:6.3f}"

        print(f"pair: {name:18s} V22 {show('V22')}   V22.1 {show('V22.1')}")
    return written


def stage_sheet(columns: int = 5, cell: int = 250) -> str:
    """Every moment, V22.1 only, as one grid - the film at a glance."""
    os.makedirs(SCRATCH, exist_ok=True)
    os.makedirs(DOCS_DIR, exist_ok=True)
    clock = _clock("v221")
    tiles: list[Image.Image] = []
    for name, kind, value in MOMENTS:
        when = _resolve(clock, kind, value)
        path = os.path.join(SCRATCH, f"sheet_{name}.png")
        if when is None or not _grab(V221_FILM, when, path):
            continue
        tile = Image.open(path).convert("RGB")
        tile = tile.resize((cell, int(cell * tile.height / tile.width)), Image.LANCZOS)
        tiles.append(_label(tile, name, f"{when:.2f} s"))
    rows = (len(tiles) + columns - 1) // columns
    width = max(tile.width for tile in tiles)
    height = max(tile.height for tile in tiles)
    sheet = Image.new("RGB", (columns * width, rows * height), (17, 17, 19))
    for index, tile in enumerate(tiles):
        sheet.paste(tile, ((index % columns) * width, (index // columns) * height))
    out = os.path.join(DOCS_DIR, "sheet.png")
    sheet.save(out)
    print(f"sheet: {len(tiles)} moments -> {out}")
    return out


def stage_phone() -> str:
    """The same moments at the size the film is actually watched at."""
    os.makedirs(SCRATCH, exist_ok=True)
    os.makedirs(DOCS_DIR, exist_ok=True)
    clock = _clock("v221")
    tiles: list[Image.Image] = []
    for name, kind, value in MOMENTS:
        when = _resolve(clock, kind, value)
        path = os.path.join(SCRATCH, f"phone_{name}.png")
        if when is None or not _grab(V221_FILM, when, path):
            continue
        tiles.append(Image.open(path).convert("RGB").resize(PHONE, Image.LANCZOS))
    columns = 5
    rows = (len(tiles) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * PHONE[0], rows * PHONE[1]), (17, 17, 19))
    for index, tile in enumerate(tiles):
        sheet.paste(tile, ((index % columns) * PHONE[0],
                           (index // columns) * PHONE[1]))
    out = os.path.join(DOCS_DIR, "phone_sheet.png")
    sheet.save(out)
    print(f"phone: {len(tiles)} moments at {PHONE[0]}x{PHONE[1]} -> {out}")
    return out


# The bands each film is drawn as. **Read off the clocks rather than typed**, so
# a change to either edit redraws this rather than making it a lie.
BANDS = (
    ("preview", (86, 132, 214)),
    ("PICK ONE hold", (150, 120, 205)),
    ("live mixer", (214, 158, 74)),
    ("omitted", (96, 96, 104)),
    ("anticipation", (206, 112, 94)),
    ("release", (196, 86, 96)),
    ("race", (96, 176, 128)),
    ("finish", (222, 196, 96)),
)


def _spans(edition: str) -> list[tuple[str, float, float]]:
    """One film's bands, in output seconds, from its own clock and plan."""
    clock = _clock(edition)
    plan = v221.START if edition == "v221" else None
    out: list[tuple[str, float, float]] = [
        ("preview", 0.0, clock.prefix),
        ("PICK ONE hold", clock.prefix, clock.origin),
    ]
    segments = clock.segments
    # The two start windows are the first two segments of either edit.
    first, second = segments[0], segments[1]
    omission = clock.origin + second[0]
    out.append(("live mixer", clock.origin + first[0], clock.origin + first[1]))
    out.append(("omitted", omission, omission))          # a zero-width mark
    # Anticipation is the machine winding down: replay 4.600 to the trapdoor.
    spin = clock.at(4.6)
    gate = clock.at(6.1)
    resume = clock.origin + second[0]
    if spin is None:
        spin = resume
    out.append(("live mixer", resume, spin))
    out.append(("anticipation", spin, gate if gate is not None else resume))
    # **The trapdoor to the handoff.** Without its own band this stretch is a
    # hole in the drawing, and it is not a hole in the film: it is the floor
    # opening and the field dropping out of the chamber, 2.067 s of it in V22
    # and 0.600 s in V22.1 - which is the empty-chamber trim, drawn.
    launch = clock.origin + second[1]
    out.append(("release", gate if gate is not None else resume, launch))
    body_end = clock.at(v221.FINISH.split if edition == "v221" else 20.2)
    out.append(("race", launch, body_end if body_end else launch))
    out.append(("finish", body_end if body_end else launch, clock.duration))
    return [(name, low, high) for name, low, high in out if high >= low]


def stage_timeline() -> str:
    os.makedirs(DOCS_DIR, exist_ok=True)
    width, row, pad, gap = 1500, 78, 130, 54
    longest = max(_clock("v22").duration, _clock("v221").duration)
    scale = (width - pad - 30) / longest
    height = pad + 2 * (row + gap) + 90
    image = Image.new("RGB", (width, height), (18, 18, 21))
    draw = ImageDraw.Draw(image)
    draw.text((pad, 24), "V22 and V22.1, the same race as two edits",
              fill=(238, 238, 234))
    draw.text((pad, 46),
              "output seconds; every band read off the film's own clock",
              fill=(140, 140, 148))
    colours = dict(BANDS)
    for index, (tag, edition) in enumerate((("V22", "v22"), ("V22.1", "v221"))):
        top = pad + index * (row + gap)
        clock = _clock(edition)
        draw.text((22, top + row // 2 - 6), tag, fill=(232, 232, 228))
        draw.text((22, top + row // 2 + 10), f"{clock.duration:.2f} s",
                  fill=(140, 140, 148))
        for name, low, high in _spans(edition):
            x0, x1 = pad + low * scale, pad + high * scale
            if name == "omitted":
                draw.line([(x0, top - 8), (x0, top + row + 8)],
                          fill=colours[name], width=3)
                continue
            draw.rectangle([x0, top, max(x1, x0 + 2), top + row],
                           fill=colours[name])
        for second in range(0, int(longest) + 1, 2):
            x = pad + second * scale
            draw.line([(x, top + row + 4), (x, top + row + 10)], fill=(70, 70, 78))
            if index == 1:
                draw.text((x - 6, top + row + 14), str(second), fill=(120, 120, 128))
    legend = height - 34
    x = pad
    for name, colour in BANDS:
        draw.rectangle([x, legend, x + 18, legend + 14], fill=colour)
        draw.text((x + 24, legend), name, fill=(190, 190, 196))
        x += 34 + 8 * len(name)
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

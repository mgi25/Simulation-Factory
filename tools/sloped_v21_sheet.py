"""V20 beside V21, at the same moments of the same race, from the two films.

    python tools/sloped_v21_sheet.py --out docs/validation/sloped_race_v1/v21_final

Not renders and not stills: the delivered mp4s, which is the only comparison
that carries the overlays, the encode and the retention cut all at once.

**The two clocks are different and the moments are the same race.** V21 omits
85 master frames in the middle of the start, so everything after output 1.517 s
lands 1.41667 s earlier than it does in V20. Each moment is therefore written
once, as a V21 output second, and its V20 partner is derived - `+ SHIFT` after
the cut, the same second before it. Writing both by hand is how a sheet ends up
comparing two different instants of the race and calling it a grade change.

Three things come out:

    pair_<name>.png   one moment, V20 | V21, at half the frame's own height
    sheet.png         all of them in a grid
    phone.png         the same grid at 270x480 a frame, which is roughly what a
                      1080-wide Short occupies on a handset
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from typing import Sequence

sys.path.insert(0, os.getcwd())

from PIL import Image, ImageDraw

from sloped import overlays

OUT_DIR = os.path.join("output", "sloped_race_v1")
V20 = os.path.join(OUT_DIR, "real_race_v20.mp4")
V21 = os.path.join(OUT_DIR, "real_race_v21.mp4")

# The retention cut: V21 output 1.517 onwards is V20's footage 1.41667 s later.
CUT_AT = 1.517
SHIFT = 85.0 / 60.0

# Written as V21 output seconds, which is the film being judged.
MOMENTS: list[tuple[float, str]] = [
    (0.40, "opening"),
    (1.05, "gates"),
    (1.90, "release"),
    (3.45, "first_descent"),
    (4.60, "long_track"),
    (5.90, "hairpin"),
    (7.00, "straight"),
    (8.90, "obstacle"),
    (11.30, "split"),
    (13.10, "branch"),
    (14.40, "merge"),
    (15.40, "final_sprint"),
    (16.00, "winner"),
    (18.20, "end_card"),
]

PAIR_HEIGHT = 720
PHONE = (270, 480)
GUTTER = 8
LABEL = 30
BACKGROUND = (17, 19, 24)
TEXT = (226, 232, 240)
COLUMNS = 5


def partner(seconds: float) -> float:
    """The V20 output second showing the same instant of the race."""
    return seconds + SHIFT if seconds >= CUT_AT else seconds


def _ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found is None:
        raise RuntimeError("ffmpeg is not on PATH")
    return found


def grab(video: str, seconds: float, path: str) -> str:
    """One frame, decoded from the start so the seek lands on the right one."""
    done = subprocess.run(
        [_ffmpeg(), "-y", "-v", "error", "-i", video,
         "-vf", f"select=eq(n\\,{int(round(seconds * 60))})",
         "-vsync", "0", "-frames:v", "1", path],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if done.returncode != 0 or not os.path.isfile(path):
        raise RuntimeError(f"ffmpeg could not read {video} at {seconds:.3f}s")
    return path


def _scaled(image: Image.Image, height: int) -> Image.Image:
    width = int(round(image.width * height / image.height))
    return image.resize((width, height), Image.LANCZOS)


def _caption(draw: ImageDraw.ImageDraw, xy, text: str, size: int = 22) -> None:
    draw.text(xy, text, font=overlays.load_font(size), fill=TEXT)


def build(out: str, v20: str = V20, v21: str = V21) -> list[str]:
    os.makedirs(out, exist_ok=True)
    scratch = os.path.join(OUT_DIR, "v21_sheet")
    os.makedirs(scratch, exist_ok=True)

    written: list[str] = []
    pairs: list[tuple[str, Image.Image, Image.Image]] = []
    for seconds, name in MOMENTS:
        old = Image.open(grab(v20, partner(seconds), os.path.join(scratch, f"v20_{name}.png")))
        new = Image.open(grab(v21, seconds, os.path.join(scratch, f"v21_{name}.png")))
        pairs.append((name, old.convert("RGB"), new.convert("RGB")))

        left, right = _scaled(old, PAIR_HEIGHT), _scaled(new, PAIR_HEIGHT)
        sheet = Image.new("RGB", (left.width + GUTTER + right.width, PAIR_HEIGHT + LABEL),
                          BACKGROUND)
        sheet.paste(left, (0, LABEL))
        sheet.paste(right, (left.width + GUTTER, LABEL))
        draw = ImageDraw.Draw(sheet)
        _caption(draw, (6, 6), f"V20  {name}  {partner(seconds):.2f}s")
        _caption(draw, (left.width + GUTTER + 6, 6), f"V21  {name}  {seconds:.2f}s")
        path = os.path.join(out, f"pair_{name}.png")
        sheet.save(path)
        written.append(path)

    for label, height in (("sheet", 420), ("phone", PHONE[1])):
        cells = []
        for name, old, new in pairs:
            if label == "phone":
                left = old.resize(PHONE, Image.LANCZOS)
                right = new.resize(PHONE, Image.LANCZOS)
            else:
                left, right = _scaled(old, height), _scaled(new, height)
            cell = Image.new("RGB", (left.width + 4 + right.width, height + LABEL),
                             BACKGROUND)
            cell.paste(left, (0, LABEL))
            cell.paste(right, (left.width + 4, LABEL))
            _caption(ImageDraw.Draw(cell), (4, 6), f"V20 | V21   {name}", 20)
            cells.append(cell)
        columns = min(COLUMNS, len(cells))
        rows = (len(cells) + columns - 1) // columns
        width = cells[0].width
        grid = Image.new("RGB",
                         (columns * width + (columns + 1) * GUTTER,
                          rows * cells[0].height + (rows + 1) * GUTTER),
                         BACKGROUND)
        for index, cell in enumerate(cells):
            column, row = index % columns, index // columns
            grid.paste(cell, (GUTTER + column * (width + GUTTER),
                              GUTTER + row * (cell.height + GUTTER)))
        path = os.path.join(out, f"{label}.png")
        grid.save(path)
        written.append(path)

    for path in written:
        print(f"  {path}  {os.path.getsize(path) // 1024} KiB")
    return written


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=os.path.join(
        "docs", "validation", "sloped_race_v1", "v21_final"))
    parser.add_argument("--v20", default=V20)
    parser.add_argument("--v21", default=V21)
    args = parser.parse_args(argv)
    build(args.out, args.v20, args.v21)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

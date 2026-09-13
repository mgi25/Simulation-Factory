"""Before-and-after proofs for the V21 readability pass.

    python tools/sloped_contrast_sheet.py \
        --before output/sloped_race_v1/v21/before \
        --after  output/sloped_race_v1/v21/after \
        --out    docs/validation/sloped_race_v1/v21

Both input directories hold the **same eleven output seconds**, rendered from
one replay, one camera track and one build of one scene - the only difference
between them is `--contrast=`. That is the whole point: a comparison whose two
halves came from different camera solves or different seeds would prove
nothing about a material change.

It writes three kinds of artefact, because three different questions get asked
of a readability pass and no single picture answers all of them:

    pair_NAME.png      one moment, V20 left and V21 right, at half resolution.
                       The question "what actually changed here".
    contrast_sheet.png every moment, both versions, small. The question "did
                       anything get worse somewhere I was not looking".
    phone.png          the V21 frames at the size a Short is watched at. The
                       question the whole pass exists to answer, and the one
                       a 1080x1920 still cannot be trusted on - a marble that
                       reads at full resolution can be four pixels of mud at
                       the size the video is actually played.

Pillow rather than pygame: this only ever composites and labels, and Pillow is
already a declared dependency of the Short's encoder.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Sequence

sys.path.insert(0, os.getcwd())

from PIL import Image, ImageDraw

# The eleven output seconds, and what each one is a picture of. Taken at the
# midpoint of each cut of the shipped camera track, so every frame here is a
# frame of the film rather than a picture near one.
MOMENTS: list[tuple[float, str]] = [
    (1.058, "start_gate"),
    (3.083, "start_release"),
    (4.550, "first_descent"),
    (5.642, "long_track"),
    (6.742, "hairpin"),
    (7.858, "straight"),
    (9.725, "obstacle"),
    (12.150, "split"),
    (14.017, "branch"),
    (15.283, "merge"),
    (17.558, "finish"),
]

PAIR_WIDTH = 540  # per half, so a pair is 1080 across
GUTTER = 8
LABEL = 30
BACKGROUND = (17, 19, 24)
TEXT = (226, 232, 240)
DIM = (128, 138, 152)

SHEET_WIDTH = 176
PHONE_WIDTH = 264  # about what a 1080-wide Short occupies on a phone


def frame_path(directory: str, seconds: float) -> str:
    return os.path.join(directory, "at_%07.3f.png" % seconds)


def _load(directory: str, seconds: float) -> Image.Image:
    path = frame_path(directory, seconds)
    if not os.path.isfile(path):
        raise SystemExit(f"missing frame: {path}")
    return Image.open(path).convert("RGB")


def _scaled(image: Image.Image, width: int) -> Image.Image:
    height = round(image.height * width / image.width)
    return image.resize((width, height), Image.LANCZOS)


def _caption(draw: ImageDraw.ImageDraw, xy, text: str, colour=TEXT) -> None:
    draw.text(xy, text, fill=colour)


def build_pairs(before: str, after: str, out: str) -> list[str]:
    written = []
    for seconds, name in MOMENTS:
        left = _scaled(_load(before, seconds), PAIR_WIDTH)
        right = _scaled(_load(after, seconds), PAIR_WIDTH)
        width = PAIR_WIDTH * 2 + GUTTER
        sheet = Image.new("RGB", (width, left.height + LABEL), BACKGROUND)
        sheet.paste(left, (0, LABEL))
        sheet.paste(right, (PAIR_WIDTH + GUTTER, LABEL))
        draw = ImageDraw.Draw(sheet)
        _caption(draw, (6, 8), f"V20   {name}  out {seconds:.3f}s")
        _caption(draw, (PAIR_WIDTH + GUTTER + 6, 8),
                 f"V21   {name}  out {seconds:.3f}s")
        path = os.path.join(out, f"pair_{name}.png")
        sheet.save(path)
        written.append(path)
    return written


def build_sheet(before: str, after: str, out: str) -> str:
    cells = []
    for seconds, name in MOMENTS:
        cells.append((name, _scaled(_load(before, seconds), SHEET_WIDTH),
                      _scaled(_load(after, seconds), SHEET_WIDTH)))
    cell_h = cells[0][1].height
    columns = 6
    rows = (len(cells) + columns - 1) // columns
    pair_w = SHEET_WIDTH * 2 + GUTTER
    width = columns * pair_w + (columns + 1) * GUTTER
    height = rows * (cell_h + LABEL + GUTTER) + GUTTER + LABEL
    sheet = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    _caption(draw, (GUTTER, 8),
             "sloped race V21 readability pass - V20 left, V21 right, "
             "same output second, same build")
    for index, (name, left, right) in enumerate(cells):
        column = index % columns
        row = index // columns
        x = GUTTER + column * (pair_w + GUTTER)
        y = LABEL + GUTTER + row * (cell_h + LABEL + GUTTER)
        sheet.paste(left, (x, y))
        sheet.paste(right, (x + SHEET_WIDTH + GUTTER, y))
        _caption(draw, (x, y + cell_h + 6), name, DIM)
    path = os.path.join(out, "contrast_sheet.png")
    sheet.save(path)
    return path


def build_phone(before: str, after: str, out: str) -> str:
    """The whole point of the pass, at the size it has to survive."""
    cells = []
    for seconds, name in MOMENTS:
        cells.append((name, _scaled(_load(before, seconds), PHONE_WIDTH),
                      _scaled(_load(after, seconds), PHONE_WIDTH)))
    cell_h = cells[0][1].height
    columns = 4
    rows = (len(cells) + columns - 1) // columns
    pair_w = PHONE_WIDTH * 2 + GUTTER
    width = columns * pair_w + (columns + 1) * GUTTER
    height = rows * (cell_h + LABEL + GUTTER) + GUTTER + LABEL
    sheet = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    _caption(draw, (GUTTER, 8),
             "phone size - V20 left, V21 right. A marble has to keep an edge "
             "and a hue at this scale or the pass has not worked.")
    for index, (name, left, right) in enumerate(cells):
        column = index % columns
        row = index // columns
        x = GUTTER + column * (pair_w + GUTTER)
        y = LABEL + GUTTER + row * (cell_h + LABEL + GUTTER)
        sheet.paste(left, (x, y))
        sheet.paste(right, (x + PHONE_WIDTH + GUTTER, y))
        _caption(draw, (x, y + cell_h + 6), name, DIM)
    path = os.path.join(out, "phone.png")
    sheet.save(path)
    return path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True,
                        help="directory of --contrast= (V20) frames")
    parser.add_argument("--after", required=True,
                        help="directory of V21 frames")
    parser.add_argument("--out", required=True)
    parser.add_argument("--pairs", action="store_true",
                        help="also write one side-by-side per moment")
    args = parser.parse_args(argv)

    os.makedirs(args.out, exist_ok=True)
    written = [build_sheet(args.before, args.after, args.out),
               build_phone(args.before, args.after, args.out)]
    if args.pairs:
        written.extend(build_pairs(args.before, args.after, args.out))
    for path in written:
        print(f"  {path}  {os.path.getsize(path) / 1024:.0f} KiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

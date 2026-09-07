"""One picture of every validation still, for a person to look at.

    python tools/sloped_sheet.py --in docs/validation/sloped_race_v1 \
        --out docs/validation/sloped_race_v1/contact_sheet.png

Section 43 asks for a contact sheet beside the seven section stills, and it
earns its place for a reason the individual frames do not: camera clearance is
the one thing section 37 cannot check arithmetically - no arithmetic here knows
where the mountain is - so it has to be looked at, and looking at eight
1080x1920 frames one at a time is how an occlusion in the seventh gets missed.

Built with pygame rather than Pillow because that is what is in this
repository's environment, and it is the same dependency `production.contact_sheet`
already uses for the duel batches.

Deliberately plain: a label under each cell, the time the frame was taken from,
and nothing else. It is a review artefact, and a contact sheet that needs
explaining is not one.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Sequence

sys.path.insert(0, os.getcwd())

CELL_WIDTH = 300
LABEL_HEIGHT = 34
PADDING = 10
COLUMNS = 4
BACKGROUND = (17, 19, 24)
LABEL = (226, 232, 240)
DIM = (120, 132, 148)

# The order the sheet reads in: down the course, which is also the order the
# clip cuts in. Alphabetical would put the finish third.
ORDER = (
    "start",
    "first_descent",
    "first_turn",
    "long_track",
    "obstacle",
    "split",
    "final_sprint",
    "merge",
    "finish",
)


def build(directory: str, out: str, cameras: str = "") -> str:
    import pygame
    import pygame.font

    pygame.init()
    pygame.font.init()

    times: dict[str, float] = {}
    if cameras and os.path.isfile(cameras):
        with open(cameras, "r", encoding="utf-8") as handle:
            track = json.load(handle)
        # The still mapping lives in `tools/sloped_integrate.py`; this only
        # needs the cut midpoints, which is what a still was taken at.
        from tools.sloped_integrate import STILL_NAMES

        for cut in track["cuts"]:
            name = STILL_NAMES.get(cut["name"])
            if name:
                times[name] = 0.5 * (float(cut["from"]) + float(cut["to"]))

    names = [name for name in ORDER if os.path.isfile(os.path.join(directory, f"{name}.png"))]
    extra = sorted(
        os.path.splitext(entry)[0]
        for entry in os.listdir(directory)
        if entry.endswith(".png")
        and os.path.splitext(entry)[0] not in ORDER
        # Any sheet, not just one called exactly `contact_sheet`. The
        # versioned ones - `contact_sheet_v11` and up - live in the same
        # directory, and a sheet that tiles the previous sheet is a sheet with
        # a thumbnail of itself in the corner. Measured, because that is what
        # v12 came out as on its first build.
        and not os.path.splitext(entry)[0].startswith("contact_sheet")
    )
    names.extend(extra)
    if not names:
        raise SystemExit(f"no stills in {directory}")

    first = pygame.image.load(os.path.join(directory, f"{names[0]}.png"))
    aspect = first.get_height() / first.get_width()
    cell_height = int(round(CELL_WIDTH * aspect))
    columns = min(COLUMNS, len(names))
    rows = (len(names) + columns - 1) // columns

    width = PADDING + columns * (CELL_WIDTH + PADDING)
    height = PADDING + rows * (cell_height + LABEL_HEIGHT + PADDING)
    sheet = pygame.Surface((width, height))
    sheet.fill(BACKGROUND)
    font = pygame.font.SysFont("consolas,couriernew,monospace", 17)
    small = pygame.font.SysFont("consolas,couriernew,monospace", 14)

    for index, name in enumerate(names):
        column = index % columns
        row = index // columns
        x = PADDING + column * (CELL_WIDTH + PADDING)
        y = PADDING + row * (cell_height + LABEL_HEIGHT + PADDING)
        image = pygame.image.load(os.path.join(directory, f"{name}.png"))
        sheet.blit(pygame.transform.smoothscale(image, (CELL_WIDTH, cell_height)), (x, y))
        sheet.blit(font.render(name, True, LABEL), (x + 2, y + cell_height + 4))
        if name in times:
            stamp = f"{times[name]:.2f} s"
            sheet.blit(small.render(stamp, True, DIM), (x + 2, y + cell_height + 20))

    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    pygame.image.save(sheet, out)
    pygame.quit()
    print(f"contact sheet: {len(names)} stills, {width}x{height} -> {out}")
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--in", dest="directory", default=os.path.join("docs", "validation", "sloped_race_v1"))
    parser.add_argument("--out", default="")
    parser.add_argument("--cameras", default="")
    args = parser.parse_args(argv)
    out = args.out or os.path.join(args.directory, "contact_sheet.png")
    build(args.directory, out, args.cameras)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

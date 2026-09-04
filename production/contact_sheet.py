"""One picture of a whole batch, for a person to look at.

A review artefact and nothing more: it is not committed, nothing downstream
reads it, and no automated check depends on it. Its only job is to answer
"what is in this batch" in one glance, so that deciding which Shorts to open
does not mean opening all of them.

Deliberately plain. A label under each cell saying which item it is, the
seed it came from and who fought - and a marker on anything that failed
automated QC, because a contact sheet of a batch with a failure in it should
show the failure. No styling beyond what makes the text readable.
"""

from __future__ import annotations

import math
import os

# Portrait cells, so the grid is kept wide enough to look at on a landscape
# screen rather than becoming one tall column.
MAX_COLUMNS = 5
THUMB_WIDTH = 180
PADDING = 10
LABEL_HEIGHT = 34
FONT_SIZE = 17

BACKGROUND = (18, 18, 22)
LABEL_COLOUR = (222, 222, 228)
FAIL_COLOUR = (232, 96, 96)
CELL_BACKGROUND = (34, 34, 40)


class ContactSheetError(RuntimeError):
    """The contact sheet could not be drawn."""


def grid_shape(count: int, max_columns: int = MAX_COLUMNS) -> tuple[int, int]:
    """Columns and rows for `count` portrait cells.

    Capped at five columns: the cells are 9:16, so a grid that grows sideways
    stays viewable while one that grows downwards does not.
    """
    if count <= 0:
        raise ContactSheetError(f"nothing to draw: {count} items")
    columns = min(max_columns, count)
    return columns, math.ceil(count / columns)


def cell_label(index: int, seed: int, label: str, status: str) -> str:
    """The one line under a cell."""
    text = f"{index:03d}  seed {seed}  {label}"
    return text if status == "pass" else f"{text}  [{status.upper()}]"


def build_sheet(
    cells: list[tuple[int, int, str, str, str]],
    path: str,
    *,
    thumb_width: int = THUMB_WIDTH,
) -> str:
    """Draw the sheet. Each cell is (index, seed, label, status, frame path).

    Missing or unreadable frames become empty cells with their label intact,
    because a sheet that refuses to draw at all is less useful than one that
    shows which item could not be sampled.
    """
    import pygame
    import pygame.font

    if not cells:
        raise ContactSheetError("no cells to draw")

    pygame.font.init()
    font = pygame.font.Font(None, FONT_SIZE)

    columns, rows = grid_shape(len(cells))
    thumb_height = int(round(thumb_width * 16 / 9))
    cell_width = thumb_width
    cell_height = thumb_height + LABEL_HEIGHT
    width = columns * cell_width + (columns + 1) * PADDING
    height = rows * cell_height + (rows + 1) * PADDING

    sheet = pygame.Surface((width, height))
    sheet.fill(BACKGROUND)

    for position, (index, seed, label, status, frame_path) in enumerate(cells):
        column, row = position % columns, position // columns
        left = PADDING + column * (cell_width + PADDING)
        top = PADDING + row * (cell_height + PADDING)

        sheet.fill(CELL_BACKGROUND, (left, top, cell_width, thumb_height))
        if frame_path and os.path.isfile(frame_path):
            try:
                frame = pygame.image.load(frame_path)
                sheet.blit(
                    pygame.transform.smoothscale(frame, (thumb_width, thumb_height)),
                    (left, top),
                )
            except Exception:  # pragma: no cover - a frame that will not decode
                pass

        colour = LABEL_COLOUR if status == "pass" else FAIL_COLOUR
        text = font.render(cell_label(index, seed, label, status), True, colour)
        if text.get_width() > cell_width:
            text = pygame.transform.smoothscale(
                text, (cell_width, text.get_height())
            )
        baseline = (LABEL_HEIGHT - text.get_height()) // 2
        sheet.blit(text, (left, top + thumb_height + baseline))

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    pygame.image.save(sheet, path)
    return path

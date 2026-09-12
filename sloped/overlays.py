"""The very few marks that go on top of the master, and where they may go.

The brief for the Short is explicit that the machine and the marbles are the
stars: no HUD, no leaderboard, no progress bar, no caption running under the
race. So this draws three things and nothing else -

* **PICK ONE**, over the held opening frame, gone before the gates move;
* a **ring on the winner**, after it has crossed, for two thirds of a second;
* **FROM 6TH -> 1ST**, at the very end.

and every one of them is placed against measured screen positions rather than
by eye. `presentation.screen_track` says where a marble is on the delivered
1080x1920 frame, so "do not cover the close finish" is a arithmetic question
with an answer, not a hope.

## What is deliberately absent

**Labels on the two routes.** The brief allows small BLUE and ORANGE marks at
the branch entrances if the footage needs them. It does not: the fork's own
structure is colour-coded in the geometry - a blue gantry on one arm and an
amber one on the other - and the split cut reads without help. Measured, the
two branch entries also swim a long way across the frame during the shot
(blue's from (214, 905) to (592, 1303), orange's from (728, 991) to (532, 785),
crossing over each other on the way, with the blue lead-in leaving the frame
entirely at one point), so a label pinned to either would wander through the
picture and sometimes off it. The split is marked in the *sound* instead, with
one cue per route, identical and symmetric, so neither is flagged as the
winner.

## The style

Arial Rounded MT Bold, which is on the machine's own side of the line between
geometric and friendly, at a weight that survives a phone. Everything is warm
white on a soft shadow rather than on a panel: a filled box would be an
interface, and a shadow is just legibility.
"""

from __future__ import annotations

import math
import os
from typing import Sequence

from PIL import Image, ImageDraw, ImageFilter, ImageFont

__all__ = [
    "FONT_CANDIDATES",
    "WIDTH",
    "HEIGHT",
    "end_fact",
    "load_font",
    "pick_one",
    "winner_ring",
]

WIDTH = 1080
HEIGHT = 1920

# Rounded first, then the nearest clean geometric weights. Arial Rounded MT
# Bold ships with Office and is on this machine; the rest are the fallbacks that
# keep this working somewhere it is not.
FONT_CANDIDATES = (
    r"C:\Windows\Fonts\ARLRDBD.TTF",
    r"C:\Windows\Fonts\seguibl.ttf",
    r"C:\Windows\Fonts\segoeuib.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)

WARM_WHITE = (255, 249, 238)
GOLD = (255, 205, 116)
# The machine's own dark, for text that has to sit on a lit surface.
GRAPHITE = (38, 32, 28)

# The safe band for the opening text: the eight racers sit at y 831 to 887 on
# the first frame and the START sign is just above them, so anything under 560
# is over the machine. Measured, not guessed.
PICK_ONE_BASELINE = 395

# The last second's clear band, measured over the exact window the fact is on
# screen (19.217 to 19.867) rather than at four sampled instants.
#
# The sixth racer is still coming down the channel through all of it and reaches
# y 1151 by the final frame; the finished marbles parked on the deck start at
# y 1586. So the clear band is **1152 to 1586**, and this baseline centres a
# 149 px line inside it with about 140 px of air above and below. An earlier
# value of 1255 was set from four samples that all predated the sixth racer's
# arrival, and grazed it by 1.4 px on the last frame.
END_FACT_BASELINE = 1395


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if os.path.isfile(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _shadowed(
    text: str,
    size: int,
    baseline: int,
    *,
    colour: Sequence[int] = WARM_WHITE,
    tracking: float = 0.06,
    shadow: int = 16,
) -> Image.Image:
    """One centred line, letter-spaced, over a soft drop shadow.

    Letter-spacing is applied by drawing glyph by glyph: a rounded face set
    tight reads as a lump at this size on a phone, and the extra air is most of
    what makes two words legible in half a second.
    """
    font = load_font(size)
    frame = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(frame)
    gap = size * tracking

    widths = [draw.textlength(char, font=font) for char in text]
    total = sum(widths) + gap * (len(text) - 1)
    x = (WIDTH - total) * 0.5

    # The shadow is the same glyphs, blurred, on their own layer, so the blur
    # cannot eat the edges of the text above it.
    under = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    under_draw = ImageDraw.Draw(under)
    cursor = x
    for char, width in zip(text, widths):
        under_draw.text((cursor, baseline), char, font=font, fill=(0, 0, 0, 190), anchor="ls")
        cursor += width + gap
    under = under.filter(ImageFilter.GaussianBlur(shadow))
    frame.alpha_composite(under)

    cursor = x
    for char, width in zip(text, widths):
        draw.text((cursor, baseline), char, font=font, fill=(*colour, 255), anchor="ls")
        cursor += width + gap
    return frame


def pick_one(text: str = "PICK ONE", size: int = 150) -> Image.Image:
    """The hook, over the held frame, above the field rather than on it.

    Sized against the *frame*, not by eye: at 186 the two words plus their
    shadow reach both edges of a 1080 frame, which on a phone is text running
    into the bezel. At 150 with this tracking the mark spans 90 to 993, an eight
    per cent margin each side, and still stands 150 px tall.
    """
    return _shadowed(text, size, PICK_ONE_BASELINE, tracking=0.09)


def _arrow(draw: ImageDraw.ImageDraw, x: float, y: float, size: float, fill) -> None:
    """A rounded arrow, drawn rather than typed.

    Arial Rounded MT Bold reports a glyph for U+2192, but a reported glyph is
    not proof it is the arrow rather than the missing-character box, and a box
    in the middle of the one fact on screen would be the worst place to find
    out. Two rounded strokes cost four lines of code and cannot be wrong - and
    a drawn arrow matches the machine's own soft geometry better than a typeset
    one would.
    """
    shaft = size * 0.86
    head = size * 0.30
    width = max(3, int(round(size * 0.13)))
    draw.line([(x, y), (x + shaft, y)], fill=fill, width=width, joint="curve")
    draw.line(
        [(x + shaft - head, y - head * 0.86), (x + shaft, y), (x + shaft - head, y + head * 0.86)],
        fill=fill,
        width=width,
        joint="curve",
    )


def end_fact(
    before: str = "FROM 6TH",
    after: str = "1ST",
    size: int = 84,
) -> Image.Image:
    """One fact, low in the frame, under the line the sixth racer is crossing.

    Sized like the hook and for the same reason: at 100 the line plus its halo
    spans 30 to 1052 of a 1080 frame, which is no margin at all on a phone. At
    84 it sits inside a ten per cent gutter each side.
    """
    font = load_font(size)
    frame = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    measure = ImageDraw.Draw(frame)
    tracking = size * 0.07
    gap = size * 0.44

    def run(text: str) -> float:
        widths = [measure.textlength(char, font=font) for char in text]
        return sum(widths) + tracking * (len(text) - 1)

    left_width, right_width = run(before), run(after)
    arrow_width = size * 0.86
    total = left_width + gap + arrow_width + gap + right_width
    start = (WIDTH - total) * 0.5
    baseline = END_FACT_BASELINE
    middle = baseline - size * 0.34

    def draw_line(target: Image.Image, colour, blur: int = 0) -> None:
        pen = ImageDraw.Draw(target)
        cursor = start
        for char in before:
            pen.text((cursor, baseline), char, font=font, fill=colour, anchor="ls")
            cursor += measure.textlength(char, font=font) + tracking
        cursor = start + left_width + gap
        _arrow(pen, cursor, middle, size, colour)
        cursor += arrow_width + gap
        for char in after:
            pen.text((cursor, baseline), char, font=font, fill=colour, anchor="ls")
            cursor += measure.textlength(char, font=font) + tracking

    # **Dark letters on a light halo, because the deck is lit.**
    #
    # The first version set this in gold with a dark shadow, like the hook. The
    # hook works because it sits on unlit mountain; this does not, because it
    # sits on the finish deck. Measured over the last second the background
    # under every candidate band runs 130 to 159 luma - cream, checker and
    # channel all bright - and gold is 205, which is four per cent of contrast.
    #
    # So it is inverted, and in doing so it lands on the machine's own idiom:
    # the FINISH gantry the racers have just passed under is dark letterforms on
    # a warm lit panel, and this is the same mark on the same kind of surface.
    glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw_line(glow, (*WARM_WHITE, 235))
    frame.alpha_composite(glow.filter(ImageFilter.GaussianBlur(18)))
    frame.alpha_composite(glow.filter(ImageFilter.GaussianBlur(7)))
    draw_line(frame, (*GRAPHITE, 255))
    return frame


def winner_ring(
    x: float,
    y: float,
    radius: float,
    phase: float,
    *,
    label: str = "WINNER",
) -> Image.Image:
    """A ring opening around the winner, with a small label beside it.

    `phase` runs 0 to 1 over the mark's life. The ring expands quickly and
    fades, which is a pulse rather than a target: a fixed circle sitting on a
    moving marble reads as a video game lock-on, and the brief asks for the
    opposite of that.
    """
    frame = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(frame)

    # Ease out, so most of the growth is in the first third.
    grown = 1.0 - (1.0 - min(1.0, phase * 1.6)) ** 3
    outer = radius * (1.45 + 1.05 * grown)
    fade = math.sin(math.pi * min(1.0, phase)) ** 0.55
    alpha = int(round(235 * fade))
    if alpha <= 0:
        return frame

    width = max(3, int(round(radius * 0.17)))
    draw.ellipse(
        [x - outer, y - outer, x + outer, y + outer],
        outline=(*GOLD, alpha),
        width=width,
    )
    # A second, fainter ring a beat behind, so the pulse has some depth.
    trail = radius * (1.45 + 1.05 * max(0.0, grown - 0.34))
    draw.ellipse(
        [x - trail, y - trail, x + trail, y + trail],
        outline=(*GOLD, int(alpha * 0.38)),
        width=max(2, width // 2),
    )

    font = load_font(54)
    text_x = x + outer + 22
    anchor = "ls"
    if text_x > WIDTH - 260:
        text_x = x - outer - 22
        anchor = "rs"
    under = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    ImageDraw.Draw(under).text(
        (text_x, y + 18), label, font=font, fill=(0, 0, 0, int(180 * fade)), anchor=anchor
    )
    frame.alpha_composite(under.filter(ImageFilter.GaussianBlur(10)))
    draw.text(
        (text_x, y + 18), label, font=font, fill=(*WARM_WHITE, alpha), anchor=anchor
    )
    return frame

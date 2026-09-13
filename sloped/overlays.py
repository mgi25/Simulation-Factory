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
    "MARBLE_HUES",
    "WINNER_HUE",
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

# `lab_palette.MARBLE_COLOURS`, in the order the racers carry them. This is the
# one place a mark is allowed to know what colour a racer is, and it is here so
# that "the winner" can be *shown* rather than named: the end card carries the
# winning marble's own hue, which is the only thing tying a line of text at the
# bottom of the frame to a ball that crossed a line two seconds earlier.
MARBLE_HUES = (
    (224, 37, 50),    # 0  candy red
    (32, 98, 222),    # 1  cobalt
    (24, 169, 78),    # 2  emerald
    (245, 197, 24),   # 3  warm yellow
    (242, 112, 31),   # 4  orange
    (142, 63, 212),   # 5  purple
    (24, 198, 198),   # 6  turquoise
    (240, 85, 155),   # 7  pink
)
# Seed 5432's winner, so `end_fact()` with no arguments is the card the film
# carries rather than a sample of one.
WINNER_HUE = MARBLE_HUES[5]

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
    accent: Sequence[int] = WINNER_HUE,
) -> Image.Image:
    """One fact, low in the frame, under the line the sixth racer is crossing.

    Sized like the hook and for the same reason: at 100 the line plus its halo
    spans 30 to 1052 of a 1080 frame, which is no margin at all on a phone. The
    base size is 84 and it sits inside a ten per cent gutter each side.

    ## V21: a hierarchy, and the winner's own colour

    V20 set both halves at one size, so "FROM 6TH" and "1ST" carried the same
    weight and the line read as a caption. The fact is not symmetric - the
    *result* is the payoff and the starting position is the setup - so the two
    runs are now set at 0.82 and 1.26 of the base, which is a third again of
    cap height between them.

    `accent` is the winning marble's own hue out of `MARBLE_HUES`, drawn as a
    ball the size of the large text's own x-height immediately before "1ST".
    The ring on the winner has been gone for about a second by the time this
    comes on, and a purple dot is what carries "the purple one" across that
    gap. It is filled with the hue, rimmed in graphite so it keeps an edge on
    the lit deck, and it is the only coloured thing in any overlay.
    """
    small = max(1, int(round(size * 0.82)))
    large = max(1, int(round(size * 1.26)))
    font_small = load_font(small)
    font_large = load_font(large)

    frame = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    measure = ImageDraw.Draw(frame)
    track_small = small * 0.07
    track_large = large * 0.06
    gap = size * 0.38

    def run(text: str, font: ImageFont.FreeTypeFont, tracking: float) -> float:
        widths = [measure.textlength(char, font=font) for char in text]
        return sum(widths) + tracking * (len(text) - 1)

    left_width = run(before, font_small, track_small)
    right_width = run(after, font_large, track_large)
    arrow_width = size * 0.86
    dot_radius = large * 0.27
    dot_gap = size * 0.20

    total = (
        left_width + gap + arrow_width + gap
        + 2.0 * dot_radius + dot_gap + right_width
    )
    start = (WIDTH - total) * 0.5
    baseline = END_FACT_BASELINE
    middle = baseline - size * 0.34
    dot_centre = baseline - large * 0.31

    def draw_line(target: Image.Image, colour, *, ball: bool = False) -> None:
        pen = ImageDraw.Draw(target)
        cursor = start
        for char in before:
            pen.text((cursor, baseline), char, font=font_small, fill=colour, anchor="ls")
            cursor += measure.textlength(char, font=font_small) + track_small
        cursor = start + left_width + gap
        _arrow(pen, cursor, middle, size, colour)
        cursor += arrow_width + gap
        box = [
            cursor, dot_centre - dot_radius,
            cursor + 2.0 * dot_radius, dot_centre + dot_radius,
        ]
        if ball:
            pen.ellipse(box, fill=(*accent, 255),
                        outline=(*GRAPHITE, 255),
                        width=max(3, int(round(dot_radius * 0.16))))
            # One small highlight, up and to the left, which is where every
            # practical in the machine is. A flat disc reads as a bullet point;
            # this reads as the ball that just won.
            spot = dot_radius * 0.30
            pen.ellipse(
                [cursor + dot_radius * 0.52 - spot, dot_centre - dot_radius * 0.46 - spot,
                 cursor + dot_radius * 0.52 + spot, dot_centre - dot_radius * 0.46 + spot],
                fill=(*WARM_WHITE, 210),
            )
        else:
            pen.ellipse(box, fill=colour)
        cursor += 2.0 * dot_radius + dot_gap
        for char in after:
            pen.text((cursor, baseline), char, font=font_large, fill=colour, anchor="ls")
            cursor += measure.textlength(char, font=font_large) + track_large

    # **Dark letters on a light plate, because the deck is a checkerboard.**
    #
    # The first version set this in gold with a dark shadow, like the hook. The
    # hook works because it sits on unlit mountain; this does not, because it
    # sits on the finish deck. Measured over the last second the background
    # under every candidate band runs 130 to 159 luma - cream, checker and
    # channel all bright - and gold is 205, which is four per cent of contrast.
    # So it is inverted, and in doing so it lands on the machine's own idiom:
    # the FINISH gantry the racers have just passed under is dark letterforms on
    # a warm lit panel, and this is the same mark on the same kind of surface.
    #
    # **V21: the mean is not the background.** That measurement is of a band,
    # and the band is a chequer - half of it is the dark tile, and graphite on
    # a dark tile is nothing. V20 got away with it because the light behind the
    # text was a soft blur that thinned out to nothing at the glyph edge; at
    # V21's size "1ST" lands squarely on two black squares. So the soft lift
    # stays and a second, tighter pass is driven back up to opacity behind it,
    # which gives every glyph a solid warm-white edge whatever tile it is over.
    #
    # It is built from a *mask* rather than by blurring a coloured layer: blur
    # runs per channel, so blurring warm white on transparent black drags the
    # colour towards black as the alpha falls and the halo comes out grey.
    mask = Image.new("L", (WIDTH, HEIGHT), 0)
    draw_line(mask, 255)

    def plate(blur: float, boost: float, soften: float = 0.0) -> Image.Image:
        alpha = mask.filter(ImageFilter.GaussianBlur(blur))
        if boost != 1.0:
            alpha = alpha.point(lambda value: min(255, int(value * boost)))
        if soften:
            alpha = alpha.filter(ImageFilter.GaussianBlur(soften))
        layer = Image.new("RGBA", (WIDTH, HEIGHT), (*WARM_WHITE, 0))
        layer.putalpha(alpha)
        return layer

    frame.alpha_composite(plate(19.0, 1.5))
    frame.alpha_composite(plate(7.0, 3.4, 2.5))
    draw_line(frame, (*GRAPHITE, 255), ball=True)
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

    ## V21: the same mark, landing harder

    The V20 mark is correct and quiet, and at phone size quiet is the fault: a
    gold hairline over a lit deck, 0.20 s after a crossing, is something a
    viewer notices only if they were already looking at the right marble. Three
    things change and none of them is a new element on screen -

    * **a short glow**, a soft disc of the ring's own gold behind the marble,
      up in the first fifth of the mark and gone by halfway. It is the thing
      that makes the eye arrive; the ring is what it reads once it is there;
    * **a flash on the frame the mark opens**, a marble of warm white over the
      ball, at full strength for about two frames and gone inside seven. That
      is the beat the crossing cue is on, and it is the only genuinely
      synchronised part;
    * **a heavier stroke**, 0.17 of the marble's radius to 0.24, with the
      trailing ring at the same proportion.

    The first build of all three was measured rather than looked at and was too
    soft to see: a 23-pixel flash blurred by 19 pixels raised the mean of the
    region around the winner by 1.6 of 255. Blur radius is the term that
    matters at this scale, not alpha.

    Everything stays inside about three marble radii of the winner, so the
    other seven racers, the deck and the FINISH gantry are never covered. The
    mark is still 0.70 s long and still ends 0.88 s before the fourth and fifth
    arrive together.
    """
    frame = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(frame)

    # Ease out, so most of the growth is in the first third.
    grown = 1.0 - (1.0 - min(1.0, phase * 1.6)) ** 3
    outer = radius * (1.45 + 1.05 * grown)
    fade = math.sin(math.pi * min(1.0, phase)) ** 0.55
    alpha = int(round(240 * fade))

    # The ring's envelope is zero at both ends, so the opening frame carries the
    # glow and the flash alone and the ring grows out of them. Returning early on
    # `alpha <= 0`, as V20 did, would have thrown away the one frame the flash
    # exists for.

    # **The glow, under everything.** A filled disc rather than a ring, so what
    # the eye catches is a brightening around the ball and not a second outline
    # competing with the first. It is drawn on its own layer and blurred, and
    # its life is the first half of the mark: `bloom` is 1 at the opening frame
    # and 0 from phase 0.5 on.
    bloom = max(0.0, 1.0 - min(1.0, phase / 0.5)) ** 1.4
    if bloom > 0.01:
        halo = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        spread = radius * (1.70 + 1.00 * grown)
        ImageDraw.Draw(halo).ellipse(
            [x - spread, y - spread, x + spread, y + spread],
            fill=(*GOLD, int(round(150 * bloom))),
        )
        frame.alpha_composite(halo.filter(ImageFilter.GaussianBlur(radius * 0.50)))

    width = max(3, int(round(radius * 0.24)))
    if alpha > 0:
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

    # **The flash.** Two frames of the 42 the mark runs for, over the ball
    # itself, on the beat the crossing cue lands on. Any longer and it is a
    # blown highlight sitting on the winner for a third of a second.
    strike = max(0.0, 1.0 - min(1.0, phase / 0.110)) ** 1.4
    if strike > 0.01:
        spark = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        core = radius * (0.90 + 0.6 * (1.0 - strike))
        ImageDraw.Draw(spark).ellipse(
            [x - core, y - core, x + core, y + core],
            fill=(*WARM_WHITE, int(round(238 * strike))),
        )
        frame.alpha_composite(spark.filter(ImageFilter.GaussianBlur(radius * 0.20)))

    if alpha <= 0:
        return frame

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

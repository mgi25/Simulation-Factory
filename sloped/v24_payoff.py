"""V24: the end of the Short, answered in the viewer's own words.

The question a cold viewer asks a marble race is one question:

    DID MY COLOUR WIN?

V22.1 answers it with `FROM 6TH -> 1ST` and a coloured dot the size of a
capital letter, 2.98 s after the winner crosses. That is a *result*, and the
brief is right that it is not an *answer*: it never says a colour, and the one
coloured thing in it is 27 px wide at the bottom of a 1920 px frame.

This module is the prototype of a stronger one. It builds a two-line card -

    PURPLE WINS
    6TH -> 1ST

in three styles that differ in **how the colour gets into the payoff**, which
is the only interesting question here and the one the measurements below turn
out to settle.

## The winner is purple, and that is measured rather than assumed

Seed 5432's finish order is `5, 2, 7, 4, 1, 6, 3, 0`, which this lab reproduced
twice: once by re-running the race on `sloped_course(routes="both")`, and once
by reading the `finish_line` events out of the locked `race_5432.json`. Both
say marble **5**, and `MARBLE_HUES[5]` is `#8E3FD4`.

`routes` is not a detail. `run_race(seed=5432)` with the default machine puts
all eight racers down the blue route and hands back a different winner
altogether - marble 7, at 19.65 - because the default course has no fork in it.
The film's course does. A winner read off the wrong machine is the whole card
wrong, so `WINNER_INDEX` is pinned and `tests/test_sloped_v24_payoff.py` checks
it against the replay the film actually ships.

`#8E3FD4` is hue 271.8 degrees, which is **purple** in anybody's words, and is
what `lab_palette` itself calls it. Its nearest neighbours in the field are
cobalt at 219.2 and pink at 332.9, so the name is 52.6 degrees clear of the one
below it and 61.1 clear of the one above. It is not red. `COLOUR_NAMES` is the
human-facing label for every racer, so a different seed names its own winner
rather than falling back on a guess.

## The finding this module is actually built on

**The winner is not on screen when either of V22.1's winner marks is.**

Measured on the delivered master, frame by frame, by looking for the racer's
own hue inside the disc `presentation.screen_track` projects it into - a
projection says where a marble *would* be, and the gantry does not care:

    22.900 - 23.100   VISIBLE   0.217 s   the crossing
    23.117 - 24.500   hidden    1.400 s   behind the finish gantry's rail
    24.517 - 25.667   VISIBLE   1.167 s   back out, parked on the deck
    25.683 - 26.517   hidden    0.850 s   gone behind the FINISH sign

Against that, what the film currently does:

    winner ring   23.100 - 23.800   ->  0.017 s of it on a visible marble
    end fact      25.883 - 26.533   ->  0.000 s of it on a visible marble

The ring spends 0.683 of its 0.700 s drawing a gold circle and the word WINNER
on the gantry rail, with nothing inside it; the only racer near enough to be
read as the subject is **emerald, which came second**. And the end card names
the winner with a purple dot at a moment when purple is not in the picture and
the two marbles that are - measured, intruding on the card's own glyph band on
7 and 9 of its 40 frames - are **candy red** and **warm yellow**.

So the reason "did my colour win" does not land is not the wording. Both marks
point at the winner while the winner is behind a rail.

## Luma carries the words, hue carries the colour

The card's home is the band `PAYOFF_BAND`, and on that background the winner's
own hue cannot be used for letterforms at all:

    warm white on the band          3.82:1 worst pixel, 7.11:1 at the mean
    #8E3FD4 on the band             1.38:1 worst pixel, 1.35:1 at the mean
    #8E3FD4 lifted 75% to white     2.65:1 worst pixel - and no longer purple

Purple's relative luminance is 90.6 and the band's mean is 85. They are the
same *value*; a purple word there is invisible. But the same purple as an
**area** is unmistakable - against the backdrop actually behind the card it is
dE 90.8, of which 89.8 is chroma. Hue separation is enormous where luma
separation is nil.

That is the rule the three styles are spread across, and `plate` is the one
that takes it seriously:

    luma carries the words; hue carries the colour; never ask one mark for both

`plate` reverses warm white out of a lozenge of the racer's **exact** hue -
5.26:1, no tinting, so the colour sample the viewer matches against their
marble is the marble's own value - and gets the largest colour area of the
three while keeping text contrast that does not depend on the background.

## What this module does not do

No confetti, no leaderboard, no flags, no country. Two lines, one colour, one
comeback fact, and the ring the film already had - moved, in `schedule()`, to
the 0.217 s where it has a marble to sit on.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from sloped import overlays
from sloped.overlays import GRAPHITE, HEIGHT, WARM_WHITE, WIDTH, load_font

__all__ = [
    "COLOUR_NAMES",
    "PAYOFF_BAND",
    "RECOGNITION_BEAT",
    "STYLES",
    "WINNER_INDEX",
    "WINNER_VISIBLE",
    "Payoff",
    "build",
    "contrast_ratio",
    "ordinal",
    "relative_luminance",
    "schedule",
    "winner_label",
]

# The human-facing name of every racer hue, in `overlays.MARBLE_HUES` order and
# taken from `lab_palette.MARBLE_COLOURS`' own comments rather than invented.
# One word each, because the card has room for one word and a viewer thinks in
# one word: nobody looks at a marble race and decides their marble is "cobalt
# blue #2062DE".
COLOUR_NAMES = (
    "RED",        # 0  #E02532  candy red
    "BLUE",       # 1  #2062DE  cobalt
    "GREEN",      # 2  #18A94E  emerald
    "YELLOW",     # 3  #F5C518  warm yellow
    "ORANGE",     # 4  #F2701F  orange
    "PURPLE",     # 5  #8E3FD4  purple
    "TEAL",       # 6  #18C6C6  turquoise
    "PINK",       # 7  #F0559B  pink
)

# Seed 5432's winner and the worst place it ever held, both measured. See the
# module docstring: this is marble 5, which is PURPLE, and the film's course is
# the one with the fork in it.
WINNER_INDEX = 5
WINNER_FROM = 6

# Where the winner is actually on screen, in finished-film seconds, measured on
# the delivered V22.1 master. Anything that points *at* the marble has to live
# inside one of these; anything outside them has to carry the colour itself.
WINNER_VISIBLE = ((22.900, 23.100), (24.517, 25.667))

# The winner's crossing, in finished-film seconds. `Clock.at(20.85)` on the
# V22.1 track, which is where every offset below is measured from.
CROSSING = 22.900

# **The band the card lives in, and why it is this one.**
#
# Measured over the whole tail of the delivered master - every second frame
# from 23.900 to the last, which is every background the card could ever sit
# on - taking the *maximum* luma of each row across the text corridor
# x 90..990. The tallest run of rows whose maximum never exceeds 130 is
#
#     y 297 .. 548,  252 px,  max luma 127
#
# It is the dark shoulder of the backdrop between the pale mountain above and
# the machine's gold top rail below, and it is clear of all eight racers for
# the entire window: the settled field sits at y 670..900 and the arrivals
# sweep down the middle below that. Nothing the card can be put on is brighter
# than 127 of 255 at any pixel, which is what lets the words be warm white with
# a shadow and no plate under them.
#
# The shipped `end_fact` baseline of 1395 is not this and was never measured
# for this edit: it was set on V19/V21's finish lens, where the band at
# 1152..1586 was clear. V22.1's camera parks *behind* the line instead, so the
# approach channel - and the three racers still coming down it - runs straight
# through that band. Measured on the card's own 40 frames, marble 0 crosses its
# glyphs on 7 of them and marble 3 on 9.
PAYOFF_BAND = (297, 548)

# The recognition beat: how long after the crossing the card comes up. The
# brief asks for 0.8-1.5 s and this is the middle of it. See `schedule()` for
# what the window costs and why 1.0 is the one to ship.
RECOGNITION_BEAT = 1.0

# The card's own length. Long enough to read two lines twice; short enough that
# Session B can shorten the tail behind it without the card being the thing
# that sets the runtime.
PAYOFF_SECONDS = 1.8

# The winner mark, moved. V22.1 opens its ring 0.200 s after the crossing and
# runs 0.700 s, which puts **one frame** of it on a visible marble; the other
# 0.683 s is a gold circle and the word WINNER drawn on the gantry rail, with
# the second-place emerald as the nearest thing inside it.
#
# The marble is on screen for 0.217 s, so the ring opens **on** the crossing
# and is nearly over by the time the rail takes it: 0.217 of its 0.300 s has a
# visible subject, against 0.017 of 0.700. A ring cut to the visible window
# exactly would be 13 frames, which is too short for `winner_ring`'s envelope
# to read as a pulse rather than a blink - and the tail is the part that
# matters least, because the glow and the flash are both in the first fifth,
# where the marble certainly is.
RING_DELAY = 0.0
RING_SECONDS = 0.30


def ordinal(place: int) -> str:
    """`6` -> `6TH`. Uppercase, because everything on this card is."""
    if place <= 0:
        raise ValueError(f"a finishing place is 1 or more, not {place}")
    if 10 <= place % 100 <= 20:
        suffix = "TH"
    else:
        suffix = {1: "ST", 2: "ND", 3: "RD"}.get(place % 10, "TH")
    return f"{place}{suffix}"


def winner_label(index: int) -> str:
    """The human-facing colour name of a racer. Never a guess."""
    return COLOUR_NAMES[index % len(COLOUR_NAMES)]


def relative_luminance(rgb: Sequence[int]) -> float:
    """WCAG relative luminance of an sRGB triple."""
    channels = []
    for value in rgb[:3]:
        srgb = value / 255.0
        channels.append(
            srgb / 12.92 if srgb <= 0.04045 else ((srgb + 0.055) / 1.055) ** 2.4
        )
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(one: Sequence[int], two: Sequence[int]) -> float:
    """WCAG contrast between two sRGB triples, 1.0 to 21.0."""
    first, second = relative_luminance(one), relative_luminance(two)
    high, low = max(first, second), min(first, second)
    return (high + 0.05) / (low + 0.05)


@dataclass(frozen=True)
class Payoff:
    """One rendered payoff card and what can be checked about it."""

    style: str
    image: Image.Image
    winner: int
    label: str
    from_place: int
    # The ink's bounding box, so a test can assert it stayed in the band.
    box: tuple[int, int, int, int]
    # Text contrast against the band's worst pixel, and the colour area in px.
    text_contrast: float
    colour_pixels: int


def _ink_box(image: Image.Image, floor: int = 200) -> tuple[int, int, int, int]:
    """The bounding box of everything solid in a card, shadows excluded."""
    alpha = image.getchannel("A")
    mask = alpha.point(lambda value: 255 if value >= floor else 0)
    box = mask.getbbox()
    if box is None:
        raise ValueError("the card drew nothing")
    return box


# The gutter every line is fitted to. `overlays.pick_one` found this the hard
# way - at size 186 its two words plus their shadow reach both edges of a 1080
# frame, which on a phone is text running into the bezel - and settled on about
# eight per cent a side. This is the same rule, applied by measurement instead
# of by a chosen size: 96 px a side leaves 888 px of line, and the soft bed
# adds about a dozen more each way before it falls under the ink threshold.
GUTTER = 96
LINE_WIDTH = WIDTH - 2 * GUTTER


def _measure(text: str, font: ImageFont.FreeTypeFont, tracking: float) -> float:
    draw = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    widths = [draw.textlength(char, font=font) for char in text]
    return sum(widths) + tracking * (len(text) - 1)


def _fit(width_at: "callable", target: float = LINE_WIDTH, cap: int = 150) -> int:
    """The largest font size whose line still fits the gutter.

    A TrueType advance scales linearly with the size, so one measurement at a
    reference size gives the whole curve and there is nothing to search. Doing
    it this way rather than typing a size means a font substitution - the
    fallbacks in `overlays.FONT_CANDIDATES` are not metrically compatible with
    Arial Rounded MT Bold - moves the type instead of pushing it off the frame.

    **`cap` is not decoration.** Fitting to the width alone makes a *short*
    name set *larger*, which is the opposite of what a band 251 px tall can
    take: `RED WINS` is four glyphs shorter than `PURPLE WINS`, fits at a size
    a third bigger, and pushed the lozenge 13 px out of the top of the band.
    Every caller derives its cap from `PAYOFF_BAND` rather than choosing one.
    """
    reference = 100
    natural = width_at(reference)
    if natural <= 0:
        raise ValueError("the line measured zero wide")
    return max(24, min(cap, int(target / natural * reference)))


def _height_cap(baseline: float, rise: float) -> int:
    """The largest size whose ink still starts below the top of the band.

    `rise` is how far above the baseline a style's tallest element reaches, as
    a multiple of the font size: 0.74 for a cap height alone, more for a style
    that puts padding or a ball above it.
    """
    return max(24, int((baseline - PAYOFF_BAND[0]) / rise))


def _fill_for(target: Image.Image, colour: Sequence[int] | int, alpha: int = 255):
    """The right kind of fill for the target's mode.

    Every mark here is drawn twice - once into the RGBA card and once into the
    `L` mask the shadow is built from - and PIL will not take an RGBA tuple on
    an `L` image. Rather than branch at every call site, the two shapes of fill
    are resolved in one place.
    """
    if target.mode == "L":
        return 255 if not isinstance(colour, (tuple, list)) else 255
    if isinstance(colour, int):
        return (colour, colour, colour, alpha)
    return (*tuple(colour)[:3], alpha)


def _run(
    target: Image.Image,
    text: str,
    font: ImageFont.FreeTypeFont,
    x: float,
    baseline: float,
    colour: Sequence[int] | int,
    tracking: float,
    alpha: int = 255,
) -> float:
    """One letter-spaced run, left edge at `x`. Returns the cursor after it."""
    pen = ImageDraw.Draw(target)
    fill = _fill_for(target, colour, alpha)
    cursor = x
    for char in text:
        pen.text((cursor, baseline), char, font=font, fill=fill, anchor="ls")
        cursor += pen.textlength(char, font=font) + tracking
    return cursor


def _arrow(draw: ImageDraw.ImageDraw, x: float, y: float, size: float, fill) -> None:
    """A rounded arrow, drawn rather than typed.

    `overlays` draws its own for `end_fact`, sized against that line; this one
    is sized against the fact line here, which is a little over half as tall.
    The reason for drawing it at all is the same one and it is worth repeating:
    a reported glyph for U+2192 is not proof it is an arrow rather than the
    missing-character box, and the middle of the payoff is the worst place in
    the film to find that out.
    """
    shaft = size * 0.86
    head = size * 0.30
    width = max(3, int(round(size * 0.14)))
    draw.line([(x, y), (x + shaft, y)], fill=fill, width=width, joint="curve")
    draw.line(
        [
            (x + shaft - head, y - head * 0.86),
            (x + shaft, y),
            (x + shaft - head, y + head * 0.86),
        ],
        fill=fill,
        width=width,
        joint="curve",
    )


def _ball(
    draw: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    radius: float,
    hue: Sequence[int],
) -> None:
    """The racer, as a ball rather than a bullet.

    Filled with the hue **unmodified** - the point of it is to be the colour
    the viewer is matching against - rimmed in graphite so it keeps an edge
    wherever it lands, and with one highlight up and to the left, which is
    where every practical in the machine is.
    """
    draw.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius],
        fill=(*hue[:3], 255),
        outline=(*GRAPHITE, 255),
        width=max(3, int(round(radius * 0.14))),
    )
    spot = radius * 0.24
    draw.ellipse(
        [
            cx + radius * 0.50 - spot, cy - radius * 0.46 - spot,
            cx + radius * 0.50 + spot, cy - radius * 0.46 + spot,
        ],
        fill=(*WARM_WHITE, 235),
    )


def _lozenge(
    draw: ImageDraw.ImageDraw,
    box: Sequence[float],
    hue: Sequence[int],
) -> None:
    """A rounded plate of the racer's exact hue, to reverse the word out of."""
    left, top, right, bottom = box
    radius = (bottom - top) * 0.34
    draw.rounded_rectangle(
        [left, top, right, bottom],
        radius=radius,
        fill=(*hue[:3], 255),
        outline=(*GRAPHITE, 255),
        width=max(3, int(round((bottom - top) * 0.045))),
    )


def _fact_line(
    frame: Image.Image,
    mask: Image.Image,
    centre_y: float,
    size: int,
    before: str,
    after: str,
    *,
    colour: Sequence[int] = WARM_WHITE,
) -> None:
    """`6TH -> 1ST`, centred, with the arrow drawn between the two runs."""
    def width_at(probe: int) -> float:
        probe_font = load_font(probe)
        probe_track = probe * 0.07
        return (
            _measure(before, probe_font, probe_track)
            + 2.0 * probe * 0.42
            + probe * 0.80
            + _measure(after, probe_font, probe_track)
        )

    # The fact is the setup, not the payoff, so it is capped well below the
    # headline even when it would fit wider - `FROM 6TH -> 1ST` is short enough
    # that an unconstrained fit would set it larger than `WINS`.
    size = min(_fit(width_at, cap=size), int(round(size * 0.60)))
    font = load_font(size)
    tracking = size * 0.07
    gap = size * 0.42
    arrow = size * 0.80
    left = _measure(before, font, tracking)
    right = _measure(after, font, tracking)
    total = left + gap + arrow + gap + right
    x = (WIDTH - total) * 0.5
    baseline = centre_y + size * 0.36

    for target in (mask, frame):
        pen = ImageDraw.Draw(target)
        cursor = _run(target, before, font, x, baseline, colour, tracking)
        cursor += gap - tracking
        _arrow(pen, cursor, centre_y, size, _fill_for(target, colour))
        cursor += arrow + gap
        _run(target, after, font, cursor, baseline, colour, tracking)


def _compose(frame: Image.Image, mask: Image.Image) -> Image.Image:
    """Put the soft bed under the ink and return the finished card.

    Two passes, the same shape the shipped overlays settled on: a wide, weak
    one that lifts the whole mark off the background, and a tight, strong one
    that guarantees an edge on every glyph whatever it happens to be over.
    """
    out = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    wide = mask.filter(ImageFilter.GaussianBlur(26.0))
    wide = wide.point(lambda value: min(255, int(value * 1.35)))
    bed = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    bed.putalpha(wide)
    out.alpha_composite(bed)

    tight = mask.filter(ImageFilter.GaussianBlur(9.0))
    tight = tight.point(lambda value: min(255, int(value * 2.6)))
    near = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    near.putalpha(tight)
    out.alpha_composite(near)

    out.alpha_composite(frame)
    return out


# --- the three styles -------------------------------------------------------
#
# All three carry the same two facts and differ only in how the colour is
# stated. The band is 252 px and every one of them is laid out inside it by
# measurement rather than by assumed cap height, so a font substitution moves
# the ink without breaking the fit.


def _style_tint(hue: Sequence[int], label: str, from_place: int) -> Image.Image:
    """A. `PURPLE WINS` with the colour word set in the colour.

    The obvious design, and the measurements say it is the weak one: to reach
    even 2.26:1 against the band's worst pixel the hue has to be lifted 65% of
    the way to white, at which point `#8E3FD4` has become `(215, 184, 229)` and
    reads as pale lilac rather than as the ball the viewer was watching. It is
    built anyway because "set the word in the colour" is the first thing anyone
    asks for and it is worth being able to look at the answer.
    """
    frame = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    mask = Image.new("L", (WIDTH, HEIGHT), 0)

    lift = 0.65
    tint = tuple(
        int(round(channel + (white - channel) * lift))
        for channel, white in zip(hue[:3], WARM_WHITE)
    )

    def width_at(size: int) -> float:
        font = load_font(size)
        tracking = size * 0.06
        return (
            _measure(label, font, tracking)
            + size * 0.40
            + _measure("WINS", font, tracking)
        )

    baseline = 425.0
    size = _fit(width_at, cap=_height_cap(baseline, 0.74))
    font = load_font(size)
    tracking = size * 0.06
    gap = size * 0.40
    left = _measure(label, font, tracking)
    right = _measure("WINS", font, tracking)
    total = left + gap + right
    x = (WIDTH - total) * 0.5

    _run(mask, label, font, x, baseline, WARM_WHITE, tracking)
    _run(mask, "WINS", font, x + left + gap, baseline, WARM_WHITE, tracking)
    _run(frame, label, font, x, baseline, tint, tracking)
    _run(frame, "WINS", font, x + left + gap, baseline, WARM_WHITE, tracking)

    _fact_line(frame, mask, 505.0, 74, ordinal(from_place), ordinal(1))
    return _compose(frame, mask)


def _style_chip(hue: Sequence[int], label: str, from_place: int) -> Image.Image:
    """B. `(o) PURPLE WINS`, the ball stated and the words left alone.

    The shipped `end_fact` had this instinct - a ball of the winner's hue, in
    the line, unmodified - and it was right. What was wrong was where it was:
    27 px across, at y 1395, in a band three other racers drive through. Here
    the ball is 0.46 of the big line's own height, which is 64 px, and it is
    the leftmost thing on the card so the colour is read before the word is.
    """
    frame = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    mask = Image.new("L", (WIDTH, HEIGHT), 0)

    def width_at(size: int) -> float:
        font = load_font(size)
        tracking = size * 0.06
        return (
            2.0 * (size * 0.23 + 14.0)
            + size * 0.26
            + _measure(label, font, tracking)
            + size * 0.38
            + _measure("WINS", font, tracking)
        )

    baseline = 425.0
    # The ball's top is 0.33 (its centre) + 0.23 (its radius) above the
    # baseline, which clears the 0.74 of a cap height; the 14 px the radius
    # adds on top of that is taken off the headroom before the cap is drawn.
    size = _fit(width_at, cap=_height_cap(baseline - 14.0, 0.56))
    font = load_font(size)
    tracking = size * 0.06
    radius = size * 0.23 + 14.0
    chip_gap = size * 0.26
    word_gap = size * 0.38

    words = _measure(label, font, tracking) + word_gap + _measure("WINS", font, tracking)
    total = 2.0 * radius + chip_gap + words
    x = (WIDTH - total) * 0.5
    centre = baseline - size * 0.33

    # The ball is on the frame only: it is an area, not a letterform, and
    # putting it in the shadow mask would bed a 128 px dark disc into the
    # backdrop and cost the hue the separation it is there for.
    _ball(ImageDraw.Draw(frame), x + radius, centre, radius, hue)

    cursor = x + 2.0 * radius + chip_gap
    for target in (mask, frame):
        step = _run(target, label, font, cursor, baseline, WARM_WHITE, tracking)
        _run(target, "WINS", font, step - tracking + word_gap, baseline,
             WARM_WHITE, tracking)

    _fact_line(frame, mask, 505.0, 72, f"FROM {ordinal(from_place)}", ordinal(1))
    return _compose(frame, mask)


def _style_plate(hue: Sequence[int], label: str, from_place: int) -> Image.Image:
    """C. The colour as an area, the word reversed out of it.

    The one the contrast table points at. The lozenge is the racer's **exact**
    hue - no lift, no tint - so the sample the viewer matches against their
    marble is the marble's own value, and warm white on it is 5.26:1 whatever
    is behind the card, because the background is no longer in the comparison.
    It is also much the largest colour area of the three, which is what the
    brief means by winner-colour emphasis: about 23x the area of the dot the
    shipped card names the winner with.

    `WINS` sits outside the plate in warm white, so the plate reads as the
    subject and the verb is not competing with it.
    """
    frame = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    mask = Image.new("L", (WIDTH, HEIGHT), 0)
    plate_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))

    def width_at(size: int) -> float:
        font = load_font(size)
        tracking = size * 0.07
        return (
            _measure(label, font, tracking)
            + 2.0 * size * 0.30
            + size * 0.26
            + _measure("WINS", font, tracking)
        )

    baseline = 428.0
    size = _fit(width_at, cap=_height_cap(baseline, 0.74 + 0.24))
    font = load_font(size)
    tracking = size * 0.07
    pad_x = size * 0.30
    pad_y = size * 0.24
    gap = size * 0.26

    label_width = _measure(label, font, tracking)
    wins_width = _measure("WINS", font, tracking)
    plate_width = label_width + 2.0 * pad_x
    total = plate_width + gap + wins_width
    x = (WIDTH - total) * 0.5
    top = baseline - size * 0.74 - pad_y
    bottom = baseline + size * 0.16 + pad_y

    _lozenge(ImageDraw.Draw(plate_layer), (x, top, x + plate_width, bottom), hue)
    # The plate is its own bed, so only `WINS` and the fact go in the shadow
    # mask. Bedding the plate would ring a dark halo round a shape that already
    # carries a graphite rim.
    _run(plate_layer, label, font, x + pad_x, baseline, WARM_WHITE, tracking)
    frame.alpha_composite(plate_layer)

    wins_x = x + plate_width + gap
    _run(mask, "WINS", font, wins_x, baseline, WARM_WHITE, tracking)
    _run(frame, "WINS", font, wins_x, baseline, WARM_WHITE, tracking)

    _fact_line(frame, mask, 508.0, 72, ordinal(from_place), ordinal(1))
    return _compose(frame, mask)


STYLES = {
    "tint": _style_tint,
    "chip": _style_chip,
    "plate": _style_plate,
}

# The style this lab recommends. See the module docstring and the report.
RECOMMENDED = "plate"


def build(
    style: str = RECOMMENDED,
    winner: int = WINNER_INDEX,
    from_place: int = WINNER_FROM,
) -> Payoff:
    """One payoff card, with the numbers a test needs to check it."""
    if style not in STYLES:
        raise KeyError(f"no such payoff style: {style!r}")
    hue = overlays.MARBLE_HUES[winner % len(overlays.MARBLE_HUES)]
    label = winner_label(winner)
    image = STYLES[style](hue, label, from_place)
    box = _ink_box(image)

    # Text contrast is quoted against the band's own worst pixel, which is the
    # honest comparison: the card has to survive the background it will be on,
    # not a convenient one. For `plate` the word is on the hue, so that is what
    # it is measured against.
    worst = (127, 127, 127)
    text_against = hue if style == "plate" else worst
    contrast = contrast_ratio(WARM_WHITE, text_against)

    pixels = _colour_area(image, hue)
    return Payoff(
        style=style,
        image=image,
        winner=winner,
        label=label,
        from_place=from_place,
        box=box,
        text_contrast=contrast,
        colour_pixels=pixels,
    )


def _colour_area(image: Image.Image, hue: Sequence[int]) -> int:
    """How many solid pixels of the card carry the racer's colour.

    The measure behind "winner-colour emphasis": a payoff that states a colour
    in 27 px of dot and one that states it in a lozenge are not the same mark,
    and this is the number that says so.

    Matched on **hue angle** rather than on the triple, so a style that lifts
    the colour towards white to make it legible still scores for the colour it
    is trying to name. Counting exact triples would give `tint` zero, which
    would be an artefact of the metric rather than a fact about the card.
    """
    import numpy as np

    rgba = np.asarray(image).astype(np.float64)
    alpha = rgba[:, :, 3]
    red, green, blue = rgba[:, :, 0], rgba[:, :, 1], rgba[:, :, 2]
    high = np.max(rgba[:, :, :3], axis=2)
    low = np.min(rgba[:, :, :3], axis=2)
    spread = high - low
    safe = np.maximum(spread, 1e-6)
    angle = np.where(
        high == red, ((green - blue) / safe) % 6.0,
        np.where(high == green, ((blue - red) / safe) + 2.0,
                 ((red - green) / safe) + 4.0),
    ) * 60.0
    target = _hue_angle(hue)
    delta = np.abs((angle - target + 180.0) % 360.0 - 180.0)
    saturation = np.where(high > 0, spread / np.maximum(high, 1e-6), 0.0)
    return int(((alpha > 200) & (delta < 22.0) & (saturation > 0.18)).sum())


def schedule(
    crossing: float = CROSSING,
    beat: float = RECOGNITION_BEAT,
    seconds: float = PAYOFF_SECONDS,
    fps: int = 60,
) -> dict[str, object]:
    """When the ring and the card run, and what the choice costs.

    The sequence the brief asks for is `cross -> beat -> payoff -> end`, and
    the only part of it with a hard constraint is the ring: the winner is on
    screen for 0.217 s and the ring has to be inside that or it is marking a
    rail. So the ring opens **on** the crossing rather than 0.200 s after it.

    The card is the other way round - it has to work while the winner is
    hidden, because every beat in the brief's 0.8-1.5 s band falls inside the
    1.400 s the gantry has it. That is not a reason to move the card; it is the
    reason the card names the colour instead of pointing at it. What the beat
    does buy, at 1.0 s, is that the card is **still up** when the winner comes
    back out at 24.517, so the ball walks back into the picture underneath a
    line that has already said PURPLE.
    """
    beat = float(beat)
    if not 0.8 - 1e-9 <= beat <= 1.5 + 1e-9:
        raise ValueError(f"the recognition beat is 0.8-1.5 s, not {beat}")

    def snap(value: float) -> float:
        # Whole frames, for the same reason `sloped_short` snaps the ring: an
        # ffmpeg offset that is not a whole tick lands between two frames and
        # the first one is never composited.
        return round(value * fps) / fps

    ring_from = snap(crossing + RING_DELAY)
    ring_to = snap(ring_from + RING_SECONDS)
    card_from = snap(crossing + beat)
    card_to = snap(card_from + seconds)

    visible = [
        window for window in WINNER_VISIBLE
        if window[0] < card_to and window[1] > card_from
    ]
    overlap = sum(
        max(0.0, min(card_to, high) - max(card_from, low)) for low, high in visible
    )
    ring_overlap = sum(
        max(0.0, min(ring_to, high) - max(ring_from, low))
        for low, high in WINNER_VISIBLE
    )
    return {
        "crossing": crossing,
        "beat": beat,
        "ring": (ring_from, ring_to),
        "card": (card_from, card_to),
        "ring_on_visible_winner": round(ring_overlap, 4),
        "card_over_visible_winner": round(overlap, 4),
        "ends": card_to,
    }


def phone(image: Image.Image, width: int = 270, height: int = 480) -> Image.Image:
    """The card at the size it is actually judged at."""
    return image.resize((width, height), Image.LANCZOS)


def over(frame: Image.Image, card: Image.Image) -> Image.Image:
    """Composite a card onto a rendered film frame."""
    out = frame.convert("RGBA")
    out.alpha_composite(card)
    return out.convert("RGB")


def measured_contrast(
    frame: Image.Image, card: Image.Image, floor: int = 200
) -> tuple[float, float]:
    """The card's real contrast on a real frame: `(worst, median)`.

    Not the table's figure, which is against a flat worst-case grey. This asks
    the question the viewer's eye asks: **where a light letterform sits
    directly on the film, how far from it is the film?**

    Three definitions, and all three of them matter:

    * **ink** is the card's warm-white pixels only. Not "alpha >= floor",
      which was the first version of this and was wrong: the soft bed is drawn
      as black at high alpha, so that set is mostly shadow, the front luminance
      comes out near zero and every card scores 1.00:1 against a dark frame.
      It is a measurement of the shadow, not of the type.
    * **behind** is the **composited** pixel beside the letter, not the raw
      film. That is deliberate and it is not cheating: the soft bed is part of
      the card, it is there to buy exactly this, and what the viewer's eye
      compares the letter against is what ends up on screen next to it. A
      first attempt restricted the ring to pixels where the card is
      transparent, and found none - the wide pass is 26 px of blur, so there
      is no bare film within reach of a glyph at all.
    * the ratio is reported against the **brightest** adjacent pixel as the
      worst case, not the mean, because legibility fails at the bright spot
      and nowhere else.
    """
    import numpy as np

    rgba = np.asarray(card).astype(np.float64)
    alpha = rgba[:, :, 3]
    ink = (alpha >= floor) & (rgba[:, :, :3] >= 200.0).all(axis=2)
    if not ink.any():
        raise ValueError("the card has no light ink to measure")

    # **The ring is taken at a standoff, and that is not a detail.** The band
    # of pixels immediately outside a glyph is the glyph's own antialiasing -
    # nearly as bright as the letter itself - so a ring that starts at the ink
    # edge measures the type against its own edge and reports about 1.45:1 for
    # every card ever built, which is what the first two versions of this did.
    # Seven pixels of clearance steps over it. Solid card marks are excluded
    # too, so `plate`'s reversed letters are not scored against their own
    # lozenge: what is being asked here is how the ink fares against the
    # *film*, and the lozenge is a known 5.26:1 that does not vary with it.
    plate_mask = Image.fromarray((ink * 255).astype("uint8"))
    inner = np.asarray(plate_mask.filter(ImageFilter.MaxFilter(15))) > 127
    outer = np.asarray(plate_mask.filter(ImageFilter.MaxFilter(35))) > 127
    ring = outer & (~inner) & (alpha < floor)
    if not ring.any():
        raise ValueError("no background beside the card's ink")

    def luminance(pixels: np.ndarray) -> np.ndarray:
        srgb = pixels / 255.0
        linear = np.where(
            srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4
        )
        return (
            0.2126 * linear[..., 0] + 0.7152 * linear[..., 1] + 0.0722 * linear[..., 2]
        )

    composite = np.asarray(over(frame, card)).astype(np.float64)
    behind = luminance(composite[ring])
    front = float(np.median(luminance(rgba[:, :, :3][ink])))

    def ratio(background: float) -> float:
        high, low = max(front, background), min(front, background)
        return (high + 0.05) / (low + 0.05)

    return ratio(float(behind.max())), ratio(float(np.median(behind)))


def describe() -> dict[str, object]:
    """Everything this module claims, as numbers, for the report and the tests."""
    hue = overlays.MARBLE_HUES[WINNER_INDEX]
    band_worst = (127, 127, 127)
    return {
        "winner": WINNER_INDEX,
        "label": winner_label(WINNER_INDEX),
        "hue": hue,
        "hex": "#%02X%02X%02X" % tuple(hue),
        "from_place": ordinal(WINNER_FROM),
        "band": PAYOFF_BAND,
        "band_height": PAYOFF_BAND[1] - PAYOFF_BAND[0],
        "warm_white_on_band": round(contrast_ratio(WARM_WHITE, band_worst), 2),
        "hue_on_band": round(contrast_ratio(hue, band_worst), 2),
        "warm_white_on_hue": round(contrast_ratio(WARM_WHITE, hue), 2),
        "visible": WINNER_VISIBLE,
        "schedule": schedule(),
    }


def _hue_angle(rgb: Sequence[int]) -> float:
    """Degrees, for the naming check in the tests."""
    red, green, blue = (value / 255.0 for value in rgb[:3])
    high, low = max(red, green, blue), min(red, green, blue)
    spread = high - low
    if spread < 1e-9:
        return 0.0
    if high == red:
        angle = ((green - blue) / spread) % 6.0
    elif high == green:
        angle = ((blue - red) / spread) + 2.0
    else:
        angle = ((red - green) / spread) + 4.0
    return math.fmod(angle * 60.0 + 360.0, 360.0)

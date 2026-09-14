"""What the V24 payoff card has to be true of.

The card makes one claim to a stranger - *this colour won, from sixth* - and
there are exactly two ways to get it wrong that a reader would never catch:
name the wrong colour, or put the words somewhere they cannot be read. So the
suite is about those two and about the timing that joins them.

The payoff's own reason for existing is a measurement that lives outside this
file, in `tools/sloped_v24_payoff.py --stage visibility`, because it needs the
rendered master: the winner is behind the finish gantry for 1.400 s after it
crosses, and both of V22.1's winner marks are inside that. What *is* pinned
here is the consequence - `WINNER_VISIBLE`, and the schedule built from it -
so that a later edit cannot quietly put the ring back on a hidden marble.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from sloped import overlays, v24_payoff

PALETTE = Path("godot/assets/marble_machine/lab_palette.gd")
REPLAY = Path("output/sloped_race_v1/race_5432.json")


# --- the winner, and its name ----------------------------------------------


def test_the_colour_names_cover_the_whole_field():
    assert len(v24_payoff.COLOUR_NAMES) == len(overlays.MARBLE_HUES)
    assert len(set(v24_payoff.COLOUR_NAMES)) == len(v24_payoff.COLOUR_NAMES)


def test_every_name_matches_the_hue_it_is_given_to():
    """A label is only useful if it is the word a viewer would have used.

    Checked as an angle rather than by eye: each name carries the hue range it
    is allowed to sit in, and a palette edit that slid a racer out of its own
    name would fail here rather than ship a card that says BLUE over a green
    ball.
    """
    allowed = {
        "RED": (335.0, 25.0),
        "ORANGE": (15.0, 45.0),
        "YELLOW": (40.0, 70.0),
        "GREEN": (80.0, 165.0),
        "TEAL": (165.0, 200.0),
        "BLUE": (200.0, 255.0),
        "PURPLE": (255.0, 305.0),
        "PINK": (305.0, 350.0),
    }
    for index, name in enumerate(v24_payoff.COLOUR_NAMES):
        angle = v24_payoff._hue_angle(overlays.MARBLE_HUES[index])
        low, high = allowed[name]
        if low > high:  # the red wrap, 335..360..25
            assert angle >= low or angle <= high, (name, angle)
        else:
            assert low <= angle <= high, (name, angle)


def test_the_hue_table_is_still_the_palettes_own():
    """`COLOUR_NAMES` is indexed against `MARBLE_HUES`, which is a copy."""
    text = PALETTE.read_text(encoding="utf-8")
    block = text.split("const MARBLE_COLOURS := [", 1)[1].split("]", 1)[0]
    hexes = re.findall(r'"#([0-9A-Fa-f]{6})"', block)
    assert len(hexes) == len(overlays.MARBLE_HUES)
    for value, hue in zip(hexes, overlays.MARBLE_HUES):
        assert tuple(int(value[i:i + 2], 16) for i in (0, 2, 4)) == tuple(hue)


def test_the_winner_is_purple_and_it_is_not_red():
    """The one fact the whole card rests on."""
    assert v24_payoff.WINNER_INDEX == 5
    assert v24_payoff.winner_label(v24_payoff.WINNER_INDEX) == "PURPLE"
    assert overlays.MARBLE_HUES[v24_payoff.WINNER_INDEX] == (142, 63, 212)
    assert v24_payoff.winner_label(v24_payoff.WINNER_INDEX) != "RED"


@pytest.mark.skipif(not REPLAY.is_file(), reason="the locked replay is not built")
def test_the_pinned_winner_is_the_replays_own():
    """And it is checked against the replay the film actually ships.

    `run_race(seed=5432)` on the *default* machine returns a different winner
    entirely - marble 7 - because the default course has no fork. This reads
    the delivered replay rather than re-running anything, so there is no
    machine to get wrong.
    """
    replay = json.loads(REPLAY.read_text(encoding="utf-8"))
    finishes = sorted(
        (event for event in replay["events"] if event["kind"] == "finish_line"),
        key=lambda event: int(event["order"]),
    )
    assert [int(event["id"]) for event in finishes] == [5, 2, 7, 4, 1, 6, 3, 0]
    assert int(finishes[0]["id"]) == v24_payoff.WINNER_INDEX
    assert float(finishes[0]["t"]) == pytest.approx(20.85, abs=1e-3)


def test_ordinals():
    assert v24_payoff.ordinal(1) == "1ST"
    assert v24_payoff.ordinal(2) == "2ND"
    assert v24_payoff.ordinal(3) == "3RD"
    assert v24_payoff.ordinal(4) == "4TH"
    assert v24_payoff.ordinal(6) == "6TH"
    assert v24_payoff.ordinal(11) == "11TH"
    assert v24_payoff.ordinal(21) == "21ST"
    with pytest.raises(ValueError):
        v24_payoff.ordinal(0)


# --- the card fits where it was measured to fit -----------------------------


@pytest.mark.parametrize("style", sorted(v24_payoff.STYLES))
def test_every_style_stays_inside_the_measured_band(style):
    """The band is `y 297..548`, and it is the only clear one in the tail.

    Anything that drifts out of it is over the pale mountain above or the
    machine's gold top rail below, both of which run past luma 220.
    """
    card = v24_payoff.build(style)
    low, high = v24_payoff.PAYOFF_BAND
    assert low <= card.box[1], (style, card.box)
    assert card.box[3] <= high, (style, card.box)


@pytest.mark.parametrize("style", sorted(v24_payoff.STYLES))
def test_every_style_keeps_the_gutter(style):
    """`overlays.pick_one` learned this the hard way; it is not relearned here."""
    card = v24_payoff.build(style)
    assert card.box[0] >= v24_payoff.GUTTER - 12, (style, card.box)
    assert card.box[2] <= overlays.WIDTH - v24_payoff.GUTTER + 12, (style, card.box)


@pytest.mark.parametrize("style", sorted(v24_payoff.STYLES))
def test_every_style_says_the_colour_and_the_comeback(style):
    """Both facts are present, and the card is not blank."""
    card = v24_payoff.build(style)
    assert card.label == "PURPLE"
    assert card.from_place == 6
    solid = np.asarray(card.image)[:, :, 3] > 200
    assert solid.sum() > 20000, (style, int(solid.sum()))


def test_a_longer_name_still_fits():
    """`ORANGE` and `YELLOW` are the widest labels the field can produce."""
    for winner in range(len(overlays.MARBLE_HUES)):
        card = v24_payoff.build("plate", winner=winner)
        assert card.box[0] >= v24_payoff.GUTTER - 12, (winner, card.box)
        assert card.box[2] <= overlays.WIDTH - v24_payoff.GUTTER + 12, (
            winner, card.box
        )
        low, high = v24_payoff.PAYOFF_BAND
        assert low <= card.box[1] and card.box[3] <= high, (winner, card.box)


# --- the contrast finding ---------------------------------------------------


def test_the_winners_own_hue_cannot_carry_the_words():
    """The measurement the design is built on, kept as a test.

    Purple's relative luminance and the band's are the same to within a few
    per cent, so a purple word on the band is invisible. If a palette change
    ever made this false, `tint` would stop being the weak option and the
    recommendation in the report would need revisiting - so it fails loudly
    rather than silently becoming wrong.
    """
    band = (127, 127, 127)
    hue = overlays.MARBLE_HUES[v24_payoff.WINNER_INDEX]
    assert v24_payoff.contrast_ratio(hue, band) < 1.6
    assert v24_payoff.contrast_ratio(overlays.WARM_WHITE, band) > 3.5


def test_warm_white_on_the_hue_is_the_way_round_that_works():
    """Which is why `plate` reverses out of the colour instead of tinting it."""
    hue = overlays.MARBLE_HUES[v24_payoff.WINNER_INDEX]
    assert v24_payoff.contrast_ratio(overlays.WARM_WHITE, hue) >= 4.5


def test_the_plate_states_the_colour_far_harder_than_the_shipped_dot():
    """The point of the pass, as an area."""
    hue = overlays.MARBLE_HUES[v24_payoff.WINNER_INDEX]
    shipped = v24_payoff._colour_area(overlays.end_fact(accent=hue), hue)
    plate = v24_payoff.build("plate").colour_pixels
    chip = v24_payoff.build("chip").colour_pixels
    assert plate > 20 * shipped, (plate, shipped)
    assert plate > chip


def test_measured_contrast_reads_the_frame_rather_than_the_type():
    """A guard on the instrument, not on the card.

    Three earlier versions of `measured_contrast` reported the same number for
    every frame, because each was accidentally measuring the card against
    itself - once against its own drop shadow, once against its own
    antialiasing. A bright frame and a dark frame must not score alike.
    """
    card = v24_payoff.build("plate").image
    dark = Image.new("RGB", (overlays.WIDTH, overlays.HEIGHT), (20, 16, 14))
    bright = Image.new("RGB", (overlays.WIDTH, overlays.HEIGHT), (245, 245, 245))
    dark_worst, _ = v24_payoff.measured_contrast(dark, card)
    bright_worst, _ = v24_payoff.measured_contrast(bright, card)
    assert dark_worst > bright_worst * 2.0, (dark_worst, bright_worst)


# --- the timing -------------------------------------------------------------


def test_the_ring_lands_where_the_winner_actually_is():
    """V22.1's ring gets 0.017 s of a visible marble; this one gets all of it."""
    plan = v24_payoff.schedule()
    low, high = plan["ring"]
    first = v24_payoff.WINNER_VISIBLE[0]
    assert low >= first[0] - 1e-9
    assert plan["ring_on_visible_winner"] >= 0.20


def test_the_card_is_still_up_when_the_winner_comes_back_out():
    """The beat is not just a delay, it is what buys the reunion.

    The winner is behind the gantry for the whole of the brief's 0.8-1.5 s
    band, so the card cannot point at it. It can still be on screen when the
    marble walks back out at 24.517, and that is where the colour on the card
    and the ball in the picture finally meet.
    """
    plan = v24_payoff.schedule()
    assert plan["card_over_visible_winner"] > 1.0


def test_the_card_never_covers_the_crossing():
    plan = v24_payoff.schedule()
    assert plan["card"][0] >= v24_payoff.CROSSING + 0.8 - 1e-9


@pytest.mark.parametrize("beat", (0.8, 1.0, 1.2, 1.5))
def test_the_whole_brief_band_is_accepted(beat):
    plan = v24_payoff.schedule(beat=beat)
    assert plan["card"][0] == pytest.approx(v24_payoff.CROSSING + beat, abs=1 / 60)


@pytest.mark.parametrize("beat", (0.4, 2.0))
def test_a_beat_outside_the_brief_is_refused(beat):
    with pytest.raises(ValueError):
        v24_payoff.schedule(beat=beat)


def test_every_cue_is_on_a_whole_frame():
    """`sloped_short` snaps its ring for this reason; so does this."""
    plan = v24_payoff.schedule()
    for span in (plan["ring"], plan["card"]):
        for value in span:
            assert abs(value * 60 - round(value * 60)) < 1e-6, value


def test_describe_reports_what_the_report_quotes():
    facts = v24_payoff.describe()
    assert facts["label"] == "PURPLE"
    assert facts["hex"] == "#8E3FD4"
    assert facts["from_place"] == "6TH"
    assert facts["band"] == v24_payoff.PAYOFF_BAND


# --- the phone -------------------------------------------------------------


def test_the_card_survives_the_phone():
    """270x480 is the size it is judged at, so it is the size it is checked at.

    Cap height rather than font size: what matters is how tall the letters of
    `WINS` end up in a 480 px frame, and the answer has to be a number a thumb
    can read at arm's length.
    """
    card = v24_payoff.build("plate")
    small = v24_payoff.phone(card.image)
    assert small.size == (270, 480)
    solid = np.asarray(small)[:, :, 3] > 150
    rows = np.nonzero(solid.any(axis=1))[0]
    assert rows.size, "the card vanished at phone size"
    # The whole mark, both lines, inside the band's own quarter-scale bounds.
    assert rows.min() >= v24_payoff.PAYOFF_BAND[0] / 4 - 2
    assert rows.max() <= v24_payoff.PAYOFF_BAND[1] / 4 + 2
    # And the headline's own band stands at least 32 px of a 480 px frame.
    # Measured, the three styles give 38 to 43; an 18 px floor, which is what
    # this asserted first, would have passed a card half the size it needs to
    # be and told nobody.
    headline = solid[: int(v24_payoff.PAYOFF_BAND[1] / 4) - 12]
    tall = np.nonzero(headline.any(axis=1))[0]
    assert tall.max() - tall.min() >= 32, tall.max() - tall.min()

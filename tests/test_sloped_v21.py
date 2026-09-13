"""V21 is the three passes in one film. These pin the joins between them.

The three passes were developed apart and each is tested on its own ground:
`test_sloped_retention` owns the cut, `test_sloped_readability` the lenses,
`test_sloped_contrast` the palette. Nothing in any of them could catch the two
mistakes that only exist once they are combined -

* the retention cut applied to the **wrong master**, so the delivered film has
  V21.1's timing and V19's picture and nobody notices because every number in
  the QC report is right;
* a payoff mark that was measured in the code and never in the pixels.

So these are about the wiring and the marks, and they are deliberately few.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sloped import cameras, overlays
from tools.sloped_short import EDITIONS, MASTER_V19, MASTER_V21, WINNER_SECONDS

PALETTE = ROOT / "godot" / "assets" / "marble_machine" / "lab_palette.gd"


# --- which master each edition is cut from ---------------------------------


def test_the_delivered_edition_is_cut_from_the_integrated_master():
    """The whole point of the integration, in one assertion."""
    assert EDITIONS["v21"]["master"] == MASTER_V21
    assert MASTER_V21.endswith("real_race_v21_master.mp4")


def test_the_earlier_editions_still_rebuild_from_v19():
    """V20 and the retention pass's own proof are not to move."""
    assert EDITIONS["v20"]["master"] == MASTER_V19
    assert EDITIONS["v211"]["master"] == MASTER_V19
    assert MASTER_V19.endswith("real_race_v19.mp4")


def test_the_masters_are_different_files():
    assert MASTER_V19 != MASTER_V21


def test_the_retention_cut_is_the_same_cut_on_both_masters():
    """Same frame numbers, because both masters run on the same edit map."""
    assert EDITIONS["v211"]["cuts"] == EDITIONS["v21"]["cuts"] == ((49, 133),)
    assert EDITIONS["v20"]["cuts"] == ()


def test_no_two_editions_write_the_same_file():
    paths = [EDITIONS[name][key] for name in EDITIONS for key in ("video", "visual")]
    assert len(paths) == len(set(paths))


def test_the_integrated_master_uses_the_v212_lenses_over_v19s_windows():
    """The camera edition the master must be rendered with, and its contract.

    The retention cut names master frames 49 and 133, which are only the right
    frames if the master's windows are V19's. V21.2 changed the lenses and kept
    the windows; this is that promise, stated where the integration can see it.
    """
    assert "v212" in cameras.EDITS
    assert _windows(cameras.EDITS["v212"]) == _windows(cameras.EDITS["v19"])


def _windows(plan):
    """A plan's `(cut, from, to)` list, without the lens settings."""
    return [(entry[0], float(entry[1]), float(entry[2])) for entry in plan]


# --- the end card ----------------------------------------------------------


def test_the_hue_table_is_the_palettes_own():
    """`MARBLE_HUES` is a copy, so it is checked against the original."""
    text = PALETTE.read_text(encoding="utf-8")
    block = text.split("const MARBLE_COLOURS := [", 1)[1].split("]", 1)[0]
    hexes = re.findall(r'"#([0-9A-Fa-f]{6})"', block)
    assert len(hexes) == len(overlays.MARBLE_HUES)
    for value, hue in zip(hexes, overlays.MARBLE_HUES):
        assert tuple(int(value[i:i + 2], 16) for i in (0, 2, 4)) == tuple(hue)


def test_the_end_card_carries_the_winning_marbles_colour():
    """Seed 5432's winner is marble 5, and the ball on the card is its purple."""
    assert overlays.WINNER_HUE == overlays.MARBLE_HUES[5]
    card = np.asarray(overlays.end_fact().convert("RGBA")).astype(int)
    solid = card[..., 3] > 200
    hue = np.array(overlays.WINNER_HUE)
    close = (np.abs(card[..., :3] - hue).sum(axis=-1) < 40) & solid
    assert close.sum() > 400, close.sum()


def test_the_end_card_is_otherwise_the_machines_own_neutrals():
    """One coloured thing on the card, and it is the ball."""
    card = np.asarray(overlays.end_fact().convert("RGBA")).astype(int)
    solid = card[..., 3] > 200
    spread = card[..., :3].max(axis=-1) - card[..., :3].min(axis=-1)
    coloured = (spread > 40) & solid
    # The ball plus its rim, and nothing across the rest of the line.
    columns = np.where(coloured.any(axis=0))[0]
    assert columns.size and columns.max() - columns.min() < 130


def test_the_result_is_set_larger_than_the_starting_position():
    """The hierarchy the V21 card exists for, measured off the drawn glyphs."""
    tall = _cap_height(overlays.end_fact(before="8", after="8"))
    assert tall is not None
    left, right = tall
    assert right > left * 1.15, (left, right)


def _cap_height(card: Image.Image):
    """The height of the leftmost and the rightmost solid glyph on the card."""
    solid = np.asarray(card.convert("RGBA"))[..., 3] > 200
    columns = np.where(solid.any(axis=0))[0]
    if columns.size == 0:
        return None
    runs = np.split(columns, np.where(np.diff(columns) > 8)[0] + 1)
    out = []
    for group in (runs[0], runs[-1]):
        rows = np.where(solid[:, group].any(axis=1))[0]
        out.append(int(rows.max() - rows.min()))
    return out[0], out[1]


def test_the_end_card_keeps_its_gutter():
    """A wider card than V20's, and still off both edges of a phone frame."""
    box = overlays.end_fact().getbbox()
    assert box[0] >= 0.07 * overlays.WIDTH
    assert box[2] <= 0.93 * overlays.WIDTH


def test_the_letterforms_have_an_opaque_edge_around_them():
    """The fix for "1ST" landing on a black chequer tile.

    Graphite letters need something light behind them, and half the finish deck
    is a dark tile - so the light has to be *opaque* where the glyph ends
    rather than a falloff that is already half gone by the time it clears the
    stroke. Measured three pixels out from every dark pixel on the card: that
    band is the plate, and it has to be near solid.
    """
    card = np.asarray(overlays.end_fact().convert("RGBA")).astype(int)
    alpha = card[..., 3]
    dark = (card[..., :3].sum(axis=-1) < 220) & (alpha > 200)
    assert dark.sum() > 2000
    grown = dark.copy()
    for shift in range(1, 4):
        grown |= np.roll(dark, shift, axis=0) | np.roll(dark, -shift, axis=0)
        grown |= np.roll(dark, shift, axis=1) | np.roll(dark, -shift, axis=1)
    edge = grown & ~dark
    band = alpha[edge]
    assert float(band.mean()) > 235.0, float(band.mean())
    assert float((band >= 240).mean()) > 0.65, float((band >= 240).mean())


# --- the winner's mark -----------------------------------------------------


def test_the_mark_opens_on_the_frame_it_is_placed_on():
    """The flash exists, and it exists on the first frame of the mark.

    V20 returned an empty image at phase 0 because the ring's own envelope is
    zero at both ends. The flash is the part that has to land *with* the sound,
    so the opening frame cannot be blank.
    """
    opening = overlays.winner_ring(540, 900, 42, 0.0)
    assert opening.getbbox() is not None
    alpha = np.asarray(opening)[..., 3]
    assert int(alpha.max()) > 180


def test_the_flash_is_bright_enough_to_see_and_short_enough_not_to_sit():
    """Measured on the pixels: strong over the ball, gone within seven frames."""
    def over_ball(phase: float) -> float:
        image = np.asarray(overlays.winner_ring(540, 900, 42, phase)).astype(float)
        patch = image[880:920, 520:560]
        return float((patch[..., 3] / 255.0 * patch[..., :3].mean(axis=-1)).mean())

    assert over_ball(0.0) > 120.0, over_ball(0.0)
    # 42 frames of mark, so phase 0.167 is seven frames in.
    assert over_ball(0.167) < 0.35 * over_ball(0.0)


def test_the_mark_stays_close_to_the_marble():
    """Nothing in the payoff covers the deck, the gantry or the other racers."""
    for phase in (0.0, 0.1, 0.3, 0.6, 0.9):
        image = overlays.winner_ring(540, 900, 42, phase)
        box = image.getbbox()
        if box is None:
            continue
        # The label runs to the right of the ring by design; the mark itself is
        # what has to stay near the ball.
        assert 540 - box[0] < 42 * 4.0, (phase, box)
        assert box[1] > 900 - 42 * 4.0 and box[3] < 900 + 42 * 4.0, (phase, box)


def test_the_mark_is_still_a_pulse_rather_than_a_lock_on():
    """It grows, it fades, and it is over well before the dead heat."""
    assert 0.5 <= WINNER_SECONDS <= 0.8
    early = np.asarray(overlays.winner_ring(540, 900, 42, 0.25))[..., 3].sum()
    late = np.asarray(overlays.winner_ring(540, 900, 42, 0.95))[..., 3].sum()
    assert late < early
    assert overlays.winner_ring(540, 900, 42, 1.0).getbbox() is None


def test_the_glow_is_gone_before_the_mark_is():
    """The lift is an arrival cue, not a colour wash over the finish."""
    def gold(phase: float) -> int:
        image = np.asarray(overlays.winner_ring(540, 900, 42, phase)).astype(int)
        ring = image[820:980, 460:620]
        return int(((ring[..., 0] > 200) & (ring[..., 2] < 170) & (ring[..., 3] > 30)).sum())

    assert gold(0.05) > gold(0.55)


@pytest.mark.parametrize("marble", range(8))
def test_any_racer_can_be_the_one_on_the_card(marble):
    """The card is built from the replay's winner, so every hue has to work."""
    card = overlays.end_fact(accent=overlays.MARBLE_HUES[marble])
    box = card.getbbox()
    assert box is not None
    assert box[0] >= 0.07 * overlays.WIDTH and box[2] <= 0.93 * overlays.WIDTH

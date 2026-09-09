"""The roll's slew limit: the constraint, the pocket it removes, and both trees.

A limited roll exists in two places - `sloped.course.BANK_SLEWS` for the
collider and `course_machine.gd`'s own table for the drawn mesh - and a roll the
physics has and the render does not is one a viewer watches a marble corner on
the wrong surface. So the last tests here parse the GDScript and compare, the
same way `test_sloped_guards.py` does for the rail.

The rest pins the reason it exists. leg2's inflection unwinds its roll about
five degrees a sample against a 10% fall, which lifts the outside of the channel
faster than the centreline drops and leaves a closed pocket there - so the
surface runs *uphill along the run* for anything riding wide while a marble on
the centreline goes downhill throughout. `sloped.track._slewed_bank` carries the
measurement, and the two counter-intuitive results: that a margin of 1.0 is the
best setting rather than the weakest, and that holding the roll instead only
moves the pocket downstream.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import pytest

from sloped import layout
from sloped.course import BANK_SLEWS, sloped_course
from sloped.track import TrackRun, _slewed_bank

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "godot/assets/marble_machine/course/course_machine.gd"
TRACK = ROOT / "godot/assets/marble_machine/v2/v2_track.gd"

# Lateral fractions of the half width. 0.0 is the cradle bottom, which was never
# trapped; the traced racers sat between 0.55 and 0.66.
FRACTIONS = (0.0, 0.4, 0.55, 0.6, 0.7, 0.8, 0.95)


def _deepest_climb(run, fraction: float) -> float:
    """The deepest climb from a local minimum to a later peak, along the run."""
    across = fraction * layout.CHANNEL_HALF
    low = None
    worst = 0.0
    for index in range(len(run.sim_path)):
        height = run.surface_point(index, across)[1]
        low = height if low is None else min(low, height)
        worst = max(worst, height - low)
    return worst


def _flat(count: int, drop: float):
    """A straight path falling `drop` a sample, for testing the rule alone."""
    return [(0.0, -drop * index, 0.0) for index in range(count)]


@pytest.fixture(scope="module")
def authored():
    """leg2 as drawn, with no limit, to measure the defect against."""
    return TrackRun("leg2")


@pytest.fixture(scope="module")
def limited():
    return sloped_course(routes="blue").runs["leg2"]


# --- the constraint -------------------------------------------------------


def test_a_zero_margin_changes_nothing():
    banks = [0.5, 0.4, 0.3]
    assert _slewed_bank(banks, _flat(3, 0.1), 0, 3, 0.0, 0.94) == banks


def test_a_roll_the_drop_can_pay_for_is_left_alone():
    """A generous drop means the authored curve already satisfies the rule."""
    banks = [0.30, 0.25, 0.20, 0.15]
    out = _slewed_bank(banks, _flat(4, 10.0), 0, 4, 1.0, 0.94)
    assert out == pytest.approx(banks)


def test_neither_edge_ever_rises_within_the_window():
    """The property the whole thing exists for, checked directly."""
    banks = [math.radians(a) for a in (20, 14, 6, -2, -6, -4, 0, 3)]
    path = _flat(len(banks), 0.06)
    half = 0.94
    out = _slewed_bank(banks, path, 0, len(banks), 1.0, half)
    for index in range(len(out) - 1):
        for side in (+half, -half):
            here = path[index][1] + side * math.sin(out[index])
            there = path[index + 1][1] + side * math.sin(out[index + 1])
            assert there <= here + 1e-12, f"edge {side:+.2f} rises at sample {index}"


def test_the_limit_is_on_the_signed_sine_so_a_sign_flip_is_bounded():
    """The first attempt at this tracked the magnitude and did nothing, because
    at leg2[102] the authored roll crosses zero and a magnitude limit permits
    the flip - which lifts the old low edge by the whole of it."""
    banks = [math.radians(-6.0), math.radians(+6.0)]
    out = _slewed_bank(banks, _flat(2, 0.01), 0, 2, 1.0, 0.94)
    assert abs(math.degrees(out[1])) < 6.0, "the flip was not bounded"
    assert out[1] < 0.0, "it should still be easing off the original side"


def test_the_limit_never_adds_roll_beyond_the_authored_extreme():
    """Why this is available when the bank itself is not: `sloped.contract`
    pins `max(abs(banks))` and nothing about the profile between."""
    banks = [math.radians(a) for a in (2, 22, 18, 10, 4, 0, -3)]
    for margin in (0.25, 0.5, 1.0, 2.0):
        out = _slewed_bank(banks, _flat(len(banks), 0.05), 0, len(banks), margin, 0.94)
        assert max(abs(v) for v in out) <= max(abs(v) for v in banks) + 1e-12


def test_the_window_constrains_the_samples_after_first_up_to_last():
    """The convention: `first` is the roll the limit starts *from*, so the
    samples it can change are `first + 1` through `last` inclusive."""
    banks = [math.radians(a) for a in (20, 10, 0, -5, 4, 9, 14)]
    out = _slewed_bank(banks, _flat(len(banks), 0.02), 2, 4, 1.0, 0.94)
    assert out[:3] == pytest.approx(banks[:3]), "nothing up to `first` moves"
    assert out[3] != pytest.approx(banks[3]), "`first + 1` is constrained"
    assert out[4] != pytest.approx(banks[4]), "`last` is constrained"
    assert out[5:] == pytest.approx(banks[5:]), "nothing past `last` moves"


def test_a_run_without_a_limit_is_untouched():
    assert TrackRun("leg1").bank_slew is None


# --- the pocket, on the built run -----------------------------------------


def test_the_authored_run_has_a_pocket_on_the_outside(authored):
    """The defect, so the fix has something to be a fix of."""
    assert _deepest_climb(authored, 0.0) == pytest.approx(0.0, abs=1e-9)
    assert _deepest_climb(authored, 0.6) > 0.06
    assert _deepest_climb(authored, 0.95) > 0.24


def test_the_pocket_traps_only_marbles_riding_wide(authored):
    for fraction in (0.55, 0.6, 0.7, 0.8, 0.95):
        assert _deepest_climb(authored, fraction) > 0.04, fraction
    for fraction in (0.0, 0.4):
        assert _deepest_climb(authored, fraction) == pytest.approx(0.0, abs=1e-9)


def test_the_limit_removes_the_pocket_at_every_fraction(limited, authored):
    """Not "mostly": the run descends monotonically at every lateral position.

    That is the point of letting the limit rejoin the authored curve on its own
    rather than truncating the window. Cut short at sample 108 it left a
    residue - 0.0020 at a fraction of 0.6, 0.0336 at the rail - and a 0.95
    degree step in the roll where it snapped back.
    """
    for fraction in FRACTIONS:
        assert _deepest_climb(limited, fraction) == pytest.approx(0.0, abs=1e-9), fraction
    assert _deepest_climb(authored, 0.95) > 0.24, "the defect is still there to fix"


def test_the_limit_leaves_the_contract_extreme_alone(limited, authored):
    mine = max(abs(math.degrees(v)) for v in limited.banks)
    theirs = max(abs(math.degrees(v)) for v in authored.banks)
    assert mine == pytest.approx(theirs, abs=1e-9)
    assert mine == pytest.approx(float(layout.run("leg2")["bank_max"]), abs=0.05)


def test_the_limit_rejoins_the_authored_curve_inside_its_window(limited, authored):
    moved = [
        index
        for index, (mine, theirs) in enumerate(zip(limited.banks, authored.banks))
        if abs(mine - theirs) > 1e-9
    ]
    first, last, _margin = BANK_SLEWS["leg2"]
    assert moved, "the limit should be doing something"
    assert min(moved) > first, "the roll at `first` is the one it starts from"
    assert max(moved) < last, (
        "the window has to be wide enough that the limit rejoins the authored "
        "curve on its own - a window that ends while it is still deviating puts "
        "a step in the roll there"
    )


def test_the_course_installs_the_limit_on_leg2_only(limited):
    assert limited.bank_slew == BANK_SLEWS["leg2"]
    for name, run in sloped_course(routes="blue").runs.items():
        if name in BANK_SLEWS:
            continue
        assert getattr(run, "bank_slew", None) is None, name


# --- both trees carry the same table --------------------------------------


def _gd_table(source: str, name: str) -> dict[str, list[float]]:
    block = re.search(rf"const {name} := \{{(.*?)\n\}}", source, re.S)
    assert block, f"{name} not found in the GDScript"
    return {
        key: [float(v) for v in values.split(",") if v.strip()]
        for key, values in re.findall(r'"(\w+)"\s*:\s*\[([^\]]*)\]', block.group(1))
    }


def test_the_render_carries_the_same_table():
    drawn = _gd_table(MACHINE.read_text(encoding="utf-8"), "BANK_SLEWS")
    assert set(drawn) == set(BANK_SLEWS)
    for name, window in BANK_SLEWS.items():
        assert drawn[name] == [float(v) for v in window], name


def test_the_render_passes_the_table_to_the_track_builder():
    source = MACHINE.read_text(encoding="utf-8")
    assert '"bank_slew": BANK_SLEWS.get(name, []),' in source


def test_the_track_builder_limits_the_roll_before_it_publishes_it():
    """Order matters: the camera rig and `course_machine.gd` read a run's roll
    from the `banks` meta, so a limit applied after `set_meta` is invisible."""
    source = TRACK.read_text(encoding="utf-8")
    assert "static func slewed_bank" in source
    applied = source.index("banks = slewed_bank(banks, path,")
    published = source.index('root.set_meta("banks", banks)')
    assert applied < published


def test_the_gdscript_uses_the_same_signed_sine_rule():
    source = TRACK.read_text(encoding="utf-8")
    body = source[
        source.index("static func slewed_bank") : source.index("static func guard_rise")
    ]
    assert "sin(float(out[index]))" in body, "no longer reads the running roll"
    assert "sin(float(banks[index + 1]))" in body, "no longer reads the authored roll"
    assert "max(here - cap, min(here + cap, want))" in body, "the clamp changed"
    assert "CHANNEL_HALF * profile_scale" in body, "the half width changed"

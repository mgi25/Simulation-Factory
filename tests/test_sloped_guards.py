"""The local rail boosts: the window's shape, and that both trees carry it.

A raised rail exists in two places - `sloped.course.GUARD_BOOSTS` for the
collider and `course_machine.gd`'s own table for the drawn mesh - and a rail the
physics has and the render does not is one a viewer watches a marble bounce off
nothing on. So the last test here parses the GDScript constant and compares it
number for number. Crude on purpose: the alternative is a third file that both
read, and neither Python nor Godot can import the other's.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import pytest

from sloped import layout
from sloped.course import GUARD_BOOSTS
from sloped.scale import SIM_TO_LAYOUT, to_sim
from sloped.track import TrackRun

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "godot/assets/marble_machine/course/course_machine.gd"
TRACK = ROOT / "godot/assets/marble_machine/v2/v2_track.gd"


# --- the window ----------------------------------------------------------


@pytest.fixture(scope="module")
def boosted() -> TrackRun:
    return TrackRun("launch", guard_boost=(0.50, 12, 24, 70, 84))


def test_a_run_without_a_boost_is_untouched():
    plain = TrackRun("launch")
    assert plain.guard_boost is None
    assert plain.guard_extra(40) == 0.0
    assert plain.containment_at(40) == plain.containment
    assert plain.section_at(40) == plain.section


def test_the_window_is_flat_then_eased_then_flat(boosted):
    extra, a, b, c, d = boosted.guard_boost
    assert boosted.guard_extra(0) == 0.0
    assert boosted.guard_extra(a) == 0.0
    assert boosted.guard_extra(b) == pytest.approx(extra)
    assert boosted.guard_extra((b + c) // 2) == pytest.approx(extra)
    assert boosted.guard_extra(c) == pytest.approx(extra)
    assert boosted.guard_extra(d) == 0.0
    assert boosted.guard_extra(117) == 0.0
    # Halfway up the ramp is half the height, because the easing is symmetric.
    assert boosted.guard_extra((a + b) // 2) == pytest.approx(0.5 * extra, abs=0.02)


def test_the_rail_top_never_steps(boosted):
    """A step in a rail's top is a kerb a marble riding the wall trips on."""
    heights = [boosted.guard_extra(index) for index in range(len(boosted.path))]
    worst = max(
        abs(heights[index + 1] - heights[index]) for index in range(len(heights) - 1)
    )
    # One sample of a smoothstep over a twelve-sample ramp: 1.5 times the mean
    # rise, and the mean is extra/12.
    assert worst <= 1.6 * boosted.guard_boost[0] / 12.0


def test_only_the_rail_moves_and_only_upward(boosted):
    """The lip and the cradle are the running surface and are left alone."""
    plain = TrackRun("launch")
    before = plain.section_at(40)
    after = boosted.section_at(40)
    assert len(after) == len(before)
    extra = boosted.guard_extra(40)
    crown = layout.LIP_CROWN * boosted.scale
    for (a0, u0), (a1, u1) in zip(before, after):
        assert a1 == pytest.approx(a0)              # nothing moves sideways
        if u0 > crown:
            assert u1 == pytest.approx(u0 + extra)
        else:
            assert u1 == pytest.approx(u0)
    assert min(u for _a, u in after) == pytest.approx(min(u for _a, u in before))


def test_the_containment_check_sees_the_same_rail_the_collider_has(boosted):
    """The half of the repair that is not geometry.

    A containment check reading the scalar `containment` while the collider
    carried the boost would book a contained marble as an escape, and the
    escape histogram would then say the repair had done nothing.
    """
    for index in (0, 12, 24, 40, 70, 84, 117):
        expected = boosted.containment + to_sim(boosted.guard_extra(index))
        assert boosted.containment_at(index) == pytest.approx(expected)
    assert boosted.containment_at(40) > boosted.containment
    assert boosted.containment_at(0) == boosted.containment


def test_the_boost_is_in_the_run_metadata():
    run = TrackRun("leg1", guard_boost=GUARD_BOOSTS["leg1"])
    assert run.describe()["guard_boost"] == list(GUARD_BOOSTS["leg1"])
    assert TrackRun("leg3").describe()["guard_boost"] is None


# --- the two trees agree -------------------------------------------------


def _gdscript_boosts() -> dict[str, list[float]]:
    text = MACHINE.read_text(encoding="utf-8")
    block = re.search(r"const GUARD_BOOSTS := \{(.*?)\n\}", text, re.S)
    assert block, "course_machine.gd has no GUARD_BOOSTS table"
    out: dict[str, list[float]] = {}
    for name, values in re.findall(r'"(\w+)":\s*\[([^\]]+)\]', block.group(1)):
        out[name] = [float(v.strip()) for v in values.split(",")]
    return out


def test_the_render_and_the_collider_carry_the_same_rails():
    drawn = _gdscript_boosts()
    assert set(drawn) == set(GUARD_BOOSTS)
    for name, window in GUARD_BOOSTS.items():
        assert drawn[name] == pytest.approx([float(v) for v in window]), name


def test_the_asset_applies_the_boost_to_its_guard_sweep():
    """That the option is read, not merely accepted.

    Parsed rather than executed because there is no Godot in a test run, so
    what is checked is that the three things that make the option work are all
    present: the table is passed, the per-sample rise is computed, and the
    guard sections are the ones raised.
    """
    machine = MACHINE.read_text(encoding="utf-8")
    assert '"guard_boost": GUARD_BOOSTS.get(name, [])' in machine
    track = TRACK.read_text(encoding="utf-8")
    assert 'options.get("guard_boost", [])' in track
    assert "static func guard_rise(" in track
    assert "_raise_rail(guard_set[0][index]" in track
    # And that it is additive: an existing build with no key gets the authored
    # rail, which is what keeps the earlier labs' committed frames reproducing.
    assert "if not boost.is_empty():" in track


def test_every_boosted_run_is_one_the_escape_trace_named():
    """Four sites, each measured before it was given a rail.

    orange's is V1.15's and it was measured the same way the first three were,
    by `tools/sloped_orange_trace.py` rather than by `sloped_escape_trace.py`:
    the start lab carries the launch and leg1 only, so a lobe's own losses need
    whole races. The reading is the same one - how high the field rides as a
    fraction of the run's own containment - and orange's answer is over 1.0 for
    sixteen consecutive samples.
    """
    assert set(GUARD_BOOSTS) == {"launch", "leg1", "leg2", "orange"}
    for name, (extra, a, b, c, d) in GUARD_BOOSTS.items():
        run = TrackRun(name, spec=None if name != "orange" else dict(layout.run("orange")))
        assert 0 <= a < b < c < d <= len(run.path) - 1, name
        # Tall enough to matter against a 0.26 authored rail, and not so tall
        # that the channel becomes a tube.
        assert 0.2 <= extra <= 0.7, name
        assert extra < layout.CONTAINMENT_TOP - layout.FLOOR_Y, name

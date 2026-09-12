"""The opened walls, and whether the render draws the same ones the physics has.

Section 19 of the V1.15 brief. `sloped.course` opens a rail wherever a marble
is meant to pass through it - leg3's east guard over the fork window, orange's
lead on its west lip, and the sprint, blue's tail and the merge lead inside the
roofed apron - and until `v2_track.wall_factor` existed the render drew a
full-height acrylic rail across every one of them. A wall the physics does not
have is a wall a viewer watches a marble go straight through.

These tests pin three things: that the physics still opens what it says it
does, that the description a renderer reads carries the window, and that the
GDScript that draws it computes the **same numbers** as the Python that
simulates it.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sloped import layout
from sloped.course import (
    BLUE_MERGE_WINDOW,
    FORK_CREST,
    MERGE_GUARD_WINDOW,
    sloped_course,
)
from sloped.track import TrackRun

GODOT_TRACK = ROOT / "godot" / "assets" / "marble_machine" / "v2" / "v2_track.gd"

# The four window shapes the course ships, and the ones
# `godot/scripts/sloped_open_side_check.gd` prints. Kept here rather than
# parsed out of the GDScript, so a change to either file has to be made in both.
PARITY_COUNT = 24
PARITY_CASES = (
    (0.0, -1, 0, 12, 14),
    (1.0, 9, 11, 18, 20, 0.12),
    (-1.0, 3, 5, 9, 11),
    (0.0, 17, 19, 23, 24),
)


def test_every_run_inside_the_apron_has_its_rails_opened():
    """The three runs standing in the roofed apron, and nothing else.

    A rail inside a roofed apron leaves a ledge along its own top, and V1 lost
    319 of its 747 marbles resting on one. The window is therefore a property
    of *being inside the apron*, so the set of runs that carry one is the set
    the apron stands around.
    """
    machine = sloped_course(routes="both")
    runs = machine.runs                                   # type: ignore[attr-defined]
    opened = {name for name, run in runs.items() if run.open_side is not None}
    assert opened == {"final", "blue", "merge_lead", "leg3", "orange_lead"}, opened
    for name in ("final", "blue", "merge_lead"):
        assert runs[name].open_side[0] == 0.0, f"{name} opens one rail, not both"


def test_the_sprints_window_stays_open_until_the_shoulder_has_closed():
    """`final[10]`, as the property rather than as the sample number.

    The apron's rim eases in to the channel's own edge and the sprint's rails
    ease back up, and V1.14 ran both over the same five samples: the west
    shoulder narrowed below a marble diameter at `final[11]` while the sprint's
    lip was already 0.22 units out of the channel edge, so a marble running
    down the shoulder wedged in the corner between them. 26 of 38 held-out
    non-finishers were found in that corner, at one pose.

    The rule that removes it: **wherever the shoulder is still wide enough to
    hold a marble, the rail beside it must still be open.** Stated that way it
    is checked against the apron's own geometry rather than against a constant.
    """
    from marble3d.units import MARBLE_DIAMETER
    from sloped.scale import to_sim

    machine = sloped_course(routes="both")
    sprint = machine.runs["final"]                        # type: ignore[attr-defined]
    merge = machine.modules["merge"]
    front = to_sim(merge.FRONT)
    worst = None
    for index in range(len(sprint.sim_path)):
        along, _across, _rise = _in_apron(merge, sprint.surface_point(index, 0.0))
        if along < 0.0 or along > front:
            continue
        # The clear shoulder: from the run's own rail foot out to the apron's
        # rim, which is the width a marble on the shoulder actually has.
        guard = to_sim(layout.GUARD_INNER * sprint.scale * sprint.widths[index])
        gutter = merge.rim(along, -1.0) - guard
        if gutter < MARBLE_DIAMETER:
            continue
        factor = sprint.wall_factor(index)
        if worst is None or factor > worst[1]:
            worst = (index, factor, gutter)
    assert worst is not None, "no station has a marble's width of shoulder"
    assert worst[1] <= TrackRun.OPEN_FLOOR + 1e-9, (
        f"final[{worst[0]}] has {worst[2]:.3f} of shoulder - a marble fits - "
        f"but its rail already stands at {worst[1]:.3f} of full height"
    )


def _in_apron(merge, point):
    offset = [point[axis] - merge.origin[axis] for axis in range(3)]
    return (
        sum(offset[axis] * merge.forward[axis] for axis in range(3)),
        sum(offset[axis] * merge.lateral[axis] for axis in range(3)),
        sum(offset[axis] * merge.up[axis] for axis in range(3)),
    )


def test_the_window_reaches_a_renderer_at_all():
    """`describe` carries it, because that is the only thing a renderer reads."""
    machine = sloped_course(routes="both")
    runs = machine.runs                                   # type: ignore[attr-defined]
    assert runs["final"].describe()["open_side"] == list(MERGE_GUARD_WINDOW)
    assert runs["blue"].describe()["open_side"] == list(BLUE_MERGE_WINDOW)
    assert runs["leg3"].describe()["open_side"][-1] == FORK_CREST
    assert runs["launch"].describe()["open_side"] is None


def test_the_godot_track_has_a_wall_factor_at_all():
    """The source-text half of the parity, so a missing file fails loudly."""
    body = GODOT_TRACK.read_text(encoding="utf-8")
    assert "static func wall_factor(" in body
    assert "static func _open_section(" in body
    assert 'options.get("open_side"' in body, "the sweep never reads the window"
    assert "_opened_set(body_set" in body, "the shell's lip is not opened"
    assert "_opened_set(guard_set" in body, "the guard rail is not opened"


def test_the_two_implementations_agree_as_numbers():
    """Run both and compare the factors, the way the bank slew is compared.

    Skipped rather than failed without Godot, the way the rest of the
    render-facing suite is.
    """
    try:
        from tools.render_replay import find_godot
    except ImportError:  # pragma: no cover - the tool moved
        pytest.skip("tools.render_replay is not importable")
    try:
        godot = find_godot(None)
    except Exception:
        pytest.skip("Godot 4 is not available; set $GODOT_BIN to run this")

    done = subprocess.run(
        [godot, "--headless", "--script", "scripts/sloped_open_side_check.gd"],
        cwd=str(ROOT / "godot"),
        capture_output=True,
        text=True,
        timeout=300,
    )
    drawn: dict[str, list[float]] = {}
    for line in done.stdout.splitlines():
        key, sep, values = line.partition("|")
        if sep and key.startswith("["):
            drawn[key] = [float(value) for value in values.split(",")]
    assert drawn, f"the check script printed nothing:\n{done.stdout}\n{done.stderr}"

    for case in PARITY_CASES:
        key = "[" + ", ".join(_gd(value) for value in case) + "]"
        assert key in drawn, f"{key} missing from {sorted(drawn)}"
        run = TrackRun("final", open_side=case)
        wanted = [run.wall_factor(index) for index in range(PARITY_COUNT)]
        for index, (theirs, ours) in enumerate(zip(drawn[key], wanted)):
            assert abs(theirs - ours) < 1e-6, (case, index, theirs, ours)


def _gd(value) -> str:
    """A number as GDScript's `str()` prints it inside an Array.

    GDScript keeps a float's point - `1.0`, `0.12` - and prints an int bare, so
    the key is built rather than JSON-dumped. The first version of this used
    `json.dumps`, which spells the same window `[0.0,-1,0,12,14]` and matched
    nothing.
    """
    if isinstance(value, float):
        return f"{value:g}" if value != int(value) else f"{value:.1f}"
    return str(value)


def test_the_parity_harness_discriminates():
    """A harness that cannot fail is not a check.

    The bank-slew parity found a real 0.99-degree gap in its own harness rather
    than in the code, so this one is asked to disagree on purpose.
    """
    run = TrackRun("final", open_side=(0.0, -1, 0, 12, 14))
    other = TrackRun("final", open_side=(0.0, -1, 0, 9, 14))
    mine = [run.wall_factor(index) for index in range(PARITY_COUNT)]
    theirs = [other.wall_factor(index) for index in range(PARITY_COUNT)]
    assert max(abs(a - b) for a, b in zip(mine, theirs)) > 0.3


def test_the_render_and_the_collider_carry_the_same_windows():
    """`course_machine.gd::OPEN_SIDES` against the course that ships.

    The same shape as `test_the_render_and_the_collider_carry_the_same_rails`
    in `tests/test_sloped_guards.py`, and for the same reason: the two tables
    are written in two languages and nothing but a test keeps them equal.
    """
    body = (
        ROOT / "godot" / "assets" / "marble_machine" / "course" / "course_machine.gd"
    ).read_text(encoding="utf-8")
    assert "const OPEN_SIDES" in body, "the render has no table of opened rails"
    drawn = _gd_table(body, "OPEN_SIDES")
    machine = sloped_course(routes="both")
    runs = machine.runs                                   # type: ignore[attr-defined]
    for name in ("leg3", "blue", "final"):
        window = [float(value) for value in runs[name].open_side]
        assert name in drawn, f"{name} has no entry in OPEN_SIDES"
        assert drawn[name] == pytest.approx(window), (name, drawn[name], window)
    assert '"open_side": (' in body, "the table never reaches Track.build"


def _gd_table(body: str, name: str) -> dict[str, list[float]]:
    """One `const NAME := { "key": [numbers], ... }` block, parsed as numbers.

    Parsed rather than string-matched, because GDScript and Python print the
    same float differently - `1.0` against `1.00` - and a test that fails on
    formatting is a test that gets loosened rather than believed.
    """
    import re

    block = body.split(f"const {name} := {{", 1)[1].split("}", 1)[0]
    out: dict[str, list[float]] = {}
    for key, values in re.findall(r'"([a-z0-9_]+)"\s*:\s*\[([^\]]*)\]', block):
        out[key] = [float(part) for part in values.split(",") if part.strip()]
    return out

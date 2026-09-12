"""Does the render draw the start the physics runs?

Sections 4 and 5 of the V1.17 brief. The start was replaced in V1.8 by
`sloped.trapdoor.ShuffleFloor` - a mixing drum on a louvre trapdoor floor - and
`course_modules.start()` went on drawing V1's fan pod on the authored node,
3.93 layout units below the field. Eight racers hung in mid-air for the first
four seconds of every video shipped since V1.9, and nothing failed.

So these tests exist to make that impossible a second time. They pin three
different things, and the third is the one that actually catches a drift:

* that the contract the renderer eats is the module's own numbers;
* that the GDScript consumes it rather than hard-coding a second layout;
* and that the **replay's own marbles rest on the replay's own floor**, which
  is a statement about the two files a render is made of and needs no renderer
  to check.

## The unit trap, recorded because it cost a session

`ShuffleFloor.describe()["bay_pitch"]` is `to_sim(layout.BAY_PITCH)` = 1.105263
while every other number in that dictionary is in layout units. The render's
`BAY_PITCH` is 0.63. Those are **the same number**, and reading the two side by
side makes the start look like it has a 1.75x pitch error that it has never
had. `test_the_bay_pitch_is_one_number_in_two_units` pins that.
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sloped import layout
from sloped.course import sloped_course
from sloped.scale import SIM_TO_LAYOUT, to_sim
from tools.sloped_start_contract import actuator_parts, contract

MODULES = ROOT / "godot" / "assets" / "marble_machine" / "course" / "course_modules.gd"
MACHINE = ROOT / "godot" / "assets" / "marble_machine" / "course" / "course_machine.gd"
SCENE = ROOT / "godot" / "scripts" / "sloped_race_scene.gd"
REPLAY = ROOT / "output" / "sloped_race_v1" / "race_5432.json"


@pytest.fixture(scope="module")
def built():
    machine = sloped_course(routes="both")
    return machine, machine.modules["start"], contract("both")


def test_the_contract_is_the_modules_own_placement(built):
    """The lift is the defect, so the lift is the first thing pinned."""
    _machine, start, data = built
    assert data["kind"] == "ShuffleFloor"
    assert data["origin"] == pytest.approx([round(v, 6) for v in start.origin])
    assert data["lift"] == pytest.approx(start.lift, abs=1e-6)
    assert data["node"] == pytest.approx([round(v, 6) for v in layout.NODES["start"]])
    # The whole of it: the module stands `lift` above the authored node.
    assert data["origin"][1] - data["node"][1] == pytest.approx(start.lift, abs=1e-6)
    assert start.lift > 3.0, "a start that no longer lifts is a different defect"


def test_the_bay_pitch_is_one_number_in_two_units(built):
    """0.63 layout and 1.105263 simulation are `layout.BAY_PITCH` twice."""
    _machine, start, data = built
    described = start.describe()
    assert data["bay_pitch"] == pytest.approx(layout.BAY_PITCH)
    assert data["bay_pitch_sim"] == pytest.approx(described["bay_pitch"])
    assert to_sim(data["bay_pitch"]) == pytest.approx(data["bay_pitch_sim"], abs=1e-6)
    # And the render's own constant is the layout one, unchanged since V1.
    body = MODULES.read_text(encoding="utf-8")
    assert "const BAY_PITCH := 0.63" in body


def test_the_contract_carries_every_part_the_renderer_draws(built):
    """Thirty kinematic parts, at the sizes the solver was given."""
    _machine, start, data = built
    parts = actuator_parts(start)
    assert set(data["parts"]) == set(parts)
    assert len(parts) == 30
    families = data["families"]
    assert families["paddle"]["count"] == layout.BAYS
    assert families["rotor"]["count"] == start.PADDLES
    assert families["panel"]["count"] == start.PANELS * start.PANEL_SPLITS
    # A rotor blade is the span it sweeps, at the authored height and thickness.
    blade = families["rotor"]["sizes"][0]
    assert blade[0] == pytest.approx(start.TIP_R - start.ROOT_R, abs=1e-6)
    assert blade[1] == pytest.approx(start.PADDLE_HEIGHT, abs=1e-6)
    assert blade[2] == pytest.approx(start.PADDLE_THICK, abs=1e-6)
    # Every slat is one thickness; only the chord differs.
    for size in families["panel"]["sizes"]:
        assert size[1] == pytest.approx(start.PANEL_THICK, abs=1e-6)


def test_the_contract_carries_the_housing(built):
    _machine, start, data = built
    assert data["chamber"]["wall_radius"] == pytest.approx(start.R_WALL)
    assert data["chamber"]["rim_floor"] == pytest.approx(start.rim_floor)
    assert data["chamber"]["centre_z"] == pytest.approx(start.CHAMBER_Z)
    assert data["pan"]["floor"] == pytest.approx(start.pan_floor)
    assert data["pan"]["apron_grade_deg"] == pytest.approx(start.APRON_GRADE)
    assert data["cone"]["lip"] == pytest.approx(start.dish_lip)
    assert data["chute"]["grade_deg"] == pytest.approx(start.CHUTE_GRADE)


def test_the_renderer_consumes_the_contract_rather_than_a_second_layout():
    """The source-text half: the GDScript reads it and draws from it."""
    modules = MODULES.read_text(encoding="utf-8")
    assert "static func shuffle_start(" in modules
    assert "static func shuffle_start_parts(" in modules
    for key in ("bay_x", "rim_floor", "wall_radius", "apron_grade_deg", "exit_local"):
        assert key in modules, f"the renderer never reads {key}"
    machine = MACHINE.read_text(encoding="utf-8")
    assert 'options.get("start_contract"' in machine
    assert "Modules.shuffle_start(palette, contract)" in machine
    scene = SCENE.read_text(encoding="utf-8")
    assert "load_start_contract" in scene
    assert "_move_start_parts" in scene
    # The parts are driven from the replay, not from a release law in GDScript.
    assert "actuators" in scene


def test_the_pod_still_builds_when_no_contract_is_given():
    """The layout proof's own frames have to keep reproducing."""
    machine = MACHINE.read_text(encoding="utf-8")
    assert "if contract.is_empty():" in machine
    assert "Modules.start(palette," in machine


@pytest.mark.skipif(not REPLAY.is_file(), reason="the selected replay is not built")
def test_the_field_rests_on_the_floor_the_replay_records(built):
    """Section 5, as a statement about the two files a render is made of.

    The renderer draws a marble at the replay's marble transform and a slat at
    the replay's slat transform, so "is the field supported" is answerable
    without a renderer at all: take the marble's lowest point and the top of
    the slat under it, both from the same frame of the same file.

    Checked over the hold - after the spawn settles and before the floor opens
    - because that is the window the start camera is on and the window the
    defect was visible in.
    """
    _machine, start, data = built
    replay = json.loads(REPLAY.read_text(encoding="utf-8"))
    scale = float(replay["units"]["render_scale"])
    radius = float(replay["marbles"][0].get("radius", 0.5))
    panels = {
        name: entry
        for name, entry in data["parts"].items()
        if name.startswith("panel")
    }
    assert panels, "the contract carries no floor slats"

    opens = float(data["floor"]["opens_at"])
    worst_gap = -9.0
    worst_lift = 9.0
    samples = 0
    for frame in replay["frames"]:
        when = float(frame["t"])
        if when < 1.5 or when > opens - 0.2:
            continue
        actuators = frame["actuators"]
        tops: list[tuple[float, float, float]] = []
        for name, entry in panels.items():
            pose = actuators[f"start.{name}"]
            half_sim = entry["half_extents"][1] / scale
            tops.append(
                (float(pose["p"][0]), float(pose["p"][1]) + half_sim, float(pose["p"][2]))
            )
        for sample in frame["marbles"]:
            position = sample["p"]
            bottom = float(position[1]) - radius
            # The slat under this marble: nearest in plan.
            near = min(
                tops,
                key=lambda t: (t[0] - position[0]) ** 2 + (t[2] - position[2]) ** 2,
            )
            gap = bottom - near[1]
            worst_gap = max(worst_gap, gap)
            worst_lift = min(worst_lift, gap)
            samples += 1
    assert samples > 200, f"only {samples} samples in the hold"
    # A marble sits ON the slats: never more than a tenth of a radius above one
    # and never sunk more than the solver's own contact slop.
    assert worst_gap < 0.1 * radius, f"a marble floats {worst_gap:.4f} above the floor"
    assert worst_lift > -0.25 * radius, f"a marble sinks {worst_lift:.4f} into the floor"


@pytest.mark.skipif(not REPLAY.is_file(), reason="the selected replay is not built")
def test_the_bays_line_up_with_the_physics_start(built):
    """The eight racers start on the eight bay centres the contract gives."""
    _machine, start, data = built
    replay = json.loads(REPLAY.read_text(encoding="utf-8"))
    origin = start.origin
    lateral, _up, _forward = start.frame
    frame = replay["frames"][0]
    across = sorted(
        sum(
            (float(sample["p"][axis]) * SIM_TO_LAYOUT - origin[axis]) * lateral[axis]
            for axis in range(3)
        )
        for sample in frame["marbles"]
    )
    wanted = sorted(data["bay_x"])
    assert len(across) == len(wanted) == layout.BAYS
    for measured, expected in zip(across, wanted):
        assert measured == pytest.approx(expected, abs=0.02), (measured, expected)

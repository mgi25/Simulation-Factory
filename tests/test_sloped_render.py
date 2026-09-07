"""What the physics does and what the render draws have to be the same course.

Not a rendering test - Godot is not run here. These are the places where a
number is written down twice, once in Python and once in GDScript, and where
the two drifting apart shows up in the video as a marble bouncing off nothing.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from sloped import layout
from sloped.course import MIXER_SAMPLE, SHUFFLE_SAMPLE, sloped_course

GODOT = Path(__file__).resolve().parents[1] / "godot"
MACHINE_GD = GODOT / "assets" / "marble_machine" / "course" / "course_machine.gd"
LAYOUT_GD = GODOT / "assets" / "marble_machine" / "course" / "course_layout.gd"
MODULES_GD = GODOT / "assets" / "marble_machine" / "course" / "course_modules.gd"
SCENE_GD = GODOT / "scripts" / "sloped_race_scene.gd"


def _int_assignment(text: str, name: str) -> int:
    match = re.search(rf"var {name} *:= *(\d+)", text)
    assert match, f"{name} is not assigned in the GDScript"
    return int(match.group(1))


def test_the_render_places_the_mixer_and_the_wheel_where_the_physics_has_them():
    """Both moved in V1.1, and the render's own table still said `mix`."""
    text = MACHINE_GD.read_text(encoding="utf-8")
    assert _int_assignment(text, "mixer_sample") == MIXER_SAMPLE
    assert _int_assignment(text, "shuffle_sample") == SHUFFLE_SAMPLE
    # ...and on the launch run, not on leg1's recorded `mix` node.
    assert "Modules.mixer(palette), launch[mixer_sample]" in text
    assert "Modules.shuffle(palette), launch[shuffle_sample]" in text


def test_the_render_has_a_shuffle_wheel_to_place():
    modules = MODULES_GD.read_text(encoding="utf-8")
    assert "static func shuffle(palette)" in modules
    assert 'root.name = "Shuffle"' in modules
    assert 'spinner.name = "Spinner0"' in modules


def test_the_scene_turns_the_shuffle_wheel_from_the_replay():
    """A drawn wheel that does not turn with its collider is a wheel a marble
    passes through."""
    scene = SCENE_GD.read_text(encoding="utf-8")
    assert '["Shuffle", "shuffle", 1]' in scene
    assert '"key": "%s.wheel%d_blade0"' in scene
    # And the key it builds is the one the replay actually carries.
    machine = sloped_course()
    shuffle = machine.modules["shuffle"]
    names = [actuator.name for actuator in shuffle.local_actuators()]
    assert "wheel0_blade0" in names


def test_the_replay_carries_a_pose_for_every_drawn_wheel():
    machine = sloped_course()
    keys = {
        f"{module.id}.{actuator.name}"
        for module in machine
        for actuator in module.local_actuators()
    }
    for expected in ("shuffle.wheel0_blade0", "obstacle.wheel0_blade0"):
        assert expected in keys, sorted(k for k in keys if "wheel" in k)


def test_oranges_tail_heights_agree_between_python_and_gdscript():
    """The one control-point change of the session, written down twice."""
    text = LAYOUT_GD.read_text(encoding="utf-8")
    controls = layout.run("orange")["controls"]
    for x, y, z in controls[6:9]:
        needle = f"Vector3({x:.2f}, {y:.4f}, {z:.2f})"
        assert needle in text, f"{needle} is not in course_layout.gd"


@pytest.mark.parametrize("module_id", ["mixer", "shuffle"])
def test_both_start_modules_stand_on_the_launch(module_id):
    machine = sloped_course()
    assert machine.modules[module_id].run.id == "launch"

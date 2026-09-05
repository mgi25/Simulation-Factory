"""Style-lock tests: the contract the premium-toy visual proof rests on.

Godot is not in this test run, so nothing here asserts how the picture looks -
and it should not. The brief for this phase is explicit that the work succeeds
or fails on the image, and a test that pinned an albedo or a fillet radius
would only make the next art iteration harder for no protection at all.

What is worth asserting is the handful of facts that are invisible from
anywhere else in the project and whose failure is silent:

* **The tool and the scene agree on what ships.** The proof renders the
  variant and the hero lens the tool names; the scene defaults to them. If the
  two drift, the hero still in `docs/` is not the direction the report claims
  was chosen, and nothing else would catch it.
* **The measurement that fixes `MARBLE_SCALE`.** The scene draws marbles at
  their simulation radius because the field is in contact in essentially every
  frame, so any multiplier draws intersecting spheres. That is a property of
  the *race*, not of the renderer, and if a future course change made the
  field sparse the constant should be revisited rather than left at 1.0 by
  habit. The test records the measurement.
* **The route to the scene exists.** `--race-style=toy` has to reach
  `toy_scene.gd` through the viewer, and the viewer's other two styles have to
  survive it.
* **The neon proof is not collateral damage.** This phase is a sibling of V1.1
  and V1.1 is the negative half of the comparison sheet, so the tool that
  produces it must still be intact.
"""

from __future__ import annotations

import math
import os
import re
import sys

import pytest

from race.courses.neon import NEON_COURSE_ID
from rendering.render_plan import RENDER_FPS
from replay.race_exporter import record_race
from tools import neon_proof, toy_proof

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(PROJECT_ROOT, "godot", "scripts")
SCENE_PATH = os.path.join(SCRIPTS, "toy_scene.gd")
MATERIALS_PATH = os.path.join(SCRIPTS, "toy_materials.gd")
VIEWER_PATH = os.path.join(SCRIPTS, "replay_viewer.gd")

PROOF_SEED = toy_proof.DEFAULT_SEED


@pytest.fixture(scope="module")
def replay() -> dict:
    return record_race(
        PROOF_SEED,
        course_name=NEON_COURSE_ID,
        racer_count=toy_proof.TOY_RACER_COUNT,
    )


def _source(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def scene_constant(name: str) -> float:
    """One `const NAME := value` out of the toy scene, as a number."""
    found = re.search(
        rf"^const {name} := (-?[0-9.]+)$", _source(SCENE_PATH), re.MULTILINE
    )
    assert found, f"{name} is not a plain constant in toy_scene.gd"
    return float(found.group(1))


# --- the field the prototype is shot with -----------------------------------


def test_the_field_is_the_size_the_brief_asks_for():
    """Six to ten. Sixteen is a bowl with no bowl visible in it."""
    assert 6 <= toy_proof.TOY_RACER_COUNT <= 10


def test_the_replay_is_the_same_race_every_time(replay: dict):
    """Every step of the proof reads one replay, so a comparison is about
    what it claims to be about. That only holds if the race is a function of
    its seed."""
    again = record_race(
        PROOF_SEED,
        course_name=NEON_COURSE_ID,
        racer_count=toy_proof.TOY_RACER_COUNT,
    )
    assert len(again["frames"]) == len(replay["frames"])
    assert again["result"]["winner_name"] == replay["result"]["winner_name"]
    assert again["frames"][-1]["racers"] == replay["frames"][-1]["racers"]


# --- why the marbles are drawn at their own size ----------------------------


def test_the_field_is_in_contact_in_essentially_every_frame(replay: dict):
    """The measurement that fixes `MARBLE_SCALE` at 1.0.

    A marble run is a pile-up: the closest pair of racers sits at about the
    simulation diameter for the whole race. So drawing marbles any larger than
    the simulation says draws *intersecting spheres*, and the bowl renders as
    one fused blob rather than as eight collectibles. Apparent size has to come
    from the lens and from a smaller field instead.

    If a future course ever spaces the field out, this test is where that
    shows up, and the constant can be revisited on evidence.
    """
    radius = float(replay["racers"][0]["radius"])
    diameter = radius * 2.0
    touching = 0
    counted = 0
    for frame in replay["frames"]:
        live = [r for r in frame["racers"] if not r.get("retired")]
        if len(live) < 2:
            continue
        closest = min(
            math.hypot(a["x"] - b["x"], a["y"] - b["y"])
            for index, a in enumerate(live)
            for b in live[index + 1 :]
        )
        counted += 1
        if closest < diameter * 1.05:
            touching += 1

    assert counted > 0
    assert touching / counted > 0.95, (
        f"only {touching}/{counted} frames have a touching pair; the field is "
        "sparser than it was, so MARBLE_SCALE above 1.0 may now be safe"
    )


def test_the_scene_draws_marbles_at_the_size_the_simulation_says():
    assert scene_constant("MARBLE_SCALE") == 1.0


# --- the tool and the scene agree on what ships -----------------------------


def test_the_scene_ships_the_variant_the_tool_selects():
    """A variant sheet rendered from three palettes and a hero rendered from
    a fourth would be a silent lie, and nothing else in the pipeline looks."""
    source = _source(SCENE_PATH)
    found = re.search(r"else ToyMaterials\.VARIANT_([ABC])", source)
    assert found, "the scene does not name a default variant"
    assert found.group(1).lower() == toy_proof.SELECTED_VARIANT


def test_every_variant_the_tool_offers_exists_in_the_palette():
    source = _source(MATERIALS_PATH)
    found = re.findall(r'^\t"([abc])": \{', source, re.MULTILINE)
    assert set(found) == set(toy_proof.VARIANTS)
    assert set(toy_proof.VARIANT_NAMES) == set(toy_proof.VARIANTS)


def test_every_hero_lens_the_tool_asks_for_is_defined_in_the_scene():
    source = _source(SCENE_PATH)
    block = source[source.index("const SHOTS := {"): source.index("const SHOT_FOLLOW")]
    defined = set(re.findall(r'^\t"([abc])": \{', block, re.MULTILINE))
    assert defined == set(toy_proof.SHOTS)
    assert toy_proof.HERO_SHOT in defined
    assert set(toy_proof.SHOT_MOMENTS) == defined


def test_the_godot_command_selects_the_toy_scene():
    command = toy_proof.godot_command(
        "godot", "replay.json", "out", 100, "a", "b", (1, 2), True
    )
    assert "--race-style=toy" in command
    assert "--toy-variant=a" in command
    assert "--toy-shot=b" in command
    assert "--stills=1,2" in command
    assert "--toy-no-glow=1" in command


def test_the_glow_flag_is_absent_unless_the_no_glow_frame_is_asked_for():
    """The bloom comparison is only a comparison if the control is the frame
    that ships, rather than a third rendering that happens to resemble it."""
    command = toy_proof.godot_command(
        "godot", "replay.json", "out", 100, "a", "a", (1,), False
    )
    assert not [arg for arg in command if arg.startswith("--toy-no-glow")]


# --- the moments and the clip -----------------------------------------------


def test_every_hero_moment_lands_inside_the_replay(replay: dict):
    for shot, at in toy_proof.SHOT_MOMENTS.items():
        index = toy_proof.moment_frame(replay, at)
        assert 0 <= index < len(replay["frames"]), shot


def test_the_clip_is_the_length_the_brief_asks_for(replay: dict):
    assert 4.0 <= toy_proof.VIDEO_SECONDS <= 6.0
    start, count = toy_proof.video_window(replay)
    assert start >= 0
    assert start + count <= len(replay["frames"])
    assert count / RENDER_FPS == pytest.approx(toy_proof.VIDEO_SECONDS, abs=0.05)


def test_the_clip_opens_before_the_release(replay: dict):
    start, _ = toy_proof.video_window(replay)
    assert start < neon_proof.gate_frame(replay)


# --- the route to the scene, and the sibling it must not break --------------


def test_the_replay_viewer_can_reach_all_three_scenes():
    source = _source(VIEWER_PATH)
    for expected in ("toy_scene.gd", "neon_scene.gd", "race_scene.gd"):
        assert expected in source, expected
    for style in ('"toy"', '"neon"', '"standard"'):
        assert style in source, style


def test_an_unknown_style_still_falls_back_to_the_production_scene():
    """Adding a third style must not turn a typo into a broken render."""
    source = _source(VIEWER_PATH)
    block = source[source.index("func _race_style_argument"):]
    block = block[: block.index("func _race_scene_for")]
    assert "return STYLE_STANDARD" in block


def test_the_neon_proof_is_undamaged():
    """V1.1 is the negative half of the comparison sheet. A style lock that
    broke the thing it is being compared against would have nothing to say."""
    command = neon_proof.godot_command("godot", "replay.json", "out", 100, 52.0)
    assert "--race-style=neon" in command
    assert neon_proof.SELECTED_ELEVATION in neon_proof.CAMERA_ANGLES


def test_the_comparison_sheet_names_files_that_exist():
    """The mandatory deliverable reads two committed images it does not
    produce, so a rename anywhere else would only surface at render time."""
    for path in (toy_proof.CONCEPT, toy_proof.V11_HERO):
        assert os.path.isfile(os.path.join(PROJECT_ROOT, path)), path


def test_a_missing_godot_is_reported_rather_than_raised(monkeypatch, capsys):
    monkeypatch.setattr(
        sys, "argv", ["toy_proof.py", "--shots", "--godot", "C:/nope.exe"]
    )
    assert toy_proof.main() == 1
    captured = capsys.readouterr()
    assert "nope.exe" in captured.err
    assert "Traceback" not in captured.err

"""What has to be true of the render path itself.

The contract tests check that the numbers agree. These check the things that
are properties of the pipeline rather than of any one number: that Godot never
simulates, that the clock is the output frame index and not the wall clock,
that the renderer refuses a replay it does not understand, and that the shot
cuts land where the run actually changes module.
"""

from __future__ import annotations

import json
import os
import re

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GODOT_DIR = os.path.join(REPO_ROOT, "godot")
SCENE = os.path.join(GODOT_DIR, "scripts", "marble3d_scene.gd")
RENDERER = os.path.join(GODOT_DIR, "scripts", "marble3d_render.gd")


def _gd_sources() -> list[str]:
    found: list[str] = []
    for root, _dirs, files in os.walk(GODOT_DIR):
        if ".godot" in root:
            continue
        for name in files:
            if name.endswith(".gd"):
                found.append(os.path.join(root, name))
    return sorted(found)


def _strip_comments(text: str) -> str:
    """GDScript source with its comments removed.

    The files in this project explain themselves at length, and several of
    those explanations are about why there is no physics here. Searching the
    raw text for 'RigidBody' finds the sentence saying there isn't one.
    """
    out = []
    for line in text.splitlines():
        stripped = line.split("#", 1)[0]
        out.append(stripped)
    return "\n".join(out)


# --- Godot does not simulate ---------------------------------------------

# Every class and callback that would mean Godot was running physics of its
# own, plus the sources of frame-to-frame state that would stop a render being
# reproducible from its frame index alone.
FORBIDDEN_PHYSICS = [
    "RigidBody2D", "RigidBody3D", "PhysicsBody2D", "PhysicsBody3D",
    "StaticBody2D", "StaticBody3D", "CharacterBody2D", "CharacterBody3D",
    "AnimatableBody2D", "AnimatableBody3D", "SoftBody3D",
    "Area2D", "Area3D", "CollisionShape2D", "CollisionShape3D",
    "CollisionPolygon2D", "CollisionPolygon3D", "CollisionObject2D",
    "CollisionObject3D", "PhysicsServer2D", "PhysicsServer3D",
    "PhysicsDirectSpaceState2D", "PhysicsDirectSpaceState3D",
    "RayCast2D", "RayCast3D", "ShapeCast2D", "ShapeCast3D",
    "Joint2D", "Joint3D", "PinJoint3D", "HingeJoint3D",
    "move_and_slide", "move_and_collide", "_physics_process",
    "set_physics_process", "_integrate_forces",
    "apply_impulse", "apply_central_impulse", "apply_force",
    "apply_central_force", "apply_torque", "apply_torque_impulse",
    "GPUParticles2D", "GPUParticles3D", "CPUParticles2D", "CPUParticles3D",
]

FORBIDDEN_NONDETERMINISM = [
    "randi", "randf", "randomize", "RandomNumberGenerator",
    "Tween", "AnimationPlayer", "create_timer",
    "get_process_delta_time", "get_physics_process_delta_time",
    "Time.get_unix_time", "Time.get_datetime",
]


def test_no_godot_file_uses_a_physics_class():
    """The claim the whole milestone rests on, checked over every file.

    PyBullet is authoritative. If Godot ever grows a physics body, the picture
    stops being a picture of the simulation and starts being a second, worse
    simulation that happens to be drawn.
    """
    offenders: list[str] = []
    for path in _gd_sources():
        with open(path, encoding="utf-8") as handle:
            code = _strip_comments(handle.read())
        for token in FORBIDDEN_PHYSICS:
            if re.search(r"\b%s\b" % re.escape(token), code):
                offenders.append(f"{os.path.relpath(path, REPO_ROOT)}: {token}")
    assert offenders == []


def test_the_project_declares_no_physics_settings():
    with open(os.path.join(GODOT_DIR, "project.godot"), encoding="utf-8") as handle:
        text = handle.read()
    assert "[physics]" not in text


def test_the_marble3d_render_path_is_deterministic():
    """The scene and its renderer carry no clock and no randomness."""
    offenders: list[str] = []
    for path in (SCENE, RENDERER):
        with open(path, encoding="utf-8") as handle:
            code = _strip_comments(handle.read())
        for token in FORBIDDEN_NONDETERMINISM:
            if re.search(r"\b%s\b" % re.escape(token.split(".")[-1]), code):
                offenders.append(f"{os.path.basename(path)}: {token}")
    assert offenders == []


def test_the_only_clock_is_the_output_frame_index():
    """`set_frame(index)` takes an int, and nothing else drives motion."""
    with open(SCENE, encoding="utf-8") as handle:
        code = _strip_comments(handle.read())
    assert "func set_frame(index: int) -> void:" in code
    # `delta` must never reach the scene: no _process, no _physics_process.
    assert not re.search(r"\bfunc _process\b", code)
    assert not re.search(r"\bfunc _physics_process\b", code)

    with open(RENDERER, encoding="utf-8") as handle:
        renderer = _strip_comments(handle.read())
    # The renderer may read the wall clock, but only to print a rate.
    for line in renderer.splitlines():
        if "Time.get_ticks_usec" in line:
            assert "started" in line or "elapsed" in line, line


def test_the_renderer_refuses_a_replay_it_does_not_understand():
    """A race replay in the same directory must not render as a machine."""
    with open(RENDERER, encoding="utf-8") as handle:
        code = handle.read()
    assert 'REPLAY_FORMAT := "marble3d"' in code
    assert "contract_version" in code
    assert '_fail("replay %s is format' in code


def test_godot_is_never_invoked_headless():
    """Load-bearing.

    Headless gives Godot no rendering device, `get_image()` returns null and
    every renderer in this repo fails. It looks like an obvious cleanup and it
    is not one, which is why the drivers explain its absence in prose - so the
    flag is looked for as a quoted argument rather than as the word, or the
    explanation would trip the test that protects it.
    """
    tools = os.path.join(REPO_ROOT, "tools")
    for name in sorted(os.listdir(tools)):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(tools, name), encoding="utf-8") as handle:
            text = handle.read()
        assert '"--headless"' not in text, name
        assert "'--headless'" not in text, name


# --- the marbles the scene draws -----------------------------------------


def test_every_marble_in_the_replay_gets_its_own_node():
    with open(SCENE, encoding="utf-8") as handle:
        code = handle.read()
    assert 'for info in _replay.get("marbles", [])' in code
    assert '_palette.marble(index)' in code
    # Eight hues, and a racer's colour is its id, so a marble keeps its colour
    # across a re-render.
    assert '"Marble%d" % index' in code


def test_the_scene_reads_position_rotation_from_the_replay():
    """Not a spline, not an eased approach - the recorded pose."""
    with open(SCENE, encoding="utf-8") as handle:
        code = _strip_comments(handle.read())
    assert 'record["p"]' in code
    assert 'record["q"]' in code
    assert "node.transform = Transform3D(Basis(spin), at)" in code


def test_the_marble_machine_never_builds_a_colour_from_floats():
    """GDScript Color floats are sRGB, and it once turned the machine grey.

    Scoped to the authored marble-machine assets and the marble3d render path.
    The older race and neon scenes carry float colours of their own and are not
    on this path; correcting them would be changing production behaviour that
    nothing here depends on.
    """
    scoped = [
        path
        for path in _gd_sources()
        if os.path.join("assets", "marble_machine") in path
        or os.path.basename(path).startswith("marble3d_")
    ]
    assert scoped, "no marble-machine sources found to check"
    offenders: list[str] = []
    for path in scoped:
        with open(path, encoding="utf-8") as handle:
            code = _strip_comments(handle.read())
        for match in re.finditer(r"Color\(\s*([0-9]*\.?[0-9]+)\s*,", code):
            offenders.append(
                f"{os.path.relpath(path, REPO_ROOT)}: Color({match.group(1)}, ...)"
            )
    assert offenders == []


# --- shot timing ----------------------------------------------------------


@pytest.fixture(scope="module")
def seed_one_replay():
    from marble3d.simulation import simulate

    return json.loads(json.dumps(simulate(seed=1, marble_count=8).to_json()))


def test_shot_cuts_are_derived_from_the_run(seed_one_replay):
    from tools.marble3d_integrate import shot_cuts

    frame_count = len(seed_one_replay["frames"])
    cuts = shot_cuts(seed_one_replay, 60, frame_count)

    assert [cut.name for cut in cuts] == ["start", "bowl", "curve"]
    frames = [cut.start_frame for cut in cuts]
    assert frames == sorted(frames)
    assert frames[0] == 0
    assert len(set(frames)) == len(frames), "two shots cannot start on one frame"
    assert frames[-1] < frame_count


def test_shot_cuts_follow_the_marbles_not_the_clock(seed_one_replay):
    """A cut must not sit on an empty module waiting for something to happen.

    Asserted as "the marble turns up soon after the camera does" rather than as
    exact frame arithmetic. The driver deliberately cuts a little early so the
    shot is settled when the marble arrives, and the event it cuts on is a tick
    time that can fall between two sampled frames, so an exact comparison would
    be testing the sampling stride rather than the framing.
    """
    from tools.marble3d_integrate import SHOT_LEAD_SECONDS, shot_cuts

    frame_count = len(seed_one_replay["frames"])
    cuts = {
        cut.name: cut.start_frame
        for cut in shot_cuts(seed_one_replay, 60, frame_count)
    }

    def first_frame_in(module: str) -> int:
        for index, frame in enumerate(seed_one_replay["frames"]):
            if any(entry.get("in") == module for entry in frame["marbles"]):
                return index
        return frame_count

    # Half a second of grace on top of the intended lead: enough to absorb the
    # stride and the hysteresis, far too little to hide a cut that fired early.
    grace = int(round((SHOT_LEAD_SECONDS + 0.5) * 60))
    for module in ("bowl", "curve"):
        arrival = first_frame_in(module)
        assert arrival < frame_count, f"nothing ever entered {module}"
        assert cuts[module] >= arrival - grace, (
            f"the {module} shot starts {arrival - cuts[module]} frames before "
            f"a marble is there"
        )
        assert cuts[module] <= arrival + grace, (
            f"the {module} shot starts {cuts[module] - arrival} frames after "
            f"the marbles arrived"
        )
    assert cuts["start"] < cuts["bowl"] < cuts["curve"]

"""V0.3 tests: the production visuals, and what they are not allowed to touch.

Almost nothing here renders a pixel. Image tests for lighting are brittle by
construction - a tenth of a degree on a key light changes every byte and tells
you nothing about whether the change was good - so what is tested is the two
things that *can* be stated exactly:

**The contract with the simulation.** Godot may present the race however it
likes and may not participate in it. So the checks are that the replay still
drives everything, that the verification camera's guarantee is intact, and
that no visual code found its way into the Python half.

**The contract with the platform.** A Short is watched with YouTube's own
chrome drawn over it. Where the overlay is allowed to be, and how big its text
has to be, are numbers - so they are asserted as numbers, against the same
constants the renderer uses.

The GDScript is read as text rather than executed, because there is no Godot in
a pytest run. That is a real limitation and it is worth being honest about what
it does and does not catch: it catches a constant moved out of the safe area, a
forbidden API appearing, or the HUD and its verifier drifting apart. It does not
catch a script that fails to parse - `tools/render_replay.py` does that, the
first time anything is rendered.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from rendering.render_plan import (
    CAMERA_BATTLE,
    CAMERA_PRODUCTION,
    CAMERA_VERIFICATION,
    MODE_RACE,
    RACE_CAMERAS,
    RenderPlanError,
    metadata,
    plan_render,
)
from replay.exporter import record_battle
from replay.race_exporter import record_race
from tools import verify_race_render

GODOT = Path("godot/scripts")
RACE_SCRIPTS = (
    "race_scene.gd",
    "race_hud.gd",
    "race_vfx.gd",
    "race_trails.gd",
    "race_materials.gd",
)


def source(name: str) -> str:
    return (GODOT / name).read_text(encoding="utf-8")


def code(name: str) -> str:
    """A script with its comments removed.

    The forbidden-API scan runs over this rather than the raw file, because
    the files that must not *use* a Tween are exactly the files whose header
    explains why they do not.
    """
    lines = []
    for line in source(name).splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        lines.append(line.split(" # ")[0])
    return chr(10).join(lines)


def constant(text: str, name: str) -> str:
    """The value of a `const NAME := ...` line, as written."""
    match = re.search(rf"^const {name} :?= (.+?)$", text, re.MULTILINE)
    assert match is not None, f"{name} is not declared"
    return match.group(1).split("#")[0].strip()


def rect(text: str, name: str) -> tuple[float, float, float, float]:
    """A `const NAME := Rect2(x, y, w, h)` as four numbers."""
    match = re.search(
        rf"^const {name} :?= Rect2\(([^)]*)\)", text, re.MULTILINE
    )
    assert match is not None, f"{name} is not a Rect2 constant"
    parts = [part.strip() for part in match.group(1).split(",")]
    numbers = []
    for part in parts:
        if part.replace(".", "").replace("_", "").isdigit():
            numbers.append(float(part))
        else:
            numbers.append(float(constant(text, part)))
    assert len(numbers) == 4
    return tuple(numbers)


# --- camera modes ---------------------------------------------------------


@pytest.fixture(scope="module")
def race() -> dict:
    return record_race(1000)


def test_a_race_defaults_to_the_production_camera(race: dict) -> None:
    assert plan_render(race, "r.json", ".").camera == CAMERA_PRODUCTION


def test_the_verification_camera_can_always_be_asked_for(race: dict) -> None:
    """It is the only mechanical proof the render is of the right race.

    If it ever stops being reachable, the production camera stops being
    evidence of anything.
    """
    plan = plan_render(race, "r.json", ".", camera=CAMERA_VERIFICATION)
    assert plan.camera == CAMERA_VERIFICATION
    assert metadata(plan, "a" * 64)["video"]["camera"] == CAMERA_VERIFICATION


def test_both_race_cameras_produce_the_same_sequence(race: dict) -> None:
    """The lens changes; the film does not.

    A verification render and a production render of one replay have to be
    the same length, at the same rate, showing the same instants - otherwise
    frame N of one is not evidence about frame N of the other.
    """
    verification = plan_render(race, "r.json", ".", camera=CAMERA_VERIFICATION)
    production = plan_render(race, "r.json", ".", camera=CAMERA_PRODUCTION)
    for field in (
        "frame_count",
        "gameplay_frames",
        "post_roll_frames",
        "fps",
        "width",
        "height",
        "physics_hz",
        "finished_tick",
        "gameplay_seconds",
    ):
        assert getattr(verification, field) == getattr(production, field), field


def test_a_battle_has_one_camera_and_cannot_be_given_another() -> None:
    battle = record_battle(12345)
    assert plan_render(battle, "b.json", ".").camera == CAMERA_BATTLE
    for camera in RACE_CAMERAS:
        with pytest.raises(RenderPlanError, match="one camera"):
            plan_render(battle, "b.json", ".", camera=camera)


def test_an_unknown_race_camera_is_refused(race: dict) -> None:
    with pytest.raises(RenderPlanError, match="unknown race camera"):
        plan_render(race, "r.json", ".", camera="cinematic")


def test_the_camera_reaches_godot_on_the_command_line() -> None:
    text = Path("tools/render_replay.py").read_text(encoding="utf-8")
    body = text[text.index("def run_godot(") : text.index("def verify_sequence(")]
    assert "--race-camera=" in body
    assert "plan.camera" in body


def test_the_viewer_only_treats_an_exact_match_as_verification() -> None:
    """Anything unrecognised must still render, and render finished.

    `run_godot` sends `--race-camera=battle` for a battle replay, so the
    parser has to cope with a value that is neither race camera without
    falling over or quietly producing the measuring lens.
    """
    text = source("replay_viewer.gd")
    body = text[text.index("func _race_camera_argument(") :]
    body = body[: body.index("func _resolve_path(")]
    assert "CAMERA_VERIFICATION" in body
    # Exactly one comparison against the verification name, and a production
    # fall-through on both paths out of the loop.
    assert body.count("== CAMERA_VERIFICATION") == 1
    assert body.count("return CAMERA_PRODUCTION") == 2


def test_verification_alignment_is_refused_on_a_production_render(tmp_path) -> None:
    """And refused before the replay override, not after it."""
    render = tmp_path / "render"
    (render / "frames").mkdir(parents=True)
    (render / "metadata.json").write_text(
        json.dumps(
            {
                "replay": {"mode": MODE_RACE, "name": "r.json", "path": "r.json"},
                "video": {"camera": CAMERA_PRODUCTION},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(verify_race_render.VerifyError, match="production camera"):
        verify_race_render.resolve_replay(str(render), None)
    with pytest.raises(verify_race_render.VerifyError, match="production camera"):
        verify_race_render.resolve_replay(str(render), "somewhere/else.json")


def test_a_sidecar_with_no_camera_is_a_verification_render(tmp_path) -> None:
    """Every race render made before the production camera existed was one."""
    render = tmp_path / "render"
    (render / "frames").mkdir(parents=True)
    (render / "metadata.json").write_text(
        json.dumps({"replay": {"mode": MODE_RACE, "path": "old.json"}, "video": {}}),
        encoding="utf-8",
    )
    assert verify_race_render.resolve_replay(str(render), "old.json") == "old.json"


# --- the simulation stays authoritative -----------------------------------


FORBIDDEN = {
    "GPUParticles3D": "a particle system integrates on engine frames",
    "CPUParticles3D": "a particle system integrates on engine frames",
    "Tween": "a tween advances on wall-clock time",
    "AnimationPlayer": "an animation player advances on wall-clock time",
    "randf": "randomness cannot be reproduced",
    "randi": "randomness cannot be reproduced",
    "Time.get_ticks": "wall-clock time is not replay time",
    "use_taa": "temporal anti-aliasing reads the previous frame",
    "sdfgi_enabled": "SDFGI accumulates across frames",
    "auto_exposure": "auto exposure adapts across frames",
    "volumetric_fog_enabled": "volumetric fog reprojects from the previous frame",
}


@pytest.mark.parametrize("script", RACE_SCRIPTS)
def test_no_race_visual_reads_a_clock_or_a_die(script: str) -> None:
    """Every visual has to be a pure function of the replay tick.

    The offline renderer seeks to an exact instant and draws once; it never
    passes a delta. Anything that integrates, accumulates or randomises would
    produce a different picture at a different render speed, and the
    pipeline's byte-identical check would fail - so the whole class is banned
    rather than reviewed case by case.
    """
    text = code(script)
    for token, why in FORBIDDEN.items():
        assert token not in text, f"{script} uses {token}: {why}"


@pytest.mark.parametrize("script", RACE_SCRIPTS)
def test_no_race_visual_reads_a_frame_delta(script: str) -> None:
    assert not re.search(r"\bfunc _process\(", source(script))
    assert not re.search(r"\bfunc _physics_process\(", source(script))


def test_the_race_scene_takes_its_transforms_from_the_replay() -> None:
    """Positions are read, never integrated.

    A spinner's angular speed is in the replay and must not be used to work
    out where an arm is: the transform the simulation actually had is right
    there, and integrating would drift away from it the moment a spinner
    could be blocked.
    """
    text = source("race_scene.gd")
    body = text[text.index("func _update_spinners(") :]
    body = body[: body.index("func _update_gates(")]
    assert "rotation_degrees" in body
    assert "angular_speed" not in body
    assert "start_angle" not in body


def test_the_squash_never_moves_a_racer() -> None:
    """Impact deformation is presentation and must stay presentation.

    The racer is scaled about its own centre. If this ever started writing a
    position, Godot would be moving a competitor the simulation had placed.
    """
    text = source("race_scene.gd")
    body = text[text.index("func _apply_squash(") :]
    body = body[: body.index("# --- trails, spinners")]
    assert "basis" in body
    assert ".position =" not in body


def test_effects_are_placed_where_the_event_says() -> None:
    """Not at whatever the racers involved have since moved to."""
    text = source("race_vfx.gd")
    body = text[text.index("func _spawn(") : text.index("func _spawn_impact(")]
    assert 'event.get("x"' in body and 'event.get("y"' in body


def test_effects_without_a_position_are_skipped() -> None:
    """Countdown, start and complete carry an explicit null, not a zero.

    `Dictionary.get(key, default)` returns the stored null rather than the
    default, so an unguarded read would put every one of them at the top-left
    corner of the course.
    """
    text = source("race_vfx.gd")
    body = text[text.index("func _spawn(") : text.index("func _spawn_impact(")]
    assert 'event.get("x") == null' in body


def test_the_impact_scale_starts_where_the_simulation_stops_recording() -> None:
    """Collisions below 620 px/s are never exported.

    Scaling from zero would compress every collision that exists into the top
    third of the range and make them all look identical.
    """
    from race.config import LARGE_COLLISION_SPEED

    text = source("race_vfx.gd")
    floor = float(constant(text, "IMPACT_FLOOR"))
    full = float(constant(text, "IMPACT_FULL"))
    assert floor == LARGE_COLLISION_SPEED
    assert full > floor


def test_the_trail_only_appears_above_a_racing_speed() -> None:
    """A trail that is always on is not a speed cue.

    The measured median racer sample is around 400 px/s against a 750 cap, so
    the threshold has to sit near or above the median or half the field
    trails constantly.
    """
    from race.config import MAX_SPEED

    text = source("race_trails.gd")
    minimum = float(constant(text, "SPEED_MIN"))
    full = float(constant(text, "SPEED_FULL"))
    assert 300.0 <= minimum < full <= MAX_SPEED


def test_the_trail_is_drawn_from_replay_history() -> None:
    text = source("race_trails.gd")
    assert "ImmediateMesh" in text
    assert "_frames" in text
    body = text[text.index("func _history(") :]
    assert "recoveries" in body, "a teleported racer must not be joined up"


def test_no_visual_state_leaked_into_the_python_simulation() -> None:
    """The race package decides races. It has no opinion about pictures."""
    for path in Path("race").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in ("camera_mode", "production", "glow", "emission"):
            assert token not in text, f"{path} mentions {token}"


# --- the platform contract ------------------------------------------------


def test_the_hud_and_its_verifier_agree_on_where_the_overlay_is() -> None:
    """These are two hand-written copies of one set of rectangles.

    They have to match. A rect the verifier does not know about is a racer it
    looks for behind an opaque panel and reports as missing; a rect it has
    that the HUD does not is a racer it silently stops checking.
    """
    text = source("race_hud.gd")

    clock = rect(text, "CLOCK_RECT")
    assert tuple(int(value) for value in clock) == verify_race_render.HUD_RECTS[0]

    left = float(constant(text, "STANDINGS_LEFT"))
    top = float(constant(text, "STANDINGS_TOP"))
    shown = int(constant(text, "STANDINGS_SHOWN"))
    gap = float(constant(text, "STANDINGS_GAP"))
    size = re.search(
        r"^const STANDINGS_SIZE :?= Vector2\(([^)]*)\)", text, re.MULTILINE
    )
    width, height = (float(part) for part in size.group(1).split(","))
    block = (
        int(left),
        int(top),
        int(width),
        int(shown * height + (shown - 1) * gap),
    )
    assert block == verify_race_render.HUD_RECTS[1]

    result = rect(text, "RESULT_RECT")
    assert tuple(int(value) for value in result) == verify_race_render.HUD_RECTS[2]


def test_every_overlay_element_is_inside_the_shorts_safe_area() -> None:
    """YouTube draws its own chrome over a Short.

    The V0.2 overlay put the clock and the leader's standings row inside the
    top band, and the winner panel under the channel and title row - so the
    payoff frame of the whole Short was the frame the platform covered.
    """
    left, top, width, height = verify_race_render.SAFE_RECT
    right, bottom = left + width, top + height

    for name, box in zip(
        ("clock", "standings", "result"), verify_race_render.HUD_RECTS
    ):
        x, y, w, h = box
        assert x >= left, f"{name} starts {left - x}px left of the safe area"
        assert y >= top, f"{name} starts {top - y}px above the safe area"
        assert x + w <= right, f"{name} runs {x + w - right}px into the action rail"
        assert y + h <= bottom, f"{name} runs {y + h - bottom}px into the bottom chrome"


def test_the_countdown_numeral_is_inside_the_safe_area() -> None:
    left, top, width, height = verify_race_render.SAFE_RECT
    x, y, w, h = verify_race_render.COUNTDOWN_RECT
    assert x >= left and y >= top
    assert x + w <= left + width and y + h <= top + height


def test_overlay_text_is_large_enough_to_read_at_shorts_scale() -> None:
    """A 1080-wide frame is watched at roughly 400 logical pixels.

    Source pixels divide by about 2.7 to reach what the eye gets, and 16
    device-independent pixels is the usual comfortable floor for text - which
    is 44 source pixels here. The V0.2 standings ran at 36.
    """
    text = source("race_hud.gd")
    for name in ("STANDINGS_FONT", "CLOCK_FONT", "RESULT_FONT", "RESULT_SUB_FONT"):
        assert int(constant(text, name)) >= 44, name
    assert int(constant(text, "COUNTDOWN_FONT")) >= 200


def test_the_overlay_covers_less_of_the_frame_than_it_used_to() -> None:
    """The brief's complaint, as a number.

    V0.2's banner block plus centre clock came to 82 900 square pixels of
    course. Whatever replaces it has to be smaller, or nothing was fixed.
    """
    previous = 380 * 178 + 230 * 76
    current = sum(w * h for _, _, w, h in verify_race_render.HUD_RECTS[:2])
    assert current < previous


def test_the_overlay_leaves_the_middle_of_the_frame_clear() -> None:
    """The course has to be visible where the race actually happens."""
    for _, y, _, h in verify_race_render.HUD_RECTS[:2]:
        assert y + h <= 700, "the standings reach into the middle of the frame"

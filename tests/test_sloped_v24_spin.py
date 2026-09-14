"""What the visible-spin pass must be true of, whatever it ends up looking like.

The pass makes an existing rotation readable. Every claim below is therefore
about what it did **not** do: it did not invent a spin, it did not touch the
replay, it did not move a marble, and it left the appearance the delivered
films were photographed with exactly where it was.

Three of these are source tests rather than behaviour tests, and deliberately.
"There is no synthetic spin law" is not a property of one call's output - it is
a property of the code, which is that no function in the racer visual takes a
time, a frame index or a velocity. A behaviour test could only sample the
absence; reading the source states it.

The replay is generated output and not in the branch, so tests that need it
skip rather than fail when it is absent. The shape tests need no replay.
"""

from __future__ import annotations

import json
import math
import os
import re
import subprocess

import numpy as np
import pytest

from sloped import v24_spin as spin

REPLAY = os.path.join("output", "sloped_race_v1", "race_5432.json")
TRACK = os.path.join("output", "sloped_race_v1", "cameras_v221_5432.json")
DUMP = os.path.join("output", "sloped_race_v1", "v24", "spin", "coverage_dump.json")

RACER_VISUAL = spin.RACER_VISUAL
RACE_SCENE = os.path.join("godot", "scripts", "sloped_race_scene.gd")

SEED = 5432
DIGEST = "aafb0d3d872e6c5f6db3a6f52d567ae073f1888fbac4ea4970867c130cf17de6"
FINISH_ORDER = [5, 2, 7, 4, 1, 6, 3, 0]


@pytest.fixture(scope="module")
def replay():
    if not os.path.isfile(REPLAY):
        pytest.skip(f"{REPLAY} is generated output and is not in the branch")
    with open(REPLAY, "r", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def track():
    if not os.path.isfile(TRACK):
        pytest.skip(f"{TRACK} is generated output and is not in the branch")
    with open(TRACK, "r", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def marker():
    return spin.Marker.load()


def _source(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


# --- the race is the race -------------------------------------------------


def test_the_replay_is_still_seed_5432s_race(replay):
    """Seed, digest and finishing order, unchanged by a pass about paint."""
    assert replay["seed"] == SEED
    assert replay["summary"]["race"]["seed"] == SEED
    order = [entry["marble"] for entry in replay["summary"]["race"]["racers"]]
    assert order == sorted(FINISH_ORDER)
    by_finish = sorted(replay["summary"]["race"]["racers"], key=lambda row: row["order"])
    assert [row["marble"] for row in by_finish] == FINISH_ORDER


def test_the_replay_digest_is_the_delivered_one(replay):
    """The same digest `test_sloped_v221_shuffle` locks. Nothing re-simulated.

    The digest checked is the one the *file* carries, which is the one the race
    computed before writing. Recomputing it from a re-read replay does not
    reproduce it and is not a weaker version of this test but a different one:
    `write_replay` rounds every number to `DECIMALS` on the way out, so
    `read_replay(path).digest()` is a digest of the rounded record and differs
    from the stored value on an untouched file.
    """
    assert replay["digest"] == DIGEST


def test_nothing_in_this_pass_can_write_a_replay():
    """The module reads. There is no writer in it, and no import of one."""
    text = _source(os.path.join("sloped", "v24_spin.py"))
    assert "write_replay" not in text
    assert not re.search(r'open\([^)]*,\s*["\']w', text)


# --- the rotation is already there ----------------------------------------


def test_every_marble_is_rotating_in_the_mixer(replay):
    """The diagnosis, as a test: no marble is inert while the rotor stirs."""
    fps = float(replay["replay_fps"])
    spins = np.linalg.norm(spin._as_array(replay, "w"), axis=2)
    window = spins[int(1.0 * fps) : int(5.0 * fps)]
    # Every marble turns, and the quietest one still passes half a radian a
    # second at its 95th percentile. A field that was being dragged rather
    # than rolled would not.
    assert window.shape[1] == 8
    assert np.percentile(window, 95, axis=0).min() > 0.5


def test_recorded_orientation_agrees_with_recorded_angular_velocity(replay):
    """The quaternions are live, not a stale field beside a live `w`.

    These are two independent records - PyBullet's reported angular velocity,
    and the angle between consecutive recorded orientations - and if the
    renderer were being fed an orientation that never advanced, only one of
    them would be large. Over the mixer they agree to a few per cent.
    """
    fps = float(replay["replay_fps"])
    quaternions = spin._as_array(replay, "q")
    step = spin.angle_between(quaternions[:-1], quaternions[1:]) * fps
    reported = np.linalg.norm(spin._as_array(replay, "w"), axis=2)[:-1]
    low, high = int(1.0 * fps), int(5.0 * fps)
    from_step = float(np.median(step[low:high]))
    from_w = float(np.median(reported[low:high]))
    assert from_step > 0.5
    assert abs(from_step - from_w) / from_w < 0.10


def test_no_marble_turns_more_than_half_a_turn_between_replay_frames(replay):
    """Otherwise the renderer's short-path slerp would show it rolling backwards."""
    report = spin.nyquist_report(replay)
    assert report["over_180_deg"] == 0
    assert report["aliased"] is False
    assert report["max_deg_per_frame"] < 180.0


def test_the_renderer_takes_orientation_straight_from_the_replay():
    """`quaternion` is only ever assigned from the replay's own `q` field.

    The failure this rules out is the tempting one: deriving a roll from the
    linear velocity and the radius, which looks right on a straight and is
    wrong everywhere else. There is no such term in the scene.
    """
    text = _source(RACE_SCENE)
    assigns = re.findall(r"\.quaternion\s*=\s*(.+)", text)
    assert assigns, "the scene no longer sets a quaternion at all"
    for line in assigns:
        assert '_quat(a["q"])' in line, line
    for forbidden in ("angular_velocity", "linear_velocity", "delta *", "* delta"):
        assert forbidden not in text, forbidden


# --- the marker cannot spin by itself -------------------------------------


def test_nothing_in_the_racer_visual_reads_time_or_velocity():
    """The source claim: there is no argument a synthetic spin could ride on."""
    text = _source(RACER_VISUAL)
    body = "\n".join(
        line for line in text.splitlines() if not line.strip().startswith("#")
    )
    for forbidden in (
        "_process", "_physics_process", "delta", "Time.", "get_ticks",
        "velocity", "randf", "randi", "Tween", "AnimationPlayer", "frame",
    ):
        assert forbidden not in body, f"racer_visual.gd mentions {forbidden!r}"


def test_the_marker_is_a_pure_function_of_the_body_frame(marker):
    """Same direction in, same coverage out - every time, in any order."""
    points = spin._hemisphere(256)
    first = spin.coverage("meridian", points, marker)
    second = spin.coverage("meridian", points[::-1], marker)[::-1]
    assert np.allclose(first, second)


def test_holding_the_quaternion_still_holds_the_marker_still(marker):
    """The anti-synthetic-spin test: a frozen orientation is a frozen marking.

    If anything anywhere gave the marker a life of its own, this is where it
    would show - the same orientation asked twice, with nothing else the same.
    """
    held = np.array([0.21, -0.37, 0.55, 0.72])
    held = held / np.linalg.norm(held)
    eye = np.array([0.0, 0.0, 5.0])
    for appearance in spin.APPEARANCES:
        assert spin.visible_change(appearance, held, held, eye, marker) == 0.0


def test_turning_the_body_turns_the_marker_with_it(marker):
    """The marking is carried by the transform, exactly and without lag.

    A point painted on the ball must land where that rotation puts it. This is
    the texture-space statement of "the child follows the parent quaternion":
    the marker lives in the mesh's own UV space, so a rotation of the node is a
    rotation of the marking, with no second law in between.
    """
    turn = np.array([0.0, math.sin(math.radians(37.0)), 0.0, math.cos(math.radians(37.0))])
    points = spin._hemisphere(400)
    # Where the marker is on the resting ball...
    resting = spin.coverage("meridian", points, marker)
    # ...and where it is on the turned ball, sampled at the turned points.
    turned = spin.coverage("meridian", spin.unrotate(turn, spin.rotate(turn, points)), marker)
    assert np.allclose(resting, turned, atol=1.0e-6)
    # And the turn really does move the pattern in the world: a 37 degree
    # rotation is not a no-op on a marking that has no axis of symmetry.
    moved = spin.coverage("meridian", spin.unrotate(turn, points), marker)
    assert np.abs(moved - resting).max() > 0.5


def test_a_solid_marble_can_never_show_a_rotation(replay, marker):
    """The diagnosis in one number, over the real race and the real camera.

    Every pair of consecutive frames, every marble: the visible face of a plain
    sphere changes by exactly zero. This is why the marbles read as sliding,
    and it is not a bug in the physics.
    """
    fps = float(replay["replay_fps"])
    quaternions = spin._as_array(replay, "q")
    eye = np.array([0.0, 10.0, 10.0])
    worst = 0.0
    for index in range(int(1.0 * fps), int(5.0 * fps), 7):
        for ball in range(quaternions.shape[1]):
            worst = max(worst, spin.visible_change(
                "solid", quaternions[index, ball], quaternions[index + 1, ball],
                eye, marker))
    assert worst == 0.0


def test_a_marked_marble_does_show_it(replay, marker):
    """And the same frames, with a marking, do not score zero."""
    fps = float(replay["replay_fps"])
    quaternions = spin._as_array(replay, "q")
    eye = np.array([0.0, 10.0, 10.0])
    values = [
        spin.visible_change("meridian", quaternions[index, ball],
                            quaternions[index + 1, ball], eye, marker)
        for index in range(int(1.0 * fps), int(5.0 * fps), 7)
        for ball in range(quaternions.shape[1])
    ]
    assert float(np.median(values)) > 0.01


# --- the shipped appearance is still there --------------------------------


def test_solid_is_featureless_everywhere(marker):
    """Backward compatibility, as a shape: the control carries no marking."""
    points = spin._hemisphere(2048)
    assert float(np.abs(spin.coverage("solid", points, marker)).max()) == 0.0


def test_the_renderer_still_defaults_to_the_shipped_appearance():
    """Every film through V22.1 re-renders what it shipped, with no new flag."""
    text = _source(RACE_SCENE)
    assert 'const DEFAULT_RACERS := "solid"' in text
    assert '_racers = str(early.get("racers", DEFAULT_RACERS))' in text


def test_solid_returns_the_palettes_own_material_untouched():
    """Not a copy of the shipped material - the shipped material itself.

    A duplicate would be equal today and free to drift tomorrow. Returning the
    same object means the default appearance cannot be changed here at all
    without changing the palette every other scene shares.
    """
    text = _source(RACER_VISUAL)
    body = text.split("static func material(", 1)[1]
    assert re.search(r'if appearance == "solid":\s*\n\s*return base', body)


def test_the_marking_costs_no_geometry():
    """One mesh, one material, no children - the same scene the sphere built."""
    text = _source(RACER_VISUAL)
    build = text.split("static func build(", 1)[1]
    assert "add_child" not in build
    assert "MeshInstance3D.new()" in build
    # The body is still the sphere the films were photographed with.
    assert "sphere.radial_segments = 32" in text
    assert "sphere.rings = 16" in text


# --- the future skin hook -------------------------------------------------


def test_a_country_skin_would_inherit_the_same_transform():
    """The skin hook is the albedo map, which is exactly where the marker is.

    Nothing about a country texture would need a new node, a new transform or
    any contact with the physics: it enters at `albedo_texture`, the same line
    a band enters at, and is therefore carried by the replay quaternion for the
    same reason. The test holds that single entry point in place.
    """
    text = _source(RACER_VISUAL)
    code = "\n".join(
        line for line in text.splitlines() if not line.strip().startswith("#")
    )
    assert code.count("albedo_texture") == 1
    assert "APPEARANCES" in text
    # And the transform is set somewhere else entirely, by the scene, from the
    # replay - so no appearance can reach it. (The prose above the code says so
    # too, which is why this reads the code and not the file.)
    assert "quaternion" not in code
    assert "position" not in code


def test_the_appearance_list_is_the_only_gate():
    """An unknown appearance is refused, rather than silently drawing nothing."""
    text = _source(RACE_SCENE)
    assert "RacerVisual.APPEARANCES.has(_racers)" in text
    assert "_racers = DEFAULT_RACERS" in text
    with pytest.raises(ValueError):
        spin.coverage("flag_of_nowhere", np.array([[0.0, 1.0, 0.0]]), spin.Marker.load())


# --- the two implementations of one shape ---------------------------------


def test_the_python_twin_matches_the_gdscript_it_describes(marker):
    """The readability numbers are computed from the shape Godot actually paints.

    The dump is written by `scripts/racer_visual_check.gd`; without it there is
    nothing to compare against and the test skips rather than passing quietly.
    """
    if not os.path.isfile(DUMP):
        pytest.skip(f"{DUMP} is generated by racer_visual_check.gd")
    with open(DUMP, "r", encoding="utf-8") as handle:
        dump = json.load(handle)
    points = np.array([row["p"] for row in dump["samples"]])
    assert tuple(dump["appearances"]) == spin.APPEARANCES
    assert dump["marker_tint"] == pytest.approx(marker.tint)
    for appearance in dump["appearances"]:
        engine = np.array([row[appearance] for row in dump["samples"]])
        twin = spin.coverage(appearance, points, marker)
        assert np.abs(engine - twin).max() < 1.0e-4, appearance


def test_the_constants_come_from_the_gdscript_and_not_from_a_copy():
    """Change a number in `racer_visual.gd` and the Python follows it."""
    marker = spin.Marker.load()
    text = _source(RACER_VISUAL)
    assert f"const BAND_HALF := {marker.band_half}" in text
    assert f"const MARKER_TINT := {marker.tint}" in text
    assert np.isclose(np.linalg.norm(marker.ribbon_normal), 1.0)


def test_the_marking_stays_restrained(marker):
    """A premium marble, not a debug marker: the band is a minority of the ball."""
    points = spin._hemisphere(4096)
    for appearance, ceiling in (("ribbon", 0.12), ("crescent", 0.10), ("meridian", 0.20)):
        share = float(spin.coverage(appearance, points, marker).mean())
        assert 0.01 < share < ceiling, (appearance, share)
    # And it tints rather than repaints: the body keeps most of its own value.
    assert 0.4 < marker.tint < 0.75


# --- the edit boundary ----------------------------------------------------


def test_the_shuffle_omission_is_where_v221_put_it(track):
    """The lab reads the delivered edit; it does not invent a new one."""
    found = spin.omissions(track)
    assert len(found) == 1
    assert found[0]["replay_before"] == pytest.approx(2.05)
    assert found[0]["replay_after"] == pytest.approx(4.00)
    assert found[0]["omitted"] == pytest.approx(1.95)


def test_the_omission_really_does_jump_marble_orientation(replay):
    """It does, and by a lot - which the plain sphere could not show.

    This is a finding rather than a fault: 1.95 s of mixing is 1.95 s of
    tumbling, and a cut is allowed to skip it. The number is locked here so
    that a later change to the edit cannot quietly make it worse.
    """
    report = spin.boundary_report(replay, 2.05, 4.00)
    assert report["turn_deg_median"] > 90.0
    # And at least one marble turns a long way while barely moving, which is
    # the case a marking exposes and a plain sphere hides completely.
    stillest = int(np.argmin(report["move_sim"]))
    assert report["move_sim"][stillest] < 0.05
    assert report["turn_deg"][stillest] > 120.0


def test_every_candidate_boundary_omits_exactly_as_much_replay_time(replay):
    """The scan slides the join; it never changes the film's length.

    That is what keeps it a continuity question rather than a pacing one - the
    duration, and therefore every downstream time in the Short, is untouched by
    every candidate the scan offers.
    """
    rows = spin.scan_boundary(replay, 2.05, 4.00, reach=0.25)
    assert rows
    for row in rows:
        gap = row["replay_after"] - row["replay_before"]
        assert gap == pytest.approx(1.95, abs=1.0e-6)
    assert any(row["offset"] == 0.0 for row in rows), "the shipped join must be in its own scan"


def test_a_better_boundary_exists_and_keeps_the_machine_locked(replay):
    """The reported candidate: same length, better rotor phase, no still spinner."""
    rows = spin.scan_boundary(replay, 2.05, 4.00, reach=0.50)
    shipped = next(row for row in rows if row["offset"] == 0.0)
    candidate = next(row for row in rows if row["offset"] == pytest.approx(-28 / 60, abs=1e-4))
    assert candidate["machine_mismatch_deg"] < shipped["machine_mismatch_deg"]
    assert candidate["stillest_move_sim"] > 10.0 * shipped["stillest_move_sim"]
    assert candidate["turn_deg_median"] < shipped["turn_deg_median"]


def test_the_marking_saturates_so_a_slide_cannot_fix_the_jump(marker):
    """Past about a quarter turn, more rotation is not more visible.

    This is why the reported candidate is offered on the two counts it does
    improve - rotor phase, and the marble that turns without moving - and not
    as a fix for the orientation discontinuity. Every whole-frame alternative
    turns the field far past this knee, so they are all equally scrambled.
    """
    curve = dict(spin.saturation("meridian", marker))
    # Small angles read as motion: the measure still grows with the angle.
    assert curve[1.0] < curve[5.0] < curve[20.0]
    # Large ones do not: a 120 degree join is no worse than a 45 degree one.
    peak = max(curve.values())
    for angle in (45.0, 60.0, 90.0, 120.0, 150.0):
        assert curve[angle] > 0.7 * peak
    assert abs(curve[120.0] - curve[45.0]) < 0.1

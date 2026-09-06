"""The contract between the simulated machine and the drawn one.

These tests are about agreement rather than about physics. The physics core has
its own suite and it passes; what can still go wrong at this seam is that the
renderer is handed a number meaning something slightly different from what it
thinks it means - a socket in the wrong frame, a quaternion in the wrong order,
a bowl whose visible surface is not the surface the solver used. Every one of
those produces a clip that looks fine in a thumbnail and is wrong.
"""

from __future__ import annotations

import json
import math
import os

import pytest

from marble3d.config import DEFAULT_CONFIG
from marble3d.geometry import Transform, quat_rotate
from marble3d.machines import start_bowl_curve
from marble3d.presentation import (
    CONTRACT_VERSION,
    PRESENTATION_SCALE,
    VISUAL_ASSETS,
    check_against_replay,
    golden_vectors,
    presentation_for_machine,
    to_render_angular_velocity,
    to_render_direction,
    to_render_position,
    to_render_quaternion,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECORDED_AXES = os.path.join(
    REPO_ROOT, "docs", "validation", "marble_v1", "godot_axes.json"
)

# Godot stores a Vector3 as three float32s, so two engines that agree perfectly
# in exact arithmetic still differ in the seventh significant figure. The
# tolerance is therefore relative to the magnitude of the coordinate, not a
# flat epsilon: the start chute sits 16.5 units out, where float32 resolution
# is already 1e-6.
FLOAT32_RELATIVE = 2.0e-6


@pytest.fixture(scope="module")
def machine():
    return start_bowl_curve()


@pytest.fixture(scope="module")
def contract(machine):
    return presentation_for_machine(machine, DEFAULT_CONFIG.marble.radius)


# --- coordinates ----------------------------------------------------------


def test_the_conversion_is_the_identity():
    """Both engines are right-handed, +Y up, quaternions xyzw."""
    point = (1.25, -3.5, 7.75)
    assert to_render_position(point) == point
    assert to_render_direction(point) == point
    assert to_render_angular_velocity(point) == point
    spin = (0.1, -0.2, 0.3, 0.927)
    assert to_render_quaternion(spin) == spin


def test_presentation_scale_is_one_and_documented():
    assert PRESENTATION_SCALE == 1.0


def test_golden_vectors_are_self_consistent():
    """Each case's recorded answer is what rotating it actually gives."""
    golden = golden_vectors()
    assert len(golden["cases"]) >= 5
    for case in golden["cases"]:
        expected = quat_rotate(case["quaternion"], case["point"])
        for axis in range(3):
            assert case["rotated"][axis] == pytest.approx(expected[axis], abs=1e-12)


def test_golden_vectors_would_catch_a_swapped_axis():
    """A test that cannot fail is not a test.

    If the conversion silently swapped Y and Z, or read the quaternion as
    wxyz, at least one golden case must move. Checking that here means the
    cross-engine comparison below is worth running.
    """
    golden = golden_vectors()
    for case in golden["cases"]:
        rotated = case["rotated"]
        swapped = [rotated[0], rotated[2], rotated[1]]
        reordered = quat_rotate(
            [case["quaternion"][3]] + list(case["quaternion"][:3]), case["point"]
        )
        if any(abs(a - b) > 1e-9 for a, b in zip(rotated, swapped)) and any(
            abs(a - b) > 1e-9 for a, b in zip(rotated, reordered)
        ):
            return
    pytest.fail("no golden case distinguishes a swapped axis or a wxyz read")


def test_godot_agrees_with_python_about_the_axes():
    """The recorded answer Godot gave, against the one Python computes.

    The JSON is produced by `godot/scripts/marble3d_axis_check.gd` and
    committed, so this runs without a GPU. Re-record it with:

        godot --path godot res://scenes/Marble3DAxisCheck.tscn -- \\
            --golden=<golden.json> --out=docs/validation/marble_v1/godot_axes.json
    """
    if not os.path.exists(RECORDED_AXES):
        pytest.skip("no recorded Godot axis check")
    with open(RECORDED_AXES, encoding="utf-8") as handle:
        recorded = json.load(handle)

    assert recorded["up"] == [0.0, 1.0, 0.0]
    # +X cross +Y is +Z in a right-handed frame, which is what PyBullet is.
    assert recorded["handedness_cross_x_y"] == pytest.approx([0.0, 0.0, 1.0], abs=1e-6)

    golden = {case["name"]: case for case in golden_vectors()["cases"]}
    assert set(golden) == {case["name"] for case in recorded["cases"]}

    for case in recorded["cases"]:
        expected = golden[case["name"]]["rotated"]
        scale = max(1.0, max(abs(value) for value in expected))
        # All three ways the render path applies a rotation: the quaternion on
        # a vector, a Basis built from it, and a Transform3D carrying it.
        for key in ("rotated", "rotated_basis", "rotated_transform"):
            for axis in range(3):
                assert case[key][axis] == pytest.approx(
                    expected[axis], abs=FLOAT32_RELATIVE * scale
                ), f"{case['name']}.{key} axis {axis}"


# --- the contract ---------------------------------------------------------


def test_every_module_has_an_authored_asset(contract):
    assert [module.module_id for module in contract.modules] == ["bowl", "start", "curve"]
    for module in contract.modules:
        assert module.visual_asset == VISUAL_ASSETS[module.module_type]
        assert module.visual_asset


def test_contract_json_is_serialisable_and_versioned(contract):
    payload = contract.to_json()
    assert payload["contract_version"] == CONTRACT_VERSION
    assert payload["scale"] == 1.0
    assert payload["marble_radius"] == DEFAULT_CONFIG.marble.radius
    # Must survive a round trip through the file Godot actually reads.
    assert json.loads(json.dumps(payload)) == payload


def test_the_contract_is_a_pure_function_of_the_machine():
    """Two builds of the same machine give byte-identical contracts.

    Renders are meant to be reproducible from a seed, and a contract that
    picked up an iteration order or a float accumulated in a different order
    would break that quietly.
    """
    first = presentation_for_machine(
        start_bowl_curve(), DEFAULT_CONFIG.marble.radius
    ).to_json()
    second = presentation_for_machine(
        start_bowl_curve(), DEFAULT_CONFIG.marble.radius
    ).to_json()
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_sockets_are_world_space_not_local(contract):
    """The bug this contract exists to prevent.

    A module's sockets are serialised in its own frame and its transform in
    world, so anything reading a socket straight out of the replay places it at
    the origin for whichever module happens to be anchored. The chute's exit is
    (0, 0, 0) locally and a long way from it in the world.
    """
    start = contract.module("start")
    exit_socket = start.sockets["exit"]
    assert exit_socket["position"] != [0.0, 0.0, 0.0]
    for axis in range(3):
        assert exit_socket["position"][axis] == pytest.approx(
            start.origin[axis], abs=1e-9
        )


def test_joined_sockets_meet_in_world_space(contract):
    """What `Machine.connect` promised, checked in the frame the renderer uses.

    If these two ever stop coinciding, the authored chute pours marbles at a
    bowl that is somewhere else.
    """
    start_exit = contract.module("start").sockets["exit"]["position"]
    bowl_entry = contract.module("bowl").sockets["entry"]["position"]
    for axis in range(3):
        assert start_exit[axis] == pytest.approx(bowl_entry[axis], abs=1e-9)

    bowl_drain = contract.module("bowl").sockets["drain"]["position"]
    curve_entry = contract.module("curve").sockets["entry"]["position"]
    fall = bowl_drain[1] - curve_entry[1]
    assert fall == pytest.approx(2.5, abs=1e-9)
    for axis in (0, 2):
        assert bowl_drain[axis] == pytest.approx(curve_entry[axis], abs=1e-9)


def test_socket_frames_are_orthonormal(contract):
    """Flow and up come out of a quaternion, so they must stay a frame."""
    for module in contract.modules:
        for name, socket in module.sockets.items():
            flow = socket["flow"]
            up = socket["up"]
            label = f"{module.module_id}.{name}"
            assert math.sqrt(sum(v * v for v in flow)) == pytest.approx(1.0, abs=1e-9), label
            assert math.sqrt(sum(v * v for v in up)) == pytest.approx(1.0, abs=1e-9), label
            assert sum(a * b for a, b in zip(flow, up)) == pytest.approx(0.0, abs=1e-9), label


def test_module_bounds_contain_their_own_sockets(contract):
    """A socket outside its module's box means one of the two is wrong."""
    for module in contract.modules:
        low, high = module.bounds
        for name, socket in module.sockets.items():
            for axis in range(3):
                value = socket["position"][axis]
                assert low[axis] - 1e-6 <= value <= high[axis] + 1e-6, (
                    f"{module.module_id}.{name} axis {axis} is outside the module bounds"
                )


def test_machine_bounds_contain_every_module(contract):
    low, high = contract.bounds
    for module in contract.modules:
        for axis in range(3):
            assert module.bounds[0][axis] >= low[axis] - 1e-6
            assert module.bounds[1][axis] <= high[axis] + 1e-6


# --- the bowl the renderer draws -----------------------------------------


def test_the_visible_dish_runs_out_to_the_containing_radius(contract):
    """Not to the rim radius.

    The collider is an open surface with no wall on it. Nothing stops a marble
    at the rim; what contains the run is the dish still climbing beyond it. A
    visual bowl that stopped at the rim would have marbles on a slope nobody
    drew, which is the single most likely way this integration looks broken.
    """
    visual = contract.module("bowl").visual
    anchors = contract.module("bowl").anchors
    assert visual["outer_radius"] == anchors["max_radius"]
    assert visual["outer_radius"] > visual["inner_radius"]


def test_the_visible_dish_is_the_solved_surface(contract):
    """The asset's profile, checked against the solver's own height function."""
    visual = contract.module("bowl").visual
    inner = visual["inner_radius"]
    depth = visual["depth"]
    power = visual["profile_power"]
    outer = visual["outer_radius"]

    assert visual["outer_depth"] == pytest.approx(depth * (outer / inner) ** power)
    # And the authored cosine really is a different surface, which is why the
    # asset had to be given the exponent rather than left alone.
    midway = 0.5 * inner
    solved = depth * (midway / inner) ** power
    authored = depth * (1.0 - (0.5 + 0.5 * math.cos(0.5 * math.pi)))
    assert abs(solved - authored) > 2.0 * DEFAULT_CONFIG.marble.radius


def test_the_bowl_reports_where_its_drain_is(contract):
    anchors = contract.module("bowl").anchors
    assert anchors["drain_radius"] > 0.0
    assert anchors["shaft_bottom"] < 0.0
    assert anchors["drain_radius"] >= DEFAULT_CONFIG.marble.radius


# --- what the other two assets are handed --------------------------------


def test_the_curve_hands_over_the_swept_frames(contract):
    """Not a spline through control points - the frames the collider used."""
    visual = contract.module("curve").visual
    centreline = visual["centreline"]
    assert len(centreline) >= 8
    # The samples run from slightly before the arc to its end: the catch scoop
    # reaches back under the drain to meet the falling marble, and that reach
    # is a negative fraction of the sweep. The span must cover the whole arc
    # and the frames must be in order.
    assert centreline[0]["t"] < 0.0
    assert centreline[-1]["t"] == pytest.approx(1.0)
    fractions = [sample["t"] for sample in centreline]
    assert fractions == sorted(fractions)
    assert len(set(fractions)) == len(fractions)
    for sample in centreline:
        assert len(sample["position"]) == 3
        assert len(sample["rotation"]) == 4
        norm = math.sqrt(sum(v * v for v in sample["rotation"]))
        assert norm == pytest.approx(1.0, abs=1e-9)


def test_the_curve_actually_banks(contract):
    """If the drawn channel does not bank, marbles ride up its wall."""
    visual = contract.module("curve").visual
    assert visual["bank_deg"] > 5.0
    ups = []
    for sample in visual["centreline"]:
        up = quat_rotate(sample["rotation"], (0.0, 1.0, 0.0))
        ups.append(up)
    tilted = [up for up in ups if abs(up[1] - 1.0) > 1e-3]
    assert len(tilted) > len(ups) // 2, "most of the channel should be banked"


def test_the_curve_channel_admits_a_marble(contract):
    visual = contract.module("curve").visual
    assert visual["half_width"] > DEFAULT_CONFIG.marble.radius


def test_the_start_bays_are_where_the_marbles_rest(contract):
    """The bays are not authored positions, they are the solver's tick zero."""
    visual = contract.module("start").visual
    bays = visual["bays"]
    assert len(bays) == 8
    assert [bay["index"] for bay in bays] == list(range(8))
    # Single file along the chute, not eight abreast. The gap between two bays
    # is the 1.2 pitch plus the height the incline drops over it, so it is
    # slightly more than the pitch and identical for every pair - which is the
    # thing worth asserting, because eight bays abreast would not be evenly
    # spaced along a line at all.
    pitch = float(visual["marble_spacing"])
    gaps = [
        math.dist(before["position"], after["position"])
        for before, after in zip(bays, bays[1:])
    ]
    assert min(gaps) == pytest.approx(max(gaps), abs=1e-9)
    assert pitch <= gaps[0] <= pitch * 1.05
    # And they must not overlap, or the chute would start with a jam.
    assert gaps[0] >= 2.0 * DEFAULT_CONFIG.marble.radius


def test_the_start_hands_over_the_swept_chute(contract):
    """The drawn chute floor is the solved chute floor, not a straight ramp.

    The chute has two slopes joined by a blend, so `incline_deg` describes none
    of it exactly. A renderer given only that number would draw a straight ramp
    at the mean angle, and the place a straight line through this curve is
    furthest from it is the exit - which is the end the marbles leave from and
    the end the eye is on.
    """
    visual = contract.module("start").visual
    centreline = visual["centreline"]
    assert len(centreline) >= 8

    fractions = [sample["t"] for sample in centreline]
    assert fractions == sorted(fractions)
    assert fractions[0] == pytest.approx(0.0)
    assert fractions[-1] == pytest.approx(1.0)

    # Flow order: the last sample is the exit, and it is the exit socket.
    exit_socket = contract.module("start").sockets["exit"]
    assert centreline[-1]["position"] == pytest.approx(exit_socket["position"])

    # It descends the whole way, and never climbs.
    heights = [sample["position"][1] for sample in centreline]
    assert heights == sorted(heights, reverse=True)

    # And it is not a straight line. If it were, the mid sample would sit on
    # the chord between the ends - this asserts the blend survives the trip
    # through the contract, which is the whole reason it is exported.
    first = centreline[0]["position"]
    last = centreline[-1]["position"]
    middle = centreline[len(centreline) // 2]["position"]
    chord = [
        0.5 * (start + finish) for start, finish in zip(first, last)
    ]
    assert math.dist(middle, chord) > 0.05


def test_the_start_chute_carries_its_marbles(contract):
    """Every bay sits over the drawn floor, one radius up, in the chute."""
    visual = contract.module("start").visual
    centreline = [sample["position"] for sample in visual["centreline"]]
    radius = DEFAULT_CONFIG.marble.radius
    half_width = 0.5 * float(visual["channel_width"])

    for bay in visual["bays"]:
        gap = min(math.dist(bay["position"], point) for point in centreline)
        # A marble resting on the floor is one radius off the centreline, and
        # the centreline is sampled coarsely enough that the nearest sample can
        # be a little along the run from it as well as below it.
        assert radius <= gap <= radius + half_width + 0.5


def test_the_gate_is_wide_enough_to_close_the_chute(contract):
    """A bar narrower than the channel is a bar the queue rolls around."""
    visual = contract.module("start").visual
    half = visual["gate_half_extents"]
    assert 2.0 * half[2] >= float(visual["channel_width"])
    assert 2.0 * half[1] >= 2.0 * DEFAULT_CONFIG.marble.radius


def test_the_gate_keeps_the_rotation_the_replay_drops(contract):
    """`LinearGate.to_json()` writes only the rest position.

    A renderer rebuilding the gate from the replay alone draws an unrotated box
    lying across a chute that is turned a long way off axis, so the contract
    carries the pose the replay loses.
    """
    actuators = contract.module("start").actuators
    assert len(actuators) == 1
    gate = actuators[0]
    assert gate["name"] == "gate"
    rotation = gate["rest"]["rotation"]
    assert rotation != [0.0, 0.0, 0.0, 1.0]
    assert math.sqrt(sum(v * v for v in rotation)) == pytest.approx(1.0, abs=1e-9)
    assert gate["duration"] > 0.0
    assert any(abs(v) > 1e-9 for v in gate["travel"])


# --- against a real replay ------------------------------------------------


def test_contract_agrees_with_a_replay_of_the_same_machine(tmp_path, machine, contract):
    """The anti-drift check the driver refuses to render without."""
    from marble3d.simulation import simulate

    replay = simulate(seed=1, machine=machine, marble_count=8)
    payload = json.loads(json.dumps(replay.to_json()))
    assert check_against_replay(contract, payload) == []


def test_a_contract_for_a_different_machine_is_rejected(contract):
    """The check has to be able to fail, or it is decoration."""
    broken = json.loads(json.dumps({"machine": {"name": "start_bowl_curve", "modules": []}}))
    assert check_against_replay(contract, broken) != []

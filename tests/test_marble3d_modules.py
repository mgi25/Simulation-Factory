"""The module contract, socket algebra, and the machine they compose into.

Section 16 and 17 of the brief. The property being defended is that a module's
place in the world is derived and never typed: joins close exactly, moving one
module moves everything downstream of it, and a join whose two sides do not
admit the same marble is a build error rather than a jam that shows up on one
seed in fifty.
"""

from __future__ import annotations

import math

import pytest

from marble3d.geometry import DROP, GUIDED, Transform
from marble3d.machine import Machine
from marble3d.machines import DRAIN_FALL, start_bowl_curve
from marble3d.modules.base import LinearGate, MarbleModule
from marble3d.modules.bowl import BowlModule, BowlSpec
from marble3d.modules.curve import CurveModule, CurveSpec, bank_for_speed
from marble3d.modules.start import StartModule, StartSpec
from marble3d.units import GRAVITY, MARBLE_DIAMETER, MARBLE_RADIUS


# --- socket algebra ------------------------------------------------------


def test_a_guided_join_closes_exactly() -> None:
    machine = start_bowl_curve()
    exit_socket = machine.modules["start"].socket("exit")
    entry_socket = machine.modules["bowl"].socket("entry")
    assert math.dist(exit_socket.frame.position, entry_socket.frame.position) < 1e-9
    assert exit_socket.flow() == pytest.approx(entry_socket.flow(), abs=1e-9)
    assert exit_socket.up() == pytest.approx(entry_socket.up(), abs=1e-9)


def test_a_drop_join_falls_straight_down_and_keeps_its_own_pitch() -> None:
    machine = start_bowl_curve()
    drain = machine.modules["bowl"].socket("drain")
    catch = machine.modules["curve"].socket("entry")
    assert drain.frame.position[1] - catch.frame.position[1] == pytest.approx(DRAIN_FALL)
    assert drain.frame.position[0] == pytest.approx(catch.frame.position[0], abs=1e-9)
    assert drain.frame.position[2] == pytest.approx(catch.frame.position[2], abs=1e-9)
    assert drain.heading() == pytest.approx(catch.heading(), abs=1e-9)


def test_moving_the_anchor_moves_the_whole_machine_with_it() -> None:
    """The property a procedural generator needs and a file of coordinates cannot."""
    offset = Transform((13.0, -4.0, 7.0))
    machine = Machine("shifted")
    bowl = machine.add(BowlModule("bowl"), offset)
    start = machine.add(StartModule("start"))
    curve = machine.add(CurveModule("curve"))
    machine.connect(start, "exit", bowl, "entry")
    machine.connect(bowl, "drain", curve, "entry", fall=DRAIN_FALL)

    reference = start_bowl_curve()
    for name in ("start", "bowl", "curve"):
        moved = machine.modules[name].transform.position
        original = reference.modules[name].transform.position
        assert moved == pytest.approx(
            tuple(a + b for a, b in zip(original, offset.position)), abs=1e-9
        )


def test_exactly_one_module_may_be_anchored() -> None:
    machine = Machine("two_anchors")
    bowl = machine.add(BowlModule("bowl"), Transform())
    start = machine.add(StartModule("start"), Transform())
    with pytest.raises(ValueError, match="both already placed"):
        machine.connect(start, "exit", bowl, "entry")


def test_a_machine_with_nothing_anchored_refuses_to_connect() -> None:
    machine = Machine("floating")
    bowl = machine.add(BowlModule("bowl"))
    start = machine.add(StartModule("start"))
    with pytest.raises(ValueError, match="neither placed"):
        machine.connect(start, "exit", bowl, "entry")


def test_a_guided_join_between_different_widths_is_refused() -> None:
    machine = Machine("stepped")
    bowl = machine.anchor(BowlModule("bowl"))
    narrow = machine.add(StartModule("start", StartSpec(width=1.05 * MARBLE_DIAMETER)))
    with pytest.raises(ValueError, match="the two sides have to be the same width"):
        machine.connect(narrow, "exit", bowl, "entry")


def test_a_catch_narrower_than_the_drain_that_feeds_it_is_refused() -> None:
    machine = Machine("pinched")
    bowl = machine.anchor(BowlModule("bowl"))
    pinched = machine.add(CurveModule("curve", CurveSpec(catch_width=2.0 * MARBLE_DIAMETER)))
    with pytest.raises(ValueError, match="the catch below is only"):
        machine.connect(bowl, "drain", pinched, "entry", fall=DRAIN_FALL)


def test_a_drop_join_needs_somewhere_to_fall_from() -> None:
    machine = Machine("no_fall")
    bowl = machine.anchor(BowlModule("bowl"))
    curve = machine.add(CurveModule("curve"))
    with pytest.raises(ValueError, match="positive fall"):
        machine.connect(bowl, "drain", curve, "entry", fall=0.0)


def test_an_unplaced_module_is_caught_before_it_is_built() -> None:
    machine = Machine("loose")
    machine.anchor(BowlModule("bowl"))
    machine.add(CurveModule("curve"))
    with pytest.raises(ValueError, match="unplaced modules"):
        machine.require_placed()


def test_module_occupancy_prefers_the_smaller_box_and_then_sticks() -> None:
    machine = start_bowl_curve()
    bowl = machine.modules["bowl"]
    curve = machine.modules["curve"]
    overlap = curve.socket("entry").frame.position
    assert bowl.bounds().contains(overlap) or curve.bounds().contains(overlap)
    # With no history, the smaller box wins where they overlap.
    assert machine.module_at(overlap) == "curve"
    # With history, a marble already in the bowl stays in it while it can.
    inside_bowl = (0.0, -1.0, 0.0)
    assert machine.module_at(inside_bowl, "bowl") == "bowl"


# --- the bowl ------------------------------------------------------------


def test_the_drain_lip_is_tangent_to_the_dish_where_they_meet() -> None:
    bowl = BowlModule()
    radius = bowl.lip_contact_radius
    # The fillet arc's slope at the contact point equals the dish's slope; the
    # solver asserts its own residual, and this checks the geometry it produced.
    assert radius > bowl.spec.drain_radius
    assert bowl.drain_rim_height < bowl.spec.height(radius)


def test_the_drain_passes_a_marble_and_the_bowl_says_so_if_it_does_not() -> None:
    assert BowlModule().spec.drain_radius > MARBLE_RADIUS
    with pytest.raises(ValueError, match="does not pass"):
        BowlModule("tiny", BowlSpec(drain_radius=0.4 * MARBLE_RADIUS))


def test_the_spout_never_dips_below_the_dish_it_lands_on() -> None:
    bowl = BowlModule()
    for distance, clearance in bowl.spout_clearance_profile():
        assert clearance >= 0.0, f"spout is {-clearance:.3f} below the dish at {distance:.2f}"


def test_the_spout_lands_on_the_outer_wall_and_not_across_the_orbit() -> None:
    """Where a marble is released into a bowl is not a free parameter.

    A spout landing part-way across the dish is a bridge over the orbit path,
    and an orbiting marble hits its underside. This asserts the release is at
    the rim, which is where the geometry keeps out of its own way and where a
    real vortex funnel is fed.
    """
    spec = BowlModule().spec
    assert spec.rim_radius < spec.entry_radius < spec.max_radius


def test_the_bowl_tessellation_meets_its_sagitta_budget() -> None:
    bowl = BowlModule()
    assert bowl.sagitta <= 0.02 + 1e-12
    assert bowl.sagitta / MARBLE_RADIUS < 0.05


def test_the_steepest_wall_is_still_a_wall_a_marble_can_roll_on() -> None:
    from marble3d.config import DEFAULT_CONFIG
    from marble3d.materials import rolling_threshold

    bowl = BowlModule()
    assert rolling_threshold(bowl.spec.steepest_angle()) < DEFAULT_CONFIG.marble.surface_friction


# --- the start -----------------------------------------------------------


def test_the_chute_is_level_at_its_mouth_so_the_bowl_sets_the_feed_angle() -> None:
    spec = StartSpec()
    assert spec.slope(0.0) == pytest.approx(0.0)
    assert spec.slope(spec.length) == pytest.approx(spec.shelf_slope)


def test_the_chute_profile_is_continuous_in_slope() -> None:
    spec = StartSpec()
    for distance in (spec.transition, spec.gate_offset - spec.shelf_blend, spec.gate_offset):
        before = spec.slope(distance - 1e-6)
        after = spec.slope(distance + 1e-6)
        assert before == pytest.approx(after, abs=1e-4)
        # And the height agrees from both sides too.
        assert spec.height(distance - 1e-6) == pytest.approx(
            spec.height(distance + 1e-6), abs=1e-6
        )


def test_the_queue_fits_on_the_shelf_and_does_not_overlap() -> None:
    start = StartModule()
    positions = [transform.position for transform in start.marble_starts()]
    assert len(positions) == start.spec.marble_count
    for first, second in zip(positions, positions[1:]):
        assert math.dist(first, second) > MARBLE_DIAMETER
    with pytest.raises(ValueError, match="of chute behind the exit"):
        StartModule("long", StartSpec(marble_count=40))
    with pytest.raises(ValueError, match="start overlapping"):
        StartModule("tight", StartSpec(marble_spacing=0.9 * MARBLE_DIAMETER))


def test_the_shelf_keeps_the_whole_field_below_orbit_speed() -> None:
    """The measurement that sets `shelf_slope`, as a test.

    On the running incline an eight-marble queue spreads over enough height
    that the back of the field arrives above the bowl's circular-orbit speed
    and climbs out over the dish edge. On the shelf it does not.
    """
    machine = start_bowl_curve()
    start = machine.modules["start"]
    bowl = machine.modules["bowl"]
    radius = bowl.spec.entry_radius
    orbit = math.sqrt(GRAVITY * radius * bowl.spec.slope(radius) / 1.4)
    spout = (
        bowl.spec.height(bowl.spec.max_radius)
        + bowl.spec.spout_clearance
        - bowl.spec.height(radius)
    )
    speeds = [
        math.sqrt(10.0 * GRAVITY * (start.release_drop(index) + spout) / 7.0)
        for index in range(start.spec.marble_count)
    ]
    assert max(speeds) < orbit, f"the back of the field enters at {max(speeds):.1f} of {orbit:.1f}"
    assert min(speeds) > 0.7 * orbit, "the front of the field barely orbits at all"


# --- actuation -----------------------------------------------------------


def test_an_actuator_pose_is_a_pure_function_of_the_tick() -> None:
    gate = LinearGate("gate", (0.1, 1.0, 1.0), Transform(), (0.0, -3.0, 0.0), 0.2, 0.1)
    dt = 1.0 / 240.0
    # Same tick, same answer, whatever order it is asked in.
    ticks = [0, 500, 48, 96, 500, 0]
    poses = [gate.pose_at(tick, dt) for tick in ticks]
    assert poses[0].position == poses[-1].position
    assert poses[1].position == poses[4].position
    # Clamped at both ends and monotone in between.
    assert gate.pose_at(0, dt).position[1] == pytest.approx(0.0)
    assert gate.pose_at(10_000, dt).position[1] == pytest.approx(-3.0)
    heights = [gate.pose_at(tick, dt).position[1] for tick in range(0, 120)]
    assert all(later <= earlier + 1e-12 for earlier, later in zip(heights, heights[1:]))


def test_the_gate_starts_closed_and_ends_clear_of_the_channel() -> None:
    start = StartModule()
    gate = start.local_actuators()[0]
    dt = 1.0 / 240.0
    closed = gate.pose_at(0, dt)
    open_pose = gate.pose_at(10_000, dt)
    assert closed.position[1] - open_pose.position[1] > MARBLE_DIAMETER + gate.half_extents[1]


def test_a_gate_needs_a_positive_release_duration() -> None:
    with pytest.raises(ValueError, match="positive amount of time"):
        LinearGate("gate", (0.1, 1.0, 1.0), Transform(), (0.0, -1.0, 0.0), 0.0, 0.0)


# --- the curve -----------------------------------------------------------


def test_the_curve_runs_underneath_the_bowl() -> None:
    """The demonstration the whole module exists for.

    A height field is single-valued, so it cannot have a bowl above and a
    channel below at the same (x, z). Every sampled point of this curve does.
    """
    machine = start_bowl_curve()
    bowl = machine.modules["bowl"]
    curve = machine.modules["curve"]
    under = 0
    samples = 41
    for index in range(samples):
        frame = curve.transform.compose(curve.frame_at(index / (samples - 1)))
        x, y, z = frame.position
        radius = math.hypot(x, z)
        if radius <= bowl.spec.max_radius and y < bowl.spec.height(radius):
            under += 1
    assert under == samples


def test_the_curve_descends_the_whole_way_and_is_level_at_its_exit() -> None:
    curve = CurveModule()
    heights = [curve.height(index / 200.0) for index in range(201)]
    assert all(later <= earlier + 1e-9 for earlier, later in zip(heights, heights[1:]))
    assert curve.height(1.0) == pytest.approx(-curve.spec.drop)
    assert curve.gradient_at(1.0) == pytest.approx(0.0, abs=1e-12)
    assert curve.gradient_at(0.0) < -0.05, "a level catch is a catch marbles pile up in"


def test_a_non_monotone_descent_is_refused() -> None:
    with pytest.raises(ValueError, match="non-monotone"):
        CurveModule("flat", CurveSpec(entry_gradient=0.05))


def test_the_catch_reaches_back_past_the_hole_that_feeds_it() -> None:
    """A marble leaving a drain travels wherever its last orbit pointed it.

    The first version of this module started its geometry at the entry socket,
    marbles left the drain moving *backwards* relative to the channel, landed
    behind where the geometry began and fell through the machine.
    """
    machine = start_bowl_curve()
    curve = machine.modules["curve"]
    bowl = machine.modules["bowl"]
    assert curve.spec.lead_in > bowl.spec.drain_radius + MARBLE_RADIUS
    behind = curve.frame_at(-curve.spec.lead_in / curve.spec.arc_length)
    assert behind.position[1] > curve.frame_at(0.0).position[1]


def test_the_bank_angle_comes_from_a_speed() -> None:
    spec = CurveSpec()
    assert spec.bank_angle() == pytest.approx(bank_for_speed(spec.design_speed, spec.radius))
    assert math.tan(spec.bank_angle()) == pytest.approx(
        spec.design_speed**2 / (GRAVITY * spec.radius)
    )
    # The bank ramps to zero at both ends, so both sockets have no *roll*: the
    # across-channel axis is horizontal. Their pitch is another matter - the
    # catch is deliberately sloped and the exit is deliberately level - so the
    # thing to check is the roll and not the up vector.
    curve = CurveModule()
    for name in ("entry", "exit"):
        across = curve.socket(name).frame.axes()[2]
        assert across[1] == pytest.approx(0.0, abs=1e-9), f"{name} socket is banked"
    assert curve.socket("exit").up() == pytest.approx((0.0, 1.0, 0.0), abs=1e-9)
    assert curve.socket("entry").up()[1] < 1.0


# --- the contract itself -------------------------------------------------


def test_a_module_reports_a_useful_error_for_an_unknown_socket() -> None:
    with pytest.raises(KeyError, match="has no socket"):
        BowlModule().socket("outflow")


def test_every_module_serialises_its_own_description() -> None:
    machine = start_bowl_curve()
    payload = machine.to_json()
    assert [module["id"] for module in payload["modules"]] == ["bowl", "start", "curve"]
    for module in payload["modules"]:
        assert module["type"]
        assert module["sockets"]
        assert len(module["bounds"]) == 2
    assert [connection["kind"] for connection in payload["connections"]] == [GUIDED, DROP]


def test_a_module_without_geometry_says_so_rather_than_guessing() -> None:
    class Hollow(MarbleModule):
        def local_sockets(self):
            return {}

        def local_colliders(self):
            return []

    with pytest.raises(ValueError, match="neither colliders nor bounds"):
        Hollow("hollow").local_bounds()

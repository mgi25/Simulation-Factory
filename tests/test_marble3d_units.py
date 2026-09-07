"""The unit convention and the transform algebra module composition rests on.

These are the cheapest tests in the package and they guard the most. Every
clearance, margin and speed in `marble3d` is quoted against the marble, so a
change to the scale that did not change the marble would silently rescale the
machine; and every module is placed by composing socket frames, so a quaternion
that is subtly wrong puts the bowl somewhere plausible rather than somewhere
obviously wrong.
"""

from __future__ import annotations

import math

import pytest

from marble3d import units
from marble3d.geometry import (
    DROP,
    GUIDED,
    Socket,
    Transform,
    basis_from_forward_up,
    quat_from_axis_angle,
    quat_multiply,
    quat_rotate,
    yaw_quaternion,
)


def test_the_marble_is_exactly_one_unit_across() -> None:
    assert units.MARBLE_RADIUS == pytest.approx(0.5)
    assert units.MARBLE_DIAMETER == pytest.approx(1.0)


def test_gravity_is_the_similarity_scaling_of_one_g() -> None:
    # Not 9.81, and the reason is the whole of units.py: lengths and gravity
    # scale by the same factor so that time is invariant.
    assert units.GRAVITY == pytest.approx(units.STANDARD_GRAVITY * units.SIMILARITY_SCALE)
    assert units.GRAVITY == pytest.approx(245.25)


def test_the_convention_round_trips_to_the_toy_it_models() -> None:
    assert units.to_toy_metres(units.MARBLE_RADIUS) == pytest.approx(units.TOY_MARBLE_RADIUS_M)
    assert units.from_toy_metres(0.02) == pytest.approx(units.MARBLE_RADIUS)


def test_free_fall_timing_matches_the_toy_it_models() -> None:
    """The point of scaling gravity: a drop takes the same time at both scales.

    A marble falling one marble diameter in this world, and a real marble
    falling one real diameter under 9.81, take the same number of seconds. If
    they did not, every replay would play back at the wrong tempo and the
    scaling would be a cosmetic claim.
    """
    world_time = math.sqrt(2.0 * units.MARBLE_DIAMETER / units.GRAVITY)
    toy_time = math.sqrt(
        2.0 * (2.0 * units.TOY_MARBLE_RADIUS_M) / units.STANDARD_GRAVITY
    )
    assert world_time == pytest.approx(toy_time, rel=1e-12)


def test_free_fall_speed_is_the_textbook_one() -> None:
    assert units.free_fall_speed(10.0) == pytest.approx(math.sqrt(2 * units.GRAVITY * 10.0))


# --- transforms ----------------------------------------------------------


def test_a_transform_and_its_inverse_cancel() -> None:
    transform = Transform((3.0, -4.0, 5.0), quat_from_axis_angle((0.3, 1.0, 0.2), 0.7))
    point = (1.0, -2.0, 0.5)
    assert transform.inverse().apply(transform.apply(point)) == pytest.approx(point, abs=1e-12)


def test_composition_applies_the_inner_transform_first() -> None:
    outer = Transform((1.0, 0.0, 0.0), yaw_quaternion(math.pi / 2))
    inner = Transform((0.0, 0.0, 2.0))
    combined = outer.compose(inner)
    # yaw(+90) sends +X to -Z and +Z to +X, so the inner offset along +Z ends
    # up along +X before the outer translation is added.
    assert combined.apply((0.0, 0.0, 0.0)) == pytest.approx((3.0, 0.0, 0.0), abs=1e-12)


def test_a_basis_survives_a_half_turn() -> None:
    """The case the naive quaternion-from-matrix formula loses all precision on.

    A socket pointing back along -X is a 180-degree rotation, which is exactly
    where `w = sqrt(1 + trace) / 2` divides by zero. Shepperd's branch selection
    is why `quat_from_basis` picks a different denominator there.
    """
    rotation = basis_from_forward_up((-1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    assert quat_rotate(rotation, (1.0, 0.0, 0.0)) == pytest.approx((-1.0, 0.0, 0.0), abs=1e-12)
    assert quat_rotate(rotation, (0.0, 1.0, 0.0)) == pytest.approx((0.0, 1.0, 0.0), abs=1e-12)


def test_a_socket_frame_is_right_handed_and_forward_is_x() -> None:
    forward = (0.3, -0.4, 0.8)
    rotation = basis_from_forward_up(forward, (0.0, 1.0, 0.0))
    x_axis = quat_rotate(rotation, (1.0, 0.0, 0.0))
    y_axis = quat_rotate(rotation, (0.0, 1.0, 0.0))
    z_axis = quat_rotate(rotation, (0.0, 0.0, 1.0))
    length = math.dist(forward, (0.0, 0.0, 0.0))
    assert x_axis == pytest.approx(tuple(v / length for v in forward), abs=1e-12)
    assert sum(a * b for a, b in zip(x_axis, y_axis)) == pytest.approx(0.0, abs=1e-12)
    cross = (
        x_axis[1] * y_axis[2] - x_axis[2] * y_axis[1],
        x_axis[2] * y_axis[0] - x_axis[0] * y_axis[2],
        x_axis[0] * y_axis[1] - x_axis[1] * y_axis[0],
    )
    assert cross == pytest.approx(z_axis, abs=1e-12)


def test_socket_up_is_orthogonalised_not_taken_as_given() -> None:
    """A descending socket still has an up perpendicular to its flow."""
    socket = Socket("s", Transform((0, 0, 0), basis_from_forward_up((1.0, -1.0, 0.0), (0, 1, 0))))
    assert sum(a * b for a, b in zip(socket.flow(), socket.up())) == pytest.approx(0.0, abs=1e-12)
    assert socket.up()[1] > 0.0


def test_heading_and_yaw_agree_about_which_way_is_which() -> None:
    """`yaw(target - source)` has to actually turn `source` to face `target`.

    The drop join is built on this identity, and getting the sign wrong would
    place a downstream module facing backwards - which reads as a physics
    problem, because the marbles would arrive against the flow.
    """
    for degrees in (0.0, 37.0, 90.0, 180.0, -125.0):
        angle = math.radians(degrees)
        flow = (math.cos(angle), 0.0, -math.sin(angle))
        socket = Socket("s", Transform((0, 0, 0), basis_from_forward_up(flow, (0, 1, 0))))
        assert socket.heading() == pytest.approx(math.remainder(angle, 2 * math.pi), abs=1e-9)

    source = Socket("a", Transform((0, 0, 0), basis_from_forward_up((1, 0, 0), (0, 1, 0))))
    target_angle = math.radians(50.0)
    turned = quat_rotate(
        quat_multiply(yaw_quaternion(target_angle - source.heading()), source.frame.rotation),
        (1.0, 0.0, 0.0),
    )
    assert math.atan2(-turned[2], turned[0]) == pytest.approx(target_angle, abs=1e-9)


def test_a_socket_kind_has_to_be_one_of_the_two() -> None:
    Socket("a", Transform(), kind=GUIDED)
    Socket("b", Transform(), kind=DROP)
    with pytest.raises(ValueError, match="unknown kind"):
        Socket("c", Transform(), kind="teleport")

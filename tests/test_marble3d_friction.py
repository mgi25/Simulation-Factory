"""Friction: what Bullet applies, not what it was told.

Section 11 of the brief. Bullet *multiplies* the two bodies' coefficients, so
neither number set on a body is the coefficient that governs a contact - and
that is not an obscure detail, it is the fourth of the four bugs the physics
lab spent its time on. Setting both the marble and the bowl to the benchmark's
0.15 gave a pair coefficient of 0.0225 against a wall needing 0.230, every
marble skidded the whole way down, and "marbles skid" reads as a finding about
rigid-body physics rather than as an arithmetic mistake.

So none of these tests check that `solve_materials` returns what it returns.
They put a marble on a slope and measure its acceleration.
"""

from __future__ import annotations

import math

import pytest

from marble3d.config import DEFAULT_CONFIG, MarbleConfig
from marble3d.experiments import measure_incline, measure_rolling_resistance
from marble3d.machines import start_bowl_curve
from marble3d.materials import combine, rolling_threshold, solve_materials
from marble3d.units import GRAVITY

pytest.importorskip("pybullet")


def test_the_solved_materials_multiply_to_what_was_asked_for() -> None:
    marble = MarbleConfig()
    solved = solve_materials(marble)
    assert solved.effective_marble_marble_friction() == pytest.approx(marble.friction)
    assert solved.effective_marble_surface_friction() == pytest.approx(marble.surface_friction)
    assert solved.effective_marble_marble_restitution() == pytest.approx(marble.restitution)
    assert solved.effective_marble_surface_restitution() == pytest.approx(
        marble.surface_restitution
    )
    # The naive thing - setting both bodies to the wanted figure - is what the
    # lab did, and this is the number it produces.
    assert combine(marble.friction, marble.friction) == pytest.approx(0.0225)


def test_an_unreachable_pair_coefficient_is_refused() -> None:
    with pytest.raises(ValueError, match="not reachable"):
        solve_materials(MarbleConfig(friction=1e-6, surface_friction=0.5))


@pytest.mark.parametrize("slope", [10.0, 20.0, 30.0, 39.9])
def test_a_marble_rolls_rather_than_skids_on_every_slope_in_the_machine(slope: float) -> None:
    """`(5/7) g sin(theta)`, out of code containing neither 5/7 nor a sine.

    39.9 degrees is the steepest surface the bowl has. A marble that skids
    there instead of rolling looks wrong in a way viewers notice immediately
    even when they cannot say why, and it would halve the energy in an orbit.
    """
    result = measure_incline(slope)
    assert result.measured_acceleration == pytest.approx(result.rolling_prediction, rel=0.02)
    assert result.rolls


def test_the_track_friction_clears_the_rolling_threshold_with_margin() -> None:
    bowl = start_bowl_curve().modules["bowl"]
    needed = rolling_threshold(bowl.spec.steepest_angle())
    assert needed == pytest.approx((2.0 / 7.0) * math.tan(bowl.spec.steepest_angle()))
    assert DEFAULT_CONFIG.marble.surface_friction > 2.0 * needed


def test_below_the_threshold_the_marble_really_does_skid() -> None:
    """The negative control, without which the tests above prove nothing.

    If the measurement could not tell rolling from sliding it would report
    rolling whatever the engine did. Starved of friction the marble has to
    follow the sliding law, and the coefficient recovered from its
    acceleration has to be the one it was given.
    """
    starved = measure_incline(30.0, surface_friction=0.10)
    assert not starved.rolls
    assert starved.measured_acceleration == pytest.approx(
        starved.sliding_prediction, rel=0.10
    )
    assert starved.inferred_friction == pytest.approx(0.10, abs=0.02)


def test_rolling_resistance_comes_from_the_collider_and_not_from_a_knob() -> None:
    """Zero rolling friction, and the tessellation still dissipates.

    A rigid sphere loses energy at every triangle edge it rolls over. Measured
    here as an effective rolling-resistance coefficient, it comes out around
    0.0023 - already above the 0.001 to 0.002 a real glass marble on a hard
    track measures. That is the whole argument for `rolling_friction = 0`: the
    collider is dissipating more than reality on its own.
    """
    assert DEFAULT_CONFIG.marble.rolling_friction == 0.0
    floor = measure_rolling_resistance()
    assert 0.0005 < floor < 0.01, f"tessellation rolling resistance {floor}"


def test_bullets_rolling_friction_cannot_be_calibrated_to_a_coefficient() -> None:
    """Why the knob is off rather than set to a small physical value.

    A rolling-resistance coefficient is a constant: double the coefficient and
    you double the deceleration. Bullet's `rollingFriction` is not - it
    saturates, and at 0.001 it costs an order of magnitude more than the
    physical figure it was reasoned from. There is no value of it that means
    "glass on a hard track".
    """
    floor = measure_rolling_resistance(rolling_friction=0.0)
    small = measure_rolling_resistance(rolling_friction=0.0002)
    assert small > 5.0 * floor


def test_marble_inertia_is_a_solid_sphere() -> None:
    marble = DEFAULT_CONFIG.marble
    assert marble.inertia == pytest.approx(0.4 * marble.mass * marble.radius**2)


def test_the_rolling_and_sliding_laws_cross_at_the_threshold() -> None:
    """A sanity check on the two predictions the measurement is compared to."""
    from marble3d.materials import rolling_acceleration, sliding_acceleration

    for degrees in (5.0, 15.0, 25.0, 35.0):
        angle = math.radians(degrees)
        mu = rolling_threshold(angle)
        assert sliding_acceleration(GRAVITY, angle, mu) == pytest.approx(
            rolling_acceleration(GRAVITY, angle), rel=1e-12
        )

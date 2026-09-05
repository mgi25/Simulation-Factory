"""Collision margins and tunnelling: what the engine does, measured.

Section 7 of the brief in full - the effective marble diameter, the channel
clearance, whether the bowl surface is inflated, and where two marbles make
contact - plus the tunnelling and body-type checks that the production
hardening turned up.

Every test here builds a real Bullet world. They are the slow ones in the
package and they are worth it: the failure they guard against is a scale or a
default that quietly moves a surface, and that is invisible in any test that
does not put a marble on one.
"""

from __future__ import annotations

import pytest

from marble3d.config import DEFAULT_CONFIG
from marble3d.experiments import (
    flat_plane,
    measure_contact_gap,
    measure_contact_separation,
    measure_resting_height,
    measure_tunnelling,
)
from marble3d.units import MARBLE_RADIUS
from marble3d.world import MarbleWorld

pytest.importorskip("pybullet")


def test_a_sphere_is_not_inflated_by_its_collision_margin() -> None:
    """The assumption every clearance in the machine rests on.

    `btSphereShape` carries the collision margin *as* its radius rather than
    outside it, so unlike a box or a trimesh a sphere's collision extent is
    exactly its radius. If that were ever not true on some build, every
    clearance quoted in marble diameters would be wrong by the margin and
    nothing else in the package would notice.
    """
    world = MarbleWorld(DEFAULT_CONFIG)
    try:
        world.add_marble(0, (0.0, 0.0, 0.0))
        bounds = world.aabb(world.marbles[0])
    finally:
        world.close()
    for axis in range(3):
        extent = 0.5 * (bounds.upper[axis] - bounds.lower[axis])
        assert extent == pytest.approx(MARBLE_RADIUS, abs=1e-6)


def test_two_marbles_touch_at_exactly_one_diameter() -> None:
    touching, clear = measure_contact_separation()
    diameter = DEFAULT_CONFIG.marble.diameter
    assert touching <= diameter + 1e-9
    assert clear >= diameter - 1e-9
    assert clear - touching <= 0.005 * diameter


def test_a_marble_rests_on_a_trimesh_at_its_own_radius() -> None:
    error = measure_resting_height()
    assert abs(error) < 0.002 * MARBLE_RADIUS, f"resting height error {error}"


def test_the_resting_height_does_not_depend_on_the_mesh_margin() -> None:
    """The expectation this package started with, and it was wrong.

    "A static trimesh collides one margin outside its triangles, so a marble
    rests one margin high" is the standard account and it does not describe
    this build: split-impulse penetration recovery resolves to contact whatever
    the margin was. Asserted rather than deleted, because the next person to
    reason about margins will start from the same expectation and should find
    out here rather than by chasing a hovering marble that is not hovering.
    """
    heights = [measure_resting_height(margin=margin) for margin in (0.04, 0.001, 0.0)]
    assert max(heights) - min(heights) < 1e-4


def test_the_mesh_margin_is_what_sets_the_contact_generation_distance() -> None:
    """And this is what it *does* change, which is why the policy exists.

    A large margin generates contacts while the marble is still a margin away,
    so in a channel barely wider than a marble it is held off both walls before
    it reaches either. Small at this scale; catastrophic at the lab's, where
    Bullet's default margin was twice the marble radius and a resting marble
    was flung across the bowl.
    """
    tight = measure_contact_gap(margin=DEFAULT_CONFIG.collider.mesh_margin)
    loose = measure_contact_gap(margin=0.04)
    assert loose > tight
    assert tight <= 2.0 * DEFAULT_CONFIG.collider.mesh_margin + 1e-9
    assert loose >= 0.01


def test_a_channel_admits_a_marble_with_the_clearance_it_claims() -> None:
    """A marble dropped into the machine's narrowest channel reaches the floor.

    Stated as a physical outcome rather than as arithmetic on the section,
    because arithmetic on the section is what the margin can invalidate.
    """
    from marble3d.machines import start_bowl_curve

    machine = start_bowl_curve()
    curve = machine.modules["curve"]
    frame = curve.transform.compose(curve.frame_at(0.9))
    world = MarbleWorld(DEFAULT_CONFIG)
    try:
        machine.build(world)
        world.add_marble(0, frame.apply((0.0, 3.0 * MARBLE_RADIUS, 0.0)))
        for _ in range(int(1.0 / DEFAULT_CONFIG.physics.dt)):
            world.step()
        position = world.marble_state(0)[0]
    finally:
        world.close()
    local = curve.transform.compose(curve.frame_at(0.9)).inverse().apply(position)
    # It settled onto the floor rather than being held up by the walls or
    # squeezed out of the channel.
    assert local[1] < 1.2 * MARBLE_RADIUS, f"marble hung up at height {local[1]}"
    assert abs(local[2]) < 0.5 * curve.spec.width


# --- body type and tunnelling -------------------------------------------


def test_marbles_are_rigid_bodies_and_are_not_velocity_clamped() -> None:
    """PyBullet's default body type stops accelerating at 100 wu/s.

    `createMultiBody` builds a `btMultiBody` unless told otherwise, and a
    `btMultiBody`'s base velocity is hard-clamped - measured on this machine at
    exactly 100 - and carries a damping term nobody asked for. A marble that
    has fallen fourteen units is already past the clamp, so a tall machine
    would quietly stop obeying gravity partway down and it would look like
    terminal velocity. `MarbleWorld` passes `useMaximalCoordinates=True`; this
    is what says so.
    """
    world = MarbleWorld(DEFAULT_CONFIG.with_overrides(gravity=0.0))
    try:
        world.add_marble(0, (0.0, 0.0, 0.0), (300.0, 0.0, 0.0))
        before = world.marble_state(0)[0][0]
        world.step()
        after = world.marble_state(0)[0][0]
        speed = world.marble_state(0)[2][0]
    finally:
        world.close()
    assert speed == pytest.approx(300.0, rel=1e-9)
    assert (after - before) * DEFAULT_CONFIG.physics.physics_hz == pytest.approx(300.0, rel=1e-6)


def test_nothing_tunnels_inside_the_configured_travel_budget() -> None:
    """The rate is chosen so the discrete solver already holds.

    Measured onset of discrete-detection failure is about 0.83 marble diameters
    of travel per tick; the budget is 0.5, and this fires a marble at exactly
    the budget through a wall thinner than any in the machine.
    """
    marble = DEFAULT_CONFIG.marble
    speed = marble.travel_budget * marble.diameter * DEFAULT_CONFIG.physics.physics_hz
    assert measure_tunnelling(speed, phases=12, ccd=False) == 0


def test_ccd_covers_the_speeds_the_discrete_solver_does_not() -> None:
    """And the negative control that says the budget is not arbitrary.

    At three times the budget the discrete solver leaks and the swept test does
    not, which is both halves of the argument for the number: the fallback
    works, and the rate is chosen so it never has to.
    """
    marble = DEFAULT_CONFIG.marble
    fast = 3.0 * marble.travel_budget * marble.diameter * DEFAULT_CONFIG.physics.physics_hz
    assert measure_tunnelling(fast, phases=12, ccd=False) > 0
    assert measure_tunnelling(fast, phases=12, ccd=True) == 0


def test_a_collider_reaches_bullet_whole() -> None:
    """Bullet's own bounding box against the mesh that was sent.

    The cheapest possible detector for the truncation class of bug: a mesh that
    arrives short has a smaller box than the one that was handed over.
    """
    from marble3d.validation import check_collider_bounds

    world = MarbleWorld(DEFAULT_CONFIG)
    try:
        world.add_static_mesh(flat_plane(size=50.0, cells=6), owner="floor")
        assert check_collider_bounds(world) == []
        actual = world.aabb(world.colliders[0].body)
        expected = world.colliders[0].expected_bounds
        assert actual.lower[0] <= expected.lower[0] + 1e-6
        assert actual.upper[2] >= expected.upper[2] - 1e-6
    finally:
        world.close()

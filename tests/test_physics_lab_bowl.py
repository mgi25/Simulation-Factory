"""The bowl geometry: the invariants both prototypes are built on top of.

These are not smoke tests. Every one of them is a property that, if it broke,
would silently make the two experiments compare different bowls - which is the
one failure mode this study cannot detect from its own results.
"""

from __future__ import annotations

import math

import pytest

from physics_lab.common.bowl import BowlSurface


def make_bowl(**overrides) -> BowlSurface:
    settings = dict(
        rim_radius=0.50,
        rim_depth=0.18,
        profile_power=2.0,
        drain_radius=0.060,
        marble_radius=0.020,
        surface_max_radius=0.60,
    )
    settings.update(overrides)
    return BowlSurface(**settings)


# --- construction -----------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"rim_radius": 0.0},
        {"rim_depth": -1.0},
        {"profile_power": 1.0},
        {"drain_radius": 0.6},
        {"drain_radius": 0.0},
        {"marble_radius": 0.060},
        {"surface_max_radius": 0.4},
    ],
)
def test_a_bowl_that_could_not_work_is_refused_at_construction(overrides):
    with pytest.raises(ValueError):
        make_bowl(**overrides)


def test_the_lip_meets_the_collider_hole_exactly():
    """The specified drain radius is the hole in the collider, to a nanometre.

    `lip_start` is solved for rather than assumed, so this is the assertion
    that the solve converged - and it is worth having as a test rather than
    only as the internal assert, because the internal one disappears under -O.
    """
    bowl = make_bowl()
    contact_s, _ = bowl.contact_profile(bowl.lip_start)
    assert contact_s == pytest.approx(bowl.drain_radius, abs=1e-9)
    assert bowl.lip_start < bowl.drain_radius
    assert bowl.lip_inner == pytest.approx(bowl.drain_radius - bowl.marble_radius)


# --- the profile ------------------------------------------------------------


def test_the_dish_and_the_lip_join_smoothly():
    """C0 and C1 across `lip_start`.

    A slope discontinuity there would be a step in the tangential gravity, and
    a marble arriving at the drain would get a kick from geometry rather than
    from physics.
    """
    bowl = make_bowl()
    step = 1e-7
    inside = bowl.profile(bowl.lip_start - step)
    outside = bowl.profile(bowl.lip_start + step)
    # Compared as one-sided limits rather than as raw values: two samples a
    # step apart on a *smooth* function differ by slope times the step, and
    # asserting they are equal would only pass for a flat join.
    assert inside[0] + step * inside[1] == pytest.approx(
        outside[0] - step * outside[1], abs=1e-12
    )
    assert inside[1] == pytest.approx(outside[1], abs=1e-4)


def test_the_dish_rises_from_the_drain_to_the_rim():
    bowl = make_bowl()
    heights = [bowl.height(bowl.lip_start + 0.01 * index) for index in range(50)]
    assert all(later > earlier for earlier, later in zip(heights, heights[1:]))
    assert bowl.height(bowl.rim_radius) == pytest.approx(bowl.rim_depth)


def test_the_lip_is_convex_and_the_dish_is_not():
    """The sign of the curvature is what makes the drain a physical event.

    A concave dish holds a marble down; a convex lip lets go of it. If the lip
    ever came out concave the marble would be flung out of the drain rather
    than dropped into it.
    """
    bowl = make_bowl()
    assert bowl.profile(0.30)[2] > 0.0
    assert bowl.profile(bowl.lip_start - 0.004)[2] < 0.0


def test_the_slope_at_the_rim_is_a_wall_not_a_ramp():
    bowl = make_bowl()
    degrees = math.degrees(math.atan(bowl.profile(bowl.rim_radius)[1]))
    assert 30.0 < degrees < 45.0


# --- the chart --------------------------------------------------------------


def test_the_normal_is_a_unit_vector_everywhere():
    bowl = make_bowl()
    for radius in (0.05, 0.12, 0.3, 0.47, 0.5, 0.59):
        for angle in (0.0, 0.7, 2.4, 4.9):
            x, z = radius * math.cos(angle), radius * math.sin(angle)
            normal = bowl.normal(x, z)
            assert math.sqrt(sum(value * value for value in normal)) == pytest.approx(1.0)
            assert normal[1] > 0.0


def test_the_gradient_matches_a_numerical_derivative():
    bowl = make_bowl()
    step = 1e-6
    for x, z in ((0.2, 0.1), (-0.35, 0.15), (0.07, -0.02), (0.0, 0.42)):
        state = bowl.state(x, z)
        numeric_x = (bowl.height(math.hypot(x + step, z)) - bowl.height(math.hypot(x - step, z))) / (2 * step)
        numeric_z = (bowl.height(math.hypot(x, z + step)) - bowl.height(math.hypot(x, z - step))) / (2 * step)
        assert state.grad_x == pytest.approx(numeric_x, abs=1e-6)
        assert state.grad_z == pytest.approx(numeric_z, abs=1e-6)


def test_the_curvature_term_is_the_second_derivative_of_height_along_a_path():
    """`K` is what the surface forces on the vertical motion, and this checks it.

    A straight-line path in the chart is integrated by hand and the height
    along it differentiated twice numerically. What comes out has to be
    `grad f . u_ddot + K`, and with `u_ddot = 0` on a straight path it is `K`
    alone.
    """
    bowl = make_bowl()
    step = 1e-5
    for x, z, vx, vz in (
        (0.30, 0.10, 0.8, -0.3),
        (-0.20, 0.25, -0.4, 0.9),
        (0.42, 0.00, 0.0, 1.4),
    ):
        heights = [
            bowl.height(math.hypot(x + vx * offset, z + vz * offset))
            for offset in (-step, 0.0, step)
        ]
        numeric = (heights[0] - 2 * heights[1] + heights[2]) / (step * step)
        state = bowl.state(x, z)
        assert bowl.curvature_term(state, x, z, vx, vz) == pytest.approx(numeric, rel=1e-4)


def test_world_position_and_velocity_are_on_the_surface_and_its_tangent_plane():
    bowl = make_bowl()
    for x, z, vx, vz in ((0.3, 0.1, 0.5, -0.2), (-0.15, -0.4, -1.1, 0.3)):
        position = bowl.world_position(x, z)
        assert position[1] == pytest.approx(bowl.height(math.hypot(x, z)))
        velocity = bowl.world_velocity(x, z, vx, vz)
        normal = bowl.normal(x, z)
        assert sum(a * b for a, b in zip(velocity, normal)) == pytest.approx(0.0, abs=1e-12)


# --- the collider a 3D engine is given --------------------------------------


def test_a_sphere_resting_on_the_collider_has_its_centre_on_the_centre_surface():
    """The whole reason the geometry is written centre-first.

    For each sample the contact point is one marble radius from the centre
    point, measured along the surface normal. If that stopped being true the
    Python constraint and the Bullet mesh would be different bowls and every
    comparison in this study would be off by a radius.
    """
    bowl = make_bowl()
    for s in (0.08, 0.15, 0.28, 0.41, 0.5, 0.58):
        contact_s, contact_y = bowl.contact_profile(s)
        centre_y = bowl.height(s)
        distance = math.hypot(contact_s - s, contact_y - centre_y)
        assert distance == pytest.approx(bowl.marble_radius, abs=1e-12)
        assert contact_y < centre_y


def test_the_collider_rings_run_from_the_hole_to_the_edge_without_folding():
    bowl = make_bowl()
    radii = bowl.contact_ring_radii(48)
    assert radii[0] == pytest.approx(bowl.lip_start)
    assert radii[-1] == pytest.approx(bowl.max_radius)
    assert all(later > earlier for earlier, later in zip(radii, radii[1:]))
    contact_radii = [bowl.contact_profile(s)[0] for s in radii]
    assert all(later > earlier for earlier, later in zip(contact_radii, contact_radii[1:]))


def test_the_rings_are_spaced_by_arc_length_not_by_radius():
    """Two rings apart at the flat floor should span more radius than at the wall.

    Uniform radial spacing would put most triangles where the surface is least
    interesting. This is the check that the arc-length spacing is actually
    doing something rather than being an expensive way to write `linspace`.
    """
    bowl = make_bowl()
    radii = bowl.contact_ring_radii(20)
    near_floor = radii[1] - radii[0]
    near_rim = radii[-1] - radii[-2]
    assert near_floor > near_rim * 1.15


def test_rings_needs_at_least_two():
    with pytest.raises(ValueError):
        make_bowl().contact_ring_radii(1)


# --- reference quantities ---------------------------------------------------


def test_the_circular_orbit_speed_is_the_rolling_one_not_the_sliding_one():
    """`v^2 = g s y'(s) / (1 + c)`, and the factor matters.

    A sliding point mass orbits at `sqrt(g s y')`. A rolling sphere carries
    two-fifths more inertia and orbits at `sqrt(5/7)` of that. Getting this
    wrong would set every entry velocity in the benchmark 18% too high.
    """
    bowl = make_bowl()
    sliding = math.sqrt(9.81 * 0.47 * bowl.profile(0.47)[1])
    rolling = bowl.circular_orbit_speed(0.47, 9.81, 0.4)
    assert rolling == pytest.approx(sliding * math.sqrt(5.0 / 7.0))


def test_orbit_speed_grows_with_radius():
    bowl = make_bowl()
    speeds = [bowl.circular_orbit_speed(0.1 * index, 9.81, 0.4) for index in range(1, 6)]
    assert all(later > earlier for earlier, later in zip(speeds, speeds[1:]))

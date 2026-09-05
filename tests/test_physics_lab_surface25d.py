"""The 2.5D prototype: the mathematical invariants it claims to have.

Four of these are worth more than the rest.

`test_a_marble_launched_at_orbit_speed_holds_its_circle` checks the equations
of motion against an independent analytic result. The circular-orbit speed is
derived from the constrained Lagrangian in `BowlSurface`; the integrator is
written separately and does not consult it. If either is wrong they disagree,
and no amount of the trajectory looking plausible would have caught it.

`test_a_marble_on_a_slope_rolls_at_five_sevenths_of_gravity` is the same idea
against the most familiar result in the subject. A solid sphere rolling on an
incline accelerates at `(5/7) g sin(theta)`, and that number falls out of the
tangential projection plus the rolling inertia factor without either being
written down anywhere in the integrator.

`test_the_surface_constraint_is_exact` is the property the whole approach is
chosen for, and the point is that the tolerance is *zero*, not small.

`test_two_runs_of_one_spec_are_byte_identical` is the determinism claim, made
on the raw-float digest rather than on the rounded file.
"""

from __future__ import annotations

import math

import pytest

from physics_lab.common.benchmark import load_benchmark, make_run_spec
from physics_lab.common.labreplay import STATE_DRAINED, STATE_FREE, STATE_SURFACE
from physics_lab.surface25d.sim import SurfaceBowlSim, simulate


@pytest.fixture(scope="module")
def benchmark():
    return load_benchmark()


def passive(benchmark, **overrides):
    """The benchmark with every source of dissipation switched off."""
    settings = dict(linear_damping=0.0, rolling_resistance=0.0)
    settings.update(overrides)
    return benchmark.with_overrides(**settings)


# --- the equations of motion ------------------------------------------------


def test_a_marble_launched_at_orbit_speed_holds_its_circle(benchmark):
    """The integrator against the analytic orbit condition, over four turns.

    `circular_orbit_speed` solves `v^2 = g s y'(s) / (1 + c)` from the
    constrained equations. The integrator never reads it. Launch a marble at
    exactly that speed, perfectly tangentially, with no dissipation, and its
    radius has to stay put - which it can only do if the tangential gravity,
    the curvature term and the rolling factor are all right at once.

    Measured at two rates rather than once against a fixed tolerance. What is
    left over at any finite step is discretisation, not a wrong orbit
    condition, and the way to say so in a test is to show it shrinking with
    the step: a genuinely mismatched speed would wander by the same amount
    however finely the step was cut.
    """
    radius = 0.42
    excursions = []
    for rate in (240, 480):
        settings = passive(benchmark, marble_count=1, physics_hz=rate)
        surface = settings.surface()
        speed = surface.circular_orbit_speed(
            radius, settings.gravity, settings.rolling_inertia_factor
        )
        sim = SurfaceBowlSim(make_run_spec(settings, 7))
        marble = sim.marbles[0]
        marble.x, marble.z = radius, 0.0
        marble.vx, marble.vz = 0.0, speed
        sim._sync_world(marble)

        period = 2.0 * math.pi * radius / speed
        worst = 0.0
        for _ in range(int(round(4.0 * period * rate))):
            sim.step()
            worst = max(worst, abs(math.hypot(marble.px, marble.pz) - radius))
        excursions.append(worst)

    assert excursions[0] < 1e-4 * radius, f"orbit wandered by {excursions[0]:.3e} m"
    assert excursions[1] * 3.0 < excursions[0], (
        f"wander did not shrink with the step ({excursions[0]:.3e} -> {excursions[1]:.3e}),"
        " so it is not discretisation"
    )


def test_a_marble_on_a_slope_rolls_at_five_sevenths_of_gravity(benchmark):
    """The classic result, recovered from the tangential projection.

    Nothing in `acceleration` contains `5/7` or `sin`. What it contains is the
    gradient of the surface, the rolling inertia factor and the constraint
    algebra, and this is the check that those three compose into the answer
    every textbook gives for a sphere on an incline.
    """
    settings = passive(benchmark, marble_count=1)
    surface = settings.surface()
    sim = SurfaceBowlSim(make_run_spec(settings, 7))
    marble = sim.marbles[0]

    for radius in (0.20, 0.35, 0.47):
        marble.x, marble.z = radius, 0.0
        marble.vx = marble.vz = 0.0
        sim._sync_world(marble)
        ax, az, _ = sim.acceleration(marble)

        slope = surface.profile(radius)[1]
        angle = math.atan(slope)
        # The horizontal acceleration is the along-slope one projected flat.
        expected = (
            settings.gravity / (1.0 + settings.rolling_inertia_factor)
            * math.sin(angle)
            * math.cos(angle)
        )
        assert ax == pytest.approx(-expected, rel=1e-12)
        assert az == pytest.approx(0.0, abs=1e-15)


def test_gravity_pulls_toward_the_centre_from_every_direction(benchmark):
    """The specific thing the production 2D bowl cannot do.

    In the simulation plane of the neon course, gravity is a constant vector,
    so it accelerates a racer toward the drain on one side of the disc and away
    from it on the other. Here the in-surface force is the projection of
    gravity onto the tangent plane and it is inward everywhere, with the same
    magnitude at the same radius whatever the bearing.
    """
    settings = passive(benchmark, marble_count=1)
    sim = SurfaceBowlSim(make_run_spec(settings, 7))
    marble = sim.marbles[0]

    magnitudes = []
    for bearing in (0.0, 0.9, 1.9, 3.1, 4.4, 5.7):
        marble.x = 0.4 * math.cos(bearing)
        marble.z = 0.4 * math.sin(bearing)
        marble.vx = marble.vz = 0.0
        sim._sync_world(marble)
        ax, az, _ = sim.acceleration(marble)
        # Inward: the acceleration points back along the position vector.
        assert ax * marble.x + az * marble.z < 0.0
        magnitudes.append(math.hypot(ax, az))
    assert max(magnitudes) - min(magnitudes) < 1e-12


def test_the_normal_force_is_positive_on_the_dish_and_falls_on_the_lip(benchmark):
    """Which is what makes the drain a physical event rather than a radius test.

    The lip does not let go of a stationary marble, and should not: a marble
    resting on a convex surface is still held by it. What the lip does is stop
    being able to supply the centripetal force a *moving* marble needs, and
    the faster the marble the further out that happens. So the measurement is
    the normal force at a fixed speed, on the dish and then on the lip.
    """
    settings = passive(benchmark, marble_count=1)
    surface = settings.surface()
    sim = SurfaceBowlSim(make_run_spec(settings, 7))
    marble = sim.marbles[0]

    def normal_at(radius: float, inward: float) -> float:
        marble.x, marble.z = radius, 0.0
        marble.vx, marble.vz = -inward, 0.0
        sim._sync_world(marble)
        return sim.acceleration(marble)[2]

    assert normal_at(0.45, 0.0) > 0.0
    assert normal_at(0.45, 0.6) > 0.0, "the dish is concave; speed presses a marble in"
    assert normal_at(0.10, 0.6) > 0.0
    assert normal_at(surface.lip_start - 0.6 * settings.marble_radius, 0.0) > 0.0
    on_the_lip = normal_at(surface.lip_start - 0.6 * settings.marble_radius, 0.6)
    assert on_the_lip < 0.0, "a convex lip cannot hold a moving marble down"


# --- the constraint ---------------------------------------------------------


def test_the_surface_constraint_is_exact(benchmark):
    """Zero tolerance, not a small one.

    Height is evaluated from the chart rather than integrated, so a marble in
    contact is on the surface to the last bit of the float. This is the
    property the whole approach is chosen for and it is why sinking, hovering,
    drift and tunnelling are not failure modes this prototype can have.
    """
    sim = SurfaceBowlSim(make_run_spec(benchmark, 19))
    surface = sim.surface
    for _ in range(2400):
        sim.step()
        for marble in sim.marbles:
            if marble.state != STATE_SURFACE:
                continue
            assert marble.py == surface.height(math.hypot(marble.px, marble.pz))


def test_velocity_stays_in_the_tangent_plane(benchmark):
    sim = SurfaceBowlSim(make_run_spec(benchmark, 23))
    for _ in range(1200):
        sim.step()
        for marble in sim.marbles:
            if marble.state != STATE_SURFACE:
                continue
            normal = sim.surface.normal(marble.x, marble.z)
            into = sum(a * b for a, b in zip(marble.velocity, normal))
            assert into == pytest.approx(0.0, abs=1e-12)


def test_a_marble_in_contact_is_rolling(benchmark):
    """`|omega| r == |v|`, which is what "not a hockey puck" means numerically."""
    sim = SurfaceBowlSim(make_run_spec(benchmark, 31))
    radius = benchmark.marble_radius
    for _ in range(1200):
        sim.step()
        for marble in sim.marbles:
            if marble.state != STATE_SURFACE:
                continue
            speed = math.sqrt(sum(value**2 for value in marble.velocity))
            spin = math.sqrt(marble.ox**2 + marble.oy**2 + marble.oz**2)
            if speed > 1e-6:
                assert spin * radius == pytest.approx(speed, rel=1e-9)


# --- energy -----------------------------------------------------------------


def test_passive_motion_does_not_create_energy(benchmark):
    """No dissipation, no collisions, ten seconds: drift under one part in 10^5.

    Section 10 of the plan allows 1%. Velocity Verlet with a velocity
    predictor delivers about a thousand times better than that at the
    benchmark rate, and the tolerance here is set where the measurement
    actually lands rather than where the criterion is, so that a regression
    into first-order behaviour fails this test instead of passing it.
    """
    settings = passive(benchmark, marble_count=1)
    sim = SurfaceBowlSim(make_run_spec(settings, 7))
    start = sim.mechanical_energy()
    worst = 0.0
    for _ in range(10 * settings.physics_hz):
        sim.step()
        worst = max(worst, abs(sim.mechanical_energy() - start) / abs(start))
    assert worst < 1e-5


def test_energy_drift_is_second_order_in_the_step(benchmark):
    """Halving the step has to quarter the drift, or the integrator regressed."""
    drifts = []
    for rate in (120, 240):
        settings = passive(benchmark, marble_count=1, physics_hz=rate)
        sim = SurfaceBowlSim(make_run_spec(settings, 7))
        start = sim.mechanical_energy()
        for _ in range(5 * rate):
            sim.step()
        drifts.append(abs(sim.mechanical_energy() - start) / abs(start))
    assert drifts[0] > 3.0 * drifts[1]


def test_a_collision_never_adds_kinetic_energy(benchmark):
    """Restitution below one, so a contact can only take energy out."""
    settings = passive(benchmark, marble_count=2)
    sim = SurfaceBowlSim(make_run_spec(settings, 7))
    first, second = sim.marbles
    # Head-on, on the flat part of the dish, well clear of the lip.
    first.x, first.z, first.vx, first.vz = -0.16, 0.0, 0.9, 0.0
    second.x, second.z, second.vx, second.vz = 0.16, 0.0, -0.9, 0.0
    sim._sync_world(first)
    sim._sync_world(second)

    before = sim.mechanical_energy()
    peak = before
    for _ in range(settings.physics_hz):
        sim.step()
        peak = max(peak, sim.mechanical_energy())
    assert peak <= before + 1e-6
    assert sim.mechanical_energy() < before


# --- collisions -------------------------------------------------------------


def test_overlapping_marbles_are_pushed_apart(benchmark):
    settings = benchmark.with_overrides(marble_count=2)
    sim = SurfaceBowlSim(make_run_spec(settings, 7))
    first, second = sim.marbles
    diameter = 2.0 * settings.marble_radius
    first.x, first.z, first.vx, first.vz = 0.30, 0.0, 0.0, 0.0
    second.x, second.z, second.vx, second.vz = 0.30 + 0.4 * diameter, 0.0, 0.0, 0.0
    sim._sync_world(first)
    sim._sync_world(second)

    for _ in range(40):
        sim.step()
    assert math.dist(first.position, second.position) >= diameter - 1e-6


def test_a_collision_between_marbles_at_different_heights_moves_both(benchmark):
    """Section 14: the response has to be a 3D impulse, not a flat one.

    Two marbles meeting on differently sloped parts of the wall are struck
    along a normal that has a real vertical component. A model that resolved
    every contact in the horizontal plane would leave the uphill marble's
    height unchanged; here the impulse goes in in 3D and each marble's
    constraint decides what it does with it.
    """
    settings = passive(benchmark, marble_count=2)
    sim = SurfaceBowlSim(make_run_spec(settings, 7))
    first, second = sim.marbles
    gap = 1.9 * settings.marble_radius
    first.x, first.z, first.vx, first.vz = 0.30, 0.0, 1.2, 0.0
    second.x, second.z, second.vx, second.vz = 0.30 + gap, 0.0, 0.0, 0.0
    sim._sync_world(first)
    sim._sync_world(second)
    heights = (first.py, second.py)
    assert heights[0] != heights[1], "the two have to start on different slopes"

    for _ in range(6):
        sim.step()
    assert any(event.kind == "collision" for event in sim.events)
    assert second.wx > 0.0, "the downhill marble was struck and moved"
    assert second.wy != 0.0, "and its height changed, so the impulse was not flat"


# --- the drain --------------------------------------------------------------


def test_the_drain_transition_is_continuous(benchmark):
    """No teleport: position and velocity carry across the release unchanged."""
    sim = SurfaceBowlSim(make_run_spec(benchmark, 7))
    seen: dict[int, tuple] = {}
    released: list[int] = []
    for _ in range(benchmark.physics_hz * 25):
        previous = {
            marble.marble_id: (marble.position, marble.velocity, marble.state)
            for marble in sim.marbles
        }
        sim.step()
        for marble in sim.marbles:
            was = previous[marble.marble_id]
            if was[2] == STATE_SURFACE and marble.state == STATE_FREE:
                released.append(marble.marble_id)
                seen[marble.marble_id] = was
        if released:
            break
    assert released, "no marble reached the drain in twenty-five seconds"
    for marble_id in released:
        marble = sim.marbles[marble_id]
        before_position, before_velocity, _ = seen[marble_id]
        # One tick of free fall separates them, and nothing else may.
        assert math.dist(marble.position, before_position) < 0.02
        drop = benchmark.gravity * benchmark.dt
        assert abs(marble.velocity[1] - before_velocity[1]) <= drop * 1.5


def test_every_marble_leaves_and_none_escapes(benchmark):
    for seed in (7, 89, 163):
        run = simulate(make_run_spec(benchmark, seed))
        assert run.stats["failure"] is None
        assert run.stats["drained"] == benchmark.marble_count
        assert run.stats["escaped"] == 0


def test_a_drained_marble_stays_drained(benchmark):
    run = simulate(make_run_spec(benchmark, 7))
    finished: set[int] = set()
    for frame in run.frames:
        for marble in frame.marbles:
            if marble.marble_id in finished:
                assert marble.state == STATE_DRAINED
            elif marble.state == STATE_DRAINED:
                finished.add(marble.marble_id)
    assert len(finished) == benchmark.marble_count


# --- determinism ------------------------------------------------------------


def test_two_runs_of_one_spec_are_byte_identical(benchmark):
    """On the raw float bytes, not on the rounded file."""
    spec = make_run_spec(benchmark, 42)
    assert simulate(spec).digest() == simulate(spec).digest()


def test_different_seeds_are_different_runs(benchmark):
    first = simulate(make_run_spec(benchmark, 42))
    second = simulate(make_run_spec(benchmark, 57))
    assert first.digest() != second.digest()


def test_the_physics_rate_does_not_change_the_race(benchmark):
    """Not identical - it cannot be - but the same run to within a few percent.

    A model whose outcome depended on the tick rate would be reporting the
    integrator rather than the bowl, and would make the performance comparison
    meaningless because each engine could buy speed by getting a different
    answer.
    """
    slow = simulate(make_run_spec(benchmark.with_overrides(physics_hz=120), 7))
    fast = simulate(make_run_spec(benchmark.with_overrides(physics_hz=480), 7))
    assert slow.stats["drained"] == fast.stats["drained"] == benchmark.marble_count
    assert abs(slow.stats["sim_seconds"] - fast.stats["sim_seconds"]) < 1.0

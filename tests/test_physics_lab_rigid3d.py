"""The rigid-body prototype: the collider, and what the engine does with it.

The mesh tests are the important ones and one of them is a regression test for
a bug that produced a *plausible physics result*. The first version of the
builder appended the drain shaft after the dish instead of before it, so the
triangle strip joined the outermost dish ring to the top of the shaft and the
collider contained a phantom cone running from the rim straight down to the
drain. Marbles wedged between the real dish and the phantom one and stopped
dead on the wall - which reads, in a summary table, exactly like "this engine
has too much friction". Nothing short of looking at the contact normals found
it. `test_no_triangle_spans_the_bowl` is what would have found it in a second.

The engine tests are marked `skipif` rather than assumed, because PyBullet is
deliberately not a production dependency: it has no wheel on this platform and
had to be compiled. The rest of the lab has to keep working without it.
"""

from __future__ import annotations

import math

import pytest

from physics_lab.common.benchmark import load_benchmark, make_run_spec
from physics_lab.common.labreplay import STATE_DRAINED
from physics_lab.rigid3d.mesh import build_bowl_mesh, worst_sagitta

pybullet = pytest.importorskip("pybullet", reason="the rigid-body prototype is optional")

from physics_lab.rigid3d.bullet import (  # noqa: E402
    WORLD_SCALE,
    BulletBowlSim,
    damping_coefficient,
    simulate,
)


@pytest.fixture(scope="module")
def benchmark():
    return load_benchmark()


@pytest.fixture(scope="module")
def mesh(benchmark):
    return build_bowl_mesh(benchmark.surface(), benchmark.drain_exit_y, rings=48, segments=64)


# --- the collider -----------------------------------------------------------


def test_the_mesh_runs_from_the_shaft_bottom_up_to_the_rim(benchmark, mesh):
    """Ring order, which is the thing the strip builder depends on."""
    segments = 64
    heights = [mesh.vertices[ring * segments][1] for ring in range(len(mesh.vertices) // segments)]
    assert all(later >= earlier for earlier, later in zip(heights, heights[1:]))
    assert heights[0] < benchmark.drain_exit_y
    assert heights[-1] == pytest.approx(
        benchmark.surface().contact_profile(benchmark.surface_max_radius)[1]
    )


def test_no_triangle_spans_the_bowl(benchmark, mesh):
    """The regression test for the phantom cone.

    Every triangle in a surface of revolution joins neighbouring rings and
    neighbouring segments, so no edge can be longer than a couple of ring
    spacings plus a chord. A triangle whose vertices are half a bowl apart is
    a triangle joining two rings that are not neighbours - which is exactly
    what the shaft-appended-after-the-dish bug produced, and it made marbles
    stop dead on the wall for reasons that looked like physics.
    """
    span = benchmark.surface_max_radius - benchmark.drain_radius
    longest = 0.0
    for base in range(0, len(mesh.indices), 3):
        corners = [mesh.vertices[mesh.indices[base + offset]] for offset in range(3)]
        for first in range(3):
            for second in range(first + 1, 3):
                longest = max(longest, math.dist(corners[first], corners[second]))
    assert longest < 0.25 * span, f"longest triangle edge {longest:.4f} m spans the bowl"


def test_every_triangle_has_area(mesh):
    degenerate = 0
    for base in range(0, len(mesh.indices), 3):
        a, b, c = (mesh.vertices[mesh.indices[base + offset]] for offset in range(3))
        u = tuple(b[i] - a[i] for i in range(3))
        v = tuple(c[i] - a[i] for i in range(3))
        cross = (
            u[1] * v[2] - u[2] * v[1],
            u[2] * v[0] - u[0] * v[2],
            u[0] * v[1] - u[1] * v[0],
        )
        if math.sqrt(sum(value * value for value in cross)) < 1e-12:
            degenerate += 1
    assert degenerate == 0


def test_the_collider_is_the_centre_surface_offset_by_one_radius(benchmark, mesh):
    """Checked through the engine, by raycast, not by re-reading the builder.

    This is the assertion that a sphere at rest in Bullet has its centre where
    the Python constraint would put it - the single thing that makes the two
    experiments comparable rather than merely similar.
    """
    surface = benchmark.surface()
    sim = BulletBowlSim(make_run_spec(benchmark, 7), rings=48, segments=64)
    try:
        for radius in (0.12, 0.25, 0.40, 0.55):
            scale = sim.scale
            hit = sim.pybullet.rayTest(
                [radius * scale, 1.0 * scale, 0.0],
                [radius * scale, -0.5 * scale, 0.0],
                physicsClientId=sim.client,
            )[0]
            assert hit[0] >= 0, f"the ray missed the bowl at radius {radius}"
            height = hit[3][1] / scale
            # Find the centre-surface radius whose contact point is here.
            low, high = surface.lip_start, surface.max_radius
            for _ in range(60):
                middle = 0.5 * (low + high)
                if surface.contact_profile(middle)[0] < radius:
                    low = middle
                else:
                    high = middle
            expected = surface.contact_profile(0.5 * (low + high))[1]
            assert height == pytest.approx(expected, abs=1e-4)
    finally:
        sim.close()


def test_a_finer_mesh_is_a_smoother_one(benchmark):
    surface = benchmark.surface()
    sagittas = [worst_sagitta(surface, segments) for segments in (32, 64, 128, 256)]
    assert all(later < earlier for earlier, later in zip(sagittas, sagittas[1:]))


# --- the engine setup -------------------------------------------------------


def test_the_damping_coefficient_inverts_bullets_own_formula():
    """Bullet decays by `(1 - d)^dt`; the benchmark asks for `exp(-k t)`."""
    for rate in (0.1, 0.25, 0.5, 1.0):
        coefficient = damping_coefficient(rate)
        after_a_second = (1.0 - coefficient) ** 1.0
        assert after_a_second == pytest.approx(math.exp(-rate))


def test_the_friction_pair_produces_the_benchmarks_two_coefficients(benchmark):
    """Bullet multiplies the two bodies' friction, so neither value is the answer."""
    sim = BulletBowlSim(make_run_spec(benchmark, 7), rings=32, segments=32)
    try:
        assert sim.marble_friction * sim.marble_friction == pytest.approx(benchmark.friction)
        assert sim.marble_friction * sim.bowl_friction == pytest.approx(
            benchmark.surface_friction
        )
    finally:
        sim.close()


def test_the_surface_friction_can_actually_sustain_rolling(benchmark):
    """`mu > (2/7) tan(theta)` at the steepest wall, or marbles skid.

    Not a property of the code - a property of the *configuration*, and the
    reason it is a test is that getting it wrong does not look like an error.
    It looks like a rigid-body engine that dissipates more than a 2.5D model,
    which is a conclusion this study could have drawn and published.
    """
    slope = benchmark.surface().profile(benchmark.surface_max_radius)[1]
    assert benchmark.surface_friction > (2.0 / 7.0) * slope


def test_state_comes_back_in_benchmark_units_not_engine_units(benchmark):
    """The world is simulated at 25x; nothing outside `_pose` may see that."""
    assert WORLD_SCALE > 1.0
    spec = make_run_spec(benchmark, 7)
    sim = BulletBowlSim(spec, rings=32, segments=32)
    try:
        sim.prime()
        position, _, velocity, spin = sim._pose(0)
        start = spec.starts[0]
        assert position == pytest.approx(start.position, abs=1e-9)
        assert velocity == pytest.approx(start.velocity, abs=1e-9)
        assert spin == pytest.approx(start.spin, abs=1e-9)
    finally:
        sim.close()


# --- what the engine does ---------------------------------------------------


@pytest.fixture(scope="module")
def run(benchmark):
    return simulate(make_run_spec(benchmark.with_overrides(linear_damping=0.0), 7))


def test_every_marble_reaches_the_drain(benchmark, run):
    assert run.stats["failure"] is None
    assert run.stats["drained"] == benchmark.marble_count
    assert run.stats["escaped"] == 0


def test_marbles_roll_rather_than_skid(benchmark, run):
    """`|omega| r / |v|` near one, averaged over the run while in contact.

    The number this test is really guarding is `surface_friction`. With the
    marble-on-marble figure used for the wall as well, Bullet's multiplying
    combine gives 0.0225 against a wall needing 0.230, and this comes out at
    1.58 - a marble spinning far faster than it travels, which is a marble
    skidding down a slope.
    """
    radius = benchmark.marble_radius
    ratios = []
    for frame in run.frames:
        for marble in frame.marbles:
            if marble.state != "surface":
                continue
            speed = math.sqrt(sum(value * value for value in marble.velocity))
            spin = math.sqrt(sum(value * value for value in marble.spin))
            if speed > 0.05:
                ratios.append(spin * radius / speed)
    assert ratios
    assert 0.9 < sum(ratios) / len(ratios) < 1.1


def test_marbles_stay_on_the_bowl(benchmark, run):
    """Penetration and hover, which the 2.5D model has exactly none of.

    Bullet has both, and the bound here is where they were measured rather
    than where they would be comfortable: a tenth of a marble radius of hover
    and a fortieth of one of penetration.
    """
    surface = benchmark.surface()
    worst_below = 0.0
    worst_above = 0.0
    for frame in run.frames:
        for marble in frame.marbles:
            if marble.state != "surface":
                continue
            radius = math.hypot(marble.position[0], marble.position[2])
            if radius < surface.lip_start:
                continue
            offset = marble.position[1] - surface.height(radius)
            worst_below = min(worst_below, offset)
            worst_above = max(worst_above, offset)
    assert -worst_below < 0.025 * benchmark.marble_radius
    assert worst_above < 0.5 * benchmark.marble_radius


def test_marbles_orbit_rather_than_heading_for_the_drain(benchmark, run):
    """The point of the whole exercise, asserted at the low end.

    The production 2D bowl measures 0.46 revolutions on this metric. Anything
    that cannot clear a full turn is a funnel.
    """
    from physics_lab.analysis.metrics import measure

    metrics = measure(run, surface_height=benchmark.surface().height)
    assert metrics.median_revolutions > 1.5
    assert metrics.fraction_over_one_revolution == 1.0


def test_two_runs_of_one_spec_are_byte_identical(benchmark):
    spec = make_run_spec(benchmark.with_overrides(linear_damping=0.0), 11)
    assert simulate(spec).digest() == simulate(spec).digest()


def test_a_drained_marble_leaves_and_stays_gone(benchmark, run):
    finished: set[int] = set()
    for frame in run.frames:
        for marble in frame.marbles:
            if marble.marble_id in finished:
                assert marble.state == STATE_DRAINED
            elif marble.state == STATE_DRAINED:
                finished.add(marble.marble_id)
    assert len(finished) == benchmark.marble_count

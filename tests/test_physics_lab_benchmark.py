"""The benchmark configuration and the initial conditions it resolves to.

The property under test throughout is comparability. A benchmark that both
prototypes read but that quietly means something different in each, or a run
spec that is not reproducible, would make every later measurement worthless
without making any of them look wrong.
"""

from __future__ import annotations

import json
import math

import pytest

from physics_lab.common.benchmark import (
    CONFIG_PATH,
    Benchmark,
    load_benchmark,
    make_run_spec,
)


@pytest.fixture(scope="module")
def benchmark() -> Benchmark:
    return load_benchmark()


# --- the configuration ------------------------------------------------------


def test_the_committed_configuration_loads(benchmark):
    assert benchmark.marble_count == 8
    assert benchmark.gravity > 0.0
    assert len(benchmark.seeds) == 20
    assert len(set(benchmark.seeds)) == 20


def test_the_sample_rate_divides_the_physics_rate(benchmark):
    """Otherwise the two prototypes would sample different instants.

    The frames are compared frame for frame, so a sample rate that does not
    divide the physics rate would leave one engine reporting the state at
    1/60 s and the other at the nearest tick to it.
    """
    assert benchmark.physics_hz % benchmark.sample_hz == 0
    assert benchmark.ticks_per_sample == benchmark.physics_hz // benchmark.sample_hz


def test_a_sample_rate_that_does_not_divide_is_refused(benchmark):
    with pytest.raises(ValueError):
        benchmark.with_overrides(physics_hz=250, sample_hz=60).ticks_per_sample


def test_the_drain_is_quoted_in_marble_diameters(benchmark):
    assert benchmark.drain_diameter_ratio == pytest.approx(
        benchmark.drain_radius / benchmark.marble_radius
    )
    assert benchmark.drain_diameter_ratio >= 2.0


def test_overrides_are_checked_against_the_real_field_names(benchmark):
    assert benchmark.with_overrides(linear_damping=0.4).linear_damping == 0.4
    with pytest.raises(ValueError):
        benchmark.with_overrides(linaer_damping=0.4)


def test_a_configuration_of_the_wrong_version_is_refused(tmp_path):
    with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
        raw = json.load(handle)
    raw["version"] = 99
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="version"):
        load_benchmark(str(path))


# --- the run spec -----------------------------------------------------------


def test_every_marble_starts_exactly_on_the_surface(benchmark):
    surface = benchmark.surface()
    for seed in benchmark.seeds:
        for start in make_run_spec(benchmark, seed).starts:
            x, _, z = start.position
            assert start.position[1] == pytest.approx(surface.height(math.hypot(x, z)))


def test_every_marble_starts_moving_along_the_surface(benchmark):
    """The entry velocity has to be tangent, or the first tick is a bounce."""
    surface = benchmark.surface()
    spec = make_run_spec(benchmark, benchmark.seeds[0])
    for start in spec.starts:
        x, _, z = start.position
        normal = surface.normal(x, z)
        into_surface = sum(a * b for a, b in zip(start.velocity, normal))
        assert into_surface == pytest.approx(0.0, abs=1e-12)


def test_every_marble_starts_already_rolling(benchmark):
    """Contact-point velocity zero, so a 3D engine does not begin by skidding.

    Without this the rigid-body prototypes spend their first tenth of a second
    converting slip into spin while the 2.5D model, which assumes rolling from
    tick zero, does not - and the two would be answering different questions
    from the first frame.
    """
    surface = benchmark.surface()
    radius = benchmark.marble_radius
    for start in make_run_spec(benchmark, 42).starts:
        x, _, z = start.position
        normal = surface.normal(x, z)
        spin, velocity = start.spin, start.velocity
        # v_contact = v + omega x (-r n)
        arm = tuple(-radius * value for value in normal)
        cross = (
            spin[1] * arm[2] - spin[2] * arm[1],
            spin[2] * arm[0] - spin[0] * arm[2],
            spin[0] * arm[1] - spin[1] * arm[0],
        )
        contact = [v + c for v, c in zip(velocity, cross)]
        assert math.sqrt(sum(value * value for value in contact)) == pytest.approx(0.0, abs=1e-9)


def test_entry_is_prograde_and_mostly_tangential(benchmark):
    """Section 11 of the brief: real bowl motion, not eight drops on the drain."""
    for seed in benchmark.seeds:
        for start in make_run_spec(benchmark, seed).starts:
            x, _, z = start.position
            radius = math.hypot(x, z)
            vx, _, vz = start.velocity
            radial = (x * vx + z * vz) / radius
            tangential = (x * vz - z * vx) / radius
            speed = math.hypot(vx, vz)
            assert tangential > 0.0, "every marble is prograde"
            assert radial < 0.0, "every marble has an inward component"
            assert abs(radial) < 0.5 * speed, "and it is modest"


def test_entry_radii_and_speeds_stay_inside_the_configured_band(benchmark):
    surface = benchmark.surface()
    for seed in benchmark.seeds:
        for start in make_run_spec(benchmark, seed).starts:
            x, _, z = start.position
            radius = math.hypot(x, z)
            assert benchmark.entry_radius_min - 1e-12 <= radius <= benchmark.entry_radius_max + 1e-12
            orbit = surface.circular_orbit_speed(
                radius, benchmark.gravity, benchmark.rolling_inertia_factor
            )
            factor = math.hypot(start.velocity[0], start.velocity[2]) / orbit
            assert benchmark.entry_speed_factor_min - 1e-9 <= factor <= benchmark.entry_speed_factor_max + 1e-9


def test_marbles_do_not_start_touching_each_other(benchmark):
    """A benchmark that begins in an overlap is measuring the solver, not the bowl."""
    diameter = 2.0 * benchmark.marble_radius
    for seed in benchmark.seeds:
        starts = make_run_spec(benchmark, seed).starts
        for index, first in enumerate(starts):
            for second in starts[index + 1:]:
                gap = math.dist(first.position, second.position)
                assert gap > diameter, f"seed {seed}: {first.marble_id} and {second.marble_id}"


def test_the_same_seed_gives_the_same_spec_and_a_different_seed_does_not(benchmark):
    first = make_run_spec(benchmark, 7).to_json()
    assert first == make_run_spec(benchmark, 7).to_json()
    assert first != make_run_spec(benchmark, 8).to_json()


def test_the_spec_carries_the_whole_benchmark_with_it(benchmark):
    """So a stored run can be re-read without the configuration file."""
    payload = make_run_spec(benchmark, 7).to_json()
    assert payload["benchmark"]["rim_radius"] == benchmark.rim_radius
    assert payload["benchmark"]["linear_damping"] == benchmark.linear_damping
    assert len(payload["starts"]) == benchmark.marble_count


def test_sweeping_a_parameter_does_not_move_the_entry_conditions(benchmark):
    """Section 8: a sweep has to change one thing.

    The entry stream is derived from the seed alone, so changing the damping
    or the restitution leaves every marble starting in exactly the same place
    at exactly the same speed. Without this a sweep would be measuring the
    parameter and a reshuffled field at the same time.
    """
    base = make_run_spec(benchmark, 19)
    swept = make_run_spec(benchmark.with_overrides(linear_damping=0.9, restitution=0.2), 19)
    assert [start.position for start in base.starts] == [start.position for start in swept.starts]
    assert [start.velocity for start in base.starts] == [start.velocity for start in swept.starts]

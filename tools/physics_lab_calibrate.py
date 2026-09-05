"""Match the two engines on what they *do*, not on what they are told.

Section 5.3 of the experiment plan. The two architectures do not expose the
same dissipation model, and setting "the same number" in both would compare
two different physical models and call the difference a result.

So the observable is matched instead. A single marble is launched into the
bowl with no other marbles and no collisions, and the time for its mechanical
energy above the drain lip to halve is measured. The 2.5D damping is then
bisected until its half-life agrees with the rigid-body engine's.

The rigid-body engine is the one that sets the target rather than the other
way round, and that is itself the finding: **it has a dissipation floor it
cannot go below.** A sphere rolling on a triangle mesh loses energy at every
edge it crosses, so even with `linearDamping` and `angularDamping` at exactly
zero, and rolling and spinning friction off, a Bullet marble in this bowl
still winds down. The benchmark's own figure - a 0.25/s exponential, chosen by
sweep because it gives eight revolutions and a seventeen second bowl - is
simply not reachable there. What is reachable is the floor, so the floor is
what both engines are calibrated to.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from physics_lab.common.benchmark import Benchmark, load_benchmark, make_run_spec  # noqa: E402

CALIBRATION_SEED = 7
CALIBRATION_SECONDS = 20.0


def half_life(approach: str, benchmark: Benchmark, seed: int = CALIBRATION_SEED) -> float:
    """Seconds for one passive marble's energy above the lip to halve.

    Energy is measured against the height of the drain lip rather than against
    zero, so "half the energy" means half of what the marble has left to spend
    getting to the drain, not half of an offset that never goes away.
    """
    settings = benchmark.with_overrides(marble_count=1)
    surface = settings.surface()
    floor = settings.marble_mass * settings.gravity * surface.height(surface.lip_start)
    mass, gravity = settings.marble_mass, settings.gravity
    inertia = settings.rolling_inertia_factor * mass * settings.marble_radius**2

    def energy(sample) -> float:
        speed_squared = sum(value * value for value in sample.velocity)
        spin_squared = sum(value * value for value in sample.spin)
        return (
            mass * gravity * sample.position[1]
            + 0.5 * mass * speed_squared
            + 0.5 * inertia * spin_squared
            - floor
        )

    if approach == "surface25d":
        from physics_lab.surface25d.sim import simulate
    else:
        from physics_lab.rigid3d.bullet import simulate

    run = simulate(make_run_spec(settings, seed), duration=CALIBRATION_SECONDS)
    start = energy(run.frames[0].marbles[0])
    for frame in run.frames:
        sample = frame.marbles[0]
        if sample.state != "surface" and sample.state != "free":
            break
        if energy(sample) < 0.5 * start:
            return frame.time
    return math.inf


def bisect_damping(benchmark: Benchmark, target: float, tolerance: float = 0.02) -> float:
    """The 2.5D damping whose half-life matches `target`, to `tolerance`."""
    low, high = 0.0, 4.0
    best = high
    for _ in range(24):
        middle = 0.5 * (low + high)
        measured = half_life("surface25d", benchmark.with_overrides(linear_damping=middle))
        best = middle
        if not math.isfinite(measured):
            low = middle
            continue
        error = (measured - target) / target
        if abs(error) <= tolerance:
            return middle
        if measured > target:
            low = middle      # decaying too slowly, damp harder
        else:
            high = middle
    return best


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", default=os.path.join("output", "physics_lab", "calibration.json"))
    args = parser.parse_args(argv)

    benchmark = load_benchmark()
    rigid = benchmark.with_overrides(linear_damping=0.0)
    floor = half_life("rigid3d", rigid)
    print(f"rigid3d floor half-life, zero configured damping: {floor:.3f} s")

    intended = half_life("surface25d", benchmark)
    print(f"surface25d at the benchmark's own {benchmark.linear_damping}/s: {intended:.3f} s")

    matched = bisect_damping(benchmark, floor)
    achieved = half_life("surface25d", benchmark.with_overrides(linear_damping=matched))
    print(f"surface25d calibrated to {matched:.4f}/s: {achieved:.3f} s")
    print(f"agreement: {100.0 * abs(achieved - floor) / floor:.2f}%")

    payload = {
        "calibration_seed": CALIBRATION_SEED,
        "rigid3d_linear_damping": 0.0,
        "rigid3d_half_life": floor,
        "benchmark_linear_damping": benchmark.linear_damping,
        "surface25d_half_life_at_benchmark": intended,
        "surface25d_calibrated_linear_damping": matched,
        "surface25d_half_life_calibrated": achieved,
        "agreement_percent": 100.0 * abs(achieved - floor) / floor,
    }
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    print(f"-> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

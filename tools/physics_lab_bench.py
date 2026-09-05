"""Run the bowl benchmark and write lab time series.

The lab's front door. One approach, one or more seeds, optional parameter
overrides, out to a directory of `LabRun` JSON plus a summary of the metrics.

    python tools/physics_lab_bench.py --approach surface25d --all-seeds
    python tools/physics_lab_bench.py --approach rigid3d --seed 7 --marbles 32
    python tools/physics_lab_bench.py --approach surface25d --set linear_damping=0.4

Every approach is driven through the same function, is handed the same
`RunSpec`, and writes the same schema. That is the whole point: the only thing
that differs between two rows of the comparison is the physics.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from physics_lab.analysis.metrics import measure, summarise  # noqa: E402
from physics_lab.common.benchmark import (  # noqa: E402
    Benchmark,
    load_benchmark,
    make_run_spec,
)
from physics_lab.common.labreplay import LabRun, write_run  # noqa: E402

APPROACHES = ("surface25d", "rigid3d", "godot3d")
DEFAULT_ROOT = os.path.join("output", "physics_lab")

# Fields a `--set` may touch. Deliberately a whitelist of the physically
# interpretable ones from section 35 of the brief, so a sweep cannot quietly
# reshape the benchmark - changing the marble count or the seed list through
# this door would produce runs that look comparable and are not.
SWEEPABLE = {
    "gravity",
    "rim_depth",
    "profile_power",
    "drain_radius",
    "restitution",
    "friction",
    "linear_damping",
    "rolling_resistance",
    "surface_restitution",
    "physics_hz",
    "duration_limit",
}


def parse_overrides(assignments: list[str]) -> dict[str, float]:
    overrides: dict[str, float] = {}
    for assignment in assignments:
        if "=" not in assignment:
            raise SystemExit(f"--set wants name=value, got {assignment!r}")
        name, _, value = assignment.partition("=")
        name = name.strip()
        if name not in SWEEPABLE:
            raise SystemExit(
                f"--set {name!r} is not a sweepable parameter; "
                f"choose from {', '.join(sorted(SWEEPABLE))}"
            )
        overrides[name] = int(value) if name == "physics_hz" else float(value)
    return overrides


def widen_entry_for(benchmark: Benchmark, count: int) -> Benchmark:
    """Make room on the entry ring for a field bigger than the benchmark's.

    Only the scaling test in section 29 of the brief needs this. Eight marbles
    fit on one band with twelve degrees of jitter and metres of clearance;
    sixty-four on the same band would start in contact, and a scaling
    measurement that begins with the solver untangling a pile-up is measuring
    the pile-up. So the band is widened inward and the jitter cut in
    proportion, and nothing else about the benchmark moves.
    """
    if count <= benchmark.marble_count:
        return benchmark.with_overrides(marble_count=count)
    crowding = count / benchmark.marble_count
    span = benchmark.entry_radius_max - benchmark.entry_radius_min
    return benchmark.with_overrides(
        marble_count=count,
        entry_radius_min=max(
            4.0 * benchmark.marble_radius,
            benchmark.entry_radius_max - span * crowding,
        ),
        entry_angle_jitter_deg=benchmark.entry_angle_jitter_deg / crowding,
    )


def run_one(approach: str, benchmark: Benchmark, seed: int) -> LabRun:
    """Simulate one seed with one approach, timed.

    The import of a rigid-body backend is deferred to here so that the 2.5D
    experiment, the metrics and the whole test suite keep working on a machine
    where PyBullet was never built - which, given what section 11 of the plan
    says about building it, is a property worth having.
    """
    spec = make_run_spec(benchmark, seed)
    started = time.perf_counter()
    if approach == "surface25d":
        from physics_lab.surface25d.sim import simulate

        run = simulate(spec)
    elif approach == "rigid3d":
        from physics_lab.rigid3d.bullet import simulate

        run = simulate(spec)
    elif approach == "godot3d":
        from physics_lab.rigid3d.godot import simulate

        run = simulate(spec)
    else:  # pragma: no cover - argparse restricts this
        raise SystemExit(f"unknown approach {approach!r}")
    run.stats["wall_clock"] = time.perf_counter() - started
    return run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--approach", choices=APPROACHES, default="surface25d")
    parser.add_argument("--seed", type=int, action="append", default=[])
    parser.add_argument("--all-seeds", action="store_true")
    parser.add_argument("--marbles", type=int, default=0, help="override the field size")
    parser.add_argument("--set", dest="overrides", action="append", default=[])
    parser.add_argument("--output", default="")
    parser.add_argument("--label", default="", help="subdirectory name; defaults to the approach")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    benchmark = load_benchmark()
    overrides = parse_overrides(args.overrides)
    if args.marbles:
        benchmark = widen_entry_for(benchmark, args.marbles)
    if overrides:
        benchmark = benchmark.with_overrides(**overrides)

    seeds = list(benchmark.seeds) if args.all_seeds else args.seed
    if not seeds:
        seeds = [benchmark.seeds[0]]

    root = args.output or os.path.join(DEFAULT_ROOT, args.label or args.approach)
    os.makedirs(root, exist_ok=True)

    metrics = []
    for seed in seeds:
        run = run_one(args.approach, benchmark, seed)
        path = os.path.join(root, f"{args.approach}_seed{seed}.json")
        write_run(run, path)
        scored = measure(run, surface_height=benchmark.surface().height)
        metrics.append(scored)
        if not args.quiet:
            print(
                f"seed {seed:>5}  drained {scored.drained}/{len(scored.marbles)}"
                f"  revs {scored.median_revolutions:5.2f}"
                f"  all-out {scored.all_drained_time if scored.all_drained_time else float('nan'):6.2f}s"
                f"  hits {scored.total_collisions:4d}"
                f"  wall {run.stats['wall_clock']:5.2f}s"
                + (f"  FAILED {scored.failure}" if scored.failure else "")
            )

    summary = summarise(metrics)
    summary_path = os.path.join(root, "summary.json")
    with open(summary_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(
            {
                "approach": args.approach,
                "overrides": overrides,
                "marble_count": benchmark.marble_count,
                "physics_hz": benchmark.physics_hz,
                "seeds": seeds,
                "summary": summary,
            },
            handle,
            indent=2,
        )
        handle.write("\n")
    if not args.quiet:
        print(f"\n{args.approach}: {json.dumps(summary, indent=2)}")
        print(f"-> {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

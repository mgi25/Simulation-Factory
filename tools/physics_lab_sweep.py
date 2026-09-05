"""Sweep one physically interpretable parameter over every benchmark seed.

Section 35 of the brief: do not keep tuning until one hand-picked seed looks
amazing. So every point of every sweep is scored over all twenty seeds and the
chosen value is reported with the measurement that chose it.

    python tools/physics_lab_sweep.py linear_damping 0.08 0.15 0.25 0.4
    python tools/physics_lab_sweep.py profile_power 1.8 2.0 2.4 --approach rigid3d
    python tools/physics_lab_sweep.py drain_radius 0.04 0.05 0.06 0.08

The output is one JSON file per sweep plus a table on stdout. Nothing is
written back into `bowl_benchmark.json`: the committed configuration describes
the benchmark, and a sweep describes itself.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from physics_lab.analysis.metrics import measure, summarise  # noqa: E402
from physics_lab.common.benchmark import load_benchmark  # noqa: E402
from tools.physics_lab_bench import (  # noqa: E402
    DEFAULT_ROOT,
    SWEEPABLE,
    parse_overrides,
    run_one,
)

# What each row of the table shows. Chosen so a reader can see, in one line,
# whether a sweep point is physically believable, whether it finishes, and what
# it costs - which are the three things a parameter has to trade between.
COLUMNS = (
    ("drained", "drained_fraction", "{:6.2f}"),
    ("stuck", "stuck", "{:5.0f}"),
    ("escaped", "escaped", "{:7.0f}"),
    ("med revs", "median_revolutions", "{:8.2f}"),
    ("min revs", "min_revolutions", "{:8.2f}"),
    ("hits/run", "collisions_per_run", "{:8.1f}"),
    ("all out", "mean_all_drained_time", "{:7.2f}"),
    ("mean out", "mean_drain_time", "{:8.2f}"),
    ("stall", "longest_drain_stall", "{:6.2f}"),
    ("overlap", "max_overlap", "{:9.2e}"),
    ("rise", "largest_energy_rise", "{:9.2e}"),
    ("roll", "mean_rolling_ratio", "{:5.3f}"),
    ("wall", "mean_wall_clock", "{:6.2f}"),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("parameter", choices=sorted(SWEEPABLE))
    parser.add_argument("values", nargs="+", type=float)
    parser.add_argument("--approach", default="surface25d")
    parser.add_argument("--seeds", type=int, default=0, help="use only the first N seeds")
    parser.add_argument(
        "--set",
        dest="fixed",
        action="append",
        default=[],
        help="hold another parameter at a value for the whole sweep",
    )
    parser.add_argument("--output", default=os.path.join(DEFAULT_ROOT, "sweeps"))
    args = parser.parse_args(argv)

    base = load_benchmark()
    if args.fixed:
        base = base.with_overrides(**parse_overrides(args.fixed))
    seeds = list(base.seeds)[: args.seeds] if args.seeds else list(base.seeds)
    os.makedirs(args.output, exist_ok=True)

    header = f"{args.parameter:>16}" + "".join(f"{name:>10}" for name, _, _ in COLUMNS)
    print(header)
    print("-" * len(header))

    points = []
    for value in args.values:
        cast = int(value) if args.parameter == "physics_hz" else value
        benchmark = base.with_overrides(**{args.parameter: cast})
        scored = [
            measure(run_one(args.approach, benchmark, seed), benchmark.surface().height)
            for seed in seeds
        ]
        summary = summarise(scored)
        points.append({"value": cast, "summary": summary})
        row = f"{cast:>16}" + "".join(
            fmt.format(summary.get(key, 0.0)).rjust(10) for _, key, fmt in COLUMNS
        )
        print(row)

    path = os.path.join(args.output, f"{args.approach}_{args.parameter}.json")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(
            {"approach": args.approach, "parameter": args.parameter,
             "seeds": seeds, "points": points},
            handle,
            indent=2,
        )
        handle.write("\n")
    print(f"\n-> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

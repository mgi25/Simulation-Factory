"""Is the same run the same run? Twenty times, in one process and in twenty.

Section 32 of the brief: the existing architecture has benefited heavily from
fixed-step reproducibility, and any replacement has to be judged against that.
So this does not ask whether two runs *look* alike. It compares a SHA-256 of
the raw IEEE-754 bytes of every sampled position, velocity, orientation and
spin, taken before anything is rounded for storage.

Two questions, and they are different:

* **In-process.** Twenty runs inside one interpreter. This catches state
  leaking between runs - a cached mesh, an un-reset solver, a random stream
  that was not re-seeded.
* **Cross-process.** Twenty separate interpreter launches. This is the one
  that catches address-dependent iteration order, hash randomisation and
  uninitialised memory, and it is the one that matters for a seed search that
  will eventually run on a farm rather than in a loop.

Where digests differ the report says *when* they first differ and how far
apart the runs are by the end, because "not bit-identical" and "diverges into
a different result" are very different findings and only the second one would
stop a replay pipeline working.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from physics_lab.common.benchmark import load_benchmark, make_run_spec  # noqa: E402
from physics_lab.common.labreplay import STATE_DRAINED, LabRun  # noqa: E402
from tools.physics_lab_bench import run_one  # noqa: E402

DEFAULT_REPEATS = 20


def drain_order(run: LabRun) -> list[int]:
    return [
        int(event.data["id"])
        for event in sorted(run.events, key=lambda event: event.time)
        if event.kind == "drained"
    ]


def divergence(first: LabRun, second: LabRun) -> dict:
    """When two runs part company, and how far apart they end up."""
    first_diff = None
    worst_position = 0.0
    worst_velocity = 0.0
    for frame_a, frame_b in zip(first.frames, second.frames):
        for marble_a, marble_b in zip(frame_a.marbles, frame_b.marbles):
            gap = math.dist(marble_a.position, marble_b.position)
            speed_gap = math.dist(marble_a.velocity, marble_b.velocity)
            if gap > 0.0 and first_diff is None:
                first_diff = frame_a.time
            worst_position = max(worst_position, gap)
            worst_velocity = max(worst_velocity, speed_gap)
    return {
        "first_difference_time": first_diff,
        "max_position_divergence": worst_position,
        "max_velocity_divergence": worst_velocity,
        "same_drain_order": drain_order(first) == drain_order(second),
        "drain_order_a": drain_order(first),
        "drain_order_b": drain_order(second),
    }


def one_digest(approach: str, seed: int, damping: float) -> str:
    benchmark = load_benchmark().with_overrides(linear_damping=damping)
    return run_one(approach, benchmark, seed).digest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--approach", default="surface25d")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    parser.add_argument("--damping", type=float, default=None)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--output", default=os.path.join("output", "physics_lab", "determinism"))
    args = parser.parse_args(argv)

    benchmark = load_benchmark()
    damping = benchmark.linear_damping if args.damping is None else args.damping

    # A child process prints one digest and exits. That is the whole
    # cross-process test: if the digest is a function of the inputs, every
    # child prints the same line.
    if args.child:
        print(one_digest(args.approach, args.seed, damping))
        return 0

    benchmark = benchmark.with_overrides(linear_damping=damping)
    spec = make_run_spec(benchmark, args.seed)

    in_process = []
    runs = []
    for _ in range(args.repeats):
        run = run_one(args.approach, benchmark, args.seed)
        in_process.append(run.digest())
        runs.append(run)

    cross_process = []
    for _ in range(args.repeats):
        result = subprocess.run(
            [
                sys.executable,
                os.path.abspath(__file__),
                "--child",
                "--approach", args.approach,
                "--seed", str(args.seed),
                "--damping", repr(damping),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        cross_process.append(result.stdout.strip().splitlines()[-1])

    report = {
        "approach": args.approach,
        "seed": args.seed,
        "linear_damping": damping,
        "repeats": args.repeats,
        "in_process_unique_digests": len(set(in_process)),
        "cross_process_unique_digests": len(set(cross_process)),
        "in_process_matches_cross_process": set(in_process) == set(cross_process),
        "spec_digest_stable": make_run_spec(benchmark, args.seed).to_json() == spec.to_json(),
        "drain_orders": sorted({tuple(drain_order(run)) for run in runs}),
    }
    report["drain_orders"] = [list(order) for order in report["drain_orders"]]
    report["unique_drain_orders"] = len(report["drain_orders"])
    if len(set(in_process)) > 1:
        first = runs[0]
        other = next(run for run in runs[1:] if run.digest() != first.digest())
        report["divergence"] = divergence(first, other)

    os.makedirs(args.output, exist_ok=True)
    path = os.path.join(args.output, f"{args.approach}_seed{args.seed}.json")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")

    print(json.dumps(report, indent=2))
    print(f"-> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

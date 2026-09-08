"""Run the start lab over many seeds and print the slot table.

    python tools/sloped_start_bench.py --start-kind fan --seeds 300
    python tools/sloped_start_bench.py --start-kind radial --seeds 300 --json out.json

One trial is about a fifth of a full race, so a 300-seed sweep on seven
workers is a couple of minutes rather than half an hour. That is the whole
point of the lab: section 6 of the brief asks for a cheap candidate loop, and
a candidate has to be rejectable in the time it takes to read the table.

## `--start-kind` is required, and that is the point

This tool used to build `SHIPPED_PLAN` with no argument at all, and
`StartPlan.start_kind` used to default to `"basin"` while
`sloped.course.START_KIND` said `"fan"`. So the 300-seed run recorded as V1.4's
"fan" start baseline was the basin's slot profile, and nothing anywhere
compared the name to the geometry. The kind is now named on the command line,
looked up in `sloped.startlab.BENCH_PLANS`, checked against the module the
machine actually instantiated, carried on every `TrialResult`, and printed in
the header and written into the JSON. Four gates, because one silent default
cost a labelled baseline.

`docs/validation/sloped_race_v1/v14/start_baseline_basin.json` is that run,
kept with its correction in its own `label` field rather than deleted - the
mislabelling is the finding.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sloped.startlab import (  # noqa: E402
    BENCH_PLANS,
    LAB_CHECKPOINTS,
    run_trial,
    start_machine,
    summarise,
)


def _one(job):
    # The machine is rebuilt per worker process rather than pickled: a Machine
    # holds meshes and a worker builds it once and reuses it across its chunk.
    # The kind travels with the job, so a worker cannot quietly reuse a machine
    # built for a different topology.
    kind, seed = job
    global _MACHINE
    try:
        machine = _MACHINE
    except NameError:
        _MACHINE = {}
        machine = None
    else:
        machine = _MACHINE.get(kind)
    if machine is None:
        from sloped.startlab import BENCH_PLANS, start_machine

        _MACHINE.clear()
        machine = _MACHINE[kind] = start_machine(plan=BENCH_PLANS[kind])
    return run_trial(seed, machine=machine)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    # No default. A start benchmark whose topology is implicit is what this
    # argument exists to make impossible.
    parser.add_argument(
        "--start-kind",
        required=True,
        choices=list(BENCH_PLANS),
        help="which start topology to measure; there is deliberately no default",
    )
    parser.add_argument("--seeds", type=int, default=200)
    parser.add_argument("--first", type=int, default=0)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--label", default="")
    args = parser.parse_args(argv)

    kind = args.start_kind
    plan = BENCH_PLANS[kind]
    # Built once here as well as in the workers, so a bad kind fails before a
    # pool is spun up and so the plan that goes into the report is the plan the
    # machine agreed to.
    probe = start_machine(plan=plan)
    if probe.start_kind != kind:                     # pragma: no cover - guarded
        raise AssertionError(f"asked for {kind!r}, machine built {probe.start_kind!r}")

    jobs = [(kind, seed) for seed in range(args.first, args.first + args.seeds)]
    started = time.perf_counter()
    if args.workers > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            results = list(pool.map(_one, jobs, chunksize=4))
    else:
        results = [_one(job) for job in jobs]
    wall = time.perf_counter() - started

    report = summarise(results, expect_kind=kind)
    report["wall_seconds"] = round(wall, 2)
    report["label"] = args.label
    report["plan"] = plan.describe()
    report["seeds"] = [args.first, args.first + args.seeds]

    names = [name for name, _ in LAB_CHECKPOINTS]
    print(
        f"{args.label or 'start lab'} [start_kind={report['start_kind']}]: "
        f"{len(results)} trials in {wall:.1f}s"
    )
    print(f"lost {report['lost']} of {report['racers']} ({report['lost_pct']}%)")
    header = "slot | " + " | ".join(f"{n:>8}" for n in names) + " |  exit | coll | wall"
    print(header)
    print("-" * len(header))
    for row in report["slots"]:
        ranks = " | ".join(
            f"{row['mean_rank'][n]:8.3f}" if row["mean_rank"][n] is not None else "       -"
            for n in names
        )
        exit_order = row["mean_exit_order"]
        print(
            f"  {row['slot']}  | {ranks} | "
            f"{exit_order:5.2f} | {row['mean_collisions']:4.1f} | {row['mean_wall_ticks']:5.1f}"
            if exit_order is not None
            else f"  {row['slot']}  | {ranks} |     - |    - |     -"
        )
    print("-" * len(header))
    for name in names:
        block = report["rank_span"][name]
        if block['span'] is None:
            # A start that delivers nothing produces no ranks at all, and a
            # report that crashes on that is a report that cannot describe a
            # total jam - which is exactly the case worth describing.
            print(f"{name:>13}: no ranks - nothing reached this checkpoint")
        else:
            print(
                f"{name:>13}: span {block['span']:.3f} places, "
                f"best slot {block['best_slot']}, worst slot {block['worst_slot']}"
            )
    if report["incomplete"]:
        print(f"incomplete trials: {report['incomplete']}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

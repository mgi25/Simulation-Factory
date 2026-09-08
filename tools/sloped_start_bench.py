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
    BARE_FAN,
    BENCH_PLANS,
    LAB_CHECKPOINTS,
    WIDE_CANDIDATES,
    run_trial,
    start_machine,
    summarise,
)


def _one(job):
    # The machine is rebuilt per worker process rather than pickled: a Machine
    # holds meshes and a worker builds it once and reuses it across its chunk.
    # The kind travels with the job, so a worker cannot quietly reuse a machine
    # built for a different topology.
    kind, candidate, seed = job
    global _MACHINE
    try:
        machine = _MACHINE
    except NameError:
        _MACHINE = {}
        machine = None
    else:
        machine = _MACHINE.get((kind, candidate))
    if machine is None:
        from sloped.startlab import (
            BARE_FAN,
            BENCH_PLANS,
            WIDE_CANDIDATES,
            start_machine,
        )

        _MACHINE.clear()
        table = dict(WIDE_CANDIDATES, **{BARE_FAN.name: BARE_FAN})
        plan = table[candidate] if candidate else BENCH_PLANS[kind]
        machine = _MACHINE[(kind, candidate)] = start_machine(plan=plan)
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
    # Which structural candidate, for the topologies that have more than one.
    # Named rather than numbered, and looked up in one table, for the reason
    # `--start-kind` is required: a recorded run has to say what it measured.
    parser.add_argument(
        "--candidate",
        default=None,
        choices=sorted(dict(WIDE_CANDIDATES, **{BARE_FAN.name: BARE_FAN})),
        help="a named candidate plan; its own start_kind must match --start-kind",
    )
    parser.add_argument("--seeds", type=int, default=200)
    parser.add_argument("--first", type=int, default=0)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--label", default="")
    args = parser.parse_args(argv)

    kind = args.start_kind
    candidates = dict(WIDE_CANDIDATES, **{BARE_FAN.name: BARE_FAN})
    if args.candidate and candidates[args.candidate].start_kind != kind:
        parser.error(
            f"candidate {args.candidate!r} is a "
            f"{candidates[args.candidate].start_kind!r} plan, not {kind!r}"
        )
    plan = candidates[args.candidate] if args.candidate else BENCH_PLANS[kind]
    # Built once here as well as in the workers, so a bad kind fails before a
    # pool is spun up and so the plan that goes into the report is the plan the
    # machine agreed to.
    probe = start_machine(plan=plan)
    if probe.start_kind != kind:                     # pragma: no cover - guarded
        raise AssertionError(f"asked for {kind!r}, machine built {probe.start_kind!r}")
    # **Warm the mesh cache here, in the parent.** `marble3d` caches colliders
    # as OBJ files keyed by content hash and installs them with an atomic
    # rename; seven workers meeting a *fresh* key at the same instant race on
    # that rename, and on Windows the loser gets PermissionError rather than
    # simply finding the file already there. Building the meshes once before
    # the pool exists costs a second and removes the race entirely - and it is
    # a race that only appears the first time a geometry is benchmarked, which
    # is exactly when a new candidate is being measured.
    for module in probe:
        getattr(module, "local_colliders", list)()

    jobs = [
        (kind, args.candidate, seed)
        for seed in range(args.first, args.first + args.seeds)
    ]
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
    report["candidate"] = args.candidate
    print(
        f"{args.label or 'start lab'} [start_kind={report['start_kind']}"
        f"{'' if not args.candidate else ' candidate=' + args.candidate}]: "
        f"{len(results)} trials in {wall:.1f}s"
    )
    print(f"lost {report['lost']} of {report['racers']} ({report['lost_pct']}%)")
    header = ("slot | " + " | ".join(f"{n:>9}" for n in names)
              + " | reach | cross | xed% | coll")
    print(header)
    print("-" * len(header))
    for row in report["slots"]:
        ranks = " | ".join(
            f"{row['mean_rank'][n]:9.3f}" if row["mean_rank"][n] is not None else "        -"
            for n in names
        )

        def maybe(value, fmt="5.2f"):
            return format(value, fmt) if value is not None else "    -"

        print(
            f"  {row['slot']}  | {ranks} | {maybe(row['mean_reach'])} | "
            f"{maybe(row['mean_crossings'])} | {maybe(row['crossed_pct'], '4.0f')} | "
            f"{maybe(row['mean_collisions'], '4.0f')}"
        )
    print("-" * len(header))
    print(
        f"  lateral: mean reach {report['mean_reach']}, mean crossings "
        f"{report['mean_crossings']}, crossed the midline {report['crossed_pct']}%"
    )
    lateral = " ".join(
        f"{n}={'n/a' if report['lateral_order_correlation'][n] is None else format(report['lateral_order_correlation'][n], '+.3f')}"
        for n in names
    )
    print(f"  lateral order kept (1.0 = translated but not mixed): {lateral}")
    for name in names:
        block = report["rank_span"][name]
        if block['span'] is None:
            # A start that delivers nothing produces no ranks at all, and a
            # report that crashes on that is a report that cannot describe a
            # total jam - which is exactly the case worth describing.
            print(f"{name:>13}: no ranks - nothing reached this checkpoint")
        else:
            slot_r = report["slot_rank_correlation"].get(name)
            centre_r = report["centre_rank_correlation"].get(name)
            print(
                f"{name:>13}: span {block['span']:.3f} places, "
                f"best slot {block['best_slot']}, worst slot {block['worst_slot']}, "
                f"slot r {'  n/a' if slot_r is None else format(slot_r, '+.3f')}, "
                f"centre r {'  n/a' if centre_r is None else format(centre_r, '+.3f')}"
            )
    if report["loss_sites"]:
        top = list(report["loss_sites"].items())[:6]
        print("  lost and stuck at: "
              + ", ".join(f"{where} x{count}" for where, count in top))
    if report["incomplete"]:
        print(f"incomplete trials: {report['incomplete']}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

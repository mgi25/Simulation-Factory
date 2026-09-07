"""Run the start lab over many seeds and print the slot table.

    python tools/sloped_start_bench.py --seeds 300
    python tools/sloped_start_bench.py --seeds 300 --json out.json

One trial is about a fifth of a full race, so a 300-seed sweep on seven
workers is a couple of minutes rather than half an hour. That is the whole
point of the lab: section 6 of the brief asks for a cheap candidate loop, and
a candidate has to be rejectable in the time it takes to read the table.
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

from sloped.startlab import LAB_CHECKPOINTS, run_trial, summarise  # noqa: E402


def _one(seed: int):
    # The machine is rebuilt per worker process rather than pickled: a Machine
    # holds meshes and a worker builds it once and reuses it across its chunk.
    global _MACHINE
    try:
        machine = _MACHINE
    except NameError:
        from sloped.startlab import start_machine

        machine = _MACHINE = start_machine()
    return run_trial(seed, machine=machine)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=200)
    parser.add_argument("--first", type=int, default=0)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--label", default="")
    args = parser.parse_args(argv)

    seeds = list(range(args.first, args.first + args.seeds))
    started = time.perf_counter()
    if args.workers > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            results = list(pool.map(_one, seeds, chunksize=4))
    else:
        results = [_one(seed) for seed in seeds]
    wall = time.perf_counter() - started

    report = summarise(results)
    report["wall_seconds"] = round(wall, 2)
    report["label"] = args.label
    report["seeds"] = [args.first, args.first + args.seeds]

    names = [name for name, _ in LAB_CHECKPOINTS]
    print(f"{args.label or 'start lab'}: {len(results)} trials in {wall:.1f}s")
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

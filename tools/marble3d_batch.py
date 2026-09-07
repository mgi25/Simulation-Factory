"""Run many seeds headless and write one summary row each.

    python -m tools.marble3d_batch --count 1000

This is the shape the pipeline is for. Nothing here opens a window, loads a
texture or writes a frame: a batch produces summary rows, a curation pass picks
the seeds worth keeping, and only those are re-run with `--replays` to produce
the files a renderer will draw. Writing a replay for every seed in a
thousand-seed search would be about a gigabyte of JSON to throw away.

Rows are written as JSON Lines, appended as each run finishes, so a batch that
is interrupted after nine hundred seeds has nine hundred usable rows.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time

from marble3d.config import DEFAULT_CONFIG
from marble3d.machines import start_bowl_curve
from marble3d.metrics import summarise
from marble3d.replay import write_replay
from marble3d.simulation import simulate

DEFAULT_OUTPUT = os.path.join("output", "marble3d", "batches")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--start-seed", type=int, default=1)
    parser.add_argument("--marbles", type=int, default=None)
    parser.add_argument("--hz", type=int, default=None)
    parser.add_argument("--out", default=None, help="jsonl path for the summary rows")
    parser.add_argument("--dir", default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--replays",
        default=None,
        help="also write full replays into this directory (slow, large)",
    )
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = DEFAULT_CONFIG
    if args.hz:
        config = config.with_overrides(physics__physics_hz=args.hz)

    path = args.out or os.path.join(
        args.dir, f"marble3d_{args.start_seed}_{args.start_seed + args.count - 1}.jsonl"
    )
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    if args.replays:
        os.makedirs(args.replays, exist_ok=True)

    started = time.perf_counter()
    rows = []
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        for index in range(args.count):
            seed = args.start_seed + index
            replay = simulate(
                seed=seed,
                machine=start_bowl_curve(),
                config=config,
                marble_count=args.marbles,
            )
            row = summarise(replay)
            rows.append(row)
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
            handle.flush()
            if args.replays:
                write_replay(
                    replay, os.path.join(args.replays, f"marble3d_seed{seed:05d}.json")
                )
            if not args.quiet and (index + 1) % 10 == 0:
                elapsed = time.perf_counter() - started
                rate = (index + 1) / elapsed
                remaining = (args.count - index - 1) / rate
                print(
                    f"  {index + 1}/{args.count} seeds, {rate:.1f}/s, "
                    f"{remaining:.0f}s to go",
                    flush=True,
                )

    wall = time.perf_counter() - started
    clean = [row for row in rows if not row["failure"]]
    print(f"\n{args.count} seeds in {wall:.1f}s ({args.count / wall:.2f} seeds/s) -> {path}")
    print(f"  {len(clean)}/{len(rows)} completed with every marble finished")
    if clean:
        turns = [row["revolutions_median"] for row in clean]
        collisions = [row["collisions"] for row in clean]
        seconds = [row["sim_seconds"] for row in clean]
        print(f"  bowl revolutions, median of medians: {statistics.median(turns):.2f} "
              f"(min {min(turns):.2f}, max {max(turns):.2f})")
        print(f"  collisions: median {statistics.median(collisions):.0f}, "
              f"range {min(collisions)}-{max(collisions)}")
        print(f"  run length: median {statistics.median(seconds):.2f}s, "
              f"range {min(seconds):.2f}-{max(seconds):.2f}s")
        orders = {tuple(row["finish_order"]) for row in clean}
        print(f"  distinct finish orders: {len(orders)}/{len(clean)}")
        digests = {row["digest"] for row in clean}
        print(f"  distinct digests: {len(digests)}/{len(clean)}")
    failures = [row for row in rows if row["failure"]]
    if failures:
        print(f"  {len(failures)} run(s) failed:")
        for row in failures[:10]:
            print(f"    seed {row['seed']}: {row['failure']}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

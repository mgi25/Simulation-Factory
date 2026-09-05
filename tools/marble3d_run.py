"""Run one seed of the marble core and write its replay.

    python -m tools.marble3d_run --seed 7
    python -m tools.marble3d_run --seed 7 --digest-only

`--digest-only` prints one line and writes nothing. It is what the
cross-process determinism harness launches: a child interpreter that shares no
memory, no allocator state and no cached geometry with the parent, which is the
only way to test the thing that actually goes wrong - Bullet's broadphase pair
ordering depending on allocation addresses.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from marble3d.config import DEFAULT_CONFIG
from marble3d.machines import start_bowl_curve
from marble3d.metrics import summarise
from marble3d.replay import write_replay
from marble3d.simulation import simulate
from marble3d.units import describe

DEFAULT_OUTPUT = os.path.join("output", "marble3d", "replays")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--marbles", type=int, default=None, help="fewer than the chute holds")
    parser.add_argument("--hz", type=int, default=None, help="override the physics rate")
    parser.add_argument("--duration", type=float, default=None, help="seconds before giving up")
    parser.add_argument("--out", default=None, help="replay path (default: under output/)")
    parser.add_argument("--dir", default=DEFAULT_OUTPUT, help="directory for the default path")
    parser.add_argument("--digest-only", action="store_true", help="print the digest, write nothing")
    parser.add_argument("--json", action="store_true", help="print the summary as JSON")
    parser.add_argument("--units", action="store_true", help="print the unit convention and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.units:
        print(describe())
        return 0

    config = DEFAULT_CONFIG
    if args.hz:
        config = config.with_overrides(physics__physics_hz=args.hz)
    if args.duration:
        config = config.with_overrides(duration_limit=args.duration)

    replay = simulate(
        seed=args.seed,
        machine=start_bowl_curve(),
        config=config,
        marble_count=args.marbles,
    )

    if args.digest_only:
        print(f"{replay.digest()} {replay.event_digest()} {replay.summary['finish_order']}")
        return 0

    path = args.out or os.path.join(args.dir, f"marble3d_seed{args.seed:05d}.json")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    write_replay(replay, path)

    summary = summarise(replay)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        failure = summary["failure"]
        print(f"seed {replay.seed}  ->  {path}")
        print(f"  {summary['finished']} finished, {summary['escaped']} escaped, "
              f"{summary['unfinished']} still in the machine")
        print(f"  {summary['sim_seconds']:.2f} simulated seconds in "
              f"{summary['wall_seconds']:.2f} wall seconds "
              f"({summary['sim_seconds'] / max(summary['wall_seconds'], 1e-9):.1f}x realtime)")
        print(f"  bowl revolutions: median {summary['revolutions_median']:.2f}, "
              f"range {summary['revolutions_min']:.2f} to {summary['revolutions_max']:.2f}")
        print(f"  {summary['collisions']} collisions, worst penetration "
              f"{summary['worst_penetration']:.4f}, largest energy rise "
              f"{summary['max_energy_rise']:.3g}")
        print(f"  finish order: {summary['finish_order']}")
        print(f"  digest: {summary['digest'][:24]}")
        if failure:
            print(f"  FAILURE: {failure}")
    return 1 if summary["failure"] else 0


if __name__ == "__main__":
    sys.exit(main())

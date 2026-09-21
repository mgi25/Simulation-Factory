"""Run the tile-escape prototype over a set of seeds and report what happened.

    python -m satisfying.tile_escape_cli --seeds 1 2 3 4 5 6 7 8 --duration 600 --log
    python -m satisfying.tile_escape_cli --seed 7 --stills docs/validation/category3_tile_escape
    python -m satisfying.tile_escape_cli --seed 7 --digest-only

Phase 1 asks one question - does a ball bouncing in a segmented arena make a
readable, technically reliable "activate every tile" simulation - and this is
the instrument that answers it. It prints, per seed, the things that would
falsify the mechanic: whether the run completed, how long it took, the longest
stretch with no new tile, the longest run of collisions confined to two tiles,
how far the ball ever got outside its allowed region, and how much energy the
solver lost.

`--log` prints the activation log the brief asks for, one line per new tile:

    8.42s | tile_17 | NEW | 31/48

`--log-duplicates` adds the repeat hits, which outnumber activations by roughly
four to one and are the reason the default is off.

`--digest-only` prints one line and nothing else, so a test can run this in a
fresh interpreter and compare the digest with the one the parent process got.
That is the determinism check the repository's other simulations make through
`tools/marble3d_run.py --digest-only`, and it is here for the same reason: a
same-process repeat shares a warm interpreter with its predecessor and cannot
see state that leaks across processes.

Nothing in this module writes to the repository unless asked. `--report` writes
the JSON; `--stills` writes the 9:16 captures.

## Why this driver is not in `tools/`

Every other simulation in this repository puts its driver in `tools/`, and this
one would too but for a rule that has nothing to do with Category 3. `tools/`
is a declared production root, and three Company OS tests - the
`test_this_branch_changed_no_race_fight_or_v30_code` guards in
`tests/test_company_os_research*.py` - refuse *any* file added under a
production root that is not on their two-entry additive allowlist. Landing a
driver in `tools/` therefore turns three green Company OS tests red on this
branch, and widening that allowlist means editing Company OS tests from a
Category 3 branch, which this workstream is not allowed to do.

So the driver sits with the code it drives. That is a smaller compromise than
either of the alternatives, it keeps every line of Category 3 in one directory,
and it leaves the allowlist decision with whoever owns those guards. If they
widen it for Category 3, this module moves to `tools/tile_escape_run.py`
unchanged.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Sequence

sys.path.insert(0, os.getcwd())

from satisfying.tile_arena import polygon_arena
from satisfying.tile_escape import TileEscapeConfig, reachability_margin, simulate

HEADER = (
    f"{'seed':>6} {'done':>5} {'finish':>8} {'coll':>6} {'dup':>6} {'c/s':>6} "
    f"{'dead_s':>8} {'dead_n':>7} {'loop':>5} {'graze':>6} {'hits_max':>9} "
    f"{'outside':>10} {'drift':>10}"
)


def row(seed: int, summary: dict[str, Any]) -> str:
    finish = summary["completion_seconds"]
    return (
        f"{seed:>6} {'yes' if summary['completed'] else 'NO':>5} "
        f"{(f'{finish:.1f}' if finish is not None else '-'):>8} "
        f"{summary['collisions']:>6} {summary['duplicate_hits']:>6} "
        f"{summary['collisions_per_second']:>6.2f} "
        f"{summary['longest_no_progress_seconds']:>8.1f} "
        f"{summary['longest_no_progress_collisions']:>7} "
        f"{summary['longest_confined_run']:>5} {summary['grazing_collisions']:>6} "
        f"{summary['hits_max']:>9} {summary['max_wall_excursion']:>10.1e} "
        f"{summary['energy_drift_relative']:>10.1e}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, nargs="+", default=None)
    parser.add_argument("--seed", type=int, default=None, help="shorthand for one seed")
    parser.add_argument("--duration", type=float, default=600.0)
    parser.add_argument("--speed", type=float, default=TileEscapeConfig.speed)
    parser.add_argument("--gravity", type=float, default=TileEscapeConfig.gravity)
    parser.add_argument(
        "--restitution", type=float, default=TileEscapeConfig.restitution
    )
    parser.add_argument(
        "--ball-radius", type=float, default=TileEscapeConfig.ball_radius
    )
    parser.add_argument("--sides", type=int, default=16)
    parser.add_argument("--tiles-per-side", type=int, default=3)
    parser.add_argument("--circumradius", type=float, default=10.0)
    parser.add_argument("--log", action="store_true", help="print the activation log")
    parser.add_argument(
        "--log-duplicates", action="store_true", help="include repeat hits in the log"
    )
    parser.add_argument("--stills", default=None, help="directory for 9:16 captures")
    parser.add_argument("--report", default=None, help="path for the JSON report")
    parser.add_argument(
        "--digest-only",
        action="store_true",
        help="print one machine-readable line, for the cross-process determinism check",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    seeds = args.seeds if args.seeds else ([args.seed] if args.seed is not None else None)
    if seeds is None:
        seeds = [1, 2, 3, 4, 5, 6, 7, 8]

    arena = polygon_arena(
        sides=args.sides,
        tiles_per_side=args.tiles_per_side,
        circumradius=args.circumradius,
    )
    config = TileEscapeConfig(
        speed=args.speed,
        gravity=args.gravity,
        restitution=args.restitution,
        ball_radius=args.ball_radius,
        duration=args.duration,
    )

    if args.digest_only:
        run = simulate(seeds[0], config, arena)
        finish = run.completion_time if run.completion_time is not None else -1.0
        print(
            f"{run.state_digest()} {len(run.collisions)} {run.activated_tiles} "
            f"{finish:.9f}"
        )
        return 0

    margin = reachability_margin(config, arena)
    print(
        f"arena {arena.sides} sides x {arena.tiles_per_side} = {arena.total_tiles} "
        f"tiles, tile {arena.tile_length:.3f} wu, ball {2 * config.ball_radius:.3f} wu"
    )
    print(
        f"reachability margin "
        f"{'infinite (no gravity)' if margin == float('inf') else f'{margin:.2f}'}"
        + ("" if margin > 1.0 else "   *** the top of the arena cannot be reached ***")
    )
    print(HEADER)

    started = time.time()
    summaries: list[dict[str, Any]] = []
    stills: dict[str, dict[str, str]] = {}
    for seed in seeds:
        run = simulate(seed, config, arena)
        summary = run.summary()
        summaries.append(summary)
        print(row(seed, summary))

        if args.log or args.log_duplicates:
            for line in run.log_lines(duplicates=args.log_duplicates):
                print(f"       {line}")
            if not run.completed:
                print(
                    f"       incomplete: {len(run.unhit_tiles())} tiles never hit "
                    f"({', '.join(run.unhit_tiles())})"
                )

        if args.stills:
            # Imported here and not at the top: Pillow is only needed when
            # captures are asked for, and the determinism check runs this
            # module in a fresh interpreter on every test run.
            from satisfying.tile_render import write_evidence_stills

            stills[str(seed)] = write_evidence_stills(run, args.stills)

    wall = time.time() - started
    completed = [s for s in summaries if s["completed"]]
    finishes = sorted(s["completion_seconds"] for s in completed)
    print(
        f"{len(completed)}/{len(summaries)} completed; "
        + (
            f"finish min {finishes[0]:.1f}s median {finishes[len(finishes) // 2]:.1f}s "
            f"max {finishes[-1]:.1f}s; "
            if finishes
            else ""
        )
        + f"worst dead period {max(s['longest_no_progress_seconds'] for s in summaries):.1f}s; "
        + f"{wall:.2f}s wall"
    )

    if args.report:
        report = {
            "arena": summaries[0]["arena"] if summaries else {},
            "config": summaries[0]["config"] if summaries else {},
            "reachability_margin": None if margin == float("inf") else round(margin, 3),
            "wall_seconds": round(wall, 3),
            "completed": len(completed),
            "runs": summaries,
            "stills": stills,
        }
        os.makedirs(os.path.dirname(args.report) or ".", exist_ok=True)
        with open(args.report, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(report, handle, indent=1, sort_keys=True)
            handle.write("\n")
        print(f"wrote {args.report}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

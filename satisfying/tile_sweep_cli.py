"""Phase 2's instrument: sweep seeds, judge them, and write the evidence down.

    python -m satisfying.tile_sweep_cli population --count 50000 --report out.json
    python -m satisfying.tile_sweep_cli speed --count 10000 --speeds 50 60 70 80 90
    python -m satisfying.tile_sweep_cli invariance --count 40
    python -m satisfying.tile_sweep_cli candidates --count 50000 --top 20
    python -m satisfying.tile_sweep_cli curves --count 10000 --csv curves.csv
    python -m satisfying.tile_sweep_cli inspect --seed 12345

Six tasks, one per question Phase 2 was asked:

- **population** - the 17 x 3 validation. Completion rate, the completion-time
  percentiles, milestone timings, stagnation, tail clocks, the periodic-orbit
  census and the failure census, over as many seeds as asked for.
- **speed** - the sweep. Runs a real simulation at every speed rather than
  rescaling, so the rescaling claim is demonstrated and not assumed.
- **invariance** - the demonstration itself: same tile sequence, exact time
  ratio, across speeds. This is what makes `speed` cheap and its curve exact.
- **candidates** - the shortlist, with every component metric and the reason
  each seed passed.
- **curves** - the machine-readable activation curves: one CSV of the
  population's per-tile percentiles, one of the shortlisted seeds' own curves.
- **inspect** - one seed in full, including its activation log, for reading a
  candidate by eye before anybody renders it.

Like the Phase 1 driver, this lives beside the code it drives rather than in
`tools/`, for the reason recorded in `satisfying/tile_escape_cli.py` and in
section 2.1 of the Phase 1 report: `tools/` is a declared production root and
three Company OS branch guards refuse additions there. Nothing here writes to
the repository unless a `--report` or `--csv` path is given.
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
from satisfying.tile_escape import TileEscapeConfig, simulate
from satisfying.tile_evaluator import (
    AcceptanceRule,
    activation_curve,
    candidate_score,
    evaluate,
    verdict,
)
from satisfying.tile_sweep import (
    PHASE2_CONFIG,
    activation_curve_percentiles,
    distribution,
    population_report,
    shortlist,
    sweep,
    verify_speed_invariance,
)


def _write_json(path: str | None, payload: Any) -> None:
    if not path:
        return
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=1, sort_keys=True)
        handle.write("\n")
    print(f"wrote {path}")


def _write_csv(path: str | None, header: str, rows: Sequence[str]) -> None:
    if not path:
        return
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(header + "\n")
        for row in rows:
            handle.write(row + "\n")
    print(f"wrote {path} ({len(rows)} rows)")


def _config(args: argparse.Namespace) -> TileEscapeConfig:
    return TileEscapeConfig(
        **{
            **PHASE2_CONFIG.as_dict(),
            "speed": args.speed,
            "gravity": args.gravity,
            "ball_radius": args.ball_radius,
        }
    )


def _arena(args: argparse.Namespace):
    return polygon_arena(
        sides=args.sides,
        tiles_per_side=args.tiles_per_side,
        circumradius=args.circumradius,
    )


def _seeds(args: argparse.Namespace) -> range:
    return range(args.seed_start, args.seed_start + args.count)


def _line(label: str, stats: dict[str, Any]) -> str:
    if not stats.get("count"):
        return f"{label:<28} (no data)"
    return (
        f"{label:<28} n={stats['count']:>6} min={stats['min']:>8.2f} "
        f"p10={stats['p10']:>8.2f} p25={stats['p25']:>8.2f} p50={stats['p50']:>8.2f} "
        f"p75={stats['p75']:>8.2f} p90={stats['p90']:>8.2f} p95={stats['p95']:>8.2f} "
        f"p99={stats['p99']:>9.2f} max={stats['max']:>9.2f}"
    )


# --------------------------------------------------------------------------
# population
# --------------------------------------------------------------------------


def task_population(args: argparse.Namespace) -> int:
    arena, config = _arena(args), _config(args)
    rule = AcceptanceRule()
    started = time.time()
    evaluations = sweep(_seeds(args), config, arena)
    wall = time.time() - started

    report = population_report(evaluations, rule, config, arena)
    report["wall_seconds"] = round(wall, 2)
    report["seed_range"] = [args.seed_start, args.seed_start + args.count - 1]

    print(
        f"{arena.sides} x {arena.tiles_per_side} = {arena.total_tiles} tiles, "
        f"speed {config.speed}, gravity {config.gravity}, "
        f"{args.count} seeds in {wall:.1f}s"
    )
    completion = report["completion"]
    print(
        f"completed {completion['completed']}/{args.count} "
        f"({100 * completion['completion_rate']:.2f}%)"
    )
    print(_line("completion seconds", completion["seconds"]))
    print(_line("collisions", completion["collisions"]))
    print(_line("collisions/second", completion["collisions_per_second"]))
    print()
    for name, stats in report["milestones"].items():
        print(_line(f"milestone {name}", stats))
    print()
    for name, stats in report["stagnation"].items():
        print(_line(f"stagnation {name}", stats))
    print()
    for name, stats in report["tail"].items():
        print(_line(f"tail {name}", stats))
    print()
    for name, stats in report["periodic"].items():
        if isinstance(stats, dict) and "count" in stats:
            print(_line(f"periodic {name}", stats))
    print(f"two-tile run histogram   {report['periodic']['two_tile_run_histogram']}")
    print(f"tile-cycle period hist   {report['periodic']['tile_cycle_period_histogram']}")
    print(f"side-cycle period hist   {report['periodic']['side_cycle_period_histogram']}")
    print()
    acceptance = report["acceptance"]
    print(
        f"accepted {acceptance['accepted']}/{args.count} "
        f"({100 * acceptance['accept_rate']:.3f}%)"
    )
    for name, count in acceptance["failure_counts"].items():
        print(f"   failed {name:<26} {count:>7} ({100 * count / args.count:.2f}%)")

    _write_json(args.report, report)
    return 0


# --------------------------------------------------------------------------
# speed
# --------------------------------------------------------------------------


def task_speed(args: argparse.Namespace) -> int:
    arena = _arena(args)
    rule = AcceptanceRule()
    rows: list[dict[str, Any]] = []
    print(
        f"{arena.total_tiles} tiles, gravity {args.gravity}, {args.count} seeds per speed"
    )
    header = (
        f"{'speed':>6} {'done%':>7} {'p10':>7} {'p25':>7} {'p50':>7} {'p75':>7} "
        f"{'p90':>7} {'coll/s':>7} {'in25_40%':>9} {'in28_38%':>9} {'accept%':>8} "
        f"{'finaltile_p50':>14}"
    )
    print(header)
    for speed in args.speeds:
        config = TileEscapeConfig(**{**_config(args).as_dict(), "speed": speed})
        started = time.time()
        evaluations = sweep(_seeds(args), config, arena)
        wall = time.time() - started
        complete = [e for e in evaluations if e.completed]
        finishes = sorted(e.completion_seconds for e in complete)
        in_envelope = sum(1 for f in finishes if 25.0 <= f <= 40.0)
        in_core = sum(1 for f in finishes if 28.0 <= f <= 38.0)
        accepted = sum(1 for e in evaluations if verdict(e, rule).accepted)
        row = {
            "speed": speed,
            "seeds": args.count,
            "completed": len(complete),
            "completion_rate": round(len(complete) / args.count, 5),
            "seconds": distribution(finishes),
            "collisions": distribution([float(e.collisions) for e in complete]),
            "collisions_per_second": distribution(
                [e.collisions_per_second for e in complete]
            ),
            "in_envelope_25_40": in_envelope,
            "in_envelope_25_40_rate": round(in_envelope / args.count, 5),
            "in_core_28_38": in_core,
            "in_core_28_38_rate": round(in_core / args.count, 5),
            "accepted": accepted,
            "accept_rate": round(accepted / args.count, 5),
            "final_tile_seconds": distribution(
                [e.final_tile_seconds for e in complete if e.final_tile_seconds is not None]
            ),
            "longest_body_gap_seconds": distribution(
                [e.longest_body_gap_seconds for e in complete]
            ),
            "wall_seconds": round(wall, 2),
        }
        rows.append(row)
        seconds, rate = row["seconds"], row["collisions_per_second"]
        print(
            f"{speed:>6.1f} {100 * row['completion_rate']:>7.2f} "
            f"{seconds['p10']:>7.1f} {seconds['p25']:>7.1f} {seconds['p50']:>7.1f} "
            f"{seconds['p75']:>7.1f} {seconds['p90']:>7.1f} {rate['p50']:>7.2f} "
            f"{100 * row['in_envelope_25_40_rate']:>9.2f} "
            f"{100 * row['in_core_28_38_rate']:>9.2f} "
            f"{100 * row['accept_rate']:>8.3f} "
            f"{row['final_tile_seconds']['p50']:>14.2f}"
        )

    _write_json(
        args.report,
        {
            "arena": {"sides": arena.sides, "total_tiles": arena.total_tiles},
            "gravity": args.gravity,
            "seed_range": [args.seed_start, args.seed_start + args.count - 1],
            "rows": rows,
        },
    )
    return 0


# --------------------------------------------------------------------------
# invariance
# --------------------------------------------------------------------------


def task_invariance(args: argparse.Namespace) -> int:
    arena = _arena(args)
    result = verify_speed_invariance(
        list(_seeds(args)), args.speeds, args.speed, arena, _config(args)
    )
    print(
        f"speed invariance over {args.count} seeds x {len(args.speeds)} speeds "
        f"(reference {args.speed} wu/s, gravity {args.gravity})"
    )
    mismatches = [r for r in result["rows"] if not r["same_tile_sequence"]]
    print(f"identical tile sequences: {len(result['rows']) - len(mismatches)}/{len(result['rows'])}")
    print(f"worst relative time error: {result['worst_relative_time_error']:.3e}")
    print(f"INVARIANT: {result['invariant']}")

    # A second, independent demonstration: arena scale is the same dial as
    # speed, so halving both leaves the run identical in every respect.
    half = polygon_arena(
        sides=args.sides, tiles_per_side=args.tiles_per_side, circumradius=args.circumradius / 2
    )
    scaled_ok = True
    for seed in list(_seeds(args))[:10]:
        base = simulate(seed, _config(args), arena)
        small = simulate(
            seed,
            TileEscapeConfig(
                **{
                    **_config(args).as_dict(),
                    "speed": args.speed / 2.0,
                    "ball_radius": args.ball_radius / 2.0,
                }
            ),
            half,
        )
        same = [c.tile_index for c in base.collisions] == [
            c.tile_index for c in small.collisions
        ]
        ratio = (
            small.completion_time / base.completion_time
            if base.completion_time and small.completion_time
            else None
        )
        if not same or ratio is None or abs(ratio - 1.0) > 1.0e-9:
            scaled_ok = False
    print(
        f"half arena + half speed reproduces the run exactly: {scaled_ok} "
        f"(so arena scale and speed are one dial, not two)"
    )
    result["arena_scale_is_the_same_dial"] = scaled_ok

    _write_json(args.report, result)
    return 0


# --------------------------------------------------------------------------
# candidates
# --------------------------------------------------------------------------

CANDIDATE_HEADER = (
    f"{'seed':>8} {'score':>6} {'total':>6} {'first':>6} {'25%':>6} {'50%':>6} "
    f"{'75%':>6} {'90%':>6} {'49/51':>6} {'50/51':>6} {'last3':>6} {'last1':>6} "
    f"{'bodygap':>8} {'coll':>5} {'c/s':>5} {'dup%':>5} {'loop':>4}"
)


def candidate_row(candidate: Any) -> str:
    e = candidate.evaluation
    m = e.milestones

    def s(value: float | None) -> str:
        return "-" if value is None else f"{value:.1f}"

    return (
        f"{e.seed:>8} {candidate.score.total:>6.3f} {s(e.completion_seconds):>6} "
        f"{s(e.first_collision_seconds):>6} {s(m['p25']):>6} {s(m['p50']):>6} "
        f"{s(m['p75']):>6} {s(m['p90']):>6} {s(m['n_minus_2']):>6} "
        f"{s(m['n_minus_1']):>6} {s(e.final_three_seconds):>6} "
        f"{s(e.final_tile_seconds):>6} {e.longest_body_gap_seconds:>8.2f} "
        f"{e.collisions:>5} {e.collisions_per_second:>5.1f} "
        f"{100 * e.duplicate_share:>5.1f} {e.longest_two_tile_run.length:>4}"
    )


def task_candidates(args: argparse.Namespace) -> int:
    arena, config = _arena(args), _config(args)
    rule = AcceptanceRule()
    started = time.time()
    evaluations = sweep(_seeds(args), config, arena)
    picks = shortlist(evaluations, rule, args.top)
    wall = time.time() - started

    accepted = sum(1 for e in evaluations if verdict(e, rule).accepted)
    print(
        f"{args.count} seeds at speed {config.speed} in {wall:.1f}s; "
        f"{accepted} accepted ({100 * accepted / args.count:.3f}%), showing top {len(picks)}"
    )
    print(CANDIDATE_HEADER)
    for candidate in picks:
        print(candidate_row(candidate))

    _write_json(
        args.report,
        {
            "seed_range": [args.seed_start, args.seed_start + args.count - 1],
            "config": config.as_dict(),
            "arena": {"sides": arena.sides, "total_tiles": arena.total_tiles},
            "rule": rule.as_dict(),
            "accepted_total": accepted,
            "accept_rate": round(accepted / args.count, 6),
            "candidates": [c.as_dict() for c in picks],
        },
    )

    if args.csv:
        rows: list[str] = []
        for candidate in picks:
            for moment, count in activation_curve(
                simulate(candidate.seed, config, arena)
            ):
                rows.append(f"{candidate.seed},{moment:.6f},{count}")
        _write_csv(args.csv, "seed,seconds,activated", rows)
    return 0


# --------------------------------------------------------------------------
# curves
# --------------------------------------------------------------------------


def task_curves(args: argparse.Namespace) -> int:
    arena, config = _arena(args), _config(args)

    def stream():
        for seed in _seeds(args):
            run = simulate(seed, config, arena)
            if run.completed:
                yield activation_curve(run)

    started = time.time()
    rows = activation_curve_percentiles(stream())
    print(f"activation-curve percentiles over {args.count} seeds in {time.time() - started:.1f}s")
    print(f"{'lit':>4} {'runs':>7} {'p10':>8} {'p25':>8} {'p50':>8} {'p75':>8} {'p90':>8} {'d p50':>8}")
    previous = 0.0
    for row in rows:
        print(
            f"{row['activated']:>4} {row['runs']:>7} {row['p10']:>8.2f} "
            f"{row['p25']:>8.2f} {row['p50']:>8.2f} {row['p75']:>8.2f} "
            f"{row['p90']:>8.2f} {row['p50'] - previous:>8.2f}"
        )
        previous = row["p50"]

    _write_csv(
        args.csv,
        "activated,runs,p10,p25,p50,p75,p90",
        [
            f"{r['activated']},{r['runs']},{r['p10']:.3f},{r['p25']:.3f},"
            f"{r['p50']:.3f},{r['p75']:.3f},{r['p90']:.3f}"
            for r in rows
        ],
    )
    _write_json(args.report, {"seeds": args.count, "rows": rows})
    return 0


# --------------------------------------------------------------------------
# inspect
# --------------------------------------------------------------------------


def task_inspect(args: argparse.Namespace) -> int:
    arena, config = _arena(args), _config(args)
    run = simulate(args.seed, config, arena)
    evaluation = evaluate(run)
    outcome = verdict(evaluation, AcceptanceRule())
    score = candidate_score(evaluation)

    print(json.dumps(evaluation.as_dict(), indent=1, sort_keys=True))
    print(json.dumps({"verdict": outcome.as_dict(), "score": score.as_dict()}, indent=1))
    if args.log:
        for line in run.log_lines(duplicates=args.log_duplicates):
            print(line)
    _write_json(
        args.report,
        {
            "evaluation": evaluation.as_dict(),
            "verdict": outcome.as_dict(),
            "score": score.as_dict(),
            "digest": run.state_digest(),
            "activation_curve": [[round(t, 6), n] for t, n in activation_curve(run)],
        },
    )
    return 0


TASKS = {
    "population": task_population,
    "speed": task_speed,
    "invariance": task_invariance,
    "candidates": task_candidates,
    "curves": task_curves,
    "inspect": task_inspect,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("task", choices=sorted(TASKS))
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument("--count", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=0, help="the one seed `inspect` reads")
    parser.add_argument("--speed", type=float, default=PHASE2_CONFIG.speed)
    parser.add_argument(
        "--speeds",
        type=float,
        nargs="+",
        default=[50.0, 55.0, 60.0, 65.0, 70.0],
        help="the speed sweep, in wu/s",
    )
    parser.add_argument("--gravity", type=float, default=PHASE2_CONFIG.gravity)
    parser.add_argument("--ball-radius", type=float, default=PHASE2_CONFIG.ball_radius)
    parser.add_argument("--sides", type=int, default=17)
    parser.add_argument("--tiles-per-side", type=int, default=3)
    parser.add_argument("--circumradius", type=float, default=10.0)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--report", default=None, help="path for the JSON evidence")
    parser.add_argument("--csv", default=None, help="path for the CSV evidence")
    parser.add_argument("--log", action="store_true")
    parser.add_argument("--log-duplicates", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return TASKS[args.task](args)


if __name__ == "__main__":
    raise SystemExit(main())

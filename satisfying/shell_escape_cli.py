"""Driver for Category 3 Test #2: batches, sweeps, shortlists and documents.

Everything Phase 1 has to answer is a question about a *population*, not about
one run, so this is where the population work lives. Follows the convention
Test #1 set: the CLI is part of the package rather than a `tools/` script,
because it is experiment scaffolding and not production tooling.

    python -m satisfying.shell_escape_cli batch --seeds 10000 --out batch.json
    python -m satisfying.shell_escape_cli sweep --axis speed --values 14,16,18
    python -m satisfying.shell_escape_cli shortlist --seeds 20000 --take 16
    python -m satisfying.shell_escape_cli document --seed 4471 --out run.json
    python -m satisfying.shell_escape_cli verify --path run.json
    python -m satisfying.shell_escape_cli describe --seed 4471

Batches run over a process pool because the simulation is pure - a seed and a
config in, a run out, no shared state - so the only thing to get right is not
sending the whole event stream back through the pickle boundary. Workers return
the evaluation, not the run.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from typing import Any, Iterable, Sequence

from satisfying.shell_escape import DEFAULT_CONFIG, ShellEscapeConfig, simulate
from satisfying.shell_evaluator import (
    DEFAULT_THRESHOLDS,
    EvaluationThresholds,
    RunEvaluation,
    evaluate,
    summarise,
)
from satisfying.shell_playback import playback_document, read_playback, verify_document, write_playback

__all__ = ["main", "run_batch", "shortlist"]


# --------------------------------------------------------------------------
# Batch machinery
# --------------------------------------------------------------------------


def _worker(payload: tuple[int, dict[str, Any], dict[str, Any]]) -> dict[str, Any]:
    """Simulate and evaluate one seed, and hand back only the headline.

    The full metrics dictionary carries a per-collision timeline and a region
    timeline; multiplied by ten thousand seeds that is hundreds of megabytes
    crossing a pipe for numbers nobody reads. The aggregate is built from the
    headline plus the handful of nested values `summarise` needs, so what comes
    back is a few hundred bytes.
    """
    seed, config_fields, threshold_fields = payload
    config = ShellEscapeConfig(**_retuple(config_fields))
    thresholds = EvaluationThresholds(**threshold_fields)
    evaluation = evaluate(simulate(seed, config), thresholds)
    return _compact(evaluation)


def _retuple(fields: dict[str, Any]) -> dict[str, Any]:
    out = dict(fields)
    for key in ("panel_counts", "openings_per_shell", "opening_slots"):
        out[key] = tuple(out[key])
    return out


COMPACT_PATHS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("escaped", ("outcome", "escaped")),
    ("duration", ("outcome", "duration")),
    ("max_region", ("outcome", "max_region")),
    ("digest", ("outcome", "digest")),
    ("collisions", ("collisions", "total")),
    ("collision_rate", ("collisions", "per_second")),
    ("grazing", ("collisions", "grazing")),
    ("post_contacts", ("collisions", "post_contacts")),
    ("near_misses", ("near_misses", "total")),
    ("near_miss_rate", ("near_misses", "per_second")),
    ("breaks", ("damage", "breaks")),
    ("first_break", ("damage", "first_break")),
    ("progression_opening", ("routes", "progression_opening")),
    ("progression_break", ("routes", "progression_break")),
    ("exit_opening", ("routes", "exit_opening")),
    ("exit_break", ("routes", "exit_break")),
    ("final_method", ("routes", "final_method")),
    ("regressions", ("progression", "regressions")),
    ("max_region_share", ("progression", "max_region_share")),
    ("longest_no_event", ("stagnation", "longest_no_event")),
    ("longest_no_progress", ("stagnation", "longest_no_progress")),
    ("middle_third_stagnation", ("stagnation", "middle_third_stagnation")),
    ("longest_cycle_run", ("repetition", "longest_cycle_run")),
    ("distinct_panels", ("repetition", "distinct_panels")),
    ("max_penetration", ("instruments", "max_penetration")),
    ("speed_drift_relative", ("instruments", "speed_drift_relative")),
    ("max_speed_correction", ("instruments", "max_speed_correction")),
    ("anomalous_crossings", ("instruments", "anomalous_crossings")),
    ("newton_failures", ("instruments", "newton_failures")),
)


def _compact(evaluation: RunEvaluation) -> dict[str, Any]:
    out: dict[str, Any] = {"seed": evaluation.seed, "flags": list(evaluation.flags)}
    for name, path in COMPACT_PATHS:
        value: Any = evaluation.metrics
        for key in path:
            value = value[key]
        out[name] = value
    out["escalation"] = {
        key: evaluation.metrics["escalation"][key]
        for key in ("collisions", "near_misses", "breaks", "progress")
    }
    out["dwell"] = [round(v, 4) for v in evaluation.metrics["progression"]["dwell"]]
    out["near_misses_per_shell"] = evaluation.metrics["near_misses"]["per_shell"]
    out["collisions_per_shell"] = evaluation.metrics["collisions"]["per_shell"]
    out["breaks_per_shell"] = evaluation.metrics["damage"]["breaks_per_shell"]
    return out


def _rehydrate(records: Sequence[dict[str, Any]]) -> list[RunEvaluation]:
    """Rebuild just enough of a `RunEvaluation` for `summarise` to work."""
    out: list[RunEvaluation] = []
    for record in records:
        metrics: dict[str, Any] = {}
        for name, path in COMPACT_PATHS:
            node = metrics
            for key in path[:-1]:
                node = node.setdefault(key, {})
            node[path[-1]] = record[name]
        metrics["escalation"] = record["escalation"]
        metrics["progression"]["dwell"] = record["dwell"]
        metrics["near_misses"]["per_shell"] = record["near_misses_per_shell"]
        metrics["collisions"]["per_shell"] = record["collisions_per_shell"]
        metrics["damage"]["breaks_per_shell"] = record["breaks_per_shell"]
        metrics["outcome"]["shell_count"] = len(record["dwell"]) - 1
        out.append(RunEvaluation(seed=record["seed"], metrics=metrics, flags=list(record["flags"])))
    return out


def run_batch(
    seeds: Iterable[int],
    config: ShellEscapeConfig = DEFAULT_CONFIG,
    thresholds: EvaluationThresholds = DEFAULT_THRESHOLDS,
    workers: int | None = None,
    chunk: int = 64,
) -> list[dict[str, Any]]:
    """Simulate and evaluate a whole population."""
    seeds = list(seeds)
    payload = [(seed, config.as_dict(), thresholds.as_dict()) for seed in seeds]
    if workers == 1:
        return [_worker(item) for item in payload]
    with ProcessPoolExecutor(max_workers=workers or os.cpu_count()) as pool:
        return list(pool.map(_worker, payload, chunksize=chunk))


# --------------------------------------------------------------------------
# Shortlisting
# --------------------------------------------------------------------------


def shortlist(
    records: Sequence[dict[str, Any]],
    take: int = 16,
    thresholds: EvaluationThresholds = DEFAULT_THRESHOLDS,
) -> list[dict[str, Any]]:
    """Pick a varied set of strong seeds, by bucket rather than by rank.

    A ranked list would hand the visual and audio branches sixteen versions of
    the same run, because whatever is ranked first is what the top of the list
    is made of. Instead the acceptable band is cut into three sub-bands, and
    each is filled with clean seeds ordered by how much is *in* them - near
    misses, breaks, and progression that used both routes - with the seeds that
    came through a broken panel at the last shell deliberately kept, because
    the outer-shell resolution is the shot the whole video is built towards and
    the branches should have more than one kind of it to choose from.
    """
    clean = [
        r
        for r in records
        if not r["flags"] and thresholds.acceptable_low <= r["duration"] <= thresholds.acceptable_high
    ]
    bands = (
        ("20-22s", 20.0, 22.0),
        ("22-24s", 22.0, 24.0),
        ("24-26s", 24.0, 26.0),
        ("18-20s", 18.0, 20.0),
    )
    per_band = max(1, take // len(bands))
    picked: list[dict[str, Any]] = []
    used: set[int] = set()

    def interest(record: dict[str, Any]) -> tuple:
        both = 1 if (record["progression_opening"] > 0 and record["progression_break"] > 0) else 0
        late = record["escalation"]["near_misses"][2]
        # How many regions got a real share of the runtime. A count, not a
        # share, and deliberately so: both of the obvious continuous measures
        # were tried and both collapsed the list. Ranking on near misses alone
        # picks inner-shell hogs, because a ball rattling in the core collects
        # near misses faster than one making progress. Ranking on the share of
        # the run spent *outside* the core picks the mirror image - runs that
        # blast out of the middle in four seconds and grind in one outer
        # annulus - and being continuous it never ties, so it becomes the only
        # thing sorting the list and the near-miss counts collapse with it. A
        # count of regions ties constantly, which is the point: it rules out
        # both extremes and then lets near misses decide.
        duration = max(record["duration"], 1e-9)
        spread = sum(1 for value in record["dwell"][:6] if value / duration >= 0.08)
        return (
            both,
            spread,
            record["near_misses"],
            late,
            record["breaks"],
            -record["longest_no_event"],
        )

    for name, low, high in bands:
        pool = sorted(
            (r for r in clean if low <= r["duration"] < high and r["seed"] not in used),
            key=interest,
            reverse=True,
        )
        for record in pool[:per_band]:
            entry = dict(record)
            entry["band"] = name
            picked.append(entry)
            used.add(record["seed"])

    # Make sure at least one candidate leaves through a broken outer panel and
    # at least one through an opening, whatever the bands happened to produce.
    for method in ("break", "opening"):
        if not any(p["final_method"] == method for p in picked):
            extra = sorted(
                (r for r in clean if r["final_method"] == method and r["seed"] not in used),
                key=interest,
                reverse=True,
            )
            if extra:
                entry = dict(extra[0])
                entry["band"] = f"final-{method}"
                picked.append(entry)
                used.add(entry["seed"])

    while len(picked) < take:
        pool = sorted((r for r in clean if r["seed"] not in used), key=interest, reverse=True)
        if not pool:
            break
        entry = dict(pool[0])
        entry["band"] = "extra"
        picked.append(entry)
        used.add(entry["seed"])
    return picked[:take]


# --------------------------------------------------------------------------
# Config overrides on the command line
# --------------------------------------------------------------------------


def _parse_value(current: Any, text: str) -> Any:
    if isinstance(current, tuple):
        return tuple(int(part) for part in text.split(","))
    if isinstance(current, bool):
        return text.lower() in ("1", "true", "yes", "on")
    if isinstance(current, int):
        return int(text)
    return float(text)


def apply_overrides(config: ShellEscapeConfig, pairs: Sequence[str]) -> ShellEscapeConfig:
    """`--set speed=18 --set panel_counts=12,13,14,15,16,17`."""
    changes: dict[str, Any] = {}
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit(f"--set expects name=value, got {pair!r}")
        name, text = pair.split("=", 1)
        if not hasattr(config, name):
            raise SystemExit(f"unknown config field {name!r}")
        changes[name] = _parse_value(getattr(config, name), text)
    return replace(config, **changes)


def _seed_range(text: str) -> list[int]:
    if ":" in text:
        start, stop = text.split(":", 1)
        return list(range(int(start), int(stop)))
    return list(range(int(text)))


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


def _write(path: str | None, payload: Any) -> None:
    text = json.dumps(payload, indent=1, sort_keys=False, default=str)
    if path:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
        print(f"wrote {path} ({len(text)} bytes)")
    else:
        print(text)


def cmd_batch(args: argparse.Namespace) -> int:
    config = apply_overrides(DEFAULT_CONFIG, args.set or [])
    seeds = _seed_range(args.seeds)
    started = time.perf_counter()
    records = run_batch(seeds, config, DEFAULT_THRESHOLDS, workers=args.workers)
    elapsed = time.perf_counter() - started
    report = {
        "seeds": len(seeds),
        "seconds": elapsed,
        "seeds_per_second": len(seeds) / elapsed if elapsed else float("inf"),
        "config": config.as_dict(),
        "config_digest": config.digest(),
        "summary": summarise(_rehydrate(records), DEFAULT_THRESHOLDS),
    }
    if args.records:
        _write(args.records, records)
    _write(args.out, report)
    summary = report["summary"]
    print(
        f"escape {summary['outcome']['escape_rate']*100:.1f}%  "
        f"usable {summary['outcome']['usable_rate']*100:.1f}%  "
        f"in-band {summary['outcome']['in_acceptable_band']}  "
        f"preferred {summary['outcome']['in_preferred_band']}  "
        f"({elapsed:.1f}s)"
    )
    return 0


def cmd_sweep(args: argparse.Namespace) -> int:
    base = apply_overrides(DEFAULT_CONFIG, args.set or [])
    seeds = _seed_range(args.seeds)
    rows: list[dict[str, Any]] = []
    for text in args.values.split(";"):
        config = apply_overrides(base, [f"{args.axis}={text}"])
        records = run_batch(seeds, config, DEFAULT_THRESHOLDS, workers=args.workers)
        summary = summarise(_rehydrate(records), DEFAULT_THRESHOLDS)
        rows.append(
            {
                "axis": args.axis,
                "value": text,
                "config_digest": config.digest(),
                "escape_rate": summary["outcome"]["escape_rate"],
                "usable_rate": summary["outcome"]["usable_rate"],
                "in_acceptable_band": summary["outcome"]["in_acceptable_band"],
                "in_preferred_band": summary["outcome"]["in_preferred_band"],
                "median_duration": summary["duration"]["quantiles"]["p50"],
                "median_collision_rate": summary["collisions"]["rate_quantiles"]["p50"],
                "median_near_misses": summary["near_misses"]["quantiles"]["p50"],
                "median_breaks": summary["breaks"]["quantiles"]["p50"],
                "progression_opening_share": summary["routes"]["progression_opening_share"],
                "escaped_using_both": summary["routes"]["escaped_using_both"],
                "pathological": summary["repetition"]["pathological"],
                "flags": summary["flags"],
                "instruments": summary["instruments"],
            }
        )
        print(
            f"{args.axis}={text:>22s}  escape {rows[-1]['escape_rate']*100:5.1f}%  "
            f"usable {rows[-1]['usable_rate']*100:5.1f}%  band {rows[-1]['in_acceptable_band']:5d}  "
            f"med {rows[-1]['median_duration']:5.2f}  c/s {rows[-1]['median_collision_rate']:4.2f}  "
            f"nm {rows[-1]['median_near_misses']:4.1f}  open {rows[-1]['progression_opening_share']*100:4.1f}%"
        )
    _write(args.out, {"seeds": len(seeds), "base": base.as_dict(), "rows": rows})
    return 0


def cmd_shortlist(args: argparse.Namespace) -> int:
    config = apply_overrides(DEFAULT_CONFIG, args.set or [])
    seeds = _seed_range(args.seeds)
    records = run_batch(seeds, config, DEFAULT_THRESHOLDS, workers=args.workers)
    picked = shortlist(records, args.take, DEFAULT_THRESHOLDS)
    _write(
        args.out,
        {
            "seeds_searched": len(seeds),
            "config": config.as_dict(),
            "config_digest": config.digest(),
            "candidates": picked,
        },
    )
    for record in picked:
        print(
            f"seed {record['seed']:6d} {record['band']:>12s} t={record['duration']:6.2f} "
            f"col={record['collisions']:4d} nm={record['near_misses']:3d} brk={record['breaks']:3d} "
            f"open/brk={record['progression_opening']}/{record['progression_break']} "
            f"final={record['final_method']} digest={record['digest'][:12]}"
        )
    return 0


def cmd_document(args: argparse.Namespace) -> int:
    config = apply_overrides(DEFAULT_CONFIG, args.set or [])
    run = simulate(args.seed, config)
    document = playback_document(run)
    if args.out:
        write_playback(document, args.out)
        print(f"wrote {args.out}  digest={document['digest']}")
    else:
        print(json.dumps(document["summary"], indent=1, default=str))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    document = read_playback(args.path)
    result = verify_document(document)
    print(json.dumps(result, indent=1, default=str))
    return 0 if all(v is True for k, v in result.items() if k.endswith("matches")) else 1


def cmd_describe(args: argparse.Namespace) -> int:
    config = apply_overrides(DEFAULT_CONFIG, args.set or [])
    run = simulate(args.seed, config)
    evaluation = evaluate(run)
    print(json.dumps(evaluation.headline(), indent=1, default=str))
    print("fit:", json.dumps(run.arena.fit_report(), default=str))
    print("timeline:")
    for span in evaluation.metrics["progression"]["timeline"]:
        print(
            f"  region {span['region']}  {span['enter_t']:6.2f} -> {span['exit_t']:6.2f}"
            f"  ({span['duration']:5.2f}s)  in via {span['entered_via']:8s} out via {span['left_via']}"
            f" {span['left_direction']}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Category 3 Test #2 - musical shell escape")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--set", action="append", help="config override, name=value")
        p.add_argument("--workers", type=int, default=None)
        p.add_argument("--out", default=None)

    batch = sub.add_parser("batch", help="simulate a population and report distributions")
    batch.add_argument("--seeds", default="10000", help="count, or start:stop")
    batch.add_argument("--records", default=None, help="also write the per-seed records")
    common(batch)
    batch.set_defaults(func=cmd_batch)

    sweep = sub.add_parser("sweep", help="one axis, several values, same seeds")
    sweep.add_argument("--axis", required=True)
    sweep.add_argument("--values", required=True, help="semicolon-separated")
    sweep.add_argument("--seeds", default="2000")
    common(sweep)
    sweep.set_defaults(func=cmd_sweep)

    short = sub.add_parser("shortlist", help="pick a varied set of strong seeds")
    short.add_argument("--seeds", default="20000")
    short.add_argument("--take", type=int, default=16)
    common(short)
    short.set_defaults(func=cmd_shortlist)

    document = sub.add_parser("document", help="write the canonical playback document")
    document.add_argument("--seed", type=int, required=True)
    common(document)
    document.set_defaults(func=cmd_document)

    verify = sub.add_parser("verify", help="re-simulate a document and compare")
    verify.add_argument("--path", required=True)
    verify.set_defaults(func=cmd_verify)

    describe = sub.add_parser("describe", help="one run, in words")
    describe.add_argument("--seed", type=int, required=True)
    common(describe)
    describe.set_defaults(func=cmd_describe)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())

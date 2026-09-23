"""Command line for MULTIPLYING SHELL ESCAPE: batches, sweeps, shortlists, documents.

    python -m satisfying.multishell_cli batch --count 10000 --out batch.json
    python -m satisfying.multishell_cli batch --count 10000 --keep-records --out full.json
    python -m satisfying.multishell_cli sweep --axis speed --values 9,10,11
    python -m satisfying.multishell_cli shortlist --from full.json --take 16
    python -m satisfying.multishell_cli describe --seed 7
    python -m satisfying.multishell_cli profile
    python -m satisfying.multishell_cli document --seed 7 --out run.json
    python -m satisfying.multishell_cli verify --document run.json

A batch record is a compact projection of a `RunEvaluation`, not the whole
thing: ten thousand full evaluations is a hundred megabytes of nested
dictionaries and almost all of it is per-shell detail that the distributions
already summarise. `_compact` names exactly what survives and `_rehydrate`
rebuilds enough of an evaluation for `summarise` to run on it, so a saved batch
can be re-summarised and re-shortlisted without re-simulating.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Iterable, Sequence

from concurrent.futures import ProcessPoolExecutor

from satisfying.multishell import (
    DEFAULT_CONFIG,
    MultishellConfig,
    difficulty_profile,
    simulate,
)
from satisfying.multishell_evaluator import (
    DEFAULT_THRESHOLDS,
    EvaluationThresholds,
    RunEvaluation,
    evaluate,
    summarise,
)
from satisfying.multishell_playback import (
    document_for,
    read_playback,
    verify_document,
    write_playback,
)

__all__ = ["run_batch", "shortlist", "build_parser", "main"]


# --------------------------------------------------------------------------
# Batch
# --------------------------------------------------------------------------

COMPACT_PATHS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("escaped", ("outcome", "escaped")),
    ("duration", ("outcome", "duration")),
    ("failure_reason", ("outcome", "failure_reason")),
    ("escape_route", ("outcome", "escape_route")),
    ("escape_generation", ("outcome", "escape_generation")),
    ("frontier_region", ("outcome", "frontier_region")),
    ("frontier_balls", ("outcome", "frontier_balls")),
    ("shell_count", ("outcome", "shell_count")),
    ("population_total", ("population", "total")),
    ("population_max", ("population", "max")),
    ("population_early", ("population", "early")),
    ("generations", ("population", "generations")),
    ("suppressed", ("population", "suppressed")),
    ("spawns", ("reproduction", "spawns")),
    ("first_spawn", ("reproduction", "first_spawn")),
    ("violations", ("reproduction", "violations")),
    ("collisions", ("collisions", "total")),
    ("collision_rate", ("collisions", "per_second")),
    ("peak_collision_rate", ("collisions", "peak_window")),
    ("grazing", ("collisions", "grazing")),
    ("ball_ball", ("collisions", "ball_ball")),
    ("near_misses", ("near_misses", "total")),
    ("damage_events", ("damage", "events")),
    ("damage_scoring", ("damage", "scoring_events")),
    ("transitions", ("damage", "transitions")),
    ("breaks", ("damage", "breaks")),
    ("shared_breaks", ("damage", "shared_breaks")),
    ("mean_break_cumulative", ("damage", "mean_break_cumulative")),
    ("progression_opening", ("routes", "progression_opening")),
    ("progression_break", ("routes", "progression_break")),
    ("meaningful_total", ("activity", "meaningful_total")),
    ("meaningful_rate", ("activity", "meaningful_per_second")),
    ("meaningful_peak", ("activity", "meaningful_peak_window")),
    ("stagnation", ("stagnation", "longest_no_event")),
    ("longest_cycle_run", ("repetition", "longest_cycle_run")),
    ("longest_cycle_period", ("repetition", "longest_cycle_period")),
    ("distinct_panels", ("repetition", "distinct_panels")),
    ("trajectory_spread", ("repetition", "trajectory_spread")),
    ("difficulty_increasing", ("difficulty", "increasing")),
    ("max_penetration", ("instruments", "max_penetration")),
    ("min_spawn_clearance", ("instruments", "min_spawn_clearance")),
    ("speed_min", ("instruments", "speed_min")),
    ("speed_max", ("instruments", "speed_max")),
    ("max_speed_correction", ("instruments", "max_speed_correction")),
    ("mean_speed_correction", ("instruments", "mean_speed_correction")),
    ("anomalous_crossings", ("instruments", "anomalous_crossings")),
    ("newton_failures", ("instruments", "newton_failures")),
    ("reproduction_violations", ("instruments", "reproduction_violations")),
    ("digest", ("digest",)),
)

COMPACT_LISTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("curve", ("population", "curve")),
    ("thirds_population", ("population", "thirds")),
    ("by_region", ("population", "by_region")),
    ("spawns_by_shell", ("reproduction", "by_shell")),
    ("reached", ("progression", "reached")),
    ("crossed", ("progression", "crossed")),
    ("crossings", ("progression", "crossings")),
    ("regressions", ("progression", "regressions")),
    ("dwell", ("progression", "dwell")),
    ("pass_rate", ("difficulty", "pass_rate")),
    ("blocked", ("difficulty", "blocked_contacts")),
    ("damage_absorbed", ("difficulty", "damage_absorbed")),
    ("collisions_per_shell", ("collisions", "per_shell")),
    ("breaks_per_shell", ("damage", "breaks_per_shell")),
    ("collision_thirds", ("activity", "collision_thirds")),
    ("spawn_thirds", ("activity", "spawn_thirds")),
    ("break_thirds", ("activity", "break_thirds")),
    ("meaningful_thirds", ("activity", "meaningful_thirds")),
)

ESCALATION_KEYS = ("collisions", "spawns", "breaks", "meaningful", "population")


def _compact(evaluation: RunEvaluation) -> dict[str, Any]:
    out: dict[str, Any] = {"seed": evaluation.seed, "flags": list(evaluation.flags)}
    for name, path in COMPACT_PATHS + COMPACT_LISTS:
        value: Any = evaluation.metrics
        for key in path:
            value = value[key]
        out[name] = list(value) if isinstance(value, (list, tuple)) else value
    out["escalation"] = {k: evaluation.metrics["escalation"][k] for k in ESCALATION_KEYS}
    return out


def _rehydrate(records: Sequence[dict[str, Any]]) -> list[RunEvaluation]:
    """Rebuild just enough of a `RunEvaluation` for `summarise` to work."""
    out: list[RunEvaluation] = []
    for record in records:
        metrics: dict[str, Any] = {}
        for name, path in COMPACT_PATHS + COMPACT_LISTS:
            node = metrics
            for key in path[:-1]:
                node = node.setdefault(key, {})
            node[path[-1]] = record[name]
        metrics["escalation"] = record["escalation"]
        metrics["population"]["curve_times"] = []
        metrics["population"]["capped"] = bool(record["suppressed"])
        metrics["progression"]["first_cross"] = [None] * record["shell_count"]
        metrics["difficulty"]["contacts_per_crossing"] = []
        metrics["difficulty"]["engaged_shells"] = []
        metrics["outcome"]["escape_time"] = record["duration"] if record["escaped"] else None
        metrics["outcome"]["escape_ball"] = None
        metrics["outcome"]["escape_lineage"] = []
        metrics["damage"]["transitions_by_state"] = {}
        metrics["routes"]["per_shell"] = []
        metrics["near_misses"] = {"total": record["near_misses"]}
        out.append(RunEvaluation(seed=record["seed"], metrics=metrics, flags=list(record["flags"])))
    return out


def _worker(item: tuple[int, dict[str, Any], dict[str, Any]]) -> dict[str, Any]:
    seed, config_dict, threshold_dict = item
    config = MultishellConfig.from_dict(config_dict)
    thresholds = EvaluationThresholds(**threshold_dict)
    return _compact(evaluate(simulate(seed, config), thresholds))


def run_batch(
    seeds: Iterable[int],
    config: MultishellConfig = DEFAULT_CONFIG,
    thresholds: EvaluationThresholds = DEFAULT_THRESHOLDS,
    workers: int | None = None,
    chunk: int = 32,
) -> list[dict[str, Any]]:
    """Simulate and evaluate a whole population."""
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

    A ranked list hands the visual and audio branches sixteen versions of the
    same run, because whatever is ranked first is what the top of the list is
    made of. The brief asks for variety along named axes, so the buckets are
    those axes: two runtime bands crossed with the things the redesign is
    actually about - how big the population got, whether the final escape came
    through an opening or through a panel the balls had broken, and whether the
    escaping ball was the original or a descendant. Each bucket is filled with
    its own best, and no seed appears twice.
    """
    clean = [
        r
        for r in records
        if not r["flags"]
        and thresholds.acceptable_low <= r["duration"] <= thresholds.acceptable_high
    ]

    def band(record: dict[str, Any]) -> str:
        d = record["duration"]
        return "preferred" if thresholds.preferred_low <= d <= thresholds.preferred_high else "wide"

    def size(record: dict[str, Any]) -> str:
        return "big" if record["population_max"] >= 12 else "moderate"

    def route(record: dict[str, Any]) -> str:
        return "break" if record["escape_route"] == "break" else "opening"

    def heir(record: dict[str, Any]) -> str:
        return "descendant" if (record["escape_generation"] or 0) > 0 else "founder"

    def interest(record: dict[str, Any]) -> tuple:
        # Ordered by what a later branch would want more of, most important
        # first: real escalation, then a busy climax, then a mixed route, then
        # shared damage, then near misses.
        both = 1 if (record["progression_opening"] > 0 and record["progression_break"] > 0) else 0
        return (
            round(record["escalation"]["meaningful"], 3),
            record["thirds_population"][2],
            both,
            record["shared_breaks"],
            record["near_misses"],
            -(record["first_spawn"] or 99.0),
            -record["peak_collision_rate"],
        )

    buckets: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for record in clean:
        buckets.setdefault((band(record), size(record), route(record), heir(record)), []).append(record)
    for rows in buckets.values():
        rows.sort(key=interest, reverse=True)

    picked: list[dict[str, Any]] = []
    used: set[int] = set()

    def fill(keys: Sequence[tuple[str, str, str, str]], limit: int) -> None:
        """Round-robin over `keys` until `limit` is reached or they run dry.

        Round-robin rather than concatenation, so a crowded bucket cannot take
        the whole list and squeeze out the one break-route descendant run in
        the batch.
        """
        depth = 0
        while len(picked) < limit:
            added = False
            for key in keys:
                rows = buckets.get(key, ())
                if depth < len(rows) and rows[depth]["seed"] not in used:
                    picked.append(rows[depth])
                    used.add(rows[depth]["seed"])
                    added = True
                    if len(picked) >= limit:
                        break
            if not added:
                return
            depth += 1

    # The band is not an equal dimension with the other three. The brief asks
    # for "approximately 20-24 s runtimes", so two thirds of the list is filled
    # from the preferred band before the wider 18-20 and 24-26 runs get a turn -
    # and they do get a turn, because a branch choosing a final seed should see
    # what the edges of the acceptable band look like too.
    ordered = sorted(buckets)
    preferred_keys = [k for k in ordered if k[0] == "preferred"]
    fill(preferred_keys, -(-2 * take // 3))
    fill(preferred_keys + [k for k in ordered if k[0] != "preferred"], take)
    picked.sort(key=lambda r: r["duration"])
    return picked


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


def _config_from_args(args: argparse.Namespace) -> MultishellConfig:
    config = DEFAULT_CONFIG
    if getattr(args, "config", None):
        with open(args.config, encoding="utf-8") as handle:
            config = MultishellConfig.from_dict(json.load(handle))
    for name in ("speed", "horizon", "max_population", "spawn_turn"):
        value = getattr(args, name, None)
        if value is not None:
            config = config.replace(**{name: value})
    return config


def _emit(payload: Any, path: str | None) -> None:
    text = json.dumps(payload, indent=2, default=str)
    if path:
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
        print(f"wrote {path}")
    else:
        print(text)


def cmd_batch(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    seeds = range(args.start, args.start + args.count)
    records = run_batch(seeds, config, DEFAULT_THRESHOLDS, workers=args.workers)
    payload = {
        "config": config.as_dict(),
        "config_digest": config.digest(),
        "difficulty": difficulty_profile(config),
        "seed_start": args.start,
        "seed_count": args.count,
        "summary": summarise(_rehydrate(records)),
        "record_count": len(records),
        "records": records if args.keep_records else [],
    }
    if args.out:
        _emit(payload, args.out)
        print(json.dumps(payload["summary"], indent=2, default=str))
    else:
        _emit({k: v for k, v in payload.items() if k != "records"}, None)
    return 0


def _parse_sweep_value(text: str) -> Any:
    """One value on a sweep axis: a scalar, or a per-shell tuple written `a:b:c`.

    The axes the brief asks to search are not all scalars - the difficulty
    profile, the opening widths and the break thresholds are one number per
    shell - so a sweep that could only vary a float would have to be a
    hand-written script, and a hand-written script is not a thing the batch
    file can be reproduced from later.
    """
    if ":" in text:
        return tuple(_parse_sweep_value(part) for part in text.split(":"))
    if "." in text or "e" in text.lower():
        return float(text)
    return int(text)


def cmd_sweep(args: argparse.Namespace) -> int:
    base = _config_from_args(args)
    values = [_parse_sweep_value(v) for v in args.values.split(",")]
    seeds = list(range(args.start, args.start + args.count))
    rows = []
    for value in values:
        config = base.replace(**{args.axis: value})
        records = run_batch(seeds, config, DEFAULT_THRESHOLDS, workers=args.workers)
        rows.append(
            {
                "value": value,
                "config_digest": config.digest(),
                "difficulty": difficulty_profile(config),
                "summary": summarise(_rehydrate(records)),
            }
        )
    _emit({"axis": args.axis, "seeds": args.count, "rows": rows}, args.out)
    return 0


def cmd_shortlist(args: argparse.Namespace) -> int:
    with open(getattr(args, "from"), encoding="utf-8") as handle:
        payload = json.load(handle)
    records = payload["records"]
    if not records:
        print("batch file has no records; re-run batch with --keep-records", file=sys.stderr)
        return 2
    picked = shortlist(records, take=args.take)
    _emit(
        {
            "config_digest": payload.get("config_digest"),
            "taken": len(picked),
            "seeds": [r["seed"] for r in picked],
            "candidates": picked,
        },
        args.out,
    )
    return 0


def cmd_profile(args: argparse.Namespace) -> int:
    _emit(difficulty_profile(_config_from_args(args)), args.out)
    return 0


def cmd_document(args: argparse.Namespace) -> int:
    document = document_for(args.seed, _config_from_args(args))
    if args.out:
        write_playback(document, args.out)
        print(f"wrote {args.out} digest={document['digest']}")
    else:
        print(json.dumps(document, indent=2, default=str))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    report = verify_document(read_playback(args.document))
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


def cmd_describe(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    run = simulate(args.seed, config)
    evaluation = evaluate(run)
    m = evaluation.metrics
    print(f"seed {run.seed}  digest {run.state_digest()[:16]}")
    print(
        f"  outcome      {'ESCAPED' if run.escaped else 'FAILED ' + str(run.failure_reason)} "
        f"at {run.duration:.3f}s by ball {run.escape_ball} "
        f"(generation {m['outcome']['escape_generation']}, route {m['outcome']['escape_route']})"
    )
    print(f"  lineage      {m['outcome']['escape_lineage']}")
    print(
        f"  population   {m['population']['total']} balls, {m['population']['generations']} generations, "
        f"curve {m['population']['curve']}"
    )
    print(f"  spawns       {m['reproduction']['spawns']} by shell {m['reproduction']['by_shell']}")
    print(f"  reached      {m['progression']['reached']}")
    print(f"  crossed      {m['progression']['crossed']}")
    print(f"  pass rate    {[round(v, 3) for v in m['difficulty']['pass_rate']]}")
    print(f"  dwell        {[round(v, 2) for v in m['progression']['dwell']]}")
    print(
        f"  collisions   {m['collisions']['total']} "
        f"({m['collisions']['per_second']:.2f}/s, peak {m['collisions']['peak_window']:.1f}/s) "
        f"per shell {m['collisions']['per_shell']}"
    )
    print(
        f"  damage       {m['damage']['breaks']} breaks ({m['damage']['shared_breaks']} shared), "
        f"{m['damage']['transitions']} state transitions, per shell {m['damage']['breaks_per_shell']}"
    )
    print(
        f"  routes       {m['routes']['progression_opening']} opening / "
        f"{m['routes']['progression_break']} break"
    )
    print(
        f"  activity     meaningful thirds {m['activity']['meaningful_thirds']}, "
        f"escalation {m['escalation']['meaningful']:.2f}"
    )
    print(
        f"  instruments  penetration {m['instruments']['max_penetration']:.2e}, "
        f"spawn clearance {m['instruments']['min_spawn_clearance']}, "
        f"speed correction mean {m['instruments']['mean_speed_correction']:.4f} "
        f"max {m['instruments']['max_speed_correction']:.3f}, "
        f"anomalies {m['instruments']['anomalous_crossings']}, "
        f"newton {m['instruments']['newton_failures']}, "
        f"violations {m['instruments']['reproduction_violations']}"
    )
    print(f"  flags        {evaluation.flags or 'none'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Category 3 Test #2 - multiplying shell escape")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--config", help="JSON config file overriding the default")
        p.add_argument("--speed", type=float)
        p.add_argument("--horizon", type=float)
        p.add_argument("--max-population", dest="max_population", type=int)
        p.add_argument("--spawn-turn", dest="spawn_turn", type=float)
        p.add_argument("--out", help="write JSON here instead of stdout")

    batch = sub.add_parser("batch", help="simulate a population and report distributions")
    common(batch)
    batch.add_argument("--count", type=int, default=2000)
    batch.add_argument("--start", type=int, default=0)
    batch.add_argument("--workers", type=int)
    # Off by default because 20,000 compact records is 71 MB and a repository
    # is not where that belongs. The summary is what gets committed; the
    # records go to a scratch path and feed `shortlist`, and the run is
    # reproducible from the config digest and the seed range either way.
    batch.add_argument(
        "--keep-records",
        action="store_true",
        default=False,
        help="also write the per-seed records (large; needed by `shortlist`)",
    )
    batch.set_defaults(func=cmd_batch)

    sweep = sub.add_parser("sweep", help="one axis, several values, the same seeds")
    common(sweep)
    sweep.add_argument("--axis", required=True)
    sweep.add_argument(
        "--values",
        required=True,
        help="comma separated; a per-shell tuple is written 1.6:2.4:3.6:5.2:7.2",
    )
    sweep.add_argument("--count", type=int, default=600)
    sweep.add_argument("--start", type=int, default=0)
    sweep.add_argument("--workers", type=int)
    sweep.set_defaults(func=cmd_sweep)

    short = sub.add_parser("shortlist", help="pick a varied set of strong seeds")
    short.add_argument("--from", required=True, dest="from")
    short.add_argument("--take", type=int, default=16)
    short.add_argument("--out")
    short.set_defaults(func=cmd_shortlist)

    profile = sub.add_parser("profile", help="print the per-shell difficulty table")
    common(profile)
    profile.set_defaults(func=cmd_profile)

    document = sub.add_parser("document", help="write the canonical playback document")
    common(document)
    document.add_argument("--seed", type=int, required=True)
    document.set_defaults(func=cmd_document)

    verify = sub.add_parser("verify", help="re-simulate a document and compare")
    verify.add_argument("--document", required=True)
    verify.set_defaults(func=cmd_verify)

    describe = sub.add_parser("describe", help="one run, in words")
    common(describe)
    describe.add_argument("--seed", type=int, required=True)
    describe.set_defaults(func=cmd_describe)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

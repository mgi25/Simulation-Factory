"""Build a production batch: evaluate a seed range, curate it, write a manifest.

The last step before rendering. It runs a large range of seeds headlessly,
scores them, picks a small diverse batch from the good ones, and writes a
manifest naming exactly which battles were chosen and why. Optionally it also
exports each chosen battle's replay and checks that the replay really is the
battle that was selected.

Typical use::

    python tools/build_batch.py --start 20000 --seeds 10000 --size 20
    python tools/build_batch.py --seeds 10000 --size 10 --export-replays
    python tools/build_batch.py --seeds 10000 --compare

Everything it writes goes under output/, which is not tracked: a manifest is
a production artefact, not source.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.arena_layout import LAYOUT_PROCEDURAL, LAYOUT_TYPES  # noqa: E402
from evaluation.candidate import Candidate  # noqa: E402
from evaluation.candidate_curation import (  # noqa: E402
    DEFAULT_MAX_SPEED,
    DEFAULT_MIN_DURATION,
    DEFAULT_MIN_SCORE,
    REJECT_REASONS,
    CurationConfig,
    CurationResult,
    count_near_duplicates,
    curate,
    matchup_key,
    motion_class,
    summarise,
)
from replay.exporter import record_battle, write_replay  # noqa: E402
from tools.candidate_search import search  # noqa: E402

# The manifest's own schema version. Nothing to do with the replay format:
# a replay describes one battle, a manifest describes a decision about many.
MANIFEST_VERSION = 1

DEFAULT_OUTPUT_ROOT = "output"
REPLAY_SUBDIR = "replays"

# What a freshly built batch says about human review. This phase only writes
# the field; approving things is somebody else's job, later.
REVIEW_PENDING = "pending"


class VerificationError(RuntimeError):
    """An exported replay is not the battle that was selected."""


def replay_facts(replay: dict) -> dict:
    """The few facts that say which battle a replay actually is.

    Shared with production, which asks the same question from the other
    direction: verification here compares a fresh replay against what
    curation chose, and production compares a replay on disk against what
    the manifest recorded. One definition of the comparison, so the two can
    never drift apart.
    """
    return {
        "powers": [fighter["power"] for fighter in replay["fighters"]],
        "winner_id": replay["result"]["winner_id"],
        "duration": round(replay["result"]["duration"], 3),
        "layout_id": replay["layout"]["id"],
    }


def manifest_facts(entry: dict) -> dict:
    """The same facts, as a manifest item records them."""
    return {
        "powers": list(entry.get("powers") or ()),
        "winner_id": entry.get("winner_id"),
        "duration": round(float(entry.get("duration", 0.0)), 3),
        "layout_id": entry.get("layout_id", ""),
    }


def batch_id_for(start: int, count: int, arena: str, explicit: str | None) -> str:
    """A stable name for a batch. Never a timestamp, never a random id.

    Two runs of the same command have to produce the same batch, including
    what it is called, or the manifest stops being reproducible.
    """
    if explicit:
        return explicit
    return f"{arena}_{start}_{start + count - 1}"


def _item(index: int, candidate: Candidate, batch_dir: str | None) -> dict:
    """One manifest entry: enough to re-render it, and to argue with it."""
    metrics, score = candidate.metrics, candidate.score
    entry = {
        "index": index,
        "seed": metrics.seed,
        "arena_mode": metrics.arena_mode,
        "layout_id": metrics.layout_id,
        "label": " vs ".join(power.upper() for power in metrics.powers),
        "powers": list(metrics.powers),
        "matchup": list(matchup_key(metrics.powers)),
        "winner_id": metrics.winner_id,
        "duration": round(metrics.duration, 3),
        "score": round(score.total, 3),
        "components": {
            "pacing": round(score.pacing, 3),
            "suspense": round(score.suspense, 3),
            "action": round(score.action, 3),
            "variety": round(score.variety, 3),
            "arena": round(score.arena, 3),
            "payoff": round(score.payoff, 3),
            "penalty": round(score.penalty, 3),
        },
        "environment": {
            "obstacles": metrics.obstacles,
            "kinetic_obstacles": metrics.kinetic_obstacles,
            "motion_class": motion_class(metrics.kinetic_obstacles),
            "shape": {kind: count for kind, count in metrics.layout_shape},
        },
        "metrics": {
            "damaging_hits": metrics.damaging_hits,
            "hit_mechanisms": metrics.hit_subtypes,
            "power_activations": metrics.power_activations,
            "lead_changes": metrics.lead_changes,
            "close_fraction": round(metrics.close_fraction, 4),
            "winner_comeback": round(metrics.winner_comeback, 3),
            "final_health_gap": round(metrics.final_health_gap, 3),
            "max_fighter_speed": round(metrics.max_fighter_speed, 3),
            "obstacle_contacts": metrics.obstacle_contacts,
        },
        "review_status": REVIEW_PENDING,
    }
    if batch_dir is not None:
        # Relative to the manifest, so a batch can be moved or copied to
        # another machine without rewriting anything inside it.
        entry["replay_path"] = f"{REPLAY_SUBDIR}/{index:03d}_seed_{metrics.seed}.json"
    return entry


def build_manifest(
    result: CurationResult,
    config: CurationConfig,
    start: int,
    count: int,
    arena: str,
    batch_id: str,
    with_replays: bool,
) -> dict:
    return {
        "version": MANIFEST_VERSION,
        "batch_id": batch_id,
        "source": {"start_seed": start, "seed_count": count, "arena": arena},
        "curation": {
            "size": config.size,
            "min_score": config.min_score,
            "min_duration": config.min_duration,
            "max_speed": config.max_speed,
            "matchup_cap": config.matchup_cap,
            "power_cap": config.power_cap,
            "mirror_cap": config.mirror_cap,
            "motion_cap": config.motion_cap,
            "similarity_threshold": config.similarity_threshold,
        },
        "summary": summarise(result.selected),
        "rejected": {name: result.rejected.get(name, 0) for name in REJECT_REASONS},
        "shortfall_reason": result.reason_for_shortfall(config.size),
        "items": [
            _item(index, candidate, "with" if with_replays else None)
            for index, candidate in enumerate(result.selected, start=1)
        ],
    }


def verify_and_export(
    manifest: dict, result: CurationResult, batch_dir: str, write_files: bool
) -> None:
    """Re-run each selected battle and confirm it is the one that was chosen.

    Selection ran the simulation once and kept only numbers. Rendering will
    run it again through a different entry point. If those two ever disagree
    the batch is describing battles that will not actually happen, so this
    checks rather than assumes - and fails loudly, because a wrong production
    batch is worse than no batch.
    """
    for entry, candidate in zip(manifest["items"], result.selected):
        metrics = candidate.metrics
        replay = record_battle(metrics.seed, arena_mode=metrics.arena_mode)

        actual = replay_facts(replay)
        expected = {
            "powers": list(metrics.powers),
            "winner_id": metrics.winner_id,
            "duration": round(metrics.duration, 3),
            "layout_id": metrics.layout_id,
        }
        if actual != expected:
            raise VerificationError(
                f"seed {metrics.seed}: the exported replay is not the battle"
                f" that was selected.\n  selected {expected}\n  replay   {actual}"
            )

        if write_files:
            write_replay(replay, os.path.join(batch_dir, entry["replay_path"]))


def report(result: CurationResult, config: CurationConfig, evaluated: int) -> None:
    print(f"\ncandidates evaluated      {evaluated}")
    print(f"cleared the quality floor {result.above_floor}")
    print(f"selected                  {result.size} of {config.size}")
    print("rejected by")
    for name in REJECT_REASONS:
        count = result.rejected.get(name, 0)
        if count:
            print(f"  {name:<24}{count:>8}")

    shortfall = result.reason_for_shortfall(config.size)
    if shortfall:
        print(f"\nSHORT BATCH: {shortfall}")

    if not result.selected:
        return
    print(
        f"\n{'#':>3} {'seed':>7} {'score':>6} {'matchup':<15} {'dur':>6}"
        f" {'win':>4} {'arena':<26} {'motion':<12} {'lead':>4} {'hits':>4}"
    )
    print("-" * 96)
    for index, candidate in enumerate(result.selected, start=1):
        m = candidate.metrics
        shape = "+".join(f"{count}{kind[0]}" for kind, count in m.layout_shape)
        print(
            f"{index:>3} {m.seed:>7} {candidate.score.total:>6.1f}"
            f" {'/'.join(m.powers):<15} {m.duration:>5.1f}s {str(m.winner_id):>4}"
            f" {shape:<26} {motion_class(m.kinetic_obstacles):<12}"
            f" {m.lead_changes:>4} {m.damaging_hits:>4}"
        )

    print("\nbatch summary")
    for key, value in summarise(result.selected).items():
        print(f"  {key:<18}{value}")


def report_comparison(pool: list[Candidate], result: CurationResult, size: int) -> None:
    """What curating cost, and what it bought.

    The honest comparison: the same pool, taken two ways. Some score is
    always given up - the raw top N is by definition the highest-scoring N -
    and the question is whether the variety gained was worth it.
    """
    raw = pool[:size]
    curated = result.selected
    if not raw or not curated:
        return

    raw_summary, curated_summary = summarise(raw), summarise(curated)
    print(f"\n=== raw top {len(raw)} against curated {len(curated)} ===")
    print(f"{'':<26}{'raw':>12}{'curated':>12}")
    rows = [
        ("mean score", raw_summary["score"]["mean"], curated_summary["score"]["mean"]),
        ("minimum score", raw_summary["score"]["min"], curated_summary["score"]["min"]),
        ("unique matchups", raw_summary["unique_matchups"], curated_summary["unique_matchups"]),
        ("mirrors", raw_summary["mirrors"], curated_summary["mirrors"]),
        ("near-duplicate pairs", count_near_duplicates(raw), count_near_duplicates(curated)),
        ("timeouts", raw_summary["timeouts"], curated_summary["timeouts"]),
    ]
    for label, left, right in rows:
        print(f"  {label:<24}{left:>12}{right:>12}")

    print(f"  {'mean score cost':<24}"
          f"{'':>12}{raw_summary['score']['mean'] - curated_summary['score']['mean']:>12.2f}")

    print("\n  power appearances")
    powers = sorted(set(raw_summary["powers"]) | set(curated_summary["powers"]))
    for power in powers:
        print(f"    {power:<22}{raw_summary['powers'].get(power, 0):>12}"
              f"{curated_summary['powers'].get(power, 0):>12}")
    print("  arena motion")
    for name, value in raw_summary["motion"].items():
        print(f"    {name:<22}{value:>12}{curated_summary['motion'][name]:>12}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="build a production batch")
    parser.add_argument("--seeds", type=int, default=10000, help="how many seeds to run")
    parser.add_argument("--start", type=int, default=20000, help="first seed")
    parser.add_argument("--arena", choices=LAYOUT_TYPES, default=LAYOUT_PROCEDURAL)
    parser.add_argument("--size", type=int, default=20, help="battles wanted")
    parser.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE)
    parser.add_argument("--min-duration", type=float, default=DEFAULT_MIN_DURATION)
    parser.add_argument("--max-speed", type=float, default=DEFAULT_MAX_SPEED)
    parser.add_argument("--matchup-share", type=float, default=None)
    parser.add_argument("--power-share", type=float, default=None)
    parser.add_argument("--mirror-share", type=float, default=None)
    parser.add_argument("--motion-share", type=float, default=None)
    parser.add_argument("--similarity", type=int, default=None,
                        help="signals that must agree before two battles are duplicates")
    parser.add_argument("--batch-id", default=None, help="stable name for this batch")
    parser.add_argument("--output-root", default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--export-replays", action="store_true")
    parser.add_argument("--compare", action="store_true",
                        help="report the raw top N alongside the curated batch")
    parser.add_argument(
        "--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1)
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    defaults = CurationConfig()
    config = CurationConfig(
        size=args.size,
        min_score=args.min_score,
        min_duration=args.min_duration,
        max_speed=args.max_speed,
        matchup_share=args.matchup_share or defaults.matchup_share,
        power_share=args.power_share or defaults.power_share,
        mirror_share=args.mirror_share or defaults.mirror_share,
        motion_share=args.motion_share or defaults.motion_share,
        similarity_threshold=args.similarity or defaults.similarity_threshold,
    )

    seeds = range(args.start, args.start + args.seeds)
    jobs = [(seed, args.arena) for seed in seeds]

    started = time.perf_counter()
    pool = search(jobs, args.jobs)
    evaluated_at = time.perf_counter()
    result = curate(pool, config)
    curated_at = time.perf_counter()

    batch_id = batch_id_for(args.start, args.seeds, args.arena, args.batch_id)
    batch_dir = os.path.join(args.output_root, f"batch_{batch_id}")
    manifest = build_manifest(
        result, config, args.start, args.seeds, args.arena, batch_id,
        with_replays=args.export_replays,
    )

    print(
        f"evaluated {len(pool)} {args.arena} battles,"
        f" seeds {seeds.start}-{seeds.stop - 1}"
        f"  (evaluation {evaluated_at - started:.1f}s,"
        f" curation {curated_at - evaluated_at:.3f}s,"
        f" total {curated_at - started:.1f}s, {args.jobs} workers)"
    )
    report(result, config, len(pool))
    if args.compare:
        report_comparison(pool, result, config.size)

    verify_and_export(manifest, result, batch_dir, write_files=args.export_replays)
    print(f"\nverified {len(result.selected)} selected battles reproduce exactly")

    os.makedirs(batch_dir, exist_ok=True)
    manifest_path = os.path.join(batch_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
    print(f"manifest -> {manifest_path}")
    if args.export_replays:
        print(f"replays  -> {os.path.join(batch_dir, REPLAY_SUBDIR)}")


if __name__ == "__main__":
    main()

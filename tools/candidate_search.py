"""Headless candidate search: run seeded battles and rank them by interest.

A developer tool, not part of the simulation. It is how a range of seeds
becomes a shortlist worth looking at, so that choosing what to render is a
decision about thousands of battles rather than the handful somebody
happened to watch.

Typical use::

    python tools/candidate_search.py --seeds 5000 --top 20
    python tools/candidate_search.py --start 10000 --seeds 5000 --stats
    python tools/candidate_search.py --seeds 5000 --audit
    python tools/candidate_search.py --explain 4471

Nothing is written unless `--json` is given, and a shortlist file is a
working note, not something to keep.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from collections import Counter
from dataclasses import dataclass
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.arena_layout import LAYOUT_CLASSIC, LAYOUT_PROCEDURAL, LAYOUT_TYPES  # noqa: E402
from evaluation.battle_metrics import BattleMetrics, evaluate_seed  # noqa: E402
from evaluation.battle_score import ScoreBreakdown, score_battle  # noqa: E402

# The share of a range treated as its best when comparing the top against
# everything else.
TOP_DECILE = 0.10
# How many candidates the diversity audit looks at.
AUDIT_SIZE = 100


@dataclass(frozen=True)
class Candidate:
    """One evaluated battle: its metrics and what they scored."""

    metrics: BattleMetrics
    score: ScoreBreakdown

    @property
    def rank_key(self) -> tuple[float, int]:
        """Best first, and ties broken by seed so ordering is total."""
        return (-self.score.total, self.metrics.seed)


def evaluate(job: tuple[int, str]) -> Candidate:
    seed, arena_mode = job
    metrics = evaluate_seed(seed, arena_mode=arena_mode)
    return Candidate(metrics=metrics, score=score_battle(metrics))


def search(jobs: list[tuple[int, str]], workers: int) -> list[Candidate]:
    """Evaluate every job and return the candidates in ranked order.

    The ranking is produced here rather than by the workers, and the sort key
    is total, so the result cannot depend on how the work was divided up.
    """
    if workers <= 1:
        found = [evaluate(job) for job in jobs]
    else:
        chunk = max(1, len(jobs) // (workers * 8))
        with ProcessPoolExecutor(max_workers=workers) as pool:
            found = list(pool.map(evaluate, jobs, chunksize=chunk))
    return sorted(found, key=lambda candidate: candidate.rank_key)


# --- reporting --------------------------------------------------------------


def _motion(metrics: BattleMetrics) -> str:
    if metrics.obstacles == 0:
        return "empty"
    still = metrics.obstacles - metrics.kinetic_obstacles
    return f"{still}s+{metrics.kinetic_obstacles}k"


def _outcome(metrics: BattleMetrics) -> str:
    if metrics.is_draw:
        return "draw"
    if metrics.is_timeout:
        return f"time:{metrics.winner_id}"
    return f"KO:{metrics.winner_id}"


def report_table(candidates: list[Candidate], limit: int) -> None:
    print(
        f"\n{'#':>3} {'seed':>7} {'score':>6} {'matchup':<15} {'outcome':>7}"
        f" {'dur':>6} {'layout':<18} {'obst':>6} {'lead':>4} {'hits':>4}"
        f" {'cmbk':>5} {'close':>6}"
    )
    print("-" * 104)
    for rank, candidate in enumerate(candidates[:limit], start=1):
        m = candidate.metrics
        print(
            f"{rank:>3} {m.seed:>7} {candidate.score.total:>6.1f}"
            f" {'/'.join(m.powers):<15} {_outcome(m):>7}"
            f" {m.duration:>5.1f}s {m.layout_id:<18} {_motion(m):>6}"
            f" {m.lead_changes:>4} {m.damaging_hits:>4}"
            f" {m.winner_comeback:>5.0f} {m.close_fraction:>5.0%}"
        )


def report_distribution(candidates: list[Candidate]) -> None:
    scores = sorted(candidate.score.total for candidate in candidates)
    print(f"\n=== score distribution, {len(scores)} candidates ===")
    print(f"minimum   {scores[0]:6.1f}")
    for label, q in (("p10", 0.10), ("median", 0.50), ("p90", 0.90),
                     ("p95", 0.95), ("p99", 0.99)):
        print(f"{label:<9} {scores[_index(scores, q)]:6.1f}")
    print(f"maximum   {scores[-1]:6.1f}")
    print(f"mean      {statistics.mean(scores):6.1f}")

    print("\ncomponent means (of their maximum)")
    for name in ("pacing", "suspense", "action", "variety", "arena", "payoff"):
        values = [getattr(c.score, name) for c in candidates]
        print(f"  {name:<10} {statistics.mean(values):5.2f}"
              f"   spread {min(values):5.2f} - {max(values):5.2f}")
    penalised = [c for c in candidates if c.score.penalty > 0.0]
    print(f"\npenalised {len(penalised)} ({_percent(len(penalised), len(candidates))})")
    reasons: Counter[str] = Counter()
    for candidate in penalised:
        for name, _ in candidate.score.penalties:
            reasons[name] += 1
    for name, count in reasons.most_common():
        print(f"  {name:<18} {count:>6} ({_percent(count, len(candidates))})")


def report_audit(candidates: list[Candidate]) -> None:
    """Is the score rewarding good battles, or one power's mechanics?"""
    total = len(candidates)
    top = candidates[: min(AUDIT_SIZE, total)]

    print(f"\n=== top {len(top)} diversity ===")
    powers: Counter[str] = Counter()
    for candidate in top:
        for power in candidate.metrics.powers:
            powers[power] += 1
    slots = 2 * len(top)
    for power, count in powers.most_common():
        flag = "  <-- over-represented" if count / slots > 0.35 else ""
        print(f"  {power:<8} {count:>5} of {slots} slots"
              f" ({_percent(count, slots)}){flag}")

    motion = Counter(candidate.metrics.kinetic_obstacles for candidate in top)
    print("  arena motion")
    for count in sorted(motion):
        label = {0: "static only", 1: "one kinetic", 2: "two kinetic"}.get(
            count, f"{count} kinetic"
        )
        print(f"    {label:<14} {motion[count]:>4} ({_percent(motion[count], len(top))})")

    cut = max(1, int(total * TOP_DECILE))
    best, everyone = candidates[:cut], candidates
    print(f"\n=== top {TOP_DECILE:.0%} ({cut}) against the whole range ({total}) ===")
    print(f"{'':<26}{'top':>10}{'all':>10}")
    for label, fn in (
        ("timeouts", lambda c: c.metrics.is_timeout),
        ("under 5 seconds", lambda c: c.metrics.duration < 5.0),
        ("draws", lambda c: c.metrics.is_draw),
    ):
        print(f"  {label:<24}{_percent(sum(fn(c) for c in best), cut):>10}"
              f"{_percent(sum(fn(c) for c in everyone), total):>10}")
    for label, fn in (
        ("lead changes", lambda c: c.metrics.lead_changes),
        ("close-fight fraction", lambda c: c.metrics.close_fraction),
        ("damaging hits", lambda c: c.metrics.damaging_hits),
        ("hit mechanisms", lambda c: c.metrics.hit_subtypes),
        ("comeback HP", lambda c: c.metrics.winner_comeback),
        ("obstacle contacts", lambda c: c.metrics.obstacle_contacts),
        ("duration", lambda c: c.metrics.duration),
    ):
        print(f"  {label + ' (mean)':<24}"
              f"{statistics.mean([fn(c) for c in best]):>10.2f}"
              f"{statistics.mean([fn(c) for c in everyone]):>10.2f}")


def _index(values: list, quantile: float) -> int:
    return min(len(values) - 1, int(quantile * (len(values) - 1)))


def _percent(part: int, whole: int) -> str:
    return "  n/a" if whole == 0 else f"{100.0 * part / whole:5.1f}%"


def _shortlist(candidates: list[Candidate], limit: int) -> list[dict]:
    return [
        {
            "rank": rank,
            "seed": c.metrics.seed,
            "score": round(c.score.total, 3),
            "arena_mode": c.metrics.arena_mode,
            "layout_id": c.metrics.layout_id,
            "powers": list(c.metrics.powers),
            "winner_id": c.metrics.winner_id,
            "duration": round(c.metrics.duration, 3),
            "is_timeout": c.metrics.is_timeout,
            "components": {
                "pacing": round(c.score.pacing, 3),
                "suspense": round(c.score.suspense, 3),
                "action": round(c.score.action, 3),
                "variety": round(c.score.variety, 3),
                "arena": round(c.score.arena, 3),
                "payoff": round(c.score.payoff, 3),
                "penalty": round(c.score.penalty, 3),
            },
        }
        for rank, c in enumerate(candidates[:limit], start=1)
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="rank seeded battles by interest")
    parser.add_argument("--seeds", type=int, default=1000, help="how many seeds to run")
    parser.add_argument("--start", type=int, default=0, help="first seed of the range")
    parser.add_argument(
        "--arena", choices=LAYOUT_TYPES, default=LAYOUT_PROCEDURAL, help="arena mode"
    )
    parser.add_argument("--top", type=int, default=20, help="how many to list")
    parser.add_argument("--stats", action="store_true", help="score distribution")
    parser.add_argument(
        "--audit", action="store_true", help="top-N diversity and quality comparison"
    )
    parser.add_argument(
        "--explain",
        type=int,
        metavar="SEED",
        default=None,
        help="print one seed's full score breakdown and exit",
    )
    parser.add_argument("--json", metavar="PATH", default=None, help="write the shortlist")
    parser.add_argument(
        "--jobs",
        type=int,
        default=max(1, (os.cpu_count() or 2) - 1),
        help="worker processes (1 disables multiprocessing)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.explain is not None:
        metrics = evaluate_seed(args.explain, arena_mode=args.arena)
        print(score_battle(metrics).explain(metrics))
        return

    seeds = range(args.start, args.start + args.seeds)
    jobs = [(seed, args.arena) for seed in seeds]

    started = time.perf_counter()
    candidates = search(jobs, args.jobs)
    elapsed = time.perf_counter() - started

    print(
        f"evaluated {len(candidates)} {args.arena} battles,"
        f" seeds {seeds.start}-{seeds.stop - 1}"
        f"  ({elapsed:.1f}s, {len(candidates) / elapsed:.0f} battles/s,"
        f" {args.jobs} workers)"
    )
    report_table(candidates, args.top)
    if args.stats:
        report_distribution(candidates)
    if args.audit:
        report_audit(candidates)
    if args.json:
        with open(args.json, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(_shortlist(candidates, args.top), handle, indent=2)
        print(f"\nshortlist -> {args.json}")


if __name__ == "__main__":
    main()

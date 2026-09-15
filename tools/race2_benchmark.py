"""Many seeds of one Race #2 course, and the hero seed that comes out of them.

Usage:

    python tools/race2_benchmark.py --course=switchyard --seeds=200
    python tools/race2_benchmark.py --course=switchyard --seeds=200 --hero

The health numbers, the fairness numbers and the content numbers all come from
`race2.bench`, so this and `tools/race2_concepts.py` measure the same things the
same way.

## The hero seed

Chosen *after* the course is healthy across many seeds, never designed for. The
brief's list of what a hero race should contain is turned into a score with the
weights stated below, and the top ten are printed with their numbers so the
choice can be argued with rather than only accepted.

The one rule that is not a weight: a hero race must have all eight finishers.
A film in which a colour the viewer picked vanishes has broken its own promise,
whatever else it did.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from race2.bench import SeedResult, run_seeds

# What a hero race should contain, as weights. Every term is normalised to
# roughly 0..1 before it is weighted, so the numbers below are the relative
# importance and not a scale.
#
# `lead_changes` and `late_lead` are separated on purpose: twenty lead changes
# in the first four seconds and none after is a worse film than eight spread
# over the whole race, and only the second term can tell them apart.
WEIGHTS = {
    "lead_changes": 1.0,        # leader changes hands often
    "late_lead": 1.6,           # and is still changing hands in the last third
    "comeback": 1.4,            # the winner was well down at the first checkpoint
    "close_finish": 1.3,        # first to second is tight
    "density": 0.8,             # events per second
    "gap": 1.2,                 # and no long dead interval (scored inverted)
}


def _score(result: SeedResult, worst_gap: float) -> tuple[float, dict]:
    if result.finished != result.racers:
        return (-1.0, {})
    terms = {
        "lead_changes": min(result.lead_changes / 26.0, 1.0),
        "late_lead": min(result.late_lead_changes / 6.0, 1.0),
        "comeback": min(result.comeback / 6.0, 1.0),
        "close_finish": (
            0.0 if result.podium_gap is None
            else max(0.0, 1.0 - result.podium_gap / 1.2)
        ),
        "density": min(result.density / 8.0, 1.0),
        "gap": max(0.0, 1.0 - result.longest_gap / max(worst_gap, 1e-6)),
    }
    total = sum(WEIGHTS[k] * v for k, v in terms.items())
    return total, terms


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--course", default="switchyard")
    parser.add_argument("--seeds", type=int, default=120)
    parser.add_argument("--first", type=int, default=1)
    parser.add_argument("--duration", type=float, default=40.0)
    parser.add_argument("--marbles", type=int, default=8)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--hero", action="store_true")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    seeds = list(range(args.first, args.first + args.seeds))
    done = [0]

    def progress(index: int, total: int) -> None:
        if index == total or index % max(1, total // 20) == 0:
            print(f"  {index}/{total}", flush=True)

    print(f"{args.course}: {len(seeds)} seeds from {args.first}", flush=True)
    bench = run_seeds(args.course, seeds, duration=args.duration,
                      marbles=args.marbles, workers=args.workers or None,
                      progress=progress)
    print()
    print(bench.summary())

    report = bench.to_json()
    if args.hero:
        worst = max((r.longest_gap for r in bench.results), default=1.0)
        scored = []
        for result in bench.results:
            total, terms = _score(result, worst)
            if total >= 0:
                scored.append((total, result, terms))
        scored.sort(key=lambda row: -row[0])
        print(f"\n{len(scored)} of {len(bench.results)} races had all "
              f"{args.marbles} finishers\n")
        print(f"{'seed':>6}{'score':>7}{'lead':>6}{'late':>6}{'back':>6}"
              f"{'podium':>8}{'ev/s':>7}{'gap':>6}{'winner':>8}{'slot':>6}")
        print("-" * 66)
        for total, result, _terms in scored[: args.top]:
            print(f"{result.seed:6d}{total:7.3f}{result.lead_changes:6d}"
                  f"{result.late_lead_changes:6d}{result.comeback:6d}"
                  f"{result.podium_gap or 0:8.3f}{result.density:7.2f}"
                  f"{result.longest_gap:6.2f}"
                  # `or -1` here would print marble 0 as -1, which it did.
                  f"{result.winner if result.winner is not None else -1:8d}"
                  f"{result.winner_slot if result.winner_slot is not None else -1:6d}")
        if scored:
            report["hero"] = {
                "seed": scored[0][1].seed,
                "score": round(scored[0][0], 4),
                "terms": {k: round(v, 4) for k, v in scored[0][2].items()},
                "weights": WEIGHTS,
                "shortlist": [
                    {"seed": r.seed, "score": round(t, 4), **r.to_json()}
                    for t, r, _ in scored[: args.top]
                ],
            }
            print(f"\nhero seed: {scored[0][1].seed}")

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=1)
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

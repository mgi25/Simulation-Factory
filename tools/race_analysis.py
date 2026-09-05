"""Measure how predictable a course is, over enough seeds to mean something.

`tools/race_batch.py` answers whether a course *works* - does it finish, does
it get stuck, how long does it take. This answers whether it is worth
watching: how early the winner is settled, whether a starting slot is worth
anything, and how much of the field is still in it at half distance.

    python -m tools.race_analysis --count 1000 --course prototype
    python -m tools.race_analysis --count 2500 --course machine --racers 16
    python -m tools.race_analysis --count 1000 --json out.json --top 12

A thousand races is around twelve minutes on one core, so the work is spread
across processes. Each race is a pure function of its seed, so the pool
changes nothing about any result - only how long the batch takes.
"""

from __future__ import annotations

import argparse
import json
import statistics
from concurrent.futures import ProcessPoolExecutor

from race.analysis import aggregate, format_analysis, race_metrics, trace_race
from race.config import RACER_COUNT
from race.courses import COURSE_NAMES, DEFAULT_COURSE
from race.telemetry import race_summary

__all__ = ["analyse_seed", "analyse_batch", "shortlist", "format_shortlist"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure race predictability")
    parser.add_argument("--count", type=int, default=1000, help="how many seeds")
    parser.add_argument("--start-seed", type=int, default=1000, help="first seed")
    parser.add_argument("--seeds", default=None, help="explicit comma-separated seeds")
    parser.add_argument(
        "--course", choices=COURSE_NAMES, default=DEFAULT_COURSE, help="course to run"
    )
    parser.add_argument(
        "--racers", type=int, default=RACER_COUNT, help="how many racers to start"
    )
    parser.add_argument(
        "--workers", type=int, default=0, help="processes to use (0 = all cores)"
    )
    parser.add_argument(
        "--json", metavar="PATH", default=None, help="write every record as JSON"
    )
    parser.add_argument(
        "--top", type=int, default=0, help="also print the N best candidate seeds"
    )
    return parser.parse_args()


def analyse_seed(job: tuple[int, str, int]) -> dict:
    """Run and measure one race. A pure function of the job tuple.

    Takes a tuple rather than three arguments because that is what a process
    pool's `map` can send, and returns plain data for the same reason: the
    manager and the simulation cannot cross a process boundary and there is
    no reason for them to.
    """
    seed, course, racers = job
    manager, trace = trace_race(seed, course_name=course, racer_count=racers)
    record = race_metrics(trace)
    summary = race_summary(manager)
    record.update(
        {
            "completed": summary["completed"],
            "timed_out": summary["timed_out"],
            "race_duration": summary["race_duration"],
            "racers_finished": summary["racers_finished"],
            "racers_retired": summary["racers_retired"],
            "recoveries": summary["recoveries"],
            "overtakes": summary["overtakes"],
            "large_collisions": summary["large_collisions"],
            "leader_changes_manager": summary["leader_changes"],
        }
    )
    return record


def analyse_batch(
    seeds: list[int],
    course: str = DEFAULT_COURSE,
    racers: int = RACER_COUNT,
    workers: int = 0,
) -> list[dict]:
    """Measure a whole batch, in parallel unless asked not to."""
    jobs = [(seed, course, racers) for seed in seeds]
    if workers == 1 or len(jobs) < 4:
        return [analyse_seed(job) for job in jobs]
    with ProcessPoolExecutor(max_workers=workers or None) as pool:
        return list(pool.map(analyse_seed, jobs, chunksize=4))


# --- picking a race to look at ---------------------------------------------

# What a watchable race is, as weights on numbers that are already measured.
# Deliberately blunt: this is a shortlist for a human to review, not the
# curation system, and a score that needed explaining would be doing too
# much. Every term is normalised to roughly 0..1 before weighting.
CANDIDATE_WEIGHTS = {
    "lock": 3.0,        # the winner settles late
    "competitive": 2.0, # the field is still together at half distance
    "comeback": 1.5,    # the winner came from somewhere
    "podium": 1.0,      # the top three turned over
    "margin": 1.0,      # it was close at the line
    "pace": 1.0,        # the winner's time is inside the target band
}
TARGET_WINNER_LOW = 15.0
TARGET_WINNER_HIGH = 22.0


def candidate_score(record: dict, field: int) -> float:
    """How promising one race looks, before anybody watches it."""
    if not record.get("completed") or record.get("winner_id") is None:
        return 0.0
    lock = record.get("winner_lock_fraction") or 0.0
    half = (record.get("marks", {}).get("50") or {}).get("competitive", 1)
    worst = record.get("winner_worst_rank") or 1
    podium = record.get("podium_racers") or 1
    margin = record.get("final_margin")
    winner_time = record.get("winner_time") or 0.0

    terms = {
        "lock": min(1.0, lock),
        "competitive": min(1.0, (half - 1) / max(1.0, field - 1)),
        "comeback": min(1.0, (worst - 1) / max(1.0, field - 1)),
        "podium": min(1.0, (podium - 3) / max(1.0, field - 3)),
        # Half a second is a photo finish, three seconds is a procession.
        "margin": 0.0 if margin is None else max(0.0, 1.0 - margin / 3.0),
        "pace": 1.0 if TARGET_WINNER_LOW <= winner_time <= TARGET_WINNER_HIGH else 0.0,
    }
    return sum(CANDIDATE_WEIGHTS[key] * value for key, value in terms.items())


def shortlist(records: list[dict], count: int, field: int) -> list[dict]:
    """The best-looking races, most promising first."""
    scored = [
        dict(record, candidate_score=round(candidate_score(record, field), 3))
        for record in records
    ]
    scored.sort(key=lambda record: (-record["candidate_score"], record["seed"]))
    return scored[:count]


def format_shortlist(rows: list[dict]) -> str:
    lines = [
        "=== CANDIDATE SEEDS ===",
        "   seed   score   winner   time    lock   worst   podium   margin   comp@50",
    ]
    for row in rows:
        half = (row.get("marks", {}).get("50") or {}).get("competitive", 0)
        margin = row.get("final_margin")
        lines.append(
            f"  {row['seed']:>6}  {row['candidate_score']:6.2f}"
            f"  {row['winner_id']:>6}  {row['winner_time'] or 0.0:6.2f}"
            f"  {row.get('winner_lock_fraction') or 0.0:6.2f}"
            f"  {row.get('winner_worst_rank') or 0:>5}"
            f"  {row.get('podium_racers') or 0:>7}"
            f"  {'  n/a' if margin is None else f'{margin:6.2f}'}"
            f"  {half:>7}"
        )
    return "\n".join(lines)


def health_lines(records: list[dict], field: int) -> list[str]:
    """The does-it-work numbers, so this tool can stand on its own."""
    winners = [r["winner_time"] for r in records if r.get("winner_time") is not None]
    durations = [
        r["race_duration"] for r in records if r.get("race_duration") is not None
    ]
    failures = [
        r
        for r in records
        if r.get("timed_out") or r.get("winner_id") is None or r.get("racers_retired")
    ]
    in_band = [
        t for t in winners if TARGET_WINNER_LOW <= t <= TARGET_WINNER_HIGH
    ]
    lines = [
        "=== BATCH HEALTH ===",
        f"Races: {len(records)}   completed: {sum(1 for r in records if r.get('completed'))}"
        f"   failures: {len(failures)}",
    ]
    if winners:
        lines.append(
            f"Winner time: min {min(winners):.2f}s  mean {statistics.fmean(winners):.2f}s"
            f"  max {max(winners):.2f}s"
            f"   in {TARGET_WINNER_LOW:g}-{TARGET_WINNER_HIGH:g}s band:"
            f" {100.0 * len(in_band) / len(winners):.1f}%"
        )
    if durations:
        lines.append(
            f"Race duration: mean {statistics.fmean(durations):.2f}s"
            f"  max {max(durations):.2f}s"
        )
    lines.append(
        f"Racers finished: mean "
        f"{statistics.fmean(r['racers_finished'] for r in records):.2f}/{field}"
        f"   recoveries {sum(r['recoveries'] for r in records)}"
        f"   retirements {sum(r['racers_retired'] for r in records)}"
    )
    return lines


def main() -> None:
    args = parse_args()
    if args.seeds:
        seeds = [int(value) for value in args.seeds.split(",") if value.strip()]
    else:
        seeds = list(range(args.start_seed, args.start_seed + args.count))

    field = max(1, args.racers)
    records = analyse_batch(seeds, args.course, field, args.workers)

    print(f"course: {args.course}   racers: {field}   seeds: {len(seeds)}")
    print()
    print("\n".join(health_lines(records, field)))
    print()
    print(format_analysis(aggregate(records, field)))

    if args.top:
        print()
        print(format_shortlist(shortlist(records, args.top, field)))

    if args.json:
        with open(args.json, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(
                {
                    "course": args.course,
                    "racers": field,
                    "seeds": seeds,
                    "records": records,
                    "aggregate": aggregate(records, field),
                },
                handle,
                indent=2,
            )
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()

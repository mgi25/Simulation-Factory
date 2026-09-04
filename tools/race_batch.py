"""Run a batch of races headlessly and report what actually happened.

The tool the V0.1 acceptance numbers come from. It exists because the only
honest way to say a physics race is reliable is to run a lot of them and
count the failures, and because "it looked fine when I watched it" is not a
result.

    python -m tools.race_batch --count 20 --start-seed 1000
    python -m tools.race_batch --seeds 839271,12345 --verbose

A race counts as a failure if it timed out, produced no winner, or retired
a racer - anything that would make the run unusable as content. Stuck
recoveries are not failures; they are the net doing its job, and they are
counted separately so a rising number is visible.
"""

from __future__ import annotations

import argparse
import json
import statistics

from race.courses import COURSE_NAMES, DEFAULT_COURSE
from race.manager import RaceManager
from race.simulation import RaceSimulation
from race.telemetry import format_summary, race_summary

__all__ = ["run_batch", "batch_report"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a batch of races and report")
    parser.add_argument("--count", type=int, default=20, help="how many seeds to run")
    parser.add_argument("--start-seed", type=int, default=1000, help="first seed")
    parser.add_argument(
        "--seeds", default=None, help="comma-separated explicit seed list"
    )
    parser.add_argument(
        "--course", choices=COURSE_NAMES, default=DEFAULT_COURSE, help="course to run"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="print the full summary for every race"
    )
    parser.add_argument(
        "--json", metavar="PATH", default=None, help="also write every summary as JSON"
    )
    return parser.parse_args()


def run_one(seed: int, course: str) -> dict:
    """Run a single race to completion and return its summary."""
    manager = RaceManager(RaceSimulation(seed, course_name=course))
    manager.run()
    summary = race_summary(manager)
    summary["_manager"] = manager
    return summary


def run_batch(seeds: list[int], course: str = DEFAULT_COURSE) -> list[dict]:
    return [run_one(seed, course) for seed in seeds]


def _failed(summary: dict) -> bool:
    """Whether a race is unusable, as opposed to merely untidy."""
    return (
        summary["timed_out"]
        or summary["winner"] is None
        or summary["racers_retired"] > 0
    )


def batch_report(summaries: list[dict]) -> str:
    """The aggregate block: the numbers a phase report should quote."""
    count = len(summaries)
    if not count:
        return "no races run"

    winners = [s["winner_time"] for s in summaries if s["winner_time"] is not None]
    durations = [s["race_duration"] for s in summaries if s["race_duration"] is not None]
    failures = [s for s in summaries if _failed(s)]
    in_band = [t for t in winners if 15.0 <= t <= 25.0]
    unique_winners = {s["winner"] for s in summaries if s["winner"]}

    lines = [
        "=== BATCH RESULTS ===",
        f"Seeds tested: {count}",
        f"Successful completions: {count - len(failures)}",
        f"Full race failures: {len(failures)}",
        f"Winner time: min {min(winners):.2f}s  mean {statistics.fmean(winners):.2f}s  "
        f"max {max(winners):.2f}s" if winners else "Winner time: n/a",
        f"Winner time in 15-25s band: {len(in_band)}/{len(winners)}",
        f"Race duration: min {min(durations):.2f}s  mean {statistics.fmean(durations):.2f}s  "
        f"max {max(durations):.2f}s" if durations else "Race duration: n/a",
        f"Racers finished: mean {statistics.fmean(s['racers_finished'] for s in summaries):.2f}/10",
        f"Stuck racer recoveries: {sum(s['recoveries'] for s in summaries)}"
        f" (affecting {sum(s['racers_stuck'] for s in summaries)} racers)",
        f"Retired racers: {sum(s['racers_retired'] for s in summaries)}",
        f"Leader changes: mean {statistics.fmean(s['leader_changes'] for s in summaries):.2f}"
        f"  min {min(s['leader_changes'] for s in summaries)}"
        f"  max {max(s['leader_changes'] for s in summaries)}",
        f"Overtakes: mean {statistics.fmean(s['overtakes'] for s in summaries):.1f}",
        f"Large collisions: mean {statistics.fmean(s['large_collisions'] for s in summaries):.1f}",
        f"Spinner contacts: mean {statistics.fmean(s['spinner_contacts'] for s in summaries):.1f}",
        # The unpredictability check: a course that always rewards the same
        # starting slot would show one or two winners across the whole batch.
        f"Distinct winners: {len(unique_winners)}/10 racers",
    ]
    lines.extend(_branch_lines(summaries))
    if failures:
        lines.append("Failures:")
        for summary in failures:
            reason = "timeout" if summary["timed_out"] else (
                "no winner" if summary["winner"] is None else "retirement"
            )
            lines.append(f"  seed {summary['seed']}: {reason}")
    return "\n".join(lines)


def _branch_lines(summaries: list[dict]) -> list[str]:
    """How a split course actually split, over the whole batch.

    Two numbers decide whether a fork is real. If almost every racer takes
    one side, the course has a fork on paper only. If almost every winner
    comes from one side, it has a fork that is really a punishment - and
    nothing about ranking across branches is being exercised by it.

    Silent on a course with no branches, so the report shape follows the
    course rather than the tool.
    """
    branches = sorted({branch for s in summaries for branch in s.get("branches", ())})
    if not branches:
        return []

    entries = {branch: 0 for branch in branches}
    winners = {branch: 0 for branch in branches}
    for summary in summaries:
        for branch, count in (summary.get("branch_entries") or {}).items():
            entries[branch] = entries.get(branch, 0) + count
        if summary.get("winner_branch"):
            winners[summary["winner_branch"]] += 1

    total = sum(entries.values()) or 1
    return [
        "Branch entries: "
        + "  ".join(
            f"{branch} {entries[branch]} ({100.0 * entries[branch] / total:.0f}%)"
            for branch in branches
        ),
        "Branch winners: "
        + "  ".join(f"{branch} {winners[branch]}" for branch in branches),
    ]


def main() -> None:
    args = parse_args()
    if args.seeds:
        seeds = [int(value) for value in args.seeds.split(",") if value.strip()]
    else:
        seeds = list(range(args.start_seed, args.start_seed + args.count))

    summaries = []
    for seed in seeds:
        summary = run_one(seed, args.course)
        manager = summary.pop("_manager")
        summaries.append(summary)
        if args.verbose:
            print(format_summary(manager))
            print()
        else:
            band = "" if summary["winner_time"] is None else (
                "  " if 15.0 <= summary["winner_time"] <= 25.0 else " !"
            )
            print(
                f"seed {seed:>8}  winner {str(summary['winner']):>8}"
                f"  {summary['winner_time']:6.2f}s{band}"
                f"  finished {summary['racers_finished']:2d}/10"
                f"  leads {summary['leader_changes']:2d}"
                f"  recoveries {summary['recoveries']:2d}"
                + ("  TIMEOUT" if summary["timed_out"] else "")
            )

    print()
    print(batch_report(summaries))

    if args.json:
        with open(args.json, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(summaries, handle, indent=2)
        print(f"wrote {args.json}")


if __name__ == "__main__":
    main()

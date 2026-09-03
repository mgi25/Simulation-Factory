"""Headless balance harness: run many battles and print the numbers.

A developer tool, not part of the simulation. It exists so power tuning is
decided from a matchup matrix over deterministic seed ranges rather than from
a handful of watched battles. Nothing here is written to disk: the console
output is the report.

Typical use::

    python tools/balance_report.py --seeds 200                  # tuning matrix
    python tools/balance_report.py --seeds 300 --start 10000    # holdout
    python tools/balance_report.py --random 1000                # matchmaking

Cross matchups are run in both orientations on the same seed - RED echo /
BLUE titan and RED titan / BLUE echo - so a spawn-position advantage cancels
out instead of being read as a power advantage.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from itertools import combinations

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.simulation import PHYSICS_DT, Simulation  # noqa: E402
from modes.power_battle import BATTLE_DURATION_TICKS, PowerBattleMode  # noqa: E402
from powers import POWER_NAMES  # noqa: E402

# How often a running battle is checked for non-finite or out-of-arena state.
# Every tick is wasteful over thousands of battles and misses nothing that
# survives longer than a twenty-fourth of a second.
VALIDITY_CHECK_EVERY = 5

SHORT_THRESHOLDS = (3.0, 5.0)


@dataclass(frozen=True)
class Result:
    """One battle, reduced to the numbers a balance decision needs."""

    seed: int
    red_power: str
    blue_power: str
    winner_id: int | None
    duration: float
    timeout: bool
    invalid: bool
    leaked: bool

    @property
    def is_draw(self) -> bool:
        return self.winner_id is None

    @property
    def winner_power(self) -> str | None:
        if self.winner_id is None:
            return None
        return self.red_power if self.winner_id == 0 else self.blue_power


def run_battle(job: tuple[int, str, str]) -> Result:
    """Run one pinned matchup headlessly and reduce it to a `Result`."""
    seed, red, blue = job
    sim = Simulation(seed)
    mode = PowerBattleMode(sim, powers=[red, blue])

    invalid = False
    while mode.step():
        if sim.ticks % VALIDITY_CHECK_EVERY == 0 and not sim.is_state_valid():
            invalid = True

    leaked = bool(sim.dynamic_entities) or len(sim.space.bodies) != len(sim.balls)
    finished_tick = mode.finished_tick or 0
    return Result(
        seed=seed,
        red_power=red,
        blue_power=blue,
        winner_id=None if mode.winner is None else mode.winner.ball_id,
        duration=finished_tick * PHYSICS_DT,
        timeout=finished_tick >= BATTLE_DURATION_TICKS,
        invalid=invalid,
        leaked=leaked,
    )


def matrix_jobs(seeds: range) -> list[tuple[int, str, str]]:
    """Every unordered matchup: cross ones in both orientations, mirrors once."""
    jobs: list[tuple[int, str, str]] = []
    for a, b in combinations(POWER_NAMES, 2):
        for seed in seeds:
            jobs.append((seed, a, b))
            jobs.append((seed, b, a))
    for name in POWER_NAMES:
        for seed in seeds:
            jobs.append((seed, name, name))
    return jobs


def random_jobs(seeds: range) -> list[tuple[int, str, str]]:
    """Seeded matchmaking: whatever each seed's own power stream picked."""
    return [
        (seed, *PowerBattleMode(Simulation(seed)).matchup) for seed in seeds
    ]


def run_all(jobs: list[tuple[int, str, str]], workers: int) -> list[Result]:
    if workers <= 1:
        return [run_battle(job) for job in jobs]
    chunk = max(1, len(jobs) // (workers * 8))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(run_battle, jobs, chunksize=chunk))


# --- reporting ---


def _percent(part: int, whole: int) -> str:
    return "  n/a" if whole == 0 else f"{100.0 * part / whole:5.1f}%"


def report(results: list[Result], title: str) -> None:
    total = len(results)
    durations = sorted(r.duration for r in results)
    cross = [r for r in results if r.red_power != r.blue_power]
    mirrors = [r for r in results if r.red_power == r.blue_power]
    timeouts = sum(r.timeout for r in results)
    draws = sum(r.is_draw for r in results)

    print(f"\n=== {title} ===")
    print(f"battles           {total}  (cross {len(cross)}, mirror {len(mirrors)})")
    print(f"timeouts          {timeouts} ({_percent(timeouts, total)})")
    print(f"draws             {draws} ({_percent(draws, total)})")
    print(f"median duration   {statistics.median(durations):.2f} s")
    print(f"duration range    {durations[0]:.2f} - {durations[-1]:.2f} s")
    for limit in SHORT_THRESHOLDS:
        short = sum(1 for d in durations if d < limit)
        print(f"fights <{limit:.0f} sec       {short} ({_percent(short, total)})")
    print(f"invalid states    {sum(r.invalid for r in results)}")
    print(f"entity leaks      {sum(r.leaked for r in results)}")

    red_wins = sum(1 for r in results if r.winner_id == 0)
    blue_wins = sum(1 for r in results if r.winner_id == 1)
    print(f"RED wins          {red_wins} ({_percent(red_wins, total)})")
    print(f"BLUE wins         {blue_wins} ({_percent(blue_wins, total)})")

    _report_powers(cross, mirrors)
    _report_matrix(cross)
    _report_mirrors(mirrors)


def _report_powers(cross: list[Result], mirrors: list[Result]) -> None:
    """Overall strength, measured on cross matchups only.

    A mirror is self-play: it always hands one win to the power on both
    sides, so folding mirrors in would drag every rate towards 50% and hide
    exactly what this report exists to show.
    """
    played: dict[str, int] = defaultdict(int)
    won: dict[str, int] = defaultdict(int)
    for r in cross:
        played[r.red_power] += 1
        played[r.blue_power] += 1
        if r.winner_power is not None:
            won[r.winner_power] += 1

    print("\npower          battles    wins    rate")
    for name in POWER_NAMES:
        print(
            f"  {name:<11} {played[name]:>7} {won[name]:>7}  "
            f"{_percent(won[name], played[name])}"
        )
    if mirrors:
        print(f"  (mirrors excluded: {len(mirrors)} battles)")


def _report_matrix(cross: list[Result]) -> None:
    """Row power's win rate against column power, both orientations pooled."""
    played: dict[tuple[str, str], int] = defaultdict(int)
    won: dict[tuple[str, str], int] = defaultdict(int)
    for r in cross:
        for me, foe in ((r.red_power, r.blue_power), (r.blue_power, r.red_power)):
            played[(me, foe)] += 1
            if r.winner_power == me:
                won[(me, foe)] += 1

    print("\nmatchup matrix (row win % vs column)")
    print("            " + "".join(f"{name:>9}" for name in POWER_NAMES))
    for row in POWER_NAMES:
        cells = []
        for col in POWER_NAMES:
            cell = "-" if row == col else _percent(won[(row, col)], played[(row, col)])
            cells.append(f"{cell:>9}")
        print(f"  {row:<10}" + "".join(cells))


def _report_mirrors(mirrors: list[Result]) -> None:
    """Mirrors say nothing about a power; they expose fighter-side bias."""
    if not mirrors:
        return
    print("\nmirror matchups (RED win % - side bias only)")
    for name in POWER_NAMES:
        rows = [r for r in mirrors if r.red_power == name]
        if not rows:
            continue
        red = sum(1 for r in rows if r.winner_id == 0)
        draws = sum(1 for r in rows if r.is_draw)
        print(
            f"  {name:<11} {len(rows):>5} battles   RED {_percent(red, len(rows))}"
            f"   draws {draws}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="headless balance report")
    parser.add_argument(
        "--seeds",
        type=int,
        default=200,
        help="seeds per unordered matchup for the full matrix (default 200)",
    )
    parser.add_argument(
        "--start", type=int, default=0, help="first seed of the range (default 0)"
    )
    parser.add_argument(
        "--random",
        type=int,
        default=0,
        help="instead of the matrix, run N seeds of seeded matchmaking",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=max(1, (os.cpu_count() or 2) - 1),
        help="worker processes (1 disables multiprocessing)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.random:
        seeds = range(args.start, args.start + args.random)
        jobs = random_jobs(seeds)
        title = f"seeded matchmaking, seeds {seeds.start}-{seeds.stop - 1}"
    else:
        seeds = range(args.start, args.start + args.seeds)
        jobs = matrix_jobs(seeds)
        title = (
            f"matchup matrix, seeds {seeds.start}-{seeds.stop - 1}, "
            "both orientations"
        )

    report(run_all(jobs, args.jobs), title)


if __name__ == "__main__":
    main()

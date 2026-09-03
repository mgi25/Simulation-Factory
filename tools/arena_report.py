"""Headless arena harness: validate generated layouts and smoke-test battles.

A developer tool, not part of the simulation. It answers three questions that
a unit test can only sample: are generated layouts geometrically sound across
many seeds, how often does generation have to settle for fewer obstacles, and
does procedural geometry break battles that run fine on the classic arena.

Typical use::

    python tools/arena_report.py --layouts 5000            # geometry + variety
    python tools/arena_report.py --battles 2000            # procedural smoke
    python tools/arena_report.py --battles 2000 --control  # classic alongside

Nothing is written to disk: the console output is the report.
"""

from __future__ import annotations

import argparse
import math
import os
import statistics
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.arena import Arena  # noqa: E402
from engine.arena_generator import (  # noqa: E402
    MAX_FIGHTER_RADIUS,
    OBSTACLE_PAIR_CLEARANCE,
    OBSTACLE_SPAWN_CLEARANCE,
    OBSTACLE_WALL_CLEARANCE,
    generate_layout,
)
from engine.arena_layout import LAYOUT_CLASSIC, LAYOUT_PROCEDURAL  # noqa: E402
from engine.randomizer import generate_ball_spawns, make_rng  # noqa: E402
from engine.simulation import BALL_COUNT, PHYSICS_DT, Simulation  # noqa: E402
from modes.power_battle import BATTLE_DURATION_TICKS, PowerBattleMode  # noqa: E402

# How often a running battle is checked for non-finite or out-of-arena state,
# matching the balance harness: every tick is wasteful over thousands of
# battles and misses nothing that survives a twenty-fourth of a second.
VALIDITY_CHECK_EVERY = 5

# Chipmunk has no continuous collision detection, so a fighter travelling
# 8-15 px per tick always dips a few pixels into whatever it hits before the
# solver pushes it back out - the arena walls have always done this. Depth
# alone therefore says nothing; how *long* an overlap lasts does. A fighter
# still inside static geometry a whole simulated second later is wedged.
PENETRATION_NOTICE = 1.0
STUCK_TICKS = 120


# --- layout geometry -------------------------------------------------------


@dataclass(frozen=True)
class LayoutCheck:
    """One generated layout, reduced to the numbers this report needs."""

    seed: int
    requested: int
    placed: int
    circles: int
    boxes: int
    rotations: tuple[float, ...]
    outside: int
    spawn_conflicts: int
    overlaps: int
    non_finite: int
    signature: tuple

    @property
    def fallback(self) -> bool:
        return self.placed < self.requested

    @property
    def invalid(self) -> int:
        return self.outside + self.spawn_conflicts + self.overlaps + self.non_finite


def check_layout(seed: int) -> LayoutCheck:
    arena = Arena.default()
    spawns = generate_ball_spawns(make_rng(seed), arena, BALL_COUNT)
    layout = generate_layout(seed, arena, spawns)

    outside = spawn_conflicts = overlaps = non_finite = 0
    for index, obstacle in enumerate(layout.obstacles):
        values = (
            obstacle.x,
            obstacle.y,
            obstacle.radius,
            obstacle.width,
            obstacle.height,
            obstacle.rotation_degrees,
        )
        if not all(math.isfinite(value) for value in values):
            non_finite += 1
        if obstacle.clearance_to_bounds(arena) < OBSTACLE_WALL_CLEARANCE:
            outside += 1
        for spawn in spawns:
            if obstacle.distance_to_point(spawn.x, spawn.y) < (
                MAX_FIGHTER_RADIUS + OBSTACLE_SPAWN_CLEARANCE
            ):
                spawn_conflicts += 1
        for other in layout.obstacles[index + 1 :]:
            if obstacle.clearance_to(other) < OBSTACLE_PAIR_CLEARANCE:
                overlaps += 1

    return LayoutCheck(
        seed=seed,
        requested=layout.requested_obstacles,
        placed=len(layout),
        circles=sum(1 for o in layout if o.is_circle),
        boxes=sum(1 for o in layout if not o.is_circle),
        rotations=tuple(o.rotation_degrees for o in layout if not o.is_circle),
        outside=outside,
        spawn_conflicts=spawn_conflicts,
        overlaps=overlaps,
        non_finite=non_finite,
        signature=tuple(
            (o.kind, o.x, o.y, o.radius, o.width, o.height, o.rotation_degrees)
            for o in layout
        ),
    )


def report_layouts(checks: list[LayoutCheck]) -> None:
    total = len(checks)
    fallbacks = [c for c in checks if c.fallback]

    print(f"\n=== generated layouts, {total} seeds ===")
    print(f"layouts checked   {total}")
    print(f"invalid           {sum(c.invalid for c in checks)}")
    print(f"  outside arena   {sum(c.outside for c in checks)}")
    print(f"  spawn conflicts {sum(c.spawn_conflicts for c in checks)}")
    print(f"  pair overlaps   {sum(c.overlaps for c in checks)}")
    print(f"  non-finite      {sum(c.non_finite for c in checks)}")
    print(f"unique layouts    {len({c.signature for c in checks})}")
    print(f"fallbacks         {len(fallbacks)} ({_percent(len(fallbacks), total)})")

    reduced = Counter((c.requested, c.placed) for c in fallbacks)
    for (requested, placed), count in sorted(reduced.items()):
        print(f"  {requested} requested -> {placed} placed   {count}")

    print(f"\nobstacles         {sum(c.placed for c in checks)}")
    _distribution("obstacle count", Counter(c.placed for c in checks), total)
    _distribution("circles", Counter(c.circles for c in checks), total)
    _distribution("boxes", Counter(c.boxes for c in checks), total)

    rotations = Counter(r for c in checks for r in c.rotations)
    print("\nbar rotations")
    for rotation, count in sorted(rotations.items()):
        print(f"  {rotation:5.0f} deg   {count:>7} ({_percent(count, rotations.total())})")


def _distribution(label: str, counts: Counter, total: int) -> None:
    print(f"\n{label}")
    for value, count in sorted(counts.items()):
        print(f"  {value:>3}   {count:>7} ({_percent(count, total)})")


# --- battle smoke ----------------------------------------------------------


@dataclass(frozen=True)
class BattleCheck:
    """One battle, reduced to the numbers this report needs."""

    seed: int
    mode: str
    obstacles: int
    fallback: bool
    winner_id: int | None
    duration: float
    timeout: bool
    invalid: bool
    leaked: bool
    penetration: float
    overlap_ticks: int

    @property
    def is_draw(self) -> bool:
        return self.winner_id is None

    @property
    def stuck(self) -> bool:
        return self.overlap_ticks >= STUCK_TICKS


def static_penetration(sim: Simulation) -> float:
    """How deep the worst fighter currently is inside a wall or an obstacle."""
    arena, worst = sim.arena, 0.0
    for ball in sim.balls:
        x, y = ball.position
        worst = max(
            worst,
            arena.left + ball.radius - x,
            x - (arena.right - ball.radius),
            arena.top + ball.radius - y,
            y - (arena.bottom - ball.radius),
        )
        for obstacle in sim.layout.obstacles:
            worst = max(worst, -obstacle.clearance_to_circle(x, y, ball.radius))
    return worst


def run_battle(job: tuple[int, str]) -> BattleCheck:
    """Run one seeded-matchmaking battle and reduce it to a `BattleCheck`."""
    seed, mode = job
    sim = Simulation(seed, arena_mode=mode)
    battle = PowerBattleMode(sim)

    invalid = False
    deepest = 0.0
    overlapping = longest = 0
    while battle.step():
        # Every tick: a run of overlapping ticks is only meaningful if none
        # of them are skipped.
        depth = static_penetration(sim)
        deepest = max(deepest, depth)
        overlapping = overlapping + 1 if depth > PENETRATION_NOTICE else 0
        longest = max(longest, overlapping)
        if sim.ticks % VALIDITY_CHECK_EVERY == 0 and not sim.is_state_valid():
            invalid = True

    leaked = bool(sim.dynamic_entities) or len(sim.space.bodies) != len(sim.balls)
    finished_tick = battle.finished_tick or 0
    return BattleCheck(
        seed=seed,
        mode=mode,
        obstacles=len(sim.layout),
        fallback=sim.layout.fallback,
        winner_id=None if battle.winner is None else battle.winner.ball_id,
        duration=finished_tick * PHYSICS_DT,
        timeout=finished_tick >= BATTLE_DURATION_TICKS,
        invalid=invalid,
        leaked=leaked,
        penetration=deepest,
        overlap_ticks=longest,
    )


def report_battles(results: list[BattleCheck], title: str) -> None:
    total = len(results)
    durations = sorted(r.duration for r in results)
    timeouts = sum(r.timeout for r in results)
    draws = sum(r.is_draw for r in results)
    eliminations = total - timeouts

    print(f"\n=== {title} ===")
    print(f"battles           {total}")
    print(f"eliminations      {eliminations} ({_percent(eliminations, total)})")
    print(f"timeouts          {timeouts} ({_percent(timeouts, total)})")
    print(f"draws             {draws} ({_percent(draws, total)})")
    print(f"invalid states    {sum(r.invalid for r in results)}")
    print(f"entity leaks      {sum(r.leaked for r in results)}")
    print(f"wedged fighters   {sum(r.stuck for r in results)}"
          f"  (overlapping static geometry for {STUCK_TICKS}+ ticks)")
    print(f"deepest overlap   {max(r.penetration for r in results):.2f} px"
          f"  (median peak {statistics.median([r.penetration for r in results]):.2f})")
    print(f"longest overlap   {max(r.overlap_ticks for r in results)} ticks"
          f"  (median peak {statistics.median([r.overlap_ticks for r in results]):.0f})")
    print(f"layout fallbacks  {sum(r.fallback for r in results)}")
    print(f"obstacles present {sum(r.obstacles for r in results)}")
    print(f"median duration   {statistics.median(durations):.2f} s")
    print(f"duration range    {durations[0]:.2f} - {durations[-1]:.2f} s")


def run_all(jobs: list[tuple[int, str]], workers: int) -> list[BattleCheck]:
    if workers <= 1:
        return [run_battle(job) for job in jobs]
    chunk = max(1, len(jobs) // (workers * 8))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(run_battle, jobs, chunksize=chunk))


def run_checks(seeds: range, workers: int) -> list[LayoutCheck]:
    if workers <= 1:
        return [check_layout(seed) for seed in seeds]
    chunk = max(1, len(seeds) // (workers * 8))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(check_layout, seeds, chunksize=chunk))


def _percent(part: int, whole: int) -> str:
    return "  n/a" if whole == 0 else f"{100.0 * part / whole:5.2f}%"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="headless arena report")
    parser.add_argument(
        "--layouts",
        type=int,
        default=0,
        help="validate N generated layouts and report variety and fallbacks",
    )
    parser.add_argument(
        "--battles",
        type=int,
        default=0,
        help="run N procedural battles with seeded matchmaking",
    )
    parser.add_argument(
        "--control",
        action="store_true",
        help="run the same battle seeds on the classic arena for comparison",
    )
    parser.add_argument(
        "--start", type=int, default=0, help="first seed of the range (default 0)"
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
    if not args.layouts and not args.battles:
        args.layouts = 5000

    if args.layouts:
        seeds = range(args.start, args.start + args.layouts)
        report_layouts(run_checks(seeds, args.jobs))

    if args.battles:
        seeds = range(args.start, args.start + args.battles)
        report_battles(
            run_all([(seed, LAYOUT_PROCEDURAL) for seed in seeds], args.jobs),
            f"procedural battles, seeds {seeds.start}-{seeds.stop - 1}",
        )
        if args.control:
            report_battles(
                run_all([(seed, LAYOUT_CLASSIC) for seed in seeds], args.jobs),
                f"classic control, seeds {seeds.start}-{seeds.stop - 1}",
            )


if __name__ == "__main__":
    main()

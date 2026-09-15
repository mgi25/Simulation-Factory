"""Many seeds of one course, and what they say about it.

Split out of the tools so that the concept comparison, the seed benchmark and
the hero search all measure the same things the same way. A benchmark that
computed slot correlation one way for the concepts and another way for the
chosen course would be a comparison of two instruments.

## What is measured, and why each one

**finish rate / all-finished rate.** Racers that crossed the line, and races in
which every racer did. The second is the one that matters for a film: a race
that loses a marble has a colour the viewer picked disappear, and
`docs/race2_drama_camera.md` treats a 7-of-8 race as a failed race however good
the other seven were.

**stuck / escape rate.** The two ways a marble fails, kept apart because they
have different causes and different fixes. Stuck is geometry too tight; escaped
is containment too low.

**start-slot correlation.** Spearman between the bay a racer started in and the
rank it finished in, over every racer of every seed. Zero is the target. The
sign is meaningful: `bay_across` puts bay 0 on the right looking downhill, so a
positive correlation means the right-hand bays finish worse.

**route advantage.** For each split, the mean finishing rank of the racers that
took each branch, and the mean time through the stage. A split whose two sides
differ by much is not a choice, it is a tax on the marbles that guessed wrong.

**lead changes, rank changes, event density, longest dead interval.** The
content metrics, from `race2.events`.

## Parallelism

One race is six to fourteen seconds of wall time, so a 200-seed benchmark is
half an hour single-threaded. Each seed is independent and PyBullet is built
per race inside `run_race`, so a process pool is the whole of what it takes -
but the course is rebuilt inside each worker rather than pickled, because a
`Machine` holds `TriMesh` objects and a built `Course` is not picklable.
"""

from __future__ import annotations

import math
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from marble3d.config import DEFAULT_CONFIG

__all__ = ["SeedResult", "Benchmark", "run_seeds", "spearman"]


def spearman(xs: Sequence[float], ys: Sequence[float]) -> float:
    """Rank correlation, with ties given their mean rank.

    Written out rather than pulled from scipy because the repository has no
    scipy and because a correlation whose tie handling nobody can see is a
    number nobody should quote. Returns 0.0 when either series is constant,
    which is the honest answer and not an error: a course on which every racer
    finishes in the same place has no slot bias to report.
    """
    if len(xs) != len(ys) or len(xs) < 3:
        return 0.0

    def ranked(values: Sequence[float]) -> list[float]:
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        index = 0
        while index < len(order):
            stop = index
            while stop + 1 < len(order) and values[order[stop + 1]] == values[order[index]]:
                stop += 1
            mean_rank = 0.5 * (index + stop) + 1.0
            for position in range(index, stop + 1):
                out[order[position]] = mean_rank
            index = stop + 1
        return out

    rx, ry = ranked(xs), ranked(ys)
    n = len(rx)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    if dx < 1e-12 or dy < 1e-12:
        return 0.0
    return num / (dx * dy)


@dataclass
class SeedResult:
    seed: int
    finished: int
    escaped: int
    stuck: int
    racers: int
    lead_changes: int
    overtakes: int
    seconds: float
    wall: float
    first_finish: float | None
    last_finish: float | None
    podium_gap: float | None
    winner: int | None
    winner_slot: int | None
    slots: list[int] = field(default_factory=list)
    ranks: list[int] = field(default_factory=list)
    branches: dict[str, dict[str, int]] = field(default_factory=dict)
    branch_ranks: dict[str, dict[str, list[int]]] = field(default_factory=dict)
    events: int = 0
    density: float = 0.0
    longest_gap: float = 0.0
    dead_zones: int = 0
    # Lead changes in the last third of the race. Separated from the total
    # because twenty of them in the first four seconds and none afterwards is a
    # worse film than eight spread out, and only this term can tell them apart.
    late_lead_changes: int = 0
    # How far down the eventual winner was at the first-event checkpoint. The
    # comeback, as a number: 0 means it led from the front.
    comeback: int = 0
    failures: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "finished": self.finished,
            "escaped": self.escaped,
            "stuck": self.stuck,
            "lead_changes": self.lead_changes,
            "overtakes": self.overtakes,
            "first_finish": self.first_finish and round(self.first_finish, 3),
            "last_finish": self.last_finish and round(self.last_finish, 3),
            "podium_gap": self.podium_gap and round(self.podium_gap, 3),
            "winner": self.winner,
            "winner_slot": self.winner_slot,
            "events": self.events,
            "late_lead_changes": self.late_lead_changes,
            "comeback": self.comeback,
            "density": round(self.density, 3),
            "longest_gap": round(self.longest_gap, 3),
            "dead_zones": self.dead_zones,
            "branches": self.branches,
            "wall": round(self.wall, 2),
            "failures": self.failures,
        }


def _warm_cache(name: str) -> None:
    """Build the course once here, so every collider's OBJ exists on disk."""
    from marble3d.config import DEFAULT_CONFIG as _config
    from marble3d.world import MarbleWorld

    from race2 import concepts, courses

    course = courses.build(name) if name in courses.COURSES else concepts.build(name)
    world = MarbleWorld(_config)
    try:
        course.machine.build(world)
    finally:
        world.close()


def _one(args: tuple[str, int, float, int]) -> SeedResult:
    """One seed, in a worker. Rebuilds the course rather than receiving it."""
    from race2 import concepts, courses
    from race2.events import extract
    from race2.race import Race2, run_race

    name, seed, duration, marbles = args
    course = courses.build(name) if name in courses.COURSES else concepts.build(name)
    outcome, _ = run_race(course, seed=seed, duration=duration, marble_count=marbles)
    timeline = extract(outcome, course, _replay_events(course, outcome, seed, duration, marbles))

    finishers = [r for r in outcome.racers if r.finish_order is not None]
    winner = outcome.winner()
    branch_ranks: dict[str, dict[str, list[int]]] = {}
    for racer in outcome.racers:
        for split, branch in racer.branches:
            branch_ranks.setdefault(split, {}).setdefault(branch, []).append(
                racer.finish_order if racer.finish_order is not None else len(outcome.racers) + 1
            )
    at, gap = timeline.longest_gap()
    last_third = timeline.start + (timeline.end - timeline.start) * 2.0 / 3.0
    late = sum(
        1 for e in timeline.events if e.kind == "leader_change" and e.time >= last_third
    )
    comeback = 0
    if winner is not None:
        # Rank at the first checkpoint the course reached, which is the earliest
        # honest reading of "where was the winner before the race happened".
        for checkpoint in ("first_event", "quarter", "half"):
            if checkpoint in winner.ranks:
                comeback = max(0, winner.ranks[checkpoint] - 1)
                break
    return SeedResult(
        seed=seed,
        finished=outcome.finished,
        escaped=outcome.escaped,
        stuck=outcome.stuck,
        racers=len(outcome.racers),
        lead_changes=outcome.lead_changes,
        overtakes=outcome.overtakes,
        seconds=outcome.seconds,
        wall=outcome.wall_seconds,
        first_finish=min((r.finish_time for r in finishers), default=None),
        last_finish=max((r.finish_time for r in finishers), default=None),
        podium_gap=outcome.podium_gap(),
        winner=winner.marble_id if winner else None,
        winner_slot=winner.start_slot if winner else None,
        slots=[r.start_slot for r in finishers],
        ranks=[r.finish_order for r in finishers],
        branches=outcome.branch_counts,
        branch_ranks=branch_ranks,
        events=len(timeline.events),
        density=timeline.density(),
        longest_gap=gap,
        dead_zones=len(timeline.dead_zones()),
        late_lead_changes=late,
        comeback=comeback,
        failures=[outcome.failure] if outcome.failure else [],
    )


def _replay_events(course, outcome, seed, duration, marbles):
    """The simulation's own event stream for a seed already run.

    Re-running the race to get at `Race2.events` costs a second race per seed
    and is what this avoided by returning them from `run_race`... except that
    `run_race` returns an outcome and a replay, and a benchmark does not want
    the replay. So the events ride on the outcome instead - see
    `RaceOutcome.sim_events`, set by `run_race`.
    """
    return getattr(outcome, "sim_events", ())


@dataclass
class Benchmark:
    """Every seed of one course, and the summary read off them."""

    course: str
    results: list[SeedResult] = field(default_factory=list)

    @property
    def races(self) -> int:
        return len(self.results)

    @property
    def racers(self) -> int:
        return sum(r.racers for r in self.results)

    def finish_rate(self) -> float:
        return sum(r.finished for r in self.results) / max(self.racers, 1)

    def all_finished_rate(self) -> float:
        return sum(1 for r in self.results if r.finished == r.racers) / max(self.races, 1)

    def stuck_rate(self) -> float:
        return sum(r.stuck for r in self.results) / max(self.racers, 1)

    def escape_rate(self) -> float:
        return sum(r.escaped for r in self.results) / max(self.racers, 1)

    def slot_correlation(self) -> float:
        slots: list[float] = []
        ranks: list[float] = []
        for result in self.results:
            slots.extend(result.slots)
            ranks.extend(result.ranks)
        return spearman(slots, ranks)

    def winner_by_slot(self) -> dict[int, int]:
        out: dict[int, int] = {}
        for result in self.results:
            if result.winner_slot is not None:
                out[result.winner_slot] = out.get(result.winner_slot, 0) + 1
        return dict(sorted(out.items()))

    def route_advantage(self) -> dict[str, dict[str, Any]]:
        merged: dict[str, dict[str, list[int]]] = {}
        for result in self.results:
            for split, table in result.branch_ranks.items():
                for branch, ranks in table.items():
                    merged.setdefault(split, {}).setdefault(branch, []).extend(ranks)
        out: dict[str, dict[str, Any]] = {}
        for split, table in merged.items():
            entry: dict[str, Any] = {}
            for branch, ranks in sorted(table.items()):
                entry[branch] = {
                    "took": len(ranks),
                    "mean_rank": round(sum(ranks) / len(ranks), 3) if ranks else None,
                }
            means = [v["mean_rank"] for v in entry.values() if v["mean_rank"] is not None]
            entry["spread"] = round(max(means) - min(means), 3) if len(means) > 1 else 0.0
            takes = [v["took"] for v in entry.values() if isinstance(v, dict) and "took" in v]
            entry["share"] = round(max(takes) / max(sum(takes), 1), 3) if takes else 0.0
            out[split] = entry
        return out

    def mean(self, attribute: str) -> float:
        values = [getattr(r, attribute) for r in self.results]
        values = [v for v in values if v is not None]
        return sum(values) / len(values) if values else 0.0

    def worst_gap(self) -> float:
        return max((r.longest_gap for r in self.results), default=0.0)

    def to_json(self) -> dict[str, Any]:
        return {
            "course": self.course,
            "races": self.races,
            "racers": self.racers,
            "finish_rate": round(self.finish_rate(), 4),
            "all_finished_rate": round(self.all_finished_rate(), 4),
            "stuck_rate": round(self.stuck_rate(), 4),
            "escape_rate": round(self.escape_rate(), 4),
            "slot_correlation": round(self.slot_correlation(), 4),
            "winner_by_slot": self.winner_by_slot(),
            "route_advantage": self.route_advantage(),
            "mean_lead_changes": round(self.mean("lead_changes"), 3),
            "mean_overtakes": round(self.mean("overtakes"), 3),
            "mean_events": round(self.mean("events"), 3),
            "mean_density": round(self.mean("density"), 3),
            "mean_longest_gap": round(self.mean("longest_gap"), 3),
            "worst_longest_gap": round(self.worst_gap(), 3),
            "mean_dead_zones": round(self.mean("dead_zones"), 3),
            "mean_late_lead_changes": round(self.mean("late_lead_changes"), 3),
            "mean_comeback": round(self.mean("comeback"), 3),
            "mean_first_finish": round(self.mean("first_finish"), 3),
            "mean_last_finish": round(self.mean("last_finish"), 3),
            "mean_podium_gap": round(self.mean("podium_gap"), 4),
            "mean_wall": round(self.mean("wall"), 3),
            "seeds": [r.to_json() for r in self.results],
        }

    def summary(self) -> str:
        data = self.to_json()
        lines = [
            f"{self.course}: {self.races} seeds, {self.racers} racers",
            f"  finished          {data['finish_rate'] * 100:6.2f}%   "
            f"all eight {data['all_finished_rate'] * 100:6.2f}%",
            f"  stuck             {data['stuck_rate'] * 100:6.2f}%   "
            f"escaped   {data['escape_rate'] * 100:6.2f}%",
            f"  slot correlation  {data['slot_correlation']:+6.3f}",
            f"  lead changes      {data['mean_lead_changes']:6.2f}   "
            f"overtakes {data['mean_overtakes']:6.1f}",
            f"  events/s          {data['mean_density']:6.2f}   "
            f"longest gap {data['mean_longest_gap']:5.2f} s "
            f"(worst {data['worst_longest_gap']:.2f})",
            f"  race              {data['mean_first_finish']:6.2f} to "
            f"{data['mean_last_finish']:.2f} s   "
            f"podium gap {data['mean_podium_gap']:.3f} s",
        ]
        for split, entry in data["route_advantage"].items():
            parts = ", ".join(
                f"{k} {v['took']}@{v['mean_rank']}"
                for k, v in entry.items()
                if isinstance(v, dict)
            )
            lines.append(f"  split {split:<10} {parts}  spread {entry['spread']}")
        return "\n".join(lines)


def run_seeds(
    course: str,
    seeds: Sequence[int],
    duration: float = 40.0,
    marbles: int = 8,
    workers: int | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> Benchmark:
    jobs = [(course, int(seed), float(duration), int(marbles)) for seed in seeds]
    workers = workers or max(1, min(len(jobs), (os.cpu_count() or 4) - 1))
    bench = Benchmark(course=course)
    if workers > 1:
        # **Warm the collider cache in the parent first.** `marble3d.mesh`
        # caches each collider as an OBJ keyed by its digest, and Bullet loads
        # it by path. Eleven workers starting at once on a course whose meshes
        # have never been written all try to write the same files, and the ones
        # that lose the race load a file that is not there yet: a wall-height
        # scan came back as a wall of "cannot find corr1_channel_0_...obj".
        # One build in the parent costs a fraction of a second and makes the
        # pool's first act a read.
        _warm_cache(course)
    if workers <= 1:
        for index, job in enumerate(jobs, start=1):
            bench.results.append(_one(job))
            if progress:
                progress(index, len(jobs))
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for index, result in enumerate(pool.map(_one, jobs), start=1):
                bench.results.append(result)
                if progress:
                    progress(index, len(jobs))
    bench.results.sort(key=lambda r: r.seed)
    return bench

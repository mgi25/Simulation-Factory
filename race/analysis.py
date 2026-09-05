"""Race quality metrics: is the result in doubt, and for how long?

`race.telemetry` answers "what happened" - who won, how many recoveries,
how many big hits. This answers a different and harder question: **was the
race worth watching**, in the one sense that can be measured. A race whose
winner is obvious at the quarter mark is a failed race however clean its
physics, and nothing in the telemetry says so.

Everything here is derived from a *trace*: the field's progress and order,
sampled on a fixed clock while the race runs. The trace is recorded by
stepping the ordinary `RaceManager` and reading it - no rule is changed, no
extra randomness is drawn, and a traced race is bit-for-bit the race the
same seed produces without tracing.

Two conventions are used throughout and both are worth stating once.

**Race progress** is a fraction of the *winner's* race time, not of the
whole recording. The race is decided when the winner crosses; the grace
period afterwards is the pack coming home and belongs to no part of the
question being asked here. So "the leader at 25%" means the leader a
quarter of the way through the winner's run.

**Course progress** is normalised to the course: 0.0 on the starting plane
and 1.0 at the finish, whatever ladder the course happens to number itself
on. That is what makes a gap comparable between two courses of different
lengths, which is the whole point of measuring a redesign against a
baseline.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Iterable, Sequence

from race.config import PHYSICS_HZ, RACER_COUNT
from race.courses import DEFAULT_COURSE
from race.manager import (
    COUNTDOWN_TICKS,
    FINISH_GRACE_TICKS,
    RACE_TIMEOUT_TICKS,
    RaceManager,
)
from race.progress import count_inversions
from race.simulation import RaceSimulation

__all__ = [
    "ANALYSIS_SAMPLE_HZ",
    "COMPETITIVE_GAP",
    "PROGRESS_MARKS",
    "TraceSample",
    "RaceTrace",
    "trace_race",
    "race_metrics",
    "winner_lock",
    "lead_changes",
    "top3_turnover",
    "winner_worst_rank",
    "overtakes_by_third",
    "slot_table",
    "percentiles",
    "aggregate",
    "format_analysis",
]

# How often the field is sampled. Twelve a second is the rate the manager
# already counts overtakes on, and it is fast enough that a lead change
# lasting a fifth of a second is still seen while being slow enough that one
# collision is not reported as twenty.
ANALYSIS_SAMPLE_HZ = 12
SAMPLE_TICKS = max(1, int(round(PHYSICS_HZ / ANALYSIS_SAMPLE_HZ)))

# How far behind the leader a racer may be and still count as competitive,
# as a fraction of the whole course. A tenth of the course is roughly one
# obstacle: near enough that the next mixer can still hand it the lead, far
# enough that it is not simply "in the leading clump".
COMPETITIVE_GAP = 0.10

# Where the race is sampled, as fractions of the winner's time.
PROGRESS_MARKS: tuple[float, ...] = (0.10, 0.25, 0.50, 0.75)


@dataclass(frozen=True)
class TraceSample:
    """The field at one moment: where everyone is and who is where."""

    tick: int
    race_time: float
    # Normalised course progress, indexed by racer id.
    progress: tuple[float, ...]
    # Racer ids, best first. Retired racers are dropped, so this can shrink.
    order: tuple[int, ...]

    @property
    def leader(self) -> int | None:
        return self.order[0] if self.order else None

    def rank_of(self, racer_id: int) -> int:
        """1-based standing, or one past the field if no longer in it."""
        try:
            return self.order.index(racer_id) + 1
        except ValueError:
            return len(self.order) + 1

    def gap_behind_leader(self, racer_id: int) -> float:
        if not self.order:
            return 0.0
        return self.progress[self.order[0]] - self.progress[racer_id]

    def competitive(self, gap: float = COMPETITIVE_GAP) -> int:
        """How many racers are still within `gap` of the lead."""
        if not self.order:
            return 0
        lead = self.progress[self.order[0]]
        return sum(1 for rid in self.order if lead - self.progress[rid] <= gap)

    def spread(self) -> float:
        """Course progress between the leader and the last racer running."""
        if not self.order:
            return 0.0
        values = [self.progress[rid] for rid in self.order]
        return max(values) - min(values)


@dataclass(frozen=True)
class RaceTrace:
    """One race, sampled on a fixed clock, plus what it needs to be read.

    Holds no opinions. Every number in `race_metrics` is computed from these
    samples, which means a metric can be added or changed without re-running
    anything, and two metrics can never disagree about what happened.
    """

    seed: int
    course_id: str
    racer_count: int
    samples: tuple[TraceSample, ...]
    winner_id: int | None
    winner_time: float | None
    # Spawn slot each racer started in, indexed by racer id. The fairness
    # question is asked of the *slot*, not of the racer: ids are shuffled
    # between slots by seed, so counting wins per id proves nothing.
    spawn_slots: tuple[int, ...]
    finish_times: tuple[float | None, ...]
    finish_order: tuple[int, ...]

    @property
    def decided(self) -> tuple[TraceSample, ...]:
        """The samples up to and including the winner crossing the line.

        Everything after it is the pack coming home: first place cannot
        change again, and counting those samples would report every race as
        locking at the same moment.
        """
        if self.winner_time is None:
            return self.samples
        window = tuple(s for s in self.samples if s.race_time <= self.winner_time)
        return window or self.samples[:1]

    def at_fraction(self, fraction: float) -> TraceSample | None:
        """The sample nearest a fraction of the way through the winner's run."""
        window = self.decided
        if not window:
            return None
        if self.winner_time is None:
            return window[-1]
        wanted = fraction * self.winner_time
        return min(window, key=lambda sample: abs(sample.race_time - wanted))


def trace_race(
    seed: int,
    course_name: str = DEFAULT_COURSE,
    racer_count: int = RACER_COUNT,
    manager: RaceManager | None = None,
) -> tuple[RaceManager, RaceTrace]:
    """Run one race, sampling the field as it goes.

    Steps the ordinary manager rather than reimplementing the loop, and
    reads it between steps. Nothing here writes to the race, so the trace is
    an observation of exactly the race the seed produces - which is what
    lets a measured course and a rendered course be the same course.
    """
    if manager is None:
        manager = RaceManager(
            RaceSimulation(seed, course_name=course_name, racer_count=racer_count)
        )
    sim = manager.sim
    scale = max(1e-9, manager.course.max_progress)
    limit = RACE_TIMEOUT_TICKS + COUNTDOWN_TICKS + FINISH_GRACE_TICKS + 1

    samples: list[TraceSample] = []

    def take() -> None:
        progress = [0.0] * len(sim.racers)
        for racer in sim.racers:
            progress[racer.racer_id] = racer.progress / scale
        order = [racer.racer_id for racer in manager.ranked if not racer.retired]
        samples.append(
            TraceSample(
                tick=sim.ticks,
                race_time=manager.race_time,
                progress=tuple(progress),
                order=tuple(order),
            )
        )

    ticks = 0
    while ticks < limit and manager.step():
        ticks += 1
        if manager.started and sim.ticks % SAMPLE_TICKS == 0:
            take()
    if not samples:
        take()

    ordered = sorted(sim.racers, key=lambda racer: racer.racer_id)
    return manager, RaceTrace(
        seed=seed,
        course_id=manager.course.course_id,
        racer_count=len(sim.racers),
        samples=tuple(samples),
        winner_id=None if manager.winner is None else manager.winner.racer_id,
        winner_time=manager.winner_time,
        spawn_slots=tuple(racer.spawn_slot for racer in ordered),
        finish_times=tuple(racer.finish_time for racer in ordered),
        finish_order=tuple(racer.racer_id for racer in manager.finish_order),
    )


# --- the metrics -----------------------------------------------------------


def winner_lock(trace: RaceTrace) -> tuple[float | None, float | None]:
    """When the winner took first place for the last time, and stayed there.

    The entertainment metric. A race whose winner leads from a third of the
    way in and is never headed again has most of its running time left with
    nothing at stake, however many overtakes happen behind. Returned as
    seconds and as a fraction of the winner's run, because the fraction is
    what compares across races of different lengths.

    Scanning backwards is not an optimisation, it is the definition: what is
    wanted is the *last* time first place changed hands, and a forward scan
    only gets that right by doing this in reverse anyway.
    """
    window = trace.decided
    if trace.winner_id is None or not window:
        return (None, None)

    lock_index = 0
    for index in range(len(window) - 1, -1, -1):
        if window[index].leader != trace.winner_id:
            lock_index = index + 1
            break
    if lock_index >= len(window):
        # The winner never led at a sampled moment before crossing: it took
        # the lead by finishing. That is the latest lock there can be.
        seconds = window[-1].race_time
    else:
        seconds = window[lock_index].race_time
    seconds = max(0.0, seconds)
    if not trace.winner_time:
        return (seconds, None)
    return (seconds, seconds / trace.winner_time)


def lead_changes(trace: RaceTrace) -> int:
    """How many times first place changed hands before the race was decided."""
    changes = 0
    previous: int | None = None
    for sample in trace.decided:
        leader = sample.leader
        if leader is None:
            continue
        if previous is not None and leader != previous:
            changes += 1
        previous = leader
    return changes


def top3_turnover(trace: RaceTrace) -> tuple[int, int]:
    """Distinct racers who held a podium place, and how often the set changed.

    Two numbers because they say different things. A high distinct count
    with few changes is a field that reshuffled once; a high change count is
    a podium that never settled. A course wants both.
    """
    seen: set[int] = set()
    changes = 0
    previous: frozenset[int] | None = None
    for sample in trace.decided:
        podium = frozenset(sample.order[:3])
        seen |= podium
        if previous is not None and podium != previous:
            changes += 1
        previous = podium
    return (len(seen), changes)


def winner_worst_rank(trace: RaceTrace, after: float = 0.25) -> int | None:
    """The comeback metric: how far back the winner was, once racing properly.

    Measured after the first quarter because the opening is where a field is
    still leaving the grid, and a racer that is tenth two seconds in has not
    made a comeback - it has not started yet. A winner whose worst position
    after that is eighth came from somewhere; one whose worst is first led
    from the front.
    """
    if trace.winner_id is None or trace.winner_time is None:
        return None
    cutoff = after * trace.winner_time
    ranks = [
        sample.rank_of(trace.winner_id)
        for sample in trace.decided
        if sample.race_time >= cutoff
    ]
    return max(ranks) if ranks else None


def overtakes_by_third(trace: RaceTrace) -> tuple[int, int, int]:
    """Order changes in the first, middle and last third of the winner's run.

    An overtake is a pair of racers swapping relative order between two
    samples, the same definition the manager counts on - so a racer passing
    three others scores three.
    """
    window = trace.decided
    if not trace.winner_time or len(window) < 2:
        return (0, 0, 0)
    thirds = [0, 0, 0]
    for before, after in zip(window, window[1:]):
        share = after.race_time / trace.winner_time
        bucket = min(2, max(0, int(share * 3.0)))
        thirds[bucket] += count_inversions(before.order, after.order)
    return (thirds[0], thirds[1], thirds[2])


def median_gap(sample: TraceSample) -> float:
    """Course progress between the leader and the middle of the field.

    The number that says whether the race has split into a breakaway and a
    remainder. The gap to second place can stay tiny while the other eight
    racers are a third of a course behind.
    """
    if len(sample.order) < 2:
        return 0.0
    lead = sample.progress[sample.order[0]]
    others = sorted(sample.progress[rid] for rid in sample.order)
    return lead - statistics.median(others)


def race_metrics(trace: RaceTrace, gap: float = COMPETITIVE_GAP) -> dict:
    """Every quality number for one race, as plain data."""
    lock_seconds, lock_fraction = winner_lock(trace)
    distinct_podium, podium_changes = top3_turnover(trace)
    first, middle, last = overtakes_by_third(trace)

    marks: dict[str, dict] = {}
    slot_progress: dict[str, dict[str, float]] = {}
    for fraction in PROGRESS_MARKS:
        sample = trace.at_fraction(fraction)
        key = str(int(round(fraction * 100)))
        if sample is None:
            marks[key] = {}
            continue
        second_gap = 0.0
        if len(sample.order) >= 2:
            second_gap = (
                sample.progress[sample.order[0]] - sample.progress[sample.order[1]]
            )
        marks[key] = {
            "race_time": round(sample.race_time, 3),
            "leader": sample.leader,
            "leader_is_winner": sample.leader == trace.winner_id,
            "winner_rank": (
                None if trace.winner_id is None else sample.rank_of(trace.winner_id)
            ),
            "competitive": sample.competitive(gap),
            "gap_first_second": round(second_gap, 4),
            "gap_first_median": round(median_gap(sample), 4),
            "spread": round(sample.spread(), 4),
        }
        slot_progress[key] = {
            str(trace.spawn_slots[rid]): round(sample.progress[rid], 4)
            for rid in range(len(trace.spawn_slots))
        }

    positions = {}
    for position, racer_id in enumerate(trace.finish_order, start=1):
        positions[str(trace.spawn_slots[racer_id])] = position
    unfinished = trace.racer_count
    for slot in range(len(trace.spawn_slots)):
        positions.setdefault(str(slot), unfinished)

    return {
        "seed": trace.seed,
        "course": trace.course_id,
        "racer_count": trace.racer_count,
        "winner_id": trace.winner_id,
        "winner_time": None if trace.winner_time is None else round(trace.winner_time, 3),
        "winner_slot": (
            None if trace.winner_id is None else trace.spawn_slots[trace.winner_id]
        ),
        "first_leader": trace.decided[0].leader if trace.decided else None,
        "winner_lock_seconds": None if lock_seconds is None else round(lock_seconds, 3),
        "winner_lock_fraction": (
            None if lock_fraction is None else round(lock_fraction, 4)
        ),
        "lead_changes": lead_changes(trace),
        "podium_racers": distinct_podium,
        "podium_changes": podium_changes,
        "winner_worst_rank": winner_worst_rank(trace),
        "overtakes_first_third": first,
        "overtakes_middle_third": middle,
        "overtakes_final_third": last,
        "final_margin": final_margin(trace),
        "marks": marks,
        # Per-slot views, keyed by slot as a string so the record survives a
        # round trip through JSON unchanged.
        "slots_used": sorted(set(trace.spawn_slots)),
        "slot_finish": positions,
        "slot_progress_25": slot_progress.get("25", {}),
        "slot_progress_50": slot_progress.get("50", {}),
    }


def final_margin(trace: RaceTrace) -> float | None:
    """Seconds between the winner and the runner-up crossing the line."""
    if len(trace.finish_order) < 2:
        return None
    first = trace.finish_times[trace.finish_order[0]]
    second = trace.finish_times[trace.finish_order[1]]
    if first is None or second is None:
        return None
    return round(second - first, 3)


# --- across a batch --------------------------------------------------------


def slot_table(records: Sequence[dict], slots: int) -> list[dict]:
    """Wins per physical starting slot, which is the fairness question.

    Not per racer id. Ids are shuffled between slots by seed, so every id
    wins sometimes on any course whatsoever - including one where the slot
    nearest the first gap always wins. The slot is the thing that could be
    unfair, so the slot is what is counted.
    """
    table = []
    for slot in range(slots):
        key = str(slot)
        starts = sum(1 for record in records if slot in record.get("slots_used", ()))
        wins = sum(1 for record in records if record.get("winner_slot") == slot)
        finals = [
            record["slot_finish"][key]
            for record in records
            if record.get("slot_finish", {}).get(key) is not None
        ]
        marks25 = [
            record["slot_progress_25"][key]
            for record in records
            if record.get("slot_progress_25", {}).get(key) is not None
        ]
        marks50 = [
            record["slot_progress_50"][key]
            for record in records
            if record.get("slot_progress_50", {}).get(key) is not None
        ]
        table.append(
            {
                "slot": slot,
                "starts": starts,
                "wins": wins,
                "win_pct": 100.0 * wins / starts if starts else 0.0,
                "mean_final_position": statistics.fmean(finals) if finals else None,
                "mean_progress_25": statistics.fmean(marks25) if marks25 else None,
                "mean_progress_50": statistics.fmean(marks50) if marks50 else None,
            }
        )
    return table


def percentiles(
    values: Iterable[float], points: Sequence[float] = (10, 50, 90)
) -> dict:
    """Percentiles by nearest rank, which needs no interpolation policy."""
    ordered = sorted(value for value in values if value is not None)
    if not ordered:
        return {f"p{int(point)}": None for point in points}
    result = {}
    for point in points:
        index = int(round(point / 100.0 * (len(ordered) - 1)))
        result[f"p{int(point)}"] = ordered[min(len(ordered) - 1, max(0, index))]
    return result


def _mean(values: Iterable[float]) -> float | None:
    kept = [value for value in values if value is not None]
    return statistics.fmean(kept) if kept else None


def aggregate(records: Sequence[dict], slots: int) -> dict:
    """Roll a batch of per-race metrics into the numbers a report quotes."""
    decided = [record for record in records if record.get("winner_id") is not None]
    locks = [
        record["winner_lock_fraction"]
        for record in decided
        if record.get("winner_lock_fraction") is not None
    ]
    lock_seconds = [
        record["winner_lock_seconds"]
        for record in decided
        if record.get("winner_lock_seconds") is not None
    ]

    marks: dict[str, dict] = {}
    for fraction in PROGRESS_MARKS:
        key = str(int(round(fraction * 100)))
        rows = [record["marks"].get(key) or {} for record in decided]
        rows = [row for row in rows if row]
        if not rows:
            continue
        marks[key] = {
            "leader_wins_pct": 100.0
            * sum(1 for row in rows if row.get("leader_is_winner"))
            / len(rows),
            "mean_competitive": _mean(row["competitive"] for row in rows),
            "mean_gap_first_second": _mean(row["gap_first_second"] for row in rows),
            "mean_gap_first_median": _mean(row["gap_first_median"] for row in rows),
            "mean_spread": _mean(row["spread"] for row in rows),
            "mean_winner_rank": _mean(row.get("winner_rank") for row in rows),
        }

    worst = [
        record["winner_worst_rank"]
        for record in decided
        if record.get("winner_worst_rank")
    ]
    margins = [
        record["final_margin"]
        for record in decided
        if record.get("final_margin") is not None
    ]
    table = slot_table(records, slots)
    win_rates = [row["win_pct"] for row in table if row["starts"]]

    return {
        "races": len(records),
        "decided": len(decided),
        "winner_lock_fraction": percentiles(locks)
        | {
            "mean": _mean(locks),
            "before_half_pct": (
                100.0 * sum(1 for value in locks if value < 0.5) / len(locks)
                if locks
                else None
            ),
            "at_or_after_75_pct": (
                100.0 * sum(1 for value in locks if value >= 0.75) / len(locks)
                if locks
                else None
            ),
        },
        "winner_lock_seconds": percentiles(lock_seconds),
        "marks": marks,
        "lead_changes": {"mean": _mean(r["lead_changes"] for r in decided)}
        | percentiles([r["lead_changes"] for r in decided]),
        "podium_racers": {"mean": _mean(r["podium_racers"] for r in decided)}
        | percentiles([r["podium_racers"] for r in decided]),
        "podium_changes": {"mean": _mean(r["podium_changes"] for r in decided)},
        "winner_worst_rank": {
            "mean": _mean(worst),
            "distribution": {
                str(rank): sum(1 for value in worst if value == rank)
                for rank in sorted(set(worst))
            },
        },
        "final_margin": {"mean": _mean(margins)} | percentiles(margins),
        "overtakes": {
            "first_third": _mean(r["overtakes_first_third"] for r in decided),
            "middle_third": _mean(r["overtakes_middle_third"] for r in decided),
            "final_third": _mean(r["overtakes_final_third"] for r in decided),
        },
        "slots": table,
        "slot_bias": _slot_bias(table, win_rates),
    }


def _slot_bias(table: list[dict], win_rates: list[float]) -> dict:
    used = [row for row in table if row["starts"]]
    if not used or not win_rates:
        return {
            "strongest": None,
            "weakest": None,
            "ratio": None,
            "max_win_pct": None,
            "min_win_pct": None,
        }
    strongest = max(used, key=lambda row: row["win_pct"])
    weakest = min(used, key=lambda row: row["win_pct"])
    return {
        "strongest": strongest["slot"],
        "weakest": weakest["slot"],
        # Undefined rather than infinite when a slot never won: a ratio of
        # infinity reads as a bug and says less than "one slot scored zero".
        "ratio": (
            strongest["win_pct"] / weakest["win_pct"]
            if weakest["win_pct"] > 0.0
            else None
        ),
        "max_win_pct": strongest["win_pct"],
        "min_win_pct": weakest["win_pct"],
    }


def format_analysis(report: dict) -> str:
    """The aggregate block, in the shape a phase report quotes."""
    lines = [
        "=== RACE QUALITY ===",
        f"Races analysed: {report['races']}  (decided: {report['decided']})",
    ]
    lock = report["winner_lock_fraction"]
    if lock.get("p50") is not None:
        lines.append(
            "Winner lock (fraction of winner race):"
            f"  p10 {lock['p10']:.2f}  median {lock['p50']:.2f}"
            f"  p90 {lock['p90']:.2f}  mean {lock['mean']:.2f}"
        )
        lines.append(
            f"  locked before halfway: {lock['before_half_pct']:.1f}%"
            f"   locked at/after 75%: {lock['at_or_after_75_pct']:.1f}%"
        )
    seconds = report["winner_lock_seconds"]
    if seconds.get("p50") is not None:
        lines.append(
            f"Winner lock (seconds): p10 {seconds['p10']:.2f}"
            f"  median {seconds['p50']:.2f}  p90 {seconds['p90']:.2f}"
        )

    for key in sorted(report["marks"], key=int):
        row = report["marks"][key]
        lines.append(
            f"At {key:>2}%: leader wins {row['leader_wins_pct']:5.1f}%"
            f"   competitive {row['mean_competitive']:.2f}"
            f"   gap 1-2 {row['mean_gap_first_second']:.3f}"
            f"   gap 1-med {row['mean_gap_first_median']:.3f}"
            f"   winner rank {row['mean_winner_rank']:.2f}"
        )

    leads = report["lead_changes"]
    if leads["mean"] is not None:
        lines.append(
            f"Lead changes: mean {leads['mean']:.2f}  p10 {leads['p10']}"
            f"  median {leads['p50']}  p90 {leads['p90']}"
        )
    podium = report["podium_racers"]
    if podium["mean"] is not None:
        lines.append(
            f"Podium racers: mean {podium['mean']:.2f}"
            f"  (set changes mean {report['podium_changes']['mean']:.1f})"
        )
    worst = report["winner_worst_rank"]
    if worst["mean"] is not None:
        spread = "  ".join(
            f"{rank}:{count}"
            for rank, count in sorted(
                worst["distribution"].items(), key=lambda item: int(item[0])
            )
        )
        lines.append(f"Winner worst rank after 25%: mean {worst['mean']:.2f}   {spread}")
    margin = report["final_margin"]
    if margin["mean"] is not None:
        lines.append(
            f"Final margin: mean {margin['mean']:.2f}s  p10 {margin['p10']:.2f}"
            f"  median {margin['p50']:.2f}  p90 {margin['p90']:.2f}"
        )
    over = report["overtakes"]
    if over["first_third"] is not None:
        lines.append(
            f"Overtakes by third: {over['first_third']:.1f} /"
            f" {over['middle_third']:.1f} / {over['final_third']:.1f}"
        )

    lines.append("")
    lines.append("Starting slot:")
    lines.append("  slot  starts   wins    win%   avg final   prog@25%   prog@50%")
    for row in report["slots"]:
        final = (
            "  n/a"
            if row["mean_final_position"] is None
            else f"{row['mean_final_position']:5.2f}"
        )
        p25 = (
            "  n/a" if row["mean_progress_25"] is None else f"{row['mean_progress_25']:.3f}"
        )
        p50 = (
            "  n/a" if row["mean_progress_50"] is None else f"{row['mean_progress_50']:.3f}"
        )
        lines.append(
            f"  {row['slot']:>4}  {row['starts']:>6}  {row['wins']:>5}"
            f"  {row['win_pct']:>5.1f}%    {final}      {p25}      {p50}"
        )
    bias = report["slot_bias"]
    if bias["max_win_pct"] is not None:
        ratio = "n/a" if bias["ratio"] is None else f"{bias['ratio']:.2f}x"
        lines.append(
            f"  strongest slot {bias['strongest']} ({bias['max_win_pct']:.1f}%)"
            f"   weakest slot {bias['weakest']} ({bias['min_win_pct']:.1f}%)"
            f"   ratio {ratio}"
        )
    return "\n".join(lines)

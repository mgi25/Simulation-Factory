"""Race telemetry: what happened, as data and as a printable summary.

Reads a finished (or half-finished) race and reports it. It holds no state
of its own and never touches the manager or the simulation, which is what
makes it safe to call at any point - including on a race that timed out,
where an honest partial report is exactly what is wanted.

This is deliberately not a scoring system. It collects the raw material an
interestingness score would eventually be computed from - lead changes,
overtakes, big collisions, how spread the finish was - and stops there.
"""

from __future__ import annotations

from typing import Any

from race.config import RACER_COUNT
from race.manager import RaceManager, RaceState
from race.racer import Racer

__all__ = ["race_summary", "format_summary", "format_finish_order"]


def race_summary(manager: RaceManager) -> dict[str, Any]:
    """Everything worth knowing about a race, as plain JSON-compatible data."""
    sim = manager.sim
    racers = sim.racers
    finished = manager.finish_order
    stuck = [racer for racer in racers if racer.recoveries > 0]
    retired = [racer for racer in racers if racer.retired]

    return {
        "seed": sim.seed,
        "course": sim.course.course_id,
        "racer_count": len(racers),
        "state": manager.state.value,
        # A race that reached a result. A timeout is a failed race, and so
        # is a race with nobody home - both are reported, not hidden.
        "completed": manager.state is RaceState.COMPLETE and not manager.timed_out,
        "timed_out": manager.timed_out,
        "race_duration": _rounded(manager.duration),
        "winner": None if manager.winner is None else manager.winner.name,
        "winner_id": None if manager.winner is None else manager.winner.racer_id,
        "winner_time": _rounded(manager.winner_time),
        "finish_order": [racer.name for racer in finished],
        "finish_times": [_rounded(racer.finish_time) for racer in finished],
        # Finish time plus recovery penalties. Kept separate from
        # `finish_times` because the order shown on screen is the order they
        # crossed in; this is the adjusted figure, not a re-ranking.
        "official_times": [_rounded(racer.official_time) for racer in finished],
        "leader_changes": manager.leader_changes,
        "racers_finished": len(finished),
        "racers_stuck": len(stuck),
        "racers_retired": len(retired),
        "recoveries": manager.recoveries,
        "overtakes": manager.overtakes,
        "large_collisions": manager.large_collisions,
        "spinner_contacts": sim.spinner_contacts,
        "finish_spread": _finish_spread(finished),
        "unfinished": [racer.name for racer in racers if not racer.finished],
        "events": len(manager.events),
    }


def _rounded(value: float | None, places: int = 2) -> float | None:
    return None if value is None else round(value, places)


def _finish_spread(finished: list[Racer]) -> float | None:
    """Seconds between the first and last finisher.

    A crude read on whether a race was close. Meaningless with fewer than
    two finishers, and reported as absent rather than as zero.
    """
    if len(finished) < 2:
        return None
    first, last = finished[0].finish_time, finished[-1].finish_time
    if first is None or last is None:
        return None
    return round(last - first, 2)


def format_finish_order(manager: RaceManager) -> str:
    """The results table, one line per finisher.

        1. Racer_07 - 18.42s
        2. Racer_02 - 18.91s  (+1.5s recovery)
    """
    lines = []
    for position, racer in enumerate(manager.finish_order, start=1):
        line = f"{position:2d}. {racer.name} - {racer.finish_time:.2f}s"
        if racer.time_penalty > 0.0:
            line += f"  (+{racer.time_penalty:.1f}s recovery)"
        lines.append(line)
    for racer in manager.sim.racers:
        if racer.finished:
            continue
        state = "RETIRED" if racer.retired else "DNF"
        lines.append(
            f"  - {racer.name} - {state} at {racer.progress:.2f}/"
            f"{manager.course.last_index}"
        )
    return "\n".join(lines)


def format_summary(manager: RaceManager, finish_order: bool = True) -> str:
    """The end-of-race block, in the shape the brief asked for."""
    summary = race_summary(manager)
    total = summary["racer_count"] or RACER_COUNT
    duration = summary["race_duration"]
    winner_time = summary["winner_time"]

    lines = [
        "=== RACE COMPLETE ===" if not summary["timed_out"] else "=== RACE TIMED OUT ===",
        f"Seed: {summary['seed']}",
        f"Course: {summary['course']}",
        f"Winner: {summary['winner'] or 'NONE'}",
        f"Time: {'n/a' if winner_time is None else f'{winner_time:.2f}s'}",
        f"Duration: {'n/a' if duration is None else f'{duration:.2f}s'}",
        f"Leader Changes: {summary['leader_changes']}",
        f"Overtakes: {summary['overtakes']}",
        f"Finished: {summary['racers_finished']}/{total}",
        f"Stuck: {summary['racers_stuck']} ({summary['recoveries']} recoveries)",
        f"Retired: {summary['racers_retired']}",
        f"Large Collisions: {summary['large_collisions']}",
    ]
    if summary["finish_spread"] is not None:
        lines.append(f"Finish Spread: {summary['finish_spread']:.2f}s")
    if finish_order and manager.finish_order:
        lines.append("")
        lines.append(format_finish_order(manager))
    return "\n".join(lines)

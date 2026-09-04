"""Where each racer is on the course, and who is therefore winning.

Ranking is the one piece of race logic that has to be right for the whole
thing to read as a race, and the obvious implementation is wrong. Distance
to the finish - straight-line or vertical - ranks a racer that has fallen
into the jump pit ahead of one still on the platform above it, because the
pit is lower down. It would also rank a racer part-way up a spinner arm
ahead of the field it is about to be dropped behind.

So progress is measured along the course rather than through space: which
checkpoint plane a racer has passed, and how far it has got towards the
next one on *its own route*.

That last qualification is what makes a split-path course work, and it is
the whole reason this is a graph rather than a ladder. On a course that
forks, two racers at the same height are not necessarily level: one may be
four nodes into a long, safe detour while the other is two nodes into a
short, fast chute. Height cannot tell them apart, and neither can a single
ordered list of planes. What can is asking each racer how far through the
route it is actually on it has got, and comparing that - which is exactly
what `Checkpoint.value` holds and what this module reads.

A racer's branch is not chosen here and is never guessed at. It is a
consequence of which corridor the racer physically was in when it crossed a
branch entry plane, and it clears itself the moment the racer crosses a
main-line node, because a main-line node is on every route and therefore
means the split is behind.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from race.course import Checkpoint, RaceCourse, progress_along
from race.racer import Racer

__all__ = [
    "update_progress",
    "progress_of",
    "reset_progress",
    "ranking",
    "assign_ranks",
    "count_inversions",
]


def _reached_node(course: RaceCourse, racer: Racer) -> Checkpoint | None:
    """The furthest node this racer has been credited with, if any."""
    if racer.checkpoint < 0:
        return None
    return course.checkpoints[racer.checkpoint]


def _candidates(course: RaceCourse, racer: Racer) -> list[Checkpoint]:
    """Nodes still ahead of this racer, on a route it may still take.

    A racer already committed to a branch can only reach that branch's
    nodes and the main line; a racer that has not committed may reach any
    branch's entry. Anything at or behind the racer's own progress mark is
    already spent and can never be crossed again, which is what stops a
    racer thrown back up the course from re-triggering a plane.
    """
    reached = _reached_node(course, racer)
    mark = float("-inf") if reached is None else reached.value
    ahead = []
    for checkpoint in course.checkpoints:
        if checkpoint.value <= mark:
            continue
        if checkpoint.branch and racer.branch and checkpoint.branch != racer.branch:
            continue
        ahead.append(checkpoint)
    ahead.sort(key=lambda checkpoint: (checkpoint.value, checkpoint.index))
    return ahead


def update_progress(course: RaceCourse, racer: Racer) -> list[int]:
    """Refresh a racer's progress and return any checkpoints newly crossed.

    A checkpoint, once reached, stays reached: the racer's progress mark is
    a high-water mark, so a racer thrown back up the course by a spinner
    keeps its credit and does not re-trigger the crossing on the way down
    again. Continuous progress is *not* a high-water mark - it has to be
    able to go down, or being knocked backwards would cost a racer nothing.

    Several planes can be crossed in one tick, and all of them are
    reported: a racer dropped a long way by a jump has genuinely passed
    each one. Where two nodes sit at the same course progress - the two
    entries of a split - at most one is ever taken, because they are
    alternatives rather than a sequence.
    """
    x, y = racer.position.x, racer.position.y
    crossed: list[int] = []
    claimed: set[float] = set()

    for checkpoint in _candidates(course, racer):
        if checkpoint.value in claimed or not checkpoint.reached_by(x, y):
            continue
        claimed.add(checkpoint.value)
        crossed.append(checkpoint.index)
        racer.checkpoint = checkpoint.index
        # A main-line node is on every route, so crossing one means any
        # split is behind and the racer is back on the shared spine.
        racer.branch = checkpoint.branch

    racer.progress = progress_of(course, racer)
    return crossed


def progress_of(course: RaceCourse, racer: Racer) -> float:
    """Continuous course progress for a racer, along the route it is on."""
    return progress_along(
        course.route(racer.branch),
        racer.position.y,
        course.top,
        _reached_node(course, racer),
    )


def reset_progress(course: RaceCourse, racer: Racer, y: float | None = None) -> float:
    """Recompute a racer's progress and clear its stuck high-water mark.

    Used where a racer's position changed by something other than the
    solver - the gate opening, or a recovery - so the two marks describe
    where the racer now is rather than where it used to be.
    """
    node = _reached_node(course, racer)
    height = racer.position.y if y is None else y
    racer.progress = progress_along(course.route(racer.branch), height, course.top, node)
    racer.best_progress = racer.progress
    racer.stuck_ticks = 0
    return racer.progress


def ranking(racers: Iterable[Racer]) -> list[Racer]:
    """The field in race order, best first.

    Finished racers come first, in the order they crossed the line. That is
    crossing order rather than adjusted time on purpose: it is the order a
    viewer just watched happen, and a results table that disagreed with the
    screen would be wrong however defensible its arithmetic. Recovery
    penalties are carried separately on `Racer.official_time`.

    Everyone still running is ordered by course progress, and a retired
    racer sorts last whatever progress it had reached.
    """
    return sorted(racers, key=_rank_key)


def _rank_key(racer: Racer) -> tuple:
    if racer.finished:
        # `finish_tick` is set the moment a racer finishes, so it is never
        # None here; the fallback keeps the key total if that ever changes.
        return (0, racer.finish_tick if racer.finish_tick is not None else 0, racer.racer_id)
    if racer.retired:
        return (2, 0, racer.racer_id)
    # Negated so that more progress sorts earlier. Racer id breaks ties, so
    # the order is stable and never depends on list order or dict iteration.
    return (1, -racer.progress, racer.racer_id)


def assign_ranks(racers: Iterable[Racer]) -> list[Racer]:
    """Rank the field and write each racer's 1-based position onto it."""
    order = ranking(racers)
    for position, racer in enumerate(order, start=1):
        racer.rank = position
    return order


def count_inversions(before: Sequence[int], after: Sequence[int]) -> int:
    """How many pairs swapped relative order between two rankings.

    This is the overtake count. A pair is counted once however far either
    racer moved, so one racer passing five others scores five - which is
    what an overtake means - rather than one, and a racer sliding down the
    order does not score again for the same swap.
    """
    place = {racer_id: index for index, racer_id in enumerate(after)}
    inversions = 0
    for i, first in enumerate(before):
        if first not in place:
            continue
        for second in before[i + 1 :]:
            if second in place and place[first] > place[second]:
                inversions += 1
    return inversions

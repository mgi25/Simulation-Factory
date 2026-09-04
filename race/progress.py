"""Where each racer is on the course, and who is therefore winning.

Ranking is the one piece of race logic that has to be right for the whole
thing to read as a race, and the obvious implementation is wrong. Distance
to the finish - straight-line or vertical - ranks a racer that has fallen
into the jump pit ahead of one still on the platform above it, because the
pit is lower down. It would also rank a racer part-way up a spinner arm
ahead of the field it is about to be dropped behind.

So progress is measured along the course rather than through space: which
checkpoint plane a racer has passed, and how far it has got towards the
next one. That is a total order that follows the route, and it is monotonic
in the direction of travel by construction.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from race.course import RaceCourse
from race.racer import Racer

__all__ = ["update_progress", "ranking", "assign_ranks", "count_inversions"]


def update_progress(course: RaceCourse, racer: Racer) -> list[int]:
    """Refresh a racer's progress and return any checkpoints newly crossed.

    A checkpoint, once reached, stays reached: `racer.checkpoint` is a
    high-water mark, so a racer thrown back up the course by a spinner keeps
    its credit and does not re-trigger the crossing on the way down again.
    Continuous progress is *not* a high-water mark - it has to be able to go
    down, or being knocked backwards would cost a racer nothing.
    """
    racer.progress = course.progress_at(racer.position.y)
    reached = course.reached_index(racer.position.y)
    crossed: list[int] = []
    if reached > racer.checkpoint:
        crossed = list(range(racer.checkpoint + 1, reached + 1))
        racer.checkpoint = reached
    return crossed


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

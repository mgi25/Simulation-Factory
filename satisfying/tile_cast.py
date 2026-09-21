"""Choosing which runs get rendered, and saying out loud what each one is for.

Phase 2 produced a shortlist of twenty seeds ranked by `candidate_score`. That
is the right answer to "which seed is best" and the wrong answer to "which
seeds should Phase 3 render", for one reason: the score's runtime component
peaks at 32.5 s and falls off either side, so the top twenty all completed
between 30.3 s and 32.3 s. Rendering those twenty would test one two-second
slice of the envelope and call it a proof.

Phase 3 needs *contrast*. A visual proof has to survive a 26-second run whose
tiles light up fast enough to blur together, a 38-second run long enough to go
slack, a run whose last tile is on the ceiling and one whose last tile is by
the floor - and, so the reader has something to compare against, at least one
run the evaluator rejected.

So this module selects by **role**, not by rank. Each role is a question the
render is meant to answer, each is filled by the best-scoring accepted seed
that satisfies it, and a seed fills at most one role so that eight roles give
eight different videos.

## The roles

| role | what it is for |
|---|---|
| `band_25_30` | the fast end: does the eye keep up when tiles fall quickly? |
| `band_30_35` | the centre of the accepted envelope, and the Phase 2 top seed |
| `band_35_40` | the slow end: does a 38-second run go dead on screen? |
| `tail_tension` | the longest final three tiles inside the accepted envelope |
| `smooth` | the smallest worst mid-run gap: progression with no visible pause |
| `final_tile_high` | last tile in the arena's upper third |
| `final_tile_low` | last tile in the lower third |
| `contrast` | **rejected**, and completing: the visually questionable case |

## The bands are centres, not ranges

A band role asks for the *middle* of its range and not merely a member of it.
`candidate_score`'s runtime component peaks at 32.5 s and falls away either
side, so "the highest-scoring accepted seed completing in 25-30 s" is reliably
a seed completing in 29.9 s - the one furthest from the fast end the role was
created to test. The first run of this selector duly returned 30.0 s for the
fast band and 35.1 s for the slow one, which is two samples of the same middle
wearing different labels.

So each band names a centre and admits `BAND_HALF_WIDTH` either side of it, and
the score ranks only inside that window: 27.5, 32.5 and 37.5 seconds, plus or
minus one. Three genuinely different videos.

## The contrast case, and why it is not a broken run

The brief asks for "one mathematically valid but visually questionable seed".
Those two words pull in opposite directions and the selector honours both:
`contrast` must have `activated_tiles == total_tiles` - it really does light
every tile, so the mechanic is not being slandered - and must have failed at
least one acceptance condition. Among those, the one chosen is the one with the
largest `longest_body_gap_seconds`, because a mid-run dead zone is the failure
a viewer can actually see, as against, say, a tail share two points over the
line which nobody could name from the video.

It must also be **filmable**, at most `CONTRAST_MAX_SECONDS` long. Unbounded,
this role selects the population's single worst pathology: the first run of the
selector returned seed 45783, which lights all 51 tiles after 1,691 seconds. It
is mathematically valid and it is not a contrast case, because nothing about a
28-minute run says anything about a 32-second one, and rendering it would cost
more than the rest of the cast together. Bounded at 60 s the role gives what it
is for - a run somebody might plausibly have cut, that reads badly.

If the population contains no such seed the role is left unfilled and the
caller is told, rather than being handed a near-miss relabelled as a failure.

## Determinism

Selection is a pure function of the evaluation list. Ties break on seed, the
population is walked in seed order, and a role that finds no candidate yields
`None`. Re-running the same sweep therefore renders the same eight videos.

## Why the selector is handed tile indices and not runs

The two final-tile roles need geometry the evaluation does not carry, so an
earlier draft took `dict[seed, TileEscapeRun]`. At the 50,000-seed population
that is fifty thousand retained runs, about sixteen million live objects, and
the selection ran the machine out of memory before it selected anything. The
caller now passes `final_tiles: dict[seed, int]` - one integer per seed, which
the sweep already has in hand as it discards each run - plus the arena the
indices refer to. Selection is the same function; only its appetite changed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Sequence

from satisfying.tile_arena import Arena
from satisfying.tile_evaluator import (
    AcceptanceRule,
    DEFAULT_RULE,
    RunEvaluation,
    ScoreBreakdown,
    candidate_score,
    verdict,
)

__all__ = [
    "ROLES",
    "CastMember",
    "Cast",
    "final_tile_index",
    "final_tile_height_fraction",
    "select_cast",
]


@dataclass(frozen=True)
class CastMember:
    """One chosen seed, the role it fills and the numbers that chose it."""

    role: str
    reason: str
    seed: int
    accepted: bool
    completion_seconds: float | None
    score: float
    final_three_seconds: float | None
    final_tile_seconds: float | None
    longest_body_gap_seconds: float
    final_tile_index: int | None
    final_tile_height: float | None
    collisions: int
    failures: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "reason": self.reason,
            "seed": self.seed,
            "accepted": self.accepted,
            "completion_seconds": (
                None
                if self.completion_seconds is None
                else round(self.completion_seconds, 3)
            ),
            "score": round(self.score, 4),
            "final_three_seconds": (
                None
                if self.final_three_seconds is None
                else round(self.final_three_seconds, 3)
            ),
            "final_tile_seconds": (
                None
                if self.final_tile_seconds is None
                else round(self.final_tile_seconds, 3)
            ),
            "longest_body_gap_seconds": round(self.longest_body_gap_seconds, 3),
            "final_tile_index": self.final_tile_index,
            "final_tile_height": (
                None if self.final_tile_height is None else round(self.final_tile_height, 4)
            ),
            "collisions": self.collisions,
            "failures": list(self.failures),
        }


@dataclass(frozen=True)
class Cast:
    """The filled roles, the unfilled ones, and the population they came from."""

    members: tuple[CastMember, ...]
    unfilled: tuple[str, ...]
    population: int
    accepted: int

    @property
    def seeds(self) -> tuple[int, ...]:
        return tuple(member.seed for member in self.members)

    def as_dict(self) -> dict[str, Any]:
        return {
            "population": self.population,
            "accepted": self.accepted,
            "members": [member.as_dict() for member in self.members],
            "unfilled": list(self.unfilled),
        }


# How far either side of a band's centre a seed may complete and still fill
# that band's role. One second: wide enough that 50,000 seeds always populate
# every window, narrow enough that the three bands cannot collapse onto the
# same runtime.
BAND_HALF_WIDTH = 1.0

# The three band centres, in seconds.
BAND_CENTRES: dict[str, float] = {
    "band_25_30": 27.5,
    "band_30_35": 32.5,
    "band_35_40": 37.5,
}

# The longest a contrast run may be and still be worth rendering. Just under
# twice the accepted envelope's upper limit.
CONTRAST_MAX_SECONDS = 60.0

# Role name -> the sentence that says what rendering it is meant to settle.
ROLES: tuple[tuple[str, str], ...] = (
    ("band_25_30", "fast end of the envelope: 27.5 s +/- 1"),
    ("band_30_35", "centre of the envelope: 32.5 s +/- 1"),
    ("band_35_40", "slow end of the envelope: 37.5 s +/- 1"),
    ("tail_tension", "longest final three tiles among accepted runs"),
    ("smooth", "smallest worst mid-run gap among accepted runs"),
    ("final_tile_high", "last tile in the upper third of the arena"),
    ("final_tile_low", "last tile in the lower third of the arena"),
    (
        "contrast",
        "completes all tiles inside 60 s but fails acceptance: the "
        "questionable case",
    ),
)


def final_tile_index(run: Any) -> int | None:
    """Which tile lit last, by index. `None` if the run never lit them all.

    Called once per seed by the sweep, as the run is about to be discarded, so
    the selector never has to hold a population of runs.
    """
    if len(run.first_hit_time) != run.arena.total_tiles:
        return None
    latest_id = max(run.first_hit_time, key=run.first_hit_time.__getitem__)
    for tile in run.arena.tiles:
        if tile.tile_id == latest_id:
            return tile.index
    return None


def final_tile_height_fraction(arena: Arena, index: int | None) -> float | None:
    """The last tile's midpoint height, 0 at the arena floor and 1 at its top.

    Height rather than side number, because "the last tile was near the
    ceiling" is a statement about the frame - the viewer's eye has to travel up
    - while "the last tile was on side 9" is a statement about the indexing.
    """
    if index is None:
        return None
    if arena.circumradius <= 0.0:
        return None
    return (arena.tiles[index].midpoint[1] + arena.circumradius) / (
        2.0 * arena.circumradius
    )


@dataclass(frozen=True)
class _Row:
    """One population member with everything the roles need, computed once."""

    evaluation: RunEvaluation
    accepted: bool
    failures: tuple[str, ...]
    score: ScoreBreakdown
    final_index: int | None
    final_height: float | None


def _rows(
    evaluations: Sequence[RunEvaluation],
    final_tiles: dict[int, int | None],
    arena: Arena,
    rule: AcceptanceRule,
) -> list[_Row]:
    rows: list[_Row] = []
    for evaluation in evaluations:
        outcome = verdict(evaluation, rule)
        index = final_tiles.get(evaluation.seed)
        rows.append(
            _Row(
                evaluation=evaluation,
                accepted=outcome.accepted,
                failures=tuple(outcome.failures),
                score=candidate_score(evaluation, rule),
                final_index=index,
                final_height=final_tile_height_fraction(arena, index),
            )
        )
    rows.sort(key=lambda row: row.evaluation.seed)
    return rows


def _best(
    rows: Iterable[_Row],
    eligible: Callable[[_Row], bool],
    key: Callable[[_Row], float],
    taken: set[int],
) -> _Row | None:
    """The row maximising `key` among the eligible and not-yet-cast."""
    best: _Row | None = None
    best_key = -math.inf
    for row in rows:
        if row.evaluation.seed in taken or not eligible(row):
            continue
        value = key(row)
        if value > best_key:
            best, best_key = row, value
    return best


def select_cast(
    evaluations: Sequence[RunEvaluation],
    final_tiles: dict[int, int | None],
    arena: Arena,
    rule: AcceptanceRule = DEFAULT_RULE,
) -> Cast:
    """Fill each role from the population, one seed per role.

    `final_tiles` maps seed to the index of the tile that lit last, and is
    needed only by the two final-tile roles - a geometric question the
    evaluation does not carry. A seed missing from it simply cannot fill those
    two roles; every other role is decided from the evaluation alone.
    """
    rows = _rows(evaluations, final_tiles, arena, rule)
    by_seed = {row.evaluation.seed: row for row in rows}
    taken: set[int] = set()
    members: list[CastMember] = []
    unfilled: list[str] = []

    def accepted(row: _Row) -> bool:
        return row.accepted

    def near(centre: float) -> Callable[[_Row], bool]:
        def test(row: _Row) -> bool:
            seconds = row.evaluation.completion_seconds
            return (
                row.accepted
                and seconds is not None
                and abs(seconds - centre) <= BAND_HALF_WIDTH
            )

        return test

    def score_of(row: _Row) -> float:
        return row.score.total

    def complete(row: _Row) -> bool:
        return row.evaluation.activated_tiles == row.evaluation.total_tiles

    def is_contrast(row: _Row) -> bool:
        seconds = row.evaluation.completion_seconds
        return (
            (not row.accepted)
            and complete(row)
            and seconds is not None
            and seconds <= CONTRAST_MAX_SECONDS
        )

    choosers: dict[str, tuple[Callable[[_Row], bool], Callable[[_Row], float]]] = {
        "band_25_30": (near(BAND_CENTRES["band_25_30"]), score_of),
        "band_30_35": (near(BAND_CENTRES["band_30_35"]), score_of),
        "band_35_40": (near(BAND_CENTRES["band_35_40"]), score_of),
        "tail_tension": (
            accepted,
            lambda row: row.evaluation.final_three_seconds or 0.0,
        ),
        "smooth": (
            accepted,
            lambda row: -row.evaluation.longest_body_gap_seconds,
        ),
        "final_tile_high": (
            lambda row: (
                row.accepted
                and row.final_height is not None
                and row.final_height >= 2.0 / 3.0
            ),
            score_of,
        ),
        "final_tile_low": (
            lambda row: (
                row.accepted
                and row.final_height is not None
                and row.final_height <= 1.0 / 3.0
            ),
            score_of,
        ),
        "contrast": (
            is_contrast,
            lambda row: row.evaluation.longest_body_gap_seconds,
        ),
    }

    for role, reason in ROLES:
        eligible, key = choosers[role]
        row = _best(rows, eligible, key, taken)
        if row is None:
            unfilled.append(role)
            continue
        taken.add(row.evaluation.seed)
        members.append(
            CastMember(
                role=role,
                reason=reason,
                seed=row.evaluation.seed,
                accepted=row.accepted,
                completion_seconds=row.evaluation.completion_seconds,
                score=row.score.total,
                final_three_seconds=row.evaluation.final_three_seconds,
                final_tile_seconds=row.evaluation.final_tile_seconds,
                longest_body_gap_seconds=row.evaluation.longest_body_gap_seconds,
                final_tile_index=row.final_index,
                final_tile_height=row.final_height,
                collisions=row.evaluation.collisions,
                failures=row.failures,
            )
        )

    return Cast(
        members=tuple(members),
        unfilled=tuple(unfilled),
        population=len(rows),
        accepted=sum(1 for row in by_seed.values() if row.accepted),
    )

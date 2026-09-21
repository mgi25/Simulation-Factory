"""What makes one tile-escape run worth filming and another one not.

Phase 1 asked whether the mechanic works. It does. Phase 2 asks a narrower and
more commercial question: out of an arbitrary number of deterministic seeds,
can *selection alone* - no steering, no magnets, no extra balls - find runs that
hold a viewer for thirty seconds? This module is the instrument that decides.

It is deliberately Category 3-specific. There is no plugin registry, no metric
protocol and no generic scoring framework: a `TileEscapeRun` goes in and a
`RunEvaluation` of named floats comes out. A general evaluator would have to
guess what "the tail" means, and the whole point here is that the tail means
something exact - the clock from the 49th tile to the 51st.

## Everything is derived from the event stream

The only inputs are `run.collisions` (an ordered list of contacts, each flagged
new or duplicate) and `run.first_hit_time`. Nothing here re-simulates, samples
the trajectory or looks at a pixel. That matters for two reasons: the evaluation
of a run is as deterministic as the run, and a future renderer or audio pass can
be handed the same event stream and agree with these numbers by construction.

## The five groups, and why each one is separate

**Opening.** A viewer decides in two seconds. `first_collision_seconds` is when
anything happens at all and `early_activation_rate` is how fast the arena starts
lighting up. These are kept apart from the rest because a run can open superbly
and still rot in the middle.

**Progression.** Milestone clocks at 25/50/75/90/95% and at the last three
tiles. Milestones are counted in *tiles*, not in time, because "half the arena
is lit" is what the viewer sees; "half the runtime has passed" is not visible to
anyone.

**Stagnation.** The longest stretch with no new tile, *and where it sits*. A
nine-second gap at 47/51 is the ending doing its job. The same nine seconds at
20/51 is the video being switched off. One number cannot tell those apart, so
there are two: `longest_gap_seconds` and `longest_body_gap_seconds`, the latter
ignoring gaps that begin inside the final three tiles.

**Tail.** Four separate clocks - from 90%, from 95%, from n-2 and from n-1 - for
the same reason. The brief wants the ending to feel like a hunt rather than a
wait, and a hunt has a shape: some time at 49, a bit more at 50, and a last tile
that is the longest single wait of the run but not by a factor of ten.

**Collision quality.** How many contacts, how many of them were new, and how the
duplicate share moves across the run. Duplicates are not waste - they are the
sound and the motion - but a run whose last third is 98% duplicates is a run
where nothing is happening on screen.

## Periodic structure

Phase 1 found a real pathology: an even-sided arena has parallel walls and a
ball can bounce between two tiles for ever, escaping only by rounding error.
`longest_periodic_run` is the production-grade detector for the whole family,
not just the two-tile case - it asks, for every period up to `MAX_PERIOD`,
"what is the longest stretch of collisions in which each tile repeats the tile
`p` contacts earlier", which catches A-B-A-B, three- and four-tile cycles and
long repeated wall sequences with one loop. It is not chaos theory and is not
meant to be; it is a diagnostic that fires on the thing Phase 1 saw.

The same detector is run over side indices as well as tile indices, because a
ball can retrace a wall sequence while drifting across the tiles of each wall -
visually the same "it is stuck in a groove" reading, but invisible to a
tile-level check.

## Scoring comes last, and shows its working

`AcceptanceRule` is a list of named thresholds, each of which a run passes or
fails on its own, and `verdict` returns *which* ones failed. `candidate_score`
is a weighted sum of five components in [0, 1], and it returns the components
alongside the total - never a bare number. The thresholds in the defaults here
were not chosen in advance: they come from the percentiles of a 50,000-seed
sweep, and `docs/category3_tile_escape_phase2.md` states which percentile each
one is.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

from satisfying.tile_escape import TileEscapeRun

__all__ = [
    "MILESTONES",
    "MAX_PERIOD",
    "PeriodicPattern",
    "ConfinedWindow",
    "RunEvaluation",
    "AcceptanceRule",
    "Verdict",
    "ScoreBreakdown",
    "DEFAULT_RULE",
    "evaluate",
    "activation_curve",
    "longest_periodic_run",
    "longest_confined_window",
    "milestone_index",
    "percentile",
]


# Milestone name -> the fraction of tiles it marks, or a negative integer
# meaning "that many tiles short of the end". The negatives are absolute
# because the last three tiles are the thing Phase 2 is about, and at 51 tiles
# "95%" and "49 of 51" happen to be the same milestone - a coincidence of this
# tile count that a fraction-only scheme would hide.
MILESTONES: tuple[tuple[str, float | int], ...] = (
    ("first", 1),
    ("p25", 0.25),
    ("p50", 0.50),
    ("p75", 0.75),
    ("p90", 0.90),
    ("p95", 0.95),
    ("n_minus_2", -2),
    ("n_minus_1", -1),
    ("complete", -0),
)

# Longest repeat period the detector looks for. Eight covers every orbit the
# geometry can support with a small number of walls - the 16-gon's two-tile and
# four-tile orbits are periods 2 and 4 - and keeps the scan linear in practice.
MAX_PERIOD = 8

# The opening window, in seconds. Two seconds is roughly the time a viewer gives
# a Short before scrolling, and it is short enough that a run cannot pass it by
# being generally busy.
OPENING_WINDOW_SECONDS = 2.0

# A gap at or above this is "a period where nothing happened" for counting
# purposes. Set from the sweep: the median activation interval is well under a
# second, so three seconds is roughly ten times a normal wait.
LONG_GAP_SECONDS = 3.0


def milestone_index(spec: float | int, total: int) -> int:
    """Which activation number a milestone refers to, 1-based.

    A fraction rounds up, so "25% of 51" is the 13th tile and not the 12.75th.
    A non-positive integer counts back from the end: 0 is the last tile, -1 the
    one before it.
    """
    if isinstance(spec, int) and spec <= 0:
        return max(1, total + spec)
    if isinstance(spec, int):
        return max(1, min(total, spec))
    return max(1, min(total, math.ceil(spec * total)))


def percentile(values: Sequence[float], fraction: float) -> float:
    """Nearest-rank percentile over a sequence that is already sorted.

    Nearest-rank rather than interpolated, so every reported percentile is a
    value some seed actually produced. A p90 of 77.6 s that no run achieved is
    a worse number to hand a production decision than one that is a real run.
    """
    if not values:
        return math.nan
    rank = max(1, math.ceil(fraction * len(values)))
    return values[min(len(values), rank) - 1]


@dataclass(frozen=True)
class PeriodicPattern:
    """A stretch of collisions that repeats with a fixed period.

    `length` counts collisions in the whole repeating stretch, including the
    first copy, so a perfect A-B-A-B of four contacts is period 2, length 4,
    repeats 2. An empty pattern is period 0.
    """

    period: int = 0
    length: int = 0
    repeats: int = 0
    start_index: int = -1
    start_seconds: float = 0.0
    members: tuple[int, ...] = ()

    @property
    def found(self) -> bool:
        return self.period > 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "period": self.period,
            "length": self.length,
            "repeats": self.repeats,
            "start_index": self.start_index,
            "start_seconds": round(self.start_seconds, 3),
            "members": list(self.members),
        }


@dataclass(frozen=True)
class ConfinedWindow:
    """The longest run of collisions touching at most `distinct` surfaces."""

    distinct: int = 0
    length: int = 0
    start_index: int = -1
    start_seconds: float = 0.0
    members: tuple[int, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "distinct": self.distinct,
            "length": self.length,
            "start_index": self.start_index,
            "start_seconds": round(self.start_seconds, 3),
            "members": list(self.members),
        }


def longest_periodic_run(
    values: Sequence[int],
    times: Sequence[float] | None = None,
    max_period: int = MAX_PERIOD,
    min_period: int = 1,
    min_repeats: int = 2,
) -> PeriodicPattern:
    """The longest stretch in which every entry equals the one `p` places back.

    Scans every period from `min_period` to `max_period` and keeps the longest
    stretch that completes at least `min_repeats` copies. Ties go to the
    **smaller** period, because a true A-B-A-B also satisfies period 4 - the
    same positions match, two fewer of them, so the stretch comes out the same
    length - and reporting it as a four-cycle would misname the pathology.

    Period 1 is in range by default even though two consecutive contacts with
    the same tile cannot happen in this simulation: if it ever fires, the skin
    nudge has failed, and that is worth catching rather than assuming away.
    """
    n = len(values)
    best = PeriodicPattern()
    for period in range(max(1, min_period), max_period + 1):
        if n < period * min_repeats:
            break
        run = 0
        for i in range(period, n + 1):
            if i < n and values[i] == values[i - period]:
                run += 1
                continue
            # The matched positions ended at i-1, so the repeating stretch is
            # those `run` entries plus the one period of originals before them.
            if run >= period * (min_repeats - 1):
                length = run + period
                start = i - length
                if length > best.length or (
                    length == best.length and best.found and period < best.period
                ):
                    best = PeriodicPattern(
                        period=period,
                        length=length,
                        repeats=length // period,
                        start_index=start,
                        start_seconds=(times[start] if times else 0.0),
                        members=tuple(sorted(set(values[start : start + period]))),
                    )
            run = 0
    return best


def longest_confined_window(
    values: Sequence[int],
    distinct: int,
    times: Sequence[float] | None = None,
) -> ConfinedWindow:
    """Longest run of consecutive entries drawn from at most `distinct` values.

    Phase 1 has the same sliding window without the position; the position is
    what turns "there was a 34-collision two-tile loop somewhere" into "there
    was one, and it started at 46.5 s", which is the difference between a
    statistic and a diagnosis.
    """
    best = ConfinedWindow(distinct=distinct)
    counts: dict[int, int] = {}
    left = 0
    for right, value in enumerate(values):
        counts[value] = counts.get(value, 0) + 1
        while len(counts) > distinct:
            leaving = values[left]
            counts[leaving] -= 1
            if counts[leaving] == 0:
                del counts[leaving]
            left += 1
        length = right - left + 1
        if length > best.length:
            best = ConfinedWindow(
                distinct=distinct,
                length=length,
                start_index=left,
                start_seconds=(times[left] if times else 0.0),
                members=tuple(sorted(counts)),
            )
    return best


@dataclass(frozen=True)
class RunEvaluation:
    """Every number Phase 2 judges a run by, with nothing folded together."""

    seed: int
    total_tiles: int
    activated_tiles: int
    completed: bool
    completion_seconds: float | None
    end_seconds: float
    stop_reason: str

    # Opening.
    first_collision_seconds: float | None
    first_activation_seconds: float | None
    opening_window_seconds: float
    activations_in_opening: int
    early_activation_rate: float

    # Progression. Milestone name -> seconds, or None if never reached.
    milestones: dict[str, float | None]

    # Stagnation.
    longest_gap_seconds: float
    longest_gap_start_seconds: float
    longest_gap_after_tiles: int
    longest_gap_progress: float
    long_gap_count: int
    long_gap_threshold_seconds: float
    longest_body_gap_seconds: float
    longest_body_gap_after_tiles: int
    median_activation_interval: float

    # Tail.
    tail_from_90_seconds: float | None
    tail_from_95_seconds: float | None
    tail_from_third_last_seconds: float | None
    tail_from_second_last_seconds: float | None
    final_three_seconds: float | None
    final_tile_seconds: float | None
    tail_share_from_90: float | None
    final_tile_over_median_interval: float | None

    # Collision quality.
    collisions: int
    new_hits: int
    duplicate_hits: int
    collisions_per_second: float
    duplicate_share: float
    duplicate_share_thirds: tuple[float, float, float]
    duplicates_per_new_thirds: tuple[float | None, float | None, float | None]
    max_hits_on_one_tile: int
    untouched_tiles: tuple[str, ...]

    # Periodic structure.
    longest_two_tile_run: ConfinedWindow
    longest_four_tile_run: ConfinedWindow
    longest_alternation: PeriodicPattern
    longest_tile_cycle: PeriodicPattern
    longest_side_cycle: PeriodicPattern

    def as_dict(self) -> dict[str, Any]:
        """A JSON-serialisable form. Rounded for reading, never for deciding."""

        def r(value: float | None, places: int = 3) -> float | None:
            return None if value is None else round(value, places)

        return {
            "seed": self.seed,
            "total_tiles": self.total_tiles,
            "activated_tiles": self.activated_tiles,
            "completed": self.completed,
            "completion_seconds": r(self.completion_seconds),
            "end_seconds": r(self.end_seconds),
            "stop_reason": self.stop_reason,
            "first_collision_seconds": r(self.first_collision_seconds),
            "first_activation_seconds": r(self.first_activation_seconds),
            "opening_window_seconds": self.opening_window_seconds,
            "activations_in_opening": self.activations_in_opening,
            "early_activation_rate": r(self.early_activation_rate),
            "milestones": {k: r(v) for k, v in self.milestones.items()},
            "longest_gap_seconds": r(self.longest_gap_seconds),
            "longest_gap_start_seconds": r(self.longest_gap_start_seconds),
            "longest_gap_after_tiles": self.longest_gap_after_tiles,
            "longest_gap_progress": r(self.longest_gap_progress, 4),
            "long_gap_count": self.long_gap_count,
            "long_gap_threshold_seconds": self.long_gap_threshold_seconds,
            "longest_body_gap_seconds": r(self.longest_body_gap_seconds),
            "longest_body_gap_after_tiles": self.longest_body_gap_after_tiles,
            "median_activation_interval": r(self.median_activation_interval),
            "tail_from_90_seconds": r(self.tail_from_90_seconds),
            "tail_from_95_seconds": r(self.tail_from_95_seconds),
            "tail_from_third_last_seconds": r(self.tail_from_third_last_seconds),
            "tail_from_second_last_seconds": r(self.tail_from_second_last_seconds),
            "final_three_seconds": r(self.final_three_seconds),
            "final_tile_seconds": r(self.final_tile_seconds),
            "tail_share_from_90": r(self.tail_share_from_90, 4),
            "final_tile_over_median_interval": r(self.final_tile_over_median_interval, 2),
            "collisions": self.collisions,
            "new_hits": self.new_hits,
            "duplicate_hits": self.duplicate_hits,
            "collisions_per_second": r(self.collisions_per_second),
            "duplicate_share": r(self.duplicate_share, 4),
            "duplicate_share_thirds": [round(v, 4) for v in self.duplicate_share_thirds],
            "duplicates_per_new_thirds": [
                None if v is None else round(v, 3) for v in self.duplicates_per_new_thirds
            ],
            "max_hits_on_one_tile": self.max_hits_on_one_tile,
            "untouched_tiles": list(self.untouched_tiles),
            "longest_two_tile_run": self.longest_two_tile_run.as_dict(),
            "longest_four_tile_run": self.longest_four_tile_run.as_dict(),
            "longest_alternation": self.longest_alternation.as_dict(),
            "longest_tile_cycle": self.longest_tile_cycle.as_dict(),
            "longest_side_cycle": self.longest_side_cycle.as_dict(),
        }


def activation_curve(run: TileEscapeRun) -> tuple[tuple[float, int], ...]:
    """The progress bar as data: `(seconds, tiles lit)` at every activation.

    Starts at `(0.0, 0)` so a plot begins at the origin rather than at the first
    tile, and ends at the run's end time so an incomplete run shows its dead
    tail instead of stopping at the last thing that happened. Between two points
    the count is constant - this is a step function, and drawing it as one is
    the difference between reading a stall and smoothing it away.
    """
    points: list[tuple[float, int]] = [(0.0, 0)]
    for time in sorted(run.first_hit_time.values()):
        points.append((time, len(points)))
    if points[-1][0] < run.end_time:
        points.append((run.end_time, points[-1][1]))
    return tuple(points)


def _thirds(count: int) -> tuple[int, int]:
    """Split `count` collisions into three near-equal consecutive blocks."""
    return count // 3, (2 * count) // 3


def evaluate(
    run: TileEscapeRun,
    opening_window_seconds: float = OPENING_WINDOW_SECONDS,
    long_gap_seconds: float = LONG_GAP_SECONDS,
) -> RunEvaluation:
    """Reduce one run to its named metrics. Pure; no simulation, no sampling."""
    total = run.total_tiles
    times = sorted(run.first_hit_time.values())
    end = run.end_time
    completion = run.completion_time

    # --- milestones -------------------------------------------------------
    milestones: dict[str, float | None] = {}
    for name, spec in MILESTONES:
        index = milestone_index(spec, total)
        milestones[name] = times[index - 1] if len(times) >= index else None

    def at(name: str) -> float | None:
        return milestones.get(name)

    # --- opening ----------------------------------------------------------
    first_collision = run.collisions[0].time if run.collisions else None
    first_activation = times[0] if times else None
    in_opening = sum(1 for t in times if t <= opening_window_seconds)
    early_rate = in_opening / opening_window_seconds if opening_window_seconds else 0.0

    # --- stagnation -------------------------------------------------------
    # One gap per activation (from the previous activation, or from t=0 for the
    # first), plus the tail from the last activation to the end of the run. The
    # tail is a gap: for an incomplete run it is the whole of the dead time.
    gaps: list[tuple[float, float, int]] = []  # (length, start, tiles lit at start)
    previous = 0.0
    for lit, time in enumerate(times):
        gaps.append((time - previous, previous, lit))
        previous = time
    if end > previous:
        gaps.append((end - previous, previous, len(times)))

    longest = max(gaps, key=lambda g: g[0]) if gaps else (0.0, 0.0, 0)
    # A gap that begins once only the last three tiles are left is the ending,
    # not a stall. `body` is everything before that.
    body_gaps = [g for g in gaps if g[2] < total - 3]
    body = max(body_gaps, key=lambda g: g[0]) if body_gaps else (0.0, 0.0, 0)
    long_gaps = sum(1 for g in gaps if g[0] >= long_gap_seconds)
    intervals = sorted(g[0] for g in gaps[: len(times)])
    median_interval = intervals[len(intervals) // 2] if intervals else 0.0

    # --- tail -------------------------------------------------------------
    def since(name: str) -> float | None:
        start = at(name)
        if start is None or completion is None:
            return None
        return completion - start

    third_last = times[total - 4] if len(times) >= total - 3 else None
    final_three = (
        None if (third_last is None or completion is None) else completion - third_last
    )
    final_tile = since("n_minus_1")
    tail_90 = since("p90")

    # --- collision quality ------------------------------------------------
    collisions = run.collisions
    new_hits = sum(1 for c in collisions if c.is_new)
    duplicates = len(collisions) - new_hits
    cut_a, cut_b = _thirds(len(collisions))
    blocks = (collisions[:cut_a], collisions[cut_a:cut_b], collisions[cut_b:])
    shares: list[float] = []
    per_new: list[float | None] = []
    for block in blocks:
        block_new = sum(1 for c in block if c.is_new)
        block_dup = len(block) - block_new
        shares.append(block_dup / len(block) if block else 0.0)
        per_new.append(block_dup / block_new if block_new else None)

    # --- periodic structure -----------------------------------------------
    tile_indices = [c.tile_index for c in collisions]
    side_indices = [c.side for c in collisions]
    hit_times = [c.time for c in collisions]
    alternation = longest_periodic_run(
        tile_indices, hit_times, max_period=2, min_period=2
    )

    return RunEvaluation(
        seed=run.seed,
        total_tiles=total,
        activated_tiles=run.activated_tiles,
        completed=run.completed,
        completion_seconds=completion,
        end_seconds=end,
        stop_reason=run.stop_reason,
        first_collision_seconds=first_collision,
        first_activation_seconds=first_activation,
        opening_window_seconds=opening_window_seconds,
        activations_in_opening=in_opening,
        early_activation_rate=early_rate,
        milestones=milestones,
        longest_gap_seconds=longest[0],
        longest_gap_start_seconds=longest[1],
        longest_gap_after_tiles=longest[2],
        longest_gap_progress=longest[2] / total if total else 0.0,
        long_gap_count=long_gaps,
        long_gap_threshold_seconds=long_gap_seconds,
        longest_body_gap_seconds=body[0],
        longest_body_gap_after_tiles=body[2],
        median_activation_interval=median_interval,
        tail_from_90_seconds=tail_90,
        tail_from_95_seconds=since("p95"),
        tail_from_third_last_seconds=since("n_minus_2"),
        tail_from_second_last_seconds=final_tile,
        final_three_seconds=final_three,
        final_tile_seconds=final_tile,
        tail_share_from_90=(
            None if (tail_90 is None or not completion) else tail_90 / completion
        ),
        final_tile_over_median_interval=(
            None
            if (final_tile is None or median_interval <= 0.0)
            else final_tile / median_interval
        ),
        collisions=len(collisions),
        new_hits=new_hits,
        duplicate_hits=duplicates,
        collisions_per_second=(len(collisions) / end if end > 0 else 0.0),
        duplicate_share=(duplicates / len(collisions) if collisions else 0.0),
        duplicate_share_thirds=(shares[0], shares[1], shares[2]),
        duplicates_per_new_thirds=(per_new[0], per_new[1], per_new[2]),
        max_hits_on_one_tile=(max(run.hits_by_tile.values()) if run.hits_by_tile else 0),
        untouched_tiles=run.unhit_tiles(),
        longest_two_tile_run=longest_confined_window(tile_indices, 2, hit_times),
        longest_four_tile_run=longest_confined_window(tile_indices, 4, hit_times),
        longest_alternation=alternation,
        longest_tile_cycle=longest_periodic_run(tile_indices, hit_times),
        longest_side_cycle=longest_periodic_run(side_indices, hit_times),
    )


# --------------------------------------------------------------------------
# Acceptance: named thresholds, each of which a run passes or fails on its own.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AcceptanceRule:
    """The production envelope, as separable conditions rather than a score.

    Every default below is a percentile of the 50,000-seed sweep recorded in
    `docs/category3_tile_escape_phase2.md`, not a preference. The brief's own
    envelope - 25-40 s, meaningful activity immediately, no mid-run dead zone,
    a last tile that is longer than an ordinary one but not punishing - maps
    onto these eight conditions one for one.
    """

    min_duration: float = 25.0
    max_duration: float = 40.0
    max_first_collision: float = 1.0
    min_opening_activations: int = 3
    max_body_gap: float = 4.0
    min_final_tile: float = 1.5
    max_final_tile: float = 9.0
    max_final_three: float = 14.0
    max_tail_share_from_90: float = 0.40
    max_two_tile_run: int = 4
    max_cycle_length: int = 12

    def as_dict(self) -> dict[str, Any]:
        return {
            "min_duration": self.min_duration,
            "max_duration": self.max_duration,
            "max_first_collision": self.max_first_collision,
            "min_opening_activations": self.min_opening_activations,
            "max_body_gap": self.max_body_gap,
            "min_final_tile": self.min_final_tile,
            "max_final_tile": self.max_final_tile,
            "max_final_three": self.max_final_three,
            "max_tail_share_from_90": self.max_tail_share_from_90,
            "max_two_tile_run": self.max_two_tile_run,
            "max_cycle_length": self.max_cycle_length,
        }


DEFAULT_RULE = AcceptanceRule()


@dataclass(frozen=True)
class Verdict:
    """Accepted or not, and - always - exactly which conditions decided it."""

    accepted: bool
    failures: tuple[str, ...] = ()
    passes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "failures": list(self.failures),
            "passes": list(self.passes),
        }


def verdict(evaluation: RunEvaluation, rule: AcceptanceRule = DEFAULT_RULE) -> Verdict:
    """Apply every condition and report all of them, not the first failure.

    Reporting all of them is the point: a seed that fails only `max_body_gap` by
    a tenth of a second is a different object from one that fails five
    conditions, and a first-failure-wins check makes the two look the same.
    """
    checks: list[tuple[str, bool]] = []

    def check(name: str, ok: bool) -> None:
        checks.append((name, bool(ok)))

    finish = evaluation.completion_seconds
    check("completes", evaluation.completed)
    check("duration_at_least_min", finish is not None and finish >= rule.min_duration)
    check("duration_at_most_max", finish is not None and finish <= rule.max_duration)
    check(
        "opens_immediately",
        evaluation.first_collision_seconds is not None
        and evaluation.first_collision_seconds <= rule.max_first_collision,
    )
    check(
        "opening_is_busy",
        evaluation.activations_in_opening >= rule.min_opening_activations,
    )
    check("no_mid_run_dead_zone", evaluation.longest_body_gap_seconds <= rule.max_body_gap)
    check(
        "last_tile_has_tension",
        evaluation.final_tile_seconds is not None
        and evaluation.final_tile_seconds >= rule.min_final_tile,
    )
    check(
        "last_tile_is_not_a_wait",
        evaluation.final_tile_seconds is not None
        and evaluation.final_tile_seconds <= rule.max_final_tile,
    )
    check(
        "final_three_are_a_hunt",
        evaluation.final_three_seconds is not None
        and evaluation.final_three_seconds <= rule.max_final_three,
    )
    check(
        "tail_is_proportionate",
        evaluation.tail_share_from_90 is not None
        and evaluation.tail_share_from_90 <= rule.max_tail_share_from_90,
    )
    check("no_two_tile_loop", evaluation.longest_two_tile_run.length <= rule.max_two_tile_run)
    check("no_long_cycle", evaluation.longest_tile_cycle.length <= rule.max_cycle_length)

    failures = tuple(name for name, ok in checks if not ok)
    passes = tuple(name for name, ok in checks if ok)
    return Verdict(accepted=not failures, failures=failures, passes=passes)


@dataclass(frozen=True)
class ScoreBreakdown:
    """A total in [0, 1] and the five components it is the weighted sum of.

    The total exists to *rank* runs that have already passed `verdict`; it is
    not an acceptance test and nothing is accepted because of it. That division
    is deliberate - a threshold you can argue with beats a number you cannot.
    """

    total: float
    components: dict[str, float] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": round(self.total, 4),
            "components": {k: round(v, 4) for k, v in self.components.items()},
            "weights": dict(self.weights),
        }


# The five things the brief says a good run is, and what each is worth. They add
# to 1.0.
#
# The weights follow the *measured variance* of each component over the
# 50,000-seed sweep, not a prior opinion about what matters. Runtime, tail
# tension and stagnation are where seeds actually differ, so they carry 0.90
# between them. Opening and density carry 0.05 each because at 17 x 3 with
# gravity 0 they barely vary: every one of 49,899 completing seeds lit its first
# tile between 0.12 s and 0.20 s and lit at least three in the first two
# seconds. Weighting a near-constant heavily would add the same number to every
# score and rank nothing - so they stay in as guards against a future
# configuration that breaks them, at a weight that says so.
SCORE_WEIGHTS: dict[str, float] = {
    "runtime": 0.35,
    "tail_tension": 0.30,
    "no_stagnation": 0.25,
    "opening": 0.05,
    "event_density": 0.05,
}

# The runtime the score treats as ideal, and the half-width over which it falls
# to zero. 32 s is the middle of the brief's stated "low/mid 30-second" target;
# 9 s puts the zeros just outside the 25-40 s acceptance window, so the score
# discriminates across the whole of the accepted range instead of saturating.
IDEAL_DURATION = 32.0
DURATION_TOLERANCE = 9.0

# The final tile's ideal length, in seconds, and its tolerance. A last tile
# under a second is over before it registers; the tolerance is set so the score
# reaches zero exactly at `AcceptanceRule.max_final_tile`, which keeps the rank
# and the rule from disagreeing at the boundary.
IDEAL_FINAL_TILE = 4.0
FINAL_TILE_TOLERANCE = 5.0

# Collisions per second the score treats as ideal, and the band outside which it
# is worth nothing. At 60 fps, 3/s is one impact every twenty frames and 9/s is
# one every seven: below the first the arena feels empty, above the second the
# impacts stop being separable events on screen and a procedural audio pass
# turns into a buzz. Phase 1 measured 1.3/s at its specified config and called
# it too sparse, which is the low end of this reasoning seen from outside.
IDEAL_RATE = 6.0
RATE_TOLERANCE = 3.0


def _tent(value: float | None, ideal: float, tolerance: float) -> float:
    """1.0 at `ideal`, falling linearly to 0.0 at `ideal +/- tolerance`."""
    if value is None or tolerance <= 0.0:
        return 0.0
    return max(0.0, 1.0 - abs(value - ideal) / tolerance)


def _decay(value: float, zero_at: float) -> float:
    """1.0 at 0, falling linearly to 0.0 at `zero_at`."""
    if zero_at <= 0.0:
        return 0.0
    return max(0.0, 1.0 - value / zero_at)


def candidate_score(
    evaluation: RunEvaluation, rule: AcceptanceRule = DEFAULT_RULE
) -> ScoreBreakdown:
    """Rank an accepted run. Always returns the components beside the total."""
    components = {
        "runtime": _tent(evaluation.completion_seconds, IDEAL_DURATION, DURATION_TOLERANCE),
        "tail_tension": _tent(
            evaluation.final_tile_seconds, IDEAL_FINAL_TILE, FINAL_TILE_TOLERANCE
        ),
        "no_stagnation": _decay(evaluation.longest_body_gap_seconds, rule.max_body_gap),
        "opening": min(
            1.0,
            evaluation.activations_in_opening / max(1, 2 * rule.min_opening_activations),
        ),
        "event_density": _tent(evaluation.collisions_per_second, IDEAL_RATE, RATE_TOLERANCE),
    }
    total = sum(components[name] * SCORE_WEIGHTS[name] for name in SCORE_WEIGHTS)
    return ScoreBreakdown(total=total, components=components, weights=dict(SCORE_WEIGHTS))

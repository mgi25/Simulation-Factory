"""Running the evaluator over tens of thousands of seeds, and what comes back.

`satisfying.tile_evaluator` judges one run. This judges a population: it runs a
seed range, reduces each run to a `RunEvaluation`, throws the run away, and
aggregates. Throwing the run away is the only reason 50,000 seeds fit in
memory - a single 51-tile run carries a few hundred `Collision` objects and a
few hundred `Flight`s, and fifty thousand of those do not.

## The one fact that shapes this whole module

With `gravity = 0` the ball's path is a *geometric* object: the release point
and heading fix the sequence of walls, and `speed` only sets how fast that
sequence is traversed. Doubling the speed does not change which tile is hit
tenth; it halves the clock. `verify_speed_invariance` checks that as a
measurement rather than trusting the algebra, comparing collision sequences and
completion-time ratios across speeds, and it is the reason the speed sweep in
`docs/category3_tile_escape_phase2.md` can report an exact curve instead of a
noisy one.

Two consequences worth stating plainly, because they save work and prevent a
mistake:

- **Speed and arena scale are the same dial.** A run's clock is (collisions x
  mean chord) / speed, and scaling the arena scales the mean chord. Halving the
  circumradius and halving the speed give the same video at the same length.
  Only the ratio `speed / circumradius` is physical, so a Phase 2 that tuned
  both would be counting one lever twice.
- **A seed's shape is speed-independent.** Collision count, tile order,
  stagnation measured in collisions, and every periodic pattern are properties
  of the seed alone. Speed moves *all* of a seed's clocks by one factor, so it
  cannot fix a badly-shaped run and cannot break a well-shaped one - it can only
  put the whole run in or out of the runtime envelope.

## Percentiles are nearest-rank

Every percentile here is a value some seed actually produced. Interpolated
percentiles invent a p90 that no run achieved, which is the wrong thing to hand
a production decision that ends in "film this seed".
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from satisfying.tile_arena import Arena, polygon_arena
from satisfying.tile_escape import TileEscapeConfig, simulate
from satisfying.tile_evaluator import (
    AcceptanceRule,
    DEFAULT_RULE,
    RunEvaluation,
    ScoreBreakdown,
    activation_curve,
    candidate_score,
    evaluate,
    percentile,
    verdict,
)

__all__ = [
    "PHASE2_ARENA",
    "PHASE2_CONFIG",
    "Candidate",
    "sweep",
    "distribution",
    "population_report",
    "activation_curve_percentiles",
    "shortlist",
    "failure_census",
    "verify_speed_invariance",
    "rescale_to_speed",
]


def phase2_arena() -> Arena:
    """17 sides x 3 tiles = 51, the locked Phase 2 geometry."""
    return polygon_arena(sides=17, tiles_per_side=3, circumradius=10.0)


# The locked base configuration. `duration` is effectively unbounded and the
# real stop is `max_collisions`, because a *time* cap censors the population
# differently at every speed while a collision cap censors it identically - and
# at gravity 0 the collision sequence is the thing that does not depend on
# speed. 8000 collisions is about 24 minutes of screen time at speed 60: far
# past any run that could ever be filmed, so nothing usable is being cut off.
PHASE2_CONFIG = TileEscapeConfig(
    speed=60.0,
    gravity=0.0,
    restitution=1.0,
    ball_radius=0.45,
    duration=1.0e6,
    max_collisions=8000,
)

PHASE2_ARENA = phase2_arena()


@dataclass(frozen=True)
class Candidate:
    """One shortlisted seed: its evaluation, why it passed, and its rank score."""

    evaluation: RunEvaluation
    verdict: Any
    score: ScoreBreakdown

    @property
    def seed(self) -> int:
        return self.evaluation.seed

    def as_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "score": self.score.as_dict(),
            "verdict": self.verdict.as_dict(),
            "evaluation": self.evaluation.as_dict(),
        }


def sweep(
    seeds: Iterable[int],
    config: TileEscapeConfig = PHASE2_CONFIG,
    arena: Arena | None = None,
) -> list[RunEvaluation]:
    """Simulate and evaluate every seed, keeping only the evaluations."""
    arena = arena if arena is not None else PHASE2_ARENA
    return [evaluate(simulate(seed, config, arena)) for seed in seeds]


def distribution(values: Sequence[float]) -> dict[str, Any]:
    """Count, mean and the nearest-rank percentiles Phase 2 reports everywhere."""
    ordered = sorted(v for v in values if v is not None and not math.isnan(v))
    if not ordered:
        return {"count": 0}
    return {
        "count": len(ordered),
        "mean": round(sum(ordered) / len(ordered), 3),
        "min": round(ordered[0], 3),
        "p10": round(percentile(ordered, 0.10), 3),
        "p25": round(percentile(ordered, 0.25), 3),
        "p50": round(percentile(ordered, 0.50), 3),
        "p75": round(percentile(ordered, 0.75), 3),
        "p90": round(percentile(ordered, 0.90), 3),
        "p95": round(percentile(ordered, 0.95), 3),
        "p99": round(percentile(ordered, 0.99), 3),
        "max": round(ordered[-1], 3),
    }


def _histogram(values: Sequence[int], top: int = 12) -> list[tuple[int, int]]:
    counts: dict[int, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top]


def failure_census(evaluations: Sequence[RunEvaluation]) -> dict[str, Any]:
    """What the unusable runs look like, split by *why* they are unusable.

    Two populations, and they are not the same problem. A run that never
    completes is a physics outcome; a run that completes in 94 s is a pacing
    outcome. Lumping them gives a single "bad seed" rate that hides which of the
    two a fix would have to attack.
    """
    total = len(evaluations)
    incomplete = [e for e in evaluations if not e.completed]
    complete = [e for e in evaluations if e.completed]

    missing_sides: dict[int, int] = {}
    for e in incomplete:
        for tile_id in e.untouched_tiles:
            side = int(tile_id.split("_")[1]) // 3
            missing_sides[side] = missing_sides.get(side, 0) + 1

    def share(predicate) -> dict[str, Any]:
        hits = [e for e in complete if predicate(e)]
        return {
            "count": len(hits),
            "share_of_all": round(len(hits) / total, 5) if total else 0.0,
            "example_seeds": [e.seed for e in hits[:5]],
        }

    return {
        "seeds": total,
        "incomplete": {
            "count": len(incomplete),
            "share_of_all": round(len(incomplete) / total, 5) if total else 0.0,
            "stop_reasons": {
                reason: sum(1 for e in incomplete if e.stop_reason == reason)
                for reason in sorted({e.stop_reason for e in incomplete})
            },
            "tiles_missing": distribution(
                [e.total_tiles - e.activated_tiles for e in incomplete]
            ),
            "missing_tiles_by_side": sorted(missing_sides.items()),
            "example_seeds": [e.seed for e in incomplete[:10]],
        },
        "completed_but_unusable": {
            "too_slow_over_40s": share(lambda e: e.completion_seconds > 40.0),
            "too_slow_over_60s": share(lambda e: e.completion_seconds > 60.0),
            "too_fast_under_25s": share(lambda e: e.completion_seconds < 25.0),
            "mid_run_dead_zone_over_4s": share(lambda e: e.longest_body_gap_seconds > 4.0),
            "mid_run_dead_zone_over_8s": share(lambda e: e.longest_body_gap_seconds > 8.0),
            "final_tile_over_10s": share(
                lambda e: (e.final_tile_seconds or 0.0) > 10.0
            ),
            "final_tile_under_1s": share(
                lambda e: (e.final_tile_seconds or 0.0) < 1.0
            ),
            "two_tile_loop_over_6": share(lambda e: e.longest_two_tile_run.length > 6),
        },
    }


def population_report(
    evaluations: Sequence[RunEvaluation],
    rule: AcceptanceRule = DEFAULT_RULE,
    config: TileEscapeConfig = PHASE2_CONFIG,
    arena: Arena | None = None,
) -> dict[str, Any]:
    """Everything Part 1 of the brief asks for, over one seed population."""
    arena = arena if arena is not None else PHASE2_ARENA
    complete = [e for e in evaluations if e.completed]
    verdicts = [verdict(e, rule) for e in evaluations]
    accepted = sum(1 for v in verdicts if v.accepted)

    failure_counts: dict[str, int] = {}
    for v in verdicts:
        for name in v.failures:
            failure_counts[name] = failure_counts.get(name, 0) + 1

    def over(field: str, source: Sequence[RunEvaluation] | None = None) -> dict[str, Any]:
        rows = complete if source is None else source
        return distribution([getattr(e, field) for e in rows])

    milestone_names = list(complete[0].milestones) if complete else []
    return {
        "seeds": len(evaluations),
        "arena": {
            "sides": arena.sides,
            "tiles_per_side": arena.tiles_per_side,
            "total_tiles": arena.total_tiles,
            "circumradius": arena.circumradius,
            "tile_length": round(arena.tile_length, 6),
        },
        "config": config.as_dict(),
        "completion": {
            "completed": len(complete),
            "completion_rate": round(len(complete) / len(evaluations), 5)
            if evaluations
            else 0.0,
            "seconds": over("completion_seconds"),
            "collisions": over("collisions"),
            "collisions_per_second": over("collisions_per_second"),
            "duplicate_share": over("duplicate_share"),
            "max_hits_on_one_tile": over("max_hits_on_one_tile"),
        },
        "opening": {
            "first_collision_seconds": over("first_collision_seconds"),
            "activations_in_first_2s": over("activations_in_opening"),
        },
        "milestones": {
            name: distribution([e.milestones[name] for e in complete if e.milestones[name] is not None])
            for name in milestone_names
        },
        "stagnation": {
            "longest_gap_seconds": over("longest_gap_seconds"),
            "longest_body_gap_seconds": over("longest_body_gap_seconds"),
            "long_gap_count": over("long_gap_count"),
            "median_activation_interval": over("median_activation_interval"),
            "longest_gap_progress": over("longest_gap_progress"),
        },
        "tail": {
            "from_90_percent": over("tail_from_90_seconds"),
            "from_95_percent": over("tail_from_95_seconds"),
            "from_third_last": over("tail_from_third_last_seconds"),
            "from_second_last": over("tail_from_second_last_seconds"),
            "final_three_seconds": over("final_three_seconds"),
            "final_tile_seconds": over("final_tile_seconds"),
            "tail_share_from_90": over("tail_share_from_90"),
            "final_tile_over_median_interval": over("final_tile_over_median_interval"),
        },
        "periodic": {
            "longest_two_tile_run": distribution(
                [float(e.longest_two_tile_run.length) for e in evaluations]
            ),
            "longest_four_tile_run": distribution(
                [float(e.longest_four_tile_run.length) for e in evaluations]
            ),
            "longest_alternation": distribution(
                [float(e.longest_alternation.length) for e in evaluations]
            ),
            "longest_tile_cycle": distribution(
                [float(e.longest_tile_cycle.length) for e in evaluations]
            ),
            "longest_side_cycle": distribution(
                [float(e.longest_side_cycle.length) for e in evaluations]
            ),
            "two_tile_run_histogram": _histogram(
                [e.longest_two_tile_run.length for e in evaluations]
            ),
            "tile_cycle_period_histogram": _histogram(
                [e.longest_tile_cycle.period for e in evaluations]
            ),
            "side_cycle_period_histogram": _histogram(
                [e.longest_side_cycle.period for e in evaluations]
            ),
            "worst_two_tile_seeds": [
                {
                    "seed": e.seed,
                    "length": e.longest_two_tile_run.length,
                    "start_seconds": round(e.longest_two_tile_run.start_seconds, 3),
                    "tiles": list(e.longest_two_tile_run.members),
                }
                for e in sorted(
                    evaluations, key=lambda e: -e.longest_two_tile_run.length
                )[:10]
            ],
            "worst_tile_cycle_seeds": [
                {
                    "seed": e.seed,
                    "period": e.longest_tile_cycle.period,
                    "length": e.longest_tile_cycle.length,
                    "repeats": e.longest_tile_cycle.repeats,
                    "start_seconds": round(e.longest_tile_cycle.start_seconds, 3),
                }
                for e in sorted(evaluations, key=lambda e: -e.longest_tile_cycle.length)[:10]
            ],
        },
        "acceptance": {
            "rule": rule.as_dict(),
            "accepted": accepted,
            "accept_rate": round(accepted / len(evaluations), 5) if evaluations else 0.0,
            "failure_counts": dict(sorted(failure_counts.items(), key=lambda kv: -kv[1])),
        },
        "failures": failure_census(evaluations),
    }


def activation_curve_percentiles(
    curves: Iterable[Sequence[tuple[float, int]]],
) -> list[dict[str, Any]]:
    """The population's progress bar: when the nth tile lights, as a spread.

    One row per activation number, so row 51 is the whole population's
    completion distribution and row 26 is when half the arena is typically lit.
    Reading the rows in order is reading the average shape of the run, and the
    gap between p50 and p90 at each row is how much of the variation is already
    present by that point.

    Takes an iterable so the caller can stream curves out of a simulation loop:
    only `total_tiles` lists of floats are ever held, not one curve per seed.
    """
    by_index: dict[int, list[float]] = {}
    for curve in curves:
        seen: set[int] = set()
        for time, count in curve:
            # The curve repeats its last count at the run's end time; that point
            # is the dead tail, not an activation, so it must not be counted.
            if count >= 1 and count not in seen:
                seen.add(count)
                by_index.setdefault(count, []).append(time)
    rows: list[dict[str, Any]] = []
    for count in sorted(by_index):
        times = sorted(by_index[count])
        rows.append(
            {
                "activated": count,
                "runs": len(times),
                "p10": round(percentile(times, 0.10), 3),
                "p25": round(percentile(times, 0.25), 3),
                "p50": round(percentile(times, 0.50), 3),
                "p75": round(percentile(times, 0.75), 3),
                "p90": round(percentile(times, 0.90), 3),
            }
        )
    return rows


def shortlist(
    evaluations: Sequence[RunEvaluation],
    rule: AcceptanceRule = DEFAULT_RULE,
    limit: int = 20,
) -> list[Candidate]:
    """The accepted seeds, best first. Acceptance decides; the score only ranks.

    Sorting is by score and then by seed, so the shortlist is a deterministic
    function of the population and two runs of the same sweep cannot disagree
    about the order of two equally-scoring seeds.
    """
    candidates: list[Candidate] = []
    for evaluation in evaluations:
        outcome = verdict(evaluation, rule)
        if not outcome.accepted:
            continue
        candidates.append(
            Candidate(
                evaluation=evaluation,
                verdict=outcome,
                score=candidate_score(evaluation, rule),
            )
        )
    candidates.sort(key=lambda c: (-c.score.total, c.seed))
    return candidates[:limit]


def rescale_to_speed(seconds: float | None, from_speed: float, to_speed: float) -> float | None:
    """A clock measured at one speed, at another. Exact when `gravity = 0`."""
    if seconds is None or to_speed <= 0.0:
        return None
    return seconds * (from_speed / to_speed)


def verify_speed_invariance(
    seeds: Sequence[int],
    speeds: Sequence[float],
    reference_speed: float = 60.0,
    arena: Arena | None = None,
    config: TileEscapeConfig = PHASE2_CONFIG,
) -> dict[str, Any]:
    """Measure, rather than assume, that speed is only a change of clock.

    For each seed it compares the full tile sequence at every speed against the
    reference, and the completion-time ratio against the exact
    `reference_speed / speed`. A single mismatch anywhere makes `invariant`
    false, because the claim this underwrites - that one sweep gives the whole
    speed curve - is not the sort of thing to hold "mostly".
    """
    arena = arena if arena is not None else PHASE2_ARENA
    rows: list[dict[str, Any]] = []
    invariant = True
    worst_ratio_error = 0.0

    for seed in seeds:
        reference = simulate(
            seed,
            TileEscapeConfig(**{**config.as_dict(), "speed": reference_speed}),
            arena,
        )
        reference_sequence = [c.tile_index for c in reference.collisions]
        for speed in speeds:
            run = simulate(
                seed, TileEscapeConfig(**{**config.as_dict(), "speed": speed}), arena
            )
            same = [c.tile_index for c in run.collisions] == reference_sequence
            expected = reference_speed / speed
            ratio = (
                run.completion_time / reference.completion_time
                if run.completion_time and reference.completion_time
                else None
            )
            error = abs(ratio - expected) / expected if ratio else math.inf
            worst_ratio_error = max(worst_ratio_error, error)
            if not same or error > 1.0e-9:
                invariant = False
            rows.append(
                {
                    "seed": seed,
                    "speed": speed,
                    "same_tile_sequence": same,
                    "collisions": len(run.collisions),
                    "completion_seconds": (
                        None if run.completion_time is None else round(run.completion_time, 6)
                    ),
                    "time_ratio": None if ratio is None else ratio,
                    "expected_ratio": expected,
                    "relative_error": None if ratio is None else error,
                }
            )

    return {
        "reference_speed": reference_speed,
        "seeds": list(seeds),
        "speeds": list(speeds),
        "invariant": invariant,
        "worst_relative_time_error": worst_ratio_error,
        "rows": rows,
    }


def curves_for(
    seeds: Iterable[int],
    config: TileEscapeConfig = PHASE2_CONFIG,
    arena: Arena | None = None,
) -> dict[int, tuple[tuple[float, int], ...]]:
    """Activation curves for a handful of seeds, for plotting or inspection."""
    arena = arena if arena is not None else PHASE2_ARENA
    return {seed: activation_curve(simulate(seed, config, arena)) for seed in seeds}

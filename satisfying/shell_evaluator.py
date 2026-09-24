"""What a MUSICAL SHELL ESCAPE run is actually like, measured rather than judged.

Category 3 Test #2. This module answers one question per number and refuses to
answer it with a score. A single number would say seed 4471 rates 0.82 and seed
9013 rates 0.79, which is exactly the information that is useless: the question
a shortlist needs answered is *which* of the things that make a run unwatchable
this run has, and a weighted sum destroys that on purpose.

So a run comes back with a metrics dictionary and a list of named **flags**. A
flag is a specific, quantified complaint - `one_shell_hog`, `dead_middle`,
`repetitive_orbit` - and `usable` is simply "no flags". A caller that disagrees
with a threshold can change it and re-run; a caller that disagrees with a score
can only argue.

## The measurements, and what each is for

**Outcome.** Escape or timeout, when, and from how deep. A population with no
failures in it is a population whose question has no tension, so the failure
rate is a headline number rather than a footnote.

**Progression.** Region 0 is inside the innermost shell, region 6 is out. The
timeline records every crossing in both directions, because the ball falling
back from region 4 to region 2 is the thing the concept is *for* and a metric
that only counted forward steps would call that run uneventful.

**Collisions.** Count, rate, per shell, and per third. The rate is a
production constraint in both directions: under about one a second the screen
is empty, and over about eight a second no viewer can follow which bounce
mattered, which the brief calls a visually impossible event rate.

**Near misses.** Defined in `satisfying.shell_escape._near_miss` and counted
here by shell and by third. This is the retention metric. A run with no near
misses has no repeated prediction opportunities, whatever else it has.

**Damage and breaks.** How much of the arena the ball actually changed, and
when. A run where nothing breaks is a run where the second mechanic is
decoration.

**Escape routes.** Two counts that are deliberately different: *every* outward
crossing, and the **progression** crossings - the ones that took the ball to a
region it had not reached before. The second is the one that means anything.
Measured the first way, breaking looks dominant in almost every configuration,
because a ball that yo-yos across one broken panel eleven times records eleven
break exits; measured the second way the same population is three-quarters
openings. Reporting only the first number is how a balance problem gets
invented that was never there.

**Stagnation.** Four separate longest-gaps - without a near miss, without a
break, without progress, without any meaningful event - because they fail
differently. A run can be full of near misses and make no progress for nine
seconds, and only one of those numbers notices.

**Repetition.** The sequence of panels struck, checked for short cycles. A
ball that bounces between the same two panels eleven times is a pathological
orbit and looks like a frozen frame no matter how the physics got there.

**Escalation.** The same counts in the first, middle and final third. The
brief does not ask for collisions to rise - at constant speed they largely
cannot - it asks for the run to become *different*, so what is reported is
each third's character and not one ratio.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from satisfying.shell_escape import DEFAULT_CONFIG, ShellEscapeConfig, ShellEscapeRun, simulate

__all__ = [
    "EvaluationThresholds",
    "DEFAULT_THRESHOLDS",
    "RunEvaluation",
    "evaluate",
    "evaluate_seed",
    "summarise",
    "FLAG_NAMES",
]


@dataclass(frozen=True)
class EvaluationThresholds:
    """Every line a flag is drawn at, in one place and all of them named.

    The brief's runtime targets are here as `preferred_*` and `acceptable_*`;
    everything else is a pathology the brief lists by name.
    """

    preferred_low: float = 20.0
    preferred_high: float = 24.0
    acceptable_low: float = 18.0
    acceptable_high: float = 26.0

    # "instant escape with no suspense"
    min_escape_seconds: float = 15.0
    # "success only at the exact timeout"
    photo_finish_seconds: float = 0.5
    # "one shell consuming most of the video". Measured on the population of
    # in-band escapes rather than picked: the median run gives its biggest
    # region 0.387 of the runtime and the 75th percentile 0.467, so 0.40 cuts
    # just above the middle and still leaves about 1600 clean in-band seeds in
    # twenty thousand. It has to be this tight - the first shortlist built at
    # 0.5 produced a candidate that spent 91% of its run inside the two
    # innermost shells and cleared the outer four in under two seconds.
    max_region_share: float = 0.40
    # "no near misses"
    min_near_misses: int = 6
    # "long dead middle" and "long repetitive orbit"
    max_stagnation_seconds: float = 6.0
    max_middle_stagnation_seconds: float = 5.0
    # "visually impossible event rate"
    max_collision_rate: float = 8.0
    min_collision_rate: float = 1.2
    # "long repetitive orbit" / "pathological orbits"
    max_cycle_run: int = 10
    max_cycle_period: int = 6
    min_distinct_panels: int = 12
    # "no meaningful environment change" / one mechanic irrelevant
    min_breaks: int = 1
    min_progression_openings: int = 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "preferred_low": self.preferred_low,
            "preferred_high": self.preferred_high,
            "acceptable_low": self.acceptable_low,
            "acceptable_high": self.acceptable_high,
            "min_escape_seconds": self.min_escape_seconds,
            "photo_finish_seconds": self.photo_finish_seconds,
            "max_region_share": self.max_region_share,
            "min_near_misses": self.min_near_misses,
            "max_stagnation_seconds": self.max_stagnation_seconds,
            "max_middle_stagnation_seconds": self.max_middle_stagnation_seconds,
            "max_collision_rate": self.max_collision_rate,
            "min_collision_rate": self.min_collision_rate,
            "max_cycle_run": self.max_cycle_run,
            "max_cycle_period": self.max_cycle_period,
            "min_distinct_panels": self.min_distinct_panels,
            "min_breaks": self.min_breaks,
            "min_progression_openings": self.min_progression_openings,
        }


DEFAULT_THRESHOLDS = EvaluationThresholds()

FLAG_NAMES: tuple[str, ...] = (
    "instrument_fault",
    "failed",
    "instant_escape",
    "photo_finish",
    "one_shell_hog",
    "too_few_near_misses",
    "dead_stretch",
    "dead_middle",
    "frantic",
    "sparse",
    "repetitive_orbit",
    "few_distinct_panels",
    "no_breaks",
    "no_opening_progress",
)


@dataclass
class RunEvaluation:
    """One run, measured. `usable` is exactly "no flags", never a score."""

    seed: int
    metrics: dict[str, Any]
    flags: list[str] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        return not self.flags

    @property
    def escaped(self) -> bool:
        return bool(self.metrics["outcome"]["escaped"])

    @property
    def duration(self) -> float:
        return float(self.metrics["outcome"]["duration"])

    def as_dict(self) -> dict[str, Any]:
        return {"seed": self.seed, "flags": list(self.flags), "usable": self.usable, **self.metrics}

    def headline(self) -> dict[str, Any]:
        """The few numbers a shortlist table needs, without the nesting."""
        m = self.metrics
        return {
            "seed": self.seed,
            "escaped": m["outcome"]["escaped"],
            "duration": round(m["outcome"]["duration"], 3),
            "collisions": m["collisions"]["total"],
            "collision_rate": round(m["collisions"]["per_second"], 3),
            "near_misses": m["near_misses"]["total"],
            "breaks": m["damage"]["breaks"],
            "progression_openings": m["routes"]["progression_opening"],
            "progression_breaks": m["routes"]["progression_break"],
            "regressions": m["progression"]["regressions"],
            "max_region_share": round(m["progression"]["max_region_share"], 3),
            "longest_dead_stretch": round(m["stagnation"]["longest_no_event"], 3),
            "longest_cycle_run": m["repetition"]["longest_cycle_run"],
            "late_near_misses": m["escalation"]["near_misses"][2],
            "flags": list(self.flags),
        }


def _thirds(duration: float) -> tuple[float, float]:
    return duration / 3.0, 2.0 * duration / 3.0


def _third_of(t: float, a: float, b: float) -> int:
    return 0 if t < a else (1 if t < b else 2)


def _longest_gap(times: Sequence[float], duration: float) -> tuple[float, float]:
    """The longest stretch with none of `times` in it, and when it started.

    The run's start and end count as boundaries, so a run whose only near miss
    is at second one has a very long gap and says so.
    """
    previous = 0.0
    longest = 0.0
    start = 0.0
    for t in times:
        if t - previous > longest:
            longest = t - previous
            start = previous
        previous = t
    if duration - previous > longest:
        longest = duration - previous
        start = previous
    return longest, start


def _longest_cycle(sequence: Sequence[Any], max_period: int) -> tuple[int, int]:
    """The longest stretch that repeats with some short period, and the period.

    A two-panel bounce loop is period 2; a triangle is period 3. Reported as
    the number of consecutive contacts that continued an already-running cycle,
    so eleven alternations between two panels reads as 9.
    """
    best_run = 0
    best_period = 0
    n = len(sequence)
    for period in range(1, max_period + 1):
        run = 0
        for i in range(period, n):
            if sequence[i] == sequence[i - period]:
                run += 1
                if run > best_run:
                    best_run = run
                    best_period = period
            else:
                run = 0
    return best_run, best_period


def evaluate(
    run: ShellEscapeRun, thresholds: EvaluationThresholds = DEFAULT_THRESHOLDS
) -> RunEvaluation:
    """Measure one run and flag every specific thing wrong with it."""
    duration = max(run.duration, 1e-9)
    shells = run.arena.shell_count
    a, b = _thirds(duration)

    collisions = [e for e in run.events if e.kind == "collision"]
    near_misses = [e for e in run.events if e.kind == "near_miss"]
    breaks = [e for e in run.events if e.kind == "panel_break"]
    damages = [e for e in run.events if e.kind == "damage"]
    exits = [e for e in run.events if e.kind == "shell_exit"]
    entries = [e for e in run.events if e.kind == "shell_entry"]

    # --- progression -----------------------------------------------------
    timeline: list[dict[str, Any]] = []
    region = 0
    entered = 0.0
    entered_via = "start"
    deepest = 0
    progress_times: list[float] = []
    progression_opening = 0
    progression_break = 0
    for event in run.events:
        if event.kind not in ("shell_exit", "shell_entry"):
            continue
        timeline.append(
            {
                "region": region,
                "enter_t": entered,
                "exit_t": event.t,
                "duration": event.t - entered,
                "entered_via": entered_via,
                "left_via": event.data["method"],
                "left_direction": "outward" if event.kind == "shell_exit" else "inward",
            }
        )
        region = event.data["to_region"]
        entered = event.t
        entered_via = event.data["method"]
        if region > deepest:
            deepest = region
            progress_times.append(event.t)
            if event.data["method"] == "opening":
                progression_opening += 1
            elif event.data["method"] == "break":
                progression_break += 1
    timeline.append(
        {
            "region": region,
            "enter_t": entered,
            "exit_t": duration,
            "duration": duration - entered,
            "entered_via": entered_via,
            "left_via": "end",
            "left_direction": "none",
        }
    )

    dwell = [0.0] * (shells + 1)
    visits = [0] * (shells + 1)
    for span in timeline:
        dwell[span["region"]] += span["duration"]
        visits[span["region"]] += 1
    max_region_share = max(dwell) / duration

    # --- collisions ------------------------------------------------------
    per_shell = [0] * shells
    for event in collisions:
        per_shell[event.data["shell_id"]] += 1
    buckets = [0] * (int(duration // 2.0) + 1)
    for event in collisions:
        buckets[min(int(event.t // 2.0), len(buckets) - 1)] += 1

    # --- near misses -----------------------------------------------------
    nm_per_shell = [0] * shells
    for event in near_misses:
        nm_per_shell[event.data["shell_id"]] += 1
    nm_separation = [e.data["arc_separation_ball_radii"] for e in near_misses]
    nm_time_separation = [
        e.data["time_separation"] for e in near_misses if math.isfinite(e.data["time_separation"])
    ]
    nm_by_criterion = {"arc": 0, "time": 0, "arc+time": 0}
    for event in near_misses:
        nm_by_criterion[event.data["criterion"]] += 1

    # --- damage ----------------------------------------------------------
    breaks_per_shell = [0] * shells
    for event in breaks:
        breaks_per_shell[event.data["shell_id"]] += 1

    # --- stagnation ------------------------------------------------------
    meaningful = sorted(
        [e.t for e in near_misses] + [e.t for e in breaks] + progress_times + [e.t for e in entries]
    )
    longest_event, longest_event_at = _longest_gap(meaningful, duration)
    longest_nm, longest_nm_at = _longest_gap([e.t for e in near_misses], duration)
    longest_break, _ = _longest_gap([e.t for e in breaks], duration)
    longest_progress, longest_progress_at = _longest_gap(progress_times, duration)
    middle_stagnation = max(
        (
            min(end, b) - max(start, a)
            for start, end in zip([0.0] + meaningful, meaningful + [duration])
            if min(end, b) > max(start, a)
        ),
        default=0.0,
    )

    # --- repetition ------------------------------------------------------
    panel_sequence = [(e.data["shell_id"], e.data["panel_id"]) for e in collisions]
    cycle_run, cycle_period = _longest_cycle(panel_sequence, thresholds.max_cycle_period)
    distinct_panels = len(set(panel_sequence))
    immediate_repeats = sum(
        1 for i in range(1, len(panel_sequence)) if panel_sequence[i] == panel_sequence[i - 1]
    )

    # --- escalation ------------------------------------------------------
    def by_third(events: Iterable[Any]) -> list[int]:
        out = [0, 0, 0]
        for event in events:
            out[_third_of(event.t, a, b)] += 1
        return out

    progress_by_third = [0, 0, 0]
    for t in progress_times:
        progress_by_third[_third_of(t, a, b)] += 1
    flight_lengths = [
        run.flights[i + 1].t - run.flights[i].t for i in range(len(run.flights) - 1)
    ]

    metrics: dict[str, Any] = {
        "outcome": {
            "escaped": run.escaped,
            "failure_reason": run.failure_reason,
            "duration": run.duration,
            "escape_time": run.escape_time,
            "final_region": run.final_region,
            "max_region": run.max_region,
            "shell_count": shells,
            "digest": run.state_digest(),
        },
        "progression": {
            "timeline": timeline,
            "dwell": dwell,
            "visits": visits,
            "max_region_share": max_region_share,
            "shells_passed": deepest,
            "progress_times": progress_times,
            "regressions": len(entries),
            "outward_crossings": len(exits),
        },
        "collisions": {
            "total": len(collisions),
            "per_second": len(collisions) / duration,
            "per_shell": per_shell,
            "per_two_seconds": buckets,
            "grazing": run.grazing_collisions,
            "post_contacts": sum(1 for e in collisions if e.data["feature"] == "post"),
            "mean_flight_seconds": statistics.fmean(flight_lengths) if flight_lengths else 0.0,
            "min_flight_seconds": min(flight_lengths) if flight_lengths else 0.0,
        },
        "near_misses": {
            "total": len(near_misses),
            "per_second": len(near_misses) / duration,
            "per_shell": nm_per_shell,
            "by_criterion": nm_by_criterion,
            "median_arc_ball_radii": statistics.median(nm_separation) if nm_separation else None,
            "median_time_separation": (
                statistics.median(nm_time_separation) if nm_time_separation else None
            ),
        },
        "damage": {
            "events": len(damages),
            "breaks": len(breaks),
            "breaks_per_shell": breaks_per_shell,
            "break_times": [e.t for e in breaks],
            "first_break": breaks[0].t if breaks else None,
            "last_break": breaks[-1].t if breaks else None,
            "panels_damaged": sum(1 for shell in run.damage for value in shell if value > 0.0),
            "max_panel_damage": max((max(shell) for shell in run.damage if shell), default=0.0),
        },
        "routes": {
            "exit_opening": sum(1 for e in exits if e.data["method"] == "opening"),
            "exit_break": sum(1 for e in exits if e.data["method"] == "break"),
            "entry_opening": sum(1 for e in entries if e.data["method"] == "opening"),
            "entry_break": sum(1 for e in entries if e.data["method"] == "break"),
            "progression_opening": progression_opening,
            "progression_break": progression_break,
            "final_method": (
                next((e.data["method"] for e in run.events if e.kind == "escape"), None)
            ),
        },
        "stagnation": {
            "longest_no_event": longest_event,
            "longest_no_event_at": longest_event_at,
            "longest_no_near_miss": longest_nm,
            "longest_no_near_miss_at": longest_nm_at,
            "longest_no_break": longest_break,
            "longest_no_progress": longest_progress,
            "longest_no_progress_at": longest_progress_at,
            "middle_third_stagnation": middle_stagnation,
        },
        "repetition": {
            "longest_cycle_run": cycle_run,
            "cycle_period": cycle_period,
            "distinct_panels": distinct_panels,
            "immediate_repeats": immediate_repeats,
        },
        "escalation": {
            "collisions": by_third(collisions),
            "near_misses": by_third(near_misses),
            "breaks": by_third(breaks),
            "progress": progress_by_third,
            "regressions": by_third(entries),
        },
        "instruments": {
            "max_penetration": run.max_penetration,
            "speed_drift_relative": run.speed_drift_relative,
            "max_speed_correction": run.max_speed_correction,
            "anomalous_crossings": run.anomalous_crossings,
            "newton_failures": run.newton_failures,
        },
    }

    flags: list[str] = []
    if (
        run.max_penetration > 1e-6
        or run.speed_drift_relative > 1e-9
        or run.anomalous_crossings
        or run.newton_failures
    ):
        flags.append("instrument_fault")
    if not run.escaped:
        flags.append("failed")
    else:
        if run.duration < thresholds.min_escape_seconds:
            flags.append("instant_escape")
        if run.config.horizon - run.duration < thresholds.photo_finish_seconds:
            flags.append("photo_finish")
    if max_region_share > thresholds.max_region_share:
        flags.append("one_shell_hog")
    if len(near_misses) < thresholds.min_near_misses:
        flags.append("too_few_near_misses")
    if longest_event > thresholds.max_stagnation_seconds:
        flags.append("dead_stretch")
    if middle_stagnation > thresholds.max_middle_stagnation_seconds:
        flags.append("dead_middle")
    rate = len(collisions) / duration
    if rate > thresholds.max_collision_rate:
        flags.append("frantic")
    if rate < thresholds.min_collision_rate:
        flags.append("sparse")
    if cycle_run > thresholds.max_cycle_run:
        flags.append("repetitive_orbit")
    if distinct_panels < thresholds.min_distinct_panels:
        flags.append("few_distinct_panels")
    if len(breaks) < thresholds.min_breaks:
        flags.append("no_breaks")
    if progression_opening < thresholds.min_progression_openings:
        flags.append("no_opening_progress")

    return RunEvaluation(seed=run.seed, metrics=metrics, flags=flags)


def evaluate_seed(
    seed: int,
    config: ShellEscapeConfig = DEFAULT_CONFIG,
    thresholds: EvaluationThresholds = DEFAULT_THRESHOLDS,
) -> RunEvaluation:
    return evaluate(simulate(seed, config), thresholds)


# --------------------------------------------------------------------------
# Populations
# --------------------------------------------------------------------------


def _quantiles(values: Sequence[float], points: Sequence[float]) -> dict[str, float]:
    if not values:
        return {f"p{int(p*100)}": float("nan") for p in points}
    ordered = sorted(values)
    out: dict[str, float] = {}
    for p in points:
        index = min(len(ordered) - 1, max(0, int(round(p * (len(ordered) - 1)))))
        out[f"p{int(p*100)}"] = ordered[index]
    return out


def _histogram(values: Sequence[float], edges: Sequence[float]) -> dict[str, int]:
    out: dict[str, int] = {}
    previous = None
    for edge in edges:
        key = f"<{edge:g}" if previous is None else f"{previous:g}-{edge:g}"
        out[key] = sum(
            1 for v in values if (previous is None or v >= previous) and v < edge
        )
        previous = edge
    out[f">={edges[-1]:g}"] = sum(1 for v in values if v >= edges[-1])
    return out


def summarise(
    evaluations: Sequence[RunEvaluation],
    thresholds: EvaluationThresholds = DEFAULT_THRESHOLDS,
) -> dict[str, Any]:
    """The population, reported as distributions and flag counts.

    Everything here is a count or a quantile. There is no aggregate score,
    for the same reason a run does not get one.
    """
    total = len(evaluations)
    if total == 0:
        return {"seeds": 0}
    escaped = [e for e in evaluations if e.escaped]
    durations = [e.duration for e in escaped]
    usable = [e for e in evaluations if e.usable]

    in_acceptable = [
        e for e in escaped if thresholds.acceptable_low <= e.duration <= thresholds.acceptable_high
    ]
    in_preferred = [
        e for e in escaped if thresholds.preferred_low <= e.duration <= thresholds.preferred_high
    ]

    flag_counts = {name: 0 for name in FLAG_NAMES}
    for evaluation in evaluations:
        for flag in evaluation.flags:
            flag_counts[flag] = flag_counts.get(flag, 0) + 1

    def metric(path: Sequence[str], source: Sequence[RunEvaluation] = evaluations) -> list[float]:
        out: list[float] = []
        for evaluation in source:
            value: Any = evaluation.metrics
            for key in path:
                value = value[key]
            if value is not None:
                out.append(float(value))
        return out

    prog_open = sum(e.metrics["routes"]["progression_opening"] for e in evaluations)
    prog_break = sum(e.metrics["routes"]["progression_break"] for e in evaluations)
    escaped_with_break = sum(1 for e in escaped if e.metrics["routes"]["progression_break"] > 0)
    escaped_with_opening = sum(1 for e in escaped if e.metrics["routes"]["progression_opening"] > 0)

    return {
        "seeds": total,
        "outcome": {
            "escaped": len(escaped),
            "escape_rate": len(escaped) / total,
            "timeout_rate": 1.0 - len(escaped) / total,
            "usable": len(usable),
            "usable_rate": len(usable) / total,
            "in_acceptable_band": len(in_acceptable),
            "in_preferred_band": len(in_preferred),
            "acceptable_share_of_escapes": len(in_acceptable) / max(len(escaped), 1),
        },
        "duration": {
            "quantiles": _quantiles(durations, (0.05, 0.25, 0.5, 0.75, 0.95)),
            "mean": statistics.fmean(durations) if durations else float("nan"),
            "histogram": _histogram(durations, (10, 12, 14, 16, 18, 20, 22, 24, 26)),
        },
        "max_region": _histogram(
            [float(e.metrics["outcome"]["max_region"]) for e in evaluations],
            (1, 2, 3, 4, 5, 6),
        ),
        "collisions": {
            "quantiles": _quantiles(metric(("collisions", "total")), (0.05, 0.5, 0.95)),
            "rate_quantiles": _quantiles(
                metric(("collisions", "per_second")), (0.05, 0.5, 0.95)
            ),
        },
        "near_misses": {
            "quantiles": _quantiles(metric(("near_misses", "total")), (0.05, 0.25, 0.5, 0.75, 0.95)),
            "histogram": _histogram(metric(("near_misses", "total")), (2, 4, 6, 9, 12, 16, 22)),
            "zero_runs": sum(1 for e in evaluations if e.metrics["near_misses"]["total"] == 0),
        },
        "breaks": {
            "quantiles": _quantiles(metric(("damage", "breaks")), (0.05, 0.5, 0.95)),
            "histogram": _histogram(metric(("damage", "breaks")), (1, 3, 6, 10, 16, 24)),
            "zero_runs": sum(1 for e in evaluations if e.metrics["damage"]["breaks"] == 0),
        },
        "routes": {
            "progression_opening": prog_open,
            "progression_break": prog_break,
            "progression_opening_share": prog_open / max(prog_open + prog_break, 1),
            "escaped_using_a_break": escaped_with_break,
            "escaped_using_an_opening": escaped_with_opening,
            "escaped_using_both": sum(
                1
                for e in escaped
                if e.metrics["routes"]["progression_break"] > 0
                and e.metrics["routes"]["progression_opening"] > 0
            ),
        },
        "dwell": {
            "max_region_share": _quantiles(
                metric(("progression", "max_region_share")), (0.5, 0.75, 0.95)
            ),
            "regressions": _quantiles(metric(("progression", "regressions")), (0.05, 0.5, 0.95)),
        },
        "stagnation": {
            "longest_no_event": _quantiles(
                metric(("stagnation", "longest_no_event")), (0.5, 0.75, 0.95, 0.99)
            ),
            "longest_no_progress": _quantiles(
                metric(("stagnation", "longest_no_progress")), (0.5, 0.75, 0.95)
            ),
            "middle_third": _quantiles(
                metric(("stagnation", "middle_third_stagnation")), (0.5, 0.95)
            ),
        },
        "repetition": {
            "longest_cycle_run": _quantiles(
                metric(("repetition", "longest_cycle_run")), (0.5, 0.95, 0.99)
            ),
            "pathological": sum(
                1
                for e in evaluations
                if e.metrics["repetition"]["longest_cycle_run"] > thresholds.max_cycle_run
            ),
            "distinct_panels": _quantiles(metric(("repetition", "distinct_panels")), (0.05, 0.5)),
        },
        "escalation": {
            "collisions_by_third": [
                statistics.fmean([e.metrics["escalation"]["collisions"][i] for e in evaluations])
                for i in range(3)
            ],
            "near_misses_by_third": [
                statistics.fmean([e.metrics["escalation"]["near_misses"][i] for e in evaluations])
                for i in range(3)
            ],
            "breaks_by_third": [
                statistics.fmean([e.metrics["escalation"]["breaks"][i] for e in evaluations])
                for i in range(3)
            ],
            "progress_by_third": [
                statistics.fmean([e.metrics["escalation"]["progress"][i] for e in evaluations])
                for i in range(3)
            ],
        },
        "flags": flag_counts,
        "instruments": {
            "runs_with_penetration": sum(
                1 for e in evaluations if e.metrics["instruments"]["max_penetration"] > 1e-6
            ),
            "runs_with_anomalies": sum(
                1 for e in evaluations if e.metrics["instruments"]["anomalous_crossings"]
            ),
            "runs_with_solver_failures": sum(
                1 for e in evaluations if e.metrics["instruments"]["newton_failures"]
            ),
            "worst_penetration": max(
                e.metrics["instruments"]["max_penetration"] for e in evaluations
            ),
            "worst_speed_drift": max(
                e.metrics["instruments"]["speed_drift_relative"] for e in evaluations
            ),
            "speed_correction": _quantiles(
                [e.metrics["instruments"]["max_speed_correction"] for e in evaluations],
                (0.5, 0.95, 1.0),
            ),
        },
        "thresholds": thresholds.as_dict(),
    }

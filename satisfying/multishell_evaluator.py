"""What a MULTIPLYING SHELL ESCAPE run is worth, as numbers rather than as taste.

Category 3 Test #2, redesigned. The single-ball evaluator asked whether one
trajectory was interesting. This one has to ask something harder, because the
redesign's whole claim is about *change over the run*: does the population
actually grow, do the outer shells actually resist, and is the last third of
the video genuinely busier than the first third because of what the mechanic
did rather than because the metric was written to say so.

## The measurements, and why each one is defined the way it is

**Population.** `active` is the ball count sampled at ten points across the
run, plus the count at each third. Nothing ever removes a ball, so "active" and
"created so far" are the same number and the report says so rather than
implying two independent facts.

**Reproduction.** Spawns by shell and by generation, and `violations` - the
count of `(parent, shell)` pairs that produced a child twice. It has to be
zero; it is read off the event stream rather than off the bitmask that is
supposed to prevent it, because a rule checked against its own enforcement
variable checks nothing.

**Progress and difficulty.** Per shell: how many distinct balls were ever
*inside* it (`reached`), how many of those got out (`crossed`), the ratio, the
blocked contacts, the ball-seconds spent in the region, and the damage the
shell absorbed. `reached` uses each ball's record of the regions it actually
stood in, not the furthest region it got to: a child born outside shell 3 has
never been inside shells 0 to 2, and counting it as a ball that failed to cross
them would make every inner shell look harder than it is. Getting that wrong
inverts the difficulty curve, which is the one curve this phase exists to prove.

`difficulty_increasing` then asks whether the measured pass rate really falls
outward. That is the honest version of the claim the config makes: the config
sets smaller holes and tougher panels, but only the batch can say whether the
balls found them harder.

**Damage.** Events, state transitions by state, panels broken per shell, the
cumulative damage a panel had when it broke, and `shared_breaks` - breaks whose
ledger was paid into by more than one ball. That last number is the emergent
behaviour the concept asked for, so it is counted rather than asserted.

**Activity and escalation.** Collisions, spawns, breaks and "meaningful events"
by third, and the late-over-early ratios. A meaningful event is a collision, a
spawn, a break, a damage-state transition, a near miss or a shell crossing -
everything a viewer or a listener would register, and nothing that exists only
in the ledger. `escalation.meaningful` above 1 is the redesign's headline claim
and it is computed from the stream, with no term added to make it come out.

**Audio density.** `per_second` over the whole run, and `peak_window` - the
highest count of collisions inside any `audio_window` seconds, divided by the
window. The peak is the number that matters and the mean is the number that
flatters: a run averaging six collisions a second with twenty-two of them in
one second is not a six-a-second soundtrack. Both are reported.

## Flags

A flag is a named failure mode from the brief, drawn at a line in
`EvaluationThresholds`, and `usable` is exactly "no flags" - never a score, and
never a weighted sum, because a weighted sum lets a run with an impossible
event rate be rescued by having a lot of near misses.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from satisfying.multishell import (
    DAMAGE_STATES,
    DEFAULT_CONFIG,
    TEAM_NAMES,
    MultishellConfig,
    MultishellRun,
    simulate,
)

__all__ = [
    "EvaluationThresholds",
    "DEFAULT_THRESHOLDS",
    "FLAG_NAMES",
    "RunEvaluation",
    "MEANINGFUL_KINDS",
    "evaluate",
    "evaluate_seed",
    "summarise",
]

# What counts as a thing the audience registers. Damage events are excluded on
# purpose: they fire on every single contact and would make "meaningful events"
# a synonym for "collisions", which is the metric this one exists to be
# different from. The *state transitions* are in, because those are the moments
# a panel visibly changes.
MEANINGFUL_KINDS: frozenset[str] = frozenset(
    {
        "collision",
        "ball_spawn",
        "panel_break",
        "damage_state",
        "near_miss",
        "shell_exit",
        "shell_entry",
        "escape",
    }
)


@dataclass(frozen=True)
class EvaluationThresholds:
    """Every line a flag is drawn at, in one place and all of them named."""

    # --- runtime, from the brief -----------------------------------------
    preferred_low: float = 21.0
    preferred_high: float = 24.0
    acceptable_low: float = 20.0
    acceptable_high: float = 26.0

    # "instant escape with no suspense"
    min_escape_seconds: float = 12.0

    # --- population, from the brief's target progression -----------------
    # Every line here moved with the second founder. A run now *starts* at two,
    # so the Phase 3B floor of five was one spawn away from being met by a
    # failure, and the measured Phase 4A distribution has p5 = 7 and p50 = 12.
    # "too weak" is a run that barely reproduced at all.
    min_final_population: int = 8
    min_late_population: int = 5
    # "too explosive: population jumps to 20+ almost immediately". The early
    # population (at a quarter of the run) measures p90 = 7 and p99 = 10, so
    # eight still names the tail rather than the middle and did not need to
    # move.
    max_early_population: int = 8
    early_fraction: float = 0.25
    # "runaway population": the safety limit is a configuration failure, not a
    # mechanic, so touching it at all is a flag.
    # "too hard: multiplication occurs but all balls die/stall at one shell"
    min_generations: int = 2
    # "first reproduction happens quickly". The split is the concept's hook and
    # a viewer who has not seen it has not been told what the video is about.
    # Phase 3B hard-rejects anything above 3 s; the preferred candidates are at
    # or below 2.5 s.  This is a selection rule only and never changes motion.
    max_first_spawn_seconds: float = 3.0

    # --- difficulty ------------------------------------------------------
    # "outer shell impossible" / "outer shell trivial", measured on the run.
    max_outer_pass_rate: float = 0.85

    # --- activity --------------------------------------------------------
    # **These are the numbers the second founder moved furthest, and they had
    # to move.** Phase 3B drew the caution line at 9 collisions a second with a
    # 16/s windowed peak, on a population whose median was 6.2/s. Phase 4A's
    # median is 14.7/s: two founders roughly double the cast, and the arena
    # shrank from an outer radius of 24.4 to 18.5 so each ball meets a wall
    # sooner. Left alone, the two flags fired on 92% of a three-thousand-seed
    # population and `usable` fell to one run in three thousand - a flag that
    # rejects almost everything has stopped measuring anything.
    #
    # Re-drawn against the measured Phase 4A distribution rather than against a
    # remembered one. Over the escaped population the mean rate is p75 = 23.0
    # and p90 = 28.8, and the two-second windowed peak is p75 = 44.5 and
    # p90 = 53.0, so these two lines name roughly the busiest fifth and the
    # busiest eighth. The brief asked for more activity than Phase 3B and got
    # it; what it did not ask for is a video nobody can follow, and that is the
    # tail these still catch.
    max_peak_collision_rate: float = 48.0
    max_collision_rate: float = 24.0
    min_collision_rate: float = 3.0
    audio_window: float = 2.0

    # "long stalls". The measured longest silent stretch is p99 = 1.14 s - one
    # crossing of the opened-out arena - so four seconds was a line nothing
    # could reach. 2.5 s still sits well clear of the population and would
    # actually catch a run that stalled.
    max_stagnation_seconds: float = 2.5

    # --- escalation, the redesign's headline claim -----------------------
    min_escalation: float = 1.15

    # --- orbit traps and sameness ----------------------------------------
    # "orbit traps": one ball hitting the same short cycle of panels over and
    # over.
    max_cycle_run: int = 10
    max_cycle_period: int = 6
    # "all balls following nearly identical trajectories". Both of these were
    # dead guards at the Phase 3B values: the Phase 4A population has p1 = 41
    # distinct panels and p1 = 0.248 spread, so 14 and 0.10 could not fire on
    # any run, healthy or not. Moved to just outside the measured population so
    # they are guards again rather than decoration.
    min_distinct_panels: int = 30
    min_trajectory_spread: float = 0.18

    # --- the race ---------------------------------------------------------
    # A two-team video whose second colour never got going is a one-founder
    # video with a spare ball in it. Both of these are about whether there was
    # a race at all, and neither is about whether it was *close*: nothing here
    # rewards a narrow finish, because rewarding one would be the first step
    # towards arranging one.
    #: Every team must have reproduced at least this many times.
    min_team_population: int = 3
    #: The losing team must have got at least this far out. Two means it was
    #: through the first two shells and genuinely in the race.
    min_loser_frontier: int = 2
    #: The winning colour may not have had more than this share of the final
    #: population. Above it, the "race" is one team with a passenger.
    max_population_share: float = 0.80

    # --- mechanic coverage -----------------------------------------------
    min_breaks: int = 1  # noqa: E501 - a run with no break never showed the damage model at all
    min_progression_openings: int = 2

    def as_dict(self) -> dict[str, Any]:
        return {
            "preferred_low": self.preferred_low,
            "preferred_high": self.preferred_high,
            "acceptable_low": self.acceptable_low,
            "acceptable_high": self.acceptable_high,
            "min_escape_seconds": self.min_escape_seconds,
            "min_final_population": self.min_final_population,
            "min_late_population": self.min_late_population,
            "max_early_population": self.max_early_population,
            "early_fraction": self.early_fraction,
            "min_generations": self.min_generations,
            "max_first_spawn_seconds": self.max_first_spawn_seconds,
            "max_outer_pass_rate": self.max_outer_pass_rate,
            "max_peak_collision_rate": self.max_peak_collision_rate,
            "max_collision_rate": self.max_collision_rate,
            "min_collision_rate": self.min_collision_rate,
            "audio_window": self.audio_window,
            "max_stagnation_seconds": self.max_stagnation_seconds,
            "min_escalation": self.min_escalation,
            "max_cycle_run": self.max_cycle_run,
            "max_cycle_period": self.max_cycle_period,
            "min_distinct_panels": self.min_distinct_panels,
            "min_trajectory_spread": self.min_trajectory_spread,
            "min_breaks": self.min_breaks,
            "min_progression_openings": self.min_progression_openings,
            "min_team_population": self.min_team_population,
            "min_loser_frontier": self.min_loser_frontier,
            "max_population_share": self.max_population_share,
        }


DEFAULT_THRESHOLDS = EvaluationThresholds()

FLAG_NAMES: tuple[str, ...] = (
    "instrument_fault",
    "spawn_farming",
    "failed",
    "instant_escape",
    "population_weak",
    "population_explosive",
    "population_capped",
    "too_few_generations",
    "slow_first_spawn",
    "outer_shell_trivial",
    "frantic_peak",
    "frantic_mean",
    "sparse",
    "dead_stretch",
    "no_escalation",
    "repetitive_orbit",
    "few_distinct_panels",
    "clone_trajectories",
    "no_breaks",
    "no_opening_progress",
    "team_starved",
    "loser_stalled",
    "one_sided",
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
            "final_population": m["population"]["total"],
            "max_population": m["population"]["max"],
            "generations": m["population"]["generations"],
            "first_spawn": m["reproduction"]["first_spawn"],
            "escape_generation": m["outcome"]["escape_generation"],
            "collisions": m["collisions"]["total"],
            "collision_rate": round(m["collisions"]["per_second"], 3),
            "peak_collision_rate": round(m["collisions"]["peak_window"], 3),
            "breaks": m["damage"]["breaks"],
            "shared_breaks": m["damage"]["shared_breaks"],
            "escalation_meaningful": round(m["escalation"]["meaningful"], 3),
            "progression_openings": m["routes"]["progression_opening"],
            "progression_breaks": m["routes"]["progression_break"],
            "escape_route": m["outcome"]["escape_route"],
            "winner": m["race"]["winner_name"],
            "winner_generation": m["race"]["winner_generation"],
            "population_by_team": m["race"]["population_by_team"],
            "lead_changes": m["race"]["population_lead_changes"],
            "frontier_lead_changes": m["race"]["frontier_lead_changes"],
            "win_margin_seconds": m["race"]["win_margin_seconds"],
            "cross_team_breaks": m["race"]["cross_team_breaks"],
            "outer_pass_rate": round(m["difficulty"]["pass_rate"][-1], 3),
            "flags": list(self.flags),
        }


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _third_of(t: float, duration: float) -> int:
    if duration <= 0.0:
        return 0
    return min(2, max(0, int(3.0 * t / duration)))


def _longest_gap(times: Sequence[float], duration: float) -> float:
    """The longest stretch with nothing in it, ends included."""
    if duration <= 0.0:
        return 0.0
    previous = 0.0
    worst = 0.0
    for t in times:
        if t - previous > worst:
            worst = t - previous
        previous = t
    if duration - previous > worst:
        worst = duration - previous
    return worst


def _peak_window(times: Sequence[float], window: float) -> float:
    """The most events in any `window` seconds, as a rate.

    A sliding count over the sorted times, which is exact rather than a
    histogram's approximation - a bin boundary in the middle of a burst halves
    the burst and is exactly the error that would make a frantic run look calm.
    """
    if not times or window <= 0.0:
        return 0.0
    ordered = sorted(times)
    best = 0
    j = 0
    for i, t in enumerate(ordered):
        while ordered[j] < t - window:
            j += 1
        if i - j + 1 > best:
            best = i - j + 1
    return best / window


def _longest_cycle(sequence: Sequence[Any], max_period: int) -> tuple[int, int]:
    """The longest run of a repeating short cycle, and its period.

    An orbit trap is a ball hitting the same handful of panels in the same
    order; this finds the longest stretch of the sequence that is periodic with
    some period up to `max_period`, and returns `(run_length, period)`.
    """
    best_run = 0
    best_period = 0
    n = len(sequence)
    for period in range(1, max_period + 1):
        if n <= period:
            break
        run = 0
        for i in range(period, n):
            if sequence[i] == sequence[i - period]:
                run += 1
                if run + period > best_run:
                    best_run = run + period
                    best_period = period
            else:
                run = 0
    return best_run, best_period


# --------------------------------------------------------------------------
# The evaluation
# --------------------------------------------------------------------------


def evaluate(
    run: MultishellRun, thresholds: EvaluationThresholds = DEFAULT_THRESHOLDS
) -> RunEvaluation:
    """Measure one run against every line in `thresholds`."""
    config = run.config
    n_shells = config.shell_count
    duration = run.duration or 1.0
    events = run.events

    by_kind: dict[str, list] = {}
    for ev in events:
        by_kind.setdefault(ev.kind, []).append(ev)

    collisions = by_kind.get("collision", [])
    spawns = by_kind.get("ball_spawn", [])
    breaks = by_kind.get("panel_break", [])
    transitions = by_kind.get("damage_state", [])
    near_misses = by_kind.get("near_miss", [])
    exits = by_kind.get("shell_exit", [])
    entries = by_kind.get("shell_entry", [])
    damages = by_kind.get("damage", [])

    # --- population ------------------------------------------------------
    samples = [round(duration * i / 10.0, 6) for i in range(11)]
    curve = [run.population_at(t) for t in samples]
    thirds_population = [run.population_at(duration * f) for f in (1 / 3, 2 / 3, 1.0)]
    early_population = run.population_at(duration * thresholds.early_fraction)
    by_region = [0] * (n_shells + 1)
    for record in run.balls:
        by_region[record.final_region] += 1
    generations = run.max_generation + 1

    # --- reproduction ----------------------------------------------------
    first_spawn = spawns[0].t if spawns else None
    spawns_by_shell = [0] * n_shells
    spawns_by_generation: dict[int, int] = {}
    claims: set[tuple[int, int]] = set()
    violations = 0
    for ev in spawns:
        spawns_by_shell[ev.data["birth_shell"]] += 1
        g = ev.data["generation"]
        spawns_by_generation[g] = spawns_by_generation.get(g, 0) + 1
        claim = (ev.data["parent_id"], ev.data["birth_shell"])
        if claim in claims:
            violations += 1
        claims.add(claim)

    # --- progress and difficulty ----------------------------------------
    reached = [0] * n_shells
    for record in run.balls:
        for region in record.visited:
            if region < n_shells:
                reached[region] += 1
    crossers: list[set[int]] = [set() for _ in range(n_shells)]
    first_cross: list[float | None] = [None] * n_shells
    crossings = [0] * n_shells
    regressions = [0] * n_shells
    route_by_shell = [{"opening": 0, "break": 0, "anomaly": 0} for _ in range(n_shells)]
    for ev in exits:
        k = ev.data["shell_id"]
        crossers[k].add(ev.data["ball_id"])
        crossings[k] += 1
        route_by_shell[k][ev.data["route"]] += 1
        if first_cross[k] is None:
            first_cross[k] = ev.t
    for ev in entries:
        regressions[ev.data["shell_id"]] += 1

    blocked = [0] * n_shells
    collisions_by_shell = [0] * n_shells
    for ev in collisions:
        k = ev.data["shell_id"]
        collisions_by_shell[k] += 1
        if ev.data["region"] == k:
            blocked[k] += 1

    damage_by_shell = [0.0] * n_shells
    for ev in damages:
        damage_by_shell[ev.data["shell_id"]] += ev.data["contribution"]

    pass_rate = [
        (len(crossers[k]) / reached[k]) if reached[k] else 0.0 for k in range(n_shells)
    ]
    contacts_per_crossing = [
        (blocked[k] / len(crossers[k])) if crossers[k] else math.inf for k in range(n_shells)
    ]
    # Does the pass rate actually fall outward? Compared on the shells a run
    # genuinely engaged with, because a shell no ball ever reached has a pass
    # rate of zero for an uninteresting reason.
    engaged = [k for k in range(n_shells) if reached[k] > 0]
    difficulty_increasing = all(
        pass_rate[a] >= pass_rate[b] - 1.0e-12 for a, b in zip(engaged, engaged[1:])
    )

    # --- damage ----------------------------------------------------------
    breaks_by_shell = [0] * n_shells
    shared_breaks = 0
    outer_cooperative_breaks = 0
    break_cumulative: list[float] = []
    break_details: list[dict[str, Any]] = []
    generation_by_ball = {record.ball_id: record.generation for record in run.balls}
    for ev in breaks:
        shell_id = ev.data["shell_id"]
        panel_id = ev.data["panel_id"]
        breaks_by_shell[shell_id] += 1
        break_cumulative.append(ev.data["cumulative"])
        if ev.data["contributors"] > 1:
            shared_breaks += 1
            if shell_id == n_shells - 1:
                outer_cooperative_breaks += 1
        paid: dict[int, float] = {}
        for damage in damages:
            if damage.t > ev.t:
                continue
            if (
                damage.data["shell_id"] == shell_id
                and damage.data["panel_id"] == panel_id
                and damage.data["contribution"] > 0.0
            ):
                ball_id = int(damage.data["ball_id"])
                paid[ball_id] = paid.get(ball_id, 0.0) + float(damage.data["contribution"])
        largest_ball = max(paid, key=lambda ball_id: (paid[ball_id], -ball_id)) if paid else None
        break_details.append(
            {
                "shell_id": shell_id,
                "panel_id": panel_id,
                "t": ev.t,
                "unique_contributing_balls": len(paid),
                "contributing_ball_ids": sorted(paid),
                "contributing_generations": sorted(
                    {generation_by_ball[ball_id] for ball_id in paid}
                ),
                "largest_contributor": largest_ball,
                "largest_contribution": paid.get(largest_ball, 0.0),
                "final_triggering_ball": int(ev.data["ball_id"]),
            }
        )
    transitions_by_state = {name: 0 for name in DAMAGE_STATES}
    for ev in transitions:
        transitions_by_state[ev.data["new_state"]] += 1
    scoring_damage = sum(1 for ev in damages if ev.data["contribution"] > 0.0)

    # --- routes ----------------------------------------------------------
    progression_opening = sum(r["opening"] for r in route_by_shell)
    progression_break = sum(r["break"] for r in route_by_shell)

    # --- activity and escalation -----------------------------------------
    def thirds(evs: Iterable[Any]) -> list[int]:
        out = [0, 0, 0]
        for ev in evs:
            out[_third_of(ev.t, duration)] += 1
        return out

    collision_thirds = thirds(collisions)
    spawn_thirds = thirds(spawns)
    break_thirds = thirds(breaks)
    meaningful = [ev for ev in events if ev.kind in MEANINGFUL_KINDS]
    meaningful_thirds = thirds(meaningful)

    def ratio(counts: Sequence[int]) -> float:
        return (counts[2] + 1.0) / (counts[0] + 1.0)

    collision_times = [ev.t for ev in collisions]
    meaningful_times = sorted(ev.t for ev in meaningful)

    # --- orbit traps and sameness ----------------------------------------
    panels_by_ball: dict[int, list[tuple[int, int]]] = {}
    for ev in collisions:
        panels_by_ball.setdefault(ev.data["ball_id"], []).append(
            (ev.data["shell_id"], ev.data["panel_id"])
        )
    longest_cycle_run = 0
    longest_cycle_period = 0
    for sequence in panels_by_ball.values():
        run_length, period = _longest_cycle(sequence, thresholds.max_cycle_period)
        if run_length > longest_cycle_run:
            longest_cycle_run = run_length
            longest_cycle_period = period
    distinct_panels = len({(ev.data["shell_id"], ev.data["panel_id"]) for ev in collisions})

    # "All balls following nearly identical trajectories": if every ball is
    # doing the same thing, they are in the same place at the same time. Sampled
    # spread of the population's radius, averaged - a clone swarm has a spread
    # of nearly zero and a healthy one does not.
    spreads: list[float] = []
    for t in samples[1:]:
        radii = []
        for record in run.balls:
            if record.birth_time > t:
                continue
            flights = run.flights.get(record.ball_id, ())
            place = None
            for flight in flights:
                if flight.t <= t:
                    place = flight
                else:
                    break
            if place is None:
                continue
            x = place.x + place.vx * (t - place.t)
            y = place.y + place.vy * (t - place.t)
            radii.append(math.hypot(x, y))
        if len(radii) > 1:
            mean = sum(radii) / len(radii)
            if mean > 0.0:
                variance = sum((r - mean) ** 2 for r in radii) / len(radii)
                spreads.append(math.sqrt(variance) / mean)
    trajectory_spread = sum(spreads) / len(spreads) if spreads else 1.0

    # --- the race ---------------------------------------------------------
    team_count = len(TEAM_NAMES)
    team_of = {record.ball_id: record.team_id for record in run.balls}
    team_curve = [list(run.team_population_at(t)) for t in samples]
    seconds = [float(i) for i in range(int(math.floor(duration)) + 1)]
    team_by_second = [list(run.team_population_at(t)) for t in seconds]
    first_spawn_by_team: list[float | None] = [None] * team_count
    for ev in spawns:
        team = int(ev.data["team_id"])
        if first_spawn_by_team[team] is None:
            first_spawn_by_team[team] = ev.t
    known = [t for t in first_spawn_by_team if t is not None]
    first_to_clone = (
        None
        if not known
        else min(
            range(team_count),
            key=lambda i: (
                math.inf if first_spawn_by_team[i] is None else first_spawn_by_team[i],
                i,
            ),
        )
    )

    # Damage, split by team, and the breaks both colours paid into. A break
    # whose contributors span both teams is the emergent moment the brief
    # names: one colour softened the panel and the other went through it.
    cross_team_breaks = 0
    breaks_by_largest_team = [0] * team_count
    breaks_triggered_by_team = [0] * team_count
    for ev in breaks:
        paid = list(ev.data["team_contributors"])
        if sum(1 for c in paid if c > 0) > 1:
            cross_team_breaks += 1
        largest = ev.data["largest_team"]
        if largest is not None:
            breaks_by_largest_team[int(largest)] += 1
        breaks_triggered_by_team[int(ev.data["team_id"])] += 1
    stolen_breaks = sum(
        1
        for ev in breaks
        if ev.data["largest_team"] is not None
        and int(ev.data["largest_team"]) != int(ev.data["team_id"])
    )

    crossings_by_team = [0] * team_count
    for ev in exits:
        crossings_by_team[int(ev.data["team_id"])] += 1

    winner = run.winner_team
    loser = None if winner is None else (winner + 1) % team_count
    final_team_population = list(run.team_balls)
    total_population = sum(final_team_population) or 1
    winner_share = (
        None if winner is None else final_team_population[winner] / total_population
    )

    escape_event = by_kind.get("escape", [None])[0]
    failure_event = by_kind.get("failure", [None])[0]

    metrics: dict[str, Any] = {
        "outcome": {
            "escaped": run.escaped,
            "duration": run.duration,
            "escape_time": run.escape_time,
            "escape_ball": run.escape_ball,
            "escape_route": escape_event.data["route"] if escape_event else None,
            "escape_generation": escape_event.data["generation"] if escape_event else None,
            "escape_lineage": list(escape_event.data["lineage"]) if escape_event else [],
            "failure_reason": run.failure_reason,
            "frontier_region": run.frontier_region,
            "frontier_balls": failure_event.data["frontier_balls"] if failure_event else 0,
            "shell_count": n_shells,
        },
        "population": {
            "total": len(run.balls),
            "max": run.max_population,
            "generations": generations,
            "curve": curve,
            "curve_times": samples,
            "thirds": thirds_population,
            "early": early_population,
            "by_region": by_region,
            "capped": run.spawns_suppressed > 0,
            "suppressed": run.spawns_suppressed,
            "note": "nothing removes a ball, so 'active' and 'created so far' are one number",
        },
        "reproduction": {
            "spawns": run.spawns,
            "first_spawn": first_spawn,
            "by_shell": spawns_by_shell,
            "by_generation": spawns_by_generation,
            "violations": violations,
        },
        "progression": {
            "reached": reached,
            "crossed": [len(s) for s in crossers],
            "crossings": crossings,
            "regressions": regressions,
            "first_cross": first_cross,
            "dwell": [round(v, 6) for v in run.region_dwell],
        },
        "difficulty": {
            "pass_rate": pass_rate,
            "blocked_contacts": blocked,
            "contacts_per_crossing": contacts_per_crossing,
            "damage_absorbed": [round(v, 6) for v in damage_by_shell],
            "increasing": difficulty_increasing,
            "engaged_shells": engaged,
        },
        "collisions": {
            "total": run.collisions,
            "per_shell": collisions_by_shell,
            "per_second": run.collisions / duration,
            "peak_window": _peak_window(collision_times, thresholds.audio_window),
            "grazing": run.grazing_collisions,
            "ball_ball": run.ball_collisions,
        },
        "near_misses": {"total": run.near_misses},
        "damage": {
            "events": len(damages),
            "scoring_events": scoring_damage,
            "transitions": len(transitions),
            "transitions_by_state": transitions_by_state,
            "breaks": run.breaks,
            "breaks_per_shell": breaks_by_shell,
            "shared_breaks": shared_breaks,
            "cooperative_outer_breaks": outer_cooperative_breaks,
            "max_break_contributors": max(
                (detail["unique_contributing_balls"] for detail in break_details), default=0
            ),
            "break_details": break_details,
            "mean_break_cumulative": (
                sum(break_cumulative) / len(break_cumulative) if break_cumulative else 0.0
            ),
        },
        "routes": {
            "per_shell": route_by_shell,
            "progression_opening": progression_opening,
            "progression_break": progression_break,
        },
        "activity": {
            "collision_thirds": collision_thirds,
            "spawn_thirds": spawn_thirds,
            "break_thirds": break_thirds,
            "meaningful_thirds": meaningful_thirds,
            "meaningful_total": len(meaningful),
            "meaningful_per_second": len(meaningful) / duration,
            "meaningful_peak_window": _peak_window(meaningful_times, thresholds.audio_window),
        },
        "escalation": {
            "collisions": ratio(collision_thirds),
            "spawns": ratio(spawn_thirds),
            "breaks": ratio(break_thirds),
            "meaningful": ratio(meaningful_thirds),
            "population": (thirds_population[2] + 1.0) / (thirds_population[0] + 1.0),
        },
        "stagnation": {
            "longest_no_event": _longest_gap(meaningful_times, duration),
        },
        "repetition": {
            "longest_cycle_run": longest_cycle_run,
            "longest_cycle_period": longest_cycle_period,
            "distinct_panels": distinct_panels,
            "trajectory_spread": trajectory_spread,
        },
        "instruments": {
            "max_penetration": run.max_penetration,
            "min_spawn_clearance": run.min_spawn_clearance,
            "speed_min": run.speed_min,
            "speed_max": run.speed_max,
            "max_speed_correction": run.max_speed_correction,
            "mean_speed_correction": run.mean_speed_correction,
            "anomalous_crossings": run.anomalous_crossings,
            "newton_failures": run.newton_failures,
            "reproduction_violations": run.reproduction_violations,
        },
        "race": {
            "teams": list(TEAM_NAMES),
            "winner": winner,
            "winner_name": None if winner is None else TEAM_NAMES[winner],
            "winner_ball": run.escape_ball,
            # Which physical founder slot the winner descends from. A founder's
            # ball id is its slot, and a lineage starts at its founder, so this
            # is the head of the winner's lineage. It is the *implementation*
            # side of the fairness question, kept next to the colour so the two
            # can never be confused for each other.
            "winner_founder_slot": (
                None if run.escape_ball is None
                else int(run.balls[run.escape_ball].lineage[0])
            ),
            "winner_generation": run.winner_generation,
            "winner_route": run.winner_route,
            "win_margin_seconds": run.win_margin_seconds,
            "first_to_clone": first_to_clone,
            "first_spawn_by_team": first_spawn_by_team,
            "population_by_team": final_team_population,
            "population_share_winner": winner_share,
            "population_curve_by_team": team_curve,
            "population_by_second": team_by_second,
            "population_seconds": seconds,
            "spawns_by_team": list(run.team_spawns),
            "collisions_by_team": list(run.team_collisions),
            "crossings_by_team": crossings_by_team,
            "frontier_by_team": list(run.team_frontier),
            "loser_frontier": None if loser is None else run.team_frontier[loser],
            "damage_by_team": [round(v, 6) for v in run.team_damage],
            "breaks_by_team": list(run.team_breaks),
            "breaks_by_largest_team": breaks_by_largest_team,
            "cross_team_breaks": cross_team_breaks,
            "stolen_breaks": stolen_breaks,
            "population_lead_changes": run.population_lead_changes,
            "frontier_lead_changes": run.frontier_lead_changes,
            "max_population_lead": run.max_population_lead,
            "team_digest": run.team_digest(),
        },
        "config_digest": config.digest(),
        "digest": run.state_digest(),
    }

    flags: list[str] = []
    instruments = metrics["instruments"]
    if (
        instruments["anomalous_crossings"]
        or instruments["newton_failures"]
        or instruments["max_penetration"] > 1.0e-6
        or (
            instruments["min_spawn_clearance"] is not None
            and instruments["min_spawn_clearance"] <= 0.0
        )
    ):
        flags.append("instrument_fault")
    if violations or run.reproduction_violations:
        flags.append("spawn_farming")
    if not run.escaped:
        flags.append("failed")
    elif run.duration < thresholds.min_escape_seconds:
        flags.append("instant_escape")

    if len(run.balls) < thresholds.min_final_population:
        flags.append("population_weak")
    elif thirds_population[1] < thresholds.min_late_population:
        flags.append("population_weak")
    if early_population > thresholds.max_early_population:
        flags.append("population_explosive")
    if run.spawns_suppressed:
        flags.append("population_capped")
    if generations < thresholds.min_generations:
        flags.append("too_few_generations")
    if first_spawn is None or first_spawn > thresholds.max_first_spawn_seconds:
        flags.append("slow_first_spawn")

    # "Outer shell trivial" only means something when several balls got the
    # chance. "Outer shell impossible" and "difficulty inverted" are properties
    # of a configuration, not of a run: with four or five balls reaching a
    # shell, one run's pass rate is a coin flip, and flagging every run whose
    # coins landed out of order would reject most of a healthy population.
    # `summarise` carries both, measured over the whole batch.
    if reached[-1] >= 3 and pass_rate[-1] > thresholds.max_outer_pass_rate:
        flags.append("outer_shell_trivial")

    if metrics["collisions"]["peak_window"] > thresholds.max_peak_collision_rate:
        flags.append("frantic_peak")
    if metrics["collisions"]["per_second"] > thresholds.max_collision_rate:
        flags.append("frantic_mean")
    if metrics["collisions"]["per_second"] < thresholds.min_collision_rate:
        flags.append("sparse")
    if metrics["stagnation"]["longest_no_event"] > thresholds.max_stagnation_seconds:
        flags.append("dead_stretch")
    if metrics["escalation"]["meaningful"] < thresholds.min_escalation:
        flags.append("no_escalation")

    if (
        longest_cycle_run > thresholds.max_cycle_run
        and longest_cycle_period <= thresholds.max_cycle_period
    ):
        flags.append("repetitive_orbit")
    if distinct_panels < thresholds.min_distinct_panels:
        flags.append("few_distinct_panels")
    if trajectory_spread < thresholds.min_trajectory_spread:
        flags.append("clone_trajectories")

    if run.breaks < thresholds.min_breaks:
        flags.append("no_breaks")
    if progression_opening < thresholds.min_progression_openings:
        flags.append("no_opening_progress")

    if min(final_team_population) < thresholds.min_team_population:
        flags.append("team_starved")
    if loser is not None and run.team_frontier[loser] < thresholds.min_loser_frontier:
        flags.append("loser_stalled")
    if winner_share is not None and winner_share > thresholds.max_population_share:
        flags.append("one_sided")

    return RunEvaluation(seed=run.seed, metrics=metrics, flags=flags)


def evaluate_seed(
    seed: int,
    config: MultishellConfig = DEFAULT_CONFIG,
    thresholds: EvaluationThresholds = DEFAULT_THRESHOLDS,
) -> RunEvaluation:
    return evaluate(simulate(seed, config), thresholds)


# --------------------------------------------------------------------------
# Population statistics
# --------------------------------------------------------------------------


def _quantiles(values: Sequence[float], points: Sequence[float]) -> dict[str, float]:
    if not values:
        return {f"p{int(100 * p)}": float("nan") for p in points}
    ordered = sorted(values)
    out: dict[str, float] = {}
    for p in points:
        index = min(len(ordered) - 1, max(0, int(round(p * (len(ordered) - 1)))))
        out[f"p{int(100 * p)}"] = ordered[index]
    return out


def _histogram(values: Sequence[float], edges: Sequence[float]) -> dict[str, int]:
    out: dict[str, int] = {}
    for lo, hi in zip(edges, edges[1:]):
        out[f"{lo:g}-{hi:g}"] = sum(1 for v in values if lo <= v < hi)
    out[f">={edges[-1]:g}"] = sum(1 for v in values if v >= edges[-1])
    return out


def _race_summary(
    evaluations: Sequence[RunEvaluation],
    escaped: Sequence[RunEvaluation],
    points: Sequence[float],
) -> dict[str, Any]:
    """Who won, how often, and whether the split is anything but a coin.

    Two different questions and they need separate answers:

    * **Colour.** How often cyan won. This is what the viewer sees, and it is
      what "no colour-dependent physics" has to show up in. It is also the one
      the labelling coin makes unbiased by construction, so a deviation here is
      either the coin or the sample.
    * **Slot.** How often physical founder *slot 0* won. This is the
      implementation question: slot 0 is ball 0, its heading is drawn first and
      its id breaks scheduling ties. A deviation here is a real asymmetry in
      the simulation, and reporting it separately is what stops the coin from
      laundering it.

    Both come with a two-sided binomial z, so "281 of 538" can be read as
    "+1.03 sigma" rather than argued about.
    """
    count = len(TEAM_NAMES)
    wins = [0] * count
    slot_wins = [0] * count
    for e in escaped:
        winner = e.metrics["race"]["winner"]
        if winner is not None:
            wins[int(winner)] += 1
        slot = e.metrics["race"]["winner_founder_slot"]
        if slot is not None and int(slot) < count:
            slot_wins[int(slot)] += 1

    def z(head: int, total: int) -> float:
        if total <= 0:
            return float("nan")
        return (head - 0.5 * total) / (math.sqrt(total) * 0.5)

    total_wins = sum(wins)
    total_slots = sum(slot_wins)

    def flat(key: str) -> list[float]:
        return [e.metrics["race"][key] for e in evaluations]

    return {
        "teams": list(TEAM_NAMES),
        "wins_by_team": wins,
        "win_rate_by_team": [w / total_wins if total_wins else 0.0 for w in wins],
        "team_win_z": z(wins[0], total_wins),
        "wins_by_founder_slot": slot_wins,
        "slot_win_z": z(slot_wins[0], total_slots),
        "first_to_clone_by_team": [
            sum(1 for e in evaluations if e.metrics["race"]["first_to_clone"] == i)
            for i in range(count)
        ],
        "population_by_team_mean": [
            sum(e.metrics["race"]["population_by_team"][i] for e in evaluations)
            / max(1, len(evaluations))
            for i in range(count)
        ],
        "damage_by_team_mean": [
            sum(e.metrics["race"]["damage_by_team"][i] for e in evaluations)
            / max(1, len(evaluations))
            for i in range(count)
        ],
        "population_lead_changes": _quantiles(flat("population_lead_changes"), points),
        "population_lead_change_histogram": _histogram(
            flat("population_lead_changes"), (0, 1, 2, 3, 4, 6)
        ),
        "frontier_lead_changes": _quantiles(flat("frontier_lead_changes"), points),
        "max_population_lead": _quantiles(flat("max_population_lead"), points),
        "win_margin_seconds": _quantiles(
            [e.metrics["race"]["win_margin_seconds"] for e in escaped], points
        ),
        "win_margin_histogram": _histogram(
            [e.metrics["race"]["win_margin_seconds"] for e in escaped],
            (0, 1, 2, 4, 8, 12, 18),
        ),
        "winner_population_share": _quantiles(
            [e.metrics["race"]["population_share_winner"] for e in escaped], points
        ),
        "cross_team_breaks": _quantiles(flat("cross_team_breaks"), points),
        "cross_team_break_runs": sum(
            1 for e in evaluations if e.metrics["race"]["cross_team_breaks"]
        ),
        "stolen_breaks": _quantiles(flat("stolen_breaks"), points),
        "stolen_break_runs": sum(
            1 for e in evaluations if e.metrics["race"]["stolen_breaks"]
        ),
        "winner_generation": _quantiles(
            [e.metrics["race"]["winner_generation"] for e in escaped], points
        ),
        "winner_route": {
            route: sum(1 for e in escaped if e.metrics["race"]["winner_route"] == route)
            for route in ("opening", "break", "anomaly", "none")
        },
        "founder_wins": sum(
            1 for e in escaped if e.metrics["race"]["winner_generation"] == 0
        ),
        "descendant_wins": sum(
            1 for e in escaped if (e.metrics["race"]["winner_generation"] or 0) > 0
        ),
    }


def summarise(
    evaluations: Sequence[RunEvaluation],
    thresholds: EvaluationThresholds = DEFAULT_THRESHOLDS,
) -> dict[str, Any]:
    """The distributions a batch is read from, not a verdict on it."""
    total = len(evaluations)
    if total == 0:
        return {"count": 0}
    escaped = [e for e in evaluations if e.escaped]
    usable = [e for e in evaluations if e.usable]
    in_band = [
        e
        for e in escaped
        if thresholds.acceptable_low <= e.duration <= thresholds.acceptable_high
    ]
    preferred = [
        e
        for e in escaped
        if thresholds.preferred_low <= e.duration <= thresholds.preferred_high
    ]
    n_shells = evaluations[0].metrics["outcome"]["shell_count"]
    points = (0.05, 0.25, 0.5, 0.75, 0.95)

    def metric(path: Sequence[str], source: Sequence[RunEvaluation] = evaluations) -> list[float]:
        out = []
        for e in source:
            node: Any = e.metrics
            for key in path:
                node = node[key]
            out.append(node)
        return out

    flag_counts = {name: 0 for name in FLAG_NAMES}
    for e in evaluations:
        for flag in e.flags:
            flag_counts[flag] = flag_counts.get(flag, 0) + 1

    def per_shell(path: Sequence[str], source: Sequence[RunEvaluation]) -> list[float]:
        if not source:
            return [float("nan")] * n_shells
        out = []
        for k in range(n_shells):
            values = []
            for e in source:
                node: Any = e.metrics
                for key in path:
                    node = node[key]
                values.append(node[k])
            out.append(sum(values) / len(values))
        return out

    return {
        "count": total,
        "escaped": len(escaped),
        "escape_rate": len(escaped) / total,
        "usable": len(usable),
        "usable_rate": len(usable) / total,
        "in_band": len(in_band),
        "in_band_rate": len(in_band) / total,
        "preferred": len(preferred),
        "preferred_rate": len(preferred) / total,
        "failure_reasons": {
            reason: sum(
                1 for e in evaluations if e.metrics["outcome"]["failure_reason"] == reason
            )
            for reason in ("timeout", "collision_cap")
        },
        "duration": _quantiles(metric(["outcome", "duration"], escaped), points),
        "duration_histogram": _histogram(
            metric(["outcome", "duration"], escaped), (0, 6, 10, 14, 18, 20, 22, 24, 26)
        ),
        "population_total": _quantiles(metric(["population", "total"]), points),
        "population_max": _quantiles(metric(["population", "max"]), points),
        "population_histogram": _histogram(
            metric(["population", "max"]), (1, 4, 7, 10, 13, 16, 20, 24, 28, 32)
        ),
        "population_curve": [
            sum(e.metrics["population"]["curve"][i] for e in evaluations) / total
            for i in range(11)
        ],
        "population_curve_in_band": (
            [
                sum(e.metrics["population"]["curve"][i] for e in in_band) / len(in_band)
                for i in range(11)
            ]
            if in_band
            else []
        ),
        "generations": _quantiles(metric(["population", "generations"]), points),
        "spawns": _quantiles(metric(["reproduction", "spawns"]), points),
        "first_spawn": _quantiles(
            [v for v in metric(["reproduction", "first_spawn"]) if v is not None], points
        ),
        "never_reproduced": sum(
            1 for e in evaluations if e.metrics["reproduction"]["first_spawn"] is None
        ),
        "spawns_by_shell": per_shell(["reproduction", "by_shell"], evaluations),
        "reproduction_violations": sum(metric(["reproduction", "violations"])),
        "reached_by_shell": per_shell(["progression", "reached"], evaluations),
        "crossed_by_shell": per_shell(["progression", "crossed"], evaluations),
        "pass_rate_by_shell": per_shell(["difficulty", "pass_rate"], evaluations),
        "blocked_by_shell": per_shell(["difficulty", "blocked_contacts"], evaluations),
        "dwell_by_region": [
            sum(e.metrics["progression"]["dwell"][k] for e in evaluations) / total
            for k in range(n_shells + 1)
        ],
        "damage_by_shell": per_shell(["difficulty", "damage_absorbed"], evaluations),
        "breaks": _quantiles(metric(["damage", "breaks"]), points),
        "breaks_by_shell": per_shell(["damage", "breaks_per_shell"], evaluations),
        "shared_breaks": _quantiles(metric(["damage", "shared_breaks"]), points),
        "shared_break_runs": sum(1 for e in evaluations if e.metrics["damage"]["shared_breaks"]),
        "cooperative_outer_breaks": sum(
            metric(["damage", "cooperative_outer_breaks"])
        ),
        "cooperative_outer_break_runs": sum(
            1 for e in evaluations if e.metrics["damage"]["cooperative_outer_breaks"]
        ),
        "max_break_contributors": _quantiles(
            metric(["damage", "max_break_contributors"]), points
        ),
        "collision_rate": _quantiles(metric(["collisions", "per_second"]), points),
        "collision_rate_histogram": _histogram(
            metric(["collisions", "per_second"]), (0, 2, 4, 6, 8, 10, 12, 16)
        ),
        "peak_collision_rate": _quantiles(metric(["collisions", "peak_window"]), points),
        "peak_collision_histogram": _histogram(
            metric(["collisions", "peak_window"]), (0, 4, 8, 10, 12, 16, 20, 26)
        ),
        "meaningful_rate": _quantiles(metric(["activity", "meaningful_per_second"]), points),
        "meaningful_peak": _quantiles(metric(["activity", "meaningful_peak_window"]), points),
        "escalation_meaningful": _quantiles(metric(["escalation", "meaningful"]), points),
        "escalation_collisions": _quantiles(metric(["escalation", "collisions"]), points),
        "escalation_population": _quantiles(metric(["escalation", "population"]), points),
        "escalation_above_one": sum(
            1 for e in evaluations if e.metrics["escalation"]["meaningful"] > 1.0
        )
        / total,
        "route_progression": {
            "opening": sum(metric(["routes", "progression_opening"])),
            "break": sum(metric(["routes", "progression_break"])),
        },
        "escape_route": {
            route: sum(1 for e in escaped if e.metrics["outcome"]["escape_route"] == route)
            for route in ("opening", "break", "anomaly")
        },
        "escape_generation": _quantiles(
            [e.metrics["outcome"]["escape_generation"] for e in escaped], points
        ),
        "difficulty_increasing": sum(
            1 for e in evaluations if e.metrics["difficulty"]["increasing"]
        )
        / total,
        # The configuration-level verdicts. A single run cannot answer either of
        # these: the per-run pass rate is four or five Bernoulli trials.
        "pass_rate_monotonic": all(
            a >= b - 1.0e-12
            for a, b in zip(
                per_shell(["difficulty", "pass_rate"], evaluations),
                per_shell(["difficulty", "pass_rate"], evaluations)[1:],
            )
        ),
        "outer_shell_reached_rate": sum(
            1 for e in evaluations if e.metrics["progression"]["reached"][-1] > 0
        )
        / total,
        "outer_shell_crossed_rate": sum(
            1 for e in evaluations if e.metrics["progression"]["crossed"][-1] > 0
        )
        / total,
        "race": _race_summary(evaluations, escaped, points),
        "stagnation": _quantiles(metric(["stagnation", "longest_no_event"]), points),
        "trajectory_spread": _quantiles(metric(["repetition", "trajectory_spread"]), points),
        "instruments": {
            "max_penetration": max(metric(["instruments", "max_penetration"])),
            "min_spawn_clearance": min(
                (
                    v
                    for v in metric(["instruments", "min_spawn_clearance"])
                    if v is not None
                ),
                default=None,
            ),
            "max_speed_correction": max(metric(["instruments", "max_speed_correction"])),
            "mean_speed_correction": sum(metric(["instruments", "mean_speed_correction"]))
            / total,
            "speed_min": min(metric(["instruments", "speed_min"])),
            "speed_max": max(metric(["instruments", "speed_max"])),
            "anomalous_crossings": sum(metric(["instruments", "anomalous_crossings"])),
            "newton_failures": sum(metric(["instruments", "newton_failures"])),
            "reproduction_violations": sum(
                metric(["instruments", "reproduction_violations"])
            ),
        },
        "flags": flag_counts,
        "in_band_flags": {
            name: sum(1 for e in in_band if name in e.flags) for name in FLAG_NAMES
        },
        "thresholds": thresholds.as_dict(),
    }

"""What happened in a battle, reduced to a handful of numbers.

`BattleMetrics` is the whole interface between a simulated battle and any
judgement of it. It is deliberately small and scalar: the point is to run
thousands of battles and keep only what a decision needs, not to archive
them. Everything that varies per tick - who is ahead, how fast anyone is
going, what got touched - is folded in while the battle runs and thrown
away; everything discrete is read afterwards from the event stream the
battle mode already records.

Collecting these changes nothing. The collector only reads state, so a seed
plays out identically whether or not anyone is watching.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable

from engine.arena_layout import LAYOUT_PROCEDURAL
from engine.simulation import PHYSICS_DT, Simulation
from modes.events import EVENT_HIT, EVENT_POWER_ACTIVATE
from modes.power_battle import BATTLE_DURATION_TICKS, PowerBattleMode
from powers import PowerSpec

# Health difference below which neither fighter is called the leader. Without
# a dead band, two fighters trading a tenth of a point would register as
# hundreds of lead changes.
LEAD_THRESHOLD = 1.0

# How close two fighters have to be for the fight to read as close.
CLOSE_HEALTH_GAP = 20.0


@dataclass(frozen=True)
class BattleMetrics:
    """One finished battle, as the numbers a judgement can be made from."""

    seed: int
    arena_mode: str
    layout_id: str
    powers: tuple[str, ...]
    obstacles: int
    kinetic_obstacles: int

    # --- outcome ---
    winner_id: int | None
    is_draw: bool
    is_timeout: bool
    duration: float

    # --- action ---
    damaging_hits: int
    hits_by_subtype: tuple[tuple[str, int], ...]
    power_activations: int
    activating_fighters: int
    damaging_fighters: int
    first_hit_time: float | None
    longest_idle_gap: float

    # --- suspense ---
    lead_changes: int
    close_fraction: float
    winner_comeback: float
    final_health_gap: float
    winner_health: float

    # --- arena and physics ---
    max_fighter_speed: float
    obstacle_contacts: int
    distinct_obstacles_contacted: int
    kinetic_obstacle_contacts: int

    @property
    def is_elimination(self) -> bool:
        return not self.is_timeout and not self.is_draw

    @property
    def hit_subtypes(self) -> int:
        """How many different mechanisms actually drew blood."""
        return len(self.hits_by_subtype)

    @property
    def hit_rate(self) -> float:
        """Damaging hits per simulated second."""
        return self.damaging_hits / self.duration if self.duration > 0.0 else 0.0

    def subtype_count(self, subtype: str) -> int:
        return dict(self.hits_by_subtype).get(subtype, 0)


@dataclass
class _Collector:
    """Per-tick aggregation. Holds counters, never a history."""

    ticks: int = 0
    close_ticks: int = 0
    lead_state: int = 0
    lead_changes: int = 0
    max_speed: float = 0.0
    # Worst health deficit each fighter ever faced, by fighter id. The winner
    # is not known until the end, so both sides are tracked and the answer is
    # picked afterwards.
    max_deficit: dict[int, float] = field(default_factory=dict)
    contacts: int = 0
    kinetic_contacts: int = 0
    touched: set[int] = field(default_factory=set)

    def observe_health(self, first_health: float, second_health: float) -> None:
        """Fold one tick of the health picture in.

        Separated from the rest because this is the fiddly part - a lead only
        counts as changing hands when it really does - and it is worth being
        able to drive it from a scripted series of health values.
        """
        self.ticks += 1
        difference = first_health - second_health

        if abs(difference) <= CLOSE_HEALTH_GAP:
            self.close_ticks += 1

        # Outside the dead band the leader is whoever is ahead; inside it the
        # previous leader is kept, so drifting through equality and back is
        # not a lead change while crossing it properly is exactly one.
        if difference > LEAD_THRESHOLD:
            leader = 1
        elif difference < -LEAD_THRESHOLD:
            leader = -1
        else:
            leader = self.lead_state
        if leader != self.lead_state:
            # Taking the lead from nobody is not taking it from anyone.
            if self.lead_state != 0:
                self.lead_changes += 1
            self.lead_state = leader

        # Fighter ids are their index, so 0 and 1 here are RED and BLUE.
        self.max_deficit[0] = max(self.max_deficit.get(0, 0.0), -difference)
        self.max_deficit[1] = max(self.max_deficit.get(1, 0.0), difference)

    def sample(self, sim: Simulation, kinetic_ids: frozenset[int]) -> None:
        first, second = sim.balls[0], sim.balls[1]
        self.observe_health(first.health, second.health)

        for ball in sim.balls:
            self.max_speed = max(self.max_speed, ball.velocity.length)

        for contact in sim.obstacle_contacts:
            self.contacts += 1
            self.touched.add(contact.obstacle_id)
            if contact.obstacle_id in kinetic_ids:
                self.kinetic_contacts += 1


def collect_metrics(sim: Simulation, mode: PowerBattleMode) -> BattleMetrics:
    """Run `mode` to its end and reduce the whole battle to `BattleMetrics`."""
    kinetic_ids = frozenset(spec.obstacle_id for spec in sim.layout.kinetic)
    collector = _Collector()

    while not mode.finished:
        mode.step()
        collector.sample(sim, kinetic_ids)

    return _finish(sim, mode, collector)


def _finish(
    sim: Simulation, mode: PowerBattleMode, collector: _Collector
) -> BattleMetrics:
    hits = [event for event in mode.events if event.type == EVENT_HIT]
    activations = [
        event for event in mode.events if event.type == EVENT_POWER_ACTIVATE
    ]
    finished_tick = mode.finished_tick or 0
    duration = finished_tick * PHYSICS_DT

    winner_id = None if mode.winner is None else mode.winner.ball_id
    first, second = sim.balls[0], sim.balls[1]

    return BattleMetrics(
        seed=sim.seed,
        arena_mode=sim.arena_mode,
        layout_id=sim.layout.layout_id,
        powers=mode.matchup,
        obstacles=len(sim.layout),
        kinetic_obstacles=len(sim.layout.kinetic),
        winner_id=winner_id,
        is_draw=mode.is_draw,
        is_timeout=finished_tick >= BATTLE_DURATION_TICKS,
        duration=duration,
        damaging_hits=len(hits),
        hits_by_subtype=_subtype_counts(hits),
        power_activations=len(activations),
        activating_fighters=len({event.source_id for event in activations}),
        damaging_fighters=len(
            {event.source_id for event in hits if event.source_id is not None}
        ),
        first_hit_time=hits[0].tick * PHYSICS_DT if hits else None,
        longest_idle_gap=_longest_idle_gap(hits, finished_tick),
        lead_changes=collector.lead_changes,
        close_fraction=(
            collector.close_ticks / collector.ticks if collector.ticks else 0.0
        ),
        winner_comeback=(
            0.0 if winner_id is None else collector.max_deficit.get(winner_id, 0.0)
        ),
        final_health_gap=abs(first.health - second.health),
        winner_health=0.0 if mode.winner is None else mode.winner.health,
        max_fighter_speed=collector.max_speed,
        obstacle_contacts=collector.contacts,
        distinct_obstacles_contacted=len(collector.touched),
        kinetic_obstacle_contacts=collector.kinetic_contacts,
    )


def _subtype_counts(hits: Iterable) -> tuple[tuple[str, int], ...]:
    """Damaging hits per mechanism, sorted so the result is deterministic."""
    counts = Counter(event.subtype for event in hits if event.subtype is not None)
    return tuple(sorted(counts.items()))


def _longest_idle_gap(hits: list, finished_tick: int) -> float:
    """The longest stretch of the battle with no damage in it, in seconds.

    Measured across the whole battle, so the wait before the first hit and
    the silence after the last one both count: a fight that stops happening
    for ten seconds is dull whether that is at the start, the middle or the
    end.
    """
    longest = 0
    previous = 0
    for event in hits:
        longest = max(longest, event.tick - previous)
        previous = event.tick
    return max(longest, finished_tick - previous) * PHYSICS_DT


def evaluate_seed(
    seed: int,
    arena_mode: str = LAYOUT_PROCEDURAL,
    powers: Iterable[PowerSpec] | None = None,
) -> BattleMetrics:
    """Run one seeded battle headlessly and return only its metrics."""
    sim = Simulation(seed, arena_mode=arena_mode)
    return collect_metrics(sim, PowerBattleMode(sim, powers=powers))

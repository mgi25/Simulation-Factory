"""One race: the core's fixed-step loop, plus the things a race needs to know.

`marble3d.MarbleSimulation` steps the engine, watches and writes down, and it
already does most of this - the tick clock, the seeded slot permutation, the
contact stream, the energy proxy, the module occupancy, the replay. What it
does not have is any notion of a *course*: which of two routes a marble took,
how far round it has got, who is leading at halfway, when it crossed a finish
line that is not the end of the machine.

This adds those four and nothing else. The physics is untouched: no marble is
pushed, damped, corrected or helped out of a jam here either.

## Route, from contact rather than from a bounding box

`Machine.module_at` decides occupancy from module AABBs with the smallest box
winning, and that cannot tell this course's two branches apart: blue's lobe
runs west to x = -15 and orange's east to x = +21, and their boxes overlap over
a third of their extent because both return to the middle. So a route is
decided by what a marble has *touched*. The first frame in which it is in
contact with a collider owned by a branch module fixes its route for the run,
and `sloped.course.BRANCH_MODULES` is the map.

That is also the honest definition. A marble's route is the channel it ran in,
not the box it was inside.

## Progress, and why it is arc length and not distance to the finish

Rank at a checkpoint has to mean the same thing for two marbles on different
branches, and straight-line distance to the finish does not: blue's lobe swings
20 units further west than orange's ever goes, so a blue marble level with an
orange one is 15 units further from the finish while being exactly as far
round. So progress is **arc length along the route the marble is actually on**,
accumulated run by run, and the two routes' totals differ by 5.7% - which is
recorded rather than normalised away, because it is one of the two things the
route balance is made of.

The nearest sample is found in a window around the last one rather than by
searching all 800, and it is done every fourth tick rather than every tick.
Both are what make a thousand-seed benchmark affordable: at 240 Hz over 25
seconds the search is six thousand ticks times eight marbles times
twenty-nine candidates, and a rank does not need 240 Hz - the course's own
sample spacing is half a marble diameter and a marble covers a quarter of one
in four ticks. A marble that leaves the channel and falls loses its window and
keeps its last progress, which is what a rank should do for a marble that is
no longer racing.

The contact stream is read once. `MarbleSimulation._read_contacts` already
fetches it to count collisions and track penetration, and asking Bullet for it
a second time to build the touch map doubled the cost of the most expensive
call in the loop.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

from marble3d.config import CoreConfig, DEFAULT_CONFIG, REPLAY_FPS
from marble3d.machine import Machine
from marble3d.replay import (
    STATE_ESCAPED,
    STATE_FINISHED,
    Event,
    MarbleInfo,
    Replay,
)
from marble3d.simulation import MarbleSimulation, environment_metadata
from marble3d.units import GRAVITY, MARBLE_RADIUS, describe as describe_units

from sloped import joins, scale
from sloped.course import BRANCH_MODULES, sloped_course

__all__ = [
    "ROUTE_RUNS",
    "CHECKPOINTS",
    "RacerResult",
    "RaceOutcome",
    "SlopedRace",
    "run_race",
]

# The runs each route is made of, in flow order. The shared prefix is listed on
# both, so a marble's progress is comparable from the first tick.
ROUTE_RUNS = {
    "blue": ("launch", "leg1", "leg2", "leg3", "blue_lead", "blue", "final"),
    "orange": ("launch", "leg1", "leg2", "leg3", "orange_lead", "orange", "final"),
}

# Where a rank is taken, as a fraction of the route. Section 27 asks for the
# leader at a quarter, a half and three quarters and whether they went on to
# win; the first descent and the mixer are added because sections 15 and 16 ask
# for slot bias *early*, before the course has had time to shuffle anything.
CHECKPOINTS = (("descent", 0.09), ("mixed", 0.20), ("quarter", 0.25), ("half", 0.50), ("three_quarter", 0.75))

# How far outside its own channel a marble has to be before it counts as having
# left it. Half a diameter of lateral slack past the wall, or a diameter above
# the guard: enough that riding up a banked wall in a hairpin is not a failure,
# little enough that a marble on the far side of the wall always is.
LATERAL_SLACK = 0.5 * 2.0 * MARBLE_RADIUS
VERTICAL_SLACK = 2.0 * MARBLE_RADIUS


@dataclass
class RacerResult:
    marble_id: int
    start_slot: int
    route: str | None = None
    finish_order: int | None = None
    finish_time: float | None = None
    state: str = "running"
    progress: float = 0.0
    top_speed: float = 0.0
    ranks: dict[str, int] = field(default_factory=dict)
    lost_at: tuple[str, int] | None = None
    lost_time: float | None = None
    last_touch: tuple[str, int] | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "marble": self.marble_id,
            "slot": self.start_slot,
            "route": self.route,
            "order": self.finish_order,
            "time": None if self.finish_time is None else round(self.finish_time, 6),
            "state": self.state,
            "progress": round(self.progress, 4),
            "top_speed": round(self.top_speed, 4),
            "ranks": dict(self.ranks),
            "lost_at": list(self.lost_at) if self.lost_at else None,
            "last_touch": list(self.last_touch) if self.last_touch else None,
            "lost_time": None if self.lost_time is None else round(self.lost_time, 6),
        }


@dataclass
class RaceOutcome:
    seed: int
    seconds: float = 0.0
    wall_seconds: float = 0.0
    racers: list[RacerResult] = field(default_factory=list)
    finished: int = 0
    escaped: int = 0
    stuck: int = 0
    collisions: int = 0
    lead_changes: int = 0
    overtakes: int = 0
    top_speed: float = 0.0
    max_travel_per_tick: float = 0.0
    worst_penetration: float = 0.0
    route_counts: dict[str, int] = field(default_factory=dict)
    route_times: dict[str, list[float]] = field(default_factory=dict)
    winner_lock_time: float | None = None
    leader_series: list[tuple[float, int]] = field(default_factory=list)
    failure: str | None = None

    # --- race quality, section 27 -------------------------------------

    def winner(self) -> RacerResult | None:
        for racer in self.racers:
            if racer.finish_order == 1:
                return racer
        return None

    def winner_lock_fraction(self) -> float | None:
        if self.winner_lock_time is None or self.seconds <= 0.0:
            return None
        return self.winner_lock_time / self.seconds

    def final_margin(self) -> float | None:
        times = sorted(r.finish_time for r in self.racers if r.finish_time is not None)
        return None if len(times) < 2 else times[1] - times[0]

    def spread(self) -> float:
        """Range of progress at the moment the winner finished, in route units."""
        values = [r.progress for r in self.racers]
        return max(values) - min(values) if values else 0.0

    def winner_worst_rank(self) -> int | None:
        champion = self.winner()
        if champion is None or not champion.ranks:
            return None
        return max(champion.ranks.values())

    def to_json(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "seconds": round(self.seconds, 6),
            "wall_seconds": round(self.wall_seconds, 4),
            "finished": self.finished,
            "escaped": self.escaped,
            "stuck": self.stuck,
            "collisions": self.collisions,
            "lead_changes": self.lead_changes,
            "overtakes": self.overtakes,
            "top_speed": round(self.top_speed, 4),
            "max_travel_per_tick": round(self.max_travel_per_tick, 5),
            "worst_penetration": round(self.worst_penetration, 5),
            "route_counts": dict(self.route_counts),
            "route_times": {k: [round(v, 4) for v in vs] for k, vs in self.route_times.items()},
            "winner_lock_time": None
            if self.winner_lock_time is None
            else round(self.winner_lock_time, 4),
            "winner_lock_fraction": None
            if self.winner_lock_fraction() is None
            else round(self.winner_lock_fraction(), 4),
            "final_margin": None if self.final_margin() is None else round(self.final_margin(), 4),
            "winner_worst_rank": self.winner_worst_rank(),
            "failure": self.failure,
            "racers": [r.to_json() for r in self.racers],
        }


class SlopedRace(MarbleSimulation):
    """`MarbleSimulation` with a course under it."""

    WINDOW = 14          # samples either side of the last known position
    LOCATE_EVERY = 4     # ticks; see the module docstring

    def __init__(
        self,
        machine: Machine | None = None,
        config: CoreConfig | None = None,
        seed: int = 0,
        marble_count: int = 8,
    ) -> None:
        machine = machine or sloped_course(config)
        super().__init__(machine, config, seed, marble_count)
        self.runs = machine.runs                              # type: ignore[attr-defined]
        self.finish_line = machine.finish_line                # type: ignore[attr-defined]

        # A route the machine does not carry every run of is simply not on
        # offer, so `sloped_course(routes="blue")` needs no other change here.
        self.offsets: dict[str, dict[str, float]] = {}
        self.route_length: dict[str, float] = {}
        for route, names in ROUTE_RUNS.items():
            if any(name not in self.runs for name in names):
                continue
            total = 0.0
            table: dict[str, float] = {}
            for name in names:
                table[name] = total
                total += self.runs[name].sim_arc[-1]
            self.offsets[route] = table
            self.route_length[route] = total
        if not self.offsets:
            raise ValueError("the machine carries no complete route")
        self.default_route = "blue" if "blue" in self.offsets else next(iter(self.offsets))

        self.results = {
            marble_id: RacerResult(marble_id=marble_id, start_slot=marble.start_index)
            for marble_id, marble in self.marbles.items()
        }
        self._contacts: list = []
        self._where: dict[int, tuple[str, int]] = {}
        # The last place a marble was in contact with something, which is where
        # it left the course. The `escaped` position that `marble3d` records is
        # wherever the fall ended, thirty units below and twenty along.
        self._last_touch: dict[int, tuple[str, int, float]] = {}
        self._crossed: set[int] = set()
        self._finish_count = 0
        self._leader: int | None = None
        self.lead_changes = 0
        self.overtakes = 0
        self.leader_series: list[tuple[float, int]] = []
        self._rank_order: list[int] = []
        self._checkpoints_done: set[str] = set()

    # --- where a marble is ----------------------------------------------

    def _route_from_place(self, marble_id: int) -> str | None:
        """The route a marble is committed to, or None while it is still open.

        Not "the first branch collider it touched", which is what this was and
        which was wrong: the two branch channels *overlap* through the fork - at
        the nose they are the same channel - so every marble touches orange's
        lead there whichever way it ends up going. Over 32 seeds that attributed
        125 of 225 marbles to orange and then reported ten of them lost on
        leg3's tail, which is blue's route.

        A marble is committed when it is located on a run only one route uses,
        past the samples where the two still share floor.
        """
        place = self._where.get(marble_id)
        if place is None:
            return None
        run, sample = place
        if run in ("blue_lead", "blue"):
            return "blue"
        if "orange_lead" not in self.runs:
            return "blue" if run in self.runs else None
        if run == "orange":
            return "orange"
        if run == "orange_lead" and sample > joins.FORK_WINDOW_ORANGE:
            return "orange"
        if run == "leg3" and sample > joins.FORK_SAMPLE + joins.FORK_GUARD_WINDOW[3]:
            return "blue"
        return None

    def _route_of(self, marble_id: int) -> str:
        route = self.results[marble_id].route
        return route if route in self.offsets else self.default_route

    def _locate(self, marble_id: int, position: Sequence[float], touched: set[str]) -> None:
        """Update a marble's run, sample and progress from what it touched.

        The candidate runs are whatever it is in contact with, plus wherever it
        was last frame - so a marble in free flight between two channels keeps
        its place instead of jumping to whichever centreline happens to be
        nearest in a straight line.
        """
        result = self.results[marble_id]
        route = ROUTE_RUNS[self._route_of(marble_id)]
        route = tuple(name for name in route if name in self.runs)
        previous = self._where.get(marble_id)
        candidates = [name for name in route if name in touched]
        if previous and previous[0] not in candidates:
            candidates.append(previous[0])
        if not candidates:
            return

        best: tuple[float, str, int] | None = None
        for name in candidates:
            run = self.runs[name]
            if previous and previous[0] == name:
                low = max(0, previous[1] - self.WINDOW)
                high = min(len(run.sim_path), previous[1] + self.WINDOW + 1)
            else:
                low, high = 0, len(run.sim_path)
            for index in range(low, high):
                distance = math.dist(position, run.sim_path[index])
                if best is None or distance < best[0]:
                    best = (distance, name, index)
        if best is None:
            return
        _distance, name, index = best
        self._where[marble_id] = (name, index)
        offsets = self.offsets[self._route_of(marble_id)]
        if name in offsets:
            progress = offsets[name] + self.runs[name].sim_arc[index]
            # Monotonic: a marble that runs back up the merge apron has not
            # un-raced the course it already covered, and a rank that goes
            # backwards there would report the apron as an overtake.
            result.progress = max(result.progress, progress)

    def _containment(self, marble_id: int, position: Sequence[float]) -> None:
        """Note the run and sample where a marble was last inside its channel."""
        place = self._where.get(marble_id)
        if place is None:
            return
        name, index = place
        run = self.runs[name]
        lateral, up, _forward = run.frames[index]
        centre = run.sim_path[index]
        offset = [position[axis] - centre[axis] for axis in range(3)]
        across = sum(offset[axis] * lateral[axis] for axis in range(3))
        height = sum(offset[axis] * up[axis] for axis in range(3))
        half = 0.5 * run.clear_width * run.widths[index]
        result = self.results[marble_id]
        if abs(across) > half + LATERAL_SLACK or height > run.containment + VERTICAL_SLACK:
            if result.lost_at is None:
                result.lost_at = (name, index)
                result.lost_time = self.elapsed
                self.events.append(
                    Event(
                        self.elapsed,
                        "left_channel",
                        {
                            "id": marble_id,
                            "run": name,
                            "sample": index,
                            "across": round(across, 4),
                            "height": round(height, 4),
                        },
                    )
                )

    # --- the loop --------------------------------------------------------

    def _read_contacts(self) -> None:
        # The parent's own contact pass, with the list kept so the touch map
        # below does not have to ask Bullet for it again.
        self._contacts = self.world.contacts()
        super()._read_contacts()

    def step(self) -> None:
        super().step()
        if self.ticks % self.LOCATE_EVERY:
            return
        touched: dict[int, set[str]] = {}
        for contact in getattr(self, "_contacts", ()):
            for body, other in ((contact.body_a, contact.body_b), (contact.body_b, contact.body_a)):
                marble_id = self.world.marble_of(body)
                if marble_id is None:
                    continue
                if self.world.marble_of(other) is None:
                    touched.setdefault(marble_id, set()).add(self.world.owner_of(other))

        for marble_id in list(self.world.marbles):
            marble = self.marbles[marble_id]
            result = self.results[marble_id]
            hits = touched.get(marble_id, set())
            self._locate(marble_id, marble.pose[0], hits)
            if result.route is None:
                route = self._route_from_place(marble_id)
                if route is not None:
                    result.route = route
                    self.events.append(
                        Event(self.elapsed, "route", {"id": marble_id, "route": route})
                    )
            if hits:
                place = self._where.get(marble_id)
                if place is not None:
                    self._last_touch[marble_id] = (place[0], place[1], self.elapsed)
            self._containment(marble_id, marble.pose[0])
            result.top_speed = marble.top_speed
            if marble_id not in self._crossed and self._past_line(marble.pose[0]):
                self._crossed.add(marble_id)
                self._finish_count += 1
                result.finish_order = self._finish_count
                result.finish_time = self.elapsed
                result.progress = self.route_length[self._route_of(marble_id)]
                self.events.append(
                    Event(
                        self.elapsed,
                        "finish_line",
                        {
                            "id": marble_id,
                            "order": result.finish_order,
                            "slot": result.start_slot,
                            "route": result.route,
                        },
                    )
                )

        self._watch_order()

    def _past_line(self, position: Sequence[float]) -> bool:
        """The sprint's own exit socket, as a gate rather than a half-space.

        The same construction `marble3d.simulation._past_finish` uses and for
        the same reason: the exit plane of a course that has turned through 250
        degrees cuts back through the course, so a plane test is true for half
        the field on tick one.
        """
        frame = self.finish_line.frame
        flow, up, across = frame.axes()
        offset = tuple(p - q for p, q in zip(position, frame.position))
        along = sum(a * b for a, b in zip(offset, flow))
        if not 0.0 < along < 6.0 * MARBLE_RADIUS:
            return False
        sideways = abs(sum(a * b for a, b in zip(offset, across)))
        height = sum(a * b for a, b in zip(offset, up))
        diameter = 2.0 * MARBLE_RADIUS
        return (
            sideways <= 0.5 * self.finish_line.width + diameter
            and -diameter <= height <= self.finish_line.height + 3.0 * diameter
        )

    def _watch_order(self) -> None:
        """Leader, lead changes and overtakes, from the progress ordering."""
        live = sorted(
            self.results.values(),
            key=lambda r: (-(r.finish_order or 0) if r.finish_order else 1, -r.progress),
        )
        order = [
            r.marble_id
            for r in sorted(
                self.results.values(),
                key=lambda r: (r.finish_order if r.finish_order else 99, -r.progress),
            )
        ]
        if order and order[0] != self._leader:
            if self._leader is not None:
                self.lead_changes += 1
            self._leader = order[0]
            self.leader_series.append((self.elapsed, order[0]))
        if self._rank_order:
            place = {marble: index for index, marble in enumerate(self._rank_order)}
            for index, marble in enumerate(order):
                if marble in place and place[marble] > index:
                    self.overtakes += 1
        self._rank_order = order

        # Checkpoint ranks, taken the first time the leader passes each mark.
        if not order:
            return
        leader = self.results[order[0]]
        route = self.route_length[self._route_of(order[0])]
        for name, fraction in CHECKPOINTS:
            if name in self._checkpoints_done:
                continue
            if leader.progress >= fraction * route:
                self._checkpoints_done.add(name)
                for rank, marble in enumerate(order, start=1):
                    self.results[marble].ranks[name] = rank


def run_race(
    seed: int = 0,
    machine: Machine | None = None,
    config: CoreConfig | None = None,
    marble_count: int = 8,
    duration: float | None = None,
    with_replay: bool = False,
) -> tuple[RaceOutcome, Replay | None]:
    """One seed, run to the finish or to the limit.

    `with_replay` is off by default because a replay is 800-odd frames of eight
    marbles and a benchmark of a thousand seeds does not want them; the
    selected seed is re-run with it on, which costs one race.
    """
    config = config or DEFAULT_CONFIG
    race = SlopedRace(machine, config, seed, marble_count)
    limit = config.duration_limit if duration is None else duration
    max_ticks = int(round(limit * config.physics.physics_hz))
    started = time.perf_counter()
    energy: list[tuple[float, float]] = []

    try:
        if with_replay:
            race.frames.append(race.sample())
            energy.append((0.0, race.energy()))
        while race.ticks < max_ticks and not race.finished:
            race.step()
            if with_replay and race.ticks % race.stride == 0:
                race.frames.append(race.sample())
                energy.append((race.elapsed, race.energy()))
        if with_replay and race.ticks % race.stride:
            race.frames.append(race.sample())

        outcome = RaceOutcome(seed=seed)
        outcome.seconds = race.elapsed
        outcome.wall_seconds = time.perf_counter() - started
        outcome.collisions = race.stats.collisions
        outcome.top_speed = race.stats.top_speed
        outcome.max_travel_per_tick = race.stats.max_travel_per_tick
        outcome.worst_penetration = race.stats.worst_penetration
        outcome.lead_changes = race.lead_changes
        outcome.overtakes = race.overtakes
        outcome.leader_series = list(race.leader_series)

        for marble_id, marble in sorted(race.marbles.items()):
            result = race.results[marble_id]
            if result.finish_order is not None:
                result.state = STATE_FINISHED
            elif marble.state == STATE_ESCAPED:
                result.state = STATE_ESCAPED
            else:
                result.state = "stuck"
            touch = race._last_touch.get(marble_id)
            if touch is not None:
                result.last_touch = (touch[0], touch[1])
                if result.state != STATE_FINISHED:
                    result.lost_time = touch[2]
            outcome.racers.append(result)

        outcome.finished = sum(1 for r in outcome.racers if r.state == STATE_FINISHED)
        outcome.escaped = sum(1 for r in outcome.racers if r.state == STATE_ESCAPED)
        outcome.stuck = sum(1 for r in outcome.racers if r.state == "stuck")
        for result in outcome.racers:
            key = result.route or "unrouted"
            outcome.route_counts[key] = outcome.route_counts.get(key, 0) + 1
            if result.finish_time is not None:
                outcome.route_times.setdefault(key, []).append(result.finish_time)

        champion = outcome.winner()
        if champion is not None:
            # The last moment the eventual winner was not in front. Section 27's
            # winner-lock time: how much of the race was still open.
            lock = 0.0
            for when, leader in race.leader_series:
                if leader != champion.marble_id:
                    lock = when
            outcome.winner_lock_time = lock
        if outcome.finished < len(outcome.racers):
            outcome.failure = (
                f"{outcome.escaped} escaped, {outcome.stuck} still in the machine "
                f"after {outcome.seconds:.1f} s"
            )

        replay = None
        if with_replay:
            replay = _replay_of(race, config, outcome, energy)
        return outcome, replay
    finally:
        race.close()


def _replay_of(
    race: SlopedRace, config: CoreConfig, outcome: RaceOutcome, energy: list[tuple[float, float]]
) -> Replay:
    """The authoritative record, in simulation units, with the render scale in it.

    Section 31's list, plus two fields the sloped course needs and the bowl
    machine did not: `units.render_scale`, which is the one number Godot applies
    (on one node, so a missed multiply is a marble at the wrong size *and* the
    wrong place, which is visible immediately), and `race`, which carries the
    slot, route, rank and finish time the renderer's cameras are cut from.
    """
    replay = Replay(
        seed=race.seed,
        physics_hz=config.physics.physics_hz,
        replay_fps=REPLAY_FPS,
        units={
            "length": "world unit (wu)",
            "time": "s",
            "mass": "marble",
            "gravity": GRAVITY,
            "frame": "+Y up, gravity -Y, course laid out in XZ",
            "render_scale": scale.SIM_TO_LAYOUT,
            "layout_marble_radius": scale.LAYOUT_MARBLE_RADIUS,
            "note": describe_units() + "\n" + scale.describe(),
        },
        config=config.to_json(),
        machine=race.machine.to_json(),
        environment=environment_metadata(),
        marbles=[
            MarbleInfo(
                marble_id=marble.marble_id,
                radius=config.marble.radius,
                mass=config.marble.mass,
                start_index=marble.start_index,
            )
            for marble in sorted(race.marbles.values(), key=lambda m: m.marble_id)
        ],
        frames=race.frames,
        events=race.events,
        summary=race.stats.to_json(),
    )
    replay.summary["energy_series"] = [[round(w, 6), round(v, 6)] for w, v in energy]
    replay.summary["race"] = outcome.to_json()
    replay.summary["fork_sample"] = joins.FORK_SAMPLE
    replay.summary["route_length"] = {k: round(v, 4) for k, v in race.route_length.items()}
    return replay

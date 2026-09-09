"""The split and the merge on their own, entered on purpose rather than by luck.

## Why this exists

`docs/sloped_race_v1.md` reports the orange route as unreachable to a completed
finish, over 600 races and six divider configurations. What it cannot report is
*where* an orange-bound marble dies, because a full race never deliberately
puts one on the orange side of the ridge - it waits for one to arrive there,
and the arrivals are whatever the upstream course happens to deliver.

Section 10 of the brief asks for the other experiment: launch marbles into the
split at chosen lateral positions, chosen realistic speeds and chosen approach
angles, and require confirmed completion of **both** branches through the
merge. That is a controlled entry test, and it is the only way to tell three
different failures apart:

* the fork never sends a marble down orange at all (a sorting failure);
* it does, and the marble is lost on the lead or the lobe (a containment
  failure);
* it reaches the merge and the merge will not pass it (a junction failure).

V1's six configurations were all scored on the first of those. This scores all
three separately.

## What it builds

leg3 from a chosen sample, the fork ridge, both leads, both lobes, the merge
catch and the final sprint - the real modules from `sloped.course`, at their
real placements, so a geometry change measured here is the change the course
gets. The upstream 175 simulation units are not built: an `Injector` stands in
for them, placing a marble on leg3's centreline at a lateral offset and giving
it a velocity along the channel's own tangent.

## Why injecting a velocity is not cheating

Nothing here decides where a marble *goes*. The injector sets an initial
condition - a position, a speed and a heading - which is exactly what the
upstream course delivers and what `sloped.race` measures: the arrival at leg3's
fork sample is 41 to 43 wu/s along the tangent, spread across the channel. The
sweep covers that range and a margin either side of it. From the first tick the
marble is under the same physics as every other marble in the project.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

from marble3d.config import CoreConfig, DEFAULT_CONFIG
from marble3d.geometry import Socket, Transform, basis_from_forward_up
from marble3d.machine import Machine
from marble3d.mesh import Aabb, TriMesh
from marble3d.modules.base import MarbleModule
from marble3d.units import MARBLE_RADIUS

from sloped import joins, layout
from sloped.course import sloped_course
from sloped.race import LATERAL_SLACK, VERTICAL_SLACK

__all__ = [
    "Injector",
    "EntryOutcome",
    "split_machine",
    "SPEEDS",
    "OFFSETS",
    "entry_sweep",
    "summarise_sweep",
]

# The entry conditions to sweep. Speeds bracket the 43 wu/s `sloped.joins`
# measured at leg3's exit; offsets span the channel from wall to wall as a
# fraction of its clear half width, which is what "several lateral positions"
# has to mean in a 3.3-diameter channel.
SPEEDS = (30.0, 36.0, 43.0, 50.0)
OFFSETS = (-0.80, -0.50, -0.20, 0.0, 0.20, 0.50, 0.80)


class Injector(MarbleModule):
    """A start module that places marbles on a run, moving.

    It has no colliders and no actuators - it is a set of poses and nothing
    else - so it adds no geometry to the thing being measured. The velocities
    are handed to `SplitEntry` rather than to `marble_starts`, because
    `marble3d.simulation` places marbles at rest and a module cannot express
    a velocity through `Transform`.
    """

    def __init__(
        self,
        module_id: str,
        run,
        index: int,
        offsets: Sequence[float],
        speed: float,
        yaw_deg: float = 0.0,
    ) -> None:
        super().__init__(module_id)
        self.run = run
        self.index = int(index)
        self.offsets = tuple(float(v) for v in offsets)
        self.speed = float(speed)
        self.yaw_deg = float(yaw_deg)

    def _pose(self, offset: float):
        """(position, velocity) for one lane of the injector, in sim units."""
        run = self.run
        lateral, up, forward = run.frames[self.index]
        half = 0.5 * run.clear_width * run.widths[self.index]
        across = offset * (half - MARBLE_RADIUS)
        # `surface_point` takes an offset in *profile* units, which the run
        # scales; going through the frame directly keeps the sweep's offsets
        # meaning fractions of the clear half width on any run.
        contact = run.surface_point(self.index, across / run.clear_width * 2.0 * layout.CHANNEL_HALF)
        position = tuple(contact[axis] + up[axis] * MARBLE_RADIUS for axis in range(3))
        angle = math.radians(self.yaw_deg)
        heading = tuple(
            forward[axis] * math.cos(angle) + lateral[axis] * math.sin(angle) for axis in range(3)
        )
        velocity = tuple(heading[axis] * self.speed for axis in range(3))
        return position, velocity

    def marble_starts(self) -> list[Transform]:
        rotation = basis_from_forward_up(self.run.frames[self.index][2], self.run.frames[self.index][1])
        return [Transform(position=self._pose(o)[0], rotation=rotation) for o in self.offsets]

    def velocities(self) -> list[tuple[float, float, float]]:
        return [self._pose(o)[1] for o in self.offsets]

    def local_colliders(self) -> list[TriMesh]:
        return []

    def local_sockets(self) -> dict[str, Socket]:
        return {}

    def local_bounds(self) -> Aabb:
        point, _velocity = self._pose(0.0)
        reach = 4.0 * MARBLE_RADIUS
        return Aabb(
            tuple(point[axis] - reach for axis in range(3)),
            tuple(point[axis] + reach for axis in range(3)),
        )

    def describe(self) -> dict[str, Any]:
        return {
            "kind": "Injector",
            "on": self.run.id,
            "sample": self.index,
            "offsets": list(self.offsets),
            "speed": self.speed,
            "yaw_deg": self.yaw_deg,
        }


def split_machine(
    config: CoreConfig | None = None,
    speed: float = 43.0,
    offsets: Sequence[float] = OFFSETS,
    yaw_deg: float = 0.0,
    entry_back: int = 10,
) -> Machine:
    """The forked course with an injector in place of everything upstream.

    Built by taking `sloped_course(routes="both")` and replacing its start
    module, so the fork, the leads, the lobes, the merge and the sprint are the
    shipped objects rather than copies of them. `entry_back` is how many leg3
    samples upstream of the fork the marbles appear: ten samples is 2.9 layout
    units, enough that a marble is settled in the cradle and carrying its own
    spin before it reaches the nose.
    """
    config = config or DEFAULT_CONFIG
    full = sloped_course(config, routes="both")
    runs = full.runs                                      # type: ignore[attr-defined]

    machine = Machine("sloped_b_split_entry")
    injector = Injector(
        "inject",
        runs["leg3"],
        max(0, joins.FORK_SAMPLE - entry_back),
        offsets,
        speed,
        yaw_deg,
    )
    machine.add(injector, Transform())
    for name in (
        "leg3", "fork", "blue_lead", "blue", "orange_lead", "orange",
        "merge_lead", "merge", "final",
    ):
        machine.add(full.modules[name], Transform())
    machine.add(full.modules["finish"], Transform())
    machine.runs = runs                                   # type: ignore[attr-defined]
    machine.injector = injector                           # type: ignore[attr-defined]
    machine.finish_line = runs["final"].socket("exit")    # type: ignore[attr-defined]
    return machine


def merge_machine(
    config: CoreConfig | None = None,
    speed: float = 30.0,
    offsets: Sequence[float] = OFFSETS,
    yaw_deg: float = 0.0,
    entry_at: int = 96,
) -> Machine:
    """Blue's tail, the merge apron and the sprint, entered on purpose.

    The section D test: `blue[100..119]` was the course's dominant loss site in
    both V1 and V1.1, and in V1.1 the marbles lost there came to rest at the
    same point to two decimals. A trap that reproducible is a shape, and a
    shape is testable directly rather than by waiting for a full race to
    deliver a slow enough marble.

    `speed` defaults to 30 rather than the 41 the lobes self-limit to, because
    the marbles that stopped were the slow ones - a step only catches what
    cannot climb it, and a sweep that only launches fast marbles proves nothing
    about a step.
    """
    config = config or DEFAULT_CONFIG
    full = sloped_course(config, routes="both")
    runs = full.runs                                      # type: ignore[attr-defined]

    machine = Machine("sloped_b_merge_entry")
    injector = Injector("inject", runs["blue"], entry_at, offsets, speed, yaw_deg)
    machine.add(injector, Transform())
    for name in ("blue", "merge_lead", "merge", "final"):
        machine.add(full.modules[name], Transform())
    machine.add(full.modules["finish"], Transform())
    machine.runs = runs                                   # type: ignore[attr-defined]
    machine.injector = injector                           # type: ignore[attr-defined]
    machine.finish_line = runs["final"].socket("exit")    # type: ignore[attr-defined]
    return machine


@dataclass
class EntryOutcome:
    """What became of one injected marble."""

    offset: float
    speed: float
    yaw_deg: float
    route: str | None = None
    reached_lobe: bool = False
    reached_merge: bool = False
    finished: bool = False
    lost_at: tuple[str, int] | None = None
    stopped_at: tuple[str, int] | None = None
    time: float | None = None
    visited: list[str] = field(default_factory=list)

    def verdict(self) -> str:
        if self.finished:
            return "finished"
        if self.lost_at is not None:
            return "left"
        if self.stopped_at is not None:
            return "stopped"
        return "running"

    def to_json(self) -> dict[str, Any]:
        return {
            "offset": self.offset,
            "speed": self.speed,
            "yaw_deg": self.yaw_deg,
            "route": self.route,
            "reached_lobe": self.reached_lobe,
            "reached_merge": self.reached_merge,
            "finished": self.finished,
            "verdict": self.verdict(),
            "lost_at": list(self.lost_at) if self.lost_at else None,
            "stopped_at": list(self.stopped_at) if self.stopped_at else None,
            "time": None if self.time is None else round(self.time, 4),
            "visited": list(self.visited),
        }


# The runs each route is made of downstream of the injector, so a marble's
# furthest point along its own branch can be named.
# `merge_lead` is on both, because it is shared: blue runs down it and an
# orange marble through the back wall's opening runs up it. Same rule and same
# reason as `sloped.race.ROUTE_RUNS`.
_BLUE_CHAIN = ("leg3", "blue_lead", "blue", "merge_lead", "final")
_ORANGE_CHAIN = ("leg3", "orange_lead", "orange", "merge_lead", "final")


class SplitEntry:
    """One injected field: as many marbles as there are offsets, all at once.

    They are launched together because that is what the course delivers - eight
    marbles inside three channel widths - and because a sweep that launched
    them one at a time would answer a question about an empty fork.
    `entry_sweep` also runs each offset alone, and the difference between the
    two is reported.
    """

    LOCATE_EVERY = 4
    STOPPED_SPEED = 1.5          # wu/s, under which a marble is not racing
    STOPPED_FOR = 240            # ticks it has to stay there

    def __init__(self, machine: Machine, config: CoreConfig | None = None) -> None:
        from marble3d.simulation import MarbleSimulation

        self.config = config or DEFAULT_CONFIG
        self.machine = machine
        self.injector = machine.injector                  # type: ignore[attr-defined]
        self.runs = machine.runs                          # type: ignore[attr-defined]
        self.sim = MarbleSimulation(machine, self.config, 0, len(self.injector.offsets))

        # `marble3d.simulation` places marbles at rest; give them the injector's
        # velocity before the first step so the sweep's speeds mean something.
        for marble_id, marble in self.sim.marbles.items():
            velocity = self.injector.velocities()[marble.start_index]
            self.sim.world.pybullet.resetBaseVelocity(
                self.sim.world.marbles[marble_id],
                linearVelocity=[float(v) for v in velocity],
                angularVelocity=[0.0, 0.0, 0.0],
                physicsClientId=self.sim.world.client,
            )

        self.outcomes = {
            marble_id: EntryOutcome(
                offset=self.injector.offsets[marble.start_index],
                speed=self.injector.speed,
                yaw_deg=self.injector.yaw_deg,
            )
            for marble_id, marble in self.sim.marbles.items()
        }
        self._where: dict[int, tuple[str, int]] = {}
        self._slow: dict[int, int] = {}
        self._crossed: set[int] = set()

    def _route_of(self, marble_id: int) -> str | None:
        return self.outcomes[marble_id].route

    def _chain(self, marble_id: int) -> tuple[str, ...]:
        """The runs this marble may be located on - all of them until it commits.

        Same rule and same reason as `sloped.race._runs_open_to`: filtering the
        search by a route the marble has not chosen yet is what made the orange
        lobe unreachable on paper.
        """
        route = self._route_of(marble_id)
        if route == "orange":
            return _ORANGE_CHAIN
        if route == "blue":
            return _BLUE_CHAIN
        return ("leg3", "blue_lead", "blue", "orange_lead", "orange", "merge_lead")

    def _locate(self, marble_id: int, position, touched: set[str]) -> None:
        previous = self._where.get(marble_id)
        candidates = [name for name in self._chain(marble_id) if name in touched]
        if previous and previous[0] not in candidates:
            candidates.append(previous[0])
        if not candidates:
            return
        best = None
        for name in candidates:
            run = self.runs[name]
            if previous and previous[0] == name:
                low = max(0, previous[1] - 14)
                high = min(len(run.sim_path), previous[1] + 15)
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
        outcome = self.outcomes[marble_id]
        if not outcome.visited or outcome.visited[-1] != name:
            outcome.visited.append(name)
        # Route, from where the marble *is*, past the samples the two channels
        # still share floor. Same rule as `sloped.race._route_from_place`.
        if outcome.route is None:
            if name in ("blue_lead", "blue"):
                outcome.route = "blue"
            elif name == "orange":
                outcome.route = "orange"
            elif name == "orange_lead" and index > joins.FORK_WINDOW_ORANGE:
                outcome.route = "orange"
            elif name == "leg3" and index > joins.FORK_SAMPLE + joins.FORK_GUARD_WINDOW[3]:
                outcome.route = "blue"
        if name in ("blue", "orange"):
            outcome.reached_lobe = True
            if index >= len(self.runs[name].sim_path) - 6:
                outcome.reached_merge = True
        if name in ("merge_lead", "final"):
            outcome.reached_merge = True

    def _outside(self, run_name: str, index: int, position) -> float:
        """How far outside one run's channel a point is, in simulation units.

        Zero or negative means inside. Lateral and vertical excess are taken
        as a max rather than summed, because either alone is enough.
        """
        run = self.runs[run_name]
        index = min(max(index, 0), len(run.sim_path) - 1)
        lateral, up, _forward = run.frames[index]
        centre = run.sim_path[index]
        offset = [position[axis] - centre[axis] for axis in range(3)]
        across = sum(offset[axis] * lateral[axis] for axis in range(3))
        height = sum(offset[axis] * up[axis] for axis in range(3))
        half = 0.5 * run.clear_width * run.widths[index]
        return max(
            abs(across) - (half + LATERAL_SLACK),
            height - (run.containment + VERTICAL_SLACK),
        )

    def _containment(self, marble_id: int, position) -> None:
        """A marble is lost when it is outside **every** channel, not one.

        Measuring it against only the run it is currently located on is what
        made the orange route unmeasurable here. Orange's mouth is a channel
        width east of leg3's centreline, so a marble crossing onto orange's
        floor is - correctly - two half-widths outside *leg3*, and the first
        version booked it as having left the course and then retired it in
        `done()` before it could land. Every one of the seven controlled
        entries reported `leg3[90..95]` for that reason and not because
        anything fell off the course.
        """
        place = self._where.get(marble_id)
        outcome = self.outcomes[marble_id]
        if place is None or outcome.lost_at is not None:
            return
        chain = self._chain(marble_id)
        nearest = min(
            (
                (self._outside(name, i, position), name, i)
                for name in chain
                for i in self._near(name, position)
            ),
            default=None,
        )
        if nearest is None or nearest[0] <= 0.0:
            return
        outcome.lost_at = (place[0], place[1])

    def _near(self, run_name: str, position) -> tuple[int, ...]:
        """The one sample of a run nearest a point, as a one-tuple.

        A full search rather than a windowed one, because this runs only for a
        marble that is already outside the channel it was located on - which is
        rare - and a window is exactly what would miss the channel it has
        crossed onto.
        """
        run = self.runs[run_name]
        best = min(
            range(len(run.sim_path)), key=lambda i: math.dist(position, run.sim_path[i])
        )
        return (best,)

    def step(self) -> None:
        sim = self.sim
        sim.step()
        contacts = sim.world.contacts()
        if sim.ticks % self.LOCATE_EVERY:
            return
        touched: dict[int, set[str]] = {}
        for contact in contacts:
            for body, other in ((contact.body_a, contact.body_b), (contact.body_b, contact.body_a)):
                marble_id = sim.world.marble_of(body)
                if marble_id is not None and sim.world.marble_of(other) is None:
                    touched.setdefault(marble_id, set()).add(sim.world.owner_of(other))
        for marble_id in list(sim.world.marbles):
            marble = sim.marbles[marble_id]
            position = marble.pose[0]
            self._locate(marble_id, position, touched.get(marble_id, set()))
            self._containment(marble_id, position)
            outcome = self.outcomes[marble_id]
            speed = math.hypot(*marble.pose[2])
            if speed < self.STOPPED_SPEED and outcome.lost_at is None:
                self._slow[marble_id] = self._slow.get(marble_id, 0) + self.LOCATE_EVERY
                if self._slow[marble_id] >= self.STOPPED_FOR and outcome.stopped_at is None:
                    outcome.stopped_at = self._where.get(marble_id)
            else:
                self._slow[marble_id] = 0
                outcome.stopped_at = None
            if marble_id not in self._crossed and self._past_line(position):
                self._crossed.add(marble_id)
                outcome.finished = True
                outcome.time = sim.elapsed

    def _past_line(self, position) -> bool:
        line = self.machine.finish_line                   # type: ignore[attr-defined]
        flow, up, across = line.frame.axes()
        offset = tuple(p - q for p, q in zip(position, line.frame.position))
        along = sum(a * b for a, b in zip(offset, flow))
        if not 0.0 < along < 6.0 * MARBLE_RADIUS:
            return False
        sideways = abs(sum(a * b for a, b in zip(offset, across)))
        height = sum(a * b for a, b in zip(offset, up))
        diameter = 2.0 * MARBLE_RADIUS
        return (
            sideways <= 0.5 * line.width + diameter
            and -diameter <= height <= line.height + 3.0 * diameter
        )

    def done(self) -> bool:
        return all(
            o.finished or o.lost_at is not None or o.stopped_at is not None
            for o in self.outcomes.values()
        )


def entry_sweep(
    speeds: Sequence[float] = SPEEDS,
    offsets: Sequence[float] = OFFSETS,
    yaws: Sequence[float] = (0.0,),
    config: CoreConfig | None = None,
    duration: float = 14.0,
    together: bool = True,
) -> list[EntryOutcome]:
    """Every (speed, offset, yaw) entry condition, as a list of outcomes.

    With `together` the offsets of one (speed, yaw) go in as one field, which is
    what the course delivers. Without it each offset is run alone, which
    separates a marble the fork cannot sort from a marble its neighbours pushed.
    """
    config = config or DEFAULT_CONFIG
    out: list[EntryOutcome] = []
    max_ticks = int(round(duration * config.physics.physics_hz))
    for speed in speeds:
        for yaw in yaws:
            groups = [tuple(offsets)] if together else [(o,) for o in offsets]
            for group in groups:
                machine = split_machine(config, speed=speed, offsets=group, yaw_deg=yaw)
                entry = SplitEntry(machine, config)
                try:
                    while entry.sim.ticks < max_ticks and not entry.done():
                        entry.step()
                    out.extend(entry.outcomes.values())
                finally:
                    # A sweep is a few hundred worlds; each one left open is a
                    # Bullet client that is never given back.
                    entry.sim.close()
    return out


def merge_sweep(
    speeds: Sequence[float] = (8.0, 12.0, 18.0, 25.0, 35.0),
    offsets: Sequence[float] = OFFSETS,
    config: CoreConfig | None = None,
    duration: float = 14.0,
    together: bool = True,
) -> list[EntryOutcome]:
    """Blue's tail through the merge, at speeds that bracket what stops there.

    The slow end matters more than the fast end here. 8 wu/s carries 0.13
    simulation units of climb and the step that was trapping marbles was 0.114,
    so a sweep that starts at 30 would have walked straight over the defect.
    """
    config = config or DEFAULT_CONFIG
    out: list[EntryOutcome] = []
    max_ticks = int(round(duration * config.physics.physics_hz))
    for speed in speeds:
        groups = [tuple(offsets)] if together else [(o,) for o in offsets]
        for group in groups:
            machine = merge_machine(config, speed=speed, offsets=group)
            entry = SplitEntry(machine, config)
            try:
                while entry.sim.ticks < max_ticks and not entry.done():
                    entry.step()
                out.extend(entry.outcomes.values())
            finally:
                entry.sim.close()
    return out


def summarise_sweep(outcomes: Sequence[EntryOutcome]) -> dict[str, Any]:
    """The three failures counted separately, per route.

    `sorted_to` counts where the fork put each marble; the rest is conditional
    on that, so a route with no entries reports no completion rate rather than
    a zero one - the difference between "the fork will not feed it" and "the
    channel will not carry it" is the whole question.
    """
    report: dict[str, Any] = {
        "entries": len(outcomes),
        "sorted_to": {},
        "unrouted": sum(1 for o in outcomes if o.route is None),
        "routes": {},
        "loss_sites": {},
    }
    for route in ("blue", "orange"):
        rows = [o for o in outcomes if o.route == route]
        report["sorted_to"][route] = len(rows)
        if not rows:
            report["routes"][route] = None
            continue
        finished = [o for o in rows if o.finished]
        report["routes"][route] = {
            "entries": len(rows),
            "reached_lobe": sum(1 for o in rows if o.reached_lobe),
            "reached_merge": sum(1 for o in rows if o.reached_merge),
            "finished": len(finished),
            "finished_pct": round(100.0 * len(finished) / len(rows), 2),
            "left": sum(1 for o in rows if o.verdict() == "left"),
            "stopped": sum(1 for o in rows if o.verdict() == "stopped"),
            "median_time": (
                round(sorted(o.time for o in finished)[len(finished) // 2], 4)
                if finished
                else None
            ),
        }
    for outcome in outcomes:
        # A finisher's `lost_at` is the finish deck: the sprint's last sample
        # hands over to `FinishDeck`, which is outside the channel by
        # construction, so every marble that crosses the line reports
        # `final[117]`. Counting those as losses put seven of them in the loss
        # map on the first run of the sweep.
        if outcome.finished:
            continue
        site = outcome.lost_at or outcome.stopped_at
        if site is None:
            continue
        key = f"{site[0]}[{site[1]}]"
        entry = report["loss_sites"].setdefault(key, {"left": 0, "stopped": 0})
        entry["left" if outcome.lost_at else "stopped"] += 1
    return report

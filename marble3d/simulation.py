"""The fixed-step loop: a machine, a seed, and the replay that comes out.

One authority for time, and it is the tick counter. `elapsed = ticks * dt` is
computed, never accumulated, so a twenty-second run does not carry four
thousand eight hundred floating-point additions of rounding into its clock;
actuator poses are functions of the tick; sampling is every `physics_hz /
replay_fps` ticks exactly. Nothing anywhere consults a wall clock, which is
what makes a run on a loaded machine the same run as a run on an idle one.

## What this module is responsible for and what it refuses

It steps the engine, watches, and writes down. It does not push a marble, damp
one, correct one, or help one out of a jam. Every behaviour in the output -
the orbit, the wall climb, the spiral, the drain order, the interleaving - is
Bullet's, or it is not there. Section 13 of the brief asks for that in the
bowl; it is easier to guarantee by making it true of the whole loop.

The one thing the loop *does* do to a marble is remove it, and only in two
circumstances: when it passes the finish plane, which is the end of the
machine, and when it leaves the machine's bounds entirely, which is a failure
and is recorded as one. A removed marble's last pose is held so the replay
stays rectangular - every frame has every marble - because a renderer that has
to handle a marble disappearing mid-array is a renderer with a bug waiting.

## Module occupancy

Which module a marble is "in" is decided by the machine's bounding boxes, with
the smallest box winning where they overlap. That is coarse and it is
deliberately coarse: the alternative is asking each module to answer for its
own interior, which means every module carrying a second geometric description
of itself that can drift from the first. Entry and exit events are therefore
"the marble crossed into this module's region", which is what a renderer and a
metric both want, and not "the marble touched this module's surface", which is
what the contact stream already says exactly.

## Energy

A proxy is tracked every frame: translation, rotation and height, summed over
the marbles still in the machine. After the gate has finished retracting there
is no source of energy in the machine at all, so the series must be
non-increasing to within the solver's own noise. `marble3d.validation` checks
it. It is the cheapest possible detector for the failure the lab found in the
2.5D model, where a positional overlap-correction pass became an energy source
under a pile-up and injected 202 J into a bowl.
"""

from __future__ import annotations

import math
import platform
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

from marble3d.config import REPLAY_FPS, CoreConfig, DEFAULT_CONFIG
from marble3d.geometry import Transform
from marble3d.machine import Machine
from marble3d.machines import start_bowl_curve
from marble3d.modules.base import BuiltModule
from marble3d.replay import (
    AIRBORNE,
    STATE_ESCAPED,
    STATE_FINISHED,
    STATE_QUEUED,
    STATE_RUNNING,
    Event,
    Frame,
    MarbleInfo,
    MarbleSample,
    Replay,
)
from marble3d.seeds import PLACEMENT_TOLERANCE, make_order_rng, make_placement_rng
from marble3d.units import GRAVITY, MARBLE_RADIUS, describe as describe_units
from marble3d.world import MarbleWorld

__all__ = ["MarbleSimulation", "simulate", "environment_metadata"]

# A marble-on-marble contact is reported as a collision when the closing speed
# along the contact normal exceeds this. 2 wu/s is 8 cm/s on the toy: below it
# marbles are jostling in a queue rather than hitting each other, and reporting
# those would bury the real impacts in a thousand nudges.
COLLISION_SPEED = 2.0

# How far past the exit socket the finish gate reaches. Four marble diameters
# against 0.17 wu of travel per tick at the speeds this machine produces, so a
# marble cannot pass through the gate between two ticks.
FINISH_CAPTURE_DEPTH = 4.0


def environment_metadata() -> dict[str, Any]:
    """What machine produced a run, for the cross-machine question.

    Section 25 of the brief: determinism was only ever measured on one machine,
    and the honest thing to do about that is to record which one, so that two
    digests taken a year apart on two continents can be compared as evidence
    rather than as a coincidence.
    """
    try:
        import pybullet

        build = pybullet.getAPIVersion()
    except Exception:  # pragma: no cover - only if the engine is missing
        build = None
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": sys.version.split()[0],
        "pybullet_api": build,
    }


@dataclass
class _Marble:
    marble_id: int
    start_index: int
    state: str = STATE_QUEUED
    module: str = AIRBORNE
    pose: tuple = ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    finish_order: int | None = None
    finish_time: float | None = None
    top_speed: float = 0.0


@dataclass
class RunStats:
    """Everything a batch run wants to sort on, without reading the frames."""

    ticks: int = 0
    sim_seconds: float = 0.0
    wall_seconds: float = 0.0
    finished: int = 0
    escaped: int = 0
    unfinished: int = 0
    collisions: int = 0
    top_speed: float = 0.0
    max_travel_per_tick: float = 0.0
    travel_budget: float = 0.0
    worst_penetration: float = 0.0
    energy_start: float = 0.0
    energy_end: float = 0.0
    max_energy_rise: float = 0.0
    finish_order: list[int] = field(default_factory=list)
    finish_times: list[float] = field(default_factory=list)
    failure: str | None = None

    def to_json(self) -> dict[str, Any]:
        return dict(self.__dict__)


class MarbleSimulation:
    """One run of one machine at one seed."""

    def __init__(
        self,
        machine: Machine | None = None,
        config: CoreConfig | None = None,
        seed: int = 0,
        marble_count: int | None = None,
    ) -> None:
        self.config = config or DEFAULT_CONFIG
        self.machine = machine or start_bowl_curve()
        self.seed = int(seed)
        self.dt = self.config.physics.dt
        self.stride = self.config.physics.ticks_per_replay_frame
        self.ticks = 0
        self.elapsed = 0.0

        self.world = MarbleWorld(self.config)
        self.built: list[BuiltModule] = self.machine.build(self.world)
        self._by_id = {record.module.id: record for record in self.built}

        self.start_module = self._require_start()
        starts = self.start_module.marble_starts()
        if marble_count is not None:
            if not 0 < marble_count <= len(starts):
                raise ValueError(
                    f"this start module has {len(starts)} slots and {marble_count} "
                    "were asked for; widen the chute or lower the count"
                )
            starts = starts[:marble_count]

        # The finish plane: the exit socket of the last module in flow order.
        finish_module = self.machine.modules[self.machine.order[-1]]
        self.finish_socket = finish_module.socket("exit")
        self.finish_module_id = finish_module.id

        self.marbles: dict[int, _Marble] = {}
        self._spawn(starts)

        self.events: list[Event] = []
        self.frames: list[Frame] = []
        self.stats = RunStats(travel_budget=self.config.marble.travel_budget * self.config.marble.diameter)
        self._touching: set[tuple[int, int]] = set()
        self._finish_count = 0
        self._retired_energy = 0.0
        self._settle_time = self._actuation_finishes()

    # --- setup -----------------------------------------------------------

    def _require_start(self) -> Any:
        for record in self.built:
            if hasattr(record.module, "marble_starts"):
                return record.module
        raise ValueError(
            f"machine {self.machine.name!r} has no module that can place marbles"
        )

    def _actuation_finishes(self) -> float:
        """When the last moving part stops doing work on the machine.

        Energy is only required to be non-increasing after this, because before
        it a gate is being retracted and a retracting gate can legitimately
        push a marble.
        """
        latest = 0.0
        for record in self.built:
            for actuator in record.module.local_actuators():
                finish = getattr(actuator, "release_time", 0.0) + getattr(actuator, "duration", 0.0)
                latest = max(latest, finish)
        return latest

    def _spawn(self, starts: Sequence[Transform]) -> None:
        """Place the field, in a seeded order, to a seeded placement tolerance.

        The permutation is over *slots*, so marble 3 may start at the front or
        the back; the tolerance is applied in the slot's own frame, so a lateral
        nudge is across the channel and a longitudinal one is along it whatever
        the chute's pitch and bank happen to be at that point.
        """
        order = list(range(len(starts)))
        make_order_rng(self.seed).shuffle(order)
        placement = make_placement_rng(self.seed)
        for slot, frame in enumerate(starts):
            marble_id = order[slot]
            jitter = Transform(
                (
                    placement.uniform(-PLACEMENT_TOLERANCE, PLACEMENT_TOLERANCE),
                    0.0,
                    placement.uniform(-PLACEMENT_TOLERANCE, PLACEMENT_TOLERANCE),
                )
            )
            placed = frame.compose(jitter)
            self.world.add_marble(marble_id, placed.position, orientation=placed.rotation)
            self.marbles[marble_id] = _Marble(
                marble_id=marble_id,
                start_index=slot,
                state=STATE_QUEUED,
                module=self.start_module.id,
                pose=(placed.position, placed.rotation, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
            )

    # --- the loop --------------------------------------------------------

    def step(self) -> None:
        for record in self.built:
            record.apply_actuators(self.world, self.ticks, self.dt)
        self.world.step()
        self.ticks += 1
        self.elapsed = self.ticks * self.dt

        self._read_contacts()
        self._read_marbles()

    def _read_contacts(self) -> None:
        touching: set[tuple[int, int]] = set()
        worst = self.stats.worst_penetration
        for contact in self.world.contacts():
            first = self.world.marble_of(contact.body_a)
            second = self.world.marble_of(contact.body_b)
            if contact.distance < worst:
                worst = contact.distance
            if first is None or second is None:
                continue
            pair = (min(first, second), max(first, second))
            if pair in touching:
                continue
            touching.add(pair)
            if pair in self._touching:
                continue
            velocity_a = self.marbles[pair[0]].pose[2]
            velocity_b = self.marbles[pair[1]].pose[2]
            closing = abs(
                sum((b - a) * n for a, b, n in zip(velocity_a, velocity_b, contact.normal))
            )
            if closing < COLLISION_SPEED:
                continue
            self.stats.collisions += 1
            self.events.append(
                Event(
                    time=self.elapsed,
                    kind="collision",
                    data={
                        "a": pair[0],
                        "b": pair[1],
                        "speed": round(closing, 6),
                        "at": [round(value, 6) for value in contact.position],
                    },
                )
            )
        self._touching = touching
        self.stats.worst_penetration = worst

    def _read_marbles(self) -> None:
        for marble_id in list(self.world.marbles):
            marble = self.marbles[marble_id]
            position, orientation, velocity, spin = self.world.marble_state(marble_id)
            if not all(math.isfinite(value) for value in position + velocity):
                self.stats.failure = f"marble {marble_id} left the real numbers"
                self._retire(marble_id, STATE_ESCAPED, "escaped")
                continue
            marble.pose = (position, orientation, velocity, spin)
            if marble.state == STATE_QUEUED and math.dist(velocity, (0.0, 0.0, 0.0)) > 0.5:
                marble.state = STATE_RUNNING
                self.events.append(
                    Event(self.elapsed, "release", {"id": marble_id, "slot": marble.start_index})
                )

            speed = math.dist(velocity, (0.0, 0.0, 0.0))
            if speed > marble.top_speed:
                marble.top_speed = speed
            if speed > self.stats.top_speed:
                self.stats.top_speed = speed

            where = self.machine.module_at(position, marble.module) or AIRBORNE
            if where != marble.module:
                if marble.module:
                    self.events.append(
                        Event(
                            self.elapsed,
                            "module_exit",
                            {"id": marble_id, "module": marble.module},
                        )
                    )
                if where:
                    self.events.append(
                        Event(self.elapsed, "module_enter", {"id": marble_id, "module": where})
                    )
                marble.module = where

            if self._past_finish(position):
                self._retire(marble_id, STATE_FINISHED, "finish")
            elif not self.machine.bounds().contains(position, slack=MARBLE_RADIUS):
                self.stats.failure = self.stats.failure or (
                    f"marble {marble_id} left the machine at "
                    f"{tuple(round(value, 2) for value in position)}"
                )
                self._retire(marble_id, STATE_ESCAPED, "escaped")

        self.stats.max_travel_per_tick = self.stats.top_speed * self.dt

    def _past_finish(self, position: Sequence[float]) -> bool:
        """Has the marble gone out through the machine's last exit socket?

        A *gate* in the socket's own frame, not a plane in world space, and the
        distinction is the whole of the method. The obvious implementation -
        "the marble is on the far side of the exit plane" - is a half-space,
        and the exit plane of a curve that has turned through 270 degrees cuts
        straight back through the curve's own middle. Every marble in the
        machine passes that test on the first tick, which is exactly what the
        first version of this did.

        So: past the plane, *and* inside the socket's cross-section, *and*
        within a few diameters of it. The window is generous - the fastest
        marble here covers 0.17 wu in a tick and the capture depth is 4 - so
        nothing can jump the gate, and it is local, so nothing can trip it from
        the other side of the module.
        """
        frame = self.finish_socket.frame
        flow, up, across = frame.axes()
        offset = tuple(p - q for p, q in zip(position, frame.position))
        along = sum(a * b for a, b in zip(offset, flow))
        if not 0.0 < along < FINISH_CAPTURE_DEPTH:
            return False
        sideways = abs(sum(a * b for a, b in zip(offset, across)))
        height = sum(a * b for a, b in zip(offset, up))
        marble = self.config.marble
        return (
            sideways <= 0.5 * self.finish_socket.width + marble.diameter
            and -marble.diameter <= height <= self.finish_socket.height + 3.0 * marble.diameter
        )

    def _retire(self, marble_id: int, state: str, kind: str) -> None:
        marble = self.marbles[marble_id]
        self._retired_energy += self._marble_energy(marble_id)
        position, orientation, _, _ = marble.pose
        marble.pose = (position, orientation, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
        marble.state = state
        if state == STATE_FINISHED:
            self._finish_count += 1
            marble.finish_order = self._finish_count
            marble.finish_time = self.elapsed
        self.world.remove_marble(marble_id)
        self.events.append(
            Event(
                self.elapsed,
                kind,
                {
                    "id": marble_id,
                    "order": marble.finish_order,
                    "at": [round(value, 6) for value in position],
                },
            )
        )

    # --- sampling --------------------------------------------------------

    def _marble_energy(self, marble_id: int) -> float:
        marble = self.config.marble
        position, _, velocity, spin = self.marbles[marble_id].pose
        return (
            0.5 * marble.mass * sum(value * value for value in velocity)
            + 0.5 * marble.inertia * sum(value * value for value in spin)
            + marble.mass * self.config.gravity * position[1]
        )

    def energy(self) -> float:
        """A mechanical-energy proxy for the field, retired marbles included.

        Translational plus rotational plus gravitational, with the marble mass
        as the unit of mass, so the number is in wu^2/s^2 per marble.

        A marble that has left the machine keeps contributing the energy it had
        when it left, frozen. Summing only the marbles still present looks
        right and is not: a marble finishing nine units below the origin is
        carrying about -2200 of gravitational potential, so removing it makes
        the total *rise* by 2200 and the series reports a 12 000-unit energy
        gain in a machine that has no energy source in it at all. Freezing the
        contribution keeps the sum comparable across a retirement, which is
        what makes "non-increasing" a check rather than a coincidence.
        """
        total = self._retired_energy
        for marble_id in self.world.marbles:
            total += self._marble_energy(marble_id)
        return total

    def sample(self) -> Frame:
        samples = []
        for marble_id in sorted(self.marbles):
            marble = self.marbles[marble_id]
            position, orientation, velocity, spin = marble.pose
            samples.append(
                MarbleSample(
                    marble_id=marble_id,
                    position=tuple(float(value) for value in position),
                    orientation=tuple(float(value) for value in orientation),
                    velocity=tuple(float(value) for value in velocity),
                    spin=tuple(float(value) for value in spin),
                    module=marble.module,
                    state=marble.state,
                )
            )
        actuators: dict[str, tuple] = {}
        for record in self.built:
            placement = record.module.transform
            for actuator in record.module.local_actuators():
                pose = placement.compose(actuator.pose_at(self.ticks, self.dt))
                actuators[f"{record.module.id}.{actuator.name}"] = (pose.position, pose.rotation)
        return Frame(time=self.elapsed, marbles=tuple(samples), actuators=actuators)

    @property
    def finished(self) -> bool:
        return not self.world.marbles

    def close(self) -> None:
        self.world.close()


def simulate(
    seed: int = 0,
    machine: Machine | None = None,
    config: CoreConfig | None = None,
    marble_count: int | None = None,
    duration: float | None = None,
) -> Replay:
    """Run one seed to completion and return its replay."""
    config = config or DEFAULT_CONFIG
    machine = machine or start_bowl_curve()
    simulation = MarbleSimulation(machine, config, seed, marble_count)
    limit = config.duration_limit if duration is None else duration
    max_ticks = int(round(limit * config.physics.physics_hz))
    started = time.perf_counter()

    energy_series: list[tuple[float, float]] = []
    try:
        simulation.frames.append(simulation.sample())
        energy_series.append((0.0, simulation.energy()))
        while simulation.ticks < max_ticks and not simulation.finished:
            simulation.step()
            if simulation.ticks % simulation.stride == 0:
                simulation.frames.append(simulation.sample())
                energy_series.append((simulation.elapsed, simulation.energy()))
        if simulation.ticks % simulation.stride:
            simulation.frames.append(simulation.sample())

        stats = simulation.stats
        stats.ticks = simulation.ticks
        stats.sim_seconds = simulation.elapsed
        stats.wall_seconds = time.perf_counter() - started
        stats.finished = sum(
            1 for marble in simulation.marbles.values() if marble.state == STATE_FINISHED
        )
        stats.escaped = sum(
            1 for marble in simulation.marbles.values() if marble.state == STATE_ESCAPED
        )
        stats.unfinished = len(simulation.marbles) - stats.finished - stats.escaped
        if stats.unfinished and stats.failure is None:
            stats.failure = (
                f"{stats.unfinished} marble(s) still in the machine after "
                f"{stats.sim_seconds:.1f} s"
            )
        ordered = sorted(
            (marble for marble in simulation.marbles.values() if marble.finish_order),
            key=lambda marble: marble.finish_order or 0,
        )
        stats.finish_order = [marble.marble_id for marble in ordered]
        stats.finish_times = [round(marble.finish_time or 0.0, 6) for marble in ordered]

        # Energy is only required to be non-increasing once the gate has stopped
        # moving; before that the machine has a moving part in it doing work.
        settled = [value for when, value in energy_series if when >= simulation._settle_time]
        if settled:
            stats.energy_start = settled[0]
            stats.energy_end = settled[-1]
            running = settled[0]
            for value in settled:
                stats.max_energy_rise = max(stats.max_energy_rise, value - running)
                running = min(running, value)

        replay = Replay(
            seed=simulation.seed,
            physics_hz=config.physics.physics_hz,
            replay_fps=REPLAY_FPS,
            units={
                "length": "world unit (wu)",
                "time": "s",
                "mass": "marble",
                "gravity": GRAVITY,
                "frame": "+Y up, gravity -Y, machine laid out in XZ",
                "note": describe_units(),
            },
            config=config.to_json(),
            machine=machine.to_json(),
            environment=environment_metadata(),
            marbles=[
                MarbleInfo(
                    marble_id=marble.marble_id,
                    radius=config.marble.radius,
                    mass=config.marble.mass,
                    start_index=marble.start_index,
                )
                for marble in sorted(simulation.marbles.values(), key=lambda m: m.marble_id)
            ],
            frames=simulation.frames,
            events=simulation.events,
            summary=stats.to_json(),
        )
        replay.summary["energy_series"] = [
            [round(when, 6), round(value, 6)] for when, value in energy_series
        ]
        return replay
    finally:
        simulation.close()

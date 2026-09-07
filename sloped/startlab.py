"""The start, on its own, so slot bias can be measured a hundred times an hour.

## Why this exists

`docs/sloped_race_v1.md` measured a start-slot win-rate ratio of **8.87** over
600 full races, and the same table showed the bias was already 3.6 places wide
at the 9% checkpoint and had decayed to 1.27 by three quarters. So the bias is
made at the start and merely *diluted* by the rest of the course. Diagnosing it
on full races costs 28 seconds of wall time a seed and spends 90% of that on
geometry that is not the suspect.

This builds the suspect alone - the eight bays, the gate, the fan, the
34-degree launch, and leg1 with its mixer - and runs it to an early checkpoint.
That is 95.7 simulation units of the route's 345.8, and it costs about a fifth
of a full race.

## What a trial measures

Per marble: the slot it started in, its arc progress at each checkpoint, its
rank there, the tick it left the start module's own footprint (the
first-transition exit order the brief asks for), how many marble-on-marble
contacts it had, and how many ticks it spent against a channel wall.

Per slot, aggregated over trials: mean rank, exit order, and the spread between
the strongest and weakest slot. Marble *identity* is permuted across slots by
`marble3d.seeds.make_order_rng` on every seed, so a slot's mean is already
averaged over which marble stood in it.

## Why the checkpoint is arc length and not time

Two marbles a metre apart on a 34-degree descent are not the same distance
apart along the channel, and a rank taken on distance-to-a-point would call the
inside of a hairpin ahead. `sloped.race` makes the same choice for the same
reason and this mirrors it, including the windowed nearest-sample search.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

from marble3d.config import CoreConfig, DEFAULT_CONFIG
from marble3d.geometry import Transform
from marble3d.machine import Machine
from marble3d.units import MARBLE_RADIUS

from sloped import course as _course
from sloped import layout
from sloped.race import LATERAL_SLACK, VERTICAL_SLACK
from sloped.stations import Mixer, Spinners, StartGrid
from sloped.track import TrackRun

__all__ = [
    "LAB_RUNS",
    "LAB_CHECKPOINTS",
    "StartPlan",
    "V1_PLAN",
    "SHIPPED_PLAN",
    "start_machine",
    "SlotRow",
    "TrialResult",
    "StartTrial",
    "run_trial",
    "summarise",
]

# The runs the lab carries, in flow order. leg1 is included whole because the
# mixer sits at its sample 3 - 1.22 layout units past the launch seam - and the
# question is what the field looks like *after* it has had room to spread.
LAB_RUNS = ("launch", "leg1")

# Arc marks, as a fraction of the lab's own length. `descent` is where the full
# course's 9% checkpoint falls (31.1 of 345.8 simulation units, which is 32.5%
# of the lab), and `exit` is the lab's end - 27.7% of the full route.
LAB_CHECKPOINTS = (("descent", 0.325), ("half", 0.60), ("exit", 0.98))

# How far down the lab a marble has to have got by the end of the trial to
# count as having come through the start. Below this it is trailing, whether
# it fell out, stopped dead or is merely grinding along behind something.
THROUGH_MARK = 0.85


@dataclass(frozen=True)
class StartPlan:
    """One candidate start geometry, as the few numbers that distinguish it.

    Everything here is physical geometry - where a divider ends, where a row of
    studs stands, how tall it is. There is deliberately no field for a per-slot
    anything: section 4 of the brief rules out scripted order, teleports,
    per-racer forces and per-lane marble properties, and a plan that could
    express one of those would make the scan able to cheat.
    """

    name: str = "v1"
    # How far along the fan each of the seven dividers runs, west to east.
    fins: tuple[float, ...] | None = None
    # How far down the fan each bay waits, in layout units, west to east.
    stagger: tuple[float, ...] | None = None
    # Studs on the trough floor, as (t along the fan, across as a fraction of
    # the half width there, height in layout units).
    deflectors: tuple[tuple[float, float, float], ...] | None = None
    # Stud rows, as (run name, sample, layout height). A sample of -1 means the
    # recorded `mix` node, which is where the V1 course's one row stands.
    mixers: tuple[tuple[str, int, float], ...] = (("leg1", -1, 0.07),)
    # Paddle wheels, as (run name, sample, rate in rad/s). One wheel each.
    wheels: tuple[tuple[str, int, float], ...] = ()

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "fins": list(self.fins) if self.fins else None,
            "stagger": list(self.stagger) if self.stagger else None,
            "deflectors": [list(d) for d in self.deflectors] if self.deflectors else None,
            "mixers": [list(m) for m in self.mixers],
            "wheels": [list(w) for w in self.wheels],
        }


# V1's start: one stud row on leg1 at the recorded `mix` node, nothing on the
# launch. Kept as the scan's baseline - `tools/sloped_start_scan.py` quotes
# every candidate against it - and not as anything the course still builds.
V1_PLAN = StartPlan(name="v1")

# What `sloped.course` builds. Read from the course's own constants rather than
# retyped, so the lab cannot drift away from the thing it is measuring.
SHIPPED_PLAN = StartPlan(
    name="shipped",
    mixers=(("launch", _course.MIXER_SAMPLE, Mixer.PIN_HEIGHT),),
    wheels=(("launch", _course.SHUFFLE_SAMPLE, _course.SHUFFLE_RATE),),
)


def start_machine(config: CoreConfig | None = None, plan: StartPlan | None = None) -> Machine:
    """The start, the launch and leg1, placed exactly as the full course places
    them.

    Identical *geometry* to `sloped.course.sloped_course` for these three
    modules - same `TrackRun` specs, same `StartGrid`, same `Mixer` on the same
    sample - so a geometry change measured here is the same change the full
    course gets. `tests/test_sloped_startlab.py` asserts that sample for
    sample.

    The one difference is declaration order: the mixer is declared before leg1
    rather than after it, because `marble3d.simulation` takes its finish plane
    from the last module in flow order and a `Mixer` has no exit socket. That
    changes Bullet's body numbering and therefore the exact trajectory of any
    single seed. It does not change the geometry, and what the lab is for is
    the *statistics* over a few hundred seeds - a slot's mean rank, averaged
    over which marble stood in it. Candidates are compared against each other
    in this instrument and then confirmed on full races.
    """
    config = config or DEFAULT_CONFIG
    plan = plan or SHIPPED_PLAN
    machine = Machine("sloped_b_start")
    runs = {name: TrackRun(name) for name in LAB_RUNS}
    machine.add(
        StartGrid(
            "start",
            runs["launch"],
            fin_schedule=plan.fins,
            bay_stagger=plan.stagger,
            deflectors=plan.deflectors,
        ),
        Transform(),
    )
    machine.add(runs["launch"], Transform())
    for order, (run_name, sample, height) in enumerate(plan.mixers):
        machine.add(
            Mixer(
                f"mixer{order}" if order else "mixer",
                runs[run_name],
                at=None if sample < 0 else sample,
                pin_height=height,
            ),
            Transform(),
        )
    for order, (run_name, sample, rate) in enumerate(plan.wheels):
        machine.add(
            Spinners(
                f"wheel{order}",
                runs[run_name],
                at=sample,
                offsets=(0.0,),
                rate=rate,
            ),
            Transform(),
        )
    machine.add(runs["leg1"], Transform())
    machine.plan = plan                                   # type: ignore[attr-defined]
    machine.runs = runs                                   # type: ignore[attr-defined]
    return machine


@dataclass
class SlotRow:
    slot: int
    trials: int = 0
    ranks: dict[str, list[int]] = field(default_factory=dict)
    exit_orders: list[int] = field(default_factory=list)
    progress: dict[str, list[float]] = field(default_factory=dict)
    collisions: list[int] = field(default_factory=list)
    wall_ticks: list[int] = field(default_factory=list)
    lost: int = 0
    stuck: int = 0
    trailing: int = 0

    def mean_rank(self, checkpoint: str) -> float | None:
        values = self.ranks.get(checkpoint) or []
        return sum(values) / len(values) if values else None

    def mean_exit_order(self) -> float | None:
        return sum(self.exit_orders) / len(self.exit_orders) if self.exit_orders else None

    def to_json(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "trials": self.trials,
            "mean_rank": {
                name: (None if self.mean_rank(name) is None else round(self.mean_rank(name), 4))
                for name, _ in LAB_CHECKPOINTS
            },
            "mean_exit_order": (
                None if self.mean_exit_order() is None else round(self.mean_exit_order(), 4)
            ),
            "mean_progress": {
                name: round(sum(v) / len(v), 4) for name, v in self.progress.items() if v
            },
            "mean_collisions": (
                round(sum(self.collisions) / len(self.collisions), 3) if self.collisions else None
            ),
            "mean_wall_ticks": (
                round(sum(self.wall_ticks) / len(self.wall_ticks), 2) if self.wall_ticks else None
            ),
            "lost": self.lost,
            "lost_pct": round(100.0 * self.lost / self.trials, 3) if self.trials else None,
            "stuck": self.stuck,
            "stuck_pct": round(100.0 * self.stuck / self.trials, 3) if self.trials else None,
            "trailing": self.trailing,
            "trailing_pct": round(100.0 * self.trailing / self.trials, 3) if self.trials else None,
        }


@dataclass
class TrialResult:
    seed: int
    seconds: float
    slot_of: dict[int, int]
    ranks: dict[str, dict[int, int]]
    progress: dict[str, dict[int, float]]
    exit_order: dict[int, int]
    collisions: dict[int, int]
    wall_ticks: dict[int, int]
    lost: dict[int, tuple[str, int]]
    stuck: dict[int, tuple[str, int]]
    # Final arc progress per marble, as a fraction of the lab's length. The
    # honest test of a start is whether the whole field got through it, and
    # neither "left the channel" nor "stopped dead" catches a marble that is
    # grinding along at 4 wu/s behind an obstruction with the leader long gone.
    through: dict[int, float]
    reached: int


class StartTrial:
    """One seed of the start lab. Deliberately not a `SlopedRace` subclass.

    `SlopedRace` needs a machine that carries a whole route - it builds route
    offset tables from `ROUTE_RUNS` and raises if none is complete - and a
    finish line. This has neither, and giving it a fake one so it could inherit
    would mean the thing being measured was not the thing that ships.
    """

    WINDOW = 14
    LOCATE_EVERY = 4

    def __init__(
        self,
        machine: Machine,
        config: CoreConfig | None = None,
        seed: int = 0,
        marble_count: int = 8,
    ) -> None:
        from marble3d.simulation import MarbleSimulation

        self.sim = MarbleSimulation(machine, config, seed, marble_count)
        self.runs: dict[str, TrackRun] = machine.runs      # type: ignore[attr-defined]
        self.offsets: dict[str, float] = {}
        total = 0.0
        for name in LAB_RUNS:
            self.offsets[name] = total
            total += self.runs[name].sim_arc[-1]
        self.length = total

        self.slot_of = {mid: m.start_index for mid, m in self.sim.marbles.items()}
        self.progress: dict[int, float] = {mid: 0.0 for mid in self.slot_of}
        self.collisions: dict[int, int] = {mid: 0 for mid in self.slot_of}
        self.wall_ticks: dict[int, int] = {mid: 0 for mid in self.slot_of}
        self.lost: dict[int, tuple[str, int]] = {}
        # A marble that has stopped is as lost to a race as one that fell off,
        # and the first version of this lab could not see the difference:
        # `wheel-6.0-early` scored 0.55% lost here and then put 17.2% of the
        # full course's field into the "stuck" column, all of it at launch[0],
        # because a paddle wheel at the launch entry holds a slow field up. A
        # lab that cannot see a jam cannot be used to choose a jamming part.
        self.stuck: dict[int, tuple[str, int]] = {}
        self._slow: dict[int, int] = {}
        self._where: dict[int, tuple[str, int]] = {}
        self._left_start: dict[int, int] = {}
        self.ranks: dict[str, dict[int, int]] = {}
        self.checkpoint_progress: dict[str, dict[int, float]] = {}
        self._done: set[str] = set()

    # --- the loop -------------------------------------------------------

    def _locate(self, marble_id: int, position: Sequence[float], touched: set[str]) -> None:
        """`sloped.race._locate`, restricted to the lab's two runs.

        Contact-gated for the same reason the full course gates it: a marble
        still standing in the start fan is 4.4 layout units across a trough
        that hands off to a 1.88 channel, so locating it on the launch run's
        first sample puts it two channel widths outside a channel it has not
        reached. Measured before this was gated: 36 of 64 marbles reported lost,
        against the 8% the full course loses over the whole route.
        """
        previous = self._where.get(marble_id)
        candidates = [name for name in LAB_RUNS if name in touched]
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
        self.progress[marble_id] = max(
            self.progress[marble_id], self.offsets[name] + self.runs[name].sim_arc[index]
        )

    def _containment(self, marble_id: int, position: Sequence[float]) -> None:
        place = self._where.get(marble_id)
        if place is None or marble_id in self.lost:
            return
        name, index = place
        run = self.runs[name]
        lateral, up, _forward = run.frames[index]
        centre = run.sim_path[index]
        offset = [position[axis] - centre[axis] for axis in range(3)]
        across = sum(offset[axis] * lateral[axis] for axis in range(3))
        height = sum(offset[axis] * up[axis] for axis in range(3))
        half = 0.5 * run.clear_width * run.widths[index]
        if abs(across) > half - MARBLE_RADIUS:
            self.wall_ticks[marble_id] += 1
        if abs(across) > half + LATERAL_SLACK or height > run.containment + VERTICAL_SLACK:
            self.lost[marble_id] = (name, index)

    # Under this speed for this many ticks and a marble is not racing. One
    # second at 240 Hz, and 1.5 wu/s is a thirtieth of the speed the launch
    # delivers - slow enough that a marble merely being nudged along by the
    # field does not count.
    STOPPED_SPEED = 1.5
    STOPPED_FOR = 240

    def _stall(self, marble_id: int, velocity: Sequence[float]) -> None:
        if marble_id in self.lost or marble_id in self.stuck:
            return
        if math.hypot(*velocity) >= self.STOPPED_SPEED:
            self._slow[marble_id] = 0
            return
        self._slow[marble_id] = self._slow.get(marble_id, 0) + self.LOCATE_EVERY
        if self._slow[marble_id] >= self.STOPPED_FOR:
            place = self._where.get(marble_id)
            if place is not None:
                self.stuck[marble_id] = place

    def step(self) -> None:
        sim = self.sim
        sim.step()
        contacts = sim.world.contacts()
        touched: dict[int, set[str]] = {}
        for contact in contacts:
            a = sim.world.marble_of(contact.body_a)
            b = sim.world.marble_of(contact.body_b)
            if a is not None and b is not None:
                self.collisions[a] = self.collisions.get(a, 0) + 1
                self.collisions[b] = self.collisions.get(b, 0) + 1
                continue
            for body, other in ((contact.body_a, contact.body_b), (contact.body_b, contact.body_a)):
                marble_id = sim.world.marble_of(body)
                if marble_id is not None and sim.world.marble_of(other) is None:
                    touched.setdefault(marble_id, set()).add(sim.world.owner_of(other))
        if sim.ticks % self.LOCATE_EVERY:
            return
        for marble_id in list(sim.world.marbles):
            position = sim.marbles[marble_id].pose[0]
            self._locate(marble_id, position, touched.get(marble_id, set()))
            self._containment(marble_id, position)
            self._stall(marble_id, sim.marbles[marble_id].pose[2])
            place = self._where.get(marble_id)
            if marble_id not in self._left_start and place is not None:
                # Past the launch run's own first eight samples is out of the
                # fan and into the channel proper.
                if place[0] != "launch" or place[1] >= 8:
                    self._left_start[marble_id] = sim.ticks
        self._watch()

    def _watch(self) -> None:
        order = sorted(self.progress, key=lambda mid: -self.progress[mid])
        if not order:
            return
        leader = order[0]
        for name, fraction in LAB_CHECKPOINTS:
            if name in self._done:
                continue
            if self.progress[leader] >= fraction * self.length:
                self._done.add(name)
                self.ranks[name] = {mid: rank for rank, mid in enumerate(order, start=1)}
                self.checkpoint_progress[name] = dict(self.progress)

    def settled(self) -> bool:
        """Every checkpoint taken and every marble accounted for.

        Not "the leader has finished", which is what this was. A trial that
        stops with the leader leaves the back of the field wherever it happens
        to be, so a start that holds four marbles up looks the same as one that
        does not - which is exactly how a wheel that put 17% of the full
        course's field into the stuck column scored 0.55% here.
        """
        if len(self._done) < len(LAB_CHECKPOINTS):
            return False
        mark = THROUGH_MARK * self.length
        return all(
            self.progress[marble] >= mark or marble in self.lost or marble in self.stuck
            for marble in self.slot_of
        )

    def result(self, seconds: float) -> TrialResult:
        by_tick = sorted(self._left_start, key=lambda mid: self._left_start[mid])
        exit_order = {mid: place for place, mid in enumerate(by_tick, start=1)}
        return TrialResult(
            seed=self.sim.seed,
            seconds=seconds,
            slot_of=dict(self.slot_of),
            ranks={k: dict(v) for k, v in self.ranks.items()},
            progress={k: dict(v) for k, v in self.checkpoint_progress.items()},
            exit_order=exit_order,
            collisions=dict(self.collisions),
            wall_ticks=dict(self.wall_ticks),
            lost=dict(self.lost),
            stuck=dict(self.stuck),
            through={
                marble: self.progress[marble] / self.length for marble in self.slot_of
            },
            reached=len(self._done),
        )


def run_trial(
    seed: int,
    machine: Machine | None = None,
    config: CoreConfig | None = None,
    marble_count: int = 8,
    duration: float = 14.0,
) -> TrialResult:
    """One seed of the start lab, run for `duration` seconds of sim time.

    Fourteen seconds is what the whole field needs to clear leg1, not what the
    leader needs - the difference is the point, and `settled` explains it. A
    trial that has not reached its last checkpoint by then reports `reached`
    short, and `summarise` counts those rather than averaging over them.
    """
    config = config or DEFAULT_CONFIG
    machine = machine or start_machine(config)
    trial = StartTrial(machine, config, seed, marble_count)
    max_ticks = int(round(duration * config.physics.physics_hz))
    started = time.perf_counter()
    # `run_race` closes its world in a `finally` for the same reason: a trial
    # leaves a Bullet DIRECT client behind otherwise, and a scan of a thousand
    # trials in one worker exhausts them - measured, as a `BrokenProcessPool`
    # part way through a nine-candidate sweep.
    try:
        while trial.sim.ticks < max_ticks and not trial.settled():
            trial.step()
        return trial.result(time.perf_counter() - started)
    finally:
        trial.sim.close()


def summarise(results: Sequence[TrialResult], slots: int = layout.BAYS) -> dict[str, Any]:
    """Slot rows, and the numbers that decide whether the start is fair.

    The full-race win-rate ratio the brief's target is written against can only
    be measured on full races. What this reports is the early proxy the bias was
    visible in: the *span* of mean rank across the eight slots, in places. A
    fair start's span is zero and a start that fully determines the early order
    has a span of seven; the V1 course's 9% checkpoint spanned 3.61.
    """
    rows = {slot: SlotRow(slot=slot) for slot in range(slots)}
    incomplete = 0
    for result in results:
        if result.reached < len(LAB_CHECKPOINTS):
            incomplete += 1
        for marble_id, slot in result.slot_of.items():
            row = rows[slot]
            row.trials += 1
            for name, _ in LAB_CHECKPOINTS:
                if name in result.ranks and marble_id in result.ranks[name]:
                    row.ranks.setdefault(name, []).append(result.ranks[name][marble_id])
                if name in result.progress and marble_id in result.progress[name]:
                    row.progress.setdefault(name, []).append(result.progress[name][marble_id])
            if marble_id in result.exit_order:
                row.exit_orders.append(result.exit_order[marble_id])
            row.collisions.append(result.collisions.get(marble_id, 0))
            row.wall_ticks.append(result.wall_ticks.get(marble_id, 0))
            if marble_id in result.lost:
                row.lost += 1
            if marble_id in result.stuck:
                row.stuck += 1
            if result.through.get(marble_id, 0.0) < THROUGH_MARK:
                row.trailing += 1

    spans: dict[str, Any] = {}
    for name, _ in LAB_CHECKPOINTS:
        means = [rows[s].mean_rank(name) for s in range(slots)]
        present = [m for m in means if m is not None]
        spans[name] = {
            "means": [None if m is None else round(m, 4) for m in means],
            "span": round(max(present) - min(present), 4) if present else None,
            "best_slot": (
                min(range(slots), key=lambda s: means[s] if means[s] is not None else 99.0)
                if present
                else None
            ),
            "worst_slot": (
                max(range(slots), key=lambda s: means[s] if means[s] is not None else -1.0)
                if present
                else None
            ),
        }

    lost_total = sum(row.lost for row in rows.values())
    stuck_total = sum(row.stuck for row in rows.values())
    trailing_total = sum(row.trailing for row in rows.values())
    trials_total = sum(row.trials for row in rows.values())
    first = LAB_CHECKPOINTS[0][0]
    last = LAB_CHECKPOINTS[-1][0]
    return {
        "trials": len(results),
        "incomplete": incomplete,
        "racers": trials_total,
        "lost": lost_total,
        "lost_pct": round(100.0 * lost_total / trials_total, 3) if trials_total else None,
        "stuck": stuck_total,
        "stuck_pct": round(100.0 * stuck_total / trials_total, 3) if trials_total else None,
        "trailing": trailing_total,
        "trailing_pct": (
            round(100.0 * trailing_total / trials_total, 3) if trials_total else None
        ),
        "checkpoints": [name for name, _ in LAB_CHECKPOINTS],
        "rank_span": spans,
        "early_rank_span": spans[first]["span"],
        "exit_rank_span": spans[last]["span"],
        "slots": [rows[s].to_json() for s in range(slots)],
    }

"""One Race #2 race: the core's loop, plus where each racer is on the course.

This is `sloped.race` re-derived against `race2.course.Course` instead of
against one hard-coded topology, and the three places it differs are the three
places Race #1's version could not generalise.

**Progress is stage-relative.** A marble's progress is its stage's canonical
offset plus its fraction of that stage, so two marbles in different branches of
the same split are compared on how far through the split they are. Race #1
accumulates real arc length, which works because it has exactly one fork whose
two lengths differ by a known 5.7%; with three splits there are eight route
lengths and no single ordering of them is "the" course. The length difference
does not disappear - it is measured as a *route advantage* in seconds through
the stage, which is the form the question is actually asked in.

**A route is a list of choices.** `RacerResult.branches` records which run of
each parallel stage a marble took, in order. Race #1's single `route` label is
the degenerate case of that.

**A marble is located by contact first and by neighbourhood second**, exactly
as Race #1 does it, and for the same measured reason: the branches of a split
overlap at the nose, so nearest-centreline attributes half the field to the
wrong side. What is new is that "which runs may this marble be on" is answered
from the *stage graph* - the runs of its current stage and the next one - which
is both cheaper and more honest than Race #1's "every run the machine carries".

## What is deliberately not here

No marble is pushed, damped, corrected, re-ordered or helped out of a jam. The
only writes into the world are `record.apply_actuators` in the parent's `step`,
and every actuator's pose is a pure function of the tick.
`tests/test_race2_physics.py` asserts both halves of that.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

from marble3d.config import CoreConfig, DEFAULT_CONFIG, REPLAY_FPS
from marble3d.replay import Event, Replay, STATE_ESCAPED, STATE_FINISHED, MarbleInfo
from marble3d.simulation import MarbleSimulation, environment_metadata
from marble3d.units import GRAVITY, MARBLE_RADIUS, describe as describe_units

from sloped import scale

from race2.course import Course

__all__ = ["RacerResult", "RaceOutcome", "Race2", "run_race", "CHECKPOINTS"]

# Where a rank is taken, as a fraction of the course. The first two are early
# on purpose: start-slot bias is a claim about what the course does *before* it
# has had time to shuffle anything, and a correlation measured only at the
# finish cannot separate "the start is fair" from "the middle is violent".
CHECKPOINTS = (
    ("release", 0.06),
    ("first_event", 0.18),
    ("quarter", 0.25),
    ("half", 0.50),
    ("three_quarter", 0.75),
)

# How far ahead a marble has to be before the ordering will put it ahead, in
# canonical course units - which are layout units, because a stage's span is
# its layout arc length.
#
# **Without this the rank order is noise.** Eight marbles crossing a pan are
# level to within a millimetre for seconds at a time, and an ordering that
# compares raw progress at 60 Hz swaps them on every sample: seed 1 of the
# switchyard reported 32 lead changes, of which the first fourteen were two
# marbles trading places every two frames inside the first second. A viewer
# sees one bunched pack there, not fourteen changes of leader, and a metric
# that disagrees with the viewer about that is measuring the sample rate.
#
# 0.8 layout units is 1.4 marble diameters: far enough to be a visible gap,
# near enough that a genuine pass is recorded on the frame it happens.
# The sort is *sticky* rather than thresholded - the previous order is kept
# unless the margin is cleared - so the order never oscillates and a pass, once
# recorded, is not unrecorded by a jitter of half a millimetre.
LEAD_MARGIN = 0.8

LATERAL_SLACK = 0.5 * 2.0 * MARBLE_RADIUS
VERTICAL_SLACK = 2.0 * MARBLE_RADIUS
FLOOR_SLACK = 2.5 * 2.0 * MARBLE_RADIUS


@dataclass
class RacerResult:
    marble_id: int
    start_slot: int
    branches: list[tuple[str, str]] = field(default_factory=list)
    finish_order: int | None = None
    finish_time: float | None = None
    state: str = "running"
    progress: float = 0.0
    top_speed: float = 0.0
    ranks: dict[str, int] = field(default_factory=dict)
    stage_times: dict[str, float] = field(default_factory=dict)
    lost_at: tuple[str, int] | None = None
    lost_time: float | None = None
    lost_how: str | None = None
    last_touch: tuple[str, int] | None = None

    def route(self) -> str:
        """The branch choices as one label, for reporting and grouping."""
        return "/".join(branch for _split, branch in self.branches) or "-"

    def to_json(self) -> dict[str, Any]:
        return {
            "marble": self.marble_id,
            "slot": self.start_slot,
            "route": self.route(),
            "branches": [list(pair) for pair in self.branches],
            "order": self.finish_order,
            "time": None if self.finish_time is None else round(self.finish_time, 6),
            "state": self.state,
            "progress": round(self.progress, 4),
            "top_speed": round(self.top_speed, 4),
            "ranks": dict(self.ranks),
            "stage_times": {k: round(v, 4) for k, v in self.stage_times.items()},
            "lost_at": list(self.lost_at) if self.lost_at else None,
            "lost_how": self.lost_how,
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
    worst_penetration: float = 0.0
    branch_counts: dict[str, dict[str, int]] = field(default_factory=dict)
    stage_times: dict[str, dict[str, list[float]]] = field(default_factory=dict)
    leader_series: list[tuple[float, int]] = field(default_factory=list)
    rank_series: list[tuple[float, tuple[int, ...]]] = field(default_factory=list)
    progress_series: list[tuple[float, dict[int, float]]] = field(default_factory=list)
    # The simulation's own event stream - branch commitments, mechanism
    # contacts, line crossings, containment losses. Carried on the outcome so
    # `race2.events` can read it without a replay: a benchmark wants the events
    # and emphatically does not want 900 frames of eight marbles per seed.
    sim_events: list = field(default_factory=list)
    failure: str | None = None

    def winner(self) -> RacerResult | None:
        for racer in self.racers:
            if racer.finish_order == 1:
                return racer
        return None

    def all_finished(self) -> bool:
        return bool(self.racers) and self.finished == len(self.racers)

    def finish_span(self) -> float | None:
        times = sorted(r.finish_time for r in self.racers if r.finish_time is not None)
        if len(times) < 2:
            return None
        return times[-1] - times[0]

    def podium_gap(self) -> float | None:
        """First to second, in seconds - the final-sprint result."""
        times = sorted(r.finish_time for r in self.racers if r.finish_time is not None)
        if len(times) < 2:
            return None
        return times[1] - times[0]

    def to_json(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "seconds": round(self.seconds, 4),
            "wall_seconds": round(self.wall_seconds, 3),
            "finished": self.finished,
            "escaped": self.escaped,
            "stuck": self.stuck,
            "collisions": self.collisions,
            "lead_changes": self.lead_changes,
            "overtakes": self.overtakes,
            "top_speed": round(self.top_speed, 4),
            "worst_penetration": round(self.worst_penetration, 6),
            "branch_counts": {k: dict(v) for k, v in self.branch_counts.items()},
            "finish_span": None if self.finish_span() is None else round(self.finish_span(), 4),
            "podium_gap": None if self.podium_gap() is None else round(self.podium_gap(), 4),
            "failure": self.failure,
            "racers": [racer.to_json() for racer in self.racers],
        }


class Race2(MarbleSimulation):
    """`MarbleSimulation` with a described course under it."""

    WINDOW = 16          # samples either side of the last known position
    LOCATE_EVERY = 4     # ticks; a rank does not need 240 Hz

    def __init__(
        self,
        course: Course,
        config: CoreConfig | None = None,
        seed: int = 0,
        marble_count: int = 8,
    ) -> None:
        super().__init__(course.machine, config, seed, marble_count)
        self.course = course
        self.runs = course.runs
        self.finish_line = course.finish_line

        self.results = {
            marble_id: RacerResult(marble_id=marble_id, start_slot=marble.start_index)
            for marble_id, marble in self.marbles.items()
        }
        self._contacts: list = []
        self._where: dict[int, tuple[str, int]] = {}
        self._entered: dict[int, set[str]] = {}
        self._crossed: set[int] = set()
        # **Not `_finish_count`.** `Race2` extends `MarbleSimulation`, which
        # keeps an attribute of that name for the marbles it retires through
        # the machine's own exit socket, and the two counters were the same
        # integer. It never showed, because until V33.1 no Race #2 racer
        # reached that socket alive - the run-out deck was laid across the
        # track and they fell out of the machine instead - so the base class
        # never incremented it. With the deck the right way round a racer runs
        # out through the gate, and the placings from fourth onward were
        # renumbered by one. A line crossing is a different event from leaving
        # the machine and it gets its own counter.
        self._line_count = 0
        self._leader: int | None = None
        self.lead_changes = 0
        self.overtakes = 0
        self.leader_series: list[tuple[float, int]] = []
        self.rank_series: list[tuple[float, tuple[int, ...]]] = []
        self.progress_series: list[tuple[float, dict[int, float]]] = []
        self._rank_order: list[int] = []
        self._checkpoints_done: set[str] = set()
        self._stage_index = {stage.name: i for i, stage in enumerate(course.stages)}
        self._last_hit: dict[tuple[int, str], float] = {}
        self._apex_done: set[str] = set()
        # The apex sample of every run whose stage role is a compression: the
        # middle of a banked pan, which is where a high line and a low line are
        # furthest apart and therefore where the choice between them is made.
        self._apexes = {
            name: len(course.runs[name].path) // 2
            for stage in course.stages
            if "compress" in stage.role
            for name in stage.runs
        }

    # --- where a marble is ------------------------------------------------

    def _stage_name(self, marble_id: int) -> str | None:
        place = self._where.get(marble_id)
        if place is None:
            return None
        return self.course.stage_of[place[0]].name

    def _runs_open_to(self, marble_id: int) -> tuple[str, ...]:
        """The runs a marble may be located on: its stage, and its neighbours.

        Race #1 searches every run in the machine until a route is committed,
        which is affordable there because there are eight runs and expensive
        here because a folded course has fifteen. The stage graph gives the
        answer directly: a marble on stage *i* is on stage *i-1*, *i* or *i+1*,
        and no course in this package lets a marble skip a stage - the seam
        check in `race2.build` is what says so.
        """
        name = self._stage_name(marble_id)
        if name is None:
            return self.course.stages[0].runs + (
                self.course.stages[1].runs if len(self.course.stages) > 1 else ()
            )
        index = self._stage_index[name]
        low = max(0, index - 1)
        high = min(len(self.course.stages), index + 2)
        out: list[str] = []
        for stage in self.course.stages[low:high]:
            out.extend(stage.runs)
        return tuple(out)

    def _locate(self, marble_id: int, position: Sequence[float], touched: set[str]) -> None:
        candidates = [name for name in self._runs_open_to(marble_id) if name in touched]
        previous = self._where.get(marble_id)
        if previous and previous[0] not in candidates:
            candidates.append(previous[0])
        if not candidates:
            # Nothing touched and nowhere known: the first frames, in the air
            # off the start shelf. Fall back to the opening stage so the search
            # window has somewhere to start from.
            candidates = list(self.course.stages[0].runs)

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

        run = self.runs[name]
        fraction = run.sim_arc[index] / run.sim_arc[-1] if run.sim_arc[-1] else 0.0
        result = self.results[marble_id]
        # Monotonic: a marble that runs back up an apron has not un-raced the
        # course it already covered, and a rank that went backwards there would
        # report the recovery as an overtake by everyone else.
        result.progress = max(result.progress, self.course.progress_at(name, fraction))

        entered = self._entered.setdefault(marble_id, set())
        if name not in entered:
            entered.add(name)
            result.stage_times[name] = self.elapsed
            stage = self.course.stage_of[name]
            if stage.parallel:
                result.branches.append((stage.name, name))
                self.events.append(
                    Event(self.elapsed, "branch",
                          {"id": marble_id, "split": stage.name, "branch": name})
                )

    def _on_apron(self, name: str, position: Sequence[float]) -> bool:
        """Is the marble standing on a station that legitimately holds it?

        The same excuse `sloped.race._on_apron` makes for the merge, made
        generic: a course declares which module ids hold marbles off-centreline
        and which runs that excuses, and a module that declares itself answers
        `holds(point)`.
        """
        for module_id, runs in self.course.aprons.items():
            if name not in runs:
                continue
            module = self.machine.modules.get(module_id)
            if module is not None and getattr(module, "holds", None) and module.holds(position):
                return True
        return False

    def _containment(self, marble_id: int, position: Sequence[float]) -> None:
        if marble_id in self._crossed:
            return
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
        ceiling = run.containment_at(index)
        floor = run.floor_offset - FLOOR_SLACK
        excused = self._on_apron(name, position)
        how = (
            "outside"
            if abs(across) > half + LATERAL_SLACK and not excused
            else "over"
            if height > ceiling + VERTICAL_SLACK and not excused
            else "through"
            if height < floor
            else None
        )
        if how is not None and result.lost_at is None:
            result.lost_at = (name, index)
            result.lost_time = self.elapsed
            result.lost_how = how
            self.events.append(
                Event(self.elapsed, "left_channel",
                      {"id": marble_id, "run": name, "sample": index,
                       "across": round(across, 4), "height": round(height, 4),
                       "how": how})
            )

    # --- the loop ---------------------------------------------------------

    def _read_contacts(self) -> None:
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
            self._note_mechanism(marble_id, hits)
            if touched.get(marble_id):
                place = self._where.get(marble_id)
                if place is not None:
                    result.last_touch = place
            self._containment(marble_id, marble.pose[0])
            result.top_speed = marble.top_speed
            if marble_id not in self._crossed and self._past_line(marble.pose[0]):
                self._crossed.add(marble_id)
                self._line_count += 1
                result.finish_order = self._line_count
                result.finish_time = self.elapsed
                result.progress = self.course.length
                self.events.append(
                    Event(self.elapsed, "finish_line",
                          {"id": marble_id, "order": result.finish_order,
                           "slot": result.start_slot, "route": result.route()})
                )

        self._watch_order()
        self._watch_lines()

    def lateral_of(self, marble_id: int) -> float | None:
        """Where a marble is across its channel, as a fraction of half width.

        -1 is one wall and +1 the other, in the run's own lateral frame. This
        is the quantity a "high line against low line" claim is made of, and it
        is read from the same `frames` the collider was swept along, so it
        means the same thing the geometry does.
        """
        place = self._where.get(marble_id)
        if place is None:
            return None
        name, index = place
        run = self.runs[name]
        lateral, _up, _forward = run.frames[index]
        centre = run.sim_path[index]
        position = self.marbles[marble_id].pose[0]
        offset = [position[axis] - centre[axis] for axis in range(3)]
        across = sum(offset[axis] * lateral[axis] for axis in range(3))
        half = 0.5 * run.clear_width * run.widths[index]
        return across / half if half > 1e-9 else None

    def _watch_lines(self) -> None:
        """One record per pan: where the leading group was when it mattered.

        The switchyard has no fork, and its route choice is the *line* a racer
        takes through a banked hairpin - high and long against low and short.
        That is a real decision with a real cost, and it would be invisible to
        an event definition that only knew about branch colliders. So it is
        measured directly: the first time the leader reaches a pan's apex, the
        leading four's lateral positions are recorded, and a group that
        straddles the channel has taken two different lines.
        """
        if not self._rank_order:
            return
        leader = self._rank_order[0]
        place = self._where.get(leader)
        if place is None:
            return
        name, index = place
        apex = self._apexes.get(name)
        if apex is None or index < apex or name in self._apex_done:
            return
        self._apex_done.add(name)
        lines: dict[int, float] = {}
        for marble_id in self._rank_order[:4]:
            value = self.lateral_of(marble_id)
            if value is not None:
                lines[marble_id] = round(value, 4)
        if len(lines) < 2:
            return
        spread = max(lines.values()) - min(lines.values())
        self.events.append(
            Event(
                self.elapsed,
                "line_choice",
                {
                    "pan": name,
                    "spread": round(spread, 4),
                    # A straddle is the leaders being on opposite sides of the
                    # centreline by more than a marble radius' worth of half
                    # width, not merely spread out on the same side.
                    "straddles": bool(
                        max(lines.values()) > 0.15 and min(lines.values()) < -0.15
                    ),
                    "lines": lines,
                },
            )
        )

    # How long after touching a mechanism the same marble may register it
    # again. A wheel is touched on a dozen consecutive frames as a blade sweeps
    # past, and twelve `mechanism_hit` events for one collision would be a
    # measure of the locator's sample rate.
    HIT_COOLDOWN = 0.60

    def _note_mechanism(self, marble_id: int, hits: set[str]) -> None:
        """Record a leading racer meeting a powered part.

        Only the leading three, and that is the definition rather than an
        optimisation: `race2.events` counts a mechanism hit because it is the
        moment a viewer expects the order to change, and the eighth racer
        hitting a wheel does not put the answer to "who is winning" at risk.
        """
        try:
            rank = self._rank_order.index(marble_id) + 1
        except ValueError:
            return
        if rank > 3:
            return
        for module in hits:
            if module not in self.course.stations:
                continue
            key = (marble_id, module)
            if self.elapsed - self._last_hit.get(key, -99.0) < self.HIT_COOLDOWN:
                continue
            self._last_hit[key] = self.elapsed
            self.events.append(
                Event(self.elapsed, "mechanism_hit",
                      {"id": marble_id, "module": module, "rank": rank})
            )

    def _past_line(self, position: Sequence[float]) -> bool:
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

    def _sticky_order(self) -> list[int]:
        """The ordering, with `LEAD_MARGIN` of hysteresis.

        A finisher is placed by its finishing order and never moves again. For
        the rest, the previous ordering is kept and a marble is bubbled past
        its neighbour only when it is ahead by the margin - an insertion sort
        over the previous answer rather than a fresh sort of the progresses.
        """
        finished = sorted(
            (r for r in self.results.values() if r.finish_order),
            key=lambda r: r.finish_order,
        )
        running = [r for r in self.results.values() if not r.finish_order]
        if not self._rank_order:
            running.sort(key=lambda r: -r.progress)
            return [r.marble_id for r in finished] + [r.marble_id for r in running]
        place = {marble: index for index, marble in enumerate(self._rank_order)}
        running.sort(key=lambda r: place.get(r.marble_id, 99))
        ids = [r.marble_id for r in running]
        progress = {r.marble_id: r.progress for r in running}
        changed = True
        while changed:
            changed = False
            for index in range(len(ids) - 1):
                ahead, behind = ids[index], ids[index + 1]
                if progress[behind] - progress[ahead] >= LEAD_MARGIN:
                    ids[index], ids[index + 1] = behind, ahead
                    changed = True
        return [r.marble_id for r in finished] + ids

    def _watch_order(self) -> None:
        order = self._sticky_order()
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
        self.rank_series.append((self.elapsed, tuple(order)))
        self.progress_series.append(
            (self.elapsed, {r.marble_id: r.progress for r in self.results.values()})
        )

        if not order:
            return
        leader = self.results[order[0]]
        for name, fraction in CHECKPOINTS:
            if name in self._checkpoints_done:
                continue
            if leader.progress >= fraction * self.course.length:
                self._checkpoints_done.add(name)
                for rank, marble in enumerate(order, start=1):
                    self.results[marble].ranks[name] = rank


def run_race(
    course: Course,
    seed: int = 0,
    config: CoreConfig | None = None,
    marble_count: int = 8,
    duration: float | None = None,
    with_replay: bool = False,
) -> tuple[RaceOutcome, Replay | None]:
    """One seed, run to the finish or to the limit."""
    config = config or DEFAULT_CONFIG
    race = Race2(course, config, seed, marble_count)
    limit = config.duration_limit if duration is None else duration
    max_ticks = int(round(limit * config.physics.physics_hz))
    started = time.perf_counter()
    failure: str | None = None

    try:
        if with_replay:
            race.frames.append(race.sample())
        while race.ticks < max_ticks and not race.finished:
            race.step()
            if with_replay and race.ticks % race.stride == 0:
                race.frames.append(race.sample())
        if with_replay and race.ticks % race.stride:
            race.frames.append(race.sample())
    except Exception as error:  # a physics failure is a result, not a crash
        failure = f"{type(error).__name__}: {error}"

    outcome = RaceOutcome(
        seed=seed,
        seconds=race.elapsed,
        wall_seconds=time.perf_counter() - started,
        racers=[race.results[key] for key in sorted(race.results)],
        collisions=race.stats.collisions,
        lead_changes=race.lead_changes,
        overtakes=race.overtakes,
        top_speed=race.stats.top_speed,
        worst_penetration=race.stats.worst_penetration,
        leader_series=list(race.leader_series),
        rank_series=list(race.rank_series),
        progress_series=list(race.progress_series),
        sim_events=list(race.events),
        failure=failure,
    )
    # A finisher is one that crossed *this* course's line, not one the core
    # retired at the machine's last exit plane: a folded course's last module
    # is not always where the race ends, and Race #1 makes the same choice for
    # the same reason.
    for marble_id, marble in race.marbles.items():
        result = race.results[marble_id]
        result.state = (
            STATE_FINISHED if result.finish_order is not None
            else STATE_ESCAPED if marble.state == STATE_ESCAPED
            else "stuck"
        )
    outcome.finished = sum(1 for r in outcome.racers if r.state == STATE_FINISHED)
    outcome.escaped = sum(1 for r in outcome.racers if r.state == STATE_ESCAPED)
    outcome.stuck = sum(1 for r in outcome.racers if r.state == "stuck")
    if failure is None and outcome.finished < len(outcome.racers):
        outcome.failure = (
            f"{outcome.escaped} escaped, {outcome.stuck} still in the machine "
            f"after {outcome.seconds:.1f} s"
        )

    for stage in course.splits():
        counts: dict[str, int] = {name: 0 for name in stage.runs}
        for racer in outcome.racers:
            for split, branch in racer.branches:
                if split == stage.name:
                    counts[branch] = counts.get(branch, 0) + 1
        outcome.branch_counts[stage.name] = counts

    replay: Replay | None = None
    if with_replay:
        replay = _replay_of(race, config, outcome)
    race.close()
    return outcome, replay


def _replay_of(race: Race2, config: CoreConfig, outcome: RaceOutcome) -> Replay:
    """The authoritative record, in simulation units, with the render scale in it.

    The same shape `sloped.race._replay_of` writes, so every tool that already
    reads a replay - the Godot renderer, the determinism probe, the frame
    sheets - reads this one without a branch. What differs is `summary.race`,
    which carries Race #2's branch lists and stage times instead of Race #1's
    single route label, and `summary.course`, which carries the stage and phase
    description the camera and event passes are built against.
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
    replay.summary["race"] = outcome.to_json()
    replay.summary["course"] = race.course.to_json()
    return replay

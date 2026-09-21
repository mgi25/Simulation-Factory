"""What the Test #5 pendulum actually does, measured rather than asserted.

The P0 question is one question - *does this mechanism create readable,
physically caused changes of race order without jams, escapes or an
unacceptable bias* - and it decomposes into four measurements this module
makes, in increasing order of how hard they are to fake.

## 1. Reliability, from the production instrument

Finish count, escapes, racers left in the machine, worst solver penetration and
the event timeline all come from `race2.race.run_race` and `race2.events.extract`
unchanged, and the aggregates from `race2.bench`'s own `spearman`. That is
deliberate: `race2.bench`'s docstring warns that a benchmark computing slot
correlation one way for the concepts and another way for the chosen course
would be "a comparison of two instruments", and a P0 lab that reimplemented
finish-rate arithmetic would be exactly that.

## 2. Contact, computed from the deterministic pose rather than guessed

`Race2._note_mechanism` records a true Bullet contact with a named station, but
only for the leading three racers and only once per 0.6 s - by design, because
it feeds an event *density*. A P0 lab wants every racer.

It can have them without touching the simulation, and the reason it can is the
actuator contract itself: the arm's pose is a pure function of the tick, so the
exact pose the solver used at tick *n* can be recomputed afterwards from the
same `pose_at`. The replay records every marble's position at 60 Hz and the
physics runs at 240, so marble positions are interpolated across each frame
interval while **arm poses are evaluated exactly at every physics tick**. The
distance from a marble centre to the swept box then gives, per racer:

    min_gap        closest approach minus a marble radius; negative is contact
                   with the solver's allowed penetration
    touched        min_gap within `TOUCH_SLACK`
    touch_time     how long it spent that close
    first_touch    when

This is a *proximity* measure and is reported as one. `TOUCH_SLACK` is 0.15 of
a marble radius, which is above the worst error the interpolation can introduce
(a racer at 35 simulation units a second moves 0.145 units per substep, so a
grazing pass is located to about 0.07) and far under a radius, so a racer that
merely went past on the far side of the channel is never counted. Nothing here
invents an event: a marble that the arm never came near has `touched` False and
a `min_gap` of half a channel.

## 3. Rank change through the pendulum, at three scopes

A rank change has to be attributed to something, and the honest difficulty is
that a struck racer loses its place *downstream* of the strike rather than at
it. So the same before/after comparison is made over three windows, each
labelled, rather than one window chosen to flatter the mechanism:

    region      2.0 units before the arm to 6.0 after it. The immediate
                deflection; about a quarter of a second of travel.
    corridor    2.0 units before the arm to the end of `corr1`. The headline
                number, because `corr1` contains the arm and nothing else, so
                a reordering inside it has one candidate cause.
    finish      2.0 units before the arm to the finishing order. Everything
                downstream, including the recovery hairpin - an upper bound on
                the arm's influence, not a measure of it.

Each window is read **two** ways, because the obvious reading has a confound.

*Crossing order* - the headline. Every racer's own crossing time of the
window's two progress marks, interpolated between the 60 Hz samples that
bracket it, and the two resulting orderings compared. This is a sector time in
the motorsport sense: who went in first against who came out first. It is
anchored to the course rather than to the clock, so it is immune to the
confound below.

*Sticky order* - the secondary reading. The ordering
(`race2.race.LEAD_MARGIN`, the one a viewer would agree with) at the last
sample before the first racer reaches the window against the ordering once the
last racer has left it. Honest, but it flatters the mechanism: an arm that
holds the sixth racer up for two seconds means the leaders are far past the
window by the time it clears, so part of what the "after" ordering shows is
downstream racing rather than the arm. Both are reported; where they disagree,
the crossing order is the one the P0 verdict uses.

### One field is not connected, and reads zero because of it

`RunStats.max_energy_rise` would be the check that a machine does not inject
energy, and it is **structurally zero for every Race #2 race**, this lab's
included. It is accumulated from an `energy_series` that only
`marble3d.simulation.run_simulation` builds, and `race2.race.run_race` is a
different driver that never calls it; `race2.race._replay_of` copies
`race.stats.to_json()`, so the field travels in the replay summary but the
number was never taken. This lab therefore does not report it - a zero from an
unconnected instrument reads exactly like a pass.

The invariant itself is not unchecked. `tests/test_race2_physics.py` steps a
SWITCHYARD race and asserts the energy of the field never rises once the start
gate has finished moving, and
`tests/test_race2_test5_lab.py::test_the_arm_hands_no_racer_free_speed` makes
the same check of this course - which matters here, because a kinematic arm is
infinitely heavy to a marble and could shove without limit.

What is connected and carried per seed is `worst_actuator_overlap` (how deep
the arm got into a marble before the solver pushed it out) and
`max_travel_per_tick` against `travel_budget` (whether anything moved far
enough in one tick to tunnel).

## 4. The control

Rates 1 to 3 mean nothing alone: a 3-unit corridor reorders a six-racer field
by itself. Every configuration is therefore run against
`race2.test5_course.pendulum_p0_bare` - the identical course with the module
left out - over the identical seeds, and the arm's contribution is the
*difference*. Removing a module renumbers Bullet's bodies, so the two runs of
one seed are different simulations and no per-seed claim is made across the
pair; the comparison is of distributions.
"""

from __future__ import annotations

import json
import math
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from marble3d.geometry import Transform
from marble3d.replay import STATE_FINISHED
from marble3d.units import MARBLE_RADIUS

from sloped.scale import SIM_TO_LAYOUT

from race2.bench import spearman

__all__ = [
    "REGION_IN",
    "REGION_OUT",
    "TOUCH_SLACK",
    "Contact",
    "RankChange",
    "P0Seed",
    "P0Benchmark",
    "measure_seed",
    "run_p0_seeds",
    "sweep",
]

# The measurement window around the arm, in layout units, which are also the
# course's canonical progress units because a stage's span is its arc length.
#
# 2.0 before is three and a half marble diameters: far enough back that the
# field has not begun to react, near enough that nothing else happened there.
# 6.0 after is a third of a second at corridor speed - long enough for a shove
# to become a gap of the 0.8 units `LEAD_MARGIN` asks for, and short enough to
# stay inside `corr1` for every station this lab places.
REGION_IN = 2.0
REGION_OUT = 6.0

# How close a marble centre has to come to the swept box, beyond a radius,
# before the pass counts as a touch. See the module docstring for why 0.15 of a
# radius and not less.
TOUCH_SLACK = 0.15 * MARBLE_RADIUS

DEFAULT_DURATION = 20.0


# --- contact, from the recorded positions and the exact arm pose ----------


@dataclass
class Contact:
    """One racer's closest approach to the arm over a whole race."""

    marble: int
    slot: int
    touched: bool
    min_gap: float
    first_touch: float | None
    touch_seconds: float
    touch_windows: int

    def to_json(self) -> dict[str, Any]:
        return {
            "marble": self.marble,
            "slot": self.slot,
            "touched": self.touched,
            "min_gap": round(self.min_gap, 5),
            "first_touch": None if self.first_touch is None else round(self.first_touch, 4),
            "touch_seconds": round(self.touch_seconds, 4),
            "touch_windows": self.touch_windows,
        }


def _box_gap(inverse: Transform, half_extents: Sequence[float], point: Sequence[float]) -> float:
    """Distance from a point to a box, in simulation units, 0 inside it."""
    local = inverse.apply(point)
    total = 0.0
    for axis in range(3):
        over = abs(local[axis]) - half_extents[axis]
        if over > 0.0:
            total += over * over
    return math.sqrt(total)


def arm_contacts(course, outcome, replay) -> list[Contact]:
    """Every racer's closest approach to the pendulum, from the replay.

    Returns an empty list on the bare course, which has no arm to approach.
    """
    from race2.test5_course import PENDULUM_ID

    module = course.machine.modules.get(PENDULUM_ID)
    if module is None or replay is None or not replay.frames:
        return []
    arm = module.local_actuators()[0]
    half = arm.half_extents
    placement = module.transform
    dt = 1.0 / float(replay.physics_hz)
    # Only evaluate the box where the box can possibly be reached. The furthest
    # any corner gets from the axle is `sqrt(L^2 + hy^2 + hz^2)`, so a marble
    # `d` from the axle is at least `d - that` from the box - a true lower
    # bound, which is both the skip test and the gap recorded for a racer that
    # never came near. Every racer therefore gets a finite closest approach and
    # the gap distribution is not silently restricted to the ones that did.
    pivot = arm.pivot
    span = math.sqrt(arm.length ** 2 + half[1] ** 2 + half[2] ** 2)
    horizon = span + MARBLE_RADIUS + TOUCH_SLACK + 0.5 * MARBLE_RADIUS
    slot_of = {racer.marble_id: racer.start_slot for racer in outcome.racers}

    best: dict[int, float] = {}
    first: dict[int, float] = {}
    seconds: dict[int, float] = {}
    windows: dict[int, int] = {}
    open_window: dict[int, bool] = {}

    frames = replay.frames
    for index in range(len(frames) - 1):
        here, ahead = frames[index], frames[index + 1]
        base_tick = int(round(here.time / dt))
        steps = max(1, int(round((ahead.time - here.time) / dt)))
        nxt = {sample.marble_id: sample.position for sample in ahead.marbles}
        for step in range(steps):
            tick = base_tick + step
            blend = step / steps
            pose = placement.compose(arm.pose_at(tick, dt))
            inverse = pose.inverse()
            when = tick * dt
            for sample in here.marbles:
                marble = sample.marble_id
                target = nxt.get(marble, sample.position)
                point = tuple(
                    sample.position[axis] * (1.0 - blend) + target[axis] * blend
                    for axis in range(3)
                )
                reach = math.dist(point, pivot)
                if reach > horizon:
                    bound = reach - span - MARBLE_RADIUS
                    if marble not in best or bound < best[marble]:
                        best[marble] = bound
                    open_window[marble] = False
                    continue
                gap = _box_gap(inverse, half, point) - MARBLE_RADIUS
                if marble not in best or gap < best[marble]:
                    best[marble] = gap
                if gap <= TOUCH_SLACK:
                    if marble not in first:
                        first[marble] = when
                    seconds[marble] = seconds.get(marble, 0.0) + dt
                    if not open_window.get(marble):
                        windows[marble] = windows.get(marble, 0) + 1
                    open_window[marble] = True
                else:
                    open_window[marble] = False

    out: list[Contact] = []
    for racer in sorted(outcome.racers, key=lambda r: r.marble_id):
        marble = racer.marble_id
        gap = best.get(marble, float("inf"))
        out.append(
            Contact(
                marble=marble,
                slot=slot_of.get(marble, -1),
                touched=gap <= TOUCH_SLACK,
                min_gap=gap,
                first_touch=first.get(marble),
                touch_seconds=seconds.get(marble, 0.0),
                touch_windows=windows.get(marble, 0),
            )
        )
    return out


# --- rank change over a window of the course ------------------------------


@dataclass
class RankChange:
    """The field's order before and after one stretch of the course."""

    scope: str
    low: float
    high: float
    enter: float | None
    leave: float | None
    # The crossing reading: who entered first against who left first.
    in_order: tuple[int, ...] = ()
    out_order: tuple[int, ...] = ()
    crossed: int = 0
    crossing_reordered: int = 0
    crossing_pairs: int = 0
    crossing_leader_lost: bool = False
    crossing_leader_drop: int = 0
    crossing_best_gain: int = 0
    # The sticky reading: the ordering a viewer would agree with, before and
    # after. See the module docstring for why it is the secondary one.
    before: tuple[int, ...] = ()
    after: tuple[int, ...] = ()
    reordered: int = 0
    pairs_swapped: int = 0
    leader_lost: bool = False
    leader_drop: int = 0
    best_gain: int = 0
    lead_changes: int = 0
    complete: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "window": [round(self.low, 3), round(self.high, 3)],
            "enter": None if self.enter is None else round(self.enter, 3),
            "leave": None if self.leave is None else round(self.leave, 3),
            "in_order": list(self.in_order),
            "out_order": list(self.out_order),
            "crossed": self.crossed,
            "crossing_reordered": self.crossing_reordered,
            "crossing_pairs": self.crossing_pairs,
            "crossing_leader_lost": self.crossing_leader_lost,
            "crossing_leader_drop": self.crossing_leader_drop,
            "crossing_best_gain": self.crossing_best_gain,
            "before": list(self.before),
            "after": list(self.after),
            "reordered": self.reordered,
            "pairs_swapped": self.pairs_swapped,
            "leader_lost": self.leader_lost,
            "leader_drop": self.leader_drop,
            "best_gain": self.best_gain,
            "lead_changes": self.lead_changes,
            "complete": self.complete,
        }


def _crossing_time(outcome, marble: int, mark: float) -> float | None:
    """When a racer's progress first reached `mark`, interpolated.

    The progress series is sampled at 60 Hz - `Race2.LOCATE_EVERY` - and a
    six-racer field crossing one plane inside a single sample is common enough
    that an un-interpolated crossing order is mostly ties. Linear between the
    two samples that bracket the mark, which over a sixtieth of a second of
    corridor is a third of a marble diameter of travel.
    """
    previous: tuple[float, float] | None = None
    for when, table in outcome.progress_series:
        value = table.get(marble)
        if value is None:
            continue
        if value >= mark:
            if previous is not None and value > previous[1]:
                span = value - previous[1]
                blend = (mark - previous[1]) / span
                return previous[0] + blend * (when - previous[0])
            return when
        previous = (when, value)
    return None


def _order_before(outcome, when: float) -> tuple[int, ...]:
    chosen = outcome.rank_series[0][1]
    for at, order in outcome.rank_series:
        if at >= when:
            break
        chosen = order
    return tuple(chosen)


def _order_after(outcome, when: float) -> tuple[int, ...]:
    for at, order in outcome.rank_series:
        if at >= when:
            return tuple(order)
    return tuple(outcome.rank_series[-1][1])


def _kendall(before: Sequence[int], after: Sequence[int]) -> int:
    place = {marble: index for index, marble in enumerate(after)}
    swapped = 0
    for i in range(len(before)):
        for j in range(i + 1, len(before)):
            a, b = before[i], before[j]
            if a in place and b in place and place[a] > place[b]:
                swapped += 1
    return swapped


def _rank_change(outcome, scope: str, low: float, high: float) -> RankChange:
    change = RankChange(scope=scope, low=low, high=high, enter=None, leave=None)
    if not outcome.rank_series or not outcome.progress_series:
        return change
    ids = [racer.marble_id for racer in outcome.racers]

    into = {m: _crossing_time(outcome, m, low) for m in ids}
    entries = [t for t in into.values() if t is not None]
    if not entries:
        return change
    change.enter = min(entries)

    # --- the crossing reading -----------------------------------------
    if scope == "finish":
        out_times = {
            r.marble_id: r.finish_time
            for r in outcome.racers
            if r.finish_time is not None
        }
    else:
        out_times = {
            m: when
            for m, when in ((m, _crossing_time(outcome, m, high)) for m in ids)
            if when is not None
        }
    both = [m for m in ids if into.get(m) is not None and m in out_times]
    change.crossed = len(both)
    if len(both) >= 2:
        change.in_order = tuple(sorted(both, key=lambda m: into[m]))
        change.out_order = tuple(sorted(both, key=lambda m: out_times[m]))
        place_in = {m: i for i, m in enumerate(change.in_order)}
        place_out = {m: i for i, m in enumerate(change.out_order)}
        change.crossing_reordered = sum(1 for m in both if place_in[m] != place_out[m])
        change.crossing_pairs = _kendall(change.in_order, change.out_order)
        leader = change.in_order[0]
        change.crossing_leader_lost = change.out_order[0] != leader
        change.crossing_leader_drop = max(0, place_out[leader] - place_in[leader])
        change.crossing_best_gain = max(place_in[m] - place_out[m] for m in both)

    # --- the sticky reading -------------------------------------------
    if scope == "finish":
        ordered = sorted(
            (r for r in outcome.racers if r.finish_order is not None),
            key=lambda r: r.finish_order,
        )
        change.after = tuple(r.marble_id for r in ordered)
        change.leave = max(
            (r.finish_time for r in outcome.racers if r.finish_time is not None),
            default=None,
        )
        change.complete = len(change.after) == len(ids)
    else:
        if not out_times:
            return change
        change.leave = max(out_times.values())
        change.after = _order_after(outcome, change.leave)
        change.complete = len(out_times) == len(ids)

    change.before = _order_before(outcome, change.enter)
    if not change.after:
        return change

    place_before = {m: i for i, m in enumerate(change.before)}
    place_after = {m: i for i, m in enumerate(change.after)}
    shared = [m for m in change.before if m in place_after]
    change.reordered = sum(
        1 for m in shared if place_before[m] != place_after[m]
    )
    change.pairs_swapped = _kendall(shared, change.after)
    leader = change.before[0]
    change.leader_lost = bool(change.after) and change.after[0] != leader
    if leader in place_after:
        change.leader_drop = max(0, place_after[leader] - place_before[leader])
    change.best_gain = max(
        (place_before[m] - place_after[m] for m in shared), default=0
    )
    if change.leave is not None:
        seen: int | None = None
        for at, order in outcome.rank_series:
            if at < change.enter or at > change.leave:
                continue
            if seen is None:
                seen = order[0]
            elif order[0] != seen:
                change.lead_changes += 1
                seen = order[0]
    return change


# --- one seed -------------------------------------------------------------


@dataclass
class P0Seed:
    """Everything one seed of the lab says, armed or bare."""

    seed: int
    armed: bool
    racers: int
    finished: int
    escaped: int
    stuck: int
    seconds: float
    first_finish: float | None
    last_finish: float | None
    podium_gap: float | None
    winner: int | None
    winner_slot: int | None
    slots: list[int] = field(default_factory=list)
    ranks: list[int] = field(default_factory=list)
    finish_order: list[int] = field(default_factory=list)
    lead_changes: int = 0
    overtakes: int = 0
    late_lead_changes: int = 0
    comeback: int = 0
    events: int = 0
    density: float = 0.0
    longest_gap: float = 0.0
    longest_gap_at: float = 0.0
    dead_zones: int = 0
    worst_penetration: float = 0.0
    # `MarbleSimulation._read_contacts` splits the deepest overlap three ways by
    # what the marble was touching, and **the arm's own penetration is not in
    # `worst_penetration`** - a kinematic body's contacts go to
    # `worst_actuator_overlap`. A P0 report that quoted the track number as
    # evidence about the arm would be quoting the wrong column, so both are
    # carried. They come off `RunStats` through the replay summary, which is
    # why the control is raced with a replay it has no other use for.
    worst_actuator_overlap: float = 0.0
    worst_marble_overlap: float = 0.0
    max_travel_per_tick: float = 0.0
    travel_budget: float = 0.0
    top_speed: float = 0.0
    collisions: int = 0
    stuck_at_pendulum: int = 0
    stuck_where: list[list[Any]] = field(default_factory=list)
    changes: dict[str, RankChange] = field(default_factory=dict)
    contacts: list[Contact] = field(default_factory=list)
    mechanism_hits: int = 0
    failures: list[str] = field(default_factory=list)

    @property
    def jam(self) -> bool:
        return self.stuck > 0

    @property
    def all_finished(self) -> bool:
        return self.finished == self.racers

    def touched(self) -> int:
        return sum(1 for contact in self.contacts if contact.touched)

    def to_json(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "armed": self.armed,
            "racers": self.racers,
            "finished": self.finished,
            "escaped": self.escaped,
            "stuck": self.stuck,
            "jam": self.jam,
            "seconds": round(self.seconds, 3),
            "first_finish": self.first_finish and round(self.first_finish, 3),
            "last_finish": self.last_finish and round(self.last_finish, 3),
            "podium_gap": self.podium_gap and round(self.podium_gap, 4),
            "winner": self.winner,
            "winner_slot": self.winner_slot,
            "slots": list(self.slots),
            "ranks": list(self.ranks),
            "finish_order": list(self.finish_order),
            "lead_changes": self.lead_changes,
            "overtakes": self.overtakes,
            "late_lead_changes": self.late_lead_changes,
            "comeback": self.comeback,
            "events": self.events,
            "density": round(self.density, 3),
            "longest_gap": round(self.longest_gap, 3),
            "longest_gap_at": round(self.longest_gap_at, 3),
            "dead_zones": self.dead_zones,
            "worst_penetration": round(self.worst_penetration, 6),
            "worst_actuator_overlap": round(self.worst_actuator_overlap, 6),
            "worst_marble_overlap": round(self.worst_marble_overlap, 6),
            "max_travel_per_tick": round(self.max_travel_per_tick, 6),
            "travel_budget": round(self.travel_budget, 6),
            "top_speed": round(self.top_speed, 4),
            "collisions": self.collisions,
            "stuck_at_pendulum": self.stuck_at_pendulum,
            "stuck_where": self.stuck_where,
            "touched": self.touched(),
            "mechanism_hits": self.mechanism_hits,
            "changes": {name: change.to_json() for name, change in self.changes.items()},
            "contacts": [contact.to_json() for contact in self.contacts],
            "failures": list(self.failures),
        }


def measure_seed(setting, seed: int, duration: float = DEFAULT_DURATION) -> P0Seed:
    """Race one seed of the lab and read everything off it.

    `setting` is a `PendulumSetting`; `setting.armed` decides whether the arm
    is built, so the no-arm control is the same value with one field flipped
    and shares every other number with the configuration it controls. None is
    accepted and means the default lab, unarmed. Imports are local so this can
    be the body of a process pool worker without the parent's module graph
    having to be picklable.
    """
    from race2 import test5_course as lab
    from race2.events import extract
    from race2.race import run_race

    if setting is None:
        setting = lab.DEFAULT_SETTING.bare()
    armed = setting.armed
    course = lab.pendulum_p0(setting=setting)
    centre = lab.window_progress(course, setting.at)
    if armed:
        exact = lab.pendulum_progress(course)
        if exact is None or abs(exact - centre) > 1e-6:
            raise AssertionError(
                f"the measurement window is centred at {centre} and the arm is at {exact}"
            )

    outcome, replay = run_race(
        course, seed=seed, marble_count=lab.BAYS, duration=duration, with_replay=True
    )
    stats = dict(replay.summary) if replay is not None else {}
    timeline = extract(outcome, course, outcome.sim_events)
    at_gap, gap = timeline.longest_gap()
    last_third = timeline.start + (timeline.end - timeline.start) * 2.0 / 3.0
    late = sum(
        1 for e in timeline.events if e.kind == "leader_change" and e.time >= last_third
    )

    low = max(course.offsets[lab.PENDULUM_RUN], centre - REGION_IN)
    end = lab.corridor_end(course)
    changes = {
        "region": _rank_change(outcome, "region", low, min(end, centre + REGION_OUT)),
        "corridor": _rank_change(outcome, "corridor", low, end),
        "finish": _rank_change(outcome, "finish", low, course.length),
    }

    finishers = [r for r in outcome.racers if r.finish_order is not None]
    winner = outcome.winner()
    comeback = 0
    if winner is not None:
        for checkpoint in ("first_event", "quarter", "half"):
            if checkpoint in winner.ranks:
                comeback = max(0, winner.ranks[checkpoint] - 1)
                break

    stuck_where: list[list[Any]] = []
    stuck_at_pendulum = 0
    for racer in outcome.racers:
        if racer.state == STATE_FINISHED:
            continue
        place = racer.lost_at or racer.last_touch
        stuck_where.append(
            [racer.marble_id, racer.state, list(place) if place else None,
             round(racer.progress, 2), racer.lost_how]
        )
        if abs(racer.progress - centre) <= REGION_IN + REGION_OUT:
            stuck_at_pendulum += 1

    hits = sum(
        1
        for record in outcome.sim_events
        if getattr(record, "kind", "") == "mechanism_hit"
        and (getattr(record, "data", {}) or {}).get("module") == lab.PENDULUM_ID
    )

    return P0Seed(
        seed=seed,
        armed=armed,
        racers=len(outcome.racers),
        finished=outcome.finished,
        escaped=outcome.escaped,
        stuck=outcome.stuck,
        seconds=outcome.seconds,
        first_finish=min((r.finish_time for r in finishers), default=None),
        last_finish=max((r.finish_time for r in finishers), default=None),
        podium_gap=outcome.podium_gap(),
        winner=winner.marble_id if winner else None,
        winner_slot=winner.start_slot if winner else None,
        slots=[r.start_slot for r in finishers],
        ranks=[r.finish_order for r in finishers],
        finish_order=[
            r.marble_id
            for r in sorted(finishers, key=lambda r: r.finish_order)
        ],
        lead_changes=outcome.lead_changes,
        overtakes=outcome.overtakes,
        late_lead_changes=late,
        comeback=comeback,
        events=len(timeline.events),
        density=timeline.density(),
        longest_gap=gap,
        longest_gap_at=at_gap,
        dead_zones=len(timeline.dead_zones()),
        worst_penetration=outcome.worst_penetration,
        worst_actuator_overlap=float(stats.get("worst_actuator_overlap", 0.0)),
        worst_marble_overlap=float(stats.get("worst_marble_overlap", 0.0)),
        max_travel_per_tick=float(stats.get("max_travel_per_tick", 0.0)),
        travel_budget=float(stats.get("travel_budget", 0.0)),
        top_speed=outcome.top_speed,
        collisions=outcome.collisions,
        stuck_at_pendulum=stuck_at_pendulum,
        stuck_where=stuck_where,
        changes=changes,
        contacts=arm_contacts(course, outcome, replay),
        mechanism_hits=hits,
        failures=[outcome.failure] if outcome.failure else [],
    )


def _one(args) -> P0Seed:
    setting, seed, duration = args
    return measure_seed(setting, seed, duration)


# --- many seeds of one configuration --------------------------------------


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return 0.5 * (ordered[middle - 1] + ordered[middle])


def _quantile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = fraction * (len(ordered) - 1)
    low = int(math.floor(position))
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return float(ordered[low] * (1.0 - weight) + ordered[high] * weight)


@dataclass
class P0Benchmark:
    """One configuration over many seeds, and what they say about it."""

    label: str
    setting: dict[str, float] | None
    seeds: list[P0Seed] = field(default_factory=list)
    geometry: dict[str, Any] = field(default_factory=dict)

    @property
    def races(self) -> int:
        return len(self.seeds)

    @property
    def racers(self) -> int:
        return sum(s.racers for s in self.seeds)

    def rate(self, predicate) -> float:
        return sum(1 for s in self.seeds if predicate(s)) / max(self.races, 1)

    def finish_rate(self) -> float:
        return sum(s.finished for s in self.seeds) / max(self.racers, 1)

    def slot_correlation(self) -> float:
        slots: list[float] = []
        ranks: list[float] = []
        for seed in self.seeds:
            slots.extend(seed.slots)
            ranks.extend(seed.ranks)
        return spearman(slots, ranks)

    def winner_by_slot(self) -> dict[int, int]:
        out: dict[int, int] = {}
        for seed in self.seeds:
            if seed.winner_slot is not None:
                out[seed.winner_slot] = out.get(seed.winner_slot, 0) + 1
        return dict(sorted(out.items()))

    def mean(self, attribute: str) -> float:
        values = [getattr(s, attribute) for s in self.seeds]
        values = [v for v in values if v is not None]
        return sum(values) / len(values) if values else 0.0

    def change_stats(self, scope: str) -> dict[str, Any]:
        present = [s.changes[scope] for s in self.seeds if scope in s.changes]
        usable = [c for c in present if c.after]
        if not usable:
            return {"measured": 0}
        reordered = [c.reordered for c in usable]
        crossing = [c for c in present if c.crossed >= 2]
        moved = [c.crossing_reordered for c in crossing]
        out: dict[str, Any] = {
            "measured": len(usable),
            "complete": sum(1 for c in usable if c.complete),
            "sticky_any_change_rate": round(
                sum(1 for c in usable if c.reordered) / len(usable), 4
            ),
            "sticky_leader_lost_rate": round(
                sum(1 for c in usable if c.leader_lost) / len(usable), 4
            ),
            "sticky_mean_reordered": round(sum(reordered) / len(usable), 3),
            "mean_lead_changes": round(
                sum(c.lead_changes for c in usable) / len(usable), 3
            ),
        }
        if crossing:
            out.update(
                {
                    "crossed": len(crossing),
                    "any_change_rate": round(
                        sum(1 for c in crossing if c.crossing_reordered) / len(crossing),
                        4,
                    ),
                    "leader_lost_rate": round(
                        sum(1 for c in crossing if c.crossing_leader_lost)
                        / len(crossing),
                        4,
                    ),
                    "two_or_more_rate": round(
                        sum(1 for c in crossing if c.crossing_reordered >= 2)
                        / len(crossing),
                        4,
                    ),
                    "mean_reordered": round(sum(moved) / len(crossing), 3),
                    "median_reordered": round(_median(moved), 3),
                    "max_reordered": max(moved),
                    "mean_pairs_swapped": round(
                        sum(c.crossing_pairs for c in crossing) / len(crossing), 3
                    ),
                    "mean_leader_drop": round(
                        sum(c.crossing_leader_drop for c in crossing) / len(crossing), 3
                    ),
                    "mean_best_gain": round(
                        sum(c.crossing_best_gain for c in crossing) / len(crossing), 3
                    ),
                }
            )
        return out

    def race_times(self) -> dict[str, float]:
        times = [s.last_finish for s in self.seeds if s.last_finish is not None]
        if not times:
            return {}
        return {
            "n": len(times),
            "min": round(min(times), 3),
            "p10": round(_quantile(times, 0.10), 3),
            "median": round(_median(times), 3),
            "p90": round(_quantile(times, 0.90), 3),
            "max": round(max(times), 3),
            "mean": round(sum(times) / len(times), 3),
        }

    def contact_stats(self) -> dict[str, Any]:
        armed = [s for s in self.seeds if s.armed]
        if not armed:
            return {"measured": 0}
        touched = [s.touched() for s in armed]
        gaps = [
            c.min_gap * SIM_TO_LAYOUT
            for s in armed
            for c in s.contacts
            if math.isfinite(c.min_gap)
        ]
        return {
            "measured": len(armed),
            "races_with_a_touch": sum(1 for t in touched if t),
            "touch_rate": round(sum(1 for t in touched if t) / len(armed), 4),
            "mean_racers_touched": round(sum(touched) / len(armed), 3),
            "median_racers_touched": round(_median(touched), 3),
            "mean_touch_seconds": round(
                sum(c.touch_seconds for s in armed for c in s.contacts)
                / max(sum(touched), 1),
                4,
            ),
            "min_gap_layout_p10": round(_quantile(gaps, 0.10), 4) if gaps else None,
            "min_gap_layout_median": round(_median(gaps), 4) if gaps else None,
            "leading_three_bullet_hits": sum(s.mechanism_hits for s in armed),
        }

    def worst(self, count: int = 5) -> list[dict[str, Any]]:
        """The seeds that went worst, by racers lost then by race time."""
        ranked = sorted(
            self.seeds,
            key=lambda s: (-(s.racers - s.finished), -(s.last_finish or 0.0)),
        )
        return [s.to_json() for s in ranked[:count] if s.finished < s.racers or s.failures]

    def useful(self, count: int = 5) -> list[int]:
        """Seeds worth looking at: complete, reordered, and the lead changed."""
        chosen = [
            s
            for s in self.seeds
            if s.all_finished
            and "corridor" in s.changes
            and s.changes["corridor"].crossing_reordered
            and s.changes["corridor"].crossing_leader_lost
        ]
        chosen.sort(
            key=lambda s: (
                -s.changes["corridor"].crossing_reordered,
                -s.comeback,
                -s.lead_changes,
            )
        )
        return [s.seed for s in chosen[:count]]

    def to_json(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "setting": self.setting,
            "geometry": self.geometry,
            "races": self.races,
            "racers": self.racers,
            "finish_rate": round(self.finish_rate(), 4),
            "all_finished_rate": round(self.rate(lambda s: s.all_finished), 4),
            "jam_rate": round(self.rate(lambda s: s.jam), 4),
            "escape_rate": round(
                sum(s.escaped for s in self.seeds) / max(self.racers, 1), 4
            ),
            "stuck_rate": round(
                sum(s.stuck for s in self.seeds) / max(self.racers, 1), 4
            ),
            "stuck_at_pendulum": sum(s.stuck_at_pendulum for s in self.seeds),
            "slot_correlation": round(self.slot_correlation(), 4),
            "winner_by_slot": self.winner_by_slot(),
            "mean_lead_changes": round(self.mean("lead_changes"), 3),
            "mean_late_lead_changes": round(self.mean("late_lead_changes"), 3),
            "mean_overtakes": round(self.mean("overtakes"), 3),
            "mean_comeback": round(self.mean("comeback"), 3),
            "mean_events": round(self.mean("events"), 3),
            "mean_density": round(self.mean("density"), 3),
            "mean_longest_gap": round(self.mean("longest_gap"), 3),
            "worst_longest_gap": round(
                max((s.longest_gap for s in self.seeds), default=0.0), 3
            ),
            "worst_penetration": round(
                min((s.worst_penetration for s in self.seeds), default=0.0), 6
            ),
            "worst_actuator_overlap": round(
                min((s.worst_actuator_overlap for s in self.seeds), default=0.0), 6
            ),
            "worst_marble_overlap": round(
                min((s.worst_marble_overlap for s in self.seeds), default=0.0), 6
            ),
            "worst_travel_per_tick": round(
                max((s.max_travel_per_tick for s in self.seeds), default=0.0), 6
            ),
            "travel_budget": round(
                max((s.travel_budget for s in self.seeds), default=0.0), 6
            ),
            "race_times": self.race_times(),
            "changes": {scope: self.change_stats(scope) for scope in ("region", "corridor", "finish")},
            "contacts": self.contact_stats(),
            "useful_seeds": self.useful(),
            "worst_seeds": self.worst(),
            "seeds": [s.to_json() for s in self.seeds],
        }

    def summary(self) -> str:
        data = self.to_json()
        corridor = data["changes"]["corridor"]
        contacts = data["contacts"]
        times = data["race_times"] or {"median": 0.0, "max": 0.0}
        lines = [
            f"{self.label}: {self.races} seeds, {self.racers} racers"
            + ("" if (self.setting or {}).get("armed") else "   [BARE CONTROL]"),
            f"  finished          {data['finish_rate'] * 100:6.2f}%   "
            f"all six {data['all_finished_rate'] * 100:6.2f}%",
            f"  jams              {data['jam_rate'] * 100:6.2f}%   "
            f"escaped {data['escape_rate'] * 100:6.2f}%   "
            f"stuck {data['stuck_rate'] * 100:6.2f}%   "
            f"at the arm {data['stuck_at_pendulum']}",
            f"  slot correlation  {data['slot_correlation']:+6.3f}   "
            f"track overlap {data['worst_penetration']:.5f}   "
            f"arm overlap {data['worst_actuator_overlap']:.5f}   "
            f"travel {data['worst_travel_per_tick']:.3f}/{data['travel_budget']:.3f}",
            f"  corridor crossing {corridor.get('any_change_rate', 0) * 100:6.2f}% reorder  "
            f"leader lost {corridor.get('leader_lost_rate', 0) * 100:6.2f}%  "
            f">=2 moved {corridor.get('two_or_more_rate', 0) * 100:6.2f}%  "
            f"mean {corridor.get('mean_reordered', 0):.2f}",
            f"  corridor sticky   {corridor.get('sticky_any_change_rate', 0) * 100:6.2f}% reorder  "
            f"leader lost {corridor.get('sticky_leader_lost_rate', 0) * 100:6.2f}%  "
            f"mean {corridor.get('sticky_mean_reordered', 0):.2f}",
            f"  lead changes      {data['mean_lead_changes']:6.2f}   "
            f"late {data['mean_late_lead_changes']:5.2f}   "
            f"comeback {data['mean_comeback']:.2f}",
            f"  race              median {times.get('median', 0):.2f} s   "
            f"max {times.get('max', 0):.2f} s   "
            f"longest gap {data['mean_longest_gap']:.2f} (worst {data['worst_longest_gap']:.2f})",
        ]
        if contacts.get("measured"):
            lines.append(
                f"  arm contact       {contacts['touch_rate'] * 100:6.2f}% of races   "
                f"mean {contacts['mean_racers_touched']:.2f} racers   "
                f"median closest gap {contacts['min_gap_layout_median']}"
            )
        if data["useful_seeds"]:
            lines.append(f"  useful seeds      {data['useful_seeds']}")
        return "\n".join(lines)


def _warm(setting) -> None:
    """Build the course once in the parent so every collider OBJ is on disk.

    `race2.bench.run_seeds` does the same and says why: `marble3d.mesh` caches
    each collider as an OBJ keyed by its digest and Bullet loads it by path, so
    a pool of workers starting on a course whose meshes have never been written
    all try to write the same files and the losers load one that is not there
    yet.
    """
    from marble3d.config import DEFAULT_CONFIG
    from marble3d.world import MarbleWorld

    from race2 import test5_course as lab

    course = lab.pendulum_p0(setting=setting)
    world = MarbleWorld(DEFAULT_CONFIG)
    try:
        course.machine.build(world)
    finally:
        world.close()


def geometry_of(setting) -> dict[str, Any]:
    """The built arm's own description, for the record next to the numbers."""
    from race2 import test5_course as lab

    if setting is None or not setting.armed:
        return {}
    course = lab.pendulum_p0(setting=setting)
    return course.machine.modules[lab.PENDULUM_ID].describe()


def run_p0_seeds(
    setting,
    seeds: Sequence[int],
    duration: float = DEFAULT_DURATION,
    workers: int | None = None,
    label: str | None = None,
    progress=None,
) -> P0Benchmark:
    """Every seed of one configuration, armed or not."""
    from race2.test5_course import DEFAULT_SETTING

    if setting is None:
        setting = DEFAULT_SETTING.bare()
    bench = P0Benchmark(
        label=label or setting.label(),
        setting=setting.to_json(),
        geometry=geometry_of(setting),
    )
    jobs = [(setting, int(seed), float(duration)) for seed in seeds]
    workers = workers or max(1, min(len(jobs), (os.cpu_count() or 4) - 1))
    if workers > 1:
        _warm(setting)
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for index, result in enumerate(pool.map(_one, jobs), start=1):
                bench.seeds.append(result)
                if progress:
                    progress(index, len(jobs))
    else:
        for index, job in enumerate(jobs, start=1):
            bench.seeds.append(_one(job))
            if progress:
                progress(index, len(jobs))
    bench.seeds.sort(key=lambda s: s.seed)
    return bench


def sweep(
    settings: Iterable[Any],
    seeds: Sequence[int],
    duration: float = DEFAULT_DURATION,
    workers: int | None = None,
    progress=None,
) -> list[P0Benchmark]:
    """One benchmark per configuration, with any infeasible one reported.

    A `PendulumSetting` whose geometry cannot be built - an amplitude too wide
    for the channel at that station, a reach that would pin a racer against the
    rail - raises out of `PendulumCross`. The sweep catches it and records the
    refusal rather than skipping it silently, because *which configurations the
    channel refuses* is itself a result.
    """
    out: list[P0Benchmark] = []
    for setting in settings:
        label = "bare" if setting is None else setting.label()
        try:  # noqa: SIM105 - the refusal is the result, see the docstring
            out.append(
                run_p0_seeds(
                    setting, seeds, duration=duration, workers=workers, progress=progress
                )
            )
        except ValueError as error:
            out.append(
                P0Benchmark(
                    label=label,
                    setting=None if setting is None else setting.to_json(),
                    geometry={"refused": str(error)},
                )
            )
    return out


# --- the command line -----------------------------------------------------


def _report(benches: Sequence[P0Benchmark]) -> dict[str, Any]:
    return {
        "lab": "race2 test5 pendulum p0",
        "region_in": REGION_IN,
        "region_out": REGION_OUT,
        "touch_slack": TOUCH_SLACK,
        "configurations": [bench.to_json() for bench in benches],
    }


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    from race2.test5_course import PendulumSetting

    parser = argparse.ArgumentParser(description="Pendulum Cross P0 validation")
    parser.add_argument("--seeds", type=int, default=50)
    parser.add_argument("--first-seed", type=int, default=1)
    parser.add_argument("--duration", type=float, default=DEFAULT_DURATION)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--amplitude", type=float, action="append")
    parser.add_argument("--rate", type=float, action="append")
    parser.add_argument("--phase", type=float, action="append")
    parser.add_argument("--at", type=float, action="append")
    parser.add_argument("--reach", type=float, action="append")
    parser.add_argument("--mixer-span", type=float, action="append")
    parser.add_argument("--no-bare", action="store_true")
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args(list(argv) if argv is not None else None)

    seeds = list(range(args.first_seed, args.first_seed + args.seeds))
    base = PendulumSetting()
    settings: list[Any] = []
    for amplitude in args.amplitude or [base.amplitude_deg]:
        for rate in args.rate or [base.rate]:
            for phase in args.phase or [base.phase]:
                for at in args.at or [base.at]:
                    for reach in args.reach or [base.reach]:
                        for span in args.mixer_span or [base.mixer_span]:
                            settings.append(
                                PendulumSetting(
                                    amplitude_deg=amplitude,
                                    rate=rate,
                                    phase=phase,
                                    at=at,
                                    reach=reach,
                                    mixer_span=span,
                                )
                            )
    if not args.no_bare:
        # One control per distinct course, which is every distinct (station,
        # mixer span) pair - the two fields that change the track rather than
        # the arm. A control built from a different course is not one.
        for course in sorted({(s.at, s.mixer_span) for s in settings}):
            settings.append(
                PendulumSetting(at=course[0], mixer_span=course[1], armed=False)
            )

    benches = sweep(settings, seeds, duration=args.duration, workers=args.workers)
    for bench in benches:
        if bench.geometry.get("refused"):
            print(f"{bench.label}: REFUSED  {bench.geometry['refused']}")
        else:
            print(bench.summary())
        print()
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(_report(benches), handle, indent=1)
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

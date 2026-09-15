"""What counts as an event, and the one number this whole package exists for.

## The definition

Race #2's brief asks for "meaningful events per second" and warns against
inventing metrics to produce numbers. So an event is defined once, here, and
narrowly:

    An event is a moment at which the answer to "who is winning?" measurably
    changed, or was measurably put at risk.

Everything below is a case of that, and nothing is counted that is not:

`leader_change`     rank one changes hands. The strongest case.
`top3_change`       the *set* of the leading three changes. Weaker than a lead
                    change and still a different answer to the question.
`overtake_cluster`  one or more position swaps inside the leading half of the
                    field, merged within 0.30 s. Clustered because eight
                    marbles crossing a pan swap constantly and reporting 140
                    of them would say only that the field is bunched.
`route_split`       the first racer commits to a branch. The question acquires
                    a new dimension.
`route_merge`       the last racer leaves a split. The dimension resolves.
`compression`       the leading five close to within a threshold of each other.
                    A gap that closes is a lead that is now at risk.
`separation`        they open past it. A lead that was at risk is now safe -
                    which is also a change of answer, and is why both signs
                    count.
`mechanism_hit`     a racer in the leading three meets a powered part. It has
                    not changed anything yet; it is the moment a viewer expects
                    it to, and anticipation is the thing the camera sells.
`finish`            each crossing.

## What is deliberately *not* an event

A marble touching a wall. A bank being ridden. A wheel turning with nobody near
it. A rank change between the seventh and eighth racers. Each of those is
motion, and the failure this package is trying to avoid is mistaking motion for
drama - which is the whole of what "the middle needs to earn attention better"
means.

## The number that matters

Not the density. **`longest_gap`**: the longest span in which no event of any
kind fired. Density can be bought by piling three mechanisms into one second
and leaving six seconds empty either side, and that is exactly the film the
analytics complained about. The gap cannot be bought that way.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from race2.course import Course
from race2.race import RaceOutcome

__all__ = ["Event", "Timeline", "extract", "EVENT_KINDS"]

EVENT_KINDS = (
    "leader_change",
    "top3_change",
    "overtake_cluster",
    "route_split",
    "route_merge",
    "compression",
    "separation",
    "mechanism_hit",
    "line_choice",
    "finish",
)

# Mechanism contacts at the same module inside this window are one event.
#
# The per-marble cooldown in `Race2._note_mechanism` stops one collision being
# counted twelve times as a blade sweeps past; this stops one *moment* being
# counted three times because three racers arrived at the same wheel together.
# For a viewer that is one question - "what does the drum do to the leaders" -
# and counting it three times would inflate the density by exactly the number
# of racers the shot happens to contain.
MECHANISM_WINDOW = 0.50

# How close the leading five have to get, as a fraction of the course, before
# the field counts as compressed. 3% of 176 layout units is 5.3 units, which is
# about nine marble diameters: near enough that the camera frames them as one
# group and near enough that the next mechanism can reorder them.
COMPRESSION = 0.030
# And how far apart before they count as separated. Hysteresis rather than one
# threshold, because a pack hovering on a single line would emit an event every
# sample and the count would be a measure of noise.
SEPARATION = 0.055

# Swaps inside this window are one event.
CLUSTER_WINDOW = 0.30
# Only swaps in the leading half of the field count.
LEADING_HALF = 4


@dataclass(frozen=True)
class Event:
    time: float
    kind: str
    detail: str
    ids: tuple[int, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "t": round(self.time, 3),
            "kind": self.kind,
            "detail": self.detail,
            "ids": list(self.ids),
        }


@dataclass
class Timeline:
    """Every event of one race, with the metrics that are read off it."""

    seed: int
    events: list[Event] = field(default_factory=list)
    start: float = 0.0
    end: float = 0.0
    phase_at: dict[str, tuple[float, float]] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return max(self.end - self.start, 1e-6)

    def density(self) -> float:
        return len(self.events) / self.duration

    def gaps(self) -> list[tuple[float, float]]:
        """Every interval with no event in it, as (start, length)."""
        marks = [self.start] + [e.time for e in self.events] + [self.end]
        return [(a, b - a) for a, b in zip(marks, marks[1:]) if b > a]

    def longest_gap(self) -> tuple[float, float]:
        gaps = self.gaps()
        if not gaps:
            return (self.start, self.duration)
        return max(gaps, key=lambda pair: pair[1])

    def counts(self) -> dict[str, int]:
        out = {kind: 0 for kind in EVENT_KINDS}
        for event in self.events:
            out[event.kind] = out.get(event.kind, 0) + 1
        return out

    def dead_zones(self, threshold: float = 1.6) -> list[tuple[float, float]]:
        """Spans longer than `threshold` with nothing in them.

        1.6 s is the number the brief's "a new question every 2 to 3 seconds"
        implies once you allow that the question needs a moment to be asked and
        a moment to be answered. It is a reporting threshold, not a law.
        """
        return [(at, length) for at, length in self.gaps() if length > threshold]

    def to_json(self) -> dict[str, Any]:
        at, length = self.longest_gap()
        return {
            "seed": self.seed,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "duration": round(self.duration, 3),
            "count": len(self.events),
            "density": round(self.density(), 3),
            "longest_gap": round(length, 3),
            "longest_gap_at": round(at, 3),
            "dead_zones": [[round(a, 2), round(b, 2)] for a, b in self.dead_zones()],
            "counts": self.counts(),
            "events": [event.to_json() for event in self.events],
        }

    def render(self, width: int = 74) -> str:
        """The timeline as text - the visual event map the brief asks for."""
        lines = [f"seed {self.seed}   {self.start:.2f} to {self.end:.2f} s   "
                 f"{len(self.events)} events   {self.density():.2f}/s   "
                 f"longest gap {self.longest_gap()[1]:.2f} s"]
        lines.append("")
        for event in self.events:
            lines.append(f"{event.time:7.2f}  {event.kind:<18} {event.detail}")
        at, length = self.longest_gap()
        lines.append("")
        lines.append(f"longest dead interval: {length:.2f} s from {at:.2f} s")
        for start, span in self.dead_zones():
            lines.append(f"  dead zone {start:6.2f} -> {start + span:6.2f}  ({span:.2f} s)")
        return "\n".join(lines)


def _top3(order: Sequence[int]) -> frozenset[int]:
    return frozenset(order[:3])


def extract(outcome: RaceOutcome, course: Course, sim_events: Iterable = ()) -> Timeline:
    """One race's timeline, from its rank series and its own event stream.

    `sim_events` is `Race2.events` - the branch commitments, the mechanism
    contacts and the line crossings the simulation recorded as it ran. The rank
    series supplies everything else, at the 60 Hz the locator runs at.
    """
    timeline = Timeline(seed=outcome.seed)
    series = outcome.rank_series
    if not series:
        return timeline

    # The race proper starts when the floor opens, not at tick zero: the shelf
    # holds the field for a tenth of a second and counting that as dead time
    # would penalise every course equally and mean nothing.
    release = 0.0
    for when, order in series:
        if any(outcome.racers[i].progress > 0 for i in order[:1]):
            release = when
            break
    finishes = [r.finish_time for r in outcome.racers if r.finish_time is not None]
    timeline.start = release
    timeline.end = max(finishes) if finishes else series[-1][0]

    events: list[Event] = []
    leader = None
    top3 = None
    compressed = None
    last_cluster = -99.0
    progress_by_time = {when: table for when, table in outcome.progress_series}

    for when, order in series:
        if when < release or when > timeline.end + 1e-6:
            continue
        if leader is None:
            leader = order[0]
            top3 = _top3(order)
            continue
        if order[0] != leader:
            events.append(
                Event(when, "leader_change", f"m{order[0]} takes the lead from m{leader}",
                      (order[0], leader))
            )
            leader = order[0]
            top3 = _top3(order)
            last_cluster = when
            continue
        current = _top3(order)
        if current != top3:
            gained = sorted(current - (top3 or frozenset()))
            events.append(
                Event(when, "top3_change",
                      "m" + ",m".join(str(i) for i in gained) + " into the top three",
                      tuple(gained))
            )
            top3 = current
            last_cluster = when

    # Overtake clusters, from consecutive orderings.
    previous: tuple[int, ...] | None = None
    last_cluster = -99.0
    for when, order in series:
        if when < release or when > timeline.end + 1e-6:
            previous = order
            continue
        if previous is not None:
            place = {marble: index for index, marble in enumerate(previous)}
            swaps = [
                marble for index, marble in enumerate(order[:LEADING_HALF])
                if place.get(marble, 99) > index
            ]
            if swaps and when - last_cluster >= CLUSTER_WINDOW:
                events.append(
                    Event(when, "overtake_cluster",
                          f"{len(swaps)} place(s) gained in the leading {LEADING_HALF}",
                          tuple(swaps))
                )
                last_cluster = when
        previous = order

    # Compression and separation of the leading five.
    span = course.length
    for when, order in series:
        if when < release or when > timeline.end + 1e-6:
            continue
        table = progress_by_time.get(when)
        if not table:
            continue
        leading = [table[i] for i in order[:5] if i in table]
        if len(leading) < 2:
            continue
        spread = (max(leading) - min(leading)) / span
        if compressed is None:
            compressed = spread <= COMPRESSION
            continue
        if not compressed and spread <= COMPRESSION:
            compressed = True
            events.append(Event(when, "compression",
                                f"leading five inside {spread * span:.1f} units"))
        elif compressed and spread >= SEPARATION:
            compressed = False
            events.append(Event(when, "separation",
                                f"leading five spread to {spread * span:.1f} units"))

    # The simulation's own record: branch commitments, mechanism contacts,
    # finishes. Splits and merges are per *stage*, not per marble.
    split_first: dict[str, float] = {}
    split_last: dict[str, float] = {}
    last_mechanism: dict[str, float] = {}
    for record in sim_events:
        kind = getattr(record, "kind", "")
        data = getattr(record, "data", {}) or {}
        when = float(getattr(record, "time", 0.0))
        if kind == "branch":
            name = str(data.get("split", ""))
            split_first.setdefault(name, when)
            split_last[name] = when
        elif kind == "mechanism_hit":
            module = str(data.get("module"))
            if when - last_mechanism.get(module, -99.0) < MECHANISM_WINDOW:
                continue
            last_mechanism[module] = when
            events.append(
                Event(when, "mechanism_hit",
                      f"m{data.get('id')} into {module} (rank {data.get('rank')})",
                      (int(data.get("id", -1)),))
            )
        elif kind == "line_choice":
            if data.get("straddles"):
                events.append(
                    Event(when, "line_choice",
                          f"leaders split high and low through {data.get('pan')} "
                          f"(spread {data.get('spread')})")
                )
        elif kind == "finish_line":
            events.append(
                Event(when, "finish",
                      f"m{data.get('id')} finishes {data.get('order')}",
                      (int(data.get("id", -1)),))
            )
    for name, when in split_first.items():
        events.append(Event(when, "route_split", f"first racer commits at {name}"))
    for name, when in split_last.items():
        if when > split_first.get(name, when):
            events.append(Event(when, "route_merge", f"last racer through {name}"))

    events.sort(key=lambda e: (e.time, e.kind))
    timeline.events = [e for e in events if release - 1e-9 <= e.time <= timeline.end + 1e-6]

    # When each phase was on screen, so a timeline can be labelled.
    for phase in course.phases:
        first = None
        last = None
        for racer in outcome.racers:
            for stage_name in phase.stages:
                for run in course.stages[
                    next(i for i, s in enumerate(course.stages) if s.name == stage_name)
                ].runs:
                    when = racer.stage_times.get(run)
                    if when is None:
                        continue
                    first = when if first is None else min(first, when)
                    last = when if last is None else max(last, when)
        if first is not None:
            timeline.phase_at[phase.name] = (first, last if last is not None else first)
    return timeline

"""What a Race #2 course *is*, as far as everything downstream is concerned.

Race #1 hard-codes its own shape: `sloped.race.ROUTE_RUNS` names eight runs,
`_route_from_place` knows that `orange_lead` past sample 14 means orange, and
the progress table is built from those two facts. That is correct for a course
with exactly one fork and it does not survive a second one.

So Race #2 separates the course *description* from the course. A `Course` is a
machine plus three things nothing else can work out for itself:

**Stages.** The course in flow order, one entry per competitive step. A stage
holds one run, or several *parallel* runs when the field has a choice. Stages
are what make rank comparable: a marble's progress is its stage's canonical
offset plus its fraction of that stage, so two marbles in different branches of
the same split are compared on how far through the split they are and not on
which branch happens to have the longer centreline. The length difference
between branches is then a **measured route advantage** rather than a silent
term inside the rank.

That is the opposite of Race #1's choice, which accumulates real arc length and
records that the two routes differ by 5.7%. Both are honest; this one is the
one that generalises, because with three splits there are eight route lengths
and no single ordering of them is "the" course.

**Phases.** The six competitive roles, each anchored to a stage. A phase is
what an event timeline is labelled with and what the camera schedule is cut
against, and it is authored rather than inferred: the question "what is this
part of the course *for*" has an answer the geometry cannot supply.

**The finish line.** A socket, used as a gate rather than a half-space, for the
reason `sloped.race._past_line` gives - a course that folds back on itself has
its exit plane cutting through its own middle, and a half-space test is true
for half the field on tick one. Race #2 folds much harder than Race #1, so this
matters more here, not less.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from marble3d.geometry import Socket
from marble3d.machine import Machine

from sloped.track import TrackRun

__all__ = ["Stage", "Phase", "Course"]


@dataclass(frozen=True)
class Stage:
    """One competitive step of the course, and the runs that carry it.

    `span` is the stage's share of canonical course distance. It defaults to
    the mean layout length of its runs, which is the only defensible default:
    it makes a stage's weight in the ranking proportional to how much course it
    is, and it makes two branches of a split weigh the same as each other
    whatever their lengths.
    """

    name: str
    runs: tuple[str, ...]
    span: float
    role: str = ""

    @property
    def parallel(self) -> bool:
        return len(self.runs) > 1


@dataclass(frozen=True)
class Phase:
    """A named competitive role, anchored to a range of stages.

    `purpose` is the answer to the module design rule's second question - not
    what the module physically does, but what it does to the race *order*. It
    is carried through to the event timeline and the documentation so the claim
    and the measurement sit next to each other.
    """

    name: str
    stages: tuple[str, ...]
    purpose: str


@dataclass
class Course:
    """A built machine, described well enough to race and to film."""

    machine: Machine
    runs: dict[str, TrackRun]
    stages: tuple[Stage, ...]
    phases: tuple[Phase, ...]
    finish_line: Socket
    title: str = ""
    concept: str = ""
    # Extra colliders a marble may legitimately be standing on while located on
    # a run it is nowhere near the centreline of: a splitter nose, a catch
    # apron. Keyed by module id; the value is the runs it excuses.
    aprons: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # Module ids that are mechanisms rather than channel: a wheel, a stud
    # field, a splitter blade. Named rather than inferred, because "is this
    # module an obstacle" is a question about what it is *for*, and a course
    # that inferred it from the class would stop being able to say that one
    # particular wheel is decorative.
    stations: tuple[str, ...] = ()
    notes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        seen: set[str] = set()
        for stage in self.stages:
            for name in stage.runs:
                if name not in self.runs:
                    raise ValueError(f"stage {stage.name!r} names unknown run {name!r}")
                if name in seen:
                    raise ValueError(f"run {name!r} is in two stages")
                seen.add(name)
        missing = set(self.runs) - seen
        if missing:
            raise ValueError(f"runs in no stage: {sorted(missing)}")
        named = {stage.name for stage in self.stages}
        for phase in self.phases:
            for stage in phase.stages:
                if stage not in named:
                    raise ValueError(f"phase {phase.name!r} names unknown stage {stage!r}")

        offset = 0.0
        self.offsets: dict[str, float] = {}
        self.spans: dict[str, float] = {}
        self.stage_of: dict[str, Stage] = {}
        for stage in self.stages:
            for name in stage.runs:
                self.offsets[name] = offset
                self.spans[name] = stage.span
                self.stage_of[name] = stage
            offset += stage.span
        self.length = offset

    # --- the ordering ----------------------------------------------------

    def progress_at(self, run: str, fraction: float) -> float:
        """Canonical course distance for a marble `fraction` through `run`."""
        return self.offsets[run] + self.spans[run] * min(max(fraction, 0.0), 1.0)

    def splits(self) -> tuple[Stage, ...]:
        return tuple(stage for stage in self.stages if stage.parallel)

    def branch_of(self, run: str) -> str | None:
        """Which side of its split a run is, or None if it is not in one."""
        stage = self.stage_of.get(run)
        if stage is None or not stage.parallel:
            return None
        return run

    def phase_of(self, run: str) -> str:
        stage = self.stage_of.get(run)
        if stage is None:
            return ""
        for phase in self.phases:
            if stage.name in phase.stages:
                return phase.name
        return ""

    # --- description ------------------------------------------------------

    def run_names(self) -> tuple[str, ...]:
        return tuple(name for stage in self.stages for name in stage.runs)

    def layout_length(self) -> float:
        """The longest way round, in layout units - the course as built."""
        total = 0.0
        for stage in self.stages:
            total += max(self.runs[name].arc[-1] for name in stage.runs)
        return total

    def drop(self) -> float:
        first = self.runs[self.stages[0].runs[0]]
        last = self.runs[self.stages[-1].runs[0]]
        return first.path[0][1] - last.path[-1][1]

    def footprint(self) -> tuple[float, float]:
        """Plan extent, in layout units: (x span, z span)."""
        xs: list[float] = []
        zs: list[float] = []
        for run in self.runs.values():
            for point in run.path:
                xs.append(point[0])
                zs.append(point[2])
        return (max(xs) - min(xs), max(zs) - min(zs))

    def to_json(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "concept": self.concept,
            "length": round(self.length, 4),
            "layout_length": round(self.layout_length(), 3),
            "drop": round(self.drop(), 3),
            "footprint": [round(v, 2) for v in self.footprint()],
            "stages": [
                {
                    "name": stage.name,
                    "runs": list(stage.runs),
                    "span": round(stage.span, 4),
                    "role": stage.role,
                    "parallel": stage.parallel,
                    "lengths": {
                        name: round(self.runs[name].arc[-1], 3) for name in stage.runs
                    },
                }
                for stage in self.stages
            ],
            "phases": [
                {"name": p.name, "stages": list(p.stages), "purpose": p.purpose}
                for p in self.phases
            ],
            "stations": list(self.stations),
        }


def stage(name: str, runs: dict[str, TrackRun], names: Sequence[str], role: str = "",
          span: float | None = None) -> Stage:
    """A stage whose span defaults to the mean layout length of its runs."""
    chosen = tuple(names)
    if not chosen:
        raise ValueError(f"stage {name!r} has no runs")
    if span is None:
        span = sum(runs[n].arc[-1] for n in chosen) / len(chosen)
    return Stage(name=name, runs=chosen, span=float(span), role=role)


def merged_stages(items: Iterable[Stage]) -> tuple[Stage, ...]:
    return tuple(items)

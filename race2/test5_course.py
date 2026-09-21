"""PENDULUM LAB: the smallest Race #2 course that can judge one pendulum.

Not the Prediction Gauntlet. This is a P0 mechanism laboratory whose only job
is to answer whether `race2.test5_parts.PendulumCross` produces readable,
physically caused changes of race order without jams, escapes or a fixed slot
advantage. It is kept in its own module, with its own registry, so that it can
never be confused with `race2.courses.switchyard` - which is filmed, frozen and
eight racers wide - for the reason `race2.courses` gives for existing at all: a
report headed with a production name must never quietly be a concept's numbers.

## What it is made of, and why each piece is borrowed rather than written

Everything structural is SWITCHYARD's, unchanged:

- `kit.serpentine` - the same switchback plan law
- `concepts._run` - the same entry-width / body-width composition
- `concepts._breaks_at` - the same "cut at a plan distance, not an index"
- `concepts._attach_start` - the same shelf-and-trapdoor release, at six bays
- the `Mixer` station from `sloped.stations` - the same nine-stud fairness field
- `race2.parts.RunOut` - the same finish deck, the one V33.1 corrected
- `race2.course.Course` - the same stage/phase description

(That fifth line names its module mid-sentence deliberately.
`tests/test_race2_isolation.py` refuses any line in this package that *begins*
with the shared package's name, because that is what a monkeypatch of a shared
primitive looks like, and it reads prose as code. Every other docstring in
`race2` follows the same convention.)

What is new is a **five-run prefix of the eleven-run skeleton** and exactly one
mechanism. `race2.concepts._skeleton_runs` cuts the full plan at ten fixed
places and cannot be asked for fewer, so the prefix is cut here instead - from
the same `SKELETON` tuple, at the same `SKELETON_BREAKS` distances. Run *i* of
this lab is then the same stretch of hill as run *i* of SWITCHYARD, sample for
sample, and `tests/test_race2_test5_lab.py` asserts that centreline by
centreline. Only the last name differs: what SWITCHYARD calls `corr2` is this
course's final sprint, because in five runs it is one.

    head    straight 14.0 x 4.2    release, and destroy the bay order
    pan1    hairpin  4.8 r 180     compress: the field arrives level
    corr1   straight 17.0 x 4.2    THE PENDULUM, and nothing else
    pan2    hairpin  4.8 r 180     recompress: the comeback opportunity
    sprint  straight 16.0 x 4.0    a clean fall with nothing on it

77.2 layout units of centreline and 16.8 of fall - 44% of SWITCHYARD's length,
which is the point: a mechanism laboratory should cost a third of a production
seed to run and should contain no second mechanism whose effect could be
mistaken for the first's.

## Six racers, and why the bay count is not the marble count

`MarbleSimulation` truncates the start's bays to the marble count with
`starts[:marble_count]`, so an eight-bay shelf asked for six racers loads the
six bays on *one side* of the band and leaves two empty. That is a lateral bias
built into the release before the race starts. `DropStart` already takes a bay
count, and `bay_across` centres whatever it is given, so the lab builds a
**six**-bay shelf and races six: the field is symmetric about the centreline,
and `docs/race2_test5_prediction_gauntlet.md`'s six-racer lock is honoured in
the geometry rather than in the argument list.

## The control

The registry carries two courses, not one. `pendulum_p0` has the arm;
`pendulum_p0_bare` is the identical course with the module left out. A
rank-change rate on its own says nothing - a corridor reorders a field by
itself - so every number this lab reports has a no-arm twin over the same
seeds. Removing a module renumbers Bullet's bodies, so the bare course is not a
perturbation of the armed one and no per-seed claim may be made across the
pair; the comparison is between *distributions*, which is what a rate is.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from marble3d.config import CoreConfig, DEFAULT_CONFIG
from marble3d.geometry import Transform
from marble3d.machine import Machine

from sloped.stations import Mixer

from race2 import kit
from race2.concepts import (
    BASE_SCALE,
    SKELETON,
    SKELETON_BREAKS,
    SKELETON_START,
    STUD_HEIGHT,
    STUD_RADIUS,
    STUD_SPAN,
    W_BAND,
    W_LANE,
    W_NECK,
    W_PAN,
    _attach_start,
    _breaks_at,
    _mid,
    _run,
)
from race2.course import Course, Phase, stage
from race2.parts import RunOut
from race2.test5_parts import PendulumCross
from race2.track import RaceRun

__all__ = [
    "BAYS",
    "P0_BREAKS",
    "P0_SEGMENTS",
    "P0_SKELETON",
    "P0_WIDTHS",
    "PendulumSetting",
    "DEFAULT_SETTING",
    "TEST5_COURSES",
    "build",
    "corridor_end",
    "course_names",
    "pendulum_p0",
    "pendulum_p0_bare",
    "pendulum_progress",
    "window_progress",
]

# Six, and it is the geometry rather than the argument list - see the module
# docstring.
BAYS = 6

# The first five elements of the production skeleton, and the first four of its
# breaks. Sliced rather than retyped so a change to the plan cannot leave the
# lab racing a hill the production course no longer has.
P0_SKELETON = SKELETON[:5]
P0_BREAKS = SKELETON_BREAKS[:4]
P0_SEGMENTS = ("head", "pan1", "corr1", "pan2", "sprint")

# Six knots for five runs: knot i is run i's entry and knot i+1 is what it
# holds and hands on, exactly as `concepts._skeleton_runs` defines it.
P0_WIDTHS = (W_BAND, W_BAND, W_PAN, W_LANE, W_PAN, W_NECK)

# The head band holds its full width until the stud field has been passed, then
# eases to the first pan's. SWITCHYARD's own number, for its own reason: the
# studs are the one mechanism that has to reach the whole field at once.
P0_HOLD = {"head": (0.72, 0.97)}

P0_ROLES = {
    "head": "release",
    "pan1": "compress",
    "corr1": "pendulum",
    "pan2": "recompress",
    "sprint": "sprint",
}

# Which run the pendulum stands on. Named rather than inlined because every
# measurement in `race2.test5_lab` is scoped to this run and a second copy of
# the string is a second place for it to go wrong.
PENDULUM_RUN = "corr1"
PENDULUM_ID = "pendulum"
MIXER_ID = "studs"


@dataclass(frozen=True)
class PendulumSetting:
    """One whole lab configuration, as a picklable value.

    Frozen and made of numbers so a benchmark can hand it to a process pool.
    `at` is a fraction along `corr1` rather than a sample index, because the
    sample count follows the run's plan length and an index would mean a
    different place if the skeleton were ever re-cut.

    Two fields are not about the pendulum, and both are here rather than in a
    second object because a control has to be built from the *same* value as
    the thing it controls or it is not a control:

    `armed` selects whether the arm is built at all. The no-arm control is
    therefore a setting rather than an absence, and it carries the same start
    and the same corridor as the configuration it is compared against.

    `mixer_span` is how much of the head band the stud row covers. It is a
    lab-fairness knob, not a pendulum knob, and it is scannable because it had
    to be: at six bays the default 0.90 lines the +/-1.23 bays up with a stud
    dead ahead while the +/-2.05 bays thread between two, and the resulting
    mid-lane penalty is in the *control* as well as in the armed course. See
    `docs/race2_test5_pendulum_p0.md`.
    """

    amplitude_deg: float = PendulumCross.AMPLITUDE_DEG
    rate: float = PendulumCross.RATE
    phase: float = 0.0
    at: float = 0.62
    reach: float = PendulumCross.REACH
    clearance: float = PendulumCross.CLEARANCE
    mixer_span: float = STUD_SPAN
    armed: bool = True

    def bare(self) -> "PendulumSetting":
        """The same lab with the arm left out."""
        return PendulumSetting(
            amplitude_deg=self.amplitude_deg,
            rate=self.rate,
            phase=self.phase,
            at=self.at,
            reach=self.reach,
            clearance=self.clearance,
            mixer_span=self.mixer_span,
            armed=False,
        )

    def label(self) -> str:
        span = "" if self.mixer_span == STUD_SPAN else f"_m{self.mixer_span:g}"
        if not self.armed:
            return f"bare_x{self.at:g}{span}"
        return (
            f"a{self.amplitude_deg:g}_r{self.rate:g}_p{self.phase:g}"
            f"_x{self.at:g}_h{self.reach:g}{span}"
        )

    def to_json(self) -> dict[str, float | bool]:
        return {
            "amplitude_deg": self.amplitude_deg,
            "rate": self.rate,
            "phase": self.phase,
            "at": self.at,
            "reach": self.reach,
            "clearance": self.clearance,
            "mixer_span": self.mixer_span,
            "armed": self.armed,
        }


DEFAULT_SETTING = PendulumSetting()


def p0_runs() -> dict[str, RaceRun]:
    """The five runs of the lab, cut from the production skeleton's prefix."""
    if len(P0_WIDTHS) != len(P0_SEGMENTS) + 1:
        raise ValueError(
            f"{len(P0_SEGMENTS)} runs need {len(P0_SEGMENTS) + 1} width entries"
        )
    master = kit.serpentine(
        SKELETON_START, 0.0, P0_SKELETON, straight_step=3.2, turn_step_deg=10.0
    )
    parts = kit.cut(master, _breaks_at(master, P0_BREAKS))
    if len(parts) != len(P0_SEGMENTS):
        raise ValueError(f"{len(parts)} cut parts against {len(P0_SEGMENTS)} names")
    out: dict[str, RaceRun] = {}
    for index, (name, controls) in enumerate(zip(P0_SEGMENTS, parts)):
        hold_to, blend_to = P0_HOLD.get(name, (0.04, 0.55))
        out[name] = _run(
            name,
            controls,
            P0_WIDTHS[index],
            P0_WIDTHS[index + 1],
            hold_to=hold_to,
            blend_to=blend_to,
        )
    return out


def _stages_and_phases(runs: dict[str, RaceRun], armed: bool):
    stages = tuple(stage(name, runs, [name], P0_ROLES[name]) for name in P0_SEGMENTS)
    middle = (
        "one pendulum sweeping the racing line; a racer's delay is where the arm "
        "is when it arrives, and nothing else stands in this corridor"
        if armed
        else "the same corridor with the arm removed - the control against which "
        "every rank-change rate in this lab is read"
    )
    phases = (
        Phase("start_scramble", ("head",),
              "release six racers in one tick and destroy the bay order before "
              "the course narrows"),
        Phase("approach", ("pan1",),
              "a banked hairpin that compresses the field and hands the corridor "
              "a level pack with a readable line into the mechanism"),
        Phase("pendulum", ("corr1",), middle),
        Phase("recovery", ("pan2",),
              "a second hairpin: whatever the arm did, this is where a delayed "
              "racer can get it back"),
        Phase("final_sprint", ("sprint",),
              "a straight fall with nothing on it, so the last order change is "
              "visible"),
    )
    return stages, phases


def _assemble(setting: PendulumSetting, config: CoreConfig | None) -> Course:
    runs = p0_runs()
    armed = setting.armed
    machine = Machine("race2_test5_pendulum_p0" if armed else "race2_test5_pendulum_bare")
    _attach_start(machine, runs["head"], bays=BAYS)
    for name in P0_SEGMENTS:
        machine.add(runs[name], Transform())
    # The fairness mechanism, unchanged from SWITCHYARD: nine studs across the
    # head band while the field is still a clump and the channel is at its
    # widest. This is what stops the bay a racer started in deciding the race,
    # and the slot correlation this lab reports is its result.
    machine.add(
        Mixer(
            MIXER_ID,
            runs["head"],
            at=_mid(runs["head"], 0.62),
            pin_height=STUD_HEIGHT,
            pin_radius=STUD_RADIUS,
            span=setting.mixer_span,
        ),
        Transform(),
    )
    if armed:
        machine.add(
            PendulumCross(
                PENDULUM_ID,
                runs[PENDULUM_RUN],
                at=_mid(runs[PENDULUM_RUN], setting.at),
                amplitude_deg=setting.amplitude_deg,
                rate=setting.rate,
                phase=setting.phase,
                reach=setting.reach,
                clearance=setting.clearance,
            ),
            Transform(),
        )
    machine.add(RunOut("runout", runs["sprint"]), Transform())

    stages, phases = _stages_and_phases(runs, armed)
    stations = (MIXER_ID, PENDULUM_ID) if armed else (MIXER_ID,)
    return Course(
        machine=machine,
        runs=runs,
        stages=stages,
        phases=phases,
        finish_line=runs["sprint"].socket("exit"),
        title="TEST5 P0  PENDULUM LAB" if armed else "TEST5 P0  PENDULUM LAB (BARE)",
        concept="pendulum_p0" if armed else "pendulum_p0_bare",
        aprons={"runout": ("sprint",)},
        stations=stations,
        notes={
            "purpose": "P0 mechanism validation for Pendulum Cross - not a Test #5 course",
            "racers": BAYS,
            "scale": BASE_SCALE,
            "skeleton": (
                "first five runs of the production skeleton: 77.2 units of plan, "
                "79.1 of centreline, 16.8 of fall"
            ),
            "mechanisms": list(stations),
            "setting": setting.to_json(),
        },
    )


def pendulum_p0(
    config: CoreConfig | None = None, setting: PendulumSetting | None = None
) -> Course:
    """The lab. `setting.armed` decides whether the arm is in it."""
    return _assemble(DEFAULT_SETTING if setting is None else setting, config)


def pendulum_p0_bare(config: CoreConfig | None = None) -> Course:
    """The same lab with the arm left out: the control."""
    return _assemble(DEFAULT_SETTING.bare(), config)


def _progress_of_sample(course: Course, index: int) -> float:
    run = course.runs[PENDULUM_RUN]
    fraction = run.sim_arc[index] / run.sim_arc[-1] if run.sim_arc[-1] else 0.0
    return course.progress_at(PENDULUM_RUN, fraction)


def pendulum_progress(course: Course) -> float | None:
    """Where the arm stands, in the course's own canonical progress units.

    None on the bare course. Read from the built module rather than recomputed
    from the setting, so a measurement window can never be centred somewhere
    the arm is not.
    """
    module = course.machine.modules.get(PENDULUM_ID)
    if module is None:
        return None
    return _progress_of_sample(course, module.index)


def window_progress(course: Course, at: float) -> float:
    """Where a setting's `at` fraction lands, with or without an arm there.

    The control course has no pendulum module to ask, and a rank-change rate
    measured over a *different* stretch of corridor than the armed course's
    would not be a control at all. Both therefore derive the window from the
    same `_mid` sample of the same run, and `race2.test5_lab` asserts that on
    the armed course this agrees with `pendulum_progress` to the unit.
    """
    return _progress_of_sample(course, _mid(course.runs[PENDULUM_RUN], at))


def corridor_end(course: Course) -> float:
    """The canonical progress at which the pendulum's corridor ends."""
    return course.offsets[PENDULUM_RUN] + course.spans[PENDULUM_RUN]


TEST5_COURSES: dict[str, Callable[[CoreConfig], Course]] = {
    "pendulum_p0": pendulum_p0,
    "pendulum_p0_bare": pendulum_p0_bare,
}


def course_names() -> tuple[str, ...]:
    return tuple(TEST5_COURSES)


def build(name: str, config: CoreConfig | None = None) -> Course:
    if name not in TEST5_COURSES:
        raise ValueError(f"unknown Test #5 course {name!r}; have {sorted(TEST5_COURSES)}")
    return TEST5_COURSES[name](config or DEFAULT_CONFIG)

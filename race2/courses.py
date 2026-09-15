"""SWITCHYARD: the production Race #2 course.

Separate from `race2.concepts` on purpose. A concept is built to be compared and
then mostly thrown away; a course here has been benchmarked, tuned and filmed,
and the two must not be confusable - `tools/race2_benchmark.py` resolves a name
against this table first, so a report headed with a production name is never
quietly a concept's numbers.

## Why this one

Three concepts were built on one skeleton and raced over 24 seeds each
(`docs/validation/race2/concepts.json`):

    concept      finish  all-8  stuck  slot r  lead  ev/s  gap  worst  race
    cascade       99.5%    96%   0.0%  -0.101  18.6  5.68  2.04  3.23  15.4
    braid         46.9%     0%  53.1%  -0.044  16.6  4.90  2.83  4.90  14.2
    mechanism    100.0%   100%   0.0%  +0.018  20.0  5.95  1.59  2.00  19.2

The mechanism line wins on every column that matters, and one of them decides
it: **the worst longest-dead-interval over 24 seeds is 2.00 seconds.** The brief
asks for a new question roughly every two to three seconds; that is the
measurement of it, and neither of the others gets under three.

Braid is falsified, and usefully. Its splits jam - the two branches cannot both
be as wide as the pan that feeds them and still leave the blade somewhere to
stand - and even in the races that completed, the more popular branch of the
first split cost its takers 1.4 places of mean rank. A split that punishes the
majority is not a choice, it is a tax. Race #1 spent five sessions making one
fork work; this is the second piece of evidence that a fork is the most
expensive drama per unit of geometry available, and Race #2 buys its drama
somewhere else.

Cascade is the honourable second. Its shape is right and its lead-change rate
close, but it loses a racer in one race in twenty-five and its worst dead
interval is 3.2 seconds - a stretch of banked hairpin where the field is simply
travelling.

## The course

Five switchbacks down a compact hill: 176 layout units of centreline, 36.6 of
fall, in a plan of 27 x 48. Race #1 is 237 units in 43 x 83, so this is 73% of
the distance in 38% of the plan area - which is the whole argument about dead
travel, stated as geometry. Nothing on this course is more than about fifteen
units from the thing before it.

Eleven runs alternate between a **wide banked pan** (4.6 units of clear channel)
and a **narrow corridor** (2.8), and a powered wheel stands in four of the five
corridors.

## What each module does to the race order

This is the module design rule's second question, and it is the one that decides
whether a module earns its place.

    shelf + trapdoor  releases eight racers in the same tick with no
                      constriction under them. Does nothing to the order by
                      design: it is the only module whose job is to *not* sort.

    stud field        nine studs across a 5.9-unit band, where the field is
                      still a clump. Destroys the bay order before the course
                      narrows for the first time. This is the fairness
                      mechanism, and the slot correlation is its result.

    pan 1..5          a banked hairpin 4.6 units wide. Two jobs. It
                      RECOMPRESSES - a leader entering fast rides high on the
                      bank, travels further, and comes out level with the pack -
                      and it offers a HIGH LINE against a LOW LINE, which is a
                      route choice with no fork in it and therefore without a
                      fork's cost.

    drum              four wheels at 6.2 rad/s in a 2.8-unit corridor, 30 units
                      into the race. The biggest single reordering on the
                      course, and deliberately the earliest: the rest of the
                      race is spent recovering from it rather than setting it
                      up.

    sweep             one wheel at 2.2 rad/s whose blades sweep the whole clear
                      width. It SHUTS the corridor for about a third of every
                      turn, so a leader can be the one it catches. The only gate
                      on the course.

    pair              four blades at 4.8 rad/s. PUNISHES THE LEADER by phase: a
                      marble's wait is its arrival time modulo the blade period,
                      which is the one mechanism whose output order is not
                      monotone in its input order.

    last              the same at 3.4 rad/s, in the last corridor before the
                      sprint. SEPARATES the field again, so the final pan has
                      something to compress and the sprint has a gap to close.

    sprint            2.2 units wide, falling with nothing on it. The last order
                      change is visible because nothing else is happening.

    run-out           the deck past the line. Not a race module: it exists so
                      the winner can be photographed crossing, and so the course
                      is proved able to bring a field to a stop.
"""

from __future__ import annotations

from typing import Callable

from marble3d.config import CoreConfig, DEFAULT_CONFIG
from marble3d.geometry import Transform
from marble3d.machine import Machine

from sloped.stations import Mixer

from race2.concepts import (
    HEAD_HOLD,
    SEGMENT_NAMES,
    STUD_HEIGHT,
    STUD_RADIUS,
    STUD_SPAN,
    W_BAND,
    W_LANE,
    W_NECK,
    W_PAN,
    _attach_start,
    _mid,
    _skeleton_runs,
)
from race2.course import Course, Phase, stage
from race2.parts import RunOut, Wheel

__all__ = ["COURSES", "build", "course_names", "switchyard", "WHEELS"]

# The four wheels, as (module id, run, where along it, reach, blades, rate,
# offsets). Reach is a fraction of the local half width: under about 0.62 the
# blade leaves more than a marble diameter either side and cannot block; at 0.95
# it sweeps the clear channel and is a gate. Both kinds are wanted, and this
# table is the one place the difference between them is visible.
WHEELS = (
    ("drum", "corr1", 0.22, 0.50, 4, 6.2, (0.0, 2.6, 5.2, 7.8)),
    ("sweep", "corr2", 0.45, 0.95, 4, 2.2, (0.0,)),
    ("pair", "corr3", 0.35, 0.50, 4, 4.8, (0.0, 3.0)),
    ("last", "corr4", 0.40, 0.50, 4, 3.4, (0.0, 2.8)),
)

# What each run arrives at and what it holds, as multiples of the base half
# width. Twelve knots for eleven runs: knot i is run i's entry and knot i+1 is
# what it holds and hands to run i+1.
WIDTHS = (
    W_BAND, W_BAND, W_PAN, W_LANE, W_PAN, W_LANE,
    W_PAN, W_LANE, W_PAN, W_LANE, W_PAN, W_NECK,
)

ROLES = {
    "head": "release",
    "pan1": "compress",
    "corr1": "disrupt",
    "pan2": "recompress",
    "corr2": "gate",
    "pan3": "recompress",
    "corr3": "disrupt",
    "pan4": "recompress",
    "corr4": "disrupt",
    "pan5": "last compression",
    "sprint": "sprint",
}


def switchyard(config: CoreConfig | None = None) -> Course:
    """Five switchbacks, four powered wheels, one gate."""
    runs = _skeleton_runs(SEGMENT_NAMES, WIDTHS, holds=HEAD_HOLD)

    machine = Machine("race2_switchyard")
    _attach_start(machine, runs["head"])
    for name in SEGMENT_NAMES:
        machine.add(runs[name], Transform())
    machine.add(
        Mixer("studs", runs["head"], at=_mid(runs["head"], 0.62),
              pin_height=STUD_HEIGHT, pin_radius=STUD_RADIUS, span=STUD_SPAN),
        Transform(),
    )
    for module_id, run, where, reach, blades, rate, offsets in WHEELS:
        machine.add(
            Wheel(module_id, runs[run], at=_mid(runs[run], where),
                  reach=reach, blades=blades, rate=rate, offsets=offsets),
            Transform(),
        )
    machine.add(RunOut("runout", runs["sprint"]), Transform())

    stages = tuple(stage(name, runs, [name], ROLES[name]) for name in SEGMENT_NAMES)
    phases = (
        Phase("start_scramble", ("head",),
              "release eight racers in one tick and destroy the bay order before "
              "the course narrows for the first time"),
        Phase("first_mechanism", ("pan1", "corr1"),
              "four wheels at 6.2 rad/s in a 2.8-unit corridor - the biggest "
              "single reordering, and the earliest"),
        Phase("recompression", ("pan2",),
              "a banked pan that erases the drum's gaps, so the next question is "
              "asked of a field that is level again"),
        Phase("gate", ("corr2", "pan3"),
              "the one wheel that sweeps the whole channel; it is shut for about a "
              "third of every turn and a leader can be the one it catches"),
        Phase("second_mechanism", ("corr3", "pan4", "corr4"),
              "two counter-turning wheels, then a slower pair - the deflection "
              "cancels and only the delay is left, which is what reorders"),
        Phase("final_sprint", ("pan5", "sprint"),
              "one more bank to compress what the last wheels separated, then a "
              "straight fall with nothing on it"),
    )
    return Course(
        machine=machine,
        runs=runs,
        stages=stages,
        phases=phases,
        finish_line=runs["sprint"].socket("exit"),
        title="SWITCHYARD",
        concept="switchyard",
        aprons={"runout": ("sprint",)},
        stations=("studs", "drum", "sweep", "pair", "last"),
        notes={
            "derived_from": "concept C, mechanism line",
            "skeleton": "five switchbacks, 176.5 layout units, 36.6 drop, plan 26.6 x 48.0",
        },
    )


COURSES: dict[str, Callable[[CoreConfig], Course]] = {
    "switchyard": switchyard,
}


def course_names() -> tuple[str, ...]:
    return tuple(COURSES)


def build(name: str, config: CoreConfig | None = None) -> Course:
    if name not in COURSES:
        raise ValueError(f"unknown course {name!r}; have {sorted(COURSES)}")
    return COURSES[name](config or DEFAULT_CONFIG)

"""Three Race #2 concepts, built rather than described.

The brief asks for three *paper or code* concepts that differ in competitive
topology, evaluated and then narrowed to one. They are built here as real
courses, because the questions that decide between them - how often the lead
changes, how long the longest dead interval is, whether a split is a choice or
a coin toss - are questions no drawing answers. They are built at modest
fidelity: one start, one finish, a handful of runs each, no art, no camera.

All three sit on the **same skeleton**: the same switchback plan, the same
drop, the same start, the same run-out. What differs is the width programme and
what is standing in the channel, which is to say the competitive topology and
nothing else. That is deliberate - a comparison in which one concept is also
longer, steeper or wider measures the wrong thing.

## A - CASCADE GAUNTLET

Single route. The channel alternates between a **wide banked hairpin** and a
**narrow corridor**. The hairpin is where the field spreads: a marble can take
the long fast high line or the short slow low line, which is a route choice
with no fork in it. The corridor is where that spread is cashed in, because
four abreast becoming two abreast is a queue and a queue is an order.

## B - BRAID

Two explicit splits with a blade between the branches, each merging back into
the hairpin that follows. One branch of each split carries a wheel, so the
choice is *shorter but obstructed* against *longer but clean*, and the two
splits swap which side is which so a viewer cannot simply learn a side.

## C - MECHANISM LINE

Single route, powered. Four fast wheels, then one slow one, then a
counter-turning pair, each in a channel narrow enough that the wheel cannot be
gone round. Order changes come from *phase*: a marble's wait at a wheel is its
arrival time modulo the blade period, which is the one mechanism whose output
order is not monotone in its input order.

## Why the profile scale never changes

Every run in every concept is built at one profile scale, and the width is
modulated by `TrackRun`'s per-sample width factor instead. The reason is a
seam: `scale` multiplies the cradle *depth* as well as its width, so a run at
scale 3.0 handing over to one at 1.5 has its floor 0.39 layout units below the
other's at the shared centreline - a step a marble arrives at sideways. Width
modulation moves the walls and leaves the floor where it is, so every seam in
this package is flush in height by construction and the only thing that has to
agree across one is the width factor.
"""

from __future__ import annotations

import math
from typing import Callable, Sequence

from marble3d.config import CoreConfig, DEFAULT_CONFIG
from marble3d.geometry import Transform
from marble3d.machine import Machine

from sloped import layout
from sloped.scale import to_sim
from sloped.stations import Mixer
from race2.track import RaceRun

from race2 import kit
from race2.course import Course, Phase, stage
from race2.parts import Divider, RunOut, Wheel
from race2.start import DropStart

__all__ = ["CONCEPTS", "build", "concept_names", "SKELETON", "BASE_SCALE"]

# One profile for the whole course. 3.76 layout units of clear channel, a
# cradle 0.42 deep across its half width and 1.08 of containment above the
# floor - which is 3.8 marble radii of wall, and the number the hairpins are
# banked against.
BASE_SCALE = 2.0

# Width factors, as multiples of the base half width of 1.88.
W_BAND = 1.65      # 6.20 clear: the head, sized to catch an 8-bay start
W_PAN = 1.30       # 4.89 clear: a hairpin wide enough for a high and a low line
W_SPREAD = 1.42    # 5.34 clear: what a split opens from
W_LANE = 0.80      # 3.01 clear: a corridor, five marble diameters
W_NECK = 0.72      # 2.71 clear: the tightest the course gets

# `sloped.stations.Mixer` states its stud height and radius *before* the run's
# profile scale and its span as a *fraction* of the local half width. Both cost
# a build to find: a span passed as an absolute width put the studs two channel
# widths outside the floor, and a height passed post-scale made them 0.49 of a
# marble radius tall, which is the regime Race #1 measured as "levers a marble
# out of the channel" rather than "deflects it".
#
# So the two numbers are divided back out here, and what reaches the collider is
# exactly the geometry `docs/sloped_race_v1.md` measured: a 0.07 stud on a 0.075
# pin, a quarter of a marble radius proud of the floor.
STUD_HEIGHT = 0.07 / BASE_SCALE
STUD_RADIUS = 0.075 / BASE_SCALE
STUD_SPAN = 0.90                # of the local half width

HEAD_FALL = 1.40          # the racer's free fall from the shelf, layout units
START_ALONG = 1.35        # how far into the head run the bays sit

# The plan every concept is laid out on: five switchbacks down a compact hill.
#
# The hairpins are 4.8 layout units of radius, which at 15 layout units a
# second asks for 18.6 degrees of bank and at 20 asks for 30.8 - past the
# 28-degree ceiling, which is the intended behaviour. A marble quick enough to
# need more bank than the channel has rides up the outer wall instead, and
# riding the wall is the high line the cascade's route choice is made of.
#
# Total: 172 layout units of centreline, 36.6 of fall, a plan of 27 x 48. Race
# #1 is 237 units in a plan of 43 x 83, so this is 73% of the distance in 38%
# of the plan area - which is the whole argument about dead travel, stated as
# geometry.
SKELETON: tuple[tuple, ...] = (
    ("straight", 14.0, 4.2),
    ("turn", 4.8, 180.0, 2.2),
    ("straight", 17.0, 4.2),
    ("turn", 4.8, -180.0, 2.2),
    ("straight", 16.0, 4.0),
    ("turn", 4.8, 180.0, 2.2),
    ("straight", 16.0, 4.0),
    ("turn", 4.8, -180.0, 2.2),
    ("straight", 15.0, 3.8),
    ("turn", 4.8, 180.0, 2.2),
    ("straight", 19.0, 5.4),
)
SKELETON_START = (-5.5, 36.0, -24.0)

# Where one run ends and the next begins, as plan distance along the skeleton.
# Every concept cuts at the same eleven places, so a stage in one is the same
# stretch of hill as the stage with that index in another.
SKELETON_BREAKS = (14.0, 29.1, 46.1, 61.2, 77.2, 92.3, 108.3, 123.4, 138.4, 153.5)

# The head band holds its full six units until the pin field has been passed,
# then eases to the first pan's width over the last third. A band that started
# narrowing at its fourth sample would be four units wide where the pins are,
# and the pins are the one mechanism that has to reach the whole field at once.
HEAD_HOLD = {"head": (0.72, 0.97)}

# How far off the spine each branch of a split runs, in layout units, and how
# wide a branch is.
#
# The arithmetic has to close or the split does not work, and it closed wrong
# twice. A branch of half width `h` at drift `d` occupies `[d - h, d + h]`. The
# inner edges must not cross - `d - h` positive, with the blade's own half
# thickness inside that - and the outer edges must stay inside the run that
# feeds it. With a 2.33-unit branch (h = 1.17), a blade 0.22 thick and a
# 5.34-unit spread run (half 2.67):
#
#     inner edge   1.35 - 1.18 = 0.17   against a 0.09 blade half   ok
#     outer edge   1.35 + 1.18 = 2.53   against a 2.67 half         ok
#
# `h` is the *flared* half width - `TrackRun` opens a run 14% at its entry and
# there is no way to turn that off for a run built from control points - so
# BRANCH_WIDTH 0.55 is 1.18 of half width where it matters, not 1.03.
#
# The first attempt used a 3.01-unit branch at the same drift, which put the
# inner edges 0.24 *past* each other: the two shells interpenetrated and the
# field jammed at the nose on every seed. The second point is why branches are
# built with no entry flare - `TrackRun` opens a run 14% at its entry by
# default, which is 0.16 of extra half width and exactly enough to undo this.
BRANCH_DRIFT = 1.35
BRANCH_WIDTH = 0.55

SEGMENT_NAMES = (
    "head", "pan1", "corr1", "pan2", "corr2", "pan3",
    "corr3", "pan4", "corr4", "pan5", "sprint",
)


def _samples_for(controls: Sequence[Sequence[float]]) -> int:
    """One sample per 0.29 layout units - half a marble diameter.

    That is the facet size `sloped.course` calls the collider's physics
    parameter, and the library default of 118 samples per run would give a
    14-unit run 0.12 and a 24-unit run 0.20 instead. Clamped below because
    `Spinners` needs samples either side of its station.
    """
    return max(48, min(240, int(round(kit.plan_length(controls) / 0.29))))


# How much rail a banked pan gets above the flat cap, and over what part of it.
#
# `race2.track` has the measurement: at the flat 0.70 cap alone, 22% of the
# field rode over the outside of a hairpin. The boost is a window rather than a
# whole-run height because a corridor with 1.65 of rail on it is a corridor no
# camera can see into, which is the problem the cap exists to solve.
# Stated *before* the run's profile scale, because `TrackRun.guard_extra`
# multiplies by it - so 0.48 here is 0.96 layout units of extra rail at scale
# 2.0, and a pan's containment comes out at 1.66. Writing 0.95 here gave 1.90
# and a 2.60-unit rail, which is the trench again with an extra step in it.
PAN_GUARD_BOOST = 0.28
PAN_BOOST_WINDOW = (0.10, 0.24, 0.80, 0.94)   # fractions of the run


def _boost_for(name: str, samples: int) -> tuple[float, int, int, int, int] | None:
    """`TrackRun`'s guard window for a pan, or None for anything else."""
    if not name.startswith("pan"):
        return None
    a, b, c, d = (int(round(f * (samples - 1))) for f in PAN_BOOST_WINDOW)
    return (PAN_GUARD_BOOST, a, b, c, d)


def _run(
    name: str,
    controls,
    entry: float,
    body: float,
    hold_to: float = 0.04,
    blend_to: float = 0.55,
    **options,
) -> RaceRun:
    """A run that arrives at `entry` width and holds `body` width.

    `TrackRun` offers two width controls and neither alone is what a pan or a
    corridor wants. `taper` eases from one factor to another over the *whole*
    run, which turns a pan into a funnel and a corridor into a flare - there is
    never a stretch that is actually wide or actually narrow. `width_profile`
    holds a factor to one sample and eases to the authored width by another,
    which is the right shape but is stated relative to 1.0.

    Composed, they say the thing directly: `taper` pins the whole run at `body`,
    and `width_profile` lifts its first samples to `entry` and eases down. So a
    pan is 4.89 units of clear channel for four fifths of its length, a corridor
    is 2.33 for four fifths of its, and the transition between them is a third
    of a run rather than a step at a seam.

    A run's exit width is therefore always `body`, which is what makes the
    seams agree: the next run's `entry` is this run's `body`, and
    `_skeleton_runs` derives it rather than asking for it twice.
    """
    spec = kit.run_spec(name, controls, scale=BASE_SCALE)
    samples = _samples_for(controls)
    return RaceRun(
        name,
        spec=spec,
        samples=samples,
        taper=(body, body),
        width_profile=(
            entry / body,
            int(round(hold_to * (samples - 1))),
            int(round(blend_to * (samples - 1))),
        ),
        guard_boost=_boost_for(name, samples),
        **options,
    )


def _skeleton_runs(names: Sequence[str], knots: Sequence[float],
                   start=SKELETON_START,
                   holds: dict[str, tuple[float, float]] | None = None) -> dict[str, RaceRun]:
    """The eleven runs, each arriving at one width and holding the next.

    `knots` has one more entry than there are runs: entry `i` is what run `i`
    arrives at and entry `i+1` is what it holds and hands on. So two runs
    meeting at a seam agree on the width there by construction rather than by
    inspection, and `tools/race2_seams.py` checks that they do.

    `holds` overrides the transition window per run, as (hold fraction, blend
    fraction). The head band uses it: its pin field is two thirds of the way
    down and the band has to still be six units wide when the field reaches it.
    """
    if len(knots) != len(names) + 1:
        raise ValueError(f"{len(names)} runs need {len(names) + 1} width entries")
    master = kit.serpentine(start, 0.0, SKELETON, straight_step=3.2, turn_step_deg=10.0)
    parts = kit.cut(master, _breaks_at(master, SKELETON_BREAKS))
    if len(parts) != len(names):
        raise ValueError(f"{len(parts)} cut parts against {len(names)} names")
    holds = dict(holds or {})
    out: dict[str, RaceRun] = {}
    for index, (name, controls) in enumerate(zip(names, parts)):
        # **The funnel from a pan into a corridor is eased over half the run,
        # not a third.** A 2.31 half width squeezing to 1.42 over a third of a
        # 16-unit corridor is a wall closing on a marble that arrives from a
        # banked hairpin at 20 layout units a second with lateral velocity on
        # it, and the escapes it caused were all in the first half of a
        # corridor: five in `corr1`, four in the sprint, over 24 seeds.
        hold_to, blend_to = holds.get(name, (0.04, 0.55))
        out[name] = _run(name, controls, knots[index], knots[index + 1],
                         hold_to=hold_to, blend_to=blend_to)
    return out


def _attach_start(machine: Machine, head: TrackRun, bays: int = 8) -> DropStart:
    """The shelf, placed over the head band at the height that gives HEAD_FALL.

    A racer at rest on the shelf sits a radius above the deck; a racer at rest
    in the band sits a radius above the band's floor, which is `FLOOR_Y * scale`
    under the centreline. So the fall between them is
    `deck_top - centreline - FLOOR_Y * scale`: the radius cancels, and the deck
    height follows from the fall instead of the other way round.
    """
    index = head.index_at_length(to_sim(START_ALONG))
    point = head.path[index]
    ahead = head.path[min(index + 6, len(head.path) - 1)]
    deck_top = point[1] + layout.FLOOR_Y * head.scale + HEAD_FALL
    start = DropStart(
        "start",
        kit.frame_towards((point[0], deck_top, point[2]), ahead),
        fall=HEAD_FALL,
        exit_width=2.0 * layout.CHANNEL_HALF * head.scale * head.widths[index],
        bays=bays,
    )
    machine.add(start, Transform())
    return start


def _breaks_at(master, distances) -> list[int]:
    """Control indices nearest the given plan distances along the polyline.

    Breaks are named in layout units rather than as indices because the
    skeleton is edited in layout units, and an index that silently referred to
    a different place after a segment grew is the edit that produces a run
    boundary in the middle of a turn.
    """
    running = [0.0]
    for a, b in zip(master, master[1:]):
        running.append(running[-1] + math.hypot(b[0] - a[0], b[2] - a[2]))
    out: list[int] = []
    for target in distances:
        index = min(range(1, len(running) - 1), key=lambda i: abs(running[i] - target))
        out.append(index)
    return sorted(set(out))


def _mid(run: RaceRun, fraction: float = 0.5) -> int:
    return max(2, min(len(run.path) - 3, int(round(fraction * (len(run.path) - 1)))))


# --- A: cascade gauntlet ---------------------------------------------------


def _cascade(config: CoreConfig) -> Course:
    """Wide banked hairpin, narrow corridor, five times over."""
    knots = (W_BAND, W_BAND, W_PAN, W_LANE, W_PAN, W_LANE,
             W_PAN, W_LANE, W_PAN, W_LANE, W_PAN, W_NECK)
    runs = _skeleton_runs(SEGMENT_NAMES, knots, holds=HEAD_HOLD)

    machine = Machine("race2_cascade")
    _attach_start(machine, runs["head"])
    for name in SEGMENT_NAMES:
        machine.add(runs[name], Transform())
    # The pin field, in the head band where the field is still a clump and the
    # channel is six units wide - the only place on the course where nine pins
    # reach the whole field at once.
    machine.add(
        Mixer("pins", runs["head"], at=_mid(runs["head"], 0.62),
              pin_height=STUD_HEIGHT, pin_radius=STUD_RADIUS, span=STUD_SPAN),
        Transform(),
    )
    machine.add(
        Wheel("blades", runs["corr2"], at=_mid(runs["corr2"], 0.28),
              reach=0.50, blades=4, rate=4.2, offsets=(0.0, 3.2, 6.4)),
        Transform(),
    )
    # A second wheel set at a different rate rather than a post comb. A comb
    # that a marble cannot pass is a wall, and a comb that it can pass is the
    # stud field again: with five studs across a three-unit corridor the gaps
    # are 0.53 against a 0.57 marble, so the only comb that fits in a corridor
    # is one that does not obstruct. The rate is what differs here - 2.6 against
    # the first set's 4.2 - so the phase pattern the field meets is a new one
    # and not a repeat of the one it has already been sorted by.
    machine.add(
        Wheel("chicane", runs["corr4"], at=_mid(runs["corr4"], 0.32),
              reach=0.50, blades=3, rate=2.6, offsets=(0.0, 3.6)),
        Transform(),
    )
    machine.add(RunOut("runout", runs["sprint"]), Transform())

    roles = {
        "head": "release", "pan1": "compress", "corr1": "queue",
        "pan2": "high line against low line", "corr2": "disrupt",
        "pan3": "recompress", "corr3": "queue",
        "pan4": "recompress", "corr4": "separate",
        "pan5": "last compression", "sprint": "sprint",
    }
    stages = tuple(stage(name, runs, [name], roles[name]) for name in SEGMENT_NAMES)
    phases = (
        Phase("start_scramble", ("head",),
              "release the field and destroy the bay order before anything narrows"),
        Phase("first_compression", ("pan1", "corr1"),
              "spread across a wide banked pan, then let a 2.3-unit corridor decide who leaves first"),
        Phase("order_disruptor", ("pan2", "corr2"),
              "three counter-turning wheels; a marble's wait is its arrival modulo the blade period"),
        Phase("recompression", ("pan3", "corr3", "pan4"),
              "two pans back to back erase the corridor's gaps, so the second half starts level"),
        Phase("separation", ("corr4",),
              "a post comb that opens gaps again and hands the field to the last pan divided"),
        Phase("final_sprint", ("pan5", "sprint"),
              "one more bank, then a straight fall with nothing on it"),
    )
    return Course(
        machine=machine, runs=runs, stages=stages, phases=phases,
        finish_line=runs["sprint"].socket("exit"),
        title="A  CASCADE GAUNTLET", concept="cascade",
        aprons={"runout": ("sprint",)},
        stations=("pins", "blades", "chicane"),
    )


# --- B: braid ---------------------------------------------------------------


def _braid(config: CoreConfig) -> Course:
    """Two splits with a blade between, each merging into the pan below it."""
    names = list(SEGMENT_NAMES)
    # The two split stages arrive at and leave at the pan's own width, because
    # the pair of branches together spans exactly what the pan delivers. Only
    # the branches themselves are narrow.
    knots = (W_BAND, W_BAND, W_SPREAD, W_SPREAD, W_SPREAD, W_LANE,
             W_SPREAD, W_SPREAD, W_SPREAD, W_LANE, W_PAN, W_NECK)
    runs = _skeleton_runs(names, knots, holds=HEAD_HOLD)

    # `corr1` and `corr3` become split pairs. Authored from the run they
    # replace, so the two branches are exactly symmetric about its centreline -
    # a split whose two sides are typed independently is a split with a bias
    # nobody wrote down.
    for tag, replaced in (("s1", "corr1"), ("s2", "corr3")):
        spine = runs.pop(replaced)
        left, right = _branch_pair(spine, tag, drift=BRANCH_DRIFT)
        runs[left.id] = left
        runs[right.id] = right
        names[names.index(replaced)] = tag

    machine = Machine("race2_braid")
    _attach_start(machine, runs["head"])
    order = []
    for name in names:
        order.extend((f"{name}_left", f"{name}_right") if name.startswith("s") and
                      f"{name}_left" in runs else (name,))
    for name in order:
        machine.add(runs[name], Transform())
    machine.add(
        Mixer("pins", runs["head"], at=_mid(runs["head"], 0.62),
              pin_height=STUD_HEIGHT, pin_radius=STUD_RADIUS, span=STUD_SPAN),
        Transform(),
    )
    machine.add(Divider("wedge1", runs["s1_left"], runs["s1_right"],
                        reach=runs["s1_left"].arc[-1]), Transform())
    machine.add(Divider("wedge2", runs["s2_left"], runs["s2_right"],
                        reach=runs["s2_left"].arc[-1]), Transform())
    # Only one branch of each split carries a wheel, and the two splits put it
    # on opposite sides. That is what makes the choice a choice: obstructed and
    # short against clean and long, with the sides swapped so a viewer cannot
    # learn "always go left".
    machine.add(
        Wheel("gate1", runs["s1_left"], at=_mid(runs["s1_left"], 0.45),
              reach=0.52, blades=3, rate=5.0, offsets=(0.0,)),
        Transform(),
    )
    machine.add(
        Wheel("gate2", runs["s2_right"], at=_mid(runs["s2_right"], 0.45),
              reach=0.52, blades=3, rate=4.4, offsets=(0.0, 2.8)),
        Transform(),
    )
    machine.add(RunOut("runout", runs["sprint"]), Transform())

    stages = (
        stage("head", runs, ["head"], "release"),
        stage("pan1", runs, ["pan1"], "compress and present the choice"),
        stage("split1", runs, ["s1_left", "s1_right"], "route decision"),
        stage("pan2", runs, ["pan2"], "merge - the confrontation"),
        stage("corr2", runs, ["corr2"], "carry"),
        stage("pan3", runs, ["pan3"], "compress and present the choice"),
        stage("split2", runs, ["s2_left", "s2_right"], "route decision"),
        stage("pan4", runs, ["pan4"], "merge - the confrontation"),
        stage("corr4", runs, ["corr4"], "separate"),
        stage("pan5", runs, ["pan5"], "last compression"),
        stage("sprint", runs, ["sprint"], "sprint"),
    )
    phases = (
        Phase("start_scramble", ("head",), "release and destroy the bay order"),
        Phase("first_choice", ("pan1", "split1"),
              "a blade divides the pan's exit; the left line is blocked by a wheel, the right is clean"),
        Phase("first_merge", ("pan2", "corr2"),
              "both fields arrive in one banked pan at once, then a corridor sorts them"),
        Phase("second_choice", ("pan3", "split2"),
              "the same question with the sides swapped, so a side cannot simply be learned"),
        Phase("second_merge", ("pan4", "corr4"), "recompress, and open the comeback"),
        Phase("final_sprint", ("pan5", "sprint"), "one more bank, then a clean fall to the line"),
    )
    return Course(
        machine=machine, runs=runs, stages=stages, phases=phases,
        finish_line=runs["sprint"].socket("exit"),
        title="B  BRAID", concept="braid",
        aprons={"runout": ("sprint",)},
        stations=("pins", "wedge1", "wedge2", "gate1", "gate2"),
    )


def _branch_pair(spine: RaceRun, tag: str, drift: float,
                 width: float = BRANCH_WIDTH) -> tuple[RaceRun, RaceRun]:
    """Two narrow runs running parallel either side of a spine's centreline.

    **Constant offset, and that is the correction.** The first build eased the
    drift in from zero, the way Race #1's lobes enter one control inside the
    channel they leave. At a symmetric split that is wrong, and expensively so:
    over the first five samples the two branches were 1.2 layout units apart
    while each was still 4.7 wide, so the two channel *shells* interpenetrated -
    each branch's guard wall passing through the other's floor - and the field
    met a lattice of intersecting surfaces instead of a choice. All eight
    racers jammed inside eleven samples of the split, on every seed.

    So the branches begin already apart, each half the width of the pan that
    feeds them, with their inner edges a blade's thickness from each other and
    their outer edges exactly on the pan's own. Nothing overlaps at any sample,
    and the only thing at the nose is the blade.

    ## The lift

    A branch centred `drift` off the pan's centreline sits over a part of the
    pan's cradle that is *above* its lowest point, so a branch authored at the
    pan's own height would have its floor below the pan's at the seam - a step
    a marble arrives at sideways. The lift is the cradle rise at that offset,
    computed from the same expression `TrackRun.surface_point` uses, so the two
    floors meet at the branch centreline.
    """
    controls = list(spine.spec["controls"])
    count = len(controls)
    entry_width = float(spine.widths[0])
    across_profile = drift / (spine.scale * max(entry_width, 1e-6))
    lift = (layout.floor_y_at(across_profile) - layout.FLOOR_Y) * spine.scale

    sides: list[list[kit.Vec3]] = []
    for sign in (1.0, -1.0):
        moved: list[kit.Vec3] = []
        for index, point in enumerate(controls):
            nxt = controls[min(index + 1, count - 1)]
            prv = controls[max(index - 1, 0)]
            dx, dz = nxt[0] - prv[0], nxt[2] - prv[2]
            span = math.hypot(dx, dz) or 1.0
            left = (-dz / span, 0.0, dx / span)
            moved.append(
                (point[0] + left[0] * sign * drift,
                 point[1] + lift,
                 point[2] + left[2] * sign * drift)
            )
        sides.append(moved)
    # **The flare cannot be turned off for a run built from control points.**
    # `TrackRun` reads `entry_flare` and `exit_flare` out of the spec only on
    # the branch that takes a pre-solved path; a run built from controls gets
    # `sloped.pathing.build_path`, which calls `width_curve` with the library
    # defaults of 14% and 9%. So a branch is 14% wider at its entry than its
    # body width says, and `BRANCH_WIDTH` is chosen against the flared figure
    # rather than the authored one. Stated here because the first build chose
    # it against the authored one and the inner edges met.
    return (
        _run(f"{tag}_left", sides[0], width, width),
        _run(f"{tag}_right", sides[1], width, width),
    )


# --- C: mechanism line ------------------------------------------------------


def _mechanism(config: CoreConfig) -> Course:
    """Powered parts in series, each in a channel narrow enough to matter."""
    knots = (W_BAND, W_BAND, W_PAN, W_LANE, W_PAN, W_LANE,
             W_PAN, W_LANE, W_PAN, W_LANE, W_PAN, W_NECK)
    runs = _skeleton_runs(SEGMENT_NAMES, knots, holds=HEAD_HOLD)

    machine = Machine("race2_mechanism")
    _attach_start(machine, runs["head"])
    for name in SEGMENT_NAMES:
        machine.add(runs[name], Transform())
    machine.add(
        Mixer("pins", runs["head"], at=_mid(runs["head"], 0.62),
              pin_height=STUD_HEIGHT, pin_radius=STUD_RADIUS, span=STUD_SPAN),
        Transform(),
    )
    # Four fast wheels in a two-unit channel: the biggest single reordering on
    # the course, and deliberately the earliest, so the rest of the race is
    # spent recovering from it rather than setting it up.
    machine.add(
        Wheel("drum", runs["corr1"], at=_mid(runs["corr1"], 0.22),
              reach=0.50, blades=4, rate=6.2, offsets=(0.0, 2.6, 5.2, 7.8)),
        Transform(),
    )
    # One slow blade. At 1.5 rad/s a blade takes 1.05 s to cross the channel, so
    # it is shut for about a third of every revolution and a leader can be the
    # one it catches.
    machine.add(
        Wheel("sweep", runs["corr2"], at=_mid(runs["corr2"], 0.45),
              reach=0.95, blades=4, rate=2.2, offsets=(0.0,)),
        Transform(),
    )
    machine.add(
        Wheel("pair", runs["corr3"], at=_mid(runs["corr3"], 0.35),
              reach=0.50, blades=4, rate=4.8, offsets=(0.0, 3.0)),
        Transform(),
    )
    machine.add(
        Wheel("last", runs["corr4"], at=_mid(runs["corr4"], 0.40),
              reach=0.50, blades=4, rate=3.4, offsets=(0.0, 2.8)),
        Transform(),
    )
    machine.add(RunOut("runout", runs["sprint"]), Transform())

    roles = {
        "head": "release", "pan1": "compress", "corr1": "disrupt",
        "pan2": "recompress", "corr2": "gate",
        "pan3": "recompress", "corr3": "disrupt",
        "pan4": "recompress", "corr4": "disrupt",
        "pan5": "last compression", "sprint": "sprint",
    }
    stages = tuple(stage(name, runs, [name], roles[name]) for name in SEGMENT_NAMES)
    phases = (
        Phase("start_scramble", ("head",), "release and destroy the bay order"),
        Phase("first_mechanism", ("pan1", "corr1"),
              "four fast wheels in a two-unit channel - the biggest single reordering"),
        Phase("recompression", ("pan2",), "a wide banked pan that erases the drum's gaps"),
        Phase("gate", ("corr2", "pan3"),
              "one slow blade that shuts the channel for a third of every turn"),
        Phase("second_mechanism", ("corr3", "pan4", "corr4"),
              "two wheels against each other, then a slower pair - deflection cancels, delay does not"),
        Phase("final_sprint", ("pan5", "sprint"), "one more bank, then a clean fall to the line"),
    )
    return Course(
        machine=machine, runs=runs, stages=stages, phases=phases,
        finish_line=runs["sprint"].socket("exit"),
        title="C  MECHANISM LINE", concept="mechanism",
        aprons={"runout": ("sprint",)},
        stations=("pins", "drum", "sweep", "pair", "last"),
    )


CONCEPTS: dict[str, Callable[[CoreConfig], Course]] = {
    "cascade": _cascade,
    "braid": _braid,
    "mechanism": _mechanism,
}


def concept_names() -> tuple[str, ...]:
    return tuple(CONCEPTS)


def build(name: str, config: CoreConfig | None = None) -> Course:
    if name not in CONCEPTS:
        raise ValueError(f"unknown concept {name!r}; have {sorted(CONCEPTS)}")
    return CONCEPTS[name](config or DEFAULT_CONFIG)

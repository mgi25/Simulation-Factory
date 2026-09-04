"""The V0.2 split course: one race, two ways down the middle of it.

The prototype is a ladder - every racer meets every obstacle in the same
order, and "further along" means "further down". This course exists to
break that assumption on purpose, because a race architecture that only
works on a ladder is not an architecture.

    START            ten racers behind a gate
    OPENING          four rows of pegs, spreading the field across the width
    SPLIT            a wall down the middle of the course, capped by a peg
     |         \\
    LEFT        RIGHT
    a switchback     a steep slick run through one pass with a rotor
    of six shelves   turning underneath it
    slow and safe    quick when it goes well, expensive when it does not
     |         /
    REJOIN           a wide merge, both paths into one field again
    FINAL            plinko, a rotor, a scatter, and a second rotor
    FINISH           a wide chute into a sloped paddock

Nothing chooses a branch. There is no rule, no die roll and no per-racer
preference anywhere in this file: there is a peg in the middle of the
course with a wall below it, and which side of the peg a racer comes off
decides where it goes. That is the whole mechanism, and it is why the split
is worth having - the choice is made by the same physics that decides
everything else about a race.

The two paths are meant to be genuinely different rather than mirror
images, because two equivalent paths would test nothing:

* Left is a switchback. Six grippy shelves, each open at the opposite end,
  so a racer covers the corridor six times over to descend it. There is
  nothing on it to go wrong, and it is the longer way down.

* Right is a steep slick chute through a single pass with a rotor turning
  under it, fast enough to throw a racer the width of the corridor. Every
  racer on this branch goes through that gap, so the hazard cannot be
  avoided by taking a good line - only survived or not.

Ranking across the two is not this file's problem, which is the point of
the design: the course states, per plane, how far along a route that plane
is, and `race.progress` compares those numbers. See `race.course` for what
those values mean and `docs/race_v02.md` for why they are the shape they
are.
"""

from __future__ import annotations

import random

from engine.arena import CANVAS_WIDTH
from race.course import BOUNCY, SLICK, TRACK, RaceCourse
from race.courses.builder import CourseBuilder
from race.seeds import make_course_rng

__all__ = ["SPLIT_COURSE_ID", "BRANCH_LEFT", "BRANCH_RIGHT", "build_split_course"]

SPLIT_COURSE_ID = "split"

BRANCH_LEFT = "left"
BRANCH_RIGHT = "right"

COURSE_TOP = 0.0
COURSE_BOTTOM = 6840.0

# Boundary, exactly as the prototype builds it: side walls centred on the
# canvas edges, so the playable width is what a racer actually has.
WALL_THICKNESS = 80.0
WALL_INSET = WALL_THICKNESS / 2.0
PLAYABLE_LEFT = WALL_INSET
PLAYABLE_RIGHT = CANVAS_WIDTH - WALL_INSET

SURFACE = 26.0  # thickness of an ordinary ramp or shelf

GRID_COLUMNS = (160.0, 350.0, 540.0, 730.0, 920.0)
GRID_ROWS = (500.0, 610.0)
GATE_Y = 700.0

SPINNER_SPEED_JITTER = 0.08


def build_split_course(seed: int) -> RaceCourse:
    """Build the split course for a seed.

    As with the prototype, only the spinners vary with the seed - their
    start angle freely, their speed slightly. The geometry is fixed: a
    course whose shape moved between seeds could not be measured.
    """
    rng = make_course_rng(seed)
    builder = CourseBuilder(SPLIT_COURSE_ID, CANVAS_WIDTH, COURSE_TOP)

    _boundary(builder)
    _start(builder)
    _opening(builder)
    _split(builder)
    _left_branch(builder)
    _right_branch(builder, rng)
    _rejoin(builder)
    _final(builder, rng)
    _finish(builder)

    return builder.finish(
        COURSE_BOTTOM,
        drop=COURSE_BOTTOM - COURSE_TOP,
        playable_width=PLAYABLE_RIGHT - PLAYABLE_LEFT,
        corridor_width=LEFT_FACE - PLAYABLE_LEFT,
        branches=2.0,
    )


# --- boundary ---------------------------------------------------------------


def _boundary(builder: CourseBuilder) -> None:
    """Two side walls, a ceiling and a floor: the course cannot be left."""
    builder.section = "boundary"
    builder.wall((0.0, COURSE_TOP), (0.0, COURSE_BOTTOM), WALL_THICKNESS)
    builder.wall(
        (CANVAS_WIDTH, COURSE_TOP), (CANVAS_WIDTH, COURSE_BOTTOM), WALL_THICKNESS
    )
    builder.wall((0.0, COURSE_TOP), (CANVAS_WIDTH, COURSE_TOP), WALL_THICKNESS)
    builder.wall((0.0, COURSE_BOTTOM), (CANVAS_WIDTH, COURSE_BOTTOM), WALL_THICKNESS)


# --- start ------------------------------------------------------------------


def _start(builder: CourseBuilder) -> None:
    builder.begin_section("start", COURSE_TOP)
    builder.gate((PLAYABLE_LEFT, GATE_Y), (PLAYABLE_RIGHT, GATE_Y), SURFACE)
    for row_y in GRID_ROWS:
        for column_x in GRID_COLUMNS:
            builder.spawn(column_x, row_y)
    builder.checkpoint("start", GATE_Y, (540.0, 760.0))


# --- opening ----------------------------------------------------------------

OPENING_PEGS = (
    (880.0, (240.0, 420.0, 600.0, 780.0)),
    (990.0, (150.0, 330.0, 510.0, 690.0, 870.0)),
    (1100.0, (240.0, 420.0, 600.0, 780.0)),
    (1210.0, (150.0, 330.0, 510.0, 690.0, 870.0)),
)
OPENING_PEG_RADIUS = 32.0
OPENING_EXIT_Y = 1290.0


def _opening(builder: CourseBuilder) -> None:
    """Four rows of pegs across the full width, and nothing else.

    This section is a plinko field rather than the pair of slick shelves the
    prototype opens with, and the difference is the whole reason the split
    below it works. A shelf translates a field: every racer that lands on
    one leaves it at the same place, so a course that opens with two of them
    hands the next section a column of racers a few pixels wide. That is
    fine when the next section is a funnel and fatal when it is a fork - the
    first two versions of this course put the entire field down one branch
    in every seed, because the entire field arrived at the splitter on the
    same line.

    Pegs do not translate a field, they spread one. Ten racers leave the
    grid across nine hundred pixels of width and are still spread across it
    four rows later, mixed but not gathered, which is exactly what a fork
    needs to be given.
    """
    builder.begin_section("opening", GATE_Y)
    for row_y, columns in OPENING_PEGS:
        for column_x in columns:
            builder.peg(column_x, row_y, OPENING_PEG_RADIUS, BOUNCY)
    builder.checkpoint("opening_exit", OPENING_EXIT_Y, (540.0, 1330.0))


# --- the split --------------------------------------------------------------

SPLIT_Y = 1380.0
SPLITTER_X = 540.0
SPLITTER_Y = 1440.0
SPLITTER_RADIUS = 44.0

DIVIDER_X = 540.0
DIVIDER_HALF = 20.0
DIVIDER_TOP = 1500.0
DIVIDER_BOTTOM = 4120.0

# The corridors, as inner faces. A branch checkpoint's corridor is stated
# against the divider centre line rather than these, so the two ranges tile
# with no gap between them: a racer cannot be in neither corridor, because
# it cannot be inside the wall.
LEFT_FACE = DIVIDER_X - DIVIDER_HALF
RIGHT_FACE = DIVIDER_X + DIVIDER_HALF

ENTRY_Y = 1620.0
EXIT_Y = 3900.0

# Course progress on the branches. The split occupies the interval between
# main-line planes 2 (`split`) and 3 (`rejoin`), and each path subdivides
# that interval its own way: seven rungs on the left, four on the right.
# Both enter at the same value and leave at the same value, because two
# racers taking different paths have to start and end the split level -
# what separates them is how long each path takes, not what it is worth.
ENTRY_PROGRESS = 2.15
EXIT_PROGRESS = 2.88


def _split(builder: CourseBuilder) -> None:
    """A wall down the middle of the course, capped by a peg.

    There is no funnel here and no shape that gathers, because the split is
    decided by where a racer already is. A racer coming out of the plinko on
    the left half falls into the left corridor and a racer on the right half
    falls into the right one; only the few that arrive over the centre line
    have anything to decide, and the peg decides for them by being round.

    The peg's other job is the one that would be easy to leave out. The
    divider is a box, so its top is a flat forty-pixel ledge, and a racer
    that came to rest on it would be in neither corridor - on neither route,
    with a progress graph that has nothing to say about it until it fell
    off. The peg is wider than the ledge and sits low enough to overlap it,
    so there is no flat top to land on at all.
    """
    builder.begin_section("split", OPENING_EXIT_Y)
    # Above the peg, not below it. A rescue at the fork puts a racer back
    # where it has to make the choice again, rather than dropping it into one
    # corridor - and the space below the peg belongs to the peg: the first
    # version respawned at 1410, fourteen pixels inside it.
    builder.checkpoint("split", SPLIT_Y, (540.0, 1340.0))
    builder.peg(SPLITTER_X, SPLITTER_Y, SPLITTER_RADIUS, BOUNCY)
    builder.wall(
        (DIVIDER_X, DIVIDER_TOP), (DIVIDER_X, DIVIDER_BOTTOM), DIVIDER_HALF * 2.0
    )


# --- the left branch: long, grippy, and hard to get wrong --------------------

# Each shelf runs the width of the corridor and stops short of one wall, so
# a racer rolls the length of it and drops off the open end onto the next
# one going the other way. Six of them is around 2800 pixels of travel to
# descend 2130, against the right-hand branch's 2100 pixels to descend 2080.
#
# Their slope is the number that decides whether this course has a fork at
# all, and it was found by measurement rather than by eye. At the fourteen
# degrees the first version used, the switchback cost nine seconds between
# the split and the rejoin against the right-hand branch's six and a half:
# nobody who went left ever won a race, in any seed, so the fork was not a
# choice but a punishment. Sweeping the slope from there to thirty-seven
# brought the left down to 6.7 seconds against the right's 6.7, and the
# winner's branch with it - from 0 wins in 16 seeds to 9 of them.
#
# The two are not level because the numbers were made to match. They are
# level because at this slope the *distributions* overlap: the left runs
# 6.5 to 7.3 seconds and almost never anything else, the right runs 6.0 to
# 8.0 depending entirely on what the rotor does. A clean run down the right
# beats any run down the left, and a caught one loses to all of them.
LEFT_SHELVES = (
    ((LEFT_FACE, 1700.0), (150.0, 1980.0)),
    ((PLAYABLE_LEFT, 2070.0), (410.0, 2350.0)),
    ((LEFT_FACE, 2440.0), (150.0, 2720.0)),
    ((PLAYABLE_LEFT, 2810.0), (410.0, 3090.0)),
    ((LEFT_FACE, 3180.0), (150.0, 3460.0)),
    ((PLAYABLE_LEFT, 3550.0), (410.0, 3830.0)),
)

# One rung in each drop gap: the plane a racer crosses on its way off one
# shelf and towards the next, with a respawn point in the clear air beside
# it. Five rungs for six shelves - the last shelf hands over to `left_exit`.
LEFT_RUNGS = (
    ("left_1", 2010.0, (95.0, 2030.0), 2.28),
    ("left_2", 2380.0, (465.0, 2400.0), 2.40),
    ("left_3", 2750.0, (95.0, 2770.0), 2.51),
    ("left_4", 3120.0, (465.0, 3140.0), 2.62),
    ("left_5", 3490.0, (95.0, 3510.0), 2.72),
)


def _left_branch(builder: CourseBuilder) -> None:
    """A switchback. Nothing here is trying to catch anyone out.

    Safe does not mean gentle. These shelves are steeper than anything on
    the prototype, and a racer covers the corridor six times over on the way
    down - what makes this the safe branch is that there is nothing on it.
    No rotor, no pass, no gap to miss: a racer that enters it will leave it,
    in about the same time as the racer in front, whatever else is going on
    in the race.

    The gaps at the open ends are 110 pixels against a 60 pixel racer, wide
    enough that two arriving together cannot bridge one, and grippy track
    the whole way so the pack rolls rather than skates. It is the control
    the right-hand side is measured against, and it is meant to be
    unremarkable.
    """
    builder.section = "branch_left"
    _branch_checkpoint(builder, "left_entry", ENTRY_Y, (330.0, 1660.0), ENTRY_PROGRESS)

    for start, end in LEFT_SHELVES:
        builder.ramp(start, end, SURFACE, TRACK)
    for name, y, respawn, progress in LEFT_RUNGS:
        _branch_checkpoint(builder, name, y, respawn, progress)

    _branch_checkpoint(builder, "left_exit", EXIT_Y, (300.0, 3940.0), EXIT_PROGRESS)


def _branch_checkpoint(
    builder: CourseBuilder,
    name: str,
    y: float,
    respawn: tuple[float, float],
    progress: float,
) -> None:
    """One rung on whichever branch is currently being laid down.

    The corridor comes from the divider rather than from the caller, so a
    branch plane can never be given a corridor that disagrees with the wall
    that makes the branch a branch.
    """
    left = builder.section == "branch_left"
    builder.branch_checkpoint(
        name,
        y,
        respawn,
        branch=BRANCH_LEFT if left else BRANCH_RIGHT,
        x_range=(None, DIVIDER_X) if left else (DIVIDER_X, None),
        progress=progress,
    )


# --- the right branch: short, slick, and expensive when it goes wrong --------

RIGHT_SPINNER = (800.0, 2480.0)
# Reach is set by the corridor, not by how big a spinner would look good.
# The tips have to clear both walls by more than a racer's diameter, or the
# gap beside the spinner stops being a gap and becomes a trap: a racer
# driven into it is batted against the wall by every passing arm instead of
# falling through. The corridor is 480 wide, so 168 of reach leaves 72 on
# each side against a 60 pixel racer.
RIGHT_SPINNER_HUB = 40.0
RIGHT_SPINNER_ARM = 128.0

# The pass: a floor across the corridor with one hole in it, directly above
# the rotor. Its clear width is set by the arching threshold, exactly as the
# prototype's funnel throat is - two racer diameters plus a margin, so two
# racers cannot bridge it and lock the floor solid.
PASS_Y = 2260.0
PASS_LEFT = 720.0
PASS_RIGHT = 880.0

# Slick chutes at about thirty-two degrees against the left's shelves at
# twenty-three. Every open end leaves at least a hundred pixels: an earlier
# version left exactly sixty - one racer wide - and the whole field wedged
# in it, in every seed.
RIGHT_RAMPS = (
    ((RIGHT_FACE, 1720.0), (900.0, 1960.0)),
    ((PLAYABLE_RIGHT, 2700.0), (660.0, 2940.0)),
    ((RIGHT_FACE, 3140.0), (900.0, 3380.0)),
    ((PLAYABLE_RIGHT, 3560.0), (660.0, 3800.0)),
)


def _right_branch(builder: CourseBuilder, rng: random.Random) -> None:
    """A steep slick run through one pass with a rotor turning under it.

    The pass is the whole reason to take this side and the whole reason not
    to. A floor crosses the corridor with a single hole in it and the rotor
    turns directly beneath, so every racer on this branch goes through the
    same gap and meets an arm on the way out - it is not a hazard that can
    be avoided by taking a good line, which is what the first version of
    this branch had and why it never cost anybody anything.

    What comes out of the pass is genuinely uncertain. An arm arriving at
    the wrong moment does not nudge a racer, it relocates one, and the
    chutes below are slick and steep - exactly the surface on which a racer
    that has lost its line cannot get it back. Cleared cleanly this is much
    the fastest way to the rejoin; caught, the left-hand switchback would
    have been quicker.

    Four rungs against the left's seven, because there is genuinely less to
    this path. The values are not a judgement about which route is better -
    they only say how far through the split a racer has got, and both paths
    are worth the same interval.
    """
    builder.section = "branch_right"
    _branch_checkpoint(builder, "right_entry", ENTRY_Y, (700.0, 1660.0), ENTRY_PROGRESS)

    first, second, third, fourth = RIGHT_RAMPS
    builder.ramp(first[0], first[1], SURFACE, SLICK)

    # The floor either side of the hole, sloping in, so a racer that lands
    # away from the gap is fed towards it rather than left sitting there.
    builder.ramp((RIGHT_FACE, 2180.0), (PASS_LEFT, PASS_Y), SURFACE, TRACK)
    builder.ramp((PLAYABLE_RIGHT, 2180.0), (PASS_RIGHT, PASS_Y), SURFACE, TRACK)

    builder.spinner(
        x=RIGHT_SPINNER[0],
        y=RIGHT_SPINNER[1],
        hub_radius=RIGHT_SPINNER_HUB,
        arm_count=3,
        arm_length=RIGHT_SPINNER_ARM,
        arm_thickness=28.0,
        angular_speed=_spinner_speed(rng, 250.0),
        start_angle=rng.uniform(0.0, 360.0),
    )
    _branch_checkpoint(builder, "right_1", 2620.0, (1000.0, 2620.0), 2.42)

    builder.ramp(second[0], second[1], SURFACE, SLICK)
    builder.ramp(third[0], third[1], SURFACE, SLICK)
    _branch_checkpoint(builder, "right_2", 3460.0, (620.0, 3480.0), 2.70)

    builder.ramp(fourth[0], fourth[1], SURFACE, SLICK)
    _branch_checkpoint(builder, "right_exit", EXIT_Y, (800.0, 3940.0), EXIT_PROGRESS)


def _spinner_speed(rng: random.Random, nominal: float) -> float:
    return nominal * (1.0 + rng.uniform(-SPINNER_SPEED_JITTER, SPINNER_SPEED_JITTER))


# --- rejoin -----------------------------------------------------------------

REJOIN_Y = 4420.0


def _rejoin(builder: CourseBuilder) -> None:
    """A wide merge rather than a funnel.

    The temptation here is a throat, because gathering two streams into one
    is what the prototype's funnel does so well. It is the wrong obstacle in
    this position: the two branches deliver racers at different times, and a
    queue at the merge would hold the quick ones up for the slow ones and
    erase the difference the split just created. The opening is 280 pixels -
    four racers abreast go through together - and the shape only exists to
    bring both sides back onto the centre line before the last obstacle.
    """
    builder.begin_section("rejoin", DIVIDER_BOTTOM)
    builder.ramp((PLAYABLE_LEFT, 4220.0), (400.0, 4340.0), SURFACE, TRACK)
    builder.ramp((PLAYABLE_RIGHT, 4220.0), (680.0, 4340.0), SURFACE, TRACK)
    builder.checkpoint("rejoin", REJOIN_Y, (540.0, 4460.0))


# --- the final obstacle -----------------------------------------------------

PLINKO_ROWS = (
    (4560.0, (240.0, 420.0, 600.0, 780.0)),
    (4670.0, (150.0, 330.0, 510.0, 690.0, 870.0)),
    (4780.0, (240.0, 420.0, 600.0, 780.0)),
    (4890.0, (150.0, 330.0, 510.0, 690.0, 870.0)),
)
SCATTER_ROWS = (
    (5480.0, (240.0, 420.0, 600.0, 780.0)),
    (5590.0, (150.0, 330.0, 510.0, 690.0, 870.0)),
)
PEG_RADIUS = 30.0
FINAL_EXIT_Y = 6180.0


def _final(builder: CourseBuilder, rng: random.Random) -> None:
    """Plinko, a rotor, a second scatter, and a second rotor.

    The same closing idea the prototype ends on, run twice. By this point
    the order is usually close, and a wide sweep is where a race stops being
    decided and starts being watched - and it matters more here than on the
    prototype, because the two branches have just merged and the field
    arrives in clumps rather than as a line. A rotor across a clump changes
    more places than one across a queue.

    Two of them rather than one because this section is also where the
    course gets its length. The branches are tuned against each other and
    cannot be stretched without upsetting that; the run-in after the merge
    can be as long as the race needs, and nothing in it can decide the
    result unfairly - both sides of the split have already merged into it.
    """
    builder.begin_section("final", REJOIN_Y)
    for row_y, columns in PLINKO_ROWS:
        for column_x in columns:
            builder.peg(column_x, row_y, PEG_RADIUS, BOUNCY)
    builder.spinner(
        x=540.0,
        y=5180.0,
        hub_radius=44.0,
        arm_count=2,
        arm_length=190.0,
        arm_thickness=34.0,
        angular_speed=_spinner_speed(rng, 230.0),
        start_angle=rng.uniform(0.0, 360.0),
    )
    for row_y, columns in SCATTER_ROWS:
        for column_x in columns:
            builder.peg(column_x, row_y, PEG_RADIUS, BOUNCY)
    builder.spinner(
        x=540.0,
        y=5900.0,
        hub_radius=44.0,
        arm_count=3,
        arm_length=175.0,
        arm_thickness=30.0,
        angular_speed=_spinner_speed(rng, -200.0),
        start_angle=rng.uniform(0.0, 360.0),
    )
    builder.checkpoint("final_exit", FINAL_EXIT_Y, (150.0, 6220.0))


# --- finish -----------------------------------------------------------------

FINISH_Y = 6540.0


def _finish(builder: CourseBuilder) -> None:
    """A wide chute into a sloped paddock. The finish is not an obstacle.

    Finished racers stay in the world, so the paddock has to hold ten of
    them without the pile reaching back up through the finish plane and
    leaving the last arrivals unable to cross it. Hence the slope: arrivals
    roll away towards the right-hand wall and line up along the floor.
    """
    builder.begin_section("finish", FINAL_EXIT_Y)
    builder.ramp((PLAYABLE_LEFT, 6360.0), (430.0, 6460.0), SURFACE, TRACK)
    builder.ramp((PLAYABLE_RIGHT, 6360.0), (650.0, 6460.0), SURFACE, TRACK)
    builder.checkpoint("finish", FINISH_Y, (540.0, 6580.0))
    builder.ramp((PLAYABLE_LEFT, 6660.0), (PLAYABLE_RIGHT, 6740.0), SURFACE, TRACK)

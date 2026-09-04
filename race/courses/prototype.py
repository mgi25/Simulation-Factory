"""The V0.1 prototype course.

One course, laid out top to bottom, with every section written as the shape
a viewer sees. The running theme is that nothing here decides an outcome:
the geometry decides where racers *can* go and how much room they have to
do it in, and the physics decides the rest.

    START            ten racers behind a gate
    ACCELERATION     two steep shelves - the field spreads and queues
    SPINNERS         an open shaft with two rotors batting racers sideways
    FUNNEL           full-width mouth narrowing to a single-file throat
    SCATTER          a peg triangle breaking up the single file
    JUMP             ramp, kicker, and a gap that punishes a slow approach
    CHAOS            plinko pegs and a long final rotor
    FINISH           a wide chute, so the last obstacle is not the exit

Slope is the tuning dial that matters most, and it is not obvious why: a
shallow surface does not make a race gentler, it makes it *empty*. An early
version of this course spent more than half of the winner's time on two
eight-degree shelves and one long flat catch ramp, with the field creeping
along in a line and nothing happening. Every travelling surface here is
therefore steep enough to be over quickly, and the time that buys is spent
on the funnel and the jump instead - the two places where the order
actually changes.
"""

from __future__ import annotations

import random

from engine.arena import CANVAS_WIDTH
from race.course import BOUNCY, SLICK, TRACK, RaceCourse
from race.courses.builder import CourseBuilder
from race.seeds import make_course_rng

__all__ = ["PROTOTYPE_COURSE_ID", "build_prototype_course"]

PROTOTYPE_COURSE_ID = "prototype"

COURSE_TOP = 0.0
COURSE_BOTTOM = 6380.0

# Boundary. The side walls are centred on the canvas edges, so their inner
# surfaces sit at `WALL_INSET` and `width - WALL_INSET` and the playable
# width is what a racer actually has.
WALL_THICKNESS = 80.0
WALL_INSET = WALL_THICKNESS / 2.0
PLAYABLE_LEFT = WALL_INSET
PLAYABLE_RIGHT = CANVAS_WIDTH - WALL_INSET

SURFACE = 26.0  # thickness of an ordinary ramp or shelf

# Grid: two rows of five. The row gap is what needs care, not the column
# gap: two racers in the same column can each be nudged towards the other,
# so the rows have to be more than a racer's diameter plus twice the y
# jitter apart. At 90px they were two pixels clear of touching on the grid.
GRID_COLUMNS = (160.0, 350.0, 540.0, 730.0, 920.0)
GRID_ROWS = (500.0, 610.0)

# Spinners: the sign of each speed is a design decision, its exact value is
# not. A few per cent of seeded variation keeps two runs of the same course
# from falling into identical arm timing without making a rotor unreadable.
SPINNER_SPEED_JITTER = 0.08


def build_prototype_course(seed: int) -> RaceCourse:
    """Build the prototype course for a seed.

    Only the spinners vary with the seed - their start angle freely, their
    speed slightly. The geometry is fixed, because a prototype has to be the
    same course every time for its results to mean anything.
    """
    rng = make_course_rng(seed)
    builder = CourseBuilder(PROTOTYPE_COURSE_ID, CANVAS_WIDTH, COURSE_TOP)

    _boundary(builder)
    _start(builder)
    _acceleration(builder)
    _spinners(builder, rng)
    _funnel(builder)
    _scatter(builder)
    _jump(builder)
    _chaos(builder, rng)
    _finish(builder)

    return builder.finish(
        COURSE_BOTTOM,
        drop=COURSE_BOTTOM - COURSE_TOP,
        playable_width=PLAYABLE_RIGHT - PLAYABLE_LEFT,
        funnel_throat=THROAT_RIGHT - THROAT_LEFT - SURFACE,
    )


# --- boundary ---------------------------------------------------------------


def _boundary(builder: CourseBuilder) -> None:
    """Two side walls, a ceiling and a floor: the course cannot be left.

    Out-of-bounds recovery still exists, but as a net under a physics
    failure rather than as the thing that keeps racers on the track.

    Not given a section of its own: the boundary spans every section, and a
    zero-height entry in the section list would only confuse the camera and
    the debug overlay that read it.
    """
    builder.section = "boundary"
    builder.wall((0.0, COURSE_TOP), (0.0, COURSE_BOTTOM), WALL_THICKNESS)
    builder.wall(
        (CANVAS_WIDTH, COURSE_TOP), (CANVAS_WIDTH, COURSE_BOTTOM), WALL_THICKNESS
    )
    builder.wall((0.0, COURSE_TOP), (CANVAS_WIDTH, COURSE_TOP), WALL_THICKNESS)
    builder.wall((0.0, COURSE_BOTTOM), (CANVAS_WIDTH, COURSE_BOTTOM), WALL_THICKNESS)


# --- start ------------------------------------------------------------------

GATE_Y = 700.0


def _start(builder: CourseBuilder) -> None:
    builder.begin_section("start", COURSE_TOP)
    builder.gate((PLAYABLE_LEFT, GATE_Y), (PLAYABLE_RIGHT, GATE_Y), SURFACE)
    for row_y in GRID_ROWS:
        for column_x in GRID_COLUMNS:
            builder.spawn(column_x, row_y)
    builder.checkpoint("start", GATE_Y, (540.0, 760.0))


# --- acceleration -----------------------------------------------------------


def _acceleration(builder: CourseBuilder) -> None:
    """Two shelves, each open at the opposite end.

    A racer rolls the length of a shelf and drops off its open end, so the
    field is sorted by where on the shelf it landed rather than by where it
    started - and the whole pack has to queue through the same two drops.
    Both are steep and slick: this section exists to get the field moving
    and mixed, not to be watched.
    """
    builder.begin_section("acceleration", GATE_Y)
    builder.ramp((PLAYABLE_LEFT, 800.0), (820.0, 1060.0), SURFACE, SLICK)
    builder.ramp((PLAYABLE_RIGHT, 1140.0), (260.0, 1400.0), SURFACE, SLICK)
    builder.checkpoint("accel_exit", 1460.0, (150.0, 1500.0))


# --- spinners ---------------------------------------------------------------


def _spinners(builder: CourseBuilder, rng: random.Random) -> None:
    """An open shaft crossed by two rotors at different heights.

    Two placement rules, both learned the hard way, decide where a rotor can
    go. Their hubs must be further apart than the sum of their reaches, or
    the arms intersect - two kinematic bodies pass through each other rather
    than collide, and it reads as a bug. And every arm tip must clear the
    side wall by more than a racer's diameter: a gap narrower than that is
    not a gap, it is a trap, and a racer driven into it gets batted against
    the wall by every passing arm instead of falling through. An earlier
    layout left twenty pixels there and lost a racer to it in one seed in
    fifteen.

    Between them the two sweeps still cover most of the playable width, so a
    racer has to be well out towards one edge to fall the shaft untouched.

    The shaft empties straight into the funnel mouth. There is no catch ramp
    between them because there is nothing for one to do: the mouth already
    spans the full width, so a ramp would only add a flat stretch for the
    field to crawl along.
    """
    builder.begin_section("spinners", 1460.0)
    builder.spinner(
        x=380.0,
        y=1720.0,
        hub_radius=50.0,
        arm_count=3,
        arm_length=220.0,
        arm_thickness=30.0,
        angular_speed=_spinner_speed(rng, 150.0),
        start_angle=rng.uniform(0.0, 360.0),
    )
    builder.spinner(
        x=700.0,
        y=2180.0,
        hub_radius=46.0,
        arm_count=4,
        arm_length=200.0,
        arm_thickness=28.0,
        angular_speed=_spinner_speed(rng, -190.0),
        start_angle=rng.uniform(0.0, 360.0),
    )
    # Pushes anything that fell down the left-hand side back across into the
    # second rotor's reach instead of letting it drop the shaft untouched.
    builder.ramp((PLAYABLE_LEFT, 2130.0), (430.0, 2230.0), SURFACE, TRACK)
    builder.checkpoint("spinner_exit", 2340.0, (200.0, 2380.0))


def _spinner_speed(rng: random.Random, nominal: float) -> float:
    return nominal * (1.0 + rng.uniform(-SPINNER_SPEED_JITTER, SPINNER_SPEED_JITTER))


# --- funnel -----------------------------------------------------------------

FUNNEL_TOP = 2400.0
FUNNEL_RIM_Y = 2920.0
FUNNEL_RIM_LEFT = 200.0
FUNNEL_RIM_RIGHT = CANVAS_WIDTH - FUNNEL_RIM_LEFT
FUNNEL_FLOOR_Y = 3060.0
# The hole. Its clear width - 126px against a 60px racer - is set by the
# arching threshold, not by how tight a queue is wanted: at 100px, two
# racers reliably wedge across the gap, each resting on one lip and on the
# other racer, and the basin locks solid with the whole field in it. Two
# diameters plus a margin cannot be bridged that way, and measuring across
# forty seeds showed congestion is unchanged by the difference - the queue
# comes from the friction of the approach, not from the pinch.
THROAT_LEFT = 464.0
THROAT_RIGHT = 616.0
THROAT_BOTTOM = 3220.0
SPLITTER_Y = 2700.0
SPLITTER_RADIUS = 36.0


def _funnel(builder: CourseBuilder) -> None:
    """Steep sides feeding a shallow floor that drains through one hole.

    This is the obstacle the whole course is built around, and the shape it
    ended up with is not the obvious one. A V-funnel narrowing to a vertical
    throat - the first thing tried here - does not congest at all: the walls
    keep the field at full speed and racers shoot the gap one after another
    in about a second, ten of them, nose to tail, no contest.

    What congests is a *floor*. The sides drop steeply into a shallow basin
    whose only exit is a hole in the middle of it, so a racer arrives fast,
    loses almost all of that speed at the break in slope, and then has to
    roll the last stretch to the hole on ordinary track friction. The hole
    is wider than one racer and narrower than two, so it drains in single
    file while the basin keeps filling - and a queue in a basin is not a
    queue in a pipe: racers jostle sideways, climb each other, and reach the
    hole in an order the arrival order does not predict.

    What stops the queue becoming a lock-up is the width of the hole, and
    only that. The floor sloping in from both sides is not enough on its
    own: with a hole narrower than two racers, two of them will eventually
    wedge across it - one on each lip, propped against each other - and the
    basin fills and stops with the whole field in it. That is ordinary
    hopper arching and it is not rare, so the hole is sized above the
    threshold instead of being made narrow and watched. Stuck recovery
    remains the net under this, but it is not the plan.

    The peg well above the hole splits the racers that come down the middle
    towards one side or the other, which is where most of the overtaking in
    a race actually happens.
    """
    builder.begin_section("funnel", 2340.0)
    builder.checkpoint("funnel_entry", 2460.0, (540.0, 2500.0))

    for edge_x, rim_x, throat_x in (
        (PLAYABLE_LEFT, FUNNEL_RIM_LEFT, THROAT_LEFT),
        (PLAYABLE_RIGHT, FUNNEL_RIM_RIGHT, THROAT_RIGHT),
    ):
        # Steep and slick: this stretch gathers the field, it does not hold it.
        builder.ramp((edge_x, FUNNEL_TOP), (rim_x, FUNNEL_RIM_Y), SURFACE, SLICK)
        # The basin floor, on ordinary track friction. The queue forms here.
        builder.ramp(
            (rim_x, FUNNEL_RIM_Y), (throat_x, FUNNEL_FLOOR_Y), SURFACE, TRACK
        )
        # A short throat below the hole, so racers leave in a line rather
        # than fanning out into the section below.
        builder.ramp(
            (throat_x, FUNNEL_FLOOR_Y), (throat_x, THROAT_BOTTOM), SURFACE, SLICK
        )

    builder.peg(540.0, SPLITTER_Y, SPLITTER_RADIUS, BOUNCY)
    builder.checkpoint("funnel_exit", 3300.0, (540.0, 3340.0))


# --- scatter ----------------------------------------------------------------


def _scatter(builder: CourseBuilder) -> None:
    """Breaks the single file coming out of the throat back into a spread."""
    builder.begin_section("scatter", 3360.0)
    for x, y in (
        (540.0, 3500.0),
        (420.0, 3590.0),
        (660.0, 3590.0),
        (300.0, 3680.0),
        (540.0, 3680.0),
        (780.0, 3680.0),
    ):
        builder.peg(x, y, 32.0, BOUNCY)
    # Gathers the spread onto one shelf and drops it off the left-hand end,
    # lined up for the jump run-up.
    builder.ramp((PLAYABLE_RIGHT, 3760.0), (200.0, 3980.0), SURFACE, TRACK)
    builder.checkpoint("jump_entry", 4040.0, (110.0, 4080.0))


# --- jump -------------------------------------------------------------------

RUN_UP_START = (PLAYABLE_LEFT, 4160.0)
PAD_START = (400.0, 4360.0)
PAD_END = (500.0, 4340.0)
# Straight up would drop a racer back on the pad; this is enough forward
# lean to carry it off the lip while still buying real air time.
PAD_ANGLE = 18.0
PAD_IMPULSE = 300.0
PAD_JITTER = 0.06

PLATFORM_START = (740.0, 4480.0)
PLATFORM_END = (930.0, 4570.0)


def _jump(builder: CourseBuilder) -> None:
    """A slick run-up, a kicker, and three ways for the jump to end.

    How far a racer flies is set by the speed it brought to the pad, and
    nothing else. Clear the platform entirely and it drops straight down the
    gap on the right, the fastest line available. Land on the platform and
    it rolls to that same gap, a little behind. Come in slow - held up in
    traffic on the run-up, or nudged off line - and it falls short into the
    pit, which feeds the long way round.

    No branch is scripted and none is closed off. The pit costs distance
    rather than removing a racer from the race: both branches drop into the
    same basin and leave through the same exit, so a bad jump is a deficit
    to make up rather than an elimination.
    """
    builder.begin_section("jump", 4040.0)
    builder.ramp(RUN_UP_START, PAD_START, SURFACE, SLICK)
    builder.jump_pad(
        PAD_START, PAD_END, SURFACE, PAD_ANGLE, PAD_IMPULSE, PAD_JITTER, SLICK
    )
    builder.ramp(PLATFORM_START, PLATFORM_END, SURFACE, TRACK)
    builder.checkpoint("jump_landing", 4620.0, (540.0, 4640.0))

    # The pit: a long, shallow slide back to the left, which is the whole
    # cost of a short jump.
    builder.ramp((700.0, 4680.0), (200.0, 4800.0), SURFACE, TRACK)

    builder.ramp((PLAYABLE_LEFT, 4900.0), (470.0, 5010.0), SURFACE, TRACK)
    builder.ramp((PLAYABLE_RIGHT, 4900.0), (610.0, 5010.0), SURFACE, TRACK)
    builder.checkpoint("basin_exit", 5070.0, (540.0, 5110.0))


# --- chaos ------------------------------------------------------------------

PLINKO_ROWS = (
    (5180.0, (250.0, 400.0, 550.0, 700.0, 850.0)),
    (5290.0, (175.0, 325.0, 475.0, 625.0, 775.0, 925.0)),
    (5400.0, (250.0, 400.0, 550.0, 700.0, 850.0)),
)
PLINKO_RADIUS = 30.0


def _chaos(builder: CourseBuilder, rng: random.Random) -> None:
    """Plinko, then one long rotor with the whole field arriving at once.

    Placed last on purpose. By this point the order is usually close, so a
    single wide sweep at the end is where a race stops being decided and
    starts being watched.
    """
    builder.begin_section("chaos", 5070.0)
    for row_y, columns in PLINKO_ROWS:
        for column_x in columns:
            builder.peg(column_x, row_y, PLINKO_RADIUS, BOUNCY)
    builder.spinner(
        x=540.0,
        y=5700.0,
        hub_radius=44.0,
        arm_count=2,
        arm_length=196.0,
        arm_thickness=34.0,
        angular_speed=_spinner_speed(rng, 230.0),
        start_angle=rng.uniform(0.0, 360.0),
    )
    builder.checkpoint("chaos_exit", 5780.0, (150.0, 5820.0))


# --- finish -----------------------------------------------------------------

FINISH_Y = 6180.0


def _finish(builder: CourseBuilder) -> None:
    """A wide chute into a sloped paddock. The finish is not an obstacle.

    Finished racers stay in the world - a winner that vanishes on crossing
    the line is no use to a Shorts edit - so the paddock has to be somewhere
    ten of them can sit without the pile reaching back up through the finish
    plane and leaving the last arrivals unable to cross it. Hence the slope:
    arrivals roll away towards the right-hand wall and line up along the
    floor instead of stacking under the chute.
    """
    builder.begin_section("finish", 5780.0)
    builder.ramp((PLAYABLE_LEFT, 5980.0), (430.0, 6080.0), SURFACE, TRACK)
    builder.ramp((PLAYABLE_RIGHT, 5980.0), (650.0, 6080.0), SURFACE, TRACK)
    builder.checkpoint("finish", FINISH_Y, (540.0, 6220.0))
    builder.ramp((PLAYABLE_LEFT, 6280.0), (PLAYABLE_RIGHT, 6360.0), SURFACE, TRACK)

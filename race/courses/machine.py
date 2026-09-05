"""The V0.4 machine course: built to keep the result in doubt.

The prototype is a good race that answers itself too early. Its shape is a
ladder of obstacles that each preserve order - a shelf translates the field,
a rotor deflects it, a jump rewards the speed a racer already had - with one
genuine mixer in it, the funnel, a third of the way down. Everything after
the funnel compounds whatever the funnel produced. Measured over 2 500
seeds, the field is seven racers deep at the quarter mark and four by
halfway, and it never recovers.

So this course is built around a different rule: **no advantage may survive
more than one obstacle unchallenged.** Every stretch of travel is followed
by something that either mixes the order or closes the gaps, and the last
of those sits at four fifths of the way down, so the race is still being
decided when the finish is already on screen.

    START       a staggered grid, four rows deep and five wide
    SPREAD      three peg rows across the full width - nobody funnels first
    BOWL        two counter-rotors, then a basin draining through two holes
    RAPIDS      two steep slick shelves; the one place order is preserved
    LANES       a divider down the middle: switchback left, rotor right
    CAROUSEL    a rotating tray that plugs the only hole, then two rotors
    PLUNGE      a kicker over a gap, with a pit for anyone who comes in slow
    SLUICE      two counter-phased trays: the last compression of the race
    RUN-IN      plinko into the finish chute
    FINISH      a wide chute into a sloped paddock

Classified the way `docs/race_v04.md` asks for:

    spread      SPREAD
    bowl        MIX + COMPRESS
    rapids      SPRINT
    lanes       CHOICE + RISK
    carousel    COMPRESS + MIX
    plunge      RISK
    sluice      COMPRESS + MIX
    run-in      CHAOS + SPRINT

Two of those categories are new to this project and both are worth reading
about before the geometry below makes sense.

**A tray gate** is a rotor whose hub sits exactly in the plane of a shelf,
with arms just long enough to reach the lips of the hole in it. Turned
broadside the arms *are* the missing piece of floor and the hole is shut;
turned edge-on the hole is open either side of the hub. Racers pile up on a
closed gate and pour through together when it opens, which is a physical
compression - nothing is teleported, nothing is queued by rule, and a racer
that arrives two seconds ahead of the pack simply waits with it. The hub is
in the shelf plane rather than below it on purpose: a rotor slung under the
floor makes a pocket between arm and shelf that a racer can be crushed in,
and one at floor level cannot, because there is no gap to be caught in.

**Two drains** rather than one is what turns a funnel from a queue into a
mixer. A single hole drains in arrival order most of the time - the racer
at the front of the queue is at the front of the queue. Two holes with an
island between them means the racer that reached the basin first is
committed to one of them, and whether that was the right one depends on how
many racers are already leaning on it. First into the bowl is emphatically
not first out, which is exactly what the prototype's funnel could not
promise.

Nothing here chooses a winner, reorders a field or moves a racer. Every
mechanism above is geometry plus a constant angular velocity, and the
result is whatever the solver makes of them.
"""

from __future__ import annotations

import random

from engine.arena import CANVAS_WIDTH
from race.course import BOUNCY, SLICK, TRACK, RaceCourse
from race.courses.builder import CourseBuilder, curve_points
from race.seeds import make_course_rng

__all__ = ["MACHINE_COURSE_ID", "build_machine_course", "SECTION_ROLES"]

MACHINE_COURSE_ID = "machine"

COURSE_TOP = 0.0
COURSE_BOTTOM = 6840.0

# What each named stretch is *for*. Not read by the simulation - it exists so
# the course can be audited against the design rule at the top of this file,
# and so a test can assert that the course has not quietly become a corridor
# of sprints again.
SECTION_ROLES: dict[str, tuple[str, ...]] = {
    "start": (),
    "spread": ("SPREAD",),
    "bowl": ("MIX", "COMPRESS"),
    "rapids": ("SPRINT",),
    "lanes": ("CHOICE", "RISK"),
    "carousel": ("COMPRESS", "MIX"),
    "plunge": ("RISK",),
    "sluice": ("COMPRESS", "MIX"),
    "runin": ("CHAOS", "SPRINT"),
    "finish": (),
}

# Boundary, as every course in this project builds it: side walls centred on
# the canvas edges, so the playable width is what a racer actually has.
WALL_THICKNESS = 80.0
WALL_INSET = WALL_THICKNESS / 2.0
PLAYABLE_LEFT = WALL_INSET
PLAYABLE_RIGHT = CANVAS_WIDTH - WALL_INSET
MID_X = CANVAS_WIDTH / 2.0

SURFACE = 26.0        # thickness of an ordinary ramp or shelf
HALF_SURFACE = SURFACE / 2.0

SPINNER_SPEED_JITTER = 0.08


def build_machine_course(seed: int) -> RaceCourse:
    """Build the machine course for a seed.

    As with every course here, only the rotors vary with the seed - their
    start angle freely, their speed slightly. Geometry that moved between
    seeds could not be measured, and this course exists to be measured.
    """
    rng = make_course_rng(seed)
    builder = CourseBuilder(MACHINE_COURSE_ID, CANVAS_WIDTH, COURSE_TOP)

    _boundary(builder)
    _start(builder)
    _spread(builder)
    _bowl(builder, rng)
    _rapids(builder)
    _lanes(builder, rng)
    _carousel(builder, rng)
    _plunge(builder)
    _sluice(builder, rng)
    _runin(builder, rng)
    _finish(builder)

    return builder.finish(
        COURSE_BOTTOM,
        drop=COURSE_BOTTOM - COURSE_TOP,
        playable_width=PLAYABLE_RIGHT - PLAYABLE_LEFT,
        drains=2.0,
        tray_gates=3.0,
        spawn_slots=float(len(GRID_COLUMNS) * len(GRID_ROWS)),
    )


# --- boundary ---------------------------------------------------------------


def _boundary(builder: CourseBuilder) -> None:
    builder.section = "boundary"
    builder.wall((0.0, COURSE_TOP), (0.0, COURSE_BOTTOM), WALL_THICKNESS)
    builder.wall(
        (CANVAS_WIDTH, COURSE_TOP), (CANVAS_WIDTH, COURSE_BOTTOM), WALL_THICKNESS
    )
    builder.wall((0.0, COURSE_TOP), (CANVAS_WIDTH, COURSE_TOP), WALL_THICKNESS)
    builder.wall((0.0, COURSE_BOTTOM), (CANVAS_WIDTH, COURSE_BOTTOM), WALL_THICKNESS)


# --- start ------------------------------------------------------------------

GATE_Y = 700.0
GRID_COLUMNS = (255.0, 445.0, 635.0, 825.0)
GRID_ROWS = (260.0, 350.0, 440.0, 530.0, 620.0)


def _start(builder: CourseBuilder) -> None:
    """Twenty slots, five deep and four wide, emitted along a diagonal.

    Two things decide this shape and neither is aesthetic.

    **Four columns, not five.** A racer in free fall has no sideways
    velocity, so wherever a starting column's fall line first meets a round
    surface, that is somewhere a racer can come to rest exactly on top of.
    With five columns the middle one sits on the centre line, and the centre
    line is where every symmetric course puts its splitter pegs - the fall
    line ran straight down the middle of the peg field and onto the apex of
    the bowl's island. Four columns are offset half a pitch from the centre,
    so no fall line on this course meets an apex at all: it is checked by
    `race.audit`, and it is why the grid is the shape it is.

    **A diagonal order.** The field size is not fixed - 10, 16 and 20 racers
    were all measured - and `build_grid` fills slots in the order a course
    hands them out. Row by row that would put a ten-racer field entirely in
    the top two rows, which is a different starting shape for every count.
    Slot *k* is row `k % 5` with the column advancing each time the rows
    wrap, so the pattern visits every cell exactly once and any prefix stays
    spread over the whole grid.

    Whether the grid is *fair* is a separate question from whether it is
    even, and this is not what the course relies on for it: the answer to
    that is `_spread`.
    """
    builder.begin_section("start", COURSE_TOP)
    builder.gate((PLAYABLE_LEFT, GATE_Y), (PLAYABLE_RIGHT, GATE_Y), SURFACE)

    rows = len(GRID_ROWS)
    columns = len(GRID_COLUMNS)
    for slot in range(rows * columns):
        row = slot % rows
        column = (slot // rows + row) % columns
        builder.spawn(GRID_COLUMNS[column], GRID_ROWS[row])

    # Off the centre line, because the centre line is where the first peg
    # row puts a peg. A rescue that drops a racer onto an apex is how the
    # first version of this course retired a whole field.
    builder.checkpoint("start", GATE_Y, (445.0, 760.0))


# --- spread -----------------------------------------------------------------

# The peg lattice sits on the *midpoints between* the starting columns, and
# that is the only placement this section is allowed to have. A racer in free
# fall has no sideways velocity, so a peg apex under a starting column is a
# place it can land exactly on top of and stay - and the first version of
# this course lost two racers a race to precisely that, then retired them,
# because the recovery point was on the same line and dropped them back onto
# the same peg. Ninety-five pixels off the fall line, against a 24px spread
# of spawn jitter, there is no landing that is not a glancing one.
#
# The pitch is the grid pitch, so the pattern is symmetric about the centre
# line, every column of the grid meets the same shape, and the centre line
# itself carries a peg rather than a channel.
SPREAD_LATTICE = tuple(160.0 + 190.0 * step for step in range(5))
SPREAD_ROWS = (810.0, 930.0, 1050.0)
# Sized by the arching threshold, not by how much of the channel is left: at
# a 190px pitch this leaves 126px clear, which is two racer diameters plus a
# margin and therefore the width two racers cannot bridge. An earlier version
# used 46px pegs for a tighter 98px channel and the field wedged in it - a peg
# field arches exactly like a hopper does, and being round does not save it.
SPREAD_PEG_RADIUS = 32.0
SPREAD_EXIT_Y = 1180.0


def _spread(builder: CourseBuilder) -> None:
    """Three peg rows across the full width, and nothing else.

    The V0.3 opening was two slick shelves, and shelves are why the starting
    slot decided the race. A shelf running from the left wall to x=820 leaves
    everything past its right-hand end falling straight down: over 2 500
    seeds the outside column won 25% of races and the inside column 2.3%, an
    eleven-fold spread on a field where ten percent is neutral.

    Pegs have no end to fall past. The field leaves the grid across nine
    hundred pixels and is still spread across them three rows later, and no
    column has anywhere to be first to.
    """
    builder.begin_section("spread", GATE_Y)
    for row_y in SPREAD_ROWS:
        for column_x in SPREAD_LATTICE:
            builder.peg(column_x, row_y, SPREAD_PEG_RADIUS, BOUNCY)
    builder.checkpoint("spread_exit", SPREAD_EXIT_Y, (MID_X, 1205.0))


# --- bowl -------------------------------------------------------------------

# The intake rotors: a counter-rotating pair at the same height, mirrored
# about the centre line. Between them they cover x 165 to 915 - every starting
# column - which is the other half of the answer to a racer falling all the
# way down a peg channel untouched: it reaches the bowl with sideways velocity
# like everything else.
#
# Two things about this arrangement were bought with measurements.
#
# One rotor on the centre line would have been simpler and wrong: it pushes
# every racer the same way round, and the drain on that side is then worth
# more than the other one for the whole life of the course.
#
# The pair also has to be *level*. The first version staggered them - 350 at
# y=1330 and 730 at y=1470 - so their sweeps could overlap in x without the
# arms being able to reach each other. It cost fairness: over 1 200 races the
# leftmost starting column won 4.3% of them against about 7% for the other
# three, because the column nearest the higher rotor met it sooner, slower and
# harder. Level, with the reach cut to 185 so the two circles clear each other
# at the same height, the four columns come back to within a point of each
# other. A mirror-symmetric course has to be mirror-symmetric in time as well
# as in space.
BOWL_ROTOR_HUB = 44.0
BOWL_ROTOR_ARM = 141.0        # reach 185; hubs are 380 apart, so 10px spare
BOWL_ROTOR_SPEED = 150.0
BOWL_ROTOR_Y = 1400.0
BOWL_ROTORS = ((350.0, 1.0), (730.0, -1.0))

BOWL_MOUTH_Y = 1720.0
BOWL_RIM_Y = 1960.0
BOWL_RIM_LEFT = 250.0
BOWL_RIM_RIGHT = CANVAS_WIDTH - BOWL_RIM_LEFT
BOWL_FLOOR_Y = 2040.0

# The island between the two drains, and the outer wall of each drain. Both
# clear widths are 132px against a 60px racer - two diameters plus a margin,
# which is the arching threshold the prototype's funnel established. Narrower
# and two racers wedge across the hole and the basin locks solid with the
# whole field in it.
ISLAND_HALF = 20.0
ISLAND_TOP = 2000.0
ISLAND_BOTTOM = 2180.0
ISLAND_PEG_Y = 1980.0
ISLAND_PEG_RADIUS = 52.0
DRAIN_LEFT_X = 375.0
DRAIN_RIGHT_X = CANVAS_WIDTH - DRAIN_LEFT_X
DRAIN_BOTTOM = 2180.0
BOWL_EXIT_Y = 2240.0


def _bowl(builder: CourseBuilder, rng: random.Random) -> None:
    """A basin with two holes in it, fed by a pair of counter-rotors.

    The prototype proved that what congests a field is a *floor*, not a
    narrowing: racers arrive fast, lose almost all of it at the break in
    slope, and then roll the last stretch to the hole on ordinary track
    friction while the basin keeps filling. That part is copied unchanged,
    because it works.

    What is new is the second hole. With one drain a queue empties roughly in
    the order it formed - the racer at the front of the queue is at the front
    of the queue, and the only mixing is the jostling. With two, a racer
    arriving has to commit to one side of the island, and which side is
    quicker depends entirely on how many racers are already leaning on it.

    The island is capped by a peg wider than itself, for the same reason the
    split course's divider is: a box has a flat top, and a racer resting on
    this one would be sitting between two drains with nothing to decide it.
    There is no flat top to land on.
    """
    builder.begin_section("bowl", SPREAD_EXIT_Y)

    for x, direction in BOWL_ROTORS:
        builder.spinner(
            x=x,
            y=BOWL_ROTOR_Y,
            hub_radius=BOWL_ROTOR_HUB,
            arm_count=3,
            arm_length=BOWL_ROTOR_ARM,
            arm_thickness=28.0,
            angular_speed=_spinner_speed(rng, direction * BOWL_ROTOR_SPEED),
            start_angle=rng.uniform(0.0, 360.0),
        )

    # Curved walls into the basin: a wide shallow mouth flattening to a steep
    # rim. Slick, because this stretch gathers the field rather than holding
    # it - the holding is the floor's job.
    for edge_x, rim_x in (
        (PLAYABLE_LEFT, BOWL_RIM_LEFT),
        (PLAYABLE_RIGHT, BOWL_RIM_RIGHT),
    ):
        builder.chain(
            curve_points(
                (edge_x, BOWL_MOUTH_Y), (rim_x, BOWL_RIM_Y), segments=5, bulge=2.0
            ),
            SURFACE,
            SLICK,
        )

    builder.ramp(
        (BOWL_RIM_LEFT, BOWL_RIM_Y), (DRAIN_LEFT_X, BOWL_FLOOR_Y), SURFACE, TRACK
    )
    builder.ramp(
        (BOWL_RIM_RIGHT, BOWL_RIM_Y), (DRAIN_RIGHT_X, BOWL_FLOOR_Y), SURFACE, TRACK
    )

    builder.peg(MID_X, ISLAND_PEG_Y, ISLAND_PEG_RADIUS, BOUNCY)
    builder.wall((MID_X, ISLAND_TOP), (MID_X, ISLAND_BOTTOM), ISLAND_HALF * 2.0)
    for throat_x in (DRAIN_LEFT_X, DRAIN_RIGHT_X):
        builder.ramp(
            (throat_x, BOWL_FLOOR_Y), (throat_x, DRAIN_BOTTOM), SURFACE, SLICK
        )

    builder.checkpoint("bowl_exit", BOWL_EXIT_Y, (MID_X, 2260.0))


def _spinner_speed(rng: random.Random, nominal: float) -> float:
    return nominal * (1.0 + rng.uniform(-SPINNER_SPEED_JITTER, SPINNER_SPEED_JITTER))


# --- rapids -----------------------------------------------------------------

# A roof and two catchers, mirrored about the centre line. The roof's apex
# sits directly under the bowl's island, so the racer that came down the left
# drain is thrown left and the one that came down the right drain is thrown
# right - and since the two drains are used equally, so are the two lanes
# below.
RAPIDS_ROOF_APEX = 2320.0
RAPIDS_ROOF_END = 2520.0
RAPIDS_ROOF_SPAN = 340.0
RAPIDS_CATCH_TOP = 2640.0
RAPIDS_CATCH_END = 2860.0
RAPIDS_CATCH_INNER = 120.0    # how far short of the centre line a catcher stops
RAPIDS_EXIT_Y = 2920.0


def _rapids(builder: CourseBuilder) -> None:
    """A steep slick roof, and two catchers that turn the field back inwards.

    A course made only of mixers is a lottery rather than a race, and a
    viewer needs somewhere to see that a racer is quick. This is it: four
    slick surfaces at thirty degrees, no obstacle on any of them, and the
    fastest way through is simply to arrive carrying speed.

    The shape is a roof rather than a shelf, and that is the whole lesson of
    this section. The first version used the two long alternating shelves the
    prototype opens with, and they work exactly as designed: a shelf gathers
    everything on it to its open end. Every racer left the second shelf at
    x=260 and fell into the left-hand lane - a hundred out of a hundred over
    ten seeds - so the right lane and the rotor in it were geometry nothing
    ever touched. A shelf is the wrong instrument anywhere the next section
    needs a field spread across the width.

    A roof does the opposite. It has no open end to gather at: whichever side
    of the apex a racer lands, it leaves on that side, and the catcher below
    turns it back inwards without merging the two streams. The bowl decides
    which drain a racer took; this decides nothing, and passes that decision
    on to the lanes intact.
    """
    builder.begin_section("rapids", BOWL_EXIT_Y)
    for side in (-1.0, 1.0):
        builder.ramp(
            (MID_X, RAPIDS_ROOF_APEX),
            (MID_X + side * RAPIDS_ROOF_SPAN, RAPIDS_ROOF_END),
            SURFACE,
            SLICK,
        )
        builder.ramp(
            (MID_X + side * (CANVAS_WIDTH * 0.5 - WALL_INSET), RAPIDS_CATCH_TOP),
            (MID_X + side * RAPIDS_CATCH_INNER, RAPIDS_CATCH_END),
            SURFACE,
            SLICK,
        )
    # Off the centre line: the lane splitter is on it, one plane below.
    builder.checkpoint("rapids_exit", RAPIDS_EXIT_Y, (445.0, 2960.0))


# --- lanes ------------------------------------------------------------------

LANE_SPLITTER_Y = 3040.0
LANE_SPLITTER_RADIUS = 52.0
LANE_DIVIDER_TOP = 3060.0
LANE_DIVIDER_BOTTOM = 3660.0
LANE_DIVIDER_HALF = 20.0
LANE_LEFT_FACE = MID_X - LANE_DIVIDER_HALF
LANE_RIGHT_FACE = MID_X + LANE_DIVIDER_HALF

# Reach is set by the corridor, not by how big a rotor would look good: the
# tips have to clear both walls by more than a racer's diameter or the gap
# beside the rotor stops being a gap and becomes a trap. The lane is 480
# wide, so 170 of reach leaves 70 on each side against a 60px racer.
LANE_ROTOR = (800.0, 3380.0)
LANE_ROTOR_HUB = 40.0
LANE_ROTOR_ARM = 90.0
LANE_EXIT_Y = 3720.0


def _lanes(builder: CourseBuilder, rng: random.Random) -> None:
    """A wall down the middle: a switchback one side, a rotor the other.

    Nothing chooses a lane. There is a peg on the centre line with a wall
    below it, and which side of the peg a racer comes off decides where it
    goes - the same mechanism the V0.2 split course used, and worth having
    for the same reason: the choice is made by the physics that decide
    everything else about a race.

    The two sides are deliberately not mirror images.

    *Left* is two grippy shelves, each open at the far end, so a racer
    crosses the lane twice on the way down. Nothing on it can go wrong, and
    it is the slower way when the other one goes right.

    *Right* is slick, steeper, and has a rotor turning in the middle of it
    with tip speed enough to throw a racer the width of the lane. Cleared
    cleanly it is much the quicker side; caught, the switchback would have
    been better.

    Neither is a branch in the progress graph, and that is deliberate. Both
    lanes descend the same planes over the same heights, so two racers level
    on the canvas are level in the race whichever side they are on - what
    separates them is how long each side takes, which is what a choice should
    cost. Branch checkpoints exist for a split whose paths cover different
    *distances*; this one does not need them, and not using them keeps the
    ranking here as simple as it looks.
    """
    builder.begin_section("lanes", RAPIDS_EXIT_Y)
    builder.peg(MID_X, LANE_SPLITTER_Y, LANE_SPLITTER_RADIUS, BOUNCY)
    builder.wall(
        (MID_X, LANE_DIVIDER_TOP),
        (MID_X, LANE_DIVIDER_BOTTOM),
        LANE_DIVIDER_HALF * 2.0,
    )

    # Left: switchback, grippy, no surprises. Both drop gaps are 120px.
    builder.ramp((PLAYABLE_LEFT, 3140.0), (400.0, 3280.0), SURFACE, TRACK)
    builder.ramp((LANE_LEFT_FACE, 3380.0), (160.0, 3520.0), SURFACE, TRACK)

    # Right: slick, steep, with a rotor between the two ramps. Both ramps are
    # kept outside the rotor's sweep - an arm turning through a static wall
    # does not collide with it, it passes through it, and it reads as a bug
    # that nothing reports.
    builder.ramp((LANE_RIGHT_FACE, 3080.0), (940.0, 3180.0), SURFACE, SLICK)
    builder.spinner(
        x=LANE_ROTOR[0],
        y=LANE_ROTOR[1],
        hub_radius=LANE_ROTOR_HUB,
        arm_count=3,
        arm_length=LANE_ROTOR_ARM,
        arm_thickness=28.0,
        angular_speed=_spinner_speed(rng, 240.0),
        start_angle=rng.uniform(0.0, 360.0),
    )
    builder.ramp((PLAYABLE_RIGHT, 3580.0), (660.0, 3680.0), SURFACE, SLICK)

    builder.checkpoint("lanes_exit", LANE_EXIT_Y, (250.0, 3760.0))


# --- carousel ---------------------------------------------------------------

# The tray gate. The arm is cut so its tips stop a few pixels short of the
# lips of the hole: broadside, the arms are the missing floor and nothing can
# pass; edge-on, the hub leaves a passable gap either side. Arms long enough
# to overlap the lips would make a pinch a racer could be caught in; much
# shorter and the gate never actually shuts.
CAROUSEL_SHELF_TOP = 3800.0
CAROUSEL_SHELF_Y = 3880.0
CAROUSEL_SHELF_LEFT_END = 390.0
CAROUSEL_SHELF_RIGHT_END = CANVAS_WIDTH - CAROUSEL_SHELF_LEFT_END
CAROUSEL_TRAY_HUB = 34.0
CAROUSEL_TRAY_ARM = 98.0      # reach 132 into a 137px half-hole
CAROUSEL_TRAY_SPEED = 58.0

# The scramblers below the gate: a counter-rotating pair, so a batch that
# leaves the tray together does not arrive at the plunge in the order it
# left. Hubs 480 apart against reaches of 180, so the arms cannot meet.
CAROUSEL_ROTOR_Y = 4150.0
CAROUSEL_ROTORS = ((300.0, -1.0), (780.0, 1.0))
CAROUSEL_EXIT_Y = 4400.0


def _carousel(builder: CourseBuilder, rng: random.Random) -> None:
    """A shelf with one hole in it, and a tray that keeps shutting the hole.

    This is the course's answer to a runaway leader, and it is a physical
    answer rather than a rule. The whole field comes through one hole; the
    hole is plugged for the best part of a second at a time, several times a
    race; and a racer that arrives while it is plugged waits on the shelf
    with whoever else is there. A four-second lead going in is worth whatever
    is left of it when the tray next opens, which is usually not much.

    The hub sits *in* the shelf plane, and that is the safety property the
    whole mechanism rests on. A rotor slung beneath the floor makes a pocket
    between arm and shelf underside that a racer can be caught in; at floor
    level there is no pocket, because a racer sits on the arm exactly as it
    would sit on the shelf and rides it until it tips away.

    A closed gate is not a wall. An arm rising back through the hole lifts
    whatever is standing over it, which is where much of this section's
    mixing comes from, and the shelf either side slopes inwards so nothing
    settles out of reach in a corner.
    """
    builder.begin_section("carousel", LANE_EXIT_Y)

    builder.ramp(
        (PLAYABLE_LEFT, CAROUSEL_SHELF_TOP),
        (CAROUSEL_SHELF_LEFT_END, CAROUSEL_SHELF_Y),
        SURFACE,
        TRACK,
    )
    builder.ramp(
        (PLAYABLE_RIGHT, CAROUSEL_SHELF_TOP),
        (CAROUSEL_SHELF_RIGHT_END, CAROUSEL_SHELF_Y),
        SURFACE,
        TRACK,
    )
    builder.spinner(
        x=MID_X,
        y=CAROUSEL_SHELF_Y,
        hub_radius=CAROUSEL_TRAY_HUB,
        arm_count=2,
        arm_length=CAROUSEL_TRAY_ARM,
        arm_thickness=30.0,
        angular_speed=_spinner_speed(rng, CAROUSEL_TRAY_SPEED),
        start_angle=rng.uniform(0.0, 360.0),
    )

    for x, direction in CAROUSEL_ROTORS:
        builder.spinner(
            x=x,
            y=CAROUSEL_ROTOR_Y,
            hub_radius=40.0,
            arm_count=3,
            arm_length=140.0,
            arm_thickness=28.0,
            angular_speed=_spinner_speed(rng, direction * 200.0),
            start_angle=rng.uniform(0.0, 360.0),
        )

    builder.checkpoint("carousel_exit", CAROUSEL_EXIT_Y, (MID_X, 4450.0))


# --- plunge -----------------------------------------------------------------

RUN_UP_START = (PLAYABLE_LEFT, 4480.0)
PAD_START = (400.0, 4660.0)
PAD_END = (500.0, 4640.0)
PAD_ANGLE = 18.0
PAD_IMPULSE = 300.0
PAD_JITTER = 0.06
PLATFORM_START = (740.0, 4780.0)
PLATFORM_END = (930.0, 4870.0)
PLUNGE_EXIT_Y = 5370.0


def _plunge(builder: CourseBuilder) -> None:
    """A slick run-up, a kicker, and three ways for the jump to end.

    Carried over from the prototype with its proportions intact, because it
    is the one obstacle on that course whose outcome genuinely could not be
    predicted from a racer's position - only from its speed. Clear the
    platform and drop straight down the gap on the right, the quickest line
    there is; land on the platform and roll to the same gap a beat later;
    come in slow, held up in traffic or nudged off line, and fall short into
    the pit, which is the long way round.

    The pit costs distance rather than removing a racer: both lines fall into
    the same basin and leave through the same gap, so a bad jump is a deficit
    to make up - and the sluice below is where it can be made up.
    """
    builder.begin_section("plunge", CAROUSEL_EXIT_Y)
    builder.ramp(RUN_UP_START, PAD_START, SURFACE, SLICK)
    builder.jump_pad(
        PAD_START, PAD_END, SURFACE, PAD_ANGLE, PAD_IMPULSE, PAD_JITTER, SLICK
    )
    builder.ramp(PLATFORM_START, PLATFORM_END, SURFACE, TRACK)
    builder.checkpoint("plunge_landing", 4920.0, (MID_X, 4960.0))

    # The pit: a long shallow slide back to the left, and the whole cost of a
    # short jump. The 100px step down to the basin below it is not slack - the
    # first version put the pit's open end level with the basin ramp beneath
    # and left a 6px slot between them, and every racer that took the pit
    # wedged there and had to be rescued. It is now 105px clear.
    builder.ramp((700.0, 5000.0), (200.0, 5120.0), SURFACE, TRACK)

    builder.ramp((PLAYABLE_LEFT, 5220.0), (470.0, 5310.0), SURFACE, TRACK)
    builder.ramp((PLAYABLE_RIGHT, 5220.0), (610.0, 5310.0), SURFACE, TRACK)
    builder.checkpoint("plunge_exit", PLUNGE_EXIT_Y, (MID_X, 5410.0))


# --- sluice -----------------------------------------------------------------

# A basin, like the bowl, but with a gate on each of its two drains. The basin
# is what makes the leaders wait - racers arrive fast down the slick walls,
# lose it at the break in slope, and have to roll the last stretch to a hole
# on track friction while the basin fills behind them. The gates are what turn
# waiting into a batch: a hole that is shut a third of the time passes less
# than the field arriving at it, so a queue forms whether or not the leader
# happens to catch an open one.
#
# Two gates rather than one, counter-rotating and started at independent
# seeded angles, so they are never in phase and there is no moment when the
# course is shut. A racer facing a closed tray can cross to the other, which
# makes this a choice under time pressure as well as a compression.
SLUICE_WALL_TOP = 5360.0
SLUICE_RIM_Y = 5540.0
SLUICE_RIM_LEFT = 180.0
SLUICE_RIM_RIGHT = CANVAS_WIDTH - SLUICE_RIM_LEFT
SLUICE_SHELF_Y = 5600.0
SLUICE_FLOOR_END = 280.0
SLUICE_ISLAND_PEG_RADIUS = 52.0
SLUICE_TRAY_X = (387.0, CANVAS_WIDTH - 387.0)
SLUICE_TRAY_HUB = 30.0
SLUICE_TRAY_ARM = 65.0        # reach 95 into a 101px half-hole
SLUICE_TRAY_SPEED = 48.0
SLUICE_EXIT_Y = 5700.0


def _sluice(builder: CourseBuilder, rng: random.Random) -> None:
    """The last compression, five sixths of the way down the course.

    Everything above is arranged to get the field here together, because this
    is what makes the ending worth watching: whatever order the plunge
    produced, the basin holds it and the gates let it go again with a
    thousand pixels left to run. A race that was three racers deep at the
    jump is usually five deep coming out of here.

    The first version of this section was a flat shelf with two gates on it,
    and it did the opposite of what it was for. A gate on an open shelf only
    compresses when the *leader* happens to arrive at a shut one; the rest of
    the time the leader sails through and the followers are held, which
    stretches the field rather than closing it. A basin does not have that
    problem, because the constraint is the drain rather than the timing:
    everybody has to get through the same two holes, and the racer in front
    is in the queue like everyone else.

    Both holes are 202px clear against a 60px racer, and the width is the
    difference between a batch and a queue. At 145 - the first tightening -
    the basin passed racers one at a time and the section stopped being a
    compression and became a serialiser: the first racer out of the gate led
    by three seconds and only three of ten reached the line inside the
    finishing window. Three abreast is wide enough that a held-up pile leaves
    together, which is the whole point of holding it up.

    The island is a peg rather than a shelf capped by one. A shelf would need
    to be narrower than the peg to have no ledge on it, at which point the
    shelf is doing nothing the peg was not already doing.
    """
    builder.begin_section("sluice", PLUNGE_EXIT_Y)

    for edge_x, rim_x, floor_x in (
        (PLAYABLE_LEFT, SLUICE_RIM_LEFT, SLUICE_FLOOR_END),
        (PLAYABLE_RIGHT, SLUICE_RIM_RIGHT, CANVAS_WIDTH - SLUICE_FLOOR_END),
    ):
        builder.ramp((edge_x, SLUICE_WALL_TOP), (rim_x, SLUICE_RIM_Y), SURFACE, SLICK)
        builder.ramp((rim_x, SLUICE_RIM_Y), (floor_x, SLUICE_SHELF_Y), SURFACE, TRACK)

    builder.peg(MID_X, SLUICE_SHELF_Y, SLUICE_ISLAND_PEG_RADIUS, BOUNCY)

    for index, x in enumerate(SLUICE_TRAY_X):
        builder.spinner(
            x=x,
            y=SLUICE_SHELF_Y,
            hub_radius=SLUICE_TRAY_HUB,
            arm_count=2,
            arm_length=SLUICE_TRAY_ARM,
            arm_thickness=24.0,
            angular_speed=_spinner_speed(
                rng, SLUICE_TRAY_SPEED if index == 0 else -SLUICE_TRAY_SPEED
            ),
            start_angle=rng.uniform(0.0, 360.0),
        )

    # Off the centre line: the first row of the run-in puts a peg on it.
    builder.checkpoint("sluice_exit", SLUICE_EXIT_Y, (445.0, 5760.0))


# --- run-in -----------------------------------------------------------------

# Staggered, unlike the opening: by this point every racer is moving sideways,
# so a peg on a fall line is a deflector rather than a perch, and the two
# lattices together leave no clean channel to the line.
RUNIN_ROWS = (
    (5820.0, SPREAD_LATTICE),
    (5930.0, GRID_COLUMNS),
)
RUNIN_PEG_RADIUS = 32.0

# The closing sweep. One wide rotor across the whole run-in, a second and a
# half from the line, and it is the single change that decides how late this
# course stays undecided: without it the sluice is the last thing that can
# reorder anybody and the winner is settled at 82% of the race, with it the
# order is still moving inside the final stretch.
RUNIN_ROTOR = (540.0, 6170.0)
RUNIN_ROTOR_HUB = 44.0
RUNIN_ROTOR_ARM = 156.0
RUNIN_ROTOR_SPEED = 210.0

FINISH_Y = 6580.0


def _runin(builder: CourseBuilder, rng: random.Random) -> None:
    """Plinko, one long rotor, then the chute. The last places change here.

    Short on purpose. The sluice has just put four or five racers on level
    terms and this is what they settle it over - long enough that the order
    coming out of the gates is not the order at the line, short enough that
    nothing has time to string out again.

    The rotor is placed last for the same reason the prototype places one
    last: by this point the order is close, and a single wide sweep across a
    tight field changes more places than anything earlier in the course can.
    It is also the only thing standing between the final compression and the
    line, which is what keeps the winner unsettled into the closing seconds.
    """
    builder.begin_section("runin", SLUICE_EXIT_Y)
    for row_y, columns in RUNIN_ROWS:
        for column_x in columns:
            builder.peg(column_x, row_y, RUNIN_PEG_RADIUS, BOUNCY)
    builder.spinner(
        x=RUNIN_ROTOR[0],
        y=RUNIN_ROTOR[1],
        hub_radius=RUNIN_ROTOR_HUB,
        arm_count=2,
        arm_length=RUNIN_ROTOR_ARM,
        arm_thickness=32.0,
        angular_speed=_spinner_speed(rng, RUNIN_ROTOR_SPEED),
        start_angle=rng.uniform(0.0, 360.0),
    )
    builder.ramp((PLAYABLE_LEFT, 6420.0), (430.0, 6510.0), SURFACE, TRACK)
    builder.ramp((PLAYABLE_RIGHT, 6420.0), (650.0, 6510.0), SURFACE, TRACK)
    builder.checkpoint("finish", FINISH_Y, (MID_X, 6620.0))


# --- finish -----------------------------------------------------------------


def _finish(builder: CourseBuilder) -> None:
    """A sloped paddock. Finished racers stay in the world and roll aside.

    Twenty of them have to fit without the pile reaching back up through the
    finish plane and leaving the last arrivals unable to cross it, which is
    why the floor is tilted: arrivals roll away to the right and line up.
    """
    builder.begin_section("finish", FINISH_Y)
    builder.ramp((PLAYABLE_LEFT, 6700.0), (PLAYABLE_RIGHT, 6780.0), SURFACE, TRACK)

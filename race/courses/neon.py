"""The Neon Marble Machine visual-proof course: start, bowl, S-curve bridge.

The three stretches the V1 brief names, and the joins between them. This is
not a race design - it is the smallest course that can carry the
art-direction proof the brief asks for, and it is deliberately short enough
that a whole run fits inside an eleven second replay:

    START     a raised grid of sixteen marbles on a floor that is removed
    CHUTE     a wedge that splits the field into two feed spouts
    BOWL      a round basin draining through one central throat
    THROAT    the transition channel out of the drain
    BRIDGE    a single S-curve channel
    FINISH    a plain catch, so the race can end

## Why the bowl is round *in the simulation plane*

The physics is two-dimensional and stays that way: x across, y down, and
gravity along +y. The renderer gives the third axis its meaning by deriving
a presentation height from the simulation position - and for a bowl the
honest derivation is radial, because that is what makes a marble ride a
curved inner surface rather than slide down a pair of ramps.

That only works if the region a racer can occupy inside the bowl fits
inside the disc the renderer draws. So the bowl is laid out *as a disc* in
the simulation plane: a centre, a radius, and geometry that keeps every
reachable point inside it. `BOWL_CENTRE` and `BOWL_RADIUS` are exported in
the course metadata for exactly that reason - the renderer is told where
the bowl is instead of recognising it, so the mapping and the mesh are
built from one description and cannot disagree.

Every distance below is checked against that disc. `tests/test_neon_proof.py`
re-checks it, because a piece that drifts outside the radius is a racer that
would be drawn hanging in mid-air.

## Why the field is fed through two spouts

A single centred spout drops the field straight down the middle of the disc
and into the drain, which mixes nothing and looks like a funnel. Two spouts
either side of the centre land the field on the two inner walls, so racers
arrive at the drain from both sides at once and have to get past each other
to leave. It is also the only arrangement that keeps a racer's *entry*
point out at the rim, where the radial mapping puts it at the top of the
bowl rather than halfway down it.

Nothing here chooses a winner or reorders a field. The mixing is geometry
and gravity, exactly as it is on the other courses.
"""

from __future__ import annotations

import math

from engine.arena import CANVAS_WIDTH
from race.course import BOUNCY, SLICK, TRACK, RaceCourse
from race.courses.builder import CourseBuilder, curve_points

__all__ = [
    "NEON_COURSE_ID",
    "NEON_SECTIONS",
    "NEON_RACER_COUNT",
    "build_neon_course",
    "bridge_centre_x",
]

NEON_COURSE_ID = "neon"

COURSE_TOP = 0.0
COURSE_BOTTOM = 4120.0

# The sections, in order. Stated here for one reader only - a test that the
# course still has the three stretches the brief asks for, plus the joins
# between them, and that they meet rather than overlap.
#
# It is deliberately *not* the source anything downstream uses. The renderer
# reads the section list out of the replay, which the exporter builds from the
# `begin_section` calls below, and it matches a piece by that piece's own
# `section` field; the proof tool picks its stills by time from the release,
# not by section at all. A tuple that looked like a manifest and was not one
# would be worse than no tuple.
NEON_SECTIONS: tuple[str, ...] = (
    "start",
    "chute",
    "bowl",
    "throat",
    "bridge",
    "finish",
)

# Sixteen, which is the top of the brief's 12-16 range and what the starting
# grid below is shaped for. Exported so one number decides the field size and
# the grid it stands on.
NEON_RACER_COUNT = 16

# Boundary, as every course here builds it: side walls centred on the canvas
# edges, so the playable width is what a racer actually has. Nothing is drawn
# for these - they are the net under the geometry, not part of the machine.
WALL_THICKNESS = 80.0
WALL_INSET = WALL_THICKNESS / 2.0
PLAYABLE_LEFT = WALL_INSET
PLAYABLE_RIGHT = CANVAS_WIDTH - WALL_INSET
MID_X = CANVAS_WIDTH / 2.0

SURFACE = 26.0
# The platform rails are thick enough to sit flush against the boundary wall.
# Thin ones left a 43px slot outside each rail - too narrow for a racer to
# pass and, on paper, somewhere one could be driven into. Unreachable in
# practice, and `tools.course_audit` is right to call it an error anyway: a
# pocket that only geometry keeps a racer out of is a pocket.
RAIL = 54.0

# --- start ------------------------------------------------------------------

# The platform floor *is* the gate: it holds sixteen marbles for the count and
# is removed the tick the race starts, so the field drops rather than rolls
# away. Two rows of eight at a 105 pitch fill the 890px deck almost exactly,
# which is what puts every racer on screen at once without a stack.
PLATFORM_LEFT = 95.0
PLATFORM_RIGHT = 985.0
PLATFORM_TOP = 430.0
GATE_Y = 740.0
GRID_PITCH = 105.0
GRID_COLUMN_COUNT = 8
GRID_ROWS = (540.0, 645.0)

# --- chute ------------------------------------------------------------------

# The wedge that splits the field. Its apex is a peg rather than a corner: a
# flat top between two spouts is somewhere a racer can come to rest with
# nothing to decide which way it goes, which is how the other courses in this
# project have lost racers before.
CHUTE_TOP = GATE_Y
# Where the outer walls stop converging and run straight down.
#
# The chute used to taper the whole way from the deck to the spouts, and the
# apron that produced was the largest single surface in the picture: six units
# of pale deck between the lens and the bowl, hiding the bowl's cradle, its
# legs and the space underneath it. Doing all the converging in the first
# hundred and forty pixels and running vertical for the remaining four hundred
# and seventy leaves the same funnel and opens the sides, and what is behind
# them is the structure the machine is supposed to be standing on.
CHUTE_NECK_Y = 880.0
WEDGE_APEX_Y = 1028.0
# The dome on top of the divider, and it is exactly as wide as the divider is.
#
# Two diverging walls from a shared apex was the first shape, and it left a
# closed V between them that nothing can enter and that the audit reports as a
# trap - correctly, because it is measuring clear width and cannot know about
# reachability. A solid slab has no inside. It needs a dome rather than a flat
# top for the same reason the machine course's island does: a flat top between
# two spouts is somewhere a racer can rest with nothing to decide which way it
# goes.
WEDGE_PEG_RADIUS = 130.0
SPOUT_Y = 1350.0
SPOUT_INNER = 130.0     # spout inner edge, from the centre line
SPOUT_OUTER = 270.0     # spout outer edge, from the centre line

# --- bowl -------------------------------------------------------------------

# The disc. Everything about the bowl is derived from these three numbers, in
# this file and in the renderer, and both read them from the same place.
BOWL_CENTRE_X = MID_X
BOWL_CENTRE_Y = 1820.0
BOWL_RADIUS = 470.0
# The top of the disc, which is where the spouts hand the field over. At this
# plane every point is at radius >= BOWL_RADIUS, so a racer arriving anywhere
# along it is at the rim - which is the whole reason the seam is here and not
# lower down.
BOWL_TOP = BOWL_CENTRE_Y - BOWL_RADIUS
# Half the drain, in course pixels. 220px clear against a 60px racer: three
# and a half diameters, comfortably past the width two racers can arch across.
DRAIN_HALF = 110.0
DRAIN_Y = BOWL_CENTRE_Y
# Where the basin wall meets the rim, as a fraction of the radius. Under 1.0
# on purpose: a racer resting on the wall sits a radius above it, and that has
# to stay inside the disc too.
BASIN_RIM_FRACTION = 0.95
BASIN_RIM_ANGLE = 200.0     # degrees, measured the simulation's way (y down)

# --- throat -----------------------------------------------------------------

THROAT_TOP = DRAIN_Y
THROAT_END = 2200.0

# --- bridge -----------------------------------------------------------------

BRIDGE_TOP = THROAT_END
BRIDGE_END = 3800.0
# One full S: the centre line swings right, back through the middle, left, and
# returns. Amplitude and half-width together keep the outer wall at x=980,
# inside the playable width with room for a rail.
# Under 277, which is where the outer wall's face stops coming within a racer
# diameter of the boundary at the extremes of the swing. Above it the strip
# behind the bridge narrows to 47px at the crest - a pocket a racer fits into
# further up and cannot fit out of, which is a trap whether or not anything
# can get there.
BRIDGE_AMPLITUDE = 268.0
BRIDGE_HALF_WIDTH = 150.0
BRIDGE_STEP = 80.0      # course pixels between wall vertices

# --- finish -----------------------------------------------------------------

FINISH_TOP = BRIDGE_END
FINISH_Y = 3870.0
FINISH_FLOOR_Y = 4020.0
# Wide enough that the whole field fits behind the line rather than queueing
# above it. A proof whose last four seconds are twelve racers stacked in a
# 300px box is a proof of the wrong thing.
FINISH_HALF_WIDTH = 430.0


def bridge_centre_x(y: float) -> float:
    """The S-curve centre line at a course height.

    One function, used to place the walls here and exported nowhere: the
    renderer rebuilds the bridge from the walls it is given, not from this.
    """
    span = max(1.0, BRIDGE_END - BRIDGE_TOP)
    u = (y - BRIDGE_TOP) / span
    return MID_X + BRIDGE_AMPLITUDE * math.sin(2.0 * math.pi * u)


def _basin_rim() -> tuple[float, float]:
    """Where the left basin wall starts, on the disc at `BASIN_RIM_FRACTION`."""
    angle = math.radians(BASIN_RIM_ANGLE)
    return (
        BOWL_CENTRE_X + BASIN_RIM_FRACTION * BOWL_RADIUS * math.cos(angle),
        BOWL_CENTRE_Y + BASIN_RIM_FRACTION * BOWL_RADIUS * math.sin(angle),
    )


def build_neon_course(seed: int) -> RaceCourse:
    """Build the visual-proof course.

    `seed` is accepted and unused: this course has no seeded geometry at all.
    Every other course in this project varies its rotors with the seed and
    this one has none, and a proof that has to be reproduced frame for frame
    is better off with geometry that cannot move.
    """
    builder = CourseBuilder(NEON_COURSE_ID, CANVAS_WIDTH, COURSE_TOP)

    _boundary(builder)
    _start(builder)
    _chute(builder)
    _bowl(builder)
    _throat(builder)
    _bridge(builder)
    _finish(builder)

    return builder.finish(
        COURSE_BOTTOM,
        drop=COURSE_BOTTOM - COURSE_TOP,
        playable_width=PLAYABLE_RIGHT - PLAYABLE_LEFT,
        spawn_slots=float(GRID_COLUMN_COUNT * len(GRID_ROWS)),
        # --- the presentation contract ---
        #
        # Everything below is read by the renderer and by nothing in the
        # simulation. It is exported rather than duplicated in the scene
        # because the bowl mesh, the height mapping and this geometry have to
        # be the same bowl: a renderer that guessed where the disc was would
        # be a second source of truth for it.
        platform_top=PLATFORM_TOP,
        platform_left=PLATFORM_LEFT,
        platform_right=PLATFORM_RIGHT,
        gate_y=GATE_Y,
        chute_top=CHUTE_TOP,
        bowl_top=BOWL_TOP,
        bowl_centre_x=BOWL_CENTRE_X,
        bowl_centre_y=BOWL_CENTRE_Y,
        bowl_radius=BOWL_RADIUS,
        drain_half=DRAIN_HALF,
        drain_y=DRAIN_Y,
        throat_end=THROAT_END,
        bridge_top=BRIDGE_TOP,
        bridge_end=BRIDGE_END,
        finish_top=FINISH_TOP,
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


def grid_columns() -> tuple[float, ...]:
    """Eight starting columns, centred on the course."""
    span = GRID_PITCH * (GRID_COLUMN_COUNT - 1)
    first = MID_X - span / 2.0
    return tuple(first + GRID_PITCH * index for index in range(GRID_COLUMN_COUNT))


def _start(builder: CourseBuilder) -> None:
    """A shuttered deck with sixteen slots on it.

    The deck is the gate. It is one piece rather than a row of them because
    the release has to be a single moment - sixteen marbles leaving together
    is the shot, and anything that opened in parts would stagger it.

    Slots are emitted along a diagonal, as the machine course's are, so that
    a field smaller than the grid still stands spread across it rather than
    filling the back row first.
    """
    builder.begin_section("start", COURSE_TOP)

    columns = grid_columns()
    rows = len(GRID_ROWS)

    # The rails. Short, and inside the boundary: they are what stops sixteen
    # marbles rolling off the deck during the count, and they are drawn - the
    # boundary walls are not.
    for side in (-1.0, 1.0):
        rail_x = MID_X + side * (MID_X - PLAYABLE_LEFT - RAIL / 2.0)
        builder.ramp((rail_x, PLATFORM_TOP), (rail_x, GATE_Y), RAIL, TRACK)

    builder.gate((PLATFORM_LEFT, GATE_Y), (PLATFORM_RIGHT, GATE_Y), SURFACE)

    for slot in range(rows * len(columns)):
        row = slot % rows
        column = (slot // rows + row) % len(columns)
        builder.spawn(columns[column], GRID_ROWS[row])

    builder.checkpoint("start", GATE_Y, (MID_X, GATE_Y + 60.0))


# --- chute ------------------------------------------------------------------


def _chute(builder: CourseBuilder) -> None:
    """Two converging outer walls and a wedge, making two spouts.

    The outer walls converge over the first stretch and then run straight
    down. Vertical at the exit matters more than it sounds: it is what sends a
    racer over the bowl rim travelling downwards rather than sideways across
    it - and it is what keeps the drawn apron narrow enough to see past.
    """
    builder.begin_section("chute", CHUTE_TOP)

    # From the boundary rather than from the platform edge. Starting them at
    # the rail left a 48px slot between the wall and the boundary the moment
    # the wall began to lean inwards, which is the same unreachable-pocket
    # error the rails themselves had.
    for side in (-1.0, 1.0):
        outer_x = MID_X + side * SPOUT_OUTER
        rail_x = MID_X + side * (MID_X - PLAYABLE_LEFT)
        builder.chain(
            curve_points(
                (rail_x, GATE_Y), (outer_x, CHUTE_NECK_Y), segments=3, bulge=1.4
            ),
            SURFACE,
            SLICK,
        )
        builder.ramp((outer_x, CHUTE_NECK_Y), (outer_x, SPOUT_Y), SURFACE, SLICK)

    # The wedge: one solid slab as wide as the two spouts are apart, with the
    # dome seated exactly on top of it.
    builder.peg(MID_X, WEDGE_APEX_Y, WEDGE_PEG_RADIUS, BOUNCY)
    builder.ramp(
        (MID_X, WEDGE_APEX_Y), (MID_X, SPOUT_Y), SPOUT_INNER * 2.0, SLICK
    )

    builder.checkpoint("spouts", 1180.0, (MID_X - 200.0, 1210.0))


# --- bowl -------------------------------------------------------------------


def _bowl(builder: CourseBuilder) -> None:
    """A round basin with one central drain.

    The two inner walls are curved with a bulge *below* 1.0, which is the
    opposite of the chute's: steep where they meet the rim, shallow where
    they meet the drain. That is a bowl's cross-section, and it is what makes
    a racer arrive at the bottom fast, cross it, and run up the far side
    instead of stopping in the middle - which is the mixing, and which the
    renderer turns into a marble circling a bowl.
    """
    builder.begin_section("bowl", BOWL_TOP)

    rim_x, rim_y = _basin_rim()
    for side in (-1.0, 1.0):
        start = (MID_X + side * (MID_X - rim_x), rim_y)
        end = (MID_X + side * DRAIN_HALF, DRAIN_Y)
        builder.chain(
            curve_points(start, end, segments=6, bulge=0.55), SURFACE, TRACK
        )

    builder.checkpoint("bowl_floor", DRAIN_Y - 40.0, (MID_X, DRAIN_Y + 30.0))


# --- throat -----------------------------------------------------------------


def _throat(builder: CourseBuilder) -> None:
    """The transition channel out of the drain. Two slick faces, nothing else.

    They flare from the drain lips to exactly where the bridge's own walls
    begin, so the two meet rather than leaving an eighteen-pixel slot at the
    joint. Nothing can reach that slot, and closing it costs one coordinate.
    """
    builder.begin_section("throat", THROAT_TOP)
    for side in (-1.0, 1.0):
        builder.ramp(
            (MID_X + side * DRAIN_HALF, THROAT_TOP),
            (bridge_centre_x(BRIDGE_TOP) + side * BRIDGE_HALF_WIDTH, BRIDGE_TOP),
            SURFACE,
            SLICK,
        )
    builder.checkpoint("throat_exit", THROAT_END - 40.0, (MID_X, THROAT_END + 20.0))


# --- bridge -----------------------------------------------------------------


def _bridge(builder: CourseBuilder) -> None:
    """One S-curve channel, as two chains either side of the centre line.

    Sampled rather than described: the walls are vertices on
    `bridge_centre_x` offset by the half width, which is what lets the
    renderer rebuild the deck from the walls alone. `BRIDGE_STEP` is short
    enough that consecutive boxes overlap at every joint, so there is no
    seam a racer could squeeze through however tight the turn.
    """
    builder.begin_section("bridge", BRIDGE_TOP)

    steps = max(2, int(round((BRIDGE_END - BRIDGE_TOP) / BRIDGE_STEP)))
    heights = tuple(
        BRIDGE_TOP + (BRIDGE_END - BRIDGE_TOP) * index / steps
        for index in range(steps + 1)
    )
    for side in (-1.0, 1.0):
        builder.chain(
            tuple(
                (bridge_centre_x(y) + side * BRIDGE_HALF_WIDTH, y) for y in heights
            ),
            SURFACE,
            SLICK,
        )

    mid_y = BRIDGE_TOP + (BRIDGE_END - BRIDGE_TOP) * 0.5
    builder.checkpoint("bridge_mid", mid_y, (bridge_centre_x(mid_y + 40.0), mid_y + 40.0))


# --- finish -----------------------------------------------------------------


def _finish(builder: CourseBuilder) -> None:
    """A plain catch. Deliberately not an arena - that is not in this proof."""
    builder.begin_section("finish", FINISH_TOP)

    exit_x = bridge_centre_x(BRIDGE_END)
    for side in (-1.0, 1.0):
        builder.ramp(
            (exit_x + side * BRIDGE_HALF_WIDTH, BRIDGE_END),
            (exit_x + side * FINISH_HALF_WIDTH, FINISH_FLOOR_Y),
            SURFACE,
            TRACK,
        )
    builder.ramp(
        (exit_x - FINISH_HALF_WIDTH, FINISH_FLOOR_Y),
        (exit_x + FINISH_HALF_WIDTH, FINISH_FLOOR_Y),
        SURFACE,
        TRACK,
    )

    builder.checkpoint("finish", FINISH_Y, (exit_x, FINISH_Y + 30.0))

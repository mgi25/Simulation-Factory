"""The Neon Marble Machine visual-proof course: start, bowl, S-curve bridge.

The three stretches the V1 brief names, and the joins between them. This is
not a race design - it is the smallest course that can carry the
art-direction proof the brief asks for, and it is deliberately short enough
that a whole run fits inside an eleven second replay:

    START     a raised grid of sixteen marbles on a floor that is removed
    CHUTE     four narrow launch channels, merging in pairs into two spouts
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
    "lane_bounds",
    "rib_centres",
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
# The platform rails, and they are thick on purpose: 65px is exactly the gap
# between the boundary wall's inner face at x=40 and the platform edge at 105,
# so a rail fills it rather than leaving a slot outside itself. A thin rail
# left a pocket there - too narrow for a racer to leave and, on the audit's
# reading, somewhere one could be driven into. Unreachable in practice, and
# `tools.course_audit` is right to call it an error anyway: a pocket that only
# geometry keeps a racer out of is a pocket.
RAIL = 65.0

# --- start ------------------------------------------------------------------

# The platform floor *is* the gate: it holds sixteen marbles for the count and
# is removed the tick the race starts, so the field drops rather than rolls
# away.
#
# The deck spans exactly the launch block below it, 105 to 975, so a marble
# leaving the platform is already over a lane. Two rows of eight, paired into
# the four channels, is what puts every racer on screen at once without a
# stack and lands four of them in each lane.
PLATFORM_LEFT = 105.0
PLATFORM_RIGHT = 975.0
PLATFORM_TOP = 430.0
GATE_Y = 740.0
GRID_ROWS = (540.0, 645.0)
# Half the gap between the two starting columns inside one lane. 40 leaves a
# five pixel margin between a 30px racer and the lane wall, which is what
# stops a marble beginning the race already touching one.
GRID_HALF_PITCH = 40.0

# --- launch channels --------------------------------------------------------
#
# The V1 chute was one apron: eight hundred and ninety pixels of clear deck
# from the platform to the spouts, and it came out of the renderer as the
# largest pale surface in the picture - six units of it between the lens and
# the bowl, hiding the bowl's cradle and its legs. It was the proof's biggest
# visual weakness and it is the first thing this revision replaces.
#
# Four narrow channels instead, divided by solid ribs. The ribs are what buy
# the change: the renderer derives its decks from the clear spans between
# walls, so a rib is a strip with no deck over it, and a strip with no deck
# over it is a hole through which the structure underneath is visible. Three
# of them across the feed is three bands of negative space where there used to
# be one unbroken slab, and negative space is what a viewer reads as depth.
#
#   105                    975
#    | lane | rib | lane | rib | lane | rib | lane |     four channels
#    |      150     90                                   y 740 -> 1030
#    \____________________/  \____________________/      pairs merge
#          left feed                right feed            y 1030 -> 1190
#            \____/                    \____/            two spouts
#                                                         y 1190 -> 1350
LANE_COUNT = 4
LANE_WIDTH = 150.0
LANE_RIB = 90.0
# Two and a half racer diameters of clear lane, and a rib wide enough that the
# decks either side of it - each reaching a rail's width past its own wall -
# still leave a visible gap between them. A narrower rib is a seam rather than
# a gap, and a seam reads as a scratch on one deck rather than as two decks.

# The outer walls have no outside, and it is the same pocket argument as the
# rails carried to its conclusion. A wall of any finite thickness that leans
# inwards sweeps a wedge of void out behind itself: its inner face arrives at
# the spout while its outer face is still back at the boundary, and the
# triangle between them is sealed above by the wall itself. Nothing can get in
# there, and `tools.course_audit` reports it as a trap anyway - which is the
# correct reading, because it is measuring clear width and cannot know about
# reachability.
#
# So the outer walls reach `OUTSIDE` pixels past the centre line, which is a
# long way outside the course. It costs nothing: these boxes are collision
# geometry and the renderer draws the gaps between them, never the walls
# themselves.
OUTSIDE = 900.0
# The facing wall a racer actually slides along, and how far short of it the
# fill behind it stops. `_outer_wall` has the argument; the short version is
# that the inset has to be more than one step of the merge and less than the
# facing wall is wide, so every shelf on the fill ends up inside the wall.
CHUTE_FACE = 60.0
CHUTE_FILL_INSET = 18.0
# Steps in the merge. Twenty-four puts each one at seven pixels of face, well
# under the inset above, and the facing wall is smooth regardless.
CONVERGE_STEPS = 24

# Where the two outer ribs stop and the pairs merge. High enough that the
# merged feed is short: it is the one stretch of this section that is wide,
# and it is 1.6 units long against the six units the V1 apron ran for.
LANE_END_Y = 1030.0
# The splitter: a dome as wide as the wedge under it, seated where the centre
# rib flares out into the wedge that holds the two spouts apart. A flat top
# between two spouts is somewhere a racer can come to rest with nothing to
# decide which way it goes, which is how the other courses in this project
# have lost racers before.
SPLITTER_Y = 1080.0
CONVERGE_END_Y = 1190.0
SPOUT_Y = 1350.0
SPOUT_INNER = 88.0      # spout inner edge, from the centre line
# The outer edge, and it is set by the bowl rather than by taste. A racer
# arriving at the seam plane is at bowl radius `hypot(dx, BOWL_RADIUS) /
# BOWL_RADIUS`, and the renderer only draws the bowl out to its flange. At 258
# the furthest a racer's *centre* can be is 228, which is rho 1.11 - the same
# worst case the V1 proof measured, with the drawn flange now out at 1.20.
SPOUT_OUTER = 258.0

# The top of each rib is domed for the reason the splitter is: a marble
# dropping off the platform lands on a lane wall from time to time, and a flat
# rib top is somewhere it can stay.
RIB_NOSE = LANE_RIB / 2.0

# The bottom of the two outer ribs is domed as well, and it is a different
# problem with the same answer. A rib that just stops leaves two convex corners
# at the merge, and a racer pressed against a rib by the one behind it can come
# to rest exactly on one: the contact normal at a corner points a few degrees
# above horizontal, which is enough to hold a marble that something else is
# pushing down onto it. Eight of thirty seeds lost a racer that way and the
# recovery system teleported it out.
#
# The dome is wider than the rib and seated above its end, so the rib's corners
# are *inside* the circle and the union has no corner at all. A racer on a
# circle is on a surface whose normal points away from the centre - there is
# nowhere on it to rest.
RIB_TAIL_RADIUS = 55.0
RIB_TAIL_Y = 1010.0


def lane_bounds(index: int) -> tuple[float, float]:
    """The clear span of one launch channel, left to right."""
    left = PLATFORM_LEFT + index * (LANE_WIDTH + LANE_RIB)
    return (left, left + LANE_WIDTH)


def rib_centres() -> tuple[float, ...]:
    """The centre line of each rib between the channels."""
    return tuple(
        (lane_bounds(index)[1] + lane_bounds(index + 1)[0]) / 2.0
        for index in range(LANE_COUNT - 1)
    )


CHUTE_TOP = GATE_Y

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
        # The launch channels, so the renderer can stand a frame under them
        # and cut the gate into one blade per lane. It could infer the lanes
        # from the clear spans it already samples; being told is what keeps
        # the blade over the lane when either changes.
        lane_count=float(LANE_COUNT),
        lane_width=LANE_WIDTH,
        lane_rib=LANE_RIB,
        lane_end_y=LANE_END_Y,
        splitter_y=SPLITTER_Y,
        converge_end_y=CONVERGE_END_Y,
        spout_y=SPOUT_Y,
        spout_inner=SPOUT_INNER,
        spout_outer=SPOUT_OUTER,
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
    """The starting columns, two inside each launch channel.

    Derived from the lanes rather than from a pitch, so the grid and the
    channels cannot drift apart: every marble on the platform is standing
    over the lane it will fall into, and each lane gets four of them.
    """
    columns: list[float] = []
    for index in range(LANE_COUNT):
        left, right = lane_bounds(index)
        centre = (left + right) / 2.0
        columns.append(centre - GRID_HALF_PITCH)
        columns.append(centre + GRID_HALF_PITCH)
    return tuple(columns)


GRID_COLUMN_COUNT = LANE_COUNT * 2


def _start(builder: CourseBuilder) -> None:
    """A shuttered deck with sixteen slots on it.

    The deck is the gate. It is one piece rather than a row of them because
    the release has to be a single moment - sixteen marbles leaving together
    is the shot, and anything that opened in parts would stagger it. The
    renderer draws it as four blades, one per launch channel, which is the
    synchronised lane release the brief asks for and is the same event.

    Slots are emitted along a diagonal, as the machine course's are, so that
    a field smaller than the grid still stands spread across it rather than
    filling the back row first.
    """
    builder.begin_section("start", COURSE_TOP)

    columns = grid_columns()
    rows = len(GRID_ROWS)

    # The rails. Short, and thick enough to fill the strip out to the
    # boundary: they are what stops sixteen marbles rolling off the deck
    # during the count, and they are drawn - the boundary walls are not.
    for side in (-1.0, 1.0):
        rail_x = MID_X + side * (MID_X - PLAYABLE_LEFT - RAIL / 2.0)
        builder.ramp((rail_x, PLATFORM_TOP), (rail_x, GATE_Y), RAIL, TRACK)

    # The ribs carried up through the platform, so the deck is four loading
    # bays rather than one slab and the field stands in the channels it is
    # about to be released into.
    #
    # This is a change to the *course*, not to the picture, and it had to be:
    # without them the sixteen marbles settle onto the gate as one row across
    # the full width, so any rib drawn on the deck would have marbles sitting
    # on both sides of it and through it. Four marbles to a bay is also the
    # only arrangement that makes 'synchronised lane release' mean anything -
    # the gate opens once and four channels empty at the same instant.
    for rib in rib_centres():
        builder.ramp((rib, PLATFORM_TOP), (rib, GATE_Y), LANE_RIB, TRACK)

    builder.gate((PLATFORM_LEFT, GATE_Y), (PLATFORM_RIGHT, GATE_Y), SURFACE)

    for slot in range(rows * len(columns)):
        row = slot % rows
        column = (slot // rows + row) % len(columns)
        builder.spawn(columns[column], GRID_ROWS[row])

        # In the middle of a launch channel, not on the centre line: the centre
    # line is where the rib that splits the field stands, and a respawn point
    # inside geometry is a racer stuck again on the next tick.
    respawn = (lane_bounds(1)[0] + lane_bounds(1)[1]) / 2.0
    builder.checkpoint("start", GATE_Y, (respawn, GATE_Y + 80.0))


# --- chute ------------------------------------------------------------------


def _outer_wall(
    builder: CourseBuilder,
    side: float,
    knots: tuple[tuple[float, float], ...],
) -> None:
    """The channel's outer bound: a smooth facing wall, and a fill behind it.

    Two pieces, and both are needed. Neither alone works, and the two failures
    are worth recording because each is what fixing the other one caused.

    **A thick leaning wall has an outside.** Its inner face arrives at the
    spout while its outer face is still back at the boundary, and the wedge
    between them is a sealed void the audit correctly reports as a trap.
    Offsetting a *polyline* outwards has the same problem at every joint: two
    offset segments that meet at a point on the inner face diverge everywhere
    else, and on the convex side of a turn that opens a V. At seven hundred
    pixels of thickness those Vs came out sixty-five pixels wide in the middle
    of this merge - wider than `MIN_SPAN` - so the renderer swept a deck
    through each of them and the chute grew four phantom channels.

    **A staircase of vertical blocks has ledges.** It has no outside and no
    holes, and every step's top face is a seven-pixel horizontal shelf. A
    racer pressed onto one by the racer behind it stays there: eight of thirty
    seeds lost a marble to a shelf on this merge and the recovery system
    teleported it out.

    So: a thin wall along the exact face for a racer to touch, offset
    *perpendicular* so its face is the line it is given, and a staircase
    filling everything behind it. The fill's inner face is set a step and a
    half short of the wall's, which puts every one of its shelves inside the
    wall's own body - interior to the union, and unreachable. What a racer
    meets is a smooth line; what the audit measures is solid to the boundary.
    """
    # The facing wall, one box per segment, offset perpendicular.
    for (y1, x1), (y2, x2) in zip(knots, knots[1:]):
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy)
        if length <= 0.0:
            continue
        offset_x = side * CHUTE_FACE * 0.5 * dy / length
        offset_y = -side * CHUTE_FACE * 0.5 * dx / length
        builder.ramp(
            (x1 + offset_x, y1 + offset_y),
            (x2 + offset_x, y2 + offset_y),
            CHUTE_FACE,
            SLICK,
        )

    # The fill, one vertical block per interval, reaching past the boundary.
    outer = MID_X + side * OUTSIDE
    for (y1, x1), (y2, _x2) in zip(knots, knots[1:]):
        if y2 <= y1:
            continue
        face = x1 + side * CHUTE_FILL_INSET
        centre = (face + outer) * 0.5
        builder.ramp((centre, y1), (centre, y2), abs(face - outer), SLICK)


def _converge(x_from: float, x_to: float, y_from: float, y_to: float,
              steps: int) -> tuple[tuple[float, float], ...]:
    """An eased merge, as `(height, inner face)` knots.

    Smoothstep rather than a straight line: a channel that turns in and out of
    its convergence with no crease is what makes the merge read as a
    manufactured junction rather than as a funnel, and it is the one place in
    this section a curve earns its cost. It also matters mechanically - the
    profile leaves and arrives with zero slope, so the merge meets the straight
    runs either side of it without a corner.
    """
    knots = []
    for index in range(steps + 1):
        t = index / steps
        eased = t * t * (3.0 - 2.0 * t)
        knots.append((y_from + (y_to - y_from) * t,
                      x_from + (x_to - x_from) * eased))
    return tuple(knots)


def _chute(builder: CourseBuilder) -> None:
    """Four launch channels, merging in pairs into two feed spouts.

    The shape is in the constants block above. What is worth saying here is
    why the ribs run *past* the plane the pairs merge on and why the outer
    walls do their converging in one short stretch.

    The ribs end at `LANE_END_Y` and the outer walls hold their lane width
    until the same plane, so the count of channels changes exactly once, from
    four to two, on one plane. The renderer's deck builder closes its open
    sweeps and opens new ones where that count changes, and it can only do
    that cleanly if the change is a single event: two ribs ending forty
    pixels apart would be two closures, and the second would land in the
    middle of the first's merged run.

    The outer walls then converge over a hundred and sixty pixels and run
    vertical for the rest. Vertical at the exit matters more than it sounds:
    it is what sends a racer over the bowl rim travelling downwards rather
    than sideways across it.
    """
    builder.begin_section("chute", CHUTE_TOP)

    ribs = rib_centres()
    centre_rib = ribs[len(ribs) // 2]

    # The three ribs. The outer two stop where the pairs merge; the centre
    # one runs on to the splitter and becomes the wedge.
    for rib in ribs:
        builder.peg(rib, CHUTE_TOP, RIB_NOSE, BOUNCY)
        if rib == centre_rib:
            # The centre rib runs on to the splitter, whose own dome is wider
            # than the rib and covers its end the same way.
            builder.ramp((rib, CHUTE_TOP), (rib, SPLITTER_Y), LANE_RIB, SLICK)
            continue
        builder.ramp((rib, CHUTE_TOP), (rib, LANE_END_Y), LANE_RIB, SLICK)
        builder.peg(rib, RIB_TAIL_Y, RIB_TAIL_RADIUS, SLICK)

    # The splitter and the wedge under it, exactly as wide as each other.
    builder.peg(centre_rib, SPLITTER_Y, SPOUT_INNER, BOUNCY)
    builder.ramp(
        (centre_rib, SPLITTER_Y), (centre_rib, SPOUT_Y), SPOUT_INNER * 2.0, SLICK
    )

    # The outer walls, as one staircase per side: the lane, the merge, the
    # spout. Straight runs are a single block each - a vertical box needs no
    # steps to be exact - and only the merge is divided.
    for side in (-1.0, 1.0):
        lane_x = MID_X + side * (MID_X - PLATFORM_LEFT)
        spout_x = MID_X + side * SPOUT_OUTER
        _outer_wall(builder, side, (
            (CHUTE_TOP - 40.0, lane_x), (LANE_END_Y, lane_x),
        ))
        _outer_wall(builder, side, _converge(
            lane_x, spout_x, LANE_END_Y, CONVERGE_END_Y, CONVERGE_STEPS))
        _outer_wall(builder, side, (
            (CONVERGE_END_Y, spout_x), (SPOUT_Y + 20.0, spout_x),
        ))

    builder.checkpoint("spouts", 1240.0, (MID_X - 170.0, 1270.0))


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

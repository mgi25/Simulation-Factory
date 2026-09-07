"""The start, rebuilt as a mixing basin instead of a converging funnel.

## Why the funnel had to go rather than be tuned again

Three sessions have measured the same thing. Eight bays 4.4 layout units across
have to become one channel 1.88 wide, and V1.2's start does that with a single
7.34-unit taper. A taper is a queue, and the queue is ordered by how far each
bay has to travel sideways to reach the line - which is bay index. Twenty
geometries inside that topology were scanned across two sessions: bay staggers,
fin schedules, a merge tree, three densities of deflector, six wheel positions,
three wide trays, five bumper sets and four launch openings. Every static one
made the ordering *stronger*; the only mechanism that ever reduced it held a
fifth of the field up. `docs/sloped_race_v12_findings.md` has the numbers.

So this replaces the topology:

    8 BAYS on a flat shelf   - unchanged, and unchanged to look at
      |  one wide flat ramp     same drop, same angle, same distance for all
      v
    BASIN                     a shallow round dish the whole field is in at once
      |  one notch in the rim  they arrive together and jostle for one exit
      v
    CHUTE                     from the notch to the launch entry

## The one thing that makes it fair, and it is not the chaos

The feed is **congruent**. One flat ramp of the same length dropping the same
height at the same angle under every bay, so every marble reaches the basin
with the same speed and the same heading, differing only in where along the
basin's upstream edge it arrives. Nothing about a bay's *position* buys it
speed or distance any more - and the shelf's pan is flat for the same reason,
because the fan's dish had the outer bays resting 0.10 units higher than the
inner ones.

That is the whole fairness argument. The basin's job is only to stop the
arrival order from being preserved: eight marbles crossing a dish and meeting
one drain together jostle for it, and which one drops through is decided by the
pile rather than by who got there first. A funnel orders because arrivals are
*staggered*; a basin does not because they are *simultaneous*.

## Why the deck had to rise

The basin needs the field moving. V1.2's start deck sits 0.63 layout units
above the launch entry, and that 0.63 is the entire energy budget for
everything between the gate and the course - which is why a held stretch inside
the old fan came out at 1.7 degrees and every bumper in it left three quarters
of the field stranded.

`START_LIFT` raises the deck 2.20 units, which is the local macro-layout
adjustment to the start the brief allows and nothing else. It buys 2.83 units
of drop, spent as 0.30 across the shelf, 0.55 down the ramp, 0.55 across the
dish and 1.00 down the chute - and every one of those had to be bought, because
V1.2's whole start budget was 0.63 and a basin with nothing to spend is a basin
the field settles in. The eight bays, the gate, the release and the
side-by-side presentation are untouched; the platform stands on longer legs.

`sloped.contract` carries the moved anchor as a named deviation with its own
budget, the way orange's tail heights are carried.
"""

from __future__ import annotations

import math
from typing import Any

from marble3d.geometry import GUIDED, Socket, Transform, basis_from_forward_up
from marble3d.mesh import Aabb, TriMesh
from marble3d.modules.base import Probe
from marble3d.units import MARBLE_DIAMETER, MARBLE_RADIUS

from sloped import layout
from sloped.scale import to_sim
from sloped.solids import merge_meshes, tube
from sloped.stations import StartGrid, _bay_x, _place, _strip
from sloped.track import TrackRun

__all__ = ["START_LIFT", "StartBasin"]

# How far the start deck is raised above the recorded anchor, in layout units.
# See the module docstring; this is the only macro-layout number that moves.
START_LIFT = 1.90


class StartBasin(StartGrid):
    """The eight bays and the gate of `StartGrid`, on a basin instead of a fan.

    Subclassed rather than rewritten because the bays, the gate paddles, the
    release and `marble_starts` are all hard-won and none of them changes - the
    corrections recorded in `StartGrid` about fin pinch, gate axis order and
    resting pitch all still apply. What changes is everything downstream of the
    shelf.
    """

    # --- the shelf the field waits on -----------------------------------
    #
    # Flat and full width, rather than the fan's taper. The bays rest at
    # z = -2.74 and the gate stands at -2.44, so the shelf runs to -2.10 and
    # hands straight to the feeders.
    SHELF_END = -2.10
    # The shelf has to *tip* the field off itself. At 0.02 over 1.30 units it
    # is 0.9 degrees and nothing moves: measured, all eight marbles sat at
    # z = -2.4 for the whole trial, a foot past the lifted gate. The gate holds
    # them meanwhile, so the shelf is free to be as steep as it needs.
    SHELF_DROP = 0.18
    # The shelf's pan is **flat across**, and that is a fairness change as much
    # as a plumbing one. The fan's trough was a dish, `-0.30 + 0.16 u^2`, so the
    # outer bays rested 0.10 layout units *higher* than the inner ones and
    # started the race with more potential energy - a systematic per-bay
    # difference sitting underneath everything else that was being measured.
    # Flat, every bay starts at the same height, and every feeder can start at
    # the same height too.
    SHELF_PAN = 0.30

    # --- the feed ramp ---------------------------------------------------
    #
    # **One wide flat ramp, not eight chutes.** The first build gave each bay
    # its own cradled feeder, and a cradle 0.30 wide and 0.20 deep has a
    # curvature radius of 0.225 at its bottom - smaller than the 0.285 marble
    # that has to sit in it. The marble cannot reach the floor and wedges
    # between the two walls instead: measured, all eight stopped four fifths of
    # the way down their own feeder and stayed there.
    #
    # Widening them is not available either, because eight feeders at the bays'
    # 0.63 pitch cannot be wider than 0.63 without merging - which is the hint.
    # Congruence never needed separate channels: what it needs is the same drop
    # over the same distance at the same angle, and one flat ramp gives every
    # marble exactly that while leaving its lateral position alone, so the field
    # arrives spread across the basin's edge rather than in eight lanes.
    FEED_END = -0.80               # where the ramp meets the basin's edge
    FEED_DROP = 0.55

    # --- the basin ------------------------------------------------------
    #
    # A **stadium**, not a circle: straight sides from the feeders' mouths back
    # to `BASIN_Z`, then a semicircular downstream end. A circle cannot take
    # eight feeders that arrive on a straight line - at the one z where the
    # circle reaches the mouths it is a single point, so the outer six would
    # have poured over the wall onto the floor outside it.
    # The basin is as wide as the ramp that feeds it. It was 2.30 and the ramp
    # is 2.73, so the outer marbles arrived beside the basin rather than in it
    # and fell past its side walls - three of eight gone in the first ten
    # seconds. Widening the basin rather than tapering the ramp keeps the ramp
    # congruent, which is the one property the whole design rests on.
    BASIN_Z = 0.00                 # where the straight sides give way to the cap
    BASIN_W = 2.75                 # half width, matching the ramp's own
    RIM_RISE = 0.70                # wall height above the dish's edge
    DISH_DEPTH = 0.85              # rim edge down to the spillway
    SPILL_HALF = 0.95              # half width of the notch in the rim
    # The dish's rings start here rather than at the low point itself, because
    # a ring of radius zero is twenty-nine coincident vertices and every
    # triangle between it and the next ring has no area - which `check_mesh`
    # reports, and rightly: the solver takes a meaningless normal from one. The
    # small opening left at the low point sits inside the notch, where the
    # chute's own first ring already covers it.
    DISH_MIN_R = 0.15

    # A dome in the middle of the basin, or zero for none.
    #
    # Without it the basin drains in bay order: the notch is one point, every
    # marble heads straight for it, and distance to it is a function of which
    # bay you came from. Measured over six seeds, bays 4 and 5 - the two centre
    # ones - took the first two places out of the basin in five of them and
    # bays 0 and 7 the last two in all six. Room to mill is not the same thing
    # as a reason to mill.
    #
    # An island blocks the straight line from the middle of the ramp to the
    # notch, so the field has to split around it and merge again, and it does
    # that symmetrically - it is on the centreline, so it cannot favour a side.
    ISLAND_R = 0.0
    ISLAND_Z = 1.10
    ISLAND_RISE = 0.55


    # --- the chute ------------------------------------------------------
    #
    # It has to be **wider than the hole and start upstream of it**. The first
    # build made it 0.62 half-width starting at the drain's own centre, while
    # the hole is 0.85 in radius and reaches 0.85 upstream - so a marble
    # dropping through the near half of the drain, or through either edge of
    # it, landed beside the chute and fell out of the world. Seven of eight,
    # every trial.
    CHUTE_HALF = 0.95
    CHUTE_DEPTH = 0.26
    CHUTE_WALL = 0.70              # lip height; a marble arrives here falling
    CHUTE_LEAD = 0.15              # how far upstream of the hole it begins

    RINGS = 28                     # points around the basin
    STEPS = 9                      # radial steps across the dish

    def __init__(self, module_id: str = "start", launch: TrackRun | None = None) -> None:
        super().__init__(module_id, launch)
        # The lift moves the module's own origin; `exit_local` is recomputed
        # from it so the chute still lands exactly on the launch's entry.
        self.origin = (self.origin[0], self.origin[1] + START_LIFT, self.origin[2])
        launch_entry = (
            launch.path[0] if launch is not None else layout.run("launch")["controls"][0]
        )
        angle = math.radians(self.yaw_deg)
        cos, sin = math.cos(angle), math.sin(angle)
        delta = tuple(launch_entry[axis] - self.origin[axis] for axis in range(3))
        self.exit_local = (
            delta[0] * cos - delta[2] * sin,
            delta[1],
            delta[0] * sin + delta[2] * cos,
        )
        self._mesh = None

    # --- what the bays stand on -----------------------------------------
    #
    # `marble_starts` and the gate reach the shelf through these three, and on
    # a flat shelf all three are simple. The fan's taper, its cradle blend and
    # its `spread` factor are all gone: the bays sit at their authored pitch on
    # a level dish, which is also why the resting pitch is exactly 0.63 rather
    # than the fan's 0.63 times a shrinking width factor.

    def _half_at(self, t: float) -> float:
        return layout.START_BACK_HALF

    def _t_at_z(self, z: float) -> float:
        back = -layout.GROOVE_LENGTH
        return min(max((z - back) / (self.SHELF_END - back), 0.0), 1.0)

    def _path_at(self, t: float) -> tuple[float, float, float]:
        back = (0.0, layout.DECK_TOP - 0.02, -layout.GROOVE_LENGTH)
        front = (0.0, layout.DECK_TOP - 0.02 - self.SHELF_DROP, self.SHELF_END)
        return tuple(back[axis] + (front[axis] - back[axis]) * t for axis in range(3))

    def _cradle(self, across: float, half: float, t: float = 0.0) -> float:
        """Flat. See `SHELF_PAN` - this is the fairness change, not plumbing."""
        return -self.SHELF_PAN

    # --- geometry helpers ------------------------------------------------

    def _feed_x(self, index: int) -> float:
        """A feeder's centreline, which is its bay's - they run straight."""
        return _bay_x(index)

    # --- heights, derived rather than typed ------------------------------
    #
    # Every one of these used to be its own constant and two of them disagreed:
    # the feeders ended 0.18 below the dish's edge, so the field ran down a
    # chute and then up a step into the basin. Deriving them in a chain means a
    # change to the shelf or the feeders cannot leave the basin behind.

    @property
    def shelf_y(self) -> float:
        """The shelf's *rim* line, which the pan hangs below."""
        return layout.DECK_TOP - 0.02 - self.SHELF_DROP

    @property
    def shelf_floor(self) -> float:
        """What a marble actually rests on, and what the feeders start from.

        The first build took the feeders from `shelf_y` and forgot the pan, so
        every feeder mouth stood 0.098 layout units *above* the floor leading
        into it - a step a marble crawling off the shelf at 1 wu/s stops dead
        against. Measured: six of eight never left the shelf and the other two
        stopped in the feeders.
        """
        return self.shelf_y - self.SHELF_PAN

    @property
    def dish_edge(self) -> float:
        """The floor where the feeders arrive - their own mouth height."""
        return self.shelf_floor - self.FEED_DROP

    @property
    def dish_lip(self) -> float:
        return self.dish_edge - self.DISH_DEPTH

    @property
    def rim_top(self) -> float:
        return self.dish_edge + self.RIM_RISE

    @property
    def spill_z(self) -> float:
        """Where the dish is lowest: the middle of the notch in the rim."""
        return self.BASIN_Z + self.BASIN_W

    def _dish_at(self, x: float, z: float) -> float:
        """The basin floor at a point: a cone about the spillway.

        Normalised by the furthest corner the basin has, so the floor is
        `dish_lip` at the notch and `dish_edge` at the far upstream corners,
        and it slopes toward the exit from everywhere.
        """
        drain_x, drain_z = self._drain_centre()
        reach = math.hypot(self.BASIN_W, self.spill_z - self.FEED_END)
        span = math.hypot(x - drain_x, z - drain_z) / reach
        floor = self._dish_y(span)
        if self.ISLAND_R > 0.0:
            radius = math.hypot(x, z - self.ISLAND_Z)
            if radius < self.ISLAND_R:
                # A smooth dome, so a marble that climbs it is turned rather
                # than stopped by a wall.
                lift = self.ISLAND_RISE * (1.0 - (radius / self.ISLAND_R) ** 2)
                return floor + lift
        return floor

    def _dish_y(self, frac: float) -> float:
        """The basin floor, as a fraction of the way from the drain to the wall.

        By fraction rather than by radius, because the stadium's wall is not
        the same distance away in every direction - so a dish keyed to absolute
        radius would meet the wall at a different height upstream and
        downstream, and the floor would run through it on one side and stop
        short on the other.

        **Conical, not quadratic.** A quadratic dish is level at the drain's
        mouth, which sounds like the right way to stop a marble dropping in on
        its first pass and is actually a flat spot for eight of them to settle
        on. With `surface_friction` at 0.50 a pile on a level floor is
        statically stable, and that is what the first build produced: the field
        crossed the basin, converged, and stopped dead over the hole.

        A constant slope has no flat spot anywhere, so nothing can come to
        rest; the basin is kept from draining too eagerly by being wide enough
        that a marble crosses it rather than by being level in the middle.
        """
        span = min(max(frac, 0.0), 1.0)
        return self.dish_lip + (self.dish_edge - self.dish_lip) * span

    def _drain_centre(self) -> tuple[float, float]:
        return (0.0, self.spill_z)

    def _inside(self, x: float, z: float) -> bool:
        """The stadium: a rectangle with a semicircular downstream cap."""
        if z > self.BASIN_Z:
            return x * x + (z - self.BASIN_Z) ** 2 <= self.BASIN_W**2
        return abs(x) <= self.BASIN_W and z >= self.FEED_END

    # --- the collider ----------------------------------------------------

    def local_colliders(self) -> list[TriMesh]:
        if self._mesh is not None:
            return [self._mesh]
        pieces: list[TriMesh] = []
        pieces.extend(self._shelf())
        pieces.extend(self._feeders())
        pieces.extend(self._basin())
        pieces.extend(self._chute())
        self._mesh = merge_meshes(pieces, f"{self.id}_basin")
        return [self._mesh]

    def _shelf(self) -> list[TriMesh]:
        """The flat trough the eight bays wait on, plus its back stop."""
        rows, columns = 12, 10
        half = layout.START_BACK_HALF
        rings = []
        for row in range(rows):
            t = row / (rows - 1)
            centre = self._path_at(t)
            ring = [_place(self.origin, self.frame, (-(half + 0.15), centre[1] + 0.32, centre[2]))]
            for column in range(columns + 1):
                across = -half + 2.0 * half * column / columns
                ring.append(
                    _place(
                        self.origin,
                        self.frame,
                        (across, centre[1] + self._cradle(across, half), centre[2]),
                    )
                )
            ring.append(_place(self.origin, self.frame, (half + 0.15, centre[1] + 0.32, centre[2])))
            rings.append(ring)
        pieces = [_strip(rings, f"{self.id}_shelf")]

        # The back stop, subdivided rather than drawn as three points. The
        # shelf is 5.46 layout units across and three points put 4.79
        # simulation units between neighbours, which `check_mesh` reports as a
        # phantom span - a triangle long enough to reach across a whole piece
        # is the shape a mis-ordered profile builds, so the limit is worth
        # respecting even where the geometry is deliberate.
        back = self._path_at(0.0)
        span = [-half + 2.0 * half * step / 8 for step in range(9)]
        pieces.append(
            _strip(
                [
                    [
                        _place(self.origin, self.frame, (x, back[1] - 0.30, back[2]))
                        for x in span
                    ],
                    [
                        _place(self.origin, self.frame, (x, back[1] + 0.32, back[2]))
                        for x in span
                    ],
                ],
                f"{self.id}_backstop",
            )
        )
        return pieces

    def _feeders(self) -> list[TriMesh]:
        """The ramp from the shelf to the basin's upstream edge.

        Flat across and level in width, so a marble's drop, its angle and its
        distance are identical whichever bay it came from - and its lateral
        position is untouched, which is the only thing about a bay that is
        allowed to survive.
        """
        half = layout.START_BACK_HALF
        start_y = self.shelf_floor
        rows, columns = 10, 12
        rings = []
        for row in range(rows):
            t = row / (rows - 1)
            z = self.SHELF_END + (self.FEED_END - self.SHELF_END) * t
            floor = start_y - self.FEED_DROP * t
            ring = [_place(self.origin, self.frame, (-(half + 0.15), floor + 0.34, z))]
            for column in range(columns + 1):
                across = -half + 2.0 * half * column / columns
                ring.append(_place(self.origin, self.frame, (across, floor, z)))
            ring.append(_place(self.origin, self.frame, (half + 0.15, floor + 0.34, z)))
            rings.append(ring)
        return [_strip(rings, f"{self.id}_ramp")]

    def _basin(self) -> list[TriMesh]:
        """The dish, with a hole in it, and the wall around it."""
        pieces: list[TriMesh] = []
        drain_x, drain_z = self._drain_centre()

        # The dish, as a grid rather than as rings about the low point.
        #
        # Rings only work when the low point is *inside* the basin. This one is
        # on the rim - that is what a spillway is - so straight sideways from
        # it the basin is zero wide, every ring collapsed to the clamp, and the
        # far two thirds of the floor was simply not built. Measured: one
        # marble of eight found the exit and the other seven sat on nothing.
        #
        # A grid over the basin's own extent has no such special direction. The
        # floor is a cone about the spillway, so it is lowest there and rises
        # evenly in every direction, and the corners are covered like anywhere
        # else.
        rings: list[list[tuple[float, float, float]]] = []
        rows, columns = 18, 20
        for row in range(rows + 1):
            z = self.FEED_END + (self.spill_z - self.FEED_END) * row / rows
            ring = []
            for column in range(columns + 1):
                x = -self.BASIN_W + 2.0 * self.BASIN_W * column / columns
                ring.append(
                    _place(self.origin, self.frame, (x, self._dish_at(x, z), z))
                )
            rings.append(ring)
        pieces.append(_strip(rings, f"{self.id}_dish"))

        # The wall, from the dish's edge up to the rim - and **not** across the
        # ramp's mouth. The first build ran it the whole way round the stadium,
        # which put a 0.70-tall wall across the upstream edge exactly where the
        # ramp arrives: the field ran down the ramp, hit it, and stopped. All
        # eight, every trial, at z = -1.1.
        #
        # So the rim is emitted as runs, broken wherever the boundary is the
        # open upstream edge. `_strip` wants contiguous rings, so a break ends
        # one piece and starts the next rather than collapsing a ring.
        runs: list[list[tuple[float, float]]] = []
        current: list[tuple[float, float]] = []
        for point in range(self.RINGS + 1):
            theta = 2.0 * math.pi * point / self.RINGS
            cos, sin = math.cos(theta), math.sin(theta)
            reach = self._wall_reach(cos, sin)
            x = drain_x + cos * reach
            z = drain_z + sin * reach
            open_ramp = abs(z - self.FEED_END) < 0.02 and abs(x) <= layout.START_BACK_HALF + 0.16
            open_spill = z > self.BASIN_Z and abs(x) <= self.SPILL_HALF
            if open_ramp or open_spill:
                if len(current) > 1:
                    runs.append(current)
                current = []
                continue
            current.append((x, z))
        if len(current) > 1:
            runs.append(current)
        for order, run in enumerate(runs):
            wall = [
                [
                    _place(self.origin, self.frame, (x, self._dish_at(x, z) + rise, z))
                    for x, z in run
                ]
                for rise in (0.0, self.RIM_RISE)
            ]
            pieces.append(_strip(wall, f"{self.id}_rim{order}"))

        return pieces

    def _wall_reach(self, cos: float, sin: float) -> float:
        """Distance from the drain to the basin wall along one direction.

        Found by bisection on `_inside` rather than solved per boundary. The
        stadium has three of them - two straight sides, an upstream edge and a
        circular cap - and a closed form that has to pick the right one in
        every direction is a place to get a sign wrong. Thirty halvings is
        exact to a ten-thousandth and this runs once, at build.
        """
        drain_x, drain_z = self._drain_centre()
        low, high = 0.0, 2.0 * (self.BASIN_W + abs(self.spill_z - self.FEED_END))
        for _ in range(30):
            mid = 0.5 * (low + high)
            if self._inside(drain_x + cos * mid, drain_z + sin * mid):
                low = mid
            else:
                high = mid
        # The low point sits *on* the rim, so straight downstream the wall is
        # zero away and the dish would divide by nothing. Clamped, which only
        # affects the handful of directions pointing out through the notch.
        return max(low, 0.5)

    def _chute(self) -> list[TriMesh]:
        """From the notch in the rim to the launch's entry.

        The first design put the drain in the middle of the dish and ran the
        chute *under* it. That meant a hole, a throat, a tunnel and a roof, and
        every one of them was a defect in turn: side walls standing 0.4 above
        the dish floor made a wall across the basin, the chute started at the
        hole's centre so marbles dropping through its upstream half missed it
        entirely, and a pile over a 2.2-diameter hole was statically stable.

        A notch in the downstream rim is the same idea with none of that. The
        dish is lowest at the notch, the whole field converges on it, and the
        chute simply carries on from there in the open.
        """
        _spill_x, spill_z = self._drain_centre()
        end_x, end_y, end_z = self.exit_local
        rows = 12
        rings = []
        for row in range(rows):
            t = row / (rows - 1)
            z = spill_z + (end_z - spill_z) * t
            x = end_x * t
            y = self.dish_lip + (end_y - self.dish_lip) * t
            ring = []
            for step in range(9):
                across = -self.CHUTE_HALF + 2.0 * self.CHUTE_HALF * step / 8
                u = abs(across) / self.CHUTE_HALF
                ring.append(
                    _place(
                        self.origin,
                        self.frame,
                        (x + across, y + self.CHUTE_DEPTH * u * u, z),
                    )
                )
            for side, index in ((-1.0, 0), (1.0, None)):
                point = _place(
                    self.origin,
                    self.frame,
                    (x + side * self.CHUTE_HALF, y + self.CHUTE_WALL, z),
                )
                if index is None:
                    ring.append(point)
                else:
                    ring.insert(index, point)
            rings.append(ring)
        return [_strip(rings, f"{self.id}_chute")]

    # --- what the machine asks for ---------------------------------------

    def local_sockets(self) -> dict[str, Socket]:
        end_x, end_y, end_z = self.exit_local
        point = _place(self.origin, self.frame, (end_x, end_y - 0.26, end_z))
        return {
            "exit": Socket(
                name="exit",
                frame=Transform(
                    position=point,
                    rotation=basis_from_forward_up(self.frame[2], (0.0, 1.0, 0.0)),
                ),
                kind=GUIDED,
                width=to_sim(2.0 * self.CHUTE_HALF),
                height=to_sim(0.62),
            )
        }

    def local_bounds(self) -> Aabb:
        bounds = self.local_colliders()[0].aabb()
        return Aabb(
            tuple(value - 0.5 * MARBLE_DIAMETER for value in bounds.lower),
            tuple(value + 0.5 * MARBLE_DIAMETER for value in bounds.upper),
        )

    def local_probes(self) -> list[Probe]:
        """The shelf, the feeders and the dish, each where a marble runs.

        Not the drain or the chute: a probe fired down the drain measures the
        chute's floor through the hole, which is the geometry being correct
        rather than a finding, and there is no honest `expected_point` to give
        it.
        """
        probes: list[Probe] = []
        reach = 3.0 * MARBLE_RADIUS
        drain_x, drain_z = self._drain_centre()

        def fire(local, label):
            surface = _place(self.origin, self.frame, local)
            up = (0.0, 1.0, 0.0)
            probes.append(
                Probe(
                    start=tuple(surface[axis] + up[axis] * reach for axis in range(3)),
                    end=tuple(surface[axis] - up[axis] * reach for axis in range(3)),
                    expect_hit=True,
                    expected_point=surface,
                    tolerance=0.05,
                    label=label,
                )
            )

        half = layout.START_BACK_HALF
        for row in range(3):
            t = row / 2
            centre = self._path_at(t)
            for fraction in (-0.6, 0.0, 0.6):
                across = fraction * half
                fire(
                    (across, centre[1] + self._cradle(across, half), centre[2]),
                    f"{self.id}.shelf[{row}]@{fraction:+.1f}",
                )

        start_y = self.shelf_y
        for index in (0, 3, 7):
            x = self._feed_x(index)
            for row in range(2):
                t = 0.25 + 0.5 * row
                z = self.SHELF_END + (self.FEED_END - self.SHELF_END) * t
                fire((x, start_y - self.FEED_DROP * t, z), f"{self.id}.feed{index}[{row}]")

        for point, (x, z) in enumerate(
            (
                (0.0, self.FEED_END + 0.5),
                (-1.6, 0.2),
                (1.6, 0.2),
                (-0.8, 1.6),
                (0.8, 1.6),
                (0.0, self.spill_z - 0.5),
            )
        ):
            fire((x, self._dish_at(x, z), z), f"{self.id}.dish[{point}]")
        return probes

    def describe(self) -> dict[str, Any]:
        return {
            "kind": "StartBasin",
            "bays": layout.BAYS,
            "bay_pitch": round(to_sim(layout.BAY_PITCH), 6),
            "yaw_deg": round(self.yaw_deg, 4),
            "gate_z": round(self.gate_z, 4),
            "release_time": self.release_time,
            "lift": START_LIFT,
            "shelf_end": self.SHELF_END,
            "ramp": {
                "from": self.SHELF_END,
                "to": self.FEED_END,
                "drop": self.FEED_DROP,
                "length": round(
                    math.hypot(self.FEED_END - self.SHELF_END, self.FEED_DROP), 4
                ),
                "angle_deg": round(
                    math.degrees(
                        math.atan2(self.FEED_DROP, self.FEED_END - self.SHELF_END)
                    ),
                    3,
                ),
            },
            "basin": {
                "centre_z": self.BASIN_Z,
                "half_width": self.BASIN_W,
                "dish_edge": round(self.dish_edge, 4),
                "dish_lip": round(self.dish_lip, 4),
                "rim_top": round(self.rim_top, 4),
            },
            "spillway": {
                "z": round(self.spill_z, 4),
                "half": self.SPILL_HALF,
                "floor": round(self.dish_lip, 4),
            },
            "exit_local": [round(v, 4) for v in self.exit_local],
        }

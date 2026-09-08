"""The line-to-radial start: eight bays abreast, eight cups around a ring.

## Why the topology had to change

`docs/sloped_race_v13_basin.md` measured the mechanism twice, in two different
start topologies, and it is not a tuning problem:

    a single common exit orders the field by distance to that exit, and
    distance to the exit is a function of which bay a marble started in.

The taper orders the field at its throat and the basin orders it at its notch.
Twenty-four geometries inside that family have been falsified. What breaks it is
**equal distance from every bay to the exit**, which needs the launch points
arranged *about* the exit rather than beside it.

## What this builds

    visible 8-bay shelf, flat, one synchronised gate    <- unchanged, and seen
      |
    the same shelf, fanning: 0.63 pitch eased out to 1.00
      |
    eight walled chutes, hidden under the platform
      |
    eight identical cups on one circle about the drain  <- the fairness surface
      |
    one synchronised port release
      |
    a conical dish, eight-fold symmetric, central drain
      |
    a chute onto the launch run

## The cups are the design

Each is the same short tangential channel, at the same radius from the drain, on
the same level, closed by the same paddle, and all eight paddles lift together.
So whatever the chutes did - and they cannot be congruent, because eight
collinear bays cannot be mapped onto eight points of a circle by congruent
curves - the field is re-presented to the course from a C8-symmetric ring, at
rest, simultaneously. **Distance from bay to exit is identical for all eight**,
which is the measured mechanism removed at its root rather than diluted.

Section 7 of the brief permits exactly this: "A deterministic global mechanism
is allowed only if genuinely necessary, but first test the passive radial
architecture." `port_gate` is a constructor flag so both are measurable, and
both are reported. Nothing here is per-marble: one release time, one paddle
geometry, one cup, eight times over.

Cups launch tangentially - floor tilted inward, paddle across the ring at the
counterclockwise end - so the field spirals in rather than converging head-on
on the hole, where eight marbles can arch across it. The same geometry in all
eight, so the swirl costs no symmetry.

## Two constraints that shaped everything else

**Eight walled chutes cannot start at the bays' pitch.** A chute needs clear
width over a 0.57 racer plus a wall each side; the bays are 0.63 apart. So the
shelf itself is the fan: one shared surface with the 0.11 ridges `StartGrid`
proved a marble will follow, easing the lane pitch out to `FAN_PITCH` before any
wall exists. That also keeps the feed **congruent** - one flat-across pan at one
grade, so every bay reaches the chutes with the same speed and heading and only
its lateral position differs.

**The shelf's pan is flat across.** The fan's trough is a dish, `-0.30 + 0.16
u^2`, so its outer bays rest 0.10 layout units higher than its inner ones - a
systematic per-bay energy difference that sat under three sessions of
measurement without being noticed. Flat, every bay starts at the same height.

## The height chain, derived and not typed

`shelf_floor` -> `port_floor` -> `dish_edge` -> `drain_lip` -> the launch entry.
The basin's notes record what a typed chain costs: its feeders ended 0.18 below
the dish's edge and the field stopped dead against the step.
"""

from __future__ import annotations

import math
from typing import Any

from marble3d.geometry import Transform, basis_from_forward_up
from marble3d.machine import Aabb, GUIDED, Socket
from marble3d.mesh import TriMesh
from marble3d.modules.base import Actuator, Probe
from marble3d.units import MARBLE_DIAMETER, MARBLE_RADIUS

from sloped import layout
from sloped.scale import to_sim
from sloped.solids import merge_meshes, plate, tube
from sloped.stations import StartGrid, _bay_x, _place, _strip
from sloped.track import TrackRun

__all__ = ["START_LIFT", "RadialStart", "feeder_table"]

# How far the whole start module rises above its recorded node.
#
# The height chain needs 2.24 layout units of fall between the shelf's pan and
# the launch entry, plus the exit chute's own grade, and the recorded geometry
# offers 0.65. The basin lifted 1.90 for the same reason and the brief allowed
# it as a local adjustment; this is the same kind of change, 0.63 further.
START_LIFT = 4.30


class RadialStart(StartGrid):
    """The eight bays and the gate of `StartGrid`, on a radial ring.

    Subclassed for the reason `StartBasin` is: the bays, the paddles, the
    release and the resting pitch carry three sessions of corrections - fin
    pinch, gate axis order, resting pitch - and none of them changes. What
    changes is everything downstream of the shelf.
    """

    START_KIND = "radial"

    # --- the shelf, which is also the fan --------------------------------
    #
    # It reaches further back than the drawn pod's groove because the ridges
    # have to fan the lane pitch out before any wall exists, and 22 degrees of
    # divergence is what a 0.11 ridge can turn. Over the 1.45 units the drawn
    # groove offers it would have to be 43 degrees, and a marble rides over a
    # ridge at that angle instead of following it.
    SHELF_BACK = -4.60
    SHELF_END = -0.95
    SHELF_DROP = 0.62              # 8.7 degrees over 4.05 units
    SHELF_PAN = 0.30
    FAN_PITCH = 1.20               # the lane pitch the chutes need

    # --- the ring --------------------------------------------------------
    DISH_Z = 0.75                  # the drain, just past the fan's lip
    PORT_R = 1.35                  # every cup, at one radius from the drain
    PORT_DEG0 = 22.5               # cups every 45 degrees from here
    PASS_BY_R = 2.25               # the radius a chute passes a foreign cup at
    DELIVERY_LEAD = 13.0           # how far clockwise of its port a chute lands
    CUP_ARC = 26.0                 # how much ring one cup occupies
    CUP_HALF = 0.36                # radial half width of a cup and a chute
    CUP_WALL = 0.62
    # **The paddle has to be taller than a resting marble's centre.** At the
    # gate's own 0.42 its top stood at exactly the height of a marble sitting
    # on the cup floor, and traced in simulation every racer rolled over it:
    # a cup floor at `port_floor` puts a 0.285 marble's centre at
    # `port_floor + 0.285`, and the paddle's base is a further `CUP_TILT`
    # down. 0.62 clears that by 0.19.
    PORT_GATE_HEIGHT = 0.62
    CUP_TILT = 0.14                # how far a cup's floor falls inward

    # --- the chutes ------------------------------------------------------
    # Short chutes, so a modest drop. The first build put the ring a full 2.5
    # units past the fan and needed 1.34 of drop over a 2.3-unit chute - 30
    # degrees mean and 60 at its steepest, which is a fall onto a paddle rather
    # than a delivery. With the ring at the lip the same drop would be absurd.
    # Steep enough that the longest chute delivers in about two seconds, and
    # therefore that the port release can be short. The first build gave the
    # chutes 1.05 and the longest took 4.5 s, which is dead time in the Short
    # and - more to the point - longer than the stall detector's own patience.
    FEEDER_DROP = 2.20             # fan lip to cup floor, every chute
    FEEDER_FLOOR_R = 0.60          # the cradle's radius; > a marble's own
    FEEDER_WALL = 0.34
    WALL_THICK = 0.09
    SAMPLES_PER_UNIT = 6

    # --- the dish --------------------------------------------------------
    # 1.24 across. One marble is 0.57, so two *could* line up abreast - but
    # eight converging on a 0.84 hole arched across it and the whole field
    # stopped, every trial, which is the failure the basin warned about in a
    # different shape. A wider hole plus the vanes below is the answer; a
    # narrower one is a plug.
    DRAIN_R = 0.62
    DISH_FALL = 0.38               # dish edge down to the drain lip
    RIM_RISE = 0.30
    RIM_R = 1.70
    # Eight identical vanes, one per sector, that turn a radially-inward marble
    # into the ring's own rotational sense. Without them the field converges
    # head-on on the drain and arches; with them it arrives as a rotating queue
    # and goes through one at a time. Eight-fold symmetric, so the swirl costs
    # no symmetry - which a spiral floor could not manage, because a spiral has
    # a riser and a riser has an azimuth.
    # Their inner end, not their outer one, is what matters: at a foot radius
    # of 1.02 a vane stands exactly where a released marble leaves its cup's
    # inner lip at 0.99, and traced in simulation the field sat wedged between
    # the two. They start well inside the lip now.
    VANE_RISE = 0.22
    VANE_FROM = (0.88, -30.0)      # (radius, degrees clockwise of its port)
    VANE_TO = (0.66, -56.0)

    # --- the exit --------------------------------------------------------
    CHUTE_HALF = 0.80
    CHUTE_WALL = 0.58
    CHUTE_LEAD = 0.20

    RINGS = 48                     # points around the dish
    STEPS = 6                      # radial steps across it
    CHUTE_STEPS = 12

    # One synchronised release for all eight cups, in seconds, on the same
    # clock as the start gate's own 0.30. `feeder_table` reports each chute's
    # rolling time and `tools/sloped_radial_check.py` asserts the margin over
    # the slowest of them.
    PORT_RELEASE = 3.40
    PORT_GATE = True

    # Plan waypoints for the west four chutes, between the fan's lip and the
    # approach point outside the rim; the east four are mirrored, so bays `i`
    # and `7 - i` are reflections and the left-right half of any bias is gone
    # by construction. Authored rather than solved, and *checked* rather than
    # asserted - `tools/sloped_radial_check.py` measures the clearance every
    # pair actually has, in three dimensions.
    #
    # Bays 0 and 1 both head for x = -1.35 and would otherwise run within 0.38
    # of each other with no height between them, so bay 0 is held out west and
    # comes in behind. Bay 3 bridges the dish, which is a height separation and
    # is measured as one.
    # One authored route per bay, as plan waypoints between the fan's lip and
    # the approach point outside the rim. Eight rather than four mirrored,
    # because the ring is C8-symmetric and *not* mirror-symmetric: every cup is
    # handed the same way round, so a cup's delivery point is 13 degrees
    # clockwise of it whichever side of the module it is on, and the east
    # routes are rotations of the west ones rather than reflections. The
    # fairness argument does not need the mirror - it needs the cups.
    #
    # Authored and then *checked*: `tools/sloped_radial_check.py` measures the
    # three-dimensional clearance every pair actually has.
    # One authored route per bay, as plan waypoints between the fan's lip and
    # the delivery point in its own cup. Eight rather than four mirrored,
    # because the ring is C8-symmetric and not mirror-symmetric: every cup is
    # handed the same way round, so a delivery point is `DELIVERY_LEAD`
    # clockwise of its port whichever side of the module it is on, and the east
    # routes are rotations of the west ones rather than reflections. The
    # fairness argument does not need the mirror - it needs the cups.
    #
    # Authored and then *checked*: `tools/sloped_radial_check.py` measures the
    # three-dimensional clearance every pair actually has. The odd chutes carry
    # a `PASS_BY_R` waypoint because they have to get round the outside of an
    # even chute's cup, whose outer wall reaches 1.80 from the drain.
    # One authored route per bay, as plan waypoints between the fan's lip and
    # the delivery point in its own cup.
    #
    # The four wrapping routes carry waypoints that hold them at a radius of
    # two or more from the drain until they are at their own cup's angle,
    # because a cup's outer wall reaches 1.80 and a chute crossing inside that
    # runs through someone else's cup. The four short routes need none: their
    # cups are the nearest ones and they go straight there.
    # One authored route per bay, as plan waypoints between the fan's lip and
    # the delivery point in its own cup.
    #
    # **The wrapping routes are held out at a radius of two and a half to
    # three and a half from the drain**, and that width is why the undercroft
    # is wider than the pod above it. It is not a preference. A cup's outer
    # wall reaches 1.80, so a chute crossing inside that runs through someone
    # else's cup; and two chutes cannot be separated in *height* here, because
    # a profile shallow enough to hold one high through the crossing is
    # shallower than the 8 degrees the basin measured a marble stalling on.
    # Plan separation is the only budget with room in it, so it is spent.
    ROUTES = {
        0: ((-4.10, 0.35), (-3.75, 2.10), (-2.20, 3.20)),
        1: ((-2.85, 0.20), (-2.40, 1.45), (-1.70, 2.05)),
        2: ((-1.80, -0.30), (-1.62, 0.20)),
        3: (),
        4: (),
        5: ((1.80, -0.30), (1.62, 0.20)),
        6: ((2.85, 0.20), (2.40, 1.45), (1.70, 2.05)),
        7: ((4.10, 0.35), (3.75, 2.10), (2.20, 3.20)),
    }

    # How each chute spends its drop, as an exponent on the remaining fraction:
    # above one drops early and runs low, below one runs high and drops late.
    #
    # **This is what isolates the chutes, and with this little plan to work in
    # it is the only thing that can be.** A wrapping route and a short route
    # cross wherever the short one's cup lies under the long one's path, and
    # eight 0.90-wide channels do not fit side by side in the two units between
    # the fan's lip and the ring. So the wrapping routes stay high and drop at
    # the end - which also clears the dish rim they pass over - and the short
    # ones drop first and get out from under them. Graded by wrap, so that two
    # neighbours are never on the same level.
    # How each chute spends its drop, as an exponent on the remaining fraction.
    #
    # Near one for every chute, and deliberately so. A shaped profile was the
    # first attempt at isolating the crossings, and it cannot be: a chute held
    # high through a crossing has to be nearly level to get there, and the
    # basin measured a marble stalling at 0.9 degrees and running at 7.9. The
    # exponents here only *lean* the profile - the wrapping chutes a little
    # late, so they clear the dish rim they pass over, the short ones a little
    # early - and every grade stays over ten degrees.
    DROP_SHAPE = {0: 0.62, 1: 0.68, 2: 1.15, 3: 1.45,
                  4: 1.45, 5: 1.15, 6: 0.68, 7: 0.62}

    def __init__(
        self,
        module_id: str = "start",
        launch: TrackRun | None = None,
        port_gate: bool | None = None,
    ) -> None:
        super().__init__(module_id, launch)
        self.port_gate = self.PORT_GATE if port_gate is None else bool(port_gate)
        # The lift moves the module's own origin; `exit_local` is recomputed
        # from it so the exit chute still lands exactly on the launch's entry.
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
        self._feeders_cache: list[dict] | None = None
        self.gate_z = self._field_z() + layout.MARBLE_RADIUS + 0.06

    # --- what the bays stand on ------------------------------------------

    def _field_z(self) -> float:
        return self.SHELF_BACK + 0.66

    def _t_at_z(self, z: float) -> float:
        back = self.SHELF_BACK
        return min(max((z - back) / (self.SHELF_END - back), 0.0), 1.0)

    def _path_at(self, t: float) -> tuple[float, float, float]:
        back = (0.0, layout.DECK_TOP - 0.02, self.SHELF_BACK)
        front = (0.0, layout.DECK_TOP - 0.02 - self.SHELF_DROP, self.SHELF_END)
        return tuple(back[axis] + (front[axis] - back[axis]) * t for axis in range(3))

    def _cradle(self, across: float, half: float, t: float = 0.0) -> float:
        """Flat. The fairness change, not the plumbing one - see the docstring."""
        return -self.SHELF_PAN

    def _half_at(self, t: float) -> float:
        """The shelf's half width, widening with the fan it carries."""
        return abs(self.lane_x(0, t)) + 0.5 * self.FAN_PITCH + 0.10

    def lane_x(self, index: int, t: float) -> float:
        """Lane `index`'s centre at `t` along the shelf: the fan.

        Held at the drawn pitch until the gate, then eased out to `FAN_PITCH`
        by the lip. Held first because the resting field is what the viewer
        sees and it has to be at the pitch the drawn module has; eased rather
        than broken, because a ridge that changes direction at a point is a
        kerb rather than a guide.
        """
        gate_t = self._t_at_z(self._gate_z_for(index)) + 0.05
        if t <= gate_t:
            spread = 1.0
        else:
            u = (t - gate_t) / max(1.0 - gate_t, 1e-6)
            spread = 1.0 + (self.FAN_PITCH / layout.BAY_PITCH - 1.0) * _smoothstep(
                0.0, 1.0, u
            )
        return _bay_x(index) * spread

    # --- the height chain -------------------------------------------------

    @property
    def shelf_y(self) -> float:
        return layout.DECK_TOP - 0.02 - self.SHELF_DROP

    @property
    def shelf_floor(self) -> float:
        """What a marble rests on at the lip, and where a chute starts."""
        return self.shelf_y - self.SHELF_PAN

    @property
    def port_floor(self) -> float:
        """The cup floors at their outer edge. One height for all eight."""
        return self.shelf_floor - self.FEEDER_DROP

    @property
    def dish_edge(self) -> float:
        """The dish's outer floor, level with the cups' inner lip."""
        return self.port_floor - self.CUP_TILT

    @property
    def drain_lip(self) -> float:
        return self.dish_edge - self.DISH_FALL

    # --- the ring ---------------------------------------------------------

    @staticmethod
    def _port_slot(index: int) -> int:
        """Which of the eight ring positions bay `index` feeds.

        **A linear map from the fan's lip to the ring, and it comes out
        exact.** Take the lip parameter `v = (i - 3.5) / 3.5`, so the eight
        bays sit at v = -1, -5/7, ... , +1, and send it to the ring angle
        `270 + 157.5 v` degrees. Then v = 1/7 lands on 292.5, 3/7 on 337.5,
        5/7 on 22.5 and 1 on 67.5 - the eight cups at exactly 45 degrees, with
        no rounding, because 157.5 / 3.5 is 45. The outer bays take the far
        cups and the inner bays the near ones, which is the nesting order that
        keeps the routes from crossing: read outward, each route wraps further
        round the ring than the one inside it.
        
        The first build had this backwards - inner bays to far cups - and every
        route then had to cut across the ones outside it.
        """
        return (2, 3, 4, 5, 6, 7, 0, 1)[index]

    def port_angle(self, index: int) -> float:
        return (self.PORT_DEG0 + 45.0 * self._port_slot(index)) % 360.0

    def _ring_point(self, radius: float, deg: float, y: float):
        angle = math.radians(deg)
        return (radius * math.cos(angle), y, self.DISH_Z + radius * math.sin(angle))

    def port_point(self, index: int) -> tuple[float, float, float]:
        return self._ring_point(self.PORT_R, self.port_angle(index), self.port_floor)

    # --- the chutes -------------------------------------------------------

    def fan_outlet(self, index: int) -> tuple[float, float, float]:
        return (self.lane_x(index, 1.0), self.shelf_floor, self.SHELF_END)

    def route_plan(self, index: int) -> list[tuple[float, float]]:
        """A chute's plan controls: the fan's lip, its waypoints, its cup."""
        outlet = self.fan_outlet(index)
        deg = self.port_angle(index) - self.DELIVERY_LEAD
        cup = self._ring_point(self.PORT_R, deg, 0.0)
        controls = [(outlet[0], outlet[2])]
        controls.extend(self.ROUTES[index])
        controls.append((cup[0], cup[2]))
        return controls

    def feeders(self) -> list[dict]:
        """One chute per bay, as samples and a description.

        **Not congruent, and they cannot be.** Eight collinear mouths cannot be
        mapped onto eight points of a circle by congruent curves, and forcing
        equal length with detours only trades a length difference for a
        curvature difference - the same inequality in different clothes. So the
        chutes equalise what geometry allows: every one drops exactly
        `FEEDER_DROP` at a constant grade onto a cup at exactly `PORT_R`. The
        cups absorb the rest, and `feeder_table` reports the residual rather
        than hiding it.
        """
        if self._feeders_cache is None:
            self._feeders_cache = [self._feeder(i) for i in range(layout.BAYS)]
        return self._feeders_cache

    def _feeder(self, index: int) -> dict:
        outlet = self.fan_outlet(index)
        plan = _smooth(self.route_plan(index), self.SAMPLES_PER_UNIT)
        span = _polyline_length(plan)
        # Constant grade, so a chute has no flat spot anywhere. The basin's
        # note about a level dish applies to a chute too: a marble that comes
        # to rest in a feeder never reaches its cup.
        shape = self.DROP_SHAPE[index]
        samples: list[tuple[float, float, float]] = []
        run = 0.0
        for order, point in enumerate(plan):
            if order:
                run += math.dist(plan[order - 1], point)
            u = min(1.0, run / max(span, 1e-6))
            # Exactly `shelf_floor` at the lip and exactly `port_floor` at the
            # cup for every chute whatever the shape, so the drop stays equal
            # while the height *at a given plan point* becomes free.
            samples.append(
                (
                    point[0],
                    self.port_floor + self.FEEDER_DROP * (1.0 - u) ** shape,
                    point[1],
                )
            )
        return {
            "bay": index,
            "slot": self._port_slot(index),
            "angle": self.port_angle(index),
            "mouth": outlet,
            "plan_length": span,
            "length": span,
            "grade": self.FEEDER_DROP / max(span, 1e-6),
            "shape": shape,
            "steepest_deg": _steepest(samples),
            "drop": self.FEEDER_DROP,
            "samples": samples,
        }

    # --- the collider -----------------------------------------------------

    def local_colliders(self) -> list[TriMesh]:
        if self._mesh is not None:
            return [self._mesh]
        pieces: list[TriMesh] = []
        pieces.extend(self._shelf())
        pieces.extend(self._chutes())
        pieces.extend(self._cups())
        pieces.extend(self._dish())
        pieces.extend(self._exit_chute())
        self._mesh = merge_meshes(pieces, f"{self.id}_radial")
        return [self._mesh]

    def _shelf(self) -> list[TriMesh]:
        pieces: list[TriMesh] = []
        rows, columns = 20, 16
        rings: list[list[tuple[float, float, float]]] = []
        for row in range(rows + 1):
            t = row / rows
            centre = self._path_at(t)
            half = self._half_at(t)
            floor = centre[1] - self.SHELF_PAN
            ring = [_place(self.origin, self.frame, (-half, centre[1] + 0.34, centre[2]))]
            for column in range(columns + 1):
                across = -half + 2.0 * half * column / columns
                ring.append(_place(self.origin, self.frame, (across, floor, centre[2])))
            ring.append(_place(self.origin, self.frame, (half, centre[1] + 0.34, centre[2])))
            rings.append(ring)
        pieces.append(_strip(rings, f"{self.id}_shelf"))

        # Seven fanning ridges, the whole length of the shelf. Past the gate a
        # ridge is not a lane divider any more - it is the steering that fans
        # the field out to the chutes' pitch. On the pan at the drawn stock's
        # radius rather than as tubes in the marble's path; `StartGrid` records
        # the measurement that forced that.
        for index in range(layout.BAYS - 1):
            lane: list[tuple[float, float, float]] = []
            for row in range(21):
                t = row / 20
                centre = self._path_at(t)
                across = 0.5 * (self.lane_x(index, t) + self.lane_x(index + 1, t))
                lane.append(
                    _place(
                        self.origin,
                        self.frame,
                        (across, centre[1] - self.SHELF_PAN, centre[2]),
                    )
                )
            for step in range(len(lane) - 1):
                pieces.append(
                    tube(
                        lane[step],
                        lane[step + 1],
                        to_sim(self.FIN_RADIUS),
                        segments=8,
                        name=f"{self.id}_fin{index}_{step}",
                        caps=step in (0, len(lane) - 2),
                    )
                )

        back = self._path_at(0.0)
        half = self._half_at(0.0)
        pieces.append(
            plate(
                [
                    _place(self.origin, self.frame, (-half, back[1] - self.SHELF_PAN, back[2])),
                    _place(self.origin, self.frame, (half, back[1] - self.SHELF_PAN, back[2])),
                    _place(self.origin, self.frame, (half, back[1] + 0.34, back[2])),
                    _place(self.origin, self.frame, (-half, back[1] + 0.34, back[2])),
                ],
                name=f"{self.id}_backstop",
                steps=5,
            )
        )
        return pieces

    def _chute_section(self) -> list[tuple[float, float]]:
        """A chute read across: two walls and a cradle wider than a marble.

        The cradle's radius matters and the basin's notes say why: a cradle
        0.30 wide and 0.20 deep has a curvature radius of 0.225 at its bottom,
        *smaller* than the 0.285 marble that has to sit in it, so the marble
        never reaches the floor and wedges between the walls instead - all
        eight stopped four fifths of the way down their own feeder.
        `FEEDER_FLOOR_R` is 0.60, over twice a marble's radius.
        """
        half = self.CUP_HALF
        radius = self.FEEDER_FLOOR_R
        points: list[tuple[float, float]] = [(-(half + self.WALL_THICK), self.FEEDER_WALL)]
        steps = 8
        for step in range(steps + 1):
            across = -half + 2.0 * half * step / steps
            points.append(
                (across, radius - math.sqrt(max(radius * radius - across * across, 0.0)))
            )
        points.append((half + self.WALL_THICK, self.FEEDER_WALL))
        return points

    def _chutes(self) -> list[TriMesh]:
        pieces: list[TriMesh] = []
        section = self._chute_section()
        for feeder in self.feeders():
            samples = feeder["samples"]
            rings: list[list[tuple[float, float, float]]] = []
            for order, point in enumerate(samples):
                behind = samples[max(order - 1, 0)]
                ahead = samples[min(order + 1, len(samples) - 1)]
                forward = (ahead[0] - behind[0], ahead[2] - behind[2])
                span = math.hypot(*forward) or 1.0
                side = (forward[1] / span, -forward[0] / span)
                rings.append(
                    [
                        _place(
                            self.origin,
                            self.frame,
                            (
                                point[0] + side[0] * across,
                                point[1] + rise,
                                point[2] + side[1] * across,
                            ),
                        )
                        for across, rise in section
                    ]
                )
            pieces.append(_strip(rings, f"{self.id}_chute{feeder['bay']}"))
        return pieces

    def _cup_section(self) -> list[tuple[float, float]]:
        """A cup read radially: outer wall, floor falling inward, inner lip.

        The floor falls `CUP_TILT` toward the drain, so a released marble
        leaves inward as well as along the ring. That is the swirl, and it is
        the same swirl in every cup.
        """
        half = self.CUP_HALF
        return [
            (half + self.WALL_THICK, self.CUP_WALL),
            (half, 0.0),
            (half * 0.5, -self.CUP_TILT * 0.45),
            (0.0, -self.CUP_TILT * 0.72),
            (-half * 0.5, -self.CUP_TILT * 0.90),
            (-half, -self.CUP_TILT),
        ]

    def _cups(self) -> list[TriMesh]:
        pieces: list[TriMesh] = []
        section = self._cup_section()
        for index in range(layout.BAYS):
            end = self.port_angle(index)
            start = end - self.CUP_ARC
            rings: list[list[tuple[float, float, float]]] = []
            for step in range(7):
                deg = start + (end - start) * step / 6
                rings.append(
                    [
                        _place(
                            self.origin,
                            self.frame,
                            self._ring_point(
                                self.PORT_R + across, deg, self.port_floor + rise
                            ),
                        )
                        for across, rise in section
                    ]
                )
            pieces.append(_strip(rings, f"{self.id}_cup{index}"))
            # A back stop at the clockwise end, so a marble delivered into the
            # middle of the cup cannot run out of the end it arrived by.
            low = [
                _place(
                    self.origin,
                    self.frame,
                    self._ring_point(self.PORT_R + across, start, self.port_floor + rise),
                )
                for across, rise in section
            ]
            # `+ 0.06`, because the section's own first point is already at
            # `CUP_WALL` and a top ring at exactly that height duplicates it -
            # two coincident vertices are a zero-area triangle, which
            # `check_mesh` reports and rightly: the solver takes a meaningless
            # normal from one.
            high = [
                _place(
                    self.origin,
                    self.frame,
                    self._ring_point(
                        self.PORT_R + across,
                        start,
                        self.port_floor + self.CUP_WALL + 0.06,
                    ),
                )
                for across, _rise in section
            ]
            pieces.append(_strip([low, high], f"{self.id}_cupback{index}"))
        return pieces

    def _dish(self) -> list[TriMesh]:
        """A cone from the cup ring to the drain, the rim, and the apron.

        **Conical rather than dished**, and the basin's notes carry the
        measurement: a floor level at the drain's mouth is a flat spot eight
        marbles settle on, and with `surface_friction` at 0.50 a pile on a
        level floor is statically stable. A constant slope has no flat spot
        anywhere.
        """
        pieces: list[TriMesh] = []
        outer = self.PORT_R - self.CUP_HALF
        rings: list[list[tuple[float, float, float]]] = []
        for step in range(self.STEPS + 1):
            radius = outer - (outer - self.DRAIN_R) * step / self.STEPS
            fraction = (radius - self.DRAIN_R) / max(outer - self.DRAIN_R, 1e-6)
            y = self.drain_lip + (self.dish_edge - self.drain_lip) * fraction
            rings.append(
                [
                    _place(
                        self.origin,
                        self.frame,
                        self._ring_point(radius, 360.0 * point / self.RINGS, y),
                    )
                    for point in range(self.RINGS + 1)
                ]
            )
        pieces.append(_strip(rings, f"{self.id}_dish"))

        # The apron between the cup ring and the rim, and the rim itself. The
        # rim is unbroken: the cups are inside it and the chutes arrive over
        # the top of it, so unlike the basin's rim it has nothing to leave a
        # gap for - which is the failure that note warns about.
        apron = [
            [
                _place(
                    self.origin,
                    self.frame,
                    self._ring_point(radius, 360.0 * p / self.RINGS, self.dish_edge - 0.02),
                )
                for p in range(self.RINGS + 1)
            ]
            for radius in (self.RIM_R, self.PORT_R + self.CUP_HALF + self.WALL_THICK)
        ]
        pieces.append(_strip(apron, f"{self.id}_apron"))
        wall = [
            [
                _place(
                    self.origin,
                    self.frame,
                    self._ring_point(self.RIM_R, 360.0 * p / self.RINGS, self.dish_edge - 0.02),
                )
                for p in range(self.RINGS + 1)
            ],
            [
                _place(
                    self.origin,
                    self.frame,
                    self._ring_point(
                        self.RIM_R, 360.0 * p / self.RINGS, self.dish_edge + self.RIM_RISE
                    ),
                )
                for p in range(self.RINGS + 1)
            ],
        ]
        pieces.append(_strip(wall, f"{self.id}_rim"))

        for index in range(layout.BAYS):
            port = self.port_angle(index)
            foot = self._ring_point(
                self.VANE_FROM[0], port + self.VANE_FROM[1], self._dish_y(self.VANE_FROM[0])
            )
            head = self._ring_point(
                self.VANE_TO[0], port + self.VANE_TO[1], self._dish_y(self.VANE_TO[0])
            )
            low = [
                _place(self.origin, self.frame, foot),
                _place(self.origin, self.frame, head),
            ]
            high = [
                _place(
                    self.origin,
                    self.frame,
                    (point[0], point[1] + self.VANE_RISE, point[2]),
                )
                for point in (foot, head)
            ]
            pieces.append(_strip([low, high], f"{self.id}_vane{index}"))
        return pieces

    def _dish_y(self, radius: float) -> float:
        """The dish's floor at a radius. One expression, used by the vanes too."""
        outer = self.PORT_R - self.CUP_HALF
        fraction = (radius - self.DRAIN_R) / max(outer - self.DRAIN_R, 1e-6)
        return self.drain_lip + (self.dish_edge - self.drain_lip) * min(
            max(fraction, 0.0), 1.0
        )

    def _exit_chute(self) -> list[TriMesh]:
        """From under the drain to the launch run's entry.

        Wider than the hole and starting upstream of it, which the basin's
        notes record the cost of getting wrong: a chute narrower than the drain
        and starting at the drain's own centre lost seven of eight marbles over
        its edges, every trial.
        """
        # **The chute has to start well below the drain and grow its walls
        # afterwards.** At `drain_lip - 0.05` with full walls from its first
        # ring, the walls stood 0.46 *above* the dish's inner floor - they came
        # up through the hole and made a slot, and traced in simulation the
        # field wedged in it and the whole start froze. A chute under a drain
        # is a landing, and a landing has no kerb.
        start = (0.0, self.drain_lip - 0.44, self.DISH_Z - self.CHUTE_LEAD)
        end = tuple(self.exit_local)
        rings: list[list[tuple[float, float, float]]] = []
        for step in range(self.CHUTE_STEPS + 1):
            t = step / self.CHUTE_STEPS
            centre = tuple(start[axis] + (end[axis] - start[axis]) * t for axis in range(3))
            half = self.CHUTE_HALF + (layout.CHANNEL_HALF - self.CHUTE_HALF) * t
            wall = self.CHUTE_WALL * _smoothstep(0.06, 0.34, t)
            ring = [
                _place(
                    self.origin,
                    self.frame,
                    (centre[0] - (half + 0.10), centre[1] + wall, centre[2]),
                )
            ]
            for column in range(9):
                across = -half + 2.0 * half * column / 8
                rise = (
                    layout.floor_y_at(min(abs(across), layout.CHANNEL_HALF)) - layout.FLOOR_Y
                )
                ring.append(
                    _place(
                        self.origin,
                        self.frame,
                        (centre[0] + across, centre[1] + rise, centre[2]),
                    )
                )
            ring.append(
                _place(
                    self.origin,
                    self.frame,
                    (centre[0] + half + 0.10, centre[1] + wall, centre[2]),
                )
            )
            rings.append(ring)
        return [_strip(rings, f"{self.id}_exit")]

    # --- the two gates ----------------------------------------------------

    def local_actuators(self) -> list[Actuator]:
        gates = list(super().local_actuators())
        if not self.port_gate:
            return gates
        from marble3d.modules.base import LinearGate

        for index in range(layout.BAYS):
            # **The paddle is the cup's inner wall.** The first build stood it
            # across the ring at the cup's counterclockwise end, on the
            # reasoning that a marble would run along the ring into it - and
            # traced in simulation, every marble arrived *radially* off its
            # chute, crossed the cup and left over the inner lip onto the dish.
            # A cup that does not close inward is not a cup. So the paddle
            # closes the one face the marble is actually travelling toward, and
            # lifting it releases the field down the dish.
            deg = self.port_angle(index) - 0.5 * self.CUP_ARC
            angle = math.radians(deg)
            point = self._ring_point(
                self.PORT_R - self.CUP_HALF,
                deg,
                self.port_floor - self.CUP_TILT + 0.5 * self.PORT_GATE_HEIGHT,
            )
            world = _place(self.origin, self.frame, point)
            # Thin along the radius, which is the axis the marble crosses it
            # on: `basis_from_forward_up` puts `forward` on local X and the
            # extents are read (thin, height, along the arc).
            radial = (math.cos(angle), 0.0, math.sin(angle))
            forward = tuple(
                self.frame[0][axis] * radial[0] + self.frame[2][axis] * radial[2]
                for axis in range(3)
            )
            gates.append(
                LinearGate(
                    name=f"port{index}",
                    half_extents=(
                        to_sim(0.05),
                        to_sim(0.5 * self.PORT_GATE_HEIGHT),
                        to_sim(self.PORT_R * math.radians(0.5 * self.CUP_ARC) + 0.08),
                    ),
                    rest=Transform(
                        position=world,
                        rotation=basis_from_forward_up(forward, self.frame[1]),
                    ),
                    travel=(0.0, to_sim(0.80), 0.0),
                    release_time=self.PORT_RELEASE,
                    duration=0.16,
                )
            )
        return gates

    # --- what the simulation needs ----------------------------------------

    def marble_starts(self) -> list[Transform]:
        """Eight resting places on the flat pan, outermost bay first.

        `StartGrid`'s version reads the fan's shrinking width factor; this
        shelf holds the drawn pitch until the gate, so the resting pitch is
        exactly `BAY_PITCH` - which is what the viewer sees.
        """
        rotation = self._rotation()
        starts: list[Transform] = []
        for index in range(layout.BAYS):
            field_z = self._field_z_for(index)
            t = self._t_at_z(field_z)
            centre = self._path_at(t)
            starts.append(
                Transform(
                    position=_place(
                        self.origin,
                        self.frame,
                        (
                            self.lane_x(index, t),
                            centre[1] - self.SHELF_PAN + MARBLE_RADIUS,
                            field_z,
                        ),
                    ),
                    rotation=rotation,
                )
            )
        return starts

    def local_sockets(self) -> dict[str, Socket]:
        exit_point = _place(self.origin, self.frame, self.exit_local)
        forward = tuple(float(v) for v in self.frame[2])
        return {
            "exit": Socket(
                name="exit",
                frame=Transform(
                    position=exit_point,
                    rotation=basis_from_forward_up(forward, (0.0, 1.0, 0.0)),
                ),
                kind=GUIDED,
                width=to_sim(2.0 * layout.CHANNEL_HALF),
                height=to_sim(0.62),
            )
        }

    def local_bounds(self) -> Aabb:
        bounds = self.local_colliders()[0].aabb()
        return Aabb(
            tuple(value - MARBLE_DIAMETER for value in bounds.lower),
            tuple(value + MARBLE_DIAMETER for value in bounds.upper),
        )

    def local_probes(self) -> list[Probe]:
        """Rays at the shelf, at every chute and around the dish.

        The cups and the ring paddles are skipped for the reason `StartGrid`
        skips its gate rows: a probe fired where a kinematic body stands
        measures the paddle and reports the floor as missing, and loosening the
        tolerance is what would make the rest of the check worthless.
        """
        probes: list[Probe] = []
        reach = 3.0 * MARBLE_RADIUS
        gate_rows = {
            int(round(self._t_at_z(self._gate_z_for(index)) * 12))
            for index in range(layout.BAYS)
        }
        for row in range(0, 13, 3):
            if any(abs(row - gate_row) <= 1 for gate_row in gate_rows):
                continue
            t = row / 12.0
            centre = self._path_at(t)
            for bay in (0, 3, 7):
                surface = _place(
                    self.origin,
                    self.frame,
                    (self.lane_x(bay, t), centre[1] - self.SHELF_PAN, centre[2]),
                )
                probes.append(
                    Probe(
                        start=(surface[0], surface[1] + reach, surface[2]),
                        end=(surface[0], surface[1] - reach, surface[2]),
                        expect_hit=True,
                        expected_point=surface,
                        tolerance=0.05,
                        label=f"{self.id}.shelf[{row}]bay{bay}",
                    )
                )
        for feeder in self.feeders():
            samples = feeder["samples"]
            for fraction in (0.25, 0.55, 0.82):
                order = int(fraction * (len(samples) - 1))
                point = samples[order]
                surface = _place(self.origin, self.frame, point)
                probes.append(
                    Probe(
                        start=(surface[0], surface[1] + reach, surface[2]),
                        end=(surface[0], surface[1] - reach, surface[2]),
                        expect_hit=True,
                        expected_point=surface,
                        tolerance=0.06,
                        label=f"{self.id}.chute{feeder['bay']}[{order}]",
                    )
                )
        outer = self.PORT_R - self.CUP_HALF
        radius = 0.5 * (self.DRAIN_R + outer)
        fraction = (radius - self.DRAIN_R) / max(outer - self.DRAIN_R, 1e-6)
        y = self.drain_lip + (self.dish_edge - self.drain_lip) * fraction
        for point in range(0, self.RINGS, 6):
            deg = 360.0 * point / self.RINGS
            surface = _place(self.origin, self.frame, self._ring_point(radius, deg, y))
            probes.append(
                Probe(
                    start=(surface[0], surface[1] + reach, surface[2]),
                    end=(surface[0], surface[1] - reach, surface[2]),
                    expect_hit=True,
                    expected_point=surface,
                    tolerance=0.05,
                    label=f"{self.id}.dish[{deg:.0f}]",
                )
            )
        return probes

    def describe(self) -> dict[str, Any]:
        table = feeder_table(self)
        return {
            "kind": "RadialStart",
            "bays": layout.BAYS,
            "bay_pitch": round(to_sim(layout.BAY_PITCH), 6),
            "fan_pitch": self.FAN_PITCH,
            "yaw_deg": round(self.yaw_deg, 4),
            "lift": START_LIFT,
            "port_radius": self.PORT_R,
            "port_angles": [round(self.port_angle(i), 2) for i in range(layout.BAYS)],
            "port_gate": self.port_gate,
            "port_release": self.PORT_RELEASE,
            "drain_radius": self.DRAIN_R,
            "release_time": self.release_time,
            "gate_z": round(self.gate_z, 4),
            "heights": {
                "shelf_floor": round(self.shelf_floor, 4),
                "port_floor": round(self.port_floor, 4),
                "dish_edge": round(self.dish_edge, 4),
                "drain_lip": round(self.drain_lip, 4),
                "exit_y": round(self.exit_local[1], 4),
            },
            "feeders": table["rows"],
            "feeder_spread": table["spread"],
        }


def _smoothstep(edge0: float, edge1: float, value: float) -> float:
    u = min(1.0, max(0.0, (value - edge0) / (edge1 - edge0)))
    return u * u * (3.0 - 2.0 * u)


def _steepest(samples) -> float:
    """The steepest pitch anywhere along a chute, in degrees.

    A constant-grade chute is described by one number; a shaped one is not, and
    what matters for reliability is the *worst* pitch rather than the mean.
    """
    worst = 0.0
    for index in range(len(samples) - 1):
        a, b = samples[index], samples[index + 1]
        run = math.hypot(b[0] - a[0], b[2] - a[2])
        if run < 1e-9:
            continue
        worst = max(worst, abs(a[1] - b[1]) / run)
    return math.degrees(math.atan(worst))


def _polyline_length(points) -> float:
    return sum(math.dist(points[i], points[i + 1]) for i in range(len(points) - 1))


def _smooth(controls, per_unit: int) -> list[tuple[float, float]]:
    """A Catmull-Rom through plan controls, sampled at a fixed density.

    At a density rather than a fixed count, so a short chute and a long one
    have the same facet size - which is a physics parameter and not a cosmetic
    one: the collider's sagitta is what the core is calibrated at.
    """
    if len(controls) < 2:
        return [tuple(controls[0])]
    pts = [tuple(controls[0])] + [tuple(p) for p in controls] + [tuple(controls[-1])]
    out: list[tuple[float, float]] = []
    for index in range(len(pts) - 3):
        p0, p1, p2, p3 = pts[index], pts[index + 1], pts[index + 2], pts[index + 3]
        steps = max(2, int(math.dist(p1, p2) * per_unit))
        for step in range(steps):
            t = step / steps
            t2, t3 = t * t, t * t * t
            out.append(
                tuple(
                    0.5
                    * (
                        2 * p1[axis]
                        + (-p0[axis] + p2[axis]) * t
                        + (2 * p0[axis] - 5 * p1[axis] + 4 * p2[axis] - p3[axis]) * t2
                        + (-p0[axis] + 3 * p1[axis] - 3 * p2[axis] + p3[axis]) * t3
                    )
                    for axis in range(2)
                )
            )
    out.append(tuple(pts[-1]))
    return out


def feeder_table(start: RadialStart) -> dict:
    """The per-bay chute measurement section 5 of the brief asks for.

    Length, drop, grade, the radius and the tangent each chute delivers at, and
    the rolling time down its own grade - which is what `PORT_RELEASE` has to
    clear. Reported rather than asserted: the chutes are not congruent, the
    spread is real, and the cups are the answer to it.
    """
    rows = []
    for feeder in start.feeders():
        grade = feeder["grade"]
        sin_theta = grade / math.hypot(1.0, grade)
        # A solid sphere rolling without slip accelerates at 5/7 g sin(theta).
        accel = (5.0 / 7.0) * 9.81 * sin_theta
        span = to_sim(feeder["plan_length"] * math.hypot(1.0, grade))
        seconds = math.sqrt(2.0 * span / accel) if accel > 1e-6 else float("inf")
        rows.append(
            {
                "bay": feeder["bay"],
                "slot": feeder["slot"],
                "port_deg": round(feeder["angle"], 2),
                "length": round(feeder["length"], 4),
                "drop": round(feeder["drop"], 4),
                "grade_deg": round(math.degrees(math.atan(grade)), 3),
                "steepest_deg": round(feeder["steepest_deg"], 3),
                "shape": feeder["shape"],
                "port_radius": round(start.PORT_R, 4),
                "entry_tangent_deg": round((feeder["angle"] + 90.0) % 360.0, 2),
                "fall_seconds": round(seconds, 4),
            }
        )
    lengths = [row["length"] for row in rows]
    drops = [row["drop"] for row in rows]
    radii = [row["port_radius"] for row in rows]
    falls = [row["fall_seconds"] for row in rows]
    return {
        "rows": rows,
        "spread": {
            "length": [round(min(lengths), 4), round(max(lengths), 4)],
            "length_spread": round(max(lengths) - min(lengths), 4),
            "drop_spread": round(max(drops) - min(drops), 6),
            "radius_spread": round(max(radii) - min(radii), 6),
            "fall_seconds": [round(min(falls), 4), round(max(falls), 4)],
            "release_margin": round(start.PORT_RELEASE - max(falls), 4),
        },
    }

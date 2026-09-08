"""The line-to-radial start: eight bays abreast, one shared apron, one ring.

## Why the topology changed, and what survived V1.4

`docs/sloped_race_v13_basin.md` measured one mechanism in two different start
topologies, and it is not a tuning problem:

    a single common exit orders the field by distance to that exit, and
    distance to the exit is a function of which bay a marble started in.

The taper orders the field at its throat and the basin orders it at its notch.
Twenty-four geometries inside that family have been falsified. What breaks the
mechanism is **equal distance from every bay to the exit**, which needs the
launch points arranged *about* the exit rather than beside it. That is the
radial architecture, and it is not what failed.

What failed was the transport. V1.4 ran eight independently walled chutes from
the shelf to the ring, and `docs/sloped_race_v14_radial.md` section 3 records
why they cannot fit: a walled chute needs clear width over a 0.57 racer plus a
wall each side, and eight of those cannot simultaneously satisfy clearance,
mutual separation, a grade above the stall threshold and a grade below a fall,
in the two units of plan available. Throughput was 41.7% of the field.

## What this builds

    eight bays abreast on a flat pan, one synchronised gate   <- unchanged, seen
      |
    ONE continuous apron: eight solved guide grooves with
    shallow ribs between them, and no walls                   <- the rewrite
      |
    an inward-tilted annular trough, closed inward by one
    gate ring in sixteen segments                             <- the fairness surface
      |
    one synchronised release
      |
    a wide central drain, rotationally symmetric
      |
    a chute onto the launch run

`sloped.apron` solves the guides and carries the reasoning for how. What
matters here is the ring, and one change from the V1.4 brief that has to be
argued rather than assumed.

## The ring is a trough, not eight pockets, and why

The brief asks to preserve "exact 45 degree radial port spacing", and the eight
delivery bearings still are exactly 22.5 + 45k. What is *not* preserved is the
eight separate walled cups, and the reason is measured rather than preferred.

A cup is a pocket in the ring, so a guide route may not pass over a foreign
cup: on one single-valued surface, passing over it means dropping into it. So
each route has to hold outside the ring's rim until it reaches its own sector,
and then descend 0.70 in radius inside its own 45 degrees. At the radius
available that is a turn of about 0.30 units, taken at 18 layout units per
second, and holding it needs a side slope of 83 degrees. No groove and no bank
supplies that. Measured across four parametrisations the number came out 0.25
to 0.32 every time, and it belongs to the route rather than to the curve
fitting: the constraint genuinely steps by 0.70 at the sector boundary.

A continuous trough removes the constraint instead of fighting it, and it
**strengthens** the fairness invariants rather than weakening them:

* every marble comes to rest against the same inward gate ring, so its radius
  from the drain is `PADDLE_R + MARBLE_RADIUS` **exactly**, for all eight,
  rather than "somewhere inside its own pocket";
* the floor it rests on is one height, exactly;
* the release is one motion of one ring;
* and everything below the trough is *rotationally* symmetric rather than
  eight-fold symmetric, so a marble's bearing round the ring - the one thing
  the trough does not control - stops mattering at all. The eight vanes V1.4
  needed are gone with the dish they stood in, and with them the last piece of
  geometry a marble could be lucky or unlucky about the orientation of.

The trough's floor tilts inward by `TROUGH_TILT`. A truly level annulus is
tempting - no azimuthal bias whatsoever - but a marble on a level floor has no
reason to settle against the ring in the first place and no reason to leave
when the ring lifts. A rotationally symmetric tilt costs no symmetry and buys
both.

## The height chain, derived and not typed

`rest_floor` -> `trough_floor` -> `paddle_floor` -> `drain_lip` -> the launch
entry. The basin's notes record what a typed chain costs: its feeders ended
0.18 below the dish's edge and the field stopped dead against the step.

`START_LIFT` is **3.40**, which is 0.90 *less* than the 4.30 the brief approved
for this experiment. The apron spends 1.70 where the chutes spent 2.20 and the
drain moved downhill, so the exit chute has less to make up: it runs at about
28 degrees rather than the 40 that 4.30 would have forced.
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
from sloped.apron import ApronGuides, bay_x
from sloped.scale import to_sim
from sloped.solids import merge_meshes, plate
from sloped.stations import StartGrid, _place, _strip
from sloped.track import TrackRun

__all__ = ["START_LIFT", "RadialStart", "guide_table"]

# How far the whole start module rises above its recorded node.
#
# The chain needs the pan to stand far enough over the launch entry for the
# apron's 1.70, the trough's fall and an exit chute that is a delivery rather
# than a drop. 3.40 leaves the exit at 28 degrees. The basin lifted 1.90 for
# the same reason and the brief allowed it as a local adjustment; V1.4's chutes
# needed 4.30, and this gives 0.90 of that back.
START_LIFT = 3.40


class RadialStart(StartGrid):
    """The eight bays and the gate of `StartGrid`, on a shared radial apron.

    Subclassed for the reason `StartBasin` is: the bays, the paddles, the
    release and the resting pitch carry three sessions of corrections - fin
    pinch, gate axis order, resting pitch - and none of them changes. What
    changes is everything downhill of the gate.
    """

    START_KIND = "radial"

    # --- the pan the field waits on --------------------------------------
    #
    # Flat *across*, which is a fairness correction and not a plumbing one: the
    # fan's trough was a dish, so its outer bays rested 0.10 layout units
    # higher than its inner ones - a systematic per-bay energy difference that
    # sat under three sessions of measurement without being noticed.
    PAN_BACK = -4.60
    PAN_SINK = 0.30                # how far the pan sits under the deck
    PAN_HALF = 2.86                # a little over the drawn pod's 2.73

    # --- the apron --------------------------------------------------------
    APRON_DROP = 1.70              # pan to trough rim, identical for all eight
    HEAD_GRADE = 8.7               # the drawn shelf's own grade, at the line
    LANE = 0.64                    # least separation between guide centrelines
    # **The groove is a circular cradle, and its radius is the constraint.**
    # The first build used a cosine rib 0.24 tall across a 0.63 lane, whose
    # curvature radius at the bottom is `W^2 / (2 R pi^2)` = 0.084 - smaller
    # than the 0.285 marble that has to sit in it. So the marble bridged the V
    # on two flanks instead of reaching the floor, and bay 0, which sits in the
    # tightest V of all with the kerb on its other side, was squeezed straight
    # through the surface: it fell 4.64 units, every seed. The basin's notes
    # record the same failure in a different shape and the same arithmetic.
    #
    # A 0.60 cradle across a 0.63 lane crests at 0.089. Shallow, and
    # deliberately so - section 6 of the brief asks for minimal guide strength,
    # and this is about all a groove can be given without closing on the
    # marble. It steers the release while the field is slow and lets it drift
    # on the fast bends, which the brief permits and the trough absorbs.
    CRADLE_R = 0.60
    # **And the crest is capped, which matters more than the cradle's radius.**
    # A cradle scaled to the strip's own width crests at half that width, and
    # the strips widen from 0.63 at the line to 1.34 at the ring - so the crest
    # rose along the flow, and a crest that rises along the flow is a
    # *transverse ridge*. Traced in simulation, both outer racers climbed 0.18
    # of it at 3.25 units from the drain and stopped there for eleven seconds.
    # The local-minimum check missed it because a ridge is not a basin: there
    # is always a way downhill sideways, just not forwards.
    #
    # Capped, the crest is one height everywhere and the middle of a wide strip
    # is a plateau instead. `cradle_rise(LANE / 2)` - the crest the narrowest
    # strip, the resting line's own, would have had.
    LANE_CREST = 0.0925
    LIP_Z = -0.95                  # where the visible pan becomes transport
    KERB_OUT = 0.42                # the outer boundary: containment, not a divider
    KERB_RISE = 0.78
    ROWS = 96                      # rows along the apron
    COLUMNS = 6                    # columns across one lane strip
    HEEL_ROWS = 8                  # rows behind the resting line; see `_lane_rows`

    # --- the ring ---------------------------------------------------------
    DISH_Z = 1.20                  # the drain, on the module's centreline
    TROUGH_R = 1.35                # the trough's mid radius
    TROUGH_HALF = 0.36
    TROUGH_TILT = 9.0              # degrees, inward; see the module docstring
    # **The trough's lip is a one-way valve, and it is needed.** Without it the
    # apron ran flush into the trough floor, and traced in simulation eight
    # racers arriving at 18 layout units per second knocked each other back
    # *out*: two of eight per seed ended up 1.5 units further out and 1.9
    # higher than the ring, so they would have been released from the wrong
    # radius entirely. A marble falls over a 0.20 step easily and has to climb
    # it, plus the apron's grade, to get back. Rotationally symmetric, so it
    # costs no fairness, and it is a feature of the ring rather than of the
    # apron - section 5's ban on elevation steps is about the guided surface.
    RIM_STEP = 0.32
    PADDLE_R = 1.02                # the gate ring, and so the resting radius
    PADDLE_THICK = 0.06
    PADDLE_HEIGHT = 0.62
    # Sixteen segments rather than eight. A box cannot be curved, so a
    # segmented ring is a polygon, and eight segments put a marble resting on a
    # flat 0.084 further from the drain than one resting against a vertex - an
    # azimuthal asymmetry in the one quantity the architecture exists to make
    # equal. Sixteen takes that to 0.021, under a tenth of a marble's radius.
    PADDLE_SEGMENTS = 16
    DRAIN_R = 0.95
    DRAIN_FALL = 0.46              # trough floor at the drain, down to its lip
    # The catch over the drain's own sector: see `_catch`. It stops short of
    # the launch entry at z 3.94 and clears the exit chute's walls by about a
    # unit, both of which `tools/sloped_radial_check.py` measures.
    CATCH_FROM = 63.0
    CATCH_TO = 117.0
    CATCH_R = 2.30
    CATCH_RISE = 0.80
    RINGS = 64                     # points around the trough

    # --- the exit ---------------------------------------------------------
    CHUTE_HALF = 0.80
    CHUTE_WALL = 0.58
    CHUTE_LEAD = 0.20
    CHUTE_STEPS = 14

    # One synchronised release of the whole ring, in seconds, on the same clock
    # as the start gate's own 0.30.
    #
    # **Set from the measured seating time, not from the rolling time.** The
    # slowest guide delivers its marble in about 2.3 seconds, but a marble that
    # has reached the trough still has to find a bearing of its own among
    # seven others and stop moving; over twelve seeds
    # `tools/sloped_radial_trace.py` measured the whole field seated between
    # 2.20 and 4.87 seconds. Releasing on the rolling time would release a
    # field that is still circulating, which is the one thing the ring exists
    # to prevent. `tools/sloped_radial_check.py` asserts the margin.
    RELEASE = 5.60
    RELEASE_DURATION = 0.18
    PORT_GATE = True

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
        self._mesh: TriMesh | None = None
        self._guides: ApronGuides | None = None
        self.gate_z = self._field_z() + layout.MARBLE_RADIUS + 0.06

    # --- what the bays stand on ------------------------------------------

    def _field_z(self) -> float:
        return self.PAN_BACK + 0.66

    def _cradle(self, across: float, half: float, t: float = 0.0) -> float:
        """Flat. The fairness change, not the plumbing one - see the docstring."""
        return -self.PAN_SINK

    # --- the height chain -------------------------------------------------

    @property
    def rest_floor(self) -> float:
        """What a marble rests on at the line, and where a guide starts."""
        return layout.DECK_TOP - 0.02 - self.PAN_SINK

    @property
    def trough_floor(self) -> float:
        """The trough's floor at its outer rim. One height for all eight."""
        return self.rest_floor - self.APRON_DROP

    @property
    def rest_radius(self) -> float:
        """Where a marble comes to rest: touching the gate ring, exactly."""
        return self.PADDLE_R + layout.MARBLE_RADIUS

    @property
    def paddle_floor(self) -> float:
        """The floor a marble actually rests on, against the gate ring.

        The trough tilts inward, so the floor at the resting radius is lower
        than at the rim, and it is this height - not the rim's - that is common
        to all eight racers. Derived rather than typed, for the reason the
        basin's notes give.
        """
        return self.trough_y(self.rest_radius)

    def trough_drop_to(self, radius: float) -> float:
        """How far the trough floor has fallen at `radius`, from its rim."""
        rim = self.TROUGH_R + self.TROUGH_HALF
        return max(rim - radius, 0.0) * math.tan(math.radians(self.TROUGH_TILT))

    def trough_y(self, radius: float) -> float:
        """The trough's floor at `radius`, below the apron's own inner edge."""
        return (self.trough_floor - self.RIM_STEP
                - self.trough_drop_to(max(radius, self.DRAIN_R)))

    @property
    def drain_lip(self) -> float:
        return self.trough_y(self.DRAIN_R) - self.DRAIN_FALL

    # --- the guides -------------------------------------------------------

    def guides(self) -> ApronGuides:
        if self._guides is None:
            self._guides = ApronGuides(
                field_z=self._field_z(),
                rest_hold=self.gate_z - self._field_z() + 0.12,
                dish_z=self.DISH_Z,
                trough_r=self.TROUGH_R,
                trough_half=self.TROUGH_HALF,
                drop=self.APRON_DROP,
                lip_z=self.LIP_Z,
                head_grade=self.HEAD_GRADE,
                lane=self.LANE,
                shelf_half=self.PAN_HALF - 0.20,
            )
        return self._guides

    def guide_point(self, index: int, fraction: float) -> tuple[float, float, float]:
        """The guide's floor at `fraction` along it, in the module's frame."""
        guides = self.guides()
        path = guides.paths()[index]
        step = max(0.0, min(1.0, fraction)) * (len(path) - 1)
        low = max(0, min(len(path) - 2, int(step)))
        t = step - low
        x = path[low][0] + (path[low + 1][0] - path[low][0]) * t
        z = path[low][1] + (path[low + 1][1] - path[low][1]) * t
        return (x, self.rest_floor - guides.fall(index, fraction), z)

    # --- the collider -----------------------------------------------------

    def local_colliders(self) -> list[TriMesh]:
        if self._mesh is not None:
            return [self._mesh]
        pieces: list[TriMesh] = []
        pieces.extend(self._apron())
        pieces.extend(self._catch())
        pieces.extend(self._trough())
        pieces.extend(self._exit_chute())
        self._mesh = merge_meshes(pieces, f"{self.id}_radial")
        return [self._mesh]

    def _lane_rows(self) -> list[list[tuple[float, float, float]]]:
        """Each guide sampled at a common parameter, in the module's frame.

        A common *parameter* rather than a common arc length: the eight guides
        are 3.6 to 7.9 long, and the apron between two of them is the strip
        swept between their whole extents. Both endpoints of every guide are
        common - the resting line and the trough's rim - so a common parameter
        closes the strips cleanly at both ends.

        **The heel matters as much as the rest of it.** A guide begins at its
        bay's resting place, so an apron built from the guides alone begins
        there too - and the drawn pod's floor runs 0.66 further back, behind
        the field. Built without the heel there was simply no surface there,
        and traced in simulation the release itself put marbles into the hole:
        eight racers 0.63 apart in 0.089-deep grooves jostle when the gate
        lifts, one gets pushed backwards, and it falls 4.6 units. Four of eight
        went that way on the first seed. Single marbles never showed it, which
        is exactly what step C of the brief's validation order is for.
        """
        rows = []
        heel = self.HEEL_ROWS
        grade = math.tan(math.radians(self.HEAD_GRADE))
        for index in range(layout.BAYS):
            lane = []
            for row in range(heel):
                # Behind the line, on the same grade, so the resting marble is
                # on a slope and rolls into the gate rather than sitting level.
                z = self.PAN_BACK + (self._field_z() - self.PAN_BACK) * row / heel
                lane.append((bay_x(index),
                             self.rest_floor + (self._field_z() - z) * grade, z))
            lane.extend(self.guide_point(index, row / self.ROWS)
                        for row in range(self.ROWS + 1))
            rows.append(lane)
        return rows

    def _apron(self) -> list[TriMesh]:
        """One surface: seven lane strips, two kerbs and a backstop.

        Cross-strip interpolation is **polar about the drain**, not a straight
        chord. Near the ring a strip spans 45 degrees of a 1.71 radius, and a
        chord there cuts 0.065 inside the rim - a step at exactly the place the
        field is delivered. Upstream, where the guides are nearly parallel and
        five units from the drain, polar and linear agree to a hundredth.

        The strips run 0-1 through 6-7 and deliberately **not** 7-0: the sheet
        is a 315-degree annulus, and the 45 degrees it does not cover is where
        the drain and the exit chute are.
        """
        lanes = self._lane_rows()
        pieces: list[TriMesh] = []
        for index in range(layout.BAYS - 1):
            rings: list[list[tuple[float, float, float]]] = []
            for row in range(len(lanes[index])):
                inner, outer = lanes[index][row], lanes[index + 1][row]
                rings.append([
                    _place(self.origin, self.frame,
                           self._between(inner, outer, column / self.COLUMNS))
                    for column in range(self.COLUMNS + 1)
                ])
            pieces.append(_strip(rings, f"{self.id}_lane{index}"))
        for side, index in ((-1.0, 0), (1.0, layout.BAYS - 1)):
            pieces.append(self._kerb(lanes, index, side))
        pieces.append(self._backstop())
        return pieces

    def _between(self, a, b, t: float) -> tuple[float, float, float]:
        """A point across a lane strip: polar in plan, with the rib on top."""
        ra = math.hypot(a[0], a[2] - self.DISH_Z)
        rb = math.hypot(b[0], b[2] - self.DISH_Z)
        pa = math.atan2(a[2] - self.DISH_Z, a[0])
        pb = math.atan2(b[2] - self.DISH_Z, b[0])
        # Shortest way round, so a strip never wraps the long way.
        span = (pb - pa + math.pi) % (2.0 * math.pi) - math.pi
        radius = ra + (rb - ra) * t
        angle = pa + span * t
        blend = t * t * (3.0 - 2.0 * t)
        # Two circular cradles, one centred on each guide, meeting at the
        # crest. A cradle rather than a bump because the marble has to be able
        # to reach the bottom of it - see `CRADLE_R`.
        height = a[1] + (b[1] - a[1]) * blend
        width = math.hypot(a[0] - b[0], a[2] - b[2])
        height += min(self._cradle_rise(t * width),
                      self._cradle_rise((1.0 - t) * width),
                      self.LANE_CREST)
        return (radius * math.cos(angle), height,
                self.DISH_Z + radius * math.sin(angle))

    def _cradle_rise(self, across: float) -> float:
        """How far a circular cradle of radius `CRADLE_R` rises at `across`."""
        radius = self.CRADLE_R
        span = min(abs(across), radius)
        return radius - math.sqrt(max(radius * radius - span * span, 0.0))

    def _kerb(self, lanes, index: int, side: float) -> TriMesh:
        """The apron's outer boundary, outboard of the outermost guide.

        **It is a floor that rises, not a wall standing off at a distance.**
        The first version offset a wall 0.30 outboard and left no surface in
        between, so the marble resting exactly on guide 0 had floor under its
        inboard half and a 0.30 hole under its outboard half; traced in
        simulation it wedged 0.057 high against the wall's foot and never moved
        at all, for the whole run, every seed.

        So the section is the rib's own shape, mirrored: zero cross-slope at
        the guide, rising to `KERB_RISE` at `KERB_OUT`. The outermost lane then
        has a symmetric groove like every other lane, and the boundary is
        containment rather than a kerb to trip over.

        Offset along the guide's own plan normal rather than radially, because
        near the resting line the guides run downhill and a radial offset there
        points along them rather than across.
        """
        path = lanes[index]
        columns = 4
        rings: list[list[tuple[float, float, float]]] = []
        for row in range(len(path)):
            behind = path[max(row - 1, 0)]
            ahead = path[min(row + 1, len(path) - 1)]
            dx, dz = ahead[0] - behind[0], ahead[2] - behind[2]
            span = math.hypot(dx, dz) or 1.0
            nx, nz = side * dz / span, -side * dx / span
            ring = []
            for column in range(columns + 1):
                t = column / columns
                # The cradle's own flank for the first stretch, so the marble
                # in the outermost lane sits in the same shape as every other,
                # then on up to `KERB_RISE`.
                rise = min(self._cradle_rise(t * self.KERB_OUT), self.LANE_CREST)
                rise += max(0.0, self.KERB_RISE - self.LANE_CREST) * (t ** 3)
                ring.append(_place(self.origin, self.frame, (
                    path[row][0] + nx * self.KERB_OUT * t,
                    path[row][1] + rise,
                    path[row][2] + nz * self.KERB_OUT * t,
                )))
            rings.append(ring if side > 0 else list(reversed(ring)))
        return _strip(rings, f"{self.id}_kerb{index}")

    def _backstop(self) -> TriMesh:
        floor = self.rest_floor
        corners = [
            (-self.PAN_HALF, floor, self.PAN_BACK),
            (self.PAN_HALF, floor, self.PAN_BACK),
            (self.PAN_HALF, floor + 0.42, self.PAN_BACK),
            (-self.PAN_HALF, floor + 0.42, self.PAN_BACK),
        ]
        return plate([_place(self.origin, self.frame, p) for p in corners],
                     name=f"{self.id}_backstop", steps=5)

    def _catch(self) -> list[TriMesh]:
        """The apron's slit, closed - over the exit chute, under nothing.

        The apron is a 315-degree annulus and the 45 degrees it does not cover
        is the sector the drain empties through. **That sector was an open hole
        at apron level, and the two outermost guides deliver at its two
        edges.** Traced in simulation, bay 0 reached the trough and was then
        knocked straight out through it: it ended 3.9 units from the drain and
        4.7 below the pan, every seed once the field was eight.

        So the sector gets a floor at the apron's own inner-edge height, rising
        outward into a catch wall, and an overshooting racer is returned to the
        trough instead of leaving the machine. It sits a clear unit above the
        exit chute's own walls and stops short of the launch entry.

        The wall is steeper than the apron is elsewhere, which is an azimuthal
        asymmetry - and it costs nothing, because the field comes to rest
        against the gate ring at 1.305 and the surround begins at 1.71.
        """
        rim = self.TROUGH_R + self.TROUGH_HALF
        rings: list[list[tuple[float, float, float]]] = []
        steps = 6
        for step in range(steps + 1):
            t = step / steps
            radius = rim + (self.CATCH_R - rim) * t
            y = self.trough_floor + self.CATCH_RISE * t * t
            rings.append([
                _place(self.origin, self.frame,
                       self._ring_point(radius, self.CATCH_FROM
                                        + (self.CATCH_TO - self.CATCH_FROM) * p / 24,
                                        y))
                for p in range(25)
            ])
        return [_strip(rings, f"{self.id}_catch")]

    def _trough(self) -> list[TriMesh]:
        """The annular holding floor, from the rim in to the drain's lip.

        Rotationally symmetric, and that is the point: the trough does not
        control where round the ring a marble comes to rest, so nothing below
        it may care. V1.4's dish had eight vanes and therefore eight
        orientations to be lucky about; this has none.
        """
        rim = self.TROUGH_R + self.TROUGH_HALF
        rings: list[list[tuple[float, float, float]]] = []
        # The lip: the apron's inner edge, then straight down `RIM_STEP`.
        rings.append([
            _place(self.origin, self.frame,
                   self._ring_point(rim, 360.0 * p / self.RINGS, self.trough_floor))
            for p in range(self.RINGS + 1)
        ])
        steps = 8
        for step in range(steps + 1):
            radius = rim - (rim - self.DRAIN_R) * step / steps
            y = self.trough_y(radius)
            rings.append([
                _place(self.origin, self.frame,
                       self._ring_point(radius, 360.0 * p / self.RINGS, y))
                for p in range(self.RINGS + 1)
            ])
        # And the lip of the drain, dropping away under the gate ring.
        rings.append([
            _place(self.origin, self.frame,
                   self._ring_point(self.DRAIN_R, 360.0 * p / self.RINGS,
                                    self.trough_y(self.DRAIN_R) - 0.12))
            for p in range(self.RINGS + 1)
        ])
        return [_strip(rings, f"{self.id}_trough")]

    def _ring_point(self, radius: float, deg: float, y: float):
        angle = math.radians(deg)
        return (radius * math.cos(angle), y, self.DISH_Z + radius * math.sin(angle))

    def _exit_chute(self) -> list[TriMesh]:
        """From under the drain to the launch run's entry.

        Wider than the hole and starting upstream of it, which the basin's
        notes record the cost of getting wrong: a chute narrower than the drain
        and starting at the drain's own centre lost seven of eight marbles over
        its edges, every trial.

        **The chute has to start well below the drain and grow its walls
        afterwards.** At `drain_lip - 0.05` with full walls from its first ring
        the walls stood 0.46 *above* the inner floor - they came up through the
        hole and made a slot - and traced in simulation the field wedged in it
        and the whole start froze. A chute under a drain is a landing, and a
        landing has no kerb.
        """
        start = (0.0, self.drain_lip - 0.30, self.DISH_Z - self.CHUTE_LEAD)
        end = tuple(self.exit_local)
        rings: list[list[tuple[float, float, float]]] = []
        for step in range(self.CHUTE_STEPS + 1):
            t = step / self.CHUTE_STEPS
            centre = tuple(start[axis] + (end[axis] - start[axis]) * t for axis in range(3))
            half = self.CHUTE_HALF + (layout.CHANNEL_HALF - self.CHUTE_HALF) * t
            wall = self.CHUTE_WALL * _smoothstep(0.06, 0.34, t)
            ring = [_place(self.origin, self.frame,
                           (centre[0] - (half + 0.10), centre[1] + wall, centre[2]))]
            for column in range(9):
                across = -half + 2.0 * half * column / 8
                rise = (layout.floor_y_at(min(abs(across), layout.CHANNEL_HALF))
                        - layout.FLOOR_Y)
                ring.append(_place(self.origin, self.frame,
                                   (centre[0] + across, centre[1] + rise, centre[2])))
            ring.append(_place(self.origin, self.frame,
                               (centre[0] + half + 0.10, centre[1] + wall, centre[2])))
            rings.append(ring)
        return [_strip(rings, f"{self.id}_exit")]

    # --- the two gates ----------------------------------------------------

    def local_actuators(self) -> list[Actuator]:
        """The eight release paddles, and the ring.

        **The paddles are placed here rather than inherited, and that was a
        bug worth the whole diagnosis it took.** `StartGrid.local_actuators`
        reads `_t_at_z`, `_half_at` and `_path_at` to find each bay's gate, and
        those describe the *fan's* trough. This module does not have one, so
        the inherited builder placed eight paddles by a geometry that no longer
        exists - clamped to the fan's back edge, spread by the fan's own width
        factor, at the fan's height. They stood on the apron, downhill of the
        field, and bay 7's racer ran into one at 3.45 units from the drain and
        stopped there for the remaining eleven seconds. Bay 0's cleared its own
        by a hair and went on, which is why the failure looked like a
        left-right asymmetry in a geometry that is exactly mirror-symmetric.

        Placed from the pan's own numbers, a paddle stands at its bay's x, at
        the gate line, on the guide's own floor there.
        """
        from marble3d.modules.base import LinearGate

        gates: list[Actuator] = []
        guides = self.guides()
        for index in range(layout.BAYS):
            gate_z = self._gate_z_for(index)
            # The guides run straight down their bay's x for the first stretch
            # (`ApronGuides` pins that, so the resting field is abreast), so
            # the arc from the resting place to the gate line is exactly the
            # distance between them.
            fraction = (gate_z - self._field_z_for(index)) / guides.length(index)
            floor = self.rest_floor - guides.fall(index, fraction)
            position = _place(
                self.origin,
                self.frame,
                (bay_x(index), floor + 0.5 * layout.GATE_HEIGHT, gate_z),
            )
            gates.append(
                LinearGate(
                    name=f"paddle{index}",
                    # (thin along the flow, up, across). `basis_from_forward_up`
                    # puts `forward` on local X, and `_rotation` passes the flow
                    # direction - see `StartGrid.local_actuators` for the cost
                    # of reading that the other way round.
                    half_extents=(
                        to_sim(0.045),
                        to_sim(0.5 * layout.GATE_HEIGHT),
                        to_sim(0.5 * (layout.BAY_PITCH - 0.12)),
                    ),
                    rest=Transform(position=position, rotation=self._rotation()),
                    travel=(0.0, to_sim(self.release_travel), 0.0),
                    release_time=self.release_time,
                    duration=0.16,
                )
            )
        if not self.port_gate:
            return gates

        count = self.PADDLE_SEGMENTS
        for index in range(count):
            deg = 360.0 * (index + 0.5) / count
            angle = math.radians(deg)
            # The ring's inner face stands at `PADDLE_R`, so a marble comes to
            # rest with its centre at `PADDLE_R + MARBLE_RADIUS` - the same
            # radius from the drain, exactly, for all eight racers. That is the
            # invariant the whole architecture exists to establish, and here it
            # is one number rather than eight pockets' worth of tolerance.
            # Centred so the ring's *outer* face stands at `PADDLE_R`: the
            # marble arrives from outside and rests against that face, so it is
            # the outer one that sets the resting radius. Centring on
            # `PADDLE_R` instead put the field at 1.427 where `rest_radius`
            # claimed 1.305 - the invariant was still exact, but the number
            # documenting it was wrong by half a marble.
            point = self._ring_point(
                self.PADDLE_R - self.PADDLE_THICK, deg,
                self.trough_y(self.PADDLE_R) + 0.5 * self.PADDLE_HEIGHT,
            )
            world = _place(self.origin, self.frame, point)
            radial = (math.cos(angle), 0.0, math.sin(angle))
            forward = tuple(
                self.frame[0][axis] * radial[0] + self.frame[2][axis] * radial[2]
                for axis in range(3)
            )
            gates.append(
                LinearGate(
                    name=f"port{index}",
                    half_extents=(
                        to_sim(self.PADDLE_THICK),
                        to_sim(0.5 * self.PADDLE_HEIGHT),
                        to_sim(self.PADDLE_R * math.tan(math.pi / count) + 0.05),
                    ),
                    rest=Transform(
                        position=world,
                        rotation=basis_from_forward_up(forward, self.frame[1]),
                    ),
                    travel=(0.0, to_sim(0.90), 0.0),
                    release_time=self.RELEASE,
                    duration=self.RELEASE_DURATION,
                )
            )
        return gates

    # --- what the simulation needs ----------------------------------------

    def marble_starts(self) -> list[Transform]:
        """Eight resting places on the flat pan, at the drawn bay pitch."""
        rotation = self._rotation()
        return [
            Transform(
                position=_place(
                    self.origin,
                    self.frame,
                    (bay_x(index), self.rest_floor + MARBLE_RADIUS,
                     self._field_z_for(index)),
                ),
                rotation=rotation,
            )
            for index in range(layout.BAYS)
        ]

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
        """Rays down every guide, and round the trough.

        The gate ring is skipped for the reason `StartGrid` skips its gate
        rows: a probe fired where a kinematic body stands measures the paddle
        and reports the floor as missing, and loosening the tolerance is what
        would make the rest of the check worthless.
        """
        probes: list[Probe] = []
        reach = 3.0 * MARBLE_RADIUS
        gate_at = (self.gate_z - self._field_z()) / max(self.guides().length(0), 1e-6)
        for index in range(layout.BAYS):
            for fraction in (0.02, 0.18, 0.36, 0.54, 0.72, 0.88, 0.97):
                if abs(fraction - gate_at) < 0.04:
                    continue
                surface = _place(self.origin, self.frame,
                                 self.guide_point(index, fraction))
                probes.append(
                    Probe(
                        start=(surface[0], surface[1] + reach, surface[2]),
                        end=(surface[0], surface[1] - reach, surface[2]),
                        expect_hit=True,
                        expected_point=surface,
                        tolerance=0.06,
                        label=f"{self.id}.guide{index}[{fraction:.2f}]",
                    )
                )
        radius = 0.5 * (self.TROUGH_R + self.TROUGH_HALF + self.rest_radius)
        for point in range(0, self.RINGS, 8):
            deg = 360.0 * point / self.RINGS
            surface = _place(self.origin, self.frame,
                             self._ring_point(radius, deg, self.trough_y(radius)))
            probes.append(
                Probe(
                    start=(surface[0], surface[1] + reach, surface[2]),
                    end=(surface[0], surface[1] - reach, surface[2]),
                    expect_hit=True,
                    expected_point=surface,
                    tolerance=0.05,
                    label=f"{self.id}.trough[{deg:.0f}]",
                )
            )
        return probes

    def describe(self) -> dict[str, Any]:
        table = guide_table(self)
        return {
            "kind": "RadialStart",
            "start_kind": self.START_KIND,
            "bays": layout.BAYS,
            "bay_pitch": round(to_sim(layout.BAY_PITCH), 6),
            "yaw_deg": round(self.yaw_deg, 4),
            "lift": START_LIFT,
            "apron_drop": self.APRON_DROP,
            "trough_radius": self.TROUGH_R,
            "rest_radius": round(self.rest_radius, 6),
            "delivery_bearings": [round(self.guides().bearing(i), 2)
                                  for i in range(layout.BAYS)],
            "port_gate": self.port_gate,
            "release": self.RELEASE,
            "paddle_segments": self.PADDLE_SEGMENTS,
            "drain_radius": self.DRAIN_R,
            "release_time": self.release_time,
            "gate_z": round(self.gate_z, 4),
            "heights": {
                "rest_floor": round(self.rest_floor, 4),
                "trough_floor": round(self.trough_floor, 4),
                "paddle_floor": round(self.paddle_floor, 4),
                "drain_lip": round(self.drain_lip, 4),
                "exit_y": round(self.exit_local[1], 4),
            },
            "guides": table["rows"],
            "spread": table["spread"],
        }


def _smoothstep(edge0: float, edge1: float, value: float) -> float:
    u = min(1.0, max(0.0, (value - edge0) / (edge1 - edge0)))
    return u * u * (3.0 - 2.0 * u)


def guide_table(start: RadialStart) -> dict:
    """The per-bay guide measurement section 4 of the V1.4 brief asks for.

    Length, drop, mean and extreme local grade, entry and delivery tangents,
    and the rolling time down the guide - which is what `RELEASE` has to clear.
    The lengths are not equal and cannot be: eight collinear bays cannot be
    mapped onto a circle by congruent curves. What *is* equal, exactly, is the
    drop and the radius the field comes to rest at, and those are the two the
    fairness argument uses. The residual spread is reported, not hidden.
    """
    table = start.guides().table()
    for row in table["rows"]:
        # A solid sphere rolling without slip down the guide's own mean grade.
        grade = math.tan(math.radians(row["mean_grade_deg"]))
        accel = (5.0 / 7.0) * 9.81 * grade / math.hypot(1.0, grade)
        span = to_sim(row["length"] * math.hypot(1.0, grade))
        row["roll_seconds"] = round(
            math.sqrt(2.0 * span / accel) if accel > 1e-6 else float("inf"), 4)
    falls = [row["roll_seconds"] for row in table["rows"]]
    table["spread"] = {
        "length": table["length"],
        "length_spread": table["length_spread"],
        "length_ratio": table["length_ratio"],
        "drop_spread": table["drop_spread"],
        "delivery_radius_spread": table["delivery_radius_spread"],
        "rest_radius": round(start.rest_radius, 6),
        "grade": table["grade"],
        "mean_grade": table["mean_grade"],
        "groove_margin": table["groove_margin"],
        "bank_needed_deg": table["bank_needed_deg"],
        "worst_lane_pair": table["worst_lane_pair"],
        "worst_delivery_gap": table["worst_delivery_gap"],
        "trough_rim_slack": table["trough_rim_slack"],
        "apron_width": table["apron_width"],
        "roll_seconds": [round(min(falls), 4), round(max(falls), 4)],
        "release_margin": round(start.RELEASE - max(falls), 4),
    }
    return table

"""The full-floor release: the chamber's whole floor opens at once.

## What this replaces, and the measurement that asked for it

V1.7 built the rotor chamber and emptied it through a central outlet. It did
not jam, it improved slot fairness by about half, and it failed the throughput
gate at 88.93% - about a tenth of the field was never released. Its two trade
curves both bought the throughput back by spending the fairness, and the
mechanism was stated as a general one:

> The chamber destroys the bay-to-position map while the exit is shut. But
> *delivering* the field to the exit requires a rule that reads where each
> marble is - a gradient, or a sweep - and the field's positions still carry
> whatever the mixing left of the bay. The better the delivery rule, the more
> of that residue it reads back out.

"Which marble is nearest the outlet?" is that rule, and it is a selection. So
this removes it. There is no outlet, no gradient and no sweep: the floor the
whole field is standing on stops being there.

    eight bays abreast on a flat pan, one synchronised gate   <- unchanged, seen
      |  a short apron, which may taper
    a circular chamber 5.40 across, its floor FLAT and LEVEL
      |  four paddles, held still until the field is in, then 2.39 turns
      |  the rotor stops; the field settles
    SIX FLOOR SLATS ROTATE DOWN TOGETHER, on one global clock
      |  every racer loses support at the same tick, wherever it stands
    a broad receiving dish, 6.10 across, sloping to a spillway notch
      |
    a short chute onto the launch run

Three things follow from the release no longer reading position, and each is a
simplification rather than a cost:

* **the chamber floor is flat and level.** V1.7 needed 7 degrees of inward cone
  to persuade the field toward its hole, and measured that a floor steep enough
  to deliver was a floor that packed the field against the closed outlet where
  the paddles could not get between them - at 15 degrees the centre-versus-rank
  correlation climbed to +0.643, the shipped taper's own bias, recreated by the
  very gradient meant to serve the outlet. With no hole to serve, the gradient
  goes, and with it that whole failure mode.
* **the rotor's blade clearance is constant.** A box at one height over a cone
  clears 0.03 at its tip and 0.208 at its root; over a level floor it clears
  0.03 everywhere.
* **the free radial travel is the whole disc.** V1.7 had to size the outlet and
  the wall together to keep two marble diameters of radial freedom either side
  of a gate ring. There is no ring.

## Why a louvre, and why it is the only shape that qualifies

Section 5 of the brief requires that the actuator timing depend on the tick and
the configuration and on nothing else, and section 4 that every marble lose
support at essentially the same time *regardless of where it sits*. Those are
different requirements and the second is the harder one: a panel that slides
out from under the field uncovers the floor progressively from one side, so its
*timing* is global while its *effect* is a position-dependent sweep - which is
the selection this whole exercise removes.

A rotating slat has no such direction. Every slat tilts about its own axis at
the same instant, so the support under every square unit of floor starts to go
at the same tick. That is the property, and it is why this is a louvre rather
than a shutter, an iris or a pair of doors.

Each slat is a chord of the chamber running across the module's x, hinged along
its upstream edge, sweeping 90 degrees down toward the chute.

**The seam two neighbours leave is `pitch - thickness`, not `pitch`, and that
one term set the slat count.** A slat of width `w` and thickness `t` rotated by
an angle has a horizontal footprint of `(t/2) sin + (w/2) cos` about a centre
at `offset * cos`, so with `w == pitch` the clear gap works out as

    gap(angle) = pitch * (1 - cos angle) - thickness * sin angle       to 90 deg
    gap(angle) = pitch * (1 + cos angle) - thickness * sin angle       past it

which peaks at 90 degrees, at `pitch - thickness`. **Sweeping further does not
help**: past 90 the slat folds back over its own hinge, the hinge edge becomes
its downstream extreme and the seam closes again. That was tried at 120 degrees
and measured at 0.299 - `tools/sloped_floor_check.py` walking the real box
corners caught it, against a closed form in this docstring that had the sign of
the fold wrong.

So the count follows from the seam a marble has to pass through freely, which
is 1.25 diameters or 0.713:

    slats   pitch   seam = pitch - t   diameters
      8     0.675       0.575            1.01     a marble rubs both sides
      7     0.771       0.671            1.18     inside the band it can be held in
      6     0.900       0.800            1.40     passes freely
      5     1.080       0.980            1.72     and 0.18 more well depth

Six. And the seam **opens monotonically over the whole sweep** from the angle at
which a marble could first enter it, which is the property that makes a moving
gap safe: below that angle no marble can get in, above it the gap only widens.
That is the earlier wheel's scissor avoided by construction rather than tuning.

Hinged along its **upstream edge** rather than its centreline, nothing rises. A
centreline hinge halves the depth needed and lifts the far edge of every slat
0.45 into the chamber as it goes, which is a paddle under a marble that has not
fallen yet. The cost of the edge hinge is one pitch of well depth.

And the well is a pitch **plus a marble**, because at 90 degrees the slats do
not go away - they hang, as six vertical plates at their own hinge lines, in
the space between the chamber floor and the dish. A marble resting on the dish
stands 0.57 tall into that space. Clearing the dish surface is not clearing the
marble on it, and the difference was six of fifteen stage-A traces landing
cleanly and then rolling along a slat's face for the rest of the run. See
`PANEL_CLEAR`.

## Why the receiving dish is the basin's shape

Section 7 asks for a broad catch that does not drop eight marbles into a
one-marble throat. `sloped.basin` already contains a measured answer to
exactly that at exactly this scale - a stadium dish 5.5 across that "drains all
eight marbles, every seed, with no jam" - and three of its findings are
load-bearing here:

* **conical, not quadratic.** A dish that is level at its drain has a flat spot,
  and with `surface_friction` at 0.50 a pile on a level floor is statically
  stable. A constant slope has no flat spot anywhere.
* **the drain is a notch in the downstream rim, not a hole in the middle.** A
  hole needs a throat, a tunnel and a roof, and each was a defect in turn.
* **the rim is emitted as runs and broken at the openings.** Run the whole way
  round and it stands as a wall across the very place the field has to leave.

What is new is that this dish is fed from *above* rather than from an upstream
ramp, so it needs no open upstream edge and its whole rim can carry a guard.

Everything is in layout units, in the start module's own frame.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

from marble3d.geometry import Transform, basis_from_forward_up
from marble3d.mesh import TriMesh
from marble3d.modules.base import Actuator, Probe
from marble3d.units import MARBLE_RADIUS

from sloped import layout
from sloped.scale import SIM_TO_LAYOUT, to_sim
from sloped.shuffle import ShuffleChamber
from sloped.solids import merge_meshes
from sloped.stations import _place, _strip
from sloped.track import TrackRun

__all__ = [
    "FloorPanel",
    "ShuffleFloor",
    "floor_table",
    "panels_by_index",
    "seam_gap",
]


class FloorPanel(Actuator):
    """One louvre slat: a box that rotates once about a fixed hinge line.

    The pose is a pure function of the tick, which is section 5's requirement
    and the reason a physical trapdoor can be in a replay at all. The angle is
    a smoothstep from zero to `sweep` between `release_time` and
    `release_time + duration`, clamped at both ends, so `pose_at` is defined
    and constant for every tick before the release and every tick after it.

    Nothing here reads a marble position, a marble id, a bay or a rank. The
    only inputs are the tick and the numbers fixed at construction, and every
    panel of a floor is given the same two times.

    `hinge` is a point on the axis and `axis` its direction; `across` and `up`
    are the two perpendiculars at rest, and `offset` is how far the box's
    centre sits from the axis along `across`. Several boxes sharing one hinge
    are one rigid panel - which is how a slat approximates the chord of a
    circle without a rectangle's corners standing outside the wall.
    """

    def __init__(
        self,
        name: str,
        half_extents: Sequence[float],
        hinge: Sequence[float],
        axis: Sequence[float],
        across: Sequence[float],
        up: Sequence[float],
        offset: float,
        sweep: float,
        release_time: float,
        duration: float,
    ) -> None:
        super().__init__(name, half_extents)
        self.hinge = tuple(float(v) for v in hinge)
        self.axis = tuple(float(v) for v in axis)
        self.across = tuple(float(v) for v in across)
        self.up = tuple(float(v) for v in up)
        self.offset = float(offset)
        self.sweep = float(sweep)
        self.release_time = float(release_time)
        self.duration = float(duration)
        if self.duration <= 0.0:
            raise ValueError(f"panel {name!r}: a release takes a positive time")

    def angle_at(self, tick: int, dt: float) -> float:
        elapsed = tick * dt - self.release_time
        if elapsed <= 0.0:
            fraction = 0.0
        elif elapsed >= self.duration:
            fraction = 1.0
        else:
            u = elapsed / self.duration
            fraction = u * u * (3.0 - 2.0 * u)
        return self.sweep * fraction

    def frame_at(self, angle: float) -> tuple[tuple, tuple]:
        """The panel's `across` and `up` after rotating by `angle`.

        The `across` direction tips downward, so the panel's downstream edge
        descends and its hinge edge stays put.
        """
        cos, sin = math.cos(angle), math.sin(angle)
        across = tuple(
            self.across[axis] * cos - self.up[axis] * sin for axis in range(3)
        )
        up = tuple(
            self.up[axis] * cos + self.across[axis] * sin for axis in range(3)
        )
        return across, up

    def pose_at(self, tick: int, dt: float) -> Transform:
        angle = self.angle_at(tick, dt)
        across, up = self.frame_at(angle)
        centre = tuple(
            self.hinge[axis] + across[axis] * self.offset for axis in range(3)
        )
        return Transform(
            position=centre, rotation=basis_from_forward_up(self.axis, up)
        )

    def corners_at(self, angle: float) -> list[tuple[float, float, float]]:
        """The eight corners of the box at `angle`, in world simulation units.

        Used by `tools/sloped_floor_check.py` to measure the real clearances
        through the whole sweep rather than trusting the closed form in this
        module's docstring. The earlier wheel's scissor was arithmetic that
        nobody had done; this is the arithmetic, done by the geometry itself.
        """
        across, up = self.frame_at(angle)
        centre = [self.hinge[axis] + across[axis] * self.offset for axis in range(3)]
        half_a, half_u, half_c = self.half_extents
        points = []
        for sign_a in (-1.0, 1.0):
            for sign_u in (-1.0, 1.0):
                for sign_c in (-1.0, 1.0):
                    points.append(
                        tuple(
                            centre[axis]
                            + self.axis[axis] * sign_a * half_a
                            + up[axis] * sign_u * half_u
                            + across[axis] * sign_c * half_c
                            for axis in range(3)
                        )
                    )
        return points

    def distance_to(self, point: Sequence[float], angle: float) -> float:
        """Distance from `point` to this box's surface at `angle`, in sim units.

        Negative inside. A proper point-to-box distance rather than a
        nearest-corner one, because a corner distance says a plate sweeping
        broadside through a marble never touched it. Section 6 asks whether a
        panel can trap a sphere against the wall, and that question needs the
        face as well as the corner.
        """
        across, up = self.frame_at(angle)
        centre = [self.hinge[axis] + across[axis] * self.offset for axis in range(3)]
        offset = [point[axis] - centre[axis] for axis in range(3)]
        outside = 0.0
        inside = -1e30
        for direction, half in ((self.axis, self.half_extents[0]),
                                (up, self.half_extents[1]),
                                (across, self.half_extents[2])):
            local = sum(offset[axis] * direction[axis] for axis in range(3))
            over = abs(local) - half
            if over > 0.0:
                outside += over * over
            inside = max(inside, over)
        return math.sqrt(outside) if outside > 0.0 else inside

    def to_json(self) -> dict[str, Any]:
        data = super().to_json()
        data.update(
            {
                "hinge": list(self.hinge),
                "axis": list(self.axis),
                "across": list(self.across),
                "up": list(self.up),
                "offset": self.offset,
                "sweep": self.sweep,
                "release_time": self.release_time,
                "duration": self.duration,
            }
        )
        return data


class ShuffleFloor(ShuffleChamber):
    """The rotor chamber with a louvre floor and a receiving dish under it.

    Subclassed from `ShuffleChamber` so the pan, the eight bays, the
    synchronised gate, the apron, the chamber wall and the rotor are the same
    parts with the same corrections. What is replaced is the floor, the outlet
    and everything below them.
    """

    START_KIND = "floor"

    # --- the chamber, with its gradient removed -----------------------------
    #
    # **Flat and level, and that is the release architecture showing up as a
    # simplification.** See the module docstring: the 7-degree cone existed to
    # deliver the field to a hole, and a floor steep enough to do that packs
    # the field against the closed outlet and recreates the taper's own centre
    # bias. There is no hole.
    FLOOR_TILT = 0.0
    # No gate ring. `floor_at` clamps its radius at this, so zero makes the
    # floor one height everywhere, and `rest_radius` is overridden to match.
    GATE_R = 0.0

    # --- the rotor, at the configuration the pre-release table chose --------
    #
    # All three come from `docs/validation/sloped_race_v1/v18/
    # prerelease_trade.txt` and each was justified by a measurement before it
    # was changed:
    #
    #   held for entry    a racer's transport angle is the rate times its own
    #                     residence, and the eight bays arrive at systematically
    #                     different times, so a running rotor writes the bay
    #                     into the final bearing. Held, every racer gets the
    #                     same number of degrees.
    #   mix 3.00          once the residual is entry position rather than entry
    #                     time, mixing bites: 0.302 -> 0.218. 4.50 is no better.
    #   settle 1.20       at V1.7's 0.55 half the field was still moving and
    #                     the residual energy carried the bay.
    ROTOR_HOLD_ENTRY = True
    MIX_SECONDS = 3.00
    SETTLE_SECONDS = 1.20
    # **The paddles rise clear before the floor opens**, and it is a measured
    # correction rather than tidiness. See `sloped.shuffle.Rotor.lift_at`: a
    # stopped blade is the third wall of a pocket, together with the chamber
    # wall and the top edge of a hanging slat, and it held two racers of 96 at
    # the radius limit. The other two walls are structural; the blade is not.
    #
    # 0.68 is what clears a marble: a blade's underside sits 0.03 above the
    # floor and a marble standing on the floor reaches 0.57, so 0.60 is the
    # requirement and this is that with a marble's radius of margin.
    # `tools/sloped_floor_check.py` asserts the clearance rather than the
    # number.
    ROTOR_LIFT = 0.68

    # --- the louvre ---------------------------------------------------------
    #
    # Six, and the module docstring has the table: the seam a marble falls
    # through is `pitch - thickness`, so six slats at 0.900 leave 0.800 - 1.40
    # marble diameters, passing freely - where seven leave 1.18 and eight 1.01.
    PANELS = 6
    PANEL_THICK = 0.10
    # Sub-boxes per slat, all sharing the one hinge, so a slat approximates the
    # chord of the chamber instead of being a rectangle whose corners stand
    # outside the wall. One box per slat overshoots the wall by 0.67 at its
    # corner; three by 0.26.
    PANEL_SPLITS = 3
    # How far past the local chord each sub-box reaches. Small and deliberate:
    # the union of the slats must cover the disc with no crescent against the
    # wall for a marble to sit in, and over-covering into a wall that is a
    # zero-thickness static shell costs nothing a marble can reach.
    PANEL_BURY = 0.06
    # **Ninety, because that is where the seam is widest.** See the module
    # docstring: past 90 degrees the slat folds back over its own hinge, its
    # hinge edge becomes its downstream extreme, and the seam closes again -
    # measured at 0.299 at a 120-degree sweep, against 0.800 at 90. The
    # deepest point of the sweep is also 90, so this is the one angle at which
    # the slat is both as far out of the way as it gets and as wide open.
    PANEL_SWEEP = 90.0
    # How long the floor takes to open. Not instant, and not a flourish: a
    # kinematic box that teleports hands a marble an impulse from nowhere, and
    # the smoothstep in `FloorPanel.angle_at` is the same easing the start
    # gate uses. Every panel is given this same number.
    FLOOR_DURATION = 0.20
    # Clearance between the slats' deepest sweep and the **top of a marble
    # resting on the dish's highest surface**, which is not the same as
    # clearance to the dish.
    #
    # It was the dish, and the mistake cost six of fifteen stage-A traces. At
    # 90 degrees a slat hangs vertically from its hinge, a plate 0.10 thick
    # reaching 0.95 below the floor plane, and the dish's rim was set 0.16
    # under that. A marble sitting on the dish then has its *top* 0.285 above
    # the surface, which put it 0.023 into the hanging plate: traced, a marble
    # landed cleanly, then rolled back and forth along a slat's face for five
    # seconds and never moved downstream. The geometry check reported a
    # healthy +0.159 because it had been asked for the clearance to the dish,
    # which was the wrong question honestly answered.
    #
    # So the well carries a whole marble diameter of it.
    PANEL_CLEAR = 0.11

    # --- the receiving dish -------------------------------------------------
    #
    # A stadium: straight sides to `CATCH_Z`, then a semicircular cap, with the
    # spillway at the cap's downstream point. `CATCH_HALF` has to cover the
    # whole chamber disc from the cap's centre, which forces
    # `CATCH_HALF >= |CHAMBER_Z - CATCH_Z| + R_WALL` - and therefore puts the
    # spillway at or downstream of the chamber's own far edge. That is not a
    # choice: a spillway upstream of the region it drains would leave part of
    # the dish sloping away from the exit.
    CATCH_HALF = 3.05
    CATCH_Z = 0.00
    CATCH_BACK = -2.85
    # Rim edge down to the spillway. Shallow, and the basin's finding is why
    # that is enough: `rolling_friction` is zero, so a sphere rolls on any
    # non-zero slope and only an exactly level floor is a trap. 0.70 over a
    # 6.6-unit reach is about 6 degrees, and it keeps the drop onto the dish
    # down - which is the number that matters, because gravity at layout scale
    # is 139.8 units per second squared and every tenth of a unit of fall is
    # speed at the bottom of it.
    DISH_DEPTH = 0.70
    DISH_RIM_RISE = 0.78
    RINGS_ROUND = 40               # points round the dish's rim
    DISH_ROWS = 22
    DISH_COLUMNS = 24

    # --- the chute ----------------------------------------------------------
    SPILL_HALF = 0.95
    CHUTE_HALF = 0.95
    CHUTE_DEPTH = 0.26
    CHUTE_WALL = 0.72
    CHUTE_STEPS = 10
    # The grade the lift is sized from. The run available is fixed by the
    # spillway's position - about 0.89 units - so this is the one term in the
    # height chain that is chosen rather than derived, and 22 degrees keeps the
    # total lift at V1.7's own 2.14.
    CHUTE_GRADE = 22.0

    # --- the height chain ---------------------------------------------------

    @property
    def rest_radius(self) -> float:
        """There is no gate ring to rest against, so the field rests anywhere.

        Overridden rather than inherited because `sloped.shuffle.chamber_table`
        computes the free radial travel from it, and the honest answer for this
        chamber is the whole disc.
        """
        return 0.0

    @property
    def panel_pitch(self) -> float:
        return 2.0 * self.R_WALL / self.PANELS

    @property
    def panel_depth(self) -> float:
        """How far below the floor plane a slat reaches at any point of its sweep.

        The hinge sits at mid-thickness under the floor and the far edge's
        lowest corner is `pitch * sin(angle)` below it plus its own half
        thickness either side, so the deepest the sweep ever goes is at 90
        degrees - which a 120-degree sweep passes through - and it is one pitch
        plus one thickness. Exact rather than a bound.
        """
        return self.panel_pitch + self.PANEL_THICK

    @property
    def panel_well(self) -> float:
        """Floor plane down to the dish's rim edge.

        The slats' depth, **plus a marble diameter**, plus the clearance. The
        diameter is the term that was missing: a marble resting on the dish
        stands 0.57 tall and the slats hang in the space above the dish, so
        clearing the surface is not clearing the marble on it. See
        `PANEL_CLEAR`.
        """
        return self.panel_depth + 2.0 * layout.MARBLE_RADIUS + self.PANEL_CLEAR

    @property
    def dish_edge(self) -> float:
        """The dish's highest surface: its rim, all the way round."""
        return self.rim_floor - self.panel_well

    @property
    def dish_lip(self) -> float:
        return self.dish_edge - self.DISH_DEPTH

    @property
    def spill_z(self) -> float:
        return self.CATCH_Z + self.CATCH_HALF

    @property
    def dish_reach(self) -> float:
        """The furthest the dish extends from its spillway.

        The normaliser for the conical floor. By fraction of this rather than
        by absolute radius, because a stadium's wall is not the same distance
        away in every direction - keyed to radius, the floor would meet the
        wall at a different height upstream and downstream. The basin records
        the same reasoning.
        """
        return math.hypot(self.CATCH_HALF, self.spill_z - self.CATCH_BACK)

    @property
    def gate_time(self) -> float:
        """When the floor opens. Named as the parent names it, so
        `sloped.chamberstate` samples this chamber with no special case."""
        return self.rotor_stop + self.SPIN_DOWN + self.SETTLE_SECONDS

    @property
    def floor_open(self) -> float:
        return self.gate_time

    def derived_lift(self, plain) -> float:
        """The elevation this chain needs, and no more.

        Four terms, and V1.7's cone drop and outlet fall are replaced by the
        well and the dish rather than added to. Computed before the lift is
        applied, which is safe because the lift moves only `y`.
        """
        run = plain[2] - self.spill_z
        needed = (
            self.apron_drop
            + self.INLET_STEP
            + self.panel_well
            + self.DISH_DEPTH
            + max(run, 0.0) * math.tan(math.radians(self.CHUTE_GRADE))
        )
        seat = plain[1] + layout.FLOOR_Y
        return max(0.0, needed - (self.pan_floor - seat))

    # --- the dish's shape ---------------------------------------------------

    def _inside(self, x: float, z: float) -> bool:
        """The stadium: straight sides, then a semicircular downstream cap."""
        if z > self.CATCH_Z:
            return x * x + (z - self.CATCH_Z) ** 2 <= self.CATCH_HALF ** 2
        return abs(x) <= self.CATCH_HALF and z >= self.CATCH_BACK

    def _wall_reach(self, cos: float, sin: float) -> float:
        """Distance from the spillway to the dish wall along one direction.

        Bisection on `_inside` rather than a closed form per boundary: the
        stadium has three of them and a formula that has to pick the right one
        in every direction is a place to get a sign wrong. The basin learnt
        this and this borrows it.
        """
        low, high = 0.0, 2.0 * (self.CATCH_HALF + abs(self.spill_z - self.CATCH_BACK))
        for _ in range(30):
            mid = 0.5 * (low + high)
            if self._inside(cos * mid, self.spill_z + sin * mid):
                low = mid
            else:
                high = mid
        # The low point is *on* the rim, so straight downstream the wall is no
        # distance away and the dish would divide by nothing.
        return max(low, 0.5)

    def dish_at(self, x: float, z: float) -> float:
        """The dish floor at a point: a cone about the spillway.

        Lowest at the notch and rising evenly in every direction, so it slopes
        toward the exit from everywhere and has a flat spot nowhere.
        """
        span = min(1.0, math.hypot(x, z - self.spill_z) / self.dish_reach)
        return self.dish_lip + (self.dish_edge - self.dish_lip) * span

    def fall_to_dish(self, x: float, z: float) -> float:
        """How far a marble resting at (x, z) falls when the floor opens.

        Reported because it is the number the containment turns on: gravity at
        layout scale is 139.8 units per second squared, so a fall of 1.5 lands
        at 20 layout units per second. `tools/sloped_floor_check.py` prints the
        range over the whole chamber and the impact speeds it implies.
        """
        return (self.rim_floor - MARBLE_RADIUS) - self.dish_at(x, z) + MARBLE_RADIUS

    # --- geometry -----------------------------------------------------------

    def local_colliders(self) -> list[TriMesh]:
        if self._mesh is not None:
            return [self._mesh]
        pieces: list[TriMesh] = []
        pieces.extend(self._apron())
        pieces.extend(self._chamber())
        pieces.extend(self._dish())
        pieces.extend(self._chute())
        pieces.append(self._backstop())
        self._mesh = merge_meshes(pieces, f"{self.id}_floor")
        return [self._mesh]

    def _chamber(self) -> list[TriMesh]:
        """The wall only. **There is no static chamber floor at all.**

        The floor is seven kinematic slats, so the chamber's collider is its
        wall and nothing else - and a marble waiting to be mixed is resting on
        a moving part, which is what a trapdoor is. `local_probes` therefore
        cannot fire a ray at the chamber floor and does not; the slats are
        checked analytically instead, by `tools/sloped_floor_check.py`.
        """
        pieces: list[TriMesh] = []
        arc: list[float] = []
        for point in range(self.RINGS + 1):
            deg = 360.0 * point / self.RINGS
            if self._in_inlet(deg):
                if len(arc) > 1:
                    pieces.append(self._wall_arc(arc, len(pieces)))
                arc = []
            else:
                arc.append(deg)
        if len(arc) > 1:
            pieces.append(self._wall_arc(arc, len(pieces)))
        return pieces

    def _dish(self) -> list[TriMesh]:
        """The receiving dish, as a grid, with a guard round all of its rim.

        A grid over the dish's own extent rather than rings about its low
        point, because the low point is *on* the rim - that is what a spillway
        is - and rings about it collapse sideways and leave the far two thirds
        of the floor unbuilt. The basin measured that as one marble of eight
        finding the exit and the other seven sitting on nothing.

        The rim runs the whole way round except across the notch. The basin had
        to break it at its upstream edge as well, because a ramp arrived there;
        this dish is fed from above and has no such edge, so it is closed all
        round and a marble cannot leave it except through the notch.
        """
        pieces: list[TriMesh] = []
        rings: list[list[tuple[float, float, float]]] = []
        for row in range(self.DISH_ROWS + 1):
            z = self.CATCH_BACK + (self.spill_z - self.CATCH_BACK) * row / self.DISH_ROWS
            ring = []
            for column in range(self.DISH_COLUMNS + 1):
                x = -self.CATCH_HALF + 2.0 * self.CATCH_HALF * column / self.DISH_COLUMNS
                ring.append(_place(self.origin, self.frame, (x, self.dish_at(x, z), z)))
            rings.append(ring)
        pieces.append(_strip(rings, f"{self.id}_dish"))

        runs: list[list[tuple[float, float]]] = []
        current: list[tuple[float, float]] = []
        for point in range(self.RINGS_ROUND + 1):
            theta = 2.0 * math.pi * point / self.RINGS_ROUND
            cos, sin = math.cos(theta), math.sin(theta)
            reach = self._wall_reach(cos, sin)
            x = cos * reach
            z = self.spill_z + sin * reach
            if z > self.CATCH_Z and abs(x) <= self.SPILL_HALF and sin > -0.2:
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
                    _place(self.origin, self.frame, (x, self.dish_at(x, z) + rise, z))
                    for x, z in run
                ]
                for rise in (0.0, self.DISH_RIM_RISE)
            ]
            pieces.append(_strip(wall, f"{self.id}_dishrim{order}"))
        return pieces

    def _chute(self) -> list[TriMesh]:
        """From the notch in the rim to the launch's entry.

        A cradle with a wall each side from its first ring, unlike the outlet
        chute this replaces: that one had to grow its walls, because it sat
        under a hole and full walls came up through the hole and made a slot the
        field wedged in. A notch has no hole over it, so the chute is a channel
        from the start and the field arrives already converged and moving.
        """
        end_x, end_y, end_z = self.exit_local
        seat = end_y + layout.FLOOR_Y
        rings: list[list[tuple[float, float, float]]] = []
        for step in range(self.CHUTE_STEPS + 1):
            t = step / self.CHUTE_STEPS
            z = self.spill_z + (end_z - self.spill_z) * t
            x = end_x * t
            y = self.dish_lip + (seat - self.dish_lip) * t
            half = self.CHUTE_HALF + (layout.CHANNEL_HALF - self.CHUTE_HALF) * t
            ring = [
                _place(self.origin, self.frame,
                       (x - (half + 0.10), y + self.CHUTE_WALL, z))
            ]
            for column in range(9):
                across = -half + 2.0 * half * column / 8
                u = abs(across) / max(half, 1e-9)
                ring.append(
                    _place(self.origin, self.frame,
                           (x + across, y + self.CHUTE_DEPTH * u * u, z))
                )
            ring.append(
                _place(self.origin, self.frame,
                       (x + half + 0.10, y + self.CHUTE_WALL, z))
            )
            rings.append(ring)
        return [_strip(rings, f"{self.id}_chute")]

    # --- the floor, as actuators --------------------------------------------

    def panel_band(self, index: int) -> tuple[float, float]:
        """Slat `index`'s span in z, relative to the chamber's centre."""
        low = -self.R_WALL + index * self.panel_pitch
        return low, low + self.panel_pitch

    def panel_half_length(self, low: float, high: float) -> float:
        """Half the length of a sub-box covering z in [low, high].

        Sized from whichever edge of the band is *nearest* the chamber's
        centre, so the box reaches the chord at every z it covers and the union
        of the slats covers the disc. Sized from the far edge instead, or from
        the centre, and the slat falls short of the wall over part of its own
        band - a crescent gap at floor level with nothing under it.
        """
        near = 0.0 if low <= 0.0 <= high else min(abs(low), abs(high))
        inside = max(self.R_WALL * self.R_WALL - near * near, 1e-9)
        return math.sqrt(inside) + self.PANEL_BURY

    def local_actuators(self) -> list[Actuator]:
        """The bay paddles, the rotor and the seven floor slats.

        The paddles and the rotor come from the parent - so a correction to
        either reaches this class - and the parent's twelve outlet segments are
        dropped, because the outlet is the thing being replaced.
        """
        gates = [
            actuator for actuator in super().local_actuators()
            if not actuator.name.startswith("outlet")
        ]
        gates.extend(self.floor_panels())
        return gates

    def floor_panels(self) -> list[FloorPanel]:
        axis = tuple(float(v) for v in self.frame[0])
        up = tuple(float(v) for v in self.frame[1])
        across = tuple(float(v) for v in self.frame[2])
        sweep = math.radians(self.PANEL_SWEEP)
        panels: list[FloorPanel] = []
        for index in range(self.PANELS):
            low, _high = self.panel_band(index)
            # The hinge: the slat's upstream edge, at mid-thickness under the
            # floor plane, on the chamber's own axis.
            hinge = _place(
                self.origin, self.frame,
                (0.0, self.rim_floor - 0.5 * self.PANEL_THICK, self.CHAMBER_Z + low),
            )
            for split in range(self.PANEL_SPLITS):
                step = self.panel_pitch / self.PANEL_SPLITS
                sub_low = low + split * step
                sub_high = sub_low + step
                half_length = self.panel_half_length(sub_low, sub_high)
                panels.append(
                    FloorPanel(
                        name=f"panel{index}_{split}",
                        # (half length along the hinge, half thickness,
                        # half width across) - the axis order
                        # `basis_from_forward_up` puts on local X, Y, Z.
                        half_extents=(
                            to_sim(half_length),
                            to_sim(0.5 * self.PANEL_THICK),
                            to_sim(0.5 * step),
                        ),
                        hinge=hinge,
                        axis=axis,
                        across=across,
                        up=up,
                        offset=to_sim(sub_low - low + 0.5 * step),
                        sweep=sweep,
                        release_time=self.floor_open,
                        duration=self.FLOOR_DURATION,
                    )
                )
        return panels

    # --- what the simulation needs ------------------------------------------

    def marble_starts(self):
        return super().marble_starts()

    def local_probes(self) -> list[Probe]:
        """The apron and the dish. **Not the chamber floor, which moves.**

        A probe fired where a kinematic body stands measures the moving part
        and reports the floor as missing, which is why `StartGrid` skips its
        own gate rows. Here the whole chamber floor is a moving part, so there
        is nothing to fire at and the slats are checked analytically instead -
        coverage, seam clearance through the sweep, and depth against the dish,
        all in `tools/sloped_floor_check.py`.
        """
        probes: list[Probe] = []
        reach = 3.0 * MARBLE_RADIUS
        gate_u = (self.gate_z - self._field_z()) / max(self.apron_run, 1e-9)
        for step in range(0, 9):
            u = step / 8.0
            if abs(u - gate_u) < 0.09:
                continue
            centre = self.apron_centre(u)
            half = self.apron_half(u)
            for fraction in (-0.8, 0.0, 0.8):
                surface = _place(self.origin, self.frame,
                                 (fraction * half, centre[1], centre[2]))
                probes.append(
                    Probe(
                        start=(surface[0], surface[1] + reach, surface[2]),
                        end=(surface[0], surface[1] - reach, surface[2]),
                        expect_hit=True,
                        expected_point=surface,
                        tolerance=0.06,
                        label=f"{self.id}.apron[{step}]{fraction:+.1f}",
                    )
                )
        # The dish, where a marble lands and where it runs. Kept clear of the
        # notch: a ray fired at the spillway measures the chute's floor through
        # the gap, which is the geometry being right rather than a finding, and
        # there is no honest expected point to give it.
        for row in range(1, 8):
            z = self.CATCH_BACK + (self.spill_z - self.CATCH_BACK) * row / 8.0
            for fraction in (-0.75, -0.3, 0.0, 0.3, 0.75):
                x = fraction * self.CATCH_HALF
                if not self._inside(x, z):
                    continue
                if z > self.CATCH_Z and abs(x) <= self.SPILL_HALF and (
                    self.spill_z - z
                ) < 0.35:
                    continue
                surface = _place(self.origin, self.frame, (x, self.dish_at(x, z), z))
                probes.append(
                    Probe(
                        start=(surface[0], surface[1] + reach, surface[2]),
                        end=(surface[0], surface[1] - reach, surface[2]),
                        expect_hit=True,
                        expected_point=surface,
                        tolerance=0.05,
                        label=f"{self.id}.dish[{row}]{fraction:+.2f}",
                    )
                )
        return probes

    def describe(self) -> dict[str, Any]:
        data = super().describe()
        data["kind"] = "ShuffleFloor"
        data["start_kind"] = self.START_KIND
        data.pop("outlet", None)
        table = floor_table(self)
        data["floor"] = table["floor"]
        data["catch"] = {
            "half_width": self.CATCH_HALF,
            "width": round(2.0 * self.CATCH_HALF, 4),
            "cap_z": self.CATCH_Z,
            "back_z": self.CATCH_BACK,
            "spill_z": round(self.spill_z, 4),
            "spill_half": self.SPILL_HALF,
            "dish_depth": self.DISH_DEPTH,
            "rim_rise": self.DISH_RIM_RISE,
            "reach": round(self.dish_reach, 4),
            "slope_deg": round(
                math.degrees(math.atan2(self.DISH_DEPTH, self.dish_reach)), 3
            ),
        }
        data["heights"] = {
            "pan_floor": round(self.pan_floor, 4),
            "chamber_floor": round(self.rim_floor, 4),
            "dish_edge": round(self.dish_edge, 4),
            "dish_lip": round(self.dish_lip, 4),
            "exit_seat": round(self.exit_local[1] + layout.FLOOR_Y, 4),
            "chute_run": round(self.exit_local[2] - self.spill_z, 4),
            "chute_grade_deg": round(
                math.degrees(math.atan2(
                    self.dish_lip - (self.exit_local[1] + layout.FLOOR_Y),
                    self.exit_local[2] - self.spill_z)), 3),
        }
        data["release"] = {
            "opens_at": round(self.floor_open, 4),
            "duration": self.FLOOR_DURATION,
            "sweep_deg": self.PANEL_SWEEP,
            "reads_marble_positions": False,
            "reads_marble_ids": False,
            "reads_start_bays": False,
        }
        return data


def floor_table(floor: ShuffleFloor) -> dict:
    """The louvre's own numbers, all of them derived from the pitch.

    Section 6 asks for the clearances to be validated through the *complete*
    opening motion, which a table of resting numbers cannot do; that is
    `tools/sloped_floor_check.py`'s job and it walks the sweep degree by
    degree. What is here is the sizing those numbers follow from.
    """
    diameter = 2.0 * layout.MARBLE_RADIUS
    pitch = floor.panel_pitch
    return {
        "floor": {
            "panels": floor.PANELS,
            "pitch": round(pitch, 4),
            "pitch_diameters": round(pitch / diameter, 3),
            "thickness": floor.PANEL_THICK,
            "splits_per_panel": floor.PANEL_SPLITS,
            "boxes": floor.PANELS * floor.PANEL_SPLITS,
            "sweep_deg": floor.PANEL_SWEEP,
            "duration": floor.FLOOR_DURATION,
            "depth_at_full_sweep": round(floor.panel_depth, 4),
            "well": round(floor.panel_well, 4),
            "opens_at": round(floor.floor_open, 4),
            # The gap two neighbours finally leave, which is the pitch, and the
            # angle at which it first passes one marble diameter. Below that
            # angle no marble can enter the seam at all, and above it the seam
            # only widens - which is why nothing can be caught in it.
            "final_seam": round(_seam(floor, math.radians(floor.PANEL_SWEEP)), 4),
            "final_seam_diameters": round(
                _seam(floor, math.radians(floor.PANEL_SWEEP)) / diameter, 3),
            "widest_seam": round(
                max(_seam(floor, math.radians(deg)) for deg in range(181)), 4),
            "seam_passes_a_marble_at_deg": _first_angle(floor, diameter),
            "seam_passes_freely_at_deg": _first_angle(floor, 1.25 * diameter),
        }
    }


def panels_by_index(floor: ShuffleFloor) -> dict[int, list[FloorPanel]]:
    """The floor's boxes, grouped into the slats they make up."""
    grouped: dict[int, list[FloorPanel]] = {}
    for panel in floor.floor_panels():
        index = int(panel.name.split("panel")[1].split("_")[0])
        grouped.setdefault(index, []).append(panel)
    return grouped


def seam_gap(here, there, along) -> float:
    """The measured clearance between two slats, across the hinge direction.

    `here` and `there` are corner lists from `FloorPanel.corners_at`, in world
    simulation units; `along` is the direction the seam opens in, which is
    perpendicular to both the hinge and world up. The result is in layout
    units, and zero when the two overlap in projection.

    **Projected rather than taken as a 3D distance**, because the distance
    between two corners that are one above the other is not a gap anything can
    go through - and this is the measurement that found the sweep's fold, so it
    is shared by the geometry check and the tests rather than written twice.
    """
    def spread(points):
        return [
            sum(point[axis] * along[axis] for axis in range(3)) for point in points
        ]

    a_span = spread(here)
    b_span = spread(there)
    if max(a_span) <= min(b_span):
        return (min(b_span) - max(a_span)) * SIM_TO_LAYOUT
    if max(b_span) <= min(a_span):
        return (min(a_span) - max(b_span)) * SIM_TO_LAYOUT
    return 0.0


def _seam(floor: ShuffleFloor, angle: float) -> float:
    """The clear gap between two neighbouring slats at `angle`.

    Two branches, and the second one is the correction: to 90 degrees the far
    edge of a slat retreats toward its hinge as the cosine, and past 90 it has
    gone *beyond* the hinge, so the hinge edge becomes the slat's downstream
    extreme and the seam closes again. Both slats' half thicknesses swing into
    the seam as the sine throughout.

    Derived here and *measured* from the real box corners by
    `tools/sloped_floor_check.py`, which is the check that matters and which is
    what caught the missing second branch.
    """
    fold = math.cos(angle)
    reach = 1.0 - fold if fold >= 0.0 else 1.0 + fold
    return floor.panel_pitch * reach - floor.PANEL_THICK * abs(math.sin(angle))


def _first_angle(floor: ShuffleFloor, clearance: float) -> float | None:
    """The first angle of the sweep at which the seam reaches `clearance`.

    Below it no marble can enter the seam at all; above it the seam only
    widens. That pair of facts is why nothing can be caught in it, and it is
    worth reporting as an angle rather than asserted in prose.
    """
    for tenth in range(1, 10 * int(floor.PANEL_SWEEP) + 1):
        angle = math.radians(tenth / 10.0)
        if _seam(floor, angle) >= clearance:
            return round(tenth / 10.0, 1)
    return None

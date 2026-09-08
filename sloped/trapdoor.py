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
    a cone on the chamber's own axis, 5.80 across
      |  through a 1.90 throat directly under the chamber's centre
    the exit chute onto the launch run

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

## Why the catch is a cone on the chamber's own axis

Section 7 asks for a broad catch that does not drop eight marbles into a
one-marble throat, and the first build of this module used the basin's answer:
a stadium dish 5.5 across draining to a notch in its downstream rim, which
`sloped.basin` measured as passing all eight marbles every seed with no jam.

**It delivered 98.96% of the field and produced a centre-versus-rank
correlation of +0.886**, worse than the shipped taper's +0.574 and far worse
than V1.7's own -0.182. The mechanism is general enough to be worth stating,
because it is the same shape of finding as V1.7's:

> A catch with one exit orders the field by path length to that exit, so the
> statistic that decides the race is "how far from the exit was this marble
> when the floor went". A position-independent release does not remove the
> selection - it *moves* it to the catch. So the catch's exit has to sit
> wherever the mixing has actually equalised the field.

The rotor equalises exactly one coordinate and the pre-release table says which:
with the paddles stopped, the field's **radius** is nearly bay-free
(`bay -> radius` is -0.10, `|bay-3.5| -> radius` is +0.10) while its bearing
still carries the bay at a concentration of 0.36. Distance to a point *on the
chamber's axis* is the radius. Distance to a notch on the rim is a function of
radius **and** bearing, so it reads back the one thing the chamber did not
erase - and it reads it back amplified, because the notch is 2.75 downstream
and the chamber is only 2.70 across, so the dominant term is the bay's
residual z.

That is also, in hindsight, why V1.7's central outlet was the fairest catch
this tree has built. Its problem was throughput and never fairness.

So the catch is a **cone on the chamber's own axis**, draining through a
1.90-wide throat directly under the chamber's centre into the exit chute. The
basin's other two findings still hold and are still used: conical rather than
quadratic, because a dish that is level at its drain has a flat spot and with
`surface_friction` at 0.50 a pile on a level floor is statically stable; and
the throat is 1.90 because V1.5 measured a 1.24 drain arching and a 1.90 one
passing 98.4%, and V1.7 measured the same at 1.50 against 1.90.

The basin's warning about a central hole - "a throat, a tunnel and a roof, and
every one of them was a defect in turn" - is answered by V1.7's exit chute,
which is inherited whole: it starts well below the throat and grows its walls
afterwards, because full walls from the first ring come up through the hole and
make a slot the field wedges in.

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
from sloped.scale import LAYOUT_TO_SIM, SIM_TO_LAYOUT, to_sim
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
    # **13 rad/s, and the rate is the knob V1.7 could not touch.** A fast rotor
    # centrifuges the field away from a central outlet and starves the
    # delivery - six of eight racers stayed put when V1.7's gate dropped - and
    # a trapdoor does not care where the field is when the floor goes.
    #
    # What it buys is measured on the statistic an axial catch reads, which is
    # the marble's own chamber radius. 96 seeds each:
    #
    #     rate   bay -> radius   |bay-3.5| -> radius   in the chamber
    #      5.0       -0.065            -0.202              100%
    #      9.0       +0.006            -0.119              100%
    #     13.0       +0.019            -0.047              100%
    #
    # and downstream, at the exit checkpoint:
    #
    #     rate   exit span   slot r   centre r   slot-mean sd
    #      5.0     1.208     -0.074    -0.928       0.439
    #     13.0     1.177     +0.378    -0.090       0.376
    #
    # **The rate rotates the residual rather than removing it** - the span is
    # the same within noise and only the shape moves - so the choice is made on
    # the standard deviation of the eight slot means, which privileges no
    # shape. 13 wins it, and it also trades a *strong* correlation for a
    # moderate one, which is the direction section 14 asks for.
    #
    # Nothing is thrown out of the chamber at 13, because the tip-to-wall
    # clearance is 0.150 at every blade angle and a gap with no angle in it
    # cannot close on a marble. The earlier in-channel wheel put 80.2% of its
    # field in the stuck column at 12 rad/s for exactly the opposite reason.
    ROTOR_RATE = 13.0

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
    #
    # **The over-reach is much larger while a slat is moving, and it is
    # inherent to an edge hinge.** At 90 degrees a slat has collapsed onto its
    # own hinge line, so every one of its boxes is at the hinge's z while
    # keeping its full half length - and the outermost slat's hinge is at the
    # chamber's very edge, where the chord is zero. Measured, its corners swing
    # to radius 3.44 against a 2.70 wall and a 2.90 catch rim.
    #
    # It is harmless and the bound is why: a marble's centre cannot exceed
    # `R_WALL - MARBLE_RADIUS` = 2.415, so nothing a marble can occupy is
    # anywhere near it; the panels are kinematic and the wall and rim are
    # static, and Bullet generates no contact between two zero-mass bodies; and
    # the static geometry a bounced marble would meet is unaffected by a
    # kinematic box passing through it. `tools/sloped_floor_check.py` measures
    # the reach and asserts the bound rather than leaving it unmeasured.
    #
    # What it is not harmless for is the *render*: slat corners visibly sweep
    # outside the chamber wall and through the catch's rim. That is a shroud
    # the renderer owes the mechanism, and it is listed as a remaining issue.
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

    # --- the receiving cone -------------------------------------------------
    #
    # **Concentric with the chamber, and that is the fairness decision rather
    # than a shape.** See the module docstring: a catch with one exit orders
    # the field by path length to it, and the only coordinate the rotor
    # equalises is the radius, so the exit has to sit on the axis.
    #
    # 2.90 rather than 2.70, so a marble that lands near the chamber wall and
    # bounces outward still lands on the cone.
    CATCH_HALF = 2.90
    # **1.90 across, and that figure is measured rather than chosen.** V1.5's
    # drain arched at 1.24 and passed 98.4% of the field at 1.90; V1.7's
    # outlet arched at 1.50 and passed at 1.90.
    THROAT_R = 0.95
    # Rim to throat. Every tenth of it is lift, and it does not have to do what
    # V1.7's chamber cone did: that one had to deliver a field *from rest* and
    # failed on 10% of it at 7 degrees, where these marbles arrive at 23 layout
    # units per second with the whole drop behind them. What it does have to do
    # is have no flat spot, which any non-zero slope satisfies because
    # `rolling_friction` is zero.
    FUNNEL_TILT = 14.0
    CONE_RIM_RISE = 0.82
    RINGS_ROUND = 48               # points round the cone
    CONE_STEPS = 12                # radial steps across it

    # --- the chute ----------------------------------------------------------
    #
    # V1.7's exit chute, inherited whole, and the basin's warning about a
    # central hole is why: a chute under a drain is a landing and a landing has
    # no kerb, so it starts well below the throat and grows its walls
    # afterwards. Full walls from the first ring come up through the hole and
    # make a slot the field wedges in.
    CHUTE_HALF = 0.95
    CHUTE_LEAD = 0.15
    CHUTE_STEPS = 14
    # How far below the throat's lip the chute's landing sits. **Named and
    # included in the height chain**, which closes V1.7's own remaining issue
    # 3: there the same 0.24 was applied to the chute's geometry but left out
    # of `derived_lift`, so the realised grade came out 2.7 degrees shallower
    # than the target the lift was sized from and the two names disagreed.
    CHUTE_LANDING = 0.24
    # 17 degrees, measured over 24 seeds in V1.7: 22 lost 3.65% of the field to
    # escapes on the launch's banked plunge and 17 lost 2.60%, with no jams at
    # either, while below about 15 the clump stacks in the chute instead and 13
    # delivered nothing at all. The trade is between two different failures.
    CHUTE_GRADE = 17.0

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
        """The cone's highest surface: its rim, all the way round."""
        return self.rim_floor - self.panel_well

    @property
    def funnel_drop(self) -> float:
        """Rim to throat."""
        return (self.CATCH_HALF - self.THROAT_R) * math.tan(
            math.radians(self.FUNNEL_TILT)
        )

    @property
    def dish_lip(self) -> float:
        """The throat's lip: the cone's lowest surface, on the axis."""
        return self.dish_edge - self.funnel_drop

    @property
    def outlet_lip(self) -> float:
        """What `ShuffleChamber._exit_chute` calls the height it starts from."""
        return self.dish_lip

    @property
    def chute_mouth_z(self) -> float:
        """Where the exit chute begins: clear of the throat's upstream edge.

        A chute whose first ring is downstream of that leaves the throat's
        upstream half opening onto nothing, and every racer falls through and
        out of the machine - which is what V1.5 built, and it reported no ranks
        at any checkpoint over 96 racers with nothing registered as lost,
        because a marble that never touches a run is never located on one.
        """
        return self.CHAMBER_Z - self.THROAT_R - self.CHUTE_LEAD

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

        Five terms: the apron, the step into the chamber, the well the slats
        hang in, the cone, and the chute. **The chute's landing is in the sum**
        rather than left out of it, which is V1.7's remaining issue 3 closed -
        there the same 0.24 shaped the geometry but not the lift, so the
        realised grade came out 2.7 degrees shallower than the target.

        Computed before the lift is applied, which is safe because the lift
        moves only `y`.
        """
        run = plain[2] - self.chute_mouth_z
        needed = (
            self.apron_drop
            + self.INLET_STEP
            + self.panel_well
            + self.funnel_drop
            + self.CHUTE_LANDING
            + max(run, 0.0) * math.tan(math.radians(self.CHUTE_GRADE))
        )
        seat = plain[1] + layout.FLOOR_Y
        return max(0.0, needed - (self.pan_floor - seat))

    # --- the dish's shape ---------------------------------------------------

    def _inside(self, x: float, z: float) -> bool:
        """Inside the cone: one circle, concentric with the chamber."""
        return x * x + (z - self.CHAMBER_Z) ** 2 <= self.CATCH_HALF ** 2

    def dish_at(self, x: float, z: float) -> float:
        """The cone's surface at a point, in the module's own frame.

        Conical about the chamber's axis, so it is the same height at every
        bearing and its only gradient is radial - which is the whole fairness
        argument, because the radius is the coordinate the rotor equalises.
        Flat across the throat, which is a 1.90-wide hole rather than a floor.
        """
        radius = math.hypot(x, z - self.CHAMBER_Z)
        span = max(min(radius, self.CATCH_HALF) - self.THROAT_R, 0.0)
        return self.dish_lip + span * math.tan(math.radians(self.FUNNEL_TILT))

    def fall_to_dish(self, x: float, z: float) -> float:
        """How far a marble resting at (x, z) falls when the floor opens.

        Reported because it is the number the containment turns on: gravity at
        layout scale is 139.8 units per second squared, so a fall of 1.5 lands
        at 20 layout units per second. `tools/sloped_floor_check.py` prints the
        range over the whole chamber and the impact speeds it implies.
        """
        return self.rim_floor - self.dish_at(x, z)

    # --- geometry -----------------------------------------------------------

    def local_colliders(self) -> list[TriMesh]:
        if self._mesh is not None:
            return [self._mesh]
        pieces: list[TriMesh] = []
        pieces.extend(self._apron())
        pieces.extend(self._chamber())
        pieces.extend(self._funnel())
        pieces.extend(self._exit_chute())
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

    def _funnel(self) -> list[TriMesh]:
        """The receiving cone, and a guard right round its rim.

        Rings about the chamber's axis rather than a grid, which is the right
        way round for *this* shape and was the wrong way round for the basin's:
        rings only work when the low point is inside the surface, and the
        basin's low point was on its rim. Here it is the throat, dead centre.

        The rim is unbroken. The basin had to break its own wherever the
        boundary was an open edge a ramp arrived at; this cone is fed from
        directly above and has no such edge, so a marble cannot leave it except
        through the throat.
        """
        pieces: list[TriMesh] = []
        rings: list[list[tuple[float, float, float]]] = []
        for step in range(self.CONE_STEPS + 1):
            radius = self.CATCH_HALF - (self.CATCH_HALF - self.THROAT_R) * (
                step / self.CONE_STEPS
            )
            y = self.dish_at(radius, self.CHAMBER_Z)
            rings.append([
                _place(self.origin, self.frame,
                       self._ring_point(radius, 360.0 * p / self.RINGS_ROUND, y))
                for p in range(self.RINGS_ROUND + 1)
            ])
        pieces.append(_strip(rings, f"{self.id}_cone"))

        wall = [
            [
                _place(self.origin, self.frame,
                       self._ring_point(self.CATCH_HALF,
                                        360.0 * p / self.RINGS_ROUND,
                                        self.dish_edge + rise))
                for p in range(self.RINGS_ROUND + 1)
            ]
            for rise in (0.0, self.CONE_RIM_RISE)
        ]
        pieces.append(_strip(wall, f"{self.id}_conerim"))
        return pieces

    # --- the floor, as actuators --------------------------------------------

    def panel_band(self, index: int) -> tuple[float, float]:
        """Slat `index`'s span in z, relative to the chamber's centre."""
        low = -self.R_WALL + index * self.panel_pitch
        return low, low + self.panel_pitch

    def panel_reach(self) -> tuple[float, float, str]:
        """The furthest any slat corner gets from the chamber's axis, and when.

        Returns (radius, degrees, panel name). See `PANEL_BURY`: this is large,
        inherent to an edge hinge, and bounded harmless by the fact that a
        marble's centre cannot exceed `R_WALL - MARBLE_RADIUS`.
        """
        worst = 0.0
        where = (0.0, "")
        for panel in self.floor_panels():
            for step in range(int(self.PANEL_SWEEP) + 1):
                angle = math.radians(step)
                for corner in panel.corners_at(angle):
                    local = self._to_local(corner)
                    radius = math.hypot(local[0], local[2] - self.CHAMBER_Z)
                    if radius > worst:
                        worst, where = radius, (float(step), panel.name)
        return worst, where[0], where[1]

    def _to_local(self, world_sim):
        """A world simulation point back in this module's layout frame."""
        point = tuple(value / LAYOUT_TO_SIM for value in world_sim)
        delta = tuple(point[axis] - self.origin[axis] for axis in range(3))
        return tuple(
            sum(self.frame[axis][component] * delta[component] for component in range(3))
            for axis in range(3)
        )

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
        # The cone, where a marble lands and where it runs. **Not the throat:**
        # a ray fired down it measures the chute's floor through the hole,
        # which is the geometry being right rather than a finding, and there is
        # no honest `expected_point` to give it. The basin skips its own drain
        # for the same reason.
        for step in range(1, self.CONE_STEPS):
            radius = self.CATCH_HALF - (self.CATCH_HALF - self.THROAT_R) * (
                step / self.CONE_STEPS
            )
            if radius <= self.THROAT_R + 0.12:
                continue
            y = self.dish_at(radius, self.CHAMBER_Z)
            for point in range(0, self.RINGS_ROUND, 7):
                deg = 360.0 * point / self.RINGS_ROUND
                surface = _place(self.origin, self.frame,
                                 self._ring_point(radius, deg, y))
                probes.append(
                    Probe(
                        start=(surface[0], surface[1] + reach, surface[2]),
                        end=(surface[0], surface[1] - reach, surface[2]),
                        expect_hit=True,
                        expected_point=surface,
                        tolerance=0.05,
                        label=f"{self.id}.cone[{radius:.2f}@{deg:.0f}]",
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
            "kind": "cone on the chamber axis",
            "half_width": self.CATCH_HALF,
            "width": round(2.0 * self.CATCH_HALF, 4),
            "throat_radius": self.THROAT_R,
            "throat_width": round(2.0 * self.THROAT_R, 4),
            "rim_to_throat": round(self.funnel_drop, 4),
            "rim_rise": self.CONE_RIM_RISE,
            "slope_deg": self.FUNNEL_TILT,
            # The one number the whole catch was rebuilt for: what a marble's
            # distance to the exit is a function of. See the module docstring.
            "orders_the_field_by": "radius from the chamber axis",
        }
        data["heights"] = {
            "pan_floor": round(self.pan_floor, 4),
            "chamber_floor": round(self.rim_floor, 4),
            "dish_edge": round(self.dish_edge, 4),
            "dish_lip": round(self.dish_lip, 4),
            "exit_seat": round(self.exit_local[1] + layout.FLOOR_Y, 4),
            "chute_mouth_z": round(self.chute_mouth_z, 4),
            "chute_run": round(self.exit_local[2] - self.chute_mouth_z, 4),
            "chute_grade_deg": round(
                math.degrees(math.atan2(
                    (self.dish_lip - self.CHUTE_LANDING)
                    - (self.exit_local[1] + layout.FLOOR_Y),
                    self.exit_local[2] - self.chute_mouth_z)), 3),
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
            "corner_reach": round(floor.panel_reach()[0], 4),
            "marble_reach": round(floor.R_WALL - layout.MARBLE_RADIUS, 4),
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

"""The dynamic start equaliser: a rotor in a chamber, with the exit held shut.

## Why anything dynamic, and why this shape

Five passive start topologies have been built and measured and all five order
the field by starting bay. `docs/sloped_race_v16_widelaunch.md` states the
general form:

> Every passive start delivers its field into a course that reads *some*
> geometric coordinate as a time advantage. Equalising one coordinate leaves
> another, and the surviving coordinate is always a function of the starting
> bay - because the bays are physically distinct places and a passive surface
> has nothing with which to forget which is which.

The last clause is the opening. A *shape* has nothing with which to forget; a
mechanism that moves has a phase, and a phase is not a function of which bay a
marble came from. So the equaliser is a rotor, and the one architectural rule
that makes it work is section 2 of the brief's:

    THE EXIT MUST REMAIN CLOSED WHILE MIXING OCCURS.

With the exit shut, "distance to the exit" is not a quantity the field can be
sorted by while it is being stirred. It becomes one again when the gate opens -
and that is allowed, because by then which marble is where is a property of the
rotor's stirring and not of the bay.

## What this builds

    eight bays abreast on a flat pan, one synchronised gate   <- unchanged, seen
      |  a short apron; it may taper, and section 2 is why
    a circular chamber, 4.90 across, shallow floor
      |  four paddles on a hub, turning throughout
    the field circulates, collides and exchanges places
      |  the gate ring drops
    a wide central outlet
      |
    a chute onto the launch run

## Why the earlier wheel jammed, and why a chamber cannot

`tools/sloped_start_scan.py` records a wheel that reduced the rank spread and
put 18.8% of the field in the stuck column, and section 4 of the brief asks for
the mechanism before anything is rebuilt. It is a **closing gap**.

That wheel swept a circle of tip radius 0.90 inside a *straight* channel whose
clear half width is 0.94. The gap between the blade tip and the wall is
therefore `0.94 - 0.90 sin(angle)`, which runs from 0.94 with the blade along
the channel to 0.04 with it across:

     blade angle      0     20     40     60     80     90
     tip-to-wall   0.94   0.63   0.36   0.16   0.05   0.04

A marble is 0.570 across, so the gap passes through exactly one marble
diameter at about 24 degrees - four times a revolution, every revolution. That
is a scissor, and the recorded numbers are what a scissor predicts: a faster
blade is *worse* (6.0 rad/s stuck 18.8%, 12.0 rad/s stuck 80.2%) because it
closes more often per second, and a wheel further downstream is better
(sample 24 stuck 5.2%) because the field crosses the pinch zone quicker.

**A chamber concentric with its rotor has a constant tip-to-wall gap.**
`R_WALL - TIP_R` is 0.15 everywhere, which is smaller than a marble at every
angle, so no marble can ever enter the gap and there is nothing for the tip to
close on. The paddle sweeps marbles *along* the wall instead, which is the
pushing action the mechanism is for. That is the whole reason the rotor moves
into a chamber rather than staying in the channel.

## The other four clearances, all constant for the same reason

| | |
|---|---|
| tip to wall | 0.15, less than a marble - swept, never pinched |
| paddle root to the gate ring | 0.09, likewise |
| between paddles, at the root | 1.41, two and a half marbles |
| the annulus the field lives in | 1.13 of free centre travel, **two marble diameters**, so racers can pass each other radially rather than forming a necklace |

The last is the sizing that matters and it is the one V1.5's trough failed:
eight marbles at one radius in a channel one marble wide cannot exchange
cyclic order, so a stirrer can only rotate the necklace and the order survives.
Two diameters of radial freedom is what lets the rotor actually reorder them.

## The lift is derived

`derived_lift()` asks for exactly the elevation the chain needs and no more:
the apron's drop, the chamber's floor, the outlet's fall and an exit chute at a
reasonable grade. The answer is about 1.50, against the radial start's 4.30.
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
from sloped.solids import merge_meshes, plate
from sloped.stations import Spinner, StartGrid, _bay_x, _place, _strip
from sloped.track import TrackRun

__all__ = ["Rotor", "ShuffleChamber", "chamber_table"]


class Rotor(Spinner):
    """A paddle that turns for a fixed interval and then holds still.

    **The rotor has to stop before the outlet opens, and that is a physical
    finding rather than a tidiness.** A spinning rotor centrifuges the field
    outward: traced in simulation with the rotor running throughout, all eight
    racers seated correctly against the gate ring, the ring dropped, and six of
    the eight simply stayed where they were - held out against a 5-degree
    inward cone by paddles sweeping past at 11.5 layout units per second. Two
    left, and only because they happened to be inside the ring's radius when it
    went.

    Stopping the rotor also buys the property the whole architecture is for
    free: with the paddles still and the floor conical, the field settles
    against the ring at *one radius* - the equal-distance-to-the-exit condition
    V1.4 built a whole ring of cups to get - while its bearing round the
    chamber is whatever the stirring left. Equal radius, scrambled azimuth.

    `angle_at` stays a pure function of the tick, which is section 9's
    requirement: the angle ramps down over `spin_down` and is constant after,
    so the same seed gives the same paddle angle at the same tick in every
    process.
    """

    def __init__(self, *args, stop_time: float, start_time: float = 0.0,
                 spin_down: float = 0.30, tail_rate: float = 0.0,
                 lift_time: float = 0.0, lift_by: float = 0.0,
                 lift_over: float = 0.30, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_time = float(start_time)
        self.stop_time = max(float(stop_time), self.start_time)
        self.spin_down = max(float(spin_down), 1e-6)
        self.tail_rate = float(tail_rate)
        self.lift_time = float(lift_time)
        self.lift_by = float(lift_by)
        self.lift_over = max(float(lift_over), 1e-6)

    def angle_at(self, tick: int, dt: float) -> float:
        """The integral of the rate profile, so the angle never jumps.

        Still, then full `rate` from `start_time` to `stop_time`, then a linear
        ramp to `tail_rate` over `spin_down`, then `tail_rate`. Integrated
        rather than sampled because a sampled rate change puts a step in the
        angle, and a kinematic box that teleports a paddle-width hands a
        marble an impulse from nowhere.

        **`start_time` is what makes every racer see the same rotor**, and it
        is a measured correction rather than a convenience. With the rotor
        turning from tick zero, a racer transport angle is
        `rate * (stop_time - its own arrival time)`, and the eight bays arrive
        at systematically different times because they have different
        distances to travel across the apron. So the bay is written into the
        final bearing, and no amount of extra mixing removes it: the residual
        is a *difference* in residence, and a longer run adds the same constant
        to everyone. `docs/validation/sloped_race_v1/v18/` records the per-bay
        bearing concentration holding at 0.60 from 1.19 turns to 7.16.

        Held still until the whole field is in the chamber, every racer gets
        the same number of degrees of rotor, and the difference cancels.
        """
        now = tick * dt
        if now <= self.start_time:
            turned = 0.0
        elif now <= self.stop_time:
            turned = self.rate * (now - self.start_time)
        else:
            span = self.stop_time - self.start_time
            over = min(now - self.stop_time, self.spin_down)
            turned = self.rate * span + over * (
                self.rate - 0.5 * (self.rate - self.tail_rate) * over / self.spin_down
            )
            if now - self.stop_time > self.spin_down:
                turned += self.tail_rate * (now - self.stop_time - self.spin_down)
        return self.phase + self.offset + turned

    def lift_at(self, tick: int, dt: float) -> float:
        """How far the paddle assembly has been raised by `tick`.

        Zero unless `lift_by` is set, and then a smoothstep over `lift_over`
        starting at `lift_time`, clamped at both ends. A pure function of the
        tick like everything else here.

        **This exists because a stopped paddle in a chamber with no floor is a
        hazard with no purpose**, and a measured one. With a full-floor release
        the blades no longer have to be anywhere in particular once the mixing
        is over, and left where they were they form the third wall of a pocket:
        two racers of 96 in `docs/validation/sloped_race_v1/v18/` were held at
        the chamber's radius limit between the wall, the top edge of a hanging
        floor slat, and a stopped blade beside them. The first two of those
        three are structural. The blade is not, so it goes.
        """
        if self.lift_by == 0.0:
            return 0.0
        elapsed = tick * dt - self.lift_time
        if elapsed <= 0.0:
            return 0.0
        if elapsed >= self.lift_over:
            return self.lift_by
        u = elapsed / self.lift_over
        return self.lift_by * u * u * (3.0 - 2.0 * u)

    def pose_at(self, tick: int, dt: float) -> Transform:
        pose = super().pose_at(tick, dt)
        raised = self.lift_at(tick, dt)
        if raised == 0.0:
            return pose
        return Transform(
            position=tuple(
                pose.position[axis] + self.up[axis] * raised for axis in range(3)
            ),
            rotation=pose.rotation,
        )

    def to_json(self):
        data = super().to_json()
        data.update({
            "start_time": self.start_time,
            "stop_time": self.stop_time,
            "spin_down": self.spin_down,
            "tail_rate": self.tail_rate,
            "lift_time": self.lift_time,
            "lift_by": self.lift_by,
            "lift_over": self.lift_over,
        })
        return data


def _ease(value: float) -> float:
    t = min(1.0, max(0.0, value))
    return t * t * (3.0 - 2.0 * t)


class ShuffleChamber(StartGrid):
    """The eight bays and the gate of `StartGrid`, over a rotor chamber.

    Subclassed for the reason every other start is: the bays, the resting
    pitch and the release carry five sessions of corrections. What is new is
    everything below the gate, and that it moves.
    """

    START_KIND = "rotor"

    # --- the pan the field waits on --------------------------------------
    #
    # Flat *across*: a dished pan rests its outer bays higher, which is a
    # per-bay energy difference, and the fan's trough had one unnoticed for
    # three sessions.
    PAN_BACK = -4.60
    PAN_SINK = 0.30
    PAN_HALF = 2.86

    # --- the apron into the chamber ---------------------------------------
    #
    # **This one is allowed to taper, and section 2 of the brief is the
    # reason.** Every passive start failed because a constriction ordered the
    # field by distance to it. Here the constriction is upstream of a chamber
    # whose exit is shut, so what it orders is discarded before anything can be
    # sorted by it. The entry order is not the race order.
    APRON_GRADE = 14.0
    INLET_HALF = 1.30
    # A step down into the chamber, so a marble the rotor throws at the inlet
    # has to climb to leave. It does not have to be un-climbable: the apron
    # rises 0.47 over its length and a marble at 11 layout units per second
    # carries 0.61 of climb, so the worst case runs a unit up the apron and
    # comes back. What it cannot do is reach the pan.
    INLET_STEP = 0.28

    # --- the chamber --------------------------------------------------------
    CHAMBER_Z = 0.30               # its centre, on the module's own axis
    # 5.40 across, still under the drawn pod's 5.46. Grown from 4.90 when the
    # outlet had to grow: the two are locked together, because the free radial
    # travel the field needs to be able to pass itself is
    # `(R_WALL - MARBLE_RADIUS) - (GATE_R + MARBLE_RADIUS)`, and that has to
    # stay near two marble diameters.
    R_WALL = 2.70
    WALL_RISE = 0.62
    # Inward, and rotationally symmetric so no bearing is special. Seven
    # degrees rather than five: with the rotor stopped this is the only thing
    # that seats the field against the ring and then feeds it through the
    # outlet, and five left racers loitering at the radius the paddles left
    # them at.
    FLOOR_TILT = 7.0
    RINGS = 72                     # points around the chamber

    # --- the rotor ----------------------------------------------------------
    PADDLES = 4
    TIP_R = 2.55                   # 0.15 inside the wall - see the docstring
    ROOT_R = 1.10                  # 0.15 outside the gate ring
    PADDLE_HEIGHT = 0.50
    PADDLE_THICK = 0.10
    FLOOR_CLEAR = 0.03
    # Tip speed 11.5 layout units per second at 5.0 rad/s, against a field
    # arriving at 10 to 15. Comparable rather than dominant: a blade much
    # faster than the marbles bats them instead of herding them, which is what
    # 12.0 rad/s did to the old wheel.
    ROTOR_RATE = 5.0
    # What the rotor slows *to* rather than stopping dead, and it is a
    # throughput fix rather than a flourish.
    #
    # At full rate the rotor centrifuges the field outward and the outlet
    # cannot draw it in - measured, six of eight racers simply stayed put when
    # the ring dropped. Stopped dead, the 7-degree floor has to deliver the
    # whole field on its own, and 7.5% of racers never reached the outlet at
    # all. Steepening the floor instead trades that for a centre bias: at 15
    # degrees the held fraction falls to 4.7% and the centre-versus-rank
    # correlation climbs to +0.64, because a floor steep enough to deliver is
    # a floor that packs the field against the closed outlet where the paddles
    # cannot get between them.
    #
    # A slow tail sweep is the way out of that trade: too slow to centrifuge,
    # fast enough to herd a straggler off the wall and let the shallow floor
    # take it.
    # **Zero, and the trade curve below is why.** Measured over 48 seeds each,
    # with everything else held:
    #
    #     tail rate   delivered   exit span   slot r
    #          0.0      91.41%        2.58    -0.100
    #          1.2      91.67%        3.75    -0.696
    #          2.2      96.35%        2.48    -0.866
    #
    # The sweep buys throughput and pays for it in fairness, monotonically.
    # That is not a tuning accident: delivering the field requires a rule that
    # reads where each marble *is*, and the field's positions still carry what
    # the mixing left of the bay. The faster the sweep, the more of that is
    # read back out. Zero keeps the fairness the architecture exists for and
    # leaves the throughput gate unmet, which is the honest configuration to
    # report.
    ROTOR_TAIL_RATE = 0.0
    ROTOR_PHASE = 0.0
    # **Whether the rotor holds still until the whole field is in the
    # chamber.** See `Rotor.angle_at`: turning from tick zero writes each bay
    # arrival time into its final bearing, and that is the residual the
    # pre-release measurement found and that no amount of mixing removes.
    # Off here so V1.7 recorded numbers stay reproducible in this class;
    # `sloped.startlab` scans it.
    ROTOR_HOLD_ENTRY = False
    # How far the paddle assembly rises once the mixing is done, and how long
    # it takes. **Zero here**: V1.7's outlet needs the blades where they are,
    # because a marble has to be persuaded toward a hole and a raised paddle
    # cannot do it. `ShuffleFloor` sets it - see `Rotor.lift_at`.
    ROTOR_LIFT = 0.0
    ROTOR_LIFT_OVER = 0.45
    # When the lift starts, as a fraction of the settle between the rotor
    # stopping and the release opening. A quarter of the way in, so the field
    # has begun to settle before the blades move and has time to settle again
    # after they have.
    ROTOR_LIFT_AT = 0.25

    # --- the outlet ---------------------------------------------------------
    #
    # A ring of segments that drops, rather than a plug that drops: the field
    # rests *against* it on the tilted floor at one radius, which is the
    # equal-distance-to-exit condition V1.4 went to such lengths for, and gets
    # it for free. Twelve segments so the polygon's own radius varies by 0.026
    # rather than the 0.084 an octagon gives.
    # **1.90 across, and that figure is measured rather than chosen.** At 1.50
    # - 2.6 marble diameters - eight racers arriving together arched over the
    # outlet and stopped: traced in simulation the whole field piled at radius
    # 0.34 to 0.52 and never left, with eight thousand marble-on-marble
    # contacts apiece. V1.5's drain is the precedent in both directions: a 1.24
    # hole arched and a 1.90 one passed 98.4% of the field.
    GATE_R = 0.95
    GATE_SEGMENTS = 12
    GATE_THICK = 0.06
    GATE_HEIGHT = 0.55
    # **Far enough to clear the exit chute, which is 1.80 and not 0.80.** The
    # ring retracts downward into the space the chute occupies, so a short
    # travel leaves it standing *in* the chute mouth as a cylindrical fence at
    # radius 0.89: traced in simulation the field went through the outlet and
    # then stopped dead against the retracted ring, five racers pinned inside
    # it at radius 0.55 for the rest of the run. The travel is measured against
    # the chute floor under the ring, and `tools/sloped_rotor_check.py`
    # asserts the clearance rather than trusting the number.
    GATE_DROP = 1.80
    GATE_DURATION = 0.16
    # When the outlet opens. Set from the measured time for the whole field to
    # be in the chamber plus the mixing interval; `chamber_table` reports the
    # margin and `tools/sloped_rotor_check.py` asserts it.
    ENTRY_ALLOWANCE = 1.30
    MIX_SECONDS = 1.50
    # After the rotor stops, before the outlet opens. Long enough for the field
    # to stop circulating and seat against the ring, so every racer leaves from
    # the same radius. See `Rotor`.
    SETTLE_SECONDS = 0.55
    SPIN_DOWN = 0.30

    # --- the exit -----------------------------------------------------------
    # As wide as the outlet, so the mouth does not pinch what the hole passes.
    CHUTE_HALF = 0.95
    CHUTE_WALL = 0.58
    # **How far *upstream* of the outlet the chute's mouth begins.** The outlet
    # is a hole 1.50 across centred on the chamber, so it spans 0.75 either
    # side of the chamber's own z - and a chute whose first ring is downstream
    # of that leaves the hole's upstream half opening onto nothing. Built that
    # way, every racer fell through and out of the machine: the start lab
    # reported no ranks at any checkpoint over 96 racers, with nothing
    # registered as lost because a marble that never touches a run is never
    # located on one either. The basin's notes record the same sign error in a
    # different shape.
    CHUTE_LEAD = 0.15              # clear of the hole's upstream edge
    CHUTE_STEPS = 14
    OUTLET_FALL = 0.40

    def __init__(
        self,
        module_id: str = "start",
        launch: TrackRun | None = None,
        rotor_phase: float | None = None,
        mix_seconds: float | None = None,
        rotor_rate: float | None = None,
        rotor_hold: bool | None = None,
    ) -> None:
        super().__init__(module_id, launch)
        self.rotor_hold = (
            self.ROTOR_HOLD_ENTRY if rotor_hold is None else bool(rotor_hold)
        )
        self.rotor_phase = self.ROTOR_PHASE if rotor_phase is None else float(rotor_phase)
        self.mix_seconds = self.MIX_SECONDS if mix_seconds is None else float(mix_seconds)
        self.rotor_rate = self.ROTOR_RATE if rotor_rate is None else float(rotor_rate)
        launch_entry = (
            launch.path[0] if launch is not None else layout.run("launch")["controls"][0]
        )
        angle = math.radians(self.yaw_deg)
        cos, sin = math.cos(angle), math.sin(angle)
        delta = tuple(launch_entry[axis] - self.origin[axis] for axis in range(3))
        plain = (
            delta[0] * cos - delta[2] * sin,
            delta[1],
            delta[0] * sin + delta[2] * cos,
        )
        self.apron_run = (self.CHAMBER_Z - self.R_WALL) - self._field_z()
        self.lift = self.derived_lift(plain)
        self.origin = (self.origin[0], self.origin[1] + self.lift, self.origin[2])
        self.exit_local = (plain[0], plain[1] - self.lift, plain[2])
        self._mesh: TriMesh | None = None
        self.gate_z = self._field_z() + layout.MARBLE_RADIUS + 0.06

    # --- the height chain, derived -----------------------------------------

    @property
    def pan_floor(self) -> float:
        return layout.DECK_TOP - 0.02 - self.PAN_SINK

    @property
    def apron_drop(self) -> float:
        return self.apron_run * math.tan(math.radians(self.APRON_GRADE))

    @property
    def rim_floor(self) -> float:
        """The chamber's floor at its wall: one height all the way round."""
        return self.pan_floor - self.apron_drop - self.INLET_STEP

    def floor_at(self, radius: float) -> float:
        """The chamber's floor at `radius`. Conical, so no azimuth is special."""
        span = max(self.R_WALL - max(radius, self.GATE_R), 0.0)
        return self.rim_floor - span * math.tan(math.radians(self.FLOOR_TILT))

    @property
    def rest_radius(self) -> float:
        """Where a marble comes to rest: against the gate ring, exactly."""
        return self.GATE_R + layout.MARBLE_RADIUS

    @property
    def outlet_lip(self) -> float:
        return self.floor_at(self.GATE_R) - self.OUTLET_FALL

    @property
    def chute_mouth_z(self) -> float:
        """Where the exit chute begins: clear of the outlet's upstream edge."""
        return self.CHAMBER_Z - self.GATE_R - self.CHUTE_LEAD

    def derived_lift(self, plain) -> float:
        """The elevation the chain needs, and no more.

        The radial start's 4.30 is not inherited and neither is the wide
        launch's 1.06: this chain has an apron, a chamber floor, an outlet fall
        and a chute, and the answer is what those four add up to against an
        exit chute at `CHUTE_GRADE`. Computed before the lift is applied, which
        is safe because the lift moves only `y`.
        """
        run = plain[2] - self.chute_mouth_z
        needed = (
            self.apron_drop
            + self.INLET_STEP
            + (self.R_WALL - self.GATE_R) * math.tan(math.radians(self.FLOOR_TILT))
            + self.OUTLET_FALL
            + run * math.tan(math.radians(self.CHUTE_GRADE))
        )
        seat = plain[1] + layout.FLOOR_Y
        return max(0.0, needed - (self.pan_floor - seat))

    # **The chute has to be steep enough to clear eight marbles at once**, not
    # merely steep enough for one to roll. At 11 degrees the field went through
    # the outlet and then stacked in the chute's mouth; V1.5's exit chute ran
    # at 30 degrees and cleared its field. 22 is what this chain affords
    # without pushing the lift past the radial start's.
    # 17 rather than 22, measured over 24 seeds: 22 degrees lost 3.65% of the
    # field to escapes on the launch's banked plunge and 17 lost 2.60%, with
    # no jams at either. Below about 15 the clump stacks in the chute instead
    # and the field stops entirely - 13 degrees delivered nothing at all. The
    # trade is real and it is between two different failures, not between a
    # failure and a margin.
    CHUTE_GRADE = 17.0

    def _field_z(self) -> float:
        return self.PAN_BACK + 0.66

    def _cradle(self, across: float, half: float, t: float = 0.0) -> float:
        """Flat. See the class comment on `PAN_BACK`."""
        return -self.PAN_SINK

    # --- the release timeline ----------------------------------------------

    @property
    def rotor_start(self) -> float:
        """When the rotor begins to turn.

        Zero unless `rotor_hold`, in which case it waits for the whole field to
        be in the chamber - the same `ENTRY_ALLOWANCE` that `rotor_stop` is
        already chained off, so the mixing interval keeps its length and only
        its placement moves.
        """
        if not self.rotor_hold:
            return 0.0
        return self.release_time + self.ENTRY_ALLOWANCE

    @property
    def rotor_stop(self) -> float:
        """When the rotor stops: after the field is in, plus the mixing."""
        return self.release_time + self.ENTRY_ALLOWANCE + self.mix_seconds

    @property
    def gate_time(self) -> float:
        """When the outlet opens: after the rotor has stopped and the field
        has settled against the ring.

        Chained off `release_time` - the visible start gate's own 0.30 - rather
        than typed, so a change to the start gate cannot leave the outlet
        opening before the field has arrived.
        """
        return self.rotor_stop + self.SPIN_DOWN + self.SETTLE_SECONDS

    @property
    def rotor_lift_time(self) -> float:
        """When the paddle assembly starts to rise.

        Inside the settle rather than after it, so raising the blades does not
        push the release later and does not change the interval the field has
        to come to rest in. Derived from the settle rather than typed, so a
        change to either cannot leave the lift happening after the floor has
        opened - which `tools/sloped_floor_check.py` asserts.
        """
        return (
            self.rotor_stop + self.SPIN_DOWN
            + self.ROTOR_LIFT_AT * self.SETTLE_SECONDS
        )

    @property
    def rotor_turns(self) -> float:
        """How many revolutions the rotor makes while it is turning."""
        return self.rotor_rate * (self.rotor_stop - self.rotor_start) / (2.0 * math.pi)

    # --- geometry ------------------------------------------------------------

    def _ring_point(self, radius: float, deg: float, y: float):
        angle = math.radians(deg)
        return (radius * math.cos(angle), y, self.CHAMBER_Z + radius * math.sin(angle))

    @property
    def inlet_half_deg(self) -> float:
        return math.degrees(math.asin(min(1.0, self.INLET_HALF / self.R_WALL)))

    def _in_inlet(self, deg: float) -> bool:
        """Is this bearing inside the wall's inlet gap? 270 is uphill."""
        return abs((deg - 270.0 + 180.0) % 360.0 - 180.0) <= self.inlet_half_deg

    def local_colliders(self) -> list[TriMesh]:
        if self._mesh is not None:
            return [self._mesh]
        pieces: list[TriMesh] = []
        pieces.extend(self._apron())
        pieces.extend(self._chamber())
        pieces.extend(self._exit_chute())
        pieces.append(self._backstop())
        self._mesh = merge_meshes(pieces, f"{self.id}_rotor")
        return [self._mesh]

    def apron_centre(self, u: float) -> tuple[float, float, float]:
        t = min(1.0, max(0.0, u))
        return (0.0, self.pan_floor - self.apron_drop * t,
                self._field_z() + self.apron_run * t)

    def apron_half(self, u: float) -> float:
        t = _ease(min(1.0, max(0.0, u)))
        return self.PAN_HALF + (self.INLET_HALF - self.PAN_HALF) * t

    def _apron(self) -> list[TriMesh]:
        """A short flat-across ramp from the resting line into the inlet.

        Flat across for the whole of it, and it ends 0.28 above the chamber's
        rim so the inlet is a step down. The heel behind the resting line is
        here for the reason it is in every other start in this tree: a marble
        seeded on the mesh's first row has its contact facet ending under its
        own centre and tips backwards off it. Learnt twice already.
        """
        rows: list[list[tuple[float, float, float]]] = []
        heel = -0.66 / max(self.apron_run, 1e-9)
        for step in range(-4, 33):
            u = heel * (-step / 4.0) if step < 0 else step / 32.0
            centre = self.apron_centre(u)
            half = self.apron_half(max(u, 0.0))
            if u < 0.0:
                centre = (0.0, self.pan_floor - self.apron_drop * u,
                          self._field_z() + self.apron_run * u)
            ring = [_place(self.origin, self.frame,
                           (-half - 0.24, centre[1] + 0.52, centre[2]))]
            for column in range(13):
                across = -half + 2.0 * half * column / 12
                ring.append(_place(self.origin, self.frame,
                                   (across, centre[1], centre[2])))
            ring.append(_place(self.origin, self.frame,
                               (half + 0.24, centre[1] + 0.52, centre[2])))
            rows.append(ring)
        return [_strip(rows, f"{self.id}_apron")]

    def _chamber(self) -> list[TriMesh]:
        """The conical floor and the wall, with a gap where the apron feeds in.

        Conical and not level: a level floor gives a marble no reason to reach
        the outlet when the gate drops, and a cone is the only inward gradient
        that is the same at every bearing. Five degrees is enough to seat the
        field against the ring and far too little to overcome a paddle.
        """
        pieces: list[TriMesh] = []
        rings: list[list[tuple[float, float, float]]] = []
        steps = 10
        for step in range(steps + 1):
            radius = self.R_WALL - (self.R_WALL - self.GATE_R) * step / steps
            y = self.floor_at(radius)
            rings.append([
                _place(self.origin, self.frame,
                       self._ring_point(radius, 360.0 * p / self.RINGS, y))
                for p in range(self.RINGS + 1)
            ])
        # And the outlet's lip, dropping away under the gate ring.
        rings.append([
            _place(self.origin, self.frame,
                   self._ring_point(self.GATE_R, 360.0 * p / self.RINGS,
                                    self.outlet_lip))
            for p in range(self.RINGS + 1)
        ])
        pieces.append(_strip(rings, f"{self.id}_floor"))

        # The wall, in the arcs the inlet does not occupy. Built as one strip
        # per arc rather than one strip with a hole, because a strip needs a
        # constant point count per ring.
        arc: list[float] = []
        for p in range(self.RINGS + 1):
            deg = 360.0 * p / self.RINGS
            if self._in_inlet(deg):
                if len(arc) > 1:
                    pieces.append(self._wall_arc(arc, len(pieces)))
                arc = []
            else:
                arc.append(deg)
        if len(arc) > 1:
            pieces.append(self._wall_arc(arc, len(pieces)))
        return pieces

    def _wall_arc(self, degrees, index: int) -> TriMesh:
        low = [
            _place(self.origin, self.frame,
                   self._ring_point(self.R_WALL, deg, self.rim_floor))
            for deg in degrees
        ]
        high = [
            _place(self.origin, self.frame,
                   self._ring_point(self.R_WALL, deg, self.rim_floor + self.WALL_RISE))
            for deg in degrees
        ]
        return _strip([low, high], f"{self.id}_wall{index}")

    def _backstop(self) -> TriMesh:
        floor = self.pan_floor
        corners = [
            (-self.PAN_HALF, floor, self.PAN_BACK),
            (self.PAN_HALF, floor, self.PAN_BACK),
            (self.PAN_HALF, floor + 0.46, self.PAN_BACK),
            (-self.PAN_HALF, floor + 0.46, self.PAN_BACK),
        ]
        return plate([_place(self.origin, self.frame, p) for p in corners],
                     name=f"{self.id}_backstop", steps=5)

    def _exit_chute(self) -> list[TriMesh]:
        """From under the outlet to the launch run's entry.

        **The chute starts well below the outlet and grows its walls
        afterwards**, which the basin's notes record the cost of getting wrong:
        full walls from the first ring stood 0.46 above the inner floor, came
        up through the hole and made a slot the field wedged in. A chute under
        a drain is a landing, and a landing has no kerb.
        """
        start = (0.0, self.outlet_lip - 0.24, self.chute_mouth_z)
        end = tuple(self.exit_local)
        rings: list[list[tuple[float, float, float]]] = []
        for step in range(self.CHUTE_STEPS + 1):
            t = step / self.CHUTE_STEPS
            centre = tuple(start[axis] + (end[axis] - start[axis]) * t for axis in range(3))
            half = self.CHUTE_HALF + (layout.CHANNEL_HALF - self.CHUTE_HALF) * t
            wall = self.CHUTE_WALL * _ease((t - 0.06) / 0.28)
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

    # --- the three actuators -------------------------------------------------

    def local_actuators(self) -> list[Actuator]:
        """The start paddles, the rotor, and the outlet ring.

        The start paddles are placed here rather than inherited:
        `StartGrid.local_actuators` reads `_t_at_z`, `_half_at` and `_path_at`,
        which describe the *fan's* trough, and V1.5's radial start inherited
        them and put a paddle out on its apron where a racer ran into it.
        """
        from marble3d.modules.base import LinearGate

        gates: list[Actuator] = []
        for index in range(layout.BAYS):
            gate_z = self._gate_z_for(index)
            u = (gate_z - self._field_z()) / max(self.apron_run, 1e-9)
            floor = self.pan_floor - self.apron_drop * max(u, 0.0)
            position = _place(
                self.origin, self.frame,
                (_bay_x(index), floor + 0.5 * layout.GATE_HEIGHT, gate_z),
            )
            gates.append(
                LinearGate(
                    name=f"paddle{index}",
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

        # The rotor. One `Spinner` per paddle, sharing a phase, turning about
        # the chamber's own axis - which is the module's up, so `lateral` and
        # `forward` are the module's x and z.
        span = self.TIP_R - self.ROOT_R
        # **From the floor at the TIP, not at the root.** A `Spinner` is a box
        # at one height and the chamber floor is a cone, so the underside has
        # to clear the highest floor the blade passes over - which is the
        # outermost, at the tip. Set from the root instead, the blade sat 0.093
        # *below* the floor at its tip and ploughed through it, while floating
        # 0.15 clear at its root. The remaining gap at the root is 0.15, which
        # is a quarter of a marble, so nothing can get under a blade anywhere.
        hub_y = self.floor_at(self.TIP_R) + self.FLOOR_CLEAR + 0.5 * self.PADDLE_HEIGHT
        hub = _place(self.origin, self.frame, (0.0, hub_y, self.CHAMBER_Z))
        for blade in range(self.PADDLES):
            gates.append(
                Rotor(
                    name=f"rotor{blade}",
                    # (half length along the arm, half height, half thickness):
                    # `basis_from_forward_up` puts the arm on local X, which is
                    # the axis order `Spinner` is written for.
                    half_extents=(
                        to_sim(0.5 * span),
                        to_sim(0.5 * self.PADDLE_HEIGHT),
                        to_sim(0.5 * self.PADDLE_THICK),
                    ),
                    hub=hub,
                    lateral=tuple(float(v) for v in self.frame[0]),
                    up=tuple(float(v) for v in self.frame[1]),
                    forward=tuple(float(v) for v in self.frame[2]),
                    radius=to_sim(0.5 * (self.ROOT_R + self.TIP_R)),
                    blade=blade,
                    blades=self.PADDLES,
                    phase=self.rotor_phase,
                    rate=self.rotor_rate,
                    start_time=self.rotor_start,
                    stop_time=self.rotor_stop,
                    spin_down=self.SPIN_DOWN,
                    tail_rate=self.ROTOR_TAIL_RATE,
                    lift_time=self.rotor_lift_time,
                    lift_by=to_sim(self.ROTOR_LIFT),
                    lift_over=self.ROTOR_LIFT_OVER,
                )
            )

        # The outlet ring: twelve segments that drop together.
        count = self.GATE_SEGMENTS
        for index in range(count):
            deg = 360.0 * (index + 0.5) / count
            angle = math.radians(deg)
            point = self._ring_point(
                self.GATE_R - self.GATE_THICK, deg,
                self.floor_at(self.GATE_R) + 0.5 * self.GATE_HEIGHT,
            )
            world = _place(self.origin, self.frame, point)
            radial = (math.cos(angle), 0.0, math.sin(angle))
            forward = tuple(
                self.frame[0][axis] * radial[0] + self.frame[2][axis] * radial[2]
                for axis in range(3)
            )
            gates.append(
                LinearGate(
                    name=f"outlet{index}",
                    half_extents=(
                        to_sim(self.GATE_THICK),
                        to_sim(0.5 * self.GATE_HEIGHT),
                        to_sim(self.GATE_R * math.tan(math.pi / count) + 0.05),
                    ),
                    rest=Transform(
                        position=world,
                        rotation=basis_from_forward_up(forward, self.frame[1]),
                    ),
                    travel=(0.0, -to_sim(self.GATE_DROP), 0.0),
                    release_time=self.gate_time,
                    duration=self.GATE_DURATION,
                )
            )
        return gates

    # --- what the simulation needs -------------------------------------------

    def marble_starts(self) -> list[Transform]:
        rotation = self._rotation()
        return [
            Transform(
                position=_place(
                    self.origin, self.frame,
                    (_bay_x(index), self.pan_floor + MARBLE_RADIUS,
                     self._field_z_for(index)),
                ),
                rotation=rotation,
            )
            for index in range(layout.BAYS)
        ]

    def local_sockets(self) -> dict[str, Socket]:
        seat = _place(self.origin, self.frame,
                      (0.0, self.exit_local[1] + layout.FLOOR_Y, self.exit_local[2]))
        forward = tuple(float(v) for v in self.frame[2])
        return {
            "exit": Socket(
                name="exit",
                frame=Transform(
                    position=seat,
                    rotation=basis_from_forward_up(forward, (0.0, 1.0, 0.0)),
                ),
                kind=GUIDED,
                width=to_sim(2.0 * layout.CHANNEL_HALF),
                height=to_sim(layout.CONTAINMENT_TOP - layout.FLOOR_Y),
            )
        }

    def local_bounds(self) -> Aabb:
        bounds = self.local_colliders()[0].aabb()
        return Aabb(
            tuple(value - MARBLE_DIAMETER for value in bounds.lower),
            tuple(value + MARBLE_DIAMETER for value in bounds.upper),
        )

    def local_probes(self) -> list[Probe]:
        """Floor rays down the apron and round the chamber.

        The rotor's sweep and the gate ring are skipped for the reason
        `StartGrid` skips its own gate rows: a probe fired where a kinematic
        body stands measures the paddle and reports the floor as missing.
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
        # Between the rotor's root and the wall, at bearings the inlet leaves
        # alone, and below the blades' underside.
        for radius in (self.R_WALL - 0.25, 0.5 * (self.GATE_R + self.R_WALL)):
            for point in range(0, self.RINGS, 9):
                deg = 360.0 * point / self.RINGS
                if self._in_inlet(deg):
                    continue
                surface = _place(self.origin, self.frame,
                                 self._ring_point(radius, deg, self.floor_at(radius)))
                probes.append(
                    Probe(
                        start=(surface[0], surface[1] + reach, surface[2]),
                        end=(surface[0], surface[1] - reach, surface[2]),
                        expect_hit=True,
                        expected_point=surface,
                        tolerance=0.05,
                        label=f"{self.id}.floor[{radius:.2f}@{deg:.0f}]",
                    )
                )
        return probes

    def describe(self) -> dict[str, Any]:
        table = chamber_table(self)
        return {
            "kind": "ShuffleChamber",
            "start_kind": self.START_KIND,
            "bays": layout.BAYS,
            "bay_pitch": round(to_sim(layout.BAY_PITCH), 6),
            "yaw_deg": round(self.yaw_deg, 4),
            "lift": round(self.lift, 4),
            "chamber": {
                "centre_z": self.CHAMBER_Z,
                "wall_radius": self.R_WALL,
                "width": round(2.0 * self.R_WALL, 4),
                "floor_tilt_deg": self.FLOOR_TILT,
                "inlet_half": self.INLET_HALF,
                "inlet_half_deg": round(self.inlet_half_deg, 3),
                "inlet_step": self.INLET_STEP,
            },
            "rotor": {
                "paddles": self.PADDLES,
                "root_radius": self.ROOT_R,
                "tip_radius": self.TIP_R,
                "rate": self.rotor_rate,
                "phase": round(self.rotor_phase, 9),
                "tip_speed": round(self.rotor_rate * self.TIP_R, 4),
                "turns_while_mixing": round(self.rotor_turns, 4),
                "holds_until_field_in": self.rotor_hold,
                "starts_at": round(self.rotor_start, 4),
                "stops_at": round(self.rotor_stop, 4),
                "lifts_by": self.ROTOR_LIFT,
                "lifts_at": round(self.rotor_lift_time, 4),
                "lifts_over": self.ROTOR_LIFT_OVER,
                "spin_down": self.SPIN_DOWN,
                "tail_rate": self.ROTOR_TAIL_RATE,
                "blade_floor_clearance": round(
                    (self.floor_at(self.TIP_R) + self.FLOOR_CLEAR)
                    - self.floor_at(self.ROOT_R), 4),
            },
            "outlet": {
                "gate_radius": self.GATE_R,
                "segments": self.GATE_SEGMENTS,
                "rest_radius": round(self.rest_radius, 6),
                "opens_at": round(self.gate_time, 4),
                "drop": self.GATE_DROP,
            },
            "release_time": self.release_time,
            "mix_seconds": self.mix_seconds,
            "settle_seconds": self.SETTLE_SECONDS,
            "heights": {
                "pan_floor": round(self.pan_floor, 4),
                "rim_floor": round(self.rim_floor, 4),
                "gate_floor": round(self.floor_at(self.GATE_R), 4),
                "outlet_lip": round(self.outlet_lip, 4),
            "chute_mouth_z": round(self.chute_mouth_z, 4),
            "chute_run": round(self.exit_local[2] - self.chute_mouth_z, 4),
            "chute_grade_deg": round(math.degrees(math.atan2(
                (self.outlet_lip - 0.24) - (self.exit_local[1] + layout.FLOOR_Y),
                self.exit_local[2] - self.chute_mouth_z)), 3),
                "exit_seat": round(self.exit_local[1] + layout.FLOOR_Y, 4),
            },
            "clearances": table["clearances"],
        }


def chamber_table(chamber: ShuffleChamber) -> dict:
    """The clearances the jam analysis turns on, all of them constant.

    Section 4 of the brief asks what caused the earlier wheel's jams and what
    is different here. The answer is in one column of this table: every gap a
    marble can be caught in is the same at every rotor angle, so none of them
    can close on it.
    """
    diameter = 2.0 * layout.MARBLE_RADIUS
    root_arc = 2.0 * math.pi * chamber.ROOT_R / chamber.PADDLES
    free = (chamber.R_WALL - layout.MARBLE_RADIUS) - chamber.rest_radius
    clearances = {
        "marble_diameter": round(diameter, 4),
        "tip_to_wall": round(chamber.R_WALL - chamber.TIP_R, 4),
        "root_to_gate_ring": round(chamber.ROOT_R - chamber.GATE_R, 4),
        "between_paddles_at_root": round(root_arc, 4),
        "free_radial_travel": round(free, 4),
        "free_radial_diameters": round(free / diameter, 3),
        "chamber_area": round(
            math.pi * (chamber.R_WALL ** 2 - chamber.GATE_R ** 2), 4),
        "field_area": round(8.0 * math.pi * layout.MARBLE_RADIUS ** 2, 4),
        "area_ratio": round(
            (chamber.R_WALL ** 2 - chamber.GATE_R ** 2)
            / (8.0 * layout.MARBLE_RADIUS ** 2), 3),
        "wall_polygon_error": 0.0,
        "gate_polygon_error": round(
            chamber.GATE_R * (1.0 / math.cos(math.pi / chamber.GATE_SEGMENTS) - 1.0), 4),
    }
    return {"clearances": clearances}

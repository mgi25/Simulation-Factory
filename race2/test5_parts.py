"""Physics-first mechanisms for Race #2 Test #5.

This module is deliberately separate from the frozen SWITCHYARD production
parts. Test #5 is a direct media experiment, not a Company OS job, and its
mechanisms must be proved in isolation before they are composed into a course.

P0 starts with Pendulum Cross because it fits the engine's existing actuator
contract exactly: its pose is a pure function of tick/time, while its effect on
race order comes from the racers' arrival phase.

A true Memory Rocker is intentionally NOT implemented here. The current
Actuator contract is kinematic and cannot react to marble contact; scripting a
rocker's tilt by time would violate the experiment's physical-cause rule. See
`docs/race2_test5_pendulum_p0.md` for the smallest architecture change that
would allow one.

## The arm's geometry is derived from the channel, not typed

The first implementation typed the arm as two pre-scale constants - a length of
2.30 and a pivot rise of 1.72 - and let `RaceRun.scale` multiply both. At Race
#2's scale of 2.0 that is a **4.60 arm hanging from a 3.44 pivot**, and the
arithmetic does not close. Measured on `cascade/corr1`, in layout units
relative to the channel centreline:

    angle   tip across   tip up   cradle   tip - cradle   wall gap
      0        +0.00      -1.16    -0.52       -0.64        +1.92
    +20        +1.57      -0.88    -0.24       -0.64        +0.34
    +45        +3.25      +0.19        -            -       -1.34

The arm was **0.64 layout units - 1.12 marble diameters - under the cradle at
every angle in its arc**, and past about 25 degrees its tip was outside the
guard rail while still below the rail's top, so the swept box passed through
the wall as well as the floor. A marble in that channel is not deflected by
that pendulum; it is scooped through the floor or crushed against a rail. Both
failures are silent - Bullet is content to let two non-dynamic bodies
interpenetrate - and neither is visible to a test that only asserts the pose is
a pure function of the tick.

`race2.parts.Wheel` records the same lesson from the other side: its parent's
tip radius was authored against Race #1's 0.94 half width and "installed
unchanged it sweeps 0.63 units through each wall ... the first three-concept run
left seven of eight racers stuck at two wheels". The fix there was to state the
reach as a **fraction of the local half width**. This module does the same, and
then derives everything else from it:

    reach       the furthest any part of the swept box goes across the channel,
                as a fraction of the local half width. The one safety number:
                `1 - reach` of half width has to stay wider than a marble, or
                the arm pins a racer against the rail.
    clearance   how far the arm passes above the cradle at the bottom of the
                swing, in layout units before the run's profile scale.
    amplitude   the swing angle.

    arm length  = (reach * half width - half depth * cos A) / sin A
    pivot rise  = whatever puts the *whole swept box* `clearance` above the
                  cradle at its worst angle - solved, not typed, because the
                  cradle is a circular arc and the box's low corner is not on
                  the centreline.

Amplitude and length are therefore coupled, and that coupling is the design
dial rather than a nuisance: for a fixed lateral reach, **a narrow-amplitude
pendulum is long and wipes across the lane at a constant height, and a
wide-amplitude one is short and lifts its tip toward the rail at each
extreme.** The lateral tip speed is `length * A * rate`, which for a fixed
reach is very nearly `reach * rate` at any amplitude - so `rate` sets how hard
the arm shoves and `amplitude` sets what the arm looks like doing it.

## A marble diameter beside the arm is not enough for a field

`race2.parts.Wheel` set the test for whether an obstacle is safe: leave more
than a marble diameter of clear channel beside it and "nothing is ever stopped
- a marble is deflected, delayed or let through". This module inherits that
test, and at `reach` 0.56 in a `W_LANE` corridor it passes it - 0.633 of clear
channel against a 0.570 marble.

It is a **single-marble** test, and a six-racer field does not arrive one at a
time. Measured on the P0 lab, seed 37: two racers come to a **dead stop**
against the arm and are released when it swings away, while the same seed on
the same course with the arm removed never drops a racer below 12.95 layout
units a second anywhere in the corridor. A 0.633 gap fits one marble with 0.063
to spare and cannot pass two abreast, so a pack queues.

So `describe()` reports the side gap in marble diameters as well, and flags
`pack_gate` under two of them. The queue is not a defect - it is where the
reordering comes from - but a mechanism that stops racers dead is a different
thing from one that deflects them, and the metadata should not call the first
one the second.

## The arm has to uncover the centreline, or it is a plug

The swing sweeps the arm's *axis* through `+/- length * sin(amplitude)`, and the
box carries `half depth` either side of that axis. If

    length * sin(amplitude) <= 0.5 * depth

then the box covers the channel's centreline **at every angle in the arc**, and
a marble - which its own cradle centres on that line - is held against the arm
for the rest of the race. Not delayed: held. Traced on the P0 lab, a racer sat
at `across` 0.000, resting on the cradle, with a zero gap to the box, through
every angle from -9.9 to +10.0 degrees, from 4 s to the 20 s limit.

The quantity is reported as `centre_uncovered` and a non-positive one is
refused. Measured over nine configurations and 450 races, it orders the failures
perfectly:

    uncovered  -0.099  -0.013  -0.008  +0.073  +0.078  +0.131  +0.136  +0.193
    racers      10       4       3       1       2       0       0       0
    pinned

So the constructor refuses `<= 0` because that case is provably a plug, and the
number is published because the margin matters: about +0.13 - half a marble
radius - was where pinning stopped in this channel.

**This is why a lower `reach` is not a safer one.** Reach sets the lateral
excursion, and lowering it shortens the arm; a shorter arm at the same amplitude
sweeps its axis a shorter distance while keeping its width, so it approaches the
plug condition from above. Over 50 seeds each, reach 0.40 finished all six in
76% of races and reach 0.60 in 94% - the opposite of what the side-gap reading
alone predicts.

## The channel bounds the amplitude from above

Worth writing down because it is not obvious: the pivot has to clear the rail it hangs over, so
`arm length` cannot fall below `rail top + pivot radius - cradle`. In a 3.01
unit corridor at `reach` 0.56 that caps the amplitude near 25 degrees. A wider
sample admits a wider swing, so *where along the run the pendulum stands* and
*how far it may swing* are one question, not two. `PendulumCross` raises rather
than building a geometry that violates either bound.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

from marble3d.geometry import Transform, basis_from_forward_up
from marble3d.mesh import Aabb, TriMesh
from marble3d.modules.base import Actuator, MarbleModule
from race2.track import RaceRun
from sloped import layout
from sloped.scale import SIM_TO_LAYOUT, to_sim
from sloped.solids import merge_meshes, tube

__all__ = ["PendulumArm", "PendulumCross"]


class PendulumArm(Actuator):
    """One rigid pendulum arm sweeping across a channel.

    Angle zero hangs straight down from the pivot. Positive angle moves the arm
    toward the run's lateral axis. The sinusoidal motion depends only on tick
    and dt, so it remains deterministic and replay-safe.

    The box is authored with its long axis on the arm, its `thickness` along the
    run's direction of travel - so the face a racer meets head on is thin - and
    its `depth` in the swing plane, which is the width of the blocker as the
    channel sees it.
    """

    def __init__(
        self,
        name: str,
        pivot: Sequence[float],
        lateral: Sequence[float],
        up: Sequence[float],
        forward: Sequence[float],
        length: float,
        thickness: float,
        depth: float,
        amplitude: float,
        rate: float,
        phase: float = 0.0,
    ) -> None:
        super().__init__(
            name,
            half_extents=(0.5 * float(length), 0.5 * float(thickness), 0.5 * float(depth)),
        )
        self.pivot = tuple(float(v) for v in pivot)
        self.lateral = tuple(float(v) for v in lateral)
        self.up = tuple(float(v) for v in up)
        self.forward = tuple(float(v) for v in forward)
        self.length = float(length)
        self.amplitude = float(amplitude)
        self.rate = float(rate)
        self.phase = float(phase)

        if self.length <= 0.0:
            raise ValueError("pendulum length must be positive")
        if not 0.0 < self.amplitude < math.pi / 2.0:
            raise ValueError("pendulum amplitude must be between 0 and 90 degrees")
        if self.rate <= 0.0:
            raise ValueError("pendulum rate must be positive")

    def angle_at(self, tick: int, dt: float) -> float:
        return self.amplitude * math.sin(self.phase + self.rate * tick * dt)

    def pose_for_angle(self, angle: float) -> Transform:
        """Where the arm is at one angle, with no reference to time.

        Separated from `pose_at` so the geometry can be surveyed - swept-box
        clearance against the cradle, lateral reach against the rail - without
        inventing a tick that happens to produce the angle wanted. The survey
        and the simulation then read the same pose law rather than two
        transcriptions of it.
        """
        arm = tuple(
            -self.up[axis] * math.cos(angle) + self.lateral[axis] * math.sin(angle)
            for axis in range(3)
        )
        centre = tuple(
            self.pivot[axis] + arm[axis] * (0.5 * self.length) for axis in range(3)
        )
        return Transform(
            position=centre,
            rotation=basis_from_forward_up(arm, self.forward),
        )

    def pose_at(self, tick: int, dt: float) -> Transform:
        return self.pose_for_angle(self.angle_at(tick, dt))

    def tip_at(self, angle: float) -> tuple[float, float, float]:
        """The far end of the arm's centre line, in simulation units."""
        return tuple(
            self.pivot[axis]
            + (-self.up[axis] * math.cos(angle) + self.lateral[axis] * math.sin(angle))
            * self.length
            for axis in range(3)
        )

    def to_json(self) -> dict[str, Any]:
        data = super().to_json()
        data.update(
            {
                "pivot": list(self.pivot),
                "length": self.length,
                "amplitude": self.amplitude,
                "rate": self.rate,
                "phase": self.phase,
            }
        )
        return data


class PendulumCross(MarbleModule):
    """A single large readable pendulum over one Race2 run.

    One actuator, one silhouette, no racer identity anywhere in it: the module
    knows a run, a sample index and four numbers, and the only thing that
    differs between two racers meeting it is *when they arrive*.
    """

    # The furthest any part of the swept box reaches across the channel, as a
    # fraction of the local half width. `race2.parts.Wheel` measured the regime
    # this number picks: under about 0.62 of half width there is more than a
    # marble diameter of clear channel beside the obstacle and nothing is ever
    # stopped dead, which is the difference between a disruptor and a jam.
    REACH = 0.56
    # How far the swept box passes above the cradle at its lowest, in layout
    # units before the run's profile scale. 0.05 is 0.10 layout units at Race
    # #2's scale - a third of a marble radius, so a racer cannot pass under the
    # arm and the arm cannot scrape the floor.
    CLEARANCE = 0.05
    AMPLITUDE_DEG = 14.0
    RATE = 3.0
    # Along the direction of travel: the face a racer meets head on.
    ARM_THICKNESS = 0.18
    # Across the swing plane: the width of the blocker as the channel sees it.
    ARM_DEPTH = 0.34
    # The axle, and how far it reaches either side of the channel.
    PIVOT_RADIUS = 0.10
    PIVOT_HALF_SPAN = 0.42
    # How far above the rail the axle has to sit before the pendulum is a thing
    # hanging over the channel rather than a thing inside it.
    PIVOT_MARGIN = 0.10

    def __init__(
        self,
        module_id: str,
        run: RaceRun,
        at: int,
        *,
        amplitude_deg: float | None = None,
        rate: float | None = None,
        phase: float = 0.0,
        reach: float | None = None,
        clearance: float | None = None,
    ) -> None:
        super().__init__(module_id)
        self.run = run
        self.index = min(max(int(at), 1), len(run.path) - 2)
        self.amplitude = math.radians(
            self.AMPLITUDE_DEG if amplitude_deg is None else float(amplitude_deg)
        )
        self.rate = self.RATE if rate is None else float(rate)
        self.phase = float(phase)
        self.reach = self.REACH if reach is None else float(reach)
        self.clearance = self.CLEARANCE if clearance is None else float(clearance)
        self._mesh: TriMesh | None = None
        self._actuators: list[Actuator] | None = None
        self._bounds: Aabb | None = None

        self.scale = float(run.scale)
        self.width_factor = float(run.widths[self.index])
        if not 0.0 < self.reach < 1.0:
            raise ValueError(
                f"{module_id}: reach is a fraction of the local half width, got {self.reach}"
            )
        if not 0.0 < self.amplitude < math.pi / 2.0:
            raise ValueError(f"{module_id}: amplitude must be between 0 and 90 degrees")
        if self.rate <= 0.0:
            raise ValueError(f"{module_id}: rate must be positive")

        # --- the derived geometry, all in layout units --------------------
        self.thickness = self.ARM_THICKNESS * self.scale
        self.depth = self.ARM_DEPTH * self.scale
        self.reach_across = self.reach * self.half_width()
        length = (
            self.reach_across - 0.5 * self.depth * math.cos(self.amplitude)
        ) / math.sin(self.amplitude)
        if length <= 0.0:
            raise ValueError(
                f"{module_id}: a {self.depth:.2f}-wide arm cannot reach "
                f"{self.reach_across:.2f} across at {math.degrees(self.amplitude):.1f} "
                "degrees - lower the reach, widen the amplitude or thin the arm"
            )
        self.arm_length = length
        self.pivot_rise, self.swept_across = self._solve_rise()

        if self.side_gap() < 2.0 * layout.MARBLE_RADIUS:
            raise ValueError(
                f"{module_id}: {self.side_gap():.3f} of clear channel beside the arm "
                f"is under a {2.0 * layout.MARBLE_RADIUS:.3f} marble - it would pin a "
                "racer against the rail; lower the reach"
            )
        uncovered = self.centre_uncovered()
        if uncovered <= 0.0:
            raise ValueError(
                f"{module_id}: the arm sweeps its axis "
                f"{self.arm_length * math.sin(self.amplitude):.3f} across and is "
                f"{self.depth:.3f} wide, so the swept box never uncovers the "
                f"channel centreline ({uncovered:+.3f}) - it would hold a racer "
                "there for the whole race rather than deflect it; raise the reach "
                "or the amplitude, or thin the arm"
            )
        floor = self.axle_floor()
        if self.pivot_rise < floor:
            raise ValueError(
                f"{module_id}: the axle would sit at {self.pivot_rise:.3f} above the "
                f"centreline, under the {floor:.3f} the rail needs - the arm is too "
                f"short for a {math.degrees(self.amplitude):.1f}-degree swing here; "
                "narrow the amplitude or stand it in a wider sample"
            )

    # --- the channel this pendulum is standing in ------------------------

    def half_width(self) -> float:
        """The clear half channel at the pendulum, in layout units."""
        return layout.CHANNEL_HALF * self.scale * self.width_factor

    def side_gap(self) -> float:
        """Clear channel between the arm's outermost reach and the rail.

        Reported for the same reason `Wheel.side_gap` is: it is the number that
        decides whether the mechanism is a disruptor or a trap, and one that
        has quietly fallen under a marble diameter is one that will pin a racer
        on the seed nobody ran.
        """
        return self.half_width() - self.swept_across

    def side_gap_marbles(self) -> float:
        """The side gap in marble diameters - the number a field cares about.

        Under 1.0 the arm can pin a racer against the rail and the constructor
        refuses it. Under 2.0 two racers cannot pass abreast, so a pack queues
        rather than filtering through; see the module docstring.
        """
        return self.side_gap() / (2.0 * layout.MARBLE_RADIUS)

    def pack_gate(self) -> bool:
        """Would a field of racers queue here rather than filter through?"""
        return self.side_gap_marbles() < 2.0

    def centre_uncovered(self) -> float:
        """How far past the centreline the box's inner edge retreats, in layout.

        Non-positive means the swept box covers the channel's centre at every
        angle in the arc, and a marble centred there is held for the whole
        race. See the module docstring for the measurement.
        """
        return self.arm_length * math.sin(self.amplitude) - 0.5 * self.depth

    def cradle_floor(self) -> float:
        """The cradle's lowest point, in layout units below the centreline."""
        return layout.FLOOR_Y * self.scale

    def rail_top(self) -> float:
        """The top of the capped rail at this sample, in layout units."""
        return (
            self.cradle_floor()
            + self.run.wall_cap
            + self.run.guard_extra(self.index)
        )

    def axle_floor(self) -> float:
        """The lowest the axle may sit and still be over the channel."""
        return (
            self.rail_top()
            + self.PIVOT_RADIUS * self.scale
            + self.PIVOT_MARGIN * self.scale
        )

    # --- the swing, surveyed rather than trusted --------------------------

    SURVEY_SAMPLES = 121

    def _frame(self):
        return self.run.frames[self.index]

    def _arm(self, pivot_rise: float) -> PendulumArm:
        lateral, up, forward = self._frame()
        centre = self.run.sim_path[self.index]
        pivot = tuple(
            centre[axis] + up[axis] * to_sim(pivot_rise) for axis in range(3)
        )
        return PendulumArm(
            name="arm",
            pivot=pivot,
            lateral=lateral,
            up=up,
            forward=forward,
            length=to_sim(self.arm_length),
            thickness=to_sim(self.thickness),
            depth=to_sim(self.depth),
            amplitude=self.amplitude,
            rate=self.rate,
            phase=self.phase,
        )

    def _survey(self, pivot_rise: float) -> tuple[float, float]:
        """(worst box-to-cradle clearance, furthest reach across), in layout.

        Every corner of the swept box at every sampled angle, projected onto
        the run's own lateral and up axes and compared against the cradle arc
        `TrackRun.surface_point` is built from. The box's lowest corner is not
        on the centreline and the cradle is not flat, so this is a survey and
        not a subtraction.
        """
        arm = self._arm(pivot_rise)
        lateral, up, _forward = self._frame()
        centre = self.run.sim_path[self.index]
        hx, hy, hz = arm.half_extents
        worst_clear = math.inf
        worst_across = 0.0
        for step in range(self.SURVEY_SAMPLES):
            angle = -self.amplitude + 2.0 * self.amplitude * step / (self.SURVEY_SAMPLES - 1)
            pose = arm.pose_for_angle(angle)
            for sx in (-1.0, 1.0):
                for sy in (-1.0, 1.0):
                    for sz in (-1.0, 1.0):
                        point = pose.apply((sx * hx, sy * hy, sz * hz))
                        offset = [point[axis] - centre[axis] for axis in range(3)]
                        across = (
                            sum(offset[axis] * lateral[axis] for axis in range(3))
                            * SIM_TO_LAYOUT
                        )
                        height = (
                            sum(offset[axis] * up[axis] for axis in range(3))
                            * SIM_TO_LAYOUT
                        )
                        profile = across / (self.scale * max(self.width_factor, 1e-9))
                        cradle = layout.floor_y_at(profile) * self.scale
                        worst_clear = min(worst_clear, height - cradle)
                        worst_across = max(worst_across, abs(across))
        return worst_clear, worst_across

    def _solve_rise(self) -> tuple[float, float]:
        """The pivot height that puts the swung box `clearance` off the cradle.

        The whole box translates with the pivot along the run's up axis, so the
        worst clearance is *affine* in the rise with unit slope and one survey
        at a trial rise settles it exactly. No search, no tolerance.
        """
        trial, across = self._survey(0.0)
        rise = self.clearance * self.scale - trial
        return rise, across

    def clearances(self) -> tuple[float, float]:
        """The built geometry's own (worst cradle clearance, reach), measured.

        Recomputed from the arm the simulation is handed rather than returned
        from the solve, so a test can assert the fix held rather than assert
        the arithmetic that was supposed to produce it.
        """
        return self._survey(self.pivot_rise)

    # --- the module contract ---------------------------------------------

    def _pivot(self) -> tuple[float, float, float]:
        _lateral, up, _forward = self._frame()
        centre = self.run.sim_path[self.index]
        rise = to_sim(self.pivot_rise)
        return tuple(centre[axis] + up[axis] * rise for axis in range(3))

    def local_actuators(self) -> list[Actuator]:
        """The one arm, built once.

        `BuiltModule.apply_actuators` calls this every tick, so the arm is
        cached: it holds no per-tick state - the pose is a function of the tick
        it is handed - and rebuilding it 240 times a second would be work for
        nothing.
        """
        if self._actuators is None:
            self._actuators = [self._arm(self.pivot_rise)]
        return self._actuators

    def local_colliders(self) -> list[TriMesh]:
        if self._mesh is not None:
            return [self._mesh]
        _lateral, _up, forward = self._frame()
        pivot = self._pivot()
        half = to_sim(self.PIVOT_HALF_SPAN * self.scale)
        a = tuple(pivot[axis] - forward[axis] * half for axis in range(3))
        b = tuple(pivot[axis] + forward[axis] * half for axis in range(3))
        self._mesh = merge_meshes(
            [
                tube(
                    a,
                    b,
                    to_sim(self.PIVOT_RADIUS * self.scale),
                    segments=10,
                    name=f"{self.id}_pivot",
                    caps=True,
                )
            ],
            name=f"{self.id}_fixed",
        )
        return [self._mesh]

    def local_sockets(self) -> dict:
        return {}

    def local_bounds(self) -> Aabb:
        """The swept volume, not a cube of the arm's reach.

        `Machine.module_at` resolves an overlap by picking the *smallest* box
        that contains the point, so a module that claims a cube two arm lengths
        on a side takes the attribution away from the run it is standing in for
        every marble anywhere near it. This claims what the arm can actually
        touch: the axle, the swept box, and a marble diameter of slack.

        **Cached, and that is not an optimisation.** `Machine.module_at` asks
        every module for its bounds for every marble on every locate, and
        `MarbleModule.bounds` gets there through `local_bounds`. Surveying 121
        angles by 8 corners inside that call cost 15 seconds of wall clock per
        30-second seed against the same course with the arm left out - five
        times the whole race. The swept volume cannot change once the arm is
        built, so it is measured once.
        """
        if self._bounds is not None:
            return self._bounds
        arm = self.local_actuators()[0]
        hx, hy, hz = arm.half_extents
        points: list[tuple[float, float, float]] = [self._pivot()]
        for step in range(self.SURVEY_SAMPLES):
            angle = -self.amplitude + 2.0 * self.amplitude * step / (self.SURVEY_SAMPLES - 1)
            pose = arm.pose_for_angle(angle)
            for sx in (-1.0, 1.0):
                for sy in (-1.0, 1.0):
                    for sz in (-1.0, 1.0):
                        points.append(pose.apply((sx * hx, sy * hy, sz * hz)))
        slack = to_sim(2.0 * layout.MARBLE_RADIUS)
        lower = tuple(min(p[axis] for p in points) - slack for axis in range(3))
        upper = tuple(max(p[axis] for p in points) + slack for axis in range(3))
        self._bounds = Aabb(lower, upper)
        return self._bounds

    # --- description ------------------------------------------------------

    def period(self) -> float:
        """One full back-and-forth, in seconds."""
        return 2.0 * math.pi / self.rate

    def sweep_speed(self) -> float:
        """Peak lateral speed of the arm's tip, in layout units a second."""
        return self.arm_length * self.amplitude * self.rate

    def blocked_fraction(self) -> float:
        """How much of the clear channel a racer cannot use at one instant.

        The arm's own width plus a marble either side, over the clear width.
        The quantity that decides how often the mechanism is met at all, and
        therefore the one to read next to a rank-change rate.
        """
        blocked = self.depth + 2.0 * layout.MARBLE_RADIUS
        return min(1.0, blocked / (2.0 * self.half_width()))

    def swept_fraction(self) -> float:
        """How much of the clear channel the arm crosses over a full period."""
        return min(1.0, (2.0 * self.swept_across) / (2.0 * self.half_width()))

    def describe(self) -> dict[str, Any]:
        clear, across = self.clearances()
        return {
            "kind": "PendulumCross",
            "on": self.run.id,
            "sample": self.index,
            "amplitude_deg": round(math.degrees(self.amplitude), 3),
            "rate": round(self.rate, 6),
            "phase": round(self.phase, 6),
            "period": round(self.period(), 4),
            "reach": round(self.reach, 4),
            "arm_length": round(self.arm_length, 4),
            "pivot_rise": round(self.pivot_rise, 4),
            "half_width": round(self.half_width(), 4),
            "side_gap": round(self.side_gap(), 4),
            "side_gap_marbles": round(self.side_gap_marbles(), 4),
            "centre_uncovered": round(self.centre_uncovered(), 4),
            "rail_top": round(self.rail_top(), 4),
            "cradle_clearance": round(clear, 4),
            "reach_across": round(across, 4),
            "sweep_speed": round(self.sweep_speed(), 4),
            "blocked_fraction": round(self.blocked_fraction(), 4),
            "swept_fraction": round(self.swept_fraction(), 4),
            # `gate` is `Wheel`'s single-marble test, kept so the two modules
            # report the same thing by the same name. `pack_gate` is the one a
            # six-racer field is actually decided by.
            "gate": self.side_gap() < 2.0 * layout.MARBLE_RADIUS,
            "pack_gate": self.pack_gate(),
            "reactive": False,
            "selection": "arrival_phase_only",
        }

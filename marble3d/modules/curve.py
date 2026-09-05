"""The curve: a banked helical channel that runs underneath the bowl.

This module exists to be the thing the old architecture could not be. A height
field `y = f(x, z)` is single-valued, so it can express a bowl, a funnel and a
banked bend, and it cannot express two surfaces over one ground point. This
curve starts directly under the bowl's drain and turns through three quarters
of a circle at a radius well inside the bowl's own, so for most of its length
there is bowl above it and channel below it at the same `(x, z)`. That is the
whole of the argument in section 9 of the lab's comparison, made as geometry.

Three parts, and each is a real feature rather than a demonstration of one:

* **A catch.** A marble arriving here has fallen out of a drain and is moving
  mostly downwards. The channel therefore starts wider than the drain it is
  fed by and narrows to its running width over the first stretch, with taller
  walls, because a marble can leave a 3-diameter hole anywhere across its
  width and something has to be under all of it.
* **A descent that is level at both ends.** `f(t) = t - sin(2 pi t) / (2 pi)`
  descends the full drop with zero gradient at the entry and the exit and
  twice the mean gradient in the middle. Level at the entry is what lets the
  catch work; level at the exit is what makes the exit socket a sane thing for
  a future module to connect to.
* **Banking, ramped in and out.** `tan(bank) = v^2 / (g R)` is the angle at
  which a marble at speed v needs no sideways force from the wall at all, and
  `bank_angle` is set from the speed the drop actually produces rather than
  from what looks right. It ramps from zero over the first fifth and back to
  zero over the last, so the sockets at both ends are level in roll as well as
  in pitch.

The channel is a gutter rather than a flat floor with walls: a marble in a flat
channel wanders across it and ticks off each wall in turn, and a marble in a
gutter is centred by its own weight. See `channel_section`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from marble3d.geometry import (
    GUIDED,
    Socket,
    Transform,
    basis_from_forward_up,
    quat_from_axis_angle,
    quat_multiply,
    quat_rotate,
)
from marble3d.mesh import TriMesh, segments_for_sagitta, sweep, worst_sagitta
from marble3d.modules.base import MarbleModule, Probe, channel_section
from marble3d.units import GRAVITY, MARBLE_DIAMETER, MARBLE_RADIUS

__all__ = ["CurveSpec", "CurveModule", "bank_for_speed"]


def bank_for_speed(speed: float, radius: float, gravity: float = GRAVITY) -> float:
    """The bank angle at which a marble needs no lateral force from the wall.

    `tan(theta) = v^2 / (g R)`, the standard banked-turn result. Quoted because
    a bank chosen this way is a physical statement about a speed, and a bank
    chosen any other way is decoration that the marble then fights.
    """
    return math.atan(speed * speed / (gravity * radius))


@dataclass(frozen=True)
class CurveSpec:
    """Every number the curve is made of, in world units."""

    radius: float = 7.0
    sweep_degrees: float = 270.0
    drop: float = 6.0
    design_speed: float = 30.0
    # The floor's gradient at the entry, as a fraction of the mean. Has to
    # clear 0.184 for the descent cubic to stay monotone, and has to be well
    # clear of zero or the catch is a flat spot marbles pile up on.
    entry_gradient: float = 1.5

    width: float = 4.0 * MARBLE_RADIUS
    wall: float = 2.0 * MARBLE_RADIUS
    # Floor arc radius as a multiple of the channel width. Must exceed 0.5 or
    # the gutter closes over the marble; at 0.667 the floor rises 0.23 of the
    # width at its edges, which is deep enough to centre a marble and shallow
    # enough that it is not a groove the marble cannot climb out of when it is
    # meant to be thrown against the outside of a bend.
    floor_ratio: float = 0.667

    # The catch, at the entry. Wider than the drain that feeds it.
    catch_width: float = 10.0 * MARBLE_RADIUS
    catch_wall: float = 3.0 * MARBLE_RADIUS
    catch_length: float = 4.0           # arc length over which it narrows
    # How far the catch reaches *behind* its own entry socket, and how far its
    # floor curls up at that end. Both are load-bearing and neither was in the
    # first version, which is why the first version dropped every marble.
    #
    # A marble leaving a drain is not travelling in the drain's nominal
    # direction. It is travelling wherever its last orbit left it pointing,
    # which over eight marbles and one bowl is every direction there is - and
    # the trace showed them leaving *backwards* relative to the channel they
    # were falling into, landing behind where the geometry started and falling
    # through the machine. A catch under a drain has to be a basin, not the end
    # of a pipe: it reaches back past the hole by more than the hole's own
    # radius plus a marble, and its back end curls up into a scoop that returns
    # a backwards-moving marble to the flow.
    lead_in: float = 3.0
    lead_rise: float = 1.5

    bank_ramp: float = 0.2              # fraction of the run spent ramping bank
    sagitta_limit: float = 0.02

    @property
    def sweep(self) -> float:
        return math.radians(self.sweep_degrees)

    @property
    def arc_length(self) -> float:
        return self.radius * self.sweep

    def bank_angle(self) -> float:
        return bank_for_speed(self.design_speed, self.radius)

    def to_json(self) -> dict[str, Any]:
        return {
            "radius": self.radius,
            "sweep_degrees": self.sweep_degrees,
            "drop": self.drop,
            "arc_length": self.arc_length,
            "design_speed": self.design_speed,
            "bank_deg": math.degrees(self.bank_angle()),
            "width": self.width,
            "wall": self.wall,
            "catch_width": self.catch_width,
            "mean_gradient": self.drop / self.arc_length,
            "max_gradient": 2.0 * self.drop / self.arc_length,
        }


class CurveModule(MarbleModule):
    """A banked descending arc with a catch at its head.

    Local frame: the origin is the entry, +X the direction of travel there,
    +Y up. The arc turns toward +Z - to the right, looking along the flow -
    about a centre at (0, 0, `radius`).
    """

    def __init__(self, module_id: str = "curve", spec: CurveSpec | None = None) -> None:
        super().__init__(module_id)
        self.spec = spec or CurveSpec()
        self._validate()
        self.frames_along = segments_for_sagitta(self.spec.radius, self.spec.sagitta_limit)
        self.sagitta = worst_sagitta(self.spec.radius, self.frames_along)
        # `segments_for_sagitta` sizes a full circle; this arc is a fraction of
        # one, so the frame count scales with it - and never below a count that
        # resolves the catch taper.
        turns = self.spec.sweep / (2.0 * math.pi)
        self.frame_count = max(24, int(math.ceil(self.frames_along * turns)))
        self._meshes: list[TriMesh] | None = None

    def _validate(self) -> None:
        spec = self.spec
        if spec.width <= MARBLE_DIAMETER:
            raise ValueError(f"a channel {spec.width} wide does not pass a marble")
        if spec.catch_width < spec.width:
            raise ValueError("the catch cannot be narrower than the channel it feeds")
        if not 0.0 < spec.bank_ramp <= 0.5:
            raise ValueError("the bank ramp is a fraction of the run, at most half of it")
        if spec.catch_length >= spec.arc_length:
            raise ValueError("the catch cannot be longer than the curve")
        if spec.lead_in <= 0.0 or spec.lead_rise <= 0.0:
            raise ValueError("a catch under a drain needs a lead-in and a back scoop")
        if spec.entry_gradient < 0.184:
            raise ValueError(
                f"entry_gradient {spec.entry_gradient} makes the descent cubic "
                "non-monotone: the channel would climb somewhere in the middle"
            )

    # --- the path --------------------------------------------------------

    def _shape(self, fraction: float) -> tuple[float, float]:
        """The descent shape and its derivative, both as fractions of the drop.

        `f(t) = g t + (3 - 2g) t^2 + (g - 2) t^3`, the unique cubic with
        `f(0) = 0`, `f(1) = 1`, `f'(0) = g` and `f'(1) = 0`. Level at the exit,
        because an exit socket a future module connects to should be level; and
        emphatically *not* level at the entry, which is the version this
        started as and is why every marble in the first working run stopped
        dead in the catch. A catch whose floor is flat where the marbles land
        is a catch that fills up, and eight marbles in a narrowing channel with
        nowhere to go is a jam that no amount of solver iterations fixes.

        `g >= 0.184` keeps `f'` from going negative anywhere on [0, 1]; the
        default is well clear of it.
        """
        g = self.spec.entry_gradient
        value = g * fraction + (3.0 - 2.0 * g) * fraction**2 + (g - 2.0) * fraction**3
        slope = g + 2.0 * (3.0 - 2.0 * g) * fraction + 3.0 * (g - 2.0) * fraction * fraction
        return value, slope

    def height(self, fraction: float) -> float:
        """Where the channel floor is, `fraction` of the way along.

        Behind the entry socket - negative `fraction` - the same cubic carries
        on, and a quadratic scoop is added on top of it. The scoop's value and
        its gradient are both zero at the socket, so the entry frame is exactly
        what it would be without one and the join upstream is unaffected.
        """
        spec = self.spec
        drop = -spec.drop * self._shape(fraction)[0]
        if fraction >= 0.0:
            return drop
        behind = -fraction * spec.arc_length
        return drop + spec.lead_rise * (behind / spec.lead_in) ** 2

    def _gradient(self, fraction: float) -> float:
        """d(height)/d(fraction), analytically, including the scoop."""
        spec = self.spec
        gradient = -spec.drop * self._shape(fraction)[1]
        if fraction < 0.0:
            behind = -fraction * spec.arc_length
            gradient -= 2.0 * spec.lead_rise * behind * spec.arc_length / spec.lead_in**2
        return gradient

    def gradient_at(self, fraction: float) -> float:
        """The floor's slope as a tangent, which is what a marble feels."""
        return self._gradient(fraction) / self.spec.arc_length

    def _bank(self, fraction: float) -> float:
        ramp = self.spec.bank_ramp
        if fraction <= ramp:
            u = fraction / ramp
        elif fraction >= 1.0 - ramp:
            u = (1.0 - fraction) / ramp
        else:
            u = 1.0
        return self.spec.bank_angle() * u * u * (3.0 - 2.0 * u)

    def frame_at(self, fraction: float) -> Transform:
        """The channel frame at `fraction` of the way along the arc."""
        spec = self.spec
        angle = spec.sweep * fraction
        position = (
            spec.radius * math.sin(angle),
            self.height(fraction),
            spec.radius * (1.0 - math.cos(angle)),
        )
        # d/dfraction of the plan position, and of the height, gives the
        # tangent without a finite difference - so the frames are exact and a
        # coarser tessellation does not tilt them.
        gradient = self._gradient(fraction)
        forward = (
            spec.radius * spec.sweep * math.cos(angle),
            gradient,
            spec.radius * spec.sweep * math.sin(angle),
        )
        base = basis_from_forward_up(forward, (0.0, 1.0, 0.0))
        # Rolling about the forward axis tilts the frame's up toward +Z, which
        # is the inside of the turn - so a positive bank is banking into it.
        roll = quat_from_axis_angle(quat_rotate(base, (1.0, 0.0, 0.0)), self._bank(fraction))
        return Transform(position, quat_multiply(roll, base))

    def _section_at(self, fraction: float) -> list[tuple[float, float]]:
        spec = self.spec
        travelled = max(0.0, fraction) * spec.arc_length
        blend = min(1.0, travelled / spec.catch_length)
        smooth = blend * blend * (3.0 - 2.0 * blend)
        width = spec.catch_width + (spec.width - spec.catch_width) * smooth
        wall = spec.catch_wall + (spec.wall - spec.catch_wall) * smooth
        return channel_section(width, wall, spec.floor_ratio * width)

    def _fractions(self) -> list[float]:
        """Sweep parameters, from behind the catch to the exit.

        Uniform in arc length across the whole thing, lead-in included, so the
        scoop is tessellated at the same resolution as the channel rather than
        being one long triangle across the part a marble lands on hardest.
        """
        spec = self.spec
        total = spec.lead_in + spec.arc_length
        count = max(self.frame_count, int(math.ceil(total / (spec.arc_length / self.frame_count))))
        start = -spec.lead_in / spec.arc_length
        span = 1.0 - start
        return [start + span * index / count for index in range(count + 1)]

    def local_colliders(self) -> list[TriMesh]:
        if self._meshes is None:
            fractions = self._fractions()
            frames = [self.frame_at(fraction) for fraction in fractions]
            sections = [self._section_at(fraction) for fraction in fractions]
            self._meshes = [sweep(sections, frames, name=f"{self.id}_channel")]
        return self._meshes

    # --- sockets ---------------------------------------------------------

    def local_sockets(self) -> dict[str, Socket]:
        spec = self.spec
        return {
            "entry": Socket(
                name="entry",
                frame=self.frame_at(0.0),
                kind=GUIDED,
                width=spec.catch_width,
                height=spec.catch_wall,
            ),
            "exit": Socket(
                name="exit",
                frame=self.frame_at(1.0),
                kind=GUIDED,
                width=spec.width,
                height=spec.wall,
            ),
        }

    # --- probes ----------------------------------------------------------

    def local_probes(self) -> list[Probe]:
        """Rays along the channel, from inside it, proving floor and both walls.

        Stated in the *frame*, not in world axes, which is the point: on a
        banked descending helix "down" is not -Y, and a probe that assumed it
        was would drift off the floor exactly where the bank is steepest and
        report a hole that is not there. The frames the probe uses are the same
        frames the mesh was swept along, so the two can only disagree if the
        mesh did not arrive.
        """
        spec = self.spec
        probes: list[Probe] = []
        samples = 60
        start = -spec.lead_in / spec.arc_length
        for index in range(samples):
            fraction = start + (1.0 - start) * (index + 0.5) / samples
            frame = self.frame_at(fraction)
            section = self._section_at(fraction)
            width = 2.0 * max(across for across, _ in section)
            probes.append(
                Probe(
                    start=frame.apply((0.0, 3.0 * MARBLE_RADIUS, 0.0)),
                    end=frame.apply((0.0, -2.0 * MARBLE_DIAMETER, 0.0)),
                    expect_hit=True,
                    expected_point=frame.apply((0.0, 0.0, 0.0)),
                    # The swept strip is a chord between frames, so a ray fired
                    # between two of them lands slightly inside the true arc.
                    tolerance=2.0 * self.sagitta + 0.05,
                    label=f"{self.id}.floor t={fraction:.2f}",
                )
            )
            for side in (-1.0, 1.0):
                probes.append(
                    Probe(
                        start=frame.apply((0.0, MARBLE_RADIUS, 0.0)),
                        end=frame.apply((0.0, MARBLE_RADIUS, side * (0.5 * width + MARBLE_DIAMETER))),
                        expect_hit=True,
                        tolerance=width,
                        label=f"{self.id}.wall t={fraction:.2f}",
                    )
                )
        return probes

    def describe(self) -> dict[str, Any]:
        return {
            "spec": self.spec.to_json(),
            "frames": self.frame_count,
            "sagitta": self.sagitta,
            "sagitta_over_marble_radius": self.sagitta / MARBLE_RADIUS,
        }

"""The start: a queue of marbles, a gate, and a chute that eases out level.

Deliberately the plainest module in the machine. Section 14 asks for starting
positions, an optional gate, a defined output socket and a deterministic
release, and nothing else - no visual polish, no fanfare. What it does have to
get right is the *state* it hands the bowl, because a marble arriving skidding,
or arriving at a speed nobody chose, makes every measurement downstream a
measurement of the chute.

## The chute is a vertical curve, and that is the socket contract at work

The exit socket is level in the direction of travel and the chute rises behind
it on a parabolic transition into a constant incline - the same shape a road
uses to join a grade to a flat, for the same reason. `h(u) = tan(theta) u^2 /
2T` up to the transition length T, then straight at `tan(theta)`.

Authoring it that way is not a style choice, it is forced by how modules
connect. `Machine` places this module by making its exit socket *coincide* with
the bowl's entry socket, so the world pitch of the chute's mouth is whatever
the bowl asks to be fed at and cannot be anything else. A chute authored as a
straight 30-degree ramp would come out as a straight 15-degree ramp, tilted to
match, with its release end 15 degrees shallower than intended. A chute
authored level at the mouth comes out with its mouth at the bowl's angle and
its release end at the bowl's angle *plus* its own incline, which is what was
wanted. The module states the shape and the machine states where it points.

## Release

Marbles are placed at rest, spaced along the chute, resting against a gate that
is a mass-zero box moved by a `LinearGate` actuator. The gate retracts
downwards over `gate_duration` on a smoothstep, so it does not hand the first
marble an impulse on the tick it starts moving, and its pose is a pure function
of the tick index - see `marble3d.modules.base`, where the argument for that is
made in full.

That the queue is single file is a decision and not a limitation. A marble
machine is fed single file, and the interesting spread does not come from the
grid anyway: it comes from each marble entering the bowl at a different speed,
because each one starts at a different height on the same chute. The lab found
the same thing - varying entry energy is most of what makes a field interleave,
far more than varying entry angle - and here it is free.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from marble3d.geometry import GUIDED, Socket, Transform, basis_from_forward_up
from marble3d.mesh import Aabb, TriMesh, sweep
from marble3d.modules.base import Actuator, LinearGate, MarbleModule, Probe, channel_section
from marble3d.units import MARBLE_DIAMETER, MARBLE_RADIUS

__all__ = ["StartSpec", "StartModule"]


@dataclass(frozen=True)
class StartSpec:
    """Every number the start is made of, in world units.

    The channel dimensions have to match the bowl's spout, because the two are
    joined by a guided socket and `Machine` refuses a join whose two sides do
    not admit the same marble. They are stated against the marble here for the
    same reason they are there.
    """

    width: float = 2.4 * MARBLE_RADIUS
    wall: float = 1.6 * MARBLE_RADIUS
    floor_radius: float = 1.6 * MARBLE_RADIUS
    length: float = 21.0
    transition: float = 4.0
    # The incline of the running section, as a tangent. Everything below the
    # gate is at this angle and it sets how fast a marble arrives at the bowl.
    incline: float = 0.30
    # The staging shelf, behind the gate, where the marbles wait. Shallow, and
    # the reason is measured rather than aesthetic. The marble at the back of a
    # queue starts a queue-length further up the slope than the one at the
    # front, so the shelf's slope *is* the spread of entry speeds: on the
    # running incline an eight-marble queue would spread them over 2.5 wu of
    # height, enough that the back of the field arrives above the bowl's
    # circular-orbit speed and climbs out over the dish edge. On the shelf the
    # spread is 0.8 wu and the whole field enters at 0.84 to 0.92 of orbit
    # speed - below it, so every marble spirals in, and spread enough that they
    # take different paths. `tools/marble3d_validate.py --entry` measures it.
    shelf_slope: float = 0.10
    shelf_blend: float = 2.0           # over which the two slopes are joined
    marble_count: int = 8
    marble_spacing: float = 1.2 * MARBLE_DIAMETER
    gate_offset: float = 10.0          # how far back from the exit the gate sits
    gate_thickness: float = 0.3
    gate_release: float = 0.15
    gate_duration: float = 0.12
    frames_per_unit: float = 1.2

    def slope(self, distance: float) -> float:
        """Floor gradient `distance` back from the exit. C1 everywhere.

        Four pieces: a parabolic transition that brings the floor to level at
        the exit socket, the running incline, a linear blend, and the shelf.
        The blend is not decoration - a marble rolling over a slope
        discontinuity leaves the surface, and the release is the one moment in
        the run when eight of them do it at once.
        """
        blend_start = self.gate_offset - self.shelf_blend
        if distance <= self.transition:
            return self.incline * distance / self.transition
        if distance <= blend_start:
            return self.incline
        if distance <= self.gate_offset:
            fraction = (distance - blend_start) / self.shelf_blend
            return self.incline + (self.shelf_slope - self.incline) * fraction
        return self.shelf_slope

    def height(self, distance: float) -> float:
        """Chute floor height at `distance` back from the exit, the integral."""
        blend_start = self.gate_offset - self.shelf_blend
        if distance <= self.transition:
            return self.incline * distance * distance / (2.0 * self.transition)
        base = self.incline * self.transition / 2.0
        if distance <= blend_start:
            return base + self.incline * (distance - self.transition)
        base += self.incline * (blend_start - self.transition)
        if distance <= self.gate_offset:
            travelled = distance - blend_start
            fraction = travelled / self.shelf_blend
            return base + travelled * (self.incline + 0.5 * (self.shelf_slope - self.incline) * fraction)
        base += 0.5 * (self.incline + self.shelf_slope) * self.shelf_blend
        return base + self.shelf_slope * (distance - self.gate_offset)

    def to_json(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "wall": self.wall,
            "length": self.length,
            "transition": self.transition,
            "incline": self.incline,
            "incline_deg": math.degrees(math.atan(self.incline)),
            "shelf_slope": self.shelf_slope,
            "gate_offset": self.gate_offset,
            "marble_count": self.marble_count,
            "marble_spacing": self.marble_spacing,
            "gate_release": self.gate_release,
            "gate_duration": self.gate_duration,
            "drop": self.height(self.length),
        }


class StartModule(MarbleModule):
    """An inclined chute holding a queue of marbles behind a gate.

    Local frame: the origin is the exit, +X the direction of travel, +Y up.
    The chute runs back along -X and rises.
    """

    def __init__(self, module_id: str = "start", spec: StartSpec | None = None) -> None:
        super().__init__(module_id)
        self.spec = spec or StartSpec()
        self._validate()
        self._meshes: list[TriMesh] | None = None

    def _validate(self) -> None:
        spec = self.spec
        if spec.width <= MARBLE_DIAMETER:
            raise ValueError(
                f"a channel {spec.width} wide does not pass a {MARBLE_DIAMETER} marble"
            )
        needed = spec.gate_offset + spec.marble_count * spec.marble_spacing
        if needed > spec.length:
            raise ValueError(
                f"{spec.marble_count} marbles at {spec.marble_spacing} spacing need "
                f"{needed:.1f} of chute behind the exit and there is {spec.length:.1f}"
            )
        if spec.marble_spacing <= MARBLE_DIAMETER:
            raise ValueError("marbles spaced a diameter apart or less start overlapping")
        if not spec.transition < spec.gate_offset - spec.shelf_blend:
            raise ValueError(
                "the shelf blend has to finish after the exit transition; move the "
                "gate further back or shorten the blend"
            )

    # --- the path --------------------------------------------------------

    def _frames(self) -> list[Transform]:
        """Frames from the top of the chute down to the exit, in flow order."""
        spec = self.spec
        count = max(8, int(math.ceil(spec.length * spec.frames_per_unit)))
        frames: list[Transform] = []
        for index in range(count + 1):
            distance = spec.length * (1.0 - index / count)
            slope = spec.slope(distance)
            frames.append(
                Transform(
                    (-distance, spec.height(distance), 0.0),
                    # Travelling in +X and descending, so the forward vector
                    # falls by the local slope.
                    basis_from_forward_up((1.0, -slope, 0.0), (0.0, 1.0, 0.0)),
                )
            )
        return frames

    def frame_at(self, distance: float) -> Transform:
        """The chute frame `distance` back from the exit, analytically."""
        spec = self.spec
        return Transform(
            (-distance, spec.height(distance), 0.0),
            basis_from_forward_up((1.0, -spec.slope(distance), 0.0), (0.0, 1.0, 0.0)),
        )

    def local_colliders(self) -> list[TriMesh]:
        if self._meshes is None:
            section = channel_section(self.spec.width, self.spec.wall, self.spec.floor_radius)
            self._meshes = [sweep(section, self._frames(), name=f"{self.id}_chute")]
        return self._meshes

    def local_bounds(self) -> Aabb:
        spec = self.spec
        top = spec.height(spec.length)
        reach = 0.5 * spec.width + spec.wall
        return Aabb(
            (-spec.length - MARBLE_DIAMETER, -2.0 * MARBLE_DIAMETER, -reach - MARBLE_DIAMETER),
            (MARBLE_DIAMETER, top + 4.0 * MARBLE_DIAMETER, reach + MARBLE_DIAMETER),
        )

    # --- sockets, marbles and the gate -----------------------------------

    def local_sockets(self) -> dict[str, Socket]:
        return {
            "exit": Socket(
                name="exit",
                frame=self.frame_at(0.0),
                kind=GUIDED,
                width=self.spec.width,
                height=self.spec.wall,
            )
        }

    def local_actuators(self) -> list[Actuator]:
        spec = self.spec
        frame = self.frame_at(spec.gate_offset)
        # The gate stands in the channel with its foot on the floor. Half a
        # marble of overlap below the floor line so there is no gap under it
        # for a marble to squeeze through when it is nearly closed.
        height = spec.wall + MARBLE_DIAMETER
        rest = frame.compose(Transform((0.0, 0.5 * height - 0.25 * MARBLE_DIAMETER, 0.0)))
        return [
            LinearGate(
                name="gate",
                half_extents=(
                    0.5 * spec.gate_thickness,
                    0.5 * height,
                    0.5 * spec.width + spec.wall,
                ),
                rest=rest,
                # Straight down and well clear, in the module's own frame. The
                # chute is shallow enough here that local down and world down
                # differ by the incline angle, which does not matter for a part
                # whose only job is to stop being in the way.
                travel=(0.0, -(height + MARBLE_DIAMETER), 0.0),
                release_time=spec.gate_release,
                duration=spec.gate_duration,
            )
        ]

    def marble_starts(self) -> list[Transform]:
        """Where each marble sits at rest, in world coordinates, in queue order.

        Index 0 is the marble against the gate. Each rests on the floor of the
        gutter, which is the frame origin, so its centre is one radius up the
        frame's own +Y - on a banked or inclined chute that is the surface
        normal and not world up, which is the whole reason the frames exist.
        """
        spec = self.spec
        starts: list[Transform] = []
        for index in range(spec.marble_count):
            distance = (
                spec.gate_offset
                + 0.5 * spec.gate_thickness
                + (index + 0.5) * spec.marble_spacing
            )
            frame = self.transform.compose(self.frame_at(distance))
            starts.append(frame.compose(Transform((0.0, MARBLE_RADIUS, 0.0))))
        return starts

    def release_drop(self, index: int) -> float:
        """How far marble `index` falls between rest and the exit socket.

        Used by the entry-speed check: a marble that rolls without slipping
        from rest through a drop h leaves at sqrt(10 g h / 7), and the spread
        of those numbers across the queue is what the bowl sees.
        """
        spec = self.spec
        distance = (
            spec.gate_offset + 0.5 * spec.gate_thickness + (index + 0.5) * spec.marble_spacing
        )
        return spec.height(distance)

    # --- probes ----------------------------------------------------------

    def local_probes(self) -> list[Probe]:
        spec = self.spec
        probes: list[Probe] = []
        samples = 40
        for index in range(samples):
            distance = spec.length * (index + 0.5) / samples
            frame = self.frame_at(distance)
            floor = frame.apply((0.0, 0.0, 0.0))
            above = frame.apply((0.0, 3.0 * MARBLE_DIAMETER, 0.0))
            probes.append(
                Probe(
                    start=above,
                    end=frame.apply((0.0, -2.0 * MARBLE_DIAMETER, 0.0)),
                    expect_hit=True,
                    expected_point=floor,
                    tolerance=0.05,
                    label=f"{self.id}.floor {distance:.1f} back",
                )
            )
            # Both walls, across the channel, at marble height.
            for side in (-1.0, 1.0):
                inside = frame.apply((0.0, MARBLE_RADIUS, 0.0))
                outside = frame.apply(
                    (0.0, MARBLE_RADIUS, side * (0.5 * spec.width + spec.wall + MARBLE_DIAMETER))
                )
                probes.append(
                    Probe(
                        start=inside,
                        end=outside,
                        expect_hit=True,
                        tolerance=spec.width,
                        label=f"{self.id}.wall {distance:.1f} back",
                    )
                )
        return probes

    def describe(self) -> dict[str, Any]:
        return {
            "spec": self.spec.to_json(),
            "marble_drops": [self.release_drop(index) for index in range(self.spec.marble_count)],
        }

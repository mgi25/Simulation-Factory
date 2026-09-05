"""The module contract: what every piece of a marble machine has to provide.

A module is authored entirely in its **own local coordinates**, with its origin
somewhere convenient to the shape - the centre of a bowl, the head of a curve -
and is placed in the world by `marble3d.machine.Machine` composing socket
frames. No module knows where it is, and no module in this package contains a
world coordinate. That is the property that makes a generator possible later:
composing a machine is composing transforms, not typing numbers.

Six things make up the contract, and each one exists because something
downstream needs it:

* **sockets** - the boundary frames, so modules can be connected geometrically
  rather than by coincidence. See `marble3d.geometry.Socket`.
* **colliders** - triangle meshes in local coordinates. The world chunks them,
  writes them and places them; a module never touches Bullet.
* **actuators** - moving parts, as pure functions of the tick index.
* **bounds** - a local AABB, which is what tells the simulation which module a
  marble is in and therefore what an entry and exit event mean.
* **probes** - rays the module asserts must hit its own surface, generated from
  the analytic shape it was built from. This is the module's own answer to "is
  the collider Bullet actually holds the collider I described", and it is the
  production replacement for looking at a picture and deciding it seems fine.
* **metadata** - whatever a replay needs to describe the module to a renderer
  that will never re-simulate it.

## Actuation, and why a pose is a function of a tick

Section 18 of the brief asks how deterministic actuation will work before any
mechanism is built, and the answer is the whole of `Actuator`: an actuator's
pose is `pose_at(tick)`, a pure function of an integer. Not of elapsed
wall-clock, not of an accumulated phase, not of the previous pose. Three things
follow, and they are the reasons for the restriction rather than consequences
of it.

A run resumed, replayed or re-simulated from tick N puts every mechanism in
exactly the position it had, with no warm-up. Floating-point phase drift cannot
accumulate, because nothing is accumulated - a rotating gate at tick 100000 is
`angle = rate * 100000 * dt` and not a hundred thousand additions. And an
actuator can be evaluated *without a physics world*, so a test can assert that a
paddle sweeps the arc it claims, and a renderer can draw a machine's moving
parts straight from the replay's module configuration without a physics engine
present at all.

The cost is that an actuator cannot react - it cannot stop when a marble is
under it, and it cannot be driven by a motor with a force limit. Both are real
mechanisms and both will eventually be wanted. When they are, they should
arrive as a *second* kind, explicitly non-reactive-free, with its state written
into the replay per frame rather than derived from the tick; they must not
arrive as an exception to this one, because the moment one mechanism's pose
depends on run history, resuming from a replay stops being exact for the whole
machine.

Bodies driven this way are mass zero: infinitely heavy to a marble, unmovable
by contact, and moved by rewriting their transform between steps. A marble
resting on one is pushed out of the way rather than lifted with momentum, which
is right for a gate and wrong for a lift - a lift needs the transform *and* a
matching velocity so the solver has something to transfer, and that is a
straightforward extension of `Actuator` when the first one is built.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

from marble3d.geometry import DROP, GUIDED, IDENTITY, Socket, Transform, Vec3
from marble3d.mesh import Aabb, TriMesh

__all__ = ["Actuator", "LinearGate", "Probe", "MarbleModule", "BuiltModule"]


# --- actuation -----------------------------------------------------------


class Actuator:
    """A moving collider whose pose is a pure function of the tick index."""

    def __init__(self, name: str, half_extents: Sequence[float]) -> None:
        self.name = name
        self.half_extents = tuple(float(value) for value in half_extents)

    def pose_at(self, tick: int, dt: float) -> Transform:
        """Where this part is at `tick`, in the owning module's local frame."""
        raise NotImplementedError

    def to_json(self) -> dict[str, Any]:
        return {"name": self.name, "kind": type(self).__name__, "half_extents": list(self.half_extents)}


class LinearGate(Actuator):
    """A block that slides along one axis, once, at a stated time.

    The whole of the start module's release mechanism. `travel` is applied over
    `duration` with a smoothstep so the gate does not hand a marble an impulse
    on the first tick of its motion, and the pose is clamped at both ends, so
    `pose_at` is defined and constant for every tick before the release and
    every tick after it finishes.
    """

    def __init__(
        self,
        name: str,
        half_extents: Sequence[float],
        rest: Transform,
        travel: Sequence[float],
        release_time: float,
        duration: float,
    ) -> None:
        super().__init__(name, half_extents)
        self.rest = rest
        self.travel = tuple(float(value) for value in travel)
        self.release_time = float(release_time)
        self.duration = float(duration)
        if self.duration <= 0.0:
            raise ValueError(f"gate {name!r}: a release takes a positive amount of time")

    def pose_at(self, tick: int, dt: float) -> Transform:
        elapsed = tick * dt - self.release_time
        if elapsed <= 0.0:
            fraction = 0.0
        elif elapsed >= self.duration:
            fraction = 1.0
        else:
            u = elapsed / self.duration
            fraction = u * u * (3.0 - 2.0 * u)
        return Transform(
            position=tuple(
                base + fraction * offset for base, offset in zip(self.rest.position, self.travel)
            ),
            rotation=self.rest.rotation,
        )

    def to_json(self) -> dict[str, Any]:
        data = super().to_json()
        data.update(
            {
                "rest": list(self.rest.position),
                "travel": list(self.travel),
                "release_time": self.release_time,
                "duration": self.duration,
            }
        )
        return data


# --- collider probes -----------------------------------------------------


@dataclass(frozen=True)
class Probe:
    """A ray a module asserts must hit its own collider, and where.

    Generated by the module from the analytic surface its mesh was built from,
    so the probe and the mesh come from the same description but by different
    routes - the mesh through tessellation and an OBJ file and Bullet's loader,
    the probe straight from the formula. A truncated mesh, a hole, a module
    placed at a wrong transform and a phantom surface in mid-air all break that
    agreement, and none of them breaks a simulation loudly enough to notice.

    `expect_hit=False` probes are as important as the others: they are how a
    phantom cone gets caught, by asserting that the space a marble has to orbit
    through is empty.
    """

    start: Vec3
    end: Vec3
    expect_hit: bool = True
    expected_point: Vec3 | None = None
    tolerance: float = 0.02
    label: str = ""


# --- the module ----------------------------------------------------------


class MarbleModule:
    """One piece of a marble machine.

    Subclasses override the `local_*` methods and nothing else. The resolved
    accessors below apply `self.transform`, which `Machine` sets when the
    module is connected and which is the identity until it is.
    """

    def __init__(self, module_id: str) -> None:
        self.id = str(module_id)
        self.transform: Transform = IDENTITY

    # --- authored in local coordinates ---------------------------------

    def local_sockets(self) -> dict[str, Socket]:
        raise NotImplementedError

    def local_colliders(self) -> list[TriMesh]:
        raise NotImplementedError

    def local_actuators(self) -> list[Actuator]:
        return []

    def local_bounds(self) -> Aabb:
        """The module's own extent, used to decide which module a marble is in.

        Defaults to the union of its colliders' bounds, grown by a marble
        diameter so a marble rolling on the inside surface counts as inside.
        A module whose region of interest is not its geometry - a drop tube, a
        catch zone - overrides this.
        """
        from marble3d.units import MARBLE_DIAMETER

        meshes = self.local_colliders()
        if not meshes:
            raise ValueError(f"module {self.id!r} has neither colliders nor bounds")
        bounds = meshes[0].aabb()
        for mesh in meshes[1:]:
            bounds = bounds.merged(mesh.aabb())
        return Aabb(
            tuple(value - MARBLE_DIAMETER for value in bounds.lower),
            tuple(value + MARBLE_DIAMETER for value in bounds.upper),
        )

    def local_probes(self) -> list[Probe]:
        return []

    def describe(self) -> dict[str, Any]:
        """Module metadata for the replay, beyond what the base class writes."""
        return {}

    # --- resolved to world ---------------------------------------------

    def socket(self, name: str) -> Socket:
        try:
            local = self.local_sockets()[name]
        except KeyError:
            available = sorted(self.local_sockets())
            raise KeyError(f"module {self.id!r} has no socket {name!r}; it has {available}") from None
        return Socket(
            name=local.name,
            frame=self.transform.compose(local.frame),
            kind=local.kind,
            width=local.width,
            height=local.height,
        )

    def socket_names(self) -> list[str]:
        return sorted(self.local_sockets())

    def bounds(self) -> Aabb:
        """World-space bounds. Exact for an axis-aligned placement.

        Computed from the eight corners of the local box under the placement,
        so a rotated module reports a box that contains it rather than one that
        clips its own corners off - which would make a marble in the corner
        belong to no module at all.
        """
        local = self.local_bounds()
        corners = [
            (x, y, z)
            for x in (local.lower[0], local.upper[0])
            for y in (local.lower[1], local.upper[1])
            for z in (local.lower[2], local.upper[2])
        ]
        moved = [self.transform.apply(corner) for corner in corners]
        lower = tuple(min(point[axis] for point in moved) for axis in range(3))
        upper = tuple(max(point[axis] for point in moved) for axis in range(3))
        return Aabb(lower, upper)

    def contains(self, point: Sequence[float], slack: float = 0.0) -> bool:
        return self.bounds().contains(point, slack)

    def probes(self) -> list[Probe]:
        placed: list[Probe] = []
        for probe in self.local_probes():
            placed.append(
                Probe(
                    start=self.transform.apply(probe.start),
                    end=self.transform.apply(probe.end),
                    expect_hit=probe.expect_hit,
                    expected_point=(
                        self.transform.apply(probe.expected_point)
                        if probe.expected_point is not None
                        else None
                    ),
                    tolerance=probe.tolerance,
                    label=probe.label or f"{self.id}",
                )
            )
        return placed

    def to_json(self) -> dict[str, Any]:
        local = self.local_bounds()
        return {
            "id": self.id,
            "type": type(self).__name__,
            "transform": {
                "position": list(self.transform.position),
                "rotation": list(self.transform.rotation),
            },
            "bounds": [list(local.lower), list(local.upper)],
            "sockets": {
                name: {
                    "kind": socket.kind,
                    "position": list(socket.frame.position),
                    "rotation": list(socket.frame.rotation),
                    "width": socket.width,
                    "height": socket.height,
                }
                for name, socket in self.local_sockets().items()
            },
            "actuators": [actuator.to_json() for actuator in self.local_actuators()],
            **self.describe(),
        }


@dataclass
class BuiltModule:
    """What a module became once it was put into a world."""

    module: MarbleModule
    collider_bodies: list[int] = field(default_factory=list)
    actuator_bodies: dict[str, int] = field(default_factory=dict)

    def apply_actuators(self, world: Any, tick: int, dt: float) -> None:
        placement = self.module.transform
        for actuator in self.module.local_actuators():
            body = self.actuator_bodies.get(actuator.name)
            if body is None:
                continue
            world.move_kinematic(body, placement.compose(actuator.pose_at(tick, dt)))


def channel_section(
    width: float,
    wall_height: float,
    floor_radius: float,
    points_in_floor: int = 9,
    points_in_wall: int = 3,
) -> list[tuple[float, float]]:
    """A gutter cross-section, as (across, up) pairs in a socket frame.

    Shared by the chute and the curve so that "the channel" is one shape with
    one set of numbers. A circular floor arc of radius `floor_radius` spanning
    `width`, then a wall up each side. The floor is an arc rather than a flat
    strip because a marble in a flat channel wanders between the two walls and
    ticks off each one, and a marble in a gutter is centred by its own weight -
    which is what a real marble run is shaped like, and it is also what keeps a
    banked curve from needing the bank to do all the work.

    The floor arc is only ever a shallow one: `floor_radius` must exceed half
    the width, or the section closes over the marble.
    """
    if floor_radius <= 0.5 * width:
        raise ValueError(
            f"a floor radius of {floor_radius} cannot span a channel {width} wide"
        )
    half = 0.5 * width
    span = math.asin(half / floor_radius)
    # The arc's centre sits directly above the channel's lowest point, which is
    # the local origin, so the floor passes through (0, 0) whatever the radius.
    section: list[tuple[float, float]] = []
    for index in range(points_in_floor):
        angle = -span + 2.0 * span * index / (points_in_floor - 1)
        across = floor_radius * math.sin(angle)
        up = floor_radius * (1.0 - math.cos(angle))
        section.append((across, up))

    floor_top = section[-1][1]
    walls: list[tuple[float, float]] = []
    for index in range(1, points_in_wall + 1):
        rise = wall_height * index / points_in_wall
        walls.append((half, floor_top + rise))
    left = [(-across, up) for across, up in reversed(walls)]
    return left + section + walls


def rolling_entry_velocity(speed: float, socket: Socket) -> tuple[Vec3, Vec3]:
    """A velocity and a matching spin for a marble entering through a socket.

    The spin is the one that puts the contact point at rest, so a marble handed
    to a module through its socket arrives already rolling rather than skidding
    for the first tenth of a second.
    """
    from marble3d.units import MARBLE_RADIUS

    flow = socket.flow()
    up = socket.up()
    velocity = tuple(speed * component for component in flow)
    spin = (
        (up[1] * velocity[2] - up[2] * velocity[1]) / MARBLE_RADIUS,
        (up[2] * velocity[0] - up[0] * velocity[2]) / MARBLE_RADIUS,
        (up[0] * velocity[1] - up[1] * velocity[0]) / MARBLE_RADIUS,
    )
    return velocity, spin


# Re-exported so a module file imports its socket kinds from the contract it is
# implementing rather than from the geometry package.
__all__ += ["GUIDED", "DROP", "channel_section", "rolling_entry_velocity"]

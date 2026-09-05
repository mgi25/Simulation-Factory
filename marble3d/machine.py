"""Composing modules into a machine by joining their sockets.

The rule this file exists to enforce is that a module's place in the world is
*derived*, never typed. `Machine.connect` takes an exit socket and an entry
socket and solves for the transform that brings them together; the only
coordinate anyone writes down is the placement of the single anchor module, and
even that is normally the identity. Adding a piece in the middle of a machine
moves everything downstream of it automatically, which is the property a
procedural generator needs and the one a file full of hand-entered world
coordinates cannot have.

## The two joins

**Guided.** The surface is continuous across the boundary, so the two socket
frames must coincide exactly - position and orientation both. Solving
`T . entry_local = exit_world` gives `T = exit_world . entry_local^-1`, and
there is nothing left over. Anything the upstream module decides about pitch,
bank or height propagates into the downstream module's whole placement, which
is why the chute in `marble3d.modules.start` is authored level at its mouth:
the bowl decides the feed angle and the chute adopts it.

**Drop.** The marble is in free flight across the boundary, so the join
constrains less and has to say exactly how much less. The downstream entry is
placed `fall` directly below the upstream exit, and the downstream module is
yawed about the world vertical until its entry heading matches the exit's. Its
pitch and roll are its own - a catch basin under a drain is not obliged to be
vertical because the drain is. That is one rotational degree of freedom fixed
by the sockets and two kept by the module, and it is still entirely derived.

A drop join is also where the machine stops being a height field. The bowl's
drain feeds a curve that runs *underneath* the bowl, so the same `(x, z)` has
dish above and channel below, and nothing about that is a special case here.

## What a connection checks

Both joins check that the two sides admit the same marble, because the failure
they prevent is not a crash. A 2 wu chute feeding a 1.2 wu channel produces a
machine that works for most seeds and jams on the one where two marbles arrive
together, which is a bug that costs a batch run to find and five minutes of
arithmetic to prevent.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from marble3d.geometry import DROP, GUIDED, Socket, Transform, yaw_quaternion
from marble3d.mesh import Aabb
from marble3d.modules.base import BuiltModule, MarbleModule
from marble3d.units import MARBLE_DIAMETER

__all__ = ["Connection", "Machine"]

# How closely two guided socket frames have to agree. A tenth of a millimetre
# at toy scale. They are computed to coincide exactly; this is a guard against
# a future join solved a different way, not a tolerance anything relies on.
GUIDED_TOLERANCE = 1e-6


@dataclass(frozen=True)
class Connection:
    upstream: str
    upstream_socket: str
    downstream: str
    downstream_socket: str
    kind: str
    fall: float = 0.0

    def to_json(self) -> dict[str, Any]:
        return {
            "from": f"{self.upstream}.{self.upstream_socket}",
            "to": f"{self.downstream}.{self.downstream_socket}",
            "kind": self.kind,
            "fall": self.fall,
        }


class Machine:
    """An ordered set of placed modules and the joins between them."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.modules: dict[str, MarbleModule] = {}
        self.order: list[str] = []
        self.connections: list[Connection] = []
        self._placed: set[str] = set()

    # --- assembly --------------------------------------------------------

    def add(self, module: MarbleModule, transform: Transform | None = None) -> MarbleModule:
        """Register a module, optionally anchoring it.

        Exactly one module in a machine is anchored; every other one is placed
        by a connection. Anchoring more than one is how a machine ends up with
        two joins that each think they own a transform, so it is refused.
        """
        if module.id in self.modules:
            raise ValueError(f"machine {self.name!r} already has a module called {module.id!r}")
        self.modules[module.id] = module
        self.order.append(module.id)
        if transform is not None:
            module.transform = transform
            self._placed.add(module.id)
        return module

    def anchor(self, module: MarbleModule) -> MarbleModule:
        return self.add(module, Transform())

    def connect(
        self,
        upstream: MarbleModule | str,
        upstream_socket: str,
        downstream: MarbleModule | str,
        downstream_socket: str,
        fall: float = 0.0,
    ) -> Connection:
        """Join two sockets, placing whichever module is not placed yet.

        Either direction works: connecting a placed bowl to an unplaced chute
        places the chute, and connecting a placed chute to an unplaced bowl
        places the bowl. That matters because the anchor should be whichever
        module has an orientation the machine cares about - the bowl has to be
        upright, and the chute does not have to be anything.
        """
        source = self._module(upstream)
        target = self._module(downstream)
        if source.id == target.id:
            raise ValueError(f"cannot connect module {source.id!r} to itself")

        placed_source = source.id in self._placed
        placed_target = target.id in self._placed
        if placed_source == placed_target:
            state = "both already placed" if placed_source else "neither placed"
            raise ValueError(
                f"connecting {source.id}.{upstream_socket} to "
                f"{target.id}.{downstream_socket}: {state}. Exactly one side of a "
                "join has to be free to move, and exactly one module in a machine "
                "is anchored."
            )

        exit_socket = source.local_sockets()[upstream_socket]
        entry_socket = target.local_sockets()[downstream_socket]
        kind = exit_socket.kind
        self._check_clearance(source.id, exit_socket, target.id, entry_socket, kind)

        if placed_source:
            self._place(target, downstream_socket, source.socket(upstream_socket), kind, fall)
        else:
            # Solving the same join backwards: the free module is upstream, so
            # its exit has to land on the already-placed entry. A drop cannot
            # be solved this way - it would need the fall to be applied upward
            # and the yaw to be inverted, and no machine has needed it - so it
            # is refused rather than silently solved wrongly.
            if kind != GUIDED:
                raise ValueError(
                    f"a {kind} join can only be solved downstream; anchor "
                    f"{source.id!r} or connect it to something first"
                )
            self._place_upstream(source, upstream_socket, target.socket(downstream_socket))

        connection = Connection(
            upstream=source.id,
            upstream_socket=upstream_socket,
            downstream=target.id,
            downstream_socket=downstream_socket,
            kind=kind,
            fall=fall,
        )
        self.connections.append(connection)
        self._verify(connection)
        return connection

    def _module(self, module: MarbleModule | str) -> MarbleModule:
        if isinstance(module, str):
            try:
                return self.modules[module]
            except KeyError:
                raise KeyError(f"machine {self.name!r} has no module {module!r}") from None
        if module.id not in self.modules:
            raise KeyError(f"module {module.id!r} has not been added to machine {self.name!r}")
        return module

    def _check_clearance(
        self, source_id: str, exit_socket: Socket, target_id: str, entry_socket: Socket, kind: str
    ) -> None:
        for label, socket in ((source_id, exit_socket), (target_id, entry_socket)):
            if socket.width and socket.width <= MARBLE_DIAMETER:
                raise ValueError(
                    f"{label}.{socket.name} is {socket.width} across and a marble is "
                    f"{MARBLE_DIAMETER}; nothing would get through"
                )
        if not (exit_socket.width and entry_socket.width):
            return
        if kind == GUIDED:
            if abs(exit_socket.width - entry_socket.width) > 1e-6:
                raise ValueError(
                    f"guided join {source_id}.{exit_socket.name} -> "
                    f"{target_id}.{entry_socket.name}: the channel steps from "
                    f"{exit_socket.width} to {entry_socket.width} across. A guided join "
                    "is a continuous surface, so the two sides have to be the same width."
                )
        elif entry_socket.width < exit_socket.width - 1e-9:
            raise ValueError(
                f"drop join {source_id}.{exit_socket.name} -> "
                f"{target_id}.{entry_socket.name}: a marble can leave a "
                f"{exit_socket.width}-wide opening anywhere across it and the catch "
                f"below is only {entry_socket.width} wide"
            )

    def _place(
        self,
        module: MarbleModule,
        socket_name: str,
        exit_world: Socket,
        kind: str,
        fall: float,
    ) -> None:
        local = module.local_sockets()[socket_name]
        if kind == GUIDED:
            module.transform = exit_world.frame.compose(local.frame.inverse())
        elif kind == DROP:
            if fall <= 0.0:
                raise ValueError(
                    f"a drop join into {module.id}.{socket_name} needs a positive fall; "
                    "the two sockets would otherwise be in the same place and the "
                    "marble would have nowhere to fall from"
                )
            target = (
                exit_world.frame.position[0],
                exit_world.frame.position[1] - fall,
                exit_world.frame.position[2],
            )
            rotation = yaw_quaternion(exit_world.heading() - local.heading())
            moved = Transform((0.0, 0.0, 0.0), rotation).apply(local.frame.position)
            module.transform = Transform(
                position=(target[0] - moved[0], target[1] - moved[1], target[2] - moved[2]),
                rotation=rotation,
            )
        else:
            raise ValueError(f"unknown socket kind {kind!r}")
        self._placed.add(module.id)

    def _place_upstream(self, module: MarbleModule, socket_name: str, entry_world: Socket) -> None:
        local = module.local_sockets()[socket_name]
        module.transform = entry_world.frame.compose(local.frame.inverse())
        self._placed.add(module.id)

    def _verify(self, connection: Connection) -> None:
        exit_world = self.modules[connection.upstream].socket(connection.upstream_socket)
        entry_world = self.modules[connection.downstream].socket(connection.downstream_socket)
        if connection.kind == GUIDED:
            offset = math.dist(exit_world.frame.position, entry_world.frame.position)
            flow = sum(a * b for a, b in zip(exit_world.flow(), entry_world.flow()))
            up = sum(a * b for a, b in zip(exit_world.up(), entry_world.up()))
            if offset > GUIDED_TOLERANCE or flow < 1.0 - 1e-9 or up < 1.0 - 1e-9:
                raise AssertionError(
                    f"guided join {connection.to_json()['from']} -> "
                    f"{connection.to_json()['to']} did not close: offset {offset:.3e}, "
                    f"flow alignment {flow:.9f}, up alignment {up:.9f}"
                )
        else:
            drop = exit_world.frame.position[1] - entry_world.frame.position[1]
            sideways = math.hypot(
                exit_world.frame.position[0] - entry_world.frame.position[0],
                exit_world.frame.position[2] - entry_world.frame.position[2],
            )
            heading = abs(
                math.remainder(exit_world.heading() - entry_world.heading(), 2.0 * math.pi)
            )
            if (
                abs(drop - connection.fall) > 1e-6
                or sideways > 1e-6
                or heading > 1e-6
            ):
                raise AssertionError(
                    f"drop join {connection.to_json()['from']} -> "
                    f"{connection.to_json()['to']} did not close: fall {drop:.6f} "
                    f"against {connection.fall}, sideways {sideways:.3e}, "
                    f"heading error {heading:.3e}"
                )

    # --- the assembled machine -------------------------------------------

    def require_placed(self) -> None:
        loose = [name for name in self.order if name not in self._placed]
        if loose:
            raise ValueError(
                f"machine {self.name!r} has unplaced modules {loose}; every module "
                "needs either an anchor or a connection"
            )

    def build(self, world: Any) -> list[BuiltModule]:
        """Put every module's geometry into a world, in declaration order.

        Order matters for reproducibility rather than for physics: Bullet
        numbers bodies as they arrive, and the broadphase pair ordering that
        `deterministicOverlappingPairs` makes stable is stable in those
        numbers. A machine assembled in a different order is a different run.
        """
        self.require_placed()
        built: list[BuiltModule] = []
        for name in self.order:
            module = self.modules[name]
            record = BuiltModule(module=module)
            for mesh in module.local_colliders():
                for collider in world.add_static_mesh(mesh, module.transform, owner=module.id):
                    record.collider_bodies.append(collider.body)
            for actuator in module.local_actuators():
                pose = module.transform.compose(actuator.pose_at(0, world.config.physics.dt))
                record.actuator_bodies[actuator.name] = world.add_kinematic_box(
                    actuator.half_extents, pose, owner=module.id
                )
            built.append(record)
        return built

    def bounds(self) -> Aabb:
        self.require_placed()
        bounds = self.modules[self.order[0]].bounds()
        for name in self.order[1:]:
            bounds = bounds.merged(self.modules[name].bounds())
        return bounds

    def module_at(self, point: Sequence[float], current: str = "") -> str | None:
        """Which module a point is in, or None if it is between them.

        Where module boxes overlap - and they do, because a drop join puts one
        module's catch under another module's drain - the smaller box wins.
        A marble in the curve's catch is in the curve, not in the bowl whose
        bounds happen to reach down past it.

        `current` gives the answer hysteresis: a marble already in a module
        stays in it while it is still inside that module's bounds. Without it a
        marble in the drain shaft sits in the overlap of two boxes and flickers
        between them, emitting a module_exit and a module_enter every couple of
        frames. The result still depends only on the trajectory, so it is
        deterministic; it just stops being noisy.
        """
        if current and current in self.modules and self.modules[current].bounds().contains(point):
            return current
        best: tuple[float, str] | None = None
        for name in self.order:
            module = self.modules[name]
            bounds = module.bounds()
            if not bounds.contains(point):
                continue
            volume = 1.0
            for extent in bounds.size():
                volume *= max(extent, 1e-9)
            if best is None or volume < best[0]:
                best = (volume, name)
        return None if best is None else best[1]

    def probes(self) -> list[Any]:
        probes: list[Any] = []
        for name in self.order:
            probes.extend(self.modules[name].probes())
        return probes

    def to_json(self) -> dict[str, Any]:
        bounds = self.bounds()
        return {
            "name": self.name,
            "bounds": [list(bounds.lower), list(bounds.upper)],
            "modules": [self.modules[name].to_json() for name in self.order],
            "connections": [connection.to_json() for connection in self.connections],
        }

    def __iter__(self) -> Iterable[MarbleModule]:
        return iter(self.modules[name] for name in self.order)

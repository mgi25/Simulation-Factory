"""An obstacle's live presence in the physics space.

`ObstacleSpec` says what an obstacle is and how it moves; this is the thing
that exists in Pymunk while a battle runs. It is deliberately not a
`DynamicEntity`: arena furniture is placed once and lives for the whole
battle, has no owner, no lifetime, no damage and never despawns, so sharing
that machinery would only mean explaining which half of it does not apply.

Motion is Python's alone. A rotor spins because its kinematic body has an
angular velocity; a gate moves because its velocity is aimed at wherever the
spec says it must be by the end of the next tick. Either way Pymunk
integrates the body and resolves the contacts, so nothing here reflects a
ball by hand, and the resulting transform - not the formula - is what the
replay carries.
"""

from __future__ import annotations

import math

import pymunk

from engine.arena_layout import (
    COLLISION_TYPE_OBSTACLE,
    OBSTACLE_ELASTICITY,
    OBSTACLE_FRICTION,
    ObstacleSpec,
)


class ObstacleRuntime:
    """One obstacle's body and shape, plus the tick hook a moving one needs."""

    def __init__(self, spec: ObstacleSpec, space: pymunk.Space) -> None:
        self.spec = spec
        self.body, self.shape = (
            _build_kinetic(spec) if spec.is_kinetic else _build_static(spec, space)
        )

        self.shape.elasticity = OBSTACLE_ELASTICITY
        self.shape.friction = OBSTACLE_FRICTION
        self.shape.collision_type = COLLISION_TYPE_OBSTACLE

        if spec.is_kinetic:
            space.add(self.body, self.shape)
        else:
            space.add(self.shape)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ObstacleRuntime {self.spec.motion} id={self.obstacle_id}>"

    @property
    def obstacle_id(self) -> int:
        return self.spec.obstacle_id

    @property
    def is_kinetic(self) -> bool:
        return self.spec.is_kinetic

    @property
    def position(self) -> tuple[float, float]:
        """Where the obstacle is right now, moving or not."""
        if self.spec.is_kinetic:
            return (self.body.position.x, self.body.position.y)
        return self.spec.center

    @property
    def rotation_degrees(self) -> float:
        """The obstacle's angle right now, moving or not."""
        if self.spec.is_kinetic:
            return math.degrees(self.body.angle)
        return self.spec.rotation_degrees

    def placed(self) -> ObstacleSpec:
        """The obstacle's current geometry as a plain static spec."""
        x, y = self.position
        return self.spec.at(x, y, self.rotation_degrees)

    def before_step(self, elapsed: float) -> None:
        """Aim a gate at where it has to be one tick from now.

        A rotor needs nothing here: a constant angular velocity set once at
        construction already integrates to exactly the angle the spec
        describes. A gate turns around, so its velocity is recomputed from
        the path every tick - which also keeps the body exactly on the
        analytic path instead of drifting along an integrated one.
        """
        if not self.spec.is_gate:
            return
        from engine.simulation import PHYSICS_DT  # local: avoids an import cycle

        target = self.spec.position_at(elapsed + PHYSICS_DT)
        current = self.body.position
        self.body.velocity = (
            (target[0] - current.x) / PHYSICS_DT,
            (target[1] - current.y) / PHYSICS_DT,
        )

    def is_finite(self) -> bool:
        x, y = self.position
        return all(math.isfinite(value) for value in (x, y, self.rotation_degrees))


def _build_static(
    spec: ObstacleSpec, space: pymunk.Space
) -> tuple[pymunk.Body, pymunk.Shape]:
    """A shape hung directly on the space's static body, as in phase 5A1.

    A bar's polygon is built from the same `corners()` the layout measures
    every clearance with, so a rotated obstacle is physically exactly where
    the replay says it is.
    """
    body = space.static_body
    if spec.is_circle:
        return body, pymunk.Circle(body, spec.radius, offset=spec.center)
    return body, pymunk.Poly(body, spec.corners())


def _build_kinetic(spec: ObstacleSpec) -> tuple[pymunk.Body, pymunk.Shape]:
    """A kinematic body carrying a box centred on its own origin.

    Kinematic rather than static because Chipmunk reads a body's velocity
    when it resolves a contact: that is what lets a turning bar actually
    shove a fighter instead of behaving like a wall that happens to move.
    Infinite mass means nothing the fighters do can push back on it.
    """
    body = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
    x, y = spec.position_at(0.0)
    body.position = (x, y)
    body.angle = math.radians(spec.rotation_degrees)
    if spec.is_rotor:
        body.angular_velocity = math.radians(spec.angular_speed)
    return body, pymunk.Poly.create_box(body, (spec.width, spec.height))

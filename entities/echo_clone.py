"""A bouncing temporary copy of a fighter: the second dynamic entity.

An EchoClone deliberately does not inherit from `Ball`. It has no health, no
power, no place in the winner decision and cannot spawn anything of its own.
It is a temporary object with a radius, a velocity and a lifetime.
"""

from __future__ import annotations

import pymunk

from entities.ball import shape_group
from entities.dynamic_entity import COLLISION_TYPE_DYNAMIC_ENTITY, DynamicEntity

# Bouncy and frictionless like the fighters, so a clone keeps its energy for
# its whole lifetime instead of dribbling to a halt in a corner.
CLONE_ELASTICITY = 1.0
CLONE_FRICTION = 0.0


class EchoClone(DynamicEntity):
    """A real physical body that rebounds off walls until it hits or expires."""

    kind = "echo"
    # Spent by the opposing fighter, but walls only turn it around.
    despawn_on_ball_contact = True
    despawn_on_wall_contact = False

    def __init__(
        self,
        entity_id: int,
        owner_id: int,
        position: tuple[float, float],
        velocity: tuple[float, float],
        radius: float,
        color: tuple[int, int, int],
        damage: float,
        lifetime_ticks: int,
        mass: float,
    ) -> None:
        super().__init__(
            entity_id=entity_id,
            owner_id=owner_id,
            position=position,
            radius=radius,
            color=color,
            lifetime_ticks=lifetime_ticks,
        )
        self.contact_damage = float(damage)

        moment = pymunk.moment_for_circle(mass, 0.0, radius)
        self.body = pymunk.Body(mass, moment)
        self.body.position = position
        self.body.velocity = velocity

        self.shape = pymunk.Circle(self.body, radius)
        self.shape.collision_type = COLLISION_TYPE_DYNAMIC_ENTITY
        # Not a sensor: Pymunk does the wall bounces, so there is no
        # hand-written reflection maths anywhere.
        self.shape.elasticity = CLONE_ELASTICITY
        self.shape.friction = CLONE_FRICTION
        # Sharing the owner's filter group keeps a clone from touching the
        # fighter that made it - and, incidentally, from jostling its twin.
        self.shape.filter = pymunk.ShapeFilter(group=shape_group(owner_id))

    @property
    def position(self) -> pymunk.Vec2d:
        return self.body.position

    @property
    def velocity(self) -> pymunk.Vec2d:
        return self.body.velocity

    @property
    def shapes(self) -> tuple[pymunk.Shape, ...]:
        return (self.shape,)

    def add_to_space(self, space: pymunk.Space) -> None:
        space.add(self.body, self.shape)

    def remove_from_space(self, space: pymunk.Space) -> None:
        space.remove(self.body, self.shape)

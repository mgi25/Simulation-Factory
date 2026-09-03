"""A straight-flying projectile: the first dynamic entity."""

from __future__ import annotations

import pymunk

from entities.ball import shape_group
from entities.dynamic_entity import DynamicEntity

# Third collision type, alongside the fighter and wall types in `ball`.
COLLISION_TYPE_PROJECTILE = 3

# Never used to resolve an impulse - the shape is a sensor - but a Pymunk
# dynamic body still needs a positive mass.
PROJECTILE_MASS = 0.01


class Projectile(DynamicEntity):
    """Travels in a straight line, hits once, never bounces."""

    kind = "projectile"
    despawn_on_contact = True

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

        moment = pymunk.moment_for_circle(PROJECTILE_MASS, 0.0, radius)
        self.body = pymunk.Body(PROJECTILE_MASS, moment)
        self.body.position = position
        self.body.velocity = velocity

        self.shape = pymunk.Circle(self.body, radius)
        self.shape.collision_type = COLLISION_TYPE_PROJECTILE
        # A sensor reports contacts but never generates a real collision, so
        # the projectile neither bounces off a wall nor shoves the fighter it
        # hits. With zero gravity and no impulses, its velocity is constant.
        self.shape.sensor = True
        # Sharing the owner's filter group makes Chipmunk skip that pair
        # outright: a projectile physically cannot touch the fighter that
        # fired it, so self-damage is impossible rather than merely unlikely.
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

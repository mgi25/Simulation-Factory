"""An energy sphere that revolves around its owner: the third dynamic entity.

Its position is not produced by physics at all. Every tick it advances its own
angle and places itself relative to wherever its owner now is, which is why it
follows a moving fighter instead of circling the spot where it was created.
The body exists only so Pymunk can report it touching someone.
"""

from __future__ import annotations

import math

import pymunk

from entities.ball import shape_group
from entities.dynamic_entity import COLLISION_TYPE_DYNAMIC_ENTITY, DynamicEntity


class OrbitOrb(DynamicEntity):
    """A satellite: manually positioned, reports contact, pushes nothing."""

    kind = "orbit"
    # Spent by the opposing fighter; a wall means nothing to it, since the
    # arena clamp already keeps it in bounds.
    despawn_on_ball_contact = True
    despawn_on_wall_contact = False

    def __init__(
        self,
        entity_id: int,
        owner_id: int,
        position: tuple[float, float],
        radius: float,
        color: tuple[int, int, int],
        damage: float,
        orbit_radius: float,
        angle: float,
        angular_step: float,
        lifetime_ticks: int = 0,
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

        self.orbit_radius = orbit_radius
        self.angle = angle
        # Radians per simulation tick: the power converts from degrees per
        # simulated second, so nothing here depends on a clock.
        self.angular_step = angular_step

        # Kinematic: this body is driven, never simulated. Its velocity stays
        # zero and `before_step` sets the position outright.
        self.body = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
        self.body.position = position

        self.shape = pymunk.Circle(self.body, radius)
        self.shape.collision_type = COLLISION_TYPE_DYNAMIC_ENTITY
        # A sensor reports the contact and applies no impulse, so an orb can
        # never shove the fighter it hits.
        self.shape.sensor = True
        self.shape.filter = pymunk.ShapeFilter(group=shape_group(owner_id))

    @property
    def position(self) -> pymunk.Vec2d:
        return self.body.position

    @property
    def shapes(self) -> tuple[pymunk.Shape, ...]:
        return (self.shape,)

    def before_step(self, simulation) -> None:
        """Advance the angle, then follow the owner to its current position."""
        owner = simulation.fighter(self.owner_id)
        if owner is None:
            return

        self.angle += self.angular_step
        offset = pymunk.Vec2d(math.cos(self.angle), math.sin(self.angle))
        target = owner.position + offset * self.orbit_radius

        # A perfect circle would put an orb through the wall when its owner
        # hugs one, so the orbit flattens there rather than leaving the arena.
        self.body.position = simulation.arena.clamp_circle(
            target.x, target.y, self.radius
        )

    def add_to_space(self, space: pymunk.Space) -> None:
        space.add(self.body, self.shape)

    def remove_from_space(self, space: pymunk.Space) -> None:
        space.remove(self.body, self.shape)

"""Temporary simulation objects that appear and disappear during a battle.

Fighters live for the whole battle; powers like Pulse create things that do
not. This is deliberately not an entity-component system: it is the smallest
shared shape that spawning, updating, colliding, despawning, replay export
and rendering can all agree on.

Gameplay meaning stays out of here. An entity exposes what it contributes
(`contact_damage`) and how it reacts to being touched, and the battle mode
decides what to do with it, exactly as powers expose a damage multiplier.
"""

from __future__ import annotations

import pymunk

# One collision type for every physical dynamic entity. The shape-to-entity
# lookup already identifies which entity was actually hit, so a shared type
# keeps the simulation at two collision handlers however many powers spawn
# things.
COLLISION_TYPE_DYNAMIC_ENTITY = 3


class DynamicEntity:
    """A temporary, owned, circular object in the simulation."""

    kind = "entity"

    # Inert by default; physical subclasses opt in.
    contact_damage = 0.0
    # Touching a fighter and touching a wall are separate questions: a
    # projectile is spent by either, while a bouncing clone is spent only by
    # a fighter and rebounds off walls for its whole lifetime.
    despawn_on_ball_contact = False
    despawn_on_wall_contact = False

    def __init__(
        self,
        entity_id: int,
        owner_id: int,
        position: tuple[float, float],
        radius: float,
        color: tuple[int, int, int],
        lifetime_ticks: int = 0,
    ) -> None:
        self.entity_id = entity_id
        self.owner_id = owner_id
        self.radius = radius
        self.color = color

        # 0 means "no lifetime of its own"; the owner despawns it instead.
        self.lifetime_ticks = max(0, int(lifetime_ticks))
        self.age_ticks = 0
        self.active = True

        self._position = pymunk.Vec2d(*position)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        state = "active" if self.active else "dead"
        return f"<{type(self).__name__} id={self.entity_id} {state}>"

    @property
    def position(self) -> pymunk.Vec2d:
        return self._position

    @property
    def shapes(self) -> tuple[pymunk.Shape, ...]:
        """Pymunk shapes to register, if this entity has any."""
        return ()

    @property
    def expired(self) -> bool:
        return self.lifetime_ticks > 0 and self.age_ticks >= self.lifetime_ticks

    def advance(self) -> None:
        """One simulation tick of bookkeeping."""
        self.age_ticks += 1

    def add_to_space(self, space: pymunk.Space) -> None:
        """Join the physics space. Non-physical entities do nothing."""

    def remove_from_space(self, space: pymunk.Space) -> None:
        """Leave the physics space. Non-physical entities do nothing."""

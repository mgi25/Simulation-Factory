"""Ball entity: physics body, presentation data and combat state.

The ball owns its physical state and knows how to scale it away from - and
back to - immutable base values. It does not know what any power does; it
only holds the one currently composed onto it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pymunk

from engine.randomizer import BallSpawn

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids an import cycle
    from engine.arena import Arena
    from powers.power import Power

BALL_MASS = 1.0
# Perfectly elastic and frictionless: the simulation conserves energy and
# therefore never grinds to a halt without artificial nudging.
BALL_ELASTICITY = 1.0
BALL_FRICTION = 0.0

MAX_HEALTH = 100.0

# Collision types, so battle rules can react to ball-vs-ball impacts only.
COLLISION_TYPE_BALL = 1
COLLISION_TYPE_WALL = 2


class Ball:
    """A single competitor: physics body plus health."""

    def __init__(
        self,
        ball_id: int,
        name: str,
        radius: float,
        color: tuple[int, int, int],
        position: tuple[float, float],
        velocity: tuple[float, float],
        max_health: float = MAX_HEALTH,
    ) -> None:
        self.ball_id = ball_id
        self.name = name
        self.color = color

        # Immutable reference state. Temporary effects are always derived from
        # these, never from the current values, so they cannot compound.
        self.base_radius = radius
        self.base_mass = BALL_MASS
        self.radius = radius

        self.power: "Power | None" = None

        self.max_health = max_health
        self._health = max_health
        self.alive = True
        self.damage_taken = 0.0
        self.damage_dealt = 0.0

        moment = pymunk.moment_for_circle(self.base_mass, 0.0, radius)
        self.body = pymunk.Body(self.base_mass, moment)
        self.body.position = position
        self.body.velocity = velocity

        self.shape = pymunk.Circle(self.body, radius)
        self.shape.elasticity = BALL_ELASTICITY
        self.shape.friction = BALL_FRICTION
        self.shape.collision_type = COLLISION_TYPE_BALL

        self.space: pymunk.Space | None = None

    @classmethod
    def from_spawn(cls, spawn: BallSpawn) -> "Ball":
        return cls(
            ball_id=spawn.ball_id,
            name=spawn.name,
            radius=spawn.radius,
            color=spawn.color,
            position=(spawn.x, spawn.y),
            velocity=(spawn.vx, spawn.vy),
        )

    @property
    def health(self) -> float:
        return self._health

    @health.setter
    def health(self, value: float) -> None:
        """Health is always clamped to [0, max_health] and drives `alive`."""
        self._health = min(self.max_health, max(0.0, float(value)))
        self.alive = self._health > 0.0

    @property
    def health_fraction(self) -> float:
        return self._health / self.max_health

    def take_damage(self, amount: float) -> float:
        """Apply damage and return how much was actually removed."""
        if amount <= 0.0 or not self.alive:
            return 0.0
        before = self._health
        self.health = before - amount
        applied = before - self._health
        self.damage_taken += applied
        return applied

    # --- power state (read-only views for renderers and combat rules) ---

    @property
    def power_name(self) -> str:
        return "none" if self.power is None else self.power.name

    @property
    def power_active(self) -> bool:
        return self.power is not None and self.power.active

    @property
    def damage_multiplier(self) -> float:
        """Impact damage multiplier contributed by this ball's power."""
        return 1.0 if self.power is None else self.power.damage_multiplier

    # --- temporary physical effects ---

    def set_size_scale(self, radius_scale: float, mass_scale: float) -> None:
        """Rescale radius, mass and moment from the immutable base values.

        Passing 1.0, 1.0 restores the base state exactly.
        """
        radius = self.base_radius * radius_scale
        mass = self.base_mass * mass_scale

        self.radius = radius
        self.shape.unsafe_set_radius(radius)
        self.body.mass = mass
        self.body.moment = pymunk.moment_for_circle(mass, 0.0, radius)
        if self.space is not None:
            self.space.reindex_shapes_for_body(self.body)

    def scale_velocity(self, factor: float) -> None:
        """Scale the current velocity, preserving its direction."""
        self.body.velocity = self.body.velocity * factor

    def clamp_into(self, arena: "Arena") -> None:
        """Move the centre the minimum needed to fit the circle in `arena`."""
        x, y = self.body.position
        clamped = (
            _clamp_axis(x, arena.left, arena.right, self.radius),
            _clamp_axis(y, arena.top, arena.bottom, self.radius),
        )
        if clamped != (x, y):
            self.body.position = clamped

    # --- physics state ---

    @property
    def position(self) -> pymunk.Vec2d:
        return self.body.position

    @property
    def velocity(self) -> pymunk.Vec2d:
        return self.body.velocity

    def add_to_space(self, space: pymunk.Space) -> None:
        space.add(self.body, self.shape)
        self.space = space


def _clamp_axis(value: float, low: float, high: float, radius: float) -> float:
    """Keep `value` at least `radius` away from both bounds when possible."""
    if high - low <= 2.0 * radius:
        return (low + high) / 2.0
    return min(max(value, low + radius), high - radius)

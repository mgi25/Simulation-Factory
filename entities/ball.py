"""Ball entity: physics body, presentation data and combat state."""

from __future__ import annotations

import pymunk

from engine.randomizer import BallSpawn

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
        self.radius = radius
        self.color = color

        self.max_health = max_health
        self._health = max_health
        self.alive = True
        self.damage_taken = 0.0
        self.damage_dealt = 0.0

        moment = pymunk.moment_for_circle(BALL_MASS, 0.0, radius)
        self.body = pymunk.Body(BALL_MASS, moment)
        self.body.position = position
        self.body.velocity = velocity

        self.shape = pymunk.Circle(self.body, radius)
        self.shape.elasticity = BALL_ELASTICITY
        self.shape.friction = BALL_FRICTION
        self.shape.collision_type = COLLISION_TYPE_BALL

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

    @property
    def position(self) -> pymunk.Vec2d:
        return self.body.position

    @property
    def velocity(self) -> pymunk.Vec2d:
        return self.body.velocity

    def add_to_space(self, space: pymunk.Space) -> None:
        space.add(self.body, self.shape)

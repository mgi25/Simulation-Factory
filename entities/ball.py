"""Ball entity: physics body plus the data the renderer needs."""

from __future__ import annotations

import pymunk

from engine.randomizer import BallSpawn

BALL_MASS = 1.0
# Perfectly elastic and frictionless: the simulation conserves energy and
# therefore never grinds to a halt without artificial nudging.
BALL_ELASTICITY = 1.0
BALL_FRICTION = 0.0


class Ball:
    """A single simulated ball."""

    def __init__(
        self,
        ball_id: int,
        radius: float,
        color: tuple[int, int, int],
        position: tuple[float, float],
        velocity: tuple[float, float],
    ) -> None:
        self.ball_id = ball_id
        self.radius = radius
        self.color = color

        moment = pymunk.moment_for_circle(BALL_MASS, 0.0, radius)
        self.body = pymunk.Body(BALL_MASS, moment)
        self.body.position = position
        self.body.velocity = velocity

        self.shape = pymunk.Circle(self.body, radius)
        self.shape.elasticity = BALL_ELASTICITY
        self.shape.friction = BALL_FRICTION

    @classmethod
    def from_spawn(cls, spawn: BallSpawn) -> "Ball":
        return cls(
            ball_id=spawn.ball_id,
            radius=spawn.radius,
            color=spawn.color,
            position=(spawn.x, spawn.y),
            velocity=(spawn.vx, spawn.vy),
        )

    @property
    def position(self) -> pymunk.Vec2d:
        return self.body.position

    @property
    def velocity(self) -> pymunk.Vec2d:
        return self.body.velocity

    def add_to_space(self, space: pymunk.Space) -> None:
        space.add(self.body, self.shape)

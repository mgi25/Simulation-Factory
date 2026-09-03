"""Headless simulation: seeded setup plus fixed-timestep physics."""

from __future__ import annotations

import math

import pymunk

from engine.arena import WALL_THICKNESS, Arena
from engine.randomizer import generate_ball_spawns, make_rng
from entities.ball import Ball

PHYSICS_HZ = 120
PHYSICS_DT = 1.0 / PHYSICS_HZ

# Upper bound on catch-up ticks per advance() call, so a slow frame cannot
# trigger a runaway "simulate forever to catch up" spiral.
MAX_TICKS_PER_ADVANCE = 8

WALL_ELASTICITY = 1.0
WALL_FRICTION = 0.0

BALL_COUNT = 2


class Simulation:
    """Owns the physics space, the entities and the simulation clock."""

    def __init__(self, seed: int, arena: Arena | None = None) -> None:
        self.seed = seed
        self.arena = arena if arena is not None else Arena.default()
        self.rng = make_rng(seed)

        self.space = pymunk.Space()
        self.space.gravity = (0.0, 0.0)

        self._build_walls()

        self.balls: list[Ball] = [
            Ball.from_spawn(spawn)
            for spawn in generate_ball_spawns(self.rng, self.arena, BALL_COUNT)
        ]
        for ball in self.balls:
            ball.add_to_space(self.space)

        self.ticks = 0
        self.elapsed = 0.0
        self._accumulator = 0.0

    def _build_walls(self) -> None:
        """Four static segments whose inner surface sits on the arena bounds."""
        a = self.arena
        t = WALL_THICKNESS
        outer_left, outer_right = a.left - t, a.right + t
        outer_top, outer_bottom = a.top - t, a.bottom + t

        edges = (
            ((outer_left, outer_top), (outer_right, outer_top)),
            ((outer_left, outer_bottom), (outer_right, outer_bottom)),
            ((outer_left, outer_top), (outer_left, outer_bottom)),
            ((outer_right, outer_top), (outer_right, outer_bottom)),
        )

        self.walls: list[pymunk.Segment] = []
        for start, end in edges:
            wall = pymunk.Segment(self.space.static_body, start, end, t)
            wall.elasticity = WALL_ELASTICITY
            wall.friction = WALL_FRICTION
            self.space.add(wall)
            self.walls.append(wall)

    def step(self) -> None:
        """Advance the physics by exactly one fixed tick."""
        self.space.step(PHYSICS_DT)
        self.ticks += 1
        self.elapsed += PHYSICS_DT

    def advance(self, frame_seconds: float) -> int:
        """Consume real elapsed time and run whole fixed ticks.

        Returns the number of ticks executed. Leftover time is kept in the
        accumulator, so physics never depends on the render framerate.
        """
        self._accumulator += max(0.0, frame_seconds)

        ticks = 0
        while self._accumulator >= PHYSICS_DT and ticks < MAX_TICKS_PER_ADVANCE:
            self.step()
            self._accumulator -= PHYSICS_DT
            ticks += 1

        if self._accumulator >= PHYSICS_DT:
            # Fell too far behind: drop the backlog instead of accumulating it.
            self._accumulator = 0.0

        return ticks

    def is_state_valid(self) -> bool:
        """True while every ball has finite state and is inside the arena."""
        for ball in self.balls:
            x, y = ball.position
            vx, vy = ball.velocity
            if not all(math.isfinite(v) for v in (x, y, vx, vy)):
                return False
            if not self.arena.contains_circle(x, y, 0.0):
                return False
        return True

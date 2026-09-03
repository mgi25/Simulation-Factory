"""Pygame preview renderer.

Draws the logical 1080x1920 canvas into a smaller window; the simulation
itself always works in logical coordinates.
"""

from __future__ import annotations

import os

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from engine.arena import CANVAS_HEIGHT, CANVAS_WIDTH, WALL_THICKNESS
from engine.simulation import Simulation

BACKGROUND_COLOR = (18, 18, 24)
ARENA_COLOR = (32, 34, 44)
WALL_COLOR = (120, 126, 150)

DEFAULT_SCALE = 0.5


class Renderer:
    """Owns the pygame window and draws simulation state."""

    def __init__(self, seed: int, scale: float = DEFAULT_SCALE) -> None:
        self.scale = scale
        self.size = (round(CANVAS_WIDTH * scale), round(CANVAS_HEIGHT * scale))

        pygame.init()
        self.screen = pygame.display.set_mode(self.size)
        pygame.display.set_caption(f"Simulation Factory - seed {seed}")
        self.clock = pygame.time.Clock()

    def tick(self, max_fps: int) -> float:
        """Cap the render loop and return the real elapsed frame time."""
        return self.clock.tick(max_fps) / 1000.0

    def handle_window_events(self) -> bool:
        """Pump window events. Returns False when the app should exit."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return False
        return True

    def draw(self, sim: Simulation) -> None:
        self.screen.fill(BACKGROUND_COLOR)

        arena = sim.arena
        s = self.scale
        arena_rect = pygame.Rect(
            round(arena.left * s),
            round(arena.top * s),
            round(arena.width * s),
            round(arena.height * s),
        )
        pygame.draw.rect(self.screen, ARENA_COLOR, arena_rect)
        pygame.draw.rect(
            self.screen, WALL_COLOR, arena_rect, max(1, round(WALL_THICKNESS * s))
        )

        for ball in sim.balls:
            x, y = ball.position
            pygame.draw.circle(
                self.screen,
                ball.color,
                (round(x * s), round(y * s)),
                max(1, round(ball.radius * s)),
            )

        pygame.display.flip()

    def close(self) -> None:
        pygame.quit()

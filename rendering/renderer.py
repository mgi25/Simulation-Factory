"""Pygame preview renderer.

Draws the logical 1080x1920 canvas into a smaller window; the simulation
itself always works in logical coordinates. The renderer only reads state -
it never applies game rules.
"""

from __future__ import annotations

import os

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from engine.arena import CANVAS_HEIGHT, CANVAS_WIDTH, WALL_THICKNESS
from engine.simulation import Simulation
from entities.ball import Ball
from modes.power_battle import PowerBattleMode

BACKGROUND_COLOR = (18, 18, 24)
ARENA_COLOR = (32, 34, 44)
WALL_COLOR = (120, 126, 150)
TEXT_COLOR = (232, 234, 240)
BAR_BACK_COLOR = (46, 48, 60)

# Logical-canvas layout of the debug HUD.
TIMER_Y = 70
HEALTH_ROW_Y = (190, 275)
HEALTH_BAR_X = (300, 800)
HEALTH_BAR_HEIGHT = 34
LABEL_X = 60
HP_TEXT_X = 1020
RESULT_Y = 1680

TIMER_FONT_SIZE = 76
LABEL_FONT_SIZE = 44
RESULT_FONT_SIZE = 92

DEFAULT_SCALE = 0.5


class Renderer:
    """Owns the pygame window and draws simulation and battle state."""

    def __init__(self, seed: int, scale: float = DEFAULT_SCALE) -> None:
        self.scale = scale
        self.size = (round(CANVAS_WIDTH * scale), round(CANVAS_HEIGHT * scale))

        pygame.init()
        self.screen = pygame.display.set_mode(self.size)
        pygame.display.set_caption(f"Simulation Factory - seed {seed}")
        self.clock = pygame.time.Clock()

        # Bundled pygame default font, sized in screen pixels.
        self._fonts = {
            size: pygame.font.Font(None, max(8, round(size * scale)))
            for size in (TIMER_FONT_SIZE, LABEL_FONT_SIZE, RESULT_FONT_SIZE)
        }
        self._text_cache: dict[tuple[str, int, tuple[int, int, int]], pygame.Surface] = {}

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

    def draw(self, sim: Simulation, mode: PowerBattleMode) -> None:
        self.screen.fill(BACKGROUND_COLOR)
        self._draw_arena(sim)
        self._draw_balls(sim)
        self._draw_hud(sim, mode)
        pygame.display.flip()

    # --- drawing helpers (all inputs in logical canvas coordinates) ---

    def _px(self, value: float) -> int:
        return round(value * self.scale)

    def _text(
        self, text: str, size: int, color: tuple[int, int, int] = TEXT_COLOR
    ) -> pygame.Surface:
        key = (text, size, color)
        surface = self._text_cache.get(key)
        if surface is None:
            surface = self._fonts[size].render(text, True, color)
            self._text_cache[key] = surface
        return surface

    def _blit(self, surface: pygame.Surface, **anchor: tuple[int, int]) -> None:
        self.screen.blit(surface, surface.get_rect(**anchor))

    def _draw_arena(self, sim: Simulation) -> None:
        arena = sim.arena
        rect = pygame.Rect(
            self._px(arena.left),
            self._px(arena.top),
            self._px(arena.width),
            self._px(arena.height),
        )
        pygame.draw.rect(self.screen, ARENA_COLOR, rect)
        pygame.draw.rect(
            self.screen, WALL_COLOR, rect, max(1, self._px(WALL_THICKNESS))
        )

    def _draw_balls(self, sim: Simulation) -> None:
        for ball in sim.balls:
            color = ball.color if ball.alive else tuple(c // 3 for c in ball.color)
            pygame.draw.circle(
                self.screen,
                color,
                (self._px(ball.position.x), self._px(ball.position.y)),
                max(1, self._px(ball.radius)),
            )

    def _draw_hud(self, sim: Simulation, mode: PowerBattleMode) -> None:
        timer = self._text(f"{mode.remaining:.1f}", TIMER_FONT_SIZE)
        self._blit(timer, center=(self._px(CANVAS_WIDTH / 2), self._px(TIMER_Y)))

        for ball, row_y in zip(sim.balls, HEALTH_ROW_Y):
            self._draw_health_row(ball, row_y)

        if mode.finished:
            result = self._text(mode.result_text, RESULT_FONT_SIZE)
            self._blit(
                result, center=(self._px(CANVAS_WIDTH / 2), self._px(RESULT_Y))
            )

    def _draw_health_row(self, ball: Ball, row_y: float) -> None:
        left, right = HEALTH_BAR_X
        bar = pygame.Rect(
            self._px(left),
            self._px(row_y - HEALTH_BAR_HEIGHT / 2),
            self._px(right - left),
            self._px(HEALTH_BAR_HEIGHT),
        )
        pygame.draw.rect(self.screen, BAR_BACK_COLOR, bar)
        filled = bar.copy()
        filled.width = round(bar.width * ball.health_fraction)
        if filled.width > 0:
            pygame.draw.rect(self.screen, ball.color, filled)

        self._blit(
            self._text(ball.name, LABEL_FONT_SIZE, ball.color),
            midleft=(self._px(LABEL_X), self._px(row_y)),
        )
        self._blit(
            self._text(f"{round(ball.health)} HP", LABEL_FONT_SIZE),
            midright=(self._px(HP_TEXT_X), self._px(row_y)),
        )

    def close(self) -> None:
        pygame.quit()

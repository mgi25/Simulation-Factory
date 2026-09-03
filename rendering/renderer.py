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
# The power tag sits under the fighter name, in the gutter left of the bars.
POWER_TAG_OFFSET_Y = 26
HEALTH_BAR_X = (300, 800)
HEALTH_BAR_HEIGHT = 34
LABEL_X = 60
HP_TEXT_X = 1020
RESULT_Y = 1680

TIMER_FONT_SIZE = 76
LABEL_FONT_SIZE = 44
POWER_FONT_SIZE = 30
RESULT_FONT_SIZE = 92

POWER_ACTIVE_COLOR = (255, 236, 150)
POWER_IDLE_COLOR = (140, 145, 165)
ENTITY_CORE_COLOR = (255, 252, 240)
ENTITY_GHOST_COLOR = (58, 62, 78)

# Static obstacles: arena furniture, so they read as part of the floor rather
# than as anything a fighter or a power put there.
OBSTACLE_COLOR = (62, 68, 86)
OBSTACLE_EDGE_COLOR = (108, 116, 142)
OBSTACLE_EDGE_WIDTH = 4


class Renderer:
    """Owns the pygame window and draws simulation and battle state."""

    def __init__(self, seed: int, scale: float) -> None:
        self.scale = scale
        self.size = (round(CANVAS_WIDTH * scale), round(CANVAS_HEIGHT * scale))

        pygame.init()
        self.screen = pygame.display.set_mode(self.size)
        pygame.display.set_caption(f"Simulation Factory - seed {seed}")
        self.clock = pygame.time.Clock()

        # Bundled pygame default font, sized in screen pixels.
        self._fonts = {
            size: pygame.font.Font(None, max(8, round(size * scale)))
            for size in (
                TIMER_FONT_SIZE,
                LABEL_FONT_SIZE,
                POWER_FONT_SIZE,
                RESULT_FONT_SIZE,
            )
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
        self._draw_obstacles(sim)
        self._draw_entities(sim)
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

    def _draw_obstacles(self, sim: Simulation) -> None:
        """Arena geometry, drawn where the simulation currently has it.

        Read from the live runtimes rather than the layout, so a rotating bar
        and a sliding gate are shown at this tick's transform. A rotated bar
        is drawn from the same `corners()` the physics polygon is built from,
        so this view shows where an obstacle actually is rather than an
        axis-aligned approximation of it.
        """
        for runtime in sim.obstacles:
            spec = runtime.placed()
            if spec.is_circle:
                center = (self._px(spec.x), self._px(spec.y))
                radius = max(1, self._px(spec.radius))
                pygame.draw.circle(self.screen, OBSTACLE_COLOR, center, radius)
                pygame.draw.circle(
                    self.screen,
                    OBSTACLE_EDGE_COLOR,
                    center,
                    radius,
                    max(1, self._px(OBSTACLE_EDGE_WIDTH)),
                )
            else:
                corners = [(self._px(x), self._px(y)) for x, y in spec.corners()]
                pygame.draw.polygon(self.screen, OBSTACLE_COLOR, corners)
                pygame.draw.polygon(
                    self.screen,
                    OBSTACLE_EDGE_COLOR,
                    corners,
                    max(1, self._px(OBSTACLE_EDGE_WIDTH)),
                )

    def _draw_balls(self, sim: Simulation) -> None:
        for ball in sim.balls:
            color = ball.color if ball.alive else tuple(c // 3 for c in ball.color)
            # `ball.radius` is the live radius, so Titan's growth shows up here
            # for free.
            center = (self._px(ball.position.x), self._px(ball.position.y))
            radius = max(1, self._px(ball.radius))
            pygame.draw.circle(self.screen, color, center, radius)
            if ball.alive and ball.power_active:
                pygame.draw.circle(
                    self.screen, POWER_ACTIVE_COLOR, center, radius, max(1, self._px(6))
                )

    def _draw_entities(self, sim: Simulation) -> None:
        """Temporary entities as plain circles - debugging, not presentation.

        A clone is drawn as an outline so it reads as a hollow copy; anything
        else gets a bright core so it reads as a projectile.
        """
        for entity in sim.dynamic_entities:
            if not entity.active:
                continue
            center = (self._px(entity.position.x), self._px(entity.position.y))
            radius = max(1, self._px(entity.radius))
            if entity.kind == "echo":
                pygame.draw.circle(
                    self.screen, ENTITY_GHOST_COLOR, center, radius
                )
                pygame.draw.circle(
                    self.screen, entity.color, center, radius, max(1, self._px(5))
                )
            else:
                pygame.draw.circle(self.screen, entity.color, center, radius)
                pygame.draw.circle(
                    self.screen, ENTITY_CORE_COLOR, center, max(1, self._px(entity.radius / 2))
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
            midleft=(self._px(LABEL_X), self._px(row_y - POWER_TAG_OFFSET_Y)),
        )
        tag = ball.power_name.upper()
        color = POWER_IDLE_COLOR
        if ball.power_active:
            tag = f"{tag} [ACTIVE]"
            color = POWER_ACTIVE_COLOR
        self._blit(
            self._text(tag, POWER_FONT_SIZE, color),
            midleft=(self._px(LABEL_X), self._px(row_y + POWER_TAG_OFFSET_Y)),
        )
        self._blit(
            self._text(f"{round(ball.health)} HP", LABEL_FONT_SIZE),
            midright=(self._px(HP_TEXT_X), self._px(row_y)),
        )

    def close(self) -> None:
        pygame.quit()

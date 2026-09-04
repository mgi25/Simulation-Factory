"""Pygame preview for a race.

Draws the 1080x1920 portrait frame the final content is cut for, at a
smaller window scale. Like `rendering.renderer` it only ever reads state -
it applies no rules, and every coordinate it is given is in logical course
pixels. The one thing it adds over the duel renderer is a scrolling camera,
because a race course is several frames tall.

The HUD is deliberately two layers. The race layer - countdown, top three,
the winner - is what a recording is meant to show. The debug layer is
everything a developer needs and a viewer must never see, and it is off
until asked for, so a recording cannot pick it up by accident.
"""

from __future__ import annotations

import os

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from engine.arena import CANVAS_HEIGHT, CANVAS_WIDTH
from race.camera import RaceCamera
from race.course import ROLE_GATE, ROLE_JUMP_PAD, ROLE_PEG, ROLE_WALL
from race.manager import RaceManager, RaceState

__all__ = ["RaceRenderer", "COMMAND_QUIT", "COMMAND_RESTART", "COMMAND_NEW_SEED"]

# Commands the window reports back. The renderer never restarts a race
# itself: it says what was pressed and the caller owns the race lifecycle.
COMMAND_QUIT = "quit"
COMMAND_RESTART = "restart"
COMMAND_NEW_SEED = "new_seed"

BACKGROUND_COLOR = (14, 15, 20)
WALL_COLOR = (44, 47, 60)
RAMP_COLOR = (66, 72, 92)
RAMP_EDGE_COLOR = (96, 104, 130)
# Pegs need to read as a different *kind* of thing from a ramp, not a
# darker one: a viewer has to see at a glance what will deflect a racer and
# what will carry it. Steel blue against the grey of the track.
PEG_COLOR = (78, 116, 176)
PEG_EDGE_COLOR = (158, 198, 250)
GATE_COLOR = (188, 74, 74)
PAD_COLOR = (86, 190, 118)
PAD_EDGE_COLOR = (150, 235, 178)
SPINNER_COLOR = (206, 132, 62)
SPINNER_EDGE_COLOR = (246, 186, 116)
HUB_COLOR = (150, 96, 48)
FINISH_COLOR = (236, 226, 120)

TEXT_COLOR = (234, 236, 242)
DIM_TEXT_COLOR = (150, 156, 174)
DEBUG_TEXT_COLOR = (126, 226, 168)
CHECKPOINT_COLOR = (70, 92, 84)
BANNER_COLOR = (18, 20, 28)

ROLE_COLORS = {
    ROLE_WALL: (WALL_COLOR, None),
    ROLE_PEG: (PEG_COLOR, PEG_EDGE_COLOR),
    ROLE_GATE: (GATE_COLOR, None),
    ROLE_JUMP_PAD: (PAD_COLOR, PAD_EDGE_COLOR),
}

# Logical-canvas HUD layout. The banner has to be tall enough to contain
# the third standings line, or the debug overlay below it collides with it.
BANNER_HEIGHT = 280
TIMER_Y = 74
STANDINGS_X = 54
STANDINGS_Y = 132
STANDINGS_STEP = 52
COUNTDOWN_Y = CANVAS_HEIGHT * 0.42
RESULT_Y = CANVAS_HEIGHT - 150

TITLE_FONT_SIZE = 54
STANDING_FONT_SIZE = 44
COUNTDOWN_FONT_SIZE = 300
RESULT_FONT_SIZE = 86
DEBUG_FONT_SIZE = 30
RACER_FONT_SIZE = 34

STANDINGS_SHOWN = 3
# How far outside the frame a piece may be and still be drawn. Only needs to
# cover the largest half-extent of anything in the course.
CULL_MARGIN = 420.0


class RaceRenderer:
    """Owns the pygame window and draws a race through a scrolling camera."""

    def __init__(self, seed: int, scale: float = 0.5, debug: bool = False) -> None:
        self.scale = scale
        self.debug = debug
        self.paused = False
        self.size = (round(CANVAS_WIDTH * scale), round(CANVAS_HEIGHT * scale))

        pygame.init()
        self.screen = pygame.display.set_mode(self.size)
        self.set_caption(seed)
        self.clock = pygame.time.Clock()

        self._fonts = {
            size: pygame.font.Font(None, max(8, round(size * scale)))
            for size in (
                TITLE_FONT_SIZE,
                STANDING_FONT_SIZE,
                COUNTDOWN_FONT_SIZE,
                RESULT_FONT_SIZE,
                DEBUG_FONT_SIZE,
                RACER_FONT_SIZE,
            )
        }
        self._text_cache: dict[tuple[str, int, tuple[int, int, int]], pygame.Surface] = {}

    def set_caption(self, seed: int) -> None:
        pygame.display.set_caption(f"Simulation Factory - race seed {seed}")

    # --- window ---

    def tick(self, max_fps: int) -> float:
        """Cap the render loop and return the real elapsed frame time.

        The race does not consume this to decide how much to simulate - it
        always steps a fixed number of ticks per frame - so a slow machine
        plays a race slowly rather than differently. It is used for the
        camera easing and the FPS readout only.
        """
        return self.clock.tick(max_fps) / 1000.0

    @property
    def fps(self) -> float:
        return self.clock.get_fps()

    def handle_events(self) -> set[str]:
        """Pump window events and report the commands pressed.

        Toggles the renderer owns - pause and the debug overlay - are
        applied here. Anything that changes which race is running is handed
        back to the caller instead.
        """
        commands: set[str] = set()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                commands.add(COMMAND_QUIT)
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    commands.add(COMMAND_QUIT)
                elif event.key == pygame.K_r:
                    commands.add(COMMAND_RESTART)
                elif event.key == pygame.K_n:
                    commands.add(COMMAND_NEW_SEED)
                elif event.key == pygame.K_SPACE:
                    self.paused = not self.paused
                elif event.key == pygame.K_F1:
                    self.debug = not self.debug
        return commands

    def close(self) -> None:
        pygame.quit()

    def save_frame(self, path: str) -> str:
        """Write the current frame to a PNG. Used for headless validation."""
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)
        pygame.image.save(self.screen, path)
        return path

    # --- drawing ---

    def draw(self, manager: RaceManager, camera: RaceCamera) -> None:
        self.screen.fill(BACKGROUND_COLOR)
        self._draw_course(manager, camera)
        self._draw_spinners(manager, camera)
        self._draw_finish_line(manager, camera)
        if self.debug:
            self._draw_checkpoints(manager, camera)
        self._draw_racers(manager, camera)
        self._draw_hud(manager)
        if self.debug:
            self._draw_debug(manager, camera)
        pygame.display.flip()

    # --- coordinate helpers ---

    def _px(self, value: float) -> int:
        return round(value * self.scale)

    def _point(self, x: float, y: float, camera: RaceCamera) -> tuple[int, int]:
        return (round(x * self.scale), round((y - camera.y) * self.scale))

    def _text(
        self, text: str, size: int, color: tuple[int, int, int] = TEXT_COLOR
    ) -> pygame.Surface:
        key = (text, size, color)
        surface = self._text_cache.get(key)
        if surface is None:
            surface = self._fonts[size].render(text, True, color)
            self._text_cache[key] = surface
        return surface

    def _blit(self, surface: pygame.Surface, **anchor) -> None:
        self.screen.blit(surface, surface.get_rect(**anchor))

    # --- course ---

    def _draw_course(self, manager: RaceManager, camera: RaceCamera) -> None:
        """Every static piece inside the frame, drawn from its own geometry.

        A gate that has been opened is simply gone from the drawing as well
        as from the space, because the renderer reads the live runtimes
        rather than the course data - so what is on screen is what a racer
        can actually hit.
        """
        for runtime in manager.sim.track.pieces:
            if not runtime.present:
                continue
            piece = runtime.piece
            spec = piece.spec
            top, bottom = spec.bounds()[1], spec.bounds()[3]
            if bottom < camera.top - CULL_MARGIN or top > camera.bottom + CULL_MARGIN:
                continue
            fill, edge = ROLE_COLORS.get(piece.role, (RAMP_COLOR, RAMP_EDGE_COLOR))
            if spec.is_circle:
                center = self._point(spec.x, spec.y, camera)
                radius = max(1, self._px(spec.radius))
                pygame.draw.circle(self.screen, fill, center, radius)
                if edge is not None:
                    pygame.draw.circle(self.screen, edge, center, radius, max(1, self._px(4)))
            else:
                corners = [self._point(x, y, camera) for x, y in spec.corners()]
                pygame.draw.polygon(self.screen, fill, corners)
                if edge is not None:
                    pygame.draw.polygon(self.screen, edge, corners, max(1, self._px(3)))

    def _draw_spinners(self, manager: RaceManager, camera: RaceCamera) -> None:
        """Arms taken from the live bodies, so the drawing cannot drift.

        Same principle the duel replay uses for a rotating bar: draw the
        transform the physics actually has, never the formula that produced
        it.
        """
        for spinner in manager.sim.track.spinners:
            spec = spinner.spec
            if not camera.visible(spec.y, spec.reach + CULL_MARGIN):
                continue
            for polygon in spinner.arm_polygons():
                corners = [self._point(x, y, camera) for x, y in polygon]
                pygame.draw.polygon(self.screen, SPINNER_COLOR, corners)
                pygame.draw.polygon(
                    self.screen, SPINNER_EDGE_COLOR, corners, max(1, self._px(3))
                )
            hub = self._point(spec.x, spec.y, camera)
            pygame.draw.circle(self.screen, HUB_COLOR, hub, max(1, self._px(spec.hub_radius)))

    def _draw_finish_line(self, manager: RaceManager, camera: RaceCamera) -> None:
        finish_y = manager.course.finish_y
        if not camera.visible(finish_y, 80.0):
            return
        y = self._point(0.0, finish_y, camera)[1]
        pygame.draw.line(
            self.screen, FINISH_COLOR, (0, y), (self.size[0], y), max(2, self._px(8))
        )
        self._blit(
            self._text("FINISH", TITLE_FONT_SIZE, FINISH_COLOR),
            midleft=(self._px(80), y - self._px(46)),
        )

    def _draw_checkpoints(self, manager: RaceManager, camera: RaceCamera) -> None:
        for checkpoint in manager.course.checkpoints:
            if not camera.visible(checkpoint.y, 40.0):
                continue
            y = self._point(0.0, checkpoint.y, camera)[1]
            pygame.draw.line(
                self.screen, CHECKPOINT_COLOR, (0, y), (self.size[0], y), max(1, self._px(3))
            )
            self._blit(
                self._text(
                    f"{checkpoint.index} {checkpoint.name}", DEBUG_FONT_SIZE, CHECKPOINT_COLOR
                ),
                midright=(self.size[0] - self._px(20), y - self._px(20)),
            )

    def _draw_racers(self, manager: RaceManager, camera: RaceCamera) -> None:
        for racer in manager.sim.racers:
            if racer.retired or not camera.visible(racer.position.y, racer.radius + 40.0):
                continue
            center = self._point(racer.position.x, racer.position.y, camera)
            radius = max(2, self._px(racer.radius))
            pygame.draw.circle(self.screen, racer.color, center, radius)
            pygame.draw.circle(
                self.screen, BACKGROUND_COLOR, center, radius, max(1, self._px(3))
            )
            # The number, so a viewer can follow one racer through a pile-up.
            self._blit(
                self._text(f"{racer.racer_id + 1}", RACER_FONT_SIZE, BACKGROUND_COLOR),
                center=center,
            )

    # --- HUD ---

    def _draw_hud(self, manager: RaceManager) -> None:
        banner = pygame.Surface((self.size[0], self._px(BANNER_HEIGHT)))
        banner.set_alpha(190)
        banner.fill(BANNER_COLOR)
        self.screen.blit(banner, (0, 0))

        if manager.state is RaceState.COUNTDOWN:
            title, color = "GET READY", DIM_TEXT_COLOR
        elif manager.winner is not None:
            title, color = f"{manager.winner.name} WINS", manager.winner.color
        else:
            title, color = "RACE", TEXT_COLOR
        self._blit(
            self._text(title, TITLE_FONT_SIZE, color),
            center=(self.size[0] // 2, self._px(TIMER_Y)),
        )

        for position, racer in enumerate(manager.ranked[:STANDINGS_SHOWN]):
            label = f"{position + 1}. {racer.name}"
            if racer.finished and racer.finish_time is not None:
                label += f"  {racer.finish_time:.2f}s"
            self._blit(
                self._text(label, STANDING_FONT_SIZE, racer.color),
                midleft=(self._px(STANDINGS_X), self._px(STANDINGS_Y + position * STANDINGS_STEP)),
            )

        if manager.state is RaceState.COUNTDOWN:
            self._draw_countdown(manager)
        elif manager.winner is not None:
            self._blit(
                self._text(
                    f"{manager.winner.name} WINS", RESULT_FONT_SIZE, manager.winner.color
                ),
                center=(self.size[0] // 2, self._px(RESULT_Y)),
            )

    def _draw_countdown(self, manager: RaceManager) -> None:
        number = manager.countdown_number
        text = str(number) if number > 0 else "GO"
        self._blit(
            self._text(text, COUNTDOWN_FONT_SIZE, TEXT_COLOR),
            center=(self.size[0] // 2, self._px(COUNTDOWN_Y)),
        )

    def _draw_debug(self, manager: RaceManager, camera: RaceCamera) -> None:
        """Developer overlay. Never present in a recording: it is off by
        default and F1 is the only thing that turns it on."""
        sim = manager.sim
        section = manager.course.section_at(camera.focus(sim.racers))
        lines = [
            f"seed {sim.seed}   course {manager.course.course_id}",
            f"fps {self.fps:5.1f}   tick {sim.ticks}   t {manager.race_time:6.2f}s",
            f"state {manager.state.value}" + ("  PAUSED" if self.paused else ""),
            f"camera {camera.y:7.1f}   section {section.name if section else '-'}",
            f"lead changes {manager.leader_changes}   overtakes {manager.overtakes}",
            f"recoveries {manager.recoveries}   retired {manager.retirements}"
            f"   big hits {manager.large_collisions}",
            "",
        ]
        for racer in manager.ranked:
            state = "FIN" if racer.finished else ("RET" if racer.retired else "   ")
            lines.append(
                f"{racer.rank:2d} {racer.name} cp{racer.checkpoint:2d} "
                f"p{racer.progress:5.2f} v{racer.speed:6.1f} {state}"
                + (f" x{racer.recoveries}" if racer.recoveries else "")
            )

        y = self._px(BANNER_HEIGHT + 30)
        step = self._px(DEBUG_FONT_SIZE + 4)
        for line in lines:
            if line:
                self._blit(
                    self._text(line, DEBUG_FONT_SIZE, DEBUG_TEXT_COLOR),
                    topleft=(self._px(24), y),
                )
            y += step

"""Race V0.1 tests: the preview renderer draws, and the debug layer is optional.

Drawn against SDL's dummy driver, so there is no window and no display. The
point is not to check that the picture is pretty - it is to check that the
renderer never crashes on real race state at any point of a race, and that
the developer overlay genuinely leaves no trace when it is off. A recording
must not be able to pick it up by accident.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

pygame = pytest.importorskip("pygame")

from engine.arena import CANVAS_HEIGHT, CANVAS_WIDTH  # noqa: E402
from race.camera import RaceCamera  # noqa: E402
from race.config import PHYSICS_HZ  # noqa: E402
from race.manager import RaceManager  # noqa: E402
from race.simulation import RaceSimulation  # noqa: E402

SCALE = 0.25


@pytest.fixture
def drawing():
    """A renderer and a race, torn down together."""
    from rendering.race_renderer import RaceRenderer

    try:
        renderer = RaceRenderer(4242, scale=SCALE)
    except pygame.error as error:  # pragma: no cover - no SDL at all
        pytest.skip(f"no usable SDL video driver: {error}")
    manager = RaceManager(RaceSimulation(4242))
    camera = RaceCamera(manager.course, CANVAS_HEIGHT)
    camera.snap_to(manager.sim.racers)
    try:
        yield renderer, manager, camera
    finally:
        renderer.close()


def frame_bytes(renderer) -> bytes:
    return pygame.image.tostring(renderer.screen, "RGB")


def test_the_window_is_the_portrait_canvas_at_scale(drawing) -> None:
    renderer, _, _ = drawing
    assert renderer.size == (
        round(CANVAS_WIDTH * SCALE),
        round(CANVAS_HEIGHT * SCALE),
    )


def test_drawing_a_whole_race_never_raises(drawing) -> None:
    """Every phase: the grid, the countdown, all eight sections, the finish."""
    renderer, manager, camera = drawing
    frames = 0
    while True:
        renderer.draw(manager, camera)
        frames += 1
        for _ in range(2):
            if not manager.step():
                break
        camera.update(manager.sim.racers, 2.0 / PHYSICS_HZ)
        if manager.complete:
            break
    renderer.draw(manager, camera)
    assert frames > 60, "a whole race should be hundreds of frames"


def test_the_frame_is_a_picture_rather_than_an_empty_rectangle(drawing) -> None:
    renderer, manager, camera = drawing
    for _ in range(PHYSICS_HZ * 5):
        manager.step()
    camera.update(manager.sim.racers, 1.0)
    renderer.draw(manager, camera)
    colours = set(pygame.transform.average_color(renderer.screen)[:3])
    assert colours != {0}, "the frame is entirely black"
    # More than a flat fill: the course and the racers are actually drawn.
    surface = renderer.screen
    sampled = {
        surface.get_at((x, y))[:3]
        for x in range(0, surface.get_width(), 7)
        for y in range(0, surface.get_height(), 7)
    }
    assert len(sampled) > 6


def test_the_debug_overlay_is_off_until_asked_for(drawing) -> None:
    """The requirement that debug information be removable for a recording."""
    renderer, manager, camera = drawing
    assert not renderer.debug
    for _ in range(PHYSICS_HZ * 4):
        manager.step()
    camera.update(manager.sim.racers, 1.0)

    renderer.draw(manager, camera)
    clean = frame_bytes(renderer)
    renderer.draw(manager, camera)
    assert frame_bytes(renderer) == clean, "drawing twice must be identical"

    renderer.debug = True
    renderer.draw(manager, camera)
    assert frame_bytes(renderer) != clean, "the overlay drew nothing"

    renderer.debug = False
    renderer.draw(manager, camera)
    assert frame_bytes(renderer) == clean, "turning it off left something behind"


def test_the_countdown_and_the_winner_both_get_drawn(drawing) -> None:
    renderer, manager, camera = drawing
    renderer.draw(manager, camera)
    counting = frame_bytes(renderer)

    manager.run()
    camera.snap_to(manager.sim.racers)
    renderer.draw(manager, camera)
    assert manager.winner is not None
    assert frame_bytes(renderer) != counting


def test_a_saved_frame_is_a_real_png(drawing, tmp_path) -> None:
    from rendering.png_frames import read_header

    renderer, manager, camera = drawing
    for _ in range(PHYSICS_HZ * 3):
        manager.step()
    renderer.draw(manager, camera)
    path = renderer.save_frame(str(tmp_path / "frame.png"))
    header = read_header(path)
    assert (header.width, header.height) == renderer.size


def test_pause_and_debug_are_window_toggles_not_race_state(drawing) -> None:
    """The renderer owns its own toggles and never touches the race."""
    renderer, manager, camera = drawing
    ticks = manager.sim.ticks
    renderer.paused = True
    renderer.debug = True
    renderer.draw(manager, camera)
    assert manager.sim.ticks == ticks
    assert manager.state.value == "countdown"


# --- the control scheme -----------------------------------------------------


def press(key) -> None:
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key))


def test_the_documented_debug_keys_do_what_they_say(drawing) -> None:
    """R restart, N new seed, Space pause, F1 debug, Esc/Q quit."""
    from rendering.race_renderer import (
        COMMAND_NEW_SEED,
        COMMAND_QUIT,
        COMMAND_RESTART,
    )

    renderer, _, _ = drawing
    pygame.event.clear()

    press(pygame.K_r)
    assert renderer.handle_events() == {COMMAND_RESTART}

    press(pygame.K_n)
    assert renderer.handle_events() == {COMMAND_NEW_SEED}

    for key in (pygame.K_ESCAPE, pygame.K_q):
        press(key)
        assert renderer.handle_events() == {COMMAND_QUIT}

    # Pause and the overlay are the window's own state, not commands.
    assert not renderer.paused
    press(pygame.K_SPACE)
    assert renderer.handle_events() == set()
    assert renderer.paused
    press(pygame.K_SPACE)
    renderer.handle_events()
    assert not renderer.paused

    assert not renderer.debug
    press(pygame.K_F1)
    assert renderer.handle_events() == set()
    assert renderer.debug


def test_closing_the_window_asks_to_quit(drawing) -> None:
    from rendering.race_renderer import COMMAND_QUIT

    renderer, _, _ = drawing
    pygame.event.clear()
    pygame.event.post(pygame.event.Event(pygame.QUIT))
    assert renderer.handle_events() == {COMMAND_QUIT}


def test_an_unbound_key_does_nothing(drawing) -> None:
    renderer, _, _ = drawing
    pygame.event.clear()
    press(pygame.K_z)
    assert renderer.handle_events() == set()
    assert not renderer.paused and not renderer.debug

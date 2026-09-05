"""Plots, drawn with pygame because the lab has no plotting library.

Sections 26 and 27 of the brief: radius against time, and a mechanical-energy
proxy against time. Both are asked for as evidence rather than decoration -
"we do not require perfectly monotonic decay because collisions can move a
marble outward, but overall a believable drained marble should tend to lose
orbital radius" is a claim you can only settle by looking at the curve.

There is no matplotlib in this project and adding one for four charts would be
a strange trade, so these are drawn directly. They are plain on purpose: axes,
gridlines, one line per marble in the same colours the videos use, so a curve
can be matched to a marble in the footage.
"""

from __future__ import annotations

import math
import os

from physics_lab.analysis.render import BACKGROUND, MARBLE_COLOURS
from physics_lab.common.labreplay import STATE_DRAINED, STATE_ESCAPED, LabRun

__all__ = ["radius_plot", "energy_plot", "comparison_plot"]

WIDTH = 1000
HEIGHT = 560
MARGIN_LEFT = 84
MARGIN_RIGHT = 24
MARGIN_TOP = 56
MARGIN_BOTTOM = 56

AXIS = (110, 118, 130)
GRID = (46, 50, 58)
TEXT = (200, 206, 216)
SUBTEXT = (132, 138, 150)


def _frame(pygame, canvas, title, x_label, y_label, x_max, y_max, y_min=0.0):
    """Axes, gridlines and labels. Returns a world-to-pixel mapping."""
    big = pygame.font.SysFont("consolas,dejavusansmono,monospace", 20)
    small = pygame.font.SysFont("consolas,dejavusansmono,monospace", 14)
    canvas.fill(BACKGROUND)

    plot_width = WIDTH - MARGIN_LEFT - MARGIN_RIGHT
    plot_height = HEIGHT - MARGIN_TOP - MARGIN_BOTTOM

    def to_pixels(x, y):
        return (
            MARGIN_LEFT + plot_width * (x / x_max if x_max else 0.0),
            MARGIN_TOP + plot_height * (1.0 - (y - y_min) / (y_max - y_min or 1.0)),
        )

    for step in range(6):
        y = y_min + (y_max - y_min) * step / 5
        pixel = to_pixels(0, y)
        pygame.draw.line(canvas, GRID, (MARGIN_LEFT, pixel[1]), (WIDTH - MARGIN_RIGHT, pixel[1]), 1)
        canvas.blit(small.render(f"{y:6.3f}", True, SUBTEXT), (10, pixel[1] - 8))
    for step in range(7):
        x = x_max * step / 6
        pixel = to_pixels(x, y_min)
        pygame.draw.line(canvas, GRID, (pixel[0], MARGIN_TOP), (pixel[0], HEIGHT - MARGIN_BOTTOM), 1)
        canvas.blit(small.render(f"{x:.1f}", True, SUBTEXT), (pixel[0] - 12, HEIGHT - MARGIN_BOTTOM + 8))

    pygame.draw.line(canvas, AXIS, (MARGIN_LEFT, MARGIN_TOP), (MARGIN_LEFT, HEIGHT - MARGIN_BOTTOM), 2)
    pygame.draw.line(
        canvas, AXIS,
        (MARGIN_LEFT, HEIGHT - MARGIN_BOTTOM), (WIDTH - MARGIN_RIGHT, HEIGHT - MARGIN_BOTTOM), 2,
    )
    canvas.blit(big.render(title, True, TEXT), (MARGIN_LEFT, 16))
    canvas.blit(small.render(x_label, True, SUBTEXT), (WIDTH - MARGIN_RIGHT - 140, HEIGHT - 22))
    canvas.blit(small.render(y_label, True, SUBTEXT), (10, 32))
    return to_pixels


def _series(run: LabRun):
    """Per marble: (times, radii, speeds), while it is still in the bowl."""
    data: dict[int, tuple[list[float], list[float], list[float]]] = {}
    for frame in run.frames:
        for marble in frame.marbles:
            if marble.state in (STATE_DRAINED, STATE_ESCAPED):
                continue
            times, radii, speeds = data.setdefault(marble.marble_id, ([], [], []))
            times.append(frame.time)
            radii.append(math.hypot(marble.position[0], marble.position[2]))
            speeds.append(math.sqrt(sum(value * value for value in marble.velocity)))
    return data


def radius_plot(run: LabRun, path: str, title: str = "") -> str:
    """Radius from the bowl axis against time, one line per marble."""
    import pygame

    pygame.init()
    canvas = pygame.Surface((WIDTH, HEIGHT))
    data = _series(run)
    duration = max((times[-1] for times, _, _ in data.values()), default=1.0)
    top = float(run.benchmark["surface_max_radius"])
    to_pixels = _frame(
        pygame, canvas,
        title or f"{run.approach}  seed {run.seed}: radius from the bowl axis",
        "seconds", "radius (m)", duration, top,
    )
    drain = float(run.benchmark["drain_radius"])
    edge = to_pixels(0, drain)
    pygame.draw.line(
        canvas, (150, 90, 70), (MARGIN_LEFT, edge[1]), (WIDTH - MARGIN_RIGHT, edge[1]), 2
    )
    for marble_id, (times, radii, _) in sorted(data.items()):
        colour = MARBLE_COLOURS[marble_id % len(MARBLE_COLOURS)]
        points = [to_pixels(t, r) for t, r in zip(times, radii)]
        if len(points) > 1:
            pygame.draw.lines(canvas, colour, False, points, 2)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    pygame.image.save(canvas, path)
    pygame.quit()
    return path


def energy_plot(run: LabRun, path: str, title: str = "") -> str:
    """Mechanical energy above the drain lip, per marble, against time."""
    import pygame

    pygame.init()
    canvas = pygame.Surface((WIDTH, HEIGHT))
    benchmark = run.benchmark
    mass = float(benchmark["marble_mass"])
    gravity = float(benchmark["gravity"])
    inertia = float(benchmark["rolling_inertia_factor"]) * mass * float(benchmark["marble_radius"]) ** 2

    curves: dict[int, tuple[list[float], list[float]]] = {}
    for frame in run.frames:
        for marble in frame.marbles:
            if marble.state in (STATE_DRAINED, STATE_ESCAPED):
                continue
            times, energies = curves.setdefault(marble.marble_id, ([], []))
            speed_squared = sum(value * value for value in marble.velocity)
            spin_squared = sum(value * value for value in marble.spin)
            times.append(frame.time)
            energies.append(
                mass * gravity * marble.position[1]
                + 0.5 * mass * speed_squared
                + 0.5 * inertia * spin_squared
            )

    duration = max((times[-1] for times, _ in curves.values()), default=1.0)
    top = max((max(values) for _, values in curves.values()), default=1.0)
    to_pixels = _frame(
        pygame, canvas,
        title or f"{run.approach}  seed {run.seed}: mechanical energy per marble",
        "seconds", "joules", duration, top * 1.05,
    )
    for marble_id, (times, energies) in sorted(curves.items()):
        colour = MARBLE_COLOURS[marble_id % len(MARBLE_COLOURS)]
        points = [to_pixels(t, e) for t, e in zip(times, energies)]
        if len(points) > 1:
            pygame.draw.lines(canvas, colour, False, points, 2)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    pygame.image.save(canvas, path)
    pygame.quit()
    return path


def comparison_plot(runs: dict[str, LabRun], path: str, title: str = "") -> str:
    """Mean radius against time for several approaches, on one pair of axes.

    The single most compact statement of the whole study: three curves that
    start together and descend at their own rates, plus - where a production
    replay is supplied - the flat, brief line the current 2D bowl produces.
    """
    import pygame

    pygame.init()
    canvas = pygame.Surface((WIDTH, HEIGHT))
    palette = ((120, 200, 255), (255, 170, 90), (150, 230, 150), (240, 110, 110))

    curves = []
    for label, run in runs.items():
        data = _series(run)
        by_time: dict[float, list[float]] = {}
        for _, (times, radii, _) in data.items():
            for time, radius in zip(times, radii):
                by_time.setdefault(round(time, 4), []).append(radius)
        points = sorted((time, sum(values) / len(values)) for time, values in by_time.items())
        curves.append((label, points))

    duration = max((points[-1][0] for _, points in curves if points), default=1.0)
    top = float(next(iter(runs.values())).benchmark["surface_max_radius"])
    to_pixels = _frame(
        pygame, canvas,
        title or "mean radius from the bowl axis",
        "seconds", "mean radius (m)", duration, top,
    )
    legend = pygame.font.SysFont("consolas,dejavusansmono,monospace", 15)
    for index, (label, points) in enumerate(curves):
        colour = palette[index % len(palette)]
        pixels = [to_pixels(time, radius) for time, radius in points]
        if len(pixels) > 1:
            pygame.draw.lines(canvas, colour, False, pixels, 3)
        row = MARGIN_TOP + 12 + index * 22
        pygame.draw.line(canvas, colour, (WIDTH - 300, row), (WIDTH - 260, row), 3)
        canvas.blit(legend.render(label, True, TEXT), (WIDTH - 252, row - 9))

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    pygame.image.save(canvas, path)
    pygame.quit()
    return path

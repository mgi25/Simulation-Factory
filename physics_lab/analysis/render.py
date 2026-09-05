"""One neutral renderer, for every approach.

Section 20 of the brief asks for simple, neutral visualisation: a plain bowl,
coloured marbles, a fixed useful camera, no particles, no bloom, no cuts. This
is that, and the important word is *one*. Both prototypes are drawn by this
same function from the same lab JSON, with the same camera, the same colours
and the same clock, so that a difference between two videos is a difference in
the physics and not in how each engine's renderer happened to be written. It
is the reason this does not go anywhere near `neon_scene.gd`.

Deliberately software-rendered with pygame, which the project already depends
on. A GPU renderer would look better and would introduce a driver into a
comparison that is supposed to be about trajectories.

Three things are drawn that are not decoration:

* **the bowl, as concentric rings and radial spokes**, projected through the
  same camera as the marbles. A viewer can see the surface a marble is on.
* **a trail** behind each marble, a fixed number of past samples. Orbit shape
  is a property of the path, not of the instant, and a still frame of eight
  dots says nothing about whether they are orbiting.
* **a pole marker**, a lighter disc drawn where the marble's own +y axis
  meets its surface. It sweeps as the marble rotates and sits still if the
  marble slides, which is what makes "marbles sliding like hockey pucks" -
  failure mode one in section 23 - something a viewer can see rather than
  something only the rolling-ratio metric knows about.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass

from physics_lab.common.bowl import BowlSurface
from physics_lab.common.labreplay import STATE_DRAINED, STATE_ESCAPED, LabRun

__all__ = ["Camera", "MARBLE_COLOURS", "render_run", "render_pair"]

WIDTH = 960
HEIGHT = 960

BACKGROUND = (22, 24, 28)
BOWL_LINE = (62, 68, 78)
BOWL_RIM = (96, 104, 118)
DRAIN_LINE = (150, 90, 70)
TEXT = (196, 202, 212)
LABEL = (128, 134, 146)

# Eight hues a viewer can tell apart at video scale, and the same eight in
# every render so that marble 3 is the same marble in both videos.
MARBLE_COLOURS = (
    (235, 72, 72),
    (64, 156, 248),
    (96, 214, 128),
    (246, 196, 64),
    (198, 108, 246),
    (255, 141, 58),
    (72, 226, 224),
    (245, 122, 186),
)

TRAIL_SAMPLES = 45


@dataclass(frozen=True)
class Camera:
    """A fixed three-quarter view. Never moves, never cuts, never zooms.

    Elevation 34 degrees was chosen the way `neon_scene.gd` chose 52: by
    looking. Lower and the far wall of the bowl hides the near one; higher and
    the dish flattens towards a plan view and the spiral stops reading as a
    descent. Different from the production figure because this camera is
    looking at one bowl rather than a whole machine.
    """

    elevation_degrees: float = 34.0
    azimuth_degrees: float = -28.0
    distance: float = 1.85
    scale: float = 1250.0
    target_y: float = 0.125

    def project(self, point: tuple[float, float, float]) -> tuple[float, float, float]:
        """World to screen, plus a depth for painter ordering."""
        elevation = math.radians(self.elevation_degrees)
        azimuth = math.radians(self.azimuth_degrees)
        x, y, z = point[0], point[1] - self.target_y, point[2]

        cos_a, sin_a = math.cos(azimuth), math.sin(azimuth)
        east = x * cos_a - z * sin_a
        north = x * sin_a + z * cos_a

        cos_e, sin_e = math.cos(elevation), math.sin(elevation)
        depth = north * cos_e - y * sin_e + self.distance
        up = north * sin_e + y * cos_e

        if depth <= 0.05:
            depth = 0.05
        perspective = self.scale / depth
        return (
            WIDTH * 0.5 + east * perspective,
            HEIGHT * 0.5 - up * perspective,
            depth,
        )

    def radius_on_screen(self, point: tuple[float, float, float], radius: float) -> float:
        depth = self.project(point)[2]
        return max(1.5, radius * self.scale / depth)


def _bowl_lines(surface: BowlSurface, camera: Camera):
    """The dish as rings and spokes, precomputed once for the whole video."""
    rings = []
    for fraction in (0.16, 0.3, 0.45, 0.6, 0.75, 0.9, 1.0, 1.12):
        radius = surface.lip_start + (surface.max_radius - surface.lip_start) * fraction
        height = surface.height(radius) if radius <= surface.max_radius else None
        if height is None:
            continue
        points = [
            camera.project(
                (radius * math.cos(step * math.pi / 60), height, radius * math.sin(step * math.pi / 60))
            )[:2]
            for step in range(121)
        ]
        rings.append((points, BOWL_RIM if fraction >= 1.0 else BOWL_LINE))

    spokes = []
    for index in range(24):
        angle = 2.0 * math.pi * index / 24
        points = []
        for step in range(31):
            radius = surface.lip_start + (surface.max_radius - surface.lip_start) * step / 30
            points.append(
                camera.project(
                    (radius * math.cos(angle), surface.height(radius), radius * math.sin(angle))
                )[:2]
            )
        spokes.append(points)

    drain = [
        camera.project(
            (
                surface.drain_radius * math.cos(step * math.pi / 30),
                surface.lip_pivot_y,
                surface.drain_radius * math.sin(step * math.pi / 30),
            )
        )[:2]
        for step in range(61)
    ]
    return rings, spokes, drain


def _draw_marble(pygame, surface_target, camera, colour, position, orientation, radius):
    """A marble as a shaded disc with a pole marker, so spin is visible."""
    screen = camera.project(position)
    pixels = camera.radius_on_screen(position, radius)
    centre = (int(screen[0]), int(screen[1]))

    shadow = tuple(int(value * 0.35) for value in colour)
    pygame.draw.circle(surface_target, shadow, centre, int(pixels) + 2)
    pygame.draw.circle(surface_target, colour, centre, int(pixels))

    # The pole: the marble's own +y axis, rotated by its orientation and
    # projected. A rolling marble's pole sweeps; a sliding one's does not.
    qx, qy, qz, qw = orientation
    pole = (
        2.0 * (qx * qy + qz * qw),
        1.0 - 2.0 * (qx * qx + qz * qz),
        2.0 * (qy * qz - qx * qw),
    )
    tip = tuple(position[index] + pole[index] * radius * 0.92 for index in range(3))
    tip_screen = camera.project(tip)
    highlight = tuple(min(255, int(value * 0.35 + 40)) for value in colour)
    pygame.draw.circle(
        surface_target,
        highlight,
        (int(tip_screen[0]), int(tip_screen[1])),
        max(2, int(pixels * 0.34)),
    )


def render_run(
    run: LabRun,
    out_dir: str,
    camera: Camera | None = None,
    label: str = "",
    frame_limit: int | None = None,
) -> int:
    """Draw one lab run to a numbered PNG sequence. Returns the frame count."""
    import pygame

    pygame.init()
    camera = camera or Camera()
    benchmark = run.benchmark
    surface = BowlSurface(
        rim_radius=float(benchmark["rim_radius"]),
        rim_depth=float(benchmark["rim_depth"]),
        profile_power=float(benchmark["profile_power"]),
        drain_radius=float(benchmark["drain_radius"]),
        marble_radius=float(benchmark["marble_radius"]),
        surface_max_radius=float(benchmark["surface_max_radius"]),
    )
    marble_radius = float(benchmark["marble_radius"])
    rings, spokes, drain = _bowl_lines(surface, camera)
    font = pygame.font.SysFont("consolas,dejavusansmono,monospace", 20)
    small = pygame.font.SysFont("consolas,dejavusansmono,monospace", 16)

    os.makedirs(out_dir, exist_ok=True)
    canvas = pygame.Surface((WIDTH, HEIGHT))
    trails: dict[int, list[tuple[float, float]]] = {}

    frames = run.frames[:frame_limit] if frame_limit else run.frames
    for number, frame in enumerate(frames):
        canvas.fill(BACKGROUND)
        for points, colour in rings:
            pygame.draw.lines(canvas, colour, False, points, 1)
        for points in spokes:
            pygame.draw.lines(canvas, BOWL_LINE, False, points, 1)
        pygame.draw.lines(canvas, DRAIN_LINE, True, drain, 2)

        # Painter's algorithm: far marbles first, so a near one occludes it.
        order = sorted(
            (marble for marble in frame.marbles if marble.state not in (STATE_DRAINED, STATE_ESCAPED)),
            key=lambda marble: -camera.project(marble.position)[2],
        )
        for marble in frame.marbles:
            if marble.state in (STATE_DRAINED, STATE_ESCAPED):
                trails.pop(marble.marble_id, None)
                continue
            trail = trails.setdefault(marble.marble_id, [])
            trail.append(camera.project(marble.position)[:2])
            if len(trail) > TRAIL_SAMPLES:
                del trail[0]

        for marble_id, trail in trails.items():
            if len(trail) < 2:
                continue
            colour = MARBLE_COLOURS[marble_id % len(MARBLE_COLOURS)]
            faded = tuple(int(value * 0.42 + BACKGROUND[i] * 0.58) for i, value in enumerate(colour))
            pygame.draw.lines(canvas, faded, False, [(int(x), int(y)) for x, y in trail], 2)

        for marble in order:
            _draw_marble(
                pygame,
                canvas,
                camera,
                MARBLE_COLOURS[marble.marble_id % len(MARBLE_COLOURS)],
                marble.position,
                marble.orientation,
                marble_radius,
            )

        left = sum(
            1 for marble in frame.marbles if marble.state not in (STATE_DRAINED, STATE_ESCAPED)
        )
        canvas.blit(font.render(label or run.approach, True, TEXT), (24, 20))
        canvas.blit(
            small.render(f"seed {run.seed}   t {frame.time:6.2f}s   in bowl {left}", True, LABEL),
            (24, 48),
        )
        pygame.image.save(canvas, os.path.join(out_dir, f"frame_{number:05d}.png"))

    pygame.quit()
    return len(frames)


def render_pair(
    left_run: LabRun,
    right_run: LabRun,
    out_dir: str,
    left_label: str,
    right_label: str,
    camera: Camera | None = None,
) -> int:
    """Two runs side by side on one clock, for the comparison video.

    Both halves are advanced by output frame index rather than by each run's
    own length, so the two are always showing the same instant. The shorter
    run holds its last frame rather than looping or going black - an empty
    bowl next to a full one is the finding, and cutting away from it would
    hide the single most legible difference between the two approaches.
    """
    import pygame

    scratch_left = os.path.join(out_dir, "_left")
    scratch_right = os.path.join(out_dir, "_right")
    count_left = render_run(left_run, scratch_left, camera, left_label)
    count_right = render_run(right_run, scratch_right, camera, right_label)
    total = max(count_left, count_right)

    pygame.init()
    combined = pygame.Surface((WIDTH * 2, HEIGHT))
    os.makedirs(out_dir, exist_ok=True)
    for number in range(total):
        left = pygame.image.load(
            os.path.join(scratch_left, f"frame_{min(number, count_left - 1):05d}.png")
        )
        right = pygame.image.load(
            os.path.join(scratch_right, f"frame_{min(number, count_right - 1):05d}.png")
        )
        combined.blit(left, (0, 0))
        combined.blit(right, (WIDTH, 0))
        pygame.draw.line(combined, BOWL_RIM, (WIDTH, 0), (WIDTH, HEIGHT), 2)
        pygame.image.save(combined, os.path.join(out_dir, f"frame_{number:05d}.png"))
    pygame.quit()
    return total

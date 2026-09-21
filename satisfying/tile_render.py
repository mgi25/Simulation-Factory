"""9:16 stills of a run, for one question: can you read it on a phone?

Pillow, not Godot. The repository's Godot pipeline exists and is the right tool
for a film, but a Phase 1 prototype needs three stills to answer "is a dark
tile obviously dark and a lit tile obviously lit at 1080x1920", and a 2D arena
drawn from 48 line segments does not need a 3D renderer to answer it. Nothing
here is a production look: no bloom, no particles, no materials, no lighting.
When Phase 2 wants a film, it should build a Godot scene and ignore this
module entirely.

## What the frame is arranged to prove

The arena is centred and fills 88% of the frame width, which is as wide as it
can be without the corner tiles touching the edge. A 16-gon is nearly circular,
so in a 9:16 frame it occupies a square in the middle and leaves roughly a
quarter of the height empty above and below. That is not wasted space, it is
where the hook line and the count go, and it is the reason a round arena suits
vertical video at all.

Three colours carry all the information:

- the wall of an untouched tile, dark and desaturated;
- the wall of an activated tile, bright amber, with a wider low-alpha pass
  under it so it reads as lit rather than merely repainted;
- the ball, white, with a faint halo and a short trail so a still frame still
  shows which way it is going.

The trail is the only thing here that is about feel rather than information,
and it is in because a still without it cannot show motion at all, which makes
"is the ball readable" unanswerable from a capture.

## Cosmetic versus physical

`TILE_GAP_FRACTION` shortens each drawn segment at both ends so the boundary
between two tiles on the same side is visible. The physics uses the full
segment: a ball landing in the drawn gap activates the tile it geometrically
hit. The gap is a drawing choice and is the one place in Category 3 where what
is drawn is not exactly what is simulated, which is why it is a named constant
in the renderer and not a field on the config.
"""

from __future__ import annotations

import os
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from satisfying.tile_escape import TileEscapeRun

__all__ = [
    "render_frame",
    "write_evidence_stills",
    "FRAME_WIDTH",
    "FRAME_HEIGHT",
]

FRAME_WIDTH = 1080
FRAME_HEIGHT = 1920

BACKGROUND = (8, 9, 14)
FLOOR_FILL = (16, 18, 26)
TILE_INACTIVE = (46, 52, 68)
TILE_ACTIVE = (255, 176, 66)
TILE_ACTIVE_GLOW = (255, 138, 30, 70)
BALL = (255, 255, 255)
BALL_HALO = (150, 205, 255, 90)
TRAIL = (120, 190, 255)
TEXT_PRIMARY = (236, 240, 248)
TEXT_DIM = (120, 130, 150)

ARENA_WIDTH_FRACTION = 0.88
TILE_GAP_FRACTION = 0.07
TILE_THICKNESS_UNITS = 0.34
TRAIL_SECONDS = 0.45
TRAIL_SAMPLES = 34


def _font(size: int) -> Any:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow older than 10.1 has no sized default font.
        return ImageFont.load_default()


def _count_colour(count: int, total: int) -> tuple[int, int, int]:
    """Amber once the arena is complete, plain otherwise. One bit of feedback."""
    return TILE_ACTIVE if count >= total else TEXT_PRIMARY


def _centred_text(
    draw: ImageDraw.ImageDraw,
    y: int,
    text: str,
    size: int,
    colour: tuple[int, int, int],
    width: int,
) -> None:
    font = _font(size)
    box = draw.textbbox((0, 0), text, font=font)
    draw.text(((width - (box[2] - box[0])) / 2 - box[0], y), text, font=font, fill=colour)


def render_frame(
    run: TileEscapeRun,
    t: float,
    width: int = FRAME_WIDTH,
    height: int = FRAME_HEIGHT,
    hook: str = "HIT EVERY TILE TO ESCAPE",
    debug: bool = True,
) -> Image.Image:
    """Draw the arena, the ball and the activation state at simulation time `t`."""
    arena = run.arena
    scale = (width * ARENA_WIDTH_FRACTION * 0.5) / arena.circumradius
    cx, cy = width * 0.5, height * 0.5

    def to_px(point: tuple[float, float]) -> tuple[float, float]:
        return (cx + point[0] * scale, cy - point[1] * scale)

    frame = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(frame)
    draw.polygon([to_px(v) for v in arena.vertices], fill=FLOOR_FILL)

    thickness = max(3, int(round(TILE_THICKNESS_UNITS * scale)))
    activated = run.activated_at(t)

    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)

    for tile in arena.tiles:
        ax, ay = tile.start
        bx, by = tile.end
        gap = TILE_GAP_FRACTION
        a = to_px((ax + (bx - ax) * gap, ay + (by - ay) * gap))
        b = to_px((ax + (bx - ax) * (1.0 - gap), ay + (by - ay) * (1.0 - gap)))
        if tile.tile_id in activated:
            glow_draw.line([a, b], fill=TILE_ACTIVE_GLOW, width=thickness * 3)
            glow_draw.line([a, b], fill=TILE_ACTIVE + (255,), width=thickness)
        else:
            glow_draw.line([a, b], fill=TILE_INACTIVE + (255,), width=thickness)

    ball_px = max(4.0, run.config.ball_radius * scale)
    for i in range(TRAIL_SAMPLES, 0, -1):
        age = (i / TRAIL_SAMPLES) * TRAIL_SECONDS
        if t - age < 0.0:
            continue
        fade = 1.0 - i / TRAIL_SAMPLES
        px, py = to_px(run.position_at(t - age))
        radius = ball_px * (0.28 + 0.55 * fade)
        glow_draw.ellipse(
            [px - radius, py - radius, px + radius, py + radius],
            fill=TRAIL + (int(90 * fade * fade),),
        )

    bx, by = to_px(run.position_at(t))
    halo = ball_px * 2.3
    glow_draw.ellipse([bx - halo, by - halo, bx + halo, by + halo], fill=BALL_HALO)
    glow_draw.ellipse(
        [bx - ball_px, by - ball_px, bx + ball_px, by + ball_px], fill=BALL + (255,)
    )

    frame = Image.alpha_composite(frame.convert("RGBA"), glow).convert("RGB")
    draw = ImageDraw.Draw(frame)

    if hook:
        _centred_text(draw, int(height * 0.085), hook, 62, TEXT_PRIMARY, width)
    count = run.activated_count_at(t)
    _centred_text(
        draw,
        int(height * 0.845),
        f"{count} / {run.total_tiles}",
        112,
        _count_colour(count, run.total_tiles),
        width,
    )
    if debug:
        _centred_text(
            draw,
            int(height * 0.915),
            f"seed {run.seed}   t={t:0.2f}s   {len(run.collisions)} collisions",
            38,
            TEXT_DIM,
            width,
        )
    return frame


def write_evidence_stills(
    run: TileEscapeRun,
    directory: str,
    prefix: str | None = None,
    width: int = FRAME_WIDTH,
    height: int = FRAME_HEIGHT,
) -> dict[str, str]:
    """Write the three Phase 1 captures: start, mid-progress, late.

    The three instants are picked from the run rather than from the clock, so
    they mean the same thing for a fast seed and a slow one:

    - **start** - just after release, at most one tile lit;
    - **mid** - the moment the half-way tile lit;
    - **late** - the moment the fourth-from-last tile lit, so a handful of dark
      tiles remain and the frame shows the state a viewer would be counting
      down from. For a run that never completed it is the end of the run, which
      is the best late state available.
    """
    os.makedirs(directory, exist_ok=True)
    prefix = prefix if prefix is not None else f"seed{run.seed:04d}"

    half = run.time_of_nth_activation(max(1, run.total_tiles // 2))
    late = run.time_of_nth_activation(run.total_tiles - 3)
    instants = {
        "a_start": min(0.35, run.end_time),
        "b_mid": half if half is not None else run.end_time * 0.5,
        "c_late": late if late is not None else run.end_time,
    }
    written: dict[str, str] = {}
    for name, t in instants.items():
        path = os.path.join(directory, f"{prefix}_{name}.png")
        render_frame(run, t, width=width, height=height).save(path)
        written[name] = path
    if run.completed:
        path = os.path.join(directory, f"{prefix}_d_complete.png")
        render_frame(run, run.end_time, width=width, height=height).save(path)
        written["d_complete"] = path
    return written

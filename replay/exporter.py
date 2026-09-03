"""Deterministic replay export.

The bridge between the authoritative Python simulation and any renderer.
A replay holds plain JSON-compatible data only: no timestamps, no paths and
no pickled objects, so the same seed always exports the same file.
"""

from __future__ import annotations

import json
import os
from typing import Any, Iterable

from engine.arena import CANVAS_HEIGHT, CANVAS_WIDTH
from engine.simulation import PHYSICS_HZ, Simulation
from modes.power_battle import BATTLE_DURATION_SECONDS, PowerBattleMode
from powers import PowerSpec

# v2 adds power metadata plus per-frame radius and power state. Radius is no
# longer static metadata: Titan makes it change during a battle, so the
# per-frame value is the authoritative one for renderers.
REPLAY_VERSION = 2
REPLAY_FPS = 60
TICKS_PER_FRAME = PHYSICS_HZ // REPLAY_FPS

# Enough precision for pixel-accurate playback without bloating the file.
DECIMALS = 3


def _frame(sim: Simulation) -> dict[str, Any]:
    return {
        "tick": sim.ticks,
        "fighters": [
            {
                "id": ball.ball_id,
                "x": round(ball.position.x, DECIMALS),
                "y": round(ball.position.y, DECIMALS),
                "health": round(ball.health, DECIMALS),
                "alive": ball.alive,
                "radius": round(ball.radius, DECIMALS),
                "power_active": ball.power_active,
                "power_cooldown_remaining": round(
                    0.0 if ball.power is None else ball.power.cooldown_remaining,
                    DECIMALS,
                ),
            }
            for ball in sim.balls
        ],
    }


def record_battle(
    seed: int, powers: Iterable[PowerSpec] | None = None
) -> dict[str, Any]:
    """Run one battle headlessly and capture it as replay data.

    Visual state is sampled every `TICKS_PER_FRAME` physics ticks, which is
    60 frames per simulated second at the 120 Hz physics rate. `powers` pins
    the matchup; left out, it is drawn from the seed.
    """
    sim = Simulation(seed)
    mode = PowerBattleMode(sim, powers=powers)

    frames = [_frame(sim)]
    while not mode.finished:
        for _ in range(TICKS_PER_FRAME):
            if not mode.step():
                break
        frames.append(_frame(sim))

    return {
        "version": REPLAY_VERSION,
        "seed": seed,
        "fps": REPLAY_FPS,
        "physics_hz": PHYSICS_HZ,
        "ticks_per_frame": TICKS_PER_FRAME,
        "limit_seconds": BATTLE_DURATION_SECONDS,
        "canvas": {"width": CANVAS_WIDTH, "height": CANVAS_HEIGHT},
        "arena": {
            "left": sim.arena.left,
            "top": sim.arena.top,
            "right": sim.arena.right,
            "bottom": sim.arena.bottom,
        },
        "fighters": [
            {
                "id": ball.ball_id,
                "name": ball.name,
                "color": list(ball.color),
                "radius": round(ball.base_radius, DECIMALS),
                "max_health": ball.max_health,
                "power": ball.power_name,
            }
            for ball in sim.balls
        ],
        "frames": frames,
        "result": {
            "winner_id": None if mode.winner is None else mode.winner.ball_id,
            "is_draw": mode.is_draw,
            "finished_tick": mode.finished_tick,
            "duration": round(mode.duration, DECIMALS),
        },
    }


def write_replay(replay: dict[str, Any], path: str) -> str:
    """Write replay data to `path`, creating parent directories as needed."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(replay, handle, separators=(",", ":"))
    return path

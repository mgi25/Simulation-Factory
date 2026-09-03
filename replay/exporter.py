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
from modes.events import BattleEvent
from modes.power_battle import BATTLE_DURATION_SECONDS, PowerBattleMode
from powers import PowerSpec

# v2 added power metadata plus per-frame radius and power state: Titan makes
# radius change during a battle, so the per-frame value is the authoritative
# one for renderers.
# v3 adds a per-frame `entities` list for temporary objects that come and go.
# It is deliberately generic - id, type, owner, position, radius, colour - so
# later powers reuse the same collection instead of adding their own fields.
# v4 adds a top-level `events` list: the discrete moments a renderer needs in
# order to show that something happened. It sits beside `frames` rather than
# inside them because physics runs at 120 Hz and frames are sampled at 60, so
# a per-frame home would round every event to the nearest sample.
REPLAY_VERSION = 4
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
        "entities": [
            {
                "id": entity.entity_id,
                "type": entity.kind,
                "owner_id": entity.owner_id,
                "x": round(entity.position.x, DECIMALS),
                "y": round(entity.position.y, DECIMALS),
                "radius": round(entity.radius, DECIMALS),
                "color": list(entity.color),
            }
            for entity in sim.dynamic_entities
            if entity.active
        ],
    }


def _event(event: BattleEvent) -> dict[str, Any]:
    """One battle event as plain JSON.

    Every event carries the same keys, absent values included as null, so a
    renderer reads one shape rather than probing for optional fields.
    """
    return {
        "tick": event.tick,
        "type": event.type,
        "x": round(event.x, DECIMALS),
        "y": round(event.y, DECIMALS),
        "source_id": event.source_id,
        "target_id": event.target_id,
        "subtype": event.subtype,
        "magnitude": (
            None if event.magnitude is None else round(event.magnitude, DECIMALS)
        ),
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
        # Recorded in the order the battle produced them, which is already
        # tick order: a lethal hit is therefore immediately followed by its
        # elimination, and nothing has to be sorted afterwards.
        "events": [_event(event) for event in mode.events],
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

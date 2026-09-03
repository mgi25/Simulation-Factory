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
from engine.arena_layout import LAYOUT_CLASSIC, ArenaLayout, ObstacleSpec
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
# v5 adds a top-level `layout`: the static obstacles standing in the arena.
# It is exported as real geometry rather than as the seed that produced it,
# so a renderer rebuilds the exact battle environment without knowing - or
# being able to disagree with - the generator that made it. Static by
# definition, so it appears once and never inside a frame.
REPLAY_VERSION = 5
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


def _obstacle(spec: ObstacleSpec) -> dict[str, Any]:
    """One static obstacle as plain JSON.

    Every obstacle carries the same keys whichever primitive it is, with the
    fields that primitive does not use left at zero, so a renderer switches
    on `type` and reads one flat shape rather than probing for fields.
    """
    return {
        "id": spec.obstacle_id,
        "type": spec.kind,
        "x": round(spec.x, DECIMALS),
        "y": round(spec.y, DECIMALS),
        "radius": round(spec.radius, DECIMALS),
        "width": round(spec.width, DECIMALS),
        "height": round(spec.height, DECIMALS),
        "rotation_degrees": round(spec.rotation_degrees, DECIMALS),
    }


def _layout(layout: ArenaLayout) -> dict[str, Any]:
    """The whole static layout, including the empty classic one.

    A classic arena still exports a layout section, with no obstacles in it,
    so a renderer has exactly one code path for arena geometry.
    """
    return {
        "id": layout.layout_id,
        "type": layout.layout_type,
        "requested_obstacles": layout.requested_obstacles,
        "fallback": layout.fallback,
        "obstacles": [_obstacle(spec) for spec in layout.obstacles],
    }


def record_battle(
    seed: int,
    powers: Iterable[PowerSpec] | None = None,
    arena_mode: str = LAYOUT_CLASSIC,
    arena_layout: ArenaLayout | None = None,
) -> dict[str, Any]:
    """Run one battle headlessly and capture it as replay data.

    Visual state is sampled every `TICKS_PER_FRAME` physics ticks, which is
    60 frames per simulated second at the 120 Hz physics rate. `powers` pins
    the matchup; left out, it is drawn from the seed. `arena_mode` picks the
    empty classic arena or a generated one, and `arena_layout` pins exact
    geometry the same way `powers` pins the matchup.
    """
    sim = Simulation(seed, arena_mode=arena_mode, arena_layout=arena_layout)
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
        # Static for the whole battle, so it is exported once here and never
        # repeated inside a frame.
        "layout": _layout(sim.layout),
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

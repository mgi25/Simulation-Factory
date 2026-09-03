"""Seeded generation of starting conditions.

Every random value used by a simulation comes from the RNG created here, so a
seed fully determines the starting scenario for a given code version.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from engine.arena import Arena

BALL_RADIUS_MIN = 50.0
BALL_RADIUS_MAX = 65.0

SPEED_MIN = 850.0
SPEED_MAX = 1150.0

# Keep spawns away from the walls and from each other so nothing starts
# overlapping or immediately resolving a penetration.
SPAWN_WALL_PADDING = 20.0
SPAWN_BALL_GAP = 60.0

# Reject launch angles too close to a multiple of 90 degrees, which would
# otherwise produce a permanent straight-line ping-pong.
MIN_AXIS_ANGLE = math.radians(15.0)

MAX_SPAWN_ATTEMPTS = 500

# Programmatically defined, clearly distinguishable ball colours.
BALL_COLORS: tuple[tuple[int, int, int], ...] = (
    (235, 72, 72),
    (64, 156, 248),
    (96, 214, 128),
    (246, 196, 64),
)
BALL_NAMES: tuple[str, ...] = ("RED", "BLUE", "GREEN", "GOLD")

SEED_MAX = 2**32


@dataclass(frozen=True)
class BallSpawn:
    """Fully resolved starting state of a single ball."""

    ball_id: int
    name: str
    x: float
    y: float
    vx: float
    vy: float
    radius: float
    color: tuple[int, int, int]


def generate_seed() -> int:
    """Pick a fresh seed from the OS entropy source (never the global RNG)."""
    return random.SystemRandom().randrange(SEED_MAX)


def make_rng(seed: int) -> random.Random:
    return random.Random(seed)


def _launch_angle(rng: random.Random) -> float:
    """Random direction, biased away from purely axis-aligned motion."""
    for _ in range(MAX_SPAWN_ATTEMPTS):
        angle = rng.uniform(0.0, 2.0 * math.pi)
        offset = angle % (math.pi / 2.0)
        if MIN_AXIS_ANGLE <= offset <= (math.pi / 2.0) - MIN_AXIS_ANGLE:
            return angle
    raise RuntimeError("could not pick a launch angle")


def generate_ball_spawns(
    rng: random.Random, arena: Arena, count: int = 2
) -> list[BallSpawn]:
    """Generate `count` non-overlapping ball spawns inside `arena`."""
    spawns: list[BallSpawn] = []

    for index in range(count):
        radius = rng.uniform(BALL_RADIUS_MIN, BALL_RADIUS_MAX)
        limit = radius + SPAWN_WALL_PADDING
        x, y = _pick_free_position(rng, arena, limit, radius, spawns)

        angle = _launch_angle(rng)
        speed = rng.uniform(SPEED_MIN, SPEED_MAX)

        spawns.append(
            BallSpawn(
                ball_id=index,
                name=BALL_NAMES[index % len(BALL_NAMES)],
                x=x,
                y=y,
                vx=math.cos(angle) * speed,
                vy=math.sin(angle) * speed,
                radius=radius,
                color=BALL_COLORS[index % len(BALL_COLORS)],
            )
        )

    return spawns


def _pick_free_position(
    rng: random.Random,
    arena: Arena,
    limit: float,
    radius: float,
    placed: list[BallSpawn],
) -> tuple[float, float]:
    """Rejection-sample a position clear of the walls and of placed balls."""
    for _ in range(MAX_SPAWN_ATTEMPTS):
        x = rng.uniform(arena.left + limit, arena.right - limit)
        y = rng.uniform(arena.top + limit, arena.bottom - limit)
        if all(
            math.dist((x, y), (other.x, other.y))
            >= radius + other.radius + SPAWN_BALL_GAP
            for other in placed
        ):
            return x, y
    raise RuntimeError("could not find a free spawn position in the arena")

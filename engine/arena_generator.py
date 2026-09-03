"""Seeded generation of procedural arena layouts.

Draws a small, restrained set of static obstacles from a dedicated RNG stream
and rejects any placement that would make the arena unfair or unplayable. The
generator produces plain `ArenaLayout` data and knows nothing about Pymunk,
replays or rendering.

Every clearance below is measured against the *largest* a fighter ever gets,
not the radius it happens to start with: a Titan grows mid-battle, and a gap
that only a normal ball fits through is a slot it can wedge into rather than
a lane it can use.
"""

from __future__ import annotations

import random
from dataclasses import replace
from typing import Sequence

from engine.arena import Arena
from engine.arena_layout import (
    LAYOUT_CLASSIC,
    LAYOUT_PROCEDURAL,
    LAYOUT_TYPES,
    ArenaLayout,
    ObstacleSpec,
    layout_id_for,
)
from engine.randomizer import BALL_RADIUS_MAX, BallSpawn, make_arena_rng

# The most a power may ever scale a fighter's radius by. Stated here as a
# physical bound on the arena rather than imported from `powers`, which would
# make the engine depend on the game rules layered on top of it - Titan is
# currently the only power that grows anything, and a test keeps it honest.
MAX_FIGHTER_RADIUS_SCALE = 1.50

# The biggest a fighter can ever be: the largest spawn radius, grown.
# Currently 65.0 * 1.50 = 97.5 logical pixels.
MAX_FIGHTER_RADIUS = BALL_RADIUS_MAX * MAX_FIGHTER_RADIUS_SCALE

# Every gap in the arena - obstacle to wall, obstacle to obstacle - has to be
# a lane a fully grown Titan can drive through, with room to spare. Anything
# narrower is a pocket something can get wedged in.
MIN_PASSAGE_WIDTH = 2.0 * MAX_FIGHTER_RADIUS + 25.0
OBSTACLE_WALL_CLEARANCE = MIN_PASSAGE_WIDTH
OBSTACLE_PAIR_CLEARANCE = MIN_PASSAGE_WIDTH
# Free space left around a fighter's spawn *centre*, on top of the grown
# radius: a fighter never starts touching an obstacle, and one that turns
# Titan on the first legal tick still has room around where it began.
OBSTACLE_SPAWN_CLEARANCE = 40.0

# Restrained by design, and bounded by geometry: with a Titan-wide lane
# required around everything, a 960x1160 arena holds two or three pieces.
# Four is not a tuning choice - measured over thousands of seeds it almost
# never fits, so asking for it would only manufacture fallbacks.
OBSTACLE_COUNT_CHOICES: tuple[int, ...] = (2, 2, 3, 3)

# Fraction of candidates that are bumpers rather than bars.
CIRCLE_SHARE = 0.5

# Big enough to matter, small enough never to dominate the arena.
BUMPER_RADIUS_MIN = 55.0
BUMPER_RADIUS_MAX = 90.0

# Clearly obstacle-like, never wall-like.
BAR_LONG_MIN = 150.0
BAR_LONG_MAX = 280.0
BAR_SHORT_MIN = 35.0
BAR_SHORT_MAX = 55.0

# A small discrete set, so bars read as deliberate arena furniture rather
# than as arbitrary visual noise.
BAR_ROTATIONS: tuple[float, ...] = (0.0, 45.0, 90.0, 135.0)

# Hard deterministic ceilings on rejection sampling: candidates per obstacle,
# and whole layouts before the best one found is accepted. A difficult seed
# costs a bounded amount of work - at most 3 x 400 x 24 candidates - and then
# yields a smaller layout. Nothing here can spin.
#
# The outer retry exists because the obstacles are placed in sequence: an
# unlucky first piece can leave nowhere legal for the second, and starting
# the whole layout over is what turns that from a fallback into a retry. It
# takes the measured fallback rate from roughly one layout in three to
# roughly one in fifteen hundred.
MAX_PLACEMENT_ATTEMPTS = 400
MAX_LAYOUT_ATTEMPTS = 24

# Generated values are rounded to the replay's own precision, so the layout
# Python simulates and the layout a renderer reads back are the same numbers
# rather than two roundings of one.
DECIMALS = 3


def generate_layout(
    seed: int,
    arena: Arena,
    spawns: Sequence[BallSpawn],
    rng: random.Random | None = None,
) -> ArenaLayout:
    """Build a procedural layout for `seed` that avoids `spawns`.

    The RNG defaults to the dedicated arena stream, so how many candidates
    this rejects can never disturb fighter spawns or power assignment. Tests
    pass their own to drive a specific sequence.
    """
    rng = make_arena_rng(seed) if rng is None else rng
    requested = rng.choice(OBSTACLE_COUNT_CHOICES)

    best: tuple[ObstacleSpec, ...] = ()
    for _ in range(MAX_LAYOUT_ATTEMPTS):
        placed = _place_all(rng, arena, spawns, requested)
        if len(placed) > len(best):
            best = placed
        if len(best) == requested:
            break

    # Whatever survived is a valid layout; it just may hold fewer obstacles
    # than were asked for, and `ArenaLayout.fallback` says so rather than the
    # layout quietly claiming to be something it is not.
    return ArenaLayout(
        layout_id=layout_id_for(LAYOUT_PROCEDURAL, seed),
        layout_type=LAYOUT_PROCEDURAL,
        obstacles=best,
        requested_obstacles=requested,
    )


def _place_all(
    rng: random.Random, arena: Arena, spawns: Sequence[BallSpawn], count: int
) -> tuple[ObstacleSpec, ...]:
    """One full pass: place `count` obstacles in sequence, keeping what fits."""
    placed: list[ObstacleSpec] = []
    for _ in range(count):
        candidate = _place_one(rng, arena, spawns, placed, len(placed))
        if candidate is not None:
            placed.append(candidate)
    return tuple(placed)


def _place_one(
    rng: random.Random,
    arena: Arena,
    spawns: Sequence[BallSpawn],
    placed: Sequence[ObstacleSpec],
    obstacle_id: int,
) -> ObstacleSpec | None:
    """Rejection-sample one obstacle. Returns None once the budget runs out."""
    for _ in range(MAX_PLACEMENT_ATTEMPTS):
        candidate = _candidate(rng, arena, obstacle_id)
        if candidate is not None and is_placement_valid(
            candidate, arena, spawns, placed
        ):
            return candidate
    return None


def _candidate(
    rng: random.Random, arena: Arena, obstacle_id: int
) -> ObstacleSpec | None:
    """Draw one candidate whose centre already respects the wall clearance.

    Sizes are drawn first and the centre is then drawn inside the band that
    keeps the whole shape clear of the walls, so the wall constraint is
    satisfied by construction instead of by rejection. Only the spawn and
    obstacle-pair constraints can actually reject a candidate.
    """
    if rng.random() < CIRCLE_SHARE:
        radius = _round(rng.uniform(BUMPER_RADIUS_MIN, BUMPER_RADIUS_MAX))
        # A bumper is drawn at the origin and moved, so one code path below
        # positions both primitives.
        probe = ObstacleSpec.circle(obstacle_id, 0.0, 0.0, radius)
    else:
        long_side = _round(rng.uniform(BAR_LONG_MIN, BAR_LONG_MAX))
        short_side = _round(rng.uniform(BAR_SHORT_MIN, BAR_SHORT_MAX))
        rotation = rng.choice(BAR_ROTATIONS)
        probe = ObstacleSpec.box(
            obstacle_id, 0.0, 0.0, long_side, short_side, rotation
        )

    # The probe's own bounding box gives the rotated extent the placement
    # band has to account for.
    left, top, right, bottom = probe.bounds()
    span_x = _band(arena.left, arena.right, (right - left) / 2.0)
    span_y = _band(arena.top, arena.bottom, (bottom - top) / 2.0)
    if span_x is None or span_y is None:
        return None

    return replace(
        probe,
        x=_round(rng.uniform(*span_x)),
        y=_round(rng.uniform(*span_y)),
    )


def _band(low: float, high: float, half_extent: float) -> tuple[float, float] | None:
    """Centres on one axis that keep a shape clear of both walls."""
    margin = half_extent + OBSTACLE_WALL_CLEARANCE
    if high - low <= 2.0 * margin:
        return None
    return (low + margin, high - margin)


def is_placement_valid(
    candidate: ObstacleSpec,
    arena: Arena,
    spawns: Sequence[BallSpawn],
    placed: Sequence[ObstacleSpec],
) -> bool:
    """Every constraint a generated obstacle has to satisfy, in one place.

    Also the predicate the geometry tests check finished layouts against, so
    the rules the generator applies and the rules a layout is judged by
    cannot drift apart.
    """
    if candidate.clearance_to_bounds(arena) < OBSTACLE_WALL_CLEARANCE:
        return False
    for spawn in spawns:
        # Measured from the spawn centre against the grown radius, not
        # against the radius this fighter happens to have started with.
        if (
            candidate.distance_to_point(spawn.x, spawn.y)
            < MAX_FIGHTER_RADIUS + OBSTACLE_SPAWN_CLEARANCE
        ):
            return False
    return all(
        candidate.clearance_to(other) >= OBSTACLE_PAIR_CLEARANCE for other in placed
    )


def layout_for_mode(
    mode: str, seed: int, arena: Arena, spawns: Sequence[BallSpawn]
) -> ArenaLayout:
    """Resolve an arena-mode name into a layout. The only place that maps one."""
    if mode == LAYOUT_CLASSIC:
        return ArenaLayout.classic()
    if mode == LAYOUT_PROCEDURAL:
        return generate_layout(seed, arena, spawns)
    raise ValueError(
        f"unknown arena mode {mode!r}; known modes: {', '.join(LAYOUT_TYPES)}"
    )


def is_layout_valid(
    layout: ArenaLayout, arena: Arena, spawns: Sequence[BallSpawn]
) -> bool:
    """True when every obstacle in `layout` satisfies every constraint."""
    for index, obstacle in enumerate(layout.obstacles):
        if not is_placement_valid(obstacle, arena, spawns, layout.obstacles[:index]):
            return False
    return True


def _round(value: float) -> float:
    return round(value, DECIMALS)

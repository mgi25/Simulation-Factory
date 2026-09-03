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
    AXIS_X,
    AXIS_Y,
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

# Between two obstacles where at least one moves, the gap is measured
# between everywhere each of them ever reaches - which is the closest the
# two *regions* come, at the worst pair of poses, whether or not those poses
# ever coincide. Demanding a full Titan lane there would be a much stronger
# claim than the static rule above makes, and it prices most kinetic layouts
# out of a 960x1160 arena. A full-size ungrown fighter fits instead, so the
# sweeps stay comfortably apart and the scene stays readable.
KINETIC_PAIR_CLEARANCE = 2.0 * BALL_RADIUS_MAX + 20.0
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

# How many of a layout's obstacles move, by obstacle count. Never all of
# them: an arena with nothing standing still stops reading as a place and
# starts reading as a machine. Never three, either - that is next phase's
# question, not this one's.
KINETIC_CHOICES: dict[int, tuple[int, ...]] = {
    2: (0, 0, 1, 1, 1),
    3: (0, 0, 1, 1, 1, 2, 2),
}

# A rotor sweeps the circle of its own diagonal, and it is that circle - not
# the bar - that has to fit with a Titan-wide lane around it. So a rotor is
# shorter than a static bar: a 280 px one would need a 143 px envelope radius
# and could only ever sit dead centre.
ROTOR_LONG_MIN = 150.0
ROTOR_LONG_MAX = 220.0
ROTOR_SHORT_MIN = 35.0
ROTOR_SHORT_MAX = 50.0
# Degrees per simulated second. Slow enough to read as machinery and to be
# dodged on sight; the sign is drawn separately and is the direction.
ROTOR_SPEEDS: tuple[float, ...] = (45.0, 60.0, 75.0, 90.0)

# A gate slides across its own width, never along its length: sweeping
# lengthways would drag a square envelope through the arena, while this keeps
# it a slim lane and reads as a door rather than a piston.
GATE_LONG_MIN = 150.0
GATE_LONG_MAX = 260.0
GATE_SHORT_MIN = 35.0
GATE_SHORT_MAX = 55.0
GATE_TRAVEL_MIN = 180.0
GATE_TRAVEL_MAX = 350.0
GATE_SPEEDS: tuple[float, ...] = (160.0, 200.0, 240.0, 280.0, 320.0)
# Lying flat and sliding down the arena, or standing up and sliding across.
GATE_ORIENTATIONS: tuple[tuple[float, str], ...] = ((0.0, AXIS_Y), (90.0, AXIS_X))

# What a single obstacle slot can be asked to produce.
PLAN_CIRCLE = "circle"
PLAN_BAR = "bar"
PLAN_ROTOR = "rotor"
PLAN_GATE = "gate"
KINETIC_PLANS: tuple[str, ...] = (PLAN_ROTOR, PLAN_GATE)

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
# The placement budget, split into shapes drawn and anchors tried per shape.
# Their product is the budget above.
SHAPE_ATTEMPTS = 20
ANCHOR_ATTEMPTS = MAX_PLACEMENT_ATTEMPTS // SHAPE_ATTEMPTS

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
    plan = _plan(rng, requested)

    best: tuple[ObstacleSpec, ...] = ()
    target = (requested, 1)
    for _ in range(MAX_LAYOUT_ATTEMPTS):
        placed = _place_all(rng, arena, spawns, plan)
        if _score(placed) > _score(best):
            best = placed
        if _score(best) == target:
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


def _score(placed: Sequence[ObstacleSpec]) -> tuple[int, int]:
    """How good a placement pass turned out: obstacle count, then the mix.

    The plan never asks for an all-moving arena, but a pass that fails to
    place its one static piece would produce one anyway. Ranking a mixed
    result above an all-kinetic one of the same size makes the retry loop
    keep looking, so that only survives when nothing better fits at all.
    """
    mixed = len(placed) < 2 or any(not spec.is_kinetic for spec in placed)
    return (len(placed), int(mixed))


def _plan(rng: random.Random, count: int) -> list[str]:
    """Decide what each obstacle slot will be, kinetic slots first.

    Order matters: a rotor's or a gate's envelope is much larger than a
    bumper's, so the moving pieces get first refusal on an empty arena and
    the static ones fill in around whatever is left. Placing them the other
    way round is what makes a kinetic layout fail to fit.
    """
    kinetic = rng.choice(KINETIC_CHOICES[count]) if count in KINETIC_CHOICES else 0
    plan = [rng.choice(KINETIC_PLANS) for _ in range(kinetic)]
    plan += [
        PLAN_CIRCLE if rng.random() < CIRCLE_SHARE else PLAN_BAR
        for _ in range(count - kinetic)
    ]
    return plan


def _place_all(
    rng: random.Random, arena: Arena, spawns: Sequence[BallSpawn], plan: Sequence[str]
) -> tuple[ObstacleSpec, ...]:
    """One full pass: work down the plan, keeping every obstacle that fits."""
    placed: list[ObstacleSpec] = []
    for slot in plan:
        candidate = _place_one(rng, arena, spawns, placed, len(placed), slot)
        if candidate is not None:
            placed.append(candidate)
    return tuple(placed)


def _place_one(
    rng: random.Random,
    arena: Arena,
    spawns: Sequence[BallSpawn],
    placed: Sequence[ObstacleSpec],
    obstacle_id: int,
    slot: str,
) -> ObstacleSpec | None:
    """Rejection-sample one obstacle. Returns None once the budget runs out.

    Sizes and motion are drawn first and the anchor is then drawn inside the
    band that keeps the obstacle's whole *envelope* clear of the walls, so a
    rotor cannot sweep into a wall and a gate cannot slide into one however
    its starting pose looks. Only the spawn and obstacle-pair constraints can
    actually reject a candidate.

    One drawn shape is offered several anchors before another is drawn:
    everything derived from the shape alone - its envelope, its extent, the
    band it may sit in - then costs one calculation instead of one per
    attempt, which matters because a hard layout tries hundreds.
    """
    obstructions = [other.envelope() for other in placed]

    for _ in range(SHAPE_ATTEMPTS):
        probe = _probe(rng, obstacle_id, slot)
        envelope = probe.envelope()
        left, top, right, bottom = envelope.bounds()
        span_x = _band(arena.left, arena.right, (right - left) / 2.0)
        span_y = _band(arena.top, arena.bottom, (bottom - top) / 2.0)
        if span_x is None or span_y is None:
            continue

        for _ in range(ANCHOR_ATTEMPTS):
            x = _round(rng.uniform(*span_x))
            y = _round(rng.uniform(*span_y))
            if _is_envelope_clear(
                replace(envelope, x=x, y=y), probe, spawns, placed, obstructions
            ):
                return replace(probe, x=x, y=y)
    return None


def _probe(rng: random.Random, obstacle_id: int, slot: str) -> ObstacleSpec:
    """One candidate's size and motion, anchored at the origin."""
    if slot == PLAN_CIRCLE:
        return ObstacleSpec.circle(
            obstacle_id,
            0.0,
            0.0,
            _round(rng.uniform(BUMPER_RADIUS_MIN, BUMPER_RADIUS_MAX)),
        )

    if slot == PLAN_ROTOR:
        return ObstacleSpec.rotor(
            obstacle_id,
            0.0,
            0.0,
            _round(rng.uniform(ROTOR_LONG_MIN, ROTOR_LONG_MAX)),
            _round(rng.uniform(ROTOR_SHORT_MIN, ROTOR_SHORT_MAX)),
            angular_speed=rng.choice(ROTOR_SPEEDS) * rng.choice((-1.0, 1.0)),
            rotation_degrees=rng.choice(BAR_ROTATIONS),
        )

    if slot == PLAN_GATE:
        rotation, axis = rng.choice(GATE_ORIENTATIONS)
        return ObstacleSpec.gate(
            obstacle_id,
            0.0,
            0.0,
            _round(rng.uniform(GATE_LONG_MIN, GATE_LONG_MAX)),
            _round(rng.uniform(GATE_SHORT_MIN, GATE_SHORT_MAX)),
            axis=axis,
            distance=_round(rng.uniform(GATE_TRAVEL_MIN, GATE_TRAVEL_MAX)),
            speed=rng.choice(GATE_SPEEDS),
            phase=_round(rng.random()),
            rotation_degrees=rotation,
        )

    return ObstacleSpec.box(
        obstacle_id,
        0.0,
        0.0,
        _round(rng.uniform(BAR_LONG_MIN, BAR_LONG_MAX)),
        _round(rng.uniform(BAR_SHORT_MIN, BAR_SHORT_MAX)),
        rng.choice(BAR_ROTATIONS),
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

    Every check is made against envelopes - everywhere an obstacle reaches
    over its whole motion, not the pose it happens to start in. For a static
    obstacle the envelope is the obstacle, so this is the same rule phase
    5A1 applied; for a rotor or a gate it is what makes a starting pose that
    merely *looks* safe insufficient.

    Also the predicate the geometry tests check finished layouts against, so
    the rules the generator applies and the rules a layout is judged by
    cannot drift apart.
    """
    envelope = candidate.envelope()
    if envelope.clearance_to_bounds(arena) < OBSTACLE_WALL_CLEARANCE:
        return False
    return _is_envelope_clear(
        envelope, candidate, spawns, placed, [other.envelope() for other in placed]
    )


def _is_envelope_clear(
    envelope: ObstacleSpec,
    candidate: ObstacleSpec,
    spawns: Sequence[BallSpawn],
    placed: Sequence[ObstacleSpec],
    obstructions: Sequence[ObstacleSpec],
) -> bool:
    """The spawn and obstacle-pair half of `is_placement_valid`.

    Split out so the generator can hand in envelopes it has already built
    rather than rebuilding them for every anchor it tries. Wall clearance is
    not repeated here: the generator satisfies it by construction.
    """
    for spawn in spawns:
        # Measured from the spawn centre against the grown radius, not
        # against the radius this fighter happens to have started with.
        if (
            envelope.distance_to_point(spawn.x, spawn.y)
            < MAX_FIGHTER_RADIUS + OBSTACLE_SPAWN_CLEARANCE
        ):
            return False
    return all(
        envelope.clearance_to(other) >= pair_clearance(candidate, spec)
        for spec, other in zip(placed, obstructions)
    )


def pair_clearance(a: ObstacleSpec, b: ObstacleSpec) -> float:
    """The gap two obstacles' envelopes have to leave between them."""
    if a.is_kinetic or b.is_kinetic:
        return KINETIC_PAIR_CLEARANCE
    return OBSTACLE_PAIR_CLEARANCE


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

"""Headless simulation: seeded setup, fixed-timestep physics, contact reports.

The simulation owns the physics world and the temporary entities living in
it. It reports ball-to-ball impacts and dynamic-entity contacts as plain
data; deciding what a contact means is a game-mode concern.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

import pymunk

from engine.arena import WALL_THICKNESS, Arena
from engine.randomizer import generate_ball_spawns, make_rng
from entities.ball import COLLISION_TYPE_BALL, COLLISION_TYPE_WALL, Ball
from entities.dynamic_entity import COLLISION_TYPE_DYNAMIC_ENTITY, DynamicEntity

PHYSICS_HZ = 120
PHYSICS_DT = 1.0 / PHYSICS_HZ

# Upper bound on catch-up ticks per advance() call, so a slow frame cannot
# trigger a runaway "simulate forever to catch up" spiral.
MAX_TICKS_PER_ADVANCE = 8

WALL_ELASTICITY = 1.0
WALL_FRICTION = 0.0

BALL_COUNT = 2


@dataclass(frozen=True)
class Impact:
    """One ball-to-ball collision, reported once when contact begins.

    The two approach speeds are the components of each ball's velocity along
    the contact normal, measured before the collision is solved.
    """

    tick: int
    ball_a: Ball
    ball_b: Ball
    speed_a_into_b: float
    speed_b_into_a: float

    @property
    def closing_speed(self) -> float:
        """Relative speed along the contact normal."""
        return self.speed_a_into_b + self.speed_b_into_a


@dataclass(frozen=True)
class EntityContact:
    """A dynamic entity touching a fighter, or a wall when `ball` is None."""

    tick: int
    entity: DynamicEntity
    ball: Ball | None = None

    @property
    def is_wall(self) -> bool:
        return self.ball is None


class Simulation:
    """Owns the physics space, the entities and the simulation clock."""

    def __init__(self, seed: int, arena: Arena | None = None) -> None:
        self.seed = seed
        self.arena = arena if arena is not None else Arena.default()
        self.rng = make_rng(seed)

        self.space = pymunk.Space()
        self.space.gravity = (0.0, 0.0)

        self._build_walls()

        self.balls: list[Ball] = [
            Ball.from_spawn(spawn)
            for spawn in generate_ball_spawns(self.rng, self.arena, BALL_COUNT)
        ]
        for ball in self.balls:
            ball.add_to_space(self.space)

        self._ball_by_shape = {ball.shape: ball for ball in self.balls}
        self.impacts: list[Impact] = []
        self.space.on_collision(
            COLLISION_TYPE_BALL, COLLISION_TYPE_BALL, begin=self._on_ball_impact
        )

        # Temporary entities. Ids continue past the fighters, so 0..n-1 are
        # always fighters and everything spawned later is unique and ordered.
        self.dynamic_entities: list[DynamicEntity] = []
        self.entity_contacts: list[EntityContact] = []
        self._entity_by_shape: dict[pymunk.Shape, DynamicEntity] = {}
        self._next_entity_id = len(self.balls)
        self._pending_removal: list[DynamicEntity] = []
        self._stepping = False
        self.space.on_collision(
            COLLISION_TYPE_DYNAMIC_ENTITY, COLLISION_TYPE_BALL, begin=self._on_entity_ball
        )
        self.space.on_collision(
            COLLISION_TYPE_DYNAMIC_ENTITY, COLLISION_TYPE_WALL, begin=self._on_entity_wall
        )

        self.ticks = 0
        self.elapsed = 0.0
        self._accumulator = 0.0

    def _build_walls(self) -> None:
        """Four static segments whose inner surface sits on the arena bounds."""
        a = self.arena
        t = WALL_THICKNESS
        outer_left, outer_right = a.left - t, a.right + t
        outer_top, outer_bottom = a.top - t, a.bottom + t

        edges = (
            ((outer_left, outer_top), (outer_right, outer_top)),
            ((outer_left, outer_bottom), (outer_right, outer_bottom)),
            ((outer_left, outer_top), (outer_left, outer_bottom)),
            ((outer_right, outer_top), (outer_right, outer_bottom)),
        )

        self.walls: list[pymunk.Segment] = []
        for start, end in edges:
            wall = pymunk.Segment(self.space.static_body, start, end, t)
            wall.elasticity = WALL_ELASTICITY
            wall.friction = WALL_FRICTION
            wall.collision_type = COLLISION_TYPE_WALL
            self.space.add(wall)
            self.walls.append(wall)

    # --- dynamic entities ---

    def spawn(self, factory: Callable[..., DynamicEntity], **kwargs) -> DynamicEntity:
        """Build, register and activate a temporary entity.

        The simulation allocates the id so it stays deterministic, unique and
        monotonic; the caller supplies the class and its own arguments.
        """
        entity = factory(entity_id=self._next_entity_id, **kwargs)
        self._next_entity_id += 1

        self.dynamic_entities.append(entity)
        entity.add_to_space(self.space)
        for shape in entity.shapes:
            self._entity_by_shape[shape] = entity
        return entity

    def despawn(self, entity: DynamicEntity) -> None:
        """Retire an entity. Safe to call from inside a collision callback."""
        if not entity.active:
            return
        entity.active = False
        if self._stepping:
            # Chipmunk forbids touching the space mid-step; finish first.
            self._pending_removal.append(entity)
        else:
            self._remove_entity(entity)

    def clear_entities(self) -> None:
        for entity in list(self.dynamic_entities):
            self.despawn(entity)

    def entity(self, entity_id: int) -> DynamicEntity | None:
        for entity in self.dynamic_entities:
            if entity.entity_id == entity_id:
                return entity
        return None

    def _remove_entity(self, entity: DynamicEntity) -> None:
        entity.remove_from_space(self.space)
        for shape in entity.shapes:
            self._entity_by_shape.pop(shape, None)
        if entity in self.dynamic_entities:
            self.dynamic_entities.remove(entity)

    def _flush_removals(self) -> None:
        while self._pending_removal:
            self._remove_entity(self._pending_removal.pop())

    def _contact_pair(self, arbiter: pymunk.Arbiter) -> tuple[DynamicEntity | None, Ball | None]:
        """Resolve an arbiter into (entity, ball) regardless of shape order."""
        entity: DynamicEntity | None = None
        ball: Ball | None = None
        for shape in arbiter.shapes:
            entity = entity or self._entity_by_shape.get(shape)
            ball = ball or self._ball_by_shape.get(shape)
        return entity, ball

    def _on_entity_ball(self, arbiter: pymunk.Arbiter, space, data) -> None:
        entity, ball = self._contact_pair(arbiter)
        if entity is None or ball is None or not entity.active:
            return
        self.entity_contacts.append(EntityContact(self.ticks, entity, ball))

    def _on_entity_wall(self, arbiter: pymunk.Arbiter, space, data) -> None:
        entity, _ = self._contact_pair(arbiter)
        if entity is None or not entity.active:
            return
        self.entity_contacts.append(EntityContact(self.ticks, entity))

    # --- collision reporting ---

    def _on_ball_impact(self, arbiter: pymunk.Arbiter, space, data) -> None:
        """Collision-begin callback: one report per physical impact."""
        shape_a, shape_b = arbiter.shapes
        ball_a = self._ball_by_shape.get(shape_a)
        ball_b = self._ball_by_shape.get(shape_b)
        if ball_a is None or ball_b is None:
            return

        normal = arbiter.normal  # unit vector pointing from shape a to shape b
        self.impacts.append(
            Impact(
                tick=self.ticks,
                ball_a=ball_a,
                ball_b=ball_b,
                speed_a_into_b=max(0.0, ball_a.velocity.dot(normal)),
                speed_b_into_a=max(0.0, -ball_b.velocity.dot(normal)),
            )
        )

    def step(self) -> None:
        """Advance the physics by exactly one fixed tick."""
        self.impacts.clear()
        self.entity_contacts.clear()

        self._stepping = True
        try:
            self.space.step(PHYSICS_DT)
        finally:
            self._stepping = False
        self._flush_removals()

        self.ticks += 1
        self.elapsed += PHYSICS_DT

        # Age entities and retire the ones that ran out of lifetime. Contacts
        # recorded above are still readable by the mode: reports hold direct
        # references, so a retired entity's hit is not lost.
        for entity in list(self.dynamic_entities):
            entity.advance()
            if entity.expired:
                self.despawn(entity)

    def advance(
        self, frame_seconds: float, on_tick: Callable[[], bool | None] | None = None
    ) -> int:
        """Consume real elapsed time and run whole fixed ticks.

        Returns the number of ticks executed. Leftover time is kept in the
        accumulator, so physics never depends on the render framerate.
        `on_tick` runs after every tick and may return False to stop early.
        """
        self._accumulator += max(0.0, frame_seconds)

        ticks = 0
        stopped = False
        while self._accumulator >= PHYSICS_DT and ticks < MAX_TICKS_PER_ADVANCE:
            self.step()
            self._accumulator -= PHYSICS_DT
            ticks += 1
            if on_tick is not None and on_tick() is False:
                stopped = True
                break

        if not stopped and self._accumulator >= PHYSICS_DT:
            # Fell too far behind: drop the backlog instead of accumulating it.
            self._accumulator = 0.0

        return ticks

    def is_state_valid(self) -> bool:
        """True while every ball has finite state and is inside the arena.

        Dynamic entities are only checked for finite positions: a projectile
        legitimately reaches the arena boundary before it despawns.
        """
        for ball in self.balls:
            x, y = ball.position
            vx, vy = ball.velocity
            if not all(math.isfinite(v) for v in (x, y, vx, vy)):
                return False
            if not self.arena.contains_circle(x, y, 0.0):
                return False
        for entity in self.dynamic_entities:
            if not all(math.isfinite(v) for v in entity.position):
                return False
        return True

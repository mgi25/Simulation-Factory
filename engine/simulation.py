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
from engine.arena_generator import layout_for_mode
from engine.arena_layout import (
    COLLISION_TYPE_OBSTACLE,
    LAYOUT_CLASSIC,
    ArenaLayout,
    ObstacleSpec,
)
from engine.obstacle_runtime import ObstacleRuntime
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

# What a dynamic entity touched. A fighter is a gameplay target; the outer
# wall and a static obstacle are both arena geometry, and entities react to
# them the same way - but the report still says which, so a renderer or a
# future rule can tell them apart.
CONTACT_FIGHTER = "fighter"
CONTACT_WALL = "wall"
CONTACT_OBSTACLE = "obstacle"


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
class ObstacleContact:
    """One fighter touching one arena obstacle, reported when contact begins.

    Purely observational: no damage, no event, no effect on the solver. It
    exists so tooling outside the simulation can tell how much a battle
    actually used the arena it was given. Reported on collision *begin*, so a
    fighter resting against a bumper is one contact rather than one per tick.
    """

    tick: int
    fighter_id: int
    obstacle_id: int


@dataclass(frozen=True)
class EntityContact:
    """A dynamic entity touching a fighter, a static obstacle or the wall.

    Exactly one of `ball` and `obstacle` is set for the first two; both are
    None for the outer wall.
    """

    tick: int
    entity: DynamicEntity
    ball: Ball | None = None
    obstacle: ObstacleSpec | None = None

    @property
    def kind(self) -> str:
        if self.ball is not None:
            return CONTACT_FIGHTER
        return CONTACT_WALL if self.obstacle is None else CONTACT_OBSTACLE

    @property
    def is_wall(self) -> bool:
        return self.kind == CONTACT_WALL

    @property
    def is_obstacle(self) -> bool:
        return self.kind == CONTACT_OBSTACLE

    @property
    def is_static(self) -> bool:
        """True for arena geometry - the outer wall or a static obstacle."""
        return self.ball is None


class Simulation:
    """Owns the physics space, the entities and the simulation clock."""

    def __init__(
        self,
        seed: int,
        arena: Arena | None = None,
        arena_mode: str = LAYOUT_CLASSIC,
        arena_layout: ArenaLayout | None = None,
    ) -> None:
        self.seed = seed
        self.arena = arena if arena is not None else Arena.default()
        self.rng = make_rng(seed)

        self.space = pymunk.Space()
        self.space.gravity = (0.0, 0.0)

        self._build_walls()

        # Fighter spawns are drawn first and from their own stream, so the
        # same seed puts the same fighters in the same places whatever the
        # arena mode is: only the geometry around them changes.
        spawns = generate_ball_spawns(self.rng, self.arena, BALL_COUNT)
        self.balls: list[Ball] = [Ball.from_spawn(spawn) for spawn in spawns]
        for ball in self.balls:
            ball.add_to_space(self.space)

        # A ready-made layout wins over a mode name, which is how a test pins
        # exact geometry instead of hunting for a seed that generates it.
        self.layout = (
            arena_layout
            if arena_layout is not None
            else layout_for_mode(arena_mode, seed, self.arena, spawns)
        )
        self._build_obstacles()

        self._ball_by_shape = {ball.shape: ball for ball in self.balls}
        self._ball_by_id = {ball.ball_id: ball for ball in self.balls}
        self.impacts: list[Impact] = []
        self.obstacle_contacts: list[ObstacleContact] = []
        self.space.on_collision(
            COLLISION_TYPE_BALL, COLLISION_TYPE_BALL, begin=self._on_ball_impact
        )
        self.space.on_collision(
            COLLISION_TYPE_BALL, COLLISION_TYPE_OBSTACLE, begin=self._on_ball_obstacle
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
        self.space.on_collision(
            COLLISION_TYPE_DYNAMIC_ENTITY,
            COLLISION_TYPE_OBSTACLE,
            begin=self._on_entity_obstacle,
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

    def _build_obstacles(self) -> None:
        """Give every obstacle in the layout a body and a shape in the space."""
        self.obstacles: list[ObstacleRuntime] = [
            ObstacleRuntime(spec, self.space) for spec in self.layout.obstacles
        ]
        self.obstacle_shapes: list[pymunk.Shape] = [
            runtime.shape for runtime in self.obstacles
        ]
        self._obstacle_by_shape: dict[pymunk.Shape, ObstacleSpec] = {
            runtime.shape: runtime.spec for runtime in self.obstacles
        }
        # Only these need a tick hook, so a battle on a static arena pays
        # nothing at all for the kinetic machinery.
        self.kinetic_obstacles = [r for r in self.obstacles if r.is_kinetic]

    @property
    def arena_mode(self) -> str:
        """Which kind of arena this simulation is running: classic or generated."""
        return self.layout.layout_type

    def obstacle(self, obstacle_id: int) -> ObstacleSpec | None:
        for spec in self.layout.obstacles:
            if spec.obstacle_id == obstacle_id:
                return spec
        return None

    def obstacle_runtime(self, obstacle_id: int) -> ObstacleRuntime | None:
        for runtime in self.obstacles:
            if runtime.obstacle_id == obstacle_id:
                return runtime
        return None

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

    def fighter(self, ball_id: int) -> Ball | None:
        """Look a fighter up by id rather than by position in the list."""
        return self._ball_by_id.get(ball_id)

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

    def _on_entity_obstacle(self, arbiter: pymunk.Arbiter, space, data) -> None:
        entity, _ = self._contact_pair(arbiter)
        if entity is None or not entity.active:
            return
        obstacle = None
        for shape in arbiter.shapes:
            obstacle = obstacle or self._obstacle_by_shape.get(shape)
        self.entity_contacts.append(
            EntityContact(self.ticks, entity, obstacle=obstacle)
        )

    # --- collision reporting ---

    def _on_ball_obstacle(self, arbiter: pymunk.Arbiter, space, data) -> None:
        """Note that a fighter touched an obstacle. Changes nothing about it.

        Returning None accepts the collision exactly as the default handler
        would, so registering this callback leaves the bounce, the impulse
        and therefore the whole battle bit-for-bit unchanged.
        """
        ball: Ball | None = None
        spec: ObstacleSpec | None = None
        for shape in arbiter.shapes:
            ball = ball or self._ball_by_shape.get(shape)
            spec = spec or self._obstacle_by_shape.get(shape)
        if ball is None or spec is None:
            return
        self.obstacle_contacts.append(
            ObstacleContact(self.ticks, ball.ball_id, spec.obstacle_id)
        )

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
        self.obstacle_contacts.clear()

        # The arena moves first: a fighter resolving against a bar this tick
        # should meet the velocity the bar is about to have, not last tick's.
        for runtime in self.kinetic_obstacles:
            runtime.before_step(self.elapsed)

        # Entities that position themselves relative to something else get
        # their chance immediately before collisions are solved.
        for entity in list(self.dynamic_entities):
            if entity.active:
                entity.before_step(self)

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
        # A moving obstacle is driven, never solved, so this should never
        # trip - which is exactly why it is worth asserting.
        for runtime in self.kinetic_obstacles:
            if not runtime.is_finite():
                return False
        return True

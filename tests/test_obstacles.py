"""Phase 5A1 tests: static obstacles in Pymunk, and the v5 replay layout."""

from __future__ import annotations

import json
import math

import pymunk
import pytest

from engine.arena_layout import (
    COLLISION_TYPE_OBSTACLE,
    LAYOUT_CLASSIC,
    LAYOUT_PROCEDURAL,
    OBSTACLE_BOX,
    OBSTACLE_CIRCLE,
    OBSTACLE_ELASTICITY,
    OBSTACLE_FRICTION,
    ArenaLayout,
    ObstacleSpec,
)
from engine.simulation import (
    CONTACT_FIGHTER,
    CONTACT_OBSTACLE,
    CONTACT_WALL,
    EntityContact,
    Simulation,
)
from entities.echo_clone import EchoClone
from entities.projectile import Projectile
from modes.power_battle import POWER_WARMUP_TICKS, PowerBattleMode
from powers import EchoPower, OrbitPower, Power
from powers.power import seconds_to_ticks
from replay.exporter import REPLAY_VERSION, record_battle

SEED = 12345

# One hand-built layout, so every physics test below knows exactly what it is
# bouncing off instead of hunting for a seed that generates the right shape.
BUMPER = ObstacleSpec.circle(0, 540.0, 700.0, 80.0)
BAR = ObstacleSpec.box(1, 540.0, 1200.0, 300.0, 40.0)
DIAGONAL_BAR = ObstacleSpec.box(1, 540.0, 1200.0, 300.0, 40.0, rotation_degrees=45.0)


def inert_power() -> Power:
    """A power whose cooldown never becomes ready inside a battle."""
    return Power(initial_delay_ticks=10**9)


def pinned(*obstacles: ObstacleSpec) -> ArenaLayout:
    return ArenaLayout(
        layout_id="test-layout",
        layout_type=LAYOUT_PROCEDURAL,
        obstacles=obstacles,
        requested_obstacles=len(obstacles),
    )


def lone_fighter(*obstacles: ObstacleSpec, seed: int = SEED):
    """One powerless fighter on a pinned layout, and nothing else to hit.

    The second fighter is taken out of the space the way the wall-bounce
    tests do it, so anything that happens below is the obstacle's doing and
    no stray fighter contact can be mistaken for one.
    """
    sim = Simulation(seed, arena_layout=pinned(*obstacles))
    mode = PowerBattleMode(sim, powers=(inert_power(), inert_power()))
    for extra in sim.balls[1:]:
        sim.space.remove(extra.body, extra.shape)
    sim.balls = sim.balls[:1]
    while mode.sim.ticks < POWER_WARMUP_TICKS - 1:
        mode.step()
    return sim, mode, sim.balls[0]


def aim(ball, position: tuple[float, float], velocity: tuple[float, float]) -> None:
    ball.body.position = position
    ball.body.velocity = velocity


def run_until(mode: PowerBattleMode, predicate, limit: int = 900) -> bool:
    for _ in range(limit):
        mode.step()
        if predicate():
            return True
    return False


# --- static construction ---


def test_a_classic_simulation_builds_no_obstacles() -> None:
    sim = Simulation(SEED)
    assert sim.arena_mode == LAYOUT_CLASSIC
    assert sim.layout.obstacles == ()
    assert sim.obstacle_shapes == []
    # Only the fighters and the four walls, exactly as before this phase.
    assert len(sim.space.shapes) == len(sim.balls) + len(sim.walls)


def test_obstacles_become_static_shapes_with_the_wall_material() -> None:
    sim = Simulation(SEED, arena_layout=pinned(BUMPER, BAR))
    assert len(sim.obstacle_shapes) == 2

    circle, box = sim.obstacle_shapes
    assert isinstance(circle, pymunk.Circle)
    assert isinstance(box, pymunk.Poly)
    for shape in sim.obstacle_shapes:
        assert shape.body is sim.space.static_body
        assert shape.body.body_type == pymunk.Body.STATIC
        assert shape.collision_type == COLLISION_TYPE_OBSTACLE
        assert shape.elasticity == OBSTACLE_ELASTICITY
        assert shape.friction == OBSTACLE_FRICTION
        assert shape in sim.space.shapes
        assert shape.sensor is False


def test_a_shape_sits_exactly_where_its_spec_says() -> None:
    """Physics geometry and replay metadata describe the same object."""
    sim = Simulation(SEED, arena_layout=pinned(BUMPER, DIAGONAL_BAR))
    circle, box = sim.obstacle_shapes

    assert tuple(circle.offset) == pytest.approx(BUMPER.center)
    assert circle.radius == pytest.approx(BUMPER.radius)

    placed = sorted(tuple(v) for v in box.get_vertices())
    expected = sorted(DIAGONAL_BAR.corners())
    for got, want in zip(placed, expected):
        assert got == pytest.approx(want, abs=1e-6)


def test_obstacle_lookup_is_by_id() -> None:
    sim = Simulation(SEED, arena_layout=pinned(BUMPER, BAR))
    assert sim.obstacle(0) == BUMPER
    assert sim.obstacle(1) == BAR
    assert sim.obstacle(7) is None


def test_procedural_mode_builds_a_shape_per_obstacle() -> None:
    sim = Simulation(SEED, arena_mode=LAYOUT_PROCEDURAL)
    assert sim.arena_mode == LAYOUT_PROCEDURAL
    assert sim.layout.obstacles
    assert len(sim.obstacle_shapes) == len(sim.layout)


# --- fighters ---


def test_a_fighter_bounces_off_a_circular_bumper() -> None:
    sim, mode, ball = lone_fighter(BUMPER)
    aim(ball, (BUMPER.x - 400.0, BUMPER.y), (900.0, 0.0))
    health = ball.health

    assert run_until(mode, lambda: ball.velocity.x < 0.0), "never rebounded"
    assert ball.velocity.length == pytest.approx(900.0, rel=1e-3)
    assert ball.health == health
    assert sim.is_state_valid()


def test_a_fighter_bounces_off_a_rectangular_bar() -> None:
    sim, mode, ball = lone_fighter(BAR)
    aim(ball, (BAR.x, BAR.y - 400.0), (0.0, 900.0))
    health = ball.health

    assert run_until(mode, lambda: ball.velocity.y < 0.0), "never rebounded"
    assert ball.velocity.length == pytest.approx(900.0, rel=1e-3)
    assert abs(ball.velocity.x) < 50.0, "a flat face should reflect straight back"
    assert ball.health == health


def test_a_fighter_deflects_off_a_45_degree_bar() -> None:
    """A diagonal face turns a horizontal shot through a right angle.

    This is the test that a rotated obstacle is physically rotated: an
    axis-aligned bar in the same place would send the ball straight back
    instead of down the arena.
    """
    sim, mode, ball = lone_fighter(DIAGONAL_BAR)
    aim(ball, (DIAGONAL_BAR.x - 360.0, DIAGONAL_BAR.y), (900.0, 0.0))

    assert run_until(mode, lambda: ball.velocity.y > 300.0), "never deflected"
    assert ball.velocity.y > 700.0
    assert abs(ball.velocity.x) < 250.0
    assert ball.velocity.length == pytest.approx(900.0, rel=1e-2)


def test_an_obstacle_never_damages_a_fighter() -> None:
    sim, mode, ball = lone_fighter(BUMPER, BAR)
    aim(ball, (BUMPER.x - 300.0, BUMPER.y), (1100.0, 320.0))

    for _ in range(1800):
        mode.step()
        assert ball.health == ball.max_health
        assert not mode.events, "an obstacle contact recorded a battle event"
    assert sim.is_state_valid()


def test_a_grown_titan_still_fits_between_obstacles_and_walls() -> None:
    """Every generated gap clears a fully grown fighter, so nothing wedges."""
    sim = Simulation(7, arena_mode=LAYOUT_PROCEDURAL)
    mode = PowerBattleMode(sim, powers=("titan", "titan"))
    while mode.step():
        assert sim.is_state_valid()
    assert not sim.dynamic_entities


def test_the_outer_walls_behave_exactly_as_before() -> None:
    """Adding obstacles changes nothing about the arena boundary."""
    for velocity in ((900, 0), (-900, 0), (0, 900), (0, -900)):
        sim, mode, ball = lone_fighter(BUMPER)
        # Launched from a corner of the arena, well clear of the bumper.
        aim(ball, (sim.arena.left + 200.0, sim.arena.top + 200.0), velocity)
        assert run_until(mode, lambda: ball.velocity.dot(velocity) < 0), velocity
        assert sim.is_state_valid()


# --- dynamic entities ---


def test_a_pulse_bolt_is_blocked_by_a_bumper_and_despawns() -> None:
    sim, mode, _ = lone_fighter(BUMPER)
    bolt = sim.spawn(
        Projectile,
        owner_id=0,
        position=(BUMPER.x - 400.0, BUMPER.y),
        velocity=(1750.0, 0.0),
        radius=16.0,
        color=(255, 0, 0),
        damage=18.0,
        lifetime_ticks=seconds_to_ticks(2.2),
    )

    assert run_until(mode, lambda: not bolt.active), "the bolt flew through"
    assert bolt not in sim.dynamic_entities
    assert bolt.body not in sim.space.bodies
    # Blocked, not landed: nobody lost health for it.
    assert all(ball.health == ball.max_health for ball in sim.balls)
    assert not mode.events


def test_a_pulse_bolt_is_blocked_by_a_bar_and_despawns() -> None:
    sim, mode, _ = lone_fighter(BAR)
    bolt = sim.spawn(
        Projectile,
        owner_id=0,
        position=(BAR.x, BAR.y - 400.0),
        velocity=(0.0, 1750.0),
        radius=16.0,
        color=(255, 0, 0),
        damage=18.0,
        lifetime_ticks=seconds_to_ticks(2.2),
    )

    assert run_until(mode, lambda: not bolt.active)
    assert bolt.body not in sim.space.bodies
    assert all(ball.health == ball.max_health for ball in sim.balls)


def test_an_echo_clone_rebounds_off_a_bumper_and_survives() -> None:
    sim, mode, _ = lone_fighter(BUMPER)
    clone = sim.spawn(
        EchoClone,
        owner_id=0,
        position=(BUMPER.x - 400.0, BUMPER.y),
        velocity=(EchoPower.CLONE_SPEED, 0.0),
        radius=30.0,
        color=(255, 0, 0),
        damage=EchoPower.CLONE_DAMAGE,
        lifetime_ticks=seconds_to_ticks(4.0),
        mass=EchoPower.CLONE_MASS,
    )

    assert run_until(mode, lambda: clone.velocity.x < 0.0), "never rebounded"
    assert clone.active and clone in sim.dynamic_entities
    assert clone.velocity.length == pytest.approx(EchoPower.CLONE_SPEED, rel=1e-3)


def test_an_echo_clone_rebounds_off_a_diagonal_bar_and_survives() -> None:
    sim, mode, _ = lone_fighter(DIAGONAL_BAR)
    clone = sim.spawn(
        EchoClone,
        owner_id=0,
        position=(DIAGONAL_BAR.x - 360.0, DIAGONAL_BAR.y),
        velocity=(EchoPower.CLONE_SPEED, 0.0),
        radius=30.0,
        color=(255, 0, 0),
        damage=EchoPower.CLONE_DAMAGE,
        lifetime_ticks=seconds_to_ticks(4.0),
        mass=EchoPower.CLONE_MASS,
    )

    assert run_until(mode, lambda: clone.velocity.y > 300.0), "never deflected"
    assert clone.active
    assert clone.velocity.length == pytest.approx(EchoPower.CLONE_SPEED, rel=1e-2)


def test_orbit_orbs_ride_through_a_battle_full_of_obstacles() -> None:
    sim = Simulation(SEED, arena_mode=LAYOUT_PROCEDURAL)
    mode = PowerBattleMode(sim, powers=(OrbitPower(), OrbitPower()))
    seen = 0
    while mode.step():
        seen = max(seen, sum(1 for e in sim.dynamic_entities if e.kind == "orbit"))
        assert sim.is_state_valid()
        for entity in sim.dynamic_entities:
            assert all(math.isfinite(v) for v in entity.position)
    assert seen >= OrbitPower.ORB_COUNT
    assert not sim.dynamic_entities, "orbs leaked past the end of the battle"


# --- contact reporting ---


def test_a_contact_names_what_was_touched() -> None:
    entity = object()
    fighter = EntityContact(0, entity, ball=object())
    wall = EntityContact(0, entity)
    obstacle = EntityContact(0, entity, obstacle=BUMPER)

    assert (fighter.kind, wall.kind, obstacle.kind) == (
        CONTACT_FIGHTER,
        CONTACT_WALL,
        CONTACT_OBSTACLE,
    )
    assert (fighter.is_wall, wall.is_wall, obstacle.is_wall) == (False, True, False)
    assert (fighter.is_obstacle, obstacle.is_obstacle) == (False, True)
    # Both kinds of arena geometry answer the same question the same way.
    assert (fighter.is_static, wall.is_static, obstacle.is_static) == (
        False,
        True,
        True,
    )


def test_an_obstacle_contact_reports_which_obstacle() -> None:
    sim, mode, _ = lone_fighter(BUMPER)
    sim.spawn(
        EchoClone,
        owner_id=0,
        position=(BUMPER.x - 400.0, BUMPER.y),
        velocity=(EchoPower.CLONE_SPEED, 0.0),
        radius=30.0,
        color=(255, 0, 0),
        damage=EchoPower.CLONE_DAMAGE,
        lifetime_ticks=seconds_to_ticks(4.0),
        mass=EchoPower.CLONE_MASS,
    )

    reported: list[EntityContact] = []
    for _ in range(900):
        mode.step()
        reported.extend(c for c in sim.entity_contacts if c.is_obstacle)
        assert not any(c.is_wall for c in sim.entity_contacts), "wall, not obstacle"
        if reported:
            break

    assert reported, "an obstacle contact was never reported"
    assert reported[0].obstacle == BUMPER
    assert reported[0].ball is None


# --- replay v5 ---


@pytest.fixture(scope="module")
def classic_replay() -> dict:
    return record_battle(SEED)


@pytest.fixture(scope="module")
def procedural_replay() -> dict:
    return record_battle(SEED, arena_mode=LAYOUT_PROCEDURAL)


def test_the_replay_is_version_5(classic_replay: dict) -> None:
    assert classic_replay["version"] == REPLAY_VERSION == 5


def test_a_classic_replay_still_carries_an_empty_layout(classic_replay: dict) -> None:
    layout = classic_replay["layout"]
    assert layout["type"] == LAYOUT_CLASSIC
    assert layout["id"] == LAYOUT_CLASSIC
    assert layout["obstacles"] == []
    assert layout["requested_obstacles"] == 0
    assert layout["fallback"] is False


def test_a_procedural_replay_carries_its_geometry(procedural_replay: dict) -> None:
    layout = procedural_replay["layout"]
    assert layout["type"] == LAYOUT_PROCEDURAL
    assert layout["id"] == f"{LAYOUT_PROCEDURAL}-{SEED}"
    assert layout["obstacles"], "this seed should generate obstacles"
    assert isinstance(layout["fallback"], bool)

    for index, obstacle in enumerate(layout["obstacles"]):
        assert obstacle["id"] == index
        assert obstacle["type"] in (OBSTACLE_CIRCLE, OBSTACLE_BOX)
        assert set(obstacle) == {
            "id",
            "type",
            "x",
            "y",
            "radius",
            "width",
            "height",
            "rotation_degrees",
        }
        assert all(
            math.isfinite(obstacle[key])
            for key in ("x", "y", "radius", "width", "height", "rotation_degrees")
        )


def test_the_replay_geometry_is_exactly_what_the_simulation_built(
    procedural_replay: dict,
) -> None:
    """The Godot contract: the replay is enough to rebuild the arena exactly."""
    sim = Simulation(SEED, arena_mode=LAYOUT_PROCEDURAL)
    exported = procedural_replay["layout"]

    assert exported["id"] == sim.layout.layout_id
    assert exported["type"] == sim.layout.layout_type
    assert exported["requested_obstacles"] == sim.layout.requested_obstacles
    assert exported["fallback"] == sim.layout.fallback
    assert len(exported["obstacles"]) == len(sim.layout)

    for raw, spec in zip(exported["obstacles"], sim.layout.obstacles):
        assert raw["id"] == spec.obstacle_id
        assert raw["type"] == spec.kind
        assert (raw["x"], raw["y"]) == (spec.x, spec.y)
        assert raw["radius"] == spec.radius
        assert (raw["width"], raw["height"]) == (spec.width, spec.height)
        assert raw["rotation_degrees"] == spec.rotation_degrees


def test_a_pinned_layout_round_trips_through_the_replay() -> None:
    replay = record_battle(SEED, arena_layout=pinned(BUMPER, DIAGONAL_BAR))
    circle, box = replay["layout"]["obstacles"]

    assert circle == {
        "id": 0,
        "type": OBSTACLE_CIRCLE,
        "x": BUMPER.x,
        "y": BUMPER.y,
        "radius": BUMPER.radius,
        "width": 0.0,
        "height": 0.0,
        "rotation_degrees": 0.0,
    }
    assert box["type"] == OBSTACLE_BOX
    assert box["rotation_degrees"] == 45.0
    assert (box["width"], box["height"]) == (DIAGONAL_BAR.width, DIAGONAL_BAR.height)


def test_frames_never_repeat_the_static_geometry(procedural_replay: dict) -> None:
    assert "layout" in procedural_replay
    for frame in procedural_replay["frames"]:
        assert "layout" not in frame
        assert "obstacles" not in frame
        # Frames only ever carry things that come and go.
        for entity in frame["entities"]:
            assert entity["type"] in ("projectile", "echo", "orbit", "entity")


def test_a_procedural_replay_is_byte_identical_for_a_seed() -> None:
    first = record_battle(SEED, arena_mode=LAYOUT_PROCEDURAL)
    second = record_battle(SEED, arena_mode=LAYOUT_PROCEDURAL)
    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_the_arena_mode_changes_the_battle_but_not_the_fighters(
    classic_replay: dict, procedural_replay: dict
) -> None:
    """Same seed, same matchup, different geometry - so a different fight."""
    assert classic_replay["seed"] == procedural_replay["seed"]
    assert classic_replay["fighters"] == procedural_replay["fighters"]
    assert classic_replay["frames"][0]["fighters"] == (
        procedural_replay["frames"][0]["fighters"]
    )
    assert classic_replay["layout"] != procedural_replay["layout"]
    assert classic_replay["frames"] != procedural_replay["frames"]

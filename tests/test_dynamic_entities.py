"""Phase 3B1 tests: the temporary-entity foundation, independent of Pulse."""

from __future__ import annotations

import math

import pytest

from engine.simulation import Simulation
from entities.dynamic_entity import COLLISION_TYPE_DYNAMIC_ENTITY, DynamicEntity
from entities.projectile import Projectile

SEED = 12345


def shot(sim: Simulation, /, **kwargs) -> Projectile:
    """Spawn a projectile with sensible defaults for the test at hand."""
    defaults = dict(
        owner_id=0,
        position=(sim.arena.left + 400.0, sim.arena.top + 400.0),
        velocity=(0.0, 0.0),
        radius=16.0,
        color=(255, 0, 0),
        damage=18.0,
        lifetime_ticks=0,
    )
    return sim.spawn(Projectile, **{**defaults, **kwargs})


def parked(seed: int = SEED) -> Simulation:
    """A simulation whose fighters sit still and far apart, out of the way."""
    sim = Simulation(seed)
    for index, ball in enumerate(sim.balls):
        ball.body.position = (
            sim.arena.right - 120.0,
            sim.arena.top + 120.0 + 260.0 * index,
        )
        ball.body.velocity = (0.0, 0.0)
    return sim


# --- identity ---


def test_entity_ids_continue_past_the_fighters() -> None:
    sim = parked()
    first, second = shot(sim), shot(sim)
    assert [ball.ball_id for ball in sim.balls] == [0, 1]
    assert (first.entity_id, second.entity_id) == (2, 3)


def test_entity_ids_are_monotonic_and_never_reused() -> None:
    sim = parked()
    first = shot(sim)
    sim.despawn(first)
    second = shot(sim)
    assert second.entity_id > first.entity_id
    assert second.entity_id == 3


def test_entity_ids_are_deterministic_for_a_seed() -> None:
    def ids() -> list[int]:
        sim = parked()
        return [shot(sim).entity_id for _ in range(4)]

    assert ids() == ids() == [2, 3, 4, 5]


# --- spawn ---


def test_spawn_registers_the_entity_and_its_physics() -> None:
    sim = parked()
    projectile = shot(sim, velocity=(500.0, 0.0))

    assert projectile.active
    assert projectile in sim.dynamic_entities
    assert projectile.body in sim.space.bodies
    assert projectile.shape in sim.space.shapes
    assert projectile.shape.collision_type == COLLISION_TYPE_DYNAMIC_ENTITY
    assert sim.entity(projectile.entity_id) is projectile


def test_multiple_entities_coexist_independently() -> None:
    sim = parked()
    left = shot(sim, position=(sim.arena.left + 200.0, sim.arena.top + 300.0))
    right = shot(sim, position=(sim.arena.left + 600.0, sim.arena.top + 300.0))

    assert len(sim.dynamic_entities) == 2
    assert left.entity_id != right.entity_id
    sim.despawn(left)
    assert sim.dynamic_entities == [right]
    assert right.active and right.body in sim.space.bodies


def test_lookup_of_an_unknown_id_returns_none() -> None:
    sim = parked()
    assert sim.entity(999) is None


# --- despawn ---


def test_despawn_removes_the_entity_from_the_list_and_the_space() -> None:
    sim = parked()
    projectile = shot(sim)
    body, shape = projectile.body, projectile.shape

    sim.despawn(projectile)
    assert not projectile.active
    assert projectile not in sim.dynamic_entities
    assert body not in sim.space.bodies
    assert shape not in sim.space.shapes
    assert sim.entity(projectile.entity_id) is None


def test_despawn_is_idempotent() -> None:
    sim = parked()
    projectile = shot(sim)
    sim.despawn(projectile)
    sim.despawn(projectile)
    assert sim.dynamic_entities == []


def test_despawn_during_a_step_is_deferred_until_the_space_is_safe() -> None:
    """Chipmunk forbids mutating the space from inside a callback."""
    sim = parked()
    projectile = shot(sim)

    # Stand in for being called from a collision callback.
    sim._stepping = True
    sim.despawn(projectile)
    assert not projectile.active
    # Still physically present: removal was queued, not performed.
    assert projectile.body in sim.space.bodies

    sim._stepping = False
    sim.step()
    assert projectile.body not in sim.space.bodies
    assert projectile not in sim.dynamic_entities


def test_clear_entities_retires_everything() -> None:
    sim = parked()
    for offset in range(3):
        shot(sim, position=(sim.arena.left + 200.0 + offset * 60.0, sim.arena.top + 300.0))

    sim.clear_entities()
    assert sim.dynamic_entities == []
    # Only the fighters are left in the space.
    assert set(sim.space.bodies) == {ball.body for ball in sim.balls}


# --- lifetime ---


def test_lifetime_expiry_despawns_the_entity() -> None:
    sim = parked()
    projectile = shot(sim, lifetime_ticks=10)

    for _ in range(9):
        sim.step()
    assert projectile.active and projectile.age_ticks == 9

    sim.step()
    assert not projectile.active
    assert projectile not in sim.dynamic_entities
    assert projectile.body not in sim.space.bodies


def test_zero_lifetime_means_no_self_expiry() -> None:
    sim = parked()
    projectile = shot(sim, lifetime_ticks=0)
    for _ in range(400):
        sim.step()
    assert projectile.active
    assert projectile.expired is False


# --- state ---


def test_entities_keep_finite_state_while_flying() -> None:
    sim = parked()
    projectile = shot(sim, velocity=(900.0, 640.0), lifetime_ticks=600)

    for _ in range(200):
        sim.step()
        if not projectile.active:
            break
        assert all(math.isfinite(v) for v in projectile.position)
        assert all(math.isfinite(v) for v in projectile.velocity)
        assert sim.is_state_valid()


def test_state_validity_rejects_a_non_finite_entity() -> None:
    sim = parked()
    projectile = shot(sim)
    assert sim.is_state_valid()

    projectile.body.position = (float("nan"), 0.0)
    assert sim.is_state_valid() is False


# --- the plain base entity ---


def test_a_non_physical_entity_needs_no_space() -> None:
    """The base class is usable on its own: no body, no shapes, no physics."""
    sim = parked()
    marker = sim.spawn(
        DynamicEntity,
        owner_id=1,
        position=(10.0, 20.0),
        radius=5.0,
        color=(1, 2, 3),
        lifetime_ticks=3,
    )

    assert marker.kind == "entity"
    assert marker.shapes == ()
    assert marker.contact_damage == 0.0
    assert marker.despawn_on_ball_contact is False
    assert marker.despawn_on_wall_contact is False
    assert tuple(marker.position) == (10.0, 20.0)
    assert len(sim.space.bodies) == len(sim.balls)

    for _ in range(3):
        sim.step()
    assert not marker.active


def test_entity_carries_its_own_gameplay_contribution() -> None:
    sim = parked()
    projectile = shot(sim, damage=18.0)
    assert projectile.kind == "projectile"
    assert projectile.contact_damage == pytest.approx(18.0)
    assert projectile.despawn_on_ball_contact is True
    assert projectile.despawn_on_wall_contact is True
    assert projectile.owner_id == 0

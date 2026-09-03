"""Phase 3B2 tests: the Echo power, its bouncing clones and the contact rules."""

from __future__ import annotations

import math

import pytest

from engine.simulation import PHYSICS_HZ, Simulation
from entities.echo_clone import EchoClone
from entities.projectile import Projectile
from modes.power_battle import (
    BATTLE_DURATION_TICKS,
    POWER_WARMUP_TICKS,
    PowerBattleMode,
)
from powers import POWER_NAMES, EchoPower, Power, PulsePower, power_class
from powers.power import seconds_to_ticks
from replay.exporter import REPLAY_VERSION, record_battle

SEED = 12345
LIFETIME_TICKS = seconds_to_ticks(EchoPower.CLONE_LIFETIME_SECONDS)


def inert_power() -> Power:
    """A power whose cooldown never becomes ready inside a battle."""
    return Power(initial_delay_ticks=10**9)


def warm_up(mode: PowerBattleMode) -> None:
    """Step to the tick *before* powers are first allowed to fire.

    The opening warmup holds every power back, so a scripted duel has to get
    past it before an activation can be watched. The fighters are parked, so
    nothing moves while it runs.
    """
    while mode.sim.ticks < POWER_WARMUP_TICKS - 1:
        mode.step()


def echo_duel(*specs, seed: int = SEED):
    """Owner motionless at the arena centre, opponent parked in a corner.

    Centring the owner keeps the arena clamp out of the way, so clone spawn
    geometry is exactly what Echo asked for.
    """
    sim = Simulation(seed)
    mode = PowerBattleMode(sim, powers=specs or (EchoPower(), inert_power()))
    owner, opponent = sim.balls
    owner.body.position = (
        (sim.arena.left + sim.arena.right) / 2,
        (sim.arena.top + sim.arena.bottom) / 2,
    )
    owner.body.velocity = (0.0, 0.0)
    opponent.body.position = (sim.arena.right - 140.0, sim.arena.bottom - 140.0)
    opponent.body.velocity = (0.0, 0.0)
    warm_up(mode)
    return sim, mode, owner, opponent


def live(sim: Simulation) -> list:
    return [e for e in sim.dynamic_entities if e.active]


def launch_clone(sim: Simulation, owner_id: int, position, velocity, **kwargs) -> EchoClone:
    """Place a clone by hand, to aim it somewhere a test needs it to go."""
    defaults = dict(
        radius=30.0,
        color=(255, 0, 0),
        damage=EchoPower.CLONE_DAMAGE,
        lifetime_ticks=LIFETIME_TICKS,
        mass=EchoPower.CLONE_MASS,
    )
    return sim.spawn(
        EchoClone,
        owner_id=owner_id,
        position=tuple(position),
        velocity=tuple(velocity),
        **{**defaults, **kwargs},
    )


# --- registration and assignment ---


def test_echo_is_registered() -> None:
    assert "echo" in POWER_NAMES
    assert power_class("echo") is EchoPower
    assert EchoPower.name == "echo"


def test_explicit_echo_assignment_works() -> None:
    for matchup in (("echo", "pulse"), ("echo", "rush"), ("echo", "titan"), ("echo", "echo")):
        mode = PowerBattleMode(Simulation(SEED), powers=list(matchup))
        assert mode.matchup == matchup
        for ball, name in zip(mode.sim.balls, matchup):
            assert ball.power_name == name


def test_echo_appears_in_seeded_assignment_and_stays_deterministic() -> None:
    matchups = [PowerBattleMode(Simulation(seed)).matchup for seed in range(60)]
    assert any("echo" in matchup for matchup in matchups)
    assert matchups == [PowerBattleMode(Simulation(seed)).matchup for seed in range(60)]


# --- timing ---


def test_echo_timing_is_expressed_in_simulation_ticks() -> None:
    echo = EchoPower()
    assert echo.cooldown_ticks == round(8.5 * PHYSICS_HZ) == 1020
    assert echo.duration_ticks == round(0.30 * PHYSICS_HZ) == 36
    assert LIFETIME_TICKS == round(1.6 * PHYSICS_HZ) == 192


def test_echo_activation_period_is_deterministic() -> None:
    sim, mode, _, _ = echo_duel()
    ticks: list[int] = []
    was_active = False
    while mode.step():
        if mode.powers[0].active and not was_active:
            ticks.append(sim.ticks)
        was_active = mode.powers[0].active

    period = 36 + 1020
    assert ticks[0] == POWER_WARMUP_TICKS
    assert ticks == [POWER_WARMUP_TICKS + period * i for i in range(len(ticks))]
    assert ticks[-1] <= BATTLE_DURATION_TICKS


# --- spawning ---


def test_activation_creates_exactly_two_clones() -> None:
    sim, mode, _, _ = echo_duel()
    assert sim.dynamic_entities == []

    mode.step()
    clones = live(sim)
    assert len(clones) == EchoPower.CLONES_PER_ACTIVATION == 2
    assert all(c.kind == "echo" for c in clones)
    assert all(c.owner_id == 0 for c in clones)


def test_clones_get_unique_deterministic_ids() -> None:
    def ids() -> list[int]:
        sim, mode, _, _ = echo_duel()
        mode.step()
        return sorted(c.entity_id for c in live(sim))

    assert ids() == ids() == [2, 3]


def test_clone_radius_is_derived_from_the_owner_base_radius() -> None:
    sim, mode, owner, _ = echo_duel()
    mode.step()

    expected = owner.base_radius * EchoPower.CLONE_RADIUS_FRACTION
    for clone in live(sim):
        assert clone.radius == pytest.approx(expected)
        assert clone.radius < owner.base_radius
        assert clone.shape.radius == pytest.approx(expected)


def test_clones_spawn_clear_of_the_owner_surface() -> None:
    sim, mode, owner, _ = echo_duel()
    mode.step()

    for clone in live(sim):
        distance = (clone.position - owner.position).length
        assert distance == pytest.approx(
            owner.radius + clone.radius + EchoPower.MUZZLE_GAP
        )
        assert distance > owner.radius + clone.radius


def test_clones_spawn_inside_the_arena() -> None:
    sim, mode, _, _ = echo_duel()
    mode.step()
    for clone in live(sim):
        x, y = clone.position
        assert sim.arena.contains_circle(x, y, clone.radius)


def test_clones_stay_inside_the_arena_when_released_against_a_wall() -> None:
    """Clamping arena validity matters more than surface clearance here."""
    sim = Simulation(SEED)
    mode = PowerBattleMode(sim, powers=[EchoPower(), inert_power()])
    owner, opponent = sim.balls
    owner.body.position = (sim.arena.left + owner.radius, sim.arena.top + owner.radius)
    owner.body.velocity = (0.0, 0.0)
    opponent.body.position = (sim.arena.right - 200.0, sim.arena.bottom - 200.0)
    opponent.body.velocity = (0.0, 0.0)

    warm_up(mode)
    mode.step()
    clones = live(sim)
    assert len(clones) == 2
    for clone in clones:
        x, y = clone.position
        assert sim.arena.contains_circle(x, y, clone.radius)


def test_launch_directions_diverge_around_the_owner_heading() -> None:
    sim, mode, owner, _ = echo_duel()
    owner.body.velocity = (1000.0, 0.0)

    mode.step()
    first, second = sorted(live(sim), key=lambda c: c.entity_id)

    spread = math.degrees(first.velocity.get_angle_between(second.velocity))
    assert abs(spread) == pytest.approx(2 * EchoPower.SPREAD_DEGREES, abs=1e-6)
    # Straddling the owner's course: one either side of it.
    assert first.velocity.angle < 0.0 < second.velocity.angle
    assert first.velocity.length == pytest.approx(EchoPower.CLONE_SPEED)
    assert second.velocity.length == pytest.approx(EchoPower.CLONE_SPEED)


def test_launch_heading_falls_back_to_the_opponent_when_owner_is_still() -> None:
    sim, mode, owner, opponent = echo_duel()
    assert owner.velocity.length == 0.0
    toward = (opponent.position - owner.position).normalized()

    mode.step()
    for clone in live(sim):
        offset = math.degrees(clone.velocity.get_angle_between(toward))
        assert abs(offset) == pytest.approx(EchoPower.SPREAD_DEGREES, abs=1e-6)


def test_launch_heading_has_a_fixed_fallback_with_no_opponent() -> None:
    """No randomness anywhere: a detached, motionless owner still fires."""
    sim, mode, owner, opponent = echo_duel()
    opponent.health = 0.0
    power = mode.powers[0]

    assert power.activate() is True
    clones = live(sim)
    assert len(clones) == 2
    for clone in clones:
        offset = math.degrees(
            clone.velocity.get_angle_between(EchoPower.FALLBACK_HEADING)
        )
        assert abs(offset) == pytest.approx(EchoPower.SPREAD_DEGREES, abs=1e-6)


# --- movement and bouncing ---


def test_clones_actually_move() -> None:
    sim, mode, _, _ = echo_duel()
    mode.step()
    clone = live(sim)[0]
    start = clone.position

    for _ in range(10):
        mode.step()
    assert (clone.position - start).length > 0.0
    assert clone.velocity.length == pytest.approx(EchoPower.CLONE_SPEED, rel=1e-6)


def test_clone_bounces_off_a_wall_and_survives() -> None:
    sim, mode, owner, opponent = echo_duel(inert_power(), inert_power())
    for ball in sim.balls:
        ball.body.position = (sim.arena.left + 200.0, sim.arena.top + 200.0)
        ball.body.velocity = (0.0, 0.0)

    clone = launch_clone(
        sim,
        owner_id=0,
        position=(sim.arena.right - 300.0, sim.arena.bottom - 200.0),
        velocity=(EchoPower.CLONE_SPEED, 0.0),
    )

    wall_contacts = 0
    for _ in range(200):
        mode.step()
        wall_contacts += sum(
            1 for c in sim.entity_contacts if c.entity is clone and c.is_wall
        )
        if wall_contacts:
            break

    assert wall_contacts >= 1
    # Survived the wall and turned around, rather than being spent by it.
    assert clone.active
    assert clone in sim.dynamic_entities
    assert clone.velocity.x < 0.0
    assert clone.velocity.length == pytest.approx(EchoPower.CLONE_SPEED, rel=1e-3)


def test_clone_keeps_bouncing_for_its_whole_lifetime() -> None:
    sim, mode, _, _ = echo_duel(inert_power(), inert_power())
    for ball in sim.balls:
        ball.body.position = (sim.arena.left + 150.0, sim.arena.top + 150.0)
        ball.body.velocity = (0.0, 0.0)

    clone = launch_clone(
        sim,
        owner_id=0,
        position=(sim.arena.right - 250.0, sim.arena.bottom - 250.0),
        velocity=(EchoPower.CLONE_SPEED * 0.8, EchoPower.CLONE_SPEED * 0.6),
    )

    bounces = 0
    while clone.active and mode.step():
        bounces += sum(
            1 for c in sim.entity_contacts if c.entity is clone and c.is_wall
        )
    assert bounces >= 3
    assert clone.age_ticks == LIFETIME_TICKS


# --- owner filter ---


def test_a_clone_cannot_touch_or_damage_its_owner() -> None:
    sim, mode, owner, opponent = echo_duel(inert_power(), inert_power())
    owner.body.position = (sim.arena.left + 500.0, sim.arena.top + 300.0)
    owner.body.velocity = (0.0, 0.0)
    opponent.body.position = (sim.arena.right - 120.0, sim.arena.bottom - 120.0)
    opponent.body.velocity = (0.0, 0.0)

    # Aimed squarely at the owner from close range.
    launch_clone(
        sim,
        owner_id=owner.ball_id,
        position=(owner.position.x - 250.0, owner.position.y),
        velocity=(EchoPower.CLONE_SPEED, 0.0),
    )

    for _ in range(40):
        mode.step()
    assert owner.health == owner.max_health
    assert owner.damage_taken == 0.0
    # Not even a physical nudge: the pair is filtered out before solving.
    assert tuple(owner.velocity) == (0.0, 0.0)


def test_twin_clones_do_not_jostle_each_other() -> None:
    sim, mode, _, _ = echo_duel()
    mode.step()
    first, second = sorted(live(sim), key=lambda c: c.entity_id)
    speeds = (first.velocity.length, second.velocity.length)

    for _ in range(6):
        mode.step()
    assert first.velocity.length == pytest.approx(speeds[0], rel=1e-9)
    assert second.velocity.length == pytest.approx(speeds[1], rel=1e-9)


# --- hitting the opponent ---


def test_clone_hit_deals_the_flat_clone_damage_and_is_spent() -> None:
    sim, mode, owner, opponent = echo_duel(inert_power(), inert_power())
    owner.body.position = (sim.arena.left + 150.0, sim.arena.top + 150.0)
    owner.body.velocity = (0.0, 0.0)
    opponent.body.position = (sim.arena.left + 700.0, sim.arena.bottom - 300.0)
    opponent.body.velocity = (0.0, 0.0)

    clone = launch_clone(
        sim,
        owner_id=owner.ball_id,
        position=(opponent.position.x - 400.0, opponent.position.y),
        velocity=(EchoPower.CLONE_SPEED, 0.0),
    )

    while opponent.health == opponent.max_health and mode.step():
        pass

    assert opponent.health == pytest.approx(
        opponent.max_health - EchoPower.CLONE_DAMAGE
    )
    assert owner.damage_dealt == pytest.approx(EchoPower.CLONE_DAMAGE)
    assert not clone.active
    assert sim.dynamic_entities == []
    assert len(sim.space.bodies) == len(sim.balls)


def test_clone_damage_ignores_the_fighter_impact_formula() -> None:
    """A flat clone damage, not anything derived from closing speed."""
    sim, mode, owner, opponent = echo_duel(inert_power(), inert_power())
    owner.body.position = (sim.arena.left + 150.0, sim.arena.top + 150.0)
    owner.body.velocity = (0.0, 0.0)
    opponent.body.position = (sim.arena.left + 700.0, sim.arena.bottom - 300.0)
    opponent.body.velocity = (0.0, 0.0)

    launch_clone(
        sim,
        owner_id=0,
        position=(opponent.position.x - 400.0, opponent.position.y),
        velocity=(EchoPower.CLONE_SPEED, 0.0),
    )
    while opponent.health == opponent.max_health and mode.step():
        pass

    assert opponent.damage_taken == pytest.approx(EchoPower.CLONE_DAMAGE)
    assert opponent.damage_taken != pytest.approx(
        PowerBattleMode.impact_damage(EchoPower.CLONE_SPEED)
    )


def test_one_clone_contact_deals_damage_exactly_once() -> None:
    sim, mode, owner, opponent = echo_duel(inert_power(), inert_power())
    owner.body.position = (sim.arena.left + 150.0, sim.arena.top + 150.0)
    owner.body.velocity = (0.0, 0.0)
    opponent.body.position = (sim.arena.left + 700.0, sim.arena.bottom - 300.0)
    opponent.body.velocity = (0.0, 0.0)

    launch_clone(
        sim,
        owner_id=0,
        position=(opponent.position.x - 400.0, opponent.position.y),
        velocity=(EchoPower.CLONE_SPEED, 0.0),
    )
    while opponent.health == opponent.max_health and mode.step():
        pass

    settled = opponent.health
    for _ in range(120):
        mode.step()
    assert opponent.health == settled
    assert opponent.damage_taken == pytest.approx(EchoPower.CLONE_DAMAGE)


def test_clone_nudges_the_opponent_without_launching_it() -> None:
    sim, mode, owner, opponent = echo_duel(inert_power(), inert_power())
    owner.body.position = (sim.arena.left + 150.0, sim.arena.top + 150.0)
    owner.body.velocity = (0.0, 0.0)
    opponent.body.position = (sim.arena.left + 700.0, sim.arena.bottom - 300.0)
    opponent.body.velocity = (0.0, 0.0)

    launch_clone(
        sim,
        owner_id=0,
        position=(opponent.position.x - 400.0, opponent.position.y),
        velocity=(EchoPower.CLONE_SPEED, 0.0),
    )
    while opponent.health == opponent.max_health and mode.step():
        pass

    # A light body pushes a heavy one: a real impulse, but well under the
    # speed the clone itself was carrying.
    assert 0.0 < opponent.velocity.length < EchoPower.CLONE_SPEED
    assert sim.is_state_valid()


# --- lifetime and cleanup ---


def test_clone_expires_when_it_never_reaches_the_opponent() -> None:
    sim, mode, _, _ = echo_duel(inert_power(), inert_power())
    for ball in sim.balls:
        ball.body.position = (sim.arena.right - 120.0, sim.arena.top + 120.0)
        ball.body.velocity = (0.0, 0.0)

    clone = launch_clone(
        sim,
        owner_id=0,
        position=(sim.arena.left + 300.0, sim.arena.bottom - 200.0),
        velocity=(0.0, 0.0),
    )

    for _ in range(LIFETIME_TICKS - 1):
        mode.step()
    assert clone.active

    mode.step()
    assert not clone.active
    assert sim.dynamic_entities == []


def test_repeated_activations_use_new_monotonic_ids() -> None:
    sim, mode, _, opponent = echo_duel()
    seen: list[int] = []
    while mode.step():
        opponent.health = opponent.max_health
        for entity in sim.dynamic_entities:
            if entity.entity_id not in seen:
                seen.append(entity.entity_id)

    assert len(seen) >= 6
    assert len(set(seen)) == len(seen)
    assert seen == sorted(seen)
    assert seen[0] == len(sim.balls)


def test_finishing_the_battle_clears_every_clone() -> None:
    sim, mode, _, opponent = echo_duel()
    mode.step()
    assert len(live(sim)) == 2

    opponent.health = 0.0
    assert mode.step() is False
    assert mode.finished

    assert sim.dynamic_entities == []
    assert len(sim.space.bodies) == len(sim.balls)


def test_every_finished_echo_battle_leaves_no_entities() -> None:
    for seed in range(10):
        sim = Simulation(seed)
        mode = PowerBattleMode(sim, powers=["echo", "echo"])
        while mode.step():
            assert sim.is_state_valid()
        assert sim.dynamic_entities == []
        assert len(sim.space.bodies) == len(sim.balls)


def test_clone_is_not_a_fighter() -> None:
    """No health, no power, no standing in the battle result."""
    sim, mode, _, _ = echo_duel()
    mode.step()
    clone = live(sim)[0]

    assert clone not in sim.balls
    assert not hasattr(clone, "health")
    assert not hasattr(clone, "power")
    assert not hasattr(clone, "take_damage")
    assert clone not in [mode.winner]


# --- the refined contact rules ---


def test_contact_rules_differ_between_a_projectile_and_a_clone() -> None:
    assert Projectile.despawn_on_ball_contact is True
    assert Projectile.despawn_on_wall_contact is True
    assert EchoClone.despawn_on_ball_contact is True
    assert EchoClone.despawn_on_wall_contact is False


def test_a_projectile_is_still_spent_by_a_wall() -> None:
    """The rule refinement must not have changed Pulse."""
    sim, mode, _, _ = echo_duel(inert_power(), inert_power())
    for ball in sim.balls:
        ball.body.position = (sim.arena.left + 200.0, sim.arena.top + 200.0)
        ball.body.velocity = (0.0, 0.0)

    projectile = sim.spawn(
        Projectile,
        owner_id=0,
        position=(sim.arena.right - 300.0, sim.arena.bottom - 200.0),
        velocity=(PulsePower.PROJECTILE_SPEED, 0.0),
        radius=PulsePower.PROJECTILE_RADIUS,
        color=(255, 0, 0),
        damage=PulsePower.PROJECTILE_DAMAGE,
        lifetime_ticks=seconds_to_ticks(PulsePower.PROJECTILE_LIFETIME_SECONDS),
    )

    for _ in range(200):
        mode.step()
        if not projectile.active:
            break
    assert not projectile.active
    assert projectile.age_ticks < seconds_to_ticks(
        PulsePower.PROJECTILE_LIFETIME_SECONDS
    )


# --- coexistence ---


def test_echo_battles_against_every_other_power_stay_valid() -> None:
    for matchup in (
        ["echo", "pulse"],
        ["echo", "rush"],
        ["echo", "titan"],
        ["pulse", "echo"],
        ["titan", "echo"],
    ):
        sim = Simulation(SEED)
        mode = PowerBattleMode(sim, powers=matchup)
        while mode.step():
            assert sim.is_state_valid()
        assert mode.finished
        assert sim.dynamic_entities == []
        for ball in sim.balls:
            assert ball.radius == ball.base_radius
            assert ball.body.mass == ball.base_mass


# --- replay ---


@pytest.fixture(scope="module")
def echo_replay() -> dict:
    return record_battle(SEED, powers=["echo", "titan"])


def test_replay_stays_at_version_3(echo_replay: dict) -> None:
    """Echo needs no new fields, so the schema does not move."""
    assert echo_replay["version"] == REPLAY_VERSION == 3


def test_echo_travels_through_the_generic_entities_list(echo_replay: dict) -> None:
    assert set(echo_replay["frames"][0]) == {"tick", "fighters", "entities"}
    owner_color = echo_replay["fighters"][0]["color"]
    expected_radius = echo_replay["fighters"][0]["radius"] * EchoPower.CLONE_RADIUS_FRACTION

    seen = 0
    for frame in echo_replay["frames"]:
        for entity in frame["entities"]:
            seen += 1
            assert set(entity) == {
                "id",
                "type",
                "owner_id",
                "x",
                "y",
                "radius",
                "color",
            }
            assert entity["type"] == "echo"
            assert entity["owner_id"] == 0
            assert entity["color"] == owner_color
            assert entity["radius"] == pytest.approx(expected_radius, abs=1e-2)
            assert math.isfinite(entity["x"]) and math.isfinite(entity["y"])
    assert seen > 0


def test_replay_has_no_echo_specific_fields(echo_replay: dict) -> None:
    assert "echoes" not in echo_replay
    assert "clone_positions" not in echo_replay
    for frame in echo_replay["frames"][:20]:
        assert not any("echo" in key.lower() for key in frame)
        assert not any("clone" in key.lower() for key in frame)


def test_replay_shows_clones_spawning_in_pairs(echo_replay: dict) -> None:
    frames_by_id: dict[int, list[int]] = {}
    for index, frame in enumerate(echo_replay["frames"]):
        for entity in frame["entities"]:
            frames_by_id.setdefault(entity["id"], []).append(index)

    assert len(frames_by_id) >= 2
    for indices in frames_by_id.values():
        # One unbroken appearance: spawn and despawn are each a single edge.
        assert indices == list(range(indices[0], indices[-1] + 1))

    # Clones arrive two at a time, on the same frame.
    first_frames = sorted(indices[0] for indices in frames_by_id.values())
    assert first_frames[0] == first_frames[1]


def test_replay_shows_clones_moving_and_changing_direction(echo_replay: dict) -> None:
    tracks: dict[int, list[tuple[float, float]]] = {}
    for frame in echo_replay["frames"]:
        for entity in frame["entities"]:
            tracks.setdefault(entity["id"], []).append((entity["x"], entity["y"]))

    # A clone released right next to the opponent can be spent inside a
    # single frame, so only the ones that survive long enough are tracked.
    flights = [points for points in tracks.values() if len(points) > 1]
    assert flights

    bounced = 0
    for points in flights:
        steps = [
            (b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:])
        ]
        assert any(abs(dx) > 0.0 or abs(dy) > 0.0 for dx, dy in steps)
        # A bounce reverses one axis of travel; Python decided that, not Godot.
        if any(x[0] * y[0] < 0 or x[1] * y[1] < 0 for x, y in zip(steps, steps[1:])):
            bounced += 1
    assert bounced >= 1


def test_replay_final_frame_holds_no_clones(echo_replay: dict) -> None:
    assert echo_replay["frames"][-1]["entities"] == []


def test_replay_result_matches_the_battle(echo_replay: dict) -> None:
    sim = Simulation(SEED)
    mode = PowerBattleMode(sim, powers=["echo", "titan"])
    while mode.step():
        pass

    result = echo_replay["result"]
    assert result["finished_tick"] == mode.finished_tick
    assert result["is_draw"] is mode.is_draw
    assert result["winner_id"] == (
        None if mode.winner is None else mode.winner.ball_id
    )
    for fighter, ball in zip(echo_replay["frames"][-1]["fighters"], sim.balls):
        assert fighter["health"] == pytest.approx(ball.health, abs=1e-3)


def test_echo_replays_stay_deterministic() -> None:
    assert record_battle(SEED, powers=["echo", "titan"]) == record_battle(
        SEED, powers=["echo", "titan"]
    )
    assert record_battle(404, powers=["echo", "echo"]) == record_battle(
        404, powers=["echo", "echo"]
    )

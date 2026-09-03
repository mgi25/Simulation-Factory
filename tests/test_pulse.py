"""Phase 3B1 tests: the Pulse power and the replay v3 entity contract."""

from __future__ import annotations

import math

import pytest

from engine.simulation import PHYSICS_HZ, Simulation
from entities.projectile import Projectile
from modes.power_battle import (
    BATTLE_DURATION_TICKS,
    POWER_WARMUP_TICKS,
    PowerBattleMode,
)
from powers import POWER_NAMES, Power, PulsePower, power_class
from powers.power import seconds_to_ticks
from replay.exporter import REPLAY_VERSION, record_battle

SEED = 12345
LIFETIME_TICKS = seconds_to_ticks(PulsePower.PROJECTILE_LIFETIME_SECONDS)


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


def pulse_duel(*specs, seed: int = SEED, gap: float = 600.0):
    """Two stationary fighters a known distance apart on one horizontal line.

    Nothing moves unless a power moves it, so the projectile's flight is the
    only thing under test.
    """
    sim = Simulation(seed)
    mode = PowerBattleMode(sim, powers=specs or (PulsePower(), inert_power()))
    shooter, target = sim.balls
    mid_y = (sim.arena.top + sim.arena.bottom) / 2
    left = sim.arena.left + 160.0
    shooter.body.position = (left, mid_y)
    shooter.body.velocity = (0.0, 0.0)
    target.body.position = (left + gap, mid_y)
    target.body.velocity = (0.0, 0.0)
    warm_up(mode)
    return sim, mode, shooter, target


def only_projectile(sim: Simulation) -> Projectile:
    live = [e for e in sim.dynamic_entities if e.active]
    assert len(live) == 1, f"expected exactly one entity, got {len(live)}"
    return live[0]


# --- registration and assignment ---


def test_pulse_is_registered() -> None:
    assert "pulse" in POWER_NAMES
    assert power_class("pulse") is PulsePower
    assert PulsePower.name == "pulse"


def test_explicit_pulse_assignment_works() -> None:
    for matchup in (("pulse", "titan"), ("pulse", "rush"), ("pulse", "pulse")):
        mode = PowerBattleMode(Simulation(SEED), powers=list(matchup))
        assert mode.matchup == matchup
        for ball, name in zip(mode.sim.balls, matchup):
            assert ball.power_name == name


def test_pulse_appears_in_seeded_assignment_and_stays_deterministic() -> None:
    matchups = [PowerBattleMode(Simulation(seed)).matchup for seed in range(60)]
    assert any("pulse" in matchup for matchup in matchups)
    repeat = [PowerBattleMode(Simulation(seed)).matchup for seed in range(60)]
    assert matchups == repeat


# --- timing ---


def test_pulse_timing_is_expressed_in_simulation_ticks() -> None:
    pulse = PulsePower()
    assert pulse.cooldown_ticks == round(6.5 * PHYSICS_HZ) == 780
    assert pulse.duration_ticks == round(0.25 * PHYSICS_HZ) == 30


def test_pulse_activation_period_is_deterministic() -> None:
    sim, mode, _, _ = pulse_duel(PulsePower(), inert_power())
    ticks: list[int] = []
    was_active = False
    while mode.step():
        if mode.powers[0].active and not was_active:
            ticks.append(sim.ticks)
        was_active = mode.powers[0].active

    period = 30 + 780
    assert ticks[0] == POWER_WARMUP_TICKS
    assert ticks == [POWER_WARMUP_TICKS + period * i for i in range(len(ticks))]
    assert ticks[-1] <= BATTLE_DURATION_TICKS


# --- firing ---


def test_one_activation_creates_exactly_one_projectile() -> None:
    sim, mode, _, _ = pulse_duel()
    assert sim.dynamic_entities == []

    mode.step()
    projectile = only_projectile(sim)
    assert projectile.kind == "projectile"
    assert projectile.owner_id == 0

    # Still one for the whole activation window and the projectile's flight.
    for _ in range(mode.powers[0].duration_ticks):
        mode.step()
        assert len([e for e in sim.dynamic_entities if e.active]) <= 1


def test_projectile_starts_outside_the_owner() -> None:
    sim, mode, shooter, _ = pulse_duel()
    mode.step()
    projectile = only_projectile(sim)

    distance = (projectile.position - shooter.position).length
    assert distance >= shooter.radius + projectile.radius
    assert distance == pytest.approx(
        shooter.radius + projectile.radius + PulsePower.MUZZLE_GAP
    )


def test_projectile_spawns_inside_the_arena() -> None:
    sim, mode, _, _ = pulse_duel()
    mode.step()
    projectile = only_projectile(sim)
    x, y = projectile.position
    assert sim.arena.contains_circle(x, y, projectile.radius)


def test_projectile_muzzle_stays_in_the_arena_when_firing_from_a_wall() -> None:
    """Back to the wall, opponent behind: the muzzle must not land outside."""
    sim = Simulation(SEED)
    mode = PowerBattleMode(sim, powers=[PulsePower(), inert_power()])
    shooter, target = sim.balls
    shooter.body.position = (sim.arena.left + shooter.radius, sim.arena.top + 200.0)
    shooter.body.velocity = (0.0, 0.0)
    target.body.position = (sim.arena.left + 60.0, sim.arena.top + 120.0)
    target.body.velocity = (0.0, 0.0)

    warm_up(mode)
    mode.step()
    projectile = only_projectile(sim)
    x, y = projectile.position
    assert sim.arena.contains_circle(x, y, projectile.radius)


def test_projectile_aims_at_the_opponent() -> None:
    sim, mode, shooter, target = pulse_duel()
    before = (target.position - shooter.position).normalized()

    mode.step()
    projectile = only_projectile(sim)

    heading = projectile.velocity.normalized()
    assert heading.x == pytest.approx(before.x, abs=1e-9)
    assert heading.y == pytest.approx(before.y, abs=1e-9)
    assert projectile.velocity.length == pytest.approx(PulsePower.PROJECTILE_SPEED)


def test_projectile_travels_in_a_straight_line_at_constant_speed() -> None:
    sim, mode, _, target = pulse_duel(PulsePower(), inert_power(), gap=900.0)
    mode.step()
    projectile = only_projectile(sim)
    heading = projectile.velocity.normalized()
    start = projectile.position

    for _ in range(20):
        mode.step()
        assert projectile.active
        assert projectile.velocity.length == pytest.approx(
            PulsePower.PROJECTILE_SPEED, rel=1e-9
        )
        travelled = projectile.position - start
        assert travelled.normalized().x == pytest.approx(heading.x, abs=1e-9)
        assert travelled.normalized().y == pytest.approx(heading.y, abs=1e-9)
    assert (projectile.position - start).length > 0.0


# --- hits ---


def test_projectile_hit_deals_the_flat_projectile_damage() -> None:
    sim, mode, shooter, target = pulse_duel()
    while mode.step() and target.health == target.max_health:
        pass

    assert target.health == pytest.approx(
        target.max_health - PulsePower.PROJECTILE_DAMAGE
    )
    assert shooter.damage_dealt == pytest.approx(PulsePower.PROJECTILE_DAMAGE)
    assert shooter.health == shooter.max_health


def test_projectile_damage_ignores_the_collision_impact_formula() -> None:
    """A flat 18 HP, not something derived from closing speed."""
    sim, mode, _, target = pulse_duel()
    while mode.step() and target.health == target.max_health:
        pass

    taken = target.damage_taken
    assert taken == pytest.approx(PulsePower.PROJECTILE_DAMAGE)
    assert taken != pytest.approx(
        PowerBattleMode.impact_damage(PulsePower.PROJECTILE_SPEED)
    )


def test_projectile_despawns_when_it_hits_the_opponent() -> None:
    sim, mode, _, target = pulse_duel()
    while mode.step() and target.health == target.max_health:
        pass

    assert sim.dynamic_entities == []
    assert len(sim.space.bodies) == len(sim.balls)


def test_projectile_does_not_shove_the_fighter_it_hits() -> None:
    sim, mode, _, target = pulse_duel()
    while mode.step() and target.health == target.max_health:
        pass

    # A sensor shape generates no impulse at all.
    assert tuple(target.velocity) == (0.0, 0.0)
    assert target.body.angular_velocity == 0.0


def test_projectile_never_damages_its_owner() -> None:
    """Fired straight back at the owner, it must pass clean through."""
    sim, mode, shooter, target = pulse_duel(inert_power(), inert_power(), gap=800.0)
    heading = (shooter.position - target.position).normalized()

    sim.spawn(
        Projectile,
        owner_id=shooter.ball_id,
        position=tuple(shooter.position + heading * 300.0),
        velocity=tuple(-heading * PulsePower.PROJECTILE_SPEED),
        radius=PulsePower.PROJECTILE_RADIUS,
        color=shooter.color,
        damage=PulsePower.PROJECTILE_DAMAGE,
        lifetime_ticks=LIFETIME_TICKS,
    )

    for _ in range(120):
        mode.step()
    assert shooter.health == shooter.max_health
    assert shooter.damage_taken == 0.0
    assert tuple(shooter.velocity) == (0.0, 0.0)


def test_projectile_despawns_on_a_wall() -> None:
    sim, mode, shooter, target = pulse_duel(inert_power(), inert_power())
    # Aimed at the right wall, with both fighters well out of the way.
    for ball in sim.balls:
        ball.body.position = (sim.arena.left + 200.0, sim.arena.top + 150.0 * (ball.ball_id + 1))
        ball.body.velocity = (0.0, 0.0)
    projectile = sim.spawn(
        Projectile,
        owner_id=0,
        position=(sim.arena.right - 300.0, sim.arena.bottom - 150.0),
        velocity=(PulsePower.PROJECTILE_SPEED, 0.0),
        radius=PulsePower.PROJECTILE_RADIUS,
        color=(255, 0, 0),
        damage=PulsePower.PROJECTILE_DAMAGE,
        lifetime_ticks=LIFETIME_TICKS,
    )

    hit_tick = None
    for _ in range(200):
        mode.step()
        if not projectile.active:
            hit_tick = sim.ticks
            break

    assert hit_tick is not None
    # Long before its lifetime would have run out, and no bounce.
    assert projectile.age_ticks < LIFETIME_TICKS
    assert sim.dynamic_entities == []
    assert all(ball.health == ball.max_health for ball in sim.balls)


def test_projectile_expires_when_it_hits_nothing() -> None:
    sim, mode, _, _ = pulse_duel(inert_power(), inert_power())
    for ball in sim.balls:
        ball.body.position = (sim.arena.right - 120.0, sim.arena.top + 120.0)
        ball.body.velocity = (0.0, 0.0)
    projectile = sim.spawn(
        Projectile,
        owner_id=0,
        position=(sim.arena.left + 300.0, sim.arena.bottom - 200.0),
        velocity=(0.0, 0.0),
        radius=PulsePower.PROJECTILE_RADIUS,
        color=(255, 0, 0),
        damage=PulsePower.PROJECTILE_DAMAGE,
        lifetime_ticks=LIFETIME_TICKS,
    )

    for _ in range(LIFETIME_TICKS - 1):
        mode.step()
    assert projectile.active

    mode.step()
    assert not projectile.active
    assert sim.dynamic_entities == []


def test_repeated_activations_produce_unique_projectile_ids() -> None:
    sim, mode, _, target = pulse_duel(PulsePower(), inert_power())
    # Keep the target alive so the shooter keeps firing all battle.
    seen: list[int] = []
    while mode.step():
        target.health = target.max_health
        for entity in sim.dynamic_entities:
            if entity.entity_id not in seen:
                seen.append(entity.entity_id)

    assert len(seen) >= 4
    assert len(set(seen)) == len(seen)
    assert seen == sorted(seen)
    assert seen[0] == len(sim.balls)


def test_two_pulse_fighters_can_have_projectiles_in_flight_at_once() -> None:
    sim = Simulation(SEED)
    mode = PowerBattleMode(sim, powers=[PulsePower(), PulsePower()])
    a, b = sim.balls
    mid_y = (sim.arena.top + sim.arena.bottom) / 2
    a.body.position = (sim.arena.left + 140.0, mid_y)
    b.body.position = (sim.arena.right - 140.0, mid_y)
    for ball in sim.balls:
        ball.body.velocity = (0.0, 0.0)

    warm_up(mode)
    mode.step()
    live = [e for e in sim.dynamic_entities if e.active]
    assert len(live) == 2
    assert {e.owner_id for e in live} == {0, 1}
    assert len({e.entity_id for e in live}) == 2


# --- cleanup ---


def test_finishing_the_battle_clears_projectiles_in_flight() -> None:
    sim, mode, _, target = pulse_duel(PulsePower(), inert_power(), gap=900.0)
    mode.step()
    assert only_projectile(sim).active

    target.health = 0.0
    assert mode.step() is False
    assert mode.finished

    assert sim.dynamic_entities == []
    assert len(sim.space.bodies) == len(sim.balls)


def test_no_new_projectiles_after_the_battle_is_over() -> None:
    sim, mode, _, _ = pulse_duel()
    while mode.step():
        pass
    assert sim.dynamic_entities == []

    for _ in range(2000):
        assert mode.step() is False
    assert sim.dynamic_entities == []


def test_every_finished_pulse_battle_leaves_no_entities() -> None:
    for seed in range(12):
        sim = Simulation(seed)
        mode = PowerBattleMode(sim, powers=["pulse", "pulse"])
        while mode.step():
            assert sim.is_state_valid()
        assert sim.dynamic_entities == []
        assert len(sim.space.bodies) == len(sim.balls)


# --- coexistence with Rush and Titan ---


def test_pulse_battles_against_rush_and_titan_stay_valid() -> None:
    for matchup in (["pulse", "rush"], ["pulse", "titan"], ["titan", "pulse"]):
        sim = Simulation(SEED)
        mode = PowerBattleMode(sim, powers=matchup)
        while mode.step():
            assert sim.is_state_valid()
        assert mode.finished
        for ball in sim.balls:
            assert ball.radius == ball.base_radius
            assert ball.body.mass == ball.base_mass


def test_titan_radius_still_exports_dynamically_alongside_pulse() -> None:
    replay = record_battle(SEED, powers=["pulse", "titan"])
    titan_base = replay["fighters"][1]["radius"]
    peak = max(frame["fighters"][1]["radius"] for frame in replay["frames"])
    assert peak == pytest.approx(titan_base * 1.50, abs=1e-2)
    # Pulse does not resize its owner.
    pulse_radii = {frame["fighters"][0]["radius"] for frame in replay["frames"]}
    assert pulse_radii == {replay["fighters"][0]["radius"]}


# --- replay v3 ---


@pytest.fixture(scope="module")
def pulse_replay() -> dict:
    return record_battle(SEED, powers=["pulse", "titan"])


def test_replay_is_version_3(pulse_replay: dict) -> None:
    assert pulse_replay["version"] == REPLAY_VERSION == 3


def test_every_frame_has_an_entities_list(pulse_replay: dict) -> None:
    for frame in pulse_replay["frames"]:
        assert isinstance(frame["entities"], list)


def test_frames_without_entities_hold_an_empty_list(pulse_replay: dict) -> None:
    empty = [f for f in pulse_replay["frames"] if not f["entities"]]
    assert empty, "expected frames with nothing in flight"
    assert pulse_replay["frames"][0]["entities"] == []


def test_entity_records_carry_exactly_the_agreed_fields(pulse_replay: dict) -> None:
    owner_colors = {m["id"]: m["color"] for m in pulse_replay["fighters"]}
    seen = 0

    for frame in pulse_replay["frames"]:
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
            assert entity["type"] == "projectile"
            assert entity["owner_id"] in owner_colors
            assert entity["color"] == owner_colors[entity["owner_id"]]
            assert entity["id"] >= len(pulse_replay["fighters"])
            assert math.isfinite(entity["x"]) and math.isfinite(entity["y"])
            assert entity["radius"] == pytest.approx(PulsePower.PROJECTILE_RADIUS)
    assert seen > 0


def test_replay_has_no_pulse_specific_positional_fields(pulse_replay: dict) -> None:
    """Entities live in one reusable collection, not in bespoke keys."""
    assert set(pulse_replay["frames"][0]) == {"tick", "fighters", "entities"}
    flat = " ".join(pulse_replay["frames"][0]).lower()
    assert "pulse" not in flat and "projectile" not in flat
    for meta in pulse_replay["fighters"]:
        assert not any("pulse" in key.lower() for key in meta)


def test_entity_ids_in_the_replay_are_deterministic_and_contiguous(
    pulse_replay: dict,
) -> None:
    ids = sorted({e["id"] for f in pulse_replay["frames"] for e in f["entities"]})
    assert ids == list(range(len(pulse_replay["fighters"]), len(pulse_replay["fighters"]) + len(ids)))
    assert record_battle(SEED, powers=["pulse", "titan"]) == pulse_replay


def test_each_entity_occupies_one_unbroken_run_of_frames(pulse_replay: dict) -> None:
    """Spawn and despawn are visible as a single contiguous appearance."""
    frames_by_id: dict[int, list[int]] = {}
    for index, frame in enumerate(pulse_replay["frames"]):
        for entity in frame["entities"]:
            frames_by_id.setdefault(entity["id"], []).append(index)

    assert frames_by_id
    for entity_id, indices in frames_by_id.items():
        assert indices == list(range(indices[0], indices[-1] + 1))
        # Never longer than the projectile could possibly live.
        span = indices[-1] - indices[0] + 1
        assert span <= LIFETIME_TICKS // pulse_replay["ticks_per_frame"] + 1


def test_final_frame_has_no_leftover_entities(pulse_replay: dict) -> None:
    assert pulse_replay["frames"][-1]["entities"] == []


def test_replay_result_matches_the_battle(pulse_replay: dict) -> None:
    sim = Simulation(SEED)
    mode = PowerBattleMode(sim, powers=["pulse", "titan"])
    while mode.step():
        pass

    result = pulse_replay["result"]
    assert result["finished_tick"] == mode.finished_tick
    assert result["is_draw"] is mode.is_draw
    assert result["winner_id"] == (
        None if mode.winner is None else mode.winner.ball_id
    )
    for fighter, ball in zip(pulse_replay["frames"][-1]["fighters"], sim.balls):
        assert fighter["health"] == pytest.approx(ball.health, abs=1e-3)


def test_pulse_replays_stay_deterministic() -> None:
    assert record_battle(999, powers=["pulse", "pulse"]) == record_battle(
        999, powers=["pulse", "pulse"]
    )
    assert record_battle(999) == record_battle(999)

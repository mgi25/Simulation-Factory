"""Phase 3B3 tests: the Orbit power, its satellites and the pre-step hook."""

from __future__ import annotations

import math

import pymunk
import pytest

from engine.simulation import PHYSICS_HZ, Simulation
from entities.dynamic_entity import DynamicEntity
from entities.echo_clone import EchoClone
from entities.orbit_orb import OrbitOrb
from entities.projectile import Projectile
from modes.power_battle import BATTLE_DURATION_TICKS, PowerBattleMode
from powers import POWER_NAMES, EchoPower, OrbitPower, Power, PulsePower, power_class
from powers.power import seconds_to_ticks
from replay.exporter import REPLAY_VERSION, record_battle

SEED = 12345


def inert_power() -> Power:
    """A power whose cooldown never becomes ready inside a battle."""
    return Power(initial_delay_ticks=10**9)


def orbit_duel(*specs, seed: int = SEED, opponent_far: bool = True):
    """Owner parked at the arena centre; opponent parked out of reach.

    Both motionless, so an orb's position is exactly what Orbit computed
    rather than that plus a tick of owner travel.
    """
    sim = Simulation(seed)
    mode = PowerBattleMode(sim, powers=specs or (OrbitPower(), inert_power()))
    owner, opponent = sim.balls
    owner.body.position = (
        (sim.arena.left + sim.arena.right) / 2,
        (sim.arena.top + sim.arena.bottom) / 2,
    )
    owner.body.velocity = (0.0, 0.0)
    if opponent_far:
        opponent.body.position = (sim.arena.right - 120.0, sim.arena.bottom - 120.0)
    opponent.body.velocity = (0.0, 0.0)
    return sim, mode, owner, opponent


def live(sim: Simulation) -> list:
    return [e for e in sim.dynamic_entities if e.active]


def orbs_of(sim: Simulation) -> list[OrbitOrb]:
    return sorted(
        (e for e in live(sim) if isinstance(e, OrbitOrb)),
        key=lambda o: o.entity_id,
    )


# --- registration and assignment ---


def test_orbit_is_registered_as_the_fifth_power() -> None:
    assert POWER_NAMES == ("rush", "titan", "pulse", "echo", "orbit")
    assert power_class("orbit") is OrbitPower
    assert OrbitPower.name == "orbit"


def test_explicit_orbit_assignment_works() -> None:
    for other in ("rush", "titan", "pulse", "echo", "orbit"):
        mode = PowerBattleMode(Simulation(SEED), powers=["orbit", other])
        assert mode.matchup == ("orbit", other)
        assert mode.sim.balls[0].power_name == "orbit"


def test_orbit_appears_in_seeded_assignment_and_stays_deterministic() -> None:
    matchups = [PowerBattleMode(Simulation(seed)).matchup for seed in range(80)]
    assert any("orbit" in matchup for matchup in matchups)
    assert matchups == [PowerBattleMode(Simulation(seed)).matchup for seed in range(80)]


# --- timing ---


def test_orbit_timing_is_expressed_in_simulation_ticks() -> None:
    orbit = OrbitPower()
    assert orbit.cooldown_ticks == round(6.5 * PHYSICS_HZ) == 780
    assert orbit.duration_ticks == round(2.75 * PHYSICS_HZ) == 330


def test_orbit_activation_period_is_deterministic() -> None:
    sim, mode, _, _ = orbit_duel()
    ticks: list[int] = []
    was_active = False
    while mode.step():
        if mode.powers[0].active and not was_active:
            ticks.append(sim.ticks)
        was_active = mode.powers[0].active

    period = 330 + 780
    assert ticks[0] == 1
    assert ticks == [1 + period * i for i in range(len(ticks))]
    assert ticks[-1] <= BATTLE_DURATION_TICKS


# --- deployment ---


def test_activation_creates_exactly_three_orbiters() -> None:
    sim, mode, _, _ = orbit_duel()
    assert sim.dynamic_entities == []

    mode.step()
    orbs = orbs_of(sim)
    assert len(orbs) == OrbitPower.ORB_COUNT == 3
    assert all(o.kind == "orbit" for o in orbs)
    assert all(o.owner_id == 0 for o in orbs)
    assert all(o.radius == OrbitPower.ORB_RADIUS for o in orbs)


def test_orb_ids_are_unique_monotonic_and_deterministic() -> None:
    def ids() -> list[int]:
        sim, mode, _, _ = orbit_duel()
        mode.step()
        return [o.entity_id for o in orbs_of(sim)]

    first = ids()
    assert first == ids() == [2, 3, 4]
    assert len(set(first)) == 3


def test_orbiters_start_evenly_spaced() -> None:
    sim, mode, _, _ = orbit_duel()
    mode.step()

    angles = sorted(math.degrees(o.angle) % 360.0 for o in orbs_of(sim))
    gaps = [(angles[(i + 1) % 3] - angles[i]) % 360.0 for i in range(3)]
    for gap in gaps:
        assert gap == pytest.approx(120.0, abs=1e-6)


def test_orbit_radius_derives_from_the_owner_base_radius() -> None:
    sim, mode, owner, _ = orbit_duel()
    power = mode.powers[0]
    assert power.orbit_radius == pytest.approx(
        owner.base_radius + OrbitPower.ORBIT_EXTRA_DISTANCE
    )

    mode.step()
    for orb in orbs_of(sim):
        assert orb.orbit_radius == pytest.approx(power.orbit_radius)
        distance = (orb.position - owner.position).length
        assert distance == pytest.approx(power.orbit_radius, abs=1e-6)


def test_orbit_radius_ignores_a_temporary_size_change() -> None:
    """Measured from base_radius, so growing the owner cannot drag the orbit."""
    sim, mode, owner, _ = orbit_duel()
    power = mode.powers[0]
    before = power.orbit_radius

    owner.set_size_scale(1.5, 1.75)
    assert owner.radius > owner.base_radius
    assert power.orbit_radius == pytest.approx(before)


def test_first_orb_starts_on_the_owner_line_of_travel() -> None:
    sim, mode, owner, _ = orbit_duel()
    owner.body.velocity = (700.0, 700.0)
    heading = owner.velocity.angle

    mode.step()
    first = orbs_of(sim)[0]
    # Deployment happens after the physics step, so the starting angle is
    # still exactly the heading; rotation begins on the following tick.
    assert first.angle == pytest.approx(heading, abs=1e-9)


# --- rotation ---


def test_orbiters_revolve_around_a_stationary_owner() -> None:
    sim, mode, owner, _ = orbit_duel()
    mode.step()
    orb = orbs_of(sim)[0]
    start_angle = orb.angle
    start_position = orb.position

    for _ in range(30):
        mode.step()

    assert orb.angle != start_angle
    assert (orb.position - start_position).length > 0.0
    # Still on its circle: it revolved rather than drifted away.
    assert (orb.position - owner.position).length == pytest.approx(
        orb.orbit_radius, abs=1e-6
    )


def test_angular_progression_is_exactly_one_step_per_tick() -> None:
    sim, mode, owner, _ = orbit_duel()
    mode.step()
    orb = orbs_of(sim)[0]
    step = mode.powers[0].angular_step()

    before = orb.angle
    mode.step()
    assert orb.angle - before == pytest.approx(step, abs=1e-12)

    # And the position agrees with the angle it now holds.
    expected = owner.position + pymunk.Vec2d(
        math.cos(orb.angle), math.sin(orb.angle)
    ) * orb.orbit_radius
    assert (orb.position - expected).length == pytest.approx(0.0, abs=1e-6)


def test_angular_speed_matches_the_declared_degrees_per_second() -> None:
    sim, mode, _, _ = orbit_duel()
    mode.step()
    step = mode.powers[0].angular_step()
    per_second = math.degrees(abs(step)) * PHYSICS_HZ
    assert per_second == pytest.approx(OrbitPower.ANGULAR_SPEED_DEGREES)


def test_rotation_direction_is_deterministic_and_differs_per_fighter() -> None:
    sim = Simulation(SEED)
    # Pinned instances, so both fighters deploy on the same tick instead of
    # waiting out their seeded activation offsets.
    mode = PowerBattleMode(sim, powers=[OrbitPower(), OrbitPower()])
    first, second = mode.powers
    assert first.spin_direction() == 1
    assert second.spin_direction() == -1
    assert first.angular_step() == pytest.approx(-second.angular_step())

    mode.step()
    by_owner: dict[int, OrbitOrb] = {}
    for orb in orbs_of(sim):
        by_owner.setdefault(orb.owner_id, orb)
    before = {oid: orb.angle for oid, orb in by_owner.items()}

    for _ in range(10):
        mode.step()
    deltas = {oid: orb.angle - before[oid] for oid, orb in by_owner.items()}
    assert deltas[0] > 0.0 > deltas[1]


def test_rotation_is_deterministic_across_identical_runs() -> None:
    def trace() -> list[tuple[float, float]]:
        sim, mode, _, _ = orbit_duel()
        points: list[tuple[float, float]] = []
        for _ in range(60):
            mode.step()
            points.extend((round(o.position.x, 9), round(o.position.y, 9)) for o in orbs_of(sim))
        return points

    assert trace() == trace()


# --- following the owner (the essential behaviour) ---


def test_orbiters_follow_the_owner_instead_of_a_fixed_point() -> None:
    sim, mode, owner, _ = orbit_duel()
    mode.step()
    origin = owner.position
    assert all(
        (o.position - origin).length == pytest.approx(o.orbit_radius, abs=1e-6)
        for o in orbs_of(sim)
    )

    # Move the owner a long way and let one tick of positioning happen.
    moved = pymunk.Vec2d(origin.x - 300.0, origin.y + 260.0)
    owner.body.position = moved
    mode.step()

    for orb in orbs_of(sim):
        assert (orb.position - moved).length == pytest.approx(
            orb.orbit_radius, abs=1e-6
        )
        # Emphatically not still circling where it started.
        assert (orb.position - origin).length > orb.orbit_radius


def test_orbiters_track_an_owner_that_keeps_moving() -> None:
    sim, mode, owner, _ = orbit_duel()
    owner.body.velocity = (600.0, 0.0)
    mode.step()

    for _ in range(40):
        previous = owner.position
        mode.step()
        assert owner.position != previous
        for orb in orbs_of(sim):
            # Positioned before the step, so the owner has since advanced by
            # one tick; the orbit still rides with it.
            distance = (orb.position - owner.position).length
            assert distance == pytest.approx(orb.orbit_radius, abs=12.0)


# --- the pre-step hook ---


def test_the_default_before_step_does_nothing() -> None:
    sim, _, _, _ = orbit_duel(inert_power(), inert_power())
    marker = sim.spawn(
        DynamicEntity,
        owner_id=0,
        position=(400.0, 700.0),
        radius=5.0,
        color=(1, 2, 3),
    )
    before = tuple(marker.position)

    marker.before_step(sim)
    assert tuple(marker.position) == before


def test_a_projectile_is_unaffected_by_the_hook() -> None:
    """Pulse is carried by Pymunk; the hook must not touch it."""
    sim, mode, _, _ = orbit_duel(inert_power(), inert_power())
    projectile = sim.spawn(
        Projectile,
        owner_id=0,
        position=(sim.arena.left + 300.0, sim.arena.top + 300.0),
        velocity=(PulsePower.PROJECTILE_SPEED, 0.0),
        radius=PulsePower.PROJECTILE_RADIUS,
        color=(255, 0, 0),
        damage=PulsePower.PROJECTILE_DAMAGE,
        lifetime_ticks=seconds_to_ticks(PulsePower.PROJECTILE_LIFETIME_SECONDS),
    )
    start = projectile.position

    for _ in range(10):
        mode.step()
    travelled = projectile.position - start
    assert travelled.y == pytest.approx(0.0, abs=1e-6)
    assert travelled.x == pytest.approx(
        PulsePower.PROJECTILE_SPEED * 10 / PHYSICS_HZ, rel=1e-6
    )


def test_a_clone_still_bounces_with_the_hook_in_place() -> None:
    """Echo is carried by Pymunk too, walls included."""
    sim, mode, _, _ = orbit_duel(inert_power(), inert_power())
    for ball in sim.balls:
        ball.body.position = (sim.arena.left + 200.0, sim.arena.top + 200.0)
        ball.body.velocity = (0.0, 0.0)

    clone = sim.spawn(
        EchoClone,
        owner_id=0,
        position=(sim.arena.right - 300.0, sim.arena.bottom - 200.0),
        velocity=(EchoPower.CLONE_SPEED, 0.0),
        radius=30.0,
        color=(255, 0, 0),
        damage=EchoPower.CLONE_DAMAGE,
        lifetime_ticks=seconds_to_ticks(EchoPower.CLONE_LIFETIME_SECONDS),
        mass=EchoPower.CLONE_MASS,
    )

    for _ in range(200):
        mode.step()
        if clone.velocity.x < 0.0:
            break
    assert clone.active
    assert clone.velocity.x < 0.0


def test_orbit_is_positioned_before_collisions_are_solved() -> None:
    """An orb that sweeps into the opponent lands its hit that same step."""
    sim, mode, owner, opponent = orbit_duel(
        OrbitPower(), inert_power(), opponent_far=False
    )
    radius = mode.powers[0].orbit_radius
    # Just off the orbit circle at the start, so only rotation can reach it.
    opponent.body.position = (owner.position.x, owner.position.y + radius)
    opponent.body.velocity = (0.0, 0.0)

    mode.step()
    starting = opponent.health

    for _ in range(200):
        mode.step()
        if opponent.health < starting:
            break
    assert opponent.health < starting


# --- owner filter ---


def test_orbiters_cannot_damage_or_touch_their_owner() -> None:
    sim, mode, owner, _ = orbit_duel()
    for _ in range(200):
        mode.step()

    assert owner.health == owner.max_health
    assert owner.damage_taken == 0.0
    assert tuple(owner.velocity) == (0.0, 0.0)


def test_same_owner_orbiters_do_not_interfere() -> None:
    sim, mode, _, _ = orbit_duel()
    mode.step()
    orbs = orbs_of(sim)

    for _ in range(60):
        mode.step()
    still = orbs_of(sim)
    assert len(still) == 3
    angles = sorted(math.degrees(o.angle) % 360.0 for o in still)
    gaps = [(angles[(i + 1) % 3] - angles[i]) % 360.0 for i in range(3)]
    for gap in gaps:
        assert gap == pytest.approx(120.0, abs=1e-6)


# --- hitting the opponent ---


def test_each_orb_lands_one_hit_and_the_rest_carry_on() -> None:
    sim, mode, owner, opponent = orbit_duel(
        OrbitPower(), inert_power(), opponent_far=False
    )
    radius = mode.powers[0].orbit_radius
    opponent.body.position = (owner.position.x + radius, owner.position.y)
    opponent.body.velocity = (0.0, 0.0)

    hits: list[int] = []
    health = opponent.health
    for _ in range(400):
        if not mode.step():
            break
        if opponent.health < health:
            hits.append(len(orbs_of(sim)))
            health = opponent.health

    assert len(hits) == 3
    # One orb consumed per hit, the others still in play.
    assert hits == [2, 1, 0]
    assert opponent.damage_taken == pytest.approx(3 * OrbitPower.ORB_DAMAGE)
    assert owner.damage_dealt == pytest.approx(3 * OrbitPower.ORB_DAMAGE)


def test_orb_damage_is_flat_and_ignores_the_impact_formula() -> None:
    sim, mode, owner, opponent = orbit_duel(
        OrbitPower(), inert_power(), opponent_far=False
    )
    radius = mode.powers[0].orbit_radius
    opponent.body.position = (owner.position.x + radius, owner.position.y)
    opponent.body.velocity = (0.0, 0.0)

    while opponent.health == opponent.max_health and mode.step():
        pass
    assert opponent.health == pytest.approx(
        opponent.max_health - OrbitPower.ORB_DAMAGE
    )


def test_orbiters_never_push_the_opponent() -> None:
    sim, mode, owner, opponent = orbit_duel(
        OrbitPower(), inert_power(), opponent_far=False
    )
    radius = mode.powers[0].orbit_radius
    opponent.body.position = (owner.position.x + radius, owner.position.y)
    opponent.body.velocity = (0.0, 0.0)

    for _ in range(300):
        mode.step()
        assert tuple(opponent.velocity) == (0.0, 0.0)
        assert opponent.body.angular_velocity == 0.0


# --- arena safety ---


def test_orbiters_stay_fully_inside_the_arena_in_a_corner() -> None:
    sim = Simulation(SEED)
    mode = PowerBattleMode(sim, powers=[OrbitPower(), inert_power()])
    owner, opponent = sim.balls
    owner.body.position = (sim.arena.left + owner.radius, sim.arena.top + owner.radius)
    owner.body.velocity = (0.0, 0.0)
    opponent.body.position = (sim.arena.right - 150.0, sim.arena.bottom - 150.0)
    opponent.body.velocity = (0.0, 0.0)

    mode.step()
    assert len(orbs_of(sim)) == 3

    for _ in range(300):
        mode.step()
        for orb in orbs_of(sim):
            x, y = orb.position
            assert sim.arena.contains_circle(x, y, orb.radius)


@pytest.mark.parametrize("corner", ["left", "right", "top", "bottom"])
def test_wall_proximity_never_despawns_an_orb(corner: str) -> None:
    sim = Simulation(SEED)
    mode = PowerBattleMode(sim, powers=[OrbitPower(), inert_power()])
    owner, opponent = sim.balls
    arena = sim.arena
    mid = ((arena.left + arena.right) / 2, (arena.top + arena.bottom) / 2)
    spots = {
        "left": (arena.left + owner.radius, mid[1]),
        "right": (arena.right - owner.radius, mid[1]),
        "top": (mid[0], arena.top + owner.radius),
        "bottom": (mid[0], arena.bottom - owner.radius),
    }
    owner.body.position = spots[corner]
    owner.body.velocity = (0.0, 0.0)
    opponent.body.position = (arena.right - 130.0, arena.bottom - 130.0)
    opponent.body.velocity = (0.0, 0.0)

    mode.step()
    for _ in range(240):
        mode.step()
        # Hugging a wall flattens the orbit; it never spends an orb.
        assert len(orbs_of(sim)) == 3


def test_orb_state_stays_finite() -> None:
    sim, mode, owner, _ = orbit_duel()
    owner.body.velocity = (900.0, 620.0)
    while mode.step():
        assert sim.is_state_valid()
        for orb in orbs_of(sim):
            assert math.isfinite(orb.angle)
            assert all(math.isfinite(v) for v in orb.position)


# --- lifecycle ---


def test_expiring_the_power_clears_surviving_orbiters() -> None:
    sim, mode, _, _ = orbit_duel()
    power = mode.powers[0]
    mode.step()
    assert len(orbs_of(sim)) == 3

    while power.active and mode.step():
        pass
    assert not power.active
    assert orbs_of(sim) == []
    assert power.orbs == []
    assert len(sim.space.bodies) == len(sim.balls)


def test_cleanup_is_safe_when_some_orbiters_already_hit() -> None:
    """Three deployed, one spent on the opponent, two retired by expiry."""
    sim, mode, owner, opponent = orbit_duel(
        OrbitPower(), inert_power(), opponent_far=False
    )
    power = mode.powers[0]
    radius = power.orbit_radius
    opponent.body.position = (owner.position.x + radius, owner.position.y)
    opponent.body.velocity = (0.0, 0.0)

    mode.step()
    assert len(orbs_of(sim)) == 3

    while opponent.health == opponent.max_health and mode.step():
        pass
    assert len(orbs_of(sim)) == 2
    # The power still tracks all three; one of them is already retired.
    assert len(power.orbs) == 3
    assert sum(1 for o in power.orbs if o.active) == 2

    # Expiring must retire the survivors and ignore the spent one.
    opponent.body.position = (sim.arena.right - 130.0, sim.arena.bottom - 130.0)
    while power.active and mode.step():
        pass
    assert orbs_of(sim) == []
    assert power.orbs == []
    assert len(sim.space.bodies) == len(sim.balls)


def test_deactivating_twice_is_harmless() -> None:
    sim, mode, _, _ = orbit_duel()
    power = mode.powers[0]
    mode.step()

    assert power.deactivate() is True
    assert power.deactivate() is False
    assert orbs_of(sim) == []
    sim.clear_entities()
    assert sim.dynamic_entities == []


def test_repeated_activations_deploy_fresh_ids() -> None:
    sim, mode, _, opponent = orbit_duel()
    seen: list[int] = []
    while mode.step():
        opponent.health = opponent.max_health
        for orb in orbs_of(sim):
            if orb.entity_id not in seen:
                seen.append(orb.entity_id)

    assert len(seen) >= 6
    assert len(set(seen)) == len(seen)
    assert seen == sorted(seen)
    assert seen[0] == len(sim.balls)


def test_finishing_the_battle_clears_orbiters() -> None:
    sim, mode, _, opponent = orbit_duel()
    mode.step()
    assert len(orbs_of(sim)) == 3

    opponent.health = 0.0
    assert mode.step() is False
    assert mode.finished
    assert sim.dynamic_entities == []
    assert len(sim.space.bodies) == len(sim.balls)


def test_every_finished_orbit_battle_leaves_no_entities() -> None:
    for seed in range(10):
        sim = Simulation(seed)
        mode = PowerBattleMode(sim, powers=["orbit", "orbit"])
        while mode.step():
            assert sim.is_state_valid()
        assert sim.dynamic_entities == []
        assert len(sim.space.bodies) == len(sim.balls)


def test_an_orb_is_not_a_fighter() -> None:
    sim, mode, _, _ = orbit_duel()
    mode.step()
    orb = orbs_of(sim)[0]

    assert orb not in sim.balls
    assert not hasattr(orb, "health")
    assert not hasattr(orb, "power")
    assert not hasattr(orb, "take_damage")


# --- coexistence with the other four powers ---


def test_orbit_battles_against_every_other_power_stay_valid() -> None:
    for other in ("rush", "titan", "pulse", "echo", "orbit"):
        for matchup in (["orbit", other], [other, "orbit"]):
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
def orbit_replay() -> dict:
    return record_battle(SEED, powers=["orbit", "titan"])


def test_replay_stays_at_version_3(orbit_replay: dict) -> None:
    """Python exports final positions, so Orbit needs no new fields."""
    assert orbit_replay["version"] == REPLAY_VERSION == 3


def test_orbit_travels_through_the_generic_entities_list(orbit_replay: dict) -> None:
    assert set(orbit_replay["frames"][0]) == {"tick", "fighters", "entities"}
    owner_color = orbit_replay["fighters"][0]["color"]

    seen = 0
    for frame in orbit_replay["frames"]:
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
            assert entity["type"] == "orbit"
            assert entity["owner_id"] == 0
            assert entity["color"] == owner_color
            assert entity["radius"] == pytest.approx(OrbitPower.ORB_RADIUS)
            assert math.isfinite(entity["x"]) and math.isfinite(entity["y"])
    assert seen > 0


def test_replay_carries_no_orbit_specific_fields(orbit_replay: dict) -> None:
    assert "orbiters" not in orbit_replay
    assert "satellite_positions" not in orbit_replay
    for frame in orbit_replay["frames"][:20]:
        assert not any("orbit" in key.lower() for key in frame)
    for frame in orbit_replay["frames"]:
        for entity in frame["entities"]:
            assert "orbit_angle" not in entity
            assert "orbit_radius" not in entity


def test_replay_shows_orbiters_arriving_three_at_a_time(orbit_replay: dict) -> None:
    frames_by_id: dict[int, list[int]] = {}
    for index, frame in enumerate(orbit_replay["frames"]):
        for entity in frame["entities"]:
            frames_by_id.setdefault(entity["id"], []).append(index)

    assert len(frames_by_id) >= 3
    for indices in frames_by_id.values():
        assert indices == list(range(indices[0], indices[-1] + 1))

    first_frames = sorted(indices[0] for indices in frames_by_id.values())
    assert first_frames[0] == first_frames[1] == first_frames[2]


def test_replay_shows_orbital_motion_around_the_owner(orbit_replay: dict) -> None:
    """The circling is visible in the exported positions, not computed later."""
    expected = orbit_replay["fighters"][0]["radius"] + OrbitPower.ORBIT_EXTRA_DISTANCE
    # An orb is placed relative to the owner before the physics step, and the
    # frame records both after it, so the measured separation swings by up to
    # one tick of owner travel either way. Below the radius it can also be the
    # arena clamp flattening the orbit near a wall.
    tolerance = 12.0
    checked = 0
    turned = 0

    for frame in orbit_replay["frames"]:
        owner = frame["fighters"][0]
        bearings = []
        for entity in frame["entities"]:
            offset = (entity["x"] - owner["x"], entity["y"] - owner["y"])
            distance = math.hypot(*offset)
            # Flattened only where the arena clamp had to intervene.
            assert distance <= expected + tolerance
            bearings.append(math.atan2(offset[1], offset[0]))
        if len(bearings) == 3:
            checked += 1
    assert checked > 0

    # Bearings advance over time for a surviving orb.
    tracks: dict[int, list[tuple[float, float, float, float]]] = {}
    for frame in orbit_replay["frames"]:
        owner = frame["fighters"][0]
        for entity in frame["entities"]:
            tracks.setdefault(entity["id"], []).append(
                (entity["x"], entity["y"], owner["x"], owner["y"])
            )
    for points in tracks.values():
        if len(points) < 10:
            continue
        bearings = [math.atan2(y - oy, x - ox) for x, y, ox, oy in points]
        if any(a != b for a, b in zip(bearings, bearings[1:])):
            turned += 1
    assert turned >= 1


def test_replay_final_frame_holds_no_orbiters(orbit_replay: dict) -> None:
    assert orbit_replay["frames"][-1]["entities"] == []


def test_replay_result_matches_the_battle(orbit_replay: dict) -> None:
    sim = Simulation(SEED)
    mode = PowerBattleMode(sim, powers=["orbit", "titan"])
    while mode.step():
        pass

    result = orbit_replay["result"]
    assert result["finished_tick"] == mode.finished_tick
    assert result["is_draw"] is mode.is_draw
    assert result["winner_id"] == (
        None if mode.winner is None else mode.winner.ball_id
    )
    for fighter, ball in zip(orbit_replay["frames"][-1]["fighters"], sim.balls):
        assert fighter["health"] == pytest.approx(ball.health, abs=1e-3)


def test_orbit_replays_stay_deterministic() -> None:
    assert record_battle(SEED, powers=["orbit", "titan"]) == record_battle(
        SEED, powers=["orbit", "titan"]
    )
    assert record_battle(808, powers=["orbit", "orbit"]) == record_battle(
        808, powers=["orbit", "orbit"]
    )

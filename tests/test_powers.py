"""Phase 3A tests: modular powers, Rush, Titan, replay v2."""

from __future__ import annotations

import math

import pymunk
import pytest

from engine.simulation import PHYSICS_HZ, Simulation
from entities.ball import BALL_MASS, Ball
from modes.power_battle import BATTLE_DURATION_TICKS, PowerBattleMode
from powers import (
    POWER_NAMES,
    Power,
    RushPower,
    TitanPower,
    assign_powers,
    create_power,
    power_class,
)
from replay.exporter import REPLAY_VERSION, record_battle

SEED = 12345


def make_ball(**kwargs) -> Ball:
    defaults = dict(
        ball_id=0,
        name="RED",
        radius=50.0,
        color=(255, 0, 0),
        position=(0.0, 0.0),
        velocity=(300.0, -400.0),
    )
    return Ball(**{**defaults, **kwargs})


def powered_ball(power: Power, **kwargs) -> tuple[Ball, Power]:
    """A detached ball with `power` composed onto it."""
    ball = make_ball(**kwargs)
    power.attach(ball)
    return ball, power


def inert_power() -> Power:
    """A power whose cooldown never becomes ready inside a battle."""
    return Power(initial_delay_ticks=10**9)


def scripted_battle(*specs, seed: int = 1):
    """Two powered fighters on separate lanes that never meet.

    Impacts are irrelevant to power timing, so removing them keeps the timing
    assertions about ticks only.
    """
    sim = Simulation(seed)
    mode = PowerBattleMode(sim, powers=specs)
    a, b = sim.balls
    mid_x = (sim.arena.left + sim.arena.right) / 2
    a.body.position = (mid_x, sim.arena.top + 220)
    a.body.velocity = (900.0, 0.0)
    b.body.position = (mid_x, sim.arena.bottom - 220)
    b.body.velocity = (-900.0, 0.0)
    return sim, mode, a, b


def activation_ticks(sim: Simulation, mode: PowerBattleMode, index: int) -> list[int]:
    """Ticks on which fighter `index`'s power switched on, over a full battle."""
    ticks: list[int] = []
    was_active = False
    while mode.step():
        is_active = mode.powers[index].active
        if is_active and not was_active:
            ticks.append(sim.ticks)
        was_active = is_active
    return ticks


def ram_battle(*specs, seed: int = 5):
    """Fighter 0 charges a stationary fighter 1 from near the left wall."""
    sim = Simulation(seed)
    mode = PowerBattleMode(sim, powers=specs)
    rammer, victim = sim.balls
    mid_y = (sim.arena.top + sim.arena.bottom) / 2
    rammer.body.position = (sim.arena.left + 140, mid_y)
    rammer.body.velocity = (900.0, 0.0)
    victim.body.position = ((sim.arena.left + sim.arena.right) / 2, mid_y)
    victim.body.velocity = (0.0, 0.0)
    return sim, mode, rammer, victim


def run_until_impact(sim: Simulation, mode: PowerBattleMode, settle: int = 60):
    """Step until the first impact lands, then a little longer. Returns it."""
    closing = None
    impact_tick = None
    for _ in range(900):
        if not mode.step():
            break
        if impact_tick is None and sim.impacts:
            impact_tick = sim.ticks
            closing = sim.impacts[0].closing_speed
        elif impact_tick is not None and sim.ticks - impact_tick >= settle:
            break
    assert closing is not None, "no impact was produced"
    return closing


# --- assignment ---


def test_registry_holds_exactly_the_implemented_powers() -> None:
    assert POWER_NAMES == ("rush", "titan", "pulse", "echo", "orbit")
    assert power_class("RUSH ") is RushPower
    assert power_class("titan") is TitanPower


def test_unknown_power_name_is_rejected() -> None:
    with pytest.raises(ValueError):
        power_class("nonesuch")


def test_same_seed_reproduces_the_same_matchup() -> None:
    first = PowerBattleMode(Simulation(SEED)).matchup
    second = PowerBattleMode(Simulation(SEED)).matchup
    assert first == second
    assert all(name in POWER_NAMES for name in first)


def test_assignment_is_not_a_constant_and_covers_both_powers() -> None:
    matchups = {PowerBattleMode(Simulation(seed)).matchup for seed in range(40)}
    assert len(matchups) > 1
    assert {name for matchup in matchups for name in matchup} == set(POWER_NAMES)


def test_assignment_ignores_the_global_random_module() -> None:
    import random

    random.seed(1)
    baseline = PowerBattleMode(Simulation(SEED)).matchup
    random.seed(999)
    random.random()
    assert PowerBattleMode(Simulation(SEED)).matchup == baseline


def test_explicit_power_assignment_wins_over_the_seed() -> None:
    for matchup in (("rush", "titan"), ("titan", "rush"), ("rush", "rush")):
        mode = PowerBattleMode(Simulation(SEED), powers=list(matchup))
        assert mode.matchup == matchup
        for ball, name in zip(mode.sim.balls, matchup):
            assert ball.power_name == name
            assert ball.power is mode.powers[ball.ball_id]


def test_explicit_instances_are_used_verbatim() -> None:
    pinned = RushPower(initial_delay_ticks=7)
    mode = PowerBattleMode(Simulation(SEED), powers=[pinned, TitanPower()])
    assert mode.powers[0] is pinned
    assert pinned.cooldown_remaining_ticks == 7


def test_assignment_rejects_the_wrong_number_of_specs() -> None:
    sim = Simulation(SEED)
    with pytest.raises(ValueError):
        PowerBattleMode(sim, powers=["rush"])
    with pytest.raises(ValueError):
        assign_powers(sim.rng, 2, ["rush", "titan", "rush"])


def test_create_power_without_rng_has_no_initial_delay() -> None:
    assert create_power("titan").cooldown_remaining_ticks == 0


# --- timing (simulation ticks only) ---


def test_timing_constants_are_expressed_in_simulation_ticks() -> None:
    rush, titan = RushPower(), TitanPower()
    assert rush.cooldown_ticks == round(5.0 * PHYSICS_HZ) == 600
    assert rush.duration_ticks == round(1.25 * PHYSICS_HZ) == 150
    assert titan.cooldown_ticks == round(6.0 * PHYSICS_HZ) == 720
    assert titan.duration_ticks == round(1.75 * PHYSICS_HZ) == 210


@pytest.mark.parametrize("name", POWER_NAMES)
def test_activation_ticks_are_a_fixed_simulated_period(name: str) -> None:
    cls = power_class(name)
    sim, mode, _, _ = scripted_battle(cls(), inert_power())
    ticks = activation_ticks(sim, mode, 0)

    period = cls().duration_ticks + cls().cooldown_ticks
    assert ticks[0] == 1
    assert ticks == [1 + period * i for i in range(len(ticks))]
    assert ticks[-1] <= BATTLE_DURATION_TICKS
    assert mode.powers[0].activations == len(ticks) >= 4


def test_active_duration_matches_the_declared_duration() -> None:
    sim, mode, _, _ = scripted_battle(RushPower(), inert_power())
    power = mode.powers[0]

    active_ticks = 0
    for _ in range(power.duration_ticks + power.cooldown_ticks):
        mode.step()
        if power.active:
            active_ticks += 1
    assert active_ticks == power.duration_ticks == 150


def test_initial_delay_shifts_only_the_first_activation() -> None:
    """A delay of N ticks means the first burst lands on tick N."""
    sim, mode, _, _ = scripted_battle(RushPower(initial_delay_ticks=90), inert_power())
    ticks = activation_ticks(sim, mode, 0)
    assert ticks[0] == 90
    assert ticks[1] - ticks[0] == 150 + 600


def test_activation_ticks_are_deterministic_for_a_seed() -> None:
    def schedule() -> list[int]:
        sim = Simulation(SEED)
        mode = PowerBattleMode(sim, powers=["rush", "titan"])
        ticks: list[list[int]] = [[], []]
        was = [False, False]
        while mode.step():
            for i, power in enumerate(mode.powers):
                if power.active and not was[i]:
                    ticks[i].append(sim.ticks)
                was[i] = power.active
        return ticks

    assert schedule() == schedule()


def test_a_dead_fighter_stops_activating() -> None:
    sim, mode, a, b = scripted_battle(RushPower(), RushPower())
    mode.step()
    assert mode.powers[0].activations == 1

    a.health = 0.0
    before = mode.powers[0].activations
    for _ in range(1000):
        if not mode.step():
            break
    assert mode.powers[0].activations == before


# --- Rush ---


def test_rush_activation_scales_speed_and_keeps_direction() -> None:
    ball, power = powered_ball(RushPower())
    before = ball.velocity

    assert power.activate() is True
    assert ball.velocity.length == pytest.approx(
        before.length * RushPower.SPEED_MULTIPLIER
    )
    assert ball.velocity.normalized().x == pytest.approx(before.normalized().x)
    assert ball.velocity.normalized().y == pytest.approx(before.normalized().y)
    assert ball.velocity.angle == pytest.approx(before.angle)


def test_rush_expiry_removes_exactly_its_own_multiplier() -> None:
    ball, power = powered_ball(RushPower())
    before = ball.velocity.length

    power.activate()
    power.deactivate()
    assert ball.velocity.length == pytest.approx(before, rel=1e-12)


def test_rush_does_not_compound_over_repeated_activations() -> None:
    ball, power = powered_ball(RushPower())
    base = ball.velocity.length

    for _ in range(6):
        power.activate()
        assert ball.velocity.length == pytest.approx(
            base * RushPower.SPEED_MULTIPLIER, rel=1e-9
        )
        power.deactivate()
        assert ball.velocity.length == pytest.approx(base, rel=1e-9)

    assert power.activations == 6
    # Nowhere near 1.65 ** 6.
    assert ball.velocity.length < base * RushPower.SPEED_MULTIPLIER


def test_rush_expiry_uses_the_current_velocity_not_the_launch_velocity() -> None:
    """Collisions change direction and speed while Rush is active."""
    ball, power = powered_ball(RushPower())
    power.activate()

    # Stand in for a collision: a completely different velocity.
    ball.body.velocity = (-1200.0, 250.0)
    collided = ball.velocity
    power.deactivate()

    assert ball.velocity.length == pytest.approx(
        collided.length / RushPower.SPEED_MULTIPLIER
    )
    assert ball.velocity.angle == pytest.approx(collided.angle)


def test_rush_cannot_activate_twice_without_expiring() -> None:
    ball, power = powered_ball(RushPower())
    power.activate()
    boosted = ball.velocity.length

    assert power.activate() is False
    assert ball.velocity.length == pytest.approx(boosted)
    assert power.activations == 1


def test_rush_damage_multiplier_applies_only_while_active() -> None:
    ball, power = powered_ball(RushPower())
    assert ball.damage_multiplier == 1.0

    power.activate()
    assert power.damage_multiplier == RushPower.DAMAGE_MULTIPLIER == 1.30
    assert ball.damage_multiplier == 1.30

    power.deactivate()
    assert ball.damage_multiplier == 1.0


def test_rush_leaves_the_radius_alone() -> None:
    ball, power = powered_ball(RushPower())
    power.activate()
    assert ball.radius == ball.base_radius


# --- Titan ---


def expected_moment(ball: Ball) -> float:
    return pymunk.moment_for_circle(ball.body.mass, 0.0, ball.radius)


def test_titan_scales_radius_mass_and_moment() -> None:
    ball, power = powered_ball(TitanPower())
    base_moment = ball.body.moment

    power.activate()
    assert ball.radius == pytest.approx(ball.base_radius * 1.50)
    assert ball.body.mass == pytest.approx(BALL_MASS * 1.75)
    assert ball.shape.radius == pytest.approx(ball.radius)
    assert ball.body.moment == pytest.approx(expected_moment(ball))
    assert math.isfinite(ball.body.moment) and ball.body.moment > base_moment


def test_titan_expiry_restores_the_exact_base_state() -> None:
    ball, power = powered_ball(TitanPower())
    base = (ball.base_radius, ball.base_mass, ball.body.moment)

    power.activate()
    power.deactivate()
    assert ball.radius == base[0]
    assert ball.shape.radius == base[0]
    assert ball.body.mass == base[1]
    assert ball.body.moment == pytest.approx(base[2], rel=1e-12)


def test_titan_does_not_accumulate_over_repeated_activations() -> None:
    ball, power = powered_ball(TitanPower())
    base_radius, base_mass = ball.base_radius, ball.base_mass

    for _ in range(5):
        power.activate()
        # Always 1.5x the base, never 2.25x or 3.375x.
        assert ball.radius == pytest.approx(base_radius * 1.50)
        assert ball.body.mass == pytest.approx(base_mass * 1.75)
        power.deactivate()
        assert ball.radius == base_radius
        assert ball.body.mass == base_mass


def test_titan_damage_multiplier_applies_only_while_active() -> None:
    ball, power = powered_ball(TitanPower())
    assert ball.damage_multiplier == 1.0
    power.activate()
    assert ball.damage_multiplier == TitanPower.DAMAGE_MULTIPLIER == 1.70
    power.deactivate()
    assert ball.damage_multiplier == 1.0


def test_titan_leaves_the_velocity_alone() -> None:
    ball, power = powered_ball(TitanPower())
    before = ball.velocity
    power.activate()
    assert ball.velocity == before


# --- Titan wall safety ---


@pytest.mark.parametrize("wall", ["left", "right", "top", "bottom"])
@pytest.mark.parametrize("overlap", [0.0, 1.0])
def test_titan_growth_stays_inside_the_arena(wall: str, overlap: float) -> None:
    """`overlap` 1.0 starts flush against the wall, 0.0 one base radius away."""
    sim = Simulation(SEED)
    mode = PowerBattleMode(sim, powers=[TitanPower(), inert_power()])
    ball = sim.balls[0]
    arena = sim.arena
    inset = ball.base_radius * (1.0 - overlap)
    mid = ((arena.left + arena.right) / 2, (arena.top + arena.bottom) / 2)

    positions = {
        "left": (arena.left + inset, mid[1]),
        "right": (arena.right - inset, mid[1]),
        "top": (mid[0], arena.top + inset),
        "bottom": (mid[0], arena.bottom - inset),
    }
    ball.body.position = positions[wall]

    assert mode.powers[0].activate() is True
    x, y = ball.position
    assert ball.radius > ball.base_radius
    assert arena.contains_circle(x, y, ball.radius)


def test_titan_growth_far_from_the_walls_does_not_move_the_fighter() -> None:
    sim = Simulation(SEED)
    mode = PowerBattleMode(sim, powers=[TitanPower(), inert_power()])
    ball = sim.balls[0]
    center = ((sim.arena.left + sim.arena.right) / 2, (sim.arena.top + sim.arena.bottom) / 2)
    ball.body.position = center

    mode.powers[0].activate()
    assert tuple(ball.position) == center


def test_titan_battles_stay_physically_valid() -> None:
    for seed in (3, 17, 404):
        sim = Simulation(seed)
        mode = PowerBattleMode(sim, powers=["titan", "titan"])
        while mode.step():
            assert sim.is_state_valid()
        assert mode.finished


# --- combat ---


def test_base_damage_formula_is_untouched_by_powers() -> None:
    sim, mode, rammer, victim = ram_battle(inert_power(), inert_power())
    closing = run_until_impact(sim, mode)

    assert victim.damage_taken == pytest.approx(PowerBattleMode.impact_damage(closing))
    assert rammer.damage_taken == 0.0


def test_attacker_power_multiplies_its_own_impact_damage() -> None:
    sim, mode, rammer, victim = ram_battle(RushPower(initial_delay_ticks=0), inert_power())
    closing = run_until_impact(sim, mode)

    assert rammer.power_active is True
    expected = PowerBattleMode.impact_damage(closing) * RushPower.DAMAGE_MULTIPLIER
    assert victim.damage_taken == pytest.approx(expected)
    assert rammer.damage_dealt == pytest.approx(victim.damage_taken)
    assert rammer.damage_taken == 0.0


def test_victim_power_does_not_amplify_incoming_damage() -> None:
    # The victim starts at rest, so its Rush burst scales a zero velocity and
    # only its multiplier is under test.
    sim, mode, rammer, victim = ram_battle(inert_power(), RushPower(initial_delay_ticks=0))
    closing = run_until_impact(sim, mode)

    assert victim.power_active is True
    assert victim.damage_taken == pytest.approx(PowerBattleMode.impact_damage(closing))


def test_one_impact_still_causes_exactly_one_damage_event_with_powers() -> None:
    sim, mode, rammer, victim = ram_battle(RushPower(initial_delay_ticks=0), inert_power())
    impact_tick = None
    health_after = None

    for _ in range(600):
        if not mode.step():
            break
        if impact_tick is None and sim.impacts:
            impact_tick = sim.ticks
            health_after = victim.health
        elif impact_tick is not None and sim.ticks - impact_tick >= 60:
            break

    assert impact_tick is not None
    assert victim.health == health_after
    assert victim.damage_taken > 0.0


# --- cleanup ---


def test_finishing_the_battle_rolls_back_active_powers() -> None:
    sim, mode, a, b = scripted_battle(RushPower(), TitanPower())
    speed_before = a.velocity.length

    mode.step()
    assert a.power_active and b.power_active
    assert b.radius > b.base_radius

    b.health = 0.0
    assert mode.step() is False
    assert mode.finished

    assert not a.power_active and not b.power_active
    assert a.velocity.length == pytest.approx(speed_before, rel=1e-6)
    assert b.radius == b.base_radius
    assert b.shape.radius == b.base_radius
    assert b.body.mass == b.base_mass


def test_no_new_activations_after_the_battle_is_over() -> None:
    sim, mode, a, b = scripted_battle(RushPower(), TitanPower())
    while mode.step():
        pass
    counts = [power.activations for power in mode.powers]

    for _ in range(500):
        assert mode.step() is False
    assert [power.activations for power in mode.powers] == counts
    assert not any(power.active for power in mode.powers)


def test_every_finished_battle_ends_with_base_physical_state() -> None:
    for seed in range(12):
        sim = Simulation(seed)
        mode = PowerBattleMode(sim)
        while mode.step():
            pass
        for ball in sim.balls:
            assert ball.radius == ball.base_radius
            assert ball.body.mass == ball.base_mass
            assert not ball.power_active


# --- replay v2 ---


@pytest.fixture(scope="module")
def titan_replay() -> dict:
    return record_battle(SEED, powers=["titan", "titan"])


@pytest.fixture(scope="module")
def mixed_replay() -> dict:
    return record_battle(SEED, powers=["rush", "titan"])


def test_replay_is_current_version(mixed_replay: dict) -> None:
    assert mixed_replay["version"] == REPLAY_VERSION == 3


def test_replay_carries_fighter_power_metadata(mixed_replay: dict) -> None:
    powers = [meta["power"] for meta in mixed_replay["fighters"]]
    assert powers == ["rush", "titan"]
    for meta in mixed_replay["fighters"]:
        assert set(meta) == {"id", "name", "color", "radius", "max_health", "power"}


def test_seeded_replay_records_the_assigned_matchup() -> None:
    replay = record_battle(SEED)
    expected = PowerBattleMode(Simulation(SEED)).matchup
    assert tuple(meta["power"] for meta in replay["fighters"]) == expected


def test_every_frame_carries_radius_and_power_state(mixed_replay: dict) -> None:
    base = {meta["id"]: meta["radius"] for meta in mixed_replay["fighters"]}

    for frame in mixed_replay["frames"]:
        for fighter in frame["fighters"]:
            assert set(fighter) == {
                "id",
                "x",
                "y",
                "health",
                "alive",
                "radius",
                "power_active",
                "power_cooldown_remaining",
            }
            assert isinstance(fighter["power_active"], bool)
            assert math.isfinite(fighter["radius"])
            assert fighter["radius"] >= base[fighter["id"]]
            assert fighter["power_cooldown_remaining"] >= 0.0
            if not fighter["power_active"]:
                assert fighter["radius"] == pytest.approx(base[fighter["id"]])


def test_replay_radius_is_dynamic_for_titan(titan_replay: dict) -> None:
    base = [meta["radius"] for meta in titan_replay["fighters"]]
    peak = [0.0, 0.0]
    for frame in titan_replay["frames"]:
        for i, fighter in enumerate(frame["fighters"]):
            peak[i] = max(peak[i], fighter["radius"])

    for grown, start in zip(peak, base):
        assert grown == pytest.approx(start * TitanPower.RADIUS_MULTIPLIER, abs=1e-2)


def test_replay_radius_is_constant_for_rush() -> None:
    replay = record_battle(SEED, powers=["rush", "rush"])
    base = [meta["radius"] for meta in replay["fighters"]]
    for frame in replay["frames"]:
        for i, fighter in enumerate(frame["fighters"]):
            assert fighter["radius"] == pytest.approx(base[i])
    assert any(
        fighter["power_active"]
        for frame in replay["frames"]
        for fighter in frame["fighters"]
    )


def test_replay_power_active_windows_match_the_declared_duration() -> None:
    replay = record_battle(SEED, powers=["rush", "titan"])
    ticks_per_frame = replay["ticks_per_frame"]

    for index, cls in enumerate((RushPower, TitanPower)):
        flags = [frame["fighters"][index]["power_active"] for frame in replay["frames"]]
        windows: list[int] = []
        run = 0
        for flag in flags:
            run = run + 1 if flag else 0
            if run == 1:
                windows.append(1)
            elif run > 1:
                windows[-1] = run
        assert windows, "power never activated"
        # Every completed window is the declared duration, sampled at 60 Hz.
        expected = cls().duration_ticks // ticks_per_frame
        assert all(width == expected for width in windows[:-1])


def test_replay_result_matches_the_battle(mixed_replay: dict) -> None:
    sim = Simulation(SEED)
    mode = PowerBattleMode(sim, powers=["rush", "titan"])
    while mode.step():
        pass

    assert mixed_replay["result"]["finished_tick"] == mode.finished_tick
    assert mixed_replay["result"]["is_draw"] is mode.is_draw
    assert mixed_replay["result"]["winner_id"] == (
        None if mode.winner is None else mode.winner.ball_id
    )
    for fighter, ball in zip(mixed_replay["frames"][-1]["fighters"], sim.balls):
        assert fighter["health"] == pytest.approx(ball.health, abs=1e-3)
        assert fighter["radius"] == pytest.approx(ball.base_radius, abs=1e-3)


def test_replay_export_stays_deterministic() -> None:
    assert record_battle(777) == record_battle(777)
    assert record_battle(777, powers=["rush", "titan"]) == record_battle(
        777, powers=["rush", "titan"]
    )

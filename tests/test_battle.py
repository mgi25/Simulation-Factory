"""Phase 2 tests: health, impact damage, elimination, timer and results."""

from __future__ import annotations

import pytest

from engine.simulation import PHYSICS_HZ, Simulation
from entities.ball import MAX_HEALTH, Ball
from modes.power_battle import (
    BATTLE_DURATION_SECONDS,
    BATTLE_DURATION_TICKS,
    DAMAGE_MAX_PER_IMPACT,
    DAMAGE_MIN_CLOSING_SPEED,
    BattleState,
    PowerBattleMode,
)
from powers import Power


def make_ball(**kwargs) -> Ball:
    defaults = dict(
        ball_id=0,
        name="RED",
        radius=50.0,
        color=(255, 0, 0),
        position=(0.0, 0.0),
        velocity=(0.0, 0.0),
    )
    return Ball(**{**defaults, **kwargs})


def inert_power() -> Power:
    """A power whose cooldown never becomes ready inside a battle.

    These tests script health by hand and assert exact totals, so no power
    may contribute damage of its own. Rush and Titan happened to be harmless
    here because they only matter on impact; Pulse fires across an empty
    arena, so the assumption has to be stated rather than assumed.
    """
    return Power(initial_delay_ticks=10**9)


def non_colliding_battle(seed: int = 1):
    """Both fighters skate horizontally on separate lanes and never meet.

    Lets tests exercise the timer and scripted health without any impacts.
    """
    sim = Simulation(seed)
    mode = PowerBattleMode(sim, powers=[inert_power(), inert_power()])
    a, b = sim.balls
    mid_x = (sim.arena.left + sim.arena.right) / 2
    a.body.position = (mid_x, sim.arena.top + 200)
    a.body.velocity = (900.0, 0.0)
    b.body.position = (mid_x, sim.arena.bottom - 200)
    b.body.velocity = (-900.0, 0.0)
    return sim, mode, a, b


def run_battle(seed: int, powers=None):
    sim = Simulation(seed)
    mode = PowerBattleMode(sim, powers=powers)
    while mode.step():
        pass
    return (
        mode.result_text,
        mode.finished_tick,
        tuple(round(ball.health, 6) for ball in sim.balls),
    )


# --- health ---


def test_fighters_start_at_full_health() -> None:
    sim = Simulation(1)
    assert len(sim.balls) == 2
    for ball in sim.balls:
        assert ball.max_health == 100.0
        assert ball.health == 100.0
        assert ball.alive


def test_take_damage_reduces_health() -> None:
    ball = make_ball()
    assert ball.take_damage(30.0) == pytest.approx(30.0)
    assert ball.health == pytest.approx(MAX_HEALTH - 30.0)
    assert ball.damage_taken == pytest.approx(30.0)
    assert ball.alive


def test_health_never_drops_below_zero_and_eliminates() -> None:
    ball = make_ball()
    applied = ball.take_damage(500.0)
    assert applied == pytest.approx(MAX_HEALTH)
    assert ball.health == 0.0
    assert ball.alive is False


def test_health_is_clamped_to_max() -> None:
    ball = make_ball()
    ball.health = 10_000.0
    assert ball.health == ball.max_health


def test_eliminated_ball_takes_no_further_damage() -> None:
    ball = make_ball()
    ball.take_damage(MAX_HEALTH)
    assert ball.take_damage(25.0) == 0.0
    assert ball.health == 0.0


# --- impact damage formula ---


def test_impact_damage_grows_with_closing_speed() -> None:
    assert PowerBattleMode.impact_damage(0.0) == 0.0
    assert PowerBattleMode.impact_damage(DAMAGE_MIN_CLOSING_SPEED) == 0.0
    assert PowerBattleMode.impact_damage(DAMAGE_MIN_CLOSING_SPEED - 100.0) == 0.0

    weak = PowerBattleMode.impact_damage(DAMAGE_MIN_CLOSING_SPEED + 200.0)
    strong = PowerBattleMode.impact_damage(DAMAGE_MIN_CLOSING_SPEED + 900.0)
    assert 0.0 < weak < strong <= DAMAGE_MAX_PER_IMPACT
    assert PowerBattleMode.impact_damage(100_000.0) == DAMAGE_MAX_PER_IMPACT


def test_one_impact_causes_exactly_one_damage_event() -> None:
    """Sustained contact must not drain health on every 120 Hz tick."""
    sim = Simulation(5)
    mode = PowerBattleMode(sim)
    rammer, victim = sim.balls
    mid_y = (sim.arena.top + sim.arena.bottom) / 2
    # Rammer starts near the left wall, victim waits mid-arena: after the
    # exchange the victim flies far enough that no second impact can land
    # inside the observation window.
    rammer.body.position = (sim.arena.left + 120, mid_y)
    rammer.body.velocity = (900.0, 0.0)
    victim.body.position = ((sim.arena.left + sim.arena.right) / 2, mid_y)
    victim.body.velocity = (0.0, 0.0)

    impact_tick = None
    closing = 0.0
    health_after_impact = None
    for tick in range(600):
        mode.step()
        if impact_tick is None and sim.impacts:
            impact_tick = tick
            closing = sim.impacts[0].closing_speed
            health_after_impact = victim.health
        elif impact_tick is not None and tick - impact_tick >= 60:
            break

    assert impact_tick is not None
    # Health stopped moving the moment the single impact was resolved.
    assert victim.health == health_after_impact
    # Exactly one hit landed, on the ball that was standing still.
    assert victim.damage_taken == pytest.approx(PowerBattleMode.impact_damage(closing))
    assert victim.damage_taken > 0.0
    assert rammer.damage_taken == 0.0


def test_wall_bounces_deal_no_damage() -> None:
    sim, mode, a, b = non_colliding_battle()
    start_vx = a.velocity.x

    bounced = False
    for _ in range(1200):
        mode.step()
        if a.velocity.x * start_vx < 0:
            bounced = True

    assert bounced, "ball never bounced off a wall"
    assert a.health == a.max_health
    assert b.health == b.max_health
    assert mode.state is BattleState.RUNNING


# --- elimination ---


def test_elimination_finishes_battle_and_opponent_wins() -> None:
    sim = Simulation(3)
    mode = PowerBattleMode(sim)
    loser, survivor = sim.balls
    loser.take_damage(loser.max_health)

    assert mode.step() is False
    assert mode.finished
    assert mode.winner is survivor
    assert mode.is_draw is False
    assert mode.result_text == f"WINNER: {survivor.name}"
    assert loser.health == 0.0
    assert loser.alive is False


def test_finished_battle_freezes_and_deals_no_more_damage() -> None:
    sim = Simulation(3)
    mode = PowerBattleMode(sim)
    sim.balls[0].take_damage(MAX_HEALTH)
    mode.step()

    finished_tick = mode.finished_tick
    survivor_health = sim.balls[1].health
    for _ in range(240):
        assert mode.step() is False
    assert mode.advance(1.0) == 0

    assert sim.ticks == finished_tick
    assert sim.balls[1].health == survivor_health


# --- timer, timeout and draw ---


def test_battle_limit_is_35_simulated_seconds() -> None:
    assert BATTLE_DURATION_SECONDS == 35.0
    assert BATTLE_DURATION_TICKS == 35 * PHYSICS_HZ == 4200


def test_timeout_awards_the_higher_health_fighter() -> None:
    sim, mode, a, b = non_colliding_battle()
    a.take_damage(40.0)

    while mode.step():
        pass

    assert sim.ticks == BATTLE_DURATION_TICKS
    assert mode.duration == pytest.approx(BATTLE_DURATION_SECONDS)
    assert mode.remaining == 0.0
    assert mode.winner is b
    assert mode.is_draw is False
    assert a.health == pytest.approx(60.0)
    assert b.health == pytest.approx(100.0)


def test_equal_health_at_timeout_is_a_draw() -> None:
    sim, mode, a, b = non_colliding_battle()
    a.take_damage(25.0)
    b.take_damage(25.0)

    while mode.step():
        pass

    assert sim.ticks == BATTLE_DURATION_TICKS
    assert mode.is_draw is True
    assert mode.winner is None
    assert mode.result_text == "DRAW"


def test_timing_follows_simulated_time_not_render_framerate() -> None:
    """Different frame sizes must produce an identical battle timeline."""
    outcomes = set()
    for frame_seconds in (1 / 60, 1 / 30, 1 / 240):
        sim, mode, a, _ = non_colliding_battle()
        a.take_damage(10.0)
        while not mode.finished:
            mode.advance(frame_seconds)
        outcomes.add((sim.ticks, mode.duration, mode.result_text))

    assert len(outcomes) == 1
    assert outcomes.pop()[0] == BATTLE_DURATION_TICKS


# --- determinism and integration ---


def test_same_seed_reproduces_the_same_battle() -> None:
    for seed in (12345, 777):
        assert run_battle(seed) == run_battle(seed)


def test_real_battle_reaches_a_decision() -> None:
    """A pure collision battle: no power may contribute to the outcome.

    Pinned rather than left to the seed, so which powers happen to exist in
    the registry cannot change what this asserts.
    """
    result, finished_tick, healths = run_battle(
        12345, powers=[inert_power(), inert_power()]
    )
    assert result.startswith("WINNER:")
    assert 0 < finished_tick <= BATTLE_DURATION_TICKS
    assert min(healths) == 0.0
    assert max(healths) > 0.0

"""Phase 1 tests: seeded setup, spawn validity and fixed-timestep stepping."""

from __future__ import annotations

import math

import pytest

from engine.arena import CANVAS_HEIGHT, CANVAS_WIDTH, Arena
from engine.simulation import BALL_COUNT, MAX_TICKS_PER_ADVANCE, PHYSICS_DT, Simulation

# Balls may penetrate a wall by a fraction of a pixel between discrete steps.
CONTAINMENT_TOLERANCE = 2.0

# 10 seconds of simulated time at 120 Hz.
LONG_RUN_TICKS = 1200


def initial_state(seed: int) -> list[tuple[float, ...]]:
    sim = Simulation(seed)
    return [
        (*ball.position, *ball.velocity, ball.radius) for ball in sim.balls
    ]


def test_canvas_is_9_by_16() -> None:
    assert CANVAS_WIDTH / CANVAS_HEIGHT == pytest.approx(9 / 16)


def test_same_seed_reproduces_initial_scenario() -> None:
    assert initial_state(12345) == initial_state(12345)


def test_different_seeds_produce_different_scenarios() -> None:
    states = {tuple(initial_state(seed)) for seed in range(10)}
    assert len(states) == 10


def test_spawns_are_inside_arena_and_not_overlapping() -> None:
    for seed in range(25):
        sim = Simulation(seed)
        assert len(sim.balls) == BALL_COUNT

        for ball in sim.balls:
            x, y = ball.position
            assert sim.arena.contains_circle(x, y, ball.radius)

        first, second = sim.balls
        gap = math.dist(first.position, second.position)
        assert gap > first.radius + second.radius


def test_balls_start_moving() -> None:
    sim = Simulation(777)
    for ball in sim.balls:
        assert ball.velocity.length > 0.0


def test_fixed_step_advance_consumes_whole_ticks() -> None:
    sim = Simulation(1)

    assert sim.advance(PHYSICS_DT * 3) == 3
    assert sim.ticks == 3
    assert sim.elapsed == pytest.approx(PHYSICS_DT * 3)

    # A partial tick is buffered, not stepped.
    assert sim.advance(PHYSICS_DT * 0.4) == 0
    assert sim.ticks == 3

    # A very long frame is capped instead of spiralling.
    assert sim.advance(10.0) == MAX_TICKS_PER_ADVANCE


def test_long_run_stays_valid_and_energetic() -> None:
    sim = Simulation(2024)
    start_speeds = sorted(ball.velocity.length for ball in sim.balls)

    for _ in range(LONG_RUN_TICKS):
        sim.step()
        assert sim.is_state_valid()

    for ball in sim.balls:
        x, y = ball.position
        assert sim.arena.contains_circle(x, y, ball.radius - CONTAINMENT_TOLERANCE)
        assert ball.velocity.length > 0.0

    # Perfectly elastic collisions must not bleed the system dry.
    end_speeds = sorted(ball.velocity.length for ball in sim.balls)
    assert sum(end_speeds) == pytest.approx(sum(start_speeds), rel=0.05)


def test_balls_bounce_off_every_wall() -> None:
    """A ball aimed at each wall in turn reverses the expected axis."""
    arena = Arena.default()
    center = ((arena.left + arena.right) / 2, (arena.top + arena.bottom) / 2)

    for velocity in ((600, 0), (-600, 0), (0, 600), (0, -600)):
        sim = Simulation(0, arena=arena)
        for extra in sim.balls[1:]:
            sim.space.remove(extra.body, extra.shape)
        sim.balls = sim.balls[:1]

        ball = sim.balls[0]
        ball.body.position = center
        ball.body.velocity = velocity

        for _ in range(600):
            sim.step()
            if ball.velocity.dot(velocity) < 0:
                break
        else:
            pytest.fail(f"ball never bounced back from velocity {velocity}")

        assert sim.is_state_valid()


def test_balls_collide_with_each_other() -> None:
    """Two balls aimed at each other exchange momentum."""
    arena = Arena.default()
    sim = Simulation(5, arena=arena)
    mid_y = (arena.top + arena.bottom) / 2
    left, right = sim.balls

    left.body.position = (arena.left + 200, mid_y)
    left.body.velocity = (500, 0)
    right.body.position = (arena.right - 200, mid_y)
    right.body.velocity = (-500, 0)

    for _ in range(240):
        sim.step()
        if left.velocity.x < 0 and right.velocity.x > 0:
            break
    else:
        pytest.fail("balls did not collide with each other")

    assert sim.is_state_valid()

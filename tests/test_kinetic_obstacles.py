"""Phase 5A2 tests: rotating bars, sliding gates and the v6 environment state."""

from __future__ import annotations

import json
import math
from collections import Counter

import pymunk
import pytest

from engine.arena import Arena
from engine.arena_generator import (
    GATE_LONG_MAX,
    GATE_LONG_MIN,
    GATE_SHORT_MAX,
    GATE_SHORT_MIN,
    GATE_SPEEDS,
    GATE_TRAVEL_MAX,
    GATE_TRAVEL_MIN,
    KINETIC_PAIR_CLEARANCE,
    MAX_FIGHTER_RADIUS,
    OBSTACLE_SPAWN_CLEARANCE,
    OBSTACLE_WALL_CLEARANCE,
    ROTOR_LONG_MAX,
    ROTOR_LONG_MIN,
    ROTOR_SHORT_MAX,
    ROTOR_SHORT_MIN,
    ROTOR_SPEEDS,
    generate_layout,
)
from engine.arena_layout import (
    AXIS_X,
    AXIS_Y,
    LAYOUT_CLASSIC,
    LAYOUT_PROCEDURAL,
    MOTION_ROTATE,
    MOTION_SLIDE,
    MOTION_STATIC,
    ArenaLayout,
    ObstacleSpec,
)
from engine.randomizer import BALL_RADIUS_MAX, generate_ball_spawns, make_rng
from engine.simulation import BALL_COUNT, PHYSICS_DT, PHYSICS_HZ, Simulation
from entities.echo_clone import EchoClone
from entities.projectile import Projectile
from modes.power_battle import POWER_WARMUP_TICKS, PowerBattleMode
from powers import EchoPower, OrbitPower, Power
from powers.power import seconds_to_ticks
from replay.exporter import REPLAY_VERSION, record_battle

SEED = 12345
SWEEP_SEEDS = 2000

# Hand-built kinetic obstacles, so a physics test knows exactly what is
# moving at it instead of hunting for a seed that generates the right thing.
ROTOR = ObstacleSpec.rotor(0, 540.0, 900.0, 240.0, 40.0, angular_speed=90.0)
GATE_DOWN = ObstacleSpec.gate(
    0, 540.0, 900.0, 240.0, 45.0, axis=AXIS_Y, distance=300.0, speed=240.0
)
GATE_ACROSS = ObstacleSpec.gate(
    0, 540.0, 900.0, 240.0, 45.0, axis=AXIS_X, distance=300.0, speed=240.0,
    rotation_degrees=90.0,
)
BUMPER = ObstacleSpec.circle(1, 300.0, 500.0, 70.0)
BAR = ObstacleSpec.box(1, 300.0, 500.0, 200.0, 40.0, rotation_degrees=45.0)


def inert_power() -> Power:
    return Power(initial_delay_ticks=10**9)


def pinned(*obstacles: ObstacleSpec) -> ArenaLayout:
    return ArenaLayout(
        layout_id="test-layout",
        layout_type=LAYOUT_PROCEDURAL,
        obstacles=obstacles,
        requested_obstacles=len(obstacles),
    )


def lone_fighter(*obstacles: ObstacleSpec, seed: int = SEED, warm: bool = True):
    """One powerless fighter and the given obstacles, and nothing else."""
    sim = Simulation(seed, arena_layout=pinned(*obstacles))
    mode = PowerBattleMode(sim, powers=(inert_power(), inert_power()))
    for extra in sim.balls[1:]:
        sim.space.remove(extra.body, extra.shape)
    sim.balls = sim.balls[:1]
    ball = sim.balls[0]
    # Parked far from the test lane until a test places it deliberately.
    ball.body.position = (sim.arena.right - 130.0, sim.arena.top + 130.0)
    ball.body.velocity = (0.0, 0.0)
    if warm:
        while sim.ticks < POWER_WARMUP_TICKS - 1:
            mode.step()
    return sim, mode, ball


def transforms(sim: Simulation) -> list[tuple[float, float, float]]:
    return [(*r.position, r.rotation_degrees) for r in sim.kinetic_obstacles]


# --- rotating bar motion ---


def test_a_rotor_turns_by_its_speed_every_tick() -> None:
    sim = Simulation(SEED, arena_layout=pinned(ROTOR))
    rotor = sim.obstacles[0]
    per_tick = ROTOR.angular_speed / PHYSICS_HZ

    assert rotor.rotation_degrees == pytest.approx(0.0)
    previous = rotor.rotation_degrees
    for _ in range(240):
        sim.step()
        assert rotor.rotation_degrees - previous == pytest.approx(per_tick, rel=1e-9)
        previous = rotor.rotation_degrees

    # Two simulated seconds of a 90 deg/s bar is half a turn.
    assert rotor.rotation_degrees == pytest.approx(180.0, abs=1e-6)


def test_a_rotor_turns_the_way_its_sign_says() -> None:
    for speed in (-90.0, 90.0):
        spec = ObstacleSpec.rotor(0, 540.0, 900.0, 240.0, 40.0, angular_speed=speed)
        sim = Simulation(SEED, arena_layout=pinned(spec))
        for _ in range(120):
            sim.step()
        turned = sim.obstacles[0].rotation_degrees
        assert turned == pytest.approx(speed, abs=1e-6)
        assert (turned > 0.0) == (speed > 0.0)


def test_a_rotor_starts_at_its_layout_angle() -> None:
    spec = ObstacleSpec.rotor(
        0, 540.0, 900.0, 240.0, 40.0, angular_speed=60.0, rotation_degrees=45.0
    )
    sim = Simulation(SEED, arena_layout=pinned(spec))
    assert sim.obstacles[0].rotation_degrees == pytest.approx(45.0)
    assert sim.obstacles[0].position == pytest.approx((540.0, 900.0))


def test_a_rotor_pivot_never_moves() -> None:
    sim = Simulation(SEED, arena_layout=pinned(ROTOR))
    rotor = sim.obstacles[0]
    for _ in range(600):
        sim.step()
        assert rotor.position == pytest.approx((ROTOR.x, ROTOR.y), abs=1e-9)


def test_rotor_motion_matches_the_spec_that_describes_it() -> None:
    sim = Simulation(SEED, arena_layout=pinned(ROTOR))
    for _ in range(500):
        sim.step()
        assert sim.obstacles[0].rotation_degrees == pytest.approx(
            ROTOR.rotation_at(sim.elapsed), abs=1e-6
        )


# --- sliding gate motion ---


def test_a_gate_slides_along_its_axis_and_nowhere_else() -> None:
    sim = Simulation(SEED, arena_layout=pinned(GATE_DOWN))
    gate = sim.obstacles[0]
    start = gate.position
    for _ in range(60):
        sim.step()
    assert gate.position[0] == pytest.approx(GATE_DOWN.x, abs=1e-9)
    assert gate.position[1] > start[1]
    assert gate.rotation_degrees == pytest.approx(0.0, abs=1e-9)


def test_a_gate_reverses_at_both_endpoints_without_teleporting() -> None:
    """The whole travel, sampled every tick: continuous, bounded, and it turns."""
    sim = Simulation(SEED, arena_layout=pinned(GATE_DOWN))
    gate = sim.obstacles[0]
    (_, low), (_, high) = GATE_DOWN.slide_endpoints()
    step_limit = GATE_DOWN.slide_speed * PHYSICS_DT

    positions = [gate.position[1]]
    for _ in range(1200):
        sim.step()
        positions.append(gate.position[1])

    assert min(positions) == pytest.approx(low, abs=1.0)
    assert max(positions) == pytest.approx(high, abs=1.0)
    for previous, current in zip(positions, positions[1:]):
        assert low - 1e-6 <= current <= high + 1e-6, "left its own travel"
        # A reversal is a change of direction, never a jump across the arena.
        assert abs(current - previous) <= step_limit + 1e-6

    directions = {
        (current > previous) for previous, current in zip(positions, positions[1:])
        if current != previous
    }
    assert directions == {True, False}, "the gate never turned around"


def test_a_gate_reverses_the_expected_number_of_times() -> None:
    """A 300 px travel at 240 px/s turns every 1.25 s, so 8 times in 10 s."""
    sim = Simulation(SEED, arena_layout=pinned(GATE_DOWN))
    gate = sim.obstacles[0]

    previous = gate.position[1]
    sim.step()
    heading = gate.position[1] - previous
    turns = 0
    for _ in range(PHYSICS_HZ * 10):
        previous = gate.position[1]
        sim.step()
        moved = gate.position[1] - previous
        if moved * heading < 0.0:
            turns += 1
            heading = moved
    assert turns == 8


def test_a_gate_slides_horizontally_too() -> None:
    sim = Simulation(SEED, arena_layout=pinned(GATE_ACROSS))
    gate = sim.obstacles[0]
    seen = []
    for _ in range(600):
        sim.step()
        assert gate.position[1] == pytest.approx(GATE_ACROSS.y, abs=1e-9)
        seen.append(gate.position[0])
    assert max(seen) - min(seen) == pytest.approx(GATE_ACROSS.slide_distance, abs=3.0)


def test_a_gate_phase_shifts_where_it_starts_without_changing_its_path() -> None:
    early = ObstacleSpec.gate(
        0, 540.0, 900.0, 240.0, 45.0, axis=AXIS_Y, distance=300.0, speed=240.0,
        phase=0.0,
    )
    late = ObstacleSpec.gate(
        0, 540.0, 900.0, 240.0, 45.0, axis=AXIS_Y, distance=300.0, speed=240.0,
        phase=0.25,
    )
    assert early.position_at(0.0) != late.position_at(0.0)
    assert early.slide_endpoints() == late.slide_endpoints()
    # Quarter of a there-and-back cycle is half the one-way travel.
    assert late.position_at(0.0)[1] == pytest.approx(early.position_at(0.0)[1] + 150.0)


def test_gate_motion_matches_the_spec_that_describes_it() -> None:
    sim = Simulation(SEED, arena_layout=pinned(GATE_DOWN))
    for _ in range(900):
        sim.step()
        assert sim.obstacles[0].position == pytest.approx(
            GATE_DOWN.position_at(sim.elapsed), abs=1e-6
        )


# --- determinism, and no wall clock anywhere ---


def test_the_same_seed_produces_the_same_motion() -> None:
    def run() -> list[list[tuple[float, float, float]]]:
        sim = Simulation(SEED, arena_mode=LAYOUT_PROCEDURAL)
        history = []
        for _ in range(400):
            sim.step()
            history.append(transforms(sim))
        return history

    assert run() == run()


def test_motion_is_driven_by_ticks_not_by_frame_length() -> None:
    """Feeding time in different sized pieces gives the same physics."""
    stepped = Simulation(SEED, arena_layout=pinned(ROTOR, GATE_ACROSS))
    for _ in range(240):
        stepped.step()

    advanced = Simulation(SEED, arena_layout=pinned(ROTOR, GATE_ACROSS))
    while advanced.ticks < 240:
        advanced.advance(1.0 / 60.0)

    assert advanced.ticks == stepped.ticks == 240
    assert transforms(advanced) == transforms(stepped)


def test_a_layout_can_be_replayed_from_its_spec_alone() -> None:
    """Nothing in the motion depends on state the layout does not carry."""
    sim = Simulation(SEED, arena_mode=LAYOUT_PROCEDURAL)
    if not sim.kinetic_obstacles:
        pytest.skip("this seed generated a static arena")
    for _ in range(600):
        sim.step()
    for runtime in sim.kinetic_obstacles:
        spec = runtime.spec
        assert runtime.position == pytest.approx(spec.position_at(sim.elapsed), abs=1e-6)
        assert runtime.rotation_degrees == pytest.approx(
            spec.rotation_at(sim.elapsed), abs=1e-6
        )


# --- static obstacles did not become kinetic ---


def test_a_static_circle_never_moves() -> None:
    sim = Simulation(SEED, arena_layout=pinned(BUMPER))
    assert sim.kinetic_obstacles == []
    runtime = sim.obstacles[0]
    for _ in range(600):
        sim.step()
    assert runtime.position == (BUMPER.x, BUMPER.y)
    assert runtime.rotation_degrees == 0.0
    assert runtime.body is sim.space.static_body


def test_a_static_bar_never_moves() -> None:
    sim = Simulation(SEED, arena_layout=pinned(BAR))
    assert sim.kinetic_obstacles == []
    runtime = sim.obstacles[0]
    for _ in range(600):
        sim.step()
    assert runtime.position == (BAR.x, BAR.y)
    assert runtime.rotation_degrees == BAR.rotation_degrees
    assert runtime.placed().corners() == BAR.corners()


def test_the_classic_arena_has_nothing_that_moves() -> None:
    sim = Simulation(SEED)
    assert sim.arena_mode == LAYOUT_CLASSIC
    assert sim.obstacles == []
    assert sim.kinetic_obstacles == []
    replay = record_battle(SEED)
    assert all(frame["obstacles"] == [] for frame in replay["frames"])


def test_a_kinetic_obstacle_is_a_kinematic_body() -> None:
    sim = Simulation(SEED, arena_layout=pinned(ROTOR, GATE_ACROSS))
    for runtime in sim.obstacles:
        assert runtime.body.body_type == pymunk.Body.KINEMATIC
        assert runtime.body is not sim.space.static_body
        assert isinstance(runtime.shape, pymunk.Poly)
        assert runtime.shape.sensor is False
        assert runtime.body in sim.space.bodies


# --- physics against fighters ---


def test_a_rotating_bar_pushes_a_resting_fighter() -> None:
    sim, mode, ball = lone_fighter(ROTOR)
    # Below the pivot, inside the sweep circle but clear of the bar at rest.
    ball.body.position = (ROTOR.x, ROTOR.y + 150.0)
    ball.body.velocity = (0.0, 0.0)
    health = ball.health

    moved = False
    for _ in range(400):
        mode.step()
        if ball.velocity.length > 20.0:
            moved = True
            break
    assert moved, "the bar swept through and never touched the fighter"
    assert ball.health == health, "an obstacle dealt damage"
    assert not mode.events, "a harmless obstacle contact recorded an event"
    assert sim.is_state_valid()


def test_a_sliding_gate_pushes_a_resting_fighter() -> None:
    """A resting ball struck head-on by a moving wall leaves at twice its speed.

    That is the whole point of driving the gate with a kinematic body rather
    than teleporting a static one: Chipmunk reads the body's velocity when it
    resolves the contact, so the fighter is shoved the way the gate is going
    and at the speed the elastic solution demands - none of it hand-written.
    """
    sim, mode, ball = lone_fighter(GATE_DOWN)
    gate = sim.obstacles[0]
    ball.body.position = (GATE_DOWN.x, GATE_DOWN.y + 100.0)
    ball.body.velocity = (0.0, 0.0)
    health = ball.health

    heading = 0.0
    for _ in range(400):
        before = gate.position[1]
        mode.step()
        if ball.velocity.length > 20.0:
            heading = gate.position[1] - before
            break
    assert heading != 0.0, "the gate slid through the fighter without moving it"
    assert ball.velocity.x == pytest.approx(0.0, abs=1e-6), "pushed off-axis"
    assert (ball.velocity.y > 0.0) == (heading > 0.0), "pushed against the gate"
    assert abs(ball.velocity.y) == pytest.approx(
        2.0 * GATE_DOWN.slide_speed, rel=0.02
    )
    assert ball.health == health
    assert not mode.events
    assert sim.is_state_valid()


def test_a_kinetic_obstacle_never_damages_a_fighter_over_a_long_run() -> None:
    sim, mode, ball = lone_fighter(ROTOR, GATE_ACROSS)
    ball.body.position = (ROTOR.x - 250.0, ROTOR.y + 60.0)
    ball.body.velocity = (700.0, 240.0)

    for _ in range(2400):
        mode.step()
        assert ball.health == ball.max_health
        assert not mode.events
        assert sim.is_state_valid()


def test_a_growing_titan_stays_stable_against_kinetic_obstacles() -> None:
    sim = Simulation(3, arena_layout=pinned(ROTOR, GATE_ACROSS))
    mode = PowerBattleMode(sim, powers=("titan", "titan"))
    while mode.step():
        assert sim.is_state_valid()
        for ball in sim.balls:
            assert ball.velocity.length < 20_000.0
    assert not sim.dynamic_entities


def test_generated_kinetic_arenas_stay_stable_for_a_whole_battle() -> None:
    checked = 0
    for seed in range(60):
        sim = Simulation(seed, arena_mode=LAYOUT_PROCEDURAL)
        if not sim.kinetic_obstacles:
            continue
        checked += 1
        mode = PowerBattleMode(sim)
        while mode.step():
            assert sim.is_state_valid()
        assert not sim.dynamic_entities, f"seed {seed} leaked entities"
    assert checked >= 20, "too few kinetic arenas in the sample"


# --- physics against power entities ---


def test_a_pulse_bolt_is_blocked_by_a_rotating_bar() -> None:
    sim, mode, _ = lone_fighter(ROTOR)
    bolt = sim.spawn(
        Projectile,
        owner_id=0,
        position=(ROTOR.x - 400.0, ROTOR.y),
        velocity=(1750.0, 0.0),
        radius=16.0,
        color=(255, 0, 0),
        damage=18.0,
        lifetime_ticks=seconds_to_ticks(2.2),
    )
    for _ in range(120):
        mode.step()
        if not bolt.active:
            break
    assert not bolt.active, "the bolt flew through a rotating bar"
    assert bolt.body not in sim.space.bodies
    assert all(ball.health == ball.max_health for ball in sim.balls)
    assert not mode.events


def test_a_pulse_bolt_is_blocked_by_a_sliding_gate() -> None:
    sim, mode, _ = lone_fighter(GATE_ACROSS)
    bolt = sim.spawn(
        Projectile,
        owner_id=0,
        position=(GATE_ACROSS.x, GATE_ACROSS.y - 400.0),
        velocity=(0.0, 1750.0),
        radius=16.0,
        color=(255, 0, 0),
        damage=18.0,
        lifetime_ticks=seconds_to_ticks(2.2),
    )
    for _ in range(120):
        mode.step()
        if not bolt.active:
            break
    assert not bolt.active, "the bolt flew through a sliding gate"
    assert all(ball.health == ball.max_health for ball in sim.balls)


def test_an_echo_clone_rebounds_off_a_rotating_bar_and_survives() -> None:
    sim, mode, _ = lone_fighter(ROTOR)
    clone = sim.spawn(
        EchoClone,
        owner_id=0,
        position=(ROTOR.x - 400.0, ROTOR.y),
        velocity=(EchoPower.CLONE_SPEED, 0.0),
        radius=30.0,
        color=(255, 0, 0),
        damage=EchoPower.CLONE_DAMAGE,
        lifetime_ticks=seconds_to_ticks(4.0),
        mass=EchoPower.CLONE_MASS,
    )
    bounced = False
    for _ in range(300):
        mode.step()
        if clone.velocity.x < 0.0:
            bounced = True
            break
    assert bounced, "the clone never rebounded"
    assert clone.active and clone in sim.dynamic_entities


def test_an_echo_clone_rebounds_off_a_sliding_gate_and_survives() -> None:
    sim, mode, _ = lone_fighter(GATE_ACROSS)
    clone = sim.spawn(
        EchoClone,
        owner_id=0,
        position=(GATE_ACROSS.x, GATE_ACROSS.y - 400.0),
        velocity=(0.0, EchoPower.CLONE_SPEED),
        radius=30.0,
        color=(255, 0, 0),
        damage=EchoPower.CLONE_DAMAGE,
        lifetime_ticks=seconds_to_ticks(4.0),
        mass=EchoPower.CLONE_MASS,
    )
    bounced = False
    for _ in range(300):
        mode.step()
        if clone.velocity.y < 0.0:
            bounced = True
            break
    assert bounced, "the clone never rebounded"
    assert clone.active and clone in sim.dynamic_entities


def test_orbit_stays_numerically_stable_around_kinetic_obstacles() -> None:
    sim = Simulation(SEED, arena_layout=pinned(ROTOR, GATE_ACROSS))
    mode = PowerBattleMode(sim, powers=(OrbitPower(), OrbitPower()))
    seen = 0
    while mode.step():
        seen = max(seen, sum(1 for e in sim.dynamic_entities if e.kind == "orbit"))
        assert sim.is_state_valid()
        for entity in sim.dynamic_entities:
            assert all(math.isfinite(v) for v in entity.position)
    assert seen >= OrbitPower.ORB_COUNT
    assert not sim.dynamic_entities


# --- generation over the whole sweep ---


@pytest.fixture(scope="module")
def arena() -> Arena:
    return Arena.default()


@pytest.fixture(scope="module")
def sweeps(arena: Arena) -> list[tuple[ArenaLayout, list]]:
    result = []
    for seed in range(SWEEP_SEEDS):
        spawns = generate_ball_spawns(make_rng(seed), arena, BALL_COUNT)
        result.append((generate_layout(seed, arena, spawns), spawns))
    return result


def test_every_sweep_stays_inside_the_arena(
    arena: Arena, sweeps: list[tuple[ArenaLayout, list]]
) -> None:
    """A rotor's whole circle and a gate's whole travel are inside the walls."""
    for layout, _ in sweeps:
        for obstacle in layout.kinetic:
            envelope = obstacle.envelope()
            left, top, right, bottom = envelope.bounds()
            assert arena.left <= left and right <= arena.right
            assert arena.top <= top and bottom <= arena.bottom
            assert envelope.clearance_to_bounds(arena) >= OBSTACLE_WALL_CLEARANCE


def test_no_sampled_pose_along_any_motion_leaves_the_arena(
    arena: Arena, sweeps: list[tuple[ArenaLayout, list]]
) -> None:
    """The envelope claim, checked against the motion it is meant to cover."""
    checked = 0
    for layout, _ in sweeps[:200]:
        for obstacle in layout.kinetic:
            for step in range(48):
                pose = obstacle.placed_at(step * 0.25)
                assert pose.clearance_to_bounds(arena) >= OBSTACLE_WALL_CLEARANCE
                checked += 1
    assert checked > 0, "the sample contained no kinetic obstacles"


def test_no_sweep_ever_reaches_a_starting_fighter(
    sweeps: list[tuple[ArenaLayout, list]],
) -> None:
    for layout, spawns in sweeps:
        for obstacle in layout.kinetic:
            envelope = obstacle.envelope()
            for spawn in spawns:
                assert envelope.distance_to_point(spawn.x, spawn.y) >= (
                    MAX_FIGHTER_RADIUS + OBSTACLE_SPAWN_CLEARANCE
                )


def test_no_two_sweeps_ever_meet(sweeps: list[tuple[ArenaLayout, list]]) -> None:
    for layout, _ in sweeps:
        for index, obstacle in enumerate(layout.obstacles):
            for other in layout.obstacles[index + 1 :]:
                if not (obstacle.is_kinetic or other.is_kinetic):
                    continue
                gap = obstacle.envelope().clearance_to(other.envelope())
                assert gap >= KINETIC_PAIR_CLEARANCE
                assert gap > 2.0 * BALL_RADIUS_MAX


def test_every_kinetic_value_is_finite_and_in_range(
    sweeps: list[tuple[ArenaLayout, list]],
) -> None:
    for layout, _ in sweeps:
        for obstacle in layout.kinetic:
            assert all(
                math.isfinite(value)
                for value in (
                    obstacle.x,
                    obstacle.y,
                    obstacle.width,
                    obstacle.height,
                    obstacle.rotation_degrees,
                    obstacle.angular_speed,
                    obstacle.slide_distance,
                    obstacle.slide_speed,
                    obstacle.slide_phase,
                )
            )
            if obstacle.is_rotor:
                assert abs(obstacle.angular_speed) in ROTOR_SPEEDS
                assert ROTOR_LONG_MIN <= obstacle.width <= ROTOR_LONG_MAX
                assert ROTOR_SHORT_MIN <= obstacle.height <= ROTOR_SHORT_MAX
                assert obstacle.slide_axis == ""
                assert obstacle.slide_distance == 0.0
            else:
                assert obstacle.slide_axis in (AXIS_X, AXIS_Y)
                assert obstacle.slide_speed in GATE_SPEEDS
                assert GATE_LONG_MIN <= obstacle.width <= GATE_LONG_MAX
                assert GATE_SHORT_MIN <= obstacle.height <= GATE_SHORT_MAX
                assert GATE_TRAVEL_MIN <= obstacle.slide_distance <= GATE_TRAVEL_MAX
                assert 0.0 <= obstacle.slide_phase < 1.0
                assert obstacle.angular_speed == 0.0
                # A gate slides across its width, never along its length.
                across = AXIS_Y if obstacle.rotation_degrees == 0.0 else AXIS_X
                assert obstacle.slide_axis == across


def test_layouts_mix_still_and_moving_obstacles(
    sweeps: list[tuple[ArenaLayout, list]],
) -> None:
    counts = Counter(len(layout.kinetic) for layout, _ in sweeps)
    total = len(sweeps)
    assert set(counts) <= {0, 1, 2}, "a layout generated three moving obstacles"
    assert 0.25 <= counts[0] / total <= 0.40
    assert 0.45 <= counts[1] / total <= 0.60
    assert 0.10 <= counts[2] / total <= 0.20
    # Something stands still in essentially every arena. A layout is only
    # ever planned with a static piece in it, so the rare exception is one
    # where placement fell back and that piece was the one that did not fit.
    all_kinetic = [
        layout
        for layout, _ in sweeps
        if len(layout) >= 2 and len(layout.kinetic) == len(layout)
    ]
    assert len(all_kinetic) / total <= 0.005
    assert all(layout.fallback for layout in all_kinetic)

    motions = Counter(o.motion for layout, _ in sweeps for o in layout)
    assert motions[MOTION_ROTATE] > 0
    assert motions[MOTION_SLIDE] > 0
    assert motions[MOTION_STATIC] > 0


# --- replay v6 ---


@pytest.fixture(scope="module")
def kinetic_seed() -> int:
    for seed in range(200):
        if Simulation(seed, arena_mode=LAYOUT_PROCEDURAL).kinetic_obstacles:
            return seed
    raise AssertionError("no seed generated a kinetic arena")


@pytest.fixture(scope="module")
def kinetic_replay(kinetic_seed: int) -> dict:
    return record_battle(kinetic_seed, arena_mode=LAYOUT_PROCEDURAL)


def test_the_replay_is_version_6(kinetic_replay: dict) -> None:
    assert kinetic_replay["version"] == REPLAY_VERSION == 6


def test_the_layout_describes_the_motion_once(kinetic_replay: dict) -> None:
    moving = [o for o in kinetic_replay["layout"]["obstacles"] if o["motion"] != MOTION_STATIC]
    assert moving, "this seed should generate a moving obstacle"
    for obstacle in moving:
        assert obstacle["motion"] in (MOTION_ROTATE, MOTION_SLIDE)
        if obstacle["motion"] == MOTION_ROTATE:
            assert obstacle["angular_speed"] != 0.0
        else:
            assert obstacle["slide_axis"] in (AXIS_X, AXIS_Y)
            assert obstacle["slide_distance"] > 0.0
            assert obstacle["slide_speed"] > 0.0


def test_frames_carry_the_transform_of_every_moving_obstacle(
    kinetic_replay: dict,
) -> None:
    layout = {o["id"]: o for o in kinetic_replay["layout"]["obstacles"]}
    moving = {i for i, o in layout.items() if o["motion"] != MOTION_STATIC}

    for frame in kinetic_replay["frames"]:
        assert {state["id"] for state in frame["obstacles"]} == moving
        for state in frame["obstacles"]:
            assert set(state) == {"id", "x", "y", "rotation_degrees"}
            assert all(
                math.isfinite(state[key]) for key in ("x", "y", "rotation_degrees")
            )


def test_frame_transforms_match_the_simulation(kinetic_seed: int, kinetic_replay: dict) -> None:
    """The Godot contract: what the replay says is what Python actually had."""
    sim = Simulation(kinetic_seed, arena_mode=LAYOUT_PROCEDURAL)
    mode = PowerBattleMode(sim)
    ticks_per_frame = kinetic_replay["ticks_per_frame"]

    for frame in kinetic_replay["frames"]:
        while sim.ticks < frame["tick"] and mode.step():
            pass
        assert sim.ticks == frame["tick"]
        by_id = {r.obstacle_id: r for r in sim.kinetic_obstacles}
        for state in frame["obstacles"]:
            runtime = by_id[state["id"]]
            assert state["x"] == pytest.approx(runtime.position[0], abs=1e-3)
            assert state["y"] == pytest.approx(runtime.position[1], abs=1e-3)
            # Exported wrapped into a single turn, so compare it that way.
            assert state["rotation_degrees"] == pytest.approx(
                runtime.rotation_degrees % 360.0, abs=1e-3
            )
            assert 0.0 <= state["rotation_degrees"] < 360.0
    assert ticks_per_frame == 2


def test_a_moving_obstacle_actually_moves_across_the_replay(
    kinetic_replay: dict,
) -> None:
    first = {s["id"]: s for s in kinetic_replay["frames"][0]["obstacles"]}
    seen_change = False
    for frame in kinetic_replay["frames"]:
        for state in frame["obstacles"]:
            start = first[state["id"]]
            if (state["x"], state["y"], state["rotation_degrees"]) != (
                start["x"],
                start["y"],
                start["rotation_degrees"],
            ):
                seen_change = True
    assert seen_change, "nothing in the environment moved"


def test_an_exported_rotor_angle_wraps_within_one_turn() -> None:
    """Which is what makes short-way angle interpolation necessary downstream."""
    replay = record_battle(1, powers=("rush", "titan"), arena_mode=LAYOUT_PROCEDURAL)
    rotors = {
        o["id"] for o in replay["layout"]["obstacles"] if o["motion"] == MOTION_ROTATE
    }
    assert rotors, "seed 1 should generate a rotating bar"

    angles = [
        state["rotation_degrees"]
        for frame in replay["frames"]
        for state in frame["obstacles"]
        if state["id"] in rotors
    ]
    assert all(0.0 <= angle < 360.0 for angle in angles)
    # A bar turning for this long passes the seam at least once, so playback
    # sees a step across it rather than a smooth ramp. Which way the seam is
    # crossed depends on the sign of the bar's speed - this one runs
    # backwards, so its angle steps up from near 0 to near 360.
    steps = [later - earlier for earlier, later in zip(angles, angles[1:])]
    assert any(abs(step) > 180.0 for step in steps), "the exported angle never wrapped"
    # Every other step is the small one a 90 deg/s bar makes in 1/60 s.
    assert all(abs(step) < 2.0 for step in steps if abs(step) <= 180.0)


def test_a_kinetic_replay_is_byte_identical_for_a_seed(kinetic_seed: int) -> None:
    first = record_battle(kinetic_seed, arena_mode=LAYOUT_PROCEDURAL)
    second = record_battle(kinetic_seed, arena_mode=LAYOUT_PROCEDURAL)
    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)

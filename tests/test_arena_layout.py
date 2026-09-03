"""Phase 5A1 tests: arena layout data, the generator and its RNG stream."""

from __future__ import annotations

import math
from collections import Counter

import pytest

from engine.arena import Arena
from engine.arena_generator import (
    BAR_LONG_MAX,
    BAR_LONG_MIN,
    BAR_ROTATIONS,
    BAR_SHORT_MAX,
    BAR_SHORT_MIN,
    BUMPER_RADIUS_MAX,
    BUMPER_RADIUS_MIN,
    MAX_FIGHTER_RADIUS,
    MAX_FIGHTER_RADIUS_SCALE,
    MAX_LAYOUT_ATTEMPTS,
    MAX_PLACEMENT_ATTEMPTS,
    MIN_PASSAGE_WIDTH,
    OBSTACLE_COUNT_CHOICES,
    OBSTACLE_PAIR_CLEARANCE,
    OBSTACLE_SPAWN_CLEARANCE,
    OBSTACLE_WALL_CLEARANCE,
    generate_layout,
    is_layout_valid,
    layout_for_mode,
)
from engine.arena_layout import (
    LAYOUT_CLASSIC,
    LAYOUT_PROCEDURAL,
    OBSTACLE_BOX,
    OBSTACLE_CIRCLE,
    ArenaLayout,
    ObstacleSpec,
)
from engine.randomizer import (
    ARENA_STREAM_SALT,
    BALL_RADIUS_MAX,
    POWER_STREAM_SALT,
    generate_ball_spawns,
    make_arena_rng,
    make_power_rng,
    make_rng,
)
from engine.simulation import BALL_COUNT, Simulation
from modes.power_battle import PowerBattleMode
from powers import POWER_CLASSES

SEED = 12345

# Cheap because no battle has to run: only geometry is produced and checked.
GEOMETRY_SEEDS = 1000
VARIETY_SEEDS = 100


@pytest.fixture(scope="module")
def arena() -> Arena:
    return Arena.default()


def spawns_for(seed: int, arena: Arena):
    """The fighter spawns a simulation with this seed would start from."""
    return generate_ball_spawns(make_rng(seed), arena, BALL_COUNT)


def layout_for(seed: int, arena: Arena) -> ArenaLayout:
    return generate_layout(seed, arena, spawns_for(seed, arena))


@pytest.fixture(scope="module")
def layouts(arena: Arena) -> list[tuple[ArenaLayout, list]]:
    """One generated layout per seed, with the spawns it had to avoid."""
    result = []
    for seed in range(GEOMETRY_SEEDS):
        spawns = spawns_for(seed, arena)
        result.append((generate_layout(seed, arena, spawns), spawns))
    return result


# --- layout data ---


def test_classic_layout_has_no_obstacles() -> None:
    layout = ArenaLayout.classic()
    assert layout.layout_type == LAYOUT_CLASSIC
    assert layout.layout_id == LAYOUT_CLASSIC
    assert layout.obstacles == ()
    assert layout.is_empty
    assert layout.fallback is False
    assert len(layout) == 0


def test_a_layout_is_plain_data_not_physics() -> None:
    """Nothing in a layout may be a Pymunk object."""
    layout = layout_for(SEED, Arena.default())
    for obstacle in layout:
        assert isinstance(obstacle, ObstacleSpec)
        for value in vars(obstacle).values():
            assert isinstance(value, (int, float, str))


def test_circle_spec_carries_only_circle_geometry() -> None:
    spec = ObstacleSpec.circle(3, 100.0, 200.0, 70.0)
    assert (spec.obstacle_id, spec.kind, spec.is_circle) == (3, OBSTACLE_CIRCLE, True)
    assert (spec.x, spec.y, spec.radius) == (100.0, 200.0, 70.0)
    assert (spec.width, spec.height, spec.rotation_degrees) == (0.0, 0.0, 0.0)
    assert spec.corners() == ()
    assert spec.bounds() == (30.0, 130.0, 170.0, 270.0)


def test_box_spec_corners_follow_its_rotation() -> None:
    upright = ObstacleSpec.box(0, 100.0, 100.0, 200.0, 40.0)
    assert upright.bounds() == (0.0, 80.0, 200.0, 120.0)

    turned = ObstacleSpec.box(0, 100.0, 100.0, 200.0, 40.0, rotation_degrees=90.0)
    left, top, right, bottom = turned.bounds()
    assert (right - left, bottom - top) == pytest.approx((40.0, 200.0))

    diagonal = ObstacleSpec.box(0, 100.0, 100.0, 200.0, 40.0, rotation_degrees=45.0)
    span = (200.0 + 40.0) * math.sqrt(0.5)
    left, top, right, bottom = diagonal.bounds()
    assert (right - left, bottom - top) == pytest.approx((span, span))
    # A rotation never moves the centre, and the corners stay on the same
    # circle around it whatever the angle.
    for corner in diagonal.corners():
        assert math.dist(corner, (100.0, 100.0)) == pytest.approx(
            diagonal.bounding_radius
        )


def test_distance_helpers_agree_with_plain_geometry() -> None:
    circle = ObstacleSpec.circle(0, 0.0, 0.0, 50.0)
    assert circle.distance_to_point(80.0, 0.0) == pytest.approx(30.0)
    assert circle.distance_to_point(10.0, 0.0) == 0.0
    assert circle.signed_distance_to_point(10.0, 0.0) == pytest.approx(-40.0)

    box = ObstacleSpec.box(1, 0.0, 0.0, 200.0, 40.0)
    assert box.distance_to_point(150.0, 0.0) == pytest.approx(50.0)
    assert box.distance_to_point(0.0, 40.0) == pytest.approx(20.0)
    assert box.distance_to_point(0.0, 0.0) == 0.0

    # Surface-to-surface, so two shapes 30 apart report 30 either way round.
    far = ObstacleSpec.circle(2, 280.0, 0.0, 30.0)
    assert box.clearance_to(far) == pytest.approx(150.0)
    assert far.clearance_to(box) == pytest.approx(150.0)

    bar = ObstacleSpec.box(3, 400.0, 0.0, 200.0, 40.0)
    assert box.clearance_to(bar) == pytest.approx(200.0)
    assert box.clearance_to(ObstacleSpec.box(4, 100.0, 0.0, 200.0, 40.0)) == 0.0


def test_clearance_to_bounds_measures_the_nearest_wall(arena: Arena) -> None:
    spec = ObstacleSpec.circle(0, arena.left + 200.0, arena.top + 500.0, 60.0)
    assert spec.clearance_to_bounds(arena) == pytest.approx(140.0)
    outside = ObstacleSpec.circle(0, arena.left + 10.0, arena.top + 500.0, 60.0)
    assert outside.clearance_to_bounds(arena) < 0.0


# --- determinism ---


def test_same_seed_produces_identical_obstacle_specs(arena: Arena) -> None:
    for seed in (0, SEED, 999_983):
        assert layout_for(seed, arena) == layout_for(seed, arena)


def test_layout_ids_are_deterministic_and_never_random(arena: Arena) -> None:
    assert layout_for(SEED, arena).layout_id == f"{LAYOUT_PROCEDURAL}-{SEED}"
    assert layout_for(0, arena).layout_id == f"{LAYOUT_PROCEDURAL}-0"


def test_obstacle_ids_are_contiguous_and_unique(
    layouts: list[tuple[ArenaLayout, list]],
) -> None:
    for layout, _ in layouts:
        ids = [obstacle.obstacle_id for obstacle in layout]
        assert ids == list(range(len(layout)))
        assert len(set(ids)) == len(ids)


def test_different_seeds_produce_different_layouts(arena: Arena) -> None:
    distinct = {
        tuple(layout_for(seed, arena).obstacles) for seed in range(VARIETY_SEEDS)
    }
    # Continuous positions and sizes make collisions vanishingly unlikely;
    # anything less than every seed being unique means a stuck stream.
    assert len(distinct) == VARIETY_SEEDS


def test_layout_for_mode_maps_names_to_layouts(arena: Arena) -> None:
    spawns = spawns_for(SEED, arena)
    assert layout_for_mode(LAYOUT_CLASSIC, SEED, arena, spawns) == ArenaLayout.classic()
    assert layout_for_mode(LAYOUT_PROCEDURAL, SEED, arena, spawns) == layout_for(
        SEED, arena
    )
    with pytest.raises(ValueError):
        layout_for_mode("maze", SEED, arena, spawns)


# --- RNG isolation ---


def test_the_arena_stream_is_its_own_salted_stream() -> None:
    assert ARENA_STREAM_SALT != POWER_STREAM_SALT
    draws = [
        [rng(SEED).random() for _ in range(8)]
        for rng in (make_rng, make_power_rng, make_arena_rng)
    ]
    assert len({tuple(sequence) for sequence in draws}) == 3


def test_arena_mode_does_not_move_the_fighters() -> None:
    def start(mode: str) -> list[tuple[float, ...]]:
        sim = Simulation(SEED, arena_mode=mode)
        return [(*ball.position, *ball.velocity, ball.radius) for ball in sim.balls]

    assert start(LAYOUT_CLASSIC) == start(LAYOUT_PROCEDURAL)


def test_arena_generation_consumes_no_spawn_rng(arena: Arena) -> None:
    """The spawn stream is left in the same state whatever arena was built."""
    classic = Simulation(SEED, arena_mode=LAYOUT_CLASSIC)
    procedural = Simulation(SEED, arena_mode=LAYOUT_PROCEDURAL)
    assert classic.rng.getstate() == procedural.rng.getstate()
    assert procedural.layout.obstacles, "this seed should generate obstacles"


def test_arena_mode_does_not_change_the_matchup() -> None:
    for seed in range(40):
        classic = PowerBattleMode(Simulation(seed, arena_mode=LAYOUT_CLASSIC))
        procedural = PowerBattleMode(Simulation(seed, arena_mode=LAYOUT_PROCEDURAL))
        assert classic.matchup == procedural.matchup
        assert [power.cooldown_remaining for power in classic.powers] == [
            power.cooldown_remaining for power in procedural.powers
        ]


def test_a_pinned_layout_also_leaves_the_spawn_stream_alone() -> None:
    pinned = ArenaLayout(
        layout_id="test",
        layout_type=LAYOUT_PROCEDURAL,
        obstacles=(ObstacleSpec.circle(0, 540.0, 960.0, 70.0),),
        requested_obstacles=1,
    )
    sim = Simulation(SEED, arena_layout=pinned)
    assert sim.layout is pinned
    assert sim.rng.getstate() == Simulation(SEED).rng.getstate()


# --- geometry validity, over many layouts ---


def test_every_generated_layout_is_valid(
    arena: Arena, layouts: list[tuple[ArenaLayout, list]]
) -> None:
    for layout, spawns in layouts:
        assert is_layout_valid(layout, arena, spawns), layout.layout_id


def test_every_obstacle_is_finite_and_correctly_sized(
    layouts: list[tuple[ArenaLayout, list]],
) -> None:
    for layout, _ in layouts:
        for obstacle in layout:
            assert obstacle.kind in (OBSTACLE_CIRCLE, OBSTACLE_BOX)
            assert all(
                math.isfinite(value)
                for value in (
                    obstacle.x,
                    obstacle.y,
                    obstacle.radius,
                    obstacle.width,
                    obstacle.height,
                    obstacle.rotation_degrees,
                )
            )
            if obstacle.is_circle:
                assert BUMPER_RADIUS_MIN <= obstacle.radius <= BUMPER_RADIUS_MAX
                assert (obstacle.width, obstacle.height) == (0.0, 0.0)
                assert obstacle.rotation_degrees == 0.0
            else:
                assert BAR_LONG_MIN <= obstacle.width <= BAR_LONG_MAX
                assert BAR_SHORT_MIN <= obstacle.height <= BAR_SHORT_MAX
                assert obstacle.rotation_degrees in BAR_ROTATIONS
                assert obstacle.radius == 0.0


def test_every_obstacle_stays_inside_the_arena(
    arena: Arena, layouts: list[tuple[ArenaLayout, list]]
) -> None:
    for layout, _ in layouts:
        for obstacle in layout:
            left, top, right, bottom = obstacle.bounds()
            assert arena.left <= left and right <= arena.right
            assert arena.top <= top and bottom <= arena.bottom
            assert obstacle.clearance_to_bounds(arena) >= OBSTACLE_WALL_CLEARANCE


def test_no_obstacle_touches_a_starting_fighter(
    layouts: list[tuple[ArenaLayout, list]],
) -> None:
    for layout, spawns in layouts:
        for obstacle in layout:
            for spawn in spawns:
                # Clear of the circle the fighter starts in, and still clear
                # of the one it would occupy fully grown.
                assert obstacle.distance_to_point(spawn.x, spawn.y) >= (
                    MAX_FIGHTER_RADIUS + OBSTACLE_SPAWN_CLEARANCE
                )
                assert obstacle.clearance_to_circle(spawn.x, spawn.y, spawn.radius) > 0.0


def test_obstacles_never_overlap_each_other(
    layouts: list[tuple[ArenaLayout, list]],
) -> None:
    for layout, _ in layouts:
        for index, obstacle in enumerate(layout.obstacles):
            for other in layout.obstacles[index + 1 :]:
                assert obstacle.clearance_to(other) >= OBSTACLE_PAIR_CLEARANCE


def test_every_passage_fits_a_fully_grown_titan(
    arena: Arena, layouts: list[tuple[ArenaLayout, list]]
) -> None:
    """No gap anywhere is narrower than the widest a fighter can ever be."""
    titan_diameter = 2.0 * MAX_FIGHTER_RADIUS
    assert MIN_PASSAGE_WIDTH > titan_diameter
    for layout, _ in layouts:
        for index, obstacle in enumerate(layout.obstacles):
            assert obstacle.clearance_to_bounds(arena) > titan_diameter
            for other in layout.obstacles[index + 1 :]:
                assert obstacle.clearance_to(other) > titan_diameter


def test_the_titan_bound_still_covers_every_power() -> None:
    """The engine's growth bound has to keep up if a power ever exceeds it."""
    for power in POWER_CLASSES.values():
        assert getattr(power, "RADIUS_MULTIPLIER", 1.0) <= MAX_FIGHTER_RADIUS_SCALE
    assert MAX_FIGHTER_RADIUS == pytest.approx(
        BALL_RADIUS_MAX * MAX_FIGHTER_RADIUS_SCALE
    )


# --- retries, fallback and variety ---


def test_generation_is_bounded_and_cannot_hang() -> None:
    assert 0 < MAX_PLACEMENT_ATTEMPTS < 10_000
    assert 0 < MAX_LAYOUT_ATTEMPTS < 1_000


def test_a_reduced_layout_reports_itself_as_a_fallback() -> None:
    full = ArenaLayout(
        layout_id="x", layout_type=LAYOUT_PROCEDURAL, obstacles=(), requested_obstacles=0
    )
    assert full.fallback is False
    reduced = ArenaLayout(
        layout_id="x",
        layout_type=LAYOUT_PROCEDURAL,
        obstacles=(ObstacleSpec.circle(0, 0.0, 0.0, 60.0),),
        requested_obstacles=3,
    )
    assert reduced.fallback is True


def test_an_impossible_arena_falls_back_to_an_empty_layout() -> None:
    """A cramped arena yields a valid, visibly empty layout rather than hanging."""
    tiny = Arena(left=0.0, top=0.0, right=300.0, bottom=300.0)
    layout = generate_layout(SEED, tiny, spawns_for(SEED, Arena.default()))
    assert layout.layout_type == LAYOUT_PROCEDURAL
    assert layout.obstacles == ()
    assert layout.fallback is True
    assert is_layout_valid(layout, tiny, [])


def test_fallback_is_rare_and_never_leaves_an_invalid_layout(
    layouts: list[tuple[ArenaLayout, list]],
) -> None:
    fallbacks = sum(1 for layout, _ in layouts if layout.fallback)
    assert fallbacks / len(layouts) <= 0.02, f"{fallbacks} of {len(layouts)} reduced"
    for layout, _ in layouts:
        assert layout.requested_obstacles in OBSTACLE_COUNT_CHOICES
        assert 0 < len(layout) <= layout.requested_obstacles


def test_layouts_vary_in_shape_and_rotation(arena: Arena) -> None:
    kinds: Counter[str] = Counter()
    rotations: Counter[float] = Counter()
    counts: Counter[int] = Counter()
    for seed in range(VARIETY_SEEDS):
        layout = layout_for(seed, arena)
        counts[len(layout)] += 1
        for obstacle in layout:
            kinds[obstacle.kind] += 1
            if not obstacle.is_circle:
                rotations[obstacle.rotation_degrees] += 1

    assert kinds[OBSTACLE_CIRCLE] > 0 and kinds[OBSTACLE_BOX] > 0
    assert len(counts) > 1, "every layout had the same obstacle count"
    assert set(rotations) == set(BAR_ROTATIONS), "some rotation never appears"


def test_obstacles_are_not_all_stacked_on_the_centre(arena: Arena) -> None:
    """Layouts spread out rather than every seed dropping a disc on the ring."""
    centre = ((arena.left + arena.right) / 2.0, (arena.top + arena.bottom) / 2.0)
    covering = sum(
        1
        for seed in range(VARIETY_SEEDS)
        if any(obstacle.distance_to_point(*centre) == 0.0 for obstacle in layout_for(seed, arena))
    )
    assert covering < VARIETY_SEEDS * 0.5

"""Race V0.1 tests: the physics world, the starting grid and determinism.

The determinism tests are the ones that matter most. A seed that does not
reproduce its race makes every other number in the project unverifiable,
so they check the whole pipeline - grid, course, contacts, jump-pad jitter -
rather than just the initial state.
"""

from __future__ import annotations

import math

import pytest

from race.config import (
    COLLISION_TYPE_RACER,
    GRAVITY,
    JUMP_PAD_COOLDOWN_TICKS,
    MAX_ANGULAR_SPEED,
    MAX_SPEED,
    PHYSICS_HZ,
    RACER_COLORS,
    RACER_COUNT,
    RACER_RADIUS,
    SPACE_DAMPING,
)
from race.course import SLICK, TRACK, Checkpoint, RaceCourse
from race.courses.builder import CourseBuilder
from race.racer import Racer, racer_name
from race.simulation import RaceSimulation, build_grid

# A racer may penetrate a surface by a fraction of a pixel between steps.
CONTAINMENT_TOLERANCE = 3.0


def pad_course() -> RaceCourse:
    """A slick chute onto a jump pad. Isolates the pad from everything else."""
    builder = CourseBuilder("pad", 1000.0, 0.0)
    builder.begin_section("run", 0.0)
    builder.ramp((0.0, 400.0), (1000.0, 400.0), 40.0, TRACK)      # floor
    builder.jump_pad((300.0, 360.0), (500.0, 360.0), 30.0, 0.0, 400.0, 0.0, SLICK)
    builder.checkpoint("start", 100.0, (400.0, 120.0))
    builder.checkpoint("finish", 3000.0, (400.0, 3010.0))
    builder.spawn(400.0, 200.0)
    return builder.finish(4000.0)


def open_course(width: float = 1000.0) -> RaceCourse:
    """A floor and nothing else, for isolating racer-on-racer contact."""
    builder = CourseBuilder("open", width, 0.0)
    builder.begin_section("run", 0.0)
    builder.ramp((0.0, 900.0), (width, 900.0), 40.0, TRACK)
    builder.checkpoint("start", 100.0, (width / 2, 120.0))
    builder.checkpoint("finish", 3000.0, (width / 2, 3010.0))
    for index in range(4):
        builder.spawn(200.0 + index * 200.0, 300.0)
    return builder.finish(4000.0)


def state_of(sim: RaceSimulation) -> list[tuple]:
    return [
        (
            racer.racer_id,
            round(racer.position.x, 9),
            round(racer.position.y, 9),
            round(racer.velocity.x, 9),
            round(racer.velocity.y, 9),
        )
        for racer in sim.racers
    ]


def run_ticks(sim: RaceSimulation, ticks: int) -> None:
    for _ in range(ticks):
        sim.step()


# --- the world --------------------------------------------------------------


def test_the_race_space_has_gravity_unlike_the_duel_space() -> None:
    """The reason a race needs its own space at all."""
    from engine.simulation import Simulation

    race = RaceSimulation(1)
    assert race.space.gravity.y == pytest.approx(GRAVITY)
    assert race.space.gravity.y > 0.0, "y grows downwards, so gravity is positive"
    assert race.space.damping == pytest.approx(SPACE_DAMPING)
    assert Simulation(1).space.gravity == (0.0, 0.0)


def test_racers_start_as_a_full_field_with_distinct_identities() -> None:
    sim = RaceSimulation(7)
    assert len(sim.racers) == RACER_COUNT
    assert [racer.racer_id for racer in sim.racers] == list(range(RACER_COUNT))
    assert len({racer.name for racer in sim.racers}) == RACER_COUNT
    assert len({racer.color for racer in sim.racers}) == RACER_COUNT
    assert all(racer.color in RACER_COLORS for racer in sim.racers)
    assert all(racer.shape.collision_type == COLLISION_TYPE_RACER for racer in sim.racers)


def test_racer_names_are_padded_so_they_sort_like_the_field() -> None:
    assert racer_name(0) == "Racer_01"
    assert racer_name(9) == "Racer_10"
    assert sorted(racer_name(i) for i in range(10))[0] == "Racer_01"


def test_racers_collide_with_each_other() -> None:
    """No shape filter: contact between racers is most of the race."""
    sim = RaceSimulation(3)
    for racer in sim.racers:
        assert racer.shape.filter.group == 0


def test_racer_count_can_be_reduced_for_a_test() -> None:
    sim = RaceSimulation(1, racer_count=3)
    assert len(sim.racers) == 3


def test_grid_needs_enough_slots_for_the_field() -> None:
    with pytest.raises(ValueError, match="spawn slots"):
        build_grid(pad_course(), seed=1, count=4)


def test_grid_assignment_is_a_permutation_of_the_slots() -> None:
    """Every racer gets a real starting position, and no slot is favoured."""
    sim = RaceSimulation(11)
    slots = sorted(racer.spawn_slot for racer in sim.racers)
    assert slots == list(range(RACER_COUNT))


def test_grid_shuffles_between_seeds_but_not_within_one() -> None:
    first = [racer.spawn_slot for racer in RaceSimulation(101).racers]
    again = [racer.spawn_slot for racer in RaceSimulation(101).racers]
    other = [racer.spawn_slot for racer in RaceSimulation(102).racers]
    assert first == again
    assert first != other


def test_spawns_sit_above_the_start_plane() -> None:
    sim = RaceSimulation(5)
    for racer in sim.racers:
        assert racer.position.y < sim.course.start.y
        assert sim.course.progress_at(racer.position.y) < 0.0


def test_spawned_racers_do_not_overlap() -> None:
    for seed in range(20):
        racers = RaceSimulation(seed).racers
        for index, first in enumerate(racers):
            for second in racers[index + 1 :]:
                gap = math.dist(tuple(first.position), tuple(second.position))
                assert gap >= first.radius + second.radius, f"seed {seed}"


# --- the speed cap ----------------------------------------------------------


def test_the_speed_cap_holds_over_a_long_fall() -> None:
    """Without the cap, gravity over a course this tall makes a blur."""
    sim = RaceSimulation(31)
    sim.open_gates()
    for _ in range(PHYSICS_HZ * 8):
        sim.step()
        for racer in sim.racers:
            assert racer.speed <= MAX_SPEED + 1e-6
            assert abs(racer.body.angular_velocity) <= MAX_ANGULAR_SPEED + 1e-6


def test_the_cap_limits_speed_without_changing_direction() -> None:
    sim = RaceSimulation(1, racer_count=1)
    racer = sim.racers[0]
    racer.body.velocity = (3000.0, 4000.0)   # 5000 long, well over the cap
    sim.step()
    assert racer.speed == pytest.approx(MAX_SPEED, rel=1e-3)
    # Direction survives: gravity adds a little downwards, nothing sideways.
    assert racer.velocity.x > 0.0 and racer.velocity.y > 0.0
    assert racer.velocity.y / racer.velocity.x == pytest.approx(4.0 / 3.0, rel=0.05)


# --- the gate ---------------------------------------------------------------


def test_the_gate_holds_the_whole_field() -> None:
    sim = RaceSimulation(13)
    assert not sim.gates_open
    run_ticks(sim, PHYSICS_HZ * 3)
    for racer in sim.racers:
        assert racer.position.y < sim.course.start.y + CONTAINMENT_TOLERANCE
        # Settled rather than motionless: ten racers packed into two rows
        # keep jostling against each other, which is fine - it is two orders
        # of magnitude below racing speed.
        assert racer.speed < 80.0, "the field should have settled on the gate"


def test_opening_the_gate_releases_the_field_and_is_idempotent() -> None:
    sim = RaceSimulation(13)
    run_ticks(sim, PHYSICS_HZ * 3)
    assert sim.open_gates() == 1
    assert sim.gates_open
    assert sim.open_gates() == 0, "opening an open gate does nothing"
    run_ticks(sim, PHYSICS_HZ)
    assert any(racer.position.y > sim.course.start.y for racer in sim.racers)


# --- the jump pad -----------------------------------------------------------


def test_a_jump_pad_launches_a_racer_upwards() -> None:
    sim = RaceSimulation(1, course=pad_course(), racer_count=1)
    racer = sim.racers[0]
    launched = False
    for _ in range(PHYSICS_HZ * 3):
        sim.step()
        if sim.jumps:
            launched = True
            kick = sim.jumps[0]
            assert kick.racer_id == racer.racer_id
            assert kick.impulse[1] < 0.0
            # Applied after the step, so it is on the body by now.
            assert racer.velocity.y < 0.0
            break
    assert launched, "the racer never reached the pad"


def test_a_jump_pad_does_not_fire_again_while_a_racer_rests_on_it() -> None:
    """Otherwise a racer sitting on a pad is launched every single tick."""
    sim = RaceSimulation(1, course=pad_course(), racer_count=1)
    fired = []
    for _ in range(PHYSICS_HZ * 6):
        sim.step()
        for kick in sim.jumps:
            fired.append(kick.tick)
    assert fired, "the pad never fired"
    for earlier, later in zip(fired, fired[1:]):
        assert later - earlier >= JUMP_PAD_COOLDOWN_TICKS


def test_jump_pad_jitter_is_reproducible_and_bounded() -> None:
    course = pad_course()
    pad = course.jump_pads[0]
    # Same seed, same scatter.
    runs = []
    for _ in range(2):
        sim = RaceSimulation(77, course=course, racer_count=1)
        impulses = []
        for _ in range(PHYSICS_HZ * 4):
            sim.step()
            impulses.extend(kick.impulse for kick in sim.jumps)
        runs.append(impulses)
    assert runs[0] == runs[1]
    assert runs[0], "the pad never fired"
    # This pad has zero jitter, so every kick is exactly the nominal one.
    for impulse in runs[0]:
        assert impulse == pytest.approx(pad.impulse)


# --- contact reporting ------------------------------------------------------


def test_racer_contacts_are_reported_with_a_closing_speed() -> None:
    sim = RaceSimulation(1, course=open_course(), racer_count=2)
    a, b = sim.racers
    a.teleport((400.0, 800.0))
    b.teleport((600.0, 800.0))
    a.body.velocity = (600.0, 0.0)
    b.body.velocity = (-600.0, 0.0)
    reported = None
    for _ in range(PHYSICS_HZ):
        sim.step()
        if sim.impacts:
            reported = sim.impacts[0]
            break
    assert reported is not None, "a head-on contact was never reported"
    assert {reported.racer_a, reported.racer_b} == {a.racer_id, b.racer_id}
    assert reported.closing_speed > 900.0


def test_contact_reports_are_cleared_every_tick() -> None:
    sim = RaceSimulation(1, course=open_course(), racer_count=2)
    a, b = sim.racers
    a.teleport((480.0, 800.0))
    b.teleport((540.0, 800.0))
    a.body.velocity = (500.0, 0.0)
    seen = False
    for _ in range(PHYSICS_HZ):
        sim.step()
        if sim.impacts:
            seen = True
            sim.step()
            assert sim.impacts == [], "last tick's contacts must not linger"
            break
    assert seen


def test_spinner_contacts_are_counted() -> None:
    """Cheap evidence that the field actually meets the rotors."""
    sim = RaceSimulation(21)
    sim.open_gates()
    run_ticks(sim, PHYSICS_HZ * 10)
    assert sim.spinner_contacts > 0


# --- determinism ------------------------------------------------------------


def test_same_seed_reproduces_the_starting_grid() -> None:
    assert state_of(RaceSimulation(12345)) == state_of(RaceSimulation(12345))


def test_different_seeds_produce_different_grids() -> None:
    grids = {tuple(state_of(RaceSimulation(seed))) for seed in range(10)}
    assert len(grids) == 10


def test_same_seed_reproduces_a_whole_race_tick_for_tick() -> None:
    """The property the entire project rests on.

    Run far enough to be past the gate, both spinners, the funnel queue and
    the jump pad, so this covers every source of randomness the race has.
    """
    def run(seed: int) -> list[tuple]:
        sim = RaceSimulation(seed)
        sim.open_gates()
        run_ticks(sim, PHYSICS_HZ * 15)
        return state_of(sim)

    assert run(4242) == run(4242)


def test_different_seeds_diverge_by_the_end_of_a_race() -> None:
    def run(seed: int) -> list[tuple]:
        sim = RaceSimulation(seed)
        sim.open_gates()
        run_ticks(sim, PHYSICS_HZ * 12)
        return state_of(sim)

    assert run(4242) != run(4243)


def test_the_three_seed_streams_are_independent() -> None:
    """Salted streams, so one concern cannot shift another."""
    from race.seeds import make_course_rng, make_jitter_rng, make_spawn_rng

    seed = 555
    draws = {
        name: [rng.random() for _ in range(5)]
        for name, rng in (
            ("course", make_course_rng(seed)),
            ("spawn", make_spawn_rng(seed)),
            ("jitter", make_jitter_rng(seed)),
        )
    }
    assert draws["course"] != draws["spawn"] != draws["jitter"]
    assert draws["course"] != draws["jitter"]


# --- validity ---------------------------------------------------------------


def test_a_long_race_keeps_finite_state() -> None:
    sim = RaceSimulation(9)
    sim.open_gates()
    for _ in range(PHYSICS_HZ * 25):
        sim.step()
        assert sim.is_state_valid()


def test_state_is_invalid_once_a_racer_stops_being_a_number() -> None:
    sim = RaceSimulation(1, racer_count=1)
    assert sim.is_state_valid()
    sim.racers[0].body.position = (float("nan"), 0.0)
    assert not sim.is_state_valid()


def test_leaving_the_course_is_not_an_invalid_state() -> None:
    """It is a race event with a defined recovery, not a broken simulation."""
    sim = RaceSimulation(1, racer_count=1)
    sim.racers[0].teleport((-5000.0, -5000.0))
    assert sim.is_state_valid()
    assert sim.course.out_of_bounds(-5000.0, -5000.0)


def test_a_retired_racer_can_be_removed_and_the_race_steps_on() -> None:
    sim = RaceSimulation(1, racer_count=3)
    victim = sim.racers[0]
    victim.remove_from_space()
    victim.remove_from_space()   # idempotent
    run_ticks(sim, 60)
    assert sim.is_state_valid()


def test_a_racer_teleport_comes_to_rest() -> None:
    racer = Racer(0, (100.0, 100.0), RACER_RADIUS)
    racer.body.velocity = (500.0, 500.0)
    racer.body.angular_velocity = 5.0
    racer.teleport((300.0, 400.0))
    assert tuple(racer.position) == (300.0, 400.0)
    assert racer.speed == 0.0
    assert racer.body.angular_velocity == 0.0


def test_a_course_can_be_pinned_instead_of_named() -> None:
    """The escape hatch a test needs to control geometry exactly."""
    course = open_course(width=800.0)
    sim = RaceSimulation(1, course=course, racer_count=2)
    assert sim.course is course
    assert sim.course.width == 800.0


def test_checkpoint_planes_of_a_pinned_course_are_honoured() -> None:
    course = open_course()
    sim = RaceSimulation(1, course=course, racer_count=1)
    assert isinstance(sim.course.checkpoints[0], Checkpoint)
    assert sim.course.finish_y == 3000.0

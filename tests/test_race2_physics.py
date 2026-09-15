"""That the race is honest: deterministic, unpushed, and unscripted.

The brief's physics principles are a list of things that must *not* happen -
no teleporting, no manual reordering, no hidden boosts, no forced finishing
order - and a list of prohibitions is hard to test directly. What is testable
is the small number of properties that make all of them impossible:

    every moving part's pose is a pure function of the tick index
    nothing but `apply_actuators` writes into the world
    the same seed produces the same race, bit for bit
    a different seed produces a different race

The last pair together are what rules out a scripted order: a scripted winner
would be the same marble whatever the seed, and a race with a hidden nudge in
it would not reproduce from its seed alone.
"""

from __future__ import annotations

import pytest

from marble3d.config import DEFAULT_CONFIG

from race2 import courses
from race2.race import Race2, run_race


@pytest.fixture(scope="module")
def course():
    return courses.build("switchyard")


def test_every_actuator_pose_is_a_pure_function_of_the_tick(course):
    """Asked twice at the same tick, and out of order, for the same answer.

    This is what makes a physical trapdoor and four turning wheels admissible
    in a replay at all: nothing in the pose reads a marble position, a rank or
    a wall clock, so a render at a different frame rate draws the blade at the
    angle the physics had it at.
    """
    dt = DEFAULT_CONFIG.physics.dt
    for module in course.machine:
        for actuator in module.local_actuators():
            forward = [actuator.pose_at(tick, dt) for tick in range(0, 900, 37)]
            backward = [
                actuator.pose_at(tick, dt) for tick in reversed(range(0, 900, 37))
            ]
            for a, b in zip(forward, reversed(backward)):
                assert a.position == b.position
                assert a.rotation == b.rotation


def test_the_only_writes_into_the_world_are_actuator_poses(course):
    """`Race2.step` adds bookkeeping to the core loop and no forces.

    Read off the source rather than asserted in prose, because the claim is
    about what the code does and a comment cannot be run. Any of these appearing
    in `race2/race.py` would be a marble being pushed.
    """
    import inspect

    import race2.race as module

    source = inspect.getsource(module)
    for forbidden in (
        "applyExternalForce",
        "apply_force",
        "apply_impulse",
        "resetBasePositionAndOrientation",
        "set_marble",
        "world.move_marble",
    ):
        assert forbidden not in source, f"{forbidden} in race2.race"


def test_the_same_seed_gives_the_same_race(course):
    first, _ = run_race(course, seed=7, duration=24.0)
    second, _ = run_race(courses.build("switchyard"), seed=7, duration=24.0)
    assert [r.to_json() for r in first.racers] == [r.to_json() for r in second.racers]
    assert first.lead_changes == second.lead_changes
    assert first.overtakes == second.overtakes


def test_a_different_seed_gives_a_different_race(course):
    """Not a formality: it is half of "the finishing order is not scripted".

    A course whose winner did not depend on the seed would pass every
    determinism test and be a recording rather than a race.
    """
    orders = set()
    for seed in (7, 8, 9, 10, 11):
        outcome, _ = run_race(course, seed=seed, duration=24.0)
        winner = outcome.winner()
        orders.add(None if winner is None else winner.marble_id)
    assert len(orders) > 1, f"the same marble won every seed: {orders}"


def test_the_start_slot_permutation_depends_on_the_seed(course):
    """Which marble waits in which bay is seeded, and it changes.

    If it did not, "start slot against finish rank" would be measuring marble
    identity and the fairness number would mean nothing.
    """
    layouts = set()
    for seed in (1, 2, 3, 4):
        race = Race2(course, DEFAULT_CONFIG, seed=seed, marble_count=8)
        layouts.add(tuple(race.marbles[key].start_index for key in sorted(race.marbles)))
        race.close()
    assert len(layouts) > 1, layouts


def test_no_finisher_was_ever_outside_its_own_channel(course):
    """A marble that crossed the line never tripped the containment check.

    Race #1 found that its finish deck is wider than its channel and booked
    43 of 90 "escapes" against racers that had already won; the same mistake
    here would make the escape rate meaningless.
    """
    outcome, _ = run_race(course, seed=3, duration=30.0)
    for racer in outcome.racers:
        if racer.finish_order is not None:
            assert racer.lost_at is None, (
                f"m{racer.marble_id} finished {racer.finish_order} and was booked "
                f"{racer.lost_how} at {racer.lost_at}"
            )


def test_energy_does_not_grow_once_the_floor_has_finished_opening(course):
    """The physical check that nothing is being handed free speed.

    Before the release a retracting panel can legitimately do work on a marble,
    so the window starts after it. After that the only inputs are gravity and
    contact, and the total energy of a closed marble run cannot increase.
    """
    race = Race2(course, DEFAULT_CONFIG, seed=5, marble_count=8)
    try:
        settle = race._settle_time
        peak = None
        while race.ticks < 240 * 12:
            race.step()
            if race.elapsed < settle + 0.25:
                continue
            energy = race.energy()
            if peak is None:
                peak = energy
            # A contact solver's impulses are not exactly conservative, so the
            # budget is a tolerance rather than zero; 2% over twelve seconds is
            # far under anything a boost would produce.
            assert energy <= peak * 1.02 + 1.0, (
                f"energy rose from {peak:.1f} to {energy:.1f} at {race.elapsed:.2f} s"
            )
            peak = max(peak, energy)
    finally:
        race.close()

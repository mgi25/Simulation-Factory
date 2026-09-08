"""Racer identity is not tied to a physical start bay.

Section 7 of the V1.9 brief. The frozen V1 start still leaves about 1.2 places
of systematic difference between the eight bays, and that is recorded as a V1
limitation. What must not happen is for a persistent *bay* advantage to become
a persistent *colour* advantage across a series of videos - bay 3 being a
tenth of a place quicker is a curiosity, red winning a third of every race for
a year is a broken product.

The mechanism already exists: `marble3d.seeds.make_order_rng` permutes which
marble id stands in which physical slot, per seed, before the race starts. What
this file does is pin the four properties the brief asks for, because none of
them is obvious from reading the shuffle and each would be invisible if it
broke.
"""

from __future__ import annotations

from collections import Counter

import pytest

from marble3d.config import DEFAULT_CONFIG
from marble3d.seeds import make_order_rng
from marble3d.simulation import MarbleSimulation
from sloped import layout
from sloped.course import sloped_course


def _permutation(seed: int) -> list[int]:
    """Slot index -> marble id, exactly as `MarbleSimulation._spawn` builds it."""
    order = list(range(layout.BAYS))
    make_order_rng(seed).shuffle(order)
    return order


# --- deterministic from the seed -----------------------------------------


def test_the_permutation_is_a_pure_function_of_the_seed():
    for seed in (0, 1, 7, 31, 599, 100000):
        assert _permutation(seed) == _permutation(seed)


def test_it_is_a_permutation_and_not_a_sample():
    """Every marble races exactly once, in exactly one bay."""
    for seed in range(64):
        order = _permutation(seed)
        assert sorted(order) == list(range(layout.BAYS))


def test_consecutive_seeds_do_not_give_the_same_arrangement():
    """Otherwise the decoupling is nominal.

    Not a randomness test - just that the thing varies. If a hundred
    consecutive seeds produced under a dozen distinct arrangements, a video
    series would still show a colour in a bay far more often than one in eight.
    """
    seen = {tuple(_permutation(seed)) for seed in range(100)}
    assert len(seen) > 90


def test_every_marble_reaches_every_bay_over_enough_seeds():
    """The property the brief is actually asking for, measured.

    Over 800 seeds each marble should stand in each of the eight bays about a
    hundred times. A marble that never saw bay 0, or saw it three times as
    often as bay 7, would carry the bay's own bias into its colour.
    """
    counts: dict[int, Counter] = {marble: Counter() for marble in range(layout.BAYS)}
    seeds = 800
    for seed in range(seeds):
        for slot, marble in enumerate(_permutation(seed)):
            counts[marble][slot] += 1
    expected = seeds / layout.BAYS
    for marble, tally in counts.items():
        assert len(tally) == layout.BAYS, marble
        assert min(tally.values()) > 0.6 * expected, (marble, dict(tally))
        assert max(tally.values()) < 1.4 * expected, (marble, dict(tally))


# --- no relationship to race rank ----------------------------------------


def test_the_permutation_is_fixed_before_the_race_starts():
    """It cannot be adaptive, because it is applied at spawn.

    `_spawn` runs in `MarbleSimulation.__init__`, before any tick, so there is
    nothing about the race for it to read. This asserts the consequence rather
    than the line: the arrangement the simulation reports at tick zero is the
    one `make_order_rng` gives, and it does not depend on the marble count or
    on anything the course does.
    """
    machine = sloped_course()
    for seed in (3, 17, 41):
        sim = MarbleSimulation(machine, DEFAULT_CONFIG, seed, layout.BAYS)
        try:
            arrangement = [None] * layout.BAYS
            for marble_id, marble in sim.marbles.items():
                arrangement[marble.start_index] = marble_id
            assert arrangement == _permutation(seed)
        finally:
            sim.close()


def test_the_bay_a_marble_stands_in_is_recorded_per_racer():
    """So a full-race fairness number can be a property of the bay.

    This is what makes section 6's characterisation possible at all: a slot's
    win rate is only a fact about the geometry if the instrument knows which
    slot each racer started in, independently of which marble it was.
    """
    machine = sloped_course()
    sim = MarbleSimulation(machine, DEFAULT_CONFIG, 5, layout.BAYS)
    try:
        slots = sorted(marble.start_index for marble in sim.marbles.values())
        assert slots == list(range(layout.BAYS))
    finally:
        sim.close()


# --- recorded in the replay ----------------------------------------------


def test_the_replay_carries_the_arrangement():
    """Godot colours by marble id, so the replay has to say where each stood.

    Without it a viewer could not tell a bay effect from a colour effect even
    in principle, and neither could a later analysis of a rendered series.
    """
    from marble3d.replay import MarbleInfo

    machine = sloped_course()
    sim = MarbleSimulation(machine, DEFAULT_CONFIG, 11, layout.BAYS)
    try:
        tracks = [
            MarbleInfo(
                marble_id=marble_id,
                radius=DEFAULT_CONFIG.marble.radius,
                mass=DEFAULT_CONFIG.marble.mass,
                start_index=marble.start_index,
            )
            for marble_id, marble in sorted(sim.marbles.items())
        ]
        payload = [track.to_json() for track in tracks]
        assert [row["start_index"] for row in payload] == [
            sim.marbles[marble_id].start_index for marble_id in sorted(sim.marbles)
        ]
        # And the arrangement is recoverable from the replay alone.
        recovered = [None] * layout.BAYS
        for row in payload:
            recovered[row["start_index"]] = row["id"]
        assert recovered == _permutation(11)
    finally:
        sim.close()


def test_the_race_result_carries_the_slot_too():
    from sloped.race import SlopedRace

    machine = sloped_course()
    race = SlopedRace(machine, DEFAULT_CONFIG, 23, layout.BAYS)
    try:
        slots = {result.marble_id: result.start_slot for result in race.results.values()}
        assert sorted(slots.values()) == list(range(layout.BAYS))
        for marble_id, slot in slots.items():
            assert _permutation(23)[slot] == marble_id
    finally:
        race.close()


def test_a_short_field_shuffles_only_the_slots_it_uses():
    """And so a debug run with three marbles is *not* the race's first three.

    Asserted as the behaviour rather than wished away, because it is a real
    property with a real consequence. `MarbleSimulation._spawn` truncates the
    slot list to the marble count and then shuffles `range(len(starts))`, so a
    three-marble field is a permutation of 0..2 and not the first three entries
    of the eight-marble permutation. Anything comparing a short debug run
    against the full race it is debugging has to know that; the production
    races all run eight, where there is only one arrangement per seed.
    """
    machine = sloped_course()
    sim = MarbleSimulation(machine, DEFAULT_CONFIG, 9, 3)
    try:
        arrangement = {marble.start_index: marble_id
                       for marble_id, marble in sim.marbles.items()}
        assert sorted(arrangement) == [0, 1, 2]
        assert sorted(arrangement.values()) == [0, 1, 2]
        short = list(range(3))
        make_order_rng(9).shuffle(short)
        assert [arrangement[slot] for slot in range(3)] == short
        # And it is *not* the eight-marble permutation truncated.
        assert [arrangement[slot] for slot in range(3)] != _permutation(9)[:3]
    finally:
        sim.close()

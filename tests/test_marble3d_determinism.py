"""Determinism, measured rather than claimed.

Section 24 of the brief: *do not claim determinism without measurement*. The
full battery - twenty same-process and twenty cross-process repeats on two
seeds - lives in `tools/marble3d_validate.py --determinism`, because forty
child interpreters is not something to run on every commit. What is here is the
same measurement at a size a test suite can carry, plus the two settings the
result depends on, asserted directly.

The cross-process half is the one that matters. A same-process repeat shares an
allocator, a warm heap and a geometry cache with its predecessor and cannot see
the failure that actually happens - Bullet's broadphase pair ordering depending
on allocation addresses, with an order-dependent solver behind it.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from marble3d.config import DEFAULT_CONFIG
from marble3d.machines import start_bowl_curve
from marble3d.simulation import environment_metadata, simulate

pytest.importorskip("pybullet")

SEED = 7


def run_in_child(seed: int) -> tuple[str, str, str]:
    completed = subprocess.run(
        [sys.executable, "-m", "tools.marble3d_run", "--seed", str(seed), "--digest-only"],
        capture_output=True,
        text=True,
        check=True,
        cwd=os.getcwd(),
        env={**os.environ, "PYTHONPATH": os.getcwd()},
    )
    digest, event_digest, order = completed.stdout.strip().splitlines()[-1].split(" ", 2)
    return digest, event_digest, order


def test_the_same_seed_gives_the_same_run_in_one_process() -> None:
    digests = set()
    events = set()
    orders = set()
    for _ in range(4):
        replay = simulate(seed=SEED, machine=start_bowl_curve())
        digests.add(replay.digest())
        events.add(replay.event_digest())
        orders.add(tuple(replay.summary["finish_order"]))
    assert len(digests) == 1
    assert len(events) == 1
    assert len(orders) == 1


def test_the_same_seed_gives_the_same_run_in_a_fresh_interpreter() -> None:
    """The measurement a same-process repeat cannot make."""
    inside = simulate(seed=SEED, machine=start_bowl_curve())
    results = {run_in_child(SEED) for _ in range(3)}
    assert len(results) == 1
    digest, event_digest, order = next(iter(results))
    assert digest == inside.digest()
    assert event_digest == inside.event_digest()
    assert order == str(inside.summary["finish_order"])


def test_different_seeds_give_different_runs() -> None:
    """Without this, "deterministic" would be satisfied by ignoring the seed."""
    digests = {simulate(seed=seed, machine=start_bowl_curve()).digest() for seed in (7, 11, 19)}
    assert len(digests) == 3


def test_deterministic_overlapping_pairs_is_on_and_stays_on() -> None:
    """The setting the whole result rests on.

    Without it the broadphase pair order depends on allocation addresses and
    the constraint solver is order-dependent, so the same seed gives different
    answers in different processes. The lab established this; a change that
    turned it off would break cross-machine reproducibility months later and in
    a way no unit test would otherwise notice.
    """
    assert DEFAULT_CONFIG.physics.deterministic_overlapping_pairs is True


def test_the_clock_is_computed_from_the_tick_and_never_accumulated() -> None:
    """Twenty seconds is 4800 additions of 1/240, and they do not add up.

    `elapsed = ticks * dt` is exact in the sense that matters: the same tick
    always gives the same instant, so a replay frame lands on a physics tick
    rather than a hair either side of one.
    """
    physics = DEFAULT_CONFIG.physics
    assert physics.ticks_per_replay_frame * 60 == physics.physics_hz
    replay = simulate(seed=SEED, machine=start_bowl_curve(), marble_count=2)
    for index, frame in enumerate(replay.frames[:-1]):
        assert frame.time == pytest.approx(index / replay.replay_fps, abs=1e-12)


def test_a_replay_rate_the_physics_rate_does_not_divide_is_refused() -> None:
    odd = DEFAULT_CONFIG.with_overrides(physics__physics_hz=250)
    with pytest.raises(ValueError, match="not a whole multiple"):
        _ = odd.physics.ticks_per_replay_frame


def test_a_run_records_the_machine_it_was_produced_on() -> None:
    """Section 25: the cross-machine question is open, so record the machine.

    Determinism has only ever been measured on one machine with one locally
    compiled Bullet. The honest thing to do about that is to write down which
    one, so two digests taken on two continents can be compared as evidence
    rather than as a coincidence.
    """
    metadata = environment_metadata()
    for key in ("platform", "machine", "processor", "python", "pybullet_api"):
        assert metadata.get(key), key
    replay = simulate(seed=SEED, machine=start_bowl_curve(), marble_count=2)
    assert replay.environment["platform"] == metadata["platform"]

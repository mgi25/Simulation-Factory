"""Seeded randomness for races, split into independent streams.

Follows the convention `engine.randomizer` established for the duel: one
salt per concern, each deriving its own `random.Random` from the race seed.
The point is insulation. Adding a spinner to the course must not move a
racer's spawn offset, and a jump pad drawing one extra jitter value must not
change the course. Anything that would break same-seed replay if it changed
gets its own stream.
"""

from __future__ import annotations

import random

from engine.randomizer import SEED_MAX, generate_seed, make_rng

__all__ = ["SEED_MAX", "generate_seed", "make_course_rng", "make_spawn_rng", "make_jitter_rng"]

# Distinct from the duel's salts, so the same integer seed describes an
# unrelated race and an unrelated battle rather than correlated ones.
COURSE_STREAM_SALT = 0x2545F491
SPAWN_STREAM_SALT = 0xC2B2AE35
JITTER_STREAM_SALT = 0x165667B1


def _derive(seed: int, salt: int) -> random.Random:
    return make_rng((int(seed) ^ salt) % SEED_MAX)


def make_course_rng(seed: int) -> random.Random:
    """Course construction: spinner start angles and speed variation."""
    return _derive(seed, COURSE_STREAM_SALT)


def make_spawn_rng(seed: int) -> random.Random:
    """Starting grid: which racer takes which slot, and small offsets."""
    return _derive(seed, SPAWN_STREAM_SALT)


def make_jitter_rng(seed: int) -> random.Random:
    """Runtime variation drawn while the race runs, e.g. jump-pad scatter."""
    return _derive(seed, JITTER_STREAM_SALT)

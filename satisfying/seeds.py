"""Seeded starting conditions, split into independent streams.

Follows the convention `marble3d.seeds` set - one salt per concern, each
deriving its own `random.Random` from the run seed - and, like that module,
imports none of the other categories' salts. The same integer here describes an
unrelated run there, on purpose.

Two concerns, so two streams:

**Position.** Where in the middle of the arena the ball is set down.
**Heading.** Which way it is pointing.

They are separate so that changing the release area cannot change the launch
angle, and vice versa. A seed varies nothing else: the speed, the gravity, the
arena and the ball size all come from the config, because a prototype that
answers "does the mechanic work" must vary one thing at a time.

The release area is small - a disc of `RELEASE_RADIUS_FRACTION` of the arena
circumradius about the centre - and that is the whole seeded difference between
two runs. It is enough. A convex polygon with elastic walls is a chaotic
billiard: two balls released a tenth of a unit apart are on opposite sides of
the arena within a few seconds, and `tests/test_tile_escape.py` checks that two
seeds really do diverge rather than assuming it.
"""

from __future__ import annotations

import random

__all__ = [
    "SEED_MAX",
    "RELEASE_RADIUS_FRACTION",
    "generate_seed",
    "make_position_rng",
    "make_heading_rng",
]

SEED_MAX = 2**32

# Distinct from the duel's, the race's and the marble core's salts, so the same
# integer describes an unrelated Category 3 run rather than a correlated one.
POSITION_STREAM_SALT = 0x3F1A77C5
HEADING_STREAM_SALT = 0x6E2B90D3

# The release disc, as a fraction of the arena circumradius. A fifth of the way
# out from the centre: far enough that two seeds start visibly apart, close
# enough that no seed starts against a wall and activates a tile at t=0.
RELEASE_RADIUS_FRACTION = 0.20


def generate_seed() -> int:
    """Pick a fresh seed from the OS entropy source, never the global RNG."""
    return random.SystemRandom().randrange(SEED_MAX)


def _derive(seed: int, salt: int) -> random.Random:
    return random.Random((int(seed) ^ salt) % SEED_MAX)


def make_position_rng(seed: int) -> random.Random:
    """Where in the release disc the ball is set down."""
    return _derive(seed, POSITION_STREAM_SALT)


def make_heading_rng(seed: int) -> random.Random:
    """Which way the ball is pointing when it is let go."""
    return _derive(seed, HEADING_STREAM_SALT)

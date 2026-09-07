"""Seeded variation, split into independent streams.

Follows the convention `engine.randomizer` set for the duel and `race.seeds`
for the race - one salt per concern, each deriving its own `random.Random` from
the run seed - but without importing either, because a physics core that drags
in an arena to draw a random number is a physics core that cannot be lifted out
of this repository.

The point of the split is insulation. Adding a placement tolerance to the
marbles must not change which marble takes which slot, and a future module
drawing a random number must not shift either. Anything that would break
same-seed replay if it changed gets its own stream.

## What a seed actually varies, and why it is so little

Two things: which marble takes which slot in the queue, and a placement
tolerance of a fraction of a millimetre on each one. Nothing else. No entry
speed, no angle, no geometry.

That is not thrift, it is the finding the lab reported and this machine is
built to exploit. Eight marbles released down one chute into one bowl diverge
because a bowl is chaotic - a marble that arrives half a millimetre further out
takes a slightly wider first orbit, meets the next marble a few degrees earlier,
and the two of them are somewhere else entirely by the fourth revolution. A
seed does not need to *arrange* an interesting race; it needs to give the
machine a different initial condition and let the machine do it. If a
half-millimetre placement tolerance did not change the drain order, the machine
would be the thing worth worrying about, and
`tests/test_marble3d_simulation.py` checks that it does.

The tolerance is also physically honest: it is roughly the accuracy with which
a real release mechanism would place a real marble.
"""

from __future__ import annotations

import random

__all__ = [
    "SEED_MAX",
    "generate_seed",
    "make_placement_rng",
    "make_order_rng",
    "PLACEMENT_TOLERANCE",
]

SEED_MAX = 2**32

# Distinct from the duel's and the race's salts, so the same integer describes
# an unrelated marble run rather than a correlated one.
PLACEMENT_STREAM_SALT = 0x5BF03635
ORDER_STREAM_SALT = 0x27D4EB2F

# How far a marble's resting position may differ from nominal, in world units.
# 0.01 wu is 0.4 mm on the toy this models: a release mechanism's tolerance,
# not a physics parameter, and small enough that a marble still starts in
# contact with the chute floor and not overlapping it.
PLACEMENT_TOLERANCE = 0.01


def generate_seed() -> int:
    """Pick a fresh seed from the OS entropy source, never the global RNG."""
    return random.SystemRandom().randrange(SEED_MAX)


def _derive(seed: int, salt: int) -> random.Random:
    return random.Random((int(seed) ^ salt) % SEED_MAX)


def make_placement_rng(seed: int) -> random.Random:
    """The tolerance on where each marble is set down."""
    return _derive(seed, PLACEMENT_STREAM_SALT)


def make_order_rng(seed: int) -> random.Random:
    """Which marble takes which slot in the starting queue."""
    return _derive(seed, ORDER_STREAM_SALT)

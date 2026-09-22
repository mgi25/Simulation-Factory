"""Seeded starting conditions for MUSICAL SHELL ESCAPE, in independent streams.

Category 3 Test #2. Follows the convention `satisfying.seeds` set for Test #1
and `marble3d.seeds` set before that - one salt per concern, each deriving its
own `random.Random` from the run seed - and deliberately does **not** reuse
Test #1's salts. The same integer describes an unrelated run there, on purpose:
a good Test #1 seed carries no information about a good Test #2 seed, and a
shared salt would quietly imply that it did.

Four concerns, so four streams:

**Position.** Where in the middle of the innermost shell the ball is set down.
**Heading.** Which way it is pointing.
**Shell phase.** Each shell's initial rotation angle - and therefore where its
opening starts. This is the single largest source of run-to-run difference:
six independent angles decide whether the first opening is in front of the ball
or a hundred and eighty degrees behind it.
**Shell rate.** A bounded jitter on each shell's angular speed. Without it every
run would share one rotation pattern and the openings of two shells would drift
into and out of alignment at the same times in every run, which is exactly the
kind of hidden structure that makes a "population" of seeds one seed wearing
different hats.

Nothing else in a run is random. The shell radii, the panel counts, the opening
widths, the ball speed, the damage model and the horizon all come from the
config, because a prototype that answers "does the mechanic work" must vary one
thing at a time.
"""

from __future__ import annotations

import random

__all__ = [
    "SEED_MAX",
    "RELEASE_RADIUS_FRACTION",
    "generate_seed",
    "make_position_rng",
    "make_heading_rng",
    "make_shell_phase_rng",
    "make_shell_rate_rng",
]

SEED_MAX = 2**32

# Distinct from Test #1's tile salts, from the duel's and from the races'.
POSITION_STREAM_SALT = 0x51C2A80F
HEADING_STREAM_SALT = 0x2D9E4B31
SHELL_PHASE_STREAM_SALT = 0x7A03E6C9
SHELL_RATE_STREAM_SALT = 0x14B7D25E

# The release disc, as a fraction of the innermost shell's apothem. Kept small
# so no seed starts touching the innermost shell, and so the seeded difference
# between two runs is a heading and a shell phase rather than a head start.
RELEASE_RADIUS_FRACTION = 0.35


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


def make_shell_phase_rng(seed: int) -> random.Random:
    """Each shell's rotation angle at t=0, and so where its opening starts."""
    return _derive(seed, SHELL_PHASE_STREAM_SALT)


def make_shell_rate_rng(seed: int) -> random.Random:
    """The bounded per-shell jitter on angular speed."""
    return _derive(seed, SHELL_RATE_STREAM_SALT)

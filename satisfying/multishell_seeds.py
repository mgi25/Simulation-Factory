"""Seeded starting conditions for MULTIPLYING SHELL ESCAPE, in independent streams.

Category 3 Test #2, redesigned. Follows the convention `satisfying.shell_seeds`
set for the single-ball version and `satisfying.seeds` set for Test #1 - one
salt per concern, each deriving its own `random.Random` from the run seed - and
deliberately does **not** reuse the single-ball salts.

That last point is the whole reason this module exists rather than an import.
The redesign changes the shell count, the opening widths, the break thresholds
and the reproduction rule, so a good single-ball seed carries no information
about a good multiplying seed. Sharing a salt would make seed 9589 start at the
same point with the same heading in both tests and quietly imply a
correspondence that is not there - and the Phase 1/Phase 3 shortlists already
name particular integers, so the implication would be acted on.

Four concerns, so four streams:

**Position.** Where in the middle of the innermost shell the first ball is set
down.
**Heading.** Which way it is pointing.
**Shell phase.** Each shell's initial rotation angle - and therefore where its
openings start. This is the single largest source of run-to-run difference.
**Shell rate.** A bounded jitter on each shell's angular speed, so two shells'
openings do not drift into alignment at the same times in every run.

## What is *not* seeded

Reproduction is not random and has no stream here. When a ball crosses a shell
outward for the first time, the child's angular split is `+spawn_turn` on
even-numbered spawns and `-spawn_turn` on odd-numbered ones, and its distance
ahead of the parent is a fixed ladder resolved by a clearance test. That is
deterministic, exactly balanced over any run with an even spawn count, and -
crucially - it reads nothing about where the openings are, so it cannot steer a
child towards or away from one. A seeded random split would be *less* defensible,
not more: it would put a random number between the physics and the outcome and
make "the child got lucky" a thing the seed decides rather than a thing the
geometry decides.
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

# Distinct from the single-ball shell salts, from Test #1's tile salts, from the
# duel's and from the races'.
POSITION_STREAM_SALT = 0x3E71C05B
HEADING_STREAM_SALT = 0x6B48A9D2
SHELL_PHASE_STREAM_SALT = 0x0CF2573E
SHELL_RATE_STREAM_SALT = 0x59AD84C7

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
    """Where in the release disc the first ball is set down."""
    return _derive(seed, POSITION_STREAM_SALT)


def make_heading_rng(seed: int) -> random.Random:
    """Which way the first ball is pointing when it is let go."""
    return _derive(seed, HEADING_STREAM_SALT)


def make_shell_phase_rng(seed: int) -> random.Random:
    """Each shell's rotation angle at t=0, and so where its openings start."""
    return _derive(seed, SHELL_PHASE_STREAM_SALT)


def make_shell_rate_rng(seed: int) -> random.Random:
    """The bounded per-shell jitter on angular speed."""
    return _derive(seed, SHELL_RATE_STREAM_SALT)

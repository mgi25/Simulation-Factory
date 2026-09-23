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

Five concerns, so five streams:

**Position.** Where in the middle of the innermost shell the two founders are
set down. One draw serves both: they share a radius and sit antipodally on it,
so a single `(r, axis)` pair fixes the pair and neither colour starts nearer
anything than the other.
**Heading.** Which way each founder is pointing. Two independent draws, because
giving the second founder the first one's heading turned by pi would make the
pair exactly point-symmetric - and on an even-panelled shell that is a symmetry
of the lattice, so the two would trace mirror images rather than race.
**Shell phase.** Each shell's initial rotation angle - and therefore where its
openings start. This is the single largest source of run-to-run difference.
**Shell rate.** A bounded jitter on each shell's angular speed, so two shells'
openings do not drift into alignment at the same times in every run.
**Team assignment.** Which founder slot wears which colour. A stream of its own
precisely because it decides nothing physical: the two founders' states are
complete before it is consulted. See `team_parity`.

## What is *not* seeded

The colours are not seeded in any sense that could reach a trajectory. The
`team_assignment` stream is the fifth one above and it produces a permutation of
two labels, applied to states that already exist; nothing downstream of it feeds
back into position, heading, speed or geometry.

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
    "FOUNDER_MIN_RADIUS_FRACTION",
    "generate_seed",
    "make_position_rng",
    "make_heading_rng",
    "make_shell_phase_rng",
    "make_shell_rate_rng",
    "make_team_assignment_rng",
    "team_parity",
]

SEED_MAX = 2**32

# Distinct from the single-ball shell salts, from Test #1's tile salts, from the
# duel's and from the races'.
POSITION_STREAM_SALT = 0x3E71C05B
HEADING_STREAM_SALT = 0x6B48A9D2
SHELL_PHASE_STREAM_SALT = 0x0CF2573E
SHELL_RATE_STREAM_SALT = 0x59AD84C7
# Which physical founder slot wears which colour. A stream of its own because it
# decides nothing physical: the two founders' states are built before it is
# consulted and are not altered by it. See `team_parity`.
TEAM_ASSIGNMENT_STREAM_SALT = 0x27B6E1F4

# The release disc, as a fraction of the innermost shell's apothem. Kept small
# so no seed starts touching the innermost shell, and so the seeded difference
# between two runs is a heading and a shell phase rather than a head start.
RELEASE_RADIUS_FRACTION = 0.35
# The two founders are placed antipodally at one shared radius inside the
# release disc, and this is the smallest that radius may be, as a fraction of
# the disc. It exists so two founders can never be released on top of each
# other: at 0.55 of a 0.35-apothem disc their separation is at least 2.4 world
# units, which is more than two ball diameters at any ball radius this test
# uses. A shared radius is also the whole of "equivalent distance from relevant
# geometry" - neither colour starts nearer a wall than the other.
FOUNDER_MIN_RADIUS_FRACTION = 0.55


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


def make_team_assignment_rng(seed: int) -> random.Random:
    """Which founder slot is team 0. A labelling stream, never a physical one."""
    return _derive(seed, TEAM_ASSIGNMENT_STREAM_SALT)


def team_parity(seed: int) -> int:
    """0 or 1: the offset from founder slot index to team index.

    The two founders' physical states are built from the position and heading
    streams and are *not* built from this. All this decides is which of the two
    finished physical states is called cyan and which is called orange, so no
    arrangement of this bit can give either colour a different starting
    position, speed, radius or distance from a wall.

    It exists because the two slots are not perfectly interchangeable in the
    implementation even though they are in the physics: slot 0 is ball 0, and
    ball id breaks scheduling ties and orders the population list. Those are
    tiny effects, but they are effects, and a fixed slot-to-colour map would
    turn any of them into a permanent colour bias. Flipping the map on a seeded
    coin makes the colour statistics unbiased by construction, and the batch
    reports the per-slot rates as well so the underlying asymmetry is measured
    rather than hidden.
    """
    return make_team_assignment_rng(seed).getrandbits(1)

"""Every tunable number the race uses, in one place.

Distances are logical canvas pixels, times are simulated seconds. The
physics rate is imported rather than redefined so the race and the duel
cannot drift onto different clocks.
"""

from __future__ import annotations

from engine.simulation import PHYSICS_DT, PHYSICS_HZ

__all__ = [
    "PHYSICS_DT",
    "PHYSICS_HZ",
    "RACER_COUNT",
    "GRAVITY",
    "SPACE_DAMPING",
    "MAX_SPEED",
    "MAX_ANGULAR_SPEED",
    "RACER_RADIUS",
    "RACER_MASS",
    "RACER_ELASTICITY",
    "RACER_FRICTION",
    "RACER_COLORS",
    "SPAWN_JITTER_X",
    "SPAWN_JITTER_Y",
    "START_NUDGE",
    "COUNTDOWN_SECONDS",
    "COUNTDOWN_TICKS",
    "FINISH_GRACE_SECONDS",
    "RACE_TIMEOUT_SECONDS",
    "STUCK_SPEED",
    "STUCK_PROGRESS_EPSILON",
    "STUCK_SECONDS",
    "RECOVERY_COOLDOWN_SECONDS",
    "RECOVERY_PENALTY_SECONDS",
    "MAX_RECOVERIES_PER_RACER",
    "LARGE_COLLISION_SPEED",
    "IMPACT_REPORT_COOLDOWN_TICKS",
    "JUMP_PAD_COOLDOWN_TICKS",
    "RANKING_SAMPLE_HZ",
    "COLLISION_TYPE_RACER",
    "COLLISION_TYPE_TRACK",
    "COLLISION_TYPE_JUMP_PAD",
    "COLLISION_TYPE_SPINNER",
    "COLLISION_TYPE_GATE",
]

# --- field ---

RACER_COUNT = 10

# --- world physics ---

# Gravity is strong enough that a stalled racer always resumes, and the
# speed cap - not drag - is what actually governs how fast the field moves.
# That keeps a race readable: without a cap, an open drop turns into a blur
# and the whole field arrives in the same frame.
GRAVITY = 1500.0
# Fraction of velocity a body keeps after one second. Mild: it exists to
# settle jitter in a pile-up, not to slow the race down.
SPACE_DAMPING = 0.96
# The single most consequential number in the race, and it was chosen by
# measurement rather than feel. Sweeping it from 1250 down to 750 over
# thirty seeds moved the winner from a mean of 14.6s to 16.8s and - more
# usefully - lifted the *fastest* race of the batch from 12.9s to 15.2s,
# putting every run inside the 15-25s target instead of most of them. It
# also raised the peak queue in the funnel from 5.1 racers to 5.7 and
# evened out the three ways the jump can end, because a slower field
# arrives closer together. Slower still starts to drag.
MAX_SPEED = 750.0
# Just above the rolling limit for a racer at full speed (v/r = 25 rad/s),
# so it clamps a spin that physics should not have produced without
# interfering with an ordinary roll.
MAX_ANGULAR_SPEED = 26.0

# --- racers ---

# Ten racers at this radius sit five abreast on a 1080-wide canvas with room
# to spare, and two of them cannot quite pass side by side through the
# funnel throat - which is where the congestion comes from.
RACER_RADIUS = 30.0
RACER_MASS = 1.0
# Bouncy enough to scatter off a peg, damped enough to stop bouncing on a
# ramp; enough friction to roll rather than skid.
RACER_ELASTICITY = 0.32
RACER_FRICTION = 0.42

# Ten hues a viewer can tell apart at Shorts scale, in racer order.
RACER_COLORS: tuple[tuple[int, int, int], ...] = (
    (235, 72, 72),      # 01 red
    (64, 156, 248),     # 02 blue
    (96, 214, 128),     # 03 green
    (246, 196, 64),     # 04 gold
    (198, 108, 246),    # 05 violet
    (255, 141, 58),     # 06 orange
    (72, 226, 224),     # 07 cyan
    (245, 122, 186),     # 08 pink
    (176, 186, 200),    # 09 silver
    (140, 200, 70),     # 10 lime
)

# --- starting grid ---

# Seeded offsets applied to a grid slot. Small enough that no two racers can
# start in contact whichever way both are nudged, large enough that the
# opening tick is not identical for every seed.
SPAWN_JITTER_X = 20.0
SPAWN_JITTER_Y = 14.0
# A few pixels a second sideways on the first tick, so ten racers resting on
# a gate do not all leave it in perfect formation.
START_NUDGE = 8.0

# --- race clock ---

COUNTDOWN_SECONDS = 3.0
COUNTDOWN_TICKS = int(round(COUNTDOWN_SECONDS * PHYSICS_HZ))
# How long the race keeps running after the winner crosses, so the pack
# behind still gets its finish order recorded. Measured rather than guessed:
# over thirty seeds this is what brings the average field home at 8.8 of 10
# while keeping the longest whole race inside 25 seconds. Shorter loses most
# of the results table (5.4 of 10 at 3.5s), longer only collects stragglers
# and pushes the total past the target length.
FINISH_GRACE_SECONDS = 6.5
# Hard stop. A race that hits this is a failed race, and the telemetry says
# so rather than the run hanging.
RACE_TIMEOUT_SECONDS = 70.0

# --- stuck detection and recovery ---

STUCK_SPEED = 40.0
# Course progress, in checkpoint units, that counts as "meaningful".
STUCK_PROGRESS_EPSILON = 0.01
# Long enough to sit out a legitimate queue. A racer waiting its turn in the
# funnel basin is barely moving and making no progress for seconds at a
# time, and it is not stuck - it is racing. Anything shorter than this
# rescues racers out of the one obstacle that is supposed to hold them up,
# which would be both wrong and unfair. Any jostle resets the count, so a
# racer has to be genuinely still for the whole window.
STUCK_SECONDS = 3.5
# A recovered racer is left alone for this long, so one bad spot cannot
# produce a burst of recoveries on the same tick range.
RECOVERY_COOLDOWN_SECONDS = 2.0
# Recorded against the racer's finish time: recovery is a rescue, not a
# shortcut, and it has to cost something even when the geometry was at fault.
RECOVERY_PENALTY_SECONDS = 1.5
# After this many rescues a racer is retired instead. Prevents a racer
# trapped in genuinely broken geometry from recovering forever.
MAX_RECOVERIES_PER_RACER = 4

# --- telemetry thresholds ---

LARGE_COLLISION_SPEED = 620.0
IMPACT_REPORT_COOLDOWN_TICKS = 10
JUMP_PAD_COOLDOWN_TICKS = 36
# Rankings are compared at this rate to count overtakes and leader changes.
# Every tick would count the same swap several times as two racers trade
# places inside one contact.
RANKING_SAMPLE_HZ = 12

# --- collision types ---
# Continues past the duel's 1-4 so a stray import can never make a race
# shape look like a fight shape.

COLLISION_TYPE_RACER = 10
COLLISION_TYPE_TRACK = 11
COLLISION_TYPE_JUMP_PAD = 12
COLLISION_TYPE_SPINNER = 13
COLLISION_TYPE_GATE = 14

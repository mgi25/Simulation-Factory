"""Contact materials, and the arithmetic that turns a wanted pair into two bodies.

Bullet does not let a pair of materials be specified. Every body carries one
friction and one restitution, and when two bodies touch the solver **multiplies**
them:

    mu_pair = clamp(mu_a * mu_b, 0, 10)
    e_pair  = e_a * e_b

That is a fact about `btManifoldResult::calculateCombinedFriction` and
`calculateCombinedRestitution`, and it is the fourth of the four bugs the
physics lab spent its time on. Setting both the marble and the bowl to the
benchmark's 0.15 gives a pair coefficient of 0.0225 against a wall that needs
0.230 to sustain rolling, so every marble skidded the whole way down - and
"marbles skid" reads as a finding about rigid-body physics rather than as an
arithmetic mistake. It is also engine-specific: Jolt combines as sqrt(a*b), so
the numbers that produce a given coefficient are different in the two engines
and a value copied between them is silently wrong.

So a marble machine states what it wants for each *pair* - marble on marble,
marble on track - and this module solves for the two per-body values that
produce them:

    mu_marble  = sqrt(mu_marble_marble)
    mu_surface = mu_marble_surface / mu_marble

Every static and kinematic collider in the machine gets `mu_surface`, so
"marble on track" means one thing everywhere. If a module ever needs a
different surface - a slick section, a grippy brake - it gets its own solved
value through `surface_for`, not a number typed into the module.

## Verified rather than assumed

`tests/test_marble3d_friction.py` does not check that these numbers are what
this module returns. It puts a marble on an incline in a real Bullet world and
measures its acceleration, which is `(5/7) g sin(theta)` if it rolls and
`g (sin(theta) - mu cos(theta))` if it slides, and recovers `mu` from the
second. That is the only way to know what the engine is doing, and section 11
of the brief asks for exactly it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from marble3d.config import MarbleConfig

__all__ = [
    "BodyMaterial",
    "SolvedMaterials",
    "solve_materials",
    "rolling_threshold",
    "rolling_acceleration",
    "sliding_acceleration",
    "combine",
]

# Bullet clamps a combined friction coefficient here. Far above anything a
# marble machine wants, but a solved surface value can climb if a caller asks
# for a very low marble-on-marble figure with a high marble-on-track one, and
# hitting the clamp silently would put the machine back where the lab started.
MAX_COMBINED_FRICTION = 10.0


def combine(a: float, b: float) -> float:
    """Bullet's own combine rule, so tests can state the expectation once."""
    return min(a * b, MAX_COMBINED_FRICTION)


@dataclass(frozen=True)
class BodyMaterial:
    """What actually goes on one body through `changeDynamics`."""

    friction: float
    restitution: float
    rolling_friction: float
    spinning_friction: float

    def to_json(self) -> dict[str, Any]:
        return {
            "friction": self.friction,
            "restitution": self.restitution,
            "rolling_friction": self.rolling_friction,
            "spinning_friction": self.spinning_friction,
        }


@dataclass(frozen=True)
class SolvedMaterials:
    """The two body materials, plus what they are meant to produce.

    `wanted` is carried alongside so a validation pass can compare a measured
    coefficient against the figure that was asked for, rather than against the
    figure that was set - which are different numbers and confusing them is the
    whole point of this module.
    """

    marble: BodyMaterial
    surface: BodyMaterial
    wanted_marble_marble_friction: float
    wanted_marble_surface_friction: float
    wanted_marble_marble_restitution: float
    wanted_marble_surface_restitution: float

    def effective_marble_marble_friction(self) -> float:
        return combine(self.marble.friction, self.marble.friction)

    def effective_marble_surface_friction(self) -> float:
        return combine(self.marble.friction, self.surface.friction)

    def effective_marble_marble_restitution(self) -> float:
        return self.marble.restitution * self.marble.restitution

    def effective_marble_surface_restitution(self) -> float:
        return self.marble.restitution * self.surface.restitution

    def to_json(self) -> dict[str, Any]:
        return {
            "marble": self.marble.to_json(),
            "surface": self.surface.to_json(),
            "wanted": {
                "marble_marble_friction": self.wanted_marble_marble_friction,
                "marble_surface_friction": self.wanted_marble_surface_friction,
                "marble_marble_restitution": self.wanted_marble_marble_restitution,
                "marble_surface_restitution": self.wanted_marble_surface_restitution,
            },
            "combine_rule": "product",
        }


def solve_materials(marble: MarbleConfig) -> SolvedMaterials:
    """Two body materials whose products are the wanted pair coefficients."""
    if marble.friction <= 0.0:
        raise ValueError(
            "marble-on-marble friction must be positive: the surface value is "
            "solved by dividing by its square root"
        )
    if marble.restitution <= 0.0:
        raise ValueError("marble-on-marble restitution must be positive for the same reason")

    marble_friction = math.sqrt(marble.friction)
    surface_friction = marble.surface_friction / marble_friction
    marble_restitution = math.sqrt(marble.restitution)
    surface_restitution = marble.surface_restitution / marble_restitution

    # The product is always solvable on paper; what is not always sane is the
    # per-body number it takes. A marble-on-marble figure far below the
    # marble-on-track one drives the surface coefficient arbitrarily high, and
    # a body carrying a friction of 500 is a body one contact away from Bullet
    # clamping the pair at 10 and the machine getting a coefficient nobody
    # asked for. Refuse it where it is still arithmetic.
    if surface_friction > MAX_COMBINED_FRICTION:
        raise ValueError(
            f"marble-on-track friction {marble.surface_friction} is not reachable "
            f"alongside marble-on-marble {marble.friction}: it needs a surface "
            f"coefficient of {surface_friction:.1f}, and Bullet clamps a combined "
            f"coefficient at {MAX_COMBINED_FRICTION}"
        )
    if surface_restitution > 1.0:
        raise ValueError(
            f"marble-on-track restitution {marble.surface_restitution} is not "
            f"reachable alongside marble-on-marble {marble.restitution}: it needs "
            f"a surface value of {surface_restitution:.2f}, and a body cannot "
            "return more energy than it receives"
        )

    # Rolling and spinning friction combine by the same product rule, and the
    # machine only ever wants one value for them, so they are solved
    # symmetrically. Marble-on-marble rolling resistance comes out at the same
    # figure, which is harmless: two marbles in rolling contact is not a state
    # this machine spends time in.
    rolling = math.sqrt(marble.rolling_friction) if marble.rolling_friction > 0.0 else 0.0
    spinning = math.sqrt(marble.spinning_friction) if marble.spinning_friction > 0.0 else 0.0

    return SolvedMaterials(
        marble=BodyMaterial(marble_friction, marble_restitution, rolling, spinning),
        surface=BodyMaterial(surface_friction, surface_restitution, rolling, spinning),
        wanted_marble_marble_friction=marble.friction,
        wanted_marble_surface_friction=marble.surface_friction,
        wanted_marble_marble_restitution=marble.restitution,
        wanted_marble_surface_restitution=marble.surface_restitution,
    )


# --- the analytic facts the friction tests measure against ----------------


def rolling_threshold(slope_angle: float) -> float:
    """The least friction coefficient that lets a solid sphere roll, not skid.

    On an incline of angle theta a rolling sphere needs a friction force of
    (2/7) m g sin(theta) and the surface can supply at most mu m g cos(theta),
    so rolling requires mu >= (2/7) tan(theta). Every surface in a marble
    machine has to clear this or its marbles slide, and a sliding marble looks
    wrong in a way viewers notice immediately even when they cannot say why.
    """
    return (2.0 / 7.0) * math.tan(slope_angle)


def rolling_acceleration(gravity: float, slope_angle: float) -> float:
    """(5/7) g sin(theta): a solid sphere rolling without slipping."""
    return (5.0 / 7.0) * gravity * math.sin(slope_angle)


def sliding_acceleration(gravity: float, slope_angle: float, friction: float) -> float:
    """g (sin(theta) - mu cos(theta)): a sphere skidding down the same incline.

    Inverting this is how a test recovers the coefficient the engine is really
    applying, which is the only number that matters.
    """
    return gravity * (math.sin(slope_angle) - friction * math.cos(slope_angle))

"""The one unit convention, written down once so nothing can convert silently.

Everything in `marble3d` - configuration, geometry, colliders, velocities,
replay files, tests - is in **world units** and **seconds**. There is no other
system of units anywhere in the package and no code that multiplies or divides
by a scale factor. That is the whole point of this module: the physics lab's
most expensive bug was a scale conversion applied in one place and not another,
and the fix is not a more careful conversion but no conversion.

## The convention

    1 world unit (wu) = 1 engine metre
    marble radius     = 0.5 wu, so a marble is exactly one unit across
    gravity           = 245.25 wu/s^2, along -Y
    +Y is up, gravity is -Y, the machine is built in the XZ plane

Gravity is not 9.81 and that is deliberate, so it needs the argument in full.

## Why gravity is 245.25

Bullet is tuned for objects around a metre across. `btCollisionShape`'s default
collision margin is 0.04 world units; against a real 20 mm marble that is *twice
the radius*, and the lab measured what that does - a marble at rest on the bowl
wall was flung outward from 0.30 m to 0.43 m in half a second, gaining 0.7 m/s
out of nothing, because every contact was generated a margin deep and pushed
out accordingly. Running a marble machine at life size is running the engine
fifty times below the scale it expects, and it does not survive it.

So the machine is authored at engine scale: the marble is half a unit in radius
rather than a fiftieth. That fixes the solver, and it leaves one question -
what should gravity be?

Under the similarity transform `L -> S*L`, `g -> S*g`, Newton's second law is
invariant in **time**: if `x(t)` solves `x'' = a(x, x')` then `S*x(t)` solves
the scaled system with the *same* `t`. Lengths, velocities and accelerations all
scale by S; times, angular velocities, dimensionless ratios and every collision
outcome do not. So scaling gravity by the same factor as the geometry gives a
machine that is geometrically similar to the desktop toy and runs on the toy's
clock. Leaving gravity at 9.81 instead would give a monument: correct SI, but
every event `sqrt(25) = 5x` slower, and a marble race that plays like a
timelapse of a glacier.

    S = 25
    MARBLE_RADIUS   = 0.020 m * 25 = 0.5 wu
    GRAVITY         = 9.81 m/s^2 * 25 = 245.25 wu/s^2
    1 wu            = 0.04 m of the toy this is a model of

`TOY_METRES_PER_UNIT` below is that last line. It is used for **reporting only**
- a docstring, a report table, a sanity check that a number is physically
plausible - and never inside a simulation, a module, a collider or a replay. If
it ever appears in a code path that runs during `step()`, the convention has
been broken.

## What this buys, concretely

* Bullet's default margin is 8% of the marble radius rather than 200% of it,
  and the explicit margin policy in `marble3d.config` takes it to 0.2%.
* Contact impulses, inertia tensors and penetration budgets are all in the
  range the solver's fixed tolerances were chosen for.
* A replay file is in world units, the renderer draws world units, and the only
  scale in the whole pipeline is whatever a camera chooses - which is a framing
  decision and not a physics one.

## Reading a number in this package

Divide by 25 to get the toy it models. A 12.5 wu bowl is a 50 cm bowl. A speed
of 70 wu/s is 2.8 m/s. An acceleration of 245.25 wu/s^2 is one gravity. Times
are already real: 17 seconds here is 17 seconds on the bench.
"""

from __future__ import annotations

import math

__all__ = [
    "SIMILARITY_SCALE",
    "TOY_METRES_PER_UNIT",
    "GRAVITY",
    "MARBLE_RADIUS",
    "MARBLE_DIAMETER",
    "STANDARD_GRAVITY",
    "TOY_MARBLE_RADIUS_M",
    "UP",
    "GRAVITY_VECTOR",
    "to_toy_metres",
    "from_toy_metres",
    "describe",
]

# The two numbers the convention is built from, and the only two.
STANDARD_GRAVITY = 9.81           # m/s^2, the thing being modelled
TOY_MARBLE_RADIUS_M = 0.020       # m, a 40 mm glass marble

# Chosen so the marble comes out at exactly half a unit. Any S in roughly
# 10..50 would work for the solver; 25 is the one that makes the marble a round
# number, which matters more than it sounds because every clearance in the
# machine is quoted in marble diameters.
SIMILARITY_SCALE = 25.0

MARBLE_RADIUS = TOY_MARBLE_RADIUS_M * SIMILARITY_SCALE      # 0.5 wu
MARBLE_DIAMETER = 2.0 * MARBLE_RADIUS                       # 1.0 wu
GRAVITY = STANDARD_GRAVITY * SIMILARITY_SCALE               # 245.25 wu/s^2

# Reporting only. See the module docstring: this constant must not appear in
# anything that runs inside a simulation step.
TOY_METRES_PER_UNIT = 1.0 / SIMILARITY_SCALE                # 0.04 m per wu

UP = (0.0, 1.0, 0.0)
GRAVITY_VECTOR = (0.0, -GRAVITY, 0.0)


def to_toy_metres(world_units: float) -> float:
    """A length in world units, as metres of the desktop toy this models."""
    return world_units * TOY_METRES_PER_UNIT


def from_toy_metres(metres: float) -> float:
    """A length in toy metres, as world units. For authoring, not for running."""
    return metres / TOY_METRES_PER_UNIT


def free_fall_speed(drop: float) -> float:
    """Speed after falling `drop` world units from rest, ignoring rotation.

    Used to size collision-continuity margins and to choose the physics rate:
    the distance a marble covers in one tick at this speed is what decides
    whether a wall of a given thickness can be tunnelled through.
    """
    return math.sqrt(2.0 * GRAVITY * max(0.0, drop))


def describe() -> str:
    """The convention as a block of text, for reports and for `--units`."""
    return (
        f"1 world unit = 1 engine metre = {TOY_METRES_PER_UNIT:.3f} m of the "
        f"{SIMILARITY_SCALE:.0f}x-smaller toy modelled\n"
        f"marble radius   {MARBLE_RADIUS:.3f} wu "
        f"({to_toy_metres(MARBLE_RADIUS) * 1000:.0f} mm toy)\n"
        f"gravity         {GRAVITY:.2f} wu/s^2 "
        f"(= {STANDARD_GRAVITY} m/s^2 scaled; time is unchanged)\n"
        f"axes            +Y up, gravity -Y, machine laid out in XZ"
    )

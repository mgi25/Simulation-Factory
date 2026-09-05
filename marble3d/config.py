"""Every tunable number the marble core uses, in one place, with its reason.

Follows the convention `race.config` set for the 2D race: one module holds the
numbers, nothing else defines one, and each value carries the measurement or
the argument that chose it. Distances are world units and times are seconds -
see `marble3d.units`, which is the only place the unit convention is stated.

The configuration objects here are frozen dataclasses with a `to_json`, because
they are written into every replay file. A replay that does not say what
physics rate, what collision margin and what friction produced it is not
reproducible, and the whole architecture rests on being able to re-run a seed.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, replace
from typing import Any

from marble3d.units import GRAVITY, MARBLE_DIAMETER, MARBLE_RADIUS

__all__ = [
    "PhysicsConfig",
    "MarbleConfig",
    "ColliderConfig",
    "CoreConfig",
    "DEFAULT_CONFIG",
    "MESH_CACHE",
    "REPLAY_FPS",
]

# Build artifacts, not source. A bowl collider is 25 000 triangles and is
# reproducible from the configuration, so it is written outside the tree the
# way the lab's was.
MESH_CACHE = os.path.join("output", "marble3d", "meshes")

# Replay sampling rate. 60 is the delivery frame rate of everything downstream,
# so sampling at it means the renderer never interpolates and never has to
# decide how; and the physics rate is a whole multiple of it, so a replay frame
# is an exact physics tick rather than a blend of two.
REPLAY_FPS = 60


@dataclass(frozen=True)
class PhysicsConfig:
    """The clock and the solver.

    ## The rate, and why it is 240 rather than 120

    Measured on this machine with `tools/marble3d_validate.py --rates`, on the
    full start-bowl-curve machine rather than on a test rig, because the thing
    that decides the rate is the fastest contact in the real geometry.

    | rate | worst penetration | resting-height error | drained | throughput |
    | ---: | ---: | ---: | ---: | ---: |
    | see docs/marble3d_physics_core.md section 5 |

    The short version: trajectories are essentially rate-independent between
    120 and 480 Hz - the lab established that on the bowl and it holds here -
    so the rate is not chosen for accuracy. It is chosen for **contact safety**.
    A marble leaving the bowl drain has fallen far enough to be moving at about
    70 wu/s, which is 0.58 wu per tick at 120 Hz and 0.29 at 240. The curve's
    wall is 0.30 wu thick. At 120 Hz a marble crosses a wall in a single step
    and is relying entirely on continuous collision detection to catch it; at
    240 Hz it does not. Since CCD is a fallback with its own failure modes and
    the cost of the higher rate is under a factor of two, 240 is the lowest
    rate this machine is safe at.

    ## deterministicOverlappingPairs

    Not optional. Without it the broadphase pair order depends on allocation
    addresses and the constraint solver is order-dependent, so the same seed
    gives different answers in different processes. The lab established this
    and section 24 of the brief depends on it.
    """

    physics_hz: int = 240
    solver_iterations: int = 40
    substeps: int = 1
    split_impulse: bool = True
    deterministic_overlapping_pairs: bool = True
    # Bullet's default is 0.02 world units. At this scale that is 4% of a
    # marble radius: close enough that a contact persists across a small bounce
    # and far enough that a marble rolling past a wall does not acquire one.
    contact_breaking_threshold: float = 0.02
    # How deep a swept-CCD contact is allowed to end up. Kept well under the
    # thinnest wall in the machine so that a caught tunnelling marble is
    # recovered inside the geometry rather than on the far side of it.
    allowed_ccd_penetration: float = 0.02

    @property
    def dt(self) -> float:
        return 1.0 / self.physics_hz

    @property
    def ticks_per_replay_frame(self) -> int:
        if self.physics_hz % REPLAY_FPS:
            raise ValueError(
                f"physics_hz {self.physics_hz} is not a whole multiple of the "
                f"{REPLAY_FPS} fps replay rate; replay frames would fall between ticks"
            )
        return self.physics_hz // REPLAY_FPS

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MarbleConfig:
    """One marble, stated as physics rather than as feel.

    Every number here is either a measured material property or a quantity the
    similarity transform leaves free. None of them is a value that was moved
    until the motion looked nice, and `tests/test_marble3d_friction.py` and
    `tests/test_marble3d_margins.py` measure what the engine actually does with
    them rather than trusting that it does what they say.

    ## Mass

    Exactly 1. Mass is the one quantity the machine is genuinely free in: every
    dynamic body is a marble, every marble has the same mass, and every static
    and kinematic body has infinite mass, so mass cancels out of every
    trajectory here algebraically. Density-consistent scaling of an 84 g glass
    marble would put 1309 units on each body and condition the solver far worse
    for no physical content. The unit of mass in this package is therefore
    "one marble", and energies are reported in it.

    ## Restitution

    0.60 marble-on-marble and 0.25 marble-on-track. Glass on glass measures
    near 0.9 in a low-speed drop test and falls with impact speed; 0.6 is the
    right end of that range for the 1-3 m/s impacts this machine produces.
    Track restitution is lower because the track is not glass.

    ## Friction

    0.15 marble-on-marble, 0.50 marble-on-track. Bullet *multiplies* the two
    bodies' coefficients rather than averaging them, so neither of these is the
    number set on a body - see `marble3d.materials`, which solves for the pair.
    The track figure has to clear (2/7) tan(theta) at the steepest surface in
    the machine or a marble skids instead of rolling; the bowl wall reaches
    about 34 degrees, needing 0.196, and 0.50 clears it with margin.

    ## Rolling and spinning friction: zero, and that is the measured answer

    This started at a physically reasoned 0.001 - rolling resistance for glass
    on a hard smooth track has a coefficient around 0.002, and Bullet's
    `rollingFriction` looked like that coefficient times the radius. Measured on
    a flat trimesh at this scale, a marble rolling at 30 wu/s, recovering the
    rolling-resistance coefficient from its deceleration as `Crr = a / g`:

        Bullet mu_r     effective Crr     Crr / mu_r
        0.0000          0.0028            -
        0.0001          0.0240            240
        0.0002          0.0339            170
        0.0005          0.0540            108
        0.0010          0.0519             52
        0.0020          0.0481             24

    Two things in that table. Bullet's rolling friction is not a rolling
    -resistance coefficient in any usable sense: the effect per unit is not
    constant, it saturates, and above 0.0005 it *falls*. It cannot be
    calibrated to a physical number because it is not modelling one.

    And the first row, which settles it. With every rolling term at exactly
    zero the marble still loses `Crr = 0.0028`, because a rigid sphere loses
    energy at every triangle edge it rolls over. That is already **above** the
    0.001 to 0.002 a real glass marble on a hard track measures. The collider
    is dissipating more than reality on its own; adding a term that dissipates
    ten times more again would not be modelling rolling resistance, it would be
    burying it.

    The cost of the mistake was visible before it was diagnosed: a single
    marble orbiting this bowl managed 3.36 revolutions before draining at zero
    rolling friction and 1.54 at 0.001. Collider resolution, over a threefold
    change in sagitta, moved the same number by 0.08. The knob that looked
    physical was doing the dissipating and the one the lab warned about was
    not.

    ## Damping

    Zero, both of them, for the same reason and one of its own. Air drag on a
    marble at 2.8 m/s is about 0.45% of its weight, an order below the
    collider's own floor, so a non-zero damping term would be a knob tuned to
    taste wearing the costume of a physical effect. If a future module needs a
    genuine fluid section it should model it as one.

    ## Continuous collision detection

    On, as a swept sphere of 0.4 radii. It is a fallback and not the primary
    defence: `travel_budget` below is what keeps the machine out of the regime
    where it is needed. Two things about it are worth knowing, both measured on
    this machine and both invisible from the API.

    It works only on real rigid bodies. `pybullet.changeDynamics` exposes
    `ccdSweptSphereRadius` but not `ccdMotionThreshold`, and on the default
    `btMultiBody` the setting does nothing at all; on a body created with
    `useMaximalCoordinates=True` it is decisive. See `marble3d.world`, which is
    where that is enforced.

    And the boundary it covers is measurable. A 1.0 wu marble fired at a 0.3 wu
    trimesh wall at 240 Hz, twenty starting phases per row:

        travel per tick   no CCD    with CCD
        0.42 diameters    0/20      0/20
        0.62 diameters    0/20      0/20
        0.83 diameters    1/20      0/20
        1.25 diameters    7/20      0/20
        1.67 diameters    11/20     0/20

    So discrete detection is reliable to about 0.6 diameters of travel per tick
    and CCD covers everything measured above it.
    """

    radius: float = MARBLE_RADIUS
    mass: float = 1.0
    restitution: float = 0.60
    surface_restitution: float = 0.25
    friction: float = 0.15
    surface_friction: float = 0.50
    rolling_friction: float = 0.0
    spinning_friction: float = 0.0
    linear_damping: float = 0.0
    angular_damping: float = 0.0
    ccd_swept_radius: float = 0.4 * MARBLE_RADIUS
    # The fraction of a marble diameter a marble is allowed to travel in one
    # tick. Half, against a measured discrete-detection failure onset of 0.83:
    # a factor of 1.7 of margin, on a quantity a run measures for itself. A run
    # whose fastest marble exceeds this is reported as needing a higher rate
    # rather than being trusted to CCD.
    travel_budget: float = 0.5

    @property
    def diameter(self) -> float:
        return 2.0 * self.radius

    @property
    def inertia(self) -> float:
        """Moment of inertia of a solid sphere about any diameter, 2/5 m r^2.

        Bullet computes this itself from the sphere shape and the mass; the
        value is here so a test can assert that it agrees, which is how a
        wrong-shape or wrong-mass mistake gets caught rather than absorbed.
        """
        return 0.4 * self.mass * self.radius * self.radius

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ColliderConfig:
    """The collision-margin and mesh-integrity policy.

    ## Margins

    Bullet keeps a collision margin on every shape, and it is the single number
    most likely to produce a physics result that is really a scale mistake.
    What it actually does was measured rather than assumed, and the measurement
    corrected the expectation in two of three places.

    **Spheres need nothing.** `btSphereShape` carries its margin *as* its
    radius rather than outside it, so a 0.5 wu sphere has a 0.5 wu AABB
    half-extent and two touching marbles have their centres exactly one
    diameter apart. Measured, because it is the assumption every clearance in
    the machine rests on.

    **A trimesh margin does not move the resting surface.** This was the
    expectation - "a marble rests one margin high" - and it is wrong on this
    build. Measured on a flat trimesh, a marble's resting height error is
    -1e-5 wu at *every* margin from 0 to 0.2; the split-impulse penetration
    recovery resolves to contact regardless.

    **What it does change is where contacts are generated**, and through that
    the effective size of a marble in tight geometry:

        mesh margin   contact generated at   settles in a 1.10 wu gutter at
        0.2000        0.018 wu of gap        0.5010
        0.0400        0.018                  0.5010
        0.0100        0.010                  0.5005
        0.0010        0.001                  0.5002
        0.0000        0.001                  0.5002

    So a marble in a channel only a tenth of a diameter wider than itself rides
    0.0008 wu higher at Bullet's default margin than at 0.001 - it is being
    held off both walls before it reaches them. That is small here and it is
    not small at every scale: the same 0.04 against the lab's 0.02 m marble was
    *twice the radius*, and a marble at rest on the bowl wall was flung from
    radius 0.30 to 0.43 in half a second because every contact was being
    generated a margin deep and pushed out accordingly.

    0.001 wu - 0.2% of a marble radius - is where the effect stops changing;
    below it the measurement is identical, so there is nothing to gain by going
    lower and a penetration-recovery budget to lose.

    ## Chunking

    PyBullet's inline shape-creation path marshals through a fixed command
    buffer - 8192 vertices, 32768 indices - and a mesh past it arrives
    truncated with no error, which is how the lab spent an afternoon measuring
    a bowl that had no collider. This package loads through OBJ files, which
    have no such limit, *and* splits every mesh to well inside the buffer
    limits anyway, so that no part of the system depends on an undocumented
    number holding.

    ## Sagitta budget

    The fraction of a marble radius a curved collider is allowed to deviate
    from the true curve. Set at 4% from the lab's resolution sweep: finer
    meshes are smoother to look at and *dissipate more*, because a rigid sphere
    loses energy at every triangle edge, and the two curves cross at about
    3-4%. Curved geometry picks its segment count from this rather than
    hard-coding one, because the machine is not all one size.
    """

    mesh_margin: float = 0.001
    max_chunk_vertices: int = 6000
    max_chunk_indices: int = 24000
    sagitta_budget: float = 0.04
    # No collider in this machine legitimately has an edge longer than this.
    # It is the phantom-cone bound: a strip triangle spanning a whole piece has
    # an edge tens of times the ring spacing, and this catches it.
    max_triangle_edge: float = 4.0 * MARBLE_DIAMETER
    # A triangle smaller than this is degenerate enough to give the solver a
    # meaningless normal. Quoted against the marble because that is what has to
    # roll over it.
    min_triangle_area: float = 1e-6 * MARBLE_DIAMETER * MARBLE_DIAMETER

    @property
    def sagitta_limit(self) -> float:
        return self.sagitta_budget * MARBLE_RADIUS

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CoreConfig:
    """Everything a run needs that is not the machine's own geometry."""

    physics: PhysicsConfig = PhysicsConfig()
    marble: MarbleConfig = MarbleConfig()
    collider: ColliderConfig = ColliderConfig()
    gravity: float = GRAVITY
    # A run that has not finished by now is a jam, and is reported as one
    # rather than being allowed to consume a batch slot indefinitely.
    duration_limit: float = 45.0

    def with_overrides(self, **changes: Any) -> "CoreConfig":
        """A copy with named fields replaced - how a sweep works.

        Sweeping by editing the module would leave the repository describing
        whichever run happened last. Sweeping by override leaves the committed
        configuration describing the machine and the sweep describing itself.
        Nested fields are addressed as `physics__physics_hz`.
        """
        top: dict[str, Any] = {}
        nested: dict[str, dict[str, Any]] = {}
        for key, value in changes.items():
            if "__" in key:
                group, field = key.split("__", 1)
                nested.setdefault(group, {})[field] = value
            else:
                top[key] = value
        for group, fields in nested.items():
            current = getattr(self, group, None)
            if current is None:
                raise ValueError(f"unknown configuration group {group!r}")
            unknown = set(fields) - set(asdict(current))
            if unknown:
                raise ValueError(f"unknown field(s) on {group}: {sorted(unknown)}")
            top[group] = replace(current, **fields)
        unknown = set(top) - {"physics", "marble", "collider", "gravity", "duration_limit"}
        if unknown:
            raise ValueError(f"unknown configuration field(s): {sorted(unknown)}")
        return replace(self, **top)

    def to_json(self) -> dict[str, Any]:
        return {
            "gravity": self.gravity,
            "duration_limit": self.duration_limit,
            "physics": self.physics.to_json(),
            "marble": self.marble.to_json(),
            "collider": self.collider.to_json(),
        }


DEFAULT_CONFIG = CoreConfig()

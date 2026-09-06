"""Solver knobs and explicit resistance models, all defaulting to off.

This module exists because of one measured fact: **the dissipation that gives
the production bowl its three revolutions is not a physical effect.** It is the
work the contact constraint does against the normal velocity a marble
re-acquires between two solves, it is first order in the timestep, and it
therefore converges to *zero* rather than to a physical number as the rate
rises. `docs/marble3d_physics_hardening.md` is the measurement; this module is
the apparatus for it and for the candidate remedies.

Nothing here changes production behaviour. Every field defaults to the value
that reproduces `marble-physics-core` exactly, `HardeningConfig()` compares
equal to the default, and `CoreConfig.to_json` omits the whole block when it is
the default - so a default run writes a byte-identical replay and produces a
byte-identical digest. `tests/test_marble3d_hardening.py` asserts both.

## What is in here and why it is split this way

Three groups, divided by what each is evidence *about*.

**`SolverConfig`** exposes the `setPhysicsEngineParameter` knobs the production
world does not set: the restitution velocity threshold, ERP and CFM, the split
impulse penetration threshold, warm starting, contact slop, cone friction, the
solver type, and `numSubSteps`. All of them were already reachable through
PyBullet on this build - they were simply never measured. Two of them turn out
to matter enormously and the rest turn out not to, and a knob that does not
matter is worth as much in a report as one that does.

**`ResistanceConfig`** is the explicit, deterministic resistance model section 8
of the hardening brief asks for: a rolling-resistance *torque* with a stated
coefficient, or a continuous-time exponential decay, applied only while a
marble is actually touching the machine. It is not scripted motion - it applies
no radial force, no attraction and no spiral, it acts only along axes the
marble's own motion defines, and it cannot move a marble that is not already
moving. It is the one term in the machine that is a physical model of a loss
rather than a numerical accident that happens to look like one.

**`engine_parameters`** turns a `SolverConfig` into the keyword arguments
`pybullet.setPhysicsEngineParameter` wants, omitting every key that was left
unset so that Bullet's own default stands rather than being overwritten by this
package's guess at what that default is.

## Why the resistance is a torque and not a velocity multiplier

A per-step multiplication `v <- v * (1 - k)` is a different physical law at
every rate: over one second it is `(1 - k) ** hz`, so 120 Hz and 480 Hz do not
merely disagree about the accuracy of an answer, they are integrating different
equations. Both models here are stated in continuous time and discretised
consistently.

* `rolling` applies a torque of magnitude `Crr * N * R` opposing the rolling
  direction, where `N` is the normal force the solver actually reported on the
  previous step. That is the textbook rolling-resistance law, its coefficient
  is the one materials tables quote, and it is what a real marble on a real
  track does. A rolling sphere under it decelerates at `(5/7) Crr g`, which is
  where the factor in `rolling_deceleration` comes from and which the
  measurement recovers.
* `exponential` applies `v <- v exp(-k dt)` and `w <- w exp(-k_w dt)`. This is
  exactly rate independent rather than approximately so: `exp(-k dt)` composed
  `T / dt` times is `exp(-k T)` for every `dt`, identically, in exact
  arithmetic. It is viscous rather than Coulomb - a marble under it never quite
  stops - and it is here because section 9 of the brief asks for the
  continuous-time form, and because it is the cleanest possible control on the
  question "does a rate-independent loss term actually produce rate-independent
  behaviour".

Both are gated on contact. A marble in free flight is untouched, because air
drag on a marble at these speeds is 0.45% of its weight and a resistance term
applied in mid-air would be a fudge wearing a physical name.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

__all__ = [
    "SolverConfig",
    "ResistanceConfig",
    "HardeningConfig",
    "engine_parameters",
    "apply_resistance",
    "rolling_deceleration",
    "RESISTANCE_MODELS",
]

RESISTANCE_MODELS = ("off", "rolling", "exponential")


@dataclass(frozen=True)
class SolverConfig:
    """Bullet solver settings the production world leaves at their defaults.

    Every field is `None` for "do not set it", so an unmeasured knob keeps
    whatever Bullet's own default is rather than being pinned to this package's
    belief about what that default is. `engine_parameters` drops the `None`s.

    ## restitution_velocity_threshold

    The one that explains the cliff. Bullet applies restitution only when the
    closing normal speed exceeds `m_restitutionVelocityThreshold`, whose default
    is 0.2 in world units per second. Gravity here is 245.25 wu/s^2, so a marble
    resting on a surface re-acquires `g dt` of inward normal velocity between
    two solves:

        120 Hz   2.044 wu/s     240 Hz   1.022     480 Hz   0.511
        960 Hz   0.255          1920 Hz  0.128

    The threshold falls between 960 and 1920 Hz. Above it every sustained
    contact is treated as an impact and given a restitution target; below it
    none of them are. That is a *discontinuity in the physical model* sitting
    inside the rate sweep, and it is why 1920 Hz does not merely orbit longer
    than 960 Hz but stops containing marbles at all.

    ## sub_steps

    `numSubSteps = k` runs Bullet at `dt / k` internally while the outer tick -
    and therefore actuator poses, sampling, the replay stride and every event
    timestamp - stays at `dt`. It is the only way to buy a smaller integration
    step without changing the replay's own clock, and it is how a candidate can
    have 960 Hz contact behaviour and a 240 Hz replay.
    """

    restitution_velocity_threshold: float | None = None
    erp: float | None = None
    contact_erp: float | None = None
    friction_erp: float | None = None
    global_cfm: float | None = None
    split_impulse_penetration_threshold: float | None = None
    warm_starting_factor: float | None = None
    contact_slop: float | None = None
    cone_friction: bool | None = None
    solver_residual_threshold: float | None = None
    constraint_solver_type: int | None = None
    sub_steps: int | None = None
    # Whether static trimeshes are built with GEOM_CONCAVE_INTERNAL_EDGE. On by
    # default because that is what production does; exposed because whether the
    # flag does anything at all on this build is a question rather than an
    # assumption, and the answer needs an A/B.
    internal_edge: bool = True

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResistanceConfig:
    """An explicit, rate-consistent loss term. Off unless asked for.

    `model` is one of `RESISTANCE_MODELS`:

    * `off` - nothing is applied and nothing is read; the production path.
    * `rolling` - a rolling-resistance torque `Crr * N * R` opposing the rolling
      direction, plus an optional spin resistance `Csr * N * R` opposing the
      spin about the contact normal. Physical, Coulomb-like, calibratable
      against a materials table, first-order consistent in dt.
    * `exponential` - `v <- v exp(-k dt)`, `w <- w exp(-k_w dt)` while in
      contact. Exactly rate independent, viscous rather than Coulomb.

    `crr` is the textbook rolling-resistance coefficient: the ratio of the
    resisting force to the normal load. Glass on a hard smooth track measures
    0.001 to 0.002. The tessellated collider's own numerical floor at 240 Hz is
    already about 0.0023, which is the whole reason this module exists - a
    physical coefficient cannot be heard over a numerical one larger than it.

    `min_normal_force` keeps the model from acting on a grazing touch the solver
    reported with essentially no load, and is quoted as a fraction of one
    marble's weight so it carries across a change of scale.
    """

    model: str = "off"
    crr: float = 0.0
    spin_crr: float = 0.0
    linear_rate: float = 0.0            # k, per second, for `exponential`
    angular_rate: float = 0.0           # k_w, per second, for `exponential`
    min_normal_force: float = 0.02      # of one marble weight
    # Free-flight marbles are never touched. A field rather than only a
    # docstring claim, so the replay carries it.
    contact_gated: bool = True

    def __post_init__(self) -> None:
        if self.model not in RESISTANCE_MODELS:
            raise ValueError(
                f"unknown resistance model {self.model!r}; expected one of {RESISTANCE_MODELS}"
            )
        if self.crr < 0.0 or self.spin_crr < 0.0:
            raise ValueError("a resistance coefficient cannot be negative")
        if self.linear_rate < 0.0 or self.angular_rate < 0.0:
            raise ValueError("a decay rate cannot be negative")

    @property
    def active(self) -> bool:
        return self.model != "off"

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HardeningConfig:
    """The research block, defaulting to "behave exactly like production"."""

    solver: SolverConfig = SolverConfig()
    resistance: ResistanceConfig = ResistanceConfig()

    @property
    def is_default(self) -> bool:
        return self == HardeningConfig()

    def to_json(self) -> dict[str, Any]:
        return {"solver": self.solver.to_json(), "resistance": self.resistance.to_json()}


def rolling_deceleration(crr: float, gravity: float) -> float:
    """What a rolling sphere under `crr` actually decelerates at.

    A resisting torque `tau = Crr N R` on a sphere rolling without slipping
    gives `a = tau / (R (m + I / R^2)) = (5/7) Crr g` when `N = mg`, because the
    friction that enforces the rolling constraint has to spin the sphere down as
    well as slow it. The 5/7 is why a measured `a / g` is not the coefficient
    that was asked for, and stating it here stops that being rediscovered.
    """
    return (5.0 / 7.0) * crr * gravity


def engine_parameters(solver: SolverConfig) -> dict[str, Any]:
    """`setPhysicsEngineParameter` keywords, for the fields that were set."""
    mapping = {
        "restitutionVelocityThreshold": solver.restitution_velocity_threshold,
        "erp": solver.erp,
        "contactERP": solver.contact_erp,
        "frictionERP": solver.friction_erp,
        "globalCFM": solver.global_cfm,
        "splitImpulsePenetrationThreshold": solver.split_impulse_penetration_threshold,
        "warmStartingFactor": solver.warm_starting_factor,
        "contactSlop": solver.contact_slop,
        "solverResidualThreshold": solver.solver_residual_threshold,
        "constraintSolverType": solver.constraint_solver_type,
    }
    parameters = {key: value for key, value in mapping.items() if value is not None}
    if solver.cone_friction is not None:
        parameters["enableConeFriction"] = 1 if solver.cone_friction else 0
    if solver.sub_steps is not None:
        parameters["numSubSteps"] = int(solver.sub_steps)
    return parameters


def normal_loads(world: Any) -> dict[int, tuple[float, tuple[float, float, float]]]:
    """Per-marble total normal load, and the load-weighted contact normal.

    Read from the manifold the previous step left behind, so this is a
    one-step-lagged explicit term. That is deliberate: after the solve is the
    only place the number exists, the lag is one tick of a quantity that changes
    slowly compared with a tick, and an explicit term is reproducible in a way
    that a mid-solve callback would not be.

    Marble-on-marble contacts are excluded. Rolling resistance is a property of
    a body rolling on a *track*; two marbles bouncing off each other are already
    governed by friction and restitution, and a rolling term on that pair would
    be double counting.
    """
    loads: dict[int, tuple[float, list[float]]] = {}
    for contact in world.contacts():
        first = world.marble_of(contact.body_a)
        second = world.marble_of(contact.body_b)
        if (first is None) == (second is None):
            continue                     # world-on-world, or marble-on-marble
        force = contact.normal_impulse
        if force <= 0.0:
            continue
        # `contactNormalOnB` points from B towards A. Flip it when the marble is
        # A so that the stored normal always points out of the surface and into
        # the marble.
        if first is not None:
            marble_id, sign = first, -1.0
        else:
            marble_id, sign = second, 1.0
        total, accumulated = loads.get(marble_id, (0.0, [0.0, 0.0, 0.0]))
        total += force
        for axis in range(3):
            accumulated[axis] += sign * force * contact.normal[axis]
        loads[marble_id] = (total, accumulated)
    return {
        marble_id: (total, (vector[0], vector[1], vector[2]))
        for marble_id, (total, vector) in loads.items()
    }


def _unit(vector: tuple[float, float, float]) -> tuple[float, float, float] | None:
    length = math.sqrt(sum(value * value for value in vector))
    if length <= 1e-12:
        return None
    return (vector[0] / length, vector[1] / length, vector[2] / length)


def apply_resistance(world: Any, resistance: ResistanceConfig, dt: float) -> int:
    """Apply the configured resistance to every marble in contact; return how many.

    Called immediately before `world.step()`. Marbles are visited in ascending
    id and every quantity comes from the engine rather than from an accumulator,
    so the term is a pure function of the world state applied in a fixed order -
    which is what keeps a run with resistance on as reproducible as one with it
    off.
    """
    if not resistance.active:
        return 0
    pybullet = world.pybullet
    marble = world.config.marble
    threshold = resistance.min_normal_force * marble.mass * world.config.gravity
    loads = normal_loads(world) if resistance.contact_gated else {}
    touched = 0

    for marble_id in sorted(world.marbles):
        load, normal_sum = loads.get(marble_id, (0.0, (0.0, 0.0, 0.0)))
        if resistance.contact_gated and load < threshold:
            continue
        body = world.marbles[marble_id]
        velocity, spin = pybullet.getBaseVelocity(body, physicsClientId=world.client)
        touched += 1

        if resistance.model == "exponential":
            linear = math.exp(-resistance.linear_rate * dt)
            angular = math.exp(-resistance.angular_rate * dt)
            pybullet.resetBaseVelocity(
                body,
                linearVelocity=[value * linear for value in velocity],
                angularVelocity=[value * angular for value in spin],
                physicsClientId=world.client,
            )
            continue

        # `rolling`: a torque about the rolling axis, and optionally one about
        # the contact normal. The rolling axis is the component of the spin
        # perpendicular to the contact normal - the part that actually rolls the
        # marble along the surface - so a marble spinning like a top on the spot
        # is slowed by `spin_crr` and not by `crr`.
        normal = _unit(normal_sum)
        if normal is None:
            continue
        along = sum(a * b for a, b in zip(spin, normal))
        rolling_axis = tuple(spin[axis] - along * normal[axis] for axis in range(3))
        torque = [0.0, 0.0, 0.0]
        direction = _unit(rolling_axis)
        if direction is not None and resistance.crr > 0.0:
            magnitude = resistance.crr * load * marble.radius
            for axis in range(3):
                torque[axis] -= magnitude * direction[axis]
        if resistance.spin_crr > 0.0 and abs(along) > 1e-9:
            magnitude = resistance.spin_crr * load * marble.radius
            sign = 1.0 if along > 0.0 else -1.0
            for axis in range(3):
                torque[axis] -= sign * magnitude * normal[axis]
        if torque != [0.0, 0.0, 0.0]:
            pybullet.applyExternalTorque(
                body, -1, torque, pybullet.WORLD_FRAME, physicsClientId=world.client
            )
    return touched

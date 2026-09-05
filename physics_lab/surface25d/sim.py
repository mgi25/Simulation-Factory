"""Approach A: Python authoritative, marbles constrained to a 3D surface.

The whole prototype rests on one choice. A marble in contact with the bowl is
**two numbers**, its horizontal position, and its height is evaluated from the
surface rather than integrated. The constraint is not enforced by a solver, a
penalty or a projection - it is the coordinate system. That disposes of four of
the failure modes the brief asks to be watched for before a line of physics is
written: a marble cannot sink below the surface, hover above it, drift off it,
or tunnel through it, because there is no degree of freedom in which any of
those is expressible.

What is left is the physics, and it is genuinely three-dimensional:

* gravity is projected into the local tangent plane, so a marble on the far
  wall of the bowl is pulled toward the centre exactly as hard as one on the
  near wall - which is the specific thing the production 2D bowl cannot do;
* the curvature of the surface enters the equations as a real term, so a fast
  marble on the wall is held against it and follows it round instead of
  crossing the basin in a straight line;
* the normal force is a number the prototype has rather than an assumption,
  which is what lets the drain be a physical event: the lip is convex, the
  normal force falls as a marble rolls onto it, and at zero the surface has
  let go;
* marble-on-marble contacts are resolved as 3D impulses between two spheres,
  with each marble's constraint entering through its effective inverse mass.

There are two phases. `surface` is the above. `free` is an ordinary ballistic
3D marble - what a marble becomes when the surface releases it at the drain
lip, or when a collision throws it clear - which falls, still collides, and
either lands back on the dish or leaves down the drain shaft. Nothing is ever
teleported between them.

## Where this is an approximation, stated plainly

* **Rolling inertia is a scalar.** A solid sphere rolling without slipping
  carries `(1/5) m v^2` of rotational energy alongside `(1/2) m v^2`, and this
  model accounts for it by giving the marble `1 + 2/5` times its mass. That is
  exact for rolling on a plane and very nearly right here; the error is the
  ratio of the marble radius to the surface radius of curvature, about 3% at
  the rim of this bowl.
* **No gyroscopic terms.** The spin axis reorients as a marble travels around
  the dish, which a full rigid-body treatment would charge for. This does not.
* **Rolling is assumed, never checked.** There is no slip condition and no
  Coulomb limit on the contact friction that maintains rolling. A real marble
  hitting a steep enough wall fast enough would skid; this one never does.
* **The contact point traces the offset surface**, whose arc length differs
  slightly from the centre path's. Neglected.

Every one of those is a place the true-3D prototype does the honest thing and
this one does not, and the comparison exists to find out whether any of them
show up in the picture.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from physics_lab.common.benchmark import Benchmark, RunSpec
from physics_lab.common.bowl import BowlSurface
from physics_lab.common.labreplay import (
    STATE_DRAINED,
    STATE_ESCAPED,
    STATE_FREE,
    STATE_SURFACE,
    FrameSample,
    LabEvent,
    LabRun,
    MarbleSample,
)

__all__ = ["SurfaceMarble", "SurfaceBowlSim", "simulate"]

APPROACH = "surface25d"

# Below this the surface is treated as having let go. Not zero, because a
# marble in a shallow contact chatters between "just holding" and "just
# released" for a few ticks otherwise, and each of those transitions costs a
# recomputation of the state for no change in the trajectory.
RELEASE_NORMAL_FORCE = 1e-9

# A landing softer than this attaches to the surface instead of bouncing. A
# marble that lands with a rebound of half a millimetre a second is resting on
# the bowl, and modelling it as an endless series of ever-smaller bounces is
# both wrong and expensive.
ATTACH_SPEED = 0.05

# How much of an overlap is removed per positional pass, and how many passes.
# Split over several passes rather than removed at once because a marble in a
# three-way pile-up is being pushed by two neighbours and correcting fully
# against one of them just buries it in the other.
SEPARATION_FRACTION = 0.8
SEPARATION_PASSES = 3


@dataclass
class SurfaceMarble:
    """One marble, in whichever of the two phases it is currently in.

    In `surface` the chart fields are authoritative and the world fields are
    derived. In `free` it is the other way round. Keeping both sets rather than
    a union is what lets the collision code ask any marble for its world state
    without caring which phase it is in.
    """

    marble_id: int
    state: str = STATE_SURFACE
    # chart: authoritative while on the surface
    x: float = 0.0
    z: float = 0.0
    vx: float = 0.0
    vz: float = 0.0
    # world: authoritative while free
    px: float = 0.0
    py: float = 0.0
    pz: float = 0.0
    wx: float = 0.0
    wy: float = 0.0
    wz: float = 0.0
    # spin, and the orientation it integrates to
    ox: float = 0.0
    oy: float = 0.0
    oz: float = 0.0
    quat: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)

    collisions: int = 0
    drain_time: float | None = None
    exit_order: int | None = None

    @property
    def active(self) -> bool:
        return self.state in (STATE_SURFACE, STATE_FREE)

    @property
    def position(self) -> tuple[float, float, float]:
        return (self.px, self.py, self.pz)

    @property
    def velocity(self) -> tuple[float, float, float]:
        return (self.wx, self.wy, self.wz)


def _quat_integrate(
    quat: tuple[float, float, float, float],
    spin: tuple[float, float, float],
    dt: float,
) -> tuple[float, float, float, float]:
    """Advance an orientation by an angular velocity for one tick.

    First order plus a renormalise, which is all a presentation quantity needs.
    Nothing in the physics reads the orientation back.
    """
    qx, qy, qz, qw = quat
    ox, oy, oz = spin
    half = 0.5 * dt
    nx = qx + half * (ox * qw + oy * qz - oz * qy)
    ny = qy + half * (-ox * qz + oy * qw + oz * qx)
    nz = qz + half * (ox * qy - oy * qx + oz * qw)
    nw = qw + half * (-ox * qx - oy * qy - oz * qz)
    length = math.sqrt(nx * nx + ny * ny + nz * nz + nw * nw)
    if length <= 0.0:
        return (0.0, 0.0, 0.0, 1.0)
    return (nx / length, ny / length, nz / length, nw / length)


class SurfaceBowlSim:
    """The bowl benchmark, with Python owning the physics."""

    def __init__(self, spec: RunSpec) -> None:
        self.spec = spec
        self.benchmark: Benchmark = spec.benchmark
        self.surface: BowlSurface = self.benchmark.surface()
        self.dt = self.benchmark.dt
        self.ticks = 0
        self.elapsed = 0.0
        self.events: list[LabEvent] = []
        self._exit_count = 0
        # Which pairs were in contact at the end of the previous tick, so a
        # collision is reported when two marbles meet rather than for every
        # tick they spend touching.
        self._touching: set[tuple[int, int]] = set()
        # Set if the run stops being a simulation - a non-finite number
        # anywhere. Reported rather than raised, because "this architecture
        # blows up on seed 113" is a result.
        self.failure: str | None = None

        mass = self.benchmark.marble_mass
        self.inertia_factor = self.benchmark.rolling_inertia_factor
        self.effective_mass = mass * (1.0 + self.inertia_factor)
        # Exponential rather than the (1 - k dt) a rigid-body engine uses, so
        # that halving the physics rate does not change the decay. The
        # calibration in the plan is what makes the two comparable anyway.
        self.damping_factor = math.exp(-self.benchmark.linear_damping * self.dt)

        self.marbles = [
            self._make_marble(start.marble_id, start.position, start.velocity, start.spin)
            for start in spec.starts
        ]

    # --- setup ----------------------------------------------------------

    def _make_marble(
        self,
        marble_id: int,
        position: tuple[float, float, float],
        velocity: tuple[float, float, float],
        spin: tuple[float, float, float],
    ) -> SurfaceMarble:
        marble = SurfaceMarble(marble_id=marble_id)
        marble.x, marble.z = position[0], position[2]
        marble.vx, marble.vz = velocity[0], velocity[2]
        marble.ox, marble.oy, marble.oz = spin
        self._sync_world(marble)
        return marble

    def _sync_world(self, marble: SurfaceMarble) -> None:
        """Refresh a surface marble's world state from its chart state."""
        marble.px, marble.py, marble.pz = self.surface.world_position(marble.x, marble.z)
        marble.wx, marble.wy, marble.wz = self.surface.world_velocity(
            marble.x, marble.z, marble.vx, marble.vz
        )

    # --- the equations of motion ----------------------------------------

    def acceleration(self, marble: SurfaceMarble) -> tuple[float, float, float]:
        """Chart acceleration and the normal force, for a marble in contact.

        Returns `(ax, az, normal_force)`. The first two are the tangential
        projection of gravity plus the curvature term, in closed form; the
        third is what the surface has to supply to keep the marble on it, and
        it going negative is how the drain lip lets go.
        """
        surface = self.surface
        state = surface.state(marble.x, marble.z)
        gradient_squared = state.grad_x * state.grad_x + state.grad_z * state.grad_z
        curvature = surface.curvature_term(state, marble.x, marble.z, marble.vx, marble.vz)

        # lambda / m_eff. The `g / (1 + c)` is the rolling factor: a solid
        # sphere reaches 5/7 of the acceleration a sliding block would.
        share = (
            self.benchmark.gravity / (1.0 + self.inertia_factor) + curvature
        ) / (1.0 + gradient_squared)
        normal_force = self.effective_mass * share * math.sqrt(1.0 + gradient_squared)
        return (-state.grad_x * share, -state.grad_z * share, normal_force)

    def _rolling_resistance(self, marble: SurfaceMarble, normal_force: float) -> None:
        """The alternative dissipation model: a force `mu * N` opposing motion.

        Physically the right model for a marble - a roughly constant
        deceleration rather than one proportional to speed - and the reason it
        is not the default is that no rigid-body engine in this study exposes
        anything equivalent, so a benchmark using it could not be matched.
        Swept in the parameter study, off in the headline runs.
        """
        coefficient = self.benchmark.rolling_resistance
        if coefficient <= 0.0 or normal_force <= 0.0:
            return
        speed = math.sqrt(
            marble.wx * marble.wx + marble.wy * marble.wy + marble.wz * marble.wz
        )
        if speed <= 1e-9:
            return
        # The 3D deceleration converts to a chart one by the same linear map
        # that carries chart velocity to world velocity, so scaling the chart
        # velocity by this scales the world velocity identically.
        loss = coefficient * normal_force / self.effective_mass * self.dt / speed
        scale = max(0.0, 1.0 - loss)
        marble.vx *= scale
        marble.vz *= scale

    def _advance_on_surface(
        self,
        marble: SurfaceMarble,
        ax: float,
        az: float,
        normal_force: float,
        dt: float,
    ) -> None:
        """One tick of velocity Verlet, with a predictor for the velocity term.

        Plain symplectic Euler was tried first and is the obvious choice for a
        constrained system, but it is not symplectic *here*: the acceleration
        depends on the velocity through the curvature term, and that breaks the
        property the method is chosen for. Measured on a passive single-marble
        orbit it gained energy at 0.094% per ten seconds at 240 Hz, first order
        in the step - small next to the physical dissipation, but growing, and
        "energy increasing without cause" is one of the failure modes this
        study is supposed to detect rather than exhibit.

        Verlet with a velocity predictor costs a second evaluation of the
        equations of motion per tick and buys second-order behaviour: the same
        measurement comes out around a thousand times smaller. See
        `docs/physics_lab_bowl_comparison.md` for the table.
        """
        x0, z0, vx0, vz0 = marble.x, marble.z, marble.vx, marble.vz

        marble.x = x0 + vx0 * dt + 0.5 * ax * dt * dt
        marble.z = z0 + vz0 * dt + 0.5 * az * dt * dt
        marble.vx = vx0 + ax * dt
        marble.vz = vz0 + az * dt
        predicted_ax, predicted_az, _ = self.acceleration(marble)

        marble.vx = vx0 + 0.5 * (ax + predicted_ax) * dt
        marble.vz = vz0 + 0.5 * (az + predicted_az) * dt
        marble.vx *= self.damping_factor
        marble.vz *= self.damping_factor
        self._sync_world(marble)
        self._rolling_resistance(marble, normal_force)
        self._sync_world(marble)
        self._set_rolling_spin(marble)

    # --- collision machinery --------------------------------------------

    def inverse_mass(self, marble: SurfaceMarble) -> tuple[float, ...]:
        """The 3x3 inverse mass matrix a 3D impulse on this marble sees.

        For a free marble that is `1/m` times the identity. For a constrained
        one it is `T A^-1 T^T`, where `T` carries chart velocity to world
        velocity and `A` is the reduced mass matrix - which comes out, after
        the algebra collapses, as

            k * [[1 + fz^2,  fx,        -fx fz  ],
                 [fx,        fx^2+fz^2,  fz     ],
                 [-fx fz,    fz,         1+fx^2 ]]

        with `k = 1 / (m_eff (1 + |grad f|^2))`. It is singular along the
        surface normal, which is exactly right: a marble cannot be pushed into
        the bowl, so an impulse in that direction produces no velocity change
        at all and the surface absorbs it. It is also what makes a marble hard
        to shove uphill and easy to shove along the wall, without any of that
        being special-cased.

        Returned flat, row-major, because it is built once per contact per
        tick and a nested tuple would allocate three more objects each time.
        """
        if marble.state == STATE_FREE:
            inverse = 1.0 / self.benchmark.marble_mass
            return (inverse, 0.0, 0.0, 0.0, inverse, 0.0, 0.0, 0.0, inverse)
        state = self.surface.state(marble.x, marble.z)
        fx, fz = state.grad_x, state.grad_z
        scale = 1.0 / (self.effective_mass * (1.0 + fx * fx + fz * fz))
        return (
            scale * (1.0 + fz * fz), scale * fx, scale * -fx * fz,
            scale * fx, scale * (fx * fx + fz * fz), scale * fz,
            scale * -fx * fz, scale * fz, scale * (1.0 + fx * fx),
        )

    @staticmethod
    def _quadratic(matrix: tuple[float, ...], vector: tuple[float, float, float]) -> float:
        ax, ay, az = vector
        return (
            ax * (matrix[0] * ax + matrix[1] * ay + matrix[2] * az)
            + ay * (matrix[3] * ax + matrix[4] * ay + matrix[5] * az)
            + az * (matrix[6] * ax + matrix[7] * ay + matrix[8] * az)
        )

    def _apply_impulse(
        self, marble: SurfaceMarble, impulse: tuple[float, float, float]
    ) -> None:
        """Push a marble with a 3D impulse, whichever phase it is in.

        A free marble takes it directly. A constrained one takes
        `A^-1 T^T J` in the chart, which is the projection onto its allowed
        tangent state falling out of the algebra rather than being applied
        afterwards. The component of the impulse along the surface normal is
        silently absorbed by the bowl, which is what a bowl does.
        """
        jx, jy, jz = impulse
        if marble.state == STATE_FREE:
            inverse = 1.0 / self.benchmark.marble_mass
            marble.wx += jx * inverse
            marble.wy += jy * inverse
            marble.wz += jz * inverse
            return
        state = self.surface.state(marble.x, marble.z)
        fx, fz = state.grad_x, state.grad_z
        scale = 1.0 / (self.effective_mass * (1.0 + fx * fx + fz * fz))
        # T^T J
        gx, gz = jx + fx * jy, jz + fz * jy
        marble.vx += scale * ((1.0 + fz * fz) * gx - fx * fz * gz)
        marble.vz += scale * (-fx * fz * gx + (1.0 + fx * fx) * gz)
        self._sync_world(marble)

    def _resolve_pair(
        self, first: SurfaceMarble, second: SurfaceMarble, touching: set[tuple[int, int]]
    ) -> bool:
        """One sphere-sphere contact, as a genuine 3D impulse. True if it fired."""
        radius = self.benchmark.marble_radius
        dx = second.px - first.px
        dy = second.py - first.py
        dz = second.pz - first.pz
        distance = math.sqrt(dx * dx + dy * dy + dz * dz)
        if distance >= 2.0 * radius or distance <= 1e-12:
            return False
        pair = (first.marble_id, second.marble_id)
        touching.add(pair)

        normal = (dx / distance, dy / distance, dz / distance)
        relative = (
            second.wx - first.wx,
            second.wy - first.wy,
            second.wz - first.wz,
        )
        approach = sum(a * b for a, b in zip(relative, normal))
        if approach >= 0.0:
            return False  # already separating; the overlap pass will finish it

        weight_a = self.inverse_mass(first)
        weight_b = self.inverse_mass(second)
        denominator = self._quadratic(weight_a, normal) + self._quadratic(weight_b, normal)
        if denominator <= 1e-12:
            # Both marbles are held rigidly against this direction. There is no
            # finite impulse; the bowl takes it.
            return False

        magnitude = -(1.0 + self.benchmark.restitution) * approach / denominator
        self._apply_impulse(first, tuple(-magnitude * value for value in normal))
        self._apply_impulse(second, tuple(magnitude * value for value in normal))

        # Coulomb friction along the contact tangent, recomputed from the
        # post-normal-impulse relative velocity so the two are not fighting.
        relative = (
            second.wx - first.wx,
            second.wy - first.wy,
            second.wz - first.wz,
        )
        along = sum(a * b for a, b in zip(relative, normal))
        tangent = tuple(r - along * n for r, n in zip(relative, normal))
        speed = math.sqrt(sum(value * value for value in tangent))
        if speed > 1e-9:
            direction = tuple(value / speed for value in tangent)
            resistance = self._quadratic(weight_a, direction) + self._quadratic(
                weight_b, direction
            )
            if resistance > 1e-12:
                wanted = speed / resistance
                limit = self.benchmark.friction * magnitude
                friction = min(wanted, limit)
                self._apply_impulse(first, tuple(friction * value for value in direction))
                self._apply_impulse(second, tuple(-friction * value for value in direction))

        if pair in self._touching:
            # Already resting against each other. The impulse above still has
            # to be applied every tick to keep them apart, but reporting it
            # every tick would turn one pile-up into hundreds of "collisions"
            # and make the count a measure of how long marbles touch rather
            # than how often they meet. Production reports contacts on
            # Chipmunk's `begin` for the same reason.
            return True

        first.collisions += 1
        second.collisions += 1
        self.events.append(
            LabEvent(
                time=self.elapsed,
                kind="collision",
                data={
                    "a": first.marble_id,
                    "b": second.marble_id,
                    "closing_speed": -approach,
                    "position": [
                        0.5 * (first.px + second.px),
                        0.5 * (first.py + second.py),
                        0.5 * (first.pz + second.pz),
                    ],
                },
            )
        )
        return True

    def _separate_overlaps(self) -> None:
        """Push overlapping marbles apart without changing any velocity.

        Position and velocity are corrected separately on purpose. Removing an
        overlap by adding velocity is how a pile-up turns into an explosion:
        the correction is proportional to the penetration, penetration is
        largest when several marbles are stacked, and the energy it injects is
        exactly when there is least room for it.
        """
        radius = self.benchmark.marble_radius
        active = [marble for marble in self.marbles if marble.active]
        for _ in range(SEPARATION_PASSES):
            worst = 0.0
            for index, first in enumerate(active):
                for second in active[index + 1:]:
                    dx = second.px - first.px
                    dy = second.py - first.py
                    dz = second.pz - first.pz
                    distance = math.sqrt(dx * dx + dy * dy + dz * dz)
                    overlap = 2.0 * radius - distance
                    if overlap <= 0.0 or distance <= 1e-12:
                        continue
                    worst = max(worst, overlap)
                    shift = SEPARATION_FRACTION * overlap * 0.5
                    normal = (dx / distance, dy / distance, dz / distance)
                    self._nudge(first, tuple(-shift * value for value in normal))
                    self._nudge(second, tuple(shift * value for value in normal))
            if worst <= 1e-9:
                break

    def _nudge(self, marble: SurfaceMarble, offset: tuple[float, float, float]) -> None:
        """Move a marble by a world offset, respecting its constraint.

        A free marble moves as asked. A constrained one keeps its height from
        the surface and takes only the horizontal part - which is the closest
        it can get to the requested displacement without leaving the bowl.
        """
        if marble.state == STATE_FREE:
            marble.px += offset[0]
            marble.py += offset[1]
            marble.pz += offset[2]
            return
        marble.x += offset[0]
        marble.z += offset[2]
        self._sync_world(marble)

    # --- phase transitions ----------------------------------------------

    def _release(self, marble: SurfaceMarble, reason: str) -> None:
        """The surface lets go. The marble keeps every number it had."""
        self._sync_world(marble)
        marble.state = STATE_FREE
        self.events.append(
            LabEvent(
                time=self.elapsed,
                kind="separated",
                data={
                    "id": marble.marble_id,
                    "reason": reason,
                    "radius": math.hypot(marble.px, marble.pz),
                    "position": list(marble.position),
                },
            )
        )

    def _try_land(self, marble: SurfaceMarble) -> None:
        """A falling marble meeting the dish again: bounce, or settle onto it."""
        radius = math.hypot(marble.px, marble.pz)
        if radius < self.surface.lip_start or radius > self.surface.max_radius:
            return  # over the drain, or past the edge of the world
        height = self.surface.height(radius)
        if marble.py > height:
            return

        normal = self.surface.normal(marble.px, marble.pz)
        into = marble.wx * normal[0] + marble.wy * normal[1] + marble.wz * normal[2]
        if into > 0.0:
            return  # already climbing away from the surface it is inside of

        marble.py = height
        rebound = -into * self.benchmark.surface_restitution
        if rebound < ATTACH_SPEED:
            # Settle. The tangential part of the velocity carries over intact
            # and becomes the chart velocity; the normal part is absorbed.
            marble.x, marble.z = marble.px, marble.pz
            marble.vx = marble.wx - into * normal[0]
            marble.vz = marble.wz - into * normal[2]
            marble.state = STATE_SURFACE
            self._sync_world(marble)
            self._set_rolling_spin(marble)
            self.events.append(
                LabEvent(
                    time=self.elapsed,
                    kind="landed",
                    data={"id": marble.marble_id, "radius": radius, "impact_speed": -into},
                )
            )
            return
        marble.wx += (rebound - into) * normal[0]
        marble.wy += (rebound - into) * normal[1]
        marble.wz += (rebound - into) * normal[2]

    def _set_rolling_spin(self, marble: SurfaceMarble) -> None:
        """`omega = (n x v) / r`: the spin of a marble already rolling."""
        normal = self.surface.normal(marble.x, marble.z)
        radius = self.benchmark.marble_radius
        marble.ox = (normal[1] * marble.wz - normal[2] * marble.wy) / radius
        marble.oy = (normal[2] * marble.wx - normal[0] * marble.wz) / radius
        marble.oz = (normal[0] * marble.wy - normal[1] * marble.wx) / radius

    def _retire(self, marble: SurfaceMarble, state: str, kind: str) -> None:
        marble.state = state
        marble.drain_time = self.elapsed
        self._exit_count += 1
        marble.exit_order = self._exit_count
        self.events.append(
            LabEvent(
                time=self.elapsed,
                kind=kind,
                data={
                    "id": marble.marble_id,
                    "order": marble.exit_order,
                    "position": list(marble.position),
                },
            )
        )

    # --- the clock ------------------------------------------------------

    def step(self) -> None:
        """One fixed tick. Integrate, transition, collide, separate."""
        dt = self.dt
        gravity = self.benchmark.gravity
        shaft_limit = self.benchmark.drain_radius - self.benchmark.marble_radius

        for marble in self.marbles:
            if marble.state == STATE_SURFACE:
                ax, az, normal_force = self.acceleration(marble)
                if normal_force < RELEASE_NORMAL_FORCE:
                    self._release(marble, "normal force reached zero")
                else:
                    self._advance_on_surface(marble, ax, az, normal_force, dt)

            if marble.state == STATE_FREE:
                marble.wy -= gravity * dt
                marble.px += marble.wx * dt
                marble.py += marble.wy * dt
                marble.pz += marble.wz * dt
                self._try_land(marble)

        self._collide()
        self._separate_overlaps()

        for marble in self.marbles:
            if not marble.active:
                continue
            marble.quat = _quat_integrate(marble.quat, (marble.ox, marble.oy, marble.oz), dt)
            if marble.state == STATE_FREE:
                self._constrain_to_shaft(marble, shaft_limit)
                if marble.py <= self.benchmark.drain_exit_y:
                    self._retire(marble, STATE_DRAINED, "drained")
                    continue
            radius = math.hypot(marble.px, marble.pz)
            if radius > self.surface.max_radius:
                self._retire(marble, STATE_ESCAPED, "escaped")
            elif not all(
                math.isfinite(value)
                for value in (marble.px, marble.py, marble.pz, marble.wx, marble.wy, marble.wz)
            ):
                self.failure = f"marble {marble.marble_id} left the real numbers"

        self.ticks += 1
        self.elapsed = self.ticks * dt

    def _constrain_to_shaft(self, marble: SurfaceMarble, limit: float) -> None:
        """The drain shaft is a real tube, not a hole marbles vanish into.

        Without it a marble released at the lip with an inward velocity sails
        straight across the drain and out the far side under the dish, which
        looks like a bug and is one.
        """
        if marble.py > self.surface.lip_pivot_y:
            return
        radius = math.hypot(marble.px, marble.pz)
        if radius <= limit or radius <= 1e-12:
            return
        nx, nz = marble.px / radius, marble.pz / radius
        marble.px, marble.pz = nx * limit, nz * limit
        outward = marble.wx * nx + marble.wz * nz
        if outward > 0.0:
            bounce = (1.0 + self.benchmark.surface_restitution) * outward
            marble.wx -= bounce * nx
            marble.wz -= bounce * nz

    def _collide(self) -> None:
        """Every pair, in marble-id order.

        Eight marbles is twenty-eight pairs and a broad phase would cost more
        than it saved. The *order* is fixed rather than incidental for the same
        reason `RaceSimulation._apply_kicks` sorts: a sequential solver's
        result depends on the order contacts are resolved in, and an order that
        came out of a spatial hash would make the run depend on where things
        happened to be in memory.
        """
        active = [marble for marble in self.marbles if marble.active]
        touching: set[tuple[int, int]] = set()
        for index, first in enumerate(active):
            for second in active[index + 1:]:
                self._resolve_pair(first, second, touching)
        self._touching = touching

    # --- reading the run ------------------------------------------------

    def sample(self) -> FrameSample:
        return FrameSample(
            time=self.elapsed,
            marbles=tuple(
                MarbleSample(
                    marble_id=marble.marble_id,
                    position=marble.position,
                    velocity=marble.velocity,
                    orientation=marble.quat,
                    spin=(marble.ox, marble.oy, marble.oz),
                    state=marble.state,
                )
                for marble in self.marbles
            ),
        )

    def mechanical_energy(self) -> float:
        """`m g y + (1/2) m |v|^2 + (1/2) I |omega|^2`, over the active marbles.

        Drained marbles are dropped from the total rather than kept at their
        exit energy, because a total that includes them cannot fall to zero and
        the interesting question is whether the marbles still in the bowl are
        losing energy for reasons the model can account for.
        """
        mass = self.benchmark.marble_mass
        inertia = self.inertia_factor * mass * self.benchmark.marble_radius ** 2
        total = 0.0
        for marble in self.marbles:
            if not marble.active:
                continue
            speed_squared = marble.wx ** 2 + marble.wy ** 2 + marble.wz ** 2
            spin_squared = marble.ox ** 2 + marble.oy ** 2 + marble.oz ** 2
            total += (
                mass * self.benchmark.gravity * marble.py
                + 0.5 * mass * speed_squared
                + 0.5 * inertia * spin_squared
            )
        return total

    @property
    def finished(self) -> bool:
        return self.failure is not None or not any(marble.active for marble in self.marbles)


def simulate(spec: RunSpec, duration: float | None = None) -> LabRun:
    """Run one bowl benchmark to completion and return its time series."""
    benchmark = spec.benchmark
    limit = benchmark.duration_limit if duration is None else duration
    sim = SurfaceBowlSim(spec)
    stride = benchmark.ticks_per_sample
    max_ticks = int(round(limit * benchmark.physics_hz))

    run = LabRun(
        approach=APPROACH,
        seed=spec.seed,
        physics_hz=benchmark.physics_hz,
        sample_hz=benchmark.sample_hz,
        benchmark=spec.to_json()["benchmark"],
        starts=spec.to_json()["starts"],
    )
    run.frames.append(sim.sample())
    energies = [sim.mechanical_energy()]

    while sim.ticks < max_ticks and not sim.finished:
        sim.step()
        if sim.ticks % stride == 0:
            run.frames.append(sim.sample())
            energies.append(sim.mechanical_energy())
    if sim.ticks % stride:
        # The last marble rarely leaves on a sample boundary, and without this
        # the frames never show it gone: the run ends, the loop exits, and the
        # final state is the one from up to a sample earlier. Anything reading
        # the frames rather than the events would count it as stuck.
        run.frames.append(sim.sample())
        energies.append(sim.mechanical_energy())

    run.events = sim.events
    run.stats = {
        "ticks": sim.ticks,
        "sim_seconds": sim.elapsed,
        "failure": sim.failure,
        "drained": sum(1 for marble in sim.marbles if marble.state == STATE_DRAINED),
        "escaped": sum(1 for marble in sim.marbles if marble.state == STATE_ESCAPED),
        "still_going": sum(1 for marble in sim.marbles if marble.active),
        "collisions": sum(marble.collisions for marble in sim.marbles) // 2,
        "energy_first": energies[0],
        "energy_last": energies[-1],
    }
    return run

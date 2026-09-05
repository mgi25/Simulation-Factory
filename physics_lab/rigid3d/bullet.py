"""Approach B: true 3D rigid bodies, in PyBullet, with Python still in charge.

Eight `btRigidBody` spheres, a static triangle mesh of the bowl, gravity, and
nothing else. No script drives a marble anywhere: the spiral, the wall
following, the orbit decay and the drain order all have to come out of sphere
geometry, contact friction and a dish, or they do not come out at all.

## Why PyBullet rather than Godot

Because it answers the question the study is actually asking. The production
architecture is *Python authoritative -> deterministic replay -> Godot draws
it*, and its value is almost entirely in the first arrow. If real 3D physics
can live where pymunk lives now, every downstream property survives: the seed
search, the offline render, the byte-exact replay, the whole pipeline. Godot
is measured too, in `godot.py`, but making Godot authoritative inverts the
architecture - physics would live downstream of the replay it is supposed to
produce - so it is a different proposal and is reported as one.

The cost is real and is not hidden: on Windows with Python 3.13 there is no
PyBullet wheel, and pip builds a 76.8 MB source tarball against the MSVC 2022
build tools. It works. It is a compiler dependency on every machine that would
ever run a simulation.

## Making it comparable rather than merely similar

Four things are done specifically so that a difference between this and the
2.5D run is a difference in the *physics* and not in the setup.

* The collider is the centre surface offset by one marble radius, so a sphere
  at rest here has its centre where the Python constraint would put it.
* Every sphere is started with the run spec's exact position, velocity **and
  spin**, so it is already rolling. Without the spin a rigid-body marble
  spends its first tenth of a second converting slip into rotation and the
  2.5D marble does not.
* Linear and angular damping are set to the same coefficient. For a sphere
  held in rolling contact that decays `v` and `omega` together, preserving
  the rolling condition and giving `dv/dt = -k v` - the same exponential the
  2.5D model applies. Bullet's damping is `v *= (1 - d)^dt`, so the
  coefficient that produces rate `k` is `1 - exp(-k)`, not `k`.
* Contacts are reported on *begin*, matching both the 2.5D prototype and the
  production race, so a pile-up is one collision rather than one per tick.

## What is genuinely different, and is the point

Rolling here is a consequence of Coulomb friction at a contact rather than an
assumption. A marble that hits a wall too fast to grip *will* skid, and the
`rolling_ratio` metric will say so. Spin is a real vector with real
gyroscopic behaviour. Contacts are solved simultaneously by a sequential
impulse solver with a penetration budget, so marbles can and do overlap
slightly. Those three are exactly the approximations the 2.5D model makes, and
whether they show up in the picture is what the comparison is for.
"""

from __future__ import annotations

import math
import os

from physics_lab.common.benchmark import RunSpec
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
from physics_lab.rigid3d.mesh import (
    DEFAULT_RINGS,
    DEFAULT_SEGMENTS,
    build_bowl_mesh,
    cached_obj,
    worst_sagitta,
)

__all__ = ["APPROACH", "BulletBowlSim", "simulate", "damping_coefficient"]

APPROACH = "rigid3d"

# Bullet's default is 10. Swept over the twenty benchmark seeds; see the
# comparison document. The measurement is in the report rather than asserted
# here.
SOLVER_ITERATIONS = 40

# --- world scale ----------------------------------------------------------
#
# The single most consequential number in this file, and it was found the hard
# way. Bullet is tuned for objects around a metre across: `btCollisionShape`'s
# default collision margin is 0.04 world units, which against this benchmark's
# 0.02 m marble is *twice the marble's radius*. The first working version of
# this prototype put a marble at rest on the wall and Bullet flung it from
# radius 0.30 to 0.43 inside half a second, gaining 0.7 m/s out of nothing,
# because every contact was being generated a margin deep and pushed out
# accordingly. Nothing about that is a fact about rigid-body physics; it is a
# fact about running a physics engine 50 times below the scale it expects.
#
# So the benchmark is simulated at 25x and reported at 1x. Lengths, velocities
# and gravity all scale by the same factor, which leaves *time* unchanged and
# every trajectory geometrically similar - so the run that comes back is the
# benchmark's run, in the benchmark's seconds, at the benchmark's size.
#
# This is worth carrying into any real decision about this architecture: a 3D
# engine imposes a working scale on the whole project, and a marble machine
# would have to be authored at engine scale rather than at toy scale.
WORLD_SCALE = 25.0

# Mass in the scaled world. Every marble has the same mass, the bowl is static
# and nothing else applies a force, so mass cancels out of every trajectory
# here exactly - and one is far better conditioned for the solver than the
# 1300 kg that density-consistent scaling of an 84 g marble would produce. The
# benchmark's real mass is what the energy metrics are computed with.
SCALED_MASS = 1.0

# The collision margin on the bowl trimesh, in scaled world units, against a
# marble of radius 0.5 there. Bullet's default is 0.04 and is a fifth of that
# again on top of the shape; the sweep in the comparison document is what
# chose this. `None` leaves Bullet's default in place.
COLLISION_MARGIN = 0.001

# Where the collider OBJ is written. Outside the repository: it is a build
# artifact of the benchmark, reproducible from the configuration, and a
# 26000-vertex mesh is not something to commit.
MESH_CACHE = os.path.join("output", "physics_lab", "meshes")


def damping_coefficient(rate: float) -> float:
    """Bullet's per-second damping fraction for an exponential decay rate.

    Bullet multiplies velocity by `(1 - d)^dt` every step, so the decay is
    `exp(dt ln(1 - d))` and `d = 1 - exp(-k)`. Passing `k` straight in - which
    is the obvious thing to do and is wrong - would decay 15% too fast at
    k = 0.25, and the two prototypes would be drained by different bowls.
    """
    return 1.0 - math.exp(-rate)


class BulletBowlSim:
    """The bowl benchmark, with a rigid-body engine owning the physics."""

    def __init__(
        self,
        spec: RunSpec,
        segments: int = DEFAULT_SEGMENTS,
        rings: int = DEFAULT_RINGS,
        solver_iterations: int = SOLVER_ITERATIONS,
        collision_margin: float | None = COLLISION_MARGIN,
        split_impulse: int = 1,
        internal_edge: bool = True,
    ) -> None:
        import pybullet

        self.pybullet = pybullet
        self.tuning = {
            "segments": segments,
            "rings": rings,
            "solver_iterations": solver_iterations,
            "collision_margin": collision_margin,
            "split_impulse": split_impulse,
            "internal_edge": bool(internal_edge),
        }
        self.spec = spec
        self.benchmark = spec.benchmark
        self.surface = self.benchmark.surface()
        self.dt = self.benchmark.dt
        self.ticks = 0
        self.elapsed = 0.0
        self.events: list[LabEvent] = []
        self.failure: str | None = None
        self._exit_count = 0
        self._touching: set[tuple[int, int]] = set()

        self.scale = WORLD_SCALE
        self.client = pybullet.connect(pybullet.DIRECT)
        pybullet.resetSimulation(physicsClientId=self.client)
        pybullet.setGravity(
            0.0, -self.benchmark.gravity * self.scale, 0.0, physicsClientId=self.client
        )
        pybullet.setPhysicsEngineParameter(
            fixedTimeStep=self.dt,
            numSubSteps=1,
            numSolverIterations=solver_iterations,
            useSplitImpulse=split_impulse,
            # The one setting that matters for reproducibility: without it the
            # broadphase pair order depends on allocation addresses, and the
            # solver is order-dependent, so the same run gives different
            # answers between processes.
            deterministicOverlappingPairs=1,
            physicsClientId=self.client,
        )

        internal_edge = pybullet.GEOM_CONCAVE_INTERNAL_EDGE if internal_edge else 0
        self.mesh = build_bowl_mesh(
            self.surface,
            self.benchmark.drain_exit_y,
            rings=rings,
            segments=segments,
        )
        self.sagitta = worst_sagitta(self.surface, segments)
        self.mesh_path = cached_obj(self.mesh, MESH_CACHE)
        shape = pybullet.createCollisionShape(
            pybullet.GEOM_MESH,
            fileName=self.mesh_path,
            meshScale=[self.scale, self.scale, self.scale],
            flags=pybullet.GEOM_FORCE_CONCAVE_TRIMESH | internal_edge,
            physicsClientId=self.client,
        )
        self.bowl = pybullet.createMultiBody(
            baseMass=0.0, baseCollisionShapeIndex=shape, physicsClientId=self.client
        )
        # Bullet combines friction by *multiplying* the two bodies' values, so
        # neither number here is the coefficient it produces. Give the marble
        # the square root of the marble-on-marble figure and the bowl whatever
        # makes the product come out at the marble-on-bowl figure, and both
        # pairs get what the benchmark asked for. Setting both to `friction`
        # directly - the obvious thing - gives 0.15 x 0.15 = 0.0225 against a
        # wall that needs 0.230 to sustain rolling, and the marbles skid the
        # whole way down. Measured: the rolling ratio came out at 1.58 rather
        # than 1.00, and a passive orbit lost half its energy in under a second.
        self.marble_friction = math.sqrt(self.benchmark.friction)
        self.bowl_friction = self.benchmark.surface_friction / self.marble_friction
        bowl_settings = dict(
            lateralFriction=self.bowl_friction,
            restitution=self.benchmark.surface_restitution,
        )
        if collision_margin is not None:
            bowl_settings["collisionMargin"] = collision_margin
        pybullet.changeDynamics(self.bowl, -1, physicsClientId=self.client, **bowl_settings)

        damping = damping_coefficient(self.benchmark.linear_damping)
        sphere = pybullet.createCollisionShape(
            pybullet.GEOM_SPHERE,
            radius=self.benchmark.marble_radius * self.scale,
            physicsClientId=self.client,
        )
        self.bodies: dict[int, int] = {}
        self.state: dict[int, str] = {}
        self.exit_order: dict[int, int] = {}
        for start in spec.starts:
            body = pybullet.createMultiBody(
                baseMass=SCALED_MASS,
                baseCollisionShapeIndex=sphere,
                basePosition=[value * self.scale for value in start.position],
                physicsClientId=self.client,
            )
            pybullet.resetBaseVelocity(
                body,
                linearVelocity=[value * self.scale for value in start.velocity],
                # Angular velocity is v/r and both scale together, so spin is
                # the one quantity that carries across untouched.
                angularVelocity=list(start.spin),
                physicsClientId=self.client,
            )
            pybullet.changeDynamics(
                body,
                -1,
                lateralFriction=self.marble_friction,
                restitution=self.benchmark.restitution,
                linearDamping=damping,
                angularDamping=damping,
                # Off, both of them. Bullet's rolling and spinning friction are
                # a different dissipation model from the one the benchmark
                # calibrates, and leaving them at anything but zero would mean
                # the two prototypes were losing energy for different reasons.
                rollingFriction=0.0,
                spinningFriction=0.0,
                physicsClientId=self.client,
            )
            self.bodies[start.marble_id] = body
            self.state[start.marble_id] = STATE_SURFACE

    # --- reading the engine ---------------------------------------------

    def _pose(self, marble_id: int):
        """A marble's state, back in the benchmark's units.

        Everything inside the engine is `WORLD_SCALE` times life size; nothing
        outside this method ever sees that.
        """
        body = self.bodies[marble_id]
        position, orientation = self.pybullet.getBasePositionAndOrientation(
            body, physicsClientId=self.client
        )
        velocity, spin = self.pybullet.getBaseVelocity(body, physicsClientId=self.client)
        inverse = 1.0 / self.scale
        return (
            tuple(value * inverse for value in position),
            tuple(orientation),
            tuple(value * inverse for value in velocity),
            tuple(spin),
        )

    def _retire(self, marble_id: int, state: str, kind: str) -> None:
        position = self._pose(marble_id)[0]
        self.pybullet.removeBody(self.bodies[marble_id], physicsClientId=self.client)
        self._last_pose[marble_id] = (
            position,
            self._last_pose[marble_id][1],
            (0.0, 0.0, 0.0),
            (0.0, 0.0, 0.0),
        )
        del self.bodies[marble_id]
        self.state[marble_id] = state
        self._exit_count += 1
        self.exit_order[marble_id] = self._exit_count
        self.events.append(
            LabEvent(
                time=self.elapsed,
                kind=kind,
                data={
                    "id": marble_id,
                    "order": self._exit_count,
                    "position": list(position),
                },
            )
        )

    # --- the clock ------------------------------------------------------

    def step(self) -> None:
        pybullet = self.pybullet
        pybullet.stepSimulation(physicsClientId=self.client)
        self.ticks += 1
        self.elapsed = self.ticks * self.dt

        touching: set[tuple[int, int]] = set()
        by_body = {body: marble_id for marble_id, body in self.bodies.items()}
        in_contact: set[int] = set()
        for contact in pybullet.getContactPoints(physicsClientId=self.client):
            body_a, body_b = contact[1], contact[2]
            if body_a == self.bowl or body_b == self.bowl:
                other = body_b if body_a == self.bowl else body_a
                if other in by_body:
                    in_contact.add(by_body[other])
                continue
            if body_a not in by_body or body_b not in by_body:
                continue
            first, second = sorted((by_body[body_a], by_body[body_b]))
            pair = (first, second)
            if pair in touching:
                continue
            touching.add(pair)
            if pair in self._touching:
                continue
            velocity_a = self._pose(first)[2]
            velocity_b = self._pose(second)[2]
            normal = contact[7]
            closing = abs(sum((b - a) * n for a, b, n in zip(velocity_a, velocity_b, normal)))
            self.events.append(
                LabEvent(
                    time=self.elapsed,
                    kind="collision",
                    data={
                        "a": first,
                        "b": second,
                        "closing_speed": closing,
                        "position": [value / self.scale for value in contact[5]],
                    },
                )
            )
        self._touching = touching

        for marble_id in list(self.bodies):
            position, orientation, velocity, spin = self._pose(marble_id)
            self._last_pose[marble_id] = (position, orientation, velocity, spin)
            if not all(math.isfinite(value) for value in position + velocity):
                self.failure = f"marble {marble_id} left the real numbers"
                continue
            # "In contact with the bowl" is the honest analogue of the 2.5D
            # surface phase. There is no constraint here to be on or off, only
            # a contact to have or not have.
            self.state[marble_id] = STATE_SURFACE if marble_id in in_contact else STATE_FREE
            if position[1] <= self.benchmark.drain_exit_y:
                self._retire(marble_id, STATE_DRAINED, "drained")
            elif math.hypot(position[0], position[2]) > self.surface.max_radius:
                self._retire(marble_id, STATE_ESCAPED, "escaped")

    # --- sampling -------------------------------------------------------

    _last_pose: dict[int, tuple]

    def prime(self) -> None:
        self._last_pose = {
            start.marble_id: (
                start.position,
                (0.0, 0.0, 0.0, 1.0),
                start.velocity,
                start.spin,
            )
            for start in self.spec.starts
        }

    def sample(self) -> FrameSample:
        marbles = []
        for start in self.spec.starts:
            marble_id = start.marble_id
            if marble_id in self.bodies:
                position, orientation, velocity, spin = self._pose(marble_id)
            else:
                position, orientation, velocity, spin = self._last_pose[marble_id]
            marbles.append(
                MarbleSample(
                    marble_id=marble_id,
                    position=tuple(float(value) for value in position),
                    velocity=tuple(float(value) for value in velocity),
                    orientation=tuple(float(value) for value in orientation),
                    spin=tuple(float(value) for value in spin),
                    state=self.state[marble_id],
                )
            )
        return FrameSample(time=self.elapsed, marbles=tuple(marbles))

    @property
    def finished(self) -> bool:
        return self.failure is not None or not self.bodies

    def close(self) -> None:
        self.pybullet.disconnect(physicsClientId=self.client)


def simulate(spec: RunSpec, duration: float | None = None) -> LabRun:
    """Run one bowl benchmark in PyBullet and return its time series."""
    benchmark = spec.benchmark
    limit = benchmark.duration_limit if duration is None else duration
    sim = BulletBowlSim(spec)
    sim.prime()
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
    try:
        run.frames.append(sim.sample())
        while sim.ticks < max_ticks and not sim.finished:
            sim.step()
            if sim.ticks % stride == 0:
                run.frames.append(sim.sample())
        if sim.ticks % stride:
            run.frames.append(sim.sample())

        run.events = sim.events
        run.stats = {
            "ticks": sim.ticks,
            "sim_seconds": sim.elapsed,
            "failure": sim.failure,
            "engine": "pybullet",
            "tuning": sim.tuning,
            "mesh_triangles": sim.mesh.triangle_count,
            "mesh_worst_sagitta": sim.sagitta,
            "marble_friction": sim.marble_friction,
            "bowl_friction": sim.bowl_friction,
            "damping_coefficient": damping_coefficient(benchmark.linear_damping),
            "drained": sum(
                1 for state in sim.state.values() if state == STATE_DRAINED
            ),
            "escaped": sum(1 for state in sim.state.values() if state == STATE_ESCAPED),
            "still_going": len(sim.bodies),
            "collisions": sum(1 for event in sim.events if event.kind == "collision"),
        }
    finally:
        sim.close()
    return run

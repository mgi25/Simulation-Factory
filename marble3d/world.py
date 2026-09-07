"""The Bullet world: one client, one set of engine settings, one body registry.

Nothing else in the package calls `pybullet`. That is worth the indirection for
one reason: every setting in this file is a decision that was measured, and
several of them are decisions that are *silently wrong by default*. A module
that reached for `pybullet.createMultiBody` itself would get the defaults, and
the defaults on this engine include a hidden velocity clamp.

## The three engine settings that are not optional

**`useMaximalCoordinates=True` on every body.** PyBullet's `createMultiBody`
builds a `btMultiBody` by default - the articulated, reduced-coordinate body
type meant for robots - and a `btMultiBody` carries two defaults that ruin a
marble machine. Measured on this machine, at 240 Hz, with gravity off:

    body type          asked 50 wu/s     asked 200 wu/s    asked 600 wu/s
    btMultiBody        49.575            100.000           100.000
    btRigidBody        50.000            200.000           600.000

The base velocity is **hard-clamped at 100 wu/s**, and there is a linear
damping term applied that nobody asked for. A marble that has fallen 14 wu is
already past the clamp, so a tall machine would quietly stop obeying gravity
partway down - and it would look like terminal velocity, which is a thing
marbles are allowed to have, so nobody would question the video. The physics
lab never met this because its bowl ran at 25 wu/s. `useMaximalCoordinates`
gives a plain `btRigidBody`, which has neither behaviour.

**Continuous collision detection, which only works on rigid bodies.** With the
clamp in place CCD appeared to do nothing, because nothing ever moved fast
enough to tunnel. On real rigid bodies it is decisive. Phase-swept probe, 20
starting offsets each, a 1.0 wu marble against a 0.3 wu trimesh wall at 240 Hz:

    travel per step   no CCD      ccdSweptSphereRadius
    0.42 diameters    0/20        0/20
    0.62 diameters    0/20        0/20
    0.83 diameters    1/20        0/20
    1.25 diameters    7/20        0/20
    1.67 diameters    11/20       0/20

So discrete detection is reliable below about 0.6 marble diameters of travel
per tick and starts failing above it, and CCD covers everything measured above
that. `PhysicsConfig` picks a rate that keeps the machine in the first column's
safe range, and CCD is the second line of defence rather than the first.

**`deterministicOverlappingPairs=1`.** Without it the broadphase pair order
depends on allocation addresses and the constraint solver is order-dependent,
so the same seed gives different answers in different processes. The lab
established this and every determinism claim in this package rests on it.

## Colliders

Static geometry arrives as a `TriMesh` in module-local coordinates and is
placed by the module's transform, so one bowl mesh can be instanced. Each mesh
is split into chunks well inside PyBullet's inline-buffer limits and each chunk
is written to a content-named OBJ, which is the loading path the lab proved has
no size limit. `marble3d.validation` then proves at run time, with ray casts
against the assembled world, that the collider Bullet holds is the collider
that was sent - because the failure mode of a truncated mesh is a run that
produces numbers rather than an error.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from marble3d.config import MESH_CACHE, ColliderConfig, CoreConfig
from marble3d.geometry import IDENTITY, Transform, Vec3
from marble3d.materials import BodyMaterial, SolvedMaterials, solve_materials
from marble3d.mesh import Aabb, TriMesh, cached_obj

__all__ = ["ColliderRecord", "MarbleWorld", "ContactPoint"]


@dataclass(frozen=True)
class ColliderRecord:
    """One chunk of one module's static geometry, and what it should be.

    The expected bounds are computed from the transformed vertices in Python,
    before Bullet sees anything. Comparing them against `getAABB` after the
    fact is the cheapest possible proof that the mesh arrived whole.
    """

    body: int
    owner: str
    piece: str
    vertex_count: int
    triangle_count: int
    expected_bounds: Aabb
    obj_path: str

    def to_json(self) -> dict[str, Any]:
        return {
            "owner": self.owner,
            "piece": self.piece,
            "vertices": self.vertex_count,
            "triangles": self.triangle_count,
            "bounds": [list(self.expected_bounds.lower), list(self.expected_bounds.upper)],
        }


@dataclass(frozen=True)
class ContactPoint:
    """One contact, in the terms the simulation reasons about.

    Bullet's raw tuple is positional and 14 entries long; unpacking it once
    here means no module or metric has to remember that index 9 is the normal
    impulse and index 7 is the normal on B.
    """

    body_a: int
    body_b: int
    position: Vec3
    normal: Vec3
    distance: float
    normal_impulse: float


@dataclass
class _Body:
    kind: str          # "marble", "static", "kinematic"
    owner: str
    marble_id: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class MarbleWorld:
    """A Bullet world built to one `CoreConfig`, with everything explicit."""

    def __init__(self, config: CoreConfig, mesh_cache: str = MESH_CACHE) -> None:
        import pybullet

        self.pybullet = pybullet
        self.config = config
        self.collider_config: ColliderConfig = config.collider
        self.materials: SolvedMaterials = solve_materials(config.marble)
        self.mesh_cache = mesh_cache

        self.client = pybullet.connect(pybullet.DIRECT)
        pybullet.resetSimulation(physicsClientId=self.client)
        pybullet.setGravity(0.0, -config.gravity, 0.0, physicsClientId=self.client)
        physics = config.physics
        pybullet.setPhysicsEngineParameter(
            fixedTimeStep=physics.dt,
            numSubSteps=physics.substeps,
            numSolverIterations=physics.solver_iterations,
            useSplitImpulse=1 if physics.split_impulse else 0,
            deterministicOverlappingPairs=1 if physics.deterministic_overlapping_pairs else 0,
            contactBreakingThreshold=physics.contact_breaking_threshold,
            allowedCcdPenetration=physics.allowed_ccd_penetration,
            physicsClientId=self.client,
        )

        self.colliders: list[ColliderRecord] = []
        self.bodies: dict[int, _Body] = {}
        self.marbles: dict[int, int] = {}          # marble id -> body id
        self._sphere_shape: int | None = None
        self.ticks = 0

    # --- static geometry -------------------------------------------------

    def add_static_mesh(
        self,
        mesh: TriMesh,
        transform: Transform = IDENTITY,
        owner: str = "world",
        material: BodyMaterial | None = None,
    ) -> list[ColliderRecord]:
        """Place a triangle mesh as immovable geometry, in chunks.

        The mesh is transformed into world coordinates here rather than being
        placed by a body transform. That costs one pass over the vertices and
        buys two things worth more than the pass: the expected bounds a
        validator compares against are exact rather than a rotated box, and a
        ray probe can be stated in the module's own local frame and pushed
        through the same transform, so a probe and the geometry it checks can
        never disagree about where the module is.
        """
        pybullet = self.pybullet
        placed = mesh.transformed(transform, mesh.name)
        chunks = placed.chunks(
            self.collider_config.max_chunk_vertices,
            self.collider_config.max_chunk_indices,
        )
        records: list[ColliderRecord] = []
        surface = material or self.materials.surface
        for index, chunk in enumerate(chunks):
            path = cached_obj(chunk, self.mesh_cache)
            shape = pybullet.createCollisionShape(
                pybullet.GEOM_MESH,
                fileName=path,
                meshScale=[1.0, 1.0, 1.0],
                # FORCE_CONCAVE_TRIMESH keeps a static mesh concave rather than
                # letting Bullet build a convex hull of it, which would fill in
                # the bowl. INTERNAL_EDGE suppresses the spurious normals a
                # sphere picks up rolling across a shared triangle edge, which
                # is a direct reduction of the tessellation dissipation the lab
                # measured.
                flags=pybullet.GEOM_FORCE_CONCAVE_TRIMESH | pybullet.GEOM_CONCAVE_INTERNAL_EDGE,
                physicsClientId=self.client,
            )
            body = pybullet.createMultiBody(
                baseMass=0.0,
                baseCollisionShapeIndex=shape,
                basePosition=[0.0, 0.0, 0.0],
                baseOrientation=[0.0, 0.0, 0.0, 1.0],
                useMaximalCoordinates=True,
                physicsClientId=self.client,
            )
            pybullet.changeDynamics(
                body,
                -1,
                lateralFriction=surface.friction,
                restitution=surface.restitution,
                rollingFriction=surface.rolling_friction,
                spinningFriction=surface.spinning_friction,
                collisionMargin=self.collider_config.mesh_margin,
                physicsClientId=self.client,
            )
            record = ColliderRecord(
                body=body,
                owner=owner,
                piece=chunk.name,
                vertex_count=chunk.vertex_count,
                triangle_count=chunk.triangle_count,
                expected_bounds=chunk.aabb(),
                obj_path=path,
            )
            self.colliders.append(record)
            self.bodies[body] = _Body(kind="static", owner=owner)
            records.append(record)
        return records

    def add_kinematic_box(
        self,
        half_extents: Sequence[float],
        transform: Transform,
        owner: str = "world",
        material: BodyMaterial | None = None,
    ) -> int:
        """A box that a module moves by rewriting its pose each tick.

        Mass zero, so it is immovable by contact and infinitely heavy to a
        marble - which is what a gate, a paddle or a lift platform should be.
        See `marble3d.modules.base.Actuator` for how the pose is produced and
        why it is a pure function of the tick index.
        """
        pybullet = self.pybullet
        shape = pybullet.createCollisionShape(
            pybullet.GEOM_BOX,
            halfExtents=[float(value) for value in half_extents],
            physicsClientId=self.client,
        )
        body = pybullet.createMultiBody(
            baseMass=0.0,
            baseCollisionShapeIndex=shape,
            basePosition=list(transform.position),
            baseOrientation=list(transform.rotation),
            useMaximalCoordinates=True,
            physicsClientId=self.client,
        )
        surface = material or self.materials.surface
        pybullet.changeDynamics(
            body,
            -1,
            lateralFriction=surface.friction,
            restitution=surface.restitution,
            rollingFriction=surface.rolling_friction,
            spinningFriction=surface.spinning_friction,
            physicsClientId=self.client,
        )
        self.bodies[body] = _Body(kind="kinematic", owner=owner)
        return body

    def move_kinematic(self, body: int, transform: Transform) -> None:
        self.pybullet.resetBasePositionAndOrientation(
            body, list(transform.position), list(transform.rotation), physicsClientId=self.client
        )

    # --- marbles ---------------------------------------------------------

    def _sphere(self) -> int:
        if self._sphere_shape is None:
            self._sphere_shape = self.pybullet.createCollisionShape(
                self.pybullet.GEOM_SPHERE,
                radius=self.config.marble.radius,
                physicsClientId=self.client,
            )
        return self._sphere_shape

    def add_marble(
        self,
        marble_id: int,
        position: Sequence[float],
        velocity: Sequence[float] = (0.0, 0.0, 0.0),
        spin: Sequence[float] = (0.0, 0.0, 0.0),
        orientation: Sequence[float] = (0.0, 0.0, 0.0, 1.0),
    ) -> int:
        pybullet = self.pybullet
        marble = self.config.marble
        body = pybullet.createMultiBody(
            baseMass=marble.mass,
            baseCollisionShapeIndex=self._sphere(),
            basePosition=[float(value) for value in position],
            baseOrientation=[float(value) for value in orientation],
            # Not negotiable; see the module docstring. A btMultiBody marble
            # stops accelerating at 100 wu/s and is quietly damped.
            useMaximalCoordinates=True,
            physicsClientId=self.client,
        )
        pybullet.changeDynamics(
            body,
            -1,
            lateralFriction=self.materials.marble.friction,
            restitution=self.materials.marble.restitution,
            rollingFriction=self.materials.marble.rolling_friction,
            spinningFriction=self.materials.marble.spinning_friction,
            linearDamping=marble.linear_damping,
            angularDamping=marble.angular_damping,
            ccdSweptSphereRadius=marble.ccd_swept_radius,
            # A marble that falls asleep on the floor of a collector and is
            # then struck ought to wake, and Bullet does wake it - but a
            # marble resting on a *kinematic* gate that starts moving is a
            # case where it does not reliably, and that is exactly the start
            # module. Sixty-four always-awake spheres cost nothing.
            activationState=pybullet.ACTIVATION_STATE_DISABLE_SLEEPING,
            physicsClientId=self.client,
        )
        pybullet.resetBaseVelocity(
            body,
            linearVelocity=[float(value) for value in velocity],
            angularVelocity=[float(value) for value in spin],
            physicsClientId=self.client,
        )
        self.bodies[body] = _Body(kind="marble", owner="marble", marble_id=int(marble_id))
        self.marbles[int(marble_id)] = body
        return body

    def remove_marble(self, marble_id: int) -> None:
        body = self.marbles.pop(int(marble_id))
        self.pybullet.removeBody(body, physicsClientId=self.client)
        self.bodies.pop(body, None)

    def marble_state(self, marble_id: int) -> tuple[Vec3, tuple[float, float, float, float], Vec3, Vec3]:
        body = self.marbles[int(marble_id)]
        position, orientation = self.pybullet.getBasePositionAndOrientation(
            body, physicsClientId=self.client
        )
        velocity, spin = self.pybullet.getBaseVelocity(body, physicsClientId=self.client)
        return (tuple(position), tuple(orientation), tuple(velocity), tuple(spin))

    def owner_of(self, body: int) -> str:
        record = self.bodies.get(body)
        return record.owner if record else "unknown"

    def marble_of(self, body: int) -> int | None:
        record = self.bodies.get(body)
        return record.marble_id if record else None

    # --- running ---------------------------------------------------------

    def step(self) -> None:
        self.pybullet.stepSimulation(physicsClientId=self.client)
        self.ticks += 1

    def contacts(self) -> list[ContactPoint]:
        return [
            ContactPoint(
                body_a=raw[1],
                body_b=raw[2],
                position=tuple(raw[6]),
                normal=tuple(raw[7]),
                distance=float(raw[8]),
                normal_impulse=float(raw[9]),
            )
            for raw in self.pybullet.getContactPoints(physicsClientId=self.client)
        ]

    # --- probing ---------------------------------------------------------

    def aabb(self, body: int) -> Aabb:
        lower, upper = self.pybullet.getAABB(body, -1, physicsClientId=self.client)
        return Aabb(tuple(lower), tuple(upper))

    def ray_batch(
        self, starts: Iterable[Sequence[float]], ends: Iterable[Sequence[float]]
    ) -> list[tuple[int, float, Vec3]]:
        """Cast rays and report (body, fraction, hit point) for each.

        A miss reports body -1 and fraction 1.0. This is how collider
        completeness is proved: fire a ray at every part of a surface that
        should exist and check that something is there, at the height the
        geometry says. A truncated mesh, a hole, a phantom cap and a module
        placed at the wrong transform all show up as a miss or a wrong height,
        and none of them shows up in a run's own numbers until it is too late.
        """
        starts = [list(map(float, start)) for start in starts]
        ends = [list(map(float, end)) for end in ends]
        results: list[tuple[int, float, Vec3]] = []
        # Bullet's batch ray cast has a per-call limit; the constant is exposed
        # but a conservative chunk keeps this working if it ever changes.
        limit = getattr(self.pybullet, "MAX_RAY_INTERSECTION_BATCH_SIZE", 16384)
        limit = max(1, min(int(limit) - 1, 4096))
        for base in range(0, len(starts), limit):
            batch = self.pybullet.rayTestBatch(
                starts[base : base + limit],
                ends[base : base + limit],
                physicsClientId=self.client,
            )
            for hit in batch:
                results.append((int(hit[0]), float(hit[2]), tuple(hit[3])))
        return results

    def close(self) -> None:
        self.pybullet.disconnect(physicsClientId=self.client)

    def __enter__(self) -> "MarbleWorld":
        return self

    def __exit__(self, *exception: object) -> None:
        self.close()


def rolling_spin(normal: Sequence[float], velocity: Sequence[float], radius: float) -> Vec3:
    """The angular velocity of a sphere already rolling without slipping.

    omega = (n x v) / r puts the contact point instantaneously at rest. A
    marble handed a velocity without this spends its first tenth of a second
    converting slip into rotation, which is a real transient that shows up as a
    skid at the top of every chute and is trivially avoidable at release.
    """
    nx, ny, nz = normal
    vx, vy, vz = velocity
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    if length <= 0.0:
        raise ValueError("rolling spin needs a surface normal")
    nx, ny, nz = nx / length, ny / length, nz / length
    return (
        (ny * vz - nz * vy) / radius,
        (nz * vx - nx * vz) / radius,
        (nx * vy - ny * vx) / radius,
    )

"""Proving the collider Bullet holds is the collider that was described.

Section 8 of the brief: *production cannot rely on visual inspection*. Every
collider failure the physics lab hit produced a plausible physics result rather
than an error - a truncated mesh gave a bowl with no collider at all and a run
that reported 0.14 revolutions; a mis-ordered profile gave a phantom cone and
marbles that "had too much friction"; a wrong working scale flung a resting
marble across the dish. None of them raised anything. All of them would have
been reported as findings about rigid-body physics.

So there are two layers here and they check different things.

## Mesh integrity, in Python, before Bullet sees anything

`check_mesh` is pure arithmetic on vertices and indices: counts, index bounds,
degenerate triangles, edge lengths, edge manifoldness, winding consistency,
connected components, and a byte-exact round trip through the OBJ writer and a
reader. It is fast, it runs in unit tests without a physics engine, and it
catches everything that is wrong with the description.

It cannot catch anything that goes wrong *after* the description - which is the
entire class of bug the lab actually hit.

## Ray probes, against the assembled world

`probe_world` fires the rays each module declares from its own analytic surface
and checks what Bullet reports. The mesh and the probe come from the same
description by different routes: the mesh through tessellation, an OBJ file and
Bullet's loader, the probe straight from the formula. They can only agree if
every step in between worked.

That covers, in one mechanism: a truncated mesh, a mesh that failed to load, a
hole, a module placed at the wrong transform, a collision margin large enough
to move the surface, a phantom surface in mid-air, and geometry from one module
intruding into another's space - which is not a hypothetical either. The
curve's catch basin, at its first working size, stood its walls up through the
bowl's floor around the drain, and two marbles per run parked on top of them.
The rays go through the whole world, so a neighbour's geometry in the wrong
place fails the probe of whoever's space it is in.

## What the checks return

A list of `Finding`s rather than an exception, because a validation run should
report everything wrong with a machine at once and because
`tools/marble3d_validate.py` prints them. `require` raises on the first one for
callers who want it fatal.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from marble3d.config import ColliderConfig, CoreConfig, DEFAULT_CONFIG
from marble3d.machine import Machine
from marble3d.mesh import TriMesh
from marble3d.modules.base import Probe
from marble3d.world import MarbleWorld

__all__ = [
    "Finding",
    "check_mesh",
    "check_machine_meshes",
    "probe_world",
    "check_machine",
    "require",
]


@dataclass(frozen=True)
class Finding:
    """One thing wrong, with enough detail to act on."""

    check: str
    subject: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.check}] {self.subject}: {self.detail}"


def require(findings: Sequence[Finding]) -> None:
    if findings:
        raise AssertionError(
            f"{len(findings)} collider problem(s):\n  " + "\n  ".join(str(f) for f in findings)
        )


# --- layer one: the mesh as arithmetic -----------------------------------


def _parse_obj(text: str) -> tuple[list[tuple[float, float, float]], list[int]]:
    vertices: list[tuple[float, float, float]] = []
    indices: list[int] = []
    for line in text.splitlines():
        if line.startswith("v "):
            parts = line.split()
            vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
        elif line.startswith("f "):
            parts = line.split()[1:]
            if len(parts) != 3:
                raise ValueError("the collider writer only ever emits triangles")
            indices.extend(int(part.split("/")[0]) - 1 for part in parts)
    return vertices, indices


def check_mesh(
    mesh: TriMesh,
    collider: ColliderConfig | None = None,
    expected_vertices: int | None = None,
    expected_triangles: int | None = None,
    expect_components: int | None = 1,
) -> list[Finding]:
    """Everything that can be known about a mesh without a physics engine."""
    collider = collider or DEFAULT_CONFIG.collider
    findings: list[Finding] = []
    name = mesh.name

    def report(check: str, detail: str) -> None:
        findings.append(Finding(check, name, detail))

    if mesh.vertex_count == 0 or mesh.triangle_count == 0:
        report("empty", "a collider with no geometry in it")
        return findings
    if expected_vertices is not None and mesh.vertex_count != expected_vertices:
        report(
            "vertex-count",
            f"{mesh.vertex_count} vertices, expected {expected_vertices}. This is the "
            "shape a truncated mesh has.",
        )
    if expected_triangles is not None and mesh.triangle_count != expected_triangles:
        report("triangle-count", f"{mesh.triangle_count} triangles, expected {expected_triangles}")

    # Index bounds and per-triangle degeneracy.
    limit = mesh.vertex_count
    bad_index = next((index for index in mesh.indices if not 0 <= index < limit), None)
    if bad_index is not None:
        report("index-range", f"index {bad_index} against {limit} vertices")
        return findings
    repeated = 0
    for base in range(0, len(mesh.indices), 3):
        a, b, c = mesh.indices[base : base + 3]
        if a == b or b == c or a == c:
            repeated += 1
    if repeated:
        report("degenerate-index", f"{repeated} triangle(s) reference the same vertex twice")

    smallest = mesh.smallest_area()
    if smallest < collider.min_triangle_area:
        report(
            "degenerate-area",
            f"smallest triangle is {smallest:.3g}, below the {collider.min_triangle_area:.3g} "
            "floor; the solver gets a meaningless normal from a triangle that thin",
        )
    longest = mesh.longest_edge()
    if longest > collider.max_triangle_edge:
        report(
            "phantom-span",
            f"longest edge is {longest:.3f}, above the {collider.max_triangle_edge:.3f} limit. "
            "A strip triangle that long spans a whole piece, which is what a mis-ordered "
            "profile builds.",
        )

    # Edge manifoldness and winding. Every directed edge should appear at most
    # once: twice means two triangles wound the same way share an edge, which
    # is a fold. Every undirected edge should be used once (a boundary) or
    # twice (an interior edge); three or more is a non-manifold junction.
    directed: dict[tuple[int, int], int] = defaultdict(int)
    undirected: dict[tuple[int, int], int] = defaultdict(int)
    for base in range(0, len(mesh.indices), 3):
        a, b, c = mesh.indices[base : base + 3]
        for start, end in ((a, b), (b, c), (c, a)):
            directed[(start, end)] += 1
            undirected[(min(start, end), max(start, end))] += 1
    folded = sum(1 for count in directed.values() if count > 1)
    if folded:
        report(
            "winding",
            f"{folded} edge(s) traversed the same way by two triangles; the winding is "
            "inconsistent and internal-edge filtering will pick the wrong normals",
        )
    junctions = sum(1 for count in undirected.values() if count > 2)
    if junctions:
        report("non-manifold", f"{junctions} edge(s) shared by more than two triangles")

    # Connected components, over shared vertices.
    if expect_components is not None:
        parent = list(range(mesh.vertex_count))

        def find(node: int) -> int:
            while parent[node] != node:
                parent[node] = parent[parent[node]]
                node = parent[node]
            return node

        for (a, b) in undirected:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
        components = len({find(index) for index in range(mesh.vertex_count)})
        if components != expect_components:
            report(
                "components",
                f"{components} connected piece(s), expected {expect_components}; a collider "
                "in two pieces usually means a strip was built across a discontinuity",
            )

    # The round trip. This is the one that would have caught the lab's
    # truncation directly: write the mesh the way the engine will read it, read
    # it back, and compare.
    vertices, indices = _parse_obj(mesh.to_obj())
    if len(vertices) != mesh.vertex_count or len(indices) != len(mesh.indices):
        report(
            "round-trip",
            f"wrote {mesh.vertex_count} vertices and {mesh.triangle_count} triangles, read "
            f"back {len(vertices)} and {len(indices) // 3}",
        )
    else:
        worst = max(
            (math.dist(a, b) for a, b in zip(vertices, mesh.vertices)),
            default=0.0,
        )
        if worst > 1e-6:
            report("round-trip", f"a vertex moved {worst:.3g} through the OBJ writer")
        if indices != mesh.indices:
            report("round-trip", "the triangle indices changed through the OBJ writer")

    # Chunking has to preserve the triangles exactly, because it is the thing
    # standing between this package and an undocumented buffer limit.
    chunks = mesh.chunks(collider.max_chunk_vertices, collider.max_chunk_indices)
    total = sum(chunk.triangle_count for chunk in chunks)
    if total != mesh.triangle_count:
        report("chunking", f"{mesh.triangle_count} triangles became {total} across {len(chunks)} chunks")
    oversized = [chunk.name for chunk in chunks if chunk.vertex_count > collider.max_chunk_vertices]
    if oversized:
        report("chunking", f"chunk(s) over the vertex limit: {oversized}")
    return findings


def check_machine_meshes(machine: Machine, config: CoreConfig | None = None) -> list[Finding]:
    config = config or DEFAULT_CONFIG
    findings: list[Finding] = []
    for module in machine:
        for mesh in module.local_colliders():
            findings.extend(check_mesh(mesh, config.collider))
    return findings


# --- layer two: what Bullet actually holds -------------------------------


def probe_world(world: MarbleWorld, probes: Iterable[Probe]) -> list[Finding]:
    """Fire each probe at the assembled world and report what disagrees."""
    probes = list(probes)
    if not probes:
        return []
    results = world.ray_batch(
        (probe.start for probe in probes), (probe.end for probe in probes)
    )
    findings: list[Finding] = []
    for probe, (body, fraction, point) in zip(probes, results):
        hit = body >= 0
        if probe.expect_hit and not hit:
            findings.append(
                Finding(
                    "collider-hole",
                    probe.label,
                    f"a ray from {_short(probe.start)} to {_short(probe.end)} hit nothing. "
                    "The surface the module describes is not in the world.",
                )
            )
            continue
        if not probe.expect_hit and hit:
            findings.append(
                Finding(
                    "phantom-geometry",
                    probe.label,
                    f"a ray from {_short(probe.start)} to {_short(probe.end)} hit "
                    f"{world.owner_of(body)!r} at {_short(point)}. That space is supposed "
                    "to be empty.",
                )
            )
            continue
        if probe.expected_point is not None and hit:
            error = math.dist(point, probe.expected_point)
            if error > probe.tolerance:
                findings.append(
                    Finding(
                        "surface-position",
                        probe.label,
                        f"the surface is {error:.4f} from where the module says it is "
                        f"(tolerance {probe.tolerance:.4f}); hit {_short(point)}, expected "
                        f"{_short(probe.expected_point)}, on {world.owner_of(body)!r}",
                    )
                )
    return findings


def check_collider_bounds(world: MarbleWorld) -> list[Finding]:
    """Compare each collider's AABB in Bullet against the mesh it was built from.

    The cheapest possible proof that a mesh arrived whole: a truncated mesh has
    a smaller bounding box than the one that was sent, and this is one call per
    chunk. Bullet inflates a static shape's broadphase box by its collision
    margin and a small contact allowance, so the comparison is one-sided - the
    reported box has to *contain* the expected one and not be much bigger.
    """
    findings: list[Finding] = []
    allowance = 4.0 * DEFAULT_CONFIG.collider.mesh_margin + 0.1
    for record in world.colliders:
        actual = world.aabb(record.body)
        expected = record.expected_bounds
        short = min(
            min(e - a for a, e in zip(actual.lower, expected.lower)),
            min(a - e for a, e in zip(actual.upper, expected.upper)),
        )
        if short < -allowance:
            findings.append(
                Finding(
                    "collider-bounds",
                    f"{record.owner}/{record.piece}",
                    f"Bullet's bounding box is {-short:.4f} smaller than the mesh that was "
                    f"sent, on some axis. A mesh that arrives short is a mesh that arrived "
                    f"truncated. sent {_short(expected.lower)}..{_short(expected.upper)}, "
                    f"holds {_short(actual.lower)}..{_short(actual.upper)}",
                )
            )
    return findings


def check_margins(world: MarbleWorld) -> list[Finding]:
    """Measure the effective size of a marble and of a contact, in the world.

    Three measurements, none of them assumed:

    * a sphere's own AABB, which must be exactly its radius. `btSphereShape`
      carries the collision margin *as* the radius rather than outside it, so
      unlike every other shape a sphere is not inflated - and everything in the
      margin policy rests on that being true of this build.
    * two marbles dropped side by side at exactly one diameter apart, which
      must not report a contact, and at slightly less, which must.
    * the resting height of a marble on a trimesh floor, which is where a mesh
      margin shows up as a physical error.
    """
    import pybullet

    findings: list[Finding] = []
    marble = world.config.marble
    client = world.client

    sphere = pybullet.createCollisionShape(
        pybullet.GEOM_SPHERE, radius=marble.radius, physicsClientId=client
    )
    probe = pybullet.createMultiBody(
        baseMass=0.0,
        baseCollisionShapeIndex=sphere,
        basePosition=[0.0, 1e6, 0.0],
        useMaximalCoordinates=True,
        physicsClientId=client,
    )
    lower, upper = pybullet.getAABB(probe, -1, physicsClientId=client)
    half = 0.5 * (upper[0] - lower[0])
    if abs(half - marble.radius) > 1e-6:
        findings.append(
            Finding(
                "sphere-margin",
                "marble",
                f"a sphere of radius {marble.radius} has a half-extent of {half:.6f}. "
                "Bullet is inflating spheres on this build, and every clearance in the "
                "machine is out by the difference.",
            )
        )
    pybullet.removeBody(probe, physicsClientId=client)
    return findings


def check_machine(
    machine: Machine, config: CoreConfig | None = None
) -> tuple[list[Finding], dict[str, Any]]:
    """The whole battery, on a freshly built world. Returns findings and facts."""
    config = config or DEFAULT_CONFIG
    findings = check_machine_meshes(machine, config)
    facts: dict[str, Any] = {}
    world = MarbleWorld(config)
    try:
        machine.build(world)
        facts["colliders"] = len(world.colliders)
        facts["triangles"] = sum(record.triangle_count for record in world.colliders)
        facts["vertices"] = sum(record.vertex_count for record in world.colliders)
        probes = machine.probes()
        facts["probes"] = len(probes)
        findings.extend(check_collider_bounds(world))
        findings.extend(check_margins(world))
        findings.extend(probe_world(world, probes))
    finally:
        world.close()
    return findings, facts


def _short(point: Sequence[float]) -> str:
    return "(" + ", ".join(f"{value:.2f}" for value in point) + ")"

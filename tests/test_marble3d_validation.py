"""Collider integrity against a live world: the checks a mesh test cannot make.

`test_marble3d_mesh.py` proves things about a description. This proves things
about what Bullet is holding, which is where the physics lab's expensive bugs
all lived: a mesh that was described correctly, marshalled through a fixed
command buffer, arrived truncated, and produced a bowl with no collider and a
run that reported 0.14 revolutions.

The probes each module declares are generated from the analytic surface its
mesh was tessellated from, so the mesh and the probe reach the same claim by
different routes. They can only agree if every step in between worked.
"""

from __future__ import annotations

import pytest

from marble3d.config import DEFAULT_CONFIG
from marble3d.machines import start_bowl_curve
from marble3d.mesh import TriMesh
from marble3d.modules.base import Probe
from marble3d.validation import (
    check_collider_bounds,
    check_machine,
    probe_world,
    require,
)
from marble3d.world import MarbleWorld

pytest.importorskip("pybullet")


@pytest.fixture(scope="module")
def checked():
    return check_machine(start_bowl_curve())


def test_the_machine_passes_every_probe_it_declares(checked) -> None:
    findings, facts = checked
    assert findings == [], "\n".join(str(finding) for finding in findings)
    assert facts["probes"] > 300
    assert facts["triangles"] > 5000


def test_the_machine_is_split_into_chunks_bullet_cannot_truncate(checked) -> None:
    _, facts = checked
    collider = DEFAULT_CONFIG.collider
    assert facts["colliders"] >= 1
    assert collider.max_chunk_vertices < 8192
    assert collider.max_chunk_indices < 32768


def test_a_missing_collider_is_caught_by_the_probes_that_expect_it() -> None:
    """The truncation failure, staged: build the world without one module.

    A bowl with no collider is not a quiet degradation. It is marbles falling
    through the world and a run that still produces numbers, and this is the
    check that turns it into a message.
    """
    machine = start_bowl_curve()
    world = MarbleWorld(DEFAULT_CONFIG)
    try:
        for module in machine:
            if module.id == "bowl":
                continue
            for mesh in module.local_colliders():
                world.add_static_mesh(mesh, module.transform, owner=module.id)
        findings = probe_world(world, machine.modules["bowl"].probes())
    finally:
        world.close()
    checks = {finding.check for finding in findings}
    assert "collider-hole" in checks
    # A handful of rays that would have landed on the missing bowl reach a
    # neighbouring module instead, which is reported as a surface in the wrong
    # place. Both are correct answers to "the bowl is not there".
    assert checks <= {"collider-hole", "surface-position"}
    assert sum(1 for f in findings if f.check == "collider-hole") > 50


def test_geometry_intruding_into_another_module_is_caught() -> None:
    """The bug that actually happened, staged as a test.

    The curve's catch basin, at its first working size, stood its walls up
    through the bowl's floor around the drain, and two marbles a run parked on
    top of them. A negative probe - "this space is supposed to be empty" - is
    what found it, and it found it because rays go through the whole world
    rather than through one module's own geometry.
    """
    machine = start_bowl_curve()
    world = MarbleWorld(DEFAULT_CONFIG)
    try:
        machine.build(world)
        # A slab where a marble orbits. Nothing declared it and nothing should
        # be there, so the bowl's own corridor probes have to object to it.
        bowl = machine.modules["bowl"]
        radius = 0.6 * bowl.spec.rim_radius
        height = bowl.spec.height(radius) + 2.5
        slab = TriMesh(
            [
                (-radius, height, -radius), (radius, height, -radius),
                (radius, height, radius), (-radius, height, radius),
            ],
            [0, 1, 2, 0, 2, 3],
            "intruder",
        )
        world.add_static_mesh(slab, owner="intruder")
        findings = probe_world(world, bowl.probes())
    finally:
        world.close()
    assert any(finding.check == "phantom-geometry" for finding in findings)
    assert any("intruder" in finding.detail for finding in findings)


def test_a_shrunken_collider_is_caught_by_its_own_bounding_box() -> None:
    """Bullet's AABB against the mesh that was sent, which is one call a chunk."""
    from marble3d.experiments import flat_plane
    from marble3d.mesh import Aabb
    from marble3d.world import ColliderRecord

    world = MarbleWorld(DEFAULT_CONFIG)
    try:
        record = world.add_static_mesh(flat_plane(size=40.0, cells=4), owner="floor")[0]
        assert check_collider_bounds(world) == []
        # Claim the mesh was twice the size it was: the box Bullet holds is now
        # short, which is exactly the shape of a truncated load.
        bounds = record.expected_bounds
        world.colliders[0] = ColliderRecord(
            body=record.body,
            owner=record.owner,
            piece=record.piece,
            vertex_count=record.vertex_count,
            triangle_count=record.triangle_count,
            expected_bounds=Aabb(
                tuple(value * 2.0 for value in bounds.lower),
                tuple(value * 2.0 for value in bounds.upper),
            ),
            obj_path=record.obj_path,
        )
        findings = check_collider_bounds(world)
    finally:
        world.close()
    assert [finding.check for finding in findings] == ["collider-bounds"]


def test_a_probe_that_expects_a_hit_and_gets_nothing_is_reported() -> None:
    world = MarbleWorld(DEFAULT_CONFIG)
    try:
        findings = probe_world(
            world,
            [Probe(start=(0.0, 10.0, 0.0), end=(0.0, -10.0, 0.0), label="empty world")],
        )
    finally:
        world.close()
    assert [finding.check for finding in findings] == ["collider-hole"]


def test_require_raises_with_every_finding_in_the_message() -> None:
    from marble3d.validation import Finding

    with pytest.raises(AssertionError, match="2 collider problem"):
        require([Finding("a", "x", "one"), Finding("b", "y", "two")])
    require([])

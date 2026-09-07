"""Collider construction and integrity: one test per bug the lab found.

Three of the four failures the physics study spent its time on were collider
bugs that produced a plausible physics result rather than an error. Each one
has a test here that fails on the shape of the mistake rather than on its
symptom, because the symptom - fewer revolutions, more apparent friction - is
indistinguishable from a finding.
"""

from __future__ import annotations

import pytest

from marble3d.config import DEFAULT_CONFIG
from marble3d.geometry import Transform, quat_from_axis_angle
from marble3d.mesh import TriMesh, revolve, segments_for_sagitta, sweep, worst_sagitta
from marble3d.modules.base import channel_section
from marble3d.units import MARBLE_DIAMETER, MARBLE_RADIUS
from marble3d.validation import check_mesh

COLLIDER = DEFAULT_CONFIG.collider


def straight_frames(count: int = 12, length: float = 6.0) -> list[Transform]:
    return [Transform((length * index / count, 0.0, 0.0)) for index in range(count + 1)]


def clean_cylinder(rings: int = 10, segments: int = 16) -> TriMesh:
    profile = [(2.0, float(index)) for index in range(rings)]
    return revolve(profile, segments, name="cylinder", max_profile_step=2.0)


# --- the strip builder ---------------------------------------------------


def test_a_surface_of_revolution_has_the_vertex_count_it_should() -> None:
    mesh = clean_cylinder(rings=10, segments=16)
    assert mesh.vertex_count == 10 * 16
    assert mesh.triangle_count == 9 * 16 * 2


def test_a_clean_collider_passes_every_integrity_check() -> None:
    assert check_mesh(clean_cylinder(), COLLIDER, expected_vertices=160) == []


def test_a_mis_ordered_profile_cannot_be_built_at_all() -> None:
    """The phantom cone, refused rather than tested for.

    The lab appended the drain shaft's rings *after* the dish's, so the strip
    builder joined the outer rim of the bowl to the top of the shaft and the
    collider gained a cone running from rim to drain. Marbles wedged between
    the real dish and the fake one and stopped dead on the wall, which in a
    results table reads exactly like "this engine has too much friction".
    """
    dish = [(radius, 0.1 * radius * radius) for radius in (2.0, 3.0, 4.0, 5.0)]
    shaft = [(1.0, height) for height in (-3.0, -2.0, -1.0)]
    with pytest.raises(ValueError, match="phantom-cone shape"):
        revolve(dish + shaft, 16, name="mis_ordered", max_profile_step=2.0)
    # In the right order it builds and is clean.
    assert check_mesh(revolve(shaft + dish, 16, "ordered", max_profile_step=2.0), COLLIDER) == []


def test_a_long_triangle_edge_is_reported_even_without_the_profile_guard() -> None:
    """The same bug caught downstream, for a mesh that arrived some other way."""
    good = clean_cylinder()
    spanning = TriMesh(
        good.vertices + [(0.0, -60.0, 0.0)],
        good.indices + [0, 1, good.vertex_count],
        "spanning",
    )
    checks = {finding.check for finding in check_mesh(spanning, COLLIDER, expect_components=None)}
    assert "phantom-span" in checks


def test_coincident_profile_points_are_refused() -> None:
    with pytest.raises(ValueError, match="coincide"):
        revolve([(2.0, 0.0), (2.0, 0.0), (2.0, 1.0)], 16, name="doubled")


def test_a_degenerate_triangle_is_reported() -> None:
    """A cross-section tapering to nothing collapses a ring; the bowl's spout
    tapers to a stub instead, and this is what says why."""
    frames = straight_frames()
    last = len(frames) - 1
    sections = [
        channel_section(1.2, max(1e-12, 0.8 * (1.0 - index / last)), 0.8)
        for index in range(len(frames))
    ]
    mesh = sweep(sections, frames, name="collapsing")
    checks = {finding.check for finding in check_mesh(mesh, COLLIDER, expect_components=None)}
    assert "degenerate-area" in checks


def test_an_index_out_of_range_is_reported_before_anything_else() -> None:
    good = clean_cylinder()
    broken = TriMesh(good.vertices, good.indices[:-1] + [good.vertex_count + 5], "broken")
    findings = check_mesh(broken, COLLIDER)
    assert findings and findings[0].check == "index-range"


def test_a_wrong_vertex_count_is_reported_as_truncation() -> None:
    """The 8192-vertex command buffer, as a check rather than an afternoon.

    PyBullet's inline shape creation marshals through a fixed buffer and a
    larger mesh arrives truncated with no error at all. The lab handed it 26624
    vertices, got a bowl with no collider, and measured 0.14 revolutions - a
    number that looks exactly like a physics result.
    """
    mesh = clean_cylinder()
    findings = check_mesh(mesh, COLLIDER, expected_vertices=mesh.vertex_count + 1)
    assert [finding.check for finding in findings] == ["vertex-count"]


def test_winding_is_consistent_across_the_whole_strip() -> None:
    mesh = clean_cylinder()
    doubled = TriMesh(
        mesh.vertices,
        mesh.indices + [mesh.indices[0], mesh.indices[2], mesh.indices[1]],
        "doubled_face",
    )
    checks = {finding.check for finding in check_mesh(doubled, COLLIDER)}
    assert "winding" in checks or "non-manifold" in checks


# --- chunking ------------------------------------------------------------


def test_chunking_preserves_every_triangle_and_its_geometry() -> None:
    mesh = clean_cylinder(rings=40, segments=32)
    chunks = mesh.chunks(200, 600)
    assert len(chunks) > 1
    assert sum(chunk.triangle_count for chunk in chunks) == mesh.triangle_count
    assert all(chunk.vertex_count <= 200 for chunk in chunks)

    original = sorted(
        tuple(sorted(triangle)) for triangle in _rounded_triangles(mesh)
    )
    rebuilt = sorted(
        tuple(sorted(triangle))
        for chunk in chunks
        for triangle in _rounded_triangles(chunk)
    )
    assert rebuilt == original


def test_chunks_stay_inside_the_configured_buffer_limits() -> None:
    mesh = clean_cylinder(rings=200, segments=64)
    chunks = mesh.chunks(COLLIDER.max_chunk_vertices, COLLIDER.max_chunk_indices)
    assert all(chunk.vertex_count <= COLLIDER.max_chunk_vertices for chunk in chunks)
    assert all(len(chunk.indices) <= COLLIDER.max_chunk_indices for chunk in chunks)
    # And comfortably inside PyBullet's own documented buffer, which is the
    # number this exists to never depend on.
    assert COLLIDER.max_chunk_vertices < 8192
    assert COLLIDER.max_chunk_indices < 32768


def _rounded_triangles(mesh: TriMesh):
    for a, b, c in mesh.triangles():
        yield tuple(tuple(round(value, 9) for value in vertex) for vertex in (a, b, c))


# --- resolution ----------------------------------------------------------


def test_segment_count_meets_the_sagitta_budget_it_was_asked_for() -> None:
    for radius in (1.0, 7.0, 15.625, 40.0):
        budget = COLLIDER.sagitta_limit
        segments = segments_for_sagitta(radius, budget)
        assert worst_sagitta(radius, segments) <= budget
        assert segments % 4 == 0
        # And it is not wastefully fine: one step coarser would miss.
        if segments > 8:
            assert worst_sagitta(radius, segments - 4) > budget


def test_the_sagitta_budget_is_a_fraction_of_the_marble() -> None:
    assert COLLIDER.sagitta_limit == pytest.approx(COLLIDER.sagitta_budget * MARBLE_RADIUS)


# --- the swept channel ---------------------------------------------------


def test_a_channel_section_is_wide_enough_for_a_marble_and_closes_upward() -> None:
    section = channel_section(2.4 * MARBLE_RADIUS, 0.8, 0.8)
    across = [point[0] for point in section]
    assert max(across) - min(across) > MARBLE_DIAMETER
    # The walls are the highest points and they are at the outside.
    highest = max(section, key=lambda point: point[1])
    assert abs(highest[0]) == pytest.approx(max(abs(value) for value in across))


def test_a_gutter_that_would_close_over_the_marble_is_refused() -> None:
    with pytest.raises(ValueError, match="cannot span"):
        channel_section(4.0, 0.8, 1.0)


def test_a_swept_channel_follows_its_frames() -> None:
    frames = [
        Transform((float(index), 0.0, 0.0), quat_from_axis_angle((1.0, 0.0, 0.0), 0.3 * index))
        for index in range(6)
    ]
    mesh = sweep(channel_section(1.2, 0.8, 0.8), frames, name="banked")
    assert check_mesh(mesh, COLLIDER, expect_components=None) == []
    bounds = mesh.aabb()
    assert bounds.lower[0] == pytest.approx(0.0)
    assert bounds.upper[0] == pytest.approx(5.0)


def test_a_sweep_needs_one_section_per_frame_or_exactly_one() -> None:
    frames = straight_frames(count=4)
    with pytest.raises(ValueError, match="cross-sections against"):
        sweep([channel_section(1.2, 0.8, 0.8)] * 3, frames, name="mismatched")


# --- serialisation -------------------------------------------------------


def test_the_obj_round_trip_is_exact() -> None:
    mesh = clean_cylinder(rings=6, segments=12)
    assert check_mesh(mesh, COLLIDER) == []


def test_a_mesh_is_named_by_its_content(tmp_path) -> None:
    from marble3d.mesh import cached_obj

    first = clean_cylinder(rings=6, segments=12)
    second = clean_cylinder(rings=6, segments=12)
    third = clean_cylinder(rings=7, segments=12)
    assert cached_obj(first, str(tmp_path)) == cached_obj(second, str(tmp_path))
    assert cached_obj(first, str(tmp_path)) != cached_obj(third, str(tmp_path))

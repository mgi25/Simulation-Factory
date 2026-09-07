"""The reconstruction is the photographed course, and the collider is the channel.

The tests that matter most in this package are the ones that would have caught
the mistakes it actually made, so each of the first three names one.
"""

from __future__ import annotations

import math

import pytest

from marble3d.config import DEFAULT_CONFIG
from marble3d.units import MARBLE_DIAMETER, MARBLE_RADIUS
from marble3d.validation import check_mesh
from sloped import contract, joins, layout, scale
from sloped.pathing import (
    SPLINE_SAMPLES,
    TRACK_SAMPLES,
    auto_bank,
    build_path,
    path_length,
    resample,
    smooth_path,
    width_curve,
)
from sloped.track import TrackRun, channel_profile


# --- the contract ---------------------------------------------------------


def test_the_reconstruction_agrees_with_the_recorded_contract():
    """All 182 recorded centreline points, and every recorded scalar.

    This is the whole argument that the physics course is the photographed
    course rather than one near it. It is also the test that caught the sample
    count: `v2_track.SAMPLES` is 132 and `course_machine.gd` passes 118, and at
    132 the worst point is 0.31 layout units out while every *length* still
    agrees to four decimals - so a length check alone passes a course whose
    hairpins are half a marble diameter from where they were drawn.
    """
    findings = contract.check()
    assert findings == [], "\n".join(str(finding) for finding in findings)


def test_the_worst_recorded_point_is_within_json_rounding():
    """Every run but orange still agrees to the JSON writer's own rounding.

    Orange is the named deviation - its three tail heights were redistributed
    to stop the run climbing - so it is checked against its own budget in
    `contract.DEVIATIONS` and excluded here rather than being allowed to widen
    the tolerance for the other six.
    """
    facts = contract.facts()
    assert facts["worst_centreline_gap_excluding_deviations"] < 1.0e-3, facts

    # And the deviation itself is the size it is supposed to be, in height only.
    orange = facts["per_run_centreline_gap"]["orange"]
    budget, _why = contract.DEVIATIONS[("orange", "centreline")]
    assert orange < budget
    assert orange > 1.0e-3, "the deviation is gone; drop it from DEVIATIONS"


def test_the_sample_count_is_the_one_the_stills_were_taken_at():
    assert TRACK_SAMPLES == 118
    spec = layout.run("leg2")
    at_132 = resample(smooth_path(spec["controls"], SPLINE_SAMPLES), 132)
    at_118 = resample(smooth_path(spec["controls"], SPLINE_SAMPLES), 118)
    # Same curve, so the same length; different samples, so a different
    # thinning - which is exactly the trap.
    assert path_length(at_132) == pytest.approx(path_length(at_118), abs=2e-3)
    thinned_132 = [at_132[round(step * 131 / 25)] for step in range(26)]
    thinned_118 = [at_118[round(step * 117 / 25)] for step in range(26)]
    worst = max(math.dist(a, b) for a, b in zip(thinned_132, thinned_118))
    assert worst > 0.2, worst


# --- the path law ---------------------------------------------------------


def test_smooth_path_emits_the_gdscript_point_count():
    """Six controls give five spans and 131 points, not 26."""
    controls = layout.run("launch")["controls"]
    assert len(controls) == 6
    assert len(smooth_path(controls, 26)) == 4 * 26 + 27


def test_smooth_path_starts_and_ends_on_its_controls():
    controls = layout.run("leg1")["controls"]
    path = smooth_path(controls, 26)
    assert math.dist(path[0], controls[0]) < 1e-12
    assert math.dist(path[-1], controls[-1]) < 1e-12


def test_resample_is_even_in_arc_length():
    path = resample(smooth_path(layout.run("leg3")["controls"], 26), 118)
    steps = [math.dist(path[i + 1], path[i]) for i in range(len(path) - 1)]
    assert max(steps) - min(steps) < 1e-3 * max(steps)


def test_auto_bank_eases_both_ends_to_level():
    path = resample(smooth_path(layout.run("leg2")["controls"], 26), 118)
    banks = auto_bank(path, 3.0, 22.0)
    assert abs(banks[0]) < 1e-9
    assert abs(banks[-1]) < 1e-9
    assert max(abs(b) for b in banks) == pytest.approx(math.radians(22.0), rel=1e-6)


def test_width_curve_flares_the_ends_and_pinches_the_middle():
    widths = width_curve(118)
    assert widths[0] > 1.10
    assert widths[-1] > 1.05
    assert min(widths) < 0.96


# --- the scale ------------------------------------------------------------


def test_the_scale_maps_the_layout_marble_onto_the_core_marble():
    assert scale.LAYOUT_MARBLE_RADIUS == 0.285
    assert scale.to_sim(scale.LAYOUT_MARBLE_RADIUS) == pytest.approx(MARBLE_RADIUS)
    assert scale.SIM_TO_LAYOUT == pytest.approx(0.57)
    assert scale.to_layout(scale.to_sim(3.7)) == pytest.approx(3.7)


def test_three_marbles_abreast_in_the_hero_channel():
    run = TrackRun("leg2")
    assert run.clear_width / MARBLE_DIAMETER == pytest.approx(3.298, abs=1e-3)
    branch = TrackRun("blue")
    assert branch.clear_width / MARBLE_DIAMETER == pytest.approx(2.705, abs=1e-3)


def test_containment_is_the_assets_own_number():
    run = TrackRun("final")
    expected = scale.to_sim(layout.CONTAINMENT_TOP - layout.FLOOR_Y)
    assert run.containment == pytest.approx(expected)
    assert run.containment / MARBLE_DIAMETER == pytest.approx(1.404, abs=1e-3)


# --- the section ----------------------------------------------------------


def test_the_section_traces_the_lip_and_the_guard_and_not_a_straight_wall():
    """The wall a climbing marble meets is the asset's, not one at the edge.

    A collider that stands a straight wall at the cradle's edge holds a marble
    0.06 layout units clear of the surface it appears to lean on.
    """
    section = channel_profile()
    highest = max(section, key=lambda point: point[1])
    assert highest[1] == pytest.approx(layout.CONTAINMENT_TOP)
    assert abs(highest[0]) == pytest.approx(layout.GUARD_INNER)
    # The lip's four authored points are in it.
    for across, up in layout.LIP_INNER:
        assert any(
            abs(a - across) < 1e-9 and abs(b - up) < 1e-9 for a, b in section
        ), (across, up)


def test_the_cradle_is_the_assets_arc():
    for across in (0.0, 0.3, 0.6, layout.CHANNEL_HALF):
        rise = layout.floor_y_at(across) - layout.FLOOR_Y
        expected = layout.FLOOR_RADIUS - math.sqrt(
            layout.FLOOR_RADIUS**2 - across**2
        )
        assert rise == pytest.approx(expected)
    # Clamped at the edge, exactly as `_floor_y_at` clamps it.
    assert layout.floor_y_at(2.0) == pytest.approx(layout.floor_y_at(layout.CHANNEL_HALF))


def test_the_section_is_symmetric_and_walked_in_order():
    section = channel_profile()
    assert len(section) == 2 * (5 + 4 + 2) - 1
    for (a_across, a_up), (b_across, b_up) in zip(section, reversed(section)):
        assert a_across == pytest.approx(-b_across)
        assert a_up == pytest.approx(b_up)
    steps = [
        math.dist(section[i], section[i + 1]) for i in range(len(section) - 1)
    ]
    assert max(steps) < 0.35, "a jump in the section is the phantom-cone shape"


# --- the colliders --------------------------------------------------------


@pytest.mark.parametrize("name", layout.run_names())
def test_every_run_builds_a_clean_collider(name):
    run = TrackRun(name)
    mesh = run.local_colliders()[0]
    findings = check_mesh(mesh, DEFAULT_CONFIG.collider, expect_components=1)
    assert findings == [], "\n".join(str(f) for f in findings)
    assert mesh.triangle_count == 2 * 20 * (TRACK_SAMPLES - 1)
    chunks = mesh.chunks(
        DEFAULT_CONFIG.collider.max_chunk_vertices,
        DEFAULT_CONFIG.collider.max_chunk_indices,
    )
    assert sum(chunk.triangle_count for chunk in chunks) == mesh.triangle_count


def test_the_collider_facets_meet_the_cores_sagitta_budget():
    """The 118 samples the stills were taken at are also the right resolution.

    A finer collider dissipates *more* - a rigid sphere loses energy at every
    triangle edge - so this is a physics bound and not an art one, and the core
    sets it at 4% of a marble radius because that is where smoothness and
    dissipation cross.

    The quantity is the sagitta of *one facet* against the arc it approximates:
    the circumradius of three consecutive samples, then `R - sqrt(R^2 -
    (L/2)^2)` for the segment length `L`. Measuring the middle sample's
    distance from the chord of its two neighbours instead - which is what the
    first version of this test did - gives four times the answer and condemns a
    collider that is inside budget.
    """
    limit = DEFAULT_CONFIG.collider.sagitta_limit
    worst = 0.0
    where = ("", 0)
    for name in layout.run_names():
        run = TrackRun(name)
        for index in range(1, len(run.sim_path) - 1):
            a, b, c = (
                run.sim_path[index - 1],
                run.sim_path[index],
                run.sim_path[index + 1],
            )
            ab, bc, ca = math.dist(a, b), math.dist(b, c), math.dist(c, a)
            ux, uy, uz = (b[i] - a[i] for i in range(3))
            vx, vy, vz = (c[i] - b[i] for i in range(3))
            cross = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
            area = 0.5 * math.sqrt(sum(v * v for v in cross))
            if area < 1e-12:
                continue
            radius = ab * bc * ca / (4.0 * area)
            half = 0.5 * bc
            if half >= radius:
                continue
            sagitta = radius - math.sqrt(radius * radius - half * half)
            if sagitta > worst:
                worst, where = sagitta, (name, index)
    assert worst < limit, (worst, limit, where)


def test_the_socket_sits_where_a_marble_rests_and_not_on_the_centreline():
    run = TrackRun("launch")
    entry = run.socket("entry")
    surface = run.surface_point(0, 0.0)
    assert math.dist(entry.frame.position, surface) < 1e-9
    assert entry.width == pytest.approx(run.clear_width)
    assert entry.height == pytest.approx(run.containment)


def test_opening_a_wall_lowers_only_that_side():
    window = (1.0, 0, 2, 6, 8)
    plain = TrackRun("leg3")
    opened = TrackRun("leg3", open_side=window)
    assert opened.wall_factor(0) == 1.0
    assert opened.wall_factor(4) == pytest.approx(TrackRun.OPEN_FLOOR)
    assert opened.wall_factor(20) == 1.0
    section = opened.section_at(4)
    reference = plain.section_at(4)
    for (a_across, a_up), (b_across, b_up) in zip(section, reference):
        assert a_across == pytest.approx(b_across)
        if b_across < 0:
            assert a_up == pytest.approx(b_up), "the far wall must not move"
    right_open = max(u for a, u in section if a > 0)
    right_shut = max(u for a, u in reference if a > 0)
    assert right_open < right_shut
    assert max(u for a, u in section if a < 0) == pytest.approx(
        max(u for a, u in reference if a < 0)
    )


def test_the_taper_opens_a_lead_at_the_width_that_feeds_it():
    spec = dict(joins.JOIN_SPECS["orange_lead"])
    path = joins.join_paths()["orange_lead"]
    lead = TrackRun("orange_lead", spec=spec, path=path, samples=44, taper=(1.0, 0.82))
    assert lead.widths[0] == pytest.approx(1.0, abs=1e-6)
    assert lead.widths[-1] < 0.95
    # Hero scale, so the containment is the full channel's - which is what
    # catches a marble thrown across the fork.
    assert lead.containment == pytest.approx(TrackRun("leg3").containment)

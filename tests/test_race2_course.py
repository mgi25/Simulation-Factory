"""The Race #2 course as assembled: geometry, seams, and the things it claims.

No race is run here. Everything in this file is a property of the built machine
and is cheap; `tests/test_race2_race.py` owns the one shared race.
"""

from __future__ import annotations

import math

import pytest

from marble3d.units import MARBLE_DIAMETER, MARBLE_RADIUS
from marble3d.validation import check_collider_bounds, check_mesh
from marble3d.world import MarbleWorld
from marble3d.config import DEFAULT_CONFIG

from race2 import concepts, courses
from race2.parts import Wheel
from race2.track import WALL_CAP, RaceRun

# Half a marble diameter of position and 24 degrees of heading, which are
# Race #1's own seam budgets in `sloped.course`. Race #2's seams are cut out of
# one continuous polyline, so they should be far inside these.
POSITION_BUDGET = 0.5 * MARBLE_DIAMETER
HEADING_BUDGET = 24.0


@pytest.fixture(scope="module")
def course():
    return courses.build("switchyard")


def test_the_course_builds_and_every_run_is_in_exactly_one_stage(course):
    assert course.title == "SWITCHYARD"
    seen = [name for stage in course.stages for name in stage.runs]
    assert sorted(seen) == sorted(course.runs)
    assert len(seen) == len(set(seen))


def test_every_phase_names_stages_that_exist_and_covers_the_course(course):
    named = {stage.name for stage in course.stages}
    covered: set[str] = set()
    for phase in course.phases:
        for stage in phase.stages:
            assert stage in named
            covered.add(stage)
    assert covered == named, f"stages in no phase: {sorted(named - covered)}"


def test_consecutive_runs_meet(course):
    """Each run's exit socket is where the next one's entry socket is.

    The runs are cut out of one polyline that shares its break controls, so
    position should agree to a rounding error rather than to a budget. The
    budget is Race #1's, kept so the two courses are checked the same way.
    """
    order = [name for stage in course.stages for name in stage.runs]
    for before, after in zip(order, order[1:]):
        exit_socket = course.runs[before].socket("exit")
        entry_socket = course.runs[after].socket("entry")
        gap = math.dist(exit_socket.frame.position, entry_socket.frame.position)
        assert gap < POSITION_BUDGET, f"{before} to {after}: {gap:.4f} apart"
        turn = abs(math.degrees(exit_socket.heading() - entry_socket.heading()))
        turn = min(turn, 360.0 - turn)
        assert turn < HEADING_BUDGET, f"{before} to {after}: {turn:.1f} deg of kink"


def test_the_width_a_run_hands_over_is_the_width_the_next_one_takes(course):
    order = [name for stage in course.stages for name in stage.runs]
    for before, after in zip(order, order[1:]):
        leaving = course.runs[before].widths[-1]
        arriving = course.runs[after].widths[0]
        # The library flares a run's entry by 14% and its exit by 9%, so the two
        # differ by that even when both were authored at the same body width.
        assert abs(leaving - arriving) < 0.30 * max(leaving, arriving), (
            f"{before} leaves at {leaving:.3f} and {after} takes {arriving:.3f}"
        )


def test_the_wall_does_not_scale_with_the_width(course):
    """Every run's containment is the cap, not the scaled profile's own.

    This is the whole of `race2.track`'s reason to exist, and a regression here
    is a course no camera can see into - which is a picture problem that would
    otherwise only be found by looking at a render.
    """
    for name, run in course.runs.items():
        assert isinstance(run, RaceRun), name
        assert run.containment == pytest.approx(WALL_CAP * 1.754386, rel=1e-4), name
        assert run.wall_angle() < 26.0, f"{name} needs {run.wall_angle():.1f} deg of look-down"


def test_no_wheel_traps_a_marble_against_a_wall(course):
    """Every wheel either leaves a marble's width beside it or is a stated gate.

    The first build sized the blades from Race #1's absolute tip radius, which
    at scale 2.0 reaches 1.80 layout units into a 1.17 half-width channel: the
    blade swept through both walls and seven of eight racers jammed. The rule
    is that a wheel is a disruptor - more than a diameter of clear channel
    either side - or a gate, and that there is exactly one gate.
    """
    gates = []
    for module in course.machine:
        if not isinstance(module, Wheel):
            continue
        gap = module.side_gap()
        assert gap > -0.01, f"{module.id} blade reaches through the wall by {-gap:.2f}"
        if gap < 2.0 * 0.285:
            gates.append(module.id)
        else:
            assert gap > 0.62, f"{module.id} leaves only {gap:.2f} beside the blade"
    assert gates == ["sweep"], f"expected one gate, found {gates}"


def test_every_collider_arrives_in_bullet_whole(course):
    world = MarbleWorld(DEFAULT_CONFIG)
    try:
        course.machine.build(world)
        findings = check_collider_bounds(world)
        assert not findings, [f.detail for f in findings]
    finally:
        world.close()


def test_the_meshes_are_well_formed(course):
    """No phantom spans, no degenerate triangles, no unclosed strips.

    `expect_components=None` because a station's collider is *meant* to be
    several pieces - a start shelf is a back wall, two side walls and seven
    dividers merged into one mesh so that Bullet holds one shape instead of
    sixteen bodies. The component count is the one check that would be a false
    finding here; everything else `check_mesh` does still applies, and the
    longest-edge bound in particular is why those walls are built in segments.
    """
    for module in course.machine:
        for mesh in module.local_colliders():
            findings = check_mesh(mesh, expect_components=None)
            assert not findings, f"{module.id}: {[f.detail for f in findings]}"


def test_the_start_releases_every_bay_in_the_same_tick(course):
    """The one claim the start rests on, read off the actuators.

    Not off the docstring: a test that read the prose would be checking the
    prose. `panel_release_times` returns what the simulation is handed.
    """
    start = course.machine.modules["start"]
    times = start.panel_release_times()
    assert times, "the start has no floor"
    assert len(set(times)) == 1, f"the floor opens at {sorted(set(times))}"


def test_the_bays_are_evenly_spaced_and_fit_a_marble(course):
    start = course.machine.modules["start"]
    offsets = [start.bay_across(index) for index in range(start.bays)]
    steps = {round(a - b, 6) for a, b in zip(offsets, offsets[1:])}
    assert len(steps) == 1, f"uneven bay pitch: {steps}"
    gap = start.BAY_PITCH - 2.0 * start.FIN_RADIUS
    assert gap > 2.0 * 0.285, f"a {gap:.3f} bay cannot hold a 0.570 marble"


def test_the_head_band_is_wide_enough_for_the_start(course):
    """Every bay drops onto floor, not onto a rail.

    A narrower head is a lane bias built into the first tick, and it is the
    kind that would never show up as a jam - only as a correlation.
    """
    start = course.machine.modules["start"]
    head = course.runs["head"]
    half = 0.94 * head.scale * head.widths[0]
    assert start.half_spread + 0.285 < half, (
        f"bays reach {start.half_spread + 0.285:.2f}, the band is {half:.2f}"
    )


def test_the_three_concepts_all_build_on_the_same_skeleton(course):
    """The comparison in `docs/race2_drama_camera.md` rests on this.

    If the three concepts stopped sharing a plan, their benchmark would be
    comparing size as well as topology and the conclusion would not hold.
    """
    shapes = {}
    for name in concepts.concept_names():
        built = concepts.build(name)
        shapes[name] = (
            round(built.drop(), 2),
            tuple(round(v, 1) for v in built.footprint()),
        )
    assert len(set(shapes.values())) == 1, shapes

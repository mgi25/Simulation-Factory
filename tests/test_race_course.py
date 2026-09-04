"""Race V0.1 tests: course data, the progress ladder and the prototype course.

The prototype-course tests are the important half of this file. They assert
the geometric invariants the course was actually debugged into satisfying -
respawn points clear of geometry, arm tips clear of the walls, a funnel hole
too wide to arch across - so that a later tweak to a coordinate cannot
quietly reintroduce a jam or a trap that took a batch of seeds to find.
"""

from __future__ import annotations

import math

import pytest

from engine.arena import CANVAS_WIDTH
from engine.arena_layout import ObstacleSpec
from race.config import RACER_RADIUS
from race.course import (
    BOUNCY,
    ROLE_GATE,
    ROLE_JUMP_PAD,
    ROLE_PEG,
    ROLE_WALL,
    SLICK,
    TRACK,
    Checkpoint,
    CoursePiece,
    RaceCourse,
    RacerSpawn,
    SpinnerSpec,
    box_between,
)
from race.courses import COURSE_NAMES, build_course
from race.courses.builder import CourseBuilder, curve_points
from race.courses.prototype import PROTOTYPE_COURSE_ID, build_prototype_course

RACER_DIAMETER = 2.0 * RACER_RADIUS
# A respawn point has to be clear enough that a recovered racer is not
# resolving a penetration on the tick it arrives.
RESPAWN_CLEARANCE = 6.0


@pytest.fixture
def course() -> RaceCourse:
    return build_prototype_course(4242)


def tiny_course(**overrides) -> RaceCourse:
    """A two-checkpoint course, for testing the ladder without geometry."""
    defaults = dict(
        course_id="tiny",
        width=1000.0,
        top=0.0,
        bottom=1000.0,
        pieces=(),
        spinners=(),
        checkpoints=(
            Checkpoint(0, "start", 100.0, (500.0, 120.0)),
            Checkpoint(1, "finish", 900.0, (500.0, 920.0)),
        ),
        spawns=(RacerSpawn(0, 500.0, 50.0),),
        sections=(),
    )
    defaults.update(overrides)
    return RaceCourse(**defaults)


# --- primitives -------------------------------------------------------------


def test_box_between_spans_its_two_endpoints() -> None:
    start, end = (40.0, 700.0), (860.0, 900.0)
    spec = box_between(7, start, end, 24.0)
    assert spec.obstacle_id == 7
    assert spec.center == pytest.approx(((40 + 860) / 2, (700 + 900) / 2))
    assert spec.width == pytest.approx(math.dist(start, end))
    assert spec.height == pytest.approx(24.0)
    assert spec.rotation_degrees == pytest.approx(
        math.degrees(math.atan2(200.0, 820.0))
    )


def test_box_between_reuses_obstacle_spec_geometry() -> None:
    """A ramp is an ObstacleSpec, so the duel geometry helpers apply to it."""
    spec = box_between(0, (0.0, 0.0), (100.0, 0.0), 20.0)
    assert isinstance(spec, ObstacleSpec)
    # A point 50px off the middle of a 20px-thick bar is 40px from it.
    assert spec.distance_to_point(50.0, 50.0) == pytest.approx(40.0)


def test_box_between_rejects_a_zero_length_span() -> None:
    with pytest.raises(ValueError):
        box_between(0, (10.0, 10.0), (10.0, 10.0), 20.0)


def test_curve_points_start_and_end_exactly_on_target() -> None:
    points = curve_points((40.0, 100.0), (400.0, 700.0), segments=5, bulge=2.0)
    assert len(points) == 6
    assert points[0] == pytest.approx((40.0, 100.0))
    assert points[-1] == pytest.approx((400.0, 700.0))


def test_curve_points_bulge_decides_where_the_bend_is() -> None:
    """Bulge above one bends early; below one bends late."""
    early = curve_points((0.0, 0.0), (100.0, 100.0), segments=2, bulge=2.0)
    straight = curve_points((0.0, 0.0), (100.0, 100.0), segments=2, bulge=1.0)
    late = curve_points((0.0, 0.0), (100.0, 100.0), segments=2, bulge=0.5)
    assert early[1][0] > straight[1][0] > late[1][0]
    assert straight[1][0] == pytest.approx(50.0)
    # y is always spaced evenly, whatever the bulge.
    for points in (early, straight, late):
        assert points[1][1] == pytest.approx(50.0)


def test_curve_points_needs_at_least_one_segment() -> None:
    with pytest.raises(ValueError):
        curve_points((0.0, 0.0), (1.0, 1.0), segments=0)


def test_race_materials_are_not_the_duel_materials() -> None:
    """A race surface must absorb energy; a duel surface must conserve it."""
    for material in (TRACK, SLICK, BOUNCY):
        assert 0.0 < material.elasticity < 1.0
        assert material.friction >= 0.0
    # Only the slick surfaces are nearly frictionless, and none is elastic.
    assert SLICK.friction < TRACK.friction
    assert BOUNCY.elasticity > TRACK.elasticity


# --- spinners ---------------------------------------------------------------


def test_spinner_reach_and_tip_speed() -> None:
    spinner = SpinnerSpec(0, 500.0, 500.0, 50.0, 3, 200.0, 30.0, 180.0)
    assert spinner.reach == pytest.approx(250.0)
    assert spinner.tip_speed == pytest.approx(math.radians(180.0) * 250.0)


def test_spinner_arms_are_evenly_spaced_and_turn_together() -> None:
    spinner = SpinnerSpec(0, 0.0, 0.0, 40.0, 4, 100.0, 20.0, 90.0, start_angle=10.0)
    at_rest = spinner.arm_angles(0.0)
    assert at_rest == pytest.approx((10.0, 100.0, 190.0, 280.0))
    # One second at 90 deg/s moves every arm by the same 90 degrees.
    later = spinner.arm_angles(1.0)
    assert [b - a for a, b in zip(at_rest, later)] == pytest.approx([90.0] * 4)


def test_spinner_direction_follows_the_sign_of_its_speed() -> None:
    clockwise = SpinnerSpec(0, 0.0, 0.0, 10.0, 2, 50.0, 10.0, 120.0)
    other_way = SpinnerSpec(1, 0.0, 0.0, 10.0, 2, 50.0, 10.0, -120.0)
    assert clockwise.arm_angles(1.0)[0] > 0.0
    assert other_way.arm_angles(1.0)[0] < 0.0
    assert clockwise.tip_speed == pytest.approx(other_way.tip_speed)


def test_spinner_arm_box_sits_beyond_the_hub() -> None:
    spinner = SpinnerSpec(0, 0.0, 0.0, 40.0, 3, 100.0, 20.0, 90.0)
    length, thickness, distance = spinner.arm_local_box()
    assert (length, thickness) == (100.0, 20.0)
    # Centre of the arm is half its length past the hub edge.
    assert distance == pytest.approx(90.0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"arm_count": 0},
        {"arm_length": 0.0},
        {"arm_thickness": -1.0},
    ],
)
def test_spinner_rejects_impossible_arms(kwargs) -> None:
    fields = dict(
        spinner_id=0,
        x=0.0,
        y=0.0,
        hub_radius=10.0,
        arm_count=2,
        arm_length=50.0,
        arm_thickness=10.0,
        angular_speed=90.0,
    )
    fields.update(kwargs)
    with pytest.raises(ValueError):
        SpinnerSpec(**fields)


# --- the progress ladder ----------------------------------------------------


def test_checkpoints_must_be_ordered_and_indexed() -> None:
    with pytest.raises(ValueError):
        tiny_course(
            checkpoints=(
                Checkpoint(0, "start", 100.0, (0.0, 0.0)),
                Checkpoint(2, "finish", 900.0, (0.0, 0.0)),
            )
        )
    with pytest.raises(ValueError):
        tiny_course(
            checkpoints=(
                Checkpoint(0, "start", 900.0, (0.0, 0.0)),
                Checkpoint(1, "finish", 100.0, (0.0, 0.0)),
            )
        )


def test_a_course_needs_a_start_and_a_finish() -> None:
    with pytest.raises(ValueError):
        tiny_course(checkpoints=(Checkpoint(0, "start", 100.0, (0.0, 0.0)),))


def test_reached_index_is_the_last_plane_passed() -> None:
    course = tiny_course()
    assert course.reached_index(50.0) == -1     # still in the pen
    assert course.reached_index(100.0) == 0     # exactly on the plane
    assert course.reached_index(500.0) == 0
    assert course.reached_index(900.0) == 1
    assert course.reached_index(2000.0) == 1    # cannot exceed the finish


def test_progress_is_zero_at_the_start_plane_and_last_at_the_finish() -> None:
    course = tiny_course()
    assert course.progress_at(100.0) == pytest.approx(0.0)
    assert course.progress_at(500.0) == pytest.approx(0.5)
    assert course.progress_at(900.0) == pytest.approx(1.0)
    assert course.progress_at(1500.0) == pytest.approx(1.0)


def test_progress_before_the_start_is_negative_so_the_grid_still_ranks() -> None:
    course = tiny_course()
    assert course.progress_at(50.0) < 0.0
    assert course.progress_at(20.0) < course.progress_at(50.0)


def test_progress_never_decreases_down_the_course(course: RaceCourse) -> None:
    """The ranking key has to be monotonic in the direction of travel.

    Without this, a racer further down the course could rank behind one that
    is not, which is the whole reason progress is measured along a ladder
    rather than as distance to the finish.
    """
    heights = [course.top + step * 20.0 for step in range(int(course.height / 20.0) + 1)]
    values = [course.progress_at(y) for y in heights]
    assert all(later >= earlier for earlier, later in zip(values, values[1:]))


def test_progress_matches_each_checkpoint_index_exactly(course: RaceCourse) -> None:
    for checkpoint in course.checkpoints:
        assert course.progress_at(checkpoint.y) == pytest.approx(
            float(checkpoint.index)
        )


def test_out_of_bounds_allows_a_margin_but_not_a_departure() -> None:
    course = tiny_course()
    assert not course.out_of_bounds(500.0, 500.0)
    assert not course.out_of_bounds(-100.0, 500.0)   # inside the margin
    assert course.out_of_bounds(-1000.0, 500.0)
    assert course.out_of_bounds(500.0, 10_000.0)


def test_section_at_names_the_stretch(course: RaceCourse) -> None:
    assert course.section_at(course.top).name == "start"
    assert course.section_at(course.finish_y - 1.0).name == "finish"
    # Sections tile the course with no gaps between them.
    for earlier, later in zip(course.sections, course.sections[1:]):
        assert earlier.bottom == pytest.approx(later.top)


# --- the builder ------------------------------------------------------------


def test_builder_hands_out_unique_contiguous_piece_ids() -> None:
    builder = CourseBuilder("t", 1000.0, 0.0)
    builder.begin_section("a", 0.0)
    builder.ramp((0.0, 0.0), (100.0, 10.0), 20.0)
    builder.peg(50.0, 200.0, 30.0)
    builder.gate((0.0, 300.0), (100.0, 300.0), 20.0)
    builder.checkpoint("start", 10.0, (50.0, 20.0))
    builder.checkpoint("finish", 400.0, (50.0, 410.0))
    course = builder.finish(500.0)
    assert [piece.piece_id for piece in course.pieces] == [0, 1, 2]
    assert [piece.role for piece in course.pieces] == [
        "ramp",
        ROLE_PEG,
        ROLE_GATE,
    ]


def test_builder_chain_overlaps_at_every_joint() -> None:
    """Neighbouring boxes must not leave a seam a racer could pass through."""
    builder = CourseBuilder("t", 1000.0, 0.0)
    builder.begin_section("a", 0.0)
    pieces = builder.chain(((0.0, 0.0), (100.0, 100.0), (100.0, 300.0)), 26.0)
    assert len(pieces) == 2
    first, second = pieces
    assert first.spec.clearance_to(second.spec) == pytest.approx(0.0)


def test_builder_jump_pad_angle_reads_as_degrees_from_straight_up() -> None:
    builder = CourseBuilder("t", 1000.0, 0.0)
    builder.begin_section("a", 0.0)
    straight_up = builder.jump_pad((0.0, 0.0), (100.0, 0.0), 20.0, 0.0, 500.0)
    assert straight_up.impulse == pytest.approx((0.0, -500.0))
    leaning = builder.jump_pad((0.0, 0.0), (100.0, 0.0), 20.0, 90.0, 500.0)
    assert leaning.impulse == pytest.approx((500.0, 0.0))
    assert straight_up.impulse_magnitude == pytest.approx(500.0)


def test_builder_sections_close_on_the_next_one() -> None:
    builder = CourseBuilder("t", 1000.0, 0.0)
    builder.begin_section("first", 0.0)
    builder.begin_section("second", 200.0)
    builder.checkpoint("start", 10.0, (0.0, 0.0))
    builder.checkpoint("finish", 400.0, (0.0, 0.0))
    course = builder.finish(500.0)
    assert [(s.name, s.top, s.bottom) for s in course.sections] == [
        ("first", 0.0, 200.0),
        ("second", 200.0, 500.0),
    ]


# --- the prototype course ---------------------------------------------------


def test_course_registry_knows_the_prototype() -> None:
    assert PROTOTYPE_COURSE_ID in COURSE_NAMES
    assert build_course(PROTOTYPE_COURSE_ID, 1).course_id == PROTOTYPE_COURSE_ID
    with pytest.raises(ValueError):
        build_course("no-such-course", 1)


def test_same_seed_builds_an_identical_course() -> None:
    first, second = build_prototype_course(99), build_prototype_course(99)
    assert first.pieces == second.pieces
    assert first.spinners == second.spinners
    assert first.checkpoints == second.checkpoints


def test_only_the_spinners_vary_with_the_seed() -> None:
    """Fixed geometry is what makes results across seeds comparable."""
    first, second = build_prototype_course(1), build_prototype_course(2)
    assert first.pieces == second.pieces
    assert first.checkpoints == second.checkpoints
    assert first.spinners != second.spinners
    for a, b in zip(first.spinners, second.spinners):
        assert (a.x, a.y, a.arm_count, a.arm_length) == (b.x, b.y, b.arm_count, b.arm_length)
        # Direction is a design decision and never flips with the seed.
        assert math.copysign(1.0, a.angular_speed) == math.copysign(1.0, b.angular_speed)


def test_course_has_the_three_obstacle_types_v0_1_requires(course: RaceCourse) -> None:
    assert len(course.spinners) >= 1
    assert len(course.jump_pads) >= 1
    # The funnel: a hole in a floor, identified by the throat gap recorded
    # in the course metadata.
    assert course.metadata["funnel_throat"] > 0.0


def test_course_has_a_gate_and_ten_grid_slots(course: RaceCourse) -> None:
    assert len(course.gates) == 1
    assert len(course.spawns) >= 10


def test_grid_slots_are_far_enough_apart_to_spawn_ten_racers(
    course: RaceCourse,
) -> None:
    from race.config import SPAWN_JITTER_X, SPAWN_JITTER_Y

    slots = course.spawns[:10]
    for index, first in enumerate(slots):
        for second in slots[index + 1 :]:
            # Worst case is per axis, not diagonal: jitter can only close a
            # gap along the axis that gap lies on, so each axis is reduced
            # by twice its own jitter and the result recombined.
            dx = max(0.0, abs(first.x - second.x) - 2.0 * SPAWN_JITTER_X)
            dy = max(0.0, abs(first.y - second.y) - 2.0 * SPAWN_JITTER_Y)
            gap = math.hypot(dx, dy)
            assert gap > RACER_DIAMETER, (
                f"slots {first.slot} and {second.slot} can start "
                f"{gap:.1f}px apart"
            )


def test_funnel_hole_is_too_wide_for_two_racers_to_arch_across(
    course: RaceCourse,
) -> None:
    """The one measurement that decides whether the funnel can lock up.

    Two racers wedging across a hole narrower than their combined diameter
    is ordinary hopper arching, and it stopped the whole field in roughly
    one seed in twenty before the hole was widened past it.
    """
    assert course.metadata["funnel_throat"] > RACER_DIAMETER


def test_every_respawn_point_is_clear_of_geometry(course: RaceCourse) -> None:
    """Recovery has to put a racer somewhere it can actually be.

    A respawn point inside a ramp, or inside the circle a spinner sweeps,
    would either eject the racer or feed it straight back into whatever it
    was rescued from.
    """
    for checkpoint in course.checkpoints:
        x, y = checkpoint.respawn
        for piece in course.pieces:
            if piece.role == ROLE_WALL:
                continue
            clearance = piece.spec.clearance_to_circle(x, y, RACER_RADIUS)
            assert clearance > RESPAWN_CLEARANCE, (
                f"{checkpoint.name} respawn is {clearance:.1f}px from "
                f"piece {piece.piece_id} ({piece.role})"
            )
        for spinner in course.spinners:
            gap = math.dist((x, y), spinner.center) - spinner.reach - RACER_RADIUS
            assert gap > RESPAWN_CLEARANCE, (
                f"{checkpoint.name} respawn is inside spinner "
                f"{spinner.spinner_id}'s sweep"
            )


def test_respawn_points_are_inside_the_course(course: RaceCourse) -> None:
    for checkpoint in course.checkpoints:
        x, y = checkpoint.respawn
        assert not course.out_of_bounds(x, y)
        assert 0.0 < x < course.width


def test_respawn_points_never_move_a_racer_forwards(course: RaceCourse) -> None:
    """A rescue must not be a shortcut.

    Every respawn sits at or just past its own checkpoint plane and short of
    the next one, so recovery always costs a racer the ground it had made.
    """
    for checkpoint in course.checkpoints:
        respawn_progress = course.progress_at(checkpoint.respawn[1])
        assert respawn_progress >= checkpoint.index
        assert respawn_progress < checkpoint.index + 1


def test_spinner_arms_clear_the_side_walls_by_more_than_a_racer(
    course: RaceCourse,
) -> None:
    """A gap narrower than a racer is a trap, not a gap.

    A racer driven into one is batted against the wall by every passing arm
    instead of falling through it, and never gets out on its own.
    """
    from race.courses.prototype import PLAYABLE_LEFT, PLAYABLE_RIGHT

    for spinner in course.spinners:
        left_gap = (spinner.x - spinner.reach) - PLAYABLE_LEFT
        right_gap = PLAYABLE_RIGHT - (spinner.x + spinner.reach)
        assert left_gap > RACER_DIAMETER, f"spinner {spinner.spinner_id} left gap"
        assert right_gap > RACER_DIAMETER, f"spinner {spinner.spinner_id} right gap"


def test_spinner_sweeps_never_intersect(course: RaceCourse) -> None:
    """Two kinematic bodies would pass through each other, not collide."""
    for index, first in enumerate(course.spinners):
        for second in course.spinners[index + 1 :]:
            separation = math.dist(first.center, second.center)
            assert separation > first.reach + second.reach, (
                f"spinners {first.spinner_id} and {second.spinner_id} overlap"
            )


def test_spinner_arm_tips_stay_slower_than_a_racer_can_travel(
    course: RaceCourse,
) -> None:
    """A spinner should redirect a racer, not fire it across the course."""
    from race.config import MAX_SPEED

    for spinner in course.spinners:
        assert spinner.tip_speed < MAX_SPEED * 1.5


def test_no_piece_reaches_outside_the_course(course: RaceCourse) -> None:
    for piece in course.pieces:
        if piece.role == ROLE_WALL:
            continue  # the boundary is allowed to straddle the edge
        left, top, right, bottom = piece.bounds()
        assert left >= -1.0 and right <= CANVAS_WIDTH + 1.0
        assert top >= course.top - 1.0 and bottom <= course.bottom + 1.0


def test_the_course_is_taller_than_one_portrait_frame(course: RaceCourse) -> None:
    """Which is why there is a camera at all."""
    from engine.arena import CANVAS_HEIGHT

    assert course.height > 2 * CANVAS_HEIGHT


def test_jump_pads_push_racers_up_the_screen(course: RaceCourse) -> None:
    for pad in course.jump_pads:
        assert isinstance(pad, CoursePiece)
        assert pad.role == ROLE_JUMP_PAD
        assert pad.impulse[1] < 0.0, "a pad has to lift a racer, not press it down"
        assert 0.0 <= pad.impulse_jitter < 0.5

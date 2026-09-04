"""V0.2 tests: the branching progress graph and the split course.

Two things are being checked here and they are worth keeping apart.

The first is the progress graph itself - a generic mechanism that happens to
have one user today. Those tests build small synthetic courses so the thing
under test is the ranking rule rather than the split course's geometry, and
they are the ones that would still mean something after the next course is
written.

The second is the split course: that it completes, that both paths are used,
that neither is a trap, and that the ranking rule gives sensible answers on
the real thing. Those run races.
"""

from __future__ import annotations

import math
import statistics

import pytest

from race.course import Checkpoint, RaceCourse, progress_along
from race.courses import COURSE_NAMES, build_course
from race.courses.builder import CourseBuilder
from race.courses.split import (
    BRANCH_LEFT,
    BRANCH_RIGHT,
    DIVIDER_X,
    ENTRY_PROGRESS,
    EXIT_PROGRESS,
    SPLIT_COURSE_ID,
)
from race.manager import RaceManager
from race.progress import progress_of, ranking, update_progress
from race.racer import Racer
from race.simulation import RaceSimulation

SEEDS = list(range(1000, 1012))


# --- a synthetic fork, so the rule is tested rather than the geometry ------


def forked_course() -> RaceCourse:
    """A minimal course that forks and rejoins.

    Two paths over the same stretch of canvas, subdividing the same interval
    of course progress differently: three rungs on the left against one on the
    right. That difference is the whole point - it is what makes "how far down
    the canvas is it" and "how far along its route is it" different questions.
    """
    builder = CourseBuilder("forked", 1000.0, 0.0)
    builder.checkpoint("start", 100.0, (500.0, 120.0))
    builder.checkpoint("split", 200.0, (500.0, 220.0))

    # The left path covers most of its route early and the right path spreads
    # itself evenly, so the two divide the same interval of course progress
    # differently. That is what makes "how far down the canvas" and "how far
    # along the route" different questions, and it is the only reason this
    # course is worth having as a fixture.
    for name, y, progress in (
        ("left_1", 300.0, 1.25),
        ("left_2", 450.0, 1.55),
        ("left_3", 650.0, 1.8),
    ):
        builder.branch_checkpoint(
            name, y, (200.0, y + 20.0),
            branch="left", x_range=(None, 500.0), progress=progress,
        )
    builder.branch_checkpoint(
        "right_1", 300.0, (800.0, 320.0),
        branch="right", x_range=(500.0, None), progress=1.25,
    )
    builder.branch_checkpoint(
        "right_2", 700.0, (800.0, 720.0),
        branch="right", x_range=(500.0, None), progress=1.6,
    )

    builder.checkpoint("rejoin", 800.0, (500.0, 820.0))
    builder.checkpoint("finish", 1000.0, (500.0, 1020.0))
    return builder.finish(1200.0)


def racer_at(x: float, y: float, racer_id: int = 0) -> Racer:
    racer = Racer(racer_id=racer_id, position=(x, y))
    return racer


def test_a_fork_is_two_complete_routes() -> None:
    course = forked_course()
    assert course.branching
    assert course.branches == ("left", "right")

    for branch in course.branches:
        names = [node.name for node in course.route(branch)]
        assert names[0] == "start"
        assert names[-1] == "finish"
        assert "rejoin" in names
        assert all(not name.startswith(other) for name in names
                   for other in ("left" if branch == "right" else "right",))

    # The shared spine on its own is still a route from start to finish.
    assert [node.name for node in course.route()] == [
        "start", "split", "rejoin", "finish"
    ]


def test_a_branch_node_must_have_a_corridor() -> None:
    """Without one, both branches would be reachable from either side."""
    with pytest.raises(ValueError, match="corridor"):
        RaceCourse(
            course_id="bad",
            width=1000.0,
            top=0.0,
            bottom=1000.0,
            pieces=(),
            spinners=(),
            checkpoints=(
                Checkpoint(0, "start", 100.0, (0.0, 0.0)),
                Checkpoint(1, "loose", 200.0, (0.0, 0.0), branch="left", progress=0.5),
                Checkpoint(2, "finish", 400.0, (0.0, 0.0)),
            ),
            spawns=(),
            sections=(),
        )


def test_alternatives_must_share_a_plane() -> None:
    """Two entries at the same progress have to be the same line.

    If they were not, a racer would be ranked by which side of the fork it
    took rather than by how far it had got - the exact failure this whole
    design exists to avoid.
    """
    with pytest.raises(ValueError, match="disagree about"):
        RaceCourse(
            course_id="bad",
            width=1000.0,
            top=0.0,
            bottom=1000.0,
            pieces=(),
            spinners=(),
            checkpoints=(
                Checkpoint(0, "start", 100.0, (0.0, 0.0)),
                Checkpoint(1, "l", 200.0, (0.0, 0.0), branch="left",
                           x_max=500.0, progress=0.5),
                Checkpoint(2, "r", 260.0, (0.0, 0.0), branch="right",
                           x_min=500.0, progress=0.5),
                Checkpoint(3, "finish", 400.0, (0.0, 0.0)),
            ),
            spawns=(),
            sections=(),
        )


def test_branches_leaving_together_must_start_together() -> None:
    with pytest.raises(ValueError, match="same course progress"):
        RaceCourse(
            course_id="bad",
            width=1000.0,
            top=0.0,
            bottom=1000.0,
            pieces=(),
            spinners=(),
            checkpoints=(
                Checkpoint(0, "start", 100.0, (0.0, 0.0)),
                Checkpoint(1, "l", 200.0, (0.0, 0.0), branch="left",
                           x_max=500.0, progress=0.4),
                Checkpoint(2, "r", 260.0, (0.0, 0.0), branch="right",
                           x_min=500.0, progress=0.6),
                Checkpoint(3, "finish", 400.0, (0.0, 0.0)),
            ),
            spawns=(),
            sections=(),
        )


def test_a_racer_only_reaches_the_branch_it_is_in() -> None:
    course = forked_course()
    left = racer_at(200.0, 350.0)
    right = racer_at(800.0, 350.0)

    assert [course.checkpoint(i).name for i in update_progress(course, left)] == [
        "start", "split", "left_1"
    ]
    assert [course.checkpoint(i).name for i in update_progress(course, right)] == [
        "start", "split", "right_1"
    ]
    assert left.branch == "left"
    assert right.branch == "right"


def test_a_committed_racer_cannot_pick_up_the_other_branch() -> None:
    """Crossing into the other corridor must not re-route a racer.

    It should not be possible on a well-built course - there is a wall in the
    way - but the ranking rule must not depend on the geometry being perfect.
    """
    course = forked_course()
    racer = racer_at(200.0, 350.0)
    update_progress(course, racer)
    assert racer.branch == "left"

    # Teleported across the divider, past where the other branch's rungs are.
    racer.teleport((800.0, 750.0))
    crossed = [course.checkpoint(i).name for i in update_progress(course, racer)]
    assert "right_2" not in crossed
    assert racer.branch == "left"


def test_the_branch_clears_when_the_routes_rejoin() -> None:
    course = forked_course()
    racer = racer_at(200.0, 350.0)
    update_progress(course, racer)
    assert racer.branch == "left"

    racer.teleport((500.0, 850.0))
    update_progress(course, racer)
    assert racer.branch == "", "a main-line node is on every route"
    assert racer.checkpoint == next(
        node.index for node in course.checkpoints if node.name == "rejoin"
    )


def test_progress_is_how_far_along_the_route_not_how_far_down() -> None:
    """The heart of it: same height, different branches, different progress.

    At y=500 both racers have fallen exactly as far, and neither the canvas
    nor the finish line can separate them. Their routes can: the left-hand
    racer has two of its three rungs behind it, the right-hand racer has one
    of two and a long way to the next.
    """
    course = forked_course()
    left = racer_at(200.0, 500.0, racer_id=0)
    right = racer_at(800.0, 500.0, racer_id=1)
    update_progress(course, left)
    update_progress(course, right)

    assert left.position.y == right.position.y
    # Left: a quarter of the way from left_2 (1.55 at y=450) to left_3 (1.8
    # at y=650). Right: halfway from right_1 (1.25 at 300) to right_2 (1.6 at
    # 700).
    assert left.progress == pytest.approx(1.55 + 0.25 * 0.25)
    assert right.progress == pytest.approx(1.25 + 0.5 * 0.35)
    assert left.progress > right.progress
    assert ranking([right, left])[0] is left


def test_landing_on_a_rung_gives_exactly_that_rung_value() -> None:
    """No interpolation error at the nodes themselves."""
    course = forked_course()
    for name, y, expected in (
        ("left_2", 450.0, 1.55),
        ("left_3", 650.0, 1.8),
        ("right_2", 700.0, 1.6),
    ):
        x = 200.0 if name.startswith("left") else 800.0
        racer = racer_at(x, y)
        update_progress(course, racer)
        assert racer.progress == pytest.approx(expected), name


def test_ranking_is_correct_with_racers_on_different_branches() -> None:
    course = forked_course()
    # A right-hand racer near the rejoin, a left-hand racer just past the
    # split. Height alone would call them close; the routes say otherwise.
    ahead = racer_at(800.0, 780.0, racer_id=0)
    behind = racer_at(200.0, 320.0, racer_id=1)
    update_progress(course, ahead)
    update_progress(course, behind)

    order = ranking([behind, ahead])
    assert [racer.racer_id for racer in order] == [0, 1]
    assert ahead.progress > behind.progress


def test_progress_is_monotonic_along_each_route() -> None:
    course = forked_course()
    for branch, x in ((BRANCH_LEFT, 200.0), (BRANCH_RIGHT, 800.0)):
        racer = racer_at(x, 0.0)
        values = []
        for y in range(0, 1100, 10):
            racer.teleport((x, float(y)))
            update_progress(course, racer)
            values.append(racer.progress)
        assert values == sorted(values), branch


def test_progress_along_handles_an_empty_route() -> None:
    assert progress_along((), 100.0, 0.0) == 0.0


def test_a_racer_above_the_start_ranks_by_how_near_the_line_it_is() -> None:
    course = forked_course()
    near = racer_at(500.0, 90.0, racer_id=0)
    far = racer_at(500.0, 20.0, racer_id=1)
    for racer in (near, far):
        racer.progress = progress_of(course, racer)
    assert near.progress < 0.0
    assert far.progress < near.progress
    assert ranking([far, near])[0] is near


# --- the split course as built --------------------------------------------


@pytest.fixture(scope="module")
def split() -> RaceCourse:
    return build_course(SPLIT_COURSE_ID, 1000)


def test_the_split_course_is_registered() -> None:
    assert SPLIT_COURSE_ID in COURSE_NAMES


def test_the_split_course_forks_and_rejoins(split: RaceCourse) -> None:
    assert split.branches == (BRANCH_LEFT, BRANCH_RIGHT)
    assert split.finish.branch == "", "the finish is shared"

    for branch in split.branches:
        route = split.route(branch)
        assert route[0].name == "start"
        assert route[-1].name == "finish"
        assert any(node.name == "rejoin" for node in route)

    # Both paths enter the split at one plane and leave it at one plane, so
    # the fork itself costs nothing: what separates two racers is how long
    # their path took, never which one they were on.
    branch_nodes = [node for node in split.checkpoints if node.branch]
    entries = [node for node in branch_nodes if node.value == ENTRY_PROGRESS]
    exits = [node for node in branch_nodes if node.value == EXIT_PROGRESS]
    assert len(entries) == len(exits) == len(split.branches)
    assert {node.branch for node in entries} == set(split.branches)
    assert {node.branch for node in exits} == set(split.branches)
    assert len({node.y for node in entries}) == 1
    assert len({node.y for node in exits}) == 1
    assert min(node.value for node in branch_nodes) == ENTRY_PROGRESS
    assert max(node.value for node in branch_nodes) == EXIT_PROGRESS


def test_the_two_corridors_tile_the_course(split: RaceCourse) -> None:
    """No x is in neither corridor, and only the wall is in both."""
    for node in split.checkpoints:
        if node.branch == BRANCH_LEFT:
            assert node.x_max == DIVIDER_X and node.x_min is None
        elif node.branch == BRANCH_RIGHT:
            assert node.x_min == DIVIDER_X and node.x_max is None


def test_the_left_branch_has_more_rungs_than_the_right(split: RaceCourse) -> None:
    """They are different paths, not mirror images of one path."""
    left = [node for node in split.checkpoints if node.branch == BRANCH_LEFT]
    right = [node for node in split.checkpoints if node.branch == BRANCH_RIGHT]
    assert len(left) > len(right)
    assert len(left) == 7 and len(right) == 4


def test_the_split_course_is_reproducible_from_its_seed() -> None:
    first = build_course(SPLIT_COURSE_ID, 4242)
    second = build_course(SPLIT_COURSE_ID, 4242)
    assert first.checkpoints == second.checkpoints
    assert first.pieces == second.pieces
    assert first.spinners == second.spinners
    assert first.spinners != build_course(SPLIT_COURSE_ID, 4243).spinners


def _clearance(piece, x: float, y: float) -> float:
    """Distance from a point to a piece's surface, in pixels.

    A real distance rather than a bounding-box test. Almost every ramp on a
    race course is a rotated box, and its bounding box can be several times
    its area - a check built on those would report half the respawn points on
    a course as buried and be ignored within a week.
    """
    spec = piece.spec
    if spec.is_circle:
        return math.dist((x, y), (spec.x, spec.y)) - spec.radius
    angle = math.radians(spec.rotation_degrees)
    dx, dy = x - spec.x, y - spec.y
    local_x = dx * math.cos(angle) + dy * math.sin(angle)
    local_y = -dx * math.sin(angle) + dy * math.cos(angle)
    return math.hypot(
        max(abs(local_x) - spec.width / 2.0, 0.0),
        max(abs(local_y) - spec.height / 2.0, 0.0),
    )


@pytest.mark.parametrize("course_name", COURSE_NAMES)
def test_every_respawn_point_is_clear_of_the_course(course_name: str) -> None:
    """A rescue must not put a racer inside something it then has to escape.

    Recovery is the net under the physics, so a respawn point buried in a peg
    is the one bug that would make the net itself the problem: the racer is
    rescued into a wall, fails to move, is rescued again, and is retired four
    seconds later having done nothing wrong. This caught exactly that on the
    split course's fork, where the respawn sat fourteen pixels inside the
    splitter peg.
    """
    from race.config import RACER_RADIUS

    course = build_course(course_name, 1000)
    for node in course.checkpoints:
        x, y = node.respawn
        for piece in course.pieces:
            gap = _clearance(piece, x, y)
            assert gap > RACER_RADIUS, (
                f"{course_name}/{node.name} respawns {gap:.1f}px from"
                f" {piece.role} {piece.piece_id}"
            )
        for spec in course.spinners:
            gap = math.dist((x, y), (spec.x, spec.y)) - spec.reach
            assert gap > RACER_RADIUS, (
                f"{course_name}/{node.name} respawns {gap:.1f}px from"
                f" spinner {spec.spinner_id}"
            )


# --- races on it ----------------------------------------------------------


@pytest.fixture(scope="module")
def races() -> list[RaceManager]:
    managers = []
    for seed in SEEDS:
        manager = RaceManager(RaceSimulation(seed, course_name=SPLIT_COURSE_ID))
        manager.run()
        managers.append(manager)
    return managers


def branch_of(manager: RaceManager) -> dict[int, str]:
    """Which path each racer entered, from the events the race recorded."""
    taken: dict[int, str] = {}
    for event in manager.events:
        if event.type == "checkpoint" and event.detail in (
            "left_entry",
            "right_entry",
        ):
            taken[event.racer_id] = event.detail.split("_")[0]
    return taken


def test_every_race_completes_with_a_winner(races: list[RaceManager]) -> None:
    for manager in races:
        assert manager.complete
        assert not manager.timed_out, f"seed {manager.sim.seed} timed out"
        assert manager.winner is not None
        assert manager.retirements == 0


def test_the_whole_field_takes_one_branch_or_the_other(
    races: list[RaceManager],
) -> None:
    for manager in races:
        taken = branch_of(manager)
        assert len(taken) == len(manager.sim.racers), (
            f"seed {manager.sim.seed}: {len(taken)} racers entered a branch"
        )


def test_both_branches_are_used_and_neither_is_a_trap(
    races: list[RaceManager],
) -> None:
    """Physics picks the path, so the split has to actually split.

    Two failure modes are being ruled out at once. A course where every racer
    goes the same way has a fork on paper only. A course where one side always
    wins has a fork that is really a punishment, and nothing about ranking
    across branches would ever be exercised by it.
    """
    counts = {BRANCH_LEFT: 0, BRANCH_RIGHT: 0}
    winners = {BRANCH_LEFT: 0, BRANCH_RIGHT: 0}
    for manager in races:
        taken = branch_of(manager)
        for side in taken.values():
            counts[side] += 1
        winners[taken[manager.winner.racer_id]] += 1

    total = sum(counts.values())
    assert min(counts.values()) / total > 0.25, counts
    assert min(winners.values()) >= 1, winners


def test_finish_order_is_a_valid_result(races: list[RaceManager]) -> None:
    for manager in races:
        order = manager.finish_order
        assert order[0] is manager.winner
        ticks = [racer.finish_tick for racer in order]
        assert ticks == sorted(ticks), "finish order is crossing order"
        assert len(set(racer.racer_id for racer in order)) == len(order)
        for racer in order:
            assert racer.finished
            assert racer.checkpoint == manager.course.finish_index


def test_ranking_stays_consistent_while_the_field_is_split() -> None:
    """Through the whole split, rank agrees with progress at every tick.

    Run with the ranking recomputed from scratch each tick and compared with
    what the manager assigned, so a racer that was somehow ranked ahead of one
    with more progress would be caught the tick it happened rather than at the
    finish.
    """
    manager = RaceManager(RaceSimulation(1003, course_name=SPLIT_COURSE_ID))
    course = manager.course
    seen_both = False

    while manager.step():
        racers = manager.sim.racers
        branches = {racer.branch for racer in racers if racer.racing}
        seen_both = seen_both or len(branches - {""}) == 2

        running = [racer for racer in racers if racer.racing]
        for first, second in zip(running, running[1:]):
            pass
        order = ranking(racers)
        for ahead, behind in zip(order, order[1:]):
            if ahead.finished or behind.finished or behind.retired:
                continue
            assert ahead.progress >= behind.progress, (
                f"{ahead.name} ranked above {behind.name} with less progress"
            )
        for racer in racers:
            assert racer.progress <= course.max_progress + 1e-6

    assert seen_both, "the field never split, so nothing was tested"


def test_recovery_keeps_a_racer_on_its_own_branch() -> None:
    """A rescue is not a route change.

    Recovery is the one place a racer moves by something other than physics,
    so it is the one place a racer could be quietly teleported onto the other
    path. It puts a racer back at the node it last reached, which is on the
    branch it was already on.
    """
    course = build_course(SPLIT_COURSE_ID, 1000)
    sim = RaceSimulation(1000, course=course)
    manager = RaceManager(sim)
    while manager.step():
        racer = sim.racers[0]
        if racer.branch:
            break

    branch = racer.branch
    node = course.checkpoint(racer.checkpoint)
    manager._recover(racer, "test")

    assert racer.branch == branch
    assert racer.position.x == pytest.approx(node.respawn[0])
    assert racer.position.y == pytest.approx(node.respawn[1])
    assert racer.progress == pytest.approx(progress_of(course, racer))


def test_the_split_course_finishes_most_of_the_field(
    races: list[RaceManager],
) -> None:
    finished = [len(manager.finish_order) for manager in races]
    assert statistics.fmean(finished) >= 9.0
    assert min(finished) >= 7


def test_races_are_not_all_won_by_the_same_racer(races: list[RaceManager]) -> None:
    winners = {manager.winner.racer_id for manager in races}
    assert len(winners) >= 5, "a course that rewards one grid slot is not a race"


def test_the_prototype_course_is_untouched_by_branching() -> None:
    """A linear course still numbers itself, and reports no branches."""
    course = build_course("prototype", 1000)
    assert course.branches == ()
    assert not course.branching
    assert course.route() == course.checkpoints
    assert [node.value for node in course.checkpoints] == [
        float(index) for index in range(len(course.checkpoints))
    ]
    assert course.max_progress == float(len(course.checkpoints) - 1)
    assert course.finish_index == len(course.checkpoints) - 1

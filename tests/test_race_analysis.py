"""V0.4 tests: the race-quality metrics, and the course audit.

These are the numbers the V0.4 redesign was steered by, so what matters most
about them is that they cannot quietly become flattering. Every metric here is
tested against a trace built by hand, where the right answer is known by
construction rather than by running a race and believing the output - a
winner-lock computation that agreed with itself would be no use at all.

The handful of tests that do run real races check the properties that only a
real race can have: that observing one does not change it, that a course
builds a legal progress graph, and that the machine course is a genuine
improvement on the prototype rather than a differently-shaped one.
"""

from __future__ import annotations

import pytest

from race.analysis import (
    COMPETITIVE_GAP,
    PROGRESS_MARKS,
    RaceTrace,
    TraceSample,
    aggregate,
    format_analysis,
    lead_changes,
    overtakes_by_third,
    percentiles,
    race_metrics,
    slot_table,
    top3_turnover,
    trace_race,
    winner_lock,
    winner_worst_rank,
)
from race.audit import Finding, audit_course, clear_spans, point_clearance
from race.courses import build_course
from race.courses.machine import MACHINE_COURSE_ID, SECTION_ROLES
from race.manager import RaceManager
from race.simulation import RaceSimulation


# --- building a trace by hand ---------------------------------------------


def make_trace(
    orders: list[list[int]],
    winner_id: int = 0,
    step: float = 1.0,
    progress: list[list[float]] | None = None,
    slots: tuple[int, ...] | None = None,
    finish_order: tuple[int, ...] = (),
    finish_times: tuple[float | None, ...] | None = None,
) -> RaceTrace:
    """A trace whose every sample is stated, so a metric's answer is known.

    `orders[i]` is the field, best first, at second `i * step`. Progress
    defaults to a descending ladder that agrees with the order, because most
    of these tests are about position rather than distance.
    """
    field = max(max(order) for order in orders) + 1
    samples = []
    for index, order in enumerate(orders):
        if progress is not None:
            values = tuple(progress[index])
        else:
            spaced = [0.0] * field
            for place, racer_id in enumerate(order):
                spaced[racer_id] = 1.0 - 0.1 * place
            values = tuple(spaced)
        samples.append(
            TraceSample(
                tick=index,
                race_time=index * step,
                progress=values,
                order=tuple(order),
            )
        )
    return RaceTrace(
        seed=1,
        course_id="test",
        racer_count=field,
        samples=tuple(samples),
        winner_id=winner_id,
        winner_time=(len(orders) - 1) * step,
        spawn_slots=slots or tuple(range(field)),
        finish_times=finish_times or tuple([None] * field),
        finish_order=finish_order,
    )


# --- winner lock ------------------------------------------------------------


def test_winner_lock_is_the_last_time_first_place_changed_hands() -> None:
    # 1 leads, then 0 takes it, loses it, and takes it back at t=4.
    trace = make_trace([[1, 0], [0, 1], [1, 0], [1, 0], [0, 1], [0, 1]])
    seconds, fraction = winner_lock(trace)
    assert seconds == 4.0
    assert fraction == pytest.approx(4.0 / 5.0)


def test_a_winner_that_led_from_the_start_locks_at_zero() -> None:
    trace = make_trace([[0, 1], [0, 1], [0, 1], [0, 1]])
    seconds, fraction = winner_lock(trace)
    assert seconds == 0.0
    assert fraction == 0.0


def test_a_winner_that_never_led_locks_at_the_line() -> None:
    """Taking the lead by crossing it is the latest lock there is.

    The trace's last sample is the moment the winner finished, and if it was
    still second there, first place changed hands after every sample this
    metric can see.
    """
    trace = make_trace([[1, 0], [1, 0], [1, 0], [1, 0]])
    seconds, fraction = winner_lock(trace)
    assert seconds == 3.0
    assert fraction == 1.0


def test_winner_lock_ignores_everything_after_the_winner_crossed() -> None:
    """The pack coming home cannot change who won, so it is not looked at.

    Without this the metric would report every race as locking at the moment
    the *last* racer finished, which is the same number for every race.
    """
    # 1 leads to t=2; 0 leads from t=3 onwards. The winner crosses at t=4,
    # so the six samples after that are the pack coming home.
    early = [
        TraceSample(index, float(index), (0.9, 1.0), (1, 0))
        for index in range(3)
    ]
    late = [
        TraceSample(index, float(index), (1.0, 0.9), (0, 1))
        for index in range(3, 10)
    ]
    trace = RaceTrace(
        seed=1,
        course_id="test",
        racer_count=2,
        samples=tuple(early + late),
        winner_id=0,
        # The winner crossed at t=4, so only the first five samples count.
        winner_time=4.0,
        spawn_slots=(0, 1),
        finish_times=(4.0, 6.0),
        finish_order=(0, 1),
    )
    seconds, _ = winner_lock(trace)
    assert seconds == 3.0


def test_a_race_with_no_winner_has_no_lock() -> None:
    trace = make_trace([[0, 1], [0, 1]], winner_id=0)
    undecided = RaceTrace(
        seed=trace.seed,
        course_id=trace.course_id,
        racer_count=trace.racer_count,
        samples=trace.samples,
        winner_id=None,
        winner_time=None,
        spawn_slots=trace.spawn_slots,
        finish_times=trace.finish_times,
        finish_order=(),
    )
    assert winner_lock(undecided) == (None, None)


# --- lead changes, podium turnover, comebacks ------------------------------


def test_lead_changes_counts_each_handover_once() -> None:
    trace = make_trace([[0, 1], [0, 1], [1, 0], [1, 0], [0, 1]])
    assert lead_changes(trace) == 2


def test_top3_turnover_reports_who_and_how_often() -> None:
    trace = make_trace(
        [
            [0, 1, 2, 3, 4],
            [0, 1, 2, 3, 4],
            [0, 1, 3, 2, 4],
            [4, 0, 1, 2, 3],
        ]
    )
    distinct, changes = top3_turnover(trace)
    # 0,1,2 then 0,1,3 then 4,0,1 - five racers held a podium place, and the
    # set changed on two of the three transitions.
    assert distinct == 5
    assert changes == 2


def test_the_comeback_metric_ignores_the_opening() -> None:
    """A racer that is last two seconds in has not made a comeback yet.

    The field is still leaving the grid then, and counting it would score
    every race the same. Only positions after the first quarter count.
    """
    orders = [[9, 0], [9, 0], [0, 9], [0, 9], [0, 9]]
    trace = make_trace(orders, winner_id=0)
    assert winner_worst_rank(trace, after=0.0) == 2
    assert winner_worst_rank(trace, after=0.5) == 1


def test_overtakes_are_bucketed_into_thirds_of_the_winners_run() -> None:
    orders = [[0, 1, 2], [1, 0, 2], [1, 0, 2], [1, 2, 0], [1, 2, 0], [1, 2, 0], [1, 2, 0]]
    # Seven samples a second apart, winner home at t=6: the thirds are
    # (0, 2], (2, 4] and (4, 6]. One swap lands in the first, one in the
    # second, and the order never moves again.
    first, middle, last = overtakes_by_third(make_trace(orders, winner_id=1))
    assert (first, middle, last) == (1, 1, 0)


# --- progress sampling ------------------------------------------------------


def test_a_mark_is_the_sample_nearest_that_fraction_of_the_race() -> None:
    trace = make_trace([[0, 1]] * 11, step=1.0)
    assert trace.at_fraction(0.0).race_time == 0.0
    assert trace.at_fraction(0.5).race_time == 5.0
    assert trace.at_fraction(1.0).race_time == 10.0


def test_every_requested_mark_appears_in_the_metrics() -> None:
    trace = make_trace([[0, 1, 2]] * 12, winner_id=0)
    marks = race_metrics(trace)["marks"]
    for fraction in PROGRESS_MARKS:
        assert str(int(round(fraction * 100))) in marks


def test_pack_spread_and_competitive_count_measure_the_same_field() -> None:
    """Competitive means "within a tenth of the course of the lead"."""
    sample = TraceSample(
        tick=0,
        race_time=1.0,
        # Leader at 0.90; then 0.85 (in), 0.79 (out by a hair), 0.40 (out).
        progress=(0.90, 0.85, 0.79, 0.40),
        order=(0, 1, 2, 3),
    )
    assert sample.competitive(COMPETITIVE_GAP) == 2
    assert sample.spread() == pytest.approx(0.50)
    assert sample.gap_behind_leader(3) == pytest.approx(0.50)


def test_a_racer_out_of_the_order_ranks_past_the_end_of_the_field() -> None:
    sample = TraceSample(0, 0.0, (0.5, 0.4, 0.3), (0, 1))
    assert sample.rank_of(0) == 1
    assert sample.rank_of(2) == 3


# --- starting slots ---------------------------------------------------------


def test_slot_statistics_count_the_slot_and_not_the_racer() -> None:
    """The fairness question is about the grid position, not the identity.

    Racer ids are shuffled between slots by seed, so a course where the
    outside slot always wins still shows every id winning sometimes. Counting
    ids would call that course fair.
    """
    records = [
        {
            "winner_slot": 3,
            "slots_used": [0, 1, 2, 3],
            "slot_finish": {"0": 4, "1": 3, "2": 2, "3": 1},
            "slot_progress_25": {"0": 0.1, "1": 0.2, "2": 0.3, "3": 0.4},
            "slot_progress_50": {"0": 0.2, "1": 0.3, "2": 0.4, "3": 0.5},
        },
        {
            "winner_slot": 3,
            "slots_used": [0, 1, 2, 3],
            "slot_finish": {"0": 3, "1": 4, "2": 2, "3": 1},
            "slot_progress_25": {"0": 0.1, "1": 0.1, "2": 0.3, "3": 0.5},
            "slot_progress_50": {"0": 0.2, "1": 0.2, "2": 0.4, "3": 0.6},
        },
    ]
    table = slot_table(records, slots=4)
    assert [row["wins"] for row in table] == [0, 0, 0, 2]
    assert table[3]["win_pct"] == pytest.approx(100.0)
    assert table[0]["mean_final_position"] == pytest.approx(3.5)
    assert table[3]["mean_progress_25"] == pytest.approx(0.45)


def test_slot_bias_reports_the_strongest_and_weakest_slots() -> None:
    records = [{"winner_slot": 0, "slots_used": [0, 1], "slot_finish": {}}] * 3 + [
        {"winner_slot": 1, "slots_used": [0, 1], "slot_finish": {}}
    ]
    report = aggregate(
        [dict(record, winner_id=0, marks={}, lead_changes=0, podium_racers=3,
              podium_changes=0, winner_worst_rank=1, overtakes_first_third=0,
              overtakes_middle_third=0, overtakes_final_third=0,
              final_margin=None, winner_lock_fraction=0.5,
              winner_lock_seconds=1.0) for record in records],
        slots=2,
    )
    assert report["slot_bias"]["strongest"] == 0
    assert report["slot_bias"]["weakest"] == 1
    assert report["slot_bias"]["ratio"] == pytest.approx(3.0)


def test_a_slot_that_never_won_gives_no_ratio_rather_than_infinity() -> None:
    table = [
        {"slot": 0, "starts": 10, "wins": 5, "win_pct": 50.0,
         "mean_final_position": None, "mean_progress_25": None,
         "mean_progress_50": None},
        {"slot": 1, "starts": 10, "wins": 0, "win_pct": 0.0,
         "mean_final_position": None, "mean_progress_25": None,
         "mean_progress_50": None},
    ]
    from race.analysis import _slot_bias

    bias = _slot_bias(table, [50.0, 0.0])
    assert bias["ratio"] is None
    assert bias["min_win_pct"] == 0.0


def test_percentiles_need_no_interpolation_policy() -> None:
    assert percentiles([1, 2, 3, 4, 5])["p50"] == 3
    assert percentiles([])["p50"] is None


# --- tracing a real race ----------------------------------------------------


@pytest.fixture(scope="module")
def traced() -> tuple[RaceManager, RaceTrace]:
    return trace_race(1000, course_name=MACHINE_COURSE_ID, racer_count=10)


def test_tracing_a_race_does_not_change_it(traced) -> None:
    """The metric layer observes; it must not participate.

    An analysis pass that drew from a seeded stream, or stepped the manager
    its own way, would measure a race nobody else can reproduce - and the
    render would then be of a different race from the one that was selected.
    """
    manager, _ = traced
    plain = RaceManager(
        RaceSimulation(1000, course_name=MACHINE_COURSE_ID, racer_count=10)
    )
    plain.run()
    assert plain.winner is not None
    assert manager.winner is not None
    assert plain.winner.racer_id == manager.winner.racer_id
    assert plain.winner_time == manager.winner_time
    assert [racer.racer_id for racer in plain.finish_order] == [
        racer.racer_id for racer in manager.finish_order
    ]


def test_a_trace_samples_the_whole_race(traced) -> None:
    _, trace = traced
    assert len(trace.samples) > 100
    times = [sample.race_time for sample in trace.samples]
    assert times == sorted(times)
    assert trace.winner_time is not None
    assert trace.decided[-1].race_time <= trace.winner_time


def test_progress_is_normalised_to_the_course(traced) -> None:
    _, trace = traced
    for sample in trace.samples:
        for value in sample.progress:
            assert -0.2 <= value <= 1.05


def test_metrics_survive_a_round_trip_through_json(traced) -> None:
    import json

    _, trace = traced
    record = race_metrics(trace)
    assert json.loads(json.dumps(record)) == record


def test_the_report_block_names_every_slot(traced) -> None:
    _, trace = traced
    report = aggregate([race_metrics(trace)], slots=len(set(trace.spawn_slots)))
    text = format_analysis(report)
    assert "Winner lock" in text
    assert "Starting slot:" in text


# --- the course audit -------------------------------------------------------


def test_point_clearance_is_negative_inside_a_shape() -> None:
    course = build_course(MACHINE_COURSE_ID, 1000)
    peg = next(piece.spec for piece in course.pieces if piece.spec.is_circle)
    assert point_clearance(peg.center, peg) == pytest.approx(-peg.radius)
    outside = (peg.x + peg.radius + 10.0, peg.y)
    assert point_clearance(outside, peg) == pytest.approx(10.0)


def test_clear_spans_can_drop_the_pegs() -> None:
    """A peg is not a hopper lip, and an arching check must not think it is.

    A racer goes round a peg and between two of them; counting them as walls
    would report every row of plinko as a throat about to jam.
    """
    course = build_course(MACHINE_COURSE_ID, 1000)
    y = 810.0
    with_pegs = clear_spans(course, y)
    without = clear_spans(course, y, walls_only=True)
    assert len(with_pegs) > len(without)


@pytest.mark.parametrize("name", ["prototype", "split", "machine"])
def test_no_shipped_course_has_an_audit_error(name: str) -> None:
    """Errors are the failures that cost a batch of races to find otherwise.

    A respawn inside geometry, a rotor arm sweeping through a wall, a gap a
    racer can be driven into and cannot leave: each one shows up thousands of
    ticks later as "stuck" or "retired", and none of them is visible in the
    course description.
    """
    findings = audit_course(build_course(name, 1000))
    errors = [finding for finding in findings if finding.severity == "error"]
    assert errors == [], "\n".join(str(finding) for finding in errors)


def test_the_audit_finds_a_respawn_buried_in_geometry() -> None:
    """The check has to fail on a course that is actually broken."""
    from race.course import Checkpoint, RaceCourse

    course = build_course(MACHINE_COURSE_ID, 1000)
    peg = next(piece.spec for piece in course.pieces if piece.spec.is_circle)
    broken = RaceCourse(
        course_id=course.course_id,
        width=course.width,
        top=course.top,
        bottom=course.bottom,
        pieces=course.pieces,
        spinners=course.spinners,
        checkpoints=tuple(
            Checkpoint(
                index=node.index,
                name=node.name,
                y=node.y,
                respawn=peg.center if node.index == 0 else node.respawn,
                branch=node.branch,
                x_min=node.x_min,
                x_max=node.x_max,
                progress=node.progress,
            )
            for node in course.checkpoints
        ),
        spawns=course.spawns,
        sections=course.sections,
    )
    kinds = {finding.kind for finding in audit_course(broken)}
    assert "respawn blocked" in kinds


def test_the_audit_finds_a_balance_point_under_a_starting_slot() -> None:
    """The prototype has one; the machine course must not.

    A racer in free fall has no sideways velocity, so a peg apex on a
    starting slot's fall line is somewhere it can come to rest exactly on
    top of. It cost the first machine course two racers a race.
    """
    machine = audit_course(build_course(MACHINE_COURSE_ID, 1000))
    assert not [f for f in machine if f.kind == "balance point"]


def test_a_finding_prints_where_it_is() -> None:
    text = str(Finding("error", "pinch trap", "too narrow", 100.0, 200.0))
    assert "ERROR" in text and "pinch trap" in text and "(100, 200)" in text


# --- the machine course -----------------------------------------------------


def test_the_machine_course_is_registered_and_builds() -> None:
    from race.courses import COURSE_NAMES

    assert MACHINE_COURSE_ID in COURSE_NAMES
    course = build_course(MACHINE_COURSE_ID, 7)
    assert len(course.checkpoints) >= 8
    assert len(course.spawns) == 20


def test_the_machine_course_is_the_same_course_for_every_seed() -> None:
    """Only the rotors vary. Geometry that moved could not be measured."""
    first = build_course(MACHINE_COURSE_ID, 1)
    second = build_course(MACHINE_COURSE_ID, 999)
    assert [piece.spec for piece in first.pieces] == [
        piece.spec for piece in second.pieces
    ]
    assert [spec.spinner_id for spec in first.spinners] == [
        spec.spinner_id for spec in second.spinners
    ]
    assert first.spinners[0].start_angle != second.spinners[0].start_angle


def test_the_course_is_not_a_corridor_of_sprints() -> None:
    """The V0.4 design rule, as an assertion.

    A course whose sections are all SPRINT is the course V0.3 shipped: every
    obstacle preserves order, an early advantage compounds through all of
    them, and the winner is settled by halfway. So the classification is
    stated in the course file and checked here - at least three of the
    reshuffling categories have to be present, and no more than a quarter of
    the named sections may be pure sprints.
    """
    course = build_course(MACHINE_COURSE_ID, 1000)
    named = [section.name for section in course.sections if section.name in SECTION_ROLES]
    roles = [role for name in named for role in SECTION_ROLES[name]]
    assert roles.count("MIX") >= 2
    assert roles.count("COMPRESS") >= 2
    assert "CHOICE" in roles and "RISK" in roles and "SPREAD" in roles
    sprints = [name for name in named if SECTION_ROLES[name] == ("SPRINT",)]
    assert len(sprints) * 4 <= len(named)


def test_every_section_of_the_course_is_classified() -> None:
    course = build_course(MACHINE_COURSE_ID, 1000)
    for section in course.sections:
        assert section.name in SECTION_ROLES, section.name


def test_the_opening_puts_no_peg_under_a_starting_column() -> None:
    """The single rule the opening exists to obey.

    Stated as geometry rather than as an outcome, because the outcome - two
    racers a race stuck on an apex and then retired - only shows up after a
    few hundred races.
    """
    from race.courses.machine import GRID_COLUMNS, SPREAD_LATTICE

    for column in GRID_COLUMNS:
        for peg in SPREAD_LATTICE:
            assert abs(peg - column) >= 45.0


def test_a_traced_machine_race_finishes_and_is_decided(traced) -> None:
    manager, trace = traced
    assert manager.winner is not None
    assert not manager.timed_out
    assert trace.winner_time is not None
    assert 10.0 < trace.winner_time < 26.0

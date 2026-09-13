"""The chase camera: the arithmetic, the filters, and the track that comes out.

One race, shared, for the same reason `test_sloped_cameras` shares one: what is
under test is the solve over the frames rather than the physics. It runs long
enough to reach the finish window V21's edit names, because the bookends are
solved by `cameras.build_track` against that edit and a replay that stops short
of it exercises a different path - the one `_bookends` drops a window on.

That path gets its own test with a twelve-second race, which is quick and which
is the case that first broke this module.
"""

from __future__ import annotations

import math

import pytest

from sloped import cameras as cameras_module
from sloped import chase_camera
from sloped.chase_camera import (
    MAX_LENS_STEP,
    MAX_LOOK_YAW,
    MAX_PHASE_STEP,
    MAX_YAW_RATE,
    PHASES,
    TARGETS,
    ChasePhase,
    build_chase,
    chase_report,
    check_chase,
    course_at,
    pack_anchor,
    route_offsets,
)
from sloped.course import sloped_course
from sloped.race import ROUTE_RUNS, run_race
from sloped.scale import SIM_TO_LAYOUT


@pytest.fixture(scope="module")
def machine():
    return sloped_course(routes="both")


@pytest.fixture(scope="module")
def replay(machine):
    _outcome, document = run_race(
        seed=31, machine=machine, marble_count=8, duration=26.0, with_replay=True
    )
    return document.to_json()


@pytest.fixture(scope="module")
def short_replay(machine):
    _outcome, document = run_race(
        seed=31, machine=machine, marble_count=8, duration=12.0, with_replay=True
    )
    return document.to_json()


@pytest.fixture(scope="module")
def track(replay, machine):
    return build_chase(replay, machine, fps=60)


# --- the course, as arc length ---------------------------------------------


def test_course_at_agrees_with_the_production_projection(machine):
    """The claim `course_at`'s docstring makes, pinned.

    `cameras._on_course` is what every production aim is built on. A chase that
    projected onto the course even slightly differently would be comparing its
    own framing against a baseline drawn on a different line, so the two are
    held to agreeing exactly wherever both are defined.
    """
    offsets, _totals = route_offsets(machine)
    for route in offsets:
        total = sum(machine.runs[name].sim_arc[-1] for name in ROUTE_RUNS[route])
        for step in range(1, 40):
            along = total * step / 40.0
            mine, _tangent = course_at(machine, offsets, route, along)
            theirs = cameras_module._on_course(machine, offsets, route, along)
            assert mine == pytest.approx(theirs, abs=1e-9), (route, along)


def test_course_at_extrapolates_before_the_start_rather_than_clamping(machine):
    """A camera thirty units behind a field on the launch is before the course."""
    offsets, _totals = route_offsets(machine)
    first, tangent = course_at(machine, offsets, "blue", 0.0)
    back, _ = course_at(machine, offsets, "blue", -20.0)
    assert math.dist(first, back) == pytest.approx(20.0 * SIM_TO_LAYOUT, rel=1e-6)
    # And it is behind, not merely elsewhere: the offset runs against the tangent.
    step = [back[axis] - first[axis] for axis in range(3)]
    assert sum(step[axis] * tangent[axis] for axis in range(3)) < 0.0


def test_course_at_extrapolates_past_the_line(machine):
    offsets, totals = route_offsets(machine)
    end, _tangent = course_at(machine, offsets, "blue", totals["blue"])
    beyond, _ = course_at(machine, offsets, "blue", totals["blue"] + 15.0)
    assert math.dist(end, beyond) == pytest.approx(15.0 * SIM_TO_LAYOUT, rel=1e-6)


def test_every_route_the_machine_carries_is_offered(machine):
    offsets, totals = route_offsets(machine)
    assert set(offsets) == {"blue", "orange"}
    for route in offsets:
        assert totals[route] > 0.0
        assert offsets[route][ROUTE_RUNS[route][0]] == 0.0


# --- targeting --------------------------------------------------------------


def test_leader_follows_one_marble_and_the_others_do_not():
    values = {0: 100.0, 1: 90.0, 2: 88.0, 3: 20.0}
    assert pack_anchor(values, "leader") == [0]
    for rule in ("centroid", "median"):
        assert sorted(pack_anchor(values, rule)) == [0, 1, 2, 3]


def test_trimmed_drops_a_detached_outlier_and_keeps_a_close_one():
    """The rule the brief asks for: exclude the extreme, not the merely behind."""
    detached = {0: 100.0, 1: 96.0, 2: 94.0, 3: 10.0}
    assert 3 not in pack_anchor(detached, "trimmed")
    together = {0: 100.0, 1: 96.0, 2: 94.0, 3: 88.0}
    assert sorted(pack_anchor(together, "trimmed")) == [0, 1, 2, 3]


def test_trimmed_never_drops_the_field_down_to_the_leader():
    """`MAX_TRIMMED` is what stops a trimmed mean becoming `leader` at the fork."""
    strung_out = {index: 100.0 - 40.0 * index for index in range(8)}
    kept = pack_anchor(strung_out, "trimmed")
    assert len(kept) >= len(strung_out) - chase_camera.MAX_TRIMMED


def test_adaptive_leans_to_the_front_when_the_field_is_tight():
    tight = {0: 100.0, 1: 99.0, 2: 98.0, 3: 97.0}
    spread = {0: 100.0, 1: 80.0, 2: 60.0, 3: 40.0}
    assert sorted(pack_anchor(tight, "adaptive")) == [0, 1, 2, 3]
    # Strung out, the adaptive centre is the median's, so the detached front
    # and back are both outside the band rather than dragging it.
    assert 0 not in pack_anchor(spread, "adaptive")


def test_an_unknown_rule_is_an_error_rather_than_a_default():
    with pytest.raises(KeyError):
        pack_anchor({0: 1.0}, "whatever")


def test_no_rule_returns_an_empty_set_for_a_live_field():
    values = {index: float(index) for index in range(8)}
    for rule in TARGETS:
        assert pack_anchor(values, rule), rule


# --- the filters ------------------------------------------------------------


def test_the_slew_limit_caps_the_turn_and_keeps_unit_length():
    """A tangent that reverses in one frame - the hairpin, in the worst case."""
    vectors = [(0.0, 0.0, 1.0)] * 3 + [(0.0, 0.0, -1.0)] * 30
    limited = chase_camera._slew(vectors, MAX_YAW_RATE)
    for vector in limited:
        assert math.sqrt(sum(v * v for v in vector)) == pytest.approx(1.0, abs=1e-9)
    for before, after in zip(limited, limited[1:]):
        cosine = sum(before[axis] * after[axis] for axis in range(3))
        angle = math.degrees(math.acos(min(max(cosine, -1.0), 1.0)))
        assert angle <= MAX_YAW_RATE + 1e-6


def test_the_slew_limit_is_the_identity_on_a_slow_turn():
    vectors = []
    for step in range(40):
        angle = math.radians(step * 0.2)
        vectors.append((math.sin(angle), 0.0, math.cos(angle)))
    limited = chase_camera._slew(vectors, MAX_YAW_RATE)
    for wanted, got in zip(vectors, limited):
        assert got == pytest.approx(wanted, abs=1e-9)


def test_the_follower_caps_a_jump_and_leaves_a_slow_path_alone():
    jump = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0)]
    assert chase_camera._follow(jump, 0.85)[1][0] == pytest.approx(0.85)
    crawl = [(value * 0.1, 0.0, 0.0) for value in range(20)]
    assert chase_camera._follow(crawl, 0.85) == [tuple(row) for row in crawl]


# --- the track --------------------------------------------------------------


def test_the_track_is_the_document_the_renderer_already_reads(track):
    """A new camera language must not need a new renderer to look at it."""
    assert track["units"] == "layout"
    assert track["fps"] == 60
    for cut in track["cuts"]:
        assert {"name", "from", "to", "fov", "frames"} <= set(cut)
        for row in cut["frames"]:
            assert len(row) == 8


def test_the_chase_phases_are_one_continuous_path(track):
    """The whole claim of the prototype, as a number.

    A boundary between two chase phases is not a cut: the last row of one and
    the first row of the next are adjacent samples of one solve. V21's
    equivalent boundaries move the lens 30 to 50 layout units.
    """
    chase_cuts = [cut for cut in track["cuts"] if cut.get("chase")]
    assert len(chase_cuts) >= 2
    for before, after in zip(chase_cuts, chase_cuts[1:]):
        moved = math.dist(before["frames"][-1][1:4], after["frames"][0][1:4])
        assert moved <= MAX_PHASE_STEP, f"{before['name']} -> {after['name']}: {moved}"


def test_the_lens_never_jumps_inside_a_phase(track):
    for cut in track["cuts"]:
        if not cut.get("chase"):
            continue
        for a, b in zip(cut["frames"], cut["frames"][1:]):
            moved = math.dist(a[1:4], b[1:4])
            assert moved <= MAX_LENS_STEP + 1e-6, (cut["name"], b[0], moved)


def test_the_camera_is_above_its_aim_in_every_frame(track):
    for cut in track["cuts"]:
        for row in cut["frames"]:
            assert row[2] > row[5], (cut["name"], row[0])


def test_the_aim_stays_inside_its_own_yaw_budget(track):
    """The look-ahead is an angle, and this is the angle."""
    for cut in track["cuts"]:
        if not cut.get("chase"):
            continue
        for row in cut["frames"][::5]:
            lens = row[1:4]
            aim = row[4:7]
            reach = math.dist(lens, aim)
            assert reach > 1.0, (cut["name"], row[0])
    # and the solved look-ahead never exceeds the phase's own maximum
    wanted = {phase.name: phase.look for phase in PHASES}
    for cut in track["cuts"]:
        if cut.get("chase"):
            assert cut["look"] <= wanted[cut["name"]] + 1e-9


def test_the_edit_map_runs_at_slope_one(track):
    """Section 40: a camera may omit replay time and may not alter its rate."""
    for segment in track["edit"]:
        out_span = segment["out"][1] - segment["out"][0]
        replay_span = segment["replay"][1] - segment["replay"][0]
        assert out_span == pytest.approx(replay_span, abs=1e-6), segment["cut"]
    for before, after in zip(track["edit"], track["edit"][1:]):
        assert after["out"][0] == pytest.approx(before["out"][1], abs=1e-6)


def test_no_chase_phase_has_a_finding(track, replay):
    """Every finding this track can have, and none of them about a chase phase.

    The bookends are V21's lenses solved by `sloped.cameras`, and on a proof
    seed that is not the production one they can legitimately complain - the
    finish lens holds one racer because this race's field has not arrived. That
    is V21's business. What this module is answerable for is the phases it
    solves itself.
    """
    names = {cut["name"] for cut in track["cuts"] if cut.get("chase")}
    mine = [f for f in check_chase(track, replay) if f.split(":")[0] in names]
    assert mine == [], "\n".join(mine)


def test_the_solve_is_deterministic(replay, machine):
    once = build_chase(replay, machine, fps=60)
    twice = build_chase(replay, machine, fps=60)
    assert once == twice


def test_every_targeting_rule_solves(replay, machine):
    for rule in TARGETS:
        solved = build_chase(replay, machine, fps=60, rule=rule)
        assert solved["rule"] == rule
        assert solved["cuts"]


def test_a_replay_too_short_for_the_finish_window_still_solves(short_replay, machine):
    """The bookends are the production edit's times; a short replay has neither.

    `cameras.build_track` raises "the edit kept nothing" when an edit names a
    window the replay does not reach, which is right for a film and wrong for a
    solver. The chase drops the window it cannot carry and covers the span
    itself.
    """
    solved = build_chase(short_replay, machine, fps=60)
    assert [cut["name"] for cut in solved["cuts"] if not cut.get("chase")] == ["start", "start"]
    chase_cuts = [cut for cut in solved["cuts"] if cut.get("chase")]
    assert chase_cuts
    # and no phase the replay had no room for survives as a flash frame
    for cut in chase_cuts:
        assert cut["to"] - cut["from"] >= chase_camera.MIN_PHASE_SECONDS - 1e-6, cut["name"]


def test_an_unknown_rule_is_refused(replay, machine):
    with pytest.raises(KeyError):
        build_chase(replay, machine, fps=60, rule="nope")


# --- the checks -------------------------------------------------------------


def test_the_drift_check_is_retired_for_chase_cuts_and_kept_for_the_others(
    track, replay
):
    """Retiring a check is only honest if the property is re-asserted.

    `cameras.check_track` forbids an aim more than `MAX_AIM_DRIFT` from the
    nearest racer, which is a statement about a camera whose aim is the field.
    A chase aims downstream on purpose. So the finding is dropped for chase
    cuts - and only for chase cuts - and replaced by a budget the look-ahead
    itself sets.
    """
    names = {cut["name"] for cut in track["cuts"] if cut.get("chase")}
    for finding in check_chase(track, replay):
        if "is not following the field" in finding:
            assert finding.split(":")[0] not in names, finding


def test_a_chase_that_aims_off_the_course_is_still_caught(track, replay):
    """The replacement check has to be able to fail, or it is not a check."""
    broken = {
        **track,
        "cuts": [
            {
                **cut,
                "frames": [
                    [row[0], *row[1:4], row[4] + 400.0, *row[5:]] for row in cut["frames"]
                ],
            }
            if cut.get("chase")
            else cut
            for cut in track["cuts"]
        ],
    }
    findings = check_chase(broken, replay)
    assert any("its look-ahead allows" in finding for finding in findings), findings


def test_the_turn_rate_check_can_fail(track, replay):
    """A whipped view, built by hand, has to be reported."""
    cut = next(cut for cut in track["cuts"] if cut.get("chase"))
    whipped = {
        **track,
        "cuts": [
            {
                **cut,
                "frames": [
                    [
                        row[0], *row[1:4],
                        row[1] + math.cos(index * 0.5) * 30.0,
                        row[5],
                        row[3] + math.sin(index * 0.5) * 30.0,
                        row[7],
                    ]
                    for index, row in enumerate(cut["frames"])
                ],
            }
        ],
    }
    assert any("whip rather than a chase" in f for f in check_chase(whipped, replay))


# --- the reports ------------------------------------------------------------


def test_the_chase_report_measures_the_course_ahead(track, replay, machine):
    rows = chase_report(track, replay, machine, stride=30)
    assert rows
    for row in rows:
        assert 0.0 <= row["ahead_share"] <= 1.0
        assert row["ahead_units"] >= 0.0
        assert row["turn_max"] >= row["turn_median"] >= 0.0


def test_a_chase_phase_shows_more_of_the_course_ahead_than_it_does_behind(
    track, replay, machine
):
    """The brief's first principle, as a measurement rather than a claim."""
    rows = {row["cut"]: row for row in chase_report(track, replay, machine, stride=30)}
    descent = rows.get("descent")
    assert descent is not None
    assert descent["ahead_share"] > 0.25, descent
    assert descent["ahead_units"] > 10.0, descent


# --- the phase table --------------------------------------------------------


def test_every_phase_names_a_station_the_table_carries():
    for phase in PHASES[:-1]:
        assert phase.until in cameras_module.STATIONS, phase.name
    assert PHASES[-1].until == "", "the last phase runs to the finish lens"


def test_the_phase_set_points_are_sane():
    for phase in PHASES:
        assert phase.trail > 0.0
        assert phase.rise > 0.0
        assert phase.look >= 0.0
        assert phase.spread >= 0.0
        assert 10.0 < phase.fov < 90.0
        assert phase.ramp > 0.0


def test_a_custom_phase_table_is_honoured(replay, machine):
    phases = (ChasePhase("only", "", trail=20.0, rise=10.0, look=10.0),)
    solved = build_chase(replay, machine, fps=60, phases=phases)
    chase_cuts = [cut for cut in solved["cuts"] if cut.get("chase")]
    assert [cut["name"] for cut in chase_cuts] == ["only"]


def test_the_look_yaw_budget_fits_the_delivery_frame():
    """`MAX_LOOK_YAW` is read off the frame, so the frame has to agree."""
    horizontal = math.degrees(
        math.atan(math.tan(math.radians(PHASES[0].fov) * 0.5) * 1080.0 / 1920.0)
    )
    assert MAX_LOOK_YAW < horizontal, (MAX_LOOK_YAW, horizontal)

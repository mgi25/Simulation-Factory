"""What the V22.1 start plans must be true of, whatever the camera looks like.

These are the claims the prototype makes about *time*: that its windows are real
replay frames, that output time never runs backwards or twice over the same
frame, that the race under them is still seed 5432's, and that a plan which says
it keeps the rotor turning through the join actually does - checked against the
replay's own recorded actuator poses rather than against `shuffle.Rotor`'s law.

The replay is generated output and not in the branch, so every test that needs it
skips rather than fails when it is absent. The arithmetic tests do not need it.
"""

from __future__ import annotations

import json
import math
import os

import pytest

from sloped import cameras, v221_shuffle as v221

REPLAY = os.path.join("output", "sloped_race_v1", "race_5432.json")
SEED = 5432
FINISH_ORDER = [5, 2, 7, 4, 1, 6, 3, 0]
DIGEST = "aafb0d3d872e6c5f6db3a6f52d567ae073f1888fbac4ea4970867c130cf17de6"


@pytest.fixture(scope="module")
def replay():
    if not os.path.isfile(REPLAY):
        pytest.skip(f"{REPLAY} is generated output and is not in the branch")
    with open(REPLAY, "r", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def machine():
    from sloped.course import sloped_course

    return sloped_course(routes="both")


@pytest.fixture(scope="module")
def tracks(replay, machine):
    return {name: v221.build_start_track(replay, machine, plan)
            for name, plan in v221.PLANS.items()}


# --- the race is still the race --------------------------------------------


def test_the_race_is_seed_5432_and_this_pass_did_not_touch_it(replay):
    """Nothing in V22.1 re-simulates, so the identity has to be unchanged.

    The order is taken from the `finish_line` events rather than from
    `summary.finish_order`, which this replay carries empty - the crossings are
    the record, and they are what `cameras.EDIT_V22`'s finish window was
    extended to 24.467 to hold.
    """
    assert replay["seed"] == SEED
    assert replay["digest"] == DIGEST
    crossings = [event for event in replay["events"]
                 if event["kind"] == "finish_line"]
    assert [event["id"] for event in crossings] == FINISH_ORDER
    assert crossings == sorted(crossings, key=lambda event: event["t"])
    assert replay["summary"]["failure"] in (None, "", False)


def test_the_start_timeline_is_the_one_the_plans_were_cut_against(machine):
    """`ShuffleFloor`'s beats, which every window edge here is placed against.

    If any of these move, the plans in `PLANS` are cut against a machine that no
    longer exists and the phase lock is arithmetic about the wrong rotor.
    """
    beats = v221.rotor_timeline(machine)
    assert beats["release"] == pytest.approx(0.30)
    assert beats["rotor_start"] == pytest.approx(1.60)
    assert beats["rotor_stop"] == pytest.approx(4.60)
    assert beats["settled"] == pytest.approx(4.90)
    assert beats["lift_at"] == pytest.approx(5.20)
    assert beats["gate"] == pytest.approx(6.10)
    assert beats["rate"] == pytest.approx(13.0)


# --- the mapping from output time to replay time ---------------------------


def test_every_window_edge_is_a_real_replay_frame():
    """An omission boundary that is not a frame is not an honest boundary."""
    for name, plan in v221.PLANS.items():
        for edge in (plan.cut_at, plan.resume_at):
            if edge is None:
                continue
            assert v221.snap(edge) == pytest.approx(edge, abs=1e-6), (
                f"{name}: {edge} is not a frame at {v221.FPS} fps")


def test_replay_time_runs_forward_and_never_repeats_a_frame(tracks):
    """Monotonic, strictly increasing, with no frame shown twice.

    Two things a cut can get wrong that no amount of watching makes obvious: a
    window that reaches back behind the one before it, and a boundary frame that
    appears in both windows and so plays twice.
    """
    for name, track in tracks.items():
        seen: list[float] = []
        for cut in track["cuts"]:
            for row in cut["frames"]:
                seen.append(round(float(row[0]), 6))
        assert seen == sorted(seen), f"{name}: replay time runs backwards"
        assert len(seen) == len(set(seen)), f"{name}: a replay frame is shown twice"
        for a, b in zip(seen, seen[1:]):
            assert b > a, f"{name}: two output frames hold the same replay frame"


def test_output_time_runs_at_slope_one_through_every_window(tracks):
    """One second of screen is one second of replay, inside a window.

    The whole claim of an honest omission is that nothing is retimed: the only
    thing an edit does is leave frames out between windows.
    """
    for name, track in tracks.items():
        for cut in track["cuts"]:
            rows = cut["frames"]
            for a, b in zip(rows, rows[1:]):
                assert float(b[0]) - float(a[0]) == pytest.approx(1.0 / v221.FPS,
                                                                  abs=1e-6), name


def test_the_omission_is_where_the_plan_says_it_is(tracks):
    """Exactly one gap, at the named boundaries, of the named length."""
    for name, plan in v221.PLANS.items():
        cuts = tracks[name]["cuts"]
        if not plan.omits:
            assert len(cuts) == 1, f"{name} omits nothing and should be one window"
            continue
        assert len(cuts) == 2, name
        assert float(cuts[0]["frames"][-1][0]) == pytest.approx(plan.cut_at, abs=1e-6)
        assert float(cuts[1]["frames"][0][0]) == pytest.approx(plan.resume_at, abs=1e-6)
        gap = float(cuts[1]["frames"][0][0]) - float(cuts[0]["frames"][-1][0])
        assert round(gap * v221.FPS) - 1 == plan.omitted_frames(), name


def test_the_shot_starts_and_ends_where_the_film_needs_it_to(tracks):
    """0.200 in, 7.620 out - the preview's handoff and the chase's takeover.

    Every plan changes what happens between those two, and none of them may
    change the two themselves, or the prototype is not droppable into the film.
    """
    for name, track in tracks.items():
        assert float(track["cuts"][0]["from"]) == pytest.approx(0.20), name
        assert float(track["cuts"][-1]["to"]) == pytest.approx(7.62), name


# --- the phase lock ---------------------------------------------------------


def test_a_whole_revolution_is_29_frames_at_60fps():
    """The arithmetic the B plans stand on, and its residual."""
    gaps = {int(row["turns"]): row for row in v221.locked_gaps(13.0, 60, 5)}
    assert gaps[1]["frames"] == 29
    assert gaps[4]["frames"] == 116
    assert gaps[5]["frames"] == 145
    for row in gaps.values():
        assert abs(row["error_deg"]) < 0.05, row


def test_every_b_plan_omits_whole_revolutions_from_inside_the_spin():
    """The two conditions that make the lock work, as a property of the plan.

    A whole number of revolutions is not enough on its own: the omission also has
    to lie between `rotor_start` and `rotor_stop`, because outside that span the
    rate is not constant and a revolution is not a revolution.
    """
    per = v221.revolution_frames(13.0, v221.FPS)
    for name, plan in v221.PLANS.items():
        if not name.startswith("b"):
            continue
        turns = plan.omitted_frames() / per
        assert turns == pytest.approx(round(turns), abs=0.01), f"{name}: {turns} turns"
        assert plan.cut_at >= 1.60, f"{name} cuts before the rotor starts"
        assert plan.resume_at <= 4.60 + 1e-9, f"{name} resumes after the rotor stops"


def test_the_blades_really_are_where_they_were(replay, machine, tracks):
    """Measured off the recorded poses, not off the law.

    A join advances a blade by one frame's worth of rotation and no more, and the
    paddle assembly is at the same height on both sides. This is the claim the
    whole B family is for, and it is checked against the file the renderer reads.
    """
    for name, plan in v221.PLANS.items():
        if not name.startswith("b"):
            continue
        report = v221.join_report(tracks[name], replay, plan, machine)
        assert abs(report["rotor"]["phase_error_deg"]) < 0.05, name
        assert report["rotor"]["lift_change"] == pytest.approx(0.0, abs=1e-6), name
        assert report["rotor"]["inside_constant_rate"], name


def test_the_control_still_has_the_fault_this_pass_is_about(replay, machine, tracks):
    """V22's join, measured. If this stops failing, V22.1 has no subject.

    Not an assertion that V22 is bad - it is the baseline the B plans are read
    against, and a regression here would mean the control has been edited.
    """
    report = v221.join_report(tracks["v22"], replay, v221.PLANS["v22"], machine)
    assert abs(report["rotor"]["phase_error_deg"]) > 10.0
    assert report["rotor"]["lift_change"] == pytest.approx(1.193, abs=1e-3)
    assert not report["rotor"]["inside_constant_rate"]
    assert report["camera_step_join"] == pytest.approx(5.3741, abs=1e-3)
    assert report["marbles"]["max_sim"] == pytest.approx(2.322, abs=1e-3)


def test_the_control_reproduces_the_delivered_v22_track(replay, machine, tracks):
    """Row for row, if the delivered track is beside this tree.

    The control is only a control if it is the film's own opening, so when the
    delivered track is available it is compared rather than trusted.
    """
    delivered = os.path.join("output", "sloped_race_v1", "cameras_v22_5432.json")
    if not os.path.isfile(delivered):
        pytest.skip("the delivered V22 track is not in this tree")
    with open(delivered, "r", encoding="utf-8") as handle:
        reference = json.load(handle)
    mine = tracks["v22"]["cuts"]
    theirs = [cut for cut in reference["cuts"] if cut["name"] == "start"]
    assert len(mine) == len(theirs)
    for one, two in zip(mine, theirs):
        assert len(one["frames"]) == len(two["frames"])
        for row, other in zip(one["frames"], two["frames"]):
            assert row == pytest.approx(other, abs=1e-4)


# --- the camera -------------------------------------------------------------


def test_a_continuity_plan_does_not_move_the_lens_at_the_join(replay, machine, tracks):
    """Position *and* velocity, which is what `constant_rate_legs` is for."""
    for name, plan in v221.PLANS.items():
        if not name.startswith("b") or name.endswith("jumpcam"):
            continue
        report = v221.join_report(tracks[name], replay, plan, machine)
        assert report["camera_step_join"] == pytest.approx(0.0, abs=1e-3), name
        assert report["camera_reach_change"] == pytest.approx(0.0, abs=1e-3), name
        assert report["aim_step_join"] == pytest.approx(0.0, abs=1e-3), name


def test_constant_rate_legs_meet_and_share_a_rate():
    """The two properties, as arithmetic, independent of any track."""
    legs = v221.constant_rate_legs((1.85, 3.62), (-36.0, 4.0))
    assert legs[0][1] == pytest.approx(legs[1][0])
    assert legs[0][0] == pytest.approx(-36.0)
    assert legs[-1][1] == pytest.approx(4.0)
    first = (legs[0][1] - legs[0][0]) / 1.85
    second = (legs[1][1] - legs[1][0]) / 3.62
    # The legs are rounded to six decimals on the way out, which is a tenth of
    # a thousandth of a degree of bearing - below anything a lens can show.
    assert first == pytest.approx(second, abs=1e-5)


def test_the_move_ends_on_the_pose_v212_proved_for_the_launch():
    """Whatever the plan does in the middle, it arrives at the proven framing."""
    for name, plan in v221.PLANS.items():
        orbit, dolly = v221.plan_legs(plan)
        assert orbit[-1][1] == pytest.approx(4.0), name
        assert dolly[-1][1] == pytest.approx(-0.06), name
        assert orbit[0][0] == pytest.approx(-36.0), name


def test_no_plan_makes_a_track_cameras_itself_objects_to(replay, tracks):
    """`cameras.check_track` is production's own reading of a camera track."""
    for name, track in tracks.items():
        assert cameras.check_track(track, replay) == [], name


# --- the trapdoor -----------------------------------------------------------


def test_the_trapdoor_is_live_in_every_plan(tracks, machine):
    """6.100 is the drop. A plan that omits it is not a start."""
    gate = v221.rotor_timeline(machine)["gate"]
    for name, plan in v221.PLANS.items():
        shown = [(low, high) for low, high in v221._live_spans(plan)
                 if low <= gate <= high]
        assert shown, f"{name} does not show the trapdoor opening"


def test_a_b_plan_keeps_the_whole_wind_down_and_lift(machine):
    """The anticipation beats, which is what the B family buys with its placement."""
    beats = v221.rotor_timeline(machine)
    for name, plan in v221.PLANS.items():
        if not name.startswith("b"):
            continue
        hold = v221._anticipation(plan, beats)
        assert hold["spin_down"] == pytest.approx(0.30, abs=1e-3), name
        assert hold["to_gate"] == pytest.approx(1.50, abs=1e-3), name

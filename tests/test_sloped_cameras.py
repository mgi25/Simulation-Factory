"""The camera track, and the contact check on the replay it is cut from.

Both work on one race, so they share it. The race is short - twelve seconds,
which is most of the way down the course - because what is being tested is the
arithmetic over the frames rather than the finish.
"""

from __future__ import annotations

import math

import pytest

from marble3d.units import MARBLE_DIAMETER, MARBLE_RADIUS
from sloped import cameras as cameras_module
from sloped.cameras import SECTIONS, STATIONS, build_track, check_track, progress_track
from sloped.contact import FLOAT_BUDGET, PENETRATION_BUDGET, check_replay
from sloped.course import sloped_course
from sloped.race import ROUTE_RUNS, run_race


@pytest.fixture(scope="module")
def machine():
    return sloped_course()


@pytest.fixture(scope="module")
def replay(machine):
    _outcome, document = run_race(
        seed=31, machine=machine, marble_count=8, duration=12.0, with_replay=True
    )
    return document.to_json()


@pytest.fixture(scope="module")
def track(replay, machine):
    return build_track(replay, machine, fps=60)


# --- progress -------------------------------------------------------------


def test_progress_is_monotonic_for_every_marble(replay, machine):
    """A marble that runs back up the merge apron has not un-raced the course."""
    measured = progress_track(replay, machine)
    for marble in measured["marbles"]:
        series = measured["progress"][marble]
        assert len(series) == len(replay["frames"])
        for earlier, later in zip(series, series[1:]):
            assert later >= earlier - 1e-9, marble


def test_progress_ends_further_than_it_starts(replay, machine):
    measured = progress_track(replay, machine)
    for marble in measured["marbles"]:
        series = measured["progress"][marble]
        assert series[-1] > series[0] + 20.0, marble


def test_every_station_names_a_run_the_course_carries(machine):
    for station, (run_name, fraction) in STATIONS.items():
        assert 0.0 <= fraction <= 1.0, station
        assert run_name in ROUTE_RUNS["blue"] or run_name in ROUTE_RUNS["orange"], station


# --- the track ------------------------------------------------------------


def test_the_track_has_no_findings(track):
    problems = check_track(track)
    assert problems == [], "\n".join(problems)


def test_the_cuts_tile_the_clip_without_a_gap_or_an_overlap(track):
    cuts = track["cuts"]
    # Not every section survives every replay. This race is twelve seconds and
    # the field is only most of the way down, so the cuts whose stations are
    # never reached have no time left and are dropped rather than emitted with
    # zero - or, before the bounds were clamped, with a negative - duration.
    # What has to hold is that the ones that are kept are a prefix of the
    # sequence and tile the replay without a seam.
    assert 0 < len(cuts) <= len(SECTIONS)
    assert [cut["name"] for cut in cuts] == [
        section.name for section in SECTIONS[: len(cuts)]
    ]
    assert cuts[0]["from"] == pytest.approx(0.0)
    for earlier, later in zip(cuts, cuts[1:]):
        assert later["from"] == pytest.approx(earlier["to"])
    assert cuts[-1]["to"] == pytest.approx(track["duration"])


def test_the_establishing_shot_is_capped(track):
    establish = track["cuts"][0]
    assert establish["name"] == "establish"
    span = establish["to"] - establish["from"]
    assert 0.5 <= span <= 1.0, span


def test_no_cut_is_shorter_than_its_own_floor(track):
    for cut, section in zip(track["cuts"], SECTIONS):
        span = cut["to"] - cut["from"]
        # The floor is a floor on what the *course* is allowed to give a
        # cut, not a promise the replay can keep: the last cut a short replay
        # has room for is clamped to its final frame and can come out under its
        # own minimum. Any earlier cut coming out short would be the station
        # logic going wrong.
        ran_out = abs(cut["to"] - track["duration"]) < 1e-6
        assert span >= section.min_seconds - 1e-6 or ran_out, (cut["name"], span)


def test_every_frame_carries_a_position_an_aim_and_a_field_of_view(track):
    for cut in track["cuts"]:
        assert cut["frames"], cut["name"]
        for entry in cut["frames"]:
            assert len(entry) == 8
            assert cut["from"] - 1e-6 <= entry[0] <= cut["to"] + 1e-6
            assert entry[7] == pytest.approx(cut["fov"])


def test_the_camera_is_always_above_and_away_from_its_subject(track):
    for cut in track["cuts"]:
        for entry in cut["frames"]:
            position = entry[1:4]
            aim = entry[4:7]
            assert position[1] > aim[1], (cut["name"], entry[0])
            assert math.dist(position, aim) > 2.0, (cut["name"], entry[0])


def test_the_aim_follows_rather_than_snaps(track):
    """A membership change in the pack band moves the centroid; smoothing hides it."""
    for cut in track["cuts"]:
        worst = 0.0
        for a, b in zip(cut["frames"], cut["frames"][1:]):
            worst = max(worst, math.dist(a[4:7], b[4:7]))
        assert worst < 2.0 * 0.285, (cut["name"], worst)


def test_the_track_is_in_layout_units_and_says_so(track, replay):
    assert track["units"] == "layout"
    assert track["seed"] == replay["seed"]
    # A marble's aim point is in layout units, so it is inside the course's own
    # authored bounds rather than the simulation's 1.75x-larger ones.
    for cut in track["cuts"]:
        for entry in cut["frames"]:
            assert -90.0 < entry[4] < 90.0
            assert -5.0 < entry[5] < 60.0
            assert -100.0 < entry[6] < 120.0


def test_the_clip_ends_after_the_last_crossing_and_not_at_the_replays_end(replay, machine):
    """The physics keeps running while the field rolls out onto the deck."""
    crossings = [
        float(event["t"]) for event in replay["events"] if event["kind"] == "finish_line"
    ]
    built = build_track(replay, machine, fps=60)
    assert built["replay_duration"] == pytest.approx(float(replay["frames"][-1]["t"]))
    if crossings:
        assert built["last_crossing"] == pytest.approx(max(crossings))
        assert built["duration"] <= built["replay_duration"] + 1e-6


def test_a_node_targeted_cut_does_not_move_its_aim(track):
    for cut in track["cuts"]:
        if cut["target"] != "node":
            continue
        aims = [entry[4:7] for entry in cut["frames"]]
        spread = max(math.dist(aims[0], aim) for aim in aims)
        assert spread < 1e-6, cut["name"]


# --- the contact check ----------------------------------------------------


def test_the_replay_agrees_with_the_channel_it_will_be_drawn_on(replay, machine):
    report = check_replay(replay, machine, stride=3)
    assert report.frames > 50
    assert report.channel_samples > 500
    assert report.findings == [], report.by_kind()
    assert report.worst_penetration > -PENETRATION_BUDGET
    assert report.worst_float < FLOAT_BUDGET


def test_the_contact_check_notices_a_floated_marble(replay, machine):
    """Lift one resting marble a diameter and the check has to say so.

    A test of the test: a contact checker that passes everything is a checker
    that would have passed the version of this course whose merge apron sat
    three quarters of a diameter above the channel it was joined to.
    """
    import copy

    doctored = copy.deepcopy(replay)
    lifted = 0
    for frame in doctored["frames"]:
        for sample in frame["marbles"]:
            if sample["s"] == "running" and math.hypot(*sample["v"]) < 1.0:
                # Half a diameter, not two. `check_replay` stops measuring a
                # marble more than `OFF_CHANNEL` - two diameters - from the
                # centreline, on the grounds that it is on a station rather
                # than in a channel; lifting by two put the doctored marbles
                # exactly there and the check reported nothing, which read as
                # the check having gone blind when it was the fixture throwing
                # the marble out of the channel it was meant to be floating in.
                sample["p"] = [
                    sample["p"][0],
                    sample["p"][1] + 0.5 * MARBLE_DIAMETER,
                    sample["p"][2],
                ]
                # Held up, not thrown up. `RESTING_RISE` exists because a
                # marble climbing away from a hit is not resting, and a marble
                # that a bad collider holds off the floor has no vertical
                # velocity at all - so the doctored sample has to be given the
                # state it is standing in for.
                sample["v"] = [sample["v"][0], 0.0, sample["v"][2]]
                lifted += 1
    if lifted == 0:
        pytest.skip("no resting marble in this replay to lift")
    report = check_replay(doctored, machine, stride=3)
    assert any(f.kind == "floating" for f in report.findings), report.by_kind()


def test_the_contact_check_notices_a_sunk_marble(replay, machine):
    import copy

    doctored = copy.deepcopy(replay)
    for frame in doctored["frames"][::5]:
        for sample in frame["marbles"]:
            if sample["s"] == "running":
                sample["p"] = [
                    sample["p"][0],
                    sample["p"][1] - 0.8 * MARBLE_DIAMETER,
                    sample["p"][2],
                ]
    report = check_replay(doctored, machine, stride=1)
    assert any(f.kind == "penetration" for f in report.findings), report.by_kind()

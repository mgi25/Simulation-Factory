"""The camera: deterministic, gapless, and pointed at something.

A camera track is a lot of numbers and almost none of them can be checked by
eye. What can be checked is the shape of the schedule - that it covers the race
exactly once, that every shot has a reason and a subject where it claims one,
and that solving it twice gives the same file - plus the two framing properties
the brief names as failure modes: racers too small, and the next obstacle
revealed only after it has been hit.
"""

from __future__ import annotations

import json

import pytest

from race2 import courses
from race2.camera import MODES, TrackState, build_track
from race2.events import extract
from race2.framing import MIN_RACER_PIXELS, report
from race2.race import run_race
from race2.shots import plan_for, station_hits

SEED = 8


@pytest.fixture(scope="module")
def filmed(tmp_path_factory):
    """One race, its timeline, its plan and its solved track."""
    course = courses.build("switchyard")
    outcome, replay = run_race(course, seed=SEED, duration=40.0, with_replay=True)
    assert replay is not None
    raw = json.loads(json.dumps(replay.to_json()))
    timeline = extract(outcome, course, outcome.sim_events)
    state = TrackState(raw, course, outcome)
    plan = plan_for(course, outcome, timeline)
    track = build_track(plan, state, course)
    return course, outcome, timeline, state, plan, track, raw


def test_the_schedule_covers_the_race_once(filmed):
    _course, _outcome, timeline, _state, plan, _track, _raw = filmed
    assert plan.shots, "no shots"
    assert not plan.check(), plan.check()
    assert plan.shots[0].start <= timeline.start + 0.05
    # The last shot is the payoff, which deliberately runs past the winner's
    # crossing and may end before the tail of the field has finished.
    assert plan.shots[-1].mode == "winner_payoff"


def test_every_shot_names_a_mode_that_exists_and_a_reason(filmed):
    _course, _outcome, _timeline, _state, plan, _track, _raw = filmed
    for shot in plan.shots:
        assert shot.mode in MODES, shot.name
        assert shot.note, f"{shot.name} has no reason"


def test_every_mechanism_gets_an_anticipation_shot(filmed):
    """The brief's Part G, as a property of the schedule.

    A station that the leaders met and that got no anticipation shot is one the
    film reveals only after the collision.
    """
    course, _outcome, timeline, _state, plan, _track, _raw = filmed
    met = {module for module, _when in station_hits(course, timeline)}
    anticipated = {
        shot.subject for shot in plan.shots if shot.mode == "obstacle_anticipation"
    }
    missing = met - anticipated - {"studs"}
    assert not missing, f"no anticipation shot for {sorted(missing)}"


def test_solving_the_track_twice_gives_the_same_numbers(filmed):
    course, outcome, timeline, state, plan, track, _raw = filmed
    again = build_track(plan_for(course, outcome, timeline), state, course)
    assert json.dumps(track, sort_keys=True) == json.dumps(again, sort_keys=True)


def test_a_shot_never_changes_which_side_it_is_on(filmed):
    """A side chosen per frame would swap mid-cut, which reads as a second camera."""
    _course, _outcome, _timeline, _state, _plan, track, _raw = filmed
    for cut in track["cuts"]:
        assert cut["side"] in (1.0, -1.0), cut["name"]


def test_the_lens_never_jumps(filmed):
    """No frame-to-frame step past the limit, inside a cut.

    Race #1's V19 track moved its lens 29.7 layout units in one frame with a
    perfectly steady aim, and no check in that package could see it. This is
    that check.
    """
    import math

    from race2.camera import MAX_STEP

    _course, _outcome, _timeline, _state, _plan, track, _raw = filmed
    for cut in track["cuts"]:
        rows = cut["frames"]
        for a, b in zip(rows, rows[1:]):
            step = math.dist(a[1:4], b[1:4])
            # A millimetre of tolerance, not a microns' worth: `_limit_step`
            # clamps a step to exactly `MAX_STEP` and the distance of the
            # clamped point comes back as 1.2000000000000002.
            assert step <= MAX_STEP + 1e-3, (
                f"{cut['name']}: the lens moved {step:.2f} in one frame"
            )


def test_the_racers_are_big_enough_to_tell_apart(filmed):
    course, outcome, timeline, _state, _plan, track, raw = filmed
    rows = report(track, raw, course, outcome, timeline)
    small = [r.name for r in rows if r.racer_pixels < MIN_RACER_PIXELS]
    assert not small, f"racers under {MIN_RACER_PIXELS:.0f} px in {small}"


def test_every_anticipation_shot_shows_its_mechanism_before_the_contact(filmed):
    course, outcome, timeline, _state, _plan, track, raw = filmed
    rows = report(track, raw, course, outcome, timeline)
    for row in rows:
        if row.mode != "obstacle_anticipation":
            continue
        assert row.subject_visible > 0.75, (
            f"{row.name}: {row.subject} in frame only "
            f"{row.subject_visible * 100:.0f}% of the shot"
        )
        assert row.lead_seconds is None or row.lead_seconds > 0.35, (
            f"{row.name}: only {row.lead_seconds:.2f} s of warning"
        )


def test_the_field_enters_every_anticipation_shot(filmed):
    """An empty opening is the reveal; an empty shot is a mistake."""
    course, outcome, timeline, _state, _plan, track, raw = filmed
    rows = report(track, raw, course, outcome, timeline)
    for row in rows:
        if row.mode != "obstacle_anticipation":
            continue
        assert row.racers_enter is not None, f"{row.name}: the field never arrived"
        assert row.racers_enter < 0.75, (
            f"{row.name}: the field enters {row.racers_enter * 100:.0f}% through"
        )

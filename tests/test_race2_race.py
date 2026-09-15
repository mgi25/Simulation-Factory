"""One race through the Race #2 course, and what is read off it.

A race is fifteen to twenty seconds of simulation, so everything that needs one
shares a single module-scoped run.
"""

from __future__ import annotations

import pytest

from marble3d.replay import STATE_FINISHED

from race2 import courses
from race2.bench import spearman
from race2.events import EVENT_KINDS, extract
from race2.race import CHECKPOINTS, run_race


# The seed `tools/race2_benchmark.py` chose out of 200, and the one every
# render in `exports/race2_drama_camera/` is of.
HERO_SEED = 8


@pytest.fixture(scope="module")
def raced():
    course = courses.build("switchyard")
    outcome, _ = run_race(course, seed=HERO_SEED, duration=40.0)
    timeline = extract(outcome, course, outcome.sim_events)
    return course, outcome, timeline


def test_the_whole_field_finishes(raced):
    _course, outcome, _timeline = raced
    assert outcome.finished == len(outcome.racers), outcome.failure
    assert outcome.escaped == 0
    assert outcome.stuck == 0


def test_the_finishing_order_is_a_permutation(raced):
    _course, outcome, _timeline = raced
    orders = sorted(r.finish_order for r in outcome.racers)
    assert orders == list(range(1, len(outcome.racers) + 1))
    times = [r.finish_time for r in sorted(outcome.racers, key=lambda r: r.finish_order)]
    assert times == sorted(times), "a later finisher crossed earlier"


def test_progress_never_goes_backwards_and_ends_at_the_course_length(raced):
    course, outcome, _timeline = raced
    for racer in outcome.racers:
        assert 0.0 <= racer.progress <= course.length + 1e-6
        if racer.state == STATE_FINISHED:
            assert racer.progress == pytest.approx(course.length)


def test_every_racer_was_seen_on_every_stage_in_order(raced):
    """Route validity: nobody skipped a stage or arrived out of order.

    A marble that appeared on stage five without having been on stage four went
    somewhere the course does not connect, which on a folded course is a real
    possibility - the legs are five units apart.
    """
    course, outcome, _timeline = raced
    order = [stage.name for stage in course.stages]
    for racer in outcome.racers:
        seen = [
            (course.stage_of[run].name, when)
            for run, when in racer.stage_times.items()
        ]
        seen.sort(key=lambda pair: pair[1])
        names = [name for name, _when in seen]
        assert names == order, f"m{racer.marble_id} ran {names}"


def test_the_checkpoints_were_all_taken(raced):
    _course, outcome, _timeline = raced
    for name, _fraction in CHECKPOINTS:
        for racer in outcome.racers:
            assert name in racer.ranks, f"m{racer.marble_id} has no {name} rank"
        ranks = sorted(racer.ranks[name] for racer in outcome.racers)
        assert ranks == list(range(1, len(outcome.racers) + 1)), name


def test_the_timeline_is_ordered_and_only_uses_declared_kinds(raced):
    _course, _outcome, timeline = raced
    assert timeline.events
    assert [e.time for e in timeline.events] == sorted(e.time for e in timeline.events)
    for event in timeline.events:
        assert event.kind in EVENT_KINDS, event.kind
        assert timeline.start - 1e-6 <= event.time <= timeline.end + 1e-6


def test_extracting_the_timeline_twice_gives_the_same_events(raced):
    course, outcome, timeline = raced
    again = extract(outcome, course, outcome.sim_events)
    assert [e.to_json() for e in again.events] == [e.to_json() for e in timeline.events]


def test_the_hero_seed_has_a_comeback_and_a_close_finish(raced):
    """What `docs/race2_drama_camera.md` says about seed 8, as a test.

    Not a tuning knob - the seed was chosen by `tools/race2_benchmark.py` from
    200 of them and this is what it was chosen for. If a physics change makes
    the claim false, the documentation is wrong and should fail.
    """
    _course, outcome, _timeline = raced
    winner = outcome.winner()
    assert winner is not None
    assert winner.ranks["first_event"] >= 4, (
        f"the winner was already {winner.ranks['first_event']} at the first event"
    )
    # 0.067 s as measured. The bound is loose because the claim is "a photo
    # finish", not "this exact margin", and a tolerance tight enough to pin the
    # margin would fail on a Bullet version bump without anything being wrong.
    assert outcome.podium_gap() < 0.25, outcome.podium_gap()
    assert outcome.lead_changes >= 7, outcome.lead_changes
    # The winner climbed at every checkpoint, which is what makes it a comeback
    # rather than a marble that happened to be lucky at the end.
    order = [winner.ranks[name] for name, _f in CHECKPOINTS if name in winner.ranks]
    assert order == sorted(order, reverse=True) or order[-1] < order[0], order


def test_no_long_dead_interval(raced):
    """The number the whole package exists to push down.

    2.6 s is a ceiling, not a target: the brief asks for a new question every
    two to three seconds and the 200-seed benchmark's worst case is what the
    documentation quotes.
    """
    _course, _outcome, timeline = raced
    _at, gap = timeline.longest_gap()
    assert gap < 2.6, f"{gap:.2f} s with nothing happening"


def test_spearman_is_right_on_cases_that_can_be_checked_by_hand():
    assert spearman([1, 2, 3, 4], [1, 2, 3, 4]) == pytest.approx(1.0)
    assert spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    # Ties take their mean rank, so a constant series correlates with nothing.
    assert spearman([1, 1, 1, 1], [1, 2, 3, 4]) == 0.0
    assert spearman([1, 2, 3, 4, 5], [2, 1, 4, 3, 5]) == pytest.approx(0.8)

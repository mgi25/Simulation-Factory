"""V28.1: the camera changed and nothing else did.

Two halves, and the first is the more important one.

**The locks.** This branch is allowed to change where the lens is and nothing
else. So the first block of tests asserts the things the brief locks - the hero
seed's replay, its finish order, its event times, its runtime, its mechanism
phase, its lack of temporal omissions, and Race #1 - against values written out
here rather than recomputed from the code under test. A camera change that
moved any of them fails here.

**The camera.** The second block asserts what the new system claims: that it is
deterministic, that the rail clears the course, that every candidate is inside
the cut budget, that the final sprint has no cut in it, that the active pack is
on screen, and that no candidate depends on the environment.
"""

from __future__ import annotations

import json
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from race2 import cinematography, courses
from race2.events import extract
from race2.flow import measure
from race2.race import run_race
from race2.rig import (
    PACK_MAX,
    PACK_MIN,
    PackTrack,
    RIGS,
    Spring,
    active_pack,
    build_track,
)
from race2.spine import RUNOUT_TAIL, Spine, camera_rail

HERO = 8
COURSE = "switchyard"

# The hero race, as V28 measured it and as this branch must leave it. Written
# as literals on purpose: a test that recomputed them from the same code would
# pass whatever the code said.
HERO_WINNER = 7
HERO_WINNER_BAY = 0
HERO_ORDER = (7, 2, 1, 5, 3, 0, 6, 4)
HERO_FIRST_FINISH = 15.82
HERO_LAST_FINISH = 18.75
HERO_MARGIN = 0.067
HERO_LEAD_CHANGES = 9
HERO_STATIONS = {
    "studs": 0.93, "drum": 2.23, "sweep": 6.28, "pair": 9.02, "last": 12.68,
}


@pytest.fixture(scope="module")
def race():
    course = courses.build(COURSE)
    outcome, replay = run_race(course, seed=HERO, duration=40.0,
                               marble_count=8, with_replay=True)
    timeline = extract(outcome, course, outcome.sim_events)
    return course, outcome, replay, timeline


@pytest.fixture(scope="module")
def spine(race):
    return Spine(race[0])


@pytest.fixture(scope="module")
def rail(spine):
    return camera_rail(spine)


@pytest.fixture(scope="module")
def pack(race, spine):
    _course, outcome, replay, _timeline = race
    return PackTrack(json.loads(json.dumps(_as_json(replay))), spine, outcome)


def _as_json(replay):
    """The replay in the shape `PackTrack` reads, without going through a file."""
    if isinstance(replay, dict):
        return replay
    return replay.to_json() if hasattr(replay, "to_json") else replay


@pytest.fixture(scope="module")
def plans(race):
    course, outcome, _replay, timeline = race
    marks = cinematography.markers(course, outcome, timeline)
    return {key: build(marks) for key, build in cinematography.CANDIDATES.items()}


# --- the locks ---------------------------------------------------------------


def test_hero_seed_still_finishes_the_race_it_did(race):
    _course, outcome, _replay, _timeline = race
    finished = [r for r in outcome.racers if r.finish_time is not None]
    assert len(finished) == 8, "the hero race must keep all eight finishers"
    order = tuple(
        r.marble_id for r in sorted(finished, key=lambda r: r.finish_time)
    )
    assert order == HERO_ORDER


def test_winner_and_margin_are_unchanged(race):
    _course, outcome, _replay, _timeline = race
    winner = outcome.winner()
    assert winner is not None
    assert winner.marble_id == HERO_WINNER
    assert winner.start_slot == HERO_WINNER_BAY
    times = sorted(r.finish_time for r in outcome.racers if r.finish_time is not None)
    assert times[0] == pytest.approx(HERO_FIRST_FINISH, abs=0.02)
    assert times[-1] == pytest.approx(HERO_LAST_FINISH, abs=0.02)
    assert times[1] - times[0] == pytest.approx(HERO_MARGIN, abs=0.01)


def test_event_timing_and_lead_changes_are_unchanged(race):
    _course, outcome, _replay, timeline = race
    assert outcome.lead_changes == HERO_LEAD_CHANGES
    hits: dict[str, float] = {}
    for event in timeline.events:
        if event.kind == "mechanism_hit":
            module = event.detail.split(" into ")[-1].split(" ")[0]
            hits.setdefault(module, event.time)
    for station, when in HERO_STATIONS.items():
        assert hits[station] == pytest.approx(when, abs=0.02), station


def test_race_runtime_is_unchanged(race):
    _course, _outcome, _replay, timeline = race
    assert timeline.end - timeline.start == pytest.approx(18.733, abs=0.05)


def test_the_films_contain_no_temporal_omission(plans, race, spine, pack):
    """Every frame of every candidate is a consecutive frame of the physics.

    The strong form of the brief's continuity rule, and the reason it can be a
    test rather than a review: a candidate is a list of windows over one replay,
    so it is enough to assert that the windows tile the film without a gap and
    that consecutive rows are one frame apart.
    """
    for key, plan in plans.items():
        assert plan.check() == [], f"camera {key} has a gap or an overlap"
        track = build_track(plan, pack, spine)
        rows = [row for cut in track["cuts"] for row in cut["frames"]]
        # Frame *indices*, not the stored seconds: the rows carry time rounded
        # to six places, so consecutive differences alternate between 0.016666
        # and 0.016667 and comparing them as a set tests the rounding rather
        # than the edit.
        indices = [int(round(row[0] * plan.fps)) for row in rows]
        assert indices == list(range(indices[0], indices[0] + len(indices))), \
            f"camera {key} skips or repeats a frame"


def test_the_course_geometry_is_untouched(race):
    course = race[0]
    assert course.title == "SWITCHYARD"
    assert round(course.layout_length(), 2) == 176.52
    assert round(course.drop(), 1) == 36.6
    assert course.stations == ("studs", "drum", "sweep", "pair", "last")


def test_race_one_is_untouched():
    """`sloped` keeps its own contract, and nothing here imports its decisions."""
    from sloped import track as sloped_track

    assert not hasattr(sloped_track, "WALL_CAP_RACE2")
    import race2.rig as rig
    import race2.spine as spine_module

    for module in (rig, spine_module):
        source = open(module.__file__, encoding="utf-8").read()
        assert "sloped.race" not in source
        assert "sloped.cameras" not in source


def test_nothing_in_the_camera_reads_an_environment():
    """The brief's other session owns the environment; this one may not touch it."""
    import race2.cinematography as cine
    import race2.flow as flow
    import race2.rig as rig
    import race2.spine as spine_module

    for module in (rig, spine_module, cine, flow):
        source = open(module.__file__, encoding="utf-8").read()
        for forbidden in ("environment", "contained_hall", "alpine", "profile_for"):
            assert forbidden not in source.lower().replace(
                "environment one", ""
            ), f"{module.__name__} mentions {forbidden}"


# --- the camera --------------------------------------------------------------


def test_the_spine_is_the_course_plus_a_named_tail(spine, race):
    course = race[0]
    assert spine.racing_length == pytest.approx(course.layout_length(), abs=0.01)
    assert spine.length == pytest.approx(spine.racing_length + RUNOUT_TAIL, abs=0.3)
    assert spine.run_at(spine.racing_length + 1.0) == "runout"


def test_the_downhill_azimuth_is_derived_and_points_downcourse(spine):
    """+Z to within a few degrees, and *measured* from the course's own plane."""
    assert spine.descent < 0.0
    assert spine.downhill_azimuth == pytest.approx(90.0, abs=8.0)


def test_the_downhill_direction_is_derived_from_the_geometry():
    """The rail's preferred side is a fit, not a constant.

    **This is the only direct evidence for the reusability claim.** Every course
    in `race2` - the switchyard and all three concepts - is built on one
    centreline skeleton, so solving a rail for `cascade` and for `switchyard`
    produces the same answer and proves nothing about a second course. What can
    be tested is the step that would have to transfer: that the downhill
    direction comes out of a plane fit and changes when the plane does.
    """
    from race2.spine import _fit_plane

    def azimuth(points):
        _a, gradient_x, gradient_z = _fit_plane(points)
        return math.degrees(math.atan2(-gradient_z, -gradient_x)) % 360.0

    # Falling toward +Z, which is the switchyard.
    assert azimuth([(x, -0.6 * z, z) for x in (-5, 0, 5) for z in range(-20, 21, 5)])         == pytest.approx(90.0, abs=1.0)
    # The same course mirrored: the answer must follow it.
    assert azimuth([(x, +0.6 * z, z) for x in (-5, 0, 5) for z in range(-20, 21, 5)])         == pytest.approx(270.0, abs=1.0)
    # Falling toward -X instead.
    assert azimuth([(x, 0.6 * x, z) for x in range(-20, 21, 5) for z in (-5, 0, 5)])         == pytest.approx(180.0, abs=1.0)


def test_the_rail_clears_the_course_everywhere(rail):
    assert min(rail.clearance) >= 2.3, rail.describe()
    assert min(rail.height) >= 2.0
    assert max(rail.height) <= 12.0


def test_the_rail_is_continuous(rail):
    """No step in the flown rail large enough for a viewer to see as a jump."""
    turns = [
        abs(b - a) / max(sb - sa, 1e-6)
        for a, b, sa, sb in zip(rail.azimuth, rail.azimuth[1:], rail.arc, rail.arc[1:])
    ]
    lifts = [
        abs(b - a) / max(sb - sa, 1e-6)
        for a, b, sa, sb in zip(rail.height, rail.height[1:], rail.arc, rail.arc[1:])
    ]
    assert max(turns) <= 3.0, f"rail turns {max(turns):.2f} deg per layout unit"
    assert max(lifts) <= 1.2, f"rail climbs {max(lifts):.2f} units per layout unit"


def test_the_camera_is_deterministic(plans, pack, spine):
    for key, plan in plans.items():
        first = build_track(plan, pack, spine)
        second = build_track(plan, pack, spine)
        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True), key


def test_the_active_pack_is_bounded_and_always_holds_the_leader(pack):
    for index, members in enumerate(pack.packs):
        assert PACK_MIN <= len(members) <= PACK_MAX, index
        order = pack.order_at(pack.times[index])
        leader = next(m for m in order if m in pack.places[index])
        assert members[0] == leader, index


def test_the_active_pack_rule_is_a_pure_function_of_rank_and_arc():
    order = (3, 1, 4, 0, 2)
    arcs = {3: 100.0, 1: 98.0, 4: 97.0, 0: 80.0, 2: 60.0}
    assert active_pack(order, arcs) == [3, 1, 4]
    # A leader clear by more than the gap still brings the floor with it.
    runaway = {3: 100.0, 1: 70.0, 4: 69.0, 0: 68.0, 2: 60.0}
    chosen = active_pack(order, runaway)
    assert chosen[0] == 3 and len(chosen) == PACK_MIN


def test_every_candidate_is_inside_the_cut_budget(plans):
    """Four to six shots. Over eight is the failure the brief names by number."""
    for key, plan in plans.items():
        assert 4 <= len(plan.shots) <= 6, f"camera {key} has {len(plan.shots)} shots"
        assert plan.cuts() <= 5, f"camera {key} has {plan.cuts()} hard cuts"


def test_no_shot_is_too_short_to_be_a_shot(plans):
    for key, plan in plans.items():
        for shot in plan.shots:
            assert shot.duration() >= cinematography.MIN_SHOT - 1e-6, \
                f"camera {key}: {shot.name} is {shot.duration():.2f} s"


def test_the_final_sprint_is_one_uninterrupted_take(plans, race):
    """The brief's hard rule: no cut between the last mechanism and the winner."""
    course, outcome, _replay, timeline = race
    marks = cinematography.markers(course, outcome, timeline)
    last_mechanism = marks["first"]["last"]
    for key, plan in plans.items():
        final = plan.shots[-1]
        assert final.start <= last_mechanism + 1e-6, \
            f"camera {key} cuts after the last mechanism at {final.start:.2f}"
        assert final.end >= marks["winner"], f"camera {key} cuts before the line"
        inside = [s for s in plan.shots if last_mechanism < s.start < marks["winner"]]
        assert inside == [], f"camera {key} cuts inside the final sprint: {inside}"


def test_every_cut_lands_on_a_physical_moment(plans):
    for key, plan in plans.items():
        for shot in plan.shots[1:]:
            assert shot.cut_on.endswith("contact"), \
                f"camera {key}: {shot.name} cuts on {shot.cut_on!r}"


def test_the_pack_is_on_screen_and_the_racers_are_legible(plans, pack, spine, race):
    _course, outcome, _replay, _timeline = race
    for key, plan in plans.items():
        track = build_track(plan, pack, spine)
        report = measure(track, pack, spine, outcome)
        assert report["racer_pixels"][0] >= 40.0, \
            f"camera {key} racers {report['racer_pixels']} px"
        assert report["phone_pixels"][0] >= 10.0, \
            f"camera {key} phone {report['phone_pixels']} px"
        for shot in report["shot_rows"]:
            assert shot["pack_on_screen"] >= 0.40, \
                f"camera {key}: {shot['name']} keeps {shot['pack_on_screen']:.0%}"


def test_the_lens_never_enters_the_course(plans, pack, spine, race):
    _course, outcome, _replay, _timeline = race
    for key, plan in plans.items():
        report = measure(build_track(plan, pack, spine), pack, spine, outcome)
        assert report["min_lens_clearance"] >= 1.0, \
            f"camera {key} comes within {report['min_lens_clearance']:.2f} units"


def test_the_camera_never_moves_faster_than_a_camera_can(plans, pack, spine, race):
    """Diagnostics, bounded loosely: what these catch is a solver artefact."""
    _course, outcome, _replay, _timeline = race
    for key, plan in plans.items():
        report = measure(build_track(plan, pack, spine), pack, spine, outcome)
        assert report["max_speed"] <= 45.0, f"camera {key} {report['max_speed']} u/s"
        assert report["max_turn"] <= 180.0, f"camera {key} {report['max_turn']} deg/s"


def test_the_spring_is_critically_damped(race):
    """A step input settles without overshoot, and is half settled at the half-life."""
    spring = Spring(0.0, 0.25)
    dt = 1.0 / 60.0
    values = []
    for _ in range(120):
        values.append(spring.step(1.0, dt))
    assert max(values) <= 1.0 + 1e-9, "a critically damped spring does not overshoot"
    assert values[:-1] == sorted(values[:-1]), "and does not ring"
    half = values[int(round(0.25 * 60)) - 1]
    assert 0.40 <= half <= 0.60, f"half-life is not a half-life: {half:.3f}"


def test_a_shot_can_be_rebuilt_from_its_rig_alone(plans):
    """Every candidate is the same six rigs; only the edit differs."""
    used = {shot.rig for plan in plans.values() for shot in plan.shots}
    assert used <= set(RIGS), sorted(used - set(RIGS))
    for plan in plans.values():
        for shot in plan.shots:
            assert shot.rig_for().name == RIGS[shot.rig].name


def test_the_candidates_differ_in_the_edit_and_not_in_the_race(plans, pack, spine):
    """A, B and C film the same replay: same duration, same first and last frame."""
    spans = set()
    for plan in plans.values():
        track = build_track(plan, pack, spine)
        rows = [row for cut in track["cuts"] for row in cut["frames"]]
        spans.add((round(rows[0][0], 3), round(rows[-1][0], 3)))
    assert len(spans) == 1, f"candidates cover different windows: {spans}"


def test_identical_frame_detector_finds_a_duplicate(tmp_path):
    """V28's detector, kept and checked, because it is what found a dead shot."""
    from race2.flow import identical_frames

    same = b"\x89PNG\r\n\x1a\n" + b"identical"
    (tmp_path / "frame_000001.png").write_bytes(same)
    (tmp_path / "frame_000002.png").write_bytes(same)
    (tmp_path / "frame_000003.png").write_bytes(same + b"different")
    pairs = identical_frames(str(tmp_path))
    assert pairs == [("frame_000001.png", "frame_000002.png")]


def test_the_v28_control_is_reproducible_and_unmodified():
    """The control track on disk is V28's, byte for byte, if it has been built."""
    control = os.path.join("output", "race2", "race2_switchyard_8.cameras.json")
    staged = os.path.join("output", "race2", "v281_camera", "V28",
                          "race2_switchyard_8.cameras.json")
    if not (os.path.isfile(control) and os.path.isfile(staged)):
        pytest.skip("the control has not been rendered in this checkout")
    with open(control, "rb") as a, open(staged, "rb") as b:
        assert a.read() == b.read()

"""V31: the locks, and the two instruments this branch added.

The load-bearing test in this file is `test_camera_a_is_byte_identical`. Every
term V31 adds to `race2.rig` defaults to the V28.1 behaviour, and the only
honest way to say so is to build the delivered camera A plan through the new
code and compare the bytes with the track that shipped. If that passes, no
locked thing can have moved: the physics, the seed, the replay, the finish
order and the runtime are all upstream of the camera, and the environment is
not touched by any module under test.

The rest hold the brief's structural locks - four shots, an uncut final sprint,
no screen-direction reversals - and prove both new instruments deterministic.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from race2 import cinematography, courses  # noqa: E402
from race2.events import extract  # noqa: E402
from race2.flow import measure  # noqa: E402
from race2.race import run_race  # noqa: E402
from race2.readability import (  # noqa: E402
    INTEREST_MAX,
    INTEREST_MIN,
    interest_group,
    interest_weights,
    measure_readability,
)
from race2.rig import PackTrack, RIGS, build_track  # noqa: E402
from race2.spine import Spine  # noqa: E402

SEED = 8
COURSE = "switchyard"
REPLAY = os.path.join(REPO, "output", "race2", f"race2_{COURSE}_{SEED}.replay.json")
DELIVERED = os.path.join(
    REPO, "output", "race2", "v281_camera", "A", f"race2_{COURSE}_{SEED}.cameras.json"
)
# The shipped V28.1 camera A schedule, as `docs/race2_v281_racing_cinematography.md`
# reports it. Hard-coded so a change to the marker extraction cannot quietly
# move a cut and still pass.
A_SHOTS = (("release", 0.017, 2.233), ("upper", 2.233, 9.017),
           ("middle", 9.017, 12.683), ("run_in", 12.683, 19.150))
# The sprint boundary at full precision: it is a frame index over 60, not the
# three-decimal number the doc quotes, and a test that compares against the
# rounded value calls the shot before it part of the sprint.
SPRINT_FROM = 761.0 / 60.0
FILM_END = 19.150
# Seed 8's finish order, read from the race rather than assumed. m7 wins from
# m2 by the 0.067 s the V28.1 doc reports.
FINISH_ORDER = [7, 2, 1, 5, 3, 0, 6, 4]


needs_replay = pytest.mark.skipif(
    not os.path.isfile(REPLAY),
    reason=f"hero replay not staged at {REPLAY}; "
           f"run tools/race2_camera.py --course={COURSE} --seed={SEED}",
)


@pytest.fixture(scope="module")
def race():
    course = courses.build(COURSE)
    spine = Spine(course)
    outcome, _replay = run_race(course, seed=SEED, duration=40.0,
                                marble_count=8, with_replay=False)
    timeline = extract(outcome, course, outcome.sim_events)
    marks = cinematography.markers(course, outcome, timeline)
    return course, spine, outcome, marks


@pytest.fixture(scope="module")
def replay():
    if not os.path.isfile(REPLAY):
        pytest.skip("hero replay not staged")
    with open(REPLAY, encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def packs(race, replay):
    _course, spine, outcome, _marks = race
    return {rule: PackTrack(replay, spine, outcome, group=rule)
            for rule in ("pack", "interest")}


@pytest.fixture(scope="module")
def tracks(race, packs):
    _course, spine, _outcome, marks = race
    rails: dict[float, object] = {}
    built = {"A": build_track(cinematography.plan_a(marks), packs["pack"],
                              spine, rails)}
    for key, builder in cinematography.READABILITY.items():
        built[key] = build_track(builder(marks), packs["interest"], spine, rails)
    return built


# --- the lock ----------------------------------------------------------------


@needs_replay
def test_camera_a_is_byte_identical(tracks):
    """The V28.1 camera, built through V31, is the track that shipped.

    This is the branch's whole claim about not having changed anything: the
    race-interest group, the containment stage, the vertical bias, the
    curvature look-ahead, the bend terms and the depression band are all
    additions that are *off* unless a rig asks for them.
    """
    if not os.path.isfile(DELIVERED):
        pytest.skip("delivered camera A track not staged")
    rebuilt = json.dumps(tracks["A"], separators=(",", ":")) + "\n"
    with open(DELIVERED, encoding="utf-8") as handle:
        assert rebuilt == handle.read()


@needs_replay
def test_every_new_rig_field_defaults_to_off(race, packs):
    """A rig with the new fields at their defaults builds A's own track.

    Belt to `test_camera_a_is_byte_identical`'s braces, and it fails with a
    more useful message: it names the field.
    """
    _course, spine, _outcome, marks = race
    from race2.rig import Rig

    fresh = Rig("probe", trail=8.5, reach=10.5)
    assert fresh.contain == 0.0
    assert fresh.frame_bias == 0.0
    assert fresh.lead_curve == 0.0
    assert fresh.look_hold == 0.0
    assert fresh.curve_reach == 0.0
    assert fresh.curve_lift == 0.0
    assert fresh.depression_span == (0.0, 45.0)
    for name, rig in RIGS.items():
        assert rig.contain == 0.0, f"{name} ships with containment on"
        assert rig.frame_bias == 0.0, f"{name} ships with a frame bias"
        assert rig.depression_span == (0.0, 45.0), f"{name} ships with a band"


@needs_replay
def test_the_replay_is_shared_not_resimulated(race, packs):
    """Every candidate films the same race: one `places` table, byte for byte.

    The physics lock, made checkable. Two `PackTrack`s built from the same
    replay differ only in which racers the camera is attached to; the marble
    positions and the finish order are the same objects' same values.
    """
    _course, _spine, outcome, _marks = race
    a, b = packs["pack"], packs["interest"]
    assert a.places == b.places
    assert a.arcs == b.arcs
    assert a.times == b.times
    order = [r.marble_id for r in sorted(
        (r for r in outcome.racers if r.finish_time is not None),
        key=lambda r: r.finish_time)]
    assert len(order) == 8


@needs_replay
def test_locked_race_facts(race):
    """Seed 8's own numbers: the finish order, the margin and the runtime."""
    _course, _spine, outcome, marks = race
    finishes = sorted(
        (r.finish_time, r.marble_id) for r in outcome.racers
        if r.finish_time is not None)
    assert len(finishes) == 8
    assert round(marks["end"], 3) == FILM_END
    assert round(marks["winner"], 4) == 15.8167
    # The 0.067 s crossing the V28.1 doc reports.
    assert round(finishes[1][0] - finishes[0][0], 3) == 0.067
    assert round(finishes[-1][0], 3) == 18.750
    assert [m for _t, m in finishes] == FINISH_ORDER


# --- structural locks --------------------------------------------------------


@needs_replay
@pytest.mark.parametrize("key", ("A", "RA", "RB", "RC"))
def test_shot_count_and_boundaries(tracks, key):
    """Four shots on camera A's own boundaries - the brief's ceiling is five."""
    cuts = tracks[key]["cuts"]
    assert len(cuts) <= 5
    assert len(cuts) == len(A_SHOTS)
    for cut, (name, start, end) in zip(cuts, A_SHOTS):
        assert cut["name"] == name
        assert round(float(cut["from"]), 3) == start
        assert round(float(cut["to"]), 3) == end


@needs_replay
@pytest.mark.parametrize("key", ("A", "RA", "RB", "RC"))
def test_final_sprint_is_one_take(tracks, key):
    """Zero hard cuts from the last powered mechanism to the end of the film."""
    inside = [c for c in tracks[key]["cuts"]
              if float(c["to"]) > SPRINT_FROM + 1e-6]
    assert len(inside) == 1
    assert abs(float(inside[0]["from"]) - SPRINT_FROM) < 1e-6
    assert round(float(inside[0]["to"]), 3) == FILM_END


@needs_replay
@pytest.mark.parametrize("key", ("A", "RA", "RB", "RC"))
def test_film_is_continuous_and_complete(tracks, key):
    """No gap and no overlap between shots, and no temporal omission.

    Every frame of the film at 60 fps is covered exactly once, which is the
    brief's "zero temporal omissions" as something a test can read.
    """
    track = tracks[key]
    assert round(float(track["duration"]), 3) == FILM_END
    seen: list[float] = []
    for cut in track["cuts"]:
        for row in cut["frames"]:
            seen.append(round(float(row[0]), 6))
    assert seen == sorted(seen)
    assert len(seen) == len(set(seen))
    # One frame apart, every time. Compared with a tolerance rather than by
    # rounding: the rows carry six decimals, and 1/60 lands on either side of
    # the sixth one from frame to frame.
    steps = [b - a for a, b in zip(seen, seen[1:])]
    assert max(abs(step - 1.0 / 60.0) for step in steps) < 2e-6


@needs_replay
@pytest.mark.parametrize("key", ("A", "RA", "RB", "RC"))
def test_no_screen_direction_reversals(race, packs, tracks, key):
    """The brief's hard rule, on the instrument that already measures it."""
    _course, spine, outcome, marks = race
    rule = "pack" if key == "A" else "interest"
    report = measure(tracks[key], packs[rule], spine, outcome, marks)
    assert report["direction_flips"] == 0
    assert report["shots"] == 4
    assert report["hard_cuts"] == 3


@needs_replay
def test_the_final_sprint_is_preserved(race, packs, tracks):
    """RA/RB/RC fly the run-in on camera A's own rig parameters.

    The shot is not identical - it is attached to the race-interest group like
    every other shot in those films - but nothing about *the shot* was retuned,
    and the measured result has to stay level with camera A's. The bands are
    generous on purpose: this asserts "not redesigned", not a number.
    """
    _course, spine, outcome, marks = race
    control = measure(tracks["A"], packs["pack"], spine, outcome, marks)
    a_run_in = [s for s in control["shot_rows"] if s["name"] == "run_in"][0]
    for key in ("RA", "RB", "RC"):
        rig = cinematography.READABILITY[key](marks).shots[-1]
        assert rig.rig == "finish_chase"
        assert rig.tweaks == {}, f"{key} retunes the final sprint"
        report = measure(tracks[key], packs["interest"], spine, outcome, marks)
        run_in = [s for s in report["shot_rows"] if s["name"] == "run_in"][0]
        assert run_in["duration"] == a_run_in["duration"]
        assert run_in["racer_pixels"] >= a_run_in["racer_pixels"] - 6.0
        assert run_in["pack_on_screen"] >= a_run_in["pack_on_screen"] - 0.05
        assert run_in["lens_clearance"] >= 1.6


# --- the race-interest group -------------------------------------------------


def test_interest_group_is_the_lead_run_plus_the_contest():
    """A lone leader keeps the frame *and* the bunch behind it.

    The brief's own worked example: first place clear, second to fifth
    fighting. The rule must return both, and not only the leader.
    """
    order = (0, 1, 2, 3, 4, 5, 6, 7)
    arcs = {0: 100.0, 1: 92.0, 2: 91.0, 3: 90.2, 4: 89.5, 5: 70.0, 6: 60.0,
            7: 50.0}
    group = interest_group(order, arcs)
    assert group[0] == 0
    assert set(group) >= {1, 2, 3}
    assert 5 not in group and 6 not in group and 7 not in group
    weights = interest_weights(group, arcs)
    assert weights[0] > weights[1], "a lone leader must outweigh one chaser"


def test_interest_group_drops_a_distant_tail():
    """One racer forty units back must not be allowed to set the framing."""
    order = (0, 1, 2, 7)
    arcs = {0: 100.0, 1: 99.0, 2: 98.0, 7: 60.0}
    assert 7 not in interest_group(order, arcs)


def test_interest_group_respects_its_floor_and_cap():
    order = tuple(range(8))
    spread = {m: 100.0 - m * 9.0 for m in order}
    assert len(interest_group(order, spread)) >= INTEREST_MIN
    bunch = {m: 100.0 - m * 0.4 for m in order}
    assert len(interest_group(order, bunch)) == INTEREST_MAX


def test_interest_group_is_empty_on_an_empty_field():
    assert interest_group((), {}) == []
    assert interest_weights([], {}) == {}


@needs_replay
def test_interest_group_holds_more_of_the_field_than_the_pack(packs):
    """On the hero replay the contest is bigger than four racers, most of the time.

    The number that opened this branch: `active_pack`'s cap binds on 73% of
    frames. If this stops being true the rule change has lost its reason.
    """
    a, b = packs["pack"], packs["interest"]
    assert a.describe()["cap_bound_frames"] / len(a.times) > 0.5
    assert b.describe()["mean_interest"] > a.describe()["mean_pack"] + 1.0
    assert max(len(g) for g in b.groups) <= INTEREST_MAX


# --- both instruments are deterministic --------------------------------------


@needs_replay
def test_camera_tracks_are_deterministic(race, packs):
    """Two builds of the same plan agree to the byte, for every candidate."""
    _course, spine, _outcome, marks = race
    for key, builder in cinematography.READABILITY.items():
        first = build_track(builder(marks), packs["interest"], spine, {})
        second = build_track(builder(marks), packs["interest"], spine, {})
        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True), key


@needs_replay
def test_readability_diagnostics_are_deterministic(race, packs, tracks):
    """And so does the readability instrument, run twice over one track."""
    course, spine, outcome, _marks = race
    from tools.race2_v31_camera import stations_of

    stations = stations_of(course)
    first = measure_readability(tracks["RB"], packs["interest"], spine, outcome,
                                stations, stride=8)
    second = measure_readability(tracks["RB"], packs["interest"], spine, outcome,
                                 stations, stride=8)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


@needs_replay
def test_readability_reports_every_racer(race, packs, tracks):
    course, spine, outcome, _marks = race
    from tools.race2_v31_camera import stations_of

    report = measure_readability(tracks["RB"], packs["interest"], spine, outcome,
                                 stations_of(course), stride=8)
    assert sorted(int(m) for m in report["racers"]) == list(range(8))
    for marble, row in report["racers"].items():
        assert 0.0 <= row["visible_pct"] <= 100.0, marble
        assert row["longest_gap_s"] >= 0.0
    assert report["track"]["forward_arc_mean"] > 0.0
    assert 0.0 <= report["turns"]["turn_read_mean"] <= 1.0


@needs_replay
def test_the_winner_reads_the_course_better_than_camera_a(race, packs, tracks):
    """RB's claim, as the numbers that are supposed to have moved.

    Not a quality assertion - a regression guard. If a later pass changes the
    rig and these fall back to camera A's values, the readability work has been
    undone and this says so.
    """
    course, spine, outcome, _marks = race
    from tools.race2_v31_camera import stations_of

    stations = stations_of(course)
    control = measure_readability(tracks["A"], packs["pack"], spine, outcome,
                                  stations, stride=6)
    winner = measure_readability(tracks["RB"], packs["interest"], spine, outcome,
                                 stations, stride=6)
    assert winner["track"]["forward_arc_mean"] > control["track"]["forward_arc_mean"]
    assert winner["track"]["seen_arc_mean"] > control["track"]["seen_arc_mean"]
    assert winner["turns"]["turn_read_mean"] > control["turns"]["turn_read_mean"]
    assert winner["group"]["visible_pct"] > control["group"]["visible_pct"]
    assert winner["racer_longest_gap_s"] < control["racer_longest_gap_s"]


@needs_replay
def test_the_winner_does_not_pay_for_it_at_the_cuts(race, packs, tracks):
    """And the camera locks the readability work had to respect."""
    _course, spine, outcome, marks = race
    control = measure(tracks["A"], packs["pack"], spine, outcome, marks)
    winner = measure(tracks["RB"], packs["interest"], spine, outcome, marks)
    assert winner["direction_flips"] == 0
    assert winner["worst_reacquire"] <= control["worst_reacquire"] + 0.02
    assert winner["worst_scale_jump"] <= control["worst_scale_jump"]
    assert winner["min_lens_clearance"] >= 1.6
    assert winner["racer_pixels"][0] >= 70.0
    assert winner["phone_pixels"][0] >= 17.0


# --- the environment is not touched ------------------------------------------


def test_no_camera_module_writes_an_environment_profile():
    """The brief's Part N, as a grep with a reason.

    Nothing this branch added may reach the stage: the profiles are JSON under
    `godot/assets`, and a camera that needed to edit one to frame a shot would
    be solving a framing problem with the set.
    """
    import pathlib

    root = pathlib.Path(REPO)
    suspicious = ("environment/profiles", "contained_bay_v301.json",
                  "_lights", "_atmosphere", "albedo")
    for name in ("race2/readability.py", "race2/rig.py", "race2/cinematography.py",
                 "tools/race2_v31_camera.py"):
        text = (root / name).read_text(encoding="utf-8")
        for needle in suspicious:
            assert needle not in text, f"{name} mentions {needle}"


def test_the_profile_the_films_use_is_the_delivered_one():
    """`contained_bay_v301` is rendered as V30.1 shipped it."""
    import pathlib
    import subprocess

    root = pathlib.Path(REPO)
    profile = root / "godot/assets/marble_machine/environment/profiles/contained_bay_v301.json"
    assert profile.is_file()
    result = subprocess.run(
        ["git", "diff", "--name-only", "0bea452", "--",
         "godot/assets/marble_machine/environment/"],
        cwd=root, capture_output=True, text=True,
    )
    if result.returncode == 0:
        assert result.stdout.strip() == "", (
            "the environment changed since the branch point:\n" + result.stdout)

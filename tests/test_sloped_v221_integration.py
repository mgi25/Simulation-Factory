"""What the integrated V22.1 film must be true of, as opposed to its parts.

The three prototypes each have their own suite and those still pass; this one is
about the seams between them and about the things only integration can get
wrong. Four claims, in the order they would bite:

* **the physics is untouched.** Same seed, same digest, same eight crossings in
  the same order. Every test below is about which frames are rendered;
* **the prototypes arrived intact.** The b116 plan, the 3.5 s pacing and
  candidate A's park are the numbers their own passes measured, not numbers that
  drifted on the way in;
* **the clock is derived rather than typed.** A film 1.500 s longer at the front
  and 1.983 s longer in the start places every cue correctly because `prefix`
  and the edit map moved, not because somebody added 3.483 to forty constants;
* **V20, V21 and V22 still rebuild.** The new preview, the new omission, the
  silent join and the parked finish are this edition's, and no older one can see
  them.

The replay and the solved tracks are generated output and not in the branch, so
tests that need them skip rather than fail.
"""

from __future__ import annotations

import json
import math
import os
import sys

import pytest

from sloped import cameras, chase_camera, presentation, v22, v221
from sloped import v221_finish, v221_preview, v221_shuffle

OUT_DIR = os.path.join("output", "sloped_race_v1")
REPLAY = os.path.join(OUT_DIR, "race_5432.json")
SEED = 5432
FINISH_ORDER = [5, 2, 7, 4, 1, 6, 3, 0]
DIGEST = "aafb0d3d872e6c5f6db3a6f52d567ae073f1888fbac4ea4970867c130cf17de6"

# What the arithmetic below has to come out at. Every one of these is derived by
# a test rather than only compared, but having them written down once is what
# makes a change to any of them show up as a diff here.
PREVIEW_FRAMES = 210
PREVIEW_PREFIX = 3.5
OMITTED_FRAMES = 116
LIVE_START = 4.55
START_HANDOFF = 6.700
ANTICIPATION = 1.5
RUNTIME = (26.0, 27.0)
SPLIT = 18.900
FINISH_END = 24.467


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
def race(replay, machine):
    return v221.build_race_track(replay, machine)


@pytest.fixture(scope="module")
def preview(race, machine):
    return v221.build_preview_track(race, machine, SEED)


@pytest.fixture(scope="module")
def clock(race):
    """The clock the finished film runs on, built the way production builds it.

    `master_frames` is what the renderer writes for a track of this duration -
    frame 0 through `round(duration * fps)` inclusive - which is the number
    `presentation.Clock` documents and the one `sloped_short.load_all` reads off
    the encoded file.
    """
    frames = round(float(race["duration"]) * v221.FPS) + 1
    return presentation.Clock(
        segments=tuple(
            (float(s["out"][0]), float(s["out"][1]),
             float(s["replay"][0]), float(s["replay"][1]))
            for s in race["edit"]
        ),
        master_frames=frames,
        prefix=PREVIEW_PREFIX,
    )


# --- the physics is untouched ----------------------------------------------


def test_the_race_is_still_seed_5432(replay):
    assert replay["seed"] == SEED
    assert replay["digest"] == DIGEST
    crossings = [event for event in replay["events"]
                 if event["kind"] == "finish_line"]
    assert [event["id"] for event in crossings] == FINISH_ORDER
    assert crossings == sorted(crossings, key=lambda event: event["t"])
    assert replay["summary"]["failure"] in (None, "", False)


def test_the_winner_is_marble_5_and_the_track_did_not_move_the_crossing(replay, race):
    """A presentation pass may not change when anybody crosses the line."""
    marble, when = v221_finish.winner(replay)
    assert marble == 5
    assert math.isclose(when, 20.85, abs_tol=1e-6)
    assert math.isclose(float(race["last_crossing"]), 24.416667, abs_tol=1e-5)


# --- the three prototypes arrived intact ------------------------------------


def test_the_start_is_b116_with_one_number_moved(replay):
    """b116, and the only field production changes is where it hands over.

    Every number the shuffle pass swept - the two window edges, the omission,
    the elevation - is the prototype's. `tail_to` is not one of those: the
    prototype left it at V22's 7.620 and said so, and the integrated render
    showed the shot holding 1.220 s on a chamber the field had left. See
    `v221.START_HANDOFF`.
    """
    base = v221_shuffle.PLANS["b116"]
    moved = {
        field: (getattr(base, field), getattr(v221.START, field))
        for field in base.__dataclass_fields__
        if getattr(base, field) != getattr(v221.START, field)
    }
    assert set(moved) == {"name", "tail_to"}
    assert v221.START.cut_at == base.cut_at == 2.05
    assert v221.START.resume_at == base.resume_at == 4.0
    assert v221.START.elevation == base.elevation == 30.0
    assert v221.START.omitted_frames() == base.omitted_frames() == OMITTED_FRAMES
    assert v221.START.tail_to == v221.START_HANDOFF == START_HANDOFF
    assert math.isclose(v221.START.live(), LIVE_START, abs_tol=1e-6)


def test_the_handoff_is_after_the_field_has_left_the_chamber(replay, machine):
    """Moving it earlier is a camera decision, so it may not move the trapdoor.

    The floor opens at replay 6.100 and the last marble is below the chamber
    floor - the trapdoor panels' own height, read off the replay - by 6.400.
    The handoff is after that, and after the whole anticipation.
    """
    beats = v221_shuffle.rotor_timeline(machine)
    frames = {round(float(f["t"]), 6): f for f in replay["frames"]}
    floor = frames[6.1]["actuators"]["start.panel0_0"]["p"][1]

    def above(when: float) -> int:
        return sum(1 for m in frames[round(when, 6)]["marbles"]
                   if m["p"][1] > floor - 0.5)

    assert above(6.1) == 8
    assert above(6.4) == 0
    assert beats["gate"] < 6.4 < v221.START.tail_to
    # And no replay time is skipped by the move: the chase starts exactly where
    # the start window ends.
    assert v221.START.tail_to == START_HANDOFF


def test_the_omission_is_a_whole_number_of_rotor_revolutions(machine):
    """116 frames is four revolutions at 13.0 rad/s, to a hundredth of a degree.

    Read off `ShuffleFloor`'s own rate rather than off the 13.0 in the comment,
    so a change to the machine breaks this rather than silently detuning the
    join.
    """
    beats = v221_shuffle.rotor_timeline(machine)
    period = v221_shuffle.revolution_frames(beats["rate"])
    turns = OMITTED_FRAMES / period
    assert abs(turns - round(turns)) * 360.0 < 0.05
    assert round(turns) == 4


def test_the_omission_sits_inside_the_constant_rate_spin(machine):
    """Outside it the rotor is accelerating or lifting, and no gap is free."""
    beats = v221_shuffle.rotor_timeline(machine)
    assert beats["rotor_start"] <= v221.START.cut_at
    assert v221.START.resume_at <= beats["rotor_stop"]


def test_the_start_camera_legs_are_computed_not_typed(replay):
    """`orbit` and `dolly` are `None` on the plan, so `constant_rate_legs` runs.

    That is what makes the join continuous in *velocity* as well as position:
    each window gets the share of the move its own length earns, so the second
    leg opens where the first closed and carries on at the same rate.
    """
    assert v221.START.orbit is None and v221.START.dolly is None
    orbit, dolly = v221_shuffle.plan_legs(v221.START)
    assert orbit[0][1] == orbit[1][0]
    assert dolly[0][1] == dolly[1][0]
    assert orbit[0][0] == v221_shuffle.ORBIT_TRAVEL[0]
    assert orbit[1][1] == v221_shuffle.ORBIT_TRAVEL[1]
    spans = v221_shuffle.window_spans(v221.START)
    # One rate across both windows: degrees per second is the same either side.
    rates = [(leg[1] - leg[0]) / span for leg, span in zip(orbit, spans)]
    assert math.isclose(rates[0], rates[1], rel_tol=1e-6)


def test_the_preview_is_210_frames_of_the_breathing_pacing():
    assert v221.PREVIEW_SECONDS == v221_preview.CANDIDATES["preview_35"]
    assert v221.PACING.frames() == PREVIEW_FRAMES
    assert v221.PACING.dwell == dict(v221_preview.DWELL)


def test_the_finish_is_candidate_a_with_the_swept_numbers():
    """Pinned against `tools/sloped_v221_finish.py`, which is where they came from.

    A library may not import a tool, so `v221.FINISH` retypes them; this is the
    test that stops the two drifting apart without anybody noticing.
    """
    sys.path.insert(0, "tools")
    try:
        import sloped_v221_finish as tool
    finally:
        sys.path.remove("tools")
    assert v221.FINISH.split == tool.PARK["split"] == SPLIT
    assert v221.FINISH.park == tool.PARK["pose"]
    assert v221.FINISH.ratio == tool.PARK["ratio"]
    assert v221.FINISH.aim_settle == tool.PARK["aim_settle"]
    # Candidate A and not B: no orbit onto V19's lens afterwards.
    assert v221.FINISH.orbit is None


# --- the edit map -----------------------------------------------------------


def test_the_edit_is_v22s_with_only_the_start_windows_replaced():
    plan = v221.edit()
    v22_plan = cameras.EDITS["v22"]
    starts = [entry for entry in plan if entry[0] == "start"]
    assert [entry[1:3] for entry in starts] == [(0.2, 2.05), (4.0, START_HANDOFF)]
    assert tuple(entry[:3] for entry in plan if entry[0] != "start") == tuple(
        tuple(entry[:3]) for entry in v22_plan if entry[0] != "start"
    )


def test_both_start_windows_stand_at_thirty_degrees():
    """The elevation that stops `build_track`'s clearance loop stair-stepping.

    V22's delivered start has nine single-frame lens jumps of 0.79-0.87 layout
    units, one per engagement of that loop. Setting the lens where the loop was
    taking it anyway means it never runs.
    """
    starts = [entry for entry in v221.edit() if entry[0] == "start"]
    assert [entry[3]["elevation"] for entry in starts] == [30.0, 30.0]


def test_exactly_116_replay_frames_are_omitted_and_the_clock_never_backs_up(race):
    times = sorted({round(float(row[0]), 6)
                    for cut in race["cuts"] for row in cut["frames"]})
    gaps = [(low, high) for low, high in zip(times, times[1:])
            if high - low > 1.5 / v221.FPS]
    assert len(gaps) == 1
    low, high = gaps[0]
    assert round((high - low) * v221.FPS) - 1 == OMITTED_FRAMES
    assert math.isclose(float(race["omitted"]), 1.95, abs_tol=1e-6)
    # Output time runs forwards, once, over replay that also runs forwards.
    out = [(float(s["out"][0]), float(s["out"][1])) for s in race["edit"]]
    rep = [(float(s["replay"][0]), float(s["replay"][1])) for s in race["edit"]]
    assert out == sorted(out)
    assert rep == sorted(rep)
    for (_a, b), (c, _d) in zip(out, out[1:]):
        assert math.isclose(b, c, abs_tol=1e-9)
    for (_a, b), (c, _d) in zip(rep, rep[1:]):
        assert c >= b - 1e-9


def test_the_anticipation_is_on_screen_in_full(machine):
    """Spin-down, blade lift and stillness, all of it live before the trapdoor.

    V22 resumes 0.267 s before the floor opens, with the blades already up. This
    is the number that says the machine is seen to prepare itself.
    """
    beats = v221_shuffle.rotor_timeline(machine)
    # The anticipation is the machine preparing itself: from the frame the
    # blades start slowing to the frame the floor goes, which is `ShuffleFloor`'s
    # own 4.600 to 6.100 and is a property of the physics rather than the edit.
    assert math.isclose(beats["gate"] - beats["rotor_stop"], ANTICIPATION,
                        abs_tol=1e-6)
    # What the *edit* decides is whether any of it is on screen. All of it is:
    # the second window resumes 0.600 s before the spin-down even begins.
    assert v221.START.resume_at <= beats["rotor_stop"]
    for beat in ("rotor_stop", "settled", "lift_at", "gate"):
        assert v221.START.resume_at <= beats[beat] <= v221.START.tail_to


# --- the join, measured -----------------------------------------------------


def test_the_camera_and_the_rotor_are_continuous_across_the_join(race, replay, machine):
    """The three things V22's join changed, measured on the integrated track.

    V22: the lens stepped 5.374 layout units and pulled back 3.664, the rotor
    stopped from 13 rad/s and rose 1.193, the field moved 1.91 diameters.
    """
    start = {"duration": float(race["cuts"][1]["to"]) - float(race["cuts"][0]["from"]),
             "cuts": race["cuts"][:2]}
    report = v221_shuffle.join_report(start, replay, v221.START, machine)
    assert report["camera_step_join"] == 0.0
    assert report["camera_reach_change"] == 0.0
    assert report["aim_step_join"] == 0.0
    assert report["rotor"]["phase_error_deg"] < 0.05
    assert report["rotor"]["lift_change"] == 0.0
    assert report["rotor"]["inside_constant_rate"] is True
    assert report["marbles"]["max_diameters"] < 1.2
    # And the shot itself is steady: no clearance-loop stair-step anywhere.
    assert report["camera_step_inside"] < 0.10
    assert report["omitted_frames"] == OMITTED_FRAMES
    assert report["omissions"] == 1


# --- the handoff ------------------------------------------------------------


def test_the_preview_arrives_on_the_race_camera_on_all_seven_columns(race, preview):
    track, _report = preview
    deltas = v221.assert_handoff(race, track)
    assert set(deltas) == set(v22.HANDOFF_COLUMNS)
    assert max(deltas.values()) <= v22.HANDOFF_TOLERANCE


def test_the_field_of_view_does_not_snap(race, preview):
    """The eighth column, which V22 never checked and got wrong by 14 degrees."""
    track, report = preview
    assert report["handoff"]["fov_delta"] == 0.0
    assert math.isclose(report["handoff"]["race_fov"],
                        float(race["cuts"][0]["frames"][0][7]), abs_tol=1e-6)
    # Eased rather than stepped: no single frame moves the lens far.
    assert report["handoff"]["max_fov_step"] < 1.0


def test_the_preview_hands_over_at_the_race_cameras_own_speed(preview):
    """V22 arrived at rest against a camera already moving. This does not."""
    _track, report = preview
    assert abs(report["handoff"]["velocity_residual"]) < 0.005
    assert abs(report["handoff"]["turn_residual"]) < 0.01
    assert report["handoff"]["pose_delta"] == 0.0
    assert report["handoff"]["aim_delta"] == 0.0


def test_the_preview_is_paced_and_clean(preview):
    track, report = preview
    assert v221.preview_frames(track) == PREVIEW_FRAMES
    assert math.isclose(v221.preview_prefix(track), PREVIEW_PREFIX, abs_tol=1e-9)
    assert report["problems"] == []
    assert report["landmarks_seen"] == len(report["landmarks"]) == 8
    # It breathes: the slowest frame is many times slower than the fastest.
    assert report["breath_ratio"] > 5.0
    # And every landmark is the subject long enough to be found in the frame.
    assert min(report["subject_seconds"].values()) >= 0.28


def test_every_landmark_is_the_subject_in_course_order(preview):
    """Down-course to up-course, once each, with no landmark revisited."""
    _track, report = preview
    order = [name for name, _second in
             sorted(report["centre_seconds"].items(), key=lambda kv: kv[1])]
    assert order == ["finish", "merge", "branches", "fork", "obstacle",
                     "turns", "mixer", "start"]


# --- the finish -------------------------------------------------------------


def test_the_old_finish_bookend_is_gone(race):
    """No `finish` cut and no hard cut into one: the chase parks instead."""
    names = [cut["name"] for cut in race["cuts"]]
    assert "finish" not in names
    assert names[-1] == "final"
    assert [s["cut"] for s in race["edit"]][-1] == "final"
    last = race["edit"][-1]
    assert math.isclose(float(last["replay"][0]), SPLIT, abs_tol=1e-9)
    assert math.isclose(float(last["replay"][1]), FINISH_END, abs_tol=1e-9)


def test_the_park_continues_the_chase_rather_than_cutting_to_it(race):
    """C1 by construction: the first solved frame leaves at the chase's speed."""
    rows = [row for cut in race["cuts"] for row in cut["frames"]]
    rows = sorted({round(float(r[0]), 6): list(r) for r in rows}.items())
    times = [t for t, _ in rows]
    index = min(range(len(times)), key=lambda i: abs(times[i] - SPLIT))
    before = math.dist(rows[index - 1][1][1:4], rows[index][1][1:4])
    after = math.dist(rows[index][1][1:4], rows[index + 1][1][1:4])
    assert abs(after - before) < 0.05
    # And it comes to a stand: the last second of the film does not move.
    tail = [math.dist(rows[i - 1][1][1:4], rows[i][1][1:4])
            for i in range(len(rows) - 60, len(rows))]
    assert max(tail) < 1e-6


def test_the_finish_passes_its_own_checker(race, replay):
    assert v221_finish.check_finish(race, replay) == []


def test_all_eight_cross_inside_the_final_window(race, replay):
    crossings = sorted(float(event["t"]) for event in replay["events"]
                       if event["kind"] == "finish_line")
    assert len(crossings) == 8
    low = float(race["edit"][-1]["replay"][0])
    high = float(race["edit"][-1]["replay"][1])
    assert all(low <= when <= high for when in crossings)


# --- the clock --------------------------------------------------------------


def test_moving_the_handoff_earlier_costs_the_film_no_time(race):
    """The chase covers replay 6.700-7.620 instead of the start lens. That is all.

    A shorter start *window* is not a shorter film: the edit map is contiguous
    from replay 4.000 to 24.467 either way, so the only thing that changed is
    which camera is pointed at those 0.920 s.
    """
    covered = sum(float(s["replay"][1]) - float(s["replay"][0])
                  for s in race["edit"])
    assert math.isclose(covered, float(race["duration"]), abs_tol=1e-6)
    assert math.isclose(float(race["duration"]), 22.317, abs_tol=1e-6)
    first_chase = next(s for s in race["edit"] if s["cut"] not in ("start",))
    assert math.isclose(float(first_chase["replay"][0]), START_HANDOFF,
                        abs_tol=1e-6)


def test_the_runtime_is_derived_and_lands_where_the_arithmetic_says(clock):
    assert clock.prefix == PREVIEW_PREFIX
    assert clock.prefix_frames == PREVIEW_FRAMES
    assert clock.hold == presentation.HOLD_SECONDS
    assert RUNTIME[0] <= clock.duration <= RUNTIME[1]
    assert clock.frames == clock.prefix_frames + clock.hold_frames + clock.master_frames


def test_every_cue_is_placed_through_the_clock_rather_than_offset_by_hand(
        clock, replay, machine):
    """The events the film marks, each one landing after the preview and hold.

    The point is not the individual numbers - they move whenever the edit does -
    but that they are all `clock.at` of a replay instant, so a 1.500 s longer
    preview moves all of them together and none of them separately.
    """
    beats = v221_shuffle.rotor_timeline(machine)
    gate = presentation.actuator_move(replay, clock, "start.paddle")
    trapdoor = presentation.actuator_move(replay, clock, "start.panel")
    winner = clock.at(v221_finish.winner(replay)[1])
    assert gate is not None and trapdoor is not None and winner is not None
    assert clock.origin < gate < trapdoor < winner < clock.duration
    # The trapdoor is `gate_time` mapped through the edit, to the frame.
    assert math.isclose(trapdoor, clock.at(beats["gate"]) or -1.0, abs_tol=0.02)
    # Every crossing is in the film.
    for event in replay["events"]:
        if event["kind"] == "finish_line":
            assert clock.at(float(event["t"])) is not None


def test_replay_the_edit_omitted_has_no_output_time(clock):
    """The 116 frames are not in the film, so nothing may be placed on them."""
    assert clock.at(3.0) is None
    assert clock.at(2.05) is not None
    assert clock.at(4.0) is not None


# --- audio ------------------------------------------------------------------


def test_the_phase_locked_join_is_deliberately_uncued():
    from audio import marble

    assert marble.CUES["v221"].omission is False
    assert marble.CUES["v221"].mechanism is True
    assert marble.CUES["default"] == marble.Cues()


def test_the_mechanism_is_derived_from_the_recorded_rotor(replay, clock):
    """Drone, spin-down and lift all come out of `start.rotor`'s own transforms.

    No beat below is typed: the rate falls because the recorded rate falls, and
    the lift happens where the recorded height rises.
    """
    motion = presentation.actuator_motion(replay, clock, "start.rotor")
    assert motion
    spinning = [rate for out, rate, _rise in motion if out < clock.at(4.6)]
    assert max(spinning) > 12.9
    settled = [rate for out, rate, _rise in motion
               if clock.at(5.0) <= out <= clock.at(6.0)]
    assert max(settled) < 0.1
    rises = [rise for _out, _rate, rise in motion]
    assert max(rises) > 1.19
    # The lift is inside the second live window, after the spin-down.
    lifting = [out for out, _rate, rise in motion if 1e-3 < rise < 1.19]
    assert clock.at(5.2) - 0.05 <= min(lifting) <= clock.at(5.9)


def test_the_soundtrack_places_the_new_voices_and_drops_the_whoosh(replay, clock, race):
    from audio import marble

    mix = marble.build_race_audio(replay, race, clock, music=False,
                                  cues=marble.CUES["v221"])
    assert "whoosh" not in mix.placed
    assert mix.placed["mechanism"] == 1
    assert mix.placed["lift"] == 1
    assert mix.placed["trapdoor"] == 1
    assert mix.placed["crossing"] == 8
    assert not mix.limited


# --- backwards compatibility ------------------------------------------------


def test_v22_still_solves_its_own_edit_and_its_own_start(replay, machine):
    """The generalised `edit` parameter did not move V22's own plan."""
    assert chase_camera.edit_plan("v22") == cameras.EDITS["v22"]
    starts = [entry for entry in cameras.EDITS["v22"] if entry[0] == "start"]
    assert [entry[1:3] for entry in starts] == [(0.2, 1.9), (5.833333, 7.62)]
    assert all("elevation" not in (entry[3] if len(entry) > 3 else {})
               for entry in starts)


def test_v22s_handoff_check_still_reads_six_columns():
    """Seven would fail the delivered film, and that is the point of the default.

    V22's preview ends at 48 degrees and its race opens at 34. The snap is real;
    `assert_handoff`'s six-column default is what lets V22 keep rebuilding while
    V22.1 is held to the stricter reading.
    """
    import inspect

    signature = inspect.signature(v22.assert_handoff)
    assert signature.parameters["columns"].default == 6


def test_the_older_editions_keep_their_own_cues_and_paths():
    sys.path.insert(0, ".")
    from tools.sloped_short import EDITIONS, cue_policy

    from audio import marble

    for edition in ("v20", "v211", "v21", "v22"):
        assert cue_policy(edition) == marble.CUES["default"]
    assert cue_policy("v221") == marble.CUES["v221"]
    assert EDITIONS["v22"]["master"].endswith(os.path.join("v22", "race_master.mp4"))
    assert EDITIONS["v221"]["master"].endswith(os.path.join("v221", "race_master.mp4"))
    assert EDITIONS["v221"]["cuts"] == ()
    assert EDITIONS["v22"]["runtime"] == (22.8, 23.3)


def test_the_production_tool_keeps_both_editions():
    sys.path.insert(0, ".")
    from tools.sloped_v22 import EDITIONS, DEFAULT_EDITION

    assert DEFAULT_EDITION == "v22"
    assert EDITIONS["v22"]["module"] is v22
    assert EDITIONS["v221"]["module"] is v221
    assert EDITIONS["v22"]["check"] is chase_camera.check_chase
    assert EDITIONS["v221"]["check"] is v221_finish.check_finish

"""What the integrated V24 film must be true of, as opposed to its parts.

The four labs each have their own suite and those still pass. This one is about
the seams and about the things only integration can get wrong. Five claims, in
the order they would bite:

* **the physics is untouched.** Same seed, same digest, same eight crossings in
  the same order, and - new to V24 - the same recorded quaternion on every
  marble, because this is the first edition that draws rotation at all;
* **the opening is the experiment.** No preview, no hold, `b_gate`, PICK A COLOR
  on frame zero over live footage, and eight racers large enough to choose
  between at the size a feed is scrolled at;
* **the edit map is honest.** Every segment slope 1, three omissions, each of
  them a window boundary rather than a compression, and the rotor phase read off
  the frames the renderer will actually draw;
* **the body is V22.1's.** Not "close to": the same solve, pose for pose, on
  every frame V24 keeps;
* **V20, V21, V21.1, V22 and V22.1 still rebuild.** The hook, the meridian
  racers, the plate and the missing hold are this edition's and no older one can
  see them.

The replay and the solved tracks are generated output and not in the branch, so
tests that need them skip rather than fail.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys

import pytest

from sloped import cameras, presentation, v221, v221_shuffle, v24, v24_hook
from sloped import v24_payoff, v24_spin, v24_timeline

OUT_DIR = os.path.join("output", "sloped_race_v1")
REPLAY = os.path.join(OUT_DIR, "race_5432.json")
V221_TRACK = os.path.join(OUT_DIR, "cameras_v221_5432.json")
V24_TRACK = os.path.join(OUT_DIR, "cameras_v24_5432.json")
SEED = 5432
FINISH_ORDER = [5, 2, 7, 4, 1, 6, 3, 0]
DIGEST = "aafb0d3d872e6c5f6db3a6f52d567ae073f1888fbac4ea4970867c130cf17de6"

# What the arithmetic has to come out at. Each is derived by a test below as
# well as compared, so a change shows up here as a diff rather than as a silent
# drift somewhere in the solve.
HOOK_NAME = "b_gate"
HOOK_SECONDS = 1.4
DURATION = 20.116666
FRAMES = 1208
RUNTIME = (19.8, 20.4)
OMISSION_COUNT = 3
WINNER = 5
WINNER_LABEL = "PURPLE"
WINNER_FROM = 6
WINNER_HUE = (0x8E, 0x3F, 0xD4)
TAIL_AT = 23.45


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
def track(replay, machine):
    if os.path.isfile(V24_TRACK):
        with open(V24_TRACK, "r", encoding="utf-8") as handle:
            return json.load(handle)
    return v24.build_race_track(replay, machine)


@pytest.fixture(scope="module")
def v221_track():
    if not os.path.isfile(V221_TRACK):
        pytest.skip(f"{V221_TRACK} is generated output and is not in the branch")
    with open(V221_TRACK, "r", encoding="utf-8") as handle:
        return json.load(handle)


# --- the physics is untouched -----------------------------------------------


def test_seed_and_digest_are_the_locked_ones(replay):
    assert int(replay["seed"]) == SEED
    assert replay.get("digest", DIGEST) == DIGEST


def test_finish_order_is_unchanged(replay):
    order = [
        int(event["id"])
        for event in sorted(
            (e for e in replay["events"] if e["kind"] == "finish_line"),
            key=lambda e: int(e["order"]),
        )
    ]
    assert order == FINISH_ORDER


def test_the_winner_is_marble_five_and_it_is_purple(replay):
    first = min(
        (e for e in replay["events"] if e["kind"] == "finish_line"),
        key=lambda e: int(e["order"]),
    )
    assert int(first["id"]) == WINNER == v24_payoff.WINNER_INDEX
    assert v24_payoff.COLOUR_NAMES[WINNER] == WINNER_LABEL
    from sloped import overlays

    assert tuple(overlays.MARBLE_HUES[WINNER]) == WINNER_HUE
    assert abs(float(first["t"]) - v24.WINNER_CROSSES) < 1e-6


def test_no_module_here_writes_to_the_replay(replay, machine):
    """V24 reads the replay and never writes one. Checked by value.

    The cheapest possible regression test for "nothing re-simulates": build the
    whole track and assert the replay document is the same object it was.
    """
    before = json.dumps(replay["frames"][0], sort_keys=True)
    v24.build_race_track(replay, machine)
    assert json.dumps(replay["frames"][0], sort_keys=True) == before


def test_the_recorded_quaternions_are_what_the_film_draws(replay):
    """**No synthetic spin.** The surface follows the replay or nothing does.

    `v24_spin.angular_stats` takes angular speed two ways - PyBullet's recorded
    `w`, and the angle between consecutive recorded orientations - precisely so
    that a stale quaternion beside a live velocity would show up as a
    disagreement. They agree, which is the evidence that the marking rides real
    physics rather than a rolling law fitted to linear speed.
    """
    import numpy as np

    quaternions = v24_spin._as_array(replay, "q")
    assert quaternions.shape[1] == 8
    # A unit quaternion per marble per frame, which a fabricated spin would not
    # generally be.
    norms = np.linalg.norm(quaternions, axis=2)
    assert abs(float(norms.min()) - 1.0) < 1e-3
    assert abs(float(norms.max()) - 1.0) < 1e-3
    # And they actually turn: a marble whose orientation never changed would be
    # the bug `meridian` exists to make visible.
    turned = np.degrees(v24_spin.angle_between(quaternions[0], quaternions[-1]))
    assert float(turned.min()) > 1.0


# --- the opening is the experiment ------------------------------------------


def test_the_hook_is_b_gate_and_its_numbers_are_the_labs(replay):
    assert v24.HOOK.name == HOOK_NAME
    assert v24.HOOK is v24_hook.HOOKS[HOOK_NAME]
    assert v24.HOOK.seconds == HOOK_SECONDS
    assert v24.HOOK.opens_at == v24_hook.LIVE_FROM == 0.2
    assert v24.HOOK.hands_over() == 1.6


def test_there_is_no_course_preview(replay):
    from tools import sloped_short, sloped_v22

    assert "preview" not in sloped_short.EDITIONS["v24"]
    assert sloped_v22.has_preview("v24") is False
    assert sloped_v22.has_preview("v221") is True


def test_there_is_no_frozen_opening_hold():
    from tools.sloped_short import EDITIONS

    assert EDITIONS["v24"]["hold"] == 0.0
    for edition in ("v20", "v211", "v21", "v22", "v221"):
        assert EDITIONS[edition].get("hold", presentation.HOLD_SECONDS) == 0.70


def test_the_film_opens_on_the_hook_and_the_clock_knows_it(track):
    clock = presentation.Clock(
        tuple(
            (float(r["out"][0]), float(r["out"][1]),
             float(r["replay"][0]), float(r["replay"][1]))
            for r in track["edit"]
        ),
        hold=0.0, fps=60, master_frames=v24.master_frames(track), prefix=0.0,
    )
    assert clock.origin == 0.0
    assert clock.prefix_frames == 0
    assert clock.hold_frames == 0
    # Output second zero is the hook's first frame, which is replay 0.200.
    assert abs(clock.replay_at(0.0) - v24.HOOK.opens_at) < 1e-9


def test_the_mark_is_pick_a_color_and_it_is_up_at_second_zero():
    assert v24_hook.HOOK_TEXT == "PICK A COLOR"
    assert v24.MARK_IN == 0.0
    assert v24.MARK_OUT_FROM < v24.MARK_OUT_TO <= v24.HOOK.seconds
    # It is drawn, and it has ink where the baseline says.
    image = v24_hook.pick_a_color(baseline=v24.MARK_BASELINE)
    assert image.size == (1080, 1920)
    box = image.getbbox()
    assert box is not None
    assert box[1] < v24.MARK_BASELINE < box[3] + 1


def test_the_mark_does_not_fade_in_when_it_opens_on_frame_zero():
    """The filter graph must not put a `fade=t=in` on a mark that opens at 0.

    A fade in starting at second zero makes the first frame transparent, and
    the first frame is the one the whole pass exists for.
    """
    from tools import sloped_short

    plan = {
        "cuts": (), "hold": 0.0, "prefix": 0.0, "preview": None,
        "mark": (v24.MARK_IN, v24.MARK_OUT_FROM, v24.MARK_OUT_TO),
        "card": (18.0, 19.8), "duration": DURATION, "frames": FRAMES,
        "ring_from": 17.45, "ring_frames": 18, "ring_dir": "x",
        "hook": "h.png", "fact": "f.png", "master": "m.mp4",
        "video": "v.mp4", "visual": "s.mp4", "silent": None, "keep": (),
    }
    # The mark's own stream, which is the one that must not fade. The end
    # card's `fade=t=in:st=0` is a different stream and is always there: it
    # fades in over its own first frame, which is 18 s into the film.
    graph = sloped_short._graph_for(plan)
    mark_stream = graph.split("[1:v]")[1].split("[hook];")[0]
    assert "fade=t=in" not in mark_stream, mark_stream
    assert "fade=t=out:st=1.05" in mark_stream
    assert "tpad" not in graph
    # and the opposite, for an edition that does hold
    held = dict(plan, hold=0.70, mark=(0.10, 0.62, 0.80))
    held_graph = sloped_short._graph_for(held)
    held_mark = held_graph.split("[1:v]")[1].split("[hook];")[0]
    assert "fade=t=in:st=0.1" in held_mark
    assert "tpad=start_duration=0.7" in held_graph


def test_frame_zero_shows_all_eight_racers_large(track, replay):
    report = v24_hook.first_frame_report(track, replay)
    assert report["racers"] == report["of"] == 8
    # The hook lab measured 146 px median over a 130-167 range; the integrated
    # solve must not have moved it, so this is a band round the lab's answer
    # rather than a floor anybody could pass.
    assert 130.0 <= report["median_px"] <= 167.0
    assert report["min_px"] >= 120.0
    assert report["occupancy"] >= 0.05
    assert report["off_centre"] <= 0.15


def test_the_machine_moves_inside_the_first_quarter_second(replay, track):
    motion = v24_hook.motion_report(replay, v24.HOOK, track)
    assert motion["mechanism"] <= 0.25
    assert motion["racers"] <= 0.30
    assert motion["camera"] <= 0.25
    assert motion["first"] <= 0.15


# --- the edit map is honest -------------------------------------------------


def test_every_segment_has_slope_one(track):
    for segment in track["edit"]:
        out = segment["out"][1] - segment["out"][0]
        replay_span = segment["replay"][1] - segment["replay"][0]
        assert abs(out - replay_span) < 1e-9, segment


def test_the_segments_tile_the_output_with_no_gap(track):
    cursor = 0.0
    for segment in track["edit"]:
        assert abs(segment["out"][0] - cursor) < 1e-9, segment
        cursor = segment["out"][1]
    assert abs(cursor - track["duration"]) < 1e-9
    assert abs(track["duration"] - DURATION) < 1e-9


def test_the_interior_cuts_are_window_boundaries_not_compressions(track):
    """The trap omission is a *split*, so the obstacle is two windows.

    This is the whole reason V24 does not use `presentation.omit_frames`: that
    helper emits one segment per window, so a cut in the middle of one leaves a
    segment of slope 1.43. Here the cut *is* a boundary and the slope test above
    is what proves it.
    """
    names = [segment["cut"] for segment in track["edit"]]
    assert names.count("obstacle") == 2
    assert names.count("start") == 2
    assert names[0] == "hook"
    first, second = [s for s in track["edit"] if s["cut"] == "obstacle"]
    assert abs(first["replay"][1] - v24.TRAP_FROM) < 1e-9
    assert abs(second["replay"][0] - v24.TRAP_TO) < 1e-9
    # the far edge is the spinner's phase lock, not the pacing lab's frame
    assert v24.TRAP_TO < v24.TRAP_FROM + v24_timeline.TRAP.seconds


def test_omit_frames_would_have_got_the_trap_wrong():
    """The defect the pacing lab found, reproduced, so the workaround is pinned.

    If `presentation.omit_frames` is ever fixed this test fails and V24 may use
    it; until then it records exactly why V24 does not.
    """
    clock = presentation.Clock(
        ((0.0, 10.0, 0.0, 10.0),), hold=0.0, fps=60, master_frames=601,
    )
    cut, _keep = presentation.omit_frames(clock, ((200, 229),))
    assert len(cut.segments) == 1
    out_span = cut.segments[0][1] - cut.segments[0][0]
    replay_span = cut.segments[0][3] - cut.segments[0][2]
    assert replay_span > out_span + 1e-6      # slope > 1: the defect
    assert v24.master_frames({"duration": DURATION, "fps": 60}) == FRAMES


def test_there_are_exactly_three_omissions_and_they_are_the_measured_ones(track):
    assert len(v24.OMISSIONS) == OMISSION_COUNT
    names = [name for name, _a, _b in v24.OMISSIONS]
    assert names == ["spin", "fall", "trap"]
    # The two the measurement removed are *not* here, and the module says so.
    assert v24_timeline.STOPPED not in ()      # it still exists in the lab
    omitted = track["omitted"]
    total = sum(after - before - 1.0 / 60 for _n, before, after in v24.OMISSIONS)
    assert abs(omitted - total) < 0.02


def test_the_trap_and_mixer_bounds_come_from_the_labs_master_frames(v221_track):
    """The cuts are the labs' own, read through the delivered master.

    Derived here from `load_master`'s own reading rather than from the module's
    arithmetic, so a track that concatenates differently fails here rather than
    silently moving a cut.

    The trap's *far* edge is four frames earlier than the pacing lab's, and
    those four frames are the spinner's phase lock - see the next test.
    """
    master = v24_timeline.load_master(v221_track)
    assert abs(master.replay_of[v24_timeline.TRAP.first - 1] - v24.TRAP_FROM) < 1e-6
    assert abs(master.replay_of[v24_timeline.SPIN.last + 1] - v24.RESUME_FRAME) < 1e-6
    resumes_at = v24_timeline.TRAP.first + v24.TRAP_RESUME_FRAMES
    assert abs(master.replay_of[resumes_at] - v24.TRAP_FRAME) < 1e-6
    assert v24.TRAP_RESUME_FRAMES < v24_timeline.TRAP.frames


def test_every_mechanism_on_screen_is_phase_clean_across_its_join(replay):
    """The gap every pass before this one had: which machine is the subject.

    `v24_spin.MACHINE_KEYS` is `start.rotor0..3`, which is the right constraint
    for a cut in the start shot and the only one anybody checked. The trap cut's
    subject is three four-bladed `obstacle.wheel`s, and against those the pacing
    lab's placement lands 13.13 degrees out of a quarter turn where one frame is
    3.44. V24 resumes four frames earlier and lands at 0.62.
    """
    from tools.sloped_v24_audit import phase_audit

    for name, before, after in v24.OMISSIONS:
        rows = phase_audit(replay, before, after, v24.IN_FRAME_ACTUATORS[name])
        on_screen = [row for row in rows if row["on_screen"]]
        assert on_screen, name
        for row in on_screen:
            assert row["phase_error_deg"] <= v24.PHASE_BAR_DEG, (name, row)

    # and the placement this rejected, so the finding cannot quietly come back
    lab_resume = round(v24.TRAP_FROM + (v24_timeline.TRAP.frames + 1) / 60.0, 6)
    rows = phase_audit(replay, v24.TRAP_FROM, lab_resume,
                       v24.IN_FRAME_ACTUATORS["trap"])
    worst = max(row["phase_error_deg"] for row in rows if row["on_screen"])
    assert worst > 10.0


def test_the_mixer_join_is_phase_exact_on_the_rendered_frames(replay):
    """The rotor phase, read off the frames the renderer draws.

    V22.1's own join is a frame off its nominal lock because replay 4.000 is a
    boundary row the renderer drops. V24 resumes 28 rendered frames later, which
    makes the gap five exact revolutions plus the one step a join is entitled
    to - so the blades land where the next frame would have put them.
    """
    _name, before, after = v24.OMISSIONS[0]
    across = v24_spin.machine_mismatch(replay, before, after)
    one_frame = v24_spin.machine_mismatch(replay, before, before + 1.0 / 60)
    assert abs(across - one_frame) < 1.0
    # and the shipped join, for contrast: a whole frame out
    shipped = v24_spin.machine_mismatch(replay, before, 4.0 + 1.0 / 60)
    assert abs(shipped - one_frame) > 10.0


def test_every_join_is_legal_on_machine_state(replay):
    """No cut straddles a gate, a rotor ramp, a blade lift or the trapdoor.

    The machine's visible state must be the same on both sides of an omission,
    or the cut shows the mechanism teleporting - which is the defect V22 shipped
    and V22.1 was written out of.
    """
    for name, before, after in v24.OMISSIONS:
        one = v24_timeline.machine_state(replay, before)
        two = v24_timeline.machine_state(replay, after)
        for key in ("rotor_rate", "panel_rate", "paddle_rate"):
            assert abs(one[key] - two[key]) < 0.5, (name, key, one[key], two[key])
        for key in ("rotor_height", "panel_height", "paddle_height"):
            assert abs(one[key] - two[key]) < 0.05, (name, key)


def test_no_join_is_more_exposed_than_the_films_own(replay, track):
    """The orientation-join audit, as a bar rather than a report.

    Meridian makes rotation observable, so every omission is quoted against the
    per-frame spread of the shot it sits in. The bar is where the film's own
    accepted joins fall.
    """
    from tools.sloped_v24_audit import EXPOSURE_BAR, join_audit

    clock = presentation.Clock(
        tuple((float(r["out"][0]), float(r["out"][1]),
               float(r["replay"][0]), float(r["replay"][1]))
              for r in track["edit"]),
        hold=0.0, fps=60, master_frames=v24.master_frames(track),
    )
    rows = join_audit(replay, track, clock)
    assert len(rows) == OMISSION_COUNT
    for row in rows:
        assert row["exposure"] <= EXPOSURE_BAR or not row["same_camera"], row
        assert row["screen_px_max"] < 300.0 or not row["same_camera"], row


# --- the body is V22.1's ----------------------------------------------------


def test_every_body_frame_is_the_shipped_solve(track, v221_track):
    """Pose for pose, not "close to". The body is a re-render, not a re-solve."""
    shipped: dict[str, dict[float, list]] = {}
    for cut in v221_track["cuts"]:
        for row in cut["frames"]:
            shipped.setdefault(cut["name"], {})[round(float(row[0]), 6)] = row
    checked = 0
    for cut in track["cuts"]:
        if cut["name"] in ("hook", "start"):
            continue
        for row in cut["frames"]:
            reference = shipped[cut["name"]][round(float(row[0]), 6)]
            assert row[1:] == reference[1:], (cut["name"], row[0])
            checked += 1
    assert checked > 900


def test_the_chase_still_opens_where_v221_hands_over(track):
    """The start ends 0.283 s early; the chase is unmoved.

    The fall omission is taken *against the lens change*, which means the chase
    picks the field up where it always did rather than being re-solved to a new
    bound. If this drifts, the whole body would have to be re-measured.
    """
    descent = next(s for s in track["edit"] if s["cut"] == "descent")
    assert abs(descent["replay"][0] - v221.START_HANDOFF) < 1e-9
    start = [s for s in track["edit"] if s["cut"] == "start"][-1]
    assert abs(start["replay"][1] - v24.FALL_AT) < 1e-9


def test_the_start_legs_are_re_split_so_the_rate_never_changes(replay, machine):
    """The camera cost the pacing lab warned about, paid off by re-solving.

    Cutting the delivered master would step the lens 28 frames' worth of its own
    orbit - 1.56 layout units - across the mixer join. Re-solving to V24's own
    windows with `constant_rate_legs` makes that step one ordinary frame.
    """
    start = v24.build_start_track(replay, machine)
    first, second = start["cuts"]
    step = math.dist(first["frames"][-1][1:4], second["frames"][1][1:4])
    inside = math.dist(first["frames"][-2][1:4], first["frames"][-1][1:4])
    assert step < 2.0 * inside
    assert step < 0.20


def test_the_hook_lands_on_the_start_shots_own_first_pose(replay, machine):
    opening = v24.build_opening_track(replay, machine)
    hook_last = opening["cuts"][0]["frames"][-1]
    start_first = opening["cuts"][1]["frames"][0]
    assert hook_last == start_first


def test_the_tail_stops_after_five_crossings(replay, track):
    crossings = sorted(
        float(e["t"]) for e in replay["events"] if e["kind"] == "finish_line"
    )
    shown = [when for when in crossings if when <= v24.TAIL_AT + 1e-9]
    assert len(shown) == 5
    assert v24.TAIL_AT == TAIL_AT
    assert crossings[5] > v24.TAIL_AT          # the sixth is not in the film
    final = track["edit"][-1]
    assert abs(final["replay"][1] - v24.TAIL_AT) < 1e-9


# --- the racers, the payoff, and the editions before this one ---------------


def test_the_racer_appearance_is_meridian_and_the_default_is_solid():
    from tools.sloped_v22 import EDITIONS

    assert v24.RACERS == "meridian"
    assert v24.RACERS in v24_spin.APPEARANCES
    assert f"--racers={v24.RACERS}" in EDITIONS["v24"]["scene"]
    for edition in ("v22", "v221"):
        assert not any(flag.startswith("--racers")
                       for flag in EDITIONS[edition]["scene"])
    source = os.path.join("godot", "scripts", "sloped_race_scene.gd")
    with open(source, "r", encoding="utf-8") as handle:
        text = handle.read()
    assert 'const DEFAULT_RACERS := "solid"' in text


def test_the_marker_is_in_the_albedo_map_and_not_a_second_transform():
    """No independent texture animation and no child node to animate.

    The marker is painted into the racer material's albedo map, which lives in
    the mesh's own UV space and is therefore carried by the node transform the
    replay sets. If a future change added a rotating child or a time-varying
    texture, this is where it would show.
    """
    source = os.path.join("godot", "assets", "marble_machine", "racers",
                          "racer_visual.gd")
    with open(source, "r", encoding="utf-8") as handle:
        text = handle.read()
    for forbidden in ("_process(", "get_ticks", "Time.", "AnimationPlayer",
                      "Tween", "rotate("):
        assert forbidden not in text, forbidden


def test_the_payoff_is_the_plate_and_it_names_the_colour():
    from tools.sloped_short import EDITIONS

    assert EDITIONS["v24"]["payoff"] == v24_payoff.RECOMMENDED == "plate"
    card = v24_payoff.build(style="plate", winner=WINNER, from_place=WINNER_FROM)
    assert card.label == WINNER_LABEL
    assert card.text_contrast >= 4.5
    # The colour is an area, not a dot: the plate is the sample.
    assert card.colour_pixels > 20000
    low, high = v24_payoff.PAYOFF_BAND
    assert low <= card.box[1] and card.box[3] <= high
    for edition in ("v20", "v211", "v21", "v22", "v221"):
        assert EDITIONS[edition].get("payoff") is None


def test_the_ring_opens_on_the_crossing_where_the_winner_is_visible():
    plan = v24_payoff.schedule(
        crossing=v24_payoff.CROSSING, beat=v24.BEAT,
        seconds=v24_payoff.PAYOFF_SECONDS,
    )
    ring_from, ring_to = plan["ring"]
    assert ring_from == v24_payoff.CROSSING
    assert abs((ring_to - ring_from) - v24_payoff.RING_SECONDS) < 1e-9
    # Most of the ring is on a marble that is actually on screen.
    visible = v24_payoff.WINNER_VISIBLE[0]
    overlap = min(ring_to, visible[1]) - max(ring_from, visible[0])
    assert overlap >= 0.20
    assert plan["ring_on_visible_winner"] >= 0.20
    # and the shipped placement, for contrast
    shipped = v24_payoff.schedule(beat=1.0)
    assert plan["ring_on_visible_winner"] > 10.0 * 0.017


def test_the_card_ends_with_the_film_and_after_a_recognition_beat(track):
    clock = presentation.Clock(
        tuple((float(r["out"][0]), float(r["out"][1]),
               float(r["replay"][0]), float(r["replay"][1]))
              for r in track["edit"]),
        hold=0.0, fps=60, master_frames=v24.master_frames(track),
    )
    crossing = clock.at(v24.WINNER_CROSSES)
    plan = v24_payoff.schedule(crossing=crossing, beat=v24.BEAT,
                               seconds=v24_payoff.PAYOFF_SECONDS)
    card_from, card_to = plan["card"]
    assert 0.8 - 1e-9 <= card_from - crossing <= 1.0 + 1e-9
    assert card_to <= clock.duration + 1e-6
    # The tail exists for the card and for nothing else: the film ends within a
    # frame of it.
    assert clock.duration - card_to < 0.05


def test_the_runtime_is_inside_the_band(track):
    frames = v24.master_frames(track)
    assert frames == FRAMES
    assert RUNTIME[0] <= frames / 60.0 <= RUNTIME[1]


def test_the_historical_editions_are_untouched():
    """Nothing V24 added is visible to an edition that shipped before it."""
    from tools.sloped_short import EDITIONS, DEFAULT_EDITION

    assert DEFAULT_EDITION == "v21"
    assert EDITIONS["v20"]["cuts"] == ()
    assert EDITIONS["v211"]["cuts"] == EDITIONS["v21"]["cuts"] == ((49, 133),)
    assert EDITIONS["v22"]["cuts"] == EDITIONS["v221"]["cuts"] == ()
    for edition in ("v20", "v211", "v21", "v22", "v221"):
        assert EDITIONS[edition].get("mark") is None
        assert EDITIONS[edition].get("payoff") is None
    assert EDITIONS["v221"]["runtime"] == (26.0, 27.0)


def test_the_shipped_start_plan_still_renders_its_own_frames(replay, machine):
    """`v221.START` is not moved by anything V24 does.

    The hook lab pins that `start_plan_for` leaves every shipped frame after the
    handoff byte-identical. V24 re-splits the legs instead, so *that* claim no
    longer holds for V24's own start - and this is the test that the shipped
    plan itself is still the shipped plan.
    """
    assert v221.START.live_from == 0.2
    assert v221.START.tail_to == v221.START_HANDOFF == 6.7
    assert v221.START.cut_at == 2.05 and v221.START.resume_at == 4.0
    shipped = v221_shuffle.build_start_track(replay, machine, v221.START)
    assert [len(cut["frames"]) for cut in shipped["cuts"]] == [112, 163]

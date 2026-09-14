"""What a V24 opening has to be true of, whatever it ends up looking like.

Three families, in the order they matter:

* **the race is untouched.** V24 is a camera and an overlay. The replay is read
  and never written, seed 5432's digest and finish order are unchanged, and the
  hook's own window is made of real replay frames with output time running
  forward exactly once over each of them;
* **the opening is continuous.** The hook hands over to `v221.START`'s own first
  pose, on the frame after its last, with position, aim and field of view all
  carried through - and the shipped start plan gets its `live_from` moved and
  nothing else;
* **the arithmetic the module argues from is the arithmetic `cameras` uses.**
  `decompose` is the exact inverse of `compose`, `px_at_extent` agrees with
  `readability`'s own projection, and the bar's thresholds are ones the machine
  can actually reach.

The replay is generated output and not in the branch, so every test that needs
it skips rather than fails when it is absent. The arithmetic tests do not.
"""

from __future__ import annotations

import json
import math
import os

import pytest

from sloped import cameras, readability, v221, v221_shuffle, v24_hook as hook

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
def reference(replay, machine):
    return hook.start_reference(replay, machine)


@pytest.fixture(scope="module")
def tracks(replay, machine):
    return {
        name: hook.build_opening_track(replay, machine, plan)
        for name, plan in hook.HOOKS.items()
    }


# --- the race is untouched --------------------------------------------------


def test_the_race_is_still_seed_5432(replay):
    """V24 is a lens and a word. Neither may move a marble."""
    assert replay["seed"] == SEED
    assert replay["digest"] == DIGEST
    crossings = [event for event in replay["events"]
                 if event["kind"] == "finish_line"]
    assert [event["id"] for event in crossings] == FINISH_ORDER


def test_every_hook_window_is_made_of_real_replay_frames(replay, tracks):
    """A window edge that is not a frame is a rounding nobody looked at."""
    times = {round(float(frame["t"]), 6) for frame in replay["frames"]}
    for name, track in tracks.items():
        for cut in track["cuts"]:
            for row in cut["frames"]:
                assert round(float(row[0]), 6) in times, f"{name}: {row[0]}"


def test_output_time_runs_forward_once_over_each_replay_frame(tracks):
    """Slope one in every window, no overlap between them, no gap in output."""
    for name, track in tracks.items():
        cursor = 0.0
        seen: list[tuple[float, float]] = []
        for segment in track["edit"]:
            low, high = segment["out"]
            replay_low, replay_high = segment["replay"]
            assert low == pytest.approx(cursor, abs=1e-6), name
            assert high - low == pytest.approx(replay_high - replay_low, abs=1e-6), name
            for other_low, other_high in seen:
                assert replay_high <= other_low + 1e-9 or replay_low >= other_high - 1e-9, (
                    f"{name}: replay {replay_low}-{replay_high} is shown twice")
            seen.append((replay_low, replay_high))
            cursor = high
        assert cursor == pytest.approx(track["duration"], abs=1e-6), name


def test_the_hook_only_moves_the_start_plan_s_near_edge(replay, machine):
    """Everything else about `v221.START` is production's, to the microsecond.

    The two legs are the exception, and they are written out precisely so the
    *poses* do not change - see `start_plan_for`. What is checked here is that
    the written legs end where the shipped ones end, so only the near edge has
    moved; that the poses agree is the next test.
    """
    shipped_orbit, shipped_dolly = v221_shuffle.plan_legs(v221.START)
    for plan in hook.HOOKS.values():
        shifted = hook.start_plan_for(plan)
        assert shifted.live_from == plan.hands_over()
        for field in ("cut_at", "resume_at", "elevation", "tail_to"):
            assert getattr(shifted, field) == getattr(v221.START, field), field
        assert shifted.orbit[0][1] == shipped_orbit[0][1]
        assert shifted.orbit[1:] == shipped_orbit[1:]
        assert shifted.dolly[0][1] == shipped_dolly[0][1]
        assert shifted.dolly[1:] == shipped_dolly[1:]
        # The near end sits between where the shipped ramp started and where it
        # ends, because the hook has already flown the part it replaces.
        assert shipped_orbit[0][0] < shifted.orbit[0][0] < shipped_orbit[0][1]
        # The omission is still four whole rotor revolutions.
        assert shifted.omitted_frames() == v221.START.omitted_frames() == 116


def test_every_shipped_start_frame_the_hook_keeps_is_unchanged(replay, machine, tracks):
    """The hook replaces the first N frames of the start shot and nothing else.

    Every replay frame the shifted plan still shows is compared against the one
    `v221.START` shows at the same replay second - the tail of the first window
    as well as all 163 frames of the post-omission window. This is the test that
    `start_plan_for`'s leg arithmetic exists for: without it, moving `live_from`
    re-times the whole orbit and moves those frames by up to 4.05 layout units.
    """
    shipped = v221_shuffle.build_start_track(replay, machine, v221.START)
    for name, track in tracks.items():
        for window in (1, 2):
            want = {round(row[0], 6): row for row in shipped["cuts"][window - 1]["frames"]}
            got = {round(row[0], 6): row for row in track["cuts"][window]["frames"]}
            common = sorted(set(want) & set(got))
            assert common, (name, window)
            worst = max(math.dist(want[t][1:4], got[t][1:4]) for t in common)
            assert worst < 5e-4, (name, window, worst)
            assert all(want[t][4:] == got[t][4:] for t in common), (name, window)
        # The post-omission window keeps every frame it ever had.
        assert len(track["cuts"][2]["frames"]) == len(shipped["cuts"][1]["frames"]), name


# --- the opening is continuous ----------------------------------------------


def test_the_hook_lands_exactly_on_the_start_shot_s_first_pose(replay, machine, tracks):
    """The shared row is the next cut's row zero, to the last written digit.

    Not "close to": identical. `sloped_race_scene._place_from_track` picks a cut
    by a float comparison against a six-decimal `to`, and a frame landing on the
    boundary can resolve either way - so both readings have to be the same pose
    or the join duplicates a frame. `course_preview.preview_track` documents the
    three frames that cost before it was found.
    """
    for name, track in tracks.items():
        shared = track["cuts"][0]["frames"][-1]
        first = track["cuts"][1]["frames"][0]
        assert shared[0] == first[0], name
        assert shared[1:] == first[1:], name


def test_the_handoff_moves_the_lens_less_than_the_shots_do(tracks):
    """A join a viewer can find is one that moves more than the shots move."""
    for name, track in tracks.items():
        report = hook.join_report(track)
        assert report["shared_row_matches"], name
        assert report["fov_step"] == pytest.approx(0.0, abs=1e-6), name
        assert report["lens_step"] <= report["largest_inside_lens"], name
        assert report["aim_step"] <= max(report["largest_inside_aim"], 0.02), name


def test_no_frame_in_the_hook_moves_the_lens_faster_than_cameras_allows(tracks):
    """`cameras.MAX_CAMERA_STEP`, applied to a track `cameras` did not solve."""
    for name, track in tracks.items():
        rows = track["cuts"][0]["frames"]
        worst = max(
            math.dist(rows[index - 1][1:4], rows[index][1:4])
            for index in range(1, len(rows))
        )
        assert worst < cameras.MAX_CAMERA_STEP, f"{name}: {worst:.3f}"


def test_the_solved_track_passes_the_shipped_camera_check(replay, tracks):
    for name, track in tracks.items():
        assert cameras.check_track(track, replay) == [], name


# --- the arithmetic ---------------------------------------------------------


def test_decompose_is_the_exact_inverse_of_compose(reference):
    for bearing in (0.0, 47.5, 194.0, 270.0, 359.9):
        for elevation in (5.0, 26.0, 44.0):
            for reach in (7.0, 25.1856):
                aim = (-20.2, 42.45, -40.78)
                position = hook.compose(aim, bearing, elevation, reach, reference)
                again = hook.decompose(position, aim, reference)
                assert again[0] == pytest.approx(bearing % 360.0, abs=1e-6)
                assert again[1] == pytest.approx(elevation, abs=1e-6)
                assert again[2] == pytest.approx(reach, abs=1e-6)


def test_the_control_is_the_pose_v221_actually_opens_on(replay, machine, reference):
    """The control is read off the solved start track, not retyped from `SECTIONS`.

    The start lens is written `bearing=28, elevation=16, extent=14`; `v221.START`
    overrides two of those and `cameras.build_track` adds the first orbit and
    dolly legs before it places anything, so what comes out is bearing 194,
    elevation 30 and a reach of 25.186 - an effective extent of 15.40.
    """
    control = hook.control_hook(replay, machine)
    shipped = v221_shuffle.build_start_track(replay, machine, v221.START)
    row = shipped["cuts"][0]["frames"][0]
    bearing, elevation, reach = hook.decompose(row[1:4], row[4:7], reference)
    assert control.bearing == pytest.approx(bearing, abs=1e-3)
    assert control.elevation == pytest.approx(elevation, abs=1e-3)
    assert control.extent == pytest.approx(
        2.0 * reach * math.tan(math.radians(control.fov) * 0.5), abs=1e-3)
    assert control.bearing == pytest.approx(194.0, abs=0.05)
    assert control.extent == pytest.approx(15.40, abs=0.01)


def test_marble_pixels_depend_on_the_extent_and_not_on_the_field_of_view(
        replay, machine, reference):
    """The sizing claim the whole pass rests on, checked against the projection.

    `px = 2 * radius * height / extent` is exact at the aim plane, and the field
    of view cancels out of it. Two lenses at the same extent and different fields
    of view therefore put a racer at the *same* size - measured through
    `readability.cut_reads`, which is the arithmetic the delivered frame uses.
    """
    aim = hook.field_centroid(replay, hook.LIVE_FROM)
    sizes = []
    for fov in (24.0, 34.0, 48.0):
        reach = 0.5 * 8.2 / math.tan(math.radians(fov) * 0.5)
        camera = hook.compose(aim, 204.0, 26.0, reach, reference)
        cut = {"frames": [[hook.LIVE_FROM, *camera, *aim, fov]]}
        row = readability.cut_reads(cut, replay, stride=1)[0]
        sizes.append(readability._median(sorted(row["diameters"])))
    assert max(sizes) - min(sizes) < 1.0, sizes
    assert sizes[1] == pytest.approx(hook.px_at_extent(8.2), rel=0.08)


def test_the_separation_bar_would_have_been_impossible(replay):
    """The bays are 1.105 diameters apart in the geometry, so 1.15 was unreachable.

    Kept as a test rather than only as a comment: the first version of this
    module carried a `MIN_SEPARATION` of 1.15 that no camera could ever have
    passed, and the number that rules it out is the machine's, not the lens's.
    """
    from sloped import layout

    span = hook.field_span(replay, hook.LIVE_FROM)
    pitch = span / 7.0
    assert pitch / (2.0 * layout.MARBLE_RADIUS) == pytest.approx(1.105, abs=0.01)


def test_disc_visibility_sees_a_stack_that_spacing_calls_fine():
    """A near racer standing in front of a far one, which spacing cannot report."""
    frame_zero = {
        "positions": {0: [500.0, 900.0, 200.0], 1: [560.0, 900.0, 260.0]},
        "bbox": (400.0, 800.0, 660.0, 1000.0),
    }
    visible = hook.disc_visibility(frame_zero)
    # The far racer keeps only what the near one is not standing on.
    assert visible["racers"][1] < 0.75
    assert visible["racers"][0] == pytest.approx(1.0, abs=1e-6)
    assert visible["worst"] == visible["racers"][1]


# --- the opening does what the brief asks ------------------------------------


def test_every_variant_holds_all_eight_racers_large_at_frame_zero(replay, tracks):
    for name, track in tracks.items():
        report = hook.first_frame_report(track, replay)
        assert report["racers"] == 8, name
        assert report["median_px"] >= hook.MIN_HOOK_PX, (name, report["median_px"])
        assert report["worst_disc"] >= hook.MIN_VISIBLE_DISC, name
        assert report["off_centre"] <= hook.MAX_OFF_CENTRE, name
        assert report["off_centre_x"] <= hook.MAX_OFF_CENTRE_X, name
        assert report["ink"] >= hook.MIN_INK, (name, report["ink"])


def test_every_variant_is_a_long_way_past_the_shipped_opening(replay, machine, tracks):
    """The control is the thing to beat, and it is measured rather than quoted."""
    control = hook.build_opening_track(replay, machine, hook.control_hook(replay, machine))
    shipped = hook.first_frame_report(control, replay)
    assert shipped["median_px"] == pytest.approx(81.3, abs=0.2)
    assert shipped["ink"] == pytest.approx(0.0201, abs=0.0005)
    for name, track in tracks.items():
        report = hook.first_frame_report(track, replay)
        assert report["median_px"] > shipped["median_px"] * 1.5, name
        assert report["ink"] > shipped["ink"] * 2.0, name


def test_something_moves_inside_the_first_third_of_a_second(replay, machine, tracks):
    """The premise arrives before a thumb does.

    The release paddles first stir at replay 0.3167 and every variant opens on
    0.200, so the mechanism moves 0.117 s into the film - and it does so because
    the held frame and the course preview are gone, not because anything was
    sped up.
    """
    for name, plan in hook.HOOKS.items():
        report = hook.motion_report(replay, plan, tracks[name])
        assert report["mechanism"] == pytest.approx(0.1167, abs=0.02), name
        assert report["subject_first"] <= hook.MAX_FIRST_MOTION, name
        # The gate is the rate-limiting instrument, not the gate's own threshold:
        # a racer resting in a shut bay creeps well under the bar.
        assert report["creep_px"] < hook.MOTION_PX, name


def test_the_mark_is_pick_a_color_and_fits_the_frame(replay):
    """Twelve glyphs, not eight - which is why it is not `overlays.pick_one`'s 150."""
    assert hook.HOOK_TEXT == "PICK A COLOR"
    width, cap = hook.text_box()
    assert width < hook.WIDTH * 0.86, width
    # At 150, `overlays.pick_one`'s own size, the same line runs off the frame.
    assert hook.text_box(size=150)[0] > hook.WIDTH
    assert cap * hook.PHONE_HEIGHT / hook.HEIGHT >= 16.0, cap

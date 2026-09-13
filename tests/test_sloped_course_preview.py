"""The V22 course preview: the flight, what it can see, and what it hands over.

These are tests of a camera path, so they are tests of arithmetic over it rather
than of pictures. They fall into four groups:

* the corridor is the course flattened, and still begins and ends on the two
  nodes the shot has to be over
* the flight is watchable: its step, its lateral step, its turn rate and its
  duration are all inside the bar `sloped.course_preview` sets, and the bar is
  the one `check_preview` applies
* the shot does its job: every landmark the brief names is in frame at some
  point, the gaze never enters the ground, and the lens never stands in the
  course
* the track it writes is the one the renderer reads, including the boundary
  overlap that a rendered clip proved was needed

The expensive part is `terrain.terrain_config`, which builds the bench index
from all seven runs, and the solve itself, which walks the terrain forty times
a frame in the lift solver. Both are module-scoped fixtures so the whole file
costs one of each.
"""

from __future__ import annotations

import json
import math
import os
import sys

import pytest

sys.path.insert(0, os.getcwd())

from sloped import course_preview as preview
from sloped import layout, terrain


@pytest.fixture(scope="module")
def cfg():
    return terrain.terrain_config()


@pytest.fixture(scope="module")
def line():
    return preview.course_line()


@pytest.fixture(scope="module")
def spine(line):
    return preview.corridor(line)


@pytest.fixture(scope="module")
def solved(line, spine, cfg):
    return preview.build_preview(preview.PREVIEW, line=line, spine=spine, cfg=cfg)


@pytest.fixture(scope="module")
def report(solved):
    return preview.path_report(solved)


# --- the course line and the corridor ------------------------------------


def test_course_line_runs_start_to_finish(line):
    """It begins on the start node and ends on the finish node, exactly."""
    assert line.points[0] == pytest.approx(layout.NODES["start"], abs=1e-9)
    assert line.points[-1] == pytest.approx(layout.NODES["finish"], abs=1e-9)
    # Long enough to be the whole course and not one branch of it. The seven
    # drawn runs total 237 units of channel; this is shorter because the two
    # branch lobes are replaced by the chord between them.
    assert 175.0 < line.length < 200.0


def test_course_line_is_finely_and_near_evenly_sampled(line):
    """Fine enough to be a curve, and even enough for a sigma in layout units.

    `corridor` converts `CORRIDOR_SIGMA` from layout units to samples with one
    division by the mean spacing, which is only meaningful if the spacing is
    about constant.

    Two spans are not, and they are worth recording rather than repairing.
    `resample` places its samples at equal arc length along the *input*
    polyline, so the straight-line span between two of them is a chord and is
    shortest where the input bends hardest between them - and the course line
    concatenates the drawn runs, where the branch midline meets leg 3 with a
    0.78-unit step and the sprint with a 0.35-unit one, because the fork's own
    lead runs are not part of the drawn table. The corridor's blur is fifty
    layout units wide and erases both.
    """
    spans = [
        math.dist(line.points[index + 1], line.points[index])
        for index in range(len(line.points) - 1)
    ]
    # Finer than the channel is wide, so the corridor is a curve not a chain.
    assert max(spans) < layout.HERO_CLEAR_WIDTH
    median = sorted(spans)[len(spans) // 2]
    off = [value for value in spans if abs(value - median) > 0.01 * median]
    assert len(off) <= 4, f"{len(off)} spans are more than 1% off {median:.4f}"
    assert min(spans) > 0.6 * median, "a span collapsed, not just shortened"


def test_branch_midline_runs_between_the_lobes():
    """Every sample of it is inside the pair it came from, on both axes."""
    from sloped.pathing import resample
    from sloped.track import TrackRun

    blue = resample(TrackRun("blue").path, 118)
    orange = resample(TrackRun("orange").path, 118)
    mid = preview.branch_midline(118)
    assert len(mid) == 118
    for index, point in enumerate(mid):
        for axis in (0, 2):
            low = min(blue[index][axis], orange[index][axis])
            high = max(blue[index][axis], orange[index][axis])
            assert low - 1e-9 <= point[axis] <= high + 1e-9
    # And the pair really are far apart somewhere, or the test proves nothing.
    assert max(math.dist(blue[i], orange[i]) for i in range(118)) > 25.0


def test_corridor_pins_both_ends(line, spine):
    """The blur must not drag the two points the shot is built around."""
    assert spine.points[0] == pytest.approx(line.points[0], abs=1e-6)
    assert spine.points[-1] == pytest.approx(line.points[-1], abs=1e-6)


def test_corridor_flattens_the_zig_zag(line, spine):
    """The whole point of it: one curve instead of six.

    The drawn course swings about 350 degrees of plan heading between its
    sections. A camera that took its facing from that would rotate 175 degrees a
    second over a two-second shot.
    """

    def swing(target):
        headings = [
            math.degrees(
                math.atan2(
                    target.tangent(target.length * step / 60.0)[0],
                    target.tangent(target.length * step / 60.0)[2],
                )
            )
            for step in range(61)
        ]
        return sum(
            abs((headings[index + 1] - headings[index] + 180.0) % 360.0 - 180.0)
            for index in range(60)
        )

    assert swing(line) > 250.0, "the course is supposed to zig-zag"
    assert swing(spine) < 40.0, "the corridor is supposed not to"


def test_corridor_stays_near_the_track(line, spine):
    """Flattened, but not into a line that has left the course behind."""
    strays = [line.nearest(spine.at(spine.length * step / 60.0)) for step in range(61)]
    assert max(strays) < 14.0
    assert sum(strays) / len(strays) < 7.0


def test_line_extrapolates_past_both_ends(spine):
    """`Line.at` off the end continues straight, which is where the camera ends."""
    step = spine.at(-20.0)
    tangent = spine.tangent(0.0)
    expected = tuple(spine.points[0][axis] - tangent[axis] * 20.0 for axis in range(3))
    assert step == pytest.approx(expected, abs=1e-6)


# --- the flight is watchable ---------------------------------------------


def test_duration_is_a_short_not_a_cinematic(report):
    low, high = preview.DURATION_RANGE
    assert low <= report["duration"] <= high


def test_the_solved_flight_passes_its_own_check(report):
    assert preview.check_preview(report) == []


def test_motion_is_inside_the_bar(report):
    assert report["max_step"] <= preview.MAX_STEP
    assert report["max_across_step"] <= preview.MAX_ACROSS_STEP
    assert report["max_rise_step"] <= preview.MAX_RISE_STEP
    assert report["max_turn"] <= preview.MAX_TURN
    assert report["max_yaw"] <= preview.MAX_YAW
    assert report["max_pitch"] <= preview.MAX_PITCH


def test_most_of_the_motion_is_a_dolly(solved, report):
    """The shot's defence: it moves along its own gaze, not across it.

    A camera that spent its travel sideways would be a pan however small each
    step was, and the brief's "not motion-sickness inducing" is about that and
    not about the total.
    """
    frames = solved["frames"]
    along = 0.0
    across = 0.0
    for index in range(1, len(frames)):
        forward = preview._unit(
            tuple(
                frames[index]["aim"][axis] - frames[index]["position"][axis]
                for axis in range(3)
            )
        )
        right = preview._unit((-forward[2], 0.0, forward[0]))
        delta = tuple(
            frames[index]["position"][axis] - frames[index - 1]["position"][axis]
            for axis in range(3)
        )
        along += abs(sum(delta[axis] * forward[axis] for axis in range(3)))
        across += abs(sum(delta[axis] * right[axis] for axis in range(3)))
    # Measured on the shipped profile: 81.4 units along the gaze against 15.0
    # across it, a ratio of 5.4. The bar is 4 so that a change to `sway` - which
    # is what almost all the sideways travel is - has to be a deliberate one.
    assert along > 4.0 * across


def test_the_gaze_never_approaches_vertical(report):
    """`look_at(aim, Vector3.UP)` has no answer straight down."""
    assert report["min_gaze_to_vertical"] >= preview.MIN_GAZE_TO_VERTICAL


def test_the_flight_starts_and_stops(solved):
    """Eased at both ends: the first and last steps are well under the middle."""
    frames = solved["frames"]
    steps = [
        math.dist(frames[index]["position"], frames[index - 1]["position"])
        for index in range(1, len(frames))
    ]
    middle = sorted(steps)[len(steps) // 2]
    assert steps[0] < 0.75 * middle
    assert steps[-1] < 0.75 * middle


def test_lift_has_no_step_in_it(solved):
    """The ground reaches the flight only through a dilated, blurred envelope.

    Taking `max(corridor, ground)` per frame instead moved the lens 3.7 layout
    units in one frame over the crest above the start. This is the regression
    test for that: the second difference of the lens's height is small
    everywhere, which a terrain-following path's would not be.
    """
    heights = [frame["position"][1] for frame in solved["frames"]]
    curvature = [
        abs(heights[index + 1] - 2.0 * heights[index] + heights[index - 1])
        for index in range(1, len(heights) - 1)
    ]
    assert max(curvature) < 0.05


# --- the shot does its job ------------------------------------------------


def test_every_landmark_is_seen(report):
    missing = [name for name, entry in report["landmarks"].items() if not entry["seen"]]
    assert missing == []


def test_the_gaze_passes_the_landmarks_in_reverse_race_order(solved):
    """The preview travels backwards, so the finish comes first and the start last.

    The claim is about the *gaze*, which is what the named windows are cut from,
    and not about when each landmark first enters the frustum. Those are not the
    same order and should not be: a landmark off to one side of the corridor -
    the branch midpoint, or leg 1's eastern apex - comes into frame later than
    one the flight passes directly over, however far up-course it is.
    """
    names = [name for name, _, _ in preview._segments(solved)]
    assert names == [name for name, _ in reversed(preview.LANDMARKS)]


def test_the_shot_opens_on_the_finish_and_closes_on_the_start(report):
    opening = math.dist(report["start_aim"], layout.NODES["finish"])
    closing = math.dist(report["end_aim"], layout.NODES["start"])
    assert opening < 12.0, "the shot does not begin looking at the finish arena"
    assert closing < 4.0, "the shot does not end looking at the start machine"


def test_the_handoff_is_behind_the_racers(solved, report):
    """Above the start, up-course of it, and looking the way the race will go.

    Three claims, each measured. Up-course is the one that matters: a camera
    down-course of the start is a camera in front of the field.
    """
    position = report["end_position"]
    aim = report["end_aim"]
    start = layout.NODES["start"]
    launch = preview.Line([point for point in __import__(
        "sloped.track", fromlist=["TrackRun"]).TrackRun("launch").path])
    forward = launch.tangent(0.0)

    assert position[1] > start[1] + 8.0, "the handoff is not elevated"
    behind = sum(
        (position[axis] - start[axis]) * forward[axis] for axis in (0, 2)
    )
    assert behind < -6.0, "the handoff is not up-course of the start"
    gaze = tuple(aim[axis] - position[axis] for axis in range(3))
    assert sum(gaze[axis] * forward[axis] for axis in (0, 2)) > 0.0, (
        "the handoff does not look down-course"
    )
    # Elevated, but a camera and not a plan view.
    assert 20.0 < report["end_elevation"] < 50.0
    assert 15.0 < report["end_reach"] < 40.0


def test_the_sight_line_clears_the_ground(report):
    assert report["min_sight_clearance"] >= preview.SIGHT_MARGIN


def test_the_lens_never_stands_in_the_course(solved, cfg):
    """The one check that needs the drawn geometry rather than the terrain."""
    from sloped import sightlines
    from sloped.course import sloped_course

    machine = sloped_course(routes="both")
    bundle = sightlines.Bundle(
        sightlines.course_solids(machine, lambda x, z: terrain.height(x, z, cfg))
    )
    report = preview.path_report(solved, bundle=bundle, stride=4)
    assert report["min_lens_clearance"] >= preview.LENS_MARGIN
    assert report["centre_blocked_frames"] == 0


def test_a_reasonable_share_of_the_ribbon_is_in_frame(report):
    assert report["mean_visible_fraction"] > 0.30


def test_visibility_uses_the_portrait_aspect():
    """A 1080x1920 frame is narrow, and a frustum test that forgets it lies.

    A point 20 units to the side at 40 ahead is inside a square frame at 48
    degrees and outside a portrait one, and the whole bearing argument in
    `sloped.cameras` rests on the difference.
    """
    position = (0.0, 0.0, 0.0)
    aim = (0.0, 0.0, 40.0)
    point = (14.0, 0.0, 40.0)
    assert preview._visible(position, aim, 48.0, point, 1.0)
    assert not preview._visible(position, aim, 48.0, point, preview.ASPECT)


def test_nothing_behind_the_lens_counts_as_visible():
    assert not preview._visible((0.0, 0.0, 0.0), (0.0, 0.0, 10.0), 48.0, (0.0, 0.0, -5.0),
                                preview.ASPECT)


# --- the track the renderer reads ----------------------------------------


def test_track_is_in_the_renderers_format(solved):
    track = preview.preview_track(solved, seed=5432)
    assert track["units"] == "layout"
    assert track["fps"] == preview.PREVIEW.fps
    assert track["edited"] is False
    assert track["cuts"], "a track with no cuts draws nothing"
    for cut in track["cuts"]:
        assert {"name", "from", "to", "fov", "frames"} <= set(cut)
        for row in cut["frames"]:
            assert len(row) == 8, "a row is t, position, aim, fov"


def test_every_frame_is_in_exactly_one_window(solved):
    """The cuts tile the shot: no frame is missed and none is ambiguous.

    Windows overlap by their shared boundary row on purpose - see
    `preview_track` - so the count of rows is the frame count plus one per
    boundary, and the *windows* themselves still tile.
    """
    track = preview.preview_track(solved)
    frames = solved["frames"]
    cuts = track["cuts"]
    assert cuts[0]["from"] == pytest.approx(frames[0]["t"])
    assert cuts[-1]["to"] == pytest.approx(frames[-1]["t"])
    for index in range(len(cuts) - 1):
        assert cuts[index]["to"] == pytest.approx(cuts[index + 1]["from"]), (
            "the windows do not tile"
        )
    rows = sum(len(cut["frames"]) for cut in cuts)
    assert rows == len(frames) + len(cuts) - 1


def test_cut_boundaries_carry_their_successors_first_row(solved):
    """The fix for three duplicated frames in the first rendered clip.

    `sloped_race_scene._place_from_track` picks the first cut whose `to` is at
    or after the wanted second and then indexes from that cut's own first row.
    At a boundary the renderer's `index / fps` and this file's six-decimal `to`
    disagree in the last bits, so the frame can land in either cut - and it must
    be drawn with the same pose whichever it lands in.
    """
    track = preview.preview_track(solved)
    cuts = track["cuts"]
    for index in range(len(cuts) - 1):
        last = cuts[index]["frames"][-1]
        first = cuts[index + 1]["frames"][0]
        assert last == first, "the boundary row is not shared"


def test_the_track_rows_are_the_solved_flight(solved):
    """Every frame appears once in order, at the pose the solver gave it."""
    track = preview.preview_track(solved)
    seen: dict[float, list[float]] = {}
    for cut in track["cuts"]:
        for row in cut["frames"]:
            if row[0] in seen:
                assert seen[row[0]] == row
            seen[row[0]] = row
    assert len(seen) == len(solved["frames"])
    for frame in solved["frames"]:
        row = seen[round(frame["t"], 6)]
        assert row[1:4] == pytest.approx(frame["position"], abs=5e-4)
        assert row[4:7] == pytest.approx(frame["aim"], abs=5e-4)


def test_the_edit_map_is_the_identity(solved):
    """Output time is replay time here, so `replay_at` must be a no-op."""
    track = preview.preview_track(solved)
    for segment in track["edit"]:
        assert segment["out"] == segment["replay"]


def test_written_track_round_trips(solved, tmp_path):
    track = preview.preview_track(solved, seed=5432)
    path = preview.write_track(track, str(tmp_path / "cameras.json"))
    with open(path, "r", encoding="utf-8") as handle:
        assert json.load(handle) == track


# --- the frozen replay ----------------------------------------------------


def _fake_replay() -> dict:
    frame = {"t": 0.0, "marbles": [{"id": 0, "p": [1.0, 2.0, 3.0]}],
             "actuators": {"start.paddle0": {"p": [0.0, 0.0, 0.0]}}}
    return {
        "format": "marble3d.replay", "version": 1, "mode": "marble3d", "seed": 5432,
        "physics_hz": 480, "replay_fps": 60,
        "units": {"render_scale": 0.57}, "marbles": [{"id": 0, "radius": 0.5}],
        "frames": [frame, {**frame, "t": 1.0, "marbles": [{"id": 0, "p": [9.0, 9.0, 9.0]}]}],
        "events": [{"kind": "finish_line", "t": 20.0}],
        "digest": "deadbeef", "summary": {"winner": 3},
    }


def test_frozen_replay_holds_frame_zero():
    frozen = preview.frozen_replay(_fake_replay(), 2.0, 60)
    assert len(frozen["frames"]) == 121
    for index, frame in enumerate(frozen["frames"]):
        assert frame["t"] == pytest.approx(index / 60.0, abs=1e-6)
        assert frame["marbles"] == _fake_replay()["frames"][0]["marbles"]
        assert frame["actuators"] == _fake_replay()["frames"][0]["actuators"]


def test_frozen_replay_keeps_what_the_scene_reads():
    frozen = preview.frozen_replay(_fake_replay(), 1.0, 60)
    assert frozen["mode"] == "marble3d"
    assert frozen["units"]["render_scale"] == 0.57
    assert frozen["marbles"] == [{"id": 0, "radius": 0.5}]


def test_frozen_replay_does_not_claim_to_be_a_record():
    """No digest and no events: it is a pose, not a physical record."""
    frozen = preview.frozen_replay(_fake_replay(), 1.0, 60)
    assert "digest" not in frozen
    assert "summary" not in frozen
    assert frozen["events"] == []
    assert "not a physical record" in frozen["note"].lower()


# --- the knobs ------------------------------------------------------------


def test_an_explicit_end_pose_is_reached_and_the_join_is_smooth(line, spine, cfg):
    """What integration will use: hand it the chase camera's own first pose.

    The blend has to land on it exactly and must not put a step in the path on
    the way, or the preview has traded one hard cut for another.
    """
    target = ((-28.0, 54.0, -48.0), (-16.0, 40.0, -34.0))
    spec = preview.Preview(end_pose=target)
    solved = preview.build_preview(spec, line=line, spine=spine, cfg=cfg)
    frames = solved["frames"]
    assert frames[-1]["position"] == pytest.approx(target[0], abs=1e-6)
    assert frames[-1]["aim"] == pytest.approx(target[1], abs=1e-6)
    report = preview.path_report(solved, stride=3)
    assert report["max_step"] <= preview.MAX_STEP
    assert report["max_turn"] <= preview.MAX_TURN


def test_the_end_blend_leaves_the_front_of_the_shot_alone(line, spine, cfg):
    plain = preview.build_preview(preview.Preview(), line=line, spine=spine, cfg=cfg)
    blended = preview.build_preview(
        preview.Preview(end_pose=((-28.0, 54.0, -48.0), (-16.0, 40.0, -34.0))),
        line=line, spine=spine, cfg=cfg,
    )
    cut = 1.0 - preview.Preview().end_blend
    for a, b in zip(plain["frames"], blended["frames"]):
        if a["u"] < cut:
            assert a["position"] == b["position"]
            assert a["aim"] == b["aim"]


def test_the_duration_is_a_knob_and_the_check_holds_it(line, spine, cfg):
    long = preview.Preview(seconds=4.0)
    solved = preview.build_preview(long, line=line, spine=spine, cfg=cfg)
    problems = preview.check_preview(preview.path_report(solved, stride=6))
    assert any("outside the brief" in problem for problem in problems)


def test_ramp_passes_through_every_knot():
    knots = (3.0, 9.0, 4.0, 7.0, 1.0)
    for index, value in enumerate(knots):
        assert preview._ramp(index / (len(knots) - 1), knots) == pytest.approx(value)
    assert preview._ramp(0.37, (5.0,)) == 5.0


def test_ramp_has_no_corner_at_a_knot():
    knots = (14.0, 22.0, 27.0, 24.0, 10.0)
    samples = [preview._ramp(step / 400.0, knots) for step in range(401)]
    second = [
        abs(samples[index + 1] - 2.0 * samples[index] + samples[index - 1])
        for index in range(1, len(samples) - 1)
    ]
    assert max(second) < 0.01


def test_envelope_is_smooth_and_never_undershoots():
    """Both halves of its contract, on a series with one spike in it."""
    raw = [0.0] * 40 + [6.0] + [0.0] * 40
    out = preview._envelope(raw, 8, 4.0)
    assert all(out[index] >= raw[index] - 1e-9 for index in range(len(raw)))
    second = [
        abs(out[index + 1] - 2.0 * out[index] + out[index - 1])
        for index in range(1, len(out) - 1)
    ]
    assert max(second) < 0.2

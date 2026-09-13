"""The V22.1 breathing course preview: its clock, its warp and its handoff.

Three of these tests are the ones that matter, and they are the three claims the
module makes that are not opinions:

* that a flat density reproduces `sloped.course_preview` exactly, so substituting
  `_ease` is reuse of the shipped solver and not a fork of it;
* that the paced flight's gaze never backs up the course, which is the failure
  mode breathing introduces and nothing else in the package would catch;
* that the handoff lands on the V22 race camera's own first frame in pose, aim,
  velocity, gaze rate **and field of view** - the last of which V22 does not.

The solves are module-scoped fixtures: one costs about half a second, and the
terrain and corridor behind them cost more.
"""

from __future__ import annotations

import json
import math
from dataclasses import replace
from pathlib import Path

import pytest

from sloped import course_preview as cp
from sloped import terrain, v22
from sloped import v221_preview as v221

OUT = Path("output") / "sloped_race_v1"
RACE_TRACK = OUT / "cameras_v22_5432.json"

needs_track = pytest.mark.skipif(
    not RACE_TRACK.is_file(), reason="the V22 race camera track is not in this tree"
)


# --- fixtures --------------------------------------------------------------


@pytest.fixture(scope="module")
def cfg():
    return terrain.terrain_config()


@pytest.fixture(scope="module")
def line():
    return cp.course_line()


@pytest.fixture(scope="module")
def spine(line):
    return cp.corridor(line)


@pytest.fixture(scope="module")
def spec():
    return v221.preview_spec(v22.PREVIEW)


@pytest.fixture(scope="module")
def rail():
    if not RACE_TRACK.is_file():
        pytest.skip("the V22 race camera track is not in this tree")
    track = json.loads(RACE_TRACK.read_text(encoding="utf-8"))
    return v221.Rail(track["cuts"][0]["frames"])


@pytest.fixture(scope="module")
def solved(spec, rail, line, spine, cfg):
    return v221.build(
        v221.Pacing(seconds=3.5, name="preview_35"),
        spec,
        rail=rail,
        land="rail",
        line=line,
        spine=spine,
        cfg=cfg,
    )


@pytest.fixture(scope="module")
def report(solved, rail):
    out = v221.pace_report(solved, bundle=None, rail=rail, stride=1)
    out["problems"] = v221.check_v221(out)
    return out


# --- the clock -------------------------------------------------------------


def test_the_clock_is_a_monotone_bijection():
    """`q_of_u` inverts `u_of_q`, which is what lets the ramps be warped."""
    pace = v221._Pace(v221._density_of(v221.Pacing(), {"fork": 0.4}), 2048)
    previous = -1.0
    for index in range(401):
        q = index / 400.0
        u = pace.u_of_q(q)
        assert u > previous
        previous = u
        assert pace.q_of_u(u) == pytest.approx(q, abs=2e-3)
    assert pace.u_of_q(0.0) == 0.0
    assert pace.u_of_q(1.0) == pytest.approx(1.0, abs=1e-12)


def test_a_flat_density_is_a_straight_line():
    """With nothing to breathe for, the clock is the identity."""
    flat = v221.Pacing(dwell={}, ease_in=0.0, ease_out=0.0)
    pace = v221._Pace(v221._density_of(flat, {}), 2048)
    for index in range(101):
        u = index / 100.0
        assert pace.q_of_u(u) == pytest.approx(u, abs=1e-9)


def test_a_flat_pace_reproduces_the_shipped_solver(spec, line, spine, cfg):
    """The substitution is reuse, not a fork.

    Driven by the same progress curve `course_preview._ease` would have produced,
    this module's build and the shipped one agree frame for frame. That is what
    licenses every other claim here: the picture is V22's picture on a different
    clock, not a second solver that happens to look similar.
    """
    seconds, fps = 2.0, 60
    flat = v221.Pacing(
        seconds=seconds, fps=fps, dwell={}, ease_in=0.0, ease_out=0.0, knots=200
    )
    pace = v221._Pace(v221._density_of(flat, {}), 4096)

    shipped_ease = cp._ease

    class _Identity:
        """The clock `course_preview`'s own default ease describes.

        `shipped_ease` is captured before the substitution: reading `cp._ease`
        inside the context would be reading the substitute, which recurses.
        """

        integral = 1.0

        @staticmethod
        def q_of_u(u):
            return shipped_ease(u, spec.ease)

    with v221._paced(_Identity()):
        mine = cp.build_preview(
            replace(spec, seconds=seconds, fps=fps, end_pose=None),
            line=line, spine=spine, cfg=cfg,
        )
    theirs = cp.build_preview(
        replace(spec, seconds=seconds, fps=fps, end_pose=None),
        line=line, spine=spine, cfg=cfg,
    )
    assert len(mine["frames"]) == len(theirs["frames"])
    for a, b in zip(mine["frames"], theirs["frames"]):
        assert a["position"] == pytest.approx(b["position"], abs=1e-12)
        assert a["aim"] == pytest.approx(b["aim"], abs=1e-12)
    # And the pacing machinery itself is capable of being that clock.
    assert pace.q_of_u(0.5) == pytest.approx(0.5, abs=1e-9)


def test_the_dwell_slows_the_flight_where_the_landmarks_are(solved):
    """The shot is slowest at the ends and at the landmarks, fastest between.

    Measured as the travel per frame, which is the pacing itself rather than the
    camera step - the lift and the sway add to the step and would blur this.
    """
    frames = solved["frames"]
    centres = solved["pace"]["centres"]
    rate = [
        frames[index - 1]["cam_station"] - frames[index]["cam_station"]
        for index in range(1, len(frames))
    ]
    mean = sum(rate) / len(rate)
    clock = solved["pace"]["clock"]
    for name in ("fork", "obstacle", "branches"):
        at = int(round(clock.u_of_q(centres[name]) * (len(rate) - 1)))
        assert rate[at] < mean, f"{name} is not slower than the shot's average"
    assert rate[0] < 0.6 * mean, "the shot does not accelerate out of the finish"
    assert rate[-1] < 0.6 * mean, "the shot does not decelerate into the start"
    # And it never stops: a stall is what a paused flyover looks like.
    assert min(rate) > 0.15 * mean


def test_breathing_is_bought_from_the_straights(spec, rail, line, spine, cfg):
    """Doubling the density integral doubles the rate over generic track.

    This is the trade the duration choice rests on, so it is pinned rather than
    left as a claim in a docstring.
    """
    reports = {}
    for seconds in (2.8, 3.5):
        solved = v221.build(
            v221.Pacing(seconds=seconds), spec, rail=rail, land="rail",
            line=line, spine=spine, cfg=cfg,
        )
        reports[seconds] = v221.pace_report(solved, rail=rail, stride=4)
    assert reports[2.8]["pace_integral"] == pytest.approx(
        reports[3.5]["pace_integral"], abs=1e-6
    ), "the two candidates are meant to differ only in the clock"
    assert reports[2.8]["flat_units_per_frame"] > v221.V22_PEAK_STEP
    assert reports[3.5]["flat_units_per_frame"] < v221.V22_PEAK_STEP


# --- the warp --------------------------------------------------------------


def test_the_warp_pins_both_ends_of_every_ramp(spec):
    """`cam_from` and `cam_to` are built from the lead's end knots, so they must
    survive the warp exactly or the flight starts and stops somewhere else."""
    pace = v221._Pace(v221._density_of(v221.Pacing(), {"fork": 0.4}), 2048)
    warped = v221.warp(spec, v221.Pacing(), pace)
    assert warped.lead[0] == pytest.approx(spec.lead[0], abs=1e-9)
    assert warped.lead[-1] == pytest.approx(spec.lead[-1], abs=1e-9)
    assert warped.lift[0] == pytest.approx(spec.lift[0], abs=1e-9)
    assert warped.lift[-1] == pytest.approx(spec.lift[-1], abs=1e-9)


def test_the_warped_ramps_stand_in_for_the_authored_ones(spec):
    """Resampling onto 49 knots has to be a re-reading, not a redesign."""
    pacing = v221.Pacing()
    pace = v221._Pace(v221._density_of(pacing, {"fork": 0.4}), 2048)
    warped = v221.warp(spec, pacing, pace)
    worst = v221.warp_error(spec, warped, pace)
    assert max(worst.values()) < 0.05, worst


def test_the_composition_follows_the_course_and_not_the_clock(solved, spec):
    """The lift at the handoff is the authored tail, not the middle of the ramp.

    This is the failure the warp exists to prevent: unwarped, a breathing flight
    is only three quarters down the corridor at `u = 0.9` and would still be
    carrying the ramp's high middle when it arrives over the start machine.
    """
    warped = solved["spec"]
    assert cp._ramp(1.0, warped.lift) == pytest.approx(spec.lift[-1], abs=1e-6)
    clock = solved["pace"]["clock"]
    late = clock.q_of_u(0.9)
    # The arrival crawls, so by nine tenths of the clock the flight is already
    # 95 per cent of the way down the corridor - the paced clock *leads* the
    # uniform one late on, not lags it.
    assert late > 0.94
    assert cp._ramp(0.9, warped.lift) == pytest.approx(
        cp._ramp(late, spec.lift), abs=0.05
    )
    # Unwarped it would be carrying the ramp's descent three units too high.
    assert cp._ramp(0.9, spec.lift) - cp._ramp(0.9, warped.lift) > 2.5


# --- what breathing puts at risk ------------------------------------------


def test_the_gaze_never_backs_up_the_course(report):
    """The aim leads the lens by a ramp; where the lens slows hard the ramp can
    outrun it, and the gaze would visibly reverse. Nothing in `check_preview`
    looks for it because a uniform flight cannot do it."""
    assert report["aim_monotone"], report["max_aim_rise"]
    assert report["max_aim_rise"] < 0.0


def test_the_shot_actually_breathes(report):
    """A uniform flight has a station-rate ratio of about one."""
    assert report["station_rate_ratio"] > 3.0


def test_the_recommended_candidate_passes_its_own_bar(report):
    assert report["problems"] == []


def test_every_landmark_is_in_frame(report):
    missing = sorted(n for n, e in report["landmarks"].items() if not e["seen"])
    assert missing == []


def test_the_high_priority_landmarks_get_their_screen_time(report):
    subject = report["subject_seconds"]
    for label, (floor, parts) in v221.SUBJECT_TIERS.items():
        assert sum(subject[part] for part in parts) >= floor, label


def test_low_priority_track_does_not_outrank_high(report):
    subject = report["subject_seconds"]
    leanest = min(
        sum(subject[part] for part in parts)
        for floor, parts in v221.SUBJECT_TIERS.values()
        if floor >= 0.42
    )
    for name in v221.LOW_PRIORITY:
        assert subject[name] <= leanest


# --- the handoff -----------------------------------------------------------


@needs_track
def test_the_rail_continues_the_orbit_backwards(rail):
    """Frame -1 is one race-camera step the other side of frame 0, on the arc.

    A Cartesian reflection would put it the same distance away but bending the
    wrong way round the machine; the cylindrical one keeps the radius.
    """
    before, at, after = rail.pose(-1), rail.pose(0), rail.pose(1)
    back = math.dist(before[0], at[0])
    forward = math.dist(at[0], after[0])
    assert back == pytest.approx(forward, rel=0.02)
    # The start orbit spirals in - the radius falls 0.034 a frame - so the
    # continuation is checked for *symmetry* about frame zero rather than for a
    # constant radius. A Cartesian reflection gets this part right too; what it
    # gets wrong is the bearing, which is why the arc is checked above.
    radius = [
        math.hypot(pose[0][0] - pose[1][0], pose[0][2] - pose[1][2])
        for pose in (before, at, after)
    ]
    assert radius[0] - radius[1] == pytest.approx(radius[1] - radius[2], rel=1e-6)
    assert radius[0] > radius[1] > radius[2]


@needs_track
def test_the_preview_lands_on_the_race_cameras_first_frame(report):
    handoff = report["handoff"]
    assert handoff["pose_delta"] == pytest.approx(0.0, abs=1e-6)
    assert handoff["aim_delta"] == pytest.approx(0.0, abs=1e-6)
    assert handoff["fov_delta"] == pytest.approx(0.0, abs=1e-6)


@needs_track
def test_the_preview_arrives_at_the_speed_the_race_leaves_at(report):
    """Near-zero *residual* motion, which is not the same as near-zero motion.

    The chase camera's own first frame is already moving 0.169 layout units; a
    preview that arrives at rest hands over with a step of exactly that. The
    residual measured here is the one a viewer could see.
    """
    handoff = report["handoff"]
    assert abs(handoff["velocity_residual"]) < 0.005
    assert abs(handoff["turn_residual"]) < 0.005
    assert handoff["last_step"] == pytest.approx(handoff["race_first_step"], abs=0.005)


@needs_track
def test_the_settle_eases_and_never_stops(report):
    """The tail is a settle, not a stop-and-restart. See `RAIL_HORIZON`."""
    handoff = report["handoff"]
    assert handoff["tail_dip"] > 0.03
    assert handoff["max_tail_step"] < 0.25


@needs_track
def test_a_still_landing_arrives_at_rest_and_v22s_fov(spec, rail, line, spine, cfg):
    """The other mode is V22's, and measuring it is how the choice was made."""
    solved = v221.build(
        v221.Pacing(seconds=3.5), spec, rail=rail, land="still",
        line=line, spine=spine, cfg=cfg,
    )
    report = v221.pace_report(solved, rail=rail, stride=4)
    handoff = report["handoff"]
    # Not exactly zero: the smootherstep's cubic tail leaves 3e-05 of a layout
    # unit in the last frame. Against the race camera's own 0.169 that is rest.
    assert handoff["last_step"] < 1e-4
    # ... and therefore hands over with the race camera's whole first step as a
    # discontinuity, which is the thing `land="rail"` exists to remove.
    assert handoff["velocity_residual"] == pytest.approx(
        -handoff["race_first_step"], abs=1e-3
    )
    # And it keeps V22's lens all the way to the cut: the zoom snap is real.
    assert handoff["fov_delta"] == pytest.approx(48.0 - 34.0, abs=1e-6)


# --- the track the renderer reads -----------------------------------------


@needs_track
def test_the_track_carries_the_field_of_view_per_row(solved, rail):
    """`course_preview.preview_track` writes one constant; this one does not."""
    track = v221.preview_track(solved, seed=5432)
    rows = [row for cut in track["cuts"] for row in cut["frames"]]
    assert rows[0][7] == pytest.approx(solved["spec"].fov, abs=1e-3)
    assert rows[-1][7] == pytest.approx(rail.fov, abs=1e-3)
    assert len({row[7] for row in rows}) > 10


@needs_track
def test_consecutive_cuts_still_share_their_boundary_row(solved):
    """The duplicate-frame bug `course_preview.preview_track` documents is fixed
    by cuts overlapping by one row, and rewriting the field of view must not
    disturb that."""
    track = v221.preview_track(solved, seed=5432)
    cuts = track["cuts"]
    for before, after in zip(cuts, cuts[1:]):
        assert before["frames"][-1][0] == after["frames"][0][0]
        assert before["frames"][-1][1:] == after["frames"][0][1:]


@needs_track
def test_the_prefix_is_frames_over_fps(solved):
    """`presentation.Clock.prefix` is seconds of output. See `sloped.v22`."""
    frames = len(solved["frames"])
    assert frames == 210
    assert frames / 60.0 == pytest.approx(3.5, abs=1e-12)
    # And the report's own duration is the span of frame centres, which is one
    # frame less and is not what the film clock wants.
    assert solved["duration"] == pytest.approx(209 / 60.0, abs=1e-12)

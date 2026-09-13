"""V22.1's finish: the continuity it claims, and the race it must not touch.

The prototype's whole argument is that a chase can end without a cut, and every
claim in that sentence is a number these check rather than a judgement:

* **The join is C1 by construction.** The first solved frame is the chase's own
  last frame, and the first *step* after it is the chase's own last step, to
  four decimal places. Not "smooth"; equal.
* **The cubic cannot bulge or bounce.** `MIN_RATIO` and `MAX_RATIO` are a band
  the settle is solved into, and the property they buy - the lens never moves
  faster than the chase already was - is asserted over the solved rows rather
  than rederived from the algebra.
* **Nothing before the split moves.** Every row the V22 solve wrote before
  `Candidate.split` is in the new track unchanged, which is what "do not touch
  the branch and merge cameras" means as a test.
* **The race is the race.** Seed, finish order, crossing times and the last
  crossing are read off the replay and compared with the locked values. A
  camera pass that changed any of them would be a different film.
* **All eight cross in frame.** Every marble, at its own crossing instant, is
  inside the frame, unobstructed and at least `MIN_MEDIAN_PX` across.
* **No whip and no terrain.** The lens's own step and the view's own turn are
  under the production limits over every frame of the window, and the camera
  stays clear of the ground and of its own sight line.

The solve is deterministic and cheap - it reads a solved V22 track and rewrites
its tail - so these run against the locked seed rather than a fresh race. The
ones that need the replay skip if it is not on disk; the pure-arithmetic ones
never do.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sloped import chase_camera, presentation, readability, v22, v221_finish
from sloped.course import sloped_course
from sloped.v221_finish import (
    MAX_RATIO,
    MIN_RATIO,
    Candidate,
    Orbit,
    Pose,
    build,
    check_finish,
    finish_clip,
    finish_frame,
    lens_pose,
    pose_to_world,
    ratio,
    settle_seconds,
    world_to_pose,
)

OUT = ROOT / "output" / "sloped_race_v1"
REPLAY = OUT / "race_5432.json"

FPS = 60
SEED = 5432
FINISH_ORDER = [5, 2, 7, 4, 1, 6, 3, 0]
CROSSINGS = [20.850, 21.133333, 21.716667, 22.633333,
             22.650000, 23.500000, 24.316667, 24.416667]
LAST_CROSSING = 24.416667
FINISH_END = 24.467

WIDTH, HEIGHT = 1080, 1920
MIN_PX = readability.MIN_MEDIAN_PX

# The shipped candidate, retyped here on purpose. `tools/sloped_v221_finish.py`
# is free to sweep; what these pin is that *these* numbers produce a finish that
# passes, so a change to either has to be a deliberate one.
SPLIT = 18.900
PARK = Pose(bearing=180.0, radius=26.0, height=18.0, aim_ahead=0.0,
            aim_lift=1.0, fov=36.0)
AIM_SETTLE = 1.2

needs_replay = pytest.mark.skipif(
    not REPLAY.is_file(), reason="the locked replay is not on disk"
)


@pytest.fixture(scope="module")
def machine():
    return sloped_course(routes="both")


@pytest.fixture(scope="module")
def replay():
    if not REPLAY.is_file():
        pytest.skip("the locked replay is not on disk")
    return json.loads(REPLAY.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def base(replay, machine):
    """The frozen V22 race track, solved from the production module."""
    return v22.build_race_track(replay, machine)


@pytest.fixture(scope="module")
def candidate_a():
    return Candidate(name="a_chase", split=SPLIT, park=PARK, ratio=2.0,
                     aim_settle=AIM_SETTLE)


@pytest.fixture(scope="module")
def track_a(base, replay, machine, candidate_a):
    return build(base, replay, machine, candidate_a)


@pytest.fixture(scope="module")
def track_b(base, replay, machine):
    lens = lens_pose(base, machine)
    return build(base, replay, machine, Candidate(
        name="b_orbit", split=SPLIT, park=PARK, ratio=2.0, aim_settle=AIM_SETTLE,
        orbit=Orbit(at=20.900, seconds=5.400, to=lens, ease=0.45),
    ))


def _rows(track, since=None):
    rows = v221_finish._rows(track)
    if since is None:
        return rows
    return [row for row in rows if float(row[0]) >= since - 1e-9]


def _direction(row):
    forward = [float(row[4 + axis]) - float(row[1 + axis]) for axis in range(3)]
    length = math.sqrt(sum(v * v for v in forward)) or 1.0
    return [v / length for v in forward]


# --- the polar frame, which is arithmetic and needs no race -----------------


def test_the_pose_round_trips_through_world_space(machine):
    """`world_to_pose` is `pose_to_world`'s inverse, not an approximation of it.

    Every number in the sweeps is a `Pose` and every number the renderer reads
    is a world position, so a conversion that drifts would make the sweep and
    the render disagree about which shot was measured.
    """
    for pose in (
        Pose(bearing=180.0, radius=26.0, height=18.0),
        Pose(bearing=26.9, radius=18.5, height=17.3, aim_ahead=2.0, aim_lift=1.5),
        Pose(bearing=-140.0, radius=31.0, height=9.0, aim_ahead=-4.0),
    ):
        position, aim = pose_to_world(machine, pose)
        back = world_to_pose(machine, position, aim, pose.fov)
        assert back.radius == pytest.approx(pose.radius, abs=1e-6)
        assert back.height == pytest.approx(pose.height, abs=1e-6)
        assert back.aim_ahead == pytest.approx(pose.aim_ahead, abs=1e-6)
        assert back.aim_lift == pytest.approx(pose.aim_lift, abs=1e-6)
        assert math.cos(math.radians(back.bearing - pose.bearing)) == pytest.approx(
            1.0, abs=1e-9
        )


def test_bearing_180_is_behind_the_racers(machine):
    """The convention the whole module is written in, asserted once.

    A pose at 180 must be **up-course** of the line - on the side the racers
    arrive from - because every sentence in the docstrings about "behind the
    marbles" is that one fact.
    """
    node, forward, _right = finish_frame(machine)
    position, _aim = pose_to_world(
        machine, Pose(bearing=180.0, radius=20.0, height=0.0)
    )
    along = sum((position[axis] - node[axis]) * forward[axis] for axis in (0, 2))
    assert along < -19.0


def test_v19s_finish_lens_is_at_a_positive_bearing_in_front(base, machine):
    """The perpendicular `finish_frame` chose, pinned by the lens it was chosen for.

    `right` has two candidates and the module picked the one that puts V19's
    finish lens at a positive bearing under 90 degrees - in front of the line
    and off to one side. If that flips, every swept bearing means its mirror.
    """
    lens = lens_pose(base, machine)
    assert 0.0 < lens.bearing < 90.0
    assert lens.radius == pytest.approx(18.5, abs=0.5)
    assert lens.height == pytest.approx(17.3, abs=0.5)


def test_the_orbit_takes_the_short_way_round(machine):
    """180 to 27 is 153 degrees one way and 207 the other; it must take 153.

    A camera that takes the long way crosses the course rather than swinging
    round the outside of it.
    """
    assert v221_finish._bearing_path(180.0, 26.9) == pytest.approx(26.9)
    # 180 to 350 is +170 the way it is written and -190 the other way, so the
    # unwrapped value is 350 rather than -10. Worth a line because the obvious
    # expectation is the wrong one: "wrap into [-180, 180)" is about the *delta*
    # and not about the destination.
    assert v221_finish._bearing_path(180.0, 350.0) == pytest.approx(350.0)
    assert v221_finish._bearing_path(-170.0, 170.0) == pytest.approx(-190.0)
    for start, end in ((180.0, 26.9), (180.0, 350.0), (-170.0, 170.0), (10.0, 200.0)):
        moved = v221_finish._bearing_path(start, end) - start
        assert -180.0 <= moved <= 180.0
        assert math.cos(math.radians(start + moved - end)) == pytest.approx(1.0)


# --- the ease profiles ------------------------------------------------------


def test_the_trapezoid_completes_and_peaks_where_the_algebra_says(machine):
    """A trapezoid's peak rate is `1 / (1 - ease)` times its mean, and it ends at 1.

    This is the number candidate B is timed on: at ease 0.25 the middle of the
    swing runs 1.33 times the mean, against a smootherstep's 1.875. If the
    profile drifted, the orbit's turn-rate budget would be wrong by that factor.
    """
    for ease in (0.0, 0.25, 0.4, 0.5):
        steps = 2000
        values = [v221_finish._trapezoid(k / steps, ease) for k in range(steps + 1)]
        assert values[0] == pytest.approx(0.0)
        assert values[-1] == pytest.approx(1.0, abs=1e-9)
        assert all(b >= a - 1e-12 for a, b in zip(values, values[1:]))
        peak = max((b - a) * steps for a, b in zip(values, values[1:]))
        assert peak == pytest.approx(1.0 / (1.0 - ease), rel=2e-3)


def test_the_settle_is_solved_for_the_ratio_it_was_asked_for():
    """`settle_seconds` and `ratio` are inverses over the band that matters."""
    for distance, speed, target in ((70.0, 0.83, 2.0), (30.0, 0.29, 1.6),
                                    (12.5, 0.40, 3.0)):
        seconds = settle_seconds(distance, speed, target)
        steps = int(round(seconds * FPS))
        # Within half a frame, which is all `int(round(...))` leaves: the solve
        # is continuous and the track is not, and the difference is 1/(2*steps)
        # of the ratio rather than anything about the shape.
        assert ratio(distance, speed, steps) == pytest.approx(
            target, rel=0.5 / steps + 1e-9
        )


# --- the join ---------------------------------------------------------------


@needs_replay
def test_nothing_before_the_split_moves(base, track_a):
    """Every row the V22 solve wrote before the split is in the new track, unchanged.

    This is "do not change the branch and merge cameras before the final
    approach" as an assertion: not *almost* the same, the same row.
    """
    before = {round(float(row[0]), 6): row for row in _rows(base)
              if float(row[0]) <= SPLIT + 1e-9}
    after = {round(float(row[0]), 6): row for row in _rows(track_a)
             if float(row[0]) <= SPLIT + 1e-9}
    assert before.keys() == after.keys()
    assert before.keys()
    for when, row in before.items():
        assert list(row) == list(after[when]), f"row at replay {when} moved"


@needs_replay
def test_the_first_step_after_the_split_is_the_chase_s_own(base, track_a):
    """The continuity claim, at the only frame where it can be checked directly.

    A Hermite whose start tangent is the chase's last velocity must produce a
    first step equal to that velocity. Equal, to the rounding the track is
    written at - which is what distinguishes a join from a small jump nobody
    noticed.
    """
    chase = _rows(base)
    incoming = [r for r in chase if float(r[0]) <= SPLIT + 1e-9]
    last_step = math.dist(incoming[-2][1:4], incoming[-1][1:4])
    rows = _rows(track_a, SPLIT)
    first_step = math.dist(rows[0][1:4], rows[1][1:4])
    # **A shade under, never over, and the shade is the discretisation.** The
    # cubic's *derivative* at the join is exactly the chase's last velocity, but
    # a rendered step is the integral of that derivative across one frame and
    # the derivative is already falling. The deficit is 1/steps of the velocity
    # - here 0.83% over 161 frames - and it is the right sign: the first frame
    # of the finish can only be calmer than the last frame of the chase.
    steps = track_a["shape"]["steps"]
    assert first_step <= last_step + 1e-4
    assert first_step >= last_step * (1.0 - 3.0 / steps)


@needs_replay
def test_the_lens_never_moves_faster_than_the_chase_already_was(track_a):
    """`MIN_RATIO`'s promise, asserted on the rows rather than on the algebra.

    Inside the band the cubic's fastest frame is its first, so the whole finish
    is bounded by the step the chase arrived with. The V22 chase's own worst
    interior step is 0.832 layout units a frame; nothing here may beat it.
    """
    rows = _rows(track_a, SPLIT)
    steps = [math.dist(a[1:4], b[1:4]) for a, b in zip(rows, rows[1:])]
    assert max(steps) <= 0.8320 + 1e-3
    assert max(steps) <= chase_camera.MAX_PHASE_STEP


@needs_replay
def test_the_settle_lands_inside_the_no_bounce_band(base, replay, machine,
                                                    candidate_a, track_a):
    """The solved settle is in `[MIN_RATIO, MAX_RATIO]` on both channels.

    Outside it the shape is wrong in a named way: over `MAX_RATIO` the lens
    overshoots the park and comes back, under `MIN_RATIO` it has to speed up to
    arrive. Neither is visible in a single still, and both are one division.
    """
    shape = track_a["shape"]
    assert MIN_RATIO <= shape["ratio"] <= MAX_RATIO
    # **The aim is deliberately under the band, and that is the anticipation.**
    # Inside it the aim would not reach the finish line until the lens did, and
    # the line would not be in frame until the shot was over. Under it the aim
    # bulges - it moves faster than it arrived - and what bounds that is not
    # this band but the aim-speed rule in `cameras.check_track`, which
    # `check_finish` runs and which `test_the_production_checker_has_nothing_to
    # _say` asserts.
    assert shape["aim_ratio"] < MIN_RATIO
    assert shape["aim_settle"] < shape["settle"]


@needs_replay
def test_the_lens_arrives_at_the_park_and_stays_there(base, replay, machine,
                                                      machine_park=PARK):
    """After `settle` the camera holds the pose it was solved onto, exactly.

    A candidate with no orbit is a stand from that instant, and a stand that
    drifts is a slow version of the thing this pass exists to remove.
    """
    candidate = Candidate(name="a", split=SPLIT, park=machine_park, ratio=2.0,
                          aim_settle=AIM_SETTLE)
    track = build(base, replay, machine, candidate)
    parked_at = track["shape"]["parked_at"]
    position, aim = pose_to_world(machine, machine_park)
    held = [row for row in _rows(track) if float(row[0]) >= parked_at + 0.05]
    assert len(held) > 60
    for row in held:
        assert math.dist(row[1:4], position) < 1e-3
        assert math.dist(row[4:7], aim) < 1e-3


@needs_replay
def test_the_hard_cut_at_the_finish_is_gone(base, replay, track_a):
    """The defect this pass was opened on: V22's 0.443 boundary, measured away.

    The control's `merge -> finish` jump is re-measured here rather than quoted,
    so the comparison is against the track this branch actually starts from.
    """
    control = {
        (join["from"], join["to"]): join["jump"]
        for join in readability.continuity_report(base, replay)
    }
    assert control[("merge", "finish")] == pytest.approx(0.443, abs=0.01)
    after = readability.continuity_report(track_a, replay)
    assert not any(join["to"] == "finish" for join in after)
    measured = [float(j["jump"]) for j in after if j.get("jump") is not None]
    assert max(measured) <= 0.25


@needs_replay
def test_no_boundary_inside_the_finish_is_a_cut(track_a):
    """Between the merge phase and the final phase the picture does not move.

    Chase phases share their boundary row on purpose, so the distance across
    every boundary in the new track is zero rather than merely small.
    """
    cuts = track_a["cuts"]
    for before, after in zip(cuts, cuts[1:]):
        if not (before.get("chase") and after.get("chase")):
            continue
        assert math.dist(before["frames"][-1][1:4], after["frames"][0][1:4]) < 1e-6


# --- what the shot has to show ---------------------------------------------


@needs_replay
def test_the_race_is_untouched(replay, track_a):
    """Seed, order, crossings and the last crossing: inputs, not outputs."""
    assert int(replay["seed"]) == SEED
    crossed = v221_finish._crossings(replay)
    assert sorted(crossed, key=lambda m: crossed[m]) == FINISH_ORDER
    for marble, when in zip(FINISH_ORDER, CROSSINGS):
        assert crossed[marble] == pytest.approx(when, abs=1e-4)
    assert track_a["last_crossing"] == pytest.approx(LAST_CROSSING, abs=1e-4)
    assert float(track_a["cuts"][-1]["to"]) == pytest.approx(FINISH_END, abs=1e-3)


@needs_replay
def test_all_eight_cross_in_frame_clear_and_readable(track_a, replay, machine):
    """Every marble, at its own crossing instant, is on screen and big enough.

    The brief's floor is that a replacement finish must not make the crossing
    order ambiguous, and this is that floor: in the frustum, with nothing drawn
    in front of it, at `readability.MIN_MEDIAN_PX` or more.
    """
    from sloped import sightlines, terrain

    cfg = terrain.terrain_config(machine.runs)
    bundle = sightlines.Bundle(
        sightlines.course_solids(machine, lambda x, z: terrain.height(x, z, cfg))
    )
    crossed = v221_finish._crossings(replay)
    times = [float(frame["t"]) for frame in replay["frames"]]
    rows = _rows(track_a)
    radius = float(replay.get("units", {}).get("layout_marble_radius", 0.285))
    for marble in FINISH_ORDER:
        when = crossed[marble]
        row = min(rows, key=lambda r: abs(float(r[0]) - when))
        index = min(range(len(times)), key=lambda k: abs(times[k] - when))
        point = [
            float(v) * chase_camera.SIM_TO_LAYOUT
            for v in replay["frames"][index]["marbles"][marble]["p"]
        ]
        placed = presentation.project(row[1:4], row[4:7], float(row[7]), point,
                                      WIDTH, HEIGHT)
        assert placed is not None, f"m{marble} is behind the camera as it crosses"
        assert 0.0 <= placed[0] <= WIDTH and 0.0 <= placed[1] <= HEIGHT, (
            f"m{marble} is outside the frame as it crosses"
        )
        size = (2.0 * radius / placed[2]) / (
            2.0 * math.tan(math.radians(float(row[7])) * 0.5)
        ) * HEIGHT
        assert size >= MIN_PX, f"m{marble} is {size:.1f} px as it crosses"
        assert bundle.first_hit(row[1:4], point, shorten=radius) is None, (
            f"m{marble} is behind the course as it crosses"
        )


@needs_replay
def test_the_finish_line_is_visible_well_before_the_winner(track_a, replay, machine):
    """Anticipation, as the brief's own question: how long can the viewer see it.

    The unbroken run must end **at** the crossing - a shot that shows the line,
    loses it and finds it again has not told anybody the finish is coming - and
    it must beat the control's 0.633 s by a margin worth the work.
    """
    from sloped import sightlines, terrain

    cfg = terrain.terrain_config(machine.runs)
    bundle = sightlines.Bundle(
        sightlines.course_solids(machine, lambda x, z: terrain.height(x, z, cfg))
    )
    node, _forward, _right = finish_frame(machine)
    _marble, won = v221_finish.winner(replay)
    rows = [row for row in _rows(track_a) if float(row[0]) <= won + 1e-9]
    run_from = None
    for row in rows:
        placed = presentation.project(row[1:4], row[4:7], float(row[7]), node,
                                      WIDTH, HEIGHT)
        inside = placed is not None and (
            90.0 <= placed[0] <= WIDTH - 90.0 and 90.0 <= placed[1] <= HEIGHT - 90.0
        )
        clear = inside and bundle.first_hit(row[1:4], node, shorten=0.30) is None
        run_from = run_from if clear else None
        if clear and run_from is None:
            run_from = float(row[0])
    assert run_from is not None
    assert won - run_from >= 1.2


@needs_replay
def test_the_view_never_whips_and_never_touches_the_ground(track_a, machine):
    """Turn rate, ground clearance and sight clearance over the whole window."""
    from sloped import terrain

    cfg = terrain.terrain_config(machine.runs)
    rows = _rows(track_a, SPLIT)
    for a, b in zip(rows, rows[1:]):
        one, two = _direction(a), _direction(b)
        dot = max(-1.0, min(1.0, sum(one[i] * two[i] for i in range(3))))
        assert math.degrees(math.acos(dot)) <= chase_camera.MAX_TURN_RATE
    for row in rows:
        ground = terrain.height(float(row[1]), float(row[3]), cfg)
        assert float(row[2]) - ground >= chase_camera.GROUND_MARGIN
        assert terrain.clearance(row[1:4], row[4:7], cfg) >= chase_camera.SIGHT_MARGIN


@needs_replay
def test_the_production_checker_has_nothing_to_say(track_a, track_b, replay):
    """`check_finish` returns no findings for either candidate.

    It is `chase_camera.check_chase` with one finding retired for a written
    reason; everything else the production checker knows still applies.
    """
    assert check_finish(track_a, replay) == []
    assert check_finish(track_b, replay) == []


@needs_replay
def test_the_orbit_may_not_begin_before_the_winner_crosses(base, replay, machine):
    """Candidate B's defining constraint, enforced rather than documented."""
    lens = lens_pose(base, machine)
    with pytest.raises(ValueError, match="may not interrupt"):
        build(base, replay, machine, Candidate(
            name="early", split=SPLIT, park=PARK, ratio=2.0,
            orbit=Orbit(at=20.500, seconds=3.0, to=lens),
        ))


@needs_replay
def test_the_orbit_has_not_moved_when_the_winner_crosses(track_a, track_b, replay):
    """B keeps A's camera through the first two crossings, which is its whole claim.

    Measured against **candidate A at the same instant** rather than against the
    park pose, because at 20.850 neither of them has reached the park yet - both
    are still settling onto it, by design, at about a third of the step they
    arrived with. The question B has to answer is not "is the camera stopped"
    but "has the orbit contributed anything", and the difference between the two
    tracks is exactly that contribution.

    Beginning the orbit 0.05 s after the winner is not enough on its own: a move
    that starts late and accelerates hard still swings under the second
    finisher. The 0.45 ease is what buys this.
    """
    left = {round(float(row[0]), 6): row for row in _rows(track_a)}
    right = {round(float(row[0]), 6): row for row in _rows(track_b)}
    crossed = v221_finish._crossings(replay)
    for marble in FINISH_ORDER[:2]:
        when = round(min(left, key=lambda t: abs(t - crossed[marble])), 6)
        assert math.dist(left[when][1:4], right[when][1:4]) < 0.05
        assert math.dist(left[when][4:7], right[when][4:7]) < 0.05


@needs_replay
def test_the_clip_renders_the_same_frames_the_master_would(track_a):
    """`finish_clip` re-times the edit and touches no camera row.

    The proofs are rendered from clips; a clip that changed a pose would make
    every rendered comparison a comparison of something else.
    """
    clip = finish_clip(track_a, 20.000)
    assert clip["edit"][0]["out"][0] == pytest.approx(0.0)
    assert clip["edit"][0]["replay"][0] == pytest.approx(20.000)
    full = {round(float(row[0]), 6): row for row in _rows(track_a)}
    for row in _rows(clip):
        assert list(row) == list(full[round(float(row[0]), 6)])
    span = sum(float(s["replay"][1]) - float(s["replay"][0]) for s in clip["edit"])
    assert clip["duration"] == pytest.approx(span, abs=1e-6)


@needs_replay
def test_the_control_is_handed_back_untouched(base, replay, machine):
    """A candidate with no park is V22 itself, not a re-solve of it."""
    control = Candidate(name="c_v22", split=None, park=None)
    assert build(base, replay, machine, control) is base

"""V21.1 is V20 with 85 frames taken out of the start. These pin the join.

The only thing V21.1 adds to the pipeline is an omission, and an omission is the
one edit that can quietly stop being honest: a frame shown twice, a frame shown
out of order, a rate that is no longer the rate PyBullet produced, a cue left
pointing at the second it used to happen on. So the suite is built around four
questions and nothing else.

* **Is every surviving frame still showing what it showed in V19?** Frame for
  frame, against the locked master's own map - `test_every_kept_frame_shows
  _what_it_showed_in_v19`.
* **Does the film ever repeat or rewind?** The shown replay must step forwards
  by exactly one frame everywhere except at the two omissions, where it steps
  forwards by more.
* **Did anything except *when* change?** After the cut every instant is the same
  instant, 85 frames earlier, and nothing else moved.
* **Is the start still legible?** Enough of the mixing to read as mixing, enough
  of the closed floor to read as a release - both measured off the replay rather
  than asserted.

The physics, the seed, the course, the camera track and `real_race_v19.mp4` are
inputs here and none of them is touched.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sloped import overlays, presentation

OUT = ROOT / "output" / "sloped_race_v1"
REPLAY = OUT / "race_5432.json"
TRACK = OUT / "cameras_5432.json"

MASTER_FRAMES = 1150             # V19, rendered: frames 0 to round(19.15 * 60)
HOLD_FRAMES = 42
FPS = 60

# The cut, in master frames. Frame 48 is replay 1.000 and frame 134 is replay
# 5.833333, both on the `start` lens, so what goes is 4.833 s of the drum.
CUT = ((49, 133),)
GONE_FRAMES = 85
SHIFT = GONE_FRAMES / FPS        # 1.416667 s earlier, for everything after it


@pytest.fixture(scope="module")
def loaded():
    if not REPLAY.is_file() or not TRACK.is_file():
        pytest.skip("the selected replay or its camera track is not built")
    replay, track, before = presentation.load(str(REPLAY), str(TRACK), MASTER_FRAMES)
    after, keep = presentation.omit_frames(before, CUT)
    return replay, track, before, after, keep


def _shown(clock: presentation.Clock) -> list[float]:
    """What each frame of the finished film is showing, in replay seconds."""
    return [clock.replay_at(clock.hold + frame / FPS) for frame in range(clock.master_frames)]


def _lens_at(track: dict, replay_second: float) -> str:
    """The cut the renderer would be on, picked exactly as `_camera_at` picks it."""
    for cut in track["cuts"]:
        if replay_second <= float(cut["to"]):
            return str(cut["name"])
    return str(track["cuts"][-1]["name"])


# --- the frames -------------------------------------------------------------


def test_the_cut_takes_whole_frames_out_of_the_master(loaded):
    _replay, _track, before, after, keep = loaded
    assert keep == ((0, 48), (134, 1149))
    assert before.master_frames - after.master_frames == GONE_FRAMES
    assert after.master_frames == 1065
    assert sum(last - first + 1 for first, last in keep) == after.master_frames


def test_the_film_is_a_whole_number_of_frames(loaded):
    _replay, _track, _before, after, _keep = loaded
    assert after.hold_frames == HOLD_FRAMES
    assert after.frames == HOLD_FRAMES + 1065 == 1107
    assert after.duration == pytest.approx(1107 / 60.0, abs=1e-9)
    assert after.duration == pytest.approx(18.45, abs=1e-6)


def test_every_kept_frame_shows_what_it_showed_in_v19(loaded):
    """Frame for frame against the locked master. This is the whole claim."""
    _replay, _track, before, after, keep = loaded
    index = 0
    for first, last in keep:
        for frame in range(first, last + 1):
            was = before.replay_at(before.hold + frame / FPS)
            now = after.replay_at(after.hold + index / FPS)
            assert was is not None and now is not None, frame
            assert now == pytest.approx(was, abs=1e-6), (frame, index)
            index += 1
    assert index == after.master_frames


def test_the_film_never_repeats_or_rewinds_a_frame(loaded):
    """Every step forwards, and exactly one frame of it outside the omissions."""
    _replay, _track, _before, after, _keep = loaded
    shown = _shown(after)
    steps = [round(b - a, 6) for a, b in zip(shown, shown[1:])]
    assert min(steps) > 0.0, "the film steps backwards somewhere"
    jumps = {index: step for index, step in enumerate(steps)
             if abs(step - 1 / FPS) > 1e-6}
    # Two, and only two: V21.1's own cut, and the 0.85 s V19 already omitted.
    assert sorted(jumps) == [48, 569]
    assert jumps[48] == pytest.approx(4.833333, abs=1e-5)
    # **V19's own cut reports 0.85 s and steps 0.866667.** Its `split` window
    # opens at replay 15.35 but the first frame of it lands at 15.366667, so the
    # map's figure is a sixtieth short of the gap the pictures actually make.
    # V21.1's cut is written from the surviving frames, so its two agree.
    assert jumps[569] == pytest.approx(0.85 + 1 / FPS, abs=1e-5)


def test_the_rate_is_still_the_rate_pybullet_produced(loaded):
    """Slope one in every window, so nothing is sped up or slowed down."""
    _replay, _track, _before, after, _keep = loaded
    for out_from, out_to, replay_from, replay_to in after.segments:
        assert (out_to - out_from) == pytest.approx(replay_to - replay_from, abs=2e-6)
    # And end to end: take the two jumps out of the span the film covers and
    # what is left is one frame of replay per frame of film, to the microsecond.
    shown = _shown(after)
    steps = [b - a for a, b in zip(shown, shown[1:])]
    jumps = [step for step in steps if abs(step - 1 / FPS) > 1e-6]
    assert len(jumps) == 2
    assert (shown[-1] - shown[0]) - sum(jumps) == pytest.approx(
        (after.master_frames - 1 - len(jumps)) / FPS, abs=1e-6
    )


# --- what did and did not move ---------------------------------------------


def test_the_only_thing_that_changed_is_when(loaded):
    """Before the cut nothing moved; after it, everything moved by 85 frames."""
    _replay, _track, before, after, _keep = loaded
    for replay_second in (0.20, 0.316667, 0.50, 0.983333):
        assert after.at(replay_second) == pytest.approx(before.at(replay_second), abs=1e-6)
    for replay_second in (5.833333, 6.116667, 7.62, 8.62, 12.0, 16.3, 20.85, 23.6):
        was = before.at(replay_second)
        now = after.at(replay_second)
        assert was is not None and now is not None, replay_second
        assert now == pytest.approx(was - SHIFT, abs=1e-5), replay_second


def test_the_omitted_drum_has_no_output_time(loaded):
    _replay, _track, before, after, _keep = loaded
    for replay_second in (1.05, 2.0, 2.30, 3.5, 4.6, 5.70, 5.80):
        assert after.at(replay_second) is None, replay_second
    # V20 showed four of those. This is what "omitted" means.
    assert before.at(2.30) is not None
    assert before.at(5.70) is not None


def test_the_omissions_are_the_two_the_film_makes(loaded):
    _replay, _track, _before, after, _keep = loaded
    found = [(round(at, 6), round(dropped, 6))
             for at, dropped in presentation.omissions(after)]
    assert found == [(1.516667, 4.833333), (10.183333, 0.85)]


def test_v20_is_still_buildable_from_the_same_master(loaded):
    """An edition with no cuts is the identity, or V20 has silently changed."""
    _replay, _track, before, _after, _keep = loaded
    same, keep = presentation.omit_frames(before, ())
    assert same is before
    assert keep == ((0, MASTER_FRAMES - 1),)
    assert before.frames == 1192


# --- what `omit_frames` refuses --------------------------------------------


def test_a_cut_may_not_take_the_frame_the_hold_clones(loaded):
    _replay, _track, before, _after, _keep = loaded
    with pytest.raises(ValueError):
        presentation.omit_frames(before, ((0, 10),))


def test_a_cut_may_not_take_the_last_frame(loaded):
    _replay, _track, before, _after, _keep = loaded
    with pytest.raises(ValueError):
        presentation.omit_frames(before, ((1100, MASTER_FRAMES - 1),))


def test_overlapping_cuts_are_refused(loaded):
    _replay, _track, before, _after, _keep = loaded
    with pytest.raises(ValueError):
        presentation.omit_frames(before, ((49, 133), (100, 200)))


def test_a_cut_that_does_not_step_forwards_is_refused(loaded):
    """V19 already jumps 2.30 -> 5.70 at frame 126, so a cut that lands on the
    far side of it and is answered by a frame showing an earlier instant is a
    rewind. Frames 127 to 136 show 5.717 to 5.867; dropping them all leaves
    frame 126 (replay 2.30) against frame 137 (replay 5.883) - forwards, fine.
    A cut cannot rewind on this map, so the refusal is checked on one built to.
    """
    straight = presentation.Clock(
        segments=((0.0, 1.0, 10.0, 11.0), (1.0, 2.0, 0.0, 1.0)),
        hold=0.7, fps=FPS, master_frames=121,
    )
    # Frame 54 shows replay 10.900; frame 66 shows replay 0.100.
    with pytest.raises(ValueError, match="step forwards"):
        presentation.omit_frames(straight, ((55, 65),))


# --- the start, as a viewer meets it ----------------------------------------


def test_the_hook_still_has_the_field_to_itself(loaded):
    """PICK ONE is over before anything moves, exactly as in V20."""
    from tools.sloped_short import PICK_ONE_OUT_TO

    replay, _track, before, after, _keep = loaded
    gate = presentation.actuator_move(replay, after, "start.paddle")
    assert gate == pytest.approx(presentation.actuator_move(replay, before, "start.paddle"))
    assert gate == pytest.approx(0.816667, abs=1e-5)
    assert gate > PICK_ONE_OUT_TO
    # The hold is the choosing time and it is untouched.
    assert after.hold == pytest.approx(0.70, abs=1e-9)


def test_the_release_lands_in_the_retention_window(loaded):
    """The floor drops at 1.80 s. In V20 it dropped at 3.22."""
    replay, _track, before, after, _keep = loaded
    was = presentation.actuator_move(replay, before, "start.panel")
    now = presentation.actuator_move(replay, after, "start.panel")
    assert was == pytest.approx(3.216667, abs=1e-4)
    assert now == pytest.approx(1.800000, abs=1e-4)
    assert 1.5 <= now <= 2.0


def test_the_start_still_shows_the_field_being_mixed(loaded):
    """Measured, not asserted: inside the kept window the eight are released,
    reach ten times their resting speed and close up from 7.1 units of spread
    to under 5.2. That is the randomisation, and it is on screen."""
    import math

    replay, _track, _before, after, _keep = loaded
    window = [
        frame for frame in replay["frames"]
        if (at := after.at(float(frame["t"]))) is not None and at < 1.5
    ]
    assert window, "nothing of the start survived"
    seconds = (float(window[-1]["t"]) - float(window[0]["t"]))
    assert 0.75 <= seconds <= 1.10, seconds

    def spread(frame):
        xs = [one["p"][0] for one in frame["marbles"]]
        return max(xs) - min(xs)

    def fastest(frame):
        return max(math.sqrt(sum(v * v for v in one["v"])) for one in frame["marbles"])

    assert spread(window[0]) > 7.0
    assert spread(window[-1]) < 5.2
    assert fastest(window[0]) < 1.0                 # held on the line
    assert max(fastest(frame) for frame in window) > 8.0    # and poured out


def test_the_release_has_a_settled_field_in_front_of_it(loaded):
    """Coming back 0.28 s early is what makes the trapdoor read as a release
    rather than a glitch: the eight are visibly at rest on a closed floor."""
    import math

    replay, _track, _before, after, _keep = loaded
    trapdoor = presentation.actuator_move(replay, after, "start.panel")
    # From the first frame *after* the cut. Output 1.5 itself is the last frame
    # before it - replay 1.000, the field in mid-air - and belongs to the other
    # side of the join.
    opens = after.hold + 49 / FPS
    lead = [
        frame for frame in replay["frames"]
        if (at := after.at(float(frame["t"]))) is not None and opens - 1e-6 <= at < trapdoor
    ]
    assert len(lead) >= 15, len(lead)
    assert len(lead) / FPS >= 0.25
    for frame in lead:
        assert max(math.sqrt(sum(v * v for v in one["v"])) for one in frame["marbles"]) < 1.5


def test_the_cut_does_not_change_the_lens(loaded):
    """The same shot on both sides, so the join reads as a skip in time."""
    _replay, track, _before, after, keep = loaded
    last_before = after.replay_at(after.hold + 48 / FPS)
    first_after = after.replay_at(after.hold + 49 / FPS)
    assert last_before == pytest.approx(1.0, abs=1e-6)
    assert first_after == pytest.approx(5.833333, abs=1e-6)
    assert _lens_at(track, last_before) == _lens_at(track, first_after) == "start"
    assert keep[0][1] + 1 == 49


# --- the race, which arrives sooner -----------------------------------------


def test_the_downhill_arrives_a_second_and_a_half_earlier(loaded):
    """Replay 7.883 is the first racer onto `leg1`, the first downhill run."""
    _replay, _track, before, after, _keep = loaded
    for replay_second in (7.62, 7.883333, 8.916667):
        was, now = before.at(replay_second), after.at(replay_second)
        assert was - now == pytest.approx(SHIFT, abs=1e-5)
    assert after.at(7.883333) == pytest.approx(3.566667, abs=1e-4)
    assert before.at(7.883333) == pytest.approx(4.983333, abs=1e-4)


def test_the_start_is_a_fifth_of_the_film_not_a_quarter(loaded):
    """How much of the running time is spent before the floor opens."""
    replay, _track, before, after, _keep = loaded
    was = presentation.actuator_move(replay, before, "start.panel") / before.duration
    now = presentation.actuator_move(replay, after, "start.panel") / after.duration
    assert was == pytest.approx(0.162, abs=0.005)
    assert now == pytest.approx(0.098, abs=0.005)
    assert now < was


# --- the marks and the sound still land -------------------------------------


def test_the_winners_mark_is_still_after_the_crossing_and_before_the_dead_heat(loaded):
    from tools.sloped_short import WINNER_DELAY, WINNER_SECONDS

    replay, _track, _before, after, _keep = loaded
    crossings = {
        int(event["order"]): after.at(float(event["t"]))
        for event in replay["events"]
        if event["kind"] == "finish_line" and after.at(float(event["t"])) is not None
    }
    assert len(crossings) == 6, "the film still holds six of the eight crossings"
    assert crossings[1] == pytest.approx(15.683333, abs=1e-4)
    start = crossings[1] + WINNER_DELAY
    assert start > crossings[1]
    assert start + WINNER_SECONDS < min(crossings[4], crossings[5])


def test_the_end_fact_shows_the_same_footage_it_always_did(loaded):
    """The tail of the film did not move relative to the race, only the clock."""
    from tools.sloped_short import END_FACT_SECONDS

    _replay, _track, before, after, _keep = loaded
    was = before.replay_at(before.duration - END_FACT_SECONDS)
    now = after.replay_at(after.duration - END_FACT_SECONDS)
    assert now == pytest.approx(was, abs=1e-6)


def test_the_end_fact_still_covers_nobody(loaded):
    replay, track, _before, after, _keep = loaded
    from tools.sloped_short import END_FACT_SECONDS

    window = (after.duration - END_FACT_SECONDS, after.duration)
    box = overlays.end_fact().getbbox()
    top, bottom = box[1], box[3]
    for marble_id in range(8):
        for _when, x, y, radius in presentation.screen_track(
            replay, track, after, marble_id, window
        ):
            if not (-radius <= x <= overlays.WIDTH + radius):
                continue
            if not (-radius <= y <= overlays.HEIGHT + radius):
                continue
            assert y + radius < top or y - radius > bottom, (marble_id, y, radius)


def test_the_whoosh_marks_the_cut_and_is_the_only_thing_that_does(loaded):
    """One cue per omission, placed on the frame the new picture arrives."""
    _replay, _track, _before, after, _keep = loaded
    found = presentation.omissions(after)
    assert len(found) == 2
    at, dropped = found[0]
    assert at == pytest.approx(after.hold + 49 / FPS, abs=1e-5)
    assert dropped > 3.4, "the cue is scaled to how much went, and this is more"


def test_the_soundtrack_is_exactly_as_long_as_the_picture(loaded):
    from audio import marble

    replay, track, _before, after, _keep = loaded
    built = marble.build_race_audio(replay, track, after)
    assert len(built.left) == len(built.right)
    assert len(built.left) == int(round(after.duration * built.sample_rate))
    assert built.seconds == pytest.approx(1107 / 60.0, abs=1e-6)
    assert built.limited is False
    assert built.placed.get("whoosh") == 2
    assert built.placed.get("split") == 2
    assert built.placed.get("crossing") == 6

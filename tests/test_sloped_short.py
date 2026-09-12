"""V20 is presentation over a locked master. These pin what may not drift.

The picture is V19 and nothing here re-renders it, so the risks are all in the
joins: a clock that puts a sound on the wrong frame, a projection that puts a
mark on the wrong pixel, a mix whose limiter flattens the finish, or an overlay
that covers the thing it is there to celebrate. Each of those has a test.

Two of them exist because the first attempt got them wrong and the file showed
it: `test_the_screen_right_vector_is_right_handed` (the winner's ring was drawn
on the wrong side of the marble) and `test_the_limiter_stays_idle` (every accent
in the finish came out at exactly -1.31 dBFS).
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sloped import overlays, presentation

OUT = ROOT / "output" / "sloped_race_v1"
REPLAY = OUT / "race_5432.json"
TRACK = OUT / "cameras_5432.json"
MASTER_FRAMES = 1150
HOLD_FRAMES = 42


@pytest.fixture(scope="module")
def loaded():
    if not REPLAY.is_file() or not TRACK.is_file():
        pytest.skip("the selected replay or its camera track is not built")
    return presentation.load(str(REPLAY), str(TRACK), MASTER_FRAMES)


# --- the clock --------------------------------------------------------------


def test_the_film_is_a_whole_number_of_frames(loaded):
    _replay, _track, clock = loaded
    assert clock.hold_frames == HOLD_FRAMES
    assert clock.frames == HOLD_FRAMES + MASTER_FRAMES == 1192
    assert clock.duration == pytest.approx(1192 / 60.0, abs=1e-9)
    # And inside the brief's window, with room under the ceiling.
    assert 19.8 <= clock.duration <= 20.2


def test_the_master_is_1150_frames_not_its_nominal_duration(loaded):
    """19.15 s of camera track is 1150 rendered frames, which is 19.1667 s.

    Taking the nominal figure makes the soundtrack a frame short of the picture.
    """
    _replay, track, clock = loaded
    nominal = float(track["duration"])
    assert nominal == pytest.approx(19.15, abs=1e-6)
    assert clock.master_frames == 1150
    assert clock.master_frames / 60.0 > nominal


def test_omitted_replay_time_has_no_output_time(loaded):
    """Three and a half seconds of mixing are not in the film and make no sound."""
    _replay, _track, clock = loaded
    assert clock.at(3.5) is None                  # inside the omitted mixing
    assert clock.at(14.9) is None                 # inside the omitted 0.85 s
    assert clock.at(0.20) == pytest.approx(clock.hold, abs=1e-9)
    assert clock.at(20.850) == pytest.approx(17.100, abs=1e-6)


def test_the_clock_is_slope_one_and_round_trips(loaded):
    _replay, _track, clock = loaded
    for replay_second in (0.5, 6.2, 9.0, 13.0, 16.3, 21.0, 23.5):
        output = clock.at(replay_second)
        assert output is not None
        assert clock.replay_at(output) == pytest.approx(replay_second, abs=1e-6)


def test_the_omissions_are_the_two_the_edit_makes(loaded):
    _replay, _track, clock = loaded
    found = [(round(at, 3), round(dropped, 3)) for at, dropped in presentation.omissions(clock)]
    assert found == [(2.8, 3.4), (11.6, 0.85)]


def test_the_releases_come_from_the_actuators(loaded):
    """The gates and the trapdoor are placed by the parts that moved."""
    replay, _track, clock = loaded
    gate = presentation.actuator_move(replay, clock, "start.paddle")
    trapdoor = presentation.actuator_move(replay, clock, "start.panel")
    assert gate == pytest.approx(0.817, abs=0.01)
    assert trapdoor == pytest.approx(3.217, abs=0.01)
    # The hook has to be gone before anything moves.
    assert gate > 0.80


# --- the projection ---------------------------------------------------------


def test_the_aim_lands_dead_centre(loaded):
    """A camera looking at a point puts that point in the middle of the frame."""
    _replay, track, _clock = loaded
    for cut in track["cuts"]:
        row = cut["frames"][len(cut["frames"]) // 2]
        placed = presentation.project(tuple(row[1:4]), tuple(row[4:7]), row[7], tuple(row[4:7]))
        assert placed is not None, cut["name"]
        assert placed[0] == pytest.approx(540.0, abs=1e-6), cut["name"]
        assert placed[1] == pytest.approx(960.0, abs=1e-6), cut["name"]


def test_the_screen_right_vector_is_right_handed():
    """A point to the camera's right must land on the right of the frame.

    `cameras.frame_report` writes this vector the other way round and is right
    to - it only compares absolute values. The first version here copied it, and
    the winner's ring came out on the wrong side of the marble.
    """
    camera = (0.0, 0.0, 10.0)
    aim = (0.0, 0.0, 0.0)          # looking along -Z, so +X is screen right
    right = presentation.project(camera, aim, 36.0, (1.0, 0.0, 0.0))
    left = presentation.project(camera, aim, 36.0, (-1.0, 0.0, 0.0))
    above = presentation.project(camera, aim, 36.0, (0.0, 1.0, 0.0))
    assert right is not None and left is not None and above is not None
    assert right[0] > 540.0 > left[0]
    assert above[1] < 960.0


def test_a_marble_projects_onto_itself(loaded):
    """The winner at its own crossing is inside the frame and about 60 px across."""
    replay, track, clock = loaded
    rows = presentation.screen_track(replay, track, clock, 5, (17.09, 17.12))
    assert rows, "the winner is not on screen when it crosses"
    _when, x, y, radius = rows[0]
    assert 0 <= x <= 1080 and 0 <= y <= 1920
    assert 25.0 <= radius <= 45.0


# --- what the sound is made of ---------------------------------------------


def test_the_residual_is_the_contact_impulse_not_the_velocity_change(loaded):
    """Removing gravity turns `dv` into the force a surface actually applied.

    The consequences are worth stating, because they are the whole reason the
    impact floor means anything. A marble in **free fall** has no contact and
    scores near zero however fast it is going. A marble **resting or rolling**
    is being held up, so it scores exactly the weight it is being held up by -
    245.25 / 60 = 4.0875 - which is why that is the median of the whole signal
    and why it is the ninetieth percentile of the raw `|dv|` as well. And an
    **impact** scores the impulse above that, so the floor of 11 wu/s is
    "two and a half times the marble's own weight" rather than an arbitrary
    number.
    """
    replay, _track, clock = loaded
    weight = presentation.GRAVITY / 60.0
    assert weight == pytest.approx(4.0875, abs=1e-4)
    raw = presentation.residuals(replay, clock)
    magnitudes = sorted(event.magnitude for event in raw)
    median = magnitudes[len(magnitudes) // 2]
    assert median == pytest.approx(weight, abs=0.35), "a supported field reads its own weight"

    # A marble the trapdoor has just dropped is in free fall and touching
    # nothing, so its contact impulse is near zero while its speed is not.
    falling = [
        event for event in raw
        if 6.35 <= event.replay <= 6.45 and event.module == "start"
    ]
    assert falling, "the drop is not in the replay where it was measured"
    assert min(event.magnitude for event in falling) < 1.0


def test_contacts_are_rationed_rather_than_merely_loud(loaded):
    """At a bare magnitude floor this race has 83 contacts a second."""
    replay, _track, clock = loaded
    flat = [e for e in presentation.residuals(replay, clock) if e.magnitude >= 6.0]
    thinned = presentation.impacts(replay, clock)
    assert len(flat) / 19.15 > 60.0
    assert 5.0 <= len(thinned) / 19.15 <= 20.0
    # One per marble per refractory span.
    last: dict[int, float] = {}
    for event in thinned:
        previous = last.get(event.marble)
        if previous is not None:
            assert event.at - previous >= 0.11 - 1e-6
        last[event.marble] = event.at


def test_every_impact_is_inside_the_film(loaded):
    replay, _track, clock = loaded
    for event in presentation.impacts(replay, clock):
        assert clock.hold - 1e-6 <= event.at <= clock.duration + 1e-6


# --- the mix ----------------------------------------------------------------


@pytest.fixture(scope="module")
def mix(loaded):
    from audio import marble

    replay, track, clock = loaded
    return marble.build_race_audio(replay, track, clock), clock, replay


def test_the_soundtrack_is_exactly_as_long_as_the_picture(mix):
    built, clock, _replay = mix
    assert len(built.left) == len(built.right)
    assert len(built.left) == int(round(clock.duration * built.sample_rate))
    assert built.seconds == pytest.approx(1192 / 60.0, abs=1e-6)


def test_the_limiter_stays_idle(mix):
    """A limiter working hard is a machine for removing the difference between
    loud things, and the finish is where those differences are the point."""
    built, _clock, _replay = mix
    assert built.limited is False
    assert built.peak_after <= 0.8611


def test_the_winner_is_the_loudest_thing_in_the_film(mix):
    import numpy as np

    built, clock, replay = mix
    mono = 0.5 * (np.array(built.left) + np.array(built.right))
    hop = built.sample_rate // 100
    envelope = np.array(
        [float(np.abs(mono[i * hop:(i + 1) * hop]).max()) for i in range(len(mono) // hop)]
    )
    crossings = sorted(
        (float(e["t"]), int(e["order"])) for e in replay["events"]
        if e["kind"] == "finish_line" and clock.at(float(e["t"])) is not None
    )
    assert len(crossings) == 6, "the film holds six of the eight crossings"

    def loudest(at: float) -> float:
        a = int(at * 100)
        return float(envelope[a:a + 25].max())

    levels = {order: loudest(clock.at(when)) for when, order in crossings}
    assert levels[1] == max(levels.values())
    # And the single loudest instant in the whole film is the winner crossing.
    assert abs(int(np.argmax(envelope)) / 100.0 - clock.at(crossings[0][0])) < 0.30


def test_both_routes_get_the_same_cue(mix):
    """Neither branch may be made to sound like the scripted winner."""
    from audio import marble

    built, _clock, _replay = mix
    assert built.placed.get("split") == 2
    a = marble.split_cue(marble.stable_seed("split", 5432))
    b = marble.split_cue(marble.stable_seed("split", 5432))
    assert list(a) == list(b), "the two placements are the same waveform"


def test_the_music_never_competes_with_the_machine():
    from audio import marble

    assert marble.LEVEL_MUSIC < marble.LEVEL_IMPACT_LOUD
    assert marble.LEVEL_MUSIC < marble.LEVEL_CROSS_OTHER
    assert marble.LEVEL_CROSS_WINNER > marble.LEVEL_CROSS_PHOTO > marble.LEVEL_CROSS_OTHER


# --- the marks --------------------------------------------------------------


def test_the_overlays_keep_a_phone_safe_gutter():
    for name, image in (("pick one", overlays.pick_one()), ("end fact", overlays.end_fact())):
        box = image.getbbox()
        assert box is not None, name
        left, _top, right, _bottom = box
        assert left >= 0.07 * overlays.WIDTH, (name, left)
        assert right <= 0.93 * overlays.WIDTH, (name, right)


def test_the_hook_sits_above_the_field(loaded):
    """The eight racers are at y 831 to 887 on the first frame."""
    replay, track, clock = loaded
    lowest = 0.0
    for marble_id in range(8):
        rows = presentation.screen_track(replay, track, clock, marble_id, (0.69, 0.72))
        if rows:
            lowest = max(lowest, rows[0][2] - rows[0][3])
    box = overlays.pick_one().getbbox()
    assert box[3] < lowest, (box[3], lowest)


def test_the_winners_mark_is_after_the_crossing_and_before_the_dead_heat(loaded):
    replay, _track, clock = loaded
    crossings = {
        int(e["order"]): clock.at(float(e["t"]))
        for e in replay["events"]
        if e["kind"] == "finish_line" and clock.at(float(e["t"])) is not None
    }
    from tools.sloped_short import WINNER_DELAY, WINNER_SECONDS

    start = crossings[1] + WINNER_DELAY
    end = start + WINNER_SECONDS
    assert start > crossings[1]
    assert end < min(crossings[4], crossings[5])
    assert 0.5 <= WINNER_SECONDS <= 0.8


def test_the_end_fact_covers_nobody(loaded):
    """Over the last 0.65 s every marble on screen is clear of the text band."""
    replay, track, clock = loaded
    from tools.sloped_short import END_FACT_SECONDS

    window = (clock.duration - END_FACT_SECONDS, clock.duration)
    box = overlays.end_fact().getbbox()
    top, bottom = box[1], box[3]
    for marble_id in range(8):
        for _when, x, y, radius in presentation.screen_track(
            replay, track, clock, marble_id, window
        ):
            if not (-radius <= x <= overlays.WIDTH + radius):
                continue
            if not (-radius <= y <= overlays.HEIGHT + radius):
                continue
            assert y + radius < top or y - radius > bottom, (marble_id, y, radius)


def test_no_route_labels_are_drawn():
    """The footage is colour-coded already; the split is marked in sound."""
    assert not hasattr(overlays, "route_label")
    assert "BLUE" not in overlays.__doc__.upper().split("**LABELS")[0].replace(
        "BLUE AND ORANGE", ""
    )

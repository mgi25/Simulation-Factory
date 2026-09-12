"""The edit omits replay time. It must never stretch or compress it.

V18 is a presentation edit of the V1.15 physics: it drops the establishing
shot, cuts three and a half seconds of the start's mixing, trims the spinner
corridor and rebuilds the finish lens, taking a 45 s replay to a 19 s film.

The one thing an edit of a *physics* record may not do is change how fast
anything moved. `sloped.cameras` therefore emits an **edit map** from output
time to replay time, and this pins the property that makes the map honest:
every segment has slope exactly one, so between two windows time is skipped and
inside a window it runs at the rate PyBullet produced.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sloped import cameras
from sloped.course import sloped_course

REPLAY = ROOT / "output" / "sloped_race_v1" / "race_5432.json"


@pytest.fixture(scope="module")
def track():
    if not REPLAY.is_file():
        pytest.skip("the selected replay is not built")
    replay = json.loads(REPLAY.read_text(encoding="utf-8"))
    machine = sloped_course(routes="both")
    return cameras.build_track(replay, machine, fps=60, edit=cameras.EDIT_V18), replay


def test_the_edit_never_changes_the_rate(track):
    """Slope one in every window: nothing is sped up or slowed down."""
    built, _replay = track
    assert built["edited"] is True
    segments = built["edit"]
    assert segments, "an edited track carries no map"
    for segment in segments:
        out_span = segment["out"][1] - segment["out"][0]
        replay_span = segment["replay"][1] - segment["replay"][0]
        assert out_span == pytest.approx(replay_span, abs=1e-6), segment


def test_the_map_is_monotone_and_tiles_the_output(track):
    """Output time is continuous; replay time may jump, and only forward."""
    built, _replay = track
    segments = built["edit"]
    cursor = 0.0
    last_replay = -1.0
    for segment in segments:
        assert segment["out"][0] == pytest.approx(cursor, abs=1e-6), segment
        cursor = segment["out"][1]
        assert segment["replay"][0] >= last_replay - 1e-6, "the edit runs backwards"
        last_replay = segment["replay"][1]
    assert built["duration"] == pytest.approx(cursor, abs=1e-6)


def test_the_edit_hits_its_brief(track):
    """The editorial decisions, as numbers rather than as intentions."""
    built, _replay = track
    segments = built["edit"]
    names = [segment["cut"] for segment in segments]
    # No establishing shot at all - the film opens on the eight racers.
    assert "establish" not in names
    assert names[0] == "start"
    assert segments[0]["replay"][0] < 0.5, "the opening is not the start line"
    # About two seconds of start-selection before the cut.
    first = segments[0]["out"][1] - segments[0]["out"][0]
    assert 1.5 <= first <= 2.5, first
    # An intentional jump that omits the mixing, and it is a jump rather than a
    # speed-up: the map is discontinuous in replay time and continuous in output.
    gap = segments[1]["replay"][0] - segments[0]["replay"][1]
    assert gap > 3.0, f"only {gap:.2f} s of mixing omitted"
    assert segments[1]["out"][0] == pytest.approx(segments[0]["out"][1], abs=1e-6)
    # The trapdoor opens at 6.10; the second window has to be on screen for it.
    assert segments[1]["replay"][0] < 6.10 < segments[1]["replay"][1]
    # Total running time.
    assert 19.0 <= built["duration"] <= 21.0, built["duration"]
    # The finish is the longest shot in the film and ends after the fifth racer.
    finish = [s for s in segments if s["cut"] == "finish"][-1]
    assert finish["replay"][1] > 22.70, "the edit cuts before fourth and fifth land"
    longest = max(s["out"][1] - s["out"][0] for s in segments)
    assert finish["out"][1] - finish["out"][0] == pytest.approx(longest, abs=1e-6)


def test_the_finish_lens_is_closer_than_the_sequence_default(track):
    """The finish was rebuilt to put the line and the leaders large in frame."""
    built, _replay = track
    default = {cut.name: cut for cut in cameras.SECTIONS}["finish"]
    finish = [cut for cut in built["cuts"] if cut["name"] == "finish"][-1]
    assert finish["extent"] < default.extent, (finish["extent"], default.extent)
    assert finish["extent"] <= 14.0
    # Almost directly behind, so the sprint recedes up a portrait frame.
    assert finish["bearing"] >= 150.0


def test_an_unedited_track_still_tiles_the_replay(track):
    """The default path is untouched, so every earlier render reproduces."""
    _built, replay = track
    machine = sloped_course(routes="both")
    plain = cameras.build_track(replay, machine, fps=60)
    assert plain["edited"] is False
    assert plain["omitted"] == pytest.approx(0.0, abs=1e-6)
    previous = None
    for cut in plain["cuts"]:
        if previous is not None:
            assert cut["from"] == pytest.approx(previous, abs=1e-6)
        previous = cut["to"]
    assert not cameras.check_track(plain, replay) or all(
        "against the previous cut" not in problem
        for problem in cameras.check_track(plain, replay)
    )


def test_a_gap_is_only_forgiven_on_an_edited_track(track):
    """The continuity check still has teeth where it should."""
    built, replay = track
    assert all(
        "against the previous cut" not in problem
        for problem in cameras.check_track(built, replay)
    )
    pretend = dict(built)
    pretend["edited"] = False
    problems = cameras.check_track(pretend, replay)
    assert any("against the previous cut" in problem for problem in problems), (
        "an unedited track with gaps has to be reported"
    )

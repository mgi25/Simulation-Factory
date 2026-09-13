"""V22 is three passes joined by one clock. These pin the joins.

Each prototype was measured on its own branch and each of those suites still
runs. What none of them could check is the thing integration actually built: a
film whose output clock has *two* stretches in front of the master, whose race
windows come from a different edit plan than V21's, and whose opening two
seconds are footage no replay instant maps into.

So the questions here are the ones that only exist once the three are together.

* **Is the preview an output-time prefix, and is it the right length?** The
  preview costs the clock `frames / fps`, not the `duration` its own report
  prints - those differ by a frame and the difference would move every cue in
  the film. `replay_at` must say "nothing" inside it and `at` must never map a
  replay second into it.
* **Is V21 still V21?** `prefix` defaults to zero and every edition before V22
  passes zero, so every number `Clock` returns for V20, V21.1 and V21 has to be
  the number it returned before this branch existed.
* **Is the pacing the one the research recommended?** Candidate A's two start
  bounds, the restored obstacle and the extended finish are four window edges in
  `cameras.EDITS["v22"]`, and the other seven windows must be V21.2's untouched.
* **Is there exactly one omission after the start?** That is the whole claim
  behind "one whoosh", and it is read off the edit map rather than asserted.
* **Does the race still finish the way it finished?** Order, crossings and seed
  are inputs to all of this and none of them may move.
* **Does the preview actually arrive on the race camera?** The opening's claim
  is that there is no cut between the two, which is a statement about two
  numbers in two files and is checkable as one.
* **Does the renderer's cut-boundary fix change what V21 renders?** It must fix
  a frame-indexed track and be a no-op on a station-bounded one, and "no-op" is
  checkable over all 1150 frames rather than by argument.

The physics, the seed, the replay and the course are inputs. Nothing in this
file writes anything.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sloped import cameras, presentation, v22
from sloped.presentation import Clock

OUT = ROOT / "output" / "sloped_race_v1"
REPLAY = OUT / "race_5432.json"
V21_TRACK = OUT / "cameras_5432.json"
V22_TRACK = OUT / "cameras_v22_5432.json"
V22_PREVIEW = OUT / "preview_v22_5432.json"

FPS = 60
PREVIEW_FRAMES = 120
PREVIEW_PREFIX = PREVIEW_FRAMES / FPS          # 2.000 s of screen, not 1.9833
HOLD_FRAMES = 42
RACE_FRAMES = 1221                             # round(20.333667 * 60) + 1
FILM_FRAMES = PREVIEW_FRAMES + HOLD_FRAMES + RACE_FRAMES     # 1383 = 23.050 s

FINISH_ORDER = [5, 2, 7, 4, 1, 6, 3, 0]

# The pacing pass's recommended timeline, which is what `EDIT_V22` has to be.
RECOMMENDED = [
    ("start", 0.200000, 1.900000),
    ("start", 5.833333, 7.620000),
    ("descent", 7.620000, 8.620000),
    ("long", 8.620000, 9.800000),
    ("hairpin", 9.800000, 10.800000),
    ("straight", 10.800000, 12.000000),
    ("obstacle", 12.000000, 15.350000),
    ("split", 15.350000, 17.670000),
    ("branch", 17.670000, 19.070000),
    ("merge", 19.070000, 20.200000),
    ("finish", 20.200000, 24.467000),
]


def _segments():
    return tuple(
        (row["out"][0], row["out"][1], row["replay"][0], row["replay"][1])
        for row in json.loads(V22_TRACK.read_text(encoding="utf-8"))["edit"]
    )


def _clock(prefix: float = PREVIEW_PREFIX) -> Clock:
    return Clock(_segments(), fps=FPS, master_frames=RACE_FRAMES, prefix=prefix)


needs_track = pytest.mark.skipif(
    not V22_TRACK.is_file(), reason="the V22 camera track is not solved"
)
needs_replay = pytest.mark.skipif(
    not REPLAY.is_file(), reason="the locked replay is not in this tree"
)


# --- the edit plan ----------------------------------------------------------


def test_the_v22_edit_is_the_pacing_passs_recommended_timeline():
    """Four edges moved from V21.2, to the microsecond the research named."""
    got = [(row[0], row[1], row[2]) for row in cameras.EDITS["v22"]]
    assert len(got) == len(RECOMMENDED)
    for (name, low, high), (want_name, want_low, want_high) in zip(got, RECOMMENDED):
        assert name == want_name
        assert low == pytest.approx(want_low, abs=1e-6)
        assert high == pytest.approx(want_high, abs=1e-6)


def test_the_seven_windows_v22_does_not_touch_are_v212s_exactly():
    """The pacing pass moved four edges. It may not have moved a fifth."""
    moved = {("start", 0), ("start", 1), ("obstacle", 6), ("finish", 10)}
    for index, (v212, v22_row) in enumerate(
        zip(cameras.EDITS["v212"], cameras.EDITS["v22"])
    ):
        if (v212[0], index) in moved:
            continue
        assert v212[1] == v22_row[1], f"window {index} ({v212[0]}) moved its start"
        assert v212[2] == v22_row[2], f"window {index} ({v212[0]}) moved its end"


def test_the_v22_edit_keeps_every_v212_lens_except_the_starts_opening_orbit():
    """V22 is a pacing and camera-language change, not a re-lensing of V21.2."""
    for index, (v212, v22_row) in enumerate(
        zip(cameras.EDITS["v212"], cameras.EDITS["v22"])
    ):
        before = dict(v212[3]) if len(v212) > 3 else {}
        after = dict(v22_row[3]) if len(v22_row) > 3 else {}
        if index == 0:
            assert after.pop("orbit") == cameras.V22_START_ORBIT
        assert after == before, f"window {index} ({v212[0]}) changed its lens"


def test_candidate_as_dial_is_where_the_start_stops():
    """Replay 1.900 is master frame 102 of the old window, and the dial's setting."""
    start = cameras.EDITS["v22"][0]
    assert start[2] == pytest.approx(1.900, abs=1e-9)
    frames = (start[2] - start[1]) * FPS
    assert frames == pytest.approx(102.0, abs=1e-6)


def test_the_restored_obstacle_covers_the_leaders_escape():
    """Replay 14.9958 - marble 7 out of the spinner - was omitted and is not now."""
    obstacle = next(row for row in cameras.EDITS["v22"] if row[0] == "obstacle")
    assert obstacle[1] <= 14.9958 <= obstacle[2]
    v212 = next(row for row in cameras.EDITS["v212"] if row[0] == "obstacle")
    assert not v212[1] <= 14.9958 <= v212[2], "V21 is supposed to have cut this"


def test_the_extended_finish_reaches_past_the_last_crossing():
    finish = next(row for row in cameras.EDITS["v22"] if row[0] == "finish")
    assert finish[2] >= 24.4167, "the eighth marble crosses at 24.4167"


# --- the clock --------------------------------------------------------------


def test_the_preview_prefix_is_frames_over_fps_not_the_reports_duration():
    """1.9833 s is the span of the frame centres; 120 frames hold 2.000 s."""
    assert PREVIEW_PREFIX == pytest.approx(2.0, abs=1e-12)
    assert PREVIEW_PREFIX != pytest.approx(1.9833, abs=1e-4)


@needs_track
def test_the_film_is_preview_plus_hold_plus_master():
    clock = _clock()
    assert clock.prefix_frames == PREVIEW_FRAMES
    assert clock.hold_frames == HOLD_FRAMES
    assert clock.frames == FILM_FRAMES
    assert clock.duration == pytest.approx(FILM_FRAMES / FPS, abs=1e-12)
    assert clock.origin == pytest.approx(PREVIEW_PREFIX + clock.hold, abs=1e-12)


@needs_track
def test_no_replay_second_maps_into_the_preview():
    """The preview is not the race, so nothing about the race may land in it."""
    clock = _clock()
    for _out_from, _out_to, replay_from, replay_to in clock.segments:
        for when in (replay_from, 0.5 * (replay_from + replay_to), replay_to):
            assert clock.at(when) >= clock.prefix - 1e-9


@needs_track
def test_replay_at_says_nothing_during_the_preview_and_the_first_frame_during_the_hold():
    clock = _clock()
    for frame in range(PREVIEW_FRAMES):
        assert clock.replay_at(frame / FPS) is None
        assert clock.in_preview(frame / FPS)
    first = clock.segments[0][2]
    for frame in range(PREVIEW_FRAMES, PREVIEW_FRAMES + HOLD_FRAMES):
        assert clock.replay_at(frame / FPS) == pytest.approx(first, abs=1e-9)
        assert not clock.in_preview(frame / FPS)


@needs_track
def test_the_prefix_shifts_every_cue_by_exactly_the_preview():
    """A preview is a translation of the race clock and nothing else."""
    with_preview = _clock()
    without = _clock(prefix=0.0)
    for _of, _ot, replay_from, replay_to in without.segments:
        for when in (replay_from, 0.5 * (replay_from + replay_to), replay_to):
            assert with_preview.at(when) - without.at(when) == pytest.approx(
                PREVIEW_PREFIX, abs=1e-9
            )


@needs_track
def test_the_film_never_repeats_rewinds_or_changes_rate():
    """Every frame after the hold steps forward, and by one frame or a cut."""
    clock = _clock()
    shown = [
        clock.replay_at(frame / FPS)
        for frame in range(PREVIEW_FRAMES + HOLD_FRAMES, clock.frames)
    ]
    assert all(value is not None for value in shown)
    steps = [b - a for a, b in zip(shown, shown[1:])]
    assert min(steps) > 0.0, "the film rewinds or holds a frame"
    ordinary = [step for step in steps if step < 0.5]
    assert max(ordinary) == pytest.approx(1.0 / FPS, abs=1e-6)
    assert min(ordinary) == pytest.approx(1.0 / FPS, abs=1e-6)


@needs_track
def test_there_is_exactly_one_omission_and_it_is_in_the_start():
    """One omission, one whoosh. The obstacle's is gone because the chase is whole."""
    clock = _clock()
    gaps = presentation.omissions(clock)
    assert len(gaps) == 1, f"expected one omission, got {gaps}"
    at, dropped = gaps[0]
    assert dropped == pytest.approx(5.833333 - 1.900, abs=1e-6)
    assert at == pytest.approx(clock.origin + 1.700, abs=1e-6)


@needs_track
def test_the_v21_editions_clock_is_untouched_by_the_prefix_field():
    """V20 and V21 pass no prefix, so every number they read is the old one."""
    segments = tuple(
        (row["out"][0], row["out"][1], row["replay"][0], row["replay"][1])
        for row in json.loads(V21_TRACK.read_text(encoding="utf-8"))["edit"]
    )
    clock = Clock(segments, fps=FPS, master_frames=1150)
    assert clock.prefix == 0.0
    assert clock.prefix_frames == 0
    assert clock.origin == clock.hold
    assert clock.frames == 1150 + HOLD_FRAMES
    assert clock.duration == pytest.approx(1192 / FPS, abs=1e-12)
    assert clock.replay_at(0.0) == pytest.approx(segments[0][2], abs=1e-9)
    assert not clock.in_preview(0.0)
    assert clock.at(segments[0][2]) == pytest.approx(clock.hold, abs=1e-9)


@needs_track
def test_omit_frames_carries_the_prefix_through():
    """V22 makes no frame cut, but a clock that loses its prefix would be silent."""
    clock = _clock()
    cut, _keep = presentation.omit_frames(clock, ((10, 20),))
    assert cut.prefix == clock.prefix


# --- the race is still the race ---------------------------------------------


@needs_replay
def test_the_seed_and_the_finish_order_are_the_locked_ones():
    replay = json.loads(REPLAY.read_text(encoding="utf-8"))
    assert int(replay["seed"]) == 5432
    order = sorted(
        (int(event["order"]), int(event["id"]))
        for event in replay["events"]
        if event["kind"] == "finish_line"
    )
    assert [marble for _place, marble in order] == FINISH_ORDER


@needs_replay
@needs_track
def test_every_one_of_the_eight_crossings_is_in_the_film():
    """V21 showed six of eight. The extended finish is the whole point of V22's tail."""
    replay = json.loads(REPLAY.read_text(encoding="utf-8"))
    clock = _clock()
    crossings = [
        float(event["t"])
        for event in replay["events"]
        if event["kind"] == "finish_line"
    ]
    assert len(crossings) == 8
    placed = [clock.at(when) for when in crossings]
    assert all(value is not None for value in placed), "a crossing is not in the film"
    assert max(placed) <= clock.duration + 1e-9


@needs_replay
def test_v21s_finish_window_really_did_cut_two_of_them():
    """The defect V22's finish extension exists to fix, stated as a test."""
    replay = json.loads(REPLAY.read_text(encoding="utf-8"))
    v212_finish = next(row for row in cameras.EDITS["v212"] if row[0] == "finish")
    late = [
        float(event["t"])
        for event in replay["events"]
        if event["kind"] == "finish_line" and float(event["t"]) > v212_finish[2]
    ]
    assert len(late) == 2


# --- the handoff ------------------------------------------------------------


@pytest.mark.skipif(
    not (V22_TRACK.is_file() and V22_PREVIEW.is_file()),
    reason="the V22 tracks are not solved",
)
def test_the_preview_lands_on_the_race_cameras_first_pose():
    """There is no cut between the preview and the race - so there is no step."""
    preview = json.loads(V22_PREVIEW.read_text(encoding="utf-8"))
    race = json.loads(V22_TRACK.read_text(encoding="utf-8"))
    last = preview["cuts"][-1]["frames"][-1]
    first = race["cuts"][0]["frames"][0]
    step = math.dist(last[1:4], first[1:4])
    turn = math.dist(last[4:7], first[4:7])
    assert step < 1e-3, f"the lens jumps {step:.4f} layout units at the handoff"
    assert turn < 1e-3, f"the aim jumps {turn:.4f} layout units at the handoff"


@pytest.mark.skipif(not V22_PREVIEW.is_file(), reason="the preview is not solved")
def test_the_preview_is_120_distinct_frames():
    """Boundary rows are shared on purpose, so counting rows over-counts."""
    preview = json.loads(V22_PREVIEW.read_text(encoding="utf-8"))
    assert v22.preview_frames(preview) == PREVIEW_FRAMES
    assert v22.preview_prefix(preview) == pytest.approx(PREVIEW_PREFIX, abs=1e-12)


@needs_track
def test_the_race_track_is_the_chase_between_two_bookends():
    """Five chase phases, two start windows and V21's finish: eight cuts."""
    race = json.loads(V22_TRACK.read_text(encoding="utf-8"))
    names = [cut["name"] for cut in race["cuts"]]
    assert names == ["start", "start", "descent", "obstacle", "fork",
                     "branches", "merge", "finish"]
    assert race["chase"] is True
    assert race["duration"] == pytest.approx(20.333667, abs=1e-5)


@needs_track
def test_the_chase_covers_the_middle_of_the_race_without_a_break():
    """Which is why the obstacle needed restoring in the plan and nowhere else."""
    race = json.loads(V22_TRACK.read_text(encoding="utf-8"))
    middle = [row for row in race["edit"] if row["cut"] not in ("start", "finish")]
    for before, after in zip(middle, middle[1:]):
        assert before["replay"][1] == pytest.approx(after["replay"][0], abs=1e-9)
    assert middle[0]["replay"][0] == pytest.approx(7.620, abs=1e-6)
    assert middle[-1]["replay"][1] == pytest.approx(20.200, abs=1e-6)


# --- the renderer's cut-boundary fix ----------------------------------------


def _place(track: dict, seconds: float, fixed: bool):
    """`sloped_race_scene._place_from_track`'s lookup, transcribed.

    Kept in step with the GDScript by hand, which is what makes the two tests
    below worth having: they are the only place the fix's claim - that it
    repairs a frame-indexed track and cannot disturb a station-bounded one - is
    written down as arithmetic.
    """
    cuts = track["cuts"]
    fps = float(track.get("fps", 60))
    half = 0.5 / fps
    index = len(cuts) - 1
    for position, cut in enumerate(cuts):
        if seconds <= float(cut["to"]):
            index = position
            break
    if fixed:
        while index > 0:
            rows = cuts[index]["frames"]
            if not rows or seconds >= float(rows[0][0]) - half:
                break
            index -= 1
    rows = cuts[index]["frames"]
    first, last = float(rows[0][0]), float(rows[-1][0])
    at = (min(max(seconds, first), last) - first) * fps
    low = min(max(int(at // 1), 0), len(rows) - 1)
    high = min(low + 1, len(rows) - 1)
    blend = max(0.0, min(1.0, at - low))
    return tuple(
        round(rows[low][k] + (rows[high][k] - rows[low][k]) * blend, 6)
        for k in range(1, 8)
    )


def _replay_at(edit, output: float) -> float:
    for index, segment in enumerate(edit):
        low, high = float(segment["out"][0]), float(segment["out"][1])
        if output <= high or index == len(edit) - 1:
            span = float(segment["replay"][1]) - float(segment["replay"][0])
            return float(segment["replay"][0]) + min(max(output - low, 0.0), span)
    return output


@pytest.mark.skipif(not V22_PREVIEW.is_file(), reason="the preview is not solved")
def test_the_boundary_fix_repairs_a_frame_indexed_track():
    """A frame-indexed track duplicates frames at its joins, and must not.

    The course-preview pass found this and worked around it in the track it
    writes, by carrying one row past each cut's own last frame; on the
    prototype's flight the fault was frames 17/18, 47/48 and 83/84. Which
    frames duplicate depends on where the landmark boundaries fall, so what is
    pinned here is the property rather than those indices: strip the workaround
    and the unfixed lookup repeats frames, the fixed one does not, and with the
    workaround in place both are already clean.
    """
    import copy

    track = json.loads(V22_PREVIEW.read_text(encoding="utf-8"))
    bare = copy.deepcopy(track)
    for cut in bare["cuts"][:-1]:
        cut["frames"] = cut["frames"][:-1]
        cut["to"] = cut["frames"][-1][0]

    def duplicates(source, fixed):
        poses = [_place(source, frame / FPS, fixed) for frame in range(PREVIEW_FRAMES)]
        return [f for f in range(1, PREVIEW_FRAMES) if poses[f] == poses[f - 1]]

    joins = len(bare["cuts"]) - 1
    broken = duplicates(bare, False)
    assert broken, "the bug this fix exists for did not reproduce"
    assert len(broken) <= joins, "a duplicate appeared away from a cut boundary"
    assert duplicates(bare, True) == []
    # And the workaround the preview pass shipped is still enough on its own.
    assert duplicates(track, False) == []
    assert duplicates(track, True) == []


@pytest.mark.skipif(not V21_TRACK.is_file(), reason="the V21 track is not in this tree")
def test_the_boundary_fix_cannot_disturb_the_v21_render():
    """Station-bounded cuts never land a frame on a boundary: 1150 of 1150 agree."""
    track = json.loads(V21_TRACK.read_text(encoding="utf-8"))
    frames = int(round(float(track["duration"]) * FPS)) + 1
    for frame in range(frames):
        seconds = _replay_at(track["edit"], frame / FPS)
        assert _place(track, seconds, False) == _place(track, seconds, True)

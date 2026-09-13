"""V22 proposes putting time back. These pin what putting it back may not do.

A pacing pass is allowed to change exactly one thing - **which of the master's
frames are in the film** - and the tempting ways to change anything else are all
invisible in a finished MP4. So the suite asks the same four questions the
retention pass asked, plus the two this pass adds.

* **Is the arithmetic exact?** Master frame `f` of the first window shows replay
  `0.200 + f/60` and every candidate is named by the frame it stops on, so a
  candidate's claimed cut point is checkable to the frame rather than to the
  tenth.
* **Does the film ever repeat, rewind or change rate?** Every candidate's clock
  steps forwards at every frame boundary, by exactly one frame except at an
  omission, and each window still runs one second of replay per second of film.
* **Are the omissions where they are said to be?** Restoring footage moves the
  start omission's near edge and nothing else; the later omission and every
  window after it are byte-identical decisions.
* **Is the physics still in the film?** Contacts are counted off the replay, not
  asserted - a candidate that claims 15 of 15 has to have all fifteen.
* **Is the criterion the measurement says it is?** `CHURN_FLOOR` separates the
  parked drum from everything the film keeps with a factor of four and no
  overlap, and that separation is the only reason any of these cuts is
  defensible. If new footage ever lands in the gap, this suite says so.
* **Does the proof clip promise anything it cannot show?** The two restorations
  are replay the camera track never covered. Nothing here may quietly pretend
  they can be cut out of a master that does not contain them.

The physics, the seed, the replay, the course, every camera pose, the edit map
and `real_race_v21_master.mp4` are inputs and none of them is touched.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sloped import presentation, v22_timeline
from sloped.v22_timeline import CANDIDATES, CHURN_FLOOR

OUT = ROOT / "output" / "sloped_race_v1"
REPLAY = OUT / "race_5432.json"
TRACK = OUT / "cameras_5432.json"

MASTER_FRAMES = 1150
HOLD_FRAMES = 42
FPS = 60

# The digest of the replay every figure in this pass was measured against. If
# it changes, nothing below means what it says.
DIGEST = "aafb0d3d872e6c5f6db3a6f52d567ae073f1888fbac4ea4970867c130cf17de6"

# Master frame 0 of the first window is replay 0.200, and the window runs to
# frame 126 / replay 2.300. Each candidate is "keep to this frame".
WINDOW_ZERO_FROM = 0.200
LAST_KEPT = {"v21": 48, "a": 102, "b": 114, "c": 126}

# Measured, not chosen: contacts in the drum at or before each cut point.
HITS = {"v21": 7, "a": 13, "b": 15, "c": 15}
DRUM_HITS = 15
HARDEST = 9.083523        # replay 1.1875, marbles 0 and 3 - the drum's biggest
LAST_HIT = 2.0125         # replay of the drum's final contact, marbles 4 and 5


@pytest.fixture(scope="module")
def loaded():
    if not REPLAY.is_file() or not TRACK.is_file():
        pytest.skip("the selected replay or its camera track is not built")
    replay, track, base = presentation.load(str(REPLAY), str(TRACK), MASTER_FRAMES)
    return replay, track, base


@pytest.fixture(scope="module")
def clocks(loaded):
    _replay, _track, base = loaded
    return {
        key: v22_timeline.candidate_clock(base, candidate)
        for key, candidate in CANDIDATES.items()
    }


def _shown(clock: presentation.Clock) -> list[float]:
    return [
        clock.replay_at(clock.hold + frame / FPS)
        for frame in range(clock.master_frames)
    ]


# --- the inputs are the ones this pass measured ------------------------------


def test_the_replay_is_the_one_every_figure_came_from(loaded):
    replay, _track, _base = loaded
    assert replay["digest"] == DIGEST
    assert int(replay["seed"]) == 5432


def test_the_master_map_is_the_locked_eleven_windows(loaded):
    _replay, track, base = loaded
    assert len(base.segments) == 11
    assert [row["cut"] for row in track["edit"]][:2] == ["start", "start"]
    assert base.segments[0][2:] == (0.2, 2.3)
    assert base.segments[1][2:] == (5.7, 7.62)
    assert base.master_frames == MASTER_FRAMES


# --- exact frame arithmetic --------------------------------------------------


def test_a_first_window_frame_shows_replay_02_plus_f_over_60(loaded):
    _replay, _track, base = loaded
    for frame in (0, 1, 48, 97, 102, 114, 126):
        shown = base.replay_at(base.hold + frame / FPS)
        assert shown == pytest.approx(WINDOW_ZERO_FROM + frame / FPS, abs=1e-9)


@pytest.mark.parametrize("key", sorted(LAST_KEPT))
def test_each_candidate_stops_on_the_frame_it_is_named_for(key, clocks):
    clock, keep = clocks[key]
    last = LAST_KEPT[key]
    assert clock.segments[0][3] == pytest.approx(
        WINDOW_ZERO_FROM + last / FPS, abs=1e-6
    )
    # The keep list is two runs: everything to the cut, then everything after.
    assert keep[0] == (0, last)
    assert keep[-1][1] == MASTER_FRAMES - 1


@pytest.mark.parametrize("key", sorted(LAST_KEPT))
def test_runtime_is_the_frame_count_and_nothing_else(key, clocks):
    clock, keep = clocks[key]
    kept = sum(last - first + 1 for first, last in keep)
    assert clock.master_frames == kept
    assert clock.frames == kept + HOLD_FRAMES
    assert clock.duration == pytest.approx(clock.frames / FPS, abs=1e-12)


def test_the_dial_only_ever_adds_frames(clocks):
    order = ["v21", "a", "b", "c"]
    runtimes = [clocks[key][0].duration for key in order]
    assert runtimes == sorted(runtimes)
    # and every one of them is under V20, which kept the whole master.
    assert max(runtimes) < (MASTER_FRAMES + HOLD_FRAMES) / FPS


# --- monotonic replay time, no duplicate or backward frames ------------------


@pytest.mark.parametrize("key", sorted(CANDIDATES))
def test_the_film_never_repeats_or_rewinds(key, clocks):
    clock, _keep = clocks[key]
    shown = _shown(clock)
    assert all(one is not None for one in shown)
    for index, (before, after) in enumerate(zip(shown, shown[1:])):
        assert after > before, f"{key}: frame {index + 1} does not move forwards"


@pytest.mark.parametrize("key", sorted(CANDIDATES))
def test_every_step_is_one_frame_except_at_the_omissions(key, clocks):
    clock, _keep = clocks[key]
    shown = _shown(clock)
    steps = [after - before for before, after in zip(shown, shown[1:])]
    jumps = [one for one in steps if one > 1.5 / FPS]
    ordinary = [one for one in steps if one <= 1.5 / FPS]
    assert len(jumps) == 2, f"{key}: expected two omissions, found {len(jumps)}"
    for one in ordinary:
        assert one == pytest.approx(1 / FPS, abs=2e-6)


@pytest.mark.parametrize("key", sorted(CANDIDATES))
def test_the_rate_is_one_second_of_replay_per_second_of_film(key, clocks):
    clock, _keep = clocks[key]
    for index, (out_from, out_to, replay_from, replay_to) in enumerate(clock.segments):
        assert (out_to - out_from) == pytest.approx(replay_to - replay_from, abs=2e-6), (
            f"{key}: window {index} is a speed change"
        )


@pytest.mark.parametrize("key", sorted(CANDIDATES))
def test_verify_passes_on_every_candidate(key, clocks, loaded):
    _replay, _track, base = loaded
    clock, keep = clocks[key]
    assert v22_timeline.verify(clock, keep, base) == []


def test_verify_catches_a_clock_that_repeats_a_frame(loaded):
    """The suite's own check, checked: a rewind has to be caught."""
    _replay, _track, base = loaded
    broken = presentation.Clock(
        segments=(
            (0.0, 1.0, 5.0, 6.0),
            (1.0, 2.0, 5.5, 6.5),      # steps backwards into footage already shown
        ),
        hold=base.hold,
        fps=FPS,
        master_frames=121,
    )
    findings = v22_timeline.verify(broken, ((0, 120),), base)
    assert findings, "a rewinding clock was accepted"
    assert any("repeat" in one or "rewind" in one for one in findings)


# --- omission boundaries -----------------------------------------------------


@pytest.mark.parametrize("key", sorted(LAST_KEPT))
def test_the_start_omission_runs_from_the_cut_to_5_833333(key, clocks):
    clock, _keep = clocks[key]
    near = clock.segments[0][3]
    far = clock.segments[1][2]
    assert near == pytest.approx(WINDOW_ZERO_FROM + LAST_KEPT[key] / FPS, abs=1e-6)
    assert far == pytest.approx(5.833333, abs=1e-6)


@pytest.mark.parametrize("key", sorted(CANDIDATES))
def test_the_later_omission_is_untouched_at_0_850_seconds(key, clocks):
    """No candidate here restores it. Only a re-rendered master can."""
    clock, _keep = clocks[key]
    omissions = presentation.omissions(clock)
    assert len(omissions) == 2
    assert omissions[1][1] == pytest.approx(0.850, abs=1e-6)


@pytest.mark.parametrize("key", sorted(CANDIDATES))
def test_everything_after_the_start_is_the_same_decision(key, clocks, loaded):
    """Windows 2 to 10 keep their replay spans exactly; only their clock moves."""
    _replay, _track, base = loaded
    clock, _keep = clocks[key]
    for index in range(2, len(base.segments)):
        assert clock.segments[index][2:] == base.segments[index][2:], (
            f"{key}: window {index} changed which replay it covers"
        )


def test_the_restorations_are_outside_every_master_this_pass_can_cut(loaded):
    _replay, _track, base = loaded
    covered = [(row[2], row[3]) for row in base.segments]
    for restoration in v22_timeline.RESTORATIONS:
        inside = any(
            low - 1e-9 <= restoration.replay_from and restoration.replay_to <= high + 1e-9
            for low, high in covered
        )
        assert not inside, (
            f"{restoration.replay_from}-{restoration.replay_to} is on the map; "
            "it would not need a re-render"
        )
        assert restoration.proven is False


# --- event inclusion ---------------------------------------------------------


@pytest.mark.parametrize("key", sorted(HITS))
def test_the_drum_contacts_each_candidate_keeps(key, clocks, loaded):
    replay, _track, _base = loaded
    clock, _keep = clocks[key]
    kept, gone = v22_timeline.retained_collisions(replay, clock)
    assert len(kept) + len(gone) == DRUM_HITS
    assert len(kept) == HITS[key], f"{key}: {len(kept)} contacts, expected {HITS[key]}"


def test_v21_is_the_only_candidate_that_cuts_the_hardest_hit(clocks, loaded):
    replay, _track, _base = loaded
    for key in ("v21", "a", "b", "c"):
        clock, _keep = clocks[key]
        kept, _gone = v22_timeline.retained_collisions(replay, clock)
        hardest = max((float(one["speed"]) for one in kept), default=0.0)
        if key == "v21":
            assert hardest < HARDEST
        else:
            assert hardest == pytest.approx(HARDEST, abs=1e-6)


def test_b_and_c_carry_the_drum_s_final_contact_and_a_does_not(clocks):
    assert CANDIDATES["a"].cuts[0][0] - 1 < (LAST_HIT - WINDOW_ZERO_FROM) * FPS
    for key in ("b", "c"):
        clock, _keep = clocks[key]
        assert clock.at(LAST_HIT) is not None, f"{key} cuts the drum's last hit"
    clock, _keep = clocks["a"]
    assert clock.at(LAST_HIT) is None


@pytest.mark.parametrize("key", sorted(CANDIDATES))
def test_the_race_itself_is_untouched(key, clocks, loaded):
    """Same winner, same order, same six crossings in the film."""
    replay, _track, _base = loaded
    clock, _keep = clocks[key]
    crossings = sorted(
        (one for one in replay["events"] if one["kind"] == "finish_line"),
        key=lambda one: int(one["order"]),
    )
    assert [int(one["id"]) for one in crossings] == [5, 2, 7, 4, 1, 6, 3, 0]
    shown = [one for one in crossings if clock.at(float(one["t"])) is not None]
    assert len(shown) == 6
    assert int(shown[0]["id"]) == 5
    assert clock.at(20.85) is not None


# --- the criterion -----------------------------------------------------------


def test_the_parked_drum_is_under_the_floor_everywhere(loaded):
    replay, _track, _base = loaded
    slices = v22_timeline.activity(replay, 2.300, 5.700)
    assert slices
    worst = max(one.churn for one in slices)
    assert worst < CHURN_FLOOR, f"the dead stretch reaches {worst:.2f}"
    assert all(one.collisions == 0 for one in slices)


def test_nothing_the_film_keeps_after_the_start_is_under_the_floor(loaded):
    replay, _track, base = loaded
    for index in range(2, len(base.segments)):
        _o0, _o1, r0, r1 = base.segments[index]
        for one in v22_timeline.activity(replay, r0, r1):
            assert one.churn >= CHURN_FLOOR, (
                f"window {index} has a slice at {one.replay_from:.3f} "
                f"scoring {one.churn:.2f} - there is trimmable footage after all"
            )


def test_both_restorations_are_live_by_the_same_measure(loaded):
    replay, _track, _base = loaded
    for restoration in v22_timeline.RESTORATIONS:
        score = v22_timeline.churn(
            replay, restoration.replay_from, restoration.replay_to
        )
        assert score > CHURN_FLOOR * 2, (
            f"{restoration.replay_from}-{restoration.replay_to} scores {score:.2f}"
        )


def test_the_floor_sits_in_a_gap_and_not_on_a_population(loaded):
    """The whole argument: dead and live do not overlap."""
    replay, _track, base = loaded
    dead = [one.churn for one in v22_timeline.activity(replay, 2.300, 5.700)]
    live: list[float] = []
    for index in range(2, len(base.segments)):
        _o0, _o1, r0, r1 = base.segments[index]
        live.extend(one.churn for one in v22_timeline.activity(replay, r0, r1))
    assert max(dead) < CHURN_FLOOR < min(live)
    assert min(live) / max(dead) > 1.4


# --- the cut gets less visible, not more -------------------------------------


def test_restoring_the_mixing_makes_the_join_less_visible(clocks, loaded):
    replay, _track, _base = loaded
    jumps = {}
    for key in ("v21", "a", "b", "c"):
        clock, _keep = clocks[key]
        jumps[key] = v22_timeline.cut_jump(replay, clock)[0][1]
    assert jumps["v21"] > 3.0
    for key in ("a", "b", "c"):
        assert jumps[key] < jumps["v21"] / 3.0, (
            f"{key} was supposed to hide the join, not widen it"
        )


def test_the_field_is_narrower_than_v21_s_own_jump(loaded):
    """3.76 wu is not just 'more'. It is most of the way across the drum."""
    replay, _track, _base = loaded
    field = v22_timeline.field_at(replay, 5.833333)
    spread = max(
        math.dist(a, b) for a in field.values() for b in field.values()
    )
    assert spread < 2 * 3.76


def test_only_one_candidate_cuts_on_motion_with_the_field_where_it_stays(
    clocks, loaded
):
    """The two halves of the tie-break, which pull against each other.

    Above the floor the omission reads as a skip; below it, as the machine
    stopping. A small jump means the far side is reconcilable with the near
    one. V21 passes the first and fails the second; B and C the reverse.
    """
    replay, _track, _base = loaded
    scored = {}
    for key in ("v21", "a", "b", "c"):
        clock, _keep = clocks[key]
        scored[key] = (
            v22_timeline.cut_on_motion(replay, clock),
            v22_timeline.cut_jump(replay, clock)[0][1],
        )
    passing = [
        key for key, (motion, jump) in scored.items()
        if motion >= CHURN_FLOOR and jump < 2.0
    ]
    assert passing == ["a"], f"expected only A to pass both, got {passing}"
    assert scored["v21"][0] > 5.0 and scored["v21"][1] > 3.0
    for key in ("b", "c"):
        assert scored[key][0] < CHURN_FLOOR

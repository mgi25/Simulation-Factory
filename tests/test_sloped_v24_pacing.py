"""What a V24 timeline has to be true of.

The pass makes one claim - **the film is the V22.1 master with whole frames
taken out of it** - and everything below is a way of failing that claim:

* the frames run forwards, once each, and so does the replay they carry;
* the clock is slope 1 everywhere, so a cue placed through it lands on the frame
  it names;
* the omission boundaries are the frames the plan says and not one either side;
* the events the brief says to keep are on screen, and the finish is seed 5432's;
* nothing the machine does is cut in half.

Two of them are about tools rather than films. `test_omit_frames_*` pins the
limitation in `presentation.omit_frames` that `v24_timeline.build` exists
because of - if somebody fixes `omit_frames`, that test fails and the workaround
can go. And `test_builder_agrees_with_production` pins the other half: where
`omit_frames` is right, the V24 builder gives the same answer, frame for frame.

The replay and the solved track are generated output and not in the branch, so
the tests that need them skip. The arithmetic tests build their own master and
run anywhere.
"""

from __future__ import annotations

import json
import math
import os

import pytest

from sloped.presentation import Clock, omit_frames
from sloped import v24_timeline
from sloped.v24_timeline import (
    ANTICIPATION,
    DRUM_FALSIFIED,
    FALL,
    FPS,
    MARBLE_WIDTH_BAR,
    Plan,
    RUNTIME_BOUNDS,
    SPIN,
    STOPPED,
    build,
    candidates,
    coverage,
    joins,
    kept_frames,
    load_master,
    machine_match,
    machine_state,
    omissions,
    production_clock,
    rejected,
    report,
    runs,
)

OUT_DIR = os.path.join("output", "sloped_race_v1")
REPLAY_PATH = os.path.join(OUT_DIR, "race_5432.json")
TRACK_PATH = os.path.join(OUT_DIR, "cameras_v221_5432.json")

FINISH_ORDER = [5, 2, 7, 4, 1, 6, 3, 0]
WINNER = 5
WINNER_AT = 20.850
MASTER_FRAMES = 1340

# The start mechanism, in replay seconds. Every one of these is re-derived from
# the recorded transforms by `test_machine_instants`, so this block is a
# statement of what the module's constants must equal rather than their source.
GATES = 0.316667
ROTOR_START = 1.616667
SPIN_DOWN = 4.616667
ROTOR_STOP = 4.916667
LIFT = 5.216667
LIFT_DONE = 5.666667
RELEASE = 6.116667


@pytest.fixture(scope="module")
def replay():
    if not os.path.isfile(REPLAY_PATH):
        pytest.skip(f"{REPLAY_PATH} is generated output and is not in the branch")
    with open(REPLAY_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def master():
    if not os.path.isfile(TRACK_PATH):
        pytest.skip(f"{TRACK_PATH} is generated output and is not in the branch")
    with open(TRACK_PATH, "r", encoding="utf-8") as handle:
        return load_master(json.load(handle))


@pytest.fixture(scope="module")
def plans(master):
    return candidates(master)


@pytest.fixture(scope="module")
def reports(master, replay, plans):
    return {key: report(master, replay, plan) for key, plan in plans.items()}


# --- the tool this pass could not use ---------------------------------------


def test_omit_frames_is_right_about_head_and_tail_cuts():
    """Production's cut - the shape every delivered edition uses - is correct.

    Two windows, a cut that takes the tail of the first and the head of the
    second. Each window's survivors stay contiguous, one segment carries each,
    and every kept frame shows the replay instant the clock says it does.
    """
    base = Clock(((0.0, 1.0, 0.0, 1.0), (1.0, 2.0, 5.0, 6.0)), hold=0.0, fps=60,
                 master_frames=121)
    cut, keep = omit_frames(base, ((40, 80),))
    kept = [frame for frame in range(121) if not 40 <= frame <= 80]
    assert keep == ((0, 39), (81, 120))
    assert cut.master_frames == len(kept)
    for position, frame in enumerate(kept):
        truth = frame / 60.0 if frame <= 60 else 5.0 + (frame / 60.0 - 1.0)
        assert cut.replay_at(position / 60.0) == pytest.approx(truth, abs=1e-6)


def test_omit_frames_cannot_represent_an_interior_cut():
    """...and is wrong about a cut in the middle of one, which is why `build` exists.

    One window, 100 frames of replay 0.000-1.650, thirty frames taken out of the
    middle. `omit_frames` returns a single segment spanning 1.15 s of output and
    1.65 s of replay - slope 1.43 - so every frame after the cut is mis-dated,
    by up to half a second.

    **If this test starts failing, `presentation.omit_frames` has been fixed and
    `v24_timeline.build` can be deleted in favour of it.**
    """
    base = Clock(((0.0, 1.65, 0.0, 1.65),), hold=0.0, fps=60, master_frames=100)
    cut, keep = omit_frames(base, ((30, 59),))
    assert keep == ((0, 29), (60, 99))
    assert len(cut.segments) == 1
    out_from, out_to, replay_from, replay_to = cut.segments[0]
    slope = (replay_to - replay_from) / (out_to - out_from)
    assert slope > 1.4, "omit_frames now splits interior cuts; see the docstring"
    # The concrete consequence: an instant the film does not contain is given an
    # output second anyway.
    assert cut.at(0.700) is not None


def test_builder_agrees_with_production_where_production_is_right(master):
    """A head-and-tail plan gives the same clock through either builder."""
    # `SPIN` is the head of window 1 and `FALL` is the tail of it, so every
    # window's survivors stay contiguous and `omit_frames` can carry the plan.
    plan = Plan(key="x", title="x", hold_frames=42, cuts=(SPIN, FALL),
                tail=master.frames - 1, note="")
    mine, my_keep = build(master, plan)
    theirs, their_keep = production_clock(master, plan)
    assert my_keep == their_keep
    assert mine.master_frames == theirs.master_frames
    assert mine.duration == pytest.approx(theirs.duration, abs=1e-9)
    for frame in kept_frames(master, plan):
        when = master.replay_of[frame]
        assert mine.at(when) == pytest.approx(theirs.at(when), abs=1e-6)


def test_production_clock_refuses_an_interior_plan(master):
    plan = Plan(key="x", title="x", hold_frames=42, cuts=(STOPPED,),
                tail=master.frames - 1, note="")
    with pytest.raises(ValueError, match="discontiguous"):
        production_clock(master, plan)


# --- the master -------------------------------------------------------------


def test_master_is_the_rendered_film(master):
    """1340 frames, eight windows, and the pose list agrees with the edit map.

    `load_master` raises if the concatenation rule stops matching the renderer,
    so reaching this line at all is most of the assertion; the rest pins the
    boundary frames the whole pass indexes against.
    """
    assert master.frames == MASTER_FRAMES
    assert len(master.segments) == 8
    assert master.names[0] == "start" and master.names[-1] == "final"
    assert master.replay_of[0] == pytest.approx(0.200)
    assert master.replay_of[111] == pytest.approx(2.050)
    assert master.replay_of[112] == pytest.approx(4.016667, abs=1e-6)
    assert master.replay_of[273] == pytest.approx(6.700)
    assert master.replay_of[274] == pytest.approx(6.716667, abs=1e-6)
    assert master.replay_of[MASTER_FRAMES - 1] == pytest.approx(24.466667, abs=1e-6)
    # The one hard lens change, and the one the fall trim is taken against.
    assert master.window_of(273) != master.window_of(274)


def test_master_replay_steps_one_frame_at_a_time_except_at_the_b116_gap(master):
    gaps = [
        (frame, master.replay_of[frame + 1] - master.replay_of[frame])
        for frame in range(master.frames - 1)
        if abs(master.replay_of[frame + 1] - master.replay_of[frame] - 1.0 / FPS) > 1e-6
    ]
    assert [frame for frame, _ in gaps] == [111]
    assert gaps[0][1] == pytest.approx(1.966667, abs=1e-6)


# --- the machine ------------------------------------------------------------


def test_machine_instants(replay):
    """The five instants the start's arithmetic is quoted against, re-derived.

    Read off the recorded transforms rather than compared to a table: if the
    replay ever changes, these fail here rather than silently moving every
    omission boundary in the module.
    """
    def first(prefix: str, key: str, test) -> float:
        previous = None
        for index in range(1, 600):
            when = round(index / FPS, 6)
            state = machine_state(replay, when)
            if previous is not None and test(previous, state):
                return when
            previous = state
        raise AssertionError(f"no {prefix} {key}")

    assert first("gate", "move", lambda a, b: abs(
        b["paddle_height"] - a["paddle_height"]) > 1e-4) == pytest.approx(GATES)
    assert first("rotor", "start", lambda a, b: b["rotor_rate"] > 1.0
                 ) == pytest.approx(ROTOR_START)
    assert first("panel", "move", lambda a, b: abs(
        b["panel_height"] - a["panel_height"]) > 1e-4) == pytest.approx(RELEASE)
    assert first("blade", "lift", lambda a, b: abs(
        b["rotor_height"] - a["rotor_height"]) > 1e-3) == pytest.approx(LIFT)

    assert machine_state(replay, 3.0)["rotor_rate"] == pytest.approx(13.0, abs=0.01)
    # `machine_state` reads the step *into* a frame, so the wind-down's first
    # frame is already below rate - which is what makes it the first frame.
    assert machine_state(replay, round(SPIN_DOWN - 1.0 / FPS, 6))["rotor_rate"]         == pytest.approx(13.0, abs=0.01)
    assert machine_state(replay, SPIN_DOWN)["rotor_rate"] < 13.0 - 0.05
    assert machine_state(replay, ROTOR_STOP)["rotor_rate"] < 0.05
    assert machine_state(replay, 5.900)["rotor_rate"] < 0.05

    # And the module's own constants are these numbers.
    assert v24_timeline.GATES_AT == pytest.approx(GATES)
    assert v24_timeline.ROTOR_AT == pytest.approx(ROTOR_START)
    assert v24_timeline.SPIN_DOWN_AT == pytest.approx(SPIN_DOWN)
    assert v24_timeline.LIFT_AT == pytest.approx(LIFT)
    assert v24_timeline.RELEASE_AT == pytest.approx(RELEASE)


def test_one_rotor_revolution_is_29_frames(replay):
    per_frame = math.degrees(13.0 / FPS)
    assert per_frame == pytest.approx(12.4139, abs=1e-3)
    assert round(360.0 / per_frame) == 29
    # **A join that omits N frames spans N+1 frame steps**, and `phase_error`
    # subtracts the one step any join is entitled to. So omitting 29 frames -
    # a span of 30 - is the exact revolution, and omitting 29 steps is not.
    exact = v24_timeline.phase_error(replay, 3.000, round(3.000 + 30.0 / FPS, 6))
    assert abs(exact) < 0.1
    off_by_one = v24_timeline.phase_error(replay, 3.000, round(3.000 + 29.0 / FPS, 6))
    assert abs(off_by_one) == pytest.approx(per_frame, abs=0.05)


def test_the_spin_cut_is_phase_exact(master, replay):
    """`SPIN` extends V22.1's own omission by 28 frames, not 29.

    The shipped join is one frame long - `resume_at=4.0` is the duplicated
    boundary row the renderer drops - so the extension that restores the lock is
    a frame shorter than a revolution.
    """
    shipped = v24_timeline.phase_error(replay, 2.050, 4.016667)
    assert abs(shipped) > 10.0, "the shipped join should be a frame off the lock"
    extended = v24_timeline.phase_error(
        replay, master.replay_of[SPIN.first - 1], master.replay_of[SPIN.last + 1]
    )
    assert abs(extended) < v24_timeline.PHASE_TOLERANCE_DEG
    assert SPIN.frames == 28


def test_the_drum_trim_is_falsified(master, replay):
    """Every phase-safe trim of the shuffle shot resumes a stopped rotor."""
    verdict = machine_match(
        replay,
        master.replay_of[DRUM_FALSIFIED.first - 1],
        master.replay_of[DRUM_FALSIFIED.last + 1],
    )
    assert verdict["problems"], "the drum trim should not be legal"
    assert any("rotor turns" in note for note in verdict["problems"])
    # ...because the rotor takes hold three frames after the nearest one.
    assert master.replay_of[DRUM_FALSIFIED.first - 1] < ROTOR_START
    assert master.frame_at(ROTOR_START) == DRUM_FALSIFIED.first + 2


def test_the_still_cuts_move_nothing(master, replay):
    """`STOPPED` and `ANTICIPATION` sit where the machine is frozen."""
    for cut in (STOPPED, ANTICIPATION):
        near = machine_state(replay, master.replay_of[cut.first - 1])
        far = machine_state(replay, master.replay_of[cut.last + 1])
        assert near["rotor_rate"] < 0.05 and far["rotor_rate"] < 0.05
        assert near["rotor_height"] == pytest.approx(far["rotor_height"], abs=1e-3)
        assert near["panel_height"] == pytest.approx(far["panel_height"], abs=1e-3)


# --- every candidate --------------------------------------------------------


def test_candidates_have_no_problems(reports):
    for key, row in reports.items():
        assert row["problems"] == [], f"{key}: {row['problems']}"


def test_runtime_bounds(reports):
    low, high = RUNTIME_BOUNDS
    for key, row in reports.items():
        assert low <= row["runtime"] <= high, f"{key} runs {row['runtime']:.3f} s"
        # ...and none of them is 20.000 exactly, which the brief asks for.
        assert abs(row["runtime"] - 20.0) > 1e-6


def test_no_course_preview(reports):
    for key, row in reports.items():
        assert row["clock"].prefix == 0.0
        # The whole film is the hold plus kept master frames and nothing else.
        assert row["frames"] == row["clock"].hold_frames + row["master_frames"]


def test_frames_run_forwards_once_each(master, plans):
    for key, plan in plans.items():
        kept = kept_frames(master, plan)
        assert kept[0] == 0, f"{key} drops the frame the hold clones"
        assert len(set(kept)) == len(kept), f"{key} keeps a frame twice"
        assert kept == sorted(kept), f"{key} runs frames backwards"


def test_replay_is_monotonic(master, plans):
    """Every kept frame shows a later replay instant than the one before it."""
    for key, plan in plans.items():
        kept = kept_frames(master, plan)
        for before, after in zip(kept, kept[1:]):
            assert master.replay_of[after] > master.replay_of[before], (
                f"{key}: master {before} -> {after} does not step forwards"
            )


def test_the_clock_is_slope_one_everywhere(reports):
    """The defect `build` exists to avoid, asserted on the real candidates."""
    for key, row in reports.items():
        for out_from, out_to, replay_from, replay_to in row["clock"].segments:
            assert (replay_to - replay_from) == pytest.approx(
                out_to - out_from, abs=1e-6
            ), f"{key}: a segment carries more replay than output"


def test_every_frame_shows_what_the_clock_says(master, plans, reports):
    """The clock and the frame list agree, frame by frame, for every candidate."""
    for key, plan in plans.items():
        clock = reports[key]["clock"]
        for position, frame in enumerate(kept_frames(master, plan)):
            # Measured from `origin`, because everything before it is the hold.
            assert clock.replay_at(clock.origin + position / FPS) == pytest.approx(
                master.replay_of[frame], abs=1e-6
            ), f"{key}: output frame {position} is not master frame {frame}"


def test_keep_ranges_are_exactly_the_kept_frames(master, plans, reports):
    for key, plan in plans.items():
        spread = [
            frame
            for first, last in reports[key]["keep"]
            for frame in range(first, last + 1)
        ]
        assert spread == kept_frames(master, plan)
        assert runs(master, plan) == reports[key]["keep"]


def test_omission_boundaries_are_exact(master, plans):
    """Each cut drops the frames it names and neither neighbour."""
    for key, plan in plans.items():
        kept = set(kept_frames(master, plan))
        for cut in plan.cuts:
            assert cut.first - 1 in kept, f"{key}: {cut.first - 1} should survive"
            assert cut.last + 1 in kept, f"{key}: {cut.last + 1} should survive"
            for frame in range(cut.first, cut.last + 1):
                assert frame not in kept, f"{key}: master {frame} should be gone"


def test_omissions_are_reported_whole(master, plans):
    """The reported intervals add up to the frames the plan drops, plus the tail."""
    for key, plan in plans.items():
        rows = omissions(master, plan)
        cut_frames = sum(row["frames"] for row in rows if row["kind"] == "cut")
        assert cut_frames == plan.dropped
        tails = [row for row in rows if row["kind"] == "tail"]
        assert len(tails) == 1
        assert tails[0]["frames"] == master.frames - 1 - plan.tail
        # ...and the master's own never-rendered gap is one of them, in every
        # candidate, whether or not the candidate touched the start.
        assert any(
            row["replay_from"] <= 2.050 + 1e-9 <= row["replay_to"] for row in rows
        )


# --- the events the brief says to keep --------------------------------------


def test_the_keep_list_is_on_screen(reports):
    wanted = {
        "the gates": GATES,
        "the shuffle": 1.800,
        "the wind-down": 4.616667,
        "the trapdoor": RELEASE,
        "the obstacle approach": 10.500,
        "the obstacle payoff": 11.400,
        "the escape": 14.995833,
        "the fork": 16.300,
        "the branches": 17.850,
        "the merge": 18.416667,
        "the winner": WINNER_AT,
    }
    for key, row in reports.items():
        for label, when in wanted.items():
            assert row["clock"].at(when) is not None, f"{key} cuts {label}"


def test_obstacle_payoff_is_whole(reports):
    """The 39 contacts at 11.400-12.650 are on screen end to end."""
    for key, row in reports.items():
        clock = row["clock"]
        for when in (11.400, 11.700, 12.000, 12.300, 12.650):
            assert clock.at(when) is not None, f"{key} cuts replay {when}"


def test_fork_is_whole(reports):
    """All eight route decisions, 16.300 to 19.350."""
    for key, row in reports.items():
        for when in (16.300, 16.766667, 17.250, 17.850, 18.583333, 18.700,
                     19.000, 19.350):
            assert row["clock"].at(when) is not None, f"{key} cuts the route at {when}"


def test_finish_order_and_winner_are_unchanged(replay, reports):
    for key, row in reports.items():
        order = [one["marble"] for one in row["crossings"]]
        assert order == FINISH_ORDER, f"{key}: {order}"
        shown = [one for one in row["crossings"] if one["output"] is not None]
        assert shown[0]["marble"] == WINNER
        assert shown[0]["order"] == 1
        assert shown[0]["replay"] == pytest.approx(WINNER_AT)
        # ...and every crossing the film shows is an unbroken run from the first.
        assert [one["order"] for one in shown] == list(range(1, len(shown) + 1))
        assert len(shown) >= 3, f"{key} shows only {len(shown)} crossings"


def test_the_winner_has_room_after_it(reports):
    """The film does not stop on the crossing frame."""
    for key, row in reports.items():
        assert row["post_winner"] > 1.5, f"{key} ends {row['post_winner']:.3f} s after"


def test_no_segment_loses_all_three_phases(reports):
    """Approach, interaction and exit: a viewer needs the whole of each."""
    for key, row in reports.items():
        for seg in row["segments"]:
            assert seg["whole"], f"{key}: the {seg['name']} is not whole"
            assert seg["run_up"] > 0.0
            assert seg["pay_off"] > 0.0


def test_no_join_lands_on_a_payoff(master, replay, plans):
    """0.25 s of clearance in front of the release, the payoff and the escape."""
    for key, plan in plans.items():
        for join in joins(master, replay, plan):
            for when in (RELEASE, 11.400, 14.995833):
                assert not (0.0 <= when - join.replay[1] < 0.25), (
                    f"{key}: a join resumes {when - join.replay[1]:.3f} s "
                    f"before replay {when}"
                )


# --- what the joins cost ----------------------------------------------------


def test_joins_do_not_teleport_the_field(master, replay, plans):
    """Every join is inside the bar, and the bar is the shipped film's own join."""
    for key, plan in plans.items():
        for join in joins(master, replay, plan):
            if join.lens_cut:
                # A cut the film already makes: measured against itself.
                assert join.widths_mean <= join.baseline_widths + MARBLE_WIDTH_BAR
            else:
                assert join.widths_mean <= MARBLE_WIDTH_BAR, (
                    f"{key}: the join at output {join.output:.3f} moves the "
                    f"field {join.widths_mean:.2f} marble widths"
                )


def test_no_join_crosses_a_machine_transition(master, replay, plans):
    for key, plan in plans.items():
        for join in joins(master, replay, plan):
            assert join.machine["problems"] == (), f"{key}: {join.machine['problems']}"


def test_the_shipped_join_is_the_bar(master, replay):
    """V22.1's own start omission, measured in the units the candidates use."""
    plan = Plan(key="v221", title="v221", hold_frames=42, cuts=(),
                tail=master.frames - 1, note="")
    control = joins(master, replay, plan)
    assert len(control) == 1, "the master's own b116 gap is the only join in it"
    assert control[0].before_frame == 111 and control[0].after_frame == 112
    assert control[0].widths_mean == pytest.approx(0.47, abs=0.05)
    assert control[0].widths_mean < MARBLE_WIDTH_BAR


# --- the rejected exhibit ---------------------------------------------------


def test_the_rejected_candidate_reaches_the_brief_and_fails_the_bar(master, replay):
    """D is the brief's start target, and the reason it is not on offer."""
    plan = rejected(master)["d_rejected"]
    row = report(master, replay, plan)
    # It really does reach the band the brief asks for...
    assert 2.7 <= row["start"]["to_downhill"] <= 3.0
    # ...and it really is the V22 defect: the marbles barely move and the
    # machine changes state in a single frame.
    big = next(one for one in row["joins"] if one.omitted_frames > 100)
    assert big.widths_mean < 1.0
    assert any("rotor turns" in note for note in big.machine["problems"])
    assert any("blades stand" in note for note in big.machine["problems"])
    assert row["problems"], "D should not pass check()"


# --- coverage ---------------------------------------------------------------


def test_coverage_adds_up(master, replay, plans, reports):
    for key, plan in plans.items():
        stats = coverage(master, plan, replay)
        assert stats["shown"] == pytest.approx(
            len(kept_frames(master, plan)) / FPS, abs=1e-9
        )
        assert 0.75 < stats["coverage"] < 0.95
        assert stats["replay_from"] == pytest.approx(0.200)


def test_the_candidates_are_ordered_by_start_length(reports):
    """A, B, C are a dial and not three unrelated films."""
    order = [reports[key]["start"]["to_downhill"] for key in ("a", "b", "c")]
    assert order == sorted(order)
    assert order[2] - order[0] > 0.4, "the three starts should be distinguishable"

"""Phase 4: the pacing gate, and an ending that cannot rewrite its own run.

Phase 3's tests asked whether the renderer could change the simulation. Phase 4
adds two things that could, and these tests are the answer to each.

**The pacing gate** is a production rule, so it is tested the way a rule is: it
is deterministic, every threshold has a run on each side of it, and the two
instrument bugs found while building it stay fixed. One of those - a near-miss
chance of **-0.94** for a single dark tile, because the band's width was
measured after its start had already been wrapped around the perimeter - would
have made every gate decision wrong in a direction nobody would have
questioned, since the excess it feeds only ever appears as a small number.

**The ending** is the first thing in Category 3 that deliberately changes the
rules, and the whole defence of it is that the change is explicit, is after the
objective, and is not a second physics. So:

* the escape flight is `run.flights[-1]`, compared **bit for bit** rather than
  approximately, because "very close to the canonical continuation" is exactly
  what a second simulation looks like;
* the timeline's first segment is the identity map, so attaching a completion
  block cannot move one frame of the run that earned it;
* the states appear once each, in order, and the ball is never released before
  the gate has finished opening;
* a run that never completed cannot produce an ending at all.

Nothing here launches Godot. The GDScript is read as text and checked against
the Python it mirrors and against the two bugs that cost the most time in this
phase: a stills task that indexed the ending in simulation time, and a shock
ring animated by scaling a mesh - which scales its rim as well, and turned a
0.42 wu line into a 5.5 wu band wider than the frame.
"""

from __future__ import annotations

import dataclasses
import json
import math
import os
import re

import pytest

from satisfying import tile_completion, tile_pacing, tile_playback
from satisfying.tile_arena import polygon_arena
from satisfying.tile_escape import simulate
from satisfying.tile_evaluator import evaluate
from satisfying.tile_sweep import PHASE2_ARENA, PHASE2_CONFIG

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENE_GD = os.path.join(REPO, "godot", "scripts", "tile_escape_scene.gd")
RENDER_GD = os.path.join(REPO, "godot", "scripts", "tile_escape_render.gd")

PHASE4_CONFIG = dataclasses.replace(PHASE2_CONFIG, speed=85.0)

# The three seeds Phase 4 rendered, and what each one is for. Named constants
# rather than a re-sweep: selecting them cost a 50,000-seed pass and these
# tests need the runs, not the search.
CONTROL_SEED = 3530        # 1.70 s worst mid-run gap; the Phase 3 cast's centre
MID_GAP_SEED = 6132        # 3.21 s at 29 of 51
LONG_GAP_SEED = 20814      # 3.71 s at 34 of 51
TENSION_SEED = 38864       # 6.31 s and 6.20 s at the very end
APPROACH_SEED = 7541       # 4.13 s at 48 of 51; the approach ceiling
BODY_BRACKET_SEED = 10557  # 5.15 s at 42 of 51; the body ceiling


@pytest.fixture(scope="module")
def control():
    return simulate(CONTROL_SEED, PHASE4_CONFIG, PHASE2_ARENA)


@pytest.fixture(scope="module")
def long_gap():
    return simulate(LONG_GAP_SEED, PHASE4_CONFIG, PHASE2_ARENA)


@pytest.fixture(scope="module")
def scene_source() -> str:
    with open(SCENE_GD, "r", encoding="utf-8") as handle:
        return handle.read()


@pytest.fixture(scope="module")
def render_source() -> str:
    with open(RENDER_GD, "r", encoding="utf-8") as handle:
        return handle.read()


def gd_code(source: str) -> str:
    """GDScript with its comments removed.

    Same helper as Phase 3's suite and for the same reason, sharpened by Phase
    4: this file's header now *names* `RigidBody` in prose while explaining why
    there is none, so a scan of the raw text fails on the comment explaining
    the absence of the thing it is looking for.
    """
    stripped: list[str] = []
    for line in source.splitlines():
        quote = ""
        cut = len(line)
        for index, character in enumerate(line):
            if quote:
                if character == quote:
                    quote = ""
            elif character in "\"'":
                quote = character
            elif character == "#":
                cut = index
                break
        stripped.append(line[:cut])
    return "\n".join(stripped)


@pytest.fixture(scope="module")
def scene_code(scene_source) -> str:
    return gd_code(scene_source)


def gd_constant(source: str, name: str) -> float:
    match = re.search(rf"^const {name} :?= ([0-9.]+)$", source, re.MULTILINE)
    assert match is not None, f"{name} is not a constant in the GDScript"
    return float(match.group(1))


# --------------------------------------------------------------------------
# The gap instrument
# --------------------------------------------------------------------------


def test_every_gap_covers_the_whole_run_with_no_overlap(control):
    """The windows partition [0, end]. A gap the instrument never looked at is
    a stall nothing can reject."""
    windows = tile_pacing.gap_windows(control, PHASE2_ARENA)
    assert windows[0].start_seconds == 0.0
    assert windows[-1].end_seconds == pytest.approx(control.end_time)
    for earlier, later in zip(windows, windows[1:]):
        assert earlier.end_seconds == later.start_seconds


def test_a_gap_contains_only_duplicate_contacts(control):
    """By construction: a contact on a dark tile ends the gap it is in.

    Worth pinning because it is the reason a gap's contact count is exactly the
    number of events that produced no progress, which is what the gate reads.
    """
    activation_times = {hit.time for hit in control.collisions if hit.is_new}
    for window in tile_pacing.gap_windows(control, PHASE2_ARENA):
        inside = [
            hit for hit in control.collisions
            if window.start_seconds < hit.time < window.end_seconds
        ]
        assert all(not hit.is_new for hit in inside)
        assert len(inside) == window.collisions
        assert window.end_seconds in activation_times or window.end_seconds == pytest.approx(
            control.end_time
        )


def test_the_number_of_windows_is_one_per_activation(control):
    windows = tile_pacing.gap_windows(control, PHASE2_ARENA)
    # One gap before each activation. A run that stops on completion has no
    # tail after the last one, so there is no extra window.
    assert len(windows) == control.total_tiles


def test_near_miss_chance_is_a_probability_for_every_dark_set():
    """The regression for the wrap bug.

    The band around tile 0 starts at a negative perimeter coordinate. The first
    implementation reduced that start modulo the perimeter and *then* took the
    width as `hi - lo`, which measured the band against the wrapped origin: one
    dark tile came out at -0.94 and fifteen at -1.58. A chance outside [0, 1]
    is not a near miss with a bad threshold, it is an instrument reading a
    negative probability, and the excess it feeds is a small number nobody
    would have questioned.
    """
    width = 2.0 * tile_pacing.BALL_DRAW_SCALE * PHASE4_CONFIG.ball_radius
    for dark in (
        [0],
        [0, 1],
        [50],
        [0, 50],
        [5, 20, 40],
        list(range(15)),
        list(range(0, 51, 3)),
        list(range(51)),
        [],
    ):
        chance = tile_pacing.near_miss_chance(PHASE2_ARENA, dark, width)
        assert 0.0 <= chance <= 1.0, (dark, chance)


def test_one_dark_tile_puts_six_percent_of_the_wall_in_the_near_band():
    """Computed by hand: (tile_length + 2 * ball_width) / perimeter.

    The number that makes a near-miss count readable. With one tile left a
    near miss is a one-in-sixteen event per contact, so a final hunt of
    eighteen contacts expects about one - which is why "at least three near
    misses" is not a condition the physics can satisfy on demand.
    """
    width = 2.0 * tile_pacing.BALL_DRAW_SCALE * PHASE4_CONFIG.ball_radius
    perimeter = PHASE2_ARENA.total_tiles * PHASE2_ARENA.tile_length
    expected = (PHASE2_ARENA.tile_length + 2.0 * width) / perimeter
    assert tile_pacing.near_miss_chance(PHASE2_ARENA, [0], width) == pytest.approx(
        expected
    )


def test_the_chance_accounts_for_dark_tiles_sitting_next_to_each_other():
    """Fifteen adjacent dark tiles cover far less wall than fifteen spread ones.

    A count-based reading cannot see the difference; the union can, and that is
    the whole reason the chance is computed geometrically rather than as
    `count * band / perimeter`.
    """
    width = 2.0 * tile_pacing.BALL_DRAW_SCALE * PHASE4_CONFIG.ball_radius
    clustered = tile_pacing.near_miss_chance(PHASE2_ARENA, list(range(15)), width)
    spread = tile_pacing.near_miss_chance(PHASE2_ARENA, list(range(0, 45, 3)), width)
    assert clustered < spread


def test_area_coverage_is_a_fraction_and_rises_with_the_path(control):
    windows = sorted(
        tile_pacing.gap_windows(control, PHASE2_ARENA), key=lambda w: w.seconds
    )
    for window in windows:
        assert 0.0 <= window.area_coverage <= 1.0
    longest = windows[-1]
    shortest = windows[0]
    assert longest.area_coverage >= shortest.area_coverage


def test_the_gap_instrument_is_deterministic(long_gap):
    """Twice over the same run, field for field. The gate is a production
    decision and a production decision that could differ between two runs of
    the same code is not a rule."""
    first = tile_pacing.gap_windows(long_gap, PHASE2_ARENA)
    second = tile_pacing.gap_windows(long_gap, PHASE2_ARENA)
    assert [w.as_dict() for w in first] == [w.as_dict() for w in second]


def test_the_gap_instrument_reads_the_same_run_twice_the_same_way():
    a = simulate(LONG_GAP_SEED, PHASE4_CONFIG, PHASE2_ARENA)
    b = simulate(LONG_GAP_SEED, PHASE4_CONFIG, PHASE2_ARENA)
    assert (
        [w.as_dict() for w in tile_pacing.gap_windows(a, PHASE2_ARENA)]
        == [w.as_dict() for w in tile_pacing.gap_windows(b, PHASE2_ARENA)]
    )


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------


def test_the_gate_is_deterministic(long_gap):
    first = tile_pacing.judge(long_gap, PHASE2_ARENA)
    second = tile_pacing.judge(long_gap, PHASE2_ARENA)
    assert first.as_dict() == second.as_dict()


def test_a_body_gap_either_side_of_the_ceiling_decides_the_run(long_gap):
    """The acceptance boundary, on the run the ceiling was set from.

    Seed 20814's worst mid-run gap is 3.71 s. A gate whose ceiling is above
    that accepts it and one below rejects it, and the failure is named rather
    than implied.
    """
    worst = tile_pacing.worst_body_gap(
        tile_pacing.gap_windows(long_gap, PHASE2_ARENA)
    )
    assert worst is not None
    above = dataclasses.replace(
        tile_pacing.DEFAULT_GATE, max_body_gap_seconds=worst.seconds + 0.01
    )
    below = dataclasses.replace(
        tile_pacing.DEFAULT_GATE, max_body_gap_seconds=worst.seconds - 0.01
    )
    assert "no_gap_over_ceiling" not in tile_pacing.judge(
        long_gap, PHASE2_ARENA, above
    ).failures
    rejected = tile_pacing.judge(long_gap, PHASE2_ARENA, below)
    assert not rejected.accepted
    assert "no_gap_over_ceiling" in rejected.failures


def test_the_ceilings_rise_as_the_targets_run_out(control):
    """The shape of the rule, stated as an ordering rather than three numbers.

    The fewer dark tiles remain, the longer a pause is allowed to be, because
    the viewer knows what they are waiting for. Seed 3530 is the case: its
    longest gap is a 3.82 s final hunt and its worst mid-run gap is 1.70 s, and
    a gate that judged both against the mid-run ceiling would reject the Phase
    3 cast's best all-round seed for having an ending.
    """
    gate = tile_pacing.DEFAULT_GATE
    assert (
        gate.max_body_gap_seconds
        < gate.max_approach_gap_seconds
        < gate.max_final_gap_seconds
    )
    windows = tile_pacing.gap_windows(control, PHASE2_ARENA)
    hunt = tile_pacing.final_hunt_gap(windows)
    body = tile_pacing.worst_body_gap(windows)
    assert hunt is not None and body is not None
    assert hunt.seconds > body.seconds
    assert gate.ceiling(hunt) > gate.ceiling(body)
    assert hunt.seconds <= gate.max_final_gap_seconds
    assert body.seconds <= gate.max_body_gap_seconds
    assert tile_pacing.judge(control, PHASE2_ARENA, gate).accepted


def test_the_approach_band_had_no_ceiling_at_all_before_phase_four():
    """The defect the gate exists for.

    `tile_evaluator.longest_body_gap_seconds` counts only gaps that begin
    before `total - 3` lit, so a stall at 48 or 49 of 51 was invisible to the
    Phase 2 rule, and the final hunt was bounded only by `max_final_tile` at
    9.0 s. Seed 38864 passes every Phase 2 condition with 6.31 s at 49 of 51
    and 6.20 s at 50 of 51.
    """
    from satisfying.tile_evaluator import DEFAULT_RULE, verdict as phase2_verdict

    run = simulate(TENSION_SEED, PHASE4_CONFIG, PHASE2_ARENA)
    evaluation = evaluate(run)
    assert phase2_verdict(evaluation, DEFAULT_RULE).accepted
    # Phase 2's own mid-run number does not see either of them.
    assert evaluation.longest_body_gap_seconds < 2.5
    worst = max(
        tile_pacing.gap_windows(run, PHASE2_ARENA), key=lambda w: w.seconds
    )
    assert worst.kind == "approach"
    assert worst.seconds > 6.0
    assert not tile_pacing.judge(run, PHASE2_ARENA).accepted


def test_a_repetitive_gap_is_rejected_at_any_duration(long_gap):
    """The brief's "reject repetitive orbit patterns regardless of raw
    duration", stated against a gate strict enough to fire.

    At the locked configuration nothing in the population is repetitive enough
    to trip the shipped threshold - 2,244 reviewed gaps over 465 accepted seeds
    returned a longest periodic cycle of **zero, at every percentile** - so the
    condition is proved on a tightened gate rather than on a seed that does not
    exist.
    """
    strict = dataclasses.replace(tile_pacing.DEFAULT_GATE, max_repeat_ratio=0.05)
    decision = tile_pacing.judge(long_gap, PHASE2_ARENA, strict)
    assert not decision.accepted
    assert "no_repetitive_stall" in decision.failures


def test_short_gaps_are_not_examined(control):
    """A three-contact window would fail a repetition test on noise.

    The floor is what keeps the gate about stalls and not about the ordinary
    rhythm of a run whose median activation interval is under a second.
    """
    decision = tile_pacing.judge(control, PHASE2_ARENA)
    assert all(
        w.seconds >= tile_pacing.DEFAULT_GATE.review_floor_seconds
        for w in decision.reviewed
    )
    assert len(decision.reviewed) < control.total_tiles


def test_the_gate_reports_every_failure_and_not_the_first():
    """Same reason `tile_evaluator.verdict` does: a run that fails one
    condition by a tenth of a second is a different object from one that fails
    three, and a first-failure-wins check makes them look the same."""
    run = simulate(TENSION_SEED, PHASE4_CONFIG, PHASE2_ARENA)
    brutal = dataclasses.replace(
        tile_pacing.DEFAULT_GATE,
        max_body_gap_seconds=1.0,
        max_approach_gap_seconds=1.0,
        max_final_gap_seconds=1.0,
        busy_above_seconds=0.1,
        min_collisions_per_second=99.0,
        max_repeat_ratio=0.0,
    )
    decision = tile_pacing.judge(run, PHASE2_ARENA, brutal)
    assert len(decision.failures) >= 2
    assert set(decision.failures) | set(decision.passes) == {
        "no_gap_over_ceiling",
        "long_gaps_are_busy",
        "no_repetitive_stall",
    }
    # And every failing condition names the gaps that caused it.
    assert set(decision.offending) == set(decision.failures)
    assert all(labels for labels in decision.offending.values())


def test_a_failure_names_the_gap_that_caused_it():
    """A verdict an operator can act on without re-reading the run."""
    run = simulate(TENSION_SEED, PHASE4_CONFIG, PHASE2_ARENA)
    decision = tile_pacing.judge(run, PHASE2_ARENA)
    labels = decision.offending["no_gap_over_ceiling"]
    assert any("approach 6.31s at 49/51" in label for label in labels), labels
    assert any("final_hunt 6.20s at 50/51" in label for label in labels), labels


def test_an_accepted_run_names_no_offending_gap():
    run = simulate(CONTROL_SEED, PHASE4_CONFIG, PHASE2_ARENA)
    decision = tile_pacing.judge(run, PHASE2_ARENA)
    assert decision.accepted
    assert decision.offending == {}


def test_the_shipped_gate_accepts_the_three_rendered_pacing_seeds():
    """The gate is derived from the clips, so the clips have to pass it.

    This is the test that would fail if a later change to a threshold quietly
    invalidated the evidence it was set from.
    """
    for seed in (CONTROL_SEED, MID_GAP_SEED, LONG_GAP_SEED, APPROACH_SEED):
        run = simulate(seed, PHASE4_CONFIG, PHASE2_ARENA)
        decision = tile_pacing.judge(run, PHASE2_ARENA)
        assert decision.accepted, (seed, decision.failures)


def test_the_shipped_gate_rejects_the_five_second_mid_run_gap():
    """Seed 10557's 5.15 s at 42 of 51 is the render that fixed the body
    ceiling: nine scattered targets, the highest contact rate of anything
    rendered at 7.4/s, and still eleven frames of a motionless "42 / 51"."""
    run = simulate(BODY_BRACKET_SEED, PHASE4_CONFIG, PHASE2_ARENA)
    decision = tile_pacing.judge(run, PHASE2_ARENA)
    assert not decision.accepted
    assert "no_gap_over_ceiling" in decision.failures


def test_the_shipped_gate_rejects_the_run_whose_ending_is_a_wait():
    """Seed 38864 holds 6.31 s at 49 of 51 and 6.20 s at 50 of 51.

    Phase 3 kept it as the tension candidate on the strength of its final-tile
    clock. The gate is where "tense" and "long" are separated, and the 6.31 s
    is not even the ending - it begins with two tiles left.
    """
    run = simulate(TENSION_SEED, PHASE4_CONFIG, PHASE2_ARENA)
    decision = tile_pacing.judge(run, PHASE2_ARENA)
    assert not decision.accepted
    assert "no_gap_over_ceiling" in decision.failures


# --------------------------------------------------------------------------
# The ending: the escape is the canonical continuation
# --------------------------------------------------------------------------


def test_the_escape_flight_is_the_runs_own_last_flight_bit_for_bit(control):
    """The single assertion the honesty of the ending rests on.

    Equality, not `approx`. A recomputed continuation would agree to twelve
    places and still be a second simulation of a chaotic billiard, which is the
    thing this architecture exists to make impossible.
    """
    block = tile_completion.completion_block(control, PHASE2_ARENA)
    last = control.flights[-1]
    assert block["escape"]["t"] == last.t_start
    assert block["escape"]["p"] == [last.position[0], last.position[1]]
    assert block["escape"]["v"] == [last.velocity[0], last.velocity[1]]


def test_the_gate_is_the_wall_the_ball_was_already_going_to_reach(control):
    """Re-derived here with the arena's own half-plane test rather than with
    the module's quadratic, so the two cannot agree by sharing a mistake."""
    route = tile_completion.escape_route(control, PHASE2_ARENA)
    px, py = route.start_position
    vx, vy = route.start_velocity
    limit = PHASE2_ARENA.apothem - control.config.ball_radius

    # At the crossing instant the ball is on the gate side's wall line and
    # strictly inside every other one.
    for side in range(PHASE2_ARENA.sides):
        nx, ny = PHASE2_ARENA.side_outward_normals[side]
        at_crossing = (
            (px + vx * route.reach_seconds) * nx
            + (py + vy * route.reach_seconds) * ny
        )
        if side == route.gate_side:
            assert at_crossing == pytest.approx(limit, abs=1.0e-9)
        else:
            assert at_crossing <= limit + 1.0e-9


def test_the_gate_side_is_never_the_side_the_last_tile_is_on(control):
    """Not a coincidence and not a rule imposed on the geometry.

    After a reflection the ball's velocity has an inward component on the wall
    it just left, so with no further bounce it can never return to that wall.
    The ending therefore always opens somewhere other than where it finished,
    which is what gives the confirmation wave somewhere to travel to.
    """
    route = tile_completion.escape_route(control, PHASE2_ARENA)
    final = [hit for hit in control.collisions if hit.is_new][-1]
    assert route.gate_side != final.side


def test_the_gate_spans_the_sides_it_says_it_does(control):
    for neighbours in (0, 1, 2):
        timing = dataclasses.replace(
            tile_completion.DEFAULT_TIMING, gate_neighbour_sides=neighbours
        )
        route = tile_completion.escape_route(control, PHASE2_ARENA, timing)
        assert len(route.gate_side_list) == 2 * neighbours + 1
        assert route.gate_side in route.gate_side_list
        assert len(route.gate_tiles) == len(route.gate_side_list) * (
            PHASE2_ARENA.tiles_per_side
        )


def test_the_escape_crossing_lands_inside_the_opening(control):
    """The ball goes out through the hole, not past the end of it."""
    route = tile_completion.escape_route(control, PHASE2_ARENA)
    tile = PHASE2_ARENA.tile_for_contact(route.gate_side, route.crossing)
    assert tile.index in route.gate_tiles


def test_the_ball_leaves_the_frame_and_the_exit_is_after_the_crossing(control):
    route = tile_completion.escape_route(control, PHASE2_ARENA)
    assert route.exit_seconds > route.reach_seconds
    x, y = route.exit_position
    assert (
        abs(x) >= route.frame_half_width_wu
        or abs(y) >= route.frame_half_height_wu
    )


def test_a_run_that_never_completed_has_no_ending():
    """`unlock cannot happen before 51/51`, at the only place it could.

    The arena is unreachable rather than merely hard - a two-tile-per-side
    arena with a short duration - so the run stops incomplete and the ending
    refuses to build at all. There is no code path that produces a gate for a
    run with a dark tile in it.
    """
    short = dataclasses.replace(PHASE4_CONFIG, duration=3.0)
    run = simulate(7, short, PHASE2_ARENA)
    assert not run.completed
    with pytest.raises(tile_completion.CompletionError):
        tile_completion.escape_route(run, PHASE2_ARENA)
    with pytest.raises(tile_completion.CompletionError):
        tile_completion.completion_block(run, PHASE2_ARENA)


def test_the_ending_refuses_a_run_that_did_not_stop_on_completion():
    """If the solver kept going past the fifty-first tile, `flights[-1]` is no
    longer the state at completion and the escape would start from the wrong
    place. That is a fault, not a case to handle quietly."""
    keep_going = dataclasses.replace(PHASE4_CONFIG, stop_on_complete=False)
    run = simulate(CONTROL_SEED, keep_going, PHASE2_ARENA)
    assert run.completed
    assert run.flights[-1].t_start > run.completion_time
    with pytest.raises(tile_completion.CompletionError):
        tile_completion.escape_route(run, PHASE2_ARENA)


def test_completion_fires_exactly_once_and_on_the_fifty_first_tile(control):
    """One completion instant, one final tile, one `final_hit` segment."""
    activations = [hit for hit in control.collisions if hit.is_new]
    assert len(activations) == control.total_tiles
    assert activations[-1].activated_after == control.total_tiles
    assert sum(
        1 for hit in control.collisions
        if hit.is_new and hit.activated_after == control.total_tiles
    ) == 1

    block = tile_completion.completion_block(control, PHASE2_ARENA)
    assert block["final_seconds"] == control.completion_time
    assert block["final_tile"] == activations[-1].tile_index
    states = [segment["state"] for segment in block["timeline"]]
    assert states.count("final_hit") == 1


# --------------------------------------------------------------------------
# The timeline
# --------------------------------------------------------------------------


def test_the_states_appear_once_each_in_order(control):
    block = tile_completion.completion_block(control, PHASE2_ARENA)
    states = [segment["state"] for segment in block["timeline"]]
    assert tuple(states) == tile_completion.STATE_SEQUENCE


def test_the_timeline_is_contiguous_and_monotonic(control):
    segments = tile_completion.timeline(
        tile_completion.escape_route(control, PHASE2_ARENA)
    )
    for earlier, later in zip(segments, segments[1:]):
        assert earlier.render_end == pytest.approx(later.render_start)
        assert earlier.render_end > earlier.render_start
    for segment in segments:
        assert segment.sim_rate >= 0.0
    # Simulation time never goes backwards, which is what makes "the first
    # render instant showing this simulation time" well defined.
    times = [
        tile_completion.sim_time_at(segments, t)
        for t in [i * 0.01 for i in range(int(segments[-1].render_end * 100))]
    ]
    assert all(b >= a - 1.0e-9 for a, b in zip(times, times[1:]))


def test_the_locked_segment_is_the_identity_map(control):
    """The ending cannot move one frame of the run that earned it.

    Sampled at every hundredth of a second up to the completion, and at every
    activation instant exactly.
    """
    segments = tile_completion.timeline(
        tile_completion.escape_route(control, PHASE2_ARENA)
    )
    completion = control.completion_time
    probes = [i * 0.01 for i in range(int(completion * 100))]
    probes += [hit.time for hit in control.collisions if hit.is_new]
    for t in probes:
        if t > completion:
            continue
        assert tile_completion.sim_time_at(segments, t) == pytest.approx(t, abs=1e-12)
        assert tile_completion.state_at(segments, t) == "locked"


def test_the_ball_is_never_released_before_the_gate_has_opened():
    """Beat 4 cannot precede beat 3. Checked on every shipped preset and
    refused at construction for anything that violates it."""
    for name, timing in tile_completion.TIMINGS.items():
        assert timing.release_at_seconds >= (
            timing.gate_open_by_seconds - timing.ORDER_EPSILON
        ), name
    with pytest.raises(tile_completion.CompletionError):
        tile_completion.ClimaxTiming(
            name="broken", gate_open_at_seconds=0.6, gate_open_seconds=0.4,
            release_at_seconds=0.7,
        )


def test_a_timing_cannot_open_the_gate_during_the_hit_stop():
    with pytest.raises(tile_completion.CompletionError):
        tile_completion.ClimaxTiming(
            name="broken", impact_hold_seconds=0.5, gate_open_at_seconds=0.2,
            release_at_seconds=1.0,
        )


@pytest.mark.parametrize("rate", [0.0, -0.1, 1.5])
def test_an_escape_rate_outside_zero_to_one_is_refused(rate):
    with pytest.raises(tile_completion.CompletionError):
        tile_completion.ClimaxTiming(name="broken", escape_rate=rate)


def test_the_hold_segments_do_not_advance_simulation_time(control):
    segments = tile_completion.timeline(
        tile_completion.escape_route(control, PHASE2_ARENA)
    )
    for segment in segments:
        if segment.state in ("final_hit", "confirming", "unlocking", "settled"):
            assert segment.sim_rate == 0.0
            assert segment.sim_at(segment.render_end) == segment.sim_start


def test_the_escape_segment_plays_the_canonical_flight_slowly(control):
    """Slow motion over a trajectory the physics produced, never a new one."""
    timing = tile_completion.DEFAULT_TIMING
    route = tile_completion.escape_route(control, PHASE2_ARENA, timing)
    segments = tile_completion.timeline(route, timing)
    escaping = [s for s in segments if s.state == "escaping"][0]
    assert escaping.sim_rate == timing.escape_rate
    assert escaping.sim_start == control.completion_time
    covered = (escaping.render_end - escaping.render_start) * escaping.sim_rate
    assert covered == pytest.approx(route.exit_seconds)


@pytest.mark.parametrize("name", sorted(tile_completion.TIMINGS))
def test_every_timing_preset_produces_an_ending_inside_the_brief(name, control):
    """The brief asks for roughly 1.0-2.5 s from the final activation to the
    end of the video. `stretched` is deliberately at the top of that band and
    `compact` at the bottom; neither may fall outside it."""
    timing = tile_completion.TIMINGS[name]
    block = tile_completion.completion_block(control, PHASE2_ARENA, timing)
    assert 0.9 <= block["climax_seconds"] <= 2.6, (name, block["climax_seconds"])


def test_the_timing_presets_order_as_their_names_say(control):
    lengths = {
        name: tile_completion.completion_block(
            control, PHASE2_ARENA, tile_completion.TIMINGS[name]
        )["climax_seconds"]
        for name in ("compact", "standard", "stretched")
    }
    assert lengths["compact"] < lengths["standard"] < lengths["stretched"]


# --------------------------------------------------------------------------
# The document
# --------------------------------------------------------------------------


def test_attaching_an_ending_changes_nothing_else_in_the_document(control):
    """Field by field, which is stronger than comparing the digest: a digest
    covers the collisions and this covers the flights, the arena and the
    activation times as well."""
    plain = tile_playback.playback_document(control)
    withending = tile_completion.attach_completion(plain, control, PHASE2_ARENA)
    assert set(withending) - set(plain) == {"completion"}
    for key in plain:
        assert withending[key] == plain[key], key


def test_attaching_an_ending_does_not_mutate_the_document_it_was_given(control):
    plain = tile_playback.playback_document(control)
    before = json.dumps(plain, sort_keys=True)
    tile_completion.attach_completion(plain, control, PHASE2_ARENA)
    assert json.dumps(plain, sort_keys=True) == before


def test_a_document_with_an_ending_still_verifies_against_a_fresh_run(control):
    """The Phase 3 guarantee, unchanged by Phase 4."""
    document = tile_completion.attach_completion(
        tile_playback.playback_document(control), control, PHASE2_ARENA
    )
    report = tile_playback.verify_document(document)
    assert report["digest_matches"]
    assert report["activation_order_matches"]
    assert report["activation_times_match_exactly"]
    assert report["completion_matches"]
    assert report["collision_count_matches"]


def test_a_document_with_an_ending_round_trips_through_json(control, tmp_path):
    document = tile_completion.attach_completion(
        tile_playback.playback_document(control), control, PHASE2_ARENA
    )
    path = tmp_path / "seed.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    reloaded = json.loads(path.read_text(encoding="utf-8"))
    assert reloaded == document
    assert reloaded["completion"]["escape"] == document["completion"]["escape"]


def test_an_ending_refuses_a_document_for_another_seed(control):
    other = simulate(LONG_GAP_SEED, PHASE4_CONFIG, PHASE2_ARENA)
    with pytest.raises(tile_completion.CompletionError):
        tile_completion.attach_completion(
            tile_playback.playback_document(other), control, PHASE2_ARENA
        )


def test_the_ripple_starts_at_the_final_tile_and_reaches_the_far_side(control):
    final = [hit for hit in control.collisions if hit.is_new][-1].tile_index
    phases = tile_completion.ripple_phases(PHASE2_ARENA, final)
    assert len(phases) == PHASE2_ARENA.total_tiles
    assert phases[final] == 0.0
    assert max(phases) == pytest.approx(1.0, abs=0.05)
    # Symmetric: the wave leaves in both directions at the same speed.
    total = PHASE2_ARENA.total_tiles
    for step in range(1, total // 2):
        assert phases[(final + step) % total] == pytest.approx(
            phases[(final - step) % total]
        )


def test_the_ending_is_deterministic(control):
    first = tile_completion.completion_block(control, PHASE2_ARENA)
    second = tile_completion.completion_block(control, PHASE2_ARENA)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_playback_stays_deterministic_across_the_whole_phase_four_pipeline():
    """Simulate, evaluate, judge, and attach an ending - twice, and compare
    everything. The brief asks for this and it is cheap; what it is really
    guarding is a future cache or a dictionary iteration order sneaking into
    one of the four."""
    def build(seed: int):
        run = simulate(seed, PHASE4_CONFIG, PHASE2_ARENA)
        document = tile_completion.attach_completion(
            tile_playback.playback_document(run), run, PHASE2_ARENA
        )
        return (
            json.dumps(document, sort_keys=True),
            json.dumps(evaluate(run).as_dict(), sort_keys=True),
            json.dumps(tile_pacing.judge(run, PHASE2_ARENA).as_dict(), sort_keys=True),
        )

    for seed in (CONTROL_SEED, LONG_GAP_SEED):
        assert build(seed) == build(seed)


def test_an_arena_of_another_size_still_produces_a_coherent_ending():
    """Nothing in the ending is hard-coded to seventeen sides or fifty-one
    tiles. Worth one test, because `ripple_phases` and the gate span are the
    two places a 51 could have been written down."""
    arena = polygon_arena(sides=11, tiles_per_side=2, circumradius=7.0)
    config = dataclasses.replace(PHASE4_CONFIG, duration=400.0)
    run = simulate(4, config, arena)
    if not run.completed:
        pytest.skip("seed 4 does not complete in this arena")
    block = tile_completion.completion_block(run, arena)
    assert len(block["ripple_phase"]) == arena.total_tiles
    assert len(block["route"]["gate_tiles"]) == 3 * arena.tiles_per_side


# --------------------------------------------------------------------------
# The GDScript
# --------------------------------------------------------------------------


def test_the_scene_and_python_agree_on_the_frame_the_escape_is_measured_against(
    scene_source,
):
    """`tile_completion` decides when the ball has left the frame, and the
    scene decides where the frame is. A drift between the two would make the
    ending end before or after the ball was actually gone."""
    assert gd_constant(scene_source, "ARENA_WIDTH_FRACTION") == pytest.approx(
        tile_completion.ARENA_WIDTH_FRACTION
    )


def test_the_scene_reads_the_completion_format_it_was_written_in(scene_source):
    assert tile_completion.COMPLETION_FORMAT == 1
    assert 'int(block.get("format", -1)) != 1' in scene_source


def test_the_scene_computes_no_part_of_the_ending_itself(scene_source):
    """Everything the ending needs is read from the document.

    The gate side in particular: a renderer that searched the geometry for a
    dramatic wall would be choosing where the ball goes, which is the exact
    difference between this ending and hidden trajectory assistance.
    """
    body = scene_source.split("func _read_completion", 1)[1]
    body = body.split("\nfunc ", 1)[0]
    for source in ("gate_tiles", "escape", "ripple_phase", "timeline", "timing"):
        assert f'"{source}"' in body or f'["{source}"]' in body, source


def test_the_climax_stills_task_indexes_the_ending_in_render_time(render_source):
    """The regression for the bug that produced the first six climax stills.

    `--climax-stills` set only `_climax_stills`, `_set_clock` tested only
    `_climax`, and the six stills were therefore handed to `set_time` as
    *simulation* instants. Four of them fell past the run's end, the ball
    evaluated its escape flight against a render clock and left the frame, and
    the confirmation still showed an arena whose gate was already open.
    """
    assert '_climax = str(options.get("climax", "")) == "1" or _climax_stills' in (
        render_source
    )
    setter = render_source.split("func _set_clock", 1)[1].split("\nfunc ", 1)[0]
    assert "set_render_time" in setter and "set_time" in setter


def test_python_and_gdscript_name_the_same_six_climax_stills(render_source):
    """`CLIMAX_STILLS` documents what the driver asks for; the scene decides
    when each one is. A rename on one side and not the other would quietly
    produce a set of stills whose names no longer describe them."""
    from satisfying import tile_phase4_cli

    moments = render_source.split("func _climax_moments", 1)[1].split("\nfunc ", 1)[0]
    names = re.findall(r'\["([a-f]_[a-z_]+)"', moments)
    assert names == [name for name, _ in tile_phase4_cli.CLIMAX_STILLS]


def test_the_six_climax_stills_are_in_timeline_order(render_source):
    """a before the hit, b at it, then confirmation, unlock, escape, end."""
    from satisfying import tile_phase4_cli

    assert [name for name, _ in tile_phase4_cli.CLIMAX_STILLS] == [
        "a_before_final", "b_final_hit", "c_confirmation",
        "d_unlock", "e_escape", "f_end",
    ]


def test_the_shock_ring_stays_a_line_at_full_extent(scene_source):
    """A uniformly scaled ring scales its own rim.

    The first build animated a 0.42 wu rim out to radius 13, which draws a
    5.5 wu band - wider than the arena and wider than the frame - as a flat
    khaki disc over the whole picture. The product of the two constants is the
    thing that has to stay small.
    """
    width = gd_constant(scene_source, "SHOCK_RING_WIDTH")
    radius = gd_constant(scene_source, "SHOCK_RING_RADIUS")
    assert width * radius < 0.8, "the shock ring's rim is a band, not a line"
    assert radius < 2.0 * PHASE2_ARENA.circumradius


def test_the_ending_keeps_three_distinguishable_event_strengths(scene_source):
    """Duplicate, new tile, final tile - and Phase 5 mirrors the same three in
    audio, so the ordering is a contract and not a preference."""
    duplicate = gd_constant(scene_source, "DUP_HIT_PULSE_SCALE")
    new_energy = 2.6  # the coefficient on `pulse` in `_apply_tiles`
    final_energy = gd_constant(scene_source, "FINAL_HIT_ENERGY")
    assert duplicate < 1.0
    assert final_energy > 2.0 * new_energy
    assert "_apply_tiles" in scene_source
    # A duplicate never moves its tile; only the other two do.
    tiles = scene_source.split("func _apply_tiles", 1)[1].split("\nfunc ", 1)[0]
    assert "push = NEW_HIT_PUSH * pulse" in tiles
    assert "dup" not in tiles.split("push = NEW_HIT_PUSH * pulse")[1].split("\n")[0]


def test_the_phase_three_completion_pulse_is_off_while_the_ending_plays(scene_source):
    """Both at once holds every tile at the completion colour for the length of
    the hold, and the wave has nothing to rise out of."""
    assert "and not _climax" in scene_source


def test_the_scene_still_contains_no_physics(scene_code):
    """Phase 3's assertion, re-stated because Phase 4 added the one thing that
    would most plausibly have justified breaking it: an ending whose ball has
    to keep moving after the run it came from has stopped."""
    for forbidden in (
        "RigidBody", "CharacterBody", "move_and_slide", "move_and_collide",
        "_physics_process", "PhysicsServer", "apply_impulse",
    ):
        assert forbidden not in scene_code, forbidden
    assert "func _process(" not in scene_code


def test_the_ending_is_a_pure_function_of_the_render_clock(scene_source):
    """`_apply_climax` reads `render_t` and the document and nothing else.

    No accumulator, so a still of the ending and the same instant of the clip
    are the same picture - the property the whole scene is built around, and
    the one a climax with a particle system would have quietly broken.
    """
    body = scene_source.split("func _apply_climax", 1)[1].split("\nfunc ", 1)[0]
    assert "var since := render_t - _final_seconds" in body
    for forbidden in ("+=  _time", "delta", "randf", "randi"):
        assert forbidden not in body, forbidden

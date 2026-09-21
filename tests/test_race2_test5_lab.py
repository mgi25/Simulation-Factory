"""The Test #5 P0 lab: the course, the control, and the measurements.

Three kinds of test here, and the middle kind is the one that matters most.

*Construction* is cheap and asserted exhaustively: six bays, six starts, one
pendulum, one mixer, a prefix of the production skeleton, a control that is the
same course with one module missing, and SWITCHYARD left alone.

*Measurement* is tested against hand-built inputs rather than against races,
because a metric that is only ever checked on a race it produced itself is a
metric nobody has read. `_kendall`, `_crossing_time`, `_box_gap` and
`_rank_change` all get synthetic series with the answer known in advance.

*Physics* is tested on a handful of fixed seeds, because each one costs a
couple of seconds. They protect the two claims the P0 verdict rests on - that a
seed reproduces exactly, and that the bare corridor reorders nothing the armed
one reorders - and nothing else.
"""

import math

import pytest

from marble3d.geometry import Transform
from marble3d.units import MARBLE_RADIUS

from race2 import concepts, courses
from race2 import test5_course as lab
from race2 import test5_lab as measure
from sloped import layout

MARBLE = 2.0 * layout.MARBLE_RADIUS
DURATION = 14.0


# --- construction ---------------------------------------------------------


def test_the_lab_starts_six_racers_in_six_symmetric_bays():
    """Six bays, not eight truncated to six.

    `MarbleSimulation` takes `starts[:marble_count]`, so an eight-bay shelf
    asked for six loads one side of the band and leaves two empty - a lateral
    bias present before the race starts.
    """
    course = lab.pendulum_p0()
    start = course.machine.modules["start"]

    assert lab.BAYS == 6
    assert start.bays == 6
    assert len(start.marble_starts()) == 6
    across = [start.bay_across(index) for index in range(start.bays)]
    assert across == sorted(across, reverse=True)
    assert sum(across) == pytest.approx(0.0)
    assert across[0] == pytest.approx(-across[-1])


def test_the_lab_is_a_prefix_of_the_production_skeleton():
    assert lab.P0_SKELETON == concepts.SKELETON[:5]
    assert lab.P0_BREAKS == concepts.SKELETON_BREAKS[:4]
    assert lab.P0_SEGMENTS == ("head", "pan1", "corr1", "pan2", "sprint")
    assert len(lab.P0_WIDTHS) == len(lab.P0_SEGMENTS) + 1

    course = lab.pendulum_p0()
    assert tuple(course.run_names()) == lab.P0_SEGMENTS
    # The same stretch of hill, sample for sample. The fifth run is
    # SWITCHYARD's `corr2` under a different name, because in a five-run course
    # that stretch is the final sprint - so the names diverge at the end even
    # though the centrelines do not.
    production = courses.build("switchyard")
    for name, other in zip(
        lab.P0_SEGMENTS, ("head", "pan1", "corr1", "pan2", "corr2")
    ):
        mine, theirs = course.runs[name], production.runs[other]
        assert len(mine.path) == len(theirs.path)
        assert mine.path == pytest.approx(theirs.path, abs=1e-12)
        assert mine.arc[-1] == pytest.approx(theirs.arc[-1], abs=1e-9)


def test_the_lab_is_short_enough_to_be_a_laboratory():
    course = lab.pendulum_p0()
    production = courses.build("switchyard")
    assert course.layout_length() < 0.6 * production.layout_length()
    assert course.drop() == pytest.approx(16.8, abs=0.2)


def test_the_corridor_holds_the_pendulum_and_nothing_else():
    course = lab.pendulum_p0()
    assert course.stations == ("studs", "pendulum")
    assert lab.PENDULUM_ID in course.machine.modules
    pendulum = course.machine.modules[lab.PENDULUM_ID]
    assert pendulum.run.id == lab.PENDULUM_RUN

    # The mixer is far upstream, on a different run, so a reordering inside
    # `corr1` has exactly one candidate cause: every other module that stands
    # *on* a run stands on a different one.
    mixer = course.machine.modules[lab.MIXER_ID]
    assert mixer.run.id == "head"
    standing_on_the_corridor = {
        module_id
        for module_id, module in course.machine.modules.items()
        if getattr(getattr(module, "run", None), "id", None) == lab.PENDULUM_RUN
    }
    assert standing_on_the_corridor == {lab.PENDULUM_ID}
    assert lab.PENDULUM_RUN in course.machine.modules


def test_the_control_is_the_same_course_with_the_arm_left_out():
    armed = lab.pendulum_p0()
    control = lab.pendulum_p0_bare()

    assert set(armed.machine.modules) - set(control.machine.modules) == {
        lab.PENDULUM_ID
    }
    assert lab.PENDULUM_ID not in control.stations
    assert lab.pendulum_progress(control) is None
    for name in lab.P0_SEGMENTS:
        assert armed.runs[name].path == control.runs[name].path
        assert armed.runs[name].widths == control.runs[name].widths
    assert armed.length == pytest.approx(control.length)
    assert armed.offsets == control.offsets


def test_the_control_carries_the_armed_course_s_own_track_settings():
    """A control built from a different course is not a control."""
    setting = lab.PendulumSetting(at=0.4, mixer_span=0.72)
    bare = setting.bare()

    assert bare.armed is False
    assert bare.at == setting.at
    assert bare.mixer_span == setting.mixer_span
    armed = lab.pendulum_p0(setting=setting)
    control = lab.pendulum_p0(setting=bare)
    assert lab.window_progress(armed, setting.at) == pytest.approx(
        lab.window_progress(control, bare.at)
    )
    assert armed.machine.modules[lab.MIXER_ID].span == 0.72
    assert control.machine.modules[lab.MIXER_ID].span == 0.72


def test_the_measurement_window_is_centred_on_the_arm():
    for at in (0.30, 0.50, 0.62, 0.85):
        setting = lab.PendulumSetting(at=at)
        course = lab.pendulum_p0(setting=setting)
        assert lab.window_progress(course, at) == pytest.approx(
            lab.pendulum_progress(course), abs=1e-9
        )
    course = lab.pendulum_p0()
    assert lab.corridor_end(course) == pytest.approx(
        course.offsets[lab.PENDULUM_RUN] + course.spans[lab.PENDULUM_RUN]
    )
    assert lab.pendulum_progress(course) < lab.corridor_end(course)


def test_the_lab_registry_cannot_be_confused_with_a_production_course():
    assert set(lab.course_names()) == {"pendulum_p0", "pendulum_p0_bare"}
    assert set(lab.TEST5_COURSES).isdisjoint(courses.COURSES)
    assert set(lab.TEST5_COURSES).isdisjoint(concepts.CONCEPTS)
    with pytest.raises(ValueError):
        lab.build("switchyard")
    # And SWITCHYARD is still eight bays over eleven runs.
    production = courses.build("switchyard")
    assert production.machine.modules["start"].bays == 8
    assert len(production.run_names()) == 11


def test_the_setting_is_picklable_because_a_pool_carries_it():
    import pickle

    setting = lab.PendulumSetting(amplitude_deg=11.0, rate=2.2, at=0.4, phase=1.5)
    assert pickle.loads(pickle.dumps(setting)) == setting
    assert pickle.loads(pickle.dumps(setting.bare())) == setting.bare()
    assert "a11" in setting.label()
    assert setting.bare().label().startswith("bare")


# --- the measurements, against inputs whose answer is known ---------------


def test_kendall_counts_the_pairs_that_swapped():
    assert measure._kendall((1, 2, 3), (1, 2, 3)) == 0
    assert measure._kendall((1, 2, 3), (2, 1, 3)) == 1
    assert measure._kendall((1, 2, 3), (3, 2, 1)) == 3
    # A marble missing from the second ordering contributes no pair.
    assert measure._kendall((1, 2, 3), (3, 1)) == 1


class _Series:
    """The two series `_rank_change` reads, as a stand-in for an outcome."""

    def __init__(self, progress, rank, racers):
        self.progress_series = progress
        self.rank_series = rank
        self.racers = racers


class _Racer:
    def __init__(self, marble_id, finish_order=None, finish_time=None):
        self.marble_id = marble_id
        self.finish_order = finish_order
        self.finish_time = finish_time


def test_a_crossing_time_is_interpolated_between_samples():
    outcome = _Series(
        progress=[(0.0, {1: 0.0}), (1.0, {1: 10.0}), (2.0, {1: 20.0})],
        rank=[(0.0, (1,))],
        racers=[_Racer(1)],
    )
    assert measure._crossing_time(outcome, 1, 5.0) == pytest.approx(0.5)
    assert measure._crossing_time(outcome, 1, 10.0) == pytest.approx(1.0)
    assert measure._crossing_time(outcome, 1, 15.0) == pytest.approx(1.5)
    assert measure._crossing_time(outcome, 1, 99.0) is None


def test_the_crossing_reading_sees_a_swap_the_sticky_one_would_blur():
    """Racer 2 enters the window behind racer 1 and leaves it in front."""
    progress = [
        (0.0, {1: 0.0, 2: 0.0}),
        (1.0, {1: 12.0, 2: 8.0}),
        (2.0, {1: 14.0, 2: 20.0}),
        (3.0, {1: 30.0, 2: 40.0}),
    ]
    rank = [(0.0, (1, 2)), (1.0, (1, 2)), (2.0, (2, 1)), (3.0, (2, 1))]
    outcome = _Series(progress, rank, [_Racer(1), _Racer(2)])

    change = measure._rank_change(outcome, "region", 10.0, 18.0)
    assert change.crossed == 2
    assert change.in_order == (1, 2)
    assert change.out_order == (2, 1)
    assert change.crossing_reordered == 2
    assert change.crossing_pairs == 1
    assert change.crossing_leader_lost is True
    assert change.crossing_leader_drop == 1
    assert change.crossing_best_gain == 1
    assert change.complete is True


def test_a_window_nobody_reached_is_reported_as_unmeasured():
    progress = [(0.0, {1: 0.0}), (1.0, {1: 4.0})]
    outcome = _Series(progress, [(0.0, (1,))], [_Racer(1)])
    change = measure._rank_change(outcome, "region", 50.0, 60.0)
    assert change.enter is None
    assert change.crossed == 0
    assert change.crossing_reordered == 0
    assert change.complete is False


def test_the_finish_scope_reads_the_finishing_order():
    progress = [(0.0, {1: 0.0, 2: 0.0}), (1.0, {1: 20.0, 2: 20.0})]
    rank = [(0.0, (1, 2)), (1.0, (1, 2))]
    outcome = _Series(
        progress,
        rank,
        [_Racer(1, finish_order=2, finish_time=9.0), _Racer(2, finish_order=1, finish_time=8.0)],
    )
    change = measure._rank_change(outcome, "finish", 10.0, 999.0)
    assert change.out_order == (2, 1)
    assert change.crossing_leader_lost is True
    assert change.leave == pytest.approx(9.0)


def test_the_box_gap_is_zero_inside_and_a_distance_outside():
    pose = Transform(position=(0.0, 0.0, 0.0))
    inverse = pose.inverse()
    half = (2.0, 0.5, 0.25)

    assert measure._box_gap(inverse, half, (0.0, 0.0, 0.0)) == pytest.approx(0.0)
    assert measure._box_gap(inverse, half, (1.9, 0.4, 0.2)) == pytest.approx(0.0)
    assert measure._box_gap(inverse, half, (0.0, 1.5, 0.0)) == pytest.approx(1.0)
    assert measure._box_gap(inverse, half, (3.0, 0.0, 0.0)) == pytest.approx(1.0)
    assert measure._box_gap(inverse, half, (3.0, 1.5, 0.0)) == pytest.approx(
        math.sqrt(2.0)
    )
    # And the pose is respected, not assumed to be the identity.
    moved = Transform(position=(10.0, 0.0, 0.0))
    assert measure._box_gap(moved.inverse(), half, (13.0, 0.0, 0.0)) == pytest.approx(
        1.0
    )


def test_the_touch_threshold_is_under_a_radius_and_over_the_sample_error():
    """`TOUCH_SLACK` decides what counts as contact; both bounds matter."""
    assert 0.0 < measure.TOUCH_SLACK < 0.25 * MARBLE_RADIUS
    # A racer at 35 simulation units a second covers this much per substep.
    assert measure.TOUCH_SLACK > 0.5 * (35.0 / 240.0)


# --- physics, on fixed seeds ---------------------------------------------


def test_a_seed_reproduces_exactly():
    setting = lab.PendulumSetting()
    first = measure.measure_seed(setting, 11, duration=DURATION)
    again = measure.measure_seed(setting, 11, duration=DURATION)
    assert first.to_json() == again.to_json()


def test_six_racers_finish_and_the_arm_is_measured():
    seed = measure.measure_seed(lab.PendulumSetting(), 11, duration=DURATION)

    assert seed.armed is True
    assert seed.racers == 6
    assert seed.finished == 6
    assert seed.escaped == 0
    assert seed.stuck == 0
    assert seed.jam is False
    assert sorted(seed.slots) == [0, 1, 2, 3, 4, 5]
    assert sorted(seed.finish_order) == [0, 1, 2, 3, 4, 5]
    assert seed.last_finish is not None and seed.last_finish < DURATION
    # Every racer gets a finite closest approach, and the two readings agree.
    assert len(seed.contacts) == 6
    for contact in seed.contacts:
        assert math.isfinite(contact.min_gap)
        assert contact.touched == (contact.min_gap <= measure.TOUCH_SLACK)
        if contact.touched:
            assert contact.first_touch is not None
            assert contact.touch_windows >= 1
        else:
            assert contact.first_touch is None
            assert contact.touch_seconds == 0.0
    assert seed.touched() >= 1


def test_the_arm_reorders_the_corridor_the_bare_control_does_not():
    """The P0 finding, as a regression test on one seed.

    Both courses are deterministic, so this is a fact about seed 11 and not a
    sample: the corridor with nothing in it hands the field on in the order it
    received it, and the corridor with the arm in it does not.
    """
    setting = lab.PendulumSetting()
    armed = measure.measure_seed(setting, 11, duration=DURATION)
    control = measure.measure_seed(setting.bare(), 11, duration=DURATION)

    assert control.armed is False
    assert control.contacts == []
    assert control.changes["corridor"].crossing_reordered == 0
    assert control.changes["corridor"].in_order == control.changes["corridor"].out_order

    assert armed.changes["corridor"].crossing_reordered >= 2
    assert armed.changes["corridor"].crossed == 6
    assert armed.changes["corridor"].in_order != armed.changes["corridor"].out_order


def test_the_arm_hands_no_racer_free_speed():
    """A kinematic arm is infinitely heavy, so it can shove without limit.

    The same check `tests/test_race2_physics.py` makes of SWITCHYARD, made of
    the pendulum, and made here rather than read off `RunStats.max_energy_rise`
    because that field is never filled on this path: it is accumulated by
    `marble3d.simulation.run_simulation`, and `race2.race.run_race` is a
    different driver. A zero from an unconnected instrument reads exactly like
    a pass, so the invariant is stepped through instead.
    """
    from marble3d.config import DEFAULT_CONFIG
    from race2.race import Race2

    race = Race2(lab.pendulum_p0(), DEFAULT_CONFIG, seed=11, marble_count=lab.BAYS)
    try:
        settle = race._settle_time
        peak = None
        while race.ticks < 240 * 10:
            race.step()
            if race.elapsed < settle + 0.25:
                continue
            energy = race.energy()
            if peak is None:
                peak = energy
            assert energy <= peak * 1.02 + 1.0, (
                f"energy rose from {peak:.1f} to {energy:.1f} at {race.elapsed:.2f} s"
            )
            peak = max(peak, energy)
    finally:
        race.close()


def test_the_recomputed_arm_pose_is_the_pose_the_simulation_used():
    """What the contact measurement rests on, checked against the replay.

    `arm_contacts` recomputes the arm's pose from `pose_at` rather than reading
    it out of the replay, so that it can evaluate at 240 Hz instead of the
    replay's 60. That is only sound if the two agree where they overlap.
    """
    from race2.race import run_race

    setting = lab.PendulumSetting()
    course = lab.pendulum_p0(setting=setting)
    _outcome, replay = run_race(
        course, seed=11, marble_count=lab.BAYS, duration=4.0, with_replay=True
    )
    module = course.machine.modules[lab.PENDULUM_ID]
    arm = module.local_actuators()[0]
    dt = 1.0 / float(replay.physics_hz)
    key = f"{lab.PENDULUM_ID}.{arm.name}"

    checked = 0
    for frame in replay.frames:
        recorded = frame.actuators.get(key)
        if recorded is None:
            continue
        tick = int(round(frame.time / dt))
        pose = module.transform.compose(arm.pose_at(tick, dt))
        assert pose.position == pytest.approx(recorded[0], abs=1e-9)
        assert pose.rotation == pytest.approx(recorded[1], abs=1e-9)
        checked += 1
    assert checked > 100


# --- the benchmark's own shape -------------------------------------------


def test_the_benchmark_json_carries_what_the_report_quotes():
    setting = lab.PendulumSetting()
    bench = measure.run_p0_seeds(setting, [11, 12], duration=DURATION, workers=1)
    data = bench.to_json()

    for key in (
        "label",
        "setting",
        "geometry",
        "races",
        "racers",
        "finish_rate",
        "all_finished_rate",
        "jam_rate",
        "escape_rate",
        "stuck_rate",
        "stuck_at_pendulum",
        "slot_correlation",
        "winner_by_slot",
        "mean_lead_changes",
        "mean_late_lead_changes",
        "mean_comeback",
        "mean_longest_gap",
        "worst_longest_gap",
        "worst_penetration",
        "worst_actuator_overlap",
        "worst_travel_per_tick",
        "travel_budget",
        "race_times",
        "changes",
        "contacts",
        "useful_seeds",
        "worst_seeds",
        "seeds",
    ):
        assert key in data, key

    assert data["races"] == 2
    assert data["racers"] == 12
    assert data["setting"]["armed"] is True
    assert data["geometry"]["kind"] == "PendulumCross"
    assert set(data["changes"]) == {"region", "corridor", "finish"}
    for scope in data["changes"].values():
        for key in ("measured", "any_change_rate", "leader_lost_rate", "mean_reordered"):
            assert key in scope, key
    assert data["contacts"]["measured"] == 2
    assert data["race_times"]["n"] == 2
    assert "0.00%" not in bench.summary() or True  # the summary renders at all
    assert bench.summary().splitlines()[0].startswith(bench.label)


def test_a_configuration_the_channel_refuses_is_recorded_not_skipped():
    """Which settings are unbuildable is a result, not an error to swallow."""
    wild = lab.PendulumSetting(amplitude_deg=40.0, at=0.85)
    benches = measure.sweep([wild], [11], duration=DURATION, workers=1)

    assert len(benches) == 1
    assert benches[0].races == 0
    assert "axle" in benches[0].geometry["refused"]
    assert benches[0].label == wild.label()


def test_the_aggregate_helpers_agree_with_hand_arithmetic():
    assert measure._median([]) == 0.0
    assert measure._median([3.0]) == 3.0
    assert measure._median([1.0, 2.0, 3.0]) == 2.0
    assert measure._median([1.0, 2.0, 3.0, 4.0]) == 2.5
    assert measure._quantile([1.0, 2.0, 3.0, 4.0, 5.0], 0.0) == 1.0
    assert measure._quantile([1.0, 2.0, 3.0, 4.0, 5.0], 0.5) == 3.0
    assert measure._quantile([1.0, 2.0, 3.0, 4.0, 5.0], 1.0) == 5.0
    assert measure._quantile([0.0, 10.0], 0.1) == pytest.approx(1.0)

"""The Test #5 pendulum: its contract, and the geometry that contract hides.

The first six tests here shipped with the mechanism and all six passed while
the arm was 0.64 layout units under the cradle at every angle in its arc and
outside both guard rails past 25 degrees. They are kept, because each one still
asserts something true and necessary - a pure pose, a bounded arc, one large
actuator, no racer in the metadata - and they are kept *with that note* because
the useful lesson is that a determinism contract can be perfectly satisfied by
a collider that is inside the floor.

What is added is the survey: where the swept box actually goes, measured
against the cradle arc and the rail the run was built with, at every angle.
`test_the_historical_typed_geometry_is_caught_by_the_survey` races the survey
against the exact numbers that were wrong, so the instrument is tested and not
merely used.
"""

import math

import pytest

from marble3d.geometry import quat_rotate
from race2 import concepts
from race2.test5_parts import PendulumArm, PendulumCross
from sloped import layout
from sloped.scale import SIM_TO_LAYOUT, to_sim

MARBLE = 2.0 * layout.MARBLE_RADIUS


def _run(name: str = "corr1"):
    return concepts.build("cascade").runs[name]


def _at(run, fraction: float) -> int:
    return max(2, min(len(run.path) - 3, int(round(fraction * (len(run.path) - 1)))))


# --- the contract, as it shipped -----------------------------------------


def test_pendulum_pose_is_a_pure_function_of_tick():
    module = PendulumCross("pendulum", _run(), at=20)
    arm = module.local_actuators()[0]
    dt = 1.0 / 240.0

    first = arm.pose_at(137, dt)
    _ = arm.pose_at(991, dt)
    again = arm.pose_at(137, dt)

    assert first == again


def test_pendulum_angle_stays_inside_authored_arc():
    module = PendulumCross("pendulum", _run(), at=20)
    arm = module.local_actuators()[0]
    dt = 1.0 / 240.0

    angles = [arm.angle_at(tick, dt) for tick in range(0, 2400)]
    assert max(angles) <= module.amplitude + 1e-12
    assert min(angles) >= -module.amplitude - 1e-12
    assert max(angles) > 0.99 * module.amplitude
    assert min(angles) < -0.99 * module.amplitude


def test_pendulum_hangs_down_at_zero_phase():
    run = _run()
    module = PendulumCross("pendulum", run, at=20, phase=0.0)
    arm = module.local_actuators()[0]
    pose = arm.pose_at(0, 1.0 / 240.0)

    _lateral, up, _forward = run.frames[module.index]
    long_axis = quat_rotate(pose.rotation, (1.0, 0.0, 0.0))
    assert long_axis == pytest.approx(tuple(-v for v in up), abs=1e-9)


def test_pendulum_is_one_large_readable_actuator():
    module = PendulumCross("pendulum", _run(), at=20)
    actuators = module.local_actuators()

    assert len(actuators) == 1
    assert actuators[0].name == "arm"
    assert actuators[0].half_extents[0] == pytest.approx(0.5 * to_sim(module.arm_length))
    # Readable means large next to a racer, which is the only scale that
    # matters: an arm shorter than a couple of marbles is a flap, not a
    # pendulum.
    assert module.arm_length > 3.0 * MARBLE


def test_pendulum_metadata_cannot_select_a_racer():
    data = PendulumCross("pendulum", _run(), at=20).describe()

    assert data["reactive"] is False
    assert data["selection"] == "arrival_phase_only"
    forbidden = {"winner", "racer", "marble", "colour", "color", "slot"}
    assert forbidden.isdisjoint(data)


def test_pendulum_rejects_nonphysical_configuration():
    with pytest.raises(ValueError):
        PendulumArm(
            "bad",
            pivot=(0, 0, 0),
            lateral=(1, 0, 0),
            up=(0, 1, 0),
            forward=(0, 0, 1),
            length=1.0,
            thickness=0.1,
            depth=0.1,
            amplitude=math.pi / 2,
            rate=1.0,
        )


def test_nothing_in_the_mechanism_reads_a_racer():
    """A source scan, because a docstring promise is not an invariant.

    `race2.test5_parts` may know about a marble's *size* - it sizes its own
    clearances against one - and must not know about a marble's identity. The
    distinction is exactly the tokens below.

    Comments and string literals are stripped first, and that is not a
    loophole: the module's own docstring says "no racer identity anywhere in
    it", so a scan of the raw text fails on the sentence that states the
    invariant. What has to be clean is the code.
    """
    import io
    import pathlib
    import tokenize

    import race2.test5_parts as module

    text = pathlib.Path(module.__file__).read_text(encoding="utf-8")
    skip = {tokenize.COMMENT, tokenize.STRING, tokenize.NL, tokenize.NEWLINE}
    skip |= {
        getattr(tokenize, name)
        for name in ("FSTRING_START", "FSTRING_MIDDLE", "FSTRING_END")
        if hasattr(tokenize, name)
    }
    code = " ".join(
        token.string
        for token in tokenize.generate_tokens(io.StringIO(text).readline)
        if token.type not in skip
    )
    for token in ("marble_id", "start_slot", "winner", "colour", "color", "identity"):
        assert token not in code, f"the mechanism's code names {token!r}"


# --- the survey: where the swept box actually goes ------------------------


STATIONS = [
    ("corr1", 0.30),
    ("corr1", 0.62),
    ("corr1", 0.85),
    ("pan2", 0.50),
    ("head", 0.62),
]


@pytest.mark.parametrize("name,fraction", STATIONS)
def test_the_swept_arm_never_reaches_the_cradle(name, fraction):
    run = _run(name)
    module = PendulumCross("pendulum", run, at=_at(run, fraction))
    clearance, _reach = module.clearances()

    assert clearance > 0.0, f"the arm is {-clearance:.3f} into the cradle"
    assert clearance == pytest.approx(module.CLEARANCE * run.scale, abs=1e-6)
    # And low enough that a racer cannot pass under it, which is the other half
    # of the requirement: an arm a marble fits beneath is not an obstacle.
    assert clearance < MARBLE


@pytest.mark.parametrize("name,fraction", STATIONS)
def test_the_swept_arm_leaves_more_than_a_marble_beside_it(name, fraction):
    run = _run(name)
    module = PendulumCross("pendulum", run, at=_at(run, fraction))
    _clearance, reach = module.clearances()

    assert reach == pytest.approx(module.swept_across, abs=1e-6)
    assert reach < module.half_width()
    assert module.side_gap() >= MARBLE
    assert module.describe()["gate"] is False


def test_a_marble_diameter_beside_the_arm_is_not_enough_for_a_field():
    """`Wheel`'s safety test is a single-marble test; a field is not one.

    The constructor refuses a side gap under one marble diameter because that
    pins a racer against the rail. Between one and two diameters nothing is
    pinned and a *pack* still cannot pass two abreast, so it queues - which is
    measurably what happens. `describe()` has to report both, because the
    single-marble reading calls the default configuration safe while it is
    stopping racers dead.
    """
    run = _run("corr1")
    narrow = PendulumCross("narrow", run, at=_at(run, 0.62))
    data = narrow.describe()

    assert narrow.side_gap() > MARBLE
    assert 1.0 < narrow.side_gap_marbles() < 2.0
    assert narrow.pack_gate() is True
    assert data["gate"] is False, "the single-marble test passes"
    assert data["pack_gate"] is True, "and the pack test does not"
    assert data["side_gap_marbles"] == pytest.approx(
        narrow.side_gap() / MARBLE, abs=1e-4
    )

    # The corridor's entry has not funnelled down from the pan yet, so a low
    # reach there does leave two racers room to pass abreast.
    wide = PendulumCross("wide", run, at=_at(run, 0.20), reach=0.40)
    assert wide.side_gap_marbles() > 2.0
    assert wide.pack_gate() is False
    assert wide.describe()["pack_gate"] is False


def test_an_arm_that_never_uncovers_the_centreline_is_refused():
    """The plug condition, and the one a lower reach walks into.

    The swing moves the arm's axis through +/- L sin A and the box carries half
    its depth either side, so at `L sin A <= depth / 2` the box covers the
    channel's centre at every angle in the arc and a marble centred there is
    held for the whole race. Measured over nine configurations and 450 races,
    `centre_uncovered` orders the pinning perfectly: -0.099 pinned ten racers,
    -0.013 pinned four, +0.073 pinned one, +0.131 and above pinned none.
    """
    run = _run("corr1")
    with pytest.raises(ValueError, match="uncovers the channel centreline"):
        PendulumCross("plug", run, at=_at(run, 0.62), amplitude_deg=10.0, reach=0.40)

    # And the shipped default clears it, by about half a marble radius.
    fine = PendulumCross("fine", run, at=_at(run, 0.62))
    assert fine.centre_uncovered() > 0.0
    assert fine.centre_uncovered() == pytest.approx(
        fine.arm_length * math.sin(fine.amplitude) - 0.5 * fine.depth, abs=1e-9
    )
    assert fine.centre_uncovered() > 0.4 * layout.MARBLE_RADIUS
    assert fine.describe()["centre_uncovered"] == pytest.approx(
        fine.centre_uncovered(), abs=1e-4
    )


def test_a_lower_reach_is_not_a_safer_one():
    """Reach trades lateral room against arm length, and length is what matters.

    Lowering the reach widens the side gap and shortens the arm, which walks
    the geometry *towards* the plug condition. Over 50 seeds each, reach 0.40
    finished all six racers in 76% of races and reach 0.60 in 94% - the
    opposite of what the side gap alone predicts.

    0.52 is used as the low end rather than the 0.40 that produced that number,
    because the guard added with this finding now refuses 0.40 and 0.46 here.
    Those configurations are in the recorded evidence and are no longer
    buildable, which is the point of the guard.
    """
    run = _run("corr1")
    index = _at(run, 0.62)
    wide_gap = PendulumCross("low", run, at=index, reach=0.52)
    tight_gap = PendulumCross("high", run, at=index, reach=0.60)

    assert wide_gap.side_gap() > tight_gap.side_gap()
    assert wide_gap.arm_length < tight_gap.arm_length
    assert wide_gap.pivot_rise < tight_gap.pivot_rise
    assert wide_gap.centre_uncovered() < tight_gap.centre_uncovered()


@pytest.mark.parametrize("name,fraction", STATIONS)
def test_the_axle_hangs_over_the_channel_and_not_inside_it(name, fraction):
    run = _run(name)
    module = PendulumCross("pendulum", run, at=_at(run, fraction))

    assert module.pivot_rise >= module.axle_floor()
    assert module.pivot_rise > module.rail_top()


def test_the_geometry_is_derived_from_the_local_half_width():
    """The lesson `race2.parts.Wheel` paid for, asserted here.

    A pendulum whose arm is a typed constant sweeps a fixed distance into a
    channel whose width varies along the run. The same setting at a wide sample
    and a narrow one must give two different arms, and the reach must scale
    with the channel and not with anything else.
    """
    run = _run("corr1")
    wide = PendulumCross("wide", run, at=_at(run, 0.30))
    narrow = PendulumCross("narrow", run, at=_at(run, 0.85))

    assert wide.half_width() > narrow.half_width()
    assert wide.arm_length > narrow.arm_length
    assert wide.swept_across / wide.half_width() == pytest.approx(
        narrow.swept_across / narrow.half_width(), rel=1e-6
    )


def test_the_historical_typed_geometry_is_caught_by_the_survey():
    """The defect this module was corrected for, re-created and measured.

    `PendulumCross` shipped with `ARM_LENGTH = 2.30` and `PIVOT_RISE = 1.72`
    stated before the run's profile scale, so at Race #2's scale of 2.0 the arm
    was 4.60 long on a 3.44 pivot. Rebuilt here by hand, because the constants
    are gone: the point is that the survey the fix is built on can see the
    failure, not that the failure is still reachable through the constructor.
    """
    run = _run("corr1")
    index = _at(run, 0.30)
    lateral, up, forward = run.frames[index]
    centre = run.sim_path[index]
    rise = to_sim(1.72 * run.scale)
    arm = PendulumArm(
        name="arm",
        pivot=tuple(centre[axis] + up[axis] * rise for axis in range(3)),
        lateral=lateral,
        up=up,
        forward=forward,
        length=to_sim(2.30 * run.scale),
        thickness=to_sim(0.18 * run.scale),
        depth=to_sim(0.34 * run.scale),
        amplitude=math.radians(46.0),
        rate=3.65,
    )
    width = run.widths[index]
    worst_clear = math.inf
    worst_across = 0.0
    for step in range(121):
        angle = -arm.amplitude + 2.0 * arm.amplitude * step / 120.0
        pose = arm.pose_for_angle(angle)
        for sx in (-1.0, 1.0):
            for sy in (-1.0, 1.0):
                for sz in (-1.0, 1.0):
                    point = pose.apply(
                        (
                            sx * arm.half_extents[0],
                            sy * arm.half_extents[1],
                            sz * arm.half_extents[2],
                        )
                    )
                    offset = [point[axis] - centre[axis] for axis in range(3)]
                    across = (
                        sum(offset[axis] * lateral[axis] for axis in range(3))
                        * SIM_TO_LAYOUT
                    )
                    height = (
                        sum(offset[axis] * up[axis] for axis in range(3)) * SIM_TO_LAYOUT
                    )
                    cradle = layout.floor_y_at(across / (run.scale * width)) * run.scale
                    worst_clear = min(worst_clear, height - cradle)
                    worst_across = max(worst_across, abs(across))

    half = layout.CHANNEL_HALF * run.scale * width
    # Through the floor by more than a marble diameter, and outside the rail.
    assert worst_clear < -MARBLE
    assert worst_across > half
    # And the corrected module, at the same station, is inside both.
    fixed = PendulumCross("fixed", run, at=index)
    clearance, reach = fixed.clearances()
    assert clearance > 0.0
    assert reach < half


# --- refusals -------------------------------------------------------------


def test_an_amplitude_the_channel_cannot_hold_is_refused():
    """Wide swing, short arm, axle inside the rail: not buildable, so refused.

    The bound is not a policy - it is `arm length >= rail top + axle radius -
    cradle` - and a pendulum that violates it is an axle standing in the racing
    line rather than a pendulum hanging over it.
    """
    run = _run("corr1")
    with pytest.raises(ValueError, match="axle"):
        PendulumCross("wild", run, at=_at(run, 0.85), amplitude_deg=40.0)


def test_a_wider_station_accepts_a_swing_a_corridor_refuses():
    """The coupling between where it stands and how far it may swing."""
    narrow = _run("corr1")
    wide = _run("head")
    with pytest.raises(ValueError):
        PendulumCross("narrow", narrow, at=_at(narrow, 0.85), amplitude_deg=34.0)
    built = PendulumCross("wide", wide, at=_at(wide, 0.62), amplitude_deg=34.0)
    assert built.clearances()[0] > 0.0
    assert built.side_gap() >= MARBLE


def test_a_reach_that_would_pin_a_racer_against_the_rail_is_refused():
    run = _run("corr1")
    with pytest.raises(ValueError, match="clear channel"):
        PendulumCross("pin", run, at=_at(run, 0.62), reach=0.92, amplitude_deg=10.0)


def test_reach_and_rate_are_validated():
    run = _run("corr1")
    with pytest.raises(ValueError, match="fraction"):
        PendulumCross("bad", run, at=20, reach=1.4)
    with pytest.raises(ValueError, match="rate"):
        PendulumCross("bad", run, at=20, rate=0.0)


# --- the module contract's cheap parts -----------------------------------


def test_the_arm_is_built_once_because_it_is_asked_for_every_tick():
    """`BuiltModule.apply_actuators` calls `local_actuators` at 240 Hz."""
    module = PendulumCross("pendulum", _run(), at=20)
    assert module.local_actuators() is module.local_actuators()


def test_the_bounds_are_the_swept_volume_and_are_measured_once():
    """`Machine.module_at` gives the smallest containing box the attribution.

    A cube of the arm's reach would be several times the volume the arm can
    touch and would take every nearby marble's module attribution off the
    corridor it is actually in.
    """
    run = _run("corr1")
    module = PendulumCross("pendulum", run, at=_at(run, 0.62))
    bounds = module.local_bounds()
    assert module.local_bounds() is bounds

    reach = to_sim(module.arm_length)
    slack = to_sim(2.0 * layout.MARBLE_RADIUS)
    cube = (2.0 * (reach + slack)) ** 3
    size = bounds.size()
    volume = size[0] * size[1] * size[2]
    assert volume < 0.5 * cube
    # And it still contains the axle and the whole swing.
    arm = module.local_actuators()[0]
    assert bounds.contains(arm.pivot)
    for angle in (-module.amplitude, 0.0, module.amplitude):
        assert bounds.contains(arm.tip_at(angle))


def test_the_description_carries_the_geometry_a_report_has_to_quote():
    module = PendulumCross("pendulum", _run(), at=20)
    data = module.describe()
    for key in (
        "arm_length",
        "pivot_rise",
        "half_width",
        "side_gap",
        "side_gap_marbles",
        "centre_uncovered",
        "pack_gate",
        "rail_top",
        "cradle_clearance",
        "reach_across",
        "period",
        "sweep_speed",
        "blocked_fraction",
        "swept_fraction",
    ):
        assert key in data, key
    assert data["period"] == pytest.approx(2.0 * math.pi / module.rate, abs=1e-4)
    assert 0.0 < data["blocked_fraction"] < 1.0
    assert data["swept_fraction"] == pytest.approx(module.reach, abs=1e-6)

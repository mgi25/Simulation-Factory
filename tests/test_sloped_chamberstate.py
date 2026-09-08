"""The pre-release instrument, pinned on cases whose answers are known.

The statistics in `sloped.chamberstate` are the ones a decision about the rotor
is read off, and three sessions in a row have had to correct the instrument
before the geometry. So each one is checked against a hand-constructed field
whose correct answer is arithmetic rather than simulated.
"""

from __future__ import annotations

import math

import pytest

from sloped import layout
from sloped.chamberstate import (
    angular_span,
    bearing_noise_floor,
    circular_linear,
    cyclic_orientation,
    pearson,
    resultant,
    summarise_chamber,
    ChamberSample,
)
from sloped.shuffle import Rotor, ShuffleChamber
from sloped.startlab import ROTOR_CANDIDATES, start_machine
from sloped.track import TrackRun


# --- the statistics ------------------------------------------------------


def test_pearson_is_exact_on_a_straight_line():
    assert pearson([0, 1, 2, 3], [1.0, 3.0, 5.0, 7.0]) == pytest.approx(1.0)
    assert pearson([0, 1, 2, 3], [7.0, 5.0, 3.0, 1.0]) == pytest.approx(-1.0)


def test_pearson_refuses_a_constant_rather_than_dividing_by_zero():
    assert pearson([0, 1, 2, 3], [2.0, 2.0, 2.0, 2.0]) is None


def test_circular_linear_finds_a_bearing_that_is_a_function_of_the_bay():
    """Eight bays spread over half a turn is as strong as the relation gets."""
    bays = list(range(8))
    angles = [math.radians(180.0 * b / 7.0) for b in bays]
    assert circular_linear(bays, angles) == pytest.approx(1.0, abs=0.02)


def test_circular_linear_has_a_ceiling_below_one_when_the_bays_wrap():
    """And the ceiling is what a measured value has to be read against.

    Eight bays at eight bearings 45 degrees apart is a *deterministic* map from
    bay to bearing, but it is not a linear-circular one: the bay index is not
    monotone in any linear embedding of a circle it goes all the way round. So
    Mardia's coefficient tops out at about 0.81 rather than 1.0, and the
    chamber's measured 0.22 to 0.40 are fractions of 0.81 and not of 1.
    """
    bays = list(range(8))
    angles = [math.radians(45.0 * b) for b in bays]
    assert circular_linear(bays, angles) == pytest.approx(0.806, abs=0.005)


def test_circular_linear_is_blind_to_a_bulk_rotation():
    """The same field, turned bodily, is the same relation.

    This is the property the plain component correlations do not have, and the
    reason both are reported: `bay -> x` swings sign as the rotor carries the
    field round while the relation itself is unchanged.
    """
    bays = list(range(8))
    plain = [math.radians(45.0 * b) for b in bays]
    turned = [a + 1.9 for a in plain]
    assert circular_linear(bays, turned) == pytest.approx(
        circular_linear(bays, plain), abs=1e-9
    )


def test_cyclic_orientation_is_total_when_the_necklace_is_only_rotated():
    bays = list(range(8))
    bearings = [(45.0 * b + 137.0) % 360.0 for b in bays]
    agree, total = cyclic_orientation(bays, bearings)
    assert total == 56                                  # C(8,3)
    assert agree == total


def test_cyclic_orientation_is_zero_when_the_necklace_is_reversed():
    bays = list(range(8))
    bearings = [(-45.0 * b) % 360.0 for b in bays]
    agree, total = cyclic_orientation(bays, bearings)
    assert agree == 0


def test_resultant_separates_a_shared_preference_from_eight_of_them():
    """One arc for everybody is fair; one arc each is not.

    `resultant` reports a length per bay and `angular_span` reports how far
    apart the bay means are, and it takes both to tell the cases apart - the
    pooled circular-linear coefficient cannot.
    """
    shared = [10.0, 12.0, 8.0, 11.0, 9.0]
    _mean, length = resultant(shared)
    assert length > 0.99
    spread = [0.0, 90.0, 180.0, 270.0]
    _mean, length = resultant(spread)
    assert length < 1e-9


def test_angular_span_takes_the_short_way_round():
    assert angular_span([350.0, 10.0]) == pytest.approx(20.0)
    assert angular_span([0.0, 90.0, 180.0]) == pytest.approx(180.0)


def test_the_noise_floor_is_the_quoted_figure():
    assert bearing_noise_floor(192) == pytest.approx(0.0640, abs=5e-4)
    assert bearing_noise_floor(0) == 0.0


# --- the summary ---------------------------------------------------------


def _sample(bearings, radii=None, seed=0):
    count = len(bearings)
    radii = radii or [1.25] * count
    return ChamberSample(
        seed=seed,
        tick=100,
        time=0.4167,
        rotor_phase=0.0,
        rotor_angle=0.0,
        blades=4,
        bays=tuple(range(count)),
        x=tuple(r * math.cos(math.radians(b)) for r, b in zip(radii, bearings)),
        y=(0.0,) * count,
        z=tuple(r * math.sin(math.radians(b)) for r, b in zip(radii, bearings)),
        radius=tuple(radii),
        bearing=tuple(bearings),
        speed=(0.0,) * count,
        in_chamber=(True,) * count,
    )


def test_a_field_that_kept_its_order_reports_it_kept_its_order():
    samples = [_sample([45.0 * b for b in range(8)], seed=s) for s in range(12)]
    report = summarise_chamber(samples)
    assert report["cyclic_order_retained"] == pytest.approx(1.0)
    assert report["bearing_resultant_mean"] == pytest.approx(1.0)
    assert report["bay_bearing_mean_span_deg"] == pytest.approx(315.0)


def test_a_racer_that_never_arrived_is_left_out_rather_than_averaged_in():
    """A racer with no chamber position is not evidence about mixing.

    Including it would put the apron's own ordering into a chamber statistic,
    which is the shape of mistake `_stall` had to be corrected for in V1.7.
    """
    good = _sample([45.0 * b for b in range(8)])
    absent = ChamberSample(**{**good.__dict__, "in_chamber": (True,) * 7 + (False,)})
    report = summarise_chamber([good, absent])
    assert report["racers"] == 16
    assert report["in_chamber"] == 15
    assert report["in_chamber_pct"] == pytest.approx(93.75)
    # The order statistics need a whole field, so only the complete trial
    # contributes triples.
    assert report["cyclic_triples"] == 56


# --- the rotor's own timing ----------------------------------------------


def test_the_held_rotor_turns_the_same_number_of_degrees_for_everyone():
    """`start_time` is the whole point: no rotation before the field is in.

    A racer that arrives late has a shorter residence, and with the rotor
    turning from tick zero that is a smaller transport angle - which is the bay
    written into the bearing. Held, the angle from `start_time` to `stop_time`
    is one number and every racer gets it.
    """
    rotor = Rotor(
        name="rotor0",
        half_extents=(1.0, 0.1, 0.05),
        hub=(0.0, 0.0, 0.0),
        lateral=(1.0, 0.0, 0.0),
        up=(0.0, 1.0, 0.0),
        forward=(0.0, 0.0, 1.0),
        radius=1.0,
        blade=0,
        blades=4,
        phase=0.0,
        rate=5.0,
        start_time=1.6,
        stop_time=4.6,
        spin_down=0.30,
        tail_rate=0.0,
    )
    dt = 1.0 / 240.0
    assert rotor.angle_at(0, dt) == pytest.approx(0.0)
    assert rotor.angle_at(int(1.6 * 240), dt) == pytest.approx(0.0)
    # Three seconds of turning at 5 rad/s.
    assert rotor.angle_at(int(4.6 * 240), dt) == pytest.approx(15.0, abs=0.02)
    # And it holds still afterwards, spin-down included.
    late = rotor.angle_at(int(9.0 * 240), dt)
    assert late == pytest.approx(rotor.angle_at(int(5.0 * 240), dt), abs=1e-9)


def test_the_held_rotor_angle_never_jumps():
    """A kinematic box that teleports hands a marble an impulse from nowhere."""
    chamber = ShuffleChamber("start", TrackRun("launch"), rotor_hold=True)
    rotor = next(a for a in chamber.local_actuators() if a.name == "rotor0")
    dt = 1.0 / 240.0
    previous = rotor.angle_at(0, dt)
    worst = 0.0
    for tick in range(1, int(12.0 * 240)):
        angle = rotor.angle_at(tick, dt)
        worst = max(worst, abs(angle - previous))
        previous = angle
    # One tick at the full rate, and no more.
    assert worst <= chamber.rotor_rate * dt + 1e-9


def test_holding_the_rotor_moves_only_when_it_turns_not_how_long():
    held = ShuffleChamber("start", TrackRun("launch"), rotor_hold=True)
    running = ShuffleChamber("start", TrackRun("launch"), rotor_hold=False)
    assert held.rotor_stop == running.rotor_stop
    assert held.gate_time == running.gate_time
    assert running.rotor_start == 0.0
    assert held.rotor_start == pytest.approx(
        held.release_time + held.ENTRY_ALLOWANCE
    )
    assert held.rotor_turns < running.rotor_turns


def test_the_shipped_rotor_still_runs_from_tick_zero():
    """V1.7's recorded numbers have to stay reproducible in this class."""
    assert ShuffleChamber.ROTOR_HOLD_ENTRY is False
    assert ShuffleChamber("start", TrackRun("launch")).rotor_start == 0.0


def test_the_held_candidate_asks_for_a_held_rotor_and_gets_one():
    machine = start_machine(plan=ROTOR_CANDIDATES["rotor-held"])
    start = machine.modules["start"]
    assert start.rotor_hold is True
    assert start.describe()["rotor"]["holds_until_field_in"] is True


def test_the_sample_frame_inverts_the_module_placement():
    """`_to_local` has to be the exact inverse of `stations._place`.

    A bearing measured in the wrong frame is a bearing about the wrong axis,
    and every statistic in this module is computed from one.
    """
    from sloped.chamberstate import _to_local
    from sloped.stations import _place

    chamber = ShuffleChamber("start", TrackRun("launch"))
    for point in ((0.0, 0.0, chamber.CHAMBER_Z), (1.7, -0.4, 2.2), (-2.3, 0.9, -1.1)):
        world = _place(chamber.origin, chamber.frame, point)
        back = _to_local(chamber, world)
        assert back == pytest.approx(point, abs=1e-9)


def test_a_marble_on_the_chamber_floor_reads_as_in_the_chamber():
    """The `in_chamber` gate has to accept the case it exists to accept."""
    from sloped.chamberstate import _to_local
    from sloped.stations import _place
    from sloped.scale import LAYOUT_TO_SIM

    chamber = ShuffleChamber("start", TrackRun("launch"))
    radius = chamber.rest_radius
    seat = chamber.floor_at(radius) + layout.MARBLE_RADIUS
    world = _place(chamber.origin, chamber.frame, (radius, seat, chamber.CHAMBER_Z))
    local = _to_local(chamber, world)
    assert math.hypot(local[0], local[2] - chamber.CHAMBER_Z) == pytest.approx(
        radius, abs=1e-9
    )
    assert local[1] == pytest.approx(seat, abs=1e-9)
    assert LAYOUT_TO_SIM > 1.0                       # the frame really converts

"""The full-floor release, pinned where the geometry check found the defects.

Three of these exist because the thing they assert was wrong first:

* the seam is `pitch - thickness`, not `pitch`, and it is widest at 90 degrees
  rather than growing forever;
* the well has to clear a marble *standing on* the dish, not the dish;
* the paddles have to be out of the way before the floor opens.

Each was found by measurement and each is cheap to assert, so each is asserted.
"""

from __future__ import annotations

import math

import pytest

from sloped import course, layout
from sloped.shuffle import ShuffleChamber, chamber_table
from sloped.startlab import FLOOR_CANDIDATES, start_machine
from sloped.trapdoor import (
    FloorPanel,
    ShuffleFloor,
    floor_table,
    panels_by_index,
    seam_gap,
)
from sloped.track import TrackRun

DIAMETER = 2.0 * layout.MARBLE_RADIUS


@pytest.fixture(scope="module")
def floor() -> ShuffleFloor:
    return ShuffleFloor("start", TrackRun("launch"))


# --- position independence, which is the whole point ---------------------


def test_every_panel_shares_one_release_and_reads_nothing_else(floor):
    """Section 5: the timing depends on the tick and the configuration only."""
    panels = floor.floor_panels()
    assert len(panels) == floor.PANELS * floor.PANEL_SPLITS
    triples = {(p.release_time, p.duration, p.sweep) for p in panels}
    assert len(triples) == 1
    release, duration, sweep = triples.pop()
    assert release == pytest.approx(floor.floor_open)
    assert duration == pytest.approx(floor.FLOOR_DURATION)
    assert sweep == pytest.approx(math.radians(floor.PANEL_SWEEP))


def test_a_panel_pose_is_a_pure_function_of_the_tick(floor):
    panel = floor.floor_panels()[0]
    dt = 1.0 / 240.0
    for tick in (0, 500, 1464, 1465, 3000):
        first = panel.pose_at(tick, dt)
        second = panel.pose_at(tick, dt)
        assert first.position == second.position
        assert first.rotation == second.rotation


def test_a_panel_is_still_before_its_release_and_still_after_it(floor):
    panel = floor.floor_panels()[0]
    dt = 1.0 / 240.0
    open_tick = int(floor.floor_open * 240)
    assert panel.angle_at(0, dt) == 0.0
    assert panel.angle_at(open_tick, dt) == 0.0
    done = int((floor.floor_open + floor.FLOOR_DURATION) * 240) + 1
    assert panel.angle_at(done, dt) == pytest.approx(
        math.radians(floor.PANEL_SWEEP)
    )
    assert panel.angle_at(done + 10000, dt) == pytest.approx(
        panel.angle_at(done, dt)
    )


def test_the_panel_angle_never_jumps(floor):
    """A kinematic box that teleports hands a marble an impulse from nowhere."""
    panel = floor.floor_panels()[0]
    dt = 1.0 / 240.0
    previous = panel.angle_at(0, dt)
    worst = 0.0
    for tick in range(1, int(9.0 * 240)):
        angle = panel.angle_at(tick, dt)
        worst = max(worst, abs(angle - previous))
        previous = angle
    # The smoothstep's steepest slope is 1.5 times the mean rate.
    assert worst <= 1.6 * math.radians(floor.PANEL_SWEEP) * dt / floor.FLOOR_DURATION


# --- the seam, which is the clearance that matters -----------------------


def test_the_seam_is_pitch_minus_thickness_and_widest_at_ninety(floor):
    """The correction the geometry check caught.

    A closed form in the module docstring said the gap grew without bound past
    90 degrees. It does not: the slat folds back over its own hinge and the gap
    closes again. Measured at a 120-degree sweep it was 0.299 against 0.800 at
    90, so the sweep is 90.
    """
    from sloped.trapdoor import _seam

    peak = max(_seam(floor, math.radians(deg)) for deg in range(181))
    assert peak == pytest.approx(floor.panel_pitch - floor.PANEL_THICK, abs=1e-9)
    assert _seam(floor, math.radians(90.0)) == pytest.approx(peak, abs=1e-9)
    assert _seam(floor, math.radians(120.0)) < 0.5 * peak
    assert floor.PANEL_SWEEP == 90.0


def test_the_seam_passes_a_marble_freely(floor):
    table = floor_table(floor)["floor"]
    assert table["final_seam_diameters"] >= 1.25
    assert table["seam_passes_a_marble_at_deg"] is not None
    assert table["seam_passes_freely_at_deg"] is not None


def test_the_seam_only_ever_opens(floor):
    """A gap that closes is a scissor whatever its size.

    Measured on the real box corners, projected onto the direction the seam
    opens in - which is the check that found the fold. The gap is negative
    while the slats' corners overlap in projection at the very start, and
    clamped to zero there, so what is asserted is that it never goes *down*
    from a positive value.
    """
    by_index = panels_by_index(floor)
    along = tuple(float(v) for v in floor.frame[2])
    for index in range(floor.PANELS - 1):
        gaps = []
        for deg in range(int(floor.PANEL_SWEEP) + 1):
            angle = math.radians(deg)
            here = [c for p in by_index[index] for c in p.corners_at(angle)]
            there = [c for p in by_index[index + 1] for c in p.corners_at(angle)]
            gaps.append(seam_gap(here, there, along))
        for step in range(len(gaps) - 1):
            assert gaps[step + 1] >= gaps[step] - 1e-9


# --- coverage ------------------------------------------------------------


def test_the_slats_cover_the_whole_chamber_disc(floor):
    """A slat short of its chord leaves a crescent with nothing under it."""
    for row in range(-24, 25):
        for column in range(-24, 25):
            x = column * floor.R_WALL / 24.0
            z = row * floor.R_WALL / 24.0
            if math.hypot(x, z) > floor.R_WALL:
                continue
            index = min(
                max(int(math.floor((z + floor.R_WALL) / floor.panel_pitch)), 0),
                floor.PANELS - 1,
            )
            low, high = floor.panel_band(index)
            assert low - 1e-9 <= z <= high + 1e-9
            step = floor.panel_pitch / floor.PANEL_SPLITS
            split = min(int(math.floor((z - low) / step)), floor.PANEL_SPLITS - 1)
            sub_low = low + split * step
            reach = floor.panel_half_length(sub_low, sub_low + step)
            assert abs(x) <= reach + 1e-9


def test_a_slat_reaches_its_chord_everywhere_on_its_own_band(floor):
    """Sized from the band edge nearest the centre, not the far one."""
    for index in range(floor.PANELS):
        low, high = floor.panel_band(index)
        step = floor.panel_pitch / floor.PANEL_SPLITS
        for split in range(floor.PANEL_SPLITS):
            sub_low = low + split * step
            reach = floor.panel_half_length(sub_low, sub_low + step)
            for sample in range(9):
                z = sub_low + step * sample / 8.0
                chord = math.sqrt(max(floor.R_WALL ** 2 - z * z, 0.0))
                assert reach >= chord - 1e-9


# --- the well, and the marble standing in it ----------------------------


def test_the_well_clears_a_marble_standing_on_the_dish(floor):
    """The defect that cost six of fifteen stage-A traces.

    A slat at 90 degrees hangs as a plate reaching one pitch below the floor
    plane. The dish was set clear of *that*, and a marble resting on the dish
    then stood 0.023 into the hanging plate and rolled along its face instead
    of down the dish. The well carries a marble diameter for that reason.
    """
    hanging = floor.panel_pitch + 0.5 * floor.PANEL_THICK
    assert floor.panel_well >= hanging + DIAMETER
    marble_top_on_dish = floor.panel_well - DIAMETER
    assert marble_top_on_dish > hanging


def test_the_dish_catches_the_whole_chamber(floor):
    """A marble over nothing falls out of the machine and is never located."""
    for row in range(-20, 21):
        for column in range(-20, 21):
            x = column * floor.R_WALL / 20.0
            z = row * floor.R_WALL / 20.0
            if math.hypot(x, z) > floor.R_WALL:
                continue
            assert floor._inside(x, floor.CHAMBER_Z + z)


def test_the_cone_has_no_flat_spot(floor):
    """The basin's finding: a level floor is statically stable under a pile."""
    previous = None
    for step in range(60):
        radius = floor.CATCH_HALF * (1.0 - step / 59.0)
        here = floor.dish_at(radius, floor.CHAMBER_Z)
        if previous is not None:
            assert here <= previous - 1e-6 or radius <= floor.THROAT_R
        previous = here


def test_the_throat_is_the_low_point_and_it_is_on_the_axis(floor):
    """The fairness decision, as an assertion.

    A catch with one exit orders the field by path length to it, so the exit's
    position decides which coordinate decides the race. On the chamber's axis
    that coordinate is the radius, which is the one the rotor equalises. The
    first build drained to a notch 2.75 downstream and measured a
    centre-versus-rank correlation of +0.886.
    """
    lip = floor.dish_at(0.0, floor.CHAMBER_Z)
    assert lip == pytest.approx(floor.dish_lip, abs=1e-9)
    # The same height at every bearing at a given radius, which is what makes
    # the ordering statistic the radius and nothing else.
    for radius in (1.2, 1.9, 2.6):
        heights = {
            round(floor.dish_at(radius * math.cos(math.radians(deg)),
                                floor.CHAMBER_Z
                                + radius * math.sin(math.radians(deg))), 9)
            for deg in range(0, 360, 15)
        }
        assert len(heights) == 1
        assert heights.pop() > lip
    assert floor.describe()["catch"]["orders_the_field_by"] == (
        "radius from the chamber axis"
    )


def test_the_chute_grade_the_lift_is_sized_from_is_the_one_it_gets(floor):
    """V1.7's remaining issue 3, closed.

    There the chute's 0.24 landing shaped the geometry but was left out of
    `derived_lift`, so the realised grade came out 2.7 degrees shallower than
    the target the lift was sized from and the two names disagreed.
    """
    realised = floor.describe()["heights"]["chute_grade_deg"]
    assert realised == pytest.approx(floor.CHUTE_GRADE, abs=0.05)


# --- the paddles get out of the way -------------------------------------


def test_the_paddles_rise_clear_before_the_floor_opens(floor):
    """The third wall of the pocket, removed.

    Two racers of 96 were held at the chamber's radius limit between the wall,
    a hanging slat's top edge and a stopped blade. The first two are
    structural.
    """
    assert floor.ROTOR_LIFT > 0.0
    under = floor.FLOOR_CLEAR + floor.ROTOR_LIFT
    assert under >= DIAMETER
    assert floor.rotor_lift_time >= floor.rotor_stop + floor.SPIN_DOWN
    assert floor.rotor_lift_time + floor.ROTOR_LIFT_OVER <= floor.floor_open


def test_the_lift_is_a_pure_function_of_the_tick_and_clamped(floor):
    rotor = next(a for a in floor.local_actuators() if a.name == "rotor0")
    dt = 1.0 / 240.0
    from sloped.scale import to_sim

    assert rotor.lift_at(0, dt) == 0.0
    assert rotor.lift_at(int(floor.rotor_lift_time * 240), dt) == 0.0
    done = int((floor.rotor_lift_time + floor.ROTOR_LIFT_OVER) * 240) + 1
    assert rotor.lift_at(done, dt) == pytest.approx(to_sim(floor.ROTOR_LIFT))
    assert rotor.lift_at(done + 5000, dt) == pytest.approx(
        rotor.lift_at(done, dt)
    )


def test_the_shipped_rotor_chamber_does_not_lift_its_paddles():
    """V1.7's outlet needs the blades where they are."""
    assert ShuffleChamber.ROTOR_LIFT == 0.0
    chamber = ShuffleChamber("start", TrackRun("launch"))
    rotor = next(a for a in chamber.local_actuators() if a.name == "rotor0")
    assert rotor.lift_by == 0.0
    dt = 1.0 / 240.0
    assert rotor.lift_at(int(9.0 * 240), dt) == 0.0


# --- the chamber the release changed ------------------------------------


def test_the_chamber_floor_is_flat_and_the_blade_clearance_constant(floor):
    assert floor.FLOOR_TILT == 0.0
    heights = {round(floor.floor_at(r), 9) for r in (0.0, 0.5, 1.3, 2.0, 2.7)}
    assert heights == {round(floor.rim_floor, 9)}
    assert floor.floor_at(floor.TIP_R) == floor.floor_at(floor.ROOT_R)


def test_the_chamber_has_no_static_floor(floor):
    """The floor is a moving part, so there is nothing to fire a probe at."""
    names = {mesh.name for piece in floor._chamber() for mesh in [piece]}
    assert names
    assert not any("floor" in name for name in names)
    assert all("wall" in name for name in names)
    assert not any(label.startswith("start.floor") for label in
                   (probe.label for probe in floor.local_probes()))


def test_the_field_can_pass_itself_with_no_ring_in_the_way(floor):
    clear = chamber_table(floor)["clearances"]
    assert floor.rest_radius == 0.0
    assert clear["free_radial_diameters"] >= 4.0


def test_no_outlet_actuators_survive(floor):
    names = [a.name for a in floor.local_actuators()]
    assert not [n for n in names if n.startswith("outlet")]
    assert len([n for n in names if n.startswith("panel")]) == (
        floor.PANELS * floor.PANEL_SPLITS
    )
    assert len([n for n in names if n.startswith("rotor")]) == floor.PADDLES
    assert len([n for n in names if n.startswith("paddle")]) == layout.BAYS


# --- the height chain, and that it is derived ---------------------------


def test_the_lift_is_derived_from_this_chain_and_not_inherited(floor):
    """Section 9: neither 2.14 nor 4.30 is assumed."""
    assert floor.lift > 0.0
    heights = floor.describe()["heights"]
    assert heights["chamber_floor"] < heights["pan_floor"]
    assert heights["dish_edge"] < heights["chamber_floor"]
    assert heights["dish_lip"] < heights["dish_edge"]
    assert heights["exit_seat"] < heights["dish_lip"]
    # The chute's realised grade is the one it was sized from, because the
    # chute interpolates straight from the dish's lip to the launch's seat.
    assert heights["chute_grade_deg"] == pytest.approx(floor.CHUTE_GRADE, abs=0.2)


def test_the_release_timeline_is_ordered(floor):
    assert floor.release_time < floor.rotor_start < floor.rotor_stop
    assert floor.rotor_stop + floor.SPIN_DOWN <= floor.rotor_lift_time
    assert floor.rotor_lift_time < floor.floor_open
    assert floor.gate_time == floor.floor_open


# --- and the wiring ----------------------------------------------------


def test_the_course_knows_the_kind_and_still_ships_the_fan():
    assert "floor" in course.START_KINDS
    assert course.START_CLASSES["floor"] is ShuffleFloor
    assert course.START_KIND == "fan"
    built = course.start_module("floor", TrackRun("launch"))
    assert built.START_KIND == "floor"
    assert isinstance(built, ShuffleFloor)


def test_the_shipped_course_still_checks_clean():
    assert course.check() == []


@pytest.mark.parametrize("name", sorted(FLOOR_CANDIDATES))
def test_each_floor_candidate_builds_what_it_says(name):
    plan = FLOOR_CANDIDATES[name]
    machine = start_machine(plan=plan)
    start = machine.modules["start"]
    assert machine.start_kind == "floor"
    assert isinstance(start, ShuffleFloor)
    assert start.rotor_hold is plan.rotor_hold
    assert start.mix_seconds == plan.mix_seconds
    assert start.SETTLE_SECONDS == plan.settle_seconds


def test_the_two_candidates_differ_only_in_the_rotor_schedule():
    plain = FLOOR_CANDIDATES["floor-plain"]
    tuned = FLOOR_CANDIDATES["floor-tuned"]
    differ = {
        field for field in plain.describe()
        if plain.describe()[field] != tuned.describe()[field]
    }
    assert differ == {"name", "rotor_hold", "mix_seconds", "settle_seconds"}

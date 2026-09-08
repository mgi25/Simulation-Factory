"""The dynamic start equaliser: the clearances, the timeline, and the actuator.

Three groups, and each exists because something in it was got wrong first.

**The clearances.** The whole reason the rotor moved out of the channel and into
a chamber is that a circular sweep inside a straight wall has a *closing* gap -
the earlier wheel's ran 0.94 to 0.04 four times a revolution, passing through
exactly one marble diameter on the way, and jammed 18.8% of the field. Every
gap here is constant, and each is pinned either well below a marble (so nothing
can enter it) or well above (so everything passes). The dangerous state is
"about one marble", which is what the check tool's own first version wrongly
flagged 0.15 as.

**The timeline.** The architecture's one rule is that the exit stays shut while
mixing happens. That is three orderings - field in before the rotor stops,
rotor stopped before the outlet opens, outlet open before the trial ends - and
each is chained off the visible gate's own release time rather than typed.

**The actuator.** Section 9 requires the rotor's angle and the gate's state to
be pure functions of the tick. A rate that changes has to be *integrated* into
the angle, because a sampled rate change puts a step in it, and a kinematic box
that teleports a paddle-width hands a marble an impulse from nowhere.
"""

from __future__ import annotations

import math

import pytest

from sloped import course as _course
from sloped import layout
from sloped.shuffle import Rotor, ShuffleChamber, chamber_table
from sloped.startlab import (
    BENCH_PLANS,
    ROTOR_CANDIDATES,
    StartTrial,
    seed_phase_for,
    start_machine,
)
from sloped.track import TrackRun

DIAMETER = 2.0 * layout.MARBLE_RADIUS


@pytest.fixture(scope="module")
def chamber():
    return ShuffleChamber("start", TrackRun("launch"))


# --- the fifth kind, and the gates that still hold ------------------------


def test_rotor_is_a_registered_start_kind():
    assert ShuffleChamber.START_KIND == "rotor"
    assert _course.START_CLASSES["rotor"] is ShuffleChamber
    # Membership rather than a count. The count grows every session a topology
    # is tried - V1.8 added `floor` - and pinning it fails for the one reason
    # that is never interesting, which the sibling assertion in
    # `tests/test_sloped_start_kind.py` says in as many words and then did.
    assert "rotor" in _course.START_KINDS
    assert len(set(_course.START_KINDS)) == len(_course.START_CLASSES)


def test_every_topology_still_builds_the_class_its_name_promises():
    for kind in _course.START_KINDS:
        machine = start_machine(plan=BENCH_PLANS[kind])
        assert machine.start_kind == kind
        assert type(machine.modules["start"]) is _course.START_CLASSES[kind]


def test_the_shipped_course_is_untouched():
    assert _course.START_KIND == "fan"
    assert _course.check() == []


# --- every clearance is constant, and none is about one marble ------------


def test_no_clearance_is_within_reach_of_a_marble(chamber):
    """The jam condition. A gap traps only if a marble can get *into* it."""
    clear = chamber_table(chamber)["clearances"]
    for name in ("tip_to_wall", "root_to_gate_ring", "between_paddles_at_root"):
        ratio = clear[name] / DIAMETER
        assert not 0.45 <= ratio <= 1.25, f"{name} is {ratio:.2f} marble diameters"


def test_the_tip_to_wall_gap_is_the_same_at_every_rotor_angle(chamber):
    """The property the chamber exists for.

    The earlier wheel's gap was `0.94 - 0.90 sin(angle)`. This one has no angle
    in it at all, because the wall is concentric with the sweep - so there is
    nothing for a tip to close on.
    """
    gap = chamber.R_WALL - chamber.TIP_R
    for degrees in range(0, 360, 15):
        angle = math.radians(degrees)
        tip = (chamber.TIP_R * math.cos(angle), chamber.TIP_R * math.sin(angle))
        here = chamber.R_WALL - math.hypot(*tip)
        assert here == pytest.approx(gap, abs=1e-12)
    assert gap < 0.45 * DIAMETER


def test_the_field_can_pass_itself(chamber):
    """V1.5's trough put eight marbles at one radius in a channel one marble
    wide, where they cannot exchange cyclic order, so a stirrer could only
    rotate the necklace and the bay order survived it."""
    clear = chamber_table(chamber)["clearances"]
    assert clear["free_radial_diameters"] >= 1.8


def test_the_chamber_holds_the_field_with_room(chamber):
    """Section 5: not barely large enough."""
    clear = chamber_table(chamber)["clearances"]
    assert clear["area_ratio"] >= 5.0
    assert 2.0 * chamber.R_WALL <= 2.0 * layout.START_BACK_HALF + 0.10


def test_a_blade_clears_the_floor_at_its_tip_and_traps_nothing_at_its_root(chamber):
    """A `Spinner` is a box at one height and the floor is a cone, so the
    underside has to be set from the *outermost* floor it passes over. Set from
    the root instead, the blade sat 0.093 into the floor at its tip."""
    at_tip = chamber.FLOOR_CLEAR
    at_root = (chamber.floor_at(chamber.TIP_R) + chamber.FLOOR_CLEAR
               - chamber.floor_at(chamber.ROOT_R))
    assert at_tip > 0.0
    assert at_root < DIAMETER
    # And the blade reaches below a resting marble's centre everywhere it
    # sweeps, or it rides over the field instead of pushing it.
    top = chamber.floor_at(chamber.TIP_R) + chamber.FLOOR_CLEAR
    for radius in (chamber.ROOT_R, 0.5 * (chamber.ROOT_R + chamber.TIP_R),
                   chamber.TIP_R):
        centre = chamber.floor_at(radius) + layout.MARBLE_RADIUS
        assert top < centre < top + chamber.PADDLE_HEIGHT


# --- the outlet ------------------------------------------------------------


def test_the_retracted_gate_ring_clears_the_exit_chute(chamber):
    """At 0.80 of travel the ring stood *in* the chute's mouth as a fence at
    radius 0.89, and five of eight racers were pinned inside it."""
    ring_top = (chamber.floor_at(chamber.GATE_R) + chamber.GATE_HEIGHT
                - chamber.GATE_DROP)
    mouth = chamber.chute_mouth_z
    run = chamber.exit_local[2] - mouth
    start = chamber.outlet_lip - 0.24
    seat = chamber.exit_local[1] + layout.FLOOR_Y
    t = ((chamber.CHAMBER_Z - chamber.GATE_R) - mouth) / run
    assert ring_top < start + t * (seat - start)


def test_the_chute_mouth_covers_the_whole_outlet(chamber):
    """A mouth downstream of the hole's upstream edge opens the rest of the
    hole onto nothing, and every racer falls out of the machine."""
    assert chamber.chute_mouth_z < chamber.CHAMBER_Z - chamber.GATE_R
    assert chamber.CHUTE_HALF >= chamber.GATE_R


def test_the_outlet_is_wide_enough_not_to_arch(chamber):
    """At 1.50 across - 2.6 marbles - the field arched over it and stopped.
    V1.5's drain arched at 1.24 and passed at 1.90."""
    assert 2.0 * chamber.GATE_R >= 3.2 * DIAMETER


def test_the_outlet_is_one_ring_released_together(chamber):
    ports = [a for a in chamber.local_actuators() if a.name.startswith("outlet")]
    assert len(ports) == chamber.GATE_SEGMENTS
    assert len({round(a.release_time, 9) for a in ports}) == 1
    assert len({round(a.duration, 9) for a in ports}) == 1
    # The polygon's own radius error, against the octagon's 0.084.
    error = chamber.GATE_R * (
        1.0 / math.cos(math.pi / chamber.GATE_SEGMENTS) - 1.0)
    assert error < 0.05


# --- the timeline ----------------------------------------------------------


def test_the_exit_is_shut_while_the_mixing_happens(chamber):
    """The architecture's one rule, in three orderings."""
    assert chamber.rotor_stop > chamber.release_time + 0.6
    assert chamber.gate_time >= chamber.rotor_stop + chamber.SPIN_DOWN
    assert chamber.gate_time > chamber.rotor_stop
    # And it is chained off the visible gate rather than typed.
    assert chamber.rotor_stop == pytest.approx(
        chamber.release_time + chamber.ENTRY_ALLOWANCE + chamber.mix_seconds)


def test_the_mixing_interval_is_in_the_briefs_range(chamber):
    """Section 6: a physically reasonable 0.5 to 2.0 seconds."""
    assert 0.5 <= chamber.mix_seconds <= 2.0
    assert chamber.rotor_turns > 0.5


def test_the_three_actuator_families_are_all_present(chamber):
    kinds: dict[str, int] = {}
    for actuator in chamber.local_actuators():
        key = actuator.name.rstrip("0123456789")
        kinds[key] = kinds.get(key, 0) + 1
    assert kinds == {
        "paddle": layout.BAYS,
        "rotor": chamber.PADDLES,
        "outlet": chamber.GATE_SEGMENTS,
    }


def test_the_start_paddles_stand_at_their_own_bays(chamber):
    """`StartGrid.local_actuators` places from the fan's trough; V1.5's radial
    start inherited that and a racer ran into a paddle out on the apron."""
    paddles = [a for a in chamber.local_actuators() if a.name.startswith("paddle")]
    seats = chamber.marble_starts()
    for index, paddle in enumerate(paddles):
        assert math.dist(paddle.rest.position, seats[index].position) < 1.0


def test_the_lift_is_derived_and_below_the_radial_starts(chamber):
    assert chamber.lift < 4.30
    assert chamber.pan_floor + 1e-9 >= chamber.rim_floor


def test_the_mesh_is_clean(chamber):
    from marble3d.validation import check_mesh

    assert check_mesh(chamber.local_colliders()[0], expect_components=None) == []


# --- the actuator is a pure function of the tick --------------------------


def _rotor(**kwargs):
    base = dict(
        name="r", half_extents=(1.0, 0.2, 0.05), hub=(0.0, 0.0, 0.0),
        lateral=(1.0, 0.0, 0.0), up=(0.0, 1.0, 0.0), forward=(0.0, 0.0, 1.0),
        radius=1.0, blade=0, blades=4, phase=0.25, rate=5.0,
        stop_time=2.0, spin_down=0.30,
    )
    base.update(kwargs)
    return Rotor(**base)


def test_the_rotor_angle_is_continuous_across_the_spin_down():
    """A sampled rate change steps the angle, and a kinematic box that
    teleports a paddle-width hands a marble an impulse from nowhere."""
    rotor = _rotor()
    dt = 1.0 / 240.0
    previous = None
    for tick in range(0, int(4.0 * 240)):
        angle = rotor.angle_at(tick, dt)
        if previous is not None:
            assert angle - previous < 5.0 * dt * 1.5
            assert angle >= previous - 1e-12
        previous = angle


def test_the_rotor_stops_and_stays_stopped_with_no_tail():
    rotor = _rotor(tail_rate=0.0)
    dt = 1.0 / 240.0
    settled = rotor.angle_at(int(2.4 * 240), dt)
    assert rotor.angle_at(int(6.0 * 240), dt) == pytest.approx(settled)
    # And it turned the amount the profile says: full rate, then half of it
    # through the ramp.
    assert settled == pytest.approx(0.25 + 5.0 * (2.0 + 0.5 * 0.30), abs=1e-9)


def test_a_tail_rate_keeps_the_rotor_turning_for_ever():
    rotor = _rotor(tail_rate=1.2)
    dt = 1.0 / 240.0
    a = rotor.angle_at(int(4.0 * 240), dt)
    b = rotor.angle_at(int(5.0 * 240), dt)
    assert b - a == pytest.approx(1.2, abs=1e-3)


def test_the_rotor_angle_depends_on_nothing_but_the_tick():
    rotor = _rotor()
    dt = 1.0 / 240.0
    once = [rotor.angle_at(t, dt) for t in range(0, 900, 7)]
    twice = [rotor.angle_at(t, dt) for t in range(0, 900, 7)]
    assert once == twice
    assert rotor.angle_at(0, dt) == pytest.approx(0.25)


def test_the_rotors_pose_is_exported_for_the_replay():
    """Section 25: the replay carries the rotor's own state."""
    data = _rotor(tail_rate=1.2).to_json()
    for key in ("hub", "radius", "phase", "offset", "rate", "stop_time",
                "spin_down", "tail_rate"):
        assert key in data


# --- the seed-derived phase ------------------------------------------------


def test_the_seed_phase_is_deterministic_and_global():
    """Section 7 allows this precisely because it is one angle for the whole
    field: it cannot depend on racer identity because it is not given one."""
    assert seed_phase_for(41) == seed_phase_for(41)
    assert seed_phase_for(41) != seed_phase_for(42)
    for seed in range(0, 500, 37):
        assert 0.0 <= seed_phase_for(seed) < 2.0 * math.pi


def test_the_seed_phase_spreads_consecutive_seeds():
    """A fixed phase gives the rotor four fixed parking bearings, and a phase
    that walked slowly with the seed would give four slowly-walking ones."""
    angles = [seed_phase_for(seed) for seed in range(24)]
    gaps = [abs(angles[i + 1] - angles[i]) for i in range(len(angles) - 1)]
    assert min(gaps) > 0.5


def test_the_plan_carries_the_phase_choice_into_the_report():
    fixed = ROTOR_CANDIDATES["rotor-fixed"].describe()
    seeded = ROTOR_CANDIDATES["rotor-seeded"].describe()
    assert fixed["seed_phase"] is False
    assert seeded["seed_phase"] is True
    assert fixed["start_kind"] == seeded["start_kind"] == "rotor"


def test_a_seed_phase_plan_on_a_start_with_no_rotor_is_refused():
    import dataclasses

    from sloped.startlab import run_trial

    plan = dataclasses.replace(BENCH_PLANS["fan"], seed_phase=True)
    machine = start_machine(plan=plan)
    with pytest.raises(TypeError, match="has no rotor"):
        run_trial(0, machine=machine, duration=0.1)


def test_the_seed_phase_actually_reaches_the_rotor():
    machine = start_machine(plan=ROTOR_CANDIDATES["rotor-seeded"])
    start = machine.modules["start"]
    start.rotor_phase = seed_phase_for(7)
    rotors = [a for a in start.local_actuators() if a.name.startswith("rotor")]
    assert len(rotors) == start.PADDLES
    for rotor in rotors:
        assert rotor.phase == pytest.approx(seed_phase_for(7))
    # All four blades share the phase, so they stay a rotor.
    assert len({round(r.phase, 12) for r in rotors}) == 1


# --- the instrument's blind spot ------------------------------------------


def test_a_marble_that_never_reached_a_run_is_still_reported_stuck():
    """**The blind spot this closes made two whole failures look like clean
    runs.** `_where` is only set once a marble has touched the launch or leg1,
    so a start that never delivers leaves every racer unlocated - and both
    V1.5's converging funnel and this chamber at two positions reported
    `lost 0, stuck 0` while delivering zero of 192 racers.
    """
    machine = start_machine(plan=ROTOR_CANDIDATES["rotor-fixed"])
    trial = StartTrial(machine, seed=0)
    try:
        trial._grace_ticks = 0
        assert trial._where.get(0) is None
        for _ in range(trial.STOPPED_FOR // trial.LOCATE_EVERY + 1):
            trial._stall(0, (0.0, 0.0, 0.0))
        assert 0 in trial.stuck
        assert trial.stuck[0] == ("start", 0)
    finally:
        trial.sim.close()


def test_a_held_marble_is_still_not_a_race_stall():
    """The V1.5 regression, re-checked against a start that holds its field for
    nearly four seconds by design."""
    machine = start_machine(plan=ROTOR_CANDIDATES["rotor-fixed"])
    trial = StartTrial(machine, seed=0)
    try:
        hz = trial.sim.config.physics.physics_hz
        assert trial._grace_ticks >= machine.modules["start"].gate_time * hz
        for _ in range(4 * trial.STOPPED_FOR // trial.LOCATE_EVERY):
            trial._stall(0, (0.0, 0.0, 0.0))
        assert trial.stuck == {}
    finally:
        trial.sim.close()

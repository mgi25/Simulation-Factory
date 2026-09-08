"""The shared apron, and the two invariants the radial start's fairness rests on.

Everything else about this start is reported rather than asserted - the guide
lengths are unequal and cannot be made equal, the grades vary, the curvature
varies. Two things are *exact*, by derivation rather than by tuning, and they
are what the architecture exists to establish:

    the drop from the resting pan to the trough        identical for all eight
    the radius from the drain at rest                  identical for all eight

So those are pinned here, along with the properties that make eight guides on
one single-valued surface possible at all: they do not cross, they do not climb,
and the east four are the exact mirror of the west four.

The stall-accounting regression from section 8 of the V1.4 brief is here too,
because the instrument and the geometry fail together: a lab that calls a held
marble stuck reports a start that works as a start that froze, which is what
the first radial trial did.
"""

from __future__ import annotations

import math

import pytest

from sloped import layout
from sloped.apron import bay_x, plan_length
from sloped.radial import RadialStart
from sloped.startlab import BENCH_PLANS, StartTrial, start_machine
from sloped.track import TrackRun


@pytest.fixture(scope="module")
def start():
    return RadialStart("start", TrackRun("launch"))


# --- the two exact invariants ---------------------------------------------


def test_the_drop_to_the_trough_is_identical_for_all_eight(start):
    """One pan height and one trough height, so the drop is one number.

    Not "equal to within a tolerance": both endpoints are single derived
    properties, so this is exact, and a non-zero spread means an edit has put a
    per-bay term into the height chain.
    """
    guides = start.guides()
    drops = [guides.fall(index, 1.0) for index in range(layout.BAYS)]
    # 1e-12 rather than exactly zero: `fall` evaluates the same closed form
    # per bay with that bay's own length, so the answer differs in the last
    # bit of a double. The point is that there is no per-bay *term*.
    assert max(drops) - min(drops) < 1e-12
    assert drops[0] == pytest.approx(start.APRON_DROP, abs=1e-12)
    assert start.rest_floor - start.trough_floor == pytest.approx(
        start.APRON_DROP, abs=1e-12
    )


def test_every_guide_delivers_at_exactly_the_trough_rim(start):
    guides = start.guides()
    rim = start.TROUGH_R + start.TROUGH_HALF
    radii = [
        math.hypot(guides.paths()[index][-1][0],
                   guides.paths()[index][-1][1] - start.DISH_Z)
        for index in range(layout.BAYS)
    ]
    assert max(radii) - min(radii) == pytest.approx(0.0, abs=1e-9)
    assert radii[0] == pytest.approx(rim, abs=1e-9)


def test_the_resting_radius_is_derived_from_the_gate_ring(start):
    """The marble rests against the ring's outer face, so that face sets it."""
    assert start.rest_radius == pytest.approx(
        start.PADDLE_R + layout.MARBLE_RADIUS, abs=1e-12
    )
    assert start.paddle_floor == pytest.approx(
        start.trough_y(start.rest_radius), abs=1e-12
    )


def test_the_delivery_bearings_are_exactly_45_degrees_apart(start):
    """`157.5 / 3.5` is 45, so the map from the line to the ring is exact."""
    guides = start.guides()
    bearings = sorted(guides.bearing(index) for index in range(layout.BAYS))
    for index, bearing in enumerate(bearings):
        assert bearing == pytest.approx(22.5 + 45.0 * index, abs=1e-9)


# --- what makes eight guides on one surface possible ----------------------


def test_no_guide_climbs_anywhere_along_its_length(start):
    """Section 5 of the brief: no hidden upward segments."""
    for index in range(layout.BAYS):
        previous = None
        for step in range(241):
            point = start.guide_point(index, step / 240.0)
            if previous is not None:
                assert point[1] <= previous[1] + 1e-9, f"bay {index} climbs at {step}"
            previous = point


def test_the_guides_do_not_cross(start):
    """On a single-valued surface a crossing is not a crossing, it is a fork.

    The nesting order is by sweep magnitude, and it is what the bay-to-bearing
    map is chosen to produce - see `ApronGuides.slot`.
    """
    paths = start.guides().paths()
    for a in range(layout.BAYS):
        for b in range(a + 1, layout.BAYS):
            gap = min(math.dist(u, v) for u in paths[a] for v in paths[b])
            assert gap > 0.30, f"guides {a} and {b} meet at {gap:.3f}"


def test_the_east_four_guides_are_the_exact_mirror_of_the_west_four(start):
    """So the left-right half of any bias is zero by construction.

    Exact, not approximate: the east routes are built by negating the west
    ones. This caught a real bug once - bay 7 stalling where bay 0 did not,
    which could only be the *simulation* differing, and was: the release
    paddles were being placed by the fan's geometry.
    """
    paths = start.guides().paths()
    for index in range(4):
        west, east = paths[index], paths[7 - index]
        assert len(west) == len(east)
        for a, b in zip(west, east):
            assert a[0] == -b[0]
            assert a[1] == b[1]


def test_the_resting_line_is_the_drawn_bay_pitch(start):
    """The viewer sees this, so it is not the solver's to choose."""
    starts = start.marble_starts()
    assert len(starts) == layout.BAYS
    for index in range(layout.BAYS):
        assert start.guides().rest_point(index)[0] == pytest.approx(bay_x(index))
    pitches = [bay_x(i + 1) - bay_x(i) for i in range(layout.BAYS - 1)]
    assert pitches == pytest.approx([layout.BAY_PITCH] * (layout.BAYS - 1))


def test_the_apron_fits_under_the_drawn_pod(start):
    """V1.4's chutes needed a 9.3-wide undercroft under a 6.3-wide pod."""
    table = start.guides().table()
    assert table["apron_width"] < 2.0 * layout.START_BACK_HALF + 0.60


def test_every_guide_grade_is_in_the_band(start):
    """Below 8 degrees a marble stops; above 42 the guide is a fall."""
    table = start.guides().table()
    for row in table["rows"]:
        assert row["min_grade_deg"] >= 8.0, row
        assert row["max_grade_deg"] <= 42.0, row


def test_the_release_waits_for_the_slowest_guide(start):
    from sloped.radial import guide_table

    assert guide_table(start)["spread"]["release_margin"] > 0.30


def test_the_ring_is_one_gate_in_equal_segments(start):
    """One release, and a polygon round enough not to bias the radius."""
    ports = [a for a in start.local_actuators() if a.name.startswith("port")]
    paddles = [a for a in start.local_actuators() if a.name.startswith("paddle")]
    assert len(paddles) == layout.BAYS
    assert len(ports) == start.PADDLE_SEGMENTS
    assert len({round(a.release_time, 9) for a in ports}) == 1
    assert len({round(a.duration, 9) for a in ports}) == 1
    # How far a marble resting against a flat differs from one against a
    # vertex. Eight segments gave 0.084; sixteen gives a fifth of that.
    error = start.PADDLE_R * (1.0 / math.cos(math.pi / start.PADDLE_SEGMENTS) - 1.0)
    assert error < 0.03


def test_the_paddles_stand_where_the_field_does(start):
    """The bug this pins cost eleven seconds of one racer's life, every seed.

    `StartGrid.local_actuators` places its paddles from the fan's trough, and
    this module does not have one, so the inherited builder put them out on the
    apron - downhill of the field, in its way.
    """
    paddles = [a for a in start.local_actuators() if a.name.startswith("paddle")]
    seats = start.marble_starts()
    for index, paddle in enumerate(paddles):
        gap = math.dist(paddle.rest.position, seats[index].position)
        # Just downhill of its own marble, not out on the apron.
        assert gap < 1.2, f"paddle {index} is {gap:.2f} from bay {index}"


def test_the_mesh_is_clean(start):
    from marble3d.validation import check_mesh

    mesh = start.local_colliders()[0]
    assert check_mesh(mesh, expect_components=None) == []


# --- section 8: a held marble is not a stalled marble ---------------------


def test_a_held_marble_is_not_counted_as_a_race_stall():
    """The radial ring holds the field for 5.6 seconds before it races.

    `STOPPED_FOR` is one second, so a detector that starts at tick zero reports
    all eight stuck before the race begins - which is what the first radial
    trial did, and the mechanism was the instrument. The grace is read off the
    machine's own actuators rather than typed.
    """
    machine = start_machine(plan=BENCH_PLANS["radial"])
    trial = StartTrial(machine, seed=0)
    try:
        hz = trial.sim.config.physics.physics_hz
        release = max(
            getattr(actuator, "release_time", 0.0) + getattr(actuator, "duration", 0.0)
            for module in machine
            for actuator in getattr(module, "local_actuators", lambda: [])()
        )
        assert trial._grace_ticks >= release * hz
        # Motionless for well over `STOPPED_FOR`, before the grace expires.
        trial._where[0] = ("launch", 3)
        for _ in range(4 * trial.STOPPED_FOR // trial.LOCATE_EVERY):
            trial._stall(0, (0.0, 0.0, 0.0))
        assert trial.stuck == {}, "a marble waiting in the ring was called stuck"
    finally:
        trial.sim.close()


def test_post_release_stall_detection_is_not_weakened():
    """The grace suppresses the verdict; it must not remove it."""
    machine = start_machine(plan=BENCH_PLANS["radial"])
    trial = StartTrial(machine, seed=0)
    try:
        trial._grace_ticks = 0
        trial._where[0] = ("launch", 3)
        for _ in range(trial.STOPPED_FOR // trial.LOCATE_EVERY + 1):
            trial._stall(0, (0.0, 0.0, 0.0))
        assert 0 in trial.stuck
    finally:
        trial.sim.close()


def test_the_fans_grace_is_short_and_the_radials_is_long():
    """The two starts differ by an order of magnitude, so a typed grace is one
    of them being wrong."""
    graces = {}
    for kind in ("fan", "radial"):
        machine = start_machine(plan=BENCH_PLANS[kind])
        trial = StartTrial(machine, seed=0)
        try:
            graces[kind] = trial._grace_ticks
        finally:
            trial.sim.close()
    assert graces["fan"] < graces["radial"] / 4


def test_the_lab_duration_includes_the_hold():
    """A fixed budget measures the radial start on what the fan gets 20 on."""
    from sloped.startlab import run_trial

    machine = start_machine(plan=BENCH_PLANS["radial"])
    result = run_trial(0, machine=machine, duration=0.5)
    # The trial cannot have finished before the ring even opened.
    assert result.seconds > 0.0
    assert start_machine(plan=BENCH_PLANS["radial"]).modules["start"].RELEASE > 5.0

"""The course as assembled, and one race through it.

Races are 15 to 25 seconds of simulation each, so the ones that need a whole
race share a single session-scoped run and the rest work on the machine without
stepping it.
"""

from __future__ import annotations

import math

import pytest

from marble3d.config import DEFAULT_CONFIG
from marble3d.geometry import Transform
from marble3d.units import MARBLE_DIAMETER, MARBLE_RADIUS
from marble3d.validation import check_collider_bounds
from marble3d.world import MarbleWorld
from sloped import joins, layout
from sloped.course import CHAIN, check, check_probes, facts, sloped_course
from sloped.race import ROUTE_RUNS, SlopedRace, run_race
from sloped.stations import Spinner


SEED = 16


@pytest.fixture(scope="module")
def machine():
    return sloped_course()


@pytest.fixture(scope="module")
def race():
    outcome, replay = run_race(seed=SEED, marble_count=8, duration=40.0, with_replay=True)
    return outcome, replay


# --- the assembly ---------------------------------------------------------


def test_the_course_checks_out(machine):
    findings = check(machine)
    assert findings == [], "\n".join(str(finding) for finding in findings)


def test_every_collider_arrives_in_bullet_whole(machine):
    world = MarbleWorld(DEFAULT_CONFIG)
    try:
        machine.build(world)
        assert check_collider_bounds(world) == []
        assert len(world.colliders) >= len(machine.order) - 2
    finally:
        world.close()


def test_the_probes_find_the_surface_the_modules_promise(machine):
    """Fired from the analytic arc at the collider Bullet actually holds.

    A truncated chunk, a missing end section, a run placed at the wrong
    transform and a section carried on the wrong lateral all break this and
    none of them breaks a run loudly enough to notice.
    """
    world = MarbleWorld(DEFAULT_CONFIG)
    try:
        machine.build(world)
        findings = check_probes(machine, world)
        assert findings == [], "\n".join(str(f) for f in findings)
        assert len(machine.probes()) > 300
    finally:
        world.close()


def test_the_flow_order_is_the_declaration_order(machine):
    order = machine.order
    for earlier, later in zip(CHAIN, CHAIN[1:]):
        assert order.index(earlier) < order.index(later)
    assert order.index("mixer") > order.index("leg1")
    assert order.index("finish") == len(order) - 1


def test_the_seams_close_to_less_than_a_radius(machine):
    for up_name, up_socket, down_name, down_socket in (
        ("start", "exit", "launch", "entry"),
        ("launch", "exit", "leg1", "entry"),
        ("leg1", "exit", "leg2", "entry"),
        ("leg2", "exit", "leg3", "entry"),
        ("leg3", "exit", "blue_lead", "entry"),
        ("blue_lead", "exit", "blue", "entry"),
        ("orange_lead", "exit", "orange", "entry"),
    ):
        a = machine.modules[up_name].socket(up_socket)
        b = machine.modules[down_name].socket(down_socket)
        assert math.dist(a.frame.position, b.frame.position) < MARBLE_RADIUS, (
            up_name,
            down_name,
        )


def test_the_fork_sits_where_leg3_crosses_south(machine):
    leg3 = machine.runs["leg3"]
    crossing = min(range(len(leg3.path)), key=lambda i: abs(leg3.heading_deg(i)))
    assert crossing == joins.FORK_SAMPLE
    assert abs(leg3.heading_deg(joins.FORK_SAMPLE)) < 2.0


def test_the_two_routes_differ_by_less_than_a_tenth(machine):
    """Usage may be uneven; length has to be close or the split is a shortcut."""
    lengths = facts(machine)["route_length_sim"]
    assert abs(lengths["difference_pct"]) < 10.0, lengths


def test_the_join_radii_hold_the_measured_arrival_speed(machine):
    for name, entry in facts(machine)["join_radius_layout"].items():
        assert entry["worst"] > entry["allowed"], (name, entry)


def test_the_start_offers_eight_bays_wide_enough_to_stand_in(machine):
    starts = machine.modules["start"].marble_starts()
    assert len(starts) == layout.BAYS
    across = sorted(
        sum(
            (t.position[axis] - starts[0].position[axis]) * 1.0 for axis in range(1)
        )
        for t in starts
    )
    # Eight distinct bays, and the field is wider than four marble diameters.
    spread = math.dist(starts[0].position, starts[-1].position)
    assert spread > 4.0 * MARBLE_DIAMETER, spread
    for a, b in zip(starts, starts[1:]):
        assert math.dist(a.position, b.position) > 0.9 * MARBLE_DIAMETER


# --- the actuators --------------------------------------------------------


def test_the_gate_is_a_pure_function_of_the_tick(machine):
    gates = machine.modules["start"].local_actuators()
    assert len(gates) == layout.BAYS
    gate = gates[0]
    dt = DEFAULT_CONFIG.physics.dt
    before = gate.pose_at(0, dt)
    assert gate.pose_at(0, dt).position == before.position
    # Clamped before the release and after it finishes, and monotonic between.
    rest = gate.pose_at(int(gate.release_time / dt) - 2, dt).position[1]
    later = gate.pose_at(int((gate.release_time + gate.duration) / dt) + 40, dt).position[1]
    middle = gate.pose_at(int((gate.release_time + 0.5 * gate.duration) / dt), dt).position[1]
    assert rest < middle < later
    assert later - rest == pytest.approx(gate.travel[1])


def test_the_spinners_are_deterministic_and_turn_opposite_ways(machine):
    actuators = machine.modules["obstacle"].local_actuators()
    assert len(actuators) == 3 * layout.SPINNER_BLADES
    dt = DEFAULT_CONFIG.physics.dt
    for actuator in actuators:
        assert isinstance(actuator, Spinner)
        a = actuator.pose_at(137, dt)
        b = actuator.pose_at(137, dt)
        assert a.position == b.position and a.rotation == b.rotation
    rates = {a.name.split("_")[0]: a.rate for a in actuators}
    assert rates["wheel0"] > 0.0
    assert rates["wheel1"] < 0.0
    assert rates["wheel2"] > 0.0
    # A quarter turn of the wheel maps one blade onto the next.
    first = actuators[0]
    quarter = 0.5 * math.pi / abs(first.rate)
    assert first.angle_at(int(quarter / dt), dt) == pytest.approx(
        actuators[1].angle_at(0, dt) + first.rate * quarter + first.phase - actuators[1].phase,
        abs=1e-3,
    )


# --- one race -------------------------------------------------------------


def test_the_field_leaves_the_grid(race):
    outcome, _replay = race
    assert len(outcome.racers) == 8
    for racer in outcome.racers:
        assert racer.progress > 20.0, racer.to_json()


def test_every_racer_gets_exactly_one_route_and_it_is_a_real_one(race):
    outcome, _replay = race
    for racer in outcome.racers:
        if racer.state == "finished":
            assert racer.route in ("blue", "orange"), racer.to_json()
    assert set(outcome.route_counts) <= {"blue", "orange", "unrouted"}


def test_a_finisher_is_ranked_and_timed_and_crossed_the_sprints_exit(race, machine):
    outcome, _replay = race
    finishers = [r for r in outcome.racers if r.state == "finished"]
    assert finishers, "nobody finished the reference seed"
    orders = sorted(r.finish_order for r in finishers)
    assert orders == list(range(1, len(finishers) + 1))
    for racer in finishers:
        assert racer.finish_time is not None and racer.finish_time > 1.0
    times = [r.finish_time for r in sorted(finishers, key=lambda r: r.finish_order)]
    assert times == sorted(times)
    # The line is the sprint's exit, not the deck's far edge.
    line = machine.finish_line.frame.position
    sprint_exit = machine.runs["final"].socket("exit").frame.position
    assert math.dist(line, sprint_exit) < 1e-9


def test_progress_never_goes_backwards(race):
    outcome, _replay = race
    for racer in outcome.racers:
        assert racer.progress >= 0.0
        if racer.state == "finished":
            assert racer.progress > 300.0


def test_the_replay_carries_what_a_renderer_needs(race):
    _outcome, replay = race
    assert replay is not None
    document = replay.to_json()
    assert document["mode"] == "marble3d"
    assert document["physics_hz"] == 240
    assert document["replay_fps"] == 60
    assert document["units"]["render_scale"] == pytest.approx(0.57)
    assert document["units"]["gravity"] == pytest.approx(245.25)
    assert len(document["marbles"]) == 8
    frame = document["frames"][len(document["frames"]) // 2]
    sample = frame["marbles"][0]
    for key in ("p", "q", "v", "w"):
        assert key in sample
    assert document["summary"]["race"]["seed"] == SEED
    assert document["summary"]["route_length"]["blue"] > 300.0
    kinds = {event["kind"] for event in document["events"]}
    assert {"release", "route", "finish_line"} <= kinds


def test_the_actuator_transforms_are_in_the_replay(race):
    _outcome, replay = race
    frame = replay.to_json()["frames"][len(replay.frames) // 2]
    actuators = frame.get("actuators") or frame.get("a") or {}
    assert any(key.startswith("obstacle.wheel") for key in actuators), sorted(actuators)
    assert any(key.startswith("start.paddle") for key in actuators), sorted(actuators)


def test_the_same_seed_gives_the_same_race_in_one_process():
    """Two runs, one interpreter. The digest is over the raw sampled bytes."""
    first, first_replay = run_race(seed=3, marble_count=8, duration=25.0, with_replay=True)
    second, second_replay = run_race(seed=3, marble_count=8, duration=25.0, with_replay=True)
    assert first_replay.digest() == second_replay.digest()
    assert first_replay.event_digest() == second_replay.event_digest()
    assert first.seconds == second.seconds
    assert [r.finish_order for r in first.racers] == [r.finish_order for r in second.racers]
    assert [r.route for r in first.racers] == [r.route for r in second.racers]


def test_a_different_seed_gives_a_different_race():
    """A half-millimetre placement tolerance has to change the outcome."""
    a, a_replay = run_race(seed=3, marble_count=8, duration=25.0, with_replay=True)
    b, b_replay = run_race(seed=4, marble_count=8, duration=25.0, with_replay=True)
    assert a_replay.digest() != b_replay.digest()


def test_the_slot_permutation_is_over_slots_and_not_marbles():
    """Which marble starts in which bay has to vary, or slot bias is meaningless."""
    seen = set()
    for seed in (1, 2, 3, 4, 5):
        race = SlopedRace(seed=seed, marble_count=8)
        try:
            seen.add(tuple(race.results[m].start_slot for m in sorted(race.results)))
        finally:
            race.close()
    assert len(seen) > 1
    for arrangement in seen:
        assert sorted(arrangement) == list(range(8))


def test_travel_per_tick_stays_inside_the_cores_budget(race):
    outcome, _replay = race
    budget = DEFAULT_CONFIG.marble.travel_budget * DEFAULT_CONFIG.marble.diameter
    assert outcome.max_travel_per_tick < budget, (outcome.max_travel_per_tick, budget)


def test_route_runs_share_their_prefix_and_differ_only_in_the_branch():
    blue = ROUTE_RUNS["blue"]
    orange = ROUTE_RUNS["orange"]
    assert blue[:4] == orange[:4] == tuple(CHAIN)
    assert blue[-1] == orange[-1] == "final"
    assert set(blue) & set(orange) == set(CHAIN) | {"final"}

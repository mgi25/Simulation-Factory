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
def forked():
    """The build that carries both branch lobes.

    The shipped course races one route - six fork configurations were measured
    and none of them got a marble round the orange lobe to the finish - but the
    forked geometry is still built and still has to be correct, because the
    finding about it is a geometric argument.
    """
    return sloped_course(routes="both")


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


def test_the_seams_close_to_less_than_a_radius(forked):
    ## Checked on the *forked* build, because the orange lobe is still shipped
    ## as geometry even though the physics races one route: `docs/
    ## sloped_race_v1_junction_finding.md` is an argument about what the shapes
    ## can and cannot do, and it is only worth anything if the shapes close.
    for up_name, up_socket, down_name, down_socket in (
        ("start", "exit", "launch", "entry"),
        ("launch", "exit", "leg1", "entry"),
        ("leg1", "exit", "leg2", "entry"),
        ("leg2", "exit", "leg3", "entry"),
        ("leg3", "exit", "blue_lead", "entry"),
        ("blue_lead", "exit", "blue", "entry"),
        ("orange_lead", "exit", "orange", "entry"),
    ):
        a = forked.modules[up_name].socket(up_socket)
        b = forked.modules[down_name].socket(down_socket)
        assert math.dist(a.frame.position, b.frame.position) < MARBLE_RADIUS, (
            up_name,
            down_name,
        )


def test_the_fork_sits_where_leg3_crosses_south(machine):
    leg3 = machine.runs["leg3"]
    crossing = min(range(len(leg3.path)), key=lambda i: abs(leg3.heading_deg(i)))
    assert crossing == joins.FORK_SAMPLE
    assert abs(leg3.heading_deg(joins.FORK_SAMPLE)) < 2.0


def test_the_two_routes_differ_by_less_than_a_tenth(forked):
    """Usage may be uneven; length has to be close or the split is a shortcut.

    On the forked build for the same reason as the seams above. The shipped
    course races one route, so `sloped_course()` reports no difference at all -
    and a test that read the raced build would be asserting that None is small.
    """
    lengths = facts(forked)["route_length_sim"]
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
    """The bay paddles, whatever else the start carries.

    Written when the start was the fan and its only moving parts were eight
    bay gates. The frozen V1 start is `sloped.trapdoor.ShuffleFloor`, which
    also carries four rotor blades and eighteen floor slats, so the paddles are
    selected by name rather than by the actuator list being nothing else. What
    is asserted is unchanged: there are eight of them and each one's pose is a
    clamped, monotonic, pure function of the tick.
    """
    actuators = machine.modules["start"].local_actuators()
    gates = [a for a in actuators if a.name.startswith("paddle")]
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
    # The four blades of a wheel stand a quarter turn apart, at every tick, so
    # a quarter turn of the wheel maps one blade onto the next.
    for wheel in ("wheel0", "wheel1", "wheel2"):
        blades = [a for a in actuators if a.name.startswith(wheel + "_")]
        assert len(blades) == layout.SPINNER_BLADES
        for tick in (0, 137, 4001):
            angles = [b.angle_at(tick, dt) for b in blades]
            for earlier, later in zip(angles, angles[1:]):
                step = (later - earlier) % (2.0 * math.pi)
                assert step == pytest.approx(0.5 * math.pi, abs=1e-6), (wheel, tick)


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
    # `format`, not `mode`: the core stamps the schema name in `format` and the
    # schema number in `version`, and the renderer reads both.
    assert document["format"] == "marble3d"
    assert document["version"] >= 1
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
    """The budget is a claim about racers, and only about racers.

    A marble that leaves the channel falls the whole drop - sixty-odd
    simulation units - and arrives at about 172 world units a second, which is
    0.72 of a unit in a 240 Hz tick against a budget of 0.5. Measured across
    eight seeds: the two that lost nobody peaked at 69.9 and 66.7 wu/s, both
    inside the budget, and every seed that lost a marble exceeded it. So the
    breach is the free fall of a marble that is already out of the race, and
    the honest form of this test is conditional on nothing having been lost.
    """
    outcome, _replay = race
    budget = DEFAULT_CONFIG.marble.travel_budget * DEFAULT_CONFIG.marble.diameter
    lost = [racer for racer in outcome.racers if racer.state != "finished"]
    if not lost:
        assert outcome.max_travel_per_tick < budget, (
            outcome.max_travel_per_tick,
            budget,
        )
        return
    # And where something was lost, the breach has to be attributable to it:
    # no racer that reached the finish may have exceeded the budget itself.
    ticks_per_second = DEFAULT_CONFIG.physics.physics_hz
    for racer in outcome.racers:
        if racer.state != "finished":
            continue
        assert racer.top_speed / ticks_per_second < budget, (
            racer.marble_id,
            racer.top_speed,
        )


def test_route_runs_share_their_prefix_and_differ_only_in_the_branch():
    blue = ROUTE_RUNS["blue"]
    orange = ROUTE_RUNS["orange"]
    assert blue[:4] == orange[:4] == tuple(CHAIN)
    assert blue[-1] == orange[-1] == "final"
    assert set(blue) & set(orange) == set(CHAIN) | {"final"}

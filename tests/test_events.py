"""Phase 4A2A tests: the battle event stream and the replay v4 contract.

Events exist so a renderer can show that something happened without guessing
it back out of health numbers. They must therefore be complete, ordered,
deterministic - and completely invisible to the rules.
"""

from __future__ import annotations

import math

import pytest

from engine.simulation import Simulation
from entities.ball import Ball
from entities.echo_clone import EchoClone
from entities.orbit_orb import OrbitOrb
from entities.projectile import Projectile
from modes.events import (
    EVENT_ELIMINATION,
    EVENT_HIT,
    EVENT_POWER_ACTIVATE,
    HIT_IMPACT,
    BattleEvent,
)
from modes.power_battle import (
    DAMAGE_MIN_CLOSING_SPEED,
    POWER_WARMUP_TICKS,
    PowerBattleMode,
)
from powers import (
    POWER_NAMES,
    EchoPower,
    OrbitPower,
    Power,
    PulsePower,
    TitanPower,
    power_class,
)
from powers.power import seconds_to_ticks
from replay.exporter import DECIMALS, REPLAY_VERSION, record_battle

SEED = 12345
EVENT_KEYS = {
    "tick",
    "type",
    "x",
    "y",
    "source_id",
    "target_id",
    "subtype",
    "magnitude",
}


def inert_power() -> Power:
    """A power whose cooldown never becomes ready inside a battle."""
    return Power(initial_delay_ticks=10**9)


def held_titan() -> TitanPower:
    """A Titan that only ever activates when a test says so."""
    return TitanPower(initial_delay_ticks=10**9)


def warm_up(mode: PowerBattleMode) -> None:
    """Step to the tick before powers are first allowed to fire."""
    while mode.sim.ticks < POWER_WARMUP_TICKS - 1:
        mode.step()


def parked_duel(*specs, seed: int = SEED, gap: float = 600.0):
    """Two motionless fighters a known distance apart on one horizontal line."""
    sim = Simulation(seed)
    mode = PowerBattleMode(sim, powers=specs)
    left, right = sim.balls
    mid_y = (sim.arena.top + sim.arena.bottom) / 2
    start_x = sim.arena.left + 180.0
    left.body.position = (start_x, mid_y)
    left.body.velocity = (0.0, 0.0)
    right.body.position = (start_x + gap, mid_y)
    right.body.velocity = (0.0, 0.0)
    return sim, mode, left, right


def run(mode: PowerBattleMode, ticks: int) -> None:
    for _ in range(ticks):
        if not mode.step():
            return


def run_until_hurt(mode: PowerBattleMode, victim: Ball, limit: int = 900) -> None:
    for _ in range(limit):
        if victim.damage_taken > 0.0 or not mode.step():
            return


def of_type(mode: PowerBattleMode, event_type: str) -> list[BattleEvent]:
    return [event for event in mode.events if event.type == event_type]


def full_battle(seed: int, powers=None) -> PowerBattleMode:
    sim = Simulation(seed)
    mode = PowerBattleMode(sim, powers=powers)
    while mode.step():
        pass
    return mode


# --- power activation ---


@pytest.mark.parametrize("name", POWER_NAMES)
def test_an_activation_emits_exactly_one_event(name: str) -> None:
    sim, mode, owner, _ = parked_duel(power_class(name)(), inert_power())
    warm_up(mode)
    mode.step()

    events = of_type(mode, EVENT_POWER_ACTIVATE)
    assert len(events) == 1
    event = events[0]
    assert event.subtype == name
    assert event.source_id == owner.ball_id
    assert event.target_id is None
    assert event.magnitude is None


def test_the_activation_event_tick_matches_the_power() -> None:
    sim, mode, owner, _ = parked_duel(EchoPower(initial_delay_ticks=40), inert_power())
    while mode.powers[0].activations == 0 and mode.step():
        pass

    event = of_type(mode, EVENT_POWER_ACTIVATE)[0]
    assert event.tick == mode.powers[0].last_activation_tick
    assert event.tick == POWER_WARMUP_TICKS + 39


def test_the_activation_event_is_placed_on_its_owner() -> None:
    sim, mode, owner, _ = parked_duel(PulsePower(), inert_power())
    warm_up(mode)
    mode.step()

    event = of_type(mode, EVENT_POWER_ACTIVATE)[0]
    assert (event.x, event.y) == pytest.approx(tuple(owner.position))


def test_every_activation_of_a_whole_battle_is_reported() -> None:
    mode = full_battle(SEED, powers=["rush", "orbit"])
    reported = of_type(mode, EVENT_POWER_ACTIVATE)
    assert len(reported) == sum(power.activations for power in mode.powers)
    assert len(reported) >= 4

    for index, power in enumerate(mode.powers):
        mine = [event for event in reported if event.source_id == index]
        assert len(mine) == power.activations
        assert all(event.subtype == power.name for event in mine)


def test_nothing_is_reported_during_the_warmup() -> None:
    sim, mode, _, _ = parked_duel(EchoPower(), EchoPower())
    for _ in range(POWER_WARMUP_TICKS - 1):
        mode.step()
    assert mode.events == []


# --- hits: fighter collisions ---


def test_a_damaging_collision_emits_one_hit() -> None:
    sim, mode, rammer, victim = parked_duel(inert_power(), inert_power())
    rammer.body.velocity = (1400.0, 0.0)
    run_until_hurt(mode, victim)

    hits = of_type(mode, EVENT_HIT)
    assert len(hits) == 1
    hit = hits[0]
    assert hit.subtype == HIT_IMPACT
    assert hit.source_id == rammer.ball_id
    assert hit.target_id == victim.ball_id
    assert hit.tick == sim.ticks


def test_the_hit_magnitude_is_the_health_actually_removed() -> None:
    sim, mode, rammer, victim = parked_duel(inert_power(), inert_power())
    rammer.body.velocity = (1400.0, 0.0)
    run_until_hurt(mode, victim)

    hit = of_type(mode, EVENT_HIT)[0]
    assert hit.magnitude == pytest.approx(victim.damage_taken)
    assert hit.magnitude == pytest.approx(victim.max_health - victim.health)
    assert hit.magnitude > 0.0


def test_the_impact_hit_sits_between_the_two_fighters() -> None:
    sim, mode, rammer, victim = parked_duel(inert_power(), inert_power())
    rammer.body.velocity = (1400.0, 0.0)
    run_until_hurt(mode, victim)

    hit = of_type(mode, EVENT_HIT)[0]
    midpoint = (rammer.position + victim.position) * 0.5
    assert (hit.x, hit.y) == pytest.approx(tuple(midpoint), abs=1e-6)


def test_a_harmless_collision_emits_no_hit() -> None:
    """Below the damage threshold a touch is not a moment worth drawing."""
    sim, mode, rammer, victim = parked_duel(inert_power(), inert_power(), gap=300.0)
    crawl = DAMAGE_MIN_CLOSING_SPEED * 0.5
    rammer.body.velocity = (crawl, 0.0)

    collided = False
    for _ in range(900):
        if not mode.step():
            break
        collided = collided or bool(sim.impacts)

    assert collided, "the fighters never touched"
    assert victim.damage_taken == 0.0
    assert of_type(mode, EVENT_HIT) == []


def test_wall_bounces_emit_nothing() -> None:
    sim, mode, a, b = parked_duel(inert_power(), inert_power())
    a.body.velocity = (0.0, 1300.0)
    b.body.velocity = (0.0, -1300.0)
    run(mode, 600)

    assert all(ball.health == ball.max_health for ball in sim.balls)
    assert mode.events == []


# --- hits: dynamic entities ---


def _launch_projectile(sim, attacker, target) -> None:
    sim.spawn(
        Projectile,
        owner_id=attacker.ball_id,
        position=tuple(attacker.position + (200.0, 0.0)),
        velocity=(PulsePower.PROJECTILE_SPEED, 0.0),
        radius=PulsePower.PROJECTILE_RADIUS,
        color=attacker.color,
        damage=PulsePower.PROJECTILE_DAMAGE,
        lifetime_ticks=seconds_to_ticks(PulsePower.PROJECTILE_LIFETIME_SECONDS),
    )


def _launch_clone(sim, attacker, target) -> None:
    sim.spawn(
        EchoClone,
        owner_id=attacker.ball_id,
        position=tuple(attacker.position + (200.0, 0.0)),
        velocity=(EchoPower.CLONE_SPEED, 0.0),
        radius=attacker.base_radius * EchoPower.CLONE_RADIUS_FRACTION,
        color=attacker.color,
        damage=EchoPower.CLONE_DAMAGE,
        lifetime_ticks=seconds_to_ticks(EchoPower.CLONE_LIFETIME_SECONDS),
        mass=EchoPower.CLONE_MASS,
    )


def _launch_orb(sim, attacker, target) -> None:
    sim.spawn(
        OrbitOrb,
        owner_id=attacker.ball_id,
        position=tuple(attacker.position),
        radius=OrbitPower.ORB_RADIUS,
        color=attacker.color,
        damage=OrbitPower.ORB_DAMAGE,
        orbit_radius=(target.position - attacker.position).length,
        angle=0.0,
        angular_step=0.0,
    )


ENTITY_CASES = [
    (_launch_projectile, "projectile", PulsePower.PROJECTILE_DAMAGE),
    (_launch_clone, "echo", EchoPower.CLONE_DAMAGE),
    (_launch_orb, "orbit", OrbitPower.ORB_DAMAGE),
]


@pytest.mark.parametrize(
    "launch, subtype, damage", ENTITY_CASES, ids=["pulse", "echo", "orbit"]
)
def test_an_entity_hit_is_named_by_the_entity(launch, subtype, damage) -> None:
    sim, mode, attacker, target = parked_duel(inert_power(), inert_power())
    launch(sim, attacker, target)
    run_until_hurt(mode, target)

    hits = of_type(mode, EVENT_HIT)
    assert len(hits) == 1
    hit = hits[0]
    assert hit.subtype == subtype
    assert hit.source_id == attacker.ball_id
    assert hit.target_id == target.ball_id
    assert hit.magnitude == pytest.approx(damage)


@pytest.mark.parametrize(
    "launch, subtype, damage", ENTITY_CASES, ids=["pulse", "echo", "orbit"]
)
def test_titan_mitigation_is_visible_in_the_hit_magnitude(
    launch, subtype, damage
) -> None:
    sim, mode, attacker, target = parked_duel(inert_power(), held_titan())
    assert mode.powers[1].activate() is True
    launch(sim, attacker, target)
    run_until_hurt(mode, target)

    hit = of_type(mode, EVENT_HIT)[0]
    assert hit.magnitude == pytest.approx(
        damage * TitanPower.INCOMING_DAMAGE_MULTIPLIER
    )
    assert hit.magnitude == pytest.approx(target.damage_taken)
    assert hit.magnitude < damage


def test_an_entity_hit_is_placed_where_the_entity_was() -> None:
    sim, mode, attacker, target = parked_duel(inert_power(), inert_power())
    _launch_projectile(sim, attacker, target)
    projectile = sim.dynamic_entities[0]

    # Contacts are resolved after the physics step, so the contact position
    # is where the projectile ended up on the tick it landed.
    contact: tuple[float, float] | None = None
    for _ in range(900):
        stepped = mode.step()
        if target.damage_taken > 0.0:
            contact = tuple(projectile.position)
            break
        if not stepped:
            break

    assert contact is not None, "the projectile never landed"
    hit = of_type(mode, EVENT_HIT)[0]
    assert (hit.x, hit.y) == pytest.approx(contact, abs=1e-6)


def test_an_entity_that_hits_nothing_emits_nothing() -> None:
    sim, mode, attacker, target = parked_duel(inert_power(), inert_power())
    _launch_projectile(sim, attacker, target)
    for ball in sim.balls:
        ball.body.position = (sim.arena.right - 140.0, sim.arena.top + 140.0)
    run(mode, 400)

    assert sim.dynamic_entities == []
    assert mode.events == []


# --- elimination ---


def test_a_lethal_hit_emits_the_hit_then_the_elimination() -> None:
    sim, mode, attacker, target = parked_duel(inert_power(), inert_power())
    target.health = PulsePower.PROJECTILE_DAMAGE * 0.5
    _launch_projectile(sim, attacker, target)
    while mode.step():
        pass

    assert [event.type for event in mode.events] == [EVENT_HIT, EVENT_ELIMINATION]
    hit, elimination = mode.events
    assert hit.tick == elimination.tick
    assert elimination.target_id == target.ball_id
    assert elimination.source_id == attacker.ball_id
    assert elimination.subtype == "projectile"
    assert elimination.magnitude is None
    assert (elimination.x, elimination.y) == pytest.approx(tuple(target.position))
    assert target.alive is False


def test_an_elimination_is_emitted_exactly_once() -> None:
    for seed in range(12):
        mode = full_battle(seed)
        eliminations = of_type(mode, EVENT_ELIMINATION)
        dead = [ball for ball in mode.sim.balls if not ball.alive]
        assert len(eliminations) == len(dead)
        assert {event.target_id for event in eliminations} == {
            ball.ball_id for ball in dead
        }


def test_a_timeout_emits_no_elimination() -> None:
    mode = full_battle(42, powers=["echo", "rush"])
    assert mode.finished_tick == 4200
    assert all(ball.alive for ball in mode.sim.balls)
    assert of_type(mode, EVENT_ELIMINATION) == []


def test_health_set_to_zero_by_hand_is_not_an_elimination() -> None:
    """Only a damaging hit is a moment; the setter is bookkeeping."""
    sim, mode, _, victim = parked_duel(inert_power(), inert_power())
    victim.health = 0.0
    assert mode.step() is False
    assert mode.finished
    assert mode.events == []


# --- ordering and determinism ---


def test_events_are_in_non_decreasing_tick_order() -> None:
    for seed in range(10):
        ticks = [event.tick for event in full_battle(seed).events]
        assert ticks == sorted(ticks)


def test_an_elimination_never_precedes_its_own_hit() -> None:
    for seed in range(12):
        events = full_battle(seed).events
        for index, event in enumerate(events):
            if event.type != EVENT_ELIMINATION:
                continue
            previous = events[index - 1]
            assert index > 0
            assert previous.type == EVENT_HIT
            assert previous.target_id == event.target_id
            assert previous.tick == event.tick


def test_the_same_seed_produces_the_same_event_stream() -> None:
    for seed in (SEED, 777, 3):
        assert full_battle(seed).events == full_battle(seed).events


def test_pinned_powers_produce_the_same_event_stream() -> None:
    first = full_battle(808, powers=["titan", "pulse"]).events
    second = full_battle(808, powers=["titan", "pulse"]).events
    assert first == second
    assert first, "the battle produced no events at all"


def test_recording_events_does_not_touch_the_battle() -> None:
    """Nothing in the rules reads the list back, so emptying it changes nothing."""
    def outcome(clear: bool):
        sim = Simulation(SEED)
        mode = PowerBattleMode(sim)
        while mode.step():
            if clear:
                mode.events.clear()
        return (
            mode.finished_tick,
            None if mode.winner is None else mode.winner.ball_id,
            tuple(round(ball.health, 9) for ball in sim.balls),
        )

    assert outcome(clear=True) == outcome(clear=False)


# --- replay v4 ---


@pytest.fixture(scope="module")
def replay() -> dict:
    return record_battle(SEED)


def test_the_replay_is_version_6(replay: dict) -> None:
    assert replay["version"] == REPLAY_VERSION == 6


def test_the_replay_carries_a_top_level_event_list(replay: dict) -> None:
    assert isinstance(replay["events"], list)
    assert replay["events"], "the battle produced no events"
    # Events live beside the frames, not inside them: the frame contract is
    # unchanged and event timing survives 60 Hz sampling.
    for frame in replay["frames"][:20]:
        assert set(frame) == {"tick", "fighters", "entities", "obstacles"}


def test_every_event_record_has_the_agreed_fields(replay: dict) -> None:
    ids = {meta["id"] for meta in replay["fighters"]}
    limit = replay["result"]["finished_tick"]

    for event in replay["events"]:
        assert set(event) == EVENT_KEYS
        assert event["type"] in {EVENT_POWER_ACTIVATE, EVENT_HIT, EVENT_ELIMINATION}
        assert isinstance(event["tick"], int)
        assert 0 <= event["tick"] <= limit
        assert math.isfinite(event["x"]) and math.isfinite(event["y"])
        assert event["source_id"] is None or event["source_id"] in ids
        assert event["target_id"] is None or event["target_id"] in ids
        assert event["subtype"] is None or isinstance(event["subtype"], str)
        if event["magnitude"] is not None:
            assert event["magnitude"] > 0.0
            assert round(event["magnitude"], DECIMALS) == event["magnitude"]


def test_replayed_events_stay_in_the_order_python_produced(replay: dict) -> None:
    ticks = [event["tick"] for event in replay["events"]]
    assert ticks == sorted(ticks)

    mode = full_battle(SEED)
    assert [event["type"] for event in replay["events"]] == [
        event.type for event in mode.events
    ]
    assert [event["tick"] for event in replay["events"]] == [
        event.tick for event in mode.events
    ]


def test_every_event_type_reaches_the_replay() -> None:
    seen = set()
    for seed in range(16):
        for event in record_battle(seed)["events"]:
            seen.add((event["type"], event["subtype"]))

    types = {event_type for event_type, _ in seen}
    assert types == {EVENT_POWER_ACTIVATE, EVENT_HIT, EVENT_ELIMINATION}
    subtypes = {subtype for event_type, subtype in seen if event_type == EVENT_HIT}
    assert subtypes == {HIT_IMPACT, "projectile", "echo", "orbit"}


def test_events_do_not_change_the_recorded_battle(replay: dict) -> None:
    mode = full_battle(SEED)
    result = replay["result"]
    assert result["finished_tick"] == mode.finished_tick
    assert result["is_draw"] is mode.is_draw
    assert result["winner_id"] == (
        None if mode.winner is None else mode.winner.ball_id
    )
    for fighter, ball in zip(replay["frames"][-1]["fighters"], mode.sim.balls):
        assert fighter["health"] == pytest.approx(ball.health, abs=1e-3)


def test_replays_with_events_stay_byte_deterministic() -> None:
    import json

    for seed, powers in ((SEED, None), (999, ["echo", "titan"]), (7, ["orbit", "rush"])):
        first = record_battle(seed, powers=powers)
        second = record_battle(seed, powers=powers)
        assert first == second
        assert json.dumps(first, separators=(",", ":")) == json.dumps(
            second, separators=(",", ":")
        )

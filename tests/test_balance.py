"""Phase 4A1 tests: generic incoming-damage mitigation and the power warmup.

Two mechanics, both deliberately kept out of the individual powers: damage
mitigation lives on `Ball.take_damage`, so every source is covered without
knowing what a Titan is, and the warmup lives on the battle mode, so no power
can opt out of it.
"""

from __future__ import annotations

import pathlib
import tokenize

import pytest

from engine.simulation import PHYSICS_HZ, Simulation
from entities.ball import Ball
from entities.echo_clone import EchoClone
from entities.orbit_orb import OrbitOrb
from entities.projectile import Projectile
from modes.power_battle import (
    POWER_WARMUP_SECONDS,
    POWER_WARMUP_TICKS,
    PowerBattleMode,
)
from powers import (
    INITIAL_OFFSET_MAX_TICKS,
    INITIAL_OFFSET_MIN_TICKS,
    POWER_NAMES,
    EchoPower,
    OrbitPower,
    Power,
    PulsePower,
    RushPower,
    TitanPower,
    create_power,
    power_class,
)
from powers.power import seconds_to_ticks

SEED = 12345
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

# What one activation of each power is expected to put on the board.
ENTITIES_PER_ACTIVATION = {
    "rush": 0,
    "titan": 0,
    "pulse": 1,
    "echo": EchoPower.CLONES_PER_ACTIVATION,
    "orbit": OrbitPower.ORB_COUNT,
}


def inert_power() -> Power:
    """A power whose cooldown never becomes ready inside a battle."""
    return Power(initial_delay_ticks=10**9)


def held_titan() -> TitanPower:
    """A Titan that only ever activates when a test says so."""
    return TitanPower(initial_delay_ticks=10**9)


def make_ball(**kwargs) -> Ball:
    defaults = dict(
        ball_id=0,
        name="RED",
        radius=50.0,
        color=(255, 0, 0),
        position=(0.0, 0.0),
        velocity=(0.0, 0.0),
    )
    return Ball(**{**defaults, **kwargs})


def powered_ball(power: Power) -> tuple[Ball, Power]:
    ball = make_ball()
    power.attach(ball)
    return ball, power


def titan_duel(seed: int = SEED):
    """Fighter 0 harmless, fighter 1 a Titan, both parked mid-arena.

    Six hundred pixels apart on one horizontal line, far from every wall, so
    growing the Titan never trips the arena clamp and nothing moves unless a
    test moves it.
    """
    sim = Simulation(seed)
    mode = PowerBattleMode(sim, powers=[inert_power(), held_titan()])
    attacker, titan = sim.balls
    mid_y = (sim.arena.top + sim.arena.bottom) / 2
    attacker.body.position = (sim.arena.left + 180.0, mid_y)
    attacker.body.velocity = (0.0, 0.0)
    titan.body.position = (sim.arena.left + 780.0, mid_y)
    titan.body.velocity = (0.0, 0.0)
    return sim, mode, attacker, titan


def run_until_hurt(mode: PowerBattleMode, victim: Ball, limit: int = 600) -> None:
    for _ in range(limit):
        if victim.damage_taken > 0.0 or not mode.step():
            return


def duel(*specs, seed: int = SEED):
    """Two parked fighters with pinned powers, ready to be stepped."""
    sim = Simulation(seed)
    mode = PowerBattleMode(sim, powers=specs)
    a, b = sim.balls
    mid_y = (sim.arena.top + sim.arena.bottom) / 2
    a.body.position = (sim.arena.left + 200.0, mid_y - 320.0)
    b.body.position = (sim.arena.right - 200.0, mid_y + 320.0)
    for ball in sim.balls:
        ball.body.velocity = (0.0, 0.0)
    return sim, mode, a, b


# --- incoming damage: the default ---


def test_the_base_power_lets_all_damage_through() -> None:
    assert Power.INCOMING_DAMAGE_MULTIPLIER == 1.0
    power = Power()
    assert power.incoming_damage_multiplier == 1.0
    power.activate()
    assert power.incoming_damage_multiplier == 1.0


@pytest.mark.parametrize("name", ["rush", "pulse", "echo", "orbit"])
def test_only_titan_mitigates_incoming_damage(name: str) -> None:
    cls = power_class(name)
    assert cls.INCOMING_DAMAGE_MULTIPLIER == 1.0

    ball, power = powered_ball(cls())
    power.activate()
    assert ball.incoming_damage_multiplier == 1.0
    assert ball.take_damage(20.0) == pytest.approx(20.0)


def test_a_ball_with_no_power_takes_full_damage() -> None:
    ball = make_ball()
    assert ball.power is None
    assert ball.incoming_damage_multiplier == 1.0
    assert ball.take_damage(30.0) == pytest.approx(30.0)


# --- incoming damage: Titan ---


def test_an_inactive_titan_takes_full_damage() -> None:
    ball, power = powered_ball(held_titan())
    assert power.active is False
    assert ball.incoming_damage_multiplier == 1.0
    assert ball.take_damage(40.0) == pytest.approx(40.0)
    assert ball.health == pytest.approx(ball.max_health - 40.0)


def test_an_active_titan_takes_less_damage() -> None:
    ball, power = powered_ball(held_titan())
    power.activate()
    assert ball.take_damage(40.0) < 40.0


def test_the_titan_reduction_is_exactly_the_declared_fraction() -> None:
    ball, power = powered_ball(held_titan())
    power.activate()

    share = TitanPower.INCOMING_DAMAGE_MULTIPLIER
    assert 0.0 < share < 1.0
    assert ball.incoming_damage_multiplier == share
    assert ball.take_damage(40.0) == pytest.approx(40.0 * share)
    assert ball.damage_taken == pytest.approx(40.0 * share)
    assert ball.health == pytest.approx(ball.max_health - 40.0 * share)


def test_titan_mitigation_stops_the_moment_the_power_expires() -> None:
    ball, power = powered_ball(held_titan())
    power.activate()
    power.deactivate()
    assert ball.incoming_damage_multiplier == 1.0
    assert ball.take_damage(40.0) == pytest.approx(40.0)


def test_assigning_health_directly_bypasses_mitigation() -> None:
    """The setter is how the mode and tests script an exact health value."""
    ball, power = powered_ball(held_titan())
    power.activate()

    ball.health = 50.0
    assert ball.health == 50.0
    assert ball.damage_taken == 0.0

    ball.health = 0.0
    assert ball.health == 0.0
    assert ball.alive is False


def test_mitigation_never_produces_negative_damage() -> None:
    class _Absurd(Power):
        INCOMING_DAMAGE_MULTIPLIER = -2.0

    ball, power = powered_ball(_Absurd())
    power.activate()

    assert power.incoming_damage_multiplier == 0.0
    assert ball.incoming_damage_multiplier == 0.0
    assert ball.take_damage(80.0) == 0.0
    assert ball.health == ball.max_health
    assert ball.damage_taken == 0.0


def test_mitigation_leaves_a_zero_or_negative_hit_alone() -> None:
    ball, power = powered_ball(held_titan())
    power.activate()
    assert ball.take_damage(0.0) == 0.0
    assert ball.take_damage(-25.0) == 0.0
    assert ball.health == ball.max_health


# --- incoming damage: every source, without any of them knowing ---


def test_titan_mitigation_applies_to_impact_damage() -> None:
    sim, mode, attacker, titan = titan_duel()
    mode.powers[1].activate()
    attacker.body.velocity = (1600.0, 0.0)

    closing = None
    for _ in range(600):
        if titan.damage_taken > 0.0 or not mode.step():
            break
        if sim.impacts:
            closing = sim.impacts[0].closing_speed

    assert closing is not None, "no impact was produced"
    assert titan.damage_taken == pytest.approx(
        PowerBattleMode.impact_damage(closing)
        * TitanPower.INCOMING_DAMAGE_MULTIPLIER
    )
    assert attacker.damage_dealt == pytest.approx(titan.damage_taken)


def _pulse_at_titan(sim, attacker, titan) -> None:
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


def _clone_at_titan(sim, attacker, titan) -> None:
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


def _orb_at_titan(sim, attacker, titan) -> None:
    # A stationary orbit whose radius is exactly the gap between the two
    # fighters, so the orb is placed straight onto the Titan.
    sim.spawn(
        OrbitOrb,
        owner_id=attacker.ball_id,
        position=tuple(attacker.position),
        radius=OrbitPower.ORB_RADIUS,
        color=attacker.color,
        damage=OrbitPower.ORB_DAMAGE,
        orbit_radius=(titan.position - attacker.position).length,
        angle=0.0,
        angular_step=0.0,
    )


@pytest.mark.parametrize(
    "launch, damage",
    [
        (_pulse_at_titan, PulsePower.PROJECTILE_DAMAGE),
        (_clone_at_titan, EchoPower.CLONE_DAMAGE),
        (_orb_at_titan, OrbitPower.ORB_DAMAGE),
    ],
    ids=["pulse", "echo", "orbit"],
)
def test_titan_mitigation_applies_to_every_entity_source(launch, damage) -> None:
    """None of these entities knows Titan exists; all of them are mitigated."""
    sim, mode, attacker, titan = titan_duel()
    launch(sim, attacker, titan)
    run_until_hurt(mode, titan)
    unmitigated = titan.damage_taken
    assert unmitigated == pytest.approx(damage)

    sim, mode, attacker, titan = titan_duel()
    assert mode.powers[1].activate() is True
    launch(sim, attacker, titan)
    run_until_hurt(mode, titan)

    assert titan.damage_taken == pytest.approx(
        damage * TitanPower.INCOMING_DAMAGE_MULTIPLIER
    )
    assert titan.damage_taken < unmitigated
    assert attacker.damage_dealt == pytest.approx(titan.damage_taken)


def _executable_code(path: pathlib.Path) -> str:
    """The file with comments and docstrings stripped out.

    Prose is free to name a power to explain itself; only running code is
    under test here.
    """
    kept: list[str] = []
    with tokenize.open(path) as handle:
        for token in tokenize.generate_tokens(handle.readline):
            if token.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            kept.append(token.string)
    return " ".join(kept)


DAMAGE_PATH = (
    "modes/power_battle.py",
    "entities/ball.py",
    "entities/dynamic_entity.py",
    "entities/projectile.py",
    "entities/echo_clone.py",
    "entities/orbit_orb.py",
)

PACKAGES = ("engine", "entities", "modes", "powers", "rendering", "replay")


def test_no_damage_source_branches_on_titan() -> None:
    """Mitigation is generic: nothing that deals damage knows Titan exists."""
    for relative in DAMAGE_PATH:
        code = _executable_code(REPO_ROOT / relative).lower()
        assert "titan" not in code, f"{relative} branches on titan"


def test_mitigation_is_read_in_exactly_one_place() -> None:
    """Declared as a constant by a power, read as a property in two places.

    `Power` turns the constant into the active-only view and `Ball` applies
    it; no damage source consults it, which is what makes it generic.
    """
    users = {
        f"{package}/{path.name}"
        for package in PACKAGES
        for path in (REPO_ROOT / package).glob("*.py")
        if "incoming_damage_multiplier" in _executable_code(path)
    }
    assert users == {"powers/power.py", "entities/ball.py"}


# --- the warmup ---


def test_warmup_is_expressed_in_simulation_ticks() -> None:
    assert POWER_WARMUP_SECONDS == 1.25
    assert POWER_WARMUP_TICKS == seconds_to_ticks(1.25) == 150
    assert POWER_WARMUP_TICKS == round(1.25 * PHYSICS_HZ)


@pytest.mark.parametrize("name", POWER_NAMES)
def test_no_power_activates_before_the_warmup_ends(name: str) -> None:
    cls = power_class(name)
    sim, mode, _, _ = duel(cls(), cls())

    for _ in range(POWER_WARMUP_TICKS - 1):
        assert mode.step() is True
        assert mode.warming_up is True
        for power in mode.powers:
            assert power.active is False
            assert power.activations == 0
        assert sim.dynamic_entities == []

    assert sim.ticks == POWER_WARMUP_TICKS - 1


@pytest.mark.parametrize("name", POWER_NAMES)
def test_every_power_activates_on_the_first_legal_tick(name: str) -> None:
    sim, mode, _, _ = duel(power_class(name)(), inert_power())
    for _ in range(POWER_WARMUP_TICKS - 1):
        mode.step()

    mode.step()
    power = mode.powers[0]
    assert sim.ticks == POWER_WARMUP_TICKS
    assert mode.warming_up is False
    assert power.active is True
    assert power.activations == 1
    assert power.last_activation_tick == POWER_WARMUP_TICKS
    assert len([e for e in sim.dynamic_entities if e.active]) == (
        ENTITIES_PER_ACTIVATION[name]
    )


def test_the_first_possible_activation_tick_is_exact() -> None:
    """A delay counts down from the warmup and fires when it reaches zero.

    Zero and one are therefore the same instruction - "the first legal tick" -
    which is why seeded offsets are drawn from one upwards.
    """
    for delay, expected in (
        (0, POWER_WARMUP_TICKS),
        (1, POWER_WARMUP_TICKS),
        (2, POWER_WARMUP_TICKS + 1),
        (90, POWER_WARMUP_TICKS + 89),
    ):
        sim, mode, _, _ = duel(RushPower(initial_delay_ticks=delay), inert_power())
        while mode.powers[0].last_activation_tick is None and mode.step():
            pass
        assert mode.powers[0].last_activation_tick == expected


def test_seeded_offsets_are_one_based_so_every_draw_is_a_distinct_tick() -> None:
    import random

    rng = random.Random(SEED)
    drawn = {create_power("rush", rng).cooldown_remaining_ticks for _ in range(4000)}
    assert min(drawn) == INITIAL_OFFSET_MIN_TICKS == 1
    assert max(drawn) == INITIAL_OFFSET_MAX_TICKS == seconds_to_ticks(1.5)
    assert drawn == set(range(INITIAL_OFFSET_MIN_TICKS, INITIAL_OFFSET_MAX_TICKS + 1))


def test_seeded_initial_delays_stay_deterministic() -> None:
    def offsets(seed: int) -> list[int]:
        mode = PowerBattleMode(Simulation(seed))
        return [power.cooldown_remaining_ticks for power in mode.powers]

    for seed in (SEED, 777, 4):
        assert offsets(seed) == offsets(seed)
        assert all(offset >= INITIAL_OFFSET_MIN_TICKS for offset in offsets(seed))


def test_a_seeded_matchup_first_fires_after_the_warmup() -> None:
    """Whatever the seed picked, nothing may act during the grace period."""
    for seed in range(20):
        sim = Simulation(seed)
        mode = PowerBattleMode(sim)
        while sim.ticks < POWER_WARMUP_TICKS and mode.step():
            assert all(power.activations == 0 for power in mode.powers)


def test_render_framerate_does_not_change_the_activation_tick() -> None:
    def first_tick(frame_seconds: float) -> int | None:
        sim = Simulation(SEED)
        mode = PowerBattleMode(sim, powers=[RushPower(initial_delay_ticks=37), inert_power()])
        while mode.powers[0].last_activation_tick is None and not mode.finished:
            mode.advance(frame_seconds)
        return mode.powers[0].last_activation_tick

    ticks = {first_tick(1 / 60), first_tick(1 / 30), first_tick(1 / 240)}
    assert ticks == {POWER_WARMUP_TICKS + 36}


def test_fighters_still_move_and_collide_during_the_warmup() -> None:
    """The warmup holds powers back; it is not invulnerability or a freeze."""
    sim = Simulation(5)
    mode = PowerBattleMode(sim, powers=[inert_power(), inert_power()])
    rammer, victim = sim.balls
    mid_y = (sim.arena.top + sim.arena.bottom) / 2
    rammer.body.position = (sim.arena.left + 140.0, mid_y)
    rammer.body.velocity = (1200.0, 0.0)
    victim.body.position = ((sim.arena.left + sim.arena.right) / 2, mid_y)
    victim.body.velocity = (0.0, 0.0)
    start = victim.position

    for _ in range(POWER_WARMUP_TICKS - 1):
        mode.step()

    assert mode.warming_up is True
    assert victim.damage_taken > 0.0
    assert (victim.position - start).length > 0.0
    assert rammer.position.x > sim.arena.left + 140.0


def test_the_warmup_leaves_the_battle_deterministic() -> None:
    def timeline(seed: int) -> list[tuple[int, int]]:
        sim = Simulation(seed)
        mode = PowerBattleMode(sim)
        seen: list[tuple[int, int]] = []
        was = [False, False]
        while mode.step():
            for index, power in enumerate(mode.powers):
                if power.active and not was[index]:
                    seen.append((index, sim.ticks))
                was[index] = power.active
        return seen

    for seed in (SEED, 777):
        events = timeline(seed)
        assert events == timeline(seed)
        assert events, "no power ever fired"
        assert min(tick for _, tick in events) >= POWER_WARMUP_TICKS

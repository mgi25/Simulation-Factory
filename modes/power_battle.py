"""Duel rules: collision damage, powers, elimination, timer, winner.

The mode reads impacts reported by the simulation and owns every combat
consequence, plus the lifecycle of each fighter's power. Physics stays in
`engine`, power effects stay in `powers`, presentation stays in `rendering`.
"""

from __future__ import annotations

from enum import Enum
from typing import Iterable

from engine.randomizer import make_power_rng
from engine.simulation import PHYSICS_DT, PHYSICS_HZ, Simulation
from entities.ball import Ball
from powers import Power, PowerSpec, assign_powers

BATTLE_DURATION_SECONDS = 35.0
BATTLE_DURATION_TICKS = int(BATTLE_DURATION_SECONDS * PHYSICS_HZ)

# Damage is driven by the closing speed of an impact: below the threshold a
# touch is harmless, above it damage grows linearly up to a hard cap.
DAMAGE_MIN_CLOSING_SPEED = 400.0
DAMAGE_SCALE = 0.036
DAMAGE_MAX_PER_IMPACT = 38.0

# Safety net against a single physical impact being reported more than once
# because the bodies jitter back into contact.
IMPACT_COOLDOWN_TICKS = 12


class BattleState(Enum):
    RUNNING = "running"
    FINISHED = "finished"


class PowerBattleMode:
    """A duel: two powered fighters, impact damage, 35 simulated seconds."""

    def __init__(
        self,
        simulation: Simulation,
        powers: Iterable[PowerSpec] | None = None,
    ) -> None:
        self.sim = simulation

        # `powers=None` draws the matchup from a seeded stream; passing names
        # or ready-made instances pins it for tests and debugging.
        self.power_rng = make_power_rng(simulation.seed)
        self.powers: list[Power] = assign_powers(
            self.power_rng, len(simulation.balls), powers
        )
        for ball, power in zip(simulation.balls, self.powers):
            power.attach(ball, simulation)

        self.state = BattleState.RUNNING
        self.winner: Ball | None = None
        self.is_draw = False
        self.finished_tick: int | None = None
        self._last_damage_tick: dict[tuple[int, int], int] = {}
        self._ball_by_id = {ball.ball_id: ball for ball in simulation.balls}

    # --- clock (simulated time only, never wall-clock) ---

    @property
    def finished(self) -> bool:
        return self.state is BattleState.FINISHED

    @property
    def elapsed(self) -> float:
        return self.sim.ticks * PHYSICS_DT

    @property
    def remaining(self) -> float:
        return max(0.0, BATTLE_DURATION_SECONDS - self.elapsed)

    @property
    def duration(self) -> float | None:
        """Simulated length of a finished battle."""
        if self.finished_tick is None:
            return None
        return self.finished_tick * PHYSICS_DT

    @property
    def matchup(self) -> tuple[str, ...]:
        """Assigned power names, in fighter order."""
        return tuple(power.name for power in self.powers)

    @property
    def result_text(self) -> str:
        if not self.finished:
            return ""
        if self.is_draw:
            return "DRAW"
        assert self.winner is not None
        return f"WINNER: {self.winner.name}"

    # --- driving the battle ---

    def step(self) -> bool:
        """One fixed physics tick plus battle rules.

        Returns False once the battle is over.
        """
        if self.finished:
            return False
        self.sim.step()
        return self._after_tick()

    def advance(self, frame_seconds: float) -> int:
        """Run the ticks owed for `frame_seconds` of real time."""
        if self.finished:
            return 0
        return self.sim.advance(frame_seconds, on_tick=self._after_tick)

    def _after_tick(self) -> bool:
        self._apply_impact_damage()
        self._apply_entity_contacts()
        self._update_state()
        if self.finished:
            # No new activations once the battle is over. Any effect still
            # running is rolled back and every temporary entity retired, so
            # the final state is internally consistent.
            self._deactivate_powers()
            self.sim.clear_entities()
            return False
        self._update_powers()
        return True

    # --- power lifecycle ---

    def _update_powers(self) -> None:
        for power in self.powers:
            if power.owner is not None and power.owner.alive:
                power.update(self.sim.ticks)

    def _deactivate_powers(self) -> None:
        for power in self.powers:
            power.deactivate()

    # --- combat rules ---

    def _apply_entity_contacts(self) -> None:
        """Resolve what a dynamic entity touching something means.

        The entity states its own contribution and whether the touch spends
        it; the mode decides who it lands on. Entity damage is a flat value
        and deliberately never goes through the closing-speed impact formula,
        nor through a fighter's collision damage multiplier.
        """
        for contact in self.sim.entity_contacts:
            entity = contact.entity
            # A single step can report a wall and a fighter for the same
            # entity, so an already-spent one must not act twice.
            if not entity.active:
                continue

            if contact.is_wall:
                if entity.despawn_on_wall_contact:
                    self.sim.despawn(entity)
                continue

            victim = contact.ball
            if victim is not None and victim.alive and entity.contact_damage > 0.0:
                dealt = victim.take_damage(entity.contact_damage)
                attacker = self._ball_by_id.get(entity.owner_id)
                if attacker is not None:
                    attacker.damage_dealt += dealt

            if entity.despawn_on_ball_contact:
                self.sim.despawn(entity)

    def _apply_impact_damage(self) -> None:
        for impact in self.sim.impacts:
            a, b = impact.ball_a, impact.ball_b
            if not (a.alive and b.alive):
                continue

            key = (min(a.ball_id, b.ball_id), max(a.ball_id, b.ball_id))
            last = self._last_damage_tick.get(key)
            if last is not None and impact.tick - last < IMPACT_COOLDOWN_TICKS:
                continue

            # Only the rammed fighter is hurt: the one that drove into the
            # contact less takes the hit, so health actually diverges.
            if impact.speed_a_into_b >= impact.speed_b_into_a:
                attacker, victim = a, b
            else:
                attacker, victim = b, a

            # The base formula stays the single source of truth; a power only
            # contributes a multiplier, and only while it is active.
            damage = self.impact_damage(impact.closing_speed)
            damage *= attacker.damage_multiplier
            if damage <= 0.0:
                continue
            self._last_damage_tick[key] = impact.tick

            attacker.damage_dealt += victim.take_damage(damage)

    @staticmethod
    def impact_damage(closing_speed: float) -> float:
        """Damage an impact deals to the fighter that was rammed."""
        damage = (closing_speed - DAMAGE_MIN_CLOSING_SPEED) * DAMAGE_SCALE
        return min(max(0.0, damage), DAMAGE_MAX_PER_IMPACT)

    def _update_state(self) -> None:
        if any(not ball.alive for ball in self.sim.balls):
            survivors = [ball for ball in self.sim.balls if ball.alive]
            self._finish(survivors[0] if len(survivors) == 1 else None)
            return

        if self.sim.ticks >= BATTLE_DURATION_TICKS:
            best, second = sorted(
                self.sim.balls, key=lambda ball: ball.health, reverse=True
            )[:2]
            self._finish(best if best.health > second.health else None)

    def _finish(self, winner: Ball | None) -> None:
        self.state = BattleState.FINISHED
        self.winner = winner
        self.is_draw = winner is None
        self.finished_tick = self.sim.ticks

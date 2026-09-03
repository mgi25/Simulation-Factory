"""Base contract for modular powers.

A power is composed onto a `Ball`, never subclassed from it. The base class
owns the lifecycle only - simulation-tick timing, active state, cooldown and
the damage multiplier - and leaves the actual effect to two hooks. All timing
is counted in physics ticks, so a power's behaviour depends on simulated time
alone and never on wall-clock, pygame or Godot time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from engine.simulation import PHYSICS_DT, PHYSICS_HZ

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids an import cycle
    from engine.arena import Arena
    from entities.ball import Ball


def seconds_to_ticks(seconds: float) -> int:
    """Convert simulated seconds into whole physics ticks."""
    return max(0, int(round(seconds * PHYSICS_HZ)))


class Power:
    """Lifecycle of one temporary ability owned by one fighter."""

    name = "none"

    COOLDOWN_SECONDS = 0.0
    DURATION_SECONDS = 0.0
    # Impact damage multiplier applied to the owner's hits while active.
    DAMAGE_MULTIPLIER = 1.0

    def __init__(self, initial_delay_ticks: int = 0) -> None:
        self.owner: "Ball | None" = None
        self.arena: "Arena | None" = None

        self.cooldown_ticks = seconds_to_ticks(self.COOLDOWN_SECONDS)
        self.duration_ticks = seconds_to_ticks(self.DURATION_SECONDS)

        self.active = False
        self.activations = 0
        self.last_activation_tick: int | None = None

        # A seeded initial delay keeps two identical powers from firing in
        # permanent lockstep without making activation non-deterministic.
        self._cooldown_remaining = max(0, int(initial_delay_ticks))
        self._active_remaining = 0

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        state = "active" if self.active else "ready" if self.ready else "cooldown"
        return f"<{type(self).__name__} {state}>"

    # --- wiring ---

    def attach(self, owner: "Ball", arena: "Arena | None" = None) -> None:
        """Bind this power to its fighter (and the arena it must stay inside)."""
        self.owner = owner
        self.arena = arena
        owner.power = self

    # --- state ---

    @property
    def ready(self) -> bool:
        return not self.active and self._cooldown_remaining <= 0

    @property
    def cooldown_remaining_ticks(self) -> int:
        return self._cooldown_remaining

    @property
    def active_remaining_ticks(self) -> int:
        return self._active_remaining

    @property
    def cooldown_remaining(self) -> float:
        """Cooldown left in simulated seconds."""
        return self._cooldown_remaining * PHYSICS_DT

    @property
    def damage_multiplier(self) -> float:
        return self.DAMAGE_MULTIPLIER if self.active else 1.0

    # --- lifecycle (one call per physics tick) ---

    def update(self, tick: int | None = None) -> None:
        """Advance the power by exactly one simulation tick.

        Phase 3A activation policy: fire as soon as the cooldown is ready.
        """
        if self.active:
            self._active_remaining -= 1
            if self._active_remaining <= 0:
                self.deactivate()
        elif self._cooldown_remaining > 0:
            self._cooldown_remaining -= 1

        if self.ready:
            self.activate(tick)

    def activate(self, tick: int | None = None) -> bool:
        """Turn the effect on. Returns False when it was not possible."""
        if self.active or self.owner is None:
            return False
        self.active = True
        self._active_remaining = self.duration_ticks
        self._cooldown_remaining = 0
        self.activations += 1
        self.last_activation_tick = tick
        self._on_activate()
        return True

    def deactivate(self) -> bool:
        """Turn the effect off and start the cooldown. Idempotent."""
        if not self.active:
            return False
        self.active = False
        self._active_remaining = 0
        self._cooldown_remaining = self.cooldown_ticks
        self._on_deactivate()
        return True

    # --- effect hooks ---

    def _on_activate(self) -> None:
        """Apply the temporary effect. Always derive it from base state."""

    def _on_deactivate(self) -> None:
        """Remove exactly what `_on_activate` applied."""

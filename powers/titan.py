"""Titan: a temporarily larger, heavier fighter."""

from __future__ import annotations

from powers.power import Power


class TitanPower(Power):
    """Scales the owner's real Pymunk radius, mass and moment.

    Both the active and the restored values are derived from the ball's
    immutable base radius and mass, so activating repeatedly can never stack
    (1.5x, then 2.25x, then 3.375x...).
    """

    name = "titan"

    COOLDOWN_SECONDS = 6.0
    DURATION_SECONDS = 1.75
    RADIUS_MULTIPLIER = 1.50
    MASS_MULTIPLIER = 1.75
    # Raised from 1.35 after the Phase 3A smoke test. Growing is partly a
    # liability - a bigger fighter is an easier target - so the damage bonus
    # is what has to pay for it.
    DAMAGE_MULTIPLIER = 1.70

    def _on_activate(self) -> None:
        assert self.owner is not None
        self.owner.set_size_scale(self.RADIUS_MULTIPLIER, self.MASS_MULTIPLIER)
        # Growing next to a wall would otherwise leave the fighter embedded
        # in it; nudge the centre by the minimum needed to fit.
        if self.arena is not None:
            self.owner.clamp_into(self.arena)

    def _on_deactivate(self) -> None:
        assert self.owner is not None
        self.owner.set_size_scale(1.0, 1.0)

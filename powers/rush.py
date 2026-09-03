"""Rush: a short burst of speed and heavier impacts."""

from __future__ import annotations

from powers.power import Power


class RushPower(Power):
    """Scales the owner's current velocity once, then undoes that scaling.

    The multiplier is applied to whatever direction and magnitude the fighter
    happens to have, so direction survives untouched. Because activation and
    expiry are exact inverses, repeated activations never compound: the
    fighter's speed between bursts is whatever physics produced, not a
    progressively inflated base value.
    """

    name = "rush"

    COOLDOWN_SECONDS = 5.0
    DURATION_SECONDS = 1.25
    # Tuned down from 1.65 / 1.45 after the Phase 3A smoke test: the speed
    # boost already inflates closing speed, and closing speed already drives
    # the base damage formula, so Rush was winning ~74% of cross-matchups.
    SPEED_MULTIPLIER = 1.60
    DAMAGE_MULTIPLIER = 1.30

    def _on_activate(self) -> None:
        assert self.owner is not None
        self.owner.scale_velocity(self.SPEED_MULTIPLIER)

    def _on_deactivate(self) -> None:
        assert self.owner is not None
        self.owner.scale_velocity(1.0 / self.SPEED_MULTIPLIER)

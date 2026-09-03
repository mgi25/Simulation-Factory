"""Titan: a temporarily larger, heavier, tougher fighter."""

from __future__ import annotations

from powers.power import Power


class TitanPower(Power):
    """Scales the owner's real Pymunk radius, mass and moment, and armours it.

    Both the active and the restored values are derived from the ball's
    immutable base radius and mass, so activating repeatedly can never stack
    (1.5x, then 2.25x, then 3.375x...).
    """

    name = "titan"

    COOLDOWN_SECONDS = 6.0
    # Nudged up from 1.75 in Phase 4A1, once the mitigation below existed:
    # a slightly longer window is the cheapest way to give Titan more of the
    # only thing it is now good at, and it costs no extra damage anywhere.
    DURATION_SECONDS = 1.90
    RADIUS_MULTIPLIER = 1.50
    MASS_MULTIPLIER = 1.75
    # Raised from 1.35 after the Phase 3A smoke test. Growing is partly a
    # liability - a bigger fighter is an easier target - so the damage bonus
    # is what has to pay for it.
    DAMAGE_MULTIPLIER = 1.70
    # Titan's real identity, added in Phase 4A1. Offence alone never paid for
    # being a bigger target: at 31% of its cross-matchups it was by far the
    # weakest power, and worst of all against the ones that throw things at
    # it. Being hard to hurt while huge is both the obvious reading of the
    # power and the thing that actually fixes those matchups.
    INCOMING_DAMAGE_MULTIPLIER = 0.60

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

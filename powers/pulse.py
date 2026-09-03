"""Pulse: fires an autonomous projectile at the opponent."""

from __future__ import annotations

from entities.projectile import Projectile
from powers.power import Power, seconds_to_ticks


class PulsePower(Power):
    """Launches one straight-flying projectile per activation.

    The projectile is a dynamic entity owned by the simulation from the
    moment it is spawned. Pulse does not track it, steer it or clean it up:
    it hits, expires or leaves the arena on its own.
    """

    name = "pulse"

    # Tuned from 4.5 s / 24 HP after the Phase 3B1 smoke test, then from
    # 5.5 s in the Phase 4A1 balance pass: unlike Rush and Titan, Pulse deals
    # damage without exposing itself to the return collision, and rate of
    # fire is the honest lever on that. The damage stays flat, so a hit reads
    # the same as it always did.
    COOLDOWN_SECONDS = 6.5
    # Just long enough to read as a muzzle flash; the projectile outlives it.
    DURATION_SECONDS = 0.25

    PROJECTILE_SPEED = 1750.0
    PROJECTILE_RADIUS = 16.0
    PROJECTILE_DAMAGE = 18.0
    PROJECTILE_LIFETIME_SECONDS = 2.2
    # Clearance between the owner's surface and the projectile's, so it never
    # starts inside the fighter that fired it.
    MUZZLE_GAP = 6.0

    def _on_activate(self) -> None:
        self._fire()

    def _fire(self) -> Projectile | None:
        """Launch at the first living opponent. Deterministic, no aim-ahead."""
        owner, sim = self.owner, self.sim
        if owner is None or sim is None:
            return None

        targets = self.opponents()
        if not targets:
            return None

        heading = targets[0].position - owner.position
        if heading.length == 0.0:
            return None
        heading = heading.normalized()

        reach = owner.radius + self.PROJECTILE_RADIUS + self.MUZZLE_GAP
        muzzle = owner.position + heading * reach
        if self.arena is not None:
            # Firing from against a wall would otherwise put the muzzle
            # outside the arena, where nothing could ever be hit.
            muzzle = self.arena.clamp_circle(
                muzzle.x, muzzle.y, self.PROJECTILE_RADIUS
            )

        return sim.spawn(
            Projectile,
            owner_id=owner.ball_id,
            position=tuple(muzzle),
            velocity=tuple(heading * self.PROJECTILE_SPEED),
            radius=self.PROJECTILE_RADIUS,
            color=owner.color,
            damage=self.PROJECTILE_DAMAGE,
            lifetime_ticks=seconds_to_ticks(self.PROJECTILE_LIFETIME_SECONDS),
        )

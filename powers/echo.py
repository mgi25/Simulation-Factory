"""Echo: spawns two temporary bouncing copies of its owner."""

from __future__ import annotations

import math

import pymunk

from entities.echo_clone import EchoClone
from powers.power import Power, seconds_to_ticks


class EchoPower(Power):
    """Releases a pair of diverging clones that ricochet around the arena.

    The clones are ordinary dynamic entities: once launched, Echo has no
    further say over them. They do not steer, do not retarget and cannot
    spawn anything themselves.
    """

    name = "echo"

    # Trimmed from 6.0s / 12 HP / 4.0s life / 0.35 mass after the Phase 3B2
    # smoke test, which had Echo winning ~75% of its battles and 79-94% of
    # its cross-matchups. Two clones that persist and ricochet get many
    # chances to land for no risk to the owner, so lifetime is the strongest
    # lever here. Left deliberately short of parity: a dedicated multi-power
    # balance pass follows once all five powers exist.
    COOLDOWN_SECONDS = 7.0
    # Long enough to read as a release; the clones far outlive it.
    DURATION_SECONDS = 0.30

    CLONES_PER_ACTIVATION = 2
    # A clone is unmistakably a smaller copy of its owner.
    CLONE_RADIUS_FRACTION = 0.55
    CLONE_SPEED = 1300.0
    CLONE_DAMAGE = 8.0
    CLONE_LIFETIME_SECONDS = 2.5
    # Light enough that a hit nudges a fighter rather than launching it.
    CLONE_MASS = 0.30

    # Half the angle between the pair, so they visibly separate instead of
    # flying as one blob.
    SPREAD_DEGREES = 25.0
    MUZZLE_GAP = 6.0

    # Used only when the owner is motionless and has no living opponent to
    # aim away from; fixed so it can never depend on chance.
    FALLBACK_HEADING = pymunk.Vec2d(1.0, 0.0)

    def _on_activate(self) -> None:
        self._release()

    def _release(self) -> list[EchoClone]:
        owner, sim = self.owner, self.sim
        if owner is None or sim is None:
            return []

        heading = self._launch_heading()
        radius = owner.base_radius * self.CLONE_RADIUS_FRACTION
        reach = owner.radius + radius + self.MUZZLE_GAP
        lifetime = seconds_to_ticks(self.CLONE_LIFETIME_SECONDS)

        clones: list[EchoClone] = []
        for direction in self._spread(heading):
            position = owner.position + direction * reach
            if self.arena is not None:
                position = pymunk.Vec2d(
                    *self.arena.clamp_circle(position.x, position.y, radius)
                )
            clones.append(
                sim.spawn(
                    EchoClone,
                    owner_id=owner.ball_id,
                    position=tuple(position),
                    velocity=tuple(direction * self.CLONE_SPEED),
                    radius=radius,
                    color=owner.color,
                    damage=self.CLONE_DAMAGE,
                    lifetime_ticks=lifetime,
                    mass=self.CLONE_MASS,
                )
            )
        return clones

    def _launch_heading(self) -> pymunk.Vec2d:
        """Where the pair straddles: the owner's course, else the opponent."""
        assert self.owner is not None
        velocity = self.owner.velocity
        if velocity.length > 0.0:
            return velocity.normalized()

        targets = self.opponents()
        if targets:
            toward = targets[0].position - self.owner.position
            if toward.length > 0.0:
                return toward.normalized()

        return self.FALLBACK_HEADING

    def _spread(self, heading: pymunk.Vec2d) -> list[pymunk.Vec2d]:
        """Evenly straddle `heading`, e.g. -25 and +25 degrees for a pair."""
        count = self.CLONES_PER_ACTIVATION
        spread = math.radians(self.SPREAD_DEGREES)
        if count == 1:
            return [heading]
        step = (2.0 * spread) / (count - 1)
        return [heading.rotated(-spread + step * i) for i in range(count)]

"""Orbit: satellites that ride along with their owner."""

from __future__ import annotations

import math

import pymunk

from engine.simulation import PHYSICS_HZ
from entities.orbit_orb import OrbitOrb
from powers.power import Power


class OrbitPower(Power):
    """Surrounds its owner with revolving orbs for as long as it is active.

    Unlike Pulse and Echo, whose entities are released and forgotten, these
    belong to the power: it holds them while active and retires whatever
    survived when it expires.
    """

    name = "orbit"

    COOLDOWN_SECONDS = 6.5
    DURATION_SECONDS = 2.75

    ORB_COUNT = 3
    ORB_RADIUS = 17.0
    # Measured from the owner's base radius, so a temporary size change
    # elsewhere can never drag the orbit in or out with it.
    ORBIT_EXTRA_DISTANCE = 80.0
    ANGULAR_SPEED_DEGREES = 270.0
    ORB_DAMAGE = 10.0

    def __init__(self, initial_delay_ticks: int = 0) -> None:
        super().__init__(initial_delay_ticks=initial_delay_ticks)
        self.orbs: list[OrbitOrb] = []

    @property
    def orbit_radius(self) -> float:
        assert self.owner is not None
        return self.owner.base_radius + self.ORBIT_EXTRA_DISTANCE

    def angular_step(self) -> float:
        """Radians per simulation tick, signed by the owner's spin direction."""
        per_tick = math.radians(self.ANGULAR_SPEED_DEGREES) / PHYSICS_HZ
        return per_tick * self.spin_direction()

    def spin_direction(self) -> int:
        """Even fighters turn one way, odd fighters the other. Deterministic."""
        assert self.owner is not None
        return 1 if self.owner.ball_id % 2 == 0 else -1

    def _on_activate(self) -> None:
        self.orbs = self._deploy()

    def _on_deactivate(self) -> None:
        # Any orb that already landed a hit is gone; despawn ignores it.
        if self.sim is not None:
            for orb in self.orbs:
                self.sim.despawn(orb)
        self.orbs = []

    def _deploy(self) -> list[OrbitOrb]:
        owner, sim = self.owner, self.sim
        if owner is None or sim is None:
            return []

        radius = self.orbit_radius
        step = self.angular_step()
        orbs: list[OrbitOrb] = []

        for angle in self._start_angles():
            position = owner.position + _unit(angle) * radius
            if self.arena is not None:
                position = self.arena.clamp_circle(
                    position.x, position.y, self.ORB_RADIUS
                )
            orbs.append(
                sim.spawn(
                    OrbitOrb,
                    owner_id=owner.ball_id,
                    position=tuple(position),
                    radius=self.ORB_RADIUS,
                    color=owner.color,
                    damage=self.ORB_DAMAGE,
                    orbit_radius=radius,
                    angle=angle,
                    angular_step=step,
                )
            )
        return orbs

    def _start_angles(self) -> list[float]:
        """Evenly spaced, with the first orb on the owner's line of travel."""
        assert self.owner is not None
        velocity = self.owner.velocity
        phase = velocity.angle if velocity.length > 0.0 else 0.0
        spacing = 2.0 * math.pi / self.ORB_COUNT
        return [phase + spacing * i for i in range(self.ORB_COUNT)]


def _unit(angle: float) -> pymunk.Vec2d:
    return pymunk.Vec2d(math.cos(angle), math.sin(angle))

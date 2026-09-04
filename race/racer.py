"""A racer: physics body, identity, and everything the race knows about it.

The racer owns its own physical state and its own record of the race. It
does not own the rules: it never decides that it has finished, is stuck or
has been overtaken. `race.manager` decides all of that and writes it here,
which keeps the one place a racer can change state easy to find.
"""

from __future__ import annotations

import math

import pymunk

from race.config import (
    COLLISION_TYPE_RACER,
    MAX_ANGULAR_SPEED,
    MAX_SPEED,
    RACER_COLORS,
    RACER_ELASTICITY,
    RACER_FRICTION,
    RACER_MASS,
    RACER_RADIUS,
)

__all__ = ["Racer", "racer_name"]


def racer_name(racer_id: int) -> str:
    """`Racer_01` .. `Racer_10`: zero-padded so names sort like the field."""
    return f"Racer_{racer_id + 1:02d}"


def _clamp_body(body: pymunk.Body) -> None:
    """Hold a body inside the speed limits, preserving its direction."""
    speed = body.velocity.length
    if speed > MAX_SPEED:
        body.velocity = body.velocity * (MAX_SPEED / speed)
    if abs(body.angular_velocity) > MAX_ANGULAR_SPEED:
        body.angular_velocity = math.copysign(MAX_ANGULAR_SPEED, body.angular_velocity)


def _limit_velocity(
    body: pymunk.Body, gravity: tuple[float, float], damping: float, dt: float
) -> None:
    """Integrate velocity as usual, then hold it inside the speed limits.

    The cap is the single most important number in the race. Gravity over a
    course this tall would otherwise put the whole field past a thousand
    pixels a second inside two seconds, and a Shorts viewer would see one
    frame of blur and a result. Capping speed - rather than adding drag - is
    what keeps the pack readable while leaving the *ordering* entirely to
    the physics: every racer is subject to the identical limit.

    This hook alone is not enough, which is not obvious and was not cheap to
    find. It runs during integration, before the solver; a spinner arm is an
    infinite-mass kinematic body, so resolving a deep contact against one
    can hand a racer an enormous impulse afterwards. Measured over forty
    seeds, that put racers up to 240% past the cap - 2500 pixels a second,
    a genuine blur - for the tick before this hook next ran. So the cap is
    applied again after the solver, in `RaceSimulation.step`.
    """
    pymunk.Body.update_velocity(body, gravity, damping, dt)
    _clamp_body(body)


class Racer:
    """One competitor. Identical to every other one except for its colour."""

    def __init__(
        self,
        racer_id: int,
        position: tuple[float, float],
        radius: float = RACER_RADIUS,
        spawn_slot: int = 0,
    ) -> None:
        self.racer_id = racer_id
        self.name = racer_name(racer_id)
        self.color = RACER_COLORS[racer_id % len(RACER_COLORS)]
        self.radius = radius
        self.spawn_slot = spawn_slot

        moment = pymunk.moment_for_circle(RACER_MASS, 0.0, radius)
        self.body = pymunk.Body(RACER_MASS, moment)
        self.body.position = position
        self.body.velocity_func = _limit_velocity

        self.shape = pymunk.Circle(self.body, radius)
        self.shape.elasticity = RACER_ELASTICITY
        self.shape.friction = RACER_FRICTION
        self.shape.collision_type = COLLISION_TYPE_RACER
        # No filter group: racers must collide with each other. Contact
        # between racers is most of what makes a race a race.

        self.space: pymunk.Space | None = None

        # --- race state, written by the manager ---
        self.checkpoint = -1        # furthest progress node credited
        self.branch = ""            # which path of a split it committed to
        self.progress = 0.0         # continuous position along its route
        self.best_progress = 0.0    # high-water mark, for stuck detection
        self.rank = racer_id + 1    # 1-based, current standing
        self.finished = False
        self.finish_tick: int | None = None
        self.finish_time: float | None = None
        self.time_penalty = 0.0     # seconds added by recoveries
        self.recoveries = 0
        self.retired = False        # gave up on recovering it
        self.stuck_ticks = 0        # consecutive ticks looking stuck
        self.recovery_cooldown = 0  # ticks left before it may recover again

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        where = f"/{self.branch}" if self.branch else ""
        return (
            f"<Racer {self.name} cp={self.checkpoint}{where}"
            f" p={self.progress:.2f}>"
        )

    # --- physics state ---

    @property
    def position(self) -> pymunk.Vec2d:
        return self.body.position

    @property
    def velocity(self) -> pymunk.Vec2d:
        return self.body.velocity

    @property
    def speed(self) -> float:
        return self.body.velocity.length

    @property
    def racing(self) -> bool:
        """True while this racer is still competing for a finish position."""
        return not self.finished and not self.retired

    @property
    def official_time(self) -> float | None:
        """Finish time including any recovery penalties."""
        if self.finish_time is None:
            return None
        return self.finish_time + self.time_penalty

    def add_to_space(self, space: pymunk.Space) -> None:
        space.add(self.body, self.shape)
        self.space = space

    def remove_from_space(self) -> None:
        """Take the racer out of the world. Idempotent; used by retirement."""
        if self.space is None:
            return
        self.space.remove(self.body, self.shape)
        self.space = None

    def clamp_speed(self) -> None:
        """Re-apply the speed limits after the solver has had its say.

        Called once per tick by the simulation, so the cap is true whenever
        anything reads a racer - a rule, a renderer or a test - rather than
        only in the middle of integration.
        """
        _clamp_body(self.body)

    def teleport(self, position: tuple[float, float]) -> None:
        """Place the racer somewhere at rest. Only recovery may call this.

        Deliberately blunt, and deliberately not called anything gentler:
        moving a racer by hand is the one thing a physics race must never do
        casually, so it happens in exactly one place and is always logged.
        """
        self.body.position = position
        self.body.velocity = (0.0, 0.0)
        self.body.angular_velocity = 0.0
        if self.space is not None:
            self.space.reindex_shapes_for_body(self.body)

    def is_finite(self) -> bool:
        return all(
            math.isfinite(value)
            for value in (
                self.body.position.x,
                self.body.position.y,
                self.body.velocity.x,
                self.body.velocity.y,
            )
        )

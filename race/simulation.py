"""The race physics world: space, course, racers, contact reports.

Deliberately the same shape as `engine.simulation`: it owns the space and
the bodies, steps at a fixed rate, and reports contacts as plain data
without deciding what any of them mean. Ranking, finishing, stuck detection
and recovery are all `race.manager`.

It has its own space rather than reusing the duel one because the two need
opposite physics. A duel runs at zero gravity with perfectly elastic,
frictionless surfaces so that it never winds down. A race needs gravity to
have a downhill at all, friction so a ball rolls rather than skates, and a
speed limit so the field stays readable. None of that could be layered onto
the duel space without changing every fight that has ever been recorded.
"""

from __future__ import annotations

from dataclasses import dataclass

import pymunk

from race.config import (
    COLLISION_TYPE_JUMP_PAD,
    COLLISION_TYPE_RACER,
    COLLISION_TYPE_SPINNER,
    GRAVITY,
    IMPACT_REPORT_COOLDOWN_TICKS,
    JUMP_PAD_COOLDOWN_TICKS,
    PHYSICS_DT,
    RACER_COUNT,
    SPACE_DAMPING,
    SPAWN_JITTER_X,
    SPAWN_JITTER_Y,
    START_NUDGE,
)
from race.course import CoursePiece, RaceCourse
from race.courses import DEFAULT_COURSE, build_course
from race.racer import Racer
from race.runtime import TrackRuntime
from race.seeds import make_jitter_rng, make_spawn_rng

__all__ = ["JumpKick", "RacerImpact", "RaceSimulation", "build_grid"]


@dataclass(frozen=True)
class RacerImpact:
    """Two racers meeting, reported once when contact begins."""

    tick: int
    racer_a: int
    racer_b: int
    closing_speed: float
    x: float
    y: float


@dataclass(frozen=True)
class JumpKick:
    """A jump pad firing: which racer, from where, with what impulse."""

    tick: int
    racer_id: int
    piece_id: int
    impulse: tuple[float, float]
    x: float
    y: float


def build_grid(course: RaceCourse, seed: int, count: int = RACER_COUNT) -> list[Racer]:
    """Put `count` racers on the grid, shuffled and offset by seed.

    Which racer gets which slot is the single largest seeded influence on a
    race, and it is a fair one: every slot is a real starting position, no
    slot is better by construction, and the assignment is a permutation, so
    no racer can draw a better *kind* of start than another.
    """
    rng = make_spawn_rng(seed)
    slots = list(course.spawns[:count])
    if len(slots) < count:
        raise ValueError(
            f"course {course.course_id!r} has {len(course.spawns)} spawn slots, "
            f"needs {count}"
        )
    rng.shuffle(slots)

    racers = []
    for racer_id, slot in enumerate(slots):
        racer = Racer(
            racer_id=racer_id,
            position=(
                slot.x + rng.uniform(-SPAWN_JITTER_X, SPAWN_JITTER_X),
                slot.y + rng.uniform(-SPAWN_JITTER_Y, SPAWN_JITTER_Y),
            ),
            spawn_slot=slot.slot,
        )
        racer.body.velocity = (rng.uniform(-START_NUDGE, START_NUDGE), 0.0)
        racers.append(racer)
    return racers


class RaceSimulation:
    """Owns the space, the course and the racers, and the simulation clock."""

    def __init__(
        self,
        seed: int,
        course: RaceCourse | None = None,
        course_name: str = DEFAULT_COURSE,
        racer_count: int = RACER_COUNT,
    ) -> None:
        self.seed = seed
        # A ready-made course wins over a name, which is how a test pins
        # exact geometry instead of hunting for a seed that produces it -
        # the same escape hatch `Simulation` gives for an arena layout.
        self.course = course if course is not None else build_course(course_name, seed)

        self.space = pymunk.Space()
        self.space.gravity = (0.0, GRAVITY)
        self.space.damping = SPACE_DAMPING

        self.track = TrackRuntime(self.course, self.space)

        self.racers: list[Racer] = build_grid(self.course, seed, racer_count)
        for racer in self.racers:
            racer.add_to_space(self.space)
        self._racer_by_shape = {racer.shape: racer for racer in self.racers}
        self._racer_by_id = {racer.racer_id: racer for racer in self.racers}

        # Runtime randomness lives on its own stream, so a race that fires
        # one more jump-pad kick cannot shift the course or the grid.
        self.jitter_rng = make_jitter_rng(seed)

        # Cleared at the start of every tick, so a reader always sees this
        # tick contacts and never a backlog.
        self.impacts: list[RacerImpact] = []
        self.jumps: list[JumpKick] = []
        self.spinner_contacts = 0

        self._last_impact_tick: dict[tuple[int, int], int] = {}
        self._last_kick_tick: dict[tuple[int, int], int] = {}
        self._pending_kicks: list[tuple[Racer, CoursePiece]] = []

        self.space.on_collision(
            COLLISION_TYPE_RACER, COLLISION_TYPE_RACER, begin=self._on_racer_impact
        )
        self.space.on_collision(
            COLLISION_TYPE_RACER, COLLISION_TYPE_JUMP_PAD, begin=self._on_jump_pad
        )
        self.space.on_collision(
            COLLISION_TYPE_RACER, COLLISION_TYPE_SPINNER, begin=self._on_spinner
        )

        self.ticks = 0
        self.elapsed = 0.0

    # --- lookups ---

    def racer(self, racer_id: int) -> Racer | None:
        return self._racer_by_id.get(racer_id)

    @property
    def gates_open(self) -> bool:
        return self.track.gates_open

    def open_gates(self) -> int:
        return self.track.open_gates()

    # --- contact reporting ---

    def _on_racer_impact(self, arbiter: pymunk.Arbiter, space, data) -> None:
        """Report a racer-on-racer contact. Changes nothing about it.

        Returning None accepts the collision exactly as the default handler
        would, so observing contacts leaves the race bit-for-bit unchanged.
        """
        shape_a, shape_b = arbiter.shapes
        racer_a = self._racer_by_shape.get(shape_a)
        racer_b = self._racer_by_shape.get(shape_b)
        if racer_a is None or racer_b is None:
            return

        key = (
            min(racer_a.racer_id, racer_b.racer_id),
            max(racer_a.racer_id, racer_b.racer_id),
        )
        last = self._last_impact_tick.get(key)
        if last is not None and self.ticks - last < IMPACT_REPORT_COOLDOWN_TICKS:
            return
        self._last_impact_tick[key] = self.ticks

        normal = arbiter.normal  # unit vector, from shape a towards shape b
        closing = max(0.0, racer_a.velocity.dot(normal)) + max(
            0.0, -racer_b.velocity.dot(normal)
        )
        contact = (racer_a.position + racer_b.position) * 0.5
        self.impacts.append(
            RacerImpact(
                tick=self.ticks,
                racer_a=racer_a.racer_id,
                racer_b=racer_b.racer_id,
                closing_speed=closing,
                x=contact.x,
                y=contact.y,
            )
        )

    def _on_jump_pad(self, arbiter: pymunk.Arbiter, space, data) -> None:
        """Note that a racer touched a pad; the kick is applied after the step.

        Queued rather than applied here so the impulse never lands in the
        middle of the solver resolving that same contact. One tick later the
        racer is sitting on the pad and the kick sends it cleanly off the
        lip, which is also what it looks like it should do.
        """
        racer: Racer | None = None
        piece: CoursePiece | None = None
        for shape in arbiter.shapes:
            racer = racer or self._racer_by_shape.get(shape)
            piece = piece or self.track.piece_by_shape.get(shape)
        if racer is None or piece is None:
            return

        key = (racer.racer_id, piece.piece_id)
        last = self._last_kick_tick.get(key)
        if last is not None and self.ticks - last < JUMP_PAD_COOLDOWN_TICKS:
            return
        self._last_kick_tick[key] = self.ticks
        self._pending_kicks.append((racer, piece))

    def _on_spinner(self, arbiter: pymunk.Arbiter, space, data) -> None:
        self.spinner_contacts += 1

    # --- the kick ---

    def _apply_kicks(self) -> None:
        """Fire every pad queued this tick, in racer order.

        The ordering matters and is not cosmetic: each kick draws a jitter
        value from the seeded stream, so if two racers hit a pad on the same
        tick, the order they are served in decides which value each gets.
        Sorting by racer id makes that independent of the order Chipmunk
        happened to report the contacts in, which is what keeps a race
        reproducible from its seed.
        """
        if not self._pending_kicks:
            return
        self._pending_kicks.sort(key=lambda pair: pair[0].racer_id)
        for racer, piece in self._pending_kicks:
            scale = 1.0
            if piece.impulse_jitter > 0.0:
                scale += self.jitter_rng.uniform(
                    -piece.impulse_jitter, piece.impulse_jitter
                )
            impulse = (piece.impulse[0] * scale, piece.impulse[1] * scale)
            racer.body.apply_impulse_at_local_point(impulse)
            self.jumps.append(
                JumpKick(
                    tick=self.ticks,
                    racer_id=racer.racer_id,
                    piece_id=piece.piece_id,
                    impulse=impulse,
                    x=racer.position.x,
                    y=racer.position.y,
                )
            )
        self._pending_kicks.clear()

    # --- the clock ---

    def step(self) -> None:
        """Advance the physics by exactly one fixed tick.

        There is no real-time accumulator anywhere in the race: a caller
        asks for ticks and gets ticks. A preview that cannot keep up plays
        the race slowly rather than stepping a different number of times,
        because a variable step count would make the same seed produce a
        different race on a slower machine.
        """
        self.impacts.clear()
        self.jumps.clear()

        self.space.step(PHYSICS_DT)

        self.ticks += 1
        self.elapsed += PHYSICS_DT

        self._apply_kicks()

        # Last thing, after both the solver and the pads. The velocity hook
        # on each body caps speed during integration, but the solver runs
        # after it and a spinner arm is an infinite-mass body: a deep
        # contact against one can throw a racer far past the cap for a tick.
        # Clamping here is what makes the limit true whenever anyone looks,
        # and it is the same limit for every racer, so it decides nothing
        # about who wins.
        for racer in self.racers:
            racer.clamp_speed()

    # --- validity ---

    def is_state_valid(self) -> bool:
        """True while every racer and spinner has finite state.

        Position is not checked against the course here: leaving the course
        is a race event with a defined recovery, not an invalid simulation.
        This is only about the numbers themselves still being numbers.
        """
        return all(racer.is_finite() for racer in self.racers) and self.track.is_finite()

"""Race rules: countdown, ranking, finishing, recovery, and the race clock.

The counterpart of `modes.power_battle`. The simulation owns the physics and
reports contacts; everything that turns those into a race with a result
happens here, and nothing here reaches into the solver. The manager reads
positions, writes race state onto racers, and records events.

One deliberate exception to "the physics decides": recovery moves a racer by
hand. It is the only code in the race that may, it happens in exactly one
method, it always costs the racer the ground it had covered since its last
checkpoint, and it is always logged. Everything else about a race - who
leads, who is held up, who wins - comes out of the solver.
"""

from __future__ import annotations

import math
from enum import Enum

from race.config import (
    COUNTDOWN_SECONDS,
    COUNTDOWN_TICKS,
    FINISH_GRACE_SECONDS,
    LARGE_COLLISION_SPEED,
    MAX_RECOVERIES_PER_RACER,
    PHYSICS_DT,
    PHYSICS_HZ,
    RACE_TIMEOUT_SECONDS,
    RANKING_SAMPLE_HZ,
    RECOVERY_COOLDOWN_SECONDS,
    RECOVERY_PENALTY_SECONDS,
    STUCK_PROGRESS_EPSILON,
    STUCK_SECONDS,
    STUCK_SPEED,
)
from race.events import (
    EVENT_CHECKPOINT,
    EVENT_COLLISION,
    EVENT_COMPLETE,
    EVENT_COUNTDOWN,
    EVENT_FINISH,
    EVENT_JUMP,
    EVENT_LEAD_CHANGE,
    EVENT_RECOVERY,
    EVENT_RETIRED,
    EVENT_START,
    EVENT_WINNER,
    REASON_OUT_OF_BOUNDS,
    REASON_STUCK,
    RaceEvent,
)
from race.progress import assign_ranks, count_inversions, update_progress
from race.racer import Racer
from race.simulation import RaceSimulation

__all__ = ["RaceState", "RaceManager"]

FINISH_GRACE_TICKS = int(round(FINISH_GRACE_SECONDS * PHYSICS_HZ))
RACE_TIMEOUT_TICKS = int(round(RACE_TIMEOUT_SECONDS * PHYSICS_HZ))
STUCK_TICKS = int(round(STUCK_SECONDS * PHYSICS_HZ))
RECOVERY_COOLDOWN_TICKS = int(round(RECOVERY_COOLDOWN_SECONDS * PHYSICS_HZ))
RANKING_SAMPLE_TICKS = max(1, int(round(PHYSICS_HZ / RANKING_SAMPLE_HZ)))


class RaceState(Enum):
    COUNTDOWN = "countdown"    # racers held behind the gate
    RUNNING = "running"        # gate open, nobody home yet
    FINISHING = "finishing"    # the winner is in, the pack still counts
    COMPLETE = "complete"      # nothing left to record


class RaceManager:
    """Drives one race from the countdown to a result."""

    def __init__(self, simulation: RaceSimulation) -> None:
        self.sim = simulation
        self.course = simulation.course

        self.state = RaceState.COUNTDOWN
        self.events: list[RaceEvent] = []

        self.winner: Racer | None = None
        self.finish_order: list[Racer] = []
        self.completed_tick: int | None = None
        self.timed_out = False

        self.leader_id: int | None = None
        self.leader_changes = 0
        self.overtakes = 0
        self.large_collisions = 0
        self.recoveries = 0
        self.retirements = 0

        self._finish_deadline_tick: int | None = None
        self._countdown_announced: set[int] = set()
        self._sampled_order: list[int] = []

        assign_ranks(self.sim.racers)

    # --- clock ---

    @property
    def race_time(self) -> float:
        """Simulated seconds since the gate opened. Negative during the count."""
        return (self.sim.ticks - COUNTDOWN_TICKS) * PHYSICS_DT

    @property
    def countdown_remaining(self) -> float:
        return max(0.0, COUNTDOWN_SECONDS - self.sim.ticks * PHYSICS_DT)

    @property
    def countdown_number(self) -> int:
        """3, 2 or 1 during the count; 0 once the race is under way."""
        return int(math.ceil(self.countdown_remaining - 1e-9))

    @property
    def started(self) -> bool:
        return self.state is not RaceState.COUNTDOWN

    @property
    def complete(self) -> bool:
        return self.state is RaceState.COMPLETE

    @property
    def duration(self) -> float | None:
        """Race time at which the race ended."""
        if self.completed_tick is None:
            return None
        return (self.completed_tick - COUNTDOWN_TICKS) * PHYSICS_DT

    @property
    def winner_time(self) -> float | None:
        return None if self.winner is None else self.winner.finish_time

    @property
    def racers_finished(self) -> int:
        return len(self.finish_order)

    @property
    def ranked(self) -> list[Racer]:
        """The field in current race order, best first."""
        return assign_ranks(self.sim.racers)

    # --- driving the race ---

    def step(self) -> bool:
        """One fixed physics tick plus race rules. False once complete."""
        if self.complete:
            return False
        self._before_tick()
        self.sim.step()
        self._after_tick()
        return not self.complete

    def run(self, max_ticks: int | None = None) -> int:
        """Step until the race completes. Returns the ticks run.

        The headless path. There is no real-time accumulator: a race is a
        number of ticks, which is what makes a seed reproducible.
        """
        limit = RACE_TIMEOUT_TICKS + COUNTDOWN_TICKS + FINISH_GRACE_TICKS + 1
        if max_ticks is not None:
            limit = min(limit, max_ticks)
        ticks = 0
        while ticks < limit and self.step():
            ticks += 1
        return ticks

    # --- the countdown ---

    def _before_tick(self) -> None:
        if self.state is not RaceState.COUNTDOWN:
            return
        if self.sim.ticks >= COUNTDOWN_TICKS:
            self._open_gate()
            return
        number = self.countdown_number
        if number not in self._countdown_announced:
            self._countdown_announced.add(number)
            self._record(EVENT_COUNTDOWN, value=float(number), detail=str(number))

    def _open_gate(self) -> None:
        self.sim.open_gates()
        self.state = RaceState.RUNNING
        # Every racer's progress high-water mark starts from where it
        # actually is, so a racer that spent the countdown resting against
        # the gate is not immediately suspected of being stuck there.
        for racer in self.sim.racers:
            racer.progress = self.course.progress_at(racer.position.y)
            racer.best_progress = racer.progress
            racer.stuck_ticks = 0
        self._record(EVENT_START, detail="go")

    # --- per-tick rules ---

    def _after_tick(self) -> None:
        if self.state is RaceState.COUNTDOWN:
            return
        self._update_positions()
        self._update_recovery()
        self._record_contacts()
        assign_ranks(self.sim.racers)
        self._sample_ranking()
        self._update_state()

    def _update_positions(self) -> None:
        for racer in self.sim.racers:
            if racer.retired:
                continue
            for index in update_progress(self.course, racer):
                if index >= self.course.last_index:
                    self._finish_racer(racer)
                else:
                    self._record(
                        EVENT_CHECKPOINT,
                        racer,
                        value=float(index),
                        detail=self.course.checkpoint(index).name,
                    )

    def _finish_racer(self, racer: Racer) -> None:
        """Cross the line once and only once.

        Reached through `update_progress`, which only reports a checkpoint
        the first time a racer passes it, so a finisher rolling back over
        the plane in the paddock cannot finish twice. The `finished` guard
        is belt and braces on top of that.
        """
        if racer.finished:
            return
        racer.finished = True
        racer.finish_tick = self.sim.ticks
        racer.finish_time = self.race_time
        self.finish_order.append(racer)
        self._record(
            EVENT_FINISH,
            racer,
            value=racer.finish_time,
            detail=str(len(self.finish_order)),
        )

        if self.winner is None:
            self.winner = racer
            self._record(EVENT_WINNER, racer, value=racer.finish_time)
            self.state = RaceState.FINISHING
            self._finish_deadline_tick = self.sim.ticks + FINISH_GRACE_TICKS

    # --- recovery ---

    def _update_recovery(self) -> None:
        """Notice racers that have left the course or stopped racing on it."""
        for racer in self.sim.racers:
            if not racer.racing:
                continue
            if racer.recovery_cooldown > 0:
                racer.recovery_cooldown -= 1

            # Order matters: a non-finite position makes every comparison
            # below meaningless, so it is caught first.
            if not racer.is_finite():
                self._recover(racer, REASON_OUT_OF_BOUNDS)
                continue
            if self.course.out_of_bounds(racer.position.x, racer.position.y):
                self._recover(racer, REASON_OUT_OF_BOUNDS)
                continue

            if racer.progress > racer.best_progress + STUCK_PROGRESS_EPSILON:
                racer.best_progress = racer.progress
                racer.stuck_ticks = 0
                continue
            # Both conditions have to hold together. Slow on its own is a
            # racer in a queue; no progress on its own is a racer bouncing
            # around an obstacle. Neither is stuck.
            racer.stuck_ticks = racer.stuck_ticks + 1 if racer.speed < STUCK_SPEED else 0
            if racer.stuck_ticks >= STUCK_TICKS and racer.recovery_cooldown == 0:
                self._recover(racer, REASON_STUCK)

    def _recover(self, racer: Racer, reason: str) -> None:
        """Put a racer back on the course at its last checkpoint.

        The only place a racer is moved by anything other than physics.
        Never silent: every recovery is an event and a telemetry count, and
        it always costs the racer everything it had covered since that
        checkpoint - which is usually a far heavier penalty than the
        recorded seconds.
        """
        racer.stuck_ticks = 0
        if racer.recoveries >= MAX_RECOVERIES_PER_RACER:
            self._retire(racer, reason)
            return

        checkpoint = self.course.checkpoint(max(0, racer.checkpoint))
        racer.teleport(checkpoint.respawn)
        racer.recoveries += 1
        racer.time_penalty += RECOVERY_PENALTY_SECONDS
        racer.recovery_cooldown = RECOVERY_COOLDOWN_TICKS
        racer.progress = self.course.progress_at(checkpoint.respawn[1])
        racer.best_progress = racer.progress
        self.recoveries += 1
        self._record(
            EVENT_RECOVERY,
            racer,
            value=float(checkpoint.index),
            detail=reason,
        )

    def _retire(self, racer: Racer, reason: str) -> None:
        """Give up on a racer that recovery cannot rescue.

        Taken out of the space rather than left lying on the course: a body
        that recovery has failed on four times is somewhere it should not
        be, and leaving it there lets it obstruct racers that are still
        racing. This should be rare - it means the geometry beat the net.
        """
        racer.retired = True
        racer.remove_from_space()
        self.retirements += 1
        self._record(EVENT_RETIRED, racer, value=float(racer.recoveries), detail=reason)

    # --- telemetry ---

    def _record_contacts(self) -> None:
        for impact in self.sim.impacts:
            if impact.closing_speed < LARGE_COLLISION_SPEED:
                continue
            self.large_collisions += 1
            self.events.append(
                RaceEvent(
                    tick=self.sim.ticks,
                    race_time=self.race_time,
                    type=EVENT_COLLISION,
                    racer_id=impact.racer_a,
                    x=impact.x,
                    y=impact.y,
                    value=impact.closing_speed,
                    detail=str(impact.racer_b),
                )
            )
        for kick in self.sim.jumps:
            self.events.append(
                RaceEvent(
                    tick=self.sim.ticks,
                    race_time=self.race_time,
                    type=EVENT_JUMP,
                    racer_id=kick.racer_id,
                    x=kick.x,
                    y=kick.y,
                    value=math.hypot(*kick.impulse),
                    detail=str(kick.piece_id),
                )
            )

    def _sample_ranking(self) -> None:
        """Count overtakes and lead changes on a coarse clock.

        Sampled at a dozen times a second rather than every tick because two
        racers in contact trade places repeatedly inside a single collision;
        counting every tick would report a jostle as twenty overtakes.
        """
        if self.sim.ticks % RANKING_SAMPLE_TICKS:
            return
        order = [racer.racer_id for racer in self.sim.racers if not racer.retired]
        order.sort(key=lambda racer_id: self.sim.racer(racer_id).rank)
        if not order:
            return

        if self._sampled_order:
            self.overtakes += count_inversions(self._sampled_order, order)
            # Only while the race is still being decided: after the winner
            # is in, first place cannot change hands again.
            if self.state is RaceState.RUNNING and order[0] != self.leader_id:
                self.leader_changes += 1
                leader = self.sim.racer(order[0])
                self._record(EVENT_LEAD_CHANGE, leader, value=float(self.leader_changes))
        self.leader_id = order[0]
        self._sampled_order = order

    # --- lifecycle ---

    def _update_state(self) -> None:
        if not any(racer.racing for racer in self.sim.racers):
            self._complete()
            return
        if self.race_time >= RACE_TIMEOUT_SECONDS:
            self.timed_out = True
            self._complete()
            return
        if (
            self.state is RaceState.FINISHING
            and self._finish_deadline_tick is not None
            and self.sim.ticks >= self._finish_deadline_tick
        ):
            self._complete()

    def _complete(self) -> None:
        if self.complete:
            return
        self.state = RaceState.COMPLETE
        self.completed_tick = self.sim.ticks
        self._record(
            EVENT_COMPLETE,
            value=self.duration,
            detail="timeout" if self.timed_out else "finished",
        )

    def _record(
        self,
        event_type: str,
        racer: Racer | None = None,
        value: float | None = None,
        detail: str | None = None,
    ) -> None:
        self.events.append(
            RaceEvent(
                tick=self.sim.ticks,
                race_time=self.race_time,
                type=event_type,
                racer_id=None if racer is None else racer.racer_id,
                x=None if racer is None else racer.position.x,
                y=None if racer is None else racer.position.y,
                value=value,
                detail=detail,
            )
        )

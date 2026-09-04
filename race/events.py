"""Race events: the ordered, tick-stamped record of what happened.

The same contract `modes.events` defines for a duel, for the same reason. A
frame of a race says where every racer is; it cannot say that this is the
tick Racer_07 took the lead, cleared the pad or was pulled out of the
funnel. Those moments have to be recorded when they happen or they are gone.

Recording is write-only. Nothing in the race rules reads this list back, so
appending an event can never change the result of a race - which is what
makes it safe to record freely.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "EVENT_COUNTDOWN",
    "EVENT_START",
    "EVENT_CHECKPOINT",
    "EVENT_LEAD_CHANGE",
    "EVENT_JUMP",
    "EVENT_COLLISION",
    "EVENT_RECOVERY",
    "EVENT_FINISH",
    "EVENT_WINNER",
    "EVENT_RETIRED",
    "EVENT_COMPLETE",
    "EVENT_TYPES",
    "REASON_STUCK",
    "REASON_OUT_OF_BOUNDS",
    "RaceEvent",
]

EVENT_COUNTDOWN = "countdown"        # one per second of the countdown
EVENT_START = "start"                # the gate opened
EVENT_CHECKPOINT = "checkpoint"      # a racer crossed a plane
EVENT_LEAD_CHANGE = "lead_change"    # a new racer is first
EVENT_JUMP = "jump"                  # a jump pad fired
EVENT_COLLISION = "collision"        # racer-on-racer, above the threshold
EVENT_RECOVERY = "recovery"          # a racer was put back on the course
EVENT_FINISH = "finish"              # a racer crossed the finish plane
EVENT_WINNER = "winner"              # the first finish, announced once
EVENT_RETIRED = "retired"            # recovery gave up on a racer
EVENT_COMPLETE = "complete"          # the race itself ended

EVENT_TYPES: tuple[str, ...] = (
    EVENT_COUNTDOWN,
    EVENT_START,
    EVENT_CHECKPOINT,
    EVENT_LEAD_CHANGE,
    EVENT_JUMP,
    EVENT_COLLISION,
    EVENT_RECOVERY,
    EVENT_FINISH,
    EVENT_WINNER,
    EVENT_RETIRED,
    EVENT_COMPLETE,
)

# Why a recovery happened. Two causes, kept apart because they say different
# things about the course: a stuck racer found somewhere it could rest, an
# out-of-bounds racer found somewhere it could leave.
REASON_STUCK = "stuck"
REASON_OUT_OF_BOUNDS = "out_of_bounds"


@dataclass(frozen=True)
class RaceEvent:
    """One thing worth knowing about, stamped with the tick it happened on.

    Positions are logical course pixels. `value` is whatever number the
    event is about - a closing speed for a collision, a finish time for a
    finish, a checkpoint index for a crossing - and `detail` names the
    variant, so a reader has one shape to handle rather than eleven.
    """

    tick: int
    race_time: float
    type: str
    racer_id: int | None = None
    x: float | None = None
    y: float | None = None
    value: float | None = None
    detail: str | None = None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        label = self.type if self.detail is None else f"{self.type}/{self.detail}"
        who = "" if self.racer_id is None else f" racer={self.racer_id}"
        return f"<RaceEvent t={self.race_time:.2f} {label}{who}>"

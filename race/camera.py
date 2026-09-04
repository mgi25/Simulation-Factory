"""A vertical camera for a 9:16 frame.

Not the cinematic director - that is a later phase. This does one job well:
keep the part of the course that matters inside a portrait frame, and move
smoothly enough that a viewer can follow it.

Two decisions carry the whole thing. It follows the *leading group* rather
than the leader, because a camera locked to first place puts the racer
being overtaken off the bottom of the frame - and the overtake is the shot.
And it never moves back up the course: a race runs downhill, so a camera
that follows a racer thrown backwards by a spinner would jerk against the
direction of travel for one racer's sake while the field runs off the
bottom.
"""

from __future__ import annotations

from race.course import RaceCourse
from race.racer import Racer

__all__ = ["RaceCamera", "FOCUS_GROUP", "LEAD_FRACTION", "FOLLOW_RATE"]

# How many of the leading racers the camera averages over.
FOCUS_GROUP = 3
# Where the focus point sits in the frame, as a fraction from the top. Above
# centre, so more of the course ahead is visible than behind - a viewer
# wants to see what the leaders are about to hit.
LEAD_FRACTION = 0.42
# Exponential follow rate, per second. The camera closes this fraction of
# the remaining distance every second: high enough to keep up with a racer
# at the speed cap, low enough that a single collision does not snap it.
FOLLOW_RATE = 6.0
# Below this, the camera is treated as already there. Stops it creeping by
# fractions of a pixel forever, which reads as a slow drift.
SETTLE_EPSILON = 0.5


class RaceCamera:
    """Tracks the leading group down the course inside a portrait viewport."""

    def __init__(
        self,
        course: RaceCourse,
        viewport_height: float,
        viewport_width: float | None = None,
    ) -> None:
        self.course = course
        self.viewport_height = viewport_height
        self.viewport_width = course.width if viewport_width is None else viewport_width
        self.y = self._clamp(course.top)
        self._target = self.y

    # --- framing ---

    @property
    def top(self) -> float:
        """Course y at the top edge of the frame."""
        return self.y

    @property
    def bottom(self) -> float:
        return self.y + self.viewport_height

    @property
    def travel(self) -> float:
        """How far the camera can move: zero if the course fits in one frame."""
        return max(0.0, self.course.height - self.viewport_height)

    def _clamp(self, top: float) -> float:
        return min(max(top, self.course.top), self.course.top + self.travel)

    def visible(self, y: float, margin: float = 0.0) -> bool:
        """Whether a course height is inside the frame, plus a margin."""
        return self.top - margin <= y <= self.bottom + margin

    # --- following ---

    def focus(self, racers: list[Racer]) -> float:
        """The course height the camera wants centred on `LEAD_FRACTION`.

        The average of the leading group, by rank rather than by height: a
        racer that has fallen into the jump pit is lower down the course
        than the leaders but is not leading, and framing on it would drag
        the camera past the action.
        """
        in_play = [racer for racer in racers if not racer.retired]
        if not in_play:
            return self._target
        leaders = sorted(in_play, key=lambda racer: racer.rank)[:FOCUS_GROUP]
        return sum(racer.position.y for racer in leaders) / len(leaders)

    def update(self, racers: list[Racer], dt: float) -> float:
        """Ease the frame towards the leading group. Returns the new top."""
        wanted = self._clamp(self.focus(racers) - self.viewport_height * LEAD_FRACTION)
        # Downhill only. The clamp above already stops it running off the
        # end of the course; this stops it running back up the course.
        self._target = max(self._target, wanted)

        gap = self._target - self.y
        if abs(gap) <= SETTLE_EPSILON:
            self.y = self._target
            return self.y

        # Exponential easing on a fixed step: frame-rate independent, and it
        # cannot overshoot however large dt gets, which a spring would.
        self.y += gap * min(1.0, FOLLOW_RATE * max(0.0, dt))
        return self.y

    def snap_to(self, racers: list[Racer]) -> float:
        """Jump straight to the framing, with no easing. Used on a reset."""
        self._target = self._clamp(
            self.focus(racers) - self.viewport_height * LEAD_FRACTION
        )
        self.y = self._target
        return self.y

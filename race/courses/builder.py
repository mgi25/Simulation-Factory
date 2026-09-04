"""Scratch pad a course builder assembles a `RaceCourse` on.

It exists so a course description reads as geometry rather than as
bookkeeping: the builder hands out piece ids, remembers which section is
being laid down, and offers the handful of shapes a course is actually made
of. Nothing here decides anything about a course - it is all recording.
"""

from __future__ import annotations

import math

from engine.arena_layout import ObstacleSpec
from race.course import (
    BOUNCY,
    ROLE_GATE,
    ROLE_JUMP_PAD,
    ROLE_PEG,
    ROLE_RAMP,
    ROLE_WALL,
    TRACK,
    Checkpoint,
    CoursePiece,
    CourseSection,
    Material,
    RaceCourse,
    RacerSpawn,
    SpinnerSpec,
    box_between,
)

Point = tuple[float, float]

__all__ = ["CourseBuilder", "curve_points"]


def curve_points(
    start: Point, end: Point, segments: int, bulge: float = 2.0
) -> tuple[Point, ...]:
    """Points along a curve from `start` to `end`, for a chain of boxes.

    `y` is spaced evenly; `x` follows `1 - (1 - t) ** bulge`, which moves
    early and flattens out at the end. For a funnel wall that means a wide,
    shallow mouth narrowing to a vertical throat - the shape that lets
    gravity, rather than a shove, push a queue through the exit. `bulge` of
    1.0 gives a straight cone.
    """
    if segments < 1:
        raise ValueError("a curve needs at least one segment")
    (x1, y1), (x2, y2) = start, end
    points = []
    for step in range(segments + 1):
        t = step / segments
        shaped = 1.0 - (1.0 - t) ** bulge
        points.append((x1 + (x2 - x1) * shaped, y1 + (y2 - y1) * t))
    return tuple(points)


class CourseBuilder:
    """Collects pieces, spinners, checkpoints, spawns and sections."""

    def __init__(self, course_id: str, width: float, top: float) -> None:
        self.course_id = course_id
        self.width = width
        self.top = top
        self.section = ""
        self._pieces: list[CoursePiece] = []
        self._spinners: list[SpinnerSpec] = []
        self._checkpoints: list[Checkpoint] = []
        self._spawns: list[RacerSpawn] = []
        self._sections: list[CourseSection] = []
        self._next_piece_id = 0
        self._next_spinner_id = 0
        # Main-line planes laid down so far. The progress scale a linear
        # course numbers itself on, and the integer grid a split's branch
        # values sit between.
        self._stages = 0

    # --- sections ---

    def begin_section(self, name: str, top: float) -> None:
        """Name the stretch of course everything after this belongs to."""
        self._close_section(top)
        self._sections.append(CourseSection(name, top, top))
        self.section = name

    def _close_section(self, bottom: float) -> None:
        if self._sections:
            open_section = self._sections[-1]
            self._sections[-1] = CourseSection(
                open_section.name, open_section.top, bottom
            )

    # --- pieces ---

    def _add(self, spec: ObstacleSpec, role: str, material: Material, **extra) -> CoursePiece:
        piece = CoursePiece(
            spec=spec, role=role, material=material, section=self.section, **extra
        )
        self._pieces.append(piece)
        return piece

    def _piece_id(self) -> int:
        piece_id = self._next_piece_id
        self._next_piece_id += 1
        return piece_id

    def ramp(
        self,
        start: Point,
        end: Point,
        thickness: float,
        material: Material = TRACK,
        role: str = ROLE_RAMP,
    ) -> CoursePiece:
        """A straight surface between two points."""
        return self._add(
            box_between(self._piece_id(), start, end, thickness), role, material
        )

    def wall(self, start: Point, end: Point, thickness: float) -> CoursePiece:
        """Course boundary. Same shape as a ramp; different role and material."""
        return self.ramp(start, end, thickness, TRACK, ROLE_WALL)

    def chain(
        self,
        points: tuple[Point, ...],
        thickness: float,
        material: Material = TRACK,
        role: str = ROLE_RAMP,
    ) -> tuple[CoursePiece, ...]:
        """A run of boxes through consecutive points.

        Neighbouring boxes overlap at each joint because both are centred on
        their own segment, so a chain has no seam a racer could squeeze
        through however sharply it turns.
        """
        return tuple(
            self.ramp(start, end, thickness, material, role)
            for start, end in zip(points, points[1:])
        )

    def peg(self, x: float, y: float, radius: float, material: Material = BOUNCY) -> CoursePiece:
        """A round scatterer."""
        return self._add(
            ObstacleSpec.circle(self._piece_id(), x, y, radius), ROLE_PEG, material
        )

    def gate(self, start: Point, end: Point, thickness: float) -> CoursePiece:
        """The starting gate: solid until the countdown ends, then removed."""
        return self.ramp(start, end, thickness, TRACK, ROLE_GATE)

    def jump_pad(
        self,
        start: Point,
        end: Point,
        thickness: float,
        impulse_angle: float,
        impulse: float,
        jitter: float = 0.0,
        material: Material = TRACK,
    ) -> CoursePiece:
        """A kicker plate.

        `impulse_angle` is degrees from straight up, positive towards +x, so
        a pad is described the way it reads on screen - "a bit forward of
        vertical" - rather than as a vector to be checked against a diagram.
        """
        radians = math.radians(impulse_angle)
        vector = (math.sin(radians) * impulse, -math.cos(radians) * impulse)
        return self._add(
            box_between(self._piece_id(), start, end, thickness),
            ROLE_JUMP_PAD,
            material,
            impulse=vector,
            impulse_jitter=jitter,
        )

    def spinner(
        self,
        x: float,
        y: float,
        hub_radius: float,
        arm_count: int,
        arm_length: float,
        arm_thickness: float,
        angular_speed: float,
        start_angle: float = 0.0,
    ) -> SpinnerSpec:
        spec = SpinnerSpec(
            spinner_id=self._next_spinner_id,
            x=x,
            y=y,
            hub_radius=hub_radius,
            arm_count=arm_count,
            arm_length=arm_length,
            arm_thickness=arm_thickness,
            angular_speed=angular_speed,
            start_angle=start_angle,
            section=self.section,
        )
        self._next_spinner_id += 1
        self._spinners.append(spec)
        return spec

    # --- ladder and grid ---

    def checkpoint(self, name: str, y: float, respawn: Point) -> Checkpoint:
        """A plane every racer crosses, one rung further along the course.

        Its course progress is the number of main-line planes laid down
        before it, so a course with no branches numbers itself 0, 1, 2 ...
        and needs to know nothing about the progress scale at all.
        """
        return self._checkpoint(name, y, respawn, "", None, None, float(self._stages))

    def branch_checkpoint(
        self,
        name: str,
        y: float,
        respawn: Point,
        *,
        branch: str,
        x_range: tuple[float | None, float | None],
        progress: float,
    ) -> Checkpoint:
        """A plane only racers in one corridor of a split can cross.

        `x_range` is the corridor, as `(x_min, x_max)` with either end left
        open by `None`. It is what separates one path from the other, and a
        branch node without one would be reachable from both.

        `progress` is stated rather than counted, because a branch
        subdivides the interval between two main-line planes and only the
        course knows how. Every branch of one split must enter at the same
        value - two racers taking different paths have to start level - and
        the interval belongs to the split, so the values are part of how
        the course is laid out rather than something a builder can infer.
        """
        if not branch:
            raise ValueError("a branch checkpoint needs a branch name")
        return self._checkpoint(
            name, y, respawn, branch, x_range[0], x_range[1], progress
        )

    def _checkpoint(
        self,
        name: str,
        y: float,
        respawn: Point,
        branch: str,
        x_min: float | None,
        x_max: float | None,
        progress: float,
    ) -> Checkpoint:
        checkpoint = Checkpoint(
            index=len(self._checkpoints),
            name=name,
            y=y,
            respawn=respawn,
            branch=branch,
            x_min=x_min,
            x_max=x_max,
            progress=progress,
        )
        self._checkpoints.append(checkpoint)
        if not branch:
            self._stages += 1
        return checkpoint

    def spawn(self, x: float, y: float) -> RacerSpawn:
        spawn = RacerSpawn(slot=len(self._spawns), x=x, y=y)
        self._spawns.append(spawn)
        return spawn

    # --- result ---

    def finish(self, bottom: float, **metadata: float) -> RaceCourse:
        self._close_section(bottom)
        return RaceCourse(
            course_id=self.course_id,
            width=self.width,
            top=self.top,
            bottom=bottom,
            pieces=tuple(self._pieces),
            spinners=tuple(self._spinners),
            checkpoints=tuple(self._checkpoints),
            spawns=tuple(self._spawns),
            sections=tuple(self._sections),
            metadata=dict(metadata),
        )

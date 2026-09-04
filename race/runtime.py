"""Turning course data into things that exist in the physics space.

`race.course` says what a course is; this is what stands in Pymunk while a
race runs. Two kinds of thing live here.

Static pieces are shapes hung on the space's static body - the same
technique `engine.obstacle_runtime` uses for arena furniture - with one
addition a duel never needed: each piece carries its own material, so a
slick funnel wall and a bouncy peg are genuinely different surfaces rather
than the same surface drawn differently.

A spinner is a single kinematic body carrying its hub and all of its arms.
Kinematic because Chipmunk reads a body velocity when it resolves a
contact, which is what lets an arm shove a racer instead of behaving like a
wall that happens to have moved; and one body rather than one per arm
because the arms have to stay rigid with respect to each other, which no
amount of matched angular velocities would guarantee.
"""

from __future__ import annotations

import math

import pymunk

from race.config import (
    COLLISION_TYPE_GATE,
    COLLISION_TYPE_JUMP_PAD,
    COLLISION_TYPE_SPINNER,
    COLLISION_TYPE_TRACK,
)
from race.course import CoursePiece, RaceCourse, SpinnerSpec

__all__ = ["PieceRuntime", "SpinnerRuntime", "TrackRuntime"]


def _collision_type(piece: CoursePiece) -> int:
    if piece.is_jump_pad:
        return COLLISION_TYPE_JUMP_PAD
    if piece.is_gate:
        return COLLISION_TYPE_GATE
    return COLLISION_TYPE_TRACK


class PieceRuntime:
    """One static course piece, present in the space."""

    def __init__(self, piece: CoursePiece, space: pymunk.Space) -> None:
        self.piece = piece
        spec = piece.spec
        body = space.static_body
        if spec.is_circle:
            self.shape: pymunk.Shape = pymunk.Circle(
                body, spec.radius, offset=spec.center
            )
        else:
            # Built from the same `corners()` the course measures its
            # clearances with, so a ramp is physically where the data says.
            self.shape = pymunk.Poly(body, spec.corners())
        self.shape.elasticity = piece.material.elasticity
        self.shape.friction = piece.material.friction
        self.shape.collision_type = _collision_type(piece)
        space.add(self.shape)
        self._space: pymunk.Space | None = space

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<PieceRuntime {self.piece.role} id={self.piece.piece_id}>"

    @property
    def present(self) -> bool:
        return self._space is not None

    def remove(self) -> None:
        """Take the piece out of the space. Idempotent; used by the gate."""
        if self._space is None:
            return
        self._space.remove(self.shape)
        self._space = None


class SpinnerRuntime:
    """A hub and its arms on one kinematic body, turning at a constant rate."""

    def __init__(self, spec: SpinnerSpec, space: pymunk.Space) -> None:
        self.spec = spec
        self.body = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
        self.body.position = spec.center
        self.body.angle = math.radians(spec.start_angle)
        # Set once. A constant angular velocity integrates to exactly the
        # angle `SpinnerSpec.arm_angles` describes, so nothing has to be
        # corrected per tick and the data and the physics cannot disagree.
        self.body.angular_velocity = math.radians(spec.angular_speed)

        self.shapes: list[pymunk.Shape] = [pymunk.Circle(self.body, spec.hub_radius)]
        self.arm_shapes: list[pymunk.Poly] = [
            pymunk.Poly(self.body, corners) for corners in self._arm_corners()
        ]
        self.shapes.extend(self.arm_shapes)
        for shape in self.shapes:
            shape.elasticity = spec.material.elasticity
            shape.friction = spec.material.friction
            shape.collision_type = COLLISION_TYPE_SPINNER
        space.add(self.body, *self.shapes)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<SpinnerRuntime id={self.spec.spinner_id} arms={self.spec.arm_count}>"

    def _arm_corners(self) -> list[tuple[tuple[float, float], ...]]:
        """Each arm as body-local corners, spaced evenly around the hub.

        Local rather than world: the body angle already carries the start
        angle and every later rotation, so an arm is described once, at
        rest, and never recomputed.
        """
        length, thickness, distance = self.spec.arm_local_box()
        half_length, half_thickness = length / 2.0, thickness / 2.0
        step = 360.0 / self.spec.arm_count
        corners = []
        for index in range(self.spec.arm_count):
            angle = math.radians(index * step)
            cos_a, sin_a = math.cos(angle), math.sin(angle)
            offset_x, offset_y = distance * cos_a, distance * sin_a
            corners.append(
                tuple(
                    (
                        offset_x + lx * cos_a - ly * sin_a,
                        offset_y + lx * sin_a + ly * cos_a,
                    )
                    for lx, ly in (
                        (-half_length, -half_thickness),
                        (half_length, -half_thickness),
                        (half_length, half_thickness),
                        (-half_length, half_thickness),
                    )
                )
            )
        return corners

    # --- read-only views for the renderer ---

    @property
    def spinner_id(self) -> int:
        return self.spec.spinner_id

    @property
    def rotation_degrees(self) -> float:
        return math.degrees(self.body.angle)

    def arm_polygons(self) -> tuple[tuple[tuple[float, float], ...], ...]:
        """Every arm world-space corners, at this tick transform.

        Taken from the live body rather than evaluated from the spec, for
        the same reason the duel exports a moving obstacle transform per
        frame: what is drawn should be where the thing actually is.
        """
        return tuple(
            tuple(
                (point.x, point.y)
                for point in (
                    self.body.local_to_world(vertex) for vertex in shape.get_vertices()
                )
            )
            for shape in self.arm_shapes
        )

    def is_finite(self) -> bool:
        return all(
            math.isfinite(value)
            for value in (self.body.position.x, self.body.position.y, self.body.angle)
        )


class TrackRuntime:
    """The whole course, standing in one space.

    Also the lookup a collision callback needs: given the shape a racer
    touched, which piece was it? Built once here rather than searched for
    per contact.
    """

    def __init__(self, course: RaceCourse, space: pymunk.Space) -> None:
        self.course = course
        self.pieces = [PieceRuntime(piece, space) for piece in course.pieces]
        self.spinners = [SpinnerRuntime(spec, space) for spec in course.spinners]
        self.piece_by_shape: dict[pymunk.Shape, CoursePiece] = {
            runtime.shape: runtime.piece for runtime in self.pieces
        }
        self.gates = [runtime for runtime in self.pieces if runtime.piece.is_gate]

    def open_gates(self) -> int:
        """Remove every starting gate. Returns how many were still present."""
        opened = 0
        for runtime in self.gates:
            if runtime.present:
                runtime.remove()
                opened += 1
        return opened

    @property
    def gates_open(self) -> bool:
        return not any(runtime.present for runtime in self.gates)

    def is_finite(self) -> bool:
        return all(spinner.is_finite() for spinner in self.spinners)

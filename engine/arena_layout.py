"""Static arena geometry as plain data.

An `ArenaLayout` is the authoritative description of everything static in an
arena beyond its four walls. It is deliberately data-only: no Pymunk shapes,
no space, no rendering state. The simulation turns it into static bodies, the
replay serialises it verbatim, and a renderer rebuilds the same geometry from
the replay without ever knowing which generator produced it.

The distance helpers live here rather than in the generator because the
generator, the simulation and the tests all have to agree on exactly what
"these two obstacles are 40 pixels apart" means.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids an import cycle
    from engine.arena import Arena

# Layout kinds. `classic` is the empty rectangular arena every phase up to
# 5A1 used, and stays the control environment for deterministic regression
# tests; `procedural` is generated from a seed.
LAYOUT_CLASSIC = "classic"
LAYOUT_PROCEDURAL = "procedural"
LAYOUT_TYPES: tuple[str, ...] = (LAYOUT_CLASSIC, LAYOUT_PROCEDURAL)

# The two static primitives this phase supports. Both are immovable, elastic
# and harmless: they change where things bounce and nothing else.
OBSTACLE_CIRCLE = "circle"
OBSTACLE_BOX = "box"
OBSTACLE_KINDS: tuple[str, ...] = (OBSTACLE_CIRCLE, OBSTACLE_BOX)

# Continues the numbering in `entities.ball` (ball 1, wall 2) and
# `entities.dynamic_entity` (3). Obstacles get their own collision type
# rather than reusing the wall's, so a contact report can say which of the
# two was touched even though gameplay currently treats them the same way.
COLLISION_TYPE_OBSTACLE = 4

# Same conservative material as the arena walls: a perfectly elastic,
# frictionless bounce that neither drains the simulation nor injects energy
# into it.
OBSTACLE_ELASTICITY = 1.0
OBSTACLE_FRICTION = 0.0


@dataclass(frozen=True)
class ObstacleSpec:
    """One static obstacle, in logical simulation pixels.

    A single record covers both primitives: a circle reads `radius`, a box
    reads `width`, `height` and `rotation_degrees`, and the unused fields
    stay at zero. That keeps the replay one flat shape per obstacle instead
    of a tagged union a renderer has to probe.
    """

    obstacle_id: int
    kind: str
    x: float
    y: float
    radius: float = 0.0
    width: float = 0.0
    height: float = 0.0
    rotation_degrees: float = 0.0

    @classmethod
    def circle(
        cls, obstacle_id: int, x: float, y: float, radius: float
    ) -> "ObstacleSpec":
        return cls(
            obstacle_id=obstacle_id,
            kind=OBSTACLE_CIRCLE,
            x=float(x),
            y=float(y),
            radius=float(radius),
        )

    @classmethod
    def box(
        cls,
        obstacle_id: int,
        x: float,
        y: float,
        width: float,
        height: float,
        rotation_degrees: float = 0.0,
    ) -> "ObstacleSpec":
        return cls(
            obstacle_id=obstacle_id,
            kind=OBSTACLE_BOX,
            x=float(x),
            y=float(y),
            width=float(width),
            height=float(height),
            rotation_degrees=float(rotation_degrees),
        )

    # --- geometry ---

    @property
    def is_circle(self) -> bool:
        return self.kind == OBSTACLE_CIRCLE

    @property
    def center(self) -> tuple[float, float]:
        return (self.x, self.y)

    @property
    def bounding_radius(self) -> float:
        """Radius of the smallest circle centred here that covers the shape."""
        if self.is_circle:
            return self.radius
        return math.hypot(self.width, self.height) / 2.0

    def corners(self) -> tuple[tuple[float, float], ...]:
        """The four world-space corners of a box, in order. Empty for a circle.

        This is the single definition of where a rotated bar actually is: the
        Pymunk polygon, the clearance checks and the tests are all derived
        from it, so they cannot disagree about a 45 degree bar.
        """
        if self.is_circle:
            return ()
        angle = math.radians(self.rotation_degrees)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        hw, hh = self.width / 2.0, self.height / 2.0
        return tuple(
            (self.x + lx * cos_a - ly * sin_a, self.y + lx * sin_a + ly * cos_a)
            for lx, ly in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh))
        )

    def bounds(self) -> tuple[float, float, float, float]:
        """Axis-aligned bounding box as (left, top, right, bottom)."""
        if self.is_circle:
            return (
                self.x - self.radius,
                self.y - self.radius,
                self.x + self.radius,
                self.y + self.radius,
            )
        corners = self.corners()
        xs = [px for px, _ in corners]
        ys = [py for _, py in corners]
        return (min(xs), min(ys), max(xs), max(ys))

    def distance_to_point(self, px: float, py: float) -> float:
        """Distance from this obstacle's surface to a point; 0.0 when inside."""
        return max(0.0, self.signed_distance_to_point(px, py))

    def signed_distance_to_point(self, px: float, py: float) -> float:
        """Like `distance_to_point`, but negative for a point inside."""
        if self.is_circle:
            return math.dist((self.x, self.y), (px, py)) - self.radius

        # Measured in the box's own frame, where the nearest surface point is
        # simply the point clamped to the half-extents.
        angle = math.radians(self.rotation_degrees)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        dx, dy = px - self.x, py - self.y
        local_x = dx * cos_a + dy * sin_a
        local_y = -dx * sin_a + dy * cos_a
        over_x = abs(local_x) - self.width / 2.0
        over_y = abs(local_y) - self.height / 2.0
        if over_x <= 0.0 and over_y <= 0.0:
            return max(over_x, over_y)
        return math.hypot(max(over_x, 0.0), max(over_y, 0.0))

    def clearance_to_circle(self, px: float, py: float, radius: float) -> float:
        """Gap between this obstacle and a circle; negative when they overlap."""
        return self.signed_distance_to_point(px, py) - radius

    def clearance_to(self, other: "ObstacleSpec") -> float:
        """Gap between two obstacles' surfaces; 0.0 when they touch or overlap."""
        if other.is_circle:
            return max(0.0, self.clearance_to_circle(other.x, other.y, other.radius))
        if self.is_circle:
            return max(0.0, other.clearance_to_circle(self.x, self.y, self.radius))
        return _polygon_gap(self.corners(), other.corners())

    def clearance_to_bounds(self, arena: "Arena") -> float:
        """Smallest gap to any arena wall; negative when it pokes through one."""
        left, top, right, bottom = self.bounds()
        return min(
            left - arena.left,
            arena.right - right,
            top - arena.top,
            arena.bottom - bottom,
        )


@dataclass(frozen=True)
class ArenaLayout:
    """Everything static in an arena, beyond the four walls."""

    layout_id: str
    layout_type: str
    obstacles: tuple[ObstacleSpec, ...] = ()
    # How many obstacles the generator set out to place. A layout that had to
    # settle for fewer is still perfectly valid - it just says so, rather
    # than claiming a complete procedural layout it did not manage to build.
    requested_obstacles: int = 0

    @classmethod
    def classic(cls) -> "ArenaLayout":
        """The empty rectangular arena: the control environment."""
        return cls(layout_id=LAYOUT_CLASSIC, layout_type=LAYOUT_CLASSIC)

    @property
    def is_empty(self) -> bool:
        return not self.obstacles

    @property
    def fallback(self) -> bool:
        """True when generation had to place fewer obstacles than it wanted."""
        return len(self.obstacles) < self.requested_obstacles

    def __len__(self) -> int:
        return len(self.obstacles)

    def __iter__(self):
        return iter(self.obstacles)


def layout_id_for(layout_type: str, seed: int) -> str:
    """Deterministic, human-readable layout identifier - never a random UUID."""
    return f"{layout_type}-{seed}"


# --- convex geometry helpers -------------------------------------------------


def _polygon_gap(
    a: Iterable[tuple[float, float]], b: Iterable[tuple[float, float]]
) -> float:
    """Smallest distance between two convex polygons; 0.0 when they intersect."""
    poly_a, poly_b = tuple(a), tuple(b)
    if _polygons_intersect(poly_a, poly_b):
        return 0.0
    # For non-intersecting convex polygons the closest pair of points always
    # lies on a pair of edges, so checking every edge pair is exact.
    best = math.inf
    for i in range(len(poly_a)):
        seg_a = (poly_a[i], poly_a[(i + 1) % len(poly_a)])
        for j in range(len(poly_b)):
            seg_b = (poly_b[j], poly_b[(j + 1) % len(poly_b)])
            best = min(best, _segment_gap(seg_a, seg_b))
    return best


def _polygons_intersect(
    poly_a: tuple[tuple[float, float], ...], poly_b: tuple[tuple[float, float], ...]
) -> bool:
    """Separating-axis test over both polygons' edge normals."""
    for poly in (poly_a, poly_b):
        for i in range(len(poly)):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % len(poly)]
            axis = (-(y2 - y1), x2 - x1)
            a_lo, a_hi = _project(poly_a, axis)
            b_lo, b_hi = _project(poly_b, axis)
            if a_hi < b_lo or b_hi < a_lo:
                return False
    return True


def _project(
    poly: tuple[tuple[float, float], ...], axis: tuple[float, float]
) -> tuple[float, float]:
    values = [px * axis[0] + py * axis[1] for px, py in poly]
    return min(values), max(values)


def _segment_gap(
    seg_a: tuple[tuple[float, float], tuple[float, float]],
    seg_b: tuple[tuple[float, float], tuple[float, float]],
) -> float:
    """Distance between two segments known not to cross."""
    return min(
        _point_segment_distance(seg_a[0], seg_b),
        _point_segment_distance(seg_a[1], seg_b),
        _point_segment_distance(seg_b[0], seg_a),
        _point_segment_distance(seg_b[1], seg_a),
    )


def _point_segment_distance(
    point: tuple[float, float],
    segment: tuple[tuple[float, float], tuple[float, float]],
) -> float:
    (x1, y1), (x2, y2) = segment
    dx, dy = x2 - x1, y2 - y1
    length_sq = dx * dx + dy * dy
    if length_sq == 0.0:
        return math.dist(point, (x1, y1))
    t = ((point[0] - x1) * dx + (point[1] - y1) * dy) / length_sq
    t = min(1.0, max(0.0, t))
    return math.dist(point, (x1 + t * dx, y1 + t * dy))

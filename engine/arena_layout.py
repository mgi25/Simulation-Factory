"""Arena geometry as plain data, including how a moving obstacle moves.

An `ArenaLayout` is the authoritative description of everything in an arena
beyond its four walls. It is deliberately data-only: no Pymunk shapes, no
space, no rendering state. The simulation turns it into bodies, the replay
serialises it verbatim, and a renderer rebuilds the same geometry from the
replay without ever knowing which generator produced it.

The distance helpers live here rather than in the generator because the
generator, the simulation and the tests all have to agree on exactly what
"these two obstacles are 40 pixels apart" means.

A kinetic obstacle carries its motion here too - the definition of the path,
not a frame of it. The simulation is the only thing that evaluates it: a
renderer is handed the resulting transform every frame and never the formula,
so playback cannot drift from the battle that was simulated.
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

# The two geometric primitives. Both are elastic and harmless: they change
# where things bounce and nothing else, moving or not.
OBSTACLE_CIRCLE = "circle"
OBSTACLE_BOX = "box"
OBSTACLE_KINDS: tuple[str, ...] = (OBSTACLE_CIRCLE, OBSTACLE_BOX)

# How an obstacle moves, if it moves at all. Three named behaviours rather
# than a general animation model: each one is a couple of numbers the
# simulation knows how to evaluate, and adding a fourth should be a
# deliberate decision rather than a configuration change.
MOTION_STATIC = "static"
MOTION_ROTATE = "rotate"
MOTION_SLIDE = "slide"
MOTION_KINDS: tuple[str, ...] = (MOTION_STATIC, MOTION_ROTATE, MOTION_SLIDE)

# Which way a gate slides. Axis-aligned only: a diagonal path would sweep a
# far larger envelope for no gain in readability.
AXIS_X = "x"
AXIS_Y = "y"
SLIDE_AXES: tuple[str, ...] = (AXIS_X, AXIS_Y)

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
    """One obstacle's immutable definition, in logical simulation pixels.

    A single record covers both primitives and all three motions: a circle
    reads `radius`, a box reads `width`, `height` and `rotation_degrees`, a
    rotor reads `angular_speed`, a gate reads the `slide_*` fields, and every
    field a given obstacle does not use stays at zero. That keeps the replay
    one flat shape per obstacle instead of a tagged union a renderer has to
    probe.

    `x` and `y` are the obstacle's anchor, which is not always where it is:
    a static obstacle sits there, a rotor pivots about it, and a gate uses it
    as the midpoint of its travel. Where a moving obstacle actually is at a
    given moment is `position_at`, and the replay exports that per frame.
    """

    obstacle_id: int
    kind: str
    x: float
    y: float
    radius: float = 0.0
    width: float = 0.0
    height: float = 0.0
    rotation_degrees: float = 0.0

    motion: str = MOTION_STATIC
    # Rotors: signed degrees per simulated second. The sign is the direction.
    angular_speed: float = 0.0
    # Gates: an axis, the full end-to-end travel centred on the anchor, the
    # speed along it, and where in the there-and-back cycle it starts.
    slide_axis: str = ""
    slide_distance: float = 0.0
    slide_speed: float = 0.0
    slide_phase: float = 0.0

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

    @classmethod
    def rotor(
        cls,
        obstacle_id: int,
        x: float,
        y: float,
        width: float,
        height: float,
        angular_speed: float,
        rotation_degrees: float = 0.0,
    ) -> "ObstacleSpec":
        """A bar that turns about its own centre at a constant rate."""
        return cls(
            obstacle_id=obstacle_id,
            kind=OBSTACLE_BOX,
            x=float(x),
            y=float(y),
            width=float(width),
            height=float(height),
            rotation_degrees=float(rotation_degrees),
            motion=MOTION_ROTATE,
            angular_speed=float(angular_speed),
        )

    @classmethod
    def gate(
        cls,
        obstacle_id: int,
        x: float,
        y: float,
        width: float,
        height: float,
        axis: str,
        distance: float,
        speed: float,
        phase: float = 0.0,
        rotation_degrees: float = 0.0,
    ) -> "ObstacleSpec":
        """A bar that slides back and forth along one axis about `x, y`."""
        if axis not in SLIDE_AXES:
            raise ValueError(f"slide axis must be one of {SLIDE_AXES}, got {axis!r}")
        return cls(
            obstacle_id=obstacle_id,
            kind=OBSTACLE_BOX,
            x=float(x),
            y=float(y),
            width=float(width),
            height=float(height),
            rotation_degrees=float(rotation_degrees),
            motion=MOTION_SLIDE,
            slide_axis=axis,
            slide_distance=float(distance),
            slide_speed=float(speed),
            slide_phase=float(phase) % 1.0,
        )

    # --- motion ---

    @property
    def is_kinetic(self) -> bool:
        return self.motion != MOTION_STATIC

    @property
    def is_rotor(self) -> bool:
        return self.motion == MOTION_ROTATE

    @property
    def is_gate(self) -> bool:
        return self.motion == MOTION_SLIDE

    def slide_endpoints(self) -> tuple[tuple[float, float], tuple[float, float]]:
        """The two ends of a gate's travel, centred on its anchor."""
        if not self.is_gate:
            return (self.center, self.center)
        half = self.slide_distance / 2.0
        if self.slide_axis == AXIS_X:
            return ((self.x - half, self.y), (self.x + half, self.y))
        return ((self.x, self.y - half), (self.x, self.y + half))

    def slide_offset_at(self, seconds: float) -> float:
        """Distance travelled from the first endpoint, as a triangle wave.

        Continuous everywhere: the gate decelerates through no endpoint but
        it never jumps either - at a turn the offset simply starts coming
        back down the same path it went up.
        """
        if not self.is_gate or self.slide_distance <= 0.0:
            return 0.0
        cycle = 2.0 * self.slide_distance
        travelled = (self.slide_phase * cycle + self.slide_speed * seconds) % cycle
        return travelled if travelled <= self.slide_distance else cycle - travelled

    def position_at(self, seconds: float) -> tuple[float, float]:
        """Where this obstacle's centre is after `seconds` of simulated time."""
        if not self.is_gate:
            return self.center
        start, _ = self.slide_endpoints()
        offset = self.slide_offset_at(seconds)
        if self.slide_axis == AXIS_X:
            return (start[0] + offset, start[1])
        return (start[0], start[1] + offset)

    def rotation_at(self, seconds: float) -> float:
        """This obstacle's angle in degrees after `seconds` of simulated time."""
        if not self.is_rotor:
            return self.rotation_degrees
        return self.rotation_degrees + self.angular_speed * seconds

    def at(self, x: float, y: float, rotation_degrees: float) -> "ObstacleSpec":
        """This obstacle's geometry placed somewhere else, motion stripped.

        Used to ask geometric questions about a moving obstacle at one
        instant: the result is a plain static shape, so every existing
        distance helper applies to it unchanged.
        """
        return ObstacleSpec(
            obstacle_id=self.obstacle_id,
            kind=self.kind,
            x=float(x),
            y=float(y),
            radius=self.radius,
            width=self.width,
            height=self.height,
            rotation_degrees=float(rotation_degrees),
        )

    def placed_at(self, seconds: float) -> "ObstacleSpec":
        """This obstacle's geometry at one moment of its motion."""
        x, y = self.position_at(seconds)
        return self.at(x, y, self.rotation_at(seconds))

    def envelope(self) -> "ObstacleSpec":
        """A static shape covering everywhere this obstacle ever reaches.

        Generation validates the envelope rather than the starting pose, so a
        rotor cannot sweep through a wall it happened to start clear of and a
        gate cannot slide into a fighter's spawn halfway along its travel.
        Conservative by construction: a rotor becomes the circle it turns
        inside, and a gate becomes its own bounding box stretched along its
        axis by the full travel.
        """
        if self.is_rotor:
            return ObstacleSpec.circle(
                self.obstacle_id, self.x, self.y, self.bounding_radius
            )
        if self.is_gate:
            left, top, right, bottom = self.at(
                self.x, self.y, self.rotation_degrees
            ).bounds()
            width, height = right - left, bottom - top
            if self.slide_axis == AXIS_X:
                width += self.slide_distance
            else:
                height += self.slide_distance
            return ObstacleSpec.box(self.obstacle_id, self.x, self.y, width, height)
        return self

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
    def kinetic(self) -> tuple[ObstacleSpec, ...]:
        """The obstacles that move, in layout order."""
        return tuple(obstacle for obstacle in self.obstacles if obstacle.is_kinetic)

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

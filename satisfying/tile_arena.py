"""The segmented arena: a regular 16-gon whose 48 wall tiles are the progress bar.

Geometry only. Nothing here moves, nothing here holds simulation state, and
nothing here knows a ball exists. `satisfying.tile_escape` owns the state, and
keeping the two apart is what lets a test assert "48 tiles, each with a stable
identity" without running a physics run at all.

## Why a polygon and not concentric rings

The reference channel draws thin concentric circles. That look costs a viewer a
beat to parse - are those rings walls, or a target, or a countdown - and it does
not say where the ball can go. A single convex polygon says it immediately: this
is a room, the ball is inside it, the walls are the things being lit. The
segmentation is then honest rather than decorative, because each drawn segment
really is one independently activatable collision surface.

16 sides x 3 tiles per side = 48 tiles. Three tiles per side is the most that
still leaves each tile clearly longer than the ball is wide, which is what makes
a hit unambiguous to the eye as well as to the code. Sixteen sides read as a
polygon while the arena is dark - the captures in
`docs/validation/category3_tile_escape/` show the flats plainly at 1080x1920 -
and round off towards a ring as tiles light up, because a lit tile is drawn with
a glow and sixteen glows in a circle are a circle. So the shape distinguishes
this from the reference channel at the start of a run and the *single segmented
wall* does it for the rest.

## An even number of sides has a cost, and Phase 1 measured it

A regular polygon with an even number of sides has parallel opposite sides, and
two parallel walls admit an exactly periodic orbit: a ball travelling
perpendicular to them bounces between the same two tiles for ever. At 16 sides
that orbit is real and reachable - seed 134 of the zero-gravity sweep spends 34
consecutive collisions and 10.6 seconds alternating between `tile_01` on the
floor and `tile_25` on the ceiling, and leaves only because floating-point drift
eventually walks the contact point onto a neighbour. Escaping by rounding error
is not escaping.

17 sides has no parallel pair and no such orbit: over the same 300 seeds the
longest two-tile stretch falls from 34 collisions to 3, which is the minimum a
ball can produce legitimately. 17 x 3 = 51 tiles, within the brief's
approximate density. The default here stays at the 16 the brief specified; the
recommendation is in `docs/category3_tile_escape_phase1.md`, because Phase 1's
job was to find this, not to act on it.

## The one geometric trick

The arena is convex, so the region the ball's *centre* may occupy is exactly the
same polygon inset by the ball radius - the intersection of the sixteen
half-planes `dot(p, u_k) <= apothem - ball_radius`, where `u_k` is side k's
outward unit normal. No corner rounding, no special case at a vertex: a corner
of the inset polygon is where two inset lines meet and the ball is touching both
sides at once. That is the whole reason `tile_escape` can solve collisions
exactly instead of stepping a solver and hoping.

So this module publishes, for each side, one outward unit normal and one
distance (the apothem), and for each tile the two endpoints of its segment and
which side it belongs to. Everything the physics needs is in those numbers.

## Which tile was hit

`tile_for_contact` takes a side and the contact point and projects it onto that
side, 0 at vertex k and 1 at vertex k+1. Slot 0, 1 or 2 follows from the thirds.
Contact points arrive exactly on the side line, so the projection is in [0, 1]
up to floating-point noise, and the clamp is there for the noise and not for a
geometric case it is hiding.

Tiles are numbered `side * tiles_per_side + slot`, counter-clockwise from the
floor. At 16 sides, side 0 is the flat floor and side 8 the flat ceiling: the
default orientation puts a side, not a vertex, at the bottom, because a ball
settling into a corner at the bottom of the frame is the one stagnation mode
this experiment cannot afford to build in by accident. With an odd number of
sides there is a flat floor and a vertex at the top instead.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = [
    "Tile",
    "Arena",
    "polygon_arena",
    "DEFAULT_SIDES",
    "DEFAULT_TILES_PER_SIDE",
    "DEFAULT_CIRCUMRADIUS",
]

DEFAULT_SIDES = 16
DEFAULT_TILES_PER_SIDE = 3
DEFAULT_CIRCUMRADIUS = 10.0

Point = tuple[float, float]


@dataclass(frozen=True)
class Tile:
    """One independently activatable wall segment.

    `index` and `tile_id` are the identity: assigned once when the arena is
    built, never reassigned, and derived from the geometry rather than from the
    order anything happened to be hit in.
    """

    index: int
    tile_id: str
    side: int
    slot: int
    start: Point
    end: Point
    midpoint: Point
    outward_normal: Point
    length: float


@dataclass(frozen=True)
class Arena:
    """A regular convex polygon, its sides, and the tiles those sides carry."""

    sides: int
    tiles_per_side: int
    circumradius: float
    apothem: float
    orientation: float
    vertices: tuple[Point, ...]
    side_outward_normals: tuple[Point, ...]
    tiles: tuple[Tile, ...]

    @property
    def total_tiles(self) -> int:
        return len(self.tiles)

    @property
    def side_length(self) -> float:
        return 2.0 * self.circumradius * math.sin(math.pi / self.sides)

    @property
    def tile_length(self) -> float:
        return self.side_length / self.tiles_per_side

    def tile(self, index: int) -> Tile:
        return self.tiles[index]

    def side_offset(self, point: Point, side: int) -> float:
        """How far outside side `side`'s wall line the point is. Negative inside."""
        nx, ny = self.side_outward_normals[side]
        return point[0] * nx + point[1] * ny - self.apothem

    def clearance(self, point: Point) -> float:
        """Distance from the point to the nearest wall line. Negative if outside."""
        return -max(self.side_offset(point, k) for k in range(self.sides))

    def contains(self, point: Point, margin: float = 0.0) -> bool:
        """Is the point inside every wall line, with `margin` to spare?"""
        return self.clearance(point) >= margin

    def tile_for_contact(self, side: int, contact: Point) -> Tile:
        """Which of side `side`'s tiles the contact point lies on."""
        ax, ay = self.vertices[side]
        bx, by = self.vertices[(side + 1) % self.sides]
        dx, dy = bx - ax, by - ay
        span = dx * dx + dy * dy
        along = ((contact[0] - ax) * dx + (contact[1] - ay) * dy) / span
        # The clamp absorbs floating-point noise at a vertex, where `along` can
        # land a few 1e-16 outside [0, 1]. It is not covering a geometric case.
        along = min(1.0, max(0.0, along))
        slot = min(self.tiles_per_side - 1, int(along * self.tiles_per_side))
        return self.tiles[side * self.tiles_per_side + slot]


def polygon_arena(
    sides: int = DEFAULT_SIDES,
    tiles_per_side: int = DEFAULT_TILES_PER_SIDE,
    circumradius: float = DEFAULT_CIRCUMRADIUS,
    orientation: float | None = None,
) -> Arena:
    """Build a regular polygonal arena with `sides * tiles_per_side` tiles.

    `orientation` is the angle of vertex 0. The default puts the midpoint of
    side 0 at straight down, so the arena has a flat floor and a flat ceiling.
    """
    if sides < 3:
        raise ValueError(f"an arena needs at least 3 sides, got {sides}")
    if tiles_per_side < 1:
        raise ValueError(f"a side needs at least 1 tile, got {tiles_per_side}")
    if circumradius <= 0.0:
        raise ValueError(f"circumradius must be positive, got {circumradius}")

    step = 2.0 * math.pi / sides
    if orientation is None:
        orientation = -math.pi / 2.0 - step / 2.0

    vertices = tuple(
        (
            circumradius * math.cos(orientation + step * k),
            circumradius * math.sin(orientation + step * k),
        )
        for k in range(sides)
    )
    normals = tuple(
        (
            math.cos(orientation + step * (k + 0.5)),
            math.sin(orientation + step * (k + 0.5)),
        )
        for k in range(sides)
    )
    apothem = circumradius * math.cos(math.pi / sides)

    total = sides * tiles_per_side
    width = len(str(total - 1))
    tiles: list[Tile] = []
    for side in range(sides):
        ax, ay = vertices[side]
        bx, by = vertices[(side + 1) % sides]
        for slot in range(tiles_per_side):
            t0 = slot / tiles_per_side
            t1 = (slot + 1) / tiles_per_side
            start = (ax + (bx - ax) * t0, ay + (by - ay) * t0)
            end = (ax + (bx - ax) * t1, ay + (by - ay) * t1)
            index = side * tiles_per_side + slot
            tiles.append(
                Tile(
                    index=index,
                    tile_id=f"tile_{index:0{width}d}",
                    side=side,
                    slot=slot,
                    start=start,
                    end=end,
                    midpoint=(0.5 * (start[0] + end[0]), 0.5 * (start[1] + end[1])),
                    outward_normal=normals[side],
                    length=math.dist(start, end),
                )
            )

    return Arena(
        sides=sides,
        tiles_per_side=tiles_per_side,
        circumradius=circumradius,
        apothem=apothem,
        orientation=orientation,
        vertices=vertices,
        side_outward_normals=normals,
        tiles=tuple(tiles),
    )

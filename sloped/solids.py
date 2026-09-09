"""Triangle-mesh primitives for the parts of the course that are not channel.

`marble3d.mesh` emits two shapes, a surface of revolution and a swept
cross-section, and it is narrow on purpose - three of the physics lab's four
expensive bugs were collider-construction bugs that produced a plausible
physics result rather than an error. The stations need four more: a tube for a
mixer pin and a lane fin, a plate for an apron and a roof, a box shell for a
kerb and a wedge, and a height field over a rectangle for a funnel floor.

They are here rather than in `marble3d.mesh` because they are this course's
shapes and not the core's, and they keep the core's one invariant: a triangle
is only ever made between two adjacent rows of the same generator, so a
triangle spanning a whole piece - the phantom cone - cannot be built. Each
returns a `TriMesh`, so `marble3d.validation.check_mesh` applies to all of them
unchanged: degenerate area, longest edge, and the component count that catches
a piece that quietly came out as two.

Everything here takes and returns **simulation** units.
"""

from __future__ import annotations

import math
from typing import Callable, Sequence

from marble3d.mesh import TriMesh

__all__ = [
    "tube",
    "plate",
    "box_shell",
    "height_field",
    "flank_field",
    "wall_strip",
    "merge_meshes",
]

Vec3 = tuple[float, float, float]


def _sub(a, b) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _norm(a) -> Vec3:
    length = math.sqrt(sum(v * v for v in a))
    if length < 1e-12:
        raise ValueError("cannot normalise a zero vector")
    return (a[0] / length, a[1] / length, a[2] / length)


def _cross(a, b) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _perpendicular(axis: Vec3) -> Vec3:
    """Any unit vector at right angles to `axis`, chosen without a branch that
    degenerates: cross with whichever world axis `axis` is least aligned to."""
    least = min(range(3), key=lambda index: abs(axis[index]))
    other = tuple(1.0 if index == least else 0.0 for index in range(3))
    return _norm(_cross(axis, other))


def _rings_to_mesh(rings: Sequence[Sequence[Vec3]], name: str, closed: bool) -> TriMesh:
    width = len(rings[0])
    if any(len(ring) != width for ring in rings):
        raise ValueError(f"{name}: every ring needs the same point count")
    vertices = [tuple(float(v) for v in point) for ring in rings for point in ring]
    indices: list[int] = []
    span = width if closed else width - 1
    for row in range(len(rings) - 1):
        base = row * width
        above = base + width
        for column in range(span):
            step = (column + 1) % width
            a, b = base + column, base + step
            c, d = above + column, above + step
            indices.extend((a, c, b, b, c, d))
    return TriMesh(vertices, indices, name)


def tube(start, end, radius: float, segments: int = 10, name: str = "tube", caps: bool = True) -> TriMesh:
    """A closed cylinder between two points. A mixer pin, a lane fin, a shaft.

    Capped by default, because an uncapped tube is a surface a marble can be
    inside, and a marble inside a pin is a marble the solver pushes out in
    whichever direction the first contact normal happened to point.
    """
    if segments < 6:
        raise ValueError(f"{name}: a tube needs at least 6 segments")
    axis = _norm(_sub(end, start))
    across = _perpendicular(axis)
    up = _cross(axis, across)
    def ring_at(base, scale: float) -> list[Vec3]:
        out: list[Vec3] = []
        for step in range(segments):
            angle = 2.0 * math.pi * step / segments
            offset = tuple(
                radius
                * scale
                * (across[index] * math.cos(angle) + up[index] * math.sin(angle))
                for index in range(3)
            )
            out.append(tuple(base[index] + offset[index] for index in range(3)))
        return out

    rings: list[list[Vec3]] = []
    # The caps are bevelled to a sixth of the radius rather than collapsed to
    # a point: a ring of coincident vertices makes `segments` zero-area
    # triangles, which `min_triangle_area` flags and the solver would take a
    # meaningless normal from. A bevel is a shape.
    if caps:
        rings.append(ring_at(start, 1.0 / 6.0))
    rings.append(ring_at(start, 1.0))
    rings.append(ring_at(end, 1.0))
    if caps:
        rings.append(ring_at(end, 1.0 / 6.0))
    return _rings_to_mesh(rings, name, closed=True)


def plate(corners: Sequence[Sequence[float]], name: str = "plate", steps: int = 1) -> TriMesh:
    """A bilinear quad through four corners, in order round the perimeter.

    `steps` subdivides it, which matters when the quad is large: a marble
    rolling across one enormous triangle is fine, but `check_mesh` bounds the
    longest edge to catch phantom spans and a big plate would trip it.
    """
    if len(corners) != 4:
        raise ValueError(f"{name}: a plate has four corners")
    p00, p10, p11, p01 = (tuple(float(v) for v in point) for point in corners)
    rings: list[list[Vec3]] = []
    for row in range(steps + 1):
        v = row / steps
        left = tuple(p00[axis] + (p01[axis] - p00[axis]) * v for axis in range(3))
        right = tuple(p10[axis] + (p11[axis] - p10[axis]) * v for axis in range(3))
        rings.append(
            [
                tuple(left[axis] + (right[axis] - left[axis]) * (column / steps) for axis in range(3))
                for column in range(steps + 1)
            ]
        )
    return _rings_to_mesh(rings, name, closed=False)


def box_shell(centre, axes, half_extents, name: str = "box") -> TriMesh:
    """The six faces of a box, as one closed mesh. A kerb, a wedge, a fin.

    `axes` is three orthonormal vectors; `half_extents` matches them. Built as
    a closed ring sweep along the first axis so the seam falls on an edge the
    box already has, rather than as six independent quads whose shared edges
    would each be duplicated four times.
    """
    ax, ay, az = (tuple(float(v) for v in axis) for axis in axes)
    hx, hy, hz = (float(v) for v in half_extents)
    profile = ((-hy, -hz), (-hy, hz), (hy, hz), (hy, -hz))
    rings: list[list[Vec3]] = []
    # The first and last rings collapse onto the axis, which closes both ends
    # without a separate cap generator. A collapsed ring makes four degenerate
    # triangles per end; `min_triangle_area` would flag them, so the two caps
    # are pulled in to a tenth of the half extent rather than to a point - a
    # bevel, which is a shape a solver can produce a normal from.
    for sign, collapse in ((-1.0, 0.1), (-1.0, 1.0), (1.0, 1.0), (1.0, 0.1)):
        ring: list[Vec3] = []
        for up, across in profile:
            ring.append(
                tuple(
                    centre[axis]
                    + ax[axis] * sign * hx
                    + ay[axis] * up * collapse
                    + az[axis] * across * collapse
                    for axis in range(3)
                )
            )
        rings.append(ring)
    return _rings_to_mesh(rings, name, closed=True)


def height_field(
    origin,
    along,
    across,
    along_range: tuple[float, float],
    across_range: tuple[float, float],
    up,
    height: Callable[[float, float], float],
    steps: tuple[int, int] = (8, 8),
    name: str = "field",
) -> TriMesh:
    """A surface over a rectangle in the (along, across) plane of a frame.

    The funnel floor of the merge catch and the aprons of the start and the
    finish. `height(a, c)` returns the offset along `up` at each station, so a
    flat apron, a tilted plane and a shallow lateral V are the same generator
    with three different two-line functions.
    """
    a0, a1 = along_range
    c0, c1 = across_range
    rows, columns = steps
    rings: list[list[Vec3]] = []
    for row in range(rows + 1):
        a = a0 + (a1 - a0) * row / rows
        ring: list[Vec3] = []
        for column in range(columns + 1):
            c = c0 + (c1 - c0) * column / columns
            rise = height(a, c)
            ring.append(
                tuple(
                    origin[axis] + along[axis] * a + across[axis] * c + up[axis] * rise
                    for axis in range(3)
                )
            )
        rings.append(ring)
    return _rings_to_mesh(rings, name, closed=False)


def flank_field(
    origin,
    along,
    across,
    along_range: tuple[float, float],
    bounds: Callable[[float], tuple[float, float]],
    up,
    height: Callable[[float, float], float],
    steps: tuple[int, int] = (10, 6),
    name: str = "flank",
) -> TriMesh:
    """A surface whose across-span follows a channel instead of a rectangle.

    `height_field` spans a rectangle, which is what made the merge apron a
    height field *laid over* two swept channels: the apron owned the floor
    wherever its own tessellation happened to sit higher than the channel's,
    and along blue's west running edge it did, by 0.132 simulation units. See
    `sloped.stations.MergeCatch`.

    So the shoulder is generated between two curves instead. `bounds(a)`
    returns the `(inner, outer)` across coordinates at station `a` - normally
    the channel's own clear edge and the apron's outer rim - and the rows are
    laid between them. Every row keeps the same point count, so the strip
    invariant `_rings_to_mesh` enforces still holds, and a row whose inner and
    outer coincide collapses to a degenerate line rather than an inverted
    surface: that is what closes the apron's front lip, and it is why the
    caller may taper `outer` all the way to `inner`.

    A collapsed row is a real triangle-quality problem rather than a
    convenience, so it is answered rather than allowed: rows are laid at the
    *midpoints* of the collapsed span, which leaves the last strip a sliver
    with no zero-area triangle in it. `marble3d.validation.check_mesh` is the
    judge and it is run on the result.
    """
    a0, a1 = along_range
    rows, columns = steps
    rings: list[list[Vec3]] = []
    for row in range(rows + 1):
        a = a0 + (a1 - a0) * row / rows
        inner, outer = bounds(a)
        ring: list[Vec3] = []
        for column in range(columns + 1):
            t = column / columns
            c = inner + (outer - inner) * t
            rise = height(a, c)
            ring.append(
                tuple(
                    origin[axis] + along[axis] * a + across[axis] * c + up[axis] * rise
                    for axis in range(3)
                )
            )
        rings.append(ring)
    return _rings_to_mesh(rings, name, closed=False)


def wall_strip(
    origin,
    along,
    across,
    up,
    stations: Sequence[tuple[float, float]],
    base: Callable[[float, float], float],
    top: Callable[[float, float], float],
    name: str = "wall",
    steps: int = 1,
) -> TriMesh:
    """A vertical ribbon following a polyline of (along, across) stations.

    Used for every wall in a station: the merge catch's back and sides, the
    start grid's outer rails, the finish deck's rim. Two heights per station -
    a base that follows the floor and a top - so a wall standing on a tilted
    apron has no gap under it, which is the failure a wall authored at a
    constant height has and does not report.
    """
    if len(stations) < 2:
        raise ValueError(f"{name}: a wall needs at least two stations")
    # Subdivided between stations, because `check_mesh` bounds the longest edge
    # at four marble diameters to catch phantom spans and a wall across a
    # 22-unit finish deck is one edge of 22 unless it is broken up.
    dense: list[tuple[float, float]] = []
    for index in range(len(stations) - 1):
        a0, c0 = stations[index]
        a1, c1 = stations[index + 1]
        for step in range(steps):
            t = step / steps
            dense.append((a0 + (a1 - a0) * t, c0 + (c1 - c0) * t))
    dense.append(tuple(stations[-1]))
    rings: list[list[Vec3]] = []
    for level in (base, top):
        ring = []
        for a, c in dense:
            rise = level(a, c)
            ring.append(
                tuple(
                    origin[axis] + along[axis] * a + across[axis] * c + up[axis] * rise
                    for axis in range(3)
                )
            )
        rings.append(ring)
    return _rings_to_mesh(rings, name, closed=False)


def merge_meshes(meshes: Sequence[TriMesh], name: str) -> TriMesh:
    """One mesh from several, for a station that is a dozen small pieces.

    Bullet holds one shape per body and a body costs a broadphase entry, so a
    station whose collider is fourteen plates is fourteen bodies unless they
    are combined. `TriMesh.chunks` then splits the result back up on the
    *buffer* limits rather than on the authoring boundaries, which is the split
    that matters.
    """
    vertices: list[Vec3] = []
    indices: list[int] = []
    for mesh in meshes:
        offset = len(vertices)
        vertices.extend(mesh.vertices)
        indices.extend(index + offset for index in mesh.indices)
    return TriMesh(vertices, indices, name)

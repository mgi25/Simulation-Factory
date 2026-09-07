"""Triangle meshes: how a module's shape becomes something Bullet can collide.

Every static collider in the machine is a triangle mesh built here, by one of
two generators - a surface of revolution for the bowl and its drain, and a
swept cross-section for every channel, chute and curve. Both are strip
builders: they join *consecutive* rings of the same vertex count, and nothing
else in the package emits a triangle.

That narrowness is deliberate, and it comes from the lab. Three of the four
bugs the physics study spent its time on were collider-construction bugs that
produced a plausible-looking physics result rather than an error:

* a mesh handed to PyBullet's inline `createCollisionShape(vertices=, indices=)`
  path arrived silently truncated at the 8192-vertex command-buffer limit, and
  the bowl simply had no collider - marbles fell through the world and the run
  reported 0.14 revolutions, which reads exactly like a physics finding;
* a drain shaft appended after the dish rings instead of before them made the
  strip builder join the outer rim to the top of the shaft, so the collider
  contained a phantom cone running from rim to drain, and marbles wedged
  between the real dish and the fake one and stopped dead on the wall - which
  in a summary table reads exactly like "too much friction";
* the mesh resolution turned out to be a physics parameter and not an art one,
  because a rigid sphere loses energy at every triangle edge it rolls over.

So this module does four things about that. It refuses a profile with a jump in
it, so the phantom-cone shape cannot be built. It splits every mesh into chunks
well under any command-buffer limit rather than trusting an undocumented one.
It reports its own vertex count, triangle count, bounds and longest edge so
`marble3d.validation` can assert them. And it writes through a content-named
OBJ file, which is the path the lab proved has no size limit.

## Resolution

`worst_sagitta` is the gap between a polygon chord and the true arc it
approximates. The lab measured the trade-off on a bowl: at a sagitta of 0.9% of
the marble radius an orbit's energy half-life was 1.20 s, and at 15% it was
3.22 s - a *finer* collider dissipates more, because there are more edges to
cross. Smoothness and dissipation cross at about 3-4%, and
`marble3d.config.SAGITTA_BUDGET` is set there. Curved geometry in this package
chooses its segment count to meet that budget rather than hard-coding a number,
because the budget is a ratio and the machine is not all one size.
"""

from __future__ import annotations

import hashlib
import math
import os
from dataclasses import dataclass
from typing import Iterable, Sequence

from marble3d.geometry import Transform, Vec3

__all__ = [
    "TriMesh",
    "revolve",
    "sweep",
    "segments_for_sagitta",
    "worst_sagitta",
    "cached_obj",
]


@dataclass(frozen=True)
class Aabb:
    lower: Vec3
    upper: Vec3

    def size(self) -> Vec3:
        return tuple(hi - lo for lo, hi in zip(self.lower, self.upper))

    def contains(self, point: Sequence[float], slack: float = 0.0) -> bool:
        return all(
            lo - slack <= value <= hi + slack
            for lo, hi, value in zip(self.lower, self.upper, point)
        )

    def merged(self, other: "Aabb") -> "Aabb":
        return Aabb(
            tuple(min(a, b) for a, b in zip(self.lower, other.lower)),
            tuple(max(a, b) for a, b in zip(self.upper, other.upper)),
        )


class TriMesh:
    """Vertices and triangle indices, in world units, with its own statistics.

    Immutable in practice: `transformed` and `chunks` return new meshes. The
    cached properties are computed once because validation asks for all of them
    and a bowl is 25 000 triangles.
    """

    __slots__ = ("name", "vertices", "indices", "_aabb", "_longest_edge", "_digest")

    def __init__(
        self,
        vertices: Sequence[Sequence[float]],
        indices: Sequence[int],
        name: str = "mesh",
    ) -> None:
        self.name = name
        self.vertices: list[Vec3] = [tuple(float(v) for v in vertex) for vertex in vertices]
        self.indices: list[int] = [int(index) for index in indices]
        if len(self.indices) % 3:
            raise ValueError(f"{name}: {len(self.indices)} indices is not a whole number of triangles")
        self._aabb: Aabb | None = None
        self._longest_edge: float | None = None
        self._digest: str | None = None

    # --- statistics ------------------------------------------------------

    @property
    def vertex_count(self) -> int:
        return len(self.vertices)

    @property
    def triangle_count(self) -> int:
        return len(self.indices) // 3

    def triangles(self) -> Iterable[tuple[Vec3, Vec3, Vec3]]:
        vertices, indices = self.vertices, self.indices
        for base in range(0, len(indices), 3):
            yield (
                vertices[indices[base]],
                vertices[indices[base + 1]],
                vertices[indices[base + 2]],
            )

    def aabb(self) -> Aabb:
        if self._aabb is None:
            if not self.vertices:
                raise ValueError(f"{self.name}: an empty mesh has no bounds")
            lower = [math.inf] * 3
            upper = [-math.inf] * 3
            for vertex in self.vertices:
                for axis in range(3):
                    value = vertex[axis]
                    if value < lower[axis]:
                        lower[axis] = value
                    if value > upper[axis]:
                        upper[axis] = value
            self._aabb = Aabb(tuple(lower), tuple(upper))
        return self._aabb

    def longest_edge(self) -> float:
        """The longest triangle edge, which is how a phantom span is caught.

        A collider built from a strip of well-formed rings has edges on the
        order of the ring spacing. A triangle that spans the whole piece - the
        lab's phantom cone - has an edge tens of times that, so a bound on this
        number is a bound on that entire class of bug.
        """
        if self._longest_edge is None:
            worst = 0.0
            for a, b, c in self.triangles():
                for p, q in ((a, b), (b, c), (c, a)):
                    length = math.dist(p, q)
                    if length > worst:
                        worst = length
            self._longest_edge = worst
        return self._longest_edge

    def smallest_area(self) -> float:
        smallest = math.inf
        for a, b, c in self.triangles():
            ux, uy, uz = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
            vx, vy, vz = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
            cross = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
            area = 0.5 * math.sqrt(sum(value * value for value in cross))
            if area < smallest:
                smallest = area
        return 0.0 if smallest is math.inf else smallest

    # --- transformation and splitting ------------------------------------

    def transformed(self, transform: Transform, name: str | None = None) -> "TriMesh":
        return TriMesh(
            transform.transform_points(self.vertices),
            self.indices,
            name or self.name,
        )

    def chunks(self, max_vertices: int, max_indices: int) -> list["TriMesh"]:
        """Split into pieces small enough that no buffer limit can be reached.

        Triangles are taken in order and a chunk is closed as soon as the next
        one would not fit, so a chunk is a contiguous run of the strip and its
        vertices are spatially local - which is what the broadphase wants
        anyway. Vertices are re-indexed per chunk, so the union of the chunks
        has exactly the triangles of the original and the same geometry, with
        vertices along a cut duplicated between the two sides.

        The limit this defends against is PyBullet's inline shape-creation
        command buffer, 8192 vertices and 32768 indices. This package loads
        through an OBJ file, which the lab established has no such limit - so
        this is the belt to that file's braces, and it costs nothing.
        """
        if max_vertices < 3 or max_indices < 3:
            raise ValueError("a chunk has to be able to hold at least one triangle")
        pieces: list[TriMesh] = []
        vertices: list[Vec3] = []
        indices: list[int] = []
        remap: dict[int, int] = {}

        def close() -> None:
            if indices:
                pieces.append(TriMesh(vertices, indices, f"{self.name}#{len(pieces)}"))

        for base in range(0, len(self.indices), 3):
            triangle = self.indices[base : base + 3]
            fresh = sum(1 for index in triangle if index not in remap)
            if indices and (len(vertices) + fresh > max_vertices or len(indices) + 3 > max_indices):
                close()
                vertices, indices, remap = [], [], {}
            for index in triangle:
                local = remap.get(index)
                if local is None:
                    local = len(vertices)
                    remap[index] = local
                    vertices.append(self.vertices[index])
                indices.append(local)
        close()
        return pieces

    # --- serialisation ---------------------------------------------------

    def to_obj(self) -> str:
        """Wavefront OBJ, which is how a collider of this size reaches Bullet.

        PyBullet's in-process `createCollisionShape(vertices=, indices=)`
        marshals through a fixed command buffer and a mesh past it arrives
        truncated with no error at all. Loading from a file has no such limit,
        and `marble3d.validation.probe_surface` proves at run time that what
        arrived is what was sent.
        """
        lines = [f"v {x:.9g} {y:.9g} {z:.9g}" for x, y, z in self.vertices]
        lines += [
            f"f {self.indices[base] + 1} {self.indices[base + 1] + 1} {self.indices[base + 2] + 1}"
            for base in range(0, len(self.indices), 3)
        ]
        return "\n".join(lines) + "\n"

    def digest(self) -> str:
        if self._digest is None:
            self._digest = hashlib.sha256(self.to_obj().encode("ascii")).hexdigest()[:16]
        return self._digest


def cached_obj(mesh: TriMesh, directory: str) -> str:
    """Write the mesh once, named by its own content, and reuse it after that.

    Content-named rather than parameter-named so that two runs asking for the
    same geometry share a file, and a run asking for different geometry cannot
    pick up a stale collider. Given that the failure mode of a stale or missing
    collider is "the marbles fall through the world and the run still produces
    numbers", that is worth the hash.
    """
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{mesh.name.replace('#', '_')}_{mesh.digest()}.obj")
    if not os.path.exists(path):
        temporary = f"{path}.{os.getpid()}.partial"
        with open(temporary, "w", encoding="ascii", newline="\n") as handle:
            handle.write(mesh.to_obj())
        os.replace(temporary, path)
    return path


# --- generators ----------------------------------------------------------


def segments_for_sagitta(radius: float, budget: float) -> int:
    """The fewest circumferential segments whose chord error is within budget.

    `budget` is an absolute length, normally `SAGITTA_BUDGET * MARBLE_RADIUS`.
    Solving `r (1 - cos(pi/n)) <= budget` for n, then rounding up to a multiple
    of four so that a quarter turn lands on a vertex - which matters when a
    socket is placed at one.
    """
    if radius <= 0.0:
        raise ValueError("sagitta is only defined for a positive radius")
    if budget <= 0.0:
        raise ValueError("sagitta budget must be positive")
    ratio = 1.0 - budget / radius
    if ratio <= -1.0:
        return 8
    exact = math.pi / math.acos(max(-1.0, min(1.0, ratio)))
    return max(8, 4 * math.ceil(exact / 4.0))


def worst_sagitta(radius: float, segments: int) -> float:
    """How far a polygon of `segments` sides cuts inside a circle of `radius`."""
    return radius * (1.0 - math.cos(math.pi / segments))


def _strip(rings: list[list[Vec3]], closed: bool, name: str, flip: bool) -> TriMesh:
    """Join consecutive rings of equal length into a triangle strip.

    The one invariant worth stating: triangles are only ever made between ring
    `i` and ring `i + 1`. A caller who wants two pieces joined has to hand over
    one profile with both in it, in order, and `revolve` checks that the
    profile has no jump - which is what makes the phantom cone unbuildable
    rather than merely tested for.
    """
    width = len(rings[0])
    if any(len(ring) != width for ring in rings):
        raise ValueError(f"{name}: every ring of a strip needs the same number of points")
    vertices: list[Vec3] = [point for ring in rings for point in ring]
    indices: list[int] = []
    span = width if closed else width - 1
    for row in range(len(rings) - 1):
        base = row * width
        above = base + width
        for column in range(span):
            step = (column + 1) % width
            a, b = base + column, base + step
            c, d = above + column, above + step
            if flip:
                indices.extend((a, b, c, b, d, c))
            else:
                indices.extend((a, c, b, b, c, d))
    mesh = TriMesh(vertices, indices, name)
    return mesh


def revolve(
    profile: Sequence[tuple[float, float]],
    segments: int,
    name: str = "revolve",
    flip: bool = False,
    max_profile_step: float | None = None,
) -> TriMesh:
    """A surface of revolution about +Y, from a (radius, height) polyline.

    The profile is traversed in the order given and consecutive entries are
    joined, so a bowl and the drain shaft below it are one profile running
    bottom-up and not two pieces concatenated in whichever order came to hand.
    `max_profile_step` rejects a profile whose consecutive entries are further
    apart than the geometry should allow; passing it is what turns "we do not
    build phantom cones any more" into something the type system nearly
    enforces.
    """
    if segments < 8:
        raise ValueError(f"{name}: a surface of revolution needs at least 8 segments")
    if len(profile) < 2:
        raise ValueError(f"{name}: a profile needs at least two points")
    for index in range(len(profile) - 1):
        (r0, y0), (r1, y1) = profile[index], profile[index + 1]
        step = math.hypot(r1 - r0, y1 - y0)
        if step <= 0.0:
            raise ValueError(
                f"{name}: profile points {index} and {index + 1} coincide, "
                "which makes a ring of degenerate triangles"
            )
        if max_profile_step is not None and step > max_profile_step:
            raise ValueError(
                f"{name}: profile step {step:.4f} between points {index} and "
                f"{index + 1} exceeds the {max_profile_step:.4f} limit - this is "
                "the phantom-cone shape, and it means the profile pieces are "
                "out of order"
            )
        if r0 < 0.0 or r1 < 0.0:
            raise ValueError(f"{name}: a profile radius cannot be negative")

    angles = [2.0 * math.pi * segment / segments for segment in range(segments)]
    cosines = [math.cos(angle) for angle in angles]
    sines = [math.sin(angle) for angle in angles]
    rings = [
        [(radius * cosine, height, radius * sine) for cosine, sine in zip(cosines, sines)]
        for radius, height in profile
    ]
    return _strip(rings, closed=True, name=name, flip=flip)


def sweep(
    cross_section: Sequence[tuple[float, float]] | Sequence[Sequence[tuple[float, float]]],
    frames: Sequence[Transform],
    name: str = "sweep",
    closed_section: bool = False,
    flip: bool = False,
) -> TriMesh:
    """A channel: a cross-section carried along a path of frames.

    The cross-section is stated in the frame's own plane as (across, up) pairs,
    which is (+Z, +Y) in the socket convention - so a gutter is written the way
    it would be drawn on paper, and the same numbers describe the channel at a
    socket. Frames come from the module that owns the path; nothing here knows
    whether the path is straight, curved, banked or descending.

    Passing one section per frame instead of one section sweeps a *changing*
    profile - a chute whose walls taper away as it merges into a bowl, a
    channel that widens into a catch. Every section still has to have the same
    number of points, because the strip joins them point for point.
    """
    if len(frames) < 2:
        raise ValueError(f"{name}: a sweep needs at least two frames")
    if not cross_section:
        raise ValueError(f"{name}: a sweep needs a cross-section")
    per_frame = isinstance(cross_section[0][0], (list, tuple))
    sections = list(cross_section) if per_frame else [cross_section] * len(frames)
    if len(sections) != len(frames):
        raise ValueError(
            f"{name}: {len(sections)} cross-sections against {len(frames)} frames"
        )
    if len(sections[0]) < 2:
        raise ValueError(f"{name}: a cross-section needs at least two points")
    rings = [
        [frame.apply((0.0, up, across)) for across, up in section]
        for frame, section in zip(frames, sections)
    ]
    return _strip(rings, closed=closed_section, name=name, flip=flip)

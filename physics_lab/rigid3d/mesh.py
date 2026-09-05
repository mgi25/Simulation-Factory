"""The bowl as a triangle mesh, for engines that need a collider.

One builder, shared by the PyBullet prototype and the Godot cross-check, so
that "the same bowl" is a fact about the code rather than a claim about two
files. It emits the **contact** surface - `BowlSurface.contact_profile`, the
centre surface offset inward by one marble radius - because that is the thing
a sphere actually rests on, and resting on it puts the sphere's centre exactly
where the 2.5D constraint would have put it.

Two pieces:

* the **dish**, a surface of revolution from the drain rim out to the edge of
  the world, tessellated by arc length so the triangles are where the surface
  is steep rather than spread evenly across a radius;
* the **shaft**, a plain cylinder from the drain rim down past the exit plane.
  Without it a marble released at the lip with an inward velocity sails across
  the hole and out the far side under the dish. The 2.5D prototype has the
  same tube, applied as a radial reflection, and the two have to agree about
  it or they are not draining into the same drain.

There is deliberately **no rim wall**. A marble that gets past `max_radius`
has escaped, and both prototypes report that as a failure rather than
bouncing it back off geometry that only exists to hide the problem.

## The faceting, which is a real difference and not a detail

The 2.5D prototype's bowl is the analytic surface. This one is a polygon
approximation to it, and a sphere rolling across a facet edge gets a real bump
and loses a little energy to it. At the default resolution the worst sagitta -
the gap between the chord and the true arc - is 0.74 mm against a marble radius
of 0.02 m, 3.7%.

That number cannot simply be reduced, which is the surprise. A finer collider
has more edges to cross, so it dissipates *more*: measured on this bowl, an
orbit's energy half-life is 1.20 s at 128 segments and 3.22 s at 32. The
resolution is therefore a physics parameter rather than an art one, and there
is no equivalent choice to make in the 2.5D prototype at all. See section 4.3
of `docs/physics_lab_bowl_comparison.md`.
"""

from __future__ import annotations

import hashlib
import math
import os

from physics_lab.common.bowl import BowlSurface

__all__ = ["BowlMesh", "build_bowl_mesh", "worst_sagitta", "cached_obj"]

# Chosen by measurement, and the measurement went the opposite way to
# intuition. A finer collider is a *worse* one here: a rigid-body sphere loses
# energy at every triangle edge it rolls over, so halving the triangle size
# roughly halves the orbit's energy half-life. Measured on this bowl, 128
# circumferential segments give a 1.20 s half-life and 32 give 3.22 s, with
# the meridian ring count barely mattering because an orbiting marble crosses
# radial edges and not ring ones.
#
# Against that pulls the faceting: at 64 segments the worst sagitta - the gap
# between the polygon chord and the true circle - is 0.74 mm against a 20 mm
# marble radius, 3.7%, which reads as a round bowl. At 32 it is 2.95 mm, 15%,
# and the bowl reads as a polygon. 64 is where those two curves cross.
#
# That trade-off has no equivalent in the 2.5D prototype, whose bowl is the
# analytic surface, and it is one of the more important findings of the study.
DEFAULT_RINGS = 96
DEFAULT_SEGMENTS = 64
DEFAULT_SHAFT_RINGS = 8


class BowlMesh:
    """Vertices and triangle indices, in the units the benchmark is stated in."""

    def __init__(self, vertices: list[tuple[float, float, float]], indices: list[int]) -> None:
        self.vertices = vertices
        self.indices = indices

    @property
    def triangle_count(self) -> int:
        return len(self.indices) // 3

    def flat_vertices(self) -> list[float]:
        return [value for vertex in self.vertices for value in vertex]

    def to_obj(self) -> str:
        """Wavefront OBJ, which is how a mesh this size reaches a physics engine.

        PyBullet's in-process `createCollisionShape(vertices=, indices=)` marshals
        through a fixed-size command buffer - 8192 vertices and 32768 indices -
        and a mesh past that arrives truncated with no error. The first version
        of this experiment handed it 26624 vertices and got a bowl with no
        collider at all: the marbles fell through the world and the run
        recorded 0.14 revolutions, which looks exactly like a physics result
        and is not one. Loading from a file has no such limit.
        """
        lines = [f"v {x:.9g} {y:.9g} {z:.9g}" for x, y, z in self.vertices]
        lines += [
            f"f {self.indices[base] + 1} {self.indices[base + 1] + 1} {self.indices[base + 2] + 1}"
            for base in range(0, len(self.indices), 3)
        ]
        return "\n".join(lines) + "\n"

    def digest(self) -> str:
        return hashlib.sha256(self.to_obj().encode("ascii")).hexdigest()[:16]


def cached_obj(mesh: BowlMesh, directory: str) -> str:
    """Write the mesh once, named by its own content, and reuse it after that.

    Named by content rather than by parameters so that two runs asking for the
    same bowl share a file and a run asking for a different one cannot pick up
    a stale collider - which, given that the failure mode is "no collider at
    all, silently", is worth being careful about.
    """
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"bowl_{mesh.digest()}.obj")
    if not os.path.exists(path):
        with open(path, "w", encoding="ascii", newline="\n") as handle:
            handle.write(mesh.to_obj())
    return path


def build_bowl_mesh(
    surface: BowlSurface,
    exit_y: float,
    rings: int = DEFAULT_RINGS,
    segments: int = DEFAULT_SEGMENTS,
    shaft_rings: int = DEFAULT_SHAFT_RINGS,
) -> BowlMesh:
    """The dish and its drain shaft as one closed-ish triangle soup.

    Winding is consistent and outward-ish - upward on the dish, inward on the
    shaft - because some engines cull backfaces on static geometry even when
    the documentation says they do not.
    """
    if segments < 8:
        raise ValueError("a surface of revolution needs a believable number of segments")

    dish = [surface.contact_profile(radius) for radius in surface.contact_ring_radii(rings)]

    # The shaft hangs below the innermost dish ring, which is the hole rim, and
    # runs past the exit plane so a marble is never asked to leave through a
    # gap. It is built *before* the dish and the whole profile is traversed
    # bottom-up, because the strip below joins consecutive entries: with the
    # shaft appended instead, the outermost dish ring would be joined to the
    # top of the shaft and the mesh would contain a spurious cone running from
    # the rim straight down to the drain. That is not a hypothetical - it is
    # what the first version of this file built, and marbles wedged between
    # the real dish and the phantom one and stopped dead on the wall.
    rim_radius, rim_y = dish[0]
    shaft_bottom = exit_y - 4.0 * surface.marble_radius
    shaft = [
        (rim_radius, shaft_bottom + (rim_y - shaft_bottom) * index / shaft_rings)
        for index in range(shaft_rings)
    ]
    profile = shaft + dish

    vertices: list[tuple[float, float, float]] = []
    for radius, height in profile:
        for segment in range(segments):
            angle = 2.0 * math.pi * segment / segments
            vertices.append((radius * math.cos(angle), height, radius * math.sin(angle)))

    indices: list[int] = []
    for ring in range(len(profile) - 1):
        base = ring * segments
        following = base + segments
        for segment in range(segments):
            step = (segment + 1) % segments
            a, b = base + segment, base + step
            c, d = following + segment, following + step
            indices.extend((a, c, b, b, c, d))

    return BowlMesh(vertices, indices)


def worst_sagitta(surface: BowlSurface, segments: int) -> float:
    """How far the polygon ring cuts inside the true circle, at its worst.

    Measured at the largest radius, because that is where a chord of fixed
    angular width is longest. Reported rather than assumed: it is the size of
    the bumps a rigid-body marble rolls over that the 2.5D marble does not.
    """
    outer = surface.contact_profile(surface.max_radius)[0]
    return outer * (1.0 - math.cos(math.pi / segments))

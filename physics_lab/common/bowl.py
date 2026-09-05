"""The bowl, as one piece of geometry both prototypes are built from.

Everything in this module describes the **centre surface**: the surface a
marble's *centre* travels on while it is in contact with the bowl. That is a
deliberate choice and it is what makes the two experiments comparable at all.

A 2.5D prototype naturally wants to constrain the centre. A 3D rigid-body
engine wants a collider for the sphere to rest on, and a sphere resting on a
collider has its centre one radius *off* it along the normal. Describe the
collider and the two disagree by a radius everywhere and by more than that
wherever the surface curves. Describe the centre surface, hand the 3D engine
the offset of it (`contact_profile`), and a sphere at rest in Bullet has its
centre exactly where the Python constraint would have put it.

The profile, in the meridian plane, is three pieces:

    s in [lip_inner, lip_start]   the drain lip: a circle of one marble
                                  radius, tangent to the dish, that a marble
                                  rolls over on its way into the hole
    s in [lip_start, max_radius]  the dish: y = depth * (s/rim)^power
    s > max_radius                nothing. A marble out here has escaped and
                                  the run says so rather than inventing a wall.

The lip exists so that leaving the bowl is a physical event. A marble does not
reach the drain radius and get deleted: it rolls onto a convex lip, the normal
force the surface can supply falls, and at the point it reaches zero the marble
stops being a constrained marble and becomes a falling one. The 2.5D integrator
finds that point by watching the normal force, not by comparing to a number.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = ["BowlSurface", "SurfaceState"]


@dataclass(frozen=True)
class SurfaceState:
    """Everything the equations of motion need at one point of the surface.

    `height`, `slope` and `curvature` are the meridian profile and its first
    two derivatives with respect to radius; `grad_x`, `grad_z` and the two
    gain terms are the same information in the (x, z) chart the integrator
    actually works in.
    """

    height: float
    slope: float             # dy/ds
    curvature: float         # d2y/ds2
    grad_x: float
    grad_z: float
    radial_gain: float       # g(s)  = y'(s) / s
    radial_gain_rate: float  # g'(s) = (y''(s) s - y'(s)) / s^2


class BowlSurface:
    """A dish with a rolled drain lip, described once for both prototypes."""

    def __init__(
        self,
        rim_radius: float,
        rim_depth: float,
        profile_power: float,
        drain_radius: float,
        marble_radius: float,
        surface_max_radius: float,
    ) -> None:
        if rim_radius <= 0.0 or rim_depth <= 0.0:
            raise ValueError("bowl needs a positive radius and depth")
        if profile_power <= 1.0:
            raise ValueError("profile_power must exceed 1: a cone has no smooth floor")
        if not 0.0 < drain_radius < rim_radius:
            raise ValueError("drain must be smaller than the bowl")
        if marble_radius <= 0.0 or marble_radius >= drain_radius:
            raise ValueError("a marble that does not fit through the drain never leaves")
        if surface_max_radius < rim_radius:
            raise ValueError("the surface must reach at least the rim")

        self.rim_radius = float(rim_radius)
        self.rim_depth = float(rim_depth)
        self.profile_power = float(profile_power)
        self.drain_radius = float(drain_radius)
        self.marble_radius = float(marble_radius)
        self.max_radius = float(surface_max_radius)

        # Where the dish stops and the lip begins, in centre-surface radius.
        #
        # The number actually specified is `drain_radius`, the radius of the
        # hole in the *collider* - because that is the hole a marble has to
        # physically fit through and the one a mesh is cut to. The centre
        # surface reaches its lip slightly inside that, by the radial part of
        # the one-radius offset. A few fixed-point steps converge to well
        # under a micrometre at these slopes; the assertion below says so
        # rather than a comment claiming it.
        lip = self.drain_radius
        for _ in range(8):
            slope = self._dish_slope(lip)
            lip = self.drain_radius - self.marble_radius * slope / math.hypot(1.0, slope)
        self.lip_start = lip

        slope0 = self._dish_slope(self.lip_start)
        scale0 = math.hypot(1.0, slope0)
        # The lip circle's centre: the contact point at `lip_start`, which is
        # exactly the rim of the hole in the collider.
        self.lip_pivot_s = self.lip_start + self.marble_radius * slope0 / scale0
        self.lip_pivot_y = self._dish_height(self.lip_start) - self.marble_radius / scale0
        assert abs(self.lip_pivot_s - self.drain_radius) < 1e-9
        # Inside this a marble centre would be under the lip. Nothing should
        # ever get there: the normal force reaches zero well before it.
        self.lip_inner = self.lip_pivot_s - self.marble_radius

    # --- the meridian profile -------------------------------------------

    def _dish_height(self, s: float) -> float:
        return self.rim_depth * (s / self.rim_radius) ** self.profile_power

    def _dish_slope(self, s: float) -> float:
        if s <= 0.0:
            return 0.0
        power, depth, rim = self.profile_power, self.rim_depth, self.rim_radius
        return power * depth * s ** (power - 1.0) / rim**power

    def _dish_curvature(self, s: float) -> float:
        if s <= 0.0:
            return 0.0
        power, depth, rim = self.profile_power, self.rim_depth, self.rim_radius
        return power * (power - 1.0) * depth * s ** (power - 2.0) / rim**power

    def profile(self, s: float) -> tuple[float, float, float]:
        """Height, dy/ds and d2y/ds2 of the centre surface at radius `s`."""
        if s >= self.lip_start:
            return (self._dish_height(s), self._dish_slope(s), self._dish_curvature(s))

        # The lip: a circle of one marble radius about the hole rim, tangent
        # to the dish where the two meet. Convex, so the curvature is negative
        # and the normal force falls as a marble rolls onto it - which is the
        # whole point of building the drain this way.
        offset = s - self.lip_pivot_s
        inside = self.marble_radius**2 - offset**2
        if inside <= 0.0:
            # Past the lip entirely. Report the equator so a caller that has
            # not yet noticed it is in free fall still gets finite numbers.
            return (self.lip_pivot_y, -math.inf, -math.inf)
        width = math.sqrt(inside)
        return (
            self.lip_pivot_y + width,
            -offset / width,
            -(self.marble_radius**2) / (inside * width),
        )

    def height(self, s: float) -> float:
        return self.profile(s)[0]

    def state(self, x: float, z: float) -> SurfaceState:
        """The surface under a marble at horizontal position (x, z).

        The chart is the horizontal plane, so a marble is two numbers and its
        height is never integrated - which is why this prototype cannot drift
        off the surface, sink into it or hover above it. The constraint is not
        enforced; it is the coordinate system.
        """
        s = math.hypot(x, z)
        if s <= 1e-12:
            height, _, curvature = self.profile(0.0)
            return SurfaceState(height, 0.0, curvature, 0.0, 0.0, 0.0, 0.0)
        height, slope, curvature = self.profile(s)
        gain = slope / s
        return SurfaceState(
            height=height,
            slope=slope,
            curvature=curvature,
            grad_x=gain * x,
            grad_z=gain * z,
            radial_gain=gain,
            radial_gain_rate=(curvature * s - slope) / (s * s),
        )

    @staticmethod
    def curvature_term(
        state: SurfaceState, x: float, z: float, vx: float, vz: float
    ) -> float:
        """The part of the vertical acceleration the *path* forces.

        The constraint says y = f(x, z), so the second derivative of y is not
        free: it is grad-f dotted with the horizontal acceleration, plus a
        quadratic form in the horizontal velocity. This is that second term.
        It is what turns a fast marble on a curved wall into a large normal
        force, and it is the reason a marble follows the bowl round instead of
        cutting the corner. Written radially because the surface is one of
        revolution and the (x, z) Hessian collapses to two scalars there.
        """
        s = math.hypot(x, z)
        if s <= 1e-12:
            return state.radial_gain * (vx * vx + vz * vz)
        radial_rate = (x * vx + z * vz) / s
        return (
            state.radial_gain_rate * s * radial_rate * radial_rate
            + state.radial_gain * (vx * vx + vz * vz)
        )

    def normal(self, x: float, z: float) -> tuple[float, float, float]:
        """The unit surface normal at (x, z), pointing up out of the bowl."""
        state = self.state(x, z)
        inverse = 1.0 / math.sqrt(1.0 + state.grad_x**2 + state.grad_z**2)
        return (-state.grad_x * inverse, inverse, -state.grad_z * inverse)

    def world_position(self, x: float, z: float) -> tuple[float, float, float]:
        return (x, self.state(x, z).height, z)

    def world_velocity(
        self, x: float, z: float, vx: float, vz: float
    ) -> tuple[float, float, float]:
        state = self.state(x, z)
        return (vx, state.grad_x * vx + state.grad_z * vz, vz)

    # --- what a 3D engine needs -----------------------------------------

    def contact_profile(self, s: float) -> tuple[float, float]:
        """The collider under a marble whose centre is at dish radius `s`.

        The centre surface offset by one marble radius along its inward
        normal. A sphere resting here has its centre at `profile(s)` exactly,
        which is what makes a Bullet mesh and a Python constraint the same
        bowl rather than two bowls a radius apart.
        """
        height, slope, _ = self.profile(s)
        scale = math.hypot(1.0, slope)
        return (
            s + self.marble_radius * slope / scale,
            height - self.marble_radius / scale,
        )

    def contact_ring_radii(self, rings: int) -> list[float]:
        """Dish radii to tessellate the collider at, lip rim outward to the edge.

        Spaced by arc length rather than by radius: the dish is nearly flat at
        the drain and steep at the rim, and a uniform radial step would put
        most of the triangles where the surface is least interesting and the
        fewest where a marble is fastest.
        """
        if rings < 2:
            raise ValueError("a surface of revolution needs at least two rings")
        samples = 4096
        span = self.max_radius - self.lip_start
        step = span / samples
        arc = [0.0]
        for index in range(1, samples + 1):
            lower = self.lip_start + step * (index - 1)
            upper = self.lip_start + step * index
            slope = 0.5 * (self.profile(lower)[1] + self.profile(upper)[1])
            arc.append(arc[-1] + math.hypot(step, slope * step))
        total = arc[-1]

        radii: list[float] = []
        cursor = 0
        for index in range(rings):
            target = total * index / (rings - 1)
            while cursor < samples and arc[cursor + 1] < target:
                cursor += 1
            lower, upper = arc[cursor], arc[min(cursor + 1, samples)]
            fraction = 0.0 if upper <= lower else (target - lower) / (upper - lower)
            radii.append(self.lip_start + step * (cursor + fraction))
        radii[-1] = self.max_radius
        return radii

    # --- reference quantities -------------------------------------------

    def circular_orbit_speed(
        self, s: float, gravity: float, inertia_factor: float
    ) -> float:
        """The speed a marble needs to hold a circle at radius `s`.

        Derived rather than measured: with rolling inertia factor `c` the
        constrained equations give v squared = g s y'(s) / (1 + c). It is the
        scale every entry velocity in the benchmark is quoted as a fraction
        of, so that "0.8 of orbit speed" means the same thing at every radius
        and in both prototypes.
        """
        slope = self.profile(s)[1]
        return math.sqrt(max(0.0, gravity * s * slope / (1.0 + inertia_factor)))

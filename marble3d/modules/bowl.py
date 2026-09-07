"""The bowl: a dish, a rolled drain lip, a shaft, and the spout that feeds it.

The behaviour this module has to produce is stated in section 13 of the brief
and it is entirely negative: no scripted spiral, no radial attraction force, no
teleport to the drain. A marble entering tangentially has to orbit, climb the
wall on its own momentum, lose energy gradually, change orbit when it is hit,
spiral in and drain, because of the shape of a dish and Coulomb friction and
nothing else. So there is no code here that touches a marble. There is a
profile, a surface of revolution, and a chute.

## The profile, bottom-up, and why the order is load-bearing

    y(r) = depth * (r / rim_radius) ** power        the dish
    a circular fillet of radius `lip_radius`         the drain lip
    a cylinder at r = drain_radius                   the shaft

`power` is 1.9 rather than 2.0 and that is a physics decision the lab made and
measured. A true paraboloid is very nearly a harmonic oscillator: every orbit
has the same period whatever its amplitude, so a field of marbles never laps
itself and the bowl records a third of the collisions. Off the isochronous
point the period depends on energy, the field mixes, and the bowl does what a
bowl is in the machine to do.

The three pieces are assembled into **one** profile running bottom-up and
handed to `revolve` in that order, with a step limit. That is not tidiness. The
lab built the shaft rings *after* the dish rings, the strip builder joined the
outermost dish ring to the top of the shaft, and the collider acquired a
phantom cone running from the rim straight down to the drain - marbles wedged
between the real dish and the fake one and stopped dead on the wall, which in a
results table reads exactly like "this engine has too much friction". The
`max_profile_step` argument to `revolve` makes that mesh unbuildable rather
than merely tested for, and `local_probes` fires rays through the space the
cone would occupy.

## The lip is a shape, not a threshold

A marble does not reach `drain_radius` and get deleted. It rolls onto a convex
fillet, the surface curves away under it faster than gravity can hold it on,
and it leaves - as a falling rigid body, at whatever speed and spin it had.
Draining is a consequence of the geometry, which is why `test_marble3d_drain`
can assert that drain order varies with seed without anything ever having
ordered them.

## The spout

Section 12 asks for entry sockets, and a bowl with a socket floating at its rim
would be a bowl a marble arrives at by teleport. So the module owns its feed
spout: a gutter that starts outside the dish entirely, descends on a cubic
whose slope is zero at the far end, banks over to match the dish's own tilt,
and lands tangentially at `entry_radius`. A marble leaves it already rolling,
already banked into the wall and already moving along a circle - which is the
entry condition an orbit needs and is a nuisance to arrange any other way.

The spout's floor merges into the dish at its end, and its **walls taper to
nothing** over the last stretch. Two static colliders overlapping is harmless -
they never collide with each other, and a marble simply rides whichever surface
is higher - but a wall left standing where it pokes up through the dish would
be a genuine obstacle in the orbit path, which is the same phantom-geometry
failure by another route.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from marble3d.geometry import (
    DROP,
    GUIDED,
    Socket,
    Transform,
    basis_from_forward_up,
    quat_from_axis_angle,
    quat_multiply,
    quat_rotate,
)
from marble3d.mesh import Aabb, TriMesh, revolve, segments_for_sagitta, sweep, worst_sagitta
from marble3d.modules.base import MarbleModule, Probe, channel_section
from marble3d.units import MARBLE_DIAMETER, MARBLE_RADIUS

__all__ = ["BowlSpec", "BowlModule"]


def _within_sector(angle: float, low: float, high: float) -> bool:
    """Is `angle` inside [low, high], both taken modulo a full turn?"""
    span = (high - low) % (2.0 * math.pi)
    offset = (angle - low) % (2.0 * math.pi)
    return offset <= span


@dataclass(frozen=True)
class BowlSpec:
    """Every number the bowl is made of, in world units.

    Quoted against the marble wherever the number is really a ratio, because
    the ratios are what carry across a change of scale and the absolute values
    are not. The defaults describe a bowl 31 marble diameters across with a
    drain 3 diameters wide - the size the lab's sweep chose, where every marble
    drains, nothing jams, and the largest spurious energy rise over twenty
    seeds was 0.0003 J.
    """

    rim_radius: float = 25.0 * MARBLE_RADIUS       # 12.5 wu
    rim_depth: float = 9.0 * MARBLE_RADIUS         # 4.5 wu
    profile_power: float = 1.9
    # How far the dish continues past the nominal rim. This is the bowl's
    # containment: there is no lip and no wall, so a marble that gets past
    # `max_radius` has escaped and the run says so rather than bouncing it back
    # off geometry that only exists to hide the problem. At 1.25 the fastest
    # marble in the field climbed to 15.42 against an edge at 15.62 - 0.4 of a
    # marble radius of headroom, which is not a margin, it is a coincidence
    # waiting for a seed. 1.35 with the release inset moved out to match leaves
    # the entry speeds untouched and puts 1.5 wu of wall above the highest
    # climb measured.
    max_radius_factor: float = 1.35                # dish continues past the rim
    drain_radius: float = 3.0 * MARBLE_RADIUS      # a 3-diameter hole
    lip_radius: float = 1.2 * MARBLE_RADIUS
    # Deep enough that a marble leaving it is clear of the underside of the
    # dish, and no deeper: every unit of shaft is a unit of free fall, and the
    # speed a marble arrives at the next module with is 2 g h.
    shaft_bottom: float = -5.0 * MARBLE_RADIUS
    ring_step: float = 0.5                         # meridian tessellation, wu

    # --- the spout ---
    # The spout lands one marble diameter inside the outer edge of the dish and
    # nowhere else, so its whole run lies over the steep outer sliver of the
    # bowl and the orbit corridor is completely clear of it. An earlier version
    # landed at 0.8 of the rim radius and was a low bridge across the middle of
    # the bowl: it cleared the dish by 0.1 to 0.7 wu along its length, which is
    # less than a marble, so an orbiting marble would have hit its underside.
    # Where a marble is released into a bowl is not a free parameter - it is
    # the rim, which is also where a real vortex funnel is fed.
    # Chosen with `max_radius_factor` so that the release radius comes out at
    # 14.625 either way: the extra dish is headroom above the marbles, not a
    # further-out release with more energy behind it.
    entry_inset: float = 2.25 * MARBLE_DIAMETER    # inside the dish edge
    spout_clearance: float = 1.0                   # how far outside the dish it starts
    spout_rise_factor: float = 2.0                 # of the dish's own rise; see _spout_path
    spout_width: float = 2.4 * MARBLE_RADIUS
    spout_wall: float = 1.6 * MARBLE_RADIUS
    spout_floor_radius: float = 1.6 * MARBLE_RADIUS
    spout_frames: int = 40
    spout_taper: float = 3.0                       # wu over which the walls fade out
    # The walls fade to this rather than to nothing. Tapering to exactly zero
    # collapses the wall vertices onto the floor edge and the last rings of the
    # strip become zero-area triangles, which is one of the degenerate cases
    # section 8 of the brief asks to be free of.
    spout_wall_stub: float = 0.16 * MARBLE_RADIUS

    @property
    def max_radius(self) -> float:
        return self.rim_radius * self.max_radius_factor

    @property
    def entry_radius(self) -> float:
        return self.max_radius - self.entry_inset

    def height(self, radius: float) -> float:
        """The dish surface, as a height above the profile's virtual apex."""
        return self.rim_depth * (radius / self.rim_radius) ** self.profile_power

    def slope(self, radius: float) -> float:
        if radius <= 0.0:
            return 0.0
        power, depth, rim = self.profile_power, self.rim_depth, self.rim_radius
        return power * depth * radius ** (power - 1.0) / rim**power

    def steepest_angle(self) -> float:
        return math.atan(self.slope(self.max_radius))

    def to_json(self) -> dict[str, Any]:
        return {
            "rim_radius": self.rim_radius,
            "rim_depth": self.rim_depth,
            "profile_power": self.profile_power,
            "max_radius": self.max_radius,
            "drain_radius": self.drain_radius,
            "lip_radius": self.lip_radius,
            "shaft_bottom": self.shaft_bottom,
            "entry_radius": self.entry_radius,
            "drain_diameters": 2.0 * self.drain_radius / MARBLE_DIAMETER,
        }


class BowlModule(MarbleModule):
    """A dish with a drained centre and a tangential feed spout.

    Local frame: the origin is on the axis at the dish profile's virtual apex,
    +Y up. The drain runs down the -Y axis and the spout arrives in the +Z
    direction at (entry_radius, ., 0).
    """

    def __init__(self, module_id: str = "bowl", spec: BowlSpec | None = None, sagitta_limit: float = 0.02) -> None:
        super().__init__(module_id)
        self.spec = spec or BowlSpec()
        self.sagitta_limit = sagitta_limit
        self._validate()
        self.segments = segments_for_sagitta(self.spec.max_radius, sagitta_limit)
        self.sagitta = worst_sagitta(self.spec.max_radius, self.segments)
        self._lip = self._solve_lip()
        self._meshes: list[TriMesh] | None = None
        self._check_spout_clearance()

    def _validate(self) -> None:
        spec = self.spec
        if spec.profile_power <= 1.0:
            raise ValueError("profile_power must exceed 1: a cone has no smooth floor")
        if not 0.0 < spec.drain_radius < spec.rim_radius:
            raise ValueError("the drain must be smaller than the bowl")
        if spec.drain_radius <= MARBLE_RADIUS:
            raise ValueError(
                f"a drain of radius {spec.drain_radius} does not pass a "
                f"{MARBLE_RADIUS} marble; nothing would ever leave"
            )
        if spec.shaft_bottom >= 0.0:
            raise ValueError("the drain shaft has to hang below the dish")
        if not spec.rim_radius < spec.entry_radius < spec.max_radius:
            raise ValueError(
                "the spout has to land on the outer wall, between the rim and "
                "the edge of the dish"
            )

    # --- the drain lip ---------------------------------------------------

    def _solve_lip(self) -> tuple[float, float, float]:
        """The fillet joining the vertical shaft to the dish, solved for.

        A circle of radius `lip_radius` centred at `drain_radius + lip_radius`
        is vertical where it meets the shaft by construction; the free
        parameters are its height and where it leaves the dish, and they are
        fixed by requiring the arc and the dish to share a tangent. Four
        fixed-point steps take the residual below a micrometre at these slopes,
        and the assertion afterwards says so rather than a comment claiming it.

        Returns (centre height, contact radius on the dish, arc end angle).
        """
        spec = self.spec
        centre_radius = spec.drain_radius + spec.lip_radius
        contact_radius = centre_radius
        angle = math.pi / 2.0
        for _ in range(24):
            slope = spec.slope(contact_radius)
            # dy/dr along the arc is cot(angle); matching it to the dish slope
            # is what makes the join tangent.
            angle = math.atan2(1.0, slope)
            contact_radius = centre_radius - spec.lip_radius * math.cos(angle)
        centre_height = spec.height(contact_radius) - spec.lip_radius * math.sin(angle)
        residual = abs(
            (centre_radius - spec.lip_radius * math.cos(angle)) - contact_radius
        )
        assert residual < 1e-9, f"drain lip did not converge: residual {residual}"
        return (centre_height, contact_radius, angle)

    @property
    def lip_contact_radius(self) -> float:
        return self._lip[1]

    @property
    def drain_rim_height(self) -> float:
        """Where the vertical shaft ends and the fillet begins."""
        return self._lip[0]

    # --- geometry --------------------------------------------------------

    def _profile(self) -> list[tuple[float, float]]:
        """The whole meridian, bottom-up, in one list. See the docstring."""
        spec = self.spec
        centre_height, contact_radius, arc_end = self._lip

        step = spec.ring_step
        profile: list[tuple[float, float]] = []

        # 1. the shaft, from its bottom up to the fillet's tangent point
        shaft_height = centre_height - spec.shaft_bottom
        shaft_rings = max(2, int(math.ceil(shaft_height / step)))
        for index in range(shaft_rings):
            profile.append(
                (spec.drain_radius, spec.shaft_bottom + shaft_height * index / shaft_rings)
            )

        # 2. the fillet, from vertical to tangent with the dish
        arc_length = spec.lip_radius * arc_end
        arc_points = max(3, int(math.ceil(arc_length / (0.5 * step))))
        centre_radius = spec.drain_radius + spec.lip_radius
        for index in range(arc_points + 1):
            angle = arc_end * index / arc_points
            profile.append(
                (
                    centre_radius - spec.lip_radius * math.cos(angle),
                    centre_height + spec.lip_radius * math.sin(angle),
                )
            )

        # 3. the dish, tessellated by arc length so the rings are where the
        #    surface is steep rather than spread evenly across a radius
        radius = contact_radius
        while radius < spec.max_radius - 1e-9:
            advance = step / math.hypot(1.0, spec.slope(radius))
            radius = min(spec.max_radius, radius + advance)
            profile.append((radius, spec.height(radius)))

        # The fillet's last point and the dish's first are the same point.
        deduplicated = [profile[0]]
        for point in profile[1:]:
            if math.dist(point, deduplicated[-1]) > 1e-9:
                deduplicated.append(point)
        return deduplicated

    def _spout_path(self) -> tuple[list[Transform], list[list[tuple[float, float]]], float]:
        """Frames and per-frame sections for the feed spout.

        In plan the spout is the straight line tangent to the circle of radius
        `entry_radius` at the point (entry_radius, ., 0), running in +Z, so a
        marble leaving it is already travelling along a circle of the bowl.
        Its length is whatever puts its far end `spout_clearance` outside the
        dish, so the join with an upstream module is out in the open.

        ## The height profile, and the constraint that fixes it

        `h(d) = y_b + a d^2 + b d^3`, with d measured back from the landing
        point, so `h'(0) = 0` and the spout arrives level in the direction of
        travel - which is what makes the release tangential rather than a drop.

        `a` is not free. Going back up the spout the *radius* grows as
        `sqrt(r_b^2 + d^2)`, so the dish underneath rises as

            y(r(d)) = y_b + slope(r_b) * d^2 / (2 r_b) + O(d^4)

        and a spout with a smaller quadratic coefficient than that starts
        *below* the dish a couple of units back from its own landing point,
        with the marble inside the bowl wall. So `a` is set at
        `spout_rise_factor` times the dish's own rate and `b` is whatever makes
        the far end come out at the right height. The pitch at the far end
        falls out of that rather than being chosen, and the entry socket
        reports it: the bowl declares the angle it wants to be fed at and the
        chute upstream adopts it through the socket, which is the right way
        round. Both properties are checked by `_check_spout_clearance` rather
        than trusted.

        Bank runs from level to the dish's own transverse tilt on a smoothstep,
        so the marble is already leaning into the wall when it is released.
        """
        spec = self.spec
        radius = spec.entry_radius
        start_radius = spec.max_radius + spec.spout_clearance
        length = math.sqrt(max(start_radius**2 - radius**2, (4.0 * MARBLE_DIAMETER) ** 2))

        landing = spec.height(radius)
        rise = spec.height(spec.max_radius) + spec.spout_clearance - landing
        a = spec.spout_rise_factor * spec.slope(radius) / (2.0 * radius)
        b = (rise - a * length * length) / length**3
        turning = -2.0 * a / (3.0 * b) if b < 0.0 else math.inf
        if turning <= length:
            raise ValueError(
                f"spout height profile turns over {turning:.2f} along its "
                f"{length:.2f} length; it needs more clearance or less rise"
            )

        bank_end = math.atan(spec.slope(radius))
        frames: list[Transform] = []
        sections: list[list[tuple[float, float]]] = []
        count = spec.spout_frames
        for index in range(count + 1):
            travelled = length * index / count       # 0 at the far end
            distance = length - travelled            # distance back from the landing
            height = landing + a * distance * distance + b * distance**3
            slope = -(2.0 * a * distance + 3.0 * b * distance * distance)
            position = (radius, height, -distance)
            forward = (0.0, slope, 1.0)
            base = basis_from_forward_up(forward, (0.0, 1.0, 0.0))
            fraction = index / count
            smooth = fraction * fraction * (3.0 - 2.0 * fraction)
            roll = quat_from_axis_angle(quat_rotate(base, (1.0, 0.0, 0.0)), bank_end * smooth)
            frames.append(Transform(position, quat_multiply(roll, base)))

            # Walls fade out over the last `spout_taper` of the run, down to a
            # stub, so nothing is left standing where the floor has merged into
            # the dish and no ring of the strip collapses to zero area.
            fade = min(1.0, distance / max(spec.spout_taper, 1e-6))
            wall = spec.spout_wall_stub + (spec.spout_wall - spec.spout_wall_stub) * fade
            sections.append(channel_section(spec.spout_width, wall, spec.spout_floor_radius))
        return frames, sections, length

    def spout_clearance_profile(self, samples: int = 64) -> list[tuple[float, float]]:
        """(distance back from the landing, floor height above the dish).

        Sampled from the built frames rather than from the formula, so it is
        checking the geometry that will actually be tessellated. A spout floor
        *below* the dish would put the marble inside the bowl wall, so the
        build refuses it; a spout floor far above the dish over the orbit
        corridor would be a bridge for marbles to hit, which is why the landing
        radius is at the rim and this profile only ever covers the outer sliver.
        """
        spec = self.spec
        frames, _, length = self._spout_path()
        profile: list[tuple[float, float]] = []
        for frame in frames:
            distance = -frame.position[2]
            radius = math.hypot(spec.entry_radius, distance)
            if radius > spec.max_radius:
                profile.append((distance, math.inf))
                continue
            profile.append((distance, frame.position[1] - spec.height(radius)))
        return profile

    def _spout_sector(self) -> tuple[float, float]:
        """The range of azimuths the spout occupies, padded by its own width.

        The spout runs along a chord, not an arc, so it covers a wedge rather
        than a constant angle: from the landing point at azimuth zero back to
        the far end. The padding is the channel's own half width projected onto
        the horizontal, which is what makes this a footprint rather than a line.
        """
        spec = self.spec
        _, _, length = self._spout_path()
        # The spout runs toward -Z from the landing point, which is -azimuth in
        # the (r cos, r sin) parametrisation this module uses.
        far = -math.atan2(length, spec.entry_radius)
        pad = math.atan2(spec.spout_width + 2.0 * spec.spout_wall, spec.entry_radius)
        return (far - pad, pad)

    def _check_spout_clearance(self) -> None:
        for distance, clearance in self.spout_clearance_profile():
            if clearance < 0.0:
                raise ValueError(
                    f"{self.id}: the spout floor is {-clearance:.3f} below the dish "
                    f"{distance:.2f} back from its landing point"
                )

    def local_colliders(self) -> list[TriMesh]:
        if self._meshes is None:
            profile = self._profile()
            dish = revolve(
                profile,
                self.segments,
                name=f"{self.id}_dish",
                # Nothing in a well-formed meridian steps further than a couple
                # of ring spacings; a strip that jumps from the rim to the
                # shaft is the phantom cone and this refuses to build it.
                max_profile_step=4.0 * self.spec.ring_step,
            )
            frames, sections, _ = self._spout_path()
            spout = sweep(sections, frames, name=f"{self.id}_spout")
            self._meshes = [dish, spout]
        return self._meshes

    def local_bounds(self) -> Aabb:
        spec = self.spec
        reach = spec.max_radius + spec.spout_clearance + spec.spout_width
        return Aabb(
            (-reach, spec.shaft_bottom - MARBLE_DIAMETER, -reach),
            (reach, spec.height(spec.max_radius) + 4.0 * MARBLE_DIAMETER, reach),
        )

    # --- sockets ---------------------------------------------------------

    def local_sockets(self) -> dict[str, Socket]:
        spec = self.spec
        frames, _, _ = self._spout_path()
        entry_frame = frames[0]
        drain = Socket(
            name="drain",
            frame=Transform(
                (0.0, spec.shaft_bottom, 0.0),
                # A marble leaving the drain is falling, and it is still
                # carrying the swirl it had - so the heading is the orbit's
                # tangent, which is what a drop join downstream yaws itself to.
                basis_from_forward_up((0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
            ),
            kind=DROP,
            width=2.0 * spec.drain_radius,
            height=2.0 * spec.drain_radius,
        )
        return {
            "entry": Socket(
                name="entry",
                frame=entry_frame,
                kind=GUIDED,
                width=spec.spout_width,
                height=spec.spout_wall,
            ),
            "drain": drain,
        }

    # --- probes ----------------------------------------------------------

    def local_probes(self) -> list[Probe]:
        """Rays that prove the collider Bullet holds is the one described here.

        Four families, and the negative ones matter as much as the positive:

        * straight down onto the dish at a spiral of sample points - proves the
          surface exists, at the analytic height, everywhere a marble orbits;
        * straight down through the drain - proves the hole is a hole;
        * outward through the shaft wall - proves the shaft is closed, which is
          what stops a marble crossing the hole and coming out under the dish;
        * horizontally through the empty space above the dish - proves there is
          no phantom cone and no spout wall left standing in the orbit path.
        """
        spec = self.spec
        probes: list[Probe] = []
        top = spec.height(spec.max_radius) + 4.0 * MARBLE_DIAMETER

        # A spiral of downward rays over the dish. Prime-ish angular stride so
        # the samples do not all land on the same meridian of the tessellation.
        samples = 96
        inner = self.lip_contact_radius + MARBLE_RADIUS
        low, high = self._spout_sector()
        for index in range(samples):
            fraction = (index + 0.5) / samples
            radius = inner + (spec.max_radius - MARBLE_RADIUS - inner) * fraction
            angle = 2.0 * math.pi * (index * 0.381966)
            # The spout is a roof over the outer wall, so a downward ray under
            # it legitimately lands on the spout rather than the dish. Skip
            # those rather than widen the tolerance until the check stops
            # meaning anything - the spout has probes of its own.
            if radius > spec.rim_radius and _within_sector(angle, low, high):
                continue
            x, z = radius * math.cos(angle), radius * math.sin(angle)
            probes.append(
                Probe(
                    start=(x, top, z),
                    end=(x, spec.shaft_bottom - MARBLE_DIAMETER, z),
                    expect_hit=True,
                    expected_point=(x, spec.height(radius), z),
                    # The chord of a tessellated ring cuts inside the true
                    # circle, so a downward ray legitimately lands a sagitta's
                    # worth of slope below the analytic surface.
                    tolerance=2.0 * self.sagitta * max(1.0, spec.slope(radius)) + 0.05,
                    label=f"{self.id}.dish r={radius:.2f}",
                )
            )

        # Down the middle of the drain: nothing should stop a marble. The ray
        # stops at the mouth of the shaft rather than carrying on into open
        # air, because whatever catches the marbles below is a different
        # module's business and it is *supposed* to be there.
        for index in range(8):
            angle = 2.0 * math.pi * index / 8.0
            radius = 0.35 * spec.drain_radius
            x, z = radius * math.cos(angle), radius * math.sin(angle)
            probes.append(
                Probe(
                    start=(x, top, z),
                    end=(x, spec.shaft_bottom, z),
                    expect_hit=False,
                    label=f"{self.id}.drain open",
                )
            )

        # Outward through the shaft wall, at three heights.
        for level in (0.2, 0.5, 0.8):
            height = spec.shaft_bottom + level * (self.drain_rim_height - spec.shaft_bottom)
            for index in range(12):
                angle = 2.0 * math.pi * index / 12.0
                direction = (math.cos(angle), 0.0, math.sin(angle))
                probes.append(
                    Probe(
                        start=(0.0, height, 0.0),
                        end=(
                            direction[0] * spec.drain_radius * 3.0,
                            height,
                            direction[2] * spec.drain_radius * 3.0,
                        ),
                        expect_hit=True,
                        expected_point=(
                            direction[0] * spec.drain_radius,
                            height,
                            direction[2] * spec.drain_radius,
                        ),
                        tolerance=self.sagitta + 0.05,
                        label=f"{self.id}.shaft wall y={height:.2f}",
                    )
                )

        # The orbit corridor: a horizontal ring of rays a marble diameter above
        # the dish, fired tangentially. A phantom cone, a leftover spout wall
        # or a mis-ordered strip all put something here.
        for index in range(24):
            angle = 2.0 * math.pi * index / 24.0
            radius = 0.6 * spec.rim_radius
            x, z = radius * math.cos(angle), radius * math.sin(angle)
            height = spec.height(radius) + 2.5 * MARBLE_DIAMETER
            span = 0.25 * spec.rim_radius
            tangent = (-math.sin(angle), 0.0, math.cos(angle))
            probes.append(
                Probe(
                    start=(x, height, z),
                    end=(x + tangent[0] * span, height, z + tangent[2] * span),
                    expect_hit=False,
                    label=f"{self.id}.orbit corridor clear",
                )
            )
        return probes

    def describe(self) -> dict[str, Any]:
        return {
            "spec": self.spec.to_json(),
            "segments": self.segments,
            "sagitta": self.sagitta,
            "sagitta_over_marble_radius": self.sagitta / MARBLE_RADIUS,
            "steepest_angle_deg": math.degrees(self.spec.steepest_angle()),
            "drain_rim_height": self.drain_rim_height,
        }

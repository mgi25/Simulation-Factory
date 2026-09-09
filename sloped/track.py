"""The channel collider: the visible track's own inner surface, and nothing else.

## What the collider is a collider *of*

`v2_track.gd` sweeps six pieces per run - a pearl shell, a polished running
insert, a graphite keel, two acrylic guards, a chrome bead and a lit edge tube.
Five of those are outside the channel or under it, and a marble never touches
one. The collider here is the sixth thing: the single open surface a marble can
actually be in contact with, traced across the section from the cradle's
centreline out to the top of each guard.

Reading it out from the asset rather than approximating it matters at the wall.
The obvious collider - a circular floor and a straight wall standing at the
channel edge, which is what `marble3d.modules.base.channel_section` builds -
puts the physical wall at |across| = 0.94 while the surface a climbing marble
meets in the render is the rolled lip's inner face and then the guard, at 0.95
rising to 1.002. A marble held off at 0.94 sits 0.06 layout units - a tenth of
a marble diameter - clear of the wall it appears to be leaning on. So the
section below has the lip's four authored points in it, and the guard's inner
face above them.

    guard top     1.002, 0.540   ─┐
    guard base    1.002, 0.280    │  acrylic rail, the real containment
    lip inner     1.000, 0.265   ─┤
                  0.985, 0.180    │  the rolled lip, from channel_section's
                  0.970, 0.080    │  own authored half
                  0.950, -0.010  ─┘
    cradle edge   0.940, -0.049  ─┐
                  0.705, -0.145   │  a circular arc of radius 2.20, five
                  0.470, -0.210   │  points per half, which is exactly what
                  0.235, -0.247   │  the asset uses
    centreline    0.000, -0.260  ─┘

Containment is 0.80 layout units from the cradle's lowest point to the guard's
top - 1.404 simulation units, so a shade over a marble diameter and a
half of wall against a marble whose centre rides half a diameter up. That is
the budget the escape count in section 18 of the brief is measured against, and
it is the asset's number, not a chosen one.

## Resolution, which is a physics parameter here and not an art one

118 samples along the path, because that is what `course_machine.gd` passes and
therefore what was photographed - see `sloped.pathing.TRACK_SAMPLES`. It also
happens to be the right number: on the tightest hairpin the longitudinal facet
sagitta comes out at about 3.2% of a marble radius against the core's 4%
budget, and `marble3d.config.ColliderConfig` records why finer is worse - a
rigid sphere loses energy at every triangle edge it rolls over, so smoothness
and dissipation cross at 3 to 4% and a denser collider dissipates *more*.
Subdividing for smoothness would move the physics away from the calibration and
away from the render at the same time.

Five points per cradle half is the same argument across the section: the
cradle's 50.6° arc at radius 3.86 simulation units needs 4.5 segments to meet
the 0.02-unit sagitta limit, the asset uses five, and so does this.

## Units

The path, the profile and every constant read out of the asset are in **layout**
units. `to_sim` is applied once, at the point where vertices are emitted, and
`sloped.scale` explains why the simulation runs at the larger scale.
"""

from __future__ import annotations

import math
from typing import Sequence

from marble3d.geometry import IDENTITY, GUIDED, Socket, Transform, basis_from_forward_up
from marble3d.mesh import Aabb, TriMesh
from marble3d.modules.base import MarbleModule, Probe
from marble3d.units import MARBLE_DIAMETER, MARBLE_RADIUS

from sloped import layout
from sloped.pathing import banked_basis, build_path, arc_lengths, nearest_index
from sloped.scale import LAYOUT_TO_SIM, to_sim, to_sim_point

__all__ = [
    "CRADLE_POINTS",
    "channel_profile",
    "frames_for",
    "ring_points",
    "sweep_rings",
    "TrackRun",
]


# Points per cradle half, as `v2_track.channel_section` walks it.
CRADLE_POINTS = 5


def _ease(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return t * t * (3.0 - 2.0 * t)


def channel_profile(scale: float = 1.0) -> list[tuple[float, float]]:
    """The inner containment surface as (across, up) pairs, in layout units.

    Walked from the left guard top, down the left wall, across the cradle and
    back up the right, so consecutive points are neighbours on the surface and
    the strip builder joins them in order. `scale` is the run's profile scale -
    0.82 for a branch - applied the way `v2_track._sized` applies it, to the
    whole section uniformly.
    """
    half = layout.CHANNEL_HALF
    right: list[tuple[float, float]] = []
    for step in range(CRADLE_POINTS):
        across = half * step / (CRADLE_POINTS - 1)
        right.append((across, layout.floor_y_at(across)))
    right.extend(layout.LIP_INNER)
    right.append((layout.GUARD_INNER, layout.GUARD_BASE))
    right.append((layout.GUARD_INNER, layout.CONTAINMENT_TOP))

    section = [(-across, up) for across, up in reversed(right[1:])] + right
    return [(across * scale, up * scale) for across, up in section]


def _interpolate_rise(section: Sequence[tuple[float, float]], across: float) -> float:
    """The section's height at one across, by linear interpolation.

    The profile's `across` is non-decreasing from the west guard to the east
    one - two pairs of points share a value at the guards - so a walk is enough
    and no sort is needed.
    """
    if across <= section[0][0]:
        return section[0][1]
    for (a0, u0), (a1, u1) in zip(section, section[1:]):
        if a0 <= across <= a1:
            if a1 - a0 < 1e-12:
                return u1
            return u0 + (u1 - u0) * (across - a0) / (a1 - a0)
    return section[-1][1]


def frames_for(path, banks, tangents):
    """The rolled frame at every sample, as (lateral, up, forward) triples."""
    return [banked_basis(tangents, banks, index) for index in range(len(path))]


def ring_points(centre, frame, section, width: float) -> list[tuple[float, float, float]]:
    """One section carried to one sample, exactly as `banked_sweep` carries it.

    `centre + lateral * across * width + up * rise` is `v2_forms.banked_sweep`'s
    own expression, with `width` the per-sample lateral factor from
    `width_curve`. Lateral only: scaling the rise too would change the cradle's
    depth, and the marble sits on the cradle.
    """
    lateral, up, _forward = frame
    out = []
    for across, rise in section:
        scaled = across * width
        out.append(
            (
                centre[0] + lateral[0] * scaled + up[0] * rise,
                centre[1] + lateral[1] * scaled + up[1] * rise,
                centre[2] + lateral[2] * scaled + up[2] * rise,
            )
        )
    return out


def sweep_rings(rings: Sequence[Sequence[Sequence[float]]], name: str) -> TriMesh:
    """Join consecutive rings of equal width into an open triangle strip.

    The same invariant `marble3d.mesh._strip` enforces and for the same reason:
    triangles are only ever made between ring `i` and ring `i + 1`, so the
    phantom-span shape that cost the physics lab an afternoon - a triangle
    running from one end of a piece to the other - cannot be built here either.
    Open rather than closed across the section, because the channel is a gutter
    and the seam would be a lid over the marble.
    """
    if len(rings) < 2:
        raise ValueError(f"{name}: a sweep needs at least two rings")
    width = len(rings[0])
    if any(len(ring) != width for ring in rings):
        raise ValueError(f"{name}: every ring of a strip needs the same point count")
    vertices = [tuple(float(v) for v in point) for ring in rings for point in ring]
    indices: list[int] = []
    for row in range(len(rings) - 1):
        base = row * width
        above = base + width
        for column in range(width - 1):
            a, b = base + column, base + column + 1
            c, d = above + column, above + column + 1
            indices.extend((a, c, b, b, c, d))
    return TriMesh(vertices, indices, name)


class TrackRun(MarbleModule):
    """One run of the approved channel, as a collider and two sockets.

    Placed by world coordinate rather than by socket algebra, which is the one
    place this package departs from `marble3d.machine`'s rule that a module's
    position is derived. The reason is that the position *is* the contract here:
    the layout JSON records where the built channel is and the render draws it
    there, so a run that solved for its own placement could be self-consistent
    and in the wrong place. The joins are checked instead of assumed -
    `sloped.course` asserts that consecutive runs' sockets coincide, and they
    do, to zero.
    """

    def __init__(
        self,
        name: str,
        samples: int | None = None,
        spec: dict | None = None,
        path: Sequence[Sequence[float]] | None = None,
        open_side: tuple[float, int, int] | None = None,
        taper: tuple[float, float] | None = None,
        width_profile: tuple[float, int, int] | None = None,
        guard_boost: tuple[float, int, int, int, int] | None = None,
        entry_trim: Sequence[float | None] | None = None,
    ) -> None:
        super().__init__(name)
        # Per-sample section trim in profile units, or None. Usually installed
        # after construction by `set_entry_trim`; see there.
        self.entry_trim = None if entry_trim is None else list(entry_trim)
        # (extra, a, b, c, d): the guard rail is authored height before sample
        # `a`, eases up to `authored + extra` by `b`, holds it to `c`, and eases
        # back by `d`. A *window*, the same shape `open_side` uses, because a
        # containment repair belongs to a stretch and not to a whole run.
        #
        # **Why a guard rather than a bank or a radius.** The escapes this
        # exists for are marbles going over the top of a 0.26 rail: measured on
        # the launch's plunge, eleven of twelve left with their centres above
        # the 0.800 containment and 0.3 outside the rail's face, at 19 to 26
        # layout units per second with 4 to 9 of that lateral. The centreline,
        # the widths, the drops and the bank extremes are all pinned by
        # `sloped.contract` against the drawn asset, so they are not available;
        # the rail's height is not pinned, and it is the surface the marbles are
        # actually clearing.
        #
        # `v2_track.gd` carries the same window, so the drawn rail and the
        # collider agree. A physics-only wall is one a viewer watches a marble
        # bounce off nothing on.
        self.guard_boost = guard_boost
        # (side, a, b, c, d): the wall on `side` is at full height before
        # sample `a`, eases open between `a` and `b`, is open between `b` and
        # `c`, eases back between `c` and `d`, and is full again after. A
        # *window* rather than a ramp, because at the fork the wall has to be
        # there at the nose and gone in the middle - see `section_at`.
        self.open_side = open_side
        # (entry factor, exit factor) on the lateral width, eased between.
        #
        # This is how a 0.82-scale branch lead is fed by a full-width channel.
        # Without it the lead's mouth is 1.54 wide where leg3 hands over 1.88,
        # so a marble running the outside line arrives 0.17 layout units
        # outside the lead's own wall - on top of its guard, with nothing
        # beyond. Measured on the first run that reached the fork: three of
        # eight marbles left the course on the orange lead at 22 to 52 wu/s.
        self.taper = taper
        # (factor, hold to sample, blended by sample): the run opens `factor`
        # times its authored width, holds it, then eases back to authored.
        #
        # This is how the start's mixing region gets somewhere to happen. The
        # fan has 0.63 layout units of drop over 7.34 - 4.9 degrees - so a
        # stretch held wide inside it runs at 1.7 degrees once the drop either
        # side is paid for, and a marble that loses speed on a bumper there
        # never gets it back: measured, three quarters of the field trailing.
        # The launch runs at 25 to 43 degrees. So the fan stays wide to the
        # seam and the *launch* carries the wide mixing stretch and the
        # convergence, where there is energy to spend.
        self.width_profile = width_profile
        spec = layout.run(name) if spec is None else spec
        self.spec = spec
        self.scale = float(spec["scale"])
        self.role = str(spec["role"])
        if path is None:
            self.path, self.banks, self.tangents, self.widths = build_path(
                spec["controls"],
                float(spec["bank_gain"]),
                float(spec["bank_max"]),
                **({} if samples is None else {"samples": samples}),
            )
        else:
            # A join authored as a path rather than as controls, so its end
            # tangents are the ones that were solved for rather than whatever
            # a second pass of Catmull-Rom through them happens to produce.
            # Everything downstream - bank, width, section, collider - is the
            # channel's, so a join is the same moulding as the runs it joins.
            from sloped.pathing import BANK_EASE_ENDS, auto_bank, flat_tangents, resample, width_curve

            self.path = resample(
                [tuple(float(v) for v in point) for point in path],
                len(path) if samples is None else samples,
            )
            # `entry_bank_deg` and `exit_bank_deg` are degrees in the spec and
            # radians in `auto_bank`. A join that starts inside a banked turn
            # has to start at that turn's own roll, or the two cradles either
            # side of the seam are not the same surface; see
            # `sloped.pathing.auto_bank` for what that cost the fork.
            self.banks = auto_bank(
                self.path,
                float(spec["bank_gain"]),
                float(spec["bank_max"]),
                ease_ends=int(spec.get("bank_ease_ends", BANK_EASE_ENDS)),
                entry_bank=math.radians(float(spec.get("entry_bank_deg", 0.0))),
                exit_bank=math.radians(float(spec.get("exit_bank_deg", 0.0))),
            )
            self.tangents = flat_tangents(self.path)
            self.widths = width_curve(
                len(self.path),
                float(spec.get("entry_flare", 0.14)),
                float(spec.get("exit_flare", 0.09)),
            )
        self.frames = frames_for(self.path, self.banks, self.tangents)
        if taper is not None:
            entry, leaving = taper
            count = len(self.path)
            self.widths = [
                width * (entry + (leaving - entry) * _ease(index / max(count - 1, 1)))
                for index, width in enumerate(self.widths)
            ]
        if width_profile is not None:
            factor, hold_to, blend_to = width_profile
            span = max(blend_to - hold_to, 1)
            self.widths = [
                width
                * (
                    factor
                    if index <= hold_to
                    else 1.0
                    if index >= blend_to
                    else factor + (1.0 - factor) * _ease((index - hold_to) / span)
                )
                for index, width in enumerate(self.widths)
            ]
        self.section = channel_profile(self.scale)
        self.arc = arc_lengths(self.path)
        self._mesh: TriMesh | None = None

        # In simulation units, for everything downstream.
        self.sim_path = [to_sim_point(point) for point in self.path]
        self.sim_arc = [to_sim(value) for value in self.arc]
        self.clear_width = to_sim(layout.HERO_CLEAR_WIDTH * self.scale)
        self.floor_offset = to_sim(layout.FLOOR_Y * self.scale)
        self.containment = to_sim((layout.CONTAINMENT_TOP - layout.FLOOR_Y) * self.scale)

    # --- geometry -------------------------------------------------------

    OPEN_FLOOR = 0.05

    def wall_factor(self, index: int) -> float:
        """How much of one wall stands at one sample, as a fraction of full.

        One at both ends of the window and the window's own open fraction
        through the middle - `OPEN_FLOOR` unless the window carries a sixth
        entry. Not zero, because scaling a wall to nothing puts the guard's two
        coincident-across points at the same height as well, and a pair of
        coincident vertices is a degenerate triangle the solver takes a
        meaningless normal from. A 5% guard is a 0.04 layout unit lip.

        **The sixth entry is the fork's sorting crest.** With
        `sloped.joins.fork_trim` in place the two channels share an edge at
        leg3's east cradle edge, so what stands on that edge is the only thing
        between the two routes: at 5% it is a threshold a marble does not
        notice and three quarters of the field crosses, and raising it raises
        the speed a marble needs to get over. It is the one number the route
        split is set by, and `sloped.course.FORK_CREST` carries the scan.
        """
        if self.open_side is None:
            return 1.0
        _side, a, b, c, d = self.open_side[:5]
        floor = self.open_side[5] if len(self.open_side) > 5 else self.OPEN_FLOOR
        if index <= a or index >= d:
            return 1.0
        if b <= index <= c:
            return floor
        if index < b:
            t = (index - a) / max(b - a, 1)
            return 1.0 + (floor - 1.0) * (t * t * (3.0 - 2.0 * t))
        t = (index - c) / max(d - c, 1)
        return floor + (1.0 - floor) * (t * t * (3.0 - 2.0 * t))

    def guard_extra(self, index: int) -> float:
        """How much taller the rail is at this sample, in layout units.

        Zero unless `guard_boost` is set. Eased in and out with the same
        smoothstep the gates use, so the rail's top is a curve rather than a
        step - a step in a rail is a kerb a marble riding the wall trips on,
        which would be a new defect in the place an old one was being fixed.
        """
        if self.guard_boost is None:
            return 0.0
        extra, a, b, c, d = self.guard_boost
        if index <= a or index >= d:
            return 0.0
        if b <= index <= c:
            return float(extra) * self.scale
        if index < b:
            return float(extra) * self.scale * _ease((index - a) / max(b - a, 1))
        return float(extra) * self.scale * _ease((d - index) / max(d - c, 1))

    def containment_at(self, index: int) -> float:
        """The containment height at one sample, in simulation units.

        Per sample rather than the one scalar `containment`, because a local
        guard boost raises it locally - and a containment *check* that used the
        scalar while the collider used the boost would call a contained marble
        an escape. Both `sloped.race` and `sloped.startlab` read this.
        """
        return self.containment + to_sim(self.guard_extra(index))

    # How far the trimmed-away half is folded down, in layout units, and why
    # it is folded rather than deleted.
    #
    # A section with points removed has fewer points than its neighbours and
    # `sweep_rings` refuses unequal rings - correctly, because that invariant is
    # what stops a strip spanning from one end of a piece to the other. So the
    # trimmed points are all placed *at* the trim and walked down the section's
    # own `-up`, which at a 26-degree bank points down and **east**, away from
    # the channel the trim exists to stop overhanging. The result is a short
    # skirt hanging under the seam: a downward-facing wall a marble cannot rest
    # on, in the void the fork ridge grows into.
    TRIM_SKIRT = 0.30

    def entry_trim_at(self, index: int) -> float | None:
        """Where this sample's section is cut off, in profile units, or None."""
        if self.entry_trim is None or index >= len(self.entry_trim):
            return None
        return self.entry_trim[index]

    def set_entry_trim(self, table: Sequence[float | None] | None) -> None:
        """Install a per-sample section trim and drop the cached collider.

        Set after construction rather than passed in, because the trim is
        solved *against another run's* geometry - see `sloped.joins.fork_trim` -
        and that run has to exist before the answer does.
        """
        self.entry_trim = None if table is None else list(table)
        self._mesh = None

    def section_at(self, index: int) -> list[tuple[float, float]]:
        """The cross-section at one sample, with any opened wall, any local
        guard boost and any entry trim applied.

        Opening a wall scales its points' height toward the cradle's own edge
        rather than deleting them, so the section keeps its point count and the
        strip builder keeps its invariant. The trim keeps it the same way.
        """
        extra = self.guard_extra(index)
        if extra > 0.0:
            crown = layout.LIP_CROWN * self.scale
            section = [
                # Only the rail's own points move, and only upward. The lip and
                # the cradle are the running surface and are left exactly as
                # the asset draws them.
                (across, up + extra) if up > crown else (across, up)
                for across, up in self.section
            ]
        else:
            section = self.section
        if self.open_side is None:
            return self._trimmed(section, index)
        factor = self.wall_factor(index)
        if factor >= 1.0:
            return self._trimmed(section, index)
        side = self.open_side[0]
        half = layout.CHANNEL_HALF * self.scale
        edge = layout.floor_y_at(layout.CHANNEL_HALF) * self.scale
        out: list[tuple[float, float]] = []
        for across, up in section:
            # `side` of zero opens **both** guards. The sprint needs it: the
            # merge apron is built around its first three units and the
            # sprint's own guard rails stand up inside that apron, so the strip
            # of apron outside the channel has a ledge along the top of each
            # rail with the apron's roof over it. Measured, an orange marble
            # crossing the apron came to rest on the east rail at across
            # +2.337, its centre 0.43 simulation units above the apron floor
            # under it and 0.74 below the roof - held there by geometry, at
            # 0.52 wu/s. It is also where V1 lost 319 of its 747 marbles, all
            # booked to `blue[100]`, which is the sample blue's exit hands over
            # on. With both rails opened the apron is one surface from its
            # outer wall to the cradle and there is no ledge to sit on.
            if (side == 0.0 or across * side > half * 0.98) and abs(across) > half * 0.98 and up > edge:
                out.append((across, edge + (up - edge) * factor))
            else:
                out.append((across, up))
        return self._trimmed(out, index)

    def _trimmed(
        self, section: list[tuple[float, float]], index: int
    ) -> list[tuple[float, float]]:
        """`section` with everything west of this sample's trim folded away.

        The point count is preserved; see `TRIM_SKIRT`.
        """
        trim = self.entry_trim_at(index)
        if trim is None:
            return section
        cut = trim * self.scale
        count = sum(1 for across, _up in section if across < cut)
        if not 0 < count < len(section):
            return section
        seam = _interpolate_rise(section, cut)
        skirt = self.TRIM_SKIRT * self.scale
        # `count - step` rather than `count - 1 - step`: the shallowest folded
        # point stays one step *below* the seam rather than on it. At a trim of
        # exactly zero - which is the mouth, where orange's cradle bottom sits
        # on leg3's east cradle edge - a point on the seam is the section's own
        # centreline point twice over, and `check_mesh` reports the zero-area
        # triangle between them rather than the solver quietly taking a
        # meaningless normal from it.
        return [
            (cut, seam - skirt * (count - step) / count) for step in range(count)
        ] + section[count:]

    def local_colliders(self) -> list[TriMesh]:
        if self._mesh is None:
            rings = [
                [
                    to_sim_point(point)
                    for point in ring_points(
                        self.path[index],
                        self.frames[index],
                        self.section_at(index),
                        self.widths[index],
                    )
                ]
                for index in range(len(self.path))
            ]
            self._mesh = sweep_rings(rings, f"{self.id}_channel")
        return [self._mesh]

    def _socket(self, index: int, name: str) -> Socket:
        """The frame a marble crosses at one end of the run.

        Seated on the cradle's lowest point rather than on the centreline, so
        the socket's origin is where a marble's contact is and its `height` is
        the containment above that. A socket on the centreline would be 0.456
        simulation units in the air and every clearance check downstream would
        be measured from thin air.
        """
        lateral, up, forward = self.frames[index]
        centre = self.sim_path[index]
        seat = tuple(centre[axis] + up[axis] * self.floor_offset for axis in range(3))
        return Socket(
            name=name,
            frame=Transform(position=seat, rotation=basis_from_forward_up(forward, up)),
            kind=GUIDED,
            width=self.clear_width,
            height=self.containment,
        )

    def local_sockets(self) -> dict[str, Socket]:
        return {"entry": self._socket(0, "entry"), "exit": self._socket(len(self.path) - 1, "exit")}

    def local_bounds(self) -> Aabb:
        """The channel's own extent, grown by a diameter.

        Taken from the collider rather than from the centreline, because a
        banked channel's shell reaches a full half-width sideways and the
        occupancy test in `marble3d.simulation` uses this box to decide which
        module a marble is in.
        """
        bounds = self.local_colliders()[0].aabb()
        return Aabb(
            tuple(value - MARBLE_DIAMETER for value in bounds.lower),
            tuple(value + MARBLE_DIAMETER for value in bounds.upper),
        )

    # --- where a marble rides -------------------------------------------

    def surface_point(self, index: int, across_profile: float = 0.0) -> tuple[float, float, float]:
        """A point on the cradle, in simulation units, from the analytic arc.

        `across_profile` is in the section's *own* coordinates - zero on the
        centreline, `layout.CHANNEL_HALF` at the channel edge - before the
        run's profile scale and before the per-sample width factor. Applying
        both here in the same order `ring_points` applies them is what makes
        this the same point the collider has a vertex at, which is the whole
        value of it: the probe reaches it from the circle formula and the
        collider reaches it through a strip, an OBJ file and Bullet's loader.
        """
        lateral, up, _forward = self.frames[index]
        centre = self.sim_path[index]
        rise = to_sim(layout.floor_y_at(across_profile) * self.scale)
        sideways = to_sim(across_profile * self.scale * self.widths[index])
        return tuple(
            centre[axis] + up[axis] * rise + lateral[axis] * sideways for axis in range(3)
        )

    def seat_at(self, index: int, across_profile: float = 0.0) -> tuple[float, float, float]:
        """Where a marble's centre rests on the cradle, in simulation units.

        `v2_track.running_point` is the same expression in layout units:
        centre + up * (radius + floor_offset). A radius along the frame's up
        rather than along the cradle's own normal, which off the centreline is
        an approximation of up to 9% of a radius laterally - immaterial for
        placing a field, because the solver settles it in the first few ticks,
        and not used for anything that has to be exact.
        """
        _lateral, up, _forward = self.frames[index]
        surface = self.surface_point(index, across_profile)
        return tuple(surface[axis] + up[axis] * MARBLE_RADIUS for axis in range(3))

    def half_profile(self) -> float:
        """The channel's clear half width in section coordinates."""
        return layout.CHANNEL_HALF

    def index_at_length(self, distance: float) -> int:
        """The sample nearest a given arc length along the run, in sim units."""
        target = min(max(distance, 0.0), self.sim_arc[-1])
        return min(
            range(len(self.sim_arc)), key=lambda index: abs(self.sim_arc[index] - target)
        )

    def index_near(self, layout_point) -> int:
        """The sample nearest a layout-unit point. How a station finds its place."""
        return nearest_index(self.path, layout_point)

    def heading_deg(self, index: int) -> float:
        forward = self.tangents[min(max(index, 0), len(self.tangents) - 1)]
        return math.degrees(math.atan2(forward[0], forward[2]))

    # --- validation -----------------------------------------------------

    def local_probes(self) -> list[Probe]:
        """Rays fired at the cradle from above, from the analytic surface.

        One every eighth sample, at the centreline and at three-quarters of the
        half width each side, aimed straight down the rolled frame's own up
        axis. They come from `seat_at`, which is `running_point`'s expression,
        while the mesh comes from `channel_profile` through the strip builder
        and an OBJ file and Bullet's loader - so the two agree only if both are
        right. A truncated chunk, a missing end section, a run placed at the
        wrong transform and a section carried on the wrong lateral all break it.
        """
        probes: list[Probe] = []
        reach = 3.0 * MARBLE_RADIUS
        half = layout.CHANNEL_HALF
        for index in range(0, len(self.path), 8):
            _lateral, up, _forward = self.frames[index]
            for fraction in (-0.75, 0.0, 0.75):
                surface = self.surface_point(index, fraction * half)
                probes.append(
                    Probe(
                        start=tuple(surface[axis] + up[axis] * reach for axis in range(3)),
                        end=tuple(surface[axis] - up[axis] * reach for axis in range(3)),
                        expect_hit=True,
                        expected_point=surface,
                        # A facet chord's own sagitta: the ray lands between two
                        # ring rows and the strip cuts inside the arc there.
                        tolerance=0.03,
                        label=f"{self.id}.cradle[{index}]@{fraction:+.2f}",
                    )
                )
        return probes

    def describe(self) -> dict:
        return {
            "kind": "TrackRun",
            "role": self.role,
            "profile_scale": self.scale,
            "samples": len(self.path),
            "guard_boost": (
                None if self.guard_boost is None else list(self.guard_boost)
            ),
            "clear_width": round(self.clear_width, 6),
            "floor_offset": round(self.floor_offset, 6),
            "containment": round(self.containment, 6),
            "length": round(self.sim_arc[-1], 6),
            "layout_length": round(self.arc[-1], 6),
            "drop": round(self.sim_path[0][1] - self.sim_path[-1][1], 6),
            "bank_max_deg": round(max(abs(math.degrees(v)) for v in self.banks), 4),
            "taper": None if self.taper is None else [round(v, 4) for v in self.taper],
            "entry_heading_deg": round(self.heading_deg(0), 4),
            "exit_heading_deg": round(self.heading_deg(len(self.path) - 1), 4),
        }

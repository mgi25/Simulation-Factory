"""The six race moments, as colliders and actuators rather than as shapes.

`course_modules.gd` builds these to be photographed. Read as physics most of
them are close to right and each has one number that is not, because a still
frame does not test containment or reachability. The corrections are listed
here and again in `docs/sloped_race_v1.md`, and every one is local to a
station:

* **Start.** Three things, all measured. The drawn gate bar sits at z = -3.22
  and the eight waiting racers at z = -2.74 - *downstream* of it - so the gate
  as drawn is behind the field and cannot hold it; the physical gate is a bar of
  eight paddles at the front of the field instead, and the drawn bar reads as
  the gantry behind the grid, which is what it looks like anyway. The lane
  dividers pinch a 0.57 racer in a 0.63 bay and are rebuilt as floor ridges
  (see `StartGrid`). And the fan's mouth hands over to a channel whose cradle it
  does not match: the trough's dish is 0.16 deep across 1.02 and the channel's
  is 0.211 across 0.94, so a marble crossing the seam meets a step of up to
  0.09 - enough that the last marble of the queue, arriving slowly, stopped
  dead on it in every seed. The trough's section now blends into the channel's
  over the last third of the fan.
* **Mixer.** The outer pins of the five-pin row stand at +/-1.04 and the
  channel's clear half width is 0.94, so two of the nine pins are inside the
  wall. The physical rows are pitched to fit the channel: five across the clear
  width and four in the gaps. Their *height* is the asset's and it is the whole
  mechanism - the drawn pins reach y = -0.06 in the module's frame against a
  cradle at -0.26, so they stand 0.20 above the floor against a 0.57 racer.
  They are studs a marble rides over and is kicked by, not a barrier it has to
  find a gap in. Built at their full 0.56 length instead, five of them across a
  1.88 channel leave 0.25 gaps and the first eight-marble run jammed six
  marbles against them in four seconds.
* **Obstacle.** The blades reach 1.39 from the shaft and sweep from y = -0.37
  to +0.41 in the module's frame, so as drawn they pass through both the
  channel floor at -0.26 and the acrylic guard at +0.28. The physical blades
  sweep inside the channel and above its cradle. Section 7 lists obstacle
  clearance among the allowed corrections.
* **Split.** Relocated. See `docs/sloped_race_v1_junction_finding.md`.
* **Merge.** A roofed funnel apron. See the same file, and `MergeCatch` below.
* **Finish.** The deck and the eight catch lanes are built as authored; the
  finish *line* is the sprint's own exit socket, which is where the timing
  happens, and the deck is what the field runs out onto afterwards.

Everything here is authored in **layout** units, from the asset's own
constants, and converted once through `sloped.scale`.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

from marble3d.geometry import GUIDED, Socket, Transform, basis_from_forward_up
from marble3d.mesh import Aabb, TriMesh
from marble3d.modules.base import Actuator, MarbleModule, Probe
from marble3d.units import MARBLE_DIAMETER, MARBLE_RADIUS

from sloped import layout
from sloped.scale import LAYOUT_TO_SIM, to_sim, to_sim_point
from sloped.solids import box_shell, height_field, merge_meshes, plate, tube, wall_strip
from sloped.track import TrackRun

__all__ = [
    "StartGrid",
    "Mixer",
    "Spinners",
    "ForkRidge",
    "MergeCatch",
    "FinishDeck",
    "Spinner",
]


# Blue's own exit gradient, from the layout contract's `slope_deg.exit` for the
# blue lobe. The merge apron's upstream fall matches it; see `MergeCatch._floor`.
BLUE_ARRIVAL_SLOPE = math.radians(4.5104)


def _yaw_frame(yaw_deg: float) -> tuple[tuple, tuple, tuple]:
    """A module frame from a Godot yaw: local +Z downhill, +X to its left.

    `course_machine._placed` sets `rotation.y = yaw` and Godot's basis for that
    maps local (x, y, z) to world (x cos + z sin, y, -x sin + z cos). The three
    axes below are that basis' columns, so a point authored in
    `course_modules.gd`'s frame lands where the asset puts it.
    """
    angle = math.radians(yaw_deg)
    cos, sin = math.cos(angle), math.sin(angle)
    return ((cos, 0.0, -sin), (0.0, 1.0, 0.0), (sin, 0.0, cos))


def _place(origin, frame, point) -> tuple[float, float, float]:
    """A layout point in a yawed module frame, as a simulation-unit world point."""
    ax, ay, az = frame
    world = tuple(
        origin[axis] + ax[axis] * point[0] + ay[axis] * point[1] + az[axis] * point[2]
        for axis in range(3)
    )
    return to_sim_point(world)


# --- START ----------------------------------------------------------------


class StartGrid(MarbleModule):
    """Eight racers abreast on a shelf, one gate, and a fan into the channel.

    The trough is the asset's: a cradle `-0.30 + 0.16 t^2` across a half width
    that eases from 2.73 at the gate to 1.02 where it hands off, on a path from
    (0, -0.02, -3.40) to the launch run's entry in the module's own frame. Seven
    round fins follow their own lanes inward, which is what keeps the field in
    eight lanes at rest and lets it merge on the move rather than at the line.

    Section 13 asks for a wide, readable, side-by-side start and specifically
    not a single-file chute. The eight bays are 0.63 apart against a 0.57
    racer, so the field is 4.4 layout units across at the line and one channel
    width four units later - a fan, and the convergence happens on the deck the
    way it does on the real sample.
    """

    SAMPLES = 40
    FIN_RADIUS = 0.055          # the asset's round stock
    FIN_END = 0.50              # the fraction of the fan the dividers cover

    # How far along the fan each of the seven dividers runs, west to east.
    # `None` is the flat `FIN_END` for all seven - what V1 shipped, and what
    # `docs/sloped_race_v1.md` measured its 8.87x slot bias on.
    # `sloped.startlab` scans alternatives.
    FIN_SCHEDULE: tuple[float, ...] | None = None

    # How far down the fan each bay's paddle and resting place sit, in layout
    # units, west to east. Zero is V1's straight line across all eight.
    #
    # A stagger is the standard physical answer to unequal path length - an
    # athletics track and a swimming pool both use one - and here the path
    # lengths really are unequal: `docs/sloped_race_v1.md` measures the outer
    # bay reaching the launch seam 76 ticks after the inner one because it has
    # 1.27 layout units further to travel sideways through a trough that
    # funnels eight marbles onto one line. The queue that forms at the funnel
    # is ordered by lateral distance, which is to say by bay index.
    BAY_STAGGER: tuple[float, ...] = (0.0,) * 8

    # Studs on the trough floor, as (t along the fan, across as a fraction of
    # the half width there, height in layout units). See `local_colliders`.
    DEFLECTORS: tuple[tuple[float, float, float], ...] = ()

    def __init__(
        self,
        module_id: str = "start",
        launch: TrackRun | None = None,
        fin_schedule: tuple[float, ...] | None = None,
        bay_stagger: tuple[float, ...] | None = None,
        deflectors: tuple[tuple[float, float, float], ...] | None = None,
    ) -> None:
        super().__init__(module_id)
        self.deflectors = self.DEFLECTORS if deflectors is None else tuple(deflectors)
        schedule = fin_schedule if fin_schedule is not None else self.FIN_SCHEDULE
        if schedule is not None and len(schedule) != layout.BAYS - 1:
            raise ValueError(
                f"a fin schedule needs {layout.BAYS - 1} entries, one per divider, "
                f"not {len(schedule)}"
            )
        self.fin_schedule = schedule
        stagger = self.BAY_STAGGER if bay_stagger is None else bay_stagger
        if len(stagger) != layout.BAYS:
            raise ValueError(
                f"a bay stagger needs {layout.BAYS} entries, one per bay, not {len(stagger)}"
            )
        self.bay_stagger = tuple(float(v) for v in stagger)
        self.origin = layout.NODES["start"]
        launch_entry = (launch.path[0] if launch is not None else layout.run("launch")["controls"][0])
        self.yaw_deg = math.degrees(
            math.atan2(launch_entry[0] - self.origin[0], launch_entry[2] - self.origin[2])
        )
        self.frame = _yaw_frame(self.yaw_deg)
        angle = math.radians(self.yaw_deg)
        cos, sin = math.cos(angle), math.sin(angle)
        delta = tuple(launch_entry[axis] - self.origin[axis] for axis in range(3))
        self.exit_local = (
            delta[0] * cos - delta[2] * sin,
            delta[1],
            delta[0] * sin + delta[2] * cos,
        )
        self._mesh: TriMesh | None = None

        # The gate stands at the downstream face of the waiting field. The
        # drawn bar is 0.82 units up-course of this; see the module docstring.
        self.gate_z = self._field_z() + layout.MARBLE_RADIUS + 0.06
        self.release_time = 0.30
        self.release_travel = 0.62

    # --- the trough -----------------------------------------------------

    def _field_z(self) -> float:
        return -layout.GROOVE_LENGTH + 0.66

    def _field_z_for(self, index: int) -> float:
        """Where bay `index` waits, with its stagger applied."""
        return self._field_z() + self.bay_stagger[index]

    def _gate_z_for(self, index: int) -> float:
        """The downstream face of bay `index`'s waiting marble."""
        return self._field_z_for(index) + layout.MARBLE_RADIUS + 0.06

    def _half_at(self, t: float) -> float:
        # The asset eases to 1.02; the physics eases to the channel's own 0.94,
        # so the fan's mouth and the channel's mouth are the same width. The
        # 0.08 difference puts the physical apron wall a seventh of a marble
        # diameter inside the drawn one, at the one place the drawn one is
        # hidden behind the launch channel's own lip.
        eased = _smoothstep(0.10, 1.0, t)
        front = layout.CHANNEL_HALF
        return layout.START_BACK_HALF + (front - layout.START_BACK_HALF) * eased

    def _path_at(self, t: float) -> tuple[float, float, float]:
        back = (0.0, layout.DECK_TOP - 0.02, -layout.GROOVE_LENGTH)
        front = self.exit_local
        return tuple(back[axis] + (front[axis] - back[axis]) * t for axis in range(3))

    # Where the trough's own dish gives way to the channel's cradle. A third of
    # the fan, which is the shortest blend that leaves no step a slow marble
    # can stop on and the longest that keeps the grid's own shallow dish over
    # the part of the fan the field is actually standing on.
    BLEND_FROM = 0.66

    def _cradle(self, across: float, half: float, t: float = 0.0) -> float:
        """The trough floor: the asset's dish, blending into the channel's cradle.

        `course_modules._cradle` is `-0.30 + 0.16 u^2` across the trough's own
        half width - a shallow pan 0.16 deep. The launch channel it hands to is
        a circular cradle 0.211 deep across a narrower 0.94. Sweeping the pan
        all the way to the seam leaves the channel's cradle standing 0.04 above
        the pan on the centreline and 0.09 above it at the edges, and a marble
        that arrives at the seam slowly - which the last of eight always does -
        stops against that step and stays there: measured in every seed, one
        marble of eight, 45 seconds in the trough with its top speed at 9 wu/s.

        So the section blends. At `t = 1` this returns the channel's own cradle
        exactly, and `_half_at` ends at the channel's own half width, so the
        two surfaces are one surface at the seam.
        """
        u = min(max(abs(across) / max(half, 0.001), 0.0), 1.0)
        dish = -0.30 + 0.16 * u * u
        cradle = layout.floor_y_at(u * layout.CHANNEL_HALF)
        return dish + (cradle - dish) * _smoothstep(self.BLEND_FROM, 1.0, t)

    def _t_at_z(self, z: float) -> float:
        back = -layout.GROOVE_LENGTH
        front = self.exit_local[2]
        return min(max((z - back) / (front - back), 0.0), 1.0)

    def local_colliders(self) -> list[TriMesh]:
        if self._mesh is not None:
            return [self._mesh]
        pieces: list[TriMesh] = []
        rows = self.SAMPLES
        columns = 10

        # The trough floor and its two low walls, as one strip in the module's
        # own frame. Authored as rings rather than through `height_field`
        # because the half width changes per row, so the across range does too.
        rings: list[list[tuple[float, float, float]]] = []
        for row in range(rows):
            t = row / (rows - 1)
            half = self._half_at(t)
            centre = self._path_at(t)
            ring: list[tuple[float, float, float]] = []
            wall = 0.32
            ring.append(_place(self.origin, self.frame, (-(half + 0.15), centre[1] + wall, centre[2])))
            for column in range(columns + 1):
                across = -half + 2.0 * half * column / columns
                rise = self._cradle(across, half, t)
                ring.append(
                    _place(self.origin, self.frame, (across, centre[1] + rise, centre[2]))
                )
            ring.append(_place(self.origin, self.frame, (half + 0.15, centre[1] + wall, centre[2])))
            rings.append(ring)
        pieces.append(_strip(rings, f"{self.id}_trough"))

        # Seven lane dividers, and the two corrections they need. Both come out
        # of the same measurement and neither is cosmetic.
        #
        # **Ridges on the cradle, not tubes in the marble's path.** The bays are
        # 0.63 apart and the drawn fins are 0.11 across, so the clear span
        # between two of them is 0.52 against a 0.57 racer: as drawn, every
        # marble on the grid is pinched between its two fins - 0.019 simulation
        # units of overlap on each side, measured - and eight marbles held in a
        # light vice do not roll down a 4.9-degree shelf. The first eight-marble
        # run reached 0.1 wu/s in three seconds and stayed there. No fin height
        # fixes it: raising the tube closes the gap at the marble's own contact
        # height about as fast as it opens it at the equator. No fin radius
        # fixes it either, because 0.63 less a 0.57 racer leaves 0.06 for two
        # fins. So the divider sits with its axis on the cradle, at the drawn
        # stock's radius, presenting an 0.11 bump. A resting marble clears it by
        # 0.13 across and a drifting one meets it after 0.13 - well before the
        # 0.315 that would put it in the next lane, which is the only thing a
        # lane divider has to do.
        #
        # **They stop at FIN_END.** The dividers converge with the trough, so
        # the lane pitch is 0.63 at the line and 0.24 at the throat, a third of
        # a marble. Past the point where two ridges are closer than a marble
        # plus its own contact geometry the field is being crushed rather than
        # guided; the eight-marble run that stalled had four marbles wedged
        # between converging ridges 3.5 units down the fan. At FIN_END the
        # pitch is still 0.47 with 0.08 to spare, and the last 3.7 units of the
        # fan are one converging channel - which is where the asset says the
        # convergence belongs: eight grooves that bend inward and become one
        # chute at the lip.
        for index in range(layout.BAYS - 1):
            end = self.FIN_END if self.fin_schedule is None else self.fin_schedule[index]
            if end <= 0.0:
                continue
            lane: list[tuple[float, float, float]] = []
            for row in range(int(round(end * (rows - 1))) + 1):
                t = row / (rows - 1)
                half = self._half_at(t)
                spread = half / layout.START_BACK_HALF
                centre = self._path_at(t)
                across = (_bay_x(index) + layout.BAY_PITCH * 0.5) * spread
                lane.append(
                    _place(
                        self.origin,
                        self.frame,
                        (across, centre[1] + self._cradle(across, half, t), centre[2]),
                    )
                )
            for step in range(len(lane) - 1):
                pieces.append(
                    tube(
                        lane[step],
                        lane[step + 1],
                        to_sim(self.FIN_RADIUS),
                        segments=8,
                        name=f"{self.id}_fin{index}_{step}",
                        caps=step in (0, len(lane) - 2),
                    )
                )

        # Deflectors: studs standing on the trough floor at chosen places in
        # the fan, as (t along, across as a fraction of the half width there,
        # height in layout units).
        #
        # The fan's second half is where the slot bias is made -
        # `docs/sloped_race_v1_start_finding.md` measures the eight slots
        # within three ticks of each other at t = 0.25 and 76 ticks apart at
        # the seam - because the bare converging trough funnels all eight onto
        # one line and the queue that forms there is ordered by how far each
        # bay had to come. A stud row is what turns that funnel into a
        # scattering region: which side of a stud a marble passes is decided by
        # a fraction of its own radius, so the delay it takes is not monotone
        # in where it started.
        #
        # They stand on the *floor* at the marble's own contact height for the
        # same reason the lane dividers do, and `Mixer.PIN_HEIGHT` records what
        # happens when a stud in a channel is tall enough to lever rather than
        # deflect. Here the field is at 7 to 11 wu/s rather than the 50 it
        # reaches by leg1, so the same stud is a much gentler thing.
        for order, (at, across_fraction, height) in enumerate(self.deflectors):
            half = self._half_at(at)
            centre = self._path_at(at)
            across = across_fraction * half
            foot = _place(
                self.origin,
                self.frame,
                (across, centre[1] + self._cradle(across, half, at), centre[2]),
            )
            head = _place(
                self.origin,
                self.frame,
                (across, centre[1] + self._cradle(across, half, at) + height, centre[2]),
            )
            pieces.append(
                tube(
                    foot,
                    head,
                    to_sim(layout.MIXER_PIN_RADIUS),
                    segments=8,
                    name=f"{self.id}_deflector{order}",
                    caps=True,
                )
            )

        # A back stop, so a marble nudged up-course at release cannot leave.
        t_back = 0.0
        half_back = self._half_at(t_back)
        centre_back = self._path_at(t_back)
        pieces.append(
            plate(
                [
                    _place(self.origin, self.frame, (-half_back, centre_back[1] - 0.30, centre_back[2])),
                    _place(self.origin, self.frame, (half_back, centre_back[1] - 0.30, centre_back[2])),
                    _place(self.origin, self.frame, (half_back, centre_back[1] + 0.32, centre_back[2])),
                    _place(self.origin, self.frame, (-half_back, centre_back[1] + 0.32, centre_back[2])),
                ],
                name=f"{self.id}_backstop",
                steps=4,
            )
        )
        self._mesh = merge_meshes(pieces, f"{self.id}_grid")
        return [self._mesh]

    # --- the gate -------------------------------------------------------

    def local_actuators(self) -> list[Actuator]:
        """One paddle per bay, lifted together.

        A `LinearGate` per bay rather than one bar across all eight, because a
        single box spanning 4.4 units would also span the seven fins and the
        two rails, and a kinematic box that starts inside static geometry is a
        contact the solver has to resolve on tick one. Eight paddles in eight
        bays touch nothing.

        ## The axis order, and why it was wrong

        `basis_from_forward_up` is explicit that "`forward` becomes +X
        exactly", so a box built with that rotation has its local **X** along
        whatever was passed as forward, its Y along up, and its Z across. The
        `Spinner` below passes the blade's own long axis as forward and so its
        extents read (long, height, thin) correctly. This gate passes the
        *direction the marbles travel* - a second, equally natural reading of
        the word - and for a while still listed its extents as (bay width,
        height, thin).

        That made every paddle a 0.9-long, 0.16-wide blade lying **down the
        middle of its own bay** instead of a barrier across it, and it showed
        up as the deepest overlap anywhere in the project: all eight marbles
        seeded 0.34 simulation units - a third of a diameter - inside their own
        paddle, with a contact normal along the flow rather than across it,
        pushed out over the first forty ticks. A gate rotated into a rail does
        not gate; the field left the grid because the fan is downhill, not
        because anything released it.

        The extents are therefore (thin, height, bay width): thin along the
        flow, which is the axis a gate is thin on.
        """
        from marble3d.modules.base import LinearGate

        gates: list[Actuator] = []
        for index in range(layout.BAYS):
            gate_z = self._gate_z_for(index)
            t = self._t_at_z(gate_z)
            half = self._half_at(t)
            centre = self._path_at(t)
            spread = half / layout.START_BACK_HALF
            across = _bay_x(index) * spread
            rise = self._cradle(across, half, t)
            position = _place(
                self.origin,
                self.frame,
                (across, centre[1] + rise + 0.5 * layout.GATE_HEIGHT, gate_z),
            )
            gates.append(
                LinearGate(
                    name=f"paddle{index}",
                    # (along, up, across). See the docstring: the rotation puts
                    # the flow direction on local X, so the thin axis is X.
                    half_extents=(
                        to_sim(0.045),
                        to_sim(0.5 * layout.GATE_HEIGHT),
                        to_sim(0.5 * (layout.BAY_PITCH - 0.12)),
                    ),
                    rest=Transform(position=position, rotation=self._rotation()),
                    travel=(0.0, to_sim(self.release_travel), 0.0),
                    release_time=self.release_time,
                    duration=0.16,
                )
            )
        return gates

    def _rotation(self):
        ax, ay, az = self.frame
        return basis_from_forward_up(az, ay)

    # --- what the simulation needs --------------------------------------

    def marble_starts(self) -> list[Transform]:
        """Eight resting places, one per bay, outermost bay first.

        Ordered from -X to +X so that slot 0 is the same physical bay in every
        run and every report. `marble3d.simulation` permutes marble identity
        across these, which is what keeps a slot-bias measurement about the
        geometry rather than about which colour started where.
        """
        rotation = self._rotation()
        starts: list[Transform] = []
        for index in range(layout.BAYS):
            field_z = self._field_z_for(index)
            t = self._t_at_z(field_z)
            half = self._half_at(t)
            centre = self._path_at(t)
            spread = half / layout.START_BACK_HALF
            across = _bay_x(index) * spread
            rise = self._cradle(across, half, t)
            starts.append(
                Transform(
                    position=_place(
                        self.origin,
                        self.frame,
                        (across, centre[1] + rise, field_z),
                    ),
                    rotation=rotation,
                )
            )
        # A marble sits a radius above the cradle it rests in, not on it.
        return [
            Transform(
                position=(start.position[0], start.position[1] + MARBLE_RADIUS, start.position[2]),
                rotation=start.rotation,
            )
            for start in starts
        ]

    def local_sockets(self) -> dict[str, Socket]:
        t = 1.0
        centre = self._path_at(t)
        exit_point = _place(self.origin, self.frame, (0.0, centre[1] - 0.30, centre[2]))
        forward = tuple(
            self.frame[2][axis] * math.cos(0.0) for axis in range(3)
        )
        return {
            "exit": Socket(
                name="exit",
                frame=Transform(position=exit_point, rotation=basis_from_forward_up(forward, (0.0, 1.0, 0.0))),
                kind=GUIDED,
                width=to_sim(2.0 * layout.START_FRONT_HALF),
                height=to_sim(0.62),
            )
        }

    def local_bounds(self) -> Aabb:
        bounds = self.local_colliders()[0].aabb()
        return Aabb(
            tuple(value - MARBLE_DIAMETER for value in bounds.lower),
            tuple(value + MARBLE_DIAMETER for value in bounds.upper),
        )

    def local_probes(self) -> list[Probe]:
        probes: list[Probe] = []
        reach = 3.0 * MARBLE_RADIUS
        # Sampled at bay centres rather than at fractions of the half width,
        # because a fin sits at every bay boundary and a probe on the boundary
        # measures the fin instead of the floor. The first version put one on
        # the centreline, where fin 3 is.
        # One row per bay, because a stagger puts the eight paddles on
        # different rows; with no stagger this is the one row it always was.
        gate_rows = {
            int(round(self._t_at_z(self._gate_z_for(index)) * (self.SAMPLES - 1)))
            for index in range(layout.BAYS)
        }
        for row in range(0, self.SAMPLES, 6):
            # The gate is a kinematic body owned by this module, so a probe
            # fired where it stands measures the paddle and reports the floor
            # as 0.76 too high. Skipped rather than loosened, because the
            # tolerance is what makes the rest of the check worth running.
            if any(abs(row - gate_row) <= 1 for gate_row in gate_rows):
                continue
            t = row / (self.SAMPLES - 1)
            half = self._half_at(t)
            centre = self._path_at(t)
            spread = half / layout.START_BACK_HALF
            for bay in (0, 3, 7):
                across = _bay_x(bay) * spread
                surface = _place(
                    self.origin,
                    self.frame,
                    (across, centre[1] + self._cradle(across, half, t), centre[2]),
                )
                probes.append(
                    Probe(
                        start=(surface[0], surface[1] + reach, surface[2]),
                        end=(surface[0], surface[1] - reach, surface[2]),
                        expect_hit=True,
                        expected_point=surface,
                        tolerance=0.05,
                        label=f"{self.id}.trough[{row}]bay{bay}",
                    )
                )
        return probes

    def describe(self) -> dict[str, Any]:
        return {
            "kind": "StartGrid",
            "bays": layout.BAYS,
            "bay_pitch": round(to_sim(layout.BAY_PITCH), 6),
            "field_width": round(to_sim(layout.BAY_PITCH * (layout.BAYS - 1)), 6),
            "yaw_deg": round(self.yaw_deg, 4),
            "gate_z": round(self.gate_z, 4),
            "release_time": self.release_time,
            "bay_stagger": [round(v, 4) for v in self.bay_stagger],
            "fin_schedule": (
                None if self.fin_schedule is None else [round(v, 4) for v in self.fin_schedule]
            ),
            "deflectors": [[round(v, 4) for v in row] for row in self.deflectors],
        }


def _bay_x(index: int) -> float:
    return (index - (layout.BAYS - 1) * 0.5) * layout.BAY_PITCH


def _smoothstep(edge0: float, edge1: float, value: float) -> float:
    u = min(1.0, max(0.0, (value - edge0) / (edge1 - edge0)))
    return u * u * (3.0 - 2.0 * u)


def _strip(rings, name: str) -> TriMesh:
    width = len(rings[0])
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


# --- MIXER ----------------------------------------------------------------


class Mixer(MarbleModule):
    """Two staggered pin rows in the channel, and the reason they are pitched.

    The asset's rows are five pins and four at 0.52 pitch, which puts the outer
    pins of the long row at +/-1.04 against a clear half width of 0.94 - two of
    the nine are inside the wall, where a marble cannot reach them. The rows
    here span the clear width instead: five pins across it and four in the
    gaps, same count, same stagger, same 0.075 stock, same two rows 0.48 apart.

    Section 14 is explicit that this is the fairness mechanism and that it is
    unverified. Nothing about the shape argues that it works; the slot-bias
    benchmark is what decides, and it is run on the field that comes out of
    here rather than on the field that goes in.
    """

    def __init__(
        self,
        module_id: str,
        run: TrackRun,
        at: int | None = None,
        pin_height: float | None = None,
    ) -> None:
        super().__init__(module_id)
        self.run = run
        # `at` overrides the recorded `mix` node so `sloped.startlab` can ask
        # what the same nine pins do earlier, where the field is still a clump
        # rather than eighteen units of single file.
        self.index = run.index_near(layout.NODES["mix"]) if at is None else int(at)
        self.pin_height = self.PIN_HEIGHT if pin_height is None else float(pin_height)
        self._mesh: TriMesh | None = None

    def _pins(self) -> list[tuple[int, float]]:
        """(sample offset, across in profile units) for each pin."""
        half = layout.CHANNEL_HALF * self.run.scale
        spacing = self.run.arc[-1] / (len(self.run.path) - 1)
        rows: list[tuple[int, float]] = []
        for row, count in enumerate(layout.MIXER_ROW_COUNTS):
            offset = int(round(layout.MIXER_ROW_Z[row] / spacing))
            for pin in range(count):
                # Five across the clear width, four in the gaps between them.
                span = (pin - (count - 1) * 0.5) * (2.0 * half * 0.86 / (count - 1)) if count > 1 else 0.0
                rows.append((offset, span / self.run.scale))
        return rows

    # The drawn pin runs from y = -0.62 to -0.06 in the module's frame and the
    # cradle's lowest point is at -0.26, so 0.20 of it stands above the floor
    # and the rest is buried in the housing. Half of that is what a marble can
    # meet without being thrown out of the channel, and the difference was
    # measured rather than guessed. Four seeds of eight down launch, leg1 and
    # leg2, counting marbles that left the course:
    #
    #     nine pins at 0.20   16 of 32 finished, 10 escaped
    #     nine pins at 0.10   26 of 32 finished,  3 escaped
    #     four pins at 0.62   24 of 32 finished,  3 escaped
    #     four pins at 0.40   24 of 32 finished,  3 escaped
    #
    # A 0.20 stud stands 0.70 of a marble radius, so a marble at 25 wu/s meets
    # it below its own equator and is levered upward over a channel with 1.40
    # of containment. At 0.10 the contact is shallow enough to deflect rather
    # than lever, and it keeps the asset's nine pins - the four-pin rows, which
    # are tall enough to deflect laterally instead, mix no better and lose five
    # of the drawn nine.
    #
    # Re-scanned on the finished course, three seeds of eight to the finish:
    #
    #     0.10   14 of 24 finished, 8 escaped, 2 jammed
    #     0.07   22 of 24 finished, 2 escaped, 0 jammed
    #     0.05   13 of 24 finished, 1 escaped, 10 jammed
    #
    # 0.05 is worse than 0.07 and the reason is worth keeping: a mixer that
    # deflects too little leaves the field bunched, and a bunched field jams at
    # the fork. Nine of those ten jams are at leg3 sample 80, the fork's nose.
    # So the mixer's job is not only fairness - it is what spaces the pack out
    # before the one place on the course that cannot take eight marbles abreast.
    PIN_HEIGHT = 0.07

    def local_colliders(self) -> list[TriMesh]:
        if self._mesh is not None:
            return [self._mesh]
        pieces: list[TriMesh] = []
        radius = to_sim(layout.MIXER_PIN_RADIUS * self.run.scale)
        height = to_sim(self.pin_height * self.run.scale)
        for offset, across in self._pins():
            index = min(max(self.index + offset, 0), len(self.run.path) - 1)
            _lateral, up, _forward = self.run.frames[index]
            foot = self.run.surface_point(index, across)
            head = tuple(foot[axis] + up[axis] * height for axis in range(3))
            pieces.append(
                tube(foot, head, radius, segments=8, name=f"{self.id}_pin{offset}_{across:+.2f}")
            )
        self._mesh = merge_meshes(pieces, f"{self.id}_pins")
        return [self._mesh]

    def local_sockets(self) -> dict[str, Socket]:
        return {}

    def local_bounds(self) -> Aabb:
        bounds = self.local_colliders()[0].aabb()
        return Aabb(
            tuple(value - 0.25 * MARBLE_DIAMETER for value in bounds.lower),
            tuple(value + 0.25 * MARBLE_DIAMETER for value in bounds.upper),
        )

    def describe(self) -> dict[str, Any]:
        return {
            "kind": "Mixer",
            "on": self.run.id,
            "sample": self.index,
            "rows": list(layout.MIXER_ROW_COUNTS),
            "pin_radius": round(to_sim(layout.MIXER_PIN_RADIUS * self.run.scale), 6),
            "pin_height": round(to_sim(self.pin_height * self.run.scale), 6),
            "pins": [[offset, round(across, 4)] for offset, across in self._pins()],
        }


# --- OBSTACLE -------------------------------------------------------------


class Spinner(Actuator):
    """One paddle wheel, turning about the channel's own up axis.

    The pose is a pure function of the tick, which is section 21's requirement
    and the reason the obstacle can be in a replay at all: `phase + rate * tick
    * dt` and nothing else. No per-frame randomness, no dependence on what the
    marbles did, so the same seed produces the same blade angle at the same
    tick in every process.

    One wheel is four blades and therefore four actuators - Bullet holds one
    box shape per kinematic body - and they share a phase so they stay a wheel.
    """

    def __init__(
        self,
        name: str,
        half_extents: Sequence[float],
        hub: Sequence[float],
        lateral: Sequence[float],
        up: Sequence[float],
        forward: Sequence[float],
        radius: float,
        blade: int,
        blades: int,
        phase: float,
        rate: float,
    ) -> None:
        super().__init__(name, half_extents)
        self.hub = tuple(float(v) for v in hub)
        self.lateral = tuple(float(v) for v in lateral)
        self.up = tuple(float(v) for v in up)
        self.forward = tuple(float(v) for v in forward)
        self.radius = float(radius)
        self.offset = 2.0 * math.pi * blade / blades
        self.phase = float(phase)
        self.rate = float(rate)

    def angle_at(self, tick: int, dt: float) -> float:
        return self.phase + self.offset + self.rate * tick * dt

    def pose_at(self, tick: int, dt: float) -> Transform:
        angle = self.angle_at(tick, dt)
        cos, sin = math.cos(angle), math.sin(angle)
        # The blade's long axis, in the channel's rolled frame: `forward` at
        # angle zero, sweeping toward `lateral`.
        arm = tuple(self.forward[axis] * cos + self.lateral[axis] * sin for axis in range(3))
        side = tuple(-self.forward[axis] * sin + self.lateral[axis] * cos for axis in range(3))
        centre = tuple(self.hub[axis] + arm[axis] * self.radius for axis in range(3))
        return Transform(position=centre, rotation=basis_from_forward_up(arm, self.up))

    def to_json(self) -> dict[str, Any]:
        data = super().to_json()
        data.update(
            {
                "hub": list(self.hub),
                "radius": self.radius,
                "phase": self.phase,
                "offset": self.offset,
                "rate": self.rate,
            }
        )
        return data


class Spinners(MarbleModule):
    """The spinner corridor: three wheels across the channel, alternating sense.

    Three positions and the 1.05-radian phase step are the asset's. Three
    things about them are not, and each is a containment or reachability fix
    rather than a design change:

    **The blades sweep inside the channel.** As drawn they reach 1.39 from the
    shaft while the clear half width is 0.94, so a blade passes through the
    rolled lip and the acrylic guard on both sides. The physical tip is at 0.90,
    which sweeps the full clear width and clears the wall by 0.04.

    **They sweep above the cradle.** As drawn they span y = -0.37 to +0.41 in
    the module's frame and the cradle's lowest point is at -0.26, so a blade
    passes through the floor. The physical blade's underside sits 0.03 above
    the cradle at the tip radius - the highest floor the blade passes over -
    which leaves no gap a marble can slip through and no floor for it to be
    wedged against. A blade's bottom edge riding onto a marble pushes it
    *down*, so the wheel cannot fling one out.

    **Neighbouring wheels turn opposite ways.** Three wheels all turning the
    same sense would deflect every marble toward the same wall three times, and
    a systematic lateral push at one point on the course is a lane bias by
    construction. Alternating cancels it to first order, and the slot benchmark
    is what checks that it cancels in fact.
    """

    TIP = 0.90                 # layout units from the shaft, against a 0.94 half
    THICK = layout.SPINNER_BLADE_THICK
    BLADE_HEIGHT = 0.40
    FLOOR_CLEARANCE = 0.03
    RATE = 3.6                 # rad/s; the tip runs at 0.16 of the marbles' speed

    def __init__(
        self,
        module_id: str,
        run: TrackRun,
        at: int | None = None,
        offsets: Sequence[float] | None = None,
        rate: float | None = None,
    ) -> None:
        super().__init__(module_id)
        self.run = run
        # `at`, `offsets` and `rate` override the recorded `obstacle` node and
        # the asset's three-wheel spacing, so the same wheel can be asked to
        # stand somewhere else. `sloped.startlab` puts one at the launch's
        # entry: a turning wheel is the one mechanism whose *output* order is
        # not monotone in its input order, because a marble's wait is its
        # arrival time modulo the blade period.
        self.index = run.index_near(layout.NODES["obstacle"]) if at is None else int(at)
        self.offsets = tuple(layout.SPINNER_Z if offsets is None else offsets)
        self.rate = self.RATE if rate is None else float(rate)
        self.spacing = run.arc[-1] / (len(run.path) - 1)
        self._mesh: TriMesh | None = None

    def _stations(self) -> list[tuple[int, float, float]]:
        """(sample, phase, rate) per wheel."""
        out: list[tuple[int, float, float]] = []
        for wheel, offset in enumerate(self.offsets):
            index = int(round(self.index + offset / self.spacing))
            index = min(max(index, 1), len(self.run.path) - 2)
            sense = 1.0 if wheel % 2 == 0 else -1.0
            out.append((index, wheel * layout.SPINNER_PHASE, sense * self.rate))
        return out

    def _hub_of(self, index: int) -> tuple[tuple[float, float, float], float]:
        """The wheel centre, and the blade's half height, in simulation units.

        The hub sits over the channel centreline at the height that puts the
        blade's underside `FLOOR_CLEARANCE` above the cradle at the tip radius,
        which is the highest floor any part of the blade passes over.
        """
        _lateral, up, _forward = self.run.frames[index]
        centre = self.run.sim_path[index]
        tip_floor = to_sim(
            layout.floor_y_at(self.TIP, layout.CHANNEL_HALF) * self.run.scale
        )
        base = tip_floor + to_sim(self.FLOOR_CLEARANCE * self.run.scale)
        half_height = to_sim(0.5 * self.BLADE_HEIGHT * self.run.scale)
        hub = tuple(centre[axis] + up[axis] * (base + half_height) for axis in range(3))
        return hub, half_height

    def local_actuators(self) -> list[Actuator]:
        actuators: list[Actuator] = []
        radius_layout = self.TIP * self.run.scale
        for wheel, (index, phase, rate) in enumerate(self._stations()):
            lateral, up, forward = self.run.frames[index]
            hub, half_height = self._hub_of(index)
            for blade in range(layout.SPINNER_BLADES):
                actuators.append(
                    Spinner(
                        name=f"wheel{wheel}_blade{blade}",
                        half_extents=(
                            to_sim(0.5 * radius_layout),
                            half_height,
                            to_sim(0.5 * self.THICK * self.run.scale),
                        ),
                        hub=hub,
                        lateral=lateral,
                        up=up,
                        forward=forward,
                        radius=to_sim(0.5 * radius_layout),
                        blade=blade,
                        blades=layout.SPINNER_BLADES,
                        phase=phase,
                        rate=rate,
                    )
                )
        return actuators

    def local_colliders(self) -> list[TriMesh]:
        """The three shafts. Static, thin, and on the centreline.

        A shaft is a real obstacle - a marble can hit it - and leaving it out
        would make the wheel a set of blades hinged on nothing.
        """
        if self._mesh is not None:
            return [self._mesh]
        pieces: list[TriMesh] = []
        for wheel, (index, _phase, _rate) in enumerate(self._stations()):
            _lateral, up, _forward = self.run.frames[index]
            hub, half_height = self._hub_of(index)
            top = tuple(hub[axis] + up[axis] * (half_height + to_sim(0.6)) for axis in range(3))
            pieces.append(
                tube(hub, top, to_sim(0.075 * self.run.scale), segments=8, name=f"{self.id}_shaft{wheel}")
            )
        self._mesh = merge_meshes(pieces, f"{self.id}_shafts")
        return [self._mesh]

    def local_sockets(self) -> dict[str, Socket]:
        return {}

    def local_bounds(self) -> Aabb:
        first, _ = self._hub_of(self._stations()[0][0])
        last, _ = self._hub_of(self._stations()[-1][0])
        reach = to_sim(self.TIP * self.run.scale) + MARBLE_DIAMETER
        lower = tuple(min(first[axis], last[axis]) - reach for axis in range(3))
        upper = tuple(max(first[axis], last[axis]) + reach for axis in range(3))
        return Aabb(lower, upper)

    def describe(self) -> dict[str, Any]:
        return {
            "kind": "Spinners",
            "on": self.run.id,
            "wheels": [
                {"sample": index, "phase": round(phase, 6), "rate": round(rate, 6)}
                for index, phase, rate in self._stations()
            ],
            "tip_radius": round(to_sim(self.TIP * self.run.scale), 6),
            "blades": layout.SPINNER_BLADES,
        }


# --- FORK -----------------------------------------------------------------


class ForkRidge(MarbleModule):
    """The divider at the split: a ridge that grows out of the floor.

    ## Why it is a ridge and not a wedge, in two failures

    At a fork that diverges, *both* branches turn away from each other, so each
    branch's inner wall - the one facing its neighbour - is the **outside** of
    its own turn. leg3's tail turns 38 degrees right over 2.3 units and throws
    its marbles east; orange's lead turns 39 degrees left and throws its marbles
    west; and east-of-blue and west-of-orange are the same place. So the divider
    is not an extra wall between two channels that have their own. It is the
    only wall either of them has there, and it carries both loads.

    A thin vertical blade does not. Two versions were built and measured over
    three seeds of eight:

    **Straight along leg3's tangent.** leg3's tail curves away from it, so by
    the far end the blade stood 1.5 units east of a channel whose half width is
    0.94 - outside it - leaving an 0.56-unit gap between the channel's edge and
    the divider meant to catch anything crossing it. Thirteen of twenty-four
    marbles left the course at leg3 samples 85 to 91.

    **On the bisector of the two centrelines**, which keeps it between them. It
    stopped being a gap and became an obstacle: four marbles of eight came to a
    dead stop against the nose with the rest queued behind them, because a
    0.08-thick blade 1.9 tall in the middle of a 3.3-diameter channel is
    something a marble arrives at rather than something it is sorted by.

    ## What a fork actually looks like

    One channel whose floor splits, with the divider growing *up* from the
    floor between the two halves. At the nose it is nothing and the field is
    undivided, which is correct - the two channels are the same channel there.
    As they part it rises, and a marble on it rolls off down whichever flank it
    is on. There is no edge to stop against and no gap to fall into: the ridge's
    feet stand on the two cradles, so the region between the channels is floor
    all the way across until their own guards have grown back to full height.

    ## It spans cradle edge to cradle edge, and only where there is a gap

    Two wrong versions of that, both measured. The first tied the crest's
    height to a schedule of its own and it became a spike: 0.70 tall on an 0.11
    foot at the fourth sample. The second tied it to half the *three
    dimensional* distance between the two centrelines - and most of that
    distance is along the flow rather than across it, because the two channels
    diverge in heading. So at ten samples past the fork the ridge came out
    spanning -0.32 to +1.50 in leg3's own frame at its full 1.40 height: a wall
    down the middle of blue's channel, leaving it 1.33 marble diameters to
    queue eight marbles through. 73 of 256 were lost at the fork's nose and
    *no* marble ever reached orange, because orange's floor was under the ridge
    too.

    So the ridge is defined by the two things that actually bound it: leg3's
    east cradle edge and orange's west cradle edge, both taken from the runs'
    own sections. Where those two cross - which is everywhere from the nose to
    about twelve samples past it - the channels overlap, there is nothing to
    divide, and the ridge is a hairline. Where they part it fills the gap
    exactly, feet on the two cradles, crest raised to at most `MAX_FLANK` times
    half the gap so a marble meets a 61-degree curve rather than a face.

        step | leg3 east | orange west | ridge
           0 |      1.61 |       -1.44 | overlap, no ridge
           8 |      1.64 |       -0.37 | overlap, no ridge
          12 |      1.65 |       +1.69 | just parted
          16 |      1.65 |       +4.22 | 1.65 to 4.22, full height

    Until they part the two are one channel, walled by blue's west guard and
    orange's east guard, and which route a marble takes is decided by which
    side of it the marble is running on. That is the fork.
    """

    NOSE_BACK = 0.30           # layout units of nose upstream of the fork
    MAX_FLANK = 1.8            # crest height per unit of foot; 61 degrees
    HAIRLINE = 0.06            # of a marble diameter, where the channels overlap
    FLANK_POINTS = 5           # per side, plus the crest

    def __init__(
        self,
        module_id: str,
        run: TrackRun,
        index: int,
        other: TrackRun,
        window: int,
    ) -> None:
        super().__init__(module_id)
        self.run = run
        self.index = index
        self.other = other
        self.window = window
        self._mesh: TriMesh | None = None

    def _stations(self):
        """(west foot, east foot, up, crest height) per step, in sim units.

        The feet are the two runs' own cradle edges, so the ridge cannot be
        anywhere but between them.
        """
        out = []
        containment = self.run.containment
        for step in range(self.window + 1):
            a_index = min(self.index + step, len(self.run.sim_path) - 1)
            b_index = min(step, len(self.other.sim_path) - 1)
            west = self.run.surface_point(a_index, layout.CHANNEL_HALF)
            east = self.other.surface_point(b_index, -layout.CHANNEL_HALF)
            _la, ua, _fa = self.run.frames[a_index]
            _lb, ub, _fb = self.other.frames[b_index]
            up = _unit(tuple(0.5 * (ua[i] + ub[i]) for i in range(3)))
            lateral = self.run.frames[a_index][0]
            gap = sum((east[i] - west[i]) * lateral[i] for i in range(3))
            if gap <= self.HAIRLINE * MARBLE_DIAMETER:
                # The channels still overlap: no gap, so no ridge, and nothing
                # is emitted at all. The first version put a zero-height
                # hairline on the midline here, which sounds like nothing and
                # is not: its feet are the two *cradle edges*, which sit 0.37
                # simulation units above the cradle's own bottom, so the
                # "hairline" was a ledge a third of a marble diameter high
                # across the middle of the channel. Marbles stopped dead on it
                # at leg3 sample 81, one sample before the fork.
                continue
            height = min(containment, self.MAX_FLANK * 0.5 * gap)
            out.append((west, east, up, height))
        return out

    def local_colliders(self) -> list[TriMesh]:
        if self._mesh is not None:
            return [self._mesh]
        stations = self._stations()
        if len(stations) < 2:
            # No gap anywhere in the window, so no divider. Not a silent empty
            # mesh: `local_colliders` returning nothing would make the module's
            # own bounds undefined, so this is refused loudly instead.
            raise ValueError(
                f"{self.id}: the two channels never part within {self.window} samples; "
                "there is nothing for a ridge to stand in"
            )
        west, east, up, _height = stations[0]
        _la, _ua, forward = self.run.frames[self.index]
        back = to_sim(self.NOSE_BACK)
        # A nose upstream of the first station, on the same feet, so the
        # divider begins as an edge in the floor rather than as a step.
        stations.insert(
            0,
            (
                tuple(west[i] - forward[i] * back for i in range(3)),
                tuple(east[i] - forward[i] * back for i in range(3)),
                up,
                0.0,
            ),
        )

        rings: list[list[tuple[float, float, float]]] = []
        for west, east, up, height in stations:
            ring: list[tuple[float, float, float]] = []
            span = 2 * self.FLANK_POINTS
            for point in range(span + 1):
                u = point / span
                base = tuple(west[i] + (east[i] - west[i]) * u for i in range(3))
                # A raised cosine across the gap: tangent to each cradle at its
                # own foot and to the horizontal at the crest.
                rise = height * math.sin(math.pi * u) ** 2
                ring.append(tuple(base[i] + up[i] * rise for i in range(3)))
            rings.append(ring)
        self._mesh = _strip(rings, f"{self.id}_ridge")
        return [self._mesh]

    def local_sockets(self) -> dict[str, Socket]:
        return {}

    def local_bounds(self) -> Aabb:
        bounds = self.local_colliders()[0].aabb()
        return Aabb(
            tuple(value - 0.2 * MARBLE_DIAMETER for value in bounds.lower),
            tuple(value + 0.2 * MARBLE_DIAMETER for value in bounds.upper),
        )

    def describe(self) -> dict[str, Any]:
        stations = self._stations()
        lateral = self.run.frames[self.index][0]
        rows = []
        for step, (west, east, _up, height) in enumerate(stations):
            gap = sum((east[i] - west[i]) * lateral[i] for i in range(3))
            rows.append([step, round(gap, 4), round(height, 4)])
        return {
            "kind": "ForkRidge",
            "on": self.run.id,
            "sample": self.index,
            "against": self.other.id,
            "window": self.window,
            "crest": round(max(row[2] for row in rows), 6),
            "gap": round(max(row[1] for row in rows), 6),
            "profile": rows,
        }


def _unit(v) -> tuple[float, float, float]:
    length = math.sqrt(sum(x * x for x in v))
    if length < 1e-12:
        return (0.0, 1.0, 0.0)
    return (v[0] / length, v[1] / length, v[2] / length)


# --- MERGE ----------------------------------------------------------------


class MergeCatch(MarbleModule):
    """A roofed funnel apron at the head of the sprint, and the wall in its back.

    The two branches arrive 147 degrees apart with the sprint leaving between
    them, and `docs/sloped_race_v1_junction_finding.md` records the arithmetic
    that says no channel joins them. So the merge is not a channel. It is a
    place where two streams arrive, lose the part of their momentum that is not
    along the sprint, and leave down it.

    Read in the sprint's own frame at its entry - `along` down the sprint,
    `across` to its side, both in simulation units - the three things that meet
    here are:

        blue's mouth    at (-2.01, -0.25)   travelling (+0.99, +0.13)
        orange's mouth  at (+1.49, +1.37)   travelling (-0.76, -0.65)
        the sprint      from ( 0.00,  0.00) travelling (+1.00,  0.00)

    Blue is the sprint's own upstream continuation, near enough: two units
    behind the start, a quarter of a unit off the centreline, pointing down it.
    Its marbles cross the apron and leave. Orange arrives *ahead* of the
    sprint's start, off to one side, travelling back up it at 40 wu/s, and
    nothing gentle will turn it: on the sprint's own 13.6-degree gradient it
    would run 19.5 units upstream before gravity stopped it, and the whole
    station is seven units long. It has to meet a wall.

    ## Where the wall can be, and where it cannot

    The first version put a plain wall across the apron's back at -4.04. That
    is 2.03 units *upstream* of blue's mouth, and blue's channel runs through
    it - so the wall caught blue instead of orange, and 23 of 48 marbles came
    to a stop against it at blue samples 100 to 119.

    The wall has to be at an `along` where orange's own line has already
    carried it clear of blue's channel. Orange crosses `along` at 0.76 units
    per unit of path and drifts across at 0.65, so at the back wall's `along`
    of -2.60 it is at across -2.13, while blue's channel there spans -1.80 to
    +1.14. So the wall stands from the apron's edge in to -1.80, and again from
    +1.14 out - a back wall with blue's channel cut out of it - and the margin
    is 0.33 units, a third of a marble diameter.

    That margin is thin and it is honest: an orange marble arriving wide will
    pass through blue's opening instead, run up blue's channel and come back
    down. It costs that marble time and it costs it no height, and how often it
    happens is in `docs/sloped_race_v1.md` with everything else.

    ## What the wall does to orange

    Its normal is the sprint's own direction, so it takes out the component of
    orange's velocity that is fighting the sprint and leaves the across
    component: 40 wu/s in becomes about 27 across the apron, and the far side
    wall takes that out in turn and leaves about 10 down the sprint. Two
    contacts at 0.25 restitution, which is the track figure, and no marble is
    pushed by anything but geometry.

    ## The apron and the roof

    Across the channel the apron *is* the channel: inside the sprint's clear
    half width the surface is the sprint's own cradle arc, so the two are one
    surface rather than a pan with a gutter standing out of it, and outside it
    keeps rising as a shallow quadratic to the apron's edge.

    Along the sprint it adds **nothing**, and getting that wrong is what cost
    the second attempt. The apron is laid out in the sprint's own frame, whose
    forward axis already descends at 13.7 degrees, so a floor function that
    also subtracts the gradient applies it twice: measured, the apron came out
    0.74 simulation units - three quarters of a marble diameter - *above* blue's
    channel floor two units back, and every marble on the blue route stopped
    dead against that step. Twenty-three of forty-eight, at blue samples 100 to
    119, in a run where the apron was otherwise correct.

    Behind the sprint's entry it interpolates, in the frame, between the
    sprint's own contact point at zero and blue's exit contact point at its own
    `along` - so the apron is flush with the sprint at one end and flush with
    blue at the other by construction rather than by a gradient that has to be
    the right one. Beyond blue's mouth it continues on the same line.

    The roof is what makes the wall safe. A marble at 40 wu/s carries 3.4 units
    of climb, so an open wall would have to be taller than the station's whole
    recorded clearance to hold it and a marble would ride up and over instead.
    A roof one diameter above the apron holds it in with geometry rather than
    with height.
    """

    BACK = -2.30               # layout units along, behind the sprint's entry
    WALL_AT = -1.48            # where the back wall stands, in layout units
    FRONT = 1.70
    ACROSS = 2.30
    ROOF = 0.95                # above the sprint's centreline
    FUNNEL = 0.16              # lateral V depth at the apron's edge

    def __init__(self, module_id: str, sprint: TrackRun, blue: TrackRun | None = None) -> None:
        super().__init__(module_id)
        self.sprint = sprint
        self.blue = blue
        self.lateral, self.up, self.forward = sprint.frames[0]
        self.origin = sprint.surface_point(0, 0.0)
        self.slope = math.atan2(
            -(sprint.sim_path[1][1] - sprint.sim_path[0][1]),
            math.dist(
                (sprint.sim_path[1][0], 0.0, sprint.sim_path[1][2]),
                (sprint.sim_path[0][0], 0.0, sprint.sim_path[0][2]),
            ),
        )
        self._mesh: TriMesh | None = None

    # --- blue's opening in the back wall --------------------------------

    def _local(self, point) -> tuple[float, float]:
        offset = [point[axis] - self.origin[axis] for axis in range(3)]
        return (
            sum(offset[axis] * self.forward[axis] for axis in range(3)),
            sum(offset[axis] * self.lateral[axis] for axis in range(3)),
        )

    def blue_opening(self) -> tuple[float, float]:
        """The across span the back wall leaves open for blue's channel.

        Derived from blue's own exit pose and width rather than typed, so a
        change to blue's lobe moves the opening with it. Falls back to a
        symmetric gap if the merge is built without blue, which is what the
        station tests do.
        """
        wall = to_sim(self.WALL_AT)
        if self.blue is None:
            return (-1.8, 1.14)
        last = len(self.blue.sim_path) - 1
        along, across = self._local(self.blue.surface_point(last, 0.0))
        nose_along, nose_across = self._local(self.blue.surface_point(last - 4, 0.0))
        run = along - nose_along
        drift = (across - nose_across) / run if abs(run) > 1e-6 else 0.0
        centre = across + drift * (wall - along)
        half = 0.5 * self.blue.clear_width * self.blue.widths[last]
        return (centre - half, centre + half)

    def _blue_frame_pose(self) -> tuple[float, float]:
        """Blue's exit contact point as (along, rise) in the apron's frame."""
        if self.blue is None:
            return (-2.009, 0.0)
        last = len(self.blue.sim_path) - 1
        point = self.blue.surface_point(last, 0.0)
        offset = [point[axis] - self.origin[axis] for axis in range(3)]
        along = sum(offset[axis] * self.forward[axis] for axis in range(3))
        rise = sum(offset[axis] * self.up[axis] for axis in range(3))
        return (along, rise)

    def _floor(self, along: float, across: float) -> float:
        # Nothing along the sprint: the frame's forward axis carries the
        # gradient already. Upstream, the line that joins the sprint's contact
        # point to blue's.
        if along >= 0.0:
            fall = 0.0
        else:
            blue_along, blue_rise = self._blue_frame_pose()
            fall = along * (blue_rise / blue_along) if abs(blue_along) > 1e-6 else 0.0
        half = layout.CHANNEL_HALF * self.sprint.scale
        edge = self.ACROSS
        across_layout = abs(across) / LAYOUT_TO_SIM
        if across_layout <= half:
            rise = layout.floor_y_at(across_layout / self.sprint.scale) * self.sprint.scale
            rise -= layout.FLOOR_Y * self.sprint.scale
        else:
            lip = layout.floor_y_at(half / self.sprint.scale) * self.sprint.scale
            lip -= layout.FLOOR_Y * self.sprint.scale
            span = (across_layout - half) / max(edge - half, 1e-6)
            rise = lip + self.FUNNEL * span * span
        return fall + to_sim(rise)

    def local_colliders(self) -> list[TriMesh]:
        if self._mesh is not None:
            return [self._mesh]
        back, front = to_sim(self.BACK), to_sim(self.FRONT)
        edge = to_sim(self.ACROSS)
        roof = to_sim(self.ROOF)
        wall = to_sim(self.WALL_AT)
        low, high = self.blue_opening()
        pieces = [
            height_field(
                self.origin, self.forward, self.lateral,
                (back, front), (-edge, edge), self.up, self._floor,
                steps=(10, 10), name=f"{self.id}_apron",
            ),
            height_field(
                self.origin, self.forward, self.lateral,
                (back, front), (-edge, edge), self.up,
                lambda a, c: self._floor(a, c) + roof,
                steps=(8, 8), name=f"{self.id}_roof",
            ),
        ]
        walls = [
            ("back_left", [(wall, -edge), (wall, max(-edge, low))]),
            ("back_right", [(wall, min(edge, high)), (wall, edge)]),
            ("left", [(back, edge), (front, edge)]),
            ("right", [(back, -edge), (front, -edge)]),
        ]
        for label, stations in walls:
            if abs(stations[0][1] - stations[1][1]) < 1e-6:
                continue
            pieces.append(
                wall_strip(
                    self.origin, self.forward, self.lateral, self.up, stations,
                    base=self._floor, top=lambda a, c: self._floor(a, c) + roof,
                    name=f"{self.id}_{label}", steps=6,
                )
            )
        self._mesh = merge_meshes(pieces, f"{self.id}_catch")
        return [self._mesh]

    def local_sockets(self) -> dict[str, Socket]:
        return {}

    def local_bounds(self) -> Aabb:
        bounds = self.local_colliders()[0].aabb()
        return Aabb(
            tuple(value - 0.2 * MARBLE_DIAMETER for value in bounds.lower),
            tuple(value + 0.2 * MARBLE_DIAMETER for value in bounds.upper),
        )

    def local_probes(self) -> list[Probe]:
        probes: list[Probe] = []
        reach = 3.0 * MARBLE_RADIUS
        back, front = to_sim(self.BACK), to_sim(self.FRONT)
        edge = to_sim(self.ACROSS)
        for step in range(5):
            along = back + (front - back) * step / 4
            for fraction in (-0.7, 0.0, 0.7):
                across = fraction * edge
                rise = self._floor(along, across)
                surface = tuple(
                    self.origin[axis]
                    + self.forward[axis] * along
                    + self.lateral[axis] * across
                    + self.up[axis] * rise
                    for axis in range(3)
                )
                probes.append(
                    Probe(
                        start=tuple(surface[axis] + self.up[axis] * reach for axis in range(3)),
                        end=tuple(surface[axis] - self.up[axis] * reach for axis in range(3)),
                        expect_hit=True,
                        expected_point=surface,
                        tolerance=0.04,
                        label=f"{self.id}.apron[{step}]@{fraction:+.1f}",
                    )
                )
        return probes

    def describe(self) -> dict[str, Any]:
        low, high = self.blue_opening()
        return {
            "kind": "MergeCatch",
            "on": self.sprint.id,
            "along": [round(to_sim(self.BACK), 6), round(to_sim(self.FRONT), 6)],
            "across": round(to_sim(self.ACROSS), 6),
            "roof": round(to_sim(self.ROOF), 6),
            "wall_at": round(to_sim(self.WALL_AT), 6),
            "blue_opening": [round(low, 4), round(high, 4)],
            "blue_frame_pose": [round(v, 4) for v in self._blue_frame_pose()],
            "entry_slope_deg": round(math.degrees(self.slope), 4),
        }


# --- FINISH ---------------------------------------------------------------


class FinishDeck(MarbleModule):
    """The arena the field runs out onto, and the eight catch lanes in it.

    The finish *line* is the sprint's exit socket and the timing happens there;
    this is what happens next, and it exists for two reasons. A marble retired
    the instant it crosses a line leaves the finish shot with nothing in it, and
    a run whose last marble is removed at the line never proves that the field
    could be brought to a stop. Eight lanes at the asset's 1.32 pitch, a rim
    round the deck, and a fall of one degree across it so the field settles.
    """

    def __init__(self, module_id: str, sprint: TrackRun) -> None:
        super().__init__(module_id)
        self.sprint = sprint
        self.origin_layout = layout.NODES["finish"]
        exit_index = len(sprint.path) - 1
        self.yaw_deg = sprint.heading_deg(exit_index)
        self.frame = _yaw_frame(self.yaw_deg)
        angle = math.radians(self.yaw_deg)
        cos, sin = math.cos(angle), math.sin(angle)
        delta = tuple(sprint.path[exit_index][axis] - self.origin_layout[axis] for axis in range(3))
        self.entry_local = (
            delta[0] * cos - delta[2] * sin,
            delta[1],
            delta[0] * sin + delta[2] * cos,
        )
        self._mesh: TriMesh | None = None

    DECK_WIDTH = 12.60
    DECK_DEPTH = 9.80
    RIM = 0.86
    LANES = layout.FINISH_LANES
    LANE_PITCH = layout.FINISH_LANE_PITCH

    def _deck_y(self, along: float, across: float) -> float:
        """A one-degree fall away from the entry, so the field runs out and stops."""
        return -math.tan(math.radians(1.0)) * (along - to_sim(self.entry_local[2]))

    def local_colliders(self) -> list[TriMesh]:
        if self._mesh is not None:
            return [self._mesh]
        ax, ay, az = self.frame
        origin = to_sim_point(
            (
                self.origin_layout[0],
                self.origin_layout[1] + self.entry_local[1] - 0.32,
                self.origin_layout[2],
            )
        )
        along = (az[0], az[1], az[2])
        across = (ax[0], ax[1], ax[2])
        up = (ay[0], ay[1], ay[2])
        half_w = to_sim(0.5 * self.DECK_WIDTH)
        half_d = to_sim(0.5 * self.DECK_DEPTH)
        pieces = [
            height_field(
                origin,
                along,
                across,
                (-half_d, half_d),
                (-half_w, half_w),
                up,
                self._deck_y,
                steps=(8, 12),
                name=f"{self.id}_deck",
            )
        ]
        rim = to_sim(self.RIM)
        for label, stations in (
            ("far", [(half_d, -half_w), (half_d, half_w)]),
            ("left", [(-half_d, half_w), (half_d, half_w)]),
            ("right", [(-half_d, -half_w), (half_d, -half_w)]),
        ):
            pieces.append(
                wall_strip(
                    origin,
                    along,
                    across,
                    up,
                    stations,
                    base=self._deck_y,
                    top=lambda a, c: self._deck_y(a, c) + rim,
                    name=f"{self.id}_rim_{label}",
                    steps=8,
                )
            )
        # Eight catch lanes in the downstream half, as authored.
        lane_from = to_sim(2.60 - 1.50)
        lane_to = to_sim(2.60 + 1.50)
        for lane in range(self.LANES - 1):
            offset = to_sim((lane - (self.LANES - 2) * 0.5) * self.LANE_PITCH)
            pieces.append(
                wall_strip(
                    origin,
                    along,
                    across,
                    up,
                    [(lane_from, offset), (lane_to, offset)],
                    base=self._deck_y,
                    top=lambda a, c: self._deck_y(a, c) + to_sim(0.62),
                    name=f"{self.id}_lane{lane}",
                    steps=3,
                )
            )
        self._mesh = merge_meshes(pieces, f"{self.id}_arena")
        return [self._mesh]

    def local_sockets(self) -> dict[str, Socket]:
        """The deck's own far edge, which is where the machine ends.

        `marble3d.simulation` retires a marble at the last module's exit, so
        this socket is the boundary of the world rather than the finish line.
        Timing is `sloped.race`'s job and it uses the sprint's exit.
        """
        ax, ay, az = self.frame
        half_d = to_sim(0.5 * self.DECK_DEPTH)
        origin = to_sim_point(
            (
                self.origin_layout[0],
                self.origin_layout[1] + self.entry_local[1] - 0.32,
                self.origin_layout[2],
            )
        )
        point = tuple(origin[axis] + az[axis] * half_d for axis in range(3))
        return {
            "exit": Socket(
                name="exit",
                frame=Transform(position=point, rotation=basis_from_forward_up(az, ay)),
                kind=GUIDED,
                width=to_sim(self.DECK_WIDTH),
                height=to_sim(self.RIM),
            )
        }

    def local_bounds(self) -> Aabb:
        bounds = self.local_colliders()[0].aabb()
        return Aabb(
            tuple(value - MARBLE_DIAMETER for value in bounds.lower),
            tuple(value + MARBLE_DIAMETER for value in bounds.upper),
        )

    def describe(self) -> dict[str, Any]:
        return {
            "kind": "FinishDeck",
            "yaw_deg": round(self.yaw_deg, 4),
            "deck": [round(to_sim(self.DECK_WIDTH), 4), round(to_sim(self.DECK_DEPTH), 4)],
            "lanes": self.LANES,
            "entry_local": [round(v, 4) for v in self.entry_local],
        }

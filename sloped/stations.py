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
from sloped.solids import (
    box_shell,
    flank_field,
    height_field,
    merge_meshes,
    plate,
    tube,
    wall_strip,
)
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

    # Which name in `sloped.course.start_module` builds this class. Declared on
    # the class rather than inferred from its name, so `sloped.startlab` can
    # assert that the kind a plan *asked* for is the kind it *got*: the V1.4
    # session shipped a 300-seed "fan" baseline that was a basin, because a
    # plan's `start_kind` defaulted and nothing compared the two.
    START_KIND = "fan"

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

    # Bumpers on the trough floor, as (t along the fan, across as a fraction of
    # the half width there, height in layout units, radius in layout units).
    # See `local_colliders`.
    DEFLECTORS: tuple[tuple[float, float, float, float], ...] = ()

    # The mixing tray, as (converge by t, hold until t, half width). `None` is
    # V1.1's single continuous funnel. See `_half_at`.
    TRAY: tuple[float, float, float] | None = None

    # How far down the fan the trough stays at its full gate width. The eight
    # marbles rest at t = 0.090 and are laid out at a fraction of their pitch
    # equal to the local half width over the gate's, so anything that narrows
    # the trough before this narrows the grid itself.
    GRID_HOLD = 0.10

    # How much of the fan's drop is spent by the tray's two ends, as
    # (fraction by `opening`, fraction by `closing`). See `_fall_at`.
    FALL_PROFILE: tuple[float, float] | None = None

    def __init__(
        self,
        module_id: str = "start",
        launch: TrackRun | None = None,
        fin_schedule: tuple[float, ...] | None = None,
        bay_stagger: tuple[float, ...] | None = None,
        deflectors: tuple[tuple[float, float, float, float], ...] | None = None,
        tray: tuple[float, float, float] | None = None,
        fall_profile: tuple[float, float] | None = None,
        front_half: float | None = None,
    ) -> None:
        super().__init__(module_id)
        self.deflectors = self.DEFLECTORS if deflectors is None else tuple(deflectors)
        self.tray = self.TRAY if tray is None else tray
        # What the fan hands over to, in layout units. `CHANNEL_HALF` unless
        # the launch has been opened out to carry the mixing stretch, in which
        # case the fan has to meet it there or the field is single file before
        # it arrives - which is the whole thing being avoided.
        self.front_half = layout.CHANNEL_HALF if front_half is None else float(front_half)
        self.fall_profile = self.FALL_PROFILE if fall_profile is None else fall_profile
        if self.tray is not None:
            opening, closing, tray_half = self.tray
            if not self.GRID_HOLD < opening <= closing <= 1.0:
                raise ValueError(
                    f"a tray converges after the grid and closes inside the fan; "
                    f"got {self.tray} against a grid held to {self.GRID_HOLD}"
                )
            if tray_half > layout.START_BACK_HALF:
                raise ValueError(
                    f"a tray {tray_half} wide is wider than the gate's {layout.START_BACK_HALF}"
                )
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
        front = self.front_half
        back = layout.START_BACK_HALF
        if self.tray is None:
            eased = _smoothstep(0.10, 1.0, t)
            return back + (front - back) * eased

        # **The mixing tray.** V1.1's fan narrows from 5.46 to 1.88 over
        # essentially its whole 7.34 units, so it is one long funnel, and a
        # funnel is a queue ordered by how far each bay has to travel sideways
        # to reach the line - which is bay index. Eleven geometries were
        # scanned inside that topology and every static one made the ordering
        # *stronger*, because each was one more restriction in a narrowing
        # channel.
        #
        # So the topology changes: a short converge to a **plateau**, a wide
        # stretch held at constant width where several marbles run abreast and
        # meet the bumpers, and only then the narrowing. The convergence is not
        # the defect - a marble's lateral position at the convergence being a
        # perfect function of its bay is the defect. Scramble that position in
        # the tray and the same funnel produces a scrambled queue.
        # Full width until `GRID_HOLD` - the same 0.10 the single taper holds
        # for, and not decoration. The eight marbles rest at t = 0.090 and the
        # bays are laid out at `half / START_BACK_HALF` of their pitch, so a
        # trough already narrowing under the grid narrows the *grid*: at a tray
        # half of 2.10 reached by t = 0.14, the resting pitch comes out 0.527
        # against a 0.57 marble. The field is seeded overlapping itself and
        # never leaves - measured, 100% of every trial trailing.
        opening, closing, tray_half = self.tray
        if t <= self.GRID_HOLD:
            return back
        if t <= opening:
            return back + (tray_half - back) * _smoothstep(self.GRID_HOLD, opening, t)
        if t <= closing:
            return tray_half
        return tray_half + (front - tray_half) * _smoothstep(closing, 1.0, t)

    def _fall_at(self, t: float) -> float:
        """The fraction of the fan's total drop used up by `t`.

        Linear when nothing is asked for, which is what the fan always did.

        With `fall_profile` the drop is redistributed without moving either
        end: most of it into the short run before the tray, so the field
        arrives at the bumpers with some speed; very little across the tray,
        so it stays a tray and not a chute; the rest into the narrowing. The
        whole fan only falls 0.63 layout units - 4.9 degrees - so where that
        0.63 is spent is the only speed control there is.
        """
        if self.fall_profile is None or self.tray is None:
            return t
        opening, closing, _half = self.tray
        by_opening, by_closing = self.fall_profile
        if t <= opening:
            return by_opening * (t / opening) if opening > 1e-9 else by_opening
        if t <= closing:
            span = max(closing - opening, 1e-9)
            return by_opening + (by_closing - by_opening) * (t - opening) / span
        span = max(1.0 - closing, 1e-9)
        return by_closing + (1.0 - by_closing) * (t - closing) / span

    def _path_at(self, t: float) -> tuple[float, float, float]:
        back = (0.0, layout.DECK_TOP - 0.02, -layout.GROOVE_LENGTH)
        front = self.exit_local
        fall = self._fall_at(t)
        return (
            back[0] + (front[0] - back[0]) * t,
            back[1] + (front[1] - back[1]) * fall,
            back[2] + (front[2] - back[2]) * t,
        )

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

        # Bumpers: rounded posts standing on the trough floor, as (t along,
        # across as a fraction of the half width there, height, radius), the
        # last two in layout units.
        #
        # These only do anything inside a **tray**. V1.1 put three rows of thin
        # studs in the fan's converging second half and every one of them made
        # the slot bias worse - the worst reached a rank span of 7.0 out of a
        # possible 7 - because an obstacle in a narrowing channel is one more
        # queue, and a queue leaves in arrival order. In a stretch held at
        # constant width there is somewhere for a deflected marble to go, and
        # which side of a bumper it passes is decided by a fraction of its own
        # radius.
        #
        # They stand on the floor at the marble's own contact height for the
        # same reason the lane dividers do, and `Mixer.PIN_HEIGHT` records what
        # happens when something in a channel is tall enough to lever rather
        # than deflect. `radius` is theirs rather than the mixer's 0.075,
        # because a post a marble is meant to be turned by has to be a
        # noticeable fraction of a 0.285 marble.
        for order, (at, across_fraction, height, radius) in enumerate(self.deflectors):
            half = self._half_at(at)
            centre = self._path_at(at)
            across = across_fraction * half
            floor = centre[1] + self._cradle(across, half, at)
            foot = _place(self.origin, self.frame, (across, floor, centre[2]))
            head = _place(self.origin, self.frame, (across, floor + height, centre[2]))
            pieces.append(
                tube(
                    foot,
                    head,
                    to_sim(radius),
                    segments=12,
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
        pin_radius: float | None = None,
        span: float | None = None,
    ) -> None:
        super().__init__(module_id)
        self.run = run
        # `at` overrides the recorded `mix` node so `sloped.startlab` can ask
        # what the same nine pins do earlier, where the field is still a clump
        # rather than eighteen units of single file.
        self.index = run.index_near(layout.NODES["mix"]) if at is None else int(at)
        self.pin_height = self.PIN_HEIGHT if pin_height is None else float(pin_height)
        self.pin_radius = (
            layout.MIXER_PIN_RADIUS if pin_radius is None else float(pin_radius)
        )
        # How much of the channel's *local* clear width the row spans. The
        # asset's 0.86 is right for a 1.88 channel; the start's mixing stretch
        # opens the launch to 4.7 and the row has to open with it, or nine pins
        # sit in the middle of a wide floor with a clear lane either side.
        self.span = 0.86 if span is None else float(span)
        self._mesh: TriMesh | None = None

    def _pins(self) -> list[tuple[int, float]]:
        """(sample offset, across in profile units) for each pin.

        The row spans the channel's width *at its own sample*, including any
        `width_profile` the run carries, rather than the authored 1.88. A row
        that ignores the local width leaves a clear lane down each side of a
        widened stretch, which is a lane a marble takes every time.
        """
        half = layout.CHANNEL_HALF * self.run.scale * self.run.widths[self.index]
        spacing = self.run.arc[-1] / (len(self.run.path) - 1)
        rows: list[tuple[int, float]] = []
        for row, count in enumerate(layout.MIXER_ROW_COUNTS):
            offset = int(round(layout.MIXER_ROW_Z[row] / spacing))
            for pin in range(count):
                # Five across the clear width, four in the gaps between them.
                across = (
                    (pin - (count - 1) * 0.5) * (2.0 * half * self.span / (count - 1))
                    if count > 1
                    else 0.0
                )
                rows.append((offset, across / self.run.scale))
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
        radius = to_sim(self.pin_radius * self.run.scale)
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
            "pin_radius": round(to_sim(self.pin_radius * self.run.scale), 6),
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
    # A floor under the crest, as a fraction of the run's containment, reached
    # by the end of the window. Zero by default, so the crest is the gap's own
    # 1.8:1 flank and nothing else - a crest raised above what its foot can
    # carry is the spike this class's docstring records as the first failure.
    # The knob exists because the handover from the entry trim to the ridge is
    # a place where the gap is real but small; `tools/sloped_fork_lab.py`
    # scans it.
    CREST_FLOOR = 0.0

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
            floor = self.CREST_FLOOR * containment * min(1.0, step / max(self.window, 1))
            height = min(containment, max(self.MAX_FLANK * 0.5 * gap, floor))
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
    """The shoulder around the junction channel, and the wall in its back.

    ## What this is, and what it stopped being

    The two branches arrive 147 degrees apart with the sprint leaving between
    them, and `docs/sloped_race_v1_junction_finding.md` records the arithmetic
    that says no channel joins them. That is still true of **orange**. It was
    never true of blue: blue arrives 7.5 degrees off the sprint's own heading,
    0.26 simulation units off its centreline and 1.9 behind its entry, and
    `sloped.joins.merge_lead_path` joins those two poses with a channel.

    So this is no longer a pan that carries blue across the junction. It is the
    **shoulder** outside whatever channel is beneath it - blue's tail, then the
    merge lead, then the sprint - plus a roof, two outer walls and the back
    wall that turns orange.

    ## Why a shoulder and not a height field, measured

    The apron used to be a `height_field` over a rectangle spanning the whole
    station, with the cradle formula laid across it, and it therefore owned the
    floor wherever its own surface came out higher than the channel's. Along
    blue's **west running edge** - which no audit had walked, because every
    audit walked the centreline - it did:

        station     floor owner   grade along the line
        blue[112]   blue                     -4.8%
        blue[113]   merge apron             +26.0%    a 0.132 step up
        blue[114]   merge apron              -4.9%

    Three things put it there, and the two chord corrections that preceded this
    rebuild addressed none of them:

    * the apron's cradle was centred on the **sprint's** centreline while
      blue's is 0.26 to 0.52 units off it and yawed 7.5 degrees, so the two
      valleys did not line up;
    * its cradle-to-shoulder changeover was at `CHANNEL_HALF * scale`, 1.649
      units, while the sprint's own cradle edge is at 1.880 - because
      `widths[0]` flares it to 1.140, and the apron did not read `widths` at
      all. The shoulder's quadratic rise therefore began 0.23 units **inside**
      the running surface;
    * past blue's mouth it extrapolated blue's gradient as a straight line
      while blue's channel was still turning.

    `flank_field` removes the whole class: the shoulder's inner edge **is** the
    channel's own clear edge, read off the run through `widths`, so the two are
    flush by construction and no part of the station stands over a running
    surface.

    ## Why the front is closed, and what was coming through it

    The apron's floor used to span `across` +/-4.035 out to its front edge and
    then simply **stop**, with side walls but no front wall and no floor
    beyond. So every marble riding the shoulder outside the sprint's channel
    ran off the lip. In apron-frame terms the lip was at `along` +2.982, which
    is the sprint's sample 9.15 - and `final[9..11]` is the site V1.10 found
    losing 14 of 128 in **six of seven** fork configurations, immovable by
    every fork knob it scanned, because it is not a fork defect.

    Two changes close it. The outer rim now eases in to the channel's own edge
    between `TAPER_FROM` and `FRONT`, so the shoulder converges into the
    channel instead of ending in mid-air; and `FRONT` is placed where the
    sprint's own rails are back to full height rather than five samples before
    it. `sloped.course.MERGE_GUARD_WINDOW` closes at `final[14]`, whose `along`
    is 4.563 simulation units, so `FRONT` is 2.60 layout units and the handover
    from the apron's wall to the sprint's rail happens at one station.

    ## The back wall, and the one margin the geometry has

    Orange arrives *ahead* of the sprint's start, off to one side, travelling
    back up it at 40 wu/s: on the sprint's own 13.7-degree gradient it would
    run 19.5 units upstream before gravity stopped it, and the whole station is
    seven long. It has to meet a wall.

    Orange crosses `along` at 0.749 per unit of path and drifts `across` at
    0.662, so its line is `across = 1.381 + 0.884 * (along - 1.531)`. That line
    passes through `(0, +0.028)` - **the sprint's entry point, on its
    centreline** - so there is no station at which orange is outside the
    sprint's channel and still upstream of it. A transverse wall with a
    channel-shaped opening in it cannot sort the two streams anywhere in front
    of the entry, and that is a property of the two pinned centrelines rather
    than of any wall.

    What makes the wall possible at all is that **blue's channel is narrower
    than the sprint's**: 1.474 against 1.880. Upstream of blue's mouth the
    opening only has to be blue's width, and orange's line has drifted further
    across. At `WALL_AT` = -1.48 layout - -2.596 simulation units, 0.70 behind
    blue's mouth - orange is at across -2.13 while blue's channel there spans
    -1.80 to +1.14. So the wall stands from the apron's rim in to -1.80, and
    again from +1.14 out, and the margin is **0.33 units, a third of a marble
    diameter**. That is the whole clearance available, it is measured rather
    than chosen, and an orange marble arriving wide passes through blue's
    opening instead, runs up the channel and comes back down. It costs that
    marble time and no height.

    The opening is derived from whichever channel is at the wall's own station,
    through `_channel_at`, so it is blue's while `WALL_AT` is behind blue's
    mouth and would become the merge lead's if it moved.

    ## What the wall does to orange

    Its normal is the sprint's own direction, so it takes out the component of
    orange's velocity that is fighting the sprint and leaves the across
    component: 40 wu/s in becomes about 27 across the shoulder, and the far
    side wall takes that out in turn and leaves about 10 down the sprint. Two
    contacts at 0.25 restitution, which is the track figure, and no marble is
    pushed by anything but geometry.

    ## The roof

    A marble at 40 wu/s carries 3.4 units of climb, so an open wall would have
    to be taller than the station's whole recorded clearance to hold it and a
    marble would ride up and over instead. A roof one and two-thirds diameters
    above the floor holds it in with geometry rather than with height.

    The roof is also why every rail under the station is opened - blue's last
    samples, the merge lead's, and the sprint's over
    `sloped.course.MERGE_GUARD_WINDOW`. A rail standing inside a roofed apron
    leaves a ledge along its own top: measured, an orange marble stopped on the
    sprint's east rail at apron-frame across +2.337, its centre 0.43 units
    above the floor beneath it and 0.74 below the roof, at 0.52 wu/s. V1 lost
    319 of its 747 marbles there, every one booked to `blue[100]`.
    """

    BACK = -2.30               # layout units along, behind the sprint's entry
    WALL_AT = -1.48            # where the back wall stands, in layout units
    # `final[14]`'s own station, where `MERGE_GUARD_WINDOW` puts the sprint's
    # rails back at full height. The apron used to end at 1.70, five samples
    # short of it, which left a stretch with neither an apron wall nor a rail.
    FRONT = 2.61
    # Where the outer rim starts easing in to the channel's edge, so the
    # shoulder converges into the channel rather than ending in a free lip.
    TAPER_FROM = 1.20
    ACROSS = 2.30
    ROOF = 0.95                # above the local channel's own contact point
    FUNNEL = 0.16              # how far the rim stands above the channel's edge
    # The rim never quite reaches the channel's edge, and that is a mesh
    # requirement rather than a physical one: a row whose inner and outer
    # coincide is a ring of identical points, and `check_mesh` reports the
    # zero-area triangles between it and its neighbour rather than letting the
    # solver take a meaningless normal from them.
    #
    # **Smaller than the channel's own lip, on purpose.** The lip runs from the
    # cradle's clear edge out to `GUARD_INNER` - 0.109 simulation units at hero
    # scale - and it is steeper than the shoulder, so a sliver narrower than
    # that is buried under the lip and is not a surface a marble can reach at
    # all. At a quarter of a diameter the sliver stood *outside* the lip, and
    # where orange's channel overlaps the sprint's that put 0.09 of step in
    # orange's own floor.
    RIM_MIN = 0.08

    def __init__(
        self,
        module_id: str,
        sprint: TrackRun,
        lead: TrackRun | None = None,
        blue: TrackRun | None = None,
        orange: TrackRun | None = None,
    ) -> None:
        super().__init__(module_id)
        self.sprint = sprint
        self.lead = lead
        self.blue = blue
        self.orange = orange
        self.lateral, self.up, self.forward = sprint.frames[0]
        self.origin = sprint.surface_point(0, 0.0)
        self.slope = math.atan2(
            -(sprint.sim_path[1][1] - sprint.sim_path[0][1]),
            math.dist(
                (sprint.sim_path[1][0], 0.0, sprint.sim_path[1][2]),
                (sprint.sim_path[0][0], 0.0, sprint.sim_path[0][2]),
            ),
        )
        self._stations = self._build_stations()
        self._crossing = self._build_crossing()
        self._mesh: TriMesh | None = None

    # --- the channel under the station ----------------------------------

    def _local(self, point) -> tuple[float, float, float]:
        """A world point as (along, across, rise) in the sprint's entry frame."""
        offset = [point[axis] - self.origin[axis] for axis in range(3)]
        return (
            sum(offset[axis] * self.forward[axis] for axis in range(3)),
            sum(offset[axis] * self.lateral[axis] for axis in range(3)),
            sum(offset[axis] * self.up[axis] for axis in range(3)),
        )

    def _build_stations(self) -> list[tuple[float, ...]]:
        """The junction channel as `(along, across, rise, half, edge, guard, scale)`.

        One row per sample of blue's tail, the merge lead and the sprint's head,
        in flow order, taken from each run's own `surface_point` so the width
        factor and the profile scale are the ones the collider was swept with.
        `half` is the clear half width at that sample, `edge` is how far the
        cradle rises over its own contact point at that half width - the two
        numbers the shoulder's inner edge is made of - and `guard` is how far
        out the run's own lip and rail reach. The shoulder starts at `half`,
        because that is where the two surfaces are flush; but the run's lip
        stands *over* the first 0.11 units of it, so anything that has to be
        fired at bare shoulder starts at `guard` instead. A probe placed at
        `half + 0.125` was answered by the sprint's own lip 0.4275 higher.

        Built once, in the constructor, because `local_colliders`,
        `local_probes` and `describe` all read it and a re-solve per query would
        be the same answer three times.

        Falls back to the sprint alone when the station is built without the
        upstream runs, which is what the station tests do.
        """
        rows: list[tuple[float, ...]] = []
        back, front = to_sim(self.BACK), to_sim(self.FRONT)
        reach = back - 2.0 * MARBLE_DIAMETER
        for run in (self.blue, self.lead, self.sprint):
            if run is None:
                continue
            for index in range(len(run.sim_path)):
                along, across, rise = self._local(run.surface_point(index, 0.0))
                if along < reach or along > front + 2.0 * MARBLE_DIAMETER:
                    continue
                half = 0.5 * run.clear_width * run.widths[index]
                edge = to_sim(
                    (layout.floor_y_at(layout.CHANNEL_HALF) - layout.FLOOR_Y) * run.scale
                )
                guard = to_sim(layout.GUARD_INNER * run.scale * run.widths[index])
                # The **profile** scale, carried separately from the width
                # factor. `ring_points` applies the width to `across` only -
                # scaling the rise too would change the cradle's depth - so a
                # shoulder that recovers one scale from `half` recovers the
                # product of the two and gets the depth wrong. Measured: 0.0666
                # units of step at blue's own cradle edge, where the profile
                # scale is 0.82 and the width factor 1.09.
                rows.append((along, across, rise, half, edge, guard, run.scale))
        rows.sort(key=lambda row: row[0])
        # Two runs share a station at every seam - blue's last sample and the
        # lead's first are the same `along` - and an interpolation over a
        # zero-width span is a division by nothing. The downstream row wins,
        # which is the wider channel at both seams and therefore the safe one.
        out: list[tuple[float, ...]] = []
        for row in rows:
            if out and row[0] - out[-1][0] < 1e-6:
                out[-1] = row
            else:
                out.append(row)
        return out

    def _build_crossing(self) -> list[tuple[float, float]]:
        """Where orange's channel crosses the shoulder, as `(along, near)` rows.

        **Orange's tail runs straight through the apron's east side**, and that
        is what the front taper found out the hard way. The rim eases in from
        `ACROSS` to the channel's edge between `TAPER_FROM` and `FRONT`, and on
        the east side that line sweeps across orange's channel: at `along`
        +3.67 the tapering wall stands at across +2.69 while orange's own
        centreline is at +3.27. Traced, a marble at 40 wu/s lost **19.13 wu/s
        in a single tick** there, in contact with `merge` and `orange` at once,
        and every one of 28 marbles launched on orange's tail stopped within
        four samples of it. Nothing in orange's own channel does that: the
        control - orange's tail built with the merge, the lead and the sprint
        absent - carries a marble from sample 96 to its exit at every speed
        from 30 to 70 wu/s.

        So where orange is present the shoulder stops at orange's **near**
        edge - the lower-across side of its channel - and orange's own walls
        are the containment from there out. `near` is that edge in the apron's
        frame, per orange sample inside the apron's span.
        """
        rows: list[tuple[float, float]] = []
        if self.orange is None:
            return rows
        back, front = to_sim(self.BACK), to_sim(self.FRONT)
        reach = 2.0 * MARBLE_DIAMETER
        for index in range(len(self.orange.sim_path)):
            along, across, _rise = self._local(self.orange.surface_point(index, 0.0))
            if along < back - reach or along > front + reach:
                continue
            half = 0.5 * self.orange.clear_width * self.orange.widths[index]
            # Orange travels against the sprint, so its own lateral axis points
            # the other way; the near edge is the smaller `across` whichever
            # way its frame happens to be signed.
            west = self._local(self.orange.surface_point(index, layout.CHANNEL_HALF))[1]
            east = self._local(self.orange.surface_point(index, -layout.CHANNEL_HALF))[1]
            rows.append((along, min(west, east)))
        rows.sort(key=lambda row: row[0])
        return rows

    def orange_near(self, along: float) -> float | None:
        """Orange's near channel edge at one station, or None if it is not there."""
        rows = self._crossing
        if not rows or along < rows[0][0] or along > rows[-1][0]:
            return None
        for lower, upper in zip(rows, rows[1:]):
            if lower[0] <= along <= upper[0]:
                span = upper[0] - lower[0]
                if span < 1e-9:
                    return lower[1]
                t = (along - lower[0]) / span
                return lower[1] + (upper[1] - lower[1]) * t
        return rows[-1][1]

    def _channel_at(self, along: float) -> tuple[float, ...]:
        """`(across, rise, half, edge, guard, scale)` of the channel at one station.

        Linear between the samples either side, clamped at both ends. The
        clamp is why `_build_stations` reaches two diameters past each end of
        the apron: a shoulder generated over a station with no channel under it
        would take the nearest one's width, and at the back edge that is blue's
        tail rather than nothing.
        """
        rows = self._stations
        if not rows:
            half = 0.5 * self.sprint.clear_width * self.sprint.widths[0]
            edge = to_sim(
                (layout.floor_y_at(layout.CHANNEL_HALF) - layout.FLOOR_Y) * self.sprint.scale
            )
            guard = to_sim(layout.GUARD_INNER * self.sprint.scale * self.sprint.widths[0])
            return (0.0, 0.0, half, edge, guard, self.sprint.scale)
        if along <= rows[0][0]:
            return rows[0][1:]
        if along >= rows[-1][0]:
            return rows[-1][1:]
        for lower, upper in zip(rows, rows[1:]):
            if lower[0] <= along <= upper[0]:
                t = (along - lower[0]) / (upper[0] - lower[0])
                return tuple(
                    lower[axis] + (upper[axis] - lower[axis]) * t for axis in range(1, 7)
                )  # type: ignore[return-value]
        return rows[-1][1:]

    # --- the shoulder ---------------------------------------------------

    def rim(self, along: float, side: float = -1.0) -> float:
        """How far out the shoulder reaches at one station, in simulation units.

        `ACROSS` until `TAPER_FROM`, then eased in to the channel's own edge by
        `FRONT` with the same smoothstep the guard windows use. A shoulder that
        keeps its full reach to the front edge is the open lip `final[9..11]`
        was; one that converges into the channel hands its marbles over.

        **On the east side it also yields to orange**, because orange's tail
        crosses that region and the tapering wall stood across its channel; see
        `_build_crossing` for the 19.13 wu/s a marble lost to it in one tick.
        Clamped to orange's near edge rather than stopped short of it, so the
        shoulder and orange's channel are adjacent and there is no strip
        between them with nothing under it.
        """
        _across, _rise, half, _edge, _guard, _scale = self._channel_at(along)
        wide = to_sim(self.ACROSS)
        start, stop = to_sim(self.TAPER_FROM), to_sim(self.FRONT)
        shut = half + self.RIM_MIN
        if along <= start:
            reach = max(wide, shut)
        elif along >= stop:
            reach = shut
        else:
            t = (along - start) / max(stop - start, 1e-6)
            ease = t * t * (3.0 - 2.0 * t)
            reach = max(wide, shut) + (shut - max(wide, shut)) * ease
        if side > 0.0:
            near = self.orange_near(along)
            if near is not None:
                centre = self._channel_at(along)[0]
                reach = min(reach, max(shut, near - centre))
        return reach

    def orange_overlaps(self, along: float) -> bool:
        """Whether orange's channel reaches inside the sprint's own at a station.

        Near its mouth orange arrives *inside* the sprint's channel - its near
        edge crosses the sprint's clear edge about four samples out - so from
        there on there is no band of bare shoulder between them for a wall to
        stand on, and `rim`'s clamp bottoms out at `RIM_MIN`. A wall on that
        sliver is a wall across orange's channel: it was measured at 19.13
        wu/s of loss in one tick at `along` +3.67, and after `rim` learned to
        yield the same wall still took every one of 28 marbles at
        `orange[113]`. So where this is true the east wall is simply absent,
        and the containment there is orange's own channel walls upstream and
        the sprint's rails downstream - which `MERGE_GUARD_WINDOW` brings back
        to full height at `final[14]`, inside the apron's own front edge.
        """
        near = self.orange_near(along)
        if near is None:
            return False
        centre, _rise, half, _edge, _guard, _scale = self._channel_at(along)
        return near - centre <= half + self.RIM_MIN

    def _bounds(self, side: float):
        """`bounds(along)` for one side of the shoulder, for `flank_field`."""

        def at(along: float) -> tuple[float, float]:
            across, _rise, half, _edge, _guard, _scale = self._channel_at(along)
            return (across + side * half, across + side * self.rim(along, side))

        return at

    def _floor(self, along: float, across: float) -> float:
        """The station's surface at one point, as a rise in the apron's frame.

        Inside the channel it **is** the channel's surface, so a caller that
        generates the shoulder from `_bounds` never evaluates it there and the
        two can never disagree. Outside, the channel's own cradle edge plus a
        quadratic to the rim, so the shoulder leans a marble back toward the
        channel rather than away from it.
        """
        centre, rise, half, edge, _guard, scale = self._channel_at(along)
        offset = abs(across - centre)
        if offset <= half:
            # The channel's own arc, read in *profile* coordinates so the
            # width factor stretches it exactly as `ring_points` does - and
            # with the **profile scale** applied to the rise and nothing else.
            # Reading it in physical units instead is what put the old apron's
            # shoulder 0.083 units above the sprint's floor at a lateral
            # fraction of 0.85; recovering one scale from `half` and using it
            # for both put it 0.0666 above blue's cradle edge.
            profile = layout.CHANNEL_HALF * offset / max(half, 1e-9)
            return rise + to_sim((layout.floor_y_at(profile) - layout.FLOOR_Y) * scale)
        # **Normalised by the shoulder's widest span, not by the local rim.**
        # The rim tapers in toward the front, so dividing by `rim - half` sends
        # `over` to 1 within a fraction of a unit there: everything outside the
        # rim becomes a plateau at full funnel height, and the plateau's inner
        # edge moves inward as the rim narrows. A taper has to *remove*
        # shoulder, not lift it.
        #
        # Measured in **world height**, which is the quantity gravity reads,
        # over five `across` lines from `along` -4.0 to +4.5:
        #
        #     local rim   0.2460 of closed basin, 9.3 wu/s to leave
        #     fixed span  0.0571, and that is the blue-to-lead seam
        #
        # Six of six marbles at 30 to 36 wu/s came to rest in it at the same
        # point to two decimals - `along` +3.27, `across` -2.19 - which is a
        # shape and not a scatter.
        #
        # **The apron's own frame is not the frame to measure this in**, and it
        # was measured there first: the frame's forward axis descends at 13.7
        # degrees, so the same surface reads 0.3857 as a frame-relative rise.
        # The defect was real either way; the magnitude was not.
        span = max(to_sim(self.ACROSS) - half, 1e-6)
        over = min(1.0, (offset - half) / span)
        return rise + edge + to_sim(self.FUNNEL) * over * over

    def blue_opening(self) -> tuple[float, float]:
        """The across span the back wall leaves open for the channel under it.

        Derived from whichever run `_channel_at` finds at `WALL_AT` - blue's
        tail, while the wall stands behind blue's mouth - so a change to blue's
        lobe or to the wall's station moves the opening with it.

        **Sized to the channel's clear width and not to a marble past it**, and
        that is the trade rather than an oversight: widening it by a radius
        either side would let orange's line through, because the whole margin
        the geometry has is 0.33 units. A blue marble riding its own west edge
        passes within 0.02 of the wall's end, so the ends are chamfered rather
        than square - see `_wall_top`.
        """
        wall = to_sim(self.WALL_AT)
        across, _rise, half, _edge, _guard, _scale = self._channel_at(wall)
        return (across - half, across + half)

    # --- geometry -------------------------------------------------------

    def local_colliders(self) -> list[TriMesh]:
        if self._mesh is not None:
            return [self._mesh]
        back, front = to_sim(self.BACK), to_sim(self.FRONT)
        roof = to_sim(self.ROOF)
        wall = to_sim(self.WALL_AT)
        low, high = self.blue_opening()
        pieces = [
            flank_field(
                self.origin, self.forward, self.lateral, (back, front),
                self._bounds(-1.0), self.up, self._floor,
                steps=(14, 6), name=f"{self.id}_west_flank",
            ),
            flank_field(
                self.origin, self.forward, self.lateral, (back, front),
                self._bounds(+1.0), self.up, self._floor,
                steps=(14, 6), name=f"{self.id}_east_flank",
            ),
            # The roof spans the channel as well as the shoulders, because what
            # it holds down is a marble crossing the channel at 40 wu/s.
            flank_field(
                self.origin, self.forward, self.lateral, (back, front),
                    lambda a: (
                    self._channel_at(a)[0] - self.rim(a, -1.0),
                    self._channel_at(a)[0] + self.rim(a, +1.0),
                ),
                self.up,
                lambda a, c: self._floor(a, c) + roof,
                steps=(12, 10), name=f"{self.id}_roof",
            ),
        ]
        centre_back = self._channel_at(back)[0]
        walls = [
            (
                "back_west",
                [(wall, centre_back - self.rim(back, -1.0)), (wall, low)],
            ),
            (
                "back_east",
                [(wall, high), (wall, centre_back + self.rim(back, +1.0))],
            ),
        ]
        # **The side walls are sampled rather than drawn through three
        # stations.** A three-station polyline is a straight line in the
        # (along, across) plane between them, and on the east side that line
        # cut through orange's channel even after `rim` learned to yield to it -
        # the clamp only binds at the stations it is evaluated on. Sampled at
        # the same count as the shoulder, the wall follows the rim it stands on.
        for label, side in (("west", -1.0), ("east", +1.0)):
            stations = []
            for step in range(15):
                along = back + (front - back) * step / 14
                if side > 0.0 and self.orange_overlaps(along):
                    break
                centre = self._channel_at(along)[0]
                stations.append((along, centre + side * self.rim(along, side)))
            if len(stations) >= 2:
                walls.append((label, stations))
        for label, stations in walls:
            if max(abs(a[1] - b[1]) for a, b in zip(stations, stations[1:])) < 1e-6:
                continue
            pieces.append(
                wall_strip(
                    self.origin, self.forward, self.lateral, self.up, stations,
                    base=self._floor, top=lambda a, c: self._floor(a, c) + roof,
                    name=f"{self.id}_{label}", steps=2,
                )
            )
        self._mesh = merge_meshes(pieces, f"{self.id}_catch")
        return [self._mesh]

    def holds(self, point) -> bool:
        """Is this point standing on the station rather than off the course?

        **A lateral containment test asks the wrong question at the merge**, in
        the same way `sloped.race._shared` records it asking the wrong question
        at the fork: the test is "is the marble outside *this run's* channel",
        and on the apron the answer is yes and it does not matter, because the
        shoulder is floor. Orange is *designed* to cross it - the back wall
        takes out the component fighting the sprint and the far shoulder takes
        out the rest - so an orange marble at 0.50 units above the shoulder,
        2.4 to 3.7 across, at 5 to 15 wu/s, is doing exactly what the station
        is for.

        Measured: of 28 marbles launched on orange's tail, eleven were booked
        as having left the course in precisely that state, touching `merge` and
        nothing else. Every forked measurement this project has taken has that
        in it, V1.10's escape rates included.

        So the run-relative test is excused where this returns True: inside the
        apron's own `along` span, inside its rim, and between half a diameter
        below its floor and its roof. Derived from the station's own geometry,
        so it cannot drift from the collider it describes.
        """
        along, across, rise = self._local(point)
        if not to_sim(self.BACK) - MARBLE_RADIUS <= along <= to_sim(self.FRONT) + MARBLE_RADIUS:
            return False
        centre = self._channel_at(along)[0]
        side = 1.0 if across >= centre else -1.0
        if abs(across - centre) > self.rim(along, side) + MARBLE_RADIUS:
            return False
        floor = self._floor(along, across)
        return floor - MARBLE_DIAMETER <= rise <= floor + to_sim(self.ROOF)

    def local_sockets(self) -> dict[str, Socket]:
        return {}

    def local_bounds(self) -> Aabb:
        bounds = self.local_colliders()[0].aabb()
        return Aabb(
            tuple(value - 0.2 * MARBLE_DIAMETER for value in bounds.lower),
            tuple(value + 0.2 * MARBLE_DIAMETER for value in bounds.upper),
        )

    def local_probes(self) -> list[Probe]:
        """Rays at the shoulder, fired where the shoulder actually is.

        Outside the channel by construction: a probe aimed inside it would be
        answered by the run's own collider, which is the correct surface there
        and would read as the apron being missing.
        """
        probes: list[Probe] = []
        reach = 3.0 * MARBLE_RADIUS
        back, front = to_sim(self.BACK), to_sim(self.FRONT)
        for step in range(5):
            along = back + (front - back) * step / 4
            centre, _rise, _half, _edge, guard, _scale = self._channel_at(along)
            # Outside the run's own lip and rail, not merely outside its clear
            # edge: the lip stands over the shoulder's first 0.11 units and a
            # probe inside it is answered by the channel 0.4275 higher.
            for side in (-1.0, 1.0):
                rim = self.rim(along, side)
                if rim - guard < 0.25 * MARBLE_DIAMETER:
                    continue
                across = centre + side * (guard + 0.5 * (rim - guard))
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
                        label=f"{self.id}.flank[{step}]@{side:+.0f}",
                    )
                )
        return probes

    def describe(self) -> dict[str, Any]:
        low, high = self.blue_opening()
        wall = to_sim(self.WALL_AT)
        return {
            "kind": "MergeCatch",
            "on": self.sprint.id,
            "lead": None if self.lead is None else self.lead.id,
            "upstream": None if self.blue is None else self.blue.id,
            "along": [round(to_sim(self.BACK), 6), round(to_sim(self.FRONT), 6)],
            "taper_from": round(to_sim(self.TAPER_FROM), 6),
            "across": round(to_sim(self.ACROSS), 6),
            "roof": round(to_sim(self.ROOF), 6),
            "wall_at": round(wall, 6),
            "blue_opening": [round(low, 4), round(high, 4)],
            "wall_channel": [round(v, 4) for v in self._channel_at(wall)],
            "rim_at_front": [
                round(self.rim(to_sim(self.FRONT), -1.0), 4),
                round(self.rim(to_sim(self.FRONT), +1.0), 4),
            ],
            "stations": len(self._stations),
            "orange_crossing": len(self._crossing),
            "east_wall_ends": round(
                next(
                    (
                        to_sim(self.BACK)
                        + (to_sim(self.FRONT) - to_sim(self.BACK)) * step / 14
                        for step in range(15)
                        if self.orange_overlaps(
                            to_sim(self.BACK)
                            + (to_sim(self.FRONT) - to_sim(self.BACK)) * step / 14
                        )
                    ),
                    to_sim(self.FRONT),
                ),
                4,
            ),
            "entry_slope_deg": round(math.degrees(self.slope), 4),
        }


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

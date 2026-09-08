"""The unconstricted start: eight bays onto one broad raceway, and no throat.

## What every previous start had in common

Four topologies have now been measured and all four ordered the field, and
`docs/sloped_race_v15_apron.md` states the shared mechanism:

    A start that delivers its field to a single exit orders the field by
    distance to that exit. Making the distances equal is not enough: whatever
    coordinate the equalisation leaves free is still a function of the bay, and
    the exit still reads it.

    taper   free coordinate: lateral position in the trough
    basin   free coordinate: position along the rim notch
    radial  free coordinate: bearing round the ring
    chutes  never got far enough to have one

The one thing all four share, and none of them varied, is that **the field is
serialised near the start**. The taper closes 5.46 to 1.88 over seven units;
the basin drains through one notch; the radial ring converges on one drain. So
the untested hypothesis is the absence of that:

    do not serialise the field near the start at all.

Keep the course wide enough for real lateral motion long enough for collisions
and overtakes to happen, and narrow to the hero channel only after the starting
order has been substantially decorrelated.

## What this builds

    eight bays abreast on a flat pan, one synchronised gate    <- unchanged, seen
      |  short alignment grooves that fade out inside a unit
    one broad apron, no lane walls, 5.6 wide                   <- the change
      |
    the launch, widened `LAUNCH_FACTOR` times and held wide
      |
    leg1, held wide through its gentle first stretch
      |  a long gradual narrowing, well clear of leg1's banked turn
    the 1.88 hero channel

**There is no taper anywhere in it.** The drawn pod is 5.46 wide across the
gate and the launch's own entry, widened 2.6 times, is 5.57 - so the apron runs
from the resting line to the launch at essentially constant width. That is the
whole architectural point, and it is a property of the numbers rather than a
choice: `START_BACK_HALF` is 2.73 and `0.5 * HERO_CLEAR_WIDTH * widths[0] *
2.6` is 2.786.

## Why widening the channel gives a *field* and not just a wide channel

`sloped.track.ring_points` scales the section **laterally only** - "scaling the
rise too would change the cradle's depth, and the marble sits on the cradle".
So a channel widened 2.6 times keeps its 0.26-deep cradle and its full-height
guards, and becomes a 5.6-wide dish only 0.21 deep at its edge: a 4.3-degree
cross-slope where the hero channel has 30. That is a surface a marble can cross
freely, which is exactly what is wanted, and it is why this needs no new
cross-section.

## The lift is derived, not inherited

The radial start needed `START_LIFT = 4.30` and section 16 of the brief is
explicit that this architecture does not inherit it. It does not: the apron has
7.88 layout units of plan between the resting line and the launch's entry, and
`derived_lift()` asks only for enough elevation to run that at the grade
profile below. The answer is about **1.06**, a quarter of the radial's.
"""

from __future__ import annotations

import math
from typing import Any

from marble3d.geometry import Transform, basis_from_forward_up
from marble3d.machine import Aabb, GUIDED, Socket
from marble3d.mesh import TriMesh
from marble3d.modules.base import Actuator, Probe
from marble3d.units import MARBLE_DIAMETER, MARBLE_RADIUS

from sloped import layout
from sloped.scale import to_sim
from sloped.solids import merge_meshes, plate
from sloped.stations import StartGrid, _bay_x, _place, _strip
from sloped.track import TrackRun, channel_profile

__all__ = ["WideLaunch", "apron_table"]


def _ease(value: float) -> float:
    t = min(1.0, max(0.0, value))
    return t * t * (3.0 - 2.0 * t)


class WideLaunch(StartGrid):
    """The eight bays and the gate of `StartGrid`, onto one broad apron.

    Subclassed for the reason `StartBasin` and `RadialStart` are: the bays, the
    gate paddles, the release and the resting pitch carry four sessions of
    corrections and none of them changes. What changes is that nothing
    downstream of the gate narrows.
    """

    START_KIND = "wide_launch"

    # --- the pan the field waits on --------------------------------------
    #
    # Flat *across*. This is a fairness correction and not a plumbing one: the
    # fan's trough is a dish, so its outer bays rest 0.10 layout units higher
    # than its inner ones - a systematic per-bay energy difference that sat
    # under three sessions of measurement without being noticed.
    PAN_BACK = -4.60
    PAN_SINK = 0.30                # how far the pan sits under the deck
    PAN_HALF = 2.86                # a little over the drawn pod's 2.73

    # --- the apron --------------------------------------------------------
    #
    # How wide the launch is held. 2.6 puts its entry at 2.786 half width
    # against the pod's 2.73, so the apron is a constant-width ramp.
    LAUNCH_FACTOR = 2.6
    # The grade at the resting line, and at the seam. The seam figure is the
    # launch's own entry grade, so the two surfaces meet at the same pitch
    # rather than at a corner a marble hops off: at 20 layout units per second
    # a six-degree corner throws a marble 0.6 units.
    HEAD_GRADE = 8.0
    SEAM_GRADE = 25.8
    # `grade(u) = head + (seam - head) * u ** GRADE_POWER`. A high power keeps
    # most of the apron at the drawn shelf's own shallow pitch and puts the
    # steepening in the last fifth, where it has to match the launch.
    GRADE_POWER = 4.0

    # **There are no alignment grooves, and the first build's were a lesson in
    # sampling rather than in guidance.**
    #
    # Section 6 of the brief permits shallow grooves near the gate. The first
    # build had them: a 0.60-radius cradle centred on each bay, faded out by a
    # fifth of the run. But the apron's cross-section is carried by the
    # channel's own profile, which has five points per cradle half - so on a
    # 5.57-wide field the floor is sampled every 0.70 layout units, while the
    # bays are 0.63 apart. The groove function was therefore evaluated at
    # x = 0, +/-0.72, +/-1.43, +/-2.15, +/-2.86 and never at a bay centre at
    # all, and what it built was not eight grooves but a single 0.089 bump on
    # the centreline with near-nothing elsewhere.
    #
    # Bays 3 and 4 rest at +/-0.315, on that bump's flank. Traced in
    # simulation they moved 0.13 and stopped, and sat there for the whole run
    # while the other six accelerated away: 7th and 8th place in every seed,
    # with the two lowest collision counts in the field. Removing the grooves
    # is both the fix and the architecture - section 6's actual requirement is
    # that the racers enter ONE shared surface, and a flat pan is that.
    #
    # The floor is also resolved properly now, at `COLUMNS` points rather than
    # the channel profile's five, so a feature the size of a marble cannot
    # fall between samples again.
    GROOVE_TO = 0.0

    # Where the flat pan becomes the launch's own shallow dish. Late, because
    # the dish pulls an outer marble inward and that is a centre-bay advantage;
    # 0.21 of depth over 2.79 of half width is 4.3 degrees, and the launch's
    # own bank is 18.
    SECTION_FROM = 0.55

    ROWS = 88                      # rows along the apron
    HEEL_ROWS = 6                  # and behind the resting line; see `heel_u`
    COLUMNS = 24                   # floor points across it; see `GROOVE_TO`

    # --- cross-flow, for candidate C --------------------------------------
    #
    # Shallow chevron ridges that steer a marble across the field rather than
    # along it. Off by default; `sloped.startlab` turns them on.
    CROSS_FLOW = False
    CROSS_ROWS = ((0.34, 1.0), (0.52, -1.0), (0.70, 1.0))
    CROSS_RISE = 0.11
    CROSS_SKEW = 0.42              # how far across the field one chevron leans

    def __init__(
        self,
        module_id: str = "start",
        launch: TrackRun | None = None,
        cross_flow: bool | None = None,
    ) -> None:
        super().__init__(module_id, launch)
        self.cross_flow = self.CROSS_FLOW if cross_flow is None else bool(cross_flow)
        # The plan run and the drop available before any lift, both read off
        # the recorded geometry rather than typed.
        launch_entry = (
            launch.path[0] if launch is not None else layout.run("launch")["controls"][0]
        )
        angle = math.radians(self.yaw_deg)
        cos, sin = math.cos(angle), math.sin(angle)
        delta = tuple(launch_entry[axis] - self.origin[axis] for axis in range(3))
        plain = (
            delta[0] * cos - delta[2] * sin,
            delta[1],
            delta[0] * sin + delta[2] * cos,
        )
        self.plan_run = plain[2] - self._field_z()
        self.lift = self.derived_lift(plain)
        self.origin = (self.origin[0], self.origin[1] + self.lift, self.origin[2])
        self.exit_local = (plain[0], plain[1] - self.lift, plain[2])
        self._mesh: TriMesh | None = None
        # **Read off the run, not multiplied by the factor again.** The launch
        # handed in has already had its width profile applied, so its
        # `widths[0]` is 1.14 * LAUNCH_FACTOR. Multiplying by the factor a
        # second time here put the seam at 7.24 half width against the pod's
        # 2.73 - a 14.5-wide apron, which is not the architecture, it is a
        # bookkeeping error. `LAUNCH_FACTOR` is now only the documented default
        # that `sloped.startlab`'s plans pass to the run.
        self._launch_half = 0.5 * layout.HERO_CLEAR_WIDTH * (
            launch.widths[0] if launch is not None else 1.14 * self.LAUNCH_FACTOR
        )
        self.gate_z = self._field_z() + layout.MARBLE_RADIUS + 0.06

    # --- the elevation, derived -------------------------------------------

    def mean_grade(self) -> float:
        """The apron's mean grade as a tangent, from its own profile.

        `integral of head + (seam - head) * u^p du` over [0,1] is
        `head + (seam - head) / (p + 1)`.
        """
        head = math.tan(math.radians(self.HEAD_GRADE))
        seam = math.tan(math.radians(self.SEAM_GRADE))
        return head + (seam - head) / (self.GRADE_POWER + 1.0)

    def derived_lift(self, plain) -> float:
        """How much elevation the apron actually needs, and no more.

        Section 16 of the brief: the radial start's 4.30 is not inherited. The
        apron needs `plan_run * mean_grade` of fall between the pan and the
        launch's seat, and the recorded geometry already supplies
        `pan_floor - seat`. The difference is the lift, and it is about 1.06.

        Computed before the lift is applied, which is safe because the lift
        moves only `y`: the plan run does not depend on it.
        """
        needed = self.plan_run * self.mean_grade()
        # The launch's seat is its cradle's lowest point, `FLOOR_Y` under the
        # centreline - the same choice `TrackRun._socket` makes, and for the
        # same reason: a socket on the centreline is 0.26 in the air.
        seat = plain[1] + layout.FLOOR_Y
        available = self.pan_floor - seat
        return max(0.0, needed - available)

    @property
    def pan_floor(self) -> float:
        """What a marble rests on at the line. One height for all eight."""
        return layout.DECK_TOP - 0.02 - self.PAN_SINK

    def _field_z(self) -> float:
        return self.PAN_BACK + 0.66

    def _cradle(self, across: float, half: float, t: float = 0.0) -> float:
        """Flat. See the class comment on `PAN_BACK`."""
        return -self.PAN_SINK

    # --- the apron's centreline and section -------------------------------

    @property
    def heel_u(self) -> float:
        """Where the apron begins, behind the resting line, as a `u`.

        **The pan has to extend behind the field, and this is the second time
        that has had to be learnt.** V1.5's radial apron began at the guides'
        own start and the drawn pod's floor runs 0.66 further back, so the
        release jostled marbles into the hole; that was written up and then
        rebuilt here in a different shape. Traced in simulation, a marble
        seeded exactly on the mesh's first row has its contact facet ending
        under its own centre, so it tips *backwards* off the edge - bays 1 and 2
        rolled uphill out of the machine and fell 17.7 units, while five of the
        eight happened to tip forwards and ran the whole lab.
        """
        return (self.PAN_BACK - self._field_z()) / max(self.plan_run, 1e-9)

    def fall(self, u: float) -> float:
        """How far the apron has fallen at `u` along its plan run.

        The integral of the grade profile, so the surface has the grade the
        profile says it has - rather than the profile being a description of a
        shape derived some other way. Negative `u` is the heel behind the
        resting line, which continues the head grade upward, so a resting
        marble is on a slope and rolls forward into its paddle.
        """
        t = min(1.0, u)
        head = math.tan(math.radians(self.HEAD_GRADE))
        seam = math.tan(math.radians(self.SEAM_GRADE))
        power = self.GRADE_POWER
        if t <= 0.0:
            return self.plan_run * head * t
        return self.plan_run * (
            head * t + (seam - head) * t ** (power + 1.0) / (power + 1.0)
        )

    def grade_deg(self, u: float) -> float:
        head = math.tan(math.radians(self.HEAD_GRADE))
        seam = math.tan(math.radians(self.SEAM_GRADE))
        t = max(0.0, min(1.0, u))
        return math.degrees(math.atan(head + (seam - head) * t ** self.GRADE_POWER))

    def centre_at(self, u: float) -> tuple[float, float, float]:
        """The apron's floor on its centreline: straight in plan, and it is.

        The module is yawed to face the launch's entry, so the entry is on the
        module's own +z axis and the apron does not have to turn at all.
        """
        return (0.0, self.pan_floor - self.fall(u),
                self._field_z() + self.plan_run * min(1.0, u))

    def half_at(self, u: float) -> float:
        t = _ease(min(1.0, max(0.0, u)))
        return self.PAN_HALF + (self._launch_half - self.PAN_HALF) * t

    def _launch_section(self) -> list[tuple[float, float]]:
        """The launch's section, as (across fraction, rise above the seat).

        The floor is re-sampled at `COLUMNS` points from `layout.floor_y_at` -
        the same analytic cradle the channel's own profile approximates with
        five - because five points across a 5.57-wide field is a facet every
        0.70 units, wider than a marble. The lip and the guard are taken from
        `channel_profile` unchanged, so the containment above the cradle is the
        run's own.

        `across` is a fraction of the clear half width, so `half_at` carries it.
        """
        floor = []
        for step in range(self.COLUMNS + 1):
            fraction = -1.0 + 2.0 * step / self.COLUMNS
            rise = (layout.floor_y_at(abs(fraction) * layout.CHANNEL_HALF)
                    - layout.FLOOR_Y)
            floor.append((fraction, rise))
        walls = [(across / layout.CHANNEL_HALF, up - layout.FLOOR_Y)
                 for across, up in channel_profile(1.0)
                 if abs(across) > layout.CHANNEL_HALF + 1e-9]
        left = sorted((a, r) for a, r in walls if a < 0.0)
        right = sorted((a, r) for a, r in walls if a > 0.0)
        return left + floor + right

    def section_at(self, u: float) -> list[tuple[float, float]]:
        """The apron read across at `u`: flat at the line, the launch's at the seam.

        The point *count* is constant, which is what `_strip` needs, so the
        blend flattens the launch's cradle rather than deleting points from it.
        Only the floor flattens - the lip and the guard keep their height the
        whole way, because they are containment and the field is 5.6 wide.
        """
        blend = _ease((max(0.0, min(1.0, u)) - self.SECTION_FROM)
                      / max(1.0 - self.SECTION_FROM, 1e-6))
        out = []
        for across, rise in self._launch_section():
            if abs(across) <= 1.0 + 1e-9:
                out.append((across, rise * blend))
            else:
                out.append((across, rise))
        return out

    def _groove(self, u: float, across: float) -> float:
        """No grooves. See `GROOVE_TO` for what the first build's cost."""
        return 0.0

    def _chevron(self, u: float, across: float) -> float:
        """Candidate C: shallow ridges that lean across the field.

        A chevron is a ridge whose crest runs at an angle to the flow, so a
        marble meeting it is steered *sideways* rather than stopped. Symmetric
        about the centreline, alternating in sense, and 0.11 tall - a marble
        rides over one and is deflected, it does not queue behind it.
        """
        if not self.cross_flow:
            return 0.0
        total = 0.0
        half = max(self.half_at(u), 1e-6)
        for at, sense in self.CROSS_ROWS:
            # The crest's own plan position at this lateral offset: a straight
            # ridge, skewed by `CROSS_SKEW` of the run across the field.
            centre = at + sense * self.CROSS_SKEW * (across / half) * 0.5
            width = 0.055
            offset = (u - centre) / width
            if abs(offset) < 3.0:
                total += self.CROSS_RISE * math.exp(-offset * offset)
        return total

    def surface(self, u: float, fraction: float) -> tuple[float, float, float]:
        """One point on the apron. `fraction` is across, in [-1, 1] of the half."""
        centre = self.centre_at(u)
        half = self.half_at(u)
        across = fraction * half
        rise = 0.0
        for a, r in self.section_at(u):
            if abs(a - fraction) < 1e-9:
                rise = r
                break
        return (across, centre[1] + rise, centre[2])

    # --- the collider -----------------------------------------------------

    def local_colliders(self) -> list[TriMesh]:
        if self._mesh is not None:
            return [self._mesh]
        rings: list[list[tuple[float, float, float]]] = []
        heel = self.heel_u
        for row in range(-self.HEEL_ROWS, self.ROWS + 1):
            u = heel * (-row / self.HEEL_ROWS) if row < 0 else row / self.ROWS
            centre = self.centre_at(u)
            half = self.half_at(u)
            ring = []
            for across, rise in self.section_at(u):
                offset = across * half
                lift = rise
                if abs(across) <= 1.0 + 1e-9:
                    lift += self._groove(u, offset) + self._chevron(u, offset)
                ring.append(_place(self.origin, self.frame,
                                   (offset, centre[1] + lift, centre[2])))
            rings.append(ring)
        pieces = [_strip(rings, f"{self.id}_apron"), self._backstop()]
        self._mesh = merge_meshes(pieces, f"{self.id}_wide")
        return [self._mesh]

    def _backstop(self) -> TriMesh:
        floor = self.pan_floor
        z = self.PAN_BACK
        corners = [
            (-self.PAN_HALF, floor, z),
            (self.PAN_HALF, floor, z),
            (self.PAN_HALF, floor + 0.46, z),
            (-self.PAN_HALF, floor + 0.46, z),
        ]
        return plate([_place(self.origin, self.frame, p) for p in corners],
                     name=f"{self.id}_backstop", steps=5)

    # --- the gate ---------------------------------------------------------

    def local_actuators(self) -> list[Actuator]:
        """One paddle per bay, placed from the pan's own numbers.

        **Not inherited.** `StartGrid.local_actuators` reads `_t_at_z`,
        `_half_at` and `_path_at`, which describe the *fan's* trough; V1.5's
        radial start inherited them and the paddles stood out on the apron,
        downhill of the field, where bay 7 ran into one and stopped for eleven
        seconds. This module has no trough either.
        """
        from marble3d.modules.base import LinearGate

        gates: list[Actuator] = []
        for index in range(layout.BAYS):
            gate_z = self._gate_z_for(index)
            u = (gate_z - self._field_z()) / max(self.plan_run, 1e-9)
            floor = self.pan_floor - self.fall(u)
            position = _place(
                self.origin,
                self.frame,
                (_bay_x(index), floor + 0.5 * layout.GATE_HEIGHT, gate_z),
            )
            gates.append(
                LinearGate(
                    name=f"paddle{index}",
                    # (thin along the flow, up, across). `basis_from_forward_up`
                    # puts `forward` on local X and `_rotation` passes the flow
                    # direction; see `StartGrid.local_actuators` for what
                    # reading that the other way round cost.
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

    # --- what the simulation needs ----------------------------------------

    def marble_starts(self) -> list[Transform]:
        """Eight resting places on the flat pan, at the drawn bay pitch."""
        rotation = self._rotation()
        return [
            Transform(
                position=_place(
                    self.origin,
                    self.frame,
                    (_bay_x(index), self.pan_floor + MARBLE_RADIUS,
                     self._field_z_for(index)),
                ),
                rotation=rotation,
            )
            for index in range(layout.BAYS)
        ]

    def local_sockets(self) -> dict[str, Socket]:
        seat = _place(self.origin, self.frame,
                      (0.0, self.exit_local[1] + layout.FLOOR_Y, self.exit_local[2]))
        forward = tuple(float(v) for v in self.frame[2])
        return {
            "exit": Socket(
                name="exit",
                frame=Transform(
                    position=seat,
                    rotation=basis_from_forward_up(forward, (0.0, 1.0, 0.0)),
                ),
                kind=GUIDED,
                width=to_sim(2.0 * self._launch_half),
                height=to_sim(layout.CONTAINMENT_TOP - layout.FLOOR_Y),
            )
        }

    def local_bounds(self) -> Aabb:
        bounds = self.local_colliders()[0].aabb()
        return Aabb(
            tuple(value - MARBLE_DIAMETER for value in bounds.lower),
            tuple(value + MARBLE_DIAMETER for value in bounds.upper),
        )

    def local_probes(self) -> list[Probe]:
        """Floor rays down the apron, at five lateral stations.

        The gate row is skipped for the reason `StartGrid` skips its own: a
        probe fired where a kinematic body stands measures the paddle and
        reports the floor as missing, and loosening the tolerance is what would
        make the rest of the check worthless.
        """
        probes: list[Probe] = []
        reach = 3.0 * MARBLE_RADIUS
        gate_u = (self.gate_z - self._field_z()) / max(self.plan_run, 1e-9)
        for row in range(-1, 21):
            u = self.heel_u * 0.5 if row < 0 else row / 20.0
            if abs(u - gate_u) < 0.035:
                continue
            centre = self.centre_at(u)
            half = self.half_at(u)
            for fraction in (-0.86, -0.45, 0.0, 0.45, 0.86):
                offset = fraction * half
                rise = 0.0
                for a, r in self.section_at(u):
                    if abs(a - fraction) < 0.06:
                        rise = r
                        break
                rise += self._groove(u, offset) + self._chevron(u, offset)
                surface = _place(self.origin, self.frame,
                                 (offset, centre[1] + rise, centre[2]))
                probes.append(
                    Probe(
                        start=(surface[0], surface[1] + reach, surface[2]),
                        end=(surface[0], surface[1] - reach, surface[2]),
                        expect_hit=True,
                        expected_point=surface,
                        tolerance=0.08,
                        label=f"{self.id}.apron[{row}]{fraction:+.2f}",
                    )
                )
        return probes

    def describe(self) -> dict[str, Any]:
        table = apron_table(self)
        return {
            "kind": "WideLaunch",
            "start_kind": self.START_KIND,
            "bays": layout.BAYS,
            "bay_pitch": round(to_sim(layout.BAY_PITCH), 6),
            "yaw_deg": round(self.yaw_deg, 4),
            "lift": round(self.lift, 4),
            "plan_run": round(self.plan_run, 4),
            "launch_factor": self.LAUNCH_FACTOR,
            "cross_flow": self.cross_flow,
            "release_time": self.release_time,
            "gate_z": round(self.gate_z, 4),
            "heights": {
                "pan_floor": round(self.pan_floor, 4),
                "seam_floor": round(self.pan_floor - self.fall(1.0), 4),
                "exit_y": round(self.exit_local[1], 4),
                "exit_seat": round(self.exit_local[1] + layout.FLOOR_Y, 4),
            },
            "widths": {
                "pan_half": self.PAN_HALF,
                "seam_half": round(self._launch_half, 4),
                "pod_half": layout.START_BACK_HALF,
                "hero_half": layout.CHANNEL_HALF,
            },
            "apron": table["rows"],
            "spread": table["spread"],
        }


def apron_table(start: WideLaunch) -> dict:
    """The apron measured along its run: width, grade, and the cross-slope.

    The cross-slope is the number this architecture lives or dies by. A marble
    can only change lateral position if the surface does not push it back, so
    the report carries the slope at the field's edge - the launch's own dish is
    4.3 degrees where the hero channel's wall is 30.
    """
    rows = []
    for step in range(11):
        u = step / 10.0
        half = start.half_at(u)
        edge = 0.0
        for across, rise in start.section_at(u):
            if abs(across - 1.0) < 1e-9:
                edge = rise
                break
        rows.append({
            "u": round(u, 3),
            "z": round(start.centre_at(u)[2], 4),
            "floor": round(start.centre_at(u)[1], 4),
            "grade_deg": round(start.grade_deg(u), 3),
            "half_width": round(half, 4),
            "width": round(2.0 * half, 4),
            "edge_rise": round(edge, 4),
            "cross_slope_deg": round(math.degrees(math.atan2(edge, half)), 3),
            # At the crest, which is midway between two bays - queried at a
            # bay's own centre this reads zero, because that is the groove's
            # floor.
            "groove_rise": round(start._groove(u, 0.0), 4),
            "marbles_abreast": int((2.0 * half) // (2.0 * layout.MARBLE_RADIUS)),
        })
    widths = [row["width"] for row in rows]
    return {
        "rows": rows,
        "spread": {
            "width": [min(widths), max(widths)],
            "width_ratio": round(max(widths) / min(widths), 4),
            "grade": [rows[0]["grade_deg"], rows[-1]["grade_deg"]],
            "mean_grade_deg": round(
                math.degrees(math.atan(start.mean_grade())), 3),
            "lift": round(start.lift, 4),
            "plan_run": round(start.plan_run, 4),
            "drop": round(start.fall(1.0), 4),
            "narrowest_marbles_abreast": min(r["marbles_abreast"] for r in rows),
            "edge_cross_slope_at_seam_deg": rows[-1]["cross_slope_deg"],
            "groove_gone_by": start.GROOVE_TO,
        },
    }

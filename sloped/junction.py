"""The merge junction as one surface, probed by ray rather than by argument.

## Why this exists

`tools/sloped_continuity_check.py` audits a *run*: its centreline curvature, its
bank rate, its grade, and the floor step where one run's socket meets the next.
It cannot see the merge, because the merge is not a run. Three swept channels
and a height field overlap there, and what a marble rests on is whichever of
them happens to be highest at that point - a question no per-run audit asks.

So this fires a vertical ray at every point of a *running line* and reports the
surface it finds, with the module that owns it. Vertical because that is the
question gravity asks; per-owner because the answer "the apron, not the channel"
is the finding.

## The one rule this instrument exists to enforce

`sloped_race_v111_leg2.md` records what a centreline audit misses:

    A downhill centreline is insufficient if bank change creates an uphill
    edge.

leg2's pocket was invisible for three versions because every audit measured the
centreline, where the run descends throughout. So every walk here is done at
**five lateral fractions**, and a climb on any of them is a finding. The same
rule applied to the merge and to the two branch tails found three more defects
of the same shape - see `docs/sloped_race_v112_merge.md`.

## What the walk reports, per station and per lateral line

* **floor** - the highest surface at or below the nominal running point, and
  its owner. `None` is a hole: nothing under a marble that is nominally on the
  course - **and a hole is only a hole if a marble fits in it.** Where three
  meshes meet, a single ray can pass between them: at `merge_lead[11]`'s east
  edge the lead's last ring, the sprint's first and the apron's shoulder all
  arrive within 0.002 units, one ray missed, and every neighbour 0.1 out had
  floor within 0.06 of the nominal height. A marble is 1.0 across, so a crack
  0.2 wide is a tessellation seam and not a loss site. A miss is therefore
  re-probed on a ring of `HOLE_REACH` and only reported when the whole
  neighbourhood is empty.

  **Probed a whisker downstream of the station, not on it.** A swept run's
  first and last rings are the boundary of its mesh, so a vertical ray at the
  exact (x, z) of a ring point meets that mesh in a single vertex - a
  measure-zero hit a barycentric test may take or leave. Walked on the stations
  themselves, `merge_lead[0]` and `final[0]` both reported holes on two lines
  each, at seams whose colliders in fact overlap. `NUDGE` is a fraction of the
  local sample spacing along the run's own tangent, which puts every ray inside
  a strip.
* **grade** - rise over run along the line, in percent, against the *previous*
  station of the same line. Positive is a climb. Measured against horizontal
  distance travelled rather than per sample, because the stations of two
  different runs are not the same distance apart and a per-sample step reads a
  1.9-unit gap between two runs' ends as a cliff. That mistake was made once
  here and it reported a 19% drop as a 0.19-unit step.

  **And only when the step is downstream.** Two runs that share a seam do not
  share a *contact* point exactly: their grades differ at the seam, so their
  cradle bottoms are offset by `up`-difference times the cradle depth - 0.010
  simulation units at the merge lead's exit, where the two grades are 22.0% and
  24.5%. The lead's last station is therefore 0.010 further **down** the slope
  than the sprint's first, and a walk that stepped between them backwards
  reported the 0.009 of height it had already descended as a +24.7% climb. The
  step is projected on the direction of travel and a backward step gets no
  grade.
* **clearance** - floor to the next surface above it. A roof is intentional at
  the merge; a surface a marble's diameter above the floor is a ledge.
* **ledge** - a surface between the floor and one diameter above it, which is
  what a guard rail standing inside an apron leaves along its own top.

## And the basin metric, which is the same one leg2 was fixed on

`climb_survey` walks one run's own surface at several lateral fractions and
reports the deepest climb from a running minimum - a closed basin, in
simulation units, with the speed needed to leave it. `tools/sloped_pocket_survey.py`
does this for `CHAIN + ("final",)` only, which is why `blue`'s basin of 0.3013
and `orange`'s of 0.9223 survived three versions unmeasured. Both branch lobes
are surveyed here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

from marble3d.units import GRAVITY, MARBLE_DIAMETER, MARBLE_RADIUS

from sloped import layout
from sloped.scale import to_sim

__all__ = [
    "SurfaceIndex",
    "Reading",
    "EdgeWalk",
    "FRACTIONS",
    "walk_line",
    "climb_survey",
    "branch_frame",
    "escape_speed",
    "reference_frame",
]

# The lateral lines every walk is done on, as fractions of the channel's clear
# half width. The two at 0.85 are where a marble thrown across the channel by a
# roll reversal actually rides; the centreline is the one that hides the defect.
FRACTIONS = (
    (-0.85, "W-edge"),
    (-0.45, "W-mid"),
    (0.0, "centre"),
    (0.45, "E-mid"),
    (0.85, "E-edge"),
)

# A rolling sphere carries 7/5 of a sliding one's kinetic energy at the same
# speed, so leaving a basin of height `h` costs sqrt(10/7 * g * h).
ROLLING = 10.0 / 7.0


def escape_speed(climb: float) -> float:
    """The forward speed a rolling marble needs to clear `climb`, in wu/s."""
    return math.sqrt(max(climb, 0.0) * ROLLING * GRAVITY)


class SurfaceIndex:
    """Every collider triangle of a machine, indexed for vertical ray casts.

    The sloped machine places every module at the identity transform - see
    `sloped.course`, which asserts placement rather than deriving it - so a
    module's local collider vertices are already world coordinates and no
    transform is applied here. That is asserted rather than assumed: the
    constructor raises on a module whose placement is not the identity.
    """

    CELL = 1.0                  # a marble diameter, in simulation units

    def __init__(self, machine, owners: Sequence[str] | None = None) -> None:
        self.tris: list[tuple[str, tuple]] = []
        self.grid: dict[tuple[int, int], list[int]] = {}
        for name, module in machine.modules.items():
            if owners is not None and name not in owners:
                continue
            placement = getattr(module, "transform", None)
            if placement is not None:
                position = tuple(placement.position)
                if max(abs(v) for v in position) > 1e-9:
                    raise ValueError(
                        f"{name} is placed at {position}; SurfaceIndex reads local "
                        "collider vertices as world coordinates and only the sloped "
                        "machine's identity placement makes that true"
                    )
            for mesh in module.local_colliders():
                for triangle in mesh.triangles():
                    self._add(name, triangle)

    def _add(self, owner: str, triangle) -> None:
        index = len(self.tris)
        self.tris.append((owner, triangle))
        xs = [point[0] for point in triangle]
        zs = [point[2] for point in triangle]
        for cx in range(
            int(math.floor(min(xs) / self.CELL)), int(math.floor(max(xs) / self.CELL)) + 1
        ):
            for cz in range(
                int(math.floor(min(zs) / self.CELL)), int(math.floor(max(zs) / self.CELL)) + 1
            ):
                self.grid.setdefault((cx, cz), []).append(index)

    def column(self, x: float, z: float) -> list[tuple[float, str]]:
        """Every surface directly under or over (x, z), highest first."""
        out: list[tuple[float, str]] = []
        cell = (int(math.floor(x / self.CELL)), int(math.floor(z / self.CELL)))
        for index in self.grid.get(cell, ()):
            owner, triangle = self.tris[index]
            height = _ray_down(x, z, *triangle)
            if height is not None:
                out.append((height, owner))
        out.sort(key=lambda row: -row[0])
        return out


def _ray_down(x: float, z: float, a, b, c) -> float | None:
    """Where the vertical line at (x, z) meets triangle abc, or None.

    Barycentric in the XZ plane, which is exact and needs no epsilon on the
    height. A triangle with zero area *in plan* - which a vertical wall is - is
    rejected by the determinant test, and that is the right answer: a vertical
    wall has no surface a falling marble lands on.
    """
    det = (b[0] - a[0]) * (c[2] - a[2]) - (c[0] - a[0]) * (b[2] - a[2])
    if abs(det) < 1e-12:
        return None
    px, pz = x - a[0], z - a[2]
    u = (px * (c[2] - a[2]) - (c[0] - a[0]) * pz) / det
    v = ((b[0] - a[0]) * pz - px * (b[2] - a[2])) / det
    if u < -1e-9 or v < -1e-9 or u + v > 1.0 + 1e-9:
        return None
    return a[1] + u * (b[1] - a[1]) + v * (c[1] - a[1])


@dataclass
class Reading:
    """What the surface does under one station of one lateral line."""

    station: str
    line: str
    floor: float | None
    owner: str | None
    grade: float | None          # percent of horizontal travel, positive uphill
    clearance: float | None      # floor to the next surface above
    ledge: float | None          # that clearance, when it is under one diameter

    def to_json(self) -> dict[str, Any]:
        return {
            "station": self.station,
            "line": self.line,
            "floor": None if self.floor is None else round(self.floor, 4),
            "owner": self.owner,
            "grade_pct": None if self.grade is None else round(self.grade, 2),
            "clearance": None if self.clearance is None else round(self.clearance, 4),
            "ledge": None if self.ledge is None else round(self.ledge, 4),
        }


@dataclass
class EdgeWalk:
    """A whole walk, with the findings already picked out of it."""

    readings: list[Reading]
    holes: list[Reading]
    climbs: list[Reading]
    ledges: list[Reading]
    tight: list[Reading]

    def worst_climb(self) -> Reading | None:
        return max(self.climbs, key=lambda r: r.grade or 0.0, default=None)

    def clean(self) -> bool:
        return not (self.holes or self.climbs or self.ledges or self.tight)

    def to_json(self) -> dict[str, Any]:
        return {
            "stations": len({r.station for r in self.readings}),
            "clean": self.clean(),
            "holes": [r.to_json() for r in self.holes],
            "climbs": [r.to_json() for r in self.climbs],
            "ledges": [r.to_json() for r in self.ledges],
            "tight": [r.to_json() for r in self.tight],
            "readings": [r.to_json() for r in self.readings],
        }


# How far below the nominal running surface a floor may be and still be the
# floor a marble rides. Half a diameter: deeper than that and the marble is
# falling to it rather than rolling on it, and calling it the floor would hide
# the drop.
FLOOR_BAND = MARBLE_RADIUS
# A climb worth reporting, in percent of horizontal travel. The course's own
# shallowest authored grade is 10%, so anything positive is against the flow;
# half a percent is the threshold that keeps facet rounding out of the list.
CLIMB_PCT = 0.5
# How far downstream of its own station each ray is fired, as a fraction of the
# local sample spacing. Small enough that the reading is the station's, large
# enough that a ray at a run's first or last ring lands inside a triangle
# rather than on the vertex that bounds it. See the module docstring.
NUDGE = 0.05
# How far out a missed ray is re-probed before the miss is called a hole, in
# simulation units. Half a marble radius: a marble bridges anything narrower.
HOLE_REACH = 0.5 * MARBLE_RADIUS


def walk_line(
    index: SurfaceIndex,
    runs: dict,
    stations: Sequence[tuple[str, int]],
    fractions: Sequence[tuple[float, str]] = FRACTIONS,
) -> EdgeWalk:
    """Probe every lateral line through a sequence of (run, sample) stations.

    The stations may span runs - that is the point - and the grade is taken
    against horizontal distance rather than per station, so a walk that steps
    from one run's last sample to the next run's first does not read the gap
    between them as a cliff.
    """
    readings: list[Reading] = []
    previous: dict[str, tuple[float, float, float]] = {}
    for run_name, sample in stations:
        run = runs[run_name]
        label = f"{run_name}[{sample}]"
        _lateral, _up, forward = run.frames[min(sample, len(run.frames) - 1)]
        spacing = run.sim_arc[-1] / max(len(run.sim_path) - 1, 1)
        for fraction, line in fractions:
            seat = run.surface_point(sample, fraction * layout.CHANNEL_HALF)
            nominal = tuple(
                seat[axis] + forward[axis] * NUDGE * spacing for axis in range(3)
            )
            column = index.column(nominal[0], nominal[2])
            floor = next(((y, o) for y, o in column if y <= nominal[1] + FLOOR_BAND), None)
            if floor is None:
                bridged = _bridged(index, nominal)
                if bridged is None:
                    readings.append(Reading(label, line, None, None, None, None, None))
                    previous.pop(line, None)
                    continue
                # A bridged floor is a neighbour's height, not this station's,
                # so it is reported and then **dropped from the grade chain**.
                # Feeding it in read the 0.048 offset to the neighbour as a
                # +30.4% climb at `merge_lead[11]`, which is the same class of
                # error as measuring a grade across a 1.9-unit gap.
                readings.append(
                    Reading(label, line, bridged[0], bridged[1], None, None, None)
                )
                previous.pop(line, None)
                continue
            above = [(y, o) for y, o in column if y > floor[0] + 0.06]
            clearance = min((y - floor[0] for y, _o in above), default=None)
            ledge = clearance if clearance is not None and clearance < MARBLE_DIAMETER else None
            grade = None
            last = previous.get(line)
            if last is not None:
                step = (nominal[0] - last[0], nominal[2] - last[2])
                run_h = math.hypot(*step)
                downstream = step[0] * forward[0] + step[1] * forward[2]
                if run_h > 1e-6 and downstream > 0.0:
                    grade = 100.0 * (floor[0] - last[1]) / run_h
            readings.append(Reading(label, line, floor[0], floor[1], grade, clearance, ledge))
            previous[line] = (nominal[0], floor[0], nominal[2])
    return EdgeWalk(
        readings=readings,
        holes=[r for r in readings if r.floor is None],
        climbs=[r for r in readings if r.grade is not None and r.grade > CLIMB_PCT],
        ledges=[r for r in readings if r.ledge is not None],
        tight=[
            r for r in readings
            if r.clearance is not None and r.clearance < MARBLE_DIAMETER * 1.05
        ],
    )


def _bridged(index: SurfaceIndex, nominal) -> tuple[float, str] | None:
    """The floor a marble would bridge to, when the ray itself missed.

    Four rays at `HOLE_REACH` on the compass. The highest floor any of them
    finds is returned, because that is the surface a marble spanning the crack
    would rest on. `None` only when the neighbourhood really is empty.
    """
    best: tuple[float, str] | None = None
    for dx, dz in ((HOLE_REACH, 0.0), (-HOLE_REACH, 0.0), (0.0, HOLE_REACH), (0.0, -HOLE_REACH)):
        for height, owner in index.column(nominal[0] + dx, nominal[2] + dz):
            if height <= nominal[1] + FLOOR_BAND:
                if best is None or height > best[0]:
                    best = (height, owner)
                break
    return best


def climb_survey(
    run,
    fractions: Sequence[float] = (0.0, 0.4, 0.55, 0.7, 0.85, 0.95),
    low: int = 0,
    high: int | None = None,
) -> dict[str, Any]:
    """The deepest closed basin on one run's own surface, per lateral fraction.

    The metric `sloped.track._slewed_bank` exists to drive to zero: the largest
    rise above a running minimum along the line, which is what a marble that
    has lost its speed cannot leave.

    `fractions` are magnitudes and **both signs are walked**, because a roll
    reversal digs its basin on whichever edge the roll leaves high and the
    answer is not symmetric. `tools/sloped_pocket_survey.py` walks one sign
    only, which is safe on the chain runs and would have halved the answer on
    the branches.
    """
    high = len(run.sim_path) if high is None else high
    out: dict[str, Any] = {"run": run.id, "from": low, "to": high, "lines": {}}
    worst = (0.0, None, None)
    for magnitude in fractions:
        for sign in ((1.0,) if magnitude == 0.0 else (-1.0, 1.0)):
            fraction = sign * magnitude
            heights = [
                run.surface_point(i, fraction * layout.CHANNEL_HALF)[1]
                for i in range(low, high)
            ]
            floor_i, floor_h, deep, at, start = low, heights[0], 0.0, None, low
            for offset, height in enumerate(heights):
                if height < floor_h:
                    floor_h, floor_i = height, low + offset
                if height - floor_h > deep:
                    deep, at, start = height - floor_h, low + offset, floor_i
            out["lines"][f"{fraction:+.2f}"] = {
                "climb": round(deep, 4),
                "from_sample": start,
                "to_sample": at,
                "escape_speed": round(escape_speed(deep), 3),
            }
            if deep > worst[0]:
                worst = (deep, fraction, at)
    out["worst"] = {
        "climb": round(worst[0], 4),
        "fraction": worst[1],
        "at_sample": worst[2],
        "escape_speed": round(escape_speed(worst[0]), 3),
    }
    return out


def reference_frame(run, index: int = 0):
    """`(origin, forward, lateral, up)` at one sample - the frame to compare in.

    The sprint's own frame at its entry, normally. Two branches 147 degrees
    apart cannot be compared in world coordinates and this is the frame the
    rebuilt merge is laid out in.
    """
    lateral, up, forward = run.frames[index]
    return (run.surface_point(index, 0.0), forward, lateral, up)


def branch_frame(run, index: int, reference=None) -> dict[str, Any]:
    """One incoming branch's endpoint frame, in the terms the rebuild needs.

    Section 2 of the V1.12 brief lists them: running-surface position, tangent,
    elevation, signed bank, the two running edges and the two guard edges. All
    read off the *built* run rather than from its spec, so a change to the path
    law or the bank law moves them.

    With `reference` - a frame from `reference_frame` - every point and vector
    is also given in that frame, which is the only form in which two branches
    that arrive head-on can be compared.
    """
    lateral, up, forward = run.frames[index]
    contact = run.surface_point(index, 0.0)
    half = layout.CHANNEL_HALF
    edges = {
        "west_running": run.surface_point(index, -half),
        "east_running": run.surface_point(index, +half),
    }
    # The guard's inner face, which is the surface a marble climbing the wall
    # meets, at the height the run actually carries at this sample - the boost
    # included, because `guard_extra` is already in layout units of this run's
    # own scale.
    guard_across = layout.GUARD_INNER * run.scale * run.widths[index]
    guard_rise = layout.GUARD_BASE * run.scale + run.guard_extra(index)
    for name, sign in (("west_guard", -1.0), ("east_guard", +1.0)):
        edges[name] = tuple(
            run.sim_path[index][axis]
            + lateral[axis] * to_sim(sign * guard_across)
            + up[axis] * to_sim(guard_rise)
            for axis in range(3)
        )
    horizontal = max(math.hypot(forward[0], forward[2]), 1e-9)
    out: dict[str, Any] = {
        "run": run.id,
        "sample": index,
        "contact": [round(v, 4) for v in contact],
        "centre": [round(v, 4) for v in run.sim_path[index]],
        "tangent": [round(v, 5) for v in forward],
        "up": [round(v, 5) for v in up],
        "lateral": [round(v, 5) for v in lateral],
        "heading_deg": round(run.heading_deg(index), 3),
        "bank_deg": round(math.degrees(run.banks[index]), 3),
        "grade_pct": round(-100.0 * forward[1] / horizontal, 3),
        "half_width": round(0.5 * run.clear_width * run.widths[index], 4),
        "containment": round(run.containment_at(index), 4),
        "scale": run.scale,
        "edges": {name: [round(v, 4) for v in point] for name, point in edges.items()},
    }
    if reference is not None:
        origin, fwd, lat, upr = reference

        def local(point):
            offset = [point[axis] - origin[axis] for axis in range(3)]
            return [
                round(sum(offset[axis] * fwd[axis] for axis in range(3)), 4),
                round(sum(offset[axis] * lat[axis] for axis in range(3)), 4),
                round(sum(offset[axis] * upr[axis] for axis in range(3)), 4),
            ]

        def direction(vector):
            return [
                round(sum(vector[axis] * fwd[axis] for axis in range(3)), 5),
                round(sum(vector[axis] * lat[axis] for axis in range(3)), 5),
                round(sum(vector[axis] * upr[axis] for axis in range(3)), 5),
            ]

        out["in_reference"] = {
            "contact": local(contact),
            "tangent": direction(forward),
            "edges": {name: local(point) for name, point in edges.items()},
        }
    return out

"""The course as one continuous curve, and the clear air beside it.

V28's camera solves every shot from the *pack*: a centroid, an extent, a
bearing off the local heading, and a reach sized so the leading group fills a
fraction of frame. That is the right answer to "how big are the racers" and it
is the wrong answer to "where is the camera", because it has no memory. Two
consecutive frames are solved independently, and the only thing keeping the
lens from teleporting is a smoothing pass over the result.

A chase camera is not a sequence of framings. It is **a thing travelling along
the course**, and to be one it needs the course to be a thing you can travel
along. That is this module.

## The spine

`Spine` concatenates the eleven runs of the switchyard, in stage order, into
one polyline with a cumulative arc length. Every sample carries its point, the
horizontal tangent, a horizontal `right`, the channel's banked `up`, its half
width and its guard height - so a camera can be placed at an *arc length*
rather than at a point, and "where is the pack" becomes a scalar.

**Why arc length and not world position.** On a course that folds back on
itself five times, two points eight units apart in world space can be forty
units apart along the course with two other legs in between, and every
occlusion failure V28 recorded is of that shape. It also settles the switchback
problem, which is the thing this branch exists to solve:

> A camera that trails the pack **along the spine** inherits the course's own
> reversal. When the course turns back on itself the camera turns with it, so
> the racers still recede from the lens and the screen direction is preserved.
> A camera that stands off to one side in *world* space does not: the pack
> crosses frame left-to-right on one corridor and right-to-left on the next,
> and no amount of smoothing repairs that.

That is the whole argument for this module in three lines, and section 6 of
`docs/race2_v281_racing_cinematography.md` measures it.

## The rail

A folded course occludes itself - V28's finding, which this branch does not get
to repeal. What it can do is stop rediscovering it sixty times a second.
`camera_rail` solves, once per course, the question

> standing off the channel at arc length `s`, in which direction and how high
> is there clear air *and* a sightline to the racers ahead?

and returns a world azimuth and a height per sample. Three consequences:

1. **Occlusion is solved offline**, against the course rather than against a
   race, so the rail is the same for every seed.
2. **It is continuous by construction**: the solve walks forward and pays for
   moving the lens from where it was. V28's per-frame lift loop had no such
   term and could not have - it has no previous frame.
3. **It is reusable**: a second course gets a rail by being a `Spine`.

### Two corrections the solve needed, and what they found

**The first solve was given the whole circle and stopped being a chase camera.**
It put the lens nine units *downcourse along the tangent* at the top of the
height range, from the second pan to the line - because in front of the racers
and high is the position with the most clear air and the most clear sightlines
on a folded course, and clearance and sightline were the only things scored. It
is also the head-on map view the brief rules out. The rail decides **which side
of the channel** the lens stands on; the trail along the spine is the rig's, and
giving the rail the freedom to cancel it produced a camera that had solved a
different problem correctly. Hence `PERPENDICULAR_MAX`.

**The second solve was parameterised in the local frame and could not express
its own answer.** Constrained to a lateral band it converged on the same world
direction everywhere - the **downcourse (+Z) side** - and that is not a
preference, it is forced: the switchyard descends 0.645 layout units of height
per unit of +Z, so the downcourse side of any leg is *above* the next leg and
the upcourse side is *below* the previous one. A lens 9 units upcourse of
`corr2` sits inside `corr1`'s guard envelope; the same lens downcourse sits
eleven units clear above `corr3`. But the local frame reverses at every
corridor, so holding one world direction means swinging the local angle through
180 degrees five times, and each swing passes through "directly in front of the
pack". The rail is therefore in **world azimuth**, where its answer is nearly
constant and trivially continuous, and the local frame appears only in the
perpendicularity constraint.

`tools/race2_cine.py --rail` prints the solved azimuths and the clearance and
sightline each achieves, so both claims can be checked against the geometry.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

from sloped.scale import SIM_TO_LAYOUT

__all__ = [
    "Spine",
    "Rail",
    "camera_rail",
    "RAIL_HEIGHTS",
    "RAIL_REACH",
    "RAIL_LEAN",
]

# How far the rail may lean off the course's own downhill direction, in
# degrees, and in what steps. A band rather than the whole circle, because the
# downhill direction is not a preference here - see `Spine.downhill_azimuth`.
RAIL_LEAN = 60.0
RAIL_STEP = 10.0
# What a degree of lean costs in the score, so the rail holds the downhill
# direction unless the geometry pays it to leave.
LEAN_COST = 0.05

# Heights above the channel, in layout units. The floor is what it takes to see
# a marble over its own near rail in the widest pan; the ceiling is where the
# shot stops being a three-quarter view. The first solve pinned itself to the
# top of a range that reached 11, so the range stops at 9 and height carries a
# standing cost in the score.
RAIL_HEIGHTS = tuple(2.5 + 0.5 * i for i in range(14))

# How far the rail stands off the channel while solving, in layout units. The
# rig scales its own reach around this; what the rail decides is the direction
# and the height, which are the parts the geometry constrains.
RAIL_REACH = 9.0

# How far ahead the rail checks it can see, in layout units of arc, chosen to
# bracket the trail distances the rigs actually use. A chase camera looks at
# racers ahead of it on the course, so the sightline that matters is to the
# channel downcourse and not to the sample the lens is beside.
RAIL_SIGHT = (4.0, 7.0, 11.0)

# What moving the lens costs, so the answer bends instead of jumping: score
# units per degree of azimuth and per layout unit of height.
TURN_COST = 0.06
LIFT_COST = 0.22
# And the standing cost of height, which is what stops the solve flying.
#
# **It has to outbid the sightline term or the rail pins itself to the
# ceiling.** At 0.17 against 1.5 per clear sightline the solve bought the last
# sightline with six units of altitude and sat at 9.0 for 120 of the course's
# 176 units - clear, seeing everything, and looking down at the race from
# above, which is the framing the brief rules out. Height is charged nearly
# three times as much here, and the sightline term is worth a unit rather than
# one and a half, so the rail comes down to whatever height the geometry
# actually demands.
HEIGHT_COST = 0.45

# Smoothing passes over the solved rail. The solve is on a 10-degree grid, so
# the rail needs enough smoothing that the grid is invisible in the camera's
# angular velocity, and few enough that it does not cut the corners the
# clearance search chose. What it does cut is repaired afterwards - see
# `_repair`, and the clearance figures `Rail.describe` reports are measured on
# the rail that will actually be flown.
RAIL_SMOOTH = 30
# The clear air the flown rail must keep, in layout units. V28's number, for
# V28's reason: a clear sightline is not a clear shot, and what ruined seed
# 140's sprint was beside the lens rather than in front of it.
RAIL_CLEARANCE = 2.4

# How far past the last run the spine carries a straight tail, in layout units.
# Enough to cover where the switchyard's field actually comes to rest - they
# roll five to seven units past the line - and no further, because past that it
# would be inventing course.
RUNOUT_TAIL = 8.0


def _norm(v: Sequence[float]) -> tuple[float, float, float]:
    span = math.sqrt(sum(float(c) * float(c) for c in v)) or 1.0
    return (float(v[0]) / span, float(v[1]) / span, float(v[2]) / span)


def _fit_plane(points: Sequence[Sequence[float]]) -> tuple[float, float, float]:
    """Least-squares `y = a + b*x + c*z` over a set of layout-unit points.

    Solved by the normal equations on a 3x3, which is enough conditioning for
    a few hundred points spread over tens of units and avoids a numpy import in
    a module the tests exercise without one.
    """
    n = float(len(points)) or 1.0
    sx = sum(p[0] for p in points)
    sz = sum(p[2] for p in points)
    sy = sum(p[1] for p in points)
    sxx = sum(p[0] * p[0] for p in points)
    szz = sum(p[2] * p[2] for p in points)
    sxz = sum(p[0] * p[2] for p in points)
    sxy = sum(p[0] * p[1] for p in points)
    szy = sum(p[2] * p[1] for p in points)
    matrix = [[n, sx, sz], [sx, sxx, sxz], [sz, sxz, szz]]
    rhs = [sy, sxy, szy]
    # Gauss-Jordan with partial pivoting on a 3x3.
    for column in range(3):
        pivot = max(range(column, 3), key=lambda r: abs(matrix[r][column]))
        if abs(matrix[pivot][column]) < 1e-12:
            return (sy / n, 0.0, 0.0)
        matrix[column], matrix[pivot] = matrix[pivot], matrix[column]
        rhs[column], rhs[pivot] = rhs[pivot], rhs[column]
        scale = matrix[column][column]
        matrix[column] = [v / scale for v in matrix[column]]
        rhs[column] /= scale
        for row in range(3):
            if row == column:
                continue
            factor = matrix[row][column]
            matrix[row] = [v - factor * w for v, w in zip(matrix[row], matrix[column])]
            rhs[row] -= factor * rhs[column]
    return (rhs[0], rhs[1], rhs[2])


class Spine:
    """The whole course as one arc-length-parameterised curve."""

    def __init__(self, course) -> None:
        self.course = course
        self.points: list[tuple[float, float, float]] = []
        self.tangents: list[tuple[float, float, float]] = []
        self.rights: list[tuple[float, float, float]] = []
        self.ups: list[tuple[float, float, float]] = []
        self.half_widths: list[float] = []
        self.containments: list[float] = []
        self.run_of: list[str] = []
        self.run_span: dict[str, tuple[int, int]] = {}

        names = [name for stage in course.stages for name in stage.runs]
        for name in names:
            run = course.runs[name]
            first = len(self.points)
            for index in range(len(run.path)):
                point = tuple(float(v) for v in run.path[index])
                # Consecutive runs share an endpoint exactly; keeping both would
                # put a zero-length segment in the arc table.
                if self.points and math.dist(self.points[-1], point) < 1e-9:
                    continue
                _lateral, up, _forward = run.frames[min(index, len(run.frames) - 1)]
                tangent = run.tangents[min(index, len(run.tangents) - 1)]
                flat = math.hypot(tangent[0], tangent[2]) or 1.0
                horizontal = (tangent[0] / flat, 0.0, tangent[2] / flat)
                self.points.append(point)
                self.tangents.append(horizontal)
                # `tangent x world up`, horizontal, turning with the tangent.
                # Deliberately *not* the run's own banked `lateral`.
                self.rights.append(_norm((-horizontal[2], 0.0, horizontal[0])))
                self.ups.append(_norm(up))
                self.half_widths.append(
                    0.5 * run.clear_width * run.widths[min(index, len(run.widths) - 1)]
                )
                self.containments.append(
                    float(run.containment_at(min(index, len(run.path) - 1)))
                )
                self.run_of.append(name)
            self.run_span[name] = (first, len(self.points) - 1)

        # **A tail past the line, along the last run's own direction.**
        #
        # The course ends at the finish; the race does not. On the switchyard
        # the eight racers roll another five to seven layout units out onto the
        # run-out deck and spread across it, and a camera whose arc pins at the
        # last sample has to solve its framing by standing further and further
        # out - which took the finish lens twenty units past the end of the
        # course, looking back over the deck's own edge, with a fifth of the
        # leading group behind it.
        #
        # So the spine carries a straight tail. It is not track and nothing
        # races on it; it is somewhere for the camera to keep travelling while
        # the field arrives, which is the whole of the payoff.
        if self.points and RUNOUT_TAIL > 0.0:
            tail_from = self.points[-1]
            direction = self.tangents[-1]
            drop = (self.points[-1][1] - self.points[-2][1]) / max(
                math.dist(self.points[-1], self.points[-2]), 1e-6
            )
            steps = max(int(RUNOUT_TAIL / 0.75), 1)
            first = len(self.points)
            for step in range(1, steps + 1):
                travel = RUNOUT_TAIL * step / steps
                self.points.append((
                    tail_from[0] + direction[0] * travel,
                    tail_from[1] + drop * travel,
                    tail_from[2] + direction[2] * travel,
                ))
                self.tangents.append(direction)
                self.rights.append(self.rights[-1])
                self.ups.append(self.ups[-1])
                self.half_widths.append(self.half_widths[-1])
                self.containments.append(self.containments[-1])
                self.run_of.append("runout")
            self.run_span["runout"] = (first, len(self.points) - 1)
            self.racing_length = None  # set below, once the arc table exists

        self.arc: list[float] = [0.0]
        for a, b in zip(self.points, self.points[1:]):
            self.arc.append(self.arc[-1] + math.dist(a, b))
        self.length = self.arc[-1]
        # Where the racing stops, as distinct from where the spine stops.
        raced = self.run_span.get("runout", (len(self.points) - 1, 0))[0]
        self.racing_length = self.arc[max(raced - 1, 0)]

        # **The plane the course lies on**, as a least-squares fit of height
        # against plan position: `y = a + bx + cz`. Two numbers come out of it
        # and the rail turns on both.
        #
        # `descent` is the fall per unit of +Z, and `downhill_azimuth` is the
        # plan direction of steepest descent. That direction is where the
        # camera has to stand, and it is **derived here rather than chosen**:
        # a leg's downhill side is above the next leg and its uphill side is
        # below the previous one, so on any folded course that descends, the
        # clear air is downhill. The switchyard's answer is +Z to within a
        # degree; a course that folded the other way would get the other
        # answer from the same three lines.
        self.plane = _fit_plane(self.points)
        _a, gradient_x, gradient_z = self.plane
        self.descent = gradient_z
        self.downhill_azimuth = math.degrees(math.atan2(-gradient_z, -gradient_x))

        # The course as blocker spheres, for clearance and sightline. Same
        # construction as `race2.camera.TrackState` and for the same reason:
        # this decides whether to move a camera, not whether a pixel is covered.
        self.blockers: list[tuple[float, float, float, float]] = []
        for name, run in course.runs.items():
            for index in range(0, len(run.path), 4):
                point = run.path[index]
                half = 0.5 * run.clear_width * run.widths[index]
                self.blockers.append(
                    (point[0], point[1], point[2],
                     half + run.containment_at(index) + 0.30)
                )
        for module in course.machine:
            if module.id in course.runs:
                continue
            bounds = module.bounds()
            centre = tuple(
                0.5 * (bounds.lower[axis] + bounds.upper[axis]) * SIM_TO_LAYOUT
                for axis in range(3)
            )
            radius = 0.5 * min(
                (bounds.upper[axis] - bounds.lower[axis]) * SIM_TO_LAYOUT
                for axis in range(3)
            )
            if radius > 0.3:
                self.blockers.append((centre[0], centre[1], centre[2], radius))

    # --- sampling --------------------------------------------------------

    def index_at(self, s: float) -> int:
        """The sample at or just before arc length `s`."""
        s = min(max(s, 0.0), self.length)
        lo, hi = 0, len(self.arc) - 1
        while lo < hi - 1:
            mid = (lo + hi) // 2
            if self.arc[mid] <= s:
                lo = mid
            else:
                hi = mid
        return lo

    def _interp(self, s: float):
        index = self.index_at(s)
        nxt = min(index + 1, len(self.points) - 1)
        span = self.arc[nxt] - self.arc[index]
        t = 0.0 if span <= 1e-9 else (min(max(s, 0.0), self.length) - self.arc[index]) / span
        return index, nxt, t

    def point_at(self, s: float) -> tuple[float, float, float]:
        a, b, t = self._interp(s)
        return tuple(
            self.points[a][axis] * (1.0 - t) + self.points[b][axis] * t
            for axis in range(3)
        )

    def frame_at(self, s: float) -> tuple:
        """`(forward, right, up)` at arc length `s`, all unit."""
        a, b, t = self._interp(s)
        forward = _norm(tuple(
            self.tangents[a][axis] * (1.0 - t) + self.tangents[b][axis] * t
            for axis in range(3)
        ))
        right = _norm(tuple(
            self.rights[a][axis] * (1.0 - t) + self.rights[b][axis] * t
            for axis in range(3)
        ))
        up = _norm(tuple(
            self.ups[a][axis] * (1.0 - t) + self.ups[b][axis] * t for axis in range(3)
        ))
        return forward, right, up

    def run_at(self, s: float) -> str:
        return self.run_of[self.index_at(s)]

    def half_width_at(self, s: float) -> float:
        return self.half_widths[self.index_at(s)]

    def curvature_at(self, s: float, window: float = 5.0) -> float:
        """Turn rate in degrees per layout unit, unsigned.

        Measured over a window rather than between neighbouring samples,
        because the hairpins are sampled finely enough that a two-sample
        difference is mostly quantisation. Used to tell a bend from a straight,
        which is where the rigs change what they are doing.
        """
        before = self.frame_at(max(s - window, 0.0))[0]
        after = self.frame_at(min(s + window, self.length))[0]
        dot = max(-1.0, min(1.0, before[0] * after[0] + before[2] * after[2]))
        return math.degrees(math.acos(dot)) / max(2.0 * window, 1e-6)

    def progress_of(
        self, point: Sequence[float], hint: float | None = None,
        back: float = 5.0, ahead: float = 26.0,
    ) -> float:
        """Arc length of the spine point nearest `point`, windowed on `hint`.

        **On a folded course a global nearest-point search is wrong**, not
        merely slow: the legs are 9.6 layout units apart in plan and the channel
        is 6.6 wide, so a marble riding the outside of a pan is genuinely nearer
        the centreline of the leg below than to its own. Windowing the search on
        the previous answer makes progress monotone, which is what a chase
        camera needs anyway.
        """
        if hint is None:
            lo, hi = 0, len(self.points) - 1
        else:
            lo = self.index_at(max(hint - back, 0.0))
            hi = self.index_at(min(hint + ahead, self.length))
        best = None
        for index in range(lo, hi + 1):
            distance = math.dist(self.points[index], point)
            if best is None or distance < best[0]:
                best = (distance, index)
        assert best is not None
        return self.arc[best[1]]

    # --- geometry queries -------------------------------------------------

    def clearance(self, position: Sequence[float]) -> float:
        """Distance from a lens to the nearest piece of course, in layout units."""
        best = 1e9
        for cx, cy, cz, radius in self.blockers:
            gap = math.sqrt(
                (cx - position[0]) ** 2 + (cy - position[1]) ** 2
                + (cz - position[2]) ** 2
            ) - radius
            if gap < best:
                best = gap
        return best

    def blocked(self, position: Sequence[float], target: Sequence[float],
                near: float = 2.6) -> bool:
        """Does the course stand between a lens and a point?

        Blockers within `near` of the target are skipped: the channel the racers
        are in is legitimately between the lens and them.
        """
        dx = target[0] - position[0]
        dy = target[1] - position[1]
        dz = target[2] - position[2]
        length2 = dx * dx + dy * dy + dz * dz
        if length2 < 1e-9:
            return False
        for cx, cy, cz, radius in self.blockers:
            gap = ((cx - target[0]) ** 2 + (cy - target[1]) ** 2
                   + (cz - target[2]) ** 2)
            if gap < (radius + near) ** 2:
                continue
            t = ((cx - position[0]) * dx + (cy - position[1]) * dy
                 + (cz - position[2]) * dz) / length2
            if t <= 0.0 or t >= 1.0:
                continue
            px = position[0] + dx * t
            py = position[1] + dy * t
            pz = position[2] + dz * t
            if (cx - px) ** 2 + (cy - py) ** 2 + (cz - pz) ** 2 < radius * radius:
                return True
        return False

    def offset(self, s: float, azimuth_deg: float, height: float,
               reach: float = RAIL_REACH) -> tuple[float, float, float]:
        """A lens `reach` out from the channel at a **world** azimuth.

        Zero degrees is +X and ninety is +Z; `height` is added along world up,
        not along the channel's banked up, because a camera is held level
        whatever the track is doing under it.
        """
        angle = math.radians(azimuth_deg)
        base = self.point_at(s)
        return (
            base[0] + math.cos(angle) * reach,
            base[1] + height,
            base[2] + math.sin(angle) * reach,
        )

    def describe(self) -> dict[str, Any]:
        return {
            "length": round(self.length, 3),
            "samples": len(self.points),
            "runs": list(self.run_span),
            "racing_length": round(self.racing_length, 3),
            "descent_per_z": round(self.descent, 4),
            "downhill_azimuth": round(self.downhill_azimuth, 2),
            "blockers": len(self.blockers),
        }


@dataclass
class Rail:
    """The solved standing-off azimuth and height, per spine sample."""

    arc: list[float]
    azimuth: list[float]
    height: list[float]
    clearance: list[float]
    seen: list[int]

    def at(self, s: float) -> tuple[float, float]:
        """`(world azimuth in degrees, height)` at arc length `s`."""
        if not self.arc:
            return (90.0, 6.0)
        if s <= self.arc[0]:
            return (self.azimuth[0], self.height[0])
        if s >= self.arc[-1]:
            return (self.azimuth[-1], self.height[-1])
        lo, hi = 0, len(self.arc) - 1
        while lo < hi - 1:
            mid = (lo + hi) // 2
            if self.arc[mid] <= s:
                lo = mid
            else:
                hi = mid
        span = self.arc[lo + 1] - self.arc[lo]
        t = 0.0 if span <= 1e-9 else (s - self.arc[lo]) / span
        # Azimuths are unwrapped by the solve, so a plain lerp is safe.
        return (
            self.azimuth[lo] * (1.0 - t) + self.azimuth[lo + 1] * t,
            self.height[lo] * (1.0 - t) + self.height[lo + 1] * t,
        )

    def describe(self) -> dict[str, Any]:
        turn = [
            abs(b - a) / max(sb - sa, 1e-6)
            for a, b, sa, sb in zip(self.azimuth, self.azimuth[1:], self.arc, self.arc[1:])
        ]
        return {
            "samples": len(self.arc),
            "azimuth_range": [round(min(self.azimuth), 1), round(max(self.azimuth), 1)],
            "height_range": [round(min(self.height), 2), round(max(self.height), 2)],
            "min_clearance": round(min(self.clearance), 3),
            "mean_clearance": round(sum(self.clearance) / len(self.clearance), 3),
            "sightlines_clear": round(
                sum(self.seen) / (len(self.seen) * len(RAIL_SIGHT)), 4
            ),
            "max_turn_per_unit": round(max(turn) if turn else 0.0, 3),
        }


def _measure(spine: Spine, s: float, azimuth: float, height: float, reach: float):
    position = spine.offset(s, azimuth, height, reach)
    clear = spine.clearance(position)
    seen = sum(
        1 for ahead in RAIL_SIGHT
        if not spine.blocked(position, spine.point_at(min(s + ahead, spine.length)))
    )
    return clear, seen


def _repair(spine: Spine, arc, azimuths, heights, reach, floor):
    """Lift the smoothed rail back out of anything the smoothing cut into.

    Smoothing a rail that was solved sample by sample shortens its corners, and
    on this course a shortened corner is a lens inside the leg above: the first
    smoothed rail came back with **-1.29 units of clearance** on `corr2`, a lens
    a layout unit inside `corr1`'s guard envelope, reported by a solve whose
    every raw sample had been clear. Raising it is the cheap repair and the
    right one - height is the axis this course is least crowded in.

    **Repairing and then smoothing does not work, and that is worth stating
    once**: the smoothing pass pulls the lifted samples straight back down, and
    the rail came out at 1.70 units against a 2.4 target with the repair
    apparently applied. So the two are interleaved and the *last* pass is a bare
    repair, which can leave a small step in the height programme rather than a
    lens inside the course. A sample that still cannot be cleared inside the
    lift budget stays in the report as a low clearance rather than being flown
    to the ceiling to hide it.
    """
    out = list(heights)

    def lift(values):
        raised = list(values)
        for index, (s, azimuth) in enumerate(zip(arc, azimuths)):
            height = raised[index]
            for _ in range(16):
                if spine.clearance(spine.offset(s, azimuth, height, reach)) >= floor:
                    break
                height += 0.4
            raised[index] = height
        return raised

    def soften(values, passes):
        out = list(values)
        for _ in range(passes):
            if len(out) < 3:
                break
            out = (
                [out[0]]
                + [0.25 * a + 0.5 * b + 0.25 * c
                   for a, b, c in zip(out, out[1:], out[2:])]
                + [out[-1]]
            )
        return out

    for _ in range(3):
        out = soften(lift(out), 6)
    return lift(out)


def camera_rail(
    spine: Spine,
    step: float = 2.0,
    reach: float = RAIL_REACH,
    clearance_target: float = RAIL_CLEARANCE,
    prefer: float | None = None,
) -> Rail:
    """Where a chase lens can actually stand, all the way down the course.

    A forward walk with a continuity penalty rather than an independent search
    per sample. The score at one candidate is

        clearance, capped at the target       how much clear air the lens has
        + 1.0 per clear sightline ahead       can it see the racers it chases
        - HEIGHT_COST per unit of height      stay low; see the constant
        - LEAN_COST per degree off downhill   hold the side the geometry gives
        - TURN_COST per degree moved          continuity in direction
        - LIFT_COST per unit of height moved  continuity in height

    and the walk keeps the best-scoring candidate at each step. Greedy rather
    than global, which is the right trade: the continuity penalty is what the
    shot needs, and a globally optimal rail that teleports once is worse than a
    locally optimal one that never does.

    `prefer` defaults to `spine.downhill_azimuth`. On the switchyard the solve
    then barely moves off it - which is the point. **The rail is one world
    direction and a height programme**, and the height is the part that has to
    work: holding the downhill azimuth and solving only the height clears the
    whole course at 2.4 units and keeps a sightline to the pack on 100% of
    samples at a six-unit trail, where the same azimuth at a *fixed* height of
    7.5 is short of clearance on a quarter of them.
    """
    if prefer is None:
        prefer = spine.downhill_azimuth
    candidates = [
        prefer + offset
        for offset in _frange(-RAIL_LEAN, RAIL_LEAN + 1e-6, RAIL_STEP)
    ]

    arc: list[float] = []
    azimuths: list[float] = []
    heights: list[float] = []

    previous: tuple[float, float] | None = None
    s = 0.0
    while s <= spine.length + 1e-6:
        best = None
        for azimuth in candidates:
            for height in RAIL_HEIGHTS:
                clear, seen = _measure(spine, s, azimuth, height, reach)
                if clear < 0.4:
                    continue
                score = (
                    min(clear, clearance_target)
                    + 1.0 * seen
                    - HEIGHT_COST * height
                    - LEAN_COST * abs(azimuth - prefer)
                )
                if previous is not None:
                    score -= TURN_COST * abs(azimuth - previous[0])
                    score -= LIFT_COST * abs(height - previous[1])
                if best is None or score > best[0]:
                    best = (score, azimuth, height)
        if best is None:
            # Nowhere clear at this sample: hold the previous answer rather than
            # invent one. It shows up in `describe` as a low clearance.
            azimuth, height = previous if previous is not None else (prefer, 6.0)
        else:
            _score, azimuth, height = best
        arc.append(s)
        azimuths.append(azimuth)
        heights.append(height)
        previous = (azimuth, height)
        s += step

    for _ in range(RAIL_SMOOTH):
        if len(azimuths) < 3:
            break
        azimuths = (
            [azimuths[0]]
            + [0.25 * a + 0.5 * b + 0.25 * c
               for a, b, c in zip(azimuths, azimuths[1:], azimuths[2:])]
            + [azimuths[-1]]
        )
        heights = (
            [heights[0]]
            + [0.25 * a + 0.5 * b + 0.25 * c
               for a, b, c in zip(heights, heights[1:], heights[2:])]
            + [heights[-1]]
        )
    heights = _repair(spine, arc, azimuths, heights, reach, clearance_target)

    # Re-measure what the flown rail achieves, not what the grid search chose.
    clears: list[float] = []
    seen_counts: list[int] = []
    for s, azimuth, height in zip(arc, azimuths, heights):
        clear, seen = _measure(spine, s, azimuth, height, reach)
        clears.append(clear)
        seen_counts.append(seen)
    return Rail(arc=arc, azimuth=azimuths, height=heights,
                clearance=clears, seen=seen_counts)


def _frange(start: float, stop: float, step: float) -> list[float]:
    out: list[float] = []
    value = start
    while value <= stop:
        out.append(value)
        value += step
    return out

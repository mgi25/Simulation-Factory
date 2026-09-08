"""The shared apron's eight guide centrelines, solved rather than authored.

## What this replaces, and why

V1.4 built the transport between the start shelf and the radial ring as eight
independently walled chutes, and `docs/sloped_race_v14_radial.md` section 3
records why that cannot be made to fit: a walled chute needs clear width over a
0.57 racer plus a wall each side, and eight of those cannot simultaneously
satisfy marble clearance, mutual separation, a grade above the stall threshold
and a grade below a fall, in the two units of plan available. Twenty-four
geometries in the taper/basin family and six in the chute family have been
falsified.

A ridge has no width requirement. So this builds **one continuous surface**
carrying eight guide grooves, and the binding lateral-spacing constraint goes
away with the walls.

## Why the guides are solved and not drawn

Four earlier attempts placed waypoints by rule and splined through them, and
every one of them failed the same way: **a rule puts a corner wherever it
clamps, and the corner is then reported as a curvature finding that belongs to
the rule rather than to the route.** Radii clamped to a clearance floor gave
0.03-unit curvature radii; a floor that stepped by one lane where an inner
route ended gave 0.26; a step from foreign-sector clearance to cup radius at a
sector boundary gave 0.31. In each case the same route, solved, holds one to
three units.

So each centreline is solved: smooth, project back into the feasible band,
repeat, innermost bay first so each route is constrained to lie outside the
ones already solved. Nesting is then true by construction rather than checked
afterwards. Two things that had to be learnt the hard way and are recorded in
the methods that carry them:

* **length must not be driven from inside the smoother.** A path can always
  buy length by looping, and a length-seeking term duly returned 47-unit routes
  for a six-unit problem.
* **separation must be a floor, not a push.** A pairwise push makes a route
  chase its neighbour round the ring; it put bay 0 into an 18.7-unit spiral
  and *reduced* the worst separation to 0.013. Read as a radius floor off the
  already-solved route at the same bearing, it is stable and it wastes no
  radius on a neighbour that has already turned in.

## Why the guide starts at the resting bay

Every earlier take solved the transport as a stage beginning at the shelf's
lip, and so had to force each route's entry tangent to match the heading the
shelf delivers, and had to equalise the *apron* lengths on their own - 2.2 to
6.8, a ratio of 2.8 that no meander closed, because the near cups sit in a
wedge between the lip line and the ring that is 0.15 units wide where they are.

Solved as one curve from the resting bay to the ring, there is no join to get
wrong, and the run every bay shares dilutes the difference: 3.9 to 8.1, a ratio
of 2.06. The drop is spread along the whole guide, so the grade band is
satisfied by a common descent profile rather than by equalising anything.

Everything here is in **layout units**, in the start module's own frame: +x
across, +z downhill, the drain at (0, `DISH_Z`).
"""

from __future__ import annotations

import math
from typing import Sequence

from sloped import layout

__all__ = ["ApronGuides", "bay_x"]

# Sim gravity expressed at layout scale, and the rolling factor for a solid
# sphere. Both only appear in the *reporting* of curvature margins - no
# geometry depends on them - but they are what makes "this bend is too tight"
# a measurement rather than an opinion.
GRAVITY = 245.25 * 0.57
ROLLING = 5.0 / 7.0


def bay_x(index: int) -> float:
    return (index - (layout.BAYS - 1) * 0.5) * layout.BAY_PITCH


def _wrap180(degrees: float) -> float:
    return (degrees + 180.0) % 360.0 - 180.0


def _smoothstep(value: float) -> float:
    t = max(0.0, min(1.0, value))
    return t * t * (3.0 - 2.0 * t)


def plan_length(points: Sequence[Sequence[float]]) -> float:
    return sum(math.dist(points[i], points[i + 1]) for i in range(len(points) - 1))


def _resample(points, count):
    """Uniform arc-length resampling. The solver needs even spacing."""
    total = plan_length(points)
    if total < 1e-9:
        return [tuple(p) for p in points]
    step = total / count
    out = [tuple(points[0])]
    run, index, target = 0.0, 0, step
    while index < len(points) - 1 and len(out) <= count:
        span = math.dist(points[index], points[index + 1])
        if run + span >= target - 1e-12 and span > 1e-12:
            t = (target - run) / span
            out.append((
                points[index][0] + (points[index + 1][0] - points[index][0]) * t,
                points[index][1] + (points[index + 1][1] - points[index][1]) * t,
            ))
            target += step
        else:
            run += span
            index += 1
    while len(out) < count + 1:
        out.append(tuple(points[-1]))
    out[-1] = tuple(points[-1])
    return out


def _cross_at(path, z: float, west: bool):
    """Where `path` crosses this z, interpolated between its samples.

    **Interpolated, not banded.** Taking the extreme x of every sample within
    0.20 of the z looks conservative and is not: on the fanning stretch the
    routes diverge steeply, so the band's extreme sample is 0.20 of z away and
    its x is already past where the route is *here*. Guides 1 and 2 passed
    within 0.465 against a 0.64 lane while the clamp reported itself satisfied.
    """
    best = None
    for index in range(len(path) - 1):
        low, high = path[index], path[index + 1]
        if (low[1] - z) * (high[1] - z) > 0.0:
            continue
        span = high[1] - low[1]
        t = 0.5 if abs(span) < 1e-9 else (z - low[1]) / span
        x = low[0] + (high[0] - low[0]) * t
        if best is None:
            best = x
        else:
            best = min(best, x) if west else max(best, x)
    return best


def curvature_radii(points, window: float = 0.30):
    """Radius of curvature over a fixed *arc* window, not a sample count.

    0.30 layout units is about half a marble. Finer than that and the number
    reports facet noise the marble itself bridges; coarser and it averages a
    real bend away. A sample-count window makes the answer depend on the
    sampling density, which is how the earlier takes came to compare routes of
    different lengths on different scales.
    """
    step = plan_length(points) / max(len(points) - 1, 1)
    skip = max(2, int(round(window / max(step, 1e-9))))
    out = [float("inf")] * len(points)
    for i in range(skip, len(points) - skip):
        a, b, c = points[i - skip], points[i], points[i + skip]
        ab, bc, ca = math.dist(a, b), math.dist(b, c), math.dist(c, a)
        area = abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])) * 0.5
        out[i] = float("inf") if area < 1e-12 else ab * bc * ca / (4.0 * area)
    return out


class ApronGuides:
    """Eight guide centrelines, from the resting line to the holding trough.

    Constructed once and cached; the solve is deterministic and takes about a
    second, and `RadialStart` holds one instance.
    """

    #: bearing bins for the nesting lookup - 0.5 degrees
    BINS = 720

    def __init__(
        self,
        field_z: float,
        rest_hold: float,
        dish_z: float,
        trough_r: float,
        trough_half: float,
        drop: float,
        lip_z: float,
        head_grade: float = 8.7,
        lane: float = 0.64,
        rib: float = 0.05,
        entry_arc: float = 46.0,
        lip_margin: float = 0.10,
        shelf_half: float = 3.40,
        samples: int = 150,
        iterations: int = 260,
    ) -> None:
        self.field_z = field_z
        self.rest_hold = rest_hold
        self.dish_z = dish_z
        self.trough_r = trough_r
        self.trough_half = trough_half
        self.drop = drop
        self.lip_z = lip_z
        self.head_grade = head_grade
        self.lane = lane
        self.rib = rib
        self.entry_arc = entry_arc
        self.lip_margin = lip_margin
        self.shelf_half = shelf_half
        self.samples = samples
        self.iterations = iterations
        # Outside this radius a centreline is clear of the trough's outer rim
        # by a marble, so a marble on it cannot drop in early.
        self.outer_r = trough_r + trough_half
        self.clear_r = self.outer_r + rib + layout.MARBLE_RADIUS
        self._paths: dict[int, list[tuple[float, float]]] | None = None
        self._lengths: dict[int, float] = {}

    # --- the ring ---------------------------------------------------------

    @staticmethod
    def slot(index: int) -> int:
        """Which of the eight ring bearings bay `index` delivers at.

        **A linear map from the resting line to the ring, and it comes out
        exact.** Take `v = (i - 3.5) / 3.5` and send it to `270 + 157.5 v`
        degrees; because `157.5 / 3.5` is 45, the eight bays land on
        22.5 + 45k with no rounding. The outer bays take the far bearings and
        the inner bays the near ones, which is the nesting order that keeps the
        routes from crossing: read outward, each route wraps further round the
        ring than the one inside it. The first V1.4 build had it backwards and
        every route had to cut across the ones outside it.
        """
        return (2, 3, 4, 5, 6, 7, 0, 1)[index]

    def bearing(self, index: int) -> float:
        return (22.5 + 45.0 * self.slot(index)) % 360.0

    def rest_point(self, index: int) -> tuple[float, float]:
        return (bay_x(index), self.field_z)

    def hold_point(self, index: int) -> tuple[float, float]:
        """A pin just past the gate: the field is abreast and straight there."""
        return (bay_x(index), self.field_z + self.rest_hold)

    def delivery(self, index: int) -> tuple[float, float]:
        return self._polar(self.outer_r, self.bearing(index))

    def _polar(self, radius: float, degrees: float) -> tuple[float, float]:
        angle = math.radians(degrees)
        return (radius * math.cos(angle), self.dish_z + radius * math.sin(angle))

    def _bearing_of(self, point) -> float:
        return math.degrees(math.atan2(point[1] - self.dish_z, point[0])) % 360.0

    def _radius_of(self, point) -> float:
        return math.hypot(point[0], point[1] - self.dish_z)

    def rest_bearing(self, index: int) -> float:
        return self._bearing_of(self.rest_point(index))

    def sweep(self, index: int) -> float:
        """Signed angular travel about the drain, the short way.

        The nesting order is by magnitude: bay 3 turns 19 degrees and bay 0
        turns 134, so read outward each route wraps further than the one
        inside it.
        """
        return _wrap180(self.bearing(index) - self.rest_bearing(index))

    # --- the feasible band -------------------------------------------------

    def floor_radius(self, index: int, degrees: float) -> float:
        """Smallest radius bay `index` may occupy at this bearing.

        A route must stay a marble clear of the trough's rim until it is close
        enough to its own delivery bearing to come in, or its marble drops into
        the trough at the wrong place and, worse, over a lip rather than down a
        grade. Eased over `entry_arc` because a step here is a ledge, and the
        solver turns a ledge into a corner: stepped, this constraint produced
        0.31-unit curvature radii at exactly the bearing it stepped at.
        """
        away = abs(_wrap180(degrees - self.bearing(index)))
        if away >= self.entry_arc:
            return self.clear_r
        t = _smoothstep((self.entry_arc - away) / self.entry_arc)
        return self.clear_r + (self.outer_r - self.clear_r) * t

    def _nesting_table(self, path) -> dict[int, float]:
        """A bearing -> outermost-radius table for one solved route."""
        table: dict[int, float] = {}
        for point in path:
            key = int(self._bearing_of(point) * self.BINS / 360.0) % self.BINS
            radius = self._radius_of(point)
            if radius > table.get(key, -1.0):
                table[key] = radius
        return table

    def _nesting_floor(self, degrees: float, tables) -> float:
        key = int(degrees * self.BINS / 360.0) % self.BINS
        best = 0.0
        for table in tables:
            for step in (-1, 0, 1):
                radius = table.get((key + step) % self.BINS)
                if radius is not None and radius > best:
                    best = radius
        return best + self.lane if best else 0.0

    def _project(self, index: int, point, tables) -> tuple[float, float]:
        x, z = point
        if z <= self.lip_z:
            # Still on the shelf: inside its width, never uphill of the line.
            return (max(-self.shelf_half, min(self.shelf_half, x)),
                    max(z, self.field_z))
        degrees = self._bearing_of(point)
        radius = self._radius_of(point)
        low = max(self.floor_radius(index, degrees),
                  self._nesting_floor(degrees, tables))
        # The apron cannot reach uphill of the shelf's lip line.
        sine = math.sin(math.radians(degrees))
        high = (float("inf") if sine >= -1e-9
                else (self.lip_z - self.dish_z) / sine - self.lip_margin)
        return self._polar(min(max(radius, low), max(high, low)), degrees)

    # --- the solve ---------------------------------------------------------

    def _seed(self, index: int):
        rest, hold = self.rest_point(index), self.hold_point(index)
        end = self.delivery(index)
        points = [rest, hold]
        for step in range(1, 13):
            t = step / 12.0
            points.append((hold[0] + (end[0] - hold[0]) * t,
                           hold[1] + (end[1] - hold[1]) * t))
        return _resample(points, self.samples)

    def _solve_one(self, index: int, inner):
        path = self._seed(index)
        count = self.samples
        tables = [self._nesting_table(other) for other in inner]
        west = bay_x(index) < 0.0
        for _ in range(self.iterations):
            moved = list(path)
            for k in range(1, count):
                moved[k] = (
                    0.5 * path[k][0] + 0.25 * (path[k - 1][0] + path[k + 1][0]),
                    0.5 * path[k][1] + 0.25 * (path[k - 1][1] + path[k + 1][1]),
                )
            for k in range(1, count):
                moved[k] = self._project(index, moved[k], tables)
            # On the shelf the routes are ordered in x, so separation there is
            # a one-dimensional clamp - against *every* inner route, not one of
            # them. Clamping against only the innermost left bays 1 and 2
            # passing within 0.42 while the report said the lane was 0.64.
            for other in inner:
                for k in range(1, count):
                    if moved[k][1] > self.lip_z:
                        continue
                    limit = _cross_at(other, moved[k][1], west)
                    if limit is None:
                        continue
                    if west:
                        moved[k] = (min(moved[k][0], limit - self.lane), moved[k][1])
                    else:
                        moved[k] = (max(moved[k][0], limit + self.lane), moved[k][1])
            # The visible start line, and only it, is pinned.
            moved[0] = self.rest_point(index)
            step = plan_length(path) / count
            for k in range(1, min(count, max(2, int(round(self.rest_hold / max(step, 1e-9)))) + 1)):
                moved[k] = (bay_x(index), moved[k][1])
            moved[count] = self.delivery(index)
            moved = [(x, max(z, self.field_z)) for x, z in moved]
            path = _resample(moved, count)
        return path

    def paths(self) -> dict[int, list[tuple[float, float]]]:
        if self._paths is not None:
            return self._paths
        west: dict[int, list] = {}
        done: list = []
        for index in (3, 2, 1, 0):
            west[index] = self._solve_one(index, list(done))
            done.append(west[index])
        out = dict(west)
        # The east four are the mirror of the west four, so the left-right half
        # of any bias is zero by construction rather than by measurement. The
        # ring below is rotationally symmetric, so a mirrored approach costs
        # nothing: see `sloped.radial`'s note on the holding trough.
        for index in (4, 5, 6, 7):
            out[index] = [(-x, z) for x, z in west[7 - index]]
        self._paths = out
        self._lengths = {i: plan_length(out[i]) for i in out}
        return out

    def length(self, index: int) -> float:
        self.paths()
        return self._lengths[index]

    # --- the descent -------------------------------------------------------

    def fall(self, index: int, fraction: float) -> float:
        """How far bay `index` has fallen at `fraction` along its guide.

        The grade starts at `head_grade` - the drawn shelf's own 8.7 degrees,
        so the visible stretch behaves like the shelf it is - and rises
        linearly along the guide until the total is `drop`. **Both endpoints
        are common: one pan height, one trough floor. So the total drop is
        identical for all eight bays whatever the shape**, exactly, and that is
        the property the fairness argument rests on.

        A profile ramping from *zero* slope, which is what this did first,
        leaves the first stretch at 0.2 degrees, and a marble released onto a
        0.2-degree floor does not move at all.
        """
        u = max(0.0, min(1.0, fraction))
        span = self.length(index)
        head = math.tan(math.radians(self.head_grade))
        gain = 2.0 * (self.drop - head * span) / max(span, 1e-9)
        return head * span * u + 0.5 * gain * span * u * u

    def grade_deg(self, index: int, fraction: float) -> float:
        span = self.length(index)
        head = math.tan(math.radians(self.head_grade))
        gain = 2.0 * (self.drop - head * span) / max(span, 1e-9)
        return math.degrees(math.atan(head + gain * max(0.0, min(1.0, fraction))))

    def speed_squared(self, index: int, fraction: float) -> float:
        return 2.0 * ROLLING * GRAVITY * self.fall(index, fraction)

    # --- measurement -------------------------------------------------------

    def table(self, groove_deg: float = 40.0) -> dict:
        """The per-bay guide report section 4 of the V1.4 brief asks for."""
        groove = math.tan(math.radians(groove_deg))
        paths = self.paths()
        rows = []
        for index in range(layout.BAYS):
            path = paths[index]
            span = self.length(index)
            radii = curvature_radii(path)
            run, worst, worst_at, bank = 0.0, float("inf"), 0.0, 0.0
            grades: list[float] = []
            for k in range(len(path)):
                if k:
                    run += math.dist(path[k - 1], path[k])
                    rise = self.fall(index, run / span) - self.fall(
                        index, (run - math.dist(path[k - 1], path[k])) / span)
                    step = math.dist(path[k - 1], path[k])
                    if step > 1e-9:
                        grades.append(math.degrees(math.atan(rise / step)))
                if radii[k] == float("inf"):
                    continue
                v2 = self.speed_squared(index, run / span)
                margin = radii[k] / max(v2 / (groove * GRAVITY), 1e-9)
                if margin < worst:
                    worst, worst_at = margin, run / span
                bank = max(bank, math.degrees(math.atan(v2 / (radii[k] * GRAVITY)))
                           - groove_deg)
            apron = [p for p in path if p[1] > self.lip_z]
            entry = path[3] if len(path) > 4 else path[-1]
            rows.append({
                "bay": index,
                "slot": self.slot(index),
                "bearing_deg": round(self.bearing(index), 4),
                "sweep_deg": round(self.sweep(index), 3),
                "length": round(span, 4),
                "apron_length": round(plan_length(apron) if len(apron) > 1 else 0.0, 4),
                "drop": round(self.drop, 6),
                "mean_grade_deg": round(math.degrees(math.atan(self.drop / span)), 3),
                "min_grade_deg": round(min(grades), 3),
                "max_grade_deg": round(max(grades), 3),
                "min_curve": round(min(r for r in radii if r != float("inf")), 4),
                "groove_margin": round(worst, 4),
                "margin_at": round(worst_at, 4),
                "bank_needed_deg": round(max(bank, 0.0), 2),
                "entry_tangent_deg": round(
                    math.degrees(math.atan2(entry[1] - path[0][1],
                                            entry[0] - path[0][0])) % 360.0, 2),
                "delivery_tangent_deg": round(
                    math.degrees(math.atan2(path[-1][1] - path[-4][1],
                                            path[-1][0] - path[-4][0])) % 360.0, 2),
                "delivery_radius": round(self._radius_of(path[-1]), 6),
                "speed_at_trough": round(math.sqrt(self.speed_squared(index, 1.0)), 3),
            })
        # Two separations, because they mean different things. A *running*
        # pinch is two lanes sharing one groove, with no room for a rib between
        # them, for as long as both routes are there. A *delivery* pinch is an
        # outer route passing close to where an inner route ends - and an
        # inner route's end is a place its marble occupies for a moment before
        # dropping into the trough, so the two racers may touch there and the
        # brief's section 6 permits exactly that. Reported apart, because
        # measured together the delivery pinch hides the running one.
        tail = max(3, int(0.09 * (self.samples + 1)))
        pair = (float("inf"), None)
        for a in range(layout.BAYS):
            for b in range(a + 1, layout.BAYS):
                gap = min(math.dist(u, v)
                          for u in paths[a][:-tail] for v in paths[b][:-tail])
                if gap < pair[0]:
                    pair = (gap, (a, b))
        delivery = (float("inf"), None)
        for a in range(layout.BAYS):
            for b in range(layout.BAYS):
                if a == b:
                    continue
                gap = min(math.dist(u, paths[b][-1]) for u in paths[a][:-tail])
                if gap < delivery[0]:
                    delivery = (gap, (a, b))
        early = float("inf")
        for index in range(layout.BAYS):
            for point in paths[index][:-1]:
                if point[1] <= self.lip_z:
                    continue
                away = abs(_wrap180(self._bearing_of(point) - self.bearing(index)))
                if away < 0.5 * self.entry_arc:
                    continue
                early = min(early, self._radius_of(point) - self.outer_r)
        lengths = [row["length"] for row in rows]
        drops = [row["drop"] for row in rows]
        radii_out = [row["delivery_radius"] for row in rows]
        return {
            "rows": rows,
            "length": [round(min(lengths), 4), round(max(lengths), 4)],
            "length_spread": round(max(lengths) - min(lengths), 4),
            "length_ratio": round(max(lengths) / min(lengths), 4),
            "drop_spread": round(max(drops) - min(drops), 9),
            "delivery_radius_spread": round(max(radii_out) - min(radii_out), 9),
            "grade": [round(min(r["min_grade_deg"] for r in rows), 3),
                      round(max(r["max_grade_deg"] for r in rows), 3)],
            "mean_grade": [round(min(r["mean_grade_deg"] for r in rows), 3),
                           round(max(r["mean_grade_deg"] for r in rows), 3)],
            "groove_margin": round(min(r["groove_margin"] for r in rows), 4),
            "bank_needed_deg": round(max(r["bank_needed_deg"] for r in rows), 2),
            "worst_lane_pair": [list(pair[1]), round(pair[0], 4)],
            "worst_delivery_gap": [list(delivery[1]), round(delivery[0], 4)],
            "lane": round(self.lane, 4),
            "trough_rim_slack": round(early, 4) if early != float("inf") else None,
            "apron_width": round(2.0 * max(abs(p[0]) for path in paths.values()
                                           for p in path), 4),
        }

"""What stands between a lens and the racers, in layout units.

`sloped.cameras` already checks the *mountain*: `terrain.clearance` walks the
sight line and raises the elevation until the ground is out of it. It has never
checked the **course**, and V18's finish shot is what that costs. Its camera was
placed twenty units behind the leading pair at twelve degrees of elevation, and
twenty units behind this finish line is not open air - the course doubles back
through there - so the lens ended up 0.15 layout units off `orange`'s channel
shell with the track body filling the frame from 16.9 s to the end. Every check
the pipeline had passed: the aim followed the field, the ground was clear, and
`frame_report` counted the racers inside the frustum. `frame_report` says so
itself - *it cannot see occlusion*.

So this module answers the two questions none of them asks:

* **Where is the camera standing?** `Bundle.nearest` is the distance from a
  point to the nearest surface of the drawn course.
* **Can it see the racer?** `Bundle.first_hit` is the first surface a segment
  meets, so a ray from the lens to a marble's centre - stopped a radius short -
  names the guard rail that is in the way.

## What counts as the course

The colliders are not enough. A collider is what the physics can touch, and a
camera is stopped by what is *drawn*: the FINISH gantry the racers pass under
carries no collider at all, and neither do the deck's rim, its corner pylons or
the piers under every run. Those are modelled here from the same constants
`course_finish.gd` and `course_machine.gd` build them from, which is a mirror
and is admitted as one - the alternative is to ask Godot, and a check that needs
a renderer running cannot be a test.

The channel shells are not mirrored. They come from `TrackRun.section_at` and
`track.ring_points`, which is the expression `local_colliders` sweeps and the
same one `v2_forms.banked_sweep` draws, so the guard rail this module tests
against is the rail on screen.

Everything here is in **layout units**, because that is what a camera track is
in. The module colliders are the one thing that arrives in simulation units and
they are converted on the way in.
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

from sloped import layout
from sloped.scale import SIM_TO_LAYOUT
from sloped.track import TrackRun, ring_points

__all__ = ["Bundle", "course_solids", "shot_report", "check_shot"]

Vec3 = tuple[float, float, float]
Tri = tuple[Vec3, Vec3, Vec3]

# Triangles per leaf box. Sixty-four is about two rings of a channel section,
# which is the grain the geometry already has.
CHUNK = 64

# `course_machine.gd`'s own support constants.
SUPPORT_SPACING = 7.4
KEEL_DROP = 0.98


# --- the solids -----------------------------------------------------------


def _box(centre: Vec3, half: Vec3, frame: Sequence[Vec3]) -> list[Tri]:
    """An oriented box as twelve triangles. `frame` is (across, up, along)."""
    across, up, along = frame
    corners = []
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            for sz in (-1.0, 1.0):
                corners.append(
                    tuple(
                        centre[axis]
                        + across[axis] * sx * half[0]
                        + up[axis] * sy * half[1]
                        + along[axis] * sz * half[2]
                        for axis in range(3)
                    )
                )
    # A corner's index is its (x, y, z) signs packed as bits, so each face is
    # four of them taken in order round the rectangle.
    faces = (
        (0, 1, 3, 2), (4, 6, 7, 5),
        (0, 4, 5, 1), (2, 3, 7, 6),
        (0, 2, 6, 4), (1, 5, 7, 3),
    )
    out: list[Tri] = []
    for a, b, c, d in faces:
        out.append((corners[a], corners[b], corners[c]))
        out.append((corners[a], corners[c], corners[d]))
    return out


def _shell(run: TrackRun) -> list[Tri]:
    """One run's channel, swept exactly as its collider and its mesh are."""
    rings = [
        ring_points(run.path[index], run.frames[index], run.section_at(index), run.widths[index])
        for index in range(len(run.path))
    ]
    out: list[Tri] = []
    count = len(rings[0])
    for index in range(len(rings) - 1):
        near, far = rings[index], rings[index + 1]
        for point in range(count - 1):
            out.append((near[point], near[point + 1], far[point + 1]))
            out.append((near[point], far[point + 1], far[point]))
    return out


def _piers(run: TrackRun, ground) -> list[Tri]:
    """`course_machine._supports`, as the box each pier stands in.

    Not the Y-frame's own stem and arms: a camera inside the box a pier occupies
    is too close to the course whichever member it would have met, and the shape
    of the ironwork is not worth mirroring to say so.
    """
    count = max(int(round(run.arc[-1] / SUPPORT_SPACING)), 2)
    upright = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    out: list[Tri] = []
    for step in range(1, count):
        index = min(max(int(round(step / count * (len(run.path) - 1))), 0), len(run.path) - 1)
        centre = run.path[index]
        keel = centre[1] - KEEL_DROP * run.scale
        floor = ground(centre[0], centre[2])
        if keel <= floor:
            continue
        out.extend(
            _box(
                (centre[0], 0.5 * (keel + floor), centre[2]),
                (1.05 * run.scale, 0.5 * (keel - floor), 0.75 * run.scale),
                upright,
            )
        )
    return out


def _finish_furniture(deck) -> list[tuple[str, list[Tri]]]:
    """The arena's drawn structure, which has no collider and still stops a lens.

    Mirrors `course_finish.gd`: the deck's local frame has +Z along the direction
    of travel and +X across it, the origin is the deck's centre at floor level,
    and every position below is that file's own.

    `course_machine.gd` takes the deck's yaw one sample earlier than
    `stations.FinishDeck` does - `_yaw_at(final_run, size - 2)` against
    `heading_deg(size - 1)` - which is 0.085 degrees apart on this course, seven
    centimetres at the gantry. Recorded rather than reconciled.
    """
    origin = layout.NODES["finish"]
    across, up, along = deck.frame

    def world(local: Vec3) -> Vec3:
        return tuple(
            origin[axis] + across[axis] * local[0] + up[axis] * local[1] + along[axis] * local[2]
            for axis in range(3)
        )

    frame = (across, up, along)
    depth, width, rim = deck.DECK_DEPTH, deck.DECK_WIDTH, deck.RIM
    groups: list[tuple[str, list[Tri]]] = []

    gantry: list[Tri] = []
    for side in (1.0, -1.0):
        gantry.extend(
            _box(world((side * 3.80, 1.55, -0.5 * depth + 0.90)), (0.22, 1.65, 0.26), frame)
        )
    gantry.extend(_box(world((0.0, 3.10, -0.5 * depth + 0.90)), (4.25, 0.21, 0.30), frame))
    # The sign leans back nine degrees. Modelled upright and a little deeper
    # instead: a camera the lean would let past is a camera its frame does not.
    gantry.extend(_box(world((0.0, 3.90, -0.5 * depth + 0.86)), (2.70, 0.64, 0.24), frame))
    groups.append(("finish:gantry", gantry))

    rail: list[Tri] = []
    for local, half in (
        ((0.0, 0.5 * rim, 0.5 * depth - 0.24), (0.5 * (width - 0.5), 0.5 * rim, 0.28)),
        ((-0.5 * width + 0.24, 0.5 * rim, 0.0), (0.28, 0.5 * rim, 0.5 * (depth - 0.5))),
        ((0.5 * width - 0.24, 0.5 * rim, 0.0), (0.28, 0.5 * rim, 0.5 * (depth - 0.5))),
    ):
        rail.extend(_box(world(local), half, frame))
    groups.append(("finish:rim", rail))

    furniture: list[Tri] = []
    for sx in (-1.0, 1.0):
        for sz in (-1.0, 1.0):
            furniture.extend(
                _box(
                    world((sx * (0.5 * width - 0.30), 0.95, sz * (0.5 * depth - 0.30))),
                    (0.23, 0.95, 0.23),
                    frame,
                )
            )
    furniture.extend(
        _box(world((0.0, 0.44, 4.32)), (0.5 * (8 * 1.32 + 0.40), 0.65, 0.17), frame)
    )
    furniture.extend(_box(world((0.0, 0.31, 2.60)), (0.5 * 8 * 1.32, 0.31, 1.50), frame))
    groups.append(("finish:furniture", furniture))
    return groups


def course_solids(machine, ground=None) -> list[tuple[str, list[Tri]]]:
    """Every drawn surface a camera can be stopped by, labelled, in layout units.

    `ground` is a height function; given one, each run also contributes the
    boxes its piers stand in. Without one the piers are left out, which is the
    right default for a sight line that never goes under a channel and the wrong
    one for asking where a camera may stand.
    """
    solids: list[tuple[str, list[Tri]]] = []
    for name, module in machine.modules.items():
        if isinstance(module, TrackRun):
            solids.append((name, _shell(module)))
            if ground is not None:
                pier = _piers(module, ground)
                if pier:
                    solids.append((f"{name}:piers", pier))
            continue
        if name == "finish":
            solids.extend(_finish_furniture(module))
        triangles: list[Tri] = []
        for mesh in module.local_colliders():
            points = [tuple(value * SIM_TO_LAYOUT for value in vertex) for vertex in mesh.vertices]
            indices = mesh.indices
            for at in range(0, len(indices), 3):
                triangles.append(
                    (points[indices[at]], points[indices[at + 1]], points[indices[at + 2]])
                )
        if triangles:
            solids.append((name, triangles))
    return solids


# --- queries --------------------------------------------------------------


class Bundle:
    """Labelled triangles in leaf boxes, for ray and distance queries.

    A flat scan is sixty thousand triangles a ray and the finish shot asks for
    seven rays a frame over two hundred frames. Grouping consecutive triangles -
    which are consecutive *rings* of a channel, and therefore already near each
    other - into boxes of sixty-four turns that into a few hundred box tests.
    """

    __slots__ = ("leaves",)

    def __init__(self, solids: Iterable[tuple[str, list[Tri]]]) -> None:
        self.leaves: list[tuple[str, Vec3, Vec3, list[Tri]]] = []
        for label, triangles in solids:
            for at in range(0, len(triangles), CHUNK):
                chunk = triangles[at : at + CHUNK]
                lower = tuple(
                    min(point[axis] for tri in chunk for point in tri) for axis in range(3)
                )
                upper = tuple(
                    max(point[axis] for tri in chunk for point in tri) for axis in range(3)
                )
                self.leaves.append((label, lower, upper, chunk))

    # -- rays --

    @staticmethod
    def _hits_box(origin, inverse, span, lower, upper) -> bool:
        near, far = 0.0, span
        for axis in range(3):
            low = (lower[axis] - origin[axis]) * inverse[axis]
            high = (upper[axis] - origin[axis]) * inverse[axis]
            if low > high:
                low, high = high, low
            near = max(near, low)
            far = min(far, high)
            if near > far:
                return False
        return True

    @staticmethod
    def _hits_tri(origin, direction, span, tri):
        """Moeller-Trumbore, both faces, within (0, span)."""
        a, b, c = tri
        e1 = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        e2 = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        p = (
            direction[1] * e2[2] - direction[2] * e2[1],
            direction[2] * e2[0] - direction[0] * e2[2],
            direction[0] * e2[1] - direction[1] * e2[0],
        )
        det = e1[0] * p[0] + e1[1] * p[1] + e1[2] * p[2]
        if -1e-12 < det < 1e-12:
            return None
        inverse = 1.0 / det
        s = (origin[0] - a[0], origin[1] - a[1], origin[2] - a[2])
        u = (s[0] * p[0] + s[1] * p[1] + s[2] * p[2]) * inverse
        if u < -1e-9 or u > 1.0 + 1e-9:
            return None
        q = (
            s[1] * e1[2] - s[2] * e1[1],
            s[2] * e1[0] - s[0] * e1[2],
            s[0] * e1[1] - s[1] * e1[0],
        )
        v = (direction[0] * q[0] + direction[1] * q[1] + direction[2] * q[2]) * inverse
        if v < -1e-9 or u + v > 1.0 + 1e-9:
            return None
        at = (e2[0] * q[0] + e2[1] * q[1] + e2[2] * q[2]) * inverse
        if at <= 1e-6 or at >= span:
            return None
        return at

    def first_hit(self, origin, target, shorten: float = 0.0):
        """The first surface between `origin` and `target` as `(distance, label)`.

        `shorten` pulls the far end back, which is how a ray at a marble stops at
        the marble's own skin rather than at the cradle it is sitting in.
        """
        delta = [target[axis] - origin[axis] for axis in range(3)]
        reach = math.sqrt(sum(value * value for value in delta))
        span = reach - shorten
        if span <= 1e-6:
            return None
        direction = tuple(value / reach for value in delta)
        inverse = tuple(
            1.0 / value if abs(value) > 1e-12 else math.inf for value in direction
        )
        best = None
        limit = span
        for label, lower, upper, chunk in self.leaves:
            if not self._hits_box(origin, inverse, limit, lower, upper):
                continue
            for tri in chunk:
                at = self._hits_tri(origin, direction, limit, tri)
                if at is not None:
                    best = (at, label)
                    limit = at
        return best

    # -- distance --

    @staticmethod
    def _box_distance(point, lower, upper) -> float:
        out = 0.0
        for axis in range(3):
            gap = max(lower[axis] - point[axis], 0.0, point[axis] - upper[axis])
            out += gap * gap
        return math.sqrt(out)

    @staticmethod
    def _tri_distance2(point, tri) -> float:
        """Squared distance to a triangle: Ericson's region test, transcribed."""
        a, b, c = tri
        ab = [b[i] - a[i] for i in range(3)]
        ac = [c[i] - a[i] for i in range(3)]
        ap = [point[i] - a[i] for i in range(3)]
        d1 = sum(ab[i] * ap[i] for i in range(3))
        d2 = sum(ac[i] * ap[i] for i in range(3))
        if d1 <= 0.0 and d2 <= 0.0:
            return sum(value * value for value in ap)
        bp = [point[i] - b[i] for i in range(3)]
        d3 = sum(ab[i] * bp[i] for i in range(3))
        d4 = sum(ac[i] * bp[i] for i in range(3))
        if d3 >= 0.0 and d4 <= d3:
            return sum(value * value for value in bp)
        vc = d1 * d4 - d3 * d2
        if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
            v = d1 / max(d1 - d3, 1e-12)
            return sum((ap[i] - v * ab[i]) ** 2 for i in range(3))
        cp = [point[i] - c[i] for i in range(3)]
        d5 = sum(ab[i] * cp[i] for i in range(3))
        d6 = sum(ac[i] * cp[i] for i in range(3))
        if d6 >= 0.0 and d5 <= d6:
            return sum(value * value for value in cp)
        vb = d5 * d2 - d1 * d6
        if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
            w = d2 / max(d2 - d6, 1e-12)
            return sum((ap[i] - w * ac[i]) ** 2 for i in range(3))
        va = d3 * d6 - d5 * d4
        if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
            w = (d4 - d3) / max((d4 - d3) + (d5 - d6), 1e-12)
            return sum((bp[i] - w * (c[i] - b[i])) ** 2 for i in range(3))
        total = 1.0 / max(va + vb + vc, 1e-12)
        v = vb * total
        w = vc * total
        return sum((ap[i] - v * ab[i] - w * ac[i]) ** 2 for i in range(3))

    def nearest(self, point, cutoff: float = 40.0) -> tuple[float, str]:
        """Distance to the nearest surface, and what it belongs to.

        `cutoff` is both a speed limit and the answer returned when nothing is
        within it, so a camera standing in open air reports the cutoff rather
        than an infinity that no comparison can use.
        """
        best, name = cutoff, ""
        for label, lower, upper, chunk in self.leaves:
            if self._box_distance(point, lower, upper) >= best:
                continue
            for tri in chunk:
                gap = self._tri_distance2(point, tri)
                if gap < best * best:
                    best, name = math.sqrt(gap), label
        return best, name


# --- the check ------------------------------------------------------------
#
# Deliberately not a general camera framework. It answers the three questions
# V18's finish got wrong and no others: is the lens standing clear of the
# course, is the middle of the frame obstructed, and can the camera see the
# racers nearest the line. Every other cut on this course is checked by eye and
# by `frame_report` as it always was.

# How close the lens may come to any drawn surface. Two layout units is three
# and a half marble diameters - far enough that no rail can be across the near
# plane, and loose enough that a shot standing on the deck is not rejected for
# it. V18's finish came to 0.15.
LENS_CLEARANCE = 2.0

# How long the next racer to cross may be out of sight before it is a fault, in
# seconds.
#
# **Not "never", and the reason is the difference between a foreground and an
# obstruction.** V19's lens loses the fourth and fifth placed marbles behind the
# FINISH sign for 0.12 s, two tenths *before* they cross, and they come out from
# behind it at 81 px and dead-heat in clear view. That is a post in the
# foreground, which is how an arena is built and how it should photograph. V18
# lost its subject behind `orange`'s channel for 2.15 s and never got it back.
# A third of a second separates the two and nothing in between is a shot worth
# defending.
BLIND_SECONDS = 0.34


def _racers(replay, index) -> dict[int, Vec3]:
    scale = float(replay.get("units", {}).get("render_scale", SIM_TO_LAYOUT))
    return {
        int(sample["id"]): tuple(float(sample["p"][axis]) * scale for axis in range(3))
        for sample in replay["frames"][index]["marbles"]
    }


def _next_to_cross(replay: dict) -> list[tuple[float, int]]:
    """Each finish crossing as `(time, marble)`, in order."""
    return sorted(
        (float(event["t"]), int(event["id"]))
        for event in replay.get("events", ())
        if event["kind"] == "finish_line"
    )


def shot_report(
    track: dict,
    replay: dict,
    machine,
    bundle: "Bundle | None" = None,
    cut: str = "finish",
    stride: int = 6,
) -> list[dict]:
    """Per sampled frame of one cut: where the lens stands and what it can see.

    `stride` is in track rows, which are at the replay rate, so the default of
    six is a tenth of a second - fine enough to catch a rail crossing the frame
    and coarse enough to run in a test.

    The **subject** is the next racer to cross the line, which is the one thing
    a finish camera is obliged to be able to see. Not the nearest racer of all:
    the nearest is very often one that has already crossed and rolled into a
    catch lane behind the backboard, and a shot is not at fault for that.
    """
    from sloped import terrain

    records = [row for row in track["cuts"] if row["name"] == cut]
    if not records:
        return []
    if bundle is None:
        cfg = terrain.terrain_config(machine.runs)
        bundle = Bundle(
            course_solids(machine, lambda x, z: terrain.height(x, z, cfg))
        )
    radius = float(replay.get("units", {}).get("layout_marble_radius", layout.MARBLE_RADIUS))
    times = [float(frame["t"]) for frame in replay["frames"]]
    crossings = _next_to_cross(replay)

    out: list[dict] = []
    for record in records:
        for row in record["frames"][::stride]:
            when = float(row[0])
            camera = (row[1], row[2], row[3])
            aim = (row[4], row[5], row[6])
            index = min(range(len(times)), key=lambda k: abs(times[k] - when))
            racers = _racers(replay, index)
            subject = next((who for at, who in crossings if at >= when), None)
            blocker = None
            if subject is not None and subject in racers:
                blocker = bundle.first_hit(camera, racers[subject], shorten=radius)
            gap, what = bundle.nearest(camera)
            centre = bundle.first_hit(camera, aim)
            out.append(
                {
                    "cut": cut,
                    "t": round(when, 3),
                    "clearance": round(gap, 3),
                    "nearest": what,
                    "centre": None if centre is None else (round(centre[0], 3), centre[1]),
                    "subject": subject,
                    "subject_blocked": None if blocker is None else blocker[1],
                }
            )
    return out


def check_shot(
    track: dict,
    replay: dict,
    machine,
    bundle: "Bundle | None" = None,
    cut: str = "finish",
    stride: int = 6,
) -> list[str]:
    """What `shot_report` found that would be a presentation failure.

    Three faults and no others: a lens standing in the course, a frame whose
    middle is obstructed, and losing the next racer to cross for longer than a
    third of a second at a stretch.
    """
    rows = shot_report(track, replay, machine, bundle, cut, stride)
    if not rows:
        return []
    problems: list[str] = []
    worst = min(rows, key=lambda row: row["clearance"])
    if worst["clearance"] < LENS_CLEARANCE:
        problems.append(
            f"{cut} at {worst['t']:.2f}s: the lens is {worst['clearance']:.2f} layout "
            f"units from {worst['nearest']}, inside the {LENS_CLEARANCE:.1f} it needs"
        )
    blocked = [row for row in rows if row["centre"] is not None]
    if blocked:
        first = blocked[0]
        problems.append(
            f"{cut}: the centre of the frame is blocked in {len(blocked)} of "
            f"{len(rows)} sampled frames, first at {first['t']:.2f}s by "
            f"{first['centre'][1]} {first['centre'][0]:.2f} units from the lens"
        )
    # The longest unbroken spell with the next racer to cross out of sight.
    step = stride / max(float(track.get("fps", 60.0)), 1.0)
    run = 0
    longest = 0
    at = 0.0
    behind = ""
    for row in rows:
        if row["subject_blocked"] is None:
            run = 0
            continue
        run += 1
        if run > longest:
            longest, at, behind = run, row["t"], row["subject_blocked"]
    if longest * step > BLIND_SECONDS:
        problems.append(
            f"{cut}: the next racer to cross is behind {behind} for "
            f"{longest * step:.2f} s at a stretch, ending {at:.2f}s"
        )
    return problems

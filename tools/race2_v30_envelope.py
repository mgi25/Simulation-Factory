"""V30: what camera A can actually see, measured before anything is built.

Usage:

    python tools/race2_v30_envelope.py                    # the whole report
    python tools/race2_v30_envelope.py --json=<path>      # and write it out

**This is the design instrument for the whole pass, and it exists because V29
built a room without one.** V29's hall is an annulus with an 88-unit hole in
the middle and a course whose plan reach is 27.06; the centre ray fell through
the hole on 100% of frames and the final sprint came out 90.8% black. Nothing
about that needed a render to predict. It needed one question asked of the
camera track before a wall went anywhere: *where do this lens's rays go?*

So this tool reads the locked camera A track and the locked course geometry,
and answers, in layout units and without opening Godot:

    footprint       the course's own plan and section bounds
    envelope        where every frustum ray lands on a horizontal plane
    floor demand    the plan region a floor has to cover to stop the void
    wall band       the height range a standing wall is seen in
    near shell      how close geometry may come without crossing the lens
    parallax        the distance strata a form has to sit in to move

It changes no camera, no course and no physics: it opens two JSON files and
does arithmetic.

## The one number that matters

`floor_demand` is the plan radius, from the course's own plan centre, inside
which a horizontal surface is hit by the *centre* ray on every sampled frame.
A floor smaller than that is a hole in the middle of the picture. V29's deck
starts at 88.0 and this tool says the demand is a fraction of that, which is
the failure restated as a constraint a builder can satisfy.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TRACK = "output/race2/v281_camera/A/race2_switchyard_8.cameras.json"
GEOMETRY = "output/race2/v281_camera/A/race2_switchyard_8.geometry.json"

# 1080x1920: the delivery. The frustum is solved from the vertical field of
# view the track carries, so the aspect is needed to get the horizontal one.
FRAME_W = 1080
FRAME_H = 1920


# --- reading ---------------------------------------------------------------


def load_track(path: str) -> dict:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def load_course(path: str) -> dict:
    """The course in layout units - the frame the camera track is written in.

    `render_scale` is the factor between simulation units, which is what the
    geometry file carries, and layout units, which is what the scene parents
    the course under and therefore what the camera positions mean. Applying it
    here is the same multiplication `race2_scene._centreline` does.
    """
    with open(path, encoding="utf-8") as handle:
        raw = json.load(handle)
    scale = float(raw.get("units", {}).get("render_scale", 0.57))

    line: list[tuple[float, float, float]] = []
    for run in raw.get("runs", []):
        for point in run.get("path", []):
            line.append((point[0] * scale, point[1] * scale, point[2] * scale))

    modules: dict[str, dict] = {}
    for module in raw.get("modules", []):
        lo = [math.inf] * 3
        hi = [-math.inf] * 3
        for mesh in module.get("meshes", []):
            flat = mesh.get("v", [])
            for index in range(0, len(flat) - 2, 3):
                for axis in range(3):
                    value = flat[index + axis] * scale
                    lo[axis] = min(lo[axis], value)
                    hi[axis] = max(hi[axis], value)
        if lo[0] < math.inf:
            modules[str(module.get("id", ""))] = {
                "centre": [(lo[a] + hi[a]) * 0.5 for a in range(3)],
                "min": lo,
                "max": hi,
            }
    return {"line": line, "modules": modules, "scale": scale}


# --- the course's own size -------------------------------------------------


def footprint(course: dict) -> dict:
    """Plan bounds, section bounds, and the plan reach from the plan centre.

    The reach is the number V29 compared its radii against and got 27.06 for.
    It is recomputed here rather than quoted, because a stage sized off a
    quoted number is a stage sized off a document.
    """
    line = course["line"]
    xs = [p[0] for p in line]
    ys = [p[1] for p in line]
    zs = [p[2] for p in line]
    centre = ((min(xs) + max(xs)) * 0.5, (min(zs) + max(zs)) * 0.5)
    reach = max(math.hypot(p[0] - centre[0], p[2] - centre[1]) for p in line)
    return {
        "centre": [centre[0], centre[1]],
        "x": [min(xs), max(xs)],
        "y": [min(ys), max(ys)],
        "z": [min(zs), max(zs)],
        "span_x": max(xs) - min(xs),
        "span_z": max(zs) - min(zs),
        "span_y": max(ys) - min(ys),
        "plan_reach": reach,
        "samples": len(line),
    }


# --- the frustum -----------------------------------------------------------


def _norm(v):
    length = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if length <= 1e-9:
        return (0.0, 0.0, 1.0)
    return (v[0] / length, v[1] / length, v[2] / length)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def corners(eye, aim, fov_y_deg, aspect):
    """The four corner rays of the frustum, as unit vectors.

    Godot's `Camera3D.fov` is the vertical field of view when `keep_aspect` is
    the default height-keeping one, which is what `race2_scene` leaves it at.
    A 1080x1920 frame is taller than it is wide, so the horizontal half-angle
    is the *smaller* of the two - which is why the void in V29 filled from the
    bottom rather than the sides.
    """
    forward = _norm((aim[0] - eye[0], aim[1] - eye[1], aim[2] - eye[2]))
    world_up = (0.0, 1.0, 0.0)
    if abs(forward[1]) > 0.999:
        world_up = (0.0, 0.0, 1.0)
    right = _norm(_cross(forward, world_up))
    up = _norm(_cross(right, forward))
    half_y = math.tan(math.radians(fov_y_deg) * 0.5)
    half_x = half_y * aspect
    out = []
    for sx, sy in ((-1, 1), (1, 1), (-1, -1), (1, -1)):
        ray = (forward[0] + right[0] * half_x * sx + up[0] * half_y * sy,
               forward[1] + right[1] * half_x * sx + up[1] * half_y * sy,
               forward[2] + right[2] * half_x * sx + up[2] * half_y * sy)
        out.append(_norm(ray))
    return forward, right, up, out


def plane_hit(eye, ray, plane_y, far=4000.0):
    """Where a ray meets a horizontal plane, or None if it never does.

    `None` is the whole finding of V29 restated: a ray that never meets the
    floor plane is a ray that renders whatever stands beyond the room, and if
    nothing stands there it renders the clear colour, which is black.
    """
    if ray[1] >= -1e-6:
        return None
    t = (plane_y - eye[1]) / ray[1]
    if t <= 0.0 or t > far:
        return None
    return (eye[0] + ray[0] * t, plane_y, eye[2] + ray[2] * t, t)


# --- the walk --------------------------------------------------------------


def frames(track: dict, every: int = 1):
    """Every sampled frame of the film, in order, as flat records."""
    out = []
    for cut in track.get("cuts", []):
        rows = cut.get("frames", [])
        for index in range(0, len(rows), every):
            row = rows[index]
            out.append({
                "shot": str(cut.get("name", "?")),
                "mode": str(cut.get("mode", "")),
                "t": float(row[0]),
                "eye": (float(row[1]), float(row[2]), float(row[3])),
                "aim": (float(row[4]), float(row[5]), float(row[6])),
                "fov": float(row[7]),
            })
    out.sort(key=lambda r: r["t"])
    return out


def envelope(track: dict, course: dict, floor_y: float, every: int = 1) -> dict:
    """The aggregate: where the rays of this film go.

    Measured against a horizontal plane at `floor_y`, which is the height the
    scene's own seam puts a stage floor at - two units under the lowest point
    of the racing line. The answers are in plan radius from the course's own
    plan centre, because that is the frame every ring-shaped form in
    `environment_stage.gd` is authored in.
    """
    plan = footprint(course)
    cx, cz = plan["centre"]
    aspect = FRAME_W / FRAME_H

    rows = frames(track, every)
    per_shot: dict[str, dict] = {}
    centre_radii = []
    corner_radii = []
    misses = 0
    near_hits = []
    frame_top_elev = []
    aim_elev = []
    eye_y = []
    eye_r = []
    reach_far = []

    for record in rows:
        eye, aim = record["eye"], record["aim"]
        forward, _right, _up, rays = corners(eye, aim, record["fov"], aspect)
        aim_elev.append(math.degrees(math.asin(max(-1.0, min(1.0, forward[1])))))
        tops = [math.degrees(math.asin(max(-1.0, min(1.0, r[1])))) for r in rays]
        frame_top_elev.append(max(tops))
        eye_y.append(eye[1])
        eye_r.append(math.hypot(eye[0] - cx, eye[2] - cz))

        hit = plane_hit(eye, forward, floor_y)
        if hit is None:
            misses += 1
            centre_r = math.inf
        else:
            centre_r = math.hypot(hit[0] - cx, hit[2] - cz)
            centre_radii.append(centre_r)

        frame_corner = []
        frame_miss = 0
        for ray in rays:
            spot = plane_hit(eye, ray, floor_y)
            if spot is None:
                frame_miss += 1
                continue
            frame_corner.append((math.hypot(spot[0] - cx, spot[2] - cz),
                                 spot[3]))
        if frame_corner:
            corner_radii.extend(r for r, _d in frame_corner)
            near_hits.append(min(d for _r, d in frame_corner))
            reach_far.append(max(r for r, _d in frame_corner))

        bucket = per_shot.setdefault(record["shot"], {
            "frames": 0, "centre_r": [], "corner_r": [], "near": [],
            "escapes": 0, "corner_escapes": 0, "eye_y": [], "top_elev": [],
            "t": [math.inf, -math.inf],
        })
        bucket["frames"] += 1
        bucket["eye_y"].append(eye[1])
        bucket["top_elev"].append(max(tops))
        bucket["t"][0] = min(bucket["t"][0], record["t"])
        bucket["t"][1] = max(bucket["t"][1], record["t"])
        if centre_r is math.inf:
            bucket["escapes"] += 1
        else:
            bucket["centre_r"].append(centre_r)
        bucket["corner_escapes"] += frame_miss
        if frame_corner:
            bucket["corner_r"].extend(r for r, _d in frame_corner)
            bucket["near"].append(min(d for _r, d in frame_corner))

    def stat(values):
        if not values:
            return None
        values = sorted(values)
        n = len(values)
        return {
            "min": values[0],
            "p50": values[n // 2],
            "p95": values[min(n - 1, int(n * 0.95))],
            "max": values[-1],
            "mean": sum(values) / n,
        }

    shots = {}
    for name, bucket in per_shot.items():
        shots[name] = {
            "frames": bucket["frames"],
            "seconds": [bucket["t"][0], bucket["t"][1]],
            "centre_radius": stat(bucket["centre_r"]),
            "corner_radius": stat(bucket["corner_r"]),
            "nearest_hit_distance": stat(bucket["near"]),
            "eye_y": stat(bucket["eye_y"]),
            "frame_top_elevation": stat(bucket["top_elev"]),
            "centre_ray_escapes": bucket["escapes"],
            "corner_ray_escapes": bucket["corner_escapes"],
        }

    return {
        "floor_y": floor_y,
        "frames_sampled": len(rows),
        "every": every,
        "footprint": plan,
        "aspect": aspect,
        "centre_radius": stat(centre_radii),
        "corner_radius": stat(corner_radii),
        "nearest_hit_distance": stat(near_hits),
        "far_corner_radius": stat(reach_far),
        "aim_elevation": stat(aim_elev),
        "frame_top_elevation": stat(frame_top_elev),
        "eye_y": stat(eye_y),
        "eye_radius": stat(eye_r),
        "centre_ray_escapes": misses,
        "shots": shots,
    }


def demands(report: dict) -> dict:
    """The four numbers a builder needs, derived from the envelope.

    * `floor_radius_centre` - inside this, a plane catches the centre ray on
      every frame the centre ray comes down at all.
    * `floor_radius_frame` - inside this, a plane catches every *corner* ray
      that comes down, so the whole picture has ground under it.
    * `near_shell` - the closest any ray lands. Geometry nearer than this to
      the lens is inside the picture's foreground, which is where parallax
      comes from and also where an obstruction comes from.
    * `wall_top` - the highest a wall is worth building: the frame top never
      rises above this elevation, so anything above the tangent from the
      highest eye is authored into a volume no ray enters.
    """
    plan = report["footprint"]
    corner = report["corner_radius"]
    centre = report["centre_radius"]
    near = report["nearest_hit_distance"]
    top_elev = report["frame_top_elevation"]["max"]
    eye_hi = report["eye_y"]["max"]

    # The highest point a ray can reach at a given plan radius, taking the
    # highest eye and the highest frame-top elevation as the worst case. Above
    # this line, at that radius, is a volume no frame contains.
    def ceiling_at(radius: float) -> float:
        return eye_hi + math.tan(math.radians(top_elev)) * radius

    return {
        "floor_radius_centre": centre["max"] if centre else None,
        "floor_radius_frame_p95": corner["p95"] if corner else None,
        "floor_radius_frame_max": corner["max"] if corner else None,
        "near_shell": near["min"] if near else None,
        "course_plan_reach": plan["plan_reach"],
        "ceiling_at_course_edge": ceiling_at(plan["plan_reach"]),
        "ceiling_at_2x": ceiling_at(plan["plan_reach"] * 2.0),
        "ceiling_at_3x": ceiling_at(plan["plan_reach"] * 3.0),
        "frame_top_elevation_max": top_elev,
        "eye_y_max": eye_hi,
        "eye_y_min": report["eye_y"]["min"],
    }


def ray_grid(eye, aim, fov_y_deg, aspect, nx: int = 9, ny: int = 15):
    """A grid of rays across the picture, not just its four corners.

    Four corners answer "does the frame have ground under it" with four
    samples and weight them equally, which is wrong twice: the corners are the
    least representative part of a tall frame, and the top two land hundreds
    of units away while the bottom two land in front of the machine. A regular
    grid is area-weighted by construction, so the share of rays that miss is
    the share of the *picture* that misses, which is the number the brief asks
    for.
    """
    forward = _norm((aim[0] - eye[0], aim[1] - eye[1], aim[2] - eye[2]))
    world_up = (0.0, 1.0, 0.0)
    if abs(forward[1]) > 0.999:
        world_up = (0.0, 0.0, 1.0)
    right = _norm(_cross(forward, world_up))
    up = _norm(_cross(right, forward))
    half_y = math.tan(math.radians(fov_y_deg) * 0.5)
    half_x = half_y * aspect
    out = []
    for iy in range(ny):
        # -1 at the bottom of the frame, +1 at the top, cell centres.
        sy = -1.0 + 2.0 * (iy + 0.5) / ny
        for ix in range(nx):
            sx = -1.0 + 2.0 * (ix + 0.5) / nx
            ray = (forward[0] + right[0] * half_x * sx + up[0] * half_y * sy,
                   forward[1] + right[1] * half_x * sx + up[1] * half_y * sy,
                   forward[2] + right[2] * half_x * sx + up[2] * half_y * sy)
            out.append((_norm(ray), sx, sy))
    return out


def cylinder_hit(eye, ray, centre, radius, floor_y, top_y):
    """Where a ray meets an upright cylindrical wall of the given radius.

    Returns (y_at_hit, distance) or None. The wall is treated as unbounded in
    height here and the caller decides whether the hit is under its top,
    because "the ray hits the wall 40 units up" and "the wall is 30 units
    tall" are two different facts and conflating them is how a room ends up
    with a strip of void above its own parapet.
    """
    ox = eye[0] - centre[0]
    oz = eye[2] - centre[1]
    a = ray[0] * ray[0] + ray[2] * ray[2]
    if a <= 1e-12:
        return None
    b = 2.0 * (ox * ray[0] + oz * ray[2])
    c = ox * ox + oz * oz - radius * radius
    disc = b * b - 4.0 * a * c
    if disc < 0.0:
        return None
    root = math.sqrt(disc)
    for t in sorted(((-b - root) / (2.0 * a), (-b + root) / (2.0 * a))):
        if t > 1e-6:
            y = eye[1] + ray[1] * t
            if y >= floor_y - 1e-6:
                return (y, t)
            return None
    return None


def sizing(track: dict, course: dict, floor_y: float, radii, every: int = 6,
           nx: int = 9, ny: int = 15) -> dict:
    """Sweep candidate stage radii and report what each one costs and buys.

    A room is one number - how far out the wall stands - and every other
    property follows from it. Rather than pick one and defend it, this walks a
    range and reports, per radius:

        floor       share of the picture that lands on a floor disc of that
                    radius before it reaches the wall
        wall        share that lands on the wall
        void        share that escapes over the wall - the V29 failure, as a
                    fraction of the picture rather than as a verdict
        wall_top    how tall the wall has to be for `void` to be that number
        near        closest the wall ever comes to the lens
        outside     frames where the camera itself is beyond the wall, which
                    disqualifies a closed ring at that radius outright

    The last column is the one that rules out the small rooms: camera A's eye
    travels to r = 45.7 and a ring inside that has the lens outdoors.
    """
    plan = footprint(course)
    centre = (plan["centre"][0], plan["centre"][1])
    aspect = FRAME_W / FRAME_H
    rows = frames(track, every)

    def sweep(subset, radius):
        floor_n = wall_n = void_n = 0
        wall_tops = []
        near_floor = near_wall = math.inf
        outside = 0
        for record in subset:
            eye = record["eye"]
            eye_r = math.hypot(eye[0] - centre[0], eye[2] - centre[1])
            if eye_r >= radius:
                outside += 1
            for ray, _sx, _sy in ray_grid(eye, record["aim"], record["fov"],
                                          aspect, nx, ny):
                ground = plane_hit(eye, ray, floor_y)
                wall = cylinder_hit(eye, ray, centre, radius, floor_y, None)
                if ground is not None and (wall is None
                                           or ground[3] <= wall[1]):
                    floor_n += 1
                    near_floor = min(near_floor, ground[3])
                elif wall is not None:
                    wall_n += 1
                    wall_tops.append(wall[0])
                    near_wall = min(near_wall, wall[1])
                else:
                    void_n += 1
        total = max(1, floor_n + wall_n + void_n)
        wall_tops.sort()
        return {
            "radius": radius,
            "floor": floor_n / total,
            "wall": wall_n / total,
            "void": void_n / total,
            "wall_top_p95": (wall_tops[int(len(wall_tops) * 0.95)]
                             if wall_tops else None),
            "wall_top_max": wall_tops[-1] if wall_tops else None,
            "nearest_floor": near_floor if near_floor < math.inf else None,
            "nearest_wall": near_wall if near_wall < math.inf else None,
            "frames_outside": outside,
            "frames": len(subset),
        }

    out = [sweep(rows, radius) for radius in radii]

    # Per shot, because the film is not one framing. `run_in` is the final
    # sprint - one continuous 6.47 s take, the shot V29 lost - and it sits
    # lowest and closest, so a radius that reads as a distant band in
    # `release` reads as a wall beside the racers here. A stage sized on the
    # aggregate would be sized on the shot that matters least.
    by_shot = {}
    for name in sorted({r["shot"] for r in rows}):
        subset = [r for r in rows if r["shot"] == name]
        by_shot[name] = {
            "frames": len(subset),
            "seconds": [min(r["t"] for r in subset),
                        max(r["t"] for r in subset)],
            "eye_radius_max": max(
                math.hypot(r["eye"][0] - centre[0], r["eye"][2] - centre[1])
                for r in subset),
            "rows": [sweep(subset, radius) for radius in radii],
        }

    return {"floor_y": floor_y, "centre": list(centre), "rows": out,
            "by_shot": by_shot,
            "rays_per_frame": nx * ny, "every": every}


def bearings(track: dict, course: dict, floor_y: float, radius: float,
             every: int = 6, nx: int = 9, ny: int = 15,
             sectors: int = 24) -> dict:
    """Which compass sectors of the wall the film actually looks at.

    This is what V29 had no way to ask, and it is the whole of Part F. A round
    hall spends its triangle budget evenly around 360 degrees; a camera does
    not. If two thirds of the wall is never in a frame, then a rotationally
    symmetric room is paying for scenery nobody sees *and* denying the viewer
    the one thing a room can give them - the sense of having moved past
    something recognisable.

    Sectors are measured at the wall radius, in the same bearing convention
    `environment_stage._polar` uses: bearing 0 is +Z and the swing is toward
    +X, so a sector index here is directly authorable as a `skip` list or a
    per-segment kind in a profile.
    """
    plan = footprint(course)
    centre = (plan["centre"][0], plan["centre"][1])
    aspect = FRAME_W / FRAME_H
    rows = frames(track, every)
    step = 360.0 / sectors

    hits = [0] * sectors
    shot_hits: dict[str, list[int]] = {}
    first_seen: dict[int, float] = {}
    total = 0
    for record in rows:
        eye = record["eye"]
        seen = set()
        for ray, _sx, _sy in ray_grid(eye, record["aim"], record["fov"],
                                      aspect, nx, ny):
            ground = plane_hit(eye, ray, floor_y)
            wall = cylinder_hit(eye, ray, centre, radius, floor_y, None)
            if wall is None:
                continue
            if ground is not None and ground[3] <= wall[1]:
                continue
            x = eye[0] + ray[0] * wall[1] - centre[0]
            z = eye[2] + ray[2] * wall[1] - centre[1]
            bearing = math.degrees(math.atan2(x, z)) % 360.0
            index = int(bearing / step) % sectors
            hits[index] += 1
            total += 1
            seen.add(index)
            first_seen.setdefault(index, record["t"])
        bucket = shot_hits.setdefault(record["shot"], [0] * sectors)
        for index in seen:
            bucket[index] += 1

    return {
        "radius": radius,
        "sectors": sectors,
        "sector_degrees": step,
        "hits": hits,
        "share": [h / max(1, total) for h in hits],
        "frames_seeing": {name: b for name, b in shot_hits.items()},
        "first_seen": {str(k): v for k, v in sorted(first_seen.items())},
        "frames": len(rows),
        "never_seen": [i for i, h in enumerate(hits) if h == 0],
    }


def parallax(track: dict, course: dict, every: int = 6,
             distances=(15.0, 30.0, 60.0, 120.0, 250.0)) -> dict:
    """How fast a static point at a given range crosses the picture.

    Part G asks for proof that near, mid and far move at different image-space
    speeds, and the honest way to get it is not a block matcher on a render -
    a matcher measures whatever texture happens to be there. It is the
    projection itself: a world point at perpendicular range `d` from a camera
    moving at `v` perpendicular to the ray sweeps `v / d` radians a second,
    which is `(v / d) / (2 * tan(fov/2))` of the frame height a second.

    So the ratio between two strata is exactly the inverse ratio of their
    ranges, and a room's parallax is decided when its radii are chosen, before
    a material exists. V29's nearest standing element was at 64 and its wall
    at 122: a 1.9x spread. A stage whose near lip is at 15 and whose wall is
    at 65 is a 4.3x spread, and that difference is a design decision rather
    than a lighting one.
    """
    rows = frames(track, 1)
    out: dict[str, list] = {str(d): [] for d in distances}
    speeds = []
    for index in range(1, len(rows)):
        a, b = rows[index - 1], rows[index]
        dt = b["t"] - a["t"]
        if dt <= 1e-6 or b["shot"] != a["shot"]:
            continue
        v = math.sqrt(sum((b["eye"][k] - a["eye"][k]) ** 2
                          for k in range(3))) / dt
        speeds.append(v)
        half = math.tan(math.radians(b["fov"]) * 0.5)
        for d in distances:
            # Frame heights per second. The perpendicular component is bounded
            # above by the speed itself, so this is the fastest a point at
            # that range can cross - the right bound for "does it read".
            out[str(d)].append((v / d) / (2.0 * half))
    speeds.sort()

    def stat(values):
        values = sorted(values)
        if not values:
            return None
        n = len(values)
        return {"p50": values[n // 2], "p90": values[int(n * 0.9)],
                "max": values[-1]}

    return {
        "camera_speed": stat(speeds),
        "frame_heights_per_second": {d: stat(v) for d, v in out.items()},
        "samples": len(speeds),
    }


def render_bearings(report: dict) -> str:
    out = ["", "WHERE THE FILM LOOKS  (wall at r = %.1f, %d sectors of %.1f deg)"
           % (report["radius"], report["sectors"], report["sector_degrees"])]
    peak = max(report["share"]) or 1.0
    out.append("  %3s %8s %9s %s" % ("sec", "bearing", "share", "seen"))
    for index, share in enumerate(report["share"]):
        bar = "#" * int(round(share / peak * 40.0))
        out.append("  %3d %7.1f  %7.2f%%  %s"
                   % (index, index * report["sector_degrees"],
                      share * 100.0, bar))
    never = report["never_seen"]
    out.append("  sectors never in frame: %s"
               % (", ".join(str(i) for i in never) if never else "none"))
    covered = sum(1 for s in report["share"] if s > 0.005)
    out.append("  sectors carrying >0.5%% of the wall pixels: %d of %d"
               % (covered, report["sectors"]))
    return "\n".join(out)


def render_parallax(report: dict) -> str:
    out = ["", "PARALLAX BY RANGE  (frame heights per second, geometric)"]
    s = report["camera_speed"]
    out.append("  camera speed          p50 %.2f  p90 %.2f  max %.2f units/s"
               % (s["p50"], s["p90"], s["max"]))
    out.append("  %10s %10s %10s %10s" % ("range", "p50", "p90", "max"))
    for key in sorted(report["frame_heights_per_second"],
                      key=lambda k: float(k)):
        v = report["frame_heights_per_second"][key]
        out.append("  %10.0f %10.3f %10.3f %10.3f"
                   % (float(key), v["p50"], v["p90"], v["max"]))
    ranges = sorted(float(k) for k in report["frame_heights_per_second"])
    out.append("  near/far speed ratio at p50: %.2fx"
               % (report["frame_heights_per_second"][str(ranges[0])]["p50"]
                  / report["frame_heights_per_second"][str(ranges[-1])]["p50"]))
    return "\n".join(out)


def render_sizing(report: dict) -> str:
    out = ["", "STAGE SIZING SWEEP  (%d rays/frame, every %d frames)"
           % (report["rays_per_frame"], report["every"])]
    out.append("  %7s %8s %8s %8s %10s %9s %9s"
               % ("radius", "floor", "wall", "VOID", "wallTop95", "nearest",
                  "eyeOut"))
    def table(rows, indent="  "):
        lines = []
        for row in rows:
            lines.append("%s%7.1f %7.2f%% %7.2f%% %7.2f%% %10s %9s %9d"
                         % (indent, row["radius"], row["floor"] * 100.0,
                            row["wall"] * 100.0, row["void"] * 100.0,
                            "%.1f" % row["wall_top_p95"]
                            if row["wall_top_p95"] else "-",
                            "%.1f" % row["nearest_wall"]
                            if row["nearest_wall"] else "-",
                            row["frames_outside"]))
        return lines

    out.extend(table(report["rows"]))
    out.append("  eyeOut > 0 disqualifies a closed ring at that radius: the")
    out.append("  camera would be standing outside its own room.")
    out.append("  nearest is the closest the WALL comes to the lens.")
    for name, shot in report.get("by_shot", {}).items():
        out.append("")
        out.append("  -- %s (%d frames, eye reaches r = %.1f)"
                   % (name, shot["frames"], shot["eye_radius_max"]))
        out.append("  %7s %8s %8s %8s %10s %9s %9s"
                   % ("radius", "floor", "wall", "VOID", "wallTop95",
                      "nearest", "eyeOut"))
        out.extend(table(shot["rows"]))
    return "\n".join(out)


def render(report: dict) -> str:
    out = []
    plan = report["footprint"]
    out.append("CAMERA A VISIBLE ENVELOPE")
    out.append("=" * 72)
    out.append("frames sampled          %d (every %d)"
               % (report["frames_sampled"], report["every"]))
    out.append("floor plane at y        %.2f" % report["floor_y"])
    out.append("")
    out.append("COURSE FOOTPRINT (layout units)")
    out.append("  plan centre           (%.2f, %.2f)"
               % (plan["centre"][0], plan["centre"][1]))
    out.append("  x span                %.2f  [%.2f .. %.2f]"
               % (plan["span_x"], plan["x"][0], plan["x"][1]))
    out.append("  z span                %.2f  [%.2f .. %.2f]"
               % (plan["span_z"], plan["z"][0], plan["z"][1]))
    out.append("  y span                %.2f  [%.2f .. %.2f]"
               % (plan["span_y"], plan["y"][0], plan["y"][1]))
    out.append("  plan reach            %.2f" % plan["plan_reach"])
    out.append("")
    out.append("THE LENS")
    for key in ("aim_elevation", "frame_top_elevation", "eye_y", "eye_radius"):
        s = report[key]
        out.append("  %-21s min %8.2f  p50 %8.2f  max %8.2f"
                   % (key, s["min"], s["p50"], s["max"]))
    out.append("")
    out.append("WHERE THE RAYS LAND (plan radius from course centre)")
    for key in ("centre_radius", "corner_radius", "far_corner_radius"):
        s = report[key]
        if s is None:
            continue
        out.append("  %-21s min %8.2f  p50 %8.2f  p95 %8.2f  max %8.2f"
                   % (key, s["min"], s["p50"], s["p95"], s["max"]))
    s = report["nearest_hit_distance"]
    out.append("  %-21s min %8.2f  p50 %8.2f  max %8.2f"
               % ("nearest hit (range)", s["min"], s["p50"], s["max"]))
    out.append("  centre rays that never come down: %d"
               % report["centre_ray_escapes"])
    out.append("")
    out.append("PER SHOT")
    out.append("  %-10s %6s %14s %9s %9s %9s %8s"
               % ("shot", "frames", "seconds", "centreR", "cornerR95",
                  "nearest", "topElev"))
    for name, shot in sorted(report["shots"].items(),
                             key=lambda kv: kv[1]["seconds"][0]):
        cr = shot["centre_radius"]
        co = shot["corner_radius"]
        nh = shot["nearest_hit_distance"]
        out.append("  %-10s %6d %6.2f-%6.2f %9s %9s %9s %8.2f"
                   % (name, shot["frames"], shot["seconds"][0],
                      shot["seconds"][1],
                      "%.2f" % cr["max"] if cr else "escape",
                      "%.2f" % co["p95"] if co else "-",
                      "%.2f" % nh["min"] if nh else "-",
                      shot["frame_top_elevation"]["max"]))
    out.append("")
    d = demands(report)
    out.append("WHAT THIS DEMANDS OF A STAGE")
    out.append("  a floor must reach r >= %.2f to catch every centre ray"
               % d["floor_radius_centre"])
    out.append("  a floor must reach r >= %.2f to catch 95%% of corner rays"
               % d["floor_radius_frame_p95"])
    out.append("  a floor must reach r >= %.2f to catch every corner ray"
               % d["floor_radius_frame_max"])
    out.append("  nothing may stand closer to the lens than %.2f"
               % d["near_shell"])
    out.append("  the course itself reaches r = %.2f"
               % d["course_plan_reach"])
    out.append("  no ray ever rises above %.2f deg; at r = %.0f that is y = %.1f"
               % (d["frame_top_elevation_max"], d["course_plan_reach"] * 2.0,
                  d["ceiling_at_2x"]))
    out.append("")
    out.append("  V29's hall, for comparison:")
    out.append("    deck inner radius   88.00   (%.2fx the course)"
               % (88.0 / d["course_plan_reach"]))
    out.append("    nearest standing     64.00   (%.2fx the course)"
               % (64.0 / d["course_plan_reach"]))
    out.append("    the demand above is  %.2f   (%.2fx the course)"
               % (d["floor_radius_frame_p95"],
                  d["floor_radius_frame_p95"] / d["course_plan_reach"]))
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--track", default=TRACK)
    parser.add_argument("--geometry", default=GEOMETRY)
    parser.add_argument("--every", type=int, default=3)
    parser.add_argument("--clearance", type=float, default=2.0,
                        help="floor below the lowest racing-line point; the "
                             "same STAGE_FLOOR_CLEARANCE race2_scene uses")
    parser.add_argument("--radii",
                        default="40,50,55,60,65,70,80,90,100,120,150")
    parser.add_argument("--sweep-every", dest="sweep_every", type=int,
                        default=12)
    parser.add_argument("--wall", type=float, default=65.0,
                        help="the wall radius the bearing histogram is taken "
                             "at; the sizing sweep is what picks it")
    parser.add_argument("--json", default="")
    args = parser.parse_args()

    if not os.path.exists(args.track):
        raise SystemExit(
            f"no camera track at {args.track}\n"
            "make it with:  python tools/race2_camera.py --seed=8 "
            "--course=switchyard && python tools/race2_cine.py --seed=8 --only=A")

    track = load_track(args.track)
    course = load_course(args.geometry)
    floor_y = min(p[1] for p in course["line"]) - args.clearance
    report = envelope(track, course, floor_y, args.every)
    report["demands"] = demands(report)
    report["duration"] = float(track.get("duration", 0.0))
    print(render(report))

    radii = [float(v) for v in args.radii.split(",") if v.strip()]
    report["sizing"] = sizing(track, course, floor_y, radii, args.sweep_every)
    print(render_sizing(report["sizing"]))

    report["bearings"] = bearings(track, course, floor_y, args.wall,
                                  args.sweep_every)
    print(render_bearings(report["bearings"]))

    report["parallax"] = parallax(track, course)
    print(render_parallax(report["parallax"]))
    if args.json:
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=1)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Where a world form has to stand to be in a given frame.

    python tools/sloped_v251_sites.py --where 30 48        # who sees this point
    python tools/sloped_v251_sites.py --ground finish      # what a moment looks at
    python tools/sloped_v251_sites.py --audit              # every authored site

**This exists because of a mistake that was made twice.** V25's own record of
it is that a ring at radius 130 "looked like the right place for a midground"
and turned out to fill half of four frames; V25.1 repeated the shape of the
error at the finish, where an arc of five seventy-unit masses was placed round
a node and came out thirty units *below* the deck, invisible.

Both were placement judgements made in plan, about a camera that is neither in
plan nor level. The fix is not more care, it is an instrument: **project the
site into the frame and read off where it lands.**

The camera track is read, never written, and no stage renders anything. This
is arithmetic on `cameras_v221_5432.json` and `sloped.terrain`, which is an
exact port of `course_terrain.height`.

## What the numbers mean

For a plan position, each moment reports:

    in      whether the point is inside the frame at all
    u, v    where it lands, -1..1 across and -1..1 up the frame
    d       distance from the lens, in layout units
    y       the terrain height there, and the lens height for comparison
    rise    how tall a form at that point has to be for its top to reach the
            top edge of the frame - which is the number that decides whether
            a mass reads as a wall or as a stump

`v = -1` is the bottom edge and `v = +1` the top. A form whose foot is at
`v < -1` is below frame; one whose crest is at `v > +1` is cropped, which for
a canyon wall is usually right.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from sloped import layout, terrain, v251_world  # noqa: E402

TRACKS = {
    "race": os.path.join("output", "sloped_race_v1", "cameras_v221_5432.json"),
    "preview": os.path.join("output", "sloped_race_v1",
                            "preview_v221_5432.json"),
}

#: The render is 1080 x 1920, and Godot's `fov` on a portrait viewport is the
#: **vertical** angle. The horizontal half-angle is therefore the vertical one
#: scaled by the aspect - which is 0.5625 here, so the frame is far narrower
#: across than a reader of `fov = 36` would assume. Getting this backwards puts
#: a form two thirds of the way out of shot and calls it centred.
ASPECT = 1080.0 / 1920.0


class Shot:
    """One camera at one output second."""

    def __init__(self, second: float, eye, aim, fov: float, cut: str):
        self.second = second
        self.eye = eye
        self.aim = aim
        self.fov = fov
        self.cut = cut
        forward = _sub(aim, eye)
        self.distance = _length(forward)
        self.forward = _scale(forward, 1.0 / max(self.distance, 1e-6))
        right = _cross(self.forward, (0.0, 1.0, 0.0))
        if _length(right) < 1e-6:
            right = (1.0, 0.0, 0.0)
        self.right = _scale(right, 1.0 / _length(right))
        self.up = _cross(self.right, self.forward)
        self.tan_v = math.tan(math.radians(fov) * 0.5)
        self.tan_h = self.tan_v * ASPECT

    def project(self, point):
        """`(inside, u, v, depth)` for a world point."""
        rel = _sub(point, self.eye)
        depth = _dot(rel, self.forward)
        if depth <= 0.01:
            return False, 0.0, 0.0, depth
        u = _dot(rel, self.right) / (depth * self.tan_h)
        v = _dot(rel, self.up) / (depth * self.tan_v)
        return abs(u) <= 1.0 and abs(v) <= 1.0, u, v, depth

    def top_of_frame(self, x: float, z: float) -> float:
        """The world y at which a point at `(x, z)` sits on the frame's top
        edge. A form there is exactly full height in shot."""
        # Solve v = 1 for y. Everything is linear in y once x and z are fixed,
        # so two samples and a straight line are exact rather than iterative.
        low = self._v_at(x, 0.0, z)
        high = self._v_at(x, 100.0, z)
        if abs(high - low) < 1e-9:
            return float("nan")
        return 100.0 * (1.0 - low) / (high - low)

    def _v_at(self, x: float, y: float, z: float) -> float:
        return self.project((x, y, z))[2]


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _scale(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def _length(a):
    return math.sqrt(_dot(a, a))


def replay_second(track: dict, out_second: float) -> float:
    """Output time to replay time, through the edit map.

    **A moment's second is an output second; a camera frame is stamped with a
    replay second; and on this film they are nearly two seconds apart by the
    finish.** V22.1's edit omits 1.95 s of replay in six windows. Inside a
    window the map has slope one; between two windows it steps, and that step
    is the cut.

    This is a port of `sloped_race_scene._replay_at`, and it is here because
    the first version of this tool did not have it. Every camera it reported
    was the camera at the *replay* second of the same number - which at the
    descent is 2.15 s of a moving chase camera away from the frame the sheet
    actually shows. Two placements in `sloped_v251_profiles` were authored
    against that before a check against the race nodes caught it: the start
    camera looks at the start node dead centre, and the tool said it did not.

    The project's oldest lesson, landing again: check the instrument before
    believing the result.
    """
    edit: list = track.get("edit", [])
    if not edit:
        return out_second
    for segment in edit:
        low, high = segment["out"]
        first, last = segment["replay"]
        if out_second <= high or segment is edit[-1]:
            return first + min(max(out_second - low, 0.0), last - first)
    return out_second


def shots() -> list[Shot]:
    """One `Shot` per comparison moment, from the solved tracks."""
    out: list[Shot] = []
    for track, path in TRACKS.items():
        full = os.path.join(PROJECT_ROOT, path)
        if not os.path.isfile(full):
            raise SystemExit(
                "missing camera track: " + path + "\n"
                "Copy V22.1's solved tracks into output/sloped_race_v1 first."
            )
        with open(full, encoding="utf-8") as handle:
            data = json.load(handle)
        for moment in v251_world.MOMENTS:
            if moment.track != track:
                continue
            want = replay_second(data, moment.second)
            best = None
            for cut in data["cuts"]:
                for frame in cut["frames"]:
                    error = abs(frame[0] - want)
                    if best is None or error < best[0]:
                        best = (error, frame)
            if best is None or best[0] > 0.05:
                raise SystemExit(
                    "no camera frame within 50 ms of %s (output %.3f s -> "
                    "replay %.3f s)" % (moment.key, moment.second, want))
            frame = best[1]
            out.append(Shot(moment.second,
                            (frame[1], frame[2], frame[3]),
                            (frame[4], frame[5], frame[6]),
                            frame[7], moment.key))
    out.sort(key=lambda one: one.cut)
    return out


def where(x: float, z: float, cfg: dict) -> str:
    ground = terrain.height(x, z, cfg)
    rows = [f"({x:.1f}, {z:.1f})  ground y = {ground:.1f}", ""]
    rows.append("  moment            in      u      v      d   lens y   "
                "rise to top")
    seen = 0
    for shot in shots():
        inside, u, v, depth = shot.project((x, ground, z))
        crest = shot.top_of_frame(x, z)
        rise = crest - ground
        if inside:
            seen += 1
        rows.append(
            "  %-16s %-4s %6.2f %6.2f %6.1f %7.1f %8.1f"
            % (shot.cut, "yes" if inside else "-", u, v, depth,
               shot.eye[1], rise))
    rows.append("")
    rows.append(f"  the foot of a form here is in {seen} of "
                f"{len(shots())} frames")
    return "\n".join(rows)


def ground_of(moment: str, cfg: dict) -> str:
    """What the named moment's camera is actually looking at, as a grid of
    ground points across the frame."""
    picked = [one for one in shots() if one.cut == moment]
    if not picked:
        raise SystemExit(f"no moment named {moment!r}")
    shot = picked[0]
    rows = [
        f"{moment}: lens ({shot.eye[0]:.1f}, {shot.eye[1]:.1f}, "
        f"{shot.eye[2]:.1f})  aim ({shot.aim[0]:.1f}, {shot.aim[1]:.1f}, "
        f"{shot.aim[2]:.1f})  fov {shot.fov:.0f}",
        "",
        "  where in frame      ground point        y     distance",
    ]
    for label, u, v in [("top left", -0.8, 0.85), ("top", 0.0, 0.85),
                        ("top right", 0.8, 0.85), ("left", -0.8, 0.0),
                        ("centre", 0.0, 0.0), ("right", 0.8, 0.0),
                        ("bottom left", -0.8, -0.85),
                        ("bottom", 0.0, -0.85),
                        ("bottom right", 0.8, -0.85)]:
        hit = _cast(shot, u, v, cfg)
        if hit is None:
            rows.append("  %-18s  (sky - no ground within 400 units)" % label)
            continue
        x, y, z, depth = hit
        rows.append("  %-18s (%6.1f, %6.1f)  %6.1f   %6.1f"
                    % (label, x, z, y, depth))
    return "\n".join(rows)


def _cast(shot: Shot, u: float, v: float, cfg: dict, limit: float = 400.0):
    """March a frame direction until it goes under the terrain."""
    direction = (
        shot.forward[0] + shot.right[0] * u * shot.tan_h
        + shot.up[0] * v * shot.tan_v,
        shot.forward[1] + shot.right[1] * u * shot.tan_h
        + shot.up[1] * v * shot.tan_v,
        shot.forward[2] + shot.right[2] * u * shot.tan_h
        + shot.up[2] * v * shot.tan_v,
    )
    direction = _scale(direction, 1.0 / _length(direction))
    step = 0.5
    depth = 1.0
    while depth < limit:
        x = shot.eye[0] + direction[0] * depth
        y = shot.eye[1] + direction[1] * depth
        z = shot.eye[2] + direction[2] * depth
        if y <= terrain.height(x, z, cfg):
            return x, y, z, depth
        depth += step
        step = min(step * 1.03, 4.0)
    return None


def audit(cfg: dict) -> str:
    """Every authored site in the V25.1 profile, with the frames that see it.

    A site nobody sees is not automatically wrong - the merge mark is placed
    for the preview - but a site nobody sees that was authored *for* a race
    moment is a site in the wrong place, and this is the only cheap way to
    know which is which.
    """
    from tools import sloped_v251_profiles as v251

    rows: list[str] = ["site                     frames that see its foot"]
    marks = v251.LANDMARKS["sites"]
    for name, site in marks.items():
        node = site.get("node", name)
        anchor = v251.NODES[node]
        offset = site.get("offset", [0.0, 0.0])
        x = anchor[0] + offset[0]
        z = anchor[1] + offset[1]
        seen = [one.cut for one in shots()
                if one.project((x, terrain.height(x, z, cfg), z))[0]]
        rows.append("  landmark %-14s %s" % (name, ", ".join(seen) or "none"))
    for index, site in enumerate(v251.PATCHES["sites"]):
        x = v251.CENTRE[0] + site[0]
        z = v251.CENTRE[1] + site[1]
        seen = [one.cut for one in shots()
                if one.project((x, terrain.height(x, z, cfg), z))[0]]
        rows.append("  patch %-2d %-14s %s"
                    % (index, site[3].replace("world_", ""),
                       ", ".join(seen) or "none"))
    return "\n".join(rows)


def suggest(moment: str, cfg: dict, height: float = 30.0,
            clearance: float = 12.0, lens: float = 16.0,
            floor: float = 14.0) -> str:
    """Plan positions a landmark of `height` could stand at and be seen.

    Sweeps the layout on a four-unit lattice and keeps the cells that clear
    the racing line and the camera path and land inside the named frame.

    The score is what the brief actually wants from a landmark: **how much of
    the frame's height the form fills once it is clipped to the frame.** A
    form whose foot is below the bottom edge and whose crest is above the top
    fills all of it; one that is thirty units behind a ridge fills none.

    Three filters, and the middle one was learnt the hard way: a point a metre
    from the lens divides by a depth near zero, so its apparent size is
    enormous and it sorts to the top. Anything nearer than `floor` is not a
    landmark, it is a lens cap.
    """
    from tools import sloped_v251_profiles as v251

    picked = [one for one in shots() if one.cut == moment]
    if not picked:
        raise SystemExit("no moment named " + repr(moment))
    shot = picked[0]
    line = _racing_line()
    lens_points = [(one[0], one[1]) for one in v251.v25.CAMERA_PATH]
    rows: list[tuple] = []
    for x in range(-80, 81, 4):
        for z in range(-90, 109, 4):
            if _nearest(line, x, z) < clearance:
                continue
            if _nearest(lens_points, x, z) < lens:
                continue
            ground = terrain.height(float(x), float(z), cfg)
            foot = shot.project((float(x), ground, float(z)))
            crest = shot.project((float(x), ground + height, float(z)))
            if foot[3] < floor or crest[3] < floor:
                continue
            if abs(foot[1]) > 1.0 or abs(crest[1]) > 1.0:
                continue
            top = min(crest[2], 1.0)
            bottom = max(foot[2], -1.0)
            share = (top - bottom) * 0.5
            if share <= 0.02:
                continue
            rows.append((share, abs(foot[1]), x, z, ground, foot[1], foot[2],
                         crest[2], foot[3]))
    rows.sort(key=lambda one: (-one[0], one[1]))
    out = [moment + ": where a %.0f-unit form is seen, best first" % height,
           "",
           "       x      z   ground      u   v foot  v crest      d   "
           "share of frame"]
    for row in rows[:16]:
        out.append("  %6d %6d %8.1f %6.2f %8.2f %8.2f %6.1f %10.2f"
                   % (row[2], row[3], row[4], row[5], row[6], row[7],
                      row[8], row[0]))
    if not rows:
        out.append("  nothing clears both keep-outs and lands in this frame")
    return chr(10).join(out)


def _racing_line() -> list[tuple[float, float]]:
    """The centreline in plan, from the layout's own runs."""
    points: list[tuple[float, float]] = []
    for run in layout.RUNS:
        for node in run["controls"]:
            points.append((float(node[0]), float(node[2])))
    dense: list[tuple[float, float]] = []
    for index in range(len(points) - 1):
        ax, az = points[index]
        bx, bz = points[index + 1]
        steps = max(int(math.dist((ax, az), (bx, bz)) / 2.0), 1)
        for step in range(steps):
            share = step / steps
            dense.append((ax + (bx - ax) * share, az + (bz - az) * share))
    dense.append(points[-1])
    return dense


def _nearest(points, x: float, z: float) -> float:
    return min(math.dist((x, z), one) for one in points)


#: The same five camera moves the image-space parallax test uses, in output
#: seconds. Kept identical to `tools/sloped_v25_world.PARALLAX_PAIRS` on
#: purpose: the two measures answer the same question two ways, and a reviewer
#: comparing them should not have to check that they are of the same instant.
MOVES = (
    ("obstacle_pan", "race", 11.400, 11.650),
    ("fork_swing", "race", 13.300, 13.550),
    ("branch_cross", "race", 15.300, 15.550),
    ("final_dive", "race", 19.400, 19.650),
    ("preview_dolly", "preview", 1.400, 1.650),
)


def _shot_at(track: str, second: float) -> Shot:
    full = os.path.join(PROJECT_ROOT, TRACKS[track])
    with open(full, encoding="utf-8") as handle:
        data = json.load(handle)
    want = replay_second(data, second)
    best = None
    for cut in data["cuts"]:
        for frame in cut["frames"]:
            error = abs(frame[0] - want)
            if best is None or error < best[0]:
                best = (error, frame)
    frame = best[1]
    return Shot(second, (frame[1], frame[2], frame[3]),
                (frame[4], frame[5], frame[6]), frame[7], track)


def geometric_parallax(cfg: dict) -> str:
    """Image displacement per depth band, from geometry rather than pixels.

    ## Why a second parallax measure exists

    V25's test block-matches 41x41 templates on the delivered frames, and it
    needs **local contrast inside the template**: a patch whose standard
    deviation is under `TEXTURE_FLOOR` is discarded, because a correlation
    peak on a flat field means nothing.

    That requirement is fine against `smooth_mass`, whose averaged normals put
    a shading gradient on every square inch of every surface. It is not fine
    against a flat-shaded kit: **a facet is one value**, which is the whole
    point of it, and a 41x41 window that lands inside one has a standard
    deviation near zero. So on V25.1 the matcher discards bands that cover a
    third of the frame - `branch_cross` reports the ridges at 31.8% cover and
    "fewer than two patches", which is not a finding about the world.

    This measure has no such failure mode, because it never looks at a
    surface. It takes the **positions of the world's own forms**, read out of
    the profile, projects each one through the camera at both instants, and
    reports the median pixel displacement per band. Exact, shading-blind, and
    directly comparable between two worlds that share a layout.

    What it cannot do is notice that a form is occluded, so it is reported
    beside the image-space test rather than instead of it: one measures what
    moved, the other measures what was visible.
    """
    from tools import sloped_v251_profiles as v251

    bands = _band_points(v251, cfg)
    rows = [
        "Analytic parallax: median image displacement per depth band over",
        "0.25 s, computed by projecting the world's own form positions through",
        "the solved camera at both instants. Shading-blind, so it measures the",
        "bands a block matcher discards on flat-shaded rock. Pixels at",
        "1080 x 1920. N is how many forms of that band are on screen at both",
        "instants.",
        "",
    ]
    header = "move            " + "".join("%-18s" % one for one in bands)
    rows.append(header)
    rows.append("-" * len(header))
    for label, track, before, after in MOVES:
        first = _shot_at(track, before)
        second = _shot_at(track, after)
        cells = []
        for name, points in bands.items():
            moved: list[float] = []
            for x, y, z in points:
                a = first.project((x, y, z))
                b = second.project((x, y, z))
                if not (a[0] and b[0]):
                    continue
                dx = (b[1] - a[1]) * 0.5 * 1080.0
                dy = (b[2] - a[2]) * 0.5 * 1920.0
                moved.append(math.hypot(dx, dy))
            if not moved:
                cells.append("%-18s" % "-")
                continue
            moved.sort()
            cells.append("%-18s" % ("%.0fpx/%dn"
                                    % (moved[len(moved) // 2], len(moved))))
        rows.append("%-16s%s" % (label, "".join(cells)))
    rows.append("")
    rows.append("counts: " + ", ".join("%s %d" % (name, len(points))
                                       for name, points in bands.items()))
    return chr(10).join(rows)


def _band_points(v251, cfg: dict) -> dict:
    """Representative world positions per depth band, from the profile.

    Every ring, scatter and authored site is re-derived here with the same
    arithmetic `environment_world.gd` uses, so the points are where the meshes
    actually are rather than where a reader of the profile would guess. The
    scatters are sampled rather than reproduced exactly - their rejection
    sampling is the builder's and porting it would be a second implementation
    to keep in step - so the foreground row is a band of positions at the
    right radii rather than the exact 46 rocks.
    """
    centre = v251.CENTRE
    bands: dict = {"foreground": [], "vegetation": [], "ridges": [],
                   "walls": [], "ranges": []}

    def ring(spec, into):
        count = int(spec.get("count", 0))
        for index in range(count):
            bearing = math.radians(
                float(spec.get("bearing_from", 90.0))
                + float(spec.get("bearing_step", 27.0)) * index)
            radius = float(spec.get("radius", 168.0)) + float(
                spec.get("radius_step", 26.0)) * (
                    index % max(int(spec.get("radius_cycle", 3)), 1))
            height = float(spec.get("height", 140.0)) + float(
                spec.get("height_step", -18.0)) * (
                    index % max(int(spec.get("height_cycle", 4)), 1))
            x = centre[0] + math.sin(bearing) * radius
            z = centre[1] + math.cos(bearing) * radius
            ground = terrain.height(x, z, cfg) - float(spec.get("sink", 14.0))
            into.append((x, ground + height * 0.55, z))

    ring(v251.WALLS, bands["walls"])
    for band in v251.RIDGES["bands"]:
        merged = dict(v251.RIDGES)
        merged.update(band)
        ring(merged, bands["ridges"])
    # The foreground: the authored scarps, plus the landmark forms that stand
    # on the near ground, plus a lattice at the boulder band's own offsets.
    for site in v251.SCARPS["sites"]:
        x = centre[0] + float(site[0])
        z = centre[1] + float(site[1])
        bands["foreground"].append((x, terrain.height(x, z, cfg) + 3.0, z))
    line = _racing_line()
    for index, (lx, lz) in enumerate(line):
        if index % 9:
            continue
        for side in (-1.0, 1.0):
            offset = float(v251.BOULDERS.get("near", 7.0)) + 9.0
            x = lx + side * offset
            z = lz + side * offset * 0.3
            bands["foreground"].append(
                (x, terrain.height(x, z, cfg) + 2.5, z))
            bands["vegetation"].append(
                (x, terrain.height(x, z, cfg) + 3.5, z))
    # V23's own distant rings are the `ranges` band and are untouched by this
    # pass; sampled on a ring at their shipped radii so the row is not empty.
    for index in range(24):
        bearing = math.radians(index * 15.0)
        for radius in (260.0, 470.0, 660.0):
            x = centre[0] + math.sin(bearing) * radius
            z = centre[1] + math.cos(bearing) * radius
            bands["ranges"].append((x, 14.0, z))
    return bands


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--where", nargs=2, type=float, metavar=("X", "Z"))
    parser.add_argument("--ground", metavar="MOMENT")
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--suggest", metavar="MOMENT")
    parser.add_argument("--parallax", action="store_true")
    parser.add_argument("--height", type=float, default=30.0)
    parser.add_argument("--layout", default="b")
    args = parser.parse_args()
    cfg = terrain.terrain_config(args.layout)
    if args.where:
        print(where(args.where[0], args.where[1], cfg))
    if args.ground:
        print(ground_of(args.ground, cfg))
    if args.audit:
        print(audit(cfg))
    if args.suggest:
        print(suggest(args.suggest, cfg, args.height))
    if args.parallax:
        print(geometric_parallax(cfg))
    if not (args.where or args.ground or args.audit or args.suggest
            or args.parallax):
        parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

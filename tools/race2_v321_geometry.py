"""V32.1: expose the Race #2 raceway to the locked RB camera, by geometry only.

    python tools/race2_v321_geometry.py all          # every stage below, in order

    contacts    how high up the guard face the marbles actually lean
    sections    the five cross-sections, side by side
    build       one geometry.json per variant; asserts CONTROL reproduces V32
    joins       the run-join seam, in world units and in delivery pixels
    expose      the analytic rasteriser: deck coverage, lane width, occluders
    bands       the same three numbers, counted off the GPU's own segmentation
    contrast    every racer against the surface it stands on and against the room
    mechanism   the drum, sweep and pair against the broadened deck
    diagram     Part Q: picture | classes | collider-vs-render, per moment
    films       one full-motion film per variant, 1150 frames, no overlay
    compare     CONTROL beside each candidate, whole film and four sections

**Nothing here simulates, re-times or re-aims anything.** The replay and the RB
camera track are read, copied and never written; the only file any variant
differs in is `race2_switchyard_8.geometry.json`, and the only part of that file
a variant touches is the `rings` of the eleven channel runs. That is the whole
separation the brief's collision rule asks for, and it is a separation by *call
site*: `race2.export._run_rings` maps the section through
`race2.v321_section.transform`, and `sloped.track.TrackRun.local_colliders` -
which is what pybullet is handed - does not.

## The measurement that drives the pass

V31.1 found the cradle covering 0.000% of the frame on eight of thirteen
moments. `expose` says why, and it says it by rebuilding the renderer's own
picture: a z-buffered label pass over the same triangles in the same winding
with the same backface culling, which reports not only how much deck is on
screen but **what is standing in front of the deck that is not**.

The first build of that measurement cast rays and said the deck was visible at
every moment, which the renderer flatly contradicts. It was wrong for a reason
worth keeping: the channel is an open strip of single-sided triangles, so half
of every ring is neither drawn nor able to occlude, and which half depends on
where the camera is. A ray test against a channel treated as solid is measuring
a tube that is never rendered.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import shutil
import sys
from typing import Any, Sequence

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import numpy as np
from PIL import Image

from race2 import courses, v321_section
from race2.track import capped_profile
from sloped import layout
from sloped.scale import SIM_TO_LAYOUT

COURSE = "switchyard"
SEED = 8
SOURCE = "output/race2/v31_readability/RB"
OUT = "output/race2/v321_track_geometry"
DOCS = "docs/validation/race2/v321_track_geometry"
ENVIRONMENT = "contained_bay_v301"
TRACK_MATERIAL = "B"
DELIVERY = (1080, 1920)
PHONE = (270, 480)
MARBLE_RADIUS = 0.285          # layout units; `replay["units"]`

ORDER = ("CONTROL", "S", "A", "B", "C")

# The moments every sheet in this branch is measured on. The first thirteen are
# V31.1's own set, kept so its table and this one are the same instrument; the
# rest are the intervals the brief names - 6-14 s route continuity, the
# 8.0-8.5 s weak section, and the final sprint.
MOMENTS: tuple[tuple[str, float], ...] = (
    ("grid", 0.350), ("hook", 1.200), ("drop", 2.400), ("drum", 3.200),
    ("post_drum", 4.200), ("sweep", 5.200), ("chase", 6.800),
    ("bend", 7.600), ("weak_in", 8.000), ("switchback", 8.400),
    ("weak_out", 8.500), ("gorge", 9.600), ("sparse", 10.600),
    ("mid_bend", 11.400), ("late_mech", 12.200), ("sprint_in", 13.600),
    ("sprint_mid", 14.600), ("comeback", 15.400), ("line", 16.200),
    ("after", 17.000), ("runout", 18.000),
)

# `race2_track_surface.gd`'s band classes, as the classifier reads them back.
BANDS = {
    "cradle": (255, 0, 0),
    "lip": (255, 0, 255),
    "wall": (0, 255, 0),
    "crown": (0, 255, 255),
}
BACKGROUND = (0, 0, 0)


class GeometryError(RuntimeError):
    pass


# --- the camera, exactly as `race2_scene.gd` poses it -----------------------


class Camera:
    """One frame of the locked RB track, as a projection.

    `race2_scene._pose_camera` lerps position, aim and fov between the two rows
    that bracket a second, then calls `Camera3D.look_at(aim, Vector3.UP)`. This
    is that, in numpy, so a screen measurement can be made without a render -
    and `sightline --check` compares it against the renderer's own racer mask so
    the claim is tested rather than asserted.
    """

    def __init__(self, position, aim, fov_deg: float, size=DELIVERY):
        self.position = np.asarray(position, dtype=float)
        self.aim = np.asarray(aim, dtype=float)
        self.fov = float(fov_deg)
        self.size = size
        forward = self.aim - self.position
        forward /= max(np.linalg.norm(forward), 1e-9)
        z = -forward
        up = np.array([0.0, 1.0, 0.0])
        x = np.cross(up, z)
        x /= max(np.linalg.norm(x), 1e-9)
        y = np.cross(z, x)
        self.basis = np.stack([x, y, z])          # rows: camera axes in world
        self.forward = forward

    def to_camera(self, points) -> np.ndarray:
        p = np.atleast_2d(np.asarray(points, dtype=float)) - self.position
        return p @ self.basis.T

    def project(self, points) -> np.ndarray:
        """(x px, y px, depth) per point. Depth is positive in front."""
        cam = self.to_camera(points)
        depth = -cam[:, 2]
        width, height = self.size
        tan_half = math.tan(math.radians(self.fov) * 0.5)
        aspect = width / height
        safe = np.where(np.abs(depth) < 1e-9, 1e-9, depth)
        ndc_x = (cam[:, 0] / safe) / (tan_half * aspect)
        ndc_y = (cam[:, 1] / safe) / tan_half
        return np.stack([(ndc_x + 1.0) * 0.5 * width,
                         (1.0 - ndc_y) * 0.5 * height, depth], axis=1)


def camera_at(track: dict[str, Any], seconds: float, size=DELIVERY) -> Camera:
    cuts = track["cuts"]
    fps = float(track.get("fps", 60.0))
    half = 0.5 / fps
    index = len(cuts) - 1
    for i, cut in enumerate(cuts):
        if seconds <= float(cut["to"]):
            index = i
            break
    while index > 0:
        previous = cuts[index]["frames"]
        if not previous or seconds >= float(previous[0][0]) - half:
            break
        index -= 1
    rows = cuts[index]["frames"]
    first = float(rows[0][0])
    at = (min(max(seconds, first), float(rows[-1][0])) - first) * fps
    low = min(max(int(math.floor(at)), 0), len(rows) - 1)
    high = min(low + 1, len(rows) - 1)
    a, b = rows[low], rows[high]
    blend = min(max(at - low, 0.0), 1.0)

    def lerp3(i):
        return [a[i + k] + (b[i + k] - a[i + k]) * blend for k in range(3)]

    fov = a[7] + (b[7] - a[7]) * blend
    return Camera(lerp3(1), lerp3(4), fov, size)


def cut_of(track: dict[str, Any], seconds: float) -> str:
    for cut in track["cuts"]:
        if float(cut["from"]) <= seconds <= float(cut["to"]):
            return str(cut["name"])
    return str(track["cuts"][-1]["name"])


# --- the course, in render space -------------------------------------------


def _paths(source: str) -> tuple[str, str, str]:
    stem = os.path.join(source, f"race2_{COURSE}_{SEED}")
    out = (f"{stem}.geometry.json", f"{stem}.replay.json", f"{stem}.cameras.json")
    for path in out:
        if not os.path.isfile(path):
            raise GeometryError(f"missing {path}")
    return out


def load(source: str = SOURCE):
    geometry_path, replay_path, cameras_path = _paths(source)
    with open(geometry_path, encoding="utf-8") as handle:
        geometry = json.load(handle)
    with open(replay_path, encoding="utf-8") as handle:
        replay = json.load(handle)
    with open(cameras_path, encoding="utf-8") as handle:
        cameras = json.load(handle)
    return geometry, replay, cameras


def run_rings(geometry: dict[str, Any]) -> dict[str, np.ndarray]:
    """Every run's rings, in render (layout) space: (samples, columns, 3)."""
    out: dict[str, np.ndarray] = {}
    scale = float(geometry.get("units", {}).get("render_scale", SIM_TO_LAYOUT))
    for run in geometry["runs"]:
        width = int(run["section_points"])
        rings = np.asarray(run["rings"], dtype=float).reshape(-1, width, 3) * scale
        out[str(run["name"])] = rings
    return out


def triangles_of(rings: np.ndarray) -> np.ndarray:
    """The strip's triangles, same winding as `race2_scene._strip_mesh`."""
    a = rings[:-1, :-1]
    b = rings[1:, :-1]
    c = rings[:-1, 1:]
    d = rings[1:, 1:]
    first = np.stack([a, b, c], axis=-2).reshape(-1, 3, 3)
    second = np.stack([c, b, d], axis=-2).reshape(-1, 3, 3)
    return np.concatenate([first, second], axis=0)


def module_triangles(geometry: dict[str, Any]) -> np.ndarray:
    scale = float(geometry.get("units", {}).get("render_scale", SIM_TO_LAYOUT))
    out = []
    for module in geometry.get("modules", []):
        for mesh in module.get("meshes", []):
            v = np.asarray(mesh["v"], dtype=float).reshape(-1, 3) * scale
            i = np.asarray(mesh["i"], dtype=int).reshape(-1, 3)
            if len(i):
                out.append(v[i])
    return np.concatenate(out, axis=0) if out else np.zeros((0, 3, 3))


def rasterise(camera: Camera, rings: dict[str, np.ndarray], size,
              extra: np.ndarray | None = None,
              both: bool = False) -> dict[str, np.ndarray]:
    """A z-buffered label pass over the channel, with Godot's own culling.

    ## Why a rasteriser and not a ray test

    The first build of this measurement cast one ray per section point and
    reported that the deck was visible at every moment, which the renderer
    flatly contradicts: `--track=bands` counts **0.000%** deck on eight of the
    thirteen V31.1 moments. The ray test was not wrong about the rays. It was
    wrong about the surface: it treated the channel as solid, and the channel is
    an **open strip with single-sided triangles**. Half of every ring is
    backface-culled and therefore neither drawn nor able to occlude, and which
    half depends on the camera. A measurement that ignores that is measuring a
    tube the renderer never draws.

    So this walks the same triangles in the same winding `race2_scene._strip_mesh`
    emits, culls by the same screen-space sign, and z-buffers. Validated against
    the renderer in `tests/test_race2_v321_geometry.py` and by
    `expose --check`: on the sampled moments the cradle and lip coverages agree
    with Godot to within 0.005 of a per cent. The wall and crown split differs
    because a crown four pixels wide on the delivery frame is one pixel here and
    a point sample cannot be narrower than its pixel - their **sum** agrees, and
    the deck, which is the number this pass exists to move, is exact.

    `both` is `--faces=both`: the strip drawn double-sided, which is V32.1's
    fix. With it off, this reproduces V32.

    Returns `label` (0 none, 1 cradle, 2 lip, 3 wall, 4 crown, 5 racer),
    `depth`, `run` (1-based index into `rings`), and `deck_depth` - the depth of
    the nearest **deck** surface at that pixel whether it is drawn, culled or
    behind something, which is what makes "the deck is there and this is what is
    over it" measurable at all.
    """
    width, height = size
    depth = np.full((height, width), np.inf)
    label = np.zeros((height, width), dtype=np.int8)
    run_id = np.zeros((height, width), dtype=np.int16)
    deck_depth = np.full((height, width), np.inf)
    order = {name: index + 1 for index, name in enumerate(rings)}

    def draw(points: np.ndarray, klass: int, who: int, deck: bool) -> None:
        area = ((points[1, 0] - points[0, 0]) * (points[2, 1] - points[0, 1])
                - (points[2, 0] - points[0, 0]) * (points[1, 1] - points[0, 1]))
        if deck:
            _record_deck(points, area, deck_depth, width, height)
        if area <= 0.0 and not both:
            return
        if area == 0.0:
            return
        if area < 0.0:
            points = points[[0, 2, 1]]
            area = -area
        x0 = max(int(points[:, 0].min()), 0)
        x1 = min(int(points[:, 0].max()) + 2, width)
        y0 = max(int(points[:, 1].min()), 0)
        y1 = min(int(points[:, 1].max()) + 2, height)
        if x1 <= x0 or y1 <= y0:
            return
        gx, gy = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
        w1 = ((gx - points[0, 0]) * (points[2, 1] - points[0, 1])
              - (points[2, 0] - points[0, 0]) * (gy - points[0, 1])) / area
        w2 = ((points[1, 0] - points[0, 0]) * (gy - points[0, 1])
              - (gx - points[0, 0]) * (points[1, 1] - points[0, 1])) / area
        w0 = 1.0 - w1 - w2
        inside = (w0 >= 0.0) & (w1 >= 0.0) & (w2 >= 0.0)
        if not inside.any():
            return
        z = w0 * points[0, 2] + w1 * points[1, 2] + w2 * points[2, 2]
        window = depth[y0:y1, x0:x1]
        hit = inside & (z < window)
        window[hit] = z[hit]
        label[y0:y1, x0:x1][hit] = klass
        run_id[y0:y1, x0:x1][hit] = who

    for name, block in rings.items():
        samples, columns, _ = block.shape
        screen = camera.project(block.reshape(-1, 3)).reshape(samples, columns, 3)
        who = order[name]
        for s in range(samples - 1):
            for c in range(columns - 1):
                klass = _band_class(c, columns)
                deck = klass == 1
                for tri in (((s, c), (s + 1, c), (s, c + 1)),
                            ((s, c + 1), (s + 1, c), (s + 1, c + 1))):
                    points = np.array([screen[i, j] for i, j in tri])
                    if (points[:, 2] <= 0.05).any():
                        continue
                    draw(points, klass, who, deck)

    if extra is not None and len(extra):
        screen = camera.project(extra.reshape(-1, 3)).reshape(-1, 3, 3)
        for points in screen:
            if (points[:, 2] <= 0.05).any():
                continue
            draw(points, 5, 0, False)

    return {"label": label, "depth": depth, "run": run_id, "deck_depth": deck_depth}


def _record_deck(points: np.ndarray, area: float, deck_depth: np.ndarray,
                 width: int, height: int) -> None:
    """Where a deck surface is, culled or not - the denominator of `over`.

    Written before the cull test on purpose. The first build recorded it after,
    so a deck triangle that was discarded for facing away never registered as
    existing, `hidden` was empty at every moment, and the instrument reported
    that nothing was in front of the deck at the exact moments the deck was
    entirely missing from the frame.
    """
    if area == 0.0:
        return
    if area < 0.0:
        points = points[[0, 2, 1]]
        area = -area
    x0 = max(int(points[:, 0].min()), 0)
    x1 = min(int(points[:, 0].max()) + 2, width)
    y0 = max(int(points[:, 1].min()), 0)
    y1 = min(int(points[:, 1].max()) + 2, height)
    if x1 <= x0 or y1 <= y0:
        return
    gx, gy = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
    w1 = ((gx - points[0, 0]) * (points[2, 1] - points[0, 1])
          - (points[2, 0] - points[0, 0]) * (gy - points[0, 1])) / area
    w2 = ((points[1, 0] - points[0, 0]) * (gy - points[0, 1])
          - (gx - points[0, 0]) * (points[1, 1] - points[0, 1])) / area
    w0 = 1.0 - w1 - w2
    inside = (w0 >= 0.0) & (w1 >= 0.0) & (w2 >= 0.0)
    if not inside.any():
        return
    z = w0 * points[0, 2] + w1 * points[1, 2] + w2 * points[2, 2]
    shelf = deck_depth[y0:y1, x0:x1]
    seen = inside & (z < shelf)
    shelf[seen] = z[seen]


def _band_class(column: int, columns: int) -> int:
    """`race2_track_surface.band_colour` for the quad starting at `column`.

    1 cradle, 2 lip, 3 wall, 4 crown - the same four the renderer paints.

    The `u` is the **texel centre**, `(column + 0.5) / (columns - 1)`, which is
    what a 20-texel NEAREST texture actually samples across that quad. Taking
    the quad's own edge instead put `1 - 18/20` at 0.09999999999999998 and threw
    the whole east crown into the wall class, which showed up as a 91:9 split in
    the renderer against 62:38 here - a bug found only because the two
    instruments were compared band by band rather than in total.
    """
    u = (column + 0.5) / (columns - 1)
    side = min(u, 1.0 - u)
    if side >= 0.30:
        return 1
    if side >= 0.25:
        return 2
    if side >= 0.10:
        return 3
    return 4


# --- where the racers are ---------------------------------------------------


def frame_at(replay: dict[str, Any], seconds: float) -> dict[str, Any]:
    fps = float(replay.get("replay_fps", 60))
    index = int(round(seconds * fps))
    frames = replay["frames"]
    return frames[min(max(index, 0), len(frames) - 1)]


def racers_at(replay: dict[str, Any], seconds: float) -> list[dict[str, Any]]:
    frame = frame_at(replay, seconds)
    out = []
    for marble in frame["marbles"]:
        point = np.asarray(marble["p"], dtype=float) * SIM_TO_LAYOUT
        out.append({"id": int(marble["id"]), "p": point, "in": str(marble.get("in", ""))})
    return out


def station_at(replay: dict[str, Any], rings: dict[str, np.ndarray],
               seconds: float, camera: Camera) -> tuple[str, int, np.ndarray]:
    """The run and sample the on-screen field is actually on.

    Not the leader and not the mean: the **median** of the racers that are both
    inside a channel run and in front of the camera. A field spread over two
    hairpins has a mean somewhere over the room between them, and a leader alone
    in the next corridor is not what the shot is looking at.
    """
    everyone = racers_at(replay, seconds)
    live = [r for r in everyone if r["in"] in rings]
    if live:
        depths = camera.to_camera([r["p"] for r in live])[:, 2]
        live = [r for r, d in zip(live, depths) if d < -0.5] or live
        names = [r["in"] for r in live]
        pick = max(set(names), key=names.count)
        centre = np.median(np.stack([r["p"] for r in live if r["in"] == pick]), axis=0)
    else:
        # Before the release the field is inside the start module, which is not
        # a run. The station is then the nearest channel sample to the field -
        # which is the head run's own mouth, and is what the grid shot frames.
        centre = np.median(np.stack([r["p"] for r in everyone]), axis=0)
        pick, best = None, None
        for name, block in rings.items():
            middle = block[:, block.shape[1] // 2, :]
            gap = float(np.min(np.linalg.norm(middle - centre, axis=1)))
            if best is None or gap < best:
                pick, best = name, gap
    ring = rings[pick]
    middle = ring[:, ring.shape[1] // 2, :]
    sample = int(np.argmin(np.linalg.norm(middle - centre, axis=1)))
    return pick, sample, centre


# --- subcommand: contacts ---------------------------------------------------


def _section_profile(scale: float):
    section = capped_profile(scale)
    right = section[len(section) // 2:]

    def rise(across: float) -> float:
        a = abs(across)
        if a >= right[-1][0]:
            return right[-1][1]
        for (a0, u0), (a1, u1) in zip(right, right[1:]):
            if a0 <= a <= a1:
                if a1 - a0 < 1e-12:
                    return u1
                return u0 + (u1 - u0) * (a - a0) / (a1 - a0)
        return right[0][1]

    return section, right, rise


def stage_contacts(args) -> dict[str, Any]:
    """Where on the section do marbles actually rest, and how high up the face?

    This is the number every variant is shaped around. Lowering a guard the
    marbles lean on would put a racer in mid-air; lowering one they never reach
    costs nothing. The answer is neither: they reach it, rarely, and about three
    quarters of the way up.
    """
    course = courses.build(COURSE)
    _geometry, replay, _cameras = load(args.source)
    section, right, rise = _section_profile(2.0)
    _west, east = v321_section.cradle_edges(section)
    edge_across, edge_up = section[east]
    face_top = max(u for _a, u in section)
    face = face_top - edge_up

    frames = {name: [(run.sim_path[i], *run.frames[i], run.widths[i])
                     for i in range(len(run.path))]
              for name, run in course.runs.items()}

    grid = np.arange(-right[-1][0], right[-1][0] + 1e-9, 0.004)
    grid_rise = np.array([rise(a) for a in grid])

    bins = 26
    touch = [0] * bins
    highest = -9.0
    highest_at = None
    on_face = 0
    total = 0
    skipped = 0
    heights: list[float] = []
    for frame in replay["frames"]:
        if frame["t"] > 19.2:
            break
        for marble in frame["marbles"]:
            where = str(marble.get("in", ""))
            if where not in frames:
                continue
            rows = frames[where]
            p = np.asarray(marble["p"], dtype=float)
            best = None
            for c, lat, up, fwd, width in rows:
                d = p - np.asarray(c)
                ahead = float(d @ np.asarray(fwd))
                radial = float(d @ d) - ahead * ahead
                if best is None or radial < best[0]:
                    best = (radial, float(d @ np.asarray(lat)),
                            float(d @ np.asarray(up)), width)
            _r, lateral, vertical, width = best
            across = lateral * SIM_TO_LAYOUT / max(width, 1e-9)
            up_value = vertical * SIM_TO_LAYOUT
            if abs(across) > right[-1][0] + 0.2:
                skipped += 1
                continue
            total += 1
            across = float(np.clip(across, -right[-1][0], right[-1][0]))
            gap = float(np.min(np.hypot(grid - across, grid_rise - up_value)))
            resting = gap <= MARBLE_RADIUS * 1.06
            slot = min(bins - 1, int(abs(across) / right[-1][0] * bins))
            if resting:
                touch[slot] += 1
            if resting and abs(across) > edge_across:
                on_face += 1
                height = (up_value - edge_up) / face
                heights.append(height)
                if height > highest:
                    highest = height
                    highest_at = (frame["t"], int(marble["id"]), where, across, up_value)

    heights.sort()

    def pct(q: float) -> float:
        if not heights:
            return 0.0
        return heights[min(len(heights) - 1, int(q * len(heights)))]

    report = {
        "marble_frames": total,
        "skipped_outside_section": skipped,
        "resting_on_face": on_face,
        "face_share": on_face / max(total, 1),
        "face_height": face,
        "cradle_half": edge_across,
        "highest_contact_fraction": highest,
        "highest_contact": None if highest_at is None else {
            "t": highest_at[0], "marble": highest_at[1], "run": highest_at[2],
            "across": highest_at[3], "up": highest_at[4],
        },
        "p50": pct(0.50), "p90": pct(0.90), "p99": pct(0.99),
        "bins": [
            {"lo": right[-1][0] * b / bins, "hi": right[-1][0] * (b + 1) / bins,
             "rest": touch[b]}
            for b in range(bins)
        ],
    }
    print(f"marble-frames inside a run   {total}  ({skipped} skipped outside the section)")
    print(f"resting on the lip or face   {on_face}  ({on_face / max(total,1) * 100:.2f}%)")
    print(f"face height above the cradle edge  {face:.4f} layout")
    print(f"highest contact              {highest:.3f} of the face"
          f"  = {highest * face:.4f} layout")
    if highest_at:
        print(f"  t={highest_at[0]:.3f} m{highest_at[1]} {highest_at[2]}"
              f" across={highest_at[3]:.3f} up={highest_at[4]:+.3f}")
    print(f"face contacts p50/p90/p99    {pct(0.5):.3f} / {pct(0.9):.3f} / {pct(0.99):.3f}")
    print(f"v321_section.LOAD_BEARING    {v321_section.LOAD_BEARING:.3f}"
          f"   {'>= measured' if v321_section.LOAD_BEARING >= highest - 1e-9 else 'BELOW MEASURED'}")
    _write(os.path.join(args.docs, "contacts.json"), report)
    return report


# --- subcommand: sections ---------------------------------------------------


def stage_sections(args) -> dict[str, Any]:
    section = capped_profile(2.0)
    rows = {}
    print(f"{'variant':9s} {'face_h':>7s} {'drop':>7s} {'run':>7s} {'angle':>6s} "
          f"{'half':>7s} {'shelf':>7s}  note")
    control = v321_section.describe("CONTROL", section)
    for name in ORDER:
        data = v321_section.describe(name, section)
        points = v321_section.transform(name, section)
        data["points_xy"] = [[round(a, 5), round(u, 5)] for a, u in points]
        data["shelf"] = data["section_half"] - control["section_half"]
        data["drop"] = control["face_height"] - data["face_height"]
        rows[name] = data
        print(f"{name:9s} {data['face_height']:7.4f} {data['drop']:7.4f} "
              f"{data['face_run']:7.4f} {data['face_angle_deg']:6.1f} "
              f"{data['section_half']:7.4f} {data['shelf']:7.4f}  "
              f"{v321_section.VARIANTS[name]['note']}")
    _write(os.path.join(args.docs, "sections.json"), rows)
    return rows


# --- subcommand: build ------------------------------------------------------


def stage_build(args) -> dict[str, Any]:
    """One input set per variant. Replay and cameras are copied, never written."""
    from race2 import export

    geometry_path, replay_path, cameras_path = _paths(args.source)
    course = courses.build(COURSE)
    digests: dict[str, Any] = {}
    for name in ORDER:
        target = os.path.join(args.out, name)
        os.makedirs(target, exist_ok=True)
        stem = os.path.join(target, f"race2_{COURSE}_{SEED}")
        for source, suffix in ((replay_path, "replay"), (cameras_path, "cameras")):
            shutil.copyfile(source, f"{stem}.{suffix}.json")
        os.environ["RACE2_RENDER_SECTION"] = "" if name == "CONTROL" else name
        os.environ["RACE2_RENDER_WELD"] = "1" if v321_section.WELD[name] else "0"
        export.write_geometry(course, f"{stem}.geometry.json")
        os.environ.pop("RACE2_RENDER_SECTION", None)
        os.environ.pop("RACE2_RENDER_WELD", None)
        digests[name] = {
            "geometry": _sha(f"{stem}.geometry.json"),
            "replay": _sha(f"{stem}.replay.json"),
            "cameras": _sha(f"{stem}.cameras.json"),
        }
    base = {
        "geometry": _sha(geometry_path),
        "replay": _sha(replay_path),
        "cameras": _sha(cameras_path),
    }
    digests["_source"] = base
    same = digests["CONTROL"]["geometry"] == base["geometry"]
    digests["control_reproduces_v32_geometry"] = same
    for name in ORDER:
        row = digests[name]
        print(f"{name:9s} geometry {row['geometry'][:16]} "
              f"replay {row['replay'][:16]} cameras {row['cameras'][:16]}")
    print(f"source    geometry {base['geometry'][:16]} "
          f"replay {base['replay'][:16]} cameras {base['cameras'][:16]}")
    print(f"CONTROL reproduces the V32 geometry byte for byte: {same}")
    if not same:
        raise GeometryError(
            "CONTROL did not reproduce the shipped geometry - the identity "
            "path is not the identity"
        )
    _write(os.path.join(args.docs, "build.json"), digests)
    return digests


# --- subcommand: expose -----------------------------------------------------


EXPOSE_SIZE = (540, 960)


def stage_expose(args) -> dict[str, Any]:
    """Per moment, per variant: how much deck is on screen, and what is over it.

    Three numbers, and the third is the one the brief's Part A is really after:

    * **deck %** - the share of the frame the running surface covers. V31.1's
      own column, reproduced by a different instrument.
    * **lane px** - the widest *contiguous* run of deck on the screen row the
      racers are on, scaled to the delivery frame. A lane is a width, and a
      sliver of deck running away up the frame is one pixel on every row it
      crosses however many pixels it adds up to.
    * **over** - of the pixels where a deck surface exists but is not the
      nearest thing, which class is in front of it. That is the root cause as a
      number rather than as a diagnosis.
    """
    _g, replay, cameras = load(args.source)
    variants = args.only.split(",") if args.only else list(ORDER)
    rings = {}
    for name in variants:
        path = os.path.join(args.out, name, f"race2_{COURSE}_{SEED}.geometry.json")
        if not os.path.isfile(path):
            raise GeometryError(f"missing {path}; run `build` first")
        with open(path, encoding="utf-8") as handle:
            rings[name] = run_rings(json.load(handle))

    width, height = EXPOSE_SIZE
    to_delivery = DELIVERY[0] / width
    report: dict[str, Any] = {"moments": [], "summary": {}, "size": list(EXPOSE_SIZE)}
    head = f"{'moment':11s} {'t':>6s} {'run':8s}"
    for name in variants:
        head += f" | {name:^26s}"
    print(head)
    print(f"{'':11s} {'':6s} {'':8s}" + "".join(
        f" | {'deck%':>6s} {'lane':>5s} {'over':>11s}" for _ in variants))

    for label, seconds in MOMENTS:
        camera = camera_at(cameras, seconds, size=EXPOSE_SIZE)
        run_name, sample, _c = station_at(replay, rings[variants[0]], seconds, camera)
        racers = racers_at(replay, seconds)
        balls = _racer_triangles(racers, MARBLE_RADIUS)
        screen = camera.project([r["p"] for r in racers])
        live = screen[screen[:, 2] > 0.2]
        row = {
            "moment": label, "t": seconds, "run": run_name, "sample": sample,
            "cut": cut_of(cameras, seconds), "fov": camera.fov,
            "racer_row": float(np.median(live[:, 1])) if len(live) else None,
            "variants": {},
        }
        for name in variants:
            buffers = rasterise(camera, rings[name], EXPOSE_SIZE, extra=balls,
                                both=v321_section.FACES[name] == "both")
            row["variants"][name] = _expose_row(buffers, row["racer_row"],
                                                EXPOSE_SIZE, to_delivery)
        report["moments"].append(row)
        line = f"{label:11s} {seconds:6.2f} {run_name:8s}"
        for name in variants:
            e = row["variants"][name]
            line += (f" | {e['deck_pct']:6.3f} {e['lane_px']:5.0f} "
                     f"{e['over_top']:>11s}")
        print(line)

    print()
    print(f"{'variant':9s} {'deck%':>7s} {'lane px':>8s} {'lane/track':>11s} "
          f"{'deck/chan':>10s} {'moments lane>=40':>17s}")
    for name in variants:
        rows = [m["variants"][name] for m in report["moments"]]
        summary = {
            "deck_pct": float(np.mean([r["deck_pct"] for r in rows])),
            "lane_px": float(np.mean([r["lane_px"] for r in rows])),
            "lane_px_median": float(np.median([r["lane_px"] for r in rows])),
            "lane_ratio": float(np.mean([r["lane_ratio"] for r in rows])),
            "deck_share_of_channel": float(np.mean([r["deck_share"] for r in rows])),
            "moments_with_lane": int(sum(1 for r in rows if r["lane_px"] >= 40.0)),
            "moments": len(rows),
            "hidden_deck_pct": float(np.mean([r["hidden_pct"] for r in rows])),
        }
        report["summary"][name] = summary
        print(f"{name:9s} {summary['deck_pct']:7.3f} {summary['lane_px']:8.1f} "
              f"{summary['lane_ratio']:11.3f} "
              f"{summary['deck_share_of_channel']:10.3f} "
              f"{summary['moments_with_lane']:12d} / {summary['moments']}")
    _write(os.path.join(args.docs, "expose.json"), report)
    return report


def _racer_triangles(racers: Sequence[dict[str, Any]], radius: float) -> np.ndarray:
    """Each racer as an octahedron: an occluder, not a picture.

    A marble blocks the deck behind it, and a measurement that left the racers
    out would credit a variant with deck the viewer cannot see. Eight faces is
    within a few per cent of a sphere's silhouette at these sizes and costs
    nothing next to the channel's twenty-five thousand triangles. Both windings
    are emitted because an octahedron built this way is not consistently wound
    and a silhouette is not a surface anybody is measuring the facing of.
    """
    if not racers:
        return np.zeros((0, 3, 3))
    axes = np.array([[1.0, 0, 0], [-1.0, 0, 0], [0, 1.0, 0],
                     [0, -1.0, 0], [0, 0, 1.0], [0, 0, -1.0]]) * radius
    faces = [(0, 2, 4), (2, 1, 4), (1, 3, 4), (3, 0, 4),
             (2, 0, 5), (1, 2, 5), (3, 1, 5), (0, 3, 5)]
    out = []
    for racer in racers:
        points = racer["p"] + axes
        for a, b, c in faces:
            out.append([points[a], points[b], points[c]])
            out.append([points[a], points[c], points[b]])
    return np.asarray(out)


def _expose_row(buffers: dict[str, np.ndarray], racer_row, size,
                to_delivery: float) -> dict[str, Any]:
    width, height = size
    label = buffers["label"]
    total = width * height
    deck = label == 1
    channel = (label >= 1) & (label <= 4)
    exists = np.isfinite(buffers["deck_depth"])
    hidden = exists & ~deck
    names = {0: "none", 2: "lip", 3: "wall", 4: "crown", 5: "racer"}
    counts = {names[k]: int(((label == k) & hidden).sum()) for k in names}
    top = max(counts, key=counts.get) if hidden.any() else "-"
    share = counts.get(top, 0) / max(int(hidden.sum()), 1)
    lane = _lane_at({"cradle": deck, "lip": label == 2, "wall": label == 3,
                     "crown": label == 4}, racer_row, height)
    return {
        "deck_pct": float(deck.sum()) / total * 100.0,
        "channel_pct": float(channel.sum()) / total * 100.0,
        "deck_share": float(deck.sum()) / max(float(channel.sum()), 1.0),
        "hidden_pct": float(hidden.sum()) / total * 100.0,
        "over": counts,
        "over_top": f"{top} {share * 100:.0f}%",
        "lane_px": lane["lane_px"] * to_delivery,
        "track_px": lane["track_px"] * to_delivery,
        "lane_ratio": lane["lane_ratio"],
        "row": lane["row"],
    }


# --- subcommand: bands ------------------------------------------------------


def _classify(path: str) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    image = np.asarray(Image.open(path).convert("RGB")).astype(np.int16)
    masks = {}
    for name, colour in BANDS.items():
        target = np.asarray(colour, dtype=np.int16)
        distance = np.abs(image - target).sum(axis=2)
        masks[name] = distance
    stack = np.stack([masks[n] for n in BANDS], axis=0)
    winner = np.argmin(stack, axis=0)
    best = np.min(stack, axis=0)
    out = {}
    for index, name in enumerate(BANDS):
        out[name] = (winner == index) & (best < 170)
    return image, out


def render_bands(args, variant: str, mode: str, size=DELIVERY) -> str:
    """Drive Godot for one variant's sheet, and return its directory.

    `mode` is a `--track=` value, except `colour`, which is the production
    picture: material B, the variant's own faces, no segmentation.
    """
    out_dir = os.path.join(args.out, variant, mode + ("_phone" if size == PHONE else ""))
    os.makedirs(out_dir, exist_ok=True)
    if glob.glob(os.path.join(out_dir, "at_*.png")) and not args.rerender:
        return out_dir
    import subprocess
    command = [
        sys.executable, os.path.join(REPO, "tools", "race2_render.py"), "still",
        f"--course={COURSE}", f"--seed={SEED}",
        f"--out={os.path.join(args.out, variant)}",
        f"--frames={os.path.join(args.out, variant)}",
        f"--environment={ENVIRONMENT}",
        f"--track={TRACK_MATERIAL if mode == 'colour' else mode}",
        f"--faces={v321_section.FACES[variant]}",
        "--at=" + ",".join(f"{t:.3f}" for _n, t in MOMENTS),
    ]
    result = subprocess.run(command, cwd=REPO, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise GeometryError((result.stdout or "")[-3000:] + (result.stderr or "")[-2000:])
    made = os.path.join(args.out, variant, f"still_{COURSE}_{SEED}")
    for path in glob.glob(os.path.join(made, "at_*.png")):
        shutil.move(path, os.path.join(out_dir, os.path.basename(path)))
    return out_dir


def stage_bands(args) -> dict[str, Any]:
    """Pixel truth: what fraction of the frame is deck, and how wide is the lane.

    The coverage columns are V31.1's instrument unchanged, so its table and this
    one can be read against each other. The lane column is new and is what the
    brief's Part E asks for: the width of the **contiguous** run of cradle pixels
    on the screen row the racers are on, which is the number a viewer's "is there
    a road under them" is actually reading.
    """
    _g, replay, cameras = load(args.source)
    variants = args.only.split(",") if args.only else list(ORDER)
    base = os.path.join(args.out, variants[0], f"race2_{COURSE}_{SEED}.geometry.json")
    with open(base, encoding="utf-8") as handle:
        rings = run_rings(json.load(handle))

    report: dict[str, Any] = {"moments": [], "summary": {}}
    for variant in variants:
        render_bands(args, variant, "bands")

    print(f"{'moment':11s} {'t':>6s} " + " ".join(
        f"{v + ' cradle/lip/wall/crown  lane':>44s}" for v in variants))
    for label, seconds in MOMENTS:
        camera = camera_at(cameras, seconds)
        row: dict[str, Any] = {"moment": label, "t": seconds, "variants": {}}
        racers = [r for r in racers_at(replay, seconds) if r["in"] in rings]
        if racers:
            screen = camera.project([r["p"] for r in racers])
            live = screen[(screen[:, 2] > 0.2) & (screen[:, 0] > -200)
                          & (screen[:, 0] < DELIVERY[0] + 200)]
            row["racer_row"] = float(np.median(live[:, 1])) if len(live) else None
        else:
            row["racer_row"] = None
        for variant in variants:
            path = os.path.join(args.out, variant, "bands", f"at_{seconds:07.3f}.png")
            if not os.path.isfile(path):
                raise GeometryError(f"missing {path}")
            _image, masks = _classify(path)
            height, width = masks["cradle"].shape
            total = height * width
            entry = {n: float(masks[n].sum()) / total * 100.0 for n in BANDS}
            channel = sum(masks[n] for n in BANDS)
            entry["channel"] = float(channel.sum()) / total * 100.0
            entry["deck_share_of_channel"] = (
                float(masks["cradle"].sum()) / max(float(channel.sum()), 1.0))
            entry.update(_lane_at(masks, row["racer_row"], height))
            row["variants"][variant] = entry
        report["moments"].append(row)
        cells = []
        for variant in variants:
            e = row["variants"][variant]
            cells.append(f"{e['cradle']:5.3f} {e['lip']:5.3f} {e['wall']:5.3f} "
                         f"{e['crown']:5.3f} {e['lane_px']:6.1f} {e['lane_ratio']:5.2f}")
        print(f"{label:11s} {seconds:6.2f} " + " ".join(f"{c:>44s}" for c in cells))

    print()
    print(f"{'variant':9s} {'cradle%':>8s} {'deck/chan':>10s} {'lane px':>9s} "
          f"{'lane/track':>11s} {'moments w/ lane>=40px':>22s}")
    for variant in variants:
        rows = [m["variants"][variant] for m in report["moments"]]
        summary = {
            "cradle_pct": float(np.mean([r["cradle"] for r in rows])),
            "deck_share_of_channel": float(np.mean([r["deck_share_of_channel"] for r in rows])),
            "lane_px": float(np.mean([r["lane_px"] for r in rows])),
            "lane_ratio": float(np.mean([r["lane_ratio"] for r in rows])),
            "lane_px_median": float(np.median([r["lane_px"] for r in rows])),
            "moments_with_lane": int(sum(1 for r in rows if r["lane_px"] >= 40.0)),
            "moments": len(rows),
        }
        report["summary"][variant] = summary
        print(f"{variant:9s} {summary['cradle_pct']:8.3f} "
              f"{summary['deck_share_of_channel']:10.3f} {summary['lane_px']:9.1f} "
              f"{summary['lane_ratio']:11.3f} {summary['moments_with_lane']:16d} / "
              f"{summary['moments']}")
    _write(os.path.join(args.docs, "bands.json"), report)
    return report


def _lane_at(masks: dict[str, np.ndarray], racer_row: float | None,
             height: int) -> dict[str, float]:
    """The widest contiguous run of deck on the racers' own screen row.

    A row rather than a perpendicular section because a row is what a viewer's
    eye does at a glance, and because it is the one measure that cannot be
    inflated by a long thin sliver of deck running away up the frame: a sliver
    is one or two pixels on every row it crosses.
    """
    if racer_row is None:
        return {"lane_px": 0.0, "track_px": 0.0, "lane_ratio": 0.0, "row": -1.0}
    row = int(min(max(round(racer_row), 0), height - 1))
    band = 9
    lo = max(row - band, 0)
    hi = min(row + band + 1, height)
    best_lane = 0.0
    best_track = 0.0
    for y in range(lo, hi):
        deck = masks["cradle"][y]
        channel = deck | masks["lip"][y] | masks["wall"][y] | masks["crown"][y]
        best_lane = max(best_lane, _longest_run(deck))
        best_track = max(best_track, _longest_run(channel))
    return {
        "lane_px": float(best_lane),
        "track_px": float(best_track),
        "lane_ratio": float(best_lane) / max(float(best_track), 1.0),
        "row": float(row),
    }


def _longest_run(mask: np.ndarray) -> int:
    if not mask.any():
        return 0
    padded = np.concatenate([[0], mask.astype(np.int8), [0]])
    edges = np.diff(padded)
    starts = np.nonzero(edges == 1)[0]
    ends = np.nonzero(edges == -1)[0]
    # One gap of up to three pixels is bridged: MSAA against a racer silhouette
    # punches single-pixel holes in a band that is plainly continuous, and a
    # measure that let a hole halve the answer would be measuring the anti-
    # aliasing rather than the lane.
    merged = []
    for start, end in zip(starts, ends):
        if merged and start - merged[-1][1] <= 3:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return max(end - start for start, end in merged)


# --- subcommand: contrast ---------------------------------------------------
#
# CIE L* and CIE76 dE over sRGB bytes, taken from `tools/race2_v311_track.py`
# rather than re-derived, so V31.1's racer-separation numbers and this pass's
# are the same instrument reporting on two different pictures.

_M = np.array([[0.4124, 0.3576, 0.1805],
               [0.2126, 0.7152, 0.0722],
               [0.0193, 0.1192, 0.9505]])
_WHITE = np.array([0.95047, 1.0, 1.08883])


def _linear(px: np.ndarray) -> np.ndarray:
    p = np.asarray(px, dtype=np.float64) / 255.0
    return np.where(p <= 0.04045, p / 12.92, ((p + 0.055) / 1.055) ** 2.4)


def _f(t: np.ndarray) -> np.ndarray:
    return np.where(t > 0.008856, np.cbrt(t), 7.787 * t + 16.0 / 116.0)


def lab(px: np.ndarray) -> np.ndarray:
    xyz = _linear(px) @ _M.T / _WHITE
    fx, fy, fz = _f(xyz[..., 0]), _f(xyz[..., 1]), _f(xyz[..., 2])
    return np.stack([116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)], axis=-1)


def _exact(image: np.ndarray, colour) -> np.ndarray:
    return np.all(image == np.array(colour, dtype=np.uint8), axis=2)


def stage_contrast(args) -> dict[str, Any]:
    """Part I: a broader deck must not cost the racers.

    Three renders per moment per variant - the colour frame, the scene mask and
    the per-racer labels - and one number that can fail the pass: **the weakest
    individual racer's CIE76 dE against the surface it is standing on.** Per
    racer and not per cluster, because V31.1 already found that clustering the
    racer pixels on a sparse frame splits one marble into four and returns a
    guard that cannot fail.
    """
    variants = args.only.split(",") if args.only else list(ORDER)
    for variant in variants:
        for mode in ("colour", "mask", "racers"):
            render_bands(args, variant, mode)

    report: dict[str, Any] = {"moments": [], "summary": {}}
    print(f"{'moment':11s} {'t':>6s} " + " ".join(
        f"{v + '  deckL  dE_deck dE_room':>26s}" for v in variants))
    for label, seconds in MOMENTS:
        row: dict[str, Any] = {"moment": label, "t": seconds, "variants": {}}
        for variant in variants:
            row["variants"][variant] = _contrast_row(args, variant, seconds)
        report["moments"].append(row)
        cells = []
        for variant in variants:
            e = row["variants"][variant]
            if not e or e.get("weakest_vs_deck") is None:
                cells.append(f"{_maybe(e.get('deck_L') if e else None):>6s} "
                             f"{'-':>7s} {'-':>7s}")
                continue
            cells.append(f"{_maybe(e['deck_L']):>6s} {e['weakest_vs_deck']:7.1f} "
                         f"{e['weakest_vs_room']:7.1f}")
        print(f"{label:11s} {seconds:6.2f} " + " ".join(f"{c:>26s}" for c in cells))

    print()
    print(f"{'variant':9s} {'deck L*':>8s} {'clip%':>7s} {'weakest dE deck':>16s} "
          f"{'weakest dE room':>16s} {'racers < 12 dE':>15s}")
    for variant in variants:
        rows = [m["variants"][variant] for m in report["moments"]]
        rows = [r for r in rows if r]
        if not rows:
            continue
        weak_deck = [r["weakest_vs_deck"] for r in rows if r["weakest_vs_deck"] is not None]
        weak_room = [r["weakest_vs_room"] for r in rows if r["weakest_vs_room"] is not None]
        summary = {
            "deck_L": float(np.mean([r["deck_L"] for r in rows if r["deck_L"]] or [0.0])),
            "deck_clip_pct": float(np.mean([r["deck_clip"] for r in rows])),
            "weakest_vs_deck": float(min(weak_deck)) if weak_deck else None,
            "median_weakest_vs_deck": float(np.median(weak_deck)) if weak_deck else None,
            "weakest_vs_room": float(min(weak_room)) if weak_room else None,
            "moments_below_12": int(sum(1 for v in weak_deck if v < 12.0)),
            "moments": len(rows),
            "per_racer_worst": _worst_per_racer(rows),
        }
        report["summary"][variant] = summary
        print(f"{variant:9s} {summary['deck_L']:8.2f} {summary['deck_clip_pct']:7.3f} "
              f"{(summary['weakest_vs_deck'] or 0):16.2f} "
              f"{(summary['weakest_vs_room'] or 0):16.2f} "
              f"{summary['moments_below_12']:10d} / {summary['moments']}")
    _write(os.path.join(args.docs, "contrast.json"), report)
    return report


def _maybe(value) -> str:
    return "-" if value is None else f"{value:.1f}"


def _worst_per_racer(rows: Sequence[dict[str, Any]]) -> dict[str, float]:
    worst: dict[str, float] = {}
    for row in rows:
        for index, value in enumerate(row.get("vs_deck", [])):
            key = f"racer{index}"
            if key not in worst or value < worst[key]:
                worst[key] = value
    return worst


def _contrast_row(args, variant: str, seconds: float) -> dict[str, Any]:
    base = os.path.join(args.out, variant)
    colour = _open(os.path.join(base, "colour", f"at_{seconds:07.3f}.png"))
    scene = _open(os.path.join(base, "mask", f"at_{seconds:07.3f}.png"))
    band = _open(os.path.join(base, "bands", f"at_{seconds:07.3f}.png"))
    labels = _open(os.path.join(base, "racers", f"at_{seconds:07.3f}.png"))
    if colour is None or scene is None or band is None or labels is None:
        return {}
    deck = _exact(band, BANDS["cradle"])
    channel = deck.copy()
    for name in BANDS:
        channel |= _exact(band, BANDS[name])
    room = ~(scene.any(axis=2) | band.any(axis=2))
    out: dict[str, Any] = {
        "deck_px": int(deck.sum()),
        "deck_L": float(lab(colour[deck].mean(axis=0))[0]) if deck.sum() >= 40 else None,
        "deck_clip": float((colour[deck] >= 250).all(axis=1).mean() * 100.0)
                     if deck.sum() >= 40 else 0.0,
        "track_L": float(lab(colour[channel].mean(axis=0))[0]) if channel.sum() >= 40 else None,
        "room_L": float(lab(colour[room].mean(axis=0))[0]) if room.sum() >= 40 else None,
    }
    surface = deck if deck.sum() >= 400 else channel
    if surface.sum() < 40 or room.sum() < 40:
        return out
    surface_lab = lab(colour[surface].mean(axis=0))
    room_lab = lab(colour[room].mean(axis=0))
    flagged = labels[..., 1] > 200
    vs_deck, vs_room, sizes = [], [], []
    if flagged.any():
        levels = sorted(int(v) for v in np.unique(labels[..., 0][flagged]))
        for level in levels:
            mask = flagged & (labels[..., 0] == level)
            if int(mask.sum()) < 60:
                continue
            marble = lab(colour[mask].mean(axis=0))
            vs_deck.append(float(np.linalg.norm(marble - surface_lab)))
            vs_room.append(float(np.linalg.norm(marble - room_lab)))
            sizes.append(int(mask.sum()))
    out.update({
        "racers_seen": len(vs_deck),
        "racer_px": sizes,
        "vs_deck": [round(v, 2) for v in vs_deck],
        "vs_room": [round(v, 2) for v in vs_room],
        "weakest_vs_deck": min(vs_deck) if vs_deck else None,
        "weakest_vs_room": min(vs_room) if vs_room else None,
        "surface_is_deck": bool(deck.sum() >= 400),
    })
    return out


def _open(path: str):
    if not os.path.isfile(path):
        return None
    return np.asarray(Image.open(path).convert("RGB"))


# --- subcommand: mechanism --------------------------------------------------


SCENE_CLASSES = {
    "deck": (255, 0, 0), "rail": (0, 255, 0), "structure": (0, 0, 255),
    "station": (0, 255, 255), "actuator": (255, 0, 255), "racer": (255, 255, 0),
}


def stage_mechanism(args) -> dict[str, Any]:
    """Part J: the broad lane must support the mechanisms, not swallow them.

    Two ways a mechanism could be lost, and both are measured: it could be
    **covered** - fewer of its pixels reach the frame because a taller-looking
    track is in front of it - or it could be **flattened**, its colour pulled
    toward the surface behind it. The second is the one a brighter deck
    threatens, so it is the one reported per moment.

    The scene mask paints a station cyan and an actuator magenta, and those two
    together are what the viewer calls the drum, the sweep, the pair and the
    last mechanism. `structure` is the start and the finish housings, which are
    on screen only in the grid shot.
    """
    variants = args.only.split(",") if args.only else list(ORDER)
    for variant in variants:
        for mode in ("colour", "mask"):
            render_bands(args, variant, mode)

    report: dict[str, Any] = {"moments": [], "summary": {}}
    print(f"{'moment':11s} {'t':>6s} " + " ".join(
        f"{v + '  mech%   dE_deck':>20s}" for v in variants))
    for label, seconds in MOMENTS:
        row: dict[str, Any] = {"moment": label, "t": seconds, "variants": {}}
        for variant in variants:
            row["variants"][variant] = _mechanism_row(args, variant, seconds)
        report["moments"].append(row)
        cells = []
        for variant in variants:
            e = row["variants"][variant]
            cells.append(f"{e['mechanism_pct']:6.3f} {_maybe(e['vs_deck']):>9s}"
                         if e else "-")
        print(f"{label:11s} {seconds:6.2f} " + " ".join(f"{c:>20s}" for c in cells))

    print()
    print(f"{'variant':9s} {'mech%':>8s} {'mech L*':>8s} {'dE vs deck':>11s} "
          f"{'worst dE':>9s} {'moments on screen':>18s}")
    for variant in variants:
        rows = [m["variants"][variant] for m in report["moments"]
                if m["variants"][variant] and m["variants"][variant]["mechanism_pct"] > 0.05]
        if not rows:
            continue
        gaps = [r["vs_deck"] for r in rows if r["vs_deck"] is not None]
        summary = {
            "mechanism_pct": float(np.mean([r["mechanism_pct"] for r in rows])),
            "mechanism_L": float(np.mean([r["mechanism_L"] for r in rows
                                          if r["mechanism_L"] is not None])),
            "vs_deck": float(np.mean(gaps)) if gaps else None,
            "worst_vs_deck": float(min(gaps)) if gaps else None,
            "moments": len(rows),
        }
        report["summary"][variant] = summary
        print(f"{variant:9s} {summary['mechanism_pct']:8.3f} "
              f"{summary['mechanism_L']:8.2f} {(summary['vs_deck'] or 0):11.2f} "
              f"{(summary['worst_vs_deck'] or 0):9.2f} {summary['moments']:13d} / "
              f"{len(report['moments'])}")
    _write(os.path.join(args.docs, "mechanism.json"), report)
    return report


def _mechanism_row(args, variant: str, seconds: float) -> dict[str, Any]:
    base = os.path.join(args.out, variant)
    colour = _open(os.path.join(base, "colour", f"at_{seconds:07.3f}.png"))
    scene = _open(os.path.join(base, "mask", f"at_{seconds:07.3f}.png"))
    band = _open(os.path.join(base, "bands", f"at_{seconds:07.3f}.png"))
    if colour is None or scene is None or band is None:
        return {}
    mech = (_exact(scene, SCENE_CLASSES["station"])
            | _exact(scene, SCENE_CLASSES["actuator"]))
    deck = _exact(band, BANDS["cradle"])
    out: dict[str, Any] = {
        "mechanism_pct": float(mech.mean()) * 100.0,
        "mechanism_L": None, "deck_L": None, "vs_deck": None,
    }
    if mech.sum() >= 200:
        mech_lab = lab(colour[mech].mean(axis=0))
        out["mechanism_L"] = float(mech_lab[0])
        if deck.sum() >= 400:
            deck_lab = lab(colour[deck].mean(axis=0))
            out["deck_L"] = float(deck_lab[0])
            out["vs_deck"] = float(np.linalg.norm(mech_lab - deck_lab))
    return out


# --- subcommand: joins ------------------------------------------------------


def stage_joins(args) -> dict[str, Any]:
    """The seam the fix uncovered, in layout units and in delivery pixels.

    Consecutive runs never met. The collider has the same gap and always did -
    a marble crosses it inside one frame - and the picture had it too,
    invisibly, because with the running surface backfacing there was no surface
    for a hole to be a hole in. Drawing the deck turns each join into a black
    slash across the road, so this measures it two ways: the world gap between
    the two rings, and the widest on-screen separation between them from the
    production camera at each moment they are in frame.
    """
    _g, replay, cameras = load(args.source)
    variants = args.only.split(",") if args.only else list(ORDER)
    report: dict[str, Any] = {"variants": {}}
    print(f"{'variant':9s} {'weld':>5s} {'world gap max':>14s} {'mean':>8s} "
          f"{'screen px max':>14s} {'median':>8s} {'moments in frame':>17s}")
    for variant in variants:
        path = os.path.join(args.out, variant, f"race2_{COURSE}_{SEED}.geometry.json")
        with open(path, encoding="utf-8") as handle:
            geometry = json.load(handle)
        rings = run_rings(geometry)
        order = [str(run["name"]) for run in geometry["runs"]]
        world = []
        for near, far in zip(order, order[1:]):
            a, b = rings[near], rings[far]
            world.append(max(float(np.linalg.norm(a[-1][k] - b[0][k]))
                             for k in range(a.shape[1])))
        widest, seen = [], 0
        for _label, seconds in MOMENTS:
            camera = camera_at(cameras, seconds)
            best = 0.0
            for near, far in zip(order, order[1:]):
                a = camera.project(rings[near][-1])
                b = camera.project(rings[far][0])
                live = ((a[:, 2] > 0.2) & (b[:, 2] > 0.2) & (a[:, 0] > 0)
                        & (a[:, 0] < DELIVERY[0]) & (a[:, 1] > 0)
                        & (a[:, 1] < DELIVERY[1]))
                if not live.any():
                    continue
                best = max(best, float(np.max(np.linalg.norm(
                    a[live, :2] - b[live, :2], axis=1))))
            if best > 0.0:
                seen += 1
                widest.append(best)
        row = {
            "weld": v321_section.WELD[variant],
            "world_gap_max": max(world) if world else 0.0,
            "world_gap_mean": float(np.mean(world)) if world else 0.0,
            "screen_px_max": max(widest) if widest else 0.0,
            "screen_px_median": float(np.median(widest)) if widest else 0.0,
            "moments_in_frame": seen,
            "moments": len(MOMENTS),
            "joins": len(world),
        }
        report["variants"][variant] = row
        print(f"{variant:9s} {str(row['weld']):>5s} {row['world_gap_max']:14.6f} "
              f"{row['world_gap_mean']:8.4f} {row['screen_px_max']:14.1f} "
              f"{row['screen_px_median']:8.1f} {seen:12d} / {len(MOMENTS)}")
    _write(os.path.join(args.docs, "joins.json"), report)
    return report


# --- subcommand: films ------------------------------------------------------


EXPORT = "exports/race2_v321_track_geometry"
FPS = 60
# `tools/race2_v32_short.py` renders its master with `--end=19.1500`, which is
# frames 0 to 1149 inclusive. The same number here, taken from the same place,
# so a candidate film and a comparison film are the same 1150 frames.
FILM_END = "19.1500"
FILM_FRAMES = 1150
CRF = 17
PRESET = "slow"


def _ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found is None:
        raise GeometryError("ffmpeg is not on PATH")
    return found


def _run(command: Sequence[str], label: str) -> str:
    import subprocess
    result = subprocess.run(list(command), cwd=REPO, capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise GeometryError(f"{label} failed:\n"
                            + (result.stdout or "")[-2500:]
                            + (result.stderr or "")[-2500:])
    return result.stdout or ""


def clip_dir(args, variant: str) -> str:
    return os.path.join(args.out, variant, "frames", f"clip_{COURSE}_{SEED}")


def stage_films(args) -> dict[str, Any]:
    """One full-motion film per variant: every frame, no overlay, no omission.

    The same course, the same seed, the same replay, the same camera track and
    the same environment for all five - `build` has already asserted that the
    replay and camera files are byte-identical copies - so the only thing that
    can differ between two of these films is the channel's render geometry and
    whether its strip is drawn on one side or two.
    """
    variants = args.only.split(",") if args.only else list(ORDER)
    os.makedirs(EXPORT, exist_ok=True)
    out: dict[str, Any] = {}
    for variant in variants:
        target = clip_dir(args, variant)
        frames = sorted(glob.glob(os.path.join(target, "frame_*.png")))
        if len(frames) != FILM_FRAMES or args.rerender:
            print(f"  rendering {variant} ...")
            _run([
                sys.executable, os.path.join(REPO, "tools", "race2_render.py"),
                "clip", f"--course={COURSE}", f"--seed={SEED}",
                f"--out={os.path.join(args.out, variant)}",
                f"--frames={os.path.join(args.out, variant, 'frames')}",
                f"--environment={ENVIRONMENT}", f"--track={TRACK_MATERIAL}",
                f"--faces={v321_section.FACES[variant]}",
                f"--end={FILM_END}",
            ], f"clip {variant}")
            frames = sorted(glob.glob(os.path.join(target, "frame_*.png")))
        video = os.path.join(EXPORT, f"race2_{COURSE}_v321_{variant}.mp4")
        _encode(target, video)
        out[variant] = {"frames": len(frames), "video": video,
                        "bytes": os.path.getsize(video)}
        print(f"{variant:9s} {len(frames):5d} frames -> {video} "
              f"({os.path.getsize(video) / 1e6:.1f} MB)")
    _write(os.path.join(args.docs, "films.json"), out)
    return out


def _encode(frames: str, target: str, scale: str = "", fps: int = FPS) -> str:
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    first = sorted(glob.glob(os.path.join(frames, "frame_*.png")))
    if not first:
        raise GeometryError(f"no frames in {frames}")
    start = int(os.path.basename(first[0])[6:12])
    command = [_ffmpeg(), "-y", "-framerate", str(fps), "-start_number",
               str(start), "-i", os.path.join(frames, "frame_%06d.png")]
    if scale:
        command += ["-vf", scale]
    command += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", str(CRF),
                "-preset", PRESET, "-movflags", "+faststart", target]
    _run(command, f"encode {os.path.basename(target)}")
    return target


# --- subcommand: compare ----------------------------------------------------


# The four sections the brief asks to be able to read side by side, plus the
# whole film. Seconds, inclusive of the first and exclusive of the last.
SECTIONS = (
    ("full", 0.0, 19.1667),
    ("s03_06", 3.0, 6.0),
    ("s06_10", 6.0, 10.0),
    ("s10_14", 10.0, 14.0),
    ("sprint", 14.0, 19.1667),
)


def stage_compare(args) -> dict[str, Any]:
    """CONTROL beside every candidate, at delivery width and at phone width.

    A border between the panels rather than a hard join, because two pale
    ribbons meeting at a seam read as one ribbon, which is the exact perception
    this pass is trying to measure.
    """
    variants = [v for v in (args.only.split(",") if args.only else list(ORDER))
                if v != "CONTROL"]
    made: dict[str, Any] = {}
    for name, start, end in SECTIONS:
        for variant in variants:
            target = os.path.join(EXPORT, f"compare_{name}_CONTROL_{variant}.mp4")
            _pair(args, "CONTROL", variant, start, end, target, (540, 960))
            made[f"{name}:{variant}"] = target
            print(f"  {os.path.basename(target)}")
        quad = os.path.join(EXPORT, f"compare_{name}_quad.mp4")
        _quad(args, list(ORDER), start, end, quad)
        made[f"{name}:quad"] = quad
        print(f"  {os.path.basename(quad)}")
    phone = os.path.join(EXPORT, "compare_phone_270x480.mp4")
    _pair(args, "CONTROL", args.pick or "B", 0.0, 19.1667, phone, PHONE)
    made["phone"] = phone
    print(f"  {os.path.basename(phone)}")
    _write(os.path.join(args.docs, "compare.json"), made)
    return made


def _window(start: float, end: float) -> tuple[int, int]:
    return int(round(start * FPS)), int(round(end * FPS)) - 1


def _pair(args, left: str, right: str, start: float, end: float,
          target: str, size) -> str:
    first, last = _window(start, end)
    width, height = size
    half = width // 2
    filters = (
        f"[0:v]trim=start_frame={first}:end_frame={last + 1},setpts=PTS-STARTPTS,"
        f"scale={half - 1}:{height},pad={half}:{height}:0:0:0x000000[l];"
        f"[1:v]trim=start_frame={first}:end_frame={last + 1},setpts=PTS-STARTPTS,"
        f"scale={half - 1}:{height},pad={half}:{height}:1:0:0x000000[r];"
        f"[l][r]hstack=inputs=2[v]"
    )
    _run([_ffmpeg(), "-y",
          "-framerate", str(FPS), "-start_number", "0",
          "-i", os.path.join(clip_dir(args, left), "frame_%06d.png"),
          "-framerate", str(FPS), "-start_number", "0",
          "-i", os.path.join(clip_dir(args, right), "frame_%06d.png"),
          "-filter_complex", filters, "-map", "[v]",
          "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", str(CRF),
          "-preset", "medium", "-movflags", "+faststart", target],
         f"compare {left}|{right}")
    return target


def _quad(args, names: Sequence[str], start: float, end: float,
          target: str) -> str:
    first, last = _window(start, end)
    picks = list(names)[:4] if len(names) >= 4 else list(names)
    cell_w, cell_h = 480, 854
    inputs: list[str] = []
    filters = []
    for index, name in enumerate(picks):
        inputs += ["-framerate", str(FPS), "-start_number", "0",
                   "-i", os.path.join(clip_dir(args, name), "frame_%06d.png")]
        filters.append(
            f"[{index}:v]trim=start_frame={first}:end_frame={last + 1},"
            f"setpts=PTS-STARTPTS,scale={cell_w - 2}:{cell_h},"
            f"pad={cell_w}:{cell_h}:1:0:0x000000[v{index}]")
    filters.append("[v0][v1]hstack=inputs=2[top]")
    filters.append("[v2][v3]hstack=inputs=2[bottom]")
    filters.append("[top][bottom]vstack=inputs=2[v]")
    _run([_ffmpeg(), "-y", *inputs, "-filter_complex", ";".join(filters),
          "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
          "-crf", str(CRF), "-preset", "medium", "-movflags", "+faststart",
          target], "quad")
    return target


# --- subcommand: diagram ----------------------------------------------------
#
# Part Q. Diagnostic colour lives here and only here: the delivered film has
# none of it, which `qc` asserts by counting saturated pixels in the candidate.

DIAGRAM_COLOURS = {
    1: (232, 66, 66),      # cradle - the running surface
    2: (206, 84, 196),     # lip
    3: (86, 196, 120),     # wall face
    4: (94, 176, 236),     # crown
    5: (246, 208, 88),     # racer
}
COLLIDER_INK = (255, 96, 0)
RENDER_INK = (0, 226, 255)

DIAGRAM_AT = ("drum", "switchback", "sparse", "sprint_mid", "comeback")


def stage_diagram(args) -> dict[str, Any]:
    """The geometry sheet: what the viewer sees, what class it is, and where the
    collider is that the picture no longer traces.

    Three panels per moment per variant:

    1. the production picture
    2. the class map - deck, lip, wall, crown, racer - so "is that the road or
       the rail" is answered by a colour rather than by an opinion
    3. the same picture with the **collider's** cross-section drawn in orange
       and the **render's** in cyan, at the station the racers are on. Where the
       two coincide the line is one colour; where a variant has moved the
       picture off the collider, the gap is the separation, drawn to scale.
    """
    _g, replay, cameras = load(args.source)
    variants = args.only.split(",") if args.only else list(ORDER)
    moments = [(n, t) for n, t in MOMENTS if n in DIAGRAM_AT] or list(MOMENTS[:4])

    control_rings = None
    made = []
    for variant in variants:
        render_bands(args, variant, "colour")
        with open(os.path.join(args.out, variant,
                               f"race2_{COURSE}_{SEED}.geometry.json"),
                  encoding="utf-8") as handle:
            rings = run_rings(json.load(handle))
        if control_rings is None:
            with open(os.path.join(args.out, "CONTROL",
                                   f"race2_{COURSE}_{SEED}.geometry.json"),
                      encoding="utf-8") as handle:
                control_rings = run_rings(json.load(handle))
        for label, seconds in moments:
            target = os.path.join(args.out, "_diagram",
                                  f"{variant}_{label}.png")
            _diagram_tile(args, variant, label, seconds, rings, control_rings,
                          replay, cameras, target)
            made.append(target)
            print(f"  {os.path.relpath(target, args.out)}")

    sheet = os.path.join(args.docs, "geometry_diagnostic.png")
    _sheet(made, sheet, columns=len(moments))
    print(f"  wrote {sheet}")

    profile = os.path.join(args.docs, "cross_sections.png")
    _cross_section_plate(profile)
    print(f"  wrote {profile}")
    return {"tiles": made, "sheet": sheet, "sections": profile}


def _diagram_tile(args, variant: str, label: str, seconds: float,
                  rings, control_rings, replay, cameras, target: str) -> None:
    from PIL import Image, ImageDraw

    size = (360, 640)
    colour_path = os.path.join(args.out, variant, "colour",
                               f"at_{seconds:07.3f}.png")
    picture = Image.open(colour_path).convert("RGB").resize(size, Image.LANCZOS)

    camera = camera_at(cameras, seconds, size=size)
    racers = racers_at(replay, seconds)
    buffers = rasterise(camera, rings, size,
                        extra=_racer_triangles(racers, MARBLE_RADIUS),
                        both=v321_section.FACES[variant] == "both")
    classes = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    classes[...] = (18, 18, 20)
    for value, ink in DIAGRAM_COLOURS.items():
        classes[buffers["label"] == value] = ink
    class_plate = Image.fromarray(classes)

    overlay = picture.copy()
    draw = ImageDraw.Draw(overlay)
    run_name, sample, _c = station_at(replay, control_rings, seconds, camera)
    for block, ink, width in ((control_rings[run_name], COLLIDER_INK, 3),
                              (rings[run_name], RENDER_INK, 2)):
        for step in (sample, min(sample + 6, len(block) - 1)):
            points = camera.project(block[step])
            draw.line([(float(x), float(y)) for x, y, _d in points],
                      fill=ink, width=width)

    plate = Image.new("RGB", (size[0] * 3 + 8, size[1] + 18), (10, 10, 12))
    for index, panel in enumerate((picture, class_plate, overlay)):
        plate.paste(panel, (index * (size[0] + 4), 18))
    ImageDraw.Draw(plate).text(
        (6, 4), f"{variant}  {label}  t={seconds:.2f}   "
                f"picture | classes | collider(orange) vs render(cyan)",
        fill=(225, 225, 230))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    plate.save(target)


def _cross_section_plate(target: str) -> None:
    """The four cross-sections, drawn to scale, one plate. PIL rather than a
    plotting library: `requirements.txt` declares Pillow and numpy and a pass
    that quietly imported a fifth dependency would be the defect V31 fixed."""
    from PIL import Image, ImageDraw

    section = capped_profile(2.0)
    width, height = 1100, 420
    pad = 46
    span = 2.9
    low, high = -0.62, 0.70
    plate = Image.new("RGB", (width, height), (16, 16, 18))
    draw = ImageDraw.Draw(plate)

    def place(a: float, u: float) -> tuple[float, float]:
        x = pad + (a + span) / (2 * span) * (width - 2 * pad)
        y = height - pad - (u - low) / (high - low) * (height - 2 * pad)
        return x, y

    draw.line([place(-span, 0.0), place(span, 0.0)], fill=(52, 52, 58))
    draw.line([place(0.0, low), place(0.0, high)], fill=(52, 52, 58))
    inks = {"CONTROL": (255, 255, 255), "S": (255, 255, 255),
            "A": (120, 210, 255), "B": (255, 190, 90), "C": (150, 240, 170)}
    order = ["CONTROL", "A", "B", "C"]
    for index, name in enumerate(order):
        points = v321_section.transform(name, section)
        draw.line([place(a, u) for a, u in points], fill=inks[name],
                  width=4 if name == "CONTROL" else 3)
        draw.text((pad + 8, 12 + index * 15),
                  f"{name}  face {v321_section.describe(name, section)['face_height']:.3f}"
                  f"  half {v321_section.describe(name, section)['section_half']:.3f}",
                  fill=inks[name])
    draw.text((width - 320, height - 26),
              "layout units, scale 2.0   S is CONTROL's section drawn both sides",
              fill=(150, 150, 158))
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    plate.save(target)


def _sheet(tiles, target: str, columns: int) -> str:
    """A grid of equal tiles, in the order they were made."""
    from PIL import Image
    if not tiles:
        raise GeometryError("nothing to sheet")
    plates = [Image.open(path).convert("RGB") for path in tiles]
    cell_w = max(p.width for p in plates)
    cell_h = max(p.height for p in plates)
    rows = (len(plates) + columns - 1) // columns
    sheet = Image.new("RGB", (cell_w * columns, cell_h * rows), (8, 8, 10))
    for index, plate in enumerate(plates):
        sheet.paste(plate, ((index % columns) * cell_w, (index // columns) * cell_h))
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    sheet.save(target)
    return target


# --- helpers ----------------------------------------------------------------


def _sha(path: str) -> str:
    import hashlib
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _write(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, default=float)
        handle.write("\n")
    print(f"  wrote {path}")


STAGES = {
    "compare": stage_compare,
    "joins": stage_joins,
    "mechanism": stage_mechanism,
    "diagram": stage_diagram,
    "contacts": stage_contacts,
    "films": stage_films,
    "contrast": stage_contrast,
    "sections": stage_sections,
    "build": stage_build,
    "expose": stage_expose,
    "bands": stage_bands,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=sorted(STAGES) + ["all"])
    parser.add_argument("--source", default=SOURCE)
    parser.add_argument("--out", default=OUT)
    parser.add_argument("--docs", default=DOCS)
    parser.add_argument("--only", default="")
    parser.add_argument("--rerender", action="store_true")
    parser.add_argument("--pick", default="")
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)
    os.makedirs(args.docs, exist_ok=True)
    names = sorted(STAGES) if args.stage == "all" else [args.stage]
    for name in ("contacts", "sections", "build", "joins", "expose",
                 "bands", "contrast", "mechanism", "diagram",
                 "films", "compare"):
        if name in names:
            print(f"=== {name} ===")
            STAGES[name](args)
            print()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GeometryError as error:
        print(f"race2 v321: {error}", file=sys.stderr)
        raise SystemExit(1)

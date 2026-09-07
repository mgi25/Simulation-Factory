"""The mountain, ported so a camera can be placed and checked without rendering.

`course_terrain.gd::height` is the only source of truth for the ground under
the sloped course, and two things a camera has to know are questions about it:

**Which side to stand on.** The layout proof already worked this out - "which
way a bearing swings is decided by the ground, not by its sign" - because the
track's own left is uphill on a leg running one way and downhill on the leg
running back, so a side-on bearing is a tracking shot on one and a camera
buried in the mountain on the next. It probes nine units to each side and takes
the lower.

**Whether the shot is clear.** Section 37 asks for a ray check or a visual one
on every production camera. With the terrain here it can be the ray: walk the
line from the camera to its aim point and confirm the ground is below it all
the way. That catches the failure the first camera pass had - a spinner-corridor
shot with the near hillside filling the bottom half of the frame - before
anything is rendered.

## The port

`height` is transcribed function for function: the flank's two grades, the
exponential crest above the start, the drifting terrace edges, the left rise,
the gorge, five noise octaves, the radial fade to the valley floor, the pads
and the bench cut. `index_cut` too, because the bench is the deepest feature
near the racing line and a camera one unit above the track is a camera inside
the bench without it.

The one place this needs care is `_lattice`. GDScript integers are 64-bit and
wrap; Python's are arbitrary precision. So the hash masks to 64 bits signed at
every step, and its shifts are arithmetic in both languages, which is what
makes the noise field identical rather than merely similar.
`tests/test_sloped_terrain.py` checks a grid of heights against values taken
from the running scene.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Sequence

from sloped import layout
from sloped.pathing import resample

__all__ = [
    "height",
    "index_cut",
    "terrain_config",
    "lower_side",
    "clearance",
    "sight_line_blocked",
]

_MASK = (1 << 64) - 1
_SIGN = 1 << 63


def _s64(value: int) -> int:
    value &= _MASK
    return value - (1 << 64) if value >= _SIGN else value


def _lattice(ix: int, iz: int, salt: int) -> float:
    n = _s64(_s64(ix * 73856093) ^ _s64(iz * 19349663) ^ _s64(salt * 83492791))
    n = _s64(_s64(n ^ (n >> 13)) * 1274126177)
    return ((n ^ (n >> 16)) & 0xFFFF) / 65536.0


def _smoothstep(edge0: float, edge1: float, value: float) -> float:
    if edge0 == edge1:
        return 0.0 if value < edge0 else 1.0
    t = min(1.0, max(0.0, (value - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def _noise(x: float, z: float, frequency: float, salt: int) -> float:
    fx = x * frequency
    fz = z * frequency
    ix = math.floor(fx)
    iz = math.floor(fz)
    tx = fx - ix
    tz = fz - iz
    tx = tx * tx * (3.0 - 2.0 * tx)
    tz = tz * tz * (3.0 - 2.0 * tz)
    a = _lattice(ix, iz, salt)
    b = _lattice(ix + 1, iz, salt)
    c = _lattice(ix, iz + 1, salt)
    d = _lattice(ix + 1, iz + 1, salt)
    return (
        (a + (b - a) * tx) + ((c + (d - c) * tx) - (a + (b - a) * tx)) * tz
    ) * 2.0 - 1.0


def terrain_config(runs: dict[str, Any] | None = None) -> dict[str, Any]:
    """Layout B's terrain table, with the bench index already built.

    The centreline the bench is cut from is the concatenation of **all seven**
    runs' paths, in the layout table's order, resampled to a third of its own
    point count - because that is what `course_machine.build` hands
    `index_cut`, and it hands it every run whether or not the physics races it.
    Cutting from five runs instead would move the bench under the two branch
    lobes and put every camera near them a couple of units out.

    ## Why the runs are always the *drawn* ones

    `runs` is accepted and deliberately not used for the cut. The scene builds
    its bench from the layout table, and the raced build's `blue` is not the
    layout's `blue`: `joins.blue_controls` enters the lobe at its second
    authored control so the join has room for its turn radius, which makes the
    raced lobe a shorter curve over the same corridor. It lies on the drawn
    ribbon to within 0.064 layout units - a ninth of a marble radius - but its
    118 samples sit at different arc positions, and a bench indexed from those
    samples is a slightly different bench. Measured against the scene's own
    dump, cutting from the raced runs put the port 0.021 layout units out at
    its worst; cutting from the drawn ones puts it at 1.7e-5.

    0.021 would never have mattered against a sight margin of 0.6. It is fixed
    because "the port is exact" is a claim worth being able to make without a
    footnote, and because the next thing to consult this will not necessarily
    have a 0.6-unit tolerance.
    """
    from sloped.track import TrackRun

    cfg: dict[str, Any] = {
        "top_y": layout.TERRAIN["top_y"],
        "z_top": layout.TERRAIN["z_top"],
        "grade": layout.TERRAIN["grade"],
        "steps": [list(step) for step in layout.TERRAIN["steps"]],
        "left_at": layout.TERRAIN["left_at"],
        "left_span": layout.TERRAIN["left_span"],
        "left_rise": layout.TERRAIN["left_rise"],
        "gorge_at": layout.TERRAIN["gorge_at"],
        "gorge_span": layout.TERRAIN["gorge_span"],
        "gorge_depth": layout.TERRAIN["gorge_depth"],
        "crest_rise": 5.5,
        "crest_scale": 24.0,
        "centre_x": 1.0,
        "centre_z": 6.0,
        "edge_from": 58.0,
        "edge_to": 94.0,
        "edge_y": -82.0,
        "noise": 2.3,
        "pads": [list(pad) for pad in layout.TERRAIN["pads"]],
        "cut_depth": 2.8,
        "cut_inner": 3.2,
        "cut_reach": 8.0,
    }
    centreline: list[tuple[float, float, float]] = []
    for name in layout.run_names():
        centreline.extend(TrackRun(name).path)
    index_cut(cfg, resample(centreline, max(len(centreline) // 3, 8)))
    return cfg


def index_cut(cfg: dict[str, Any], centreline: Sequence[Sequence[float]]) -> None:
    reach = float(cfg.get("cut_reach", 9.0))
    buckets: dict[tuple[int, int], list[tuple[float, float, float]]] = {}
    for point in centreline:
        key = (math.floor(point[0] / reach), math.floor(point[2] / reach))
        buckets.setdefault(key, []).append(tuple(float(v) for v in point))
    cfg["cut_index"] = buckets
    cfg["cut_reach"] = reach
    cfg["cut_inner"] = float(cfg.get("cut_inner", 3.4))
    cfg["cut_depth"] = float(cfg.get("cut_depth", 3.0))


def height(x: float, z: float, cfg: dict[str, Any], detail: bool = True) -> float:
    """Ground level under (x, z), in layout units."""
    run = z - float(cfg["z_top"])
    h = float(cfg["top_y"]) - run * float(cfg["grade"])
    if run < 0.0:
        rise = float(cfg.get("crest_rise", 15.0))
        scale = float(cfg.get("crest_scale", 30.0))
        h = float(cfg["top_y"]) + rise * (1.0 - math.exp(run / scale))

    for step in cfg.get("steps", []):
        edge = float(step[0]) + _noise(x, float(step[0]), 0.014, 5) * 2.4
        h -= float(step[1]) * _smoothstep(edge - float(step[2]), edge + float(step[2]), z)

    left = min(1.0, max(0.0, (-x - float(cfg["left_at"])) / float(cfg["left_span"])))
    h += float(cfg["left_rise"]) * pow(left, 1.5)

    right = min(1.0, max(0.0, (x - float(cfg["gorge_at"])) / float(cfg["gorge_span"])))
    h -= float(cfg["gorge_depth"]) * pow(right, 1.4)

    amplitude = float(cfg.get("noise", 1.8)) if detail else 0.0
    h += _noise(x, z, 0.0085, 3) * amplitude * 3.4
    h += _noise(x, z, 0.031, 7) * amplitude
    h += _noise(x, z, 0.098, 23) * amplitude * 0.55
    h += _noise(x, z, 0.240, 41) * amplitude * 0.24
    h += _noise(x, z, 0.520, 59) * amplitude * 0.10

    reach_from = float(cfg.get("edge_from", 66.0))
    reach_to = float(cfg.get("edge_to", 104.0))
    radial = math.hypot(x - float(cfg.get("centre_x", 0.0)), z - float(cfg.get("centre_z", 0.0)))
    fade = _smoothstep(reach_from, reach_to, radial)
    if fade > 0.0:
        h = h + (float(cfg.get("edge_y", -74.0)) - h) * fade

    for pad in cfg.get("pads", []):
        distance = math.hypot(x - float(pad[0]), z - float(pad[1]))
        blend = 1.0 - _smoothstep(float(pad[2]), float(pad[2]) + float(pad[3]), distance)
        h = h + (float(pad[4]) - h) * blend

    cut = cfg.get("cut_index") or {}
    if cut:
        reach = float(cfg["cut_reach"])
        inner = float(cfg["cut_inner"])
        depth = float(cfg["cut_depth"])
        gx = math.floor(x / reach)
        gz = math.floor(z / reach)
        nearest = reach
        nearest_y = 0.0
        for ox in (-1, 0, 1):
            for oz in (-1, 0, 1):
                for point in cut.get((gx + ox, gz + oz), ()):
                    d = math.hypot(x - point[0], z - point[2])
                    if d < nearest:
                        nearest = d
                        nearest_y = point[1]
        if nearest < reach:
            blend = 1.0 - _smoothstep(inner, reach, nearest)
            h = min(h, h + (nearest_y - depth - h) * blend)
    return h


# --- what a camera asks it ------------------------------------------------

PROBE = 9.0


def lower_side(point, forward, cfg: dict[str, Any], probe: float = PROBE):
    """The track's own side that stands over lower ground, as a unit vector.

    `course_scene.gd::_aim_of`'s rule, transcribed: the open side is the side
    with the view, and it is also the side that is not inside the hill.
    """
    side = (forward[2], 0.0, -forward[0])
    length = math.hypot(side[0], side[2])
    if length < 1e-9:
        side = (1.0, 0.0, 0.0)
        length = 1.0
    side = (side[0] / length, 0.0, side[2] / length)
    left = (point[0] + side[0] * probe, point[2] + side[2] * probe)
    right = (point[0] - side[0] * probe, point[2] - side[2] * probe)
    if height(left[0], left[1], cfg) > height(right[0], right[1], cfg):
        side = (-side[0], 0.0, -side[2])
    return side


def clearance(camera, aim, cfg: dict[str, Any], samples: int = 24) -> float:
    """The least height the sight line stands above the ground, in layout units.

    Negative means the terrain crosses the line: the shot is looking through
    the mountain. Sampled rather than solved because the surface has five noise
    octaves and a bench cut in it and there is nothing to solve.
    """
    worst = math.inf
    for step in range(samples + 1):
        t = step / samples
        x = camera[0] + (aim[0] - camera[0]) * t
        y = camera[1] + (aim[1] - camera[1]) * t
        z = camera[2] + (aim[2] - camera[2]) * t
        worst = min(worst, y - height(x, z, cfg))
    return worst


def sight_line_blocked(camera, aim, cfg: dict[str, Any], margin: float = 0.0) -> bool:
    return clearance(camera, aim, cfg) < margin

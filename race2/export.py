"""The built course, written out for the renderer.

## Why the renderer is fed geometry instead of building its own

Race #1 has two courses. `sloped.*` builds the one the physics runs on and
`godot/assets/marble_machine/course/*.gd` builds a visual twin of it, and
`docs/validation/sloped_course/physics_layout.json` exists to check that the two
agree. That is a defensible arrangement for a course transcribed from a drawn
asset - the drawing is the contract and both sides are transcriptions of it -
and it cost a whole module (`sloped.contract`) and a validation pass to keep
honest.

Race #2 has no drawing. Its geometry is *solved*, so a second hand-built copy
would not be a check on anything: it would be a second chance to be wrong. So
the renderer is handed the collider the physics actually used, and a
disagreement between what is simulated and what is photographed is not
possible rather than merely tested for.

## What is exported, and in what units

Everything is in **simulation units**, which is what the replay is in, and the
scene parents the whole course under one node scaled by `SIM_TO_LAYOUT` - the
same node the marbles hang from. One scale in one place: a missed multiply is a
course at the wrong size *and* in the wrong place, which is visible in the first
frame rather than subtly wrong in the twentieth.

Runs are exported as **rings** rather than as triangles. A `TrackRun`'s collider
is a strip sweep of its cross-section along its frames, so the rings are the
vertices and the triangles are implied; sending the rings is 45% of the bytes
and lets the scene generate its own normals and a sensible UV per run. Stations
are exported as raw vertices and indices, because a stud field and a paddle
shaft are not strips and are small.

Actuators are exported as their box half extents only. Their *poses* come from
the replay, frame by frame, which is the same route Race #1's wheels take and
the reason a blade in the film is at the angle the blade in the physics was.
"""

from __future__ import annotations

import json
import os
from typing import Any

from marble3d.mesh import TriMesh
from sloped.scale import SIM_TO_LAYOUT, to_sim_point
from sloped.track import ring_points

from race2 import v321_section
from race2.course import Course

__all__ = ["RENDER_SECTION", "RENDER_WELD", "course_geometry",
           "render_section", "render_weld", "write_geometry"]

PLACES = 4

# **The one place the picture may differ from the collider.**
#
# `_run_rings` below and `TrackRun.local_colliders` build the same rings from
# the same `section_at`, and this module's own docstring is the argument for
# that: a second hand-built copy would be a second chance to be wrong. V31.1
# then measured what it costs - the cradle covers 0.000% of the frame on eight
# of thirteen sampled moments, because the near guard stands 0.678 above it in
# 0.124 of lateral run and the RB camera looks along the channel rather than
# down into it.
#
# So V32.1 adds a **render-only** map over the cross-section, named by
# `$RACE2_RENDER_SECTION` and applied here and nowhere else. `local_colliders`
# cannot see it: it does not call this module. Empty or `CONTROL` is the
# identity and reproduces the shipped geometry file byte for byte, which is
# what `tools/race2_v321_geometry.py build` asserts before it renders anything.
#
# An environment variable rather than an argument for the reason
# `race2.track.WALL_CAP` gives for its own: every tool in this branch that
# writes a geometry file goes through `write_geometry(course, path)`, and a
# parameter threaded through all of them would be a parameter that four call
# sites could disagree about.
RENDER_SECTION = "RACE2_RENDER_SECTION"

# **The seam the fix uncovered, and the render-only weld that closes it.**
#
# Consecutive runs do not meet. Measured on the delivered course, the last ring
# of each run stands **0.051 to 0.077** simulation-scaled layout units from the
# first ring of the next at the centreline, and **0.11 to 0.23** at the section
# edges, because the bank and the width are still changing across the join. The
# collider has that gap too and always did - a marble crosses it in under a
# frame and never notices - and so did the picture, invisibly, because with the
# deck backfacing there was no surface for a hole to be a hole in.
#
# With the deck drawn, the join is a **black slash across the road**: 6.5 to
# 48.8 delivery pixels wide, on screen at 16 of the 21 sampled moments.
#
# `RACE2_RENDER_WELD=1` replaces each run's last ring with the next run's first
# ring, so the two strips share an edge instead of facing each other across a
# gap. It is longitudinal rather than lateral - no cross-section changes - and
# it is render-only for the same reason the sections are: `local_colliders`
# does not come through this module. The bridging quad it creates is 0.77 to
# 1.25 times the run's own sample step, so nothing is stretched and nothing
# folds; `tests/test_race2_v321_geometry.py` holds both bounds.
RENDER_WELD = "RACE2_RENDER_WELD"


def render_weld() -> bool:
    """Whether consecutive runs are welded in the render mesh."""
    return os.environ.get(RENDER_WELD, "").strip() not in ("", "0", "off", "false")


def render_section() -> str:
    """The render-only section variant in force, or `""` for the collider's own."""
    name = os.environ.get(RENDER_SECTION, "").strip()
    if not v321_section.known(name):
        raise ValueError(f"${RENDER_SECTION} names no variant: {name!r}")
    return "" if name == "CONTROL" else name


def _round(value: float) -> float:
    return round(float(value), PLACES)


def _mesh_json(mesh: TriMesh) -> dict[str, Any]:
    return {
        "v": [_round(v) for vertex in mesh.vertices for v in vertex],
        "i": list(mesh.indices),
    }


def _run_rings(run) -> list[list[float]]:
    """The strip rings the collider was swept from, flattened per ring.

    Rebuilt from the run's own `section_at` and `frames` rather than read back
    off the mesh: the mesh is the same points with the triangles already
    resolved, and going back to the source keeps the export honest if the strip
    builder ever changes the winding.
    """
    rings: list[list[float]] = []
    variant = render_section()
    for index in range(len(run.path)):
        # The same call `TrackRun.local_colliders` makes: the ring is built in
        # *layout* units - the path, the frames and the section are all layout -
        # and converted point by point afterwards. Building it from `sim_path`
        # with a layout section would put a 1.88-unit channel on a 3.3-unit
        # centreline, which is a course that looks right in plan and is a third
        # too narrow.
        section = run.section_at(index)
        if variant:
            section = v321_section.transform(variant, section)
        points = ring_points(
            run.path[index], run.frames[index], section, run.widths[index]
        )
        rings.append([_round(v) for point in points for v in to_sim_point(point)])
    return rings


def _weld(runs: list[dict[str, Any]]) -> None:
    """Each run's last ring, replaced by the next run's first ring.

    In place, over the runs in the order they are emitted - which is the order
    the stages put them in, and therefore the order a marble meets them. The
    join is only welded when the two rings are actually neighbours: the guard is
    that the next run's *first* ring is nearer to this run's last than its own
    last ring is, and that the two are within a quarter of a layout unit. A
    course whose stages were not a chain would fail both and be left alone.
    """
    for near, far in zip(runs, runs[1:]):
        a = near["rings"][-1]
        first, last = far["rings"][0], far["rings"][-1]
        middle = len(a) // 6 * 3
        def gap(other: list[float]) -> float:
            return sum((a[middle + k] - other[middle + k]) ** 2 for k in range(3)) ** 0.5
        if gap(first) > gap(last):
            continue
        if gap(first) > 0.25 / SIM_TO_LAYOUT:
            continue
        near["rings"][-1] = list(first)


def course_geometry(course: Course) -> dict[str, Any]:
    """Everything the scene needs to build this course."""
    runs: list[dict[str, Any]] = []
    for stage in course.stages:
        for name in stage.runs:
            run = course.runs[name]
            rings = _run_rings(run)
            runs.append(
                {
                    "name": name,
                    "stage": stage.name,
                    "role": stage.role,
                    "phase": course.phase_of(name),
                    "scale": run.scale,
                    "section_points": len(run.section_at(0)),
                    "samples": len(run.sim_path),
                    "rings": rings,
                    "path": [[_round(v) for v in point] for point in run.sim_path],
                    "banks": [_round(v) for v in run.banks],
                    "widths": [_round(v) for v in run.widths],
                    "clear_width": _round(run.clear_width),
                }
            )

    if render_weld():
        _weld(runs)

    modules: list[dict[str, Any]] = []
    actuators: list[dict[str, Any]] = []
    for module in course.machine:
        if module.id in course.runs:
            continue
        colliders = module.local_colliders()
        placed = module.transform
        entry: dict[str, Any] = {
            "id": module.id,
            "kind": type(module).__name__,
            "station": module.id in course.stations,
            "meshes": [_mesh_json(mesh.transformed(placed)) for mesh in colliders],
        }
        describe = module.describe()
        if isinstance(describe, dict):
            entry["describe"] = {
                k: v for k, v in describe.items()
                if isinstance(v, (int, float, str, bool, list))
            }
        modules.append(entry)
        for actuator in module.local_actuators():
            actuators.append(
                {
                    "key": f"{module.id}.{actuator.name}",
                    "module": module.id,
                    "name": actuator.name,
                    "half_extents": [_round(v) for v in actuator.half_extents],
                }
            )

    start = course.machine.modules.get("start")
    return {
        "course": course.concept or course.title,
        "title": course.title,
        "units": {
            "geometry": "simulation units",
            "render_scale": SIM_TO_LAYOUT,
            "note": "parent the whole course under one node scaled by render_scale",
        },
        "description": course.to_json(),
        "start": start.describe() if start is not None else {},
        "runs": runs,
        "modules": modules,
        "actuators": actuators,
    }


def write_geometry(course: Course, path: str) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    data = course_geometry(course)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, separators=(",", ":"))
        handle.write("\n")
    return path

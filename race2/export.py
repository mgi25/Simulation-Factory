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

from race2.course import Course

__all__ = ["course_geometry", "write_geometry"]

PLACES = 4


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
    for index in range(len(run.path)):
        # The same call `TrackRun.local_colliders` makes: the ring is built in
        # *layout* units - the path, the frames and the section are all layout -
        # and converted point by point afterwards. Building it from `sim_path`
        # with a layout section would put a 1.88-unit channel on a 3.3-unit
        # centreline, which is a course that looks right in plan and is a third
        # too narrow.
        points = ring_points(
            run.path[index], run.frames[index], run.section_at(index), run.widths[index]
        )
        rings.append([_round(v) for point in points for v in to_sim_point(point)])
    return rings


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

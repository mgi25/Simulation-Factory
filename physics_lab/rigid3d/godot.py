"""The Godot/Jolt cross-check: the other half of the architecture question.

PyBullet asks whether Python can own 3D physics. This asks what would be
gained by moving the authority *downstream* into Godot, where physics would
live below the replay it is supposed to produce. They are different proposals
and the report treats them as such.

Everything that could differ between engines is decided here and handed over
as data - the marble starts, the bowl as the exact flattened triangle soup
PyBullet was given, every coefficient, the world scale. Godot generates
nothing. That is what makes a difference in the results a difference in the
engine.

Godot is driven headless with its own project under `godot/physics_lab/`,
separate from `godot/` so that no production scene, material or project
setting is touched. It has to be a separate project rather than a flag,
because `physics/3d/physics_engine` is read at startup and cannot be set from
the command line.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import tempfile

from physics_lab.common.benchmark import RunSpec
from physics_lab.common.labreplay import FrameSample, LabEvent, LabRun, MarbleSample
from physics_lab.rigid3d.bullet import SCALED_MASS, WORLD_SCALE, damping_coefficient
from physics_lab.rigid3d.mesh import DEFAULT_RINGS, DEFAULT_SEGMENTS, build_bowl_mesh

__all__ = ["APPROACH", "GodotUnavailable", "find_godot", "simulate"]

APPROACH = "godot3d"

PROJECT = os.path.join("godot", "physics_lab")
SCRIPT = "bowl_bench.gd"

# Same order as `tools/render_replay.py`, deliberately: one way to find Godot
# in this repository, and no machine-specific path committed anywhere.
GODOT_ENV_VARS = ("GODOT_BIN", "GODOT4_BIN")
GODOT_ON_PATH = ("godot", "godot4", "Godot_v4.7.2-stable_win64.exe")


class GodotUnavailable(RuntimeError):
    """Godot is not installed, or the run did not produce a result."""


def find_godot(explicit: str | None = None) -> str:
    if explicit and os.path.isfile(explicit):
        return explicit
    for variable in GODOT_ENV_VARS:
        value = os.environ.get(variable)
        if value and os.path.isfile(value):
            return value
    for name in GODOT_ON_PATH:
        found = shutil.which(name)
        if found:
            return found
    raise GodotUnavailable(
        "cannot find Godot 4. Set $GODOT_BIN or put it on PATH. "
        "The Godot cross-check is optional; the rest of the lab does not need it."
    )


def simulate(
    spec: RunSpec,
    duration: float | None = None,
    godot: str | None = None,
    project_root: str | None = None,
) -> LabRun:
    """Run one bowl benchmark in Godot and read the result back."""
    benchmark = spec.benchmark
    if duration is not None:
        benchmark = benchmark.with_overrides(duration_limit=duration)
    executable = find_godot(godot)
    root = project_root or os.getcwd()
    project = os.path.join(root, PROJECT)
    if not os.path.isfile(os.path.join(project, "project.godot")):
        raise GodotUnavailable(f"no Godot project at {project}")

    mesh = build_bowl_mesh(
        benchmark.surface(),
        benchmark.drain_exit_y,
        rings=DEFAULT_RINGS,
        segments=DEFAULT_SEGMENTS,
    )
    # Flattened triangle soup - Godot's `ConcavePolygonShape3D.set_faces` wants
    # three vertices per triangle with no index buffer, so the indices are
    # expanded here rather than in GDScript.
    soup: list[float] = []
    for index in mesh.indices:
        soup.extend(mesh.vertices[index])

    payload = {
        "seed": spec.seed,
        "scale": WORLD_SCALE,
        "scaled_mass": SCALED_MASS,
        "damping": benchmark.linear_damping,
        # Jolt combines friction as sqrt(a*b), where Bullet multiplies. So the
        # numbers that produce the benchmark's two coefficients are different
        # in the two engines, and neither is the coefficient itself. Getting
        # this wrong is invisible: it just looks like the other engine has
        # more friction.
        "bowl_friction": benchmark.surface_friction**2 / benchmark.friction,
        "benchmark": json.loads(json.dumps(spec.to_json()["benchmark"])),
        "starts": spec.to_json()["starts"],
        "mesh": soup,
    }

    with tempfile.TemporaryDirectory() as scratch:
        spec_path = os.path.join(scratch, "spec.json")
        out_path = os.path.join(scratch, "run.json")
        with open(spec_path, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle)

        result = subprocess.run(
            [
                executable,
                "--headless",
                "--path", project,
                "--script", SCRIPT,
                "++",
                f"--spec={spec_path}",
                f"--out={out_path}",
            ],
            capture_output=True,
            text=True,
        )
        if not os.path.isfile(out_path):
            raise GodotUnavailable(
                "Godot produced no result.\n"
                f"exit {result.returncode}\n{result.stdout[-3000:]}\n{result.stderr[-3000:]}"
            )
        with open(out_path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)

    run = LabRun(
        approach=APPROACH,
        seed=spec.seed,
        physics_hz=benchmark.physics_hz,
        sample_hz=benchmark.sample_hz,
        benchmark=spec.to_json()["benchmark"],
        starts=spec.to_json()["starts"],
    )
    run.frames = [
        FrameSample(
            time=float(frame["time"]),
            marbles=tuple(
                MarbleSample(
                    marble_id=int(marble["id"]),
                    position=tuple(float(value) for value in marble["position"]),
                    velocity=tuple(float(value) for value in marble["velocity"]),
                    orientation=tuple(float(value) for value in marble["orientation"]),
                    spin=tuple(float(value) for value in marble["spin"]),
                    state=str(marble["state"]),
                )
                for marble in frame["marbles"]
            ),
        )
        for frame in raw["frames"]
    ]
    run.events = [
        LabEvent(
            time=float(event["time"]),
            kind=str(event["kind"]),
            data={key: value for key, value in event.items() if key not in ("time", "kind")},
        )
        for event in raw["events"]
    ]
    run.stats = {
        key: raw[key]
        for key in ("ticks", "sim_seconds", "failure", "engine", "godot_version",
                    "physics_engine", "drained", "escaped", "still_going")
        if key in raw
    }
    run.stats["collisions"] = sum(1 for event in run.events if event.kind == "collision")
    run.stats["mesh_triangles"] = mesh.triangle_count
    if not run.stats.get("failure"):
        run.stats["failure"] = None
    return run

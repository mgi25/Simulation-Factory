"""Plots, the comparison table, and the committed validation artifacts.

Reads the lab JSON that `tools/physics_lab_bench.py` wrote and produces what
sections 26, 27, 39 and 40 of the brief ask for: radius against time, energy
against time, one chart with every approach on it, and a small set of stills
and summaries light enough to commit.

The one chart worth singling out is the mean-radius comparison, because it
includes the **production** bowl. The neon replay's racers are converted into
bowl-relative radii - each racer's distance from `bowl_centre` over
`bowl_radius`, rescaled to this benchmark's rim - so the current architecture
appears on the same axes as the two prototypes. That normalisation is the only
fair way to put a course measured in canvas pixels beside a bowl measured in
metres, and what it shows is not a close call.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from physics_lab.analysis.metrics import measure, summarise  # noqa: E402
from physics_lab.analysis.plots import comparison_plot, energy_plot, radius_plot  # noqa: E402
from physics_lab.common.benchmark import load_benchmark  # noqa: E402
from physics_lab.common.labreplay import FrameSample, LabRun, MarbleSample, read_run  # noqa: E402

LAB_ROOT = os.path.join("output", "physics_lab")
VALIDATION = os.path.join("docs", "validation", "physics_lab")

# label -> (directory, file prefix). The calibrated runs, because those are the
# ones the comparison is drawn from.
SOURCES = {
    "Python 2.5D (calibrated)": ("surface25d_cal", "surface25d"),
    "PyBullet rigid 3D": ("rigid3d_cal", "rigid3d"),
    "Godot / Jolt rigid 3D": ("godot3d", "godot3d"),
}


def load(directory: str, prefix: str, seed: int) -> LabRun | None:
    path = os.path.join(LAB_ROOT, directory, f"{prefix}_seed{seed}.json")
    return read_run(path) if os.path.isfile(path) else None


def production_run(replay_path: str, benchmark) -> LabRun | None:
    """The neon replay, expressed as a bowl run so it can share the axes.

    Each racer's distance from the exported bowl centre, over the exported
    bowl radius, times this benchmark's rim radius. Height is not converted -
    the production simulation does not have one - so this is a radius series
    and nothing more, which is all the comparison chart uses.
    """
    if not os.path.isfile(replay_path):
        return None
    with open(replay_path, "r", encoding="utf-8") as handle:
        replay = json.load(handle)
    metadata = replay["course"]["metadata"]
    centre_x = float(metadata["bowl_centre_x"])
    centre_y = float(metadata["bowl_centre_y"])
    bowl_radius = float(metadata["bowl_radius"])
    rim = benchmark.rim_radius

    frames = []
    started = None
    for frame in replay["frames"]:
        inside = []
        for racer in frame["racers"]:
            dx = float(racer["x"]) - centre_x
            dy = float(racer["y"]) - centre_y
            rho = math.hypot(dx, dy) / bowl_radius
            if rho > 1.0:
                continue
            inside.append((int(racer["id"]), rho, math.atan2(dy, dx)))
        if not inside:
            if started is None:
                continue
            break
        if started is None:
            started = float(frame["t"]) if "t" in frame else len(frames) / float(replay["fps"])
        time = (float(frame.get("t", len(frames) / float(replay["fps"]))) - started)
        frames.append(
            FrameSample(
                time=max(0.0, time),
                marbles=tuple(
                    MarbleSample(
                        marble_id=racer_id,
                        position=(rho * rim * math.cos(angle), 0.0, rho * rim * math.sin(angle)),
                        velocity=(0.0, 0.0, 0.0),
                        orientation=(0.0, 0.0, 0.0, 1.0),
                        spin=(0.0, 0.0, 0.0),
                        state="surface",
                    )
                    for racer_id, rho, angle in inside
                ),
            )
        )
    if not frames:
        return None
    run = LabRun(
        approach="production2d",
        seed=int(replay.get("seed", 0)),
        physics_hz=int(replay.get("physics_hz", 120)),
        sample_hz=int(replay.get("fps", 60)),
        benchmark=json.loads(json.dumps(benchmark.__dict__, default=list)),
        starts=[],
    )
    run.frames = frames
    return run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--plots", default=os.path.join(LAB_ROOT, "plots"))
    parser.add_argument("--neon", default=os.path.join("output", "neon_v11", "neon_7.json"))
    parser.add_argument("--publish", action="store_true", help="copy artifacts into docs/validation")
    args = parser.parse_args(argv)

    benchmark = load_benchmark()
    os.makedirs(args.plots, exist_ok=True)

    runs: dict[str, LabRun] = {}
    for label, (directory, prefix) in SOURCES.items():
        run = load(directory, prefix, args.seed)
        if run is None:
            print(f"  (missing: {directory}/{prefix}_seed{args.seed}.json)")
            continue
        runs[label] = run
        slug = prefix
        radius_plot(run, os.path.join(args.plots, f"radius_{slug}_seed{args.seed}.png"),
                    f"{label}  seed {args.seed}: radius from the bowl axis")
        energy_plot(run, os.path.join(args.plots, f"energy_{slug}_seed{args.seed}.png"),
                    f"{label}  seed {args.seed}: mechanical energy per marble")
        print(f"  plotted {label}")

    combined = dict(runs)
    production = production_run(args.neon, benchmark)
    if production is not None:
        combined["Production 2D neon bowl"] = production
        print("  included the production neon bowl")
    comparison_plot(
        combined,
        os.path.join(args.plots, f"mean_radius_seed{args.seed}.png"),
        "Mean radius from the bowl axis - every approach, one set of axes",
    )

    table = {}
    for label, (directory, _) in SOURCES.items():
        path = os.path.join(LAB_ROOT, directory, "summary.json")
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as handle:
                table[label] = json.load(handle)
    with open(os.path.join(args.plots, "summaries.json"), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(table, handle, indent=2)
        handle.write("\n")

    if args.publish:
        os.makedirs(VALIDATION, exist_ok=True)
        for name in sorted(os.listdir(args.plots)):
            if name.endswith((".png", ".json")):
                shutil.copy2(os.path.join(args.plots, name), os.path.join(VALIDATION, name))
        for extra in ("calibration.json", "scaling.json", "production_bowl.json"):
            source = os.path.join(LAB_ROOT, extra)
            if os.path.isfile(source):
                shutil.copy2(source, os.path.join(VALIDATION, extra))
        determinism = os.path.join(LAB_ROOT, "determinism")
        if os.path.isdir(determinism):
            target = os.path.join(VALIDATION, "determinism")
            os.makedirs(target, exist_ok=True)
            for name in sorted(os.listdir(determinism)):
                shutil.copy2(os.path.join(determinism, name), os.path.join(target, name))
        print(f"-> published to {VALIDATION}")

    print(f"-> {args.plots}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

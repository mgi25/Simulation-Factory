"""What the finished V22 camera track is, measured, against V21's.

    python tools/sloped_v22_metrics.py --against v212

The prototypes each measured their own track. This measures the **integrated**
one, which is not the same document: the chase's phases now sit between V22's
bookends rather than V21's, the obstacle phase runs 0.850 s longer than anything
the chase prototype solved, and the finish is 0.867 s longer than anything at
all. Numbers carried over from a prototype report would be about a track that
was never rendered.

Everything here reads the solved tracks and the locked replay. Nothing renders,
nothing simulates and nothing is written except the report.

The preview is measured by its own instrument - `course_preview.path_report` -
because "is the flight smooth and does it show the course" is a different
question from "how big is a racer", and the preview has no racers in it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Sequence

sys.path.insert(0, os.getcwd())

from sloped import (
    cameras,
    chase_camera,
    course_preview,
    presentation,
    readability,
    sightlines,
    terrain,
    v22,
)
from sloped.course import sloped_course

OUT_DIR = os.path.join("output", "sloped_race_v1")
DOCS_DIR = os.path.join("docs", "validation", "sloped_race_v1", "v22_final")

# Which phase of the film each brief question is about, by cut name. The chase
# renamed the middle of the race, so a V21 cut and a V22 cut that cover the same
# stretch have different names and have to be paired by hand.
PAIRS = (
    ("opening / start", ("start",), ("start",)),
    ("first descent", ("descent", "long", "hairpin"), ("descent",)),
    ("obstacle", ("straight", "obstacle"), ("obstacle",)),
    ("fork", ("split",), ("fork",)),
    ("branches", ("branch",), ("branches",)),
    ("merge", ("merge",), ("merge",)),
    ("finish", ("finish",), ("finish",)),
)


def _pool(rows: Sequence[dict[str, Any]], names: Sequence[str], key: str,
          weight: str = "frames") -> float:
    """One figure for a group of cuts, weighted by how long each is on screen."""
    picked = [row for row in rows if row["cut"] in names and row.get(key) is not None]
    if not picked:
        return 0.0
    total = sum(float(row.get(weight, 1)) for row in picked) or 1.0
    return sum(float(row[key]) * float(row.get(weight, 1)) for row in picked) / total


def _load(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def report(seed: int, against: str = "v212") -> dict[str, Any]:
    replay = _load(os.path.join(OUT_DIR, f"race_{seed}.json"))
    machine = sloped_course(routes="both")
    cfg = terrain.terrain_config(machine.runs)
    bundle = sightlines.Bundle(
        sightlines.course_solids(machine, lambda x, z: terrain.height(x, z, cfg))
    )

    v22_track = _load(os.path.join(OUT_DIR, f"cameras_v22_{seed}.json"))
    preview = _load(os.path.join(OUT_DIR, f"preview_v22_{seed}.json"))
    old = cameras.build_track(
        replay, machine, fps=60, edit=cameras.EDITS[against]
    )

    out: dict[str, Any] = {"seed": seed, "against": against}

    # --- the shape of the film ---------------------------------------------
    prefix = v22.preview_prefix(preview)
    master = int(round(float(v22_track["duration"]) * 60)) + 1
    clock = presentation.Clock(
        tuple(
            (row["out"][0], row["out"][1], row["replay"][0], row["replay"][1])
            for row in v22_track["edit"]
        ),
        fps=60, master_frames=master, prefix=prefix,
    )
    out["film"] = {
        "preview_frames": v22.preview_frames(preview),
        "preview_seconds": round(prefix, 6),
        "hold_frames": clock.hold_frames,
        "race_frames": master,
        "frames": clock.frames,
        "runtime": round(clock.duration, 6),
        "replay_covered": round(float(v22_track["duration"]), 6),
        "omitted": round(float(v22_track["omitted"]), 6),
        "omissions": [
            {"at": round(at, 4), "dropped": round(dropped, 6)}
            for at, dropped in presentation.omissions(clock)
        ],
        "phases": len(v22_track["cuts"]),
        "v21_frames": 1192 - 85,
        "v21_runtime": round((1192 - 85) / 60.0, 6),
    }

    # --- the preview --------------------------------------------------------
    # **Re-solved rather than read back, because `path_report` needs the solve.**
    # The flight is deterministic and the handoff comes out of the track on
    # disk, so the re-solve is the same shot; `_same_flight` says so rather than
    # trusting it, and a mismatch means the written track is stale.
    resolved, solved_report = v22.build_preview_track(v22_track, machine, seed)
    _same_flight(preview, resolved)
    out["preview"] = {
        key: solved_report[key]
        for key in (
            "duration", "frames", "max_step", "mean_step", "max_across_step",
            "max_rise_step", "max_turn", "mean_turn", "max_yaw", "max_pitch",
            "max_aim_step", "min_sight_clearance", "mean_visible_fraction",
            "min_visible_fraction", "landmarks_seen", "end_reach", "end_elevation",
        )
    }
    out["preview"]["problems"] = solved_report.get(
        "problems", course_preview.check_preview(solved_report)
    )
    out["preview"]["landmarks"] = {
        name: {"seen": entry["seen"], "seconds": entry["seconds"]}
        for name, entry in solved_report["landmarks"].items()
    }

    # --- the race camera, phase by phase ------------------------------------
    out["phases"] = {}
    for label, old_names, new_names in PAIRS:
        row: dict[str, Any] = {"v21_cuts": list(old_names), "v22_cuts": list(new_names)}
        for tag, track, names in (("v21", old, old_names), ("v22", v22_track, new_names)):
            reads = readability.readability_report(track, replay, stride=2)
            seen = readability.visibility_report(track, replay, machine, bundle, stride=6)
            ahead = chase_camera.chase_report(track, replay, machine, bundle, stride=6)
            row[tag] = {
                "seconds": round(sum(
                    float(r["seconds"]) for r in reads if r["cut"] in names
                ), 3),
                "px_median": round(_pool(reads, names, "px_median"), 1),
                "in_frame": round(_pool(reads, names, "in_frame_mean"), 2),
                "visible": round(_pool(seen, names, "visible_mean", "sampled"), 2),
                "hidden_share": round(_pool(seen, names, "hidden_share", "sampled"), 3),
                "both_routes": round(_pool(seen, names, "both_routes", "sampled"), 3),
                "ahead_share": round(_pool(ahead, names, "ahead_share"), 3),
                "ahead_units": round(_pool(ahead, names, "ahead_units"), 1),
                "camera_step": round(max(
                    [float(r["camera_step"]) for r in reads if r["cut"] in names] or [0.0]
                ), 3),
            }
        out["phases"][label] = row

    # --- the joins ----------------------------------------------------------
    for tag, track in (("v21", old), ("v22", v22_track)):
        joins = readability.continuity_report(track, replay)
        # **A boundary with no shared racer has no jump**, and that is a real
        # answer rather than a zero: `continuity_report` measures how far the
        # eye moves by following a racer that is in *both* pictures, and across
        # the start's omission there is none in frame on both sides. Averaging a
        # None as zero would report the film as smoother than it is.
        measured = [float(j["jump"]) for j in joins if j.get("jump") is not None]
        out.setdefault("continuity", {})[tag] = {
            "boundaries": len(joins),
            "measured": len(measured),
            "max_jump": round(max(measured or [0.0]), 4),
            "mean_jump": round(sum(measured) / max(len(measured), 1), 4),
            "hard_cuts": sum(1 for value in measured if value > 0.25),
            "joins": [
                {
                    "from": j["from"], "to": j["to"],
                    "jump": None if j.get("jump") is None else round(float(j["jump"]), 4),
                }
                for j in joins
            ],
        }

    out["findings"] = chase_camera.check_chase(v22_track, replay)
    return out


def _same_flight(written: dict[str, Any], resolved: dict[str, Any]) -> None:
    """The preview on disk is the one just re-solved, to the written precision."""
    a = {round(float(row[0]), 6): row
         for cut in written["cuts"] for row in cut["frames"]}
    b = {round(float(row[0]), 6): row
         for cut in resolved["cuts"] for row in cut["frames"]}
    if a.keys() != b.keys():
        raise SystemExit(
            "the preview track on disk has different frames from a fresh solve; "
            "re-run tools/sloped_v22.py --stage solve"
        )
    worst = max(
        abs(float(a[when][k]) - float(b[when][k]))
        for when in a for k in range(1, 8)
    )
    if worst > 5e-4:
        raise SystemExit(
            f"the preview track on disk is stale: {worst:.6f} layout units from "
            "a fresh solve. Re-run tools/sloped_v22.py --stage solve"
        )


def _print(data: dict[str, Any]) -> None:
    film = data["film"]
    print(f"runtime   {film['runtime']:.4f} s, {film['frames']} frames "
          f"= {film['preview_frames']} preview + {film['hold_frames']} hold "
          f"+ {film['race_frames']} race")
    print(f"          V21 was {film['v21_runtime']:.4f} s, {film['v21_frames']} frames")
    print(f"replay    {film['replay_covered']:.4f} s kept, {film['omitted']:.4f} s omitted "
          f"in {len(film['omissions'])} place(s)")
    for gap in film["omissions"]:
        print(f"            output {gap['at']:.3f}: {gap['dropped']:.4f} s")
    print(f"phases    {film['phases']}")
    print()
    preview = data["preview"]
    print(f"preview   {preview['frames']} frames, {preview['duration']:.4f} s of centres, "
          f"{film['preview_seconds']:.4f} s of screen")
    print(f"          step max {preview['max_step']:.3f}  across {preview['max_across_step']:.3f}"
          f"  turn max {preview['max_turn']:.3f}  pan {preview['max_yaw']:.3f}"
          f"  tilt {preview['max_pitch']:.3f}")
    print(f"          {100 * preview['mean_visible_fraction']:.1f}% of the ribbon in frame, "
          f"{preview['landmarks_seen']}/8 landmarks, "
          f"handoff {preview['end_reach']:.1f} units at {preview['end_elevation']:.1f} deg")
    print(f"          problems: {preview['problems'] or 'none'}")
    print()
    head = (f"{'phase':<16}{'sec':>12}{'px':>13}{'in frame':>15}"
            f"{'visible':>14}{'ahead':>14}{'ahead u':>14}")
    print(head)
    print(f"{'':<16}{'V21    V22':>12}{'V21    V22':>13}{'V21    V22':>15}"
          f"{'V21    V22':>14}{'V21    V22':>14}{'V21    V22':>14}")
    for label, row in data["phases"].items():
        a, b = row["v21"], row["v22"]
        print(f"{label:<16}"
              f"{a['seconds']:6.2f}{b['seconds']:6.2f}"
              f"{a['px_median']:7.0f}{b['px_median']:6.0f}"
              f"{a['in_frame']:8.2f}{b['in_frame']:7.2f}"
              f"{a['visible']:7.2f}{b['visible']:7.2f}"
              f"{a['ahead_share']:7.2f}{b['ahead_share']:7.2f}"
              f"{a['ahead_units']:7.1f}{b['ahead_units']:7.1f}")
    print()
    for tag in ("v21", "v22"):
        row = data["continuity"][tag]
        print(f"{tag} joins  {row['boundaries']} boundaries "
              f"({row['measured']} with a racer in both pictures), "
              f"max {row['max_jump']:.3f} of a frame diagonal, "
              f"mean {row['mean_jump']:.3f}, {row['hard_cuts']} over 0.25")
    print()
    print(f"findings  {data['findings'] or 'none'}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=5432)
    parser.add_argument("--against", default="v212", choices=("v19", "v212"))
    parser.add_argument("--out", default=os.path.join(DOCS_DIR, "metrics.json"))
    args = parser.parse_args(argv)

    data = report(args.seed, args.against)
    _print(data)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

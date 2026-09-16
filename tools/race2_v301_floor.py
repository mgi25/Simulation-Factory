"""V30.1: where camera A's frame actually lands on the floor, cell by cell.

Usage:

    python tools/race2_v301_floor.py map        # the floor-plane histogram
    python tools/race2_v301_floor.py modules    # what module size the frame wants
    python tools/race2_v301_floor.py all

## Why this exists, and why V30 needed it and did not have it

V30's whole method is *measure the lens before authoring the room*, and
`tools/race2_v30_envelope.py` does that for the room's **radii** - how far the
wall must stand, how high it must reach, which bearings carry any wall pixel at
all. It answers none of the questions a *floor* asks, because a floor is not a
radius. The floor is a plane, and the questions are:

    where on that plane does the picture land, per shot
    how wide is the picture there, so a module can be sized against it
    how many module seams cross the frame per second at that size

V30 answered the first of those once, by hand, in a comment: "the sprint's rays
land in a patch centred near (-14, 26)". It is right, and it is two of the
numbers this file reports out of several hundred. Every other floor decision in
V30 - the 2.2-unit strip pitch above all - was taken against the *frame width*
alone, and the frame width is the one thing that only ever says "make it finer".
Nothing in the V30 toolchain ever reported the resulting **seam rate**, which is
the number that decides whether a floor reads as a surface or as a grate, and
the delivered film reads as a grate at 5.06 seams a second.

So this is the floor's envelope tool: the same ray grid as V30's, binned onto
the floor plane rather than reduced to radii, plus the seam-rate arithmetic the
strip decision needed and never had.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.race2_v30_envelope import (  # noqa: E402
    frames, load_track, plane_hit, ray_grid,
)

TRACK = "output/race2/v281_camera/A/race2_switchyard_8.cameras.json"
DOCS = "docs/validation/race2/v301_stage"

# The plane the stage's own top surface lands on, as V30's seam places it: the
# profile authors its floor at y = 0 and `race2_scene._build_stage` lifts the
# stage so that surface sits `STAGE_FLOOR_CLEARANCE` under the lowest point of
# the racing line. On this course that is -2.60, and every number below is in
# world space so it can be compared with the course's own geometry.
FLOOR_Y = -2.599982
ASPECT = 0.5625          # 1080 x 1920

# Camera A's median ground speed, from `envelope.parallax`. A seam rate is a
# speed divided by a pitch, so this is half of every module decision.
CAMERA_SPEED = 12.04


def floor_map(track: dict, cell: float = 4.0, every: int = 3,
              nx: int = 9, ny: int = 15) -> dict:
    """A 2D histogram of floor-plane ray hits, over the film and per shot.

    Area-weighted by construction for the same reason V30's `ray_grid` is: a
    regular grid of rays across the picture makes the share of rays landing in
    a cell the share of the *picture* that cell occupies, so a cell's count is
    screen area rather than a count of geometry.
    """
    cells: dict[tuple[int, int], dict[str, float]] = {}
    shots: dict[str, int] = {}
    total = 0
    for record in frames(track, every):
        shot = record["shot"]
        shots[shot] = shots.get(shot, 0) + 1
        for ray, _sx, _sy in ray_grid(record["eye"], record["aim"],
                                      record["fov"], ASPECT, nx, ny):
            hit = plane_hit(record["eye"], ray, FLOOR_Y)
            total += 1
            if hit is None:
                continue
            key = (int(math.floor(hit[0] / cell)),
                   int(math.floor(hit[2] / cell)))
            bucket = cells.setdefault(key, {"n": 0.0, "range": 0.0})
            bucket["n"] += 1.0
            bucket["range"] += hit[3]
            bucket[shot] = bucket.get(shot, 0.0) + 1.0
    rows = []
    for (ix, iz), bucket in cells.items():
        rows.append({
            "at": [round((ix + 0.5) * cell, 2),
                   round((iz + 0.5) * cell, 2)],
            "share": bucket["n"] / max(total, 1),
            "mean_range": bucket["range"] / bucket["n"],
            "shots": {s: bucket.get(s, 0.0) / bucket["n"] for s in shots},
            "n": int(bucket["n"]),
        })
    rows.sort(key=lambda r: -r["share"])
    return {"cell": cell, "every": every, "rays": total, "shots": shots,
            "cells": rows}


def per_shot_extent(report: dict, share_floor: float = 0.0002) -> dict:
    """The bounding box of the floor each shot actually shows.

    This is the field floor art has to land inside. `share_floor` drops the
    long tail of cells a single grazing top-of-frame ray reached once, which
    would otherwise stretch every box to the horizon: the p95 corner radius is
    193 and the *centre* ray never passes 81.
    """
    out: dict[str, dict] = {}
    for shot in report["map"]["shots"]:
        picked = [c for c in report["map"]["cells"]
                  if c["shots"].get(shot, 0.0) * c["share"] >= share_floor]
        if not picked:
            continue
        xs = [c["at"][0] for c in picked]
        zs = [c["at"][1] for c in picked]
        weight = sum(c["share"] * c["shots"][shot] for c in picked)
        out[shot] = {
            "cells": len(picked),
            "x": [min(xs), max(xs)], "z": [min(zs), max(zs)],
            "centroid": [
                round(sum(c["at"][0] * c["share"] * c["shots"][shot]
                          for c in picked) / weight, 2),
                round(sum(c["at"][1] * c["share"] * c["shots"][shot]
                          for c in picked) / weight, 2)],
            "share_of_film": round(weight, 5),
        }
    return out


def frame_width(track: dict, every: int = 3) -> dict:
    """How wide the picture is where it meets the floor, per shot.

    **The number V30 sized its module against, and it is only half the
    decision.** A 1080x1920 delivery at camera A's 32-38 degree vertical field
    has a horizontal field near 21 degrees, so the picture is narrow at the
    floor - 5.8 units at the final sprint's near edge. Sizing a module to fit
    several seams inside *that* is what produced a 2.2-unit strip, and a
    2.2-unit strip under a camera moving at 12.04 units a second is 5 seams a
    second, which is the grate.
    """
    out: dict[str, dict] = {}
    for record in frames(track, every):
        eye, aim, fov = record["eye"], record["aim"], record["fov"]
        half_x = math.tan(math.radians(fov) * 0.5) * ASPECT
        forward = (aim[0] - eye[0], aim[1] - eye[1], aim[2] - eye[2])
        norm = math.sqrt(sum(c * c for c in forward)) or 1.0
        forward = tuple(c / norm for c in forward)
        centre = plane_hit(eye, forward, FLOOR_Y)
        if centre is None:
            continue
        bucket = out.setdefault(record["shot"], {"widths": [], "ranges": []})
        bucket["widths"].append(2.0 * centre[3] * half_x)
        bucket["ranges"].append(centre[3])
    for _shot, bucket in out.items():
        widths = sorted(bucket.pop("widths"))
        ranges = sorted(bucket.pop("ranges"))
        bucket.update({
            "frames": len(widths),
            "width_min": round(widths[0], 2),
            "width_p50": round(widths[len(widths) // 2], 2),
            "width_max": round(widths[-1], 2),
            "range_p50": round(ranges[len(ranges) // 2], 2),
        })
    return out


def module_table(widths: dict, pitches=(2.38, 6.0, 9.0, 13.0, 18.1, 22.0,
                                        26.5, 30.55)) -> list:
    """Seams a second, and seams across the narrowest frame, per candidate pitch.

    **The two numbers pull in opposite directions and that is the whole floor
    problem.** A pitch fine enough to put several seams across a 5.8-unit
    frame puts five of them a second through it, and five a second is a pattern
    the eye locks onto and tracks instead of the race. A pitch coarse enough to
    stay quiet in motion shows at most one seam in the narrowest shot, and a
    shot with no edge anywhere in it renders as a smooth gradient - which is
    the other failure V30 measured, from its 34x30 run-out pad.

    So the target is not a value of either number, it is a *band*: about one
    seam a second, which is slow enough to read as architecture passing rather
    than as texture scrolling, with the wider framings still crossing several.
    """
    narrow = min(w["width_min"] for w in widths.values())
    out = []
    for pitch in pitches:
        out.append({
            "pitch": pitch,
            "seams_per_second": round(CAMERA_SPEED / pitch, 2),
            "seams_across_narrowest_frame": round(narrow / pitch, 2),
            "seams_across_sprint_p50": round(
                widths["run_in"]["width_p50"] / pitch, 2)
            if "run_in" in widths else None,
        })
    return out


def render(report: dict) -> str:
    out = ["V30.1 FLOOR ENVELOPE: where camera A's picture meets the floor",
           "=" * 74, ""]
    out.append("FRAME WIDTH AT THE FLOOR, per shot")
    out.append("  %-9s %7s %9s %9s %9s %9s"
               % ("shot", "frames", "narrow", "median", "widest", "range"))
    for shot, w in report["frame_width"].items():
        out.append("  %-9s %7d %9.2f %9.2f %9.2f %9.2f"
                   % (shot, w["frames"], w["width_min"], w["width_p50"],
                      w["width_max"], w["range_p50"]))
    out.append("")
    out.append("MODULE PITCH: the two numbers that disagree")
    out.append("  %-8s %10s %14s %13s"
               % ("pitch", "seams/s", "across narrow", "across sprint"))
    for row in report["modules"]:
        out.append("  %-8.2f %10.2f %14.2f %13s"
                   % (row["pitch"], row["seams_per_second"],
                      row["seams_across_narrowest_frame"],
                      ("%.2f" % row["seams_across_sprint_p50"])
                      if row["seams_across_sprint_p50"] is not None else "-"))
    out.append("")
    out.append("  V30 shipped 2.38 (a 2.2 plate on a 0.18 gap).")
    out.append("  The target band is about 0.4 to 2.0 seams a second.")
    out.append("")
    out.append("FLOOR FIELD EACH SHOT SHOWS")
    out.append("  %-9s %6s %18s %18s %16s"
               % ("shot", "cells", "x", "z", "centroid"))
    for shot, box in report["per_shot"].items():
        out.append("  %-9s %6d %18s %18s %16s"
                   % (shot, box["cells"],
                      "%.0f .. %.0f" % tuple(box["x"]),
                      "%.0f .. %.0f" % tuple(box["z"]),
                      "%.0f, %.0f" % tuple(box["centroid"])))
    out.append("")
    out.append("THE TWENTY CELLS THAT CARRY THE MOST PICTURE  (4-unit cells)")
    out.append("  %-16s %9s %9s %s" % ("at", "share", "range", "shots"))
    for cell in report["map"]["cells"][:20]:
        live = ", ".join("%s %.0f%%" % (s, v * 100.0)
                         for s, v in sorted(cell["shots"].items(),
                                            key=lambda kv: -kv[1])
                         if v > 0.05)
        out.append("  %-16s %8.3f%% %9.1f %s"
                   % ("%.0f, %.0f" % tuple(cell["at"]),
                      cell["share"] * 100.0, cell["mean_range"], live))
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("map", "modules", "all"),
                        nargs="?", default="all")
    parser.add_argument("--track", default=TRACK)
    parser.add_argument("--cell", type=float, default=4.0)
    parser.add_argument("--every", type=int, default=3)
    parser.add_argument("--json", default=os.path.join(DOCS, "floor.json"))
    parser.add_argument("--txt", default=os.path.join(DOCS, "floor.txt"))
    args = parser.parse_args()

    track = load_track(args.track)
    report = {
        "floor_y": FLOOR_Y,
        "camera_speed": CAMERA_SPEED,
        "map": floor_map(track, args.cell, args.every),
        "frame_width": frame_width(track, args.every),
    }
    report["per_shot"] = per_shot_extent(report)
    report["modules"] = module_table(report["frame_width"])

    text = render(report)
    print(text)
    os.makedirs(DOCS, exist_ok=True)
    with open(args.json, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1)
    with open(args.txt, "w", encoding="utf-8") as handle:
        handle.write(text + "\n")
    print(f"\nwrote {args.json} and {args.txt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

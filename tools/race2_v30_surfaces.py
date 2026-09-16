"""V30: which authored surfaces are actually in the film, by screen area.

Usage:

    python tools/race2_v30_surfaces.py            # all three concepts
    python tools/race2_v30_surfaces.py --world=A

**This is the brief's Part D, and V29 is why it exists.** V29 authored a hall
with three recessed bays, two pylon rings and a set of warm wall practicals,
and measured six of its surfaces at **0.000% screen coverage** - not "small",
not "subtle", absent. A stage that spends its triangle budget on scenery the
lens never points at is paying twice: once to build it, and once in the
detail it did not put where the camera was looking.

## How it works: a marker render

For each concept this writes a temporary **marker profile** - the same
geometry, the same camera, the same frames, with every material in the family
replaced by a flat `unshaded` colour and fog disabled. `lab_palette._retune`
supports both switches for exactly this purpose and says so: an unshaded
surface renders its own albedo at any distance under any light, so a pixel's
colour *is* the identity of the surface at that pixel, and counting is a
lookup rather than an inference.

The marker profiles are written, rendered and deleted. Nothing they touch is
committed, and the concept profiles themselves are never modified.

## What counts as a failure

A material family with no pixels in any of the ten sampled frames is reported
as **UNSEEN** and has to be either removed from the profile or justified in
the write-up. There is no third option: a surface nobody can see is not
restraint, it is waste.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from tools.race2_v30_review import (  # noqa: E402
    DOCS, MOMENTS, WORLDS, at_list, godot_path,
)

PROFILES = "godot/assets/marble_machine/environment/profiles"
FRAMES = "output/race2/v30_stage/marker"

# One flat colour per material family, far enough apart in RGB that an 8-bit
# render cannot confuse two of them. Deliberately saturated and primary: these
# frames are never looked at as pictures.
MARKERS = {
    "hall_deck": "#FF0000",
    "hall_deck_mid": "#00FF00",
    "hall_deck_dark": "#0000FF",
    "hall_panel": "#FFFF00",
    "hall_panel_dark": "#FF00FF",
    "hall_rib": "#00FFFF",
    "hall_trim": "#FF8000",
    "hall_glass": "#8000FF",
    "hall_beam": "#00FF80",
    "hall_grate": "#804000",
    "lit_hall_warm": "#FF0080",
    "lit_hall_cool": "#0080FF",
}


def marker_profile(source: str, ident: str) -> str:
    with open(os.path.join(PROFILES, f"{source}.json"), encoding="utf-8") as h:
        profile = json.load(h)
    profile["id"] = ident
    palette = profile.setdefault("palette", {})
    for key, colour in MARKERS.items():
        row = dict(palette.get(key, {}))
        # Everything that could shade, tint or fade the flat colour is
        # stripped, not just overridden: a leftover `soft_light` on an
        # unshaded material is inert, but a leftover `alpha` is not.
        for field in ("soft_light", "floor_lift", "edge_light", "alpha",
                      "emission", "backlight", "energy"):
            row.pop(field, None)
        row.update({"albedo": colour, "unshaded": True, "no_fog": True})
        palette[key] = row
    profile["fog"] = {"enabled": False}
    profile["glow"] = {"enabled": False}
    # **The grade has to come off too, and that is the whole trick.**
    # `tools/race2_v29_surfaces.py` states it and the first version of this
    # file ignored it, which cost a full render pass: `unshaded` takes a
    # surface out of the lighting and `no_fog` out of the haze, and neither
    # touches what happens *after* the frame is shaded. This room is graded by
    # an ACES tonemap at exposure 0.82 against a white point of 12 and then a
    # contrast and saturation adjustment, and a flat #00FF00 through that lands
    # nowhere near #00FF00 - so a marker count with a tolerance of 12 found
    # **nine of twelve families "unseen"** in a room whose walls are plainly in
    # the frames. Linear tonemap, unit white, unit exposure, no adjustment: an
    # unshaded albedo then round-trips to the file exactly.
    profile["grade"] = {
        "tonemap": "linear", "exposure": 1.0, "white": 1.0,
        "contrast": 1.0, "saturation": 1.0, "brightness": 1.0,
        "background_energy": 0.0, "ambient_energy": 0.0,
        "ambient_sky_contribution": 0.0, "ambient_colour": "#000000",
    }
    path = os.path.join(PROFILES, f"{ident}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(profile, handle, indent=1)
    index_path = os.path.join(PROFILES, "index.json")
    with open(index_path, encoding="utf-8") as handle:
        index = json.load(handle)
    if ident not in index["profiles"]:
        index["profiles"].append(ident)
        with open(index_path, "w", encoding="utf-8") as handle:
            json.dump(index, handle, indent=2)
            handle.write("\n")
    return path


def drop_marker(ident: str) -> None:
    path = os.path.join(PROFILES, f"{ident}.json")
    if os.path.exists(path):
        os.remove(path)
    index_path = os.path.join(PROFILES, "index.json")
    with open(index_path, encoding="utf-8") as handle:
        index = json.load(handle)
    if ident in index["profiles"]:
        index["profiles"].remove(ident)
        with open(index_path, "w", encoding="utf-8") as handle:
            json.dump(index, handle, indent=2)
            handle.write("\n")


def measure_world(world: str, environment: str, args) -> dict:
    import numpy as np
    from PIL import Image

    ident = f"_v30marker_{world}"
    marker_profile(environment, ident)
    folder = os.path.join(FRAMES, world)
    try:
        os.makedirs(folder, exist_ok=True)
        result = subprocess.run([
            sys.executable, "tools/race2_render.py", "still",
            f"--seed={args.seed}", f"--course={args.course}",
            "--out=output/race2/v281_camera/A", f"--frames={folder}",
            f"--environment={ident}", f"--at={at_list()}",
            f"--godot={godot_path(args.godot)}",
        ], cwd=REPO, capture_output=True, text=True, encoding="utf-8",
            errors="replace")
        if result.returncode != 0:
            raise SystemExit(f"marker {world}:\n"
                             f"{(result.stderr or result.stdout)[-2000:]}")
    finally:
        drop_marker(ident)

    wanted = {k: tuple(int(v[i:i + 2], 16) for i in (1, 3, 5))
              for k, v in MARKERS.items()}
    totals = {k: 0 for k in MARKERS}
    peak = {k: (0.0, "") for k in MARKERS}
    seen_in = {k: 0 for k in MARKERS}
    pixels = 0
    for name, seconds in MOMENTS:
        path = os.path.join(folder, f"still_{args.course}_{args.seed}",
                            f"at_{seconds:07.3f}.png")
        if not os.path.exists(path):
            continue
        a = np.asarray(Image.open(path).convert("RGB")).astype(np.int16)
        pixels += a.shape[0] * a.shape[1]
        for key, rgb in wanted.items():
            # A tolerance, not equality: the renderer still antialiases an
            # unshaded surface against its neighbour, so an edge pixel is a
            # blend of two markers and belongs to neither.
            hit = (np.abs(a - np.array(rgb, dtype=np.int16)).max(axis=2) <= 12)
            count = int(hit.sum())
            totals[key] += count
            share = count / (a.shape[0] * a.shape[1])
            if share > 0:
                seen_in[key] += 1
            if share > peak[key][0]:
                peak[key] = (share, name)
    # Which families the profile actually names. A key that appears in no
    # builder spec is not "unseen" - it was never authored, and reporting it
    # as a failure is the instrument accusing the stage of its own blind spot.
    # `hall_beam` and `hall_glass` are both in that position for every V30
    # concept, and the couple of stray pixels they score are antialiased
    # blends between two neighbouring markers rather than surfaces.
    with open(os.path.join(PROFILES, f"{environment}.json"),
              encoding="utf-8") as handle:
        authored_text = json.dumps(json.load(handle).get("world", {}))
    authored = {k: (f'"{k}"' in authored_text) for k in MARKERS}

    return {
        "environment": environment,
        "pixels": pixels,
        "authored": authored,
        "families": {
            key: {
                "coverage": totals[key] / max(1, pixels),
                "frames_visible": seen_in[key],
                "frames": len(MOMENTS),
                "max_coverage": peak[key][0],
                "max_at": peak[key][1],
                "authored": authored[key],
            } for key in MARKERS
        },
    }


def render_report(report: dict) -> str:
    out = ["V30 SURFACE COVERAGE: every authored material family, by screen area",
           "=" * 78,
           "  V29 measured six of its own surfaces at 0.000%. A family with no",
           "  pixels in any sampled frame is UNSEEN and must be removed or",
           "  justified.", ""]
    for world, data in report.items():
        out.append(f"{world}  ({data['environment']})")
        out.append("  %-16s %10s %8s %10s  %s"
                   % ("family", "coverage", "frames", "peak", "peak at"))
        rows = sorted(data["families"].items(),
                      key=lambda kv: -kv[1]["coverage"])
        for key, stat in rows:
            if not stat["authored"]:
                continue
            flag = "  UNSEEN" if stat["frames_visible"] == 0 else ""
            out.append("  %-16s %9.4f%% %5d/%2d %9.3f%%  %s%s"
                       % (key, stat["coverage"] * 100.0,
                          stat["frames_visible"], stat["frames"],
                          stat["max_coverage"] * 100.0, stat["max_at"], flag))
        unseen = [k for k, v in data["families"].items()
                  if v["authored"] and v["frames_visible"] == 0]
        unauthored = [k for k, v in data["families"].items()
                      if not v["authored"]]
        out.append("  authored families seen: %d of %d"
                   % (sum(1 for v in data["families"].values()
                          if v["authored"] and v["frames_visible"]),
                      sum(1 for v in data["families"].values()
                          if v["authored"])))
        out.append("  AUTHORED BUT UNSEEN: %d  %s"
                   % (len(unseen), ", ".join(unseen) if unseen else "-"))
        out.append("  not authored by this concept: %s"
                   % (", ".join(unauthored) if unauthored else "-"))
        out.append("")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--course", default="switchyard")
    parser.add_argument("--seed", type=int, default=8)
    parser.add_argument("--world", default="A,B,C")
    parser.add_argument("--godot", default="")
    args = parser.parse_args()

    wanted = args.world.split(",")
    report = {}
    for world, environment in WORLDS:
        if world not in wanted:
            continue
        report[world] = measure_world(world, environment, args)
        print(f"  measured {world}")
    text = render_report(report)
    print(text)
    os.makedirs(DOCS, exist_ok=True)
    with open(os.path.join(DOCS, "surfaces.json"), "w",
              encoding="utf-8") as handle:
        json.dump(report, handle, indent=1)
    with open(os.path.join(DOCS, "surfaces.txt"), "w",
              encoding="utf-8") as handle:
        handle.write(text + "\n")
    print(f"wrote {DOCS}/surfaces.json and surfaces.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""V25.1: render the world-art pass against V25 B, compare it, and measure it.

    python tools/sloped_v251_world.py --stage render   --godot PATH
    python tools/sloped_v251_world.py --stage sheet
    python tools/sloped_v251_world.py --stage measure
    python tools/sloped_v251_world.py --stage parallax --godot PATH
    python tools/sloped_v251_world.py --stage clip     --godot PATH
    python tools/sloped_v251_world.py --stage all      --godot PATH

Two worlds - **V25 B as the control and V25.1 as the candidate** - through the
same solved V22.1 camera tracks, over the same locked replay, at the same
thirteen output seconds. The only flag that differs between two renders here is
`--environment=`.

## Why this file is thin

Every stage is `tools/sloped_v25_world.py`'s, run against V25.1's variant
table. That is not laziness, it is the point: **the control has to be measured
by the instrument that measured it**, or a difference in a sheet could be a
difference in the ruler. V25's segmentation, its parallax block matcher, its
phone contrast, its marble separation and its cost parser are all reused
without a line changed, and `sloped/v251_world.py` re-exports every one of
them.

The swap is done explicitly and undone in a `finally`, so an interrupted run
cannot leave the V25 lab pointing at V25.1's tables.

**Nothing here touches the physics.** The replay and both camera tracks are
read and never written, no stage runs a simulation, the seed is 5432 in every
render, and the frame at a given output second is the frame the film has at
that second.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import shutil
import sys
from typing import Any, Sequence

import numpy as np
from PIL import Image

sys.path.insert(0, os.getcwd())

from sloped import v251_world  # noqa: E402
from tools import sloped_v25_world as lab  # noqa: E402

PROJECT_ROOT = os.getcwd()
LAB_DIR = os.path.join("output", "sloped_race_v1", "v251_world")
DOC_DIR = os.path.join("docs", "validation", "sloped_race_v1", "v251_world")
EXPORT_DIR = os.path.join("exports", "v251_world_art_polish")


@contextlib.contextmanager
def v251():
    """Point the V25 lab at V25.1's tables and output directory.

    Two module attributes and nothing else: `v25_world`, which is every table
    the stages read, and `LAB_DIR`, which is where they write. Restored in a
    `finally` so a `KeyboardInterrupt` in the middle of a render cannot leave
    a later V25 run writing into V25.1's tree.
    """
    tables = lab.v25_world
    directory = lab.LAB_DIR
    docs = lab.DOCS_DIR
    lab.v25_world = v251_world
    lab.LAB_DIR = LAB_DIR
    lab.DOCS_DIR = DOC_DIR
    try:
        yield
    finally:
        lab.v25_world = tables
        lab.LAB_DIR = directory
        lab.DOCS_DIR = docs


def stage_export() -> list[str]:
    """Copy the deliverables out of `output/` into `exports/`.

    `output/` is a scratch tree and `exports/` is what a reviewer is handed;
    the project's own memory records that `exports/` holds the only copy of
    several deliverables and is not in git, so this copies rather than moves.
    """
    written: list[str] = []
    for source, destination in (
        (os.path.join(LAB_DIR, "clips"),
         os.path.join(EXPORT_DIR, "clips")),
        (os.path.join(LAB_DIR, "clips", "sections"),
         os.path.join(EXPORT_DIR, "clips", "sections")),
        (os.path.join(LAB_DIR, "kit"), os.path.join(EXPORT_DIR, "kit")),
        (DOC_DIR, os.path.join(EXPORT_DIR, "sheets")),
    ):
        if not os.path.isdir(source):
            continue
        os.makedirs(destination, exist_ok=True)
        for name in sorted(os.listdir(source)):
            full = os.path.join(source, name)
            if not os.path.isfile(full):
                continue
            target = os.path.join(destination, name)
            shutil.copy2(full, target)
            written.append(target)
    return written


def stage_texture() -> str:
    """Why the image-space parallax test loses bands on flat-shaded rock.

    `v25_world.band_shift` discards any 41x41 template whose standard
    deviation is under `TEXTURE_FLOOR`, because a correlation peak on a flat
    field means nothing. That rule is right, and against `smooth_mass` it costs
    almost nothing: averaged normals put a shading gradient on every square
    inch of every surface, so a window anywhere inside a band has contrast in
    it.

    **A flat-shaded facet is one value.** At a distance where a facet spans
    more than forty-one pixels, a template lands wholly inside one and its
    standard deviation collapses - while the band's *cover* is unchanged or
    larger. So the measure reports "fewer than two patches" for a band that is
    a third of the picture and plainly moving.

    This stage is the evidence for that claim rather than the claim itself: it
    prints, per band and per world, how many of the nine candidate sites clear
    the floor and what the median template contrast is. Run it after
    `--stage parallax`, which is what writes the frames it reads.
    """
    rows = [
        "Template contrast inside each depth band, at the first instant of",
        "three camera moves. `sites` is how many 41x41 windows fit wholly",
        "inside the band; `pass` is how many clear TEXTURE_FLOOR = %.1f; `sd`"
        % v251_world.TEXTURE_FLOOR,
        "is the median template standard deviation; `cover` is the band's",
        "share of the frame.",
        "",
        "A band with high cover and low `pass` is one the image-space",
        "parallax test cannot see and the analytic test in",
        "`tools/sloped_v251_sites.py --parallax` can.",
        "",
        "move          band         world       sites  pass      sd   cover",
        "------------  -----------  ----------  -----  ----  ------  ------",
    ]
    for label, track, before, after in lab.PARALLAX_PAIRS:
        if label == "final_dive":
            continue
        for entry in v251_world.ALL:
            marker = v251_world.marker(entry.key)

            def frame(environment: str, layers: str) -> "np.ndarray":
                path = os.path.join(
                    lab.parallax_dir(lab.tagged(environment, layers)), label,
                    "at_%07.3f.png" % before)
                return np.asarray(Image.open(path).convert("RGB"))

            if not os.path.isfile(os.path.join(
                    lab.parallax_dir(lab.tagged(entry.key, "")), label,
                    "at_%07.3f.png" % before)):
                raise SystemExit(
                    "no parallax frames for %s / %s - run --stage parallax"
                    % (entry.key, label))
            masks = v251_world.segment(frame(marker, ""),
                                       frame(marker, "world"))
            grey = np.asarray(Image.open(os.path.join(
                lab.parallax_dir(lab.tagged(entry.key, "")), label,
                "at_%07.3f.png" % before)).convert("L")).astype(float)
            for band in ("foreground", "ridges", "walls"):
                mask = masks[band]
                sites = v251_world.patch_sites(mask)
                if not sites:
                    continue
                edge = v251_world.PATCH
                spread = sorted(
                    float(grey[y - edge:y + edge + 1,
                               x - edge:x + edge + 1].std())
                    for y, x in sites)
                clear = sum(1 for one in spread
                            if one >= v251_world.TEXTURE_FLOOR)
                rows.append(
                    "%-14s%-13s%-12s%5d%6d%8.2f%7.1f%%"
                    % (label, band, entry.title.split()[0], len(sites),
                       clear, spread[len(spread) // 2], mask.mean() * 100))
        rows.append("")
    report = chr(10).join(rows)
    path = os.path.join(DOC_DIR, "texture.txt")
    with open(path, "w", encoding="utf-8", newline=chr(10)) as handle:
        handle.write(report + chr(10))
    print(report)
    return path


def stage_geometry() -> str:
    """The analytic parallax table, written beside the image-space one."""
    from sloped import terrain
    from tools import sloped_v251_sites as sites

    report = sites.geometric_parallax(terrain.terrain_config("b"))
    path = os.path.join(DOC_DIR, "parallax_geometric.txt")
    with open(path, "w", encoding="utf-8", newline=chr(10)) as handle:
        handle.write(report + chr(10))
    print(report)
    return path


#: The five race sections the brief asks for a motion proof of, as output
#: seconds. Taken from V22.1's own edit boundaries rather than chosen, so a
#: section starts where a cut starts.
#:
#: **Cut out of the finished masters rather than rendered.** A section rendered
#: separately would be a second render of the same frames, and two renders of
#: one span on one GPU are not guaranteed identical across a driver reset -
#: this branch measured a 7/255 drift on 0.44% of pixels between sessions.
#: Slicing the master makes a section the master's own frames by construction,
#: and costs an ffmpeg pass instead of six minutes of Godot.
SECTIONS = (
    ("1_start", 0.000, 4.550),
    ("2_descent", 4.550, 7.517),
    ("3_obstacle_fork", 7.517, 14.583),
    ("4_branches_merge", 14.583, 16.750),
    ("5_final_finish", 16.750, 22.317),
)


def stage_sections() -> list[str]:
    """Slice the five race sections out of each variant's `full` master."""
    import subprocess

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise SystemExit("ffmpeg is not on PATH")
    out_dir = os.path.join(LAB_DIR, "clips", "sections")
    os.makedirs(out_dir, exist_ok=True)
    made: list[str] = []
    for entry in v251_world.ALL:
        master = os.path.join(LAB_DIR, "clips", f"full_{entry.key}.mp4")
        if not os.path.isfile(master):
            raise SystemExit(
                f"no master for {entry.key} - run --stage clip first")
        for name, start, end in SECTIONS:
            target = os.path.join(out_dir, f"{name}_{entry.key}.mp4")
            # Re-encoded rather than stream-copied: a copy can only cut on a
            # keyframe, and these masters are encoded for quality rather than
            # for seeking, so a copy would slide a boundary by up to a second.
            completed = subprocess.run(
                [ffmpeg, "-loglevel", "error", "-y", "-ss", f"{start:.3f}",
                 "-to", f"{end:.3f}", "-i", master, "-c:v", "libx264",
                 "-crf", str(lab.VIDEO_CRF), "-preset", lab.VIDEO_PRESET,
                 "-pix_fmt", "yuv420p", target],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if completed.returncode != 0:
                raise SystemExit(f"ffmpeg failed on {target}:\n"
                                 + (completed.stderr or ""))
            made.append(target)
            print(f"  {os.path.basename(target)}  "
                  f"{end - start:.2f} s")
    return made


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True,
                        choices=["render", "sheet", "measure", "parallax",
                                 "parallax-report", "texture",
                                 "geometry", "clip", "sections",
                                 "export", "all"])
    parser.add_argument("--godot")
    parser.add_argument("--only", nargs="*", default=(),
                        help="variant keys to limit a render or a clip to")
    parser.add_argument("--clips", nargs="*", default=(),
                        help="clip keys to limit --stage clip to")
    parser.add_argument("--no-marker", action="store_true",
                        help="skip the two diagnostic passes per variant")
    args = parser.parse_args(argv)

    os.makedirs(LAB_DIR, exist_ok=True)
    os.makedirs(DOC_DIR, exist_ok=True)

    with v251():
        godot = ""
        if args.stage in ("render", "parallax", "clip", "all"):
            godot = lab.find_godot(args.godot)
        if args.stage in ("render", "all"):
            report: dict[str, Any] = lab.stage_render(
                godot, args.only, not args.no_marker)
            for key, entry in report.items():
                print(f"{key}: {entry['cost']}")
        if args.stage in ("sheet", "all"):
            for path in lab.stage_sheet():
                print("wrote", path)
        if args.stage in ("measure", "all"):
            lab.stage_measure()
            print("wrote", os.path.join(DOC_DIR, "measures.json"))
        if args.stage in ("parallax", "all"):
            lab.stage_parallax(godot, args.only)
        if args.stage in ("parallax", "parallax-report", "all"):
            lab.stage_parallax_report()
            print("wrote", os.path.join(DOC_DIR, "parallax.txt"))
        if args.stage in ("texture", "all"):
            print("wrote", stage_texture())
        if args.stage in ("geometry", "all"):
            print("wrote", stage_geometry())
        if args.stage in ("clip", "all"):
            lab.stage_clip(godot, args.only, args.clips)
        if args.stage in ("sections", "all"):
            stage_sections()
        if args.stage in ("export", "all"):
            for path in stage_export():
                print("exported", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

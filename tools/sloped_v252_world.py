"""V25.2: render the final lookdev pass against V25.1, compare it, measure it.

    python tools/sloped_v252_world.py --stage render    --godot PATH
    python tools/sloped_v252_world.py --stage sheet
    python tools/sloped_v252_world.py --stage measure
    python tools/sloped_v252_world.py --stage lookdev
    python tools/sloped_v252_world.py --stage parallax  --godot PATH
    python tools/sloped_v252_world.py --stage clip      --godot PATH
    python tools/sloped_v252_world.py --stage all       --godot PATH

Two worlds - **V25.1 as the control and V25.2 as the candidate** - through the
same solved V22.1 camera tracks, over the same locked replay, at the same
thirteen output seconds. The only flag that differs between two renders here is
`--environment=`.

## Why this file is thin, again

Every stage is `tools/sloped_v25_world.py`'s, run against V25.2's variant
table, exactly as V25.1's lab was. That is the point rather than laziness: the
control has to be measured by the instrument that measured it, or a difference
in a sheet could be a difference in the ruler. V25's segmentation, its parallax
block matcher, its phone contrast, its marble separation and its cost parser
are reused without a line changed.

The swap is done explicitly and undone in a `finally`, so an interrupted run
cannot leave the V25 or V25.1 labs pointing at V25.2's tables.

**Nothing here touches the physics.** The replay and both camera tracks are
read and never written, no stage runs a simulation, the seed is 5432 in every
render, and the frame at a given output second is the frame the film has at
that second.

## The one stage that is new

`--stage lookdev` takes the three measures the brief asks this pass for and
V25 had no reason to take: the midground dark-pixel fraction, the local value
spread on the hero rocks, and the warm-pixel fraction at the finish. It is
separate from `--stage measure` so that the shared measures stay literally
V25's code on V25's tables, and so a reader can tell which numbers are the
instrument that judged three passes and which are this pass's own.
"""

from __future__ import annotations

import argparse
import contextlib
import math
import os
import shutil
import sys
from typing import Any, Sequence

import numpy as np
from PIL import Image

sys.path.insert(0, os.getcwd())

from sloped import v252_world  # noqa: E402
from tools import sloped_v25_world as lab  # noqa: E402

PROJECT_ROOT = os.getcwd()
LAB_DIR = os.path.join("output", "sloped_race_v1", "v252_world")
DOC_DIR = os.path.join("docs", "validation", "sloped_race_v1", "v252_world")
EXPORT_DIR = os.path.join("exports", "v252_world_final_lookdev")

#: The five race sections, V25.1's boundaries exactly. They are cut on the
#: film's own cuts, so a section is a whole number of shots.
SECTIONS = (
    ("1_start", 0.000, 4.550),
    ("2_descent", 4.550, 7.517),
    ("3_obstacle_fork", 7.517, 14.583),
    ("4_branches_merge", 14.583, 16.750),
    ("5_final_finish", 16.750, 22.317),
)


@contextlib.contextmanager
def v252():
    """Point the V25 lab at V25.2's tables and output directory.

    Three module attributes and nothing else: `v25_world`, which is every
    table the stages read, and `LAB_DIR` and `DOCS_DIR`, which are where they
    write. Restored in a `finally` so a `KeyboardInterrupt` in the middle of a
    render cannot leave a later V25 or V25.1 run writing into this tree.
    """
    tables = lab.v25_world
    directory = lab.LAB_DIR
    docs = lab.DOCS_DIR
    lab.v25_world = v252_world
    lab.LAB_DIR = LAB_DIR
    lab.DOCS_DIR = DOC_DIR
    try:
        yield
    finally:
        lab.v25_world = tables
        lab.LAB_DIR = directory
        lab.DOCS_DIR = docs


# --- stage: lookdev ---------------------------------------------------------


def _grey(image: "np.ndarray") -> "np.ndarray":
    return (0.2126 * image[..., 0] + 0.7152 * image[..., 1]
            + 0.0722 * image[..., 2])


def _masks(key: str, moment: str):
    """The colour frame and the per-band masks, for one variant and moment.

    The masks come from `v25_world.segment`, which needs **both** marker
    passes: the ordinary one and the `--layers=world` one. That is not a
    detail - a pixel counts as a band only where the two agree, which is what
    subtracts the machine, and taking the world-only pass alone would count
    every ridge pixel the machine is standing in front of.
    """
    shot = np.asarray(lab._open(lab.still(key, moment)), dtype=np.uint8)
    marker = v252_world.marker(key)
    masks = v252_world.segment(
        np.asarray(lab._open(lab.still(marker, moment))),
        np.asarray(lab._open(lab.still(marker, moment, "world"))))
    return shot, masks


def stage_lookdev() -> dict[str, Any]:
    """The three measures this pass adds, per variant.

    Written next to the shared ones rather than into them, and reported in the
    doc beside the pictures they are about. The brief's Part P is explicit that
    none of these is the verdict, and it is right: every one of them can be
    driven the "good" way by making the world worse.
    """
    report: dict[str, Any] = {}
    for entry in v252_world.ALL:
        # **Pooled over the moments rather than averaged per moment.** A band
        # that is 2% of one frame and 30% of another must not count the same
        # in both, so the dark fraction is accumulated as raw pixel counts and
        # divided once at the end. The local spread is a median of medians,
        # which cannot be pooled that way and is not trying to be - it is a
        # per-frame property being summarised over frames.
        pooled: dict[str, list[int]] = {
            band: [0, 0] for band in v252_world.MIDGROUND}
        spreads: dict[str, list[float]] = {
            band: [] for band in v252_world.MIDGROUND}
        for one in v252_world.RACE_MOMENTS:
            shot, masks = _masks(entry.key, one.key)
            grey = _grey(shot)
            for band in v252_world.MIDGROUND:
                mask = masks[band]
                total = int(mask.sum())
                if total == 0:
                    continue
                pooled[band][0] += int((grey[mask] < v252_world.DARK).sum())
                pooled[band][1] += total
                value = v252_world.value_spread(grey, mask)
                if value == value:
                    spreads[band].append(value)
        dark = {band: (counts[0] / counts[1] if counts[1] else float("nan"))
                for band, counts in pooled.items()}
        spread = {band: (float(np.median(values)) if values else float("nan"))
                  for band, values in spreads.items()}

        # The hero rock: the obstacle's east wall, cropped by the same
        # rectangle for both variants so the number is about the rock rather
        # than about where it landed.
        hero = v252_world.crop("hero")
        shot, masks = _masks(entry.key, hero.moment)
        box = _pixels(shot.shape, hero.box)
        window = shot[box[1]:box[3], box[0]:box[2]]
        rock = np.zeros(shot.shape[:2], dtype=bool)
        for band in ("ridges", "foreground", "walls"):
            rock |= masks[band]
        hero_spread = v252_world.value_spread(
            _grey(window), rock[box[1]:box[3], box[0]:box[2]])

        # The finish: how much of the world in the payoff frame has crossed
        # over into warm. Machine and marbles are excluded by the segmentation,
        # so the gold chute and the FINISH board cannot flatter it.
        shot, masks = _masks(entry.key, "finish")
        world = np.zeros(shot.shape[:2], dtype=bool)
        for mask in masks.values():
            world |= mask
        warm = v252_world.warm_fraction(shot, world)
        shift = v252_world.warm_shift(shot, world)
        # The rim itself, as well as the whole world: the brief's hierarchy is
        # about the finish *area* being the warmest place, and a fraction over
        # the whole frame dilutes that with the gorge under it.
        rim = v252_world.warm_fraction(shot, masks["ridges"])
        rim_shift = v252_world.warm_shift(shot, masks["ridges"])

        report[entry.key] = {
            "midground_dark": dark,
            "midground_spread": spread,
            "hero_spread": hero_spread,
            "finish_warm": warm,
            "finish_shift": shift,
            "finish_rim_warm": rim,
            "finish_rim_shift": rim_shift,
        }
    path = os.path.join(DOC_DIR, "lookdev.json")
    os.makedirs(DOC_DIR, exist_ok=True)
    lab._write_json(path, report)
    for key, entry in report.items():
        print(f"{key}:")
        for band in v252_world.MIDGROUND:
            print(f"  {band:<12} dark {entry['midground_dark'][band]:6.1%}"
                  f"   local spread {entry['midground_spread'][band]:5.1f}")
        print(f"  hero rock    local spread {entry['hero_spread']:5.1f}")
        print(f"  finish world warm {entry['finish_warm']:6.1%}"
              f"   R-B median {entry['finish_shift']:6.1f}")
        print(f"  finish rim   warm {entry['finish_rim_warm']:6.1%}"
              f"   R-B median {entry['finish_rim_shift']:6.1f}")
    return report


def _pixels(shape, box) -> tuple[int, int, int, int]:
    height, width = shape[0], shape[1]
    return (int(box[0] * width), int(box[1] * height),
            int(box[2] * width), int(box[3] * height))


# --- stage: geometry --------------------------------------------------------


def _tool(name: str):
    """Load a sibling tool by path; `tools/` is not a package."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_v252_" + name, os.path.join(PROJECT_ROOT, "tools", name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module




def _resolved(profile_id: str) -> dict:
    """One profile with its `extends` chain merged, as Godot resolves it."""
    import copy

    def read(name: str) -> dict:
        path = os.path.join(
            "godot", "assets", "marble_machine", "environment", "profiles",
            f"{name}.json")
        with open(path, encoding="utf-8") as handle:
            import json as _json
            return _json.load(handle)

    def merge(base: dict, over: dict) -> dict:
        out = copy.deepcopy(base)
        for key, value in over.items():
            if value is None:
                out.pop(key, None)
            elif isinstance(value, dict) and isinstance(out.get(key), dict):
                out[key] = merge(out[key], value)
            else:
                out[key] = copy.deepcopy(value)
        return out

    chain: list[dict] = []
    name = profile_id
    while name:
        node = read(name)
        chain.append(node)
        name = node.get("extends", "")
    out: dict = {}
    for node in reversed(chain):
        out = merge(out, node)
    return out


class _Shim:
    """What `sloped_v251_sites._band_points` reads, out of a resolved profile.

    The geometric parallax instrument takes a module and asks it for five
    tables. Pointing it at a *resolved profile* instead of at V25.1's authoring
    module is what lets the same arithmetic measure both worlds - and it is the
    only honest way to compare them, because a difference in the tool would be
    indistinguishable from a difference in the world.
    """

    CENTRE = (1.0, 6.0)

    def __init__(self, profile: dict) -> None:
        world = profile["world"]
        self.WALLS = world["walls"]
        self.RIDGES = world["ridges"]
        self.SCARPS = world["scarps"]
        self.BOULDERS = world["boulders"]


def stage_geometry() -> str:
    """Parallax from geometry rather than from pixels, for both worlds.

    **The image-space test cannot adjudicate this pass and says so.** V25.1's
    section 15 records why it fails on flat-shaded rock - a 41-pixel template
    inside one facet has no contrast - and V25.2 breaks it a second way: a
    tempered surface is a smooth gradient with no distinctive feature, so the
    correlation peak lands on zero. `--stage parallax` reports `0px` on the
    final dive for both the terrain and the foreground, which is not a finding
    about a camera that is plainly moving.

    So the verdict on Part Q's "parallax remains strong" is this measure: the
    positions of the world's own forms, projected through the solved camera at
    both instants. It never looks at a surface, so no shading change can move
    it - which also means that if it is unchanged between the two worlds, the
    parallax field is unchanged, which is exactly the claim.
    """
    sites = _tool("sloped_v251_sites")
    from sloped import terrain

    cfg = terrain.terrain_config("b")
    lines = [
        "Analytic parallax, both worlds: median image displacement per depth",
        "band over 0.25 s, from the world's own form positions projected",
        "through the solved camera at both instants. Shading-blind, so it is",
        "the measure that survives both the flat facets V25.1 broke the block",
        "matcher with and the tempered surfaces V25.2 breaks it with.",
        "Pixels at 1080 x 1920; N is how many forms of that band are on",
        "screen at both instants.",
        "",
    ]
    for entry in v252_world.ALL:
        bands = sites._band_points(_Shim(_resolved(entry.key)), cfg)
        lines.append(entry.title)
        header = "move            " + "".join("%-16s" % one for one in bands)
        lines += [header, "-" * len(header)]
        for label, track, before, after in sites.MOVES:
            first = sites._shot_at(track, before)
            second = sites._shot_at(track, after)
            cells = []
            spread: list[float] = []
            for points in bands.values():
                moved: list[float] = []
                for x, y, z in points:
                    a = first.project((x, y, z))
                    b = second.project((x, y, z))
                    if not (a[0] and b[0]):
                        continue
                    moved.append(math.hypot((b[1] - a[1]) * 0.5 * 1080.0,
                                            (b[2] - a[2]) * 0.5 * 1920.0))
                if not moved:
                    cells.append("%-16s" % "-")
                    continue
                moved.sort()
                median = moved[len(moved) // 2]
                spread.append(median)
                cells.append("%-16s" % ("%.0fpx/%dn" % (median, len(moved))))
            ratio = ""
            if len(spread) >= 2 and min(spread) > 0.5:
                ratio = "  spread %.1fx" % (max(spread) / min(spread))
            lines.append("%-16s%s%s" % (label, "".join(cells), ratio))
        lines.append("")
    text = chr(10).join(lines)
    path = os.path.join(DOC_DIR, "geometry.txt")
    os.makedirs(DOC_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline=chr(10)) as handle:
        handle.write(text + chr(10))
    print(text)
    return path


# --- stage: sections and export ---------------------------------------------


def stage_sections() -> list[str]:
    """Slice the five race sections out of each variant's `full` master."""
    import subprocess

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise SystemExit("ffmpeg is not on PATH")
    out_dir = os.path.join(LAB_DIR, "clips", "sections")
    os.makedirs(out_dir, exist_ok=True)
    made: list[str] = []
    for entry in v252_world.ALL:
        master = os.path.join(LAB_DIR, "clips", f"full_{entry.key}.mp4")
        if not os.path.isfile(master):
            raise SystemExit(
                f"no master for {entry.key} - run --stage clip first")
        for name, start, end in SECTIONS:
            target = os.path.join(out_dir, f"{name}_{entry.key}.mp4")
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
            print(f"  {os.path.basename(target)}  {end - start:.2f} s")
    return made


#: The three the brief asks for side by side. Stacked horizontally at half
#: width each, so a phone-shaped pair still fits a phone-shaped screen.
SIDE_BY_SIDE = ("1_start", "3_obstacle_fork", "5_final_finish")


def stage_side_by_side() -> list[str]:
    """V25.1 | V25.2, in motion, for the three sections the brief names."""
    import subprocess

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise SystemExit("ffmpeg is not on PATH")
    sections = os.path.join(LAB_DIR, "clips", "sections")
    out_dir = os.path.join(LAB_DIR, "clips", "pairs")
    os.makedirs(out_dir, exist_ok=True)
    made: list[str] = []
    for name in SIDE_BY_SIDE:
        left = os.path.join(sections, f"{name}_{v252_world.CONTROL.key}.mp4")
        right = os.path.join(sections, f"{name}_{v252_world.CANDIDATE.key}.mp4")
        for path in (left, right):
            if not os.path.isfile(path):
                raise SystemExit(f"missing {path} - run --stage sections")
        target = os.path.join(out_dir, f"{name}_pair.mp4")
        completed = subprocess.run(
            [ffmpeg, "-loglevel", "error", "-y", "-i", left, "-i", right,
             "-filter_complex",
             "[0:v]scale=540:960[a];[1:v]scale=540:960[b];[a][b]hstack",
             "-c:v", "libx264", "-crf", str(lab.VIDEO_CRF),
             "-preset", lab.VIDEO_PRESET, "-pix_fmt", "yuv420p", target],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if completed.returncode != 0:
            raise SystemExit(f"ffmpeg failed on {target}:\n"
                             + (completed.stderr or ""))
        made.append(target)
        print(f"  {os.path.basename(target)}")
    return made


def stage_export() -> list[str]:
    """Copy the deliverables out of `output/` into `exports/`.

    `output/` is scratch and `exports/` is what a reviewer is handed; the
    project's own memory records that `exports/` holds the only copy of several
    deliverables and is not in git, so this copies rather than moves.
    """
    written: list[str] = []
    for source, destination in (
        (os.path.join(LAB_DIR, "clips"), os.path.join(EXPORT_DIR, "clips")),
        (os.path.join(LAB_DIR, "clips", "sections"),
         os.path.join(EXPORT_DIR, "clips", "sections")),
        (os.path.join(LAB_DIR, "clips", "pairs"),
         os.path.join(EXPORT_DIR, "clips", "pairs")),
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True,
                        choices=["render", "sheet", "measure", "lookdev",
                                 "parallax", "parallax-report",
                                 "geometry", "clip", "sections", "pairs",
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

    with v252():
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
        if args.stage in ("lookdev", "all"):
            stage_lookdev()
            print("wrote", os.path.join(DOC_DIR, "lookdev.json"))
        if args.stage in ("parallax", "all"):
            lab.stage_parallax(godot, args.only)
        if args.stage in ("parallax", "parallax-report", "all"):
            lab.stage_parallax_report()
            print("wrote", os.path.join(DOC_DIR, "parallax.txt"))
        if args.stage in ("geometry", "all"):
            print("wrote", stage_geometry())
        if args.stage in ("clip", "all"):
            lab.stage_clip(godot, args.only, args.clips)
        if args.stage in ("sections", "all"):
            stage_sections()
        if args.stage in ("pairs", "all"):
            stage_side_by_side()
        if args.stage in ("export", "all"):
            for path in stage_export():
                print("exported", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

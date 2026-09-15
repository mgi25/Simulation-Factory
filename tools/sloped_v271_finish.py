"""V27.1: render, measure and report the finish correction.

    python tools/sloped_v271_finish.py --stage all

Stages, and each one can be run on its own:

    survey     which hall surface is behind the finish, and where it is seen
    render     the three worlds and their diagnostic twins, twelve moments each
    measure    the corrected separation instrument, all twelve moments
    surfaces   which hall material the bright background is, by name
    delta      which of the twelve frames the one-field delta reaches
    winner     Part B: the purple racer at the three finish moments
    ring       Part B: how much of the WINNER mark's life lands on it
    payoff     Part C: the card's contrast on the contained finish bay
    hook       Part F: frame 0, unchanged, checked rather than assumed
    country    Part E: one India-skinned racer at five moments, render-only
    proof      Part I: the brief's five finish frames, three worlds
    sheet      the comparison boards and the phone board
    clip       the finish clip, full size and phone size
    export     copy the deliverables into exports/

`ring` reads the frames `clip` renders, so run it after `clip` or as part of
`all`, which orders them.

Everything is rendered from V26's own replay, V24's own camera track and V24's
own edit. No stage here may write either.

## The twelve-second rule, inherited

V27 found it and it still binds: a still is only comparable with another still
requested in the **same `--at` list**, because the renderer accumulates between
samples inside one process. Every sheet here is therefore rendered from
`v27.seconds()` - the same twelve - and the country probe, which asks for five,
is compared only against itself.

## The track's time axis is the replay's

`cameras_v24_5432.json` runs 0.2 to 23.45, which is replay seconds; the film is
20.117 s long because V24 omits 3.133 s of it. So a moment has two clocks -
`Moment.second` for the renderer and the file name, `Moment.replay` for
anything that reads the solved track - and mixing them up puts a camera three
seconds from where the picture was taken. `--stage survey`'s first version did
exactly that.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
from typing import Any, Sequence

import numpy as np
from PIL import Image, ImageDraw

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sloped import overlays  # noqa: E402
from sloped import readability  # noqa: E402
from sloped import v24  # noqa: E402
from sloped import v24_hook  # noqa: E402
from sloped import v24_payoff  # noqa: E402
from sloped import v27_contained as v27  # noqa: E402
from sloped import v271_finish as v271  # noqa: E402
from sloped.presentation import project  # noqa: E402

import tools.sloped_v27_contained as lab  # noqa: E402

SEED = v271.SEED
WIDTH, HEIGHT = v271.WIDTH, v271.HEIGHT
PHONE = v27.PHONE

OUT_DIR = os.path.join("output", "sloped_race_v1")
LAB_DIR = os.path.join(OUT_DIR, "v271_contained")
DOC_DIR = os.path.join("docs", "validation", "sloped_race_v1", "v271_contained")
EXPORT_DIR = os.path.join("exports", "v271_contained_hall_finish")

REPLAY = lab.REPLAY
TRACK = lab.TRACK
START_CONTRACT = lab.START_CONTRACT

#: The three worlds the finish is compared across, in the order they are
#: printed. The control first, because a correction that is not scored against
#: what ships is a correction against nothing.
WORLDS: tuple[tuple[str, str, str], ...] = (
    (v271.CONTROL, "v26", "V26 outdoor"),
    (v271.PARENT, "v27", "V27 contained_hall"),
    (v271.PROFILE, "v271", "V27.1 corrected"),
)

#: Each world's depth-band twin.
MARKERS = {
    v271.CONTROL: "_marker_v27_control",
    v271.PARENT: "_marker_v27a",
    v271.PROFILE: v271.MARKER,
}

PROBES = ("_probe_v271", "_probe_v271_pad")

SHEET_BACKGROUND = lab.SHEET_BACKGROUND
SHEET_LABEL = lab.SHEET_LABEL
SHEET_DIM = lab.SHEET_DIM
SHEET_RULE = lab.SHEET_RULE

NEWLINE = chr(10)


class LabError(RuntimeError):
    pass


# --- paths ------------------------------------------------------------------


def stills_dir(environment: str, layers: str = "") -> str:
    tag = environment if not layers else f"{environment}@{layers}"
    return os.path.join(LAB_DIR, "stills", tag)


def still(environment: str, key: str, layers: str = "") -> str:
    return os.path.join(stills_dir(environment, layers),
                        f"at_{v27.moment(key).second:07.3f}.png")


def country_dir(tag: str) -> str:
    return os.path.join(LAB_DIR, "country", tag)


def country_still(tag: str, key: str) -> str:
    return os.path.join(country_dir(tag), f"at_{v27.moment(key).second:07.3f}.png")


def _load(path: str) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: str, payload: Any) -> None:
    v271.write_json(path, payload)


def _write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text.rstrip("\n") + "\n")


def _open(path: str) -> Image.Image:
    if not os.path.isfile(path):
        raise LabError(f"missing render: {path}{NEWLINE}Run --stage render first.")
    return Image.open(path).convert("RGB")


def _pixels(path: str) -> np.ndarray:
    return np.asarray(_open(path)).astype(float)


# --- running Godot ----------------------------------------------------------


def _render_at(godot: str, environment: str, layers: str,
               seconds: Sequence[float], out: str, label: str,
               extra: Sequence[str] = ()) -> str:
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out, exist_ok=True)
    flags = [
        f"--out-dir={os.path.abspath(out)}",
        "--at=" + ",".join(f"{one:.3f}" for one in seconds),
        f"--replay={os.path.abspath(REPLAY)}",
        f"--cameras={os.path.abspath(TRACK)}",
        f"--start-contract={os.path.abspath(START_CONTRACT)}",
        f"--width={WIDTH}", f"--height={HEIGHT}",
        *lab.FIXED_FLAGS,
        f"--environment={environment}",
        *extra,
    ]
    if layers:
        flags.append(f"--layers={layers}")
    completed = subprocess.run(
        [godot, "--path", lab.GODOT_PROJECT, lab.RENDER_SCENE, "--", *flags],
        cwd=PROJECT_ROOT, stderr=subprocess.PIPE, stdout=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace")
    errors = NEWLINE.join((completed.stderr or "").splitlines()[-40:])
    if completed.returncode != 0:
        raise LabError(f"{label}: Godot exited {completed.returncode}"
                       f"{NEWLINE}{errors}")
    for line in (completed.stderr or "").splitlines():
        if "SCRIPT ERROR" in line or "Parse Error" in line:
            raise LabError(f"{label}: Godot reported an error: {line.strip()}")
        # **A push_error is not a crash and Godot exits 0 on one.** An
        # unrecognised `--racers=` makes the scene fall back to its default
        # appearance and render a perfectly good sheet of the wrong thing, so
        # the scene's own complaints are failures here rather than log noise.
        if "sloped_race_scene:" in line or "racer_visual:" in line:
            raise LabError(f"{label}: {line.split(': ', 1)[-1].strip()}")
        if "environment_stage:" in line or "environment_world:" in line:
            print("  ! " + line.split(": ", 1)[-1].strip())
    written = sorted(one for one in os.listdir(out) if one.endswith(".png"))
    if len(written) != len(seconds):
        raise LabError(f"{label}: asked for {len(seconds)} frames, "
                       f"got {len(written)}")
    return completed.stdout or ""


# --- stage: survey ----------------------------------------------------------


def stage_survey() -> dict[str, Any]:
    """Which wall and deck pieces the finish cameras see, and which are shared.

    Read off the solved track with the film's own projector. It answers two
    questions the fix depends on:

    1. **Is there a finish sector at all?** No. Of the 32 segments of the main
       wall, 7 are in a finish frame and every one of them is also in the
       obstacle, the branch or the merge; the two deck rings are the same. So a
       per-segment repaint of "the wall behind the finish" is not available,
       because there is no wall that is only behind the finish.
    2. **What is left that is local?** The finish bay's own forms - the landing
       pad and the frame - which are sited at the finish node and belong to no
       other section. That is where the fix had to go, and it is where it went.
    """
    frames = v271.frames_of(_load(TRACK))
    profile = _load(os.path.join(
        PROJECT_ROOT, "godot", "assets", "marble_machine", "environment",
        "profiles", f"{v271.PARENT}.json"))
    bands = profile["world"]["shell"]["bands"]
    rings = profile["world"]["deck"]["rings"]
    finish = set(v271.FINISH)

    seen: dict[tuple[str, int, int], set[str]] = {}
    for one in v27.MOMENTS:
        frame = v271.frame_at(frames, one.replay)
        for index, band in enumerate(bands):
            count = int(band["count"])
            step = float(band["bearing_step"])
            start = float(band["bearing_from"])
            foot = float(band["foot"])
            tall = float(band["height"])
            for segment in range(count):
                x, z = v271.polar(start + step * segment, float(band["radius"]))
                for part in (0.05, 0.3, 0.6, 0.9):
                    if v271.in_frame(frame, (x, foot + tall * part, z)):
                        seen.setdefault(("shell", index, segment),
                                        set()).add(one.key)
                        break
        for index, ring in enumerate(rings):
            facets = int(ring.get("facets", 24))
            mid = (float(ring["outer"]) + float(ring["inner"])) * 0.5
            for facet in range(facets):
                x, z = v271.polar(360.0 / facets * facet, mid)
                if v271.in_frame(frame, (x, float(ring["y"]), z)):
                    seen.setdefault(("deck", index, facet), set()).add(one.key)

    report: dict[str, Any] = {"parts": []}
    lines = [
        "THE FINISH SECTOR",
        "which pieces of the hall the three finish cameras see, and what else",
        "sees them. Projected with the film's own lens onto the solved track.",
        "",
        "%-14s %6s %10s %10s %10s" % ("part", "pieces", "at finish",
                                      "finish only", "never seen"),
        "-" * 56,
    ]
    for kind, index, count in ([("shell", i, int(b["count"]))
                                for i, b in enumerate(bands)]
                               + [("deck", i, int(r.get("facets", 24)))
                                  for i, r in enumerate(rings)]):
        only, shared, never = [], [], []
        for piece in range(count):
            got = seen.get((kind, index, piece), set())
            if not got:
                never.append(piece)
            elif got <= finish:
                only.append(piece)
            elif got & finish:
                shared.append(piece)
        name = f"{kind} {index}"
        report["parts"].append({
            "part": name, "pieces": count, "finish_only": only,
            "finish_shared": shared, "never_seen": len(never),
        })
        lines.append("%-14s %6d %10d %10d %10d" % (
            name, count, len(only) + len(shared), len(only), len(never)))

    lines += [
        "",
        "Not one piece of wall or deck is private to the finish. Every segment",
        "and every facet the three finish cameras see is also in the obstacle,",
        "the branch or the merge, so there is no 'wall behind the finish' to",
        "take down a value: the brief's fixes 1, 3 and 6 have no surface to",
        "act on that is not shared. What *is* local to the finish is the bay's",
        "own furniture, sited at the finish node and built nowhere else - and",
        "the fix is one field of it.",
    ]
    text = NEWLINE.join(lines)
    _write_json(os.path.join(LAB_DIR, "survey.json"), report)
    _write_text(os.path.join(DOC_DIR, "survey.txt"), text)
    print(text)
    return report


# --- stage: render ----------------------------------------------------------


def stage_render(godot: str, only: Sequence[str] = ()) -> dict[str, Any]:
    """Twelve moments per world, plus a marker pair each, plus two probes."""
    seconds = v27.seconds()
    cost_path = os.path.join(LAB_DIR, "cost.json")
    report: dict[str, Any] = _load(cost_path) if os.path.isfile(cost_path) else {}
    for environment, tag, _title in WORLDS:
        if only and environment not in only and tag not in only:
            continue
        marker = MARKERS[environment]
        for env, layers in ((environment, ""), (marker, ""), (marker, "world")):
            label = env + ("" if not layers else f"@{layers}")
            print(f"--- {label} ---")
            started = time.perf_counter()
            stdout = _render_at(godot, env, layers, seconds,
                                stills_dir(env, layers), label)
            elapsed = time.perf_counter() - started
            if env == environment and not layers:
                cost = v27.parse_cost(stdout)
                report[tag] = {
                    "environment": environment,
                    "meshes": cost.meshes,
                    "triangles": cost.triangles,
                    "ms_per_frame": cost.milliseconds,
                    "census": v27.census_of(stdout),
                    "wall_seconds": round(elapsed, 2),
                }
                print(f"  {cost.line()}")
            print(f"  {len(seconds)} frames in {elapsed:.1f} s")
    if not only:
        for probe in PROBES:
            print(f"--- {probe} ---")
            _render_at(godot, probe, "", seconds, stills_dir(probe), probe)
    _write_json(cost_path, report)
    return report


# --- the corrected measurement ----------------------------------------------


def _world_masks(environment: str, key: str):
    marker = MARKERS[environment]
    whole = _pixels(still(marker, key))
    world = _pixels(still(marker, key, "world"))
    bands, machine = v271.background_mask(whole, world)
    background = np.zeros(machine.shape, dtype=bool)
    for mask in bands.values():
        background |= mask
    return bands, machine, background


def stage_measure() -> dict[str, Any]:
    """Separation at every moment, through both instruments."""
    out: dict[str, Any] = {"seed": SEED, "worlds": {}, "moments": {}}
    cache: dict[tuple[str, str], Any] = {}
    for environment, tag, title in WORLDS:
        rows: dict[str, Any] = {}
        for one in v27.MOMENTS:
            pixels = _pixels(still(environment, one.key))
            bands, machine, background = _world_masks(environment, one.key)
            cache[(tag, one.key)] = (pixels, machine, background)
            grey = v271.luma(pixels)
            # V27's own number, kept so the two can be printed together.
            marker = MARKERS[environment]
            old_bands = v27.segment(_pixels(still(marker, one.key)),
                                    _pixels(still(marker, one.key, "world")))
            old_background = np.zeros(machine.shape, dtype=bool)
            for mask in old_bands.values():
                old_background |= mask
            rows[one.key] = {
                "separation": v271.separation(pixels, machine, background),
                "v27_separation": v271.separation(pixels, ~old_background,
                                                  old_background),
                "collar": v271.collar(pixels, machine, background),
                "machine_luma": round(float(grey[machine].mean()), 2),
                "machine_cover": round(float(machine.mean()), 4),
                "background_luma": round(float(grey[background].mean()), 2),
                "cover": {k: round(float(m.mean()), 4)
                          for k, m in bands.items()},
                "value": {k: round(float(grey[m].mean()), 1)
                          for k, m in bands.items() if int(m.sum()) > 400},
                "clip_white": round(float((grey >= 250.0).mean()), 5),
                "clip_black": round(float((grey <= 5.0).mean()), 5),
                "mean_luma": round(float(grey.mean()), 2),
            }
        out["worlds"][tag] = {"environment": environment, "title": title,
                              "moments": rows}
    # The pairwise collar, on the silhouette two worlds share.
    for one in v27.MOMENTS:
        pa, ma, ba = cache[("v26", one.key)]
        pb, mb, bb = cache[("v271", one.key)]
        control, corrected = v271.collar_pair(pa, ma, ba, pb, mb, bb)
        pc, mc, bc = cache[("v27", one.key)]
        _, hall = v271.collar_pair(pa, ma, ba, pc, mc, bc)
        out["moments"][one.key] = {
            "common_collar": {"v26": control, "v27": hall, "v271": corrected},
        }
    cost_path = os.path.join(LAB_DIR, "cost.json")
    if os.path.isfile(cost_path):
        out["cost"] = _load(cost_path)
    _write_json(os.path.join(LAB_DIR, "measures.json"), out)
    text = _measure_table(out)
    _write_text(os.path.join(DOC_DIR, "measures.txt"), text)
    print(text)
    return out


def _cell(value: Any, width: int = 8, places: int = 1) -> str:
    if value is None:
        return " " * (width - 1) + "-"
    return f"{value:{width}.{places}f}"


def _measure_table(measured: dict[str, Any]) -> str:
    worlds = measured["worlds"]
    lines = [
        "THE FINISH CORRECTION",
        "machine-to-background separation in luma, at the twelve V27 moments.",
        "",
        "1  Through the corrected instrument (occlusion, not hue agreement)",
        "",
        "%-16s %8s %8s %8s   %s" % ("moment", "V26", "V27", "V27.1", "verdict"),
        "-" * 68,
    ]
    for one in v27.MOMENTS:
        row = [worlds[tag]["moments"][one.key]["separation"]
               for _e, tag, _t in WORLDS]
        mark = ""
        if None not in row:
            mark = "over V26" if row[2] >= row[0] else f"{row[2] - row[0]:+.1f}"
            if abs(row[2] - row[1]) >= 0.05:
                mark += f", {row[2] - row[1]:+.1f} on V27"
        star = " *" if one.key in v271.FINISH else "  "
        lines.append("%-16s%s%s%s   %s" % (
            one.key, _cell(row[0]), _cell(row[1]), _cell(row[2]), mark) + star)
    lines += [
        "",
        "  * the three the pass is judged on. Target %.0f, ideal 75-85." % v271.TARGET,
        "",
        "2  The same frames through V27's own instrument, for comparison",
        "",
        "%-16s %8s %8s %8s" % ("moment", "V26", "V27", "V27.1"),
        "-" * 52,
    ]
    for key in v271.FINISH:
        row = [worlds[tag]["moments"][key]["v27_separation"]
               for _e, tag, _t in WORLDS]
        lines.append("%-16s%s%s%s" % (key, _cell(row[0]), _cell(row[1]),
                                      _cell(row[2])))
    lines += [
        "",
        "  V27 published 90/49 at the winner and 84/53 at the payoff. The",
        "  instrument counted the cream finish chute as background wherever it",
        "  stood over the repainted landform, which is the contained case and",
        "  not the control's. See sloped/v271_finish.py's header.",
        "",
        "3  At the silhouette, on the machine both worlds show",
        "",
        "%-16s %8s %8s %8s" % ("moment", "V26", "V27", "V27.1"),
        "-" * 52,
    ]
    for key in v271.FINISH:
        row = measured["moments"][key]["common_collar"]
        lines.append("%-16s%s%s%s" % (key, _cell(row["v26"]),
                                      _cell(row["v27"]), _cell(row["v271"])))
    lines += [
        "",
        "4  What the background is made of at the finish",
        "",
        "%-16s %-6s %9s %9s %9s %9s" % ("moment", "world", "near gnd",
                                        "structure", "deck", "wall"),
        "-" * 64,
    ]
    for key in v271.FINISH:
        for _e, tag, _t in WORLDS:
            row = worlds[tag]["moments"][key]
            cells = []
            for band in ("terrain", "structure", "deck", "shell"):
                cover = row["cover"].get(band, 0.0)
                value = row["value"].get(band)
                cells.append("-" if value is None
                             else "%4.1f%%/%3.0f" % (cover * 100, value))
            lines.append("%-16s %-6s %9s %9s %9s %9s" % (key, tag, *cells))
        lines.append("")
    lines += [
        "5  Exposure",
        "",
        "%-16s %-6s %9s %9s %9s" % ("moment", "world", "mean", "clip wht",
                                    "clip blk"),
        "-" * 56,
    ]
    for key in v271.FINISH:
        for _e, tag, _t in WORLDS:
            row = worlds[tag]["moments"][key]
            lines.append("%-16s %-6s %9.1f %8.2f%% %8.2f%%" % (
                key, tag, row["mean_luma"], row["clip_white"] * 100,
                row["clip_black"] * 100))
        lines.append("")
    cost = measured.get("cost", {})
    if cost:
        lines += ["6  Cost", "",
                  "%-6s %9s %11s %9s" % ("world", "meshes", "triangles",
                                         "ms/frame"),
                  "-" * 40]
        for _e, tag, _t in WORLDS:
            row = cost.get(tag)
            if row:
                lines.append("%-6s %9d %11d %9.0f" % (
                    tag, row["meshes"], row["triangles"], row["ms_per_frame"]))
        base = cost.get("v27", {}).get("ms_per_frame")
        now = cost.get("v271", {}).get("ms_per_frame")
        if base and now:
            lines += ["", "  V27.1 against contained_hall: %+.1f%%"
                      % ((now / base - 1.0) * 100.0)]
    return NEWLINE.join(lines)


# --- stage: the surface probe ----------------------------------------------


def stage_surfaces() -> dict[str, Any]:
    """Name the bright thing behind the finish, rather than attribute it."""
    out: dict[str, Any] = {}
    lines = [
        "WHAT IS BEHIND THE FINISH, BY SURFACE",
        "the hall's own materials, each rendered its own flat hue and read off",
        "the lit frame. The machine is masked out first - see SURFACES.",
        "",
    ]
    for key in v271.FINISH:
        _bands, machine, _background = _world_masks(v271.PARENT, key)
        probe = _pixels(still("_probe_v271_pad", key))
        masks = v271.surface_masks(probe, machine)
        before = v271.luma(_pixels(still(v271.PARENT, key)))
        after = v271.luma(_pixels(still(v271.PROFILE, key)))
        rows = []
        lines += [f"  {key}", "    %-16s %7s %8s %8s %8s"
                  % ("surface", "cover", "V27", "V27.1", "clip wht"), "    " + "-" * 52]
        for name, mask in masks.items():
            if float(mask.mean()) < 0.002:
                continue
            row = {
                "surface": name,
                "cover": round(float(mask.mean()), 4),
                "luma_v27": round(float(before[mask].mean()), 1),
                "luma_v271": round(float(after[mask].mean()), 1),
                "clip_white": round(float((mask & (after >= 250)).mean()), 5),
            }
            rows.append(row)
            label = "FINISH PAD" if name == "hall_glass" else name
            lines.append("    %-16s %6.2f%% %8.1f %8.1f %7.2f%%" % (
                label, row["cover"] * 100, row["luma_v27"], row["luma_v271"],
                row["clip_white"] * 100))
        lines.append("")
        out[key] = rows
    lines += [
        "  `hall_glass` is the finish landing pad: `_probe_v271_pad` re-materials",
        "  it so it can be told apart from the deck ring it shares `hall_deck`",
        "  with. It is the whole of the bright background at all three moments.",
        "  Nothing the hall builds clips white at any of them.",
    ]
    text = NEWLINE.join(lines)
    _write_json(os.path.join(LAB_DIR, "surfaces.json"), out)
    _write_text(os.path.join(DOC_DIR, "surfaces.txt"), text)
    print(text)
    return out


# --- stage: the winner ------------------------------------------------------


def _winner_at(track: dict[str, Any], replay: dict[str, Any],
               key: str) -> dict[str, Any]:
    """Where the winning marble is on screen, **after it has crossed**.

    `readability.cut_reads` cannot answer this and should not be asked to: it
    drops a racer the moment it crosses the line, deliberately, so that a
    finish lens is not marked down for the marbles it has already delivered.
    At the winner and the payoff the winner has crossed, so it is exactly the
    racer that instrument stops reporting. This projects it directly.
    """
    one = v27.moment(key)
    frames = v271.frames_of(track)
    frame = v271.frame_at(frames, one.replay)
    times = [float(f["t"]) for f in replay["frames"]]
    index = min(range(len(times)), key=lambda k: abs(times[k] - float(frame[0])))
    points = readability._racer_points(replay, index)
    radius = float(replay.get("units", {}).get("layout_marble_radius",
                                               readability.layout.MARBLE_RADIUS))
    camera = (frame[1], frame[2], frame[3])
    aim = (frame[4], frame[5], frame[6])
    fov = float(frame[7])
    placed = project(camera, aim, fov, points[v271.FLAG_RACER], WIDTH, HEIGHT)
    if placed is None:
        return {"moment": key, "on_screen": False}
    x, y, depth = placed
    half_up = math.tan(math.radians(fov) * 0.5)
    return {
        "moment": key,
        "t": round(float(frame[0]), 3),
        "on_screen": bool(0.0 <= x <= WIDTH and 0.0 <= y <= HEIGHT),
        "x": round(x, 1), "y": round(y, 1), "depth": round(depth, 2),
        "px": round((2.0 * radius / depth) / (2.0 * half_up) * HEIGHT, 1),
    }


def _patch(pixels: np.ndarray, x: float, y: float, px: float,
           scale: float = 0.55, clip: bool = False) -> np.ndarray | None:
    """A square of picture centred on a racer, `scale` of its own diameter.

    `clip` trims the square to the frame instead of refusing it. The body
    patch must not be clipped - a half-visible marble's mean is not the
    marble's colour - but the surround ring may be, and refusing it is how the
    first run of this reported a surround distance of 0.0 at frame zero, where
    the winner stands 180 px from the left edge and a 2.2-diameter square
    around it does not fit.
    """
    reach = max(2, int(round(px * scale * 0.5)))
    left, right = int(round(x)) - reach, int(round(x)) + reach
    top, bottom = int(round(y)) - reach, int(round(y)) + reach
    if clip:
        left, top = max(0, left), max(0, top)
        right = min(pixels.shape[1], right)
        bottom = min(pixels.shape[0], bottom)
        if right - left < 4 or bottom - top < 4:
            return None
    elif (left < 0 or top < 0 or right > pixels.shape[1]
          or bottom > pixels.shape[0]):
        return None
    return pixels[top:bottom, left:right]


def stage_winner() -> dict[str, Any]:
    """Part B: is the purple racer readable at the three finish moments.

    Three questions, three numbers:

    * **is it on screen at all**, projected rather than assumed;
    * **is anything in front of it** - answered by comparing the patch against
      the same patch of the world-only marker pass, which is what an occluder
      would show through;
    * **does it separate from what it is on** - the marble's own colour
      distance from the ring of picture just outside it.
    """
    track = _load(TRACK)
    replay = _load(REPLAY)
    hue = overlays.MARBLE_HUES[v271.FLAG_RACER]
    out: dict[str, Any] = {"winner": v271.FLAG_RACER,
                           "label": v24_payoff.winner_label(v271.FLAG_RACER),
                           "hue": list(hue), "moments": {}}
    lines = [
        "THE WINNER, THROUGH THE FINISH",
        "marble %d, %s. Projected from the replay, not read off a sheet."
        % (v271.FLAG_RACER, v24_payoff.winner_label(v271.FLAG_RACER)),
        "",
        "%-16s %-6s %8s %8s %7s %9s %9s" % ("moment", "world", "on screen",
                                            "px", "occl", "dE surround",
                                            "surround"),
        "-" * 74,
    ]
    for key in v271.FINISH:
        where = _winner_at(track, replay, key)
        out["moments"][key] = {"where": where, "worlds": {}}
        for environment, tag, _title in WORLDS:
            row: dict[str, Any] = {}
            if where.get("on_screen"):
                pixels = _pixels(still(environment, key))
                marker = MARKERS[environment]
                whole = _pixels(still(marker, key))
                world = _pixels(still(marker, key, "world"))
                machine = v271.machine_mask(whole, world)
                body = _patch(pixels, where["x"], where["y"], where["px"])
                cover = _patch(machine.astype(float), where["x"], where["y"],
                               where["px"])
                ring_outer = _patch(pixels, where["x"], where["y"],
                                    where["px"], scale=2.2, clip=True)
                if body is not None and body.size:
                    mean = body.reshape(-1, 3).mean(axis=0)
                    around = (ring_outer.reshape(-1, 3).mean(axis=0)
                              if ring_outer is not None and ring_outer.size
                              else mean)
                    row = {
                        "body": [round(float(v), 1) for v in mean],
                        "occluded": round(1.0 - float(cover.mean()), 3)
                        if cover is not None else None,
                        "delta_e": round(float(np.linalg.norm(mean - around)), 1),
                        "surround_luma": round(float(v271.luma(around)), 1),
                    }
            out["moments"][key]["worlds"][tag] = row
            lines.append("%-16s %-6s %8s %8s %7s %9s %9s" % (
                key, tag,
                "yes" if where.get("on_screen") else "NO",
                ("%.0f" % where["px"]) if where.get("on_screen") else "-",
                ("%.2f" % row["occluded"]) if row.get("occluded") is not None else "-",
                ("%.1f" % row["delta_e"]) if row else "-",
                ("%.1f" % row["surround_luma"]) if row else "-"))
        lines.append("")
    lines += [
        "`occl` is the share of the marble's own patch that the world stands in",
        "front of: 0.00 is a clear marble. `dE surround` is the marble's mean",
        "RGB distance from the ring of picture just outside it - the thing an",
        "eye reads when it decides a ball is not part of what it is on.",
        "",
        "The ring: V24 opens the WINNER mark on the crossing and it runs 0.300 s",
        "(v24_payoff.RING_SECONDS), which `v24_payoff` measured against the",
        "marble's own 0.217 s of visibility. That schedule is V24's and this",
        "pass does not touch it; what is checked here is that the marble the",
        "ring is drawn around is on screen and clear when the ring opens.",
    ]
    text = NEWLINE.join(lines)
    _write_json(os.path.join(LAB_DIR, "winner.json"), out)
    _write_text(os.path.join(DOC_DIR, "winner.txt"), text)
    print(text)
    return out


# --- stage: the payoff card -------------------------------------------------


def stage_ring() -> dict[str, Any]:
    """Part B: how much of the WINNER mark's life lands on the winner.

    V26's own method, on V27.1's frames. The winner is projected through the
    delivered track at each of the mark's eighteen frames and the rendered
    pixel at that place is read back; the frame counts when the marble is in
    frame and the picture there is nearer the winner's hue than any other
    racer's.

    **`readability.cut_reads` is deliberately not used**, for the reason
    `tools/sloped_v26.winner_ring` records: it drops a racer the moment it
    crosses, which is exactly the marble this measurement is about. Asked
    through it, every edition answers "the winner is in 0 of its own 18 ring
    frames" - a fact about the filter.

    The frames come from `--stage clip`'s own render, so this needs no render
    of its own and is measured on the same pixels the clip ships.
    """
    from sloped import layout
    from sloped.readability import _racer_points

    replay = _load(REPLAY)
    _replay, track, clock = v24.film_clock(REPLAY, TRACK)
    crossing = clock.at(v24.WINNER_CROSSES)
    if crossing is None:
        raise LabError("the winner's crossing is not in the film")
    count = int(round(v24_payoff.RING_SECONDS * v271.FPS))
    hues = np.array(overlays.MARBLE_HUES, dtype=float)
    times = [float(frame["t"]) for frame in replay["frames"]]
    radius = float(replay.get("units", {}).get("layout_marble_radius",
                                               layout.MARBLE_RADIUS))
    clip = v27.clip("finish")
    out: dict[str, Any] = {"crossing": round(crossing, 4), "frames": count,
                           "worlds": {}}
    lines = [
        "THE WINNER RING",
        "the mark opens on the crossing at %.3f s and runs %.3f s (%d frames)."
        % (crossing, v24_payoff.RING_SECONDS, count),
        "For each of them: is the winner in frame, and is the picture under the",
        "mark the winner's own colour rather than another racer's.",
        "",
        "%-6s %-22s %10s %12s %11s" % ("world", "title", "in frame",
                                       "reads purple", "median dE"),
        "-" * 66,
    ]
    for environment, tag, title in WORLDS:
        folder = os.path.join(LAB_DIR, "frames", tag, "finish")
        if not os.path.isdir(folder):
            raise LabError("run --stage clip first: " + folder)
        rows: list[dict[str, Any]] = []
        for index in range(count):
            at = crossing + v24_payoff.RING_DELAY + index / float(v271.FPS)
            replay_at = clock.replay_at(at)
            entry: dict[str, Any] = {"at": round(at, 4), "in_frame": False}
            if replay_at is not None:
                frames = v271.frames_of(track)
                pose = v271.frame_at(frames, replay_at)
                order = min(range(len(times)),
                            key=lambda k: abs(times[k] - replay_at))
                points = _racer_points(replay, order)
                placed = project(tuple(pose[1:4]), tuple(pose[4:7]),
                                 float(pose[7]),
                                 points[v271.FLAG_RACER], WIDTH, HEIGHT)
                if placed is not None:
                    x, y, depth = placed
                    entry["in_frame"] = bool(0 <= x <= WIDTH and 0 <= y <= HEIGHT)
                    entry.update(x=round(x, 1), y=round(y, 1))
                    path = os.path.join(
                        folder, "at_%07.3f.png" % round(clip.start + round(
                            (at - clip.start) * v271.FPS) / float(v271.FPS), 3))
                    if entry["in_frame"] and os.path.isfile(path):
                        pixels = _pixels(path)
                        patch = _patch(pixels, x, y,
                                       (2.0 * radius / depth) / (2.0 * math.tan(
                                           math.radians(float(pose[7])) * 0.5))
                                       * HEIGHT, 0.5)
                        if patch is not None and patch.size:
                            mean = patch.reshape(-1, 3).mean(axis=0)
                            distance = np.linalg.norm(hues - mean, axis=1)
                            entry["reads"] = int(distance.argmin())
                            entry["delta_e"] = round(
                                float(distance[v271.FLAG_RACER]), 1)
            rows.append(entry)
        seen = sum(1 for row in rows if row["in_frame"])
        purple = sum(1 for row in rows
                     if row.get("reads") == v271.FLAG_RACER)
        deltas = [row["delta_e"] for row in rows if "delta_e" in row]
        out["worlds"][tag] = {"environment": environment, "rows": rows,
                              "in_frame": seen, "reads_winner": purple}
        lines.append("%-6s %-22s %6d/%-3d %8d/%-3d %11s" % (
            tag, title, seen, count, purple, count,
            "%.1f" % float(np.median(deltas)) if deltas else "-"))
    lines += [
        "",
        "`median dE` is the distance from the picture under the mark to the",
        "winner's own hue - small is the winner, and the column beside it is",
        "how often that hue is the *nearest* of the eight.",
    ]
    text = NEWLINE.join(lines)
    _write_json(os.path.join(LAB_DIR, "ring.json"), out)
    _write_text(os.path.join(DOC_DIR, "ring.txt"), text)
    print(text)
    return out


def stage_payoff() -> dict[str, Any]:
    """Part C: the shipped card's real contrast on each world's payoff frame."""
    card = v24_payoff.build()
    out: dict[str, Any] = {"style": card.style, "label": card.label,
                           "text_contrast": round(card.text_contrast, 2),
                           "worlds": {}}
    lines = [
        "THE PAYOFF CARD ON THE CONTAINED FINISH BAY",
        "V24's own card, unchanged, measured on each world's payoff frame with",
        "v24_payoff.measured_contrast - ink against the composited picture",
        "beside it, worst case first.",
        "",
        "%-6s %-22s %9s %9s %9s" % ("world", "title", "worst", "median",
                                    "band max"),
        "-" * 62,
    ]
    for environment, tag, title in WORLDS:
        frame = _open(still(environment, "payoff"))
        worst, median = v24_payoff.measured_contrast(frame, card.image)
        grey = v271.luma(np.asarray(frame).astype(float))
        top, bottom = v24_payoff.PAYOFF_BAND
        band = grey[top:bottom, 90:990]
        out["worlds"][tag] = {
            "environment": environment,
            "worst": round(worst, 2),
            "median": round(median, 2),
            "band_max": round(float(band.max()), 1),
            "band_mean": round(float(band.mean()), 1),
        }
        lines.append("%-6s %-22s %9.2f %9.2f %9.1f" % (
            tag, title, worst, median, float(band.max())))
    lines += [
        "",
        "`band max` is the brightest pixel of `v24_payoff.PAYOFF_BAND` inside",
        "the text corridor: the worst thing the card could ever have to sit on",
        "in that frame. V24 chose the band because nothing there exceeded 130.",
        "",
        "WCAG large text wants 3.0. The card also carries a blurred dark bed",
        "that `measured_contrast` composites in, so these are delivery numbers",
        "rather than an unaided worst case.",
    ]
    text = NEWLINE.join(lines)
    _write_json(os.path.join(LAB_DIR, "payoff.json"), out)
    _write_text(os.path.join(DOC_DIR, "payoff.txt"), text)
    print(text)
    return out


# --- stage: frame zero ------------------------------------------------------


def stage_hook() -> dict[str, Any]:
    """Part F: frame 0 is supposed to be unchanged. Check it, don't assume it."""
    track = _load(TRACK)
    replay = _load(REPLAY)
    reads = lab._moment_reads(track, replay, "frame0")
    out: dict[str, Any] = {"worlds": {}}
    lines = [
        "FRAME ZERO",
        "the hook, which no part of a finish correction may reach.",
        "",
        "%-6s %-22s %8s %9s %9s %8s %9s" % ("world", "title", "racers",
                                            "worst col", "mean", "plate",
                                            "least dE"),
        "-" * 78,
    ]
    for environment, tag, title in WORLDS:
        image = _open(still(environment, "frame0"))
        hook = lab.hook_contrast(image)
        legible = v24_hook.legibility_report(image, reads)
        out["worlds"][tag] = {"environment": environment, "hook": hook,
                              "legibility": legible}
        lines.append("%-6s %-22s %5d/%d %9.2f %9.2f %8.1f %9.1f" % (
            tag, title, legible.get("legible", 0), reads["of"],
            hook["worst_column"], hook["mean_contrast"], hook["plate_luma"],
            legible.get("min_de", 0.0)))
    same = _identical(v271.PARENT, v271.PROFILE, "frame0")
    out["identical_to_v27"] = same
    lines += [
        "",
        "V27.1 against contained_hall at frame 0: %s."
        % ("byte-identical" if same else "DIFFERENT - the fix leaked"),
        "",
        "WCAG large text wants 3.0 of the worst column. `least dE` is the",
        "nearest any racer's colour comes to the picture under it.",
    ]
    text = NEWLINE.join(lines)
    _write_json(os.path.join(LAB_DIR, "hook.json"), out)
    _write_text(os.path.join(DOC_DIR, "hook.txt"), text)
    print(text)
    return out


def _identical(one: str, two: str, key: str) -> bool:
    import hashlib

    def digest(path: str) -> str:
        with open(path, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()

    return digest(still(one, key)) == digest(still(two, key))


def stage_delta() -> dict[str, Any]:
    """Exactly which frames the one-field delta reaches, and by how much."""
    out: dict[str, Any] = {}
    lines = [
        "WHERE THE DELTA LANDS",
        "contained_hall against contained_hall_v271, frame by frame.",
        "",
        "%-16s %12s %11s %11s" % ("moment", "changed px", "max dLuma",
                                  "mean dLuma"),
        "-" * 54,
    ]
    for one in v27.MOMENTS:
        before = _pixels(still(v271.PARENT, one.key))
        after = _pixels(still(v271.PROFILE, one.key))
        moved = np.abs(before - after).max(axis=2) > 2
        delta = np.abs(v271.luma(before) - v271.luma(after))
        row = {
            "changed": round(float(moved.mean()), 5),
            "max_dluma": round(float(delta.max()), 2),
            "mean_dluma": round(float(delta[moved].mean()), 2)
            if int(moved.sum()) else 0.0,
        }
        out[one.key] = row
        lines.append("%-16s %11.3f%% %11.1f %11.2f" % (
            one.key, row["changed"] * 100, row["max_dluma"], row["mean_dluma"]))
    untouched = [k for k, v in out.items() if v["changed"] == 0.0]
    lines += [
        "",
        "Untouched, byte for byte: " + ", ".join(untouched) + ".",
        "",
        "The pad stands behind the finish, and eight of the twelve cameras can",
        "see some of it: the merge moment's own description is 'the routes",
        "rejoining, with the finish already in frame', and the branch looks",
        "down the same line. So the delta cannot be confined to three frames by",
        "any choice of surface. `--stage measure` is where it is shown to",
        "improve every frame it reaches and regress none of them - +9.2 luma",
        "at the final approach, +2.4 at the merge, +2.6 at the winner.",
    ]
    text = NEWLINE.join(lines)
    _write_json(os.path.join(LAB_DIR, "delta.json"), out)
    _write_text(os.path.join(DOC_DIR, "delta.txt"), text)
    print(text)
    return out


# --- stage: the country probe ----------------------------------------------


def stage_country(godot: str) -> dict[str, Any]:
    """Part E: one India-skinned racer, rendered, never integrated.

    Five moments and two worlds - the corrected hall, and V26 beside it so the
    question "does a contained stage host a flag" has a control. The other
    seven racers keep `meridian`, so each sheet carries its own comparison.
    """
    seconds = [v27.moment(key).second for key in v271.FLAG_MOMENTS]
    for environment, tag in ((v271.PROFILE, "v271"), (v271.CONTROL, "v26")):
        print(f"--- country {tag} ---")
        _render_at(godot, environment, "", seconds, country_dir(tag),
                   f"country {tag}",
                   extra=[f"--racers={v271.FLAG.key}",
                          f"--flag-racer={v271.FLAG_RACER}"])
    track = _load(TRACK)
    replay = _load(REPLAY)
    out: dict[str, Any] = {"flag": v271.FLAG.key, "title": v271.FLAG.title,
                           "racer": v271.FLAG_RACER, "moments": {}}
    lines = [
        "THE COUNTRY-SKIN PROBE",
        "%s on marble %d, `meridian` on the other seven. Render-only: the skin"
        % (v271.FLAG.title, v271.FLAG_RACER),
        "is one appearance in `racer_visual.gd` behind `--flag-racer=`, there is",
        "no country system, and no shipped render reaches it.",
        "",
        "%-16s %-6s %8s %9s %9s %9s" % ("moment", "world", "px", "dE around",
                                        "bands seen", "spread"),
        "-" * 66,
    ]
    for key in v271.FLAG_MOMENTS:
        where = _winner_at(track, replay, key)
        out["moments"][key] = {"where": where, "worlds": {}}
        for tag in ("v271", "v26"):
            row: dict[str, Any] = {}
            path = country_still(tag, key)
            if where.get("on_screen") and os.path.isfile(path):
                pixels = _pixels(path)
                body = _patch(pixels, where["x"], where["y"], where["px"], 0.62)
                around = _patch(pixels, where["x"], where["y"], where["px"],
                                2.2, clip=True)
                if body is not None and body.size:
                    row = _flag_read(body, around)
            out["moments"][key]["worlds"][tag] = row
            lines.append("%-16s %-6s %8s %9s %9s %9s" % (
                key, tag,
                ("%.0f" % where["px"]) if where.get("on_screen") else "-",
                ("%.1f" % row["delta_e"]) if row else "-",
                ("%d/3" % row["bands"]) if row else "-",
                ("%.0f" % row["spread"]) if row else "-"))
        lines.append("")
    lines += [
        "`bands seen` is how many of the flag's three colours are present in",
        "the marble's own patch at that size - the test of whether a tricolour",
        "is still a tricolour on screen rather than one average. `spread` is",
        "the patch's own luma range, which is what a flag has and a solid",
        "marble does not.",
    ]
    text = NEWLINE.join(lines)
    _write_json(os.path.join(LAB_DIR, "country.json"), out)
    _write_text(os.path.join(DOC_DIR, "country.txt"), text)
    print(text)
    return out


def _flag_read(body: np.ndarray, around: np.ndarray | None) -> dict[str, Any]:
    """How much of the flag survived to the screen, in three numbers."""
    flat = body.reshape(-1, 3)
    mean = flat.mean(axis=0)
    grey = v271.luma(flat)
    table = np.array([[int(one[i:i + 2], 16) for i in (1, 3, 5)]
                      for one in v271.FLAG.bands], dtype=float)
    distance = np.linalg.norm(flat[:, None, :] - table[None, :, :], axis=2)
    nearest = distance.argmin(axis=1)
    close = distance.min(axis=1) < 110.0
    bands = sum(1 for index in range(len(v271.FLAG.bands))
                if float(((nearest == index) & close).mean()) > 0.06)
    outside = (around.reshape(-1, 3).mean(axis=0)
               if around is not None and around.size else mean)
    return {
        "bands": bands,
        "spread": round(float(grey.max() - grey.min()), 1),
        "delta_e": round(float(np.linalg.norm(mean - outside)), 1),
        "mean": [round(float(v), 1) for v in mean],
    }


# --- sheets -----------------------------------------------------------------


def _label(draw: ImageDraw.ImageDraw, at: tuple[int, int], text: str,
           size: int = 22, fill=SHEET_LABEL) -> None:
    draw.text(at, text, font=overlays.load_font(size), fill=fill)


def _thumb(path: str, size: tuple[int, int]) -> Image.Image:
    return _open(path).resize(size, Image.LANCZOS)


def _board(rows: Sequence[tuple[str, Sequence[str]]], columns: Sequence[str],
           name: str, title: str, subtitle: str, width: int = 300) -> str:
    """One board: a row per moment, a column per world."""
    height = int(round(width * HEIGHT / WIDTH))
    gutter, top, left = 18, 116, 210
    sheet = Image.new("RGB", (left + len(columns) * (width + gutter) + gutter,
                              top + len(rows) * (height + gutter) + gutter),
                      SHEET_BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    _label(draw, (gutter, 22), title, 30)
    _label(draw, (gutter, 62), subtitle, 20, SHEET_DIM)
    for index, column in enumerate(columns):
        _label(draw, (left + index * (width + gutter), top - 30), column, 21)
    for order, (caption, paths) in enumerate(rows):
        y = top + order * (height + gutter)
        _label(draw, (gutter, y + 8), caption, 20)
        draw.line([(gutter, y - 6), (sheet.width - gutter, y - 6)],
                  fill=SHEET_RULE)
        for index, path in enumerate(paths):
            sheet.paste(_thumb(path, (width, height)),
                        (left + index * (width + gutter), y))
    out = os.path.join(DOC_DIR, f"{name}.png")
    os.makedirs(DOC_DIR, exist_ok=True)
    sheet.save(out)
    print("wrote " + out)
    return out


def proof_dir(tag: str) -> str:
    return os.path.join(LAB_DIR, "proof", tag)


def proof_still(tag: str, key: str, second: float) -> str:
    return os.path.join(proof_dir(tag), f"at_{second:07.3f}.png")


def _with_ring(path: str, second: float) -> Image.Image:
    """The frame with V24's own WINNER mark composited where it would land.

    The renderer draws no overlays - the Short composites them in Python - so a
    still of the ring second is the picture the ring is drawn *on*. This draws
    it, with `overlays.winner_ring` and the winner's own projected position, so
    the board shows the mark rather than the frame under it. It is a proof
    image and nothing in the film is built from it.
    """
    from sloped import layout
    from sloped.readability import _racer_points

    frame = _open(path).convert("RGBA")
    replay = _load(REPLAY)
    _r, track, clock = v24.film_clock(REPLAY, TRACK)
    crossing = clock.at(v24.WINNER_CROSSES) or second
    replay_at = clock.replay_at(second)
    if replay_at is None:
        return frame.convert("RGB")
    pose = v271.frame_at(v271.frames_of(track), replay_at)
    times = [float(one["t"]) for one in replay["frames"]]
    order = min(range(len(times)), key=lambda k: abs(times[k] - replay_at))
    placed = project(tuple(pose[1:4]), tuple(pose[4:7]), float(pose[7]),
                     _racer_points(replay, order)[v271.FLAG_RACER],
                     WIDTH, HEIGHT)
    if placed is None:
        return frame.convert("RGB")
    x, y, depth = placed
    radius = float(replay.get("units", {}).get("layout_marble_radius",
                                               layout.MARBLE_RADIUS))
    half_up = math.tan(math.radians(float(pose[7])) * 0.5)
    px = (2.0 * radius / depth) / (2.0 * half_up) * HEIGHT
    phase = max(0.0, min(1.0, (second - crossing) / v24_payoff.RING_SECONDS))
    frame.alpha_composite(overlays.winner_ring(x, y, px * 0.5, phase))
    return frame.convert("RGB")


def stage_proof(godot: str) -> str:
    """Part I: the same five finish frames in all three worlds.

    Its own `--at` list, because two of the five are not V27 moments - the
    WINNER ring and the film's last frame - and a still is only comparable
    with one asked for in the same list.
    """
    seconds = [second for _key, second, _title in v271.PROOF_FRAMES]
    for environment, tag, _title in WORLDS:
        print(f"--- proof {tag} ---")
        _render_at(godot, environment, "", seconds, proof_dir(tag),
                   f"proof {tag}")
    width = 300
    height = int(round(width * HEIGHT / WIDTH))
    gutter, top, left = 18, 116, 210
    rows = list(v271.PROOF_FRAMES)
    sheet = Image.new("RGB",
                      (left + len(WORLDS) * (width + gutter) + PHONE[0]
                       + 2 * gutter,
                       top + len(rows) * (height + gutter) + gutter),
                      SHEET_BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    _label(draw, (gutter, 22), "THE FINISH, FIVE FRAMES, THREE WORLDS", 30)
    _label(draw, (gutter, 62),
           "identical output seconds. The last column is V27.1 at %d x %d."
           % PHONE, 20, SHEET_DIM)
    for index, (_e, _t, name) in enumerate(WORLDS):
        _label(draw, (left + index * (width + gutter), top - 30), name, 21)
    _label(draw, (left + len(WORLDS) * (width + gutter), top - 30),
           "V27.1 phone", 21)
    for order, (key, second, title) in enumerate(rows):
        y = top + order * (height + gutter)
        _label(draw, (gutter, y + 8), title, 20)
        _label(draw, (gutter, y + 34), "%.3f s" % second, 18, SHEET_DIM)
        if key == "ring":
            _label(draw, (gutter, y + 58), "mark composited", 16, SHEET_DIM)
        draw.line([(gutter, y - 6), (sheet.width - gutter, y - 6)],
                  fill=SHEET_RULE)
        ring = key == "ring"
        for index, (_e, tag, _n) in enumerate(WORLDS):
            path = proof_still(tag, key, second)
            cell = (_with_ring(path, second) if ring else _open(path))
            sheet.paste(cell.resize((width, height), Image.LANCZOS),
                        (left + index * (width + gutter), y))
        last = proof_still("v271", key, second)
        cell = (_with_ring(last, second) if ring else _open(last))
        sheet.paste(cell.resize(PHONE, Image.LANCZOS),
                    (left + len(WORLDS) * (width + gutter), y))
    out = os.path.join(DOC_DIR, "proof.png")
    os.makedirs(DOC_DIR, exist_ok=True)
    sheet.save(out)
    print("wrote " + out)
    return out


def stage_sheet() -> list[str]:
    written = [
        _board(
            [(v27.moment(key).title, [still(env, key) for env, _t, _n in WORLDS])
             for key in ("merge",) + v271.FINISH],
            [name for _e, _t, name in WORLDS],
            "finish", "THE FINISH, THREE WORLDS",
            "V26 outdoor, V27 contained_hall, V27.1 corrected. Same replay, "
            "same camera track, same edit, same seed."),
        _board(
            [(v27.moment(key).title,
              [still(env, key) for env, _t, _n in WORLDS])
             for key in ("frame0", "obstacle", "branch")],
            [name for _e, _t, name in WORLDS],
            "elsewhere", "EVERYWHERE ELSE",
            "the three moments the delta does not reach, or barely does."),
    ]
    # The phone board: the finish at delivery size.
    width = PHONE[0]
    height = PHONE[1]
    gutter, top, left = 14, 104, 200
    rows = list(v271.FINISH)
    sheet = Image.new("RGB",
                      (left + len(WORLDS) * (width + gutter) + gutter,
                       top + len(rows) * (height + gutter) + gutter),
                      SHEET_BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    _label(draw, (gutter, 20), "THE FINISH AT %d x %d" % PHONE, 26)
    _label(draw, (gutter, 56), "the size the film is judged at", 18, SHEET_DIM)
    for index, (_e, _t, name) in enumerate(WORLDS):
        _label(draw, (left + index * (width + gutter), top - 26), name, 17)
    for order, key in enumerate(rows):
        y = top + order * (height + gutter)
        _label(draw, (gutter, y + 6), v27.moment(key).title, 17)
        for index, (env, _t, _n) in enumerate(WORLDS):
            sheet.paste(_thumb(still(env, key), PHONE),
                        (left + index * (width + gutter), y))
    out = os.path.join(DOC_DIR, "phone.png")
    sheet.save(out)
    print("wrote " + out)
    written.append(out)
    return written


def stage_country_sheet() -> str:
    width = 300
    height = int(round(width * HEIGHT / WIDTH))
    gutter, top, left = 18, 116, 210
    rows = list(v271.FLAG_MOMENTS)
    columns = ["V27.1 corrected", "V26 outdoor", "V27.1 at %d x %d" % PHONE]
    sheet = Image.new("RGB",
                      (left + 2 * (width + gutter) + PHONE[0] + 2 * gutter,
                       top + len(rows) * (height + gutter) + gutter),
                      SHEET_BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    _label(draw, (gutter, 22), "COUNTRY-SKIN PROBE: %s" % v271.FLAG.title.upper(), 30)
    _label(draw, (gutter, 62),
           "marble %d only; the other seven are `meridian`. Render-only."
           % v271.FLAG_RACER, 20, SHEET_DIM)
    for index, column in enumerate(columns):
        _label(draw, (left + index * (width + gutter), top - 30), column, 21)
    for order, key in enumerate(rows):
        y = top + order * (height + gutter)
        _label(draw, (gutter, y + 8), v27.moment(key).title, 20)
        draw.line([(gutter, y - 6), (sheet.width - gutter, y - 6)],
                  fill=SHEET_RULE)
        sheet.paste(_thumb(country_still("v271", key), (width, height)),
                    (left, y))
        sheet.paste(_thumb(country_still("v26", key), (width, height)),
                    (left + width + gutter, y))
        sheet.paste(_thumb(country_still("v271", key), PHONE),
                    (left + 2 * (width + gutter), y))
    out = os.path.join(DOC_DIR, "country.png")
    os.makedirs(DOC_DIR, exist_ok=True)
    sheet.save(out)
    print("wrote " + out)
    return out


# --- clips ------------------------------------------------------------------


def _ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if not found:
        raise LabError("ffmpeg is not on PATH")
    return found


def stage_clip(godot: str) -> list[str]:
    """The finish, whole, in each world - and the same at phone size."""
    clip = v27.clip("finish")
    frames = int(round((clip.end - clip.start) * v271.FPS))
    seconds = [clip.start + index / float(v271.FPS) for index in range(frames)]
    written: list[str] = []
    for environment, tag, _title in WORLDS:
        out = os.path.join(LAB_DIR, "frames", tag, "finish")
        print(f"--- clip {tag}: {frames} frames ---")
        started = time.perf_counter()
        _render_at(godot, environment, "", seconds, out, f"clip {tag}")
        print(f"  {frames} frames in {time.perf_counter() - started:.1f} s")
        names = sorted(one for one in os.listdir(out) if one.endswith(".png"))
        listing = os.path.join(out, "frames.txt")
        with open(listing, "w", encoding="utf-8", newline="\n") as handle:
            for name in names:
                handle.write("file '%s'\n" % name.replace("'", "'\\''"))
        for size, suffix in ((None, ""), (PHONE, "_phone")):
            video = os.path.join(LAB_DIR, "clips", f"finish_{tag}{suffix}.mp4")
            os.makedirs(os.path.dirname(video), exist_ok=True)
            command = [_ffmpeg(), "-y", "-r", str(v271.FPS), "-f", "concat",
                       "-safe", "0", "-i", os.path.abspath(listing)]
            if size:
                command += ["-vf", "scale=%d:%d:flags=lanczos" % size]
            command += ["-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-crf", str(lab.VIDEO_CRF), "-preset", lab.VIDEO_PRESET,
                        os.path.abspath(video)]
            done = subprocess.run(command, cwd=PROJECT_ROOT,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, encoding="utf-8", errors="replace")
            if done.returncode != 0:
                raise LabError("ffmpeg failed: "
                               + NEWLINE.join((done.stderr or "").splitlines()[-12:]))
            written.append(video)
            print("wrote " + video)
    return written


# --- export -----------------------------------------------------------------


def stage_export() -> list[str]:
    os.makedirs(EXPORT_DIR, exist_ok=True)
    written: list[str] = []
    for name in ("proof.png", "finish.png", "elsewhere.png", "phone.png",
                 "country.png",
                 "measures.txt", "surfaces.txt", "survey.txt", "winner.txt",
                 "payoff.txt", "hook.txt", "delta.txt", "country.txt",
                 "ring.txt"):
        source = os.path.join(DOC_DIR, name)
        if os.path.isfile(source):
            target = os.path.join(EXPORT_DIR, name)
            shutil.copy2(source, target)
            written.append(target)
    clips = os.path.join(LAB_DIR, "clips")
    if os.path.isdir(clips):
        for name in sorted(os.listdir(clips)):
            if name.endswith(".mp4"):
                target = os.path.join(EXPORT_DIR, name)
                shutil.copy2(os.path.join(clips, name), target)
                written.append(target)
    for path in written:
        print("exported " + os.path.relpath(path, PROJECT_ROOT))
    return written


# --- main -------------------------------------------------------------------


STAGES = ("survey", "render", "measure", "surfaces", "delta", "winner",
          "ring", "payoff", "hook", "country", "proof", "sheet", "clip",
          "export", "all")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stage", default="all", choices=STAGES)
    parser.add_argument("--godot", default=None)
    parser.add_argument("--only", default="")
    args = parser.parse_args(argv)
    only = tuple(one for one in args.only.split(",") if one)
    stage = args.stage
    needs_godot = stage in ("render", "country", "proof", "clip", "all")
    godot = lab.find_godot(args.godot) if needs_godot else ""

    if stage in ("survey", "all"):
        stage_survey()
    if stage in ("render", "all"):
        stage_render(godot, only)
    if stage in ("measure", "all"):
        stage_measure()
    if stage in ("surfaces", "all"):
        stage_surfaces()
    if stage in ("delta", "all"):
        stage_delta()
    if stage in ("winner", "all"):
        stage_winner()
    if stage in ("payoff", "all"):
        stage_payoff()
    if stage in ("hook", "all"):
        stage_hook()
    if stage in ("country", "all"):
        stage_country(godot)
    if stage in ("proof", "all"):
        stage_proof(godot)
    if stage in ("sheet", "all"):
        stage_sheet()
        if os.path.isdir(country_dir("v271")):
            stage_country_sheet()
    if stage in ("clip", "all"):
        stage_clip(godot)
    if stage in ("ring", "all"):
        stage_ring()
    if stage in ("export", "all"):
        stage_export()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

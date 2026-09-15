"""V27: render three contained stages against the V26 outdoor control, and
measure what changed.

    envelope   what the V26 camera track can see, as a polar table. No render.
    sites      where a form can legally stand at each race node. No render.
    render     the twelve moments per world, plus two marker passes each
    sheet      the contact, phone, opening, middle, finish and hook boards
    measure    measures.json and the table the doc quotes
    parallax   five camera moves, per depth band, per world
    clip       the whole Short per world, its three windows, and the
               four-up comparison strips
    score      the brief's Part Y decision table
    export     everything above into exports/v27_contained_environment/
    all        all of it, in that order

    python tools/sloped_v27_contained.py --stage all --godot PATH
    python tools/sloped_v27_contained.py --stage render --only a,b --godot PATH

Four worlds - V26 as the control, then A, B and C - through **V24's own solved
camera track**, over the locked seed-5432 replay, at the same twelve output
seconds. The only flag that differs between two renders here is
`--environment=`; `--machine=v23b`, `--racers=meridian`, `--finish-sign=double`,
the layout, the detail level and the route set are identical in all four, and
so is every number in `cameras_v24_5432.json`.

**Nothing here touches the physics.** The replay and the camera track are read
and never written, no stage runs a simulation, the seed is 5432 in every render
and the frame at a given output second is the frame the film has at that
second. `tests/test_sloped_v27_contained.py` asserts all of that against the
files rather than against this docstring.

**One still is only comparable with another from the same `--at` list.** The
renderer accumulates between samples inside one process, so output second 9.600
asked for as the second of three frames and as the fifth of twelve are
different images - byte-different, and visibly so at the edges of a moving
subject. Every stage here therefore asks for its whole list in one call, and a
later pass comparing against these frames has to ask for the same twelve
seconds in the same order. This was found while proving that a V26 render is
unchanged by the pass, which it is; the first comparison said otherwise and the
difference was entirely the list.

## The two stages that are not proofs

`--stage envelope` and `--stage sites` render nothing. They are measurements of
the *camera track*, and they are first in the list because they decided most of
what the three profiles contain:

    envelope   the highest point at each plan position that any V26 frame can
               see. It is what says a ceiling over the machine is invisible and
               that a third of the compass is never in shot.
    sites      where a form can legally stand: clear of the racing line, clear
               of the camera path, inside some cut's frustum, and behind the
               action rather than in front of it.

Both print tables that are quoted in `docs/sloped_race_v27_contained.md`, and
both are cheap enough to re-run whenever a camera solve changes.
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

sys.path.insert(0, os.getcwd())

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from sloped import layout, overlays, readability, terrain, v24, v24_hook
from sloped import v27_contained as v27

PROJECT_ROOT = os.getcwd()
GODOT_PROJECT = os.path.join(PROJECT_ROOT, "godot")
RENDER_SCENE = "res://scenes/SlopedRaceRender.tscn"

SEED = v27.SEED
WIDTH, HEIGHT, FPS = v27.WIDTH, v27.HEIGHT, v27.FPS
PHONE = v27.PHONE
VIDEO_CRF = 18
VIDEO_PRESET = "medium"

OUT_DIR = os.path.join("output", "sloped_race_v1")
LAB_DIR = os.path.join(OUT_DIR, "v27_contained")
DOC_DIR = os.path.join("docs", "validation", "sloped_race_v1", "v27_contained")
EXPORT_DIR = os.path.join("exports", "v27_contained_environment")

REPLAY = os.path.join(OUT_DIR, f"race_{SEED}.json")
TRACK = os.path.join(OUT_DIR, f"cameras_v24_{SEED}.json")
START_CONTRACT = os.path.join(OUT_DIR, f"start_contract_{SEED}.json")

#: The machine, racer and board flags. Identical in every render this tool
#: makes, so that a difference between two frames is a difference of world.
FIXED_FLAGS = ("--layout=b", "--detail=hero", "--routes=both",
               "--finish-sign=double", "--machine=v23b", "--racers=meridian")

# The sheet's furniture, V25's exactly: dark and plain, so a cell is judged on
# what is in it rather than against the paper it is printed on.
SHEET_BACKGROUND = (14, 14, 17)
SHEET_LABEL = (238, 238, 234)
SHEET_DIM = (146, 150, 160)
SHEET_RULE = (44, 46, 54)

#: Written out because several of the report builders below are themselves
#: written by a patch script, and a literal escape in one of those is a
#: newline by the time it reaches the file.
NEWLINE = chr(10)


class LabError(RuntimeError):
    pass


# --- inputs -----------------------------------------------------------------


def _require_inputs() -> None:
    for path in (REPLAY, TRACK, START_CONTRACT):
        if not os.path.isfile(path):
            raise LabError(
                f"missing input: {path}\n"
                "  it is generated output and not in the branch; copy it from a "
                "tree that has it."
            )


def find_godot(explicit: str | None) -> str:
    if explicit:
        if os.path.isfile(explicit):
            return explicit
        found = shutil.which(explicit)
        if found:
            return found
        raise LabError(f"--godot does not name an executable: {explicit}")
    for variable in ("GODOT_BIN", "GODOT4_BIN"):
        value = os.environ.get(variable)
        if value and os.path.isfile(value):
            return value
    for name in ("godot", "godot4"):
        found = shutil.which(name)
        if found:
            return found
    raise LabError(
        "cannot find Godot 4. Pass --godot PATH, set $GODOT_BIN, or put it on "
        "PATH.")


def _load(path: str) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: str, payload: Any) -> None:
    v27.write_json(path, payload)


def _write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text.rstrip("\n") + "\n")


# --- paths ------------------------------------------------------------------


def stills_dir(environment: str, layers: str = "") -> str:
    tag = environment if not layers else f"{environment}@{layers}"
    return os.path.join(LAB_DIR, "stills", tag)


def still(environment: str, key: str, layers: str = "") -> str:
    return os.path.join(stills_dir(environment, layers),
                        f"at_{v27.moment(key).second:07.3f}.png")


def frames_dir(tag: str, clip: str) -> str:
    return os.path.join(LAB_DIR, "frames", tag, clip)


def video_path(tag: str, clip: str) -> str:
    return os.path.join(LAB_DIR, "clips", f"{clip}_{tag}.mp4")


def parallax_dir(tag: str) -> str:
    return os.path.join(LAB_DIR, "parallax", tag)


def _open(path: str) -> Image.Image:
    if not os.path.isfile(path):
        raise LabError(f"missing render: {path}\nRun --stage render first.")
    return Image.open(path).convert("RGB")


# --- running Godot ----------------------------------------------------------


def _scene_flags(environment: str, layers: str = "") -> list[str]:
    flags = [
        f"--replay={os.path.abspath(REPLAY)}",
        f"--cameras={os.path.abspath(TRACK)}",
        f"--start-contract={os.path.abspath(START_CONTRACT)}",
        f"--width={WIDTH}", f"--height={HEIGHT}",
        *FIXED_FLAGS,
        f"--environment={environment}",
    ]
    if layers:
        flags.append(f"--layers={layers}")
    return flags


def run_godot(godot: str, extra: Sequence[str], label: str) -> str:
    completed = subprocess.run(
        [godot, "--path", GODOT_PROJECT, RENDER_SCENE, "--", *extra],
        cwd=PROJECT_ROOT, stderr=subprocess.PIPE, stdout=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
    )
    errors = "\n".join((completed.stderr or "").splitlines()[-40:])
    if completed.returncode != 0:
        raise LabError(f"{label}: Godot exited {completed.returncode}\n{errors}")
    for line in (completed.stderr or "").splitlines():
        if "SCRIPT ERROR" in line or "Parse Error" in line:
            raise LabError(f"{label}: Godot reported an error: {line.strip()}")
        # A rejected placement is a mistake in a profile and a profile is data,
        # so it is surfaced here rather than buried in a log nobody reads.
        if "environment_stage:" in line or "environment_world:" in line:
            print("  ! " + line.split(": ", 1)[-1].strip())
    return completed.stdout or ""


def _render_at(godot: str, environment: str, layers: str,
               seconds: Sequence[float], out: str, label: str) -> str:
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out, exist_ok=True)
    stdout = run_godot(godot, [
        f"--out-dir={os.path.abspath(out)}",
        "--at=" + ",".join(f"{one:.3f}" for one in seconds),
        *_scene_flags(environment, layers),
    ], label)
    written = sorted(one for one in os.listdir(out) if one.endswith(".png"))
    if len(written) != len(seconds):
        raise LabError(
            f"{label}: asked for {len(seconds)} frames, got {len(written)}")
    return stdout


# --- stage: envelope --------------------------------------------------------


def stage_envelope() -> dict[str, Any]:
    """What the V26 camera track can and cannot see, as a polar table.

    The measurement the rest of this pass is built on. It reads a camera track
    and nothing else - no render, no replay, no profile - so it is true of
    every edition that shares V24's cameras, and it would be equally true of an
    empty scene.
    """
    _require_inputs()
    frames = v27.frames_of(_load(TRACK))
    grid = v27.ceiling_grid(frames)
    unseen = v27.unseen_arc(grid)
    heights = [row[1] for row in
               [(f[0], f[2]) for f in frames]]
    report = {
        "frames": len(frames),
        "camera_y": [round(min(heights), 2), round(max(heights), 2)],
        "grid": {
            str(row["radius"]): {str(k): (None if v is None else round(v, 1))
                                 for k, v in row["cells"].items()}
            for row in grid["rows"]
        },
        "bearings_seen": grid["bearings_seen"],
        "unseen_arcs": unseen,
        "top_edge_below_horizon_deg": round(min(
            float(f[7]) * -0.5 + math.degrees(math.atan2(
                -(f[5] - f[2]), math.hypot(f[4] - f[1], f[6] - f[3])))
            for f in frames), 2),
    }
    _write_json(os.path.join(LAB_DIR, "envelope.json"), report)
    text = _envelope_table(grid, report)
    _write_text(os.path.join(DOC_DIR, "envelope.txt"), text)
    print(text)
    return report


def _envelope_table(grid: dict[str, Any], report: dict[str, Any]) -> str:
    bearings = [b for b in
                sorted({b for row in grid["rows"] for b in row["cells"]})]
    lines = [
        "THE VISIBLE CEILING",
        "the highest y at each plan position that lies inside any V26 frame,",
        "measured about the terrain centre (%.1f, %.1f). '-' is never in shot."
        % v27.CENTRE,
        "",
        "  r  |" + "".join("%7d" % b for b in bearings),
        "-----+" + "-" * (7 * len(bearings)),
    ]
    for row in grid["rows"]:
        cells = "".join(
            "      -" if row["cells"][b] is None else "%7.0f" % row["cells"][b]
            for b in bearings)
        lines.append("%4.0f |" % row["radius"] + cells)
    lines += [
        "",
        "camera eye height      %.1f to %.1f" % tuple(report["camera_y"]),
        "top of frame is always at least %.1f degrees BELOW horizontal"
        % report["top_edge_below_horizon_deg"],
        "never in any frame:    " + ", ".join(
            "%.0f to %.0f deg" % arc for arc in report["unseen_arcs"]) or "-",
    ]
    return "\n".join(lines)


# --- stage: sites -----------------------------------------------------------


def _centreline() -> list[tuple[float, float]]:
    """The racing line in plan, from the layout's own control points.

    Sampled along the control polygon rather than along the Catmull-Rom the
    scene builds, which makes it very slightly *inside* the true curve at a
    bend and therefore conservative: a site this accepts, the builder's own
    test accepts too. The builder is the authority and it complains in the
    render log; this is the search that stops a profile arriving there wrong.
    """
    out: list[tuple[float, float]] = []
    for run in layout.RUNS:
        controls = run["controls"]
        for index in range(len(controls) - 1):
            a, b = controls[index], controls[index + 1]
            steps = max(1, int(math.dist(a, b) / 0.5))
            for step in range(steps):
                t = step / steps
                out.append((a[0] + (b[0] - a[0]) * t,
                            a[2] + (b[2] - a[2]) * t))
        out.append((controls[-1][0], controls[-1][2]))
    return out


def _keepout() -> list[tuple[float, float]]:
    from sloped import environment as env

    return [(float(a), float(b))
            for a, b in env.resolve("contained_hall")["world"]["keepout"]]


def _in_frustum(frames: Sequence[Sequence[float]], x: float, z: float) -> int:
    hits = 0
    for frame in frames:
        px, pz = frame[1], frame[3]
        yaw = math.atan2(frame[4] - px, frame[6] - pz)
        angle = math.atan2(x - px, z - pz)
        offset = (angle - yaw + math.pi) % (2.0 * math.pi) - math.pi
        half_v = math.radians(frame[7]) / 2.0
        if abs(offset) <= math.atan(math.tan(half_v) * WIDTH / HEIGHT):
            hits += 1
    return hits


def stage_sites(clearance: float = 10.0, lens: float = 16.0) -> dict[str, Any]:
    """Where a form can legally stand at each race node, and how tall.

    Four conditions, and a site has to meet all of them:

        clear of the racing line       `clearance` units in plan
        clear of the camera path       `lens` units in plan
        inside a frustum               at one of the moments that name the node
        behind the action              further from the camera than the node

    The fifth column is what the search exists to produce: the **headroom**,
    which is the visible ceiling at that site minus the ground under it. It is
    what says the fork's architecture is 54 units tall and the finish's is 77,
    on a course whose whole drop is 37.
    """
    _require_inputs()
    frames = v27.frames_of(_load(TRACK))
    track_pts = _centreline()
    lens_pts = _keepout()
    cfg = terrain.terrain_config()
    tasks = {
        "obstacle": ("obstacle", ["obstacle", "fork_approach"]),
        "split": ("split", ["split", "branch"]),
        "merge": ("merge", ["merge"]),
        "finish": ("finish", ["final_approach", "winner", "payoff"]),
        "start": ("start", ["frame0", "mixer"]),
    }
    report: dict[str, Any] = {"clearance": clearance, "lens": lens,
                              "nodes": {}}
    lines = ["WHERE ARCHITECTURE CAN STAND",
             "legal (%.0f from the racing line, %.0f from the camera path), in "
             "frame, and behind the action." % (clearance, lens), ""]
    for name, (node, moments) in tasks.items():
        anchor = layout.NODES[node]
        want = []
        for key in moments:
            one = v27.moment(key)
            want.append(min(frames, key=lambda f: abs(f[0] - one.replay)))
        rows: list[dict[str, Any]] = []
        for dx in range(-40, 41, 2):
            for dz in range(-40, 41, 2):
                reach = math.hypot(dx, dz)
                if reach < 10.0 or reach > 40.0:
                    continue
                x, z = anchor[0] + dx, anchor[2] + dz
                to_track = min(math.hypot(x - a, z - b) for a, b in track_pts)
                to_lens = min(math.hypot(x - a, z - b) for a, b in lens_pts)
                if to_track < clearance or to_lens < lens:
                    continue
                seen = _in_frustum(want, x, z)
                if seen == 0:
                    continue
                behind = sum(
                    1 for f in want
                    if math.dist((x, z), (f[1], f[3]))
                    > math.dist((anchor[0], anchor[2]), (f[1], f[3])))
                ground = terrain.height(x, z, cfg)
                ceiling = v27.visible_ceiling(frames, x, z)
                if ceiling is None:
                    continue
                rows.append({
                    "offset": [dx, dz],
                    "bearing": round(math.degrees(math.atan2(dx, dz)) % 360, 1),
                    "in_frame": seen, "of": len(want), "behind": behind,
                    "ground": round(ground, 1),
                    "ceiling": round(ceiling, 1),
                    "headroom": round(ceiling - ground, 1),
                    "to_track": round(to_track, 1),
                    "to_lens": round(to_lens, 1),
                })
        rows.sort(key=lambda r: (-r["in_frame"], -r["behind"], -r["headroom"]))
        report["nodes"][name] = {"viable": len(rows), "best": rows[:6]}
        lines.append("%-9s node (%6.1f,%6.1f,%6.1f)   %d viable sites"
                     % (name, anchor[0], anchor[1], anchor[2], len(rows)))
        if not rows:
            lines.append("    none. no position within 40 units is legal, in "
                         "frame and behind the action at once.")
        for row in rows[:4]:
            lines.append(
                "    offset [%+3d,%+3d] bearing %5.1f  ground %7.1f  "
                "ceiling %7.1f  headroom %6.1f  track %5.1f  lens %5.1f"
                % (row["offset"][0], row["offset"][1], row["bearing"],
                   row["ground"], row["ceiling"], row["headroom"],
                   row["to_track"], row["to_lens"]))
        lines.append("")
    text = "\n".join(lines)
    _write_json(os.path.join(LAB_DIR, "sites.json"), report)
    _write_text(os.path.join(DOC_DIR, "sites.txt"), text)
    print(text)
    return report


# --- stage: render ----------------------------------------------------------


def stage_render(godot: str, only: Sequence[str] = (),
                 with_marker: bool = True) -> dict[str, Any]:
    """Twelve moments per world, plus two marker passes each.

    A marker is rendered twice - once whole, once with `--layers=world`, which
    draws the world without the machine - and a pixel counts as a band only
    where the two agree. That is what subtracts the machine, and V25 found out
    the hard way what happens without it: a baseline with no foreground rock
    in it at all measured as 22% foreground rock, because the near ground had
    drifted one band over.
    """
    _require_inputs()
    seconds = v27.seconds()
    cost_path = os.path.join(LAB_DIR, "cost.json")
    report: dict[str, Any] = _load(cost_path) if os.path.isfile(cost_path) else {}
    for entry in v27.ALL:
        if only and entry.key not in only and entry.tag not in only:
            continue
        passes: list[tuple[str, str]] = [(entry.key, "")]
        if with_marker:
            marker = v27.marker(entry.key)
            passes += [(marker, ""), (marker, "world")]
        for environment, layers in passes:
            label = environment + ("" if not layers else f"@{layers}")
            print(f"--- {label} ---")
            started = time.perf_counter()
            stdout = _render_at(godot, environment, layers, seconds,
                                stills_dir(environment, layers), label)
            elapsed = time.perf_counter() - started
            if environment == entry.key and not layers:
                cost = v27.parse_cost(stdout)
                census = v27.census_of(stdout)
                report[entry.tag] = {
                    "environment": entry.key,
                    "meshes": cost.meshes,
                    "triangles": cost.triangles,
                    "ms_per_frame": cost.milliseconds,
                    "census": census,
                }
                print(f"  {cost.line()}")
                if census:
                    print("  world: " + ", ".join(
                        f"{k} {v}" for k, v in census.items()))
            print(f"  {len(seconds)} frames in {elapsed:.1f} s")
    _write_json(cost_path, report)
    return report


# --- sheets -----------------------------------------------------------------


def _label(draw: ImageDraw.ImageDraw, at: tuple[int, int], text: str,
           size: int = 22, fill=SHEET_LABEL) -> None:
    draw.text(at, text, font=overlays.load_font(size), fill=fill)


def _cell(path: str, size: tuple[int, int]) -> Image.Image:
    return _open(path).resize(size, Image.LANCZOS)


def _contact_sheet(width: int = 200) -> str:
    """Four worlds down, twelve moments across."""
    height = int(round(width * HEIGHT / WIDTH))
    margin, gutter, head, side = 16, 6, 74, 230
    sheet = Image.new(
        "RGB",
        (side + margin + len(v27.MOMENTS) * (width + gutter),
         head + margin + len(v27.ALL) * (height + gutter + 18)),
        SHEET_BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    _label(draw, (margin, 12),
           "V27  contained stages against the V26 outdoor control", 26)
    _label(draw, (margin, 42),
           "identical replay, camera track, edit, machine and racers - the "
           "only flag that differs between two rows is --environment=",
           18, SHEET_DIM)
    for column, one in enumerate(v27.MOMENTS):
        x = side + margin + column * (width + gutter)
        _label(draw, (x, head - 22), one.title, 17, SHEET_DIM)
    for row, entry in enumerate(v27.ALL):
        y = head + row * (height + gutter + 18)
        _label(draw, (margin, y + 6), entry.title, 19)
        _label(draw, (margin, y + 30), "--environment=", 14, SHEET_DIM)
        _label(draw, (margin, y + 46), entry.key, 14, SHEET_DIM)
        for column, one in enumerate(v27.MOMENTS):
            x = side + margin + column * (width + gutter)
            sheet.paste(_cell(still(entry.key, one.key), (width, height)),
                        (x, y))
    path = os.path.join(LAB_DIR, "sheets", "contact.png")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sheet.save(path)
    return path


def _phone_sheet() -> str:
    """The same grid at 270x480, which is the size that decides."""
    width, height = PHONE
    margin, gutter, head, side = 14, 6, 62, 130
    sheet = Image.new(
        "RGB",
        (side + margin + len(v27.ALL) * (width + gutter),
         head + margin + 4 * (height + gutter + 20)),
        SHEET_BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    _label(draw, (margin, 10),
           "V27 at 270x480 - the four moments that decide, at the size a feed "
           "shows", 22)
    picked = ["frame0", "obstacle", "branch", "winner"]
    for row, key in enumerate(picked):
        y = head + row * (height + gutter + 20)
        _label(draw, (margin, y + 8), v27.moment(key).title, 18)
        for column, entry in enumerate(v27.ALL):
            x = side + margin + column * (width + gutter)
            sheet.paste(_cell(still(entry.key, key), (width, height)), (x, y))
            if row == 0:
                _label(draw, (x, head - 24), entry.title, 16, SHEET_DIM)
    path = os.path.join(LAB_DIR, "sheets", "phone.png")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sheet.save(path)
    return path


def _moment_sheet(keys: Sequence[str], name: str, title: str,
                  width: int = 330) -> str:
    """One row per moment, four worlds across, large enough to judge."""
    height = int(round(width * HEIGHT / WIDTH))
    margin, gutter, head, side = 16, 8, 72, 170
    sheet = Image.new(
        "RGB",
        (side + margin + len(v27.ALL) * (width + gutter),
         head + margin + len(keys) * (height + gutter + 22)),
        SHEET_BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    _label(draw, (margin, 10), title, 24)
    for row, key in enumerate(keys):
        one = v27.moment(key)
        y = head + row * (height + gutter + 22)
        _label(draw, (margin, y + 8), one.title, 20)
        _label(draw, (margin, y + 34), "out %.3f s" % one.second, 15, SHEET_DIM)
        _label(draw, (margin, y + 52), "replay %.3f s" % one.replay, 15,
               SHEET_DIM)
        for column, entry in enumerate(v27.ALL):
            x = side + margin + column * (width + gutter)
            sheet.paste(_cell(still(entry.key, key), (width, height)), (x, y))
            if row == 0:
                _label(draw, (x, head - 26), entry.title, 18, SHEET_DIM)
    path = os.path.join(LAB_DIR, "sheets", f"{name}.png")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sheet.save(path)
    return path


def _hook_card_sheet() -> str:
    """Frame 0 with the real PICK A COLOR plate composited on it.

    The contrast numbers in `measures.txt` say the card *reads*; they cannot
    say whether a wall edge lands behind a glyph or a practical sits under a
    letter, and Part K asks both. This draws the mark from `v24_hook` at V24's
    own baseline - the same call `tools/sloped_short.py` makes - so what is on
    the board is what is on the film.
    """
    mark = v24_hook.pick_a_color(baseline=v24.MARK_BASELINE).convert("RGBA")
    width, height = PHONE
    margin, gutter, head = 14, 6, 44
    sheet = Image.new(
        "RGB",
        (margin * 2 + len(v27.ALL) * (width + gutter),
         head + margin + height),
        SHEET_BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    _label(draw, (margin, 10),
           "Frame 0 with the delivered PICK A COLOR plate, at 270x480", 20)
    for index, entry in enumerate(v27.ALL):
        base = _open(still(entry.key, "frame0")).convert("RGBA")
        base.alpha_composite(mark)
        x = margin + index * (width + gutter)
        sheet.paste(base.convert("RGB").resize((width, height),
                                               Image.LANCZOS), (x, head))
        _label(draw, (x, head - 20), entry.tag.upper(), 16, SHEET_DIM)
    path = os.path.join(LAB_DIR, "sheets", "hook_card.png")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sheet.save(path)
    return path


def stage_sheet() -> list[str]:
    made = [
        _contact_sheet(),
        _phone_sheet(),
        _moment_sheet(["frame0", "mixer", "release"], "opening",
                      "V27 opening - the hook, the mixer and the release"),
        _moment_sheet(["obstacle", "fork_approach", "split"], "middle",
                      "V27 middle - the obstacle and the fork"),
        _moment_sheet(["merge", "final_approach", "winner", "payoff"],
                      "finish", "V27 finish - the approach and the payoff"),
        _hook_card_sheet(),
    ]
    os.makedirs(DOC_DIR, exist_ok=True)
    for path in made:
        shutil.copy2(path, os.path.join(DOC_DIR, os.path.basename(path)))
        print("sheet", path)
    return made


# --- measurement ------------------------------------------------------------


def _moment_reads(track: dict[str, Any], replay: dict[str, Any],
                  key: str) -> dict[str, Any]:
    """A `first_frame_report`-shaped dict for any moment, not only frame zero.

    `readability.cut_reads` wants a cut; this hands it a synthetic one holding
    the single solved frame nearest the moment's replay second, so the racer
    projections come from the same arithmetic the delivered readability bar and
    `cameras.frame_report` use rather than from a second implementation.
    """
    one = v27.moment(key)
    frames = v27.frames_of(track)
    frame = min(frames, key=lambda f: abs(f[0] - one.replay))
    row = readability.cut_reads({"frames": [frame]}, replay, WIDTH, HEIGHT,
                                stride=1)[0]
    diameters = sorted(row["diameters"])
    return {
        "t": row["t"],
        "racers": row["in_frame"],
        "of": row["of"],
        "median_px": round(readability._median(diameters), 2) if diameters else 0.0,
        "bbox": [round(v, 1) for v in row["bbox"]] if row["bbox"] else None,
        "positions": {int(k): [round(v[0], 1), round(v[1], 1), round(v[2], 2)]
                      for k, v in sorted(row["racers"].items())},
    }


def _luma(pixels: np.ndarray) -> np.ndarray:
    return (0.2126 * pixels[..., 0] + 0.7152 * pixels[..., 1]
            + 0.0722 * pixels[..., 2])


def _sobel(grey: np.ndarray) -> np.ndarray:
    """Gradient magnitude, with numpy's own differences rather than a kernel."""
    gy, gx = np.gradient(grey)
    return np.hypot(gx, gy)


#: What counts as an edge: a luma gradient this steep, per pixel. Four is about
#: the smallest step a viewer separates from dithering on a dark surface at
#: phone scale, and it is a threshold rather than a mean because a mean
#: gradient cannot tell a wall with three hard lines on it from a hillside
#: covered in small ones - the two integrate to the same number.
EDGE_FLOOR = 4.0

#: The blur, in pixels of the delivered 1080x1920, that separates detail a
#: viewer reads as *form* from detail they read as *texture*. Eight is a
#: quarter of a racer's own diameter at frame zero.
SQUINT = 8


def _blur(grey: np.ndarray, radius: int = SQUINT) -> np.ndarray:
    image = Image.fromarray(np.clip(grey, 0.0, 255.0).astype(np.uint8))
    return np.asarray(image.filter(ImageFilter.GaussianBlur(radius))).astype(float)


def background_complexity(pixels: np.ndarray,
                          background: np.ndarray) -> dict[str, float]:
    """How busy the picture is *behind* the machine, at two spatial scales.

    **Why two scales, and not one number.** The brief's Part G asks for wall
    detail that is low frequency: large panel divisions, recesses, ribs, big
    geometric forms - and rules out tiny greebles and dozens of glowing lines.
    A mean gradient cannot tell those apart, because a wall with three hard
    lines across it and a hillside covered in small ones integrate to the same
    figure, and the first version of this measured exactly that and made the
    contained stages look busier than the rock they replaced.

    So:

        fine    the fraction of background pixels that are an edge at
                delivery scale - how much texture there is
        coarse  the same fraction after an eight-pixel blur - how much of it
                is *form*, which is the detail that survives being squinted at
                and is the detail the brief wants
        ratio   coarse / fine. Near 1 means every edge is structural; near 0
                means the background is texture that disappears at distance.

    `local_contrast` is kept as the standard deviation of luma inside the
    mask, which says how wide a value range the background occupies. It is not
    a busyness number and it is easy to misread as one: a wall lit on one side
    and unlit on the other scores high on it while being perfectly quiet.

    None of these is a score for good design. A blank wall measures best on
    every one of them and is the thing the brief rules out in its first
    paragraph. Read them against the layer-cover numbers, which say whether
    there is anything there at all.
    """
    if int(background.sum()) < 500:
        return {"fine": 0.0, "coarse": 0.0, "ratio": 0.0,
                "local_contrast": 0.0, "cover": 0.0}
    grey = _luma(pixels)
    fine = _sobel(grey)
    coarse = _sobel(_blur(grey))
    inside = background
    fine_fraction = float((fine[inside] >= EDGE_FLOOR).mean())
    coarse_fraction = float((coarse[inside] >= EDGE_FLOOR * 0.25).mean())
    return {
        "fine": round(fine_fraction, 4),
        "coarse": round(coarse_fraction, 4),
        "ratio": round(coarse_fraction / fine_fraction, 3)
        if fine_fraction > 1e-6 else 0.0,
        "local_contrast": round(float(grey[inside].std()), 2),
        "cover": round(float(background.mean()), 4),
    }


def _separation(pixels: np.ndarray, mask_a: np.ndarray,
                mask_b: np.ndarray) -> float | None:
    """Mean-luma difference between two masks, or None if either is empty."""
    if int(mask_a.sum()) < 200 or int(mask_b.sum()) < 200:
        return None
    grey = _luma(pixels)
    return round(float(grey[mask_a].mean() - grey[mask_b].mean()), 2)


def hook_contrast(image: Image.Image,
                  baseline: int = None) -> dict[str, Any]:
    """PICK A COLOR's readability on this frame, at **V24's own baseline**.

    `v24_hook.text_plate` scores every candidate baseline and returns the one
    it would choose. That is the right instrument for a pass that is allowed to
    move the mark, and this is not one: V24 fixed the baseline at
    `v24.MARK_BASELINE` and the brief locks the overlays, so the question here
    is what the card reads against on *this* background at *that* height.

    Same method as `text_plate` otherwise, and deliberately so - the mark's own
    box, cut into twelve columns, one per glyph, scored as a WCAG contrast
    ratio against the warm white it is set in, and reported as the **worst**
    column. A mean cannot say which letters are readable; the first version of
    the V24 instrument tried and could only report that a plate "crossed a
    seam".

    The ratio is the unaided one: PICK A COLOR also carries a blurred black
    shadow, so a frame that clears 3.0 here clears it by more in delivery.
    """
    if baseline is None:
        baseline = v24.MARK_BASELINE
    pixels = np.asarray(image.convert("RGB")).astype(float)
    height, width = pixels.shape[:2]
    scale = height / float(HEIGHT)
    line_width, cap = v24_hook.text_box()
    left = max(0, int(round((WIDTH - line_width) * 0.5 * scale)))
    right = min(width, int(round((WIDTH + line_width) * 0.5 * scale)))
    white = v24_hook._relative_luminance(overlays.WARM_WHITE)
    y0 = max(0, int(round((baseline - cap - 12) * scale)))
    y1 = min(height, int(round((baseline + 12) * scale)))
    columns = v24_hook.TEXT_COLUMNS
    edges = [left + int(round((right - left) * c / columns))
             for c in range(columns + 1)]
    ratios: list[float] = []
    for column in range(columns):
        cell = pixels[y0:y1, edges[column]:edges[column + 1]]
        if cell.size == 0:
            continue
        mean = tuple(float(cell[..., axis].mean()) for axis in range(3))
        plate = v24_hook._relative_luminance(mean)
        ratios.append((max(white, plate) + 0.05) / (min(white, plate) + 0.05))
    patch = pixels[y0:y1, left:right]
    grey = _luma(patch) if patch.size else np.zeros(1)
    return {
        "baseline": baseline,
        "worst_column": round(min(ratios), 2) if ratios else 0.0,
        "mean_contrast": round(sum(ratios) / len(ratios), 2) if ratios else 0.0,
        "plate_luma": round(float(grey.mean()), 1),
        "plate_variance": round(float(grey.std()), 1),
        "passes_wcag_large": bool(ratios and min(ratios)
                                  >= v24_hook.MIN_TEXT_CONTRAST),
    }


def stage_measure() -> dict[str, Any]:
    """Every number the brief's Part W asks for, per world and per moment."""
    _require_inputs()
    track = _load(TRACK)
    replay = _load(REPLAY)
    reads = {one.key: _moment_reads(track, replay, one.key)
             for one in v27.MOMENTS}
    out: dict[str, Any] = {"seed": SEED, "worlds": {}}
    for entry in v27.ALL:
        marker = v27.marker(entry.key)
        rows: dict[str, Any] = {}
        for one in v27.MOMENTS:
            image = _open(still(entry.key, one.key))
            pixels = np.asarray(image).astype(float)
            whole = np.asarray(_open(still(marker, one.key))).astype(float)
            world_only = np.asarray(
                _open(still(marker, one.key, "world"))).astype(float)
            masks = v27.segment(whole, world_only)
            background = np.zeros(pixels.shape[:2], dtype=bool)
            for mask in masks.values():
                background |= mask
            machine = ~background
            grey = _luma(pixels)
            small = np.asarray(image.resize(PHONE, Image.LANCZOS)).astype(float)
            small_mask = np.asarray(
                Image.fromarray(background.astype(np.uint8) * 255)
                .resize(PHONE, Image.NEAREST)).astype(bool)
            row: dict[str, Any] = {
                "cover": {k: round(v, 4)
                          for k, v in v27.layer_cover(masks).items()},
                "value": {k: round(v, 1)
                          for k, v in v27.layer_value(pixels, masks).items()},
                "machine_minus_background": _separation(pixels, machine,
                                                        background),
                "clip_white": round(float((grey >= 250.0).mean()), 5),
                "clip_black": round(float((grey <= 5.0).mean()), 5),
                "mean_luma": round(float(grey.mean()), 2),
                "background": background_complexity(pixels, background),
                "phone": background_complexity(small, small_mask),
                "legibility": v24_hook.legibility_report(image,
                                                         reads[one.key]),
            }
            row["recession"] = [
                [near, far, round(step, 1)]
                for near, far, step in v27.recession(row["value"])
            ]
            rows[one.key] = row
        # The hook's own numbers, on frame zero only.
        hook_image = _open(still(entry.key, "frame0"))
        rows["frame0"]["hook"] = hook_contrast(hook_image)
        # What the mark *could* reach on this picture if it were free to move,
        # which it is not: V24 fixed the baseline and V27 may not change it.
        # Reported so a reader can see whether a world is being held back by
        # the shipped position or by its own background.
        free = v24_hook.text_plate(hook_image, reads["frame0"])
        rows["frame0"]["hook"]["best_available"] = free["contrast"]
        rows["frame0"]["hook"]["best_baseline"] = free["baseline"]
        out["worlds"][entry.tag] = {"environment": entry.key, "moments": rows}
    cost_path = os.path.join(LAB_DIR, "cost.json")
    if os.path.isfile(cost_path):
        out["cost"] = _load(cost_path)
    _write_json(os.path.join(LAB_DIR, "measures.json"), out)
    text = _measure_table(out)
    _write_text(os.path.join(DOC_DIR, "measures.txt"), text)
    print(text)
    return out


def _mean(values: Sequence[float]) -> float:
    kept = [v for v in values if v is not None]
    return sum(kept) / len(kept) if kept else 0.0


def _measure_table(measured: dict[str, Any]) -> str:
    lines = ["V27 MEASURES - mean over the twelve moments unless said "
             "otherwise", ""]
    header = "%-34s" % "" + "".join("%12s" % one.tag for one in v27.ALL)
    lines += [header, "-" * len(header)]

    def row(name: str, pick) -> None:
        cells = []
        for entry in v27.ALL:
            world = measured["worlds"][entry.tag]
            try:
                value = pick(world)
            except (KeyError, TypeError):
                value = None
            cells.append("%12s" % ("-" if value is None else value))
        lines.append("%-34s" % name + "".join(cells))

    moments = [one.key for one in v27.MOMENTS]

    def over(path) -> Any:
        def pick(world):
            return round(_mean([path(world["moments"][k]) for k in moments]), 3)
        return pick

    row("racers legible / 12 moments",
        over(lambda m: m["legibility"]["legible"]))
    row("racers in frame", over(lambda m: m["legibility"]["of"]))
    row("least racer dE (legible only)",
        over(lambda m: m["legibility"]["min_de"]))
    row("machine - background luma",
        over(lambda m: m["machine_minus_background"] or 0.0))
    row("mean luma", over(lambda m: m["mean_luma"]))
    row("clipped white %", over(lambda m: m["clip_white"] * 100.0))
    row("clipped black %", over(lambda m: m["clip_black"] * 100.0))
    row("environment cover", over(lambda m: m["background"]["cover"]))
    row("background edge px (fine) %",
        over(lambda m: m["background"]["fine"] * 100.0))
    row("background edge px (coarse) %",
        over(lambda m: m["background"]["coarse"] * 100.0))
    row("detail that survives a squint",
        over(lambda m: m["background"]["ratio"]))
    row("background value spread",
        over(lambda m: m["background"]["local_contrast"]))
    row("phone edge px (fine) %", over(lambda m: m["phone"]["fine"] * 100.0))
    row("phone value spread", over(lambda m: m["phone"]["local_contrast"]))
    lines.append("")
    row("HOOK worst column (shipped)",
        lambda w: w["moments"]["frame0"]["hook"]["worst_column"])
    row("HOOK mean contrast",
        lambda w: w["moments"]["frame0"]["hook"]["mean_contrast"])
    row("HOOK plate luma",
        lambda w: w["moments"]["frame0"]["hook"]["plate_luma"])
    row("HOOK racers legible / 8",
        lambda w: w["moments"]["frame0"]["legibility"]["legible"])
    lines.append("")
    if "cost" in measured:
        row("mesh instances",
            lambda w: measured["cost"].get(_tag_of(w), {}).get("meshes"))
        row("triangles",
            lambda w: measured["cost"].get(_tag_of(w), {}).get("triangles"))
        row("ms / frame",
            lambda w: measured["cost"].get(_tag_of(w), {}).get("ms_per_frame"))
    lines += [
        "",
        "WCAG large text wants 3.0:1. `worst column` is the weakest twelfth of",
        "PICK A COLOR at the shipped baseline of %d, measured on the picture"
        % v24.MARK_BASELINE,
        "the card will sit on, unaided by its own drop shadow.",
    ]
    return "\n".join(lines)


def _tag_of(world: dict[str, Any]) -> str:
    for entry in v27.ALL:
        if entry.key == world["environment"]:
            return entry.tag
    return "?"


# --- stage: parallax --------------------------------------------------------


def stage_parallax(godot: str, only: Sequence[str] = ()) -> dict[str, Any]:
    """How far each depth band moves during five camera moves.

    **Three passes per world, and the division of labour between them is the
    whole instrument.** The bands are segmented from the marker pair - whole
    and world-only, so the machine is subtracted - at the **first** instant
    only, because a template has to start inside its band and where it ends is
    what is being measured. The displacement itself is block-matched on the
    *lit* frames, which are the only ones with enough shading detail in them to
    track: a marker render is flat by construction, and the first run of this
    stage matched on markers and reported nothing at all for every band in
    every move, because a 41x41 window of one flat hue has a standard deviation
    of zero and the matcher refuses it.

    A contained stage that measured one speed for every band would be a
    wallpaper with a machine in front of it, however good its stills look. That
    is the failure this stage exists to catch.
    """
    _require_inputs()
    seconds: list[float] = []
    for _, before, after in v27.PARALLAX_PAIRS:
        seconds += [before, after]
    for entry in v27.ALL:
        if only and entry.key not in only and entry.tag not in only:
            continue
        marker = v27.marker(entry.key)
        for environment, layers in ((entry.key, ""), (marker, ""),
                                    (marker, "world")):
            tag = environment + (f"@{layers}" if layers else "")
            print(f"--- parallax {tag} ---")
            _render_at(godot, environment, layers, seconds,
                       parallax_dir(tag), f"parallax {tag}")
    return stage_parallax_report()


def stage_parallax_report() -> dict[str, Any]:
    frames = v27.frames_of(_load(TRACK))
    out: dict[str, Any] = {"worlds": {}, "curve": {}}
    for label, before, after in v27.PARALLAX_PAIRS:
        one = min(frames, key=lambda f: abs(f[0] - _replay_of(before)))
        two = min(frames, key=lambda f: abs(f[0] - _replay_of(after)))
        out["curve"][label] = v27.parallax_curve(one, two)
    for entry in v27.ALL:
        marker = v27.marker(entry.key)
        rows: dict[str, Any] = {}
        for label, before, after in v27.PARALLAX_PAIRS:
            def read(tag: str, when: float) -> np.ndarray:
                return np.asarray(_open(os.path.join(
                    parallax_dir(tag), f"at_{when:07.3f}.png"))).astype(float)

            masks_a = v27.segment(read(marker, before),
                                  read(f"{marker}@world", before))
            masks_b = v27.segment(read(marker, after),
                                  read(f"{marker}@world", after))
            lit_a = read(entry.key, before)
            lit_b = read(entry.key, after)
            bands: dict[str, Any] = {}
            for band, mask in masks_a.items():
                if not v27.layer(band).ranked:
                    continue
                travel = v27.mask_travel(masks_a, masks_b, band)
                if travel is None:
                    continue
                found = v27.band_shift(lit_a, lit_b, mask)
                # `patches` is part of the measurement, not bookkeeping. Four
                # is the floor: a displacement from two patches is a different
                # claim from one from nine.
                if int(found.get("patches", 0)) >= 4:
                    travel["shift_px"] = round(float(found["shift"]), 2)
                    travel["patches"] = int(found["patches"])
                bands[band] = travel
            rows[label] = bands
        ranked = [one.key for one in sorted(
            (l for l in v27.LAYERS if l.ranked), key=lambda l: l.order)]
        ordered = 0
        measurable = 0
        for bands in rows.values():
            present = [bands[k]["moved"] for k in ranked if k in bands]
            if len(present) < 2:
                continue
            measurable += 1
            # Near-to-far order on the fraction of each band's area that is
            # no longer the same area: a near band re-frames more of itself in
            # a tenth of a second than a far one does. The tolerance is a
            # hundredth, which is the matcher-free equivalent of the sixth of
            # a pixel the displacement version used.
            if all(present[i] >= present[i + 1] - 0.01
                   for i in range(len(present) - 1)):
                ordered += 1
        out["worlds"][entry.tag] = {
            "environment": entry.key,
            "moves": rows,
            "monotone_moves": ordered,
            "measurable_moves": measurable,
            "of": len(rows),
        }
    _write_json(os.path.join(LAB_DIR, "parallax.json"), out)
    text = _parallax_table(out)
    _write_text(os.path.join(DOC_DIR, "parallax.txt"), text)
    print(text)
    return out


def _replay_of(output_second: float) -> float:
    """An output second on V24's edit, as the replay second it shows.

    The parallax pairs are authored in output time like every other moment in
    this lab, and `cameras_v24_5432.json` is indexed in replay time, so one of
    the two has to be converted and it is this one. The map is V24's own edit
    table, read from the solved track rather than restated here.
    """
    track = _load(TRACK)
    for segment in track["edit"]:
        low, high = segment["out"]
        if low - 1e-9 <= output_second <= high + 1e-9:
            return segment["replay"][0] + (output_second - low)
    return output_second


def _parallax_table(measured: dict[str, Any]) -> str:
    ranked = [one for one in sorted(v27.LAYERS, key=lambda l: l.order)
              if one.ranked]
    lines = [
        "PARALLAX",
        "",
        "PART 1 - what the camera makes available.",
        "Screen travel in pixels of a STATIC point on the view axis, by its",
        "distance from the lens, over each move. A property of the camera",
        "track: identical in all four worlds.",
        "",
    ]
    distances = ["%.0f" % d for d in v27.PARALLAX_DISTANCES]
    header = "  %-16s" % "move" + "".join("%12s" % (d + "u")
                                          for d in distances)
    lines += [header, "  " + "-" * (len(header) - 2)]
    for label, curve in measured["curve"].items():
        lines.append("  %-16s" % label + "".join(
            "%12s" % ("-" if d not in curve else "%.1f" % curve[d])
            for d in distances))
    lines += [
        "",
        "PART 2 - what each world does with it.",
        "`moved` is the fraction of a band's screen area that is no longer the",
        "same area a tenth of a second later - one minus the intersection over",
        "union of its two masks. Higher is faster. Depth reads when the three",
        "fall near-to-far.",
        "",
        "A displacement in pixels is added where the block matcher found four",
        "or more trackable patches. It usually does not: both worlds here are",
        "flat-shaded by design, and a 41-pixel window of V26's own stylised",
        "rock has an L* standard deviation of 0.1 to 0.5. That is a finding",
        "about the project's look rather than about any of these three walls.",
        "",
    ]
    for entry in v27.ALL:
        world = measured["worlds"][entry.tag]
        lines.append("%s  (%s)" % (entry.title, entry.key))
        header = "  %-16s" % "move" + "".join("%20s" % one.title
                                              for one in ranked)
        lines += [header, "  " + "-" * (len(header) - 2)]
        for label, bands in world["moves"].items():
            cells = ""
            for one in ranked:
                if one.key not in bands:
                    cells += "%20s" % "-"
                    continue
                cell = bands[one.key]
                text = "%.3f/%.0f%%" % (cell["moved"],
                                        cell["cover_before"] * 100.0)
                if "shift_px" in cell:
                    text += " %.0fpx" % cell["shift_px"]
                cells += "%20s" % text
            lines.append("  %-16s" % label + cells)
        lines.append("  ordered near-to-far in %d of the %d moves where two "
                     "or more bands were measurable (%d moves in all)"
                     % (world["monotone_moves"], world["measurable_moves"],
                        world["of"]))
        lines.append("")
    lines.append("Each cell is `moved / cover`, plus a matched displacement "
                 "where one was")
    lines.append("available. A band is absent where it covered under two per "
                 "cent of the")
    lines.append("frame: below that a sliver the machine eats and uncovers "
                 "changes nearly")
    lines.append("all of its own area without going anywhere, which is how "
                 "the control")
    lines.append("first measured 0.99 on a wall it barely showed.")
    return NEWLINE.join(lines)


# --- stage: clip ------------------------------------------------------------


def _encode(directory: str, names: Sequence[str], video: str) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise LabError("ffmpeg is not on PATH; the frames are rendered but not "
                       "encoded")
    first = int(names[0].split("_")[1].split(".")[0])
    os.makedirs(os.path.dirname(os.path.abspath(video)), exist_ok=True)
    done = subprocess.run(
        [ffmpeg, "-y", "-framerate", str(FPS), "-start_number", str(first),
         "-i", os.path.join(directory, "frame_%06d.png"),
         "-frames:v", str(len(names)), "-an",
         "-c:v", "libx264", "-preset", VIDEO_PRESET, "-crf", str(VIDEO_CRF),
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", video],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if done.returncode != 0:
        tail = "\n".join((done.stderr or "").splitlines()[-15:])
        raise LabError(f"ffmpeg exited {done.returncode}\n{tail}")
    print("  video %s  %.1f MiB"
          % (video, os.path.getsize(video) / (1024 * 1024)))


def stage_clip(godot: str, only: Sequence[str] = ()) -> list[str]:
    """The motion proofs: the whole 20.117 s Short, per world, then its windows.

    **Rendered once and cut with ffmpeg, rather than rendered per window.**
    The three windows the brief asks for - the opening five seconds, the middle
    and the finish - are contiguous spans of the same film, so rendering them
    separately would photograph 1207 frames twice and would also let a window
    disagree with the full clip about a frame on its boundary. Trimming is
    exact here because the encode is constant frame rate from a numbered
    sequence, so `-ss` lands on a frame index rather than near one.

    Stills cannot show the failure a contained stage has and an outdoor one
    does not: a wall that reads as depth in a held frame and as wallpaper the
    moment the camera moves. These are the proof of that, and they are rendered
    through the same track at the same fps, so two clips of two worlds are
    frame-for-frame comparable.
    """
    _require_inputs()
    duration = float(_load(TRACK)["duration"])
    made: list[str] = []
    for entry in v27.ALL:
        if only and entry.key not in only and entry.tag not in only:
            continue
        label = f"{entry.tag} full"
        print(f"--- clip {label} ---")
        out = frames_dir(entry.tag, "full")
        if os.path.isdir(out):
            shutil.rmtree(out)
        os.makedirs(out, exist_ok=True)
        started = time.perf_counter()
        run_godot(godot, [
            f"--out-dir={os.path.abspath(out)}",
            "--clip=1", f"--start=0.0", f"--end={duration:.6f}",
            f"--fps={FPS}",
            *_scene_flags(entry.key),
        ], label)
        names = sorted(f for f in os.listdir(out) if f.endswith(".png"))
        if not names:
            raise LabError(f"{label}: no frames were written")
        elapsed = time.perf_counter() - started
        print("  %d frames in %.1f s (%.0f ms/frame)"
              % (len(names), elapsed, elapsed / len(names) * 1000.0))
        full = video_path(entry.tag, "full")
        _encode(out, names, full)
        made.append(full)
        shutil.rmtree(out)
        for one in v27.CLIPS:
            made.append(_trim(full, video_path(entry.tag, one.key),
                              one.start, one.end))
    made += stage_compare()
    return made


def _trim(source: str, target: str, start: float, end: float) -> str:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise LabError("ffmpeg is not on PATH")
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    done = subprocess.run(
        [ffmpeg, "-y", "-ss", f"{start:.6f}", "-to", f"{end:.6f}",
         "-i", source, "-an", "-c:v", "libx264", "-preset", VIDEO_PRESET,
         "-crf", str(VIDEO_CRF), "-pix_fmt", "yuv420p",
         "-movflags", "+faststart", target],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if done.returncode != 0:
        tail = NEWLINE.join((done.stderr or "").splitlines()[-15:])
        raise LabError("ffmpeg exited %d%s%s" % (done.returncode, NEWLINE, tail))
    print("  trim  %s" % target)
    return target


def stage_compare() -> list[str]:
    """Four worlds side by side in one 1080x1920 strip, per window.

    The control first, then A, B and C, each at 270 wide - which is the phone
    size the sheets are judged at, and four of them fill the delivery width
    exactly. A viewer scrubbing this sees the same instant of the same race in
    four worlds, which no amount of cutting between separate clips achieves.
    """
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise LabError("ffmpeg is not on PATH")
    made: list[str] = []
    windows = [v27.Clip("full", "the whole Short", 0.0, 0.0), *v27.CLIPS]
    for one in windows:
        sources = [video_path(entry.tag, one.key) for entry in v27.ALL]
        if not all(os.path.isfile(path) for path in sources):
            continue
        target = os.path.join(LAB_DIR, "clips", f"compare_{one.key}.mp4")
        args = [ffmpeg, "-y"]
        for path in sources:
            args += ["-i", path]
        chain = "".join(
            "[%d:v]scale=270:480:flags=lanczos[v%d];" % (index, index)
            for index in range(len(sources)))
        chain += "".join("[v%d]" % index for index in range(len(sources)))
        chain += "hstack=inputs=%d,pad=1080:1920:0:720:color=0x0E0E11[out]"             % len(sources)
        args += ["-filter_complex", chain, "-map", "[out]", "-an",
                 "-c:v", "libx264", "-preset", VIDEO_PRESET,
                 "-crf", str(VIDEO_CRF), "-pix_fmt", "yuv420p",
                 "-movflags", "+faststart", target]
        done = subprocess.run(args, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        if done.returncode != 0:
            tail = NEWLINE.join((done.stderr or "").splitlines()[-15:])
            raise LabError("ffmpeg exited %d%s%s" % (done.returncode, NEWLINE, tail))
        print("  compare %s" % target)
        made.append(target)
    return made


# --- stage: score -----------------------------------------------------------

#: The brief's Part Y, scored out of five.
#:
#: **These are judgements and they are written down so that a reader can
#: disagree with one row rather than with a paragraph.** Seven of the twelve
#: are anchored to a number this lab measured and the anchor is named; the
#: other five - premium, cleanliness, reuse, skins, layouts - are taste, and
#: saying so is more useful than dressing them up.
#:
#:     racer_focus     least racer dE at frame 0, and legible racers per moment
#:     machine_focus   machine minus background luma, mean over twelve moments
#:     hook            PICK A COLOR's worst column at the shipped baseline
#:     depth           how many of the four bands are present in most frames
#:     parallax        moves ordered near-to-far, out of five
#:     finish          machine minus background at the winner and the payoff
#:     cost            mesh instances, triangles and ms/frame against V26
SCORES: dict[str, dict[str, int]] = {
    # The control. Scored on the same rows, because a recommendation that is
    # not scored against what ships is a recommendation against nothing.
    "v26": {
        "racer_focus": 3,     # dE 65.9, the lowest here
        "machine_focus": 5,   # 109 luma, the highest here
        "hook": 4,            # 8.64 worst column; nothing wrong with it
        "depth": 4,           # four bands, but 37% of the frame is one of them
        "parallax": 2,        # 0 of 5 moves ordered near-to-far
        "premium": 3,
        "cleanliness": 2,     # 4.56% fine edges over 69% of the frame
        "reuse": 1,           # a landscape authored against this course
        "skins": 2,           # a saturated teal world under any racer palette
        "layouts": 1,
        "finish": 3,          # 90 luma separation, and conifers behind FINISH
        "cost": 3,            # 2284 meshes, 651k triangles
    },
    "a": {
        "racer_focus": 5,     # dE 71.7; 4.83 legible per moment
        "machine_focus": 4,   # 93.1 luma
        "hook": 4,            # 8.45; V24's baseline still optimal
        "depth": 5,           # four bands, thinnest under 0.5% in 1 of 12
        "parallax": 5,        # 5 of 5
        "premium": 5,
        "cleanliness": 4,     # 5.55% fine edges, the highest of the three
        "reuse": 5,
        "skins": 5,
        "layouts": 5,
        "finish": 4,          # 49 luma; a place, but a lit surround
        "cost": 4,            # -34% meshes, -17% triangles, +7% time
    },
    "b": {
        "racer_focus": 5,
        "machine_focus": 4,   # 91.6 luma
        "hook": 4,            # 8.40
        "depth": 3,           # structure band absent in 6 of 12 moments
        "parallax": 4,        # 4 of 5
        "premium": 4,
        "cleanliness": 5,     # 4.78% fine edges and the best squint ratio
        "reuse": 4,           # a strong identity is a weaker host
        "skins": 4,
        "layouts": 4,
        "finish": 4,          # 48 luma
        "cost": 5,            # -42% meshes, -23% triangles
    },
    "c": {
        "racer_focus": 4,     # 4.67 legible per moment, the only one under 4.8
        "machine_focus": 3,   # 82.2 luma
        "hook": 4,            # 8.42
        "depth": 4,           # no deck band at all
        "parallax": 5,        # 5 of 5
        "premium": 4,
        "cleanliness": 4,     # 4.43% fine edges, the lowest here
        "reuse": 3,
        "skins": 4,
        "layouts": 3,
        "finish": 2,          # 24 luma at the winner against V26's 90
        "cost": 5,            # -42% meshes, -23% triangles
    },
}


def stage_score(scores: dict[str, dict[str, int]] | None = None) -> str:
    table = v27.score_table(scores or SCORES)
    _write_text(os.path.join(DOC_DIR, "scores.txt"), table)
    print(table)
    return table


# --- stage: export ----------------------------------------------------------


def stage_export() -> list[str]:
    """Everything a reviewer needs, in one directory outside the branch.

    `exports/` is not in git - see `.gitignore` - and is the only copy of
    several of this project's deliverables, so this stage copies rather than
    moves and never deletes. The sheets and tables are small enough to live in
    `docs/validation/` as well and do; the clips are not, and this is the only
    place they land.
    """
    made: list[str] = []
    os.makedirs(EXPORT_DIR, exist_ok=True)
    for name in ("contact.png", "phone.png", "opening.png", "middle.png",
                 "finish.png", "hook_card.png"):
        source = os.path.join(LAB_DIR, "sheets", name)
        if os.path.isfile(source):
            target = os.path.join(EXPORT_DIR, name)
            shutil.copy2(source, target)
            made.append(target)
    for name in ("envelope.txt", "sites.txt", "measures.txt", "parallax.txt",
                 "scores.txt"):
        source = os.path.join(DOC_DIR, name)
        if os.path.isfile(source):
            target = os.path.join(EXPORT_DIR, name)
            shutil.copy2(source, target)
            made.append(target)
    for name in ("measures.json", "parallax.json", "envelope.json",
                 "sites.json", "cost.json"):
        source = os.path.join(LAB_DIR, name)
        if os.path.isfile(source):
            target = os.path.join(EXPORT_DIR, name)
            shutil.copy2(source, target)
            made.append(target)
    clips = os.path.join(LAB_DIR, "clips")
    if os.path.isdir(clips):
        out = os.path.join(EXPORT_DIR, "clips")
        os.makedirs(out, exist_ok=True)
        for name in sorted(os.listdir(clips)):
            if not name.endswith(".mp4"):
                continue
            target = os.path.join(out, name)
            shutil.copy2(os.path.join(clips, name), target)
            made.append(target)
    doc = os.path.join("docs", "sloped_race_v27_contained.md")
    if os.path.isfile(doc):
        target = os.path.join(EXPORT_DIR, "sloped_race_v27_contained.md")
        shutil.copy2(doc, target)
        made.append(target)
    for path in made:
        print("export", path)
    return made


# --- driver -----------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", default="all",
                        choices=("envelope", "sites", "render", "sheet",
                                 "measure", "parallax", "parallax-report",
                                 "clip", "compare", "score", "export",
                                 "all"))
    parser.add_argument("--godot", default=None)
    parser.add_argument("--only", default="",
                        help="comma-separated concept keys or tags")
    parser.add_argument("--no-marker", action="store_true")
    args = parser.parse_args(argv)
    only = tuple(one for one in args.only.split(",") if one)

    try:
        if args.stage in ("envelope", "all"):
            stage_envelope()
        if args.stage in ("sites", "all"):
            stage_sites()
        if args.stage in ("render", "all"):
            stage_render(find_godot(args.godot), only,
                         with_marker=not args.no_marker)
        if args.stage in ("sheet", "all"):
            stage_sheet()
        if args.stage in ("measure", "all"):
            stage_measure()
        if args.stage in ("parallax", "all"):
            stage_parallax(find_godot(args.godot), only)
        elif args.stage == "parallax-report":
            stage_parallax_report()
        if args.stage in ("clip", "all"):
            stage_clip(find_godot(args.godot), only)
        elif args.stage == "compare":
            stage_compare()
        if args.stage in ("score", "all"):
            stage_score()
        if args.stage in ("export", "all"):
            stage_export()
    except LabError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

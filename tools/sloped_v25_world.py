"""V25: render the world-density variants, compare them, and measure them.

    python tools/sloped_v25_world.py --stage render    --godot PATH
    python tools/sloped_v25_world.py --stage sheet
    python tools/sloped_v25_world.py --stage measure
    python tools/sloped_v25_world.py --stage parallax  --godot PATH
    python tools/sloped_v25_world.py --stage clip      --godot PATH
    python tools/sloped_v25_world.py --stage all       --godot PATH

Four variants - V23's accepted world as the baseline, then A, B and C - through
the same solved V22.1 camera tracks, over the same locked replay, at the same
thirteen output seconds. The only flag that differs between two renders here is
`--environment=`.

Stages, in dependency order:

    render    the thirteen moments per variant, plus two marker passes each
    sheet     the pair sheets, the contact sheet, the crops, the phone sheet
    measure   measures.json: constraints, layer cover, layer value, recession
    parallax  per-depth-band image displacement during five camera moves
    clip      the motion proofs, encoded
    all       all five

## Why a marker is rendered twice

Depth is measured off a segmentation rather than off a guess, and the
segmentation comes from `_marker_v25*`, which paints every world surface the
flat hue of its depth band. Each marker is rendered twice: once whole, and once
with `--layers=world`, which draws the world without the machine. A pixel counts
as a visible band only where the two agree - which is what subtracts the
machine, and without which the V23 baseline measures as 22% foreground rock it
does not have. See `sloped.v25_world.segment`.

**Nothing here touches the physics.** The replay and both camera tracks are read
and never written, and no stage runs a simulation. The seed is 5432 in every
render, and the frame at a given output second is the frame the film has at that
second.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from typing import Any, Sequence

sys.path.insert(0, os.getcwd())

import numpy as np
from PIL import Image, ImageDraw

from sloped import v23_env, v25_world

PROJECT_ROOT = os.getcwd()
GODOT_PROJECT = os.path.join(PROJECT_ROOT, "godot")
RENDER_SCENE = "res://scenes/SlopedRaceRender.tscn"

SEED = 5432
WIDTH, HEIGHT, FPS = 1080, 1920, 60
VIDEO_CRF = 18
VIDEO_PRESET = "medium"

OUT_DIR = os.path.join("output", "sloped_race_v1")
LAB_DIR = os.path.join(OUT_DIR, "v25_world")
DOCS_DIR = os.path.join("docs", "validation", "sloped_race_v1", "v25_world")

REPLAY = os.path.join(OUT_DIR, f"race_{SEED}.json")
START_CONTRACT = os.path.join(OUT_DIR, f"start_contract_{SEED}.json")
RACE_TRACK = os.path.join(OUT_DIR, f"cameras_v221_{SEED}.json")
PREVIEW_TRACK = os.path.join(OUT_DIR, f"preview_v221_{SEED}.json")
FROZEN = os.path.join(OUT_DIR, "v23", f"frozen_{SEED}.json")

#: The machine pass. V25 is a world pass and changes nothing about the machine,
#: so every render here is under V23's own shipped machine - which is what makes
#: a V23-against-V25 pair a comparison of worlds.
MACHINE = "v23b"

# The sheet's furniture, V23's exactly: dark and plain, so a cell is judged on
# what is in it rather than against the paper it is printed on.
SHEET_BACKGROUND = (14, 14, 17)
SHEET_LABEL = (238, 238, 234)
SHEET_DIM = (146, 150, 160)
SHEET_RULE = (44, 46, 54)

#: Frame pairs the parallax test is taken across, as `(label, track, before,
#: after)` in output seconds. A quarter of a second is fifteen frames: long
#: enough that a background band moves a measurable number of pixels, short
#: enough that nothing leaves the frame and the correlation still has the same
#: content in both images to lock onto.
PARALLAX_PAIRS: tuple[tuple[str, str, float, float], ...] = (
    ("obstacle_pan", "race", 11.400, 11.650),
    ("fork_swing", "race", 13.300, 13.550),
    ("branch_cross", "race", 15.300, 15.550),
    ("final_dive", "race", 19.400, 19.650),
    ("preview_dolly", "preview", 1.400, 1.650),
)


class LabError(RuntimeError):
    pass


# --- inputs -----------------------------------------------------------------


def _require_inputs() -> None:
    missing = [path for path in (REPLAY, START_CONTRACT, RACE_TRACK,
                                 PREVIEW_TRACK, FROZEN)
               if not os.path.isfile(path)]
    if not missing:
        return
    raise LabError(
        "the lab needs the locked replay and V22.1's two solved tracks:\n  "
        + "\n  ".join(missing)
        + "\n\nThese are `tools/sloped_v22.py`'s outputs and are not in git."
          "\nCopy them from a tree that has them - the V23 integration tree"
          "\nholds all five."
    )


def find_godot(explicit: str | None) -> str:
    if explicit:
        if os.path.isfile(explicit):
            return explicit
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
        "PATH."
    )


# --- paths ------------------------------------------------------------------


def tagged(environment: str, layers: str = "") -> str:
    """One render pass's own name: the profile, plus the layer isolation."""
    return environment if not layers else f"{environment}@{layers}"


def stills_dir(environment: str, track: str, layers: str = "") -> str:
    return os.path.join(LAB_DIR, "stills", tagged(environment, layers), track)


def frames_dir(key: str, clip: str) -> str:
    return os.path.join(LAB_DIR, "frames", key, clip)


def video_path(key: str, clip: str) -> str:
    return os.path.join(LAB_DIR, "clips", f"{clip}_{key}.mp4")


def parallax_dir(tag: str) -> str:
    return os.path.join(LAB_DIR, "parallax", tag)


def marker_for(key: str) -> str:
    """The diagnostic twin of one variant - see `v25_world.MARKERS`."""
    return v25_world.marker(key)


def _replay_path(track: str) -> str:
    return REPLAY if track == "race" else FROZEN


def _track_path(track: str) -> str:
    return RACE_TRACK if track == "race" else PREVIEW_TRACK


def _scene_flags(track: str, environment: str, layers: str = "") -> list[str]:
    """The one flag list. Two renders differ in `--environment=` and nothing
    else, which is the whole basis of every comparison in this lab."""
    flags = [
        f"--replay={os.path.abspath(_replay_path(track))}",
        f"--cameras={os.path.abspath(_track_path(track))}",
        f"--start-contract={os.path.abspath(START_CONTRACT)}",
        f"--width={WIDTH}",
        f"--height={HEIGHT}",
        "--layout=b",
        "--detail=hero",
        "--routes=both",
        "--finish-sign=double",
        f"--machine={MACHINE}",
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
    errors = "\n".join((completed.stderr or "").splitlines()[-30:])
    if completed.returncode != 0:
        raise LabError(f"{label}: Godot exited {completed.returncode}\n{errors}")
    for line in (completed.stderr or "").splitlines():
        if "SCRIPT ERROR" in line or "Parse Error" in line:
            raise LabError(f"{label}: Godot reported an error: {line.strip()}")
        # A world form inside the racing line or a lens is a mistake in the
        # profile, and a profile is data - so it is surfaced here rather than
        # buried in a log nobody reads.
        if "environment_world:" in line:
            print(f"  ! {line.split('environment_world:')[-1].strip()}")
    return completed.stdout or ""


def _render_at(godot: str, environment: str, track: str, layers: str,
               seconds: Sequence[float], out: str, label: str) -> str:
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out, exist_ok=True)
    stdout = run_godot(godot, [
        f"--out-dir={os.path.abspath(out)}",
        "--at=" + ",".join(f"{one:.3f}" for one in seconds),
        *_scene_flags(track, environment, layers),
    ], label)
    written = sorted(one for one in os.listdir(out) if one.endswith(".png"))
    if len(written) != len(seconds):
        raise LabError(
            f"{label}: asked for {len(seconds)} frames, got {len(written)}")
    return stdout


# --- stage: render ----------------------------------------------------------


def stage_render(godot: str, only: Sequence[str] = (),
                 with_marker: bool = True) -> dict[str, Any]:
    """Thirteen frames per variant from both tracks, plus two marker passes."""
    _require_inputs()
    # Merged into whatever is already there rather than replacing it, so
    # re-rendering one variant after a tweak does not silently delete the other
    # three's costs - which is how the first performance table came out with
    # two rows in it.
    cost_path = os.path.join(LAB_DIR, "cost.json")
    report: dict[str, Any] = _load(cost_path) if os.path.isfile(cost_path) \
        else {}
    for entry in v25_world.ALL:
        if only and entry.key not in only:
            continue
        passes: list[tuple[str, str]] = [(entry.key, "")]
        if with_marker:
            passes += [(marker_for(entry.key), ""),
                       (marker_for(entry.key), "world")]
        for environment, layers in passes:
            for track in ("preview", "race"):
                seconds = v25_world.seconds_for(track)
                label = f"{tagged(environment, layers)} / {track}"
                print(f"--- {label} ---")
                started = time.perf_counter()
                stdout = _render_at(
                    godot, environment, track, layers, seconds,
                    stills_dir(environment, track, layers), label)
                elapsed = time.perf_counter() - started
                if environment == entry.key and track == "race" and not layers:
                    cost = v25_world.parse_cost(stdout)
                    census = v25_world.census_of(stdout)
                    report[entry.key] = {
                        "cost": {"meshes": cost.meshes,
                                 "triangles": cost.triangles,
                                 "ms_per_frame": cost.milliseconds},
                        "census": census,
                    }
                    print(f"  {cost.line()}")
                    if census:
                        print("  world: " + ", ".join(
                            f"{k} {v}" for k, v in census.items()))
                print(f"  {len(seconds)} frames in {elapsed:.1f} s")
    _write_json(cost_path, report)
    return report


def still(environment: str, key: str, layers: str = "") -> str:
    one = v25_world.moment(key)
    return os.path.join(stills_dir(environment, one.track, layers),
                        f"at_{one.second:07.3f}.png")


def _open(path: str) -> Image.Image:
    if not os.path.isfile(path):
        raise LabError(f"missing render: {path}\nRun --stage render first.")
    return Image.open(path).convert("RGB")


# --- stage: sheet -----------------------------------------------------------


def stage_sheet() -> list[str]:
    """Every sheet the brief asks for, written to the docs directory."""
    os.makedirs(DOCS_DIR, exist_ok=True)
    made: list[str] = []
    made += _pair_sheets()
    made.append(_contact_sheet())
    made.append(_phone_sheet())
    made += _crop_sheets()
    made.append(_wide_sheet())
    return made


def _label(draw: ImageDraw.ImageDraw, at: tuple[int, int], text: str,
           colour=SHEET_LABEL) -> None:
    draw.text(at, text, fill=colour)


def _pair_sheets() -> list[str]:
    """One page per moment: the baseline and the three variants side by side.

    Large, because the sheet's job is to let a reviewer look at one moment
    properly and the contact sheet's job is to let them compare all thirteen at
    a glance. Neither does the other's.
    """
    made: list[str] = []
    cell = 460
    for one in v25_world.MOMENTS:
        images = [(entry, _open(still(entry.key, one.key)))
                  for entry in v25_world.ALL]
        height = int(cell * images[0][1].height / images[0][1].width)
        sheet = Image.new("RGB", (cell * len(images), height + 58),
                          SHEET_BACKGROUND)
        draw = ImageDraw.Draw(sheet)
        for index, (entry, image) in enumerate(images):
            sheet.paste(image.resize((cell, height), Image.LANCZOS),
                        (index * cell, 36))
            _label(draw, (index * cell + 10, 8), entry.title)
            _label(draw, (index * cell + 10, 22), entry.key, SHEET_DIM)
            draw.line([(index * cell, 34), (index * cell, height + 36)],
                      fill=SHEET_RULE)
        _label(draw, (10, height + 42),
               f"{one.title}  -  out {one.second:.2f}s on the {one.track} "
               f"track  -  {one.why}", SHEET_DIM)
        path = os.path.join(DOCS_DIR, f"pair_{one.key}.png")
        sheet.save(path)
        made.append(path)
        print(f"  {path}")
    return made


def _contact_sheet() -> str:
    """All thirteen moments by all four variants on one page."""
    cell = 176
    rows = len(v25_world.ALL)
    columns = len(v25_world.MOMENTS)
    probe = _open(still(v25_world.ALL[0].key, v25_world.MOMENTS[0].key))
    height = int(cell * probe.height / probe.width)
    sheet = Image.new("RGB", (cell * columns + 130, (height + 18) * rows + 26),
                      SHEET_BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    for r, entry in enumerate(v25_world.ALL):
        top = 22 + r * (height + 18)
        _label(draw, (6, top + height // 2), entry.title.split(" - ")[0])
        for c, one in enumerate(v25_world.MOMENTS):
            image = _open(still(entry.key, one.key))
            sheet.paste(image.resize((cell, height), Image.LANCZOS),
                        (130 + c * cell, top))
            if r == 0:
                _label(draw, (130 + c * cell + 4, 6), one.title, SHEET_DIM)
    path = os.path.join(DOCS_DIR, "contact_sheet.png")
    sheet.save(path)
    print(f"  {path}")
    return path


def _phone_sheet() -> str:
    """Every moment at 270x480, which is the size the film is judged at.

    One column per variant, one row per moment, so a reviewer scrolls down the
    race rather than across it - which is how the film is watched.
    """
    width, height = v25_world.PHONE
    columns = len(v25_world.ALL)
    rows = len(v25_world.MOMENTS)
    sheet = Image.new("RGB", (width * columns + 8,
                              (height + 16) * rows + 24), SHEET_BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    for c, entry in enumerate(v25_world.ALL):
        _label(draw, (4 + c * width, 6), entry.title)
    for r, one in enumerate(v25_world.MOMENTS):
        top = 22 + r * (height + 16)
        _label(draw, (4, top + height + 2), one.title, SHEET_DIM)
        for c, entry in enumerate(v25_world.ALL):
            image = _open(still(entry.key, one.key))
            sheet.paste(image.resize((width, height), Image.LANCZOS),
                        (4 + c * width, top))
    path = os.path.join(DOCS_DIR, "phone_sheet.png")
    sheet.save(path)
    print(f"  {path}")
    return path


def _crop_sheets() -> list[str]:
    """The six close reads, each at full render resolution."""
    made: list[str] = []
    for crop in v25_world.CROPS:
        cells = []
        for entry in v25_world.ALL:
            image = _open(still(entry.key, crop.moment))
            box = (int(crop.box[0] * image.width),
                   int(crop.box[1] * image.height),
                   int(crop.box[2] * image.width),
                   int(crop.box[3] * image.height))
            cells.append((entry, image.crop(box)))
        wide = max(one.width for _, one in cells)
        tall = max(one.height for _, one in cells)
        sheet = Image.new("RGB", (wide * len(cells), tall + 40),
                          SHEET_BACKGROUND)
        draw = ImageDraw.Draw(sheet)
        for index, (entry, cell) in enumerate(cells):
            sheet.paste(cell, (index * wide, 34))
            _label(draw, (index * wide + 8, 8), entry.title)
        _label(draw, (8, tall + 38),
               f"{crop.title}  -  {v25_world.moment(crop.moment).title}",
               SHEET_DIM)
        path = os.path.join(DOCS_DIR, f"crop_{crop.key}.png")
        sheet.save(path)
        made.append(path)
        print(f"  {path}")
    return made


def _wide_sheet() -> str:
    """The three preview framings, large: the only whole-valley views."""
    cell = 520
    probe = _open(still(v25_world.ALL[0].key, v25_world.WIDE[0]))
    height = int(cell * probe.height / probe.width)
    sheet = Image.new("RGB", (cell * len(v25_world.ALL),
                              (height + 26) * len(v25_world.WIDE) + 22),
                      SHEET_BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    for c, entry in enumerate(v25_world.ALL):
        _label(draw, (c * cell + 8, 6), entry.title)
    for r, key in enumerate(v25_world.WIDE):
        top = 22 + r * (height + 26)
        for c, entry in enumerate(v25_world.ALL):
            sheet.paste(_open(still(entry.key, key)).resize(
                (cell, height), Image.LANCZOS), (c * cell, top))
        _label(draw, (8, top + height + 6),
               v25_world.moment(key).title, SHEET_DIM)
    path = os.path.join(DOCS_DIR, "wide_sheet.png")
    sheet.save(path)
    print(f"  {path}")
    return path


# --- stage: measure ---------------------------------------------------------


def stage_measure() -> dict[str, Any]:
    """Constraints, layer cover, layer value and recession, per moment."""
    os.makedirs(DOCS_DIR, exist_ok=True)
    tracks = {"race": _load(RACE_TRACK), "preview": _load(PREVIEW_TRACK)}
    replays = {"race": _load(REPLAY), "preview": _load(FROZEN)}

    from sloped import presentation

    out: dict[str, Any] = {"moments": {}, "variants": {}}
    for one in v25_world.MOMENTS:
        row: dict[str, Any] = {}
        when = v23_env.output_to_replay(tracks[one.track], one.second)
        places = v23_env.places_at(
            replays[one.track], tracks[one.track], when,
            presentation.project, presentation._camera_at, WIDTH, HEIGHT)
        for entry in v25_world.ALL:
            pixels = np.asarray(_open(still(entry.key, one.key)))
            measures = v23_env.frame_measures(pixels)
            pairs = v23_env.separation(pixels, places)
            measures["racers"] = len(pairs)
            measures["dE"] = v23_env.median([a for a, _ in pairs])
            measures["noise"] = v25_world.noise(v25_world.phone(pixels))
            marker_path = still(marker_for(entry.key), one.key)
            world_path = still(marker_for(entry.key), one.key, "world")
            if os.path.isfile(marker_path) and os.path.isfile(world_path):
                masks = v25_world.segment(np.asarray(_open(marker_path)),
                                          np.asarray(_open(world_path)))
                measures["layer_cover"] = v25_world.layer_cover(masks)
                measures["layer_value"] = v25_world.layer_value(pixels, masks)
                measures["recession"] = [
                    {"from": a, "to": b, "step": round(step, 2)}
                    for a, b, step in
                    v25_world.recession(measures["layer_value"])
                ]
                measures["world_cover"] = round(sum(
                    value for key, value in measures["layer_cover"].items()
                    if key != "terrain"), 3)
            row[entry.key] = measures
        out["moments"][one.key] = row
        print(f"  {one.title}")
    cost_path = os.path.join(LAB_DIR, "cost.json")
    if os.path.isfile(cost_path):
        out["variants"] = _load(cost_path)
    _write_json(os.path.join(DOCS_DIR, "measures.json"), out)
    summary = _summary(out)
    print(summary)
    with open(os.path.join(DOCS_DIR, "measures.txt"), "w",
              encoding="utf-8", newline="\n") as handle:
        handle.write(summary + "\n")
    return out


def _summary(measured: dict[str, Any]) -> str:
    rows = []
    for one in v25_world.MOMENTS:
        row: dict[str, Any] = {"moment": one.title}
        for entry in v25_world.ALL:
            got = measured["moments"][one.key][entry.key]
            tag = entry.title.split(" ")[0]
            row[f"{tag} hr"] = f"{got['headroom']:.1f}"
            row[f"{tag} dE"] = f"{got['dE']:.0f}"
            row[f"{tag} wc"] = f"{got.get('world_cover', 0.0):.1f}"
            row[f"{tag} clip"] = f"{got['flat_white']:.3f}"
        rows.append(row)
    columns = ["moment"]
    for entry in v25_world.ALL:
        tag = entry.title.split(" ")[0]
        columns += [f"{tag} hr", f"{tag} dE", f"{tag} wc", f"{tag} clip"]
    head = ("headroom (machine L* minus backdrop L*), marble dE, world cover %"
            " and flat-white %\n(world cover is every depth band except the "
            "near ground, off the marker render)\n\n")
    return head + v25_world.table(rows, columns)


# --- stage: parallax --------------------------------------------------------


def stage_parallax(godot: str, only: Sequence[str] = ()) -> dict[str, Any]:
    """Per-depth-band image displacement across five camera moves.

    Three passes per pair. The bands are segmented from a world-only marker
    render with the machine subtracted, at the **first** instant only - a
    template has to start inside its band, and where it ends is what is being
    measured. The displacement itself is block-matched on the delivered frames,
    which are the only ones with enough shading detail in them to track. See
    `v25_world.band_shift` for the two versions of this that measured nonsense
    before this one.
    """
    _require_inputs()
    os.makedirs(DOCS_DIR, exist_ok=True)
    # Merged into what is already there, for the same reason `stage_render`
    # merges its costs: re-running one variant after a tweak must not delete
    # the other three's measurements. The first version overwrote, and a table
    # of four variants came back with two rows in it.
    path = os.path.join(DOCS_DIR, "parallax.json")
    out: dict[str, Any] = _load(path) if os.path.isfile(path) else {}
    for entry in v25_world.ALL:
        if only and entry.key not in only:
            continue
        rows: dict[str, Any] = {}
        marker = marker_for(entry.key)
        for label, track, before, after in PARALLAX_PAIRS:
            frames: dict[str, dict[float, np.ndarray]] = {}
            for environment, layers in ((entry.key, ""), (marker, ""),
                                        (marker, "world")):
                tag = tagged(environment, layers)
                folder = os.path.join(parallax_dir(tag), label)
                _render_at(godot, environment, track, layers,
                           (before, after), folder, f"{tag} / {label}")
                frames[tag] = {
                    when: np.asarray(_open(os.path.join(
                        folder, f"at_{when:07.3f}.png")))
                    for when in (before, after)
                }
            masks = v25_world.segment(
                frames[marker][before],
                frames[tagged(marker, "world")][before])
            measured = v25_world.parallax(
                frames[entry.key][before], frames[entry.key][after], masks)
            ok, series = v25_world.monotone(measured)
            rows[label] = {"bands": measured, "monotone": ok,
                           "series": series,
                           "separation": v25_world.separation(measured),
                           "verdict": v25_world.verdict(measured),
                           "seconds": [before, after], "track": track}
            print(f"  {entry.title:<22} {label:<14} "
                  f"{rows[label]['verdict']}")
        out[entry.key] = rows
    _write_json(path, out)
    report = _parallax_report(out)
    with open(os.path.join(DOCS_DIR, "parallax.txt"), "w",
              encoding="utf-8", newline="\n") as handle:
        handle.write(report + "\n")
    print(report)
    return out


def stage_parallax_report() -> dict[str, Any]:
    """Re-derive the parallax verdict from a finished `parallax.json`.

    Sixty renders are not cheap, and how the per-band displacements are
    *grouped* into a depth series is a judgement that was revised once - see
    `v25_world.monotone`. Re-reading the measured numbers is the difference
    between revising that judgement and re-rendering the film to revise it.
    """
    path = os.path.join(DOCS_DIR, "parallax.json")
    if not os.path.isfile(path):
        raise LabError(f"no {path}; run --stage parallax first")
    measured = _load(path)
    for key, pairs in measured.items():
        for label, got in pairs.items():
            ok, series = v25_world.monotone(got["bands"])
            got["monotone"] = ok
            got["series"] = series
            got["separation"] = v25_world.separation(got["bands"])
            got["verdict"] = v25_world.verdict(got["bands"])
            print(f"  {v25_world.variant(key).title:<22} {label:<14} "
                  f"{got['verdict']}")
    _write_json(path, measured)
    report = _parallax_report(measured)
    with open(os.path.join(DOCS_DIR, "parallax.txt"), "w",
              encoding="utf-8", newline="\n") as handle:
        handle.write(report + "\n")
    print(report)
    return measured


def _parallax_report(measured: dict[str, Any]) -> str:
    lines = [
        "Per-depth-band image displacement, in pixels, across 0.25 s (15",
        "frames) of each camera move. A band under 0.4% of the frame is not",
        "measured - a correlation peak on a few hundred pixels means nothing -",
        "and its cover is printed in brackets instead, so the gap is visible.",
        "Each cell is the median of N tracked 41x41 patches, printed as px/Np;",
        "a band tracked by fewer than two patches is not reported either.",
        "",
        "'world bands' is the verdict: how many world depth bands were",
        "trackable at all, the slowest and fastest of them, and the ratio.",
        "That ratio is the parallax - a painted backdrop gives one rate and a",
        "world gives a spread. 'near-to-far' is the same numbers in depth",
        "order, and it is NOT expected to fall: every race camera here is",
        "tracking the pack, which pins a point at the pack's own distance and",
        "makes image motion grow in BOTH directions from it. See",
        "sloped/v25_world.separation. The near ground and the ravine floor are",
        "measured but not ranked - neither is at a single depth.",
        "",
    ]
    for key, pairs in measured.items():
        lines.append(v25_world.variant(key).title)
        rows = []
        for label, got in pairs.items():
            row: dict[str, Any] = {"move": label}
            for band in v25_world.LAYERS:
                cell = got["bands"].get(band.key, {})
                if "shift" in cell and int(cell.get("patches", 0)) >= 2:
                    row[band.key] = (f"{cell['shift']:.0f}px"
                                     f"/{int(cell['patches'])}p")
                else:
                    row[band.key] = f"({cell.get('cover', 0.0):.2f}%)"
            row["depth order"] = got["series"] if got["monotone"] \
                else "NOT " + got["series"]
            rows.append(row)
        columns = ["move"] + [one.key for one in v25_world.LAYERS] \
            + ["depth order"]
        lines.append(v25_world.table(rows, columns))
        lines.append("")
    return "\n".join(lines)


# --- stage: clip ------------------------------------------------------------


def stage_clip(godot: str, only: Sequence[str] = (),
               which: Sequence[str] = ()) -> list[str]:
    """The moving proofs, rendered and encoded."""
    _require_inputs()
    os.makedirs(os.path.join(LAB_DIR, "clips"), exist_ok=True)
    made: list[str] = []
    for clip in v25_world.CLIPS:
        if which and clip.key not in which:
            continue
        for entry in v25_world.ALL:
            if only and entry.key not in only:
                continue
            out = frames_dir(entry.key, clip.key)
            if os.path.isdir(out):
                shutil.rmtree(out)
            os.makedirs(out, exist_ok=True)
            label = f"{entry.title} / {clip.key}"
            print(f"--- {label} ---")
            started = time.perf_counter()
            stdout = run_godot(godot, [
                f"--out-dir={os.path.abspath(out)}",
                "--clip=1",
                f"--start={clip.start:.6f}",
                f"--end={clip.end:.6f}",
                f"--fps={FPS}",
                *_scene_flags(clip.track, entry.key),
            ], label)
            names = sorted(one for one in os.listdir(out)
                           if one.endswith(".png"))
            if not names:
                raise LabError(f"{label}: no frames were written")
            cost = v25_world.parse_cost(stdout)
            print(f"  {len(names)} frames in "
                  f"{time.perf_counter() - started:.1f} s  ({cost.line()})")
            path = video_path(entry.key, clip.key)
            _encode(out, names, path)
            made.append(path)
            # The frames are the expensive half and the video is the artefact:
            # a full set is tens of thousands of 1080x1920 PNGs, and keeping
            # them fills a disk to hold what ffmpeg has already read.
            shutil.rmtree(out)
    return made


def _encode(directory: str, names: Sequence[str], video: str) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise LabError("ffmpeg is not on PATH; frames are rendered, not encoded")
    first = int(names[0].split("_")[1].split(".")[0])
    os.makedirs(os.path.dirname(os.path.abspath(video)), exist_ok=True)
    done = subprocess.run(
        [ffmpeg, "-y", "-framerate", str(FPS), "-start_number", str(first),
         "-i", os.path.join(directory, "frame_%06d.png"),
         "-frames:v", str(len(names)), "-an",
         "-c:v", "libx264", "-preset", VIDEO_PRESET, "-crf", str(VIDEO_CRF),
         "-pix_fmt", "yuv420p", video],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace")
    if done.returncode != 0:
        tail = "\n".join((done.stderr or "").splitlines()[-12:])
        raise LabError(f"ffmpeg failed for {video}:\n{tail}")
    print(f"  {video}")


# --- helpers ----------------------------------------------------------------


def _load(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(f"  {path}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", default="all",
                        choices=["render", "sheet", "measure", "parallax",
                                 "parallax-report", "clip", "all"])
    parser.add_argument("--godot", default=None)
    parser.add_argument("--only", default="",
                        help="comma-separated variant keys")
    parser.add_argument("--clips", default="",
                        help="comma-separated clip keys")
    parser.add_argument("--no-marker", action="store_true")
    args = parser.parse_args(argv)

    only = tuple(one for one in args.only.split(",") if one)
    clips = tuple(one for one in args.clips.split(",") if one)
    try:
        if args.stage in ("render", "all"):
            stage_render(find_godot(args.godot), only, not args.no_marker)
        if args.stage in ("sheet", "all"):
            stage_sheet()
        if args.stage in ("measure", "all"):
            stage_measure()
        if args.stage in ("parallax", "all"):
            stage_parallax(find_godot(args.godot), only)
        if args.stage == "parallax-report":
            stage_parallax_report()
        if args.stage in ("clip", "all"):
            stage_clip(find_godot(args.godot), only, clips)
    except LabError as problem:
        print(f"\nv25 world lab: {problem}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

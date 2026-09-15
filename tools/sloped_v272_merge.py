"""V27.2: render, measure and report the merge correction.

    python tools/sloped_v272_merge.py --stage all

Stages, and each one can be run on its own:

    survey     which hall pieces the merge cameras see, and which are shared
    render     the worlds and their marker twins, both `--at` lists
    listcheck  what asking for a different list of seconds costs a number
    isolate    one probe per candidate object: which one is the bright thing
    mechanism  why that object is bright, field by field, and why 0.06
    surfaces   the same frames by material, for the record
    measure    the corrected separation instrument, every moment, both lists
    coverage   how much of the gap is contrast and how much is coverage
    delta      which frames the one-leaf delta reaches, and by how much
    regress    the brief's guards: hook, obstacle, fork, finish
    winner     the purple racer at the finish, unchanged from V27.1's method
    payoff     the card's contrast on each world's payoff frame
    hook       frame 0, checked rather than assumed
    country    the India render-only probe, re-run against the correction
    proof      the brief's six frames, three worlds, plus a phone column
    sheet      the merge boards and the 270x480 phone board
    clip       branch -> merge -> post-merge, in motion, in each world
    compare    the three clips stacked into one comparison file
    ring       why no WINNER-mark number is invented on a merge clip
    timing     four renders per world, for an honest frame time
    cost       mesh, triangle and frame-time comparison
    clean      report any diagnostic profile a killed run left behind
    export     copy the deliverables into exports/

`ring` reads the frames `clip` renders, so run it after `clip` or as part of
`all`, which orders them.

Everything is rendered from V26's own replay, V24's own camera track and V24's
own edit. No stage here may write either, and none of them touches the physics,
the seed, the course, the camera solve, the timing, the hook, the payoff, the
audio or the racers.

## The two lists, and why both

V27 found that a still is only comparable with another still asked for in the
**same `--at` list**, because the renderer accumulates between samples inside
one process. This pass needs two:

    list A   the twelve V27 moments, so every number it prints beside V27.1's
             published table was taken the way V27.1 took it
    list B   the brief's six proof frames, two of which V27 does not have

Four moments are in both. `--stage listcheck` measures what that costs instead
of assuming it costs nothing, and the answer is printed in the report.

## Nothing is left in the registry

Every diagnostic profile - the marker and the nine probes - is written,
rendered and deleted inside `sloped_v272_profiles.temporary`, and `index.json`
is restored from the bytes it had on entry. `--stage clean` reports anything a
killed run left behind.
"""

from __future__ import annotations

import argparse
import hashlib
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
os.chdir(PROJECT_ROOT)

from sloped import overlays  # noqa: E402
from sloped import readability  # noqa: E402
from sloped import v24  # noqa: E402
from sloped import v24_hook  # noqa: E402
from sloped import v24_payoff  # noqa: E402
from sloped import v27_contained as v27  # noqa: E402
from sloped import v271_finish as v271  # noqa: E402
from sloped import v272_merge as v272  # noqa: E402
from sloped.presentation import project  # noqa: E402

import tools.sloped_v271_finish as finish_lab  # noqa: E402
import tools.sloped_v27_contained as lab  # noqa: E402
import tools.sloped_v272_profiles as gen  # noqa: E402

SEED = v272.SEED
WIDTH, HEIGHT = v272.WIDTH, v272.HEIGHT
PHONE = v27.PHONE

OUT_DIR = os.path.join("output", "sloped_race_v1")
LAB_DIR = os.path.join(OUT_DIR, "v272_contained")
DOC_DIR = os.path.join("docs", "validation", "sloped_race_v1", "v272_contained")
EXPORT_DIR = os.path.join("exports", "v272_contained_hall_merge")

REPLAY = lab.REPLAY
TRACK = lab.TRACK
START_CONTRACT = lab.START_CONTRACT

#: The three worlds, in the order they are printed. The control first, then the
#: profile this pass starts from, then the correction.
WORLDS: tuple[tuple[str, str, str], ...] = (
    (v272.CONTROL, "v26", "V26 outdoor"),
    (v272.PARENT, "v271", "V27.1 contained"),
    (v272.PROFILE, "v272", "V27.2 corrected"),
)

#: Each world's depth-band twin. V26's and V27.1's are committed profiles;
#: V27.2's is built on demand and deleted after.
MARKERS = {
    v272.CONTROL: "_marker_v27_control",
    v272.PARENT: "_marker_v271",
    v272.PROFILE: v272.MARKER,
}

LISTS: dict[str, tuple[float, ...]] = {"a": v272.LIST_A, "b": v272.LIST_B}

#: Which moments each list carries, by key.
LIST_KEYS: dict[str, tuple[str, ...]] = {
    "a": tuple(one.key for one in v27.MOMENTS),
    "b": v272.PROOF_FRAMES,
}

SHEET_BACKGROUND = lab.SHEET_BACKGROUND
SHEET_LABEL = lab.SHEET_LABEL
SHEET_DIM = lab.SHEET_DIM
SHEET_RULE = lab.SHEET_RULE

NEWLINE = chr(10)


class LabError(RuntimeError):
    pass


# --- paths ------------------------------------------------------------------


def stills_dir(listing: str, environment: str, layers: str = "") -> str:
    tag = environment if not layers else f"{environment}@{layers}"
    return os.path.join(LAB_DIR, "stills", listing, tag)


def still(listing: str, environment: str, key: str, layers: str = "") -> str:
    return os.path.join(stills_dir(listing, environment, layers),
                        f"at_{v272.moment(key).second:07.3f}.png")


def country_dir(tag: str) -> str:
    return os.path.join(LAB_DIR, "country", tag)


def country_still(tag: str, key: str) -> str:
    return os.path.join(country_dir(tag),
                        f"at_{v272.moment(key).second:07.3f}.png")


def _load(path: str) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: str, payload: Any) -> None:
    v272.write_json(path, payload)


def _write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text.rstrip("\n") + "\n")


def _open(path: str) -> Image.Image:
    if not os.path.isfile(path):
        raise LabError(f"missing render: {path}{NEWLINE}Run --stage render "
                       f"first.")
    return Image.open(path).convert("RGB")


def _pixels(path: str) -> np.ndarray:
    return np.asarray(_open(path)).astype(float)


def _digest(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def _have(environment: str) -> bool:
    return os.path.isfile(os.path.join(gen.PROFILE_DIR, f"{environment}.json"))


def _worlds() -> list[tuple[str, str, str]]:
    """The worlds that actually have a profile on disk.

    The correction does not exist during the diagnosis stages and every stage
    below has to run without it, which is the whole point of the ordering:
    `isolate` names the object, and only then is there something to render.
    """
    return [one for one in WORLDS if _have(one[0])]


# --- running Godot ----------------------------------------------------------


def _render_at(godot: str, environment: str, layers: str,
               seconds: Sequence[float], out: str, label: str,
               extra: Sequence[str] = ()) -> str:
    """One Godot process, one `--at` list, one directory of stills.

    Lifted from `tools/sloped_v271_finish._render_at` unchanged in behaviour,
    including the two failure modes that matter: a `SCRIPT ERROR` is a failure
    rather than log noise, and a scene `push_error` - which Godot exits 0 on -
    is a failure too, because an unrecognised flag makes the scene fall back to
    a default and render a perfectly good sheet of the wrong thing.
    """
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
        for who in ("sloped_race_scene:", "racer_visual:", "course_scene:",
                    "lab_palette:"):
            if who in line:
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
    """Which wall, deck and bay pieces the merge cameras see, and which are
    private to them.

    The same question V27.1 asked at the finish, and the same projector: the
    film's own lens on the solved track, because "is this segment in shot" is
    not "is its centre inside four planes".

    It exists to decide, before anything is rendered, whether a merge-local
    repaint is even available - and if it is not, to say so rather than to
    invent one.
    """
    frames = v272.frames_of(_load(TRACK))
    profile = gen.env.resolve(v272.PARENT)
    bands = profile["world"]["shell"]["bands"]
    rings = profile["world"]["deck"]["rings"]
    merge = set(v272.MERGE)

    seen: dict[tuple[str, int, int], set[str]] = {}
    for one in v272.MOMENTS:
        frame = v272.frame_at(frames, one.replay)
        for index, band in enumerate(bands):
            count = int(band["count"])
            step = float(band["bearing_step"])
            start = float(band["bearing_from"])
            foot = float(band["foot"])
            tall = float(band["height"])
            for segment in range(count):
                x, z = v272.polar(start + step * segment, float(band["radius"]))
                for part in (0.05, 0.3, 0.6, 0.9):
                    if v272.in_frame(frame, (x, foot + tall * part, z)):
                        seen.setdefault(("shell", index, segment),
                                        set()).add(one.key)
                        break
        for index, ring in enumerate(rings):
            facets = int(ring.get("facets", 24))
            mid = (float(ring["outer"]) + float(ring["inner"])) * 0.5
            for facet in range(facets):
                x, z = v272.polar(360.0 / facets * facet, mid)
                if v272.in_frame(frame, (x, float(ring["y"]), z)):
                    seen.setdefault(("deck", index, facet), set()).add(one.key)

    report: dict[str, Any] = {"parts": []}
    lines = [
        "THE MERGE SECTOR",
        "which pieces of the hall the three merge cameras see, and what else",
        "sees them. Projected with the film's own lens onto the solved track,",
        "over all fourteen moments.",
        "",
        "%-14s %6s %10s %10s %10s" % ("part", "pieces", "at merge",
                                      "merge only", "never seen"),
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
            elif got <= merge:
                only.append(piece)
            elif got & merge:
                shared.append(piece)
        name = f"{kind} {index}"
        report["parts"].append({
            "part": name, "pieces": count, "merge_only": only,
            "merge_shared": shared, "never_seen": len(never),
        })
        lines.append("%-14s %6d %10d %10d %10d" % (
            name, count, len(only) + len(shared), len(only), len(never)))

    private = sum(len(one["merge_only"]) for one in report["parts"])
    lines += [
        "",
        "Pieces private to the merge: %d." % private,
        "",
        "`merge only` is a piece the three merge cameras see and no other",
        "camera does. A repaint there would be invisible everywhere else; a",
        "repaint of a shared piece is a change to the whole film, and has to",
        "be defended at every moment rather than at three. --stage delta is",
        "where that is done.",
    ]
    text = NEWLINE.join(lines)
    _write_json(os.path.join(LAB_DIR, "survey.json"), report)
    _write_text(os.path.join(DOC_DIR, "survey.txt"), text)
    print(text)
    return report


# --- stage: render ----------------------------------------------------------


def _render_world(godot: str, listing: str, environment: str,
                  report: dict[str, Any], tag: str) -> None:
    seconds = LISTS[listing]
    marker = MARKERS[environment]
    started = time.perf_counter()
    stdout = _render_at(godot, environment, "", seconds,
                        stills_dir(listing, environment), f"{tag}/{listing}")
    elapsed = time.perf_counter() - started
    cost = v27.parse_cost(stdout)
    report.setdefault(tag, {})[listing] = {
        "environment": environment,
        "meshes": cost.meshes,
        "triangles": cost.triangles,
        "ms_per_frame": cost.milliseconds,
        "census": v27.census_of(stdout),
        "wall_seconds": round(elapsed, 2),
    }
    print(f"  {cost.line()}")
    for layers in ("", "world"):
        _render_at(godot, marker, layers, seconds,
                   stills_dir(listing, marker, layers),
                   f"{marker}@{layers or 'all'}/{listing}")


def stage_render(godot: str, only: Sequence[str] = ()) -> dict[str, Any]:
    """Every world, both lists, with its marker pair.

    The V27.2 marker does not exist on disk and is built for the duration of
    this stage only.
    """
    cost_path = os.path.join(LAB_DIR, "cost.json")
    report: dict[str, Any] = _load(cost_path) if os.path.isfile(cost_path) else {}
    wanted = [one for one in _worlds()
              if not only or one[0] in only or one[1] in only]
    ephemeral = [gen.marker(v272.PROFILE)] if any(
        one[0] == v272.PROFILE for one in wanted) else []
    with gen.temporary(ephemeral):
        for environment, tag, _title in wanted:
            for listing in ("a", "b"):
                print(f"--- {tag} list {listing} "
                      f"({len(LISTS[listing])} frames) ---")
                _render_world(godot, listing, environment, report, tag)
    _write_json(cost_path, report)
    return report


# --- stage: listcheck -------------------------------------------------------


def stage_listcheck() -> dict[str, Any]:
    """What asking for a different list of seconds does to the same second.

    V27's reproducibility trap, measured rather than quoted. Four moments -
    `merge`, `final_approach`, `winner`, `payoff` - are rendered twice by
    `--stage render`, once inside the twelve and once inside the six, and this
    compares the two files.

    If they are byte-identical the trap does not bite on these frames and a
    number from either list can be quoted beside V27.1's. If they are not, the
    size of the difference is the error bar on every cross-list comparison in
    the report, and it is printed rather than hidden.
    """
    shared = [key for key in LIST_KEYS["b"] if key in LIST_KEYS["a"]]
    out: dict[str, Any] = {"shared": shared, "worlds": {}}
    lines = [
        "THE TWO --at LISTS, COMPARED ON THE FRAMES THEY SHARE",
        "the same output second, rendered once inside the twelve V27 moments",
        "and once inside the brief's six. V27 found that a still is only",
        "comparable with one asked for in the same list; this is how much.",
        "",
        "%-16s %-6s %10s %11s %11s %11s" % ("moment", "world", "identical",
                                            "changed px", "max dLuma",
                                            "dSeparation"),
        "-" * 72,
    ]
    for environment, tag, _title in _worlds():
        rows: dict[str, Any] = {}
        for key in shared:
            one, two = still("a", environment, key), still("b", environment, key)
            if not (os.path.isfile(one) and os.path.isfile(two)):
                continue
            same = _digest(one) == _digest(two)
            a, b = _pixels(one), _pixels(two)
            moved = np.abs(a - b).max(axis=2) > 2
            delta = np.abs(v272.luma(a) - v272.luma(b))
            sep_a = _separation_of("a", environment, key)
            sep_b = _separation_of("b", environment, key)
            row = {
                "identical": same,
                "changed": round(float(moved.mean()), 6),
                "max_dluma": round(float(delta.max()), 2),
                "separation_a": sep_a,
                "separation_b": sep_b,
                "d_separation": (None if sep_a is None or sep_b is None
                                 else round(sep_b - sep_a, 2)),
            }
            rows[key] = row
            lines.append("%-16s %-6s %10s %10.4f%% %11.1f %11s" % (
                key, tag, "yes" if same else "NO", row["changed"] * 100,
                row["max_dluma"],
                "-" if row["d_separation"] is None
                else "%+.2f" % row["d_separation"]))
        out["worlds"][tag] = rows
    worst = max(
        (abs(row["d_separation"])
         for world in out["worlds"].values() for row in world.values()
         if row.get("d_separation") is not None), default=0.0)
    out["worst_d_separation"] = round(float(worst), 2)
    lines += [
        "",
        "Worst separation difference between the two lists: %.2f luma." % worst,
        "",
        "That figure is the error bar on any number in this report that is",
        "quoted from one list beside a number from another. Inside this pass",
        "every comparison is list against itself; the only cross-list",
        "quotations are against V27.1's published table, which was taken on",
        "list A, and this pass's own list-A numbers are what stand beside it.",
    ]
    text = NEWLINE.join(lines)
    _write_json(os.path.join(LAB_DIR, "listcheck.json"), out)
    _write_text(os.path.join(DOC_DIR, "listcheck.txt"), text)
    print(text)
    return out


# --- the corrected measurement ----------------------------------------------


def _world_masks(listing: str, environment: str, key: str):
    marker = MARKERS[environment]
    whole = _pixels(still(listing, marker, key))
    world = _pixels(still(listing, marker, key, "world"))
    bands, machine = v272.background_mask(whole, world)
    background = np.zeros(machine.shape, dtype=bool)
    for mask in bands.values():
        background |= mask
    return bands, machine, background


def _separation_of(listing: str, environment: str, key: str) -> float | None:
    marker = MARKERS[environment]
    if not os.path.isfile(still(listing, marker, key)):
        return None
    pixels = _pixels(still(listing, environment, key))
    _bands, machine, background = _world_masks(listing, environment, key)
    return v272.separation(pixels, machine, background)


def stage_measure() -> dict[str, Any]:
    """Separation at every moment of both lists, through V27.1's instrument.

    **The mask, stated once.** `machine` is where hiding the machine changes
    the marker render by more than `v271.DIFF_FLOOR` = 24 of 255 on any
    channel; `background` is every pixel the four depth bands claim that the
    machine mask does not; `separation` is the mean luma of the first minus the
    mean luma of the second. Excluded from both: nothing. Every pixel of the
    frame is machine, background, or a band the marker did not paint - the sky,
    which is neither.
    """
    out: dict[str, Any] = {"seed": SEED, "lists": {}}
    cache: dict[tuple[str, str, str], Any] = {}
    for listing in ("a", "b"):
        worlds: dict[str, Any] = {}
        for environment, tag, title in _worlds():
            if not os.path.isfile(still(listing, environment,
                                        LIST_KEYS[listing][0])):
                continue
            rows: dict[str, Any] = {}
            for key in LIST_KEYS[listing]:
                pixels = _pixels(still(listing, environment, key))
                bands, machine, background = _world_masks(listing, environment,
                                                          key)
                cache[(listing, tag, key)] = (pixels, machine, background)
                grey = v272.luma(pixels)
                rows[key] = {
                    "separation": v272.separation(pixels, machine, background),
                    "collar": v272.collar(pixels, machine, background),
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
            worlds[tag] = {"environment": environment, "title": title,
                           "moments": rows}
        # The pairwise collar, on the silhouette two worlds share.
        pairs: dict[str, Any] = {}
        for key in LIST_KEYS[listing]:
            row: dict[str, Any] = {}
            if (listing, "v26", key) in cache:
                pa, ma, ba = cache[(listing, "v26", key)]
                for tag in ("v271", "v272"):
                    if (listing, tag, key) not in cache:
                        continue
                    pb, mb, bb = cache[(listing, tag, key)]
                    control, other = v272.collar_pair(pa, ma, ba, pb, mb, bb)
                    row["v26_vs_" + tag] = control
                    row[tag] = other
            pairs[key] = row
        out["lists"][listing] = {"worlds": worlds, "common_collar": pairs}
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
    return ("%%%d.%df" % (width, places)) % float(value)


def _measure_table(measured: dict[str, Any]) -> str:
    tags = [tag for _e, tag, _t in _worlds()]
    lines = [
        "THE MERGE CORRECTION",
        "machine-to-background separation in luma.",
        "",
        "  THE INSTRUMENT. `machine` is where hiding the machine changes the",
        "  marker render by more than 24/255 on any channel - an occlusion",
        "  test, V27.1's, not a hue classification. `background` is every",
        "  pixel the four depth bands claim and the machine mask does not.",
        "  Nothing is excluded from either; what belongs to neither is the",
        "  sky, which the marker does not paint. Both marker passes are",
        "  unshaded and un-fogged, so a world pixel is a constant colour",
        "  between them and the only thing that can differ is which object it",
        "  is. See sloped/v271_finish.machine_mask.",
        "",
    ]
    for listing, title in (("a", "1  List A: the twelve V27 moments"),
                           ("b", "2  List B: the brief's six proof frames")):
        block = measured["lists"].get(listing)
        if not block:
            continue
        lines += [title, ""]
        lines.append("%-16s %s   %s" % (
            "moment", "".join("%8s" % tag for tag in tags), "vs V26"))
        lines.append("-" * (18 + 8 * len(tags) + 12))
        for key in LIST_KEYS[listing]:
            row = "%-16s" % key
            values: dict[str, Any] = {}
            for tag in tags:
                got = (block["worlds"].get(tag, {}).get("moments", {})
                       .get(key, {}).get("separation"))
                values[tag] = got
                row += _cell(got)
            control = values.get("v26")
            last = values.get(tags[-1])
            if control is not None and last is not None:
                row += "   %+7.1f" % (last - control)
            lines.append(row)
        lines.append("")
        lines.append("  at the silhouette, on the machine both worlds show")
        lines.append("%-16s %8s %8s %8s" % ("moment", "v26", "v271", "v272"))
        lines.append("-" * 44)
        for key in LIST_KEYS[listing]:
            row = block["common_collar"].get(key, {})
            lines.append("%-16s %s %s %s" % (
                key, _cell(row.get("v26_vs_v272", row.get("v26_vs_v271"))),
                _cell(row.get("v271")), _cell(row.get("v272"))))
        lines.append("")
        lines.append("  exposure and clipping")
        lines.append("%-16s %-6s %9s %9s %9s" % ("moment", "world", "mean",
                                                 "clip wht", "clip blk"))
        lines.append("-" * 54)
        for key in LIST_KEYS[listing]:
            for tag in tags:
                row = (block["worlds"].get(tag, {}).get("moments", {})
                       .get(key, {}))
                if not row:
                    continue
                lines.append("%-16s %-6s %9.1f %8.2f%% %8.2f%%" % (
                    key, tag, row["mean_luma"], row["clip_white"] * 100,
                    row["clip_black"] * 100))
        lines.append("")
    block = measured["lists"].get("a")
    if block:
        lines += [
            "3  Against V27.1's published table (list A, same instrument)",
            "",
            "%-16s %8s %8s %8s %8s %8s" % ("moment", "V26 pub", "V26 now",
                                           "v271 pub", "v271 now", "v272 now"),
            "-" * 62,
        ]
        for key in LIST_KEYS["a"]:
            published = v272.V271_PUBLISHED.get(key, {})
            now = {tag: (block["worlds"].get(tag, {}).get("moments", {})
                         .get(key, {}).get("separation"))
                   for tag in tags}
            lines.append("%-16s %s %s %s %s %s" % (
                key, _cell(published.get("v26")), _cell(now.get("v26")),
                _cell(published.get("v271")), _cell(now.get("v271")),
                _cell(now.get("v272"))))
        lines += [
            "",
            "  `pub` is V27.1's own table, reproduced here from the same",
            "  profiles and the same list of seconds. A `now` that matches it",
            "  is the check that this pass's instrument is that pass's.",
        ]
    return NEWLINE.join(lines)


# --- stage: isolate ---------------------------------------------------------


def _isolate_mask(listing: str, name: str, key: str):
    """Where the one re-materialled object is, by difference rather than by hue.

    **This is the second version of this stage and the first one measured
    nothing.** It classified the probe by nearest hue, the way V27.1's material
    probe does, and every one of the eight objects came back at 0.00% cover - a
    clean, confident, finished-looking table of zeroes. The isolate hue is
    authored `#00FF80` and renders `(127, 243, 154)`: flat and stable, so the
    probe was working perfectly, but 130 units from where the classifier had
    been told to look, because an unshaded albedo still goes through the
    profile's own grade.

    So the hue is not used at all. An isolate probe differs from the base probe
    in exactly one material, so a pixel belongs to the isolated object **where
    the two probes disagree** - the same occlusion argument `v271.machine_mask`
    makes, and exact here for the same reason: every surface either probe
    paints is `unshaded` and `no_fog`, so a pixel that is not the isolated
    object is the same constant colour in both renders.

    The machine cannot appear in the difference either, because no profile
    palette names a machine key and the geometry does not move between the two
    probes. `stage_isolate` asserts that rather than assuming it.

    This is the third time in three passes that a mask built from colour has
    been wrong in a picture where the colour was not what it was authored as.
    The fix, as in V27.1, is to stop classifying and start differencing.
    """
    base = _pixels(still(listing, v272.PROBE, key))
    probe = _pixels(still(listing, name, key))
    return np.abs(base - probe).max(axis=2) > v272.DIFF_FLOOR


def stage_isolate(godot: str, render: bool = True) -> dict[str, Any]:
    """One probe per candidate object: which of them is the bright thing.

    This is the stage the correction is chosen from. Each probe is the base
    surface probe with **exactly one object** re-materialled to `hall_grate`, a
    key `contained_hall` builds nothing from, and the object is found by
    differencing the two probes rather than by looking for a colour - see
    :func:`_isolate_mask`.

    Three numbers per object, and the third is the one the fix is chosen on:

    * **cover** - how much of the frame the object is;
    * **luma** - what the *lit* frame of the parent reads over exactly that
      mask;
    * **lever** - the object's share of the **background**, which is how many
      luma of separation one luma of darkening it would buy. An object with a
      lever of 0.30 turns a 20-luma repaint into 6 luma of separation; an
      object with a lever of 0.01 cannot be the answer whatever its value is.
    """
    keys = list(LIST_KEYS["b"])
    if render:
        ephemeral = gen.diagnostics(over=v272.PARENT)
        with gen.temporary(ephemeral) as names:
            for name in names:
                print(f"--- {name} ---")
                _render_at(godot, name, "", LISTS["b"],
                           stills_dir("b", name), name)

    lit = {key: v272.luma(_pixels(still("b", v272.PARENT, key))) for key in keys}
    frames = {key: _world_masks("b", v272.PARENT, key) for key in keys}

    out: dict[str, Any] = {"objects": {}, "background": {}, "leak": {}}
    for key in keys:
        _bands, machine, background = frames[key]
        out["background"][key] = {
            "cover": round(float(background.mean()), 5),
            "luma": round(float(lit[key][background].mean()), 2),
            "machine_cover": round(float(machine.mean()), 5),
            "machine_luma": round(float(lit[key][machine].mean()), 2),
        }

    lines = [
        "WHICH OBJECT IS THE BRIGHT ONE",
        "one probe per candidate, each re-materialling exactly that object to",
        "%s - the one hall key contained_hall builds nothing from - and"
        % v272.ISOLATE_KEY,
        "the object found by DIFFERENCING the two probes rather than by hue.",
        "The first version of this stage classified by hue and reported 0.00%",
        "for every object; see _isolate_mask for why, and why it is a",
        "difference now.",
        "",
        "cover is the share of the whole frame. luma is read off the LIT frame",
        "of %s over exactly that mask. lever is the object's" % v272.PARENT,
        "share of the background: the luma of separation that one luma of",
        "darkening it would buy.",
        "",
        "%-24s %s" % ("object", "".join("%24s" % k for k in v272.MERGE)),
        "%-24s %s" % ("", "".join("%8s%8s%8s" % ("cover", "luma", "lever")
                                  for _ in v272.MERGE)),
        "-" * (25 + 24 * len(v272.MERGE)),
    ]
    for one in v272.ISOLATES:
        name = v272.isolate_id(one.key)
        row: dict[str, Any] = {"title": one.title, "material": one.material,
                               "why": one.why, "moments": {}}
        cells = ""
        for key in keys:
            if not os.path.isfile(still("b", name, key)):
                row["moments"][key] = None
                if key in v272.MERGE:
                    cells += "%8s%8s%8s" % ("-", "-", "-")
                continue
            _bands, machine, background = frames[key]
            mask = _isolate_mask("b", name, key)
            leak = float((mask & machine).mean())
            out["leak"][f"{one.key}/{key}"] = round(leak, 6)
            inside = mask & background
            cover = float(mask.mean())
            share = (float(inside.sum()) / float(background.sum())
                     if int(background.sum()) else 0.0)
            value = (round(float(lit[key][mask].mean()), 1)
                     if int(mask.sum()) > 200 else None)
            row["moments"][key] = {"cover": round(cover, 5), "luma": value,
                                   "lever": round(share, 5),
                                   "leak": round(leak, 6)}
            if key in v272.MERGE:
                cells += "%7.2f%%%8s%8.3f" % (
                    cover * 100, "-" if value is None else "%.1f" % value,
                    share)
        out["objects"][one.key] = row
        lines.append("%-24s %s" % (one.title[:24], cells))

    worst_leak = max(out["leak"].values(), default=0.0)
    lines += [
        "",
        "%-24s %s" % ("the machine, for scale", "".join(
            "%7.2f%%%8.1f%8s" % (out["background"][k]["machine_cover"] * 100,
                                 out["background"][k]["machine_luma"], "-")
            for k in v272.MERGE)),
        "%-24s %s" % ("the whole background", "".join(
            "%7.2f%%%8.1f%8s" % (out["background"][k]["cover"] * 100,
                                 out["background"][k]["luma"], "1.000")
            for k in v272.MERGE)),
        "",
        "Machine leak, worst of every object at every moment: %.4f%% of frame."
        % (worst_leak * 100),
        "  A re-materialled world object may not change a machine pixel - no",
        "  profile palette names a machine key and the geometry does not move -",
        "  so this is the check that a difference mask is the object and only",
        "  the object. Anything but ~0 would mean a probe moved something it",
        "  was not asked to.",
        "",
    ]

    ranked = _rank(out)
    out["ranked"] = ranked
    lines += [
        "RANKED BY WHAT DARKENING EACH OBJECT WOULD BUY AT THE MERGE",
        "",
        "  `headroom` is how far the object sits above the background it is",
        "  part of. `gain` is lever x headroom: the separation this pass would",
        "  win by taking this one object down to the background's own average -",
        "  the first-order size of the prize, before any particular new value",
        "  is chosen. Averaged over the three merge moments.",
        "",
        "%-24s %8s %8s %9s %9s %8s" % ("object", "cover", "luma", "lever",
                                       "headroom", "gain"),
        "-" * 72,
    ]
    for entry in ranked:
        lines.append("%-24s %7.2f%% %8s %9.3f %9s %8.2f" % (
            entry["title"][:24], entry["cover"] * 100,
            "-" if entry["luma"] is None else "%.1f" % entry["luma"],
            entry["lever"],
            "-" if entry["headroom"] is None else "%+.1f" % entry["headroom"],
            entry["gain"]))
    total = sum(entry["lever"] for entry in ranked)
    lines += [
        "",
        "The eight candidates are %.1f%% of the merge background between them."
        % (total * 100),
        "What is left is the course's own landform, which is not a hall surface",
        "and may not be repainted: GEOMETRY IS NOT THEME binds the",
        "heightfield's materials as well as its shape.",
    ]
    text = NEWLINE.join(lines)
    _write_json(os.path.join(LAB_DIR, "isolate.json"), out)
    _write_text(os.path.join(DOC_DIR, "isolate.txt"), text)
    print(text)
    return out


def _rank(measured: dict[str, Any]) -> list[dict[str, Any]]:
    """Each object's first-order prize at the merge, averaged over the three."""
    out: list[dict[str, Any]] = []
    background = float(np.mean([measured["background"][m]["luma"]
                                for m in v272.MERGE]))
    for key, row in measured["objects"].items():
        covers, lumas, levers, gains = [], [], [], []
        for moment in v272.MERGE:
            cell = row["moments"].get(moment)
            if not cell:
                continue
            covers.append(cell["cover"])
            levers.append(cell["lever"])
            if cell["luma"] is None:
                continue
            lumas.append(cell["luma"])
            gains.append(cell["lever"]
                         * (cell["luma"] - measured["background"][moment]["luma"]))
        mean_luma = float(np.mean(lumas)) if lumas else None
        out.append({
            "key": key,
            "title": row["title"],
            "material": row["material"],
            "cover": round(float(np.mean(covers)), 5) if covers else 0.0,
            "luma": round(mean_luma, 1) if mean_luma is not None else None,
            "lever": round(float(np.mean(levers)), 5) if levers else 0.0,
            "headroom": (round(mean_luma - background, 1)
                         if mean_luma is not None else None),
            "gain": round(float(np.mean(gains)), 2) if gains else 0.0,
        })
    out.sort(key=lambda one: one["gain"], reverse=True)
    return out


# --- stage: coverage --------------------------------------------------------


def stage_coverage() -> dict[str, Any]:
    """How much of the merge gap is contrast, and how much is coverage.

    **This is the stage that says what the 22-luma headline actually is**, and
    it is the same shape of finding as V27.1 §3: most of the number was the
    ruler, and the part that is real is smaller and fixable.

    `separation` is a mean over the machine minus a mean over the background,
    and each world supplies its own two populations. That is the right question
    for one picture and the wrong one for a comparison, because the two worlds
    do not show the same machine: V26's foreground rock stands in front of the
    course and hides some of it, and what it hides is the far, dark, lower edge.
    Remove that and V26's *visible* machine is its bright half, so V26's machine
    mean is lifted by an occluder rather than by contrast.

    So this splits the gap four ways at each moment:

        dMachine    each world's own machine mean, difference
        dBackground each world's own background mean, difference
        dMachine_c  the same machines measured on the pixels BOTH worlds show
        dBackground_c   the same for the background

    `dMachine_c` is the honest machine term and it is ~0 everywhere: the hall
    does not darken the machine at all. `dBackground_c` is the honest and
    entirely real background term, and it is what the correction acts on.

    **Masks, stated exactly.** Machine is `v271.machine_mask` on each world's
    own marker pair - a pixel where hiding the machine changes the render by
    more than 24/255 on any channel. Background is the union of the four depth
    bands minus that machine. `common` is the intersection of the two worlds'
    masks, taken separately for machine and for background. Excluded from every
    figure: pixels in neither population, which is the sky. Nothing else is
    dropped, sampled or weighted.
    """
    out: dict[str, Any] = {"moments": {}}
    lines = [
        "CONTRAST, OR COVERAGE",
        "the merge gap split into the part that is the picture and the part",
        "that is the two worlds not showing the same machine.",
        "",
        "%-16s %9s %9s %9s %10s %11s" % ("moment", "dSep", "dMachine",
                                         "dBackgnd", "dMach_same",
                                         "dBackg_same"),
        "-" * 70,
    ]
    for key in LIST_KEYS["b"]:
        control = still("b", v272.CONTROL, key)
        mine = still("b", v272.PROFILE, key)
        if not (os.path.isfile(control) and os.path.isfile(mine)):
            continue
        pa = _pixels(control)
        _x, ma, ba = _world_masks("b", v272.CONTROL, key)
        _y, mb, bb = _world_masks("b", v272.PARENT, key)
        ga = v272.luma(pa)
        rows: dict[str, Any] = {}
        for tag, folder in (("v271", v272.PARENT), ("v272", v272.PROFILE)):
            gb = v272.luma(_pixels(still("b", folder, key)))
            common_m, common_b = ma & mb, ba & bb
            rows[tag] = {
                "d_separation": round(float(
                    (gb[mb].mean() - gb[bb].mean())
                    - (ga[ma].mean() - ga[ba].mean())), 2),
                "d_machine": round(float(gb[mb].mean() - ga[ma].mean()), 2),
                "d_background": round(float(gb[bb].mean() - ga[ba].mean()), 2),
                "d_machine_common": round(float(
                    gb[common_m].mean() - ga[common_m].mean()), 2),
                "d_background_common": round(float(
                    gb[common_b].mean() - ga[common_b].mean()), 2),
                "separation_common": round(float(
                    gb[common_m].mean() - gb[common_b].mean()), 2),
                "control_common": round(float(
                    ga[common_m].mean() - ga[common_b].mean()), 2),
                "machine_cover": round(float(mb.mean()), 5),
                "control_cover": round(float(ma.mean()), 5),
            }
        out["moments"][key] = rows
        row = rows["v271"]
        lines.append("%-16s %9.2f %9.2f %9.2f %10.2f %11.2f" % (
            key, row["d_separation"], row["d_machine"], row["d_background"],
            row["d_machine_common"], row["d_background_common"]))
    lines += [
        "",
        "  read on V27.1 against V26, before the correction.",
        "",
        "  dMach_same is ~0 at every moment: measured on the pixels both",
        "  worlds show, the hall does not darken the machine. The large",
        "  negative dMachine beside it is V26's foreground rock hiding the",
        "  machine's own dark lower edge, which lifts V26's visible-machine",
        "  mean and is not a contrast difference at all.",
        "",
        "  dBackg_same is the real defect, and it is the one the correction",
        "  acts on.",
        "",
        "SEPARATION ON THE PIXELS BOTH WORLDS SHOW",
        "",
        "%-16s %9s %9s %9s" % ("moment", "v26", "v271", "v272"),
        "-" * 48,
    ]
    for key, rows in out["moments"].items():
        lines.append("%-16s %9.1f %9.1f %9.1f" % (
            key, rows["v271"]["control_common"],
            rows["v271"]["separation_common"],
            rows["v272"]["separation_common"]))
    lines += [
        "",
        "  This is the brief's number asked as a like-for-like question: one",
        "  machine mask, one background mask, both worlds measured over them.",
        "  It is the pairing V27.1 built `collar_pair` for, applied to the",
        "  whole frame rather than to the silhouette.",
    ]
    text = NEWLINE.join(lines)
    _write_json(os.path.join(LAB_DIR, "coverage.json"), out)
    _write_text(os.path.join(DOC_DIR, "coverage.txt"), text)
    print(text)
    return out


# --- stage: mechanism -------------------------------------------------------

#: `hall_panel_dark`, exactly as `contained_hall` authors it. Every variant
#: below is this row with one field moved, so a difference in the table is a
#: difference of one field.
PANEL_DARK = {"albedo": "#151920", "roughness": 0.88,
              "soft_light": "#1E2632", "floor_lift": "#11161E"}

#: The decomposition, and then the ladder that chose the value.
#:
#: A palette row merges field by field, and `None` **erases** an inherited key -
#: which is the only way to turn the backlight off, since `_retune` enables it
#: from the presence of `soft_light` rather than from its value.
MECHANISM: tuple[tuple[str, str, dict[str, Any]], ...] = (
    ("no_albedo", "albedo black, everything else the parent's",
     dict(PANEL_DARK, albedo="#000000")),
    ("no_emission", "floor_lift black: the emissive floor off",
     dict(PANEL_DARK, floor_lift="#000000")),
    ("no_backlight", "soft_light erased: the backlight off",
     dict(PANEL_DARK, soft_light=None)),
    ("nothing", "black, un-emissive, un-backlit - and still not dark",
     {"albedo": "#000000", "roughness": 0.88, "floor_lift": "#000000",
      "soft_light": None}),
    ("no_fog", "the same, with fog disabled: the floor is not fog",
     {"albedo": "#000000", "roughness": 0.88, "floor_lift": "#000000",
      "soft_light": None, "no_fog": True}),
    ("spec_00", "specular 0.00", dict(PANEL_DARK, specular=0.0)),
    ("spec_06", "specular 0.06  <- the delta", dict(PANEL_DARK, specular=0.06)),
    ("spec_12", "specular 0.12", dict(PANEL_DARK, specular=0.12)),
    ("spec_20", "specular 0.20", dict(PANEL_DARK, specular=0.20)),
    ("spec_30", "specular 0.30", dict(PANEL_DARK, specular=0.30)),
)


def _mechanism_id(key: str) -> str:
    return "_trial_v272_" + key


def stage_mechanism(godot: str, render: bool = True) -> dict[str, Any]:
    """Why the surface is bright, field by field, and why the value is 0.06.

    `--stage isolate` names the object and the material. This says what is
    actually producing the light, and it is the stage that overturned the
    obvious answer.

    Read down the table. Taking `hall_panel_dark`'s albedo to **black** leaves
    36.7 of its 46.0 luma at the merge. Turning its emissive floor off leaves
    41.1. Turning its backlight off as well leaves 31.3. Disabling fog on top
    of all three changes nothing at all, to a tenth of a luma - so the floor is
    not fog, not value, not emission and not the soft term.

    It is a **specular lobe**. `lab_palette._matte` sets albedo, metallic and
    roughness and never touches `metallic_specular`, so the material runs at
    StandardMaterial3D's default 0.5; at roughness 0.88 that lobe is wide
    enough to take a sheen from all five of the rig's directional lights at
    once and lay it evenly over the whole surface. `specular: 0.0` takes the
    same slab, with its authored value untouched, from 46.0 to 13.7.

    **It carries no form.** The surface's own 5th-to-95th percentile spread is
    0.8 luma with the lobe and 0.8 without it, so what is being removed is a
    flat lift rather than a highlight. The stage prints that spread beside
    `hall_rib`'s, which is 27.4 - a real vertical highlight band, on a material
    this pass therefore does not touch.
    """
    if render:
        # The summary is padded out deliberately. A temporary profile is in
        # the registry for as long as it takes to render, and anything else
        # reading the registry in that window - another session's test run,
        # for one - sees it and holds it to the same standard as a shipped
        # profile. `test_sloped_environment` wants more than 80 characters of
        # it, and a diagnostic that fails somebody else's suite while it
        # exists is not worth the two lines it saves.
        documents = [{"id": _mechanism_id(key), "title": f"V27.2 trial: {key}",
                      "family": "diagnostic",
                      "summary": (
                          "V27.2 mechanism trial, ephemeral: "
                          "contained_hall_v271 with hall_panel_dark's palette "
                          "row changed in one field - %s - so the merge bay's "
                          "backing slab can be read with that term and only "
                          "that term removed" % note),
                      "extends": v272.PARENT,
                      "palette": {"hall_panel_dark": row}}
                     for key, note, row in MECHANISM]
        with gen.temporary(documents) as names:
            for name in names:
                print(f"--- {name} ---")
                _render_at(godot, name, "", LISTS["b"], stills_dir("b", name),
                           name)

    backing = {key: _isolate_mask("b", v272.isolate_id("merge_backing"), key)
               for key in v272.MERGE}
    wall = {key: _isolate_mask("b", v272.isolate_id("wall_lower"), key)
            for key in v272.MERGE}

    def row_for(folder: str, masks: str = v272.PARENT) -> dict[str, Any] | None:
        """One variant's numbers, read through `masks`' own marker pair.

        Every variant here is `contained_hall_v271` with one palette field
        moved, so its machine and its band union are the parent's, and the
        parent's marker is the right ruler for all of them. **The control is
        not.** The first version of this table read V26's pixels through the
        hall's masks and printed 104.8 for a frame that measures 120.3 - the
        same class of mistake as measuring two worlds with one mask, which is
        what V27.1 was written to correct.
        """
        if not os.path.isfile(still("b", folder, "merge")):
            return None
        out: dict[str, Any] = {}
        for key in v272.MERGE:
            grey = v272.luma(_pixels(still("b", folder, key)))
            _b, machine, background = _world_masks("b", masks, key)
            inside = grey[backing[key]]
            out[key] = {
                "separation": round(float(grey[machine].mean()
                                          - grey[background].mean()), 2),
                "backing": round(float(inside.mean()), 1),
                "wall": round(float(grey[wall[key]].mean()), 1),
                "spread": round(float(np.percentile(inside, 95)
                                      - np.percentile(inside, 5)), 1),
                "clip_black": round(float((grey <= 5.0).mean()), 5),
            }
        return out

    out: dict[str, Any] = {"variants": {}}
    order = [("v271 base", v272.PARENT, "contained_hall_v271, unchanged")]
    order += [(key, _mechanism_id(key), note) for key, note, _row in MECHANISM]
    lines = [
        "WHY THE SURFACE IS BRIGHT, AND WHY THE VALUE IS 0.06",
        "hall_panel_dark, one field at a time. Every row is contained_hall's",
        "own palette entry with a single field moved, rendered over",
        "contained_hall_v271 and read on the merge bay's backing slab.",
        "",
        "%-13s %s  %s" % ("variant", "".join("%8s%8s" % (m[:7], "back")
                                             for m in v272.MERGE), "note"),
        "-" * 100,
    ]
    for label, folder, note in order:
        row = row_for(folder)
        if row is None:
            continue
        out["variants"][label] = row
        cells = "".join("%8.1f%8.1f" % (row[m]["separation"], row[m]["backing"])
                        for m in v272.MERGE)
        lines.append("%-13s %s  %s" % (label, cells, note))

    control = row_for(v272.CONTROL, masks=v272.CONTROL)
    if control:
        lines.append("%-13s %s  %s" % (
            "v26", "".join("%8.1f%8s" % (control[m]["separation"], "-")
                           for m in v272.MERGE), "the outdoor control"))

    base = out["variants"].get("v271 base", {})
    chosen = out["variants"].get("spec_06", {})
    nothing = out["variants"].get("nothing", {})
    no_fog = out["variants"].get("no_fog", {})
    if base and nothing:
        lines += [
            "",
            "THE DECOMPOSITION, at the merge",
            "",
            "  the surface as authored                     %5.1f luma"
            % base["merge"]["backing"],
            "  with its albedo taken to black              %5.1f"
            % out["variants"]["no_albedo"]["merge"]["backing"],
            "  with its emissive floor off                 %5.1f"
            % out["variants"]["no_emission"]["merge"]["backing"],
            "  black, un-emissive and un-backlit           %5.1f"
            % nothing["merge"]["backing"],
            "  the same with fog disabled                  %5.1f"
            % (no_fog["merge"]["backing"] if no_fog
               else nothing["merge"]["backing"]),
            "  as authored, with specular 0.06             %5.1f"
            % (chosen["merge"]["backing"] if chosen else float("nan")),
            "",
            "  A black, un-emissive, un-backlit, un-fogged surface still reads",
            "  %.1f. That is a specular lobe: lab_palette._matte never sets"
            % nothing["merge"]["backing"],
            "  metallic_specular, so the material runs at StandardMaterial3D's",
            "  default 0.5, and at roughness 0.88 the lobe is broad enough to",
            "  take an even sheen from all five directional lights at once.",
            "",
            "  It is a LIFT AND NOT A HIGHLIGHT. The slab's own 5th-to-95th",
            "  percentile spread is %.1f luma as authored and %.1f at 0.06, so"
            % (base["merge"]["spread"],
               chosen["merge"]["spread"] if chosen else float("nan")),
            "  nothing that describes the form is being removed.",
        ]

    # The material this pass does NOT touch, and why.
    probe = still("b", v272.PROBE, "merge")
    if os.path.isfile(probe):
        hue = np.array([int("#FF00FF"[i:i + 2], 16) for i in (1, 3, 5)],
                       dtype=float)
        _b, machine, background = _world_masks("b", v272.PARENT, "merge")
        rib = (np.linalg.norm(_pixels(probe) - hue[None, None, :], axis=2)
               < 40.0) & background
        grey = v272.luma(_pixels(still("b", v272.PARENT, "merge")))[rib]
        spread = float(np.percentile(grey, 95) - np.percentile(grey, 5))
        out["hall_rib"] = {"cover": round(float(rib.mean()), 5),
                           "luma": round(float(grey.mean()), 1),
                           "spread": round(spread, 1)}
        lines += [
            "",
            "  For contrast, hall_rib on the same frame: %.2f%% of the picture"
            % (rib.mean() * 100),
            "  at %.1f luma, spread %.1f. That lobe IS a highlight - it is the"
            % (grey.mean(), spread),
            "  vertical band a viewer reads the wall's height off, which",
            "  environment_stage._shell_rib exists for - so hall_rib keeps its",
            "  specular and this pass does not touch it.",
        ]
    text = NEWLINE.join(lines)
    _write_json(os.path.join(LAB_DIR, "mechanism.json"), out)
    _write_text(os.path.join(DOC_DIR, "mechanism.txt"), text)
    print(text)
    return out


def stage_mechanism_sheet() -> str:
    """The ladder as pictures: the value was looked at, not only measured."""
    columns = [("V26", v272.CONTROL), ("V27.1", v272.PARENT)]
    columns += [(key.replace("_", " "), _mechanism_id(key))
                for key in ("spec_00", "spec_06", "spec_12", "spec_20",
                            "spec_30")
                if os.path.isfile(still("b", _mechanism_id(key), "merge"))]
    width = 220
    height = int(round(width * HEIGHT / WIDTH))
    gutter, top, left = 12, 108, 170
    sheet = Image.new("RGB",
                      (left + len(columns) * (width + gutter) + gutter,
                       top + len(v272.MERGE) * (height + gutter) + gutter),
                      SHEET_BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    _label(draw, (gutter, 20), "THE SPECULAR LADDER ON hall_panel_dark", 28)
    _label(draw, (gutter, 58),
           "one field, five values, and the two worlds it sits between. "
           "0.06 ships.", 18, SHEET_DIM)
    for index, (name, _folder) in enumerate(columns):
        _label(draw, (left + index * (width + gutter), top - 26), name, 18)
    for order, key in enumerate(v272.MERGE):
        y = top + order * (height + gutter)
        _label(draw, (gutter, y + 6), v272.moment(key).title, 17)
        draw.line([(gutter, y - 5), (sheet.width - gutter, y - 5)],
                  fill=SHEET_RULE)
        for index, (_name, folder) in enumerate(columns):
            sheet.paste(_thumb(still("b", folder, key), (width, height)),
                        (left + index * (width + gutter), y))
    os.makedirs(DOC_DIR, exist_ok=True)
    out = os.path.join(DOC_DIR, "mechanism.png")
    sheet.save(out)
    print("wrote " + out)
    return out


# --- stage: surfaces --------------------------------------------------------


def stage_surfaces() -> dict[str, Any]:
    """The same frames by material, for the record.

    Kept beside `--stage isolate` rather than replaced by it, because a
    material table is what the two earlier passes published and a reader
    checking this one against them needs the same view. Where a material is
    shared by more than one object the isolate table is the one that answers
    the question; this one says how much there is of each *key*.
    """
    out: dict[str, Any] = {}
    lines = [
        "WHAT IS BEHIND THE MERGE, BY MATERIAL",
        "the hall's own materials, each rendered its own flat hue and read off",
        "the lit frame of %s. The machine is masked out first." % v272.PARENT,
        "",
    ]
    for key in LIST_KEYS["b"]:
        probe_path = still("b", v272.PROBE, key)
        if not os.path.isfile(probe_path):
            continue
        _bands, machine, _background = _world_masks("b", v272.PARENT, key)
        masks = v272.surface_masks(_pixels(probe_path), machine)
        grey = v272.luma(_pixels(still("b", v272.PARENT, key)))
        after = (v272.luma(_pixels(still("b", v272.PROFILE, key)))
                 if os.path.isfile(still("b", v272.PROFILE, key)) else None)
        rows = []
        lines += [f"  {key}", "    %-18s %7s %8s %8s" % (
            "surface", "cover", "V27.1", "V27.2"), "    " + "-" * 44]
        for name, mask in masks.items():
            if float(mask.mean()) < 0.002:
                continue
            row = {
                "surface": name,
                "cover": round(float(mask.mean()), 4),
                "luma_v271": round(float(grey[mask].mean()), 1),
                "luma_v272": (round(float(after[mask].mean()), 1)
                              if after is not None else None),
            }
            rows.append(row)
            lines.append("    %-18s %6.2f%% %8.1f %8s" % (
                name, row["cover"] * 100, row["luma_v271"],
                "-" if row["luma_v272"] is None else "%.1f" % row["luma_v272"]))
        lines.append("")
        out[key] = rows
    lines += [
        "  A material is not an object: `hall_panel_dark` is the lower wall,",
        "  the merge bay's backing and the fork's wings at once, and",
        "  `hall_deck_dark` is the outer ring and the finish pad. --stage",
        "  isolate is where those are told apart.",
    ]
    text = NEWLINE.join(lines)
    _write_json(os.path.join(LAB_DIR, "surfaces.json"), out)
    _write_text(os.path.join(DOC_DIR, "surfaces.txt"), text)
    print(text)
    return out


# --- stage: delta -----------------------------------------------------------


def stage_delta() -> dict[str, Any]:
    """Exactly which frames the delta reaches, and whether any of them falls."""
    out: dict[str, Any] = {}
    lines = [
        "WHERE THE DELTA LANDS",
        "%s against %s, frame by frame, on list A." % (v272.PARENT,
                                                       v272.PROFILE),
        "",
        "%-16s %11s %9s %9s %10s %9s %9s" % (
            "moment", "changed px", "max dL", "mean dL", "dSeparation",
            "blk V27.1", "blk V27.2"),
        "-" * 82,
    ]
    for key in LIST_KEYS["a"]:
        before_path = still("a", v272.PARENT, key)
        after_path = still("a", v272.PROFILE, key)
        if not (os.path.isfile(before_path) and os.path.isfile(after_path)):
            continue
        before = _pixels(before_path)
        after = _pixels(after_path)
        moved = np.abs(before - after).max(axis=2) > 2
        delta = np.abs(v272.luma(before) - v272.luma(after))
        one = _separation_of("a", v272.PARENT, key)
        two = _separation_of("a", v272.PROFILE, key)
        grey_before, grey_after = v272.luma(before), v272.luma(after)
        row = {
            "changed": round(float(moved.mean()), 5),
            "max_dluma": round(float(delta.max()), 2),
            "mean_dluma": round(float(delta[moved].mean()), 2)
            if int(moved.sum()) else 0.0,
            "separation_before": one,
            "separation_after": two,
            "d_separation": (None if one is None or two is None
                             else round(two - one, 2)),
            "clip_black_before": round(float((grey_before <= 5.0).mean()), 5),
            "clip_black_after": round(float((grey_after <= 5.0).mean()), 5),
            "clip_white_before": round(float((grey_before >= 250.0).mean()), 5),
            "clip_white_after": round(float((grey_after >= 250.0).mean()), 5),
            # what the delta does inside its own region, which is where the
            # black floor question actually lives
            "region_luma_before": round(float(np.median(grey_before[moved])), 1)
            if int(moved.sum()) else None,
            "region_luma_after": round(float(np.median(grey_after[moved])), 1)
            if int(moved.sum()) else None,
            "region_black_after": round(float((grey_after[moved] <= 5.0).mean()),
                                        4) if int(moved.sum()) else None,
        }
        out[key] = row
        lines.append("%-16s %10.3f%% %9.1f %9.2f %10s %8.2f%% %8.2f%%" % (
            key, row["changed"] * 100, row["max_dluma"], row["mean_dluma"],
            "-" if row["d_separation"] is None
            else "%+.2f" % row["d_separation"],
            row["clip_black_before"] * 100, row["clip_black_after"] * 100))
    untouched = [k for k, v in out.items() if v["changed"] == 0.0]
    worse = [k for k, v in out.items()
             if v["d_separation"] is not None and v["d_separation"] < -0.05]
    crushed = sorted(((v["clip_black_after"] - v["clip_black_before"]), k)
                     for k, v in out.items())
    lines += [
        "",
        "Untouched, byte for byte: " + (", ".join(untouched) or "none") + ".",
        "Separation regressed by more than 0.05 luma: "
        + (", ".join(worse) or "none") + ".",
        "White clipping moves at any moment by: %.4f points of a per cent."
        % (max(abs(v["clip_white_after"] - v["clip_white_before"])
               for v in out.values()) * 100),
        "",
        "THE BLACK FLOOR, which is the delta's one real cost.",
        "",
        "  Taking the lobe off a surface that was already dark puts part of it",
        "  under luma 5. It is not a tuning error and a higher specular does",
        "  not fix it: at the branch, whole-frame black clipping is 10.12% at",
        "  0.06, 10.02% at 0.12 and 9.78% at 0.20, while the merge's gain",
        "  falls from +9.41 to +7.90 across the same range. The dial for a",
        "  black floor is floor_lift, and this pass does not turn it.",
        "",
        "%-16s %14s %14s %14s %12s" % ("moment", "region of frame",
                                       "region luma", "region luma",
                                       "region <= 5"),
        "%-16s %14s %14s %14s %12s" % ("", "", "V27.1", "V27.2", "V27.2"),
        "-" * 74,
    ]
    for key, row in out.items():
        if row["region_luma_before"] is None:
            continue
        lines.append("%-16s %13.1f%% %14.1f %14.1f %11.1f%%" % (
            key, row["changed"] * 100, row["region_luma_before"],
            row["region_luma_after"], row["region_black_after"] * 100))
    lines += [
        "",
        "  Where the surface was bright - the merge at 45.7, the final",
        "  approach at 45.0 - it lands near 14 and nothing clips. Where it was",
        "  already dark - the fork family at about 12 - it lands near 6 and a",
        "  third of it goes under the floor. The moments that gain the most",
        "  are the ones that clip the least, which is the whole shape of the",
        "  trade.",
        "",
        "  At 270 x 480 the three fork frames are not distinguishable from",
        "  V27.1's by eye; what changes is the depth of an already-dark",
        "  ground, not the presence of detail, because the ribs, trim and",
        "  beams that carry the wall's form are other materials and are",
        "  untouched. docs/.../fork_phone.png is that comparison.",
    ]
    text = NEWLINE.join(lines)
    _write_json(os.path.join(LAB_DIR, "delta.json"), out)
    _write_text(os.path.join(DOC_DIR, "delta.txt"), text)
    print(text)
    return out


# --- stage: the brief's regression guards -----------------------------------


def stage_regress() -> dict[str, Any]:
    """The brief's guards, in one table: hook, obstacle, fork, finish.

    Each row is a moment the correction is not allowed to cost anything, the
    three worlds' separation at it, and whether V27.2 holds V27.1's figure.
    `frame0` additionally has to be byte-identical.
    """
    out: dict[str, Any] = {"moments": {}}
    lines = [
        "THE REGRESSION GUARDS",
        "every moment the merge correction is not allowed to cost anything.",
        "",
        "%-16s %8s %8s %8s %10s  %s" % ("moment", "v26", "v271", "v272",
                                        "v272-v271", "guard"),
        "-" * 96,
    ]
    worst = 0.0
    for key, why in v272.REGRESSION:
        one = _separation_of("a", v272.PARENT, key)
        two = _separation_of("a", v272.PROFILE, key)
        control = _separation_of("a", v272.CONTROL, key)
        step = None if one is None or two is None else round(two - one, 2)
        if step is not None:
            worst = min(worst, step)
        out["moments"][key] = {"v26": control, "v271": one, "v272": two,
                               "step": step, "guard": why}
        lines.append("%-16s %s %s %s %10s  %s" % (
            key, _cell(control), _cell(one), _cell(two),
            "-" if step is None else "%+.2f" % step, why))
    identical = None
    zero_before, zero_after = (still("a", v272.PARENT, "frame0"),
                               still("a", v272.PROFILE, "frame0"))
    if os.path.isfile(zero_before) and os.path.isfile(zero_after):
        identical = _digest(zero_before) == _digest(zero_after)
    out["frame0_identical"] = identical
    out["worst_step"] = round(worst, 2)
    lines += [
        "",
        "Frame 0 against V27.1: %s." % (
            "byte-identical" if identical else
            "NOT byte-identical - the correction reached the hook"
            if identical is False else "not rendered"),
        "Worst step at any guarded moment: %+.2f luma." % worst,
    ]
    text = NEWLINE.join(lines)
    _write_json(os.path.join(LAB_DIR, "regress.json"), out)
    _write_text(os.path.join(DOC_DIR, "regress.txt"), text)
    print(text)
    return out


# --- stage: the winner, the card, the hook ----------------------------------


def _winner_at(track: dict[str, Any], replay: dict[str, Any],
               key: str) -> dict[str, Any]:
    """Where the winning marble is on screen. V27.1's own, on V27.2's moments."""
    one = v272.moment(key)
    frames = v272.frames_of(track)
    frame = v272.frame_at(frames, one.replay)
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


_patch = finish_lab._patch


def stage_winner() -> dict[str, Any]:
    """The purple racer at the finish, and at the merge on the way to it."""
    track = _load(TRACK)
    replay = _load(REPLAY)
    keys = ("merge", "final_approach", "winner", "payoff")
    out: dict[str, Any] = {"winner": v271.FLAG_RACER,
                           "label": v24_payoff.winner_label(v271.FLAG_RACER),
                           "moments": {}}
    lines = [
        "THE WINNER, THROUGH THE MERGE AND THE FINISH",
        "marble %d, %s. Projected from the replay, not read off a sheet."
        % (v271.FLAG_RACER, v24_payoff.winner_label(v271.FLAG_RACER)),
        "",
        "%-16s %-6s %9s %7s %6s %11s %9s" % ("moment", "world", "on screen",
                                             "px", "occl", "dE surround",
                                             "surround"),
        "-" * 74,
    ]
    for key in keys:
        where = _winner_at(track, replay, key)
        out["moments"][key] = {"where": where, "worlds": {}}
        for environment, tag, _title in _worlds():
            row: dict[str, Any] = {}
            path = still("b", environment, key)
            if where.get("on_screen") and os.path.isfile(path):
                pixels = _pixels(path)
                _b, machine, _bg = _world_masks("b", environment, key)
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
                        "surround_luma": round(float(v272.luma(around)), 1),
                    }
            out["moments"][key]["worlds"][tag] = row
            lines.append("%-16s %-6s %9s %7s %6s %11s %9s" % (
                key, tag,
                "yes" if where.get("on_screen") else "NO",
                ("%.0f" % where["px"]) if where.get("on_screen") else "-",
                ("%.2f" % row["occluded"]) if row.get("occluded") is not None
                else "-",
                ("%.1f" % row["delta_e"]) if row else "-",
                ("%.1f" % row["surround_luma"]) if row else "-"))
        lines.append("")
    lines += [
        "`occl` is the share of the marble's own patch the world stands in",
        "front of: 0.00 is a clear marble. `dE surround` is the marble's mean",
        "RGB distance from the ring of picture just outside it.",
        "",
        "Measured on list B, so the merge row and the finish rows are the same",
        "render. V27.1 published 132.0 at the winner and 125.4 at the payoff,",
        "on list A; --stage listcheck is the bridge between the two.",
    ]
    text = NEWLINE.join(lines)
    _write_json(os.path.join(LAB_DIR, "winner.json"), out)
    _write_text(os.path.join(DOC_DIR, "winner.txt"), text)
    print(text)
    return out


def stage_payoff() -> dict[str, Any]:
    """V24's card, unchanged, on each world's own payoff frame."""
    card = v24_payoff.build()
    out: dict[str, Any] = {"style": card.style, "label": card.label,
                           "text_contrast": round(card.text_contrast, 2),
                           "worlds": {}}
    lines = [
        "THE PAYOFF CARD",
        "V24's own card, unchanged, measured with v24_payoff.measured_contrast",
        "on each world's payoff frame - ink against the composited picture.",
        "",
        "%-6s %-22s %9s %9s %9s" % ("world", "title", "worst", "median",
                                    "band max"),
        "-" * 62,
    ]
    for environment, tag, title in _worlds():
        frame = _open(still("b", environment, "payoff"))
        worst, median = v24_payoff.measured_contrast(frame, card.image)
        grey = v272.luma(np.asarray(frame).astype(float))
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
        "`band max` is the brightest pixel of v24_payoff.PAYOFF_BAND inside",
        "the text corridor: the worst thing the card could have to sit on.",
        "WCAG large text wants 3.0. V27.1 published 7.79 for V26 and 14.18 for",
        "the contained bay.",
    ]
    text = NEWLINE.join(lines)
    _write_json(os.path.join(LAB_DIR, "payoff.json"), out)
    _write_text(os.path.join(DOC_DIR, "payoff.txt"), text)
    print(text)
    return out


def stage_hook() -> dict[str, Any]:
    """Frame 0, checked rather than assumed."""
    track = _load(TRACK)
    replay = _load(REPLAY)
    reads = lab._moment_reads(track, replay, "frame0")
    out: dict[str, Any] = {"worlds": {}}
    lines = [
        "FRAME ZERO",
        "the hook, which no part of a merge correction may reach.",
        "",
        "%-6s %-22s %8s %9s %9s %8s %9s" % ("world", "title", "racers",
                                            "worst col", "mean", "plate",
                                            "least dE"),
        "-" * 78,
    ]
    for environment, tag, title in _worlds():
        image = _open(still("a", environment, "frame0"))
        hook = lab.hook_contrast(image)
        legible = v24_hook.legibility_report(image, reads)
        out["worlds"][tag] = {"environment": environment, "hook": hook,
                              "legibility": legible}
        lines.append("%-6s %-22s %5d/%d %9.2f %9.2f %8.1f %9.1f" % (
            tag, title, legible.get("legible", 0), reads["of"],
            hook["worst_column"], hook["mean_contrast"], hook["plate_luma"],
            legible.get("min_de", 0.0)))
    pairs = []
    for base, other in ((v272.GRANDPARENT, v272.PARENT),
                        (v272.PARENT, v272.PROFILE)):
        one, two = still("a", base, "frame0"), still("a", other, "frame0")
        if os.path.isfile(one) and os.path.isfile(two):
            pairs.append((base, other, _digest(one) == _digest(two)))
    for base, other, same in pairs:
        out.setdefault("identical", {})[f"{base} vs {other}"] = same
    lines.append("")
    for base, other, same in pairs:
        lines.append("%s against %s at frame 0: %s."
                     % (other, base,
                        "byte-identical" if same else "DIFFERENT"))
    lines += [
        "",
        "WCAG large text wants 3.0 of the worst column. `least dE` is the",
        "nearest any racer's colour comes to the picture under it.",
    ]
    text = NEWLINE.join(lines)
    _write_json(os.path.join(LAB_DIR, "hook.json"), out)
    _write_text(os.path.join(DOC_DIR, "hook.txt"), text)
    print(text)
    return out


# --- stage: the country probe -----------------------------------------------


def stage_country(godot: str) -> dict[str, Any]:
    """V27.1's India probe, re-run against the correction. Render-only.

    Not expanded: the same one flag, the same one racer, the same five
    moments, the same appearance behind the same `--flag-racer=` flag. The only
    question this pass asks of it is whether the merge correction changed how
    it reads, and the answer is the difference between the V27.1 column and the
    V27.2 column.
    """
    seconds = [v272.moment(key).second for key in v271.FLAG_MOMENTS]
    pairs = [(one[0], one[1]) for one in _worlds()]
    for environment, tag in pairs:
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
        "THE COUNTRY-SKIN PROBE, RE-RUN",
        "%s on marble %d, `meridian` on the other seven. Render-only, and not"
        % (v271.FLAG.title, v271.FLAG_RACER),
        "expanded: one appearance in `racer_visual.gd` behind `--flag-racer=`,",
        "no country system, no shipped render reaches it. The question here is",
        "only whether the merge correction changed how it reads.",
        "",
        "%-16s %-6s %8s %9s %11s %9s" % ("moment", "world", "px", "dE around",
                                         "bands seen", "spread"),
        "-" * 66,
    ]
    for key in v271.FLAG_MOMENTS:
        where = _winner_at(track, replay, key)
        out["moments"][key] = {"where": where, "worlds": {}}
        for _environment, tag in pairs:
            row: dict[str, Any] = {}
            path = country_still(tag, key)
            if where.get("on_screen") and os.path.isfile(path):
                pixels = _pixels(path)
                body = _patch(pixels, where["x"], where["y"], where["px"], 0.62)
                around = _patch(pixels, where["x"], where["y"], where["px"],
                                2.2, clip=True)
                if body is not None and body.size:
                    row = finish_lab._flag_read(body, around)
            out["moments"][key]["worlds"][tag] = row
            lines.append("%-16s %-6s %8s %9s %11s %9s" % (
                key, tag,
                ("%.0f" % where["px"]) if where.get("on_screen") else "-",
                ("%.1f" % row["delta_e"]) if row else "-",
                ("%d/3" % row["bands"]) if row else "-",
                ("%.0f" % row["spread"]) if row else "-"))
        lines.append("")
    lines += [
        "`bands seen` is how many of the flag's three colours are present in",
        "the marble's own patch at that size. `spread` is the patch's own luma",
        "range, which is what a turning tricolour has and a solid marble does",
        "not.",
    ]
    text = NEWLINE.join(lines)
    _write_json(os.path.join(LAB_DIR, "country.json"), out)
    _write_text(os.path.join(DOC_DIR, "country.txt"), text)
    print(text)
    return out


# --- sheets -----------------------------------------------------------------


def _label(draw: ImageDraw.ImageDraw, at: tuple[int, int], text: str,
           size: int, fill: tuple[int, int, int] = SHEET_LABEL) -> None:
    lab._label(draw, at, text, size, fill)


def _thumb(path: str, size: tuple[int, int]) -> Image.Image:
    return _open(path).resize(size, Image.LANCZOS)


def _board(rows: Sequence[tuple[str, Sequence[str]]], columns: Sequence[str],
           name: str, title: str, note: str) -> str:
    width = 300
    height = int(round(width * HEIGHT / WIDTH))
    gutter, top, left = 18, 116, 230
    sheet = Image.new("RGB",
                      (left + len(columns) * (width + gutter) + gutter,
                       top + len(rows) * (height + gutter) + gutter),
                      SHEET_BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    _label(draw, (gutter, 22), title, 30)
    _label(draw, (gutter, 62), note, 19, SHEET_DIM)
    for index, column in enumerate(columns):
        _label(draw, (left + index * (width + gutter), top - 30), column, 21)
    for order, (row_title, paths) in enumerate(rows):
        y = top + order * (height + gutter)
        _label(draw, (gutter, y + 8), row_title, 20)
        draw.line([(gutter, y - 6), (sheet.width - gutter, y - 6)],
                  fill=SHEET_RULE)
        for index, path in enumerate(paths):
            sheet.paste(_thumb(path, (width, height)),
                        (left + index * (width + gutter), y))
    os.makedirs(DOC_DIR, exist_ok=True)
    out = os.path.join(DOC_DIR, f"{name}.png")
    sheet.save(out)
    print("wrote " + out)
    return out


def stage_sheet() -> list[str]:
    """The brief's six-frame board, the merge trio, and the phone column."""
    worlds = _worlds()
    columns = [name for _e, _t, name in worlds]
    written = [
        _board([(v272.moment(key).title,
                 [still("b", env, key) for env, _t, _n in worlds])
                for key in v272.PROOF_FRAMES],
               columns, "proof",
               "THE MERGE AND THE FINISH, %d WORLDS" % len(worlds),
               "identical output seconds, one --at list. Same replay, same "
               "camera track, same edit, same seed."),
        _board([(v272.moment(key).title,
                 [still("b", env, key) for env, _t, _n in worlds])
                for key in v272.MERGE],
               columns, "merge", "THE MERGE, THREE FRAMES",
               "approach, rejoin, and the shot after it."),
        _board([(v272.moment(key).title,
                 [still("a", env, key) for env, _t, _n in worlds])
                for key in ("frame0", "obstacle", "split", "branch")],
               columns, "elsewhere", "THE GUARDED MOMENTS",
               "the hook, the obstacle and the fork: what the correction may "
               "not cost."),
    ]
    # The phone board: the brief's six at delivery size.
    width, height = PHONE
    gutter, top, left = 14, 104, 210
    rows = list(v272.PROOF_FRAMES)
    sheet = Image.new("RGB",
                      (left + len(worlds) * (width + gutter) + gutter,
                       top + len(rows) * (height + gutter) + gutter),
                      SHEET_BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    _label(draw, (gutter, 20), "THE MERGE AND THE FINISH AT %d x %d" % PHONE, 26)
    _label(draw, (gutter, 56), "the size the film is judged at", 18, SHEET_DIM)
    for index, name in enumerate(columns):
        _label(draw, (left + index * (width + gutter), top - 26), name, 17)
    for order, key in enumerate(rows):
        y = top + order * (height + gutter)
        _label(draw, (gutter, y + 6), v272.moment(key).title, 17)
        for index, (env, _t, _n) in enumerate(worlds):
            sheet.paste(_thumb(still("b", env, key), PHONE),
                        (left + index * (width + gutter), y))
    out = os.path.join(DOC_DIR, "phone.png")
    sheet.save(out)
    print("wrote " + out)
    written.append(out)
    written.append(_phone_board(
        ("fork_approach", "split", "branch"), "a", "fork_phone",
        "THE FORK AT %d x %d" % PHONE,
        "the brief's fork guard, at the size that decides. The delta's black "
        "floor is here and not at the merge - see delta.txt."))
    return written


def _phone_board(keys: Sequence[str], listing: str, name: str, title: str,
                 note: str) -> str:
    """One row per moment, one column per world, at delivery size."""
    worlds = _worlds()
    width, height = PHONE
    gutter, top, left = 14, 104, 210
    sheet = Image.new("RGB",
                      (left + len(worlds) * (width + gutter) + gutter,
                       top + len(keys) * (height + gutter) + gutter),
                      SHEET_BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    _label(draw, (gutter, 20), title, 26)
    _label(draw, (gutter, 56), note, 17, SHEET_DIM)
    for index, (_e, _t, label) in enumerate(worlds):
        _label(draw, (left + index * (width + gutter), top - 26), label, 17)
    for order, key in enumerate(keys):
        y = top + order * (height + gutter)
        _label(draw, (gutter, y + 6), v272.moment(key).title, 17)
        for index, (env, _t, _n) in enumerate(worlds):
            sheet.paste(_thumb(still(listing, env, key), PHONE),
                        (left + index * (width + gutter), y))
    out = os.path.join(DOC_DIR, f"{name}.png")
    sheet.save(out)
    print("wrote " + out)
    return out


def stage_country_sheet() -> str:
    worlds = _worlds()
    width = 300
    height = int(round(width * HEIGHT / WIDTH))
    gutter, top, left = 18, 116, 230
    rows = list(v271.FLAG_MOMENTS)
    columns = [name for _e, _t, name in worlds] + ["V27.2 at %d x %d" % PHONE]
    sheet = Image.new("RGB",
                      (left + len(worlds) * (width + gutter) + PHONE[0]
                       + 2 * gutter,
                       top + len(rows) * (height + gutter) + gutter),
                      SHEET_BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    _label(draw, (gutter, 22),
           "COUNTRY-SKIN PROBE: %s" % v271.FLAG.title.upper(), 30)
    _label(draw, (gutter, 62),
           "marble %d only; the other seven are `meridian`. Render-only, "
           "unchanged from V27.1." % v271.FLAG_RACER, 19, SHEET_DIM)
    for index, column in enumerate(columns):
        _label(draw, (left + index * (width + gutter), top - 30), column, 21)
    for order, key in enumerate(rows):
        y = top + order * (height + gutter)
        _label(draw, (gutter, y + 8), v272.moment(key).title, 20)
        draw.line([(gutter, y - 6), (sheet.width - gutter, y - 6)],
                  fill=SHEET_RULE)
        for index, (_e, tag, _n) in enumerate(worlds):
            sheet.paste(_thumb(country_still(tag, key), (width, height)),
                        (left + index * (width + gutter), y))
        sheet.paste(_thumb(country_still(worlds[-1][1], key), PHONE),
                    (left + len(worlds) * (width + gutter), y))
    os.makedirs(DOC_DIR, exist_ok=True)
    out = os.path.join(DOC_DIR, "country.png")
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
    """Branch to post-merge, in motion, in each world - and at phone size.

    Rendered as an explicit `--at` list of every frame rather than through
    `--clip`, so the clip and the stills come out of the same code path.
    """
    seconds = v272.clip_seconds()
    written: list[str] = []
    for environment, tag, _title in _worlds():
        out = os.path.join(LAB_DIR, "frames", tag, "merge")
        print(f"--- clip {tag}: {len(seconds)} frames ---")
        started = time.perf_counter()
        _render_at(godot, environment, "", seconds, out, f"clip {tag}")
        print(f"  {len(seconds)} frames in {time.perf_counter() - started:.1f} s")
        names = sorted(one for one in os.listdir(out) if one.endswith(".png"))
        listing = os.path.join(out, "frames.txt")
        with open(listing, "w", encoding="utf-8", newline="\n") as handle:
            for name in names:
                handle.write("file '%s'\n" % name.replace("'", "'\\''"))
        for size, suffix in ((None, ""), (PHONE, "_phone")):
            video = os.path.join(LAB_DIR, "clips", f"merge_{tag}{suffix}.mp4")
            os.makedirs(os.path.dirname(video), exist_ok=True)
            command = [_ffmpeg(), "-y", "-r", str(v272.FPS), "-f", "concat",
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
                raise LabError("ffmpeg failed: " + NEWLINE.join(
                    (done.stderr or "").splitlines()[-12:]))
            written.append(video)
            print("wrote " + video)
    return written


def stage_side_by_side() -> str:
    """The three worlds' merge clips stacked into one comparison file."""
    tags = [tag for _e, tag, _n in _worlds()]
    inputs = [os.path.join(LAB_DIR, "clips", f"merge_{tag}.mp4") for tag in tags]
    for path in inputs:
        if not os.path.isfile(path):
            raise LabError("run --stage clip first: " + path)
    out = os.path.join(LAB_DIR, "clips", "merge_compare.mp4")
    command = [_ffmpeg(), "-y"]
    for path in inputs:
        command += ["-i", os.path.abspath(path)]
    scale = "".join("[%d:v]scale=360:640[v%d];" % (index, index)
                    for index in range(len(inputs)))
    joins = "".join("[v%d]" % index for index in range(len(inputs)))
    command += ["-filter_complex",
                f"{scale}{joins}hstack=inputs={len(inputs)}[out]",
                "-map", "[out]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-crf", str(lab.VIDEO_CRF), "-preset", lab.VIDEO_PRESET,
                os.path.abspath(out)]
    done = subprocess.run(command, cwd=PROJECT_ROOT, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, encoding="utf-8",
                          errors="replace")
    if done.returncode != 0:
        raise LabError("ffmpeg failed: " + NEWLINE.join(
            (done.stderr or "").splitlines()[-12:]))
    print("wrote " + out)
    return out


def stage_ring() -> dict[str, Any]:
    """The WINNER mark is outside this clip's span - say so, do not fake it.

    V27.1 measured the ring off its own finish clip, 15.567 to 20.117. This
    pass's clip is the merge, 13.450 to 16.100, and the mark opens at the
    crossing at 17.517: there are no frames here to read it off. What *can* be
    checked without a second 273-frame render is that nothing this pass changed
    reaches the ring's own frames, and `--stage delta` is where that is shown:
    the winner and the payoff are in the guarded table.
    """
    _replay, _track, clock = v24.film_clock(REPLAY, TRACK)
    crossing = clock.at(v24.WINNER_CROSSES)
    start, end = v272.CLIP
    inside = crossing is not None and start <= crossing <= end
    out = {"crossing": None if crossing is None else round(crossing, 4),
           "clip": [start, end], "inside": inside,
           "measured_by": "tools/sloped_v271_finish.py --stage ring"}
    lines = [
        "THE WINNER RING",
        "the mark opens on the crossing at %s s and runs %.3f s."
        % ("-" if crossing is None else "%.3f" % crossing,
           v24_payoff.RING_SECONDS),
        "This pass's clip is %.3f to %.3f - the merge - so the mark's own"
        % (start, end),
        "frames are not in it, and no number for it is invented here.",
        "",
        "What is checked instead: the winner and the payoff are both in the",
        "regression table, V24's ring schedule is untouched, and --stage delta",
        "shows what the correction does to the frames the mark is drawn on.",
        "V27.1 measured 12 of 18 frames reading purple at a median dE of 50.1,",
        "identical to V26's 12 of 18 at 48.0.",
    ]
    text = NEWLINE.join(lines)
    _write_json(os.path.join(LAB_DIR, "ring.json"), out)
    _write_text(os.path.join(DOC_DIR, "ring.txt"), text)
    print(text)
    return out


# --- stage: cost ------------------------------------------------------------


def stage_timing(godot: str, runs: int = 4) -> dict[str, Any]:
    """Frame time, `runs` times per world, median of the engine's own figure.

    One render is not a measurement on this machine: the run-to-run spread on
    the twelve-moment list is about +-3%, which is larger than any difference a
    material value could possibly make. V27.1 took four runs per world and this
    takes the same four, so the two tables can be read together.

    The renders go to a scratch directory and are deleted: this stage is about
    the clock, and leaving eight more copies of the same twelve frames around
    would make `--stage measure` ambiguous about which it read.
    """
    out: dict[str, Any] = {"runs": runs, "worlds": {}}
    scratch = os.path.join(LAB_DIR, "timing")
    for environment, tag, title in _worlds():
        samples: list[float] = []
        for index in range(runs):
            stdout = _render_at(godot, environment, "", LISTS["a"],
                                os.path.join(scratch, tag),
                                f"timing {tag} {index + 1}/{runs}")
            cost = v27.parse_cost(stdout)
            samples.append(float(cost.milliseconds))
            print(f"  {tag} run {index + 1}: {cost.milliseconds:.0f} ms/frame")
        out["worlds"][tag] = {
            "environment": environment, "title": title, "samples": samples,
            "median": round(float(np.median(samples)), 1),
            "meshes": cost.meshes, "triangles": cost.triangles,
        }
    if os.path.isdir(scratch):
        shutil.rmtree(scratch)
    lines = [
        "FRAME TIME",
        "%d runs of the twelve-moment list per world, median of the engine's"
        % runs,
        "own per-frame figure. One run is not a measurement here: the",
        "run-to-run spread is about 3 per cent, which is larger than anything",
        "a material value can do.",
        "",
        "%-6s %-24s %-26s %9s" % ("world", "environment", "ms/frame", "median"),
        "-" * 70,
    ]
    for _environment, tag, _title in _worlds():
        row = out["worlds"][tag]
        lines.append("%-6s %-24s %-26s %9.1f" % (
            tag, row["environment"],
            " ".join("%.0f" % one for one in row["samples"]), row["median"]))
    base = out["worlds"].get("v271")
    now = out["worlds"].get("v272")
    if base and now:
        change = (now["median"] - base["median"]) / base["median"] * 100.0
        same = (base["meshes"] == now["meshes"]
                and base["triangles"] == now["triangles"])
        out["against_v271"] = {"percent": round(change, 2),
                               "identical_geometry": same}
        lines += [
            "",
            "V27.2 against V27.1: %+.2f%%." % change,
            "Mesh instances %d against %d, triangles %d against %d: %s."
            % (now["meshes"], base["meshes"], now["triangles"],
               base["triangles"],
               "identical" if same else "DIFFERENT - the delta added geometry"),
            "",
            "The delta is one reflectance field on one material. It adds no",
            "draw call, no shader variant and no vertex, so the honest",
            "expectation is zero and anything here is spread.",
        ]
    text = NEWLINE.join(lines)
    _write_json(os.path.join(LAB_DIR, "timing.json"), out)
    _write_text(os.path.join(DOC_DIR, "timing.txt"), text)
    print(text)
    return out


def stage_cost() -> dict[str, Any]:
    """Mesh, triangle and frame-time comparison, from the render stage's own
    report."""
    path = os.path.join(LAB_DIR, "cost.json")
    if not os.path.isfile(path):
        raise LabError("run --stage render first")
    report = _load(path)
    lines = [
        "COST",
        "read off the engine's own per-frame figure during --stage render.",
        "",
        "%-6s %-24s %9s %12s %11s" % ("world", "environment", "meshes",
                                      "triangles", "ms/frame"),
        "-" * 68,
    ]
    out: dict[str, Any] = {}
    for _environment, tag, _title in _worlds():
        block = report.get(tag, {})
        for listing in ("a", "b"):
            row = block.get(listing)
            if not row:
                continue
            out.setdefault(tag, {})[listing] = row
            lines.append("%-6s %-24s %9d %12d %11.0f" % (
                f"{tag}/{listing}", row["environment"], row["meshes"],
                row["triangles"], row["ms_per_frame"]))
    base = out.get("v271", {}).get("a")
    now = out.get("v272", {}).get("a")
    if base and now:
        change = (now["ms_per_frame"] - base["ms_per_frame"]) / base["ms_per_frame"]
        same = (base["meshes"] == now["meshes"]
                and base["triangles"] == now["triangles"])
        out["against_v271"] = {"ms_change": round(change * 100, 2),
                               "identical_geometry": same}
        lines += [
            "",
            "V27.2 against V27.1: %+.2f%% frame time, geometry %s."
            % (change * 100,
               "identical" if same else "DIFFERENT - the delta added meshes"),
            "",
            "A material value costs a shader nothing; a difference here that is",
            "not zero is run-to-run spread, which is about +-3% on this",
            "machine.",
        ]
    text = NEWLINE.join(lines)
    _write_json(os.path.join(LAB_DIR, "costs.json"), out)
    _write_text(os.path.join(DOC_DIR, "cost.txt"), text)
    print(text)
    return out


# --- stage: clean, export ---------------------------------------------------


def stage_clean() -> list[str]:
    stale = gen.leftovers()
    for one in stale:
        print("! " + one)
    if not stale:
        print("no V27.2 diagnostic profiles on disk or in the index")
    return stale


def stage_export() -> list[str]:
    os.makedirs(EXPORT_DIR, exist_ok=True)
    written: list[str] = []
    for name in sorted(os.listdir(DOC_DIR)) if os.path.isdir(DOC_DIR) else []:
        if name.endswith((".png", ".txt")):
            target = os.path.join(EXPORT_DIR, name)
            shutil.copy2(os.path.join(DOC_DIR, name), target)
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

STAGES = ("survey", "render", "listcheck", "isolate", "mechanism", "surfaces",
          "measure", "coverage",
          "delta", "regress", "winner", "payoff", "hook", "country", "proof",
          "sheet", "clip", "compare", "ring", "timing", "cost", "clean",
          "export", "all")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", default="all", choices=STAGES)
    parser.add_argument("--godot", default=None)
    parser.add_argument("--only", default="")
    parser.add_argument("--no-render", action="store_true",
                        help="for --stage isolate: read probes already on disk")
    args = parser.parse_args(argv)
    only = tuple(one for one in args.only.split(",") if one)

    def godot() -> str:
        return lab.find_godot(args.godot)

    stage = args.stage
    if stage in ("survey", "all"):
        stage_survey()
    if stage in ("render", "all"):
        stage_render(godot(), only)
    if stage in ("listcheck", "all"):
        stage_listcheck()
    if stage in ("isolate", "all"):
        render = not args.no_render
        stage_isolate(godot() if render else "", render=render)
    if stage in ("mechanism", "all"):
        render = not args.no_render
        stage_mechanism(godot() if render else "", render=render)
        stage_mechanism_sheet()
    if stage in ("surfaces", "all"):
        stage_surfaces()
    if stage in ("measure", "all"):
        stage_measure()
    if stage in ("coverage", "all"):
        stage_coverage()
    if stage in ("delta", "all"):
        stage_delta()
    if stage in ("regress", "all"):
        stage_regress()
    if stage in ("winner", "all"):
        stage_winner()
    if stage in ("payoff", "all"):
        stage_payoff()
    if stage in ("hook", "all"):
        stage_hook()
    if stage in ("country", "all"):
        stage_country(godot())
        stage_country_sheet()
    if stage in ("proof", "sheet", "all"):
        stage_sheet()
    if stage in ("clip", "all"):
        stage_clip(godot())
    if stage in ("compare", "all"):
        stage_side_by_side()
    if stage in ("ring", "all"):
        stage_ring()
    if stage in ("timing", "all"):
        stage_timing(godot())
    if stage in ("cost", "all"):
        stage_cost()
    stale: list[str] = []
    if stage in ("clean", "all"):
        stale = stage_clean()
    if stage in ("export", "all"):
        stage_export()
    # A leftover diagnostic in the registry is a failure of this tool, not a
    # note: the whole point of the ephemeral arrangement is that nothing
    # survives it. Exiting non-zero is what makes that checkable from a shell.
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())

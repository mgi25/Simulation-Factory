"""V22.1 beside V23, at the same frame of the same race, and what changed.

    python tools/sloped_v23_sheet.py --stage all

**The two films share a clock exactly, so here "the same moment" *is* the same
frame index.** V23 renders V22.1's own solved camera track over V22.1's own
replay to V22.1's own edit; only the world and the machine's colours differ. So
unlike the V22-against-V22.1 sheet - where the two films were 3.483 s apart at
the trapdoor and every pair had to be keyed by a replay instant - a pair here is
frame *n* of one master beside frame *n* of the other, and any difference in
what the marbles are doing would be a bug rather than an edit.

Sixteen moments: four in the course preview and twelve in the race, named for
the cut they sit in. Each pair is written full size; the contact sheet puts all
sixteen on one page; the phone sheet renders every one at 270x480, which is the
size the brief says the film is actually judged at.

The measurements are taken on the **combined** V23 frames rather than inherited
from either lab, because the two passes were measured separately and their
effects do not add: the machine got brighter in three sections and the world got
darker everywhere, and only a real frame knows what that came to.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Any, Sequence

import numpy as np
from PIL import Image, ImageDraw

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

OUT_DIR = os.path.join(PROJECT_ROOT, "output", "sloped_race_v1")
SHEET_DIR = os.path.join(OUT_DIR, "v23", "sheet")
DOCS_DIR = os.path.join(PROJECT_ROOT, "docs", "validation", "sloped_race_v1",
                        "v23_integration")

MASTERS = {
    "v221": {
        "race": os.path.join(OUT_DIR, "v221", "race_master.mp4"),
        "preview": os.path.join(OUT_DIR, "v221", "preview_master.mp4"),
    },
    "v23": {
        "race": os.path.join(OUT_DIR, "v23", "race_master.mp4"),
        "preview": os.path.join(OUT_DIR, "v23", "preview_master.mp4"),
    },
}

# One row per comparison the brief asks for. `piece` says which master the
# frame comes from and `frame` is the zero-based index into it - the same index
# in both editions, which is the whole point of this sheet.
#
# **The race master is 1340 frames, not the 1456 its cut bounds suggest.** The
# track's cuts span 0.20-24.47 s, but the edit omits 1.95 s inside that span, so
# an index cannot be derived from a cut time by arithmetic - the last frame is
# 1339 and a naive (24.47 - 0.20) * 60 asks for one that was never rendered.
# These are indices into the rendered master, checked against its own length.
MOMENTS: list[dict[str, Any]] = [
    {"key": "preview_start", "piece": "preview", "frame": 12,
     "title": "1  preview - start"},
    {"key": "preview_mid", "piece": "preview", "frame": 78,
     "title": "2  preview - mid-course"},
    {"key": "preview_fork", "piece": "preview", "frame": 132,
     "title": "3  preview - fork"},
    {"key": "preview_finish", "piece": "preview", "frame": 196,
     "title": "4  preview - finish"},
    {"key": "start_grid", "piece": "race", "frame": 24,
     "title": "5  start grid"},
    {"key": "mixer", "piece": "race", "frame": 300,
     "title": "6  mixer"},
    {"key": "release", "piece": "race", "frame": 372,
     "title": "7  release"},
    {"key": "descent", "piece": "race", "frame": 444,
     "title": "8  descent"},
    {"key": "obstacle", "piece": "race", "frame": 640,
     "title": "9  obstacle"},
    {"key": "fork_approach", "piece": "race", "frame": 876,
     "title": "10  fork approach"},
    {"key": "route_split", "piece": "race", "frame": 924,
     "title": "11  route split"},
    {"key": "branches", "piece": "race", "frame": 1008,
     "title": "12  branches"},
    {"key": "merge", "piece": "race", "frame": 1104,
     "title": "13  merge"},
    {"key": "final_approach", "piece": "race", "frame": 1170,
     "title": "14  final approach"},
    {"key": "winner", "piece": "race", "frame": 1268,
     "title": "15  winner crossing"},
    {"key": "finish", "piece": "race", "frame": 1332,
     "title": "16  finish"},
]

PHONE = (270, 480)


class SheetError(RuntimeError):
    pass


def _ffmpeg() -> str:
    import shutil
    found = shutil.which("ffmpeg")
    if found is None:
        raise SheetError("ffmpeg is not on PATH")
    return found


def grab(video: str, frame: int, out_path: str) -> None:
    """One exact frame, by index, decoded rather than seeked to.

    `select='eq(n\\,N)'` counts decoded frames, so it lands on frame N even
    though every frame here is inside a long GOP. A `-ss` seek would land on
    the nearest keyframe and the two editions would not be compared at the same
    instant, which is the one thing this sheet exists to guarantee.
    """
    if not os.path.isfile(video):
        raise SheetError(f"missing master: {video}")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    done = subprocess.run(
        [_ffmpeg(), "-y", "-i", video, "-vf", f"select='eq(n\\,{frame})'",
         "-vsync", "0", "-frames:v", "1", out_path],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if done.returncode != 0 or not os.path.isfile(out_path):
        tail = "\n".join((done.stderr or "").splitlines()[-10:])
        raise SheetError(f"ffmpeg could not grab frame {frame} of {video}\n{tail}")


# --- measurement -----------------------------------------------------------


def lstar(rgb: np.ndarray) -> np.ndarray:
    """Per-pixel L*, from 8-bit sRGB."""
    linear = rgb.astype(float) / 255.0
    linear = np.where(linear <= 0.04045, linear / 12.92,
                      ((linear + 0.055) / 1.055) ** 2.4)
    y = (linear * np.array([0.2126, 0.7152, 0.0722])).sum(axis=-1)
    return np.where(y > 0.008856, 116 * np.cbrt(y) - 16, 903.3 * y)


def measure(path: str) -> dict[str, float]:
    """What one frame is worth, in the terms the brief asks for.

    **`machine` here is a luminance split, not a segmentation.** There is no
    per-object mask in a finished MP4, so "the machine" is taken as the top
    decile of L* and "the world" as the bottom two thirds - which on this course
    is a fair proxy because the machine is the only lit object in frame and the
    world is everything behind it. It is a *relative* measure between two
    editions of the same frame, and that is all it is used for.
    """
    image = np.asarray(Image.open(path).convert("RGB"))
    values = lstar(image)
    flat = np.sort(values.reshape(-1))
    world = float(flat[: int(flat.size * 0.66)].mean())
    machine = float(flat[int(flat.size * 0.90):].mean())
    return {
        "mean": float(values.mean()),
        "world": world,
        "machine": machine,
        "headroom": machine - world,
        "p98": float(np.percentile(values, 98)),
        # "Flat white" is the V21 gate's own definition: a pixel within one
        # 8-bit step of saturation on all three channels.
        "clip_pct": float((image.min(axis=-1) >= 254).mean() * 100.0),
        "top_third_mean": float(values[: values.shape[0] // 3].mean()),
        "top_third_sd": float(values[: values.shape[0] // 3].std()),
    }


def to_lab(rgb01: np.ndarray) -> np.ndarray:
    """sRGB in [0,1] to CIE L*a*b* under D65. Shape (..., 3) either way."""
    linear = np.where(rgb01 <= 0.04045, rgb01 / 12.92,
                      ((rgb01 + 0.055) / 1.055) ** 2.4)
    matrix = np.array([[0.4124564, 0.3575761, 0.1804375],
                       [0.2126729, 0.7151522, 0.0721750],
                       [0.0193339, 0.1191920, 0.9503041]])
    xyz = linear @ matrix.T / np.array([0.95047, 1.0, 1.08883])
    delta = 6.0 / 29.0
    f = np.where(xyz > delta ** 3, np.cbrt(xyz),
                 xyz / (3 * delta ** 2) + 4.0 / 29.0)
    return np.stack([116.0 * f[..., 1] - 16.0,
                     500.0 * (f[..., 0] - f[..., 1]),
                     200.0 * (f[..., 1] - f[..., 2])], axis=-1)


def marble_separation(path: str, frame: int, replay: dict[str, Any],
                      track: dict[str, Any]) -> dict[str, float]:
    """Each racer against the course immediately behind it, in Lab.

    **The marbles are found by projection, not by looking for them.** An
    earlier draft of this tool took the top saturation percentile as "the
    racers", and on a V23 frame that finds the machine's own zone lights - the
    orange fork and the violet mixer are more saturated than a marble - so it
    reported the separation as having halved when the projected measure says it
    improved. The replay and the camera track already know exactly where every
    racer is on every frame; there is no reason to guess.

    Borrowed unchanged from the V23 machine lab so the two are comparable: a
    disc at 0.85 of the projected radius, which keeps the antialiased rim and
    the contact shadow out of the mean, against a ring of whatever is behind
    it. Frame index to output second is n / 60 - the renderer's clock is the
    output frame index, which is why a still can be trusted to match a clip.
    """
    discs = _machine_lab().marble_discs(replay, track, frame / 60.0)
    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=float) / 255.0
    flat = to_lab(rgb).reshape(-1, 3)
    deltas: list[float] = []
    steps: list[float] = []
    for disc in discs:
        if disc["ring"].size < 24:
            continue
        ball = flat[disc["disc"]].mean(axis=0)
        around = flat[disc["ring"]].mean(axis=0)
        deltas.append(float(np.linalg.norm(ball - around)))
        steps.append(abs(float(ball[0] - around[0])))
    if not deltas:
        return {"marble_dE": float("nan"), "marble_dL": float("nan"),
                "marbles": 0.0}
    return {"marble_dE": float(np.median(deltas)),
            "marble_dL": float(np.median(steps)),
            "marbles": float(len(deltas))}


_MACHINE_LAB = None


def _machine_lab():
    """The V23 machine lab's projection helpers, loaded by path."""
    global _MACHINE_LAB
    if _MACHINE_LAB is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_v23_machine_lab",
            os.path.join(PROJECT_ROOT, "tools", "sloped_v23_machine.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _MACHINE_LAB = module
    return _MACHINE_LAB


def _load_geometry() -> tuple[dict[str, Any], dict[str, Any]]:
    with open(os.path.join(OUT_DIR, "race_5432.json"), encoding="utf-8") as handle:
        replay = json.load(handle)
    with open(os.path.join(OUT_DIR, "cameras_v221_5432.json"),
              encoding="utf-8") as handle:
        track = json.load(handle)
    return replay, track


# --- sheets ----------------------------------------------------------------


def _label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str) -> None:
    x, y = xy
    draw.rectangle([x - 4, y - 4, x + 7 * len(text) + 6, y + 16], fill=(0, 0, 0))
    draw.text((x, y), text, fill=(255, 255, 255))


def pair_sheet(key: str, title: str, left: str, right: str, out_path: str,
               scale: float = 0.5) -> None:
    a, b = Image.open(left).convert("RGB"), Image.open(right).convert("RGB")
    size = (int(a.width * scale), int(a.height * scale))
    a, b = a.resize(size), b.resize(size)
    sheet = Image.new("RGB", (size[0] * 2 + 24, size[1] + 44), (17, 17, 20))
    sheet.paste(a, (8, 36))
    sheet.paste(b, (size[0] + 16, 36))
    draw = ImageDraw.Draw(sheet)
    _label(draw, (10, 10), title)
    _label(draw, (12, 42), "V22.1")
    _label(draw, (size[0] + 20, 42), "V23")
    sheet.save(out_path)


def contact_sheet(rows: list[dict[str, Any]], out_path: str,
                  cell: tuple[int, int] = (150, 267)) -> None:
    columns = 4
    lines = (len(rows) + columns - 1) // columns
    width = columns * (cell[0] * 2 + 14) + 10
    height = lines * (cell[1] + 26) + 10
    sheet = Image.new("RGB", (width, height), (17, 17, 20))
    draw = ImageDraw.Draw(sheet)
    for index, row in enumerate(rows):
        column, line = index % columns, index // columns
        x = 10 + column * (cell[0] * 2 + 14)
        y = 10 + line * (cell[1] + 26)
        for offset, side in ((0, "v221"), (cell[0] + 4, "v23")):
            image = Image.open(row[side]).convert("RGB").resize(cell)
            sheet.paste(image, (x + offset, y + 20))
        _label(draw, (x, y), row["title"][:26])
    sheet.save(out_path)


def phone_sheet(rows: list[dict[str, Any]], out_path: str) -> None:
    """Every pair at 270x480 - the size the film is actually watched at."""
    columns = 4
    lines = (len(rows) + columns - 1) // columns
    width = columns * (PHONE[0] * 2 + 16) + 10
    height = lines * (PHONE[1] + 28) + 10
    sheet = Image.new("RGB", (width, height), (17, 17, 20))
    draw = ImageDraw.Draw(sheet)
    for index, row in enumerate(rows):
        column, line = index % columns, index // columns
        x = 10 + column * (PHONE[0] * 2 + 16)
        y = 10 + line * (PHONE[1] + 28)
        for offset, side in ((0, "v221"), (PHONE[0] + 6, "v23")):
            image = Image.open(row[side]).convert("RGB").resize(PHONE)
            sheet.paste(image, (x + offset, y + 22))
        _label(draw, (x, y), row["title"][:30])
    sheet.save(out_path)


# --- stages ----------------------------------------------------------------


def stage_grab() -> list[dict[str, Any]]:
    os.makedirs(SHEET_DIR, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for moment in MOMENTS:
        row = dict(moment)
        for edition in ("v221", "v23"):
            path = os.path.join(SHEET_DIR, f"{moment['key']}_{edition}.png")
            grab(MASTERS[edition][moment["piece"]], moment["frame"], path)
            row[edition] = path
        rows.append(row)
        print(f"  {moment['title']}: frame {moment['frame']} of {moment['piece']}")
    return rows


def stage_measure(rows: list[dict[str, Any]]) -> dict[str, Any]:
    replay, track = _load_geometry()
    table: dict[str, Any] = {"moments": {}}
    for row in rows:
        entry: dict[str, Any] = {}
        for edition in ("v221", "v23"):
            entry[edition] = measure(row[edition])
            if row["piece"] == "race":
                # Only the race master shares the replay's clock; the course
                # preview is its own footage over a frozen field, and the
                # racers in it are not where the replay says they are.
                entry[edition].update(
                    marble_separation(row[edition], row["frame"], replay, track))
        entry["title"] = row["title"]
        table["moments"][row["key"]] = entry
    # The roll-up, which is what the report quotes.
    summary: dict[str, Any] = {}
    for edition in ("v221", "v23"):
        for field in ("world", "machine", "headroom", "clip_pct", "mean",
                      "marble_dE", "marble_dL", "top_third_sd"):
            values = [table["moments"][k][edition][field]
                      for k in table["moments"]
                      if field in table["moments"][k][edition]
                      and not np.isnan(table["moments"][k][edition][field])]
            if not values:
                continue
            summary[f"{edition}_{field}_median"] = float(np.median(values))
            summary[f"{edition}_{field}_mean"] = float(np.mean(values))
            if field == "clip_pct":
                summary[f"{edition}_clip_worst"] = float(np.max(values))
    table["summary"] = summary
    return table


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stage", default="all",
                        choices=("grab", "sheets", "measure", "all"))
    args = parser.parse_args(argv)

    os.makedirs(SHEET_DIR, exist_ok=True)
    os.makedirs(DOCS_DIR, exist_ok=True)

    print("--- grab ---")
    rows = stage_grab()

    if args.stage in ("sheets", "all"):
        print("--- sheets ---")
        for row in rows:
            out = os.path.join(DOCS_DIR, f"pair_{row['key']}.png")
            pair_sheet(row["key"], row["title"], row["v221"], row["v23"], out)
        contact_sheet(rows, os.path.join(DOCS_DIR, "contact_sheet.png"))
        phone_sheet(rows, os.path.join(DOCS_DIR, "phone_sheet.png"))
        print(f"  -> {DOCS_DIR}")

    if args.stage in ("measure", "all"):
        print("--- measure ---")
        table = stage_measure(rows)
        path = os.path.join(DOCS_DIR, "measures.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(table, handle, indent=2)
        summary = table["summary"]
        print(f"  world  L*  {summary['v221_world_mean']:6.2f} -> "
              f"{summary['v23_world_mean']:6.2f}")
        print(f"  machine L* {summary['v221_machine_mean']:6.2f} -> "
              f"{summary['v23_machine_mean']:6.2f}")
        print(f"  headroom   {summary['v221_headroom_mean']:6.2f} -> "
              f"{summary['v23_headroom_mean']:6.2f}")
        print(f"  marble dE  {summary['v221_marble_dE_median']:6.2f} -> "
              f"{summary['v23_marble_dE_median']:6.2f}  (median, race only)")
        print(f"  marble dL  {summary['v221_marble_dL_median']:6.2f} -> "
              f"{summary['v23_marble_dL_median']:6.2f}")
        print(f"  clip worst {summary['v221_clip_worst']:6.3f}% -> "
              f"{summary['v23_clip_worst']:6.3f}%")
        print(f"  -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

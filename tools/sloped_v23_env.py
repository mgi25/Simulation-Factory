"""Render, compare and measure the V23 environment directions.

    python tools/sloped_v23_env.py --stage render  --godot PATH
    python tools/sloped_v23_env.py --stage sheet
    python tools/sloped_v23_env.py --stage phone
    python tools/sloped_v23_env.py --stage measure
    python tools/sloped_v23_env.py --stage clip    --godot PATH
    python tools/sloped_v23_env.py --stage all     --godot PATH

The lab in one file. It renders the same eleven frames of the same locked
V22.1 race under four environments - the production baseline and the three
directions - builds the sheets a person compares them on, and prints the table
that keeps the comparison honest.

## What it does not do

It does not solve a camera, freeze a replay or run a physics step. Both V22.1
camera tracks and the frozen preview replay are `tools/sloped_v22.py`'s, and
this tool requires them to exist:

    python tools/sloped_v22.py --edition v221 --stage solve
    python tools/sloped_v22.py --edition v221 --stage freeze

If they are missing it says so and stops, rather than solving its own and
quietly comparing four directions against a camera track production never
shipped.

## Why every direction is rendered by the same command

`_render` builds one flag list and changes exactly one entry of it per
direction: `--env=`. The out-dir changes with it and nothing else does - not
the width, not the detail level, not the routes, not the start contract, not
`--finish-sign=double`. A comparison sheet whose cells were rendered by two
slightly different commands is worth nothing, and the cheapest way to be sure
is to have one command.
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

from sloped import presentation, v23_env

PROJECT_ROOT = os.getcwd()
GODOT_PROJECT = os.path.join(PROJECT_ROOT, "godot")
RENDER_SCENE = "res://scenes/V23EnvRender.tscn"

SEED = 5432
WIDTH, HEIGHT, FPS = 1080, 1920, 60
VIDEO_CRF = 18
VIDEO_PRESET = "medium"

OUT_DIR = os.path.join("output", "sloped_race_v1")
LAB_DIR = os.path.join(OUT_DIR, "v23")
DOCS_DIR = os.path.join("docs", "validation", "sloped_race_v1", "v23_environment")

REPLAY = os.path.join(OUT_DIR, f"race_{SEED}.json")
START_CONTRACT = os.path.join(OUT_DIR, f"start_contract_{SEED}.json")
RACE_TRACK = os.path.join(OUT_DIR, f"cameras_v221_{SEED}.json")
PREVIEW_TRACK = os.path.join(OUT_DIR, f"preview_v221_{SEED}.json")
FROZEN = os.path.join(OUT_DIR, "v221", f"frozen_{SEED}.json")

# The sheet's furniture. Deliberately plain and dark, so a cell is judged on
# what is in it rather than against the paper it is printed on: a light sheet
# behind a dark direction flatters the light one, which is exactly the bias
# this pass is trying to remove from the argument.
SHEET_BACKGROUND = (14, 14, 17)
SHEET_LABEL = (238, 238, 234)
SHEET_DIM = (146, 150, 160)
SHEET_RULE = (44, 46, 54)


class LabError(RuntimeError):
    pass


# --- inputs -----------------------------------------------------------------


def _require_inputs() -> None:
    missing = [
        path for path in (REPLAY, START_CONTRACT, RACE_TRACK, PREVIEW_TRACK, FROZEN)
        if not os.path.isfile(path)
    ]
    if not missing:
        return
    raise LabError(
        "the lab needs the locked replay and the two solved V22.1 tracks:\n"
        + "\n".join(f"  missing {path}" for path in missing)
        + "\n  the replay is generated output and not in the branch; copy it from"
          "\n  a tree that has it. The tracks and the frozen preview replay come"
          "\n  from:\n"
          "    python tools/sloped_v22.py --edition v221 --stage solve\n"
          "    python tools/sloped_v22.py --edition v221 --stage freeze"
    )


def _track_path(track: str) -> str:
    return RACE_TRACK if track == "race" else PREVIEW_TRACK


def _replay_path(track: str) -> str:
    return REPLAY if track == "race" else FROZEN


def _load(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def stills_dir(key: str, track: str) -> str:
    return os.path.join(LAB_DIR, key or "baseline", track)


def frames_dir(key: str, clip: str) -> str:
    return os.path.join(LAB_DIR, key or "baseline", f"clip_{clip}")


def video_path(key: str, clip: str) -> str:
    return os.path.join(LAB_DIR, "clips", f"{clip}_{key or 'baseline'}.mp4")


def frame_path(key: str, moment: v23_env.Moment) -> str:
    return os.path.join(stills_dir(key, moment.track), f"at_{moment.second:07.3f}.png")


# --- Godot ------------------------------------------------------------------


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
        "cannot find Godot 4. Pass --godot PATH, set $GODOT_BIN, or put it on PATH."
    )


def _scene_flags(track: str, env: str) -> list[str]:
    """The one flag list. See the module docstring for why there is only one."""
    flags = [
        f"--replay={os.path.abspath(_replay_path(track))}",
        f"--cameras={os.path.abspath(_track_path(track))}",
        f"--start-contract={os.path.abspath(START_CONTRACT)}",
        f"--width={WIDTH}",
        f"--height={HEIGHT}",
        "--layout=b",
        "--detail=hero",
        "--routes=both",
        # V22.1's own render flag. The finish parks up-course of the line, and
        # without this the payoff frame is the back of a blank board - in every
        # direction equally, which would be a fair comparison of the wrong
        # picture.
        "--finish-sign=double",
    ]
    if env:
        flags.append(f"--env={env}")
    return flags


def run_godot(godot: str, extra: Sequence[str], label: str) -> float:
    started = time.perf_counter()
    completed = subprocess.run(
        [godot, "--path", GODOT_PROJECT, RENDER_SCENE, "--", *extra],
        cwd=PROJECT_ROOT, stderr=subprocess.PIPE, stdout=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
    )
    elapsed = time.perf_counter() - started
    errors = "\n".join((completed.stderr or "").splitlines()[-30:])
    if completed.returncode != 0:
        raise LabError(f"{label}: Godot exited {completed.returncode}\n{errors}")
    for line in (completed.stderr or "").splitlines():
        if "SCRIPT ERROR" in line or "Parse Error" in line:
            raise LabError(f"{label}: Godot reported an error: {line.strip()}")
    for line in (completed.stdout or "").splitlines():
        if line.startswith("env:") or line.startswith("    "):
            print(f"  {line.rstrip()}")
    if errors.strip():
        print(f"  godot stderr tail:\n{errors}")
    return elapsed


# --- stages -----------------------------------------------------------------


def stage_render(godot: str, only: Sequence[str] = ()) -> dict[str, int]:
    """The eleven comparison frames, per direction, from both tracks."""
    _require_inputs()
    counts: dict[str, int] = {}
    for entry in v23_env.ALL:
        if only and entry.key not in only:
            continue
        for track in ("preview", "race"):
            seconds = v23_env.seconds_for(track)
            out = stills_dir(entry.key, track)
            if os.path.isdir(out):
                shutil.rmtree(out)
            os.makedirs(out, exist_ok=True)
            label = f"{entry.title} / {track}"
            print(f"--- {label} ---")
            elapsed = run_godot(godot, [
                f"--out-dir={os.path.abspath(out)}",
                "--at=" + ",".join(f"{when:.3f}" for when in seconds),
                *_scene_flags(track, entry.key),
            ], label)
            written = sorted(one for one in os.listdir(out) if one.endswith(".png"))
            if len(written) != len(seconds):
                raise LabError(
                    f"{label}: asked for {len(seconds)} frames, got {len(written)}"
                )
            counts[f"{entry.key or 'baseline'}/{track}"] = len(written)
            print(f"  {len(written)} frames in {elapsed:.1f} s")
    return counts


def stage_clip(godot: str, only: Sequence[str] = (),
               which: Sequence[str] = ()) -> list[str]:
    """Short moving proofs, one span per direction."""
    _require_inputs()
    os.makedirs(os.path.join(LAB_DIR, "clips"), exist_ok=True)
    made: list[str] = []
    for clip in v23_env.CLIPS:
        if which and clip.key not in which:
            continue
        for entry in v23_env.ALL:
            if only and entry.key not in only:
                continue
            out = frames_dir(entry.key, clip.key)
            if os.path.isdir(out):
                shutil.rmtree(out)
            os.makedirs(out, exist_ok=True)
            label = f"{entry.title} / {clip.key}"
            print(f"--- {label} ---")
            elapsed = run_godot(godot, [
                f"--out-dir={os.path.abspath(out)}",
                "--clip=1",
                f"--start={clip.start:.6f}",
                f"--end={clip.end:.6f}",
                f"--fps={FPS}",
                *_scene_flags(clip.track, entry.key),
            ], label)
            names = sorted(one for one in os.listdir(out) if one.endswith(".png"))
            if not names:
                raise LabError(f"{label}: no frames were written")
            print(f"  {len(names)} frames in {elapsed:.1f} s")
            path = video_path(entry.key, clip.key)
            _encode(out, names, path)
            made.append(path)
            # The frames are the expensive half and the video is the artefact.
            # A full set of four directions times two clips is about nine
            # thousand PNGs at one and a half megabytes each; keeping them
            # would fill a disk to hold something ffmpeg has already read.
            shutil.rmtree(out)
    return made


def _encode(directory: str, names: Sequence[str], video: str) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise LabError("ffmpeg is not on PATH; frames are rendered but not encoded")
    first = int(names[0].split("_")[1].split(".")[0])
    os.makedirs(os.path.dirname(os.path.abspath(video)), exist_ok=True)
    done = subprocess.run(
        [ffmpeg, "-y", "-framerate", str(FPS), "-start_number", str(first),
         "-i", os.path.join(directory, "frame_%06d.png"),
         "-frames:v", str(len(names)), "-an",
         "-c:v", "libx264", "-preset", VIDEO_PRESET, "-crf", str(VIDEO_CRF),
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", video],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if done.returncode != 0:
        tail = "\n".join((done.stderr or "").splitlines()[-15:])
        raise LabError(f"ffmpeg exited {done.returncode}\n{tail}")
    print(f"  video: {video}  {os.path.getsize(video) / (1024 * 1024):.1f} MiB")


# --- the sheets -------------------------------------------------------------


def _font(size: int):
    from PIL import ImageFont
    for name in ("DejaVuSans.ttf", "arial.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _cell(path: str, width: int) -> Image.Image:
    image = Image.open(path).convert("RGB")
    height = int(round(width * image.height / image.width))
    return image.resize((width, height), Image.LANCZOS)


def stage_sheet(cell_width: int = 268) -> list[str]:
    """One sheet per moment: the four directions side by side, labelled.

    A sheet per *moment* rather than one per direction, because the question
    the lab is asked is "which of these four is the best fork frame", and a
    sheet that puts four forks in a row answers it while a sheet that puts
    eleven aurora frames in a grid does not.
    """
    os.makedirs(DOCS_DIR, exist_ok=True)
    title_font = _font(22)
    body_font = _font(15)
    small_font = _font(13)
    written: list[str] = []
    for moment in v23_env.MOMENTS:
        cells = []
        for entry in v23_env.ALL:
            path = frame_path(entry.key, moment)
            if not os.path.isfile(path):
                raise LabError(f"render first: {path} is missing")
            cells.append((entry, _cell(path, cell_width)))
        cell_height = cells[0][1].height
        head = 64
        foot = 46
        sheet = Image.new(
            "RGB",
            (cell_width * len(cells), head + cell_height + foot),
            SHEET_BACKGROUND,
        )
        draw = ImageDraw.Draw(sheet)
        draw.text((14, 12), moment.title, font=title_font, fill=SHEET_LABEL)
        draw.text((14, 40), moment.why, font=small_font, fill=SHEET_DIM)
        for index, (entry, image) in enumerate(cells):
            x = index * cell_width
            sheet.paste(image, (x, head))
            if index:
                draw.line([(x, head), (x, head + cell_height)], fill=SHEET_RULE)
            draw.text((x + 10, head + cell_height + 8), entry.title,
                      font=body_font, fill=SHEET_LABEL)
            draw.text((x + 10, head + cell_height + 26),
                      f"{moment.track} {moment.second:.2f} s",
                      font=small_font, fill=SHEET_DIM)
        path = os.path.join(DOCS_DIR, f"sheet_{moment.key}.png")
        sheet.save(path)
        written.append(path)
        print(f"sheet: {path}")
    return written


def stage_contact(cell_width: int = 150) -> str:
    """Every moment against every direction, on one page.

    The sheet that gets looked at first and decides which of the eleven
    per-moment sheets is worth opening. Directions down the page, moments
    across it, so a direction reads as a row and can be judged for consistency
    - which is a thing the per-moment sheets cannot show and is most of what
    separates a colour direction from a lucky frame.
    """
    os.makedirs(DOCS_DIR, exist_ok=True)
    title_font = _font(26)
    body_font = _font(15)
    small_font = _font(12)
    gutter = 128
    head = 76
    sample = _cell(frame_path("", v23_env.MOMENTS[0]), cell_width)
    cell_height = sample.height
    width = gutter + cell_width * len(v23_env.MOMENTS)
    height = head + (cell_height + 22) * len(v23_env.ALL)
    sheet = Image.new("RGB", (width, height), SHEET_BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    draw.text((16, 14), "V23 environment directions - the same V22.1 race",
              font=title_font, fill=SHEET_LABEL)
    draw.text((16, 46),
              "seed 5432, the solved V22.1 preview and race tracks, one flag "
              "changed per row", font=small_font, fill=SHEET_DIM)
    for column, moment in enumerate(v23_env.MOMENTS):
        draw.text((gutter + column * cell_width + 4, head - 16),
                  moment.key.replace("_", " "), font=small_font, fill=SHEET_DIM)
    for row, entry in enumerate(v23_env.ALL):
        y = head + row * (cell_height + 22)
        draw.text((10, y + 6), entry.title, font=body_font, fill=SHEET_LABEL)
        for column, moment in enumerate(v23_env.MOMENTS):
            path = frame_path(entry.key, moment)
            if not os.path.isfile(path):
                raise LabError(f"render first: {path} is missing")
            sheet.paste(_cell(path, cell_width),
                        (gutter + column * cell_width, y))
    path = os.path.join(DOCS_DIR, "contact_sheet.png")
    sheet.save(path)
    print(f"contact sheet: {path}")
    return path


def stage_phone(cell_width: int = 206) -> str:
    """The review that decides it: four directions at the size they ship at.

    1080x1920 judged on a desktop at a third of its height is not the delivery
    condition, and this course has been wrong about that before - the V21 pass
    exists because a track that looked moulded on a monitor was a white ribbon
    on a phone. So this sheet is built at 1170 px wide, which is an iPhone's
    own pixel width, and each cell is a real crop rather than a downscale of
    the whole frame: the centre 46% of the height at full resolution, which is
    the band the machine occupies in every one of the eleven moments.

    Four moments rather than eleven, chosen because each is a different kind of
    readability problem: the grid is the smallest the marbles ever are, the
    fork is where two routes have to be told apart, the branches are the frame
    with the most open air in it, and the finish is the payoff.
    """
    os.makedirs(DOCS_DIR, exist_ok=True)
    picks = ("start_grid", "fork", "branches", "finish")
    title_font = _font(26)
    body_font = _font(18)
    small_font = _font(14)
    page_width = 1170
    columns = len(v23_env.ALL)
    cell_width = page_width // columns
    crop_fraction = 0.46
    rows = []
    for key in picks:
        moment = v23_env.moment(key)
        strip = []
        for entry in v23_env.ALL:
            path = frame_path(entry.key, moment)
            if not os.path.isfile(path):
                raise LabError(f"render first: {path} is missing")
            image = Image.open(path).convert("RGB")
            band = int(image.height * crop_fraction)
            top = (image.height - band) // 2
            crop = image.crop((0, top, image.width, top + band))
            height = int(round(cell_width * crop.height / crop.width))
            strip.append(crop.resize((cell_width, height), Image.LANCZOS))
        rows.append((moment, strip))
    row_height = rows[0][1][0].height
    head = 84
    label = 40
    sheet = Image.new(
        "RGB", (page_width, head + (row_height + label + 26) * len(rows)),
        SHEET_BACKGROUND,
    )
    draw = ImageDraw.Draw(sheet)
    draw.text((16, 16), "V23 directions at phone width", font=title_font,
              fill=SHEET_LABEL)
    draw.text((16, 50),
              "1170 px wide; the centre 46% of each 1080x1920 frame at full "
              "resolution", font=small_font, fill=SHEET_DIM)
    for index, entry in enumerate(v23_env.ALL):
        draw.text((index * cell_width + 8, head - 20),
                  entry.title, font=small_font, fill=SHEET_DIM)
    for row, (moment, strip) in enumerate(rows):
        y = head + row * (row_height + label + 26)
        for column, image in enumerate(strip):
            sheet.paste(image, (column * cell_width, y))
            if column:
                draw.line([(column * cell_width, y),
                           (column * cell_width, y + row_height)],
                          fill=SHEET_RULE)
        draw.text((10, y + row_height + 8), moment.title, font=body_font,
                  fill=SHEET_LABEL)
    path = os.path.join(DOCS_DIR, "phone_sheet.png")
    sheet.save(path)
    print(f"phone sheet: {path}  {sheet.width}x{sheet.height}")
    return path


# --- the table --------------------------------------------------------------


def stage_measure(write: bool = True) -> dict[str, Any]:
    """The five measures, per direction, averaged over the eleven moments.

    Separation is measured only on the race moments. The preview is rendered
    from a *frozen* replay - every frame identical, the field parked on the
    start line - so its marbles are a hundred and eighty units from the lens in
    every preview frame and their disc is under two pixels. Measuring them
    would report a number that is about the preview's framing rather than about
    the environment, in all four directions equally.
    """
    rows: dict[str, Any] = {}
    tracks = {name: _load(_track_path(name)) for name in ("race", "preview")}
    replay = _load(REPLAY)
    for entry in v23_env.ALL:
        per_moment = []
        separations: list[float] = []
        chroma: list[float] = []
        for moment in v23_env.MOMENTS:
            path = frame_path(entry.key, moment)
            if not os.path.isfile(path):
                raise LabError(f"render first: {path} is missing")
            pixels = np.asarray(Image.open(path).convert("RGB"))
            measures = v23_env.frame_measures(pixels)
            measures["moment"] = moment.key
            per_moment.append(measures)
            if moment.track != "race":
                continue
            when = v23_env.output_to_replay(tracks["race"], moment.second)
            places = v23_env.places_at(
                replay, tracks["race"], when, presentation.project,
                presentation._camera_at, WIDTH, HEIGHT,
            )
            for whole, only_chroma in v23_env.separation(pixels, places):
                separations.append(whole)
                chroma.append(only_chroma)
        rows[entry.key or "baseline"] = {
            "title": entry.title,
            "moments": per_moment,
            "headroom": sum(one["headroom"] for one in per_moment) / len(per_moment),
            "backdrop": sum(one["backdrop"] for one in per_moment) / len(per_moment),
            "spread": sum(one["spread"] for one in per_moment) / len(per_moment),
            "planes": sum(one["planes"] for one in per_moment) / len(per_moment),
            "walls": sum(1 for one in per_moment if one["planes"] <= 1),
            "warmth": sum(one["warmth"] for one in per_moment) / len(per_moment),
            "mean": sum(one["mean"] for one in per_moment) / len(per_moment),
            "flat_white": max(one["flat_white"] for one in per_moment),
            "near_clip": max(one["near_clip"] for one in per_moment),
            "separation": v23_env.median(separations),
            "chroma": v23_env.median(chroma),
            "racers": len(separations),
        }

    print()
    print(f"{'direction':<20} {'headroom':>9} {'backdrop':>9} {'warm b*':>8} "
          f"{'mean L*':>8} {'dE':>6} {'dE C':>6} {'clip %':>7} {'walls':>6}")
    print("-" * 90)
    for key, row in rows.items():
        print(f"{row['title']:<20} {row['headroom']:>9.1f} {row['backdrop']:>9.1f} "
              f"{row['warmth']:>8.1f} {row['mean']:>8.1f} "
              f"{row['separation']:>6.1f} {row['chroma']:>6.1f} "
              f"{row['flat_white']:>7.3f} {row['walls']:>4d}/11")
    print()
    print("headroom  subject L* (98th pct) minus backdrop L* (top quarter mean);")
    print("          positive means the machine is brighter than what is behind it")
    print("warm b*   mean CIELAB b* of the backdrop; positive is tan, negative blue")
    print("dE        median marble-against-course separation over the race moments")
    print("clip %    worst frame's share of pixels flat at the top of the range")
    print("walls     moments whose backdrop is a featureless wall. NOTE: there is")
    print("          no layering number here - three were tried and all three")
    print("          measured brightness under another name. See v23_env.plateaus.")

    if write:
        os.makedirs(DOCS_DIR, exist_ok=True)
        path = os.path.join(DOCS_DIR, "measures.json")
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(rows, handle, indent=1, sort_keys=True)
            handle.write("\n")
        print(f"\nmeasures: {path}")
    return rows


# --- entry point ------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stage", default="all",
                        choices=("render", "sheet", "contact", "phone",
                                 "measure", "clip", "all"))
    parser.add_argument("--godot", default=None)
    parser.add_argument("--only", default="",
                        help="comma-separated direction keys; "
                             "empty is all four, 'baseline' is the unskinned one")
    parser.add_argument("--clips", default="",
                        help="comma-separated clip keys; empty is all")
    args = parser.parse_args(argv)

    only = tuple(
        "" if one.strip() == "baseline" else one.strip()
        for one in args.only.split(",") if one.strip()
    )
    clips = tuple(one.strip() for one in args.clips.split(",") if one.strip())
    stages = (("render", "sheet", "contact", "phone", "measure")
              if args.stage == "all" else (args.stage,))
    godot = None
    try:
        for stage in stages:
            print(f"=== {stage} ===")
            if stage == "render":
                godot = godot or find_godot(args.godot)
                stage_render(godot, only)
            elif stage == "clip":
                godot = godot or find_godot(args.godot)
                stage_clip(godot, only, clips)
            elif stage == "sheet":
                stage_sheet()
            elif stage == "contact":
                stage_contact()
            elif stage == "phone":
                stage_phone()
            elif stage == "measure":
                stage_measure()
    except LabError as error:
        print(f"\nFAILED: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

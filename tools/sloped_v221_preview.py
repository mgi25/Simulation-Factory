"""Solve, render and compare the three V22.1 course-preview candidates.

    python tools/sloped_v221_preview.py solve
    python tools/sloped_v221_preview.py stills --godot PATH
    python tools/sloped_v221_preview.py clip   --godot PATH
    python tools/sloped_v221_preview.py qc
    python tools/sloped_v221_preview.py sheet
    python tools/sloped_v221_preview.py all    --godot PATH

`solve` needs nothing but Python and is the whole argument: it builds
`preview_28`, `preview_32` and `preview_35`, measures each against
`sloped.v221_preview.check_v221`, and prints the three side by side. The other
stages render them.

## What it borrows

The renderer, the scene, the frozen replay and the Godot invocation are
`tools/sloped_course_preview.py`'s, imported rather than copied, so the three
candidates are photographed by the same shipped `SlopedRaceRender.tscn` driving
the same `sloped_race_scene.gd` with the same V21 readability pass in frame that
the race itself ships with. Nothing in `sloped/` that V22 renders through is
touched: the only new module is `sloped/v221_preview.py`, and the only new file
in the render is a camera track.

## Why every proof is at phone size

The defect this pass exists to fix was found by a person watching the film on a
phone, and the question is whether a *new* viewer can tell what the course
contains before the race starts. A 1080-wide still flatters a flyover: the fork
is legible at 1080 and a smudge at 270. Both sheets are written - `sheet`
renders the landmark grid at 270x480 and `compare` puts the three candidates
side by side at the same landmark - and the phone sheet is the one that decides.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from typing import Any, Sequence

sys.path.insert(0, os.getcwd())

from sloped import course_preview as cp
from sloped import sightlines, terrain, v22
from sloped import v221_preview as v221
from sloped.course import sloped_course

from tools.sloped_course_preview import PreviewError, find_godot, run_godot

PROJECT_ROOT = os.getcwd()

SEED = 5432
OUT_DIR = os.path.join("output", "sloped_race_v1")
V221_DIR = os.path.join(OUT_DIR, "v221")
DOCS_DIR = os.path.join("docs", "validation", "sloped_race_v1", "v221_preview")

RACE_REPLAY = os.path.join(OUT_DIR, f"race_{SEED}.json")
RACE_TRACK = os.path.join(OUT_DIR, f"cameras_v22_{SEED}.json")
START_CONTRACT = os.path.join(OUT_DIR, f"start_contract_{SEED}.json")

WIDTH, HEIGHT = 1080, 1920
FPS = 60
VIDEO_CRF = 16
VIDEO_PRESET = "slow"

# The order the sheets read in, which is the order the preview travels.
SHEET_ORDER = (
    "finish", "merge", "branches", "fork", "obstacle", "turns", "mixer", "start",
)

PHONE = (270, 480)
GUTTER = 10
LABEL = 40
BACKGROUND = (17, 19, 24)
TEXT = (226, 232, 240)
DIM = (120, 132, 148)
GOOD = (126, 217, 154)
BAD = (240, 138, 122)


def candidate_dir(name: str) -> str:
    return os.path.join(V221_DIR, name)


def track_path(name: str) -> str:
    return os.path.join(candidate_dir(name), "cameras.json")


def replay_path(name: str) -> str:
    return os.path.join(candidate_dir(name), "replay.json")


def report_path(name: str) -> str:
    return os.path.join(candidate_dir(name), "report.json")


def stills_dir(name: str) -> str:
    return os.path.join(candidate_dir(name), "stills")


def frames_dir(name: str) -> str:
    return os.path.join(candidate_dir(name), "frames")


def video_path(name: str) -> str:
    return os.path.join(OUT_DIR, f"{name}_v221.mp4")


# --- solving --------------------------------------------------------------


def load_rail() -> v221.Rail:
    """The V22 race camera's own first cut, which the preview hands over to."""
    if not os.path.isfile(RACE_TRACK):
        raise PreviewError(
            f"the V22 race camera track is missing: {RACE_TRACK}\n"
            "  it is generated output and not in the branch; copy it from a tree "
            "that has it, or rebuild it with tools/sloped_v22.py."
        )
    with open(RACE_TRACK, "r", encoding="utf-8") as handle:
        track = json.load(handle)
    return v221.Rail(track["cuts"][0]["frames"])


def stage_solve(with_solids: bool = True) -> dict[str, Any]:
    """Build all three candidates, measure them and write their tracks."""
    rail = load_rail()
    line = cp.course_line()
    spine = cp.corridor(line)
    cfg = terrain.terrain_config()
    spec = v221.preview_spec(v22.PREVIEW)

    bundle = None
    if with_solids:
        machine = sloped_course(routes="both")
        bundle = sightlines.Bundle(
            sightlines.course_solids(machine, lambda x, z: terrain.height(x, z, cfg))
        )

    out: dict[str, Any] = {}
    for name, seconds in v221.CANDIDATES.items():
        pacing = v221.Pacing(seconds=seconds, name=name)
        solved = v221.build(
            pacing, spec, rail=rail, land="rail", line=line, spine=spine, cfg=cfg
        )
        # stride 1: the whole point of this pass is that it has more frames, and
        # the one centre-blocked frame it found lives between V22's.
        report = v221.pace_report(solved, bundle=bundle, rail=rail, stride=1)
        report["problems"] = v221.check_v221(report)
        track = v221.preview_track(solved, seed=SEED)
        report["segments"] = [
            {"cut": cut["name"], "from": cut["from"], "to": cut["to"],
             "frames": len(cut["frames"])}
            for cut in track["cuts"]
        ]
        report["prefix"] = round(len(solved["frames"]) / float(FPS), 6)
        os.makedirs(candidate_dir(name), exist_ok=True)
        cp.write_track(track, track_path(name))
        with open(report_path(name), "w", encoding="utf-8", newline="\n") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
            handle.write("\n")
        out[name] = {"solved": solved, "report": report}
    _print_comparison(out)
    return out


def _print_comparison(built: dict[str, Any]) -> None:
    names = list(built)
    reports = [built[name]["report"] for name in names]

    def row(label: str, fetch, fmt: str = "%10s") -> None:
        print(("  %-26s" % label) + "".join(fmt % fetch(r) for r in reports))

    print("\n" + " " * 28 + "".join("%10s" % name.split("_")[-1] + "  " for name in names))
    print("  " + "-" * 26 + "-" * (12 * len(names)))
    row("duration (s)", lambda r: "%.3f" % r["duration"], "%10s  ")
    row("frames", lambda r: r["frames"], "%10s  ")
    row("prefix (s)", lambda r: "%.3f" % r["prefix"], "%10s  ")
    print()
    row("max camera step", lambda r: "%.3f" % r["max_step"], "%10s  ")
    row("mean camera step", lambda r: "%.3f" % r["mean_step"], "%10s  ")
    row("max across / rise",
        lambda r: "%.2f/%.2f" % (r["max_across_step"], r["max_rise_step"]), "%10s  ")
    row("max angular step", lambda r: "%.3f" % r["max_turn"], "%10s  ")
    row("max yaw / pitch",
        lambda r: "%.2f/%.2f" % (r["max_yaw"], r["max_pitch"]), "%10s  ")
    row("straight-track rate", lambda r: "%.3f" % r["flat_units_per_frame"], "%10s  ")
    print("  %-26s" % "  (V22's own peak)" + "%10s" % ("%.3f" % v221.V22_PEAK_STEP))
    print()
    row("track in frame, mean", lambda r: "%.3f" % r["mean_visible_fraction"], "%10s  ")
    row("track in frame, worst", lambda r: "%.3f" % r["min_visible_fraction"], "%10s  ")
    row("ground clearance", lambda r: "%.2f" % r["min_sight_clearance"], "%10s  ")
    row("lens clearance", lambda r: "%.2f" % r["min_lens_clearance"], "%10s  ")
    row("centre blocked (frames)", lambda r: r["centre_blocked_frames"], "%10s  ")
    print()
    print("  landmark screen time, as the subject of the shot")
    for landmark in SHEET_ORDER:
        row("    " + landmark,
            lambda r, k=landmark: "%.3f" % r["subject_seconds"].get(k, 0.0), "%10s  ")
    row("    split (branches+fork)",
        lambda r: "%.3f" % (r["subject_seconds"]["branches"]
                            + r["subject_seconds"]["fork"]), "%10s  ")
    print()
    print("  handoff")
    row("    last step / race first",
        lambda r: "%.3f/%.3f" % (r["handoff"]["last_step"],
                                 r["handoff"]["race_first_step"]), "%10s  ")
    row("    velocity residual",
        lambda r: "%+.5f" % r["handoff"]["velocity_residual"], "%10s  ")
    row("    turn residual",
        lambda r: "%+.5f" % r["handoff"]["turn_residual"], "%10s  ")
    row("    pose / aim delta",
        lambda r: "%.4f/%.4f" % (r["handoff"]["pose_delta"],
                                 r["handoff"]["aim_delta"]), "%10s  ")
    row("    slowest step in settle",
        lambda r: "%.4f" % r["handoff"]["tail_dip"], "%10s  ")
    print()
    for name, report in zip(names, reports):
        problems = report["problems"]
        if problems:
            print(f"  {name}: {len(problems)} problem(s)")
            for problem in problems:
                print(f"    - {problem}")
        else:
            print(f"  {name}: clean")


def stage_freeze(name: str) -> str:
    """The race's first frame held for the length of one candidate."""
    if not os.path.isfile(RACE_REPLAY):
        raise PreviewError(
            f"the race replay is missing: {RACE_REPLAY}\n"
            "  it is generated output and not in the branch; copy it from a tree "
            "that has it, or rebuild it with tools/sloped_integrate.py race."
        )
    with open(RACE_REPLAY, "r", encoding="utf-8") as handle:
        replay = json.load(handle)
    frozen = cp.frozen_replay(replay, v221.CANDIDATES[name] + 0.1, FPS)
    os.makedirs(candidate_dir(name), exist_ok=True)
    with open(replay_path(name), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(frozen, handle, separators=(",", ":"))
        handle.write("\n")
    return replay_path(name)


# --- rendering ------------------------------------------------------------


def _scene_flags(name: str) -> list[str]:
    flags = [
        f"--replay={os.path.abspath(replay_path(name))}",
        f"--cameras={os.path.abspath(track_path(name))}",
        f"--width={WIDTH}",
        f"--height={HEIGHT}",
        "--layout=b",
        "--detail=hero",
        "--routes=both",
    ]
    if os.path.isfile(START_CONTRACT):
        flags.append(f"--start-contract={os.path.abspath(START_CONTRACT)}")
    return flags


def stage_stills(godot: str, only: Sequence[str] = ()) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for name in only or list(v221.CANDIDATES):
        if not os.path.isfile(track_path(name)):
            raise PreviewError(f"{name}: solve first, {track_path(name)} is missing")
        stage_freeze(name)
        with open(track_path(name), "r", encoding="utf-8") as handle:
            cuts = [cut["name"] for cut in json.load(handle)["cuts"]]
        directory = stills_dir(name)
        os.makedirs(directory, exist_ok=True)
        elapsed = run_godot(
            godot,
            [f"--out-dir={os.path.abspath(directory)}",
             f"--stills={','.join(cuts)}", *_scene_flags(name)],
            f"stills {name}",
        )
        written = []
        for cut in cuts:
            path = os.path.join(directory, f"{cut}.png")
            if not os.path.isfile(path):
                raise PreviewError(f"stills {name}: Godot did not write {path}")
            written.append(path)
        print(f"stills {name}: {len(written)} frames in {elapsed:.1f} s -> {directory}")
        out[name] = written
    return out


def stage_clip(godot: str, only: Sequence[str] = ()) -> list[str]:
    videos = []
    for name in only or list(v221.CANDIDATES):
        if not os.path.isfile(track_path(name)):
            raise PreviewError(f"{name}: solve first, {track_path(name)} is missing")
        stage_freeze(name)
        directory = frames_dir(name)
        if os.path.isdir(directory):
            shutil.rmtree(directory)
        os.makedirs(directory, exist_ok=True)
        elapsed = run_godot(
            godot,
            [f"--out-dir={os.path.abspath(directory)}", "--clip=1", f"--fps={FPS}",
             *_scene_flags(name)],
            f"clip {name}",
        )
        count = len([f for f in os.listdir(directory) if f.endswith(".png")])
        print(f"clip {name}: {count} frames in {elapsed:.1f} s")
        videos.append(encode(name))
    return videos


def encode(name: str) -> str:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise PreviewError("ffmpeg is not on PATH")
    video = video_path(name)
    os.makedirs(os.path.dirname(os.path.abspath(video)) or ".", exist_ok=True)
    completed = subprocess.run(
        [ffmpeg, "-y", "-v", "error", "-framerate", str(FPS),
         "-i", os.path.join(frames_dir(name), "frame_%06d.png"),
         "-c:v", "libx264", "-preset", VIDEO_PRESET, "-crf", str(VIDEO_CRF),
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", video],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if completed.returncode != 0:
        raise PreviewError(f"ffmpeg exited {completed.returncode}\n{completed.stderr}")
    print(f"video: {video}  {os.path.getsize(video) / 1024:.0f} KiB")
    return video


def stage_phone(name: str) -> str:
    """The recommended candidate again at 270x480, which is the review size.

    Scaled from the rendered 1080x1920 frames rather than re-rendered, so it is
    the same picture a phone would down-sample - and encoded at a low CRF so the
    encoder is not the thing that makes the fork unreadable.
    """
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise PreviewError("ffmpeg is not on PATH")
    video = os.path.join(OUT_DIR, f"{name}_v221_phone.mp4")
    completed = subprocess.run(
        [ffmpeg, "-y", "-v", "error", "-framerate", str(FPS),
         "-i", os.path.join(frames_dir(name), "frame_%06d.png"),
         "-vf", f"scale={PHONE[0]}:{PHONE[1]}:flags=area",
         "-c:v", "libx264", "-preset", VIDEO_PRESET, "-crf", "14",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", video],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if completed.returncode != 0:
        raise PreviewError(f"ffmpeg exited {completed.returncode}\n{completed.stderr}")
    print(f"phone proof: {video}  {os.path.getsize(video) / 1024:.0f} KiB")
    return video


# --- the rendered frames, measured ---------------------------------------

DUPLICATE_DELTA = 1.0
SPIKE_RATIO = 1.6


def stage_qc(only: Sequence[str] = ()) -> dict[str, Any]:
    """What the rendered frames say about the move, at phone size.

    `tools/sloped_course_preview.stage_qc`'s measurement, run per candidate: the
    mean absolute luma difference between consecutive frames, downsampled to
    270x480 first. It answers two questions the geometry cannot - whether any
    pair of frames is the same picture, and whether any single step stands above
    its neighbours as a hitch rather than a change of speed.

    A *paced* shot's difference series is meant to rise and fall, so the spike
    test is against a nine-frame neighbourhood and not against the whole shot.
    """
    import numpy as np
    from PIL import Image

    out: dict[str, Any] = {}
    for name in only or list(v221.CANDIDATES):
        directory = frames_dir(name)
        if not os.path.isdir(directory):
            continue
        names = sorted(f for f in os.listdir(directory) if f.endswith(".png"))
        if len(names) < 3:
            raise PreviewError(f"qc {name}: {len(names)} frames, not a clip")
        deltas: list[float] = []
        previous = None
        for frame_name in names:
            frame = np.asarray(
                Image.open(os.path.join(directory, frame_name))
                .convert("L").resize(PHONE, Image.BOX),
                dtype=np.int16,
            )
            if previous is not None:
                deltas.append(float(np.abs(frame - previous).mean()))
            previous = frame
        series = np.array(deltas)
        local = np.convolve(series, np.ones(9) / 9.0, mode="same")
        ratio = (series / np.maximum(local, 1e-6))[4:-4]
        duplicates = [
            f"{names[i]} == {names[i + 1]}"
            for i, value in enumerate(deltas) if value < DUPLICATE_DELTA
        ]
        report = {
            "frames": len(names),
            "min_delta": round(float(series.min()), 4),
            "mean_delta": round(float(series.mean()), 4),
            "max_delta": round(float(series.max()), 4),
            "duplicates": duplicates,
            "max_spike_ratio": round(float(ratio.max()), 3),
        }
        verdict = "clean"
        if duplicates:
            verdict = f"FAILED: {len(duplicates)} duplicate pair(s)"
        elif report["max_spike_ratio"] > SPIKE_RATIO:
            verdict = f"FAILED: a step {report['max_spike_ratio']:.2f}x its neighbours"
        print(f"qc {name}: {report['frames']} frames  difference"
              f" min {report['min_delta']:.2f} mean {report['mean_delta']:.2f}"
              f" max {report['max_delta']:.2f}  spike {report['max_spike_ratio']:.2f}"
              f"  {verdict}")
        out[name] = report
    os.makedirs(V221_DIR, exist_ok=True)
    with open(os.path.join(V221_DIR, "qc.json"), "w",
              encoding="utf-8", newline="\n") as handle:
        json.dump(out, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return out


# --- the sheets -----------------------------------------------------------


def _font(size: int):
    from sloped import overlays
    return overlays.load_font(size)


def stage_sheet(out: str = DOCS_DIR) -> list[str]:
    """Two sheets: the three candidates at each landmark, and one candidate's eight.

    The comparison sheet is the one the brief asks for - the same landmark moment
    from all three candidates, side by side, at phone size, so the question "can
    a viewer read the fork" is asked of the three clocks and nothing else.
    """
    from PIL import Image, ImageDraw

    os.makedirs(out, exist_ok=True)
    written: list[str] = []
    names = [n for n in v221.CANDIDATES if os.path.isdir(stills_dir(n))]
    if not names:
        print("sheet: no stills rendered yet")
        return written
    reports = {}
    for name in names:
        if os.path.isfile(report_path(name)):
            with open(report_path(name), "r", encoding="utf-8") as handle:
                reports[name] = json.load(handle)

    cell_w, cell_h = PHONE
    rows = [lm for lm in SHEET_ORDER
            if all(os.path.isfile(os.path.join(stills_dir(n), f"{lm}.png"))
                   for n in names)]
    header = 62
    sheet = Image.new(
        "RGB",
        (GUTTER + len(names) * (cell_w + GUTTER) + 110,
         header + GUTTER + len(rows) * (cell_h + LABEL + GUTTER)),
        BACKGROUND,
    )
    draw = ImageDraw.Draw(sheet)
    draw.text((GUTTER, 8), "V22.1 course preview", font=_font(23), fill=TEXT)
    draw.text((GUTTER, 30),
              "the same landmark at three clocks, at 270x480 - the review size",
              font=_font(15), fill=DIM)
    for column, name in enumerate(names):
        x = GUTTER + 110 + column * (cell_w + GUTTER)
        seconds = v221.CANDIDATES[name]
        draw.text((x, header - 24), f"{name}   {seconds:.1f} s", font=_font(19), fill=TEXT)
    for index, landmark in enumerate(rows):
        y = header + GUTTER + index * (cell_h + LABEL + GUTTER)
        draw.text((GUTTER, y + cell_h // 2 - 8), landmark, font=_font(21), fill=TEXT)
        for column, name in enumerate(names):
            x = GUTTER + 110 + column * (cell_w + GUTTER)
            image = Image.open(os.path.join(stills_dir(name), f"{landmark}.png"))
            sheet.paste(image.convert("RGB").resize(PHONE, Image.LANCZOS), (x, y))
            report = reports.get(name, {})
            subject = report.get("subject_seconds", {}).get(landmark)
            when = next((s["from"] for s in report.get("segments", [])
                         if s["cut"] == landmark), None)
            stamp = f"{when:.2f} s" if when is not None else ""
            if subject is not None:
                stamp += f"   subject {subject:.2f} s"
            draw.text((x + 2, y + cell_h + 6), stamp, font=_font(16), fill=DIM)
    path = os.path.join(out, "v221_landmarks_by_clock.png")
    sheet.save(path)
    written.append(path)
    print(f"sheet: {path}")

    for name in names:
        written.append(_pace_sheet(name, out))
    return written


def _pace_sheet(name: str, out: str) -> str:
    """One candidate's own eight landmarks, over a plot of where its time went."""
    from PIL import Image, ImageDraw

    with open(report_path(name), "r", encoding="utf-8") as handle:
        report = json.load(handle)
    cell_w, cell_h = PHONE
    columns = 4
    rows = 2
    plot_h = 190
    width = GUTTER + columns * (cell_w + GUTTER)
    sheet = Image.new(
        "RGB", (width, 44 + plot_h + rows * (cell_h + LABEL + GUTTER) + GUTTER),
        BACKGROUND,
    )
    draw = ImageDraw.Draw(sheet)
    problems = report.get("problems", [])
    draw.text((GUTTER, 10),
              f"{name}   {report['duration']:.3f} s   {report['frames']} frames"
              f"   straight-track {report['flat_units_per_frame']:.3f} units a frame",
              font=_font(21), fill=TEXT)
    draw.text((GUTTER, 30),
              "clean" if not problems else f"{len(problems)} problem(s): " + problems[0],
              font=_font(16), fill=GOOD if not problems else BAD)

    # Where the time went: a bar per landmark, as a share of the shot, with the
    # brief's priority marked. This is the picture of the pacing.
    top = 52
    total = report["duration"]
    left = GUTTER
    span = width - 2 * GUTTER
    tiers = {"finish": "high", "branches": "high", "fork": "high",
             "obstacle": "high", "start": "high", "merge": "medium",
             "turns": "medium", "mixer": "low"}
    colour = {"high": (120, 190, 255), "medium": (140, 150, 175), "low": (80, 86, 100)}
    cursor = 0.0
    for landmark in SHEET_ORDER:
        seconds = report["subject_seconds"].get(landmark, 0.0)
        x0 = left + span * cursor / total
        x1 = left + span * (cursor + seconds) / total
        draw.rectangle([x0, top, x1 - 1, top + 46], fill=colour[tiers[landmark]])
        draw.text((x0 + 3, top + 6), landmark[:8], font=_font(14), fill=(12, 14, 18))
        draw.text((x0 + 3, top + 24), f"{seconds:.2f}", font=_font(14), fill=(12, 14, 18))
        cursor += seconds
    draw.text((left, top + 52),
              "blue = the brief's high priority, grey = medium, dark = low."
              "  Bar width is screen time as the subject of the shot.",
              font=_font(15), fill=DIM)
    # And the per-frame step, which is the motion itself.
    step_top = top + 78
    steps = report.get("step_series", [])
    if steps:
        peak = max(steps) or 1.0
        for index, value in enumerate(steps):
            x = left + span * index / max(len(steps) - 1, 1)
            draw.line([x, step_top + 76, x, step_top + 76 - 74 * value / peak],
                      fill=(96, 168, 232))
        draw.text((left, step_top + 78),
                  f"lens travel per frame, peak {peak:.2f} layout units",
                  font=_font(15), fill=DIM)

    for index, landmark in enumerate(SHEET_ORDER):
        path = os.path.join(stills_dir(name), f"{landmark}.png")
        if not os.path.isfile(path):
            continue
        column, row = index % columns, index // columns
        x = GUTTER + column * (cell_w + GUTTER)
        y = 44 + plot_h + row * (cell_h + LABEL + GUTTER)
        sheet.paste(Image.open(path).convert("RGB").resize(PHONE, Image.LANCZOS), (x, y))
        entry = report["landmarks"].get(landmark, {})
        draw.text((x + 2, y + cell_h + 3), landmark, font=_font(19), fill=TEXT)
        draw.text((x + 2, y + cell_h + 20),
                  f"subject {report['subject_seconds'].get(landmark, 0):.2f} s"
                  f"   in frame {entry.get('seconds', 0):.2f} s",
                  font=_font(14), fill=DIM)
    path = os.path.join(out, f"v221_{name}.png")
    sheet.save(path)
    print(f"sheet: {path}")
    return path


# --- entry ----------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "stage",
        choices=("solve", "stills", "clip", "qc", "sheet", "phone", "all"),
    )
    parser.add_argument("--godot", default=None)
    parser.add_argument("--only", default="", help="comma-separated candidate names")
    parser.add_argument("--no-solids", action="store_true")
    args = parser.parse_args(argv)
    only = tuple(n for n in args.only.split(",") if n)

    try:
        if args.stage in ("solve", "all"):
            stage_solve(with_solids=not args.no_solids)
        if args.stage in ("stills", "all"):
            stage_stills(find_godot(args.godot), only)
        if args.stage in ("clip", "all"):
            stage_clip(find_godot(args.godot), only)
        if args.stage in ("qc", "all"):
            stage_qc(only)
        if args.stage in ("sheet", "all"):
            stage_sheet()
        if args.stage in ("phone", "all"):
            for name in only or ("preview_35",):
                if os.path.isdir(frames_dir(name)):
                    stage_phone(name)
    except PreviewError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

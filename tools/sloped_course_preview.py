"""Solve, measure, photograph and render the V22 course preview.

    python tools/sloped_course_preview.py solve
    python tools/sloped_course_preview.py stills --godot PATH
    python tools/sloped_course_preview.py clip   --godot PATH
    python tools/sloped_course_preview.py qc
    python tools/sloped_course_preview.py sheet
    python tools/sloped_course_preview.py all    --godot PATH

`solve` is the whole prototype and needs nothing but Python: it writes the
camera track, the metadata and the path report, and prints what
`sloped.course_preview.check_preview` made of it. The other stages render it.

## Why it renders through the race's own scene

The preview is a camera and nothing else, so it is rendered by the shipped
`SlopedRaceRender.tscn` driving the shipped `sloped_race_scene.gd`, with two
files handed to it:

* the camera track, in the format that scene already reads, and
* a **frozen replay** - the race's own frame zero repeated for the length of the
  preview, so the eight racers sit loaded in the start drum and every paddle,
  rotor and wheel is at rest.

That is the whole of the integration. No Godot script is added or changed, the
production camera track is untouched, and the course, the lighting and the
V21 readability pass in frame are exactly the ones the race ships, because they
are the same scene.

The track carries one cut per landmark, so `--stills=finish,merge,fork,...`
photographs the frame whose gaze is on each, and the contact sheet is that set
at phone size beside a plan of the flight.
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

from sloped import course_preview as preview
from sloped import sightlines, terrain
from sloped.course import sloped_course

PROJECT_ROOT = os.getcwd()
GODOT_PROJECT = os.path.join(PROJECT_ROOT, "godot")
RENDER_SCENE = "res://scenes/SlopedRaceRender.tscn"

SEED = 5432
OUT_DIR = os.path.join("output", "sloped_race_v1")
PREVIEW_DIR = os.path.join(OUT_DIR, "preview")
DOCS_DIR = os.path.join("docs", "validation", "sloped_race_v1", "v22_preview")

RACE_REPLAY = os.path.join(OUT_DIR, f"race_{SEED}.json")
START_CONTRACT = os.path.join(OUT_DIR, f"start_contract_{SEED}.json")
TRACK_PATH = os.path.join(PREVIEW_DIR, "preview_cameras.json")
FROZEN_PATH = os.path.join(PREVIEW_DIR, "preview_replay.json")
REPORT_PATH = os.path.join(PREVIEW_DIR, "preview_report.json")
VIDEO_PATH = os.path.join(OUT_DIR, "course_preview_v22.mp4")
FRAMES_DIR = os.path.join(PREVIEW_DIR, "frames")
STILLS_DIR = os.path.join(PREVIEW_DIR, "stills")

WIDTH = 1080
HEIGHT = 1920
FPS = 60
VIDEO_CRF = 16
VIDEO_PRESET = "slow"

# The order the contact sheet reads in, which is the order the preview travels:
# finish first, start last.
SHEET_ORDER = ("finish", "merge", "branches", "fork", "obstacle", "turns", "mixer", "start")


class PreviewError(RuntimeError):
    pass


# --- solving --------------------------------------------------------------


def stage_solve(spec: preview.Preview, with_solids: bool = True) -> dict[str, Any]:
    """Build the flight, measure it, write the track and the report."""
    line = preview.course_line()
    spine = preview.corridor(line)
    cfg = terrain.terrain_config()
    solved = preview.build_preview(spec, line=line, spine=spine, cfg=cfg)

    bundle = None
    if with_solids:
        machine = sloped_course(routes="both")
        bundle = sightlines.Bundle(
            sightlines.course_solids(machine, lambda x, z: terrain.height(x, z, cfg))
        )
    report = preview.path_report(solved, bundle=bundle)
    problems = preview.check_preview(report)
    report["problems"] = problems
    report["segments"] = [
        {"cut": cut["name"], "from": cut["from"], "to": cut["to"], "frames": len(cut["frames"])}
        for cut in preview.preview_track(solved, seed=SEED)["cuts"]
    ]

    os.makedirs(PREVIEW_DIR, exist_ok=True)
    preview.write_track(preview.preview_track(solved, seed=SEED), TRACK_PATH)
    with open(REPORT_PATH, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")

    _print_report(report)
    return {"solved": solved, "report": report, "problems": problems}


def _print_report(report: dict[str, Any]) -> None:
    print(f"preview '{report['name']}'  {report['duration']:.3f} s  "
          f"{report['frames']} frames at {report['fps']} fps  fov {report['fov']:.0f}")
    print(f"  from  {_vec(report['start_position'])}  looking at {_vec(report['start_aim'])}")
    print(f"  to    {_vec(report['end_position'])}  looking at {_vec(report['end_aim'])}")
    print(f"  handoff   {report['end_reach']:.1f} layout units out at"
          f" {report['end_elevation']:.1f} degrees of elevation")
    print(f"  step      max {report['max_step']:.3f}  mean {report['mean_step']:.3f}"
          f"   across {report['max_across_step']:.3f}  rise {report['max_rise_step']:.3f}"
          f"  layout units/frame")
    print(f"  turn      max {report['max_turn']:.3f}  mean {report['mean_turn']:.3f}"
          f"   yaw {report['max_yaw']:.3f}  pitch {report['max_pitch']:.3f}"
          f"   total {report['total_turn']:.1f} degrees")
    print(f"  aim step  max {report['max_aim_step']:.3f} layout units/frame")
    print(f"  clearance terrain {report['min_sight_clearance']:.2f}"
          + (f"  lens {report['min_lens_clearance']:.2f} from {report['nearest_solid']}"
             if "min_lens_clearance" in report else "  (lens clearance not measured)"))
    print(f"  gaze      {report['min_gaze_to_vertical']:.1f} degrees from vertical at worst")
    print(f"  visible   {100.0 * report['mean_visible_fraction']:.1f}% of the ribbon on"
          f" average, {100.0 * report['min_visible_fraction']:.1f}% at worst")
    print(f"  corridor  {report['corridor_length']:.1f} of {report['course_length']:.1f}"
          f" units, straying {report['mean_corridor_stray']:.1f} from the track"
          f" (worst {report['max_corridor_stray']:.1f})")
    print(f"  landmarks {report['landmarks_seen']}/{len(report['landmarks'])} in frame")
    for name, entry in report["landmarks"].items():
        if entry["seen"]:
            print(f"      {name:<10} {entry['from']:.2f}-{entry['to']:.2f} s"
                  f"  ({entry['seconds']:.2f} s)   closest {entry['nearest']:6.1f}"
                  f" at {entry['nearest_at']:.2f} s, {100.0 * entry['best_height']:4.1f}%"
                  f" of frame height")
        else:
            print(f"      {name:<10} never in frame")
    if report["problems"]:
        print("  PROBLEMS")
        for line in report["problems"]:
            print(f"      {line}")
    else:
        print("  no problems found")


def _vec(values: Sequence[float]) -> str:
    return "(%8.2f,%7.2f,%8.2f)" % tuple(values)


def stage_freeze(spec: preview.Preview) -> str:
    """The race's first frame, held, so the scene has something legal to pose."""
    if not os.path.isfile(RACE_REPLAY):
        raise PreviewError(
            f"the race replay is missing: {RACE_REPLAY}\n"
            "  it is generated output and not in the branch; copy it from a tree "
            "that has it, or rebuild it with tools/sloped_integrate.py race."
        )
    with open(RACE_REPLAY, "r", encoding="utf-8") as handle:
        replay = json.load(handle)
    frozen = preview.frozen_replay(replay, spec.seconds, spec.fps)
    os.makedirs(PREVIEW_DIR, exist_ok=True)
    with open(FROZEN_PATH, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(frozen, handle, separators=(",", ":"))
        handle.write("\n")
    print(f"frozen replay: {len(frozen['frames'])} identical frames -> {FROZEN_PATH}"
          f"  ({os.path.getsize(FROZEN_PATH) / 1024:.0f} KiB)")
    return FROZEN_PATH


# --- rendering ------------------------------------------------------------


def find_godot(explicit: str | None) -> str:
    if explicit:
        if os.path.isfile(explicit):
            return explicit
        found = shutil.which(explicit)
        if found:
            return found
        raise PreviewError(f"--godot does not name an executable: {explicit}")
    for variable in ("GODOT_BIN", "GODOT4_BIN"):
        value = os.environ.get(variable)
        if value and os.path.isfile(value):
            return value
    for name in ("godot", "godot4"):
        found = shutil.which(name)
        if found:
            return found
    raise PreviewError(
        "cannot find Godot 4. Pass --godot PATH, set $GODOT_BIN, or put it on PATH."
    )


def run_godot(godot: str, extra: Sequence[str], label: str) -> float:
    """`tools/sloped_integrate.run_godot`'s invocation, unchanged."""
    started = time.perf_counter()
    completed = subprocess.run(
        [godot, "--path", GODOT_PROJECT, RENDER_SCENE, "--", *extra],
        cwd=PROJECT_ROOT,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    elapsed = time.perf_counter() - started
    errors = "\n".join((completed.stderr or "").splitlines()[-30:])
    if completed.returncode != 0:
        raise PreviewError(
            f"{label}: Godot exited {completed.returncode}\n--- stderr ---\n{errors}"
        )
    for line in (completed.stderr or "").splitlines():
        if "SCRIPT ERROR" in line or "Parse Error" in line:
            raise PreviewError(f"{label}: Godot reported an error: {line.strip()}")
    if errors.strip():
        print(f"  godot stderr tail:\n{errors}")
    return elapsed


def _scene_flags() -> list[str]:
    flags = [
        f"--replay={os.path.abspath(FROZEN_PATH)}",
        f"--cameras={os.path.abspath(TRACK_PATH)}",
        f"--width={WIDTH}",
        f"--height={HEIGHT}",
        "--layout=b",
        "--detail=hero",
        # The physics course has both lobes, and a preview of the race has to
        # draw the fork the race actually runs.
        "--routes=both",
    ]
    if os.path.isfile(START_CONTRACT):
        flags.append(f"--start-contract={os.path.abspath(START_CONTRACT)}")
    return flags


def stage_stills(godot: str) -> list[str]:
    with open(TRACK_PATH, "r", encoding="utf-8") as handle:
        track = json.load(handle)
    names = [cut["name"] for cut in track["cuts"]]
    os.makedirs(STILLS_DIR, exist_ok=True)
    elapsed = run_godot(
        godot,
        [f"--out-dir={os.path.abspath(STILLS_DIR)}", f"--stills={','.join(names)}",
         *_scene_flags()],
        "stills",
    )
    written = []
    for name in names:
        path = os.path.join(STILLS_DIR, f"{name}.png")
        if not os.path.isfile(path):
            raise PreviewError(f"stills: Godot did not write {path}")
        written.append(path)
    print(f"stills: {len(written)} frames in {elapsed:.1f} s -> {STILLS_DIR}")
    return written


def stage_at(godot: str, seconds: Sequence[float], out: str = "") -> list[str]:
    """One frame per named output second, from one build of the scene.

    The renderer's own `--at` mode, which walks the same clock `--clip` does, so
    a frame taken here is the frame the video has at that second. The handoff
    pose is the last frame of the shot and the thing the integration session has
    to match, so being able to photograph it without encoding 120 frames is
    worth the stage.
    """
    directory = out or os.path.join(PREVIEW_DIR, "at")
    os.makedirs(directory, exist_ok=True)
    elapsed = run_godot(
        godot,
        [f"--out-dir={os.path.abspath(directory)}",
         "--at=" + ",".join(f"{value:.3f}" for value in seconds),
         *_scene_flags()],
        "at",
    )
    written = [os.path.join(directory, "at_%07.3f.png" % value) for value in seconds]
    missing = [path for path in written if not os.path.isfile(path)]
    if missing:
        raise PreviewError(f"at: Godot did not write {missing[0]}")
    print(f"at: {len(written)} frames in {elapsed:.1f} s -> {directory}")
    return written


def stage_clip(godot: str, video: str = VIDEO_PATH) -> str:
    if os.path.isdir(FRAMES_DIR):
        shutil.rmtree(FRAMES_DIR)
    os.makedirs(FRAMES_DIR, exist_ok=True)
    elapsed = run_godot(
        godot,
        [f"--out-dir={os.path.abspath(FRAMES_DIR)}", "--clip=1", f"--fps={FPS}",
         *_scene_flags()],
        "clip",
    )
    count = len([name for name in os.listdir(FRAMES_DIR) if name.endswith(".png")])
    print(f"clip: {count} frames in {elapsed:.1f} s")
    return encode(video)


def encode(video: str = VIDEO_PATH) -> str:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise PreviewError("ffmpeg is not on PATH")
    os.makedirs(os.path.dirname(os.path.abspath(video)) or ".", exist_ok=True)
    completed = subprocess.run(
        [ffmpeg, "-y", "-v", "error", "-framerate", str(FPS),
         "-i", os.path.join(FRAMES_DIR, "frame_%06d.png"),
         "-c:v", "libx264", "-preset", VIDEO_PRESET, "-crf", str(VIDEO_CRF),
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", video],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if completed.returncode != 0:
        raise PreviewError(f"ffmpeg exited {completed.returncode}\n{completed.stderr}")
    print(f"video: {video}  {os.path.getsize(video) / 1024:.0f} KiB")
    return video


# --- the rendered clip, measured -----------------------------------------

# A frame pair this close is the same picture. The flight never moves less than
# 0.40 layout units between frames, so no honest pair can be.
DUPLICATE_DELTA = 1.0
# And how far one step may stand above its neighbours before it is a hitch
# rather than a change of speed.
SPIKE_RATIO = 1.6
QC_WIDTH, QC_HEIGHT = 270, 480


def stage_qc(directory: str = FRAMES_DIR) -> dict[str, Any]:
    """What the rendered frames themselves say about the move.

    The path report measures the camera; this measures the *picture*, and the
    two are not the same claim. It found a fault nothing geometric could: three
    frames of the first 120-frame render were byte-near-identical to their
    successors, each preceded by a step of twice the usual size, because the cut
    boundaries in the track landed exactly on frame times and the renderer's
    `seconds <= to` comparison sent those frames into the next cut. See
    `sloped.course_preview.preview_track`.

    Mean absolute luma difference between consecutive frames, at phone size.
    Two numbers come out of it: how many pairs are duplicates, and how far the
    worst step stands above its own neighbourhood. A flyover's difference series
    should be smooth and never zero.
    """
    import numpy as np
    from PIL import Image

    names = sorted(name for name in os.listdir(directory) if name.endswith(".png"))
    if len(names) < 3:
        raise PreviewError(f"qc: {directory} has {len(names)} frames, not a clip")
    deltas: list[float] = []
    previous = None
    for name in names:
        frame = np.asarray(
            Image.open(os.path.join(directory, name))
            .convert("L")
            .resize((QC_WIDTH, QC_HEIGHT), Image.BOX),
            dtype=np.int16,
        )
        if previous is not None:
            deltas.append(float(np.abs(frame - previous).mean()))
        previous = frame
    series = np.array(deltas)
    # Against a nine-frame neighbourhood rather than the whole shot, because the
    # flight eases in and out and its difference series is meant to rise and
    # fall. The first and last four are dropped: the window is one-sided there.
    local = np.convolve(series, np.ones(9) / 9.0, mode="same")
    ratio = (series / np.maximum(local, 1e-6))[4:-4]
    duplicates = [
        (names[index], names[index + 1])
        for index, value in enumerate(deltas)
        if value < DUPLICATE_DELTA
    ]
    report = {
        "frames": len(names),
        "min_delta": round(float(series.min()), 4),
        "mean_delta": round(float(series.mean()), 4),
        "max_delta": round(float(series.max()), 4),
        "duplicates": [f"{a} == {b}" for a, b in duplicates],
        "max_spike_ratio": round(float(ratio.max()), 3),
    }
    print(f"qc: {report['frames']} frames   inter-frame difference"
          f"  min {report['min_delta']:.2f}  mean {report['mean_delta']:.2f}"
          f"  max {report['max_delta']:.2f}")
    print(f"    worst step is {report['max_spike_ratio']:.2f} times its neighbours"
          f"   duplicate pairs: {len(duplicates)}")
    for pair in duplicates:
        print(f"      {pair[0]} == {pair[1]}")
    if duplicates:
        print(f"    FAILED: {len(duplicates)} duplicate frame pair(s)")
    elif report["max_spike_ratio"] > SPIKE_RATIO:
        print(f"    FAILED: a step {report['max_spike_ratio']:.2f} times its "
              f"neighbours, over the {SPIKE_RATIO:.1f} allowed")
    else:
        print("    no hitches found")
    with open(os.path.join(PREVIEW_DIR, "preview_qc.json"), "w",
              encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return report


# --- the contact sheet ----------------------------------------------------

PHONE = (270, 480)
GUTTER = 10
LABEL = 34
BACKGROUND = (17, 19, 24)
TEXT = (226, 232, 240)
DIM = (120, 132, 148)
INK = (232, 238, 246)
TRACK_INK = (96, 168, 232)
CORRIDOR_INK = (232, 148, 72)


def stage_sheet(out: str = DOCS_DIR) -> list[str]:
    """The eight landmark frames at phone size, and a plan of the flight beside them.

    Phone size rather than full resolution because the question a preview has to
    answer - can a viewer tell what the course is - is a question about a frame
    270 pixels wide, and a 1080-wide still flatters it.
    """
    from PIL import Image, ImageDraw

    from sloped import overlays

    with open(REPORT_PATH, "r", encoding="utf-8") as handle:
        report = json.load(handle)
    os.makedirs(out, exist_ok=True)
    written: list[str] = []

    names = [name for name in SHEET_ORDER
             if os.path.isfile(os.path.join(STILLS_DIR, f"{name}.png"))]
    if names:
        columns = min(4, len(names))
        rows = (len(names) + columns - 1) // columns
        cell_w, cell_h = PHONE
        sheet = Image.new(
            "RGB",
            (GUTTER + columns * (cell_w + GUTTER), GUTTER + rows * (cell_h + LABEL + GUTTER)),
            BACKGROUND,
        )
        draw = ImageDraw.Draw(sheet)
        for index, name in enumerate(names):
            column, row = index % columns, index // columns
            x = GUTTER + column * (cell_w + GUTTER)
            y = GUTTER + row * (cell_h + LABEL + GUTTER)
            image = Image.open(os.path.join(STILLS_DIR, f"{name}.png")).convert("RGB")
            sheet.paste(image.resize(PHONE, Image.LANCZOS), (x, y))
            draw.text((x + 2, y + cell_h + 4), name,
                      font=overlays.load_font(20), fill=TEXT)
            entry = report["landmarks"].get(name, {})
            when = next((row_["from"] for row_ in report["segments"]
                         if row_["cut"] == name), None)
            stamp = f"{when:.2f} s" if when is not None else ""
            if entry.get("seen"):
                stamp += f"   seen {entry['seconds']:.2f} s"
            draw.text((x + 2, y + cell_h + 20), stamp,
                      font=overlays.load_font(15), fill=DIM)
        path = os.path.join(out, "contact_sheet.png")
        sheet.save(path)
        written.append(path)
    else:
        print(f"sheet: no stills in {STILLS_DIR}; rendering the plan only")

    written.append(_plan(os.path.join(out, "flight_plan.png")))
    for path in written:
        print(f"  {path}  {os.path.getsize(path) // 1024} KiB")
    return written


def _plan(path: str, size: int = 1000) -> str:
    """A plan view of the course, the corridor and the flight, with the gaze drawn.

    The one picture that says what the shot is doing. Every metric in the report
    is a number about this drawing, and a reviewer who disagrees with the numbers
    can point at the place on it.
    """
    from PIL import Image, ImageDraw

    from sloped import overlays

    spec = preview.Preview()
    line = preview.course_line()
    spine = preview.corridor(line)
    solved = preview.build_preview(spec, line=line, spine=spine)

    from sloped.track import TrackRun

    ribbons = [TrackRun(name).path for name in
               ("launch", "leg1", "leg2", "leg3", "blue", "orange", "final")]
    points = [point for ribbon in ribbons for point in ribbon]
    points += [frame["position"] for frame in solved["frames"]]
    low_x = min(point[0] for point in points) - 6.0
    high_x = max(point[0] for point in points) + 6.0
    low_z = min(point[2] for point in points) - 6.0
    high_z = max(point[2] for point in points) + 6.0
    scale = min(size / (high_x - low_x), size / (high_z - low_z))
    width = int((high_x - low_x) * scale) + 1
    height = int((high_z - low_z) * scale) + 1

    def to_px(point):
        return ((point[0] - low_x) * scale, (point[2] - low_z) * scale)

    image = Image.new("RGB", (width, height + 2 * LABEL), BACKGROUND)
    draw = ImageDraw.Draw(image)
    for ribbon in ribbons:
        draw.line([to_px(point) for point in ribbon], fill=TRACK_INK, width=3)
    draw.line([to_px(point) for point in spine.points], fill=CORRIDOR_INK, width=2)
    flight = [to_px(frame["position"]) for frame in solved["frames"]]
    draw.line(flight, fill=INK, width=3)
    for index, frame in enumerate(solved["frames"]):
        if index % 10:
            continue
        draw.line([to_px(frame["position"]), to_px(frame["aim"])], fill=(88, 96, 110), width=1)
    for spot, colour in ((flight[0], (120, 230, 140)), (flight[-1], (240, 108, 108))):
        draw.ellipse([spot[0] - 7, spot[1] - 7, spot[0] + 7, spot[1] + 7], fill=colour)
    for name, point in preview.LANDMARKS:
        at = to_px(point)
        draw.ellipse([at[0] - 4, at[1] - 4, at[0] + 4, at[1] + 4], outline=TEXT, width=2)
        draw.text((at[0] + 7, at[1] - 8), name, font=overlays.load_font(17), fill=TEXT)
    for row, text in enumerate((
        "plan view, +x right and +z down.  blue: the drawn course."
        "  orange: the flight corridor.",
        "white: the flight, green at 0.00 s and red at the handoff."
        "  grey: the gaze, every tenth frame.",
    )):
        draw.text((6, height + 6 + row * 22), text, font=overlays.load_font(16), fill=DIM)
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    image.save(path)
    return path


# --- entry point ----------------------------------------------------------


def _knots(text: str, what: str) -> tuple[float, ...]:
    numbers = tuple(float(value) for value in text.split(","))
    if not numbers:
        raise PreviewError(f"--{what} takes one or more numbers, evenly spaced "
                           f"over the shot")
    return numbers


def _spec(args: argparse.Namespace) -> preview.Preview:
    spec = preview.Preview(seconds=args.seconds, fov=args.fov, name=args.name)
    if args.sway is not None:
        spec.sway = args.sway
    if args.lift:
        spec.lift = _knots(args.lift, "lift")
    if args.lead:
        spec.lead = _knots(args.lead, "lead")
    if args.end_pose:
        numbers = [float(value) for value in args.end_pose.split(",")]
        if len(numbers) != 6:
            raise PreviewError(
                "--end-pose takes six numbers: px,py,pz,ax,ay,az in layout units"
            )
        spec.end_pose = (tuple(numbers[:3]), tuple(numbers[3:]))
    return spec


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("stage", choices=("solve", "freeze", "stills", "at", "clip",
                                          "encode", "qc", "sheet", "all"))
    parser.add_argument("--godot", default="")
    parser.add_argument("--seconds", type=float, default=preview.PREVIEW.seconds)
    parser.add_argument("--fov", type=float, default=preview.PREVIEW.fov)
    parser.add_argument("--sway", type=float, default=None)
    parser.add_argument("--lift", default="", help="layout units, evenly spaced "
                        "over the shot: the lens's height over the corridor")
    parser.add_argument("--lead", default="", help="layout units, evenly spaced "
                        "over the shot: the camera-to-aim distance")
    parser.add_argument("--name", default=preview.PREVIEW.name)
    parser.add_argument("--end-pose", default="",
                        help="px,py,pz,ax,ay,az in layout units: where the race "
                             "camera takes over, blended onto over the last third")
    parser.add_argument("--at", default="",
                        help="output seconds to photograph, for the `at` stage")
    parser.add_argument("--video", default=VIDEO_PATH)
    parser.add_argument("--out", default=DOCS_DIR)
    parser.add_argument("--no-solids", action="store_true",
                        help="skip the lens-clearance pass, which costs a few seconds")
    args = parser.parse_args(argv)

    try:
        spec = _spec(args)
        if args.stage in ("solve", "all"):
            outcome = stage_solve(spec, with_solids=not args.no_solids)
            if args.stage == "solve":
                return 1 if outcome["problems"] else 0
        if args.stage in ("freeze", "stills", "at", "clip", "all"):
            if not os.path.isfile(TRACK_PATH):
                stage_solve(spec, with_solids=not args.no_solids)
            stage_freeze(spec)
        if args.stage in ("stills", "all"):
            stage_stills(find_godot(args.godot or None))
        if args.stage == "at":
            moments = [float(value) for value in args.at.split(",") if value.strip()]
            if not moments:
                raise PreviewError("--at takes output seconds, e.g. --at=0,0.5,1.98")
            stage_at(find_godot(args.godot or None), moments)
        if args.stage in ("clip", "all"):
            stage_clip(find_godot(args.godot or None), args.video)
        if args.stage == "encode":
            encode(args.video)
        if args.stage in ("qc", "all"):
            qc = stage_qc()
            if qc["duplicates"] or qc["max_spike_ratio"] > SPIKE_RATIO:
                return 1
        if args.stage in ("sheet", "all"):
            stage_sheet(args.out)
    except PreviewError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

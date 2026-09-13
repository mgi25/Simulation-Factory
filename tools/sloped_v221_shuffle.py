"""Solve, render and measure the V22.1 start-continuity prototypes.

    python tools/sloped_v221_shuffle.py --stage all --godot PATH

Stages:

    solve    every plan's camera track, and the join measurements
    render   one silent clip per plan, replay 0.200 to 7.620 as that plan cuts it
    sheet    a transition contact sheet per plan - the frames either side of the
             join, plus the replay frames it omits, so the cut can be read on
             paper before anyone watches anything
    report   the measurement table, as JSON and as markdown
    all      all four

Everything lands under `output/sloped_race_v1/v221/`. **Nothing here touches the
physics**: the replay is read and never written, the course is rebuilt from the
same contract the race ran on only so the camera solve has geometry to aim at,
and every window edge is a real replay frame. Seed 5432, finish order unchanged,
`ShuffleFloor` untouched.

The proofs start at the race rather than at the course preview, which is what the
brief asked for: the start is the thing being compared and 2.0 s of identical
preview in front of each clip only makes them harder to scrub.
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

from sloped import cameras, v221_shuffle as v221
from sloped.course import sloped_course

PROJECT_ROOT = os.getcwd()
GODOT_PROJECT = os.path.join(PROJECT_ROOT, "godot")
RENDER_SCENE = "res://scenes/SlopedRaceRender.tscn"

OUT_DIR = os.path.join("output", "sloped_race_v1")
WORK_DIR = os.path.join(OUT_DIR, "v221")

WIDTH, HEIGHT, FPS = 1080, 1920, 60
VIDEO_CRF = 16
VIDEO_PRESET = "slow"

# The plans the proof set renders. The rest of `v221_shuffle.PLANS` stays
# solvable and measurable from `--plans`, which is what the A sweep is for.
PROOF = ("v22", "a25", "b116", "b87", "c")


class ShuffleError(RuntimeError):
    pass


def _replay_path(seed: int) -> str:
    return os.path.join(OUT_DIR, f"race_{seed}.json")


def _load_replay(seed: int) -> dict[str, Any]:
    path = _replay_path(seed)
    if not os.path.isfile(path):
        raise ShuffleError(
            f"the locked replay is missing: {path}\n"
            "  it is generated output and not in the branch; copy it from a tree "
            "that has it, or rebuild it with tools/sloped_integrate.py race."
        )
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _track_path(name: str, seed: int) -> str:
    return os.path.join(WORK_DIR, f"start_{name}_{seed}.json")


def _clip_path(name: str) -> str:
    return os.path.join(WORK_DIR, f"start_{name}.mp4")


def _frames_dir(name: str) -> str:
    return os.path.join(WORK_DIR, "frames", name)


# --- solving ----------------------------------------------------------------


def stage_solve(seed: int, names: Sequence[str]) -> dict[str, Any]:
    replay = _load_replay(seed)
    machine = sloped_course(routes="both")
    os.makedirs(WORK_DIR, exist_ok=True)

    beats = v221.rotor_timeline(machine)
    print("the machine's own start timeline, read off ShuffleFloor:")
    print(f"    gate opens        {beats['release']:.3f}")
    print(f"    rotor turns       {beats['rotor_start']:.3f} - {beats['rotor_stop']:.3f}"
          f"   {beats['rate']:.1f} rad/s, {beats['turns']:.2f} revolutions")
    print(f"    spins down        {beats['rotor_stop']:.3f} - {beats['settled']:.3f}")
    print(f"    blades lift       {beats['lift_at']:.3f}")
    print(f"    trapdoor          {beats['gate']:.3f}")
    print("\nomission lengths that leave the blades where they were:")
    for row in v221.locked_gaps(beats["rate"], FPS, 5):
        print(f"    {int(row['turns'])} rev  {int(row['frames']):3d} frames  "
              f"{row['seconds']:.4f} s   blade error {row['error_deg']:+.4f} deg")

    reports: dict[str, Any] = {}
    for name in names:
        plan = v221.PLANS[name]
        track = v221.build_start_track(replay, machine, plan)
        cameras.write_track(track, _track_path(name, seed))
        report = v221.join_report(track, replay, plan, machine)
        report["problems"] = cameras.check_track(track, replay)
        rows = {i: row for i, row in enumerate(cameras.frame_report(track, replay))}
        report["visible"] = [
            {"in_frame": row.get("in_frame"), "of": row.get("of"),
             "nearest_px": round(float(row.get("nearest_px", 0.0)), 1)}
            for row in rows.values()
        ]
        reports[name] = report
        _print_plan(report)
    path = os.path.join(WORK_DIR, f"joins_{seed}.json")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(reports, handle, indent=1, sort_keys=True)
        handle.write("\n")
    print(f"\njoin measurements -> {path}")
    return reports


def _print_plan(report: dict[str, Any]) -> None:
    print(f"\n{report['plan']}: {report['note']}")
    for window in report["windows"]:
        print(f"    window   replay {window['replay'][0]:8.4f} - {window['replay'][1]:8.4f}"
              f"   {window['frames']} frames")
    print(f"    screen   {report['duration']:.4f} s, {report['output_frames']} frames;"
          f" {report['omissions']} omission, {report['omitted_frames']} replay frames"
          f" ({report['omitted_frames'] / FPS:.4f} s) never shown")
    rotor = report["rotor"]
    print(f"    rotor    blade {rotor['phase_error_deg']:+.4f} deg off, lift "
          f"{rotor['lift_change']:+.4f} sim; inside the constant-rate spin: "
          f"{rotor['inside_constant_rate']}")
    marbles = report["marbles"]
    print(f"    marbles  {marbles['max_sim']:.3f} sim worst, {marbles['mean_sim']:.3f} mean;"
          f" {marbles['max_px']:.0f} px worst = {marbles['max_diameters']:.2f} diameters")
    print(f"    camera   {report['camera_step_join']:.4f} units across the join, against"
          f" {report['camera_step_inside']:.4f} the largest inside a shot;"
          f" reach {report['camera_reach_change']:+.4f}")
    if report["coverage"]["per_marble"]:
        print(f"    blades   {100 * report['coverage']['mean']:.1f}% of the field covered"
              f" at the cut, {100 * report['coverage']['worst_mover']:.1f}% of the worst mover")
    hold = report["live_anticipation"]
    print(f"    live     pour {hold['pour']:.3f}  mixing {hold['mixing']:.3f}"
          f"  wind-down {hold['spin_down']:.3f}  blade lift {hold['blade_lift']:.3f}"
          f"  still {hold['still']:.3f}  -> trapdoor {hold['to_gate']:.3f}")
    for problem in report["problems"]:
        print(f"    PROBLEM: {problem}")


# --- rendering --------------------------------------------------------------


def find_godot(explicit: str | None) -> str:
    if explicit:
        if os.path.isfile(explicit):
            return explicit
        found = shutil.which(explicit)
        if found:
            return found
        raise ShuffleError(f"--godot does not name an executable: {explicit}")
    for variable in ("GODOT_BIN", "GODOT4_BIN"):
        value = os.environ.get(variable)
        if value and os.path.isfile(value):
            return value
    for name in ("godot", "godot4"):
        found = shutil.which(name)
        if found:
            return found
    raise ShuffleError(
        "cannot find Godot 4. Pass --godot PATH, set $GODOT_BIN, or put it on PATH."
    )


def run_godot(godot: str, extra: Sequence[str], label: str) -> float:
    started = time.perf_counter()
    completed = subprocess.run(
        [godot, "--path", GODOT_PROJECT, RENDER_SCENE, "--", *extra],
        cwd=PROJECT_ROOT, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
    )
    elapsed = time.perf_counter() - started
    errors = "\n".join((completed.stderr or "").splitlines()[-20:])
    if completed.returncode != 0:
        raise ShuffleError(f"{label}: Godot exited {completed.returncode}\n{errors}")
    for line in (completed.stderr or "").splitlines():
        if "SCRIPT ERROR" in line or "Parse Error" in line:
            raise ShuffleError(f"{label}: Godot reported an error: {line.strip()}")
    return elapsed


def stage_render(seed: int, names: Sequence[str], godot: str) -> None:
    contract = os.path.join(OUT_DIR, f"start_contract_{seed}.json")
    for name in names:
        track_path = _track_path(name, seed)
        if not os.path.isfile(track_path):
            raise ShuffleError(f"solve first: {track_path} is missing")
        with open(track_path, "r", encoding="utf-8") as handle:
            end = float(json.load(handle)["duration"])
        frames_dir = _frames_dir(name)
        if os.path.isdir(frames_dir):
            shutil.rmtree(frames_dir)
        os.makedirs(frames_dir, exist_ok=True)
        flags = [
            f"--out-dir={os.path.abspath(frames_dir)}",
            f"--replay={os.path.abspath(_replay_path(seed))}",
            f"--cameras={os.path.abspath(track_path)}",
            "--clip=1", f"--end={end:.6f}", f"--fps={FPS}",
            f"--width={WIDTH}", f"--height={HEIGHT}",
            "--layout=b", "--detail=hero", "--routes=both",
        ]
        if os.path.isfile(contract):
            flags.append(f"--start-contract={os.path.abspath(contract)}")
        elapsed = run_godot(godot, flags, name)
        written = sorted(f for f in os.listdir(frames_dir) if f.endswith(".png"))
        if not written:
            raise ShuffleError(f"{name}: no frames were written")
        print(f"{name}: {len(written)} frames in {elapsed:.1f} s "
              f"({elapsed / len(written) * 1000:.0f} ms/frame)")
        _encode(frames_dir, written, _clip_path(name))


def _encode(frames_dir: str, names: Sequence[str], video: str) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise ShuffleError("ffmpeg is not on PATH; frames are rendered but not encoded")
    first = int(names[0].split("_")[1].split(".")[0])
    os.makedirs(os.path.dirname(os.path.abspath(video)), exist_ok=True)
    done = subprocess.run(
        [ffmpeg, "-y", "-framerate", str(FPS), "-start_number", str(first),
         "-i", os.path.join(frames_dir, "frame_%06d.png"),
         "-frames:v", str(len(names)), "-an",
         "-c:v", "libx264", "-preset", VIDEO_PRESET, "-crf", str(VIDEO_CRF),
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", video],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if done.returncode != 0:
        tail = "\n".join((done.stderr or "").splitlines()[-10:])
        raise ShuffleError(f"ffmpeg failed for {video}:\n{tail}")
    print(f"    -> {video} ({os.path.getsize(video) / 1e6:.1f} MB)")


# --- the transition sheet ---------------------------------------------------

# How many output frames either side of the join the sheet shows. Three is enough
# to read a jump and few enough that the strip stays legible on one screen.
SHEET_EITHER_SIDE = 3


def stage_sheet(seed: int, names: Sequence[str]) -> None:
    """One strip per plan: the frames around the join, and the pixel change.

    The strip is built from the rendered frames rather than re-rendered, so what
    it shows is exactly what the clip shows. The two columns either side of the
    gap are the join itself; the number under it is how much of the picture
    changed between them, against the same number for ordinary playback.

    **The number that decides this pass is `rank`**, printed beside each strip:
    where the join's own picture change sits in the sorted list of *every*
    neighbour change in the clip. A join a viewer notices is the biggest change
    in the shot. A join they do not is somewhere down among the drop, the launch
    and the camera's own move - which is to say, among the things that are
    supposed to change the picture.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError as error:  # pragma: no cover - environment
        raise ShuffleError("the contact sheet needs Pillow: pip install Pillow") from error

    summary: dict[str, Any] = {}
    for name in names:
        plan = v221.PLANS[name]
        frames_dir = _frames_dir(name)
        if not os.path.isdir(frames_dir):
            raise ShuffleError(f"render first: {frames_dir} is missing")
        shots = sorted(f for f in os.listdir(frames_dir) if f.endswith(".png"))
        if not shots:
            raise ShuffleError(f"{name}: no frames in {frames_dir}")
        join = _join_index(plan)
        if join is None:
            picks = [max(0, len(shots) // 2 - SHEET_EITHER_SIDE + i)
                     for i in range(2 * SHEET_EITHER_SIDE)]
            label = "no omission - the middle of the shot"
        else:
            picks = [join - SHEET_EITHER_SIDE + 1 + i for i in range(2 * SHEET_EITHER_SIDE)]
            label = (f"replay {plan.cut_at:.4f} | {plan.resume_at:.4f} "
                     f"({plan.omitted_frames()} frames omitted)")
        picks = [p for p in picks if 0 <= p < len(shots)]
        tiles = [Image.open(os.path.join(frames_dir, shots[p])) for p in picks]
        changes = [_mean_abs_change(a, b) for a, b in zip(tiles, tiles[1:])]
        whole = _clip_changes(frames_dir, shots)

        wide = 300
        tall = round(wide * HEIGHT / WIDTH)
        pad, top = 8, 112
        sheet = Image.new("RGB", (len(tiles) * (wide + pad) + pad, tall + top + 46),
                          (17, 17, 20))
        draw = ImageDraw.Draw(sheet)
        draw.text((pad, 10), f"{name}  -  {plan.note}", fill=(240, 240, 240))
        draw.text((pad, 30), label, fill=(190, 190, 190))
        draw.text((pad, 50), "mean |frame difference| between neighbours, 0-255:",
                  fill=(150, 150, 150))
        for index, tile in enumerate(tiles):
            x = pad + index * (wide + pad)
            sheet.paste(tile.resize((wide, tall)), (x, top))
            marks = "JOIN" if join is not None and index == SHEET_EITHER_SIDE - 1 else ""
            draw.text((x, top - 16),
                      f"out {picks[index] / FPS:.3f}s  {marks}", fill=(210, 210, 210))
        for index, change in enumerate(changes):
            x = pad + index * (wide + pad) + wide - 24
            cut = join is not None and index == SHEET_EITHER_SIDE - 1
            draw.text((x, top + tall + 8), f"{change:.1f}",
                      fill=(255, 120, 90) if cut else (140, 200, 140))
        ranked = sorted(whole, reverse=True)
        middle = ranked[len(ranked) // 2]
        across = whole[join] if join is not None else middle
        rank = 1 + sum(1 for value in whole if value > across)
        summary[name] = {
            "join_change": round(across, 3),
            "median_change": round(middle, 3),
            "ratio": round(across / max(middle, 1e-6), 2),
            "largest_change": round(ranked[0], 3),
            "rank_of_join": rank if join is not None else None,
            "of_changes": len(whole),
        }
        draw.text((pad, 70),
                  f"join {across:.1f} vs median {middle:.1f} "
                  f"({across / max(middle, 1e-6):.1f}x); rank {rank} of {len(whole)} "
                  f"neighbour changes in the clip", fill=(235, 190, 150))
        path = os.path.join(WORK_DIR, f"transition_{name}.png")
        sheet.save(path)
        print(f"{name}: join change {across:.2f}, median neighbour {middle:.2f} "
              f"({across / max(middle, 1e-6):.2f}x), biggest in clip {ranked[0]:.2f}; "
              f"the join ranks {rank} of {len(whole)} -> {path}")
    out = os.path.join(WORK_DIR, "picture_change.json")
    with open(out, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(summary, handle, indent=1, sort_keys=True)
        handle.write("\n")
    print(f"-> {out}")


def _clip_changes(frames_dir: str, shots: Sequence[str]) -> list[float]:
    """Mean absolute luma change between every pair of neighbouring frames."""
    import numpy
    from PIL import Image

    values: list[float] = []
    previous = None
    for shot in shots:
        current = numpy.asarray(
            Image.open(os.path.join(frames_dir, shot)).convert("L"), dtype=numpy.int16)
        if previous is not None:
            values.append(float(numpy.abs(current - previous).mean()))
        previous = current
    return values


def _join_index(plan: v221.StartPlan) -> int | None:
    """Which output frame is the last one before the omission, zero-based."""
    if not plan.omits:
        return None
    return round((v221.snap(plan.cut_at) - plan.live_from) * FPS)


def _mean_abs_change(one, two) -> float:
    """Mean absolute luma difference between two frames, 0-255.

    Mean *absolute* difference, not mean luma: two different frames can have the
    same mean luma, which is the trap `docs/sloped_race_v120_short.md` records
    from the duplicate-frame hunt.
    """
    import numpy

    a = numpy.asarray(one.convert("L"), dtype=numpy.int16)
    b = numpy.asarray(two.convert("L"), dtype=numpy.int16)
    return float(numpy.abs(a - b).mean())


# --- the table --------------------------------------------------------------


def stage_report(seed: int, names: Sequence[str]) -> None:
    path = os.path.join(WORK_DIR, f"joins_{seed}.json")
    if not os.path.isfile(path):
        raise ShuffleError(f"solve first: {path} is missing")
    with open(path, "r", encoding="utf-8") as handle:
        reports = json.load(handle)
    lines = [
        "| plan | screen | live mixing | omitted | omissions | rotor blade | rotor lift"
        " | marbles | camera step | to trapdoor |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name in names:
        row = reports[name]
        hold = row["live_anticipation"]
        lines.append(
            f"| `{name}` | {row['duration']:.3f} s | {hold['mixing']:.3f} s |"
            f" {row['omitted_frames'] / FPS:.3f} s | {row['omissions']} |"
            f" {row['rotor']['phase_error_deg']:+.3f} deg |"
            f" {row['rotor']['lift_change']:+.3f} |"
            f" {row['marbles']['max_diameters']:.2f} d |"
            f" {row['camera_step_join']:.3f} |"
            f" {hold['to_gate']:.3f} s |"
        )
    table = "\n".join(lines)
    out = os.path.join(WORK_DIR, "table.md")
    with open(out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(table + "\n")
    print(table)
    print(f"\n-> {out}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", default="all",
                        choices=("solve", "render", "sheet", "report", "all"))
    parser.add_argument("--seed", type=int, default=5432)
    parser.add_argument("--plans", default=",".join(PROOF),
                        help="comma-separated plan names, or 'every'")
    parser.add_argument("--godot", default=None)
    args = parser.parse_args(argv)

    names = (list(v221.PLANS) if args.plans == "every"
             else [n.strip() for n in args.plans.split(",") if n.strip()])
    unknown = [n for n in names if n not in v221.PLANS]
    if unknown:
        raise ShuffleError(f"no such plan: {', '.join(unknown)}")

    if args.stage in ("solve", "all"):
        stage_solve(args.seed, names)
    if args.stage in ("render", "all"):
        stage_render(args.seed, names, find_godot(args.godot))
    if args.stage in ("sheet", "all"):
        stage_sheet(args.seed, names)
    if args.stage in ("report", "all"):
        stage_report(args.seed, names)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ShuffleError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)

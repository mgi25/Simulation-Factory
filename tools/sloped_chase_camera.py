"""The V22 chase-camera prototype, end to end, against a replay that exists.

    python tools/sloped_chase_camera.py --seed 5432 --stage all

Stages, each runnable alone so a set-point tweak does not cost a render:

    solve      build the chase track from the replay, check it, write it
    target     the same solve under all five targeting rules, measured
    sweep      one phase's one set-point over a range, measured
    metrics    every report this prototype claims, as JSON and as a table
    stills     one frame per phase, and V21's frame of the same replay instant
    clip       every frame of the chase, then ffmpeg into one mp4
    sheet      the comparison contact sheet and the 270x480 phone sheet

## What this does not do

It does not re-simulate. `tools/sloped_integrate.py --stage race` writes the
authoritative replay and this reads it; the seed, the physics, the route split
and the finishing order are whatever that file says. A camera is a presentation
decision and this tool cannot reach the race.

It also does not touch `sloped/cameras.py`, `sloped/presentation.py`,
`tools/sloped_short.py` or `tools/sloped_short_qc.py`. The chase is a parallel
subsystem in `sloped/chase_camera.py` that emits the *same* track document the
production solver does, so the Godot scene renders it with no change at all and
the integration session can decide later how the two meet.

## The V21 comparison is like for like

Both tracks are solved from the same replay and both carry an edit map from
output time to replay time. A still is therefore requested by **replay** second
and each track's own map converts it, so the two frames are the same instant of
the same race seen through two camera languages - not two frames that happen to
be near each other.
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

from sloped import cameras as cameras_module
from sloped import chase_camera, readability, sightlines, terrain
from sloped.course import sloped_course

PROJECT_ROOT = os.getcwd()
GODOT_PROJECT = os.path.join(PROJECT_ROOT, "godot")
RENDER_SCENE = "res://scenes/SlopedRaceRender.tscn"

OUT_DIR = os.path.join("output", "sloped_race_v1")
CHASE_DIR = os.path.join(OUT_DIR, "chase")
PROOF_DIR = os.path.join("docs", "validation", "sloped_race_v1", "v22_chase")

WIDTH = 1080
HEIGHT = 1920
FPS = 60
VIDEO_CRF = 16
VIDEO_PRESET = "slow"

GODOT_ENV_VARS = ("GODOT_BIN", "GODOT4_BIN")
GODOT_ON_PATH = ("godot", "godot4")

# The moments the two languages are compared at, in **replay** seconds, chosen
# to be the beats the brief names: first descent, a turn, the approach to the
# obstacle, the obstacle itself, the approach to the fork, the choice, the two
# branches, the junction, and the run to the line. Every one of them lands
# inside a window of both edits, which is what makes the pair legitimate.
MOMENTS: tuple[tuple[str, float], ...] = (
    ("descent", 7.90),
    ("turn", 9.30),
    ("approach", 11.60),
    ("obstacle", 13.20),
    ("fork_in", 15.80),
    ("fork_choice", 16.30),
    ("branches", 18.20),
    ("merge", 19.60),
    ("final", 20.10),
)


class ChaseError(RuntimeError):
    pass


# --- shared ----------------------------------------------------------------


def find_godot(explicit: str | None) -> str:
    if explicit:
        if os.path.isfile(explicit):
            return explicit
        found = shutil.which(explicit)
        if found:
            return found
        raise ChaseError(f"--godot does not name an executable: {explicit}")
    for variable in GODOT_ENV_VARS:
        value = os.environ.get(variable)
        if value and os.path.isfile(value):
            return value
    for name in GODOT_ON_PATH:
        found = shutil.which(name)
        if found:
            return found
    raise ChaseError(
        "cannot find Godot 4. Pass --godot PATH, set "
        f"{' or '.join('$' + n for n in GODOT_ENV_VARS)}, or put it on PATH."
    )


def paths_for(seed: int) -> dict[str, str]:
    return {
        "replay": os.path.join(OUT_DIR, f"race_{seed}.json"),
        "start": os.path.join(OUT_DIR, f"start_contract_{seed}.json"),
        "chase": os.path.join(CHASE_DIR, f"chase_{seed}.json"),
        "v21": os.path.join(CHASE_DIR, f"v21_{seed}.json"),
        "metrics": os.path.join(CHASE_DIR, f"metrics_{seed}.json"),
        "video": os.path.join(OUT_DIR, f"chase_v22_{seed}.mp4"),
    }


def load_replay(path: str) -> dict[str, Any]:
    if not os.path.isfile(path):
        raise ChaseError(
            f"no replay at {path}. Run "
            f"`python tools/sloped_integrate.py --seed SEED --stage race --routes both` first."
        )
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def out_time(track: dict[str, Any], replay_seconds: float) -> float | None:
    """Where one replay instant lands on a track's own output clock.

    The inverse of the edit map, and `None` when the track omits that instant -
    which is a fact worth returning rather than approximating, because a
    comparison sheet that silently substitutes the nearest kept frame is a
    sheet comparing two different moments.
    """
    for segment in track.get("edit", []):
        low, high = segment["replay"]
        if low - 1e-6 <= replay_seconds <= high + 1e-6:
            return segment["out"][0] + (replay_seconds - low)
    return None


def _fmt(value: Any, spec: str = "") -> str:
    if value is None:
        return "-"
    return format(value, spec) if spec else str(value)


# --- stages ----------------------------------------------------------------


def stage_solve(
    replay: dict[str, Any],
    machine,
    out: str,
    rule: str = "adaptive",
    phases: Sequence[chase_camera.ChasePhase] = chase_camera.PHASES,
    quiet: bool = False,
) -> dict[str, Any]:
    track = chase_camera.build_chase(replay, machine, phases=phases, fps=FPS, rule=rule)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    cameras_module.write_track(track, out)
    if quiet:
        return track

    chase_cuts = [cut for cut in track["cuts"] if cut.get("chase")]
    print(
        f"chase: {len(track['cuts'])} cuts ({len(chase_cuts)} chase phases) over "
        f"{track['duration']:.2f} s of output from {track['replay_duration']:.2f} s "
        f"of replay, rule {track['rule']!r} -> {out}"
    )
    rows = {row["cut"]: row for row in readability.readability_report(track, replay)}
    print(
        f"    {'phase':10s} {'from':>6} {'to':>6} {'px_med':>7} {'px_tail':>7} "
        f"{'cover':>6} {'lost':>5} {'off':>5} {'step':>6} {'elev':>5} {'clear':>6}  racers"
    )
    for cut in track["cuts"]:
        row = rows.get(cut["name"], {})
        mark = " " if cut.get("chase") else "*"
        print(
            f"  {mark} {cut['name']:10s} {cut['from']:6.2f} {cut['to']:6.2f} "
            f"{row.get('px_median', 0.0):7.1f} {row.get('px_tail', 0.0):7.1f} "
            f"{row.get('coverage', 0.0):6.3f} {row.get('lost_seconds', 0.0):5.2f} "
            f"{row.get('off_centre', 0.0):5.2f} {row.get('camera_step', 0.0):6.3f} "
            f"{cut.get('elevation', 0.0):5.1f} {cut.get('min_clearance', 0.0):6.2f}"
            f"  {row.get('in_frame_mean', 0.0):4.1f}/{row.get('of', 0)}"
        )
    print("    (* = a V21 lens, lifted unchanged)")

    problems = chase_camera.check_chase(track, replay)
    problems += readability.check_readability(
        track, replay, skip=(), arrivals=("finish", "start")
    )
    if problems:
        print("  findings:")
        for problem in problems:
            print(f"    - {problem}")
    else:
        print("  findings: none")
    return track


def stage_target(replay: dict[str, Any], machine) -> list[dict[str, Any]]:
    """The same chase under every targeting rule, measured on the chase phases."""
    print(
        f"{'rule':10s} {'px_med':>7} {'px_tail':>7} {'cover':>6} {'lost':>6} "
        f"{'off':>5} {'step':>6} {'racers':>7}  worst phase"
    )
    out: list[dict[str, Any]] = []
    for rule in chase_camera.TARGETS:
        track = chase_camera.build_chase(replay, machine, fps=FPS, rule=rule)
        rows = [
            row
            for row in readability.readability_report(track, replay)
            if any(
                cut["name"] == row["cut"] and cut.get("chase") for cut in track["cuts"]
            )
        ]
        if not rows:
            continue
        weights = [row["frames"] for row in rows]
        total = sum(weights) or 1

        def mean(key: str) -> float:
            return sum(row[key] * row["frames"] for row in rows) / total

        worst = min(rows, key=lambda row: row["coverage"])
        record = {
            "rule": rule,
            "px_median": round(mean("px_median"), 1),
            "px_tail": round(mean("px_tail"), 1),
            "coverage": round(mean("coverage"), 3),
            "lost_seconds": round(max(row["lost_seconds"] for row in rows), 2),
            "off_centre": round(mean("off_centre"), 3),
            "camera_step": round(max(row["camera_step"] for row in rows), 3),
            "in_frame": round(mean("in_frame_mean"), 2),
            "worst": f"{worst['cut']} {worst['coverage']:.2f}",
        }
        out.append(record)
        print(
            f"{rule:10s} {record['px_median']:7.1f} {record['px_tail']:7.1f} "
            f"{record['coverage']:6.3f} {record['lost_seconds']:6.2f} "
            f"{record['off_centre']:5.2f} {record['camera_step']:6.3f} "
            f"{record['in_frame']:7.2f}  {record['worst']}"
        )
    return out


def stage_sweep(
    replay: dict[str, Any],
    machine,
    phase_name: str,
    field: str,
    values: Sequence[float],
    rule: str = "adaptive",
) -> list[dict[str, Any]]:
    """One set-point over a range, with the readability of its own phase."""
    import dataclasses

    print(f"sweep {phase_name}.{field}")
    print(
        f"{'value':>7} {'px_med':>7} {'px_tail':>7} {'cover':>6} {'lost':>6} "
        f"{'off':>5} {'step':>6} {'racers':>7} {'visible':>8} {'both':>6}"
    )
    cfg = terrain.terrain_config(machine.runs)
    bundle = sightlines.Bundle(
        sightlines.course_solids(machine, lambda x, z: terrain.height(x, z, cfg))
    )
    out: list[dict[str, Any]] = []
    for value in values:
        phases = tuple(
            dataclasses.replace(phase, **{field: float(value)})
            if phase.name == phase_name
            else phase
            for phase in chase_camera.PHASES
        )
        track = chase_camera.build_chase(
            replay, machine, phases=phases, fps=FPS, rule=rule
        )
        rows = {
            row["cut"]: row for row in readability.readability_report(track, replay)
        }
        row = rows.get(phase_name)
        if row is None:
            continue
        vis = {
            entry["cut"]: entry
            for entry in readability.visibility_report(
                track, replay, machine, bundle=bundle, stride=12
            )
        }
        seen = vis.get(phase_name, {})
        record = {
            "value": float(value),
            **{key: row[key] for key in
               ("px_median", "px_tail", "coverage", "lost_seconds", "off_centre",
                "camera_step", "in_frame_mean")},
            "visible_mean": seen.get("visible_mean", 0.0),
            "both_routes": seen.get("both_routes", 0.0),
        }
        out.append(record)
        print(
            f"{value:7.1f} {row['px_median']:7.1f} {row['px_tail']:7.1f} "
            f"{row['coverage']:6.3f} {row['lost_seconds']:6.2f} {row['off_centre']:5.2f} "
            f"{row['camera_step']:6.3f} {row['in_frame_mean']:7.2f} "
            f"{seen.get('visible_mean', 0.0):8.2f} {seen.get('both_routes', 0.0):6.2f}"
        )
    return out


def stage_metrics(
    replay: dict[str, Any], machine, chase: dict[str, Any], v21: dict[str, Any], out: str
) -> dict[str, Any]:
    """Every number this prototype claims, for both tracks, in one document."""
    cfg = terrain.terrain_config(machine.runs)
    bundle = sightlines.Bundle(
        sightlines.course_solids(machine, lambda x, z: terrain.height(x, z, cfg))
    )

    def measure(track: dict[str, Any], label: str) -> dict[str, Any]:
        read = readability.readability_report(track, replay)
        vis = readability.visibility_report(track, replay, machine, bundle=bundle, stride=6)
        chase_rows = chase_camera.chase_report(
            track, replay, machine, bundle=bundle, stride=12
        )
        cont = readability.continuity_report(track, replay)
        by_name: dict[str, dict[str, Any]] = {}
        for row in read:
            by_name.setdefault(row["cut"], {}).update(row)
        for row in vis:
            by_name.setdefault(row["cut"], {}).update(
                {key: row[key] for key in
                 ("visible_mean", "hidden_share", "both_routes", "blockers")}
            )
        for row in chase_rows:
            by_name.setdefault(row["cut"], {}).update(
                {key: row[key] for key in
                 ("turn_median", "turn_max", "speed_median", "speed_max",
                  "ahead_share", "ahead_units")}
            )
        # A boundary counts as a **cut** only where the lens actually jumps.
        # Phase boundaries inside the chase are samples of one curve and are
        # counted separately, which is the whole claim of this prototype.
        jumps = [row for row in cont if (row.get("travel") or 0.0) > chase_camera.MAX_PHASE_STEP]
        return {
            "label": label,
            "cuts": len(track["cuts"]),
            "duration": track["duration"],
            "hard_cuts": len(jumps),
            "per_cut": by_name,
            "continuity": cont,
            "findings": (
                chase_camera.check_chase(track, replay)
                if track.get("chase")
                else cameras_module.check_track(track, replay)
            )
            + readability.check_readability(
                track, replay, skip=("establish",), arrivals=("finish", "start")
            ),
        }

    document = {
        "seed": replay["seed"],
        "v22": measure(chase, "v22-chase"),
        "v21": measure(v21, "v21-production"),
    }
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(document, handle, indent=1, sort_keys=True)
        handle.write("\n")

    for label in ("v22", "v21"):
        block = document[label]
        print(
            f"{block['label']}: {block['cuts']} cuts, {block['hard_cuts']} of them a "
            f"jump over {chase_camera.MAX_PHASE_STEP} layout units, "
            f"{block['duration']:.2f} s"
        )
        print(
            f"    {'cut':10s} {'px_med':>7} {'cover':>6} {'vis':>5} {'hid':>5} "
            f"{'both':>5} {'turn/f':>7} {'ahead':>6} {'ahead_u':>8}"
        )
        for name, row in block["per_cut"].items():
            print(
                f"    {name:10s} {_fmt(row.get('px_median'), '7.1f')} "
                f"{_fmt(row.get('coverage'), '6.3f')} {_fmt(row.get('visible_mean'), '5.2f')} "
                f"{_fmt(row.get('hidden_share'), '5.2f')} {_fmt(row.get('both_routes'), '5.2f')} "
                f"{_fmt(row.get('turn_median'), '7.3f')} {_fmt(row.get('ahead_share'), '6.2f')} "
                f"{_fmt(row.get('ahead_units'), '8.1f')}"
            )
    print(f"  wrote {out}")
    return document


# --- rendering --------------------------------------------------------------


def godot_command(godot: str, extra: Sequence[str]) -> list[str]:
    return [godot, "--path", GODOT_PROJECT, RENDER_SCENE, "--", *extra]


def run_godot(godot: str, extra: Sequence[str], label: str) -> float:
    started = time.perf_counter()
    completed = subprocess.run(
        godot_command(godot, extra),
        cwd=PROJECT_ROOT,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    elapsed = time.perf_counter() - started
    errors = "\n".join((completed.stderr or "").splitlines()[-30:])
    if completed.returncode != 0:
        raise ChaseError(
            f"{label}: Godot exited {completed.returncode}\n--- stderr ---\n{errors}"
        )
    for line in (completed.stderr or "").splitlines():
        if "SCRIPT ERROR" in line or "Parse Error" in line:
            raise ChaseError(f"{label}: Godot reported an error: {line.strip()}")
    return elapsed


def start_flag(path: str) -> list[str]:
    if path and os.path.isfile(path):
        return [f"--start-contract={os.path.abspath(path)}"]
    return []


def stage_stills(
    godot: str,
    replay_path: str,
    start_path: str,
    tracks: dict[str, str],
    out_dir: str,
) -> dict[str, list[str]]:
    """One frame per named moment, from each track, at the same replay instant."""
    written: dict[str, list[str]] = {}
    os.makedirs(out_dir, exist_ok=True)
    for label, cameras_path in tracks.items():
        with open(cameras_path, "r", encoding="utf-8") as handle:
            track = json.load(handle)
        wanted: list[tuple[str, float]] = []
        for name, when in MOMENTS:
            mapped = out_time(track, when)
            if mapped is None:
                print(f"  {label}: {name} at replay {when:.2f}s is omitted by this edit")
                continue
            wanted.append((name, mapped))
        scratch = os.path.join(CHASE_DIR, f"stills_{label}")
        if os.path.isdir(scratch):
            shutil.rmtree(scratch)
        os.makedirs(scratch, exist_ok=True)
        elapsed = run_godot(
            godot,
            [
                f"--out-dir={os.path.abspath(scratch)}",
                f"--replay={os.path.abspath(replay_path)}",
                f"--cameras={os.path.abspath(cameras_path)}",
                *start_flag(start_path),
                f"--at={','.join(f'{when:.3f}' for _name, when in wanted)}",
                f"--width={WIDTH}",
                f"--height={HEIGHT}",
                "--layout=b",
                "--detail=hero",
            ],
            f"stills:{label}",
        )
        paths = []
        for name, when in wanted:
            source = os.path.join(scratch, f"at_{when:07.3f}.png")
            if not os.path.isfile(source):
                raise ChaseError(f"stills: Godot did not write {source}")
            target = os.path.join(out_dir, f"{label}_{name}.png")
            shutil.copyfile(source, target)
            paths.append(target)
        written[label] = paths
        print(f"stills {label}: {len(paths)} frames in {elapsed:.1f} s")
    return written


def stage_clip(
    godot: str, replay_path: str, start_path: str, cameras_path: str, video: str
) -> dict[str, Any]:
    frames_dir = os.path.join(CHASE_DIR, "frames")
    if os.path.isdir(frames_dir):
        shutil.rmtree(frames_dir)
    os.makedirs(frames_dir, exist_ok=True)
    with open(cameras_path, "r", encoding="utf-8") as handle:
        track = json.load(handle)
    end = float(track["duration"])
    elapsed = run_godot(
        godot,
        [
            f"--out-dir={os.path.abspath(frames_dir)}",
            f"--replay={os.path.abspath(replay_path)}",
            f"--cameras={os.path.abspath(cameras_path)}",
            *start_flag(start_path),
            "--clip=1",
            f"--end={end:.6f}",
            f"--fps={FPS}",
            f"--width={WIDTH}",
            f"--height={HEIGHT}",
            "--layout=b",
            "--detail=hero",
        ],
        "clip",
    )
    frames = sorted(f for f in os.listdir(frames_dir) if f.endswith(".png"))
    if not frames:
        raise ChaseError("clip: no frames were written")
    print(
        f"clip: {len(frames)} frames in {elapsed:.1f} s "
        f"({elapsed / len(frames) * 1000:.0f} ms/frame)"
    )
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise ChaseError("ffmpeg is not on PATH; the frames are rendered but not encoded")
    first = int(frames[0].split("_")[1].split(".")[0])
    os.makedirs(os.path.dirname(os.path.abspath(video)), exist_ok=True)
    completed = subprocess.run(
        [
            ffmpeg, "-y",
            "-framerate", str(FPS),
            "-start_number", str(first),
            "-i", os.path.join(frames_dir, "frame_%06d.png"),
            "-frames:v", str(len(frames)),
            "-an",
            "-c:v", "libx264",
            "-preset", VIDEO_PRESET,
            "-crf", str(VIDEO_CRF),
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            video,
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if completed.returncode != 0:
        tail = "\n".join((completed.stderr or "").splitlines()[-15:])
        raise ChaseError(f"ffmpeg exited {completed.returncode}\n{tail}")
    size = os.path.getsize(video) / (1024 * 1024)
    print(f"video: {video}  {size:.1f} MiB  {len(frames) / FPS:.2f} s")
    return {"video": video, "frames": len(frames)}


def stage_sheet(stills: str, out_dir: str) -> list[str]:
    """V21 above V22 at each moment, full size and at a handset's own size.

    Two sheets rather than one, because they answer different questions. The
    contact sheet is whether the framing is right; the phone sheet is whether a
    racer is still a racer at 270x480, which is roughly what a 1080-wide Short
    occupies on a handset and is the size the brief is actually about.
    """
    from PIL import Image, ImageDraw

    from sloped import overlays

    os.makedirs(out_dir, exist_ok=True)
    pairs: list[tuple[str, str, str]] = []
    for name, _when in MOMENTS:
        top = os.path.join(stills, f"v21_{name}.png")
        bottom = os.path.join(stills, f"v22_{name}.png")
        if os.path.isfile(top) and os.path.isfile(bottom):
            pairs.append((name, top, bottom))
    if not pairs:
        raise ChaseError(f"no still pairs in {stills}")

    written: list[str] = []
    for tile_height, label, columns in ((480, "sheet", 5), (480 // 2, "phone", 9)):
        tile_width = round(tile_height * WIDTH / HEIGHT)
        pad, header = 8, 26
        rows = math.ceil(len(pairs) / columns)
        cell_w = tile_width + pad
        cell_h = 2 * tile_height + header + pad * 2
        sheet = Image.new(
            "RGB", (columns * cell_w + pad, rows * cell_h + pad), (17, 18, 22)
        )
        draw = ImageDraw.Draw(sheet)
        for index, (name, top, bottom) in enumerate(pairs):
            column, row = index % columns, index // columns
            x = pad + column * cell_w
            y = pad + row * cell_h
            draw.text(
                (x + 2, y + 4),
                f"{name}   V21 / V22",
                font=overlays.load_font(16),
                fill=(232, 232, 236),
            )
            for offset, path in enumerate((top, bottom)):
                with Image.open(path) as image:
                    frame = image.convert("RGB").resize(
                        (tile_width, tile_height), Image.LANCZOS
                    )
                sheet.paste(frame, (x, y + header + offset * (tile_height + pad // 2)))
        target = os.path.join(out_dir, f"{label}.png")
        sheet.save(target)
        written.append(target)
        print(f"{label}: {sheet.size[0]}x{sheet.size[1]} -> {target}")
    return written


# --- cli --------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=5432)
    parser.add_argument(
        "--stage",
        default="solve",
        choices=("solve", "target", "sweep", "metrics", "stills", "clip", "sheet",
                 "all", "render"),
    )
    parser.add_argument("--rule", default="adaptive", choices=chase_camera.TARGETS)
    parser.add_argument("--routes", default="both", choices=("blue", "both"))
    parser.add_argument("--godot", default="")
    parser.add_argument("--phase", default="routes", help="which phase --stage sweep moves")
    parser.add_argument("--field", default="trail", help="which set-point it moves")
    parser.add_argument(
        "--values", default="",
        help="comma-separated values for --stage sweep",
    )
    parser.add_argument("--video", default="")
    args = parser.parse_args(argv)

    paths = paths_for(args.seed)
    os.makedirs(CHASE_DIR, exist_ok=True)
    replay = load_replay(paths["replay"])
    machine = sloped_course(routes=args.routes)

    stages = (
        ("solve", "metrics", "stills", "clip", "sheet")
        if args.stage == "all"
        else ("stills", "clip", "sheet")
        if args.stage == "render"
        else (args.stage,)
    )
    godot = ""
    if any(stage in ("stills", "clip") for stage in stages):
        godot = find_godot(args.godot or None)
        print(f"godot: {godot}")

    chase = v21 = None
    for stage in stages:
        print(f"--- {stage} ---")
        if stage == "solve":
            chase = stage_solve(replay, machine, paths["chase"], rule=args.rule)
        elif stage == "target":
            stage_target(replay, machine)
        elif stage == "sweep":
            values = [float(v) for v in args.values.split(",") if v.strip()]
            if not values:
                raise ChaseError("--stage sweep needs --values")
            stage_sweep(replay, machine, args.phase, args.field, values, rule=args.rule)
        elif stage == "metrics":
            if chase is None:
                chase = stage_solve(
                    replay, machine, paths["chase"], rule=args.rule, quiet=True
                )
            v21 = cameras_module.build_track(
                replay, machine, fps=FPS, edit=cameras_module.EDITS["v212"]
            )
            cameras_module.write_track(v21, paths["v21"])
            stage_metrics(replay, machine, chase, v21, paths["metrics"])
        elif stage == "stills":
            if not os.path.isfile(paths["v21"]):
                track = cameras_module.build_track(
                    replay, machine, fps=FPS, edit=cameras_module.EDITS["v212"]
                )
                cameras_module.write_track(track, paths["v21"])
            if not os.path.isfile(paths["chase"]):
                stage_solve(replay, machine, paths["chase"], rule=args.rule, quiet=True)
            stage_stills(
                godot,
                paths["replay"],
                paths["start"],
                {"v21": paths["v21"], "v22": paths["chase"]},
                os.path.join(PROOF_DIR, "stills"),
            )
        elif stage == "clip":
            if not os.path.isfile(paths["chase"]):
                stage_solve(replay, machine, paths["chase"], rule=args.rule, quiet=True)
            stage_clip(
                godot,
                paths["replay"],
                paths["start"],
                paths["chase"],
                args.video or paths["video"],
            )
        elif stage == "sheet":
            stage_sheet(os.path.join(PROOF_DIR, "stills"), PROOF_DIR)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ChaseError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)

"""Prove that the marbles were always spinning, and make the spin visible.

    python tools/sloped_v24_spin.py --stage diagnose
    python tools/sloped_v24_spin.py --stage all --godot PATH

Stages, in the order they answer the brief:

    diagnose  measure the replay: is there rotation, and does the renderer
              apply it? Writes `validation/diagnosis.json`.
    clips     one clip per moment per appearance, full resolution, plus a
              270x480 downscale of each - the phone read.
    sheet     the four appearances side by side at one instant, at both sizes
    boundary  what the V22.1 shuffle omission does to marble orientation, and
              whether a different whole-frame boundary joins it better
    perf      render cost of each appearance against the plain sphere
    all       all five

**Nothing here simulates.** The replay is `race_5432.json`, read and never
written, and every clip is the same seed, the same physics and the same
outcome. The only thing that changes between a control clip and a proof clip
is `--racers=`, which picks which albedo map the racer material carries.

**The control matters as much as the variants.** `--racers=solid` is the
appearance every film through V22.1 shipped, and it is rendered here from the
same replay through the same camera as the proofs, so the pair of clips differ
in exactly one thing.
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

from sloped import v24_spin as spin

PROJECT_ROOT = os.getcwd()
GODOT_PROJECT = os.path.join(PROJECT_ROOT, "godot")
RENDER_SCENE = "res://scenes/SlopedRaceRender.tscn"

OUT_DIR = os.path.join("output", "sloped_race_v1")
WORK = os.path.join(OUT_DIR, "v24", "spin")
VALIDATION = os.path.join("docs", "validation", "sloped_race_v1", "v24_spin")

SEED = 5432
WIDTH, HEIGHT, FPS = 1080, 1920, 60
PHONE = (270, 480)
VIDEO_CRF = 16
VIDEO_PRESET = "slow"

#: The appearances, control first. `solid` is not a variant - it is what the
#: delivered film has, rendered here so every comparison is a pair.
APPEARANCES = ("solid", "ribbon", "crescent", "meridian")

#: The moments, named in **replay** seconds and converted to the film's own
#: clock by the camera track's edit. Naming them in replay time is what makes
#: them moments in the race rather than positions in a file: the mixer is where
#: the rotor is turning, wherever the edit happens to put it.
MOMENTS: tuple[tuple[str, float, float, str], ...] = (
    ("mixer_spin_up", 0.80, 2.00, "the rotor winding up, marbles stirred in the bowl"),
    ("mixer_full", 4.05, 5.25, "the rotor at speed and slowing - the key proof"),
    ("trapdoor", 5.95, 7.05, "the floor drops and the field falls out of the start"),
    ("descent", 8.40, 9.60, "the first downhill, marbles rolling on the slope"),
    ("obstacle", 13.80, 15.00, "the paddle wheels, spin changed by contact"),
)

#: The edit boundary, spanned by a clip of its own so the cut can be watched
#: rather than described.
BOUNDARY_CLIP = ("omission", 1.35, 2.35)


class SpinError(RuntimeError):
    pass


# --- paths ----------------------------------------------------------------


def replay_path(seed: int = SEED) -> str:
    return os.path.join(OUT_DIR, f"race_{seed}.json")


def track_path(seed: int = SEED) -> str:
    return os.path.join(OUT_DIR, f"cameras_v221_{seed}.json")


def contract_path(seed: int = SEED) -> str:
    return os.path.join(OUT_DIR, f"start_contract_{seed}.json")


def find_godot(explicit: str | None) -> str:
    for candidate in (explicit, os.environ.get("GODOT_BIN"), os.environ.get("GODOT4_BIN")):
        if candidate and os.path.isfile(candidate):
            return candidate
    found = shutil.which("godot") or shutil.which("godot4")
    if found:
        return found
    raise SpinError("no Godot binary; pass --godot or set GODOT_BIN")


def _ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found is None:
        raise SpinError("ffmpeg is not on PATH")
    return found


# --- the film's clock -----------------------------------------------------


def out_seconds(track: dict[str, Any], replay_second: float) -> float | None:
    """This film's output second for a replay second, or None if it is cut.

    The inverse of the renderer's `replay_at`. A moment named in replay time
    may simply not be in the film - the shuffle omission drops 1.95 s of it -
    and that has to come back as "not in the film" rather than as the nearest
    second that is, or a proof clip would silently be of the wrong thing.
    """
    for entry in track.get("edit") or []:
        low, high = float(entry["replay"][0]), float(entry["replay"][1])
        if low - 1.0e-9 <= replay_second <= high + 1.0e-9:
            return float(entry["out"][0]) + (replay_second - low)
    return None


def out_window(track: dict[str, Any], start: float, end: float) -> tuple[float, float]:
    first = out_seconds(track, start)
    last = out_seconds(track, end)
    if first is None or last is None:
        raise SpinError(
            f"replay {start:.3f}-{end:.3f} s is not entirely in the film; "
            "the edit omits part of it"
        )
    if last <= first:
        raise SpinError(f"replay {start:.3f}-{end:.3f} s spans a cut")
    return first, last


# --- rendering ------------------------------------------------------------


def run_godot(godot: str, extra: Sequence[str], label: str) -> tuple[float, str]:
    started = time.perf_counter()
    completed = subprocess.run(
        [godot, "--path", GODOT_PROJECT, RENDER_SCENE, "--", *extra],
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    elapsed = time.perf_counter() - started
    errors = "\n".join((completed.stderr or "").splitlines()[-30:])
    if completed.returncode != 0:
        raise SpinError(f"{label}: Godot exited {completed.returncode}\n{errors}")
    for line in (completed.stderr or "").splitlines():
        if "SCRIPT ERROR" in line or "Parse Error" in line:
            raise SpinError(f"{label}: Godot reported an error: {line.strip()}")
    return elapsed, completed.stdout or ""


def render(
    godot: str,
    appearance: str,
    frames_dir: str,
    start: float,
    end: float,
    seed: int = SEED,
    width: int = WIDTH,
    height: int = HEIGHT,
) -> dict[str, Any]:
    """One window of the film, at one racer appearance."""
    if os.path.isdir(frames_dir):
        shutil.rmtree(frames_dir)
    os.makedirs(frames_dir, exist_ok=True)
    flags = [
        f"--out-dir={os.path.abspath(frames_dir)}",
        f"--replay={os.path.abspath(replay_path(seed))}",
        f"--cameras={os.path.abspath(track_path(seed))}",
        "--clip=1",
        f"--start={start:.6f}",
        f"--end={end:.6f}",
        f"--fps={FPS}",
        f"--width={width}",
        f"--height={height}",
        "--layout=b",
        "--detail=hero",
        "--routes=both",
        # V22.1's own render flag. The proofs have to be of the delivered
        # picture, not of a picture that differs from it in a second way.
        "--finish-sign=double",
        f"--racers={appearance}",
        f"--start-contract={os.path.abspath(contract_path(seed))}",
    ]
    elapsed, output = run_godot(godot, flags, f"{appearance} {start:.2f}-{end:.2f}")
    names = sorted(name for name in os.listdir(frames_dir) if name.endswith(".png"))
    if not names:
        raise SpinError(f"{appearance}: no frames were written")
    meshes, triangles = _scene_cost(output)
    return {
        "appearance": appearance,
        "frames": len(names),
        "seconds": round(elapsed, 3),
        "ms_per_frame": round(elapsed / len(names) * 1000.0, 1),
        "mesh_instances": meshes,
        "triangles": triangles,
        "dir": frames_dir,
        "names": names,
    }


def _scene_cost(output: str) -> tuple[int, int]:
    for line in output.splitlines():
        if line.startswith("scene: ") and "mesh instances" in line:
            parts = line.replace(",", " ").split()
            return int(parts[1]), int(parts[4].lstrip("~"))
    return 0, 0


def encode(frames_dir: str, names: Sequence[str], video: str, scale: tuple[int, int] | None = None) -> None:
    first = int(names[0].split("_")[1].split(".")[0])
    os.makedirs(os.path.dirname(os.path.abspath(video)), exist_ok=True)
    command = [
        _ffmpeg(), "-y", "-framerate", str(FPS),
        "-start_number", str(first),
        "-i", os.path.join(frames_dir, "frame_%06d.png"),
        "-frames:v", str(len(names)), "-an",
    ]
    if scale is not None:
        # `lanczos` rather than the default, because the whole question a phone
        # clip answers is whether a thin band survives being made small, and a
        # soft resampler would answer it for the wrong reason.
        command += ["-vf", f"scale={scale[0]}:{scale[1]}:flags=lanczos"]
    command += [
        "-c:v", "libx264", "-preset", VIDEO_PRESET, "-crf", str(VIDEO_CRF),
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", video,
    ]
    done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if done.returncode != 0:
        tail = "\n".join((done.stderr or "").splitlines()[-15:])
        raise SpinError(f"ffmpeg failed for {video}\n{tail}")


# --- stages ---------------------------------------------------------------


def stage_diagnose(seed: int = SEED) -> dict[str, Any]:
    """Is the marble rotating, and does the renderer apply it? Numbers only."""
    replay = spin.load_replay(replay_path(seed))
    track = spin.load_track(track_path(seed))
    marker = spin.Marker.load()

    phases = [entry.to_json() for entry in spin.angular_stats(replay)]
    print("--- is the replay rotating? ---")
    for row in phases:
        print(
            f"  {row['phase']:10s} {row['replay_from']:5.2f}-{row['replay_to']:5.2f} s  "
            f"|w| med {row['spin_rad_s']['median']:7.2f} p95 {row['spin_rad_s']['p95']:7.2f} "
            f"max {row['spin_rad_s']['max']:7.2f} rad/s | "
            f"step med {row['step_deg_per_frame']['median']:6.2f} deg/frame | "
            f"{row['turns_per_second_median']:5.2f} turns/s"
        )
    nyquist = spin.nyquist_report(replay)
    print(
        f"  sampling: max {nyquist['max_deg_per_frame']:.2f} deg between replay frames "
        f"(at {nyquist['at_replay_second']:.2f} s); {nyquist['over_180_deg']} over 180 deg"
    )

    print("--- can the picture say so? visible marker change per frame ---")
    readable: dict[str, list[dict[str, Any]]] = {}
    for name, start, end, _why in MOMENTS:
        window = (start, end)
        readable[name] = []
        for appearance in APPEARANCES:
            row = spin.readability(replay, track, appearance, window, marker)
            readable[name].append(row)
            print(
                f"  {name:14s} {appearance:9s} median {row.get('median', 0.0):8.5f} "
                f"p95 {row.get('p95', 0.0):8.5f} quiet {row.get('quiet_share', 0.0) * 100:5.1f}%"
            )

    report = {
        "seed": seed,
        "replay_digest_frames": len(replay["frames"]),
        "phases": phases,
        "sampling": nyquist,
        "readability": readable,
        "marker_tint": marker.tint,
    }
    _write_json(os.path.join(VALIDATION, "diagnosis.json"), report)
    return report


def stage_boundary(seed: int = SEED) -> dict[str, Any]:
    """What the shuffle omission does to orientation, and what would do better."""
    replay = spin.load_replay(replay_path(seed))
    track = spin.load_track(track_path(seed))
    found = spin.omissions(track)
    if not found:
        raise SpinError("this camera track omits no replay time")
    cut = found[0]
    before, after = cut["replay_before"], cut["replay_after"]
    print(
        f"--- the V22.1 shuffle omission: replay {before:.3f} -> {after:.3f} s "
        f"({cut['omitted']:.3f} s), at output {cut['out_second']:.3f} s ---"
    )

    shipped = spin.boundary_report(replay, before, after)
    machine = {
        "rotors": round(spin.machine_mismatch(replay, before, after), 4),
        "shuffle_wheel": round(
            spin.machine_mismatch(replay, before, after, ("shuffle.wheel0_blade0",)), 4
        ),
    }
    print(
        f"  marbles turn a median {shipped['turn_deg_median']:.1f} deg across it "
        f"(max {shipped['turn_deg_max']:.1f}); one ordinary frame here is "
        f"{shipped['one_frame_turn_deg_median']:.2f} deg"
    )
    for index, (turn, move) in enumerate(zip(shipped["turn_deg"], shipped["move_sim"])):
        flag = "  <-- turns while standing still" if move < 0.2 else ""
        print(f"    marble {index}: turns {turn:6.1f} deg, moves {move:6.4f} sim{flag}")
    print(f"  machine across the cut: rotors {machine['rotors']:.2f} deg, "
          f"shuffle wheel {machine['shuffle_wheel']:.2f} deg "
          f"(4 blades, so {min(machine['shuffle_wheel'] % 90.0, 90.0 - machine['shuffle_wheel'] % 90.0):.2f} deg visible)")

    scan = spin.scan_boundary(replay, before, after, reach=0.50)
    baseline = next(row for row in scan if row["offset"] == 0.0)
    keep = [
        row for row in scan
        if row["machine_mismatch_deg"] <= baseline["machine_mismatch_deg"] + 1.0e-6
    ]
    keep.sort(key=lambda row: -row["stillest_move_sim"])
    print(f"--- {len(scan)} whole-frame alternatives of the same length; "
          f"{len(keep)} keep the machine no worse ---")
    for row in keep[:6]:
        print(
            f"    offset {row['offset']:+7.4f} s ({int(round(row['offset'] * FPS)):+4d} fr)  "
            f"rotors {row['machine_mismatch_deg']:6.2f} deg  "
            f"stillest marble moves {row['stillest_move_sim']:.4f} sim while turning "
            f"{row['turn_of_stillest_deg']:6.1f} deg"
        )
    marker = spin.Marker.load()
    curve = spin.saturation("meridian", marker)
    knee = next((deg for deg, value in curve if value > 0.9 * max(v for _d, v in curve)), None)
    print("--- how much turn a marking can actually show ---")
    print("    " + "  ".join(f"{int(deg)}d:{value:.3f}" for deg, value in curve))
    print(f"    the measure saturates by about {knee:.0f} deg, so every candidate above is "
          "equally scrambled: sliding the join cannot reduce the orientation jump,")
    print("    it can only remove the marble that changes face without changing place.")

    best = keep[0] if keep else None
    report = {
        "saturation": curve,
        "saturation_knee_deg": knee,
        "omission": cut,
        "shipped": shipped,
        "shipped_machine": machine,
        "scan": scan,
        "best_offset": best["offset"] if best else None,
        "best": best,
    }
    _write_json(os.path.join(VALIDATION, "boundary.json"), report)
    return report


def stage_clips(godot: str, seed: int = SEED, only: Sequence[str] = ()) -> dict[str, Any]:
    """One clip per moment per appearance, full resolution and phone size."""
    track = spin.load_track(track_path(seed))
    wanted = [row for row in MOMENTS if not only or row[0] in only]
    made: list[dict[str, Any]] = []
    for name, start, end, why in wanted:
        first, last = out_window(track, start, end)
        print(f"--- {name}: replay {start:.2f}-{end:.2f} s -> out {first:.2f}-{last:.2f} s ({why}) ---")
        for appearance in APPEARANCES:
            frames_dir = os.path.join(WORK, "frames", f"{name}_{appearance}")
            result = render(godot, appearance, frames_dir, first, last, seed)
            full = os.path.join(WORK, "clips", f"{name}_{appearance}.mp4")
            phone = os.path.join(WORK, "clips", f"{name}_{appearance}_phone.mp4")
            encode(frames_dir, result["names"], full)
            encode(frames_dir, result["names"], phone, scale=PHONE)
            print(
                f"  {appearance:9s} {result['frames']} frames  "
                f"{result['ms_per_frame']:.0f} ms/frame  {full}"
            )
            made.append({k: v for k, v in result.items() if k != "names"} | {
                "moment": name, "video": full, "phone": phone,
            })
    _write_json(os.path.join(VALIDATION, "clips.json"), {"clips": made})
    return {"clips": made}


def stage_boundary_clip(godot: str, seed: int = SEED) -> dict[str, Any]:
    """The cut itself, at each appearance, so the join can be watched."""
    name, first, last = BOUNDARY_CLIP
    made: list[dict[str, Any]] = []
    print(f"--- {name}: out {first:.2f}-{last:.2f} s, spanning the shuffle omission ---")
    for appearance in APPEARANCES:
        frames_dir = os.path.join(WORK, "frames", f"{name}_{appearance}")
        result = render(godot, appearance, frames_dir, first, last, seed)
        full = os.path.join(WORK, "clips", f"{name}_{appearance}.mp4")
        encode(frames_dir, result["names"], full)
        encode(frames_dir, result["names"], os.path.join(
            WORK, "clips", f"{name}_{appearance}_phone.mp4"), scale=PHONE)
        # The two frames either side of the join, side by side and large.
        _join_pair(frames_dir, result["names"], first, appearance)
        print(f"  {appearance:9s} {result['frames']} frames -> {full}")
        made.append({k: v for k, v in result.items() if k != "names"} | {"video": full})
    return {"boundary_clips": made}


def _join_pair(frames_dir: str, names: Sequence[str], first: float, appearance: str) -> None:
    """The last frame before the cut and the first after it, as one picture."""
    track = spin.load_track(track_path())
    cut = spin.omissions(track)[0]["out_second"]
    index = int(round((cut - first) * FPS))
    if index < 1 or index >= len(names):
        return
    left = Image.open(os.path.join(frames_dir, names[index - 1]))
    right = Image.open(os.path.join(frames_dir, names[index]))
    sheet = Image.new("RGB", (left.width + right.width, left.height), (14, 16, 20))
    sheet.paste(left, (0, 0))
    sheet.paste(right, (left.width, 0))
    draw = ImageDraw.Draw(sheet)
    draw.text((24, 24), f"{appearance}  last frame before the cut", fill=(240, 240, 240))
    draw.text((left.width + 24, 24), f"{appearance}  first frame after", fill=(240, 240, 240))
    out = os.path.join(VALIDATION, f"join_{appearance}.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sheet.resize((sheet.width // 2, sheet.height // 2), Image.LANCZOS).save(out)


def stage_sheet(godot: str, seed: int = SEED) -> dict[str, Any]:
    """The four appearances at one instant, full size and phone size."""
    track = spin.load_track(track_path(seed))
    # Mid-mixer, where the brief says the problem is most visible.
    when = out_seconds(track, 4.60)
    if when is None:
        raise SpinError("the mixer instant is not in this film")
    tiles: list[tuple[str, Image.Image]] = []
    for appearance in APPEARANCES:
        frames_dir = os.path.join(WORK, "frames", f"sheet_{appearance}")
        result = render(godot, appearance, frames_dir, when, when + 1.0 / FPS, seed)
        tiles.append((appearance, Image.open(os.path.join(frames_dir, result["names"][0])).copy()))
        print(f"  sheet {appearance:9s} ok")
    for label, size in (("sheet", (WIDTH // 3, HEIGHT // 3)), ("phone_sheet", PHONE)):
        sheet = Image.new("RGB", (size[0] * len(tiles), size[1] + 22), (14, 16, 20))
        draw = ImageDraw.Draw(sheet)
        for index, (appearance, image) in enumerate(tiles):
            sheet.paste(image.resize(size, Image.LANCZOS), (index * size[0], 22))
            note = f"{appearance}  (as shipped)" if appearance == "solid" else appearance
            draw.text((index * size[0] + 8, 6), note, fill=(235, 235, 235))
        out = os.path.join(VALIDATION, f"{label}.png")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        sheet.save(out)
        print(f"  wrote {out}")
    return {"sheet": os.path.join(VALIDATION, "sheet.png")}


def stage_phone(seed: int = SEED) -> dict[str, Any]:
    """Does the marking survive 270x480? Measured on the pixels, not by eye.

    A still at phone size cannot answer this, because the question is about
    motion: at ten pixels across, a marble's band is a soft darkening, and what
    the eye picks up is that the darkening *moves*. So the measure is the
    frame-to-frame change inside the marble discs after the frame has been
    reduced to phone size.

    **The control is what makes it a measurement.** A plain marble already
    changes those pixels every frame, because it is travelling and the light on
    it is changing; that is the floor. Whatever a marked marble scores above
    the plain one is what the marking contributed, and it is the only part of
    the number that is about rotation at all.
    """
    replay = spin.load_replay(replay_path(seed))
    track = spin.load_track(track_path(seed))
    scale = float(replay["units"]["render_scale"])
    fps = float(replay["replay_fps"])
    rows: list[dict[str, Any]] = []
    for name, start, end, _why in MOMENTS:
        first, _last = out_window(track, start, end)
        masks: dict[int, np.ndarray] = {}
        scores: dict[str, list[float]] = {}
        for appearance in APPEARANCES:
            frames_dir = os.path.join(WORK, "frames", f"{name}_{appearance}")
            if not os.path.isdir(frames_dir):
                continue
            names = sorted(n for n in os.listdir(frames_dir) if n.endswith(".png"))
            small = [
                np.asarray(
                    Image.open(os.path.join(frames_dir, n)).convert("L").resize(
                        PHONE, Image.LANCZOS),
                    dtype=np.float32,
                )
                for n in names
            ]
            values: list[float] = []
            for index in range(len(small) - 1):
                if index not in masks:
                    masks[index] = _disc_mask(replay, track, start + index / fps, scale)
                mask = masks[index]
                if not mask.any():
                    continue
                values.append(float(np.abs(small[index + 1] - small[index])[mask].mean()))
            if values:
                scores[appearance] = values
        if "solid" not in scores:
            continue
        floor = float(np.median(scores["solid"]))
        for appearance, values in scores.items():
            median = float(np.median(values))
            rows.append({
                "moment": name,
                "appearance": appearance,
                "phone_luma_change": round(median, 4),
                "over_control": round(median - floor, 4),
                "over_control_pct": round((median - floor) / floor * 100.0, 1) if floor else None,
            })
            print(f"  {name:14s} {appearance:9s} {median:7.3f} luma/frame in the discs  "
                  f"({median - floor:+6.3f} vs the plain sphere)")
    _write_json(os.path.join(VALIDATION, "phone.json"), {"phone": rows})
    return {"phone": rows}


def _disc_mask(replay: dict[str, Any], track: dict[str, Any], replay_second: float,
               scale: float) -> np.ndarray:
    """True where a marble is, at phone size, at one replay instant."""
    mask = np.zeros((PHONE[1], PHONE[0]), dtype=bool)
    fps = float(replay["replay_fps"])
    index = min(max(int(round(replay_second * fps)), 0), len(replay["frames"]) - 1)
    frame = None
    for cut in track["cuts"]:
        for row in cut["frames"]:
            if abs(float(row[0]) - round(index / fps, 6)) < 0.5 / fps:
                frame = row
                break
        if frame is not None:
            break
    if frame is None:
        return mask
    eye, aim, fov = np.array(frame[1:4]), np.array(frame[4:7]), float(frame[7])
    radius = float(replay["marbles"][0].get("radius", 0.5)) * scale
    ys, xs = np.mgrid[0:PHONE[1], 0:PHONE[0]]
    for marble in replay["frames"][index]["marbles"]:
        centre = np.array(marble["p"], dtype=float) * scale
        x, y, depth = spin.project(centre, eye, aim, fov, PHONE[0], PHONE[1])
        if np.isnan(x):
            continue
        span = radius / depth / np.tan(np.radians(fov) * 0.5) * PHONE[1]
        mask |= (xs - x) ** 2 + (ys - y) ** 2 <= span * span
    return mask


def stage_crop(seed: int = SEED) -> dict[str, Any]:
    """Filmstrips: the same eight marbles, close, every few frames.

    A clip answers the review question properly, but a strip is the thing that
    can be put in a report and argued about - and it is the only form in which
    the control and a variant can be compared frame for frame without playing
    two files at once. The crop is computed from the camera, not chosen by eye,
    so the control and the variants are cropped identically by construction.
    """
    replay = spin.load_replay(replay_path(seed))
    track = spin.load_track(track_path(seed))
    made: list[str] = []
    for name, start, end, _why in MOMENTS:
        first, _last = out_window(track, start, end)
        # A third of a second in, so the strip starts after the clip settles.
        at = start + 0.30
        try:
            box = spin.field_box(replay, track, at, WIDTH, HEIGHT)
        except ValueError as problem:
            print(f"  {name}: no crop ({problem})")
            continue
        box = _padded(box, WIDTH, HEIGHT)
        # Six frames two apart: 1/30 s of real time between tiles, which is slow
        # enough to follow a band and fast enough that a whole strip is one
        # moment rather than a summary of the shot.
        start_index = int(round(0.30 * FPS))
        steps = [start_index + step * 2 for step in range(6)]
        # **Each tile is cropped around the field at its own instant.** A single
        # box taken from the first tile works in the bowl, where the marbles
        # stay put, and fails completely on the descent, where the field crosses
        # the frame and leaves a fixed crop behind within three tiles.
        # The box is sized to the *widest* the field gets over the strip, not to
        # the first tile: on the descent the eight spread out as they roll, and
        # a box cut to the huddle they start in clips half of them away.
        spans = [box]
        for index in steps:
            try:
                spans.append(_padded(spin.field_box(
                    replay, track, start + index / FPS, WIDTH, HEIGHT), WIDTH, HEIGHT))
            except ValueError:
                continue
        size = (
            min(WIDTH, max(span[2] - span[0] for span in spans)),
            min(HEIGHT, max(span[3] - span[1] for span in spans)),
        )
        boxes = [_recentred(replay, track, start + index / FPS, size) for index in steps]
        for appearance in APPEARANCES:
            frames_dir = os.path.join(WORK, "frames", f"{name}_{appearance}")
            if not os.path.isdir(frames_dir):
                continue
            names = sorted(n for n in os.listdir(frames_dir) if n.endswith(".png"))
            picked = [(names[index], boxes[order])
                      for order, index in enumerate(steps)
                      if index < len(names) and boxes[order] is not None]
            if not picked:
                continue
            made.append(_strip(frames_dir, picked, name, appearance))
    return {"strips": made}


def _padded(box: tuple[int, int, int, int], width: int, height: int,
            pad: int = 40) -> tuple[int, int, int, int]:
    left, top, right, bottom = box
    return (
        max(0, left - pad), max(0, top - pad),
        min(width, right + pad), min(height, bottom + pad),
    )


def _recentred(replay: dict[str, Any], track: dict[str, Any], replay_second: float,
               size: tuple[int, int]) -> tuple[int, int, int, int] | None:
    """A crop of fixed size, centred on where the field is at this instant."""
    try:
        left, top, right, bottom = spin.field_box(replay, track, replay_second,
                                                  WIDTH, HEIGHT)
    except ValueError:
        return None
    centre_x, centre_y = (left + right) // 2, (top + bottom) // 2
    half_w, half_h = size[0] // 2, size[1] // 2
    x = min(max(centre_x - half_w, 0), max(0, WIDTH - size[0]))
    y = min(max(centre_y - half_h, 0), max(0, HEIGHT - size[1]))
    return (x, y, x + size[0], y + size[1])


def _strip(frames_dir: str, picked: Sequence[tuple[str, tuple[int, int, int, int]]],
           moment: str, appearance: str) -> str:
    tiles = [Image.open(os.path.join(frames_dir, name)).crop(box)
             for name, box in picked]
    gap = 6
    sheet = Image.new(
        "RGB",
        (tiles[0].width * len(tiles) + gap * (len(tiles) - 1), tiles[0].height + 20),
        (14, 16, 20),
    )
    for index, tile in enumerate(tiles):
        sheet.paste(tile, (index * (tile.width + gap), 20))
    draw = ImageDraw.Draw(sheet)
    label = f"{moment}  {appearance}" + ("  (as shipped)" if appearance == "solid" else "")
    draw.text((6, 5), f"{label}   one tile every 2 frames (1/30 s apart)", fill=(235, 235, 235))
    out = os.path.join(VALIDATION, f"strip_{moment}_{appearance}.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    # Half size to commit. A marble is ~60 px across in the crop, so halving
    # still shows which way the band is facing, and a set of twenty
    # full-resolution strips is 35 MB of branch for no extra evidence.
    sheet.resize((sheet.width // 2, sheet.height // 2), Image.LANCZOS).save(out)
    print(f"  wrote {out}")
    return out


def stage_perf(godot: str, seed: int = SEED) -> dict[str, Any]:
    """What the marking costs, measured the only way that counts: rendering."""
    track = spin.load_track(track_path(seed))
    first, last = out_window(track, 4.05, 5.25)
    rows: list[dict[str, Any]] = []
    for appearance in APPEARANCES:
        frames_dir = os.path.join(WORK, "frames", f"perf_{appearance}")
        result = render(godot, appearance, frames_dir, first, last, seed)
        rows.append({k: v for k, v in result.items() if k not in ("names", "dir")})
        print(
            f"  {appearance:9s} {result['frames']} frames  {result['ms_per_frame']:7.1f} ms/frame  "
            f"{result['mesh_instances']} mesh instances  {result['triangles']} triangles"
        )
    base = next(row for row in rows if row["appearance"] == "solid")
    for row in rows:
        row["vs_solid_pct"] = round(
            (row["ms_per_frame"] - base["ms_per_frame"]) / base["ms_per_frame"] * 100.0, 2
        )
        row["extra_mesh_instances"] = row["mesh_instances"] - base["mesh_instances"]
        row["extra_triangles"] = row["triangles"] - base["triangles"]
        print(f"  {row['appearance']:9s} {row['vs_solid_pct']:+6.2f}% vs solid, "
              f"{row['extra_mesh_instances']:+d} mesh instances, "
              f"{row['extra_triangles']:+d} triangles")
    _write_json(os.path.join(VALIDATION, "performance.json"), {"renders": rows})
    return {"renders": rows}


def _write_json(path: str, payload: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    print(f"  wrote {path}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--godot", default="")
    parser.add_argument(
        "--stage", default="diagnose",
        choices=("diagnose", "boundary", "clips", "boundary-clip", "sheet", "crop",
                 "phone", "perf", "all"),
    )
    parser.add_argument("--only", default="", help="comma-separated moment names")
    args = parser.parse_args(argv)

    stages = (
        ("diagnose", "boundary", "perf", "clips", "boundary-clip", "sheet", "crop",
         "phone")
        if args.stage == "all" else (args.stage,)
    )
    godot = ""
    if any(stage in ("clips", "boundary-clip", "sheet", "perf") for stage in stages):
        godot = find_godot(args.godot or None)
        print(f"godot: {godot}")
    only = tuple(part for part in args.only.split(",") if part)

    for stage in stages:
        print(f"=== {stage} ===")
        if stage == "diagnose":
            stage_diagnose(args.seed)
        elif stage == "boundary":
            stage_boundary(args.seed)
        elif stage == "clips":
            stage_clips(godot, args.seed, only)
        elif stage == "boundary-clip":
            stage_boundary_clip(godot, args.seed)
        elif stage == "sheet":
            stage_sheet(godot, args.seed)
        elif stage == "crop":
            stage_crop(args.seed)
        elif stage == "phone":
            stage_phone(args.seed)
        elif stage == "perf":
            stage_perf(godot, args.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

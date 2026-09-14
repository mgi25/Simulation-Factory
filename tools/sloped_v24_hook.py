"""Solve, render and measure the V24 opening hooks.

    python tools/sloped_v24_hook.py --stage all --godot PATH

Stages:

    solve    every variant's opening track, and the frame-zero measurements
    frames   the first frame of every variant, as a full-resolution still
    measure  the two things only a render can answer, folded into the report:
             whether each racer's own colour is on screen, and what PICK A COLOR
             will read against
    render   a short proof clip per variant: the hook plus enough of the start
             shot after it to read the handoff
    sheet    the phone-size comparison boards - first frames at 270x480 side by
             side, with and without PICK A COLOR, and a motion strip per variant
    report   the measurement table, as JSON and as markdown
    all      all six

    grid     the search the three variants were chosen out of: up to fourteen
             candidate framings rendered and scored in **one** Godot launch.
             Takes `--grid bearing=...,elevation=...,extent=...,pan=...` as
             comma-separated lists and sweeps their product

Everything lands under `output/sloped_race_v1/v24/` and the boards are copied to
`docs/validation/sloped_race_v1/v24/`.

**Nothing here touches the physics.** The replay is read and never written, the
course is rebuilt from the same contract the race ran on only so the camera
solve has geometry to aim at, seed 5432 is untouched and every window edge is a
real replay frame. The hook consumes replay 0.200 to its own handoff and hands
the rest of the shipped start window back to `v221.START` with nothing but its
`live_from` moved.
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

from sloped import cameras, sightlines, terrain, v24_hook as hook
from sloped.course import sloped_course

PROJECT_ROOT = os.getcwd()
GODOT_PROJECT = os.path.join(PROJECT_ROOT, "godot")
RENDER_SCENE = "res://scenes/SlopedRaceRender.tscn"

OUT_DIR = os.path.join("output", "sloped_race_v1")
WORK_DIR = os.path.join(OUT_DIR, "v24")
DOC_DIR = os.path.join("docs", "validation", "sloped_race_v1", "v24")

WIDTH, HEIGHT, FPS = 1080, 1920, 60
VIDEO_CRF = 16
VIDEO_PRESET = "slow"

# The phone the retention numbers came off. 270x480 is a quarter of the delivery
# in each axis and is what a feed thumbnail and a scrubbed preview look like.
PHONE = (270, 480)

# How much of the shipped start shot rides along after the hook in a proof clip.
# The brief asks for three to four seconds; the hook is 1.2 and this makes the
# clip long enough to hold the handoff, the pour and the rotor taking hold.
PROOF_SECONDS = 3.6


class HookError(RuntimeError):
    pass


# --- inputs -----------------------------------------------------------------


def _replay_path(seed: int) -> str:
    return os.path.join(OUT_DIR, f"race_{seed}.json")


def _load_replay(seed: int) -> dict[str, Any]:
    path = _replay_path(seed)
    if not os.path.isfile(path):
        raise HookError(
            f"the locked replay is missing: {path}\n"
            "  it is generated output and not in the branch; copy it from a tree "
            "that has it, or rebuild it with tools/sloped_integrate.py race."
        )
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _track_path(name: str, seed: int) -> str:
    return os.path.join(WORK_DIR, f"open_{name}_{seed}.json")


def _frames_dir(name: str) -> str:
    return os.path.join(WORK_DIR, "frames", name)


def _still_dir(name: str) -> str:
    return os.path.join(WORK_DIR, "stills", name)


def _clip_path(name: str) -> str:
    return os.path.join(WORK_DIR, f"open_{name}.mp4")


def variants(replay: dict[str, Any], machine, names: Sequence[str] | None = None):
    """The control plus the named hooks, in report order."""
    table = {"v221": hook.control_hook(replay, machine), **hook.HOOKS}
    if names:
        missing = [name for name in names if name not in table]
        if missing:
            raise HookError(f"no such variant: {', '.join(missing)}")
        return [(name, table[name]) for name in names]
    return list(table.items())


# --- solving ----------------------------------------------------------------


def stage_solve(seed: int, names: Sequence[str] | None, backdrop: bool = True) -> dict[str, Any]:
    replay = _load_replay(seed)
    machine = sloped_course(routes="both")
    os.makedirs(WORK_DIR, exist_ok=True)

    cfg = terrain.terrain_config()
    bundle = None
    if backdrop:
        bundle = sightlines.Bundle(
            sightlines.course_solids(machine, lambda x, z: terrain.height(x, z, cfg))
        )

    span = hook.field_span(replay, hook.LIVE_FROM)
    print(f"the field at replay {hook.LIVE_FROM}: 8 racers spanning {span:.2f} layout units")
    print(f"the shipped start lens frames {cameras.SECTIONS[1].extent:.1f} units, "
          f"which puts a racer at {hook.px_at_extent(cameras.SECTIONS[1].extent):.0f} px "
          "at the aim plane\n")

    reports: dict[str, Any] = {}
    for name, plan in variants(replay, machine, names):
        started = time.perf_counter()
        report = hook.hook_report(replay, machine, plan)
        track = report.pop("track")
        cameras.write_track(track, _track_path(name, seed))
        report["problems"] += [
            f"track: {line}" for line in cameras.check_track(track, replay)
        ]
        if bundle is not None:
            report["backdrop"] = hook.background_report(track, replay, bundle, cfg)
            # The bar is re-run now that the backdrop exists: `hook_report` is
            # given the geometry and cannot cast the rays itself.
            report["problems"] = hook.check_hook(
                report["frame_zero"], report["motion"], report["join"],
                backdrop=report["backdrop"],
            ) + [f"track: {line}" for line in cameras.check_track(track, replay)]
        report["elapsed"] = round(time.perf_counter() - started, 2)
        reports[name] = report
        _print_variant(name, report)

    print(f"\n-> {_save_reports(seed, reports)}")
    return reports


def _print_variant(name: str, report: dict[str, Any]) -> None:
    zero = report["frame_zero"]
    motion = report["motion"]
    join = report["join"]
    print(f"{name:10s} {report['note']}")
    print(f"    frame 0   {zero['racers']}/{zero['of']} racers   "
          f"median {zero['median_px']:.1f} px ({zero['min_px']:.0f}-{zero['max_px']:.0f})   "
          f"ink {zero['ink'] * 100:.2f}%   off-centre {zero['off_centre']:.2f}"
          f" (sideways {zero.get('off_centre_x', 0):.2f})")
    if zero.get("bbox_px"):
        margins = zero["margins"]
        print(f"              pack box {zero['bbox_px'][0]:.0f} x {zero['bbox_px'][1]:.0f} px "
              f"at ({zero['centroid'][0]:.0f}, {zero['centroid'][1]:.0f})   "
              f"closest pair {zero['min_separation']:.2f} diameters   "
              f"least-visible disc {zero.get('worst_disc', 0) * 100:.0f}%")
        print(f"              margins  L {margins['left']:.2f}  R {margins['right']:.2f}  "
              f"T {margins['top']:.2f}  B {margins['bottom']:.2f}")
    if report.get("backdrop"):
        back = report["backdrop"]
        print(f"    backdrop  racers {back['racer'] * 100:.1f}%   machine {back['machine'] * 100:.1f}%"
              f"   near ground {back['terrain_near'] * 100:.1f}%"
              f"   far {back['terrain_far'] * 100:.1f}%   sky {back['sky'] * 100:.1f}%"
              f"   -> subject {back['subject'] * 100:.1f}%  empty {back['empty'] * 100:.1f}%")
    if report.get("legibility"):
        legible = report["legibility"]
        lost = [row["id"] for row in legible["racers"] if not row["legible"]]
        print(f"    colour    {legible['legible']}/{legible['of']} racers show their own hue"
              + (f"   hidden: {lost}" if lost else ""))
    if report.get("text"):
        text = report["text"]
        print(f"    mark      baseline y {text['baseline']}   worst twelfth "
              f"{text['contrast']:.2f}:1   mean {text.get('mean_contrast', 0):.2f}:1"
              f"   cap {text['cap_px']:.0f} px"
              f" ({text['phone_cap_px']:.0f} px on a phone)")
    print(f"    motion    mechanism {_secs(motion['mechanism'])}   racers {_secs(motion['racers'])}"
          f"   camera {_secs(motion['camera'])}   (creep {motion['creep_px']:.2f} px/frame)")
    print(f"    handoff   lens {join['lens_step']:.4f} vs {join['largest_inside_lens']:.4f} inside"
          f"   aim {join['aim_step']:.4f}   fov {join['fov_step']:.2f} deg"
          f"   turn {report['hook']['bearing']:.0f} -> 194 deg over {report['hook']['seconds']:.2f} s")
    if report["problems"]:
        for line in report["problems"]:
            print(f"    FAIL      {line}")
    else:
        print("    PASS      every bar in check_hook")
    print()


def _report_path(seed: int) -> str:
    return os.path.join(WORK_DIR, f"hooks_{seed}.json")


def _load_reports(seed: int) -> dict[str, Any]:
    path = _report_path(seed)
    if not os.path.isfile(path):
        raise HookError(f"solve first: {path} is missing")
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _save_reports(seed: int, reports: dict[str, Any]) -> str:
    path = _report_path(seed)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(reports, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return path


def stage_measure(seed: int, names: Sequence[str] | None) -> None:
    """Fold the rendered first frame's own answers into the report.

    Two of the brief's questions cannot be answered from geometry, and the pass
    that tried found out the hard way: `sightlines` builds its occluders from
    colliders, and the board the eight racers sit against has none, so a ray to
    every racer's centre and rim came back clear on a framing whose render shows
    seven of the eight behind it. Both of these read the picture.
    """
    replay = _load_replay(seed)
    machine = sloped_course(routes="both")
    reports = _load_reports(seed)
    for name, plan in variants(replay, machine, names):
        if name not in reports:
            raise HookError(f"solve {name} first")
        image = _open_still(name, 0)
        report = reports[name]
        report["legibility"] = hook.legibility_report(image, report["frame_zero"])
        report["text"] = hook.text_plate(image, report["frame_zero"])
        # The same two questions at the size a feed asks them, which is the only
        # size the retention numbers were measured at.
        small = image.resize((hook.PHONE_WIDTH, hook.PHONE_HEIGHT))
        report["legibility_phone"] = hook.legibility_report(small, report["frame_zero"])
        report["problems"] = hook.check_hook(
            report["frame_zero"], report["motion"], report["join"],
            backdrop=report.get("backdrop"),
            legibility=report["legibility"], text=report["text"],
        ) + [line for line in report.get("problems", []) if line.startswith("track:")]
        _print_variant(name, report)
    print(f"-> {_save_reports(seed, reports)}")


def _secs(value: float | None) -> str:
    return "never" if value is None else f"{value:.3f} s"


# --- Godot ------------------------------------------------------------------


def find_godot(explicit: str | None) -> str:
    if explicit:
        if os.path.isfile(explicit):
            return explicit
        found = shutil.which(explicit)
        if found:
            return found
        raise HookError(f"--godot does not name an executable: {explicit}")
    for variable in ("GODOT_BIN", "GODOT4_BIN"):
        value = os.environ.get(variable)
        if value and os.path.isfile(value):
            return value
    for name in ("godot", "godot4"):
        found = shutil.which(name)
        if found:
            return found
    raise HookError(
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
        raise HookError(f"{label}: Godot exited {completed.returncode}\n{errors}")
    for line in (completed.stderr or "").splitlines():
        if "SCRIPT ERROR" in line or "Parse Error" in line:
            raise HookError(f"{label}: Godot reported an error: {line.strip()}")
    return elapsed


def _render_flags(seed: int, name: str, out_dir: str) -> list[str]:
    contract = os.path.join(OUT_DIR, f"start_contract_{seed}.json")
    flags = [
        f"--out-dir={os.path.abspath(out_dir)}",
        f"--replay={os.path.abspath(_replay_path(seed))}",
        f"--cameras={os.path.abspath(_track_path(name, seed))}",
        f"--fps={FPS}", f"--width={WIDTH}", f"--height={HEIGHT}",
        "--layout=b", "--detail=hero", "--routes=both",
    ]
    if os.path.isfile(contract):
        flags.append(f"--start-contract={os.path.abspath(contract)}")
    return flags


# --- the frame that is the product ------------------------------------------

# The output seconds every variant is stilled at. Zero is the product; the rest
# are the beats the brief names, so the sheet shows the premise arriving rather
# than only its first instant.
STILL_AT = (0.0, 0.117, 0.25, 0.5, 0.9, 1.3)


def stage_frames(seed: int, names: Sequence[str] | None, godot: str) -> None:
    replay = _load_replay(seed)
    machine = sloped_course(routes="both")
    for name, _plan in variants(replay, machine, names):
        track_path = _track_path(name, seed)
        if not os.path.isfile(track_path):
            raise HookError(f"solve first: {track_path} is missing")
        out = _still_dir(name)
        if os.path.isdir(out):
            shutil.rmtree(out)
        os.makedirs(out, exist_ok=True)
        at = ",".join(f"{value:.6f}" for value in STILL_AT)
        elapsed = run_godot(godot, [*_render_flags(seed, name, out), f"--at={at}"], name)
        written = sorted(f for f in os.listdir(out) if f.endswith(".png"))
        if not written:
            raise HookError(f"{name}: no stills were written")
        print(f"{name}: {len(written)} stills in {elapsed:.1f} s -> {out}")


def stage_render(seed: int, names: Sequence[str] | None, godot: str) -> None:
    replay = _load_replay(seed)
    machine = sloped_course(routes="both")
    for name, _plan in variants(replay, machine, names):
        track_path = _track_path(name, seed)
        if not os.path.isfile(track_path):
            raise HookError(f"solve first: {track_path} is missing")
        with open(track_path, "r", encoding="utf-8") as handle:
            duration = float(json.load(handle)["duration"])
        end = min(duration, PROOF_SECONDS)
        frames_dir = _frames_dir(name)
        if os.path.isdir(frames_dir):
            shutil.rmtree(frames_dir)
        os.makedirs(frames_dir, exist_ok=True)
        flags = [*_render_flags(seed, name, frames_dir), "--clip=1", f"--end={end:.6f}"]
        elapsed = run_godot(godot, flags, name)
        written = sorted(f for f in os.listdir(frames_dir) if f.endswith(".png"))
        if not written:
            raise HookError(f"{name}: no frames were written")
        print(f"{name}: {len(written)} frames in {elapsed:.1f} s "
              f"({elapsed / len(written) * 1000:.0f} ms/frame)")
        _encode(frames_dir, written, _clip_path(name))


def _encode(frames_dir: str, names: Sequence[str], video: str) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise HookError("ffmpeg is not on PATH; frames are rendered but not encoded")
    first = int(names[0].split("_")[1].split(".")[0])
    os.makedirs(os.path.dirname(os.path.abspath(video)) or ".", exist_ok=True)
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
        raise HookError(f"ffmpeg failed for {video}:\n{tail}")
    print(f"    -> {video} ({os.path.getsize(video) / 1e6:.1f} MB)")


# --- the boards -------------------------------------------------------------


def _open_still(name: str, index: int):
    from PIL import Image

    folder = _still_dir(name)
    if not os.path.isdir(folder):
        raise HookError(f"render the stills first: {folder} is missing")
    files = sorted(f for f in os.listdir(folder) if f.endswith(".png"))
    if index >= len(files):
        raise HookError(f"{name}: still {index} of {len(files)} is missing")
    return Image.open(os.path.join(folder, files[index])).convert("RGB")


def _label(image, text: str, size: int = 34):
    from PIL import ImageDraw

    from sloped import overlays

    draw = ImageDraw.Draw(image)
    font = overlays.load_font(size)
    box = draw.textbbox((0, 0), text, font=font)
    draw.rectangle([0, 0, box[2] + 18, box[3] + 16], fill=(18, 16, 14))
    draw.text((9, 6), text, font=font, fill=(255, 249, 238))
    return image


def stage_sheet(seed: int, names: Sequence[str] | None) -> None:
    from PIL import Image

    replay = _load_replay(seed)
    machine = sloped_course(routes="both")
    chosen = variants(replay, machine, names)
    reports = _load_reports(seed)
    os.makedirs(DOC_DIR, exist_ok=True)

    # 1. the first frames, full size, side by side with the mark on.
    marked: list[Any] = []
    plain: list[Any] = []
    for name, _plan in chosen:
        report = reports[name]
        frame = _open_still(name, 0)
        plain.append((name, frame.copy()))
        baseline = int(report.get("text", {}).get("baseline", 395))
        layer = hook.pick_a_color(baseline=baseline)
        composed = frame.convert("RGBA")
        composed.alpha_composite(layer)
        marked.append((name, composed.convert("RGB")))

    _board(marked, os.path.join(WORK_DIR, "first_frames.png"),
           scale=0.32, caption=lambda n: f"{n}  {reports[n]['frame_zero']['median_px']:.0f} px")
    _board(plain, os.path.join(WORK_DIR, "first_frames_plain.png"), scale=0.32,
           caption=lambda n: n)

    # 2. the phone board: the same first frames at the size a feed shows them.
    phone = [
        (name, image.resize(PHONE, Image.LANCZOS)) for name, image in marked
    ]
    _board(phone, os.path.join(WORK_DIR, "first_frames_phone.png"), scale=1.0,
           caption=lambda n: n, label_size=18, gap=12)
    phone_plain = [
        (name, image.resize(PHONE, Image.LANCZOS)) for name, image in plain
    ]
    _board(phone_plain, os.path.join(WORK_DIR, "first_frames_phone_plain.png"),
           scale=1.0, caption=lambda n: n, label_size=18, gap=12)

    # 3. one motion strip per variant, at phone size, so the first half second
    #    can be read as a sequence rather than described.
    for name, _plan in chosen:
        strip = [
            (f"{value:.3f}s", _open_still(name, index).resize(PHONE, Image.LANCZOS))
            for index, value in enumerate(STILL_AT)
        ]
        _board(strip, os.path.join(WORK_DIR, f"motion_{name}.png"), scale=1.0,
               caption=lambda n: n, label_size=18, gap=12)

    for leaf in ("first_frames.png", "first_frames_plain.png",
                 "first_frames_phone.png", "first_frames_phone_plain.png"):
        shutil.copyfile(os.path.join(WORK_DIR, leaf), os.path.join(DOC_DIR, leaf))
    for name, _plan in chosen:
        leaf = f"motion_{name}.png"
        shutil.copyfile(os.path.join(WORK_DIR, leaf), os.path.join(DOC_DIR, leaf))
    print(f"-> {DOC_DIR}")


def _board(items, path: str, scale: float, caption, label_size: int = 34,
           gap: int = 24) -> None:
    from PIL import Image

    tiles = []
    for name, image in items:
        if scale != 1.0:
            image = image.resize(
                (int(image.width * scale), int(image.height * scale)), Image.LANCZOS
            )
        tiles.append(_label(image.copy(), caption(name), label_size))
    width = sum(tile.width for tile in tiles) + gap * (len(tiles) + 1)
    height = max(tile.height for tile in tiles) + gap * 2
    board = Image.new("RGB", (width, height), (10, 9, 8))
    cursor = gap
    for tile in tiles:
        board.paste(tile, (cursor, gap))
        cursor += tile.width + gap
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    board.save(path)
    print(f"    -> {path}  ({board.width}x{board.height})")


# --- the table --------------------------------------------------------------


def stage_report(seed: int) -> None:
    reports = _load_reports(seed)
    lines = [
        "| variant | racers | in own colour | median px | ink | off-centre | closest pair | least disc "
        "| machine | empty | mark | mechanism | racers move | handoff |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, report in reports.items():
        zero, motion, join = report["frame_zero"], report["motion"], report["join"]
        back = report.get("backdrop", {})
        legible = report.get("legibility", {})
        text = report.get("text", {})
        lines.append(
            f"| `{name}` | {zero['racers']}/{zero['of']} | "
            f"{legible.get('legible', 0)}/{legible.get('of', 8)} | "
            f"{zero['median_px']:.0f} | "
            f"{zero['ink'] * 100:.2f}% | {zero['off_centre']:.2f} | "
            f"{zero.get('min_separation', 0):.2f} | "
            f"{zero.get('worst_disc', 0) * 100:.0f}% | "
            f"{back.get('machine', 0) * 100:.0f}% | {back.get('empty', 0) * 100:.0f}% | "
            f"{text.get('contrast', 0):.1f}:1 | "
            f"{_secs(motion['mechanism'])} | {_secs(motion['racers'])} | "
            f"{join['lens_step']:.3f} |"
        )
    table = "\n".join(lines)
    print(table)
    out = os.path.join(WORK_DIR, f"hooks_{seed}.md")
    with open(out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(table + "\n")
    print(f"\n-> {out}")


# --- the search -------------------------------------------------------------
#
# **Every candidate rides on its own replay frame, and there is a ceiling on how
# many.** The renderer walks output time and maps it to replay time with slope
# one, so a sheet of N poses is N consecutive replay frames however little the
# camera has to do with them. That is only free while the machine is holding
# still, which here is replay 0.083 to 0.300 - after the solver has settled the
# field into its bays and before the release paddles stir at 0.3167. Fourteen
# frames.
GRID_BASE = 0.083333
GRID_MAX = 14


def _grid_axes(spec: str) -> dict[str, list[float]]:
    axes: dict[str, list[float]] = {}
    for part in spec.split(":"):
        if not part.strip():
            continue
        name, _, values = part.partition("=")
        axes[name.strip()] = [float(value) for value in values.split(",") if value]
    for name in ("bearing", "elevation", "extent", "pan"):
        axes.setdefault(name, [0.0] if name == "pan" else [])
        if not axes[name]:
            raise HookError(f"--grid needs a {name} list")
    return axes


def stage_grid(seed: int, spec: str, label: str, godot: str) -> None:
    """Render and score a product of framings, in one Godot launch.

    This is the stage the three variants were chosen out of, kept so the choice
    can be re-run rather than only asserted. It answers the one question the
    geometry cannot: whether each racer's own colour survives the machine
    standing in front of it.
    """
    from dataclasses import replace as _replace

    from PIL import Image, ImageDraw

    replay = _load_replay(seed)
    machine = sloped_course(routes="both")
    axes = _grid_axes(spec)
    cells = [
        (bearing, elevation, extent, pan)
        for bearing in axes["bearing"]
        for elevation in axes["elevation"]
        for extent in axes["extent"]
        for pan in axes["pan"]
    ]
    if len(cells) > GRID_MAX:
        raise HookError(
            f"{len(cells)} framings, and only {GRID_MAX} replay frames hold the "
            "machine still. Split the sweep.")

    folder = os.path.join(WORK_DIR, "grid", label)
    os.makedirs(folder, exist_ok=True)
    plans, cuts, edit = [], [], []
    cursor = 0.0
    for index, (bearing, elevation, extent, pan) in enumerate(cells):
        when = round(GRID_BASE + index / FPS, 6)
        plan = _replace(
            hook.HOOKS["a_rear"],
            name=f"b{bearing:.0f}e{elevation:.0f}x{extent:.1f}p{pan:+.1f}",
            bearing=bearing, elevation=elevation, extent=extent, aim_pan=pan,
            opens_at=when, seconds=1.0,
        )
        plans.append(plan)
        # Only the hook's own first row is wanted, held for one output frame.
        row = hook.build_hook_track(replay, machine, plan)["cuts"][0]["frames"][0]
        after = round(when + 1.0 / FPS, 6)
        cuts.append({
            "name": plan.name, "until": plan.name, "fov": row[7],
            "extent": extent, "elevation": elevation, "bearing": bearing,
            "target": "node", "band": 60.0, "node": "start", "side": 0,
            "fixed_heading": True, "heading_run": "",
            "from": when, "to": after, "distance": 0.0, "fastest_racer": 0.0,
            "subject": list(range(8)), "lift_deg": 0.0, "min_clearance": 0.0,
            "frames": [row, [after, *row[1:]]],
        })
        edit.append({"cut": plan.name, "out": [round(cursor, 6),
                                               round(cursor + 1.0 / FPS, 6)],
                     "replay": [when, after]})
        cursor = round(cursor + 1.0 / FPS, 6)

    track = {"units": "layout", "fps": FPS, "seed": replay["seed"], "edited": True,
             "duration": round(cursor, 6),
             "replay_duration": float(replay["frames"][-1]["t"]),
             "omitted": 0.0, "last_crossing": 0.0, "edit": edit, "cuts": cuts}
    track_path = cameras.write_track(track, os.path.join(folder, "grid.json"))

    frames_dir = os.path.join(folder, "frames")
    if os.path.isdir(frames_dir):
        shutil.rmtree(frames_dir)
    os.makedirs(frames_dir)
    # **The middle of each window, not its edge.** `sloped_race_scene.replay_at`
    # matches on `out_seconds <= high`, so an output second sitting exactly on a
    # boundary resolves to the window *before* it and every tile but the first
    # renders the candidate before the one it is labelled with. That produced a
    # legibility sweep reading 8, 1, 2, 2, 2, 3, 0, 4, 4, 1, 6, 6 across a smooth
    # change of elevation; sampled at the middle the same sweep is twelve eights.
    at = ",".join(f"{(index + 0.5) / FPS:.6f}" for index in range(len(cells)))
    flags = [
        f"--out-dir={os.path.abspath(frames_dir)}",
        f"--replay={os.path.abspath(_replay_path(seed))}",
        f"--cameras={os.path.abspath(track_path)}",
        f"--at={at}", f"--fps={FPS}", f"--width={WIDTH}", f"--height={HEIGHT}",
        "--layout=b", "--detail=hero", "--routes=both",
    ]
    contract = os.path.join(OUT_DIR, f"start_contract_{seed}.json")
    if os.path.isfile(contract):
        flags.append(f"--start-contract={os.path.abspath(contract)}")
    elapsed = run_godot(godot, flags, label)
    files = sorted(f for f in os.listdir(frames_dir) if f.endswith(".png"))
    if len(files) != len(cells):
        raise HookError(f"{label}: {len(files)} frames for {len(cells)} framings")
    print(f"{label}: {len(files)} framings in {elapsed:.1f} s")

    columns = min(7, len(files))
    rows = (len(files) + columns - 1) // columns
    tile = (230, 409)
    board = Image.new("RGB", (columns * (tile[0] + 8) + 8,
                              rows * (tile[1] + 30) + 8), (10, 9, 8))
    draw = ImageDraw.Draw(board)
    font = __import__("sloped.overlays", fromlist=["load_font"]).load_font(17)
    # Scored at the delivery **and** at 270x480, because the two disagree and
    # the smaller one is the size the retention numbers were taken at: measured
    # on the rear framing, the yellow racer's disc reads 29.2 degrees off its own
    # hue at 1080x1920 - one degree inside the bar - and 131.4 degrees off at a
    # quarter of that, where the downsample mixes it with the stanchion it is
    # half behind.
    print(f"{'framing':28}{'clr':>4}{'ph':>4}{'n':>3}{'px':>6}{'disc':>6}{'off':>6}{'ink':>7}")
    for index, (plan, leaf) in enumerate(zip(plans, files)):
        solved = hook.build_hook_track(replay, machine, plan)
        zero = hook.first_frame_report(solved, replay)
        image = Image.open(os.path.join(frames_dir, leaf)).convert("RGB")
        legible = hook.legibility_report(image, zero)
        phone = hook.legibility_report(
            image.resize((hook.PHONE_WIDTH, hook.PHONE_HEIGHT), Image.LANCZOS), zero)
        line = (f"{plan.name} L{legible['legible']}/{phone['legible']} "
                f"n{zero['racers']} {zero['median_px']:.0f}px")
        print(f"{plan.name:28}{legible['legible']:4d}{phone['legible']:4d}{zero['racers']:3d}"
              f"{zero['median_px']:6.0f}{zero.get('worst_disc', 0):6.2f}"
              f"{zero['off_centre']:6.2f}{zero['ink'] * 100:6.2f}%")
        x = 8 + (index % columns) * (tile[0] + 8)
        y = 8 + (index // columns) * (tile[1] + 30)
        board.paste(image.resize(tile, Image.LANCZOS), (x, y))
        draw.text((x + 3, y + tile[1] + 5), line, font=font, fill=(255, 240, 220))
    out = os.path.join(WORK_DIR, f"grid_{label}.png")
    board.save(out)
    print(f"    -> {out}")
    os.makedirs(DOC_DIR, exist_ok=True)
    shutil.copyfile(out, os.path.join(DOC_DIR, f"grid_{label}.png"))


# --- entry ------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", default="all",
                        choices=("solve", "frames", "measure", "render",
                                 "sheet", "report", "all", "grid"))
    parser.add_argument("--seed", type=int, default=5432)
    parser.add_argument("--variants", default="")
    parser.add_argument("--godot", default=None)
    parser.add_argument("--grid", default="bearing=184,194,204:elevation=26:"
                                       "extent=8.2:pan=-0.6,-0.2,0.2,0.6",
                        help="axes for --stage grid, as name=v,v,v separated by ':'")
    parser.add_argument("--grid-name", default="grid")
    parser.add_argument("--no-backdrop", action="store_true",
                        help="skip the ray-cast backdrop classification, which is "
                             "the slow part of solving")
    args = parser.parse_args(argv)
    names = [value for value in args.variants.split(",") if value] or None

    try:
        if args.stage in ("solve", "all"):
            stage_solve(args.seed, names, backdrop=not args.no_backdrop)
        if args.stage in ("frames", "all"):
            stage_frames(args.seed, names, find_godot(args.godot))
        if args.stage in ("measure", "all"):
            stage_measure(args.seed, names)
        if args.stage in ("render", "all"):
            stage_render(args.seed, names, find_godot(args.godot))
        if args.stage in ("sheet", "all"):
            stage_sheet(args.seed, names)
        if args.stage in ("report", "all"):
            stage_report(args.seed)
        if args.stage == "grid":
            stage_grid(args.seed, args.grid, args.grid_name, find_godot(args.godot))
    except HookError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

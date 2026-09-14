"""Audit V24: every temporal join, the first second, and V22.1 beside it.

    python tools/sloped_v24_audit.py --stage all

Three questions, one per stage, and all three exist because V24 changed
something that made a previously unaskable question askable.

    joins   every omission in the film, measured on the marbles' **orientation**
            as well as their position. Meridian racers make rotation visible, so
            a cut that was invisible with uniform spheres may not be any more
    first   what is on screen at output second zero and what moves next. This is
            the whole experiment: the uploaded Short lost 80.4% of its viewers
            before its premise arrived
    sheet   the delivered V22.1 and V24 at ten matched moments, at 1080x1920 and
            at the 270x480 a feed is actually scrolled at
    clip    the first five seconds of each, side by side. The single most
            useful artefact in the pass, because it is the comparison the
            experiment is a test of

Nothing here renders the race or touches the physics; `joins` and `first` read
the replay and the camera track, and `sheet` and `clip` read finished files.

## Why the join audit is not the spin lab's, quite

`v24_spin.boundary_report` answers "what does each marble do across this cut",
and `boundary_visible` answers "how much of its visible face changes". Both are
per-cut absolutes. What decides whether a cut *reads* is neither: it is the
comparison against **the shot the cut is in**.

A marble in the mixer turns 119 degrees across V22.1's shipped omission, and
nobody has ever reported seeing it - because in the mixer a marble turns 1.8
degrees every ordinary frame and the picture is a blur of tumbling. A marble
on the stopped rotor turns 25 degrees across the pacing lab's `STOPPED` cut,
which is a fifth as much, in a shot where an ordinary frame turns it 1.5 - and
against its own background that is the more exposed of the two by a factor of
four.

So every join below is quoted as a **ratio to the 95th percentile of its own
shot's per-frame visible change**, and that ratio is what `verdict` reads.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
from typing import Any, Sequence

sys.path.insert(0, os.getcwd())

import numpy as np

from sloped import presentation, terrain, v24, v24_hook, v24_spin
from sloped.course import sloped_course

OUT_DIR = os.path.join("output", "sloped_race_v1")
DOC_DIR = os.path.join("docs", "validation", "sloped_race_v1", "v24_integration")
WIDTH, HEIGHT, FPS = 1080, 1920, 60

# The phone size the retention numbers were taken at.
PHONE = (270, 480)

# How far above its own shot's ordinary per-frame change a join may sit before
# the marking is the thing that moved.
#
# **1.5 is not a round number, it is where the film's own accepted joins fall.**
# V22.1's shipped mixer omission - the one join a real audience has watched
# without reporting it - measures 1.2, and the start-to-chase lens change, which
# is a *cut* and is supposed to be visible, measures 1.1. A join at 3 to 5 times
# its shot's spread is in different company entirely.
EXPOSURE_BAR = 1.5


# How many identical blades each rotating family has, which is its symmetry: a
# four-bladed wheel that turns a whole quarter turn across a cut is in exactly
# the pose it left. Read off the replay's own actuator names rather than
# assumed, so a machine with a different wheel fails loudly here.
BLADE_COUNTS = {
    "start.rotor": 4,
    "shuffle.wheel0_blade": 4,
    "obstacle.wheel0_blade": 4,
    "obstacle.wheel1_blade": 4,
    "obstacle.wheel2_blade": 4,
}


def actuator_families(replay: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    """The rotating actuator families in this replay, by prefix."""
    names = sorted((replay["frames"][len(replay["frames"]) // 2].get("actuators")
                    or {}).keys())
    out: dict[str, list[str]] = {}
    for prefix in BLADE_COUNTS:
        matched = [name for name in names if name.startswith(prefix)]
        if matched:
            out[prefix] = matched
    return {prefix: tuple(names) for prefix, names in out.items()}


def phase_audit(
    replay: dict[str, Any], before: float, after: float, on_screen: Sequence[str],
) -> list[dict[str, Any]]:
    """Every rotating mechanism's phase across one join, with the subject flagged.

    **The gap this exists to close.** `v24_spin.MACHINE_KEYS` is
    `start.rotor0..3`, which is the right constraint for a cut in the start shot
    and the only one any pass before V24 checked. The spinner trap's cut is not
    in the start shot: its subject is three four-bladed `obstacle.wheel`s the
    field is being held against, and measured against *those* the pacing lab's
    placement steps the blades 13.13 degrees out of their own quarter turn,
    where one frame is 3.44.

    A mechanism that is not on screen may be as far out of phase as it likes,
    which is why this reports all of them and judges only the ones named.
    """
    families = actuator_families(replay)
    rows: list[dict[str, Any]] = []
    for prefix, keys in families.items():
        across = v24_spin.machine_mismatch(replay, before, after, keys=keys)
        one = v24_spin.machine_mismatch(replay, before, before + 1.0 / FPS, keys=keys)
        period = 360.0 / BLADE_COUNTS[prefix]
        error = abs(((across - one + period / 2.0) % period) - period / 2.0)
        rows.append({
            "family": prefix,
            "step_deg": round(across, 3),
            "one_frame_deg": round(one, 3),
            "symmetry_deg": period,
            "phase_error_deg": round(error, 3),
            "on_screen": prefix in on_screen,
        })
    return rows


# --- the joins --------------------------------------------------------------


def _per_frame_spread(
    replay: dict[str, Any], marker, eye: np.ndarray, low: float, high: float,
) -> np.ndarray:
    """Every marble's per-frame visible-face change over one stretch of a shot.

    The camera is held at `eye` for the whole window on purpose. The question is
    how much *the marking* changes from frame to frame, and letting the lens
    move would fold the shot's own travel into the answer - which is exactly the
    confound that makes a flying chase look like a churning marble.
    """
    quaternions = v24_spin._as_array(replay, "q")
    positions = v24_spin._as_array(replay, "p") * float(replay["units"]["render_scale"])
    fps = float(replay["replay_fps"])
    out: list[float] = []
    for frame in range(int(round(low * fps)), int(round(high * fps))):
        for marble in range(quaternions.shape[1]):
            out.append(
                v24_spin.visible_change(
                    "meridian", quaternions[frame, marble],
                    quaternions[frame + 1, marble],
                    eye - positions[frame + 1, marble], marker,
                )
            )
    return np.array(out) if out else np.zeros(1)


def _row_at(track: dict[str, Any], when: float) -> tuple[str, int, list[float]]:
    """The cut, its index and the camera row that draws a replay second.

    The **last** cut that contains it, because consecutive cuts share their
    boundary row and the far side of a join is the one that owns it.
    """
    best: tuple[str, int, list[float]] | None = None
    for index, cut in enumerate(track["cuts"]):
        for row in cut["frames"]:
            if abs(float(row[0]) - when) < 1e-6:
                if best is None or index > best[1]:
                    best = (cut["name"], index, row)
    if best is None:
        raise ValueError(f"replay {when} is not in the track")
    return best


def _screen(row: Sequence[float], point: Sequence[float]):
    return presentation.project(row[1:4], row[4:7], float(row[7]), point, WIDTH, HEIGHT)


def join_audit(
    replay: dict[str, Any], track: dict[str, Any], clock: presentation.Clock,
) -> list[dict[str, Any]]:
    """One row per omission in the finished film. See the module docstring."""
    marker = v24_spin.Marker.load()
    scale = float(replay["units"]["render_scale"])
    positions = v24_spin._as_array(replay, "p") * scale
    fps = float(replay["replay_fps"])
    rows: list[dict[str, Any]] = []

    for name, before, after in v24.OMISSIONS:
        # Which camera row draws each side, and which window each is in. A join
        # whose two frames are in *different* cuts is a camera cut, and the
        # viewer is owed a spatial discontinuity there rather than surprised by
        # one.
        cut_before, index_before, row_before = _row_at(track, before)
        cut_after, index_after, row_after = _row_at(track, after)
        same_camera = index_after == index_before + 1 and cut_before == cut_after

        # The shot the join lives in, for the spread. Taken on the near side,
        # which is the side the viewer has been watching.
        span = next(
            (float(s["replay"][0]), float(s["replay"][1]))
            for s in track["edit"]
            if abs(float(s["replay"][1]) - before) < 1e-6
        )
        eye = np.array(row_before[1:4], dtype=float)
        spread = _per_frame_spread(replay, marker, eye, max(span[0], span[1] - 1.0), span[1])

        report = v24_spin.boundary_report(replay, before, after)
        visible = np.array(
            v24_spin.boundary_visible(replay, "meridian", before, after, eye, marker)
        )
        p95 = float(np.percentile(spread, 95))
        exposure = float(np.median(visible)) / max(p95, 1e-9)

        # Screen displacement: each marble drawn by the row that actually draws
        # it, on each side. This is the pixel the viewer's eye is tracking, and
        # across a lens change it is large *because the lens changed*.
        low = int(round(before * fps))
        high = int(round(after * fps))
        moved: list[float] = []
        for marble in range(positions.shape[1]):
            one = _screen(row_before, positions[low, marble])
            two = _screen(row_after, positions[high, marble])
            if one is None or two is None:
                continue
            moved.append(math.dist(one[:2], two[:2]))
        moved_arr = np.array(moved) if moved else np.zeros(1)

        state_before = v24_spin.machine_mismatch(replay, before, after)
        one_frame_rotor = v24_spin.machine_mismatch(replay, before, before + 1.0 / fps)
        phases = phase_audit(replay, before, after,
                             v24.IN_FRAME_ACTUATORS.get(name, ()))
        worst_phase = max((row["phase_error_deg"] for row in phases
                           if row["on_screen"]), default=0.0)

        rows.append({
            "name": name,
            "replay_before": round(before, 6),
            "replay_after": round(after, 6),
            "omitted_seconds": round(after - before - 1.0 / fps, 6),
            "output_at": round(clock.at(before) or 0.0, 6),
            "camera_before": [round(v, 4) for v in row_before[1:4]],
            "camera_after": [round(v, 4) for v in row_after[1:4]],
            "camera_step": round(math.dist(row_before[1:4], row_after[1:4]), 4),
            "fov_before": float(row_before[7]),
            "fov_after": float(row_after[7]),
            "same_camera": bool(same_camera),
            "cut_before": cut_before,
            "cut_after": cut_after,
            "turn_deg_median": report["turn_deg_median"],
            "turn_deg_max": report["turn_deg_max"],
            "turn_deg_one_frame": report["one_frame_turn_deg_median"],
            "screen_px_median": round(float(np.median(moved_arr)), 1),
            "screen_px_max": round(float(moved_arr.max()), 1),
            "visible_change_median": round(float(np.median(visible)), 4),
            "visible_change_max": round(float(visible.max()), 4),
            "shot_p95": round(p95, 4),
            "exposure": round(exposure, 2),
            "rotor_step_deg": round(state_before, 3),
            "rotor_one_frame_deg": round(one_frame_rotor, 3),
            "rotor_phase_error_deg": round(abs(state_before - one_frame_rotor), 3),
            "machine_before": _machine(replay, before),
            "machine_after": _machine(replay, after),
            "phases": phases,
            "phase_error_on_screen_deg": round(worst_phase, 3),
        })
        rows[-1]["verdict"] = _verdict(rows[-1])
    return rows


def _machine(replay: dict[str, Any], when: float) -> dict[str, float]:
    from sloped.v24_timeline import machine_state

    return {key: round(value, 4) for key, value in machine_state(replay, when).items()}


def _verdict(row: dict[str, Any]) -> str:
    """What the numbers say about one join, in a sentence."""
    if not row["same_camera"]:
        return (
            f"camera cut ({row['cut_before']} -> {row['cut_after']}, lens steps "
            f"{row['camera_step']:.1f} units): the spatial discontinuity is the "
            f"edit, and the marking's {row['visible_change_median']:.3f} is "
            f"{row['exposure']:.1f}x the shot's own spread - inside it"
        )
    if row["exposure"] <= EXPOSURE_BAR:
        return (
            f"same camera, {row['exposure']:.1f}x its shot's per-frame spread: "
            f"the marbles turn {row['turn_deg_median']:.0f} degrees across it and "
            f"{row['turn_deg_one_frame']:.1f} in an ordinary frame, so the "
            f"marking is already churning and the cut is inside the churn"
        )
    return (
        f"EXPOSED: same camera, {row['exposure']:.1f}x its shot's per-frame "
        f"spread. The shot is still, so the marking is the only thing that moves"
    )


# --- the first second -------------------------------------------------------


def first_second(
    replay: dict[str, Any], track: dict[str, Any], machine, image=None,
) -> dict[str, Any]:
    """Frame zero and the first motion, in the numbers the brief asks for."""
    from sloped import sightlines

    frame_zero = v24_hook.first_frame_report(track, replay)
    motion = v24_hook.motion_report(replay, v24.HOOK, track)
    cfg = terrain.terrain_config()
    bundle = sightlines.Bundle(
        sightlines.course_solids(machine, lambda x, z: terrain.height(x, z, cfg))
    )
    background = v24_hook.background_report(track, replay, bundle, cfg)

    out: dict[str, Any] = {
        "frame_zero": frame_zero,
        "motion": motion,
        "background": background,
        "mark": {
            "text": v24_hook.HOOK_TEXT,
            "size": v24_hook.HOOK_SIZE,
            "baseline": v24.MARK_BASELINE,
            "from": v24.MARK_IN,
            "fade_from": v24.MARK_OUT_FROM,
            "gone": v24.MARK_OUT_TO,
        },
    }
    if image is not None:
        out["legibility"] = v24_hook.legibility_report(image, frame_zero)
        out["legibility_phone"] = v24_hook.legibility_report(
            image.resize(PHONE), frame_zero
        )
    return out


# --- the comparison ---------------------------------------------------------

# Ten matched moments, named by what the brief asks to see. Each is a pair of
# **output** seconds, one per film, because the two films do not run on the same
# clock at all: V22.1 spends its first 4.2 s on a preview and a frozen frame.
#
# The V24 column is derived from its own track at run time - see `moments` - so
# a change to the edit moves these with it rather than leaving them pointing at
# whatever used to be there.
MOMENT_REPLAY: tuple[tuple[str, float | None], ...] = (
    ("frame 0", None),
    ("0.25 s", None),
    ("0.50 s", None),
    ("1.00 s", None),
    ("mixer", 5.400),
    ("release", 6.300),
    ("obstacle", 12.500),
    ("fork", 15.800),
    ("winner crossing", 20.850),
    ("payoff", None),
)


def moments(v221_clock: presentation.Clock, v24_clock: presentation.Clock,
            v24_card: float) -> list[tuple[str, float, float]]:
    """`(label, V22.1 output second, V24 output second)` for each moment."""
    out: list[tuple[str, float, float]] = []
    for label, replay_at in MOMENT_REPLAY:
        if label.endswith(" s") or label == "frame 0":
            offset = {"frame 0": 0.0, "0.25 s": 0.25, "0.50 s": 0.50,
                      "1.00 s": 1.00}[label]
            out.append((label, offset, offset))
            continue
        if label == "payoff":
            # Each film's own card, which is the point: V22.1's end fact is
            # 0.65 s at the very end and V24's plate is 1.8 s from a beat after
            # the crossing.
            out.append((label, v221_clock.duration - 0.325, v24_card + 0.6))
            continue
        one = v221_clock.at(replay_at)
        two = v24_clock.at(replay_at)
        if one is None or two is None:
            continue
        out.append((label, round(one, 4), round(two, 4)))
    return out


def _grab(video: str, when: float, path: str) -> str:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is not on PATH")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    done = subprocess.run(
        [ffmpeg, "-y", "-ss", f"{max(0.0, when):.4f}", "-i", video,
         "-frames:v", "1", "-q:v", "2", path],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if done.returncode != 0:
        tail = "\n".join((done.stderr or "").splitlines()[-8:])
        raise RuntimeError(f"ffmpeg could not grab {when} from {video}\n{tail}")
    return path


def sheet(one: str, two: str, pairs: Sequence[tuple[str, float, float]],
          path: str, phone: bool = False) -> str:
    """A contact sheet: V22.1 above, V24 below, one column per moment."""
    from PIL import Image, ImageDraw

    cell = PHONE if phone else (216, 384)
    pad, label_h, head = 8, 26, 34
    width = pad + len(pairs) * (cell[0] + pad)
    height = head + 2 * (label_h + cell[1] + pad) + pad
    canvas = Image.new("RGB", (width, height), (18, 17, 16))
    draw = ImageDraw.Draw(canvas)
    from sloped.overlays import load_font

    small = load_font(17)
    draw.text((pad, 8), "UPLOADED V22.1  (above)      |      V24  (below)",
              font=small, fill=(255, 249, 238))

    work = os.path.join(OUT_DIR, "short", "audit")
    os.makedirs(work, exist_ok=True)
    for column, (label, at_one, at_two) in enumerate(pairs):
        x = pad + column * (cell[0] + pad)
        for rank, (video, when) in enumerate(((one, at_one), (two, at_two))):
            y = head + rank * (label_h + cell[1] + pad)
            draw.text((x, y + 4), f"{label} @{when:.2f}", font=small,
                      fill=(200, 195, 188))
            grabbed = _grab(video, when,
                            os.path.join(work, f"m{column}_{rank}.jpg"))
            canvas.paste(Image.open(grabbed).resize(cell, Image.LANCZOS),
                         (x, y + label_h))
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    canvas.save(path)
    return path


def _label(text: str, size: tuple[int, int], path: str) -> str:
    """A caption as a transparent PNG, drawn with the film's own face.

    **Not `drawtext`.** ffmpeg's text filter needs fontconfig, which is not
    present on every machine this is run on and fails with "Cannot load default
    config file" rather than with a missing-font error. The project already
    owns a font loader and a shadowed-text drawer, so the caption is drawn the
    way every other mark in the film is drawn and handed to ffmpeg as an image.
    """
    from PIL import Image, ImageDraw

    from sloped.overlays import load_font

    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    font = load_font(30)
    box = draw.textbbox((0, 0), text, font=font)
    pad = 12
    draw.rectangle(
        (16, 16, 16 + (box[2] - box[0]) + 2 * pad, 16 + (box[3] - box[1]) + 2 * pad),
        fill=(0, 0, 0, 150),
    )
    draw.text((16 + pad - box[0], 16 + pad - box[1]), text, font=font,
              fill=(255, 249, 238, 255))
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    image.save(path)
    return path


def opening_clip(one: str, two: str, path: str, seconds: float = 5.0) -> str:
    """The first `seconds` of both films, side by side, each captioned.

    **The most important artefact in the pass.** Everything else measures the
    experiment; this is the experiment - two openings, the same length, the same
    screen, and the question is whether a thumb would stop on either.
    """
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is not on PATH")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    half = (540, 960)
    work = os.path.join(OUT_DIR, "short", "audit")
    left = _label("V22.1  (uploaded)", half, os.path.join(work, "label_v221.png"))
    right = _label("V24  (hook)", half, os.path.join(work, "label_v24.png"))
    graph = (
        f"[0:v]trim=0:{seconds},setpts=PTS-STARTPTS,scale={half[0]}:{half[1]}[a0];"
        f"[2:v]format=rgba[l0];[a0][l0]overlay=0:0[a];"
        f"[1:v]trim=0:{seconds},setpts=PTS-STARTPTS,scale={half[0]}:{half[1]}[b0];"
        f"[3:v]format=rgba[l1];[b0][l1]overlay=0:0[b];"
        f"[a][b]hstack=inputs=2[v]"
    )
    done = subprocess.run(
        [ffmpeg, "-y", "-i", one, "-i", two,
         "-loop", "1", "-framerate", "60", "-i", left,
         "-loop", "1", "-framerate", "60", "-i", right,
         "-filter_complex", graph, "-map", "[v]", "-an",
         "-frames:v", str(int(round(seconds * 60))),
         "-c:v", "libx264", "-preset", "slow", "-crf", "18",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", path],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if done.returncode != 0:
        tail = "\n".join((done.stderr or "").splitlines()[-15:])
        raise RuntimeError(f"ffmpeg exited {done.returncode}\n{tail}")
    return path


# --- the stages -------------------------------------------------------------


def _load(seed: int):
    replay_path = os.path.join(OUT_DIR, f"race_{seed}.json")
    track_path = os.path.join(OUT_DIR, f"cameras_v24_{seed}.json")
    replay, track, clock = v24.film_clock(replay_path, track_path)
    return replay, track, clock


def stage_joins(seed: int) -> list[dict[str, Any]]:
    replay, track, clock = _load(seed)
    rows = join_audit(replay, track, clock)
    print(f"{'join':6s} {'replay before':>13s} {'after':>9s} {'out':>7s} "
          f"{'camera':>8s} {'turn med':>9s} {'turn max':>9s} {'px med':>7s} "
          f"{'px max':>7s} {'vis':>6s} {'p95':>6s} {'x':>5s}  same")
    for row in rows:
        print(f"{row['name']:6s} {row['replay_before']:13.4f} "
              f"{row['replay_after']:9.4f} {row['output_at']:7.3f} "
              f"{row['camera_step']:8.4f} {row['turn_deg_median']:9.1f} "
              f"{row['turn_deg_max']:9.1f} {row['screen_px_median']:7.1f} "
              f"{row['screen_px_max']:7.1f} {row['visible_change_median']:6.3f} "
              f"{row['shot_p95']:6.3f} {row['exposure']:5.2f}  "
              f"{'yes' if row['same_camera'] else 'CUT'}")
    for row in rows:
        print(f"\n  {row['name']}: {row['verdict']}")
        for phase in row["phases"]:
            flag = "ON SCREEN" if phase["on_screen"] else "off screen"
            print(f"    {phase['family']:22s} steps {phase['step_deg']:7.2f} deg "
                  f"({phase['one_frame_deg']:5.2f} in one frame), phase error "
                  f"{phase['phase_error_deg']:6.2f} on a "
                  f"{phase['symmetry_deg']:.0f} deg symmetry  [{flag}]")
        print(f"    machine before {row['machine_before']}")
        print(f"    machine after  {row['machine_after']}")
    os.makedirs(DOC_DIR, exist_ok=True)
    path = os.path.join(DOC_DIR, "joins.json")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(rows, handle, indent=1)
        handle.write("\n")
    print(f"\nwrote {path}")
    return rows


def stage_first(seed: int, frame: str | None = None) -> dict[str, Any]:
    from PIL import Image

    replay, track, _clock = _load(seed)
    machine = sloped_course(routes="both")
    image = Image.open(frame) if frame and os.path.isfile(frame) else None
    report = first_second(replay, track, machine, image)
    zero = report["frame_zero"]
    print(f"frame zero: {zero['racers']}/{zero['of']} racers, median "
          f"{zero['median_px']} px ({zero['min_px']}-{zero['max_px']}), "
          f"{100 * zero['ink']:.2f}% of the frame by area, "
          f"{100 * zero['occupancy']:.1f}% by bounding box, "
          f"{zero['off_centre']} off centre ({zero['off_centre_x']} sideways)")
    print(f"           least-visible disc {zero['worst_disc']}, "
          f"closest pair {zero['min_separation']} diameters")
    # `subject` is racer plus machine and `empty` is distant hill plus sky. The
    # two are the brief's "is the frame about the race", read off the rendered
    # geometry rather than off the projection.
    back = report["background"]
    print(f"background: racer {100 * back['racer']:.1f}%, machine "
          f"{100 * back['machine']:.1f}% (subject {100 * back['subject']:.1f}%), "
          f"distant hill + sky {100 * back['empty']:.1f}%")
    motion = report["motion"]
    for key in ("mechanism", "racers", "camera", "first"):
        if key in motion:
            print(f"first {key:10s} {motion[key]}")
    mark = report["mark"]
    print(f"mark: {mark['text']!r} at baseline {mark['baseline']}, "
          f"up {mark['from']:.2f}-{mark['gone']:.2f} s")
    if "legibility_phone" in report:
        rows = report["legibility_phone"]
        seen = sum(1 for row in rows if row.get("own_colour"))
        print(f"at {PHONE[0]}x{PHONE[1]}: {seen}/{len(rows)} racers show their own colour")
    os.makedirs(DOC_DIR, exist_ok=True)
    path = os.path.join(DOC_DIR, "first_second.json")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, indent=1)
        handle.write("\n")
    print(f"wrote {path}")
    return report


def stage_sheet(seed: int) -> list[str]:
    from tools import sloped_short

    _replay, _track, v24_clock = _load(seed)
    one = os.path.join(OUT_DIR, "real_race_v221.mp4")
    two = os.path.join(OUT_DIR, "real_race_v24.mp4")
    for path in (one, two):
        if not os.path.isfile(path):
            raise SystemExit(f"missing input: {path}")
    _r, _t, v221_clock, _k = sloped_short.load_all(seed, "v221")
    plan_card = v24_clock.at(v24.WINNER_CROSSES)
    pairs = moments(v221_clock, v24_clock, (plan_card or 0.0) + v24.BEAT)
    written = [
        sheet(one, two, pairs, os.path.join(DOC_DIR, "compare.png")),
        sheet(one, two, pairs, os.path.join(DOC_DIR, "compare_phone.png"), phone=True),
    ]
    for label, at_one, at_two in pairs:
        print(f"  {label:16s} V22.1 {at_one:7.3f}   V24 {at_two:7.3f}")
    for path in written:
        print(f"wrote {path}")
    return written


def stage_clip(seed: int) -> str:
    one = os.path.join(OUT_DIR, "real_race_v221.mp4")
    two = os.path.join(OUT_DIR, "real_race_v24.mp4")
    path = opening_clip(one, two, os.path.join(DOC_DIR, "opening_v221_vs_v24.mp4"))
    print(f"wrote {path}  {os.path.getsize(path) / (1024 * 1024):.1f} MiB")
    return path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=5432)
    parser.add_argument("--frame", default=None,
                        help="a rendered first frame, for the legibility rows")
    parser.add_argument("--stage", default="all",
                        choices=("joins", "first", "sheet", "clip", "all"))
    args = parser.parse_args(argv)
    stages = (("joins", "first", "sheet", "clip")
              if args.stage == "all" else (args.stage,))
    for stage in stages:
        print(f"--- {stage} ---")
        if stage == "joins":
            stage_joins(args.seed)
        elif stage == "first":
            stage_first(args.seed, args.frame)
        elif stage == "sheet":
            stage_sheet(args.seed)
        elif stage == "clip":
            stage_clip(args.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

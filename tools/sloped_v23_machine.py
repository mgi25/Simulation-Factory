"""V23: the machine's colour, measured on the frames the film actually has.

    python tools/sloped_v23_machine.py all --godot PATH

Four builds of one scene, photographed at thirteen identical instants of one
replay through one camera track, differing in nothing but `--machine=`:

    control   the machine V22.1 ships - no pass, `lab_palette` untouched
    v23a      subtle premium    - the neutrals go cool, two zone hues corrected
    v23b      balanced signature - the designed zone system
    v23c      bold showcase     - the same system pushed past V21's ceiling

`lab_palette.MACHINE_PASSES` is what each name means. Nothing here renders a
different race: the seed, the physics, the replay, the camera track, the cut
list, the lighting rig, the environment and the grade are the ones that shipped,
and the control column is the check on that claim - it is byte-identical to a
render from before this branch existed.

Stages:

    render    the four columns, thirteen frames each
    sheets    pair_NAME.png (control beside the recommendation), zone_NAME.png
              (all four at one moment), contact.png, phone.png
    measure   the numbers, to JSON and to a markdown table
    all       all three

## What is measured, and why those things

A colour pass can fail in four ways that looking at a big monitor will not
catch, so each has a number:

* **It clips.** V21 exists because the V20 machine put 9.2% of every pixel at
  or above 250 in a channel, which is moulding rendered as paper. `clipped` and
  `p99 L*` are the same two statistics that pass was judged on, so a machine
  pass cannot quietly undo it. Both are reported twice, and the second column is
  the one to read: **the reachable set**. A whole-frame figure on these cuts is
  dominated by the sky wedge above the machine, which no machine pass touches
  and which therefore reports the same number for every variant - 6.5% of the
  shipped frame is clipped and about five of those six points are the
  environment. The reachable set is every pixel a pass can move at all, taken
  as the pixels that differ by more than 3/255 between the control and the
  loudest variant, computed once per moment and used for all four columns. It
  includes the glow each emissive spills onto its surroundings, which is
  precisely what an over-glow measurement should count.
* **It greys out.** The toy style lock measured the failure of a machine that
  was 46% achromatic against a concept reference at 14%. `achromatic` is that
  statistic, over lit pixels only.
* **It eats the racers.** This is the one the brief names and the only one that
  is about the *interaction* between the machine and the marbles rather than
  about either alone. A racer is not *found* in the frame - it is **projected
  into it**, from the replay's own position through the camera track's own pose
  by `sloped.presentation.project`, which is the projection the renderer used.
  A detector would have had to be trusted not to answer differently under
  colours it was measuring; an arithmetic position cannot. `marble dL*` is the
  median lightness step from a racer to the ring of machine around it and `p10`
  is the worst tenth - a pass that lifts the median and drops the tail has made
  the average marble prettier and one marble invisible.
* **It loses its zones.** `zone spread` is the mean a*b* distance between the
  five zone frames' machines, over the reachable set: one number for "can a
  viewer tell where in the race they are from the machine alone". It is
  reported twice - as a *field mean* and as the *strongest accent*, the top
  decile by chroma - because neither alone is honest. A violet rotor is five
  per cent of the mixer's pixels and the field mean cannot see it; a shell that
  cools by a step moves the field mean and the accent cannot see that. The
  pairwise tables matter more than either average: a pass that pulls all five
  zones the same way raises the mean distance while collapsing the three cool
  zones onto each other, and only the pairs show it.

Pillow and numpy only, both already declared.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from typing import Any, Sequence

sys.path.insert(0, os.getcwd())

import numpy as np
from PIL import Image, ImageDraw

from sloped.presentation import project

OUT_DIR = os.path.join("output", "sloped_race_v1")
WORK = os.path.join(OUT_DIR, "v23")
DOCS = os.path.join("docs", "validation", "sloped_race_v1", "v23_machine")

SCENE = "res://scenes/SlopedRaceRender.tscn"
WIDTH, HEIGHT = 1080, 1920

#: The four columns. `""` is the shipped machine and must stay first: every
#: comparison and every measurement is relative to it.
VARIANTS: tuple[tuple[str, str, str], ...] = (
    ("control", "", "V22.1 as shipped"),
    ("v23a", "v23a", "A - subtle premium"),
    ("v23b", "v23b", "B - balanced signature"),
    ("v23c", "v23c", "C - bold showcase"),
)

RECOMMENDED = "v23b"

#: The brief's seven comparison moments, plus the six that carry a zone between
#: them. `track` says which camera solve the second is on: the reverse-dolly
#: course preview has its own, and its clock is its own too.
#:
#: Race seconds are **output** seconds on the V22.1 edit, where the 1.95 s
#: omission after the gate makes output = replay - 0.20 before it and
#: replay - 2.15 after. The replay instant each one lands on is in the table in
#: the doc; the renderer prints it as it goes.
MOMENTS: tuple[tuple[str, str, float, str], ...] = (
    ("preview_finish", "preview", 0.25, "preview"),
    ("preview_fork", "preview", 1.50, "preview"),
    ("preview_start", "preview", 2.80, "preview"),
    ("start_gate", "race", 1.00, "start"),
    ("mixer_spin", "race", 3.35, "mixer"),
    ("mixer_release", "race", 4.35, "mixer"),
    ("descent", "race", 6.05, "descent"),
    ("obstacle", "race", 10.25, "obstacle"),
    ("split", "race", 13.75, "split"),
    ("branch", "race", 15.45, "split"),
    ("merge", "race", 16.55, "finish"),
    ("final", "race", 18.85, "finish"),
    ("winner", "race", 20.35, "finish"),
)

#: The five zones the pass is a language for, and the moment that photographs
#: each one best. Used by `zone spread` and by the zone sheet.
ZONE_MOMENTS = ("start_gate", "mixer_spin", "descent", "split", "winner")

#: The eight racers, from `lab_palette.MARBLE_COLOURS`. Duplicated rather than
#: parsed: a skin change is a thing this pass must *not* make, so a copy that
#: can drift is a copy a test can catch. `tests/test_sloped_v23_machine.py`
#: asserts the two lists are the same.
MARBLE_COLOURS = ("#E02532", "#2062DE", "#18A94E", "#F5C518",
                  "#F2701F", "#8E3FD4", "#18C6C6", "#F0559B")

PHONE = (270, 480)


# --- running Godot ---------------------------------------------------------

class MachineError(RuntimeError):
    pass


def find_godot(explicit: str | None) -> str:
    """`--godot`, then `$GODOT_BIN`, then the PATH: the project's own order."""
    for candidate in (explicit, os.environ.get("GODOT_BIN")):
        if candidate and os.path.exists(candidate):
            return candidate
    from shutil import which
    found = which("godot") or which("godot4")
    if found:
        return found
    raise MachineError(
        "Godot not found: pass --godot PATH or set $GODOT_BIN")


def _input(name: str) -> str:
    path = os.path.abspath(os.path.join(OUT_DIR, name))
    if not os.path.exists(path):
        raise MachineError(
            f"missing render input {path}\n"
            "  race_5432.json, cameras_v221_5432.json, preview_v221_5432.json\n"
            "  and start_contract_5432.json are outputs, not branch contents.")
    return path


def frame_path(variant: str, moment: str) -> str:
    _, track, second, _ = _moment(moment)
    return os.path.join(WORK, variant, track, "at_%07.3f.png" % second)


def _moment(name: str) -> tuple[str, str, float, str]:
    for entry in MOMENTS:
        if entry[0] == name:
            return entry
    raise KeyError(name)


def stage_render(godot: str, only: Sequence[str] = ()) -> None:
    """One Godot run per column per camera track: four builds, 52 frames."""
    replay = _input("race_5432.json")
    contract = _input("start_contract_5432.json")
    tracks = {
        "race": _input("cameras_v221_5432.json"),
        "preview": _input("preview_v221_5432.json"),
    }
    for name, flag, _label in VARIANTS:
        if only and name not in only:
            continue
        for track, cameras in tracks.items():
            seconds = [str(m[2]) for m in MOMENTS if m[1] == track]
            out = os.path.abspath(os.path.join(WORK, name, track))
            os.makedirs(out, exist_ok=True)
            command = [
                godot, "--path", "godot", SCENE, "--",
                f"--out-dir={out}",
                f"--replay={replay}",
                f"--cameras={cameras}",
                f"--start-contract={contract}",
                "--at=" + ",".join(seconds),
                f"--width={WIDTH}", f"--height={HEIGHT}",
                "--layout=b", "--detail=hero",
            ]
            if flag:
                command.append(f"--machine={flag}")
            started = time.time()
            done = subprocess.run(command, capture_output=True, text=True)
            if done.returncode != 0:
                raise MachineError(
                    f"{name}/{track} render failed:\n{done.stdout[-2000:]}\n"
                    f"{done.stderr[-2000:]}")
            print("  %-8s %-8s %2d frames  %.1fs"
                  % (name, track, len(seconds), time.time() - started))


# --- colour ----------------------------------------------------------------

def _srgb_to_linear(a: np.ndarray) -> np.ndarray:
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def to_lab(rgb: np.ndarray) -> np.ndarray:
    """sRGB in [0,1] to CIE L*a*b* under D65. Shape (..., 3) either way."""
    linear = _srgb_to_linear(rgb)
    matrix = np.array([[0.4124564, 0.3575761, 0.1804375],
                       [0.2126729, 0.7151522, 0.0721750],
                       [0.0193339, 0.1191920, 0.9503041]])
    xyz = linear @ matrix.T
    white = np.array([0.95047, 1.0, 1.08883])
    t = xyz / white
    delta = 6.0 / 29.0
    f = np.where(t > delta ** 3, np.cbrt(t), t / (3 * delta ** 2) + 4.0 / 29.0)
    return np.stack([116.0 * f[..., 1] - 16.0,
                     500.0 * (f[..., 0] - f[..., 1]),
                     200.0 * (f[..., 1] - f[..., 2])], axis=-1)


def load(path: str) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)


# --- where the racers are, from the replay and the camera track -------------

#: A racer's radius in layout units. The replay states it; this is the fallback.
LAYOUT_RADIUS = 0.285

#: A projected racer nearer the frame edge than this, in pixels, is dropped: its
#: ring would be half off-screen and the half that is left is not what the
#: viewer reads it against.
EDGE_MARGIN = 26


def _replay_second(track: dict[str, Any], output: float) -> float:
    """Output second to replay second, through the camera track's own edit map.

    The same map `sloped_race_scene.set_time` walks, so a second named here is
    the second the renderer put on that frame. The renderer prints the pair as
    it goes, which is how this is checked.
    """
    windows = track.get("edit") or []
    for row in windows:
        out_from, out_to = float(row["out"][0]), float(row["out"][1])
        if out_from - 1e-9 <= output <= out_to + 1e-9:
            replay_from, replay_to = float(row["replay"][0]), float(row["replay"][1])
            span = max(out_to - out_from, 1e-9)
            return replay_from + (output - out_from) * (replay_to - replay_from) / span
    return output


def _camera_at(track: dict[str, Any], replay_second: float):
    """The pose the renderer used, picked and blended the way it picks it.

    `presentation._camera_at` is the same arithmetic and is private; this is a
    copy rather than an import of an underscore name, and the test asserts the
    two agree on the shipped track.
    """
    chosen = track["cuts"][-1]
    for cut in track["cuts"]:
        if replay_second <= float(cut["to"]):
            chosen = cut
            break
    rows = chosen["frames"]
    first, last = float(rows[0][0]), float(rows[-1][0])
    fps = float(track.get("fps", 60))
    at = (min(max(replay_second, first), last) - first) * fps
    low = min(max(int(at), 0), len(rows) - 1)
    high = min(low + 1, len(rows) - 1)
    blend = min(max(at - low, 0.0), 1.0)
    a, b = rows[low], rows[high]
    mix = lambda i: a[i] + (b[i] - a[i]) * blend
    return (mix(1), mix(2), mix(3)), (mix(4), mix(5), mix(6)), mix(7)


def _marbles_at(replay: dict[str, Any], replay_second: float) -> list[list[float]]:
    """Eight positions in **layout** units, interpolated between replay frames."""
    frames = replay["frames"]
    fps = float(replay.get("replay_fps", 60))
    scale = float(replay.get("units", {}).get("render_scale", 0.57))
    at = min(max(replay_second * fps, 0.0), len(frames) - 1.0)
    low = int(at)
    high = min(low + 1, len(frames) - 1)
    blend = at - low
    out = []
    for a, b in zip(frames[low]["marbles"], frames[high]["marbles"]):
        out.append([(a["p"][i] + (b["p"][i] - a["p"][i]) * blend) * scale
                    for i in range(3)])
    return out


def marble_discs(replay: dict[str, Any], track: dict[str, Any],
                 output_second: float) -> list[dict[str, Any]]:
    """Every racer on screen at one output second, as a disc and a ring.

    The disc is the racer's own projected circle at 0.85 of its radius, which
    keeps the antialiased rim and the contact shadow out of its mean; the ring
    is the machine immediately around it. Both are flat pixel indices, computed
    once and reused for all four columns - the geometry cannot move between
    them because nothing this pass changes moves a marble or a camera.
    """
    replay_second = _replay_second(track, output_second)
    camera, aim, fov = _camera_at(track, replay_second)
    radius_layout = float(replay.get("units", {}).get("layout_marble_radius",
                                                      LAYOUT_RADIUS))
    half = np.tan(np.radians(fov) * 0.5)
    discs: list[dict[str, Any]] = []
    for index, point in enumerate(_marbles_at(replay, replay_second)):
        placed = project(camera, aim, fov, point, WIDTH, HEIGHT)
        if placed is None:
            continue
        x, y, depth = placed
        radius = radius_layout * HEIGHT / (2.0 * depth * half)
        if radius < 2.0:
            continue
        if not (EDGE_MARGIN <= x <= WIDTH - EDGE_MARGIN
                and EDGE_MARGIN <= y <= HEIGHT - EDGE_MARGIN):
            continue
        discs.append({
            "id": index,
            "centre": (y, x),
            "radius": float(radius),
            "disc": _disc(y, x, radius * 0.85),
            "ring": _ring((y, x), radius),
        })
    return discs


def _pixels(cy: float, cx: float, outer: float,
            keep) -> np.ndarray:
    y0, y1 = max(0, int(cy - outer) - 1), min(HEIGHT, int(cy + outer) + 2)
    x0, x1 = max(0, int(cx - outer) - 1), min(WIDTH, int(cx + outer) + 2)
    if y1 <= y0 or x1 <= x0:
        return np.zeros(0, dtype=np.int64)
    ys, xs = np.mgrid[y0:y1, x0:x1]
    distance = np.hypot(ys - cy, xs - cx)
    mask = keep(distance)
    return (ys[mask] * WIDTH + xs[mask]).astype(np.int64)


def _disc(cy: float, cx: float, radius: float) -> np.ndarray:
    return _pixels(cy, cx, radius, lambda d: d <= radius)


def _ring(centre: tuple[float, float], radius: float) -> np.ndarray:
    """The machine immediately around a racer: 1.9 to 3.2 radii out.

    Nearer and the ring is the marble's own antialiased edge and its contact
    shadow; further and it is whatever scenery happens to be behind the track,
    which is not what the racer is being read against. A minimum of three pixels
    of standoff keeps that true for the smallest racers in the film, which are
    the ones the whole measurement is about.
    """
    cy, cx = centre
    inner = max(1.9 * radius, radius + 3.0)
    outer = max(3.2 * radius, inner + 4.0)
    return _pixels(cy, cx, outer, lambda d: (d >= inner) & (d <= outer))


# --- what a machine pass can reach -----------------------------------------

#: A channel step this small is dither and tone-mapping noise, not a change.
REACH_THRESHOLD = 3

#: The column the reachable set is measured against. The loudest variant, so
#: the set is the union of what any pass moves rather than what one pass moved.
REACH_AGAINST = "v23c"


def reachable(moment: str) -> np.ndarray:
    """Pixels any machine pass can move, as a boolean mask of one frame.

    Computed from the control against `REACH_AGAINST` and then shared by all
    four columns, so no variant is measured over a footprint of its own
    choosing. Everything outside it - sky, cloud bank, terrain, the distant
    tower - is byte-identical in every column by construction, because a
    machine pass reaches neither the environment surfaces nor the light rig.
    """
    control = load(frame_path("control", moment)).astype(np.int16)
    loudest = load(frame_path(REACH_AGAINST, moment)).astype(np.int16)
    return np.abs(control - loudest).max(axis=-1) > REACH_THRESHOLD


# --- the statistics --------------------------------------------------------

def frame_stats(frame: np.ndarray, discs: Sequence[dict[str, Any]],
                reach: np.ndarray) -> dict[str, float]:
    rgb = frame.astype(np.float64) / 255.0
    lab = to_lab(rgb)
    lightness = lab[..., 0]
    channels = frame.astype(np.int16)
    high = channels.max(axis=-1)
    low = channels.min(axis=-1)

    lit = lightness >= 20.0
    clipped = high >= 250
    stats = {
        "mean_L": float(lightness.mean()),
        "p99_L": float(np.percentile(lightness, 99.0)),
        "clipped": float(clipped.mean() * 100.0),
        "achromatic": float(((high - low) <= 10)[lit].mean() * 100.0)
        if lit.any() else 0.0,
        "warm": float((channels[..., 0] > channels[..., 2] + 15).mean() * 100.0),
        # The reachable set: the machine and the glow it spills.
        "machine_mean_L": float(lightness[reach].mean()) if reach.any() else 0.0,
        "machine_p99_L": (float(np.percentile(lightness[reach], 99.0))
                          if reach.any() else 0.0),
        "machine_clipped": (float(clipped[reach].mean() * 100.0)
                            if reach.any() else 0.0),
        "reach": float(reach.mean() * 100.0),
    }

    flat_lab = lab.reshape(-1, 3)
    steps: list[float] = []
    deltas: list[float] = []
    for disc in discs:
        ring = disc["ring"]
        if ring.size < 24:
            continue
        ball = flat_lab[disc["disc"]].mean(axis=0)
        around = flat_lab[ring].mean(axis=0)
        steps.append(abs(float(ball[0] - around[0])))
        deltas.append(float(np.linalg.norm(ball - around)))
    stats["marble_dL"] = float(np.median(steps)) if steps else float("nan")
    stats["marble_dL_p10"] = (float(np.percentile(steps, 10.0)) if steps
                              else float("nan"))
    stats["marble_dE"] = float(np.median(deltas)) if deltas else float("nan")
    stats["marbles"] = float(len(steps))
    return stats


def machine_colour(frame: np.ndarray, reach: np.ndarray) -> np.ndarray:
    """The mean Lab of a frame's machine, over the reachable set.

    A mask rather than a threshold, so the number is about the machine and not
    about how much sky this particular lens happened to include.
    """
    lab = to_lab(frame.astype(np.float64) / 255.0)
    if not reach.any():
        return lab.reshape(-1, 3).mean(axis=0)
    return lab[reach].mean(axis=0)


def zone_spread(frames: dict[str, np.ndarray],
                reaches: dict[str, np.ndarray]) -> float:
    """How differently coloured the five zones are, in the a*b* plane.

    **Chroma only, with L* dropped.** A zone language is a claim about hue and
    saturation; including lightness would score a pass that made one zone
    brighter than another as well as one that made it a different colour, and
    the first is a lighting decision this pass does not get to make.
    """
    means = [machine_colour(frames[name], reaches[name])[1:]
             for name in ZONE_MOMENTS if name in frames]
    gaps = [float(np.linalg.norm(a - b))
            for i, a in enumerate(means) for b in means[i + 1:]]
    return float(np.mean(gaps)) if gaps else float("nan")


def machine_accent(frame: np.ndarray, reach: np.ndarray) -> np.ndarray:
    """The (a*, b*) of the machine's *strongest colour statement* in a frame.

    The mean over the whole machine is a field measure and it cannot see an
    accent: a violet rotor is five per cent of the pixels of the mixer's frame,
    and a shell that cools by a step moves the mean further than the rotor does.
    Both are real - a viewer reads the field *and* looks at the salient thing -
    so the field mean and this are reported side by side and neither is the
    whole answer.

    The top decile of the machine by chroma, which on these frames is the
    painted bodies, the lit strips and the tinted guards, and never the silver.
    """
    lab = to_lab(frame.astype(np.float64) / 255.0)
    if not reach.any():
        return np.zeros(2)
    inside = lab[reach]
    chroma = np.hypot(inside[:, 1], inside[:, 2])
    cut = np.percentile(chroma, 90.0)
    top = inside[chroma >= cut]
    return top[:, 1:].mean(axis=0)


def zone_signature(variant: str, reaches: dict[str, np.ndarray],
                   accent: bool = False) -> dict[str, tuple[float, float]]:
    """Each zone's own (a*, b*), as a field mean or as an accent."""
    measure = machine_accent if accent else (
        lambda frame, reach: machine_colour(frame, reach)[1:])
    return {name: tuple(round(float(v), 1) for v in measure(
        load(frame_path(variant, name)), reaches[name]))
        for name in ZONE_MOMENTS}


def zone_pairs(variant: str, reaches: dict[str, np.ndarray],
               accent: bool = False) -> dict[str, float]:
    """Every pair of zones, in a*b*. **The mean hides the failure case.**

    A pass that pulls all five zones the same way raises the average distance
    between them - the two warm zones move further from the three cool ones -
    while the three cool ones collapse onto each other. Only the pairwise
    figures say whether a viewer can tell the start from the mixer, and that is
    the pair the whole mixer zone exists for.
    """
    signature = zone_signature(variant, reaches, accent)
    out: dict[str, float] = {}
    names = list(ZONE_MOMENTS)
    for index, first in enumerate(names):
        for second in names[index + 1:]:
            a = np.array(signature[first])
            b = np.array(signature[second])
            out["%s|%s" % (first, second)] = round(
                float(np.linalg.norm(a - b)), 1)
    return out


def _tracks() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    with open(_input("race_5432.json"), "r", encoding="utf-8") as handle:
        replay = json.load(handle)
    tracks = {}
    for key, name in (("race", "cameras_v221_5432.json"),
                      ("preview", "preview_v221_5432.json")):
        with open(_input(name), "r", encoding="utf-8") as handle:
            tracks[key] = json.load(handle)
    return replay, tracks


def all_discs() -> dict[str, list[dict[str, Any]]]:
    replay, tracks = _tracks()
    return {name: marble_discs(replay, tracks[track], second)
            for name, track, second, _zone in MOMENTS}


def stage_measure() -> dict[str, Any]:
    discs = all_discs()
    print("  racers on screen: "
          + ", ".join("%s %d" % (n, len(discs[n])) for n, *_ in MOMENTS))
    reaches = {name: reachable(name) for name, *_ in MOMENTS}
    print("  reachable: %.1f%% of a frame on average"
          % (100.0 * float(np.mean([m.mean() for m in reaches.values()]))))

    report: dict[str, Any] = {"moments": {}, "variants": {}}
    for variant, _flag, label in VARIANTS:
        frames = {name: load(frame_path(variant, name)) for name, *_ in MOMENTS}
        per_moment = {name: frame_stats(frames[name], discs[name],
                                        reaches[name])
                      for name in frames}
        report["moments"][variant] = per_moment
        keys = ("mean_L", "p99_L", "clipped", "achromatic", "warm",
                "machine_mean_L", "machine_p99_L", "machine_clipped", "reach",
                "marble_dL", "marble_dL_p10", "marble_dE")
        summary = {k: float(np.nanmean([per_moment[n][k] for n in per_moment]))
                   for k in keys}
        summary["zone_spread"] = zone_spread(frames, reaches)
        summary["zones"] = zone_signature(variant, reaches)
        summary["zone_pairs"] = zone_pairs(variant, reaches)
        summary["accents"] = zone_signature(variant, reaches, accent=True)
        summary["accent_pairs"] = zone_pairs(variant, reaches, accent=True)
        summary["accent_spread"] = round(float(np.mean(
            list(summary["accent_pairs"].values()))), 1)
        summary["label"] = label
        report["variants"][variant] = summary
    os.makedirs(DOCS, exist_ok=True)
    with open(os.path.join(DOCS, "measurements.json"), "w",
              encoding="utf-8") as handle:
        json.dump(report, handle, indent=1, sort_keys=True)
    print(markdown_table(report))
    with open(os.path.join(DOCS, "measurements.md"), "w",
              encoding="utf-8") as handle:
        handle.write(markdown_table(report) + "\n\n"
                     + zone_table(report) + "\n\n"
                     + zone_table(report, "accent_pairs",
                                  "strongest accent") + "\n\n"
                     + per_moment_table(report) + "\n")
    return report


ROWS = (
    ("machine mean L*", "machine_mean_L", "{:.1f}"),
    ("machine 99th pct L*", "machine_p99_L", "{:.1f}"),
    ("machine clipped %", "machine_clipped", "{:.2f}"),
    ("zone spread dE (field)", "zone_spread", "{:.1f}"),
    ("zone spread dE (accent)", "accent_spread", "{:.1f}"),
    ("marble dL* median", "marble_dL", "{:.1f}"),
    ("marble dL* p10", "marble_dL_p10", "{:.1f}"),
    ("marble dE median", "marble_dE", "{:.1f}"),
    ("achromatic % of lit", "achromatic", "{:.1f}"),
    ("warm %", "warm", "{:.1f}"),
    ("whole frame mean L*", "mean_L", "{:.1f}"),
    ("whole frame clipped %", "clipped", "{:.2f}"),
    ("reachable % of frame", "reach", "{:.1f}"),
)


def markdown_table(report: dict[str, Any]) -> str:
    names = [v[0] for v in VARIANTS]
    lines = ["| | " + " | ".join(report["variants"][n]["label"] for n in names)
             + " |",
             "| --- |" + " --- |" * len(names)]
    for title, key, fmt in ROWS:
        cells = [fmt.format(report["variants"][n][key]) for n in names]
        lines.append("| %s | %s |" % (title, " | ".join(cells)))
    return "\n".join(lines)


def zone_table(report: dict[str, Any], key: str = "zone_pairs",
               title: str = "field mean") -> str:
    """Zone against zone. **The mean hides the failure case.**

    A pass that pulls all five zones the same way raises the average distance
    between them - the two warm zones move further from the three cool ones -
    while the three cool ones collapse onto each other. Only the pairwise
    figures say whether a viewer can tell the start from the mixer.
    """
    names = [v[0] for v in VARIANTS]
    lines = ["### Zone against zone, %s: a*b* distance" % title, "",
             "| pair | " + " | ".join(names) + " |",
             "| --- |" + " --- |" * len(names)]
    for pair in report["variants"]["control"][key]:
        cells = ["%.1f" % report["variants"][n][key][pair] for n in names]
        lines.append("| %s | %s |" % (pair.replace("|", " vs "),
                                      " | ".join(cells)))
    return "\n".join(lines)


def per_moment_table(report: dict[str, Any]) -> str:
    names = [v[0] for v in VARIANTS]
    lines = ["### Per moment: machine clipped % / marble dL* median", "",
             "| moment | zone | " + " | ".join(names) + " |",
             "| --- | --- |" + " --- |" * len(names)]
    for name, _track, _second, zone in MOMENTS:
        cells = []
        for variant in names:
            stats = report["moments"][variant][name]
            cells.append("%.2f / %.1f"
                         % (stats["machine_clipped"], stats["marble_dL"]))
        lines.append("| %s | %s | %s |" % (name, zone, " | ".join(cells)))
    return "\n".join(lines)


# --- the sheets ------------------------------------------------------------

BACKDROP = (16, 17, 21)
TEXT = (232, 234, 238)
DIM = (150, 154, 162)


def _label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str,
           colour=TEXT) -> None:
    draw.text(xy, text, fill=colour)


def _scaled(path: str, size: tuple[int, int]) -> Image.Image:
    return Image.open(path).convert("RGB").resize(size, Image.LANCZOS)


def stage_sheets() -> list[str]:
    os.makedirs(DOCS, exist_ok=True)
    written: list[str] = []

    # One moment, control beside the recommendation, big enough to judge.
    for name, _track, _second, zone in MOMENTS:
        half = (520, 924)
        sheet = Image.new("RGB", (half[0] * 2 + 24, half[1] + 40), BACKDROP)
        draw = ImageDraw.Draw(sheet)
        for index, variant in enumerate(("control", RECOMMENDED)):
            sheet.paste(_scaled(frame_path(variant, name), half),
                        (index * (half[0] + 24), 32))
            _label(draw, (index * (half[0] + 24) + 4, 12),
                   "%s  -  %s" % (variant, name))
        _label(draw, (4, half[1] + 38), "zone: %s" % zone, DIM)
        path = os.path.join(DOCS, "pair_%s.png" % name)
        sheet.save(path)
        written.append(path)

    # One moment, all four columns: the variant comparison proper.
    for name in ZONE_MOMENTS:
        cell = (420, 746)
        sheet = Image.new("RGB", (cell[0] * 4 + 3 * 12, cell[1] + 40), BACKDROP)
        draw = ImageDraw.Draw(sheet)
        for index, (variant, _flag, label) in enumerate(VARIANTS):
            sheet.paste(_scaled(frame_path(variant, name), cell),
                        (index * (cell[0] + 12), 32))
            _label(draw, (index * (cell[0] + 12) + 4, 12), label)
        _label(draw, (4, cell[1] + 38), name, DIM)
        path = os.path.join(DOCS, "zone_%s.png" % name)
        sheet.save(path)
        written.append(path)

    # Everything, small: the "did something get worse where I was not looking"
    # sheet. Thirteen moments across, four columns down.
    cell = (150, 267)
    sheet = Image.new("RGB",
                      (cell[0] * len(MOMENTS) + 90,
                       cell[1] * len(VARIANTS) + 30), BACKDROP)
    draw = ImageDraw.Draw(sheet)
    for row, (variant, _flag, label) in enumerate(VARIANTS):
        _label(draw, (4, 30 + row * cell[1] + cell[1] // 2), label[:11])
        for column, (name, *_rest) in enumerate(MOMENTS):
            sheet.paste(_scaled(frame_path(variant, name), cell),
                        (90 + column * cell[0], 30 + row * cell[1]))
            if row == 0:
                _label(draw, (94 + column * cell[0], 10), name[:14], DIM)
    path = os.path.join(DOCS, "contact.png")
    sheet.save(path)
    written.append(path)

    # The review that decides. Every moment of every column at the size a Short
    # is watched at - a machine colour that only works at 1080 wide is a machine
    # colour that does not work.
    sheet = Image.new("RGB",
                      (PHONE[0] * len(VARIANTS) + 3 * 8 + 8,
                       PHONE[1] * 4 + 3 * 8 + 40), BACKDROP)
    draw = ImageDraw.Draw(sheet)
    picked = ("start_gate", "mixer_spin", "obstacle", "split",
              "branch", "winner", "preview_fork", "descent")
    for index, name in enumerate(picked[:4]):
        for column, (variant, _flag, label) in enumerate(VARIANTS):
            sheet.paste(_scaled(frame_path(variant, name), PHONE),
                        (8 + column * (PHONE[0] + 8),
                         32 + index * (PHONE[1] + 8)))
            if index == 0:
                _label(draw, (8 + column * (PHONE[0] + 8), 12), label)
        _label(draw, (8, 26 + index * (PHONE[1] + 8) + PHONE[1]), name, DIM)
    path = os.path.join(DOCS, "phone.png")
    sheet.save(path)
    written.append(path)

    sheet = Image.new("RGB",
                      (PHONE[0] * len(VARIANTS) + 3 * 8 + 8,
                       PHONE[1] * 4 + 3 * 8 + 40), BACKDROP)
    draw = ImageDraw.Draw(sheet)
    for index, name in enumerate(picked[4:]):
        for column, (variant, _flag, label) in enumerate(VARIANTS):
            sheet.paste(_scaled(frame_path(variant, name), PHONE),
                        (8 + column * (PHONE[0] + 8),
                         32 + index * (PHONE[1] + 8)))
            if index == 0:
                _label(draw, (8 + column * (PHONE[0] + 8), 12), label)
        _label(draw, (8, 26 + index * (PHONE[1] + 8) + PHONE[1]), name, DIM)
    path = os.path.join(DOCS, "phone_b.png")
    sheet.save(path)
    written.append(path)

    for path in written:
        print("  %s" % path)
    return written


def stage_detection() -> str:
    """The racer rings the measurement uses, drawn on the control frames.

    A contrast number computed through a mask nobody has looked at is a number
    nobody should believe, and this one doubles as the proof that the projection
    agrees with the renderer: every circle should sit on a marble.
    """
    os.makedirs(DOCS, exist_ok=True)
    cell = (216, 384)
    names = [m[0] for m in MOMENTS]
    discs = all_discs()
    sheet = Image.new("RGB", (cell[0] * 7, cell[1] * 2), BACKDROP)
    for index, name in enumerate(names):
        image = Image.fromarray(load(frame_path("control", name)))
        draw = ImageDraw.Draw(image)
        for disc in discs[name]:
            cy, cx = disc["centre"]
            radius = disc["radius"] * 3.2
            draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                         outline=(80, 255, 120), width=3)
        sheet.paste(image.resize(cell, Image.LANCZOS),
                    ((index % 7) * cell[0], (index // 7) * cell[1]))
    path = os.path.join(DOCS, "detection.png")
    sheet.save(path)
    print("  %s" % path)
    return path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["render", "sheets", "measure",
                                          "detection", "all"])
    parser.add_argument("--godot", default=None)
    parser.add_argument("--only", default="",
                        help="comma-separated variant names, for --render")
    args = parser.parse_args(argv)
    only = tuple(p for p in args.only.split(",") if p)
    try:
        if args.stage in ("render", "all"):
            print("render:")
            stage_render(find_godot(args.godot), only)
        if args.stage in ("sheets", "all"):
            print("sheets:")
            stage_sheets()
        if args.stage in ("detection", "all"):
            print("detection:")
            stage_detection()
        if args.stage in ("measure", "all"):
            print("measure:")
            stage_measure()
    except MachineError as error:
        print("error: %s" % error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

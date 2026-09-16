"""Measure the V31.1 track-surface variants in image space.

Usage:

    python tools/race2_v311_track.py masks      # the segmentation, once
    python tools/race2_v311_track.py stills     # control + A + B + C
    python tools/race2_v311_track.py probe      # Part E, one field at a time
    python tools/race2_v311_track.py measure    # the tables, to JSON and stdout

## What this tool is, and what it refuses to do

It renders **one camera track, one replay, one environment and one geometry**,
four times, changing a single `StandardMaterial3D` between runs. There is no
code path here that can reach the physics, the course, the camera solve, the
environment profile or the grade: the camera track is read out of
`output/race2/v31_readability/RB` exactly as `tools/race2_v31_review.py` reads
it, and the only thing that differs between the four renders is `--track=`.

## The instrument

`--track=mask` and `--track=bands` paint the scene as flat unshaded classes and
switch the picture-making off - see `race2_track_surface.flat`. That gives a
**pixel-exact segmentation of the same frame**, so "the deck covers 0.066% of
this frame" is a count rather than an inference from colour, and every
luminance in the tables below is measured over pixels a mask selected rather
than over a region somebody drew.

The masks are a property of the *geometry*, and no variant moves a vertex. So
one mask set serves all four candidates, which is also the cheapest possible
proof that the variants are material-only: if a variant had moved geometry, its
own frames would no longer line up with the control's mask and the deck/rail
counts would drift.

`measure` turns that into a picture-level lock on "material only". For every
variant and every moment it compares the frame with the control **outside** the
channel mask.

The first build expected that to be exactly zero and it is not, which is worth
recording because the reason is a property of the instrument rather than of the
render. The masks are the only frames in this branch drawn **without MSAA**, and
the channel is a thin ribbon receding the length of the picture: its silhouette
is aliased over about 5% of the frame, and every one of those pixels is part
channel and part room in a 4x-resolved render and legitimately moves when the
channel does. So the count is not the measurement - the **amplitude** is.
`offtrack_max_delta` is the largest off-track byte change at one pixel of
dilation and comes back at 3 of 255; `offtrack_over_8_pct` is the share of
off-track pixels that move by more than 8 of 255 and comes back at exactly
0.000. Two renders of the *same* material differ on 0.002% of pixels by one
byte, so 3 is within two of the floor.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

import numpy as np
from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from tools.race2_v30_review import godot_path, run  # noqa: E402

CAMERA = "output/race2/v31_readability/RB"
OUT = "output/race2/v311_track"
DOCS = "docs/validation/race2/v311_track"
ENVIRONMENT = "contained_bay_v301"
VARIANTS = ("v31", "A", "B", "C")

# The brief's Part G, as times on the hero replay: two in the opening, two over
# the first mechanisms, three across the stretch Part G calls the first
# visibility problem, two in the middle chase and three inside the final sprint.
MOMENTS = (
    ("grid", 0.35),
    ("hook", 1.20),
    ("drum", 3.20),
    ("sweep", 5.20),
    ("chase", 6.80),
    ("switchback", 8.40),
    ("gorge", 9.60),
    ("sparse", 10.60),
    ("late_mech", 12.20),
    ("sprint_in", 13.60),
    ("comeback", 15.40),
    ("line", 16.20),
    ("runout", 18.00),
)

# Part E: the four fields the brief names, moved one at a time over the control.
PROBES = (
    "albedo=#9AA0A6", "albedo=#EFEFEC",
    "roughness=0.55", "roughness=0.80",
    "specular=0.20", "specular=0.00",
    "metallic=0.60", "clearcoat=0.0",
)

CLASSES = {
    "deck": (255, 0, 0), "rail": (0, 255, 0), "structure": (0, 0, 255),
    "station": (0, 255, 255), "actuator": (255, 0, 255), "racer": (255, 255, 0),
}
BANDS = {
    "cradle": (255, 0, 0), "lip": (255, 0, 255),
    "wall": (0, 255, 0), "crown": (0, 255, 255),
}


# --- colour ----------------------------------------------------------------
#
# CIE L* and CIE76 dE over sRGB bytes. L* rather than a raw mean because the
# question the brief asks - "can the viewer separate these two things" - is a
# perceptual one, and 8 points of L* means the same thing at the top of the
# range as at the bottom while 8 points of byte does not. Nothing here needs a
# colour library: the frames are sRGB PNGs and D65 is the only illuminant in
# play.

_M = np.array([[0.4124, 0.3576, 0.1805],
               [0.2126, 0.7152, 0.0722],
               [0.0193, 0.1192, 0.9505]])
_WHITE = np.array([0.95047, 1.0, 1.08883])


def _linear(px: np.ndarray) -> np.ndarray:
    p = np.asarray(px, dtype=np.float64) / 255.0
    return np.where(p <= 0.04045, p / 12.92, ((p + 0.055) / 1.055) ** 2.4)


def _f(t: np.ndarray) -> np.ndarray:
    return np.where(t > 0.008856, np.cbrt(t), 7.787 * t + 16.0 / 116.0)


def lab(px: np.ndarray) -> np.ndarray:
    """sRGB bytes, shape (..., 3), to CIE Lab."""
    xyz = _linear(px) @ _M.T / _WHITE
    fx, fy, fz = _f(xyz[..., 0]), _f(xyz[..., 1]), _f(xyz[..., 2])
    return np.stack([116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)], axis=-1)


def lightness(px: np.ndarray) -> np.ndarray:
    return lab(px)[..., 0]


def delta_e(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(np.asarray(a) - np.asarray(b)))


# --- rendering -------------------------------------------------------------


def at_list() -> str:
    return ",".join(f"{seconds:.3f}" for _name, seconds in MOMENTS)


def frames_dir(tag: str) -> str:
    return os.path.join(OUT, "frames", tag)


def frame(tag: str, seconds: float) -> str:
    return os.path.join(frames_dir(tag), "still_switchyard_8",
                        f"at_{seconds:07.3f}.png")


def render(tag: str, args, track: str = "", probe: str = "",
           at: str = "", size: str = "still") -> None:
    out = frames_dir(tag)
    os.makedirs(out, exist_ok=True)
    command = [
        sys.executable, "tools/race2_render.py", size,
        f"--seed={args.seed}", f"--course={args.course}",
        f"--out={CAMERA}", f"--frames={out}",
        f"--environment={ENVIRONMENT}", f"--at={at or at_list()}",
        f"--godot={godot_path(args.godot)}",
    ]
    if track:
        command.append(f"--track={track}")
    if probe:
        command.append(f"--track-probe={probe}")
    run(command, f"{size} {tag}")


def masks(args) -> None:
    render("mask", args, track="mask")
    render("bands", args, track="bands")
    render("racers", args, track="racers")


def stills(args) -> None:
    for variant in VARIANTS:
        render(variant, args, track="" if variant == "v31" else variant)


def probe(args) -> None:
    for field in PROBES:
        render(f"E_{_slug(field)}", args, probe=field,
               at="3.200,6.800,10.600,13.600")


def _slug(field: str) -> str:
    return field.replace("#", "").replace("=", "").replace(".", "")


# --- measuring -------------------------------------------------------------


def _load(path: str) -> np.ndarray | None:
    if not os.path.exists(path):
        return None
    return np.array(Image.open(path).convert("RGB"))


def _is(image: np.ndarray, colour: tuple[int, int, int]) -> np.ndarray:
    return np.all(image == np.array(colour, dtype=np.uint8), axis=2)


def _dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    """`mask` grown by `radius` pixels, by shifted ors. No SciPy needed."""
    out = mask.copy()
    for _step in range(radius):
        grown = out.copy()
        grown[1:, :] |= out[:-1, :]
        grown[:-1, :] |= out[1:, :]
        grown[:, 1:] |= out[:, :-1]
        grown[:, :-1] |= out[:, 1:]
        out = grown
    return out


def _racer_classes(seconds: float) -> list[np.ndarray]:
    """One boolean mask per racer, from the `--track=racers` render.

    Racer `i` was painted `Color(i / (n - 1), 1, 0)`, so every racer pixel has
    the flag channel full and a red level that is monotone in the racer's
    index. Reading the distinct red levels back and **sorting** them recovers
    the labels without this tool having to know what transfer curve the frame
    was written through - a sort survives any per-channel monotone function,
    which a threshold would not.
    """
    image = _load(frame("racers", seconds))
    if image is None:
        return []
    flagged = image[..., 1] > 200
    if not flagged.any():
        return []
    levels = sorted(int(v) for v in np.unique(image[..., 0][flagged]))
    return [flagged & (image[..., 0] == level) for level in levels]


def _selectors(seconds: float) -> dict[str, np.ndarray] | None:
    """Every pixel class for one moment, from the three mask renders."""
    scene = _load(frame("mask", seconds))
    band = _load(frame("bands", seconds))
    if scene is None or band is None:
        return None
    out = {name: _is(scene, colour) for name, colour in CLASSES.items()}
    out.update({name: _is(band, colour) for name, colour in BANDS.items()})
    out["track"] = out["deck"] | out["rail"]
    # The room: everything the scene mask left black *and* that is not channel.
    # Two masks rather than one because `bands` paints the machine out and
    # `mask` does not, and the background a separation measure wants is the
    # room, not the room plus the mechanism the viewer is meant to see.
    out["background"] = ~(scene.any(axis=2) | band.any(axis=2))
    return out


def _stat(image: np.ndarray, mask: np.ndarray, floor: int = 40) -> dict | None:
    if int(mask.sum()) < floor:
        return None
    px = image[mask]
    values = lightness(px)
    mean_rgb = px.mean(axis=0)
    return {
        "pixels": int(mask.sum()),
        "coverage": round(float(mask.mean()) * 100.0, 4),
        "L": round(float(values.mean()), 2),
        "L_p5": round(float(np.percentile(values, 5)), 2),
        "L_p95": round(float(np.percentile(values, 95)), 2),
        "L_std": round(float(values.std()), 2),
        "rgb": [round(float(v), 1) for v in mean_rgb],
        "warmth": round(float(mean_rgb[0] - mean_rgb[2]), 2),
        "lab": [round(float(v), 2) for v in lab(mean_rgb).tolist()],
        "clipped": round(float((px >= 250).all(axis=1).mean()) * 100.0, 3),
    }


def _racer_separation(image: np.ndarray, picks: dict, seconds: float) -> dict:
    """Part K: every racer against the track it is on, and against the room.

    One entry per *labelled* racer, so the guard the brief asks for - reject a
    variant if yellow, cyan, pink or a white-adjacent colour loses separation -
    is the weakest individual racer and not an average over a cluster fit.
    """
    track = _stat(image, picks["track"])
    room = _stat(image, picks["background"])
    if track is None or room is None:
        return {}
    against_track, against_room, sizes = [], [], []
    for mask in _racer_classes(seconds):
        if int(mask.sum()) < 60:
            continue
        colour = lab(image[mask].mean(axis=0))
        against_track.append(round(delta_e(colour, track["lab"]), 2))
        against_room.append(round(delta_e(colour, room["lab"]), 2))
        sizes.append(int(mask.sum()))
    if not against_track:
        return {}
    return {
        "racers_seen": len(against_track),
        "pixels": sizes,
        "vs_track": against_track,
        "vs_room": against_room,
        "weakest_vs_track": min(against_track),
        "weakest_vs_room": min(against_room),
        "mean_vs_track": round(float(np.mean(against_track)), 2),
    }


def measure(args) -> None:
    report: dict = {"environment": ENVIRONMENT, "camera": "RB",
                    "seed": args.seed, "moments": {}, "variants": {}}
    per_variant: dict[str, list[dict]] = {v: [] for v in VARIANTS}

    for name, seconds in MOMENTS:
        picks = _selectors(seconds)
        if picks is None:
            raise SystemExit("no masks; run `masks` first")
        entry = {
            "t": seconds,
            "coverage": {k: round(float(picks[k].mean()) * 100.0, 4)
                         for k in ("deck", "rail", "track", "racer",
                                   "cradle", "lip", "wall", "crown")},
        }
        for variant in VARIANTS:
            image = _load(frame(variant, seconds))
            if image is None:
                continue
            row = {"track": _stat(image, picks["track"]),
                   "background": _stat(image, picks["background"])}
            for band in ("cradle", "lip", "wall", "crown", "racer",
                         "station", "actuator", "structure"):
                row[band] = _stat(image, picks[band])
            if row["track"] and row["background"]:
                row["track_vs_room_dL"] = round(
                    row["track"]["L"] - row["background"]["L"], 2)
                row["track_vs_room_dE"] = round(
                    delta_e(row["track"]["lab"], row["background"]["lab"]), 2)
            if row["wall"] and row["crown"]:
                row["edge_step_dL"] = round(
                    row["crown"]["L"] - row["wall"]["L"], 2)
            if variant != "v31":
                control = _load(frame("v31", seconds))
                if control is not None:
                    # **Dilated, because the masks are the only frames in this
                    # branch rendered without MSAA.** A variant's frame is
                    # resolved 4x, so the pixel on a channel silhouette is part
                    # channel and part room and legitimately moves when the
                    # channel does. Un-dilated this read 3.6% of the frame
                    # changed, all of it one pixel wide. Two pixels of dilation
                    # is wider than the resolve can reach.
                    off = ~_dilate(picks["track"], 1)
                    diff = np.abs(image[off].astype(np.int16)
                                  - control[off].astype(np.int16))
                    row["offtrack_max_delta"] = int(diff.max())
                    row["offtrack_over_8_pct"] = round(float(
                        np.any(diff > 8, axis=1).mean()) * 100.0, 6)
            if row["racer"] and row["track"]:
                row["racer_minus_track_dL"] = round(
                    row["racer"]["L"] - row["track"]["L"], 2)
            # Part L: the mechanisms are the stage's other readable objects and
            # a brighter or flatter track must not take them with it. The
            # station class is the hazard orange, the actuators are the moving
            # blades, the structure is the graphite shell.
            for machine in ("station", "actuator", "structure"):
                if row[machine] and row["track"]:
                    row[f"{machine}_vs_track_dE"] = round(
                        delta_e(row[machine]["lab"], row["track"]["lab"]), 2)
            row["racers"] = _racer_separation(image, picks, seconds)
            entry.setdefault("variants", {})[variant] = row
            per_variant[variant].append(row)
        report["moments"][name] = entry

    for variant, rows in per_variant.items():
        if not rows:
            continue
        report["variants"][variant] = _summarise(rows)
        # Part M: the final sprint against the rest of the film. The brief asks
        # that the runway not be made much brighter than the course unless
        # there is a material reason, and a material with no section-specific
        # tuning cannot do that - but it is worth being the number rather than
        # the argument.
        sprint = [r for r, (_n, t) in zip(rows, MOMENTS) if t >= 13.0]
        rest = [r for r, (_n, t) in zip(rows, MOMENTS) if 2.0 <= t < 13.0]
        report["variants"][variant]["sprint_track_L"] = _mean(sprint, "track",
                                                              "L")
        report["variants"][variant]["course_track_L"] = _mean(rest, "track",
                                                              "L")

    os.makedirs(DOCS, exist_ok=True)
    target = os.path.join(DOCS, "track_measure.json")
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1)
    _print(report)
    print(f"  wrote {target}")


def _mean(rows, path, sub=None):
    values = []
    for row in rows:
        value = row.get(path)
        if isinstance(value, dict) and sub:
            value = value.get(sub)
        if isinstance(value, (int, float)):
            values.append(float(value))
    return round(float(np.mean(values)), 2) if values else None


def _summarise(rows: list[dict]) -> dict:
    weakest = [r["racers"]["weakest_vs_track"] for r in rows
               if r.get("racers")]
    return {
        "track_L": _mean(rows, "track", "L"),
        "track_L_spread": round(float(np.mean(
            [r["track"]["L_p95"] - r["track"]["L_p5"] for r in rows
             if r.get("track")])), 2),
        "track_L_std": _mean(rows, "track", "L_std"),
        "track_warmth": _mean(rows, "track", "warmth"),
        "track_clipped": _mean(rows, "track", "clipped"),
        "wall_L": _mean(rows, "wall", "L"),
        "wall_L_spread": round(float(np.mean(
            [r["wall"]["L_p95"] - r["wall"]["L_p5"] for r in rows
             if r.get("wall")])), 2),
        "crown_L": _mean(rows, "crown", "L"),
        "cradle_L": _mean(rows, "cradle", "L"),
        "lip_L": _mean(rows, "lip", "L"),
        "edge_step_dL": _mean(rows, "edge_step_dL"),
        "track_vs_room_dL": _mean(rows, "track_vs_room_dL"),
        "track_vs_room_dE": _mean(rows, "track_vs_room_dE"),
        "racer_minus_track_dL": _mean(rows, "racer_minus_track_dL"),
        "weakest_racer_vs_track_dE": round(min(weakest), 2) if weakest else None,
        "station_vs_track_dE": _mean(rows, "station_vs_track_dE"),
        "actuator_vs_track_dE": _mean(rows, "actuator_vs_track_dE"),
        "structure_vs_track_dE": _mean(rows, "structure_vs_track_dE"),
        "offtrack_max_delta": max(
            [r["offtrack_max_delta"] for r in rows
             if "offtrack_max_delta" in r] or [0]),
        "offtrack_over_8_pct": _mean(rows, "offtrack_over_8_pct"),
        "mean_racer_vs_track_dE": round(float(np.mean(
            [r["racers"]["mean_vs_track"] for r in rows if r.get("racers")])), 2)
        if weakest else None,
    }


def _print(report: dict) -> None:
    print()
    print("  screen coverage, by section band (one mask, every variant)")
    print(f'  {"moment":<12}{"t":>7}{"cradle":>9}{"lip":>8}{"wall":>8}'
          f'{"crown":>8}{"track":>8}{"racer":>8}')
    for name, entry in report["moments"].items():
        c = entry["coverage"]
        print(f'  {name:<12}{entry["t"]:>7.2f}{c["cradle"]:>9.3f}'
              f'{c["lip"]:>8.3f}{c["wall"]:>8.3f}{c["crown"]:>8.3f}'
              f'{c["track"]:>8.3f}{c["racer"]:>8.3f}')
    print()
    print("  the variants")
    keys = ("track_L", "track_L_spread", "wall_L", "wall_L_spread",
            "crown_L", "edge_step_dL",
            "cradle_L", "track_vs_room_dL", "track_vs_room_dE",
            "racer_minus_track_dL", "weakest_racer_vs_track_dE",
            "mean_racer_vs_track_dE", "station_vs_track_dE",
            "actuator_vs_track_dE", "structure_vs_track_dE",
            "sprint_track_L", "course_track_L",
            "track_warmth", "track_clipped",
            "offtrack_max_delta", "offtrack_over_8_pct")
    print(f'  {"":<26}' + "".join(f"{v:>12}" for v in report["variants"]))
    for key in keys:
        cells = []
        for variant in report["variants"]:
            value = report["variants"][variant].get(key)
            cells.append(f"{value:>12.2f}" if isinstance(value, (int, float))
                         else f"{'-':>12}")
        print(f"  {key:<26}" + "".join(cells))
    print()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("masks", "stills", "probe", "measure",
                                         "all"))
    parser.add_argument("--course", default="switchyard")
    parser.add_argument("--seed", type=int, default=8)
    parser.add_argument("--godot", default="")
    args = parser.parse_args()
    if args.mode in ("masks", "all"):
        masks(args)
    if args.mode in ("stills", "all"):
        stills(args)
    if args.mode == "probe":
        probe(args)
    if args.mode in ("measure", "all"):
        measure(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

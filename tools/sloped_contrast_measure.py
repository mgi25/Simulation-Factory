"""What the contrast pass claims, measured on two sets of rendered frames.

    python tools/sloped_contrast_measure.py --before <dir> --after <dir>

The V21 contrast pass was argued from a table of eleven frames, and that table
was produced by hand - which meant it could not be re-run against a different
camera track. The V21 integration needs exactly that: the cameras moved after
the contrast numbers were taken, so every one of them has to be measured again
on the lenses the film actually ships with.

Two families of number, both per frame and both averaged over the eleven:

* **how much of the frame has stopped shading** - the share of pixels flat at
  the top of the range, and where the lightness distribution's shoulder sits.
  A clipped surface is one that has run out of curvature, and the finding this
  pass exists for is that V20 clipped one pixel in eighteen;
* **how far a racer is from what is immediately behind it** - each marble's
  replay position projected through the solved camera, a disc of pixels on the
  ball against the annulus of course around it, in CIELAB. Reported as a whole
  dE and as the chroma-only part, because on a pale course the separation that
  survives a phone is the colour one.

The projection is `sloped.presentation`'s, so it is the same arithmetic the
overlays are placed with. An occluded marble reports a false near-zero - its
centre lands on whatever is in front of it - so the medians are printed beside
the means, and it is the *direction* between two builds of the same frame that
is the claim, never the absolute.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from typing import Any, Sequence

sys.path.insert(0, os.getcwd())

import numpy as np
from PIL import Image

from sloped import presentation
from tools.sloped_contrast_sheet import MOMENTS, frame_path

OUT_DIR = os.path.join("output", "sloped_race_v1")

PHONE = (270, 480)          # roughly what a 1080-wide Short occupies on a handset
FLAT_WHITE = 242            # at or above this in *every* channel
NEAR_CLIP = 250             # at or above this in any one


def replay_second(track: dict[str, Any], output: float) -> float | None:
    """The camera track's own output clock, which is what `--at` is in.

    Not `Clock`: the Short's clock carries the held opening and the retention
    cut, and these frames are rendered straight out of the track.
    """
    for window in track.get("edit", ()):
        low, high = window["out"]
        if low <= output <= high:
            return window["replay"][0] + (output - low)
    return None


def _lab(rgb: np.ndarray) -> np.ndarray:
    """sRGB 0-255 to CIELAB, D65, on an array whose last axis is the channel."""
    srgb = rgb.astype(np.float64) / 255.0
    linear = np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)
    matrix = np.array([
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ])
    xyz = linear @ matrix.T
    white = np.array([0.95047, 1.0, 1.08883])
    ratio = xyz / white
    f = np.where(ratio > 0.008856, np.cbrt(ratio), 7.787 * ratio + 16.0 / 116.0)
    return np.stack([
        116.0 * f[..., 1] - 16.0,
        500.0 * (f[..., 0] - f[..., 1]),
        200.0 * (f[..., 1] - f[..., 2]),
    ], axis=-1)


def frame_report(image: Image.Image) -> dict[str, float]:
    pixels = np.asarray(image.convert("RGB"))
    flat = float((pixels >= FLAT_WHITE).all(axis=-1).mean() * 100.0)
    near = float((pixels >= NEAR_CLIP).any(axis=-1).mean() * 100.0)
    lightness = _lab(pixels)[..., 0]
    return {
        "flat_white": flat,
        "near_clip": near,
        "above_88": float((lightness > 88.0).mean() * 100.0),
        "above_78": float((lightness > 78.0).mean() * 100.0),
        "p99": float(np.percentile(lightness, 99.0)),
        "mean": float(lightness.mean()),
    }


def separation(
    image: Image.Image,
    places: Sequence[tuple[float, float, float]],
    scale: float = 1.0,
) -> list[tuple[float, float]]:
    """Per racer, the pair `(dE, chroma-only dE)` against the course behind it."""
    pixels = np.asarray(image.convert("RGB")).astype(np.float64)
    height, width = pixels.shape[:2]
    ys, xs = np.mgrid[0:height, 0:width]
    out: list[tuple[float, float]] = []
    for x, y, radius in places:
        x, y, radius = x * scale, y * scale, radius * scale
        if radius < 2.0 or not (0 <= x < width and 0 <= y < height):
            continue
        far = (xs - x) ** 2 + (ys - y) ** 2
        ball = far <= (radius * 0.55) ** 2
        ring = (far >= (radius * 1.60) ** 2) & (far <= (radius * 2.60) ** 2)
        if int(ball.sum()) < 4 or int(ring.sum()) < 12:
            continue
        a = _lab(pixels[ball].mean(axis=0))
        b = _lab(pixels[ring].mean(axis=0))
        out.append((
            float(np.linalg.norm(a - b)),
            float(np.linalg.norm(a[1:] - b[1:])),
        ))
    return out


def places_at(replay: dict[str, Any], track: dict[str, Any], when: float):
    """Every marble's `(x, y, radius)` on a 1080x1920 frame at a replay second."""
    scale = float(replay.get("units", {}).get("render_scale", 0.57))
    marble_radius = float(replay.get("units", {}).get("layout_marble_radius", 0.285))
    frame = min(replay["frames"], key=lambda one: abs(float(one["t"]) - when))
    camera, aim, fov = presentation._camera_at(track, when)
    half_up = math.tan(math.radians(fov) * 0.5)
    out = []
    for sample in frame["marbles"]:
        point = tuple(float(sample["p"][axis]) * scale for axis in range(3))
        placed = presentation.project(camera, aim, fov, point)
        if placed is None:
            continue
        x, y, depth = placed
        if not (0 <= x < presentation.WIDTH and 0 <= y < presentation.HEIGHT):
            continue
        out.append(
            (x, y, (marble_radius / depth) / half_up * (presentation.HEIGHT * 0.5))
        )
    return out


def measure(directory: str, replay, track) -> dict[str, Any]:
    rows, full, phone = [], [], []
    for seconds, _name in MOMENTS:
        image = Image.open(frame_path(directory, seconds))
        rows.append(frame_report(image))
        when = replay_second(track, seconds)
        if when is None:
            continue
        places = places_at(replay, track, when)
        full.extend(separation(image, places))
        small = image.convert("RGB").resize(PHONE, Image.LANCZOS)
        phone.extend(separation(small, places, scale=PHONE[0] / presentation.WIDTH))
    summary = {key: float(np.mean([row[key] for row in rows])) for key in rows[0]}
    summary["racers"] = len(full)
    for label, data in (("full", full), ("phone", phone)):
        if data:
            summary[f"de_{label}"] = float(np.mean([one[0] for one in data]))
            summary[f"de_{label}_median"] = float(np.median([one[0] for one in data]))
            summary[f"chroma_{label}"] = float(np.mean([one[1] for one in data]))
    return summary


LABELS = (
    ("flat_white", "pixels flat white (all channels 242+)   %"),
    ("near_clip", "pixels at 250+ in any channel           %"),
    ("above_88", "pixels above L* 88                      %"),
    ("above_78", "pixels above L* 78                      %"),
    ("p99", "99th percentile frame lightness   L*"),
    ("mean", "mean frame lightness              L*"),
    ("de_full", "racer vs. its surround, dE"),
    ("de_full_median", "the same, median rather than mean"),
    ("chroma_full", "racer vs. its surround, chroma only"),
    ("de_phone", "the same at 270x480, dE"),
    ("chroma_phone", "the same at 270x480, chroma only"),
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--before", required=True, help="the V20 control frames")
    parser.add_argument("--after", required=True, help="the V21 frames")
    parser.add_argument("--seed", type=int, default=5432)
    parser.add_argument("--json", default="")
    args = parser.parse_args(argv)

    replay_path = os.path.join(OUT_DIR, f"race_{args.seed}.json")
    track_path = os.path.join(OUT_DIR, f"cameras_{args.seed}.json")
    with open(replay_path, encoding="utf-8") as handle:
        replay = json.load(handle)
    with open(track_path, encoding="utf-8") as handle:
        track = json.load(handle)

    before = measure(args.before, replay, track)
    after = measure(args.after, replay, track)
    print(f"    {'':44s} {'V20':>8s} {'V21':>8s} {'delta':>8s}")
    for key, label in LABELS:
        if key not in before or key not in after:
            continue
        print(f"    {label:44s} {before[key]:8.2f} {after[key]:8.2f} "
              f"{after[key] - before[key]:+8.2f}")
    print(f"    racers sampled: {before['racers']} / {after['racers']} over "
          f"{len(MOMENTS)} frames")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump({"before": before, "after": after}, handle, indent=2)
        print(f"  wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

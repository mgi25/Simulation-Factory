"""V30.1: what the premium pass does to camera A's frames, measured.

Usage:

    python tools/race2_v301_review.py frames     # render the sample set
    python tools/race2_v301_review.py matte      # the same, machine-only
    python tools/race2_v301_review.py measure    # the numbers
    python tools/race2_v301_review.py sheets     # comparison + phone sheets
    python tools/race2_v301_review.py fullfilm   # every frame of the winner
    python tools/race2_v301_review.py clips      # the films
    python tools/race2_v301_review.py compare    # V30 | V30.1 side by side
    python tools/race2_v301_review.py phone      # the 270x480 pair

The render, matte, silhouette and clip machinery is
`tools/race2_v30_review.py`'s, imported rather than restated, so the two
passes are measured by the same instrument on the same frames. What is added
here is three metrics V30 did not have, and each of them exists because a V30
number disagreed with the delivered picture.

## 1. Hue, measured where the eye reads it

V30's `blue_over_red` is a ratio of channel means over every room pixel above
luma 20. On the delivered final sprint it reports **1.18** against a 1.35
threshold, and the same frame's lit floor measures **1.97**: a strong teal. The
average is not wrong, it is answering a different question. A floor made of
bright panel tops separated by dark shadow has most of its *pixels* in the
shadow and all of its *colour* in the tops, and hue is a property the eye reads
where the picture is bright.

So `bright_*` repeats every hue measure over the top quartile of the room's own
luma. V30's film-average numbers are kept alongside, because "is the room blue"
really is a question about the average - it was just never the question about
the floor.

## 2. Background frequency, as the brief's Part J

Two numbers, both on the room only and both taken inside the middle band of
the frame where the active pack is:

    edge_density    share of room pixels on a luma edge. A floor of 2.2-unit
                    strips is nearly all edge; a floor of 13-unit modules is
                    nearly all surface.
    stripe_score    the strongest periodic component of the room's row-mean
                    luma profile, by autocorrelation. This is the one that
                    names the defect: a *grate* is not a busy surface, it is a
                    **periodic** one, and periodicity is what makes the eye
                    track the floor instead of the race.

## 3. Whether the authored floor module is the module in the picture

`seam_rate` is arithmetic rather than image analysis - camera speed over
module pitch - but it is reported next to the image numbers because it is the
quantity the two of them are consequences of, and because nothing in V30's
toolchain ever printed it.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from tools.race2_v30_review import (  # noqa: E402
    MOMENTS, SPRINT, encode, ffmpeg, film_end, godot_path, run,
)

TRACKS = "output/race2/v281_camera/A"
FRAMES = "output/race2/v301_stage/frames"
DOCS = "docs/validation/race2/v301_stage"
EXPORT = "exports/race2_v301_stage"

# The comparison the brief asks for, plus the three floor treatments. `v30` is
# the control and it is the *delivered* V30 profile, untouched by this branch,
# rendered through the same pipeline on the same frames.
WORLDS = (
    ("v30", "contained_bay_v30"),
    ("v301", "contained_bay_v301"),
    ("floor_a", "contained_bay_v301a"),
    ("floor_b", "contained_bay_v301b"),
    ("floor_c", "contained_bay_v301c"),
)

# Module pitch per world, for the `seam_rate` column. V30's is a 2.2 plate on
# a 0.18 gap; the variants are in `tools/race2_v301_stage.py`.
PITCH = {"v30": 2.38, "v301": 13.00, "floor_a": 26.50, "floor_b": 13.00,
         "floor_c": 18.10}
CAMERA_SPEED = 12.04


def at_list() -> str:
    return ",".join(f"{seconds:.3f}" for _name, seconds in MOMENTS)


def render(args, show: str) -> None:
    tag = "frames" if show == "all" else "matte"
    stats: dict[str, dict] = {}
    for world, environment in WORLDS:
        if args.worlds and world not in args.worlds.split(","):
            continue
        folder = os.path.join(FRAMES, f"{tag}_{world}")
        os.makedirs(folder, exist_ok=True)
        out = run([
            sys.executable, "tools/race2_render.py", "still",
            f"--seed={args.seed}", f"--course={args.course}",
            f"--out={TRACKS}", f"--frames={folder}",
            f"--environment={environment}", f"--show={show}",
            f"--at={at_list()}", f"--godot={godot_path(args.godot)}",
        ], f"{tag} {world}")
        record = {"environment": environment}
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("scene:"):
                parts = line.replace(",", "").split()
                record["meshes"] = int(parts[1])
                record["triangles"] = int(parts[4].lstrip("~"))
            if line.startswith("rendered"):
                record["ms_per_frame"] = float(line.split("(")[1].split()[0])
        stats[world] = record
        print(f"  {tag} {world}: {record}")
    path = os.path.join(DOCS, f"cost_{tag}.json")
    os.makedirs(DOCS, exist_ok=True)
    existing = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            existing = json.load(handle)
    existing.update(stats)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(existing, handle, indent=1)


def frame_path(tag: str, world: str, seconds: float, args) -> str:
    return os.path.join(FRAMES, f"{tag}_{world}",
                        f"still_{args.course}_{args.seed}",
                        f"at_{seconds:07.3f}.png")


# --- the added metrics ------------------------------------------------------


def _stripe_score(profile, min_gap: int = 8, depth: float = 1.5) -> dict:
    """How many separate dark lines cross the frame, and how deep they are.

    **The brief calls this "repeated line frequency" and that is exactly what
    it has to be: a count, not a period.** Two earlier versions of this
    function tried to measure a period by autocorrelation and both failed, for
    two different reasons that are worth keeping because they are properties
    of the problem rather than of the code.

    The first was not detrended. Every chase frame here is bright at one end
    and dark at the other because the floor recedes, and that ramp carries so
    much power that it autocorrelates above 0.98 at every small lag: V30's
    grate scored 0.980 and V30.1's broad slabs 0.975, and a blank grey card
    would have scored the same.

    The second was detrended and still failed, because **a floor seen in
    perspective has no period.** The seam pitch in the picture is a chirp: at
    camera A's sprint framing a 2.38-unit seam spacing is roughly 360 px apart
    in the near foreground and a couple of px apart at the top of the same
    frame. There is no single lag to find, which is why both variants kept
    returning the shortest lag they were allowed.

    What survives the chirp is the *count*. A floor of narrow strips puts many
    dark lines across the picture; a floor of large modules puts a few. So the
    measure is the number of prominent local minima in the detrended row-mean
    luma profile - one per seam crossing the frame, at whatever spacing
    perspective gives it - normalised per thousand image rows so that
    framings of different heights compare.

    `depth` is in luma and is what keeps this from counting shading: a minimum
    has to sit 1.5 luma below the nearer of the two local maxima flanking it
    to count as a line. `min_gap` stops one soft seam being counted twice.
    """
    import numpy as np

    series = np.asarray(profile, dtype=np.float64)
    series = series[np.isfinite(series)]
    if series.size < 120:
        return {"lines": 0.0, "count": 0, "power": 0.0}
    # Detrend against everything slower than a seam, so the recession ramp and
    # the machine's own large shadows drop out and the seams stay.
    window = 81
    kernel = np.ones(window) / float(window)
    trend = np.convolve(series, kernel, mode="same")
    half = window // 2
    residual = (series - trend)[half:-half]
    if residual.size < 60:
        return {"lines": 0.0, "count": 0, "power": 0.0}
    # A light smooth first: a single-pixel dip is noise, not a line.
    smooth = np.convolve(residual, np.ones(3) / 3.0, mode="same")
    count, last = 0, -min_gap
    for i in range(1, smooth.size - 1):
        if smooth[i] > smooth[i - 1] or smooth[i] >= smooth[i + 1]:
            continue
        if i - last < min_gap:
            continue
        left = smooth[max(0, i - min_gap * 3):i]
        right = smooth[i + 1:i + 1 + min_gap * 3]
        if left.size == 0 or right.size == 0:
            continue
        if min(left.max(), right.max()) - smooth[i] < depth:
            continue
        count += 1
        last = i
    return {
        "lines": round(count * 1000.0 / float(smooth.size), 2),
        "count": count,
        "power": round(float(np.sqrt((residual * residual).mean())), 3),
    }


def _frequency(delivery, room, luma) -> dict:
    """Edge density and stripe score over the room, in the band the pack is in.

    Restricted to the middle 60% of the frame's height on purpose. The brief
    asks for the background complexity *behind the active pack*, and the pack
    is never at the very top or the very bottom of a 9:16 chase frame - the top
    is the far field and the bottom is the foreground the camera is flying
    over. A measure taken over the whole frame is dominated by whichever of
    those two happens to be busier.
    """
    import numpy as np

    height = luma.shape[0]
    band = slice(int(height * 0.2), int(height * 0.8))
    strip_room = room[band]
    strip_luma = luma[band]
    if not strip_room.any():
        return {"edge_density": 0.0, "stripe": {"score": 0.0, "lag": 0}}

    # A Sobel magnitude would weight the two axes equally; the seams that make
    # this floor a pattern all run across the frame, so the gradient that
    # matters is the vertical one. Both are reported.
    dy = np.zeros_like(strip_luma)
    dx = np.zeros_like(strip_luma)
    dy[1:-1, :] = (strip_luma[2:, :] - strip_luma[:-2, :]) * 0.5
    dx[:, 1:-1] = (strip_luma[:, 2:] - strip_luma[:, :-2]) * 0.5
    magnitude = np.sqrt(dy * dy + dx * dx)
    inside = strip_room
    edges = (magnitude > 6.0) & inside

    # The row-mean luma of the room, which is the profile a transverse seam
    # pattern shows up in. Rows with almost no room in them are dropped rather
    # than counted as zero, which would inject a step the size of the machine.
    counts = inside.sum(axis=1)
    rows = np.where(counts > strip_luma.shape[1] * 0.25,
                    (strip_luma * inside).sum(axis=1)
                    / np.maximum(counts, 1), np.nan)
    return {
        "edge_density": float(edges.sum() / max(inside.sum(), 1)),
        "edge_density_vertical": float((((np.abs(dy) > 6.0) & inside).sum())
                                       / max(inside.sum(), 1)),
        "stripe": _stripe_score(rows[np.isfinite(rows)]),
        "rows_used": int(np.isfinite(rows).sum()),
    }


def measure(args) -> dict:
    import numpy as np
    from PIL import Image

    def load(path):
        return np.asarray(Image.open(path).convert("RGB")).astype(np.float32)

    def luma(a):
        return a @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)

    worlds = [w for w in WORLDS
              if not args.worlds or w[0] in args.worlds.split(",")]
    report: dict = {"worlds": {}}

    for world, environment in worlds:
        per_moment = {}
        for name, seconds in MOMENTS:
            delivery = frame_path("frames", world, seconds, args)
            matte = frame_path("matte", world, seconds, args)
            if not (os.path.exists(delivery) and os.path.exists(matte)):
                continue
            a = load(delivery)
            m = load(matte)
            la, lm = luma(a), luma(m)

            subject = lm > 2.0
            room = ~subject
            mx, mn = m.max(axis=2), m.min(axis=2)
            sat = np.where(mx > 1.0, (mx - mn) / np.maximum(mx, 1.0), 0.0)
            racers = subject & (sat > 0.35)
            machine = subject & ~racers

            void = room & (la <= 2.0)
            third = la.shape[0] // 3
            lower_void = void[2 * third:]

            ax, an = a.max(axis=2), a.min(axis=2)
            asat = np.where(ax > 1.0, (ax - an) / np.maximum(ax, 1.0), 0.0)
            bright = room & (la > 90.0) & (asat > 0.22)
            warm = bright & (a[:, :, 0] > a[:, :, 2] * 1.25)
            cool = bright & (a[:, :, 2] > a[:, :, 0] * 1.25)

            lit = room & (la > 20.0)
            room_l = la[room]

            # **The instrument fix.** The top quartile of the room's own lit
            # luma: the panel tops rather than the shadow between them. On
            # V30's final sprint this and the line below it differ by a factor
            # of 1.7 on the same frame.
            hue = {}
            if lit.any():
                lit_l = la[lit]
                cut = float(np.quantile(lit_l, 0.75))
                top = room & (la >= max(cut, 20.0))
                hue = {
                    "blue_over_red": float(a[lit][:, 2].mean()
                                           / max(a[lit][:, 0].mean(), 0.01)),
                    "green_over_red": float(a[lit][:, 1].mean()
                                            / max(a[lit][:, 0].mean(), 0.01)),
                    "chroma": float(asat[lit].mean()),
                    "bright_cut": cut,
                    "bright_coverage": float(top.mean()),
                }
                if top.any():
                    hue.update({
                        "bright_blue_over_red":
                            float(a[top][:, 2].mean()
                                  / max(a[top][:, 0].mean(), 0.01)),
                        "bright_green_over_red":
                            float(a[top][:, 1].mean()
                                  / max(a[top][:, 0].mean(), 0.01)),
                        "bright_chroma": float(asat[top].mean()),
                        "bright_luma": float(la[top].mean()),
                    })

            entry = {
                "void": float(void.mean()),
                "lower_third_void": float(lower_void.mean()),
                "mean_luma": float(la.mean()),
                "room_mean_luma": float(room_l.mean()) if room_l.size else 0.0,
                "room_coverage": float(room.mean()),
                "machine_coverage": float(machine.mean()),
                "racer_coverage": float(racers.mean()),
                "warm_coverage": float(warm.mean()),
                "cool_coverage": float(cool.mean()),
                "racer_mean_luma": (float(la[racers].mean())
                                    if racers.any() else 0.0),
                "machine_mean_luma": (float(la[machine].mean())
                                      if machine.any() else 0.0),
                "lit_room_coverage": float(lit.mean()),
            }
            entry.update(hue)
            entry.update(_frequency(a, room, la))
            entry["racer_separation"] = (entry["racer_mean_luma"]
                                         - entry["room_mean_luma"])
            entry["machine_separation"] = (entry["machine_mean_luma"]
                                           - entry["room_mean_luma"])
            per_moment[name] = entry

        if not per_moment:
            continue

        def avg(key, names=None, sub=None):
            picks = []
            for n in (names or per_moment):
                if n not in per_moment:
                    continue
                value = per_moment[n]
                if sub:
                    value = value.get(sub, {})
                if key in value:
                    picks.append(value[key])
            return sum(picks) / max(1, len(picks)) if picks else 0.0

        flat = ("void", "lower_third_void", "mean_luma", "room_mean_luma",
                "room_coverage", "machine_coverage", "racer_coverage",
                "warm_coverage", "cool_coverage", "racer_separation",
                "machine_separation", "blue_over_red", "green_over_red",
                "chroma", "bright_blue_over_red", "bright_green_over_red",
                "bright_chroma", "bright_luma", "lit_room_coverage",
                "edge_density", "edge_density_vertical")
        report["worlds"][world] = {
            "environment": environment,
            "seam_rate": round(CAMERA_SPEED / PITCH.get(world, 1.0), 2),
            "module_pitch": PITCH.get(world),
            "film": {k: avg(k) for k in flat},
            "final_sprint": {k: avg(k, SPRINT) for k in flat},
            "stripe": {"lines": avg("lines", sub="stripe"),
                       "power": avg("power", sub="stripe")},
            "stripe_sprint": {"lines": avg("lines", SPRINT, sub="stripe"),
                              "power": avg("power", SPRINT, sub="stripe")},
            "worst_void": max(per_moment.items(),
                              key=lambda kv: kv[1]["void"])[0],
            "worst_void_value": max(v["void"] for v in per_moment.values()),
            "moments": per_moment,
        }
    return report


def render_measure(report: dict) -> str:
    out = ["V30.1 PREMIUM STAGE: camera A, ten moments", "=" * 78, ""]
    out.append("OVER THE FILM")
    out.append("%-9s %7s %8s %7s %8s %8s %7s %7s %7s"
               % ("world", "void%", "sprint%", "roomL", "racerSep", "warm%",
                  "B/R", "brB/R", "brChr"))
    for world, data in report["worlds"].items():
        f, s = data["film"], data["final_sprint"]
        out.append("%-9s %6.2f%% %7.2f%% %7.1f %8.1f %7.3f%% %7.2f %7.2f %7.3f"
                   % (world, f["void"] * 100.0, s["void"] * 100.0,
                      f["room_mean_luma"], f["racer_separation"],
                      f["warm_coverage"] * 100.0, f["blue_over_red"],
                      f["bright_blue_over_red"], f["bright_chroma"]))
    out.append("")
    out.append("  B/R      V30's measure: blue over red on every lit room px")
    out.append("  brB/R    the same on the room's brightest quartile")
    out.append("  brChr    chroma there. V30's sprint floor measures 0.49")
    out.append("")
    out.append("BACKGROUND FREQUENCY  (room only, middle 60% of the frame)")
    out.append("%-9s %7s %9s %9s %10s %9s %8s"
               % ("world", "pitch", "seams/s", "edge%", "vert-edge%",
                  "lines/k", "ampl"))
    for world, data in report["worlds"].items():
        f = data["film"]
        out.append("%-9s %7s %9.2f %8.2f%% %9.2f%% %9.2f %8.2f"
                   % (world, data["module_pitch"], data["seam_rate"],
                      f["edge_density"] * 100.0,
                      f["edge_density_vertical"] * 100.0,
                      data["stripe"]["lines"], data["stripe"]["power"]))
    out.append("")
    out.append("  lines/k  dark lines crossing the room per 1000 image")
    out.append("           rows. This is the grate, counted.")
    out.append("  ampl     RMS of that detrended residual, in luma. A floor")
    out.append("           can repeat perfectly at an invisible amplitude.")
    out.append("")
    out.append("THE FINAL SPRINT ALONE")
    out.append("%-9s %7s %8s %8s %8s %8s %8s %7s"
               % ("world", "void%", "roomL", "racerSep", "warm%", "edge%",
                  "lines/k", "ampl"))
    for world, data in report["worlds"].items():
        s = data["final_sprint"]
        out.append("%-9s %6.2f%% %8.1f %8.1f %7.3f%% %7.2f%% %7.3f %7.2f"
                   % (world, s["void"] * 100.0, s["room_mean_luma"],
                      s["racer_separation"], s["warm_coverage"] * 100.0,
                      s["edge_density"] * 100.0,
                      data["stripe_sprint"]["lines"],
                      data["stripe_sprint"]["power"]))
    out.append("")
    out.append("PER MOMENT, void %")
    names = [n for n, _s in MOMENTS]
    out.append("  %-16s " % "moment"
               + " ".join("%9s" % w for w in report["worlds"]))
    for name in names:
        row = ["  %-16s " % name]
        for _world, data in report["worlds"].items():
            moment = data["moments"].get(name)
            row.append("%8.2f%%" % (moment["void"] * 100.0) if moment
                       else "%9s" % "-")
        out.append(" ".join(row))
    out.append("")
    out.append("PER MOMENT, dark lines crossing the room per 1000 rows")
    out.append("  %-16s " % "moment"
               + " ".join("%9s" % w for w in report["worlds"]))
    for name in names:
        row = ["  %-16s " % name]
        for _world, data in report["worlds"].items():
            moment = data["moments"].get(name)
            row.append("%9.2f" % moment["stripe"]["lines"] if moment
                       else "%9s" % "-")
        out.append(" ".join(row))
    return "\n".join(out)


# --- the whole film, frame by frame ----------------------------------------


def fullfilm(args) -> None:
    """Near-black and stripe score over every delivered frame, not ten of them.

    V30's equivalent measured near-black only. The stripe score is added
    because the grate is a *motion* defect - it is what the eye locks onto
    over a six-second take - so its worst case matters more than its mean.
    """
    import numpy as np
    from PIL import Image

    world = args.world
    folder = os.path.join(FRAMES, f"clip_{world}",
                          f"clip_{args.course}_{args.seed}")
    found = sorted(glob.glob(os.path.join(folder, "frame_*.png")))
    if not found:
        raise SystemExit(f"no clip frames in {folder}; run `clips` first")
    with open(os.path.join(TRACKS, "race2_switchyard_8.cameras.json"),
              encoding="utf-8") as handle:
        cuts = json.load(handle)["cuts"]

    def shot_at(seconds):
        for cut in cuts:
            if float(cut["from"]) <= seconds < float(cut["to"]):
                return str(cut["name"])
        return str(cuts[-1]["name"])

    weights = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    rows, per_shot = [], {}
    for index, path in enumerate(found):
        a = np.asarray(Image.open(path).convert("RGB")).astype(np.float32)
        la = a @ weights
        near = float((la <= 2.0).mean())
        band = slice(int(la.shape[0] * 0.2), int(la.shape[0] * 0.8))
        profile = la[band].mean(axis=1)
        stripe = _stripe_score(profile)
        seconds = index / 60.0
        shot = shot_at(seconds)
        rows.append({"t": round(seconds, 4), "shot": shot,
                     "near_black": near, "stripe": stripe["lines"],
                     "mean_luma": float(la.mean())})
        bucket = per_shot.setdefault(shot, {"near": [], "stripe": [],
                                            "luma": []})
        bucket["near"].append(near)
        bucket["stripe"].append(stripe["lines"])
        bucket["luma"].append(float(la.mean()))

    near_all = np.array([r["near_black"] for r in rows])
    stripe_all = np.array([r["stripe"] for r in rows])
    report = {
        "world": world,
        "environment": dict(WORLDS)[world],
        "frames": len(rows),
        "near_black_mean": float(near_all.mean()),
        "near_black_p99": float(np.quantile(near_all, 0.99)),
        "near_black_max": float(near_all.max()),
        "frames_over_2pct": int((near_all > 0.02).sum()),
        "frames_over_10pct": int((near_all > 0.10).sum()),
        "frames_over_25pct": int((near_all > 0.25).sum()),
        "stripe_mean": float(stripe_all.mean()),
        "stripe_p99": float(np.quantile(stripe_all, 0.99)),
        "stripe_max": float(stripe_all.max()),
        "mean_luma": float(np.mean([r["mean_luma"] for r in rows])),
        "per_shot": {
            shot: {"frames": len(v["near"]),
                   "near_mean": float(np.mean(v["near"])),
                   "near_max": float(np.max(v["near"])),
                   "stripe_mean": float(np.mean(v["stripe"])),
                   "stripe_max": float(np.max(v["stripe"])),
                   "luma_mean": float(np.mean(v["luma"]))}
            for shot, v in per_shot.items()},
    }
    os.makedirs(DOCS, exist_ok=True)
    path = os.path.join(DOCS, f"fullfilm_{world}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1)
    print(f"  {world}: {report['frames']} frames, "
          f"near-black mean {report['near_black_mean'] * 100:.3f}%, "
          f"worst {report['near_black_max'] * 100:.2f}%, "
          f"stripe mean {report['stripe_mean']:.3f}, "
          f"max {report['stripe_max']:.3f}")
    for shot, data in report["per_shot"].items():
        print(f"    {shot:<9} {data['frames']:>4} frames  "
              f"near {data['near_mean'] * 100:>6.3f}% / "
              f"{data['near_max'] * 100:>5.2f}%  "
              f"stripe {data['stripe_mean']:.3f} / {data['stripe_max']:.3f}")
    print(f"  wrote {path}")


# --- sheets and motion ------------------------------------------------------


def sheets(args) -> None:
    from PIL import Image, ImageDraw

    worlds = [w for w in WORLDS
              if not args.worlds or w[0] in args.worlds.split(",")]
    cell = (args.cell, int(args.cell * 16 / 9))
    pad, label = 6, 26
    width = pad + len(MOMENTS) * (cell[0] + pad)
    height = label + len(worlds) * (cell[1] + pad + label)
    sheet = Image.new("RGB", (width, height), (16, 16, 18))
    draw = ImageDraw.Draw(sheet)
    for column, (name, _seconds) in enumerate(MOMENTS):
        draw.text((pad + column * (cell[0] + pad) + 2, 6), name[:16],
                  fill=(190, 190, 190))
    y = label
    for world, environment in worlds:
        draw.text((pad, y + 4), f"{world}  ({environment})",
                  fill=(235, 220, 180))
        for column, (_name, seconds) in enumerate(MOMENTS):
            path = frame_path("frames", world, seconds, args)
            if not os.path.exists(path):
                continue
            tile = Image.open(path).convert("RGB").resize(cell, Image.LANCZOS)
            sheet.paste(tile, (pad + column * (cell[0] + pad), y + label))
        y += cell[1] + pad + label
    os.makedirs(DOCS, exist_ok=True)
    target = os.path.join(DOCS, f"sheet_{args.cell}.png")
    sheet.save(target)
    print(f"  wrote {target}  ({sheet.size[0]}x{sheet.size[1]})")


def clips(args) -> None:
    end = film_end()
    for world, environment in WORLDS:
        if args.worlds and world not in args.worlds.split(","):
            continue
        folder = os.path.join(FRAMES, f"clip_{world}")
        os.makedirs(folder, exist_ok=True)
        run([sys.executable, "tools/race2_render.py", "clip",
             f"--seed={args.seed}", f"--course={args.course}",
             f"--out={TRACKS}", f"--frames={folder}",
             f"--environment={environment}", f"--end={end:.4f}",
             f"--godot={godot_path(args.godot)}"], f"clip {world}")
        encode(os.path.join(folder, f"clip_{args.course}_{args.seed}"),
               os.path.join(EXPORT, f"race2_v301_{world}.mp4"))


def compare(args) -> None:
    """V30 and V30.1 on the same race, side by side, as motion.

    The brief's Part U, and it is the only honest way to judge a *frequency*
    defect: a grate at 5 seams a second is a still that looks textured and a
    shot that looks like a conveyor belt.
    """
    wanted = (args.worlds or "v30,v301").split(",")
    sources = []
    for world in wanted:
        folder = os.path.join(FRAMES, f"clip_{world}",
                              f"clip_{args.course}_{args.seed}")
        if not os.path.isdir(folder):
            raise SystemExit(f"no clip for {world}; run `clips` first")
        sources.append(folder)
    scale = args.scale
    target = os.path.join(EXPORT, args.out or "race2_v301_compare.mp4")
    os.makedirs(EXPORT, exist_ok=True)
    command = [ffmpeg(), "-y"]
    for folder in sources:
        command += ["-framerate", "60", "-i",
                    os.path.join(folder, "frame_%06d.png")]
    chain = "".join(f"[{i}:v]scale={scale}:{int(scale * 16 / 9)}[v{i}];"
                    for i in range(len(sources)))
    joins = "".join(f"[v{i}]" for i in range(len(sources)))
    command += ["-filter_complex",
                f"{chain}{joins}hstack=inputs={len(sources)}[out]",
                "-map", "[out]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-crf", "18", "-preset", "slow", target]
    run(command, "compare")
    print(f"  {target}  ({' | '.join(wanted)})")


def phone(args) -> None:
    """The 270x480 pair the brief's Part V asks for, and the pair side by side.

    Encoded at 270x480 rather than downscaled on playback, so what is judged
    is what a phone actually resolves - which is where a floor-frequency
    change is most visible, because a 2.2-unit seam at 270 px wide is about
    one pixel and a field of them is aliasing.
    """
    for world in (args.worlds or "v30,v301").split(","):
        folder = os.path.join(FRAMES, f"clip_{world}",
                              f"clip_{args.course}_{args.seed}")
        if not os.path.isdir(folder):
            raise SystemExit(f"no clip for {world}; run `clips` first")
        found = sorted(glob.glob(os.path.join(folder, "frame_*.png")))
        first = int(os.path.basename(found[0])[6:12])
        target = os.path.join(EXPORT, f"race2_v301_{world}_phone.mp4")
        os.makedirs(EXPORT, exist_ok=True)
        run([ffmpeg(), "-y", "-framerate", "60", "-start_number", str(first),
             "-i", os.path.join(folder, "frame_%06d.png"),
             "-vf", "scale=270:480:flags=lanczos",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
             "-preset", "slow", "-movflags", "+faststart", target],
            f"phone {world}")
        print(f"  {target}")
    args.scale = 270
    args.out = "race2_v301_phone_compare.mp4"
    compare(args)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("frames", "matte", "measure",
                                         "sheets", "clips", "compare",
                                         "fullfilm", "phone", "all"))
    parser.add_argument("--course", default="switchyard")
    parser.add_argument("--seed", type=int, default=8)
    parser.add_argument("--worlds", default="")
    parser.add_argument("--world", default="v301")
    parser.add_argument("--godot", default="")
    parser.add_argument("--cell", type=int, default=135)
    parser.add_argument("--scale", type=int, default=440)
    parser.add_argument("--out", default="")
    parser.add_argument("--json", default=os.path.join(DOCS, "review.json"))
    parser.add_argument("--txt", default=os.path.join(DOCS, "review.txt"))
    args = parser.parse_args()

    if args.mode in ("frames", "all"):
        render(args, "all")
    if args.mode in ("matte", "all"):
        render(args, "matte")
    if args.mode in ("measure", "all"):
        report = measure(args)
        text = render_measure(report)
        print(text)
        os.makedirs(DOCS, exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=1)
        with open(args.txt, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
        print(f"\nwrote {args.json} and {args.txt}")
    if args.mode in ("sheets", "all"):
        sheets(args)
    if args.mode == "clips":
        clips(args)
    if args.mode == "compare":
        compare(args)
    if args.mode == "fullfilm":
        fullfilm(args)
    if args.mode == "phone":
        phone(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

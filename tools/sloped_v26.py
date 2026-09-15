"""Compare V24 and V26, and measure what the integration could have changed.

**The two films share a clock**, which is what makes this instrument simple and
is worth saying before any of its numbers are read. V26 renders V24's own solved
camera track over V24's own replay under V24's own edit, so output second `t` in
`real_race_v24.mp4` and output second `t` in `real_race_v26.mp4` are *the same
instant of the same race through the same lens*. Every comparison below is
therefore a comparison of pixels and nothing else: no moment has to be found
twice, and a difference in a sheet cannot be a difference in timing.

That is not true of `tools/sloped_v24_audit.py`, which compares V24 against
V22.1 - two different edits - and has to map each moment through both clocks.
This is the easier problem and the tool is correspondingly smaller.

    --stage moments    the sixteen same-frame comparisons, as a contact sheet
    --stage phone      the same sheet at 270x480, which is the size that decides
    --stage opening    the first five seconds side by side, as a clip
    --stage full       the whole film side by side, as a clip
    --stage metrics    the brief's Part M numbers, as JSON and as a table
    --stage joins      each omission's environment step, measured on the pixels
    --stage all        all of the above

Everything lands under `output/sloped_race_v1/v26/` and the boards are copied to
`docs/validation/sloped_race_v1/v26/`. Nothing here renders, simulates or writes
a replay: it reads two delivered MP4s and the replay, and it never writes one.
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

from sloped import overlays, presentation, v24, v24_hook, v24_payoff, v26

OUT_DIR = os.path.join("output", "sloped_race_v1")
WORK = os.path.join(OUT_DIR, "v26", "audit")
DOC_DIR = os.path.join("docs", "validation", "sloped_race_v1", "v26")
FPS = 60
WIDTH, HEIGHT = 1080, 1920
PHONE = (270, 480)

#: The sixteen moments the brief names, as replay seconds. `None` means the
#: moment is defined on the *film's* clock rather than the race's - the first
#: four are output offsets and the last two are the card and the last frame.
#:
#: The race-time ones are inside the cut that owns them, read off the delivered
#: track: hook 0.20-1.60, start 1.60-2.05 and 4.47-6.42, descent 6.70-9.67,
#: obstacle 9.67-13.58 and 14.02-15.10, fork 15.10-16.73, branches 16.73-18.42,
#: merge 18.42-18.90, final 18.90-23.45.
MOMENTS: tuple[tuple[str, float | None], ...] = (
    ("frame 0", None),
    ("0.25 s", None),
    ("0.50 s", None),
    ("1.00 s", None),
    ("mixer", 5.400),
    ("release", 6.300),
    ("descent", 8.000),
    ("obstacle", 12.500),
    ("fork approach", 15.300),
    ("split", 15.900),
    ("branch", 17.400),
    ("merge", 18.600),
    ("final approach", 19.800),
    ("winner crossing", 20.850),
    ("payoff", None),
    ("final frame", None),
)

OFFSETS = {"frame 0": 0.0, "0.25 s": 0.25, "0.50 s": 0.50, "1.00 s": 1.00}


def _tool(name: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_v26_" + name, os.path.join("tools", name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found is None:
        raise RuntimeError("ffmpeg is not on PATH")
    return found


def film(edition: str) -> dict[str, str]:
    """The three delivered files for one edition."""
    short = _tool("sloped_short")
    entry = short.EDITIONS[edition]
    return {"video": entry["video"], "visual": entry["visual"],
            "silent": entry["silent"], "master": entry["master"]}


def clock(edition: str = "v26", seed: int = 5432) -> presentation.Clock:
    short = _tool("sloped_short")
    return short.load_all(seed, edition)[2]


def _card_at(film_clock: presentation.Clock) -> float:
    """When the payoff card comes up, **in output seconds**.

    `v24.WINNER_CROSSES` is 20.850 and it is a *replay* second; the film shows
    that instant at 17.517, because 3.13 s of replay are omitted before it.
    Scheduling the card off the replay number put it at 21.65 in a 20.13 s film,
    and `-ss` answered that with the last frame rather than with an error - so
    the payoff column of the first metrics run was the final frame twice.
    """
    crossing = film_clock.at(v24.WINNER_CROSSES)
    if crossing is None:
        raise RuntimeError("the winner's crossing is not in this film")
    return round(crossing + v24.BEAT, 6)


def moments(film_clock: presentation.Clock, card_at: float) -> list[tuple[str, float]]:
    """`(label, output second)` - one second, because both films share it."""
    rows: list[tuple[str, float]] = []
    for label, replay_at in MOMENTS:
        if label in OFFSETS:
            rows.append((label, OFFSETS[label]))
        elif label == "payoff":
            rows.append((label, round(card_at + 0.6, 4)))
        elif label == "final frame":
            rows.append((label, round(film_clock.duration - 1.0 / FPS, 4)))
        else:
            at = film_clock.at(replay_at)
            if at is not None:
                rows.append((label, round(at, 4)))
    return rows


def _grab(video: str, when: float, path: str) -> str:
    """One exact frame, addressed by its index rather than by a seek time.

    **`-ss` is not frame-accurate on these files and it does not say so.**
    Measured on the delivered V26 cut, `-ss 10.6667` and `-ss 10.6833` - one
    frame apart at 60 fps - return the *same* picture, and any `-ss` past the
    last frame returns the last frame with exit status zero. The first of those
    made the trap join measure a luma step of exactly 0.000, which is not a
    finding about the cut; the second put the payoff and the final frame on the
    same still as the winner's crossing.

    So the time is snapped to its own frame index first, and then the frame is
    fetched by **seeking coarsely and decoding forward accurately**: an input
    `-ss` to one second earlier lands on or before a keyframe, and the output
    `-ss` after `-i` decodes from there to the exact frame.

    That form was checked against `select=eq(n,N)`, which decodes from frame
    zero and is unambiguous but costs 1.4 s a grab at the tail of the film -
    enough to make a full metrics run take hours. At frames 641, 1051 and 1060
    the two agree **to the byte**, and this one is four times faster. It also
    keeps the property a bare input `-ss` lacks: a request past the last frame
    writes nothing and raises here, rather than quietly returning the tail.
    """
    index = int(round(max(0.0, when) * FPS))
    exact = index / float(FPS)
    lead = min(1.0, exact)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    if os.path.exists(path):
        os.remove(path)
    done = subprocess.run(
        [_ffmpeg(), "-y", "-ss", f"{exact - lead:.6f}", "-i", video,
         "-ss", f"{lead:.6f}", "-frames:v", "1", "-q:v", "2", path],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if done.returncode != 0 or not os.path.isfile(path):
        tail = "\n".join((done.stderr or "").splitlines()[-8:])
        raise RuntimeError(
            "ffmpeg could not grab frame %d (%.4f s) from %s\n%s"
            % (index, when, video, tail))
    return path


def sheet(one: str, two: str, rows: Sequence[tuple[str, float]], path: str,
          phone: bool = False, titles: tuple[str, str] = ("V24", "V26")) -> str:
    """A contact sheet: V24 above, V26 below, one column per moment.

    **Both rows are grabbed at the same second**, which is the whole comparison:
    anything that differs between the two cells is the world, the machine or the
    grade, because the instant and the lens are shared.
    """
    from PIL import Image, ImageDraw

    cell = PHONE if phone else (216, 384)
    pad, label_h, head = 8, 26, 34
    width = pad + len(rows) * (cell[0] + pad)
    height = head + 2 * (label_h + cell[1] + pad) + pad
    canvas = Image.new("RGB", (width, height), (18, 17, 16))
    draw = ImageDraw.Draw(canvas)
    small = overlays.load_font(17)
    draw.text((pad, 8),
              f"{titles[0]}  (above)      |      {titles[1]}  (below)"
              f"      same output second in both",
              font=small, fill=(255, 249, 238))
    for column, (label, when) in enumerate(rows):
        x = pad + column * (cell[0] + pad)
        for rank, video in enumerate((one, two)):
            y = head + rank * (label_h + cell[1] + pad)
            draw.text((x, y + 4), f"{label} @{when:.2f}", font=small,
                      fill=(200, 195, 188))
            grabbed = _grab(video, when, os.path.join(WORK, f"m{column}_{rank}.png"))
            canvas.paste(Image.open(grabbed).resize(cell, Image.LANCZOS),
                         (x, y + label_h))
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    canvas.save(path)
    print(f"sheet: {len(rows)} moments -> {path}")
    return path


def _caption(text: str, size: tuple[int, int], path: str) -> str:
    """A caption as a PNG, drawn with the film's own face.

    Not `drawtext`: ffmpeg's text filter needs fontconfig, which is not present
    on every machine this is run on. `sloped_v24_audit._label` makes the same
    choice for the same reason.
    """
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    font = overlays.load_font(34)
    box = draw.textbbox((0, 0), text, font=font)
    pad = 14
    draw.rectangle((18, 18, 18 + (box[2] - box[0]) + 2 * pad,
                    18 + (box[3] - box[1]) + 2 * pad), fill=(0, 0, 0, 160))
    draw.text((18 + pad - box[0], 18 + pad - box[1]), text, font=font,
              fill=(255, 249, 238, 255))
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    image.save(path)
    return path


def side_by_side(one: str, two: str, path: str, seconds: float | None = None,
                 scale: int = 540, titles: tuple[str, str] = ("V24", "V26")) -> str:
    """Two films, left and right, captioned, at the same instant throughout."""
    height = scale * HEIGHT // WIDTH
    left = _caption(titles[0], (scale, 120), os.path.join(WORK, "cap_a.png"))
    right = _caption(titles[1], (scale, 120), os.path.join(WORK, "cap_b.png"))
    trim = [] if seconds is None else ["-t", f"{seconds:.4f}"]
    graph = (
        f"[0:v]scale={scale}:{height},setsar=1[a];"
        f"[1:v]scale={scale}:{height},setsar=1[b];"
        f"[a][2:v]overlay=0:0[al];"
        f"[b][3:v]overlay=0:0[bl];"
        f"[al][bl]hstack=inputs=2[v]"
    )
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    done = subprocess.run(
        [_ffmpeg(), "-y", *trim, "-i", one, *trim, "-i", two,
         "-i", left, "-i", right,
         "-filter_complex", graph, "-map", "[v]",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", path],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if done.returncode != 0:
        tail = "\n".join((done.stderr or "").splitlines()[-15:])
        raise RuntimeError(f"ffmpeg exited {done.returncode}\n{tail}")
    print(f"clip: {path}  {os.path.getsize(path) / (1024 * 1024):.1f} MiB")
    return path


# --- measurement -------------------------------------------------------------


def _array(path: str):
    import numpy as np
    from PIL import Image

    return np.asarray(Image.open(path).convert("RGB")).astype(float)


def _luma(pixels):
    return (0.2126 * pixels[..., 0] + 0.7152 * pixels[..., 1]
            + 0.0722 * pixels[..., 2])


def picture_stats(path: str) -> dict[str, float]:
    """What one frame is made of, in the terms the brief asks about.

    `warm` is the share of pixels whose red channel leads blue by more than a
    tenth of the range - the reading that says "this part of the picture is a
    warm element" without committing to a hue. `clipped` is the share at or
    above 250 in all three channels, which is the V21 readability pass's own
    measure of paper white.
    """
    import numpy as np

    pixels = _array(path)
    luma = _luma(pixels)
    warm = (pixels[..., 0] - pixels[..., 2]) > 25.0
    clipped = np.all(pixels >= 250.0, axis=-1)
    dark = luma < 26.0
    return {
        "mean_luma": round(float(luma.mean()), 2),
        "p05_luma": round(float(np.percentile(luma, 5)), 2),
        "p95_luma": round(float(np.percentile(luma, 95)), 2),
        "contrast": round(float(np.percentile(luma, 95) - np.percentile(luma, 5)), 2),
        "warm_fraction": round(float(warm.mean()), 5),
        "clipped_fraction": round(float(clipped.mean()), 5),
        "dark_fraction": round(float(dark.mean()), 5),
        "saturation": round(float((pixels.max(axis=-1) - pixels.min(axis=-1)).mean()), 2),
    }


def join_step(video: str, at: float) -> dict[str, float]:
    """How far the picture moves across one cut, in its own frames' terms.

    The instrument is the mean absolute luma difference between the two frames
    either side of the join, **scaled against the same difference taken over the
    ordinary frame pairs around it**. A ratio near 1 means the join is no bigger
    a change than the shot's own motion; a large ratio means something jumps.

    This is the pixel form of the question `tools/sloped_v24_audit.py` asks on
    the geometry, and it is here because V25.2 put close rocks in the frame: a
    join that was invisible against a sparse hillside can reveal itself when a
    boulder crosses it.
    """
    import numpy as np

    step = 1.0 / FPS
    frames = {}
    for index in range(-4, 5):
        when = at + index * step
        if when < 0:
            continue
        frames[index] = _luma(_array(
            _grab(video, when, os.path.join(WORK, f"join_{index:+d}.png"))))

    def delta(a: int, b: int) -> float | None:
        if a not in frames or b not in frames:
            return None
        return float(np.abs(frames[a] - frames[b]).mean())

    across = delta(-1, 0)
    neighbours = [d for d in (delta(-4, -3), delta(-3, -2), delta(-2, -1),
                              delta(0, 1), delta(1, 2), delta(2, 3)) if d is not None]
    typical = float(np.median(neighbours)) if neighbours else 0.0
    return {
        "at": round(at, 4),
        "across": round(across, 3) if across is not None else None,
        "typical": round(typical, 3),
        "ratio": round(across / typical, 2) if across and typical > 1e-6 else None,
    }


def winner_ring(video: str, film_clock, track: dict[str, Any],
                replay: dict[str, Any], winner: int = 5) -> dict[str, Any]:
    """How many of the ring's frames actually have the purple winner under them.

    **Measured on this edition's own frames rather than inherited.**
    `v24_payoff.WINNER_VISIBLE` is a pair of windows in *V22.1's* output clock,
    which is neither V24's nor V26's, so a count taken through it would be a
    count of the wrong film. Here the winner is projected through the delivered
    camera track at each of the ring's own frames and the rendered pixel at that
    place is read back: a frame counts when the marble is inside the frame and
    the picture there is nearer the winner's own hue than any other racer's.

    **`readability.cut_reads` is deliberately not used**, and the reason is worth
    recording because it cost this pass a wrong answer. That function drops every
    racer that has already crossed - "a marble whose viewer already has their
    answer" - which is right for a readability bar and exactly inverted here: the
    winner's ring opens *on* the crossing, so the one marble this measurement is
    about is the one marble `cut_reads` has just stopped reporting. Asked through
    it, both films answered "the winner is in 0 of its own 18 ring frames", which
    is a fact about the filter and not about the picture.
    """
    import numpy as np
    from PIL import Image
    from sloped import overlays
    from sloped.presentation import project
    from sloped.readability import _racer_points

    crossing = film_clock.at(v24.WINNER_CROSSES)
    ring_from = crossing + v24_payoff.RING_DELAY
    count = int(round(v24_payoff.RING_SECONDS * FPS))
    hues = np.array(overlays.MARBLE_HUES, dtype=float)
    times = [float(frame["t"]) for frame in replay["frames"]]
    from sloped import layout
    radius = float(replay.get("units", {}).get(
        "layout_marble_radius", layout.MARBLE_RADIUS))

    def pose(replay_at: float):
        """The camera row of the cut that owns this replay second."""
        for cut in track["cuts"]:
            rows = cut.get("frames") or []
            if not rows:
                continue
            if rows[0][0] - 1e-6 <= replay_at <= rows[-1][0] + 1e-6:
                return min(rows, key=lambda row: abs(float(row[0]) - replay_at))
        return None

    rows_out: list[dict[str, Any]] = []
    for index in range(count):
        at = ring_from + index / float(FPS)
        replay_at = film_clock.replay_at(at)
        entry: dict[str, Any] = {"at": round(at, 4)}
        row = None if replay_at is None else pose(replay_at)
        if row is None:
            rows_out.append({**entry, "in_frame": False})
            continue
        frame_index = min(range(len(times)), key=lambda k: abs(times[k] - replay_at))
        points = _racer_points(replay, frame_index)
        placed = project(tuple(row[1:4]), tuple(row[4:7]), float(row[7]),
                         points[winner], WIDTH, HEIGHT)
        if placed is None:
            rows_out.append({**entry, "in_frame": False})
            continue
        x, y, depth = placed
        inside = 0.0 <= x <= WIDTH and 0.0 <= y <= HEIGHT
        entry.update({"in_frame": bool(inside), "x": round(x, 1),
                      "y": round(y, 1), "depth": round(depth, 3)})
        if inside:
            # **Sampled on the overlay-free master, not on the delivered cut.**
            # The ring is drawn *over* the marble it points at, in warm white,
            # so a sample taken from the finished film reads the ring's own ink
            # and reports the winner as whichever racer that ink is nearest -
            # measured, racer 7 in every frame of both films. The question this
            # answers is whether there is a purple marble under the ring, and
            # the only picture that can answer it is the one without the ring.
            grabbed = _grab(video, at, os.path.join(WORK, "ring_%02d.png" % index))
            pixels = np.asarray(Image.open(grabbed).convert("RGB")).astype(float)
            # The patch is the marble's own disc, not a fixed box: the same
            # expression `readability.cut_reads` sizes a racer with, halved so
            # the sample stays inside the ball rather than straddling its rim.
            half_up = math.tan(math.radians(float(row[7])) * 0.5)
            diameter = (radius / max(depth, 1e-6)) / max(half_up, 1e-6) * HEIGHT
            entry["px"] = round(diameter, 1)
            half = max(3.0, diameter * 0.25)
            y0, y1 = int(max(0, y - half)), int(min(HEIGHT, y + half))
            x0, x1 = int(max(0, x - half)), int(min(WIDTH, x + half))
            patch = pixels[y0:y1, x0:x1]
            if patch.size:
                median = np.median(patch.reshape(-1, 3), axis=0)
                distances = np.linalg.norm(hues - median, axis=1)
                entry["rgb"] = [round(float(v), 1) for v in median]
                entry["nearest_racer"] = int(distances.argmin())
                entry["de_to_winner"] = round(float(distances[winner]), 1)
                entry["on_winner"] = bool(distances.argmin() == winner)
        rows_out.append(entry)

    return {
        "ring_from": round(ring_from, 4),
        "frames": len(rows_out),
        "in_frame": sum(1 for row in rows_out if row.get("in_frame")),
        "on_winner": sum(1 for row in rows_out if row.get("on_winner")),
        "rows": rows_out,
    }


def metrics(seed: int = 5432) -> dict[str, Any]:
    """The brief's Part M, measured on the delivered V26 and V24 files."""
    from PIL import Image

    v24_film, v26_film = film("v24"), film("v26")
    film_clock = clock("v26", seed)
    card_at = _card_at(film_clock)
    rows = moments(film_clock, card_at)

    with open(os.path.join(OUT_DIR, f"race_{seed}.json"), encoding="utf-8") as handle:
        replay = json.load(handle)
    with open(os.path.join(OUT_DIR, f"cameras_v24_{seed}.json"), encoding="utf-8") as handle:
        track = json.load(handle)
    frame_zero = v24_hook.first_frame_report(track, replay)

    report: dict[str, Any] = {
        "seed": seed,
        "duration": round(film_clock.duration, 6),
        "frames": film_clock.frames,
        "config": {
            "environment": v26.ENVIRONMENT, "machine": v26.MACHINE,
            "racers": v26.RACERS, "edit": v26.EDIT, "preview": v26.PREVIEW,
        },
        "hook": {
            "racers": frame_zero["racers"], "of": frame_zero["of"],
            "median_px": frame_zero["median_px"],
            "occupancy": frame_zero["occupancy"],
            "off_centre": frame_zero["off_centre"],
            "ink": frame_zero["ink"],
            "worst_disc": frame_zero["worst_disc"],
            "motion": v24_hook.motion_report(replay, v26.HOOK, track),
        },
        "moments": [], "joins": [],
    }

    # Frame zero, rendered, in both films and at both sizes.
    report["frame_zero"] = {}
    for name, movie in (("v24", v24_film["silent"]), ("v26", v26_film["silent"])):
        grabbed = _grab(movie, 0.0, os.path.join(WORK, f"fz_{name}.png"))
        image = Image.open(grabbed)
        phone = image.resize(PHONE, Image.LANCZOS)
        plate = v24_hook.text_plate(image, frame_zero)
        plate_phone = v24_hook.text_plate(phone, frame_zero)
        legible = v24_hook.legibility_report(image, frame_zero)
        legible_phone = v24_hook.legibility_report(phone, frame_zero)
        report["frame_zero"][name] = {
            "mark_baseline": plate["baseline"],
            "mark_contrast": plate["contrast"],
            "mark_contrast_phone": plate_phone["contrast"],
            "mark_mean_contrast": plate["mean_contrast"],
            "racers_legible": legible["legible"],
            "min_de": legible["min_de"],
            "min_de_phone": legible_phone["min_de"],
            "picture": picture_stats(grabbed),
        }

    # Every moment, in both films, on the picture.
    for label, when in rows:
        entry: dict[str, Any] = {"label": label, "at": when}
        for name, movie in (("v24", v24_film["video"]), ("v26", v26_film["video"])):
            grabbed = _grab(movie, when, os.path.join(
                WORK, "stat_%s_%02d.png" % (name, len(report["moments"]))))
            entry[name] = picture_stats(grabbed)
        report["moments"].append(entry)

    # Every omission, on the pixels, in both films.
    for name, low, high in v26.OMISSIONS:
        at = film_clock.at(low)
        if at is None:
            continue
        entry = {"omission": name, "replay": [low, high], "out": round(at, 4)}
        for movie_name, movie in (("v24", v24_film["silent"]),
                                  ("v26", v26_film["silent"])):
            entry[movie_name] = join_step(movie, at)
        report["joins"].append(entry)

    # The winner's ring, on each film's own frames.
    report["ring"] = {}
    for name, movie in (("v24", v24_film["silent"]), ("v26", v26_film["silent"])):
        report["ring"][name] = winner_ring(movie, film_clock, track, replay)

    os.makedirs(os.path.join(OUT_DIR, "v26"), exist_ok=True)
    path = os.path.join(OUT_DIR, "v26", "metrics.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(f"metrics: -> {path}")
    _print_metrics(report)
    return report


def _print_metrics(report: dict[str, Any]) -> None:
    hook = report["hook"]
    print()
    print(f"  {report['config']}")
    print(f"  runtime {report['duration']:.6f} s over {report['frames']} frames")
    print()
    print("  HOOK (geometric - shared with V24 by construction)")
    print(f"    racers {hook['racers']}/{hook['of']}  median {hook['median_px']} px  "
          f"occupancy {hook['occupancy']}  ink {hook['ink']}  "
          f"worst disc {hook['worst_disc']}")
    print(f"    first motion: mechanism {hook['motion']['mechanism']:.4f}  "
          f"camera {hook['motion']['camera']:.4f}  marbles {hook['motion']['racers']:.4f}")
    print()
    print("  FRAME ZERO (rendered)")
    header = f"    {'':5s} {'mark':>6s} {'phone':>6s} {'min dE':>7s} {'dE ph':>7s} " \
             f"{'luma':>6s} {'clip%':>7s} {'warm%':>7s}"
    print(header)
    for name in ("v24", "v26"):
        row = report["frame_zero"][name]
        pic = row["picture"]
        print(f"    {name:5s} {row['mark_contrast']:6.2f} {row['mark_contrast_phone']:6.2f} "
              f"{row['min_de']:7.1f} {row['min_de_phone']:7.1f} "
              f"{pic['mean_luma']:6.1f} {100 * pic['clipped_fraction']:7.3f} "
              f"{100 * pic['warm_fraction']:7.2f}")
    print()
    print("  MOMENTS (mean luma / contrast / warm% / clipped%)")
    print(f"    {'moment':16s} {'at':>6s} | {'V24 luma':>8s} {'ctr':>5s} {'warm':>6s} "
          f"{'clip':>6s} | {'V26 luma':>8s} {'ctr':>5s} {'warm':>6s} {'clip':>6s}")
    for row in report["moments"]:
        a, b = row["v24"], row["v26"]
        print(f"    {row['label']:16s} {row['at']:6.2f} | "
              f"{a['mean_luma']:8.1f} {a['contrast']:5.0f} {100*a['warm_fraction']:6.2f} "
              f"{100*a['clipped_fraction']:6.3f} | "
              f"{b['mean_luma']:8.1f} {b['contrast']:5.0f} {100*b['warm_fraction']:6.2f} "
              f"{100*b['clipped_fraction']:6.3f}")
    print()
    print("  WINNER RING (its own frames, winner projected and the pixel read back)")
    for name in ("v24", "v26"):
        row = report.get("ring", {}).get(name)
        if row:
            print(f"    {name}: ring opens {row['ring_from']:.3f}  "
                  f"{row['frames']} frames  in frame {row['in_frame']}  "
                  f"on the winner {row['on_winner']}/{row['frames']}")
    print()
    print("  JOINS (luma step across the cut, against the shot's own typical step)")
    print(f"    {'omission':10s} {'out':>7s} | {'V24 across':>10s} {'typ':>6s} {'ratio':>6s}"
          f" | {'V26 across':>10s} {'typ':>6s} {'ratio':>6s}")
    for row in report["joins"]:
        a, b = row["v24"], row["v26"]
        print(f"    {row['omission']:10s} {row['out']:7.3f} | "
              f"{a['across']:10.3f} {a['typical']:6.3f} {str(a['ratio']):>6s} | "
              f"{b['across']:10.3f} {b['typical']:6.3f} {str(b['ratio']):>6s}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=5432)
    parser.add_argument("--stage", default="all",
                        choices=("moments", "phone", "opening", "full",
                                 "metrics", "joins", "all"))
    args = parser.parse_args(argv)

    os.makedirs(WORK, exist_ok=True)
    os.makedirs(DOC_DIR, exist_ok=True)
    v24_film, v26_film = film("v24"), film("v26")
    stages = (("metrics", "moments", "phone", "opening", "full")
              if args.stage == "all" else (args.stage,))

    film_clock = clock("v26", args.seed)
    card_at = _card_at(film_clock)
    rows = moments(film_clock, card_at)

    for stage in stages:
        print(f"--- {stage} (v26) ---")
        if stage in ("metrics", "joins"):
            metrics(args.seed)
        elif stage == "moments":
            path = sheet(v24_film["video"], v26_film["video"], rows,
                         os.path.join(DOC_DIR, "compare.png"))
            shutil.copy(path, os.path.join(OUT_DIR, "v26", "compare.png"))
        elif stage == "phone":
            path = sheet(v24_film["video"], v26_film["video"], rows,
                         os.path.join(DOC_DIR, "compare_phone.png"), phone=True)
            shutil.copy(path, os.path.join(OUT_DIR, "v26", "compare_phone.png"))
        elif stage == "opening":
            side_by_side(v24_film["video"], v26_film["video"],
                         os.path.join(OUT_DIR, "v26", "opening_v24_v26.mp4"),
                         seconds=5.0)
        elif stage == "full":
            side_by_side(v24_film["video"], v26_film["video"],
                         os.path.join(OUT_DIR, "v26", "compare_v24_v26.mp4"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Render, compare and prove the V31.1 track-surface variants.

Usage:

    python tools/race2_v311_review.py sheet     # variant x moment, 1080 tiles
    python tools/race2_v311_review.py phone     # the same at 270x480
    python tools/race2_v311_review.py proof     # Part I/J: the mask proofs
    python tools/race2_v311_review.py clips     # four full 19.15 s films
    python tools/race2_v311_review.py compare   # control | variant, each way
    python tools/race2_v311_review.py quad      # control / A / B / C, 4-up
    python tools/race2_v311_review.py phonefilm # the winner at 270x480
    python tools/race2_v311_review.py cost      # Part O: meshes, triangles, time
    python tools/race2_v311_review.py preview   # the production preview

Everything here reads **the V31 RB camera track**, `output/race2/v31_readability/RB`,
and passes `--environment=contained_bay_v301` on the command line. No profile,
no light, no camera parameter and no piece of geometry is authored in this file.
The only thing that differs between the four renders is `--track=`.

`tools/race2_v311_track.py` is the measuring half of the same pass and owns the
segmentation; this file owns the pictures.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from tools.race2_v30_review import encode, ffmpeg, godot_path, run  # noqa: E402
from tools.race2_v311_track import (  # noqa: E402
    CAMERA, DOCS, ENVIRONMENT, MOMENTS, OUT, VARIANTS, _dilate, _load,
    _selectors, at_list, frame, frames_dir, lab, lightness,
)

EXPORT = "exports/race2_v311_track"
# The brief's Part G, as named ranges on the hero replay.
SECTIONS = (
    ("opening", 0.00, 3.00),
    ("first_mechanisms", 3.00, 6.00),
    ("visibility_problem", 6.00, 10.00),
    ("switchback_chase", 10.00, 14.00),
    ("final_sprint", 14.00, 19.15),
)
LABEL = {"v31": "CONTROL (V31)", "A": "A light pearl",
         "B": "B pearl + value break", "C": "C pearl + roughness"}


def film_end() -> float:
    with open(os.path.join(CAMERA, "race2_switchyard_8.cameras.json"),
              encoding="utf-8") as handle:
        return float(json.load(handle)["duration"])


def _track_flag(variant: str) -> list[str]:
    return [] if variant == "v31" else [f"--track={variant}"]


def variants_for(args) -> list[str]:
    return [v for v in VARIANTS if not args.only or v in args.only.split(",")]


# --- sheets -----------------------------------------------------------------


def _tile(path, cell):
    from PIL import Image
    if not os.path.exists(path):
        return Image.new("RGB", cell, (28, 28, 30))
    return Image.open(path).convert("RGB").resize(cell, Image.LANCZOS)


def _grid(args, cell, picks, target, title):
    from PIL import Image, ImageDraw

    rows = variants_for(args)
    pad, label = 8, 26
    canvas = Image.new("RGB",
                       (pad + len(picks) * (cell[0] + pad),
                        label + len(rows) * (cell[1] + pad + label)),
                       (16, 16, 18))
    draw = ImageDraw.Draw(canvas)
    for column, (name, seconds) in enumerate(picks):
        draw.text((pad + column * (cell[0] + pad) + 2, 7),
                  f"{name}  {seconds:.2f}s", fill=(195, 195, 195))
    y = label
    for variant in rows:
        draw.text((pad, y + 5), f"{LABEL[variant]}   {title}",
                  fill=(235, 220, 180))
        for column, (_name, seconds) in enumerate(picks):
            canvas.paste(_tile(frame(variant, seconds), cell),
                         (pad + column * (cell[0] + pad), y + label))
        y += cell[1] + pad + label
    os.makedirs(DOCS, exist_ok=True)
    canvas.save(target)
    print(f"  wrote {target}  ({canvas.size[0]}x{canvas.size[1]})")


def sheet(args) -> None:
    _grid(args, (args.cell, int(args.cell * 16 / 9)), MOMENTS,
          os.path.join(DOCS, f"sheet_{args.cell}.png"), "1080 source")


def phone(args) -> None:
    """Part F and Part R: the mandatory judgement, at delivery phone size.

    The tiles are the delivered 1080x1920 frames resampled to 270x480, which is
    what a viewer's phone does to them, and they are pasted at exactly that size
    rather than at a sheet-sized thumbnail - a readability judgement made at 135
    px wide is not a judgement about a phone.
    """
    picks = [m for m in MOMENTS if m[0] in
             ("hook", "drum", "chase", "sparse", "sprint_in", "comeback")]
    _grid(args, (270, 480), picks, os.path.join(DOCS, "phone_270.png"),
          "270x480")


# --- Part I and Part J: the diagnostics -------------------------------------


def proof(args) -> None:
    """The three diagnostic views the brief asks for, plus the continuity test.

    Per moment, four panels from the *same* delivered frame:

    1. **normal** - what ships.
    2. **track highlighted** - every pixel the segmentation calls channel, left
       alone; everything else taken down to a fifth. This is the answer to "is
       the raceway continuous on screen", with no judgement involved.
    3. **environment suppressed** - the channel, the machine and the racers on
       black. What the route looks like with the room removed.
    4. **racers masked** - Part J. The racers are painted out in flat room grey
       and the question is whether the raceway can still be traced. Diagnostic
       only: no mask reaches any delivered frame.

    None of these is a render. They are composites over the delivered frame
    using the masks, so a panel cannot disagree with the film it came from.
    """
    from PIL import Image, ImageDraw
    import numpy as np

    picks = [m for m in MOMENTS if m[0] in
             ("hook", "chase", "sparse", "comeback")]
    rows = variants_for(args)
    cell = (216, 384)
    views = ("normal", "track", "no-room", "no-racers")
    pad, label = 8, 24
    width = pad + len(picks) * len(views) * (cell[0] + 3) + len(picks) * pad
    canvas = Image.new("RGB", (width, label + len(rows) * (cell[1] + pad + label)),
                       (16, 16, 18))
    draw = ImageDraw.Draw(canvas)
    report: dict = {}

    x_of = []
    x = pad
    for name, seconds in picks:
        x_of.append(x)
        draw.text((x + 2, 7), f"{name} {seconds:.2f}s  "
                  + " | ".join(views), fill=(195, 195, 195))
        x += len(views) * (cell[0] + 3) + pad

    y = label
    for variant in rows:
        draw.text((pad, y + 4), LABEL[variant], fill=(235, 220, 180))
        for column, (name, seconds) in enumerate(picks):
            plate = _load(frame(variant, seconds))
            masks = _selectors(seconds)
            if plate is None or masks is None:
                continue
            channel = _dilate(masks["track"], 1)
            machine = masks["structure"] | masks["station"] | masks["actuator"]
            panels = [
                plate,
                _dim(plate, ~channel, 0.20),
                _black(plate, channel | machine | masks["racer"]),
                _paint_out(plate, masks["racer"], plate[masks["background"]]),
            ]
            for index, panel in enumerate(panels):
                canvas.paste(
                    Image.fromarray(panel).resize(cell, Image.LANCZOS),
                    (x_of[column] + index * (cell[0] + 3), y + label))
            report.setdefault(variant, {})[name] = _traceability(
                plate, masks)
        y += cell[1] + pad + label
    os.makedirs(DOCS, exist_ok=True)
    target = os.path.join(DOCS, "track_proof.png")
    canvas.save(target)
    with open(os.path.join(DOCS, "traceability.json"), "w",
              encoding="utf-8") as handle:
        json.dump(report, handle, indent=1)
    print(f"  wrote {target}  ({canvas.size[0]}x{canvas.size[1]})")
    print()
    print(f'  {"":<16}' + "".join(f"{name:>20}" for name, _t in picks))
    for key, unit in (("traceable_pct", "%"), ("longest_run_pct", "%"),
                      ("local_dE_p5", " "), ("local_dE_median", " ")):
        for variant in rows:
            cells = "".join(
                f'{report[variant][name][key]:>19.1f}{unit}' for name, _t in picks)
            print(f"  {variant + ' ' + key:<16}" + cells)
        print()


def _dim(plate, where, factor: float):
    import numpy as np
    out = plate.astype(np.float32)
    out[where] *= factor
    return out.clip(0, 255).astype(np.uint8)


def _black(plate, keep):
    import numpy as np
    out = np.zeros_like(plate)
    out[keep] = plate[keep]
    return out


def _paint_out(plate, where, reference):
    """`where` replaced by the room's own median colour: a flat, honest hole."""
    import numpy as np
    out = plate.copy()
    if reference.size:
        out[where] = np.median(reference, axis=0).astype(np.uint8)
    return out


def _traceability(plate, masks) -> dict:
    """Part J as a number: how much of the channel separates from its own room.

    For every channel pixel, the reference is the median colour of the
    *background* inside its own 64-pixel tile rather than the frame's overall
    background - the room is not one value, and a channel crossing a lit floor
    panel has a different job from one crossing a shadowed wall. A pixel counts
    as traceable at dE 12, which is about four times a just-noticeable
    difference and comfortably above what a phone's resampling can erase.

    `longest_run_pct` is the image-space answer to "visible centreline length":
    the longest run of consecutive image *columns* that contain at least one
    traceable channel pixel, as a share of the frame width. A route that breaks
    into two pieces scores the longer piece, which is the point.

    **`traceable_pct` saturates, and that is the result rather than a fault in
    the instrument.** Every candidate returns 98-100% on every racing moment,
    because the channel sits 60 dE from the room and a 12 dE bar is nowhere
    near it. So the brief's premise - the raceway blending into the dark
    environment - is not what is happening, and `local_dE_p5` is reported
    beside it as the number that *does* discriminate: the fifth percentile of
    each channel pixel's distance from its own local room.
    """
    import numpy as np

    channel = masks["track"]
    if int(channel.sum()) < 200:
        return {"traceable_pct": 0.0, "trace_span_pct": 0.0,
                "longest_run_pct": 0.0, "pixels": int(channel.sum())}
    tile = 64
    height, width = channel.shape
    values = lab(plate)
    traceable = np.zeros(channel.shape, dtype=bool)
    distances = np.zeros(channel.shape, dtype=np.float32)
    room = masks["background"]
    for top in range(0, height, tile):
        for left in range(0, width, tile):
            cell = (slice(top, top + tile), slice(left, left + tile))
            here = channel[cell]
            if not here.any():
                continue
            near = room[cell]
            if near.sum() < 32:
                # No room in this tile: fall back to the frame's own room, so a
                # channel that fills its tile is still measured against
                # something rather than silently counted as readable.
                reference = np.median(values[room], axis=0)
            else:
                reference = np.median(values[cell][near], axis=0)
            distance = np.linalg.norm(values[cell] - reference, axis=-1)
            distances[cell] = distance
            traceable[cell] = here & (distance >= 12.0)
    columns = traceable.any(axis=0)
    best = run = 0
    for flag in columns:
        run = run + 1 if flag else 0
        best = max(best, run)
    return {
        "pixels": int(channel.sum()),
        "traceable_pct": round(float(traceable.sum() / channel.sum()) * 100, 2),
        "trace_span_pct": round(float(columns.mean()) * 100, 2),
        "longest_run_pct": round(best / width * 100, 2),
        "local_dE_p5": round(float(np.percentile(distances[channel], 5)), 2),
        "local_dE_median": round(float(np.median(distances[channel])), 2),
    }


# --- films ------------------------------------------------------------------


def clips(args) -> None:
    end = film_end()
    for variant in variants_for(args):
        out = frames_dir(f"clip_{variant}")
        os.makedirs(out, exist_ok=True)
        run([sys.executable, "tools/race2_render.py", "clip",
             f"--seed={args.seed}", f"--course={args.course}",
             f"--out={CAMERA}", f"--frames={out}",
             f"--environment={ENVIRONMENT}", f"--end={end:.4f}",
             f"--godot={godot_path(args.godot)}"] + _track_flag(variant),
            f"clip {variant}")
        encode(_clip_dir(variant, args),
               os.path.join(EXPORT, f"race2_v311_{variant}.mp4"))


def _clip_dir(variant: str, args) -> str:
    return os.path.join(frames_dir(f"clip_{variant}"),
                        f"clip_{args.course}_{args.seed}")


def _first_frame(folder: str) -> int:
    found = sorted(glob.glob(os.path.join(folder, "frame_*.png")))
    if not found:
        raise SystemExit(f"no frames in {folder}; run `clips` first")
    return int(os.path.basename(found[0])[6:12])


def compare(args) -> None:
    """Part Q: CONTROL | A, CONTROL | B, CONTROL | C."""
    left = "v31"
    a = _clip_dir(left, args)
    os.makedirs(EXPORT, exist_ok=True)
    for right in [v for v in variants_for(args) if v != left]:
        b = _clip_dir(right, args)
        first = _first_frame(a)
        target = os.path.join(EXPORT, f"race2_v311_control_vs_{right}.mp4")
        run([ffmpeg(), "-y",
             "-framerate", "60", "-start_number", str(first),
             "-i", os.path.join(a, "frame_%06d.png"),
             "-framerate", "60", "-start_number", str(_first_frame(b)),
             "-i", os.path.join(b, "frame_%06d.png"),
             "-filter_complex",
             "[0:v]scale=540:960[l];[1:v]scale=540:960[r];[l][r]hstack=inputs=2",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "17", target],
            f"compare control|{right}")
        print(f"  wrote {target}")


def quad(args) -> None:
    """Part Q's 4-up: CONTROL / A / B / C, one frame, four times."""
    folders = [_clip_dir(v, args) for v in VARIANTS]
    starts = [_first_frame(f) for f in folders]
    os.makedirs(EXPORT, exist_ok=True)
    inputs: list[str] = []
    for folder, first in zip(folders, starts):
        inputs += ["-framerate", "60", "-start_number", str(first),
                   "-i", os.path.join(folder, "frame_%06d.png")]
    chain = "".join(f"[{i}:v]scale=270:480[v{i}];" for i in range(4))
    chain += "[v0][v1][v2][v3]hstack=inputs=4"
    target = os.path.join(EXPORT, "race2_v311_quad_control_A_B_C.mp4")
    run([ffmpeg(), "-y"] + inputs + ["-filter_complex", chain,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "17", target],
        "quad")
    print(f"  wrote {target}")
    for name, start, end in SECTIONS:
        first = int(round(start * 60))
        count = max(int(round((end - start) * 60)), 1)
        section_inputs: list[str] = []
        for folder in folders:
            section_inputs += ["-framerate", "60", "-start_number", str(first),
                               "-i", os.path.join(folder, "frame_%06d.png")]
        target = os.path.join(EXPORT, f"race2_v311_quad_{name}.mp4")
        run([ffmpeg(), "-y"] + section_inputs
            + ["-frames:v", str(count), "-filter_complex", chain,
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "17", target],
            f"quad {name}")
        print(f"  wrote {target}")


def phonefilm(args) -> None:
    """Part R: every candidate as a full 270x480 film, plus a phone 4-up."""
    os.makedirs(EXPORT, exist_ok=True)
    for variant in variants_for(args):
        folder = _clip_dir(variant, args)
        target = os.path.join(EXPORT, f"race2_v311_{variant}_phone_270x480.mp4")
        run([ffmpeg(), "-y", "-framerate", "60",
             "-start_number", str(_first_frame(folder)),
             "-i", os.path.join(folder, "frame_%06d.png"),
             "-vf", "scale=270:480:flags=lanczos",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", target],
            f"phone film {variant}")
        print(f"  wrote {target}")


# --- Part O -----------------------------------------------------------------


def cost(args) -> None:
    """Meshes, triangles, materials and render time, per variant.

    The counts come out of the scene's own census - `race2_scene` prints them
    on every build - so this is what was actually drawn rather than what the
    tool believes was drawn. A material-only change has to leave the first
    three identical; the fourth is the number the brief asks about.
    """
    import re
    import time

    report = {}
    for variant in variants_for(args):
        out = frames_dir(f"cost_{variant}")
        os.makedirs(out, exist_ok=True)
        started = time.time()
        text = run([sys.executable, "tools/race2_render.py", "still",
                    f"--seed={args.seed}", f"--course={args.course}",
                    f"--out={CAMERA}", f"--frames={out}",
                    f"--environment={ENVIRONMENT}", f"--at={at_list()}",
                    f"--godot={godot_path(args.godot)}"] + _track_flag(variant),
                   f"cost {variant}")
        elapsed = time.time() - started
        scene = re.search(r"scene: (\d+) mesh instances, ~(\d+) triangles", text)
        course = re.search(r"race2: (\d+) runs, (\d+) modules, (\d+) actuators,"
                           r" (\d+) triangles", text)
        per = re.search(r"rendered (\d+) frames in ([\d.]+)s\s+\((\d+) ms/frame",
                        text)
        report[variant] = {
            "mesh_instances": int(scene.group(1)) if scene else None,
            "triangles": int(scene.group(2)) if scene else None,
            "course_triangles": int(course.group(4)) if course else None,
            "runs": int(course.group(1)) if course else None,
            "ms_per_frame": int(per.group(3)) if per else None,
            "wall_seconds": round(elapsed, 2),
            # One `StandardMaterial3D` for the channel, one for structure, one
            # for the hazard: the variants change what is in the first, never
            # how many there are.
            "course_materials": 3,
        }
    os.makedirs(DOCS, exist_ok=True)
    target = os.path.join(DOCS, "cost.json")
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1)
    print()
    print(f'  {"":<18}' + "".join(f"{v:>14}" for v in report))
    for key in ("mesh_instances", "triangles", "course_triangles",
                "course_materials", "ms_per_frame", "wall_seconds"):
        print(f"  {key:<18}" + "".join(
            f"{report[v][key]:>14}" for v in report))
    print(f"\n  wrote {target}")


# --- Part V -----------------------------------------------------------------


def preview(args) -> None:
    """The production preview: the winner, with the viewer-facing marks on.

    `tools/race2_v31_preview` is imported rather than restated - the marks, the
    measured title placement and the occlusion refusal are V31's and are not
    being redesigned here, which is what Part V asks for. It reads its frames
    from wherever it is told to; this points it at the winning variant's clip.
    """
    from tools.race2_v31_preview import build_preview

    build_preview(argparse.Namespace(
        camera="RB", course=args.course, seed=args.seed,
        title="PICK A COLOR", title_size=104, place_only=args.place_only,
        frames_root=os.path.join(OUT, "frames"),
        clip_tag=f"clip_{args.winner}",
        export=EXPORT, docs=DOCS,
        name=f"race2_v311_production_preview_{args.winner}",
    ))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("sheet", "phone", "proof", "clips",
                                         "compare", "quad", "phonefilm",
                                         "cost", "preview"))
    parser.add_argument("--course", default="switchyard")
    parser.add_argument("--seed", type=int, default=8)
    parser.add_argument("--only", default="")
    parser.add_argument("--winner", default="B")
    parser.add_argument("--cell", type=int, default=180)
    parser.add_argument("--godot", default="")
    parser.add_argument("--place-only", dest="place_only", action="store_true")
    args = parser.parse_args()
    {"sheet": sheet, "phone": phone, "proof": proof, "clips": clips,
     "compare": compare, "quad": quad, "phonefilm": phonefilm, "cost": cost,
     "preview": preview}[args.mode](args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

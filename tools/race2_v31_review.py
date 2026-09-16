"""Render, compare and prove the V31 readability cameras.

Usage:

    python tools/race2_v31_review.py frames     # the moment set, every camera
    python tools/race2_v31_review.py sheet      # camera x moment contact sheet
    python tools/race2_v31_review.py phone      # the same at 270x480
    python tools/race2_v31_review.py clips      # full 19.15 s films
    python tools/race2_v31_review.py compare    # control | winner, side by side
    python tools/race2_v31_review.py sections   # the brief's five sections
    python tools/race2_v31_review.py trackproof # the track-visibility overlay sheet
    python tools/race2_v31_review.py preview    # PICK A COLOUR + payoff, composited

Every render goes through `tools/race2_render.py` against
`output/race2/v31_readability/<cam>`, which `tools/race2_v31_camera.py` staged
with the *same* geometry and the *same* replay as the control. The environment
is `contained_bay_v301`, passed on the command line and never edited: this tool
contains no profile, no material and no light.

Overlays exist only in `trackproof`. The films and the production preview are
rendered clean, and the preview's titles are the established presentation
language rather than a new one.
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

TRACKS = "output/race2/v31_readability"
FRAMES = "output/race2/v31_readability/frames"
DOCS = "docs/validation/race2/v31_readability"
EXPORT = "exports/race2_v31_readability"
ENVIRONMENT = "contained_bay_v301"

CAMERAS = ("A", "RA", "RB", "RC")

# The brief's Part Q, as times on the hero replay. `hook` and `grid` sit inside
# the opening take, `drum` and `sweep` on the two early mechanisms, `chase` and
# `switchback` in the stretch the brief calls the first problematic chase,
# `sparse` in the middle section where the field is most strung out, and the
# last three inside the continuous final sprint.
MOMENTS = (
    ("grid", 0.35),
    ("hook", 1.20),
    ("drum", 3.20),
    ("sweep", 5.20),
    ("chase", 6.80),
    ("switchback", 8.40),
    ("sparse", 10.60),
    ("late_mech", 12.20),
    ("sprint_in", 13.60),
    ("comeback", 15.40),
    ("line", 16.20),
)

# The brief's Part S sections: name, from, to.
SECTIONS = (
    ("opening", 0.00, 3.00),
    ("early_mechanism", 3.00, 6.00),
    ("first_chase", 6.00, 10.00),
    ("middle_sparse", 10.00, 14.00),
    ("final_sprint", 12.683, 19.15),
)


def film_end() -> float:
    """How long the film is, from the control track itself."""
    with open(os.path.join(TRACKS, "A", "race2_switchyard_8.cameras.json"),
              encoding="utf-8") as handle:
        return float(json.load(handle)["duration"])


def at_list(moments=MOMENTS) -> str:
    return ",".join(f"{seconds:.3f}" for _name, seconds in moments)


def folder_for(camera: str, tag: str) -> str:
    return os.path.join(FRAMES, f"{tag}_{camera}")


def frame_path(camera: str, tag: str, seconds: float, args) -> str:
    return os.path.join(folder_for(camera, tag),
                        f"still_{args.course}_{args.seed}",
                        f"at_{seconds:07.3f}.png")


def cameras_for(args) -> list[str]:
    return [c for c in CAMERAS if not args.cameras or c in args.cameras.split(",")]


def frames(args, size: str = "") -> None:
    for camera in cameras_for(args):
        tag = "phone" if size == "phone" else "frames"
        out = folder_for(camera, tag)
        os.makedirs(out, exist_ok=True)
        command = [
            sys.executable, "tools/race2_render.py", "still",
            f"--seed={args.seed}", f"--course={args.course}",
            f"--out={os.path.join(TRACKS, camera)}", f"--frames={out}",
            f"--environment={ENVIRONMENT}", f"--at={at_list()}",
            f"--godot={godot_path(args.godot)}",
        ]
        run(command, f"{tag} {camera}")
        print(f"  {tag} {camera}: {out}")


def _tile(path, cell):
    from PIL import Image
    if not os.path.exists(path):
        return Image.new("RGB", cell, (28, 28, 30))
    return Image.open(path).convert("RGB").resize(cell, Image.LANCZOS)


def sheet(args) -> None:
    """One row per camera, one column per moment."""
    from PIL import Image, ImageDraw

    cams = cameras_for(args)
    cell = (args.cell, int(args.cell * 16 / 9))
    pad, label = 6, 24
    width = pad + len(MOMENTS) * (cell[0] + pad)
    height = label + len(cams) * (cell[1] + pad + label)
    canvas = Image.new("RGB", (width, height), (16, 16, 18))
    draw = ImageDraw.Draw(canvas)
    for column, (name, seconds) in enumerate(MOMENTS):
        draw.text((pad + column * (cell[0] + pad) + 2, 6),
                  f"{name} {seconds:.1f}s"[:20], fill=(190, 190, 190))
    y = label
    for camera in cams:
        draw.text((pad, y + 4), f"camera {camera}", fill=(235, 220, 180))
        for column, (_name, seconds) in enumerate(MOMENTS):
            canvas.paste(_tile(frame_path(camera, "frames", seconds, args), cell),
                         (pad + column * (cell[0] + pad), y + label))
        y += cell[1] + pad + label
    os.makedirs(DOCS, exist_ok=True)
    target = os.path.join(DOCS, f"sheet_{args.cell}.png")
    canvas.save(target)
    print(f"  wrote {target}  ({canvas.size[0]}x{canvas.size[1]})")


def phone(args) -> None:
    """The mandatory 270x480 review, as one sheet at delivery size.

    Part P. The tiles are the delivered 1080x1920 frames resampled to the phone
    frame, which is what a viewer's phone does to them, and they are pasted at
    exactly 270x480 rather than at a sheet-sized thumbnail - a readability
    judgement made at 135 px wide is not a judgement about a phone.
    """
    from PIL import Image, ImageDraw

    cams = cameras_for(args)
    cell = (270, 480)
    pad, label = 8, 26
    picks = [m for m in MOMENTS if m[0] in
             ("hook", "drum", "chase", "switchback", "sparse", "comeback")]
    width = pad + len(picks) * (cell[0] + pad)
    height = label + len(cams) * (cell[1] + pad + label)
    canvas = Image.new("RGB", (width, height), (16, 16, 18))
    draw = ImageDraw.Draw(canvas)
    for column, (name, seconds) in enumerate(picks):
        draw.text((pad + column * (cell[0] + pad) + 2, 7),
                  f"{name}  {seconds:.2f}s", fill=(195, 195, 195))
    y = label
    for camera in cams:
        draw.text((pad, y + 5), f"camera {camera}   270x480",
                  fill=(235, 220, 180))
        for column, (_name, seconds) in enumerate(picks):
            canvas.paste(_tile(frame_path(camera, "frames", seconds, args), cell),
                         (pad + column * (cell[0] + pad), y + label))
        y += cell[1] + pad + label
    os.makedirs(DOCS, exist_ok=True)
    target = os.path.join(DOCS, "phone_270.png")
    canvas.save(target)
    print(f"  wrote {target}  ({canvas.size[0]}x{canvas.size[1]})")


def clips(args) -> None:
    end = film_end()
    for camera in cameras_for(args):
        out = folder_for(camera, "clip")
        os.makedirs(out, exist_ok=True)
        run([sys.executable, "tools/race2_render.py", "clip",
             f"--seed={args.seed}", f"--course={args.course}",
             f"--out={os.path.join(TRACKS, camera)}", f"--frames={out}",
             f"--environment={ENVIRONMENT}", f"--end={end:.4f}",
             f"--godot={godot_path(args.godot)}"], f"clip {camera}")
        encode(os.path.join(out, f"clip_{args.course}_{args.seed}"),
               os.path.join(EXPORT, f"race2_v31_{camera}.mp4"))


def _clip_dir(camera: str, args) -> str:
    return os.path.join(folder_for(camera, "clip"),
                        f"clip_{args.course}_{args.seed}")


def compare(args) -> None:
    """Control and winner as one side-by-side film, plus the phone cut."""
    left, right = args.left, args.right
    a, b = _clip_dir(left, args), _clip_dir(right, args)
    for folder in (a, b):
        if not glob.glob(os.path.join(folder, "frame_*.png")):
            raise SystemExit(f"no frames in {folder}; run `clips` first")
    os.makedirs(EXPORT, exist_ok=True)
    target = os.path.join(EXPORT, f"race2_v31_{left}_vs_{right}.mp4")
    first = int(os.path.basename(
        sorted(glob.glob(os.path.join(a, "frame_*.png")))[0])[6:12])
    run([ffmpeg(), "-y",
         "-framerate", "60", "-start_number", str(first),
         "-i", os.path.join(a, "frame_%06d.png"),
         "-framerate", "60", "-start_number", str(first),
         "-i", os.path.join(b, "frame_%06d.png"),
         "-filter_complex",
         "[0:v]scale=540:960[l];[1:v]scale=540:960[r];[l][r]hstack=inputs=2",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "17", target],
        f"compare {left}|{right}")
    print(f"  wrote {target}")


def sections(args) -> None:
    """The brief's Part S: one side-by-side clip per named section."""
    left, right = args.left, args.right
    a, b = _clip_dir(left, args), _clip_dir(right, args)
    os.makedirs(EXPORT, exist_ok=True)
    for name, start, end in SECTIONS:
        first = int(round(start * 60))
        count = max(int(round((end - start) * 60)), 1)
        target = os.path.join(EXPORT, f"section_{name}_{left}_vs_{right}.mp4")
        run([ffmpeg(), "-y",
             "-framerate", "60", "-start_number", str(first),
             "-i", os.path.join(a, "frame_%06d.png"),
             "-framerate", "60", "-start_number", str(first),
             "-i", os.path.join(b, "frame_%06d.png"),
             "-frames:v", str(count),
             "-filter_complex",
             "[0:v]scale=540:960[l];[1:v]scale=540:960[r];[l][r]hstack=inputs=2",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "17", target],
            f"section {name}")
        print(f"  wrote {target}")


def phonefilm(args) -> None:
    """The winner at delivery phone size, 270x480, as a film.

    Part P asks for the review to happen at phone size, and a sheet of stills
    at 270x480 is only half of that: the thing a chase camera has to survive is
    *motion* at that size. This is the same frames, scaled the way a phone
    scales them, so the judgement is made on what a viewer sees.
    """
    folder = _clip_dir(args.right, args)
    found = sorted(glob.glob(os.path.join(folder, "frame_*.png")))
    if not found:
        raise SystemExit(f"no frames in {folder}; run `clips` first")
    first = int(os.path.basename(found[0])[6:12])
    os.makedirs(EXPORT, exist_ok=True)
    target = os.path.join(EXPORT, f"race2_v31_{args.right}_phone_270x480.mp4")
    run([ffmpeg(), "-y", "-framerate", "60", "-start_number", str(first),
         "-i", os.path.join(folder, "frame_%06d.png"),
         "-vf", "scale=270:480:flags=lanczos",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", target],
        f"phone film {args.right}")
    print(f"  wrote {target}")


def trackproof(args) -> None:
    """Part T: the active pack, the course under it and the course ahead.

    The only overlaid output in this branch. Over a rendered frame it draws the
    centreline from 8 units behind the pack to 40 ahead - solid where the
    instrument calls it visible, hollow where it does not - a ring on each
    member of the race-interest group, and a marker at the next station. What
    it proves is that the readability numbers and the picture are describing
    the same thing.
    """
    from PIL import Image, ImageDraw

    from race2.flow import DELIVERY, _basis, _project
    from race2.readability import interest_group
    from tools.race2_v31_camera import context, stations_of
    from race2.rig import PackTrack

    class Args:
        course, seed, duration, marbles, source = (
            args.course, args.seed, 40.0, 8, "output/race2")

    course, spine, outcome, raw, _marks, _path = context(Args())
    stations = stations_of(course)
    cams = cameras_for(args)
    from tools.race2_v31_camera import RULES
    picks = [m for m in MOMENTS if m[0] in
             ("drum", "chase", "switchback", "sparse", "comeback")]

    cell = (args.cell * 2, int(args.cell * 2 * 16 / 9))
    pad, label = 8, 24
    canvas = Image.new("RGB",
                       (pad + len(picks) * (cell[0] + pad),
                        label + len(cams) * (cell[1] + pad + label)),
                       (16, 16, 18))
    draw = ImageDraw.Draw(canvas)
    for column, (name, seconds) in enumerate(picks):
        draw.text((pad + column * (cell[0] + pad) + 2, 6),
                  f"{name} {seconds:.2f}s", fill=(190, 190, 190))
    y = label
    rows: list[dict] = []
    for camera in cams:
        pack = PackTrack(raw, spine, outcome, group=RULES[camera])
        with open(os.path.join(TRACKS, camera,
                               f"race2_{args.course}_{args.seed}.cameras.json"),
                  encoding="utf-8") as handle:
            track = json.load(handle)
        frame_rows = [r for cut in track["cuts"] for r in cut["frames"]]
        draw.text((pad, y + 4), f"camera {camera}", fill=(235, 220, 180))
        for column, (name, seconds) in enumerate(picks):
            source = frame_path(camera, "frames", seconds, args)
            if not os.path.exists(source):
                y_offset = y + label
                canvas.paste(Image.new("RGB", cell, (28, 28, 30)),
                             (pad + column * (cell[0] + pad), y_offset))
                continue
            plate = Image.open(source).convert("RGB")
            over = ImageDraw.Draw(plate)
            row = min(frame_rows, key=lambda r: abs(r[0] - seconds))
            position = (row[1], row[2], row[3])
            aim = (row[4], row[5], row[6])
            fov = row[7]
            forward, right, up = _basis(position, aim)
            index = pack.frame_at(seconds)
            s_pack = pack.pack_arcs[index]

            def to_pixels(point):
                projected, depth = _project(point, position, forward, right, up,
                                            fov, DELIVERY)
                if projected is None:
                    return None
                return ((projected[0] + 1.0) * 0.5 * DELIVERY[0],
                        (1.0 - projected[1]) * 0.5 * DELIVERY[1], depth)

            seen_ahead = 0
            for step in range(-8, 41):
                point = spine.point_at(
                    min(max(s_pack + step, 0.0), spine.length))
                at = to_pixels(point)
                if at is None:
                    continue
                inside = (-40 < at[0] < DELIVERY[0] + 40
                          and -40 < at[1] < DELIVERY[1] + 40)
                if not inside:
                    continue
                hidden = spine.blocked(position, point)
                radius = 9 if step >= 0 else 6
                colour = ((255, 215, 90) if step >= 0 else (120, 190, 255))
                if hidden:
                    over.ellipse([at[0] - radius, at[1] - radius,
                                  at[0] + radius, at[1] + radius],
                                 outline=(120, 120, 120), width=3)
                else:
                    over.ellipse([at[0] - radius, at[1] - radius,
                                  at[0] + radius, at[1] + radius], fill=colour)
                    if step >= 0:
                        seen_ahead += 1

            group = interest_group(pack.order_at(seconds), pack.arcs[index])
            for marble in group:
                point = pack.places[index].get(marble)
                if point is None:
                    continue
                at = to_pixels(point)
                if at is None:
                    continue
                over.ellipse([at[0] - 34, at[1] - 34, at[0] + 34, at[1] + 34],
                             outline=(90, 255, 140), width=6)

            best = None
            for module_id, detail in stations.items():
                at = to_pixels(detail["centre"])
                if at is None:
                    continue
                if best is None or at[2] < best[1][2]:
                    best = (module_id, at)
            if best is not None:
                _id, at = best
                over.rectangle([at[0] - 46, at[1] - 46, at[0] + 46, at[1] + 46],
                               outline=(255, 120, 120), width=5)
                over.text((at[0] - 44, at[1] + 50), _id, fill=(255, 150, 150))
            over.text((24, 24), f"{camera}  {name} {seconds:.2f}s   "
                                f"ahead {seen_ahead} u   group {len(group)}",
                      fill=(255, 255, 255))
            rows.append({"camera": camera, "moment": name, "t": seconds,
                         "forward_units_visible": seen_ahead,
                         "group": len(group)})
            canvas.paste(plate.resize(cell, Image.LANCZOS),
                         (pad + column * (cell[0] + pad), y + label))
        y += cell[1] + pad + label
    os.makedirs(DOCS, exist_ok=True)
    target = os.path.join(DOCS, "track_visibility.png")
    canvas.save(target)
    with open(os.path.join(DOCS, "track_visibility.json"), "w",
              encoding="utf-8") as handle:
        json.dump(rows, handle, indent=1)
    print(f"  wrote {target}  ({canvas.size[0]}x{canvas.size[1]})")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("frames", "sheet", "phone", "clips",
                                         "compare", "sections", "trackproof",
                                         "preview", "phonefilm"))
    parser.add_argument("--course", default="switchyard")
    parser.add_argument("--seed", type=int, default=8)
    parser.add_argument("--cameras", default="")
    parser.add_argument("--left", default="A")
    parser.add_argument("--right", default="RB")
    parser.add_argument("--cell", type=int, default=150)
    parser.add_argument("--godot", default="")
    args = parser.parse_args()

    if args.mode == "frames":
        frames(args)
    elif args.mode == "sheet":
        sheet(args)
    elif args.mode == "phone":
        phone(args)
    elif args.mode == "clips":
        clips(args)
    elif args.mode == "compare":
        compare(args)
    elif args.mode == "sections":
        sections(args)
    elif args.mode == "trackproof":
        trackproof(args)
    elif args.mode == "phonefilm":
        phonefilm(args)
    elif args.mode == "preview":
        # The preview tool owns its own placement arguments; `--right` names
        # the winning camera here so one flag selects the winner everywhere.
        from tools.race2_v31_preview import build_preview
        build_preview(argparse.Namespace(
            camera=args.right, course=args.course, seed=args.seed,
            title="PICK A COLOR", title_size=104, place_only=False,
        ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""V29: SWITCHYARD, filmed by V28.1's camera A, standing in V27.2's hall.

Usage:

    python tools/race2_v29_short.py clips      # both worlds, 19.15 s, 1080x1920
    python tools/race2_v29_short.py phone      # 270x480 versions
    python tools/race2_v29_short.py compare    # outdoor | contained, side by side
    python tools/race2_v29_short.py sheet      # contact sheets, from the clip
    python tools/race2_v29_short.py measure    # the review numbers
    python tools/race2_v29_short.py all

**Nothing here builds a race or a camera.** The replay is the one
`tools/race2_camera.py` wrote for seed 8 and the track is the one
`tools/race2_cine.py --only=A` solved from it; this tool reads both and changes
neither. The only variable it moves is `--environment`, which is the whole
point: two renders of one film, identical to the frame, differing in the room.

    outdoor     aurora_valley_v26     the world camera A was developed against
    contained   contained_hall_v272   the hall, brought over from V27.2

Everything lands in `exports/race2_v29_switchyard_contained/`, and `output/`
and `exports/` are not in git, per this repository's convention.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

# The two worlds, in the order every table in the write-up reports them.
WORLDS = (
    ("outdoor", "aurora_valley_v26"),
    ("contained", "contained_hall_v272"),
)
CAMERA = "A"
TRACKS = "output/race2/v281_camera"
OUT = "output/race2/v29"
FRAMES = "output/race2/v29/frames"
EXPORT = "exports/race2_v29_switchyard_contained"

# The contact sheet's sample times, in seconds of the film.
#
# Fixed here rather than derived, so that a later pass comparing against these
# tiles asks for the same instants - and taken out of the rendered clip rather
# than from a `--at` list, which is the stronger version of the same guarantee:
# one continuous render per world, sampled afterwards, so the two sheets cannot
# differ by the renderer's accumulation between samples the way two `--at`
# lists of different lengths do.
SHEET_AT = (
    0.10, 0.80, 1.50, 2.23, 3.00, 4.00,
    5.00, 6.00, 7.00, 8.00, 9.02, 10.00,
    11.00, 12.00, 12.68, 14.00, 15.50, 16.50,
    17.50, 18.30, 18.80, 19.10,
)

# The five sections the V28.1 pass cut, kept to the frame so a V29 section clip
# and a V28.1 one are the same window of the same race.
SECTIONS = (
    ("1_hook", 0.0, 3.0),
    ("2_early_chase", 1.8, 5.2),
    ("3_middle", 5.2, 10.0),
    ("4_switchbacks", 9.6, 13.6),
    ("5_final_sprint", 12.68, 19.15),
)


def ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found is None:
        raise SystemExit("ffmpeg is not on PATH")
    return found


def run(command: list[str], label: str) -> None:
    result = subprocess.run(command, cwd=REPO, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise SystemExit(f"{label} failed:\n{(result.stderr or result.stdout)[-2500:]}")
    print(f"  {label}")


def track_path(args) -> str:
    return os.path.join(TRACKS, CAMERA,
                        f"race2_{args.course}_{args.seed}.cameras.json")


def film_end(args) -> float:
    """How long the film is, from camera A's own track.

    **Not the replay's duration.** The replay runs 40 s on this seed - the
    marbles keep rolling down the run-out long after the film is over - and a
    clip rendered without an end is 1250 frames of settled field past the
    finish. The film ends where the track does, and the track knows: 19.15.
    """
    with open(track_path(args), encoding="utf-8") as handle:
        return float(json.load(handle)["duration"])


def clip_dir(world: str, args) -> str:
    return os.path.join(FRAMES, f"delivery_{world}",
                        f"clip_{args.course}_{args.seed}")


def encode(folder: str, target: str, fps: int = 60, crf: int = 17) -> str:
    frames = sorted(glob.glob(os.path.join(folder, "frame_*.png")))
    if not frames:
        raise SystemExit(f"no frames in {folder}")
    first = int(os.path.basename(frames[0])[6:12])
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    run([
        ffmpeg(), "-y", "-framerate", str(fps), "-start_number", str(first),
        "-i", os.path.join(folder, "frame_%06d.png"),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", str(crf),
        "-preset", "slow", "-movflags", "+faststart", target,
    ], f"{os.path.basename(target)} ({len(frames)} frames)")
    return target


def render_clips(args) -> None:
    end = film_end(args)
    for world, environment in WORLDS:
        if args.worlds and world not in args.worlds:
            continue
        folder = os.path.join(FRAMES, f"delivery_{world}")
        os.makedirs(folder, exist_ok=True)
        run([
            sys.executable, "tools/race2_render.py", "clip",
            f"--seed={args.seed}", f"--course={args.course}",
            f"--out={TRACKS}/{CAMERA}", f"--frames={folder}",
            f"--environment={environment}", f"--end={end:.4f}",
        ], f"render {world} ({environment})")
        encode(clip_dir(world, args),
               os.path.join(EXPORT, f"race2_v29_{world}.mp4"))


def matte_dir(world: str, args) -> str:
    return os.path.join(FRAMES, f"matte_{world}",
                        f"clip_{args.course}_{args.seed}")


def render_mattes(args) -> None:
    """The same film as a silhouette: the machine, lit, against black.

    This is what makes "how much of the frame is the room" a measurement
    rather than an impression. `--show=matte` builds the machine and the
    racers, drops the world and clears the background, so a lit pixel is a
    pixel of machine - and it is the same camera on the same frames, so the
    subtraction against the delivery is exact.

    **One matte per world, not one shared matte.** The two worlds light the
    machine differently, and a silhouette taken under the wrong lights would
    misread a dark edge as background. It also gives the measurement its own
    check: machine coverage is the same geometry seen by the same camera in
    both worlds, so the two mattes have to agree, and `measure` prints the
    gap between them.
    """
    end = film_end(args)
    for world, environment in WORLDS:
        if args.worlds and world not in args.worlds:
            continue
        folder = os.path.join(FRAMES, f"matte_{world}")
        os.makedirs(folder, exist_ok=True)
        run([
            sys.executable, "tools/race2_render.py", "clip",
            f"--seed={args.seed}", f"--course={args.course}",
            f"--out={TRACKS}/{CAMERA}", f"--frames={folder}",
            f"--environment={environment}", "--show=matte", f"--end={end:.4f}",
        ], f"render matte {world}")


def phone_versions(args) -> None:
    """270x480, scaled from the delivered file.

    Scaled rather than re-rendered, for the reason the V28.1 tool gives: what a
    viewer sees on a phone is the delivered file resampled, and a phone proof
    rendered natively at 270x480 would be a kinder picture than the one being
    shipped.
    """
    for world, _environment in WORLDS:
        source = os.path.join(EXPORT, f"race2_v29_{world}.mp4")
        if not os.path.isfile(source):
            print(f"  (skipping {world}: no delivery clip yet)")
            continue
        run([ffmpeg(), "-y", "-i", source, "-vf", "scale=270:480:flags=lanczos",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
             "-preset", "slow", "-movflags", "+faststart",
             os.path.join(EXPORT, "phone", f"race2_v29_{world}_phone.mp4")],
            f"phone {world}")


def sections(args) -> None:
    for world, _environment in WORLDS:
        source = os.path.join(EXPORT, f"race2_v29_{world}.mp4")
        if not os.path.isfile(source):
            continue
        for name, start, end in SECTIONS:
            run([ffmpeg(), "-y", "-ss", f"{start}", "-to", f"{end}", "-i", source,
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
                 "-preset", "medium", "-movflags", "+faststart",
                 os.path.join(EXPORT, "sections", f"{world}_{name}.mp4")],
                f"section {world} {name}")


def side_by_side(args) -> None:
    left = os.path.join(EXPORT, "race2_v29_outdoor.mp4")
    right = os.path.join(EXPORT, "race2_v29_contained.mp4")
    if not (os.path.isfile(left) and os.path.isfile(right)):
        print("  (skipping side by side: both worlds must be rendered)")
        return
    run([ffmpeg(), "-y", "-i", left, "-i", right, "-filter_complex",
         "[0:v]scale=540:960[l];[1:v]scale=540:960[r];[l][r]hstack=inputs=2",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
         "-preset", "medium", "-movflags", "+faststart",
         os.path.join(EXPORT, "compare", "outdoor_vs_contained.mp4")],
        "side by side outdoor | contained")
    for name, start, end in SECTIONS:
        run([ffmpeg(), "-y", "-ss", f"{start}", "-to", f"{end}", "-i", left,
             "-ss", f"{start}", "-to", f"{end}", "-i", right, "-filter_complex",
             "[0:v]scale=540:960[l];[1:v]scale=540:960[r];[l][r]hstack=inputs=2",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
             "-preset", "medium", "-movflags", "+faststart",
             os.path.join(EXPORT, "compare", f"outdoor_vs_contained_{name}.mp4")],
            f"side by side {name}")


def _frame_for(folder: str, seconds: float, fps: int = 60) -> str | None:
    frames = sorted(glob.glob(os.path.join(folder, "frame_*.png")))
    if not frames:
        return None
    first = int(os.path.basename(frames[0])[6:12])
    index = first + int(round(seconds * fps))
    path = os.path.join(folder, "frame_%06d.png" % index)
    return path if os.path.isfile(path) else frames[min(
        max(0, index - first), len(frames) - 1)]


def contact_sheet(args) -> None:
    """One tile per sample time, per world, from the rendered clip.

    The tiles are camera A's own frames - the shot it was in, the lens it had,
    the pose it solved - rather than a sheet shot from invented viewpoints, so
    a tile that shows an empty upper frame is showing what the delivered film
    shows there.
    """
    from PIL import Image, ImageDraw

    columns = 6
    tile = (200, 356)
    label = 18
    for world, _environment in WORLDS:
        folder = clip_dir(world, args)
        if not glob.glob(os.path.join(folder, "frame_*.png")):
            print(f"  (skipping sheet {world}: no frames)")
            continue
        rows = (len(SHEET_AT) + columns - 1) // columns
        sheet = Image.new("RGB",
                          (columns * tile[0], rows * (tile[1] + label)),
                          (12, 12, 14))
        draw = ImageDraw.Draw(sheet)
        for index, seconds in enumerate(SHEET_AT):
            path = _frame_for(folder, seconds)
            if path is None:
                continue
            frame = Image.open(path).convert("RGB").resize(tile, Image.LANCZOS)
            x = (index % columns) * tile[0]
            y = (index // columns) * (tile[1] + label)
            sheet.paste(frame, (x, y))
            draw.text((x + 4, y + tile[1] + 3), f"{seconds:5.2f}s  {_shot_at(args, seconds)}",
                      fill=(190, 196, 206))
        target = os.path.join(EXPORT, "sheets", f"camera_A_{world}.png")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        sheet.save(target)
        print(f"  sheet {world} -> {target}")


def _shot_at(args, seconds: float) -> str:
    with open(track_path(args), encoding="utf-8") as handle:
        cuts = json.load(handle)["cuts"]
    for cut in cuts:
        if float(cut["from"]) <= seconds <= float(cut["to"]):
            return str(cut["name"])
    return "?"


def measure(args) -> None:
    """The review numbers, from the delivered frames and the matte.

    Four things per frame, and each of them answers a question the brief asks
    in words:

      void        share of the frame with nothing drawn in it at all
      world       share of the frame that is environment rather than machine
      racers      share of the frame that is a racer
      luma        mean, and the share above and below the readable band
    """
    import numpy as np
    from PIL import Image

    report: dict = {"seed": args.seed, "course": args.course, "camera": CAMERA,
                    "worlds": {}}
    with open(track_path(args), encoding="utf-8") as handle:
        cuts = json.load(handle)["cuts"]

    for world, environment in WORLDS:
        folder = clip_dir(world, args)
        frames = sorted(glob.glob(os.path.join(folder, "frame_*.png")))
        if not frames:
            print(f"  (skipping measure {world}: no frames)")
            continue
        mattes = sorted(glob.glob(os.path.join(matte_dir(world, args),
                                               "frame_*.png")))
        rows = []
        step = max(1, args.every)
        for index in range(0, len(frames), step):
            seconds = index / 60.0
            image = np.asarray(Image.open(frames[index]).convert("RGB"))
            luma = (0.2126 * image[..., 0] + 0.7152 * image[..., 1]
                    + 0.0722 * image[..., 2])
            drawn = luma >= 0.5
            if index < len(mattes):
                matte = np.asarray(Image.open(mattes[index]).convert("RGB"))
                matte_luma = (0.2126 * matte[..., 0] + 0.7152 * matte[..., 1]
                              + 0.0722 * matte[..., 2])
                machine = matte_luma >= 0.5
            else:
                machine = np.zeros_like(drawn)
            rows.append({
                "t": round(seconds, 4),
                "shot": _shot_at(args, seconds),
                "void": round(100.0 * float((~drawn).mean()), 3),
                "machine": round(100.0 * float(machine.mean()), 3),
                "world": round(100.0 * float((drawn & ~machine).mean()), 3),
                "luma": round(float(luma.mean()), 3),
                "luma_p90": round(float(np.percentile(luma, 90)), 3),
                "clipped": round(100.0 * float((luma >= 250).mean()), 4),
            })
        per_shot: dict = {}
        for cut in cuts:
            name = str(cut["name"])
            inside = [r for r in rows if r["shot"] == name]
            if not inside:
                continue
            per_shot[name] = {
                "from": cut["from"], "to": cut["to"],
                "samples": len(inside),
                "void_mean": round(sum(r["void"] for r in inside) / len(inside), 2),
                "void_max": round(max(r["void"] for r in inside), 2),
                "world_mean": round(sum(r["world"] for r in inside) / len(inside), 2),
                "machine_mean": round(sum(r["machine"] for r in inside) / len(inside), 2),
                "luma_mean": round(sum(r["luma"] for r in inside) / len(inside), 2),
            }
        report["worlds"][world] = {
            "environment": environment,
            "frames": len(frames),
            "void_mean": round(sum(r["void"] for r in rows) / len(rows), 2),
            "world_mean": round(sum(r["world"] for r in rows) / len(rows), 2),
            "machine_mean": round(sum(r["machine"] for r in rows) / len(rows), 2),
            "luma_mean": round(sum(r["luma"] for r in rows) / len(rows), 2),
            "shots": per_shot,
            "rows": rows,
        }

    os.makedirs(args.docs, exist_ok=True)
    target = os.path.join(args.docs, "coverage.json")
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1)
    print(f"  wrote {target}")
    print()
    print(f"{'world':<11}{'frames':>7}{'void%':>8}{'world%':>8}{'machine%':>10}{'luma':>7}")
    for world, data in report["worlds"].items():
        print(f"{world:<11}{data['frames']:>7}{data['void_mean']:>8.2f}"
              f"{data['world_mean']:>8.2f}{data['machine_mean']:>10.2f}"
              f"{data['luma_mean']:>7.2f}")
    print()
    print(f"{'world':<11}{'shot':<10}{'void%':>8}{'world%':>8}{'machine%':>10}{'luma':>7}")
    for world, data in report["worlds"].items():
        for name, shot in data["shots"].items():
            print(f"{world:<11}{name:<10}{shot['void_mean']:>8.2f}"
                  f"{shot['world_mean']:>8.2f}{shot['machine_mean']:>10.2f}"
                  f"{shot['luma_mean']:>7.2f}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("clips", "matte", "phone", "sections",
                                         "compare", "sheet", "measure", "all"))
    parser.add_argument("--course", default="switchyard")
    parser.add_argument("--seed", type=int, default=8)
    parser.add_argument("--worlds", default="")
    parser.add_argument("--docs", default="docs/validation/race2/v29_contained")
    parser.add_argument("--every", type=int, default=6,
                        help="measure every Nth frame (6 = ten a second)")
    args = parser.parse_args()
    args.worlds = [w for w in args.worlds.split(",") if w]
    for folder in ("compare", "sections", "phone", "sheets"):
        os.makedirs(os.path.join(EXPORT, folder), exist_ok=True)

    if args.mode in ("clips", "all"):
        render_clips(args)
    if args.mode in ("matte", "all"):
        render_mattes(args)
    if args.mode in ("phone", "all"):
        phone_versions(args)
    if args.mode in ("sections", "all"):
        sections(args)
    if args.mode in ("compare", "all"):
        side_by_side(args)
    if args.mode in ("sheet", "all"):
        contact_sheet(args)
    if args.mode in ("measure", "all"):
        measure(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

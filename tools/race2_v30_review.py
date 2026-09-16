"""V30: what each contained stage does to camera A's frames, measured.

Usage:

    python tools/race2_v30_review.py frames     # render the sample set
    python tools/race2_v30_review.py matte      # the same, machine-only
    python tools/race2_v30_review.py measure    # the numbers
    python tools/race2_v30_review.py sheets     # comparison + phone sheets
    python tools/race2_v30_review.py all

**Nothing here builds a race or a camera.** The replay is the one
`tools/race2_camera.py` wrote for seed 8 and the track is the one
`tools/race2_cine.py --only=A` solved from it. The only variable is
`--environment`.

## Why a matte, and what it buys

Every coverage number below is taken against a **silhouette matte** - the same
camera on the same frames with `--show=matte`, which builds the machine and the
racers, drops the world and clears the background to black. A lit pixel in the
matte is a pixel of machine or racer, so "how much of this frame is the room"
becomes a subtraction rather than an inference from colour. It is V29's method
and it carries V29's own check: machine coverage is the same geometry seen by
the same camera in every world, so the mattes have to agree, and `measure`
prints the spread between them.

## The three numbers this pass exists to move

    void            share of the frame with nothing drawn. V29: 64.89% over
                    the film and 90.8% in the final sprint.
    floor           share of the frame that is the stage's own ground. V29:
                    there was no ground, which is the same statement.
    warm            share that is a warm practical. V29: 0.000%, in a room
                    that authored three of them.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

TRACKS = "output/race2/v281_camera/A"
FRAMES = "output/race2/v30_stage/frames"
DOCS = "docs/validation/race2/v30_stage"
EXPORT = "exports/race2_v30_stage"

# The worlds under test, and the two controls. `outdoor` is the world camera A
# was developed against and `v29_hall` is the failure this pass answers; both
# are rendered through the same pipeline on the same frames, because a
# comparison whose control went through a different renderer measures the
# renderer.
WORLDS = (
    ("outdoor", "aurora_valley_v26"),
    ("v29_hall", "contained_hall_v272"),
    ("A", "contained_bay_v30"),
    ("B", "horseshoe_arena_v30"),
    ("C", "stepped_chamber_v30"),
)

# Ten moments, named by what they have to carry. These are the brief's Part W
# list, resolved against camera A's own cut table: `release` 0.02-2.23,
# `upper` 2.23-9.02, `middle` 9.02-12.68, `run_in` 12.68-19.15.
MOMENTS = (
    ("hook", 0.60),
    ("early_chase", 2.60),
    ("first_mechanism", 4.40),
    ("central_chase", 6.80),
    ("switchback", 9.60),
    ("late_mechanism", 11.40),
    ("sprint_early", 13.40),
    ("sprint_mid", 15.60),
    ("winner", 17.60),
    ("final_frame", 19.10),
)

# Which of those are the final sprint. The brief's Part Q target is on these
# and on these only: one continuous 6.47 s take that V29 lost.
SPRINT = ("sprint_early", "sprint_mid", "winner", "final_frame")


def godot_path(explicit: str) -> str:
    if explicit:
        return explicit
    for name in ("GODOT_BIN", "GODOT4_BIN"):
        value = os.environ.get(name, "")
        if value and os.path.isfile(value):
            return value
    guess = os.path.expanduser(
        "~/Downloads/Godot_v4.7.2-stable_win64.exe/Godot_v4.7.2-stable_win64.exe")
    if os.path.isfile(guess):
        return guess
    raise SystemExit("pass --godot PATH or set $GODOT_BIN")


def run(command: list[str], label: str) -> str:
    result = subprocess.run(command, cwd=REPO, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise SystemExit(f"{label} failed:\n"
                         f"{(result.stderr or result.stdout)[-2500:]}")
    return result.stdout or ""


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
                # "scene: 264 mesh instances, ~79268 triangles"
                parts = line.replace(",", "").split()
                record["meshes"] = int(parts[1])
                record["triangles"] = int(parts[4].lstrip("~"))
            if line.startswith("rendered"):
                record["ms_per_frame"] = float(
                    line.split("(")[1].split()[0])
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


# --- the measurements -------------------------------------------------------


def measure(args) -> dict:
    import numpy as np
    from PIL import Image

    def load(path):
        return np.asarray(Image.open(path).convert("RGB")).astype(np.float32)

    def luma(a):
        return a @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)

    worlds = [w for w in WORLDS
              if not args.worlds or w[0] in args.worlds.split(",")]
    report: dict = {"moments": {}, "worlds": {}}

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

            # The silhouette. A pixel lit above the threshold in the matte is
            # machine or racer; everything else in the delivery is room or
            # nothing. The threshold is V29's 0.5/255 scaled to 8-bit.
            subject = lm > 2.0
            room = ~subject

            # Racers are the saturated pixels of the matte: the machine is
            # pearl and the marbles are candy, and nothing else is drawn.
            mx = m.max(axis=2)
            mn = m.min(axis=2)
            sat = np.where(mx > 1.0, (mx - mn) / np.maximum(mx, 1.0), 0.0)
            racers = subject & (sat > 0.35)
            machine = subject & ~racers

            # Void is a frame pixel with nothing drawn at all. Measured on the
            # delivery outside the silhouette, at the same threshold, which is
            # how V29's 64.89% was taken.
            void = room & (la <= 2.0)
            third = la.shape[0] // 3
            lower_void = void[2 * third:]

            # Warm and cool practicals: strongly tinted bright pixels of the
            # room. A practical is the only thing in this palette that is both
            # bright and saturated, so the test is a conjunction rather than a
            # hue window - the floor is warm-grey and must not count.
            ax, an = a.max(axis=2), a.min(axis=2)
            asat = np.where(ax > 1.0, (ax - an) / np.maximum(ax, 1.0), 0.0)
            bright = room & (la > 90.0) & (asat > 0.22)
            warm = bright & (a[:, :, 0] > a[:, :, 2] * 1.25)
            cool = bright & (a[:, :, 2] > a[:, :, 0] * 1.25)

            lit = room & (la > 20.0)
            room_l = la[room]
            per_moment[name] = {
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
                # The cast the first build was lost to. Above about 1.35 the
                # room reads as blue rather than as grey.
                #
                # **Taken over the room's *lit* pixels only, and the first
                # version of this number was not.** A ratio of channel means
                # over every room pixel is dominated by the near-black ones,
                # where both channels are a rounding error and the quotient is
                # noise: the outdoor control measured 1652 by that definition,
                # and the same room got *bluer* on the metric every time it was
                # darkened. Hue is only a fact about a pixel bright enough to
                # have one, so the sample is room pixels above luma 20.
                "blue_over_red": float(a[lit][:, 2].mean()
                                       / max(a[lit][:, 0].mean(), 0.01))
                if lit.any() else 0.0,
                "lit_room_coverage": float(lit.mean()),
            }
            sep = per_moment[name]
            sep["racer_separation"] = (sep["racer_mean_luma"]
                                       - sep["room_mean_luma"])
            sep["machine_separation"] = (sep["machine_mean_luma"]
                                         - sep["room_mean_luma"])

        if not per_moment:
            continue

        def avg(key, names=None):
            picks = [per_moment[n][key] for n in (names or per_moment)
                     if n in per_moment]
            return sum(picks) / max(1, len(picks))

        report["worlds"][world] = {
            "environment": environment,
            "film": {k: avg(k) for k in (
                "void", "lower_third_void", "mean_luma", "room_mean_luma",
                "room_coverage", "machine_coverage", "racer_coverage",
                "warm_coverage", "cool_coverage", "racer_separation",
                "machine_separation", "blue_over_red",
                "lit_room_coverage")},
            "final_sprint": {k: avg(k, SPRINT) for k in (
                "void", "lower_third_void", "mean_luma", "room_mean_luma",
                "racer_separation", "machine_separation", "warm_coverage",
                "blue_over_red")},
            "worst_void": max(per_moment.items(),
                              key=lambda kv: kv[1]["void"])[0],
            "worst_void_value": max(v["void"] for v in per_moment.values()),
            "moments": per_moment,
        }
    return report


def render_measure(report: dict) -> str:
    out = ["V30 CONTAINED STAGE: camera A, ten moments, five worlds",
           "=" * 78, ""]
    head = ("%-9s %8s %8s %9s %8s %8s %8s %7s"
            % ("world", "void%", "sprint%", "lower3%", "roomL", "racerSep",
               "warm%", "B/R"))
    out.append("OVER THE FILM")
    out.append(head)
    for world, data in report["worlds"].items():
        f, s = data["film"], data["final_sprint"]
        out.append("%-9s %7.2f%% %7.2f%% %8.2f%% %8.1f %8.1f %7.3f%% %7.2f"
                   % (world, f["void"] * 100.0, s["void"] * 100.0,
                      f["lower_third_void"] * 100.0, f["room_mean_luma"],
                      f["racer_separation"], f["warm_coverage"] * 100.0,
                      f["blue_over_red"]))
    out.append("")
    out.append("  void      nothing drawn.   V29 measured 64.89% over its film")
    out.append("  sprint    void in the final sprint.   V29: 90.8%")
    out.append("  racerSep  racer luma minus room luma; positive is readable")
    out.append("  warm      warm practical pixels.   V29: 0.000%")
    out.append("  B/R       room blue channel over red; >1.35 reads as blue")
    out.append("")
    out.append("PER MOMENT, void %")
    names = [n for n, _s in MOMENTS]
    out.append("  %-16s " % "moment"
               + " ".join("%8s" % w for w in report["worlds"]))
    for name in names:
        row = ["  %-16s " % name]
        for _world, data in report["worlds"].items():
            moment = data["moments"].get(name)
            row.append("%7.2f%%" % (moment["void"] * 100.0) if moment
                       else "%8s" % "-")
        out.append(" ".join(row))
    out.append("")
    out.append("PER MOMENT, room mean luma")
    out.append("  %-16s " % "moment"
               + " ".join("%8s" % w for w in report["worlds"]))
    for name in names:
        row = ["  %-16s " % name]
        for _world, data in report["worlds"].items():
            moment = data["moments"].get(name)
            row.append("%8.1f" % moment["room_mean_luma"] if moment
                       else "%8s" % "-")
        out.append(" ".join(row))
    return "\n".join(out)


# --- sheets -----------------------------------------------------------------


def sheets(args) -> None:
    """One row per world, one column per moment, at phone size.

    The brief's Part R asks the review questions at 270x480, and this is the
    only honest way to ask them: a 1080x1920 still answers "is the detail
    there", and the question is "does it read".
    """
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


# --- motion ----------------------------------------------------------------


def ffmpeg() -> str:
    import shutil
    found = shutil.which("ffmpeg")
    if not found:
        raise SystemExit("ffmpeg is not on PATH")
    return found


def film_end() -> float:
    """How long the film is, from camera A's own track.

    **Not the replay's duration.** The replay runs 40 s on this seed - the
    marbles keep rolling down the run-out long after the film is over - and a
    clip rendered without an end is 1250 frames of settled field past the
    finish. The film ends where the track does, and the track knows: 19.15.
    """
    with open(os.path.join(TRACKS, "race2_switchyard_8.cameras.json"),
              encoding="utf-8") as handle:
        return float(json.load(handle)["duration"])


def encode(folder: str, target: str, fps: int = 60, crf: int = 17) -> str:
    frames_found = sorted(glob.glob(os.path.join(folder, "frame_*.png")))
    if not frames_found:
        raise SystemExit(f"no frames in {folder}")
    first = int(os.path.basename(frames_found[0])[6:12])
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    run([ffmpeg(), "-y", "-framerate", str(fps), "-start_number", str(first),
         "-i", os.path.join(folder, "frame_%06d.png"),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", str(crf),
         "-preset", "slow", "-movflags", "+faststart", target],
        f"{os.path.basename(target)} ({len(frames_found)} frames)")
    print(f"  {target}  ({len(frames_found)} frames)")
    return target


def clips(args) -> None:
    """The full 19.15 s film, per world.

    The brief's Part X: stills are not enough, and the winner must have a
    whole film. `--end` is the track's own duration, so every clip is the same
    1149 frames of the same race under a different room.
    """
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
               os.path.join(EXPORT, f"race2_v30_{world}.mp4"))


def compare(args) -> None:
    """Three rooms, one race, side by side on the same frames.

    Stacked horizontally at a third scale each, so the sheet is a 1080x640
    strip that plays: the comparison the brief's Part W asks for, as motion
    rather than as a contact sheet.
    """
    wanted = (args.worlds or "outdoor,v29_hall,A").split(",")
    sources = []
    for world in wanted:
        folder = os.path.join(FRAMES, f"clip_{world}",
                              f"clip_{args.course}_{args.seed}")
        if not os.path.isdir(folder):
            raise SystemExit(f"no clip for {world}; run `clips` first")
        sources.append(folder)
    target = os.path.join(EXPORT, "race2_v30_compare.mp4")
    os.makedirs(EXPORT, exist_ok=True)
    command = [ffmpeg(), "-y"]
    for folder in sources:
        command += ["-framerate", "60", "-i",
                    os.path.join(folder, "frame_%06d.png")]
    scale = "".join(f"[{i}:v]scale=360:640[v{i}];" for i in range(len(sources)))
    joins = "".join(f"[v{i}]" for i in range(len(sources)))
    command += ["-filter_complex",
                f"{scale}{joins}hstack=inputs={len(sources)}[out]",
                "-map", "[out]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-crf", "18", "-preset", "slow", target]
    run(command, "compare")
    print(f"  {target}  ({' | '.join(wanted)})")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("frames", "matte", "measure",
                                         "sheets", "clips", "compare", "all"))
    parser.add_argument("--course", default="switchyard")
    parser.add_argument("--seed", type=int, default=8)
    parser.add_argument("--worlds", default="")
    parser.add_argument("--godot", default="")
    parser.add_argument("--cell", type=int, default=135)
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

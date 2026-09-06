"""Render the track visual lab: hero stills, module lenses, sheets, a clip.

An art driver, like ``visual_lab.py`` and separate from it. It launches Godot
against ``scenes/TrackLabRender.tscn``, which builds the V2 machine from the
module scripts under ``godot/assets/marble_machine/v2/`` and photographs it. It
loads no replay, imports nothing from ``race`` or ``engine``, and cannot change
what a race does.

Finding Godot, in order: ``--godot``, then ``$GODOT_BIN`` or ``$GODOT4_BIN``,
then the PATH. The same rule every other render tool here follows.

Typical use::

    python tools/track_lab.py shots      # the six required stills
    python tools/track_lab.py sheets     # module sheet + target comparison
    python tools/track_lab.py sweeps     # elevation and azimuth sheets
    python tools/track_lab.py motion     # the short clip
    python tools/track_lab.py all
"""

from __future__ import annotations

import argparse
import glob
import os
import shutil
import subprocess
import sys
import time

from PIL import Image, ImageDraw, ImageFont

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GODOT_PROJECT = os.path.join(REPO, "godot")
RENDER_SCENE = "scenes/TrackLabRender.tscn"

OUT_DOCS = os.path.join(REPO, "docs", "validation", "track_visual_v2")
OUT_MEDIA = os.path.join(REPO, "output", "track_visual_v2")
REFERENCE = os.path.join(REPO, "docs", "references",
                         "neon_marble_machine_concept.png")

WIDTH = 1080
HEIGHT = 1920
CLIP_FPS = 30
CLIP_SECONDS = 4.0

# The reference sheet is a multi-panel infographic; its left column is the
# hero render of the machine and the only part a hero frame can be compared
# against. This fraction is the column's right edge.
REFERENCE_HERO_FRACTION = 0.335

HERO_SHOTS = ("hero", "start", "bowl", "track", "upper")
ELEVATION_SHOTS = ("e16", "e20", "e24", "e28")
AZIMUTH_SHOTS = ("a18", "a34", "a50", "a66")

GODOT_ENV_VARS = ("GODOT_BIN", "GODOT4_BIN")
GODOT_ON_PATH = ("godot", "godot4", "Godot_v4.7.2-stable_win64.exe")


class LabError(RuntimeError):
    """The render did not produce what was asked for."""


# --- locating Godot -------------------------------------------------------


def find_godot(explicit: str | None) -> str:
    if explicit:
        if os.path.isfile(explicit):
            return explicit
        found = shutil.which(explicit)
        if found:
            return found
        raise LabError(f"--godot does not name an executable: {explicit}")

    for variable in GODOT_ENV_VARS:
        value = os.environ.get(variable)
        if value and os.path.isfile(value):
            return value
    for name in GODOT_ON_PATH:
        found = shutil.which(name)
        if found:
            return found
    raise LabError(
        "cannot find Godot 4. Pass --godot PATH, set "
        f"{' or '.join('$' + name for name in GODOT_ENV_VARS)}, or put it on PATH."
    )


# --- one render -----------------------------------------------------------


def run_godot(command: list[str], label: str) -> float:
    started = time.time()
    result = subprocess.run(
        command, cwd=REPO, capture_output=True, text=True, encoding="utf-8",
        errors="replace",
    )
    elapsed = time.time() - started
    if result.returncode != 0:
        tail = "\n".join((result.stdout or "").splitlines()[-25:])
        errors = "\n".join((result.stderr or "").splitlines()[-25:])
        raise LabError(
            f"{label}: Godot exited {result.returncode}\n--- stdout ---\n{tail}"
            f"\n--- stderr ---\n{errors}"
        )
    # GDScript pushes parse and runtime errors to stderr without failing the
    # process, so a zero exit is not on its own proof the scene was built.
    for line in (result.stderr or "").splitlines():
        if "SCRIPT ERROR" in line or "Parse Error" in line:
            raise LabError(f"{label}: {line.strip()}")
    for line in (result.stdout or "").splitlines():
        if line.startswith("scene:") or line.startswith("rendered"):
            print(f"    {line.strip()}")
    print(f"  {label}: {elapsed:.1f}s")
    return elapsed


def render_stills(godot: str, out_dir: str, shots: tuple[str, ...],
                  width: int = WIDTH, height: int = HEIGHT,
                  dump_modules: str | None = None) -> None:
    os.makedirs(out_dir, exist_ok=True)
    command = [
        godot, "--path", GODOT_PROJECT, RENDER_SCENE, "--",
        f"--out-dir={os.path.abspath(out_dir)}",
        f"--shots={','.join(shots)}",
        f"--width={width}", f"--height={height}",
    ]
    if dump_modules:
        command.append(f"--dump-modules={os.path.abspath(dump_modules)}")
    run_godot(command, f"stills [{', '.join(shots)}] {width}x{height}")

    missing = [n for n in shots
               if not os.path.isfile(os.path.join(out_dir, f"{n}.png"))]
    if missing:
        raise LabError(f"no image written for {', '.join(missing)}")


def render_clip(godot: str, out_dir: str, shot: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    frames = int(CLIP_SECONDS * CLIP_FPS)
    command = [
        godot, "--path", GODOT_PROJECT, RENDER_SCENE, "--",
        f"--out-dir={os.path.abspath(out_dir)}",
        f"--frames={frames}", f"--fps={CLIP_FPS}",
        f"--width={WIDTH}", f"--height={HEIGHT}", f"--shot={shot}",
    ]
    run_godot(command, f"clip {shot} ({frames} frames)")


# --- sheets ---------------------------------------------------------------


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _labelled(image: Image.Image, text: str, height: int) -> Image.Image:
    """One panel, scaled to `height`, with a caption bar under it."""
    scale = height / image.height
    panel = image.resize((max(1, int(image.width * scale)), height),
                         Image.LANCZOS)
    bar = 54
    out = Image.new("RGB", (panel.width, height + bar), (10, 14, 20))
    out.paste(panel, (0, 0))
    draw = ImageDraw.Draw(out)
    draw.text((16, height + 14), text, font=_font(26), fill=(214, 232, 244))
    return out


def _row(panels: list[Image.Image], gap: int = 14) -> Image.Image:
    width = sum(p.width for p in panels) + gap * (len(panels) - 1)
    height = max(p.height for p in panels)
    sheet = Image.new("RGB", (width, height), (10, 14, 20))
    x = 0
    for panel in panels:
        sheet.paste(panel, (x, 0))
        x += panel.width + gap
    return sheet


def module_sheet(source: str, destination: str) -> None:
    """Start, bowl, track and the assembled machine, at one height."""
    names = [("start", "START V2"), ("bowl", "BOWL V2"),
             ("track", "TRACK V2"), ("hero", "MACHINE V2")]
    panels = [_labelled(Image.open(os.path.join(source, f"{n}.png")), t, 900)
              for n, t in names]
    _row(panels).save(destination)
    print(f"  module sheet -> {destination}")


def target_comparison(hero: str, destination: str) -> None:
    """Reference hero column beside ours, at equal visual height.

    Equal height and no cropping of either side: the brief's own rule is that
    a comparison must not hide a weakness behind a different scale, and the
    only honest way to hold to that is to fit both to the same number of
    pixels top to bottom and show whatever width that produces.
    """
    reference = Image.open(REFERENCE)
    column = reference.crop(
        (0, 0, int(reference.width * REFERENCE_HERO_FRACTION), reference.height))
    panels = [_labelled(column, "TARGET CONCEPT", 1180),
              _labelled(Image.open(hero), "OUR MACHINE V2", 1180)]
    _row(panels, 20).save(destination)
    print(f"  comparison -> {destination}")


def sweep_sheet(source: str, names: tuple[str, ...], labels: tuple[str, ...],
                destination: str) -> None:
    panels = [_labelled(Image.open(os.path.join(source, f"{n}.png")), t, 760)
              for n, t in zip(names, labels)]
    _row(panels).save(destination)
    print(f"  sweep -> {destination}")


def phone_sheet(hero: str, destination: str) -> None:
    """The hero at the size a phone actually shows it, beside a 2x crop.

    A hero frame is reviewed at 1080x1920 and then shipped to a screen a
    third that size, and detail that survives one does not always survive the
    other. The crop is there so the sheet answers both questions at once.
    """
    full = Image.open(hero)
    small = full.resize((390, int(390 * full.height / full.width)),
                        Image.LANCZOS)
    crop = full.crop((int(full.width * 0.18), int(full.height * 0.26),
                      int(full.width * 0.86), int(full.height * 0.62)))
    crop = crop.resize((390, int(390 * crop.height / crop.width)), Image.LANCZOS)
    panels = [_labelled(small, "PHONE 390px", small.height),
              _labelled(crop, "PHONE DETAIL", small.height)]
    _row(panels).save(destination)
    print(f"  phone -> {destination}")


# --- clip -----------------------------------------------------------------


def encode(frame_dir: str, destination: str) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("  ffmpeg not found; leaving the clip as frames")
        return
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    subprocess.run(
        [ffmpeg, "-y", "-framerate", str(CLIP_FPS),
         "-i", os.path.join(frame_dir, "frame_%06d.png"),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", destination],
        check=True, capture_output=True,
    )
    for path in glob.glob(os.path.join(frame_dir, "frame_*.png")):
        os.remove(path)
    print(f"  clip -> {destination}")


# --- commands -------------------------------------------------------------


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("shots", "sheets", "sweeps",
                                            "motion", "all"))
    parser.add_argument("--godot")
    parser.add_argument("--width", type=int, default=WIDTH)
    parser.add_argument("--height", type=int, default=HEIGHT)
    options = parser.parse_args(argv)

    godot = find_godot(options.godot)
    os.makedirs(OUT_DOCS, exist_ok=True)
    scratch = os.path.join(OUT_MEDIA, "frames")

    if options.command in ("shots", "all"):
        print("stills:")
        render_stills(godot, OUT_DOCS, HERO_SHOTS, options.width,
                      options.height,
                      dump_modules=os.path.join(OUT_DOCS, "modules.json"))
        for source, target in (("hero", "machine_v2"), ("start", "start_v2"),
                               ("bowl", "bowl_v2"), ("track", "track_v2")):
            shutil.copyfile(os.path.join(OUT_DOCS, f"{source}.png"),
                            os.path.join(OUT_DOCS, f"{target}.png"))

    if options.command in ("sheets", "all"):
        print("sheets:")
        module_sheet(OUT_DOCS, os.path.join(OUT_DOCS, "module_sheet.png"))
        target_comparison(os.path.join(OUT_DOCS, "machine_v2.png"),
                          os.path.join(OUT_DOCS, "target_comparison.png"))
        phone_sheet(os.path.join(OUT_DOCS, "machine_v2.png"),
                    os.path.join(OUT_DOCS, "phone.png"))

    if options.command in ("sweeps", "all"):
        print("sweeps:")
        sweeps = os.path.join(OUT_DOCS, "camera")
        render_stills(godot, sweeps, ELEVATION_SHOTS + AZIMUTH_SHOTS, 540, 960)
        sweep_sheet(sweeps, ELEVATION_SHOTS, ("16 deg", "20 deg", "24 deg",
                                              "28 deg"),
                    os.path.join(OUT_DOCS, "camera_elevation.png"))
        sweep_sheet(sweeps, AZIMUTH_SHOTS, ("18 deg", "34 deg", "50 deg",
                                            "66 deg"),
                    os.path.join(OUT_DOCS, "camera_azimuth.png"))

    if options.command in ("motion", "all"):
        print("motion:")
        render_clip(godot, scratch, "hero")
        encode(scratch, os.path.join(OUT_MEDIA, "motion_proof.mp4"))

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except LabError as error:
        print(f"track_lab: {error}", file=sys.stderr)
        sys.exit(1)

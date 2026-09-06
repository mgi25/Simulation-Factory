"""Render the final hero machine: the hero still, module lenses, sheets, a clip.

An art driver, like ``visual_lab.py`` and ``track_lab.py`` and separate from
both. It launches Godot against ``scenes/HeroRender.tscn``, which builds the
seven-stage machine from the module scripts under
``godot/assets/marble_machine/hero/`` and photographs it. It loads no replay,
imports nothing from ``race`` or ``engine``, and cannot change what a race does.

Finding Godot, in order: ``--godot``, then ``$GODOT_BIN`` or ``$GODOT4_BIN``,
then the PATH. The same rule every other render tool here follows.

Typical use::

    python tools/hero_lab.py preview      # fast 540x960 hero, for iterating
    python tools/hero_lab.py shots        # hero + phone + seven module stills
    python tools/hero_lab.py sheets       # target comparison, phone, modules
    python tools/hero_lab.py sweeps       # elevation / azimuth / lens sheets
    python tools/hero_lab.py motion       # the 6-second clip
    python tools/hero_lab.py all
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
RENDER_SCENE = "scenes/HeroRender.tscn"

OUT_DOCS = os.path.join(REPO, "docs", "validation", "final_hero_machine")
OUT_MEDIA = os.path.join(REPO, "output", "final_hero_machine")
PREVIEW = os.path.join(REPO, "docs", "validation", "final_hero_machine",
                       "_preview")
REFERENCE = os.path.join(REPO, "docs", "references",
                         "neon_marble_machine_concept.png")

WIDTH = 1080
HEIGHT = 1920
MODULE_SIZE = 1200
PREVIEW_WIDTH = 540
PREVIEW_HEIGHT = 960
CLIP_FPS = 30
CLIP_SECONDS = 6.0

# The reference sheet is a multi-panel infographic; its left column is the
# hero render of the machine and the only part a hero frame can be compared
# against. This fraction is that column's right edge.
REFERENCE_HERO_FRACTION = 0.335

MODULE_SHOTS = ("start", "bowl", "s_bridge", "collector", "split",
                "compression", "finish")
HERO_SHOTS = ("hero", "phone") + MODULE_SHOTS
ELEVATION_SHOTS = ("e18", "e21", "e24", "e27")
AZIMUTH_SHOTS = ("a26", "a33", "a40", "a47")
LENS_SHOTS = ("f28", "a33", "f35", "f38")

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
        f"{' or '.join('$' + name for name in GODOT_ENV_VARS)}, or put it "
        "on PATH."
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
        tail = "\n".join((result.stdout or "").splitlines()[-30:])
        errors = "\n".join((result.stderr or "").splitlines()[-30:])
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
    """The seven stages, side by side at one height."""
    labels = ("1 START", "2 BOWL", "3 S-BRIDGE", "4 COLLECTOR", "5 SPLIT",
              "6 COMPRESSION", "7 FINISH")
    panels = [_labelled(Image.open(os.path.join(source, f"{n}.png")), t, 760)
              for n, t in zip(MODULE_SHOTS, labels)]
    _row(panels).save(destination)
    print(f"  module sheet -> {destination}")


def target_comparison(hero: str, destination: str) -> None:
    """Reference hero column beside ours, at equal visual height.

    Equal height and no cropping of either side. The brief's own rule is that
    a comparison must not hide a weakness behind a different scale, and the
    only honest way to hold to that is to fit both to the same number of
    pixels top to bottom and show whatever width that produces.
    """
    reference = Image.open(REFERENCE)
    column = reference.crop(
        (0, 0, int(reference.width * REFERENCE_HERO_FRACTION),
         reference.height))
    panels = [_labelled(column, "TARGET CONCEPT", 1240),
              _labelled(Image.open(hero), "FINAL HERO MACHINE", 1240)]
    _row(panels, 20).save(destination)
    print(f"  comparison -> {destination}")


def sweep_sheet(source: str, names: tuple[str, ...], labels: tuple[str, ...],
                destination: str) -> None:
    panels = [_labelled(Image.open(os.path.join(source, f"{n}.png")), t, 780)
              for n, t in zip(names, labels)]
    _row(panels).save(destination)
    print(f"  sweep -> {destination}")


def phone_sheet(hero: str, destination: str) -> None:
    """The hero at the size a phone actually shows it, beside a 2x crop.

    A hero frame is reviewed at 1080x1920 and then shipped to a screen a third
    that size, and detail that survives one does not always survive the other.
    The crop is there so the sheet answers both questions at once.
    """
    full = Image.open(hero)
    small = full.resize((390, int(390 * full.height / full.width)),
                        Image.LANCZOS)
    crop = full.crop((int(full.width * 0.12), int(full.height * 0.30),
                      int(full.width * 0.90), int(full.height * 0.74)))
    crop = crop.resize((390, int(390 * crop.height / crop.width)),
                       Image.LANCZOS)
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
    parser.add_argument("command", choices=("preview", "shots", "sheets",
                                            "sweeps", "motion", "all"))
    parser.add_argument("--godot")
    parser.add_argument("--shots", help="comma-separated shot names")
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    options = parser.parse_args(argv)

    godot = find_godot(options.godot)
    os.makedirs(OUT_DOCS, exist_ok=True)
    scratch = os.path.join(OUT_MEDIA, "frames")

    if options.command == "preview":
        shots = tuple(s.strip() for s in options.shots.split(",")) \
            if options.shots else ("hero",)
        render_stills(godot, PREVIEW, shots,
                      options.width or PREVIEW_WIDTH,
                      options.height or PREVIEW_HEIGHT)
        return 0

    if options.command in ("shots", "all"):
        print("stills:")
        render_stills(godot, OUT_DOCS, ("hero", "phone"),
                      options.width or WIDTH, options.height or HEIGHT,
                      dump_modules=os.path.join(OUT_DOCS,
                                                "physics_anchors.json"))
        # The module stills are square. A 9:16 frame is the right shape for
        # the machine and the wrong one for any single module in it: the lens
        # is fitted to the module's height, so a tall frame necessarily
        # includes the modules above and below and the subject ends up as a
        # third of its own inspection shot.
        render_stills(godot, OUT_DOCS, MODULE_SHOTS,
                      MODULE_SIZE, MODULE_SIZE)

    if options.command in ("sheets", "all"):
        print("sheets:")
        hero = os.path.join(OUT_DOCS, "hero.png")
        module_sheet(OUT_DOCS, os.path.join(OUT_DOCS, "module_sheet.png"))
        target_comparison(hero,
                          os.path.join(OUT_DOCS, "target_comparison.png"))
        phone_sheet(hero, os.path.join(OUT_DOCS, "phone.png"))

    if options.command in ("sweeps", "all"):
        print("sweeps:")
        sweeps = os.path.join(OUT_DOCS, "camera")
        render_stills(godot, sweeps,
                      ELEVATION_SHOTS + AZIMUTH_SHOTS + ("f28", "f35", "f38"),
                      540, 960)
        sweep_sheet(sweeps, ELEVATION_SHOTS,
                    ("18 deg", "21 deg", "24 deg", "27 deg"),
                    os.path.join(OUT_DOCS, "camera_elevation.png"))
        sweep_sheet(sweeps, AZIMUTH_SHOTS,
                    ("26 deg", "33 deg", "40 deg", "47 deg"),
                    os.path.join(OUT_DOCS, "camera_azimuth.png"))
        sweep_sheet(sweeps, LENS_SHOTS,
                    ("FOV 28", "FOV 32", "FOV 35", "FOV 38"),
                    os.path.join(OUT_DOCS, "camera_lens.png"))

    if options.command in ("motion", "all"):
        print("motion:")
        render_clip(godot, scratch, "hero")
        encode(scratch, os.path.join(OUT_MEDIA, "motion_proof.mp4"))

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except LabError as error:
        print(f"hero_lab: {error}", file=sys.stderr)
        sys.exit(1)

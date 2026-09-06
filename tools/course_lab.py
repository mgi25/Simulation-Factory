"""Render the sloped race course: layout studies, section stills, a clip.

An art driver, a sibling of ``hero_lab.py`` and separate from it. It launches
Godot against ``scenes/CourseRender.tscn``, which builds one layout from
``godot/assets/marble_machine/course/`` and photographs it. It loads no replay,
imports nothing from ``race`` or ``engine``, and cannot change what a race does.

Finding Godot, in order: ``--godot``, then ``$GODOT_BIN`` or ``$GODOT4_BIN``,
then the PATH.

Typical use::

    python tools/course_lab.py study            # the three layouts, low res
    python tools/course_lab.py preview -l b     # one fast frame, for iterating
    python tools/course_lab.py shots            # the seven section stills
    python tools/course_lab.py sheets           # comparisons
    python tools/course_lab.py motion           # the camera proof
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
RENDER_SCENE = "scenes/CourseRender.tscn"

OUT_DOCS = os.path.join(REPO, "docs", "validation", "sloped_course")
OUT_MEDIA = os.path.join(REPO, "output", "sloped_course")
PREVIEW = os.path.join(OUT_DOCS, "_preview")
CONCEPT = os.path.join(REPO, "docs", "references",
                       "neon_marble_machine_concept.png")
START_REFERENCE = os.path.join(REPO, "docs", "references",
                               "sloped_course_start_reference.png")
LAYOUT_REFERENCE = os.path.join(REPO, "docs", "references",
                                "sloped_course_layout_reference.png")

WIDTH = 1080
HEIGHT = 1920
STUDY_WIDTH = 620
STUDY_HEIGHT = 1102
PREVIEW_WIDTH = 540
PREVIEW_HEIGHT = 960
CLIP_FPS = 30
CLIP_SECONDS = 8.0

# The concept sheet is a multi-panel infographic; its left column is the hero
# render and the only part a hero frame can honestly be compared against.
CONCEPT_HERO_FRACTION = 0.335

SECTION_SHOTS = ("start", "descent", "long_track", "obstacle", "split",
                 "final_run", "finish")

GODOT_ENV_VARS = ("GODOT_BIN", "GODOT4_BIN")
GODOT_ON_PATH = ("godot", "godot4", "Godot_v4.7.2-stable_win64.exe")

SELECTED = "b"


class LabError(RuntimeError):
    """The render did not produce what was asked for."""


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


def run_godot(command: list[str], label: str) -> None:
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
        stripped = line.strip()
        if stripped.startswith(("scene:", "rendered", "layout", "length",
                                "start->finish", "hero lens", "physics")):
            print(f"    {stripped}")
    print(f"  {label}: {elapsed:.1f}s")


def render(godot: str, out_dir: str, shots: tuple[str, ...], layout: str,
           width: int, height: int, detail: str = "block",
           dump_physics: str | None = None) -> None:
    os.makedirs(out_dir, exist_ok=True)
    command = [
        godot, "--path", GODOT_PROJECT, RENDER_SCENE, "--",
        f"--out-dir={os.path.abspath(out_dir)}",
        f"--shots={','.join(shots)}",
        f"--width={width}", f"--height={height}",
        f"--layout={layout}", f"--detail={detail}",
    ]
    if dump_physics:
        command.append(f"--dump-physics={os.path.abspath(dump_physics)}")
    run_godot(command, f"{layout}/{detail} [{', '.join(shots)}] {width}x{height}")
    missing = [n for n in shots
               if not os.path.isfile(os.path.join(out_dir, f"{n}.png"))]
    if missing:
        raise LabError(f"no image written for {', '.join(missing)}")


def render_clip(godot: str, out_dir: str, layout: str, detail: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    frames = int(CLIP_SECONDS * CLIP_FPS)
    command = [
        godot, "--path", GODOT_PROJECT, RENDER_SCENE, "--",
        f"--out-dir={os.path.abspath(out_dir)}",
        f"--frames={frames}", f"--fps={CLIP_FPS}",
        f"--width={WIDTH}", f"--height={HEIGHT}",
        f"--layout={layout}", f"--detail={detail}", "--shot=hero",
        "--sequence=1",
    ]
    run_godot(command, f"clip {layout} ({frames} frames)")


# --- sheets ---------------------------------------------------------------


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _labelled(image: Image.Image, text: str, height: int) -> Image.Image:
    scale = height / image.height
    panel = image.resize((max(1, int(image.width * scale)), height),
                         Image.LANCZOS)
    bar = 56
    out = Image.new("RGB", (panel.width, height + bar), (10, 14, 20))
    out.paste(panel, (0, 0))
    draw = ImageDraw.Draw(out)
    draw.text((16, height + 15), text, font=_font(26), fill=(214, 232, 244))
    return out


def _row(panels: list[Image.Image], gap: int = 16) -> Image.Image:
    width = sum(p.width for p in panels) + gap * (len(panels) - 1)
    height = max(p.height for p in panels)
    sheet = Image.new("RGB", (width, height), (10, 14, 20))
    x = 0
    for panel in panels:
        sheet.paste(panel, (x, 0))
        x += panel.width + gap
    return sheet


def layout_comparison(destination: str) -> None:
    labels = ("A  CLIFF DESCENT", "B  ZIG-ZAG RACEWAY", "C  OPEN MOUNTAIN RUN")
    panels = [
        _labelled(Image.open(os.path.join(OUT_DOCS, f"layout_{k}.png")),
                  text, 1180)
        for k, text in zip("abc", labels)
    ]
    _row(panels).save(destination)
    print(f"  comparison -> {destination}")


def section_sheet(destination: str) -> None:
    labels = ("1 START", "2 FIRST DESCENT", "3 LONG SWEEP", "4 OBSTACLE",
              "5 SPLIT", "6 FINAL RUN", "7 FINISH")
    panels = [_labelled(Image.open(os.path.join(OUT_DOCS, f"{n}.png")), t, 700)
              for n, t in zip(SECTION_SHOTS, labels)]
    _row(panels).save(destination)
    print(f"  sections -> {destination}")


def quality_comparison(hero: str, destination: str) -> None:
    """The concept's hero column beside ours, at equal height, uncropped.

    The layouts differ on purpose - that is the whole point of this branch - so
    this sheet is about material, light and finish only.
    """
    concept = Image.open(CONCEPT)
    column = concept.crop((0, 0, int(concept.width * CONCEPT_HERO_FRACTION),
                           concept.height))
    panels = [_labelled(column, "TARGET CONCEPT  (quality)", 1240),
              _labelled(Image.open(hero), "SLOPED COURSE  (ours)", 1240)]
    _row(panels, 20).save(destination)
    print(f"  quality -> {destination}")


def reference_comparison(destination: str) -> None:
    """The two real-world samples beside the sections they informed."""
    panels = [
        _labelled(Image.open(START_REFERENCE), "REF  START SAMPLE", 900),
        _labelled(Image.open(os.path.join(OUT_DOCS, "start.png")),
                  "OURS  START", 900),
        _labelled(Image.open(LAYOUT_REFERENCE), "REF  LONG SLOPED TRACK", 900),
        _labelled(Image.open(os.path.join(OUT_DOCS, "long_track.png")),
                  "OURS  LONG TRACK", 900),
    ]
    _row(panels).save(destination)
    print(f"  reference -> {destination}")


def phone_sheet(hero: str, destination: str) -> None:
    full = Image.open(hero)
    small = full.resize((390, int(390 * full.height / full.width)),
                        Image.LANCZOS)
    crop = full.crop((int(full.width * 0.10), int(full.height * 0.28),
                      int(full.width * 0.92), int(full.height * 0.76)))
    crop = crop.resize((390, int(390 * crop.height / crop.width)),
                       Image.LANCZOS)
    panels = [_labelled(small, "PHONE 390px", small.height),
              _labelled(crop, "PHONE DETAIL", small.height)]
    _row(panels).save(destination)
    print(f"  phone -> {destination}")


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
    parser.add_argument("command", choices=("study", "preview", "shots",
                                            "sheets", "motion", "all"))
    parser.add_argument("--godot")
    parser.add_argument("-l", "--layout", default=SELECTED)
    parser.add_argument("--shots", help="comma-separated shot names")
    parser.add_argument("--detail", default="hero",
                        choices=("block", "hero"))
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    options = parser.parse_args(argv)

    godot = find_godot(options.godot)
    os.makedirs(OUT_DOCS, exist_ok=True)

    if options.command == "study":
        print("layout study:")
        for key in "abc":
            render(godot, PREVIEW, ("hero",), key,
                   options.width or STUDY_WIDTH,
                   options.height or STUDY_HEIGHT, "block")
            shutil.copyfile(os.path.join(PREVIEW, "hero.png"),
                            os.path.join(OUT_DOCS, f"layout_{key}.png"))
        layout_comparison(os.path.join(OUT_DOCS, "layout_comparison.png"))
        return 0

    if options.command == "preview":
        shots = tuple(s.strip() for s in options.shots.split(",")) \
            if options.shots else ("hero",)
        render(godot, PREVIEW, shots, options.layout,
               options.width or PREVIEW_WIDTH,
               options.height or PREVIEW_HEIGHT, options.detail)
        return 0

    if options.command in ("shots", "all"):
        print("stills:")
        render(godot, OUT_DOCS, ("hero",), options.layout,
               options.width or WIDTH, options.height or HEIGHT,
               options.detail,
               dump_physics=os.path.join(OUT_DOCS, "physics_layout.json"))
        render(godot, OUT_DOCS, SECTION_SHOTS, options.layout,
               options.width or WIDTH, options.height or HEIGHT,
               options.detail)

    if options.command in ("sheets", "all"):
        print("sheets:")
        hero = os.path.join(OUT_DOCS, "hero.png")
        section_sheet(os.path.join(OUT_DOCS, "section_sheet.png"))
        quality_comparison(
            hero, os.path.join(OUT_DOCS, "visual_quality_comparison.png"))
        reference_comparison(
            os.path.join(OUT_DOCS, "layout_reference_comparison.png"))
        phone_sheet(hero, os.path.join(OUT_DOCS, "phone.png"))

    if options.command in ("motion", "all"):
        print("motion:")
        scratch = os.path.join(OUT_MEDIA, "frames")
        render_clip(godot, scratch, options.layout, options.detail)
        encode(scratch, os.path.join(OUT_MEDIA, "motion_proof.mp4"))

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except LabError as error:
        print(f"course_lab: {error}", file=sys.stderr)
        sys.exit(1)

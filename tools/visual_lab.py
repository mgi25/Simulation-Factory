"""Render the marble visual lab: hero stills, lens sweeps, variants, a clip.

The lab is an art experiment, so this driver deliberately has no simulation in
it. It does not load a replay, does not import anything from ``race`` or
``engine``, and cannot change what a race does. It launches Godot against
``scenes/LabRender.tscn``, which builds an authored machine from the module
scripts under ``godot/assets/marble_machine/`` and photographs it.

Finding Godot, in order: ``--godot``, then ``$GODOT_BIN`` or ``$GODOT4_BIN``,
then the PATH. Same rule as every other render tool here.

Typical use::

    python tools/visual_lab.py hero          # the hero still, one variant
    python tools/visual_lab.py variants      # tower / deck / spine sheet
    python tools/visual_lab.py lenses        # the five-way field-of-view sweep
    python tools/visual_lab.py compare       # reference | hero comparison
    python tools/visual_lab.py motion        # the short clip
    python tools/visual_lab.py all
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time

from PIL import Image, ImageDraw, ImageFont

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GODOT_PROJECT = os.path.join(REPO, "godot")
RENDER_SCENE = "scenes/LabRender.tscn"

OUT_DOCS = os.path.join(REPO, "docs", "validation", "marble_visual_lab")
OUT_MEDIA = os.path.join(REPO, "output", "marble_visual_lab")
REFERENCE = os.path.join(REPO, "docs", "references", "neon_marble_machine_concept.png")

WIDTH = 1080
HEIGHT = 1920
CLIP_FPS = 60
CLIP_SECONDS = 4.0

VARIANTS = ("tower", "deck", "spine")
LENS_SHOTS = ("fov30", "fov35", "fov40", "fov45", "fov50")
ANGLE_SHOTS = ("elev04", "elev18", "elev26", "azi00", "azi55")
PRODUCT_SHOTS = ("bowl", "start", "collector", "upper")

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
    """One Godot invocation. Returns wall seconds; raises on a bad exit."""
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
    print(f"  {label}: {elapsed:.1f}s")
    return elapsed


def render_stills(
    godot: str,
    out_dir: str,
    shots: tuple[str, ...],
    variant: str,
    no_glow: bool = False,
    width: int = WIDTH,
    height: int = HEIGHT,
) -> float:
    os.makedirs(out_dir, exist_ok=True)
    command = [
        godot,
        "--path",
        GODOT_PROJECT,
        RENDER_SCENE,
        "--",
        f"--out-dir={os.path.abspath(out_dir)}",
        f"--shots={','.join(shots)}",
        f"--width={width}",
        f"--height={height}",
        f"--lab-variant={variant}",
    ]
    if no_glow:
        command.append("--lab-no-glow=1")
    elapsed = run_godot(command, f"{variant} [{', '.join(shots)}]")

    missing = [name for name in shots if not os.path.isfile(
        os.path.join(out_dir, f"{name}.png"))]
    if missing:
        raise LabError(f"{variant}: no image written for {', '.join(missing)}")
    return elapsed


def render_clip(godot: str, out_dir: str, variant: str, shot: str) -> float:
    os.makedirs(out_dir, exist_ok=True)
    frames = int(CLIP_SECONDS * CLIP_FPS)
    command = [
        godot,
        "--path",
        GODOT_PROJECT,
        RENDER_SCENE,
        "--",
        f"--out-dir={os.path.abspath(out_dir)}",
        f"--frames={frames}",
        f"--fps={CLIP_FPS}",
        f"--width={WIDTH}",
        f"--height={HEIGHT}",
        f"--lab-variant={variant}",
        f"--lab-shot={shot}",
    ]
    return run_godot(command, f"clip {variant}/{shot} ({frames} frames)")


# --- sheets ---------------------------------------------------------------


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def contact_sheet(
    panels: list[tuple[str, str]],
    out_path: str,
    panel_height: int = 1180,
    gap: int = 26,
    title: str = "",
) -> str:
    """Lay images side by side at one display height, each captioned.

    The brief's comparison rule is "same display height", which is the only
    fair way to put a portrait render beside a landscape concept sheet: equal
    height means equal apparent scale for the thing being judged, and letting
    each keep its own aspect means neither is distorted to fit the other.
    """
    loaded = []
    for caption, path in panels:
        if not os.path.isfile(path):
            raise LabError(f"contact sheet: missing {path}")
        image = Image.open(path).convert("RGB")
        scale = panel_height / image.height
        loaded.append((caption, image.resize(
            (max(1, round(image.width * scale)), panel_height), Image.LANCZOS)))

    label_height = 58
    title_height = 76 if title else 0
    total_width = sum(image.width for _, image in loaded) + gap * (len(loaded) + 1)
    total_height = title_height + label_height + panel_height + gap * 2

    sheet = Image.new("RGB", (total_width, total_height), (14, 16, 20))
    draw = ImageDraw.Draw(sheet)

    if title:
        draw.text((gap, gap), title, font=_font(40), fill=(232, 238, 244))

    x = gap
    for caption, image in loaded:
        y = title_height + gap
        draw.text((x, y), caption, font=_font(30), fill=(150, 216, 232))
        sheet.paste(image, (x, y + label_height))
        draw.rectangle(
            [x - 1, y + label_height - 1, x + image.width, y + label_height + panel_height],
            outline=(48, 54, 62), width=1)
        x += image.width + gap

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    sheet.save(out_path)
    print(f"  sheet -> {out_path}  ({sheet.width}x{sheet.height})")
    return out_path


def encode_clip(frame_dir: str, out_path: str) -> str:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise LabError("ffmpeg is not on PATH; cannot encode the motion proof")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    command = [
        ffmpeg, "-y",
        "-framerate", str(CLIP_FPS),
        "-i", os.path.join(frame_dir, "frame_%06d.png"),
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", "17",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        out_path,
    ]
    result = subprocess.run(command, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if result.returncode != 0:
        tail = "\n".join((result.stderr or "").splitlines()[-15:])
        raise LabError(f"ffmpeg exited {result.returncode}\n{tail}")
    size_mb = os.path.getsize(out_path) / (1024 * 1024)
    print(f"  clip -> {out_path}  ({size_mb:.1f} MiB)")
    return out_path


# --- tasks ----------------------------------------------------------------


def task_hero(godot: str, variant: str) -> None:
    render_stills(godot, OUT_DOCS, ("hero",), variant)
    os.replace(os.path.join(OUT_DOCS, "hero.png"),
               os.path.join(OUT_DOCS, "hero_v1.png"))
    print(f"  hero -> {os.path.join(OUT_DOCS, 'hero_v1.png')}")


def task_variants(godot: str) -> None:
    panels = []
    for variant in VARIANTS:
        directory = os.path.join(OUT_DOCS, "variants", variant)
        render_stills(godot, directory, ("hero",), variant)
        panels.append((variant.upper(), os.path.join(directory, "hero.png")))
    contact_sheet(panels, os.path.join(OUT_DOCS, "variants_v1.png"),
                  title="ART VARIANTS - support design, proportion, trim, density")


def task_lenses(godot: str, variant: str) -> None:
    directory = os.path.join(OUT_DOCS, "lenses")
    render_stills(godot, directory, LENS_SHOTS, variant)
    contact_sheet(
        [(name.replace("fov", "") + " deg", os.path.join(directory, f"{name}.png"))
         for name in LENS_SHOTS],
        os.path.join(OUT_DOCS, "lens_sweep_v1.png"), panel_height=980,
        title="FIELD OF VIEW - machine held at one height, lens varied")

    render_stills(godot, directory, ANGLE_SHOTS, variant)
    contact_sheet(
        [(name, os.path.join(directory, f"{name}.png")) for name in ANGLE_SHOTS],
        os.path.join(OUT_DOCS, "angle_sweep_v1.png"), panel_height=980,
        title="ELEVATION AND AZIMUTH")


def task_product(godot: str, variant: str) -> None:
    directory = os.path.join(OUT_DOCS, "product")
    render_stills(godot, directory, PRODUCT_SHOTS, variant)
    contact_sheet(
        [(name.upper(), os.path.join(directory, f"{name}.png"))
         for name in PRODUCT_SHOTS],
        os.path.join(OUT_DOCS, "modules_v1.png"), panel_height=1080,
        title="MODULES - one lens each, same rig")


def task_control(godot: str, variant: str) -> None:
    """The bloom-off frame. If the picture only works with glow, it does not
    work: every earlier style pass in this project carried the same control."""
    directory = os.path.join(OUT_DOCS, "control")
    render_stills(godot, directory, ("hero",), variant, no_glow=True)
    os.replace(os.path.join(directory, "hero.png"),
               os.path.join(OUT_DOCS, "hero_v1_no_glow.png"))
    print(f"  control -> {os.path.join(OUT_DOCS, 'hero_v1_no_glow.png')}")


def task_compare() -> None:
    hero = os.path.join(OUT_DOCS, "hero_v1.png")
    contact_sheet(
        [("TARGET CONCEPT", REFERENCE), ("HERO V1", hero)],
        os.path.join(OUT_DOCS, "reference_comparison_v1.png"),
        panel_height=1300,
        title="")


def task_motion(godot: str, variant: str) -> None:
    frames = os.path.join(OUT_MEDIA, "frames")
    render_clip(godot, frames, variant, "hero")
    encode_clip(frames, os.path.join(OUT_MEDIA, "hero_motion.mp4"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "task",
        choices=["hero", "variants", "lenses", "product", "control", "compare",
                 "motion", "all"],
        help="what to render")
    parser.add_argument("--godot", default=None, help="path to the Godot 4 binary")
    parser.add_argument("--variant", default="tower", choices=list(VARIANTS),
                        help="art variant for single-variant tasks")
    arguments = parser.parse_args(argv)

    try:
        needs_godot = arguments.task != "compare"
        godot = find_godot(arguments.godot) if needs_godot else ""
        if needs_godot:
            print(f"godot: {godot}")

        if arguments.task in ("hero", "all"):
            task_hero(godot, arguments.variant)
        if arguments.task in ("variants", "all"):
            task_variants(godot)
        if arguments.task in ("lenses", "all"):
            task_lenses(godot, arguments.variant)
        if arguments.task in ("product", "all"):
            task_product(godot, arguments.variant)
        if arguments.task in ("control", "all"):
            task_control(godot, arguments.variant)
        if arguments.task in ("compare", "all"):
            task_compare()
        if arguments.task in ("motion", "all"):
            task_motion(godot, arguments.variant)
    except LabError as error:
        print(f"visual_lab: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

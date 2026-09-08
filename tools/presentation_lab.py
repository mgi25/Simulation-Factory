"""Photograph the sloped course's presentation pass: stills, sheets, a proof.

A fifth art driver, and an edit to none of the four before it. `course_lab.py`
still renders the approved sloped-course proofs from the same scene with the
same seven section lenses, so the committed frames in
``docs/validation/sloped_course/`` remain the *before* of this comparison and
are not overwritten. This tool renders the eleven presentation camera
candidates instead, and writes their measured clearances alongside.

Finding Godot, in order: ``--godot``, then ``$GODOT_BIN`` or ``$GODOT4_BIN``,
then the PATH.

Typical use::

    python tools/presentation_lab.py preview     # eleven candidates, fast
    python tools/presentation_lab.py shots       # the deliverables, full res
    python tools/presentation_lab.py sheets      # contact, phone, before/after
    python tools/presentation_lab.py motion      # the camera proof
    python tools/presentation_lab.py all
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

OUT_DOCS = os.path.join(REPO, "docs", "validation", "presentation_polish")
OUT_MEDIA = os.path.join(REPO, "output", "presentation_polish")
PREVIEW = os.path.join(OUT_DOCS, "_preview")
BEFORE = os.path.join(REPO, "docs", "validation", "sloped_course")

WIDTH = 1080
HEIGHT = 1920
PREVIEW_WIDTH = 405
PREVIEW_HEIGHT = 720
PHONE_WIDTH = 390
CLIP_FPS = 30
CLIP_SECONDS = 8.0

LAYOUT = "b"

# The nine sections the brief asks for, in course order, plus the two plates
# that photograph this branch's own work rather than the race.
CANDIDATES = (
    "start_event", "first_descent", "fast_turn", "hairpin", "long_straight",
    "obstacle_action", "split_wide", "final_sprint", "finish_push",
    "environment", "track_materials",
)

# The brief's required filenames, and which candidate answers each.
DELIVERABLES = {
    "environment.png": "environment",
    "track_materials.png": "track_materials",
    "obstacle_view.png": "obstacle_action",
    "split_view.png": "split_wide",
    "final_run.png": "final_sprint",
    "finish_view.png": "finish_push",
}

CONTACT_LABELS = (
    ("start_event", "1  START"),
    ("first_descent", "2  FIRST DESCENT"),
    ("fast_turn", "3  FAST TURN"),
    ("hairpin", "4  HAIRPIN"),
    ("long_straight", "5  LONG STRAIGHT"),
    ("obstacle_action", "6  OBSTACLE"),
    ("split_wide", "7  SPLIT"),
    ("final_sprint", "8  FINAL RUN"),
    ("finish_push", "9  FINISH"),
    ("environment", "ENVIRONMENT"),
    ("track_materials", "TRACK MATERIALS"),
)

# before-name, after-name, caption. The five framings this pass changed most.
BEFORE_AFTER = (
    ("split", "split_wide", "SPLIT"),
    ("obstacle", "obstacle_action", "OBSTACLE"),
    ("finish", "finish_push", "FINISH"),
    ("start", "start_event", "START"),
    ("long_track", "long_straight", "LONG RUN"),
)

# The frames the phone sheet has to survive, and what each one is checked for.
PHONE_CHECKS = (
    ("start_event", "racers at the line, sign legible"),
    ("first_descent", "direction of travel obvious"),
    ("split_wide", "blue against orange readable"),
    ("final_sprint", "warm zone reads, supports subordinate"),
    ("finish_push", "finish unmistakable"),
    ("environment", "environment adds depth, not clutter"),
)

GODOT_ENV_VARS = ("GODOT_BIN", "GODOT4_BIN")
GODOT_ON_PATH = ("godot", "godot4", "Godot_v4.7.2-stable_win64.exe")


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
        if stripped.startswith(("layout", "length", "start->finish",
                                "candidates", "cameras ->", "scene:")):
            print(f"    {stripped}")
        # The per-candidate clearance table, which is the point of the tool.
        if stripped.startswith(tuple(CANDIDATES)):
            print(f"      {stripped}")
    print(f"  {label}: {elapsed:.1f}s")


def render(godot: str, out_dir: str, shots: tuple[str, ...], width: int,
           height: int, dump_cameras: str | None = None) -> None:
    os.makedirs(out_dir, exist_ok=True)
    command = [
        godot, "--path", GODOT_PROJECT, RENDER_SCENE, "--",
        f"--out-dir={os.path.abspath(out_dir)}",
        f"--shots={','.join(shots)}",
        f"--width={width}", f"--height={height}",
        f"--layout={LAYOUT}", "--detail=hero",
    ]
    if dump_cameras:
        command.append(f"--dump-cameras={os.path.abspath(dump_cameras)}")
    run_godot(command, f"{len(shots)} candidates at {width}x{height}")
    missing = [n for n in shots
               if not os.path.isfile(os.path.join(out_dir, f"{n}.png"))]
    if missing:
        raise LabError(f"no image written for {', '.join(missing)}")


def render_clip(godot: str, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    frames = int(CLIP_SECONDS * CLIP_FPS)
    command = [
        godot, "--path", GODOT_PROJECT, RENDER_SCENE, "--",
        f"--out-dir={os.path.abspath(out_dir)}",
        f"--frames={frames}", f"--fps={CLIP_FPS}",
        f"--width={WIDTH}", f"--height={HEIGHT}",
        f"--layout={LAYOUT}", "--detail=hero", "--shot=hero",
        "--sequence=polish",
    ]
    run_godot(command, f"camera proof ({frames} frames)")


# --- sheets ---------------------------------------------------------------


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _labelled(image: Image.Image, text: str, height: int,
              caption: str = "") -> Image.Image:
    scale = height / image.height
    panel = image.resize((max(1, int(image.width * scale)), height),
                         Image.LANCZOS)
    bar = 54 if not caption else 84
    out = Image.new("RGB", (panel.width, height + bar), (10, 14, 20))
    out.paste(panel, (0, 0))
    draw = ImageDraw.Draw(out)
    draw.text((14, height + 13), text, font=_font(25), fill=(214, 232, 244))
    if caption:
        draw.text((14, height + 48), caption, font=_font(19),
                  fill=(138, 164, 186))
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


def _grid(panels: list[Image.Image], columns: int,
          gap: int = 14) -> Image.Image:
    width = max(p.width for p in panels)
    height = max(p.height for p in panels)
    rows = (len(panels) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * width + gap * (columns - 1),
                              rows * height + gap * (rows - 1)), (10, 14, 20))
    for index, panel in enumerate(panels):
        sheet.paste(panel, ((index % columns) * (width + gap),
                            (index // columns) * (height + gap)))
    return sheet


def contact_sheet(source: str, destination: str) -> None:
    """All eleven candidates, in course order, on one page."""
    panels = [
        _labelled(Image.open(os.path.join(source, f"{name}.png")), label, 620)
        for name, label in CONTACT_LABELS
    ]
    _grid(panels, 6).save(destination)
    print(f"  contact -> {destination}")


def before_after(source: str, destination: str) -> None:
    """The five framings this pass changed most, against what they replaced.

    The *before* frames are the committed sloped-course proofs, untouched on
    this branch on purpose: a presentation pass that overwrites its own
    reference cannot be reviewed.
    """
    panels: list[Image.Image] = []
    for old, new, caption in BEFORE_AFTER:
        before_path = os.path.join(BEFORE, f"{old}.png")
        if not os.path.isfile(before_path):
            raise LabError(f"missing the before frame {before_path}")
        panels.append(_labelled(Image.open(before_path),
                                f"{caption}  BEFORE", 760))
        panels.append(_labelled(Image.open(os.path.join(source,
                                                        f"{new}.png")),
                                f"{caption}  AFTER", 760))
    _grid(panels, 4).save(destination)
    print(f"  before/after -> {destination}")


def phone_sheet(source: str, destination: str) -> None:
    """Six candidates at phone width, each with what it is checked for.

    390 logical pixels is the narrow end of a phone in portrait, and the whole
    point of the sheet is that a frame which reads at 1080 can still lose its
    racers, its route colours or its direction of travel at 390.
    """
    panels: list[Image.Image] = []
    for name, check in PHONE_CHECKS:
        full = Image.open(os.path.join(source, f"{name}.png"))
        small = full.resize(
            (PHONE_WIDTH, int(PHONE_WIDTH * full.height / full.width)),
            Image.LANCZOS)
        panels.append(_labelled(small, name.replace("_", " ").upper(),
                                small.height, check))
    sheet = _grid(panels, 6)
    # And one detail crop at phone scale, which is what a viewer who stops
    # scrolling actually sees.
    hero = Image.open(os.path.join(source, "split_wide.png"))
    crop = hero.crop((int(hero.width * 0.06), int(hero.height * 0.24),
                      int(hero.width * 0.94), int(hero.height * 0.72)))
    crop = crop.resize((PHONE_WIDTH * 2,
                        int(PHONE_WIDTH * 2 * crop.height / crop.width)),
                       Image.LANCZOS)
    detail = _labelled(crop, "SPLIT  DETAIL AT PHONE SCALE",
                       crop.height, "both branches must stay separable")
    out = Image.new("RGB", (max(sheet.width, detail.width),
                            sheet.height + 14 + detail.height), (10, 14, 20))
    out.paste(sheet, (0, 0))
    out.paste(detail, (0, sheet.height + 14))
    out.save(destination)
    print(f"  phone -> {destination}")


def encode(frame_dir: str, destination: str) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("  ffmpeg not found; leaving the proof as frames")
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
    print(f"  proof -> {destination}")


# --- commands -------------------------------------------------------------


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preview", "shots", "sheets",
                                            "motion", "all"))
    parser.add_argument("--godot")
    parser.add_argument("--shots", help="comma-separated candidate names")
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    options = parser.parse_args(argv)

    godot = find_godot(options.godot)
    os.makedirs(OUT_DOCS, exist_ok=True)
    chosen = tuple(s.strip() for s in options.shots.split(",")) \
        if options.shots else CANDIDATES

    if options.command == "preview":
        print("candidates, preview:")
        render(godot, PREVIEW, chosen,
               options.width or PREVIEW_WIDTH,
               options.height or PREVIEW_HEIGHT,
               dump_cameras=os.path.join(PREVIEW, "cameras.json"))
        return 0

    if options.command in ("shots", "all"):
        print("candidates, full res:")
        render(godot, OUT_DOCS, chosen, options.width or WIDTH,
               options.height or HEIGHT,
               dump_cameras=os.path.join(OUT_DOCS, "cameras.json"))
        # The brief names its deliverables; the candidates name their
        # sections. Copied rather than renamed so the contact sheet and the
        # camera file can keep speaking about sections.
        for filename, candidate in DELIVERABLES.items():
            # Two of the brief's names already are their candidate's name.
            if filename == f"{candidate}.png":
                continue
            shutil.copyfile(os.path.join(OUT_DOCS, f"{candidate}.png"),
                            os.path.join(OUT_DOCS, filename))
            print(f"    {candidate} -> {filename}")

    if options.command in ("sheets", "all"):
        print("sheets:")
        contact_sheet(OUT_DOCS, os.path.join(OUT_DOCS, "contact_sheet.png"))
        before_after(OUT_DOCS, os.path.join(OUT_DOCS, "before_after.png"))
        phone_sheet(OUT_DOCS, os.path.join(OUT_DOCS, "phone.png"))

    if options.command in ("motion", "all"):
        print("motion:")
        scratch = os.path.join(OUT_MEDIA, "frames")
        render_clip(godot, scratch)
        encode(scratch, os.path.join(OUT_MEDIA, "camera_proof.mp4"))

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except LabError as error:
        print(f"presentation_lab: {error}", file=sys.stderr)
        sys.exit(1)

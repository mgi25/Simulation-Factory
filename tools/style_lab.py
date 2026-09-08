"""Lock the sloped course's visual design system: candidate sheets, then a board.

A fifth art driver and a sibling of ``course_lab.py``, not an edit to it: that
tool renders the layout study this branch inherited and has to keep rendering
it byte for byte. This one drives the same scene through
``godot/assets/marble_machine/course/course_style.gd``, whose five axes -
track, guard, support, environment, finish - are selected independently.

It loads no replay, imports nothing from ``race`` or ``engine``, and cannot
change what a race does.

Method, and the reason it is cheap: every candidate sheet varies **one** axis
and holds the other four at the locked setting, so a sheet answers "pearl or
silver" rather than "sheet 1 or sheet 3". Candidate panels render at
``PANEL`` height; only the board, the phone check and the comparison pay for
full resolution.

Finding Godot, in order: ``--godot``, then ``$GODOT_BIN`` or ``$GODOT4_BIN``,
then the PATH.

Typical use::

    python tools/style_lab.py axis track      # one candidate sheet
    python tools/style_lab.py candidates      # all five
    python tools/style_lab.py board           # the locked style, full res
    python tools/style_lab.py palette         # swatches, from the live dump
    python tools/style_lab.py all
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

from PIL import Image, ImageDraw, ImageFont

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GODOT_PROJECT = os.path.join(REPO, "godot")
RENDER_SCENE = "scenes/CourseRender.tscn"

OUT = os.path.join(REPO, "docs", "validation", "style_lock")
FRAMES = os.path.join(OUT, "_frames")
CONCEPT = os.path.join(REPO, "docs", "references",
                       "neon_marble_machine_concept.png")

LAYOUT = "b"
FULL = (1080, 1920)
PANEL = (560, 996)
INK = (9, 12, 17)
TEXT = (216, 233, 245)
DIM = (135, 156, 172)

# The concept sheet is a multi-panel infographic; its left column is the hero
# render and the only part a hero frame can honestly be compared against.
CONCEPT_HERO_FRACTION = 0.335

# Kept in step with `course_style.LOCK`. Asserted against the scene's own
# report on every render, so the two cannot drift apart silently.
LOCK = {"track": "pearl", "guard": "cast", "support": "brass",
        "env": "valley", "finish": "gold"}

# One axis, the shot that shows it, and the candidates in the order a sheet
# should read them: the shipped setting first, then the proposals.
#
# The shot per axis is the whole reason this is cheap. A guard is 0.26 units
# tall, so judging it from the hero lens is judging a two-pixel line; a
# support language only exists where the piers are tall, which is the viaduct
# on the final run. Each axis is photographed where it lives.
AXES = {
    "track": {
        # Two lenses, and neither is a race framing. `descent` is the only
        # shot on this course that looks down *into* the cradle with racers
        # sitting in it, which is where a running surface is either working
        # or not; `material` is a close section, added for this sheet, that
        # shows the value ladder across shell, lip, band and keel at once.
        # The first version of this sheet used `long_track`, whose bearing
        # of sixteen degrees shows the channel's *outer shell wall* - the one
        # surface none of these candidates change - and all four panels came
        # back indistinguishable.
        "shot": "descent",
        "second": "material",
        "options": ["base", "pearl", "silver", "fascia"],
        "labels": {
            "base": "BASE  shipped pearl",
            "pearl": "PEARL  warm shell / cool band",
            "silver": "SILVER  cool shell",
            "fascia": "FASCIA  soft gloss / black belly",
        },
        "title": "TRACK MATERIAL",
        "file": "track_material_candidates.png",
    },
    "guard": {
        "shot": "descent",
        "options": ["base", "tint", "lit", "glass", "cast"],
        "labels": {
            "base": "BASE  12% aqua tint",
            "tint": "TINT  30% + frosted edge",
            "lit": "LIT  22% + self-emission",
            "glass": "GLASS  40% cast",
            "cast": "CAST  34% + 0.40 emission  (PICK)",
        },
        "title": "GUARD SYSTEM",
        "file": "guard_candidates.png",
    },
    "support": {
        "shot": "final_run",
        "options": ["base", "brass", "copper", "mono"],
        "labels": {
            "base": "BASE  graphite + metal gold",
            "brass": "BRASS  lifted graphite + brass",
            "copper": "COPPER  deep graphite + copper",
            "mono": "MONO  two-tone, no warm accent",
        },
        "title": "SUPPORT SYSTEM",
        "file": "support_candidates.png",
    },
    "env": {
        "shot": "hero",
        "options": ["base", "depth", "valley", "warm"],
        "labels": {
            "base": "BASE  shipped dusk",
            "depth": "DEPTH  layer split + cool haze",
            "valley": "VALLEY  depth + settlement",
            "warm": "WARM  warm-dominant dusk",
        },
        "title": "ENVIRONMENT",
        "file": "environment_candidates.png",
    },
    "finish": {
        "shot": "finish",
        "options": ["base", "gold", "contrast"],
        "labels": {
            "base": "BASE  shipped gold",
            "gold": "GOLD  hotter wash, hard checker",
            "contrast": "CONTRAST  cool arena, gold trim",
        },
        "title": "FINISH ZONE",
        "file": "finish_zone_candidates.png",
    },
}

BOARD_SHOTS = ("hero", "start", "long_track", "split", "finish")
BOARD_LABELS = ("HERO", "START", "TRACK", "SPLIT CHOICE", "FINISH")

GODOT_ENV_VARS = ("GODOT_BIN", "GODOT4_BIN")
GODOT_ON_PATH = ("godot", "godot4", "Godot_v4.7.2-stable_win64.exe")


class LabError(RuntimeError):
    """The render did not produce what was asked for."""


# --- godot ----------------------------------------------------------------


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


def style_of(axis: str | None = None, value: str | None = None) -> dict:
    style = dict(LOCK)
    if axis:
        style[axis] = value
    return style


def render(godot: str, out_dir: str, shots: tuple[str, ...], style: dict,
           size: tuple[int, int], dump_style: str | None = None) -> None:
    """One build of one scene, photographed through every named lens."""
    os.makedirs(out_dir, exist_ok=True)
    command = [
        godot, "--path", GODOT_PROJECT, RENDER_SCENE, "--",
        f"--out-dir={os.path.abspath(out_dir)}",
        f"--shots={','.join(shots)}",
        f"--width={size[0]}", f"--height={size[1]}",
        f"--layout={LAYOUT}", "--detail=hero",
    ]
    for axis, value in style.items():
        command.append(f"--{axis}={value}")
    if dump_style:
        command.append(f"--dump-style={os.path.abspath(dump_style)}")

    label = " ".join(f"{a}={v}" for a, v in style.items())
    started = time.time()
    result = subprocess.run(command, cwd=REPO, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    elapsed = time.time() - started
    if result.returncode != 0:
        tail = "\n".join((result.stdout or "").splitlines()[-25:])
        errors = "\n".join((result.stderr or "").splitlines()[-25:])
        raise LabError(f"{label}: Godot exited {result.returncode}\n{tail}\n{errors}")
    # GDScript pushes parse and runtime errors to stderr without failing the
    # process, so a zero exit is not on its own proof the scene was built.
    for line in (result.stderr or "").splitlines():
        if "SCRIPT ERROR" in line or "Parse Error" in line:
            raise LabError(f"{label}: {line.strip()}")
    # The scene reports the style it resolved. Comparing it to the style asked
    # for is what stops this tool and `course_style.LOCK` drifting apart - a
    # sheet labelled `pearl` that rendered `base` is worse than no sheet.
    reported = [ln.strip()[7:] for ln in (result.stdout or "").splitlines()
                if ln.strip().startswith("style: ")]
    if reported and reported[0] != label:
        raise LabError(f"asked for [{label}], scene built [{reported[0]}]")
    if not reported and any(v != "base" for v in style.values()):
        raise LabError(f"{label}: the scene reported no style at all")

    missing = [n for n in shots
               if not os.path.isfile(os.path.join(out_dir, f"{n}.png"))]
    if missing:
        raise LabError(f"no image written for {', '.join(missing)}")
    print(f"  [{label}] {', '.join(shots)} {size[0]}x{size[1]}  {elapsed:.1f}s")


# --- sheet furniture ------------------------------------------------------


def _font(size: int, bold: bool = True) -> ImageFont.ImageFont:
    names = (("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf") if bold
             else ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"))
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _panel(image: Image.Image, heading: str, note: str,
           height: int) -> Image.Image:
    """One labelled column: the frame, a heading, and a line of reasoning."""
    scale = height / image.height
    body = image.resize((max(1, int(image.width * scale)), height),
                        Image.LANCZOS)
    bar = 88 if note else 52
    out = Image.new("RGB", (body.width, height + bar), INK)
    out.paste(body, (0, 0))
    draw = ImageDraw.Draw(out)
    draw.text((14, height + 12), heading, font=_font(23), fill=TEXT)
    if note:
        _wrapped(draw, note, 14, height + 44, body.width - 28,
                 _font(19, False), DIM)
    return out


def _wrapped(draw: ImageDraw.ImageDraw, text: str, x: int, y: int, width: int,
             font: ImageFont.ImageFont, fill: tuple) -> int:
    line = ""
    for word in text.split():
        probe = f"{line} {word}".strip()
        if draw.textlength(probe, font=font) > width and line:
            draw.text((x, y), line, font=font, fill=fill)
            y += font.size + 5
            line = word
        else:
            line = probe
    if line:
        draw.text((x, y), line, font=font, fill=fill)
        y += font.size + 5
    return y


def _row(panels: list[Image.Image], gap: int = 16,
         title: str = "", subtitle: str = "") -> Image.Image:
    width = sum(p.width for p in panels) + gap * (len(panels) - 1)
    body = max(p.height for p in panels)
    head = 0 if not title else (110 if subtitle else 68)
    sheet = Image.new("RGB", (width, body + head), INK)
    x = 0
    for panel in panels:
        sheet.paste(panel, (x, head))
        x += panel.width + gap
    if title:
        draw = ImageDraw.Draw(sheet)
        draw.text((16, 18), title, font=_font(38), fill=TEXT)
        if subtitle:
            _wrapped(draw, subtitle, 16, 66, width - 32, _font(21, False), DIM)
    return sheet


def _stack(rows: list[Image.Image], gap: int = 18) -> Image.Image:
    width = max(r.width for r in rows)
    height = sum(r.height for r in rows) + gap * (len(rows) - 1)
    sheet = Image.new("RGB", (width, height), INK)
    y = 0
    for row in rows:
        sheet.paste(row, (0, y))
        y += row.height + gap
    return sheet


# --- commands -------------------------------------------------------------


NOTES = {
    ("track", "base"):
        "Shell #E8E6E0 at key energy 3.2 sits past the ACES shoulder, so "
        "shell, lip and polished floor all resolve to one white. A road.",
    ("track", "pearl"):
        "Shell down to #D8D4CB, running band to #7F8B99, clearcoat on the "
        "cradle cut to 0.45. Three separated values across the section.",
    ("track", "silver"):
        "Shell itself goes cool #C6CED7. Matches the concept's silver "
        "swatch literally; the risk is a track with no warm value in it.",
    ("track", "fascia"):
        "Warm pearl at low gloss over a near-black keel. Best underside "
        "contrast, softest highlight - closest to matte.",
    ("guard", "base"):
        "12% aqua on a 0.26 wall. Below the resolution of every camera on "
        "this course; the aqua rail of the target concept is simply absent.",
    ("guard", "tint"):
        "30% pigment and a 0.44 frosted edge. Holds colour in a still, and "
        "the frosting reads as a bright line rather than as glass.",
    ("guard", "lit"):
        "22% plus a 0.55 self-emission. The rail glows along its length, so "
        "it survives the resize to phone width. Geometry untouched.",
    ("guard", "glass"):
        "40% and almost no rim. Reads as thick cast glass and darkens the "
        "channel it is standing on.",
    ("guard", "cast"):
        "34% pigment, a 0.32 rim and 0.40 self-emission: glass's pigment and "
        "lit's survival at phone width, which no single candidate had both "
        "of. The lock.",
    ("support", "base"):
        "Graphite #2A2E35 with metal caps. Metal reflects an unlit sky, so "
        "every warm accent renders dull olive; the piers are hairlines.",
    ("support", "brass"):
        "Graphite lifted to #333A44, caps moulded brass with a metallic "
        "hint. Warm hardware that keeps its colour in an unlit scene.",
    ("support", "copper"):
        "Deeper graphite, hotter copper. More contrast at the cap and a "
        "warmer read overall; closer to rust than to hardware.",
    ("support", "mono"):
        "Two-tone graphite with a cool cap. The control for 'not too busy' "
        "- and the frame loses its structural warmth with it.",
    ("env", "base"):
        "The amber world rake lands on the near ground, tanning the "
        "mountainside; mauve haze; the cyan rim is unmasked and teals the "
        "scatter; the dusk band hides behind the far range.",
    ("env", "depth"):
        "Near ground on its own light layer, so the distance is warm and "
        "the mountainside stays cool rock. Cool haze, warmer sky horizon, "
        "rim masked to the product.",
    ("env", "valley"):
        "Depth, plus a dusk band raised until it clears the far range, lit "
        "settlement on the near crests, near haze veils, and a darker near "
        "ground for the pearl to be bright against.",
    ("env", "warm"):
        "The counter-proposal: warmth in the ground itself. Cohesive, and "
        "it spends the temperature contrast that was buying the depth.",
    ("finish", "base"):
        "The gold fascia reads; the atmosphere does not. Fog at 0.30 sky "
        "affect turns everything behind the arena into one pale sheet.",
    ("finish", "gold"):
        "Hotter wash, brighter sign face, and a checker separated hard "
        "enough to survive the wash. Warm and legible.",
    ("finish", "contrast"):
        "The same gold with the arena's own shell pushed cool, so warmth "
        "reads by comparison. Cleaner, and less of an occasion.",
}


def axis_sheet(godot: str, axis: str) -> str:
    """One sheet: the axis swept, every other axis held at the lock."""
    spec = AXES[axis]
    shots = tuple(s for s in (spec["shot"], spec.get("second")) if s)
    panels: list[Image.Image] = []
    seconds: list[Image.Image] = []
    for value in spec["options"]:
        out_dir = os.path.join(FRAMES, f"{axis}_{value}")
        render(godot, out_dir, shots, style_of(axis, value), PANEL)
        panels.append(_panel(
            Image.open(os.path.join(out_dir, f"{shots[0]}.png")),
            str(spec["labels"][value]), NOTES.get((axis, value), ""),
            PANEL[1]))
        if len(shots) > 1:
            # A landscape band out of the middle of the second frame, so the
            # lower row is the same total width as the upper one and the four
            # candidates still line up column for column.
            full = Image.open(os.path.join(out_dir, f"{shots[1]}.png"))
            band = full.crop((0, int(full.height * 0.30), full.width,
                              int(full.height * 0.74)))
            seconds.append(_panel(
                band, str(spec["labels"][value]).split("  ")[0], "",
                band.height))

    destination = os.path.join(OUT, str(spec["file"]))
    held = ", ".join(f"{a}={v}" for a, v in LOCK.items() if a != axis)
    subtitle = (f"one axis varied, the other four held at the lock ({held})."
                f"  shot: {' + '.join(shots)}")
    top = _row(panels, 16, str(spec["title"]) + "  —  CANDIDATES",
               subtitle)
    sheet = _stack([top, _row(seconds, 16)]) if seconds else top
    sheet.save(destination)
    print(f"  sheet -> {destination}")
    return destination


def board(godot: str) -> None:
    """The locked style at full resolution, and the sheets that read it."""
    out_dir = os.path.join(FRAMES, "lock")
    render(godot, out_dir, BOARD_SHOTS, style_of(), FULL,
           dump_style=os.path.join(OUT, "material_values.json"))

    panels = [_panel(Image.open(os.path.join(out_dir, f"{shot}.png")),
                     label, "", 1180)
              for shot, label in zip(BOARD_SHOTS, BOARD_LABELS)]
    # Derived, never typed. The first board went out labelled `guard=lit`
    # after the lock had moved to `cast`, which is exactly the kind of wrong
    # caption a reviewer has no way to catch.
    subtitle = ("  ".join(f"{a}={v}" for a, v in LOCK.items())
                + f"  —  layout {LAYOUT.upper()}, {FULL[0]}x{FULL[1]},"
                  " glow on")
    _row(panels, 18, "SLOPED COURSE  —  LOCKED STYLE", subtitle) \
        .save(os.path.join(OUT, "final_style_board.png"))
    print(f"  board -> {os.path.join(OUT, 'final_style_board.png')}")

    hero = os.path.join(out_dir, "hero.png")
    _target_comparison(hero)
    _phone_check(out_dir)


def _target_comparison(hero: str) -> None:
    """The concept's hero column beside ours, at equal height, uncropped.

    The layouts differ on purpose - a course is not a tower - so this sheet is
    about material, light, temperature and finish only.
    """
    concept = Image.open(CONCEPT)
    column = concept.crop((0, 0, int(concept.width * CONCEPT_HERO_FRACTION),
                           concept.height))
    panels = [
        _panel(column, "TARGET CONCEPT", "dark gorge, silver channel, aqua "
               "rails, graphite structure, cyan-violet-orange-gold journey, "
               "warm lights behind.", 1320),
        _panel(Image.open(hero), "LOCKED STYLE", "the same seven traits on a "
               "sloped course: cool upper, violet mid, blue/orange choice, "
               "gold finale, warm settlement in the distance.", 1320),
    ]
    destination = os.path.join(OUT, "target_comparison.png")
    _row(panels, 22, "AGAINST THE TARGET",
         "quality, temperature and finish - not layout").save(destination)
    print(f"  comparison -> {destination}")


def _phone_check(out_dir: str) -> None:
    """Mandatory: the five readability questions, at 390 CSS pixels."""
    checks = [
        ("hero", "WHOLE COURSE  390px", "route legible? environment adding?"),
        ("long_track", "TRACK  390px", "channel / guard / band / racer?"),
        ("split", "SPLIT  390px", "blue against orange?"),
        ("finish", "FINISH  390px", "gold zone unmistakable?"),
    ]
    panels = []
    for shot, heading, note in checks:
        full = Image.open(os.path.join(out_dir, f"{shot}.png"))
        small = full.resize((390, int(390 * full.height / full.width)),
                            Image.LANCZOS)
        panels.append(_panel(small, heading, note, small.height))
    top = _row(panels, 16, "PHONE CHECK  —  390 CSS PIXELS WIDE",
               "rendered at 1080x1920 and resized, so this is what a phone "
               "viewer actually receives")

    # A second row at true 1:1 crops, because a resize hides whether a
    # feature is thin or merely small.
    crops = []
    for shot, heading in (("long_track", "TRACK  1:1 CROP"),
                          ("split", "SPLIT  1:1 CROP"),
                          ("finish", "FINISH  1:1 CROP")):
        full = Image.open(os.path.join(out_dir, f"{shot}.png"))
        box = (int(full.width * 0.12), int(full.height * 0.32),
               int(full.width * 0.88), int(full.height * 0.72))
        crop = full.crop(box)
        crop = crop.resize((520, int(520 * crop.height / crop.width)),
                           Image.LANCZOS)
        crops.append(_panel(crop, heading, "", crop.height))
    destination = os.path.join(OUT, "phone_check.png")
    _stack([top, _row(crops, 16)]).save(destination)
    print(f"  phone -> {destination}")


def palette_sheet() -> None:
    """The swatch document, drawn from the renderer's own dump."""
    source = os.path.join(OUT, "material_values.json")
    if not os.path.isfile(source):
        raise LabError(f"{source} not found - run `board` first")
    data = json.loads(open(source, encoding="utf-8").read())
    groups = data["groups"]

    swatch = 116
    gap = 10
    columns = 5
    rows = (len(groups) + columns - 1) // columns
    col_w = swatch + 200
    head = 128
    step = swatch // 2 + 4

    # Row heights are per row, not one global maximum. With a global one the
    # five-swatch top row is padded out to the seven-swatch bottom row's
    # height and the sheet carries 150 pixels of dead band across its middle.
    row_h = []
    for row in range(rows):
        block = groups[row * columns:(row + 1) * columns]
        row_h.append(44 + max(len(g["swatches"]) for g in block) * step + 26)
    row_y = [head + sum(row_h[:r]) for r in range(rows)]

    width = columns * col_w + (columns + 1) * gap
    height = row_y[-1] + row_h[-1] + 168
    sheet = Image.new("RGB", (width, height), INK)
    draw = ImageDraw.Draw(sheet)
    draw.text((gap + 6, 20), "FINAL PALETTE  —  SLOPED RACE COURSE",
              font=_font(40), fill=TEXT)
    _wrapped(draw, "every value resolved out of the live palette after the "
             "machine was built, so the swatch is the value that rendered. "
             "style: " + "  ".join(f"{a}={v}" for a, v in data["style"].items()),
             gap + 6, 70, width - 2 * gap - 12, _font(21, False), DIM)

    for index, group in enumerate(groups):
        cx = gap + (index % columns) * (col_w + gap)
        cy = row_y[index // columns]
        draw.text((cx + 4, cy), str(group["zone"]), font=_font(24),
                  fill=(150, 214, 246))
        y = cy + 38
        for entry in group["swatches"]:
            box = swatch // 2
            colour = entry["albedo"]
            draw.rectangle([cx + 4, y, cx + 4 + box, y + box - 4],
                           fill=colour, outline=(60, 70, 82))
            if entry.get("emission"):
                draw.rectangle([cx + 4 + box - 13, y + box - 17,
                                cx + 4 + box - 3, y + box - 7],
                               fill=entry["emission"])
            if entry.get("transparent"):
                draw.line([cx + 4, y + box - 4, cx + 4 + box, y],
                          fill=(230, 240, 248), width=2)
            draw.text((cx + box + 16, y + 2), str(entry["name"]),
                      font=_font(19), fill=TEXT)
            detail = colour
            if entry.get("emission"):
                detail += f"  em {entry['emission_energy']:g}"
            elif entry.get("transparent"):
                detail += f"  a{entry['alpha']:.2f}"
            elif entry["metallic"] > 0.02:
                detail += f"  m{entry['metallic']:.2f} r{entry['roughness']:.2f}"
            else:
                detail += f"  r{entry['roughness']:.2f}"
            draw.text((cx + box + 16, y + 25), detail, font=_font(17, False),
                      fill=DIM)
            y += step

    fy = row_y[-1] + row_h[-1] + 8
    draw.text((gap + 6, fy), "THE FIELD  —  EIGHT RACERS",
              font=_font(24), fill=(150, 214, 246))
    for index, colour in enumerate(data["field"]):
        x = gap + 6 + index * 74
        draw.ellipse([x, fy + 40, x + 58, fy + 98], fill=colour,
                     outline=(60, 70, 82))
        draw.text((x, fy + 104), colour, font=_font(15, False), fill=DIM)
    _wrapped(draw, "swatch corner = emission colour;  diagonal = transparent;"
             "  em = emission energy, a = alpha, m = metallic, r = roughness",
             gap + 6, fy + 128, width - 2 * gap - 12, _font(18, False), DIM)

    destination = os.path.join(OUT, "final_palette.png")
    sheet.save(destination)
    print(f"  palette -> {destination}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("axis", "candidates", "board",
                                            "palette", "one", "all"))
    parser.add_argument("target", nargs="?", help="axis name, for `axis`")
    parser.add_argument("--godot")
    parser.add_argument("--shot", default="hero")
    parser.add_argument("--set", action="append", default=[],
                        help="axis=value, for `one`")
    options = parser.parse_args(argv)
    os.makedirs(OUT, exist_ok=True)

    if options.command == "palette":
        palette_sheet()
        return 0

    godot = find_godot(options.godot)

    if options.command == "one":
        style = dict(LOCK)
        for pair in options.set:
            axis, _, value = pair.partition("=")
            style[axis] = value
        render(godot, os.path.join(FRAMES, "one"), (options.shot,), style,
               PANEL)
        return 0

    if options.command == "axis":
        if options.target not in AXES:
            raise LabError(f"axis must be one of {', '.join(AXES)}")
        axis_sheet(godot, options.target)
        return 0

    if options.command in ("candidates", "all"):
        print("candidate sheets:")
        for axis in AXES:
            axis_sheet(godot, axis)

    if options.command in ("board", "all"):
        print("locked style:")
        board(godot)
        palette_sheet()

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except LabError as error:
        print(f"style_lab: {error}", file=sys.stderr)
        sys.exit(1)

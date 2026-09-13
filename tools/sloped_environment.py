"""Drive the environment profile system: inspect it, check it, photograph it.

The framework itself is ``sloped/environment.py`` (Python reader),
``godot/assets/marble_machine/environment/`` (GDScript reader and builder) and
``.../environment/profiles/*.json`` (the profiles). This is the driver.

    python tools/sloped_environment.py list                 # the registry
    python tools/sloped_environment.py check                # validate all
    python tools/sloped_environment.py show canyon_dusk     # one resolved
    python tools/sloped_environment.py diff alpine_neon glow_valley
    python tools/sloped_environment.py sheet                # the proof sheet
    python tools/sloped_environment.py measure              # world vs machine
    python tools/sloped_environment.py neutral              # identity proof

``list``, ``check``, ``show`` and ``diff`` never launch Godot and are the ones
worth running in a loop while authoring a theme. ``sheet`` and ``neutral`` do.

Finding Godot, in order: ``--godot``, then ``$GODOT_BIN`` or ``$GODOT4_BIN``,
then the PATH. Same rule as every other render tool here.
"""

from __future__ import annotations

import argparse
import filecmp
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from sloped import environment as env  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GODOT_PROJECT = os.path.join(REPO, "godot")
RENDER_SCENE = "scenes/CourseRender.tscn"

OUT_DOCS = os.path.join(REPO, "docs", "validation", "sloped_race_v1",
                        "v23_environment")

GODOT_ENV_VARS = ("GODOT_BIN", "GODOT4_BIN")
GODOT_ON_PATH = ("godot", "godot4", "Godot_v4.7.2-stable_win64.exe")

#: The proof sheet's columns. One wide section, one mid section and one close
#: module, because a theme that only reads at one scale is not a theme - the
#: haze carries the first, the ground materials the second and the practicals
#: the third.
SHEET_SHOTS = ("long_track", "split", "finish")

#: The pass the race ships under. The sheet is rendered under it so the
#: comparison is against the picture that is actually delivered, not against
#: the lab look nothing has shipped since V20.
SHEET_CONTRAST = "v21"

SHEET_WIDTH = 460
SHEET_HEIGHT = 818
LAYOUT = "b"


class LabError(RuntimeError):
    """The render did not produce what was asked for."""


def find_godot(explicit: str | None) -> str:
    if explicit:
        return explicit
    for name in GODOT_ENV_VARS:
        value = os.environ.get(name)
        if value and os.path.isfile(value):
            return value
    for name in GODOT_ON_PATH:
        found = shutil.which(name)
        if found:
            return found
    raise LabError(
        "Godot not found: pass --godot, or set $GODOT_BIN to the binary"
    )


def render(godot: str, out_dir: str, profile_id: str, shots: tuple[str, ...],
           contrast: str = SHEET_CONTRAST, width: int = SHEET_WIDTH,
           height: int = SHEET_HEIGHT, project: str = GODOT_PROJECT,
           layers: str = "") -> None:
    os.makedirs(out_dir, exist_ok=True)
    command = [
        godot, "--path", project, RENDER_SCENE, "--",
        f"--out-dir={os.path.abspath(out_dir)}",
        f"--shots={','.join(shots)}",
        f"--width={width}", f"--height={height}",
        f"--layout={LAYOUT}", "--detail=hero",
        f"--contrast={contrast}",
    ]
    if profile_id:
        command.append(f"--environment={profile_id}")
    if layers:
        command.append(f"--layers={layers}")
    result = subprocess.run(command, cwd=REPO, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    label = profile_id or "(default)"
    if result.returncode != 0:
        tail = "\n".join((result.stdout or "").splitlines()[-20:])
        raise LabError(f"{label}: Godot exited {result.returncode}\n{tail}")
    # GDScript pushes parse and runtime errors to stderr without failing the
    # process, so a zero exit is not on its own proof the scene was built.
    for line in (result.stderr or "").splitlines():
        if "SCRIPT ERROR" in line or "Parse Error" in line:
            raise LabError(f"{label}: {line.strip()}")
    for line in (result.stdout or "").splitlines():
        if line.startswith("environment "):
            print(f"    {line.strip()}")
    missing = [n for n in shots
               if not os.path.isfile(os.path.join(out_dir, f"{n}.png"))]
    if missing:
        raise LabError(f"{label}: no image for {', '.join(missing)}")


# --- sheets ---------------------------------------------------------------


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _caption(width: int, title: str, body: str, height: int = 78) -> Image.Image:
    panel = Image.new("RGB", (width, height), (14, 16, 20))
    draw = ImageDraw.Draw(panel)
    draw.text((14, 12), title, font=_font(26), fill=(238, 242, 248))
    draw.text((14, 46), body, font=_font(17), fill=(150, 162, 178))
    return panel


def sheet(godot: str, destination: str, profile_ids: list[str]) -> None:
    """One row per profile, one column per shot, rendered fresh.

    The only claim a framework like this can make that is worth anything is
    that the *same* course, seed and camera come out differently - so every
    panel is layout B under the shipped contrast pass, and the only thing that
    changes between rows is ``--environment``.
    """
    work = tempfile.mkdtemp(prefix="env_sheet_")
    try:
        rows: list[Image.Image] = []
        for profile_id in profile_ids:
            print(f"  {profile_id}")
            out = os.path.join(work, profile_id)
            render(godot, out, profile_id, SHEET_SHOTS)
            profile = env.resolve(profile_id, SHEET_CONTRAST)
            panels = [Image.open(os.path.join(out, f"{name}.png")).convert("RGB")
                      for name in SHEET_SHOTS]
            band = Image.new(
                "RGB",
                (sum(p.width for p in panels) + 12 * (len(panels) - 1),
                 panels[0].height),
                (10, 12, 15),
            )
            cursor = 0
            for panel in panels:
                band.paste(panel, (cursor, 0))
                cursor += panel.width + 12
            caption = _caption(band.width, profile["title"], env.describe(profile))
            row = Image.new("RGB", (band.width, band.height + caption.height),
                            (10, 12, 15))
            row.paste(caption, (0, 0))
            row.paste(band, (0, caption.height))
            rows.append(row)

        gap = 22
        sheet_image = Image.new(
            "RGB",
            (rows[0].width + 2 * gap,
             sum(r.height for r in rows) + gap * (len(rows) + 1) + 46),
            (10, 12, 15),
        )
        draw = ImageDraw.Draw(sheet_image)
        draw.text(
            (gap, 16),
            "one course, one seed, one camera - %s, layout %s, contrast %s"
            % (", ".join(SHEET_SHOTS), LAYOUT, SHEET_CONTRAST),
            font=_font(20), fill=(150, 162, 178),
        )
        cursor = 46 + gap
        for row in rows:
            sheet_image.paste(row, (gap, cursor))
            cursor += row.height + gap
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        sheet_image.save(destination)
        print(f"  wrote {os.path.relpath(destination, REPO)}")
    finally:
        shutil.rmtree(work, ignore_errors=True)


def neutral(godot: str, reference: str) -> int:
    """Prove the default profile renders what the old constants rendered.

    ``reference`` is a checkout of the commit this branch left from. Both
    trees render the same four sections under both contrast passes and the
    files are compared byte for byte, which is the same property the style
    lock proved for the additive style system and the reason that system could
    be trusted afterwards.
    """
    if not os.path.isdir(os.path.join(reference, "godot")):
        raise LabError(f"{reference} is not a checkout of this project")
    work = tempfile.mkdtemp(prefix="env_neutral_")
    shots = ("start", "long_track", "split", "finish")
    failures = 0
    try:
        for contrast in ("", "v21"):
            tag = contrast or "v20"
            before = os.path.join(work, f"before_{tag}")
            after = os.path.join(work, f"after_{tag}")
            render(godot, before, "", shots, contrast,
                   project=os.path.join(reference, "godot"))
            render(godot, after, "", shots, contrast)
            for name in shots:
                same = filecmp.cmp(os.path.join(before, f"{name}.png"),
                                   os.path.join(after, f"{name}.png"),
                                   shallow=False)
                print("  %-9s %-11s %s" % (tag, name,
                                           "identical" if same else "DIFFERS"))
                failures += 0 if same else 1
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return failures


def measure(godot: str, profile_ids: list[str]) -> None:
    """Photograph each profile three ways and report the two populations.

    "Dark background, bright machine" is a claim about two sets of pixels, and
    the scene has been able to separate them since the two-key rig was built -
    the product is on visual layer 1 and everything this framework makes is on
    layer 2. ``--layers`` points the camera at one of them, and at neither:

        machine   layer 1: the course, the modules, the racers
        world     layer 2: the terrain, the dressing, the ranges, the band
        sky       no layer at all: the sky, the haze and the grade

    The sky frame is what makes the other two honest. Both of them render the
    background as well, so a pixel that matches the sky frame belongs to
    neither population and is dropped - without that step the sky is counted
    as part of whichever half happens to be in front of it, and a profile with
    a bright sky reads as a profile with a bright mountain.

    Four numbers per profile, averaged over the sheet's shots:

        world L     mean CIELAB lightness where the environment covers
        machine L   mean lightness where the course covers
        headroom    machine minus world: the separation the goal asks for
        flat        share of the finished frame that has stopped shading

    ``flat`` is the V21 pass's own measure, from
    ``tools/sloped_contrast_measure.py`` - a theme is judged by the instrument
    the film was graded with, not by a new one invented to flatter it.
    """
    import importlib.util

    import numpy as np

    spec = importlib.util.spec_from_file_location(
        "sloped_contrast_measure",
        os.path.join(REPO, "tools", "sloped_contrast_measure.py"))
    contrast_measure = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(contrast_measure)

    def _lightness(path: str) -> np.ndarray:
        pixels = np.asarray(Image.open(path).convert("RGB"))
        return contrast_measure._lab(pixels)[..., 0], pixels

    work = tempfile.mkdtemp(prefix="env_measure_")
    try:
        print("  %-18s %8s %10s %9s %7s"
              % ("profile", "world L", "machine L", "headroom", "flat %"))
        for profile_id in profile_ids:
            cuts = {}
            for which in ("", "machine", "world", "sky"):
                out = os.path.join(work, profile_id, which or "full")
                render(godot, out, profile_id, SHEET_SHOTS, layers=which)
                cuts[which or "full"] = out
            rows = []
            for name in SHEET_SHOTS:
                sky_l, sky_rgb = _lightness(
                    os.path.join(cuts["sky"], f"{name}.png"))
                world_l, world_rgb = _lightness(
                    os.path.join(cuts["world"], f"{name}.png"))
                machine_l, machine_rgb = _lightness(
                    os.path.join(cuts["machine"], f"{name}.png"))
                # A tolerance rather than equality: the sky is the same
                # render every time, but the two passes reach it through
                # different depth buffers and the fog resolves a shade apart.
                world_mask = np.abs(world_rgb.astype(int)
                                    - sky_rgb.astype(int)).max(-1) > 3
                machine_mask = np.abs(machine_rgb.astype(int)
                                      - sky_rgb.astype(int)).max(-1) > 3
                report = contrast_measure.frame_report(
                    Image.open(os.path.join(cuts["full"], f"{name}.png")))
                rows.append((
                    float(world_l[world_mask].mean()) if world_mask.any() else 0.0,
                    float(machine_l[machine_mask].mean())
                    if machine_mask.any() else 0.0,
                    report["flat_white"],
                ))
            world_mean = sum(r[0] for r in rows) / len(rows)
            machine_mean = sum(r[1] for r in rows) / len(rows)
            flat = sum(r[2] for r in rows) / len(rows)
            print("  %-18s %8.1f %10.1f %9.1f %7.2f"
                  % (profile_id, world_mean, machine_mean,
                     machine_mean - world_mean, flat))
    finally:
        shutil.rmtree(work, ignore_errors=True)


# --- inspection -----------------------------------------------------------


def show(profile_id: str, contrast: str) -> None:
    profile = env.resolve(profile_id, contrast)
    print(env.describe(profile))
    print(f"  id       {profile['id']}")
    print(f"  extends  {profile.get('extends') or '-'}")
    print(f"  contrast {contrast or '-'}")
    print(f"  {profile['summary']}")
    print()
    for path, value in sorted(env.flatten(profile).items()):
        print(f"  {path:52s} {value}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",
                        choices=["list", "check", "show", "diff", "sheet",
                                 "measure", "neutral"])
    parser.add_argument("names", nargs="*", help="profile ids")
    parser.add_argument("--contrast", default=SHEET_CONTRAST,
                        help="contrast pass to resolve under ('' for none)")
    parser.add_argument("--godot", help="path to the Godot 4 binary")
    parser.add_argument("--reference",
                        help="a checkout of the base commit, for 'neutral'")
    parser.add_argument("-o", "--out", default=os.path.join(
        OUT_DOCS, "profile_sheet.png"))
    args = parser.parse_args(argv)

    if args.command == "list":
        print(f"default: {env.default_id()}")
        for name in env.ids():
            profile = env.resolve(name, args.contrast)
            print(f"  {name:18s} {env.describe(profile)}")
            print(f"  {'':18s} extends {profile.get('extends') or '-'}")
        return 0

    if args.command == "check":
        failures = 0
        for name in env.ids():
            for contrast in ("", "v21"):
                problems = env.validate(env.resolve(name, contrast))
                # `validate` is run on the resolved profile because that is
                # what the scene builds from: a delta that is legal on its own
                # can still merge into something that is not.
                for problem in problems:
                    print(f"  {name} [{contrast or 'none'}]: {problem}")
                failures += len(problems)
            # The id inside the file has to match the file it is in, or
            # `--environment=x` selects one profile and the scene reports
            # another.
            raw = env.load(name)
            if raw.get("id") != name:
                print(f"  {name}: id field says {raw.get('id')!r}")
                failures += 1
        print("  %d profiles, %d complaints" % (len(env.ids()), failures))
        return 1 if failures else 0

    if args.command == "show":
        if not args.names:
            parser.error("show needs a profile id")
        show(args.names[0], args.contrast)
        return 0

    if args.command == "diff":
        if len(args.names) != 2:
            parser.error("diff needs two profile ids")
        left, right = args.names
        changes = env.diff(env.resolve(left, args.contrast),
                           env.resolve(right, args.contrast))
        print(f"{left} -> {right}: {len(changes)} fields")
        for path, before, after in changes:
            print(f"  {path:46s} {before}  ->  {after}")
        return 0

    godot = find_godot(args.godot)
    if args.command == "sheet":
        names = args.names or env.ids()
        sheet(godot, args.out, names)
        return 0

    if args.command == "measure":
        measure(godot, args.names or env.ids())
        return 0

    if args.command == "neutral":
        if not args.reference:
            parser.error("neutral needs --reference=PATH")
        return 1 if neutral(godot, args.reference) else 0
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except LabError as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(2)

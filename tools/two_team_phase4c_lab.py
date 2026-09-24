"""The Phase 4C laboratory: pick the final framing from rendered frames.

Phase 4B chose 0.850 by fitting the whole arena inside the frame. The human
review rejected the result for the third time - the race is still too small,
there is still too much empty dark space - and the 4C brief replaces the rule
outright: *keep the interesting action large, even if parts of the arena are
cropped*. The frame fraction is therefore allowed above 1.0, where the framed
wall is wider than the frame and its left and right caps are off screen.

``framing``
    Render one seed's event-centred stills at the brief's three candidate
    final-structure widths - 100%, 110% and 120% of the frame - and measure
    each frame. Writes one comparison row per variant plus a side-by-side
    contact sheet per moment, at render resolution, because composition is
    judged at the size it will be seen.

``occupancy``
    Measure ink from rendered frames rather than from the model, at the
    selected fraction, across the run. The review's complaint is that the late
    frame is emptier than the early one, so the thirds are the measurement and
    a single mean is not.

Neither command decides anything. They produce the numbers and the sheets a
person looks at before the framing is locked.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from satisfying import multishell_visual as visual  # noqa: E402
from satisfying import multishell_visual_cli as visual_cli  # noqa: E402
from satisfying.multishell_playback import document_for  # noqa: E402

#: The brief's three, plus the Phase 4B framing as the "what we had" control.
#: A is 1.00, B is 1.10, C is 1.20; cropping is expected at B and C and is not
#: on its own a reason to reject either.
VARIANTS: tuple[tuple[str, float], ...] = (
    ("4B", 0.850), ("A", 1.000), ("B", 1.100), ("C", 1.200),
)
#: Anything at or below this in linear luminance is empty dark space. The
#: background is (0.020, 0.026, 0.042) and the floor glow reaches about 0.10,
#: so 0.14 counts the arena and the balls and not the pool they sit in.
INK_LUMINANCE = 0.14
#: And this is material and balls only.
SOLID_LUMINANCE = 0.30
#: A bright pixel this unsaturated is white rather than cyan or orange. The
#: brief's "reduce bloom if clusters become white" is otherwise an eye call,
#: and an eye call cannot compare three renders fairly.
WHITE_SATURATION = 0.22


class LabError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def _render_stills(
    godot: str, out_dir: Path, playback: Path, moments: Path,
    fraction: float, width: int, height: int,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    visual_cli.run_godot(
        godot,
        [
            f"--playback={visual_cli.godot_path(str(playback))}",
            f"--out-dir={visual_cli.godot_path(str(out_dir))}",
            f"--moments={visual_cli.godot_path(str(moments))}",
            "--stills=1",
            f"--frontier-width={fraction:g}",
            f"--width={width}",
            f"--height={height}",
            f"--release={visual.RELEASE_SECONDS}",
            f"--hold={visual.END_HOLD_SECONDS}",
        ],
        f"framing at {fraction:g}",
    )


# --------------------------------------------------------------------------
# Measurement from pixels
# --------------------------------------------------------------------------


def measure_frame(path: Path) -> dict[str, Any]:
    """Ink, emptiness, the worst empty band and how white the bright part is."""
    from PIL import Image
    import numpy

    with Image.open(path) as handle:
        rgb = numpy.asarray(handle.convert("RGB"), dtype=numpy.float32) / 255.0
    luma = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
    ink = luma > INK_LUMINANCE
    height, width = ink.shape
    rows = ink.any(axis=1)
    worst = run = 0
    for value in rows:
        run = 0 if value else run + 1
        worst = max(worst, run)
    solid = luma > SOLID_LUMINANCE
    high = rgb.max(axis=2)
    low = rgb.min(axis=2)
    saturation = numpy.where(
        high > 0.0, (high - low) / numpy.maximum(high, 1e-6), 0.0)
    white = solid & (saturation < WHITE_SATURATION)
    return {
        "ink_fraction": float(ink.mean()),
        "solid_fraction": float(solid.mean()),
        "mean_luma": float(luma.mean()),
        "empty_band_px": int(worst),
        "empty_band_fraction": worst / float(height),
        "white_share_of_bright": (
            float(white.sum()) / float(solid.sum()) if solid.any() else 0.0
        ),
        "mean_saturation_of_bright": (
            float(saturation[solid].mean()) if solid.any() else 0.0
        ),
    }


# --------------------------------------------------------------------------
# Sheets
# --------------------------------------------------------------------------


def _side_by_side(paths: Sequence[Path], target: Path,
                  labels: Sequence[str]) -> None:
    from PIL import Image, ImageDraw

    images = [Image.open(path).convert("RGB") for path in paths]
    scale = 460.0 / images[0].width
    tiles = [
        image.resize((int(image.width * scale), int(image.height * scale)))
        for image in images
    ]
    pad = 12
    sheet = Image.new(
        "RGB",
        (sum(tile.width for tile in tiles) + pad * (len(tiles) + 1),
         tiles[0].height + pad * 2 + 30),
        (10, 12, 18),
    )
    draw = ImageDraw.Draw(sheet)
    x = pad
    for tile, label in zip(tiles, labels):
        sheet.paste(tile, (x, pad + 30))
        draw.text((x + 6, pad + 6), label, fill=(226, 234, 248))
        x += tile.width + pad
    target.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(target)
    for image in images:
        image.close()


def _set_fraction(fraction: float) -> None:
    """Re-point the module's derived framing constants. Laboratory only."""
    visual.FRONTIER_WIDTH_FRACTION = fraction
    visual.VIEW_DIAMETER_FRACTION = fraction * (1.0 + visual.VIEW_PAD_FRACTION)
    visual._STAGE_CACHE.clear()


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


def cmd_framing(args: argparse.Namespace) -> int:
    godot = visual_cli.find_godot(args.godot)
    visual_cli.check_scripts(godot)
    out = Path(args.out)
    seed = args.seed
    document = document_for(seed)
    reason = visual.validate_document(document)
    if reason:
        raise LabError(f"seed {seed}: {reason}")

    playback = out / "playback" / f"seed{seed}.json"
    playback.parent.mkdir(parents=True, exist_ok=True)
    visual_cli.write_playback(document, str(playback))
    moments_list = visual.event_moments(document)
    moments = out / "playback" / f"seed{seed}_moments.json"
    with open(moments, "w", encoding="utf-8") as handle:
        json.dump(moments_list, handle, indent=1)

    variants = [(name, value) for name, value in VARIANTS
                if not args.only or name in args.only]
    rows: list[dict[str, Any]] = []
    for name, fraction in variants:
        frames = out / "framing" / f"seed{seed}" / name
        if frames.is_dir():
            shutil.rmtree(frames)
        _render_stills(godot, frames, playback, moments, fraction,
                       args.width, args.height)
        stills = sorted(frames.glob("*.png"))
        if not stills:
            raise LabError(f"no stills rendered for variant {name}")
        measured = [dict(measure_frame(path), file=path.name) for path in stills]
        saved = visual.FRONTIER_WIDTH_FRACTION
        try:
            _set_fraction(fraction)
            sizes = visual.frame_size_report(document)
            critical = visual.critical_visibility_report(document)
            occupancy = visual.occupancy_report(document)
            contained = visual.containment_report(document)
        finally:
            _set_fraction(saved)
        third = max(1, len(measured) // 3)
        rows.append({
            "variant": name,
            "fraction": fraction,
            "frames": len(stills),
            "measured": measured,
            "measured_mean_ink": sum(m["ink_fraction"] for m in measured)
            / len(measured),
            "measured_early_ink": sum(
                m["ink_fraction"] for m in measured[:third]) / third,
            "measured_late_ink": sum(
                m["ink_fraction"] for m in measured[-third:]) / third,
            "measured_worst_empty_band": max(
                m["empty_band_px"] for m in measured),
            "measured_white_share": max(
                m["white_share_of_bright"] for m in measured),
            "derived_ink_thirds": {
                key: value["ink_fraction"]
                for key, value in occupancy["thirds"].items()
            },
            "opening_stage": sizes[0],
            "final_stage": sizes[-1],
            "critical_hidden": len(critical["hidden"]),
            "critical_pass": critical["critical_pass"],
            "hard_on_frame": critical["hard_on_frame"],
            "worst_hard_off_frame": critical["worst_hard_off_frame"],
            "contained": contained["contained"],
            "ball_frames_off_frame": contained["outside_frames"],
            "frames_measured": contained["frames"],
        })

    names = [entry["name"] for entry in moments_list]
    for index, moment in enumerate(names):
        tiles: list[Path] = []
        labels: list[str] = []
        for name, fraction in variants:
            stills = sorted(
                (out / "framing" / f"seed{seed}" / name).glob("*.png"))
            if index < len(stills):
                tiles.append(stills[index])
                labels.append(f"{name}  {fraction:g}")
        if tiles:
            _side_by_side(
                tiles,
                out / "framing" / f"seed{seed}" / "sheets" / f"{moment}.png",
                labels)

    report = {
        "format": 1,
        "seed": seed,
        "render_config_digest": visual.render_config_digest(),
        "ink_luminance": INK_LUMINANCE,
        "solid_luminance": SOLID_LUMINANCE,
        "white_saturation": WHITE_SATURATION,
        "moments": names,
        "rows": rows,
    }
    target = out / "framing" / f"seed{seed}" / "framing.json"
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")

    print(f"{'var':>4}{'frac':>7}{'ink':>8}{'early':>8}{'late':>8}{'band':>7}"
          f"{'white':>7}{'ball':>7}{'open':>7}{'wall':>7}{'hid':>5}"
          f"{'hard':>6}{'offF':>6}")
    for row in rows:
        stage = row["final_stage"]
        print(f"{row['variant']:>4}{row['fraction']:>7.3f}"
              f"{row['measured_mean_ink']:>8.3f}"
              f"{row['measured_early_ink']:>8.3f}"
              f"{row['measured_late_ink']:>8.3f}"
              f"{row['measured_worst_empty_band']:>7d}"
              f"{row['measured_white_share']:>7.3f}"
              f"{stage['ball_drawn_diameter_px']:>7.1f}"
              f"{stage['opening_width_px']:>7.1f}"
              f"{stage['wall_apparent_thickness_px']:>7.1f}"
              f"{row['critical_hidden']:>5d}"
              f"{'ok' if row['critical_pass'] else 'FAIL':>6}"
              f"{row['ball_frames_off_frame']:>6d}")
    print(f"  -> {target}")
    return 0


def cmd_measurements(args: argparse.Namespace) -> int:
    """Every derived report for the production candidates, plus the decision.

    The framing table is recomputed here from the module rather than copied
    from the render log, so the document and the code cannot drift: if a
    constant moves, this file moves with it and the phase document's table is
    wrong in a way somebody notices.
    """
    rows: dict[str, Any] = {}
    saved = visual.FRONTIER_WIDTH_FRACTION
    try:
        for seed in args.seeds:
            document = document_for(seed)
            per_variant = {}
            for name, fraction in VARIANTS:
                _set_fraction(fraction)
                per_variant[name] = {
                    "fraction": fraction,
                    "frame_size": visual.frame_size_report(document),
                    "critical_visibility": visual.critical_visibility_report(
                        document),
                    "containment": visual.containment_report(document, fps=60.0),
                    "occupancy": visual.occupancy_report(document),
                }
            _set_fraction(saved)
            rows[str(seed)] = {
                "seed": seed,
                "summary": document["summary"],
                "camera_stages": [
                    {key: (list(value) if isinstance(value, tuple) else value)
                     for key, value in stage.items()
                     if key != "guard_conflicts"}
                    for stage in visual.camera_stages(document)
                ],
                "camera_lock_time": visual.camera_lock_time(document),
                "static_tail_seconds": visual.static_tail_seconds(document),
                "zoom_ratio": visual.zoom_ratio(document),
                "centring": visual.centring_report(document),
                "safe_area": visual.safe_area_report(document),
                "readability": visual.readability_report(document),
                "damage": visual.damage_report(document),
                "wear": visual.wear_report(document),
                "winner_banner": visual.winner_banner_placement(document),
                "passages": visual.passage_responses(document),
                "by_variant": per_variant,
            }
    finally:
        _set_fraction(saved)
    payload = {
        "kind": "category3_two_team_shell_race_phase4c_measurements",
        "render_config_digest": visual.render_config_digest(),
        "frame_fraction": visual.FRONTIER_WIDTH_FRACTION,
        "camera_stage_plan": [list(entry) for entry in visual.CAMERA_STAGE_PLAN],
        "frame_ease_seconds": visual.FRAME_EASE_SECONDS,
        "seeds": rows,
    }
    target = Path(args.validation) / "phase4c_measurements.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1, default=float)
        handle.write("\n")
    print(f"  {len(rows)} candidates -> {target}")
    return 0


def cmd_sequence(args: argparse.Namespace) -> int:
    """A strip of stills across one named beat, at the selected framing.

    The eleven event-centred moments are one frame each and a break is a
    *sequence* - the network flares, the slab parts, the chunks leave, a hole
    is left, a ball goes through it. The brief's destruction gate is a claim
    about that ordering, so it has to be looked at as an ordering, and the
    eleven-still set cannot show one.
    """
    godot = visual_cli.find_godot(args.godot)
    visual_cli.check_scripts(godot)
    out = Path(args.out)
    seed = args.seed
    document = document_for(seed)
    reason = visual.validate_document(document)
    if reason:
        raise LabError(f"seed {seed}: {reason}")
    playback = out / "playback" / f"seed{seed}.json"
    playback.parent.mkdir(parents=True, exist_ok=True)
    visual_cli.write_playback(document, str(playback))

    times = sorted(float(value) for value in args.times)
    moments = [{"name": f"t{index:02d}_{value:.3f}".replace(".", "p"),
                "t": value} for index, value in enumerate(times)]
    moments_path = out / "playback" / f"seed{seed}_{args.name}_moments.json"
    with open(moments_path, "w", encoding="utf-8") as handle:
        json.dump(moments, handle, indent=1)

    fraction = dict(VARIANTS)[args.variant]
    frames = out / "sequence" / f"seed{seed}" / args.name
    if frames.is_dir():
        shutil.rmtree(frames)
    _render_stills(godot, frames, playback, moments_path, fraction,
                   args.width, args.height)
    stills = sorted(frames.glob("*.png"))
    if not stills:
        raise LabError("no stills rendered")
    if args.crop:
        left, top, right, bottom = args.crop
        from PIL import Image
        cropped: list[Path] = []
        for path in stills:
            with Image.open(path) as handle:
                tile = handle.crop((left, top, right, bottom))
                target = path.with_name(f"crop_{path.name}")
                tile.save(target)
            cropped.append(target)
        stills = cropped
    _side_by_side(stills, out / "sequence" / f"seed{seed}" / f"{args.name}.png",
                  [f"{value:.2f}s" for value in times])
    print(f"  {len(stills)} frames -> "
          f"{out / 'sequence' / f'seed{seed}' / f'{args.name}.png'}")
    return 0


def cmd_occupancy(args: argparse.Namespace) -> int:
    """Measured pixels against the model, on **uniformly spaced** frames.

    The framing sweep measures the eleven event-centred stills, which is the
    right set for judging composition and the wrong one for judging emptiness:
    they are clustered where things happen, and three of them sit inside the
    last second. The review's complaint - "too much empty dark space remains
    late in the video" - is a claim about thirds of the *run*, so the sample
    has to be uniform in time, and it is rendered here rather than reused.
    """
    godot = visual_cli.find_godot(args.godot)
    visual_cli.check_scripts(godot)
    out = Path(args.out)
    fraction = dict(VARIANTS)[args.variant]
    payload: dict[str, Any] = {
        "format": 2, "variant": args.variant, "fraction": fraction,
        "samples": args.samples, "seeds": {},
    }
    for seed in args.seeds:
        document = document_for(seed)
        duration = float(document["summary"]["duration"])
        playback = out / "playback" / f"seed{seed}.json"
        playback.parent.mkdir(parents=True, exist_ok=True)
        visual_cli.write_playback(document, str(playback))
        times = [duration * index / (args.samples - 1)
                 for index in range(args.samples)]
        moments = [{"name": f"u{index:03d}", "t": value}
                   for index, value in enumerate(times)]
        moments_path = out / "playback" / f"seed{seed}_uniform_moments.json"
        with open(moments_path, "w", encoding="utf-8") as handle:
            json.dump(moments, handle, indent=1)
        frames = out / "occupancy" / f"seed{seed}" / args.variant
        if frames.is_dir():
            shutil.rmtree(frames)
        _render_stills(godot, frames, playback, moments_path, fraction,
                       args.width, args.height)
        stills = sorted(frames.glob("*.png"))
        rows: list[dict[str, Any]] = []
        for moment, path in zip(moments, stills):
            measured = measure_frame(path)
            modelled = visual.occupancy_at(document, float(moment["t"]))
            rows.append({
                "t": float(moment["t"]),
                "measured_ink": measured["ink_fraction"],
                "measured_solid": measured["solid_fraction"],
                "modelled_ink": modelled["ink_fraction"],
                "difference": measured["ink_fraction"] - modelled["ink_fraction"],
                "empty_band_px": measured["empty_band_px"],
                "white_share_of_bright": measured["white_share_of_bright"],
            })
        third = max(1, len(rows) // 3)
        bands = {
            "early": rows[:third],
            "middle": rows[third:2 * third],
            "late": rows[-third:],
        }
        summary = {
            name: {
                "measured_ink": sum(r["measured_ink"] for r in band) / len(band),
                "measured_solid": sum(r["measured_solid"] for r in band) / len(band),
                "modelled_ink": sum(r["modelled_ink"] for r in band) / len(band),
                "worst_empty_band_px": max(r["empty_band_px"] for r in band),
            }
            for name, band in bands.items()
        }
        summary["late_not_emptier_than_middle"] = (
            summary["late"]["measured_ink"] >= summary["middle"]["measured_ink"])
        summary["late_over_early"] = (
            summary["late"]["measured_ink"] / summary["early"]["measured_ink"])
        payload["seeds"][str(seed)] = {"rows": rows, "thirds": summary}
        print(f"seed {seed}")
        for name in ("early", "middle", "late"):
            row = summary[name]
            print(f"  {name:>7}  ink {row['measured_ink']:.3f}  "
                  f"solid {row['measured_solid']:.3f}  "
                  f"model {row['modelled_ink']:.3f}  "
                  f"worst empty band {row['worst_empty_band_px']:>4d} px")
        print(f"  late/early {summary['late_over_early']:.3f}  "
              f"late >= middle {summary['late_not_emptier_than_middle']}")
    target = Path(args.validation) / "occupancy_crosscheck.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1)
        handle.write("\n")
    print(f"  -> {target}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="two_team_phase4c_lab", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=os.path.join("output", "phase4c"))
    parser.add_argument("--godot", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    framing = sub.add_parser("framing", help="the 100/110/120 comparison")
    framing.add_argument("--seed", type=int, default=17964)
    framing.add_argument("--only", nargs="*", default=None,
                         help="variant names to render, default all")
    framing.add_argument("--width", type=int, default=1080)
    framing.add_argument("--height", type=int, default=1920)
    framing.set_defaults(func=cmd_framing)

    measurements = sub.add_parser(
        "measurements", help="every derived report for the candidates")
    measurements.add_argument("--seeds", type=int, nargs="+",
                              default=[17964, 1176])
    measurements.add_argument(
        "--validation",
        default=os.path.join("docs", "validation",
                             "category3_two_team_shell_race_v4c"))
    measurements.set_defaults(func=cmd_measurements)

    sequence = sub.add_parser("sequence", help="a strip across one beat")
    sequence.add_argument("--seed", type=int, default=1176)
    sequence.add_argument("--name", default="final_break")
    sequence.add_argument("--variant", default="C")
    sequence.add_argument("--times", type=float, nargs="+", required=True)
    sequence.add_argument("--crop", type=int, nargs=4, default=None,
                          metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"))
    sequence.add_argument("--width", type=int, default=1080)
    sequence.add_argument("--height", type=int, default=1920)
    sequence.set_defaults(func=cmd_sequence)

    occupancy = sub.add_parser("occupancy", help="pixels against the model")
    occupancy.add_argument("--seeds", type=int, nargs="+", default=[17964, 1176])
    occupancy.add_argument("--variant", default="C")
    occupancy.add_argument("--samples", type=int, default=25)
    occupancy.add_argument("--width", type=int, default=1080)
    occupancy.add_argument("--height", type=int, default=1920)
    occupancy.add_argument(
        "--validation",
        default=os.path.join("docs", "validation",
                             "category3_two_team_shell_race_v4c"))
    occupancy.set_defaults(func=cmd_occupancy)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (LabError, visual_cli.VisualError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

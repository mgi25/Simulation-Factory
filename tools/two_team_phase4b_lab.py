"""The Phase 4B laboratory: choose a framing from rendered frames, not from taste.

Phase 4A's whole-arena safe-area number - 15.12 px of action-rail clearance -
was the thing that pinned the arena at 0.652 of the frame width, and the human
review rejected the result. So the 4B decision may not be made from a single
derived number either. This tool renders the *same instants of the same seed*
at three frame fractions and measures what a viewer actually gets.

``sweep``
    Render one seed's eleven event-centred stills at each candidate frame
    fraction and measure each frame: ink occupancy, the largest empty band, the
    drawn ball and opening in pixels, and whether the critical subject of that
    still is under the player's controls. Writes one comparison row per
    fraction plus a side-by-side contact sheet per moment.

``occupancy``
    Measure ink from rendered frames rather than from the model. The module's
    `occupancy_at` is a closed form over discs and annuli; this counts pixels
    above a luminance floor. The two are independent, and quoting either is
    only honest if they agree - which is the Phase 4A lesson written as a
    procedure rather than as a resolution.

Neither command decides anything on its own. They produce the numbers and the
sheets a person looks at before the framing is locked.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from satisfying import multishell_visual as visual  # noqa: E402
from satisfying import multishell_visual_cli as visual_cli  # noqa: E402
from satisfying.multishell_playback import document_for  # noqa: E402

#: The three the brief names. 0.652 is carried as the Phase 4A control so the
#: comparison has a "what we had" column rather than only a "what we propose".
FRACTIONS: tuple[float, ...] = (0.652, 0.800, 0.850, 0.900)
#: Anything at or below this in linear luminance is empty dark space. The
#: background is (0.020, 0.026, 0.042) and the floor glow reaches about 0.10,
#: so 0.14 counts the arena and the balls and not the pool they sit in.
INK_LUMINANCE = 0.14
#: And this is material and balls only. The floor glow reaches about 0.19 at
#: the centre, so the two thresholds separate "not dark" from "something is
#: drawn here" - and the review's complaint was about both.
SOLID_LUMINANCE = 0.30


class LabError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def _render_stills(
    godot: str, seed: int, out_dir: Path, playback: Path, moments: Path,
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
        f"sweep seed {seed} at {fraction:g}",
    )


# --------------------------------------------------------------------------
# Measurement from pixels
# --------------------------------------------------------------------------


def measure_frame(path: Path) -> dict[str, Any]:
    """Ink, emptiness and the worst empty band, counted off the image itself."""
    from PIL import Image
    import numpy

    with Image.open(path) as handle:
        rgb = numpy.asarray(handle.convert("RGB"), dtype=numpy.float32) / 255.0
    luma = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
    ink = luma > INK_LUMINANCE
    height, width = ink.shape
    rows = ink.any(axis=1)
    # The tallest run of rows with no ink at all: the black band the review
    # complained about, measured rather than inferred from the disc's radius.
    worst = run = 0
    for value in rows:
        run = 0 if value else run + 1
        worst = max(worst, run)
    columns = ink.any(axis=0)
    left = int(numpy.argmax(columns)) if columns.any() else 0
    right = int(width - numpy.argmax(columns[::-1])) if columns.any() else 0
    top = int(numpy.argmax(rows)) if rows.any() else 0
    bottom = int(height - numpy.argmax(rows[::-1])) if rows.any() else 0
    solid = luma > SOLID_LUMINANCE
    return {
        "ink_fraction": float(ink.mean()),
        "solid_fraction": float(solid.mean()),
        "mean_luma": float(luma.mean()),
        "empty_band_px": int(worst),
        "empty_band_fraction": worst / float(height),
        "ink_bbox": [left, top, right, bottom],
        "ink_width_px": right - left,
        "ink_height_px": bottom - top,
    }


# --------------------------------------------------------------------------
# Sheets
# --------------------------------------------------------------------------


def _side_by_side(paths: Sequence[Path], target: Path, labels: Sequence[str]) -> None:
    from PIL import Image, ImageDraw

    images = [Image.open(path).convert("RGB") for path in paths]
    scale = 420.0 / images[0].width
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


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


def cmd_sweep(args: argparse.Namespace) -> int:
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

    rows: list[dict[str, Any]] = []
    for fraction in args.fractions:
        frames = out / "sweep" / f"seed{seed}" / f"w{fraction:g}"
        if frames.is_dir():
            shutil.rmtree(frames)
        _render_stills(
            godot, seed, frames, playback, moments, fraction,
            args.width, args.height,
        )
        stills = sorted(frames.glob("*.png"))
        if not stills:
            raise LabError(f"no stills rendered at {fraction:g}")
        measured = [dict(measure_frame(path), file=path.name) for path in stills]
        # The derived numbers at this fraction, for the same instants.
        saved = visual.FRONTIER_WIDTH_FRACTION
        try:
            _set_fraction(fraction)
            sizes = visual.frame_size_report(document)
            critical = visual.critical_visibility_report(document)
            occupancy = visual.occupancy_report(document)
            contained = visual.containment_report(document)
        finally:
            _set_fraction(saved)
        rows.append(
            {
                "fraction": fraction,
                "frames": len(stills),
                "measured": measured,
                "measured_mean_ink": sum(m["ink_fraction"] for m in measured)
                / len(measured),
                "measured_worst_empty_band": max(
                    m["empty_band_px"] for m in measured
                ),
                "derived_ink_thirds": {
                    name: value["ink_fraction"]
                    for name, value in occupancy["thirds"].items()
                },
                "final_stage": sizes[-1],
                "critical_hidden": len(critical["hidden"]),
                "critical_pass": critical["critical_pass"],
                "worst_critical": critical["worst"],
                "contained": contained["contained"],
                "worst_containment_ratio": contained["worst_ratio"],
            }
        )

    # One sheet per moment, the fractions side by side.
    names = [entry["name"] for entry in moments_list]
    for index, name in enumerate(names):
        tiles: list[Path] = []
        labels: list[str] = []
        for fraction in args.fractions:
            frames = out / "sweep" / f"seed{seed}" / f"w{fraction:g}"
            stills = sorted(frames.glob("*.png"))
            if index < len(stills):
                tiles.append(stills[index])
                labels.append(f"{fraction:g}")
        if tiles:
            _side_by_side(
                tiles, out / "sweep" / f"seed{seed}" / "sheets" / f"{name}.png",
                labels,
            )

    report = {
        "format": 1,
        "seed": seed,
        "render_config_digest": visual.render_config_digest(),
        "ink_luminance": INK_LUMINANCE,
        "moments": names,
        "rows": rows,
    }
    target = out / "sweep" / f"seed{seed}" / "sweep.json"
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")

    print(f"{'frac':>6}{'ink(px)':>10}{'ink(model)':>12}{'band px':>9}"
          f"{'ball px':>9}{'open px':>9}{'wall px':>9}{'hidden':>8}{'held':>6}")
    for row in rows:
        stage = row["final_stage"]
        print(f"{row['fraction']:>6.3f}{row['measured_mean_ink']:>10.3f}"
              f"{row['derived_ink_thirds']['late']:>12.3f}"
              f"{row['measured_worst_empty_band']:>9d}"
              f"{stage['ball_drawn_diameter_px']:>9.1f}"
              f"{stage['opening_width_px']:>9.1f}"
              f"{stage['wall_apparent_thickness_px']:>9.1f}"
              f"{row['critical_hidden']:>8d}"
              f"{'yes' if row['contained'] else 'NO':>6}")
    print(f"  -> {target}")
    return 0


def _set_fraction(fraction: float) -> None:
    """Re-point the module's derived framing constants. Sweep only."""
    visual.FRONTIER_WIDTH_FRACTION = fraction
    visual.VIEW_DIAMETER_FRACTION = fraction * (1.0 + visual.VIEW_PAD_FRACTION)
    visual._STAGE_CACHE.clear()


def cmd_occupancy(args: argparse.Namespace) -> int:
    """Cross-check the analytic occupancy against rendered frames."""
    out = Path(args.out)
    rows: list[dict[str, Any]] = []
    for seed in args.seeds:
        document = document_for(seed)
        moments = visual.event_moments(document)
        frames = out / "sweep" / f"seed{seed}" / f"w{visual.FRONTIER_WIDTH_FRACTION:g}"
        stills = sorted(frames.glob("*.png"))
        if not stills:
            raise LabError(f"no stills under {frames}; run sweep first")
        for moment, path in zip(moments, stills):
            measured = measure_frame(path)
            modelled = visual.occupancy_at(document, float(moment["t"]))
            rows.append(
                {
                    "seed": seed,
                    "moment": moment["name"],
                    "t": float(moment["t"]),
                    "measured_ink": measured["ink_fraction"],
                    "modelled_ink": modelled["ink_fraction"],
                    "difference": measured["ink_fraction"] - modelled["ink_fraction"],
                    "empty_band_px": measured["empty_band_px"],
                }
            )
    target = out / "occupancy_crosscheck.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        json.dump({"format": 1, "rows": rows}, handle, indent=2)
        handle.write("\n")
    worst = max(abs(row["difference"]) for row in rows) if rows else 0.0
    print(f"{'seed':>7}{'moment':>20}{'measured':>10}{'model':>8}{'delta':>8}")
    for row in rows:
        print(f"{row['seed']:>7}{row['moment']:>20}{row['measured_ink']:>10.3f}"
              f"{row['modelled_ink']:>8.3f}{row['difference']:>+8.3f}")
    print(f"  worst disagreement {worst:.3f} -> {target}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="two_team_phase4b_lab", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=os.path.join("output", "phase4b"))
    parser.add_argument("--godot", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    sweep = sub.add_parser("sweep", help="render one seed at several fractions")
    sweep.add_argument("--seed", type=int, default=17964)
    sweep.add_argument("--fractions", type=float, nargs="+", default=list(FRACTIONS))
    sweep.add_argument("--width", type=int, default=1080)
    sweep.add_argument("--height", type=int, default=1920)
    sweep.set_defaults(func=cmd_sweep)

    occupancy = sub.add_parser("occupancy", help="pixels against the model")
    occupancy.add_argument("--seeds", type=int, nargs="+", default=[17964])
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

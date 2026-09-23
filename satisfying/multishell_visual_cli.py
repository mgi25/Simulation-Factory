"""Category 3, Test #2 redesign - visual Phase 2A, driven from one place.

    python -m satisfying.multishell_visual_cli candidates --out OUT
    python -m satisfying.multishell_visual_cli export     --out OUT
    python -m satisfying.multishell_visual_cli stills     --out OUT [--seed N]
    python -m satisfying.multishell_visual_cli clip       --out OUT [--seed N]
    python -m satisfying.multishell_visual_cli audit      --out OUT [--seed N]
    python -m satisfying.multishell_visual_cli measure    --out OUT
    python -m satisfying.multishell_visual_cli phone      --out OUT
    python -m satisfying.multishell_visual_cli report     --out OUT

`candidates` is the only command that reads the Phase 1 shortlist, and it is
the only one that decides anything: it applies `multishell_visual.CANDIDATE_RULE`
and writes the manifest that Audio Phase 2B will read. Everything after it
takes the manifest as given.

Finding Godot, in order: `--godot`, then `$GODOT_BIN` or `$GODOT4_BIN`, then
the PATH; FFmpeg the same way, via `$FFMPEG_BIN`.

`rendering/encode.py` does this job better and this module does not use it, on
purpose. `test_category_three_imports_no_other_category_and_no_company_os`
holds everything under `satisfying/` to the standard library, numpy, Pillow,
three leaf modules of `audio/` and itself, so that Category 3 can be lifted out
whole. Reaching into `rendering/` for a nicer encode command would have been
the first hole in that boundary; the encode here is twelve arguments and the
boundary is worth more than they are.

## Why `audit` exists

The architecture claims the renderer cannot change the simulation. That claim
is worth exactly as much as the diff behind it, so `audit` walks every frame in
Godot, writes down the ball position and panel state the *scene* computed, and
compares them here against `satisfying.multishell_playback`. A rendering bug
that moved a ball would show up as a position error; one that drew the wrong
damage state would show up as a state mismatch. Both are reported as numbers.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
from typing import Any

from satisfying import multishell_visual as visual
from satisfying.multishell_playback import (
    document_for,
    panel_state_at,
    position_at,
    read_playback,
    verify_document,
    write_playback,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GODOT_PROJECT = os.path.join(REPO, "godot")
RENDER_SCENE = "res://scenes/MultishellRender.tscn"
SCENE_SCRIPT = "res://scripts/multishell_scene.gd"
RENDER_SCRIPT = "res://scripts/multishell_render.gd"
GODOT_ENV_VARS = ("GODOT_BIN", "GODOT4_BIN")
GODOT_ON_PATH = ("godot", "godot4", "Godot_v4.7.2-stable_win64.exe")
FFMPEG_ENV_VARS = ("FFMPEG_BIN",)
FFMPEG_ON_PATH = ("ffmpeg", "ffmpeg.exe")
# The review encode. CRF 16 and `slow` on this material at 1080x1920 is
# visually transparent, which is what a review clip has to be: a compression
# artefact that a reviewer reads as a rendering artefact wastes a whole round.
# `-bitexact` and the two `-map_*` flags leave no creation time, machine name
# or encoder version in the file, so two encodes of the same frames compare.
REVIEW_CRF = 16
REVIEW_PRESET = "slow"
SHORTLIST = os.path.join(REPO, visual.SHORTLIST_PATH)
MANIFEST = os.path.join(
    REPO, "docs", "validation", "category3_multiplying_shell_adjust_v3b",
    "phase3b_candidates.json",
)


class VisualError(RuntimeError):
    """Something a caller has to fix, reported without a traceback."""


# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------


def godot_path(path: str) -> str:
    """A path Godot can open from anywhere.

    Godot is launched with `--path godot`, so its working directory is the
    Godot project and **every relative path handed to it resolves there**, not
    against the repository. `output/...` becomes `godot/output/...` and the
    render fails with "cannot read playback" on a file that plainly exists.
    Absolute, with forward slashes, which Godot accepts on Windows.
    """
    return os.path.abspath(path).replace("\\", "/")


def playback_path(out: str, seed: int) -> str:
    return os.path.join(out, "playback", f"seed{seed}.json")


def moments_path(out: str, seed: int) -> str:
    return os.path.join(out, "moments", f"seed{seed}.json")


def stills_dir(out: str, seed: int) -> str:
    return os.path.join(out, "stills", f"seed{seed}")


def frames_dir(out: str, seed: int, tag: str) -> str:
    return os.path.join(out, "frames", f"seed{seed}{tag}")


def clip_path(out: str, seed: int, tag: str) -> str:
    return os.path.join(out, "review", f"multishell_seed{seed}{tag}.mp4")


def manifest_seeds(out: str) -> list[int]:
    if not os.path.isfile(MANIFEST):
        raise VisualError(
            f"no candidate manifest at {MANIFEST}; run `candidates` first"
        )
    with open(MANIFEST, encoding="utf-8") as handle:
        return [int(seed) for seed in json.load(handle)["seeds"]]


# --------------------------------------------------------------------------
# Godot
# --------------------------------------------------------------------------


def find_ffmpeg(explicit: str | None) -> str:
    if explicit:
        if os.path.isfile(explicit):
            return explicit
        found = shutil.which(explicit)
        if found:
            return found
        raise VisualError(f"--ffmpeg does not name an executable: {explicit}")
    for variable in FFMPEG_ENV_VARS:
        value = os.environ.get(variable)
        if value and os.path.isfile(value):
            return value
    for name in FFMPEG_ON_PATH:
        found = shutil.which(name)
        if found:
            return found
    raise VisualError(
        "cannot find FFmpeg. Pass --ffmpeg PATH, set $FFMPEG_BIN, or put it "
        "on PATH. Nothing is downloaded automatically."
    )


def encode_command(ffmpeg: str, frames: str, output: str, fps: float,
                   frame_count: int) -> list[str]:
    """One review clip from one image sequence. No audio: this phase has none.

    `-framerate` on the input and `-r` with `-fps_mode cfr` on the output,
    because an image sequence carries no timing of its own and the rate is
    better stated twice than inferred once. `-frames:v` pins the count to what
    was rendered, so a stray file in the directory cannot lengthen the clip.
    """
    return [
        ffmpeg, "-hide_banner", "-nostdin", "-y",
        "-loglevel", "error",
        "-framerate", f"{fps:g}",
        "-start_number", "0",
        "-i", frames,
        "-frames:v", str(frame_count),
        "-c:v", "libx264",
        "-preset", REVIEW_PRESET,
        "-crf", str(REVIEW_CRF),
        "-profile:v", "high",
        "-pix_fmt", "yuv420p",
        "-r", f"{fps:g}",
        "-fps_mode", "cfr",
        "-movflags", "+faststart",
        "-map_metadata", "-1",
        "-map_chapters", "-1",
        "-bitexact",
        output,
    ]


def find_godot(explicit: str | None) -> str:
    if explicit:
        if os.path.isfile(explicit):
            return explicit
        found = shutil.which(explicit)
        if found:
            return found
        raise VisualError(f"--godot does not name an executable: {explicit}")
    for variable in GODOT_ENV_VARS:
        value = os.environ.get(variable)
        if value and os.path.isfile(value):
            return value
    for name in GODOT_ON_PATH:
        found = shutil.which(name)
        if found:
            return found
    raise VisualError(
        "cannot find Godot 4. Pass --godot PATH, set "
        f"{' or '.join('$' + name for name in GODOT_ENV_VARS)}, or put it on PATH."
    )


def check_scripts(godot: str) -> None:
    """Parse the GDScript before launching the scene.

    A parse error does not make Godot exit; it opens its window and sits there,
    and the first render of this phase hung for two minutes on an undeclared
    variable before it was killed by a timeout. `--check-only` turns that into a
    line of text in under ten seconds.
    """
    for script in (SCENE_SCRIPT, RENDER_SCRIPT):
        result = subprocess.run(
            [godot, "--path", GODOT_PROJECT, "--check-only", "--script", script],
            cwd=REPO, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        blob = (result.stdout or "") + (result.stderr or "")
        for line in blob.splitlines():
            if "SCRIPT ERROR" in line or "Parse Error" in line or "Failed to load" in line:
                raise VisualError(f"{script}: {line.strip()}")


def run_godot(godot: str, user_args: list[str], label: str) -> str:
    # No `--headless`: the headless display driver has no rendering device, so
    # `get_texture().get_image()` comes back empty. Every other render tool in
    # this repository opens the real window for the same reason.
    command = [godot, "--path", GODOT_PROJECT, RENDER_SCENE, "--"]
    command.extend(user_args)
    started = time.time()
    result = subprocess.run(
        command, cwd=REPO, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    elapsed = time.time() - started
    if result.returncode != 0:
        tail = "\n".join((result.stdout or "").splitlines()[-30:])
        errors = "\n".join((result.stderr or "").splitlines()[-30:])
        raise VisualError(
            f"{label}: Godot exited {result.returncode}\n--- stdout ---\n{tail}"
            f"\n--- stderr ---\n{errors}"
        )
    # GDScript pushes parse and runtime errors to stderr without failing the
    # process, so a zero exit is not on its own proof the scene was built.
    for line in (result.stderr or "").splitlines():
        if "SCRIPT ERROR" in line or "Parse Error" in line:
            raise VisualError(f"{label}: {line.strip()}")
    for line in (result.stdout or "").splitlines():
        stripped = line.strip()
        if stripped.startswith(("playback:", "arena:", "framing:", "rendered",
                                "audit:", "still ")):
            print(f"    {stripped}")
    print(f"  {label}: {elapsed:.1f}s")
    return result.stdout or ""


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


def cmd_candidates(args: argparse.Namespace) -> int:
    if not os.path.isfile(SHORTLIST):
        raise VisualError(f"no Phase 1 shortlist at {SHORTLIST}")
    with open(SHORTLIST, encoding="utf-8") as handle:
        shortlist = json.load(handle)
    manifest = visual.candidate_manifest(shortlist)
    manifest["render_config_digest"] = visual.render_config_digest()
    os.makedirs(os.path.dirname(MANIFEST), exist_ok=True)
    with open(MANIFEST, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")
    print(f"{len(manifest['seeds'])} of {len(shortlist['seeds'])} shortlisted "
          f"seeds pass the rule -> {MANIFEST}")
    print(f"{'seed':>7}{'dur':>8}{'split':>8}{'pop':>5}{'gens':>6}"
          f"{'route':>9}{'escape':>12}{'open/brk':>10}")
    for entry in manifest["candidates"]:
        print(f"{entry['seed']:>7}{entry['duration']:>8.2f}{entry['first_split']:>8.2f}"
              f"{entry['population']:>5}{entry['generations']:>6}"
              f"{entry['escape_route']:>9}{entry['escape_by']:>12}"
              f"{entry['progression_opening']:>6}/{entry['progression_break']:<4}")
    coverage = manifest["coverage"]
    print(f"  routes {coverage['escape_route']}  escaping {coverage['escaping_ball']}")
    print(f"  opening-dominant {coverage['opening_dominant']}  "
          f"break-heavy {coverage['break_heavy']}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    seeds = [args.seed] if args.seed else manifest_seeds(args.out)
    for seed in seeds:
        document = document_for(seed)
        reason = visual.validate_document(document)
        if reason:
            raise VisualError(f"seed {seed}: {reason}")
        path = write_playback(document, playback_path(args.out, seed))
        report = verify_document(document)
        os.makedirs(os.path.dirname(moments_path(args.out, seed)), exist_ok=True)
        with open(moments_path(args.out, seed), "w", encoding="utf-8") as handle:
            json.dump(visual.event_moments(document), handle, indent=1)
        print(f"  seed {seed:>6}  {document['summary']['duration']:.2f}s  "
              f"{len(document['balls'])} balls  digest {document['digest'][:16]}  "
              f"verify {'ok' if report['ok'] else report['checks']}  -> {path}")
    return 0


def cmd_stills(args: argparse.Namespace) -> int:
    godot = find_godot(args.godot)
    check_scripts(godot)
    seeds = [args.seed] if args.seed else manifest_seeds(args.out)
    for seed in seeds:
        out_dir = stills_dir(args.out, seed)
        os.makedirs(out_dir, exist_ok=True)
        run_godot(godot, [
            f"--playback={godot_path(playback_path(args.out, seed))}",
            f"--out-dir={godot_path(out_dir)}",
            f"--moments={godot_path(moments_path(args.out, seed))}",
            "--stills=1",
            f"--release={visual.RELEASE_SECONDS}",
            f"--hold={visual.END_HOLD_SECONDS}",
        ], f"stills seed {seed}")
    return 0


def cmd_clip(args: argparse.Namespace) -> int:
    godot = find_godot(args.godot)
    check_scripts(godot)
    ffmpeg = find_ffmpeg(args.ffmpeg)
    seeds = [args.seed] if args.seed else manifest_seeds(args.out)
    tag = "" if args.release is None else f"_release{args.release:g}"
    release = visual.RELEASE_SECONDS if args.release is None else args.release
    for seed in seeds:
        out_dir = frames_dir(args.out, seed, tag)
        if os.path.isdir(out_dir):
            shutil.rmtree(out_dir)
        os.makedirs(out_dir, exist_ok=True)
        run_godot(godot, [
            f"--playback={godot_path(playback_path(args.out, seed))}",
            f"--out-dir={godot_path(out_dir)}",
            "--clip=1",
            f"--fps={args.fps}",
            f"--release={release}",
            f"--hold={visual.END_HOLD_SECONDS}",
        ], f"clip seed {seed}")
        target = clip_path(args.out, seed, tag)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        frame_count = len([
            name for name in os.listdir(out_dir) if name.endswith(".png")
        ])
        command = encode_command(
            ffmpeg,
            os.path.join(out_dir, "frame_%05d.png"),
            target,
            args.fps,
            frame_count,
        )
        result = subprocess.run(command, capture_output=True, text=True,
                                encoding="utf-8", errors="replace")
        if result.returncode != 0:
            raise VisualError(
                f"encode seed {seed}: ffmpeg exited {result.returncode}\n"
                + "\n".join((result.stderr or "").splitlines()[-25:])
            )
        size = os.path.getsize(target) / 1e6
        print(f"  seed {seed:>6} -> {target}  ({size:.1f} MB)")
        if not args.keep_frames:
            shutil.rmtree(out_dir)
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    """Godot walks every frame; Python checks it against the document."""
    godot = find_godot(args.godot)
    check_scripts(godot)
    seeds = [args.seed] if args.seed else manifest_seeds(args.out)
    rows: list[dict[str, Any]] = []
    for seed in seeds:
        document = read_playback(playback_path(args.out, seed))
        for fps in args.fps_set:
            out_dir = os.path.join(args.out, "audit", f"seed{seed}")
            os.makedirs(out_dir, exist_ok=True)
            run_godot(godot, [
                f"--playback={godot_path(playback_path(args.out, seed))}",
                f"--out-dir={godot_path(out_dir)}",
                "--audit=1",
                f"--fps={fps}",
            ], f"audit seed {seed} at {fps:g} fps")
            with open(os.path.join(out_dir, f"audit_{fps:.0f}.json"),
                      encoding="utf-8") as handle:
                audit = json.load(handle)
            rows.append(_check_audit(document, audit))
    path = os.path.join(args.out, "audit", "audit_report.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"format": 1, "rows": rows}, handle, indent=2)
        handle.write("\n")
    print(f"{'seed':>7}{'fps':>6}{'frames':>8}{'max ball err':>14}"
          f"{'centre px':>12}{'panel rows':>12}{'panel bad':>11}{'digest':>9}")
    for row in rows:
        print(f"{row['seed']:>7}{row['fps']:>6.0f}{row['frames']:>8}"
              f"{row['max_position_error']:>14.3e}"
              f"{row['max_centre_error_px']:>12.3e}{row['panel_rows']:>12}"
              f"{row['panel_mismatches']:>11}"
              f"{'ok' if row['digest_matches'] else 'BAD':>9}")
    worst = max(row["max_position_error"] for row in rows)
    bad = sum(row["panel_mismatches"] for row in rows)
    centre_worst = max(row["max_centre_error_px"] for row in rows)
    print(f"  worst ball position error {worst:.3e} world units, "
          f"centre disagreement {centre_worst:.3e} px, "
          f"{bad} panel-state mismatches -> {path}")
    return 0 if (worst < 1e-9 and centre_worst <= 1.0 and bad == 0) else 1


def _check_audit(document: dict[str, Any], audit: dict[str, Any]) -> dict[str, Any]:
    worst = 0.0
    worst_t = 0.0
    panel_rows = 0
    mismatches = 0
    population_bad = 0
    max_centre_error = 0.0
    for row in audit["rows"]:
        t = float(row["t"])
        for ball in row["balls"]:
            expected = position_at(document, int(ball["ball_id"]), t)
            if expected is None:
                mismatches += 1
                continue
            error = math.hypot(float(ball["x"]) - expected[0],
                               float(ball["y"]) - expected[1])
            if error > worst:
                worst = error
                worst_t = t
        if len(row["balls"]) != _population_at(document, t):
            population_bad += 1
        max_centre_error = max(
            max_centre_error, float(row.get("centre_max_error_px", math.inf))
        )
        for entry in row["panels"]:
            panel_rows += 1
            expected_state = panel_state_at(
                document, int(entry["shell_id"]), int(entry["panel_id"]), t)
            if str(entry["state"]) != expected_state:
                mismatches += 1
    return {
        "seed": int(audit["seed"]),
        "fps": float(audit["fps"]),
        "frames": int(audit["frames"]),
        "digest_matches": str(audit["digest"]) == str(document["digest"]),
        "max_position_error": worst,
        "max_position_error_t": worst_t,
        "panel_rows": panel_rows,
        "panel_mismatches": mismatches,
        "population_mismatch_frames": population_bad,
        "max_centre_error_px": max_centre_error,
    }


def _population_at(document: dict[str, Any], t: float) -> int:
    return len([b for b in document["balls"] if float(b["birth_time"]) <= t])


PHONE_WIDTH = 405
PHONE_HEIGHT = 720


def cmd_phone(args: argparse.Namespace) -> int:
    """The same stills at the size a phone actually shows them.

    1080x1920 is the render, not the viewing condition. A Shorts player lays
    out against about 412 dp, so a feature that is 24 px in the render is
    9 px on the glass, and "is that panel cracked" is a different question
    there. This downsamples with a proper filter - not nearest, which would
    flatter thin bright lines by aliasing them into existence - and reports
    the feature sizes at that scale beside the render's own.
    """
    from PIL import Image  # noqa: PLC0415 - only this command needs Pillow

    seeds = [args.seed] if args.seed else manifest_seeds(args.out)
    rows = []
    for seed in seeds:
        source = stills_dir(args.out, seed)
        target = os.path.join(args.out, "phone", f"seed{seed}")
        os.makedirs(target, exist_ok=True)
        names = sorted(n for n in os.listdir(source) if n.endswith(".png"))
        for name in names:
            with Image.open(os.path.join(source, name)) as image:
                image.convert("RGB").resize(
                    (PHONE_WIDTH, PHONE_HEIGHT), Image.LANCZOS
                ).save(os.path.join(target, name))
        rows.append({"seed": seed, "stills": len(names), "path": target})
        print(f"  seed {seed:>6}  {len(names)} stills at "
              f"{PHONE_WIDTH}x{PHONE_HEIGHT} -> {target}")

    scale = PHONE_WIDTH / float(visual.FRAME_WIDTH)
    document = read_playback(playback_path(args.out, seeds[0]))
    shells = visual.shell_geometry_report(document)
    composition = visual.composition_report(document)
    print()
    print(f"AT PHONE SIZE ({PHONE_WIDTH}x{PHONE_HEIGHT}, "
          f"{scale:.3f} of the render)")
    print(f"  ball at the opening      {composition['ball_px_first_frame'] * scale:>6.1f} px")
    print(f"  ball at the climax       {composition['ball_px_last_frame'] * scale:>6.1f} px")
    print(f"  its halo at the climax   {composition['halo_px_last_frame'] * scale:>6.1f} px")
    print(f"{'shell':>7}{'wall':>8}{'gap':>8}{'chord':>8}{'wall at own stage':>20}")
    for entry in shells:
        final = entry["at_final_stage"]
        print(f"{entry['shell_id']:>7}{final['wall_px'] * scale:>8.1f}"
              f"{final['gap_px'] * scale:>8.1f}{final['chord_px'] * scale:>8.1f}"
              f"{entry['at_own_stage']['wall_px'] * scale:>20.1f}")
    path = os.path.join(args.out, "phone", "phone_report.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({
            "format": 1,
            "size": [PHONE_WIDTH, PHONE_HEIGHT],
            "scale": scale,
            "seeds": rows,
            "ball_px": {
                "opening": composition["ball_px_first_frame"] * scale,
                "climax": composition["ball_px_last_frame"] * scale,
                "halo_climax": composition["halo_px_last_frame"] * scale,
            },
            "shells": [
                {
                    "shell_id": entry["shell_id"],
                    "wall_px": entry["at_final_stage"]["wall_px"] * scale,
                    "gap_px": entry["at_final_stage"]["gap_px"] * scale,
                    "wall_px_own_stage": entry["at_own_stage"]["wall_px"] * scale,
                }
                for entry in shells
            ],
        }, handle, indent=2)
        handle.write("\n")
    return 0


def cmd_measure(args: argparse.Namespace) -> int:
    seeds = [args.seed] if args.seed else manifest_seeds(args.out)
    reports = []
    for seed in seeds:
        document = read_playback(playback_path(args.out, seed))
        reports.append(visual.measure_document(document, fps=args.fps))
    payload = {
        "format": 1,
        "render_config": visual.render_config(),
        "render_config_digest": visual.render_config_digest(),
        "seeds": seeds,
        "reports": reports,
    }
    path = os.path.join(args.out, "phase2a_measurements.json")
    os.makedirs(args.out, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    _print_measurements(reports)
    print(f"  render config digest {payload['render_config_digest']} -> {path}")
    return 0


def _print_measurements(reports: list[dict[str, Any]]) -> None:
    print()
    print("COMPOSITION AND BALLS")
    print(f"{'seed':>7}{'ball px':>9}{'ball px':>9}{'halo px':>9}{'cam mv':>8}"
          f"{'static':>8}{'occ 1st':>9}{'occ end':>9}{'clear px':>10}{'hidden':>8}")
    print(f"{'':>7}{'open':>9}{'end':>9}{'end':>9}{'%':>8}{'tail s':>8}"
          f"{'':>9}{'':>9}{'':>10}{'s':>8}")
    for report in reports:
        composition = report["composition"]
        safe = report["safe_area"]
        print(f"{report['seed']:>7}{composition['ball_px_first_frame']:>9.1f}"
              f"{composition['ball_px_last_frame']:>9.1f}"
              f"{composition['halo_px_last_frame']:>9.1f}"
              f"{100 * composition['camera_moving_fraction']:>8.1f}"
              f"{composition['static_tail_seconds']:>8.2f}"
              f"{composition['structure_occupancy_first']:>9.3f}"
              f"{composition['structure_occupancy_last']:>9.3f}"
              f"{safe['min_clearance_px']:>10.1f}"
              f"{safe['ball_hidden_longest_seconds']:>8.2f}")
    print()
    print("READABILITY AT PEAK POPULATION")
    print(f"{'seed':>7}{'peak':>6}{'thirds':>13}{'fams':>6}{'clust':>7}"
          f"{'3-merge s':>11}{'blob/ball':>11}{'step':>7}{'strobe':>8}")
    for report in reports:
        r = report["readability"]
        print(f"{report['seed']:>7}{r['peak_population']:>6}"
              f"{str(r['population_by_third']):>13}{r['families_max_on_screen']:>6}"
              f"{r['largest_cluster']:>7}{r['longest_triple_merge_seconds']:>11.2f}"
              f"{r['mean_blobs_per_ball']:>11.3f}{r['max_step_diameters']:>7.2f}"
              f"{str(r['strobes']):>8}")
    print()
    print("DAMAGE, AND THE WALL AT THE END")
    print(f"{'seed':>7}{'damaged':>9}{'critical':>10}{'fractured':>11}{'broken':>8}"
          f"{'shared':>8}{'worn at end':>13}{'min panel px':>14}")
    for report in reports:
        d = report["damage"]
        sizes = d["panel_chord_px_when_reached"]
        smallest = min((v["min"] for v in sizes.values()), default=0.0)
        print(f"{report['seed']:>7}{d['states_reached'].get('damaged', 0):>9}"
              f"{d['states_reached'].get('critical', 0):>10}"
              f"{d['states_reached'].get('fractured', 0):>11}"
              f"{d['states_reached'].get('broken', 0):>8}{d['shared_breaks']:>8}"
              f"{d['damaged_or_worse_at_end']:>13}{smallest:>14.1f}")
    print()
    print("THE FIVE LAYERS, AT THE FINAL FRAMING (px)")
    shells = reports[0]["shells"]
    print(f"{'shell':>6}{'panels':>8}{'open %':>8}{'face':>7}{'flank':>7}{'wall':>7}"
          f"{'chord':>8}{'gap':>8}{'wall at own stage':>20}")
    for entry in shells:
        final = entry["at_final_stage"]
        own = entry["at_own_stage"]
        print(f"{entry['shell_id']:>6}{entry['panels']:>8}"
              f"{100 * entry['open_fraction']:>8.1f}{final['face_px']:>7.1f}"
              f"{final['flank_px']:>7.1f}{final['wall_px']:>7.1f}"
              f"{final['chord_px']:>8.1f}{final['gap_px']:>8.1f}"
              f"{own['wall_px']:>20.1f}")


def cmd_report(args: argparse.Namespace) -> int:
    """Everything, in the order a reviewer reads it."""
    path = os.path.join(args.out, "phase2a_measurements.json")
    if not os.path.isfile(path):
        raise VisualError(f"no measurements at {path}; run `measure` first")
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    _print_measurements(payload["reports"])
    print()
    print("EVENT-CENTRED STILLS")
    for report in payload["reports"]:
        print(f"  seed {report['seed']}")
        for moment in report["moments"]:
            print(f"    {moment['name']:<18} {moment['t']:>6.2f}s  {moment['why']}")
    return 0


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="multishell_visual_cli", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="output/category3_multishell_v2a",
                        help="working directory for playback, frames and clips")
    parser.add_argument("--godot", default=None)
    parser.add_argument("--ffmpeg", default=None)
    parser.add_argument("--seed", type=int, default=None,
                        help="one seed instead of the whole manifest")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("candidates", help="apply the rule to the Phase 1 shortlist"
                   ).set_defaults(func=cmd_candidates)
    sub.add_parser("export", help="write the canonical playback documents"
                   ).set_defaults(func=cmd_export)
    sub.add_parser("stills", help="the nine event-centred stills per seed"
                   ).set_defaults(func=cmd_stills)

    clip = sub.add_parser("clip", help="render frames and encode a review MP4")
    clip.add_argument("--fps", type=float, default=30.0)
    clip.add_argument("--release", type=float, default=None,
                      help="override the escapee run-on; 0 is the hard cut")
    clip.add_argument("--keep-frames", action="store_true")
    clip.set_defaults(func=cmd_clip)

    audit = sub.add_parser("audit", help="prove the renderer changed nothing")
    audit.add_argument("--fps-set", type=float, nargs="+", default=[30.0, 60.0])
    audit.set_defaults(func=cmd_audit)

    measure = sub.add_parser("measure", help="every number the brief asks for")
    measure.add_argument("--fps", type=float, default=30.0)
    measure.set_defaults(func=cmd_measure)

    sub.add_parser("phone", help="the stills at the size a phone shows them"
                   ).set_defaults(func=cmd_phone)
    sub.add_parser("report", help="print the measurements again"
                   ).set_defaults(func=cmd_report)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    try:
        return int(args.func(args))
    except VisualError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

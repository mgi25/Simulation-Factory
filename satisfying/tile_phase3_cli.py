"""Phase 3's driver: pick the cast, export the playback, drive Godot, measure.

    python -m satisfying.tile_phase3_cli cast     --count 50000 --out output/category3_v3
    python -m satisfying.tile_phase3_cli export   --out output/category3_v3
    python -m satisfying.tile_phase3_cli stills   --out output/category3_v3 --seed 3530
    python -m satisfying.tile_phase3_cli clip     --out output/category3_v3 --seed 3530 --fps 30
    python -m satisfying.tile_phase3_cli audit    --out output/category3_v3 --seed 3530 --fps 30
    python -m satisfying.tile_phase3_cli measure  --out output/category3_v3
    python -m satisfying.tile_phase3_cli verify   --out output/category3_v3

Six tasks, and the split between them is the architecture:

- **cast** simulates the population, selects one seed per role and writes
  `cast.json`. This is the only task that sweeps.
- **export** writes one playback document per cast seed. This is the only task
  that touches the physics.
- **stills**, **clip** and **audit** call Godot, which reads a playback
  document and draws it. None of the three may produce a number the physics
  did not already contain.
- **measure** reads the rendered PNGs and reports what a viewer can see.
- **verify** re-simulates every exported document and compares.

Like the Phase 1 and Phase 2 drivers this lives in `satisfying/` rather than
`tools/`, for the reason recorded at the top of `satisfying/tile_escape_cli.py`:
`tools/` is a declared production root and three Company OS branch guards
refuse additions to it, and widening their allowlist from a Category 3 branch
is not this workstream's to do.

Finding Godot, in order: `--godot`, then `$GODOT_BIN` or `$GODOT4_BIN`, then
the PATH - the same order `tools/race2_render.py` uses, because a lab that
found Godot differently from the labs beside it would be one more thing to get
wrong on a new machine.
"""

from __future__ import annotations

import argparse
import dataclasses
import glob
import json
import os
import shutil
import subprocess
import sys
import time
from typing import Any, Sequence

sys.path.insert(0, os.getcwd())

from satisfying import tile_cast, tile_playback
from satisfying.tile_escape import simulate
from satisfying.tile_evaluator import DEFAULT_RULE, evaluate
from satisfying.tile_sweep import PHASE2_ARENA, PHASE2_CONFIG

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GODOT_PROJECT = os.path.join(REPO, "godot")
RENDER_SCENE = "res://scenes/TileEscapeRender.tscn"
GODOT_ENV_VARS = ("GODOT_BIN", "GODOT4_BIN")
GODOT_ON_PATH = ("godot", "godot4", "Godot_v4.7.2-stable_win64.exe")

# The locked Phase 2 operating point, with Phase 2's chosen speed.
PHASE3_SPEED = 85.0
PHASE3_CONFIG = dataclasses.replace(PHASE2_CONFIG, speed=PHASE3_SPEED)

DELIVERY = (1080, 1920)
PHONE = (270, 480)

# The five still moments, named. `tile_escape_render.gd` decides *when* each one
# is, from the run's own activation times rather than from the clock, so that
# "90% of the tiles are lit" means the same thing in a 26-second run and a
# 38-second one. They are listed here only so this module can document what it
# asks for; `d_penultimate` is the 50/51 frame and the most important still in
# the set, because it is where the mechanic either creates tension or does not.
STILL_MOMENTS: tuple[tuple[str, str], ...] = (
    ("a_open", "opening"),
    ("b_half", "~50% of tiles lit"),
    ("c_late", "~90% of tiles lit"),
    ("d_penultimate", "50 of 51 lit"),
    ("e_complete", "completion"),
)


class Phase3Error(RuntimeError):
    pass


# --------------------------------------------------------------------------
# Paths. One directory per run so a seed's evidence never mixes with another's.
# --------------------------------------------------------------------------


def cast_path(out: str) -> str:
    return os.path.join(out, "cast.json")


def playback_path(out: str, seed: int) -> str:
    return os.path.join(out, "playback", f"seed_{seed}.json")


def seed_dir(out: str, seed: int, kind: str) -> str:
    return os.path.join(out, kind, f"seed_{seed}")


def load_cast(out: str) -> dict[str, Any]:
    path = cast_path(out)
    if not os.path.isfile(path):
        raise Phase3Error(f"no cast at {path}; run the `cast` task first")
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def cast_seeds(out: str, only: Sequence[int] | None = None) -> list[int]:
    members = load_cast(out)["members"]
    seeds = [int(member["seed"]) for member in members]
    if only:
        missing = [seed for seed in only if seed not in seeds]
        if missing:
            raise Phase3Error(
                f"seeds {missing} are not in the cast; cast seeds are {seeds}"
            )
        return list(only)
    return seeds


# --------------------------------------------------------------------------
# cast
# --------------------------------------------------------------------------


def task_cast(args: argparse.Namespace) -> int:
    """Sweep the population once, select by role, write `cast.json`.

    The runs are evaluated and thrown away one at a time. Only the evaluation
    and the index of the last tile to light survive each iteration, which is
    what keeps a 50,000-seed selection inside a few hundred megabytes.
    """
    config = dataclasses.replace(PHASE3_CONFIG, speed=args.speed)
    arena = PHASE2_ARENA
    started = time.time()
    evaluations = []
    final_tiles: dict[int, int | None] = {}
    for seed in range(args.count):
        run = simulate(seed, config, arena)
        evaluations.append(evaluate(run))
        final_tiles[seed] = tile_cast.final_tile_index(run)
    swept = time.time() - started

    cast = tile_cast.select_cast(evaluations, final_tiles, arena, DEFAULT_RULE)
    document = {
        "kind": "category3_tile_escape_cast",
        "speed": config.speed,
        "seeds_searched": args.count,
        "sweep_seconds": round(swept, 1),
        "arena": {
            "sides": arena.sides,
            "tiles_per_side": arena.tiles_per_side,
            "total_tiles": arena.total_tiles,
            "circumradius": arena.circumradius,
        },
        "rule": DEFAULT_RULE.as_dict(),
        **cast.as_dict(),
    }
    os.makedirs(args.out, exist_ok=True)
    with open(cast_path(args.out), "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=1)

    print(
        f"swept {args.count} seeds at {config.speed:g} wu/s in {swept:.1f}s: "
        f"{cast.accepted} accepted"
    )
    for member in cast.members:
        flag = "accepted" if member.accepted else "REJECTED"
        print(
            f"  {member.role:16s} seed {member.seed:<6d} "
            f"{(member.completion_seconds or 0.0):5.1f}s  score {member.score:.3f}  "
            f"final tile {member.final_tile_index} at height "
            f"{(member.final_tile_height or 0.0):.2f}  {flag}"
        )
    for role in cast.unfilled:
        print(f"  {role:16s} UNFILLED")
    print(f"wrote {cast_path(args.out)}")
    return 0


# --------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------


def task_export(args: argparse.Namespace) -> int:
    """One playback document per cast seed. The only task that simulates."""
    config = dataclasses.replace(PHASE3_CONFIG, speed=args.speed)
    seeds = cast_seeds(args.out, args.seeds)
    for seed in seeds:
        run = simulate(seed, config, PHASE2_ARENA)
        path = tile_playback.write_playback(run, playback_path(args.out, seed))
        size = os.path.getsize(path)
        print(
            f"  seed {seed:<6d} {run.activated_tiles}/{run.total_tiles} tiles  "
            f"{(run.completion_time or run.end_time):6.2f}s  "
            f"{len(run.collisions)} collisions  {size / 1024:.0f} kB  -> {path}"
        )
    return 0


# --------------------------------------------------------------------------
# verify
# --------------------------------------------------------------------------


def task_verify(args: argparse.Namespace) -> int:
    """Re-simulate every exported document and compare it against the run."""
    seeds = cast_seeds(args.out, args.seeds)
    failures = 0
    for seed in seeds:
        document = tile_playback.read_playback(playback_path(args.out, seed))
        report = tile_playback.verify_document(document)
        ok = all(
            report[key]
            for key in (
                "digest_matches",
                "activation_order_matches",
                "activation_times_match_exactly",
                "completion_matches",
                "collision_count_matches",
            )
        )
        failures += 0 if ok else 1
        print(f"  seed {seed:<6d} {'OK ' if ok else 'FAIL'} {report['document_digest'][:16]}")
        if not ok:
            print(f"    {report}")
    print(f"{len(seeds) - failures}/{len(seeds)} documents verified")
    return 1 if failures else 0


# --------------------------------------------------------------------------
# Godot
# --------------------------------------------------------------------------


def find_godot(explicit: str | None) -> str:
    if explicit:
        if os.path.isfile(explicit):
            return explicit
        found = shutil.which(explicit)
        if found:
            return found
        raise Phase3Error(f"--godot does not name an executable: {explicit}")
    for variable in GODOT_ENV_VARS:
        value = os.environ.get(variable)
        if value and os.path.isfile(value):
            return value
    for name in GODOT_ON_PATH:
        found = shutil.which(name)
        if found:
            return found
    raise Phase3Error(
        "cannot find Godot 4. Pass --godot PATH, set "
        f"{' or '.join('$' + name for name in GODOT_ENV_VARS)}, or put it on PATH."
    )


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
        tail = "\n".join((result.stdout or "").splitlines()[-40:])
        errors = "\n".join((result.stderr or "").splitlines()[-40:])
        raise Phase3Error(
            f"{label}: Godot exited {result.returncode}\n--- stdout ---\n{tail}"
            f"\n--- stderr ---\n{errors}"
        )
    # GDScript pushes parse and runtime errors to stderr without failing the
    # process, so a zero exit is not on its own proof the scene was built.
    for line in (result.stderr or "").splitlines():
        if "SCRIPT ERROR" in line or "Parse Error" in line:
            raise Phase3Error(f"{label}: {line.strip()}")
    for line in (result.stdout or "").splitlines():
        stripped = line.strip()
        if stripped.startswith(("tile_escape:", "playback:", "arena:", "rendered",
                                "adapter:", "audit:", "frame", "still ")):
            print(f"    {stripped}")
    print(f"  {label}: {elapsed:.1f}s")
    return result.stdout or ""


def _godot_path(path: str) -> str:
    """A path Godot can open from anywhere.

    Godot is launched with `--path godot`, so its working directory is the
    Godot project and **every relative path handed to it resolves there**, not
    against the repository. A relative `--playback=output/...` therefore fails
    with "cannot read playback" while the same path works perfectly from the
    shell. Absolute, with forward slashes, which Godot accepts on Windows.
    """
    return os.path.abspath(path).replace("\\", "/")


def _render_args(args: argparse.Namespace, seed: int, out_dir: str) -> list[str]:
    return [
        f"--playback={_godot_path(playback_path(args.out, seed))}",
        f"--out-dir={_godot_path(out_dir)}",
        f"--width={args.width}",
        f"--height={args.height}",
        f"--fps={args.fps}",
        f"--hook={args.hook}",
        f"--trail={args.trail}",
        f"--debug={1 if args.debug else 0}",
    ]


def task_stills(args: argparse.Namespace) -> int:
    """The five progress stills, per seed, at delivery and at phone size."""
    godot = find_godot(args.godot)
    for seed in cast_seeds(args.out, args.seeds):
        out_dir = seed_dir(args.out, seed, args.kind)
        run_godot(
            godot,
            _render_args(args, seed, out_dir) + ["--stills=1"],
            f"stills seed {seed} at {args.width}x{args.height}",
        )
    return 0


def task_clip(args: argparse.Namespace) -> int:
    """Every frame of a run, or a window of it."""
    godot = find_godot(args.godot)
    for seed in cast_seeds(args.out, args.seeds):
        out_dir = seed_dir(args.out, seed, f"clip{int(args.fps)}")
        extra = ["--clip=1"]
        if args.start > 0.0:
            extra.append(f"--start={args.start}")
        if args.end > 0.0:
            extra.append(f"--end={args.end}")
        run_godot(
            godot,
            _render_args(args, seed, out_dir) + extra,
            f"clip seed {seed} at {args.fps:g} fps",
        )
    return 0


def task_audit(args: argparse.Namespace) -> int:
    """Walk every frame without saving PNGs, and write what the scene showed.

    This is the playback-accuracy evidence: Godot reports the frame on which it
    first drew each tile as active, and the ball position it computed at a
    sample of frames. Python then compares both against the canonical document.
    Nothing here is rendered to disk, so it is cheap enough to run at several
    frame rates for every seed in the cast.
    """
    godot = find_godot(args.godot)
    from satisfying import tile_readability

    failures = 0
    for seed in cast_seeds(args.out, args.seeds):
        out_dir = seed_dir(args.out, seed, "audit")
        run_godot(
            godot,
            _render_args(args, seed, out_dir) + ["--audit=1"],
            f"audit seed {seed} at {args.fps:g} fps",
        )
        audit_file = os.path.join(out_dir, f"audit_{int(args.fps)}fps.json")
        document = tile_playback.read_playback(playback_path(args.out, seed))
        report = tile_readability.compare_audit(document, audit_file)
        ok = report["playback_matches"]
        failures += 0 if ok else 1
        print(
            f"  seed {seed:<6d} {'OK ' if ok else 'FAIL'} "
            f"order={report['activation_order_matches']} "
            f"frames={report['activation_frames_match']} "
            f"final={report['final_activated']}/{report['total_tiles']} "
            f"max ball error={report['max_position_error_wu']:.3e} wu"
        )
        if not ok:
            print(f"    {json.dumps(report, indent=2)}")
    return 1 if failures else 0


# --------------------------------------------------------------------------
# measure
# --------------------------------------------------------------------------


def task_measure(args: argparse.Namespace) -> int:
    """Read the rendered stills and report what is visible in them."""
    from satisfying import tile_readability

    report: dict[str, Any] = {"seeds": {}}
    for seed in cast_seeds(args.out, args.seeds):
        document = tile_playback.read_playback(playback_path(args.out, seed))
        entry: dict[str, Any] = {
            "geometry": tile_readability.frame_geometry(
                document, args.width, args.height
            ),
            "motion": {
                str(int(fps)): tile_readability.motion_report(
                    document, fps, args.width, args.height
                )
                for fps in args.fps_list
            },
        }
        for kind, (width, height) in (("stills", DELIVERY), ("phone", PHONE)):
            directory = seed_dir(args.out, seed, kind)
            frames = sorted(glob.glob(os.path.join(directory, "*.png")))
            if not frames:
                continue
            entry[kind] = {
                os.path.basename(path): tile_readability.still_report(
                    document, path, width, height
                )
                for path in frames
            }
        report["seeds"][str(seed)] = entry
        geometry = entry["geometry"]
        print(
            f"  seed {seed:<6d} arena {geometry['arena_width_px']:.0f}px wide "
            f"({geometry['arena_occupancy_width']:.0%} of frame), tile "
            f"{geometry['tile_length_px']:.0f}px, ball {geometry['ball_diameter_px']:.0f}px"
        )
        for fps, motion in sorted(entry["motion"].items(), key=lambda kv: int(kv[0])):
            print(
                f"    {fps:>3s} fps: {motion['travel_px_median']:.0f}px median step, "
                f"{motion['travel_px_max']:.0f}px max, "
                f"{motion['frames_over_ball_diameter']} of {motion['frames']} frames "
                f"move more than one ball diameter"
            )

    path = os.path.join(args.out, "readability.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1)
    print(f"wrote {path}")
    return 0


# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m satisfying.tile_phase3_cli",
        description="Category 3 Phase 3: visual proof and candidate playback.",
    )
    parser.add_argument("task", choices=[
        "cast", "export", "verify", "stills", "clip", "audit", "measure",
    ])
    parser.add_argument("--out", default=os.path.join("output", "category3_v3"),
                        help="the evidence directory")
    parser.add_argument("--count", type=int, default=50_000,
                        help="seeds to sweep in the `cast` task")
    parser.add_argument("--speed", type=float, default=PHASE3_SPEED)
    parser.add_argument("--seeds", type=int, nargs="*", default=None,
                        help="restrict to these cast seeds")
    parser.add_argument("--godot", default=None)
    parser.add_argument("--fps", type=float, default=60.0)
    parser.add_argument("--fps-list", type=float, nargs="*", default=[30.0, 60.0],
                        dest="fps_list", help="frame rates the `measure` task reports")
    parser.add_argument("--width", type=int, default=DELIVERY[0])
    parser.add_argument("--height", type=int, default=DELIVERY[1])
    parser.add_argument("--phone", action="store_true",
                        help="render at phone size instead of delivery size")
    parser.add_argument("--kind", default="stills",
                        help="subdirectory the stills task writes into")
    parser.add_argument("--start", type=float, default=0.0)
    parser.add_argument("--end", type=float, default=-1.0)
    parser.add_argument("--hook", default="HIT EVERY TILE TO ESCAPE")
    parser.add_argument("--trail", default="temporal",
                        choices=["none", "halo", "temporal"],
                        help="the ball's motion treatment")
    parser.add_argument("--debug", action="store_true",
                        help="draw the seed, clock and collision count")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.phone:
        args.width, args.height = PHONE
        if args.kind == "stills":
            args.kind = "phone"
    tasks = {
        "cast": task_cast,
        "export": task_export,
        "verify": task_verify,
        "stills": task_stills,
        "clip": task_clip,
        "audit": task_audit,
        "measure": task_measure,
    }
    try:
        return tasks[args.task](args)
    except Phase3Error as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

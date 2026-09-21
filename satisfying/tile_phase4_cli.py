"""Phase 4's driver: the pacing evidence and the ending.

    python -m satisfying.tile_phase4_cli pacing  --out output/category3_v4 --seeds 3530 6132 20814
    python -m satisfying.tile_phase4_cli export  --out output/category3_v4 --seeds 3530 --timing standard
    python -m satisfying.tile_phase4_cli clip    --out output/category3_v4 --seeds 3530 --fps 30
    python -m satisfying.tile_phase4_cli climax  --out output/category3_v4 --seeds 3530 --fps 30
    python -m satisfying.tile_phase4_cli stills  --out output/category3_v4 --seeds 3530
    python -m satisfying.tile_phase4_cli audit   --out output/category3_v4 --seeds 3530 --fps 30
    python -m satisfying.tile_phase4_cli encode  --out output/category3_v4 --seeds 3530 --fps 30
    python -m satisfying.tile_phase4_cli verify  --out output/category3_v4 --seeds 3530

Phase 3's driver selected a cast from a fifty-thousand-seed sweep and could
only ever render that cast. Phase 4 renders named seeds instead, because the
question it is answering - what does a 3.7-second mid-run gap look like - is
about seeds chosen *for their gaps*, and the Phase 3 roles rank by a score
whose stagnation term is a quarter of the weight and therefore returns the
smooth end of the population. So `--seeds` is required and there is no cast.

Godot is found the same way Phase 3 finds it, and `ffmpeg` the same way the
race tools do: explicit flag, then the environment, then the PATH. The two
render tasks are deliberately separate - `clip` plays the Phase 3 presentation
and `climax` plays the Phase 4 ending - so a pacing clip cannot accidentally
carry the ending and a climax clip cannot accidentally be judged as pacing
evidence.

Like the Phase 1-3 drivers this lives in `satisfying/` and not in `tools/`, for
the reason at the top of `satisfying/tile_escape_cli.py`.
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

from satisfying import tile_completion, tile_pacing, tile_playback
from satisfying.tile_escape import simulate
from satisfying.tile_evaluator import DEFAULT_RULE, candidate_score, evaluate, verdict
from satisfying.tile_phase3_cli import (
    DELIVERY,
    PHASE3_CONFIG,
    PHONE,
    Phase3Error,
    _godot_path,
    find_godot,
    run_godot,
)
from satisfying.tile_sweep import PHASE2_ARENA

FFMPEG_ENV_VARS = ("FFMPEG_BIN",)
FFMPEG_ON_PATH = ("ffmpeg", "ffmpeg.exe")

# The six stills of the ending, named. `tile_escape_render.gd` decides *when*
# each one is, from the completion block's own timeline, so the same six names
# mean the same six beats whatever the timing preset is. Listed here so this
# module documents what it asks for - and pinned by a test against the GDScript,
# so the list is load-bearing rather than decorative and a rename on one side
# cannot silently leave the other behind.
CLIMAX_STILLS: tuple[tuple[str, str], ...] = (
    ("a_before_final", "one frame before the final activation"),
    ("b_final_hit", "the exact final activation"),
    ("c_confirmation", "the arena-wide wave"),
    ("d_unlock", "the gate fully open"),
    ("e_escape", "the ball on its way out"),
    ("f_end", "the final frame"),
)


class Phase4Error(RuntimeError):
    pass


# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------


def playback_path(out: str, seed: int, timing: str) -> str:
    return os.path.join(out, "playback", f"seed_{seed}_{timing}.json")


def seed_dir(out: str, seed: int, kind: str) -> str:
    return os.path.join(out, kind, f"seed_{seed}")


def _run(seed: int, speed: float):
    return simulate(seed, dataclasses.replace(PHASE3_CONFIG, speed=speed), PHASE2_ARENA)


# --------------------------------------------------------------------------
# pacing
# --------------------------------------------------------------------------


def task_pacing(args: argparse.Namespace) -> int:
    """Every reviewed gap of every named seed, and the gate's verdict on it."""
    gate = tile_pacing.DEFAULT_GATE
    report: dict[str, Any] = {
        "kind": "category3_tile_escape_pacing",
        "speed": args.speed,
        "gate": gate.as_dict(),
        "seeds": {},
    }
    os.makedirs(args.out, exist_ok=True)
    for seed in args.seeds:
        run = _run(seed, args.speed)
        evaluation = evaluate(run)
        decision = tile_pacing.judge(run, PHASE2_ARENA, gate)
        report["seeds"][str(seed)] = {
            "completion_seconds": evaluation.completion_seconds,
            "longest_body_gap_seconds": evaluation.longest_body_gap_seconds,
            "longest_body_gap_after_tiles": evaluation.longest_body_gap_after_tiles,
            "candidate_score": candidate_score(evaluation, DEFAULT_RULE).total,
            "phase2_accepted": verdict(evaluation, DEFAULT_RULE).accepted,
            "pacing": decision.as_dict(),
        }
        print(
            f"  seed {seed:<6d} {(evaluation.completion_seconds or 0.0):5.2f}s  "
            f"{'ACCEPT' if decision.accepted else 'REJECT'}"
        )
        for name, labels in sorted(decision.offending.items()):
            print(f"      ! {name}: {'; '.join(labels)}")
        for window in sorted(decision.reviewed, key=lambda w: -w.seconds):
            print(
                f"      {window.kind:11s} {window.seconds:5.2f}s @"
                f"{window.tiles_lit_at_start:3d}/{window.total_tiles}  "
                f"{window.collisions:3d} hits ({window.collisions_per_second:4.1f}/s)  "
                f"near {window.near_misses:2d} (chance {window.near_miss_chance:.2f}, "
                f"excess {window.near_miss_excess:+.2f})  sides {window.distinct_sides:2d}  "
                f"cover {window.area_coverage:.2f}  repeat {window.repeat_ratio:.2f}  "
                f"targets {window.targets_remaining}"
            )
    path = os.path.join(args.out, "pacing.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1)
    print(f"wrote {path}")
    return 0


# --------------------------------------------------------------------------
# export / verify
# --------------------------------------------------------------------------


def task_export(args: argparse.Namespace) -> int:
    """One playback document per seed, with a completion block attached."""
    timing = tile_completion.named_timing(args.timing)
    for seed in args.seeds:
        run = _run(seed, args.speed)
        document = tile_playback.playback_document(run)
        if run.completed:
            document = tile_completion.attach_completion(
                document, run, PHASE2_ARENA, timing
            )
            block = document["completion"]
            route = block["route"]
            print(
                f"  seed {seed:<6d} {run.activated_tiles}/{run.total_tiles}  "
                f"{run.completion_time:6.2f}s  gate side {route['gate_side']} "
                f"({len(route['gate_tiles'])} tiles)  reach "
                f"{route['reach_seconds']:.3f}s  exit {route['exit_seconds']:.3f}s  "
                f"ending {block['climax_seconds']:.2f}s  "
                f"video {block['total_render_seconds']:.2f}s"
            )
        else:
            print(f"  seed {seed:<6d} did not complete; no ending attached")
        path = playback_path(args.out, seed, args.timing)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(document, handle)
        print(f"            -> {path} ({os.path.getsize(path) / 1024:.0f} kB)")
    return 0


def task_verify(args: argparse.Namespace) -> int:
    """Re-simulate each document and confirm the ending changed nothing."""
    failures = 0
    for seed in args.seeds:
        path = playback_path(args.out, seed, args.timing)
        document = tile_playback.read_playback(path)
        report = tile_playback.verify_document(document)
        keys = (
            "digest_matches",
            "activation_order_matches",
            "activation_times_match_exactly",
            "completion_matches",
            "collision_count_matches",
        )
        ok = all(report[key] for key in keys)

        # And the Phase 4 half: the escape is the run's own last flight, not a
        # nearby one. Bit-for-bit, because "close enough" is how a second
        # simulation gets in.
        escape_ok = True
        if document.get("completion"):
            run = tile_playback.reload_run(document)
            last = run.flights[-1]
            escape = document["completion"]["escape"]
            escape_ok = (
                escape["t"] == last.t_start
                and escape["p"] == [last.position[0], last.position[1]]
                and escape["v"] == [last.velocity[0], last.velocity[1]]
            )
        failures += 0 if (ok and escape_ok) else 1
        print(
            f"  seed {seed:<6d} document {'OK ' if ok else 'FAIL'}  "
            f"escape-is-canonical {'OK ' if escape_ok else 'FAIL'}  "
            f"{report['document_digest'][:16]}"
        )
    print(f"{len(args.seeds) - failures}/{len(args.seeds)} verified")
    return 1 if failures else 0


# --------------------------------------------------------------------------
# Godot
# --------------------------------------------------------------------------


def _render_args(args: argparse.Namespace, seed: int, out_dir: str) -> list[str]:
    return [
        f"--playback={_godot_path(playback_path(args.out, seed, args.timing))}",
        f"--out-dir={_godot_path(out_dir)}",
        f"--width={args.width}",
        f"--height={args.height}",
        f"--fps={args.fps}",
        f"--hook={args.hook}",
        f"--trail={args.trail}",
        f"--debug={1 if args.debug else 0}",
    ]


def task_clip(args: argparse.Namespace) -> int:
    """The Phase 3 presentation, for pacing evidence. No ending."""
    godot = find_godot(args.godot)
    for seed in args.seeds:
        out_dir = seed_dir(args.out, seed, f"clip{int(args.fps)}")
        extra = ["--clip=1"]
        if args.start > 0.0:
            extra.append(f"--start={args.start}")
        if args.end > 0.0:
            extra.append(f"--end={args.end}")
        run_godot(godot, _render_args(args, seed, out_dir) + extra,
                  f"clip seed {seed} at {args.fps:g} fps")
    return 0


def task_climax(args: argparse.Namespace) -> int:
    """The full video with the ending, indexed by render time."""
    godot = find_godot(args.godot)
    for seed in args.seeds:
        out_dir = seed_dir(args.out, seed, f"climax{int(args.fps)}_{args.timing}")
        extra = ["--clip=1", "--climax=1"]
        if args.start > 0.0:
            extra.append(f"--start={args.start}")
        if args.end > 0.0:
            extra.append(f"--end={args.end}")
        run_godot(godot, _render_args(args, seed, out_dir) + extra,
                  f"climax seed {seed} at {args.fps:g} fps, timing {args.timing}")
    return 0


def task_stills(args: argparse.Namespace) -> int:
    """The six named stills of the ending, at whatever size is asked for."""
    godot = find_godot(args.godot)
    for seed in args.seeds:
        out_dir = seed_dir(args.out, seed, f"{args.kind}_{args.timing}")
        run_godot(godot, _render_args(args, seed, out_dir) + ["--climax-stills=1"],
                  f"climax stills seed {seed} at {args.width}x{args.height}")
    return 0


def task_audit(args: argparse.Namespace) -> int:
    """Phase 3's playback audit, re-run on a Phase 4 document.

    Deliberately runs with the ending **off**: the claim it checks is that the
    canonical run is bit-identical to what the renderer draws, and that claim
    is about the run, not about the sequence bolted to the end of it. If
    attaching a completion block had disturbed one activation frame, this is
    what would say so.
    """
    godot = find_godot(args.godot)
    from satisfying import tile_readability

    failures = 0
    for seed in args.seeds:
        out_dir = seed_dir(args.out, seed, "audit")
        run_godot(godot, _render_args(args, seed, out_dir) + ["--audit=1"],
                  f"audit seed {seed} at {args.fps:g} fps")
        audit_file = os.path.join(out_dir, f"audit_{int(args.fps)}fps.json")
        document = tile_playback.read_playback(playback_path(args.out, seed, args.timing))
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
# encode
# --------------------------------------------------------------------------


def find_ffmpeg(explicit: str | None) -> str:
    if explicit:
        if os.path.isfile(explicit):
            return explicit
        found = shutil.which(explicit)
        if found:
            return found
        raise Phase4Error(f"--ffmpeg does not name an executable: {explicit}")
    for variable in FFMPEG_ENV_VARS:
        value = os.environ.get(variable)
        if value and os.path.isfile(value):
            return value
    for name in FFMPEG_ON_PATH:
        found = shutil.which(name)
        if found:
            return found
    raise Phase4Error("cannot find ffmpeg; pass --ffmpeg PATH or put it on PATH")


def task_encode(args: argparse.Namespace) -> int:
    """PNG sequence to MP4. Silent: Phase 5 designs the audio."""
    ffmpeg = find_ffmpeg(args.ffmpeg)
    for seed in args.seeds:
        directory = seed_dir(args.out, seed, args.kind)
        frames = sorted(glob.glob(os.path.join(directory, "frame_*.png")))
        if not frames:
            raise Phase4Error(f"no frames in {directory}; render it first")
        first = int(os.path.basename(frames[0])[6:12])
        target = os.path.join(args.out, f"{args.label or args.kind}_seed{seed}.mp4")
        command = [
            ffmpeg, "-y",
            "-framerate", str(args.fps),
            "-start_number", str(first),
            "-i", os.path.join(directory, "frame_%06d.png"),
            "-c:v", "libx264", "-preset", "slow", "-crf", "17",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            target,
        ]
        started = time.time()
        result = subprocess.run(command, capture_output=True, text=True,
                                encoding="utf-8", errors="replace")
        if result.returncode != 0:
            tail = "\n".join((result.stderr or "").splitlines()[-25:])
            raise Phase4Error(f"ffmpeg exited {result.returncode}\n{tail}")
        size = os.path.getsize(target)
        print(
            f"  seed {seed:<6d} {len(frames)} frames -> {target} "
            f"({size / 1_048_576:.1f} MB, {time.time() - started:.0f}s)"
        )
    return 0


# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m satisfying.tile_phase4_cli",
        description="Category 3 Phase 4: the pacing gate and the completion climax.",
    )
    parser.add_argument("task", choices=[
        "pacing", "export", "verify", "clip", "climax", "stills", "audit", "encode",
    ])
    parser.add_argument("--out", default=os.path.join("output", "category3_v4"))
    parser.add_argument("--seeds", type=int, nargs="+", required=True)
    parser.add_argument("--speed", type=float, default=PHASE3_CONFIG.speed)
    parser.add_argument("--timing", default="standard",
                        choices=sorted(tile_completion.TIMINGS),
                        help="which climax timing preset to build and render")
    parser.add_argument("--godot", default=None)
    parser.add_argument("--ffmpeg", default=None)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--width", type=int, default=DELIVERY[0])
    parser.add_argument("--height", type=int, default=DELIVERY[1])
    parser.add_argument("--phone", action="store_true")
    parser.add_argument("--kind", default="stills",
                        help="the subdirectory a task reads or writes")
    parser.add_argument("--label", default=None, help="the encoded file's prefix")
    parser.add_argument("--start", type=float, default=0.0)
    parser.add_argument("--end", type=float, default=-1.0)
    parser.add_argument("--hook", default="HIT EVERY TILE TO ESCAPE")
    parser.add_argument("--trail", default="temporal",
                        choices=["none", "halo", "temporal"])
    parser.add_argument("--debug", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.phone:
        args.width, args.height = PHONE
        if args.kind == "stills":
            args.kind = "phone"
    tasks = {
        "pacing": task_pacing,
        "export": task_export,
        "verify": task_verify,
        "clip": task_clip,
        "climax": task_climax,
        "stills": task_stills,
        "audit": task_audit,
        "encode": task_encode,
    }
    try:
        return tasks[args.task](args)
    except (Phase4Error, Phase3Error, tile_completion.CompletionError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

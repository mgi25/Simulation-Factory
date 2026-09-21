"""Phase 5's driver: the score, the master, the previews and the evidence.

    python -m satisfying.tile_phase5_cli export  --seeds 3530 --timing standard
    python -m satisfying.tile_phase5_cli score   --seeds 3530 --config v2_refined
    python -m satisfying.tile_phase5_cli render  --seeds 3530 --config v2_refined
    python -m satisfying.tile_phase5_cli sync    --seeds 3530 --config v2_refined
    python -m satisfying.tile_phase5_cli climax  --seeds 26267 --fps 30
    python -m satisfying.tile_phase5_cli mux     --seeds 3530 --config v2_refined \
        --video ../wt-category3-tile-escape/output/category3_v4/climax_seed3530.mp4
    python -m satisfying.tile_phase5_cli verify  --seeds 3530 --config v2_refined
    python -m satisfying.tile_phase5_cli compare --seeds 3530

Phase 4 rendered the pictures and this phase does not re-render the ones it
already has: `mux` will take an existing MP4 and copy its video stream bit for
bit rather than re-encoding a frame sequence, so a preview with sound carries
the *same* pixels the silent climax preview was judged on and the only
difference between the two files is the thing being judged.

`export` writes Phase 5's own playback documents rather than reading Phase 4's,
so this phase reproduces from a seed and not from a directory. They are the
same documents - `verify` re-simulates and compares - and having them locally
is what lets the audio evidence stand on its own.

Like the Phase 1-4 drivers this lives in `satisfying/` and not in `tools/`, for
the reason at the top of `satisfying/tile_escape_cli.py`.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
import time
from typing import Any, Sequence

sys.path.insert(0, os.getcwd())

from satisfying import tile_audio, tile_completion, tile_playback, tile_score
from satisfying.tile_phase3_cli import DELIVERY, PHONE, Phase3Error, _godot_path, find_godot, run_godot
from satisfying.tile_phase4_cli import (
    Phase4Error,
    _render_args,
    _run,
    find_ffmpeg,
    seed_dir,
)
from satisfying.tile_sweep import PHASE2_ARENA

DEFAULT_OUT = os.path.join("output", "category3_v5")
# What the encoded Short must not exceed as a true peak. The master sits at
# `audio.soundtrack.PEAK_CEILING_DBFS` (-1.3), a third of a decibel below this,
# which is the repository's established reserve for AAC's inter-sample
# overshoot. `verify` decodes the finished MP4 and checks it, rather than
# trusting the reserve.
DELIVERY_TRUE_PEAK_DBTP = -1.0
AUDIO_BITRATE = "192k"


class Phase5Error(RuntimeError):
    pass


# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------


def playback_path(out: str, seed: int, timing: str) -> str:
    return os.path.join(out, "playback", f"seed_{seed}_{timing}.json")


def score_path(out: str, seed: int, config: str) -> str:
    return os.path.join(out, "score", f"seed_{seed}_{config}.json")


def wav_path(out: str, seed: int, config: str) -> str:
    return os.path.join(out, "audio", f"seed_{seed}_{config}.wav")


def measure_path(out: str, seed: int, config: str) -> str:
    return os.path.join(out, "audio", f"seed_{seed}_{config}.measure.json")


def preview_path(out: str, seed: int, config: str) -> str:
    return os.path.join(out, f"preview_seed{seed}_{config}.mp4")


def _write_json(path: str, payload: Any) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1)
    return path


def _config(args: argparse.Namespace) -> tile_score.AudioConfig:
    return tile_score.named_config(args.config, fps=args.fps)


def _document(args: argparse.Namespace, seed: int) -> dict[str, Any]:
    path = playback_path(args.out, seed, args.timing)
    if not os.path.isfile(path):
        raise Phase5Error(f"no playback document at {path}; run `export` first")
    return tile_playback.read_playback(path)


# --------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------


def task_export(args: argparse.Namespace) -> int:
    """Phase 4's playback document with its completion block, per seed."""
    timing = tile_completion.named_timing(args.timing)
    for seed in args.seeds:
        run = _run(seed, args.speed)
        document = tile_playback.playback_document(run)
        if not run.completed:
            raise Phase5Error(f"seed {seed} does not complete; it has no ending")
        document = tile_completion.attach_completion(
            document, run, PHASE2_ARENA, timing)
        block = document["completion"]
        path = _write_json(playback_path(args.out, seed, args.timing), document)
        print(
            f"  seed {seed:<6d} {run.completion_time:6.2f}s + "
            f"{block['climax_seconds']:.2f}s ending = "
            f"{block['total_render_seconds']:.2f}s  "
            f"{len(document['collisions'])} contacts  "
            f"digest {document['digest'][:16]}  -> {path}"
        )
    return 0


# --------------------------------------------------------------------------
# score
# --------------------------------------------------------------------------


def task_score(args: argparse.Namespace) -> int:
    """The audio-event schedule, as a machine-readable sidecar."""
    config = _config(args)
    for seed in args.seeds:
        document = _document(args, seed)
        plan = tile_score.schedule(document, config)
        payload = plan.as_dict()
        payload["schedule_fingerprint"] = plan.fingerprint()
        path = _write_json(score_path(args.out, seed, config.name), payload)
        metrics = plan.metrics
        print(
            f"  seed {seed:<6d} {config.name:15s} {metrics['events']:3d} events "
            f"({metrics['by_kind']['duplicate']} dup, "
            f"{metrics['by_kind']['activation']} new, "
            f"{metrics['by_kind']['final']} final)  "
            f"{metrics['events_per_second']:.2f}/s  "
            f"overlap {metrics['max_scheduled_overlap']}  "
            f"{plan.frames} frames / {plan.total_seconds:.2f}s  "
            f"{plan.fingerprint()[:16]}"
        )
        print(f"            -> {path}")
    return 0


# --------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------


def task_render(args: argparse.Namespace) -> int:
    """The stereo PCM master, and every measurement of it."""
    config = _config(args)
    for seed in args.seeds:
        document = _document(args, seed)
        started = time.time()
        rendered = tile_audio.render_document(document, config)
        path = tile_audio.write_master(rendered, wav_path(args.out, seed, config.name))
        report = tile_audio.measure(rendered, phone=not args.no_phone,
                                    document=document)
        report["wav"] = os.path.basename(path)
        report["pcm_digest"] = rendered.digest()
        _write_json(measure_path(args.out, seed, config.name), report)
        gaps = report["hierarchy_gaps_db"]
        print(
            f"  seed {seed:<6d} {config.name:15s} "
            f"peak {report['peak']['sample_peak_dbfs']:+.2f} dBFS / "
            f"{report['peak']['true_peak_dbtp']:+.2f} dBTP  "
            f"{report['loudness']['integrated_lufs']:+.1f} LUFS  "
            f"clip {report['peak']['clipped_samples']}  "
            f"voices {report['voices']['max_voices']}  "
            f"new>dup {gaps['activation_over_duplicate_db']:+.1f} dB  "
            f"final>new {gaps['final_over_activation_db']:+.1f} dB  "
            f"({time.time() - started:.0f}s)"
        )
        print(f"            -> {path} ({os.path.getsize(path) / 1_048_576:.1f} MB)")
    return 0


# --------------------------------------------------------------------------
# sync
# --------------------------------------------------------------------------


def task_sync(args: argparse.Namespace) -> int:
    """Where every cue lands against the frame that shows what caused it."""
    config = _config(args)
    failures = 0
    for seed in args.seeds:
        document = _document(args, seed)
        plan = tile_score.schedule(document, config)
        report = tile_audio.sync_report(plan, document)
        ok = (not report["frame_mismatches"]
              and report["activation_frames_agree"]
              and report["max_placement_error_frames"] < 0.01)
        failures += 0 if ok else 1
        print(
            f"  seed {seed:<6d} {'OK  ' if ok else 'FAIL'} "
            f"{report['events']} events  "
            f"frames agree={report['activation_frames_agree']}  "
            f"mismatches={len(report['frame_mismatches'])}  "
            f"placement {report['max_placement_error_seconds'] * 1e6:.1f} us "
            f"({report['max_placement_error_frames']:.6f} frames)  "
            f"frame lead mean {report['mean_frame_lead_seconds'] * 1000:.1f} ms "
            f"max {report['max_frame_lead_seconds'] * 1000:.1f} ms"
        )
        for name, beat in sorted(report["beats"].items()):
            if name.startswith("cue_"):
                print(f"      {name:14s} render {beat['render_seconds']:8.4f}s "
                      f"frame {beat['frame']:5d} at {beat['at_seconds']:8.4f}s")
        _write_json(os.path.join(args.out, "sync",
                                 f"seed_{seed}_{config.name}.json"), report)
    return 1 if failures else 0


# --------------------------------------------------------------------------
# climax - the Godot render, for seeds Phase 4 did not draw
# --------------------------------------------------------------------------


def task_climax(args: argparse.Namespace) -> int:
    """The full video with the ending, indexed by render time.

    Identical to `tile_phase4_cli climax` and calling the same scene; it is
    here so a Phase 5 seed can be drawn into a Phase 5 directory without
    reaching into Phase 4's output.
    """
    godot = find_godot(args.godot)
    for seed in args.seeds:
        out_dir = seed_dir(args.out, seed, f"climax{int(args.fps)}_{args.timing}")
        run_godot(godot, _render_args(args, seed, out_dir) + ["--clip=1", "--climax=1"],
                  f"climax seed {seed} at {args.fps:g} fps, timing {args.timing}")
    return 0


# --------------------------------------------------------------------------
# mux
# --------------------------------------------------------------------------


def _ffprobe_streams(ffmpeg: str, path: str) -> str:
    probe = os.path.join(os.path.dirname(ffmpeg), "ffprobe")
    for candidate in (probe, probe + ".exe"):
        if os.path.isfile(candidate):
            result = subprocess.run(
                [candidate, "-v", "error", "-show_entries",
                 "stream=codec_type,codec_name,duration,nb_frames",
                 "-of", "default=noprint_wrappers=1", path],
                capture_output=True, text=True, encoding="utf-8", errors="replace")
            return result.stdout.strip()
    return ""


def task_mux(args: argparse.Namespace) -> int:
    """Picture plus sound, into one MP4.

    Two paths, and the first is preferred wherever it is available:

    * `--video` names an MP4 that already exists. Its video stream is copied
      with `-c:v copy`, so not one pixel is re-encoded and the preview with
      sound is provably the same picture as the silent preview Phase 4 judged.
    * otherwise the frame sequence under `--kind` is encoded, at Phase 4's
      settings.
    """
    ffmpeg = find_ffmpeg(args.ffmpeg)
    config = _config(args)
    for seed in args.seeds:
        audio = wav_path(args.out, seed, config.name)
        if not os.path.isfile(audio):
            raise Phase5Error(f"no master at {audio}; run `render` first")
        target = preview_path(args.out, seed, config.name)
        os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)

        source = args.video
        if source and not os.path.isfile(source):
            raise Phase5Error(f"--video does not name a file: {source}")
        if source:
            command = [
                ffmpeg, "-y", "-i", source, "-i", audio,
                "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", AUDIO_BITRATE,
                "-movflags", "+faststart", "-shortest", target,
            ]
            what = f"copied from {os.path.basename(source)}"
        else:
            directory = seed_dir(args.frames_from or args.out, seed, args.kind)
            frames = sorted(glob.glob(os.path.join(directory, "frame_*.png")))
            if not frames:
                raise Phase5Error(f"no frames in {directory}; render it first")
            first = int(os.path.basename(frames[0])[6:12])
            command = [
                ffmpeg, "-y",
                "-framerate", str(args.fps),
                "-start_number", str(first),
                "-i", os.path.join(directory, "frame_%06d.png"),
                "-i", audio,
                "-c:v", "libx264", "-preset", "slow", "-crf", "17",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", AUDIO_BITRATE,
                "-movflags", "+faststart", "-shortest", target,
            ]
            what = f"{len(frames)} frames encoded"

        started = time.time()
        result = subprocess.run(command, capture_output=True, text=True,
                                encoding="utf-8", errors="replace")
        if result.returncode != 0:
            tail = "\n".join((result.stderr or "").splitlines()[-25:])
            raise Phase5Error(f"ffmpeg exited {result.returncode}\n{tail}")
        print(
            f"  seed {seed:<6d} {config.name:15s} {what} -> {target} "
            f"({os.path.getsize(target) / 1_048_576:.1f} MB, "
            f"{time.time() - started:.0f}s)"
        )
        streams = _ffprobe_streams(ffmpeg, target)
        if streams:
            print("            " + streams.replace("\n", "  "))
    return 0


# --------------------------------------------------------------------------
# verify
# --------------------------------------------------------------------------


def task_verify(args: argparse.Namespace) -> int:
    """Four things, and each one is a different way the phase could be wrong.

    1. The playback document still describes the run it names - Phase 3's
       check, re-run, so a Phase 5 document is a Phase 4 document.
    2. The schedule is reproducible: built twice, compared as JSON.
    3. The master is reproducible: rendered twice, PCM digests compared.
    4. The *encoded* MP4's audio still clears the delivery ceiling. The master
       reserves 0.3 dB for AAC's inter-sample overshoot; this decodes the file
       and measures what actually came out, because a reserve that is never
       checked is a hope.
    """
    from audio import loudness

    config = _config(args)
    failures = 0
    for seed in args.seeds:
        document = _document(args, seed)
        playback = tile_playback.verify_document(document)
        document_ok = all(playback[key] for key in (
            "digest_matches", "activation_order_matches",
            "activation_times_match_exactly", "completion_matches",
            "collision_count_matches"))

        first = tile_score.schedule(document, config)
        second = tile_score.schedule(document, config)
        schedule_ok = first.fingerprint() == second.fingerprint()

        one = tile_audio.render(first).digest()
        two = tile_audio.render(second).digest()
        render_ok = one == two

        encoded_ok: bool | None = None
        encoded_peak = None
        encoded_lufs = None
        preview = preview_path(args.out, seed, config.name)
        if os.path.isfile(preview):
            ffmpeg = find_ffmpeg(args.ffmpeg)
            decoded = os.path.join(args.out, "audio",
                                   f"seed_{seed}_{config.name}.decoded.wav")
            result = subprocess.run(
                [ffmpeg, "-y", "-i", preview, "-vn",
                 "-c:a", "pcm_s24le", "-ar", str(config.sample_rate), decoded],
                capture_output=True, text=True, encoding="utf-8", errors="replace")
            if result.returncode != 0:
                raise Phase5Error(f"could not decode {preview}")
            # `loudness.read_pcm` normalises to [-1, 1); the integers
            # `wav_io.decode_samples` returns would read as +138 dBTP.
            stereo, decoded_rate = loudness.read_pcm(decoded)
            encoded_peak = round(loudness.true_peak(stereo), 3)
            encoded_lufs = round(loudness.integrated(stereo, decoded_rate), 2)
            encoded_ok = encoded_peak <= DELIVERY_TRUE_PEAK_DBTP

        ok = document_ok and schedule_ok and render_ok and encoded_ok is not False
        failures += 0 if ok else 1
        print(
            f"  seed {seed:<6d} {config.name:15s} "
            f"document {'OK ' if document_ok else 'FAIL'}  "
            f"schedule {'OK ' if schedule_ok else 'FAIL'}  "
            f"waveform {'OK ' if render_ok else 'FAIL'}  "
            f"encoded "
            + ("n/a " if encoded_ok is None
               else f"{'OK ' if encoded_ok else 'FAIL'} {encoded_peak:+.2f} dBTP"
                   f" {encoded_lufs:+.1f} LUFS")
            + f"  {one[:16]}"
        )
    return 1 if failures else 0


# --------------------------------------------------------------------------
# compare
# --------------------------------------------------------------------------


COMPARE_ROWS: tuple[tuple[str, str], ...] = (
    ("peak.sample_peak_dbfs", "sample peak dBFS"),
    ("peak.true_peak_dbtp", "true peak dBTP"),
    ("peak.clipped_samples", "clipped samples"),
    ("loudness.integrated_lufs", "integrated LUFS"),
    ("loudness.lra_lu", "LRA LU"),
    ("voices.max_voices", "max voices"),
    ("hierarchy_gaps_db.activation_over_duplicate_db", "new over dup, peak dB"),
    ("hierarchy_gaps_db.final_over_activation_db", "final over new, peak dB"),
    ("hierarchy_gaps_db.phone_activation_over_duplicate_db",
     "phone new over dup dB"),
    ("hierarchy_gaps_db.phone_final_over_activation_rms_db",
     "phone final over new, RMS dB"),
    ("confirmation.at_detonation_dbfs", "pause: at detonation dB"),
    ("confirmation.floor_dbfs", "pause: quietest bin dB"),
    ("confirmation.at_unlock_dbfs", "pause: at the unlock dB"),
    ("confirmation.contrast_db", "pause: contrast dB"),
    ("masking.activation.median_emergence_db", "new emerges by, dB"),
    ("masking.activation.masked_count", "new events masked"),
    ("masking.duplicate.median_emergence_db", "dup emerges by, dB"),
    ("longest_silence_seconds", "longest silence s"),
    ("silent_fraction", "silent fraction"),
    ("phone.integrated_lufs", "phone LUFS"),
    ("fatigue.energy_above_4k_pct", "energy above 4k %"),
)


def _dig(payload: dict[str, Any], path: str) -> Any:
    node: Any = payload
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def task_compare(args: argparse.Namespace) -> int:
    """One table across every rendered configuration of a seed."""
    for seed in args.seeds:
        reports: dict[str, dict[str, Any]] = {}
        for name in args.configs or sorted(tile_score.CONFIGS):
            path = measure_path(args.out, seed, name)
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as handle:
                    reports[name] = json.load(handle)
        if not reports:
            print(f"  seed {seed}: nothing rendered yet")
            continue
        names = list(reports)
        width = max(len(name) for name in names) + 2
        print(f"\n  seed {seed}")
        print("  " + "hold / reading".ljust(30)
              + "".join(name.rjust(width) for name in names))
        holds = "".join(
            reports[name]["config"].rjust(width) for name in names)
        print("  " + "confirmation".ljust(30) + holds)
        for path, label in COMPARE_ROWS:
            cells = []
            for name in names:
                value = _dig(reports[name], path)
                cells.append(("-" if value is None
                              else (f"{value:.2f}" if isinstance(value, float)
                                    else str(value))).rjust(width))
            print("  " + label.ljust(30) + "".join(cells))
        _write_json(os.path.join(args.out, f"compare_seed{seed}.json"), reports)
    return 0


# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m satisfying.tile_phase5_cli",
        description="Category 3 Phase 5: procedural audio and sound identity.",
    )
    parser.add_argument("task", choices=[
        "export", "score", "render", "sync", "climax", "mux", "verify", "compare",
    ])
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--seeds", type=int, nargs="+", required=True)
    parser.add_argument("--config", default="v2_refined",
                        choices=sorted(tile_score.CONFIGS))
    parser.add_argument("--configs", nargs="+", default=None,
                        help="compare: which configurations to tabulate")
    parser.add_argument("--speed", type=float, default=85.0)
    parser.add_argument("--timing", default="standard",
                        choices=sorted(tile_completion.TIMINGS))
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--video", default=None,
                        help="mux: an existing MP4 whose video stream is copied")
    parser.add_argument("--frames-from", default=None,
                        help="mux: the output root holding the frame sequence")
    parser.add_argument("--kind", default="climax30_standard")
    parser.add_argument("--no-phone", action="store_true",
                        help="render: skip the phone-speaker pass")
    parser.add_argument("--godot", default=None)
    parser.add_argument("--ffmpeg", default=None)
    parser.add_argument("--width", type=int, default=DELIVERY[0])
    parser.add_argument("--height", type=int, default=DELIVERY[1])
    parser.add_argument("--phone", action="store_true")
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
    tasks = {
        "export": task_export,
        "score": task_score,
        "render": task_render,
        "sync": task_sync,
        "climax": task_climax,
        "mux": task_mux,
        "verify": task_verify,
        "compare": task_compare,
    }
    try:
        return tasks[args.task](args)
    except (Phase5Error, Phase4Error, Phase3Error,
            tile_score.ScoreError, tile_audio.AudioError,
            tile_completion.CompletionError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

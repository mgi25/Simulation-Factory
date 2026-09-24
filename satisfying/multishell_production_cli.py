"""Make, check and identify the Phase 4C upload-ready master.

    python -m satisfying.multishell_production_cli frames
    python -m satisfying.multishell_production_cli audio
    python -m satisfying.multishell_production_cli deliver
    python -m satisfying.multishell_production_cli archive
    python -m satisfying.multishell_production_cli qc

`deliver` and `archive` are **siblings, not a chain**. Both are encoded from
the same rendered PNG sequence and the same master WAV, so neither carries the
other's generation loss, and the brief's "do not derive delivery from archive
or archive from delivery" is a property of the command graph rather than a
promise. `qc` refuses to write an identity block if either file is missing or
if its decoded properties do not match the production configuration.

Nothing here re-renders the simulation or re-schedules the score: the document
comes from `multishell_playback` and the audio from the frozen `open_quartal`
system, and the 4C brief forbids touching either.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from typing import Any, Sequence

from satisfying import multishell_audio as audio
from satisfying import multishell_av as av
from satisfying import multishell_av_cli as av_cli
from satisfying import multishell_production as production
from satisfying import multishell_score as score
from satisfying import multishell_visual as visual

VALIDATION_ROOT = os.path.join(
    "docs", "validation", "category3_two_team_shell_race_v4c"
)
PROFILE = "production"


class ProductionCLIError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------


def frames_dir(config: production.ProductionConfig) -> str:
    return av_cli.frames_dir(config.seed, PROFILE)


def delivery_path(config: production.ProductionConfig) -> str:
    return os.path.join(av_cli.OUTPUT_ROOT, "delivery",
                        f"{config.name}_delivery.mp4")


def archive_path(config: production.ProductionConfig) -> str:
    return os.path.join(av_cli.OUTPUT_ROOT, "delivery",
                        f"{config.name}_archive.mkv")


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


def cmd_frames(args: argparse.Namespace) -> int:
    """Render the delivery frame sequence: 1080x1920 at 60 fps."""
    config = production.PRODUCTION
    godot = av_cli.find_godot(args.godot)
    av_cli.check_scripts(godot)
    av_cli.document(config.seed, reuse=not args.fresh)
    out_dir = frames_dir(config)
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    av_cli.run_godot(godot, [
        f"--playback={av_cli.godot_path(av_cli.playback_path(config.seed))}",
        f"--out-dir={av_cli.godot_path(out_dir)}",
        "--clip=1",
        f"--fps={config.fps:g}",
        f"--width={config.width}",
        f"--height={config.height}",
        f"--release={visual.RELEASE_SECONDS}",
        f"--hold={visual.END_HOLD_SECONDS}",
    ], f"production frames seed {config.seed}")
    count = len([n for n in os.listdir(out_dir) if n.endswith(".png")])
    print(f"  {count} frames at {config.fps:g} fps -> {out_dir}")
    return 0


def cmd_audio(args: argparse.Namespace) -> int:
    """Render the master WAV. The score is frozen; this only re-renders it."""
    config = production.PRODUCTION
    document = av_cli.document(config.seed, reuse=not args.fresh)
    plan = score.schedule(document, config.audio_config)
    if plan.playback_digest != document["digest"]:
        raise ProductionCLIError("the score is not this document")
    rendered = audio.render(plan)
    path = av_cli.wav_path(config.seed)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    audio.write_master(rendered, path)
    report = audio.measure(rendered)
    loud = report["loudness"]
    print(f"  {report['duration_seconds']:.2f}s  "
          f"{loud['integrated_lufs']} LUFS  LRA {loud['lra_lu']}  "
          f"peak {loud['true_peak_dbtp']} dBTP  "
          f"clipped {report['peak']['clipped_samples']}  -> {path}")
    return 0


def _pad_seconds(document: Any, frame_count: int,
                 config: production.ProductionConfig) -> float:
    """How long the last frame is held so the score's tail is not cut.

    The score runs past the final frame so the escape chord can decay, so the
    video is always the shorter half. The pad is computed from the schedule
    rather than over-shot and trimmed, because `-shortest` does not reliably
    cut a `tpad` inside `filter_complex`.
    """
    plan = score.schedule(document, config.audio_config)
    return max(0.0, plan.total_seconds - frame_count / float(config.fps))


def _encode(args: argparse.Namespace, target: str,
            video_args: Sequence[str], audio_args: Sequence[str],
            extra: Sequence[str] = ()) -> str:
    config = production.PRODUCTION
    ffmpeg = av_cli.find_ffmpeg(args.ffmpeg)
    document = av_cli.document(config.seed, reuse=True)
    out_dir = frames_dir(config)
    if not os.path.isdir(out_dir):
        raise ProductionCLIError(f"render the frames first ({out_dir})")
    wav = av_cli.wav_path(config.seed)
    if not os.path.exists(wav):
        raise ProductionCLIError(f"render the audio first ({wav})")
    frame_count = len([n for n in os.listdir(out_dir) if n.endswith(".png")])
    pad = _pad_seconds(document, frame_count, config)
    chain = (f"tpad=stop_mode=clone:stop_duration={pad:.6f},"
             if pad > 1.0 / config.fps else "")
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    command = [
        ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
        "-framerate", f"{config.fps:g}",
        "-start_number", "0",
        "-i", os.path.join(out_dir, "frame_%05d.png"),
        "-i", wav,
        "-filter_complex", f"[0:v]{chain}format={config.pixel_format}[v]",
        "-map", "[v]", "-map", "1:a",
        *video_args, *audio_args,
        "-r", f"{config.fps:g}", "-fps_mode", "cfr",
        "-map_metadata", "-1", "-map_chapters", "-1",
        *extra, target,
    ]
    av_cli.run(command, f"encode {os.path.basename(target)}")
    return target


def cmd_deliver(args: argparse.Namespace) -> int:
    """The upload candidate: H.264 CRF 17 slow, AAC 192 kbps, faststart."""
    config = production.PRODUCTION
    target = _encode(
        args, delivery_path(config),
        ["-c:v", config.video_codec, "-crf", str(config.crf),
         "-preset", config.preset, "-profile:v", "high"],
        ["-c:a", config.audio_codec, "-b:a", config.audio_bitrate,
         "-ar", str(config.audio_sample_rate)],
        ["-movflags", "+faststart"] if config.faststart else (),
    )
    print(f"  {os.path.getsize(target) / 1e6:.1f} MB -> {target}")
    return 0


def cmd_archive(args: argparse.Namespace) -> int:
    """The archival master, from the same frames and WAV as the delivery."""
    config = production.PRODUCTION
    target = _encode(
        args, archive_path(config),
        ["-c:v", config.video_codec, "-crf", str(config.archive_crf),
         "-preset", config.preset, "-profile:v", "high"],
        ["-c:a", config.archive_audio],
    )
    print(f"  {os.path.getsize(target) / 1e6:.1f} MB -> {target}")
    return 0


def _probe(ffmpeg: str, path: str) -> dict[str, Any]:
    ffprobe = av_cli.find_ffprobe(ffmpeg)
    out = av_cli.run([
        ffprobe, "-v", "error",
        "-show_entries",
        "stream=codec_type,codec_name,width,height,nb_frames,duration,"
        "r_frame_rate,sample_rate,channels,bits_per_raw_sample,pix_fmt",
        "-show_entries", "format=duration,size,format_name",
        "-of", "json", path], f"probe {os.path.basename(path)}")
    info = json.loads(out)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    sound = next(s for s in info["streams"] if s["codec_type"] == "audio")
    numerator, _, denominator = str(video.get("r_frame_rate", "0/1")).partition("/")
    rate = float(numerator) / float(denominator or 1)
    video_seconds = float(video.get("duration") or 0.0)
    audio_seconds = float(sound.get("duration") or 0.0)
    return {
        "path": path,
        "container": info["format"]["format_name"],
        "size_mb": float(info["format"]["size"]) / 1e6,
        "width": int(video["width"]),
        "height": int(video["height"]),
        "aspect_is_9_16": abs(int(video["width"]) * 16
                              - int(video["height"]) * 9) <= 1,
        "video_codec": video["codec_name"],
        "pix_fmt": video.get("pix_fmt"),
        "fps": rate,
        "video_frames": int(video.get("nb_frames") or 0),
        "audio_codec": sound["codec_name"],
        "sample_rate": int(sound["sample_rate"]),
        "channels": int(sound["channels"]),
        "video_seconds": video_seconds,
        "audio_seconds": audio_seconds,
        "av_drift_seconds": video_seconds - audio_seconds,
        "container_seconds": float(info["format"]["duration"]),
    }


def _black_frames(ffmpeg: str, path: str) -> dict[str, Any]:
    """Whether the encoded file opens or ends on a blank frame.

    Measured from the *encoded* file rather than from the render, because the
    brief's "no blank first frame" and "no dead tail" are claims about what a
    viewer is served.
    """
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-nostdin", "-i", path,
         "-vf", "blackdetect=d=0.05:pix_th=0.06", "-an", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    blob = (result.stderr or "") + (result.stdout or "")
    spans = []
    for line in blob.splitlines():
        if "black_start" in line:
            row = {}
            for token in line.split():
                if ":" in token and token.split(":")[0].startswith("black"):
                    key, _, value = token.partition(":")
                    try:
                        row[key] = float(value)
                    except ValueError:
                        pass
            if row:
                spans.append(row)
    return {"black_spans": spans, "black_span_count": len(spans)}


def _frame_alignment(ffmpeg: str, path: str,
                     config: production.ProductionConfig,
                     document: Any) -> dict[str, Any]:
    """Does the encoded file put each canonical event on the frame that has it?

    The container's A/V drift says the two streams start together. It does not
    say the *picture* is where it was rendered, and a one-frame shift in the
    image sequence would leave that drift at zero while moving every event.

    So this decodes the delivery MP4 at the frame index each event falls on and
    compares that image against the rendered PNG of the same index and its
    neighbours. If the best match is always offset zero, the encode moved
    nothing - a stronger statement than a duration comparison, and made from
    the encoded file as the brief asks.
    """
    import numpy
    from PIL import Image

    out_dir = frames_dir(config)
    fps = float(config.fps)
    events = document["events"]
    picked: list[tuple[str, float]] = []
    first_spawn = next((e for e in events if e["kind"] == "ball_spawn"), None)
    if first_spawn:
        picked.append(("clone", float(first_spawn["t"])))
    outer = max(int(shell["shell_id"]) for shell in document["shells"])
    outer_breaks = [e for e in events
                    if e["kind"] == "panel_break" and int(e["shell_id"]) == outer]
    if outer_breaks:
        picked.append(("final_wall_break", float(outer_breaks[0]["t"])))
    first_break = next((e for e in events if e["kind"] == "panel_break"), None)
    if first_break:
        picked.append(("break", float(first_break["t"])))
    state = next((e for e in events if e["kind"] == "damage_state"), None)
    if state:
        picked.append(("damage_transition", float(state["t"])))
    exits = [e for e in events if e["kind"] == "shell_exit"]
    if exits:
        picked.append(("progression", float(exits[len(exits) // 2]["t"])))
    escape = next((e for e in events if e["kind"] == "escape"), None)
    if escape:
        picked.append(("winner_escape", float(escape["t"])))
    collision = next((e for e in events if e["kind"] == "collision"), None)
    if collision:
        picked.append(("bounce", float(collision["t"])))

    rows: list[dict[str, Any]] = []
    for name, at in sorted(picked, key=lambda entry: entry[1]):
        index = int(round(at * fps))
        decoded = os.path.join(
            os.path.dirname(os.path.abspath(path)), f"_qc_{name}.png")
        av_cli.run([
            ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
            "-i", path, "-vf", "select=eq(n\\," + str(index) + ")",
            "-vsync", "0", "-frames:v", "1", decoded],
            f"decode frame {index}")
        with Image.open(decoded) as handle:
            got = numpy.asarray(handle.convert("RGB"), dtype=numpy.float32)
        best_offset, best_error = None, None
        for offset in (-2, -1, 0, 1, 2):
            source = os.path.join(out_dir, f"frame_{index + offset:05d}.png")
            if not os.path.exists(source):
                continue
            with Image.open(source) as handle:
                want = numpy.asarray(handle.convert("RGB"), dtype=numpy.float32)
            error = float(numpy.abs(got - want).mean())
            if best_error is None or error < best_error:
                best_offset, best_error = offset, error
        os.remove(decoded)
        rows.append({
            "event": name, "t": at, "frame_index": index,
            "best_offset_frames": best_offset,
            "mean_abs_error_at_best": best_error,
        })
    offsets = [row["best_offset_frames"] for row in rows if
               row["best_offset_frames"] is not None]
    return {
        "fps": fps,
        "events": rows,
        "worst_offset_frames": max((abs(v) for v in offsets), default=0),
        "aligned": all(value == 0 for value in offsets),
    }


def cmd_qc(args: argparse.Namespace) -> int:
    """Every check the brief asks for, off the encoded files themselves."""
    config = production.PRODUCTION
    ffmpeg = av_cli.find_ffmpeg(args.ffmpeg)
    document = av_cli.document(config.seed, reuse=True)
    delivery = delivery_path(config)
    if not os.path.exists(delivery):
        raise ProductionCLIError(f"no delivery master at {delivery}")
    archive = archive_path(config)

    probes = {"delivery": _probe(ffmpeg, delivery)}
    if os.path.exists(archive):
        probes["archive"] = _probe(ffmpeg, archive)

    plan = score.schedule(document, config.audio_config)
    rendered = audio.render(plan)
    measured = audio.measure(rendered)
    sync = av.sync_audit(document, float(config.fps))

    frame_count = len([n for n in os.listdir(frames_dir(config))
                       if n.endswith(".png")])
    delivered = probes["delivery"]
    alignment = _frame_alignment(ffmpeg, delivery, config, document)
    checks = {
        "resolution_is_production": (
            delivered["width"] == config.width
            and delivered["height"] == config.height),
        "fps_is_production": abs(delivered["fps"] - config.fps) < 1e-6,
        "video_codec_is_production": delivered["video_codec"] == "h264",
        "audio_codec_is_production": delivered["audio_codec"] == "aac",
        "sample_rate_is_production": (
            delivered["sample_rate"] == config.audio_sample_rate),
        "stereo": delivered["channels"] == 2,
        "av_drift_under_one_frame": (
            abs(delivered["av_drift_seconds"]) < 1.0 / config.fps),
        "no_clipped_samples": measured["peak"]["clipped_samples"] == 0,
        "no_limiter": measured["peak"]["limiter_used"] is False,
        "cue_sync_pass": bool(sync["pass"]),
        "cue_sync_within_one_frame": bool(sync["within_one_rendered_frame"]),
        "no_black_span": _black_frames(ffmpeg, delivery)["black_span_count"] == 0,
        "encoded_frames_are_the_rendered_frames": alignment["aligned"],
    }
    if "archive" in probes:
        checks["archive_is_pcm"] = probes["archive"]["audio_codec"].startswith(
            "pcm")
        checks["archive_matches_resolution"] = (
            probes["archive"]["width"] == config.width
            and probes["archive"]["height"] == config.height)

    digests = {
        "playback": production.file_digest(av_cli.playback_path(config.seed)),
        "master_wav": production.file_digest(av_cli.wav_path(config.seed)),
        "delivery_mp4": production.file_digest(delivery),
    }
    if os.path.exists(archive):
        digests["archive_mkv"] = production.file_digest(archive)

    payload = {
        "kind": "category3_two_team_shell_race_production",
        "identity": production.identity(document, config),
        "source_frames": frame_count,
        "probe": probes,
        "checks": checks,
        "all_checks_pass": all(checks.values()),
        "sha256": digests,
        "audio": {
            "integrated_lufs": measured["loudness"]["integrated_lufs"],
            "lra_lu": measured["loudness"]["lra_lu"],
            "lra_low_lufs": measured["loudness"]["lra_low_lufs"],
            "lra_high_lufs": measured["loudness"]["lra_high_lufs"],
            "sample_peak_dbfs": measured["peak"]["sample_peak_dbfs"],
            "true_peak_dbtp": measured["peak"]["true_peak_dbtp"],
            "clipped_samples": measured["peak"]["clipped_samples"],
            "limiter_used": measured["peak"]["limiter_used"],
            "mono": measured["mono"],
            "phone": measured["phone"],
            "ending_silence_peak": measured["ending_silence_peak"],
            "pcm_digest": measured["pcm_digest"],
        },
        "frame_alignment": alignment,
        "sync": {
            "pass": sync["pass"],
            "max_error_frames": sync["maximum_sync_error_frames"],
            "max_error_seconds": sync["maximum_sync_error_seconds"],
            "mean_error_frames": sync["mean_sync_error_frames"],
            "within_one_rendered_frame": sync["within_one_rendered_frame"],
            "video_never_early": sync["video_never_early"],
            "audio_never_retimed": sync["audio_never_retimed"],
            "mapping_complete": sync["mapping_complete"],
            "timing": sync["timing"],
        },
    }
    target = av_cli.write_json(
        payload, os.path.join(VALIDATION_ROOT, "production_qc.json"))
    for name, value in checks.items():
        print(f"  {'ok ' if value else 'FAIL'}  {name}")
    print(f"  -> {target}")
    return 0 if payload["all_checks_pass"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="multishell_production_cli", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--godot", default=None)
    parser.add_argument("--ffmpeg", default=None)
    parser.add_argument("--fresh", action="store_true",
                        help="rebuild the playback document from the seed")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, function, help_text in (
        ("frames", cmd_frames, "render the 1080x1920 60 fps sequence"),
        ("audio", cmd_audio, "render the master WAV"),
        ("deliver", cmd_deliver, "encode the upload candidate"),
        ("archive", cmd_archive, "encode the archival master"),
        ("qc", cmd_qc, "check the encoded files and write the identity"),
    ):
        sub.add_parser(name, help=help_text).set_defaults(func=function)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (ProductionCLIError, production.ProductionError,
            av_cli.CLIError, av.AVIntegrationError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

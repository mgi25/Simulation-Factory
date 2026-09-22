"""Build and verify the Category 3 Test #2 production master.

Six tasks, in the order they are meant to run:

* `prepare` - copy the already-recorded Phase 1 playback, build the score and
  the 24-bit PCM master from it, and write the production identity. Nothing
  here simulates anything.
* `render`  - drive Godot over that same document at 1080x1920, 60 fps.
* `master`  - encode two files from the frames and the PCM: the archive
  (CRF 12 + PCM) and the delivery MP4 (CRF 17 + AAC, faststart). Neither is
  made from the other, so neither carries the other's generation loss.
* `safearea`- measure the conservative Shorts gate across the whole clip.
* `verify`  - decode the delivered MP4 and check it, rather than the sources:
  frame count, resolution, rate, duration, peak, clipping, ending silence,
  and cue-by-cue A/V placement.
* `identity`- write the reproduction block on its own.

The delivery file is the only upload artefact. Everything else exists so that
the claim "this repository can make that file again" can be checked.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Sequence

from satisfying import (
    shell_audio,
    shell_av,
    shell_playback,
    shell_production,
    shell_score,
    shell_visual,
)
from satisfying.shell_av_cli import _find_ffmpeg, _find_godot, _run

ROOT = Path(__file__).resolve().parents[1]
GODOT_PROJECT = ROOT / "godot"
RENDER_SCENE = "res://scenes/ShellEscapeRender.tscn"
DEFAULT_OUT = ROOT / "output" / "category3_shell_production_v4"
DEFAULT_EVIDENCE = ROOT / "docs" / "validation" / "category3_shell_production_v4"
PHASE1 = ROOT / "docs" / "validation" / "category3_shell_escape"


class ProductionCLIError(RuntimeError):
    pass


def _json(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=1) + "\n", encoding="utf-8")
    return path


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)



def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()

def _config(args: argparse.Namespace) -> shell_production.ProductionConfig:
    """The locked production, or the backup with its seed substituted.

    `--seed 11929` is the documented escape hatch and nothing else: the
    ProductionConfig refuses any other seed outright, and the backup is only
    meant to be built if the primary fails QC.
    """
    config = shell_production.PRODUCTION
    seed = getattr(args, "seed", None)
    if seed is None or seed == config.seed:
        return config
    if seed != config.backup_seed:
        raise ProductionCLIError(
            f"seed {seed} is neither the production seed {config.seed} nor the "
            f"recorded backup {config.backup_seed}"
        )
    return _backup_config(config, seed)


def _backup_config(config: shell_production.ProductionConfig,
                   seed: int) -> shell_production.ProductionConfig:
    """The backup production: every dial identical, only the seed moved.

    `ProductionConfig.__post_init__` refuses a non-primary seed on purpose, so
    the backup is built by relaxing exactly that one rule here, in the open,
    instead of weakening the guard for everybody.
    """
    fields = config.as_dict()
    fields["seed"] = seed
    fields["name"] = f"category3_test2_seed{seed}"
    backup = object.__new__(shell_production.ProductionConfig)
    for key, value in fields.items():
        object.__setattr__(backup, key, value)
    return backup


def _paths(out: Path, config: shell_production.ProductionConfig) -> dict[str, Path]:
    return {
        "playback": out / "playback" / f"seed_{config.seed}.json",
        "score": out / "scores" / f"seed_{config.seed}_{config.audio}.score.json",
        "wav": out / "wav" / f"seed_{config.seed}_{config.audio}.wav",
        "measure": out / "measurements" / f"seed_{config.seed}_{config.audio}.measure.json",
        "frames": out / "frames" / f"seed_{config.seed}",
        "audit": out / "audits" / f"seed_{config.seed}" / "audit.json",
        "archive": out / "master" / f"{config.name}_archive.mkv",
        "delivery": out / "master" / f"{config.name}_delivery.mp4",
        "decoded": out / "master" / f"{config.name}_delivery_audio.wav",
    }


# --------------------------------------------------------------------------
# prepare
# --------------------------------------------------------------------------


def task_prepare(args: argparse.Namespace) -> int:
    config = _config(args)
    out, evidence = Path(args.out), Path(args.evidence)
    paths = _paths(out, config)

    source = PHASE1 / f"phase1_playback_seed{config.seed}.json"
    if not source.is_file():
        raise ProductionCLIError(f"missing recorded Phase 1 playback: {source}")
    document = _load(source)

    verification = shell_playback.verify_document(document)
    failed = [key for key, value in verification.items()
              if key.endswith("_matches") and not value]
    if failed:
        raise ProductionCLIError(f"playback verification failed: {failed}")
    shell_av.validate_shared_document(document)
    if document["schema_version"] != shell_visual.EXPECTED_SCHEMA_VERSION:
        raise ProductionCLIError("frozen schema moved")
    if document["config_digest"] != shell_visual.EXPECTED_CONFIG_DIGEST:
        raise ProductionCLIError("frozen simulation config digest moved")

    paths["playback"].parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, paths["playback"])

    before = json.dumps(document, sort_keys=True, separators=(",", ":"))
    plan = shell_score.schedule(document, shell_score.named_config(config.audio))
    rendered = shell_audio.render(plan)
    if json.dumps(document, sort_keys=True, separators=(",", ":")) != before:
        raise ProductionCLIError("the score mutated the canonical playback")

    score = plan.as_dict()
    score["score_fingerprint"] = plan.fingerprint()
    measurement = shell_audio.measure(rendered)
    _json(paths["score"], score)
    paths["wav"].parent.mkdir(parents=True, exist_ok=True)
    shell_audio.write_master(rendered, os.fspath(paths["wav"]))
    _json(paths["measure"], measurement)

    identity = shell_production.identity(document, config)
    identity["production_digest"] = shell_production.production_digest(document, config)
    identity["pcm_digest"] = rendered.digest()
    identity["score_fingerprint"] = plan.fingerprint()
    _json(evidence / "production_identity.json", identity)
    _json(evidence / "scores" / paths["score"].name, score)
    _json(evidence / "measurements" / paths["measure"].name, measurement)

    print(f"seed {config.seed}: playback {document['digest'][:16]}  "
          f"score {plan.fingerprint()[:16]}  PCM {rendered.digest()[:16]}")
    print(f"  expected frames at {config.fps:g} fps: "
          f"{shell_production.rendered_frame_count(document, config.fps)}")
    return 0


# --------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------


def _godot(args: argparse.Namespace, config: shell_production.ProductionConfig,
           audit: bool) -> None:
    godot = _find_godot(args.godot)
    paths = _paths(Path(args.out), config)
    target = paths["audit"].parent if audit else paths["frames"]
    target.mkdir(parents=True, exist_ok=True)
    command = [
        godot, "--path", os.fspath(GODOT_PROJECT), RENDER_SCENE, "--",
        f"--playback={paths['playback'].resolve().as_posix()}",
        f"--out-dir={target.resolve().as_posix()}",
        f"--width={config.width}", f"--height={config.height}",
        f"--fps={config.fps:g}",
        "--audit=1" if audit else "--clip=1",
    ]
    _run(command, f"Godot {'audit' if audit else 'render'} seed {config.seed}")


def task_render(args: argparse.Namespace) -> int:
    config = _config(args)
    out = Path(args.out)
    paths = _paths(out, config)
    if not paths["playback"].is_file():
        raise ProductionCLIError("run `prepare` before `render`")
    document = _load(paths["playback"])
    expected = shell_production.rendered_frame_count(document, config.fps)

    existing = sorted(paths["frames"].glob("frame_*.png"))
    if len(existing) == expected and not args.force:
        print(f"{expected} frames already rendered; pass --force to redo")
        return 0
    if existing:
        for path in existing:
            path.unlink()
    _godot(args, config, False)

    frames = sorted(paths["frames"].glob("frame_*.png"))
    if len(frames) != expected:
        raise ProductionCLIError(
            f"render is incomplete: {len(frames)} frames, expected {expected}"
        )
    print(f"  {len(frames)} frames at {config.width}x{config.height}")
    return 0


# --------------------------------------------------------------------------
# master
# --------------------------------------------------------------------------


def _ffprobe(ffmpeg: str, path: Path) -> dict[str, Any]:
    probe = Path(ffmpeg).with_name("ffprobe.exe")
    executable = os.fspath(probe if probe.is_file() else "ffprobe")
    result = subprocess.run(
        [executable, "-v", "error", "-show_streams", "-show_format",
         "-of", "json", os.fspath(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode:
        raise ProductionCLIError(f"ffprobe failed for {path}: {result.stderr}")
    return json.loads(result.stdout)


def _faststart(path: Path) -> bool:
    """True when `moov` precedes `mdat`, which is what faststart means."""
    with path.open("rb") as handle:
        head = handle.read(4 << 20)
    moov, mdat = head.find(b"moov"), head.find(b"mdat")
    return moov != -1 and (mdat == -1 or moov < mdat)


def task_master(args: argparse.Namespace) -> int:
    config = _config(args)
    out, evidence = Path(args.out), Path(args.evidence)
    paths = _paths(out, config)
    ffmpeg = _find_ffmpeg(args.ffmpeg)

    if not paths["wav"].is_file():
        raise ProductionCLIError("run `prepare` before `master`")
    frames = sorted(paths["frames"].glob("frame_*.png"))
    if not frames:
        raise ProductionCLIError("run `render` before `master`")
    document = _load(paths["playback"])
    expected = shell_production.rendered_frame_count(document, config.fps)
    if len(frames) != expected:
        raise ProductionCLIError(
            f"refusing to master an incomplete render: {len(frames)}/{expected}"
        )
    paths["archive"].parent.mkdir(parents=True, exist_ok=True)

    colour = [
        "-color_primaries", config.colour_primaries,
        "-color_trc", config.colour_trc,
        "-colorspace", config.colour_space,
    ]
    # The picture ends one rendered frame before the score finishes resolving,
    # so the final frame is cloned out to the score end and `-shortest` trims
    # the pad exactly there. This is the padding Phase 3 measured.
    source = [
        "-framerate", f"{config.fps:g}", "-start_number", "0",
        "-i", os.fspath(paths["frames"] / "frame_%06d.png"),
        "-i", os.fspath(paths["wav"]),
        "-filter_complex", "[0:v]tpad=stop_mode=clone:stop_duration=1[v]",
        "-map", "[v]", "-map", "1:a:0",
    ]

    _run([ffmpeg, "-y", *source,
          "-c:v", config.video_codec, "-preset", config.preset,
          "-crf", str(config.archive_crf),
          "-pix_fmt", config.pixel_format, *colour,
          "-c:a", config.archive_audio,
          "-shortest", os.fspath(paths["archive"])],
         "archive")

    movflags = ["-movflags", "+faststart"] if config.faststart else []
    _run([ffmpeg, "-y", *source,
          "-c:v", config.video_codec, "-preset", config.preset,
          "-crf", str(config.crf),
          "-pix_fmt", config.pixel_format, *colour,
          "-c:a", config.audio_codec, "-b:a", config.audio_bitrate,
          "-ar", str(config.audio_sample_rate),
          *movflags, "-shortest", os.fspath(paths["delivery"])],
         "delivery")

    for label, path in (("archive", paths["archive"]), ("delivery", paths["delivery"])):
        probe = _ffprobe(ffmpeg, path)
        _json(out / "delivery" / f"{label}.probe.json", probe)
        _json(evidence / "delivery" / f"{label}.probe.json", probe)
        print(f"  {label}: {path.stat().st_size / 1_048_576:.1f} MB  -> {path}")
    print(f"  {len(frames)} frames encoded twice from one source; "
          f"neither file was made from the other")
    return 0


# --------------------------------------------------------------------------
# safearea
# --------------------------------------------------------------------------


def task_safearea(args: argparse.Namespace) -> int:
    config = _config(args)
    out, evidence = Path(args.out), Path(args.evidence)
    document = _load(_paths(out, config)["playback"])
    report = shell_visual.safe_area_report(
        document, config.safe_area_config, config.width, config.height
    )
    report["fps"] = config.fps
    report["seed"] = config.seed
    _json(evidence / "safe_area.json", report)
    print(f"safe area {report['safe_area']} at {config.fps:g} fps: "
          f"{'PASS' if report['gate_pass'] else 'FAIL'}")
    print(f"  arena {report['arena_occupancy_width_pct']:.2f}% width, "
          f"outer clearance {report['outer_shell_clearance_px']:.1f} px, "
          f"hook {report['hook_clearance_px']:.1f} px")
    print(f"  ball hidden {report['ball_hidden_frames']}/{report['ball_frames']} "
          f"frames, openings {'clear' if report['openings_clear'] else 'OBSTRUCTED'}, "
          f"final escape {report['final_escape_clearance_px']:.1f} px")
    return 0 if report["gate_pass"] else 1


# --------------------------------------------------------------------------
# verify
# --------------------------------------------------------------------------


def _decode_audio(ffmpeg: str, source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    _run([ffmpeg, "-y", "-i", os.fspath(source), "-vn",
          "-c:a", "pcm_s24le", os.fspath(target)], "decode delivery audio")


def task_verify(args: argparse.Namespace) -> int:
    from audio import loudness

    config = _config(args)
    out, evidence = Path(args.out), Path(args.evidence)
    paths = _paths(out, config)
    ffmpeg = _find_ffmpeg(args.ffmpeg)
    document = _load(paths["playback"])
    failures: list[str] = []

    def fail(area: str, message: str) -> None:
        failures.append(f"{area}: {message}")

    report: dict[str, Any] = {
        "format": "category3-test2-shell-production-verify/1.0.0",
        "seed": config.seed,
        "production_fingerprint": config.fingerprint(),
        "production_digest": shell_production.production_digest(document, config),
        "playback_digest": document["digest"],
    }

    # --- the container ----------------------------------------------------
    probe = _ffprobe(ffmpeg, paths["delivery"])
    video = next(s for s in probe["streams"] if s["codec_type"] == "video")
    audio_stream = next(s for s in probe["streams"] if s["codec_type"] == "audio")
    expected_frames = shell_production.rendered_frame_count(document, config.fps)
    fps = float(video["r_frame_rate"].split("/")[0]) / float(
        video["r_frame_rate"].split("/")[1])
    container = {
        "path": os.fspath(paths["delivery"]),
        "size_bytes": paths["delivery"].stat().st_size,
        "width": int(video["width"]),
        "height": int(video["height"]),
        "fps": fps,
        "video_codec": video["codec_name"],
        "pixel_format": video["pix_fmt"],
        "colour": [video.get("color_primaries"), video.get("color_transfer"),
                   video.get("color_space")],
        "audio_codec": audio_stream["codec_name"],
        "audio_sample_rate": int(audio_stream["sample_rate"]),
        "audio_channels": int(audio_stream["channels"]),
        "muxed_frames": int(video["nb_frames"]),
        "rendered_frames": expected_frames,
        "duration_seconds": float(probe["format"]["duration"]),
        "faststart": _faststart(paths["delivery"]),
    }
    report["container"] = container

    if (container["width"], container["height"]) != (config.width, config.height):
        fail("frame", f"{container['width']}x{container['height']} delivered")
    if abs(fps - config.fps) > 1e-6:
        fail("frame", f"{fps} fps delivered, expected {config.fps}")
    if container["video_codec"] != "h264":
        fail("video", f"codec {container['video_codec']}")
    if container["pixel_format"] != config.pixel_format:
        fail("video", f"pixel format {container['pixel_format']}")
    if container["audio_codec"] != config.audio_codec:
        fail("audio", f"codec {container['audio_codec']}")
    if container["audio_sample_rate"] != config.audio_sample_rate:
        fail("audio", f"sample rate {container['audio_sample_rate']}")
    if config.faststart and not container["faststart"]:
        fail("container", "moov does not precede mdat; faststart did not apply")
    # The muxed count is the rendered count plus the cloned tail, and the tail
    # may never be longer than the gap the score actually leaves.
    if container["muxed_frames"] < expected_frames:
        fail("video", f"{container['muxed_frames']} muxed frames is fewer than "
                      f"the {expected_frames} rendered")
    padding = container["muxed_frames"] - expected_frames
    report["final_frame_padding_frames"] = padding
    if padding > math.ceil(config.fps):
        fail("video", f"{padding} cloned frames is more than one second of tail")

    # --- the delivered audio, decoded -------------------------------------
    _decode_audio(ffmpeg, paths["delivery"], paths["decoded"])
    samples, sample_rate = loudness.read_pcm(os.fspath(paths["decoded"]))
    source_samples, _ = loudness.read_pcm(os.fspath(paths["wav"]))
    measured = loudness.measure(samples, sample_rate)
    peak = float(abs(samples).max())
    clipped = int((abs(samples) >= 1.0).sum())
    tail = samples[-int(0.05 * sample_rate):]
    # `lra` returns (range, low, high), in that order.
    lra_range, lra_low, lra_high = loudness.lra(samples, sample_rate)
    audio_report = {
        "seconds": round(samples.shape[0] / sample_rate, 4),
        "source_seconds": round(source_samples.shape[0] / sample_rate, 4),
        "sample_peak_dbfs": round(20.0 * math.log10(max(peak, 1e-12)), 3),
        "true_peak_dbtp": round(loudness.true_peak(samples), 3),
        "integrated_lufs": round(measured.integrated_lufs, 2),
        "loudness_range_lu": round(lra_range, 3),
        "loudness_low_lufs": round(lra_low, 2),
        "loudness_high_lufs": round(lra_high, 2),
        "clipped_samples": clipped,
        "final_50ms_peak_dbfs": round(
            20.0 * math.log10(max(float(abs(tail).max()), 1e-12)), 2),
        "delivery_ceiling_dbtp": shell_production.DELIVERY_TRUE_PEAK_DBTP,
    }
    report["audio"] = audio_report
    if clipped:
        fail("audio", f"{clipped} clipped samples in the delivered file")
    if audio_report["true_peak_dbtp"] > shell_production.DELIVERY_TRUE_PEAK_DBTP:
        fail("audio", f"true peak {audio_report['true_peak_dbtp']} dBTP exceeds "
                      f"{shell_production.DELIVERY_TRUE_PEAK_DBTP}")
    if audio_report["final_50ms_peak_dbfs"] > -40.0:
        fail("ending", "the last 50 ms is not silent: "
                       f"{audio_report['final_50ms_peak_dbfs']} dBFS")

    # --- mono and phone ----------------------------------------------------
    report["mono"] = {
        key: (round(value, 4) if isinstance(value, (int, float)) else value)
        for key, value in loudness.mono_compatibility(samples, sample_rate).items()
    }
    phone = loudness.phone_filter(samples, sample_rate)
    bands = loudness.band_profile(phone, sample_rate)
    report["phone"] = {
        # `band_profile` reports each band as a percentage of total energy.
        "energy_300_2000_pct": round(bands["300-800"] + bands["800-2000"], 3),
        "energy_above_300_pct": round(loudness.energy_above(phone, 300.0, sample_rate), 3),
        "bands_pct": {key: round(value, 3) for key, value in bands.items()},
        "integrated_lufs": round(loudness.measure(phone, sample_rate).integrated_lufs, 2),
    }

    # --- synchronisation, on the delivered frame grid ----------------------
    if not paths["audit"].is_file():
        raise ProductionCLIError("run `audit` before `verify`")
    sync = shell_av.sync_audit(document, _load(paths["audit"]), int(config.fps))
    report["sync"] = sync
    if not sync["pass"]:
        fail("sync", "the canonical audit did not pass")
    for kind, row in sync["timing"].items():
        if not row["within_one_frame"]:
            fail("sync", f"{kind} exceeds one rendered frame")

    # --- picture and score agree on length ---------------------------------
    drift = container["duration_seconds"] - audio_report["seconds"]
    report["drift_seconds"] = round(drift, 6)
    if abs(drift) > 1.0 / config.fps:
        fail("sync", f"container and audio differ by {drift:.4f} s")

    # --- the reproduction hashes ------------------------------------------
    # The encoded files are not claimed to be bit-reproducible - x264 differs
    # between builds - so these identify *this* master. The playback and the
    # PCM above it are exactly reproducible, and those digests are the ones a
    # rebuild has to match.
    report["hashes"] = {
        "playback_sha256": _sha256(paths["playback"]),
        "wav_sha256": _sha256(paths["wav"]),
        "delivery_sha256": _sha256(paths["delivery"]),
        "archive_sha256": _sha256(paths["archive"]) if paths["archive"].is_file() else None,
    }

    report["failures"] = failures
    report["pass"] = not failures
    _json(evidence / "delivery_verification.json", report)

    print(f"delivery {container['width']}x{container['height']} @ {fps:g} fps, "
          f"{container['duration_seconds']:.3f} s, "
          f"{container['size_bytes'] / 1_048_576:.1f} MB")
    print(f"  peak {audio_report['sample_peak_dbfs']:+.2f} dBFS / "
          f"{audio_report['true_peak_dbtp']:+.2f} dBTP  "
          f"{audio_report['integrated_lufs']:+.2f} LUFS  "
          f"LRA {audio_report['loudness_range_lu']:.2f} LU  "
          f"clip {clipped}")
    print(f"  sync max {sync['maximum_sync_error_seconds'] * 1000:.3f} ms "
          f"({sync['maximum_sync_error_frames']:.6f} frame)")
    print(f"  mono loss {report['mono']['mono_loss_db']:+.2f} dB, "
          f"correlation {report['mono']['correlation']:.4f}; "
          f"phone 300-2000 Hz {report['phone']['energy_300_2000_pct']:.2f}%")
    if failures:
        for line in failures:
            print(f"  FAIL {line}")
        return 1
    print("  PASS")
    return 0


def task_audit(args: argparse.Namespace) -> int:
    config = _config(args)
    out, evidence = Path(args.out), Path(args.evidence)
    paths = _paths(out, config)
    _godot(args, config, True)
    document = _load(paths["playback"])
    report = shell_av.sync_audit(document, _load(paths["audit"]), int(config.fps))
    _json(evidence / "sync.json", report)
    print(f"sync max {report['maximum_sync_error_seconds'] * 1000:.3f} ms "
          f"({report['maximum_sync_error_frames']:.6f} frame), "
          f"{'PASS' if report['pass'] else 'FAIL'}")
    return 0 if report["pass"] else 1


def task_identity(args: argparse.Namespace) -> int:
    config = _config(args)
    out, evidence = Path(args.out), Path(args.evidence)
    document = _load(_paths(out, config)["playback"])
    identity = shell_production.identity(document, config)
    identity["production_digest"] = shell_production.production_digest(document, config)
    _json(evidence / "production_identity.json", identity)
    print(json.dumps(identity, indent=1))
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("task", choices=(
        "prepare", "render", "audit", "master", "safearea", "verify", "identity",
    ))
    result.add_argument("--out", default=os.fspath(DEFAULT_OUT))
    result.add_argument("--evidence", default=os.fspath(DEFAULT_EVIDENCE))
    result.add_argument("--seed", type=int)
    result.add_argument("--godot")
    result.add_argument("--ffmpeg")
    result.add_argument("--force", action="store_true")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return int({
        "prepare": task_prepare,
        "render": task_render,
        "audit": task_audit,
        "master": task_master,
        "safearea": task_safearea,
        "verify": task_verify,
        "identity": task_identity,
    }[args.task](args))


if __name__ == "__main__":
    raise SystemExit(main())
